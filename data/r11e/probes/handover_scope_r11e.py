#!/usr/bin/env python3
"""R11E 片 C:把「R11D 之后仍需有人做实事的移交条目」机械导出成一张工作底表。

**本探针只负责发现与排队,不判开闭、不判归属。** 归属(这条是不是 R11E 的)由人读原文判,
写在 `notes/r11e-raw-handover.md` 里。这是 `CLAUDE.md`「机械判据不得用词根去判『开/闭』
这类语义」的直接后果 —— R11C 那份词根表 13 条命中里 6 条是假阳性,全栽在
「短语被从它的否定里摘出来」。

## 口径(三条,都要能被复述)

1. **语料**:只读两份 R11D 的**定案层**文件 ——
   `notes/r11d-raw-handover-disposition.md`(140 行处置表)与
   `reports/round-11d-pre-binding-prereq.md` §9.1(17 条新铸号)。
   理由:R11D 是最后一轮有处置表的轮次,**每一条前序移交的最后落点都在这两份里**;
   `--occurrences` 模式会把这个前提**当场验一遍**,而不是假定它 —— 判据是
   「R11D 之后有没有别的轮次把这些号写进过移交/定案表」,**不是**「全仓路径排序最后的
   那一次出现」(路径排序不是时间序,第一版这么写给出 71 条假阳性)。

2. **认表**:只认表头含「处置结论」或「去向」的表(与 R11C 普查器同源的 hint 思路),
   其余表(口径表、类别表、来源表)一律跳过。**认不出表头的表不静默丢弃**,
   `--unclassified` 会把它们打印出来 —— R11C 记过一次「认不出的表整张消失」。

3. **认案号**:用 R11D 片 C 那条宽正则(`H-(?:[A-Za-z0-9]+-)+[a-z]\\b|H-\\d{1,2}`),
   因为 R11C 原正则匹配不了三段式片内号,而案号纪律**要求**片内铸号带片标识。
   本探针**不新造正则**,直接 import R11D 的探针取它的 `WIDE_ID_RE`。

## 用法

    python3 data/r11e/probes/handover_scope_r11e.py              # 导出工作底表(TSV)
    python3 data/r11e/probes/handover_scope_r11e.py --unclassified   # 认不出表头的表格行
    python3 data/r11e/probes/handover_scope_r11e.py --occurrences    # 每个号的最后一次表内出现
    python3 data/r11e/probes/handover_scope_r11e.py --dests           # 去向取值分布

输出列:`case_id  source  dest  one_line  anchor`
(`source` = 该案最后一次出现在移交/定案表的位置;`dest` = 处置结论/去向那一格的开头。)
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = pathlib.Path(subprocess.run(
    ["git", "-C", str(HERE.parent), "rev-parse", "--show-toplevel"],
    capture_output=True, check=True).stdout.decode().strip())

_spec = importlib.util.spec_from_file_location(
    "handover_disposition_r11d",
    ROOT / "data" / "r11d" / "probes" / "handover_disposition_r11d.py")
disp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(disp)
census = disp.census

ID_RE = disp.WIDE_ID_RE
RULING_COL = ("处置结论", "去向")

# 定案层语料:R11D 的两份。顺序即优先级 —— 同一个号两处都有时,取**报告**那一份,
# 因为 §9.1 是该轮收口时的「装订前遗留清单 v2」,比底稿表更晚定稿。
SOURCES = [
    ROOT / "reports" / "round-11d-pre-binding-prereq.md",
    ROOT / "notes" / "r11d-raw-handover-disposition.md",
]

# 本片自己的产出:做「最后一次出现」核验时必须排除,否则本片一写就把读数改了
# (`CLAUDE.md`「量『之前』的命令不许钉在会移动的引用上」)。
SELF = {"notes/r11e-raw-handover.md", "data/r11e/handover-candidates.tsv"}


def cells_of(line: str) -> list[str]:
    return census.split_row(line)


def tables(path: pathlib.Path):
    """产出 (lineno, header_cells, row_cells);表头按 markdown 表格的第一行认。"""
    header: list[str] | None = None
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.lstrip()
        if not s.startswith("|"):
            header = None
            continue
        cells = cells_of(line)
        if header is None:
            header = cells
            continue
        if all(set(c.strip()) <= set("-: ") for c in cells if c.strip()):
            continue  # 分隔行
        yield lineno, header, cells


def is_ruling_table(header: list[str]) -> bool:
    return any(h in c for c in header for h in RULING_COL)


def verdict_cell(header: list[str], cells: list[str]) -> str:
    for i, c in enumerate(header):
        if any(h in c for h in RULING_COL):
            return cells[i] if i < len(cells) else ""
    return ""


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\t", " ")).strip()


def collect() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for src in SOURCES:
        rel = src.relative_to(ROOT).as_posix()
        for lineno, header, cells in tables(src):
            if not is_ruling_table(header) or not cells:
                continue
            ids = ID_RE.findall(cells[0])
            if not ids:
                continue
            cid = ids[0]
            if cid in out:
                continue  # SOURCES 顺序即优先级
            out[cid] = {
                "source": f"{rel}:{lineno}",
                "dest": clean(verdict_cell(header, cells)),
                "one_line": clean(cells[1] if len(cells) > 1 else ""),
                "anchor": clean(cells[2] if len(cells) > 2 else ""),
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unclassified", action="store_true")
    ap.add_argument("--occurrences", action="store_true")
    # CLAUDE.md:「量『之前』的命令不许钉在会移动的引用上」——写法是钉到一个具体提交,
    # 或给普查加 --exclude <本轮>。本轮主线的定案表 notes/r11e-90-handover-rulings.md
    # 一落库,这个读数就从 0 变 25(那 25 条正是主线裁定的),于是这条证据命令当场
    # EVIDENCE-DIFF。加 --exclude 让「主线定案表落库**之前**」这个读数可以稳定重跑。
    ap.add_argument("--exclude", action="append", default=[],
                    help="额外排除的仓库相对路径(可重复)")
    ap.add_argument("--dests", action="store_true")
    args = ap.parse_args()

    rows = collect()

    if args.unclassified:
        n = 0
        for src in SOURCES:
            rel = src.relative_to(ROOT).as_posix()
            for lineno, header, cells in tables(src):
                if is_ruling_table(header) or not cells:
                    continue
                if ID_RE.findall(cells[0]):
                    n += 1
                    print(f"{rel}:{lineno}\t表头[{' / '.join(clean(c) for c in header)}]"
                          f"\t{clean(cells[0])}")
        print(f"# 认不出表头但首格含案号的表格行 {n} 行", file=sys.stderr)
        return 0

    if args.dests:
        c = collections.Counter(
            re.sub(r"[。.].*$", "", v["dest"].replace("**", ""))[:28] for v in rows.values())
        for k, n in c.most_common():
            print(f"{n}\t{k}")
        print(f"# 共 {len(rows)} 条", file=sys.stderr)
        return 0

    if args.occurrences:
        # 「R11D 是最后落点」这个前提要当场验,不能假定。
        #
        # **不能**用「全仓 *.md 里行号最大 / 路径排序最后的一次出现」来定「最后」——
        # 路径排序不是时间序(`reports/round-9d-*` 字符串上排在 `round-11d-*` 之后,
        # 因为 '1' < '9'),本探针第一版就是这么写的,给出 71 条假阳性。
        # 正确判据只有一条:**R11D 之后有没有别的轮次把这些号写进过移交/定案表**。
        # R11D 之后只有 R11E(本轮),所以面就是本轮产出,并排除本片自己的两个文件。
        later_pat = re.compile(r"^(reading/|reports/round-11e|notes/r11e-|data/r11e/)")
        hits = 0
        for p in sorted(ROOT.rglob("*.md")):
            rel = p.relative_to(ROOT).as_posix()
            if rel in SELF or rel in args.exclude or not later_pat.match(rel):
                continue
            for lineno, line in enumerate(p.read_text(encoding="utf-8",
                                                      errors="replace").splitlines(), 1):
                if not line.lstrip().startswith("|"):
                    continue
                cs = cells_of(line)
                if not cs:
                    continue
                for cid in ID_RE.findall(cs[0]):
                    if cid in rows:
                        hits += 1
                        print(f"{rel}:{lineno}\t{cid}")
        print(f"R11D 之后(本轮产出,排除本片自己的两个文件)把这 {len(rows)} 个号"
              f"写进移交/定案表的行数:{hits}")
        return 0

    print("case_id\tsource\tdest\tone_line\tanchor")
    for cid in sorted(rows, key=lambda k: (rows[k]["source"], k)):
        v = rows[cid]
        print("\t".join([cid, v["source"], v["dest"][:120],
                         v["one_line"][:200], v["anchor"][:200]]))
    print(f"# 导出 {len(rows)} 条", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
