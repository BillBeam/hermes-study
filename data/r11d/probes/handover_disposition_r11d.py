#!/usr/bin/env python3
"""移交条目枚举与处置基数(R11D 片 C)。

**不改 R11C 的普查器**,而是 import 它,只换两样东西:

1. **案号正则**。R11C 版的 `ID_RE` 是
   `H-[A-Za-z0-9]+-[a-z]\\b|H-R8FIX-[a-z]\\b|H-\\d{1,2}`,
   而 R11B 立的案号纪律要求**片内铸号必须带片标识**(`H-R11C-M-a`、`H-R11B-B1-a`)。
   这两条互相打架:`H-R11C-M-a` 里 `[A-Za-z0-9]+` 吃掉 `R11C` 之后,
   下一段是 `-M-a`,而 `[a-z]` 匹配不到大写的 `M` —— **整个片内号域对普查不可见**。
   本探针把中间段改成可重复的 `(?:[A-Za-z0-9]+-)+`。

2. **语料**。R11C 版按 `reports/round-*.md` 逐轮取「该轮报告 + 该轮同名底稿」,
   于是**一轮的底稿在该轮报告落盘之前不进语料**。R11D 的报告尚未写,
   `notes/r11d-*.md` 因此一条都读不到。`--with-round r11d` 把该轮底稿追加到语料末尾
   (追加在末尾 = 时间序上最新,与报告落盘后的效果一致)。

用法:

    python3 data/r11d/probes/handover_disposition_r11d.py                 # R11C 语料 + 宽正则
    python3 data/r11d/probes/handover_disposition_r11d.py --legacy-id     # R11C 语料 + R11C 正则(还原基数)
    python3 data/r11d/probes/handover_disposition_r11d.py --exclude round-11d          # 钉住语料(前读数)
    python3 data/r11d/probes/handover_disposition_r11d.py --exclude round-11d \
        --add-note notes/r11d-raw-handover-disposition.md                             # 后读数
    python3 data/r11d/probes/handover_disposition_r11d.py --wide-hints                # 再补认不出的移交表表头
    python3 data/r11d/probes/handover_disposition_r11d.py --mint          # 每个案号的首次出现处

不依赖会话专属路径:仓库根由 R11C 探针从自身位置推出。
"""
from __future__ import annotations

import argparse
import importlib.util
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = pathlib.Path(subprocess.run(
    ["git", "-C", str(HERE.parent), "rev-parse", "--show-toplevel"],
    capture_output=True, check=True).stdout.decode().strip())
CENSUS = ROOT / "data" / "r11c" / "probes" / "handover_census_r11c.py"

_spec = importlib.util.spec_from_file_location("handover_census_r11c", CENSUS)
census = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(census)

LEGACY_ID_RE = census.ID_RE
# 中间段可重复 -> 覆盖 H-R11C-M-a / H-R11B-B1-a;末段仍限单个小写字母,
# 避免把 `H-R11C-D-` 这类残缺写法或普通英文吃进来。
WIDE_ID_RE = re.compile(
    r"H-(?:[A-Za-z0-9]+-)+[a-z]\b|(?<![\w-])H-\d{1,2}(?![\w-])")

# R11C 版的 HANDOVER_HINTS 只有「去向」「建议轮次」两个词,于是历史上写成
# 「建议下一轮做什么」「建议接手方」「建议动作」「建议」的移交表**表头认不出**,
# 整张表以 UNCLASSIFIED 出现(R11C 已让它可见,但没判)。这里按表头逐类补:
# 只补**明确是「这条接下来交给谁 / 下一轮做什么」**的列名,不补含糊的。
WIDE_HANDOVER_HINTS = census.HANDOVER_HINTS + (
    "建议下一轮", "建议接手", "建议动作", "建议", "移交至", "本片定档")


