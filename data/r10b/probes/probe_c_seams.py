#!/usr/bin/env python3
"""R10B slice C probe: enumerate the outward seams of the settings /
billing / profiles / gateway-hooks / apps-shared slice.

Seams enumerated (each is a closed list, not a sample):
  1. REST/bridge helpers imported from '@/hermes'
  2. Electron main-process bridge calls  window.hermesDesktop.<x>
  3. Gateway JSON-RPC methods (requestGateway / gateway.request / api.ts literals)
  4. nanostores atoms + actions imported from '@/store/*'
  5. URL query params read/written (useRouteEnumParam / useSearchParams / deep links)
  6. @hermes/shared imports

Usage: python3 data/r10b/probes/probe_c_seams.py /home/user/hermes-agent
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

repo = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")
study = Path(__file__).resolve().parents[3]
files = [l.strip() for l in (study / "data/r10b/slices/C.txt").read_text().splitlines() if l.strip()]

hermes_api = defaultdict(list)
bridge = defaultdict(list)
rpc = defaultdict(list)
stores = defaultdict(list)
params = defaultdict(list)
shared = defaultdict(list)

IMPORT_RE = re.compile(r"import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+'([^']+)'", re.S)

for rel in files:
    p = repo / rel
    if not p.exists() or p.suffix not in {".ts", ".tsx"}:
        continue
    txt = p.read_text()
    for m in IMPORT_RE.finditer(txt):
        names = [n.strip().replace("type ", "") for n in m.group(1).split(",") if n.strip()]
        src = m.group(2)
        line = txt[: m.start()].count("\n") + 1
        if src == "@/hermes":
            for n in names:
                hermes_api[n].append(f"{rel}:{line}")
        elif src.startswith("@/store/"):
            for n in names:
                stores[f"{src} :: {n}"].append(f"{rel}:{line}")
        elif src.startswith("@hermes/shared"):
            for n in names:
                shared[f"{src} :: {n}"].append(f"{rel}:{line}")
    for m in re.finditer(r"window\.hermesDesktop(\??\.[A-Za-z_$][\w$]*)+", txt):
        line = txt[: m.start()].count("\n") + 1
        bridge[m.group(0).replace("?.", ".")].append(f"{rel}:{line}")
    for m in re.finditer(r"(?:requestGateway|gateway\.request)<[^>]*>\(\s*'([^']+)'|requestGateway\(\s*'([^']+)'", txt):
        line = txt[: m.start()].count("\n") + 1
        rpc[(m.group(1) or m.group(2))].append(f"{rel}:{line}")
    for m in re.finditer(r"callBilling<[^>]*>\(requestGateway,\s*'([^']+)'", txt):
        line = txt[: m.start()].count("\n") + 1
        rpc[m.group(1)].append(f"{rel}:{line}")
    for m in re.finditer(r"gateway\?\.on<[^>]*>\('([^']+)'", txt):
        line = txt[: m.start()].count("\n") + 1
        rpc["(event) " + m.group(1)].append(f"{rel}:{line}")
    for m in re.finditer(r"useRouteEnumParam<?[^>]*>?\(\s*'([^']+)'", txt):
        line = txt[: m.start()].count("\n") + 1
        params[m.group(1)].append(f"{rel}:{line}")
    for m in re.finditer(r"(?:searchParams|params)\.get\('([^']+)'\)|param:\s*'([^']+)'", txt):
        line = txt[: m.start()].count("\n") + 1
        params[(m.group(1) or m.group(2))].append(f"{rel}:{line}")

def dump(title, d):
    print(f"\n=== {title} ({len(d)}) ===")
    for k in sorted(d):
        print(f"  {k:<52} {'; '.join(sorted(set(d[k])))}")

dump("1. @/hermes REST helpers", hermes_api)
dump("2. window.hermesDesktop.* bridge calls", bridge)
dump("3. gateway JSON-RPC methods / events", rpc)
dump("4. @/store/* atoms + actions", stores)
dump("5. URL query params", params)
dump("6. @hermes/shared imports", shared)
