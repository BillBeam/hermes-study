#!/usr/bin/env python3
"""H-R10B-a negative control: prove the gate BLOCKS on extensionless anchors.

Teaching the gate to *recognise* `.gitignore:3` is worth nothing if it then
passes everything it recognises. R10B made the same point about its own
widening and built the same kind of fixture; this is the extensionless
counterpart.

The fixture deliberately writes wrong anchors — one per failing shape the gate
has — runs the real `scripts/verify_citations.py` over it, and asserts the
verdicts. It also asserts the converse, which is the trap H-R10B-a named:
`base:645`, `run:12` and `notbase:5` must NOT be picked up, because
extensionless names collide with ordinary English far more readily than dotted
ones do.

The `citations=` **total** is asserted, not just the failure lines. R10B found
this to be the assertion that matters: a swallowed string can be recorded
UNCHECKED, which produces no failure text at all — only the total moves.

    python3 data/r11a/probes/extless_negative_control.py [baseline_repo]

Exit 0 = the gate enforces what R11A claims it enforces. Exit 1 = it does not.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
REPO = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")
GATE = STUDY / "scripts" / "verify_citations.py"


def lines_of(rel):
    return (REPO / rel).read_text(encoding="utf-8", errors="replace").splitlines()


def pick(rel, near, *, table_safe=False):
    """A line at/after *near* that can actually testify to drift.

    R10B's first draft of its own control drew a *blank* line out of a fixture
    file; an empty excerpt block is recorded UNCHECKED, so that case proved
    nothing while looking like it proved something. So require a line that is
    non-blank, long enough not to collide by accident, and unique in the file.

    `table_safe` additionally excludes backticks and pipes (they would break the
    Markdown cell the excerpt is embedded in) and requires the `CODEISH` shape
    `cell_tokens()` demands of a table excerpt.
    """
    src = lines_of(rel)
    norm = [" ".join(x.split()) for x in src]
    for n in range(near, min(len(src), near + 200)):
        t = norm[n - 1]
        if len(t) < 25 or norm.count(t) != 1:
            continue
        if table_safe and ("`" in t or "|" in t or not re.search(r"[_/(){}\[\]=<>.\"'|:-]|[A-Z]", t)):
            continue
        return n
    raise SystemExit(f"no usable fixture line in {rel} near {near}")


# (label, rel path, anchor-drift distance) — fence cases.
FENCE_CASES = [
    ("bare dotfile at repo root", ".gitignore", 30, 6),
    ("bare buildfile at repo root", "Dockerfile", 60, 5),
    ("nested, name is an English word", "docker/s6-rc.d/main-hermes/run", 5, 4),
    ("nested, numeric-prefixed name", "docker/cont-init.d/015-supervise-perms", 20, 7),
]

# Table cases: (label, rel, near, drift) — excerpt declared inline after anchor.
TABLE_CASES = [
    ("table row, nested Makefile",
     "skills/research/research-paper-writing/templates/neurips2025/Makefile", 5, 3),
    ("table row, bare dotfile", ".dockerignore", 20, 4),
]

# Strings that must NOT become anchors. Each is `token:digits` shaped and each
# names something real in prose terms, which is exactly why they are dangerous.
NON_ANCHORS = [
    "base:645",        # the real one: reports/round-5 shorthand for a base.py line
    "run:12",          # `run` IS a file at 863e313 — but only under docker/s6-rc.d/
    "type:3",          # ditto
    "notbase:5",       # suffix collision the lookbehind must reject
    "sqlite.org:443",  # the host:port trap H-R10-a named, re-asserted here
    "127.0.0.1:18789",
]


def drift_to_content(rel, n, d):
    """Shift *d* until `n+d` lands on a non-blank line of *rel*.

    A drifted anchor that happens to point at a blank line is a weaker test than
    it looks: CLAUDE.md's own account of BLOCK-DRIFT stresses that the dangerous
    shape is an anchor whose real target is "一条普通语句" — an ordinary
    statement — not something visibly degenerate. Keep the fixture on that
    shape so a pass means what it appears to mean.
    """
    src = lines_of(rel)
    for k in range(d, d + 40):
        if n + k <= len(src) and src[n + k - 1].strip():
            return k
    raise SystemExit(f"no non-blank drift target in {rel} near {n + d}")


def build(tmp: Path) -> tuple[Path, int]:
    """Write the fixture; return its path and the number of anchors it should
    make the gate count."""
    out = ["# extensionless negative control fixture", ""]
    expected = 0

    # 1. positive control — a CORRECT anchor must come back OK, otherwise a
    #    fixture that is simply malformed would look like a working gate.
    rel, n = ".gitignore", pick(".gitignore", 10)
    out += [f"positive control", "", f"`{rel}:{n}`", "", "```", lines_of(rel)[n - 1], "```", ""]
    expected += 1

    # 2. drifted fence anchors -> MISMATCH
    for label, rel, near, d in FENCE_CASES:
        n = pick(rel, near)
        d = drift_to_content(rel, n, d)
        out += [f"{label}", "", f"`{rel}:{n + d}`", "", "```", lines_of(rel)[n - 1], "```", ""]
        expected += 1

    # 3. out-of-range fence anchor -> OUT-OF-RANGE
    rel = "docker/s6-rc.d/main-hermes/run"
    big = len(lines_of(rel)) + 500
    out += ["fence, past EOF", "", f"`{rel}:{big}`", "", "```", lines_of(rel)[3], "```", ""]
    expected += 1

    # 4. table rows -> TABLE-DRIFT / TABLE-OUT-OF-RANGE (counted separately)
    out += ["| 项 | 锚点 | 说明 |", "|---|---|---|"]
    for label, rel, near, d in TABLE_CASES:
        n = pick(rel, near, table_safe=True)
        d = drift_to_content(rel, n, d)
        txt = " ".join(lines_of(rel)[n - 1].split())
        out += [f"| {label} | `{rel}:{n + d}`:`{txt}` | drifted |"]
    rel, near = "skills/research/research-paper-writing/templates/neurips2025/Makefile", 5
    n = pick(rel, near, table_safe=True)
    txt = " ".join(lines_of(rel)[n - 1].split())
    oor = len(lines_of(rel)) + 500
    out += [f"| table, past EOF | `{rel}:{oor}`:`{txt}` | out of range |", ""]

    # 5. the must-not-be-swallowed strings, in prose
    out += ["非锚点串:" + "、".join(NON_ANCHORS), ""]

    p = tmp / "extless_fixture.md"
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    return p, expected


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fixture, expected_citations = build(tmp)
        proc = subprocess.run(
            [sys.executable, str(GATE), str(REPO), str(fixture)],
            capture_output=True, text=True,
        )
        report = proc.stdout + proc.stderr
        print(report)

        failures = []

        def check(cond, msg):
            print(("  ok   " if cond else "  FAIL ") + msg)
            if not cond:
                failures.append(msg)

        print("=== assertions ===")

        # -- the newly recognised anchors must actually FAIL, not just count --
        mism = len(re.findall(r"^\[MISMATCH\]", report, re.M))
        check(mism == len(FENCE_CASES),
              f"MISMATCH on every drifted extensionless fence anchor "
              f"(expect {len(FENCE_CASES)}, got {mism})")

        oor = len(re.findall(r"^\[OUT-OF-RANGE\]", report, re.M))
        check(oor == 1, f"OUT-OF-RANGE on the past-EOF fence anchor (expect 1, got {oor})")

        m = re.search(r"^table_anchors=(\d+)\s+(.*)$", report, re.M)
        tbl = dict(re.findall(r"([A-Z-]+)=(\d+)", m.group(2))) if m else {}
        check(tbl.get("DRIFT") == "2",
              f"TABLE-DRIFT on both drifted table anchors (expect 2, got {tbl.get('DRIFT')})")
        check(tbl.get("OUT-OF-RANGE") == "1",
              f"TABLE-OUT-OF-RANGE on the past-EOF table anchor "
              f"(expect 1, got {tbl.get('OUT-OF-RANGE')})")

        # -- the positive control must pass, or the fixture proves nothing --
        cm = re.search(r"^citations=(\d+)\s+(.*)$", report, re.M)
        counts = dict(re.findall(r"([A-Z-]+)=(\d+)", cm.group(2))) if cm else {}
        check(counts.get("OK") == "1",
              f"positive control counted OK (expect 1, got {counts.get('OK')})")

        # -- and nothing may be swallowed --
        # This is the assertion that catches the silent failure: a swallowed
        # string usually lands in UNCHECKED, which prints no failure line at
        # all. Only the TOTAL moves, so assert the total.
        total = int(cm.group(1)) if cm else -1
        check(total == expected_citations,
              f"citations total is exactly the {expected_citations} planted "
              f"anchors — no prose swallowed (got {total})")

        for s in NON_ANCHORS:
            check(s not in report,
                  f"not swallowed as an anchor: {s}")

        check(proc.returncode != 0, "gate exits non-zero on the fixture")

        print()
        if failures:
            print(f"NEGATIVE CONTROL FAILED: {len(failures)} assertion(s)")
            sys.exit(1)
        print("NEGATIVE CONTROL PASSED: the gate blocks extensionless drift "
              "and swallows nothing.")


if __name__ == "__main__":
    main()
