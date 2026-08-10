#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11B 片 A · A-2「后轮覆盖前轮已证伪结论」普查(口径见底稿 §3)。

两步:
  (1) `--reversals` 建**已证伪断言库**:扫全语料的改判语,取该行的锚点与案号,
      记下「哪一轮、把什么判为不成立」。
  (2) `--recur`    对库里每一条,在**更晚轮次**的产出里找同一锚点(同文件、行号 ±窗口),
      列出候选;是否真的「把已证伪的说法重新写成结论」由人裁决。

搜索面(写死在代码里,报告要照抄):
  * 文件:`reports/*.md` + `notes/*.md` + `chapters/*.md`,共 266 份;排除 `reviews/`
    (评审报告评的是本学习仓库的产出,不是对基线的定案)与 `data/`、`scripts/`。
  * 改判语模式:见 REVERSAL 列表(逐条是一个中文正则),**只在围栏块外的行**上匹配。
  * 排除:围栏代码块内的行;`## 勘误` 节内的行**不排除**(勘误正是改判的载体之一)。
  * 轮次序:ORDER 常量给出全项目轮次的时间序,用于判定「后轮」。
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
# 本普查的语料面截止到 R11A:R11B 的 notes/ 是本轮各片**正在写**的文件,是移动靶,
# 纳入会让报出的数不可复现。排除规则单列在这里,便于日后有意放开。
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


ORDER = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R7B", "R7C", "R8A", "R8FIX",
         "R8B", "R8C", "R8D", "R9A", "R9B", "R9C", "R9D", "R10", "R10B", "R11A", "R11B"]
RANK = {r: i for i, r in enumerate(ORDER)}

# 改判语分两档。强档 = 明说「前面那个说法不成立」;弱档 = 修正/缩小但未否定。
# 逐条都在语料里真实出现过(用 --reversals --grep <词> 可逐词回看)。
REVERSAL_STRONG = [
    r"证伪", r"推翻", r"改判", r"撤销", r"作废", r"收回", r"不成立",
    r"不足以", r"原判", r"驳回", r"重开", r"堵不住",
]
REVERSAL_WEAK = [
    r"收窄", r"关闭并改述", r"是错的", r"判错", r"误判", r"更正", r"改述",
]
RE_REV = re.compile("|".join(REVERSAL_STRONG))
RE_REV_WEAK = re.compile("|".join(REVERSAL_STRONG + REVERSAL_WEAK))

CITE_EXTS = "py|mdx|md|yaml|yml|toml|c|h|sh|json|tsx|ts|mjs|js|nix|rs|txt"
RE_ANCHOR = re.compile(r"(?<![\w/.-])(\.?[\w][\w./+-]*\.(?:%s)):(\d+)" % CITE_EXTS)
RE_H = re.compile(r"H-(?:R\d+[A-Z]*|\d+[A-Z]*)(?:-[A-Za-z0-9]+)*")
RE_G = re.compile(r"[▲◇■◎]-R\d+[A-Z]*-[0-9A-Za-z]+")

RE_ROUND_REPORT = re.compile(r"round-([0-9]+[a-z]*(?:-fix)?)-")
RE_ROUND_NOTE = re.compile(r"^(r[0-9]+[a-z]*)-")


def round_of(rel: str) -> str:
    b = os.path.basename(rel)
    m = RE_ROUND_REPORT.match(b)
    if m:
        return "R" + m.group(1).upper().replace("-FIX", "FIX")
    m = RE_ROUND_NOTE.match(b)
    return m.group(1).upper() if m else "?"


def files():
    return corpus_files()


_ex: dict[str, bool] = {}


def exists(p: str) -> bool:
    if p not in _ex:
        _ex[p] = os.path.exists(os.path.join(BASELINE, p))
    return _ex[p]


