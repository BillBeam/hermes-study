#!/usr/bin/env python3
"""Shape of the `round=R6 && layer=L3` bucket, so the calibration slice can be
sampled on evidence instead of by eye.

R10B's handover (H-R10B-c) asks R11 to run a calibration slice before scheduling
the L3 backlog, because its own two extrapolations from slice I disagreed by 4x
(by-line said ~34 slices, by-file ~144). A calibration slice only settles that
if it is representative on whatever axis actually drives cost — so first measure
what the bucket looks like.

    python3 data/r11a/probes/skills_bucket_profile.py
"""
import statistics
import sys
from collections import defaultdict
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
LEDGER = STUDY / "data" / "ledger.tsv"


def rows():
    for i, raw in enumerate(LEDGER.read_text(encoding="utf-8").splitlines()):
        if i == 0:
            continue
        f = [c.rstrip("\r") for c in raw.split("\t")]
        if len(f) >= 6 and f[3] == "L3" and f[4] == "R6":
            yield f[0], int(f[2])


def skill_dir(path: str) -> str:
    """The directory that holds a SKILL.md — the unit a reader actually reads.

    `skills/mlops/evaluation/evaluating-llms-harness/references/api-evaluation.md`
    belongs to `skills/mlops/evaluation/evaluating-llms-harness`.
    """
    parts = path.split("/")
    if "references" in parts:
        return "/".join(parts[:parts.index("references")])
    if len(parts) <= 2:
        return "/".join(parts[:-1]) or parts[0]
    return "/".join(parts[:-1])


def main() -> None:
    data = list(rows())
    total_f = len(data)
    total_l = sum(n for _, n in data)
    print(f"bucket: {total_f} files / {total_l} lines "
          f"({total_l / total_f:.1f} lines/file)")
    print()

    sizes = sorted(n for _, n in data)
    print("per-file line distribution:")
    for q in (10, 25, 50, 75, 90, 99):
        print(f"  p{q:<3}= {statistics.quantiles(sizes, n=100)[q - 1]:8.0f}")
    print(f"  max = {sizes[-1]:8d}   min = {sizes[0]:8d}")
    print()

    # by top-level tree x category
    cat = defaultdict(lambda: [0, 0])
    for p, n in data:
        parts = p.split("/")
        k = "/".join(parts[:2]) if len(parts) > 1 else parts[0]
        cat[k][0] += 1
        cat[k][1] += n
    print(f"categories: {len(cat)}")
    print(f"{'category':45s} {'files':>6s} {'lines':>8s} {'ln/file':>8s}")
    for k, (f, l) in sorted(cat.items(), key=lambda kv: -kv[1][1]):
        print(f"{k:45s} {f:6d} {l:8d} {l / f:8.1f}")
    print()

    ratios = [l / f for f, l in cat.values()]
    print(f"lines/file across categories: min {min(ratios):.0f}  "
          f"median {statistics.median(ratios):.0f}  max {max(ratios):.0f}  "
          f"-> spread {max(ratios) / min(ratios):.1f}x")
    print()

    sk = defaultdict(lambda: [0, 0])
    for p, n in data:
        d = skill_dir(p)
        sk[d][0] += 1
        sk[d][1] += n
    print(f"skill directories (the unit a reader reads): {len(sk)}")
    fs = sorted(v[0] for v in sk.values())
    ls = sorted(v[1] for v in sk.values())
    print(f"  files per skill : median {statistics.median(fs):.0f}  "
          f"max {fs[-1]}")
    print(f"  lines per skill : median {statistics.median(ls):.0f}  "
          f"max {ls[-1]}")


if __name__ == "__main__":
    main()
