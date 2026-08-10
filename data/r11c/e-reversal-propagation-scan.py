#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11C 片 E · 改判传播型污染复查 —— 语料侧扫描器(口径见 notes/r11c-raw-reversal-propagation.md)。

与 R11B 的 `data/r11b/probes/rulings_reversal_scan.py` 的**口径差**(必须写出来,否则两个数
会被误当成同一个测量的两次读数):

  * **源面(找「哪些结论被改判过」的面)**:R11B = reports/ + notes/ + chapters/(排除 reviews/、
    data/、scripts/)。本片 = 上述三者 **+ `reviews/` + `CLAUDE.md` + `data/*/dispatch-brief.md`**。
    加 reviews/ 的理由:review-1 是全项目**最大的一次集中改判**(阻断 8 条 + 建议 23 条),
    R11B 把它排除在源面之外,于是它推翻的那些说法一条都没进过改判清单。
  * **目标面(找「改判有没有被后来的产出覆盖」的面)**:R11B 只查 reports/ + notes/;
    本片查 **chapters/ + 制度文件**(CLAUDE.md / 派工书 / 探针 docstring)。
  * **判据**:R11B 三条路径(改判语普查 / 案号法 / 特征短语法)全部围着**案号**转;
    成品章不写案号,案号法在那里天然零命中。本片对成品章另设两条判据,见 --phrases / --derived。

用法:
  python3 data/r11c/e-reversal-propagation-scan.py --surface     # 目标面清点(文件数/行数)
  python3 data/r11c/e-reversal-propagation-scan.py --ledger      # 源面的定案级改判行普查
  python3 data/r11c/e-reversal-propagation-scan.py --phrases     # 判据 1:短语法,对目标面
  python3 data/r11c/e-reversal-propagation-scan.py --phrases --keep-r11c   # 不剔除 r11c-*

语料**钉在一条 commit 上**而不是工作区:片 B / 片 C 与本片并发在同一棵工作树上改
历史 `notes/`,从工作区读会让本底稿报出的每个数随它们的进度漂移。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys


def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=here,
                          capture_output=True, text=True, check=True).stdout.strip()


ROOT = repo_root()
# R11C 片 E 开工时的分支 HEAD(片 A / 片 C / 片 F 已到货并已合入本分支)。
CORPUS_REV = os.environ.get("R11C_CORPUS_REV", "f440d7814a4528cb9782bc93d079eec7a0f8b127")


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", ROOT, *args],
                          capture_output=True, text=True, check=True).stdout


def tree_files() -> list[str]:
    return [p for p in _git("ls-tree", "-r", "--name-only", CORPUS_REV).split("\n") if p]


def read(path: str) -> str:
    return _git("show", f"{CORPUS_REV}:{path}")


# ------------------------------------------------------------------ 面的定义
def source_files() -> list[str]:
    """源面:从这里抽「已改判结论」。"""
    out = []
    for p in tree_files():
        if p == "CLAUDE.md":
            out.append(p)
        elif p.endswith(".md") and p.split("/")[0] in ("reports", "notes", "chapters", "reviews"):
            out.append(p)
        elif re.fullmatch(r"data/[^/]+/dispatch-brief\.md", p):
            out.append(p)
    return sorted(out)


def target_chapters() -> list[str]:
    return sorted(p for p in tree_files() if p.startswith("chapters/") and p.endswith(".md"))


def target_institutional() -> list[str]:
    out = []
    for p in tree_files():
        if p == "CLAUDE.md":
            out.append(p)
        elif re.fullmatch(r"data/[^/]+/dispatch-brief\.md", p):
            out.append(p)
        elif re.fullmatch(r"data/r[^/]*/probes/.*\.py", p) or re.fullmatch(r"data/r11c/[^/]*\.py", p):
            out.append(p)
        elif p.startswith("scripts/") and p.endswith(".py"):
            out.append(p)
    return sorted(out)


def is_r11c(path: str) -> bool:
    return os.path.basename(path).startswith("r11c-") or path.startswith("data/r11c/")


# ------------------------------------------------------------------ 改判语
REVERSAL_STRONG = [r"证伪", r"推翻", r"改判", r"撤销", r"作废", r"收回", r"不成立",
                   r"不足以", r"原判", r"驳回", r"重开", r"堵不住"]
REVERSAL_WEAK = [r"收窄", r"关闭并改述", r"是错的", r"判错", r"误判", r"更正", r"改述"]
RE_REV = re.compile("|".join(REVERSAL_STRONG))
RE_H = re.compile(r"H-(?:R\d+[A-Z]*|\d+[A-Z]*)(?:-[A-Za-z0-9]+)*")
RE_G = re.compile(r"[▲◇■◎]-R\d+[A-Z]*-[0-9A-Za-z]+")
RE_REVIEW_ID = re.compile(r"(?:阻断|建议)-\d+")


