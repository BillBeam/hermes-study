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
    ("toolset_distributions.py", "L1", "R9"),
    ("hermes_state.py", "L1", "R5"),
    ("hermes_state_schema.py", "L1", "R5"),
    ("hermes_state_common.py", "L1", "R5"),
    ("hermes_state_search.py", "L1", "R6"),
    ("hermes_state_portability.py", "L1", "R5"),
    ("trajectory_compressor.py", "L1", "R9"),
    ("batch_runner.py", "L1", "R9"),
    ("mini_swe_runner.py", "L1", "R9"),
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
    ("agent/moa_loop.py", "L1", "R9"),
    ("agent/moa_trace.py", "L1", "R9"),
    ("agent/subagent_lifecycle.py", "L1", "R9"),
    ("agent/delegation_context.py", "L1", "R9"),
    # R3 机制簇涉及的 agent/ 文件(工具护栏、结果分类、子进程 secret 卫生)
    ("agent/tool_guardrails.py", "L1", "R3"),
    ("agent/tool_result_classification.py", "L1", "R3"),
    ("agent/secret_scope.py", "L1", "R3"),
    ("agent/redact.py", "L1", "R3"),
    ("agent/*.py", "L1", "R3-R7"),          # 其余 agent/ 文件在后续轮次开工时显式定轮
    ("agent/**/*.py", "L1", "R3-R7"),
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
    ("tools/environments/**", "L1", "R4"),
    ("tools/*.py", "L1", "R3-R4"),
    ("tools/**/*.py", "L1", "R3-R4"),
    ("cron/**/*.py", "L1", "R7"),
    ("gateway/*.py", "L1", "R7"),
    ("gateway/platforms/base.py", "L1", "R7"),

    # ---- L2: structure-level ----
    ("cli.py", "L2", "R8"),
    ("mcp_serve.py", "L2", "R8"),
    ("hermes_bootstrap.py", "L2", "R8"),
    ("hermes_logging.py", "L2", "R8"),
    ("hermes_time.py", "L2", "R8"),
    ("utils.py", "L2", "R8"),
    ("hermes_cli/**", "L2", "R8"),
    ("gateway/**", "L2", "R7"),             # platform adapters + assets
    ("plugins/model-providers/**", "L2", "R2"),   # provider 插件注册面,随 R2 结构级学习
    ("plugins/**", "L2", "R6"),
    ("tui_gateway/**", "L2", "R10"),
    ("acp_adapter/**", "L2", "R10"),
    ("ui-tui/**", "L2", "R10"),
    ("apps/desktop/src/i18n/*", "L3", "R10"),   # translation data, not structure
    ("apps/**", "L2", "R10"),
    ("web/**", "L2", "R10"),
    ("native/**", "L2", "R10"),
    ("providers/**", "L2", "R2"),
    ("scripts/**", "L2", "R11"),
    ("docker/**", "L2", "R11"),
    ("nix/**", "L2", "R11"),
    (".github/**", "L2", "R11"),
    ("cron/**", "L2", "R7"),

    # ---- L3: cataloged content ----
    ("skills/**", "L3", "R6"),
    ("optional-skills/**", "L3", "R6"),
    ("optional-mcps/**", "L3", "R6"),
    ("locales/**", "L3", "R11"),
    ("datagen-config-examples/**", "L3", "R9"),
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
