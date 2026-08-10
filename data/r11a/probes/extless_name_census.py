#!/usr/bin/env python3
"""H-R10B-a groundwork: how big is the extensionless-anchor gap, and what would
a *sniffed* whitelist swallow that a *declared* one does not?

H-R10B-a says the fix needs "an explicit list of extensionless filenames —
declared, not sniffed". That is a design assertion, and this project's own rule
is that assertions get evidence. The cheap-looking alternative is to sniff: walk
the baseline, collect every basename with no extension, accept `name:digits` for
any of them. This probe measures what that alternative actually costs, so the
choice between the two is a number rather than a preference.

Three readings, all printed:

  A. baseline census   — every extensionless basename that exists at 863e313
  B. declared capture  — corpus hits for the names verify_citations.py declares
  C. sniffed extra     — corpus hits the sniffed variant would ADD over B, split
                         into (resolves to a real file) and (prose lookalike)

Reading C is the answer to "有无误吞": every hit in C that is not a real file is
a string the sniffed variant would have started treating as an anchor.

    python3 data/r11a/probes/extless_name_census.py [baseline_repo] [--no-exclude]
"""
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
_pos = [a for a in sys.argv[1:] if not a.startswith("-")]
REPO = Path(_pos[0] if _pos else "/home/user/hermes-agent")
sys.path.insert(0, str(STUDY / "scripts"))

# Measurement pollution (H-R10B-b, generalised from H-R9D-e): a probe that scans
# the corpus is polluted by the round that writes the probe up — this round's
# report quotes `Dockerfile:12` and `.gitignore:3` as examples, and the census
# then counts its own prose. Exclude by PREFIX, not by a hand-kept name list:
# R10B's first draft of such a list already missed one of its own files.
PREFIXES = ("r11a-", "round-11a-")
RAW = "--no-exclude" in sys.argv


def corpus():
    for d in ("chapters", "notes", "reports", "reviews"):
        for f in sorted((STUDY / d).glob("*.md")):
            if RAW or not f.name.startswith(PREFIXES):
                yield f


def baseline_extless_names() -> set:
    """Basenames at 863e313 that carry no extension.

    `.gitignore` counts as extensionless: the leading dot is not a suffix
    separator. `foo.bar` does not.
    """
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,
                         text=True, check=True).stdout.split("\n")
    names = set()
    for p in out:
        if not p:
            continue
        n = p.rsplit("/", 1)[-1]
        stem = n[1:] if n.startswith(".") else n
        if "." not in stem:
            names.add(n)
    return names


def token_re(names):
    """`(dir/)*NAME:digits` for NAME in *names*, longest-first."""
    alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(
        r"(?<![A-Za-z0-9_./-])"
        r"((?:\.?[A-Za-z0-9_][A-Za-z0-9_.-]*/)*(?:" + alt + r"))"
        r":(\d+)(?![0-9])"
    )


def main() -> None:
    from verify_citations import CITE  # noqa: E402

    try:
        from verify_citations import EXTLESS_NAMES as DECLARED
    except ImportError:
        DECLARED = set()  # probe predates the fix; reading B is then empty

    sniffed = baseline_extless_names()
    print(f"baseline repo: {REPO}")
    print(f"corpus excludes: {'(none, --no-exclude)' if RAW else PREFIXES}")
    print()
    print(f"A. baseline extensionless basenames: {len(sniffed)}")
    for n in sorted(sniffed):
        print(f"     {n}")
    print()
    print(f"   declared by verify_citations.py: {len(DECLARED)}")

    # Names the sniffed variant would add over the declared list.
    extra = sniffed - set(DECLARED)
    print(f"   sniffed-only names (would be ADDED): {len(extra)}")
    print()

    def scan(names, label):
        if not names:
            print(f"{label}: (no names)")
            return Counter(), Counter()
        rx = token_re(names)
        real, prose = Counter(), Counter()
        where = defaultdict(set)
        for f in corpus():
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                for m in rx.finditer(line):
                    path = m.group(1)
                    if CITE.search(m.group(0)):
                        continue  # already an extension-carrying anchor
                    where[path].add(f.name)
                    if (REPO / path).is_file() or (STUDY / path).is_file():
                        real[path] += 1
                    else:
                        prose[path] += 1
        print(f"{label}")
        print(f"  resolves to a real file  ({sum(real.values())} occurrences, "
              f"{len(real)} paths):")
        for p, n in sorted(real.items()):
            w = sorted(where[p])
            print(f"     x{n:<4} {p}   in: "
                  f"{', '.join(w) if len(w) <= 3 else str(len(w)) + ' 个文件'}")
        print(f"  does NOT resolve — prose lookalike ({sum(prose.values())} "
              f"occurrences, {len(prose)} paths):")
        for p, n in sorted(prose.items(), key=lambda kv: -kv[1]):
            w = sorted(where[p])
            print(f"     x{n:<4} {p}   in: "
                  f"{', '.join(w) if len(w) <= 3 else str(len(w)) + ' 个文件'}")
        print()
        return real, prose

    scan(DECLARED, "B. DECLARED list capture")
    _, prose = scan(extra, "C. SNIFFED-ONLY extra (what declaring keeps out)")
    print(f"VERDICT: sniffing would add {sum(prose.values())} non-anchor "
          f"occurrences across {len(prose)} distinct tokens.")


if __name__ == "__main__":
    main()
