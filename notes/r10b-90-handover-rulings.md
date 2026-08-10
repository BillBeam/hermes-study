# r10b · 移交项定案 —— 底稿

> 溯源约定:凡对 hermes-agent 行为的断言,锚点写作 `路径:行号 @ 863e313`,
> **单独成行、置于代码块之前**。本文件是证据层,求全求证。

## 0. 本轮的移交收件箱里有什么

先回答「有多少条、哪些归本轮」。机械普查:

```verify
cd /home/user/hermes-study && python3 data/r10b/probes/handover_census.py --open-only | tail -3
```

```text
H-R9D-f          9d-l1-completion R11B                       —          OPEN

总计 66 条,其中未结清 32 条
```

*本轮在这个脚本上又踩到第二处同型缺陷*:**未提交的报告没有「加入提交」,`git log` 返回空,
回落成 `ts=0` 就把它排成了最老的一份** —— 而它其实是最新的。后果是本报告 §11.2 的定案表
在提交前**不生效**,未结清数读作 35;提交后才变回 32。已改为把未跟踪文件当作最新。
**和它替换掉的那张手工清单是同一个病:输入面的顺序错了,输出看起来完全正常。**

*两个读数*:**开工时是 59 条 / 未结清 28 条**;上面是**本轮报告落地之后**的读数,
差额 7 条正是本报告新提的移交项。普查扫 `reports/`,而本轮报告就在里面——
**它一写完就改变了自己报的数**。

**搜索面**:`reports/round-*.md` 全部 20 份报告的**全部表格行**;表头含「去向」或
「建议轮次」的判为移交表,含「处置结论」/「结论」/「复核结果」的判为定案表;
一条 `H-*` 最后一次出现在移交表(而非定案表)即判 OPEN。**未扫 `notes/`**
——这正是 H-R10-c 记下的账目问题(结清可能只写在底稿散文里),本轮不改这一点。

### 0.1 先记一条普查工具自己的缺陷(本轮开工时撞见)

R10 版普查脚本把报告的时间序写成**一张手工清单**(`data/r10/probes/handover_census.py`
的 `ORDER`)。清单里没有 R10 自己的报告,于是本轮开工跑它,读到的仍是「52 条」——
**H-R10-a..f 六条 + H-R10E-c 共 7 条一条都没出现,输出里没有任何提示**。
「漏了一整轮」和「那一轮没有移交项」在它的输出里长得一模一样。

本轮的 `data/r10b/probes/handover_census.py` 改为向 git 要顺序,清单不再需要有人记得维护:

```verify
cd /home/user/hermes-study && diff \
  <(python3 data/r10/probes/handover_census.py  | awk '/^H-/{print $1}' | sort) \
  <(python3 data/r10b/probes/handover_census.py | awk '/^H-/{print $1}' | sort)
```

```text
5a6,19
> H-R10-a
> H-R10-b
> H-R10-c
> H-R10-d
> H-R10-e
> H-R10-f
> H-R10B-a
> H-R10B-b
> H-R10B-c
> H-R10B-d
> H-R10B-e
> H-R10B-f
> H-R10B-g
> H-R10E-c
```

*同上*:R10B 版能看见本轮报告新提的 7 条,R10 版看不见(它的手工清单里既没有 R10 也没有 R10B),
所以差集现在是 14 条而不是开工时的 7 条。**这恰好又演示了一遍这条移交项本身。**

**这条并入 H-R10-c 一起交 R11 复盘**:H-R10-c 说的是「结清记录有两个存放地」,
本条是同一个病的另一面——**普查的输入面本身要靠人记得维护**。
两条合起来才是完整的问题:*一个用来发现遗漏的工具,自己会静默遗漏。*

## 1. 归本轮的三条

去向列点名 R10B 的只有 **H-R10-e** 与 **H-R10-f**;**H-R10-a** 的去向写的是 R11A,
但任务书把它指定为本轮开工杂项(理由:它是后续所有轮次的公共设施),故一并在此定案。

---

### 1.1 H-R10-a —— **结清**,并且比移交项描述的更宽

**移交项原文**(`reports/round-10-client-interface-layer.md` §13):扩展名白名单不含
`h`/`mjs`/`nix`/`rs`,这些锚点连"引用"都不算,不校验也不计 UNCHECKED;放宽时须避免把
`sqlite.org:443` 当锚点。

**处置:已修,并发现移交项没点到的两处同型缺陷。** 详见
`notes/r10b-01-scope-and-criteria.md` §3,此处只记结论:

