#!/usr/bin/env python3
"""Assign every hermes-agent file to a learning layer, producing the ledger.

Input:  data/inventory.tsv  (path, kind, lines, bytes) — from inventory.py
Output: data/ledger.tsv     (path, kind, lines, layer, round, status)

Layers (learning treatment; see report for definitions):
  L1  机制精读     — deep line-level read; can re-implement from memory
  L2  结构级理解   — architecture + key paths understood; can navigate & explain role
  L3  知悉用途     — cataloged: know what it is, why it exists, when to consult
  L4  有理由排除   — generated / vendored / binary / media / lockfiles; justified skip
  LT  行为规格参照 — tests: consulted as behavioral spec alongside L1/L2 modules

Rules are ordered; first match wins. Every file MUST match a rule (fallback
raises), guaranteeing totality. Round assignment happens in round plans; this
script sets the planned round from RULES too.
"""
import csv
import fnmatch
import sys
from pathlib import Path

# (pattern, layer, planned_round)  — first match wins.
RULES = [
    # ---- L4: generated / lockfiles / binaries / media / data ----
    ("package-lock.json", "L4", "-"),
    ("uv.lock", "L4", "-"),
    ("flake.lock", "L4", "-"),
    ("*.png", "L4", "-"),
    ("*.woff2", "L4", "-"),
    ("*.pdf", "L4", "-"),
    ("*.ai", "L4", "-"),
    ("assets/*", "L4", "-"),
    ("contributors/*", "L4", "-"),          # contributor avatars/data
    ("mcp-research-data/*", "L4", "-"),     # research data dumps
    ("log.txt", "L4", "-"),
    ("sqlite_leak_fix.png", "L4", "-"),
    (".mailmap", "L4", "-"),
    ("website/static/*", "L4", "-"),
    ("website/build/*", "L4", "-"),
    ("*/package-lock.json", "L4", "-"),
    ("**/package-lock.json", "L4", "-"),
    ("**/*.woff2", "L4", "-"),
    ("**/*.png", "L4", "-"),
    ("**/*.jpg", "L4", "-"),
    ("**/*.jpeg", "L4", "-"),
    ("**/*.gif", "L4", "-"),
    ("**/*.ico", "L4", "-"),
    ("**/*.svg", "L4", "-"),
    ("**/*.mp3", "L4", "-"),
    ("**/*.wav", "L4", "-"),
    ("**/*.pt", "L4", "-"),
    ("**/*.onnx", "L4", "-"),
    ("tests/**/fixtures/**", "L4", "-"),
    ("tests/fixtures/**", "L4", "-"),

    # ---- LT: tests as behavioral spec ----
    ("tests/**", "LT", "with-module"),
    ("tests-js/**", "LT", "with-module"),
    ("**/*.test.ts", "LT", "with-module"),
    ("**/*.test.tsx", "LT", "with-module"),
    ("**/__tests__/**", "LT", "with-module"),

    # ---- L1: harness core mechanisms ----
    ("run_agent.py", "L1", "R2"),
    ("model_tools.py", "L1", "R3"),
    ("toolsets.py", "L1", "R3"),
    ("toolset_distributions.py", "L1", "R9A"),
    ("hermes_state.py", "L1", "R5"),
    ("hermes_state_schema.py", "L1", "R5"),
    ("hermes_state_common.py", "L1", "R5"),
    ("hermes_state_search.py", "L1", "R5"),   # R5 修订:FTS5 会话检索归入"状态与持久化"轮(R5 卡片点名)
    ("hermes_state_portability.py", "L1", "R5"),
    ("trajectory_compressor.py", "L1", "R9A"),
    ("batch_runner.py", "L1", "R9A"),
    ("mini_swe_runner.py", "L1", "R9A"),
    ("hermes_constants.py", "L1", "R2"),
    # R2 机制簇:回合主循环与模型接入(显式列举,R2 轮定稿)
    ("agent/conversation_loop.py", "L1", "R2"),
    ("agent/turn_context.py", "L1", "R2"),
    ("agent/turn_finalizer.py", "L1", "R2"),
    ("agent/turn_retry_state.py", "L1", "R2"),
    ("agent/turn_summary.py", "L1", "R2"),
    ("agent/tool_executor.py", "L1", "R2"),
    ("agent/tool_dispatch_helpers.py", "L1", "R2"),
    ("agent/iteration_budget.py", "L1", "R2"),
    ("agent/interrupt_compat.py", "L1", "R2"),
    ("agent/oneshot.py", "L1", "R2"),
    ("agent/agent_init.py", "L1", "R2"),
    ("agent/agent_runtime_helpers.py", "L1", "R2"),
    ("agent/codex_runtime.py", "L1", "R2"),
    ("agent/stream_single_writer.py", "L1", "R2"),
    ("agent/stream_diag.py", "L1", "R2"),
    ("agent/reasoning_timeouts.py", "L1", "R2"),
    ("agent/thinking_timeout_guidance.py", "L1", "R2"),
    ("agent/async_utils.py", "L1", "R2"),
    ("agent/jiter_preload.py", "L1", "R2"),
    ("agent/chat_completion_helpers.py", "L1", "R2"),
    ("agent/prompt_caching.py", "L1", "R2"),
    ("agent/credential_pool.py", "L1", "R2"),
    ("agent/credential_sources.py", "L1", "R2"),
    ("agent/credential_persistence.py", "L1", "R2"),
    ("agent/error_classifier.py", "L1", "R2"),
    ("agent/errors.py", "L1", "R2"),
    ("agent/retry_utils.py", "L1", "R2"),
    ("agent/rate_limit_tracker.py", "L1", "R2"),
    ("agent/nous_rate_guard.py", "L1", "R2"),
    ("agent/anthropic_adapter.py", "L1", "R2"),
    ("agent/codex_responses_adapter.py", "L1", "R2"),
    ("agent/gemini_native_adapter.py", "L1", "R2"),
    ("agent/bedrock_adapter.py", "L1", "R2"),
    ("agent/vertex_adapter.py", "L1", "R2"),
    ("agent/azure_identity_adapter.py", "L1", "R2"),
    ("agent/gemini_schema.py", "L1", "R2"),
    ("agent/moonshot_schema.py", "L1", "R2"),
    ("agent/lmstudio_reasoning.py", "L1", "R2"),
    ("agent/backend_identity.py", "L1", "R2"),
    ("agent/model_metadata.py", "L1", "R2"),
    ("agent/models_dev.py", "L1", "R2"),
    ("agent/auxiliary_client.py", "L1", "R2"),
    ("agent/usage_pricing.py", "L1", "R2"),
    ("agent/account_usage.py", "L1", "R2"),
    # R5 修订:上下文工程(构建/压缩)并入"状态与持久化"轮(R2 轮方案修订,见 round-2 报告)
    ("agent/context_compressor.py", "L1", "R5"),
    ("agent/conversation_compression.py", "L1", "R5"),
    ("agent/context_engine.py", "L1", "R5"),
    ("agent/context_breakdown.py", "L1", "R5"),
    ("agent/context_references.py", "L1", "R5"),
    ("agent/prompt_builder.py", "L1", "R5"),
    ("agent/system_prompt.py", "L1", "R5"),
    ("agent/bounded_response.py", "L1", "R5"),
    ("agent/message_sanitization.py", "L1", "R5"),
    ("agent/message_content.py", "L1", "R5"),
    ("agent/subdirectory_hints.py", "L1", "R5"),
    ("agent/coding_context.py", "L1", "R5"),
    ("agent/manual_compression_feedback.py", "L1", "R5"),
    # R9 修订:委派/多智能体并入研究管线轮(R2 轮方案修订)
    # R9A 改挂:研究管线轮不再单列,并入 R9A 的委派簇(理由见下方 R9 机制簇注释块)。
    ("agent/moa_loop.py", "L1", "R9A"),
    ("agent/moa_trace.py", "L1", "R9A"),
    ("agent/subagent_lifecycle.py", "L1", "R9A"),
    ("agent/delegation_context.py", "L1", "R9A"),
    # R3 机制簇涉及的 agent/ 文件(工具护栏、结果分类、子进程 secret 卫生)
    ("agent/tool_guardrails.py", "L1", "R3"),
    ("agent/tool_result_classification.py", "L1", "R3"),
    ("agent/secret_scope.py", "L1", "R3"),
    ("agent/redact.py", "L1", "R3"),
    # R5 机制簇补充:记忆存储侧 + 会话活动(R5 轮定稿,从 R3-R7 桶吸纳)
    ("agent/memory_manager.py", "L1", "R5"),
    ("agent/memory_provider.py", "L1", "R5"),
    ("agent/session_activity.py", "L1", "R5"),
    # R8D 补记:这两个当年被 R4/R5 顺手读了(status 是 R4/R5-deep-read),
    # 但规则表没跟着改,round 列一直挂在兜底桶里。补上,让计划列与事实列对齐。
    ("agent/runtime_cwd.py", "L1", "R4"),
    ("agent/shell_hooks.py", "L1", "R5"),
    # R8D 改名:原为 ("agent/*.py", "L1", "R3-R7") —— 一个**区间占位符**。
    # 它把"没有任何一轮认领过"伪装成了"已经计划好了":注释写着"其余 agent/ 文件在
    # 后续轮次开工时显式定轮",而那件事从 R5 之后一次也没发生。R8D 复核发现,
    # 这两个兜底桶里合计压着 171 个 L1 文件 / 104,656 行从未开工——比 R8D 自己
    # 的 L1 量还大一倍半,其中包括 R6 计划里点名的"skills 全链"与"学习闭环"全部。
    # 改成显式的 UNCLAIMED,于是任何一轮按 round 列报数时它都会自己跳出来。
    # 依据与逐文件清单见 notes/r8d-02-coverage-audit.md。
    # ------------------------------------------------------------------
    # R9 机制簇:R8D 核出的 179 个"从未被任何一轮认领"的 L1 文件(111,926 行)。
    # R8D 已把兜底桶从区间占位符 "R3-R7" 改成 UNCLAIMED,让它们在报数时跳出来;
    # R9 这一步是给它们**逐个显式定轮**,于是 UNCLAIMED 桶归零、计划列恢复可读。
    #
    # 单轮装不下(111,926 行 ≈ 历史单轮 L1 量的 2.6 倍),按 R7→R7B/R7C、
    # R8→R8A..D 的先例切四片。切片判据沿用 R8A 定的那一条——
    # **哪些文件必须同时摆在眼前,一个机制才讲得清**:
    #   R9A 能力的组织、扩展与委派  37 文件 / 38,893 行
    #   R9B 多模态与呈现            46 文件 / 27,325 行
    #   R9C 传输、凭据与可观测      47 文件 / 19,274 行
    #   R9D 代码智能与工具面        49 文件 / 26,434 行
    # 四片文件数 37..49、行数 19k..39k,均落在历史单轮区间内
    # (历史 L1 单轮:15..52 文件 / 21,893..68,645 行)。
    # 原 round=R9 的"研究管线"12 个文件不再单列:它们就是 R9A 的委派簇本身
    # (batch_runner / mini_swe_runner / trajectory_compressor / toolset_distributions
    #  + datagen-config-examples/),两条编号线并行只会让报数出现两个 R9。
    # 逐文件依据与簇内叙述见 notes/r9a-01-scope-and-split.md。
    # ------------------------------------------------------------------
    # R9A · skills 全链(4 文件 / 2328 行)
    ("agent/skill_utils.py", "L1", "R9A"),
    ("agent/skill_commands.py", "L1", "R9A"),
    ("agent/skill_bundles.py", "L1", "R9A"),
    ("agent/skill_preprocessing.py", "L1", "R9A"),
    # R9A · 学习闭环(11 文件 / 7352 行)
    ("agent/curator.py", "L1", "R9A"),
    ("agent/insights.py", "L1", "R9A"),
    ("agent/background_review.py", "L1", "R9A"),
    ("agent/curator_backup.py", "L1", "R9A"),
    ("agent/learning_graph_render.py", "L1", "R9A"),
    ("agent/verification_evidence.py", "L1", "R9A"),
    ("agent/learning_graph.py", "L1", "R9A"),
    ("agent/verification_stop.py", "L1", "R9A"),
    ("agent/learning_mutations.py", "L1", "R9A"),
    ("agent/learn_prompt.py", "L1", "R9A"),
    ("agent/verify_hooks.py", "L1", "R9A"),
    # R9A · 委派/MoA/研究管线(agent/ 半边共 5 文件 / 3,308 行;其中 moa_loop /
    # moa_trace / subagent_lifecycle / delegation_context 四个早有显式规则,
    # 已在上方就地改挂 R9A —— 在这里重列会成为永不命中的死规则,故只列剩下这一个。)
    ("agent/trajectory.py", "L1", "R9A"),
    # R9A · 出网约束(2 文件 / 2502 行)
    ("agent/proxy_sources/iron_proxy.py", "L1", "R9A"),
    ("agent/proxy_sources/__init__.py", "L1", "R9A"),
    # R9B · 多模态(9 文件 / 2807 行)
    ("agent/image_routing.py", "L1", "R9B"),
    ("agent/video_gen_provider.py", "L1", "R9B"),
    ("agent/image_gen_provider.py", "L1", "R9B"),
    ("agent/tts_provider.py", "L1", "R9B"),
    ("agent/transcription_provider.py", "L1", "R9B"),
    ("agent/image_gen_registry.py", "L1", "R9B"),
    ("agent/tts_registry.py", "L1", "R9B"),
    ("agent/video_gen_registry.py", "L1", "R9B"),
    ("agent/transcription_registry.py", "L1", "R9B"),
    # R9B · pet(11 文件 / 3653 行)
    ("agent/pet/generate/atlas.py", "L1", "R9B"),
    ("agent/pet/render.py", "L1", "R9B"),
    ("agent/pet/store.py", "L1", "R9B"),
    ("agent/pet/generate/orchestrate.py", "L1", "R9B"),
    ("agent/pet/generate/imagegen.py", "L1", "R9B"),
    ("agent/pet/generate/prompts.py", "L1", "R9B"),
    ("agent/pet/constants.py", "L1", "R9B"),
    ("agent/pet/manifest.py", "L1", "R9B"),
    ("agent/pet/state.py", "L1", "R9B"),
    ("agent/pet/__init__.py", "L1", "R9B"),
    ("agent/pet/generate/__init__.py", "L1", "R9B"),
    # R9B · 显示与本地化(8 文件 / 2882 行)
    ("agent/display.py", "L1", "R9B"),
    ("agent/markdown_tables.py", "L1", "R9B"),
    ("agent/i18n.py", "L1", "R9B"),
    ("agent/onboarding.py", "L1", "R9B"),
    ("agent/thread_scoped_output.py", "L1", "R9B"),
    ("agent/portal_tags.py", "L1", "R9B"),
    ("agent/battery.py", "L1", "R9B"),
    ("agent/reactions.py", "L1", "R9B"),
    # R9C · 传输层(16 文件 / 8811 行)
    ("agent/transports/codex_app_server_session.py", "L1", "R9C"),
    ("agent/relay_llm.py", "L1", "R9C"),
    ("agent/plugin_llm.py", "L1", "R9C"),
    ("agent/relay_runtime.py", "L1", "R9C"),
    ("agent/transports/chat_completions.py", "L1", "R9C"),
    ("agent/copilot_acp_client.py", "L1", "R9C"),
    ("agent/transports/codex.py", "L1", "R9C"),
    ("agent/transports/codex_app_server.py", "L1", "R9C"),
    ("agent/transports/codex_event_projector.py", "L1", "R9C"),
    ("agent/transports/hermes_tools_mcp_server.py", "L1", "R9C"),
    ("agent/transports/anthropic.py", "L1", "R9C"),
    ("agent/transports/types.py", "L1", "R9C"),
    ("agent/transports/bedrock.py", "L1", "R9C"),
    ("agent/relay_tools.py", "L1", "R9C"),
    ("agent/transports/base.py", "L1", "R9C"),
    ("agent/transports/__init__.py", "L1", "R9C"),
    # R9C · 凭据源与出网(9 文件 / 3451 行)
    ("agent/secret_sources/bitwarden.py", "L1", "R9C"),
    ("agent/secret_sources/onepassword.py", "L1", "R9C"),
    ("agent/secret_sources/command.py", "L1", "R9C"),
    ("agent/secret_sources/registry.py", "L1", "R9C"),
    ("agent/secret_sources/base.py", "L1", "R9C"),
    ("agent/secret_sources/_cache.py", "L1", "R9C"),
    ("agent/ssl_guard.py", "L1", "R9C"),
    ("agent/ssl_verify.py", "L1", "R9C"),
    ("agent/secret_sources/__init__.py", "L1", "R9C"),
    # R9C · 可观测与计费(17 文件 / 5461 行)
    ("agent/credits_tracker.py", "L1", "R9C"),
    ("agent/monitoring/gateway_health_export.py", "L1", "R9C"),
    ("agent/outbound_webhooks.py", "L1", "R9C"),
    ("agent/billing_view.py", "L1", "R9C"),
    ("agent/subscription_view.py", "L1", "R9C"),
    ("agent/monitoring/gateway_health.py", "L1", "R9C"),
    ("agent/trace_upload.py", "L1", "R9C"),
    ("agent/billing_usage.py", "L1", "R9C"),
    ("agent/monitoring/otlp_exporter.py", "L1", "R9C"),
    ("agent/monitoring/emitter.py", "L1", "R9C"),
    ("agent/monitoring/cron_health.py", "L1", "R9C"),
    ("agent/aux_accounting.py", "L1", "R9C"),
    ("agent/billing_links.py", "L1", "R9C"),
    ("agent/monitoring/events.py", "L1", "R9C"),
    ("agent/monitoring/redaction.py", "L1", "R9C"),
    ("agent/monitoring/policy.py", "L1", "R9C"),
    ("agent/monitoring/__init__.py", "L1", "R9C"),
    # R9D · 代码智能与文件(12 文件 / 5401 行)
    ("agent/lsp/servers.py", "L1", "R9D"),
    ("agent/lsp/client.py", "L1", "R9D"),
    ("agent/lsp/manager.py", "L1", "R9D"),
    ("agent/file_safety.py", "L1", "R9D"),
    ("agent/lsp/install.py", "L1", "R9D"),
    ("agent/lsp/cli.py", "L1", "R9D"),
    ("agent/lsp/eventlog.py", "L1", "R9D"),
    ("agent/lsp/workspace.py", "L1", "R9D"),
    ("agent/lsp/protocol.py", "L1", "R9D"),
    ("agent/lsp/range_shift.py", "L1", "R9D"),
    ("agent/lsp/reporter.py", "L1", "R9D"),
    ("agent/lsp/__init__.py", "L1", "R9D"),
    # R9D · 平台工具(5 文件 / 992 行)
    ("agent/web_search_registry.py", "L1", "R9D"),
    ("agent/web_search_provider.py", "L1", "R9D"),
    ("agent/browser_registry.py", "L1", "R9D"),
    ("agent/browser_provider.py", "L1", "R9D"),
    ("agent/kanban_stop.py", "L1", "R9D"),
    # R9D · 工具面杂项(5 文件 / 1356 行)
    ("agent/title_generator.py", "L1", "R9D"),
    ("agent/think_scrubber.py", "L1", "R9D"),
    ("agent/replay_cleanup.py", "L1", "R9D"),
    ("agent/process_bootstrap.py", "L1", "R9D"),
    ("agent/__init__.py", "L1", "R9D"),
    ("agent/*.py", "L1", "UNCLAIMED"),
    ("agent/**/*.py", "L1", "UNCLAIMED"),
    # R3 机制簇:工具基础设施与安全(显式列举,R3 轮定稿)
    ("tools/registry.py", "L1", "R3"),
    ("tools/schema_sanitizer.py", "L1", "R3"),
    ("tools/tool_output_limits.py", "L1", "R3"),
    ("tools/tool_result_storage.py", "L1", "R3"),
    ("tools/tool_search.py", "L1", "R3"),
    ("tools/lazy_deps.py", "L1", "R3"),
    ("tools/fuzzy_match.py", "L1", "R3"),
    ("tools/approval.py", "L1", "R3"),
    ("tools/write_approval.py", "L1", "R3"),
    ("tools/slash_confirm.py", "L1", "R3"),
    ("tools/path_security.py", "L1", "R3"),
    ("tools/url_safety.py", "L1", "R3"),
    ("tools/website_policy.py", "L1", "R3"),
    ("tools/tirith_security.py", "L1", "R3"),
    ("tools/threat_patterns.py", "L1", "R3"),
    ("tools/skills_guard.py", "L1", "R3"),
    ("tools/skills_ast_audit.py", "L1", "R3"),
    ("tools/osv_check.py", "L1", "R3"),
    ("tools/code_execution_tool.py", "L1", "R3"),
    ("tools/env_passthrough.py", "L1", "R3"),
    ("tools/env_probe.py", "L1", "R3"),
    ("tools/mcp_tool.py", "L1", "R3"),
    ("tools/mcp_oauth.py", "L1", "R3"),
    ("tools/mcp_oauth_manager.py", "L1", "R3"),
    ("tools/mcp_stdio_watchdog.py", "L1", "R3"),
    ("tools/mcp_dashboard_oauth.py", "L1", "R3"),
    ("tools/mcp_schema_cache.py", "L1", "R3"),
    ("tools/ansi_strip.py", "L1", "R3"),
    ("tools/binary_extensions.py", "L1", "R3"),
    # R4 机制簇:终端与执行环境(显式列举,R4 轮定稿)
    ("tools/environments/**", "L1", "R4"),         # base + 8 后端 + file_sync/modal_utils
    ("tools/terminal_tool.py", "L1", "R4"),
    ("tools/process_registry.py", "L1", "R4"),
    ("tools/daemon_pool.py", "L1", "R4"),
    ("tools/close_terminal_tool.py", "L1", "R4"),
    ("tools/read_terminal_tool.py", "L1", "R4"),
    ("tools/interrupt.py", "L1", "R4"),
    ("agent/runtime_cwd.py", "L1", "R4"),
    ("agent/shell_hooks.py", "L1", "R4"),
    ("tools/patch_parser.py", "L1", "R4"),
    ("tools/file_state.py", "L1", "R4"),
    ("tools/browser_tool.py", "L1", "R4"),
    ("tools/browser_supervisor.py", "L1", "R4"),
    ("tools/browser_cdp_tool.py", "L1", "R4"),
    ("tools/browser_dialog_tool.py", "L1", "R4"),
    ("tools/browser_camofox.py", "L1", "R4"),
    ("tools/browser_camofox_state.py", "L1", "R4"),
    ("agent/browser_provider.py", "L1", "R4"),
    ("agent/browser_registry.py", "L1", "R4"),
    ("tools/computer_use_tool.py", "L1", "R4"),
    ("tools/computer_use/**", "L1", "R4"),
    ("tools/desktop_ui.py", "L1", "R4"),
    # R5 机制簇补充:会话检索工具 + 检查点 + 记忆工具(R5 轮定稿,从 R3-R4 桶吸纳)
    ("tools/session_search_tool.py", "L1", "R5"),
    ("tools/checkpoint_manager.py", "L1", "R5"),
    ("tools/memory_tool.py", "L1", "R5"),
    # R8D 改名,理由同 agent/ 的兜底桶(见上,以及 notes/r8d-02-coverage-audit.md)。
    # R9 机制簇的 tools/ 半边(定轮依据同上,见 agent/ 段的注释块)。
    # R9A · skills 全链(8 文件 / 13515 行)
    ("tools/skills_hub.py", "L1", "R9A"),
    ("tools/skills_sync_client.py", "L1", "R9A"),
    ("tools/skills_tool.py", "L1", "R9A"),
    ("tools/skill_manager_tool.py", "L1", "R9A"),
    ("tools/skills_sync.py", "L1", "R9A"),
    ("tools/skill_usage.py", "L1", "R9A"),
    ("tools/blueprints.py", "L1", "R9A"),
    ("tools/skill_provenance.py", "L1", "R9A"),
    # R9A · 委派/MoA/研究管线(3 文件 / 5870 行)
    ("tools/delegate_tool.py", "L1", "R9A"),
    ("tools/async_delegation.py", "L1", "R9A"),
    ("tools/delegation_live_log.py", "L1", "R9A"),
    # R9B · 多模态(15 文件 / 17576 行)
    ("tools/tts_tool.py", "L1", "R9B"),
    ("tools/transcription_tools.py", "L1", "R9B"),
    ("tools/voice_mode.py", "L1", "R9B"),
    ("tools/vision_tools.py", "L1", "R9B"),
    ("tools/image_generation_tool.py", "L1", "R9B"),
    ("tools/wake_word.py", "L1", "R9B"),
    ("tools/flux3_video_tool.py", "L1", "R9B"),
    ("tools/video_generation_tool.py", "L1", "R9B"),
    ("tools/tts_streaming.py", "L1", "R9B"),
    ("tools/image_source.py", "L1", "R9B"),
    ("tools/tts_text_normalize.py", "L1", "R9B"),
    ("tools/xai_video_tools.py", "L1", "R9B"),
    ("tools/fal_common.py", "L1", "R9B"),
    ("tools/neutts_synth.py", "L1", "R9B"),
    ("tools/audio_container.py", "L1", "R9B"),
    # R9B · 显示与本地化(3 文件 / 407 行)
    ("tools/terminal_hints.py", "L1", "R9B"),
    ("tools/react_to_message_tool.py", "L1", "R9B"),
    ("tools/focus_pane_tool.py", "L1", "R9B"),
    # R9C · 凭据源与出网(5 文件 / 1551 行)
    ("tools/credential_files.py", "L1", "R9C"),
    ("tools/microsoft_graph_client.py", "L1", "R9C"),
    ("tools/xai_http.py", "L1", "R9C"),
    ("tools/microsoft_graph_auth.py", "L1", "R9C"),
    ("tools/openrouter_client.py", "L1", "R9C"),
    # R9D · 代码智能与文件(6 文件 / 5795 行)
    ("tools/file_operations.py", "L1", "R9D"),
    ("tools/file_tools.py", "L1", "R9D"),
    ("tools/read_extract.py", "L1", "R9D"),
    ("tools/working_diff.py", "L1", "R9D"),
    ("tools/read_preview_tool.py", "L1", "R9D"),
    ("tools/open_preview_tool.py", "L1", "R9D"),
    # R9D · 平台工具(13 文件 / 10926 行)
    ("tools/kanban_tools.py", "L1", "R9D"),
    ("tools/send_message_tool.py", "L1", "R9D"),
    ("tools/web_tools.py", "L1", "R9D"),
    ("tools/cronjob_tools.py", "L1", "R9D"),
    ("tools/discord_tool.py", "L1", "R9D"),
    ("tools/yuanbao_tools.py", "L1", "R9D"),
    ("tools/x_search_tool.py", "L1", "R9D"),
    ("tools/homeassistant_tool.py", "L1", "R9D"),
    ("tools/feishu_drive_tool.py", "L1", "R9D"),
    ("tools/todo_tool.py", "L1", "R9D"),
    ("tools/project_tools.py", "L1", "R9D"),
    ("tools/feishu_doc_tool.py", "L1", "R9D"),
    ("tools/thread_context.py", "L1", "R9D"),
    # R9D · 工具面杂项(8 文件 / 1964 行)
    ("tools/clarify_gateway.py", "L1", "R9D"),
    ("tools/managed_tool_gateway.py", "L1", "R9D"),
    ("tools/tool_backend_helpers.py", "L1", "R9D"),
    ("tools/clarify_tool.py", "L1", "R9D"),
    ("tools/hook_output_spill.py", "L1", "R9D"),
    ("tools/budget_config.py", "L1", "R9D"),
    ("tools/debug_helpers.py", "L1", "R9D"),
    ("tools/__init__.py", "L1", "R9D"),
    ("tools/*.py", "L1", "UNCLAIMED"),
    ("tools/**/*.py", "L1", "UNCLAIMED"),
    # R7 机制簇:网关会话核心与多路复用(显式列举,R7 轮定稿)。
    # 切片理由:原方案 R7=整个 gateway+cron(110k 行)超单轮预算,按 R1 方案
    # 允许的拆分条款切三片——R7 会话核心引擎(session_key 路由/会话状态/看门狗/
    # steer/流式桥)、R7B 平台接入面(platforms+relay)、R7C 运维生命周期与调度
    # (delivery/shutdown/slash/authz/cron)。R7B/R7C 开轮时再显式定轮。
    ("gateway/run.py", "L1", "R7"),
    ("gateway/session.py", "L1", "R7"),
    ("gateway/session_context.py", "L1", "R7"),
    ("gateway/session_state.py", "L1", "R7"),
    ("gateway/session_stall.py", "L1", "R7"),
    ("gateway/memory_monitor.py", "L1", "R7"),
    ("gateway/turn_lease.py", "L1", "R7"),
    ("gateway/turn_context.py", "L1", "R7"),
    ("gateway/wake.py", "L1", "R7"),
    ("gateway/stream_consumer.py", "L1", "R7"),
    ("gateway/stream_events.py", "L1", "R7"),
    ("gateway/stream_dispatch.py", "L1", "R7"),
    ("gateway/config.py", "L1", "R7"),
    ("gateway/profile_routing.py", "L1", "R7"),
    ("gateway/message_timestamps.py", "L1", "R7"),
    ("gateway/__init__.py", "L1", "R7"),
    ("cron/**/*.py", "L1", "R7C"),
    # R7C 修订:cron/ 顶层 .py 促升 L1。原先只有 cron/scripts/*.py 命中上一条
    # (fnmatch 下 "cron/**/*.py" 要求路径里有第二个 "/"),cron/scheduler.py 等
    # 九个文件落到末尾的 ("cron/**", "L2") 上。而 R7C 的主题就是"定时调度",
    # 卡片要求本簇达 L1 完成标准,主题本体不能留在 L2。先例:R6 同理由促升 8 个
    # memory backend 实现(commit 141a06e)。
    ("cron/*.py", "L1", "R7C"),
    ("gateway/platforms/*.py", "L1", "R7B"),
    ("gateway/relay/*.py", "L1", "R7B"),
    ("gateway/*.py", "L1", "R7C"),
    # R7C 修订:短语库 yaml 是 gateway/status_phrases.py 的数据本体(52 行),
    # 读 .py 不读它等于没读懂短语选择;与实现同层。
    ("gateway/assets/status_phrases.yaml", "L1", "R7C"),

    # ---- L2: structure-level ----
    # R8 四切片(R8A 开轮定稿)。原 round=R8 桶实测 268 文件 / 227,803 行,是 R7C
    # (28,282 行)的 8 倍,单轮闭合不了;按 R7 拆成 R7/R7B/R7C 的先例切四片。
    # 切片判据是"哪些文件必须同时摆在眼前,一个机制才讲得清":
    #   R8A 配置面   —— 决定一个配置键最终取什么值的全部模块 + R7C 移交的三笔账
    #   R8B CLI 主干 —— 进程入口、argparse 子命令树、命令分发 mixin
    #   R8C web 面   —— dashboard HTTP 服务、鉴权、路由
    #   R8D 其余     —— 彼此独立的功能模块(kanban / update / proxy / observability…)

    # R8A(本轮执行):15 文件 / 21,893 行,全部由 L2 促升 L1。
    # 促升理由同 R6(8 个 memory backend)、R7C(9 个 cron 顶层 .py)先例:
    # 轮次主题本体留在 L2,与「本轮达成 L1 完成标准」直接冲突。
    # (1) 配置解析链:默认值 → config.yaml → .env/环境变量 → 外部密钥源
    ("hermes_cli/config_defaults.py", "L1", "R8A"),
    ("hermes_cli/config.py", "L1", "R8A"),
    ("hermes_cli/config_migrations.py", "L1", "R8A"),
    ("hermes_cli/env_loader.py", "L1", "R8A"),
    ("hermes_cli/secret_prompt.py", "L1", "R8A"),
    # (2) 五个领域子模式(工具 / MCP / MoA / 技能 / 供应商回退)
    ("hermes_cli/tools_config.py", "L1", "R8A"),
    ("hermes_cli/mcp_config.py", "L1", "R8A"),
    ("hermes_cli/moa_config.py", "L1", "R8A"),
    ("hermes_cli/skills_config.py", "L1", "R8A"),
    ("hermes_cli/fallback_config.py", "L1", "R8A"),
    # (3) `hermes config` 的 argparse 面(处理函数在 config.py 里)
    ("hermes_cli/subcommands/config.py", "L1", "R8A"),
    # (4) R7C 移交的三笔账(移交理由见 reports/round-7c-*.md §10)
    ("hermes_cli/commands.py", "L1", "R8A"),           # 斜杠命令注册表,受配置门控
    ("hermes_cli/status.py", "L1", "R8A"),             # QQBot 环境变量倒置
    ("hermes_cli/pairing.py", "L1", "R8A"),            # 配对批准入口(门外那把钥匙)
    ("hermes_cli/subcommands/pairing.py", "L1", "R8A"),

    # R8B:CLI 主干与子命令树(本轮执行)。全部由 L2 促升 L1,理由同 R8A:
    # 轮次主题本体留在 L2,与「本轮达成 L1 完成标准」直接冲突。
    ("cli.py", "L1", "R8B"),
    ("hermes_bootstrap.py", "L1", "R8B"),
    ("hermes_cli/main.py", "L1", "R8B"),
    ("hermes_cli/cli_commands_mixin.py", "L1", "R8B"),
    ("hermes_cli/cli_billing_mixin.py", "L1", "R8B"),
    ("hermes_cli/cli_agent_setup_mixin.py", "L1", "R8B"),
    # R8B 开轮增补 2 个文件(理由见 reports/round-8b-*.md §1):
    # (a) _parser.py 就是 R8B 自己的范围描述里那句"argparse 子命令树"的本体
    #     ——顶层 parser 与 chat 子 parser 都在它里面(hermes_cli/_parser.py:1-11)。
    #     它当初落进 R8D 只是因为规则表没点名它、被 `hermes_cli/**` 兜底吃掉。
    # (b) profiles.py 是 R8A 报告 §1 明确写了"留 R8B"的文件(多实例隔离,决定
    #     读哪一份配置),而规则表同样漏了点名。`--profile/-p` 在 argparse 之前
    #     就被 main._apply_profile_override 消费掉,与主干耦合极紧,必须同处理。
    ("hermes_cli/_parser.py", "L1", "R8B"),
    ("hermes_cli/profiles.py", "L1", "R8B"),
    ("hermes_cli/subcommands/**", "L1", "R8B"),

    # R8C:dashboard 与 web 面
    ("hermes_cli/web_server.py", "L2", "R8C"),
    ("hermes_cli/web_models.py", "L2", "R8C"),
    ("hermes_cli/web_git.py", "L2", "R8C"),
    ("hermes_cli/auth.py", "L2", "R8C"),
    ("hermes_cli/auth_commands.py", "L2", "R8C"),
    ("hermes_cli/web_routers/**", "L2", "R8C"),
    ("hermes_cli/dashboard_auth/**", "L2", "R8C"),

    # R8D:其余(体量最大、内聚度最低;开轮时按同样方法再核一遍是否继续拆)
    #
    # R8D 开轮定稿(理由见 reports/round-8d-*.md §1):**不再拆轮,改拆深度**。
    # 复核结论:这 177 文件 / 125,634 行之所以最大,是因为它是"其余"这个收容桶,
    # 文件彼此独立(一个 CLI 子命令一个文件),再切一刀只会切出任意边界,
    # 切不出"必须同时摆在眼前才讲得清"的簇——而那正是 R8A 定下的切片判据。
    # 于是按 R8C 先例(计划层与完成状态分开记)分深度:
    #   L1 促升 —— 承载"别处学不到的 harness 机制"的 52 个文件 / 42,284 行;
    #   L2 保留 —— 其余 125 个文件 / 83,350 行,多是"把已学机制包一层 CLI"的子命令,
    #              以及 kanban(任务板产品功能)、setup/wizard(交互向导)、皮肤与横幅。
    # 体量与 R8B(50 文件 / 43,539 行)同级,是单轮真能读到 L1 标准的量。
    #
    # (A) 自我更新与自愈:harness 自己升级自己、自己修自己的 venv、
    #     在自己的 import 跑起来之前先自救。全仓独此一份,别的轮次没有对应物。
    ("hermes_cli/update_cmd.py", "L1", "R8D"),
    ("hermes_cli/update_lock.py", "L1", "R8D"),
    ("hermes_cli/managed_uv.py", "L1", "R8D"),
    ("hermes_cli/_early_recovery.py", "L1", "R8D"),
    ("hermes_cli/_scan_venv_blockers.py", "L1", "R8D"),
    ("hermes_cli/_startup_fast.py", "L1", "R8D"),
    ("hermes_cli/dep_ensure.py", "L1", "R8D"),
    ("hermes_cli/npm_engine.py", "L1", "R8D"),
    ("hermes_cli/psutil_android.py", "L1", "R8D"),
    ("hermes_cli/relaunch.py", "L1", "R8D"),
    ("hermes_cli/sqlite_runtime.py", "L1", "R8D"),
    ("hermes_cli/doctor.py", "L1", "R8D"),
    ("hermes_cli/session_recovery.py", "L1", "R8D"),
    # (B) provider / 模型的身份与路由substrate。R2 学的是"怎么调用一个模型",
    #     这里是"先认定这是哪个 provider、哪个模型、该走哪个 URL"——上游的那半。
    ("hermes_cli/providers.py", "L1", "R8D"),
    ("hermes_cli/provider_catalog.py", "L1", "R8D"),
    ("hermes_cli/runtime_provider.py", "L1", "R8D"),
    ("hermes_cli/model_normalize.py", "L1", "R8D"),
    ("hermes_cli/route_identity.py", "L1", "R8D"),
    ("hermes_cli/model_catalog.py", "L1", "R8D"),
    ("hermes_cli/models.py", "L1", "R8D"),
    ("hermes_cli/model_switch.py", "L1", "R8D"),
    ("hermes_cli/codex_models.py", "L1", "R8D"),
    # (C) 凭据生命周期与供应链安全:凭据散在多个存储里,谁负责统一它们的生老病死;
    #     以及 harness 对"自己装进来的东西"做什么审计。
    ("hermes_cli/credential_lifecycle.py", "L1", "R8D"),
    ("hermes_cli/secrets_cli.py", "L1", "R8D"),
    ("hermes_cli/onepassword_secrets_cli.py", "L1", "R8D"),
    ("hermes_cli/copilot_auth.py", "L1", "R8D"),
    ("hermes_cli/security_audit.py", "L1", "R8D"),
    ("hermes_cli/security_audit_startup.py", "L1", "R8D"),
    ("hermes_cli/security_advisories.py", "L1", "R8D"),
    ("hermes_cli/mcp_security.py", "L1", "R8D"),
    ("hermes_cli/urllib_security.py", "L1", "R8D"),
    ("hermes_cli/managed_scope.py", "L1", "R8D"),
    # (D) 扩展与分发:第三方代码怎么进到这个进程里来,以及进来之后挂在哪。
    ("hermes_cli/plugins.py", "L1", "R8D"),
    ("hermes_cli/middleware.py", "L1", "R8D"),
    ("hermes_cli/lifecycle.py", "L1", "R8D"),
    ("hermes_cli/profile_distribution.py", "L1", "R8D"),
    ("hermes_cli/mcp_catalog.py", "L1", "R8D"),
    ("hermes_cli/skills_hub.py", "L1", "R8D"),
    ("hermes_cli/agent_import.py", "L1", "R8D"),
    # (E) 根模块与进程边界:被全仓 import 的四个根文件,加上本地代理与跨进程租约。
    ("hermes_logging.py", "L1", "R8D"),
    ("hermes_time.py", "L1", "R8D"),
    ("utils.py", "L1", "R8D"),
    ("mcp_serve.py", "L1", "R8D"),
    ("hermes_cli/active_sessions.py", "L1", "R8D"),
    ("hermes_cli/mem_trim.py", "L1", "R8D"),
    ("hermes_cli/proxy/**", "L1", "R8D"),
    # 其余(kanban 任务板、setup/model 向导、皮肤横幅、各子命令包装层)留 L2。
    ("hermes_cli/**", "L2", "R8D"),
    ("gateway/platforms/**", "L2", "R7B"),  # adapter docs (ADDING_A_PLATFORM.md)
    ("gateway/**", "L2", "R7C"),            # assets (status_phrases.yaml)
    ("plugins/model-providers/**", "L2", "R2"),   # provider 插件注册面,随 R2 结构级学习
    # R6 修订:8 个记忆后端的实现 .py 促升 L1(R6 卡片要求对本簇达 L1 完成标准;
    # 它们是 MemoryProvider ABC 契约的全部生产实现,机制精读才能定案各家取舍)。
    # README/plugin.yaml 留 L2(文档与元数据,结构级即可)。
    ("plugins/memory/**/README.md", "L2", "R6"),
    ("plugins/memory/**/plugin.yaml", "L2", "R6"),
    ("plugins/memory/**/*.py", "L1", "R6"),
    ("plugins/memory/*.py", "L1", "R6"),
    ("plugins/**", "L2", "R6"),
    ("tui_gateway/**", "L2", "R10"),
    ("acp_adapter/**", "L2", "R10"),
    ("ui-tui/**", "L2", "R10"),
    ("apps/desktop/src/i18n/*", "L3", "R10"),   # translation data, not structure
    ("apps/**", "L2", "R10"),
    ("web/**", "L2", "R10"),
    # R5 吸纳:FTS5 CJK 分词器本体(vendored sqlite 头文件仍留 R10)
    ("native/fts5_cjk/fts5_cjk.c", "L2", "R5"),
    ("native/fts5_cjk/build.sh", "L2", "R5"),
    ("native/fts5_cjk/README.md", "L2", "R5"),
    ("native/**", "L2", "R10"),
    ("providers/**", "L2", "R2"),
    ("scripts/**", "L2", "R11"),
    ("docker/**", "L2", "R11"),
    ("nix/**", "L2", "R11"),
    (".github/**", "L2", "R11"),
    ("cron/**", "L2", "R7C"),

    # ---- L3: cataloged content ----
    # R11A 改判:这三条原本写的是 R6 —— 一个**已经收官的轮次**。
    # 与 R8D 在 L1 侧修掉的是同一个形态,而且更隐蔽:R8D 那边是区间占位符
    # ("R3-R7"),一眼看得出没定;这边写的是一个**真实存在、且已经完成**的轮次,
    # 于是按 round 列扫过去,它看起来不是"没排期",而是"早就做完了"。
    #
    # 事实(R11A 复核):R6 名下 1,347 个文件里,只有 24 个 L1 的 status 是
    # R6-deep-read;另外 1,080 个 L3(315,887 行)与 243 个 L2(116,078 行)
    # 自 R6 起 status 一直是 R1-inventoried,**八轮无人动过**。
    # 而 R6 是"记忆-技能-学习闭环",R1 称 skills/ 是"本仓库最独特的卖点"。
    #
    # 沿用 R8D 立的语义:**round 列只写"还在钩上"的轮次**;已经读到位的用
    # status 列表示(R11A 校准片 118 个文件 = R11A-aware)。UNCLAIMED 会在
    # 任何一轮按 round 报数时自己跳出来,这正是它存在的理由。
    # 依据见 reports/round-11a-ops-and-delivery.md §11 与
    # data/r11a/probes/skills_bucket_profile.py。
    ("skills/**", "L3", "UNCLAIMED"),
    ("optional-skills/**", "L3", "UNCLAIMED"),
    ("optional-mcps/**", "L3", "UNCLAIMED"),
    ("locales/**", "L3", "R11"),
    ("datagen-config-examples/**", "L3", "R9A"),
    ("website/**", "L3", "R11"),
    ("docs/**", "L3", "R11"),
    (".plans/**", "L3", "R11"),
    ("*.md", "L3", "R1"),
    ("**/*.md", "L3", "with-module"),

    # ---- root config / build files: L3 catalog ----
    ("*", "L3", "R11"),
]


