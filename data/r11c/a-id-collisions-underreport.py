#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11C 片 A · 复核 R11B 撞号探针的两个自陈偏差,各给一个可重跑读数。

R11B 在 `notes/r11b-raw-rulings-census.md:564-572` 自陈了三个方向的误差。
本探针只做**可机械复核**的那两个,第三个(误报 4 个)靠人读正文,写在底稿里。

变体 A —— **窄 span**(复核「漏报」)
    R11B 的铸号判据对加粗段首取 3 行、对小节标题取 4 行作为锚点搜索窗。
    窗子越宽,越容易把**下文提到的别的文件**也算进这条铸号的锚点集;
    而实体分组是按「锚点集相交」做的,于是**两条本来不同的案子会被融成一个实体**,
    这个号就不再被报成撞号。变体 A 把窗口收到**铸号行本身**,再比对撞号集合。

变体 B —— **含本仓库锚点**(复核「实体数系统性偏低」)
    R11B 的探针只认**基线里真实存在**的锚点,于是锚点指向本学习仓库自己的
    `scripts/` / `data/` 的铸号位一个都不算。`H-R10B-a` 的第三处铸号
    (`reports/round-10b-desktop-application.md:702`,锚 `scripts/verify_citations.py`)
    正是这样掉出统计的。变体 B 把「存在性」放宽到**两棵树任一**。

两个变体都**只用于复核读数**,不替换基线口径:本底稿正文报的 39 / 100
仍是 R11B 那一套判据,以保证与上一轮严格可比。

    python3 data/r11c/a-id-collisions-underreport.py            # 三行汇总 + 差集
    python3 data/r11c/a-id-collisions-underreport.py --summary  # 只要汇总
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
    "r11c_a_audit", os.path.join(ROOT, "data", "r11c", "a-id-collisions-audit.py"))
_A = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_A)
_MOD = _A._MOD


def mint_sites(*, narrow: bool, study_too: bool):
    """R11B `mint_sites` 的可调重写。判据逐字照抄,只有两处开关不同。"""
    import collections
    out = collections.defaultdict(lambda: collections.defaultdict(list))

    def exists(p: str) -> bool:
        if os.path.exists(os.path.join(_MOD.BASELINE, p)):
            return True
        return study_too and os.path.exists(os.path.join(ROOT, p))

    for rel in _MOD.corpus_files():
        lines = _MOD.corpus_read(rel).split("\n")
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
                head = cells[0] if cells else ""
            elif s.startswith("**") or s.startswith("- **") or s.startswith("* **"):
                head, span = s[:60], 1 if narrow else 3
            elif s.startswith("#"):
                head, span = s.lstrip("#").strip()[:60], 1 if narrow else 4
            if not head:
                continue
            m = _MOD.RE_H.search(head)
            if not m:
                continue
            scope = "\n".join(lines[i:i + span])
            anchors = {a.group(1) for a in _MOD.RE_ANCHOR.finditer(scope) if exists(a.group(1))}
            if not anchors:
                continue
            out[m.group(0)][rel].append((i + 1, anchors, s[:150]))
    return out


def collide_of(sites):
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


def line(tag, c):
    return (f"{tag:22s} 撞号 {len(c):3d} 号 / "
            f"{sum(len(g) for g in c.values()):3d} 实体")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    _MOD.CORPUS_REV = _A.CORPUS_REV
    _MOD.EXCLUDE_PREFIX = ("r11c-",)

    base = collide_of(mint_sites(narrow=False, study_too=False))   # == R11B 口径
    narrow = collide_of(mint_sites(narrow=True, study_too=False))
    study = collide_of(mint_sites(narrow=False, study_too=True))

    print(line("R11B 口径(基准)", base))
    print(line("变体A 窄 span", narrow))
    print(line("变体B 含本仓库锚点", study))
    if args.summary:
        return 0

    only_narrow = sorted(set(narrow) - set(base))
    lost_narrow = sorted(set(base) - set(narrow))
    print(f"\n变体A 新增撞号 {len(only_narrow)}: {', '.join(only_narrow) or '(无)'}")
    print(f"变体A 丢失撞号 {len(lost_narrow)}: {', '.join(lost_narrow) or '(无)'}")

    grew = sorted(c for c in base if c in study and len(study[c]) > len(base[c]))
    print(f"\n变体B 实体数变多的号 {len(grew)}:")
    for cid in grew:
        print(f"  {cid}: {len(base[cid])} -> {len(study[cid])} 实体")
    only_study = sorted(set(study) - set(base))
    print(f"变体B 新增撞号 {len(only_study)}: {', '.join(only_study) or '(无)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
