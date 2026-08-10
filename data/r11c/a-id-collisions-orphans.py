#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11C 片 A · 撞号实体的「此后再无人提起」机械化:锚点串在铸号文件之外的命中数。

`a-id-collisions-coverage.py` 回答「处置语有没有点名这个实体」。它有个盲区:
处置**可以不提案号**——后一轮完全可能直接按锚点接着做,只是没写「结清 H-x」。
把那种情况判成欠账,就是负结论错了会关闭调查的反面:**误报一条欠账**。

本探针补的就是这一面,判据尽量硬:

    取该实体每个铸号行里的**完整锚点串**(`路径:行号`,逐字,含行号),
    在全语料里搜这个串,**排除该实体自己的铸号文件**。

命中 0 == 「除了铸号处,全语料再没有任何文件写过这个 `路径:行号`」。
这是一条**可重跑的负结论**,搜索面就是它自己(语料 = 快照里 reports/ notes/ chapters/
的全部 .md;排除面 = 该实体的铸号文件本身,以及 `--exclude-census` 时的两份普查文件)。

**它证明不了「这个案子没被处置」** —— 后一轮可能换了个行号写、可能只提符号名。
所以它的输出是**排序用的信号**,不是判决:命中 0 的排在最前面,人先读那些。

    python3 data/r11c/a-id-collisions-orphans.py             # 全部实体,按命中数升序
    python3 data/r11c/a-id-collisions-orphans.py --zero      # 只列命中 0 的
    python3 data/r11c/a-id-collisions-orphans.py --cid H-1   # 只看一个号
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys


def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=here,
                          capture_output=True, text=True, check=True).stdout.strip()


ROOT = repo_root()
_SPEC = importlib.util.spec_from_file_location(
    "r11c_a_cov", os.path.join(ROOT, "data", "r11c", "a-id-collisions-coverage.py"))
_C = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_C)
_A, _MOD = _C._A, _C._MOD


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zero", action="store_true")
    ap.add_argument("--cid")
    ap.add_argument("--exclude-census", action="store_true")
    args = ap.parse_args()

    collide = _C.collisions(include_self=False)
    corpus = {rel: _MOD.corpus_read(rel) for rel in _MOD.corpus_files()}
    if args.exclude_census:
        corpus = {k: v for k, v in corpus.items() if k not in _C.CENSUS_FILES}

    rows = []
    for cid, groups in sorted(collide.items()):
        if args.cid and cid != args.cid:
            continue
        for gi, g in enumerate(groups, 1):
            mint_files = {r[0] for r in g["recs"]}
            # 铸号行里的完整锚点串(逐字,含行号)
            toks = set()
            for rel, ln, _fs, txt in g["recs"]:
                for m in _MOD.RE_ANCHOR.finditer(txt):
                    toks.add(m.group(0))
            hits = []
            for other, text in corpus.items():
                if other in mint_files:
                    continue
                n = sum(text.count(t) for t in toks)
                if n:
                    hits.append(f"{other}:{n}")
            rows.append((sum(int(h.rsplit(':', 1)[1]) for h in hits), cid, gi,
                         len(groups), sorted(toks), sorted(mint_files), hits))

    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    zero = sum(1 for r in rows if r[0] == 0)
    print(f"# 实体 {len(rows)} 个,其中锚点串在铸号文件之外命中 0 的:{zero}"
          f"{'  (--exclude-census)' if args.exclude_census else ''}")
    for n, cid, gi, tot, toks, mints, hits in rows:
        if args.zero and n:
            continue
        print(f"{n:4d}  {cid} {gi}/{tot}  铸={','.join(mints)[:70]}")
        print(f"      锚点串={' '.join(toks)[:110]}")
        if hits:
            print(f"      命中={','.join(sorted(hits))[:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
