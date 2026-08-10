#!/usr/bin/env python3
"""Any statistic about this repo's own history must ship its denominator.

The incident this exists for
----------------------------
R10 and R10B both reported "148 commits carry `Claude-Session:`, 160 carry
either trailer", each with a ```verify block holding the exact command. The
command is correct and reruns cleanly. It is also, in a *complete* clone of the
same repository at the same ref, wrong: the answer there is 175 / 187.

Nothing was mis-transcribed. The container's clone was **shallow** — a single
grafted boundary at 37e4a4d cut 40 commits off the history reachable from the
cited ref, 27 of which carried the trailer. `git log --grep | wc -l` cannot tell
the difference between "these commits do not match" and "these commits are not
in my clone", and neither can the reader.

So the rule (R11A): a history statistic is reported **with the number of
commits reachable from the ref it counted over**. That one extra number makes
the incompleteness visible — 218 vs 258 says "your clone is short" at a glance,
while 148 vs 175 says nothing until someone happens to rerun it elsewhere.

This is the same principle CLAUDE.md already applies to negative conclusions:
"全称否定的可信度等于一次 grep 的完备性" — write out the search surface. A
history count is a grep over commits, and its search surface is the clone.

    python3 data/r11a/probes/history_stat_guard.py [ref]

Prints the counts and the denominator, and warns if the clone is shallow.
"""
import subprocess
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
REF = sys.argv[1] if len(sys.argv) > 1 else "HEAD"


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=STUDY, capture_output=True,
                          text=True, check=True).stdout.strip()


def count(*grep) -> int:
    args = ["log", REF, "--regexp-ignore-case", "--format=%H"]
    for g in grep:
        args.append(f"--grep={g}")
    out = git(*args)
    return len(out.splitlines()) if out else 0


def main() -> None:
    shallow = (STUDY / ".git" / "shallow").is_file()
    reachable = int(git("rev-list", "--count", REF))

    print(f"ref                      : {REF}")
    print(f"reachable commits        : {reachable}   <- the denominator")
    print(f"clone is shallow         : {'YES — counts below are LOWER BOUNDS' if shallow else 'no'}")
    if shallow:
        boundary = (STUDY / ".git" / "shallow").read_text().split()
        print(f"  shallow boundary       : {', '.join(b[:7] for b in boundary)}")
        print("  fix: git fetch --unshallow, then rerun")
    print()
    print(f"Claude-Session: only     -> {count('Claude-Session:')}")
    print(f"either trailer           -> {count('Claude-Session:', 'Co-Authored-By: Claude')}")


if __name__ == "__main__":
    main()
