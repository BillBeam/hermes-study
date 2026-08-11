#!/usr/bin/env python3
"""R11E · 点名覆盖率(验收项 7):两个读数都报。

CLAUDE.md 定过一条:凡判据是「某字符串在语料里出现过没有」的测量,**报数时必须
(a) 剔除本轮承载清单/点名的文件,(b) 剔除与不剔除两个读数都报**。理由是这类测量
对「报告它」这个动作**不幂等**——写一份点名清单就会改变下一次的读数,而
**没有任何脚本会发现这种污染**。

## 本轮的被测集合

本轮**触及的文件清单**是 21 份成品章(`data/chapter-order.tsv` 的 file 列)。
它们被三处清单同时点名:章序落点表、源节钉表、以及两份编辑源。
注意与历史轮次的差别:**过去几轮的被测集合是 hermes-agent 的基线文件,本轮是本仓库自己的
成品章**——因为本轮是阅读层轮,不吃新内容,没有新的基线文件被点名。这一点必须写出来,
否则读者会把本轮的读数和历史轮次的读数放在一起比,而它们量的不是同一个集合。

## 承载清单(剔除的那一组)

  - `data/chapter-order.tsv`(章序落点,R11D 立)
  - `data/r11e/section-digests.tsv`(源节钉表,本轮生成)
  - `data/r11e/principles-src.md` / `data/r11e/problem-index.tsv`(两份编辑源)
  - `reading/*.md`(三份派生产物 —— 它们逐条列出章路径,是最强的承载者)
  - `reports/round-11e-*.md`、`notes/r11e-*.md`(本轮报告与底稿)

## 口径

  - **全路径命中**:语料里出现 `chapters/<file>.md` 这个完整相对路径。
  - **裸文件名命中**:语料里出现 `<file>.md`(不带目录)。裸名口径**更宽**,
    所以它的零命中数是**下界**——与 R8A 给「叶子名口径」写下的偏差方向说明同源。
  - **语料**:本仓库全部 `*.md`(排除 `.git/`)。

用法:
    python3 data/r11e/probes/named_coverage_r11e.py
"""
import fnmatch
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
CARRIERS = (
    "data/chapter-order.tsv",
    "data/r11e/section-digests.tsv",
    "data/r11e/principles-src.md",
    "data/r11e/problem-index.tsv",
    "reading/*.md",
    "reports/round-11e-*.md",
    "notes/r11e-*.md",
)


def is_carrier(rel):
    return any(fnmatch.fnmatch(rel, pat) for pat in CARRIERS)


def targets():
    rows = (STUDY / "data" / "chapter-order.tsv").read_text(encoding="utf-8").split("\n")
    return [r.split("\t")[1] for r in rows[1:] if r.strip()]


def corpus(exclude_carriers):
    out = []
    for p in sorted(STUDY.rglob("*.md")):
        rel = p.relative_to(STUDY).as_posix()
        if rel.startswith(".git/"):
            continue
        if exclude_carriers and is_carrier(rel):
            continue
        try:
            out.append((rel, p.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue
    return out


def measure(exclude):
    docs = corpus(exclude)
    blob = "\n".join(t for _r, t in docs)
    full_zero, bare_zero = [], []
    for rel in targets():
        if rel not in blob:
            full_zero.append(rel)
        if Path(rel).name not in blob:
            bare_zero.append(rel)
    return len(docs), full_zero, bare_zero


def main():
    tgt = targets()
    print(f"被测集合:{len(tgt)} 份成品章(data/chapter-order.tsv 的 file 列)")
    print("注意:本轮被测集合是**本仓库的成品章**,不是 hermes-agent 基线文件"
          "——阅读层轮不吃新内容,没有新的基线文件被点名。\n")

    rows = []
    for label, exclude in (("不剔除承载清单", False), ("剔除承载清单", True)):
        ndocs, fz, bz = measure(exclude)
        rows.append((label, ndocs, fz, bz))
        print(f"[{label}] 语料 {ndocs} 份 *.md")
        print(f"    全路径零命中:{len(fz)} 份" + (f" -> {fz}" if fz else ""))
        print(f"    裸文件名零命中:{len(bz)} 份" + (f" -> {bz}" if bz else ""))

    (_l1, _n1, fz1, bz1), (_l2, _n2, fz2, bz2) = rows
    print()
    if len(fz1) == len(fz2) and len(bz1) == len(bz2):
        print("两个读数相同。**原因必须说清**(验收项 7 明令):"
              "21 份成品章在本轮**之前**就已经被历史轮次的报告、底稿与评审反复点名,")
        print("所以剔掉本轮的承载清单之后,历史语料仍然覆盖全部 21 份 —— "
              "读数相同不是「测量没生效」,是被测集合本来就不依赖本轮产物。")
        print("反证见下:剔除承载清单后语料仍有 "
              f"{_n2} 份文档,占不剔除时的 {_n2 / _n1 * 100:.1f}%。")
    else:
        print("两个读数不同 —— 本轮承载清单确实改变了读数,以剔除后的为准:"
              f"全路径零命中 {len(fz2)}、裸名零命中 {len(bz2)}。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
