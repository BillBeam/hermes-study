#!/usr/bin/env python3
"""Re-run every ```verify block and diff it against the ```text block it precedes.

CLAUDE.md (R8-fix, review-1 建议-16) says: a shell command written as evidence
MUST be the one whose re-run reproduces the stated conclusion, fenced as
```verify. Until R10B that rule had no enforcement — it was the only evidence
rule in the project on the honour system, and the incident that produced it
(r4-90's self-check grep, whose `iron` matched env*iron*ment and hit every file
it claimed hit nothing) is exactly the kind of thing a human reviewer skims past.

R10B added this after tripping the same wire four times in one file: four pasted
outputs were hand-trimmed copies of what the command actually prints, so the
command and the block disagreed while both looked right.

Pairing rule — deliberately narrow, in the same spirit as the citation gate's
"declared, not sniffed":

    ```verify
    <command>
    ```

    ```text            <- the very next block, blank lines allowed between
    <expected stdout>
    ```

A ```verify block with no ```text block after it is UNPAIRED and reported but
not failed: plenty of commands are cited so the reader can run them, not to
pin an output. Anything paired must match stdout byte-for-byte after trailing
whitespace is stripped.

Commands run with cwd = the study repo root, via bash -c, stdout only (stderr
is shown on failure but not compared — pasted evidence is what the reader sees).

    python3 scripts/verify_evidence_commands.py notes/r10b-*.md
    python3 scripts/verify_evidence_commands.py --list notes/foo.md   # dry run

Exit 1 if any paired block differs.
"""
import difflib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 900

# `(?:(?!```).)*?` instead of `.*?`: a plain non-greedy dot can BACKTRACK PAST the
# command's own closing fence and keep going until it finds some later ```text,
# silently pairing a command with an unrelated block hundreds of lines away.
# The first version of this checker did exactly that and reported a bogus diff
# against a block from a different section — a checker whose own pairing is
# sloppy manufactures failures, which is how a gate gets ignored.
NOFENCE = r"(?:(?!```).)*?"
PAIR = re.compile(r"```verify\n(?P<cmd>" + NOFENCE + r")```[ \t]*\n\s*```text\n"
                  r"(?P<out>" + NOFENCE + r")```", re.S)
ANY_VERIFY = re.compile(r"```verify\n" + NOFENCE + r"```", re.S)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--list" in sys.argv
    if not args:
        raise SystemExit(__doc__)

    checked = failed = unpaired = 0
    for arg in args:
        note = Path(arg)
        if not note.is_file():
            print(f"skip (not a file): {note}")
            continue
        text = note.read_text(encoding="utf-8", errors="replace")
        paired = PAIR.findall(text)
        n_all = len(ANY_VERIFY.findall(text))
        unpaired += n_all - len(paired)

        for cmd, expected in paired:
            cmd = cmd.strip()
            checked += 1
            if dry:
                print(f"[would run] {note.name}: {cmd.splitlines()[0][:90]}")
                continue
            r = subprocess.run(["bash", "-c", cmd], cwd=ROOT, capture_output=True,
                               text=True, timeout=TIMEOUT)
            got = r.stdout.rstrip("\n")
            want = expected.rstrip("\n")
            if got == want:
                continue
            failed += 1
            print(f"\n[EVIDENCE-DIFF] {note}")
            print(f"  command: {cmd.splitlines()[0][:110]}")
            diff = list(difflib.unified_diff(want.splitlines(), got.splitlines(),
                                             "pasted-in-note", "actual-rerun", lineterm=""))
            print("\n".join("      " + d for d in diff[:30]))
            if len(diff) > 30:
                print(f"      ... ({len(diff) - 30} more diff lines)")
            if r.returncode != 0 and r.stderr.strip():
                print(f"      stderr: {r.stderr.strip().splitlines()[-1][:150]}")

    print(f"\nverify-blocks paired={checked}  unpaired={unpaired}  differing={failed}")
    if failed:
        print("FAIL: a ```verify command does not reproduce the output pasted under it")
        sys.exit(1)
    print("OK: every paired ```verify command reproduces its pasted output")


if __name__ == "__main__":
    main()
