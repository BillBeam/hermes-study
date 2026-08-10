#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11C 片 A · 撞号的「结清覆盖面」队列:哪个实体被处置语盖到了,哪个没有。

`a-id-collisions-audit.py` 把「铸号位」与「处置位」摆在同一张表上,但它不回答
本片任务二那一句:**这条处置语是冲着同号里的哪一个实体说的?**

`H-R10B-a` 的形态就是答案为「都不是」:R11A 那句「结清」点的是
`scripts/verify_citations.py`,而同号另外两个实体的锚点分别在 `tui_gateway/`
与 `apps/desktop/`,处置语一个字都没提到它们 —— 于是两条真欠账随号消失。

本探针给每个 (案号, 实体) 打一个**队列标签**,不打结论:

    NO-RULING   该号全语料无 STRONG 处置语 —— 谁都没结,不存在「随号消失」
    COVERED     有 STRONG 处置语点名了该实体(锚点路径 / 铸号文件 / 同文件邻近)
    REVIEW      该号有 STRONG 处置语,但没有一条点名该实体
                ←—— H-R10B-a 的形态。**要人去读,不自动判**

CLAUDE.md(R11C 定):「机械判据不得用词根去判开/闭这类语义 …… 判开闭是人的事,
普查的事是别让任何一条从眼前消失。」所以 REVIEW 是队列不是判决,
输出里连同点名失败的处置语原文一起打出来,让人当场看见语境。

判「点名」的三条路径(都要求是**声明式**证据,不做同义词嗅探):

    1. 处置语所在行含该实体任一锚点的**完整路径**(如 `tui_gateway/methods_session.py`);
    2. 处置语所在文件 == 该实体的某个铸号文件,且行距 ≤ RULING_NEAR 行
       (移交表里「铸号行 + 处置列」常常就是同一行或紧邻几行);
    3. 处置语所在行含该实体某个铸号文件的**文件名主干**(如 `r10b-raw-capability-panels`)
       —— 定案表常写成「详见 notes/rXX-…」。

用法(仓库任意位置):

    python3 data/r11c/a-id-collisions-coverage.py                 # 汇总 + REVIEW 队列
    python3 data/r11c/a-id-collisions-coverage.py --tsv           # 明细 TSV
    python3 data/r11c/a-id-collisions-coverage.py --include-self  # 不剔除 r11c-*
    python3 data/r11c/a-id-collisions-coverage.py --summary       # 只打三行汇总
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys

RULING_NEAR = 3  # 同文件内,处置语与铸号行的最大行距

# 「普查文件」显式名单(R11C 片 A 定,--no-census 用)。
#
# 这两份是**讨论撞号这件事本身**的文件,不是对底层案子的处置。它们在正文里逐字
# 复述了 `H-R10B-a` 两个未处置实体的锚点,于是本探针的「点名」判据会把它们记成
# COVERED —— 而 R11B 在同一份文件里写的是「这两条至今没有任何一轮处置过」。
#
# 这正是 CLAUDE.md 说的「搜过没有类测量对『报告它』这个动作不幂等」:写一份点名
# 清单就会改变下一次的读数。名单是**声明式**的(两个文件名写死),不做「看起来像
# 普查」的嗅探;两个读数都报,谁也不当唯一真值。
CENSUS_FILES = frozenset({
    "notes/r11b-raw-rulings-census.md",
    "reports/round-11b-review-and-reconciliation.md",
})


def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=here,
                          capture_output=True, text=True, check=True).stdout.strip()


ROOT = repo_root()

# 铸号判据与处置语判据都从 R11C 片 A 的审计探针 import,不复制。
# 复制一份就会有第二套判据,而本片报的数必须与它报的 39/100 严格可比。
_SPEC = importlib.util.spec_from_file_location(
    "r11c_a_audit", os.path.join(ROOT, "data", "r11c", "a-id-collisions-audit.py"))
_A = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_A)
_MOD = _A._MOD  # R11B 的铸号探针


def stem(rel: str) -> str:
    return os.path.splitext(os.path.basename(rel))[0]


def collisions(include_self: bool):
    _MOD.CORPUS_REV = _A.CORPUS_REV
    _MOD.EXCLUDE_PREFIX = () if include_self else ("r11c-",)
    sites = _MOD.mint_sites()
    out = {}
    for cid, per in sites.items():
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
            out[cid] = groups
    return out


