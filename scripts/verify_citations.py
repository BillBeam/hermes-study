#!/usr/bin/env python3
"""Verify `path:line @ 863e313` citations in study notes against the baseline tree.

The project's evidence standard is: every assertion about hermes-agent behavior is
followed by `path:line @ <commit>` and a verbatim code block, so that reading the
note *is* the verification. That only holds if the line numbers are right.

R7B found 5 line-number offsets by hand-sampling. This script checks every
citation that is immediately followed by a fenced code block:

  1. Parse citations of the form  path:N  or  path:N-M  (optionally ` @ <sha>`),
     appearing inside backticks or bold, at the end of a line.
  2. If the next non-blank line opens a fenced code block, take the block's
     first non-blank line as the expected source line.
  3. Compare (whitespace-normalized) against the baseline file at line N.
     If it doesn't match, search +/- WINDOW lines and report the actual offset.

Exit status is 1 if any citation MISMATCHES or points at a missing file/line.
Citations without a following code block are counted as UNCHECKED, not failures —
many are prose references to a region, which is legitimate.

With --fix, a MISMATCH whose code block is found at exactly one nearby line is
rewritten in place to the true line number (a `N-M` range is shifted by the same
delta, preserving its length). Ambiguous or not-found cases are never touched —
they are left for a human. Always re-run without --fix afterwards to confirm.

Usage:
    python3 scripts/verify_citations.py <baseline_repo> <note.md> [note.md ...]
    python3 scripts/verify_citations.py /home/user/hermes-agent notes/r7c-*.md
    python3 scripts/verify_citations.py --fix /home/user/hermes-agent notes/r7c-*.md
"""
import re
import sys
from pathlib import Path

WINDOW = 40  # how far to search for the real location when a citation misses
STUDY_ROOT = Path(__file__).resolve().parent.parent  # this study repo

# `gateway/run.py:1234 @ 863e313`  /  **`cron/jobs.py:10-20`**  /  path:1234
CITE = re.compile(
    r"(?P<path>[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:py|md|yaml|yml|toml|c|sh|json|ts|tsx|js))"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?"
)
FENCE = re.compile(r"^\s*```")

# Notes sometimes open a fenced block with a locator comment naming the source,
# e.g. `# gateway/shutdown_flush.py:228-249`. That is annotation, not source —
# skip it and compare against the first real line of the excerpt.
LOCATOR = re.compile(r"^\s*(?:#|//|--)\s*[A-Za-z0-9_][A-Za-z0-9_./-]*\.\w+:\d+")


def norm(s: str) -> str:
    return " ".join(s.split())


def first_source_line(block):
    """First non-blank line of a fenced block, skipping a leading locator comment."""
    for b in block:
        if not b.strip():
            continue
        if LOCATOR.match(b):
            continue
        return b
    return None


def block_locator(block):
    """The `# path:line` comment a block may open with — it, not the prose line,
    is then the authoritative claim about where the excerpt came from."""
    for b in block:
        if not b.strip():
            continue
        if LOCATOR.match(b):
            return CITE.search(b)
        return None
    return None


