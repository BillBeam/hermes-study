# r7c-raw-status · status.py + status_phrases.py + status_phrases.yaml + display_config.py

> 底稿(求全求证)。基线 `863e31318553cda8ad61df681d08175364d4164b`,下文一律简写 `@ 863e313`。
> hermes-agent 只读。凡对代码行为的断言,紧跟 `路径:行号 @ 863e313` 与代码原文块。

---

## 0. 本切片一句话

**同名不同物**:`gateway/status.py` 是**网关进程运行态**(PID 文件 / 文件锁 / 接管标记 /
存活判定,2260 行,与聊天完全无关),`gateway/status_phrases.py` + `assets/status_phrases.yaml`
才是**聊天里的"还在忙"状态短语库**,`gateway/display_config.py` 是**按平台分档的显示策略表**
——三者共用 "status" 一词但分属两条完全独立的链路。

### 0.1 必须先纠正的任务前提

派单简报把本切片整体理解为"状态消息(UX)"机制,并按此提出了一组问题
("状态怎么发到平台?是新消息还是编辑同一条?与 stream_consumer 什么分工?")。
**这个前提对 `status_phrases.py` / `display_config.py` 成立,对 `status.py` 不成立。**

证据:`gateway/status.py` 全文的公开函数没有任何一个与聊天消息有关。模块自述
(`gateway/status.py:1-11 @ 863e313`):

```python
"""
Gateway runtime status helpers.

Provides PID-file based detection of whether the gateway daemon is running,
used by send_message's check_fn to gate availability in the CLI.

The PID file lives at ``{HERMES_HOME}/gateway.pid``.  HERMES_HOME defaults to
``~/.hermes`` but can be overridden via the environment variable.  This means
separate HERMES_HOME directories naturally get separate PID files — a property
that will be useful when we add named profiles (multiple agents running
concurrently under distinct configurations).
"""
```

因此本底稿按**两条链路**分别作答:§2 走 UX 状态消息链路(status_phrases + display_config +
run.py 的心跳/live status),§3 走进程运行态链路(status.py)。§5 定案 R7 移交的描述矛盾。

---

## 1. 结构总览

### 1.1 `gateway/status.py`(2260 行)

| 行区间 | 内容 | 关键符号 |
|---|---|---|
| 1-11 | 模块 docstring(**只讲 PID 检测**,见 §5) | — |
| 13-52 | import + 模块常量 + 全局可变状态 | `_RUNTIME_STATUS_FILE`、`_gateway_lock_handle`、`_gateway_running_pid_cache` |
| 55-128 | **重生风暴断路器**(respawn-storm breaker) | `StormInfo`、`record_start_and_check_storm` |
| 131-185 | 身份文件路径解析(进程级 HERMES_HOME) | `_get_process_hermes_home`、`_get_pid_path`、`_get_gateway_lock_path`、`_get_runtime_status_path`、`_get_lock_dir` |
| 187-244 | 时间与 `updated_at` 归一化 | `_utc_now_iso`、`normalize_updated_at` |
| 247-277 | 跨平台终止进程 | `terminate_pid` |
| 280-325 | 作用域哈希 + 进程启动时间指纹(PID 复用防护) | `_scope_hash`、`_get_process_start_time`、`get_process_start_time` |
| 328-367 | 读取目标进程命令行(/proc → ps → psutil 三级) | `_read_process_cmdline` |
| 370-460 | **网关命令行判别器**(子命令级,不做子串匹配) | `_gateway_command_subcommand`、`looks_like_gateway_command_line`、`looks_like_gateway_runtime_command_line` |
| 463-566 | 网关身份判定 + profile 归属判定 | `_looks_like_gateway_process`、`_record_looks_like_gateway`、`_profile_name_for_home`、`_command_line_belongs_to_profile`、`_record_matches_live_gateway_pid` |
| 569-658 | 记录构造 + JSON 读写 + PID 记录解析 | `_build_pid_record`、`_build_runtime_status_record`、`_read_json_file`、`_write_json_file`、`_read_pid_record` |
| 661-709 | running-pid 缓存签名 + 过期 PID 文件清理 | `_file_cache_signature`、`_running_pid_cache_signature`、`_cleanup_invalid_pid_path` |
| 711-735 | 文件锁原语(fcntl / msvcrt) | `_write_gateway_lock_record`、`_try_acquire_file_lock` |
| 738-866 | **不杀进程的存活探测**(Windows `os.kill(pid,0)` 陷阱) | `_pid_exists`、`_release_file_lock` |
| 868-952 | 网关运行时锁 | `acquire_gateway_runtime_lock`、`release_gateway_runtime_lock`、`is_gateway_runtime_lock_active` |
| 954-978 | 原子写 PID 文件(O_CREAT\|O_EXCL) | `write_pid_file` |
| 980-1045 | **运行态快照读写**(`gateway_state.json`) | `write_runtime_status`、`read_runtime_status` |
| 1048-1106 | 快照新鲜度 / PID 存活 / 计数归一 | `runtime_status_is_stale`、`runtime_status_pid_is_live`、`parse_active_agents` |
| 1109-1149 | busy / drainable 派生契约 | `derive_gateway_busy`、`derive_gateway_drainable` |
| 1152-1290 | **存活判定三级梯子**(唯一真源) | `GatewayLiveness`、`resolve_gateway_liveness` |
| 1293-1334 | 从运行态快照回退取 PID | `get_runtime_status_running_pid` |
| 1337-1359 | 只删自己的 PID 文件 | `remove_pid_file` |
| 1362-1556 | **机器级 scoped 锁**(同一 bot token 只许一个网关用) | `acquire_scoped_lock`、`release_scoped_lock`、`release_all_scoped_locks` |
| 1559-1754 | **`--replace` 接管标记** | `write_takeover_marker`、`consume_takeover_marker_for_self`、`clear_takeover_marker`、`_consume_pid_marker_for_self` |
| 1757-1852 | scoped 锁持有者身份校验与等待 | `_validated_scoped_lock_gateway_owner`、`_scoped_lock_owner_state`、`_wait_for_scoped_lock_owner_exit` |
| 1853-1952 | 孤儿子进程快照与回收(POSIX) | `_snapshot_gateway_children`、`reap_gateway_children` |
| 1955-2054 | 跨 home 接管的完整流程 | `take_over_scoped_lock_holder`、`_terminate_scoped_lock_owner_once` |
| 2057-2155 | **计划内停止标记** | `write_planned_stop_marker`、`consume_planned_stop_marker_for_self`、`planned_stop_marker_targets_self`、`clear_planned_stop_marker` |
| 2158-2251 | 取运行中 PID(+短 TTL 缓存) | `get_running_pid`、`get_running_pid_cached` |
| 2254-2260 | 布尔封装 | `is_gateway_running` |

按行数粗分:**token/scoped 锁相关**约 `280-285` + `1362-1556` + `1757-2054` ≈ 500 行(22%);
**PID / 运行态 / 存活判定 / 标记 / 风暴断路** ≈ 1750 行(78%)。这个比例是 §5 定案的关键。

### 1.2 `gateway/status_phrases.py`(227 行)

| 行区间 | 内容 |
|---|---|
| 1-26 | 模块 docstring:短语来源、用户扩展路径、"绝不回显原始模型草稿"承诺 |
| 28-50 | import + 常量 + **硬编码兜底短语** `_FALLBACK_PHRASES` |
| 53-64 | 单个短语列表清洗(去空、限长、去重、限量) |
| 67-76 | 一层 mapping 合并(append/replace) |
| 78-84 | 单文件合并 |
| 87-111 | **路径沙箱**(拒绝绝对路径与 `..`)+ 目录展开 |
| 114-129 | 多路径合并 |
| 132-143 | 内置目录加载 + 进程级缓存 `_DEFAULT_PHRASES` |
| 146-182 | 配置段合并 + `resolve_status_phrase_catalog`(四级解析顺序) |
| 185-196 | `classify_status_context`:事件 kind → 两个 surface 之一 |
| 199-227 | `choose_status_phrase`:随机选 + 近 6 条去重 |

### 1.3 `gateway/assets/status_phrases.yaml`(52 行)

两个顶层键:`status:`(30 条,行 2-31)、`generic:`(20 条,行 33-52)。纯英文字符串列表,无结构、无占位符。

### 1.4 `gateway/display_config.py`(311 行)

| 行区间 | 内容 |
|---|---|
| 1-20 | docstring:四级解析顺序 + `display.streaming` 例外 + 向后兼容说明 |
| 33-71 | `_GLOBAL_DEFAULTS`:12 个可按平台覆盖的键 + 默认值 |
| 81-119 | 四档能力档位 `_TIER_HIGH/MEDIUM/LOW/MINIMAL` |
| 121-181 | `_PLATFORM_DEFAULTS`:20 个平台键 → 档位(含 4 处逐平台微调) |
| 184 | `OVERRIDEABLE_KEYS`(**全仓无调用方**,见 §6 ◇C-7) |
| 187-249 | `resolve_display_setting`:四级 fallback |
| 256-311 | `_normalise`:YAML 1.1 怪癖归一 + 三态/枚举收敛 |

---

## 2. 链路 A:聊天里的"状态消息"生命周期

### 2.1 解决什么问题

用户在 Telegram/Slack 里发一句"帮我把整个测试套跑一遍",agent 可能跑 20 分钟。
期间平台上只有一个 `typing…` 气泡(甚至没有)。用户无法区分"还在跑"和"已经死了"。
`gateway/display_config.py:126-128 @ 863e313` 把这个 UX 目标写死在注释里:

```python
    # heartbeats (long_running_notifications) so the user has signal between
    # turn start and final answer. Otherwise it looks like "typing..." for
    # 30 minutes with nothing happening. Opt in to verbose iteration detail
```

### 2.2 三条并行的可见性通道(相互独立,分别开关)

代码里"让用户看到 agent 在干什么"实际上是**三条独立通道**,共用 `display` 配置面但互不依赖:

| 通道 | 载体 | 开关 | 粒度 |
|---|---|---|---|
| ① 工具进度气泡 | 普通聊天消息(可编辑/累积) | `tool_progress` + `tool_progress_grouping` | 每次工具调用 |
| ② 长任务心跳 | 普通聊天消息(**优先编辑同一条**) | `long_running_notifications` + `HERMES_AGENT_NOTIFY_INTERVAL` | 固定周期(默认 180s) |
| ③ live status | **typing 指示器本身携带的文本** | `live_status` + 适配器 `supports_status_text` | 每次 `tool.started` / `tool.completed` |

三者互不依赖的证据 —— ③ 的注释明说独立于 ①(`gateway/run.py:24418-24424 @ 863e313`):

