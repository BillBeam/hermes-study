#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11C 片 B · 从底稿 §3 的逐簇裁决表机械清点四类裁决,防止正文里的数与表脱节。

    python3 data/r11c/b-dedup-82-tally.py

判据只看「裁决」那一格(第 4 列),优先级:不成簇 > 合并 > R11B 已覆盖 > 纯不合并。
**这是清点,不是判断** —— 判断在表里,本脚本只保证正文报的数与表对得上。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys


def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=here,
                          capture_output=True, text=True, check=True).stdout.strip()


def main():
    path = os.path.join(repo_root(), "notes", "r11c-raw-dedup-82.md")
    rows = [l for l in open(path, encoding="utf-8").read().split("\n")
            if re.match(r"^\| C\d\d \|", l)]
    cat = {"合并": 0, "纯不合并": 0, "R11B 已覆盖": 0, "不成簇": 0}
    for r in rows:
        v = r.split("|")[4]
        if "不成簇" in v:
            cat["不成簇"] += 1
        elif "合并 B-" in v:
            cat["合并"] += 1
        elif "M-" in v and "已覆盖" in v and "不合并" not in v:
            cat["R11B 已覆盖"] += 1
        else:
            cat["纯不合并"] += 1
    print(f"逐簇裁决表行数 {len(rows)}")
    for k in ("合并", "纯不合并", "R11B 已覆盖", "不成簇"):
        print(f"  {k}: {cat[k]}")
    print(f"  合计 {sum(cat.values())}")

    # §2 合并组表:号数 / 定案号 / 跨轮铸号(✔)/ 同轮铸号但跨轮结清(↦)
    grp = [l for l in open(path, encoding="utf-8").read().split("\n")
           if re.match(r"^\| \*\*B-\d\d\*\* \|", l)]
    ids = rul = cross = soft = 0
    for r in grp:
        c = [x.strip() for x in r.strip().strip("|").split("|")]
        ids += int(c[-5])
        rul += int(c[-4])
        cross += "\u2714" in c[-2]
        soft += "\u21a6" in c[-2]
    print(f"合并组表行数 {len(grp)}")
    print(f"  涉及案号 {ids};其中定案号 {rul}")
    print(f"  跨轮铸号 {cross};同轮铸号跨轮结清 {soft}")


if __name__ == "__main__":
    sys.exit(main())
