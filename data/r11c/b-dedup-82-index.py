#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11C 片 B · 92 簇的结构化索引 + 锚点归属(bleed)判定。

    python3 data/r11c/b-dedup-82-index.py            # 索引 TSV(簇号 C01..C92)
    python3 data/r11c/b-dedup-82-index.py --bleed    # 逐条锚点归属明细
    python3 data/r11c/b-dedup-82-index.py --clean    # 剔除 bled 锚点后重新聚类
    python3 data/r11c/b-dedup-82-index.py --summary  # 只打汇总数

口径:直接 import R11B 的 `rulings_census.py`,**不另起一套口径**
(语料快照、案号正则、is_decl / block_of 全部沿用),这样本片的簇号与 R11B 报的 92 簇逐簇可对齐。

**bleed(锚点归属漂移)的判据**,机械、无解释空间:
  R11B 探针为每个「声明位」取一个正文块(表格行 = 本行;标题 = 到下一个同级标题、≤25 行;
  项目符号/加粗段首 = 到空行、≤12 行),块内**所有** `路径:行号` 都算这条声明的锚点。
  于是**连续排布、中间没有空行的兄弟条目**(如 `- **▲-1** …` / `- **▲-2** …` / `- **▲-3** …`)
  会让前一条把后面几条的锚点全部吃进来。
  判据:在块内自上而下走,遇到「是另一个案号的声明行」就把归属切给那个案号;
  归属不是本条时读到的锚点记 **BLED**。簇若在剔除 BLED 后不再满足
  「≥2 案号 且 ≥2 轮」,则该簇**只由归属漂移造出来**,记 `BLEED-ONLY`。
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import os
import subprocess
import sys


def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         cwd=here, capture_output=True, text=True, check=True)
    return out.stdout.strip()


ROOT = repo_root()
_spec = importlib.util.spec_from_file_location(
    "rulings_census", os.path.join(ROOT, "data", "r11b", "probes", "rulings_census.py"))
RC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RC)

WINDOW = 30
MIN_ROUNDS = 2


def collect_with_provenance():
    """与 RC.collect() 同构,但每个锚点多带一个 owner 判定(own / bled-to-<cid>)。"""
    decls = collections.defaultdict(list)
    for rel in RC.iter_files(RC.CORPUS_DIRS):
        rnd = RC.round_of(rel)
        lines = RC.corpus_read(rel).split("\n")
        in_fence = False
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            seen = set()
            for cid, fam, _ in RC.find_ids(line):
                if cid in seen:
                    continue
                seen.add(cid)
                if not RC.is_decl(line, cid):
                    continue
                key = f"{rel}::{cid}" if fam in ("L", "S") else cid
                blk = RC.block_of(lines, i)
                own, bled = set(), set()
                owner = cid
                for off, bline in enumerate(blk):
                    if off > 0:
                        for ocid, _f, _p in RC.find_ids(bline):
                            if ocid != cid and RC.is_decl(bline, ocid):
                                owner = ocid
                                break
                    for m in RC.RE_ANCHOR.finditer(bline):
                        if not RC.baseline_exists(m.group(1)):
                            continue
                        tup = (m.group(1), int(m.group(2)))
                        (own if owner == cid else bled).add(tup + (owner,))
                decls[key].append(dict(
                    file=rel, line=i + 1, round=rnd, fam=fam, cid=cid,
                    kind=RC.is_decl(line, cid), text=line.strip()[:190],
                    own=sorted({(p, n) for p, n, _o in own}),
                    bled=sorted(bled)))
    return decls


def cluster(decls, use_own_only: bool):
    byfile = collections.defaultdict(list)
    for key, ds in decls.items():
        for d in ds:
            anchors = d["own"] if use_own_only else sorted(
                set(d["own"]) | {(p, n) for p, n, _o in d["bled"]})
            for p, n in anchors:
                byfile[p].append((n, key, d))
    out = []
    for p, items in byfile.items():
        items.sort(key=lambda t: (t[0], t[1]))
        used = [False] * len(items)
        for i, (n, key, d) in enumerate(items):
            if used[i]:
                continue
            grp = [(n, key, d)]
            used[i] = True
            for j in range(i + 1, len(items)):
                if used[j]:
                    continue
                if abs(items[j][0] - n) <= WINDOW:
                    grp.append(items[j])
                    used[j] = True
            cases = {g[1] for g in grp}
            rounds = {g[2]["round"] for g in grp}
            if len(cases) >= 2 and len(rounds) >= MIN_ROUNDS:
                out.append((len(cases), len(rounds), p, grp))
    out.sort(key=lambda t: (-t[1], -t[0], t[2]))
    return out


def cluster_sig(p, grp):
    """簇的稳定标识:锚点文件 + 该簇的行号集合(用于 full/clean 两次聚类之间对齐)。"""
    return (p, tuple(sorted({g[0] for g in grp})))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bleed", action="store_true")
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    decls = collect_with_provenance()
    full = cluster(decls, use_own_only=False)
    clean = cluster(decls, use_own_only=True)
    clean_files = {}
    for ncase, nround, p, grp in clean:
        clean_files.setdefault(p, []).append(sorted({g[0] for g in grp}))

    def survives(p, grp):
        lines = set(g[0] for g in grp)
        for cl in clean_files.get(p, []):
            if lines & set(cl):
                return True
        return False

    n_bleed_only = sum(0 if survives(p, g) else 1 for _c, _r, p, g in full)

    if args.summary:
        print(f"full 聚类簇数: {len(full)}")
        print(f"剔除 BLED 锚点后仍成簇: {len(full) - n_bleed_only}")
        print(f"BLEED-ONLY(只由锚点归属漂移造出来的簇): {n_bleed_only}")
        tot_own = sum(len(d["own"]) for ds in decls.values() for d in ds)
        tot_bled = sum(len(d["bled"]) for ds in decls.values() for d in ds)
        print(f"锚点归属:own={tot_own} bled={tot_bled}")
        return

    if args.bleed:
        for idx, (ncase, nround, p, grp) in enumerate(full, 1):
            rows = []
            seen = set()
            for n, key, d in grp:
                sig = (key, d["file"], d["line"])
                if sig in seen:
                    continue
                seen.add(sig)
                tag = "own" if (p, n) in d["own"] else "BLED"
                src = ""
                if tag == "BLED":
                    src = ",".join(sorted({o for q, m, o in d["bled"]
                                           if q == p and m == n}))
                rows.append((tag, d["round"], d["cid"], f"{d['file']}:{d['line']}", n, src))
            if args.clean and survives(p, grp):
                continue
            print(f"C{idx:02d}\t{p}\t{'BLEED-ONLY' if not survives(p, grp) else 'REAL'}")
            for tag, rnd, cid, loc, n, src in rows:
                print(f"    {tag:4s} [{rnd:6s}] {cid:14s} {loc} ->{n}"
                      + (f"   (锚点其实属于 {src})" if src else ""))
        return

    print("cluster\tanchor_file\tlines\tn_cases\tn_rounds\tstatus\tcases")
    for idx, (ncase, nround, p, grp) in enumerate(full, 1):
        lines = sorted({g[0] for g in grp})
        cases = []
        for n, key, d in grp:
            lab = f"{d['round']}/{d['cid']}"
            if lab not in cases:
                cases.append(lab)
        print(f"C{idx:02d}\t{p}\t{','.join(map(str, lines))}\t{ncase}\t{nround}\t"
              f"{'REAL' if survives(p, grp) else 'BLEED-ONLY'}\t{' '.join(cases)}")


if __name__ == "__main__":
    sys.exit(main())