```python
        # Live working-state status for text-rendering typing indicators
        # (Slack's assistant status line). Independent of tool_progress —
        # Slack defaults tool_progress off (permanent lines spam channels)
        # but the status line is ephemeral, so live status stays useful
        # there. Rendering rides the existing _keep_typing refresh: the
        # callback only stores a phrase on the adapter, costing zero extra
        # platform API calls.
```

**本切片(status_phrases.yaml)只服务通道 ②**,而且只在 ② 被设成 `generic` 模式时才生效
(见 §2.4)。通道 ③ 的文案来自另一个模块 `agent/display.py` 的 `build_status_phrase`
(`agent/display.py:687 @ 863e313`),**不读 yaml**。这是本切片最容易误判的一点。

### 2.3 谁调用、什么时机(通道 ②:心跳)

心跳是一个独立的 asyncio 任务,与回合执行并行(`gateway/run.py:24979-24992 @ 863e313`):

```python
        async def _notify_long_running():
            if _NOTIFY_INTERVAL is None:
                return  # Notifications disabled (gateway_notify_interval: 0)
            _notify_adapter = self._adapter_for_source(source)
            if not _notify_adapter:
                return
            # Track the heartbeat message id so we can edit-in-place on
            # platforms that support it (Telegram, Discord, Slack, etc.)
            # instead of spamming a new "Still working" bubble every
            # interval. Falls back to send-new when edit fails or isn't
            # supported by the adapter.
            _heartbeat_msg_id: Optional[str] = None
            while True:
                await asyncio.sleep(_NOTIFY_INTERVAL)
```

周期与总开关(`gateway/run.py:24968-24977 @ 863e313`):

```python
        _NOTIFY_INTERVAL_RAW = _float_env("HERMES_AGENT_NOTIFY_INTERVAL", 180)
        _NOTIFY_INTERVAL = _NOTIFY_INTERVAL_RAW if _NOTIFY_INTERVAL_RAW > 0 else None
        _long_running_mode = _display_surface_mode(
            "long_running_notifications",
            default=True,
            allow_generic=True,
        )
        if _long_running_mode == "off":
            _NOTIFY_INTERVAL = None
        _notify_start = time.time()
```

