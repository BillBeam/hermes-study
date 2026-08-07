# R8A 配置项全表 · 值得先看的几片

本文件由 `scripts/config_table.py` 生成,**不要手改**——它存在的意义就是不会与表脱节。
表本身回答“有哪些键”,本文件回答“该先读哪些行”。

> **读之前先读 `scripts/config_table.py` 开头的边界说明。** 一句话:
> 这 856 个键是“**有默认值的键**”的全集,不是“用户能合法写的键”的全集。

- 配置键合计:**856**(叶子 719 / 分支 137)
- 静态环境变量合计:**151**(运行时会被就地灌到 308,见脚本说明)

## 1. Python 与 TypeScript 都不读的键(2)

候选死配置。**逐条人工复核过再下结论**——本轮第一版就在这里错判过 5 个。

- `bedrock.discovery.refresh_interval` — 默认 `3600`,定义于 hermes_cli/config_defaults.py:792,文档:website/docs
- `display.copy_shortcut` — 默认 `"auto"`,定义于 hermes_cli/config_defaults.py:1280,文档:无

## 2. 只有 TypeScript 读的键(4)

Python 侧完全不碰;配置经 `config.get` RPC 发给 TS 客户端后由它解释。
**任何只扫 Python 的分析都会把这些判成死键。**

- `terminal.font_family` — apps/desktop/src/app/session/hooks/use-hermes-config.ts:112
- `display.tui_agents_nudge` — ui-tui/src/app/createGatewayEventHandler.ts:481
- `display.show_cost` — ui-tui/src/gatewayTypes.ts:89
- `dashboard.show_token_analytics` — web/src/App.tsx:411

## 3. 全部文档面零提及的键(105)

这是本轮 ◇-1 的清单,也是**唯一站得住的文档缺口数字**
(为什么不报百分比,见 `notes/r8a-90` ◇-1)。R11 对表时可直接消费。

