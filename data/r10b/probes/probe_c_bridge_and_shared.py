#!/usr/bin/env python3
"""R10B slice C probe (2/2).

A) Full Electron-bridge surface used by slice C — catches both the direct
   `window.hermesDesktop.x` form and the aliased `const desktop = window.hermesDesktop`
   form the gateway hooks / gateway-settings use.
B) Repo-wide consumer map of the `@hermes/shared` package (who imports which
   subpath) — the package has 5 declared subpath exports in
   apps/shared/package.json; this shows which are actually consumed and by whom.

Usage: python3 data/r10b/probes/probe_c_bridge_and_shared.py /home/user/hermes-agent
"""
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

repo = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")
study = Path(__file__).resolve().parents[3]
files = [l.strip() for l in (study / "data/r10b/slices/C.txt").read_text().splitlines() if l.strip()]

# --- A) bridge surface --------------------------------------------------
bridge = defaultdict(set)
ALIAS = re.compile(r"(?:const|let)\s+(\w+)\s*=\s*window\.hermesDesktop\b")

for rel in files:
    p = repo / rel
    if not p.exists() or p.suffix not in {".ts", ".tsx"}:
        continue
    txt = p.read_text()
    aliases = {"window.hermesDesktop"} | {m.group(1) for m in ALIAS.finditer(txt)}
    for alias in aliases:
        pat = re.compile(re.escape(alias) + r"(?:\?)?\.([A-Za-z_$][\w$]*)(?:(?:\?)?\.([A-Za-z_$][\w$]*))?")
        for m in pat.finditer(txt):
            if alias != "window.hermesDesktop" and m.group(1) in {"current"}:
                continue
            name = m.group(1)
            # second hop only for known namespace objects
            if m.group(2) and name in {"cloud", "themes", "settings", "profile", "uninstall"}:
                name = f"{name}.{m.group(2)}"
            line = txt[: m.start()].count("\n") + 1
            bridge[name].add(f"{rel}:{line}")

print(f"=== A) Electron bridge (window.hermesDesktop.*) used by slice C: {len(bridge)} members ===")
for k in sorted(bridge):
    sites = sorted(bridge[k])
    print(f"  {k:<32} x{len(sites):<3} {sites[0]}")

# --- B) @hermes/shared consumer map ------------------------------------
out = subprocess.run(
    ["git", "grep", "-n", "-E", r"from '@hermes/shared", "--", "apps", "tui", "*.ts", "*.tsx"],
    cwd=repo, capture_output=True, text=True,
).stdout
subpaths = defaultdict(set)
for line in out.splitlines():
    path, _, rest = line.partition(":")
    m = re.search(r"from '(@hermes/shared[^']*)'", rest)
    if m:
        subpaths[m.group(1)].add(path)

print(f"\n=== B) @hermes/shared subpath consumers (declared exports: 5) ===")
for sp in sorted(subpaths):
    print(f"  {sp:<34} {len(subpaths[sp])} files")
    for f in sorted(subpaths[sp]):
        print(f"      {f}")
