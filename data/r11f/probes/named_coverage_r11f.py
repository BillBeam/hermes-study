#!/usr/bin/env python3
"""R11F · 点名覆盖率(验收项 6):两个读数都报。

CLAUDE.md 定过一条:凡判据是「某字符串在语料里出现过没有」的测量,**报数时必须
(a) 剔除本轮承载清单/点名的文件,(b) 剔除与不剔除两个读数都报**。理由是这类测量
对「报告它」这个动作**不幂等** —— 写一份点名清单就会改变下一次的读数,而
**没有任何脚本会发现这种污染**。

## 被测集合

本轮范围内的 **243 个基线文件**(`data/r11f/slices/*.txt` 六片合并),
即台账开工时 `layer=L2 && status=R1-inventoried` 的全部文件。

## 承载清单(剔除的那一组)—— 本轮为什么它一定会咬

R11E 那版探针的语料只扫 `*.md`,而它列的承载者里有 `.tsv`,
于是那几条剔除**实际是空操作**。本轮的最强承载者恰恰不是 `.md`:

  - `data/r11f/slices/{A..F}.txt` —— 六片派工清单,**逐字列出全部 243 个全路径**;
  - `data/ledger.tsv` / `data/inventory.tsv` —— 全仓盘点,同样逐个列全;
  - `data/r11f/dispatch-brief.md` —— 派工书;
  - `reports/round-11f-*.md`、`notes/r11f-*.md`、`chapters/r11f-*.md` —— 本轮产出。

所以语料**必须**包含 `.tsv` / `.txt` / `.py`,否则这条规矩在本轮又是空转。
这一点本身是 R11E 那版的一个缺陷,记在这里而不是改它的历史产出。

## 口径

  - **全路径命中**:语料里出现 `plugins/...` 这个完整相对路径。
  - **裸文件名命中**:语料里出现 `<basename>`(不带目录)。裸名口径**极宽** ——
    本轮有 63 个 `plugin.yaml`、大量 `__init__.py` / `README.md` / `adapter.py`,
    一次命中就能让几十个文件"看起来被点到了"。所以**裸名零命中数是下界,
    不能当成覆盖率**;它唯一的用处是给出"连这么宽的口径都没命中"的那一批。
  - **语料**:本仓库全部 `*.md` / `*.tsv` / `*.txt` / `*.py`(排除 `.git/`)。

    python3 data/r11f/probes/named_coverage_r11f.py [--list]
"""
import fnmatch
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
EXTS = ("*.md", "*.tsv", "*.txt", "*.py")
CARRIERS = (
    "data/r11f/slices/*.txt",
    "data/r11f/dispatch-brief.md",
    "data/ledger.tsv",
    "data/inventory.tsv",
    "reports/round-11f-*.md",
    "notes/r11f-*.md",
    "chapters/r11f-*.md",
    "data/r11f/probes/*.py",
)


def is_carrier(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in CARRIERS)


def targets() -> list[str]:
    out = []
    for f in sorted((STUDY / "data/r11f/slices").glob("*.txt")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(line.split("\t")[0])
    return sorted(set(out))


def corpus(exclude_carriers: bool):
    docs = []
    for ext in EXTS:
        for p in sorted(STUDY.rglob(ext)):
            rel = p.relative_to(STUDY).as_posix()
            if rel.startswith(".git/"):
                continue
            if exclude_carriers and is_carrier(rel):
                continue
            try:
                docs.append((rel, p.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError):
                continue
    return docs


def measure(exclude: bool):
    docs = corpus(exclude)
    blob = "\n".join(t for _r, t in docs)
    full_zero = [r for r in targets() if r not in blob]
    bare_zero = [r for r in targets() if Path(r).name not in blob]
    return len(docs), full_zero, bare_zero


def main() -> int:
    show = "--list" in sys.argv
    tgt = targets()
    print(f"被测集合:{len(tgt)} 个基线文件(R11F 范围,data/r11f/slices/*.txt 合并)\n")

    res = []
    for label, exclude in (("不剔除承载清单", False), ("剔除承载清单", True)):
        ndocs, fz, bz = measure(exclude)
        res.append((ndocs, fz, bz))
        print(f"[{label}] 语料 {ndocs} 份({'/'.join(e.lstrip('*') for e in EXTS)})")
        print(f"    全路径零命中:{len(fz)} / {len(tgt)}")
        print(f"    裸文件名零命中:{len(bz)} / {len(tgt)}")
        if show and fz:
            for r in fz:
                print(f"        {r}")

    (n1, fz1, bz1), (n2, fz2, bz2) = res
    print()
    if (len(fz1), len(bz1)) == (len(fz2), len(bz2)):
        print("两个读数相同 —— **原因必须说清**(CLAUDE.md 明令)。")
        print(f"剔除后语料仍有 {n2} 份(占 {n2 / n1 * 100:.1f}%),"
              "若该数接近 100% 则说明承载清单在语料里占比过小、这条剔除没咬住;")
        print("若剔除后语料明显变小而读数不变,才说明被测集合本来就不依赖本轮产物。")
    else:
        print("两个读数不同 —— 本轮承载清单确实改变了读数,**以剔除后的为准**:")
        print(f"    全路径零命中 {len(fz2)} / {len(tgt)}、裸名零命中 {len(bz2)} / {len(tgt)}")
        print(f"    (不剔除时分别是 {len(fz1)} 与 {len(bz1)};语料 {n1} -> {n2} 份)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
