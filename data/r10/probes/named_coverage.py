#!/usr/bin/env python3
"""点名覆盖率:范围内每个文件在学习语料里被提到过没有。

两个读数,必须分开报,不得合并:
  * 全路径零命中 —— 语料里找不到 `path/to/file.ts` 这个完整字符串的文件数;
  * 裸文件名零命中 —— 连 `file.ts` 这个基名都找不到的文件数(必然 ≤ 全路径零命中)。

**测量污染(R9D §3.4 立,H-R9D-e)**:这个测量对「报告它」不是幂等的 ——
把积压文件逐个点名写进一张表,这个动作本身就把它们变成「已命中」。
故本脚本要求显式传 --exclude:承载清单/范围表的那些文件必须从语料里剔除,
否则读到的是虚高的改善。剔除了哪些文件会打印出来,读数旁边永远带着它的搜索面。

用法:
  python3 data/r10/probes/named_coverage.py \
      --scope data/r10/slices/A.txt [--scope ...] \
      --corpus 'chapters/*.md' --corpus 'notes/*.md' --corpus 'reports/*.md' \
      --exclude notes/r10-01-scope-and-split.md \
      [--list-misses]

不传 --corpus 时默认扫 chapters/ + notes/ + reports/ + reviews/ 下的 .md。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
DEFAULT_CORPUS = ["chapters/*.md", "notes/*.md", "reports/*.md", "reviews/*.md"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", action="append", required=True,
                    help="文件清单(每行一个仓库相对路径),可重复")
    ap.add_argument("--corpus", action="append", default=None,
                    help="语料 glob,可重复;默认 chapters/notes/reports/reviews 的 .md")
    ap.add_argument("--exclude", action="append", default=[],
                    help="从语料里剔除的文件(承载清单本身的那些),可重复")
    ap.add_argument("--list-misses", action="store_true", help="逐个列出零命中文件")
    args = ap.parse_args()

    scope: list[str] = []
    seen: set[str] = set()
    for spec in args.scope:
        for line in (ROOT / spec).read_text(encoding="utf-8").splitlines():
            p = line.strip()
            if p and p not in seen:
                seen.add(p)
                scope.append(p)

    excluded = {str(pathlib.Path(e)) for e in args.exclude}
    corpus_files: list[pathlib.Path] = []
    for pat in (args.corpus or DEFAULT_CORPUS):
        for f in sorted(ROOT.glob(pat)):
            rel = str(f.relative_to(ROOT))
            if rel not in excluded:
                corpus_files.append(f)

    blob = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in corpus_files)

    path_miss = [p for p in scope if p not in blob]
    base_miss = [p for p in path_miss if p.rsplit("/", 1)[-1] not in blob]

    print(f"scope files      : {len(scope)}")
    print(f"corpus files     : {len(corpus_files)} ({len(blob)} chars)")
    print(f"excluded from    : {sorted(excluded) if excluded else '(none)'}")
    print(f"full-path ZERO   : {len(path_miss)}")
    print(f"bare-name ZERO   : {len(base_miss)}")
    if args.list_misses:
        print("--- full-path zero-hit ---")
        for p in path_miss:
            print(f"  {p}")
        print("--- bare-name zero-hit ---")
        for p in base_miss:
            print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
