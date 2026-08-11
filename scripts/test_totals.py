#!/usr/bin/env python3
"""从 `scripts/run_tests.sh` 的完整日志汇总 passed / failed / skipped / 零执行。

## 为什么这个解析要落在 `scripts/` 而不是每轮自己写一遍(R11F 立,结清 `H-R11E-M-c`)

`hermes-agent` 的 `scripts/run_tests.sh` 收尾**只打印失败清单与零执行清单**,
不打印 passed/skipped 的聚合行;逐文件读数藏在进度行的括号里,形如
`(57✓ 5s, 3.1s)` —— `N✓` 通过、`N✗` 失败、`Ns` 跳过,末尾带小数点的是耗时。
于是**每一轮都要自己写一次解析**,而两轮写出了两个口径:R11D 报 skipped **132**、
R11E 报 **239**,同一套测试、同一个名字的指标。

这正是 R11E 原则层 P08 要防的形状(同一份知识存在多个副本),
只不过副本落在**工具的输出格式**这一侧。R11E 把解析写成了
`data/r11e/probes/test_totals_r11e.py` 并铸 `H-R11E-M-c`,去向写的是
「乙,或任一改 `scripts/` 的轮次:把汇总解析收进 `scripts/`」。
R11F 是改 `scripts/` 的轮次,故在此收口:**此后各轮共用这一个口径**。

相对 R11E 版的唯一功能增补是**零执行清单也一并解析**。理由是验收项把
「skipped 逐个点名」与「零执行逐个点名」列在同一条里,而它们此前要读两处:
skipped 靠解析进度行,零执行靠人眼看日志末尾那一节。两个读数出自一条命令,
才不会出现"报了一个忘了另一个"。

## 三类"没跑到"的用例互不相同,分开报

| 类别 | 判据 | 它在一个只看 passed 的读者眼里 |
|---|---|---|
| **整文件跳过** | 该文件 `passed == 0 且 skipped > 0` | 不存在 —— 文件是绿的,只是一个用例都没真跑 |
| **部分跳过** | `passed > 0 且 skipped > 0` | 不存在 —— 被通过数盖住 |
| **零执行** | 出现在日志末尾 `=== N files where no tests ran ===` 一节 | 不存在 —— 连进度行都没有,`✓/✗/s` 全都为空 |

**零执行的用例数日志里没有**(收集阶段就失败了,pytest 没数出来),
故用 `--baseline <repo>` 时改为静态数该文件里的 `def test_` 与 `async def test_`,
给出"掩盖了多少用例"的下界。不给 `--baseline` 就只点名、不报数 ——
**不猜**,与本项目其他关卡同源(声明,不靠嗅探)。

    python3 scripts/test_totals.py <完整日志> [--baseline /home/user/hermes-agent]
"""
import argparse
import re
import sys
from pathlib import Path

# 进度行:  [ 41.2% | ... ] ✓ tests/x/y.py (57✓ 5s, 3.1s)
LINE = re.compile(r"^\[\s*[\d.]+%[^\]]*\]\s+\S+\s+(?P<file>\S+\.py)\s+\((?P<counts>[^)]*)\)\s*$")
TOK = re.compile(r"(\d+)(✓|✗|s)(?=[\s,)]|$)")
ZERO_HDR = re.compile(r"^===\s+(?P<n>\d+)\s+files where no tests ran\b")
DEF_TEST = re.compile(r"^\s*(?:async\s+)?def\s+test_", re.M)


def parse(log_lines):
    files, tot = {}, {"✓": 0, "✗": 0, "s": 0}
    zero, in_zero = [], False
    for line in log_lines:
        s = line.rstrip()
        if ZERO_HDR.match(s):
            in_zero = True
            continue
        if in_zero:
            t = s.strip()
            if t.startswith("tests/") and t.endswith(".py"):
                zero.append(t)
                continue
            if t.startswith("===") or not t:
                if t.startswith("==="):
                    in_zero = False
                continue
            in_zero = False
        m = LINE.match(s)
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
    return files, tot, zero


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--baseline", help="hermes-agent 克隆路径,用于静态数零执行文件的 def test_")
    args = ap.parse_args()

    lines = Path(args.log).read_text(encoding="utf-8", errors="replace").split("\n")
    files, tot, zero = parse(lines)

    whole = {f: c for f, c in files.items() if c["✓"] == 0 and c["s"] > 0}
    part = {f: c for f, c in files.items() if c["✓"] > 0 and c["s"] > 0}

    print(f"文件数(有进度行)={len(files)}")
    print(f"passed={tot['✓']}  failed={tot['✗']}  skipped={tot['s']}")
    print(f"含 skip 的文件={len(whole) + len(part)}"
          f"(整文件跳过 {len(whole)} / 部分跳过 {len(part)})")
    print(f"零执行文件={len(zero)}")

    print("\n=== 整文件跳过(passed=0 且 skipped>0)逐个点名 ===")
    for f, c in sorted(whole.items(), key=lambda x: -x[1]["s"]) or [(None, None)]:
        if f is None:
            print("(无)")
            break
        print(f"  {c['s']:>3} 个用例被跳过  {f}")
    print(f"整文件跳过合计掩盖 {sum(c['s'] for c in whole.values())} 个用例")

    print("\n=== 零执行(连进度行都没有)逐个点名 ===")
    total_hidden = 0
    for f in sorted(zero) or []:
        n = ""
        if args.baseline:
            p = Path(args.baseline) / f
            if p.exists():
                k = len(DEF_TEST.findall(p.read_text(encoding="utf-8", errors="replace")))
                total_hidden += k
                n = f"  (静态 def test_ = {k})"
        print(f"  {f}{n}")
    if not zero:
        print("(无)")
    if args.baseline:
        print(f"零执行合计掩盖 ≥{total_hidden} 个用例(静态计数,下界)")
    else:
        print("(未给 --baseline,零执行掩盖的用例数不报 —— 不猜)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
