#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11C 片 E · 判据 2 —— 「可复算指标的第二份手抄件」检测器。

**为什么需要第二条判据(这是本片的核心方法论结论)。**
判据 1(短语法)拿「被推翻的那句话的不可替换短语」去搜。它只能抓住**说法**被抄走的情形。
但成品章里还有另一类过期:一条**当时正确、以现在时陈述、而其真值随项目推进而移动**的
派生数据。它从来没有被任何一条「改判」点名过(没人会写「511 这个数被推翻了」),
所以**它在判据 1 下永远零命中**——一个天然零命中的判据等于没搜。

判据 2 的形态是**不预设答案**的:运行期从权威源(`data/ledger.tsv`)复算真值,
再去目标面找同名指标的手抄件,不等即命中。
`chapters/r1-what-is-hermes-agent.md` 自己就写着这条道理的出处
(review-1 阻断-2 / M-2:「凡是能被脚本算出来的数,正文就不该有第二份手抄件」)——
**它是被这条道理修好过一次、又在同一个地方复发的**。

用法:
  python3 data/r11c/e-reversal-propagation-derived.py            # 逐章比对分层表
  python3 data/r11c/e-reversal-propagation-derived.py --blast    # 过期值的传播半径
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
CORPUS_REV = os.environ.get("R11C_CORPUS_REV", "f440d7814a4528cb9782bc93d079eec7a0f8b127")


def _git(*a: str) -> str:
    return subprocess.run(["git", "-C", ROOT, *a], capture_output=True,
                          text=True, check=True).stdout


def truth() -> dict[str, tuple[int, int]]:
    """从 data/ledger.tsv 复算五层的 (文件数, 行数)。CRLF 行尾,必须剥 CR。"""
    out: dict[str, list[int]] = {}
    with open(os.path.join(ROOT, "data", "ledger.tsv"), encoding="utf-8") as fh:
        next(fh)
        for row in fh:
            f = row.rstrip("\n").rstrip("\r").split("\t")
            if len(f) < 4:
                continue
            layer = f[3].strip()
            rec = out.setdefault(layer, [0, 0])
            rec[0] += 1
            rec[1] += int(f[2])
    res = {k: (v[0], v[1]) for k, v in out.items()}
    tot = [sum(v[0] for v in res.values()), sum(v[1] for v in res.values())]
    res["合计"] = (tot[0], tot[1])
    return res


def chapters() -> list[str]:
    return sorted(p for p in _git("ls-tree", "-r", "--name-only", CORPUS_REV).split("\n")
                  if p.startswith("chapters/") and p.endswith(".md"))


def read(p: str) -> str:
    return _git("show", f"{CORPUS_REV}:{p}")


RE_ROW = re.compile(r"^\|\s*\*{0,2}(L[1-4T])\b")
RE_NUM = re.compile(r"(\d[\d,]*)")
# 判据 2 的第二个指标:台账 status 列停在 R1-inventoried 的剩余量。
# 它是 CLAUDE.md「每轮报告恢复必报项」点名的那个数,同样可由台账复算。
RE_INV = re.compile(r"R1-inventoried")
# 判据 2 的覆盖面探测:成品章里**以现在时陈述**的数字断言(不判对错,只清点分母)。
RE_PRESENT = re.compile(r"(当前|目前|截至|现在仍|仍有|现有)")