- `database.journal_mode` (hermes_cli/config_defaults.py:17)
- `database.wal_autocheckpoint` (hermes_cli/config_defaults.py:20)
- `database.journal_size_limit` (hermes_cli/config_defaults.py:21)
- `max_live_sessions` (hermes_cli/config_defaults.py:30)
- `agent.restart_drain_timeout` (hermes_cli/config_defaults.py:47)
- `agent.restart_after_turn_timeout` (hermes_cli/config_defaults.py:54)
- `agent.build_wait_timeout` (hermes_cli/config_defaults.py:62)
- `agent.intent_ack_continuation` (hermes_cli/config_defaults.py:88)
- `agent.task_completion_guidance` (hermes_cli/config_defaults.py:94)
- `agent.parallel_tool_call_guidance` (hermes_cli/config_defaults.py:103)
- `agent.environment_probe` (hermes_cli/config_defaults.py:111)
- `agent.environment_hint` (hermes_cli/config_defaults.py:118)
- `agent.coding_context` (hermes_cli/config_defaults.py:133)
- `agent.gateway_timeout_warning` (hermes_cli/config_defaults.py:162)
- `agent.gateway_notify_interval` (hermes_cli/config_defaults.py:182)
- `agent.gateway_startup_restore_drain_timeout` (hermes_cli/config_defaults.py:219)
- `terminal.modal_mode` (hermes_cli/config_defaults.py:253)
- `terminal.daemon_term_grace_seconds` (hermes_cli/config_defaults.py:269)
- `terminal.docker_shm_size` (hermes_cli/config_defaults.py:345)
- `browser.allow_unsafe_evaluate` (hermes_cli/config_defaults.py:386)
- `mcp_discovery_timeout` (hermes_cli/config_defaults.py:485)
- `mcp_single_query_discovery_timeout` (hermes_cli/config_defaults.py:495)
- `mcp.auto_reload_on_config_change` (hermes_cli/config_defaults.py:508)
- `compression.max_attempts` (hermes_cli/config_defaults.py:589)
- `compression.abort_on_summary_failure` (hermes_cli/config_defaults.py:677)
- `auxiliary.transient_retries` (hermes_cli/config_defaults.py:838)
- `auxiliary.free_only` (hermes_cli/config_defaults.py:846)
- `auxiliary.openrouter_model` (hermes_cli/config_defaults.py:852)
- `display.resume_exchanges` (hermes_cli/config_defaults.py:1079)
- `display.resume_max_user_chars` (hermes_cli/config_defaults.py:1080)
- `display.resume_max_assistant_chars` (hermes_cli/config_defaults.py:1081)
- `display.resume_max_assistant_lines` (hermes_cli/config_defaults.py:1082)
- `display.resume_skip_tool_only` (hermes_cli/config_defaults.py:1088)
- `display.busy_steer_ack_enabled` (hermes_cli/config_defaults.py:1093)
- `display.tui_auto_resume_recent` (hermes_cli/config_defaults.py:1104)
- `display.tui_agents_nudge` (hermes_cli/config_defaults.py:1109)
- `display.reasoning_full` (hermes_cli/config_defaults.py:1119)
- `display.final_response_markdown` (hermes_cli/config_defaults.py:1129)
- `display.persistent_output` (hermes_cli/config_defaults.py:1133)
- `display.persistent_output_max_lines` (hermes_cli/config_defaults.py:1134)
- `display.persist_prompts` (hermes_cli/config_defaults.py:1138)
- `display.inline_diffs` (hermes_cli/config_defaults.py:1139)
- `display.turn_completion_explainer` (hermes_cli/config_defaults.py:1159)
- `display.cli_refresh_interval` (hermes_cli/config_defaults.py:1188)
- `display.user_message_preview` (hermes_cli/config_defaults.py:1189)
- `display.user_message_preview.first_lines` (hermes_cli/config_defaults.py:1190)
- `display.user_message_preview.last_lines` (hermes_cli/config_defaults.py:1191)
- `display.friendly_tool_labels` (hermes_cli/config_defaults.py:1210)
- `display.ephemeral_system_ttl` (hermes_cli/config_defaults.py:1249)
- `display.copy_shortcut` (hermes_cli/config_defaults.py:1280)
- `dashboard.turn_isolation` (hermes_cli/config_defaults.py:1313)
- `dashboard.compute_host_heartbeat_secs` (hermes_cli/config_defaults.py:1314)
- `dashboard.compute_host_respawn_max` (hermes_cli/config_defaults.py:1315)
- `stt.elevenlabs.language_code` (hermes_cli/config_defaults.py:1545)
- `stt.elevenlabs.tag_audio_events` (hermes_cli/config_defaults.py:1546)
- `stt.elevenlabs.diarize` (hermes_cli/config_defaults.py:1547)
- `voice.thinking_sound` (hermes_cli/config_defaults.py:1561)
- `wake_word.sherpa.model_dir` (hermes_cli/config_defaults.py:1602)
- `context.memory_trim` (hermes_cli/config_defaults.py:1627)
- `context.memory_trim.log_every_n` (hermes_cli/config_defaults.py:1632)
- `context.memory_trim.info_log_min_delta_mb` (hermes_cli/config_defaults.py:1635)
- `delegation.max_summary_chars` (hermes_cli/config_defaults.py:1700)
- `moa.active_preset` (hermes_cli/config_defaults.py:1756)
- `moa.trace_dir` (hermes_cli/config_defaults.py:1764)
- `discord.bots_require_inline_mention` (hermes_cli/config_defaults.py:1915)
- `discord.dm_role_auth_guild` (hermes_cli/config_defaults.py:1940)
- `discord.server_actions` (hermes_cli/config_defaults.py:1948)
- `discord.approval_mentions` (hermes_cli/config_defaults.py:1964)
- `cron.max_parallel_jobs` (hermes_cli/config_defaults.py:2232)
- `cron.output_retention` (hermes_cli/config_defaults.py:2236)
- `cron.session_db_timeout_seconds` (hermes_cli/config_defaults.py:2242)
- `kanban.worker_log_rotate_bytes` (hermes_cli/config_defaults.py:2276)
- `kanban.worker_log_backup_count` (hermes_cli/config_defaults.py:2277)
- `logging.max_size_mb` (hermes_cli/config_defaults.py:2382)
- `logging.backup_count` (hermes_cli/config_defaults.py:2383)
- `monitoring.gateway_health_export.metrics_enabled` (hermes_cli/config_defaults.py:2431)
- `monitoring.gateway_health_export.diagnostic_events_enabled` (hermes_cli/config_defaults.py:2432)
- `monitoring.gateway_health_export.warning_error_events_enabled` (hermes_cli/config_defaults.py:2433)
- `monitoring.gateway_health_export.export_interval_seconds` (hermes_cli/config_defaults.py:2434)
- `monitoring.gateway_health_export.logs_export_interval_seconds` (hermes_cli/config_defaults.py:2435)
- `monitoring.gateway_health_export.resource_attributes` (hermes_cli/config_defaults.py:2436)
- `gateway.loop_watchdog` (hermes_cli/config_defaults.py:2481)
- `gateway.scale_to_zero` (hermes_cli/config_defaults.py:2498)
- `gateway.scale_to_zero.idle_timeout_minutes` (hermes_cli/config_defaults.py:2499)
- `gateway.restart_loop_guard` (hermes_cli/config_defaults.py:2514)
- `gateway.restart_loop_guard.max_restarts` (hermes_cli/config_defaults.py:2515)
- `gateway.max_inbound_media_bytes` (hermes_cli/config_defaults.py:2551)
- `gateway.media_delivery_allow_dirs` (hermes_cli/config_defaults.py:2576)
- `gateway.trust_recent_files` (hermes_cli/config_defaults.py:2585)
- `gateway.trust_recent_files_seconds` (hermes_cli/config_defaults.py:2589)
- `sessions.auto_archive` (hermes_cli/config_defaults.py:2664)
- `sessions.auto_archive_days` (hermes_cli/config_defaults.py:2667)
- `sessions.fts_optimize_notice` (hermes_cli/config_defaults.py:2707)
- `sessions.search_slow_ms` (hermes_cli/config_defaults.py:2721)
- `updates.refresh_cua_driver` (hermes_cli/config_defaults.py:2791)
- `paste_collapse_threshold` (hermes_cli/config_defaults.py:2973)
- `paste_collapse_threshold_fallback` (hermes_cli/config_defaults.py:2974)
- `paste_collapse_char_threshold` (hermes_cli/config_defaults.py:2975)
- `computer_use.max_image_dimension` (hermes_cli/config_defaults.py:2988)
- `computer_use.capture_after_mode` (hermes_cli/config_defaults.py:2991)
- `computer_use.no_overlay` (hermes_cli/config_defaults.py:3000)
- `desktop.electron_flags` (hermes_cli/config_defaults.py:3075)
- `desktop.disable_gpu` (hermes_cli/config_defaults.py:3083)
- `desktop.auto_continue.freshness_minutes` (hermes_cli/config_defaults.py:3100)
- `desktop.auto_continue.max_attempts` (hermes_cli/config_defaults.py:3102)

