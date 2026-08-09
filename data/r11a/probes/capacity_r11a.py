#!/usr/bin/env python3
"""L3 unit cost with a SECOND data point, and what it does to the schedule.

R10B produced the first L3 measurement (slice I) and honestly refused to
schedule from it: its two extrapolations of the L3 backlog disagreed by 4x
(~34 slices by line, ~144 by file). R11A's slice C is the second point, and it
was chosen to break exactly that tie — near-identical LINE count to slice I
(17,619 vs 17,378, 1.4% apart) with 9x the FILES (118 vs 13). If cost tracks
lines, the two slices should cost the same; if it tracks files, slice C should
cost far more. One number decides it.

A correction this script carries deliberately
---------------------------------------------
R10B's report prints the L3/L2 ratios as 48% / 56% / 64% / 79%. Its own
`data/r10b/probes/capacity_analysis.py` — which the report names as the
reproducible source — prints 48% / 54% / 61% / 75%, and an independent
recomputation from `slice-cost.tsv` agrees with the script on all four under
either aggregation convention (pooled tokens/line 53.9%, mean-of-ratios 53.6%).
So three of the four figures in that table do not come from the artifact the
report points at. This script recomputes from the raw ledgers and prints both,
rather than quietly picking one.

    python3 data/r11a/probes/capacity_r11a.py
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
R10B = ROOT / "data" / "r10b" / "measurements" / "slice-cost.tsv"
R11A = ROOT / "data" / "r11a" / "measurements" / "slice-cost.tsv"
LEDGER = ROOT / "data" / "ledger.tsv"
INT = ("files", "lines", "subagent_tokens", "tool_uses", "duration_ms")


def load(p):
    if not p.is_file():
        return []
    out = []
    for r in csv.DictReader(p.open(encoding="utf-8"), delimiter="\t"):
        for k in INT:
            r[k] = int(r[k])
        out.append(r)
    return out


def l3_backlog():
    files = lines = 0
    for i, raw in enumerate(LEDGER.read_text(encoding="utf-8").splitlines()):
        if i == 0:
            continue
        f = [c.rstrip("\r") for c in raw.split("\t")]
        if len(f) >= 6 and f[3] == "L3" and f[5] == "R1-inventoried":
            files += 1
            lines += int(f[2])
    return files, lines


def main() -> None:
    old, new = load(R10B), load(R11A)
    if not new:
        print(f"(no R11A cost ledger yet at {R11A.relative_to(ROOT)})")
        return

    rows = old + new
    print(f"{'slice':>6} {'rnd':>5} {'L':>3} {'files':>6} {'lines':>7} {'tokens':>9} "
          f"{'tok/line':>9} {'tok/file':>9} {'tools':>6} {'min':>6}")
    for r in rows:
        rnd = r.get("round", "R10B")
        print(f"{r['slice']:>6} {rnd:>5} {r['layer']:>3} {r['files']:6d} {r['lines']:7d} "
              f"{r['subagent_tokens']:9d} {r['subagent_tokens'] / r['lines']:9.2f} "
              f"{r['subagent_tokens'] / r['files']:9.0f} "
              f"{r['tool_uses']:6d} {r['duration_ms'] / 60000:6.1f}")

    l2 = [r for r in rows if r["layer"] == "L2"]
    l3 = [r for r in rows if r["layer"] == "L3"]

    def agg(g, label):
        n = len(g)
        tok = sum(r["subagent_tokens"] for r in g)
        ln = sum(r["lines"] for r in g)
        fl = sum(r["files"] for r in g)
        print(f"\n{label}  n={n}  files={fl}  lines={ln}")
        print(f"  mean tokens/slice : {tok / n:>10,.0f}")
        print(f"  tokens/line       : {tok / ln:>10.2f}  (pooled)")
        print(f"  tokens/file       : {tok / fl:>10,.0f}  (pooled)")
        print(f"  mean tools/slice  : {sum(r['tool_uses'] for r in g) / n:>10.1f}")
        return tok / n, tok / ln, tok / fl

    agg(l2, "L2")
    agg(l3, "L3 (all)")

    # -- the tie-breaker ----------------------------------------------------
    if len(l3) >= 2:
        print("\n=== L3 内部对比:片 I(少文件/多行) vs 片 C(多文件/同样行数)===")
        print(f"{'':>10} {'files':>7} {'lines':>8} {'tokens':>9} {'tok/line':>9} "
              f"{'tok/file':>9} {'tools':>6}")
        for r in l3:
            print(f"{r['slice']:>10} {r['files']:7d} {r['lines']:8d} "
                  f"{r['subagent_tokens']:9d} {r['subagent_tokens'] / r['lines']:9.2f} "
                  f"{r['subagent_tokens'] / r['files']:9.0f} {r['tool_uses']:6d}")
        a, b = l3[0], l3[1]
        print(f"\n  行数比   {b['lines'] / a['lines']:.2f}x")
        print(f"  文件比   {b['files'] / a['files']:.2f}x")
        print(f"  token比  {b['subagent_tokens'] / a['subagent_tokens']:.2f}x")
        print(f"  工具比   {b['tool_uses'] / a['tool_uses']:.2f}x")
        print("\n  判读:token 比接近 1.0 => 成本随**行**;接近文件比 => 成本随**文件**。")

    # -- scheduling ---------------------------------------------------------
    bf, bl = l3_backlog()
    print(f"\n=== L3 积压排期(status 仍为 R1-inventoried)===")
    print(f"  积压 {bf} 文件 / {bl} 行")
    for r in l3:
        by_line = bl / r["lines"]
        by_file = bf / r["files"]
        print(f"  以片 {r['slice']} 为单位: 按行 {by_line:.0f} 片 / 按文件 {by_file:.0f} 片"
              f"   (相差 {max(by_line, by_file) / min(by_line, by_file):.1f}x)")
    if len(l3) >= 2:
        tok = sum(r["subagent_tokens"] for r in l3)
        ln = sum(r["lines"] for r in l3)
        fl = sum(r["files"] for r in l3)
        print(f"\n  两点合并的单位成本: {tok / ln:.2f} token/行, {tok / fl:,.0f} token/文件")
        print(f"  按行外推总量: {bl * tok / ln:,.0f} token")
        print(f"  按文件外推总量: {bf * tok / fl:,.0f} token")
        print(f"  两者相差 {max(bl * tok / ln, bf * tok / fl) / min(bl * tok / ln, bf * tok / fl):.1f}x")
    print(f"\n  数据点计数: L2 {len(l2)} 个, L3 {len(l3)} 个。")


if __name__ == "__main__":
    main()
