# r7b-10 · `gateway/platforms/base.py` —— 适配器基类契约

> 底稿。基线 `863e31318553cda8ad61df681d08175364d4164b`;断言均带 `路径:行号 @ 863e313` + 原文块。
> 覆盖 base.py 的「契约面」:能力位、钩子安装点、抽象方法、渲染钩子、致命错误状态机、平台锁。
> 守卫见 `r7b-20-*`,媒体安全见 `r7b-30-*`。

## 0. 一句话

`BasePlatformAdapter` 是 24 个平台的**唯一收口**:它把"平台差异"压缩成一组**可询问的能力位**
和**可覆盖的渲染钩子**,把"并发、重试、媒体、脱敏"这些**每个平台都要做对的事**做成基类默认实现。

## 1. 能力位:平台差异的"可询问化"

网关不认识 Telegram、Discord、Signal。它只问适配器四类问题。**默认值全部选"最保守"**,
所以一个新适配器什么都不覆盖也能跑,只是体验退化 —— 这是本簇最重要的设计取舍。

### 1.1 授权类:两个**语义不同**的位

`enforces_own_access_policy`(`gateway/platforms/base.py:2884-2909 @ 863e313`)默认 `False`:

```python
    def enforces_own_access_policy(self) -> bool:
        """Whether this adapter gates inbound access before dispatch.

        Some adapters (WeCom, Weixin, Yuanbao, QQBot, WhatsApp) implement a
        documented config-driven access surface — ``dm_policy`` / ``group_policy`` /
        ``allow_from`` / ``group_allow_from`` in ``PlatformConfig.extra`` — and
        enforce it at intake: a message is dropped inside the adapter and never
        reaches the gateway unless it already passed that policy.
```

关键在于它**不等于"已授权"**,基类 docstring 自己把这条边界写死了:

```python
        flag alone is NOT "already authorized": these adapters default
        ``dm_policy`` / ``group_policy`` to ``"open"``, which forwards every
        sender, so the gateway trusts the adapter only when its effective policy
        for the chat type is an actual ``"allowlist"`` restriction — never for
        ``"open"`` (that would be the network-exposed fail-open SECURITY.md §2.6
        forbids).
```

`authorization_is_upstream`(`gateway/platforms/base.py:2911-2941 @ 863e313`)默认 `False`,
**全仓唯一使用者是 relay 适配器**:

```python
        This is NOT a fail-open: it is authorization DELEGATED to a trusted
        upstream that authenticated the transport (the relay WS secret) and
        enforced owner-only binding, as opposed to authorization being ABSENT.
        It only takes effect for an adapter that explicitly overrides this to
        ``True``; every network-exposed direct adapter leaves it ``False`` and
        the env-allowlist default-deny continues to apply unchanged.
```

**设计理由**:两者都是"网关不要重复判授权",但**信任来源不同** —— 一个是本地配置策略
(网关可以自己读到、可以复核),一个是远端可信上游(网关读不到,只能委托)。合并成一个
布尔位会让"委托"和"本地策略"共用一条 fail-open 路径。**取舍**:多一个概念,换来
"委托"永远只对显式覆盖的适配器生效。

### 1.2 流式类:三个位 + 一个方法

| 成员 | 默认 | 语义 | 溯源 |
|---|---|---|---|
| `supports_draft_streaming(chat_type, metadata)` | `False` | 平台是否有原生"草稿"流式(Telegram Bot API 9.5 `sendMessageDraft`) | `base.py:2943-2960` |
| `prefers_fresh_final_streaming(content, metadata)` | `False` | 终稿是否要**重发新消息 + 删预览**,而不是原地编辑 | `base.py:2962-2983` |
| `streaming_overflow_limit()` | `None` | 终稿可累积的更大上限(Telegram Rich Message 32,768 vs 编辑上限 4,096) | `base.py:2985-3000` |
| `send_draft(chat_id, draft_id, content, metadata)` | `raise NotImplementedError` | 草稿发送本体 | `base.py:3002-3042` |

三者共同解决一个问题:**"流式预览"和"终稿"在很多平台上不是同一种消息**。
`prefers_fresh_final_streaming` 的 docstring 把动机讲得很具体
(`gateway/platforms/base.py:2969-2977 @ 863e313`):

```python
        Some adapters can send richer final messages than their current edit
        implementation supports. Telegram is the motivating case: Hermes sends
        final replies through ``sendRichMessage`` but still finalizes streamed
        previews through its existing MarkdownV2 edit path until Bot API 10.1's
        ``rich_message`` edit parameter is wired directly.
```

