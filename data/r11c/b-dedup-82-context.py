#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11C 片 B · 为 92 簇里每一个「声明位」导出正文上下文,供逐簇人工裁决。

    python3 data/r11c/b-dedup-82-context.py           # 全部唯一声明位 + 上下文
    python3 data/r11c/b-dedup-82-context.py --cluster C17

去重口径:同一个 (产出文件, 行号, 案号) 只导一次(它会同时出现在多个簇里)。
上下文:声明行前 1 行、后 N 行(默认 9),每行截断到 200 字符;不解析、不判断,只是把正文摆出来。
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys

# 派工书硬约束 6:探针会把它读到的东西带进仓库。语料里有历史底稿写下的会话专属
# scratchpad 路径(R11B 的 H-R9D-f 就是这条),原样转录等于把它们又抄一遍。
# 生成明细前就地抹除,**在写盘之前**,而不是事后 sed —— 事后 sed 会漏掉重跑。
_SCRUB = re.compile(r"/tmp/claude-\d+/[^\s`)\]]*")


def scrub(text: str) -> str:
    return _SCRUB.sub("<会话路径已抹除>", text)

def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=here,
                          capture_output=True, text=True, check=True).stdout.strip()

ROOT = repo_root()
_s = importlib.util.spec_from_file_location(
    "b_index", os.path.join(ROOT, "data", "r11c", "b-dedup-82-index.py"))
BI = importlib.util.module_from_spec(_s)
_s.loader.exec_module(BI)
RC = BI.RC


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", type=int, default=9)
    ap.add_argument("--cluster")
    args = ap.parse_args()

    decls = BI.collect_with_provenance()
    full = BI.cluster(decls, use_own_only=False)

    want = {}
    for idx, (nc, nr, p, grp) in enumerate(full, 1):
        cid_lbl = f"C{idx:02d}"
        if args.cluster and cid_lbl != args.cluster:
            continue
        for n, key, d in grp:
            want.setdefault((d["file"], d["line"], d["cid"]), []).append(cid_lbl)

    cache: dict[str, list[str]] = {}
    for (rel, ln, cid), clusters in sorted(want.items()):
        if rel not in cache:
            cache[rel] = RC.corpus_read(rel).split("\n")
        lines = cache[rel]
        i = ln - 1
        print(f"\n### {rel}:{ln}  [{cid}]  簇={','.join(sorted(set(clusters)))}")
        for j in range(max(0, i - 1), min(len(lines), i + 1 + args.after)):
            mark = ">>" if j == i else "  "
            print(f"{mark}{j+1:6d}| {scrub(lines[j])[:200]}")


if __name__ == "__main__":
    sys.exit(main())