def ledger_lines():
    """定案级改判行 = 表格行 / 标题行 / 引用块首,且带案号或记号或评审编号。"""
    for rel in source_files():
        lines = read(rel).split("\n")
        fence = False
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith("```"):
                fence = not fence
                continue
            if fence:
                continue
            if not ((s.startswith("|") and s.count("|") >= 3) or s.startswith("#")
                    or s.startswith(">")):
                continue
            if not RE_REV.search(s):
                continue
            ids = sorted(set(RE_H.findall(s) + RE_G.findall(s) + RE_REVIEW_ID.findall(s)))
            if not (ids or re.search(r"[▲◇■◎]", s)):
                continue
            yield rel, i + 1, ids, s[:150]


# ------------------------------------------------------------------ 判据 1
# 「已改判结论」清单(逐条见底稿 §2)。每条给一个**不可替换短语**:
# 它必须是被推翻的那个说法特有的,而不是这个话题的通名。
# 字段:编号, 短语(正则), 说明
PHRASES: list[tuple[str, str, str]] = [
    ("E-01", r"关机即删|关机就删|停止即删",              "R4 证伪 tools.md「容器关机即删」"),
    ("E-02", r"20\+ 平台.{0,12}(低估|偏小).{0,6}▲|▲.{0,10}20\+ 平台", "R8-fix 把「20+ 平台」从 ▲ 改判为 ◎"),
    ("E-03", r"Tool Search.{0,20}(无文档|没有文档|文档缺失)", "R3 证伪「Tool Search 渐进披露无文档」"),
    ("E-04", r"静默消失|静默抹掉|静默地?(?:抹|删|丢)",     "R8C 推翻 ■-R8B-12 的「静默」定性"),
    ("E-05", r"没有第三个|不存在第三个",                  "R8B 重开 H-7:第三个落盘调用方确实存在"),
    ("E-06", r"PairingStore\(\).{0,40}▲|▲.{0,40}PairingStore", "R8C 撤销「profile 语义差异」的 ▲"),
    ("E-07", r"waitpid.{0,20}不主张|不主张.{0,20}waitpid", "R9D 推翻 R9A「waitpid 不主张」"),
    ("E-08", r"24 个平台束.{0,10}▲|平台族.{0,10}▲",        "R9D 把「24 个平台束」从 ▲ 改判为 ◇"),
    ("E-09", r"需(?:要)?起真实网关|必须起真实网关",        "R10B 推翻「H-R10-f 需起真实网关才能复现」"),
    ("E-10", r"抄了一份.{0,30}(STT|stt)|native_stt_available.{0,30}抄", "R9C 改述 H-R9B-a 的病因"),
    ("E-11", r"目前无害",                                  "R8B 收回 ▲-10「目前无害」一半"),
    ("E-12", r"后果更轻",                                  "R9A 推翻 H-R8D-c「后果更轻」的前提"),
    ("E-13", r"比对配置的 connector host|正确的?比较值.{0,20}_base_url.{0,20}(就在|即可)",
     "R9C 证伪「只比对 host/_base_url 即可修好」(种子案)"),
    ("E-14", r"忙时.{0,12}不(?:往下|向下)送|忙时.{0,8}不下发",  "review-1 阻断-1:r7 把忙时投递写反"),
    ("E-15", r"26 万行|260,?000 行",                        "review-1 阻断-3:仓库规模写成 26 万行"),
    ("E-16", r"有基类默认桩|default stubs in base.{0,30}▲",  "review-1 阻断-4:r7b ▲4 挂错文档小节"),
    ("E-17", r"三家都与实现不符|三家.{0,10}都不符",          "review-1 阻断-5:hooks 声明「三家不符」"),
    ("E-18", r"container_persistent.{0,30}persist_across_processes.{0,20}(同一|同个)",
     "review-1 阻断-6:r4 把两个开关当同一个"),
    ("E-19", r"17 个 ContextVar",                          "review-1 建议-6:实为 18"),
    ("E-20", r"加载器只读 description|只读 description",    "review-1 建议-12:不成立"),
    ("E-21", r"五个读取函数|5 个读取函数",                  "review-1 建议-9:r8a 说五个,r8b 更正为六个"),
    ("E-22", r"读超时.{0,20}(?:60|300) 秒(?:$|[^,、])",     "review-1 建议-10:把流式超时写成普遍值"),
    ("E-23", r"共 16 条",                                   "review-1 建议-18:底稿说 16,实为 17"),
    ("E-24", r"venv.{0,10}89 (?:个)?包|89 个包",             "review-1 建议-20:venv 包数 87 vs 89"),
    ("E-25", r"H-14.{0,10}结清",                            "review-1 建议-19:同报告后文说它未落实"),
    # E-26 是**负控**,不是一条改判条目:它示范短语法的误吞形态(见底稿 §3)。
    ("E-26", r"iron",                                       "[负控] r4-90 自检 grep 的 `iron` 误匹配 env`iron`ment"),
    ("E-27", r"512 个|8,?530 个文件.{0,20}(?:26|260) 万",     "review-1 阻断-3 同源:规模数字"),
    ("E-28", r"读数相同|两次读数一致",                       "R11B:同名指标多次测量不得写成「读数相同」"),
    ("E-29", r"业务无影响|无实际影响|不影响功能",             "泛化:被后轮升格为 ■ 的「无害」定性"),
    ("E-30", r"审批.{0,10}两道地板|两道无条件地板",           "review-1 建议-8:审批短路链实为三道"),
]


