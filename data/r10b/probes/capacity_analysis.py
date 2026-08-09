#!/usr/bin/env python3
"""L2 vs L3 unit cost, from the per-slice cost ledger this round collected.

R11B has 787 files / 263,763 lines of L3 waiting to be scheduled and, before
R10B, ZERO L3 data points existed — R10 said so explicitly and declined to
extrapolate. Slice I is that data point. This script does the arithmetic in one
rerunnable place so the report cannot quietly round it.

Three cost axes, because they disagree and the disagreement is the finding:
  tokens    — how much model work the slice took
  tool_uses — how many discrete look-ups
  duration  — wall clock (contaminated: 11 slices ran concurrently on one box,
              so this is elapsed-under-contention, not isolated cost)

    python3 data/r10b/probes/capacity_analysis.py
"""
import csv
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[1] / "measurements" / "slice-cost.tsv"


def main() -> None:
    rows = list(csv.DictReader(LEDGER.open(encoding="utf-8"), delimiter="\t"))
    for r in rows:
        for k in ("files", "lines", "subagent_tokens", "tool_uses", "duration_ms"):
            r[k] = int(r[k])

    l2 = [r for r in rows if r["layer"] == "L2"]
    l3 = [r for r in rows if r["layer"] == "L3"]

    print(f"{'slice':>5} {'L':>3} {'files':>6} {'lines':>7} {'tokens':>8} "
          f"{'tok/line':>9} {'tools':>6} {'min':>6}")
    for r in sorted(rows, key=lambda x: x["slice"]):
        print(f"{r['slice']:>5} {r['layer']:>3} {r['files']:6d} {r['lines']:7d} "
              f"{r['subagent_tokens']:8d} {r['subagent_tokens'] / r['lines']:9.2f} "
              f"{r['tool_uses']:6d} {r['duration_ms'] / 60000:6.1f}")

    def agg(name, group):
        if not group:
            return None
        n = len(group)
        tok = sum(r["subagent_tokens"] for r in group)
        ln = sum(r["lines"] for r in group)
        fl = sum(r["files"] for r in group)
        tu = sum(r["tool_uses"] for r in group)
        du = sum(r["duration_ms"] for r in group)
        print(f"\n{name}  n={n}  files={fl}  lines={ln}")
        print(f"  mean tokens/slice : {tok // n:,}")
        print(f"  mean tokens/line  : {tok / ln:.2f}")
        print(f"  mean tools/slice  : {tu / n:.1f}")
        print(f"  mean minutes/slice: {du / n / 60000:.1f}")
        return {"tok_slice": tok / n, "tok_line": tok / ln,
                "tools": tu / n, "min": du / n / 60000}

    a2 = agg("L2", l2)
    a3 = agg("L3", l3)
    if a2 and a3:
        print("\nL3 as a fraction of L2 (the number R11B needs):")
        for k, label in (("tok_slice", "tokens per slice"), ("tok_line", "tokens per LINE"),
                         ("tools", "tool calls per slice"), ("min", "wall-clock per slice")):
            print(f"  {label:<22} {a3[k] / a2[k]:5.0%}")
        print("\n  NOTE wall-clock is contaminated: all slices ran concurrently on one")
        print("  machine, so elapsed time reflects contention, not isolated cost.")
        print("  tokens and tool_uses are per-agent and are not.")

    if l3:
        l3_backlog()
        r = l3[0]
        print("\nExtrapolating slice I onto the WHOLE remaining L3 backlog:")
        by_line = 584490 / r["lines"]
        by_file = 1878 / r["files"]
        print(f"  scaled by LINES : {by_line:5.1f} x slice I  -> ~{by_line:.0f} slices")
        print(f"  scaled by FILES : {by_file:5.1f} x slice I  -> ~{by_file:.0f} slices")
        print(f"  the two disagree by {max(by_line, by_file) / min(by_line, by_file):.0f}x.")
        print("  NEITHER is usable — see the shape table above: slice I is 13 files of")
        print("  which 5 are huge data tables and whose chain left the slice entirely,")
        print("  while both backlog buckets are ~1,000 small homogeneous documents.")
        print("  Recommendation in the report: R11 runs a CALIBRATION slice, not a forecast.")


def l3_backlog() -> None:
    """Profile the L3 layer by planned round. R10 (and R9A/R8D before it) quoted
    787 files / 263,763 lines as 'the' L3 backlog; that is the `round=R11`
    bucket only. A second, larger bucket sits under `round=R6` and has been
    R1-inventoried since R6 -- the same planned-but-never-read hole R8D found on
    the L1 side, still open on the L3 side."""
    import collections
    import statistics
    led = Path(__file__).resolve().parents[2] / "ledger.tsv"
    rows = list(csv.DictReader(led.open(newline="", encoding="utf-8"), delimiter="\t"))
    l3 = [r for r in rows if r["layer"].strip() == "L3"]
    print("\nL3 layer by planned round (status shown; shape decides the unit):")
    print(f"  {'round':>6} {'files':>6} {'lines':>8} {'median':>7} {'max':>7}  status / top dir")
    for rnd in sorted({r["round"].strip() for r in l3}):
        g = [r for r in l3 if r["round"].strip() == rnd]
        ln = [int(r["lines"]) for r in g]
        st = collections.Counter(r["status"].strip() for r in g)
        top = collections.Counter("/".join(r["path"].split("/")[:2]) for r in g).most_common(1)[0][0]
        print(f"  {rnd:>6} {len(g):6d} {sum(ln):8d} {statistics.median(ln):7.0f} {max(ln):7d}"
              f"  {dict(st)} {top}")
    rem = [r for r in l3 if r["status"].strip() == "R1-inventoried"]
    done = [r for r in l3 if r["round"].strip() == "R10"]
    nf = len(rem) - len(done)
    nl = sum(int(r["lines"]) for r in rem) - sum(int(r["lines"]) for r in done)
    print(f"\n  L3 still R1-inventoried once R10B lands: {nf} files / {nl} lines")
    print(f"  R10's quoted backlog (787 / 263,763) is {263763 / nl:.0%} of it.")


if __name__ == "__main__":
    main()
