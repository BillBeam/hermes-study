#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11C 片 B · 「92 − 10 = 82」这个减法的口径核对。

R11B 裁决的单位是**组(实体)**,而 92 是**簇**;一个实体可以横跨多簇。
本脚本把 R11B 的 M-1…M-10 各自的案号集合写死,机械算出:
  * 全部案号都落在某一个 M 组里的簇  -> R11B 已完整覆盖,本片无须再裁
  * 部分案号落在 M 组里的簇          -> 本片只需裁那些**多出来的**案号
  * 一个案号都不沾 M 组的簇          -> 本片全裁

    python3 data/r11c/b-dedup-82-coverage.py
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys


def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=here,
                          capture_output=True, text=True, check=True).stdout.strip()


ROOT = repo_root()
_s = importlib.util.spec_from_file_location(
    "b_index", os.path.join(ROOT, "data", "r11c", "b-dedup-82-index.py"))
BI = importlib.util.module_from_spec(_s)
_s.loader.exec_module(BI)

# R11B §2.3 的 10 个合并组,逐组抄它「涉及案号」那一列。
# 只记案号本身;L/S 家族的案号在探针里带文件前缀,故用 endswith 匹配。
M_GROUPS = {
    "M-1": ["■-01", "H-R9A-a", "H-R9B-d", "■-R11A-01", "H-R11A-a"],
    "M-2": ["H-R8C-d", "H-R8D-c", "■-R9A-01"],
    "M-3": ["■-1", "■-2", "H-R9D-B-b"],          # R9C ■-1 / R9D ■-2
    "M-4": ["▲3", "◇3", "◇6"],                    # R7C ▲3 / R8A ◇3 / R8A ◇6
    "M-5": ["▲21", "▲-B-1", "▲1"],                # R7 ▲21-1 / R7B ▲ B-1 / r7b 章 ▲1
    "M-6": ["▲-1", "▲-4"],                        # r7c-sched-a/b ▲-1 / r7c-90 ▲-4
    "M-7": ["■1", "H-R9D-A-a", "H-R9D-a"],
    "M-8": ["■-4", "H-R9D-F-b", "H-R9D-c"],
    "M-9": ["H-R8C-g", "■-R10-01", "H-R10-d"],
    "M-10": ["▲-3", "▲4", "H-R9A-g"],
}
# M-3 / M-4 / M-5 / M-6 / M-10 的裸序号在别的文件里也叫同一个名字,
# 故按「案号 + 声明所在文件」双重限定,避免把无关的 ■-1 / ▲3 算成已覆盖。
M_FILES = {
    "M-3": ("r9c-raw-secret-sources", "r9d-raw-file-io-safety"),
    "M-4": ("r7c-raw-authz-pairing", "r8a-raw-pairing-and-config-cmd"),
    "M-5": ("r7-raw-run-05", "r7b-10-base-adapter", "r7b-90-doc-conflict",
            "chapters/r7b-"),
    "M-6": ("r7c-raw-cron-sched-a", "r7c-raw-cron-sched-b", "r7c-90-doc-conflict"),
    "M-7": ("r9d-raw-lsp", "r11a-90-handover", "round-9d-l1-completion"),
    "M-8": ("r9d-raw-gateway-clarify", "r11a-90-handover", "round-9d-l1-completion"),
    "M-10": ("r9a-raw-moa", "chapters/r9a-", "r9d-90-handover", "r9d-91-handover",
             "round-9a-capability"),
}


def in_group(cid: str, decl_file: str) -> str | None:
    for g, ids in M_GROUPS.items():
        if cid not in ids:
            continue
        pats = M_FILES.get(g)
        if pats and not any(p in decl_file for p in pats):
            continue
        return g
    return None


def main():
    decls = BI.collect_with_provenance()
    full = BI.cluster(decls, use_own_only=False)
    fully, partly, untouched = [], [], []
    for idx, (nc, nr, p, grp) in enumerate(full, 1):
        lbl = f"C{idx:02d}"
        hits, misses = set(), set()
        for n, key, d in grp:
            g = in_group(d["cid"], d["file"])
            (hits if g else misses).add(g or d["cid"])
        if not misses:
            fully.append((lbl, p, sorted(hits)))
        elif hits:
            partly.append((lbl, p, sorted(hits), sorted(misses)))
        else:
            untouched.append((lbl, p, sorted(misses)))
    print(f"簇总数 {len(full)}")
    print(f"  R11B 的 M 组**完整覆盖**的簇: {len(fully)}  -> {[x[0] for x in fully]}")
    print(f"  M 组**部分覆盖**的簇:        {len(partly)}  -> {[x[0] for x in partly]}")
    print(f"  M 组**一个案号都不沾**的簇:  {len(untouched)}")
    print(f"  本片仍须出裁决的簇 = {len(partly) + len(untouched)}"
          f"(R11B 报的是 82)")
    print("\n-- 部分覆盖的簇,多出来的案号 --")
    for lbl, p, hits, misses in partly:
        print(f"{lbl} {p}: 已覆盖 {hits};未覆盖 {misses}")


if __name__ == "__main__":
    sys.exit(main())
