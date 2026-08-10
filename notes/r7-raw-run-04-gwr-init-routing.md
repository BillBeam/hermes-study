# r7 底稿 · run.py 第 4 段:GatewayRunner 状态总清单 + 会话路由 + 每会话运行时装配(5759-7691)

> 溯源约定:`gateway/run.py:行号 @ 863e313`(基线 commit 863e31318553cda8ad61df681d08175364d4164b,仓库只读)。
> 本段为 `class GatewayRunner` 第 1 段:类声明(5759)→ `/queue` FIFO 注释块与 `_enqueue_fifo` 签名行(7691,方法主体属下一段)。
> 全文件 27146 行,GatewayRunner 是 `GatewayAuthorizationMixin + GatewayKanbanWatchersMixin + GatewaySlashCommandsMixin` 的汇合类(gateway/run.py:5759 @ 863e313)。

---

## 0. 本段机制目录

| # | 机制 | 行号 |
|---|------|------|
| 1 | 类级默认值 + legacy dict 视图(SessionState 迁移的兼容层) | 5767-5871 |
| 2 | `__init__`:多路复用状态字段总清单 | 5873-6257 |
| 3 | Teams meeting pipeline 接线 | 6258-6287 |
| 4 | Docker 媒体递送风险警告 | 6289-6334 |
| 5 | Voice mode 持久化与 adapter 同步 | 6340-6465 |
| 6 | Adapter 断连/连接超时(detach-on-timeout 模式) | 6467-6661 |
| 7 | 退出原因 properties | 6663-6677 |
| 8 | `_session_key_for_source` —— 会话路由入口 | 6679-6707 |
| 9 | Telegram DM topic 模式全套 | 6709-6931 |
| 10 | `_resolve_session_agent_runtime` —— 每会话模型/运行时装配 | 6933-7099 |
| 11 | `_resolve_turn_agent_config` + `_sync_session_model_from_agent` | 7101-7194 |
| 12 | Reaction 事件 → HookRegistry | 7196-7210 |
| 13 | Adapter fatal error 处理(三层结构) | 7212-7371 |
| 14 | 活跃工作计数(agent + cron + API) | 7373-7421 |
| 15 | Scale-to-zero 判定与 watcher | 7423-7666 |
| 16 | 状态标签 + drain 期排队开关 + FIFO 注释块 | 7668-7691 |

---

## 1. 类级默认值 + legacy dict 视图(5767-5871)

### 1.1 解决什么问题

