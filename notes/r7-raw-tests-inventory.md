# R7 原始盘点 · tests/gateway/ 会话核心簇测试清单

> 基线 @ 863e313。判定方法:不按文件名猜,全部用 grep 追 import 目标与机制符号
> (`build_session_key`、`SessionStore(`/`AsyncSessionStore`、`_handle_active_session_busy_message`、
> `SessionTurnLeaseRegistry`/`run_generation`、`_session_stall_watcher`/`_watch_gateway_turn_inactivity`、
> `GatewayStreamConsumer`/`GatewayEventDispatcher`、`session_context` 各函数、`cached_agent`/`_evict_cached_agent`、
> `load_gateway_config`、`deliver_wake` 等)。tests/gateway/ 顶层共 576 项;其中 449 个文件至少 import
> 一个 R7 模块,但 `gateway.config`(365)与 `gateway.run`(231)绝大多数只是 fixture 级使用,
> 本清单只收"测试主题就是 R7 机制"的文件。相关 grep 中间产物在会话 scratchpad,不入库。

R7 簇文件:gateway/run.py、session.py、session_context.py、session_state.py、session_stall.py、
memory_monitor.py、turn_lease.py、turn_context.py、wake.py、stream_consumer.py、stream_events.py、
stream_dispatch.py、config.py、profile_routing.py、message_timestamps.py。

各模块被测试直接 import 的文件数(精确 grep):run 231 / session 190 / config 365 /
session_context 8 / stream_consumer 11 / wake 3 / profile_routing 2 / stream_events 2 /
session_state、session_stall、memory_monitor、turn_lease、turn_context、stream_dispatch、
message_timestamps 各 1(即各自有一个同名专属测试)。

## 一、按机制分组(每个文件一句话:钉死了什么行为)

### 1. 会话键与路由(11)

- `test_session.py` — 簇核心综合卷:`build_session_key` 的平台/发送者/线程维度拆分 + SessionStore 基本读写(31 处 key 符号、29 处 store 符号,双组之首)。
- `test_base_topic_sessions.py` — BasePlatformAdapter 的 topic 感知会话:同 chat 不同 topic 必须派生不同 session key。
- `test_handoff_thread_session_key.py` — CLI→Discord 交接后,线程目标必须按线程维度成键,不得落回 chat 级键。
- `test_interrupt_key_match.py` — adapter 侧与 gateway 侧计算的 interrupt key 必须一致,否则打断打不中正在跑的会话。
- `test_profile_routing.py` — `gateway/profile_routing.py` 单元卷:`parse_profile_routes`/`match_profile_route` 的路由匹配语义。
- `test_profile_resolution.py` — `GatewayRunner._resolve_profile_home_for_source`:入站来源如何解析到 profile home。
- `test_multiplex_phase0.py` — 多 profile 复用的 Phase 0 地基:profile 命名空间进入 session key(`_session_key_namespace`)。
- `test_multiplex_http_routing.py` — Phase 1:webhook 入站 `/p/<profile>/` 路径路由到对应 profile。
- `test_queued_native_image_session_key.py` — busy 排队的原生图片消息必须携带正确 session key 与 run_generation 重放。
- `test_matrix_project_context_isolation.py` — Matrix 两个项目频道的会话上下文隔离(键隔离 + 缓存隔离的组合回归)。
- `test_telegram_prune_stale_topic_binding_31501.py` — #31501:Telegram DM topic 与会话键的陈旧绑定要被剪除。

### 2. SessionStore 持久化与找回(17)

