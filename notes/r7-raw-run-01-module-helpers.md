# gateway/run.py 第 1–1923 行 · 模块级辅助(上)底稿 @ 863e313

> 本段是 gateway 运行器的模块级辅助层:进入 `GatewayRunner` 类(约 5794 行起)之前的全部纯函数、正则常量与模块级初始化副作用。所有行号均对 `gateway/run.py @ 863e313`,跨文件引用另行标注。

---

## 模块头:bootstrap 导入与依赖(1–67)

### 机制 1:hermes_bootstrap 必须第一个导入 + 容错降级

**场景/问题**:Windows 上 stdio 默认非 UTF-8,任何输出前必须先修;但 `hermes update` 中途失败(git reset 落了新代码、`uv pip install -e .` 没跑完)时 venv 里没有注册 `hermes_bootstrap` 模块,硬导入会让 gateway 直接起不来。

**实现**:文件第一条可执行语句就是 try-import,`ModuleNotFoundError` 时静默跳过(POSIX 本来就是 no-op)。

路径:gateway/run.py:16-25 @ 863e313
```python
# IMPORTANT: hermes_bootstrap must be the very first import — UTF-8 stdio
# on Windows.  No-op on POSIX.  See hermes_bootstrap.py for full rationale.
try:
    import hermes_bootstrap  # noqa: F401
except ModuleNotFoundError:
    # Graceful fallback when hermes_bootstrap isn't registered in the venv
    # yet — happens during partial ``hermes update`` where git-reset landed
    # new code but ``uv pip install -e .`` didn't finish.  Missing bootstrap
    # means UTF-8 stdio setup is skipped on Windows; POSIX is unaffected.
    pass
```

**设计理由与取舍**:把"半升级状态可启动"排在"Windows 编码一定正确"之前——降级的代价是 Windows 上可能乱码,而硬失败的代价是整个 gateway 拒绝启动。

**调用关系**:27–67 行为标准库与项目内导入,其中 49–65 行从 `agent.*` 导入(`consume_detached_task_result`、压缩状态模板常量、`INTERRUPT_WAITING_FOR_MODEL_PREFIX`(定义于 agent/conversation_loop.py:100)、`compression_made_progress`(定义于 agent/turn_context.py:199)),66–67 行导入 `hermes_cli.config.cfg_get` / `hermes_cli.fallback_config.get_fallback_chain`。纯样板,点名带过。

**重实现要点**:
1. 平台 stdio 修补必须是进程第一条语句,且必须能容忍"部分升级"状态;
2. 把"必须第一个导入"的约束写在导入旁边的注释里,防止后续重排;
3. 降级路径要注明降级后丢了什么能力(此处:Windows UTF-8)。

---

## Agent 缓存与超时常量(69–88)

### 机制 2:长驻进程的资源上界常量

**场景/问题**:gateway 是长驻进程,每个会话缓存一个 `AIAgent`(持有 LLM client、工具 schema、memory provider),不设上界会无限增长。

**实现**:模块级常量,LRU 上限 + 空闲 TTL,连同各平台连接/断开超时、stall 通知发送超时、SSE 缓冲上限。

路径:gateway/run.py:69-88 @ 863e313
```python
# --- Agent cache tuning ---------------------------------------------------
# Bounds the per-session AIAgent cache to prevent unbounded growth in
# long-lived gateways (each AIAgent holds LLM clients, tool schemas,
# memory providers, etc.).  LRU order + idle TTL eviction are enforced
# from _enforce_agent_cache_cap() and _session_expiry_watcher() below.
_AGENT_CACHE_MAX_SIZE = 128
_AGENT_CACHE_IDLE_TTL_SECS = 3600.0  # evict agents idle for >1h
_PLATFORM_CONNECT_TIMEOUT_SECS_DEFAULT = 30.0
# Telegram cold polling now proves one real getUpdates round trip before connect
# returns. Leave enough outer budget for initialize/deleteWebhook/start_polling
# wall deadlines plus readiness; other platforms retain the 30s isolation bound.
_TELEGRAM_CONNECT_TIMEOUT_SECS_DEFAULT = 180.0
_ADAPTER_DISCONNECT_TIMEOUT_SECS_DEFAULT = 5.0
# Round-2 #2: upper bound on a single stall-notify adapter.send so a wedged
# transport cannot block the session-stall watcher pass (notify-only path;
# on timeout the latch stays clear and the next tick retries).
_STALL_NOTIFY_SEND_TIMEOUT_SECONDS = 15.0
_GATEWAY_PROXY_SSE_BUFFER_MAX_CHARS = 16 * 1024 * 1024
_TELEGRAM_COMMAND_MENTION_RE = re.compile(r"(?<![\w:/])/([A-Za-z0-9][A-Za-z0-9_-]*)")
_GATEWAY_HYGIENE_PLATFORM = "gateway_hygiene"
```

**调用关系(段外)**:`_AGENT_CACHE_MAX_SIZE` 用于 `_enforce_agent_cache_cap`(gateway/run.py:23609、23623);`_AGENT_CACHE_IDLE_TTL_SECS` 用于空闲驱逐(gateway/run.py:23682);连接超时用于 gateway/run.py:6590、6606-6607;`_STALL_NOTIFY_SEND_TIMEOUT_SECONDS` 用于 stall watcher(gateway/run.py:12295);SSE 缓冲上限用于 gateway/run.py:24049;`_GATEWAY_HYGIENE_PLATFORM` 用于 hygiene agent 打标(gateway/run.py:16912)。

**设计理由与取舍**:Telegram 连接超时(180s)是普通平台(30s)的 6 倍,因为其冷启动要真跑一轮 getUpdates 才算 ready——用差异化超时换启动可靠性,代价是 Telegram 卡死要 3 分钟才暴露。

**重实现要点**:
1. 长驻进程的每级缓存都要同时有"数量上限 + 空闲 TTL"两条驱逐线;
2. 平台连接超时不搞一刀切,按"connect 返回前证明了什么"定预算;
3. 通知类 send 必须有独立小超时,失败留给下个 tick 重试,不阻塞 watcher 主循环。

---

## 噪声状态正则(90–123)

### 机制 3:`_TELEGRAM_NOISY_STATUS_RE` —— 聊天面不接收运维碎碎念

