#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11C 片 A · 100 个撞号实体的逐条台账(机械分档 + 人工定档)。

前三个探针各回答一面:
    `-audit.py`     铸号位与处置位摆在一起
    `-coverage.py`  处置语点没点名这个实体(NO-RULING / COVERED / REVIEW)
    `-orphans.py`   这个实体的锚点串此后还有没有人提过(0 == 再无人提)

本脚本把三面合成一张**逐实体台账**,给每个实体一个档位。档位分两类:

  机械档(判据写死在 RULES 里,可重跑):
    SHAPE-CONFUSION 铸号文本里案号带 ▲/■/◇/◎ 前缀 —— 那是片内定案号不是移交号
    NO-CLOSURE      剔除普查文件后该号无任何 STRONG 处置语 —— 没有"结清"可供误读
    SELF-RULED      处置语就落在该实体自己的铸号行/邻近 —— 该行自带处置
    NAMED           处置语点名了本实体的锚点或铸号文件
    CANDIDATE       有真处置语、未点名本实体、锚点此后无人再提 —— 隐形欠账候选

  人工档(HAND 字典,逐条写在底稿 §5,机械判据够不到的语义):
    FALSE-POSITIVE  该"铸号位"其实是交叉引用,不是独立铸号
    HIDDEN-DEBT     确认的隐形欠账
    DECLARED        该轮主线报告显式声明"片内移交留在各片底稿",在册但分散

**机械档不下开闭结论**(CLAUDE.md R11C:判开闭是人的事)。CANDIDATE 是队列,
底稿 §5 逐条读完后写进 HAND 覆盖它。

    python3 data/r11c/a-id-collisions-verdicts.py            # TSV 到 stdout
    python3 data/r11c/a-id-collisions-verdicts.py --counts   # 只打档位计数
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
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

SHAPE = re.compile(r"[▲■◇◎]\s*-?\s*H-\d")

# 人工定档,逐条理由写在 notes/r11c-raw-id-collisions.md §5。键是 (案号, 实体序号)。
HAND = {
    # §4.1 逐条读正文核实的交叉引用(R11B 点名 4 个,本片另发现第 5 个 H-7 2/4)
    ("H-17", 2): "FALSE-POSITIVE", ("H-R8D-e", 1): "FALSE-POSITIVE",
    ("H-R9A-g", 2): "FALSE-POSITIVE", ("H-R8C-f", 1): "FALSE-POSITIVE",
    ("H-7", 2): "FALSE-POSITIVE",
    # §5.2 R8D 片底稿 provider-identity 的 7 条:该轮主线移交表用的是 H-R8D-a…j,
    # 这 7 条一条都没进去,报告也没有"片内移交留在底稿"的声明。
    ("H-1", 3): "HIDDEN-DEBT", ("H-2", 3): "HIDDEN-DEBT", ("H-3", 3): "HIDDEN-DEBT",
    ("H-4", 2): "HIDDEN-DEBT", ("H-5", 2): "HIDDEN-DEBT", ("H-6", 1): "HIDDEN-DEBT",
    ("H-7", 3): "HIDDEN-DEBT",
}

# §5.3:主线报告显式声明"片内移交留在各片底稿,不在本表重复"的轮次。
# 这些轮次的片内移交号即使撞号,也**在册**(分散存放),不是"随号消失"。
DECLARED_ROUNDS = {
    "notes/r9a-": "reports/round-9a-capability-organization.md:334",
    "notes/r9b-": "reports/round-9b-multimodal-delivery.md:464",
    "notes/r9d-": "reports/round-9a-capability-organization.md:334",
    "notes/r10-": "reports/round-10-client-interface-layer.md:531",
    "notes/r10b-": "reports/round-10b-desktop-application.md:709",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", action="store_true")
    args = ap.parse_args()

    collide = _C.collisions(include_self=False)
    corpus = {rel: _MOD.corpus_read(rel) for rel in _MOD.corpus_files()}
    lines = {k: v.split("\n") for k, v in corpus.items()}
    vd = _A.scan_verdicts(set(collide), lines)
    vd_nc = _A.scan_verdicts(set(collide),
                             {k: v for k, v in lines.items() if k not in _C.CENSUS_FILES})

    rows = []
    for cid, groups in sorted(collide.items()):
        s_all = [v for v in vd.get(cid, []) if v[0] == "STRONG"]
        s_nc = [v for v in vd_nc.get(cid, []) if v[0] == "STRONG"]
        for gi, g in enumerate(groups, 1):
            tag, named = _C.label(g, s_all)
            tag_nc, _ = _C.label(g, s_nc)
            mint_files = sorted({r[0] for r in g["recs"]})
            toks = set()
            for rel, ln, _fs, txt in g["recs"]:
                for m in _MOD.RE_ANCHOR.finditer(txt):
                    toks.add(m.group(0))
            orphan = ("n/a" if not toks else
                      str(sum(corpus[o].count(t) for o in corpus
                              if o not in set(mint_files) for t in toks)))

            if any(SHAPE.search(r[3]) for r in g["recs"]):
                verdict, why = "SHAPE-CONFUSION", "铸号文本里是片内定案号(▲/■/◇/◎-H-N)"
            elif tag_nc == "NO-RULING":
                verdict, why = "NO-CLOSURE", "剔除普查文件后该号无 STRONG 处置语"
            elif tag == "COVERED" and any(k == "同文件邻近" for k, *_ in named):
                verdict, why = "SELF-RULED", "处置语落在本实体自己的铸号行/邻近"
            elif tag == "COVERED":
                verdict, why = "NAMED", "处置语点名了本实体的锚点或铸号文件"
            elif orphan == "0":
                verdict, why = "CANDIDATE", "有真处置语但未点名本实体,且锚点此后无人再提"
            else:
                verdict, why = "REVIEWED", "有真处置语未点名本实体,但锚点此后仍被提及"

            hand = HAND.get((cid, gi))
            if hand is None:
                for pfx, src in DECLARED_ROUNDS.items():
                    if verdict == "CANDIDATE" and any(f.startswith(pfx) for f in mint_files):
                        hand, why = "DECLARED", f"该轮主线声明片内移交留在底稿({src})"
                        break
            rows.append((cid, gi, len(groups), hand or verdict, why, tag, tag_nc,
                         orphan, ";".join(mint_files), ";".join(sorted(g["files"]))))

    if args.counts:
        import collections
        for k, v in sorted(collections.Counter(r[3] for r in rows).items(),
                           key=lambda kv: -kv[1]):
            print(f"{k:16s} {v:3d}")
        print(f"{'合计':16s} {len(rows):3d}")
        return 0

    print("cid\tentity\tentities\tverdict\twhy\ttag\ttag_no_census\torphan_hits\tmint_files\tanchor_files")
    for r in rows:
        print("\t".join(str(x) for x in r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
