#!/usr/bin/env python3
"""H-R10-a negative control: prove the widened gate actually BLOCKS.

A gate that starts recognising a new class of anchor is worthless if it
recognises them and then passes everything. This builds a throwaway fixture
whose anchors are deliberately wrong -- one per newly-allowed extension, in each
of the three failing shapes the gate has -- runs the real
`scripts/verify_citations.py` over it, and asserts the expected verdicts.

It also asserts the converse: `sqlite.org:443` and friends must NOT be picked up
as anchors, which is the trap H-R10-a warned about.

    python3 data/r10b/probes/cite_ext_negative_control.py [baseline_repo]

Exit 0 = gate behaved as specified. Exit 1 = gate is not enforcing what this
round claims it enforces.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
REPO = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")
GATE = STUDY / "scripts" / "verify_citations.py"

# (path, a line number that really exists, the verbatim text at that line)
def at(rel, n):
    src = (REPO / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    return src[n - 1]


def pick(rel, near):
    """A line at/after *near* that can actually testify to drift.

    The first draft hard-coded line numbers and drew a blank line out of
    nix/tui.nix; an empty excerpt block is recorded UNCHECKED, so that case
    proved nothing while looking like it did. Require a line that is non-blank,
    long enough not to collide by accident, and unique in the file.
    """
    src = (REPO / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    norm = [" ".join(x.split()) for x in src]
    for n in range(near, min(len(src), near + 200)):
        t = norm[n - 1]
        if len(t) >= 25 and norm.count(t) == 1:
            return n
    raise SystemExit(f"no usable fixture line in {rel} near {near}")


# rel path, a starting point to look near, how far to drift the anchor
CASES = [(rel, pick(rel, near), d) for rel, near, d in [
    ("native/fts5_cjk/vendor/sqlite3.h",            100,  7),
    ("ui-tui/scripts/build.mjs",                     20,  3),
    ("nix/tui.nix",                                  10,  4),
    ("apps/bootstrap-installer/src-tauri/build.rs",  30,  5),
    ("website/docs/index.mdx",                       40,  6),
]]

EXPECT = {}


def build(tmp: Path):
    out = ["# negative control fixture (generated; not a study artifact)", ""]

    # --- shape 1: fence anchored to the wrong line -> MISMATCH ---
    out.append("## fenced blocks, each anchored N lines off")
    out.append("")
    for rel, n, d in CASES:
        text = at(rel, n)
        out.append(f"`{rel}:{n + d} @ 863e313`")
        out.append("")
        out.append("```")
        out.append(text)
        out.append("```")
        out.append("")
        EXPECT[f"{rel}:{n + d}"] = "MISMATCH"

    # --- shape 2: table-row anchor with a declared inline excerpt, drifted ---
    out.append("## table rows with declared inline excerpts, drifted")
    out.append("")
    out.append("| item | anchor |")
    out.append("|---|---|")
    for rel, n, d in CASES:
        text = at(rel, n).strip().replace("|", r"\|").replace("`", "'")
        if len(text) < 8:
            continue
        out.append(f"| drift | `{rel}:{n + d}`:`{text}` |")
    out.append("")

    # --- shape 3: line number past EOF -> OUT-OF-RANGE ---
    out.append("## anchors past end of file")
    out.append("")
    for rel, n, _ in CASES[:2]:
        out.append(f"`{rel}:999999 @ 863e313`")
        out.append("")
        out.append("```")
        out.append(at(rel, n))
        out.append("```")
        out.append("")

    # --- converse: host:port must NOT be read as an anchor ---
    out.append("## host:port lookalikes -- must NOT be treated as anchors")
    out.append("")
    out.append("The build fetches from sqlite.org:443 and the mock listens on")
    out.append("127.0.0.1:18789; upstream is api.openai.com:443 and the hub is")
    out.append("homeassistant.local:8123. A bare example.rs:443 is a hostname too.")
    out.append("")

    p = tmp / "negctl.md"
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    return p


def main():
    if not REPO.is_dir():
        raise SystemExit(f"baseline repo not found: {REPO}")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fixture = build(tmp)
        r = subprocess.run(
            [sys.executable, str(GATE), str(REPO), str(fixture)],
            capture_output=True, text=True,
        )
        out = r.stdout
        print(out)
        print(f"--- gate exit code: {r.returncode} ---\n")

        fails = []

        def want(cond, msg):
            print(("  OK   " if cond else "  FAIL ") + msg)
            if not cond:
                fails.append(msg)

        want(r.returncode == 1, "gate exits 1 on the drifted fixture")
        for key in EXPECT:
            want(f"{key} ->" in out or f"{key} (" in out,
                 f"MISMATCH reported for {key}")
        want("TABLE-DRIFT" in out, "TABLE-DRIFT reported for drifted table anchors")
        want("OUT-OF-RANGE" in out, "OUT-OF-RANGE reported for past-EOF anchors")

        # the converse: none of the host:port strings may appear as a citation
        for host in ("sqlite.org:443", "127.0.0.1:18789", "api.openai.com:443",
                     "homeassistant.local:8123", "example.rs:443"):
            want(host not in out, f"{host} was NOT read as an anchor")

        # and the whole host:port paragraph must contribute zero citations
        m = re.search(r"citations=(\d+)", out)
        n_cites = int(m.group(1)) if m else -1
        want(n_cites == len(CASES) + 2,
             f"citations={n_cites} equals the {len(CASES)} drifted fences + 2 past-EOF "
             f"(no host:port leaked in)")

    if fails:
        print(f"\nNEGATIVE CONTROL FAILED: {len(fails)} expectation(s) not met")
        sys.exit(1)
    print("\nNEGATIVE CONTROL PASSED: the widened gate blocks what it claims to block")


if __name__ == "__main__":
    main()