def assign(path: str) -> tuple[str, str]:
    for pattern, layer, rnd in RULES:
        if fnmatch.fnmatch(path, pattern):
            return layer, rnd
    raise SystemExit(f"UNMATCHED FILE (totality violated): {path}")


def main() -> None:
    inv = Path(sys.argv[1] if len(sys.argv) > 1 else "data/inventory.tsv")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "data/ledger.tsv")
    # Preserve study status from an existing ledger when regenerating.
    prev_status: dict[str, str] = {}
    if out.exists():
        with out.open() as f:
            next(f, None)
            for line in f:
                cols = line.rstrip("\n").split("\t")
                if len(cols) >= 6:
                    prev_status[cols[0]] = cols[5]
    rows = []
    with inv.open() as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            path, kind, lines, nbytes = line.rstrip("\n").split("\t")
            layer, rnd = assign(path)
            if kind == "binary" and layer not in ("L4",):
                layer, rnd = "L4", "-"   # binaries are never study targets
            status = prev_status.get(path, "R1-inventoried")
            rows.append((path, kind, int(lines), layer, rnd, status))
    with out.open("w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["path", "kind", "lines", "layer", "round", "status"])
        w.writerows(rows)
    # summary
    totals: dict[str, int] = {}
    counts: dict[str, int] = {}
    for _, _, n, layer, _, _ in rows:
        totals[layer] = totals.get(layer, 0) + n
        counts[layer] = counts.get(layer, 0) + 1
    grand = sum(totals.values())
    print(f"files={len(rows)} total_lines={grand}")
    for layer in sorted(totals):
        print(f"{layer}\tfiles={counts[layer]}\tlines={totals[layer]}")


if __name__ == "__main__":
    main()
