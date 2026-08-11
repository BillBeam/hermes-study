#!/usr/bin/env python3
"""R11F · 台账 round 列「同层同状态、多归属」普查(验收项 2 的后半)。

## 这个探针在问什么

R11F 开工时的形态:`layer=L2 && status=R1-inventoried` 这 243 个文件,
`round` 列**分裂成两个值**(`UNCLAIMED` 227 / `R6` 16)。同一批文件、同一处理状态,
却有两个归属。验收要求回答「同类分裂在台账其他位置是否还存在」。

**判据(写死,不靠嗅探)**:把台账按 `(layer, status)` 分组,组内 `round` 的
**去重值个数 > 1** 即记一次分裂。这条判据没有解释空间 —— 它不问"这个分裂合不合理",
只问"它在不在"。合不合理是人的事(见 CLAUDE.md「机械判据不得用词根去判开/闭这类语义」)。

## 为什么按 (layer, status) 而不是别的键

`round` 与 `status` 记的是两件不同的事:
  * `status` = **事实**,这个文件被学到什么程度了;
  * `round`  = **计划**,它还挂在哪一轮的钩上(R8D 立、R11A 复述的语义)。
一组文件如果 `status` 相同(处理程度一样)、`layer` 相同(该受同一套判据约束),
那它们的 `round` 本该一致;不一致就意味着**台账在用两个名字记同一件事**,
而这正是 R11F 开工时那 227/16 的形状。

## 报数口径

分裂组分三档打印,**三档都打印,不做筛选**:
  * `未开工`   —— status 为 `R1-inventoried`:分裂**仍在生效**,会影响下一轮按 round 报数;
  * `已交付`   —— status 非 `R1-inventoried`:分裂是**历史留痕**,那几轮各自做完了自己那份;
  * 其中 `-` / `with-module` / `UNCLAIMED` 这三个**非轮次占位符**单独标注 ——
    它们不是"某一轮",混在一起数会把占位符当成归属。

    python3 data/r11f/probes/round_split_census.py [data/ledger.tsv]
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

PLACEHOLDERS = {"-", "with-module", "UNCLAIMED"}


def main() -> int:
    led = Path(sys.argv[1] if len(sys.argv) > 1 else "data/ledger.tsv")
    groups: dict[tuple[str, str], dict[str, list]] = defaultdict(lambda: defaultdict(list))
    with led.open(newline="") as f:
        r = csv.reader(f, delimiter="\t")
        next(r)
        for path, _kind, lines, layer, rnd, status in r:
            groups[(layer, status)][rnd].append((path, int(lines)))

    split = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"(layer,status) 组数 = {len(groups)};其中 round 分裂的组 = {len(split)}")
    print()
    for (layer, status), byround in sorted(split.items()):
        nf = sum(len(v) for v in byround.values())
        nl = sum(n for v in byround.values() for _, n in v)
        kind = "未开工" if status == "R1-inventoried" else "已交付"
        print(f"[{kind}] layer={layer} status={status}  共 {nf} 文件 / {nl} 行,"
              f"{len(byround)} 个 round 值:")
        for rnd, v in sorted(byround.items(), key=lambda x: -len(x[1])):
            tag = "  <- 占位符,非轮次" if rnd in PLACEHOLDERS else ""
            print(f"    {rnd:<14} {len(v):>5} 文件 {sum(n for _, n in v):>8} 行{tag}")
        print()

    live = [k for k in split if k[1] == "R1-inventoried"]
    print(f"仍在生效的分裂(status=R1-inventoried)= {len(live)} 组")
    for layer, status in sorted(live):
        print(f"    layer={layer} status={status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
