#!/usr/bin/env python3
"""移交项普查(R11C 版):修两处让 R11B 自己的 21 条定案在账面上不存在的缺陷。

R11B 定了制度「**结清必须写进它所属轮次的移交/定案表**」,并把 21 条移交逐条
定案写进了报告 §5 与 `notes/r11b-90-handover-rulings.md`。**普查一条都没读到。**
R11C 开工实测(前后对比见 §报数):

  reports/round-11b-review-and-reconciliation.md  ->  解析出 0 条
  notes/r11b-90-handover-rulings.md               ->  解析出 8 条,**全部记成 handover**

两处根因,都不在「扫描面」上 —— R11B 已经把扫描面扩过一次了:

1. **表头分类靠猜,猜不中就整张表消失。** R11B 报告 §5 的表头是
   `| 移交项 | 处置 |`,而 R10B/R11B 版认 ruling 的关键词是
   「处置**结论**」「结论」「复核结果」—— 三个都不含「处置」二字单独出现的情形。
   于是 `kind=None`,整张表被 `continue` 掉,**既不报错也不计数**。
   这与 R10B 那条「白名单外的锚点不是记 UNCHECKED,是根本不被当成锚点,
   连分母都进不去」是同一个物种,换了个部件复发。
   **改法不是继续往关键词表里加词**(那是追不完的靶子,R11B 自己驳过),
   而是:**认不出来的表,只要第一列有案号,就必须以 UNCLASSIFIED 出现在输出里。**
   猜错不可怕,猜错且无声才可怕。

2. **判 handover 优先于判 ruling,于是定案表反而把案子重新打开。**
   `notes/r11b-90-handover-rulings.md:388` 的表头是 `| 移交项 | 去向 | 本轮处置 |`
   —— 它带「去向」列是为了让读者看见这条案子原本要去哪,而分类器先看「去向」,
   就把整张定案表读成了一次新的移交,连「去向」的旧值一起原样登记回去。
   **一张给每一行写了处置的表,就是定案表**,无论它是否同时回显去向。
   故改为:**先判处置,再判去向。**

其余(时间序向 git 要、语料面 = 报告 + 同轮移交定案底稿)沿用 R11B 版,不动。

    python3 data/r11c/probes/handover_census_r11c.py [--open-only] [--dest R11C]
    python3 data/r11c/probes/handover_census_r11c.py --legacy      # R11B 口径,前后对比用
    python3 data/r11c/probes/handover_census_r11c.py --unclassified # 只列认不出的表

不依赖会话专属路径:仓库根从本文件位置推出。
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(subprocess.run(
    ["git", "-C", str(pathlib.Path(__file__).resolve().parent),
     "rev-parse", "--show-toplevel"],
    capture_output=True, check=True).stdout.decode().strip())
REPORTS = ROOT / "reports"
NOTES = ROOT / "notes"

ID_RE = re.compile(r"H-[A-Za-z0-9]+-[a-z]\b|H-R8FIX-[a-z]\b|(?<![\w-])H-\d{1,2}(?![\w-])")
ROUND_KEY = re.compile(r"round-(\d+[a-z]*(?:-fix)?)-")

# 判 ruling 的线索。「处置」单列成词是 R11B 报告 §5 用的写法,R11B 版没有它。
RULING_HINTS = ("处置", "结论", "复核结果", "裁决", "判定", "定案")
HANDOVER_HINTS = ("去向", "建议轮次")

# 一张定案表里的一行,写的未必是「关闭」。R11B §5 就有明写不关闭的:
# H-R9B-f「维持推定,**不关闭**」;另有一小节整节「不归属本轮…给出状态,不做定案」。
# 只看「这一行落在定案表里」就判 CLOSED,会把它们错判成已结清 —— 而错判成已结清
# 正是 H-R10B-a 那三处欠账消失的机制,本轮要清的就是它。
#
# **本探针试过用词表去判开闭,当场翻车,故不采用。** 首次运行 13 条命中里 6 条是
# 假阳性,全部栽在同一个坑:短语被从它的否定里摘了出来。
#   `H-R10E-c` / `H-R8C-a` / `-e` / `-g` / `H-R9A-a` —— 小节标题是
#     「移交项定案(逐条给结论,**无一「续转」了事**)」,命中「续转」,
#     而这句话的意思**恰好相反**。
#   `H-R8B-b`「**关闭**,不再续转」、`H-R9B-c`「**关闭并加重**…不再续转」同理。
# 这就是 r4-90 那条 `iron` 匹配到 `env`**`iron`**`ment` 的自检 grep,换了个部件。
# 一个会把「无一续转」读成「续转」的判据,拿去关闭调查是危险的。
#
# 保留下来的是**well-defined 的机械口径 + 一份交人裁决的队列**:
#   is_open   = 该案最后一次出现在移交表(不是定案表)。判据单一,没有解释空间。
#   REVIEW    = 最后一次是定案、但处置文本里带了这些词根 —— **不改变 is_open**,
#               只是列出来提示「这条值得人去读一眼」,并把命中的词与原文一起打出来,
#               让否定语境当场可见。
# 判开闭是人的事,普查的事是别让任何一条从眼前消失。
REVIEW_HINTS = ("不关闭", "维持去向", "续转", "不做定案", "未结清", "留待",
                "维持推定", "暂不", "不动")

HEADING_RE = re.compile(r"^#{2,4}\s+(.*)$")


def stamp(rel: str) -> int:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "log", "--diff-filter=A", "--follow",
         "--format=%ct", "--", rel],
        capture_output=True, text=True).stdout.split()
    return int(out[-1]) if out else 1 << 62


def round_of_report(name: str) -> str:
    m = ROUND_KEY.search(name)
    return (m.group(1) if m else name).lower().replace("-fix", "fix")


def companion_notes(rkey: str, legacy: bool = False) -> list[pathlib.Path]:
    """该轮报告的同轮底稿。

    R11B 版只认 `r<轮>-9*-*ruling*.md` / `*handover*.md`,于是**片内铸的号一个
    都扫不到** —— `H-R11B-A-c` / `-d` 立在 `notes/r11b-raw-rulings-census.md`,
    那正是本轮要清的两笔真欠账,而它们从来没进过普查的语料。R11B 自己的报告 §9
    也写明「见各底稿 `## 移交` 节」,列了 8 份文件,其中 6 份不匹配旧模式。

    改为扫该轮全部底稿。**这不是又一次「扩扫描面」** —— R11B 驳回的是
    「靠不断追加目录去找**结清**」,而结清的落点已经定死在所属轮次的移交/定案表。
    这里扩的是**发现面**:一条案子铸在哪儿,决定它能不能被看见,
    而铸号发生在片里是制度自己承认的(案号纪律:片内铸号必须带片标识)。
    """
    if legacy:
        pats = (f"r{rkey}-9*-*ruling*.md", f"r{rkey}-9*-*handover*.md")
    else:
        pats = (f"r{rkey}-*.md",)
    seen: dict[str, pathlib.Path] = {}
    for pat in pats:
        for p in NOTES.glob(pat):
            seen[p.name] = p
    return [seen[k] for k in sorted(seen)]


def split_row(line: str) -> list[str]:
    return [p.strip() for p in line.strip().strip("|").split("|")]


def classify_header(cells: list[str], legacy: bool) -> str | None:
    joined = "".join(cells)
    if legacy:
        if "去向" in joined or "建议轮次" in joined:
            return "handover"
        if "处置结论" in joined or "结论" in joined or "复核结果" in joined:
            return "ruling"
        return None
    # R11C:先判处置。一张给每行写了处置的表就是定案表,哪怕它同时回显去向。
    if any(h in joined for h in RULING_HINTS):
        return "ruling"
    if any(h in joined for h in HANDOVER_HINTS):
        return "handover"
    return None


def scan(path: pathlib.Path, legacy: bool = False):
    """返回 (events, unclassified)。

    unclassified 是本版新增的那半边:表头认不出、但第一列出现了案号的表格行。
    R11B 版把它们 `continue` 掉,于是「这张表没有案号」和「这张表我看不懂」
    在输出里长得一模一样。
    """
    out, unknown = [], []
    header: list[str] | None = None
    kind = None
    heading = ""
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.lstrip().startswith("|"):
            header, kind = None, None
            m = HEADING_RE.match(line)
            if m:
                heading = m.group(1)
            continue
        cells = split_row(line)
        if set("".join(cells)) <= set("-: "):
            continue
        if header is None:
            header, kind = cells, classify_header(cells, legacy)
            continue
        if not cells:
            continue
        ids = [i for i in ID_RE.findall(cells[0]) if i]
        if not ids:
            continue
        if kind is None:
            unknown.append((lineno, " | ".join(header)[:70], ids))
            continue
        if kind == "handover":
            col = next((i for i, h in enumerate(header)
                        if h in ("去向", "建议轮次")), 1)
        else:
            col = next((i for i, h in enumerate(header)
                        if any(x in h for x in RULING_HINTS)), len(cells) - 1)
        note = cells[col] if col < len(cells) else ""
        for i in ids:
            out.append((kind, i, note, heading))
    return out, unknown


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--open-only", action="store_true")
    ap.add_argument("--dest")
    ap.add_argument("--reports-only", action="store_true")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--legacy", action="store_true",
                    help="用 R11B 的表头判据,供前后对比")
    ap.add_argument("--unclassified", action="store_true",
                    help="只列表头认不出、但含案号的表")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    order = sorted((stamp(f"reports/{p.name}"), p.name)
                   for p in REPORTS.glob("round-*.md"))
    events: dict[str, list[tuple[str, str, str]]] = {}
    scanned, unknowns = [], []
    for _, name in order:
        if args.exclude and args.exclude in name:
            continue
        sources = [REPORTS / name]
        if not args.reports_only:
            sources += companion_notes(round_of_report(name), args.legacy)
        for src in sources:
            scanned.append(src.relative_to(ROOT).as_posix())
            evs, unk = scan(src, args.legacy)
            for kind, hid, note, heading in evs:
                events.setdefault(hid, []).append((name, kind, note, heading))
            for lineno, hdr, ids in unk:
                unknowns.append((src.relative_to(ROOT).as_posix(), lineno, hdr, ids))

    if args.unclassified:
        for rel, lineno, hdr, ids in unknowns:
            print(f"{rel}:{lineno}  表头[{hdr}]  案号={','.join(ids)}")
        print(f"\n认不出表头但含案号的表格行:{len(unknowns)} 行")
        return 0

    rows = []
    held = []
    for hid, evs in events.items():
        opened = evs[0][0].replace("round-", "").replace(".md", "")
        handovers = [(n, note) for n, k, note, _ in evs if k == "handover"]
        rulings = [(n, note) for n, k, note, _ in evs if k == "ruling"]
        last_kind, last_note, last_head = evs[-1][1], evs[-1][2], evs[-1][3]
        is_open = last_kind == "handover"
        if not is_open and not args.legacy:
            hit = next((h for h in REVIEW_HINTS if h in last_note), None) or \
                  next((h for h in REVIEW_HINTS if h in last_head), None)
            if hit:
                # 不改 is_open。只入队。
                held.append((hid, hit, (last_note or last_head)[:88]))
        rows.append((hid, opened, handovers[-1] if handovers else None,
                     rulings[-1] if rulings else None, is_open))

    sel = [r for r in rows if (r[4] or not args.open_only)]
    if args.dest:
        sel = [r for r in sel if r[4] and r[2] and args.dest in r[2][1]]
    if not args.quiet:
        for hid, opened, lh, lr, is_open in sorted(sel, key=lambda r: (not r[4], r[0])):
            dest = lh[1] if lh else "—"
            ruled = lr[0].replace("round-", "").replace(".md", "") if lr else "—"
            print(f"{hid:14s} 立项={opened:26s} 最后去向={dest:24s} "
                  f"最后定案={ruled:26s} {'OPEN' if is_open else 'CLOSED'}")
    if held and not args.quiet:
        print("\nREVIEW(记 CLOSED,但处置文本带了续转类词根 —— 交人读一眼,"
              "**不自动改判**;注意词根常出现在否定里):")
        for hid, hit, note in sorted(held):
            print(f"  {hid:14s} [{hit}] {note}")
    print(f"\n口径={'R11B(legacy)' if args.legacy else 'R11C'} "
          f"扫描文件 {len(scanned)} 份;总计 {len(rows)} 条,"
          f"未结清 {sum(1 for r in rows if r[4])} 条,"
          f"另有 {len(held)} 条入 REVIEW 队列(仍记 CLOSED);"
          f"认不出表头但含案号的表格行 {len(unknowns)} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
