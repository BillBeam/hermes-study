#!/usr/bin/env python3
"""H-R10-a measurement: what does widening verify_citations.py's extension
whitelist actually capture, and does it swallow anything that is not an anchor?

Run from the study repo root:
    python3 data/r10b/probes/cite_ext_scan.py /home/user/hermes-agent
"""
import re, sys, collections
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]  # data/r10b/probes/x.py -> repo root
REPO = Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-")
            else "/home/user/hermes-agent")

# The pre-R10B whitelist, frozen here as the baseline of the comparison.
OLD = "py|md|yaml|yml|toml|c|sh|json|ts|tsx|js"
# The current one is imported from the gate itself, so this probe can never
# drift from what the gate actually enforces (the first draft of this probe
# hard-coded it, measured a list the gate no longer used, and under-reported
# `.mdx`/`.txt` to zero).
sys.path.insert(0, str(STUDY / "scripts"))
from verify_citations import CITE_EXTS as NEW  # noqa: E402

def cite(exts):
    return re.compile(
        r"(?P<path>[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:" + exts + r"))"
        r":(?P<start>\d+)(?:-(?P<end>\d+))?")

OLD_RE, NEW_RE = cite(OLD), cite(NEW)
# Anything shaped like `token:number` whose token ends in a dotted suffix --
# the superset both regexes are carved out of. Used to find what a NAIVE
# widening (`\.\w+`) would have swallowed.
ANY_RE = re.compile(r"(?P<path>[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?P<ext>[A-Za-z0-9]{1,6})):(?P<start>\d+)")

FENCE = re.compile(r"^\s*```")

# Measurement pollution, same family as named_coverage.py's (H-R9D-e): this
# probe scans notes/ and reports/, and the round that WRITES UP the probe puts
# `sqlite.org:443`, `127.0.0.1:18789` etc. into those very files as examples.
# The host:port census then counts the write-up's own prose. So the write-up
# must be excludable, and both readings reported. Default excludes are the two
# R10B artifacts that discuss the gate; pass --exclude to add more, --no-exclude
# for the raw reading.
# Exclude this round's own write-up by PREFIX, not by a name list: a list has
# to be remembered, and the very first draft of it already missed
# notes/r10b-90-handover-rulings.md (which quotes `sqlite.org:443` from the
# handover item it is ruling on, and so inflated the host:port census by 1).
# Same failure mode as the hand-maintained report list in R10's handover census.
EXCLUDE_PREFIXES = ("r10b-", "round-10b-")
EXTRA_EXCLUDE = set()
for i, a in enumerate(sys.argv):
    if a == "--exclude" and i + 1 < len(sys.argv):
        EXTRA_EXCLUDE.add(sys.argv[i + 1])
NO_EXCLUDE = "--no-exclude" in sys.argv


def excluded(name: str) -> bool:
    if NO_EXCLUDE:
        return False
    return name in EXTRA_EXCLUDE or name.startswith(EXCLUDE_PREFIXES)


def corpus():
    for d in ("chapters", "notes", "reports", "reviews"):
        for f in sorted((STUDY / d).glob("*.md")):
            if not excluded(f.name):
                yield f

def resolve(p):
    t = REPO / p
    if not t.is_file() and (STUDY / p).is_file():
        t = STUDY / p
    return t

new_hits = collections.Counter()      # (ext, path) -> count
new_files = collections.defaultdict(set)
naive_extra = collections.Counter()   # ext -> count, matched by ANY but not by NEW
naive_examples = collections.defaultdict(set)

for f in corpus():
    for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
        for m in NEW_RE.finditer(ln):
            if OLD_RE.fullmatch(m.group(0)) or OLD_RE.search(m.group(0)):
                continue
            ext = m.group("path").rsplit(".", 1)[-1]
            new_hits[(ext, m.group("path"))] += 1
            new_files[(ext, m.group("path"))].add(f.name)
        for m in ANY_RE.finditer(ln):
            if NEW_RE.search(m.group(0)):
                continue
            ext = m.group("ext")
            naive_extra[ext] += 1
            if len(naive_examples[ext]) < 6:
                naive_examples[ext].add(m.group(0))