**降级链是闭合的**:`send_draft` 默认抛 `NotImplementedError`,而消费端约定
"返回 False **或 `send_draft` 抛异常**都回落编辑路径"(`base.py:2956-2958 @ 863e313`):

```python
        Default implementation returns False.  Stream consumers fall back to
        the edit-based path (``send`` + ``edit_message``) when this returns
        False or when ``send_draft`` raises.
```

即:**能力位说谎也不会挂**,异常本身就是第二道降级信号。这是可迁移的设计原则。

### 1.3 长度类:平台的"一个字符"不一样

`message_len_fn` / `max_message_length_for_chat` / `message_len_fn_for_chat`
(`base.py:2851-2882 @ 863e313`)。根因是 Telegram 按 **UTF-16 码元**计长
(`gateway/platforms/base.py:190-202 @ 863e313`):

```python
def utf16_len(s: str) -> int:
    """Count UTF-16 code units in *s*.

    Telegram's message-length limit (4 096) is measured in UTF-16 code units,
    **not** Unicode code-points.  Characters outside the Basic Multilingual
    Plane (emoji like 😀, CJK Extension B, musical symbols, …) are encoded as
    surrogate pairs and therefore consume **two** UTF-16 code units each, even
    though Python's ``len()`` counts them as one.

    Ported from nearai/ironclaw#2304 which discovered the same discrepancy in
    Rust's ``chars().count()``.
    """
    return len(s.encode("utf-16-le")) // 2
```

一个满是 emoji 的回复,Python `len()` 说 4,000 合法,Telegram 说 8,000 超限 → 发送失败。
所以截断不能用 `s[:limit]`,必须二分找**不劈开代理对**的最长前缀
(`gateway/platforms/base.py:205-222 @ 863e313`):

```python
def _prefix_within_utf16_limit(s: str, limit: int) -> str:
    """Return the longest prefix of *s* whose UTF-16 length ≤ *limit*.

    Unlike a plain ``s[:limit]``, this respects surrogate-pair boundaries so
    we never slice a multi-code-unit character in half.
    """
```

并且泛化成"任意长度函数"的二分(`_custom_unit_to_cp`,`base.py:224-241 @ 863e313`),
供 `truncate_message` 使用。**可迁移原则**:长度是平台方言,把它抽成注入的 `len_fn`,
所有切分/截断只经由 `len_fn`,不要在业务代码里写 `len()`。

## 2. 渲染钩子:适配器可以"吃掉"事件

`render_message_event(event, sink)`(`gateway/platforms/base.py:3044-3063 @ 863e313`)
默认把结构化流事件映射回消费端原语:

```python
    def render_message_event(self, event: Any, sink: Any) -> None:
        """Render a MessageChunk / MessageStop / Commentary onto the sink.

        Default: map onto the stream consumer's existing primitives, preserving
        today's behavior 1:1.  ``sink`` is a GatewayStreamConsumer.
        """
        from gateway.stream_events import MessageChunk, MessageStop, Commentary

        if isinstance(event, MessageChunk):
            if event.text:
                sink.on_delta(event.text)
        elif isinstance(event, MessageStop):
            # An intermediate stop (text → tool → text) is a segment break;
            # the terminal stop is signalled by the gateway via finish(),
            # not here, so we only break segments on non-final stops.
            if not event.final:
                sink.on_segment_break()
        elif isinstance(event, Commentary):
            if event.text:
                sink.on_commentary(event.text)
```

其上方的块注释给出了这一族钩子的**宪法条款**
(`gateway/platforms/base.py:3030-3042 @ 863e313`):

```python
    # The contract is presentation-only: nothing rendered here is persisted to
    # conversation history.  History is owned by the agent; what an adapter
    # chooses to "eat" must never change the bytes the agent stored.
```

**这是本簇最值得抄走的一条**:允许适配器自由改写呈现(iMessage 可以吃掉它渲染不了的
工具链路 chrome),但**呈现层的自由不得回流到历史**。历史归 agent 所有。没有这条,
"哪个平台看到什么"就会污染"模型记得什么",同一会话跨平台恢复立刻错乱。

## 3. 钩子安装点:网关往适配器里塞什么

