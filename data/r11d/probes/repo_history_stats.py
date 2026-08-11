#!/usr/bin/env python3
"""R11D · 引用仓库历史的统计数字:可重跑命令 + 口径 + 分母(验收项 12)。

本轮有两处结论引用了**本学习仓库的 git 历史**:

  (a) `chapters/r1` 的 L1 轨迹补到 `563(R8D)` —— 依据是 `data/ledger.tsv` 每次提交时
      L1 的文件数;
  (b) 同章「L3 / L4 / LT 三层**自建账起**一字未动」—— 把原文的「连续五轮」换掉。

CLAUDE.md 要求这类数字给出**口径定义**与**该命令所在仓库的可达提交总数**(分母),
否则「变过几次」这种数没有基准:同一条命令在浅克隆里会给出完全不同、且看起来同样合理的答案。

**口径**:
  - 语料 = `git log --follow -- data/ledger.tsv` 能列出的**全部**提交(--follow 跟过改名),
    按 `--reverse` 从早到晚。
  - 每个提交上,用 `git show <sha>:data/ledger.tsv` 取那一版台账,按第 4 列(layer)
    分组计数。**必须剥 CR** —— 台账是 CRLF 行尾,不剥的话 layer 列永远匹配不上,
    命令会安静地打出 0(CLAUDE.md 拿这个形状当反例)。
  - 「变过」= 相邻两次提交的该层文件数不等。
  - **分母**:`git rev-list --count HEAD`,即本命令所在仓库从 HEAD 可达的提交总数。

用法:
    python3 data/r11d/probes/repo_history_stats.py
"""
import subprocess
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
LAYERS = ("L1", "L2", "L3", "L4", "LT")


def git(*a):
    return subprocess.run(["git", "-C", str(STUDY), *a],
                          capture_output=True, text=True, check=True).stdout


def counts_at(sha):
    blob = subprocess.run(["git", "-C", str(STUDY), "show", f"{sha}:data/ledger.tsv"],
                          capture_output=True, text=True)
    if blob.returncode != 0:
        return None
    out = dict.fromkeys(LAYERS, 0)
    for i, raw in enumerate(blob.stdout.split("\n")):
        if not i or not raw.strip():
            continue
        col = raw.rstrip("\r\n").split("\t")
        if len(col) < 4:
            continue
        layer = col[3].rstrip("\r")          # CRLF:不剥 CR 就恒为 0
        if layer in out:
            out[layer] += 1
    return out


def main():
    reachable = git("rev-list", "--count", "HEAD").strip()
    shas = [s for s in git("log", "--follow", "--format=%H", "--reverse",
                           "--", "data/ledger.tsv").split("\n") if s]
    print(f"分母:本仓库 HEAD 可达提交总数 = {reachable}")
    print(f"语料:改动过 data/ledger.tsv 的提交 = {len(shas)}(--follow,含改名前)")
    print()

    prev, changes = None, {k: 0 for k in LAYERS}
    traj = []
    for sha in shas:
        cur = counts_at(sha)
        if cur is None:
            continue
        if prev is None:
            traj.append((sha[:7], cur["L1"]))
        else:
            for k in LAYERS:
                if cur[k] != prev[k]:
                    changes[k] += 1
            if cur["L1"] != prev["L1"]:
                traj.append((sha[:7], cur["L1"]))
        prev = cur

    print("各层文件数在台账全部历史里变过几次:")
    for k in LAYERS:
        print(f"  {k}: {changes[k]} 次")
    print()
    print("L1 轨迹(只列发生变化的提交):")
    for sha, n in traj:
        subj = git("log", "-1", "--format=%s", sha).strip()[:46]
        print(f"  {sha}  L1={n}  {subj}")
    print()
    never = [k for k in LAYERS if changes[k] == 0]
    print(f"自建账起一次未变的层:{', '.join(never) if never else '(无)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
