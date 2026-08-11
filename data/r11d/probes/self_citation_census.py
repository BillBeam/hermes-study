#!/usr/bin/env python3
"""R11D · 自引锚点普查:指向本学习仓库自己的锚点有多少,其中多少指向 `chapters/`。

**为什么要数这个。** 基线锚点写作 `路径:行号 @ 863e313` —— 后面那个 commit 把它**钉死**了,
基线不动,所以锚点永远有效。而**指向本仓库自己的锚点没有任何钉子**:它浮在一棵会动的树上。
R11D 只改了 `chapters/r1` 的几个数,就当场打断了 R11C 底稿里 7 处锚点(4 MISMATCH + 3 TABLE-DRIFT)。
R12 装订要把 21 章重排、合并、加分部 —— 那是一次**大得多**的移动。

本探针回答的就是「那一次会打断多少」。

用法:
    python3 data/r11d/probes/self_citation_census.py            # 汇总
    python3 data/r11d/probes/self_citation_census.py --detail    # 逐处
"""
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]

# 与 verify_citations.py 的 CITE 同形(此处只用来数,不做校验)。
CITE = re.compile(
    r"(?P<path>\.?[A-Za-z0-9_][A-Za-z0-9_./-]*\."
    r"(?:py|mdx|md|yaml|yml|toml|c|h|sh|json|tsx|ts|mjs|js|nix|rs|txt|ps1|css|tsv))"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?"
)
FENCE = re.compile(r"^\s*```")

# 本仓库自己的顶层目录(候选);**但 `scripts/` 与 `data/` 两个目录名在两棵树上都有**,
# 只看前缀会把 `scripts/run_tests.sh` 这种基线路径算成自引 —— R11D 片 B 实测本探针第一版
# 因此虚高 138(615 -> 477)。判据必须是**解析结果**:本仓库解析得到、且基线解析不到。
SELF_DIRS = ("chapters/", "notes/", "reports/", "reviews/", "scripts/", "data/")
REPO = Path("/home/user/hermes-agent")


def is_self_path(p: str) -> bool:
    return (STUDY / p).is_file() and not (REPO / p).is_file()


def corpus():
    out = subprocess.run(["git", "-C", str(STUDY), "ls-files"],
                         capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\n")
            if p.endswith(".md") and p.split("/")[0] in
            ("chapters", "notes", "reports", "reviews")]


def main():
    detail = "--detail" in sys.argv
    by_target = Counter()
    by_source = Counter()
    rows = []
    for rel in corpus():
        try:
            lines = (STUDY / rel).read_text(encoding="utf-8").split("\n")
        except OSError:
            continue
        in_fence = False
        for i, line in enumerate(lines, 1):
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for m in CITE.finditer(line):
                p = m.group("path")
                top = next((d for d in SELF_DIRS if p.startswith(d)), None)
                if not top or not is_self_path(p):
                    continue
                by_target[top] += 1
                if top == "chapters/":
                    by_source[rel.split("/")[0] + "/"] += 1
                    rows.append((rel, i, p, m.group("start")))
    print("自引锚点按被指向的目录:")
    for k, v in sorted(by_target.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<12} {v}")
    print(f"总计自引 {sum(by_target.values())} 处")
    print()
    print("指向 chapters/ 的锚点,按来源目录:")
    for k, v in sorted(by_source.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<12} {v}")
    print(f"合计 {sum(by_source.values())} 处 —— 这就是 R12 重排章节会打断的规模")
    if detail:
        print()
        for r in rows:
            print(f"{r[0]}:{r[1]}\t{r[2]}:{r[3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