def inventoried() -> tuple[int, int]:
    n = l = 0
    with open(os.path.join(ROOT, "data", "ledger.tsv"), encoding="utf-8") as fh:
        next(fh)
        for row in fh:
            f = row.rstrip("\n").rstrip("\r").split("\t")
            if len(f) >= 6 and f[5].strip() == "R1-inventoried":
                n += 1
                l += int(f[2])
    return n, l


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blast", action="store_true", help="过期值在全语料的传播半径")
    args = ap.parse_args()

    tr = truth()
    if args.blast:
        # 先算出「哪些值是过期的」:成品章里手抄、而与权威源不等的那些
        stale: set[str] = set()
        for rel in chapters():
            for line in read(rel).split("\n"):
                m = RE_ROW.match(line.strip())
                if not m:
                    continue
                nums = [n for n in RE_NUM.findall(line)]
                want = tr.get(m.group(1))
                for n in nums:
                    v = int(n.replace(",", ""))
                    if want and v not in want and v > 100:
                        stale.add(n)
        # 只量**带千分位**的那一种写法:裸 `511` 在语料里同时是行号、端口、字节数,
        # 量它等于量噪音(与 CLAUDE.md 记的 `iron` 匹配到 env`iron`ment 同一物种)。
        # 两个口径都报(CLAUDE.md「同一指标多次/多方法测量必须分别标注」):
        #   散文口径 = 带千分位 `479,923`;脚本输出口径 = 裸 `479923`(校验器打印的形态)。
        # 裸 `511` 这种不带千分位的短数字不量:它在语料里同时是行号、端口、字节数,
        # 量它等于量噪音(与 CLAUDE.md 记的 `iron` 匹配到 env`iron`ment 同一物种)。
        print("# 过期值(带千分位者):" + " ".join(sorted(s for s in stale if "," in s)))
        for s in sorted(s for s in stale if "," in s):
            for label, needle in (("散文口径", s), ("脚本输出口径", s.replace(",", ""))):
                out = subprocess.run(["git", "-C", ROOT, "grep", "-n", "-F", needle, CORPUS_REV,
                                      "--", "*.md", "*.py"],
                                     capture_output=True, text=True).stdout.strip()
                rows = [r.split(":", 3) for r in out.split("\n") if r]
                rows = [r for r in rows if not (label == "脚本输出口径" and s in r[3])]
                locs = [f"{r[1]}:{r[2]}" for r in rows]
                by_dir: dict[str, int] = {}
                for r in rows:
                    by_dir[r[1].split("/")[0]] = by_dir.get(r[1].split("/")[0], 0) + 1
                print(f"{s}\t{label}\t命中 {len(locs)}\t"
                      + " ".join(f"{k}={v}" for k, v in sorted(by_dir.items())))
                for lo in locs:
                    print(f"    {lo}")
        return 0

    bad = 0
    for rel in chapters():
        for i, line in enumerate(read(rel).split("\n")):
            m = RE_ROW.match(line.strip())
            if not m:
                continue
            layer = m.group(1)
            nums = [int(n.replace(",", "")) for n in RE_NUM.findall(line)
                    if int(n.replace(",", "")) > 100 or n in ("560",)]
            want = tr.get(layer)
            if not want:
                continue
            got = tuple(nums[-2:]) if len(nums) >= 2 else tuple(nums)
            ok = got == want
            if not ok:
                bad += 1
            print(f"{'STALE' if not ok else 'ok   '} {rel}:{i+1} {layer} "
                  f"手抄={got} 台账真值={want}")
    print(f"# 分层表手抄件:STALE={bad}")

    # 指标二:R1-inventoried 剩余量(同样可由台账复算)
    inv = inventoried()
    bad2 = 0
    for rel in chapters():
        lines = read(rel).split("\n")
        for i, line in enumerate(lines):
            if not RE_INV.search(line):
                continue
            ctx = " ".join(lines[max(0, i - 1):i + 2])
            nums = {int(n.replace(",", "")) for n in RE_NUM.findall(ctx)}
            if not (nums & set(inv)):
                bad2 += 1
                print(f"STALE {rel}:{i+1} R1-inventoried 手抄邻域={sorted(n for n in nums if n > 400)} "
                      f"台账真值={inv}")
            else:
                print(f"ok    {rel}:{i+1} R1-inventoried 台账真值={inv}")
    print(f"# R1-inventoried 手抄件:STALE={bad2}")

    # 覆盖面(不判对错,只报分母):成品章里以现在时陈述的数字断言有多少条,
    # 本判据只覆盖其中**有权威源可复算**的两个指标。**不报这个分母就是谎报覆盖率。**
    present = 0
    for rel in chapters():
        for line in read(rel).split("\n"):
            if RE_PRESENT.search(line) and RE_NUM.search(line):
                present += 1
    print(f"# 覆盖面:成品章「现在时 + 数字」的行 {present} 行;"
          f"本判据可复算的指标 2 个(分层表、R1-inventoried)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
