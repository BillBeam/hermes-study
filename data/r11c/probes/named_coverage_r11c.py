#!/usr/bin/env python3
"""点名覆盖率(R11C 版):被测对象是**本轮触及的文件清单**,不是台账 L1 全集。

R11B 版量的是「台账里 status=*-deep-read 的 L1 文件有没有被点过名」。R11C 不吃内容,
没有新读的文件,但**触及了文件清单**(片 C 的 31 个坏证据文件、片 D 的锚点欠账文件),
验收项 5 因此仍然适用:清单里的每个文件在语料里被点到了没有。

沿用 R9D 踩出来的那条性质,不重新发明:**这个测量对「报告它」不幂等** ——
判据是「该路径字符串在语料里出现过没有」,而为了履行「逐个点名」把清单写进底稿,
点名这个动作本身就把被点名文件变成了已命中。所以**两个读数都报,不合并**。

与 R11B 版的口径差(必须写出来,不得当成同一个测量):
  - 被测集合不同:R11B 是台账 L1 deep-read 全集(563 个),R11C 是本轮清单文件。
  - 承载清单不同:R11B 剔除 `r9d-01-scope-and-l1-closeout.md`,
    R11C 剔除的是本轮自己那两份清单(`data/r11c/*.tsv` / `*.txt` 不在语料 SCOPE 内,
    但引用它们的**底稿**在),见 DEFAULT_EXCLUDE。

    python3 data/r11c/probes/named_coverage_r11c.py [--list] [--set c|d]

不依赖会话专属路径:仓库根从本文件位置推出。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "-C", str(Path(__file__).resolve().parent),
                            "rev-parse", "--show-toplevel"],
                           capture_output=True, check=True).stdout.decode().strip())
SCOPE = ("notes", "chapters", "reports")

# 只列清单、不含可溯源断言的文件。加一份到这里之前先问:它是「研究了这些文件」
# 还是「抄了一遍文件名」?只有后者才该剔除。
# 本轮片 C / 片 D 的底稿**不剔除** —— 它们点这些路径正是因为真的改了那些文件。
DEFAULT_EXCLUDE = ("r9d-01-scope-and-l1-closeout.md",)


def load_set(which: str) -> list[str]:
    if which == "c":
        f = ROOT / "data" / "r11c" / "slice-c-files.txt"
        return [ln.strip() for ln in f.read_text().splitlines() if ln.strip()]
    # 片 D 的被测集合 = R11B 那份引用欠账清单点名的 41 个 notes
    f = ROOT / "data" / "r11b" / "notes-citation-backlog.txt"
    seen = []
    for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = ln.split()
        if len(parts) >= 2 and ":" in parts[1]:
            rel = "notes/" + parts[1].split(":")[0]
            if rel not in seen:
                seen.append(rel)
    return seen


def corpus(exclude: set[str]) -> str:
    return "\n".join(
        f.read_text(encoding="utf-8", errors="replace")
        for d in SCOPE for f in sorted((ROOT / d).glob("*.md"))
        if f.name not in exclude)


def measure(paths, text):
    pm = [p for p in paths if p not in text]
    nm = [p for p in pm if Path(p).name not in text]
    return pm, nm


def main(argv: list[str]) -> int:
    which = argv[argv.index("--set") + 1] if "--set" in argv else "c"
    paths = load_set(which)
    for label, ex in (("不剔除(朴素)", set()),
                      ("剔除承载清单", set(DEFAULT_EXCLUDE))):
        pm, nm = measure(paths, corpus(ex))
        print(f"[片 {which.upper()} 清单 {len(paths)} 个] {label}: "
              f"全路径零命中 {len(pm)};裸名零命中 {len(nm)}")
    if "--list" in argv:
        pm, nm = measure(paths, corpus(set(DEFAULT_EXCLUDE)))
        for p in pm:
            print(f"  {p}{'  [连裸名也零命中]' if p in nm else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
