# r7 底稿 · gateway/run.py 第 13 段(23758–27146):回合真正执行 + 网关进程生命周期

> 学习对象:NousResearch/hermes-agent @ 863e31318553cda8ad61df681d08175364d4164b(只读)。
> 本段覆盖 GatewayRunner 第 10 段(代理模式、_run_agent 三层、_run_agent_inner 回合总装)
> 与模块尾部(planned-stop watcher、housekeeping、cron shim、start_gateway、main、os._exit 收尾)。
> 所有断言紧跟 `gateway/run.py:行号 @ 863e313` + 代码原文;跨文件引用给出对方文件:行号。

---

## 0. 段落总览与调用关系

本段是"一条消息如何变成一次 agent 回合"的最后一公里,加上"网关进程从 main() 到 os._exit 的全生命周期":

- 调用入口:`_handle_message_with_agent`(gateway/run.py:16276)在 17548 处 `await self._run_agent(...)`;
  `_run_agent_inner` 自己在 25765 处递归调用 `self._run_agent(...)` 处理排队后续消息。
- `_run_agent`(24112)→ profile 作用域包装 → `_run_agent_inner`(24265);
  若配置了代理 URL,`_run_agent_inner` 开头直接改走 `_run_agent_via_proxy`(23827)。
- `_run_agent_inner` 把回合执行体 `run_sync` 交给 `TurnRunner`(gateway/run.py:3670,`run_sync` 在 4396),
  自己负责:显示配置解析、TurnContext(gateway/turn_context.py:33)装配、五个后台 asyncio 任务、
  executor 线程调度、双层不活跃看门狗、结果收集与 already_sent 抑制、排队消息递归。
- 进程生命周期:`main()`(27021)→ `start_gateway`(26360)→ `runner.start()`(10664)
  → `wait_for_shutdown()`(13176)→ 协作式排空 cron/housekeeping → `_exit_after_graceful_shutdown`(27074)。

---

## 1. 代理模式三件套

### 1.1 `_get_proxy_url`(23742)——代理模式的开关

问题:Docker 容器擅长处理 Matrix E2EE(libolm 依赖),但本机文件/记忆/技能在宿主机上。
解法:网关可以退化为"平台 I/O 薄中继",把 agent 工作全部转发给远端 Hermes API server。

```python
# gateway/run.py:23742 @ 863e313
    def _get_proxy_url(self) -> Optional[str]:
        """Return the proxy URL if proxy mode is configured, else None.

        Checks GATEWAY_PROXY_URL env var first (convenient for Docker),
        then ``gateway.proxy_url`` in config.yaml.
        """
        url = os.getenv("GATEWAY_PROXY_URL", "").strip()
        if url:
            return url.rstrip("/")
        cfg = _load_gateway_config()
        url = (cfg.get("gateway") or {}).get("proxy_url")
        url = (url or "").strip()
        if url:
            return url.rstrip("/")
        return None
```

- 优先级:env(Docker 注入方便)> config.yaml;`rstrip("/")` 统一无尾斜杠。
- 调用点:`_run_agent_inner` 开头(24295)每回合都调,意味着改 config 热生效(`_load_gateway_config` 3145 有缓存策略,见其他段)。

**重实现要点**:① env 覆盖 config 的两级读取;② 返回值规范化(去尾斜杠);③ 每回合判定而非启动时判定,支持热切换;④ None 即"本地跑",不引入第三态。

### 1.2 `_build_stream_consumer_config`(23758)——两条 agent 路径共享的流式配置构造

问题:代理路径与本地路径都要构造 `StreamConsumerConfig`(gateway/stream_consumer.py:128),
之前两处调用点各自复制平台特判,重构后收敛到一个 helper,但两处对"平台不支持编辑消息"的语义不同,
用 `on_missing_cursor` 参数逐字保留:

```python
# gateway/run.py:23769 @ 863e313(docstring 节选)
        ``on_missing_cursor`` controls how platforms whose adapter sets
        ``SUPPORTS_MESSAGE_EDITING = False`` are handled — both semantics
        are preserved verbatim from the pre-refactor call sites:

        - ``"fallback"`` (proxy path): stream anyway with an empty cursor.
        - ``"raise"`` (in-process agent path): raise ``RuntimeError`` so
          the caller's ``except`` skips streaming entirely.
```

三个平台特判(全部有注释说明动机):

```python
# gateway/run.py:23795 @ 863e313
        _adapter_supports_edit = getattr(adapter, "SUPPORTS_MESSAGE_EDITING", True)
        if not _adapter_supports_edit and on_missing_cursor == "raise":
            raise RuntimeError("skip streaming for non-editable platform")
        _effective_cursor = scfg.cursor if _adapter_supports_edit else ""
        # Some Matrix clients render the streaming cursor
        # as a visible tofu/white-box artifact.  Keep
        # streaming text on Matrix, but suppress the cursor.
        _buffer_only = False
        if source.platform == Platform.MATRIX:
            _effective_cursor = ""
            _buffer_only = True
```

```python
# gateway/run.py:23806 @ 863e313
        # Fresh-final applies to Telegram only — other
        # platforms either edit in place cheaply (Discord,
        # Slack) or don't have the timestamp-on-edit /
        # edit-timestamp-stays-stale problem.
        # (Ported from openclaw/openclaw#72038.)
        _fresh_final_secs = (
            float(getattr(scfg, "fresh_final_after_seconds", 0.0) or 0.0)
            if source.platform == Platform.TELEGRAM
            else 0.0
        )
```

- QQ/微信这类 `SUPPORTS_MESSAGE_EDITING=False` 平台若照常流式,会先发一条永远无法更新的
  partial 消息,最终出现"partial + final 两条重复消息"(23788-23792 注释)。
- Matrix:保留流式文本但去掉光标(部分客户端把光标字符渲染成"豆腐块")→ `buffer_only=True`。
- Telegram 专属 fresh-final(编辑不刷新时间戳问题),移植自 openclaw/openclaw#72038。
- 副产物:Telegram 的 `pause_typing_for_chat` 闭包(23782-23787),作为 `on_before_finalize`
  传给 consumer——最终编辑前先停 typing,避免"正在输入…"盖在完整回复上。
- 与 `StreamConsumerConfig` 的字段一一对应(gateway/stream_consumer.py:128-153):
  `edit_interval / buffer_threshold / cursor / buffer_only / fresh_final_after_seconds / transport / chat_type`。
  `transport` 语义(gateway/stream_consumer.py:142-149 注释):auto/draft/edit/off,off 由网关在构造 consumer 前处理。

**重实现要点**:① 把"平台能力差异"收敛为一个构造函数,双语义用显式参数而非布尔魔法;② 不支持编辑的平台必须整体跳过流式(否则重复消息);③ 光标是配置项且可按平台清空;④ finalize 前钩子(暂停 typing)与 consumer 解耦成闭包;⑤ 重构保真:两个调用点的历史语义逐字保留并写进 docstring。

### 1.3 `_run_agent_via_proxy`(23827)——薄中继 + SSE 手工解析

实现分五步,全部在事件循环内(不需要 executor,因为没有本地阻塞 agent):

1) **依赖与配置守卫**(23850-23867):aiohttp 缺失或 URL 未配,直接返回带 ⚠️ 文案的结果 dict——
   降级为用户可见错误,不抛异常。
2) **代理密钥的作用域读取**(23869-23880):multiplex 下密钥是 per-profile 凭据,
   走 `agent.secret_scope.get_secret`;`UnscopedSecretError` 时回退 `os.environ`:

```python
# gateway/run.py:23869 @ 863e313
        # Scope-aware read: the proxy key is a per-profile credential; under
        # multiplex honor the installed scope's verdict (Slack pattern for
        # the unscoped default-profile loop).
        try:
            from agent.secret_scope import UnscopedSecretError, get_secret

            try:
                proxy_key = (get_secret("GATEWAY_PROXY_KEY") or "").strip()
            except UnscopedSecretError:
                proxy_key = os.getenv("GATEWAY_PROXY_KEY", "").strip()
        except Exception:
            proxy_key = os.getenv("GATEWAY_PROXY_KEY", "").strip()
```

3) **消息构造**(23887-23922):远端靠 `X-Hermes-Session-Id` 头维持自己的会话连续性,
   本地只发当前消息 + 紧凑历史(纯文本 user/assistant 轮),远端负责 tool replay 与 system prompt;
   body 是 OpenAI 兼容 `{"model": "hermes-agent", "messages": ..., "stream": True}`。
