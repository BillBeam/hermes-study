#!/usr/bin/env python3
"""把 scripts/run_tests.sh(run_tests_parallel.py)的输出解析成 passed/failed/skipped/error 四个数。

为什么需要专门一个解析器,而不是读它的摘要行:
  * 运行器每个文件打一行进度,计数写在括号里,形如
        (2✓ 1✗, 4.9s)      ← 括号内**先空格分隔**计数,再逗号接耗时
        (12✓ 1s, 3.1s)     ← `1s` 是「1 个跳过」,`3.1s` 是耗时
        (1e, 3.0s)         ← `1e` 是「收集期报错,该文件零执行」
  * **`Ns` 的歧义是本项目栽过的坑**:R9D 把 `(1s, 1.1s)` 里的 `1s` 读成了「1 秒」,
    据此写下"无整文件跳过",是错的。判据:跳过数是**整数** + `s`,耗时**一定带小数点**。
  * 只按逗号切会把 `2✓ 1✗` 当成一个 token,两个数一起丢掉(R10 初版解析器就是这么
    把 2 个失败读成 0 的)。所以要按**空白与逗号一起**切。

用法:python3 data/r10/probes/parse_pytest_run.py <运行输出文件>
"""
from __future__ import annotations

import re
import sys


def main() -> int:
    txt = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    rows = re.findall(r"^\[[^\]]*\]\s+(\S)\s+(\S+\.py)\s+\(([^)]*)\)", txt, re.M)
    agg = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    per = []
    for mark, path, inside in rows:
        c = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
        for tok in re.split(r"[,\s]+", inside.strip()):
            if not tok:
                continue
            if m := re.fullmatch(r"(\d+)✓", tok):
                c["passed"] = int(m.group(1))
            elif m := re.fullmatch(r"(\d+)✗", tok):
                c["failed"] = int(m.group(1))
            elif m := re.fullmatch(r"(\d+)e", tok):
                c["error"] = int(m.group(1))
            elif m := re.fullmatch(r"(\d+)s", tok):     # 整数+s = 跳过;耗时带小数点
                c["skipped"] = int(m.group(1))
        for k in agg:
            agg[k] += c[k]
        per.append((path, c, mark))

    disc = re.search(r"Discovered (\d+) test files \(~(\d+) tests\)", txt)
    print(f"files parsed          : {len(rows)}")
    if disc:
        print(f"discovered (运行器自报): {disc.group(1)} files / ~{disc.group(2)} tests")
    print(f"passed={agg['passed']}  failed={agg['failed']}  "
          f"skipped={agg['skipped']}  zero-run-files={agg['error']}")
    print("\n非全绿文件:")
    for path, c, mark in per:
        if c["failed"] or c["skipped"] or c["error"]:
            print(f"  {mark} {path}: passed={c['passed']} failed={c['failed']} "
                  f"skipped={c['skipped']} error={c['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
