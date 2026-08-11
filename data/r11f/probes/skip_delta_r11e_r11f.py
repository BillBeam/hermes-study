#!/usr/bin/env python3
"""R11F · 「整文件跳过」逐文件对比 R11E,定位 skipped 239 -> 247 的差额来源。

## 为什么要做这个对比

R11E 报 `skipped=239`,R11F 报 `247`;而 `passed=25637` / `failed=75` **两轮逐个相同**。
CLAUDE.md 明令:**同一指标的多次测量,不同数值不得表述为「读数相同」**,
要写清各自口径。所以先要回答一个前置问题:**差额是"方法变了"还是"跑出来就不一样"?**

**方法这一侧已经排除**:R11F 把解析收进 `scripts/test_totals.py`(结清 `H-R11E-M-c`),
拿 R11E 那版探针与新脚本**跑同一份 R11F 日志**,两者都给 `skipped=247` ——
解析口径是同一个,差额不来自方法。

本探针回答剩下那一半:差额落在哪些文件上。
**R11E 的完整日志没有落库**(它只留了 `data/r11e/tests-full-tail.log`,是个 tail),
所以对比只能拿它报告里那张**整文件跳过表**做,覆盖不到 43 个"部分跳过"的文件 ——
这个覆盖限度必须写出来,否则读者会以为差额已被完全归因。

## 判据

从 `reports/round-11e-reading-layer.md` 的整文件跳过表解析
`| N | \`tests/...\` |` 行,与本轮日志的同类文件逐个比对。

    python3 data/r11f/probes/skip_delta_r11e_r11f.py
"""
import re
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(STUDY / "scripts"))
from test_totals import parse  # noqa: E402  判据从生产者 import,不另起口径

R11E_REPORT = STUDY / "reports/round-11e-reading-layer.md"
R11F_LOG = STUDY / "data/r11f/tests-full.log"
ROW = re.compile(r"^\|\s*(?P<n>\d+)\s*\|\s*`(?P<f>tests/[\w./-]+\.py)`\s*\|\s*$")


def main() -> int:
    prev = {}
    for line in R11E_REPORT.read_text(encoding="utf-8").split("\n"):
        m = ROW.match(line)
        if m:
            prev[m.group("f")] = int(m.group("n"))

    files, tot, _zero = parse(R11F_LOG.read_text(encoding="utf-8",
                                                 errors="replace").split("\n"))
    cur = {f: c["s"] for f, c in files.items() if c["✓"] == 0 and c["s"] > 0}

    print(f"R11E 表内整文件跳过 {len(prev)} 文件 / {sum(prev.values())} 用例")
    print(f"R11F 本轮日志整文件跳过 {len(cur)} 文件 / {sum(cur.values())} 用例")
    print(f"R11F 全量 skipped={tot['s']}(含 43 个部分跳过的文件,本对比覆盖不到)\n")

    only_prev = sorted(set(prev) - set(cur))
    only_cur = sorted(set(cur) - set(prev))
    print(f"仅 R11E 有的文件 = {len(only_prev)}{only_prev}")
    print(f"仅 R11F 有的文件 = {len(only_cur)}{only_cur}\n")

    moved = [(f, prev[f], cur[f]) for f in sorted(set(prev) & set(cur)) if prev[f] != cur[f]]
    print(f"两轮都在、但用例数变了的文件 = {len(moved)}")
    for f, a, b in sorted(moved, key=lambda x: -(x[2] - x[1])):
        print(f"  {a:>3} -> {b:>3}  ({b - a:+d})  {f}")
    print(f"\n整文件跳过这一档的净差额 = {sum(cur.values()) - sum(prev.values()):+d}")
    print(f"全量 skipped 的净差额   = {tot['s'] - 239:+d}(R11E 报 239)")
    print("差额未被本对比解释的部分 = "
          f"{(tot['s'] - 239) - (sum(cur.values()) - sum(prev.values())):+d}"
          "(落在 43 个部分跳过的文件上,R11E 未逐个落库,原理上比不了)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
