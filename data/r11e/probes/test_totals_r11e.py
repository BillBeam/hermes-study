#!/usr/bin/env python3
"""R11E · 从 run_tests.sh 完整日志汇总 passed / failed / skipped(验收项 8)。

`scripts/run_tests.sh` 的收尾**只打印失败清单与零执行清单**,不打印 passed/skipped 的
聚合行;逐文件读数在进度行的括号里,形如 `(57✓ 5s, 3.1s)` —— `N✓` 通过、`N✗` 失败、
`Ns` 跳过,最后那个带小数点的是耗时。本脚本按这个格式汇总。

**为什么要有它**:第一次跑全量时把输出管进了 `tail -120`,聚合信息恰好被截掉,
只剩失败清单 —— 证据被自己的排版动作弄没了,只好整轮重跑。把解析落库,
下一轮不必再靠 `tail` 的运气。

**整文件跳过**的判据:该文件 `passed == 0 且 skipped > 0`。验收明令这类文件要**逐个点名**
并报出掩盖了多少用例 —— 它们和「零执行」一样,在一个只看 passed 的读者眼里是不存在的。

    python3 data/r11e/probes/test_totals_r11e.py <完整日志>
"""
import re
import sys
from pathlib import Path

# 进度行:  [ 41.2% | ... ] ✓ tests/x/y.py (57✓ 5s, 3.1s)
LINE = re.compile(r"^\[\s*[\d.]+%[^\]]*\]\s+\S+\s+(?P<file>\S+\.py)\s+\((?P<counts>[^)]*)\)\s*$")
TOK = re.compile(r"(\d+)(✓|✗|s)(?=[\s,)]|$)")


def main():
    log = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").split("\n")
    files, tot = {}, {"✓": 0, "✗": 0, "s": 0}
    for line in log:
        m = LINE.match(line.rstrip())
        if not m:
            continue
        counts = m.group("counts").rsplit(",", 1)[0]   # 去掉末尾耗时
        c = {"✓": 0, "✗": 0, "s": 0}
        for n, kind in TOK.findall(counts):
            c[kind] += int(n)
        f = m.group("file")
        prev = files.get(f)
        # 同一文件可能因 FLAKY 重跑出现两次,取最后一次(运行器的最终判定)
        files[f] = c
        if prev:
            for k in tot:
                tot[k] -= prev[k]
        for k in tot:
            tot[k] += c[k]

    whole_skip = {f: c for f, c in files.items() if c["✓"] == 0 and c["s"] > 0}
    part_skip = {f: c for f, c in files.items() if c["✓"] > 0 and c["s"] > 0}
    print(f"文件数(有进度行)={len(files)}")
    print(f"passed={tot['✓']}  failed={tot['✗']}  skipped={tot['s']}")
    print(f"含 skip 的文件={len(whole_skip) + len(part_skip)}"
          f"(整文件跳过 {len(whole_skip)} / 部分跳过 {len(part_skip)})")
    print("\n=== 整文件跳过(passed=0 且 skipped>0)逐个点名 ===")
    if not whole_skip:
        print("(无)")
    for f, c in sorted(whole_skip.items(), key=lambda x: -x[1]["s"]):
        print(f"  {c['s']:>3} 个用例被跳过  {f}")
    print(f"\n整文件跳过合计掩盖 {sum(c['s'] for c in whole_skip.values())} 个用例")
    return 0


if __name__ == "__main__":
    sys.exit(main())
