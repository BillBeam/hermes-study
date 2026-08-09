#!/usr/bin/env python3
"""Form ledger for the R11A slice-C (L3) manifest — the 形态账 behind L3-2.

Buckets the 118 slice files by **form** (what shape of artifact it is, and
therefore who reads it), not by category or by tree. Rules are first-match,
top to bottom, so the ordering below is the definition:

    schema      .xsd                                  (OOXML schema dump)
    index-cache skills/index-cache/*.json             (docs-site legacy cache)
    manifest    basename == manifest.yaml             (optional-mcps entries)
    skill       basename == SKILL.md                  (the indexed root doc)
    category    basename == DESCRIPTION.md            (category blurb)
    reference   */references/*                        (progressive disclosure)
    template    */templates/* or */prompts/* or */assets/*
    script      */scripts/*
    license     LICENSE*                              (vendored license text)
    other       anything else -> printed loudly, the bucket list is wrong

Prints per-form file/line counts plus the same counts for the whole
`skills/` + `optional-skills/` + `optional-mcps/` trees in the baseline, so the
slice can be read against its population.

    python3 data/r11a/probes/probe_c_form_ledger.py [--baseline /home/user/hermes-agent]
"""
import subprocess
import sys
from collections import Counter
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
SLICE = STUDY / "data" / "r11a" / "slices" / "slice-L3-calibration.tsv"
BASE = Path("/home/user/hermes-agent")
for i, a in enumerate(sys.argv):
    if a == "--baseline" and i + 1 < len(sys.argv):
        BASE = Path(sys.argv[i + 1])

FORMS = ["schema", "index-cache", "manifest", "skill", "category",
         "reference", "template", "script", "license", "other"]


def form_of(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    if path.endswith(".xsd"):
        return "schema"
    if path.startswith("skills/index-cache/"):
        return "index-cache"
    if name == "manifest.yaml":
        return "manifest"
    if name == "SKILL.md":
        return "skill"
    if name == "DESCRIPTION.md":
        return "category"
    if "/references/" in path:
        return "reference"
    if "/templates/" in path or "/prompts/" in path or "/assets/" in path:
        return "template"
    if "/scripts/" in path:
        return "script"
    if name.startswith("LICENSE"):
        return "license"
    return "other"


def count_lines(p: Path) -> int:
    """Line count = number of \\n-terminated records, matching scripts/inventory.py."""
    try:
        data = p.read_bytes()
    except OSError:
        return 0
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def main() -> None:
    rows = [r.split("\t") for r in
            SLICE.read_text(encoding="utf-8").splitlines()[1:]]
    f_files, f_lines = Counter(), Counter()
    for path, lines, _sd in rows:
        f = form_of(path)
        f_files[f] += 1
        f_lines[f] += int(lines)

    print("== slice C (118 files) by form ==")
    print(f"{'form':12s} {'files':>6s} {'lines':>8s}  {'ln/file':>8s}")
    for f in FORMS:
        if f_files[f]:
            print(f"{f:12s} {f_files[f]:6d} {f_lines[f]:8d}  "
                  f"{f_lines[f] / f_files[f]:8.1f}")
    print(f"{'TOTAL':12s} {sum(f_files.values()):6d} {sum(f_lines.values()):8d}")
    if f_files["other"]:
        print("\n!! unbucketed files (fix FORMS):")
        for path, _l, _s in rows:
            if form_of(path) == "other":
                print("   ", path)

    print("\n== baseline population (skills/ + optional-skills/ + optional-mcps/) ==")
    out = subprocess.run(
        ["git", "ls-files", "skills", "optional-skills", "optional-mcps"],
        cwd=BASE, capture_output=True, text=True, check=True).stdout
    p_files, p_lines = Counter(), Counter()
    for path in out.splitlines():
        f = form_of(path)
        p_files[f] += 1
        p_lines[f] += count_lines(BASE / path)
    print(f"{'form':12s} {'files':>6s} {'lines':>8s}  {'slice/pop files':>16s}")
    for f in FORMS:
        if p_files[f]:
            frac = f_files[f] / p_files[f] if p_files[f] else 0
            print(f"{f:12s} {p_files[f]:6d} {p_lines[f]:8d}  {frac:15.1%}")
    print(f"{'TOTAL':12s} {sum(p_files.values()):6d} {sum(p_lines.values()):8d}  "
          f"{sum(f_files.values()) / sum(p_files.values()):15.1%}")


if __name__ == "__main__":
    main()
