#!/usr/bin/env python3
"""Cut R11A into slices and write one manifest per slice.

Two populations this round, cut separately because they are different work:

  * **运维基建 L2** — `round=R11 && layer=L2`, 141 files / 43,365 lines. Split in
    two along a functional seam rather than by size alone, so each slice is a
    thing a chapter can describe: A = 装机与发布(how the product gets built,
    packaged and onto a machine), B = CI 与运行时容器(how it is tested in CI and
    supervised at runtime).
  * **L3 校准片** — selected by `make_calibration_slice.py`, which owns its own
    sampling rationale. Read here from the manifest that script writes.

Slice sizes are held inside the 17,544–22,551 lines/slice band that R10 and R10B
measured as one subagent's working capacity; that band, not a guess, is why
141 files becomes two slices and not three.

    python3 data/r11a/probes/make_slices.py [--write]
"""
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
LEDGER = STUDY / "data" / "ledger.tsv"
SLICES = STUDY / "data" / "r11a" / "slices"
WRITE = "--write" in sys.argv

# Slice A: everything that turns the source tree into an installed, running
# product — the installers, the release pipeline, the Nix packaging, and the
# generators whose output ships with a release.
A_EXACT = {
    "scripts/install.sh", "scripts/install.ps1", "scripts/install.cmd",
    "scripts/install_psutil_android.py",
    "scripts/release.py", "scripts/build_model_catalog.py",
    "scripts/build_skills_index.py", "scripts/generate_conformance_vectors.py",
    "scripts/hermes-gateway", "scripts/dev-sandbox.sh",
    "scripts/docker_rebootstrap_nous_session.py", "scripts/docker_config_migrate.py",
}
A_PREFIX = ("nix/", "scripts/lib/", "scripts/tests/")

# Slice B gets the rest: CI definitions, the container/supervision tree, the
# test-orchestration and diagnostic scripts, and the WhatsApp bridge.


def rows():
    for i, raw in enumerate(LEDGER.read_text(encoding="utf-8").splitlines()):
        if i == 0:
            continue
        f = [c.rstrip("\r") for c in raw.split("\t")]
        if len(f) >= 6 and f[3] == "L2" and f[4] == "R11":
            yield f[0], int(f[2])


def bucket(path: str) -> str:
    if path in A_EXACT or path.startswith(A_PREFIX):
        return "A"
    return "B"


def main() -> None:
    data = list(rows())
    groups = {"A": [], "B": []}
    for p, n in data:
        groups[bucket(p)].append((p, n))

    total_f = len(data)
    total_l = sum(n for _, n in data)
    print(f"运维基建 L2 total: {total_f} files / {total_l} lines")
    for k in ("A", "B"):
        g = sorted(groups[k])
        print(f"  slice {k}: {len(g):3d} files / {sum(n for _, n in g):6d} lines")

    # conservation: the split must lose nothing
    got_f = sum(len(v) for v in groups.values())
    got_l = sum(n for v in groups.values() for _, n in v)
    assert (got_f, got_l) == (total_f, total_l), "slice split lost files/lines"
    print(f"  conservation OK: {got_f} files / {got_l} lines")

    calib = SLICES / "slice-L3-calibration.tsv"
    if calib.is_file():
        cl = [ln.split("\t") for ln in
              calib.read_text(encoding="utf-8").splitlines()[1:]]
        print(f"  slice C (L3 校准): {len(cl)} files / "
              f"{sum(int(x[1]) for x in cl)} lines   [from make_calibration_slice.py]")

    if WRITE:
        SLICES.mkdir(parents=True, exist_ok=True)
        for k in ("A", "B"):
            out = SLICES / f"slice-L2-{k}.tsv"
            with out.open("w", encoding="utf-8") as fh:
                fh.write("path\tlines\n")
                for p, n in sorted(groups[k]):
                    fh.write(f"{p}\t{n}\n")
            print(f"wrote {out.relative_to(STUDY)}")


if __name__ == "__main__":
    main()