def sources(with_round: str | None, legacy_corpus: bool,
            exclude: str = "", add_notes: list[str] | None = None):
    """语料。

    `exclude` / `add_notes` 是为了让读数**可重跑**:本轮有三片并发在写
    `reports/` 与 `notes/`,而语料是「全部报告 + 同轮底稿」——不钉住它,
    同一条命令隔十分钟就给出另一个数(CLAUDE.md「量『之前』的命令不许钉在
    会移动的引用上」)。前读数用 `--exclude round-11d` 把本轮整轮排除;
    后读数用同一条 exclude **再显式追加**要量的那一份底稿。
    """
    order = sorted((census.stamp(f"reports/{p.name}"), p.name)
                   for p in census.REPORTS.glob("round-*.md"))
    out: list[pathlib.Path] = []
    for _, name in order:
        if exclude and exclude in name:
            continue
        out.append(census.REPORTS / name)
        out += census.companion_notes(census.round_of_report(name), legacy_corpus)
    if with_round:
        key = with_round.lower().removeprefix("r")
        out += [p for p in sorted(census.NOTES.glob(f"r{key}-*.md")) if p not in out]
    for rel in add_notes or []:
        p = ROOT / rel
        if p.exists() and p not in out:
            out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--legacy-id", action="store_true")
    ap.add_argument("--with-round", default=None)
    ap.add_argument("--mint", action="store_true")
    ap.add_argument("--open-only", action="store_true")
    ap.add_argument("--wide-hints", action="store_true",
                    help="把「建议下一轮/建议接手/建议动作/建议/移交至」也认作移交表表头")
    ap.add_argument("--exclude", default="",
                    help="报告文件名含该子串的整轮排除(钉住语料用)")
    ap.add_argument("--add-note", action="append", default=[],
                    help="显式追加一份底稿到语料末尾(可重复)")
    args = ap.parse_args()

    census.ID_RE = LEGACY_ID_RE if args.legacy_id else WIDE_ID_RE
    if args.wide_hints:
        census.HANDOVER_HINTS = WIDE_HANDOVER_HINTS

    events: dict[str, list[tuple[str, str, str, str]]] = {}
    unknowns = []
    scanned = []
    for src in sources(args.with_round, legacy_corpus=False,
                        exclude=args.exclude, add_notes=args.add_note):
        rel = src.relative_to(ROOT).as_posix()
        scanned.append(rel)
        evs, unk = census.scan(src)
        for kind, hid, note, heading in evs:
            events.setdefault(hid, []).append((rel, kind, note, heading))
        unknowns += [(rel, ln, hdr, ids) for ln, hdr, ids in unk]

    if args.mint:
        for hid in sorted(events):
            first = events[hid][0]
            last = events[hid][-1]
            print(f"{hid:16s} 铸于={first[0]:52s} 末次={last[0]:52s} "
                  f"{'OPEN' if last[1] == 'handover' else 'CLOSED'}")
        print(f"\n案号 {len(events)} 个")
        return 0

    rows = []
    held = []
    for hid, evs in events.items():
        last_kind, last_note, last_head = evs[-1][1], evs[-1][2], evs[-1][3]
        is_open = last_kind == "handover"
        if not is_open:
            hit = next((h for h in census.REVIEW_HINTS if h in last_note), None) or \
                  next((h for h in census.REVIEW_HINTS if h in last_head), None)
            if hit:
                held.append((hid, hit, (last_note or last_head)[:88]))
        rows.append((hid, evs[0][0], evs[-1][0], is_open))

    for hid, first, last, is_open in sorted(rows, key=lambda r: (not r[3], r[0])):
        if args.open_only and not is_open:
            continue
        print(f"{hid:16s} 铸于={first:52s} 末次={last:52s} "
              f"{'OPEN' if is_open else 'CLOSED'}")
    if held:
        print("\nREVIEW(记 CLOSED、处置文本带续转类词根;**不自动改判**):")
        for hid, hit, note in sorted(held):
            print(f"  {hid:16s} [{hit}] {note}")
    print(f"\n口径=正则{'R11C' if args.legacy_id else 'R11D(宽)'}"
          f"/语料{'R11C' if not args.with_round else 'R11C+' + args.with_round} "
          f"扫描文件 {len(scanned)} 份;总计 {len(rows)} 条,"
          f"未结清 {sum(1 for r in rows if r[3])} 条,"
          f"另有 {len(held)} 条入 REVIEW 队列(仍记 CLOSED);"
          f"认不出表头但含案号的表格行 {len(unknowns)} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