**粒度是时间驱动而非事件驱动**:每 180 秒一次,不随工具调用变化。每次醒来先检查这一轮是否还
持有会话槽位,否则退出(`gateway/run.py:24993-25006 @ 863e313`,注释里带 issue #12029,见 §7)。

### 2.4 状态怎么渲染:yaml 还是硬编码文案

**二选一,由 `long_running_notifications` 的取值决定**(`gateway/run.py:25037-25041 @ 863e313`):

```python
                _heartbeat_text = (
                    _generic_status_phrase("status")
                    if _long_running_mode == "generic"
                    else f"⏳ Working — {_elapsed_mins} min{_status_detail}"
                )
```

- `long_running_notifications: true`(默认)→ 走 **硬编码** `⏳ Working — N min — iteration 3/60, terminal`,**完全不读 yaml**;
- `long_running_notifications: generic` → 走 **yaml 短语库**,输出如 `still on it`;
- `long_running_notifications: false` → 整条通道关掉。

`generic` 这个第三态由 `_normalise` 单独放行,且**只对这一个键放行**
(`gateway/display_config.py:269-283 @ 863e313`):

```python
    if setting in {
        "show_reasoning",
        "streaming",
        "interim_assistant_messages",
        "long_running_notifications",
        "busy_ack_detail",
        "busy_steer_ack_enabled",
        "thinking_progress",
    }:
        if isinstance(value, str):
            val = value.strip().lower()
            if val == "generic" and setting == "long_running_notifications":
                return "generic"
            return val in {"true", "1", "yes", "on", "raw", "verbose"}
        return bool(value)
```

配套测试正是这一条:`tests/gateway/test_display_config.py:93` `test_only_long_running_visibility_accepts_generic_mode`。

**结论:yaml 短语库默认不生效**。默认路径下用户看到的是 `⏳ Working — N min`。
这与 `website/docs/user-guide/messaging/index.md:452` 的表述有落差(见 §6 ▲C-3)。

### 2.5 随机化 / 去重 / 节流

三者都在 `choose_status_phrase`(`gateway/status_phrases.py:199-227 @ 863e313`):

```python
def choose_status_phrase(
    kind: str,
    *,
    tool_name: str | None = None,
    preview: str | None = None,
    args: Any = None,
    recent: MutableSequence[str] | None = None,
    rng: Any = None,
    catalog: Mapping[str, list[str]] | None = None,
) -> str:
    """Pick a short generic status phrase, avoiding recent repeats.

    ``preview`` and ``args`` are accepted for callback compatibility, but their
    raw contents are never embedded in the returned phrase.
    """
    phrase_catalog = catalog or _DEFAULT_PHRASES
    category = classify_status_context(kind, tool_name=tool_name, preview=preview, args=args)
    candidates = list(phrase_catalog.get(category) or phrase_catalog.get("generic") or _DEFAULT_PHRASES["generic"])
    if recent:
        recent_set = set(recent)
        fresh = [phrase for phrase in candidates if phrase not in recent_set]
        if fresh:
            candidates = fresh
    picker = rng or _random
    phrase = picker.choice(candidates)
    if recent is not None:
        recent.append(phrase)
        del recent[:-6]
    return phrase
```

- **随机化**:`random.choice`,可注入 `rng`(测试用 `random.Random(4)`)。
- **去重**:`recent` 滑动窗口,`del recent[:-6]` 只保留最近 6 条;候选全被用过则退回全集(不会死锁)。
- **节流**:短语层没有节流,节流在上游 —— 180s 的 `asyncio.sleep`。
- `recent` 的宿主是**每回合一个新列表**(`gateway/run.py:24374 @ 863e313` `_generic_status_recent: List[str] = []`),
  即去重窗口**不跨回合**。

**目录在回合开始时解析一次并缓存**(`gateway/run.py:24373-24375 @ 863e313`):

```python
        from gateway.status_phrases import choose_status_phrase, resolve_status_phrase_catalog
        _generic_status_recent: List[str] = []
        _generic_status_catalog = resolve_status_phrase_catalog(user_config, platform_key)
```

短语选择失败有兜底,且兜底文案**又是一次硬编码**(`gateway/run.py:24411-24413 @ 863e313`):

```python
            except Exception as _phrase_err:
                logger.debug("generic status phrase selection failed: %s", _phrase_err)
                return "still on it" if kind in {"heartbeat", "waiting", "long_running", "status"} else "one sec"
```

于是同一句 `still on it` 在仓库里有**三份来源**:yaml 行 2、`_FALLBACK_PHRASES`
(`gateway/status_phrases.py:48`)、run.py 的 except 分支。见 §6 ◇C-8。

### 2.6 怎么发到平台:先编辑,失败再新发

`gateway/run.py:25042-25065 @ 863e313`:

```python
                try:
                    _notify_res = None
                    if _heartbeat_msg_id:
                        try:
                            _notify_res = await _notify_adapter.edit_message(
                                source.chat_id,
                                _heartbeat_msg_id,
                                _heartbeat_text,
                            )
                        except Exception as _ee:
                            logger.debug("Heartbeat edit failed: %s", _ee)
                            _notify_res = None
                    if not (_notify_res and getattr(_notify_res, "success", False)):
                        _notify_res = await _notify_adapter.send(
                            source.chat_id,
                            _heartbeat_text,
                            metadata=_non_conversational_metadata(_status_thread_metadata, platform=source.platform),
                        )
                        if getattr(_notify_res, "success", False) and getattr(
                            _notify_res, "message_id", None
                        ):
                            _heartbeat_msg_id = str(_notify_res.message_id)
                            if _cleanup_progress:
                                _cleanup_msg_ids.append(_heartbeat_msg_id)
```

**投递策略是"编辑同一条为主、send 为兜底"**,而且**不做能力探测**:直接 try `edit_message`,
异常吞成 debug、`success=False` 也回退。这与 R7B 记录的"能力探测靠 TypeError + 宽 except"
是同一类反模式,但这里更温和 —— 回退语义是明确设计的(注释 `gateway/run.py:24988-24989`
"Falls back to send-new when edit fails or isn't supported by the adapter")。

**不支持编辑的平台怎么办**:两层防御。
1. 事前:`display_config.py` 把这些平台整档降到 `_TIER_LOW` / `_TIER_MINIMAL`,
   `long_running_notifications: False`,心跳根本不启动(`gateway/display_config.py:101-119 @ 863e313`)。
2. 事中:即使被用户强行打开,`edit_message` 失败会退化成每 180s 一条新消息 —— 这正是档位
   注释所说的 "Tier 3 (low): No edit support — each progress msg is permanent"
   (`gateway/display_config.py:78 @ 863e313`)。

**收尾**:`cleanup_progress` 开启时,心跳消息 id 进 `_cleanup_msg_ids`,回合成功后统一删除。
适配器不实现 `delete_message` 则静默关掉该功能(`gateway/run.py:24509-24516 @ 863e313`):

```python
        _cleanup_delete = getattr(type(_cleanup_adapter), "delete_message", None) if _cleanup_adapter is not None else None
        if _cleanup_adapter is not None and (
            _cleanup_delete is None
            or _cleanup_delete is BasePlatformAdapter.delete_message
        ):
            # Adapter doesn't support deletion — silently disable.
            _cleanup_progress = False
```

注意这里用 `getattr(type(adapter), ...)` 并与基类方法做**同一性比较** —— 判断的是"子类是否
覆写过",而非"属性是否存在"。这是比 `hasattr` 严谨一档的能力探测,值得抄。

### 2.7 typing indicator 与状态消息的关系(通道 ③)

**关键区分:typing 指示器在多数平台是无文字的动画,在 Slack 是一行可带文字的 assistant status。**
Hermes 把"这行字"当成第三块可写的屏幕。

写入点在工具事件回调(`gateway/run.py:3696-3714 @ 863e313`):

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
            except Exception as _ls_err:
                logger.debug("live status update failed: %s", _ls_err)
```

`set_status_text` 只是**往适配器上的一个 dict 写字符串**,不发任何 API
(`gateway/platforms/base.py:2658-2670 @ 863e313`,基类默认 `supports_status_text: bool = False`
在 `:2656`)。真正的渲染搭**已有的 typing 刷新节拍**顺风车,零额外 API 调用。

能力开关:全仓只有两处宣称支持 ——
- `plugins/platforms/slack/adapter.py:875 @ 863e313`:`supports_status_text = True`
- `gateway/relay/adapter.py:154 @ 863e313`:按 relay 握手 descriptor 动态判断(relay 代理 Slack 时才为真)

relay 侧把短语塞进 typing 帧(`gateway/relay/adapter.py:1227-1233 @ 863e313`):

```python
        frame: Dict[str, Any] = {
            "op": "typing",
            "chat_id": chat_id,
            "metadata": self._with_scope(chat_id, md),
        }
        phrase = getattr(self, "_status_text", {}).get(str(chat_id))
        if phrase:
            frame["content"] = str(phrase)
```

网关侧的门禁三连(`gateway/run.py:24425-24432 @ 863e313`):

```python
        _live_status_mode = resolve_display_setting(
            user_config, platform_key, "live_status", "full"
        )
        _live_status_adapter = self._adapter_for_source(source)
        if not getattr(_live_status_adapter, "supports_status_text", False):
            _live_status_adapter = None
        if _live_status_mode == "off":
            _live_status_adapter = None
```

**取舍**:`live_status` 的三态设计(`full` / `verb` / `off`)是一个**隐私开关而非音量开关** ——
`verb` 传 `args=None` 给 `build_status_phrase`,于是只出 `is running…` 不出文件路径与命令行。
理由写在 `agent/display.py:696-698 @ 863e313`:

```python
    Pass ``args=None`` for a verb-only phrase (``is running…``) — used when
    ``display.live_status`` is ``verb`` to keep argument previews out of
    shared channels.
```

### 2.8 与 stream_consumer(R7 已读)的分工

`gateway/stream_consumer.py` 全文只有 **1 处** "status" 命中,而且指的是**另一件事**
—— 模型自己产出的 commentary 文本(`gateway/stream_consumer.py:1818-1821 @ 863e313`):

```python
            # Commentary messages are interim status updates (e.g. "Using browser
            # tool..."), not the final response. Setting already_sent would cause
            # the final response to be incorrectly suppressed when there are
            # multiple tool calls. See: https://github.com/NousResearch/hermes-agent/issues/10454
```

对 typing 也只有一处"暂停刷新"钩子(`gateway/stream_consumer.py:215-217 @ 863e313`):

```python
        # Fired once when the stream transitions into its finalization path.
        # Gateway callers use this to pause typing refreshes before a slow
        # final rich-text edit (Telegram MarkdownV2 finalize, etc.).
        self._on_before_finalize = on_before_finalize
```

**分工:stream_consumer 管"最终答案这条消息"的增量渲染;本切片三条通道管"最终答案之外的一切"。**
唯一耦合点是 `_on_before_finalize` —— 定稿前让 typing 刷新停手,避免 typing 帧覆盖终稿编辑。

---

## 3. 链路 B:`status.py` 的网关运行态(与聊天无关)

按机制列,每条给"解决什么问题 / 怎么实现 / 取舍"。

### 3.1 两套并存的存活凭据:PID 文件 + 运行时文件锁

**问题**:PID 文件在进程被 `kill -9` / OOM / 断电后会留下,内容还宣称"我活着"。
纯 PID 文件不可能区分"活着"与"死得难看"。

**实现**:文件锁由**活进程本身持有**,进程一死 OS 自动释放
(`gateway/status.py:868-873 @ 863e313`):

```python
def acquire_gateway_runtime_lock() -> bool:
    """Claim the cross-process runtime lock for the gateway.

    Unlike the PID file, the lock is owned by the live process itself. If the
    process dies abruptly, the OS releases the lock automatically.
    """
```

`get_running_pid` 把锁作为**前置门禁**,锁不活就直接判死并清理
(`gateway/status.py:2168-2177 @ 863e313`):

```python
    resolved_pid_path = pid_path or _get_pid_path()
    resolved_lock_path = _get_gateway_lock_path(resolved_pid_path)
    lock_active = is_gateway_runtime_lock_active(resolved_lock_path)
    if not lock_active:
        if pid_path is None:
            runtime_pid = get_runtime_status_running_pid()
            if runtime_pid is not None:
                return runtime_pid
        _cleanup_invalid_pid_path(resolved_pid_path, cleanup_stale=cleanup_stale)
        return None
```

**取舍**:锁的探测方式是"打开文件 → 尝试加锁 → 立刻解锁"(`gateway/status.py:942-946`),
每次都开关一次 fd。高频 HTTP 轮询会打爆 fd,于是又加了一层 1 秒 TTL 缓存
(`gateway/status.py:2206-2219 @ 863e313`),缓存键含文件 mtime+size 签名,启停变化能秒级察觉。

Windows 特殊处理:字节区间锁对其他读者是**强制锁**,会挡住读 JSON 的人,所以锁一个远在
payload 之后的字节(`gateway/status.py:44-47 @ 863e313`):

```python
# Windows byte-range locks are mandatory for other readers. Lock a byte well
# past the JSON payload so runtime status / PID readers can still read the file
# while another process holds the mutual-exclusion lock.
_WINDOWS_LOCK_OFFSET = 1024 * 1024
```

### 3.2 `_pid_exists`:一个"检查是否存活"的函数为什么有 116 行

**问题(事故讲成故事)**:POSIX 上 `os.kill(pid, 0)` 是无副作用的存活探测,是几十年的惯用法。
把这段代码原样搬到 Windows,CPython 的 `os_kill_impl` 因为 `sig=0` 与 `CTRL_C_EVENT` 在
C 层数值相同,会走 `GenerateConsoleCtrlEvent(0, pid)` —— **向目标 PID 所在的整个控制台进程组
发 Ctrl+C**。于是"我只是想看看它还在不在"变成了"我把它和它的一票邻居都杀了"。
证据(`gateway/status.py:739-750 @ 863e313`):

```python
    """Cross-platform "is this PID alive" check that does NOT kill the target.

    CRITICAL on Windows: Python's ``os.kill(pid, 0)`` is NOT a no-op like it
    is on POSIX. CPython's Windows implementation
    (``Modules/posixmodule.c::os_kill_impl``) treats ``sig=0`` as
    ``CTRL_C_EVENT`` because the two values collide at the C level, and
    routes it through ``GenerateConsoleCtrlEvent(0, pid)`` — which sends
    a Ctrl+C to the entire console process group containing the target
    PID, not just the PID itself. Any caller that wanted to "check if
    this PID is alive" via ``os.kill(pid, 0)`` on Windows was silently
    killing that process (and often unrelated processes in the same
    console group). Long-standing Python quirk; see bpo-14484.
    ...
    """
```

仓库把这条教训**制度化**了:唯一允许写 `os.kill(pid, 0)` 的地方是这个函数的 POSIX 分支,
并带内联豁免标记(`gateway/status.py:845 @ 863e313`):

```python
            os.kill(int(pid), 0)  # windows-footgun: ok — POSIX-only branch (the whole point of _pid_exists)
```

配套有 `scripts/check-windows-footguns.py` 扫描器(在 `_pid_exists` 引用清单里)。
**这是"用 linter 把一条事故变成不可复发"的范例**,可直接进成品章的可迁移原则。

第二个故事(**issue #42126**,僵尸进程):`--replace` 想接管旧网关,先 SIGTERM 再等它死。
但在 systemd `Restart=always` 下,systemd 会**先拉起新进程、后回收旧进程**,旧进程于是长期
处于 zombie(defunct)状态。zombie 仍在进程表里,`psutil.pid_exists()` 返回 True,SIGKILL
对它无效 —— `--replace` 永远等不到它死,超时后 `exit 1`,systemd 再拉起,构成静默崩溃循环。
修法:把 zombie 显式判为"已死"(`gateway/status.py:763-781 @ 863e313`):

```python
        # A zombie (defunct) process is still in the process table, so
        # ``psutil.pid_exists()`` returns True for it — but it is already
        # dead: SIGKILL has no effect and it cannot be a running gateway.
        # Treating a zombie as alive makes ``--replace`` wait for the old
        # PID to die (it never does, until its parent reaps it), then abort
        # with exit 1 — a silent crash loop under systemd ``Restart=always``,
        # which respawns the gateway before reaping the previous process
        # (issue #42126). Report zombies as dead so the takeover proceeds.
```

同一修复在 psutil 缺失时的 stdlib 分支也重做了一遍(`gateway/status.py:819-843`),
读 `/proc/<pid>/stat` 第 3 字段 == `"Z"`,macOS 退回 `ps -o state=`。

### 3.3 PID 复用防护:`(pid, start_time)` 二元组

**问题**:PID 是会被 OS 回收再分配的。一个陈旧记录里的 PID 可能已经落在别人身上,
把别人当成"我的网关"会导致误判存活、甚至误杀。

**实现**:`_get_process_start_time`(`gateway/status.py:288-320 @ 863e313`)取 Linux
`/proc/<pid>/stat` 第 22 字段(自启动以来的时钟滴答),无 `/proc` 时用
`psutil.Process(pid).create_time()` 量化到厘秒。docstring 明确说明**两种来源永不在同一主机上混用**,
所以单位不一致无所谓 —— 只比较同源相等性。

**取舍(重要)**:这个指纹在 macOS / Windows 上可能拿不到(返回 `None`)。全仓统一采用
**"双方都有才比,任一方缺就退回只比 PID"** 的规则,并靠标记的短 TTL(60s)兜底
(`gateway/status.py:1659-1676 @ 863e313`):

```python
    # Start-time is a PID-reuse guard. It is only meaningful when both
    # sides actually have it: ``_get_process_start_time`` returns None on
    # platforms without ``/proc`` (macOS, native Windows — the very
    # platform the planned-stop watcher exists for). Requiring a non-None
    # match there would make every consume return False, so a legitimate
    # ``hermes gateway stop`` on Windows would be misclassified as an
    # unexpected ``UNKNOWN`` exit (exit 1) and revived by the service
    # manager. So: when both start_times are known they must match; when
    # either is unknown, fall back to PID equality alone (bounded by the
    # marker's short TTL). This mirrors ``planned_stop_marker_targets_self``
    # so the watcher's non-destructive probe and this authoritative
    # consume agree on every platform (issue #34597).
```

同一段规则在 `planned_stop_marker_targets_self` 里逐字复述一遍
(`gateway/status.py:2136-2147 @ 863e313`,提到 **issue #33778**)。**这是可读性代价换正确性:
两个函数必须在每个平台上给出一致答案,注释宁可重复也不让读者去别处拼。**

### 3.4 网关命令行判别器:从子串匹配升级到子命令解析

**事故经过**(`gateway/status.py:371-389 @ 863e313`):

```python
    """Return the Hermes gateway lifecycle subcommand from a command line.

    Lifecycle decisions (is the gateway up? did restart relaunch it?) must not
    fire on loose substring matches.  The previous ``"... gateway" in cmdline``
    test also matched ``hermes_cli.main gateway status`` and even unrelated
    processes like ``python -m tui_gateway`` -- which made ``restart()`` race
    against a still-draining old process and ``status``/``start`` report false
    positives.  This requires the actual ``gateway`` subcommand followed by
    ``run`` (or one of the gateway-dedicated entrypoints), excluding the other
    ``gateway`` management subcommands and any process that merely contains the
    word "gateway".

    Tokenizes quote-aware (``shlex``) so quoted Windows paths with spaces
    (``"C:\\Program Files\\...\\hermes-gateway.exe"``) survive, and strips
    ``--profile``/``-p`` selectors from anywhere in argv -- Hermes's
    ``_apply_profile_override`` removes them before argparse, so the profile
    flag (and a profile literally named ``gateway``) can legally appear on
    either side of the ``gateway`` subcommand.
    """
```

什么输入 → `python -m tui_gateway`(一个**完全无关的进程**,只是名字里有 gateway);
什么现象 → `hermes gateway restart` 认为旧网关还活着,与自己竞态;`hermes gateway status`
误报运行中;
为什么 → 判据是 `"gateway" in cmdline` 的裸子串;
怎么修 → shlex 分词 → 剥离 `--profile/-p` 及其值 → 找到 `gateway` token → 读它**后面那个**
token 作为子命令 → 只认 `run`。

派生出**两级严格度**(`gateway/status.py:444-460 @ 863e313`):

```python
def looks_like_gateway_command_line(command: str | None) -> bool:
    """Return True only for a real ``gateway run`` process command line."""
    return _gateway_command_subcommand(command) == "run"


def looks_like_gateway_runtime_command_line(command: str | None) -> bool:
    """Return True for command lines that can host the gateway runtime.

    ``gateway restart`` is normally a management command, not the gateway
    runtime. On hosts without a service manager, though, the manual restart
    fallback executes ``run_gateway()`` in that same process, so its argv stays
    as ``gateway restart`` while it owns the webhook port and writes runtime
    state. Keep the public ``looks_like_gateway_command_line()`` strict, and
    use this broader matcher only when validating Hermes-owned runtime records
    or no-supervisor cleanup scans.
    """
    return _gateway_command_subcommand(command) in {"run", "restart"}
```

**取舍**:严格版给"外部世界"(`hermes_cli/_scan_venv_blockers.py:113` 用它扫要杀的进程),
宽松版只给"校验 Hermes 自己写的记录"。这个二分是刻意的,不是遗留。

### 3.5 profile 归属判定:同机多网关的第二道身份

`_command_line_belongs_to_profile`(`gateway/status.py:497-534 @ 863e313`)。
**事故**:每 profile 一个容器时,profile A 的陈旧 `gateway_state.json` 里记的 PID
被 OS 回收给了 profile B 的**活网关**;那个 PID 的命令行确实 `looks_like_gateway`,
于是仪表盘把已死的 A 报成运行中。

```python
    In a per-profile container, one profile's stale ``gateway_state.json`` can
    record a PID that the OS has since recycled onto a DIFFERENT profile's live
    gateway.  That recycled PID's command line still ``looks_like_gateway`` —
    so without a profile check the dead profile is reported running.
```

判定规则不对称:命名 profile 要求 argv 里出现 `--profile <name>` / `-p <name>` /
`hermes_home=<path>`;默认 profile 反过来 —— **只要没宣称别的 profile 就算数**,理由是
HERMES_HOME 通常走环境变量、命令行上看不见(`gateway/status.py:525-534 @ 863e313`)。

### 3.6 `gateway_state.json`:字段级增量写

**问题**:多个写者(启动序列写 `gateway_state`、每回合边界写 `active_agents`、
各适配器写自己的 `platforms.<name>`)。任何一个写者做全量覆盖都会抹掉别人的字段。

**实现**:所有参数默认 `_UNSET` 哨兵,只有显式传入才落盘;`None` 是合法值(用来清字段)
(`gateway/status.py:980-1029 @ 863e313`,`_UNSET = object()` 在 `:41`):

```python
def write_runtime_status(
    *,
    gateway_state: Any = _UNSET,
    exit_reason: Any = _UNSET,
    restart_requested: Any = _UNSET,
    active_agents: Any = _UNSET,
    platform: Any = _UNSET,
    platform_state: Any = _UNSET,
    error_code: Any = _UNSET,
    error_message: Any = _UNSET,
    served_profiles: Any = _UNSET,
) -> None:
    """Persist gateway runtime health information for diagnostics/status."""
    path = _get_runtime_status_path()
    payload = _read_json_file(path) or _build_runtime_status_record()
```

**身份字段无条件覆盖**(`gateway/status.py:998-1002`):`kind/pid/argv/start_time/updated_at`
每次都写成"当前进程"的值。这正是重启后接手旧文件时把陈旧 PID 顶掉的机制,
测试 `tests/gateway/test_status.py:173 test_write_runtime_status_overwrites_stale_pid_on_restart` 守着。

**副作用外发**:写完后触发状态迁移事件,失败静默(`gateway/status.py:1029-1033 @ 863e313`):

```python
    _write_json_file(path, payload)
    try:
        from agent.monitoring.gateway_health import emit_runtime_status_transition
        emit_runtime_status_transition(previous_payload, payload)
    except Exception:
        pass
```

为此在函数开头做了一次 `copy.deepcopy(payload)`(`:995`)保存旧值 —— **每次状态写入都付一次
深拷贝**,是可观测性换性能的显式取舍(该文件每回合边界都写)。

### 3.7 存活判定的三级梯子:`resolve_gateway_liveness`

**事故经过**(`gateway/status.py:1183-1193 @ 863e313`):

```python
    """Single source of truth for "is the gateway up?" across dashboard surfaces.

    Before this existed, ``/api/status`` and ``/api/messaging/platforms``
    each open-coded their own ladder and disagreed on the same page load —
    the sidebar read "running" while the Channels page rendered "The gateway
    is not running."  Three deployments hit it: a cross-container gateway
    (only ``/api/status`` ran the HTTP health probe), a profile-scoped
    dashboard (only ``/api/status`` passed the profile's paths, so messaging
    borrowed another profile's runtime state — issue #71211), and a
    launch-service-managed gateway with no PID file (only some callers used
    the runtime-status fallback).
```

什么输入 → 一次仪表盘页面加载;什么现象 → 同一页面上侧边栏说"运行中"、Channels 页说"未运行";
为什么 → 两个端点各自手写了不同的判定梯子;怎么修 → 抽出唯一真源,三级梯子固定顺序:
① PID 文件+运行时锁 → ② 调用方注入的 HTTP 健康探针 → ③ 运行态快照里的 PID(带 profile 归属校验)。

`probe_error` 字段的设计值得单列(`gateway/status.py:1159-1163 @ 863e313`):

```python
    ``probe_error`` is True when a rung raised instead of answering. Callers
    that must distinguish "the gateway is down" from "we could not tell"
    need it: the dashboard renders a down badge either way, but the kanban
    dispatcher warning deliberately fails OPEN on an unreadable probe so it
    never cries wolf at a user whose gateway is fine.
```

**"探测失败"与"确实没在跑"是两个不同的答案** —— 前者让告警 fail-open,后者才报警。
另有一条纪律写进 docstring:`source` 字段只给日志和测试用,**永远不许拿它分支产品行为**
(`gateway/status.py:1156-1157`)。

第 3 级只对**本机**记录生效(`gateway/status.py:1207-1210`):远端探针体里的 PID 属于别的主机,
`os.kill` 一个远端 PID 既错误又会踩到测试的 live-system 守卫。

### 3.8 scoped 锁:同一 bot token 不许两个网关同时用

**是机器级而非 profile 级** —— 这一点与 §5 的定案直接相关(`gateway/status.py:178-184 @ 863e313`):

```python
def _get_lock_dir() -> Path:
    """Return the machine-local directory for token-scoped gateway locks."""
    override = os.getenv("HERMES_GATEWAY_LOCK_DIR")
    if override:
        return Path(override)
    state_home = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state_home / "hermes" / _LOCKS_DIRNAME
```

锁文件落在 `$XDG_STATE_HOME/hermes/gateway-locks/<scope>-<sha256[:16]>.lock`,
**不在 HERMES_HOME 下**。原因写在 PID 记录构造处(`gateway/status.py:575-579 @ 863e313`):

```python
        # Scoped credential locks are machine-global rather than
        # HERMES_HOME-local.  Persist the owning gateway's process home so an
        # explicit cross-profile --replace can place its planned-takeover
        # marker where the target process will actually read it.
        "hermes_home": str(_canonical_hermes_home(_get_process_hermes_home())),
```

**逻辑必须如此**:锁的目的正是**跨 profile** 互斥(profile A 和 profile B 不能同时用同一个
Telegram token)。放进 HERMES_HOME 就完全失效了。

**陈旧锁判定是本文件最长的一段条件链**(`gateway/status.py:1398-1456`),五道判据依次收敛:
PID 不存在 → 陈旧;start_time 不匹配 → 陈旧;两侧 start_time 有缺失且活进程不像网关且
cmdline 可读 → 陈旧;两侧 start_time 都在且相等但活进程不像网关且 cmdline 可读 → 陈旧
(注释说明这是防 systemd 确定性启动造成的 PID+jiffy 双撞,`gateway/status.py:1427-1432`);
`/proc/<pid>/status` 里 `State:` 为 `T`/`t`(Ctrl+Z 停住)→ 陈旧。

**竞态修复:用 rename 到墓碑代替 unlink**(`gateway/status.py:1457-1478 @ 863e313`):

```python
        if stale:
            # Remove the stale lock ATOMICALLY by renaming it to a tombstone
            # instead of unlinking. With unlink()+O_EXCL, two racing starters
            # could both observe "removed" (the second unlink() silently
            # deleting the first racer's freshly-created lock) and both win.
            # os.replace() is atomic: exactly one racer claims the stale
            # file; the loser gets FileNotFoundError and falls through to
            # the O_EXCL create below, where at most one process succeeds.
            tombstone = lock_path.with_name(lock_path.name + ".stale")
```

**这是全切片最漂亮的一处并发修复**:两个 racer 同时判定"锁陈旧"时,`unlink` 不能定胜负
(第二个 unlink 会删掉第一个刚建的新锁),`os.replace` 可以。

另有一处空/坏 JSON 锁文件的处理(`gateway/status.py:1379-1387`),注释指名了触发场景:
"a previous process was killed between O_CREAT|O_EXCL and the subsequent json.dump()
(e.g. DNS failure during rapid Slack reconnect retries)"。

### 3.9 `--replace` 接管标记:一条被 exit code 语义逼出来的机制

**事故经过**(`gateway/status.py:1559-1576 @ 863e313`):

```python
# ── --replace takeover marker ─────────────────────────────────────────
#
# When a new gateway starts with ``--replace``, it SIGTERMs the existing
# gateway so it can take over the bot token. PR #5646 made SIGTERM exit
# the gateway with code 1 so ``Restart=on-failure`` can revive it after
# unexpected kills — but that also means a --replace takeover target
# exits 1, which tricks systemd into reviving it 30 seconds later,
# starting a flap loop against the replacer when both services are
# enabled in the user's systemd (e.g. ``hermes.service`` + ``hermes-
# gateway.service``).
#
# The takeover marker breaks the loop: the replacer writes a short-lived
# file naming the target PID + start_time BEFORE sending SIGTERM.
# The target's shutdown handler reads the marker and, if it names
# this process, treats the SIGTERM as a planned takeover and exits 0.
# The marker is unlinked after the target has consumed it, so a stale
# marker left by a crashed replacer can grief at most one future
# shutdown on the same PID — and only within _TAKEOVER_MARKER_TTL_S.
```

什么输入 → `hermes gateway start --replace`;什么现象 → 新旧网关反复互相杀,30 秒一轮;
为什么 → PR #5646 为了让"意外被杀"能被 `Restart=on-failure` 救活,把 SIGTERM 的退出码
定成 1,而计划内接管用的也是 SIGTERM,systemd 分不清;
怎么修 → **在信号之外开一条带外信道**:文件标记。SIGTERM 只说"停",标记回答"这是计划内的"。

**设计精髓:`exit code` 是一个只有几比特带宽的信道,用不下"意图"。文件标记是给信号加语义标签。**

同一模式复用了第二次:`write_planned_stop_marker` / `consume_planned_stop_marker_for_self`
(`gateway/status.py:2057-2085`),解决的是 `hermes gateway stop` 与"意外 SIGTERM"的区分。
两者共用 `_consume_pid_marker_for_self`(`gateway/status.py:1609-1683`),只是字段名和 TTL 不同。

**跨 profile 守卫(issue #29092)**(`gateway/status.py:1638-1655 @ 863e313`):

```python
    # Cross-profile guard (#29092): new markers explicitly name the verified
    # TARGET home.  That permits a deliberate cross-HERMES_HOME --replace while
    # ensuring a marker accidentally written into another profile's directory
    # is ignored.  Legacy markers have no target field, so retain the original
    # same-replacer-home rule for backwards compatibility.
```

新旧两种标记格式共存,靠 `target_hermes_home` 字段是否存在分流 —— 教科书式的**灰度兼容**。

**非破坏性探测 vs 权威消费**:watcher 线程要轮询标记但不能消费(消费权在 shutdown handler),
于是 `planned_stop_marker_targets_self`(`gateway/status.py:2088-2147`)只清理"永远不可能匹配
任何人"的标记(格式错、超 TTL),命名别人的标记原样留下。docstring 把这个不对称写清楚了。

### 3.10 孤儿子进程回收

**问题**(`gateway/status.py:1877-1883 @ 863e313`):

```python
    """Best-effort reap of a dead gateway's orphaned descendants (POSIX).

    Mirrors the Windows ``taskkill /T`` tree-kill for the POSIX ``--replace``
    paths: adapter subprocesses that survive their parent keep holding scoped
    token locks and block the replacement gateway.  Call only AFTER the main
    gateway PID is confirmed dead, with a ``children`` snapshot taken via
    :func:`_snapshot_gateway_children` while it was still alive.
```

**时序陷阱**:必须在旧网关**还活着的时候**拍快照,死后子进程被 reparent 到 init,
父进程遍历再也找不到它们(`gateway/status.py:1855-1857`)。
调用点严格遵守这个顺序(`gateway/status.py:1979-1992 @ 863e313`):

```python
    # Snapshot descendants while the owner is still alive — after it exits
    # they are reparented and undiscoverable (POSIX; [] on Windows where
    # taskkill /T already tree-kills).
    owner_children = _snapshot_gateway_children(owner_pid)

    replaced = _terminate_scoped_lock_owner_once(
        owner_pid,
        owner_start_time,
        target_home,
        graceful_attempts=graceful_attempts,
        force_attempts=force_attempts,
    )
    if replaced is not None:
        reap_gateway_children(owner_children, parent_pid=owner_pid)
```

三重安全阀(`gateway/status.py:1885-1892`):psutil 的 `is_running()` 自带 (PID, create_time)
身份校验;`child.ppid() == parent_pid` 说明父亲其实还活着 → 这不是孤儿,跳过;
先 SIGTERM、限时等、只对幸存者 SIGKILL。

### 3.11 重生风暴断路器

`record_start_and_check_storm`(`gateway/status.py:71-128`):把每次启动的 UTC 时间戳
append 到 `~/.hermes/gateway-starts.log`,窗口内启动次数超阈值就返回一个建议 backoff。
指数退避 `5.0 * 2**min(n-max, 6)`,上限 300s(`gateway/status.py:118-122`)。
文件做环形缓冲 `keep = max(max_starts * 4, 40)`(`:109`),不会无限增长。

唯一调用方在 CLI 启动路径(`hermes_cli/gateway.py:5098 @ 863e313`),配置来自
`gateway.respawn_storm.{max_starts,window_seconds}`,可被
`HERMES_GATEWAY_MAX_STARTS` / `HERMES_GATEWAY_START_WINDOW_S` 覆盖。

**取舍**:断路器在**被重启的那一方**里 sleep,而不是去劝阻 supervisor。这是唯一能在
"不控制 systemd 配置"的前提下打断风暴的位置 —— 代价是每次被误判都白等最多 5 分钟。
`_get_starts_log_path` 的 docstring 特意声明与 `restart_loop.json` 不是同一套(`:65-67`)。

### 3.12 `_get_process_hermes_home`:一个被 contextvar 坑出来的函数(issue #56986)

**事故经过**(`gateway/status.py:132-139 @ 863e313`):

```python
    """Return the process-level HERMES_HOME, skipping context-local overrides.

    Gateway identity files (PID, lock, runtime status, takeover/stop markers)
    must always live in the directory the gateway process was launched with.
    ``get_hermes_home()`` honors ``_HERMES_HOME_OVERRIDE`` contextvar used for
    per-session profile dispatch, which would route these files into the wrong
    profile directory when a profile-context task happens to be active at write
    time.  See issue #56986.
    """
```

什么输入 → 一个多 profile 网关,某个 profile 上下文的任务恰好在跑;
什么现象 → PID 文件 / 锁 / `gateway_state.json` 被写进**别的 profile** 的目录;
为什么 → 全局 `get_hermes_home()` 会读 contextvar,而"我是谁"这件事不该随任务上下文漂移;
怎么修 → 身份文件一律走 `_get_process_hermes_home()`,只认 `os.environ["HERMES_HOME"]`
和平台默认值,**绕过 contextvar**。

**对比**:`gateway/status_phrases.py:166` 用的是普通 `get_hermes_home()`(读 contextvar)——
这是对的,短语目录**应该**跟随 profile。**同一个仓库里两个"取家目录"的语义,分界线是
"这是身份还是配置"。** 这条区分值得进成品章。

测试守着:`tests/gateway/test_status.py:135 test_gateway_identity_files_use_process_home_not_context_override`。

---

## 4. `display_config.py` 配置面

### 4.1 解析顺序(四级,首个非 None 生效)

`gateway/display_config.py:211-249 @ 863e313`,顺序为
① `display.platforms.<platform>.<key>` → ①b `display.tool_progress_overrides.<platform>`(仅 `tool_progress`)
→ ② `display.<key>` → ③ `_PLATFORM_DEFAULTS[<platform>][<key>]` → ④ `_GLOBAL_DEFAULTS[<key>]` → `fallback`。

**只有 ①/①b/② 走 `_normalise`,③/④ 直接 return 原值**(内置默认已是规范形态)。

`streaming` 是唯一例外(`gateway/display_config.py:229-235 @ 863e313`):

```python
    # 2. Global user setting (display.<key>).  Skip display.streaming because
    # that key controls only CLI terminal streaming; gateway token streaming is
    # governed by the top-level streaming config plus per-platform overrides.
    if setting != "streaming":
```

即 `display.streaming` 对网关无效,只有 `display.platforms.<p>.streaming` 有效。

### 4.2 全局默认清单(12 键)

`gateway/display_config.py:33-71 @ 863e313`:

| 键 | 默认 | 语义 |
|---|---|---|
| `tool_progress` | `"all"` | 工具进度气泡:`off\|new\|all\|verbose\|log` |
| `tool_progress_grouping` | `"accumulate"` | `accumulate`=编辑同一条;`separate`=每工具一条 |
| `show_reasoning` | `False` | 是否显示思考摘要 |
| `reasoning_style` | `"code"` | `code\|blockquote\|subtext`(Discord 默认 subtext) |
| `tool_preview_length` | `0` | 工具参数预览截断长度(0=不限) |
| `streaming` | `None` | None=跟随顶层 streaming 配置 |
| `interim_assistant_messages` | `True` | 回合中途的真实助手评论是否单独发消息 |
| `long_running_notifications` | `True` | 长任务心跳(第三态 `generic` 走 yaml 短语) |
| `busy_ack_detail` | `True` | 忙时回执/心跳里是否带 `iteration N/M` |
| `busy_steer_ack_enabled` | `True` | steer 成功后是否回一条"已插入"确认 |
| `cleanup_progress` | `False` | 终稿落地后是否删除进度/心跳气泡 |
| `live_status` | `"full"` | typing 状态行:`full\|verb\|off` |

`live_status`(`:61-70`)与 `cleanup_progress`(`:55-60`)的注释是全文件最完整的两段设计说明,
分别解释了"为什么它独立于 tool_progress"和"为什么失败的回合不清理"。

### 4.3 平台档位表

四档定义(`gateway/display_config.py:76-79 @ 863e313`):

```python
# Tier 1 (high): Supports message editing, typically personal/team use
# Tier 2 (medium): Supports editing but often workspace/customer-facing
# Tier 3 (low): No edit support — each progress msg is permanent
# Tier 4 (minimal): Batch/non-interactive delivery
```

**分档的第一判据是"平台支不支持编辑消息"**,这就是 §2.6 那个"编辑优先、send 兜底"策略的
配置面镜像:不能编辑 → 每条进度都是永久污染 → 整档关掉。

20 个平台键的映射在 `gateway/display_config.py:121-181`(telegram / discord / slack / mattermost / matrix / feishu / signal / whatsapp / whatsapp_cloud / photon / bluebubbles / weixin / wecom / wecom_callback / dingtalk / email / sms / webhook / homeassistant / api_server)。四处逐平台微调:
- `telegram`(`:130-134`):TIER_HIGH 但 `tool_progress: off` + `busy_ack_detail: False` ——
  理由是"手机收件箱",但**保留** interim 与心跳(注释 `:124-131`)。
- `discord`(`:138`):TIER_HIGH + `reasoning_style: "subtext"`,因为 Discord 有原生的
  `-#` 小灰字元语义原语。
- `slack`(`:143-148`):TIER_MEDIUM 但 `tool_progress`/`long_running_notifications`/
  `busy_ack_detail` 全关,注释带 **hermes-agent#14663**(见 §7)。
- `api_server`(`:180`):TIER_HIGH + `tool_preview_length: 0`。

**档位字典是共享对象**:`_TIER_MEDIUM` 同时被 mattermost / matrix / feishu / whatsapp 四个键
引用(`gateway/display_config.py:149-155`),`_TIER_LOW` 被 8 个键引用。当前全部只读,
但任何对 `_PLATFORM_DEFAULTS[x]` 的原地写入会串到同档所有平台。见 §6 ◇C-6。

**档位字典不覆盖全部 12 键**:`reasoning_style`、`cleanup_progress`、`live_status`、
`busy_steer_ack_enabled`、`tool_progress_grouping` 都不在任何 `_TIER_*` 里(除 discord 的
显式 `reasoning_style`),因此这 5 个键在所有平台上都直落第 ④ 级全局默认。

### 4.4 `_normalise`:YAML 1.1 的裸 `off`

`gateway/display_config.py:256-311 @ 863e313`。核心问题:YAML 1.1 把裸 `off` 解析成布尔
`False`,而 `tool_progress: off` 用户本意是字符串 `"off"`。归一化把 `False → "off"`、
`True → "all"`(`:258-268`)。三态键 `live_status` 同理(`:288-299`)。

**未在 `_GLOBAL_DEFAULTS` 里、但 `_normalise` 认识的键**:`thinking_progress`(`:276`)。
它没有全局默认值,靠调用方传 `default=False`(`gateway/run.py:24453-24457`)。
于是 `OVERRIDEABLE_KEYS`(由 `_GLOBAL_DEFAULTS.keys()` 生成)不含它 —— 见 §6 ◇C-7。

同理 `friendly_tool_labels` 被 `gateway/run.py:24343` 按平台解析,但既不在 `_GLOBAL_DEFAULTS`
也不在 `_normalise` 的任何分支,走 `return value` 原样透传(`gateway/display_config.py:311`)。

### 4.5 谁读它

非测试调用点共 13 处:`gateway/run.py`(854 / 4488 / 9043-9074 / 17740 / 23933 / 24335 /
24343 / 24349 / 24372 / 24396 / 24425 / 24503 / 25015)、`gateway/slash_commands.py:3836-3837`
(`/verbose` 命令读当前 `tool_progress`)。`gateway/turn_context.py:103` 把
`resolve_display_setting` 作为字段注入 TurnContext,`gateway/run.py:24544` 完成注入 ——
这是 R7 记过的"把函数当依赖注入"模式的又一例。

---

## 5. R7B/R7 移交项:`status.py` 描述矛盾 —— 双侧证据与定案

### 5.0 先更正移交项的出处

简报说该项记在 `notes/r7b-90-doc-conflict-rulings.md`。**实际不在那里**:
`grep -i status notes/r7b-*.md` 在 R7B 全部 9 篇底稿里只有 1 处命中,且与本项无关
(`notes/r7b-20-base-first-layer-guard.md:126` 的斜杠命令列表)。

真正的移交项在 **R7**(`notes/r7-90-doc-conflict-rulings.md:215-219`):

> ### B3. gateway-internals.md Key Files 表 status.py 描述与其 docstring 不符 —— 记录待 R7C
> - 文档表:`gateway/status.py | Token lock management for profile-scoped gateway instances`
>   (gateway-internals.md:22);status.py 模块 docstring 自述为 PID 文件网关运行检测
>   (status.py:1-10)。status.py 属 R7C,本轮只记录矛盾线索,定案移交。

R7B 报告 `reports/round-7b-platform-integration.md:154` 把它误记为"R7B 新增的三项"之一。
**这是本学习项目自身台账的一处串轮,不是仓库问题**,在本轮报告里更正即可(照 R7B 处理
B-13 的先例)。

### 5.1 三侧原文

**侧 A —— `website/docs/developer-guide/gateway-internals.md:22 @ 863e313`**:

```
| `gateway/status.py` | Token lock management for profile-scoped gateway instances |
```

中文镜像同(`website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/developer-guide/gateway-internals.md:22 @ 863e313`):

```
| `gateway/status.py` | 面向 profile 范围的 gateway 实例的 token 锁管理 |
```

**侧 B —— 模块 docstring(`gateway/status.py:1-11 @ 863e313`)**,原文见 §0.1。
要点:自述为 "PID-file based detection of whether the gateway daemon is running",
且末句为 **"a property that will be useful when we add named profiles"** —— 将来时。

**侧 C —— 另一份文档 `website/docs/developer-guide/architecture.md:118 @ 863e313`**:

```
│   ├── status.py             # Token locks, profile-scoped process tracking
```

### 5.2 代码事实

1. **两件事都在,且 PID/运行态是主体**。按 §1.1 行数统计:token/scoped 锁 ≈ 500 行(22%),
   PID / 运行态 / 存活梯子 / 接管标记 / 风暴断路 ≈ 1750 行(78%)。
2. **"profile-scoped" 用在 token 锁上是反的**。scoped 锁**故意是机器级**,不在 HERMES_HOME 下
   (`gateway/status.py:178-184`,§3.8 已引),因为它的目的正是**跨 profile 互斥**。
   代码里明写(`gateway/status.py:575-576`):"Scoped credential locks are machine-global
   rather than HERMES_HOME-local."
   真正 profile-scoped 的是 PID 文件 / 锁 / `gateway_state.json` / 两种标记
   (`gateway/status.py:159-176` 全部经 `_get_process_hermes_home()`)。
   **文档把两组事实交叉配错了对象。**
3. **docstring 的将来时已过期**。named profiles 早已落地:`_profile_name_for_home`
   (`gateway/status.py:484-494`)、`_command_line_belongs_to_profile`(`:497`)、
   `write_runtime_status(served_profiles=...)`(`:1012-1016`)、
   `resolve_gateway_liveness(profile_dir=...)`(`:1175`)全都是多 profile 的一等公民机制,
   `website/docs/user-guide/multi-profile-gateways.md` 是一整篇用户文档。
4. **docstring 声称的用途也偏窄**。它说 PID 检测是 "used by send_message's check_fn to gate
   availability in the CLI"。实际消费方远不止:40 个非测试 `.py` 文件 `from gateway.status import`
   (`grep -rln "from gateway.status import\|from gateway import status" --include=*.py . | grep -v "^./tests/" | grep -v "^./gateway/status.py" | wc -l` → 40),
   `hermes_cli/web_server.py`(仪表盘)、`hermes_cli/kanban.py`、
   `agent/monitoring/gateway_health.py`、`gateway/platforms/api_server.py`(`/api/status`)、
   `gateway/platforms/base.py`(适配器状态上报)都在其中。

### 5.3 定案

**▲ C-1 成立(双侧都不准,程度不同)。**

- `gateway-internals.md:22`(及中文镜像):**证伪**。两处错:
  (a) 把 22% 的次要职责写成全部职责,漏掉了 78% 的 PID/运行态/存活判定;
  (b) "profile-scoped" 修饰错了对象 —— token 锁恰恰是机器级的。
- 模块 docstring `status.py:1-11`:**不算证伪,但已陈旧且偏窄**。它写的是模块的**起点**
  (只有 PID 检测那一版),既没有跟上后来加进来的锁、标记、存活梯子,也没有跟上 named
  profiles 从 "will add" 变成 "已有"。
- `architecture.md:118`:**最准的一份**("Token locks, profile-scoped process tracking",
  两件事都提到)。**同一仓库的两份开发者文档对同一文件给出精度不同的描述**,而更差的那份
  在更常被引用的 "Key Files" 表里。

**规律确认**:R7B 提出的"模块 docstring 也会说谎"在此**再次成立**,但形态不同 ——
R7B 的 B-5 是"路径引用腐烂",本例是**时间腐烂**:docstring 写于模块诞生时且从未随功能增长
重写,里面的将来时("when we add named profiles")就是化石层的时间戳。
**可迁移原则:模块 docstring 里出现将来时,就是它已过期的自证。**

---

## 6. ▲ / ◇ 候选清单

> **▲** = 文档所述与代码矛盾;**◇** = 代码有真实机制而文档无载。

### ▲ C-1 —— `gateway-internals.md` 的 status.py 描述

见 §5.3。双侧证据齐备,**结案**。

### ▲ C-2 —— `display_config.py` 内部档位横幅与实际赋值不符

**文档侧(代码自带注释,`gateway/display_config.py:153-155 @ 863e313`)**:

```python
    # Tier 3 — no edit support, progress messages are permanent
    "signal":          _TIER_LOW,
    "whatsapp":        _TIER_MEDIUM,  # Baileys bridge supports /edit
```

**代码侧**:`whatsapp` 被列在 "Tier 3 — no edit support" 横幅下,赋的却是 `_TIER_MEDIUM`
(Tier 2)。行内注释自己承认了原因("Baileys bridge supports /edit"),
且 `plugins/platforms/whatsapp/adapter.py:985 @ 863e313` 确实实现了 `async def edit_message`。

**定案**:横幅注释与其下第二行赋值矛盾。属**分组注释未随例外更新**的小范围失真,
不影响运行行为(赋值是对的),但会误导读表的人。记 ▲,程度轻。
对照:`whatsapp_cloud` 的例外(`:156-161`)就写了完整理由并**保持在 TIER_LOW**,
`gateway/platforms/whatsapp_cloud.py` 确实无 `edit_message` —— 那处注释是准的。

### ◇ C-3 —— 用户文档暗示 yaml 短语库是心跳的默认渲染,代码里它默认不生效

**文档侧(`website/docs/user-guide/messaging/index.md:452 @ 863e313`)**:

> Long-running gateway status lines ("still working…"-style heartbeats) draw from a phrase
> catalog. Built-in defaults ship in `gateway/assets/status_phrases.yaml`; ...

同页 `:741` 又描述默认心跳形态为:

> **`long_running_notifications`** stays **on** — a single edit-in-place "⏳ Working — N min"
> bubble updates every few minutes ...

**代码侧(`gateway/run.py:25037-25041`,§2.4 已引)**:只有 `_long_running_mode == "generic"`
才走短语库,否则走硬编码 `⏳ Working — N min`。而 `generic` 这个取值**在整个 website/ 下
没有任何一处提及**(`grep -rn "long_running_notifications" website/ | grep -i generic` 无结果)。

**定案**:记 **◇**(而非 ▲)—— 两段文档各自都没有说错,但拼在一起会让读者以为
"心跳默认从 yaml 取词"。真实开启方式(`long_running_notifications: generic`)**完全无文档**。
这是"两段真话拼出一个假印象 + 关键开关缺文档"的组合,是本轮最有用户影响的一条。

### ◇ C-4 —— `display.busy_steer_ack_enabled` 有实现、有默认值,website 无载

代码:`gateway/display_config.py:50-54`(注释 + 默认 `True`)、`:275`(`_normalise` 认它)、
`hermes_cli/config_defaults.py:1090-1093`(配置模板里有)。
文档:`grep -rn "busy_steer_ack_enabled" website/ README.md AGENTS.md` **零命中**。
用户能在生成的 config.yaml 注释里看到它,但站点文档搜不到。

### ◇ C-5 —— `clear_planned_stop_marker` 是死代码

`gateway/status.py:2150-2155 @ 863e313`:

```python
def clear_planned_stop_marker() -> None:
    """Remove the planned-stop marker unconditionally."""
    try:
        _get_planned_stop_marker_path().unlink(missing_ok=True)
    except OSError:
        pass
```

`grep -rn "clear_planned_stop_marker" .` 全仓(含 tests)只有这一处定义,**零调用**。
对照它的孪生 `clear_takeover_marker`(`:1749`)在 `gateway/run.py` 与
`_terminate_scoped_lock_owner_once`(`:2054`)都有调用 —— 说明这是"照孪生补齐 API"
留下的未接线分支。

### ◇ C-6 —— `_TIER_*` 是共享可变字典

`gateway/display_config.py:149-152` 等处把同一个 dict 对象赋给多个平台键。
当前全代码路径只读,但 `_PLATFORM_DEFAULTS[k][key] = v` 形式的任何修改会静默串档。
若要重实现,`types.MappingProxyType` 或 `dict(**_TIER_MEDIUM)` 都能封死。

### ◇ C-7 —— `OVERRIDEABLE_KEYS` 是无人使用的导出

`gateway/display_config.py:183-184 @ 863e313`:

```python
# Canonical set of per-platform overrideable keys (for validation).
OVERRIDEABLE_KEYS = frozenset(_GLOBAL_DEFAULTS.keys())
```

`grep -rn "OVERRIDEABLE_KEYS" .` 全仓唯一命中就是这一行。注释说 "(for validation)",
但**没有任何校验器读它**。而实际可按平台覆盖的键**多于**它:`thinking_progress`
(`gateway/display_config.py:276` 参与归一、`gateway/run.py:24453` 按平台解析)和
`friendly_tool_labels`(`gateway/run.py:24343`)都能被 `display.platforms.<p>` 覆盖,
却都不在 `_GLOBAL_DEFAULTS` 里。**这个"权威集合"既没人用、也不权威。**

### ◇ C-8 —— 同一句兜底文案有三份来源

`still on it`:`gateway/assets/status_phrases.yaml:2`、
`gateway/status_phrases.py:48`(`_FALLBACK_PHRASES["status"][0]`)、
`gateway/run.py:24413`(短语选择异常时的字面量)。
`one sec`:`yaml:34`、`gateway/status_phrases.py:49`、`gateway/run.py:24413`。

其中 `_FALLBACK_PHRASES` **在正常路径上完全被覆盖**:内置 yaml 用 `inherited_mode="replace"`
加载(`gateway/status_phrases.py:132-136 @ 863e313`):

```python
def _load_builtin_catalog() -> dict[str, list[str]]:
    catalog = {surface: list(phrases) for surface, phrases in _FALLBACK_PHRASES.items()}
    catalog_path = Path(__file__).resolve().parent / "assets" / "status_phrases.yaml"
    _merge_phrase_file(catalog, catalog_path, inherited_mode="replace")
    return catalog
```

yaml 两个 surface 都非空 → `_merge_phrase_mapping` 的 `replace` 分支
(`gateway/status_phrases.py:75`)整体替换 → `_FALLBACK_PHRASES` 只在 yaml 缺失/损坏时才露头。
这是刻意的"资产文件丢了也不崩"的三层保险,但代价是同一文案三处维护。

### ◇ C-9 —— 短语库完全没有 i18n

`status_phrases.py` 不 import 任何 `t()` / gettext,yaml 是裸英文。仓库有完整的
`locales/*.yaml`(en/de/es/fr/ja/ar/… 至少 10 种),`gateway/slash_commands.py:655-710`
大量使用 `t("gateway.status.*")`,但**心跳短语与 live status 短语都绕开了这套体系**。
`⏳ Working — N min` 同样是英文硬编码(`gateway/run.py:25040`)。
文档也未说明短语是英文-only。用户唯一的本地化手段是自己写一份 yaml 覆盖
(`mode: replace`)—— 这算是设计上的替代方案,但没写进文档。

### ◇ C-10 —— `classify_status_context` 的三个参数是装饰性的

`gateway/status_phrases.py:185-196 @ 863e313`:

```python
def classify_status_context(
    kind: str,
    *,
    tool_name: str | None = None,
    preview: str | None = None,
    args: Any = None,
) -> str:
    """Classify an internal gateway event into a Hermes UI-surface bucket."""
    normalized = str(kind or "").strip().lower()
    if normalized in {"heartbeat", "waiting", "long_running", "status"}:
        return "status"
    return "generic"
```

`tool_name` / `preview` / `args` **全部未被函数体使用**。`choose_status_phrase` 同样接收它们
并原样转发(`:215`)。这不是疏忽 —— docstring 明写是为 callback 签名兼容而留
(`:211-212`),而且**不使用它们正是安全属性本身**(不把工具参数插进短语)。
测试直接把它当安全断言来验:`tests/gateway/test_status_phrases.py:16
test_status_phrase_does_not_leak_raw_preview_or_args`。
记 ◇ 是因为"故意的空参数"从签名上看不出来,是易被后人"顺手用上"的陷阱。

### 命名漂移登记

| 现象 | 位置 |
|---|---|
| 模块叫 `status.py`,写的文件叫 `gateway_state.json`,字段叫 `gateway_state` | `gateway/status.py:38`;`_RUNTIME_STATUS_FILE = "gateway_state.json"` |
| 常量 `_RUNTIME_STATUS_FILE` / 函数 `write_runtime_status` 用 "status",落盘用 "state" | `gateway/status.py:38 / 980` |
| `gateway/status.py`(进程态)与 `gateway/status_phrases.py`(聊天文案)同前缀、零关系 | 两文件均无交叉 import |
| 下划线私有函数被大量跨模块导入:`_pid_exists` 出现在 **22 个**非测试 `.py` 文件里,`_try_acquire_file_lock` / `_release_file_lock` / `_snapshot_gateway_children` / `_pid_from_record` 同样被外部导入 —— "私有"命名已名不副实 | `cli.py`、`cron/executions.py`、`gateway/kanban_watchers.py:71`、`tools/*`、`plugins/platforms/*` 等 |
| `live_status`(display 键)vs `_live_status_mode`(run.py)vs `set_status_text`(适配器)vs `build_status_phrase`(agent/display.py):同一通道四个名字 | 见 §2.7 |

---

## 7. issue 溯源

| 编号 | 出现行 | 因果经过 |
|---|---|---|
| **bpo-14484** | `gateway/status.py:750` | 输入:Windows 上 `os.kill(pid, 0)`。现象:目标进程及其控制台进程组全被 Ctrl+C 杀掉。原因:CPython `os_kill_impl` 里 `sig=0` 与 `CTRL_C_EVENT` 数值相同,走 `GenerateConsoleCtrlEvent(0, pid)`。修法:`_pid_exists` 统一用 psutil / ctypes `OpenProcess+WaitForSingleObject`,POSIX 分支保留 `os.kill(pid,0)` 并加 `# windows-footgun: ok` 豁免标记(`:845`),配 `scripts/check-windows-footguns.py` 扫描器。 |
| **#42126** | `gateway/status.py:770`、`:820` | 输入:systemd `Restart=always` 下的 `hermes gateway start --replace`。现象:`--replace` 静默崩溃循环。原因:systemd 先拉起新进程后回收旧进程,旧进程长期 zombie;zombie 在进程表里,`psutil.pid_exists()` 为 True 但 SIGKILL 无效,replacer 等不到它死→exit 1→再被拉起。修法:psutil 路径与 stdlib 路径都显式把 zombie 判为已死。 |
| **#56986** | `gateway/status.py:139` | 输入:多 profile 网关,写身份文件时恰好有 profile 上下文任务在跑。现象:PID/锁/状态文件写进了别的 profile 目录。原因:`get_hermes_home()` 尊重 `_HERMES_HOME_OVERRIDE` contextvar。修法:新增 `_get_process_hermes_home()`,身份文件一律绕开 contextvar。 |
| **#71211** | `gateway/status.py:1191` | 输入:profile 作用域的仪表盘一次页面加载。现象:侧边栏"运行中"、Channels 页"未运行"。原因:`/api/status` 与 `/api/messaging/platforms` 各自手写存活梯子,后者没传 profile 路径,借用了别的 profile 的运行态。修法:抽出 `resolve_gateway_liveness` 作唯一真源,三级梯子 + `profile_dir` 贯穿全部三级。 |
| **PR #5646** | `gateway/status.py:1562` | 输入:`hermes gateway start --replace`(用户同时启用了 `hermes.service` + `hermes-gateway.service`)。现象:新旧网关 30 秒一轮互相扑杀。原因:PR #5646 为让"意外被杀"能被 `Restart=on-failure` 救活,把 SIGTERM 退出码定为 1;计划内接管用的也是 SIGTERM,systemd 分不清。修法:接管标记文件 —— replacer 在发 SIGTERM **之前**写下目标 PID+start_time,目标的 shutdown handler 读到自己被点名就 exit 0。 |
| **#29092** | `gateway/status.py:1638` | 输入:跨 HERMES_HOME 的 `--replace`。现象:标记被写进别的 profile 目录仍被消费(或反之,合法跨 home 接管被拒)。修法:新格式标记显式写 `target_hermes_home`,消费方校验它等于自己的 home;旧格式无此字段,退回"replacer home 相同"的老规则,新旧共存。 |
| **#34597** | `gateway/status.py:1670` | 输入:Windows / macOS 上的 `hermes gateway stop`。现象:被误判为意外退出(exit 1),然后被服务管理器复活。原因:`_get_process_start_time` 在无 `/proc` 平台返回 None,若强制要求 start_time 非空且相等,则每次 consume 都返回 False。修法:双方都有才比 start_time,任一方缺则只比 PID,靠 60s TTL 兜底;并要求 `consume_planned_stop_marker_for_self` 与 `planned_stop_marker_targets_self` 采用同一规则。 |
| **#33778** | `gateway/status.py:2140` | 输入:Windows 上的会话恢复路径。现象:planned-stop watcher 从不触发。原因:同 #34597 的 start_time 缺失问题。修法:同上;此行注释是防回归提醒("re-break the #33778 Windows session-resume path")。 |
| **hermes-agent#14663** | `gateway/display_config.py:142` | 输入:Slack 频道里跑长任务且 `tool_progress` 为 `new`/`all`。现象:频道被永久性进度行刷屏。原因:Bolt 发出的消息不像 CLI 那样可自由编辑,每条进度都成为永久消息。修法:Slack 默认 `tool_progress: off`(同时关掉 `long_running_notifications` 与 `busy_ack_detail`)。 |
| **#12029** | `gateway/run.py:24996`(切片外,与心跳直接相关) | 现象:一个 "running: delegate_task" 心跳气泡活得比产生它的那次 run 还久。修法:心跳每次醒来先调 `_should_emit_long_running_notification(session_key, agent, executor_task)`,不再持有会话槽位就 break。 |
| **#3459 / #3458** | `gateway/run.py:24434`(切片外) | `tool_progress: log` 模式的来源:把工具调用写进 `~/.hermes/logs/tool_calls.log` 而不是聊天。 |
| **#18859** | `gateway/relay/adapter.py:1216`(切片外,与 live status 相关) | relay 顶层 DM 无 thread 锚点导致心跳被静默丢弃;修法是从 per-chat inbound 缓存合成 thread 锚点,同时保留 flat 模式的 no-op。 |
| **#10454** | `gateway/stream_consumer.py:1821`(切片外,§2.8 引) | 现象:多次工具调用时最终回复被错误抑制。原因:commentary(模型的中途叙述)被当成终稿,置了 `_already_sent`。修法:commentary 只算 interim status update,不置 `_already_sent`。**注意此处的 "status" 指模型自己写的叙述文本,与本切片的三条通道都不是一回事。** |

---

## 8. 测试(作为行为规格)

### 8.1 对应测试文件

| 文件 | 行数 | 用例数 | 覆盖 |
|---|---|---|---|
| `tests/gateway/test_status.py` | 1130 | 51 | status.py 主力:PID 状态、运行态、start_time、terminate、scoped 锁、两种标记、cmdline 回退、损坏文件、active_agents、busy/drainable、风暴断路、锁文件权限、`normalize_updated_at`、存活梯子 |
| `tests/gateway/test_status_phrases.py` | 56 | 4 | 分类、**不泄漏 preview/args**、相对目录加载、自定义目录 |
| `tests/gateway/test_display_config.py` | 304 | 20 | 四级解析、遗留 overrides、YAML 归一、档位默认、配置迁移、per-platform streaming、cleanup_progress、grouping、reasoning_style、live_status |
| `tests/gateway/test_gateway_command_line_matcher.py` | 60 | 17 | `_gateway_command_subcommand` 的边界(引号路径、profile 剥离、`tui_gateway` 假阳性) |
| `tests/gateway/test_planned_stop_watcher.py` | 203 | 4 | 计划停止标记的 watcher 侧 |
| `tests/gateway/test_replace_child_reap.py` | 251 | 5 | `_snapshot_gateway_children` / `reap_gateway_children` |
| `tests/gateway/test_clean_shutdown_marker.py` | 201 | — | 接管/停止标记与关机路径 |

另有 40+ 个测试文件间接依赖 `gateway.status`(`tests/hermes_cli/test_gateway*.py`、
`tests/gateway/test_multiplex_*.py`、`tests/dashboard/*` 等)。

### 8.2 实跑结果(本轮验证)

```
$ HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
    tests/gateway/test_status_phrases.py tests/gateway/test_display_config.py
=== Summary: 2 files, 24 tests passed, 0 failed (100% complete) in 1.3s (8 workers) ===

$ HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
    tests/gateway/test_status.py tests/gateway/test_gateway_command_line_matcher.py \
    tests/gateway/test_planned_stop_watcher.py tests/gateway/test_replace_child_reap.py
=== Summary: 4 files, 77 tests passed, 0 failed (100% complete) in 1.7s (8 workers) ===
```

全绿,101 个用例。不需要任何模型凭据。

### 8.3 几条把设计意图钉死的用例

- `tests/gateway/test_status.py:135 test_gateway_identity_files_use_process_home_not_context_override`
  —— 把 issue #56986 的修法变成不可回归。
- `tests/gateway/test_status.py:194 test_runtime_status_running_pid_rejects_pid_reused_by_other_profile`
  —— 把 §3.5 的 profile 归属判定钉死。
- `tests/gateway/test_status.py:422 test_acquire_scoped_lock_race_second_acquirer_loses`
  —— 守住 §3.8 的墓碑 rename 竞态修复。
- `tests/gateway/test_status.py:539` / `:724` 两个同名的
  `test_consume_returns_true_on_windows_when_start_time_unavailable`
  —— 分别守 takeover 与 planned-stop 两条路径的 #34597 规则,**同名不同类**正是"两处必须一致"的表达。
- `tests/gateway/test_display_config.py:93 test_only_long_running_visibility_accepts_generic_mode`
  —— 把"`generic` 只对一个键放行"这条易被顺手推广的规则钉死。
- `tests/gateway/test_status_phrases.py:16 test_status_phrase_does_not_leak_raw_preview_or_args`
  —— 把 §6 ◇C-10 的"空参数即安全属性"变成可执行断言。

**缺口**:`resolve_status_phrase_catalog` 的路径沙箱(`_relative_path_under`,
拒绝绝对路径与 `..`,`gateway/status_phrases.py:87-100`)**没有专门的负例测试** ——
4 个用例里没有一个尝试 `path: /etc/passwd` 或 `path: ../../secrets`。这是安全边界无守卫的一处。

---

## 9. 重实现要点(造自己的 harness 时怎么做)

### 9.1 进程运行态(对应 status.py)

1. **存活凭据要两套并用**:一套是进程自愿写的(PID 文件,可能撒谎),一套是 OS 代管的
   (文件锁,进程一死自动释放)。**只信第一套必然误判"死得难看"的情况。**
2. **PID 永远配 start_time 用**。并且要提前想好"拿不到 start_time 的平台怎么办",
   全仓统一成一条规则(双方都有才比,否则只比 PID + 短 TTL),并在**每个**采用该规则的
   函数里重复写清楚 —— 一致性比 DRY 重要。
3. **进程身份判定不许用子串匹配**。至少要 shlex 分词 + 子命令位置解析,并区分
   "严格版给外部世界、宽松版只校验自家记录"两级。
4. **exit code 装不下意图,给信号加带外语义标签**。计划内的停止/接管,用短 TTL 的
   文件标记在发信号**之前**写下"目标 PID + start_time + 我是谁",接收方读了才知道
   这次 SIGTERM 该 exit 0 还是 exit 1。TTL 把"崩溃的写标记者"造成的伤害限制在一次。
5. **删陈旧锁用 `os.replace` 到墓碑,不用 `unlink`**。两个 racer 同时判"陈旧"时,
   unlink 不能定胜负,rename 可以。
6. **"身份"与"配置"用不同的家目录解析函数**。身份文件(PID/锁/状态)只认进程启动时的
   环境;配置(短语库/显示设置)才跟随 per-request 上下文。混用一次就是 #56986。
7. **状态文件写入用哨兵默认参数做字段级 merge**,让 `None` 保持"显式清空"的语义。
   多写者共享一个 JSON 文件时这是最小成本的方案。
8. **liveness 要有唯一真源,且要区分 down 与 unknown**。多个端点各写各的梯子,
   一定会在同一页面上互相打脸。`probe_error` 让告警能 fail-open。
9. **把踩过的平台陷阱变成 linter 规则**。`# windows-footgun: ok` + 扫描脚本这套组合,
   比在 code review 里靠人记住便宜得多。

### 9.2 状态消息 UX(对应 status_phrases + display_config)

10. **"让用户看到进展"要拆成多条独立通道**,按载体成本分级:
    永久消息(贵,默认关)/ 可编辑消息(中,编辑优先)/ ephemeral 指示器(便宜,默认开)。
    **同一条信息在不同平台落在不同通道上。**
11. **平台能力分档表比逐平台 if 好**。第一判据选"最能决定成本的那个能力"——
    这里是"支不支持编辑消息",因为不支持就意味着每条进度都是永久污染。
12. **进度气泡优先编辑同一条,失败退化为新发**,并且允许把它们在成功后删掉、
    失败时保留(失败时的面包屑正是排障线索)。
13. **能力探测用 `getattr(type(obj), name) is not Base.name`,不用 `hasattr`** ——
    区分"子类覆写了"和"继承了基类的 no-op"。
14. **状态短语必须与模型输出隔离**。签名可以收 `preview` / `args` 以兼容回调,
    但函数体一个字都不许用 —— 并写一条测试把这件事钉死。
15. **短语选择要有"最近 N 条不重复"的滑动窗口**,窗口内候选耗尽时退回全集(不要死锁)。
    窗口挂在回合上而非全局,避免长会话逐渐无词可用。
16. **用户可扩展的资产路径要做沙箱**:拒绝绝对路径与 `..`,并 `resolve()` 后
    `relative_to(base)` 二次确认。(并且**要为这个沙箱写负例测试** —— 本仓库缺这一条。)
17. **`append` / `replace` 两种合并模式**是这类"内置 + 用户扩展"目录的最小够用语义;
    内置资产自身用 `replace` 加载,可以让硬编码兜底只在资产缺失时露头。
18. **YAML 1.1 的裸 `off`/`on`/`yes`/`no` 会变成布尔** —— 任何字符串枚举型配置项
    都要有一个 `_normalise` 收敛层,否则 `tool_progress: off` 会变成 `False`。

---

## 10. 延伸与遗留

- **本切片与 R7 已读部分的接缝**:心跳/live status 的调用点全在 `gateway/run.py`
  的 `_agent_turn` 区段(24320-25070),R7 底稿 `r7-raw-run-10-agent-turn.md` 覆盖了该区段的
  骨架;本篇补齐了它调用的三个配置/短语模块。
- **未展开的邻接项**(不在本切片,列出以免留黑洞):
  - `agent/display.py` 的 `_TOOL_VERBS` / `build_status_phrase` / `build_tool_preview`
    —— live status 的真正文案源,属 agent 侧;
  - `agent/monitoring/gateway_health.py` 的 `emit_runtime_status_transition`
    —— `write_runtime_status` 的下游消费者;
  - `hermes_cli/web_server.py` / `hermes_cli/kanban.py` 对 `resolve_gateway_liveness` 的三处调用。
- **建议进成品章的三个"故事"**:①`os.kill(pid,0)` 的 Windows 陷阱 + linter 化(§3.2);
  ② exit code 装不下意图 → 文件标记(§3.9);③ 一次页面加载两个矛盾答案 → 唯一真源
  存活梯子(§3.7)。三者都符合"因果经过可复述"的标准。