## 4. 叶子名过于常见、读取点统计不可信的键(121)

叶子名形如 `enabled` / `timeout` / `mode`。**这些行的 `py_sites` / `ts_sites` 只能当上界看。**

<details><summary>展开</summary>

- `model`
- `terminal.backend`
- `terminal.timeout`
- `web.backend`
- `checkpoints.enabled`
- `compression.enabled`
- `bedrock.discovery.enabled`
- `auxiliary.vision.provider`
- `auxiliary.vision.model`
- `auxiliary.vision.timeout`
- `auxiliary.web_extract.provider`
- `auxiliary.web_extract.model`
- `auxiliary.web_extract.timeout`
- `auxiliary.compression.provider`
- `auxiliary.compression.model`
- `auxiliary.compression.timeout`
- `auxiliary.skills_hub.provider`
- `auxiliary.skills_hub.model`
- `auxiliary.skills_hub.timeout`
- `auxiliary.approval.provider`
- `auxiliary.approval.model`
- `auxiliary.approval.timeout`
- `auxiliary.mcp.provider`
- `auxiliary.mcp.model`
- `auxiliary.mcp.timeout`
- `auxiliary.title_generation.enabled`
- `auxiliary.title_generation.provider`
- `auxiliary.title_generation.model`
- `auxiliary.title_generation.timeout`
- `auxiliary.memory_query_rewrite.provider`
- `auxiliary.memory_query_rewrite.model`
- `auxiliary.memory_query_rewrite.timeout`
- `auxiliary.tts_audio_tags.provider`
- `auxiliary.tts_audio_tags.model`
- `auxiliary.tts_audio_tags.timeout`
- `auxiliary.triage_specifier.provider`
- `auxiliary.triage_specifier.model`
- `auxiliary.triage_specifier.timeout`
- `auxiliary.kanban_decomposer.provider`
- `auxiliary.kanban_decomposer.model`
- `auxiliary.kanban_decomposer.timeout`
- `auxiliary.profile_describer.provider`
- `auxiliary.profile_describer.model`
- `auxiliary.profile_describer.timeout`
- `auxiliary.goal_judge.provider`
- `auxiliary.goal_judge.model`
- `auxiliary.goal_judge.timeout`
- `auxiliary.curator.provider`
- `auxiliary.curator.model`
- `auxiliary.curator.timeout`
- `auxiliary.monitor.provider`
- `auxiliary.monitor.model`
- `auxiliary.monitor.timeout`
- `auxiliary.background_review.provider`
- `auxiliary.background_review.model`
- `auxiliary.background_review.timeout`
- `auxiliary.moa_reference.provider`
- `auxiliary.moa_reference.model`
- `auxiliary.moa_reference.timeout`
- `auxiliary.moa_aggregator.provider`
- `auxiliary.moa_aggregator.model`
- `auxiliary.moa_aggregator.timeout`
- `display.runtime_footer.enabled`
- `display.pet.enabled`
- `dashboard.theme`
- `tts.provider`
- `tts.openai.model`
- `tts.gemini.model`
- `tts.mistral.model`
- `tts.minimax.model`
- `tts.kittentts.model`
- `tts.neutts.model`
- `tts.deepinfra.model`
- `stt.enabled`
- `stt.provider`
- `stt.local.model`
- `stt.groq.model`
- `stt.openai.model`
- `stt.mistral.model`
- `stt.deepinfra.model`
- `wake_word.enabled`
- `wake_word.provider`
- `wake_word.openwakeword.model`
- `human_delay.mode`
- `context.memory_trim.enabled`
- `memory.provider`
- `delegation.model`
- `delegation.provider`
- `moa.presets.default`
- `moa.presets.default.aggregator.provider`
- `moa.presets.default.aggregator.model`
- `moa.presets.default.enabled`
- `curator.enabled`
- `curator.backup.enabled`
- `discord.missed_message_backfill.enabled`
- `discord.missed_message_backfill.limit`
- `discord.voice_fx.enabled`
- `approvals.mode`
- `approvals.timeout`
- `security.website_blocklist.enabled`
- `cron.model`
- `cron.provider`
- `code_execution.mode`
- `tools.tool_search.enabled`
- `logging.level`
- `model_catalog.enabled`
- `model_catalog.url`
- `monitoring.gateway_health_export.enabled`
- `monitoring.gateway_health_export.resource_attributes.service.name`
- `monitoring.gateway_health_export.resource_attributes.deployment.environment.name`
- `monitoring.export.otlp.enabled`
- `gateway.message_timestamps.enabled`
- `streaming.enabled`
- `telemetry.shared_metrics.enabled`
- `lsp.enabled`
- `x_search.model`
- `secrets.bitwarden.enabled`
- `secrets.bitwarden.encrypted_cache.enabled`
- `secrets.onepassword.enabled`
- `proxy.enabled`
- `desktop.auto_continue.enabled`

</details>

## 5. 无人读取的环境变量(4)

- `NOUS_BASE_URL` — 文档:website/docs
- `AIRTABLE_API_KEY` — 文档:website/docs
- `TENOR_API_KEY` — 文档:CONTRIBUTING,website/docs
- `QQ_SANDBOX` — 文档:website/docs

