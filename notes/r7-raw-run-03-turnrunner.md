# r7 底稿 · gateway/run.py 03 —— class TurnRunner 全体(3670-5759)

> 溯源约定:`路径:行号 @ 863e313`,代码原文逐字摘录(每处 ≤25 行)。
> 本段 = `TurnRunner` 类全体:GatewayRunner 每回合(turn)的执行协作者,承载原先内嵌在
> `GatewayRunner._run_agent_inner` 里的 6 个巨型闭包(progress_callback / send_progress_messages /
> voice_ack_callback / _step_callback_sync(+event/status)/ run_sync)。
> 缝合层(seam)是 `gateway/turn_context.py` 的 `TurnContext` dataclass。

---

## 类头与 TurnContext seam(3670-3685)

### 机制:闭包 → 类方法的"零语义漂移"提取缝

**解决什么问题**:`_run_agent_inner` 历史上把 ~250 行的 `progress_callback`、~353 行的
`send_progress_messages` 等写成嵌套闭包,闭包捕获了 ~20 个外层局部变量,函数体膨胀到无法维护。
直接搬成方法会改变捕获语义(closure cell 共享可变状态)。作者的做法:把每个被捕获的局部变量
变成 `TurnContext` 的一个字段,方法体"逐字节等价"迁移,只做 `name -> ctx.name` 与
`self -> self._runner` 的机械替换。

gateway/run.py:3670-3684 @ 863e313:

```python
class TurnRunner:
    """Per-turn collaborator carrying the tool-progress callbacks that used to
    be nested closures inside ``GatewayRunner._run_agent_inner``.

    The bodies are byte-identical to the original closures modulo
    ``local_name`` -> ``ctx.field`` rewrites (closed-over locals now travel on
    the shared :class:`gateway.turn_context.TurnContext`) and ``self`` ->
    ``self._runner`` (the owning :class:`GatewayRunner`). Module-global
    references (logger, cfg_get, BasePlatformAdapter, ...) resolve in this
    same module exactly as before.
    """

    def __init__(self, runner: "GatewayRunner", ctx: TurnContext) -> None:
        self._runner = runner
        self._ctx = ctx
```

**seam 的关键规则**(gateway/turn_context.py:13-26 @ 863e313):

```python
- All fields are written once by ``_run_agent_inner`` while wiring up the turn
  (a few — ``_progress_metadata``, ``_progress_reply_to``, ``agent_holder`` —
  are computed slightly later than construction and assigned onto the ctx as
  soon as the original locals were bound).  None of the original closures
  *rebound* their captured names (no ``nonlocal``); mutable state uses the
  same single-element-list containers as before (``last_progress_msg``,
  ``repeat_count``, ...), so mutation stays visible to the outer body through
  the shared objects exactly as it did through the shared closure cells.
- ``_run_still_current`` stays a callable (it captures ``self``/
  ``session_key``/``run_generation``); carrying the callable keeps the
  extracted bodies byte-identical.
```

即:**不可变捕获 → 普通字段;可变捕获 → 保留单元素 list 容器**(`last_tool=[None]` 等,
共享引用即共享可见性);**唯一的 `nonlocal` 例外是 `message`**,提取后改为写 `ctx.message`
(turn_context.py:68-79 @ 863e313 第二波说明)。

**与 GatewayRunner 的协作契约(谁调它)**:全部接线在 `_run_agent_inner` 中完成:

- 构造:gateway/run.py:24523-24566 @ 863e313 —— `turn_ctx = TurnContext(...)`,
  `turn_runner = TurnRunner(self, turn_ctx)`;
- 回调回填到 ctx(供 run_sync 通过 ctx 读取,保持原闭包互相引用的形状):
  gateway/run.py:24569-24570、24745、24750、24790 @ 863e313:

```python
        turn_ctx.progress_callback = turn_runner.progress_callback
        turn_ctx.voice_ack_callback = turn_runner.voice_ack_callback
        ...
        turn_ctx._step_callback_sync = turn_runner._step_callback_sync
        ...
        turn_ctx._event_callback_sync = turn_runner._event_callback_sync
        ...
        turn_ctx._status_callback_sync = turn_runner._status_callback_sync
```

- 晚绑定字段按"原始绑定点"回填:`turn_ctx._progress_metadata/_progress_reply_to`
  (run.py:24717-24718)、`turn_ctx.agent_holder/result_holder/tools_holder/
  stream_consumer_holder/streaming_tts_consumer_holder`(run.py:24722-24735)、
  `_loop_for_step/_hooks_ref`(run.py:24743-24744)、状态三件套(run.py:24787-24789);
- 消费:`send_progress_messages` 作为后台任务启动(run.py:24843
  `progress_task = asyncio.create_task(send_progress_messages())`),`run_sync` 进
  executor 线程池(run.py:25151-25191,包一层 `_run_sync_with_timeout_lifecycle` 做
  watchdog 收尾);回合结束 `progress_task.cancel()`(run.py:25782)。

**为什么这么设计 / 取舍**:重构目标是"可评审性"——bodies 不变、只搬运,评审只需核对字段清单;
代价是 `TurnContext` 成为一个 40+ 字段的"扁平大包"(无内聚分组),且保留了单元素 list 这种
闭包时代的怪味道(本可用普通属性),换来的是与 git 历史逐字节可对照。

**重实现要点**:
1. 拆巨型闭包时先建"捕获变量清单 → dataclass 字段"映射,不可变直传、可变用共享容器;
2. 被 `nonlocal` 重绑定的变量必须显式改为 ctx 字段读写,并在两侧注释标明;
3. 回调之间互相引用时,把 bound method 回填到 ctx,而不是让方法直接互调,保持原引用拓扑;
4. `_run_still_current` 这类捕获闭包保留为 callable 字段,避免把 runner 内部状态泄进 seam。

---

## progress_callback(3686-3945)

**总述**:agent 在工具生命周期事件时调用的同步回调(在 agent 的 sync worker 线程上执行!),
签名 `(event_type, tool_name=None, preview=None, args=None, **kwargs)`。它不直接发消息,而是
把渲染好的文本放进线程安全的 `ctx.progress_queue`(`queue.Queue`,run.py:24463),由事件循环上
的 `send_progress_messages` 后台任务消费。**生产者-消费者分离是整个进度气泡机制的骨架**:
回调在工具线程上必须零阻塞、零事件循环依赖。

**Agent 侧调用点(它被谁调)**:
- `tool.started`:agent/tool_executor.py:708-710 @ 863e313
  `agent.tool_progress_callback("tool.started", function_name, preview, display_args)`;
- `tool.completed`:agent/tool_executor.py:1509-1513 @ 863e313(带 `duration=`、`is_error=`、`result=` kwargs);
- `tool.output_risk`:agent/tool_executor.py:1547-1554 @ 863e313(本回调静默忽略,见下);
- `_thinking` 两种形状:agent/conversation_loop.py:5785 与 5790 @ 863e313(见"思考中转"机制);
- codex runtime 把 `item/started|completed` 映射为同名事件(agent/codex_runtime.py:286、439-441 @ 863e313)。

### 机制 1:live status 行(Slack assistant 状态,3689-3714)

**解决什么问题**:Slack 默认关闭 tool_progress(永久消息刷屏),但 Slack Assistant API 有一条
"ephemeral 状态行"(is thinking...),可以零成本展示当前工具短语。该机制独立于进度气泡:
回调只把短语写到 adapter 上的 dict,真正渲染搭 `_keep_typing` 的顺风车(几秒内刷新),
零额外平台 API 调用(外层注释 run.py:24418-24424 @ 863e313)。

gateway/run.py:3696-3712 @ 863e313:

```python
        if (
            ctx._live_status_adapter is not None
            and ctx._live_status_mode != "off"
            and tool_name != "_thinking"
        ):
            try:
                if event_type == "tool.started" and tool_name and ctx._run_still_current():
                    from agent.display import build_status_phrase
                    _phrase = build_status_phrase(
                        tool_name,
                        args if ctx._live_status_mode == "full" else None,
                    )
                    ctx._live_status_adapter.set_status_text(ctx.source.chat_id, _phrase)
                elif event_type == "tool.completed":
                    # Between tools the model is genuinely "thinking"
                    # again — revert to the static default.
                    ctx._live_status_adapter.set_status_text(ctx.source.chat_id, None)
```

- `build_status_phrase`:agent/display.py:687 @ 863e313;`set_status_text`:
  gateway/platforms/base.py:2658 @ 863e313(能力探测在 run.py:24428-24430,
  `supports_status_text` 为假则 adapter 置 None)。
- `live_status` 模式解析:run.py:24425-24427(默认 `"full"`;`"full"` 才把 args 传给短语构造)。
- 注释自述"Plain dict write — safe from the agent's sync worker thread"(3693-3695):
  这是它放在**所有其他 gate 之前**的原因——它不依赖 progress_queue 是否存在。
- 工具结束时清空状态(置 None)= 回到"thinking"默认文案,语义上准确。

**取舍**:牺牲了状态行的即时性(最多等一个 typing 刷新周期),换取工具线程零事件循环交互。

### 机制 2:log 模式旁路(3715-3726)

**解决什么问题**:#3459/#3458——用户想要工具审计但不想在聊天里看到任何进度。
`display.tool_progress: log` 把 tool.started 行写入 `~/.hermes/logs/tool_calls.log`
而聊天保持安静(外层 run.py:24433-24436 @ 863e313 创建 `log_queue`)。

gateway/run.py:3718-3726 @ 863e313:

```python
        if ctx.log_queue is not None:
            if event_type == "tool.started" and tool_name and tool_name != "_thinking":
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                preview_str = f' "{preview}"' if preview else ""
                ctx.log_queue.put(f"{ts}  {tool_name}:{preview_str}".rstrip())
            if not ctx.progress_queue:
                return
        if not ctx.progress_queue or not ctx._run_still_current():
            return
```

- 消费者是外层的 `write_tool_log` 协程(run.py:24659-24712 @ 863e313):RotatingFileHandler
  (5MB×3)+ `RedactingFormatter`(agent/redact.py)保证密钥不落盘;由 run.py:24848 启动。
- 注意双 gate 顺序:log 队列处理在 progress_queue guard **之前**,因为 log 模式下
  progress_queue 根本不存在(`needs_progress_queue` 为假);log+progress 并存时两边都走。
- 3725 行的 `_run_still_current()`:陈旧 run(被 /stop、/new 顶替)不再入队。
  `_run_still_current` 定义在外层(run.py:24310-24313 @ 863e313):
  `run_generation` 与 `session_key` 比对 `_is_session_run_current`。

### 机制 3:长工具首触 onboarding 提示(3728-3755)

**解决什么问题**:用户第一次遇到 >30s 的长工具时,不知道有 `/verbose` 可看详情。
一次性(跨会话持久化 seen 标记)在进度流里塞一条提示。

gateway/run.py:3734-3752 @ 863e313(节选 ≤25 行):

```python
        if event_type == "tool.completed" and not ctx.long_tool_hint_fired[0]:
            try:
                duration = kwargs.get("duration") or 0
                if duration >= ctx._LONG_TOOL_THRESHOLD_S and ctx.progress_mode == "all":
                    from agent.onboarding import (
                        TOOL_PROGRESS_FLAG,
                        is_seen,
                        mark_seen,
                        tool_progress_hint_gateway,
                    )
                    _cfg = _load_gateway_config()
                    gate_on = is_truthy_value(
                        cfg_get(_cfg, "display", "tool_progress_command"),
                        default=False,
                    )
                    if gate_on and not is_seen(_cfg, TOOL_PROGRESS_FLAG):
                        ctx.long_tool_hint_fired[0] = True
                        ctx.progress_queue.put(tool_progress_hint_gateway())
                        mark_seen(_hermes_home / "config.yaml", TOOL_PROGRESS_FLAG)
            except Exception as _hint_err:
                logger.debug("tool-progress onboarding hint failed: %s", _hint_err)
            return
```

