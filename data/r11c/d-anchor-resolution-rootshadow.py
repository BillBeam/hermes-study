#!/usr/bin/env python3
"""R11C 片 D:「解析成功」本身可以是假保证 —— 仓库根同名文件的遮蔽面。

R11B 在 H-R11B-D-d 里点名担心过一次(`notes/r6-10-honcho.md:677` 的
`plugins/memory/honcho/cli.py:1113`)。本探针把这条担心量化:

  裸文件名锚点(路径里没有 `/`)
  ∧ 它在基线**仓库根**确实是一个真文件      -> 于是解析成功,关卡满意
  ∧ 同名文件在树的**别处还有 ≥1 个**        -> 于是「解析成功」不等于「指对了」

这一类**任何现有关卡都发现不了**:路径解析得到,行号也可能恰好在范围内,
校验器对着根上那个文件比对,而作者说的是别处那一个。行号越界只是它**偶尔**
露出的马脚(全语料 3 处,已在 §2.6 修掉),露不出马脚的才是主体。

    python3 data/r11c/d-anchor-resolution-rootshadow.py [--no-exclude]
"""
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

STUDY = Path(__file__).resolve().parents[2]
REPO = Path("/home/user/hermes-agent")
RAW = "--no-exclude" in sys.argv
PREFIXES = ("r11c-", "round-11c-")

WIDE = re.compile(
    r"(?P<path>\.?[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?P<ext>[A-Za-z0-9]{1,6}))"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?"
)
FENCE = re.compile(r"^\s*```")


def ls(root):
    return [p for p in subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                                      text=True, check=True).stdout.split("\n") if p]


paths = ls(REPO)
root_files = {p for p in paths if "/" not in p}
by_base = defaultdict(set)
for p in paths:
    by_base[p.split("/")[-1]].add(p)

# 遮蔽名 = 根上有、别处也有的文件名
shadowed = {n for n in root_files if len(by_base[n]) > 1}

_len = {}


def flen(rel):
    if rel not in _len:
        _len[rel] = len((REPO / rel).read_text(encoding="utf-8",
                                               errors="replace").splitlines())
    return _len[rel]


def main():
    print(f"基线仓库根文件 {len(root_files)} 个,其中 {len(shadowed)} 个在树的别处还有同名:")
    print("  " + "  ".join(sorted(shadowed)))
    hits = Counter()
    rows = []
    for d in ("chapters", "notes", "reports", "reviews"):
        for f in sorted((STUDY / d).glob("*.md")):
            if not RAW and f.name.startswith(PREFIXES):
                continue
            in_fence = False
            for ln, line in enumerate(f.read_text(encoding="utf-8",
                                                  errors="replace").splitlines(), 1):
                if FENCE.match(line):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                for m in WIDE.finditer(line):
                    p = m.group("path")
                    if p not in shadowed:
                        continue
                    start = int(m.group("start"))
                    n = flen(p)
                    hits[p] += 1
                    rows.append((f"{d}/{f.name}", ln, p, start, n,
                                 "行号越界" if start > n else ""))
    print(f"\n语料里用了这些名字的裸锚点 = {sum(hits.values())} 处"
          f"({'不剔除本轮' if RAW else '剔除本轮 r11c-*'})")
    for name, c in hits.most_common():
        others = sorted(by_base[name] - {name})
        print(f"  {c:>4}  {name}  (根 {flen(name)} 行;别处还有 {len(others)} 个"
              f":{', '.join(others[:3])}{' …' if len(others) > 3 else ''})")
    oob = [r for r in rows if r[5]]
    print(f"\n其中行号越界(即**已经露馅**的) = {len(oob)} 处")
    for r in oob:
        print(f"  {r[0]}:{r[1]}  {r[2]}:{r[3]}  (根上那个只有 {r[4]} 行)")


if __name__ == "__main__":
    main()