print("corpus excludes: " + ("(none, --no-exclude)" if NO_EXCLUDE else
      f"prefixes {EXCLUDE_PREFIXES} + {sorted(EXTRA_EXCLUDE) or []}"))
print("=" * 72)
print("A. Anchors NEWLY captured by the widened whitelist (h/mjs/nix/rs)")
print("=" * 72)
tot = 0
for (ext, path), n in sorted(new_hits.items(), key=lambda x: (x[0][0], x[0][1])):
    ok = "resolves" if resolve(path).is_file() else "UNRESOLVABLE"
    tot += n
    print(f"  .{ext:4s} x{n:<3d} {ok:12s} {path}")
    print(f"          in: {', '.join(sorted(new_files[(ext, path)]))}")
print(f"\n  newly captured anchor occurrences: {tot}   distinct paths: {len(new_hits)}")

print()
print("=" * 72)
print("B. What a NAIVE widening would ALSO have swallowed (still excluded)")
print("=" * 72)
for ext, n in sorted(naive_extra.items(), key=lambda x: -x[1]):
    ex = sorted(naive_examples[ext])
    res = [e for e in ex if resolve(e.rsplit(":", 1)[0]).is_file()]
    verdict = "REAL ANCHOR (resolves)" if res else "not a path"
    print(f"  .{ext:6s} x{n:<4d} {verdict:24s} e.g. {', '.join(ex[:4])}")
print(f"\n  total still-excluded token:number occurrences: {sum(naive_extra.values())}")

print()
print("=" * 72)
print("C. Every distinct still-excluded token, with resolvability")
print("=" * 72)
allnaive = collections.Counter()
for f in corpus():
    for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
        for m in ANY_RE.finditer(ln):
            if NEW_RE.search(m.group(0)):
                continue
            allnaive[m.group("path")] += 1
real, fake = 0, 0
for p, n in sorted(allnaive.items()):
    hit = resolve(p).is_file()
    real, fake = (real + n, fake) if hit else (real, fake + n)
    print(f"  {'RESOLVES    ' if hit else 'not-a-path  '} x{n:<3d} {p}")
print(f"  ---- still-excluded occurrences: {real + fake}"
      f"  (resolvable={real}, host:port-or-not-a-path={fake})")

print()
print("=" * 72)
print("D. Gate-scope count: anchors newly captured, per extension")
print("   (replicates verify_citations.py's two skip rules -- no scanning inside")
print("    fenced blocks or blockquotes -- so this is comparable to the gate's")
print("    own citations= delta, unlike section A which scans raw text.)")
print("=" * 72)
QUOTE = re.compile(r"^\s*>\s?")
def gate_lines(f):
    """Yield the lines verify_citations.py would actually scan for anchors."""
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    while i < len(lines):
        if FENCE.match(lines[i]):
            i += 1
            while i < len(lines) and not FENCE.match(lines[i]):
                i += 1
            i += 1
            continue
        if QUOTE.match(lines[i]):
            while i < len(lines) and QUOTE.match(lines[i]):
                i += 1
            continue
        yield lines[i]
        i += 1

TABLE = re.compile(r"^\s*\|.*\|")
per_ext = collections.Counter()
per_ext_tbl = collections.Counter()
for f in corpus():
    for ln in gate_lines(f):
        for m in NEW_RE.finditer(ln):
            if OLD_RE.search(m.group(0)):
                continue
            ext = m.group("path").rsplit(".", 1)[-1]
            (per_ext_tbl if TABLE.match(ln) else per_ext)[ext] += 1
print("  block-level (counts into `citations=`):")
for e, n in sorted(per_ext.items()):
    print(f"      .{e:4s} {n}")
print(f"      TOTAL {sum(per_ext.values())}")
print("  table-row (counts into `table_anchors=`):")
for e, n in sorted(per_ext_tbl.items()):
    print(f"      .{e:4s} {n}")
print(f"      TOTAL {sum(per_ext_tbl.values())}")
