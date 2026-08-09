#!/usr/bin/env python3
"""R10B slice C probe: reconcile the desktop Settings config-key surface
against the R8A whole-repo config-key table (data/r8a-config-keys.tsv).

Sources
  A) SECTIONS[].keys in apps/desktop/src/app/settings/constants.ts
     (the curated desktop config surface, per-section)
  B) every other dotted config key the slice-C files write via setNested(...)
     / read via getNested(...)  -> collected by regex, reported separately
  C) data/r8a-config-keys.tsv  -> the 856-key baseline table

Usage:
  python3 data/r10b/probes/probe_c_config_keys.py /home/user/hermes-agent
"""
import csv
import re
import sys
from pathlib import Path

repo = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")
study = Path(__file__).resolve().parents[3]

consts = (repo / "apps/desktop/src/app/settings/constants.ts").read_text()

# --- A) SECTIONS[].keys -------------------------------------------------
body = consts.split("export const SECTIONS: DesktopConfigSection[] = [", 1)[1]
body = body.split("\nexport interface ModeOption", 1)[0]

sections = []
for m in re.finditer(r"id:\s*'([^']+)',\s*\n\s*label:\s*'([^']+)',\s*\n\s*icon:\s*\w+,\s*\n\s*keys:\s*(\[[^\]]*\])", body):
    sid, label, keyblob = m.group(1), m.group(2), m.group(3)
    keys = re.findall(r"'([^']+)'", keyblob)
    sections.append((sid, label, keys))

section_keys = [k for _, _, ks in sections for k in ks]

# --- B) other dotted keys touched by slice-C files ----------------------
slice_files = [
    l.strip() for l in (study / "data/r10b/slices/C.txt").read_text().splitlines() if l.strip()
]
extra = set()
for rel in slice_files:
    p = repo / rel
    if not p.exists():
        continue
    txt = p.read_text()
    for m in re.finditer(r"(?:setNested|getNested)\([^,]+,\s*'([a-z_]+(?:\.[a-z_0-9]+)+)'", txt):
        extra.add(m.group(1))
    # sessions-settings writes record.sessions.{auto_archive,auto_archive_days}
for k in ("sessions.auto_archive", "sessions.auto_archive_days"):
    extra.add(k)
extra -= set(section_keys)

# --- C) the R8A baseline table -----------------------------------------
r8a = {}
with (study / "data/r8a-config-keys.tsv").open(newline="") as fh:
    for row in csv.DictReader(fh, delimiter="\t"):
        r8a[row["key"].strip()] = row

def report(title, keys):
    known = [k for k in keys if k in r8a]
    unknown = [k for k in keys if k not in r8a]
    print(f"{title}: {len(keys)} keys | in r8a table: {len(known)} | NOT in r8a table: {len(unknown)}")
    for k in unknown:
        print(f"    MISSING-FROM-R8A  {k}")

print("== A) SECTIONS (constants.ts) ==")
for sid, label, keys in sections:
    print(f"  section {sid:<10} label={label:<16} keys={len(keys)}")
print(f"  TOTAL sections={len(sections)} keys={len(section_keys)} unique={len(set(section_keys))}")
report("  SECTIONS keys vs r8a", section_keys)

print()
print("== B) config keys written/read by slice-C files but NOT in SECTIONS ==")
for k in sorted(extra):
    mark = "in-r8a" if k in r8a else "MISSING-FROM-R8A"
    print(f"  {k:<40} {mark}")
report("  extra keys vs r8a", sorted(extra))

print()
print(f"== C) r8a table size: {len(r8a)} keys ==")
print(f"desktop-settings surface / whole-repo surface = "
      f"{len(set(section_keys) | extra)}/{len(r8a)}")
