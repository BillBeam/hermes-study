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

R11C adds the RUNNABILITY check (closes H-R11B-c). Pairing only ever compared
the blocks an author *chose* to pin, so an unpaired block had never been
executed by anything. R11B ran all 595 read-only unpaired blocks once by hand
and found 63 that cannot reproduce anything at all — the fence holds a command
spliced together with its own output, or a path from a session that no longer
exists, or code that raises. Those claim to be "the command whose re-run
reproduces this", and re-running them produces no conclusion. No pairing rate,
however high, finds any of them.

So: every UNPAIRED block is classified, and the read-only ones are run.

  MUTATING   installs packages / writes files / touches a repo — NEVER run.
             The corpus really does contain `npm install --workspace ...`
             against the baseline, and a clean baseline is the first thing
             every round asserts. A gate that dirties it is worse than no gate.
  READONLY   run it; RUNFAIL iff it exits non-zero AND writes to stderr.

The stderr half of that predicate is the whole design. `grep` with no match
exits 1 and says nothing, and "no match" is frequently the conclusion being
evidenced — flagging those would make the gate cry wolf on correct evidence.
Requiring stderr keeps exactly the three failing shapes (spliced output, dead
path, runtime error) and drops the 27 silent exit-1 blocks, whose legitimacy
R11B explicitly left unadjudicated. Measured against R11B's hand-classified
sweep this predicate reproduces its A+B+E = 63 exactly.

Landing straight to blocking, without the report-only phase used by R7C->R8A,
R8C->R8D and R10B->R11A: that phase exists so a new gate does not scream about
a backlog it did not create, and here there is none to scream about. The
mandatory scope is `chapters/` + the current round, `chapters/` holds zero
unpaired blocks, and R11C clears the 63 in the same round it lands the check —
the same reasoning R9B used to land table anchors blocking on day one.

Commands run with cwd = the study repo root, via bash -c, stdout only (stderr
is shown on failure but not compared — pasted evidence is what the reader sees).

    python3 scripts/verify_evidence_commands.py notes/r10b-*.md
    python3 scripts/verify_evidence_commands.py --list notes/foo.md   # dry run
    python3 scripts/verify_evidence_commands.py --no-runnability ...  # pairing only