def grep_surface(files: list[str], pattern: str, keep_r11c: bool):
    rx = re.compile(pattern)
    hits = []
    for rel in files:
        if not keep_r11c and is_r11c(rel):
            continue
        try:
            text = read(rel)
        except subprocess.CalledProcessError:
            continue
        for i, line in enumerate(text.split("\n")):
            if rx.search(line):
                hits.append((rel, i + 1, line.strip()[:160]))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--surface", action="store_true")
    ap.add_argument("--casedensity", action="store_true",
                    help="案号密度:成品章 vs notes/ vs reports/(证明案号法在成品章上天然近乎零命中)")
    ap.add_argument("--ledger", action="store_true")
    ap.add_argument("--phrases", action="store_true")
    ap.add_argument("--keep-r11c", action="store_true", help="不剔除 r11c-* (污染读数)")
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--only", default=None, help="只跑某个编号,如 E-04")
    args = ap.parse_args()

    if args.surface:
        ch, inst, src = target_chapters(), target_institutional(), source_files()
        for name, fs in (("源面", src), ("目标面-成品章", ch), ("目标面-制度文件", inst)):
            n = len(fs)
            lines = sum(len(read(f).split("\n")) for f in fs)
            print(f"{name}: {n} 份 / {lines} 行")
        if args.detail:
            for f in ch + inst:
                print(" ", f)
        return 0

    if args.casedensity:
        # 语料钉在 CORPUS_REV,**不读工作区** —— 本片自己的底稿写满了 H-R11C-E-* 案号,
        # 从工作区读会把它算进 notes/ 那一格(实测 1663 -> 1673),
        # 正是「搜过没有类测量对报告它这个动作不幂等」的形状。
        for d in ("chapters", "notes", "reports"):
            n = f = 0
            for rel in tree_files():
                if not (rel.startswith(d + "/") and rel.endswith(".md")):
                    continue
                t = read(rel)
                c = len(RE_H.findall(t)) + len(RE_G.findall(t))
                n += c
                f += 1 if c else 0
            print(f"{d}: 案号出现 {n} 次,分布在 {f} 份")
        return 0

    if args.ledger:
        rows = list(ledger_lines())
        by_dir: dict[str, int] = {}
        for rel, _, _, _ in rows:
            d = rel.split("/")[0] if "/" in rel else rel
            by_dir[d] = by_dir.get(d, 0) + 1
        withid = sum(1 for r in rows if r[2])
        print(f"# 定案级改判行:{len(rows)};带案号/评审编号的 {withid}")
        print("# 按目录:" + "  ".join(f"{k}={v}" for k, v in sorted(by_dir.items())))
        if args.detail:
            for rel, ln, ids, txt in rows:
                print(f"{rel}:{ln} {','.join(ids) or '-'} {txt}")
        return 0

    if args.phrases:
        ch, inst = target_chapters(), target_institutional()
        tot_ch = tot_inst = 0
        for pid, pat, desc in PHRASES:
            if args.only and pid != args.only:
                continue
            hc = grep_surface(ch, pat, args.keep_r11c)
            hi = grep_surface(inst, pat, args.keep_r11c)
            tot_ch += len(hc)
            tot_inst += len(hi)
            print(f"{pid}\tchapters={len(hc)}\tinstitutional={len(hi)}\t{desc}")
            if args.detail:
                for rel, ln, txt in hc + hi:
                    print(f"    {rel}:{ln}  {txt}")
        print(f"# 合计 chapters={tot_ch} institutional={tot_inst} "
              f"(r11c-* {'计入' if args.keep_r11c else '剔除'})")
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