| 安装器 | 装什么 | 溯源 |
|---|---|---|
| `set_message_handler` | 主消息处理器(→ `GatewayRunner._handle_message`) | `base.py:3302-3309` |
| `set_topic_recovery_fn` | Telegram DM topic 的 `thread_id` 改写钩子 | `base.py:3311-3323` |
| `set_busy_session_handler` | **忙时策略机**(返回 True 表示已处理) | `base.py:3345-3347` |
| `set_reaction_handler` | 平台原生 emoji 反应事件 | `base.py:3349-3366` |
| `set_authorization_check` | 授权判定回调 | `base.py:3368-3380` |
| `set_session_store` | 会话存储(供历史媒体路径查询) | `base.py:3406-3414` |
| `set_fatal_error_handler` | 致命错误上报 | `base.py:3154-3155` |

**设计观察**:全部是**运行期注入**而非构造参数。理由在 `set_topic_recovery_fn` 的注释里
(`gateway/platforms/base.py:3321-3323 @ 863e313`):

```python
        # Guard against subclasses that initialize via ``object.__new__`` in
        # tests and never run ``BasePlatformAdapter.__init__``.
        self._topic_recovery_fn = fn  # type: ignore[attr-defined]
```

适配器可能被测试用 `object.__new__` 造出来(绕过 `__init__`),所以读取侧一律用
`getattr(self, "_x", None)` 而非直接属性访问。这是"测试可造性"反向约束生产代码的实例。

### 3.1 Telegram topic 适配(任务简报点名项)

改写逻辑(`gateway/platforms/base.py:3325-3344 @ 863e313`):

```python
    def _apply_topic_recovery(self, event: MessageEvent) -> None:
        """Rewrite ``event.source.thread_id`` in place if the hook returns one."""
        recover = getattr(self, "_topic_recovery_fn", None)
        if recover is None:
            return
        source = getattr(event, "source", None)
        if source is None:
            return
        try:
            recovered = recover(source)
        except Exception:
            logger.debug("topic recovery hook failed", exc_info=True)
            return
        if recovered is None or str(recovered) == str(source.thread_id or ""):
            return
        try:
            event.source = dataclasses.replace(source, thread_id=str(recovered))
        except Exception:
            logger.debug("topic recovery rewrite failed", exc_info=True)
```

三层"啥都不做"的短路(钩子未装 / 无 source / 返回值等于原值),加两层异常吞。
**为什么钩子失败要静默**:topic 恢复失败的后果是"会话键退回未恢复的 thread_id",
即回落到旧行为;而抛出会让整条消息丢失。**用可降级换可用性**。

门控在入口且**只对 Telegram DM 生效**(`gateway/platforms/base.py:5566-5576 @ 863e313`):

```python
        # Telegram topic recovery only applies to private DM topic lanes. Do
        # not submit a no-op check for group/forum/channel traffic to the
        # shared default executor: a busy pool would delay message dispatch.
        needs_topic_recovery = (
            getattr(self, "_topic_recovery_fn", None) is not None
            and event.source.platform == Platform.TELEGRAM
            and event.source.chat_type == "dm"
        )
        if needs_topic_recovery:
            await asyncio.to_thread(self._apply_topic_recovery, event)
```

**注意 `asyncio.to_thread`**:钩子是同步的(要查 SQLite),放进默认线程池。注释点明了
门控的真实理由不是正确性而是**性能** —— 一个满负荷的默认执行器会拖慢所有消息分发,
所以不给非 DM 流量提交空操作。这是"异步 harness 里同步钩子怎么接"的标准答案:
**丢线程池 + 前置门控,别让空操作占坑**。

三个安装点全在 run.py(R7 范围),插件侧只有一行调用
(`plugins/platforms/telegram/adapter.py:8909 @ 863e313`):`self._apply_topic_recovery(event)`。

## 4. 致命错误状态机与平台锁

### 4.1 致命错误

`has_fatal_error` / `fatal_error_message` / `fatal_error_code` / `fatal_error_retryable`
(`base.py:3124-3137 @ 863e313`),由 `_set_fatal_error(code, message, retryable)`
(`base.py:3170-3175`)置位,`_notify_fatal_error`(`base.py:3209-3215`)上报。
**`retryable` 是三元决策的关键**:网关据此决定"重连"还是"放弃这个平台"。

### 4.2 跨进程平台锁

