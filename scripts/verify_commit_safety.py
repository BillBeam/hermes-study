#!/usr/bin/env python3
"""Block commits that sweep in a file a background producer is still writing.

WHY THIS EXISTS
---------------
The same accident happened in R9B, R10B and R11A: the mainline ran a `git add`
that matched more than it meant to, and a file a still-running subagent was
midway through writing landed in a commit. All three times a human noticed.
CLAUDE.md already carries the rule ("异步产出的完成判定:只以完成信号为准,不以
产物形态推断") — a rule that had no enforcement, which is exactly the shape this
project keeps deciding to mechanise (R7C→R8A for citations, R8C→R8D for block
drift, R10B→R11A for evidence commands).

DECLARATION, NOT SNIFFING
-------------------------
The gate cannot observe "is an agent writing this file right now" — no filesystem
fact answers that. So the producer's outputs are *declared* at dispatch time,
in a claim file, the same way `verify_citations.py` requires an author to declare
that a block is not source rather than sniffing at whether it looks like code.
A dispatch already has to name its outputs (the 派工书 does), so the declaration
costs nothing new.

CLAIM FORMAT — data/inflight/<slug>.claim
-----------------------------------------
    agent: <label matching the dispatch>
    dispatched: <free text, usually an ISO timestamp>
    signal: OPEN
    path: notes/r11b-raw-foo.md
    path: data/r11b/probes/foo-*.py

`signal:` is the whole mechanism. It stays `OPEN` until the *completion signal*
arrives, then it becomes `RELEASED <what the signal was>`. Editing that one line
is the only way to make the claimed paths committable, so "did the signal
actually arrive?" becomes a thing the author has to answer in writing rather than
infer from the file looking finished.

`path:` entries are fnmatch globs against repo-relative paths. Claim files
themselves are always committable — they are the audit trail.

TWO NETS
--------
1. BLOCKING — a staged path matching an OPEN claim. This is the declared case.
2. WARNING (never blocks) — while any claim is OPEN, a staged file whose mtime is
   within FRESH_WINDOW_S of now and which no claim covers. That is the
   "declaration was incomplete" case; it cannot block, because the mainline
   legitimately edits its own files while shards run. Non-blocking hints have
   precedent here (R8C's UNCHECKED≥90% notice).

Usage:
    scripts/verify_commit_safety.py --staged      # what the pre-commit hook runs
    scripts/verify_commit_safety.py <path>...     # ask about specific paths
    scripts/verify_commit_safety.py --list        # show claims and their state
Exit 0 = nothing staged is under an open claim.
"""
import fnmatch
import subprocess
import sys
import time
from pathlib import Path

CLAIM_DIR = "data/inflight"
FRESH_WINDOW_S = 120


def repo_root() -> Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         capture_output=True, check=True).stdout.decode().strip()
    return Path(out)


def load_claims(root: Path) -> list[dict]:
    claims = []
    d = root / CLAIM_DIR
    if not d.is_dir():
        return claims
    for f in sorted(d.glob("*.claim")):
        claim = {"file": f.relative_to(root).as_posix(), "agent": "?",
                 "dispatched": "?", "signal": "OPEN", "paths": []}
        for raw in f.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            key, _, val = line.partition(":")
            key, val = key.strip().lower(), val.strip()
            if key == "path":
                claim["paths"].append(val)
            elif key in ("agent", "dispatched", "signal"):
                claim[key] = val
        claims.append(claim)
    return claims


def is_open(claim: dict) -> bool:
    return claim["signal"].split()[0].upper() == "OPEN" if claim["signal"] else True


def staged_paths(root: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(root), "diff", "--cached", "--name-only", "-z"],
                         capture_output=True, check=True).stdout.decode()
    return [p for p in out.split("\0") if p]


def main(argv: list[str]) -> int:
    root = repo_root()
    claims = load_claims(root)

    if "--list" in argv:
        if not claims:
            print("no claims in " + CLAIM_DIR)
        for c in claims:
            state = "OPEN" if is_open(c) else c["signal"]
            print(f"{c['file']}  agent={c['agent']}  signal={state}")
            for p in c["paths"]:
                print(f"    path: {p}")
        return 0

    if "--staged" in argv:
        targets = staged_paths(root)
    else:
        targets = [a for a in argv if not a.startswith("--")]
    if not targets:
        return 0

    open_claims = [c for c in claims if is_open(c)]
    claim_files = {c["file"] for c in claims}

    violations = []
    covered = set()
    for path in targets:
        if path in claim_files:
            continue  # the audit trail is always committable
        for c in open_claims:
            for pat in c["paths"]:
                if path == pat or fnmatch.fnmatch(path, pat):
                    violations.append((path, c))
                    covered.add(path)
                    break
            else:
                continue
            break

    if violations:
        print("FAIL: refusing to commit — these paths are under an OPEN claim,")
        print("      i.e. their producer has not signalled completion.\n")
        for path, c in violations:
            print(f"  {path}")
            print(f"      claimed by {c['file']} (agent={c['agent']}, dispatched={c['dispatched']})")
        print("\nIf the completion signal HAS arrived, record it and retry:")
        for c in sorted({v[1]['file'] for v in violations}):
            print(f"  edit {c}: replace 'signal: OPEN' with "
                  f"'signal: RELEASED <what the signal was>'")
        print("\nIf it has not: do not commit these paths. Waiting is the whole point —")
        print("a finished-looking file is not a completion signal (CLAUDE.md).")
        return 1

    if open_claims:
        now = time.time()
        fresh = []
        for path in targets:
            if path in covered or path in claim_files:
                continue
            fp = root / path
            try:
                if now - fp.stat().st_mtime <= FRESH_WINDOW_S:
                    fresh.append(path)
            except OSError:
                pass
        if fresh:
            print(f"NOTE: {len(open_claims)} claim(s) still OPEN and these staged "
                  f"files changed in the last {FRESH_WINDOW_S}s but no claim covers them:")
            for p in fresh:
                print(f"  {p}")
            print("  If any belongs to a running producer, its claim is missing a "
                  "`path:` line. Not blocking.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