def label(group, strongs):
    """(标签, 命中该实体的处置语列表)。strongs 是该号的全部 STRONG 处置位。"""
    if not strongs:
        return "NO-RULING", []
    anchors = group["files"]
    mints = {(r[0], r[1]) for r in group["recs"]}          # (文件, 行号)
    mint_files = {r[0] for r in group["recs"]}
    mint_stems = {stem(f) for f in mint_files}
    named = []
    for kind, rel, ln, word, txt in strongs:
        if any(a in txt for a in anchors):
            named.append(("锚点路径", rel, ln, word, txt))
            continue
        if any(rel == mf and abs(ln - mln) <= RULING_NEAR for mf, mln in mints):
            named.append(("同文件邻近", rel, ln, word, txt))
            continue
        if any(s in txt for s in mint_stems):
            named.append(("点名铸号文件", rel, ln, word, txt))
    return ("COVERED" if named else "REVIEW"), named


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--include-self", action="store_true")
    ap.add_argument("--no-census", action="store_true",
                    help="处置语扫描剔除 CENSUS_FILES(讨论撞号本身的两份文件)")
    ap.add_argument("--show", default="REVIEW",
                    help="打印哪一档的明细:REVIEW(默认)/ COVERED / NO-RULING / ALL")
    args = ap.parse_args()

    collide = collisions(args.include_self)
    corpus = {rel: _MOD.corpus_read(rel).split("\n") for rel in _MOD.corpus_files()}
    vcorpus = {k: v for k, v in corpus.items() if not (args.no_census and k in CENSUS_FILES)}
    verdicts = _A.scan_verdicts(set(collide), vcorpus)

    rows = []
    for cid, groups in sorted(collide.items()):
        strongs = [v for v in verdicts.get(cid, []) if v[0] == "STRONG"]
        for gi, g in enumerate(groups, 1):
            tag, named = label(g, strongs)
            rows.append((cid, gi, len(groups), tag, g, named, strongs))

    n = {t: sum(1 for r in rows if r[3] == t) for t in ("NO-RULING", "COVERED", "REVIEW")}
    print(f"# 语料 {_A.CORPUS_REV[:12]} / {len(corpus)} 份"
          f"  剔除前缀 {_MOD.EXCLUDE_PREFIX or '(无)'}"
          f"  处置语语料 {len(vcorpus)} 份{' (--no-census)' if args.no_census else ''}")
    print(f"# 撞号 {len(collide)} 号 / {len(rows)} 实体")
    print(f"# 实体标签  NO-RULING={n['NO-RULING']}  COVERED={n['COVERED']}  REVIEW={n['REVIEW']}")
    if args.summary:
        return 0

    if args.tsv:
        print("cid\tentity\tentities\ttag\tmint_sites\tanchor_files\tnamed_by")
        for cid, gi, tot, tag, g, named, _s in rows:
            print("%s\t%d\t%d\t%s\t%s\t%s\t%s" % (
                cid, gi, tot, tag,
                ";".join(f"{r[0]}:{r[1]}" for r in g["recs"]),
                ";".join(sorted(g["files"])),
                ";".join(f"{k}@{r}:{l}" for k, r, l, _w, _t in named) or "-"))
        return 0

    for cid, gi, tot, tag, g, named, strongs in rows:
        if args.show != "ALL" and tag != args.show:
            continue
        print(f"\n== {cid} 实体 {gi}/{tot}  [{tag}]")
        for rel, ln, fs, txt in g["recs"]:
            print(f"   铸 {rel}:{ln}  锚={','.join(sorted(fs))[:70]}")
            print(f"      {txt[:150]}")
        if tag == "COVERED":
            print(f"   点名本实体的处置语 {len(named)} 条:")
            for k, rel, ln, word, txt in named[:6]:
                print(f"      [{k}] {rel}:{ln} [{word}] {txt[:130]}")
        elif tag == "REVIEW":
            print(f"   该号 STRONG 处置语 {len(strongs)} 条,无一条点名本实体:")
            for _k, rel, ln, word, txt in strongs[:6]:
                print(f"      {rel}:{ln} [{word}] {txt[:130]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