`_acquire_platform_lock(scope, identity, resource_desc)`(`base.py:3217-3281 @ 863e313`)
解决的是:**同一个 bot token 被两个 Hermes 进程同时长轮询**,平台侧会互相抢 update,
表现为消息随机丢失。锁的 takeover 只在显式 `gateway run --replace` 首连时武装
(`gateway/platforms/base.py:2770-2774 @ 863e313`):

```python
        # Cross-HERMES_HOME token takeover is armed by GatewayRunner only for
        # an adapter's initial connect during an explicit ``gateway run
        # --replace`` startup.  Ordinary starts and every reconnect fail safe
        # through the existing retryable conflict path.
```

**取舍**:重连永远不抢锁。代价是"对端进程僵死时新进程连不上",收益是"网络抖动不会
让两个进程互相踢"。选择了**收敛而非可用**,对长轮询型平台是正确的。

## 5. 抽象方法与默认桩:两类"可选"

`connect` / `disconnect` / `send` 等以 `@abstractmethod` 声明(`base.py:3471-3600 @ 863e313`)。
但**交互式 UX 方法分成两类**,这是本轮一条重要定案的来源:

- **有基类实现、可覆盖**:`send_slash_confirm`(`base.py:3745-3778`)、
  `send_clarify`(`base.py:3780-3852`)—— 基类给纯文本兜底。
- **基类完全不存在、靠调用点探测**:`send_exec_approval` / `send_model_picker` /
  `send_choice_picker`。全仓 `def send_model_picker` 只出现在 3 个插件 + 3 个测试桩,
  base.py 中**没有任何定义**。降级发生在调用点,而且探测的是**类**不是实例:

```python
            and getattr(type(adapter), "send_choice_picker", None) is not None
```

(`gateway/slash_commands.py:3463 @ 863e313`;`send_model_picker` 同形,
`gateway/slash_commands.py:1779 @ 863e313`;`send_exec_approval` 在
`gateway/run.py:5181 @ 863e313`)

qqbot 适配器专门为这个契约留了注释(`gateway/platforms/qqbot/adapter.py:2693-2699 @ 863e313`)。

**为什么探测类而不是实例**:`getattr(instance, name)` 会命中实例属性(测试 mock、
运行期 monkeypatch),把"这个对象碰巧有个同名属性"误判成"这个平台支持按钮"。
探测 `type(adapter)` 只认真正定义在类上的方法。**可迁移原则**:能力探测走类型,不走实例。

## 6. 【文档-代码冲突候选】

**▲ B-1(R7 移交项定案)**:`website/docs/developer-guide/gateway-internals.md:86 @ 863e313`
描述第一层守卫:

> 1. **Level 1 — Base adapter** (`gateway/platforms/base.py`): Checks `_active_sessions`.
>    If the session is active, queues the message in `_pending_messages` **and sets an
>    interrupt event**. This catches messages *before* they reach the gateway runner.

**证伪后半句**。base.py 全文只有**一处** `.set()`,且不在 `handle_message` 里:

```
$ grep -n "\.set()" gateway/platforms/base.py
4813:                interrupt_event.set()
```

该处属于 `interrupt_session_activity`(`gateway/platforms/base.py:4808-4813 @ 863e313`):

```python
    async def interrupt_session_activity(self, session_key: str, chat_id: str, metadata=None) -> None:
        """Signal the active session loop to stop and clear typing immediately."""
        if session_key:
            interrupt_event = self._active_sessions.get(session_key)
            if interrupt_event is not None:
                interrupt_event.set()
```