Exit 1 if any paired block differs, any command times out, or any unpaired
read-only command fails to run.
"""
import difflib
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mandatory_scope import format_scope, resolve, take_round_args  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# R11B (H-R11A-e): this used to be a bare constant, and `subprocess.run` was
# called without catching `TimeoutExpired`. One command that outran the limit
# therefore killed the whole scan with a traceback, and **every file after it
# went unchecked** — while the output already printed still looked like a
# complete failure list. That is the same shape this gate exists to catch:
# the numbers look right, the coverage is empty. R11A had to work around it with
# an external per-file timeout wrapper. Now a timeout is reported per command,
# counted, and fails the run, but the scan continues.
#
# The env override exists so the negative control can force a timeout in
# seconds rather than in fifteen minutes.
TIMEOUT = int(os.environ.get("HERMES_EVIDENCE_TIMEOUT", "900"))

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

# Only match these verbs in COMMAND position (line start, or after a pipe /
# semicolon / && / $( ). Without that anchor `grep -rn "curl"` reads as a
# network call and the block gets skipped as MUTATING — i.e. the sniffing
# would silently shrink the gate's coverage. Ported from R11B's
# data/r11b/probes/evidence_block_profile.py so the gate owns its own
# classifier rather than importing a probe.
MUTATE = re.compile(
    r"(?:^|[|;&]\s*|\$\(\s*)(?:sudo\s+)?"
    r"(?:pip3?\s+install|apt(?:-get)?\s+install|npm\s+(?:i|ci|install)|yarn\s+add"
    r"|pnpm\s+(?:i|add|install)|cargo\s+(?:install|build)|go\s+install"
    r"|rm\s+-|mv\s+|cp\s+|chmod\s+|chown\s+|tee\s+|mkdir\s+"
    r"|git\s+(?:commit|push|checkout|clean|reset|apply|rm)"
    r"|curl\s|wget\s)", re.M)
# Any write redirection other than to /dev/null. The (?<![0-9<>]) guard keeps
# `2>&1` and `<<'PY'` heredocs from reading as writes.
REDIRECT_WRITE = re.compile(r"(?<![0-9<>])>\s*(?!/dev/null)[^\s|&;]+")

BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))


def is_mutating(cmd: str) -> bool:
    return bool(MUTATE.search(cmd) or REDIRECT_WRITE.search(cmd))


def baseline_porcelain() -> str | None:
    """Tracked-file dirtiness of the read-only baseline, or None if absent.

    The runnability check executes commands nobody vetted for this run. If the
    classifier ever lets a mutating one through, the damage lands on the one
    artifact every `路径:行号 @ 863e313` citation in the project depends on.
    Assert it directly before and after rather than trusting the classifier.
    """
    if not (BASELINE / ".git").exists():
        return None
    r = subprocess.run(["git", "-C", str(BASELINE), "status", "--porcelain",
                        "--untracked-files=no"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def main() -> None:
    # `--round <N>` 展开 CLAUDE.md 的强制范围;单一落点见 scripts/mandatory_scope.py。
    rounds, rest = take_round_args(sys.argv[1:])
    args = [a for a in rest if not a.startswith("--")]
    dry = "--list" in sys.argv
    runnability = "--no-runnability" not in sys.argv
    scope_line = None
    if rounds:
        scope_files, breakdown = resolve(rounds)
        scope_line = format_scope(rounds, breakdown)
        args = [str(p) for p in scope_files]
    if not args:
        raise SystemExit(__doc__)
    print(scope_line if scope_line else f"scope=explicit  files={len(args)}")

    checked = failed = unpaired = timedout = 0
    ran = runfailed = skipped_mutating = 0
    porcelain_before = baseline_porcelain() if runnability and not dry else None
    for arg in args:
        note = Path(arg)
        if not note.is_file():
            print(f"skip (not a file): {note}")
            continue
        text = note.read_text(encoding="utf-8", errors="replace")
        paired = PAIR.findall(text)
        paired_bodies = {m.group("cmd") for m in PAIR.finditer(text)}
        all_bodies = [m.group(0)[len("```verify\n"):-3]
                      for m in ANY_VERIFY.finditer(text)]
        loose = [b for b in all_bodies if b not in paired_bodies]
        unpaired += len(all_bodies) - len(paired)

        for body in loose if runnability else []:
            cmd = body.strip()
            if not cmd:
                continue
            if is_mutating(cmd):
                skipped_mutating += 1
                continue
            if dry:
                print(f"[would run, unpaired] {note.name}: {cmd.splitlines()[0][:80]}")
                continue
            ran += 1
            try:
                r = subprocess.run(["bash", "-c", cmd], cwd=ROOT, capture_output=True,
                                   text=True, timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                timedout += 1
                print(f"\n[EVIDENCE-TIMEOUT] {note}")
                print(f"  command: {cmd.splitlines()[0][:110]}")
                print(f"  exceeded {TIMEOUT}s — counted as a failure, scan continues")
                continue
            # Non-zero with nothing on stderr is `grep` finding nothing, and
            # "found nothing" is often the conclusion. Only a command that also
            # complains has actually failed to run.
            if r.returncode == 0 or not r.stderr.strip():
                continue
            runfailed += 1
            print(f"\n[EVIDENCE-RUNFAIL] {note}")
            print(f"  command: {cmd.splitlines()[0][:110]}")
            print(f"  exit {r.returncode}: {r.stderr.strip().splitlines()[-1][:150]}")

        for cmd, expected in paired:
            cmd = cmd.strip()
            checked += 1
            if dry:
                print(f"[would run] {note.name}: {cmd.splitlines()[0][:90]}")
                continue
            try:
                r = subprocess.run(["bash", "-c", cmd], cwd=ROOT, capture_output=True,
                                   text=True, timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                timedout += 1
                print(f"\n[EVIDENCE-TIMEOUT] {note}")
                print(f"  command: {cmd.splitlines()[0][:110]}")
                print(f"  exceeded {TIMEOUT}s — counted as a failure, scan continues")
                continue
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

    print(f"\nverify-blocks paired={checked}  unpaired={unpaired}  "
          f"differing={failed}  timedout={timedout}")
    if runnability and not dry:
        print(f"runnability   ran={ran}  runfail={runfailed}  "
              f"skipped-mutating={skipped_mutating}")
    porcelain_after = baseline_porcelain() if runnability and not dry else None
    dirtied = (porcelain_before is not None
               and porcelain_after is not None
               and porcelain_before != porcelain_after)
    if dirtied:
        print(f"FAIL: running unpaired commands dirtied the read-only baseline "
              f"at {BASELINE} — the MUTATING classifier let one through")
        sys.exit(1)
    if timedout:
        print("FAIL: a ```verify command exceeded the time limit "
              "(a command that cannot finish cannot reproduce anything)")
        sys.exit(1)
    if failed:
        print("FAIL: a ```verify command does not reproduce the output pasted under it")
        sys.exit(1)
    if runfailed:
        print("FAIL: an unpaired ```verify command does not run at all "
              "(a command that cannot run cannot reproduce anything)")
        sys.exit(1)
    print("OK: every paired ```verify command reproduces its pasted output")


if __name__ == "__main__":
    main()
