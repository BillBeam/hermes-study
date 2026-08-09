/**
 * H-R10-f runtime probe: does the TUI go deaf after a gateway restart?
 *
 * R10 handed this over as "static inference, not reproduced -- needs a real
 * gateway". It does not need a real gateway: the repo's own test suite already
 * mocks the transport (ui-tui/src/__tests__/gatewayClient.test.ts), and the
 * FakeWebSocket harness below is that file's, reused verbatim in shape.
 *
 * The claim under test:
 *   - gatewayClient.ts:221  `this.subscribed = false`  lives in resetStartupState()
 *   - resetStartupState() is called from start()       (gatewayClient.ts:530)
 *   - the ONLY place that sets `subscribed = true` is the deferred flush inside
 *     drain()                                          (gatewayClient.ts:647)
 *   - the ONLY production caller of drain() is the mount effect in
 *     ui-tui/src/app/useMainApp.ts:858, whose deps are [gw, sys] -- both stable
 *
 * If all four hold, then the recovery path (useMainApp.ts:846 calls gw.start()
 * from the exit handler) flips `subscribed` back to false and nothing ever
 * flips it on again: publish() buffers forever (gatewayClient.ts:170-174) and
 * handleTransportExit() stores pendingExit instead of emitting (:261-265).
 *
 * Run:  bash data/r10b/probes/run_h_r10f_probe.sh
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

interface ListenerEntry {
  callback: (event: any) => void
  once: boolean
}

const { FakeWebSocket } = vi.hoisted(() => {
  class FakeWebSocket {
    static CONNECTING = 0
    static OPEN = 1
    static CLOSING = 2
    static CLOSED = 3
    static instances: FakeWebSocket[] = []

    readyState = FakeWebSocket.CONNECTING
    sent: string[] = []
    readonly url: string
    private listeners = new Map<string, ListenerEntry[]>()

    constructor(url: string) {
      this.url = url
      FakeWebSocket.instances.push(this)
    }

    static reset() {
      FakeWebSocket.instances = []
    }

    addEventListener(type: string, callback: (event: any) => void, options?: unknown) {
      const once =
        typeof options === 'object' &&
        options !== null &&
        'once' in options &&
        Boolean((options as { once?: unknown }).once)
      const entries = this.listeners.get(type) ?? []

      entries.push({ callback, once })
      this.listeners.set(type, entries)
    }

    removeEventListener(type: string, callback: (event: any) => void) {
      const entries = this.listeners.get(type)

      if (!entries) {
        return
      }

      this.listeners.set(
        type,
        entries.filter(entry => entry.callback !== callback)
      )
    }

    send(payload: string) {
      if (this.readyState !== FakeWebSocket.OPEN) {
        throw new Error('socket not open')
      }

      this.sent.push(payload)
    }

    close(code = 1000) {
      if (this.readyState === FakeWebSocket.CLOSED) {
        return
      }

      this.readyState = FakeWebSocket.CLOSED
      this.emit('close', { code })
    }

    open() {
      this.readyState = FakeWebSocket.OPEN
      this.emit('open', {})
    }

    message(data: string) {
      this.emit('message', { data })
    }

    private emit(type: string, event: any) {
      const entries = [...(this.listeners.get(type) ?? [])]

      for (const entry of entries) {
        entry.callback(event)

        if (entry.once) {
          this.removeEventListener(type, entry.callback)
        }
      }
    }
  }

  return { FakeWebSocket }
})

vi.mock('undici', () => ({ WebSocket: FakeWebSocket }))

import { GatewayClient } from '../gatewayClient.js'

const evFrame = (type: string) =>
  JSON.stringify({ jsonrpc: '2.0', method: 'event', params: { type, payload: {} } })

describe('H-R10-f: subscription state across a gateway restart', () => {
  const originalWebSocket = globalThis.WebSocket
  let originalGatewayUrl: string | undefined

  beforeEach(() => {
    originalGatewayUrl = process.env.HERMES_TUI_GATEWAY_URL
    FakeWebSocket.reset()
    ;(globalThis as { WebSocket?: unknown }).WebSocket = FakeWebSocket as unknown as typeof WebSocket
  })

  afterEach(() => {
    if (originalGatewayUrl === undefined) {
      delete process.env.HERMES_TUI_GATEWAY_URL
    } else {
      process.env.HERMES_TUI_GATEWAY_URL = originalGatewayUrl
    }

    FakeWebSocket.reset()

    if (originalWebSocket) {
      globalThis.WebSocket = originalWebSocket
    } else {
      delete (globalThis as { WebSocket?: unknown }).WebSocket
    }
  })

  it('CONTROL: before any restart, a live event reaches the subscriber', async () => {
    process.env.HERMES_TUI_GATEWAY_URL = 'ws://gateway.test/api/ws?token=abc'
    const gw = new GatewayClient()
    const seen: string[] = []

    gw.start()
    FakeWebSocket.instances[0]!.open()
    gw.on('event', ev => seen.push(ev.type))
    gw.drain()
    await vi.waitFor(() => expect(seen).toEqual([]))

    FakeWebSocket.instances[0]!.message(evFrame('session.info'))
    await vi.waitFor(() => expect(seen).toEqual(['session.info']))

    gw.kill()
  })

  it('PROBE: after start() is called again (the recovery path), live events stop arriving', async () => {
    process.env.HERMES_TUI_GATEWAY_URL = 'ws://gateway.test/api/ws?token=abc'
    const gw = new GatewayClient()
    const seen: string[] = []

    // --- mount: subscribe exactly the way useMainApp.ts:856-858 does ---
    gw.start()
    FakeWebSocket.instances[0]!.open()
    gw.on('event', ev => seen.push(ev.type))
    gw.drain()
    FakeWebSocket.instances[0]!.message(evFrame('before.restart'))
    await vi.waitFor(() => expect(seen).toContain('before.restart'))

    // --- the gateway dies and useMainApp.ts:846 restarts it. The mount effect
    //     does NOT re-run: its deps [gw, sys] are unchanged. So no second
    //     drain() -- which is the whole point of the claim.
    gw.start()
    const fresh = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]!

    fresh.open()
    fresh.message(evFrame('after.restart'))

    // Give any deferred flush a chance to run before judging.
    await new Promise(r => setTimeout(r, 25))

    // eslint-disable-next-line no-console
    console.log(`H-R10-f events seen after restart: ${JSON.stringify(seen)}`)
    expect(seen).toContain('before.restart')
    expect(seen).not.toContain('after.restart') // <- the defect, asserted as present

    gw.kill()
  })

  it('PROBE: and a later gateway exit is swallowed too (pendingExit, never emitted)', async () => {
    process.env.HERMES_TUI_GATEWAY_URL = 'ws://gateway.test/api/ws?token=abc'
    const gw = new GatewayClient()
    const exits: (number | null)[] = []

    gw.start()
    FakeWebSocket.instances[0]!.open()
    gw.on('exit', code => exits.push(code))
    gw.drain()
    await new Promise(r => setTimeout(r, 10))

    gw.start() // recovery path -> subscribed = false, nothing turns it back on
    const fresh = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]!

    fresh.open()
    fresh.close(1006) // transport dies again
    await new Promise(r => setTimeout(r, 25))

    // eslint-disable-next-line no-console
    console.log(`H-R10-f exit events after restart: ${JSON.stringify(exits)}`)
    expect(exits).toEqual([]) // <- the UI never learns the gateway died again

    gw.kill()
  })
})
