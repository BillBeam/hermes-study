#!/usr/bin/env python3
"""R11E · 原则层编辑正文里的「第 N 章」自检。

`scripts/verify_chapter_order.py` 的第 4 项只判**同一行里同时出现「第 N 章」和某份成品章
文件名**的那些提及;没点名文件的记 `UNVERIFIABLE` 并计数,**它不猜**(这是对的)。
本轮 `reading/02-principles.md` 里有一批这样的提及:它们出现在**编辑正文**里
(「第 15 章『这是本簇缺陷的共同根因』」),而同一行不会再写一遍文件名——写了就毁了可读性。

于是这批数字处在一个熟悉的位置:**它在分母里(被计为 UNVERIFIABLE),但没有任何东西校验它**。
本脚本补这一格,判据是**声明式**的,不靠嗅探:

    一条原则的编辑正文里提到「第 N 章」,那么第 N 章必须出现在**这条原则自己的 src 声明**里。

这条判据对本轮的写法是**充分**的,因为编辑正文引用某一章,正是因为那一章是它的源之一;
反过来,如果哪天有人要在正文里引用一个不属于本条源的章(比如做对比),
这个检查会报出来,那时应当**显式给它一个豁免声明**,而不是放宽判据 ——
与 CLAUDE.md 给 ```text 豁免、给 ccTLD 守卫定的是同一条原则。

**覆盖面要如实说**:本脚本只查 `data/r11e/principles-src.md` 的编辑正文,
不查 `chapters/`(那是 `verify_chapter_order.py` 的事),也不查本轮报告与底稿。

用法:
    python3 data/r11e/probes/editorial_chapter_refs.py
"""
import re
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
SRC = STUDY / "data" / "r11e" / "principles-src.md"
ORDER = STUDY / "data" / "chapter-order.tsv"

ENTRY = re.compile(r"^## ([PC]\d+)\s*·\s*(.+?)\s*$")
SRC_LINE = re.compile(r"^src:\s*(chapters/[^\s]+\.md)\s*§")
MENTION = re.compile(r"第\s*(\d+)\s*章")
# 「第 N 章」也会出现在字段行(merge-why)里,那同样是编辑正文,一并查。
FIELD_PROSE = ("merge-why:", "ruling:", "note:", "scope:")


def chapter_map():
    rows = ORDER.read_text(encoding="utf-8").split("\n")
    return {int(r.split("\t")[0]): r.split("\t")[1] for r in rows[1:] if r.strip()}


def main():
    cmap = chapter_map()
    entries, cur = [], None
    for line in SRC.read_text(encoding="utf-8").split("\n"):
        m = ENTRY.match(line)
        if m:
            cur = {"id": m.group(1), "srcs": set(), "prose": []}
            entries.append(cur)
            continue
        if cur is None:
            continue
        s = SRC_LINE.match(line)
        if s:
            cur["srcs"].add(s.group(1))
            continue
        if line.startswith(("family:", "src:", "merge:", "conflict-with:")):
            continue
        if line.startswith(FIELD_PROSE) or not line.startswith(tuple(
                f"{k}:" for k in ("family", "src", "merge", "conflict-with"))):
            cur["prose"].append(line)

    total, bad, unknown = 0, [], []
    for e in entries:
        for line in e["prose"]:
            for m in MENTION.finditer(line):
                n = int(m.group(1))
                total += 1
                if n not in cmap:
                    unknown.append((e["id"], n, line.strip()[:70]))
                elif cmap[n] not in e["srcs"]:
                    bad.append((e["id"], n, cmap[n], line.strip()[:70]))

    print(f"条目 {len(entries)} 条;编辑正文里的「第 N 章」提及 {total} 处")
    print(f"章号不存在:{len(unknown)}   指向的章不在本条 src 里:{len(bad)}")
    for eid, n, line in unknown:
        print(f"  [UNKNOWN] {eid} 第 {n} 章 —— {line}")
    for eid, n, rel, line in bad:
        print(f"  [NOT-A-SOURCE] {eid} 第 {n} 章({rel})不在本条 src 声明里 —— {line}")
    if unknown or bad:
        print("FAIL")
        return 1
    print("OK: 编辑正文里每一处「第 N 章」都指向本条原则自己的源章")
    return 0


if __name__ == "__main__":
    sys.exit(main())
