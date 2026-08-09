/**
 * Mainline independent measurement for slice I (L3): are the 5 language packs
 * key-for-key equal, and is LOCALE_OPTIONS exactly the set of packs that exist?
 *
 * This is run by the MAINLINE, not by slice I, so slice I's answer can be
 * cross-checked rather than accepted. It loads the real modules through the
 * app's own toolchain instead of regex-counting `key: '...'` lines, because a
 * regex cannot tell a nested object from a template literal spanning lines.
 *
 * Run: bash data/r10b/probes/run_i18n_parity.sh
 */
import { describe, expect, it } from 'vitest'

import { TRANSLATIONS } from '@/i18n/catalog'
import { LOCALE_OPTIONS } from '@/i18n/languages'

function leaves(obj: unknown, prefix = '', out: string[] = []): string[] {
  if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      leaves(v, prefix ? `${prefix}.${k}` : k, out)
    }
  } else {
    out.push(prefix)
  }
  return out
}

describe('i18n leaf-key parity (mainline probe)', () => {
  it('reports leaf counts and diffs against en', () => {
    const keys: Record<string, string[]> = {}
    for (const [loc, pack] of Object.entries(TRANSLATIONS)) {
      keys[loc] = leaves(pack).sort()
    }
    const rows = Object.entries(keys).map(([l, k]) => `${l}=${k.length}`)
    // eslint-disable-next-line no-console
    console.log(`LEAF_COUNTS ${rows.join(' ')}`)

    const en = new Set(keys.en)
    for (const [loc, k] of Object.entries(keys)) {
      if (loc === 'en') continue
      const missing = keys.en.filter(x => !new Set(k).has(x))
      const extra = k.filter(x => !en.has(x))
      // eslint-disable-next-line no-console
      console.log(`DIFF_VS_EN ${loc} missing=${missing.length} extra=${extra.length}` +
        (missing.length ? ` firstMissing=${missing.slice(0, 3).join(',')}` : '') +
        (extra.length ? ` firstExtra=${extra.slice(0, 3).join(',')}` : ''))
    }

    const declared = LOCALE_OPTIONS.map(o => o.id).sort()
    const present = Object.keys(TRANSLATIONS).sort()
    // eslint-disable-next-line no-console
    console.log(`LOCALE_OPTIONS=[${declared.join(',')}] TRANSLATIONS=[${present.join(',')}] equal=${
      JSON.stringify(declared) === JSON.stringify(present)}`)
    expect(present.length).toBeGreaterThan(0)
  })
})