4) **平台流式装配**(23924-23971):按 `display` 配置解析流式开关
   (`resolve_display_setting` → gateway/display_config.py),构造 `GatewayStreamConsumer`
   (gateway/stream_consumer.py:157 附近),`on_missing_cursor="fallback"`;
   consumer 作为后台 task 运行,SSE 每个 delta 喂 `on_delta`。
5) **SSE 手工解析**(23981-24052):`ClientTimeout(total=0, sock_read=1800)`——总时长不限、
   读间隔 30 分钟;逐 chunk 解码拼 buffer,按 `\n` 切行,`data: ` 前缀 + `[DONE]` 哨兵;
   并有防 OOM 上限:

```python
# gateway/run.py:24049 @ 863e313
                        if len(buffer) > _GATEWAY_PROXY_SSE_BUFFER_MAX_CHARS:
                            raise ValueError(
                                "Proxy SSE stream exceeded max buffer size without a line boundary"
                            )
```

(`_GATEWAY_PROXY_SSE_BUFFER_MAX_CHARS = 16 * 1024 * 1024`,gateway/run.py:86。)

**代际守卫**贯穿全程:`_run_still_current()`(23882-23885,包一层 `_is_session_run_current`,
23041)在流中每 chunk 检查一次(24009),流结束后再检查一次(24077)——/stop、/new 把
generation 拨高后,旧流的结果整体丢弃,返回空 `final_response` 且 `history_offset=len(history)`
(告诉上层"历史无增量")。

错误处理的不对称(24054-24065):`CancelledError` 重新抛出(尊重取消);其他异常时若已有
partial 文本则**保留 partial 返回**,一无所有才返回 ⚠️ 错误。finally 里 `finish()` consumer 并
等 5s(24066-24074)。

返回结构(24097-24108):`api_calls=1`(远端才知道真实次数)、`response_previewed` 标记
"流式已把内容送达过",供上层 already_sent 判定;`messages` 只有 user/assistant 两条(远端持有完整轨迹)。

**重实现要点**:① 薄中继 = 平台 I/O 留本地、认知留远端,会话连续性用 header 传 session id;② SSE 解析必须带缓冲上限与 `[DONE]` 哨兵;③ 每 chunk 做代际检查,stale 流早退不浪费带宽;④ partial 结果好于错误文案,只有零输出才报错;⑤ 密钥读取尊重 profile 秘钥作用域;⑥ `sock_read` 超时(而非 total)匹配"长回合但不允许长时间静默"的语义。

---

## 2. Profile 多路复用包装:_run_agent / _profile_name_for_source / _resolve_profile_home_for_source

### 2.1 `_run_agent`(24112)——透明的 profile 作用域壳

```python
# gateway/run.py:24138 @ 863e313
        if not getattr(getattr(self, "config", None), "multiplex_profiles", False):
            return await self._run_agent_inner(
                message, context_prompt, history, source, session_id,
                session_key=session_key, run_generation=run_generation,
                _interrupt_depth=_interrupt_depth, event_message_id=event_message_id,
                channel_prompt=channel_prompt, moa_config=moa_config,
                persist_user_message=persist_user_message,
                persist_user_timestamp=persist_user_timestamp,
                message_type=message_type,
            )

        profile_home = self._resolve_profile_home_for_source(source)
        with _profile_runtime_scope(profile_home):
            return await self._run_agent_inner(...)
```

`_profile_runtime_scope`(gateway/run.py:1938)是两条缝的组合:
`set_hermes_home_override`(contextvar,经 `copy_context()` 传进 agent worker 线程)+
`set_secret_scope`(profile 的 .env 成为凭据权威源,**不写 os.environ**,避免子进程继承跨 profile 秘密,
1950-1954 注释)。单 profile 网关零行为变化——这是包装层存在的全部理由。

### 2.2 `_profile_name_for_source`(24161)——路由与作用域的一致性门

关键设计:路由结果被 `gateway.multiplex_profiles` 硬门:

```python
# gateway/run.py:24171 @ 863e313(docstring 节选)
        Gated on ``gateway.multiplex_profiles``: routing stamps
        ``source.profile``, which selects the session-key namespace and batch
        keys — but the profile-scoped agent run only activates under
        multiplexing. Without this gate, a configured route with multiplexing
        off would namespace batch/session keys by profile while the agent
        still runs in ``agent:main``, splitting the two out of agreement.
```

即:profile 路由影响两个东西——(a)session/batch key 命名空间,(b)agent 运行时作用域;
两者必须同开同关,否则 key 按 profile 分了、agent 却还在主 profile 跑,状态错位。
匹配规则委托 gateway/profile_routing.py 的 `match_profile_route`(最具体者胜:guild < channel < thread),
匹配异常降级为 None + warning(24194-24199),不炸回合。

### 2.3 `_resolve_profile_home_for_source`(24209)——三级解析 + 显式 profile 不存在的兜底

解析顺序(docstring 24212-24217):① `source.profile`(/p/<profile>/ URL 前缀、per-credential
adapter 归属、build_source 时的路由);② 兜底重跑 `_profile_name_for_source`(绕过 build_source
的 source);③ 活动 profile。显式指定但磁盘上不存在 → warning + 回退全局 HERMES_HOME(24241-24250);
任何异常 → 回退全局 HERMES_HOME(24252-24263)。

**重实现要点**:① 多租户作用域用 contextvar + with,不污染进程全局;② 路由与运行时作用域必须同一开关门,防止"命名空间分裂";③ 显式 profile 不存在要可观测(warning)且行为安全(回退默认);④ 单租户路径零开销直通;⑤ 秘钥隔离在 dict 层完成,不碰 os.environ。

---

## 3. `_run_agent_inner`(24265)——回合总装线

这是全仓最长的单个函数之一(24265-26039,约 1770 行)。历史上它内嵌 ~600 行闭包
(progress_callback ~250 行、send_progress_messages ~353 行),后被抽到 `TurnRunner`
(gateway/run.py:3670),闭包捕获的 ~20 个局部变量变成 `TurnContext`
(gateway/turn_context.py:33)字段。本段读到的是"装配 + 调度 + 收尾",执行体在 TurnRunner(另段覆盖)。

### 3.1 代理分流与工具集/显示配置解析(24294-24375)

- 24295:`if self._get_proxy_url(): return await self._run_agent_via_proxy(...)`——代理模式短路。
- 24310-24313:本地路径自己的 `_run_still_current`(与代理路径同构)。
- 24318-24321:`_get_platform_tools`(hermes_cli/tools_config.py)算出该平台启用的 toolsets,
  `agent.disabled_toolsets` 作减法——都会进 TurnContext 传给 agent 构造。
- 24333-24346:`set_tool_preview_max_len` / `set_friendly_tool_labels`(agent/display.py)按平台解析后设置进程级显示状态。
- **tool_progress 模式的优先级机(24348-24370)**:

```python
# gateway/run.py:24355 @ 863e313
        _tool_progress_configured = (
            "tool_progress" in _display_cfg
            or (
                isinstance(_platform_cfg, dict)
                and "tool_progress" in _platform_cfg
            )
            or (
                isinstance(_legacy_tp_overrides, dict)
                and platform_key in _legacy_tp_overrides
            )
        )
        progress_mode = (
            _env_tp
            if _env_tp and not _tool_progress_configured
            else (_resolved_tp or _env_tp or "all")
        )
```

语义:env 变量 `HERMES_TOOL_PROGRESS_MODE` 只在 config **完全没配**该项时生效;
config(全局键、平台键或 legacy overrides 任一)一旦出现,env 让位。默认 "all"。

### 3.2 显示表面三态:`_display_surface_mode`(24377)与状态短语

问题:网关有多个"可见性表面"(interim_assistant_messages、thinking_progress、
long_running_notifications),每个表面要支持 off/raw/generic 三态,且部分平台要求
**必须平台级显式配置才开**(Mattermost:全局 thinking 开着也不许漏进繁忙公共线程,24451-24452 注释)。

```python
# gateway/run.py:24384 @ 863e313
            """Return off|raw|generic for a gateway visibility surface."""
            if require_platform_override_for:
                current_platform = _gateway_platform_value(source.platform)
                platform_only = {
                    _gateway_platform_value(item)
                    for item in require_platform_override_for
                }
                if (
                    current_platform in platform_only
                    and not _has_platform_display_override(user_config, platform_key, setting)
                ):
                    return "off"
            value = resolve_display_setting(user_config, platform_key, setting, default)
            if isinstance(value, str) and value.strip().lower() == "generic":
                return "generic" if allow_generic else "off"
            return "raw" if bool(value) else "off"
```