- 四重 gate:`tool.completed` + 每 run 一次锁(`long_tool_hint_fired[0]`,外层 run.py:24520)
  + 时长 ≥30s(`_LONG_TOOL_THRESHOLD_S`,run.py:24521)+ `progress_mode == "all"`(已在流式
  展示每个工具的用户才需要 /verbose)+ 平台 gate(`display.tool_progress_command` 必须开,
  否则 /verbose 根本不可用)+ 持久 seen 标记(写 config.yaml)。
- 注释"the CLI has its own trigger"(3733):CLI 侧另有触发器,gateway 不越权。
- **注意 3755 的 `return` 缩进在 if 块内**:`tool.completed` 且 hint 已 fired 时不在此返回,
  而是落到 3777 的 `event_type not in {"tool.started",}` 过滤——殊途同归,都不渲染。

### 机制 4:_thinking 思考文本中转(3757-3769)

**解决什么问题**:助手在工具调用之间的 scratch 文本(REASONING_SCRATCHPAD 剥离后)不是工具进度,
默认不该出现在聊天;只有平台显式开 `thinking_progress` 才转发。且要兼容**两种历史回调形状**。

gateway/run.py:3762-3769 @ 863e313:

```python
        if event_type == "_thinking" or tool_name == "_thinking":
            if not ctx._thinking_enabled:
                return
            thinking_text = preview if tool_name == "_thinking" else tool_name
            msg = f"💬 {thinking_text}" if thinking_text else None
            if msg:
                ctx.progress_queue.put(msg)
            return
```

两种形状的生产端(agent/conversation_loop.py:5783-5790 @ 863e313):

```python
                if first_line and getattr(agent, '_delegate_depth', 0) > 0:
                    try:
                        agent.tool_progress_callback("_thinking", first_line)
                    except Exception:
                        pass
                elif _think_text:
                    try:
                        agent.tool_progress_callback("reasoning.available", "_thinking", _think_text[:500], None)
                    except Exception:
                        pass
```

- 形状 A(子代理场景):`event_type="_thinking"`,`tool_name` 是文本本身 → 取 `tool_name`;
- 形状 B(结构化事件):`tool_name="_thinking"`,`preview` 是文本 → 取 `preview`。
- `_thinking_enabled` 来自外层 `_display_surface_mode("thinking_progress", default=False,
  require_platform_override_for={Platform.MATTERMOST})`(run.py:24453-24458 @ 863e313):
  Mattermost 必须逐平台显式 opt-in,防全局配置把 scratch 文本漏进公共 thread。
- 机制 1 的 gate `tool_name != "_thinking"` 挡的是形状 B;形状 A 的 event_type 不是
  started/completed,自然穿过 live-status 分支不产生副作用。

### 机制 5:进度气泡准入过滤(3771-3805)

三连 gate,顺序即语义:

1. `tool_progress_enabled` 关 → 只有 _thinking(上面已处理)能过,普通工具全压制
   (run.py:3773-3774);该开关 = `progress_mode not in {"off","log"}` 且非 WEBHOOK
   (run.py:24417 @ 863e313,webhook 不能编辑消息,逐条发会刷屏)。
2. 只处理 `tool.started`(run.py:3777-3778,`event_type not in {"tool.started",}` return)
   ——`tool.completed`(hint 已处理)、`reasoning.available`、`tool.output_risk` 全部丢弃。
