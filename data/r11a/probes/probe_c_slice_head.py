#!/usr/bin/env python3
"""Dump a compact head of every file in the R11A slice-C manifest.

Purpose: slice C is an **L3** slice (知悉用途) over 118 near-isomorphic short
documents. The reader needs "what is it / who reads it" per file, not a line
read. This probe prints, per file: the YAML frontmatter `name`/`description`
(for SKILL.md / DESCRIPTION.md), or the first non-empty comment/def line
(for scripts), so one pass produces the per-file one-liners.

    python3 data/r11a/probes/probe_c_slice_head.py [--baseline /home/user/hermes-agent]
"""
import re
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
SLICE = STUDY / "data" / "r11a" / "slices" / "slice-L3-calibration.tsv"
BASE = Path("/home/user/hermes-agent")
for i, a in enumerate(sys.argv):
    if a == "--baseline" and i + 1 < len(sys.argv):
        BASE = Path(sys.argv[i + 1])


def frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    m = re.search(r"\n---\s*\n", text[3:])
    if not m:
        return {}
    out = {}
    for line in text[3:m.start() + 3].splitlines():
        mm = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if mm:
            out[mm.group(1)] = mm.group(2).strip().strip("'\"")
    return out


def main() -> None:
    rows = SLICE.read_text(encoding="utf-8").splitlines()[1:]
    for raw in rows:
        path, lines, _sd = raw.split("\t")
        p = BASE / path
        if not p.exists():
            print(f"{path}\tMISSING")
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:  # pragma: no cover
            print(f"{path}\tERR {e}")
            continue
        fm = frontmatter(text)
        if fm:
            keys = ",".join(fm.keys())
            print(f"{path}\t[{lines}L]\tFM({keys})\tname={fm.get('name','-')}\t"
                  f"desc={(fm.get('description','-') or '-')[:150]}")
        else:
            head = ""
            for ln in text.splitlines():
                if ln.strip():
                    head = ln.strip()[:150]
                    break
            print(f"{path}\t[{lines}L]\tNO-FM\t{head}")


if __name__ == "__main__":
    main()
