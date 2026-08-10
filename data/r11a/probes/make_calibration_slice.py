#!/usr/bin/env python3
"""Select the R11A L3 calibration slice out of the `round=R6 && layer=L3` bucket.

Why sampling, and why the bucket splits in two first.
-----------------------------------------------------
The slice exists to measure one number — what a line (or a file) of L3
"知悉用途" work actually costs — so the 1,878-file / 584,490-line L3 backlog can
be scheduled. R10B produced the first L3 point (slice I) and its two
extrapolations disagreed by 4x, so representativeness is the whole game.

`skills_bucket_profile.py` says the bucket is not one population:

  * median file 156 lines, max 16,799;
  * lines/file across the 42 categories spans 1,195x;
  * **22 of the 316 skill directories hold 52.6% of the lines.**

And those 22 are not "同构短文档" at all. The four largest are
`optional-skills/mlops/training/unsloth` (29,016 lines in 5 files — 5,803
lines/file), two copies of the OOXML schema dump
`.../scripts/office/schemas/ISO-IEC29500-4_2016` (18,795 lines in 27 files
each), and `skills/creative/popular-web-designs/templates` (14,552 lines in 54
HTML templates). Few files, enormous lines, machine-generated — which is
precisely the shape R10B's slice I already measured.

So the bucket is TWO shapes, and mixing them is what would make a single
average meaningless:

  * **bulk-data tail** — skill dirs over the cap. Slice I is already a data
    point for this shape; R11A does not need a second one.
  * **短文档主体** — everything under the cap. This is the shape the round is
    asked to calibrate, and it has no data point at all.

The cap is set at CAP lines/skill on a stated principle rather than by tuning:
**no single skill directory may exceed ~10% of the slice target**, otherwise one
skill dominates the sample and the slice stops being a sample. At TARGET=17,500
that is ~1,750, rounded to 2,000.

Within the under-cap pool, allocation is proportional to lines across
categories, and the sampling unit is the **skill directory** (`SKILL.md` plus
its `references/`) — the unit a reader actually opens. Selection is
deterministic (path order, no RNG), so the slice is reproducible from this file.

    python3 data/r11a/probes/make_calibration_slice.py [--target 17500] [--write]
"""
import sys
from collections import defaultdict
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
LEDGER = STUDY / "data" / "ledger.tsv"
OUT = STUDY / "data" / "r11a" / "slices" / "slice-L3-calibration.tsv"

TARGET = 17500
CAP = 2000
for i, a in enumerate(sys.argv):
    if a == "--target" and i + 1 < len(sys.argv):
        TARGET = int(sys.argv[i + 1])
    if a == "--cap" and i + 1 < len(sys.argv):
        CAP = int(sys.argv[i + 1])
WRITE = "--write" in sys.argv


def rows():
    for i, raw in enumerate(LEDGER.read_text(encoding="utf-8").splitlines()):
        if i == 0:
            continue
        f = [c.rstrip("\r") for c in raw.split("\t")]
        if len(f) >= 6 and f[3] == "L3" and f[4] == "R6":
            yield f[0], int(f[2])


def skill_dir(path: str) -> str:
    parts = path.split("/")
    if "references" in parts:
        return "/".join(parts[:parts.index("references")])
    if len(parts) <= 2:
        return "/".join(parts[:-1]) or parts[0]
    return "/".join(parts[:-1])


def category(path: str) -> str:
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) > 1 else parts[0]


def main() -> None:
    data = list(rows())
    bucket_f, bucket_l = len(data), sum(n for _, n in data)

    skills = defaultdict(list)
    for p, n in data:
        skills[skill_dir(p)].append((p, n))
    sk_lines = {d: sum(n for _, n in v) for d, v in skills.items()}
    sk_files = {d: len(v) for d, v in skills.items()}

    over = {d for d, n in sk_lines.items() if n > CAP}
    pool = [d for d in skills if d not in over]
    pool_l = sum(sk_lines[d] for d in pool)
    pool_f = sum(sk_files[d] for d in pool)
    over_l = sum(sk_lines[d] for d in over)
    over_f = sum(sk_files[d] for d in over)

    print(f"bucket        : {bucket_f} files / {bucket_l} lines "
          f"({bucket_l / bucket_f:.1f} ln/file), {len(skills)} skill dirs")
    print(f"cap           : {CAP} lines/skill dir")
    print(f"  bulk-data tail (over cap) : {len(over):3d} skills  "
          f"{over_f:4d} files  {over_l:6d} lines  "
          f"({over_l / bucket_l:.1%} of bucket, {over_l / over_f:.0f} ln/file)")
    print(f"  短文档主体 (under cap)     : {len(pool):3d} skills  "
          f"{pool_f:4d} files  {pool_l:6d} lines  "
          f"({pool_l / bucket_l:.1%} of bucket, {pool_l / pool_f:.0f} ln/file)")
    print()

    by_cat = defaultdict(list)
    for d in pool:
        by_cat[category(d)].append(d)
    cat_l = defaultdict(int)
    for d in pool:
        cat_l[category(d)] += sk_lines[d]

    chosen, per_cat = [], {}
    for cat in sorted(by_cat):
        quota = cat_l[cat] / pool_l * TARGET
        got, picked = 0, []
        for d in sorted(by_cat[cat]):
            if got >= quota:
                break
            # Take the overshooting skill only when doing so lands closer to
            # quota than stopping short would. Never skip a skill for being
            # large: that is a size filter, and the cap is the only size filter
            # this design admits.
            if got and abs(got + sk_lines[d] - quota) > abs(got - quota):
                break
            picked.append(d)
            got += sk_lines[d]
        if picked:
            per_cat[cat] = (quota, got, len(picked))
            chosen.extend(picked)

    files = [(p, n) for d in chosen for p, n in sorted(skills[d])]
    tot_f, tot_l = len(files), sum(n for _, n in files)

    print(f"slice : {tot_f} files / {tot_l} lines "
          f"({tot_l / tot_f:.1f} ln/file) across {len(chosen)} skill dirs")
    print(f"        vs 短文档主体 {pool_l / pool_f:.1f} ln/file "
          f"-> {(tot_l / tot_f) / (pool_l / pool_f):.2f}x  (1.00 = representative)")
    print(f"        covers {tot_l / pool_l:.1%} of the 短文档主体 by lines, "
          f"{tot_f / pool_f:.1%} by files")
    print()
    print(f"{'category':40s} {'quota':>7s} {'got':>7s} {'skills':>6s}")
    for cat in sorted(per_cat):
        q, g, k = per_cat[cat]
        print(f"{cat:40s} {q:7.0f} {g:7d} {k:6d}")

    if WRITE:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8") as fh:
            fh.write("path\tlines\tskill_dir\n")
            for d in sorted(chosen):
                for p, n in sorted(skills[d]):
                    fh.write(f"{p}\t{n}\t{d}\n")
        print(f"\nwrote {OUT.relative_to(STUDY)}  ({tot_f} files / {tot_l} lines)")


if __name__ == "__main__":
    main()
