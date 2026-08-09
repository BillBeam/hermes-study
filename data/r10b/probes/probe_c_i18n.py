#!/usr/bin/env python3
"""R10B slice C probe: which slice-C .tsx files ship user-facing copy without
going through useI18n() / translateNow().

DESIGN.md:285 states "Every user-facing string goes through `useI18n()`".
This counts the violations mechanically. A "user-facing literal" is a quoted
string used as one of the copy-carrying props (title / label / description /
placeholder / aria-label / message / caption / emptyMessage / hint), OR a bare
JSX text node of >=2 word characters between tags.

Deliberately conservative: className/style/id/key/href/type/variant/size/name/
value/role/rel/target/data-* and single-word CSS-ish tokens are excluded, so the
count under-reports rather than over-reports.

Usage: python3 data/r10b/probes/probe_c_i18n.py /home/user/hermes-agent
"""
import re
import sys
from pathlib import Path

repo = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")
files = [l.strip() for l in (Path(__file__).resolve().parents[3] / "data/r10b/slices/C.txt").read_text().splitlines() if l.strip()]

COPY_PROPS = r"(?:title|label|description|placeholder|aria-label|message|caption|emptyMessage|hint|busyLabel|confirmLabel|doneLabel|clearLabel|consequence)"
PROP_RE = re.compile(COPY_PROPS + r"[=:]\s*[\"']([^\"'{}]{2,})[\"']")
JSXTEXT_RE = re.compile(r">\s*([A-Z][A-Za-z][^<>{}\n]{3,})\s*<")

total_files = 0
viol_files = 0
viol_lines = 0
rows = []

for rel in files:
    p = repo / rel
    if not p.exists() or p.suffix != ".tsx":
        continue
    total_files += 1
    txt = p.read_text()
    if "useI18n" in txt or "translateNow" in txt:
        continue
    hits = []
    for m in PROP_RE.finditer(txt):
        hits.append((txt[: m.start()].count("\n") + 1, m.group(1)))
    for m in JSXTEXT_RE.finditer(txt):
        s = m.group(1).strip()
        if " " in s or len(s) > 6:
            hits.append((txt[: m.start()].count("\n") + 1, s))
    if hits:
        viol_files += 1
        viol_lines += len(hits)
    rows.append((rel, len(hits), sorted(hits)[:3]))

print(f".tsx files in slice C            : {total_files}")
print(f"  without useI18n/translateNow   : {len(rows)}")
print(f"  ...and shipping literal copy   : {viol_files}   (total literal sites: {viol_lines})")
print()
for rel, n, sample in sorted(rows, key=lambda r: -r[1]):
    tag = "LITERAL COPY" if n else "no copy found"
    print(f"  {n:>3}  {tag:<14} {rel}")
    for ln, s in sample:
        print(f"        {rel}:{ln}  {s[:70]!r}")
