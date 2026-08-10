#!/usr/bin/env python3
"""Why 26 corpus occurrences become +20 on the gate's counters.

Two different things get called "how many extensionless anchors are there":

  * the census counts **occurrences of the token** in the corpus text (26);
  * the gate counts **citations it adjudicates** (+19 prose, +1 table = 20).

CLAUDE.md forbids reporting two different measurements of one quantity as
though they agreed, so the gap has to be explained by a command rather than by
a plausible story. Two documented gate behaviours should account for all of it:

  1. citations inside a ``` fence or a `>` quote are deliberately not scanned —
     there they are an excerpt's own text, not this note asserting something;
  2. one prose line yields one verdict, so several anchors on a line collapse;
  3. and — the term the first draft of this probe missed, which is why it
     predicted +21 against an observed +19 — a line that ALREADY carried a
     dotted anchor was already producing a verdict. Adding an extensionless
     anchor to such a line changes which anchor is adjudicated, not how many
     verdicts exist. Only lines whose *sole* anchors are extensionless raise
     the count.

    python3 data/r11a/probes/extless_delta_reconcile.py [baseline_repo]
"""
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
_pos = [a for a in sys.argv[1:] if not a.startswith("-")]
REPO = Path(_pos[0] if _pos else "/home/user/hermes-agent")
sys.path.insert(0, str(STUDY / "scripts"))
from verify_citations import (  # noqa: E402
    CITE, CITE_EXTLESS, FENCE, QUOTE, is_extless_citation, is_path_citation,
    is_table_row,
)

PREFIXES = ("r11a-", "round-11a-")
RAW = "--no-exclude" in sys.argv


def resolve(p):
    t = REPO / p
    if not t.is_file() and (STUDY / p).is_file():
        t = STUDY / p
    return t


def main() -> None:
    in_fence = in_quote = 0
    prose_occ = 0
    prose_lines = set()
    shared_lines = set()  # prose lines that ALREADY carried a dotted anchor
    table_occ = 0
    table_lines = set()

    for d in ("chapters", "notes", "reports", "reviews"):
        for f in sorted((STUDY / d).glob("*.md")):
            if not RAW and f.name.startswith(PREFIXES):
                continue
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            fence = False
            for k, line in enumerate(lines):
                if FENCE.match(line):
                    fence = not fence
                    continue
                hits = [m for m in CITE_EXTLESS.finditer(line)
                        if is_extless_citation(m, resolve)]
                if not hits:
                    continue
                if fence:
                    in_fence += len(hits)
                elif QUOTE.match(line):
                    in_quote += len(hits)
                elif is_table_row(line):
                    table_occ += len(hits)
                    table_lines.add((f.name, k))
                else:
                    prose_occ += len(hits)
                    prose_lines.add((f.name, k))
                    if any(is_path_citation(m, resolve) for m in CITE.finditer(line)):
                        shared_lines.add((f.name, k))

    total = in_fence + in_quote + prose_occ + table_occ
    print(f"corpus excludes: {'(none)' if RAW else PREFIXES}")
    print(f"total resolvable extensionless occurrences : {total}")
    print(f"  inside a ``` fence   (not scanned)       : {in_fence}")
    print(f"  inside a `>` quote   (not scanned)       : {in_quote}")
    print(f"  in a table row                           : {table_occ}"
          f"   on {len(table_lines)} distinct rows")
    print(f"  in prose                                 : {prose_occ}"
          f"   on {len(prose_lines)} distinct lines")
    print(f"    of those prose lines, already had a dotted anchor : "
          f"{len(shared_lines)}  (no new verdict)")
    print()
    new_prose = len(prose_lines) - len(shared_lines)
    print(f"gate should gain  prose citations = {new_prose}"
          f"   ({len(prose_lines)} lines - {len(shared_lines)} already counted)")
    print(f"gate should gain  table anchors   = {len(table_lines)}")
    print(f"predicted delta: citations +{new_prose}, "
          f"table_anchors +{len(table_lines)}")


if __name__ == "__main__":
    main()