- `test_async_session_store.py` — AsyncSessionStore 边界:store 调用必须经 to_thread 下线程,守住 gateway 事件循环。
- `test_async_session_db.py` — AsyncSessionDB offload 门面契约 + "gateway 内不得裸调同步 SessionDB"守卫。
- `test_session_store_lock_io.py` — 持有 `session_store._lock` 期间禁止阻塞 I/O。
- `test_session_store_prune.py` — `SessionStore.prune_old_entries` 及调用它的 gateway watcher(过期剪枝)。
- `test_session_store_stale_prune.py` — `_prune_stale_sessions_locked`:崩溃后自愈剪枝。
- `test_session_store_runtime_stale_guard.py` — #54878:sessions.json 路由条目运行时 stale 自愈。
- `test_session_store_expiry_finalized.py` — 会话过期终结必须以 `session_reset` 收尾关闭。
- `test_session_load_bool.py` — #46994:load 布尔字段的反序列化回归。
- `test_load_transcript_db_only.py` — `load_transcript` 仅凭 SQLite 即可返回消息,不依赖 JSONL 文件。
- `test_routing_save_fast_path.py` — 单行路由保存快路径(不整写 sessions.json)。
- `test_dedupe_user_turns.py` — #47237:transcript 中用户回合去重规则。
- `test_13121_shutdown_inflight_transcript_flush.py` — #13121:restart/shutdown 必须把 in-flight 回合的 transcript 落进 SQLite,resume 才有临场上下文。
- `test_7100_transient_failure_transcript.py` — #7100:429/超时等瞬态失败不得丢用户消息(区别于 context-overflow 的整体跳写)。
- `test_restart_resume_pending.py` — resume_pending 会话连续性:重启后待续回合的找回路径。
- `test_incomplete_gateway_turns.py` — 只有隐藏 reasoning 的不完整回合的落盘与恢复规则。
- `test_first_turn_session_meta_rebaseline.py` — 首回合 `session_meta` 行必须重新基线进 transcript。
- `test_undo_rewind_session.py` — `SessionStore.rewind_session`:/undo [N] 的回卷原语。

