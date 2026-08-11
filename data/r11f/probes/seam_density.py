#!/usr/bin/env python3
"""R11F · 逐片接缝密度 —— 回答「插件面这一形态的成本驱动是什么」(验收项 5)。

## 背景:「行/片」这个容量单位是怎么来的

R10B 立过一条:L2 的容量单位是**「行/片」而不是「文件/片」**,依据是
R8D 每片 20,838 行、R10 每片 22,145 行,**差 6.3%**;而同两轮的每片文件数差 **2.2 倍**。
R11A 沿用,按 17,500~22,500 行/片 估算切片数。

## 本轮为什么要重新量

插件面的文件构成与前几轮完全不同:一个插件目录 = 一份 `plugin.yaml` 清单 +
一个薄 `__init__.py` + 一份实现。**清单是接缝、实现是体量**,而 L2 判据 2 要穷举的是**接缝**。
于是"行"与"要交付的工作量"在本轮可能脱钩 —— 本探针就是去测这个脱钩有多大。

## 口径

  * `manifest`   —— 片内 `plugin.yaml` 份数;
  * `键次`       —— 片内所有 manifest 的顶层键**出现次数之和**(不是去重后的键种类数)。
                    用出现次数是因为判据 2 要求"每份 manifest 的键集逐份列全",
                    工作量随份数×键数增长,不随键的**种类**增长;
  * `env 条`     —— `requires_env` + `optional_env` 的条目总数(设置向导的输入面);
  * `py 文件`    —— 片内 `.py` 文件数。

    python3 data/r11f/probes/seam_density.py
"""
import collections
import sys
from pathlib import Path

import yaml

STUDY = Path(__file__).resolve().parents[3]
BASELINE = Path("/home/user/hermes-agent")
SLICES = STUDY / "data/r11f/slices"


def main() -> int:
    hdr = f"{'片':<3}{'文件':>6}{'行':>9}{'manifest':>10}{'键次':>7}{'env 条':>8}{'py 文件':>8}{'行/文件':>9}"
    print(hdr)
    tot = collections.Counter()
    for f in sorted(SLICES.glob("*.txt")):
        rows = [l.split("\t") for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        paths = [r[0] for r in rows]
        lines = sum(int(r[1]) for r in rows)
        man = [p for p in paths if p.endswith("plugin.yaml")]
        keys = envs = 0
        for p in man:
            d = yaml.safe_load((BASELINE / p).read_text(encoding="utf-8")) or {}
            keys += len(d)
            for k in ("requires_env", "optional_env"):
                v = d.get(k) or []
                envs += len(v) if isinstance(v, list) else 0
        py = [p for p in paths if p.endswith(".py")]
        print(f"{f.stem:<3}{len(paths):>6}{lines:>9}{len(man):>10}{keys:>7}"
              f"{envs:>8}{len(py):>8}{lines / len(paths):>9.0f}")
        tot["files"] += len(paths); tot["lines"] += lines; tot["man"] += len(man)
        tot["keys"] += keys; tot["envs"] += envs; tot["py"] += len(py)
    print(f"{'合计':<3}{tot['files']:>5}{tot['lines']:>9}{tot['man']:>10}{tot['keys']:>7}"
          f"{tot['envs']:>8}{tot['py']:>8}{tot['lines'] / tot['files']:>9.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
