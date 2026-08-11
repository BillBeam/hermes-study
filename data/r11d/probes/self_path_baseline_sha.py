#!/usr/bin/env python3
"""R11D · 把**自引路径**挂在**基线 sha** `863e313` 上的锚点普查(H-R11D-M-b)。

`@ 863e313` 的含义是「这一段引的是 hermes-agent 基线仓库的那一版」。把它写在
`scripts/…` / `chapters/…` / `notes/…` 这种**本学习仓库自己的路径**后面,是一个**类别错误**:
那个 sha 在本仓库里 rev-parse 不出来,它根本不指向这份文件的任何一版。

**当前无害**:R11D 的钉子实现只在 sha 能在本仓库解析时才启用,解析不出来就退回原行为
(读工作树),所以这些锚点的校验结果与从前一致。**但读者会被误导** —— 一个写着
`@ 863e313` 的锚点看上去是被钉住的,实际上它浮在会动的树上。

用法:
    python3 data/r11d/probes/self_path_baseline_sha.py            # 汇总
    python3 data/r11d/probes/self_path_baseline_sha.py --detail   # 逐处
"""
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
SELF_DIRS = ("chapters/", "notes/", "reports/", "reviews/", "scripts/", "data/")

MISPIN = re.compile(
    r"(?P<path>(?:chapters|notes|reports|reviews|scripts|data)/[A-Za-z0-9_./-]+"
    r"\.(?:py|md|tsv|sh|json|txt))"
    r":(?P<line>\d+(?:-\d+)?)\s*@\s*863e313"
)

# **`scripts/` 和 `data/` 这两个目录名在两个仓库里都存在。** 本探针第一版只看目录前缀,
# 于是把 `scripts/run_tests.sh:12 @ 863e313` 这种**完全正确的基线引用**算成了类别错误
# —— 一次实测里 37 处 `.sh` 命中全是这样来的,读数从 74 虚增到 112。
# 判据必须是**解析结果**,不是路径长相:**在本仓库解析得到、且在基线解析不到**,才是自引。
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
    by_dir, rows = Counter(), []
    for rel in corpus():
        try:
            lines = (STUDY / rel).read_text(encoding="utf-8").split("\n")
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for m in MISPIN.finditer(line):
                if not is_self_path(m.group("path")):
                    continue          # 基线里也有同路径 -> 这是正确的基线引用
                top = m.group("path").split("/")[0] + "/"
                by_dir[top] += 1
                rows.append((rel, i, m.group(0)))
    print("自引路径却挂基线 sha `863e313` 的锚点,按被指向的目录:")
    for k, v in sorted(by_dir.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<12} {v}")
    print(f"合计 {sum(by_dir.values())} 处")
    if detail:
        for r in rows:
            print(f"{r[0]}:{r[1]}\t{r[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
