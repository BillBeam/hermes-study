#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11C 片 A · 撞号的「同类后果」审计:某处铸号被标结清,同号另一处从未处置。

R11B 的 `data/r11b/probes/rulings_id_collisions.py` 只回答「哪些号撞了」
(39 号 / 100 实体)。它**不回答**本片要问的那一句:

    这个号在语料里被人写过「结清 / 关闭 / 证伪 / 改判」吗?
    如果写过,那句话是冲着**哪一个实体**说的?同号的其它实体呢?

`H-R10B-a` 就是这样活下来的:R11A 写「结清」,冲的是 `scripts/` 那一处,
而 `tui_gateway/` 与 `apps/desktop/` 那两处从此不会再被任何人翻出来。

本探针把两件事拼到一张表上:

    A. 铸号位(复用 R11B 的判据,单一来源,数字必然一致)
    B. 处置位 —— 全语料里**同一行内**同时出现该案号与处置语的行

判定语分两档,理由见 VERDICT_WORDS 的注释。**探针只负责把两者摆在一起,
不自动判「谁结清了谁」** —— 那要读两边的正文,是人的活。表里给的是
「该号有几个实体、有几处处置语、处置语落在哪个文件」,供逐条人工裁决。

用法(在本仓库任意位置):

    python3 data/r11c/a-id-collisions-audit.py              # 汇总三行
    python3 data/r11c/a-id-collisions-audit.py --tsv        # 明细 TSV(给 data/)
    python3 data/r11c/a-id-collisions-audit.py --detail     # 人读的逐号明细
    python3 data/r11c/a-id-collisions-audit.py --include-self  # 不剔除 r11c-*

