#!/usr/bin/env python3
"""R10B slice H probe: enumerate every ⌘K command-palette ROW registered through
the contribution registry (`PALETTE_AREA`).

Two registration shapes exist and both are collected:
  1. `{ id, area: PALETTE_AREA, data: { id, label, ... } satisfies PaletteContribution }`
  2. `paletteToggle({ id, label, ... })`  (helper in app/command-palette/contrib.ts
     that returns shape 1 with detail/keepOpen filled in)

The palette ALSO renders ~10 statically-built groups (Go to / Projects / Command
center / Appearance / Settings / type-to-search lists) that never touch the
registry — those are NOT registry contributions and are not counted here.

Usage: python3 probe_h_palette.py [/home/user/hermes-agent]
"""
import re
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")
src = root / "apps/desktop/src"

rows = []
for path in sorted(list(src.rglob("*.ts")) + list(src.rglob("*.tsx"))):
    if ".test." in path.name:
        continue
    text = path.read_text()
    rel = str(path.relative_to(src))
    for m in re.finditer(r"area: PALETTE_AREA,\s*\n\s*data: \{(.*?)\n\s*\}", text, re.S):
        body = m.group(1)
        cid = re.search(r"id: '([^']+)'", body)
        label = re.search(r"label: (?:'([^']+)'|([^\n,]+))", body)
        if cid:
            rows.append((cid.group(1), (label.group(1) or label.group(2)).strip() if label else "", rel))
    for m in re.finditer(r"paletteToggle\(\{(.*?)\n\s*\}\)", text, re.S):
        body = m.group(1)
        cid = re.search(r"id: '([^']+)'", body)
        label = re.search(r"label: '([^']+)'", body)
        if cid:
            rows.append((cid.group(1), label.group(1) if label else "", rel + " (paletteToggle)"))

print(f"{len(rows)} PALETTE_AREA contributions\n")
for cid, label, where in sorted(rows):
    print(f"{cid:<26} {label:<34} {where}")
