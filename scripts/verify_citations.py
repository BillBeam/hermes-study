#!/usr/bin/env python3
"""Verify `path:line @ 863e313` citations in study notes against the baseline tree.

The project's evidence standard is: every assertion about hermes-agent behavior is
followed by `path:line @ <commit>` and a verbatim excerpt, so that reading the
note *is* the verification. That only holds if the line numbers are right.

R7B found 5 line-number offsets by hand-sampling. This script checks every
citation that is immediately followed by an excerpt block:

  1. Parse citations of the form  path:N  or  path:N-M  (optionally ` @ <sha>`),
     appearing inside backticks or bold, at the end of a line.
  2. If the next non-blank line opens an excerpt block, take the block's first
     non-blank line as the expected source line. Two block forms count:
       - a fenced block  ```...```   — the code side (contract: verbatim source);
       - a blockquote    > ...       — the doc side (see "Two block kinds" below).
  3. Compare (whitespace-normalized) against the baseline file at line N.
     If it doesn't match, search +/- WINDOW lines and report the actual offset.

Exit status is 1 if any citation MISMATCHES or points at a missing file/line.
Citations without a following block are counted as UNCHECKED, not failures —
many are prose references to a region, which is legitimate.

Two block kinds, two strictnesses (review-1 M-16a)
--------------------------------------------------
Until R8-fix this script only looked at fenced blocks, so the *code* side of every
doc-vs-code ruling was machine-checked while the *doc* side — which is written as a
`>` blockquote, essentially always — was never checked by anything. A first-pass
review sampling that blind spot hit 5 drifted anchors out of 5 sampled. So
blockquotes are now checked too, but under a deliberately weaker rule:

  - **Fence**: contract is "verbatim source excerpt". Not matching at the cited
    line is a MISMATCH whether or not the text is found elsewhere.
  - **Blockquote**: the corpus uses `>` for verbatim doc excerpts *and* for
    paraphrase. So a blockquote is only failed when its text is found VERBATIM at
    some other line of the cited file within the window — that proves it is a real
    excerpt that is merely mis-anchored. Text found nowhere nearby is treated as
    paraphrase and recorded UNCHECKED. This catches anchor drift without
    manufacturing failures out of every paraphrased quote.

Declared non-source fences
--------------------------
A fenced block whose info string is in NON_SOURCE_LANGS (`text`, `console`,
`verify`, `shell-session`) is a shell transcript, a judgement table, a checklist —
not a source excerpt — and is recorded UNCHECKED. This is an *author declaration*,
not a heuristic sniff: the alternative considered (guessing "this doesn't look like
code") would quietly weaken the gate, which is the one thing a blocking gate must
not do.

With --fix, a MISMATCH whose block is found at exactly one nearby line is
rewritten in place to the true line number (a `N-M` range is shifted by the same
delta, preserving its length). Ambiguous or not-found cases are never touched —
they are left for a human. Always re-run without --fix afterwards to confirm.

Per-file UNCHECKED ratio hint (R8C)
-----------------------------------
UNCHECKED is not a failure, and legitimately so: a prose reference to a region is
a valid thing to write. But UNCHECKED is also exactly what a *layout* mistake
looks like from in here. The gate pairs a citation with the block that FOLLOWS
it; an author who puts the anchor *after* its code block produces a file whose
every citation is UNCHECKED, and the gate says OK. That is the failure mode this
hint exists to surface: when a single file is at or above UNCHECKED_HINT_RATIO
(and carries at least UNCHECKED_HINT_MIN citations, so a 1-of-1 file cannot trip
it), the run prints a "疑似锚点排版不合规" note naming the file.

It is a HINT, not a failure — it does not change the exit code. A file can
legitimately be nearly all prose. Making it blocking would push authors to
manufacture code blocks to clear a gate, which is worse than the disease.

The run also prints 可校验比例 = OK / (OK + UNCHECKED + failures), the metric R8A
put a 70% floor under. The floor is a reporting standard, not a script gate:
the script computes and prints the number so the round report cannot fudge it.

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

# Per-file UNCHECKED-ratio hint (see module docstring). Non-blocking.
UNCHECKED_HINT_RATIO = 0.90
UNCHECKED_HINT_MIN = 5  # below this many citations the ratio says nothing
VERIFIABLE_FLOOR = 0.70  # R8A's reporting floor for OK / all citations

# `gateway/run.py:1234 @ 863e313`  /  **`cron/jobs.py:10-20`**  /  path:1234
CITE = re.compile(
    r"(?P<path>[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:py|md|yaml|yml|toml|c|sh|json|ts|tsx|js))"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?"
)
FENCE = re.compile(r"^\s*```(?P<lang>[A-Za-z0-9_+-]*)")
QUOTE = re.compile(r"^\s*>\s?(?P<body>.*)$")

# Fences the author has declared to be something other than a source excerpt.
NON_SOURCE_LANGS = {"text", "console", "verify", "shell-session"}

# Notes sometimes open a fenced block with a locator comment naming the source,
# e.g. `# gateway/shutdown_flush.py:228-249`. That is annotation, not source —
# skip it and compare against the first real line of the excerpt.
LOCATOR = re.compile(r"^\s*(?:#|//|--)\s*[A-Za-z0-9_][A-Za-z0-9_./-]*\.\w+:\d+")

_SRC_CACHE: dict = {}


def norm(s: str) -> str:
    return " ".join(s.split())


def source_lines(path: Path):
    key = str(path)
    if key not in _SRC_CACHE:
        _SRC_CACHE[key] = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return _SRC_CACHE[key]


def first_source_line(block):
    """First non-blank line of a block, skipping a leading locator comment."""
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


def read_block(lines, j):
    """Read the excerpt block that starts at line index *j*.

    Returns (kind, body_lines, next_index) where kind is "fence", "quote", or
    None when line *j* does not open a block at all.
    """
    fm = FENCE.match(lines[j])
    if fm:
        k = j + 1
        body = []
        while k < len(lines) and not FENCE.match(lines[k]):
            body.append(lines[k])
            k += 1
        lang = (fm.group("lang") or "").lower()
        kind = "non-source" if lang in NON_SOURCE_LANGS else "fence"
        return kind, body, k + 1

    if QUOTE.match(lines[j]):
        k = j
        body = []
        while k < len(lines):
            qm = QUOTE.match(lines[k])
            if not qm:
                break
            body.append(qm.group("body"))
            k += 1
        return "quote", body, k

    return None, [], j


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

        # Nor inside a blockquote: a quoted doc excerpt may contain `path:line`
        # of its own (docs cite code too), and that is the *quote's* text, not
        # this note asserting something.
        if QUOTE.match(line):
            while i < len(lines) and QUOTE.match(lines[i]):
                i += 1
            continue

        cands = list(CITE.finditer(line))
        if not cands:
            i += 1
            continue
        m = cands[-1]  # default: the last citation is usually the one the block follows

        # find the next non-blank line; it must open a block for us to check content
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines):
            results.append(("UNCHECKED", f"{note.name}:{i+1}  {m.group(0)}"))
            i += 1
            continue

        kind, block, nxt = read_block(lines, j)
        if kind is None:
            results.append(("UNCHECKED", f"{note.name}:{i+1}  {m.group(0)}"))
            i += 1
            continue
        if kind == "non-source":
            results.append(
                ("UNCHECKED", f"{note.name}:{i+1}  {m.group(0)} (declared non-source block)")
            )
            i = nxt
            continue

        first = first_source_line(block)

        def resolve(pth):
            t = repo / pth
            # A note may legitimately cite this study repo's own files (prior-round
            # reports, chapters). Resolve against the baseline first, then locally.
            if not t.is_file() and (STUDY_ROOT / pth).is_file():
                t = STUDY_ROOT / pth
            return t

        # A `>` excerpt of a prose doc is routinely re-wrapped to the note's own
        # column width, so "quote line 1 == source line N" is too strict: the
        # single source line got split across several quote lines. Joining the
        # quote back into one string and asking whether the source line *starts*
        # with it recovers those. Fences keep strict equality — a code excerpt
        # that got re-wrapped is not a faithful excerpt in the first place.
        joined = norm(" ".join(block)) if kind == "quote" else ""

        def line_matches(text: str) -> bool:
            if first is None:
                return False
            if norm(text) == norm(first):
                return True
            return bool(joined) and len(joined) >= 20 and norm(text).startswith(joined)

        def matches(cand):
            t = resolve(cand.group("path"))
            if not t.is_file() or first is None:
                return False
            src = source_lines(t)
            n = int(cand.group("start"))
            return 1 <= n <= len(src) and line_matches(src[n - 1])

        # A block that opens with its own `# path:line` locator is asserting that
        # location; believe the locator over the surrounding prose citation.
        loc = block_locator(block) if kind == "fence" else None
        if loc is not None and resolve(loc.group("path")).is_file():
            m = loc
        # A prose line may carry several citations (the call site AND the callee).
        # The block belongs to whichever one it actually matches.
        elif len(cands) > 1:
            m = next((c for c in cands if matches(c)), m)

        path, start = m.group("path"), int(m.group("start"))
        target = resolve(path)

        if not target.is_file():
            # A blockquote after a prose line that merely happens to name a file is
            # common; only the fence contract makes an unresolvable path an error.
            status = "MISSING-FILE" if kind == "fence" else "UNCHECKED"
            results.append((status, f"{note.name}:{i+1}  {path}"))
        elif first is None:
            results.append(("UNCHECKED", f"{note.name}:{i+1}  {m.group(0)} (empty block)"))
        else:
            src = source_lines(target)
            if start < 1 or start > len(src):
                results.append(
                    ("OUT-OF-RANGE", f"{note.name}:{i+1}  {path}:{start} (file has {len(src)} lines)")
                )
            elif line_matches(src[start - 1]):
                results.append(("OK", ""))
            else:
                # where does it actually live?
                lo, hi = max(0, start - 1 - WINDOW), min(len(src), start - 1 + WINDOW)
                hits = [n + 1 for n in range(lo, hi) if line_matches(src[n])]
                if kind == "quote" and not hits:
                    # A `>` block whose text appears nowhere near the anchor is a
                    # paraphrase, not drift. Not checkable, so not a failure.
                    results.append(
                        ("UNCHECKED", f"{note.name}:{i+1}  {m.group(0)} (quote, not verbatim)")
                    )
                    i = nxt
                    continue
                where = f" -> actually at {hits}" if hits else " -> not found within +/-%d" % WINDOW
                if len(hits) == 1:
                    delta = hits[0] - start
                    end = m.group("end")
                    old = f"{path}:{start}" + (f"-{end}" if end else "")
                    new = f"{path}:{hits[0]}" + (f"-{int(end)+delta}" if end else "")
                    fixes.append((i, old, new))
                    where += f" [fixable: {old} -> {new}]"
                detail = (
                    f"{note.name}:{i+1}  {path}:{start}{where}\n"
                    f"      cited: {norm(first)[:110]}\n"
                    f"      found: {norm(src[start-1])[:110]}"
                )
                # review-1 M-8: when the prose line carries several citations the
                # block is compared against a *fallback* pick, and printing only
                # that pick sent the last reader hunting an innocent citation.
                # Name every candidate and say which one this verdict is about.
                if len(cands) > 1:
                    listed = "  ".join(c.group(0) for c in cands)
                    detail += (
                        f"\n      note: {len(cands)} citations on this line ({listed});"
                        f" none matched, so the verdict above is about the fallback"
                        f" pick {path}:{start} — the drifted one may be another."
                    )
                results.append(("MISMATCH", detail))
        i = nxt

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
    per_file = {}  # path -> {status: count}
    for arg in argv[1:]:
        note = Path(arg)
        if not note.is_file():
            print(f"skip (not a file): {note}")
            continue
        seen = per_file.setdefault(str(note), {})
        for status, detail in check_note(repo, note, fix=fix):
            tally[status] = tally.get(status, 0) + 1
            seen[status] = seen.get(status, 0) + 1
            if status not in ("OK", "UNCHECKED"):
                problems.append(f"[{status}] {detail}")

    for p in problems:
        print(p)

    # Files that are almost entirely UNCHECKED. Usually that means the anchors
    # were written AFTER their code blocks, so the gate never paired them up and
    # silently checked nothing. See module docstring — hint only, never fatal.
    suspects = []
    for path, counts in sorted(per_file.items()):
        n = sum(v for k, v in counts.items() if k != "FIXED")
        if n < UNCHECKED_HINT_MIN:
            continue
        ratio = counts.get("UNCHECKED", 0) / n
        if ratio >= UNCHECKED_HINT_RATIO:
            suspects.append((path, counts.get("UNCHECKED", 0), n, ratio))
    if suspects:
        print(
            f"\nHINT: 疑似锚点排版不合规 —— 以下文件 UNCHECKED 占比 >= {UNCHECKED_HINT_RATIO:.0%}"
        )
        print("      按制度锚点 `路径:行号 @ 863e313` 应单独成行、置于代码块/引用块**之前**;")
        print("      写在块后会让每一条引用都配不上块,于是全部记 UNCHECKED —— 关卡看起来是绿的,")
        print("      实际一条都没校验。请逐条确认是真散文引用,还是锚点放错了位置。")
        for path, u, n, ratio in suspects:
            print(f"      - {path}: UNCHECKED {u}/{n} = {ratio:.1%}")
        print("      (提示不影响退出码。)")

    total = sum(tally.values())
    print(
        f"\ncitations={total}  "
        + "  ".join(f"{k}={v}" for k, v in sorted(tally.items()))
    )
    checkable = total - tally.get("FIXED", 0)
    if checkable:
        rate = tally.get("OK", 0) / checkable
        flag = "" if rate >= VERIFIABLE_FLOOR else f"  << 低于 {VERIFIABLE_FLOOR:.0%} 下限"
        print(f"可校验比例 OK/{checkable} = {rate:.1%}{flag}")
    bad = total - tally.get("OK", 0) - tally.get("UNCHECKED", 0) - tally.get("FIXED", 0)
    if bad:
        print(f"FAIL: {bad} citation(s) need fixing")
        sys.exit(1)
    print("OK: every code-block-backed citation matches the baseline")


if __name__ == "__main__":
    main()