`generic` 态配 `_generic_status_phrase`(24401):从 gateway/status_phrases.py 的目录中挑
不重复的自然短语("still on it"/"one sec" 兜底)。用途:企业环境不想暴露工具名/参数,
但仍要"活着"的信号。

派生开关:
- `tool_progress_enabled`(24417):`progress_mode not in {"off","log"}` 且非 WEBHOOK
  (webhook 无编辑能力,每条进度都会变成独立消息)。
- **live_status(24418-24432)**:Slack assistant 状态行。独立于 tool_progress——Slack 默认
  tool_progress off(永久行刷屏),但状态行是 ephemeral 的;渲染搭 `_keep_typing` 的便车,
  回调只是把短语存在 adapter 上,零额外平台 API 调用(24421-24424 注释)。
  适配器须有 `supports_status_text`。
- **log 模式(24433-24436)**:`progress_mode == "log"` 把工具调用写
  `~/.hermes/logs/tool_calls.log` 而非聊天(#3459 / #3458),gateway-only。
- `interim_assistant_messages`(24440-24448,默认 on,Mattermost 需平台级 override)与
  `thinking_progress`(24453-24458,默认 off,Mattermost 同上)各自独立。
- `needs_progress_queue = tool_progress_enabled or _thinking_enabled`(24459)——见 3.8 的历史 bug。

**重实现要点**:① 每个可见性表面独立三态(off/raw/generic),不与其他表面共享开关;② "敏感平台需平台级显式 opt-in"做成参数而非硬编码 if;③ generic 态用短语目录 + 最近去重,避免机械重复;④ env 变量只做 config 缺省时的后门;⑤ webhook 类无编辑平台一律禁进度。

### 3.3 语音确认、清理气泡、TurnContext/TurnRunner 装配(24472-24570)

- **Discord voice ack(24472-24491)**:bot 在语音频道且连续混音器激活时,本回合**第一次**
  工具调用要播一句"let me look into that"(叠在 idle 氛围床上)。此处只解析绑定的 guild
  (遍历 `_voice_text_channels` 匹配 `source.chat_id` 且 `voice_mixer_active`),真正回调是
  `TurnRunner.voice_ack_callback`(4302)。latch `_voice_ack_fired` 保证每回合至多一次。
- **cleanup_progress(24496-24517)**:`display.platforms.<platform>.cleanup_progress: true` 时,
  进度气泡/心跳气泡的 message id 收进 `_cleanup_msg_ids`,最终回复落地后删除;
  **失败回合不删**(气泡留作 breadcrumbs)。能力探测用 `getattr(type(adapter), "delete_message")`
  并排除基类默认实现(24509-24512)——duck-typed 最小 adapter 不炸。
- **TurnContext 装配(24523-24565)**:约 40 个字段一次性构造,随后 `TurnRunner(self, turn_ctx)`
  (24566),再把 `progress_callback` / `voice_ack_callback` 绑回 ctx(24569-24570)。
  turn_context.py:13-23 的注释讲清了抽取协议:闭包从不 `nonlocal` 重绑(唯一例外 `message`),
  可变状态沿用单元素 list 容器,mutation 通过共享对象可见——与闭包 cell 语义等价。

```python
# gateway/turn_context.py:74-78 @ 863e313
    # shared mutable containers; ``message`` is the ONE exception — the old
    # closure rebound it via ``nonlocal``, so the rebind sites now write
    # ``ctx.message`` and the outer body reads ``ctx.message`` afterwards.
    # ------------------------------------------------------------------

    # --- the ex-``nonlocal`` turn message (rebindable) --------------------
    message: Optional[str] = None
```

**重实现要点**:① 巨型闭包抽取的可靠配方:捕获变量 → dataclass 字段,共享可变性用容器不用拷贝,`nonlocal` 重绑点显式改写;② 单次触发的副作用(voice ack)用 latch list;③ "删除临时消息"必须探测真实能力且失败回合保留现场。

### 3.4 进度消息的线程元数据(24572-24657)——平台线程语义的博物馆

四个平台特判,每个都有事故背书:

- **Slack #18859**(24583-24610):用户配置 `reply_in_thread=false`(不要线程化回复)时,
  进度消息也不得合成线程——否则第一条进度消息创建的线程会被后续所有回复(包括最终答案)继承。
  Relay lane 与 native lane 的配置解析路径不同(`_effective_reply_in_thread` 方法 vs flat extra)。
- `_resolve_progress_thread_id`(定义于 gateway/run.py:783)统一决定进度消息进哪个线程。
- **Relay Discord auto-thread(24615-24631)**:频道首条消息在 ingest 时还没有 thread_id
  (线程诞生于 connector 的第一次 send)。connector 预先盖 `prospective_thread_id`
  (= 锚消息 id = 未来线程 id),凡带该锚做 reply_to 的 outbound 自动进线程。不带锚,
  进度/搜索状态气泡会平铺进**父频道**而最终回复进线程——2026-08-02 staging 复现。

```python
# gateway/run.py:24624 @ 863e313
        _relay_prospective_thread_id = (
            str(getattr(source, "prospective_thread_id", None))
            if source.platform == Platform.DISCORD
            and getattr(source, "delivered_via_upstream_relay", False)
            and getattr(source, "prospective_thread_id", None)
            and not source.thread_id
            else None
        )
```

- `_progress_metadata`(24632-24647):线程 id 与 source 一致时用 `_thread_metadata_for_source`,
  否则用 `_thread_metadata_for_target` 重建;无真实线程但有 relay 锚时,退化为
  `{"reply_to_message_id": event_message_id}`;最后过 `_non_conversational_metadata`
  (gateway/run.py:452,标记"这不是会话消息",各 adapter 据此走非会话渲染)。
- **Feishu / Mattermost**(24648-24657):话题内进度必须用 reply API + 触发消息 id 才留在话题里,
  所以 `_progress_reply_to` 只在这两个平台(或 relay 锚场景)携带 event_message_id。
- `_status_thread_metadata`(24753-24782)是同一套逻辑给 status/interim/审批/流式路径的复刻,
  Feishu 分支(24755-24763)显式带 `reply_to_message_id`。

**重实现要点**:① 线程路由是平台强语义,进度/状态/最终回复三路必须共享同一套解析,否则"进度漏出线程"类 bug 无穷尽;② "尚未诞生的线程"需要预写锚 id 的协议(prospective_thread_id);③ 用户的 no-thread 偏好必须传染给所有辅助消息;④ 辅助消息统一打非会话标记。

### 3.5 `write_tool_log`(24659)——log 模式的落盘器

```python
# gateway/run.py:24673 @ 863e313
            log_dir = _hermes_home / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_dir / "tool_calls.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setFormatter(RedactingFormatter("%(message)s"))
            tool_logger = logging.getLogger(f"hermes.tool_calls.{id(log_queue)}")
            tool_logger.setLevel(logging.INFO)
            tool_logger.propagate = False
```

- RotatingFileHandler 5MB×3——审计日志不无限膨胀;`RedactingFormatter`(agent/redact.py)保证
  秘密不落盘;logger 名带 `id(log_queue)` 防并发回合互踩 handler;`propagate=False` 不进主日志。
- 排水循环:`get_nowait` + 0.3s 空转;CancelledError 后 finally **再排一遍**残余(24697-24706
  注释:最后一轮迭代的晚到工具调用不丢),然后 removeHandler + flush + close。

**重实现要点**:① 审计日志三件套:轮转上限、脱敏 formatter、独立 logger;② 取消后必须二次排空队列;③ handler 生命周期与回合绑定(加了必须摘,摘了必须 close)。

### 3.6 Holder 单元与四座回调桥(24721-24790)

五个单元素 list 容器(24722-24735):`agent_holder / result_holder / tools_holder /
stream_consumer_holder / streaming_tts_consumer_holder`——run_sync 在 executor 线程里创建
agent/consumer,外层事件循环的 task 轮询这些 holder 拿引用。streaming_tts_consumer_holder
特别注明(24727-24731):**必须在事件循环线程创建持有者**,否则外层 finalize/interrupt 路径
引用它会 cross-scope NameError(#60671)。

四座 sync→async 桥全部抽到 TurnRunner,此处只发布 wiring:
- `_step_callback_sync`(TurnRunner 4323):agent 每步 → `hooks.emit("agent:step")`,
  经 `_loop_for_step`(24738)`call_soon_threadsafe`。
- `_event_callback_sync`(4350):生命周期事件(如 session:compress,上下文压缩切分会话后)。
- `_status_callback_sync`(4360):上下文压力等状态 → adapter.send。
- 审批桥:不在本段——在 `TurnRunner.run_sync` 内(gateway/run.py:5139-5200,
  "Register per-session gateway approval callback so dangerous command approval blocks the
  agent thread (mirrors CLI input())",tools/approval 的 sync→async 桥,危险命令审批用
  `send_exec_approval` 按钮或纯文本降级)。本段的贡献是把 `_status_adapter/_status_chat_id/
  _status_thread_metadata` 发布到 ctx(24787-24790),审批桥直接复用这套 status wiring。

### 3.7 流式 TTS 装配(24792-24828,#60671)

门条件四连:adapter 存在、`message_type == "voice"`(24801-24804,兼容 enum/str)、
该 chat 开了 auto-TTS(`_should_auto_tts_for_chat`)、`StreamingTTSConsumer` 构造后 `.active`
(有可用流式 TTS provider)。不满足则 holder 留 None → 走整文件 TTS 兜底路径(24825-24826 注释)。
consumer 拿的 metadata 是 `_status_thread_metadata`(语音回复进同一线程)。

### 3.8 五个后台 asyncio 任务(24835-25069)

**(a) send_progress_messages(24841-24843)**——门是 `needs_progress_queue` 而非 tool_progress:

```python
# gateway/run.py:24835 @ 863e313
        # Start progress message sender if enabled. Gate on needs_progress_queue
        # (tool_progress OR thinking_progress), not tool_progress alone: the
        # sender drains BOTH tool-progress lines and _thinking scratch bubbles.
        # With the old tool_progress-only gate, a thinking_progress:true /
        # tool_progress:off user had the callback queue _thinking messages that
        # no task ever drained — so they silently never appeared.
```

历史 bug 形态:生产者(callback)按 A∨B 入队,消费者按 A 启动——B-only 用户的消息静默消失。

**(b) write_tool_log**(24847-24848):log 模式才启动。

**(c) _start_stream_consumer(24854-24862)**:consumer 在 executor 线程内、agent 构造后才创建,
外层任务以 0.05s×200(至多 10s)轮询 holder,出现即 `await consumer.run()`。

**(d) track_agent(24866-24889)**:等 agent_holder 出现后,把 agent 挂到
`self._session_state(session_key).turn.agent`(供 /stop 等中断路径找到活 agent)。
**stale 晋升守卫**:generation 已被 /stop、/new 拨走时放弃晋升(24876-24884),
不动新回合的槽位——旧回合将在结果收集时被 stale 检查丢弃。

**(e) monitor_for_interrupt(24899-24961)**——主中断路径。0.2s 轮询,每轮**重新解析 adapter**
(重连后不持旧引用,24906-24908 注释)。核心是 peek-不-pop:

```python
# gateway/run.py:24917 @ 863e313(注释节选)
                            # Peek at the pending message text WITHOUT consuming it.
                            # The message must remain in _pending_messages so the
                            # post-run dequeue at _dequeue_pending_event() can
                            # retrieve the full MessageEvent (with media metadata).
                            # If we pop here, a race exists: the agent may finish
                            # before checking _interrupt_requested, and the message
                            # is lost — neither the interrupt path nor the dequeue
                            # path finds it.
```

语音中断先转写(`_transcribe_and_echo_pending_voice`)再 `agent.interrupt(pending_text)`——
语音打断携带真实转写而非空串/文件路径占位(24930-24935);无文本纯媒体则用
`_build_media_placeholder`。触发后设 `_interrupt_detected`(与主轮询循环的 backup 检查共享,
24897),并 `_stts.abort("barge-in")` 掐断正在播的流式 TTS(#60671)。
注释(24891-24896)申明层级:Level 1(base.py)在 `_handle_message()` 之前就拦截普通文本,
这里是 Level 2;主轮询循环里还有 backup 检查兜"monitor task 无声死亡 = 中断丢失"。

**(f) _notify_long_running(24979-25069)**:默认 180s 心跳(`HERMES_AGENT_NOTIFY_INTERVAL`,
经 config `agent.gateway_notify_interval` 在 2178-2179 导出为 env)。要点:
- 停止条件 `_should_emit_long_running_notification`(9524)防 stale 心跳泡泡活过回合本身(#12029);
  `_executor_task` 闭包变量可能尚未绑定,用 `except NameError` 容忍首个窗口(24996-25002)。
- 心跳文案:elapsed 分钟 + 当前工具;迭代计数默认给(`busy_ack_detail`,25014-25021),
  generic 模式换状态短语。
- **编辑优先**(24985-24989 注释):记住心跳消息 id,后续心跳 edit-in-place,编辑失败才发新条;
  新条 id 进 `_cleanup_msg_ids`。

**重实现要点(3.6-3.8 合并)**:① executor 线程产物用 holder 容器 + 外层轮询获取,禁止跨线程直接构造;② 中断监视 peek 不 pop,消费留给统一 dequeue 点;③ 生产者/消费者的启动门必须同一表达式;④ 后台任务都要防 stale(generation 守卫)与自杀检测(backup 检查);⑤ 心跳消息编辑复用而非刷屏,且带停止条件。

### 3.9 executor 执行与双层不活跃看门狗(25108-25343,#4815 / #76115)

**超时哲学**(25109-25117 注释):不用 wall-clock 上限——agent 活跃时可以跑几小时;
用 *inactivity*(`_touch_activity()` 在每次工具调用/API 调用/流 delta 时刷新)。
默认 1800s,`HERMES_AGENT_TIMEOUT`;900s 先警告一次(`HERMES_AGENT_TIMEOUT_WARNING`);0=无限。

**进程 baseline 与所有权(25124-25149)**:回合开始时快照
`process_registry.snapshot_running_ids(task_id)`(tools/process_registry.py)——
background=true 的进程故意活过成功回合,超时只杀**本回合新建**的子进程。
task_id 是 session 级不是回合级(#76115 review),所以 reap 前必须 `_turn_is_current` 再确认:
同 session 的替换回合已经开跑时,旧回合的 stale baseline 不得杀新回合的进程。

**worker 收尾即刻清除所有权(25151-25170)**:

```python
# gateway/run.py:25151 @ 863e313
            def _run_sync_with_timeout_lifecycle():
                try:
                    return run_sync()
                finally:
                    _turn_worker_done.set()
                    ...
                    _finished_agent = agent_holder[0] if agent_holder else None
                    if _finished_agent is not None:
                        _finished_agent._gateway_turn_process_task_id = ""
                        _finished_agent._gateway_turn_process_baseline = frozenset()
```

理由(25156-25166 注释):`.turn.agent` 要到**下一回合**认领时才重置为哨兵,期间
`_interrupt_and_clear_session()` 仍可达本 agent;不清标记的话,回合已结束后落地的显式 /stop
会误杀回合故意留下的后台进程(#76115)。

**双层看门狗**:
1. **守护线程 `_watch_gateway_turn_inactivity`(定义 2951,启动 25172-25188)**:独立于 asyncio——
   cgroup 内存回收可能饿死事件循环,正常超时轮询停摆,但清理不该跟着推迟(#76115,25126-25129 注释)。
   线程 `worker_done.wait(5s)` 轮询 `get_activity_summary()`,超时则调
   `_abandon_timed_out_gateway_turn`(2912):`cleanup_lock` 下 worker_done/timeout_fired 双检
   (2923-2926,tiebreak:worker 先完成则放弃),然后 `request_hard_interrupt`
   (agent/interrupt_compat.py:9)+ `_reap_gateway_turn_processes`(2841,内含 task_id 为空
   直接返回的守卫——空 id 会匹配并杀掉所有 sessionless 进程,2859-2863)。
2. **asyncio 轮询循环(25196-25343)**:`asyncio.wait({_executor_task}, timeout=5.0)`;
   worker 完成优先于 timeout_fired(25252-25259 注释:完成的回合已把回复写进会话历史,
   再报"agent inactive"会与存储的 transcript 矛盾——与 reaper 自己的 worker_done-wins
   tiebreak 呼应);警告阶段发一次 ⚠️;超时则起 reaper 线程(25295-25308,同一个
   `_abandon_timed_out_gateway_turn`,锁保证与守护线程互斥、幂等);
   每轮还带 backup 中断检查(与 monitor 任务逻辑相同,25311-25343)。
   无限模式(timeout=None)仍保留 5s 轮询,只为 backup 中断检查(25196-25199)。

executor 本身:`_run_in_executor_with_context`(21375)= `copy_context()` + `ctx.run(func)`——
`_set_session_env`(21333)经 `gateway.session_context.set_session_vars` 设的 contextvars
(platform/chat_id/session_key/async_delivery 等)随 context 拷贝进 worker 线程;
线程池是网关自有的 10-worker `ThreadPoolExecutor`(21386-21403),关闭中会拒绝新任务。

**超时诊断响应(25345-25406)**:从 `get_activity_summary()` 提取 last_activity/current_tool/
iteration,拼多行用户可读诊断(卡在哪个工具、几秒没动、如何调 `agent.gateway_timeout`、
可 /reset),`failed: True`;`messages` 尽量用 result_holder 里的部分轨迹。

**重实现要点**:① inactivity ≠ wall-clock:活跃度由 agent 侧 `_touch_activity` 自报,轮询只读;② 看门狗必须双层——asyncio 层可被资源压力饿死,守护线程兜底;③ 超时清理三元组(worker_done / timeout_fired / cleanup_lock)保证"完成 vs 超时"竞态只有一个赢家且完成优先;④ 杀进程要 baseline 差分 + 回合 current 检查 + 空 task_id 守卫三重限定;⑤ worker 收尾即刻清所有权标记,防已结束回合被 /stop 误伤;⑥ contextvars 跨线程传播用 copy_context,不用 os.environ(#24100,run_sync 4408-4421 注释)。

### 3.10 Fallback 模型驱逐守卫(25408-25442,#7130)

```python
# gateway/run.py:25411 @ 863e313(注释节选)
            # Skip eviction when the run failed — evicting a failed agent
            # forces MCP reinit on the next message for no benefit (the
            # same error will recur).  This was the root cause of #7130:
            # a bad model ID triggered fallback → eviction → recreation →
            # MCP reinit → same 400 → loop, burning 91% CPU for hours.
```

成功回合上,若 `_agent.model != 配置模型` 且不是用户主动 /model 切换
(`_is_intentional_model_switch`),驱逐缓存 agent → 下条消息重试主模型。
**归一化陷阱**(25420-25438):config 里 vendor 前缀模型(`deepseek/deepseek-v4-pro`)
在原生 provider 下 agent 侧存的是剥前缀的 `deepseek-v4-pro`,不归一化则每个成功回合都误判
"发生了 fallback"→ 驱逐 → prompt cache 全毁;聚合器(openrouter)保留 slug 不动
(hermes_cli/model_normalize.py 的 `_AGGREGATOR_PROVIDERS` / `normalize_model_for_provider`)。

**重实现要点**:① fallback 自愈 = 成功后驱逐重建,失败后绝不驱逐(否则重建风暴);② 比较模型 ID 前必须做与构造时相同的归一化;③ 用户主动切换要与故障 fallback 区分(intent 记录)。

### 3.11 流式 TTS 收尾(25448-25473,#60671)

`finish()` 在**外层事件循环线程**调(run_sync 提前 return 的路径也能收尾,25450-25452 注释);
`wait_complete(10s)` 排空音频;超时则无条件 `abort`:已出声则保留 suppression
(整文件兜底不得从头重播),没出声则允许整文件兜底(25453-25457、25464-25469)。
`suppress_whole_file` 时向 adapter 打 `(session_key, run_generation)` 完成标记
(`_mark_streaming_tts_completed_turn`,25470-25473),供发送层跳过整文件 TTS。

### 3.12 排队后续消息链(25475-25778)——回合结束不等于交互结束

顺序严格:

1. **dequeue + promote**(25479-25487):`_dequeue_pending_event`(2823)消费 adapter 的
   "next-up"槽;`_promote_queued_event`(7705)把 /queue 溢出队列的下一条顶进槽位——
   槽位始终占着,保 FIFO 顺序且中途 /queue 正确进溢出而非插队。
2. **中断消息过滤**(25488-25497):`result["interrupt_message"]` 若是控制哨语
   (`_is_control_interrupt_message`,3000,匹配 2833-2838 的六个 reason 串)则忽略——
   "Stop requested" 这类内部信号不能变成下一条用户输入。
3. **排队事件的语音转写**(25498-25521):与中断路径同款,drain 时转写 + 🎙️ 回显。
4. **leftover /steer**(25523-25531):steer 在最后一批工具之后到达(如最终 API 调用期间),
   agent 注不进去,放在 `result["pending_steer"]` 里,这里作为下一轮用户输入递送,不静默丢。
5. **斜杠命令安全网**(25533-25553):pending 文本是可解析命令(hermes_cli/commands
   `resolve_command`)则丢弃——命令绝不能作为 agent 输入;主修复在 base.py,这里兜
   interrupt_message 回退路径的漏网。
6. **draining 丢弃**(25555-25562):网关正在排空时不再接续。
7. **递归深度帽**(25575-25586,#816):`_MAX_INTERRUPT_DEPTH` 到顶后不递归,把事件塞回
   `merge_pending_message_event` / `queue_message` 排队,防 agent 连续失败 + 用户连发导致资源耗尽。
8. **正常完成 + 排队消息:先递送首个回复**(25588-25650):等 stream_task ≤5s;
   delivery 用**finalized 的 `response`** 而非原始 `result`(25605-25610 注释:空/失败归一化与
   final response 处理只在 task 结果里);`_stream_confirmed_final_delivery`(25071,见 3.14)
   确认流式已送达则跳过;intentional-silence 标记过滤(gateway/response_filters,25618-25632
   注释:该直发分支早于静默标记机制,不查会把字面量标记漏给用户)。
9. **post-delivery 回调释放**(25651-25675):从 adapter pop(防 base.py finally 双触发)
   后调用,新 API `pop_post_delivery_callback(generation=...)` 优先,legacy dict 兜底。
10. **递归准备**(25680-25763):
    - goal continuation 事件但 goal 已不活跃 → 丢弃(25692-25697)。
    - **先解析 next_session_key 再准备文本**(25698-25710 注释):
      `_prepare_inbound_message_text` 把原生图片路径按 key 缓存,递归 `_run_agent` 按
      next_session_key 消费——写读 key 不一致图片就丢。
    - 清 streaming-TTS completed-turn 标记(25723-25734,#60671:上一逻辑回合的完成标记
      不得抑制递归回合的流式 TTS)。
    - 重发 typing(25736-25747)。
    - **重挂 agent 缓存 message_count 基线**(25749-25763,#45966/#46237):首回合已把
      user+assistant 行刷进 SessionDB,跨进程一致性守卫会拿长大的磁盘计数对比 stale 的
      build-time 快照 → 在自己进程写入上重建 agent → prompt-cache 前缀被毁;
      `_handle_message_with_agent` 的重挂在整条 `_run_agent` 链 unwind 后才跑,对 in-band
      follow-up 来不及,所以这里先行 `_refresh_agent_cache_message_count`(23149)。
11. **递归 + 历史偏移保持**(25765-25778):`_run_agent(..., _interrupt_depth+1)`;
    返回 `_preserve_queued_followup_history_offset(result, followup_result)`(3574)——
    外层持有的是首回合的 history 快照,offset 语义必须相对它修正。

**重实现要点**:① 排队/中断/steer 三路 pending 统一在回合尾集中处理,一处入口;② 控制哨语、斜杠命令、draining 三道过滤在递归之前;③ 递归深度必须有帽,溢出退化为排队;④ 首回复递送用 finalized 结果并先确认流式是否已送达;⑤ 递归前的状态修复清单(session key、TTS 标记、typing、缓存基线)每项都对应一个真实 bug;⑥ 递归返回值要修正 history_offset 参照系。

### 3.13 finally 清理(25779-25847)

- 取消 progress/log/interrupt/notify 四任务(25781-25786)。
- stream_task:**无 consumer 快路径**(25790-25805 注释:非流式路径下等 5s 超时纯属浪费——
  曾是每个非流式测试 5 秒的成本),有 consumer 才 `wait_for(5s)` 让最终编辑落地。
- STTS 兜底 abort(25816-25825):正常收尾块被异常/取消跳过时仍有界收尾。
- **带代际守卫的槽位释放**(25829-25837):`_release_running_agent_state(session_key,
  run_generation=...)`(22802)——generation 已被 /stop、/new 拨走则不清(旧回合 unwind 不得
  clobber 新回合已装好的状态);该函数是对历史上散落的 `del self._running_agents[key]`
  漂移(有的漏 ts、有的漏 busy_ack)的收敛(22809-22822 docstring)。
- 最后逐一 await 被取消的任务吞 CancelledError(25842-25847)。

### 3.14 already_sent 抑制判定(25071-25106 + 25849-25991)——"别重复发,但更别不发"

这是本段最密的事故沉积层。谓词 `_stream_confirmed_final_delivery`(25071):

```python
# gateway/run.py:25080 @ 863e313
            if getattr(consumer, "final_response_sent", False):
                # A successful finalize call is not proof the *content* was
                # final: the edit may have carried only the last preview
                # snapshot while the tail generated between that snapshot and
                # stream completion never reached any API call (#71643).
                ...
                matcher = getattr(consumer, "delivered_final_matches", None)
                if callable(matcher):
                    try:
                        if matcher(final_text) is False:
                            return False
                    except Exception:
                        pass
                return True
            if previewed:
                has_delivered_text = getattr(consumer, "has_delivered_text", None)
```

三值协议:`delivered_final_matches(final_text)` 返回 False=证实不匹配(含 #78541 的
payload-less 多消息分片递送)→ 推翻 flag;None=无记录(非分片 legacy 路径)→ 维持
legacy 信任,不回退歧义超时去重(#51828/#33793 家族)。

主判定(25862-25991),仅对 `not response.get("failed")`:
- **空哨兵**:`final == "(empty)"` 或空 → 永不抑制(25855-25861 注释,#10xxx "agent stops
  after web search":流式发过 "Let me search…" 中间文本置了 already_sent,但那不是最终答案,
  抑制会让用户对着沉默发呆)。
- **#14238**:previewed 只有在 interim 预览递送的**正是**final 文本时才算数
  (`has_delivered_text(final_text)`)——压缩/会话切分期间的无关评论不能被当成最终回复。
- **#71643 stale finalize**:finalize 编辑成功但内容只是最后一次 preview 快照(快照与流完成
  之间生成的尾巴从未进任何 API 调用)。检测:`delivered_final_matches` 证伪 →
  `_stale_finalized`;修复:优先**原地编辑**流式消息为完整文本(25920-25964),编辑失败则
  放行正常 final send;
- **#78541**:多消息分片递送时 `message_id` 只是最后一片,拿完整文本编辑它会把已封片的头部
  文本重复进尾片——检测 `_turn_split_delivery` 则跳过 reconcile 编辑,走正常 final send
  (25935-25939)。
- **transformed**(25896-25899、25970-25991):插件钩子(transform_llm_output)在流式结束后
  追加了内容 → 永不抑制;有流式消息则编辑该消息补上转换后的内容,避免重复消息。

**重实现要点**:① "已送达"必须是内容级判定(payload 对账),调用成功 ≠ 内容最终;② 三值协议(False 证伪/True 证实/None 保持 legacy)让新校验不回归旧的去重行为;③ 空回复、失败回合、被转换回合三类永不抑制;④ 修复首选原地编辑,分片递送除外;⑤ 每条分支都打 log,便于事后判读是哪条腿抑制/放行。

### 3.15 清理气泡删除注册(25993-26039)

成功回合 + 有收集到的 id + adapter 支持 `register_post_delivery_callback` 时,注册回调:
最终回复**递送后**才批量 `delete_message`(快照 ids/chat_id/adapter/loop 后经
`safe_schedule_threadsafe`(agent/async_utils.py:34)调回事件循环);失败全吞。
失败回合根本不进这个分支(气泡留作 breadcrumbs)。

---

## 4. `_run_planned_stop_watcher`(26042)——Windows 的信号替身与 #34597 回归

问题链(docstring 26052-26071):Windows 上 `asyncio.add_signal_handler` 对 SIGTERM/SIGINT 抛
NotImplementedError → `hermes gateway stop` 的信号打不进 shutdown 路径 → drain 循环不跑、
`resume_pending` 不设 → 下次启动不知道要自动恢复会话(#33778,v0.13.0 会话恢复在原生
Windows 上碎裂)。修法:CLI 的 stop() 先 `write_planned_stop_marker(pid)`
(gateway/status.py:2057)再杀;本 watcher 线程 0.5s 轮询 marker,把文件系统标记翻译成与真实
SIGTERM 相同的 shutdown_handler 调用。POSIX 上是无害保险(信号处理器同步于内核投递,总是抢先消费 marker)。

**PID 校验(#34597)**:

```python
# gateway/run.py:26099 @ 863e313(注释节选)
                # A marker existing is NOT sufficient — it may have been
                # written for a PREVIOUS gateway instance (different PID)
                # and left behind because that process exited before the
                # CLI's stop() could clean it up. Firing the handler on a
                # stale/foreign marker drives the gateway into shutdown,
                # ... it's logged as an unexpected "UNKNOWN" exit
                # and the watchdog crash-loops the gateway (issue #34597,
                # a regression from PR #33798 which added this watcher
                # without the PID check).
```

`planned_stop_marker_targets_self()`(gateway/status.py:2088)非破坏性探测(匹配时不消费,
权威消费在 loop 线程的 handler 里做,校验 target_pid + start_time),且自愈式 unlink
陈旧/畸形 marker。触发方式:`loop.call_soon_threadsafe(shutdown_handler, None)`
(26123)——signal=None,handler 容忍。

**重实现要点**:① 平台信号缺口用"文件标记 + 轮询线程"补,且所有平台常开(便宜、防 CI 屏蔽信号);② 标记必须绑定目标 PID+start_time,存在 ≠ 针对我;③ 探测与消费分离:轮询线程只探测,消费权威在事件循环线程;④ 陈旧标记要自愈删除,否则 wedge 新实例。

## 5. `_start_gateway_housekeeping`(26131)——60s 家务线程逐项

设计动机(docstring 26134-26143):从历史 `_start_cron_ticker` 拆出——cron **触发器**要能换成
外部 provider(scale-to-zero 的外部 provider 根本没有 60s 循环),而这些网关家务无论谁触发
cron 都要跑,所以自己拥有自己的循环。tick 计数 + 模数分频:

| 项 | 频率 | 内容与证据 |
|---|---|---|
| 频道目录 | 5 tick(5min) | `build_channel_directory(adapters)`(gateway/channel_directory.py)是 async(Slack web 调用),从线程经 `safe_schedule_threadsafe` 调度到网关 loop,`fut.result(timeout=30)` 等待以便失败仍被 except 记录(26176-26192) |
| 媒体缓存×5 | 60 tick(1h) | Image/Document/Audio/Video/Screenshot 五个 cleanup 函数(gateway/platforms/base.py)统一 `(name, fn)` 元组循环,`max_age_hours=24`(26163-26201) |
| paste 清扫 | 60 tick | `hermes debug share` 过期粘贴,`_sweep_expired_pastes`(hermes_cli/debug.py)(26203-26212) |
| curator | 60 tick 轮询 | `maybe_run_curator(idle_for_seconds=inf)`(agent/curator.py)——内部按 `config.interval_hours`(默认 7 天)门,轮询率≠工作率(26214-26227) |
| skills 同步 | 同上 | `maybe_pull_skills` + `maybe_pull_org_skills`(tools/skills_sync_client.py);org 版门在真实 org 成员身份上,solo 账户不触网(26229-26244) |
| 会话自动归档 | 60 tick 轮询 | `sessions.auto_archive` 配置门 + `maybe_auto_archive` 内部 `min_interval_hours` 门;**自开自关 SessionDB**——SQLite 连接线程绑定,本函数跑在离 loop 线程(26246-26266) |
| 内存修剪 | 每 tick | `trim_memory(reason=...)`(hermes_cli/mem_trim.py),helper 自带配置门+冷却;失败记 debug 而非 warning——持久性失败否则每 60s 刷一条 warning(26268-26285) |

**重实现要点**:① 单线程 + tick 模数,而非 N 个定时器;② 每项独立 try/except + debug 级日志,任何一项烂掉不拖垮循环也不刷屏;③ "轮询率"与"工作率"分离——真实节奏由被调 helper 的内部门管;④ async 工作从家务线程回 loop 要有界等待;⑤ 线程绑定资源(SQLite)在使用线程内开关。

## 6. cron shim、drain 常量与 `_await_thread_exit`(26291-26345,#58818)

`_start_cron_ticker`(26291)已是废弃薄壳:`InProcessCronScheduler().start(...)`
(cron/scheduler_provider.py:162);保留只为外部引用(hermes_cli/debug.py:81 的文档字符串
提到它)。真正的 provider 解析在 start_gateway(见 §8)。

两个 drain 常量的推导都写成注释:`_CRON_SHUTDOWN_DRAIN_TIMEOUT = 65.0`(26311,cron 线程
`future.result(timeout=60)` + 余量);`_HOUSEKEEPING_SHUTDOWN_DRAIN_TIMEOUT = 35.0`
(26322,频道目录刷新 `fut.result(timeout=30)` + 余量——旧的 5s join 会把进行中的刷新腰斩)。

`_await_thread_exit`(26325)是 #58818 的修复本体:

```python
# gateway/run.py:26330 @ 863e313(docstring 节选)
    A synchronous ``thread.join()`` here would freeze the event loop — fatal
    for the cron ticker, whose in-flight delivery is a coroutine scheduled onto
    *this* loop via ``safe_schedule_threadsafe``. Blocking the loop deadlocks
    that delivery (the loop can never run it), so ``join(timeout=5)`` always
    times out and the message is silently dropped on restart (#58818).
```

死锁三角:cron 线程阻塞在 future.result → future 要 loop 跑协程 → loop 阻塞在 join(cron 线程)。
解:`is_alive()` + `await asyncio.sleep(0.1)` 轮询,loop 保持活着让递送完成。

**重实现要点**:① 任何"线程等 loop、loop 等线程"的拓扑禁止同步 join;② drain 超时必须 ≥ 被等线程内部最长阻塞 + 余量,并把推导写在常量旁;③ 废弃 API 用一行 shim 保引用兼容。

## 7. `_shutdown_gateway_health_export`(26348)

幂等收尾:取 `runner._gateway_health_export_runtime`(在 runner.start 内 10793 创建),
先置 None 再 `runtime.shutdown()`,异常仅 debug。被 start_gateway 的每条早退路径调用
(26821、26824、26837、26868)——OTLP 导出线程不能被早退路径遗留。

## 8. `start_gateway`(26360)——启动入口全流程

按执行顺序:

**(1) boot 指纹**(26374-26379):`record_boot_fingerprint()`(gateway/code_skew.py)——
长活进程期间 `git pull` 后,内存模块与磁盘不一致可被检测,危险操作(模型切换)拒绝而非崩在
stale 模块上。

**(2) 单实例守卫与 --replace 接管**(26381-26541):
- `get_running_pid()`(gateway/status.py:2158)发现同 HERMES_HOME 已有实例:无 --replace 则
  报错返回 False(26528-26541,含用户指引文案);PID 文件按 HERMES_HOME 作用域,
  多 profile 各自 HOME 天然并存(26382-26385 注释)。
- --replace 流程:写 takeover marker(gateway/status.py:1686;让被杀者的 handler 识别为计划
  接管、exit 0——否则 systemd Restart=on-failure 复活它与新实例互搏,26402-26406 注释)→
  **先快照对方子进程**(`_snapshot_gateway_children`,26412-26422:对方一退,孤儿被 reparent
  就找不到了;POSIX 上残存 adapter 子进程会占 scoped token 锁堵死替换者)→ SIGTERM →
  10s 等待(`_pid_exists`,26440-26449;注:Windows 上 `os.kill(pid,0)` 不是 no-op,用句柄检查)
  → 不退则 SIGKILL 并**再确认真死**:

```python
# gateway/run.py:26462 @ 863e313(注释节选)
                # Confirm the force-kill actually reaped the process before we
                # clear its PID file / scoped locks. SIGKILL can fail to take
                # (e.g. an uninterruptible-sleep or zombie-reaping parent), and
                # if we blindly clear the metadata and start a fresh instance
                # we end up with two live gateways fighting over the same
                # token — the duplicate-gateway failure in #19471.
```

- 确认死后:`reap_gateway_children`(gateway/status.py:1876)清孤儿 → remove_pid_file +
  强制 unlink(旧进程崩溃残留)→ 清 takeover marker(SIGKILL 时对方没消费)→
  `release_all_scoped_locks(owner_pid, owner_start_time)`(gateway/status.py:1514;
  Ctrl+Z 停住的进程不释放锁,26515-26517 注释)。

**(3) 启动杂项**(26543-26589):bundled skills 同步;`setup_logging(mode="gateway")`
(hermes_logging,幂等);启动安全姿态审计(root/弱 SSH/无认证 listener 警告——
"2026 年 6 月 MCP-config persistence campaign 受害者从未得到的信号",26556-26559 注释);
-v/-q 驱动的 stderr handler(RedactingFormatter)。

**(4) runner 构造**(26591-26595):`GatewayRunner(config)`;
`_platform_lock_takeover_on_start = bool(replace)`——--replace 是**显式启动权限**而非持久
重连策略,runner 把它限定在冷启动 adapter 连接,后台重连 watcher 启动前清除(26592-26594 注释)。

**(5) shutdown_signal_handler**(26604-26697)——信号语义仲裁器:
- takeover marker 命中 → 计划接管,exit 0;
- SIGINT 或 planned-stop marker 命中 → 计划停止;
- 否则 `_signal_initiated_shutdown = True` 并镜像到 runner(#42675:非计划信号不得把
  `gateway_state=stopped` 持久化——容器/s6 重启时的 SIGTERM、OOM、裸 kill 不代表用户想停,
  26662-26669 注释);
- **shutdown 取证**(26634-26696):`snapshot_shutdown_context`(gateway/shutdown_forensics)
  纯 stdlib+/proc、<10ms——前实现同步跑 `ps aux` 堵 loop 3s(PR #15826);一行 key=value
  warning 记"谁杀的我";重量级诊断(ps auxf/pstree/dmesg)`spawn_async_diagnostic` 到
  **detached 子进程**——本 cgroup 被拆时它还能写完盘;
- 末尾 `asyncio.create_task(runner.stop())`(12659)。

**(6) loop 级异常处理器**(26702-26716):`_gateway_loop_exception_handler`(定义 533)。
#31066/#31110:后台任务里未处理的 `telegram.error.TimedOut` 等瞬态网络异常传到 loop 会杀死
整个进程(拖死同 runner 的所有 profile),systemd 5s 后重启但当前回合已丢。修复刻意窄:
只吞已知瞬态网络错误(带全栈日志),其余转默认 handler。

**(7) 信号注册**(26718-26730):仅主线程注册 SIGINT/SIGTERM/SIGUSR1(restart),
全部 try/except NotImplementedError(Windows);非主线程只打 log。

**(8) planned-stop watcher 线程启动**(26744-26751):见 §4。

**(9) PID 文件在 adapter 之前认领**(26753-26782):

```python
# gateway/run.py:26753 @ 863e313(注释节选)
    # Claim the PID file BEFORE bringing up any platform adapters.
    # This closes the --replace race window: two concurrent `gateway run
    # --replace` invocations both pass the termination-wait above, but
    # only the winner of the O_CREAT|O_EXCL race below will ever open
    # Telegram polling, Discord gateway sockets, etc.
```

三重闸:再查 `get_running_pid()`(启动期间冒出的新实例)→ `acquire_gateway_runtime_lock()`
(gateway/status.py:868)→ `write_pid_file()`(954,O_CREAT|O_EXCL,FileExistsError=输了竞态,
回滚 runtime lock);atexit 注册两个释放。

**(10) 生命周期台账 NS-608**(26784-26793):`record_startup`(gateway/lifecycle_ledger)——
上一世是否 SIGKILL/OOM/VM 死(没走任何退出路径)在此上报,然后为本世认领哨兵;
放在 PID/锁认领之后,--replace 输家不得碰哨兵(26786-26788 注释)。

**(11) 其余启动件**(26795-26815):nous auth keepalive;`_ensure_windows_gateway_venv_imports`
(393);**MCP 发现进 executor**(26803-26813,#16856:`discover_mcp_tools` 内部有 120s 阻塞
等待,在 loop 线程调会冻结 Discord shard 心跳/Telegram 轮询)。

**(12) runner.start 与早退路径**(26817-26868):
- `runner.start()`(10664)抛任何 BaseException → 先 `_shutdown_gateway_health_export` 再 raise;
- 成功后恢复上次 shutdown 冲刷的 pending 消息(`recover_pending_to_db`,
  gateway/shutdown_flush,#72680);
- `should_exit_cleanly`(6664)+ `exit_code` → `raise SystemExit(code)`:#51228——致命配置错
  以 78 出走,s6 finish 脚本把 78 翻译成 125 停止 supervisor 重启循环;若这里 return True,
  main() exit 0,finish 脚本的 `[ "$1" = "78" ]` 永不命中,s6 照样 crash-loop;
- `not runner._running`(启动被 restart/shutdown 有意中止):走 `wait_for_shutdown` +
  MCP 关闭 + exit_code,但**不启动 cron**(26850-26868)。

**(13) cron provider + 家务线程**(26870-26933):
- `resolve_cron_scheduler()`(cron/scheduler_provider.py:122):`cron.provider` 配置,缺省/
  加载失败/`is_available()==False` 全部回退内建 ticker——"cron 绝不能没有触发器"。
- **多 profile cron #69377**(26880-26905):multiplex 下把 `profiles_to_serve` 的 home 列表
  传给内建 ticker,否则只有进程全局 HERMES_HOME 被 tick,副 profile 的任务显示"scheduled、
  next_run_at 有效"却永不执行(没有 ticker 拥有那个 store);
- `can_dispatch`(26907-26912):仅内建 ticker 接受本地 external-drain 门
  (`not (runner._draining or runner._external_drain_active)`)——外部 provider 拥有自己的
  远程调度契约;
- cron 线程 + housekeeping 线程共享同一个 `cron_stop` Event(26925 注释)。

**(14) systemd watchdog**(26935-26940):READY 只在 adapters、cron、housekeeping 全部到达
运行边界后发;缺配置则 watchdog 禁用而不改行为。

**(15) 关停序列**(26942-27017):`wait_for_shutdown()`(13176)→ 停 keepalive →
`should_exit_with_failure` 判定 → `cron_stop.set()` + `provider.stop()` +
`_await_thread_exit`(cron 65s、housekeeping 35s,协作式,见 §6)→ 停 watcher 线程 →
`shutdown_mcp_servers()` → `exit_code` 传播;两条尾判定:
- `_signal_initiated_shutdown and not runner._restart_requested` → return False(=exit 1),
  让 systemd Restart=on-failure 复活(覆盖 hermes update 中途杀、外部 kill、WSL2 异常信号,
  26994-27001 注释);
- `runner._restart_via_service` → `SystemExit(75)`(历史服务重启路径的非零码)。

**重实现要点(start_gateway)**:① 单实例三重闸(pre-check → runtime lock → O_EXCL PID 文件)且认领先于任何外部连接;② --replace 是完整协议:takeover marker(退出码语义)+ 子进程快照先于杀 + SIGKILL 后确认真死 + 孤儿 reap + 锁清理;③ 信号语义靠 marker 区分"计划/接管/意外"三类,意外→exit 1 交给 supervisor;④ 取证要分两级:同步 <10ms 快照 + detached 子进程重诊断;⑤ 所有会阻塞的启动件(MCP 发现)进 executor;⑥ 退出码是与 supervisor 的协议(78/75/1/0),早退路径也必须精确传播;⑦ loop 异常处理器窄吞瞬态网络错误,防单条后台异常杀进程。

## 9. `main()`(27021)与 `_exit_after_graceful_shutdown`(27074,#53107)

main():Windows stdio UTF-8 → argparse(--config/-v)→ 可选 YAML 构造 GatewayConfig →
`asyncio.run(start_gateway(config))`;SystemExit 显式捕获并归一化 code
(None→0/int→原值/str→1,27063-27070),**一切出口汇入 `_exit_after_graceful_shutdown`**:

```python
# gateway/run.py:27046 @ 863e313(注释节选)
    # start_gateway() performs the full graceful teardown ... Force-exit
    # afterwards so a wedged non-daemon worker thread (e.g. a ThreadPoolExecutor
    # tool/LLM call blocked with no timeout) cannot block interpreter
    # finalization (Py_FinalizeEx joins all non-daemon threads, incl.
    # concurrent.futures' _python_exit) and strand the gateway half-shut down
    # with the supervisor unable to restart it (#53107).
```

`_exit_after_graceful_shutdown`(27074)的收尾顺序有讲究:
1. flush stdout/stderr;
2. **先释放 PID + runtime lock 再排日志**(27111-27114:日志排空有界但 wedged 磁盘下仍可能吃满
   timeout,锁绝不能被 strand;os._exit 跳过 atexit,而早退 SystemExit 路径从没跑过
   `_stop_impl`,atexit 曾是它们唯一的释放点——现在这里显式幂等释放);
3. 生命周期哨兵 `mark_exited(exit_code, reason="graceful_shutdown")`——所有优雅退出的单一漏斗,
   下次启动的"不干净死亡"检测只对真 SIGKILL/OOM 触发;内部有所有权守卫,--replace 旧世不会
   clobber 新世刚认领的 running 哨兵(27121-27125);
4. `drain_log_queue(timeout=1.0)`(hermes_logging)而**不是** `flush_log_queue`:listener 若
   wedged 在轮转锁上(正是异步日志要幸存的故障),无界 stop() join 会把关停重新冻住
   (27131-27136);
5. `os._exit(exit_code)`。

**重实现要点**:① 优雅收尾完成后用 os._exit 兜底,防非守护线程卡死解释器终结;② os._exit 跳过 atexit,故 atexit 承担的每一项(PID、锁、日志排空、哨兵)都要在此显式重做且幂等;③ 排空必须有界(wedged listener 不能反噬关停);④ 锁释放排在一切可能耗时的动作之前;⑤ SystemExit 的 code 归一化遵循 CPython 语义(str→1)。

---

## 10. 文档-代码冲突候选

1. **memory_monitor 无生产调用点**。gateway/memory_monitor.py 模块 docstring 声称
   "The timer runs in a background thread and shuts down cleanly with the gateway"、
   "Config: ``logging.memory_monitor`` in ``config.yaml``"(gateway/memory_monitor.py:13-14、27-28
   @ 863e313),但全仓 grep 显示 `start_memory_monitoring`(gateway/memory_monitor.py:139)只被
   tests/gateway/test_memory_monitor.py 调用——`start_gateway` 与 `runner.start()` 均无启动点。
   即该基线上内存监控是**接线未通电**的模块(本轮任务描述中的"memory_monitor 启动点"在
   start_gateway 里并不存在)。定案:◇ 文档(模块自述)超前于代码。
2. **`main()` 的 `--verbose` 旗标是死的**。gateway/run.py:27035 定义
   `parser.add_argument("--verbose", "-v", action="store_true", ...)`,但 27061 调用
   `start_gateway(config)` 未传 `verbosity`,`args.verbose` 从未被读——直接跑
   `python -m gateway.run -v` 不会提升 stderr 级别(真正的 verbosity 传递在 hermes_cli 的
   gateway 子命令里)。定案:▲ 入口自带的 CLI 文档(help 文案)与行为不符。
3. **"env var takes precedence" 注释过时**。gateway/run.py:25115-25117 注释称
   `agent.gateway_timeout` 或 `HERMES_AGENT_TIMEOUT`"env var takes precedence",但
   `_load_gateway_config` 在 2166-2179 依 PR #18413("config.yaml is the documented,
   authoritative source ... it unconditionally wins over .env values")无条件把 config 值写进
   `os.environ["HERMES_AGENT_TIMEOUT"]`——两者同时设置时**config 胜**。同样文案也出现在
   `gateway_notify_interval`(24965-24967)。定案:▲ 行内注释滞后于 #18413 的语义反转。
4. `_start_cron_ticker` docstring(26296-26299)称保留是为 "external caller or test that
   still references this symbol (e.g. hermes_cli/debug.py)"——hermes_cli/debug.py:81 实际只在
   docstring 里**提及**该符号,并无代码调用;弱冲突,记录备查。

## 11. 覆盖清单(本段 23758-27146 全部交代)

- 23742-23756 `_get_proxy_url`(§1.1);23758-23825 `_build_stream_consumer_config`(§1.2);
  23827-24108 `_run_agent_via_proxy`(§1.3);24112-24159 `_run_agent`(§2.1);
  24161-24207 `_profile_name_for_source`(§2.2);24209-24263 `_resolve_profile_home_for_source`(§2.3);
  24265-26039 `_run_agent_inner`(§3.1-3.15);26042-26128 `_run_planned_stop_watcher`(§4);
  26131-26288 `_start_gateway_housekeeping`(§5);26291-26303 `_start_cron_ticker`、
  26306-26322 两个 drain 常量、26325-26345 `_await_thread_exit`(§6);
  26348-26357 `_shutdown_gateway_health_export`(§7);26360-27018 `start_gateway`(§8);
  27021-27071 `main`、27074-27142 `_exit_after_graceful_shutdown`、27145-27146 入口守卫(§9)。
- 依赖的段外定义(供其他段核对):TurnRunner 3670(progress_callback 3686、
  send_progress_messages 3947、voice_ack_callback 4302、_step 4323、_event 4350、_status 4360、
  run_sync 4396、审批桥 5139);`_watch_gateway_turn_inactivity` 2951、
  `_abandon_timed_out_gateway_turn` 2912、`_reap_gateway_turn_processes` 2841;
  `_run_in_executor_with_context` 21375、`_set_session_env` 21333
  (→ gateway/session_context.set_session_vars);`_release_running_agent_state` 22802、
  `_is_session_run_current` 23041;`_profile_runtime_scope` 1938;`_float_env` 1000;
  config→env 导出 2166-2185。