3. clarify 工具永不渲染进度气泡(#52374):

gateway/run.py:3780-3789 @ 863e313:

```python
        # Never render a progress bubble for the clarify tool.  The
        # adapter's send_clarify IS the user-facing rendering (interactive
        # buttons or the numbered-text fallback), so a progress bubble is
        # pure duplication — and in verbose mode it dumps the raw
        # tool-call args JSON ({"question": ..., "choices": [...]}) into
        # the chat.  Because the progress queue drains on a background
        # task, that raw JSON typically lands right underneath the
        # rendered prompt (#52374).
        if tool_name == "clarify":
            return
```

4. `stop` 后压制(并行工具竞态):

gateway/run.py:3791-3805 @ 863e313:

```python
        # Suppress tool-progress bubbles once the user has sent `stop`.
        # When the LLM response carries N parallel tool calls, the agent
        # fires N "tool.started" events back-to-back before checking for
        # interrupts — without this guard, a late `stop` still renders
        # all N as 🔍 bubbles, making the interrupt feel ignored.
        # (agent lives in run_sync's scope; agent_holder[0] is the shared
        # handle across nested scopes — see line ~9607.)
        try:
            _agent_for_interrupt = ctx.agent_holder[0] if ctx.agent_holder else None
            if _agent_for_interrupt is not None and getattr(
                _agent_for_interrupt, "is_interrupted", False
            ):
                return
        except Exception:
            pass
```

**问题成因**:一条 LLM 响应带 N 个并行 tool_calls 时,agent 会背靠背发 N 个 tool.started
再检查中断;迟到的 stop 会让 N 个气泡照样弹出,"中断像被无视了"。生产端(progress_callback)
和消费端(send_progress_messages 4130-4138)**双侧**都查 `is_interrupted`,覆盖
"事件已入队但还没渲染"的窗口。

> ▲ 文档-代码冲突候选 1:3797 注释 "see line ~9607" 已失效——本基线 run.py:9607 位于
> `_cleanup_agent_resources_off_loop`(9596-9619)内部,与 agent_holder 无关;
> 真正的共享 handle 接线在 run.py:24722-24723(`agent_holder = [None]` /
> `turn_ctx.agent_holder = agent_holder`)。闭包提取时行号漂移,注释未更新。

### 机制 6:消息构造 —— new 去重、terminal 代码块、verbose、友好标签(3807-3931)

**"new" 模式**(只报工具切换,gateway/run.py:3808-3810):

```python
        if ctx.progress_mode == "new" and tool_name == ctx.last_tool[0]:
            return
        ctx.last_tool[0] = tool_name
```

**terminal 命令的 fenced code block**(#42634,markdown 平台专属):

gateway/run.py:3835-3861 @ 863e313(节选):

```python
        if (
            getattr(_progress_adapter, "supports_code_blocks", False)
            and tool_name == "terminal"
            and isinstance(args, dict)
            and isinstance(args.get("command"), str)
            and args["command"].strip()
        ):
            from agent.display import get_tool_preview_max_len
            _cmd_full = args["command"].rstrip()
            # Consecutive terminal calls: drop the repeated
            # "💻 terminal" header so back-to-back commands render as
            # adjacent code blocks under a single header.
            _block_header = (
                "" if ctx.last_was_terminal_block[0] else f"{emoji} {tool_name}\n"
            )
            _code_block_full = f"{_block_header}```\n{_cmd_full}\n```"
            # Single-line, capped preview for non-verbose modes.
            _pl = get_tool_preview_max_len()
            _cap = _pl if _pl > 0 else 40
            _lines = _cmd_full.splitlines()
            _cmd_short = _lines[0] if _lines else _cmd_full
            _multiline = len(_lines) > 1
            if len(_cmd_short) > _cap:
                _cmd_short = _cmd_short[:_cap - 3] + "..."
            elif _multiline:
                _cmd_short = _cmd_short + " ..."
            _code_block_short = f"{_block_header}```\n{_cmd_short}\n```"
```

设计细节(注释 3816-3828):
- 不写语言标签(```` ```bash ````):Slack mrkdwn 会把标签渲染成字面第一行 "bash";裸围栏到处兼容;
- 连续 terminal 调用去掉重复的 "💻 terminal" 头(`last_was_terminal_block[0]` 共享容器,
  外层 run.py:24470),背靠背命令渲染成同一 header 下的相邻代码块;
- verbose 显示完整命令,"all"/"new" 截成单行 ≤`tool_preview_length`(默认 40)——注释点名
  与非 terminal 预览路径共用同一预算(#42634:长/多行命令曾渲染成巨型块)。

**verbose 模式**(run.py:3864-3885):`{emoji} {tool}({arg键列表})\n{args JSON}`;
`tool_preview_length` 为 0(默认)时**不截断**——"用户显式要了全量,平台长度上限兜底"
(3874-3877 注释)。

**"all"/"new" 的友好标签**(gateway/run.py:3905-3927 @ 863e313,节选):

```python
            _prepared_preview = prepare_tool_preview(
                tool_name,
                args,
                fallback=preview,
                max_len=_cap,
            )
            if _progress_adapter is not None:
                preview = _progress_adapter.format_tool_preview(_prepared_preview)
            else:
                preview = _prepared_preview.text
...
            _verb = get_tool_verb(tool_name)
            if _verb:
                if verb_drops_preview(tool_name):
                    msg = f"{emoji} {_verb}"
                else:
                    msg = f"{emoji} {_verb}{tool_verb_connector(tool_name)}{preview}"
            else:
                msg = f"{emoji} {tool_name}: \"{preview}\""
```

- 依赖 agent/display.py 的 5 个函数:`get_tool_emoji`(:148)、`get_tool_preview_max_len`(:122)、
  `prepare_tool_preview`(:569)、`get_tool_verb`(:664)、`tool_verb_connector`(:677)、
  `verb_drops_preview`(:682)@ 863e313。内置工具有动词("🔍 Searching the web for ...");
  自定义/插件/MCP 工具无动词,回落 `tool_name: "preview"` 原始形。
- `_progress_adapter.format_tool_preview`:平台可按自身 markdown 方言格式化预览。

### 机制 7:重复折叠(dedup,3933-3945)

**解决什么问题**:execute_code 类工具模型常带同样 boilerplate 反复迭代 → 预览完全相同,
逐条渲染是噪音。折叠成"最后一行 + (×N)"。

gateway/run.py:3936-3945 @ 863e313:

```python
        if msg == ctx.last_progress_msg[0]:
            ctx.repeat_count[0] += 1
            # Update the last line in progress_lines with a counter
            # via a special "dedup" queue message.
            ctx.progress_queue.put(("__dedup__", msg, ctx.repeat_count[0]))
            return
        ctx.last_progress_msg[0] = msg
        ctx.repeat_count[0] = 0

        ctx.progress_queue.put(msg)
```

队列协议由此形成三种载荷:纯文本行、`("__dedup__", msg, count)`、`("__reset__",)`
(后者由 stream consumer 生产,见 send_progress_messages 机制 3)。

**progress_callback 重实现要点**:
1. 工具线程回调只做"渲染 + 入队",绝不碰事件循环;用线程安全队列 + 单消费者任务;
2. 事件形状会演化(位置参数复用/兼容),准入过滤要同时匹配 event_type 与 tool_name;
3. 有自渲染 UI 的工具(clarify/审批)必须在进度层显式豁免,否则 verbose 会把原始 JSON 泼进聊天;
4. 中断抑制要生产/消费双侧都做——并行 tool_calls 的事件在中断检查之前就批量发出;
5. dedup 用带外队列信号(元组标记)而不是让消费者猜,协议显式化;
6. 每类展示面(live status / log / 气泡 / thinking)独立 gate,先处理不依赖队列的面。

---

## send_progress_messages(3947-4300)

**总述**:事件循环上的异步消费者,把队列里的进度行聚合成**一条可编辑的气泡**(edit 而非刷屏),
处理平台长度上限、编辑节流、编辑失败降级、溢出滚动、与内容气泡的顺序线性化、取消时的收尾排空。
由 run.py:24843 `asyncio.create_task` 启动,run.py:25782 `progress_task.cancel()` 终止。

### 机制 1:入口 gate —— 不能编辑消息的平台整体禁用(3956-3969)

gateway/run.py:3956-3969 @ 863e313:

```python
        # Skip tool progress for platforms that don't support message
        # editing (e.g. iMessage/BlueBubbles) — each progress update
        # would become a separate message bubble, which is noisy.
        # getattr, not attribute access: duck-typed adapters (test fakes,
        # minimal plugin adapters) may not define edit_message at all —
        # "missing" means the same thing as "base no-op": can't edit.
        _adapter_edit = getattr(type(adapter), "edit_message", None)
        if _adapter_edit is None or _adapter_edit is BasePlatformAdapter.edit_message:
            while not ctx.progress_queue.empty():
                try:
                    ctx.progress_queue.get_nowait()
                except Exception:
                    break
            return
```

- 能力探测查**类**而非实例(`getattr(type(adapter), ...)`),且把"没定义"与"基类 no-op"等同
  ——这是本文件反复出现的 duck-typing 探测模式(同 run.py:24506-24513 的 delete_message、
  5181 的 send_exec_approval:查类避免 MagicMock 自动属性的假阳性)。
- 排空一次后直接 return:此后 progress_callback 仍会入队(它只看 `tool_progress_enabled`
  平台级开关,不看 adapter 能力),这些项无人消费,靠回合结束丢弃——有界但存在。
- 注意:`progress_grouping: "separate"`(不编辑、逐条发)也被这个 gate 挡住——
  "separate" 只是**选择不编辑**,平台**能不能**编辑仍是硬前提。

### 机制 2:限长与溢出滚动基础设施(3971-4110)

**局部状态**(3971-3975):`progress_lines`(当前可编辑气泡的行)、`progress_msg_id`、
`can_edit = ctx.progress_grouping != "separate"`(注释:separate = pre-v0.9 每工具一条)、
`_last_edit_ts` + `_PROGRESS_EDIT_INTERVAL = 1.5`(节流)。

**per-chat 长度上限**(3977-4002):adapter 可能是 relay(一个 adapter 前置 N 个平台),
上限与长度度量函数按 chat 解析:

gateway/run.py:3989-4002 @ 863e313:

```python
        if isinstance(adapter, BasePlatformAdapter):
            try:
                _raw_progress_limit = int(
                    adapter.max_message_length_for_chat(ctx.source.chat_id) or 4000
                )
                _progress_len_fn = adapter.message_len_fn_for_chat(ctx.source.chat_id)
            except Exception:
                pass
        # Leave a little room for platform quirks / formatting.  For tiny
        # test adapters keep the limit usable instead of clamping to 500+.
        _PROGRESS_TEXT_LIMIT = max(
            1,
            _raw_progress_limit - (64 if _raw_progress_limit > 128 else 0),
        )
```

> ▲ 文档-代码冲突候选 4:3997-3998 注释 "instead of clamping to 500+" 所指的 500 下限
> 在代码中不存在(现实现是 `max(1, raw - 64 if raw>128 else raw)`),疑为旧实现残留措辞。

**编辑保留 metadata 探测**(#27487,4004-4030):Telegram 话题(topic)路由信息在 metadata 里,
溢出后的 edit 若不带 metadata 会把消息编辑回 General 话题。用 `inspect.signature` 探测
adapter.edit_message 是否收 `metadata`(显式参数或 **kwargs):

gateway/run.py:4008-4018 @ 863e313:

```python
            try:
                _edit_params = inspect.signature(adapter.edit_message).parameters
                _edit_accepts_metadata = (
                    "metadata" in _edit_params
                    or any(
                        param.kind is inspect.Parameter.VAR_KEYWORD
                        for param in _edit_params.values()
                    )
                )
            except (TypeError, ValueError):
                _edit_accepts_metadata = False
```

`_edit_progress_message`(4020-4030)统一出口:附加 `finalize=True`
(`REQUIRES_EDIT_FINALIZE` 平台)与 metadata。

**分组切割 + 溢出滚动**:`_split_progress_groups`(4035-4048)按 `_progress_len_fn` 把行贪心
装进 ≤limit 的组;`_roll_progress_overflow_if_needed`(4068-4110)在当前气泡将超限时,
把第一组 edit 进旧气泡、其余组作为新消息发出,**只保留最后一组作为唯一可变气泡**:

gateway/run.py:4096-4110 @ 863e313:

```python
            else:
                result = await _send_progress_text(first_text)
                if result.success and result.message_id:
                    progress_msg_id = result.message_id

            for group in groups[1:]:
                result = await _send_progress_text(_progress_text(group))
                if result.success and result.message_id:
                    progress_msg_id = result.message_id

            # The newest continuation is now the only mutable bubble.  Keep
            # just its lines so subsequent edits update it instead of
            # replaying the full historical transcript into new messages.
            progress_lines = groups[-1]
            return True
```

失败分级(4084-4095):edit 失败且 `retryable` → 返回 True 保持缓冲与身份等下轮重试;
非 retryable → `can_edit = False` 回落逐条发送路径。
`_track_progress_result` / `_send_progress_text`(4050-4066):`cleanup_progress` 开启时
记录 message_id 进 `ctx._cleanup_msg_ids`,供回合结束批量删除临时气泡
(接线 run.py:24496-24517 @ 863e313,失败的 run 保留气泡当"面包屑")。

### 机制 3:主循环 —— 排空、静默、队列协议(4112-4169)

每轮:先查 `_run_still_current()`(陈旧 run 排空队列退出,4114-4120);`get_nowait` 取消息;
中断静默(4129-4138,同机制 5 的消费端半边:interrupt 后事件直接丢弃,唯一保留的进度类气泡
是单独发送的 "⚡ Interrupting current task");随后按协议分派:

gateway/run.py:4141-4162 @ 863e313(节选):

```python
                if isinstance(raw, tuple) and len(raw) == 3 and raw[0] == "__dedup__":
                    _, base_msg, count = raw
                    if progress_lines:
                        progress_lines[-1] = f"{base_msg} (×{count + 1})"
                    msg = progress_lines[-1] if progress_lines else base_msg
                elif isinstance(raw, tuple) and len(raw) >= 1 and raw[0] == "__reset__":
                    # Content bubble just landed on the platform — close off
                    # the current tool-progress bubble so the next tool
                    # starts a fresh bubble below the content. Without this,
                    # tool lines keep editing the ORIGINAL progress message
                    # above the new content, making the chat appear out of
                    # order. Mirrors GatewayStreamConsumer.on_segment_break
                    # on the content side. (Issue: tool + content
                    # linearization regression after PR #7885.)
                    progress_msg_id = None
                    progress_lines = []
                    ctx.last_progress_msg[0] = None
                    ctx.repeat_count[0] = 0
                    continue
                else:
                    msg = raw
                    progress_lines.append(msg)
```

**`__reset__` 与 streaming draft 的关系**(本段核心协作点):生产者是 stream consumer——
run_sync 里接线 `on_new_message=(lambda: ctx.progress_queue.put(("__reset__",)))`
(run.py:4516-4520,见 run_sync 机制 3);GatewayStreamConsumer 每当在平台上**新开一条内容
消息**(流式草稿气泡)就回调它(gateway/stream_consumer.py:526-533、2223 @ 863e313)。
效果:内容气泡落地 → 进度气泡"翻页"(丢弃 id、清空行、重置 dedup),下一个工具行在内容
**下方**开新气泡,聊天保持时间线性。反方向的镜像是内容侧的 `on_segment_break`
(stream_consumer.py:493-495)。这是修复 PR #7885 之后"工具+内容乱序回归"的机制。

溢出滚动优先(4164-4169):`_roll_progress_overflow_if_needed()` 为真 → 刷新节流钟、
sleep 0.3、恢复 typing、continue。

### 机制 4:编辑节流与失败分级(4171-4254)

**节流**(grammY 风格,主动限速而非被动吃 429):

gateway/run.py:4175-4182 @ 863e313:

```python
                _now = time.monotonic()
                _remaining = _PROGRESS_EDIT_INTERVAL - (_now - _last_edit_ts)
                if _remaining > 0:
                    # Wait out the throttle interval, then loop back to
                    # drain any additional queued messages before sending
                    # a single batched edit.
                    await asyncio.sleep(_remaining)
                    continue
```

**行为细节(重实现必知)**:被节流的行已 append 进 `progress_lines`,continue 后若队列已空
则落入 `except queue.Empty: sleep(0.3)` 循环——**该缓冲行不会被主动 flush**,要等下一条消息
到达(批量编辑)或任务取消(final drain 补一次 edit)。孤立的节流行会延迟到回合收尾才可见,
这是"合并编辑减 API 调用"的有意取舍。

**编辑失败三级分类**(4187-4225):

gateway/run.py:4190-4212 @ 863e313(节选):

```python
                    result = await _edit_progress_message(progress_msg_id, full_text)
                    if not result.success:
                        _err = (getattr(result, "error", "") or "").lower()
                        # Transient network errors (ConnectError, timeouts)
                        # must not permanently disable progress-message
                        # editing — the next cycle can catch up.  Only
                        # permanent failures (flood control, message not
                        # found, permissions) should set can_edit = False.
                        if getattr(result, "retryable", False):
                            logger.debug(
                                "[%s] Transient edit failure — keeping can_edit=True",
                                adapter.name,
                            )
                            continue
                        if "flood" in _err or "retry after" in _err:
                            # Flood control hit — backoff but keep editing.
...
                            logger.info(
                                "[%s] Progress edit flood control, backing off",
                                adapter.name,
                            )
                            _last_edit_ts = time.monotonic()
                        else:
                            can_edit = False
```

- retryable(网络瞬断)→ 什么都不动,下轮追平;
- flood("flood"/"retry after" 字符串匹配)→ 重置节流钟退避,**保持 can_edit**;
- 其余(消息不存在/权限)→ 永久降级 `can_edit = False`。
- flood/永久两支都会把当前行单独 send 一条兜底(4214-4225),并按 cleanup 记账;
  注意兜底 send 的 message_id **不**接管 progress_msg_id(编辑目标不变)。

首条消息 / 不可编辑分支(4226-4247):can_edit 且无 id → 全量发新消息并记 id;
不可编辑 → 只发当前行。每次成功发/编辑后 `sleep(0.3)` 并恢复 typing(4249-4254)
——发消息会打断平台的 typing 指示,这里补回去。

### 机制 5:CancelledError 收尾排空(4256-4300)

回合结束外层 `progress_task.cancel()`(run.py:25782)触发。取消处理**不是丢弃**而是
把队列剩余(最后一轮迭代的迟到工具行)完整落盘:

gateway/run.py:4258-4287 @ 863e313(节选):

```python
            except asyncio.CancelledError:
                # Drain remaining queued messages
                while not ctx.progress_queue.empty():
                    try:
                        raw = ctx.progress_queue.get_nowait()
                        if isinstance(raw, tuple) and len(raw) == 3 and raw[0] == "__dedup__":
                            _, base_msg, count = raw
                            if progress_lines:
                                progress_lines[-1] = f"{base_msg} (×{count + 1})"
                                await _roll_progress_overflow_if_needed()
                        elif isinstance(raw, tuple) and len(raw) >= 1 and raw[0] == "__reset__":
                            # Content-bubble marker during drain: close off
                            # the current progress bubble and start a fresh
                            # one for any tool lines that arrived after.
                            await _roll_progress_overflow_if_needed()
                            if can_edit and progress_lines and progress_msg_id:
                                _pending_text = _progress_text(progress_lines)
                                try:
                                    await _edit_progress_message(progress_msg_id, _pending_text)
                                except Exception:
                                    pass
                            progress_msg_id = None
                            progress_lines = []
```

随后(4288-4297)双重收尾:先 `_roll_progress_overflow_if_needed()` 处理超限,再对剩余行
做最终 edit(仅 can_edit 且有 id 时)。与主循环的 `__reset__` 不同,drain 中的 `__reset__`
会先把当前气泡的未落盘行 edit 出去再翻页——因为 drain 后没有"下一轮"了。
兜底 `except Exception`(4298-4300):log + sleep(1),循环永不因单次错误退出。

**send_progress_messages 重实现要点**:
1. "一条可编辑气泡 + 溢出滚动"优于逐条发送:平台限长按 per-chat 解析,贪心分组,滚动后只保留
   尾组为可变气泡,避免历史行重放;
2. 编辑失败必须三级分类(瞬态重试 / 限流退避 / 永久降级),字符串匹配限流是现实妥协;
3. 编辑节流合并批量更新,接受"孤立行延迟到收尾"的代价;取消路径必须完整 drain + final edit;
4. 与流式内容气泡的顺序问题用带外 `__reset__` 标记解决:内容新开消息 → 进度翻页,双向镜像
   (内容侧 on_segment_break / 进度侧 __reset__);
5. 能力探测查类不查实例,把"未定义"等同"基类 no-op";编辑是否收 metadata 用签名探测,
   否则 Telegram 话题路由在溢出 edit 时丢失(#27487);
6. 临时气泡清理(cleanup_progress)只记账成功 send 的 id,失败 run 保留气泡作诊断面包屑。

---

## voice_ack_callback(4302-4321)

### 机制:Discord 语音频道的一次性口头确认

**解决什么问题**:语音场景下工具调用开始后长时间无声,用户不知道 bot 在干活。
在**本回合第一个工具调用**时于语音频道播放一句短语("let me look into that"),
每回合至多一次,独立于文本进度 gate。

gateway/run.py:4302-4321 @ 863e313:

```python
    def voice_ack_callback(self, call_id, tool_name, args):
        """tool_start_callback: speak a one-time ack in the voice channel."""
        ctx = self._ctx
        if ctx._voice_ack_fired[0] or ctx._voice_ack_guild[0] is None:
            return
        if not ctx._run_still_current():
            return
        ctx._voice_ack_fired[0] = True
        _adapter = self._runner.adapters.get(Platform.DISCORD)
        if _adapter is None or not hasattr(_adapter, "play_ack_in_voice"):
            return
        try:
            safe_schedule_threadsafe(
                _adapter.play_ack_in_voice(ctx._voice_ack_guild[0]),
                ctx._voice_ack_loop,
                logger=logger,
                log_message="voice ack scheduling error",
            )
        except Exception as _ack_err:
            logger.debug("voice ack schedule failed: %s", _ack_err)
```

- 挂载点:`agent.tool_start_callback`(run_sync 4866-4868,仅 `_voice_ack_guild[0]` 非空时);
  agent 侧触发:agent/tool_executor.py:720-722 @ 863e313。
- 布防在外层(run.py:24472-24491 @ 863e313):仅 Discord 平台,遍历 adapter 的
  `_voice_text_channels` 找到与 `source.chat_id` 绑定且 `voice_mixer_active(gid)` 的 guild;
  `_voice_ack_loop = asyncio.get_running_loop()`(24491)在事件循环线程上提前捕获。
- `safe_schedule_threadsafe`(agent/async_utils.py:34 @ 863e313):sync 线程 → 指定 loop 的
  协程调度封装,本类所有 sync→async 桥的统一原语。
- 一次性锁 `_voice_ack_fired[0]` 在**调度前**置位:宁可失败也不重复出声。

**重实现要点**:
1. 语音确认与文本进度分离成独立回调,gate 独立(在语音频道 ≠ 开了 tool_progress);
2. 每回合一次的锁先置位再调度,幂等優先于可靠;
3. loop 引用必须在事件循环线程上提前捕获,工具线程不得 `get_event_loop()`。

---

## _step_callback_sync / _event_callback_sync(4323-4358)

### 机制:agent 迭代/生命周期事件 → 用户 hooks 的 sync→async 桥

`_step_callback_sync`:agent 每次 API 迭代前调用(agent/conversation_loop.py:1476 @ 863e313
`agent.step_callback(api_call_count, prev_tools)`),桥接到 `hooks.emit("agent:step", ...)`。

gateway/run.py:4327-4349 @ 863e313(节选):

```python
        # prev_tools may be list[str] or list[dict] with "name"/"result"
        # keys.  Normalise to keep "tool_names" backward-compatible for
        # user-authored hooks that do ', '.join(tool_names)'.
        _names: list[str] = []
        for _t in (prev_tools or []):
            if isinstance(_t, dict):
                _names.append(_t.get("name") or "")
            else:
                _names.append(str(_t))
        safe_schedule_threadsafe(
            ctx._hooks_ref.emit("agent:step", {
                "platform": ctx.source.platform.value if ctx.source.platform else "",
                "user_id": ctx.source.user_id,
                "session_id": ctx.session_id,
                "iteration": iteration,
                "tool_names": _names,
                "tools": prev_tools,
            }),
            ctx._loop_for_step,
            logger=logger,
            log_message="agent:step hook scheduling error",
        )
```

- 关键兼容层:`prev_tools` 的形状从 `list[str]` 演化为 `list[dict]`(带 name/result),
  但用户 hooks 里写死了 `', '.join(tool_names)`——所以归一化出 `tool_names`(纯字符串)
  与 `tools`(原始结构)两个字段并存。**事件负载是对外 API,升级要加字段不改字段**。
- 只在有 hooks 时挂载:run.py:4869 `agent.step_callback = ctx._step_callback_sync if
  ctx._hooks_ref.loaded_hooks else None`(零 hooks 时零开销)。

`_event_callback_sync`(4350-4358):通用生命周期事件直通 `hooks.emit(event_type, context)`,
用裸 `asyncio.run_coroutine_threadsafe` + debug 级吞错。agent 侧调用者:压缩后
`agent.event_callback("session:compress", ...)`(agent/conversation_compression.py:3479
@ 863e313)、codex runtime(agent/codex_runtime.py:253)。与 step 桥的差异:step 有
`_run_still_current` gate,event 桥**没有**——生命周期事件(如压缩完成)即使 run 已被顶替
也值得让 hooks 知道。

**重实现要点**:
1. hooks 负载做兼容性归一化(新旧形状并存字段),永不破坏用户脚本;
2. sync→async 桥统一走 `run_coroutine_threadsafe` 封装,吞错降级 debug 日志;
3. 是否 gate 在 `_run_still_current` 取决于事件语义:UI 类事件 gate,状态类事件不 gate。

---

## _status_callback_sync(4360-4394)

### 机制:agent 状态消息(上下文压力等)→ 平台状态气泡

agent 侧调用者:压缩生命周期消息 `agent.status_callback("lifecycle", msg)`
(agent/conversation_compression.py:1841 @ 863e313)、压实完成
`status_callback("compacted", COMPACTION_DONE_STATUS)`(同文件:110)等。

gateway/run.py:4360-4382 @ 863e313(节选):

```python
    def _status_callback_sync(self, event_type: str, message: str) -> None:
        ctx = self._ctx
        if not ctx._status_adapter or not ctx._run_still_current():
            return
        prepared_message = _prepare_gateway_status_message(
            ctx.source.platform,
            event_type,
            message,
        )
        if prepared_message is None:
            logger.debug(
                "status_callback suppressed for %s/%s: %s",
                ctx.source.platform.value if ctx.source.platform else "unknown",
                event_type,
                _redact_gateway_user_facing_secrets(str(message or ""))[:160],
            )
            return
        _fut = safe_schedule_threadsafe(
            _send_or_update_status_coro(ctx._status_adapter, ctx._status_chat_id, event_type, prepared_message, ctx._status_thread_metadata),
            ctx._loop_for_step,
            logger=logger,
            log_message=f"status_callback ({event_type}) scheduling error",
        )
```

- `_prepare_gateway_status_message`(run.py:725 @ 863e313):按平台/事件类型过滤+改写
  状态文案,返回 None = 压制(压制时日志里也要**先脱敏** `_redact_gateway_user_facing_secrets`
  再截 160 字符——连 debug 日志都不漏密钥);
- `_send_or_update_status_coro`(run.py:770 @ 863e313):同 event_type 的状态消息做
  send-or-update(编辑复用同一条气泡);
- 尾部(4385-4394):cleanup_progress 开启时通过 future 的 done_callback 把状态气泡
  message_id 记进 `_cleanup_msg_ids`——**跨线程记账用 add_done_callback,不阻塞工具线程**。
- 状态接线(`_status_adapter/_status_chat_id/_status_thread_metadata`)在外层
  run.py:24753-24789 @ 863e313 计算:Feishu 话题需要 `reply_to_message_id` 特例
  (Feishu 只在 reply API + reply_in_thread 时把消息留在话题内,24755-24763),
  relay Discord auto-thread 需要 prospective anchor(24776-24782)。

**重实现要点**:
1. 状态消息经过平台感知的准备层(可改写/压制),压制路径的日志也要脱敏;
2. 同类状态用 send-or-update 折叠为一条,不刷屏;
3. message_id 记账走 future 回调,保持发起线程零等待。

---

## run_sync 之一:开场与运行时解析(4396-4471)

### 机制:回合入口 —— session key 传播策略与模型/推理配置解析

`run_sync` 是**在 executor 线程池上跑的同步方法**(run.py:25189-25191 经
`_run_in_executor_with_context` 提交,contextvars 随之传播),是一回合的真正执行体。

开场注释解释两个历史决策:

1. `nonlocal message` 的去向(4398-4405):见类头机制,重绑定写 `ctx.message`。
2. **为什么不写 `os.environ["HERMES_SESSION_KEY"]`**(#24100):

gateway/run.py:4407-4420 @ 863e313(节选):

```python
        # session_key is propagated via contextvars in _set_session_env()
        # (_SESSION_KEY) and via set_current_session_key() (_approval_session_key)
        # below — both concurrency-safe and inherited by tool worker threads.
        # We deliberately do NOT write os.environ["HERMES_SESSION_KEY"] here:
        # os.environ is process-global, so concurrent gateway sessions (e.g.
        # two Discord threads) would clobber each other's value, and a tool
        # thread whose contextvar is unset would fall back to os.environ and
        # read the wrong session key — misrouting command-approval prompts to
        # the wrong thread (#24100). The non-gateway surfaces don't depend on
        # this write: CLI and cron bind the session via contextvars
        # (set_current_session_key / session context), and only the TUI
        # slash-worker *subprocess* exports HERMES_SESSION_KEY (from its own
        # --session-key argv, a separate process) — so removing this in-process
        # gateway write does not affect any of them.
```

事故还原(#24100):两个 Discord thread 并发跑 → 后来者覆盖 env → 前者的工具线程 contextvar
未设置时回落读 env → 危险命令审批提示**发错 thread**。修法:contextvars 双通道
(`_SESSION_KEY` + approval 的 `_approval_session_key`),彻底不碰进程级 env。

随后(4422-4471):
- 平台键映射:`Platform.LOCAL → "cli"`(4424);
- ephemeral prompt 三层拼接(4429-4440):事件层 context_prompt + 事件 channel_prompt +
  配置层 `_get_system_prompt_for_channel`(runner 方法);
- 运行时解析:`_resolve_session_agent_runtime`(run.py:6933 @ 863e313)失败即早退,
  返回 `⚠️ Provider authentication failed` 的最小 result dict(4454-4460)——
  **失败也走统一 result 形状**;
- `_resolve_session_reasoning_config` / `_resolve_session_service_tier` 结果暂存到
  runner 属性(4463-4471),供本回合后续使用。

---

## run_sync 之二:流式消费者与 TTS 接线(4472-4565)

### 机制:stream consumer / 流式 TTS / interim 评论的三路组装

**解决什么问题**:token 流式输出(草稿气泡实时编辑)、语音回复的流式 TTS(#60671)、
非流式平台的"interim 评论消息",三者共享 LLM delta 源但目的地不同,需要一次性接好。

**平台级流式开关**(4485-4496):`display.platforms.<plat>.streaming` 覆盖全局:

```python
        _plat_streaming = ctx.resolve_display_setting(
            ctx.user_config, platform_key, "streaming"
        )
        # None = no per-platform override → follow global config
        _streaming_enabled = (
            _scfg.enabled and _scfg.transport != "off"
            if _plat_streaming is None
            else bool(_plat_streaming)
        )
```

**consumer 构造**(4500-4534,gateway/stream_consumer.py 的 `GatewayStreamConsumer`):

gateway/run.py:4511-4532 @ 863e313(节选):

```python
                    _stream_consumer = GatewayStreamConsumer(
                        adapter=_adapter,
                        chat_id=ctx.source.chat_id,
                        config=_consumer_cfg,
                        metadata=ctx._status_thread_metadata,
                        on_new_message=(
                            (lambda: ctx.progress_queue.put(("__reset__",)))
                            if ctx.progress_queue is not None
                            else None
                        ),
                        on_before_finalize=_pause_typing_before_finalize,
                        initial_reply_to_id=ctx.event_message_id,
                        run_still_current=ctx._run_still_current,
                    )
                    if _want_stream_deltas:
                        def _stream_delta_cb(text: str) -> None:
                            if ctx._run_still_current():
                                _stream_consumer.on_delta(text)
                                # Tee to the streaming-TTS consumer (#60671).
                                if _stts_consumer_ref is not None:
                                    _stts_consumer_ref.on_delta(text)
                    ctx.stream_consumer_holder[0] = _stream_consumer
```

- **`on_new_message` = 进度气泡翻页信号源**(`__reset__`,见 send_progress_messages 机制 3);
- consumer 存进 `ctx.stream_consumer_holder[0]`:外层 `_start_stream_consumer` 任务轮询该
  holder 最多 10s 后 `await consumer.run()`(run.py:24854-24858 @ 863e313)——consumer 在
  executor 线程里建、run 任务在事件循环上跑,holder 是两个线程域的交接点;
- delta 回调 tee 到流式 TTS consumer(#60671);TTS consumer 本体在**外层事件循环线程**创建
  (run.py:24792-24828 @ 863e313,注释:若在 run_sync 里建,外层中断/收尾路径引用
  `streaming_tts_consumer_holder[0]` 会 NameError——所以 holder 由外层填,run_sync 只读 4479);
- 文本流式关但 TTS 开:装 TTS-only delta 回调(4539-4542);
- agent 侧 delta 生产:agent/chat_completion_helpers.py:3281-3283 @ 863e313
  `agent.stream_delta_callback(delta.content)`;终止哨兵 `stream_delta_callback(None)`
  (agent/conversation_loop.py:6359-6394)。

**interim 评论回调**(4544-4565):

```python
        def _interim_assistant_cb(text: str, *, already_streamed: bool = False) -> None:
            if not ctx._run_still_current():
                return
            display_text = text
            if _stream_consumer is not None:
                if already_streamed:
                    _stream_consumer.on_segment_break()
                else:
                    _stream_consumer.on_commentary(display_text)
                return
            if already_streamed or not ctx._status_adapter or not str(display_text or "").strip():
                return
            safe_schedule_threadsafe(...)
```

三分支:有 consumer 且已流出 → 只做 segment break(内容已在草稿里,别重发);
有 consumer 未流出 → `on_commentary` 入 consumer 队列(保序);无 consumer → 直接
adapter.send。`on_segment_break`/`on_commentary`:gateway/stream_consumer.py:493-499 @ 863e313。

**重实现要点**:
1. 同一 delta 源多路复用(文本草稿 + TTS)用 tee 回调,各自独立 gate;
2. 跨线程对象交接用共享 holder + 消费侧轮询,并把"谁在哪个线程创建"作为硬规则写注释;
3. interim 文本必须经 consumer 队列保序,绕过队列直发会与流式草稿乱序;
4. 内容新开消息 → 通知进度侧翻页(on_new_message→__reset__),保持双向镜像。

---

## run_sync 之三:agent 缓存(4567-4843)

### 机制:按 session 缓存 AIAgent —— prompt cache 保命 + 三种失效

**解决什么问题**:AIAgent 构造昂贵(上下文文件扫描、工具 schema、系统 prompt 冻结),
且 provider 的 prompt cache 命中要求系统 prompt/工具 schema 字节稳定 → 同一 session 的
连续消息必须复用同一 agent 实例。但缓存会陈旧,需要精确的失效规则。

**缓存键与签名**(4583-4592):`_agent_config_signature`(run.py:22608 @ 863e313)把
model/runtime/toolsets/ephemeral prompt/cache-busting 配置/user 身份/skip_context_files
折叠成签名 `_sig`;缓存表 `self._runner._agent_cache`,锁 `_agent_cache_lock`,
条目形状 `(agent, _sig, message_count, session_id)`。

**失效 1:死会话残留(#54878 × #54947 交互,4598-4712)**——这是一段"修复相互打架"的
精细处理。背景:
- #54947:同 session_key 下 session_id 切换(/resume)时,message_count 对比无意义
  (两个计数追踪不同 DB 行),应**直接复用**缓存 agent,避免每次切换都重建并击穿 prompt cache;
- #54878:自愈逻辑把路由键从已 ended 的会话上恢复走;
- 交互 bug:自愈产生与 /resume **完全相同的元组形状**(cached_sid != current_sid),
  #54947 规则会把**属于死会话的旧 agent**当"兄弟会话"复用,回合结束的 session-split 同步
  再把路由键写回死 session_id,**撤销自愈,每条消息都循环**,直到某次中断碰巧抢先。

修法:锁外先 peek 缓存条目的 session_id,查 state.db 它是否已 ended(4612-4629):

gateway/run.py:4612-4629 @ 863e313(节选):

```python
        _peek_cached_sid = None
        if _cache_lock and _cache is not None:
            with _cache_lock:
                _peek_entry = _cache.get(ctx.session_key)
            if _peek_entry and len(_peek_entry) > 3:
                _peek_cached_sid = _peek_entry[3]
        _cached_sid_is_dead = False
        if (
            _peek_cached_sid is not None
            and ctx.session_id is not None
            and _peek_cached_sid != ctx.session_id
        ):
            try:
                _cached_sid_is_dead = self._runner.session_store._is_session_ended_in_db(
                    _peek_cached_sid
                )
            except Exception:
                _cached_sid_is_dead = False
```

DB 查询放**锁外**(不让磁盘 IO 占缓存锁),但锁内**重验证** peek 结果仍指同一条目
(4676-4680,`_cached_sid == _peek_cached_sid`)——防止 peek 与加锁之间条目被替换,
把陈旧的"dead"判决错杀活 agent。命中则弃用重建(4681-4712),注释明言
"no existing upstream issue tracks this combination as of 2026-07-12"(4610-4611)。

**失效 2:跨进程写(#45966,4631-4743)**:另一进程(hermes dashboard)向同一 SessionDB
追加消息 → 缓存 agent 的内存转录陈旧。对比 DB 的 `message_count` 与缓存时快照
(`cached[2]`),不等且 session_id 未切换 → 弃用重建(4713-4743)。
`_session_id_mismatch` 时跳过对比(#54947 规则本体,4657-4669 注释)。

**命中路径**(4744-4758):

```python
                    else:
                        agent = cached[0]
                        # Refresh LRU order so the cap enforcement evicts
                        # truly-oldest entries, not the one we just used.
                        if hasattr(_cache, "move_to_end"):
                            try:
                                _cache.move_to_end(ctx.session_key)
                            except KeyError:
                                pass
                        self._runner._init_cached_agent_for_turn(agent, ctx._interrupt_depth)
                        # Refresh agent max_iterations from current config
                        # (cached agent may have been created with old config)
                        agent.max_iterations = max_iterations
                        logger.debug("Reusing cached agent for session %s", ctx.session_key)
                        reused_cached_agent = True
```

`_init_cached_agent_for_turn`(run.py:23446 @ 863e313)重置 per-turn 状态;
`max_iterations` 从当前配置刷新(缓存时的配置可能已旧)。

**锁外收尾两件事**(#52197 事故模式:锁内做慢事 → `_sweep_idle_cached_agents` 等锁 →
Discord 心跳阻塞):
1. fallback 链从磁盘刷新(#60955,4760-4770):缓存后才配置的 fallback 链必须下一回合生效,
   `_apply_fallback_chain_to_agent(agent, self._runner._refresh_fallback_model())`;
   per-session 回合串行化(`_running_agents`)保证锁外安全;
2. 被逐 agent 的**软释放**在 daemon 线程上做(4776-4790):

```python
        if _xproc_evicted_agent is not None:
            try:
                threading.Thread(
                    target=self._runner._release_evicted_agent_soft,
                    args=(_xproc_evicted_agent,),
                    daemon=True,
                    name=f"agent-xproc-evict-{str(ctx.session_key)[:24]}",
                ).start()
            except Exception:
                try:
                    self._runner._release_evicted_agent_soft(_xproc_evicted_agent)
                except Exception:
                    pass
```

"软"= `_release_evicted_agent_soft`(run.py:23539 @ 863e313)保留会话的终端沙箱/浏览器/
后台进程,重建的 agent 继承(4738-4742 注释:同一会话马上重建,资源不该被硬拆)。

**未命中重建**(4792-4843):`ctx.AIAgent(...)` 全参构造(model/toolsets/ephemeral/prefill/
reasoning/service_tier/provider 路由/会话身份/`fallback_model=self._runner.
_refresh_fallback_model()`(4826,注释:从磁盘重读,不用启动快照,#60955)/
`skip_context_files`(4569-4578:messaging 平台可关掉 SOUL.md/AGENTS.md/.cursorrules
文件扫描,Windows 上 stat+目录遍历慢 10-100 倍;`load_soul_identity=True` 保人格)),
然后锁内写缓存四元组并 `_enforce_agent_cache_cap()`(4832-4842)。

**重实现要点**:
1. agent 复用的动机是 prompt cache:签名覆盖一切影响系统 prompt/工具 schema 的输入;
2. 失效规则要区分"同会话被外部写"(count 对比)与"会话切换"(直接复用)与
   "死会话残留"(DB 校验),三者的判定信号完全不同;
3. 锁内只做内存操作;DB 查询锁外 + 锁内重验证;慢清理丢 daemon 线程,且区分软/硬释放;
4. LRU 要在命中时 move_to_end,否则容量逐出会杀掉刚用过的条目;
5. 缓存命中后仍要刷新"每回合可变"配置(max_iterations、fallback 链)。

---

## run_sync 之四:每回合回调接线(4845-4975)

### 机制:把 TurnRunner 的桥回调装到(可能是缓存的)agent 上

**为什么每回合重装**:回调闭包捕获了本回合的 ctx(队列、loop、metadata),缓存 agent 上
残留上一回合的回调会把消息发进已死的队列/旧 thread。注释(4845-4847):
"callbacks and reasoning config change every turn and must not be baked into the cached
agent constructor."

gateway/run.py:4855-4872 @ 863e313(节选):

```python
        agent.tool_progress_callback = (
            ctx.progress_callback
            if (
                ctx.needs_progress_queue
                or ctx.log_mode_enabled
                or ctx._live_status_adapter is not None
            )
            else None
        )
        # Discord voice verbal-ack hook (fires once per turn on first tool
        # call; armed only when in a voice channel with the mixer running).
        agent.tool_start_callback = (
            ctx.voice_ack_callback if ctx._voice_ack_guild[0] is not None else None
        )
        agent.step_callback = ctx._step_callback_sync if ctx._hooks_ref.loaded_hooks else None
        agent.stream_delta_callback = _stream_delta_cb
        agent.interim_assistant_callback = _interim_assistant_cb if _want_interim_messages else None
        agent.status_callback = ctx._status_callback_sync
```

- `tool_progress_callback` 的 gate 是修过 bug 的(注释 4848-4854):早年只 gate 在
  `tool_progress_enabled`,导致 `thinking_progress:true + tool_progress:off` 的用户拿到
  None 回调——思考气泡的队列建了却没人生产。现在 gate = `needs_progress_queue`
  (tool OR thinking)OR log 模式 OR live status。外层的消费任务同理 gate 在
  `needs_progress_queue`(run.py:24835-24843 注释:同一 bug 的消费侧半边——队列有人生产
  没人排空,消息"静默永不出现")。
- **credits notice 回调**(4873-4903):额度通知(用量档位/耗尽/恢复)。messaging 无持久
  状态栏 → 每条通知渲染成单行 `render_notice_line(notice)`(run.py:755 @ 863e313)走
  `_deliver_platform_notice`(run.py:13886)独立推送;`notice_clear_callback = None`
  (4903)——"已发出的平台消息无法干净撤回,档位也只 fire 一次"(4883-4884 注释;
  fired-once 锁存在缓存 agent 上跨回合持久,agent 侧机制见 agent/credits_tracker.py:202)。
- `agent._gateway_turn_context_notes`(4908-4915):本回合必达注记(auto-reset 提示、
  首次接触介绍、语音频道变更)**走当前用户消息的 api_content sidecar,不进系统 prompt**
  (系统 prompt 变化会击穿 prompt cache);无条件赋值,缓存 agent 绝不重放旧注记
  (`_consume_pending_turn_sidecar_notes`,run.py:23230 @ 863e313,consume-and-clear)。

### 机制:background review 消息的"主响应之后"缓冲(4917-4967)

**解决什么问题**:后台记忆审查("💾 Memory updated")完成时机不定,若在主响应发出**之前**
送达,聊天顺序错乱(次要通知插在回答前)。

gateway/run.py:4944-4954 @ 863e313:

```python
        def _bg_review_send(message: str) -> None:
            if not ctx._status_adapter or not ctx._run_still_current():
                return
            if not _bg_review_release.is_set():
                with _bg_review_pending_lock:
                    if not _bg_review_release.is_set():
                        _bg_review_pending.append(message)
                        return
            _deliver_bg_review_message(message)

        agent.background_review_callback = _bg_review_send
```

- 双检查锁模式(Event + Lock):release 前的消息进 pending 列表;
  `_release_bg_review_messages`(4935-4941)set Event 后原子取走 pending 逐条投递;
- release 钩子注册到 adapter(4957-4967):`register_post_delivery_callback(session_key,
  cb, generation=run_generation)`(gateway/platforms/base.py:4819 @ 863e313)——
  base.py 投递主响应的 finally 块触发;旧 adapter 无该方法时直接写
  `_post_delivery_callbacks` dict 兜底(4964-4967);
- 投递用 `_non_conversational_metadata(...)`(run.py:452 @ 863e313)标记非会话消息
  (4928),避免平台把它当对话回复处理;
- agent 侧调用:agent/background_review.py:991 @ 863e313。

**重实现要点**:
1. 每回合重装全部回调(包括显式装 None),缓存实例上的旧回调是隐蔽炸弹;
2. 生产者 gate 与消费者 gate 必须同一条件表达式,否则出现"建了队列没人生产/生产了没人排空"
   两类对偶 bug;
3. "次要通知晚于主响应"用 Event+pending 缓冲 + 投递方 finally 释放,带 generation 防陈旧;
4. 必达注记走用户消息 sidecar 而非系统 prompt,保 prompt cache;consume-and-clear 防重放。

---

## run_sync 之五:clarify 回调(4977-5075)

### 机制:澄清问题的 sync→async 桥 + 排序屏障

**解决什么问题**:clarify 工具要"问用户一个问题并**阻塞等待**回答"(镜像 CLI 的 input())。
agent 在 worker 线程上同步等;发送要跳到事件循环;回答从平台事件路由回来 set Event。

流程(4988-5068):
1. 生成 `clarify_id`,`_clarify_mod.register(...)` 登记(tools/clarify_gateway.py:80
   @ 863e313,建 threading.Event 条目);
2. **暂停 typing**(5004-5011):Slack Assistant API 的 "is thinking..." 状态会**禁用输入框**,
   用户没法打 "Other" 自由回答——与审批同理;
3. **排序屏障**(#clarify-ordering):

gateway/run.py:5013-5030 @ 863e313(节选):

```python
            # Ordering barrier (#clarify-ordering): flush any buffered
            # assistant prose (interim commentary / streamed deltas) to the
            # platform BEFORE sending the poll.  The poll is delivered on a
            # separate, agent-thread-blocking path; without this barrier it
            # races ahead of prose still sitting in the stream consumer's
            # queue, so the question renders ABOVE its own explanation.
            # Best-effort + short timeout: never hang the agent thread if
            # the consumer task isn't running.
            try:
                _sc = ctx.stream_consumer_holder[0] if ctx.stream_consumer_holder else None
                _flush = getattr(_sc, "flush_pending_sync", None)
                if callable(_flush):
                    _flush(timeout=3.0)
```

`flush_pending_sync`(gateway/stream_consumer.py:502 @ 863e313)阻塞 agent 线程直到
队列中此前的内容全部落地——否则问题气泡跑到自己的解释文字**上面**。

4. 调度 `send_clarify` 到事件循环,`fut.result(timeout=15)` 等发送结果(5032-5054);
   发送失败 → `clear_session` 清登记,返回哨兵字符串
   `"[clarify prompt could not be delivered]"`(5056-5061)——**让模型能适配而不是挂死**;
5. 阻塞等待回答(5063-5068):

```python
            timeout = _clarify_mod.get_clarify_timeout()
            response = _clarify_mod.wait_for_response(clarify_id, timeout=float(timeout))
            if response is None or response == "":
                # Timeout or session-boundary cancellation
                return f"[user did not respond within {int(timeout / 60)}m]"
            return response
```

`wait_for_response`(clarify_gateway.py:107,1 秒切片轮询让 agent 心跳存活)、
`get_clarify_timeout`(:408,默认 3600s)。run_sync 的 finally(5441-5445)统一
`clear_session` 兜底,阻塞线程绝不悬挂过 run 生命周期。
挂载:`agent.clarify_callback = _clarify_callback_sync`(5070);agent 侧消费:
agent/tool_executor.py:1819、agent/agent_runtime_helpers.py:2967 @ 863e313。

**与进度气泡的分工**:进度层对 clarify 完全豁免(progress_callback 3788-3789,#52374),
`send_clarify` 是唯一渲染面(按钮或编号文本 fallback,adapter 决定)。

**重实现要点**:
1. "问用户并等待"= 登记表 + threading.Event + 平台回路 set;超时/失败都返回**可解释哨兵**,
   模型侧可降级,永不无限挂;
2. 阻塞前必须 flush 流式缓冲(排序屏障),且 flush 必须限时 best-effort;
3. 暂停 typing 是硬需求:某些平台 typing 状态直接禁用用户输入;
4. finally 里 clear_session 幂等兜底,覆盖中断/完成/关机三种退出。

---

## run_sync 之六:历史构建与 FTS 守卫(5076-5137)

### 机制:回合所有权发布 + 历史双形状 + 三重防护

- `ctx.agent_holder[0] = agent`(5077)发布给中断路径;
  `agent._gateway_turn_process_task_id / _gateway_turn_process_baseline`(5081-5082)
  发布回合进程所有权:/stop、/new、断连、关机中断只清理**本回合基线之后**的进程,
  更老会话的进程不受波及(5078-5080 注释;外层 finally 在 worker 结束瞬间清空这两个标记,
  run.py:25167-25170,#76115:已结束回合上迟到的 /stop 不得误杀回合故意留下的后台工作)。
- `ctx.tools_holder[0] = agent.tools`(5084):完整工具定义供转录日志。

**历史转换**(5086-5104):`_build_gateway_agent_history`(run.py:1316 @ 863e313)处理两种
形状(注释 5087-5093):正常路径的 `{role, content, timestamp}` 简单行(剥 timestamp);
中断路径的完整 agent 消息(带 tool_calls/tool_call_id/reasoning,**必须原样透传**,
丢 tool_calls 会让 API 见到断裂的 assistant→tool 序列直接 500)。同时结构化处理 Telegram
观察组上下文:`observed=True` 的行**不进可重放历史**,作为 API-only 上下文附在当前消息上
(5095-5099 注释),返回 `(agent_history, observed_group_context)` 二元组。

**FTS 写腐坏守卫**(#50502,5106-5132):

gateway/run.py:5113-5132 @ 863e313(节选):

```python
        if reused_cached_agent and getattr(agent, "session_id", None) == ctx.session_id:
            _selected = _select_cached_agent_history(
                agent_history, getattr(agent, "_session_messages", None)
            )
            if _selected is not agent_history:
                logger.warning(
                    "Persisted transcript lagged live cached history for "
                    "session %s (disk=%d, memory=%d); preserving live "
                    "conversation context (possible FTS write corruption)",
                    ctx.session_key, len(agent_history), len(_selected),
                )
                # The live in-memory history bypassed the
                # _build_gateway_agent_history cleanup pipeline above —
                # re-apply the stale-confirmation expiry (#59607) so a
                # dangerous confirmation can't slip through this path
                # either. Idempotent; messages without timestamps are
                # untouched.
                agent_history = strip_stale_dangerous_confirmations(
                    _selected, now=time.time()
                )
```

事故链(#50502):SQLite FTS 触发器腐坏 → 消息持久化**静默失败** → 从盘重载的转录比缓存
agent 内存里的 `_session_messages` 短 → 若用盘上短版本覆盖,**同会话瞬间失忆**。
守卫:仅当复用缓存 agent 且绑定同一 session_id 时,`_select_cached_agent_history`
(run.py:1421 @ 863e313)择长保留内存版;但内存版绕过了清洗管线,需补
`strip_stale_dangerous_confirmations`(agent/replay_cleanup.py:255 @ 863e313,#59607:
过期的危险命令确认不得从旁路溜进历史,幂等)。

媒体路径收集(5134-5137):`_collect_history_media_paths`(run.py:1654)先于本回合执行
记录历史中已有的 MEDIA 路径,供收尾的 MEDIA 去重(压缩安全:列表缩短也知道哪些是旧的)。

**重实现要点**:
1. 中断恢复的历史必须保留完整 tool_calls 链,任何"清理"都可能制造 API 级断裂;
2. 磁盘与内存转录不一致时,同会话同 id 场景应信任内存(写路径可能静默失败),但旁路数据
   必须补跑安全清洗;
3. 回合进程所有权(task_id + 基线快照)使中断清理可精确到回合,并在回合结束即刻撤销。

---

## run_sync 之七:审批回调(5139-5239)

### 机制:危险命令审批的 sync→async 桥(按钮优先,文本兜底)

**解决什么问题**:危险命令执行前要用户批准,agent 工具线程阻塞等待(镜像 CLI input())。
注册按 session:`register_gateway_notify(session_key, cb)`(tools/approval.py:2465
@ 863e313);approval 模块在需要审批时回调 `_approval_notify_sync(approval_data)` 发提示,
用户 /approve /deny 走平台命令路径解锁。`unregister_gateway_notify`(:2477)会
"Signals ALL blocked threads for this session"——run 结束绝不留悬挂线程。

关键片段一:typing 暂停(Slack 硬约束):

gateway/run.py:5158-5165 @ 863e313:

```python
            # Pause the typing indicator while the agent waits for
            # user approval.  Critical for Slack's Assistant API where
            # assistant_threads_setStatus disables the compose box — the
            # user literally cannot type /approve while "is thinking..."
            # is active.  The approval message send auto-clears the Slack
            # status; pausing prevents _keep_typing from re-setting it.
            # Typing resumes in _handle_approve_command/_handle_deny_command.
            ctx._status_adapter.pause_typing_for_chat(ctx._status_chat_id)
```

(`pause_typing_for_chat`:gateway/platforms/base.py:4796 @ 863e313;恢复在
approve/deny 命令处理器里——**暂停与恢复分属两个代码路径**,靠命令处理器闭环。)

关键片段二:命令脱敏(#48456):

gateway/run.py:5170-5175 @ 863e313:

```python
            # Redact credentials from the command before displaying it in
            # the approval prompt — Tirith's findings are already redacted,
            # but the raw command string still leaks secrets to the chat
            # platform (#48456). Applied here so BOTH the button-based
            # (send_exec_approval) and plain-text fallback paths below use
            # the redacted value.
            cmd = _redact_approval_command(cmd)
```

(`_redact_approval_command`:run.py:596 @ 863e313。事故:安全扫描器 Tirith 的 findings
已脱敏,但审批提示里的**原始命令串**仍把密钥泼上聊天平台。)

关键片段三:按钮优先 + 文本兜底(5181-5239):
- 类上探测 `send_exec_approval`(5181,"Check the *class* ... avoids false positives
  from MagicMock auto-attribute creation in tests");
- 调度到事件循环 `fut.result(timeout=15)`,成功即返回;失败(含调度失败抛
  RuntimeError)落文本路径;
- 文本兜底用 adapter 的 `typed_command_prefix`(5216,Slack thread 里 "/" 被平台拦截、
  Matrix 客户端保留 "/",这些平台教用户打 `!approve`),
  `_format_exec_approval_fallback`(run.py:612 @ 863e313)渲染,透传
  `allow_permanent/allow_session/smart_denied` 三个策略位。

会话键绑定(5384-5386):

```python
        _approval_session_key = ctx.session_key or ""
        _approval_session_token = set_current_session_key(_approval_session_key)
        register_gateway_notify(_approval_session_key, _approval_notify_sync)
```

`set_current_session_key`(tools/approval.py:172 @ 863e313)= contextvar 绑定,工具
worker 线程继承,审批提示路由到正确 thread(#24100 修法的另一半);finally 里
`unregister + reset_current_session_key(token)`(5437、5446)。

**重实现要点**:
1. 审批 UI 分层:富交互(按钮)优先、纯文本兜底,兜底要用平台真实可打的命令前缀;
2. 任何面向用户展示的命令串必须过脱敏,不能只依赖上游扫描器的输出已脱敏;
3. 审批期间关 typing(有的平台 typing = 锁输入框),恢复由命令处理器负责;
4. 注册/注销必须对称且注销要唤醒所有阻塞线程;session 绑定用 contextvar 不用 env。

---

## run_sync 之八:auto-continue 与 resume 恢复(5241-5382)

### 机制:中断回合的续跑注记(4 层防护)

**解决什么问题**:gateway 重启/崩溃/SIGTERM 把回合杀在半路,历史尾巴挂着未消化的 tool 结果
(#4493);或 drain-timeout 关机标记了 `resume_pending`。新消息来时要给模型一段恢复指引,
但指引是 API-only 的:**绝不能作为用户原话持久化**(5241-5243 注释,
`_persist_user_message_override` 机制)。

**新鲜度双信号**(#16802,5275-5311):
- 信号 A:最后一条持久化转录行的年龄(`_last_transcript_timestamp(ctx.history)`,
  run.py:1469;窗口 `_auto_continue_freshness_window()`,run.py:949)。读 `ctx.history`
  而非 `agent_history`,因为后者已把 timestamp 剥掉(5269-5274 注释);
- 信号 B:重启看门狗盖的 `last_resume_marked_at` 时间戳:

gateway/run.py:5301-5311 @ 863e313:

```python
        _resume_mark_is_fresh = False
        if _resume_entry is not None and getattr(_resume_entry, "resume_pending", False):
            _resume_mark_is_fresh = _is_fresh_gateway_interruption(
                getattr(_resume_entry, "last_resume_marked_at", None),
                window_secs=_freshness_window,
            )
        _is_resume_pending = bool(
            _resume_entry is not None
            and getattr(_resume_entry, "resume_pending", False)
            and (_interruption_is_fresh or _resume_mark_is_fresh)
        )
```

**为什么要 OR**(5288-5300 注释还原的事故):活跃 thread 最后持久化行可能是几小时前,
但中断刚刚发生;只看转录钟会静默丢弃恢复注记,而启动 auto-resume 回合的用户文本是空的
(`_schedule_resume_pending_sessions` 合成)→ 模型收到**空白用户消息**,回一句
"the message came through blank" 的困惑噪音。

**分支 1:resume_pending**(5318-5335):`build_resume_recovery_note(reason, message,
interactive=...)`(run.py:1057 @ 863e313);adapter 感知(#57056):交互平台报告恢复并问
下一步;非交互事件平台(webhook/API server)**继续中断的工作**——没人会回答,
一句确认等于静默弃任务。

**分支 2:新消息 + 新鲜 tool 尾巴**(5336-5344):

gateway/run.py:5338-5344 @ 863e313:

```python
            ctx.message = (
                "[System note: A new message has arrived. The conversation "
                "history contains pending tool outputs from an interrupted turn. "
                "IGNORE those pending results. Address the user's NEW message "
                "below FIRST. Do NOT re-execute old tool calls from the history.]\n\n"
                + ctx.message
            )
```

**分支 3:空消息安全网**(5357-5382):两个新鲜度信号都失败/标记被竞态清掉时,
resume_pending 会话的空文本回合仍**必须**拿到恢复注记(限定 resume_pending 会话,
合法的空用户回合——如无 caption 图片——不受影响):

gateway/run.py:5366-5371 @ 863e313:

```python
        if (
            isinstance(ctx.message, str)
            and not ctx.message.strip()
            and _resume_entry is not None
            and getattr(_resume_entry, "resume_pending", False)
        ):
```

**其他 ctx.message 前缀注入**(同区域):模型切换注记(5248-5251,
`_pending_model_notes.pop` 一次性)、/reload-skills 注记(5351-5355,同 CLI 队列模式:
prepend 到下一条用户消息,"Nothing was written to the transcript out-of-band, so message
alternation stays intact")。这些都是 `nonlocal message` 时代的重绑定点,现全部写 `ctx.message`。

**重实现要点**:
1. 恢复指引 = API-only 前缀 + 持久化覆盖(存原话),两者必须成对出现;
2. 新鲜度判定用多信号 OR:转录钟 + 中断标记钟,任何单钟都有致盲场景;
3. 恢复行为要按 adapter 交互性分叉:有人在场→问,无人在场→继续干;
4. 空用户消息是模型毒药,合成回合必须有兜底注记(且兜底要窄限定,不误伤合法空消息);
5. 一次性注记统一 pop-and-prepend 模式,绝不带外写转录(保持 user/assistant 交替)。

---

## run_sync 之九:执行与 finally(5384-5455)

### 机制:run_conversation 的参数组装与对称清理

gateway/run.py:5435-5447 @ 863e313:

```python
            result = agent.run_conversation(_api_run_message, **_conversation_kwargs)
        finally:
            unregister_gateway_notify(_approval_session_key)
            # Cancel any pending clarify entries so blocked agent
            # threads don't hang past the end of the run (interrupt,
            # completion, gateway shutdown).  Idempotent.
            try:
                from tools.clarify_gateway import clear_session as _clear_clarify_session
                _clear_clarify_session(_approval_session_key)
            except Exception:
                pass
            reset_current_session_key(_approval_session_token)
        ctx.result_holder[0] = result
```

try 块内(5387-5435):
- 原生图片附件(5392-5417):`_consume_pending_native_image_paths`(run.py:16224,
  consume-and-clear 防陈旧重附)→ `build_native_content_parts`(agent/image_routing.py)
  把用户回合包成 OpenAI 多模态 content list;全部图片读失败回落纯文本;
- 观察上下文包装(5419-5422):`_wrap_current_message_with_observed_context`
  (run.py:1443)把 Telegram 观察组消息附在**API 消息**上;`persist_user_message`
  仍存真实原话(5429-5430);
- `_conversation_kwargs`:`conversation_history=agent_history`、`task_id=ctx.session_id`、
  条件性 `persist_user_message/persist_user_timestamp/moa_config`(5423-5434)。

结果发布:`ctx.result_holder[0] = result`(5447,外层通过 holder 读);
`_stream_consumer.finish()`(5450-5451,gateway/stream_consumer.py:602 哨兵入队);
流式 TTS 的 finish **不在这里**(5453-5456 注释:由外层事件循环线程在 executor 返回后调,
这样 run_sync 的早退路径也能被收尾;外层兜底 abort 在 run.py:25816-25824)。

---

## run_sync 之十:收尾同步(5457-5572)

### 机制:token 统计 + session split 同步

**token 统计**(5461-5472):从 agent 实例抽 `context_compressor.last_prompt_tokens`、
`session_prompt_tokens`、`session_completion_tokens`、`context_length`、`model`,
进返回 dict(供计费/显示)。

**session split 检测与同步**(5474-5561):压缩可能把会话轮转成子会话(id 变),或
in-place 压实(#38763,id 不变):

gateway/run.py:5479-5487 @ 863e313:

```python
        # In-place compaction (compression.in_place / #38763) compacts the
        # transcript WITHOUT rotating the id, so the id-change diff below
        # can't detect it. compress_context() sets this rotation-independent
        # flag on the agent; the gateway uses it to re-baseline transcript
        # handling (history_offset=0 + rewrite the JSONL transcript) the
        # same way a split would, even though the session_id is unchanged.
        _compacted_in_place = bool(getattr(agent, "_last_compaction_in_place", False)) if agent else False
        agent_session_id = getattr(agent, 'session_id', ctx.session_id) if agent else ctx.session_id
        if agent and ctx.session_key and agent_session_id != ctx.session_id:
```

**同步的三重防守**(5493-5523):写 session_store 前检查:
① `_run_still_current()`——陈旧 run 不得发布 split(5497-5503);
② entry 已指向新 id → 视为已持久化(5504-5505);
③ entry 指向第三个 id → 绑定在压缩期间已被别人移走,跳过(5506-5514);
否则写入 `entry.session_id = agent_session_id` + `_save()` +
`_record_gateway_session_peer`(5515-5523)。**位置注释**(5474-5476):同步做在
run_conversation 返回后**立即**、而非成功路径末尾——"压缩可能在后续模型调用失败之前轮转;
失败返回也必须指向压缩后的子会话"。

**Telegram DM thread 恢复**(5525-5557):合成/恢复事件丢失 `source.thread_id` 时,
从 topic binding 表按新 session_id 反查回填(5540-5546),否则
`_thread_metadata_for_source` 会把消息路由进 General 话题;仅在本 run 成功发布 split 后
执行("a stale /stop→/new predecessor must not mutate routing/binding state",5531-5533);
失败非致命(落 General = 修复前行为)。之后 `_sync_telegram_topic_binding(...,
reason="agent-run-compression")`(5558-5561)。

**history_offset**(5563-5572):

```python
        _effective_history_offset = (
            0 if (_session_was_split or _compacted_in_place) else len(agent_history)
        )
```

语义:gateway 侧持久化要从 `messages[offset:]` 起切。正常回合 offset = 传入历史长度
(只存本回合新消息);split 或 in-place 压实后返回的 messages **就是压实集**,必须全量
持久化(offset 0),按旧长度切会把一切都切丢(5565-5569 注释)。

---

## run_sync 之十一:空响应与 MEDIA 附加(5574-5647)

### 机制:空响应归一化返回

5574-5609:`_normalize_empty_agent_response`(run.py:3445)+
`_sanitize_gateway_final_response`(run.py:699)+ 错误兜底 `⚠️ {error}`,返回与成功路径
同形状的 dict。注释点名 #64686(5586-5592):`failure_reason` 必须在空响应路径也透传——
"downstream consumers (TUI billing surface, transient-failure persistence) lose the
structured reason exactly when the run produced no text"。

### 机制:MEDIA 标签自动附加(#34608 / #160)

**解决什么问题**:TTS 等工具在**工具结果 JSON**里嵌 `MEDIA:<path>` 标签,模型的最终文本
通常不带 → adapter 的 `extract_media()` 找不到文件。需要从工具结果收集标签补到响应尾部,
且**恰好一次**。

gateway/run.py:5631-5647 @ 863e313:

```python
        if "MEDIA:" not in final_response:
            media_tags, has_voice_directive = _collect_auto_append_media_tags(
                result.get("messages", []),
                history_offset=len(agent_history),
                history_media_paths=_history_media_paths,
            )

            if media_tags:
                seen = set()
                unique_tags = []
                for tag in media_tags:
                    if tag not in seen:
                        seen.add(tag)
                        unique_tags.append(tag)
                if has_voice_directive:
                    unique_tags.insert(0, "[[audio_as_voice]]")
                final_response = final_response + "\n" + "\n".join(unique_tags)
```

两代修复叠加(5618-5630 注释):
- #34608:主防线改为**切片定位本回合**——`messages = agent_history + 本回合产物`,
  从 `len(agent_history)` 切,几回合前的陈旧 MEDIA 路径永不泄漏到纯文本回复上;
- #160(旧防线保留):基于路径集合 `_history_media_paths` 的去重,是压缩把消息列表
  切短于原历史长度时 fallback 分支的**唯一**防线(压缩安全);
- `_collect_auto_append_media_tags`:run.py:1573 @ 863e313。

### 机制:自动会话标题(5649-5716)

首轮交换后后台生成标题(`maybe_auto_title`,agent/title_generator.py):
- 失败静默(#23246,5654-5663):gateway 模式下 auto-title 失败**不得**变成用户可见消息,
  debug 日志即可(CLI 保留原 `_emit_auxiliary_failure` 行为);
- 运行时校验器(#19027,5664-5682):快照当前 model/provider,后台 titler 触发时若会话
  模型已切换则跳过 LLM 调用——陈旧请求会**把已卸载的 Ollama 模型重新拉起**;
- 标题回调分道(5684-5706):Telegram topic lane → `_schedule_telegram_topic_title_rename`;
  Discord auto-thread / relay Discord channel lane → `_schedule_discord_semantic_thread_rename`。
  relay 注释(5695-5701)记录 2026-07-31 staging 复现:第二个谓词只是形状判断,连接器是否
  真的 auto-thread 了回复要**投递后**才知道(非流式 lane 上晚于本注册)→ 回调必须**急切
  注册**,cache 查询推迟到触发时;当年 gate 在 cache 读上导致回调从未注册、rename 从未发出。

---

## run_sync 之十二:最终返回 dict(5718-5755)

统一 result 契约(外层 `_run_agent_inner` 消费):`final_response / last_reasoning /
messages / api_calls / failed / failure_reason / completed / interrupted / partial / error /
interrupt_message / compression_deferred / tools / history_offset / compacted_in_place /
last_prompt_tokens / input_tokens / output_tokens / model / context_length / session_id /
response_previewed / response_transformed / agent_persisted`。三个注释点:

gateway/run.py:5732-5738 @ 863e313:

```python
            # Soft lock-contention defer (#69870 consumer): distinct from
            # compression_exhausted so the gateway never auto-resets a
            # session that a concurrent compressor is about to shrink.
            "compression_deferred": (
                ctx.result_holder[0].get("compression_deferred", False)
                if ctx.result_holder[0] else False
            ),
```

gateway/run.py:5750-5754 @ 863e313:

```python
            # Pass through the agent_persisted flag so the persistence block
            # above can correctly determine whether the codex app-server path
            # self-persisted (it didn't — see codex_runtime.py).  Default
            # True preserves the skip-db behaviour for the standard runtime.
            "agent_persisted": (ctx.result_holder[0].get("agent_persisted", True) if ctx.result_holder[0] else True),
```

- `compression_deferred` ≠ `compression_exhausted`:前者是软锁竞争推迟(#69870),gateway
  不得据此 auto-reset 会话;
- `agent_persisted` 默认 True:标准 runtime 自持久化,gateway 跳过 DB 写;codex app-server
  路径不自持久化,需 gateway 补写;
- 读值大量走 `ctx.result_holder[0]` 而非局部 `result`:与成功路径外的读者(外层中断路径
  也读 holder)保持同一数据源。样板级别:两处 return dict 字段罗列(5581-5609、5718-5755)。

**run_sync 整体重实现要点**:
1. 回合执行体放 worker 线程,一切 UI 副作用经 loop 调度;contextvars 是会话身份的唯一载体;
2. result dict 是外层的稳定契约:成功/空响应/认证失败三条路径同形状,新增诊断字段
   (failure_reason 等)要三路同步;
3. session id 同步要在 run 返回后立即做、带三重陈旧防守(generation/已持久化/绑定被移);
4. history_offset 协议:正常=传入历史长度,split 或 in-place 压实=0,由 agent 的
   rotation-independent 标志位驱动;
5. 附带产物(MEDIA、标题、通知)全部后台化/幂等化/失败静默,绝不污染主响应。

---

## 文档-代码冲突候选汇总(6 条)

1. **[确认] run.py:3797 @ 863e313 注释 "see line ~9607" 行号失效**:本基线该行位于
   `_cleanup_agent_resources_off_loop`(9596-9619)内部;agent_holder 的共享接线实际在
   run.py:24722-24723。闭包提取导致行号漂移,注释未随迁。
2. **[无法验证的出处声明] run.py:3674 "The bodies are byte-identical to the original
   closures"**:本基线树内已无原闭包,该声明只能对照 git 历史验证;作为设计意图记录,
   不构成行为冲突,但读者不应把它当作"现在仍与某处代码一致"的断言。
3. **[前后不一致] turn_context.py:13-14 "All fields are written once by
   `_run_agent_inner`"** 与 `message` 字段实际被 `TurnRunner.run_sync` 多次重绑定
   (run.py:5251、5333、5338、5355、5376)矛盾;同文件 68-79 行的"第二波"说明已自我修正
   (message 是唯一 ex-nonlocal 例外),但首段总述未更新,单看首段会得出错误结论。
4. **[措辞残留] run.py:3997-3998 "instead of clamping to 500+"**:代码是
   `max(1, raw - (64 if raw > 128 else 0))`,不存在 500 下限;疑指已删除的旧实现。
5. **[待他轮验证] run.py:4881-4882 "The fired-once latch lives on the cached agent and
   persists across turns"**:通知档位只触发一次的锁存声明属于 agent 侧
   (agent/credits_tracker.py),本轮未验证其真伪,移交 credits 机制精读轮。
6. **[待他轮验证] run.py:3692-3694 "Slack keeps tool_progress off by default"**:与
   run.py:24418-24421 注释互证,但实际逐平台默认值在 gateway/display_config.py 的
   `resolve_display_setting` 数据里,本轮未核对 Slack 默认表。

另记两条**行为微妙点**(非冲突,重实现须知):
- send_progress_messages 的节流路径(4176-4182)把行留在缓冲后 `continue`,而
  `queue.Empty` 分支(4256-4257)不检查未落盘缓冲——孤立的被节流行要等下一条消息或
  任务取消才可见;
- 无编辑能力平台的入口 gate(3962-3969)排空一次即 return,此后 progress_callback 仍持续
  入队(平台级开关与 adapter 能力不同步),队列积压至回合结束丢弃(有界)。

---

## 簇内调用关系总表

**它被谁调**(全部经 ctx 字段间接或经 agent 属性):
- 构造/接线:gateway/run.py:24523-24570、24717-24719、24722-24735、24743-24750、
  24787-24790、24833 @ 863e313(`_run_agent_inner`);
- `send_progress_messages`:run.py:24843 create_task,run.py:25782 cancel;
- `run_sync`:run.py:25151-25191(watchdog 包装后进 executor);
- `progress_callback` ← agent/tool_executor.py:708、1509、1547;
  agent/conversation_loop.py:5785、5790;agent/codex_runtime.py:439-441;
- `voice_ack_callback` ← agent/tool_executor.py:720;
- `_step_callback_sync` ← agent/conversation_loop.py:1476;
- `_event_callback_sync` ← agent/conversation_compression.py:3479、agent/codex_runtime.py:253;
- `_status_callback_sync` ← agent/conversation_compression.py:110、1841。

**它调谁**(方向:TurnRunner →):
- runner 方法:`_adapter_for_source`、`_resolve_session_agent_runtime`(run.py:6933)、
  `_resolve_turn_agent_config`(:7101)、`_agent_config_signature`(:22608)、
  `_init_cached_agent_for_turn`(:23446)、`_release_evicted_agent_soft`(:23539)、
  `_build_stream_consumer_config`(:23758)、`_consume_pending_turn_sidecar_notes`(:23230)、
  `_consume_pending_native_image_paths`(:16224)、`_deliver_platform_notice`(:13886)、
  `_refresh_fallback_model`、`_apply_fallback_chain_to_agent`、`_enforce_agent_cache_cap`、
  `_sync_session_model_from_agent`、`_sync_telegram_topic_binding`、
  `_is_telegram_topic_lane`、`_schedule_telegram_topic_title_rename`、
  `_schedule_discord_semantic_thread_rename`、session_store/_session_db 各查询;
- run.py 模块级助手:`_prepare_gateway_status_message`(:725)、
  `_send_or_update_status_coro`(:770)、`render_notice_line`(:755)、
  `_non_conversational_metadata`(:452)、`_redact_approval_command`(:596)、
  `_format_exec_approval_fallback`(:612)、`_sanitize_gateway_final_response`(:699)、
  `_normalize_empty_agent_response`(:3445)、`_build_gateway_agent_history`(:1316)、
  `_select_cached_agent_history`(:1421)、`_wrap_current_message_with_observed_context`
  (:1443)、`_last_transcript_timestamp`(:1469)、`_collect_auto_append_media_tags`
  (:1573)、`_collect_history_media_paths`(:1654)、`_current_max_iterations`(:1899)、
  `_checkpoint_agent_kwargs`(:3207)、`_auto_continue_freshness_window`(:949)、
  `_is_fresh_gateway_interruption`(:1028)、`build_resume_recovery_note`(:1057);
- 跨文件:agent/display.py(:122/:148/:569/:664/:677/:682/:687)、
  agent/async_utils.py:34(safe_schedule_threadsafe)、
  agent/replay_cleanup.py:255(strip_stale_dangerous_confirmations)、
  agent/onboarding.py(hint 四件套)、agent/image_routing.py(build_native_content_parts)、
  agent/title_generator.py(maybe_auto_title)、
  tools/approval.py(:172/:177/:2465/:2477)、
  tools/clarify_gateway.py(:80/:107/:357/:408)、
  gateway/stream_consumer.py(GatewayStreamConsumer,:493/:497/:502/:590/:602/:760)、
  gateway/streaming_tts_consumer.py(经 holder 只读)、
  gateway/platforms/base.py(:2658 set_status_text、:4796 pause_typing_for_chat、
  :4819 register_post_delivery_callback、edit_message/send/send_typing/send_clarify/
  send_exec_approval 契约)、gateway/turn_context.py(TurnContext seam)。
