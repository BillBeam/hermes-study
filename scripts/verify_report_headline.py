#!/usr/bin/env python3
"""Check the CLAUDE.md rule "报告第一句 ≤20 字结论" — with a stated caliber.

Until R8-fix the rule had no counting caliber, so it could not be checked by
anything and three reports drifted past it under every reading. The caliber is
now fixed and mechanical:

  * The headline is the report's **first non-empty line that is not a heading,
    not a quote, and not a table row** — i.e. the first line of prose.
  * A leading label such as `一句话结论:` / `结论:` is **not** counted.
  * Markdown emphasis (`**`, `*`, `` ` ``) is stripped; everything else counts,
    **including Chinese punctuation** — a comma is a character the reader reads.
  * The sentence ends at the first `。`/`!`/`?`/`.` or end of line.
  * Length = number of characters after the above stripping.

Pure-data appendices are exempt: they carry no conclusion of their own, they are
the main volume's data attachment. Exemption is by explicit list, not by guessing.

Usage:
    python3 scripts/verify_report_headline.py reports/*.md
"""
import re
import sys
from pathlib import Path

LIMIT = 20

# Data attachments to the main volume — no headline conclusion expected.
EXEMPT = {"round-1-capabilities-full.md"}

# Historical reports whose headline predates this caliber existing. They are NOT
# silently rewritten (a past round's report is a record, and this project's rule
# is that report-level corrections appear as an errata section rather than as an
# edited body), and they are NOT hidden either: each one names the overage in its
# own errata. The list is closed — nothing may be added to it. Everything written
# from R8-fix onward is held to the limit.
GRANDFATHERED = {"round-1-survey.md"}

LABEL = re.compile(r"^\s*(?:\*\*)?(?:一句话结论|结论|TL;DR)(?:\*\*)?\s*[::]\s*")
EMPH = re.compile(r"[*`>]+")
SENT_END = re.compile(r"[。!?.]")


def headline(path: Path):
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith(">") or s.startswith("|"):
            continue
        if s.startswith("---"):
            continue
        return s
    return None


def measure(line: str) -> tuple:
    s = LABEL.sub("", line)
    s = EMPH.sub("", s).strip()
    m = SENT_END.search(s)
    sent = s[: m.start()] if m else s
    return sent, len(sent)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    bad = 0
    for a in args:
        p = Path(a)
        if not p.is_file():
            print(f"skip (not a file): {p}")
            continue
        if p.name in EXEMPT:
            print(f"EXEMPT   {p.name}  (纯数据附卷,不承载结论句)")
            continue
        h = headline(p)
        if h is None:
            print(f"NO-PROSE {p.name}")
            bad += 1
            continue
        sent, n = measure(h)
        if n <= LIMIT:
            status = "OK "
        elif p.name in GRANDFATHERED:
            status = "OLD"  # over, but recorded in that report's own errata
        else:
            status = "OVER"
            bad += 1
        print(f"{status} {n:3d}  {p.name}  「{sent}」")
    print(f"\nlimit={LIMIT}  over={bad}")
    if bad:
        print(f"FAIL: {bad} report headline(s) over the limit")
        sys.exit(1)
    print("OK: every report headline is within the limit")


if __name__ == "__main__":
    main()
