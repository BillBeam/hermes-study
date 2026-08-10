#!/usr/bin/env python3
"""从铸号行**机械生成**处置表的 markdown 行,避免手抄锚点。

移交表的锚点漂一行,下一轮就直接找错地方(CLAUDE.md 移交项格式那条的理由)。
本轮片 C 要给 100 多条案子各写一个声明式锚点,**手抄就是在制造那种漂移**。
所以锚点一律从铸号行里**原样切**:取该行第一个形如
``` `路径:行号`:`原文` ``` 或 ``` `路径:行号` 的 `符号` ``` 的片段,整段照搬。

    python3 data/r11d/probes/handover_rowgen_r11d.py --prefix H-R9D- --disposition "转 …"

输出是 markdown 表格行,直接贴进底稿。
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(subprocess.run(
    ["git", "-C", str(pathlib.Path(__file__).resolve().parent),
     "rev-parse", "--show-toplevel"],
    capture_output=True, check=True).stdout.decode().strip())
TSV = ROOT / "data" / "r11d" / "handover-open-rows.tsv"

# 「锚点 + 紧跟的反引号摘录」——与 verify_citations.py 认的是同一个形状。
PAIR = re.compile(
    r"`[^`]*?[A-Za-z0-9_./-]+\.[A-Za-z0-9]+:\d+[^`]*`(?:\s*(?::|的)\s*`[^`]*`)?")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="")
    ap.add_argument("--ids", default="", help="逗号分隔的案号白名单")
    ap.add_argument("--disposition", default="转(见组级理由)")
    args = ap.parse_args()

    want = {s.strip() for s in args.ids.split(",") if s.strip()}
    for raw in TSV.read_text(encoding="utf-8").splitlines():
        parts = raw.split("\t")
        if len(parts) < 5:
            continue
        hid, src, lineno, _second, row = parts[0], parts[1], parts[2], parts[3], parts[4]
        if args.prefix and not hid.startswith(args.prefix):
            continue
        if want and hid not in want:
            continue
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        anchor = ""
        for c in cells[1:]:
            m = PAIR.search(c)
            if m:
                anchor = m.group(0)
                break
        # 一句话现象:取最长的非锚点单元格,截断到 88 字,去掉表格分隔符。
        phen = ""
        for c in cells[1:]:
            body = PAIR.sub("", c).strip(" ：:的—— ")
            if len(body) > len(phen):
                phen = body
        phen = phen.replace("|", "/")[:88]
        print(f"| `{hid}` | {phen} | {anchor or '(铸号行内无声明式锚点)'} "
              f"| {args.disposition} | 铸于 `{src}:{lineno}` |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