def check_note(repo: Path, note: Path, fix: bool = False):
    raw = note.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    results = []  # (status, detail)
    fixes = []  # (note_line_index, old_cite, new_cite)
    i = 0
    while i < len(lines):
        line = lines[i]

        # Never scan for citations *inside* a fenced block: `path:line` there is a
        # diagram label or an excerpt's own text, not an assertion being sourced.
        if FENCE.match(line):
            i += 1
            while i < len(lines) and not FENCE.match(lines[i]):
                i += 1
            i += 1
            continue

        cands = list(CITE.finditer(line))
        if not cands:
            i += 1
            continue
        m = cands[-1]  # default: the last citation is usually the one the block follows

        # find the next non-blank line; it must open a fence for us to check content
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines) or not FENCE.match(lines[j]):
            results.append(("UNCHECKED", f"{note.name}:{i+1}  {m.group(0)}"))
            i += 1
            continue

        # collect the fenced block
        k = j + 1
        block = []
        while k < len(lines) and not FENCE.match(lines[k]):
            block.append(lines[k])
            k += 1

        first = first_source_line(block)

        def resolve(pth):
            t = repo / pth
            # A note may legitimately cite this study repo's own files (prior-round
            # reports, chapters). Resolve against the baseline first, then locally.
            if not t.is_file() and (STUDY_ROOT / pth).is_file():
                t = STUDY_ROOT / pth
            return t

        def matches(cand):
            t = resolve(cand.group("path"))
            if not t.is_file() or first is None:
                return False
            src = t.read_text(encoding="utf-8", errors="replace").splitlines()
            n = int(cand.group("start"))
            return 1 <= n <= len(src) and norm(src[n - 1]) == norm(first)

        # A block that opens with its own `# path:line` locator is asserting that
        # location; believe the locator over the surrounding prose citation.
        loc = block_locator(block)
        if loc is not None and resolve(loc.group("path")).is_file():
            m = loc
        # A prose line may carry several citations (the call site AND the callee).
        # The block belongs to whichever one it actually matches.
        elif len(cands) > 1:
            m = next((c for c in cands if matches(c)), m)

        path, start = m.group("path"), int(m.group("start"))
        target = resolve(path)

        if not target.is_file():
            results.append(("MISSING-FILE", f"{note.name}:{i+1}  {path}"))
        elif first is None:
            results.append(("UNCHECKED", f"{note.name}:{i+1}  {m.group(0)} (empty block)"))
        else:
            src = target.read_text(encoding="utf-8", errors="replace").splitlines()
            if start < 1 or start > len(src):
                results.append(
                    ("OUT-OF-RANGE", f"{note.name}:{i+1}  {path}:{start} (file has {len(src)} lines)")
                )
            elif norm(src[start - 1]) == norm(first):
                results.append(("OK", ""))
            else:
                # where does it actually live?
                lo, hi = max(0, start - 1 - WINDOW), min(len(src), start - 1 + WINDOW)
                hits = [n + 1 for n in range(lo, hi) if norm(src[n]) == norm(first)]
                where = f" -> actually at {hits}" if hits else " -> not found within +/-%d" % WINDOW
                if len(hits) == 1:
                    delta = hits[0] - start
                    end = m.group("end")
                    old = f"{path}:{start}" + (f"-{end}" if end else "")
                    new = f"{path}:{hits[0]}" + (f"-{int(end)+delta}" if end else "")
                    fixes.append((i, old, new))
                    where += f" [fixable: {old} -> {new}]"
                results.append(
                    ("MISMATCH", f"{note.name}:{i+1}  {path}:{start}{where}\n"
                                 f"      cited: {norm(first)[:110]}\n"
                                 f"      found: {norm(src[start-1])[:110]}")
                )
        i = k + 1

    if fix and fixes:
        for idx, old, new in fixes:
            lines[idx] = lines[idx].replace(old, new)
        note.write_text("\n".join(lines) + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")
        results.append(("FIXED", f"{note.name}: rewrote {len(fixes)} citation(s)"))
    return results


def main() -> None:
    argv = [a for a in sys.argv[1:] if a != "--fix"]
    fix = "--fix" in sys.argv
    if len(argv) < 2:
        raise SystemExit(__doc__)
    repo = Path(argv[0])
    if not repo.is_dir():
        raise SystemExit(f"baseline repo not a directory: {repo}")

    tally = {}
    problems = []
    for arg in argv[1:]:
        note = Path(arg)
        if not note.is_file():
            print(f"skip (not a file): {note}")
            continue
        for status, detail in check_note(repo, note, fix=fix):
            tally[status] = tally.get(status, 0) + 1
            if status not in ("OK", "UNCHECKED"):
                problems.append(f"[{status}] {detail}")

    for p in problems:
        print(p)
    total = sum(tally.values())
    print(
        f"\ncitations={total}  "
        + "  ".join(f"{k}={v}" for k, v in sorted(tally.items()))
    )
    bad = total - tally.get("OK", 0) - tally.get("UNCHECKED", 0) - tally.get("FIXED", 0)
    if bad:
        print(f"FAIL: {bad} citation(s) need fixing")
        sys.exit(1)
    print("OK: every code-block-backed citation matches the baseline")


if __name__ == "__main__":
    main()