**场景/问题**:agent 的 status 回调流里混着压缩进度、重试、辅助模型失败等运维性文案。这些在 CLI 里是有用诊断,在 Telegram/Discord 等聊天窗口里是骚扰,且随措辞演化(如 #69332 改写了 auto-lower 提示)。

**实现**:一个大 alternation 正则,逐条枚举应"留在日志、不进聊天"的状态类别;对措辞变过的条目同时覆盖新旧两代;用 `", retrying"`/`"— compressing"` 锚点把手动 `/compress` 的成功反馈从匹配中排除。

路径:gateway/run.py:90-104 @ 863e313
```python
_TELEGRAM_NOISY_STATUS_RE = re.compile(
    r"("  # transient/auxiliary status that should stay in logs, not gateway chats
    r"auxiliary\s+.+\s+failed"
    r"|compression\s+summary\s+failed"
    r"|fallback\s+context\s+marker"
    r"|configured\s+compression\s+model\s+.+\s+failed"
    r"|no\s+auxiliary\s+llm\s+provider\s+configured"
    r"|auto-lowered\s+compression\s+threshold"
    # #69332 reworded the auto-lower notice to "Auto-lowered this session's
    # threshold to N tokens" — keep both generations covered.
    r"|auto-lowered\s+(?:this\s+)?session'?s?\s+threshold"
    r"|configured\s+auxiliary\s+compression\s+provider\s+.+\s+unavailable"
    r"|skipping\s+concurrent\s+compression"
    r"|compacting\s+context\s+[—-]\s+summarizing\s+earlier\s+conversation"
    r"|resumed\s+after\s+\d+s\s+idle\s+[—-]\s+compacting"
```

(其余分支到 123 行:preflight/pre-api 压缩、context too large 重试链、rate limited、max retries、stream drop、stale connections 等。)

**调用关系**:唯一消费者是 `_prepare_gateway_status_message`(gateway/run.py:738)。

**设计理由与取舍**:黑名单式过滤——只压已知噪声,未知新状态默认放行(宁多说不漏说)。代价是每次上游改措辞都要追着改正则;仓库的补救是机制 4 的"模板即措辞"派生。

**▲ 文档-代码冲突候选 1(命名漂移)**:常量名带 `_TELEGRAM_` 前缀,但实际适用于**所有**聊天平台——`_prepare_gateway_status_message` 对一切非 raw-text 平台生效(gateway/run.py:734-738),334 行注释也明说 #39293 已把 #28533 的 Telegram-only 过滤推广到全部聊天 gateway。命名是历史遗留,读代码时会误导作用域。

**重实现要点**:
1. 面向人的通道与面向程序的通道要在出口处统一分流,而不是在每个 emit 点各自判断;
2. 噪声过滤用黑名单(fail-open),安全过滤用白名单(fail-closed),两类不要混;
3. 上游措辞改版时保留旧 pattern("keep both generations covered"),否则旧版本回放/混布期间漏过滤;
4. 正则里写明每个分支的排除锚点为什么存在(防止后人"顺手简化"放进误杀)。

---

## hygiene 压缩冷却与恢复(126–262)

### 机制 4:gateway 侧压缩失败冷却梯子(#79624)

**场景/问题**:会话卫生(hygiene)压缩用的 summary 模型一直超时的会话,会以固定间隔永远重试(#79624)。agent 内部本有 60→300→900s 的绝对梯子(`ContextCompressor.record_timeout_failure`,agent/context_compressor.py:1975-1991),但 hygiene 每次跑都**新建**一个 `AIAgent` 并 `bind_session_state`,而 bind 会把内存计数器清零(agent/context_compressor.py:1645 `self._consecutive_timeout_failures = 0`),所以从 gateway 看那个梯子的连败数永远是 0,爬不上去。

**实现**:把连败计数搬到 gateway 的 `PersistentState`(gateway/session_state.py:169 `hygiene_failure_streak: int = 0`)上——它比 per-run agent 长寿。梯子是**乘法**梯(×1、×3、×9,作用在操作员配置的基数上),封顶 1 小时。

路径:gateway/run.py:126-132 @ 863e313
```python
_HYGIENE_COOLDOWN_LADDER_MULTIPLIERS = (1, 3, 9)
# Absolute ceiling on an escalated hygiene cooldown, mirroring
# _RECONNECT_BACKOFF_CAP above: with an operator-raised base the multiplier
# ladder alone would reach 9h (base 3600 -> 32400s), which is indistinguishable
# from "compaction silently switched off". 1h is well past the point where a
# retry is cheap and still recovers within a session.
_HYGIENE_COOLDOWN_MAX_SECONDS = 3600.0
```

路径:gateway/run.py:157-170 @ 863e313
```python
    streak = 1
    try:
        state = gateway._session_state(session_key).persistent
        state.hygiene_failure_streak += 1
        streak = state.hygiene_failure_streak
    except Exception as exc:
        # The caller uses the return value to record the cooldown, so an
        # escaping exception would mean NO cooldown at all (hot retry loop) —
        # strictly worse than no escalation.  Degrade to the base rung.
        logger.debug("hygiene failure streak update failed: %s", exc)
    multiplier = _HYGIENE_COOLDOWN_LADDER_MULTIPLIERS[
        min(streak, len(_HYGIENE_COOLDOWN_LADDER_MULTIPLIERS)) - 1
    ]
    return min(base_cooldown_seconds * multiplier, _HYGIENE_COOLDOWN_MAX_SECONDS)
```

细节:异常时降级为 `streak = 1`(基数一档)而非抛出——docstring 明说抛出意味着调用方记不了任何冷却,是"比不升级更糟"的热重试循环。注意 `logger` 直到 gateway/run.py:2416 才定义,这里能用是因为函数体运行时才解析名字。

**调用关系**:两个调用点都在 `_handle_message_with_agent` 的 hygiene 分支——超时路径 gateway/run.py:17040-17049,abort 路径 gateway/run.py:17264-17274;基数 `hygiene_failure_cooldown_seconds` 从压缩配置读入(gateway/run.py:16700-16707,负数表示禁用,调用点有 `>= 0` 门)。

**▲ 文档-代码冲突候选 2**:132 行注释说 "mirroring `_RECONNECT_BACKOFF_CAP` **above**",但该常量实际定义在 gateway/run.py:3662(`_RECONNECT_BACKOFF_CAP = 300`),在本注释**之后** 3500 行,且值也不同(300s vs 3600s)——"mirroring"指的是"同样设绝对上限"这个模式,不是同值;"above"是方位错误。

**设计理由与取舍**:乘法梯 vs 绝对梯:操作员调过基数(比如 3600s)时,绝对梯会把调优覆盖掉,乘法梯保留基数为第一档;代价是需要额外的绝对封顶,否则大基数 ×9 等于事实上关掉压缩。

**重实现要点**:
1. 退避计数器的生存期必须 ≥ 失败主体的生存期;per-run 对象上的计数器对"每次重建再跑"的任务永远是 0;
2. 操作员可调基数上的退避用乘法梯 + 绝对封顶,别用绝对梯覆盖调优;
3. 计数落库/升档失败时降级为最低档而不是抛异常——"无冷却"比"不升级"更糟;
4. 封顶值的选取标准写进注释:上限要小到"用户能区分'在退避'和'功能坏了'"。

### 机制 5:`_reset_hygiene_failure_streak` —— 只 peek 不创建

**场景/问题**:压缩成功后要清零连败;但 `_sessions` 条目永不驱逐,"写一个本来就是 0 的 0"不该顺手创建一条永久会话状态。

路径:gateway/run.py:173-184 @ 863e313
```python
def _reset_hygiene_failure_streak(gateway, session_key: str) -> None:
    """Clear the hygiene failure streak after a compression that reduced context.

    Peeks rather than get-or-creates: writing a 0 that is already 0 must not
    materialise a ``_sessions`` entry (those are never evicted).
    """
    try:
        state = gateway._peek_session_state(session_key)
        if state is not None:
            state.persistent.hygiene_failure_streak = 0
    except Exception as exc:
        logger.debug("hygiene failure streak reset failed: %s", exc)
```

**调用关系**:`_peek_session_state` 定义在 gateway/run.py:5841;调用点 gateway/run.py:17260-17262(仅在机制 6 判定"真恢复"之后)。

**重实现要点**:
1. 对"永不驱逐"的注册表,读路径一律 peek,get-or-create 只留给确实要写有效数据的路径;
2. 清零操作幂等 + 静默失败(debug 级日志)即可,不值得冒中断主流程的风险。

### 机制 6:`hygiene_compaction_recovered` —— "真恢复"三条件判定(#21301、#39548)

**场景/问题**:hygiene 跑完后要决定清不清连败。坑有二:(a) 压缩器的退化路径"既没 rotate 也没就地压实"(#21301)会**复用压缩前的计数**,只看数字会把 no-op 读成成功,每次卡死都清梯子(17245-17250 行调用点注释点名 #79624);(b) token 数一边可能是 provider 实报、一边永远是粗估(代码重的会话高估 30–50%),裸 `<` 比较既漏真赢也把噪声当赢。

**实现**:纯函数,三条件与:未 abort、确实改写了转写(rotated 或 in_place)、且经共享判定 `compression_made_progress` 判定实质缩小。

路径:gateway/run.py:222-228 @ 863e313
```python
    if aborted:
        return False
    if not (rotated or in_place):
        return False
    return compression_made_progress(
        msg_count, new_count, approx_tokens, new_tokens
    )
```

`compression_made_progress`(agent/turn_context.py:199-211)的语义:行数下降算进步(即使 token 估计持平),token 波动 <5% 不算(#39548 的实案:220→220 条、~288k→~183k tokens 在 1M 上下文模型上仍被误触发 auto-reset)。

**docstring 中的可验证断言**:197-204 行说本函数从 ~2000 行的 `_handle_message_with_agent` 里抽出,因为 AGENTS.md **点名本文件**禁止 source-reading 测试——已核实:AGENTS.md:1382 "### Never read source code in tests",AGENTS.md:1434 在同节点名 `gateway/run.py`。不构成冲突。

**调用关系**:gateway/run.py:17251-17262(判 True 才调机制 5 清零)。

**重实现要点**:
1. "成功"判定必须绑定**副作用发生**的证据(转写被改写),不能只信统计数字——退化路径常复用旧数字;
2. 进步判定抽成全仓唯一谓词共享(此处 `compression_made_progress`),防止各处 `<` 各自为政;
3. 精度不对等的两个量(实报 vs 粗估)比较时必须留噪声带;
4. 把判定从巨型方法抽成纯函数,是让"禁止读源码的测试策略"可执行的前提。

### 机制 7:`_record_hygiene_cooldown` —— 冷却落库复用会话内通道(#74136)

**场景/问题**:冷却存内存则 gateway 一重启就清零(#74136)。

**实现**:复用会话内压缩路径(agent/context_compressor.py)已有的 `compression_failure_cooldown_until` 列与 `record_compression_failure_cooldown` 方法;全程 getattr 探测、异常吞掉(诊断辅助功能不许影响主流程)。

路径:gateway/run.py:250-261 @ 863e313
```python
    import time as _time
    session_db = getattr(gateway, "_session_db", None)
    if session_db is None:
        return
    session_db = getattr(session_db, "_db", session_db)
    recorder = getattr(session_db, "record_compression_failure_cooldown", None)
    if recorder is None:
        return
    try:
        recorder(session_id, _time.time() + cooldown_seconds, error)
    except Exception as exc:
        logger.debug("session hygiene cooldown persist failed: %s", exc)
```

`error` 必传的原因(244-248 行 docstring):recorder **无条件**写 `compression_failure_error` 列,省略会把会话内路径记下的原因清成 NULL,而读方会把该原因展示给用户(冷却升到 1 小时后这点更要紧)。

**调用关系**:gateway/run.py:17040、17265(与机制 4 成对)。

**重实现要点**:
1. 冷却/退避这类"跨重启才有意义"的状态必须落盘,且**复用**既有 schema 而非另开列;
2. 复用别人的 recorder 前读清楚它的写语义(此处:无条件覆盖 error 列)——共享列的所有写方要么都带全字段,要么会互相清数据;
3. duck-typing(getattr 链)接依赖,让单测能用假对象驱动。

---

## 状态模板正则与进度通知开关(264–325)

### 机制 8:模板即措辞——`_status_template_to_regex` + 进度通知 opt-in(#69550、#52995)

**场景/问题**:#52995 允许用户 opt-in 接收**例行压缩进度**状态,但机制 3 的黑名单同时罩住了压缩进度与无关噪声(辅助失败、重试碎碎念)。需要在黑名单命中的集合里再精确辨认"哪些是压缩进度"——如果靠再抄一遍措辞,上游一改就静默失配。

**实现**:直接 import emit 点使用的**模板常量本身**(agent/conversation_compression.py 的 8 个 `*_STATUS_TEMPLATE`,见 gateway/run.py:50-59 导入),把字面文本 `re.escape`、把 `{field}` 占位符替换成 `[\d,]+`,编译成判别正则——措辞的唯一权威是常量,正则是派生物。

路径:gateway/run.py:264-274 @ 863e313
```python
def _status_template_to_regex(template: str) -> str:
    """Compile a compression status template constant into a regex source.

    Literal text is escaped verbatim (so wording drift in
    agent/conversation_compression.py cannot silently diverge from this
    matcher — the constants ARE the wording) and each ``{field}`` format
    placeholder is replaced with a numeric-ish pattern covering every value
    the emit sites format in (ints, ``{:,}`` thousands separators).
    """
    parts = re.split(r"\{[^{}]*\}", template)
    return r"[\d,]+".join(re.escape(part) for part in parts)
```

开关读取(gateway/run.py:304-325):`_gateway_compression_progress_notices_enabled` 读 raw YAML 的 `compression.progress_notices`,默认 False,truthy 集合 `{"true","1","yes","on"}`,任何读错保持沉默默认(fail-closed);"read live (mtime-cached)" 依赖 `_load_gateway_config`(定义在 gateway/run.py:3145,内部走 `hermes_cli.config.read_raw_config` 的 mtime 缓存),所以运行中改配置下一条状态即生效。

**调用关系**:`_COMPRESSION_PROGRESS_STATUS_RE`(gateway/run.py:286-301)与开关都只被 `_prepare_gateway_status_message` 消费(gateway/run.py:745-748)。

**设计理由与取舍**:与机制 3 的手抄黑名单相反,这里是**派生式**匹配——因为该门是白名单语义(放行哪些),漏配会放走噪声,必须与措辞源头强绑定。代价:占位符一律按数字匹配,若未来模板嵌入非数字字段会失配(当前 emit 点只格式化整数/千分位)。

**重实现要点**:
1. "对生成文本做二次识别"时,让识别器从**生成模板**编译而来,消灭双份措辞;
2. 放行类开关 fail-closed(读配置失败=保持默认沉默),过滤类黑名单 fail-open,方向要选对;
3. 占位符→模式的映射按 emit 点的实际 format 说明书写死并注释,而非泛化成 `.+`(会吃掉相邻文字);
4. 长驻进程读配置走 mtime 缓存,兼得"热生效"与"不每条状态都读盘"。

---

## raw-text 平台集合与出站脱敏(327–390、567–609)

### 机制 9:程序面/人面二分 `_GATEWAY_RAW_TEXT_PLATFORMS`(#28533→#39293)

**场景/问题**:CLI/TUI 诊断、API JSON、webhook 载荷需要原文;所有聊天面需要压噪 + 脱敏。#28533 只对 Telegram 做过滤,#39293 推广到全部聊天 gateway。

**实现**:白名单 frozenset,只有名单内的平台保留原文;未知/空平台按聊天面处理(fail-closed)。

路径:gateway/run.py:333-340 @ 863e313
```python
_GATEWAY_RAW_TEXT_PLATFORMS = frozenset(
    {"local", "api_server", "webhook", "msgraph_webhook"}
)


def _gateway_surface_passes_raw_text(platform: Any) -> bool:
    """True only for programmatic/local surfaces that must keep raw text."""
    return _gateway_platform_value(platform) in _GATEWAY_RAW_TEXT_PLATFORMS
```

`_gateway_platform_value`(gateway/run.py:447-449)把 enum 或裸字符串统一成小写字符串:`str(getattr(platform, "value", platform) or "").strip().lower()`。

**调用关系**:`_sanitize_gateway_final_response`(gateway/run.py:711)、`_prepare_gateway_status_message`(gateway/run.py:734)。

**重实现要点**:
1. 面的分类做成"程序面白名单",新平台默认落在受保护一侧;
2. 平台标识在入口归一化(enum/str/None 三态统一),后续全部按归一值比较。

### 机制 10:出站秘密脱敏——权威脱敏器 + 本地兜底双层(#23810)

**场景/问题**:provider 错误体、工具回显里可能带 API key,出聊天前必须脱敏;且启动横幅承诺 "chat responses are scrubbed before delivery",不能只盖 gateway 历史上认识的那几种 key。

**实现**:先委托全仓权威 `agent.redact.redact_sensitive_text`(定义于 agent/redact.py:659)且 `force=True`(即使用户关了 `security.redact_secrets` 也脱,与 `_redact_approval_command` 的 #23810 论证一致);import/执行失败时 fail-soft 落到本地 `_GATEWAY_SECRET_PATTERNS`(gateway/run.py:382-390:sk-、ghp/gho/ghu/ghs/ghr、xapp、xoxb/a/p/r/s、hf_、glpat、Bearer)第二遍兜底——两层叠加保证"历史上抓得到的永不回归"。

路径:gateway/run.py:582-593 @ 863e313
```python
    redacted = str(text or "")
    try:
        from agent.redact import redact_sensitive_text

        redacted = redact_sensitive_text(redacted, force=True)
    except Exception:
        # Fail-soft: fall back to the local pattern pass below rather than
        # letting a redactor import/error leak the raw text to chat.
        pass
    for pattern in _GATEWAY_SECRET_PATTERNS:
        redacted = pattern.sub(lambda m: (m.group(1) if m.lastindex else "") + "[REDACTED]", redacted)
    return redacted
```

姊妹函数 `_redact_approval_command`(gateway/run.py:596-609):审批提示由**原始命令串**构造,Tirith(危险命令审计器)只脱敏它自己的 findings,不脱命令本身,导致被标记的凭据会原样回显到聊天(#48456);故审批提示也过同一权威脱敏器。docstring 言明抽到模块级是因为调用点是深嵌套闭包无法直接驱动、需可单测。

**调用关系**:`_redact_gateway_user_facing_secrets` 被 gateway/run.py:719、737、4374、22362 调用;`_redact_approval_command` 被 gateway/run.py:5176 调用,并被其他模块 `from gateway.run import` 复用。

**重实现要点**:
1. 出站脱敏 = 权威实现 + 冻结的本地最小集兜底;兜底集只加不删,防权威实现回归;
2. 安全脱敏无视用户开关(`force=True`)的场景要单独论证并落注释/issue 号;
3. `Bearer <token>` 这类"保留前缀替换余部"的模式,用 `m.lastindex` 区分有无捕获组,一个 sub 回调通吃;
4. 审计器的输出脱敏≠输入脱敏:任何"把原始输入回显给人"的路径都要独立过一遍脱敏。

### 机制 11:provider 错误/策略/认证/限流四分类正则(343–380)

**实现**:四个分类正则:`_GATEWAY_PROVIDER_ERROR_RE`(343-355,错误前导词)、`_GATEWAY_PROVIDER_POLICY_RE`(357-370,policy/safety/moderation 词汇)、`_GATEWAY_AUTH_ERROR_RE`(372-375,认证失败/401)、`_GATEWAY_RATE_LIMIT_RE`(377-380,rate limit/429/quota)。后三者被机制 13 的 `_gateway_provider_error_reply` 消费(gateway/run.py:643、648、653)。

**▲ 文档-代码冲突候选 3(死代码)**:`_GATEWAY_PROVIDER_ERROR_RE`(gateway/run.py:343)在**全仓无任何引用**(含 tests;已 grep 验证仅定义行命中)。真正做"是否 provider 错误"判定的是 661 行的 `_GATEWAY_PROVIDER_ERROR_SHAPE_RE`(内容几乎相同但加了行首锚定)。前者是被 shape 版取代后遗留的孤儿常量。

路径:gateway/run.py:343-355 @ 863e313
```python
_GATEWAY_PROVIDER_ERROR_RE = re.compile(
    r"("  # infrastructure/provider error preambles, not ordinary assistant prose
    r"api\s+(?:call\s+)?failed"
    r"|provider\s+authentication\s+failed"
    r"|non-retryable\s+error"
    r"|rate\s+limited\s+after\s+\d+\s+retries"
    r"|error\s+code\s*:"
    r"|\bhttp\s*\d{3}\b"
    r"|incorrect\s+api\s+key"
    r"|invalid\s+api\s+key"
    r")",
    re.IGNORECASE,
)
```

**重实现要点**:
1. 替换正则时删旧常量,或至少标注 deprecated——两份近似正则并存必然漂移;
2. 错误分类的优先级(认证 > 策略 > 限流 > 兜底)要在消费方固定成 if 链,不靠正则互斥。

---

## Windows venv 导入修复(393–444)

### 机制 12:`_ensure_windows_gateway_venv_imports`

**场景/问题**:Windows 某些重启路径用 uv 基座的 `pythonw.exe`(避免 venv launcher 弹可见控制台)拉起 gateway:cwd/PYTHONPATH 能看到源码树,但看不到只装在 `venv/Lib/site-packages` 的可选包(典型:MCP SDK),MCP 工具注入就静默失效。

**实现**:仅 win32;候选 venv 取 `VIRTUAL_ENV` 环境变量与 `<project>/venv`,按 resolve 后小写去重;找到存在的 `Lib/site-packages` 后:(1) 项目根插到 `sys.path[0]`;(2) **用 `site.addsitedir` 而非裸 append**——pywin32(MCP SDK 在 Windows 的依赖)靠 `.pth` 处理暴露 `pywintypes`;(3) 再把 site-packages 从 addsitedir 落点挪到项目根之后的第 1/0 位,保证优先级;(4) 回写 `VIRTUAL_ENV` 与去重后的 `PYTHONPATH`,让**子进程**继承同样视野;首个成功候选即 return。

路径:gateway/run.py:427-444 @ 863e313
```python
        project_entry = str(project_root)
        site_entry = str(site_packages)
        if project_entry not in sys.path:
            sys.path.insert(0, project_entry)
        # addsitepackages() semantics matter here: pywin32, used by the MCP
        # SDK on Windows, relies on .pth processing to expose pywintypes.
        site.addsitedir(site_entry)
        if site_entry in sys.path:
            sys.path.remove(site_entry)
        insert_at = 1 if sys.path and sys.path[0] == project_entry else 0
        sys.path.insert(insert_at, site_entry)

        os.environ["VIRTUAL_ENV"] = str(resolved_venv)
        pythonpath = [project_entry, site_entry]
        if os.environ.get("PYTHONPATH"):
            pythonpath.append(os.environ["PYTHONPATH"])
        os.environ["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(pythonpath))
        return
```

**调用关系**:在 `start_gateway` 中、MCP 发现之前调用(gateway/run.py:26802)。

**重实现要点**:
1. 修补 `sys.path` 时用 `site.addsitedir` 触发 `.pth`,裸 insert 会漏掉 pywin32 这类靠 .pth 的包;
2. 修补进程内视野的同时回写 `VIRTUAL_ENV`/`PYTHONPATH`,否则子进程(MCP server)复现同一故障;
3. 路径去重要在 resolve + 大小写归一后做(Windows 大小写不敏感);
4. `dict.fromkeys` 是保序去重的标准写法,PYTHONPATH 拼接用它防重复膨胀。

---

## 平台小工具:归一化与 Discord 元数据(447–462)

### 机制 13(小):`_gateway_platform_value` / `_non_conversational_metadata`

前者见机制 9。后者(gateway/run.py:452-462)只对 Discord 平台在 metadata 里并入 `non_conversational: True` 标记生命周期/状态类发送,其他平台原样返回——Discord 适配器据此区分"对话消息"与"状态泡"。调用点遍布状态/生命周期发送路径(gateway/run.py:4928、20908、20935、21040、21223、24647、25058 等十余处)。样板级,一句话带过。

**重实现要点**:平台特有的发送语义用 metadata 标记而非分叉发送函数;标记函数对无关平台恒等返回,调用点可无脑包裹。

---

## hygiene 系统提示种子(465–487)

### 机制 14:`_seed_hygiene_system_prompt`

**场景/问题**:hygiene 跑压缩用的临时 agent 故意跳过 memory-provider 初始化;而压缩**允许持久化 system prompt**——若让这个"残缺"agent 重建 prompt,会把活会话已持久化 prompt 里的外部 provider 块洗掉。

**实现**:把会话行里存的 `system_prompt` 原样种进 `agent._cached_system_prompt`;取不到可用值就种空串。压缩要么保留该(不可用)值、要么用 hygiene 专属平台标记重建;真正的用户回合会用完整初始化的 provider 重建任一形态。返回 bool 表示是否种到了非空 prompt。

路径:gateway/run.py:479-486 @ 863e313
```python
    stored_prompt = ""
    if isinstance(session_row, dict):
        raw_prompt = session_row.get("system_prompt")
        if isinstance(raw_prompt, str) and raw_prompt.strip():
            stored_prompt = raw_prompt

    agent._cached_system_prompt = stored_prompt
    return bool(stored_prompt)
```

**调用关系**:gateway/run.py:16905(hygiene 路径);gateway/slash_commands.py:4129(手动 `/compress` 等价路径,4050 行导入)。

**重实现要点**:
1. 用降级组件替跑维护任务时,凡是维护任务**可能持久化**的派生物,都要先从持久层种入原值,防止降级视角覆盖完整视角;
2. "种空值 + 真回合重建"是安全兜底:让不可用状态显式存在,而不是让降级组件即兴生成。

---

## 瞬态网络错误识别与事件循环兜底(489–564)

### 机制 15:`_is_transient_network_error` + `_gateway_loop_exception_handler`(#31066、#31110)

**场景/问题**:Telegram 轮询的 `TimedOut`(或 PTB `NetworkError` 包着 `httpx.ConnectError`)从后台任务逃逸到事件循环,默认 handler 当致命错误,**杀掉整个 gateway 进程**(#31066/#31110)。这类错误定义上就是瞬态——下个轮询周期自愈。

**实现**:按**类名**(非 isinstance)匹配 13 个瞬态类名集合,沿 `__cause__ or __context__` 链最多走 12 层、以 `id()` 集合防环;loop 级 handler 对命中的错误记 WARNING(带完整 traceback 与任务名,保持可诊断),未命中的转交默认 handler(真 bug 仍然炸出来)。

路径:gateway/run.py:520-530 @ 863e313
```python
    while cur is not None and depth < 12:
        ident = id(cur)
        if ident in seen:
            break
        seen.add(ident)
        depth += 1
        name = type(cur).__name__
        if name in transient_class_names:
            return True
        cur = cur.__cause__ or cur.__context__
    return False
```

路径:gateway/run.py:546-564 @ 863e313
```python
    exc = context.get("exception")
    if exc is not None and _is_transient_network_error(exc):
        task = context.get("future") or context.get("task")
        task_name = ""
        if task is not None:
            try:
                task_name = task.get_name() if hasattr(task, "get_name") else repr(task)
            except Exception:
                task_name = repr(task)
        logger.warning(
            "Gateway swallowed transient network error from %s: %s: %s",
            task_name or "<unknown task>",
            type(exc).__name__,
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return
    # Fall back to the default handler for anything we don't recognise.
    loop.default_exception_handler(context)
```

**调用关系**:`start_gateway` 中 `loop.set_exception_handler(_gateway_loop_exception_handler)` 安装一次(gateway/run.py:26716)。

**设计理由与取舍**:按类名匹配是刻意的——telegram、httpx、aiohttp 各自的异常类都不必 import(有的平台包可能未安装);代价是同名异类会误吞,靠"只吞网络类命名"控制风险。深度 12 与 id-set 防的是异常链成环(`__context__` 可指回自身)。

**重实现要点**:
1. 长驻 asyncio 进程必须装 loop 级异常 handler,把"已知瞬态类"与"真 bug"分流,后者仍走默认路径;
2. 跨可选依赖识别异常用类名字符串集合,免 import;
3. 走 `__cause__/__context__` 链必须限深 + 防环;
4. 吞错误也要留全 traceback + 任务名,可诊断性不打折。

---

## 审批 fallback 文案(612–638)

### 机制 16:`_format_exec_approval_fallback` —— 按能力而非平台渲染

**场景/问题**:平台不支持按钮时,危险命令审批要降级成文本指令;不同场景(允许永久批准?smart-deny 覆写?)选项集合不同。

**实现**:命令截断 200 字符;`smart_denied` 换标题且强制只留"单次批准/拒绝";`allow_session`/`allow_permanent` 分层追加选项;选项拼成 ", …, or …" 英文并列。签名以能力布尔为参("Render the text fallback from approval capabilities, not platform names",gateway/run.py:621)。

路径:gateway/run.py:622-638 @ 863e313
```python
    cmd_preview = command[:200] + "..." if len(command) > 200 else command
    heading = "⚠️ **Dangerous command requires approval:**"
    if smart_denied:
        heading = "⚠️ **Smart DENY — owner override for one operation:**"

    choices = [f"Reply `{command_prefix}approve` to execute this one operation"]
    if not smart_denied and allow_session:
        choices.append(
            f"`{command_prefix}approve session` to approve this pattern for the session"
        )
        if allow_permanent:
            choices.append(f"`{command_prefix}approve always` to approve permanently")
    choices.append(f"`{command_prefix}deny` to cancel")
    return (
        f"{heading}\n```\n{cmd_preview}\n```\nReason: {description}\n\n"
        + ", ".join(choices[:-1]) + f", or {choices[-1]}."
    )
```

**调用关系**:gateway/run.py:5217(审批闭包内,命令先经 5176 行 `_redact_approval_command` 脱敏)。

**重实现要点**:
1. 降级 UI 按**能力矩阵**参数化,不按平台名 switch——新平台自动获得正确文案;
2. smart-deny(策略本要拒但允许 owner 单次覆写)必须收窄选项集,禁止顺手升级成永久批准;
3. 回显命令一律先截断 + 脱敏。

---

## provider 错误识别与替换文案(641–722)

### 机制 17:`_looks_like_gateway_provider_error` + `_gateway_provider_error_reply` + `_sanitize_gateway_final_response`(#7921)

**场景/问题**:重试耗尽后,原始 provider 错误体(HTTP body、request id、policy 文本、甚至凭据)会成为"最终回复"发到聊天;而助手正文里也可能正常地提到 "HTTP 404",不能误改写。

**实现**:两重启发式判"错误信封"——短(≤400 字符且 ≤4 个换行)且错误标记出现在**行首**(允许标点/符号前缀,`_GATEWAY_PROVIDER_ERROR_SHAPE_RE`,gateway/run.py:661-673 的 `^\s*(\W*\s*)?(...)`);命中后按认证→策略→限流→兜底的 if 链换成固定安全文案(gateway/run.py:641-658),原始细节留在日志。最终出口 `_sanitize_gateway_final_response`:raw 平台直通;`INTERRUPT_WAITING_FOR_MODEL_PREFIX` 开头的取消哨兵文本(agent/conversation_loop.py:100)对聊天面清空(ACP/TUI 已抑制,聊天面同样该抑制,#7921);否则先脱敏、再判错误信封替换。

路径:gateway/run.py:689-696 @ 863e313
```python
    if not text:
        return False
    body = str(text).strip()
    # Provider failure envelopes are short. Assistant answers that happen
    # to mention HTTP status codes ("HTTP 404 means...") tend to be longer.
    if len(body) > 400 or body.count("\n") > 4:
        return False
    return bool(_GATEWAY_PROVIDER_ERROR_SHAPE_RE.search(body))
```

路径:gateway/run.py:709-722 @ 863e313
```python
    if not text:
        return text
    if _gateway_surface_passes_raw_text(platform):
        return text

    # Cancellation metadata, not assistant prose. ACP/TUI already suppress
    # this sentinel; chat surfaces should too (#7921).
    if str(text).strip().startswith(INTERRUPT_WAITING_FOR_MODEL_PREFIX):
        return ""

    redacted = _redact_gateway_user_facing_secrets(str(text))
    if _looks_like_gateway_provider_error(redacted):
        return _gateway_provider_error_reply(redacted)
    return redacted
```

**调用关系**:gateway/run.py:5578(主回合最终回复)、17671(另一路回复出口)。

**▲ 文档-代码冲突候选 4(docstring 作用域过窄)**:`_gateway_provider_error_reply` docstring 写 "user-safe **Telegram** reply"(gateway/run.py:642),实际服务所有非 raw 聊天平台(经 `_sanitize_gateway_final_response`/`_prepare_gateway_status_message` 调用)。与候选 1 同源的 Telegram-first 历史遗留。

**设计理由与取舍**:长度阈值是可被构造绕过的启发式(助手写一条 ≤400 字符、行首是 "HTTP 500" 的正经回答会被误换文案),换来的是不必在错误产生点打结构化标记就能全线兜底。哨兵替换发生在脱敏**之前**判断、返回 `""`(空串让上层跳过发送)。

**重实现要点**:
1. 错误信封识别用"形状"(短 + 行首标记)而非仅关键词,压住助手正文误伤;
2. 替换文案固定四类,原始细节永远只进日志——聊天面文案里明说"细节在日志"给运维指路;
3. 取消/中断类哨兵文本要在所有面统一抑制,任何新面复用同一前缀常量;
4. 更根治的方案是在错误产生点带结构化 error 标记出栈;文本启发式是"改不动上游"时的出口层补救。

---

## 状态消息准备与投递(725–812)

### 机制 18:`_prepare_gateway_status_message` —— 状态出口三重闸

**实现**:空文本→None(不发);raw 平台直通;否则:脱敏 → 噪声黑名单(机制 3)命中时,仅当 opt-in 开 **且** 命中压缩进度白名单(机制 8)才放行,否则 None → provider 错误信封换文案(机制 17)。

路径:gateway/run.py:731-752 @ 863e313
```python
    text = str(message or "").strip()
    if not text:
        return None
    if _gateway_surface_passes_raw_text(platform):
        return text

    text = _redact_gateway_user_facing_secrets(text)
    if _TELEGRAM_NOISY_STATUS_RE.search(text):
        # Opt-in #52995: `compression.progress_notices: true` lets ROUTINE
        # compression progress statuses through to chat platforms. The
        # membership check is derived from the #69550 template constants, so
        # non-compression noise (aux failures, provider retry chatter, ...)
        # stays suppressed even when the gate is open. Default False keeps
        # the silent-by-design behavior byte-identical.
        if not (
            _gateway_compression_progress_notices_enabled()
            and _COMPRESSION_PROGRESS_STATUS_RE.search(text)
        ):
            return None
    if _looks_like_gateway_provider_error(text):
        return _gateway_provider_error_reply(text)
    return text
```

**调用关系**:状态回调 gateway/run.py:4364-4366,产物交给 4378 行的 `_send_or_update_status_coro`。

### 机制 19:`render_notice_line`(755–767)与 `_send_or_update_status_coro`(770–780,#30045)

`render_notice_line`:AgentNotice → 单行纯文本。glyph(⚠/•/✕/✓)已由 notice 策略烘进 text,TUI/CLI 都原样渲染,这里再加前缀会**双写**("⚠ ⚠ Credits 90% used");纯文本无 markdown 免去每平台转义;空/畸形 notice 降级为 `""` 不抛(它在 agent 回调路径上)。证据:gateway/run.py:767 `return str(getattr(notice, "text", "") or "").strip()`。调用点 gateway/run.py:4889。

`_send_or_update_status_coro`:#30045——支持 `send_or_update_status` 的适配器(目前 Telegram)对同一 `status_key` **编辑上一个气泡**而非追加刷屏;无此方法的适配器降级 `adapter.send`。

路径:gateway/run.py:777-780 @ 863e313
```python
    sender = getattr(adapter, "send_or_update_status", None)
    if callable(sender):
        return await sender(chat_id, status_key, content, metadata=metadata)
    return await adapter.send(chat_id, content, metadata=metadata)
```

### 机制 20:`_resolve_progress_thread_id`(783–812,#18859)

**场景/问题**:进度气泡该发到哪个 thread?两个坑:(a) Slack 配 `reply_in_thread=false` 时,进度消息不许自己开一个 thread,否则最终的平铺回复会被迫继承它;(b) 适配器用"消息自身 id 作 thread_id"合成会话键,这不是真 thread(#18859)。

**实现**:`reply_in_thread=False` 时:`source_thread_id == event_message_id`(合成键特征)视为无 thread,否则用真实 thread_id;`True` 时:有 thread_id 用之,无则 slack/mattermost 用消息 id 合成 thread,其他平台 None。

路径:gateway/run.py:800-812 @ 863e313
```python
    if not reply_in_thread:
        if (
            source_thread_id
            and event_message_id
            and str(source_thread_id) == str(event_message_id)
        ):
            return None
        return str(source_thread_id) if source_thread_id else None
    if source_thread_id:
        return str(source_thread_id)
    if platform_key in {"slack", "mattermost"} and event_message_id:
        return str(event_message_id)
    return None
```

**调用关系**:gateway/run.py:24611。

**机制 18–20 重实现要点**:
1. 状态出口做成单一函数管道(过滤→脱敏→改写),所有平台回调只许走它;
2. 通知渲染层不重复叠加级别符号——"谁烘进文本,谁负责唯一性"要定约;
3. 进度类消息用 update-in-place 能力探测 + send 降级,而非平台 if;
4. "会话键复用了 thread 字段"的适配器约定必须在消费端识别合成值,否则派生行为(自动开 thread)串味。

---

## display 布尔解析与 Telegram 命令名(815–883)

### 机制 21:`_resolve_gateway_display_bool` —— 平台级显式 opt-in 门

**场景/问题**:某些 display 特性暴露的是助手草稿而非成品输出;对 Mattermost 这类高噪声 thread 平台,全局开关太粗,必须 `display.platforms.<platform>.<setting>` 显式点名才生效。

**实现**:先查当前平台是否在 `require_platform_override_for` 集合且缺平台级覆盖(`_has_platform_display_override`,gateway/run.py:815-824,逐层 isinstance 校验 dict)→ 是则强制 False;否则委托 `gateway.display_config.resolve_display_setting`(gateway/display_config.py:187),对返回值做 bool/字符串 truthy(`{"true","yes","1","on"}`)/None→default 的三态归一。

路径:gateway/run.py:843-863 @ 863e313
```python
    current_platform = _gateway_platform_value(platform or platform_key)
    platform_only = {
        _gateway_platform_value(candidate)
        for candidate in (require_platform_override_for or set())
    }
    if (
        current_platform in platform_only
        and not _has_platform_display_override(user_config, platform_key, setting)
    ):
        return False

    from gateway.display_config import resolve_display_setting

    value = resolve_display_setting(user_config, platform_key, setting, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "on"}
    if value is None:
        return bool(default)
    return bool(value)
```

**调用关系**:gateway/run.py:17711(`_show_reasoning_effective` 等 display 决策)。

### 机制 22:`_telegramize_command_mentions`(866–883)

**场景/问题**:Telegram Bot API 命令名只允许小写字母/数字/下划线;帮助文本里的 `/someCommand` 提及在 Telegram 端要保持可点击。

**实现**:仅 `platform == "telegram"` 时,用 `_TELEGRAM_COMMAND_MENTION_RE`(gateway/run.py:87,负向后顾 `(?<![\w:/])` 排除 URL/路径中的斜杠)找出命令提及,交 `hermes_cli.commands._sanitize_telegram_name`(hermes_cli/commands.py:797)清洗;清洗为空则保留原文。

**调用关系**:本文件内无调用;被 gateway/slash_commands.py:1642、1652 `from gateway.run import` 后使用(1646、1666 行调用)——帮助文本渲染路径。

**重实现要点**:
1. "草稿类"显示特性用**双钥匙**:全局开关 + 平台点名,缺一不发;
2. 配置值的 bool 归一(bool/str/None/其他)集中一处,别在调用点各写各的 truthy;
3. 平台命名法规约(如 Telegram 命令字符集)的改写只在目标平台分支做,且与命令注册用同一 sanitize 函数,保证提及与注册名一致。

---

## auto-continue 新鲜度窗口与时间戳强转(886–1054)

### 机制 23:`_coerce_gateway_timestamp` + `_is_fresh_gateway_interruption`

**场景/问题**:gateway 重启后,残留的 resume_pending 标记或 tool-tail(最后一条持久化消息是没被回复的工具结果)会触发 auto-continue;若中断是**陈年旧事**,用户下一条消息开新工作时会诡异地复活旧任务。判"新鲜"的信号统一为**转写最后一行的时间戳**(两种 auto-continue 情形共用一个信号,替代原先两套发散逻辑;见 gateway/run.py:890-897 注释)。默认窗口 1 小时 = `agent.gateway_timeout` 默认 30 分钟 + 运行余量(gateway/run.py:899-904)。

**实现**:`_coerce_gateway_timestamp`(gateway/run.py:915-946)接受 datetime / epoch 秒 / epoch 毫秒(>10_000_000_000,即超过 2286 年才当毫秒)/ ISO-8601(含尾 Z)/ 数字字符串,bool 显式排除(是 int 子类),解析失败返回 None。`_is_fresh_gateway_interruption`(gateway/run.py:1028-1054):窗口 ≤0 → 恒新鲜(用户 opt-out);时间戳解析不出 → 恒新鲜(兼容无时间戳的老转写与测试脚手架);否则 `now - ts <= window`。

路径:gateway/run.py:928-946 @ 863e313
```python
    if isinstance(value, bool):  # bool is a subclass of int — skip it
        return None
    if isinstance(value, (int, float)):
        # Some platform events use milliseconds; Hermes state rows use seconds.
        return float(value) / 1000.0 if float(value) > 10_000_000_000 else float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            numeric = float(text)
            return numeric / 1000.0 if numeric > 10_000_000_000 else numeric
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None
```

**调用关系**:`_is_fresh_gateway_interruption` 在 gateway/run.py:5276(tool-tail 判定,配 1469-1491 行 `_last_transcript_timestamp`)与 5303(resume 标记判定)使用。窗口值经 `_auto_continue_freshness_window`(gateway/run.py:949-964)薄包装取自 gateway/session.py:40 的 `auto_continue_freshness_window`(单一权威,与路由期 zombie 门共享);包装保留在 run.py 只为既有调用点/测试 patch 兼容。env `HERMES_AUTO_CONTINUE_FRESHNESS` 由启动桥接写入(gateway/run.py:2186-2187,段外)。

**设计理由与取舍**:未知时间戳按"新鲜"处理是向后兼容优先——宁可偶尔复活旧任务,不静默丢弃合法恢复;opt-out 语义(非正值=恒新鲜)复原修复前行为,给不满新门的用户退路。

### 机制 24:`_startup_restore_drain_timeout_secs`(967–997)+ `_float_env`(1000–1012)

**场景/问题**:启动恢复期间 gateway 把**所有**入站消息排队(`_queue_startup_restore_event`),闸门由 `_finish_startup_restore` 等 boot auto-resume 回合结束后才开——一个病态长的恢复回合曾把**每个频道**的入站都压住没人应答。

**实现**:给这个等待加上限(默认 30s,`HERMES_STARTUP_RESTORE_DRAIN_TIMEOUT` 可覆盖,非正值恢复"永远等")。超时放闸是安全的:防重复 agent 不靠等待——`_schedule_resume_pending_sessions` **同步**占住每个会话的 `_running_agents` 槽(在闸门逻辑运行前),放闸后 drain 出的消息只会排在该槽后面,不会起第二个 agent(gateway/run.py:979-984 docstring)。`_float_env` 是通用的"env 读 float、typo/空回退默认"工具——配置错(`HERMES_AGENT_TIMEOUT=abc`)不许炸 gateway。

路径:gateway/run.py:991-997 @ 863e313
```python
    raw = os.environ.get("HERMES_STARTUP_RESTORE_DRAIN_TIMEOUT")
    if raw is None or raw == "":
        return float(_STARTUP_RESTORE_DRAIN_TIMEOUT_SECS_DEFAULT)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(_STARTUP_RESTORE_DRAIN_TIMEOUT_SECS_DEFAULT)
```

**调用关系**:drain timeout 用于 gateway/run.py:10286;`_float_env` 用于 12106、14709、16588、24968、25118、25120。

**机制 23–24 重实现要点**:
1. 恢复类自动行为必须有新鲜度门,信号选"转写最后活动时间"这类单一事实,而不是给每种恢复情形各发明一个;
2. 时间戳强转要显式处理 bool-是-int 陷阱与秒/毫秒歧义(用天文数量级阈值判别);
3. 未知/缺失时间戳的默认方向按"哪种误判更可逆"选(此处:误恢复可被用户打断,误丢弃不可);
4. 全局启动闸门必须有超时,且**正确性不依赖闸门**(并发安全靠同步占槽),闸门只管延迟;
5. 所有 env 数值读取统一走"解析失败回默认"的工具函数,配置 typo 永不致崩。

---

## hygiene provenance 戳(1015–1025)

### 机制 25(小):`_stamp_hygiene_compression_provenance`

对 hygiene agent 调 `agent._touch_activity(desc, provenance=...)` 记活动来源,异常仅 debug 日志——纯 best-effort 观测。调用点 gateway/run.py:17053(超时)、17278(abort),传入 `ActivityProvenance.AGENT_COMPRESSION_TIMEOUT` 等枚举。样板级。

**重实现要点**:观测/审计戳一律 best-effort 包裹,失败降级为 debug 日志,绝不反噬主流程。

---

## resume 恢复注记(1057–1123)

### 机制 26:`build_resume_recovery_note`(#57056)

**场景/问题**:中断回合恢复时要给模型一段系统注记。三种情形指令必须不同:(a) 用户带着新消息回来——先答新消息,别碰历史里的旧活;(b) 启动自动恢复且平台有人(interactive)——报告"已恢复"并问下一步;(c) **非交互**事件平台(webhook/API server,适配器 `interactive_resume = False`)——没人会回答提问,"已恢复,想做什么?"会把任务静默丢在一句没人看的致意后面(#57056),必须命令模型直接把中断的工作跑完。

**实现**:reason(`restart_timeout`/`shutdown_timeout`/其他)→措辞;(message, interactive) 二维选 guidance;统一前缀强调"历史里的 restart/shutdown 命令已经跑过,不许重跑/验证"。尾部指令也分叉:交互情形"跳过全部未完成旧活";非交互情形"从第一个没有记录结果的步骤续跑,已有结果的不重跑"。

路径:gateway/run.py:1104-1123 @ 863e313
```python
    else:
        resume_guidance = (
            "No user is present on this non-interactive platform, "
            "so do NOT emit a 'session restored' acknowledgement "
            "or ask questions. Review the conversation history and "
            "CONTINUE the interrupted task to completion."
        )
        tail_guidance = (
            "Do NOT re-run tool calls whose results already "
            "appear in the history — resume from the first step "
            "that has no recorded result."
        )
    return (
        f"[System note: The previous turn was interrupted by "
        f"{reason_phrase}; the gateway is now back online. "
        f"Any restart/shutdown command in the history has already "
        f"run — do NOT re-execute or verify it. {resume_guidance} "
        f"{tail_guidance}]"
        + (f"\n\n{message}" if message else "")
    )
```

**调用关系**:gateway/run.py:5333(带新消息情形)、5376(启动自动恢复情形)。产物以 `[System note: ...]` 前缀持久化——正是机制 30 的剥离目标(注意:本函数前缀是 "The previous turn was interrupted",而剥离器匹配 "Your previous turn"/"A new message" 两种**旧版**前缀,见下文冲突候选 6)。

**重实现要点**:
1. 恢复注记按"平台有没有人"分叉:有人→报告+提问,没人→直接续跑;这是事件驱动 agent 的关键区分;
2. 显式否定句("已经跑过,不许重跑")防模型复读历史里的危险命令,比只给正向指令可靠;
3. 续跑锚点用"第一个无记录结果的步骤",与转写事实绑定,而非让模型自由回忆进度。

---

## 重放字段白名单与 `_build_replay_entry`(1126–1227)

### 机制 27:`_ASSISTANT_REPLAY_FIELDS` —— CLI/gateway 重放行为对齐(PR #2974 及其回归)

**场景/问题**:gateway 从 DB 重放转写时,纯文本 assistant 行(无 tool_calls)只带 role/content 就丢了 reasoning 相关字段。PR #2974(schema v6)保了 3 个字段,后来 DB 又加了 `reasoning_content`/`codex_reasoning_items`/`codex_message_items`/`finish_reason` 但白名单**没同步扩**——多轮 reasoning 连续性、prefix-cache 命中、provider 回显要求在 gateway 上静默劣化,CLI 却正常(gateway/run.py:1130-1136 注释)。

**实现**:6 字段 tuple 白名单(gateway/run.py:1154-1161),每字段为何必须回放在 1137-1153 注释逐条交代(如 `codex_message_items` 引 OpenAI 文档 "preserve and resend phase on all assistant messages";`reasoning_details` 是 OpenRouter/Anthropic 的加密续链数据)。

### 机制 28:`_build_replay_entry` —— 空值语义与 api_content sidecar

**实现要点一(空值)**:多数字段 falsy 即丢(沿 #2974);唯 `reasoning_content` 例外——空串是 DeepSeek/Kimi thinking 模式的**有效哨兵**,`_copy_reasoning_content_for_api` 会把它升格为单空格;丢掉它下一轮就完全不发 `reasoning_content`,严格 thinking provider 直接 HTTP 400(gateway/run.py:1186-1191 docstring)。

**实现要点二(api_content sidecar)**:persist-what-you-send——转发上次真正发给 API 的字节,让请求前缀跨轮字节稳定(prompt cache);但**仅当本重放管道没改写 content**(时间戳注入、auto-continue 剥离、mirror 前缀都算改写)时才转发:管道决定要回放不同字节时,再发旧 sidecar 会把刚剥掉的噪声原样带回。丢 sidecar 只损一个 cache 边界;重发被剥噪声是行为回归。

路径:gateway/run.py:1203-1227 @ 863e313
```python
    _sidecar = msg.get("api_content")
    if (
        role in ("user", "assistant")
        and isinstance(_sidecar, str)
        and _sidecar
        and content == msg.get("content")
    ):
        entry["api_content"] = _sidecar
    if role == "assistant":
        for _rkey in _ASSISTANT_REPLAY_FIELDS:
            if _rkey not in msg:
                continue
            _rval = msg.get(_rkey)
            if _rkey == "reasoning_content":
                # Preserve empty-string sentinel for thinking-mode replay.
                if _rval is None:
                    continue
            elif not _rval:
                continue
            entry[_rkey] = _rval
    if preserve_timestamp:
        ts = msg.get("timestamp")
        if ts:
            entry["timestamp"] = ts
    return entry
```

`preserve_timestamp` 仅 user 行需要:agent/replay_cleanup.py 的陈旧危险确认剥离器要读它判过期;assistant/tool 行的剥离器看的是 tool_calls 结构不看时间戳(gateway/run.py:1176-1182)。

**调用关系**:唯一调用点 gateway/run.py:1394(`_build_gateway_agent_history` 内,`preserve_timestamp=(role == "user")`)。从 `run_sync` 闭包抽出以便白名单可独立单测(1173-1174)。

**重实现要点**:
1. DB schema 加字段时,**所有重放/序列化白名单是同一变更的一部分**——用共享常量+单测钉住,防"加列忘加名单";
2. 区分"falsy=无信息"与"空值=哨兵"的字段,逐字段写明空值语义;
3. persist-what-you-send 的 sidecar 只在"内容未被管道改写"时回放,改写即放弃(宁付一次 cache miss,不回灌已剥噪声);
4. 时间戳等元数据是否随重放保留,以下游消费者(清洗器)的需求为准,逐 role 决定。

---

## Telegram 观察上下文(1230–1246、1443–1466)

### 机制 29:observe-unmentioned 聊天记录不当作用户回合重放

**场景/问题**:Telegram 群"观察未提及消息"模式会把 bot 没被 @ 的群聊持久化,供日后 @提及 时参考。这些行若按普通 user 回合重放,一句弱唤醒(`@bot cambio`)就会让模型把陈年群聊当作待办工单。

**实现**:三件套。(1) 适配器给此类回合打 channel prompt 标记,`_uses_telegram_observed_group_context`(gateway/run.py:1235-1246)检测 `"observed Telegram group context"` 子串,保持 run 路径判定显式可单测;(2) `_build_gateway_agent_history` 把 `observed` 标记的 user 行**摘出** history、汇成字符串(见机制 32);(3) `_wrap_current_message_with_observed_context`(gateway/run.py:1443-1466)把它作为 **API-only** 前缀包在当前消息上,带两个显式标头分隔"仅供参考的旁听内容"与"当前被点名消息"。

路径:gateway/run.py:1230-1232 @ 863e313
```python
_TELEGRAM_OBSERVED_CONTEXT_PROMPT_MARKER = "observed Telegram group context"
_OBSERVED_GROUP_CONTEXT_HEADER = "[Observed Telegram group context - context only, not requests]"
_CURRENT_ADDRESSED_MESSAGE_HEADER = "[Current addressed message - answer only this unless it explicitly asks you to use the observed context]"
```

路径:gateway/run.py:1449-1464 @ 863e313
```python
    prefix = (
        f"{_OBSERVED_GROUP_CONTEXT_HEADER}\n"
        f"{observed_context}\n\n"
        f"{_CURRENT_ADDRESSED_MESSAGE_HEADER}\n"
    )

    if isinstance(message, str):
        return f"{prefix}{message}"

    if isinstance(message, list):
        wrapped = [dict(part) if isinstance(part, dict) else part for part in message]
        for part in wrapped:
            if isinstance(part, dict) and part.get("type") == "text":
                part["text"] = f"{prefix}{part.get('text', '')}"
                return wrapped
        return [{"type": "text", "text": prefix.rstrip()}] + wrapped

    return message
```

多模态列表消息:浅拷贝各 part,前缀注进**第一个** text part;没有 text part 就前插一个独立 text part。

**调用关系**:检测在 gateway/run.py:1343;包装在 5419(`_api_run_message`——只影响发给 API 的消息,持久化的用户消息保持原样)。docstring(1326-1329)点明动机:留在 conversation_history 会被 consecutive-user 修复合并进活回合,再被 `history_offset` 挡在持久化之外。

**重实现要点**:
1. "旁听内容"必须与"指令内容"在 API 消息层显式分层,并用标头明说旁听内容不是请求;
2. 分层做成 API-only 包装,持久层保留原始结构,重放时重新决定呈现;
3. 多模态注入选定第一个 text part,浅拷贝防止污染原消息对象;
4. 检测函数抽出来单测,不要把子串判断埋在 2000 行方法里。

---

## Slack 忽略频道兜底(1249–1293)

### 机制 30:runner 级 Slack 黑名单二道闸(#46925)

**场景/问题**:Slack 适配器有第一道 drop,但未来代码路径/测试钩子/畸形事件/陈旧适配器实例可能绕过它;被忽略频道一旦漏进来,会触达 auth、配对、会话、home-channel prompt 全管线。

**实现**:`_csv_or_list_to_set`(gateway/run.py:1249-1258)归一 list 或逗号串;`_slack_ignored_channels_from_gateway_config`(1261-1279)先读 `PlatformConfig.extra["ignored_channels"]`,None 再落 `SLACK_IGNORED_CHANNELS` env——因为顶层 `slack.ignored_channels` 走插件的 YAML→env 桥而非 extra(#46925);`_slack_parent_channel_id`(1282-1286)从 `channel:thread` 复合 id 取父频道;`_is_slack_ignored_channel`(1289-1293)支持 `"*"` 通配全禁。

路径:gateway/run.py:1289-1293 @ 863e313
```python
def _is_slack_ignored_channel(config: Any, chat_id: Any) -> bool:
    """Check the generic Slack gateway blacklist for channel or thread IDs."""
    channel_id = _slack_parent_channel_id(chat_id)
    ignored = _slack_ignored_channels_from_gateway_config(config)
    return bool(channel_id and ("*" in ignored or channel_id in ignored))
```

**调用关系**:gateway/run.py:13896、14373(通用分发路径上的守卫)。docstring 明说这是**故意重复**的 fail-safe(1264-1268)。

**重实现要点**:
1. 安全过滤在信任边界两侧各设一道(适配器 + runner),并注明重复是故意的,防止后人"去重";
2. 同一配置项的多种落点(extra vs env 桥)要在读取端全部覆盖并写明为什么;
3. thread-scoped 复合 id 判黑名单要归约到父资源。

---

## 消息时间戳开关与历史重放构建(1296–1440)

### 机制 31:`_message_timestamps_enabled`(1296–1313)

`gateway.message_timestamps.enabled` 默认 OFF——给每条用户消息注 `[Tue 2026-04-28 13:40:53 CEST]` 前缀会改变所有 gateway 用户的模型输入,必须显式 opt-in;兼容 `message_timestamps: true` 裸捷径。调用点:gateway/run.py:5103(重放注入)、17500(另一路)。

### 机制 32:`_build_gateway_agent_history` —— 转写→重放消息的总装线(1316–1418)

**场景/问题**:DB 转写行到 agent 可用历史之间要过一整套清洗:元数据行剔除、system 行剔除(agent 自建 system prompt)、时间戳注入、observed 行分流、工具消息保真、auto-continue 噪声剥离、mirror 标注、三道尾部清洗。

**实现(逐步)**:
- 跳过 `session_meta` 与 `system` 行(1352-1357);
- opt-in 时 user 行 content 经 `render_user_content_with_timestamp`(gateway/message_timestamps.py:114)注时间戳(1360-1361);
- observed user 行分流到 `observed_group_context` 列表(1362-1364,机制 29);
- 带 `tool_calls`/`tool_call_id`/role=tool 的富消息整体透传,仅剥 `timestamp`/`observed` 两键——API 必须看到合法的 assistant→tool 序列(1368-1374);
- 普通文本:user 行先 `_strip_auto_continue_noise`(剥后为空则整行丢),mirror 行加 `[Delivered from <src>]` 前缀,最后 `_build_replay_entry`(机制 28)(1381-1395);
- 三道尾部清洗,全部来自 agent/replay_cleanup.py(单一实现,messaging gateway 与 TUI/WebUI gateway 共用;导入在 gateway/run.py:1512-1516,函数定义于 agent/replay_cleanup.py:42、120、255)。

路径:gateway/run.py:1397-1418 @ 863e313
```python
    # Strip interrupted tool-call tails so the LLM doesn't re-execute
    # tools that were killed mid-flight.
    agent_history = strip_interrupted_tool_tails(agent_history)

    # Strip a dangling assistant(tool_calls) tail with no tool answers —
    # the signature of a SIGKILL mid-tool-call (e.g. the tool itself ran
    # `docker restart`/`kill` and took the gateway down before the result
    # was persisted). Without this the model re-issues the unanswered call
    # on resume and loops the restart forever (#49201).
    agent_history = strip_dangling_tool_call_tail(agent_history)

    # Strip stale dangerous-confirmation text in user messages (#59607).
    # A high-risk confirmation phrase (e.g. "confirm forced restart") that
    # is older than the expiry window must not be replayed to the model,
    # otherwise an unrelated follow-up message can be interpreted as a
    # fresh confirmation and trigger the destructive action a second time.
    agent_history = strip_stale_dangerous_confirmations(
        agent_history, now=time.time()
    )

    observed_context = "\n".join(observed_group_context).strip() or None
    return agent_history, observed_context
```

三道清洗对应三类事故:工具被杀中途→别重跑;SIGKILL 打断 tool-call(工具自己跑了 `docker restart` 把 gateway 弄死,结果没落盘)→模型恢复后重发未回应的 call,**无限重启循环**(#49201);过期的危险确认语("confirm forced restart",#59607)→无关后续消息被解读成新确认,毁灭性操作跑第二次。

**调用关系**:gateway/run.py:5100-5103 调用;返回的 observed_context 由 5419 行包装进 API 消息。

### 机制 33:`_select_cached_agent_history` —— FTS 写坏时保活转写(#50502)

**场景/问题**:FTS5 触发器损坏时消息写库**静默失败**,下一轮从盘上读回的是变短/空的历史;而缓存的 `AIAgent` 内存里 `_session_messages` 还是全的。用短的持久副本覆盖活转写=同会话即时失忆。

**实现**:活转写是 list 且**严格更长**才选它(拷贝返回);否则用持久副本。

路径:gateway/run.py:1438-1440 @ 863e313
```python
    if isinstance(live_history, list) and len(live_history) > len(persisted_history):
        return list(live_history)
    return persisted_history
```

**调用关系**:gateway/run.py:5114(注意 5125 行注释:选中活转写后仍会再过 `_build_gateway_agent_history` 的清洗管道)。

**取舍**:长度是粗糙代理——活副本更长也可能是"持久层刚被合法压缩截短",此时保活副本会回退压缩;仓库押注"写路径静默失败"比"读放大"更常见更致命。

### 机制 34:`_last_transcript_timestamp`(1469–1491)

从尾部找**第一条可用行**(跳过 `session_meta`/`system`)的 timestamp;该行没有 timestamp 即返回 None(遗留转写),**不再继续向前找**——让调用方走 legacy-fresh 路径。调用点 gateway/run.py:5277(喂给机制 23)。

**机制 31–34 重实现要点**:
1. 重放构建做成单函数管道,顺序固定:行级过滤→行级改写→整体尾部清洗;清洗器全仓单实现共享;
2. 富工具消息透传时只剥自家元数据键,不碰 API 结构字段;
3. "危险文本过期"(确认语、恢复注记)是重放清洗的一等需求,与"结构修复"并列;
4. 内存副本 vs 持久副本冲突时,选择规则要简单可述("严格更长者胜")并注明误差方向;
5. 尾行时间戳的"找到无戳行即停"语义防止跨行借用旧时间戳造成假新鲜/假陈旧。

---

## auto-continue 噪声剥离(1505–1550)

### 机制 35:`_is_auto_continue_noise` / `_strip_auto_continue_noise`

**场景/问题**:老版 gateway 把恢复注记直接**前置拼接**在用户消息上持久化;重放这些行会把"请继续之前的工作"当成新指令,造成被打断长任务的无限重执行循环(gateway/run.py:1376-1380 注释)。

**实现**:识别两个已知前缀;剥离时循环剥**一个或多个**连续注记(取第一个 `]` 为界),保留其后的真实用户文本;找不到闭合 `]` 则整条判空。

路径:gateway/run.py:1519-1550 @ 863e313(节选)
```python
_AUTO_CONTINUE_NOTE_PREFIX = "[System note: Your previous turn"
_AUTO_CONTINUE_FALLBACK_PREFIX = "[System note: A new message"
```
```python
    if not _is_auto_continue_noise(content):
        return content
    text = str(content)
    while _is_auto_continue_noise(text):
        end = text.find("]")
        if end < 0:
            return ""
        text = text[end + 1 :].lstrip()
    return text
```

**调用关系**:gateway/run.py:1382(机制 32 管道内)。

**▲ 文档-代码冲突候选 5(前缀集合与当前生成器脱节)**:剥离器只认 `"[System note: Your previous turn"` 与 `"[System note: A new message"` 两个**旧版**前缀;而当前 `build_resume_recovery_note`(机制 26)生成的是 `"[System note: The previous turn was interrupted..."`(gateway/run.py:1117),**不在**剥离集合内。这自洽的前提是:新版注记不再拼进持久化的用户消息(1536-1540 行 docstring 说明剥离目标是 "Older gateway builds" 的持久化产物;5333/5376 行的新注记如何持久化在段外)。若新版注记仍以用户行落库,则重放时不会被剥——留待段外(`ctx.message` 持久化路径)核实定案。

**重实现要点**:
1. 合成注记要么不落用户转写、要么带机器可识别前缀 + 配套剥离器,二者是一个决定;
2. 剥离器处理"多个连续注记"与"无闭合符"两个边界;
3. 前缀常量与生成器放同一文件同一节,改一处必见另一处(本仓库恰未做到,见冲突候选 5)。

---

## 媒体标签收集(1494–1503、1552–1715)

### 机制 36:auto-append 媒体的双层守卫(#16721、#34608、#160、#46627)

**场景/问题**:工具产出的可交付媒体(TTS 音频、生成图)若模型在最终回复里忘了写 `MEDIA:` 标签,就不会投递;但文档/日志/搜索结果里会出现**示例性** `MEDIA:/absolute/path/to/file` 字符串(#16721),盲扫会把示例当附件发出;旧回合的工具结果还留在消息列表里,会泄漏到后续纯文本回复上(#34608)。

**实现**:
- **第一层:生产者工具白名单** `_AUTO_APPEND_MEDIA_TOOL_NAMES`(gateway/run.py:1498-1503:text_to_speech、text_to_speech_tool、image_generate、bfl_flux3_get_result)——先由 assistant 行的 tool_calls 建 `call_id→tool_name` 映射,只扫这些工具的 tool 结果;
- **第二层:扩展名锚定正则** `_TOOL_MEDIA_RE`(gateway/run.py:1564-1570)——路径必须以盘符/`/`/`~/` 开头且以已知可交付扩展名结尾,散文里裸 `MEDIA:` 永不命中;
- **当前回合隔离**:只扫 `messages[history_offset:]`;但压缩可能把列表改写到比 history_offset 还短,此时边界不可信,回退全量扫描 + 靠 `history_media_paths` 去重(#160 的压缩安全行为);
- **JSON 载荷工具**:image_generate 返回 `{"success": true, "image": "/abs/path.png"}` 而非 MEDIA 标签,按 `_JSON_MEDIA_TOOL_PATH_FIELDS = ("host_image", "image", "agent_visible_image")`(gateway/run.py:1557)顺序取第一个通过 `fullmatch` 校验且未投递过的路径;
- 结果中发现 `[[audio_as_voice]]` 指令则置 voice 标志。

路径:gateway/run.py:1596-1613 @ 863e313
```python
    history_media_paths = history_media_paths or set()
    # Only trust the slice boundary when the message list still contains the
    # full history prefix. Otherwise scan everything (compression-safe fallback).
    if history_offset and len(messages) >= history_offset:
        new_messages = messages[history_offset:]
    else:
        new_messages = messages

    tool_name_by_call_id: Dict[str, str] = {}
    for msg in new_messages:
        if msg.get("role") != "assistant":
            continue
        for call in msg.get("tool_calls") or []:
            call_id = call.get("id") or call.get("call_id")
            fn = call.get("function") or {}
            name = str(fn.get("name") or call.get("name") or "")
            if call_id and name:
                tool_name_by_call_id[str(call_id)] = name
```

**▲ 文档-代码冲突候选 6(docstring 例举过窄)**:`_collect_auto_append_media_tags` docstring 写 "only tools that intentionally emit deliverable artifacts **(TTS)** are eligible"(gateway/run.py:1582-1583),但白名单实际含 image_generate 与 bfl_flux3_get_result——括注是白名单只有 TTS 时代的遗文。

### 机制 37:`_collect_history_media_paths` —— 已投递去重集(1654–1715)

**场景/问题**:同一文件不许跨回合重发。漏了 JSON 载荷形态导致 #46627;漏了 assistant 消息里模型复读的 MEDIA 标签导致重复投递。

**实现**:覆盖三种投递形态:tool 结果中的 MEDIA 标签、assistant 消息中的 MEDIA 标签、image_generate 的 JSON 路径。文本形态**双通道**收集:正则 + `BasePlatformAdapter.extract_media`(gateway/platforms/base.py:4457)——正则漏掉引号/含空格路径,而投递管道的 extract_media 文法接受它们;去重集必须看见**一切可能已投递**的路径。

路径:gateway/run.py:1670-1680 @ 863e313
```python
    def _add_text_media_paths(content: str) -> None:
        for match in _TOOL_MEDIA_RE.finditer(content):
            path = match.group(1).strip().rstrip('",}')
            if path:
                paths.add(path)
        # The regex alone misses quoted and spaced paths that the delivery
        # pipeline's extract_media grammar accepts — collect through the same
        # extractor so the dedup set sees every path that could actually have
        # been delivered.
        media_files, _ = BasePlatformAdapter.extract_media(content)
        paths.update(path for path, _is_voice in media_files)
```

**调用关系**:`_collect_history_media_paths` 在 gateway/run.py:5137 调用,产物喂给 5632 行的 `_collect_auto_append_media_tags`(19385 行注释亦引用该配对)。

**机制 36–37 重实现要点**:
1. "自动补投"类功能必须双层守卫:**来源白名单**(谁有资格产出)+ **形状校验**(产出长什么样),单靠文本模式必然误发示例;
2. "当前回合"切片边界在列表可能被压缩改写时不可信——校验 `len >= offset` 再用,否则回退全量+去重;
3. 去重集合的收集文法必须 ⊇ 投递文法(宁可多记不可漏记),最稳做法是直接复用投递端解析器;
4. JSON 载荷字段按固定优先序取**一个**,且复用同一形状校验(`fullmatch`)防字段里塞怪路径;
5. 每修一个泄漏形态(#16721/#34608/#46627)就把形态写进 docstring,守卫演化史即需求清单。

---

## SSL 证书自动探测(1717–1770)

### 机制 38:`_ensure_ssl_certs`

**场景/问题**:NixOS 等系统不把 CA 证书暴露在 Python 默认位置;Windows 启动路径(桌面、计划任务、安装器子进程)可能继承**指向已删除文件**的陈旧 `SSL_CERT_FILE`——若因"变量已设置"直接 return,之后每个 httpx/OpenAI client 构造都在 `ssl.load_verify_locations()` 抛 FileNotFoundError。

**实现**:已设且路径存在→尊重用户;已设但路径不存在→WARNING + **弹出该变量**继续探测。探测链:Python 编译内默认(`ssl.get_default_verify_paths()` 的 cafile/openssl_cafile)→ certifi 自带 Mozilla bundle → 8 个发行版/macOS 常见路径逐一试存在。

路径:gateway/run.py:1730-1738 @ 863e313
```python
    configured_cert = os.environ.get("SSL_CERT_FILE")
    if configured_cert:
        if os.path.exists(configured_cert):
            return  # user already configured it to a real file
        logging.getLogger(__name__).warning(
            "Ignoring stale SSL_CERT_FILE=%r because the path does not exist",
            configured_cert,
        )
        os.environ.pop("SSL_CERT_FILE", None)
```

**调用关系**:模块加载时即调(gateway/run.py:1814)。

**▲ 文档-代码冲突候选 7(“先于 HTTP 库导入”与实际时序)**:1718-1719 行节注声称 "Must run BEFORE any HTTP library (discord, aiohttp, etc.) is imported",但调用点在 1814 行,而模块头 49-67 行已导入 `agent.async_utils`、`agent.conversation_compression`、`agent.conversation_loop`、`hermes_cli.config` 等,这些**可能**传递性导入 httpx/aiohttp(未逐一追导入图)。缓解因素:`SSL_CERT_FILE` 多在 client **构造/连接**时读取而非 import 时,故即便约束被违反通常无害;但注释表述的强约束与实际放置顺序存在缝隙,值得定案时追一层导入图。

**重实现要点**:
1. 环境变量指向文件的配置,消费前必须验存在性;陈旧值要**清除**而非仅忽略,否则子进程继承同一坑;
2. 证书探测链按"最可信→最通用"排序:解释器内置 > certifi > 发行版路径;
3. "必须先于 X"的时序约束要用可执行手段固定(如放模块最顶),仅靠注释会随重构漂移。

---

## home target env 与 planned restart 通知(1772–1807)

### 机制 39:`_home_target_env_var` / `_home_thread_env_var`

home channel(定时任务/通知的默认投递目标)的 env 变量名解析:先查内置表与插件注册表(委托 `cron.scheduler._resolve_home_env_var`,cron/scheduler.py:1030),未知平台落 `<PLATFORM>_HOME_CHANNEL` 约定;thread 变量名恒为 `<home-var>_THREAD_ID`。

路径:gateway/run.py:1779-1789 @ 863e313
```python
    from cron.scheduler import _resolve_home_env_var

    resolved = _resolve_home_env_var(platform_name)
    if resolved:
        return resolved
    return f"{platform_name.upper()}_HOME_CHANNEL"


def _home_thread_env_var(platform_name: str) -> str:
    """Return the optional thread/topic env var for a platform home target."""
    return f"{_home_target_env_var(platform_name)}_THREAD_ID"
```

**调用关系**:gateway/run.py:17392;`_home_thread_env_var` 亦被其他模块 import(见 import 清单)。

### 机制 40:restart 通知标记文件(1792–1807)

两个哨兵文件区分两种重启通知:`~/.hermes/.restart_notify.json`(聊天内 `/restart` 完成回执,`_restart_notification_pending`)与 `.restart_pending.json`(非聊天途径的计划重启,须广播到各平台 home channel;`_planned_restart_notification_pending` / `_clear_planned_restart_notification`,清除用 `unlink(missing_ok=True)` 幂等)。

**调用关系**:gateway/run.py:11413-11435(启动后检查两标记、投递、清除)。

**重实现要点**:
1. 跨进程/跨重启的"待办通知"用哨兵文件承载,重启后的新进程凭文件存在性接力;
2. "谁发起的重启"决定通知面(发起会话 vs 全体 home channel),用不同哨兵文件区分而非文件内容分支;
3. 平台扩展点(env 变量名)用"注册表优先 + 命名约定兜底",插件平台零配置可用。

---

## 模块级初始化副作用(1810–1829)

### 机制 41:进程自标记、路径、env 装载顺序

**实现(按执行序)**:
1. `os.environ["_HERMES_GATEWAY"] = "1"`(1812)——标记本进程是 gateway,cli.py 模块级 `load_cli_config()` 被惰性导入时据此不覆写 `TERMINAL_CWD`;
2. `_ensure_ssl_certs()`(1814,机制 38);
3. `sys.path.insert(0, 项目父目录)`(1817);
4. 解析 hermes home(`get_hermes_home`,尊重 `HERMES_HOME` 覆盖;1820-1822);
5. 装载 `~/.hermes/.env`(`load_hermes_dotenv`,1827-1829)——**用户管理的 env 文件应覆盖重启时残留的 shell export**;1826 行保留 `from dotenv import load_dotenv  # noqa: F401` 仅为测试 monkeypatch 兼容。

路径:gateway/run.py:1810-1829 @ 863e313(节选)
```python
# Mark this process as a gateway so cli.py's module-level load_cli_config()
# knows not to clobber TERMINAL_CWD if lazily imported.
os.environ["_HERMES_GATEWAY"] = "1"

_ensure_ssl_certs()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

**重实现要点**:
1. 进程角色标记尽早写 env,供任何被惰性导入的共享模块自辨语境;
2. env 装载语义定死方向:"文件覆盖继承的 shell 残留"适合长驻服务,与一般 dotenv 默认(不覆盖)相反,要显式注明;
3. 为测试保留的兼容 import 必须注明原因,否则会被当死码清理。

---

## 运行时 env 重载与 max_turns 桥接(1832–1905)

### 机制 42:`_reload_runtime_env_preserving_config_authority` + `_bridge_max_turns_from_config`

**场景/问题**:gateway 长驻,API key 会轮换——每回合要重读 `.env` 拿新凭据;但 `.env` 里陈旧的 `HERMES_MAX_ITERATIONS` 不能反过来覆盖 config.yaml 的 `agent.max_turns`(config 是预算类设置的权威)。多路复用(multiplex)模式下还有第三个约束:凭据来自 per-turn `set_secret_scope` 的隔离映射,重载进程级 `os.environ` 会把默认 profile 的 key 泄漏给所有 profile 的回合与子进程。

**实现**:multiplex 激活时跳过 `.env` 重载、只跑 max_turns 桥;否则先 `load_hermes_dotenv` 再桥。桥接(1861-1896):raw 读 config(**存在敏感**——只有用户真写了的键才桥)、`_expand_env_vars` 展开、`managed_scope.apply_managed_overlay` 保管理员钉死值每回合重新生效(否则第一回合后被用户值顶掉;fail-open),然后 `agent.max_turns` → `HERMES_MAX_ITERATIONS`,顺带桥 `sessions.cjk_fts`/`sessions.search_slow_ms`(config 赢过陈旧 env,env 只作跨进程载体)。

路径:gateway/run.py:1846-1858 @ 863e313
```python
    from agent.secret_scope import is_multiplex_active
    if is_multiplex_active():
        # Credentials are resolved from the active profile's secret scope, not
        # os.environ. Still honor config.yaml's agent.max_turns bridge below
        # using the scoped home, but never reload .env into global env.
        _bridge_max_turns_from_config(_hermes_home)
        return

    load_hermes_dotenv(
        hermes_home=_hermes_home,
        project_env=Path(__file__).resolve().parents[1] / '.env',
    )
    _bridge_max_turns_from_config(_hermes_home)
```

路径:gateway/run.py:1886-1896 @ 863e313
```python
    agent_cfg = cfg.get("agent", {})
    if isinstance(agent_cfg, dict) and "max_turns" in agent_cfg:
        os.environ["HERMES_MAX_ITERATIONS"] = str(agent_cfg["max_turns"])
    # config-authoritative knobs for the session-search index (config.yaml
    # sessions.* wins over stale env; env stays the cross-process carrier).
    sessions_cfg = cfg.get("sessions", {})
    if isinstance(sessions_cfg, dict):
        if "cjk_fts" in sessions_cfg:
            os.environ["HERMES_CJK_FTS"] = str(sessions_cfg["cjk_fts"])
        if "search_slow_ms" in sessions_cfg:
            os.environ["HERMES_SEARCH_SLOW_MS"] = str(sessions_cfg["search_slow_ms"])
```

### 机制 43:`_current_max_iterations`(1899–1905)

每次取每回合迭代预算前**先跑一遍机制 42**(即"每回合刷新凭据"就是挂在这里实现的),再读 `HERMES_MAX_ITERATIONS`,解析失败回 500。

**调用关系**:gateway/run.py:4442、19526(每个 agent 回合起点)。

**机制 42–43 重实现要点**:
1. 长驻进程的凭据热轮换靠"每回合重读 env 文件",预算类配置靠"每回合 config→env 再桥接",两个方向都要**每回合**做,否则谁后写谁赢的竞态随回合数漂移;
2. 权威层次定死并写进函数名:config.yaml(权威)> env(载体)> .env 残留(可被覆盖);
3. 隔离模式(multi-tenant/secret scope)下,任何"写进程级 os.environ"的路径都要显式短路;
4. presence-敏感桥接用 raw config 读取——只桥用户显式写的键,避免默认值污染 env;
5. 管理员钉值 overlay 必须在**每次**桥接时重放,单次启动时套一遍会被后续重载洗掉。

---

## 尾部样板(1908–1922)

`from contextlib import contextmanager as _contextmanager`(1908,供段外 1937 行 `_profile_runtime_scope` 用);1911-1921 从 `gateway.config` 导入 `PORT_BINDING_PLATFORM_VALUES`/`platform_binds_port` 并附长注释:绑定主机端口的平台在 profile 多路复用器里只能由默认 profile 持有(次级 profile 启用即配置错误,跳过该 profile 而非拖垮整机;集合放 gateway.config 使 dashboard 预写校验同策略)。消费者是段外的 `SecondaryPortBindingConfigError` 体系(1933 行起)。纯导入样板,点名带过。

---

## 本段「文档-代码冲突」候选汇总

| # | 位置 | 冲突 |
|---|------|------|
| 1 | gateway/run.py:90 | `_TELEGRAM_NOISY_STATUS_RE` 命名限定 Telegram,实际经 `_prepare_gateway_status_message`(:738)作用于**所有**聊天平台(#39293 已推广,334 行注释自认) |
| 2 | gateway/run.py:128 | 注释称 "mirroring `_RECONNECT_BACKOFF_CAP` **above**",该常量实际在 :3662(其后 3500 行)且值不同(300 vs 3600);"mirror"仅指模式 |
| 3 | gateway/run.py:343 | `_GATEWAY_PROVIDER_ERROR_RE` 全仓零引用(含 tests),被 :661 `_GATEWAY_PROVIDER_ERROR_SHAPE_RE` 取代后的孤儿死代码 |
| 4 | gateway/run.py:642 | `_gateway_provider_error_reply` docstring 称 "Telegram reply",实际服务全部非 raw 聊天面 |
| 5 | gateway/run.py:1519-1520 vs 1117 | auto-continue 剥离器只认旧版前缀("Your previous turn"/"A new message"),当前 `build_resume_recovery_note` 生成 "The previous turn"——自洽前提是新注记不再拼入持久化用户行,需段外核实定案 |
| 6 | gateway/run.py:1582-1583 | docstring "(TTS)" 例举过窄,白名单实含 image_generate、bfl_flux3_get_result |
| 7 | gateway/run.py:1718-1719 vs 1814 | "Must run BEFORE any HTTP library is imported" 与实际调用点在 49-67 行 agent 系导入之后存在时序缝隙(通常无害,SSL_CERT_FILE 多在 client 构造时读) |

另核实为**非冲突**:机制 6 docstring 称 AGENTS.md 点名本文件禁 source-reading 测试——AGENTS.md:1382(禁令)与 AGENTS.md:1434(点名 `gateway/run.py`)属实。

## 与簇内其他文件的调用关系总表(本段视角)

- **被谁调**:`GatewayRunner._handle_message_with_agent` 及各闭包(gateway/run.py:4364/4378/4889/5100/5114/5137/5176/5217/5276/5303/5333/5376/5419/5578/5632/17040/17251/17671 等);`start_gateway`(:26716 装 loop handler、:26802 venv 修复);gateway/slash_commands.py(:1642 导入 `_telegramize_command_mentions`、:4050 导入 `_seed_hygiene_system_prompt`);其余模块经 `from gateway.run import` 复用 `_load_gateway_config`、`_home_target_env_var`、`_redact_approval_command` 等。
- **调谁**:agent/turn_context.py:199(`compression_made_progress`);agent/replay_cleanup.py:42/120/255(三剥离器);agent/redact.py:659(`redact_sensitive_text`);agent/conversation_loop.py:100(中断哨兵前缀);gateway/session.py:40(freshness 权威);gateway/session_state.py:169(`hygiene_failure_streak`);gateway/display_config.py:187;gateway/message_timestamps.py:114;gateway/platforms/base.py:4457(`extract_media`);cron/scheduler.py:1030(home env 解析);hermes_cli/commands.py:797(Telegram 名清洗);agent/context_compressor.py:1975/1638(对照:agent 内冷却梯与 bind 清零,机制 4 的动机)。