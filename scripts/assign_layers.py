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
    ("toolset_distributions.py", "L1", "R3"),
    ("hermes_state.py", "L1", "R5"),
    ("hermes_state_schema.py", "L1", "R5"),
    ("hermes_state_common.py", "L1", "R5"),
    ("hermes_state_search.py", "L1", "R6"),
    ("hermes_state_portability.py", "L1", "R5"),
    ("trajectory_compressor.py", "L1", "R9"),
    ("batch_runner.py", "L1", "R9"),
    ("mini_swe_runner.py", "L1", "R9"),
    ("hermes_constants.py", "L1", "R2"),
    ("agent/*.py", "L1", "R2-R6"),          # per-round split in round plans
    ("agent/**/*.py", "L1", "R2-R6"),
    ("tools/registry.py", "L1", "R3"),
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
    rows = []
    with inv.open() as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            path, kind, lines, nbytes = line.rstrip("\n").split("\t")
            layer, rnd = assign(path)
            if kind == "binary" and layer not in ("L4",):
                layer, rnd = "L4", "-"   # binaries are never study targets
            rows.append((path, kind, int(lines), layer, rnd, "R1-inventoried"))
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