def scan():
    """返回 (reversals, anchor_index)。

    reversals: [dict(file,line,round,text,anchors,cases)]  —— 命中改判语的行
    anchor_index: (基线文件) -> [(行号, 产出文件, 产出行, 轮次, 原文)]
    """
    reversals = []
    anchor_index = collections.defaultdict(list)
    for rel in files():
        rnd = round_of(rel)
        lines = corpus_read(rel).split("\n")
        fence = False
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                fence = not fence
                continue
            if fence:
                continue
            anchors = [(m.group(1), int(m.group(2)))
                       for m in RE_ANCHOR.finditer(line) if exists(m.group(1))]
            for p, n in anchors:
                anchor_index[p].append((n, rel, i + 1, rnd, line.strip()[:150]))
            weak = bool(RE_REV_WEAK.search(line))
            if weak:
                ctx = "\n".join(lines[max(0, i - 2):i + 3])
                ca = [(m.group(1), int(m.group(2)))
                      for m in RE_ANCHOR.finditer(ctx) if exists(m.group(1))]
                reversals.append(dict(file=rel, line=i + 1, round=rnd,
                                      text=line.strip()[:180],
                                      anchors=sorted(set(ca)),
                                      strong=bool(RE_REV.search(line)),
                                      cases=sorted(set(RE_H.findall(ctx) + RE_G.findall(ctx)))))
    return reversals, anchor_index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reversals", action="store_true")
    ap.add_argument("--recur", action="store_true")
    ap.add_argument("--ledger", action="store_true",
                    help="只取**定案级**改判行(表格行/标题行 + 带案号或记号)")
    ap.add_argument("--casepass", action="store_true",
                    help="A-2 案号法:定案级改判行的案号在更晚轮次的再出现")
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--grep", default=None, help="只看命中该词的改判语")
    args = ap.parse_args()

    revs, idx = scan()

    if args.ledger or args.casepass:
        # 定案级改判行 = 表格行或标题行(散文里的「证伪」多半在讲被测代码,不是在改判本项目的定案)
        led = []
        for rel in files():
            rnd = round_of(rel)
            lines = corpus_read(rel).split("\n")
            fence = False
            for i, line in enumerate(lines):
                s = line.strip()
                if s.startswith("```"):
                    fence = not fence
                    continue
                if fence:
                    continue
                if not ((s.startswith("|") and s.count("|") >= 3) or s.startswith("#")):
                    continue
                if not RE_REV.search(s):
                    continue
                ids = sorted(set(RE_H.findall(s) + RE_G.findall(s)))
                if not (ids or re.search(r"[▲◇■◎]", s)):
                    continue
                led.append((rel, i + 1, rnd, ids, s[:120]))
        if args.ledger:
            print(f"# 定案级改判行:{len(led)};其中带案号的 {sum(1 for x in led if x[3])}")
            if args.detail:
                for rel, ln, rnd, ids, txt in led:
                    print(f"{rel}:{ln} [{rnd}] {','.join(ids) or '-'} {txt}")
            return
        # --casepass:同案号在更晚轮次的再出现
        cidx = collections.defaultdict(list)
        for rel in files():
            rnd = round_of(rel)
            for i, line in enumerate(corpus_read(rel).split("\n")):
                for cid in set(RE_H.findall(line) + RE_G.findall(line)):
                    cidx[cid].append((rnd, rel, i + 1, line.strip()[:130]))
        n = 0
        out = []
        for rel, ln, rnd, ids, txt in led:
            if not ids:
                continue
            later = [(cid, r2, f2, l2, t2) for cid in ids
                     for (r2, f2, l2, t2) in cidx[cid]
                     if RANK.get(r2, -1) > RANK.get(rnd, 99) and f2 != rel]
            if later:
                n += 1
                out.append((rel, ln, rnd, ids, txt, later))
        print(f"# 定案级改判行 {len(led)};带案号 {sum(1 for x in led if x[3])};"
              f"其中案号在更晚轮次再出现的 {n}")
        if args.detail:
            for rel, ln, rnd, ids, txt, later in out:
                print(f"\n== [{rnd}] {rel}:{ln} 案号={','.join(ids)}\n   {txt}")
                for cid, r2, f2, l2, t2 in later:
                    print(f"   -> [{r2}] {f2}:{l2} ({cid}) {t2[:110]}")
        return

    if args.reversals:
        per = collections.Counter(r["round"] for r in revs)
        ps = collections.Counter(r["round"] for r in revs if r["strong"])
        n_s = sum(1 for r in revs if r["strong"])
        print(f"# 语料 {len(list(files()))} 份(排除 r11b-*);改判语命中行 强档 {n_s} / 强+弱 {len(revs)}")
        for r in ORDER:
            if per[r]:
                print(f"   {r:6s} 强 {ps[r]:4d}  强+弱 {per[r]:4d}")
        if args.grep:
            for r in revs:
                if args.grep in r["text"]:
                    print(f"{r['file']}:{r['line']} [{r['round']}] {r['text']}")
        return

    if args.recur:
        # 只看「带锚点的改判语」——没有锚点就无法机械地找它的后续复现
        withanchor = [r for r in revs if r["anchors"] and r["strong"]]
        print(f"# 带锚点的**强档**改判语行:{len(withanchor)} / 强档 {sum(1 for r in revs if r['strong'])}")
        hits = []
        for r in withanchor:
            later = []
            for p, n in r["anchors"]:
                for (n2, rel2, ln2, rnd2, txt2) in idx[p]:
                    if abs(n2 - n) > args.window:
                        continue
                    if RANK.get(rnd2, -1) <= RANK.get(r["round"], 99):
                        continue
                    if rel2 == r["file"]:
                        continue
                    later.append((p, n, rel2, ln2, rnd2, txt2))
            if later:
                hits.append((r, later))
        print(f"# 其中在更晚轮次的**别的产出文件**里又提到同一锚点(±{args.window} 行)的:{len(hits)}")
        for r, later in hits:
            print(f"\n== [{r['round']}] {r['file']}:{r['line']}  案号={','.join(r['cases']) or '-'}")
            print(f"   改判语: {r['text'][:150]}")
            seen = set()
            for p, n, rel2, ln2, rnd2, txt2 in later:
                if (rel2, ln2) in seen:
                    continue
                seen.add((rel2, ln2))
                print(f"   -> [{rnd2}] {rel2}:{ln2}  ({p}:{n})")
                print(f"      {txt2[:140]}")
        return

    print("用 --reversals 或 --recur")


if __name__ == "__main__":
    sys.exit(main())