语料快照钉在 R11C 派工那一条 commit 上(`CORPUS_REV`),与 R11B 同理:
片 C / 片 D 与本片**并发**改历史 `notes/`,从工作区读会让本底稿报出的每个数
随它们的进度漂移,而「shell 命令即证据」关卡要在它们改完之后才重跑。
"""
from __future__ import annotations

import argparse
import collections
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

# R11C 批次二派发那一条 commit(`8d6bac6`)。用固定 rev 而不是工作区:见模块 docstring。
# 批次二重派时从 4b215e8 上调到这里:3f9f6ee 改正了六处历史锚点漂移,
# 从旧 rev 读会让本底稿引用的行号与工作区对不上,而引用关卡是按工作区解析的。
CORPUS_REV = os.environ.get("R11C_CORPUS_REV", "8d6bac6")

# 铸号判据单一来源:直接加载 R11B 的探针,不复制它的正则与切分规则。
# 复制一份就会有第二套判据,而本片报的数必须与 R11B 报的 39/100 严格可比。
_SPEC = importlib.util.spec_from_file_location(
    "r11b_id_collisions",
    os.path.join(ROOT, "data", "r11b", "probes", "rulings_id_collisions.py"),
)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", ROOT, *args],
                          capture_output=True, text=True, check=True).stdout


# 处置语。分两档是因为它们的证据力不同:
#   STRONG —— 作者宣告这条案子有了终局(结清/关闭/证伪/改判/升格/撤销)。
#             这一档才可能造成 H-R10B-a 那种「一句话盖住三个实体」的后果。
#   WEAK   —— 作者宣告这条案子**还活着**(续转/维持/待判/未处置)。
#             它不会造成误判为已结,但读者会拿它当「有人管过」,所以一并列出。
STRONG_WORDS = ["结清", "关闭", "已结", "证伪", "改判", "升格", "撤销", "作废", "定案", "不成立"]
WEAK_WORDS = ["续转", "维持", "待判", "未处置", "移交", "去向"]


def scan_verdicts(cids: set[str], corpus: dict[str, list[str]]):
    """cid -> [(档位, 文件, 行号, 命中的词, 整行)]。判据:同一行内同时出现案号与处置语。"""
    out = collections.defaultdict(list)
    # 长号优先,避免 `H-1` 在 `H-17` 的行上假命中。
    ordered = sorted(cids, key=len, reverse=True)
    for rel, lines in corpus.items():
        for i, line in enumerate(lines):
            if "H-" not in line:
                continue
            for cid in ordered:
                # 右边界守卫:`H-1` 不得命中 `H-17` / `H-1a`。
                if not re.search(re.escape(cid) + r"(?![\w-])", line):
                    continue
                strong = [w for w in STRONG_WORDS if w in line]
                weak = [w for w in WEAK_WORDS if w in line]
                if strong:
                    out[cid].append(("STRONG", rel, i + 1, "/".join(strong), line.strip()[:220]))
                elif weak:
                    out[cid].append(("WEAK", rel, i + 1, "/".join(weak), line.strip()[:220]))
                break   # 一行只归给最长的那个号
    return out


# 从一条铸号行里抠出「这条案子讲的是哪个符号」。
#
# 不用「锚点后紧跟的反引号」那条 R9B 配对规则:那条规则要求作者写了声明式锚点,
# 而这里要处理的恰恰是 R8A–R10B 的历史铸号行,大多数没这么写。
# 改为:取该行**所有**反引号片段,剔掉其中是锚点/纯路径的,再从余下片段里挑
# 判别力最高的标识符(含 `_` 或 `.` 或驼峰,长度 ≥6)。挑不出就退回锚点路径。
_RE_TICKS = re.compile(r"`([^`\n]{2,160})`")
_RE_IS_ANCHOR = re.compile(r"^[\w./+-]+\.\w+(:\d+(-\d+)?)?$")
_RE_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{5,}")


def entity_token(text: str, anchors: set[str]) -> tuple[str, str]:
    """(用来搜的 token, token 来源)。token 越独特,负结论的搜索面越有意义。"""
    cands: list[str] = []
    for span in _RE_TICKS.findall(text):
        span = span.strip()
        if _RE_IS_ANCHOR.match(span):
            continue                      # 这是锚点或纯路径,不是「案子讲的符号」
        for ident in _RE_IDENT.findall(span):
            if ident.endswith((".py", ".ts", ".tsx", ".md", ".js", ".json", ".yaml")):
                continue
            if "_" in ident or "." in ident or re.search(r"[a-z][A-Z]", ident):
                cands.append(ident)
    if cands:
        return max(cands, key=len), "摘录符号"
    if anchors:
        return sorted(anchors)[0], "锚点路径(该行无可用摘录符号)"
    return "", "无"


def followup(collide, corpus) -> None:
    """逐实体报「这个符号在别的产出文件里还被提过几次」。

    **它不判定「处置过没有」** —— 那要读正文。它只把负结论的搜索面机械化:
    命中 0 就是「除铸号处外全语料零提及」,这条负结论可重跑;命中 >0 给出文件名单,
    人去读那几处。
    """
    print("kind\tcid\tentity\tmint\ttoken\ttoken_src\thits_outside\twhere")
    for cid, groups in sorted(collide.items()):
        for gi, g in enumerate(groups, 1):
            rel, ln, fs, txt = g["recs"][0]
            tok, src = entity_token(txt, fs)
            mint_files = {r[0] for r in g["recs"]}
            hits = []
            if tok:
                for other, lines in corpus.items():
                    if other in mint_files:
                        continue
                    n = sum(1 for line in lines if tok in line)
                    if n:
                        hits.append(f"{other}:{n}")
            print("ENT\t%s\t%d\t%s:%d\t%s\t%s\t%d\t%s"
                  % (cid, gi, rel, ln, tok, src,
                     sum(int(h.rsplit(":", 1)[1]) for h in hits),
                     ",".join(sorted(hits)[:6]) or "-"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", action="store_true")
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--followup", action="store_true",
                    help="逐实体机械化负结论搜索面:该实体的符号在铸号文件之外的提及数")
    ap.add_argument("--include-self", action="store_true",
                    help="不剔除本片自己的 r11c-* 产出(测量污染对照读数)")
    args = ap.parse_args()

    _MOD.CORPUS_REV = CORPUS_REV
    _MOD.EXCLUDE_PREFIX = () if args.include_self else ("r11c-",)

    sites = _MOD.mint_sites()

    collide = {}
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
            collide[cid] = groups

    corpus = {rel: _MOD.corpus_read(rel).split("\n") for rel in _MOD.corpus_files()}
    verdicts = scan_verdicts(set(collide), corpus)

    n_strong = sum(1 for c in collide if any(v[0] == "STRONG" for v in verdicts.get(c, [])))
    print(f"# 语料快照 : {CORPUS_REV[:12]}  文件 {len(corpus)} 份"
          f"  剔除前缀 {_MOD.EXCLUDE_PREFIX or '(无)'}")
    print(f"# 撞号     : {len(collide)} 号 / {sum(len(g) for g in collide.values())} 实体")
    print(f"# 带处置语 : {n_strong} 号出现过 STRONG 处置语(结清/关闭/证伪/改判/…)")

    if args.followup:
        followup(collide, corpus)
        return 0

    if args.tsv:
        print("\tcid\tentities\tentity_idx\tmint_file\tmint_line\tanchor_files\tmint_text")
        for cid, groups in sorted(collide.items()):
            for gi, g in enumerate(groups, 1):
                for rel, ln, fs, txt in g["recs"]:
                    print("MINT\t%s\t%d\t%d\t%s\t%d\t%s\t%s"
                          % (cid, len(groups), gi, rel, ln,
                             ",".join(sorted(fs)), txt.replace("\t", " ")[:200]))
            for kind, rel, ln, word, txt in verdicts.get(cid, []):
                print("VERDICT-%s\t%s\t%d\t-\t%s\t%d\t%s\t%s"
                      % (kind, cid, len(groups), rel, ln, word,
                         txt.replace("\t", " ")[:200]))
        return 0

    if args.detail:
        for cid, groups in sorted(collide.items()):
            vs = verdicts.get(cid, [])
            print(f"\n== {cid}  {len(groups)} 实体  "
                  f"STRONG={sum(1 for v in vs if v[0] == 'STRONG')} "
                  f"WEAK={sum(1 for v in vs if v[0] == 'WEAK')}")
            for gi, g in enumerate(groups, 1):
                for rel, ln, fs, txt in g["recs"]:
                    print(f"  铸({gi}) {rel}:{ln}  锚={','.join(sorted(fs))[:70]}")
            for kind, rel, ln, word, txt in vs:
                print(f"  {kind:7s} {rel}:{ln}  [{word}]  {txt[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
