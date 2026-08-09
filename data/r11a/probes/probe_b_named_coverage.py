#!/usr/bin/env python3
"""R11A 片B 探针:片内每个文件是否在底稿里以**全路径**出现过(判据 1)。

用法:

    python3 data/r11a/probes/probe_b_named_coverage.py \
        data/r11a/slices/slice-L2-B.tsv notes/r11a-raw-ci-and-container.md

打印两个读数,必须分开看:
  * 全路径零命中 —— 语料里找不到完整路径字符串的文件数(判据 1 要求为 0);
  * 裸文件名零命中 —— 连基名都找不到的文件数(必然 ≤ 上者)。
加 --list 打印漏掉的路径。
"""
import sys
from pathlib import Path


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tsv, notes = Path(args[0]), [Path(a) for a in args[1:]]
    corpus = "\n".join(n.read_text(encoding="utf-8") for n in notes)
    paths = []
    for i, line in enumerate(tsv.read_text(encoding="utf-8").splitlines()):
        if i == 0:
            continue
        p = line.split("\t")[0].strip()
        if p:
            paths.append(p)
    miss_full = [p for p in paths if p not in corpus]
    miss_base = [p for p in paths if p.rsplit("/", 1)[-1] not in corpus]
    print(f"片内文件 {len(paths)}  全路径零命中 {len(miss_full)}  裸文件名零命中 {len(miss_base)}")
    if "--list" in sys.argv:
        for p in miss_full:
            print("  MISS-FULL", p)
        for p in miss_base:
            print("  MISS-BASE", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
