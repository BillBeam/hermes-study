#!/usr/bin/env python3
"""R10B slice H probe: enumerate every contribution AREA of the desktop app.

An "area" is the string key `contrib/registry.ts` buckets contributions by; it is
the desktop's plugin mounting-point identifier. This script does not guess: it
(a) resolves every `*_AREA` / `*_AREAS` constant from its definition site,
(b) collects every bare area string literal passed to `registry.getArea(...)`,
    `useContributions(...)` or `area:` in a `registry.register*` call,
(c) expands the two template-literal consumers (`statusBar.${side}`,
    `titleBar.tools.${side}`) whose `side` type is `'left' | 'right'`,
and reports, per area, whether the plugin SDK (`src/sdk/index.ts`) exports a
name for it.

Usage: python3 probe_h_areas.py [/home/user/hermes-agent]
"""
import re
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")
src = root / "apps/desktop/src"

# (a) constants, read from their definition sites
const_defs = {}
for path in src.rglob("*.ts"):
    text = path.read_text()
    # object form: `export const X_AREAS = { k: 'v', ... } as const` (may span lines)
    for m in re.finditer(r"export const ([A-Z_]+_AREAS?)\s*=\s*\{(.*?)\}", text, re.S):
        const_defs[m.group(1)] = dict(re.findall(r"(\w+):\s*'([^']+)'", m.group(2)))
    # scalar form: `export const X_AREA = 'v'`
    for m in re.finditer(r"export const ([A-Z_]+_AREAS?)\s*=\s*'([^']+)'", text):
        const_defs[m.group(1)] = m.group(2)

areas = {}


def add(area, where):
    areas.setdefault(area, set()).add(where)


for name, val in const_defs.items():
    if isinstance(val, dict):
        for key, area in val.items():
            add(area, f"{name}.{key}")
    else:
        add(val, name)

# (b) bare literals reaching the registry
LIT = re.compile(r"(?:getArea|useContributions)\('([^']+)'\)|area:\s*'([^']+)'")
for path in list(src.rglob("*.ts")) + list(src.rglob("*.tsx")):
    if ".test." in path.name:
        continue
    for m in LIT.finditer(path.read_text()):
        area = m.group(1) or m.group(2)
        add(area, str(path.relative_to(src)))

# (c) the two `${side}` template consumers; `side: 'left' | 'right'`
for tmpl in ("statusBar", "titleBar.tools"):
    for side in ("left", "right"):
        add(f"{tmpl}.{side}", "app/contrib/panes.tsx (${side})")

sdk = (src / "sdk/index.ts").read_text()
sdk_named = {a for a in areas if a in sdk or any(
    n.split(".")[0] in sdk and isinstance(const_defs.get(n.split(".")[0]), (str, dict))
    for n in areas[a] if n.isupper() or "_AREA" in n)}

print(f"{len(areas)} contribution areas\n")
for area in sorted(areas):
    mark = "sdk" if area in sdk_named else "NOT-IN-SDK"
    print(f"{mark:<11} {area:<26} {sorted(areas[area])[0]}")
print(f"\nnot exported by src/sdk/index.ts: "
      f"{sorted(a for a in areas if a not in sdk_named)}")
