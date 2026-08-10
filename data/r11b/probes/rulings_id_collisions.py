#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11B 片 A · A-1 第二物种:同一个移交号被多处独立「铸造」。

与 `rulings_census.py --species2` 的区别:那个按锚点文件是否相交推断实体,
会被「同一条移交项的结清写在另一个文件里」误判成两个实体。本探针只认
**铸号位**——一个移交号第一次带着自己的锚点被登记的地方——判据是:

    该行是表格行或加粗段首,案号在行首,且**同一行内**给出了锚点或引号摘录。

然后按「文件」聚类:同一个号如果在**两个不同产出文件**里各被这样登记过一次,
且两处给的锚点文件不同,就是一次撞号。这比锚点相交法保守,漏报优于误报。

    python3 data/r11b/probes/rulings_id_collisions.py           # 撞号清单
    python3 data/r11b/probes/rulings_id_collisions.py --all     # 含单处铸号的全表
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import subprocess
import sys


def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=here,
                          capture_output=True, text=True, check=True).stdout.strip()


ROOT = repo_root()
BASELINE = os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent")
DIRS = ["reports", "notes", "chapters"]
# 同 rulings_census.py:排除本轮正在写的 r11b-* 产出,保证报出的数可复现。
EXCLUDE_PREFIX = ("r11b-",)

# ---------------------------------------------------------------- 语料快照
# 语料固定在 R11B 派工那一条 commit 上,而不是工作区。
# 理由:R11B 的片 C(改 chapters/ 锚点排版)与片 D(改历史 notes/ 引用)与本片**并行**
# 在同一棵工作树上写文件;若从工作区读,本底稿报出的每一个数都会随它们的进度漂移,
# 而「shell 命令即证据」这条关卡要在它们改完之后才重跑。快照读法让重跑恒等。
CORPUS_REV = os.environ.get("R11B_CORPUS_REV", "00f09bfeebc09055070f5577c3d51271a48d2088")


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", ROOT, *args],
                          capture_output=True, text=True, check=True).stdout


def corpus_files():
    """快照里 reports/ notes/ chapters/ 下的 .md,排除本轮在写的 r11b-*。"""
    out = _git("ls-tree", "-r", "--name-only", CORPUS_REV)
    for path in sorted(out.split("\n")):
        if not path.endswith(".md"):
            continue
        d = path.split("/")[0]
        if d not in ("reports", "notes", "chapters"):
            continue
        if os.path.basename(path).startswith(EXCLUDE_PREFIX):
            continue
        yield path


def corpus_read(path: str) -> str:
    return _git("show", f"{CORPUS_REV}:{path}")


# 注意 `\d+[A-Z]*`:`H-9A-1`(R9A 的 MoA / skills-hub 两片各自铸的号)否则会被截成 `H-9`,
# 与 R8A 的主线移交号 H-9 假撞。
RE_H = re.compile(r"H-(?:R\d+[A-Z]*|\d+[A-Z]*)(?:-[A-Za-z0-9]+)*")
CITE_EXTS = "py|mdx|md|yaml|yml|toml|c|h|sh|json|tsx|ts|mjs|js|nix|rs|txt"
RE_ANCHOR = re.compile(r"(?<![\w/.-])(\.?[\w][\w./+-]*\.(?:%s)):(\d+)" % CITE_EXTS)

_ex: dict[str, bool] = {}


def exists(p: str) -> bool:
    if p not in _ex:
        _ex[p] = os.path.exists(os.path.join(BASELINE, p))
    return _ex[p]


def files():
    return corpus_files()


def mint_sites():
    """返回 cid -> {产出文件: [(行号, 锚点文件集, 原文)]}"""
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for rel in files():
        lines = corpus_read(rel).split("\n")
        fence = False
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith("```"):
                fence = not fence
                continue
            if fence or not s:
                continue
            head, span = None, 1
            if s.startswith("|"):
                cells = [c.strip() for c in s.strip("|").split("|")]
                head = cells[0] if cells else ""      # 表格行:锚点必须在同一行
            elif s.startswith("**") or s.startswith("- **") or s.startswith("* **"):
                head, span = s[:60], 3                # 加粗段首:`**H-x** ——` 后锚点常换行
            elif s.startswith("#"):
                head, span = s.lstrip("#").strip()[:60], 4   # 小节标题:锚点在标题下几行
            if not head:
                continue
            m = RE_H.search(head)
            if not m:
                continue
            scope = "\n".join(lines[i:i + span])
            anchors = {a.group(1) for a in RE_ANCHOR.finditer(scope) if exists(a.group(1))}
            if not anchors:
                continue
            out[m.group(0)][rel].append((i + 1, anchors, s[:150]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--detail", action="store_true",
                    help="逐条列出撞号明细;不给则只打三行汇总")
    args = ap.parse_args()
    sites = mint_sites()

    collide = {}
    for cid, per in sites.items():
        # 按锚点文件集把不同产出文件并成实体
        groups = []
        for rel, recs in per.items():
            fs = set().union(*[r[1] for r in recs])
            hit = [g for g in groups if g["files"] & fs]
            if hit:
                g0 = hit[0]
                for g in hit[1:]:
                    g0["files"] |= g["files"]
                    g0["recs"] += g["recs"]
                    groups.remove(g)
                g0["files"] |= fs
                g0["recs"] += [(rel,) + r for r in recs]
            else:
                groups.append(dict(files=set(fs), recs=[(rel,) + r for r in recs]))
        if len(groups) >= 2:
            collide[cid] = groups

    print(f"# 铸号位总数(带锚点的登记行):{sum(len(r) for p in sites.values() for r in p.values())}")
    print(f"# 有铸号位的移交号:{len(sites)}")
    print(f"# 被 ≥2 处独立铸造(锚点不相交)的移交号:{len(collide)},"
          f"共 {sum(len(g) for g in collide.values())} 个实体,"
          f"净多铸 {sum(len(g) for g in collide.values()) - len(collide)}")
    if not (args.detail or args.all):
        return
    for cid, groups in sorted(collide.items()):
        print(f"\n== {cid}  {len(groups)} 个实体")
        for gi, g in enumerate(groups, 1):
            for rec in g["recs"]:
                rel, ln, fs, txt = rec
                print(f"  ({gi}) {rel}:{ln}  锚={','.join(sorted(fs))[:60]}")
                print(f"      {txt[:130]}")
    if args.all:
        print("\n# 全表")
        for cid, per in sorted(sites.items()):
            print(cid, "->", ", ".join(f"{k}:{v[0][0]}" for k, v in per.items()))


if __name__ == "__main__":
    sys.exit(main())