而它的调用者全在**第二层**:`gateway/run.py:23127`、`gateway/run.py:23131`、
以及 relay 适配器的 `on_interrupt`(`gateway/relay/adapter.py:626 @ 863e313`)。
**结论**:置中断位是**第二层(runner)的动作**,由 runner 反向调进适配器;第一层从不置位。
文档把两层的动作合并叙述,读者会以为"消息进适配器就会打断当前回合" —— 恰恰相反,
第一层默认**不打断**,只入槽(见 `r7b-20`)。中文镜像同错
(`website/i18n/zh-Hans/.../gateway-internals.md:86 @ 863e313`:"将消息加入 `_pending_messages`
队列并设置中断事件")。

**▲ B-2**:同文件 `gateway-internals.md:59-61 @ 863e313`:

> 2. **Base adapter** checks active session guard:
>    - If `/approve`, `/deny`, `/stop` → bypass guard (dispatched inline)

`/approve` `/deny` 确是 inline 直分发,但 `/stop` **不是**同一条路 —— 它属
`interrupt_then_dispatch`,走的是专门序列化"取消 + 应答 + 排水"的
`_dispatch_active_session_command`(`gateway/platforms/base.py:5611-5619 @ 863e313`):

```python
                if cmd and is_interrupt_then_dispatch(cmd):
                    self._discard_text_debounce(session_key)
                    try:
                        await self._dispatch_active_session_command(event, session_key, cmd)
```

代码注释明确禁止把它们混为一谈(`gateway/platforms/base.py:5605-5610 @ 863e313`):
"`/stop`, `/new`, `/reset` must cancel the in-flight adapter task and preserve ordering of
queued follow-ups. Route those through the dedicated handoff path"。

**▲ B-3**:`gateway/platforms/ADDING_A_PLATFORM.md:135 @ 863e313` 与 `:66-70`:

> See `gateway/platforms/telegram.py`, `discord.py`, and `whatsapp_cloud.py` for reference
> implementations.
> WhatsApp does this: `gateway/platforms/whatsapp.py` (Baileys bridge) and
> `gateway/platforms/whatsapp_cloud.py` (Meta Cloud API) both inherit from ...

三个被点名的文件里**两个不存在**:

```
$ for f in gateway/platforms/telegram.py gateway/platforms/discord.py gateway/platforms/whatsapp.py; do
    [ -f "$f" ] && echo "EXISTS: $f" || echo "MISSING: $f"; done
MISSING: gateway/platforms/telegram.py
MISSING: gateway/platforms/discord.py
MISSING: gateway/platforms/whatsapp.py
```

telegram / discord 已迁到 `plugins/platforms/*/adapter.py`;Baileys 版 WhatsApp 在
`plugins/platforms/whatsapp/adapter.py:381 @ 863e313`(确实继承 `WhatsAppBehaviorMixin`,
所以**结论对、路径错**)。同文档 §16 的验证 grep 也只扫 `gateway/`,扫不到插件目录。

**▲ B-4**:`gateway/platforms/ADDING_A_PLATFORM.md:105-113 @ 863e313` 标题为
"### Optional methods (**have default stubs in base**)",紧随的"Interactive UX"表格
(`:115-122`)列入 `send_exec_approval` / `send_model_picker` / `send_choice_picker`,
并称 "They all degrade gracefully to plain text when not overridden"。

**基类里这三个方法根本不存在**:

```
$ grep -n "def send_exec_approval\|def send_model_picker\|def send_choice_picker" gateway/platforms/base.py
(无输出)
```

优雅降级是真的,但**实现位置在调用点的类型探测**(见 §5),不是基类桩。差别不是学术性的:
按文档理解去写适配器的人会以为"不覆盖 = 继承一个文本兜底",于是不明白为什么
`super().send_exec_approval(...)` 报 `AttributeError`。

**◇ B-5**:`render_message_event` 的"呈现层不得回流历史"宪法条款
(`gateway/platforms/base.py:3040-3042 @ 863e313`)在 `website/docs/**` 与 `AGENTS.md`
中无任何对应描述 —— 这是跨平台一致性的关键不变量,只活在代码注释里。

**◇ B-6**:能力探测走 `type(adapter)` 而非实例(§5)是全仓一致的约定
(`gateway/slash_commands.py:1779`、`:3463`、`gateway/run.py:5181`、
`gateway/run.py:23113-23114` 均同形),但没有任何文档陈述这条约定。

## 7. 【bug 候选】

无(本段范围内)。`_apply_topic_recovery` 的双层 `except Exception` 静默是**有意**的
降级(见 §3.1),不计入。

## 8. 【重实现要点】

1. **能力位默认全保守**,新适配器零覆盖即可跑通;每个能力位都要有"说谎也不挂"的第二道
   降级(返回 False **或**抛异常都回落)。
2. **长度是平台方言**:抽成注入的 `len_fn`,截断走二分找边界,禁止业务代码直接 `len()`/切片。
3. **呈现与历史彻底分离**:适配器可任意改写呈现,但不得改变 agent 存下的字节。
4. **能力探测走类型不走实例**,否则 mock 与 monkeypatch 会污染能力判断。
5. **钩子运行期注入 + `getattr` 读取**,让适配器可以被 `object.__new__` 造出来测试。
6. **同步钩子丢线程池 + 前置门控**,不给不相关流量提交空操作。
7. **区分"本地策略已判"与"可信上游已判"**:两者都免除网关复判,但信任来源不同,
   不可共用一个布尔位。
