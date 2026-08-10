#!/usr/bin/env python3
"""R11D · 轮次落点表自检:`data/round-registry.tsv` 的每一行都指向真实文件。

**为什么要有这张表。** 轮次编号此前和章号一样**没有单一落点**:它散在分支名、
报告文件名、`data/ledger.tsv` 的 `round` 列、以及各轮 PR 标题里。而 `data/ledger.tsv`
的 `round` 列是**逐文件**的——它回答「这个文件计划在哪一轮读」,不回答「一共有哪些轮」。
R11D 这种**不覆盖任何基线文件**的元工作轮,在那一列里正确的取值是「一行都不占」;
把 R11D 写进任何一行都会是 `CLAUDE.md` 明令禁止的「为使账面好看而调整」。
所以轮次编号落在这张表上,与 `data/chapter-order.tsv` 之于章号同型。

检查三项:报告存在、成品章存在、与 `data/chapter-order.tsv` 的轮次映射不矛盾。

**已知且有意的两个豁免**:
  - `reports/round-1-capabilities-full.md` 是 R1 的**纯数据附卷**(`CLAUDE.md` 已就
    「首句结论」一项给过它同样的豁免),不单独占一行。
  - 元工作轮 / 评审处置轮的 `chapter` 列为 `-`:它们按设计不产出成品章。

用法:
    python3 data/r11d/probes/round_registry_check.py
"""
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
APPENDIX = {"reports/round-1-capabilities-full.md"}


def load(rel, cols):
    out = []
    for i, line in enumerate((STUDY / rel).read_text(encoding="utf-8").split("\n")):
        if not i or not line.strip():
            continue
        f = line.split("\t")
        if len(f) != cols:
            sys.exit(f"FAIL: {rel} 第 {i+1} 行字段数 {len(f)} != {cols}")
        out.append(f)
    return out


def main():
    reg = load("data/round-registry.tsv", 4)
    chap = {r[2]: r[1] for r in load("data/chapter-order.tsv", 4)}
    bad = []
    for rnd, rep, ch, _ in reg:
        if rep != "-" and not (STUDY / rep).is_file():
            bad.append(f"{rnd}: 报告不存在 {rep}")
        if ch != "-" and not (STUDY / ch).is_file():
            bad.append(f"{rnd}: 成品章不存在 {ch}")
        if rnd in chap and chap[rnd] != ch:
            bad.append(f"{rnd}: 与 chapter-order 冲突({chap[rnd]} vs {ch})")
    for rnd in chap:
        if rnd not in {r[0] for r in reg}:
            bad.append(f"chapter-order 有轮次 {rnd},registry 没有")
    listed = {r[1] for r in reg}
    orphan = sorted(p.relative_to(STUDY).as_posix()
                    for p in (STUDY / "reports").glob("*.md")
                    if p.relative_to(STUDY).as_posix() not in listed | APPENDIX)

    print(f"registry 行数={len(reg)}  成品章轮次={len(chap)}  未列报告={len(orphan)}")
    if orphan:
        print("  未被 registry 引用的报告:" + ", ".join(orphan))
    for b in bad:
        print("  [BAD] " + b)
    if bad or orphan:
        print(f"FAIL: {len(bad) + len(orphan)} 项")
        return 1
    print("OK: 轮次落点表与磁盘、与章序落点表一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