| # | 缺陷 | 移交项有没有点到 |
|---|---|---|
| 1 | 白名单缺 `h`/`mjs`/`nix`/`rs` | **有** |
| 2 | 白名单还缺 `mdx`(6 处)与 `txt`(1 处) | **没有**。`.mdx` 那 6 处全部指向 `website/docs/`,而 CLAUDE.md 正是把 `website/docs` 列为「作者自绘地图」——**每一条 ▲ 的文档侧都在那里**,却从来不被识别成锚点 |
| 3 | 路径正则不允许前导点,`.github/...` 被解析成 `github/...`,永远解析不到 | **没有**(但 R10 的片 I 底稿散文里提过一句) |

**为什么第 2 条比第 1 条重**:R7C 当年把引用校验升格为关卡、R8-fix 又把 `>` 引用块纳入校验,
给出的理由都是同一条——**「代码侧有脚本兜着所以稳,文档侧只有人工约定所以漂」**。
`.mdx` 这个口子的效果,是把那次扩面在 `website/docs` 上**整个抵消掉了**:
引用块规则管得着 `>` 块,却管不着一条根本没被识别成锚点的引用。

---

### 1.2 H-R10-e —— **结清:它就是本轮的范围**

**移交项原文**:`data/r10/slices/REMAINDER.txt` 的 977 行清单 —— R10 显式未吃的
977 文件 / 214,245 行,含 `apps/desktop/src/` 816 文件与全部 13 个 L3 文件。

**处置:开工先核,与移交项逐字一致,已全部吃下并切 11 片。**

```verify
cd /home/user/hermes-study && python3 data/r10b/probes/make_slices.py
```

核出的分层构成:**964 个 L2(196,867 行)+ 13 个 L3(17,378 行)**,
`status` 开工时全部为 `R1-inventoried`、`round` 全部为 `R10`。
13 个 L3 单独切为片 I,理由与判据见 `data/r10b/l3-criteria.md`。

---

### 1.3 H-R10-f —— **维持,并升级:由「静态推演」升为「实测复现」,且移交项说的复现条件是错的**

**移交项原文**:`ui-tui/src/gatewayClient.ts:221`:`this.subscribed = false` ——
网关重启后订阅开关无复位路径(唯一开启点在 `drain()`,唯一调用点在依赖恒定的 mount effect);
**静态推演,未实测,需起真实网关复现**。

**处置:结论成立,证据等级从静态推演提到实测;但「需起真实网关」这个前提不成立
——仓库自己的测试套件早就把传输层 mock 掉了,复现只要 100 行探针。**

#### (a) 机制:三段代码合起来构成一个单向开关

订阅关掉的地方 ——

`ui-tui/src/gatewayClient.ts:213-221 @ 863e313`

```ts
  private resetStartupState() {
    // Reject any in-flight RPCs left over from the previous transport
    // before we swap. Otherwise the old transport's stale exit/close
    // handlers (now identity-gated to ignore unrelated transports)
    // never fire `rejectPending`, leaving callers hanging on promises
    // attached to a discarded child / socket.
    this.rejectPending(new Error('gateway restarting'))
    this.ready = false
    this.subscribed = false
```

它由 `start()` 无条件调用 ——

`ui-tui/src/gatewayClient.ts:523-530 @ 863e313`

```ts
  start() {
    const root = process.env.HERMES_PYTHON_SRC_ROOT ?? resolve(import.meta.dirname, '../../')
    const attachUrl = resolveGatewayAttachUrl()
    const sidecarUrl = resolveSidecarUrl()

    this.attachUrl = attachUrl
    this.sidecarUrl = sidecarUrl
    this.resetStartupState()
```

而订阅**打开**的地方全仓只有一处,在 `drain()` 排的那个微任务里 ——

`ui-tui/src/gatewayClient.ts:642-647 @ 863e313`

```ts
    queueMicrotask(() => {
      if (this.drainGeneration !== generation) {
        return
      }

      this.subscribed = true
```

关掉之后会怎样:事件进缓冲区不再外发 ——

`ui-tui/src/gatewayClient.ts:170-174 @ 863e313`

```ts
    if (this.subscribed) {
      return void this.emit('event', ev)
    }

    this.bufferedEvents.push(ev)
```

—— 而且**连"网关又死了"都不再上报**,只是记进 `pendingExit`:

`ui-tui/src/gatewayClient.ts:261-265 @ 863e313`

```ts
    if (this.subscribed) {
      this.emit('exit', code)
    } else {
      this.pendingExit = code
    }
```

#### (b) 为什么没有第二次 `drain()`:三个恒定量

唯一的生产调用点在 mount effect 里,依赖是 `[gw, sys]`:

`ui-tui/src/app/useMainApp.ts:856-865 @ 863e313`