历史上 GatewayRunner 携带约 19 个按 session_key 索引的 `Dict[str, ...]` 属性,各自有独立生命周期,产生三类事故(gateway/session_state.py:7-19 @ 863e313 列举:#48031、#58403、#10702、#35809 边界漂移;turn 释放漂移;#28686 整体重置竞态)。重构后所有每会话状态收进单一 `SessionState` 容器,但大量测试(以及少数 mixin/adapter 调用点)仍直接读写旧 dict 属性名。兼容层用 property 把旧属性名映射为**活视图**。

### 1.2 实现

类体先声明一批类级默认值,让测试用 `object.__new__` 构造的"裸 runner"访问属性不炸:

gateway/run.py:5767-5779 @ 863e313
```python
    # Class-level defaults so partial construction in tests doesn't
    # blow up on attribute access.
    _busy_input_mode: str = "interrupt"
    _busy_text_mode: str = "interrupt"
    _restart_drain_timeout: float = DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
    _restart_after_turn_timeout: float = DEFAULT_GATEWAY_RESTART_AFTER_TURN_TIMEOUT
    _exit_code: Optional[int] = None
    _draining: bool = False
    _external_drain_active: bool = False
    _restart_requested: bool = False
    _restart_task_started: bool = False
    _restart_detached: bool = False
    _restart_via_service: bool = False
```

随后 19 个 legacy 视图属性(节选):

gateway/run.py:5788-5801 @ 863e313
```python
    # ------------------------------------------------------------------
    # Legacy per-session dict adapters.  All per-session state lives in
    # ``self._sessions`` (Dict[str, SessionState]); these properties expose
    # the pre-consolidation dict attributes as LIVE MutableMapping views so
    # the extensive test surface (and a few mixin/adapter call sites) that
    # read/write ``runner._running_agents`` etc. keeps working unchanged.
    # New production code should use ``self._session_state(key)`` directly.
    # ------------------------------------------------------------------
    _running_agents = legacy_dict_property("_running_agents")
    _running_agents_ts = legacy_dict_property("_running_agents_ts")
    _active_session_leases = legacy_dict_property("_active_session_leases")
    _busy_ack_ts = legacy_dict_property("_busy_ack_ts")
    _turn_lease_tokens = legacy_lease_token_property()
    _session_run_generation = legacy_dict_property("_session_run_generation")
```

其余为:`_session_model_overrides`、`_pending_one_turn_model_restores`、`_session_reasoning_overrides`、`_session_service_tier_overrides`、`_last_resolved_model`、`_queued_events`、`_pending_turn_sidecar_notes`、`_pending_messages`、`_pending_native_image_paths_by_session`、`_session_ephemeral_pin`、`_session_vc_last`、`_pending_approvals`、`_update_prompt_pending`(gateway/run.py:5802-5820 @ 863e313)。

`legacy_dict_property` 工厂在 gateway/session_state.py:419-450 @ 863e313:getter 返回 `SessionFieldView`(MutableMapping,活视图,`__setitem__` 走 `runner._session_state(key)` get-or-create,`__delitem__` 写回字段默认值而非删条目);setter 接受普通 dict(测试常写 `runner._X = {...}`),先 `view.clear()` 再逐项写入。字段规格表 `LEGACY_FIELD_SPECS`(gateway/session_state.py:371-416 @ 863e313)给每个旧 dict 指定 scope(turn/conversation/persistent)、字段名、默认值工厂、"存在性"判定(`_present_not_none` / `_present_nonzero` / `_present_not_unset`——`/fast` 的 service_tier 用哨兵 `_UNSET_TIER` 区分"未设置"与"显式 None")。

`_turn_lease_tokens` 特殊:旧 dict 按 `(session_key, generation)` 二元组索引,现在存于 `TurnState.lease_token/lease_generation` 单槽,`TurnLeaseTokenView`(gateway/session_state.py:299-349 @ 863e313)读写时校验 generation 匹配——保留 #28686 的所有权检查语义(过期 turn 的 unwind 绝不能释放新 turn 的 lease)。

### 1.3 SessionState 访问器

gateway/run.py:5823-5851 @ 863e313
```python
    def _sessions_map(self) -> Dict[str, "SessionState"]:
        """The per-session state map; lazily created so bare test runners
        built via ``object.__new__`` work without ``__init__``."""
        sessions = self.__dict__.get("_sessions")
        if sessions is None:
            sessions = {}
            self.__dict__["_sessions"] = sessions
        return sessions

    def _session_state(self, session_key: str) -> "SessionState":
        """Get-or-create the :class:`SessionState` for ``session_key``."""
        sessions = self._sessions_map()
        state = sessions.get(session_key)
        if state is None:
            state = SessionState()
            sessions[session_key] = state
        return state

    def _peek_session_state(self, session_key: str) -> Optional["SessionState"]:
        """Return the SessionState for ``session_key`` without creating one."""
        sessions = self.__dict__.get("_sessions")
        if not sessions:
            return None
        return sessions.get(session_key)
```

读/写分工:读路径用 `_peek_session_state`(不创建条目,避免只读检查污染 map),写路径用 `_session_state`(get-or-create)。`_is_session_running`(5848-5851)以 `state.turn.agent is not None` 为"占用 turn 槽"(含 pending 哨兵);`_running_agent_items`(5853-5861)重建旧 `_running_agents` dict 的 items 语义。

SessionState 三 scope(gateway/session_state.py:172-178 @ 863e313):
- `turn`(TurnState,51-87):agent / started_ts / lease / busy_ack_ts / lease_token+lease_generation;`clear()` 故意**不**清 lease_token——那由 `_release_turn_lease`(#64934)独占管理。
- `conversation`(ConversationState,90-128):model_override、one_turn_restore、reasoning_override、service_tier_override(哨兵)、last_resolved_model(#35314)、queued_events(/queue 溢出)、sidecar_notes、ephemeral_pin、vc_last;单一 `clear()` 结构性取代旧的手抄 pop-list。
- `persistent`(PersistentState,131-169):approvals、update_prompt_pending、native_image_paths、pending_command_text(#72680 关机落盘)、run_generation(#28686 单调**永不重置**)、hygiene_failure_streak(#79624,进程内、按 session_key 而非 session_id 键控以跨压缩轮转)。

注意条目**从不驱逐**(gateway/session_state.py:30-33 @ 863e313 明言,与旧 dict 的泄漏行为持平,留了 follow-up)。

### 1.4 重实现要点

1. 状态整合迁移时,用"活视图 property"兜住旧属性名调用面,可让重构一次落地而不必同步改全部测试;视图必须是 live(不 copy),且 setter 支持整 dict 赋值。
2. 每字段带独立"存在性谓词":`in`/`KeyError` 语义要和旧 dict 完全等价(0/None/空 list 视为不存在),否则测试语义漂移。
3. 状态按"在哪里被清"分 scope(turn/conversation/persistent),清理入口收敛到每 scope 一个 `clear()`;新增字段自动获得正确生命周期。
4. 单调计数器(run_generation)必须放在任何 clear() 之外,否则过期 turn 检测失效。
5. lease token 与 generation 配对存储,释放时校验 generation,防止 stale unwind 释放新 turn 的锁。
6. 类级默认值 + 惰性 `_sessions_map` 让 `object.__new__` 构造的对象可用——测试友好性是显式设计目标。

---

## 2. `__init__`:多路复用状态字段总清单(5873-6257)

`__init__` 是全 gateway 多路复用状态的总目录。逐块交代(标注【SessionState】= 已迁入统一容器,【裸】= 仍是独立属性/裸 dict):

### 2.1 配置装载与 multiplex secret scope(5873-5911)

gateway/run.py:5873-5888 @ 863e313
```python
    def __init__(self, config: Optional[GatewayConfig] = None):
        global _gateway_runner_ref
        # When multiplex_profiles is on, load under the default profile secret
        # scope so bot tokens in that profile's .env resolve the same way
        # secondary profiles do (#64674). Explicit config= injection (tests)
        # is left untouched.
        self.config = config if config is not None else load_gateway_config_for_runner()
        # Mark the process as a profile multiplexer when configured. This flips
        # agent.secret_scope.get_secret() to fail-closed on any unscoped
        # credential read, so a missed migration crashes loudly instead of
        # leaking a cross-profile value (Workstream A). Inert when off.
        try:
            from agent.secret_scope import set_multiplex_active
            set_multiplex_active(bool(getattr(self.config, "multiplex_profiles", False)))
        except Exception:
            logger.debug("could not set multiplex-active flag", exc_info=True)
```

- `load_gateway_config_for_runner`(gateway/run.py:1974-2006 @ 863e313):multiplex 开时在默认 profile 的 `_profile_runtime_scope` 下重载配置,否则 `profiles/<name>/.env` 里的 bot token 解析不到(#64674)。
- `set_multiplex_active`:multiplex 下未加 scope 的凭据读取 fail-closed(响亮崩溃优于跨 profile 泄漏)。
- `self.adapters`【裸 dict】默认 profile 的 Platform→adapter;`self._profile_adapters`【裸】次级 profile 的 `{profile: {Platform: adapter}}`——multiplex 关时为空,~93 处 `self.adapters[...]` 现场零改动(gateway/run.py:5889-5895 @ 863e313)。
- 5896 调 `_warn_if_docker_media_delivery_is_risky()`(见 §4);5897 存全局弱引用 `_gateway_runner_ref`。
- 5901-5911 十一个 ephemeral 配置 loader(prefill/系统提示/reasoning/service_tier/show_reasoning/busy 两模式/restart 两超时/provider_routing/fallback_model)——"仅 API 调用时注入,从不持久化"。

### 2.2 SessionStore + 后台进程重置保护(5913-5935)

gateway/run.py:5918-5930 @ 863e313
```python
        from tools.process_registry import process_registry
        _bg_max_age_hours = getattr(
            self.config.default_reset_policy, "bg_process_max_age_hours", 24
        )
        _bg_max_age_seconds = (
            _bg_max_age_hours * 3600 if _bg_max_age_hours and _bg_max_age_hours > 0 else None
        )
        self.session_store = SessionStore(
            self.config.sessions_dir, self.config,
            has_active_processes_fn=lambda key: process_registry.has_active_for_session(
                key, max_active_age=_bg_max_age_seconds,
            ),
        )
```

会话 idle/daily 重置被"该会话有活跃后台进程"否决;但超过 24h 的后台进程视为 stale,**只被重置守卫忽略、不被杀**(#29177)。`self._async_session_store = AsyncSessionStore(self.session_store)`(5934):同步 SessionStore 的唯一 loop 侧边界(async 处理器全走 facade await,同步 helper 直用 store;类定义 gateway/session.py:1189/1206 @ 863e313)。5935 `DeliveryRouter(self.config)`。

### 2.3 退出/drain/重启标志(5936-5983)【全裸标量】

- `_running/_gateway_loop/_shutdown_event/_exit_cleanly/_exit_with_failure/_exit_reason/_exit_code/_draining`(5936-5943)。
- `_external_drain_active`(5944-5955):NAS 外部 drain,与关机 `_draining` **正交**——由 `.drain_request.json` 标记驱动,拒新 turn 但**不退出进程**,可逆(移除标记恢复 running);`_draining` 单向、终于进程退出。
- `_signal_initiated_shutdown`(5957-5966):SIGTERM/SIGINT 到达且**无** planned-stop/takeover 标记 = 意外外部信号(docker restart、OOM、裸 kill);`_stop_impl` 据此**不**持久化 `gateway_state=stopped`,否则下次 boot 时 container_boot 拒绝自启(#42675)。
- `_startup_time`(5975)/`_booted_from_restart`(5981):/restart 重投递去重窗口的一次性信号——仅当确认刚经历 restart 循环时,标记缺失才可判为 stale 重投递,绝不误伤真冷启。
- `_restart_*` 一组 + `_stop_task/_restart_task`(5967-5983)。

### 2.4 executor 与 `_sessions`(5984-5993)

`_executor_lock/_executor/_executor_closing`(5984-5988,线程池惰性建,关机时 `_executor_closing` 阻止重建复活)。核心容器:

gateway/run.py:5989-5993 @ 863e313
```python
        # ALL per-session state (turn / conversation / persistent scopes)
        # lives in one container — see gateway/session_state.py.  Access via
        # self._session_state(key) (get-or-create) or
        # self._peek_session_state(key) (read-only).
        self._sessions: Dict[str, SessionState] = {}
```

### 2.5 turn lease 注册表 + 迁移注记(5994-6031)

gateway/run.py:5994-6000 @ 863e313
```python
        # Per-SESSION_ID turn lease (#64934): serializes the
        # [load history → run → flush] region when two ROUTING KEYS resolve
        # to one session_id (switch_session's many-to-one mapping). The
        # routing-key guards above cannot see that overlap. Acquired in
        # _handle_message_with_agent after session resolution is final,
        # released via _release_turn_lease in the same method's finally.
        self._turn_leases = SessionTurnLeaseRegistry()
```

`SessionTurnLeaseRegistry`(gateway/turn_lease.py:115-121 @ 863e313):按**解析后的 session_id**(非路由键)串行化转录 turn,进程内单 loop;解决 switch_session 多路由键→单 session_id 时路由键守卫看不见的重叠。6001-6031 是大段迁移注记,逐条指认旧 dict 现在的落点(lease token 对→TurnState;pending_command_text→persistent,并强调与 gateway/platforms/base.py 的 adapter 级 `_pending_messages`(Dict[str, MessageEvent])**同名异物**;last_resolved_model→conversation,`"*"` 条目为进程级 last-known-good,#35314;/queue 溢出→conversation.queued_events——adapter 槽是单槽会合并,/queue 语义是每次调用一个完整 turn、FIFO、不合并)。

### 2.6 其余字段逐项(6035-6255)

| 字段 | 行 | 归属 | 用途 |
|------|----|------|------|
| `_session_stall_notified: Dict[str, bool]` | 6035 | 【裸 dict,按 session_key】 | 当前 stall 事件已通知过的会话(gateway.session_stall) |
| `_startup_restore_in_progress` | 6040 | 【裸标量】 | 启动恢复门:restart 中断会话自动续跑期间,真实入站消息进队列不与合成 resume turn 抢会话 |
| `_platform_lock_takeover_on_start` | 6044 | 【裸】 | 仅 `--replace` 启动置位;详见 §6.4 |
| `_startup_restore_queue/List` + `_startup_restore_tasks` | 6045-6046 | 【裸】 | 恢复门排队的事件与任务 |
| `_session_sources: OrderedDict` + `_session_sources_max=512` | 6047-6053 | 【裸 LRU,按 session_key】 | 活 SessionSource 缓存;fallback 路由(关机通知、合成后台进程事件)在持久化 origin 缺失且 `_parse_session_key` 恢复不了 thread_id 时用;封顶防无界增长 |
| `_completion_delivery_lock` + `_completion_deliveries_inflight/set` + `_completion_deliveries_delivered/OrderedDict` + retention=2048 | 6054-6062 | 【裸】 | 完成投递去重,**刻意 lifecycle-scoped**:只关单 gateway 内 queue/watcher 竞态,不假装跨进程崩溃 exactly-once;持久重放归 tools.async_delegation |
| `_agent_cache: OrderedDict` + `_agent_cache_lock` | 6064-6076 | 【裸 LRU,按 session_key】 | AIAgent 实例缓存,保 prompt 前缀缓存(否则每消息重建系统提示,Anthropic 上成本 ~10x);值为 `(AIAgent, config_signature_str)`;`_AGENT_CACHE_MAX_SIZE` 硬顶 + `_session_expiry_watcher` 执行 idle TTL |
| `_kanban_notifier_profile` | 6082 | 【裸】 | kanban 通知归属 profile |
| `_teams_pipeline_runtime(+_error)` | 6083-6085 | 【裸】 | §3 |
| `_failed_platforms: Dict[Platform, {...}]` | 6088-6090 | 【裸】 | 连接失败平台重连队列:`{"config":…, "attempts":int, "next_retry":float}` |
| `_fatal_handler_tasks: set` | 6092-6094 | 【裸】 | detached fatal-handler 任务强引用防 GC |
| `_slash_confirm_counter` | 6099-6105 | 【裸】 | confirm_id 紧凑计数(部分平台 callback_data 64 字节顶);slash-confirm 状态本体在 tools.slash_confirm 模块级,免 adapter 反向引用 runner |
| tirith `ensure_installed` | 6113-6118 | — | 安全扫描器预装,失败 fail-open |
| 审批模式启动警告 | 6120-6145 | — | #30882:manual 审批 + tirith 关 + 无 auxiliary.approval ⇒ 危险命令 fail-closed 阻塞至人工批准,启动时 WARN 提醒无人值守场景 |
| `_session_db = AsyncSessionDB(SessionDB())` | 6147-6159 | 【裸】 | session_search//resume//title 等的 SQLite;失败 **WARNING**(非 DEBUG)——NFS HERMES_HOME 用户曾静默丢失整组功能 |
| state.db 自动维护 | 6161-6189 | — | opt-in auto_archive/auto_prune+VACUUM,state_meta 记 last-run 限频(min_interval_hours),阻塞几秒可接受,失败只记日志 |
| checkpoint 影子仓清理 | 6191-6212 | — | opt-in;`delete_orphans` **刻意永不启用**:启动时 workdir 缺失有歧义(删了 vs 网络盘没挂),无人值守清扫不做,孤儿只走显式 CLI |
| `pairing_store` + `pairing_stores: Dict[str, PairingStore]` | 6214-6222 | 【裸】 | DM 配对码授权;per-profile map 供 authz_mixin 路由到正确白名单 |
| `self.hooks = HookRegistry()` | 6224-6226 | 【裸】 | 事件钩子 |
| `_voice_mode: Dict[str, str]` | 6228-6229 | 【裸,按 `platform:chat_id`】 | "off"/"voice_only"/"all",§5 |
| `_recent_voice_transcripts: Dict[(guild,user), List[(ts,text)]]` | 6230-6233 | 【裸】 | 语音转写去重:同一句被 STT 管线重复吐出会产生第二条延迟回复 |
| `_background_tasks: set` | 6235-6236 | 【裸】 | 后台任务防 GC |
| `_gateway_started_at` + `_loop_heartbeat_task/_loop_floor_timer_handle/_loop_liveness_watchdog` | 6238-6244 | 【裸】 | #66892 loop 活性心跳:30s 重写文件,外部监督者用 mtime 区分"进程活着"与"loop 冻死"(类级默认在 5862-5871,#66892/#69089) |
| `_last_inbound_at` + `_scale_to_zero_cooldown_until` | 6246-6255 | 【裸】 | §15;入站时钟种子为 now,防新 gateway 被判"自纪元起 idle" |

**迁移状态小结**:19 个旧 per-session dict 已全部进 SessionState(经 legacy property 暴露);仍为裸容器的按-session 状态是 `_session_stall_notified`、`_session_sources`(LRU)、`_agent_cache`(LRU)、惰性的 `_telegram_lobby_reminder_ts`(6765-6766)——共性:要么带独立淘汰策略(LRU/TTL),要么生命周期与会话边界无关,不适合塞进无驱逐的 SessionState。

### 2.7 重实现要点

1. `__init__` 里每个字段旁写清:键是什么、谁清、封顶策略;无界 dict 是长寿进程的头号泄漏源(此处 `_session_sources`/`_agent_cache`/`_completion_deliveries_delivered` 全部显式封顶,SessionState 则明示"暂不驱逐")。
2. agent 实例必须按会话缓存以保 provider 前缀缓存(prompt caching);缓存键要含配置签名,配置变即失效。
3. 去重结构要诚实标注一致性边界:进程内 exactly-once 与跨崩溃 exactly-once 是两个问题,别用一个 ledger 假装都解决。
4. 启动期 opt-in 维护(prune/vacuum)要:限频标记 + 永不 raise + 有歧义的破坏性选项(删孤儿)只留给显式人工命令。
5. 关机语义分三轨:内部 drain(单向)、外部 drain(可逆稳态)、意外信号(不得持久化 stopped)——三个标志各自独立,混用会造成"重启后拒绝自启"这类事故(#42675)。
6. 无人值守安全兜底要在启动时**说出来**(#30882 的 WARN),fail-closed 而不告知等于静默瘫痪。

---

## 3. Teams pipeline 接线(6258-6287)

gateway/run.py:6258-6281 @ 863e313
```python
    def _wire_teams_pipeline_runtime(self) -> None:
        """Bind the Teams meeting pipeline runtime to Graph webhook ingress.

        No-op when the msgraph_webhook adapter isn't running or the
        teams_pipeline plugin isn't enabled — lets the gateway start cleanly
        whether or not the user has opted into the pipeline.
        """
        if Platform.MSGRAPH_WEBHOOK not in self.adapters:
            return
        if not _teams_pipeline_plugin_enabled():
            logger.debug("Teams pipeline plugin is disabled; skipping runtime wiring")
            return
        try:
            from plugins.teams_pipeline.runtime import bind_gateway_runtime
        except Exception as exc:
            logger.warning("Teams pipeline runtime import failed: %s", exc)
            return
        try:
            bound = bind_gateway_runtime(self)
        except Exception as exc:
            logger.warning("Teams pipeline runtime wiring failed: %s", exc)
            return
        if bound:
            logger.info("Teams pipeline runtime bound to msgraph webhook ingress")
```

- 双重开关:msgraph_webhook adapter 在跑 **且** 插件在 `plugins.enabled` 列表(`_teams_pipeline_plugin_enabled`,gateway/run.py:3128-3134 @ 863e313,接受 `teams_pipeline`/`teams-pipeline` 两种写法)。
- `bind_gateway_runtime`(plugins/teams_pipeline/runtime.py:98 @ 863e313)把 runtime 挂到 `gateway._teams_pipeline_runtime`,失败原因写 `_teams_pipeline_runtime_error`(plugins/teams_pipeline/runtime.py:112/133-134),本方法在 bound 为假时把该错误 WARN 出来(6282-6286)。
- 调用点:start 流程 gateway/run.py:11349 @ 863e313(adapter 全部连接后)。
- 重实现要点:插件接线全程 try/except 降级为日志——可选组件的 import/绑定失败绝不能拦核心启动;错误原因存字段供后续诊断而非只打日志。

---

## 4. Docker 媒体递送风险警告(6289-6334)

**问题**:MEDIA 投递发生在 gateway 进程(宿主机),模型吐出的容器内路径(`/workspace/report.txt`)宿主机读不到,文件递送静默失败。**做法**:仅告警不拦截。

gateway/run.py:6298-6323 @ 863e313(节选)
```python
        if os.getenv("TERMINAL_ENV", "").strip().lower() != "docker":
            return

        connected = self.config.get_connected_platforms()
        messaging_platforms = [p for p in connected if p not in {Platform.LOCAL, Platform.API_SERVER, Platform.WEBHOOK}]
        if not messaging_platforms:
            return

        raw_volumes = os.getenv("TERMINAL_DOCKER_VOLUMES", "").strip()
        ...
        has_explicit_output_mount = False
        for spec in volumes:
            match = _DOCKER_VOLUME_SPEC_RE.match(spec)
            if not match:
                continue
            container_path = match.group("container")
            if container_path in _DOCKER_MEDIA_OUTPUT_CONTAINER_PATHS:
                has_explicit_output_mount = True
                break
```

- 触发条件三连:`TERMINAL_ENV=docker`;有真实消息平台(排除 LOCAL/API_SERVER/WEBHOOK);`TERMINAL_DOCKER_VOLUMES`(JSON 列表)里没有挂到 `/output` 或 `/outputs` 的卷(`_DOCKER_VOLUME_SPEC_RE`/`_DOCKER_MEDIA_OUTPUT_CONTAINER_PATHS`,gateway/run.py:2029-2030 @ 863e313,正则解析 `host:container[:options]`)。
- 满足则 WARN 建议 `host-dir:/output` 挂载(6329-6334)。
- 重实现要点:跨边界文件递送的"路径可见性"检查放在启动期做一次性提示,成本最低;检查必须容忍环境变量缺失/坏 JSON(此处 debug 降级);措辞承认误报可能("This is fine if…")。

---

## 5. Voice mode 持久化与 adapter 同步(6340-6465)

**问题**:`/voice` 的每 chat 语音回复模式要跨 gateway 重启存活,且真正执行 TTS 抑制/放行的是 adapter 内存里的 set——两边要同步。

- 存储:`~/.hermes/gateway_voice_mode.json`(`_VOICE_MODE_PATH`,6350),键 `f"{platform.value}:{chat_id}"`(`_voice_key`,6352-6354),值 ∈ {"off","voice_only","all"}。
- 加载(`_load_voice_modes`,6356-6380):非法值跳过;**无冒号的 legacy 无前缀键告警并跳过**(迁移策略:不自动改写,让用户重新开一次重建带前缀键):

gateway/run.py:6367-6379 @ 863e313
```python
        for chat_id, mode in data.items():
            if mode not in valid_modes:
                continue
            key = str(chat_id)
            # Skip legacy unprefixed keys (warn and skip)
            if ":" not in key:
                logger.warning(
                    "Skipping legacy unprefixed voice mode key %r during migration. "
                    "Re-enable voice mode on that chat to rebuild the prefixed key.",
                    key,
                )
                continue
            result[key] = mode
        return result
```

- adapter 侧两个 set:`_auto_tts_disabled_chats` / `_auto_tts_enabled_chats`。互斥语义:`/voice off` 是硬覆盖(加 disabled 同时从 enabled 剔除,6391-6403);显式 opt-in 清掉 stale 的 off(6405-6421)。
- `_sync_voice_mode_state_to_adapter`(6423-6465):连接/重连时把持久化状态恢复进活 adapter——三件事:从 config.yaml `voice.auto_tts` 推 `_auto_tts_default`;按 `platform.value+":"` 前缀过滤 `self._voice_mode`,off→disabled set,voice_only/all→enabled set(先 clear 再 update,幂等)。调用点:初连 gateway/run.py:11120、重连 12484、以及 13457 @ 863e313。
- 重实现要点:①持久层键必须带平台命名空间,否则两平台同 chat_id 串台(legacy 键即为此弃用);②双向覆盖(off 清 enabled、on 清 disabled)要显式写,否则出现"又 enabled 又 disabled"的未定义态;③恢复函数须幂等(clear+update),重连任意次结果一致;④写文件失败只 WARN——语音偏好不值得拦关机路径。

---

## 6. Adapter 断连/连接超时:detach-on-timeout 模式(6467-6661)

### 6.1 问题与事故

`asyncio.wait_for` 超时后 cancel 子任务,**然后等它退出**;若 adapter 的 close/connect 吞了 `CancelledError`(半死的 Feishu WebSocket 线程等 I/O),调用方永远等不回来。后果链:关机序列卡过 systemd `TimeoutStopSec` → SIGKILL 跳过 atexit PID 清理 → 下次启动 "PID file race lost"(#14128,6530-6535);重连场景则 watcher 永远到不了下一次 retry(#70344,6623-6628)。

### 6.2 核心原语 `_await_adapter_cleanup_with_timeout`(6467-6494)

gateway/run.py:6477-6494 @ 863e313
```python
        if timeout <= 0:
            await awaitable
            return True

        task = asyncio.ensure_future(awaitable)
        try:
            done, _pending = await asyncio.wait({task}, timeout=timeout)
        except asyncio.CancelledError:
            task.cancel()
            task.add_done_callback(consume_detached_task_result)
            raise
        if task in done:
            await task
            return True

        task.cancel()
        task.add_done_callback(consume_detached_task_result)
        return False
```

要义:用 `asyncio.wait`(到点即返回,不等子任务死)替代 `wait_for`;超时后 cancel + 挂 `consume_detached_task_result`(agent/async_utils.py:71 @ 863e313,吞掉 detached 任务的结果/异常防 "never retrieved" 噪音)然后**放手**;自身被 cancel 时同样先把子任务 detach 再 re-raise。

### 6.3 三个消费者

- `_safe_adapter_disconnect`(6496-6523):connect 失败后的防御性 disconnect,吞一切异常(部分初始化的 aiohttp session/poll task/子进程会泄漏成 "Unclosed client session")。
- `_bounded_adapter_teardown`(6525-6575):关机路径,对 `cancel_background_tasks()` 与 `disconnect()` 各给一份超时预算,超时 WARN "forcing continue",**永不 raise**。
- `_connect_adapter_with_timeout`(6609-6645):连接侧同模式;`is_reconnect` 透传给 `adapter.connect()`——冷启丢弃服务端 stale 队列 vs 断网重连保留队列补投(#46621);超时 raise `TimeoutError`。

超时配置:断连 `HERMES_GATEWAY_ADAPTER_DISCONNECT_TIMEOUT`(默认 5.0s,gateway/run.py:81);连接 `HERMES_GATEWAY_PLATFORM_CONNECT_TIMEOUT`(默认 30s,Telegram 特判 180s——gateway/run.py:76/80,6605-6607)。非法值 WARN 后用默认;负值 clamp 到 0(0 = 无限等)。

### 6.4 `_connect_initial_adapter_with_timeout`(6647-6661)

gateway/run.py:6647-6661 @ 863e313
```python
    async def _connect_initial_adapter_with_timeout(self, adapter, platform) -> bool:
        """Connect one cold-start adapter with tightly scoped replace intent.

        The capability is visible only while this initial connect is awaited.
        Reconnects call ``_connect_adapter_with_timeout`` directly and adapters
        also default to deny, so a later network recovery can never evict a
        healthy token holder.
        """
        adapter._platform_lock_takeover_allowed = bool(
            self._platform_lock_takeover_on_start
        )
        try:
            return await self._connect_adapter_with_timeout(adapter, platform)
        finally:
            adapter._platform_lock_takeover_allowed = False
```

`--replace` 的"抢占平台锁"能力只在**初次冷启连接的 await 期间**可见,finally 必收回——否则后来的网络恢复重连可能驱逐健康的 token 持有者。调用点:11113(启动)、13379(profile 路径)。

### 6.5 重实现要点

1. 对不可信的第三方 close/connect 代码,永远用 "wait + detach" 而非 `wait_for`:到点收回控制权,把子任务连同 done-callback 甩出去。
2. detached 任务必须挂结果消费回调,否则异常告警刷屏。
3. teardown 路径永不 raise、每步限时、超时只记日志继续——关机的敌人是"卡住",不是"不干净"。
4. 冷启与重连是两种语义(队列丢弃 vs 保留),用参数显式区分,别让 adapter 猜。
5. 危险能力(锁抢占)作用域最小化:置位-await-finally 复位,能力窗口 = 单次 await。
6. 超时读 env,平台可特判(Telegram 180s),坏值降级默认并告警。

---

## 7. 退出原因 properties(6663-6677)

`should_exit_cleanly / should_exit_with_failure / exit_reason / exit_code` 四个只读 property 包装内部标志(6663-6677),供 `start_gateway()` 外层决定进程退出码与 systemd 重启行为。无逻辑,纯封装。

---

## 8. `_session_key_for_source` —— 会话路由入口(6679-6707)

**问题**:一个入站 `SessionSource`(platform/chat_type/chat_id/user_id/thread_id/scope_id/profile)要确定地映射到一个 session_key;且 slash 命令、fallback 路径、测试裸 runner 都要能算,不能强依赖已初始化的 store。

gateway/run.py:6679-6707 @ 863e313
```python
    def _session_key_for_source(self, source: SessionSource) -> str:
        """Resolve the current session key for a source, honoring gateway config when available."""
        if hasattr(self, "session_store") and self.session_store is not None:
            try:
                session_key = self.session_store._generate_session_key(source)
                if isinstance(session_key, str) and session_key:
                    return session_key
            except Exception:
                pass
        config = getattr(self, "config", None)
        # Mirror SessionStore._resolve_profile_for_key so this fallback path
        # produces the same namespace as the primary path: None (legacy
        # agent:main) unless multiplexing is on, then the active profile.
        _profile = None
        if getattr(config, "multiplex_profiles", False):
            if source.profile:
                _profile = source.profile
            else:
                try:
                    from hermes_cli.profiles import get_active_profile_name
                    _profile = get_active_profile_name() or "default"
                except Exception:
                    _profile = None
        return build_session_key(
            source,
            group_sessions_per_user=getattr(config, "group_sessions_per_user", True),
            thread_sessions_per_user=getattr(config, "thread_sessions_per_user", False),
            profile=_profile,
        )
```

- 主路径:`SessionStore._generate_session_key`(gateway/session.py:1725-1732 @ 863e313)= `build_session_key(source, group_sessions_per_user, thread_sessions_per_user, profile=_resolve_profile_for_key(source))`。
- fallback 路径(store 缺/坏):自行镜像 profile 解析后直调 `build_session_key`。**关键不变量:两条路径必须产出同一命名空间**——multiplex 关时 profile=None(legacy `agent:main` 命名空间),开时用 source.profile 或活动 profile。
- `build_session_key`(gateway/session.py:1058 @ 863e313)是键构造唯一权威:DM 键 `ns:platform:dm[:slack_scope][:chat_id[:thread_id]]`,无 chat_id 时退 `user_id_alt or user_id`(否则所有无 chat_id 的 DM 塌缩进一个共享会话 → 缓存 agent 跨用户历史串台,1116-1132 注释明言);群组键含 chat_id + (可选 per-user) + thread_id,`thread_sessions_per_user=False`(默认)时线程**跨参与者共享**。
- 调用极广:slash_commands.py 30+ 处(124/741/1203/1762/3503/…),run.py 消息主线 14521、15811、cron/heartbeat 18807/18864、后台完成 20322/20521/20619、下一事件推进 25704 @ 863e313 等。
- 重实现要点:①键构造只留一个权威函数,任何 fallback 都 delegate 到它而不是复制格式;②fallback 与主路径的命名空间参数逐项对齐并写注释说明"镜像自谁";③键要把"隔离维度"(workspace/user/thread/profile)显式编码,缺维度的退化路径要选**更隔离**而非更共享的方向。

---

## 9. Telegram DM topic 模式全套(6709-6931)

### 9.1 背景

Telegram 私聊(DM)开启 forum/topic 后,一个 bot DM 可有多个 topic。hermes 把它做成"多会话 DM 模式":每个用户建的 topic = 一个独立 hermes 会话(lane),根 DM(含 General topic)= 只收系统命令的大厅(lobby)。开关按 (chat_id, user_id) 存 SQLite(`telegram_dm_topic_mode` 表),topic→会话绑定存 `telegram_dm_topic_bindings` 表。

### 9.2 开关读取(6709-6729)

gateway/run.py:6709-6729 @ 863e313(节选)
```python
    def _telegram_topic_mode_enabled(self, source: SessionSource) -> bool:
        """Return whether Telegram DM topic mode is active for this chat."""
        if source.platform != Platform.TELEGRAM or source.chat_type != "dm":
            return False
        session_db = getattr(self, "_session_db", None)
        if session_db is None:
            return False
        # Runs off-loop (always via asyncio.to_thread); use the sync handle.
        session_db = getattr(session_db, "_db", session_db)
        try:
            raw = session_db.is_telegram_topic_mode_enabled(
                chat_id=str(source.chat_id),
                user_id=str(source.user_id),
            )
        except Exception:
            logger.debug("Failed to read Telegram topic mode state", exc_info=True)
            return False
        # Only honor a real True from the SessionDB. Any other value
        # (including MagicMock instances from test fixtures that didn't
        # opt into topic mode) means topic mode is off for this chat.
        return raw is True
```

三个细节:①走同步 `_db` 句柄——调用方保证在 `asyncio.to_thread` 里(见 15635-15637、gateway/slash_commands.py:1761 等全部 to_thread 包裹);②`raw is True` 严格判等——防测试 MagicMock 之类 truthy 值误开;③一切异常回 False(fail-safe:读不到 = 没开)。DB 方法:hermes_state.py:9033(is_enabled)/9071(list_bindings)/9193(bind)@ 863e313。

### 9.3 lobby/lane 判定(6731-6754)

gateway/run.py:6731-6743 @ 863e313
```python
    # Telegram's General (pinned top) topic in forum-enabled private chats.
    # Bot API behavior varies: some clients omit message_thread_id for
    # General, others send "1". Treat both as "root" for lobby/lane purposes.
    _TELEGRAM_GENERAL_TOPIC_IDS = frozenset({"", "1"})

    def _is_telegram_topic_root_lobby(self, source: SessionSource) -> bool:
        """True for the main Telegram DM (or General topic) when topic mode has made it a lobby."""
        if source.platform != Platform.TELEGRAM or source.chat_type != "dm":
            return False
        if not self._telegram_topic_mode_enabled(source):
            return False
        tid = str(source.thread_id or "")
        return tid in self._TELEGRAM_GENERAL_TOPIC_IDS
```

lane 判定(6745-6754)= topic 模式开 且 thread_id 非空且非 General。General 的 `{"", "1"}` 双 id 是对 Bot API 客户端差异的兼容(有的省略 message_thread_id,有的发 "1")。

### 9.4 lobby 提醒限频(6756-6776)

`_TELEGRAM_LOBBY_REMINDER_COOLDOWN_S = 30.0`;`_should_send_telegram_lobby_reminder` 用惰性建的 `_telegram_lobby_reminder_ts`(monotonic,按 chat_id)做 30s 防抖——忘了模式已开、连打十条 prompt 的用户只收到一条提醒。消费点:消息主线 gateway/run.py:15635-15642 @ 863e313——命中 root lobby 时,防抖通过则回 `_telegram_topic_root_lobby_message()`(6778-6785 文案),否则**回 None 静默丢弃**。`/new` 在 root 则回 `_telegram_topic_root_new_message()`(6787-6794;消费点 15063);lane 内 `/new` 的头部文案 `_telegram_topic_new_header`(6796-6804;消费点 gateway/slash_commands.py:262/266 @ 863e313,`asyncio.to_thread` 调用,空时退 i18n 默认)。

### 9.5 绑定记录与压缩轮转同步(6806-6849)

`_record_telegram_topic_binding`(6806-6823):把 (chat_id, thread_id, user_id) → (session_key, session_id) 写进 `telegram_dm_topic_bindings`,使新进程里重开 topic 能续上正确会话。

`_sync_telegram_topic_binding`(6825-6849)解决一个三连事故:

gateway/run.py:6832-6841 @ 863e313
```python
        """Update the topic binding to point at ``session_entry.session_id``.

        Telegram topic lanes persist a (chat_id, thread_id) -> session_id row
        so reopening a topic in a fresh process resumes the right Hermes
        session. When compression rotates ``session_entry.session_id`` mid-turn,
        the binding goes stale and the next inbound message in that topic
        reloads the oversized parent transcript instead of the compressed
        child, retriggering preflight compression — sometimes in a loop
        (#20470, #29712, #33414).
        """
```

事故因果:上下文压缩把 session_id 轮转成新的"压缩子会话"→ 绑定还指旧超长父转录 → topic 下一条消息加载父转录 → 再次触发 preflight 压缩 → 循环。修法:压缩轮转处(gateway/run.py:5559 @ 863e313,turn pipeline 内)调本方法刷新绑定;仅 lane 生效,失败 debug 降级。

### 9.6 thread_id 恢复(6851-6903)

**问题**:topic 模式 DM 下,Telegram 对部分回复省略 `message_thread_id` 或给 General("1")——按原样路由会落进 lobby 键,对话断线。

gateway/run.py:6874-6903 @ 863e313(节选)
```python
        inbound = str(source.thread_id or "")
        is_lobby = not inbound or inbound in self._TELEGRAM_GENERAL_TOPIC_IDS
        if not is_lobby:
            # A non-lobby, unknown thread_id is most likely the first message in
            # a brand-new Telegram DM topic. Preserve it so it can be recorded
            # as a new independent lane below instead of hijacking the latest
            # existing topic binding.
            return None
        ...
        user_id = str(source.user_id)
        for b in bindings:  # newest-first
            if str(b.get("user_id") or "") == user_id:
                recovered = str(b.get("thread_id") or "")
                if recovered and recovered != inbound:
                    return recovered
                return None
        return None
```

规则:只在"lobby 形态"(thread_id 空或 General)时,才把会话钉回该用户**最近绑定**的 topic;非 lobby 的未知 thread_id **不改写**——那多半是全新 topic 的第一条消息,改写会把新 topic 的回答劫持进旧 lane(6862-6865 注释)。绑定按 newest-first 遍历,匹配 user_id 取第一条。

### 9.7 `_normalize_source_for_session_key`(6905-6931)—— #30479

**事故因果**:消息主线在派生 session_key **前**先做 `_recover_telegram_topic_thread_id` 改写;但 `/model`、`/reasoning` 等会话级命令直接用原始 `event.source` 派生 override 存储键——跳过了恢复,于是 override 存在 A 键、下一条消息 turn 从 B 键读,override 在 Telegram forum topic 和压缩分裂后**静默失效**(#30479,6910-6920 docstring)。

gateway/run.py:6921-6931 @ 863e313
```python
        Returns a recovery-normalized copy when a rewrite applies, otherwise
        the original source unchanged.  Always derive the override storage key
        from the result so storage and read use an identical key.
        """
        try:
            recovered = self._recover_telegram_topic_thread_id(source)
        except Exception:
            return source
        if recovered is None:
            return source
        return dataclasses.replace(source, thread_id=recovered)
```

不可变改写(`dataclasses.replace`)。消费点:gateway/slash_commands.py:1761(/model)、3502(/reasoning)、4500、4689 @ 863e313,全部 `asyncio.to_thread` 包裹(内部有同步 DB 读)。

### 9.8 重实现要点

1. "路由键改写"必须收敛为单一函数,**所有**从 source 派生持久键的路径(消息、命令、后台)统一先过它——存/读键不一致是最难查的静默失效。
2. 平台原生 id 的怪癖(General topic 的 ""/"1" 二义)用 frozenset 常量集中吸收,别散落各处判空。
3. 恢复类改写要区分"确定的 lobby 形态"与"未知新 id":前者可改写,后者必须保留——宁可新建 lane 不可劫持旧 lane。
4. 持久绑定指向会轮转的 id(session_id)时,轮转点必须带绑定刷新钩子,否则出现自触发循环(#20470 系)。
5. 用户教育型提醒一律限频(monotonic + per-chat);限频未过时返回 None(静默)而非重复发。
6. 同步 DB 读放 `asyncio.to_thread`,并在方法内注释这一契约("Runs off-loop");严格 `is True` 判定防 mock/脏数据误开行为开关。

---

## 10. `_resolve_session_agent_runtime` —— 每会话模型/运行时装配(6933-7099)

**问题**:一个会话的 turn 用什么 model/provider/api_key/base_url/api_mode?来源有五层,须定序合并,且要抗"配置瞬时读空"。

**优先级(高→低)**:会话 `/model` override(带 api_key 的快路径)→ 运行时 provider 显式 model → channel_overrides → `/model` override(无 api_key 的叠加路径)→ provider 目录默认 → last-known-good 兜底。

### 10.1 快路径:带凭据的会话 override

gateway/run.py:6953-6984 @ 863e313(节选)
```python
        model = _resolve_gateway_model(user_config)
        if resolved_session_key:
            self._rehydrate_session_model_override(resolved_session_key)
        _override_state = (
            self._peek_session_state(resolved_session_key)
            if resolved_session_key
            else None
        )
        override = (
            _override_state.conversation.model_override if _override_state else None
        )
        if override:
            override_model = override.get("model", model)
            override_runtime = {
                "provider": override.get("provider"),
                "api_key": override.get("api_key"),
                "base_url": override.get("base_url"),
                "api_mode": override.get("api_mode"),
                "max_tokens": override.get("max_tokens"),
                "credential_pool": override.get("credential_pool"),
            }
            if override_runtime.get("api_key"):
                if override_runtime.get("credential_pool") is None:
                    override_runtime["credential_pool"] = _credential_pool_for_provider(
                        override.get("provider")
                    )
                logger.debug(
                    "Session model override (fast): session=%s config_model=%s -> override_model=%s provider=%s",
                    resolved_session_key or "", model, override_model,
                    override_runtime.get("provider"),
                )
                return override_model, override_runtime
```

- `_resolve_gateway_model`(gateway/run.py:3256-3269 @ 863e313):config.yaml `model.default` 唯一权威。
- `_rehydrate_session_model_override`(gateway/run.py:22681-22741 @ 863e313):重启后惰性回灌持久化的 /model override——store 只存非密部分(model/provider/base_url),api_key **从不落盘**,此处经 `_resolve_runtime_agent_kwargs_for_provider` 重新解析凭据;内存已有 override 则 no-op(live 态优先)。
- override 带 api_key ⇒ 直接短路返回(补 credential_pool);无 api_key ⇒ 落入慢路径,先 env 解析再叠加(7043-7046 经 `_apply_session_model_override`,gateway/run.py:22743-22771 @ 863e313:None 值字段跳过,不 clobber 有效默认)。

### 10.2 慢路径:env/provider + channel override(7002-7041)

`_resolve_runtime_agent_kwargs`(gateway/run.py:2511-2579 @ 863e313):`resolve_runtime_provider()` 解析主 provider,AuthError 时区分 429 限额与真实凭据失效(#32790 日志措辞)再试 fallback 链;返回 api_key/base_url/provider/requested_provider/api_mode/command/args/credential_pool/max_tokens。runtime 若自带显式 model 则覆盖(7003-7010)。

channel override(7012-7041):`_get_channel_override`(gateway/run.py:3296-3322 @ 863e313)按 chat_id → thread_id → parent_id 顺序查 `channel_overrides`(Discord 子线程继承父频道条目);`ch.provider` 存在则整组换 provider 凭据,provider 捆绑的 model 仅在 override **未**显式指定 model 时采纳(7038-7041)。

### 10.3 空模型兜底(7050-7097)—— #35314

事故因果:中断后恢复 turn 恰逢 mtime 键控配置缓存 miss → 读到空 user_config → model="" 建 agent → 每次 API 调用 HTTP 400 "No models provided" → 会话静默直到用户手动重发。三层兜底:

gateway/run.py:7052-7062、7072-7097 @ 863e313(节选)
```python
        if not model and runtime_kwargs.get("provider"):
            try:
                from hermes_cli.models import get_default_model_for_provider
                model = get_default_model_for_provider(runtime_kwargs["provider"])
        ...
        if not model:
            _lr_state = (... resolved_session_key ...)
            _lr_star = self._peek_session_state("*")
            _recovered = (
                (_lr_state.conversation.last_resolved_model if _lr_state else "")
                or (_lr_star.conversation.last_resolved_model if _lr_star else "")
            )
            if _recovered:
                logger.warning("Empty model resolved ... recovering last-known-good model %s ...", ...)
                model = _recovered
        elif model:
            if resolved_session_key:
                self._session_state(
                    resolved_session_key
                ).conversation.last_resolved_model = model
            self._session_state("*").conversation.last_resolved_model = model
```

①provider 有但 model 空 → provider 目录首个默认(`hermes auth add openai-codex` 未跑 `hermes model` 的场景);②仍空 → 本会话 last_resolved_model,再退 `"*"` 会话(进程级 last-known-good,给首见会话用);③解析成功则双写缓存(会话 + `"*"`)。

**调用点**:turn pipeline gateway/run.py:4445;/model 命令 gateway/slash_commands.py:4055;消息路径 15906、16112;hygiene 压缩 16714、16858;cron 19506;其他 21459 @ 863e313。

### 10.4 重实现要点

1. 模型解析写成纯定序合并函数,层级顺序用 docstring 声明并测试锁定;每层"部分覆盖"跳过 None,不 clobber。
2. 密钥不落盘:持久化 override 只存非密字段,回灌时按 provider 现场重解析凭据;失败保留无凭据 override 让下游 env 路径接手。
3. "空值兜底链"三层:provider 目录默认 → 会话 LKG → 进程 LKG(`"*"`);LKG 在每次成功解析时回写。空模型建 agent = 会话静默死,值得三层防。
4. channel override 查找顺序(自身→线程→父)与提示词解析保持同一套 key 函数,免两处漂移。
5. 兜底触发必须 WARN 带 issue 号——它掩盖的是上游配置读的 bug,不能无声。

---

## 11. `_resolve_turn_agent_config` + `_sync_session_model_from_agent`(7101-7194)

### 11.1 单 turn 配置(7101-7146)

把 (model, runtime_kwargs) 收拢成 route dict:`{"model", "runtime"(9 字段), "signature"(7 元组:model/provider/requested_provider/base_url/api_mode/command/args), "request_overrides"}`。signature 即 agent 缓存失效键。`/fast`(`_service_tier`)开且模型支持 Priority Processing 时,`resolve_fast_mode_overrides(model)` 产出 `request_overrides` 附加到 API 调用;不支持/异常 → 空 dict(7136-7146)。消费点:gateway/run.py:4567(turn pipeline)、19532(cron)@ 863e313。

### 11.2 实际后端回写(7148-7194)

**问题**:provider fallback 可能在会话行创建后切换 `agent.model/provider`,session DB 元数据仍显示旧后端——列表/仪表盘/后续工具汇报失真。**做法**:turn 收尾在 executor 线程(`run_sync` 闭包,调用点 5564)直用同步 `_db`:读 `get_session(session_id)` → 对比 model 与 `model_config.gateway_runtime`(provider/base_url/api_mode/fallback_active,None/"" 剔除)→ 有差异才 `update_session_meta`(7186-7192);全程 try/except debug 降级。幂等短路(7187-7190)避免每 turn 无谓写。

重实现要点:①运行时实际生效的后端要回写元数据,"配置说的"与"实际用的"分开记(`fallback_active` 标志);②回写做 diff-then-write;③明确线程语境(off-loop 用同步句柄)写进 docstring。

---

## 12. Reaction 事件 → HookRegistry(7196-7210)

gateway/run.py:7196-7210 @ 863e313(节选)
```python
    async def _handle_reaction_event(self, ctx: Dict[str, Any]) -> None:
        ...
        event_name = str(ctx.get("event_name") or "reaction:added")
        try:
            await self.hooks.emit(event_name, ctx)
        except Exception:
            logger.debug("[Gateway] reaction hook emit failed", exc_info=True)
```

adapter 经 `set_reaction_handler`(gateway/platforms/base.py:3349 @ 863e313)注册本方法(接线点 gateway/run.py:11097-11099、12469-12471、13411-13413);adapter 提供的 `event_name`("reaction:added"/"reaction:removed")直接作为 hook 事件名,与 `agent:*` 家族同一命名面;异常吞掉——hook 契约是非阻塞,绝不拖垮 adapter 事件循环。重实现要点:平台事件进用户 hook 的桥要"归一化命名 + 永不 raise + 默认值兜底"。

---

## 13. Adapter fatal error 处理:三层结构(7212-7371)

### 13.1 第一层:detach + shield(7212-7238)

**事故因果**(docstring 记录,观测于 2026-07-21):fatal 通知在**故障 adapter 自己的 polling task**上到达;handler 内的 disconnect 会 cancel 那个 polling task——而 handler 正跑在它上面,于是 handler 死在"fatal 日志已打、重连还没入队"之间,telegram 从 adapters 弹出后**再也没人重连**,静默失联。

gateway/run.py:7227-7238 @ 863e313
```python
        tasks = getattr(self, "_fatal_handler_tasks", None)
        if tasks is None:
            tasks = self._fatal_handler_tasks = set()
        task = asyncio.create_task(self._handle_adapter_fatal_error_detached(adapter))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        # Await so callers that expect completion still get it — but through
        # shield(): Task.cancel() on the caller also cancels the future it is
        # awaiting (_fut_waiter), so a plain `await task` would tunnel the
        # cancellation straight into the "detached" task. shield() absorbs
        # it: the caller sees CancelledError, the handler runs to completion.
        await asyncio.shield(task)
```

真工作放 detached task(强引用集合防 GC);`await asyncio.shield(task)` 兼顾"调用方等到完成"与"调用方被 cancel 不殃及 handler"——裸 `await task` 会让 cancel 顺 `_fut_waiter` 隧穿进"detached"任务。

### 13.2 第二层:stranded 兜底(7240-7273)

impl 跑完(或炸了)后 finally 检查:retryable 且 platform 既不在 `self.adapters` 也不在 `_failed_platforms` 且非关机中 ⇒ **stranded**——ERROR + `_exit_with_failure` + `stop()`,让 service manager 重启进程,拒绝静默半瘫(7257-7273)。

### 13.3 第三层:impl(7275-7371)

顺序:
1. **stale 通知丢弃**(7284-7291):槽位现任 adapter 既非本 adapter 亦非空 ⇒ 是输给了已成功重连的延迟通知,不动现任的状态,直接 return。
2. **runtime status**(7299-7314):`relay_disabled` → "disabled"(用户主动 opt-out,不是红色 fatal);retryable → "retrying";否则 "fatal"(经 `_update_platform_runtime_status`,gateway/run.py:7913)。
3. **claim-then-disconnect**(7316-7327):先 `adapters.pop` 声明接管、同步 `delivery_router.adapters`,**再** await disconnect——否则并发的第二个 fatal 通知在 await 期间仍见 "existing",同一对象被 disconnect 两次。断连走 §6 的限时防御路径。
4. **重连入队**(7329-7345):retryable 且有 platform_config 且未入队 ⇒ `_failed_platforms[platform] = {"config":…, "attempts":0, "next_retry":monotonic()}`,并 `_ensure_reconnect_watcher_running()`(gateway/run.py:12368-12390 @ 863e313:watcher task 死了就重生,#70344;watcher 本体 `_platform_reconnect_watcher` 12392 起,30→300s 指数退避、retryable 无限重试、经 `_spawn_supervised` 带 on_spawn 回写句柄,11515-11519,#71758 曾 17.5h 静默停机)。
5. **末平台策略**(7347-7371):无 adapter 且无排队 ⇒ 停机(retryable 则 failure 退出让 systemd 重启);无 adapter 但**有**排队 ⇒ **保活**——注释明言旧行为(exit-with-failure 触发重启)把瞬时断网变成重启循环、每次杀光进程内状态,现在让 cron 继续跑、watcher 后台恢复。

### 13.4 重实现要点

1. 故障处理器可能跑在故障源自己的任务上——真工作必须 detach;要向调用方回执完成时用 `shield(task)` 而非裸 await。
2. 三层防线:主逻辑 → stranded 终检(不重连、不排队、不关机 = 异常态,退出求重启)→ watcher 死亡重生;每层针对一个已发生的静默失联事故。
3. 处理并发通知:先快照现任、stale 即弃;claim(pop)在任何 await 之前完成。
4. "全平台皆失"细分:有重连队列 = 瞬态,保活;无队列 = 终态,退出。重启不是免费的——它清空进程内状态。
5. 错误分类三态(disabled/retrying/fatal)直达状态面板,用户 opt-out 不得渲染成红色故障。

---

## 14. 活跃工作计数(7373-7421)

`_request_clean_exit`(7373-7376):置 `_exit_cleanly/_exit_reason` + set `_shutdown_event`。

**问题**(#60432):关机 drain 只看 `_running_agents` 会**结构性看不见** cron 与 API server 的在跑工作——曾在 cron 的终端命令还在跑时报 `active_at_start=0` 直接杀工具子进程。

gateway/run.py:7381-7387 @ 863e313
```python
    def _active_work_count(self) -> int:
        """All agent work the gateway must expose and drain as one total."""
        return (
            self._running_agent_count()
            + self._active_cron_job_count()
            + self._active_api_run_count()
        )
```

- `_active_cron_job_count`(7389-7407):cron job 走调度器自有线程池(cron/scheduler.py::run_job)、独立 AIAgent,完全在 `_running_agents` 之外;从 `cron.scheduler.get_running_job_ids()` 取数,import 失败回 0(最小测试替身兼容)。
- `_active_api_run_count`(7409-7421):`adapters[API_SERVER].active_agent_work_count()`;注释说明只有主 profile 可能有 api_server(端口绑定,次级 multiplex profile 建不了)。
- 消费点:runtime status 写出 7800/7823/7850;drain 循环 10090/10118/10126/10133 @ 863e313。

重实现要点:①"活跃工作"是跨子系统总和,每个绕开主注册表跑 agent 的子系统(cron、API、未来新增)都必须贡献一个计数器,否则 drain 对它盲;②计数器 best-effort(异常回 0),但要理解这意味着 drain 保护也随之失效——统计源自身要稳。

---

## 15. Scale-to-zero 判定与 watcher(7423-7666)

**问题**:托管(Fly)实例想在无流量时被平台挂起(suspend)省钱,又要能被唤醒不丢消息。纯逻辑在 gateway/scale_to_zero.py(124 行,纯函数可单测);run.py 侧把它绑到活 runner/transport。

### 15.1 armed 条件(7494-7528)

三条全真才启动 watcher(`should_arm`,gateway/scale_to_zero.py:91-104 @ 863e313):Labs 开关 `HERMES_SCALE_TO_ZERO` env 为 truthy(**非** config 键,D11);messaging 仅 relay 或全无(`messaging_is_relay_only_or_absent`,72-83——直连平台持长连接套接字,无法缩零);relay wakeUrl 已注册(gateway/relay/__init__.py:228 @ 863e313——没有唤醒目标的挂起实例是黑洞)。

**修过的 bug**(注释 7504-7512):`config.platforms` 为**每个已知平台预置 disabled 占位 PlatformConfig**,直接拿 `.keys()` 判会把 ~20 个占位当直连平台,真 relay-only 实例**永不 armed**;修为只数 `pc.enabled` 的平台(与 adapter 连接循环同一"活跃平台"定义):

gateway/run.py:7513-7517 @ 863e313
```python
            platforms = (
                [p for p, pc in self.config.platforms.items() if getattr(pc, "enabled", False)]
                if self.config
                else []
            )
```

未 armed 的诊断(7530-7574):**仅对已 opt-in 实例**打一行 INFO(为何没 arm:relay_only?wake_url?);未 opt-in 不 arm 是常态,保持静默——"为什么不挂起"变成 log grep 而非上机翻箱。

### 15.2 idle 判定(7429-7469、7576-7584)

`is_idle`(gateway/scale_to_zero.py:107-124 @ 863e313)三合取:无在跑 agent turn;距最近**真实**入站 ≥ 超时(config `gateway.scale_to_zero.idle_timeout_minutes`,默认 5min,`parse_idle_timeout_seconds` 对非法/非正值回默认——0/负会导致"即刻休眠",永非本意);无活后台工作。

后台工作检查(7429-7455):`_background_tasks` 未完成任务、`tools.async_delegation.active_count()>0`、`process_registry.has_any_active()` 或 `pending_watchers`——backgrounded delegate_task/kanban/后台 terminal 不计入 `_running_agent_count`,但挂起会弄丢它们(D3/F7);检查永不 raise。

入站时钟(7586-7601):`_scale_to_zero_note_real_inbound` 在 `_handle_message` 单一入站咽喉处、**仅非 internal 事件**时打点(gateway/run.py:14391-14397 @ 863e313——内部完成/重放事件不算流量,算了会让真 idle 的 gateway 永不休眠);若处于 wake 后冷却期,顺带把 runtime status 从 draining 恢复为 running 并清冷却。

### 15.3 watcher 与 dormant 序列(7611-7666)

gateway/run.py:7628-7662 @ 863e313(节选)
```python
        await asyncio.sleep(min(interval, 30.0))  # let startup settle
        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    return
                if time.time() < self._scale_to_zero_cooldown_until:
                    continue
                if not self._scale_to_zero_is_idle():
                    continue
                adapter = self._relay_adapter_for_dormancy()
                if adapter is None:
                    continue
                go_dormant = getattr(adapter, "go_dormant", None)
                if not callable(go_dormant):
                    continue
                ...
                try:
                    self._update_runtime_status("draining")
                ...
                try:
                    result = go_dormant()
                    if asyncio.iscoroutine(result):
                        await result
                ...
                self._scale_to_zero_cooldown_until = time.time() + max(interval, 60.0)
```

dormant 序列要点:①status 标 `draining`(与既有状态机复用词,但**不**置 `_running=False`);②relay `adapter.go_dormant()`(gateway/relay/adapter.py:872、gateway/relay/ws_transport.py:634 @ 863e313)= going_idle 握手 + **保留重连 supervisor 的**套接字关闭——刻意不是 `disconnect()`、不是 stop 路径(F12/F14);③**不**调 mark_resume_pending(D13:suspend 保 RAM,无须恢复标记);④设 ≥60s 再武装冷却——否则唤醒后 backlog 还没来得及刷新入站时钟,又被同一读数打回休眠。进程保活,由 Fly `autostop:"suspend"` 冻结、autostart 收到 wakeUrl poke 解冻,保留的 supervisor 重拨、connector 排空缓冲 backlog。watcher 每轮 try/except 永不崩 gateway。启动点:gateway/run.py:11539-11552 @ 863e313(`_spawn_supervised`,arm 失败不拦启动)。

夹在中间的 `_restart_loop_guard_config`(7471-7492):auto-resume 重启循环断路器(#30719 defense-3)的 `(max_restarts, window_seconds)` 配置读取,`max_restarts<=0` 关断路器——消费者在别处(gateway.restart_loop_guard)。

### 15.4 重实现要点

1. 缩零决策链拆成纯函数模块(enabled/relay_only/is_idle/should_arm 都吃 plain 值),runner 只做绑定——可单测、可讲清。
2. "idle" ≠ 无 turn:必须并入后台工作与真实入站时钟;内部合成事件不得喂时钟。
3. dormant 与 shutdown-drain 是不同状态机路径:保 supervisor 的 socket close,不碰 stop 流程;唤醒后要有再武装冷却防抖振。
4. arm 失败对 opted-in 实例必须可 grep 诊断;对未 opt-in 实例必须静默。
5. 配置目录里的"占位条目"是谓词毒药——一切"有哪些平台"判定要过 `enabled` 过滤,并和连接循环共用同一定义。
6. 超时解析对 0/负值防御性回默认:错误配置的失败模式应是"不休眠",不是"狂休眠"。

---

## 16. 状态标签 + drain 期排队 + FIFO 注释块(7668-7691)

gateway/run.py:7668-7678 @ 863e313
```python
    def _status_action_label(self) -> str:
        return "restart" if self._restart_requested else "shutdown"

    def _status_action_gerund(self) -> str:
        return "restarting" if self._restart_requested else "shutting down"

    def _queue_during_drain_enabled(self) -> bool:
        # Both "queue" and "steer" modes imply the user doesn't want messages
        # to be lost during restart — queue them for the newly-spawned gateway
        # process to pick up.  "interrupt" mode drops them (current behaviour).
        return self._restart_requested and self._busy_input_mode in {"queue", "steer"}
```

- 两个标签函数让用户可见文案随"这是 restart 还是 shutdown"变化(消费点 8769-8771、14855-14857、15403、25559 @ 863e313)。
- `_queue_during_drain_enabled`:**仅 restart** 且 busy_input_mode ∈ {queue, steer} 时,drain 期间的消息排给新进程接手;interrupt 模式照旧丢弃。语义推理:用户选 queue/steer 已表达"别丢我的消息"。
- 7680-7690 是 `/queue` FIFO 的设计注释块(单槽 adapter dict 当队头 + overflow list 当队尾;/new//reset 清空),`_enqueue_fifo` 签名在 7691——主体与 `_promote_queued_event`(7705)/`_queue_depth`(7736)属下一段,此处只记边界:enqueue 逻辑为"槽空进槽、槽满进 overflow"(7698-7703),promote 在每轮 drain 后把 overflow 头补进槽(调用点 25487)。

重实现要点:①busy 模式(interrupt/queue/steer)是用户意图声明,重启丢不丢消息应从它推导而非另设开关;②面向用户的状态文案由单一函数产出,防止 restart/shutdown 措辞散落不一致。

---

## 17. 调用关系汇总(对方文件:行号 @ 863e313)

| 本段成员 | 被谁调 / 调谁 |
|---|---|
| `_session_state`/`_peek_session_state` | 全 run.py + 三 mixin 通用;legacy 视图 setter 也走它(gateway/session_state.py:252) |
| legacy 视图 | 测试面 + mixin/adapter 少量现场;定义 gateway/session_state.py:419/453 |
| `__init__` | start_gateway 入口构造;`SessionStore`/`AsyncSessionStore`(session.py:1206/1189)、`SessionTurnLeaseRegistry`(gateway/turn_lease.py:115)、`PairingStore`(gateway/pairing.py)、`HookRegistry`(gateway/hooks.py)、`AsyncSessionDB/SessionDB`(hermes_state.py) |
| `_wire_teams_pipeline_runtime` | gateway/run.py:11349;→ plugins/teams_pipeline/runtime.py:98 |
| `_sync_voice_mode_state_to_adapter` | gateway/run.py:11120 / 12484 / 13457 |
| `_connect_initial_adapter_with_timeout` | gateway/run.py:11113 / 13379 |
| `_bounded_adapter_teardown`/`_safe_adapter_disconnect` | stop 路径与 fatal impl(7327) |
| `_session_key_for_source` | gateway/slash_commands.py:124/741/1203/1762/3503/3592/3640/3692/3789/4039/4502/4691/4746/4964/5195/5329/5398/5447/5585;gateway/run.py:8175/8214/14521/15811/18864/18951/20322/20521/20619/25704 |
| topic 模式家族 | 消费:gateway/run.py:15635-15642(lobby 门)、15063(/new root)、5559(压缩轮转同步)、5684(lane 判定)、20142(topic 标题改名)、20225(/topic status);gateway/slash_commands.py:262/266(new header);DB:hermes_state.py:9033/9071/9193 |
| `_normalize_source_for_session_key` | gateway/slash_commands.py:1761/3502/4500/4689(均 to_thread) |
| `_resolve_session_agent_runtime` | gateway/run.py:4445/15906/16112/16714/16858/19506/21459;gateway/slash_commands.py:4055;→ gateway/run.py:2511/2582/2604/3256/3296/22681/22743 |
| `_resolve_turn_agent_config` | gateway/run.py:4567/19532 |
| `_sync_session_model_from_agent` | gateway/run.py:5564(run_sync 闭包,executor 线程) |
| `_handle_reaction_event` | 接线 gateway/run.py:11097-11099/12469-12471/13411-13413;→ gateway/platforms/base.py:3349 `set_reaction_handler` |
| `_handle_adapter_fatal_error` | 接线 gateway/run.py:11094/12466;→ gateway/platforms/base.py:3154 `set_fatal_error_handler`;→ `_ensure_reconnect_watcher_running`(12368)→ `_platform_reconnect_watcher`(12392,spawn 于 11515-11519) |
| `_active_work_count` | gateway/run.py:7800/7823/7850/10090/10118/10126/10133;→ cron/scheduler.py `get_running_job_ids` |
| scale-to-zero 家族 | arm:gateway/run.py:11539-11552;时钟:14391-14397;→ gateway/scale_to_zero.py 全部纯函数、gateway/relay/__init__.py:228、gateway/relay/adapter.py:872、gateway/relay/ws_transport.py:634;→ tools/async_delegation `active_count`、tools/process_registry |
| detach 原语 | → agent/async_utils.py:71 `consume_detached_task_result` |

---

## 18. 文档-代码冲突候选

1. **代码注释引用仓库外私有规范**:scale-to-zero 段注释指向 `~/nous/specs/scale-to-zero (decisions.md)`(gateway/run.py:7426-7427 @ 863e313:"See ~/nous/specs/ scale-to-zero (decisions.md) for the design + the F12/F14 distinctions"),该路径不在仓库内、website/docs 也无 gateway scale-to-zero 用户文档(全站仅 cron-internals.md:132 提及 Chronos 面向 scale-to-zero 部署)——D1-D13/F6-F14/§3.4 等编号体系在仓库内不可解引用。属"作者自绘地图不可得",读者只能以代码注释为准。
2. **`/voice` 文档模式名与代码内部三态不同名**:website/docs/reference/slash-commands.md:246 记 `/voice [on|off|tts|join|channel|leave|status]`,代码持久化三态为 `{"off","voice_only","all"}`(gateway/run.py:6365 @ 863e313)。是用户命令面→内部模式的映射差异而非行为矛盾,具体映射(on/tts 各落到哪个内部态)待 slash_commands 段核实后定案。
3. **一致性验证(非冲突,记录以闭环)**:telegram.md:838 "root-lobby 提醒 30 秒每 chat 限一条"与 `_TELEGRAM_LOBBY_REMINDER_COOLDOWN_S = 30.0`(gateway/run.py:6756)一致;telegram.md:857 降级行为描述与 `build_session_key` DM+thread_id 规则(session.py:1103-1115)一致;telegram.md:830 的 `telegram_dm_topic_mode(chat_id, user_id, …)` 表结构与 hermes_state.py:9033 读取参数一致。

---

## 19. 边界与遗留

- 7691 行 `_enqueue_fifo` 起的 /queue FIFO 三方法主体、`_update_runtime_status`(7793)/`_update_platform_runtime_status`(7913)归下一段。
- `_load_prefill_messages` 等 11 个 ephemeral loader 与 `_active_profile_name`、`_enforce_agent_cache_cap`、`_session_expiry_watcher`、`_spawn_supervised`、`_release_turn_lease`、startup restore 排队/排空,均为本段引用、他段定义。
- SessionState 无驱逐(gateway/session_state.py:30-33 自认遗留);`hygiene_failure_streak` 进程内不持久(#79624 计划 schema 跟进)。