相邻但计入本组证据面:`test_35809_auto_reset_clean_context.py`(#35809 压缩耗尽触发 auto-reset 后 store 状态必须干净)、`test_session_dm_thread_seeding.py`(DM 线程会话隔离播种)、`test_channel_continuity_hint.py`(Slack/Discord 频道会话连续性提示)、`test_clean_shutdown_marker.py`(干净停机标记写入)、`test_session_hygiene.py`(run.py 会话卫生自动压缩:冷却/失败连击,14 处符号)。

### 3. busy 策略与 steer(12)

- `test_busy_session_ack.py` — busy 会话收到新消息时的确认回执策略(`_handle_active_session_busy_message` 主卷,10 处符号)。
- `test_busy_session_auth_bypass.py` — #17775:未授权用户不得借 busy 路径绕过鉴权。
- `test_active_session_text_merge.py` — busy 期间 TEXT 追加消息的排队合并语义。
- `test_command_bypass_active_session.py` — slash 命令必须绕过 base adapter 的 active-session 拦截直达 gateway。
- `test_clarify_active_session_bypass.py` — busy 期间 clarify 回复不得被 busy 策略吞掉。
- `test_internal_event_never_interrupts_busy_session.py` — 内部合成事件永不打断 busy 会话。
- `test_steer_command.py` — /steer 命令处理器:向运行中回合注入转向文本。
- `test_steer_fifo_overwrite.py` — #75164:/steer 回退路径不得覆写 FIFO 队头。
- `test_queue_command.py` — /queue 命令(running-agent 路径)的入队行为。
- `test_queue_consumption.py` — agent 正常完成后 /queue 消息的消费顺序。
- `test_42039_duplicate_user_message.py` — #42039:busy 路径导致用户消息在 state.db 双写。
- `test_max_concurrent_sessions.py` — `max_concurrent_sessions` 活跃会话上限的准入拒绝。

相邻:`test_session_split_brain_11016.py`(#11016:Telegram 会话 busy 态裂脑,横跨 busy+租约)、`test_subagent_protection_30170.py`(#30170:子代理运行期的 busy 保护)、`test_gateway_silence_tokens.py`(故意沉默 token 与 busy 回执的交互)。

### 4. 回合租约与 run generation(8)

- `test_turn_lease.py` — #64934:`SessionTurnLeaseRegistry`/`TurnLeaseToken` 行为卷——每会话回合租约的获取/续期/释放。
- `test_session_race_guard.py` — 会话竞态守卫:同一 session key 不得并发跑两个 agent 回合。
- `test_session_state_cleanup.py` — `_release_running_agent_state` 与 SessionDB 停机清理的成对释放。
- `test_stale_finalize_suppression.py` — #71643:过期 run_generation 的流式 finalize 必须被压制,不得覆盖新回合输出。
- `test_abandoned_turn_process_cleanup.py` — #76115:被遗弃 gateway 回合的子进程清理(租约失效后的资源回收)。
- `test_conversation_scope_funnel.py` — `_clear_conversation_scope`:会话作用域清理的唯一漏斗。
- `test_tool_response_drop_recovery.py` — #29346:工具响应静默丢失后按 run_generation 恢复不残留。
- `test_session_split_brain_11016.py` — #11016:租约/键不一致导致的会话裂脑修复(与 busy 组共享)。

### 5. 看门狗:stall / expiry / inactivity / memory(6)

- `test_session_stall_watchdog.py` — #72016:`_session_stall_watcher` 会话停摆检测——何时发停摆通知、何时清除(session_stall.py 的谓词)。
- `test_gateway_inactivity_timeout.py` — `_watch_gateway_turn_inactivity`:agent 回合分级不活动超时。
- `test_watchdog_review_76354.py` — #76354:活动时间戳写入预算与 watchdog 观测点的复审回归。
- `test_53175_cleanup_off_loop.py` — #53175:同步清理把 gateway 事件循环卡死,清理必须下线程。
- `test_session_store_expiry_finalized.py` — `_session_expiry_watcher` 到期终结路径(与 store 组共享)。
- `test_memory_monitor.py` — `gateway.memory_monitor`:周期性 RSS 记录线程的启停与幂等。

### 6. 流式投递(9)

- `test_stream_consumer.py` — `GatewayStreamConsumer` 主卷:流式输出中 MEDIA 指令剥离等消费语义。
- `test_stream_consumer_draft.py` — 原生 draft 流式(边生成边改草稿消息)的更新节奏。
- `test_stream_consumer_fresh_final.py` — 长寿预览消息改走"新发 final"路径的判定。
- `test_stream_consumer_silence.py` — 流式中的故意沉默 token 压制(不发半截沉默)。
- `test_stream_consumer_thread_routing.py` — 流式消息的 thread/topic 路由修复:预览与 final 必须落同一线程。
- `test_stream_events.py` — 结构化流事件协议(MessageChunk/MessageStop/ToolCallChunk…)+ `GatewayEventDispatcher` 分发行为。
- `test_code_fence_tracking.py` — 消息分片/截断/流式路径上的 ``` 围栏跟踪闭合(stream_consumer 的 `ensure_closed_code_fences`)。
- `test_escape_reasoning_fences.py` — `escape_code_fences_for_display`:reasoning 内层 ``` 转义,防止破坏外层围栏。
- `test_stale_finalize_suppression.py` — 过期流式 finalize 压制(与租约组共享)。

### 7. 会话上下文与 env(8)

- `test_session_env.py` — `session_context` 的 `set_session_vars`/`get_session_env`:会话作用域 env 的设置与读取。
- `test_session_context_inheritance.py` — 跨会话 ContextVar 继承泄漏守卫:新任务不得继承别的会话的 contextvars。
- `test_delegation_session_id_leak.py` — 委派子代理不得顶替父会话的 session identity。
- `test_compression_session_id_persistence.py` — #29335:压缩后 `session_entry.session_id` 必须持久化,session_context 不漂移。
- `test_async_delivery_capability.py` — #10760:`async_delivery_supported` 能力门(哪些通道允许异步投递)。
- `test_prompt_tail_freeze.py` — 系统提示字节稳定:会话上下文 pin 作为 ephemeral 尾部,不得抖动破坏 prompt cache。
- `test_turn_context.py` — 从 `_handle_message_with_agent` 抽出的 TurnContext/TurnRunner 接缝的单元契约。
- `test_message_timestamps.py` — `message_timestamps` 单元卷:时间戳前缀的 coerce/strip/render 往返。

### 8. agent 缓存(12)

- `test_agent_cache.py` — gateway AIAgent 缓存集成主卷:命中/未命中、逐出、复用时序。
- `test_cached_agent_max_iterations.py` — PR #48127:缓存 agent 复用时 max_iterations 必须刷新。
- `test_10710_auto_reset_evicts_cached_agent.py` — #10710:auto-reset 必须逐出缓存 agent,否则旧上下文摘要泄漏进新会话。
- `test_48031_model_switch_after_auto_reset.py` — #48031:auto-reset 后首条 /model 切换不得被 was_auto_reset 清理块吞掉。
- `test_35994_reset_button_deadlock.py` — #35994:Telegram /new 确认按钮路径的重置死锁(缓存逐出 × store 锁)。
- `test_73297_memory_flush_on_reset.py` — #73297:`_cleanup_agent_resources` 关停 memory provider 前必须先排干后台写队列。
- `test_stale_self_heal_agent_cache_eviction.py` — #54878×#54947 交互:stale 自愈触发的缓存逐出不误伤。
- `test_session_id_cache_coherence.py` — #54947:跨进程守卫不得让本进程 agent 缓存与 session_id 失配。
- `test_fallback_eviction.py` — #7130:失败回合才触发 fallback 逐出,成功回合不逐出。
- `test_shutdown_cache_cleanup.py` — #11205:gateway 停机时清理缓存 agent 的 memory provider。
- `test_mcp_reload_refreshes_cached_agents.py` — /reload-mcp 后缓存 agent 的工具列表必须刷新。
- `test_moa_one_shot_restore.py` — MoA 一次性模型覆写在成功/失败后都要恢复(缓存 agent 状态还原)。

### 9. 配置装载(6)

- `test_config.py` — `gateway.config` 主卷:`load_gateway_config` 解析、平台段、默认值与校验。
- `test_config_env_bridge_authority.py` — config.yaml → 环境变量桥(run.py)的权威顺序:谁覆盖谁。
- `test_config_cwd_bridge.py` — config.yaml → env 桥的 cwd 相关键处理。
- `test_channel_overrides.py` — #1955:per-channel 模型与系统提示覆写(ChannelOverride)。
- `test_checkpoint_config.py` — 文件系统 checkpoint 配置的运行时生效。
- `test_71671_faulthandler_no_stderr.py` — #71671:`sys.stderr=None` 时 run.py 启动的 faulthandler.enable 不得崩。

相邻(profile 运行时作用域,属 run.py `_profile_runtime_scope`):`test_64674_multiplex_primary_token_scope.py`、`test_75349_whatsapp_multiplex_secret_scope.py`。

### 10. wake 注入(1)

- `test_wake_delivery.py` — `gateway/wake.py` 全卷:`deliver_wake` 的 adapter push 直投与 `_self_post_chat_completion` 自投回退、`adapter_supports_push` 判定。

相邻:`test_kanban_notifier_apiserver_wake.py`(kanban 通知走 api_server 无状态唤醒,主题在 kanban_watchers,非 R7)。

## 二、行为规格价值最高的 42 个文件(pytest 路径,单行,供 scripts/run_tests.sh)

```
tests/gateway/test_session.py tests/gateway/test_base_topic_sessions.py tests/gateway/test_handoff_thread_session_key.py tests/gateway/test_interrupt_key_match.py tests/gateway/test_profile_routing.py tests/gateway/test_async_session_store.py tests/gateway/test_async_session_db.py tests/gateway/test_session_store_lock_io.py tests/gateway/test_session_store_prune.py tests/gateway/test_session_store_stale_prune.py tests/gateway/test_session_store_runtime_stale_guard.py tests/gateway/test_session_store_expiry_finalized.py tests/gateway/test_load_transcript_db_only.py tests/gateway/test_13121_shutdown_inflight_transcript_flush.py tests/gateway/test_restart_resume_pending.py tests/gateway/test_busy_session_ack.py tests/gateway/test_busy_session_auth_bypass.py tests/gateway/test_active_session_text_merge.py tests/gateway/test_steer_command.py tests/gateway/test_queue_consumption.py tests/gateway/test_42039_duplicate_user_message.py tests/gateway/test_max_concurrent_sessions.py tests/gateway/test_session_split_brain_11016.py tests/gateway/test_turn_lease.py tests/gateway/test_session_race_guard.py tests/gateway/test_session_state_cleanup.py tests/gateway/test_stale_finalize_suppression.py tests/gateway/test_session_stall_watchdog.py tests/gateway/test_gateway_inactivity_timeout.py tests/gateway/test_memory_monitor.py tests/gateway/test_stream_consumer.py tests/gateway/test_stream_consumer_thread_routing.py tests/gateway/test_stream_events.py tests/gateway/test_session_env.py tests/gateway/test_session_context_inheritance.py tests/gateway/test_turn_context.py tests/gateway/test_agent_cache.py tests/gateway/test_cached_agent_max_iterations.py tests/gateway/test_config.py tests/gateway/test_config_env_bridge_authority.py tests/gateway/test_wake_delivery.py tests/gateway/test_message_timestamps.py
```

选取原则:每个机制组保底 1–3 个"机制同名主卷"(test_turn_lease、test_stream_events、
test_wake_delivery、test_memory_monitor、test_message_timestamps、test_turn_context 是各自模块
唯一直测),其余按符号频次与 docstring 主题取行为面最宽的;纯平台适配器口味的(Telegram/
Matrix/Slack 专属)让位给平台簇轮次。

## 三、issue 号命名(test_NNNNN_*)且属本簇的文件

| 文件 | issue | 机制组 |
|---|---|---|
| test_7100_transient_failure_transcript.py | #7100 | SessionStore 持久化 |
| test_10710_auto_reset_evicts_cached_agent.py | #10710 | agent 缓存 |
| test_13121_shutdown_inflight_transcript_flush.py | #13121 | SessionStore 持久化 |
| test_35809_auto_reset_clean_context.py | #35809 | SessionStore/auto-reset |
| test_35994_reset_button_deadlock.py | #35994 | agent 缓存 × store 锁 |
| test_42039_duplicate_user_message.py | #42039 | busy 策略 |
| test_48031_model_switch_after_auto_reset.py | #48031 | agent 缓存/auto-reset |
| test_53175_cleanup_off_loop.py | #53175 | 看门狗/清理下线程 |
| test_64674_multiplex_primary_token_scope.py | #64674 | profile 运行时作用域(run.py) |
| test_71671_faulthandler_no_stderr.py | #71671 | run.py 启动 |
| test_73297_memory_flush_on_reset.py | #73297 | agent 缓存清理链 |
| test_75349_whatsapp_multiplex_secret_scope.py | #75349 | profile 运行时作用域(边缘,WhatsApp 口味) |

前缀 issue 命名但**不属**本簇:test_25107(slash_commands.py 持久化)、test_73771(delivery
媒体去重)。另有后缀 issue 命名的本簇文件:test_session_split_brain_11016(#11016)、
test_subagent_protection_30170(#30170)、test_telegram_prune_stale_topic_binding_31501(#31501)、
test_watchdog_review_76354(#76354);缓存组的 #54878/#54947/#7130/#11205/#48127/#64934/#71643/
#75164/#76115/#72016/#29346/#29335/#46994/#47237/#17775/#75164 见各组行内标注。