```ts
    gw.on('event', handler)
    gw.on('exit', exitHandler)
    gw.drain()

    // entry.tsx's setupGracefulExit handles process cleanup on real exit.
    return () => {
      gw.off('event', handler)
      gw.off('exit', exitHandler)
    }
  }, [gw, sys])
```

两个依赖都恒定,所以这个 effect **整个进程生命周期只跑一次**:

- `gw` 是**模块级单例**,重启网关不换实例 ——

  `ui-tui/src/entry.tsx:51 @ 863e313`

  ```tsx
  const gw = new GatewayClient()
  ```

- `sys` 的依赖链一路 `useCallback` 到空依赖数组,恒定 ——

  `ui-tui/src/app/useMainApp.ts:444 @ 863e313`

  ```ts
  const sys = useCallback((text: string) => appendMessage({ role: 'system', text }), [appendMessage])
  ```

  `ui-tui/src/app/useMainApp.ts:439-442 @ 863e313`

  ```ts
  const appendMessage = useCallback(
    (msg: Msg) => setHistoryItems(prev => appendTranscriptMessage(prev, msg)),
    [setHistoryItems]
  )
  ```

  `ui-tui/src/app/useMainApp.ts:181-187 @ 863e313`

  ```ts
  const setHistoryItems = useCallback<StateSetter<Msg[]>>(value => {
    if (typeof value !== 'function') {
      setHistoryGeneration(generation => generation + 1)
    }

    setHistoryItemsState(previous => capTranscriptHistory(typeof value === 'function' ? value(previous) : value))
  }, [])
  ```

  **这一点值得单独说**:依赖若是不稳定的,这个缺陷会变成**偶发**的(有时 effect 重跑、
  顺手补上了订阅)。实际是全稳定的,所以它是**确定性**缺陷——每一次都发生。
  偶发本来会更难查,这里反而是"稳定"让它变成了必现。

#### (c) 负结论的搜索面

「没有第二个打开订阅的地方」「没有第二个 `drain()` 调用点」是全称否定,搜索面如下:

```verify
cd /home/user/hermes-agent && grep -rn "subscribed" ui-tui/src --include=*.ts --include=*.tsx | grep -v __tests__
```

```text
ui-tui/src/gatewayClient.ts:148:  private subscribed = false
ui-tui/src/gatewayClient.ts:170:    if (this.subscribed) {
ui-tui/src/gatewayClient.ts:221:    this.subscribed = false
ui-tui/src/gatewayClient.ts:261:    if (this.subscribed) {
ui-tui/src/gatewayClient.ts:620:    // `subscribed` until that microtask runs.
ui-tui/src/gatewayClient.ts:633:    // Crucially, `subscribed` stays false until the flush so any LIVE event
ui-tui/src/gatewayClient.ts:635:    // (publish() pushes when !subscribed) instead of emitting synchronously
ui-tui/src/gatewayClient.ts:637:    // flush re-drains the buffer right after flipping `subscribed`, so any
ui-tui/src/gatewayClient.ts:647:      this.subscribed = true
```

九处里四处是注释,赋值只有 `:148` 初始化、`:221` 关、`:647` 开三处。`drain()` 的调用点:

```verify
cd /home/user/hermes-agent && grep -rn "\.drain()" --include=*.ts --include=*.tsx . | grep -v node_modules | grep -v __tests__ | grep -v "\.test\."
```

```text
./ui-tui/src/app/useMainApp.ts:858:    gw.drain()
./ui-tui/src/gatewayClient.ts:651:      for (const ev of this.bufferedEvents.drain()) {
```

第二条是**缓冲区自己的** `drain()`,不是客户端的。**排除面**:`node_modules/`、
`__tests__/` 与 `*.test.*`(测试里 13 处 `drain()`,全部是 `start()` 在前、`drain()` 在后,
**没有一处是 `drain()` 之后再 `start()`** —— 这正是这个缺陷能活下来的原因)。

#### (d) 实测复现(本轮做的,移交项说做不到的那一步)

移交项写「需起真实网关复现」。**不需要**:`ui-tui/src/__tests__/gatewayClient.test.ts`
自带一个 `FakeWebSocket` 传输替身,照抄它的形状就能驱动整条路径。探针已落库:

```verify
cd /home/user/hermes-study && bash data/r10b/probes/run_h_r10f_probe.sh 2>&1 | grep -E "^H-R10-f|Tests  |Test Files"
```

```text
H-R10-f events seen after restart: ["before.restart"]
H-R10-f exit events after restart: []
 Test Files  1 passed (1)
      Tests  3 passed (3)
```

三个用例:**对照**(重启前事件正常到达)、**探针 1**(重启后 `after.restart` 事件
**收不到**)、**探针 2**(重启后网关再死一次,`exit` 事件**一条都收不到**)。
三个断言全部成立,即缺陷全部复现。

#### (e) 定级与后果

**立 ■-R10B-01。** 触发路径不是边角:`ui-tui/src/app/useMainApp.ts:846` 的 `gw.start()` 正是
**「gateway exited — recovering your session」那条恢复路径**。也就是说——
界面告诉用户"正在为你恢复会话",然后**从这一刻起再也收不到任何网关事件**,
并且**下一次网关死掉时连提示都不会有**(`pendingExit` 存下了,没人取)。

**可迁移形式**:`resetStartupState()` 把「传输层状态」和「消费者订阅状态」放在了同一个
复位函数里。传输层该复位,**订阅不该**——订阅是消费者的事实,传输换了它没变。
一个状态字段同时被两个生命周期共用,而只有一个生命周期有重建路径,另一个就是单向的。

*一处必须交代的限定*:本条全部证据来自**替身传输**下的复现与静态搜索面。
真实网关下的时序(例如重启后是否有别的路径意外触发 React 重挂载)**未验**。
但替身复现的是 `GatewayClient` 自身的状态机,而依赖恒定性是从源码直接读出来的,
两者都不依赖真实网关。

---

## 2. 明确不归本轮的(逐条核过,不是默认续转)

下面这些的去向列都不是 R10B。本轮**只核一件事:锚点在基线上还解析得到吗**
——移交项是下一轮直接拿来当起点用的东西,锚点漂了下一轮就直接找错地方。

| 移交项 | 去向 | 锚点复核 |
|---|---|---|
| H-R10-b | R11 复盘 | 指向 R10 报告 §8.1,非基线锚点,无需复核 |
| H-R10-c | R11 复盘 | 同上;**本轮为它补了一条同型证据**(见 §0.1),建议合并处置 |
| H-R10-d | R11A | `hermes_cli/web_server.py:5524`:`shell=True` —— 复核:解析得到,行号正确 |
| H-R8C-f(后端半边) | R11A | `hermes_cli/web_server.py:12892`:`@app.post("/api/ops/import")` —— 复核:解析得到,行号正确 |
| H-R9B-d | R11A | `gateway/relay/media.py:94` 的 `is_relay_media_url` —— 复核:解析得到,行号正确 |
| H-R8FIX-b + H-R8D-g | R11B | 指向 R10 报告 §4 的 314 处统计,非基线锚点 |
| 其余 21 条 OPEN | R11A / R11B / R11 复盘 / R12 前置 | 去向均非 R10B,本轮不处置 |

三条基线锚点的复核命令:

```verify
cd /home/user/hermes-agent && sed -n '5524p' hermes_cli/web_server.py; sed -n '12892p' hermes_cli/web_server.py; sed -n '94p' gateway/relay/media.py
```

```text
                    shell=True,
@app.post("/api/ops/import")
        return "/relay/media/" in (url or "")
```

**三条全部解析得到,但第三条要说清楚,我第一版把它说错了。**

前两条锚点落在它们各自点名的那一行,没有疑问。第三条 `gateway/relay/media.py:94`
落在的是 `is_relay_media_url` 的**函数体**(那句子串判断),`def` 在 `:92`:

`gateway/relay/media.py:92-94 @ 863e313`

```python
    def is_relay_media_url(self, url: str) -> bool:
        """Is ``url`` a connector re-host reference (needs our bearer to GET)?"""
        return "/relay/media/" in (url or "")
```

**这个锚点是对的**——H-R9B-d 说的缺陷正是那句 `in` 子串判断,锚到 `:94` 比锚到 `def` 更准。
错的是我的措辞:初稿写「行号正确」并配了一条 `sed -n '94p'`,读者照着跑会看到函数体而不是
我暗示的函数头,于是会以为锚点漂了。

*这条是被本轮新加的 `scripts/verify_evidence_commands.py` 抓出来的,不是我自己发现的。*
**而它能骗过引用校验器是有原因的**:表格锚点判 TABLE-OK 有两条路径,其中第二条是
「摘录正好是锚点所在函数/类的头行」。这一格写的是 `` `gateway/relay/media.py:94` 的 `is_relay_media_url` ``,
`is_relay_media_url` 确实在 `:92` 的头行上,于是走第二条路径判 OK。
**关卡是对的,我的散文是错的**——关卡从没声称 `:94` 那一行写着函数名。

## 3. 本轮新提的移交项

见 `reports/round-10b-*.md` 的移交清单节,每条带声明式锚点。
