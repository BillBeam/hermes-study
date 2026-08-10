#!/usr/bin/env python3
"""移交项普查(R11B 版):语料面从 `reports/` 扩到 `reports/ + notes/*-9?-*rulings*`。

R10B 版(`data/r10b/probes/handover_census.py`)只扫 `reports/`。R11A 的报告把
移交与定案**整节挪进了底稿**——报告里写的是「见 notes/r11a-90-handover-rulings.md
§10 的七条,此处不重复」。于是 R11A 的 15 条定案与 7 条新立项**在普查里一条都不存在**,
输出仍停在 66 条,而「漏了一整轮」和「那一轮没有移交项」在输出里长得一模一样。

这正是 R10B 修过的那个物种换了个轴复发:R10 版把报告时间序写成手工清单,于是
R10 自己缺席;R10B 改成向 git 要顺序,却把**语料面**继续钉死在 `reports/`。
本版按同一条教训处理:语料面也不再钉死,而是「报告 + 与报告同轮的移交定案底稿」。

时间序仍向 git 要(沿用 R10B 的理由:未提交的报告没有 add-commit,回落到 ts=0
会把它排成最老的一份,正好把开/闭判断反过来)。

    python3 data/r11b/probes/handover_census_r11b.py [--open-only] [--dest R11B]
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

# 报告名 -> 该轮的移交/定案底稿。底稿本身没有 git 时间序上的可靠位置(同一轮里
# 报告与底稿常在同一个 commit),所以挂到报告上,与报告同序。
ROUND_KEY = re.compile(r"round-(\d+[a-z]*(?:-fix)?)-")


def stamp(rel: str) -> int:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "log", "--diff-filter=A", "--follow",
         "--format=%ct", "--", rel],
        capture_output=True, text=True).stdout.split()
    # 未提交的报告没有 add-commit;当作最新,而不是最老。
    return int(out[-1]) if out else 1 << 62


def round_of_report(name: str) -> str:
    m = ROUND_KEY.search(name)
    return (m.group(1) if m else name).lower().replace("-fix", "fix")


def companion_notes(rkey: str) -> list[pathlib.Path]:
    """与该轮报告同轮的移交/定案底稿。r8-fix -> r8fix;round-9d -> r9d。"""
    pats = (f"r{rkey}-9*-*ruling*.md", f"r{rkey}-9*-*handover*.md")
    seen: dict[str, pathlib.Path] = {}
    for pat in pats:
        for p in NOTES.glob(pat):
            seen[p.name] = p
    return [seen[k] for k in sorted(seen)]


def split_row(line: str) -> list[str]:
    return [p.strip() for p in line.strip().strip("|").split("|")]


def scan(path: pathlib.Path):
    out = []
    header: list[str] | None = None
    kind = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("|"):
            header, kind = None, None
            continue
        cells = split_row(line)
        if set("".join(cells)) <= set("-: "):
            continue
        if header is None:
            header = cells
            joined = "".join(cells)
            if "去向" in joined or "建议轮次" in joined:
                kind = "handover"
            elif "处置结论" in joined or "结论" in joined or "复核结果" in joined:
                kind = "ruling"
            else:
                kind = None
            continue
        if kind is None or not cells:
            continue
        ids = [i for i in ID_RE.findall(cells[0]) if i]
        if not ids:
            continue
        if kind == "handover":
            col = next((i for i, h in enumerate(header) if h in ("去向", "建议轮次")), 1)
        else:
            col = next((i for i, h in enumerate(header)
                        if "处置结论" in h or h == "结论" or "复核结果" in h), len(cells) - 1)
        note = cells[col] if col < len(cells) else ""
        for i in ids:
            out.append((kind, i, note))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--open-only", action="store_true")
    ap.add_argument("--dest", help="只列最后去向包含该串的未结清项")
    ap.add_argument("--reports-only", action="store_true",
                    help="退回 R10B 的语料面,用于前后对比")
    ap.add_argument("--exclude", default="",
                    help="跳过报告名含该串的轮次(及其同轮底稿)。普查自己也会被"
                         "写它的那一轮污染 —— 本轮把 R11B 的报告与移交底稿加进语料后,"
                         "读数当场就变了。要报「扩面前后」这种前后对比,就得把当轮剔掉,"
                         "与 CLAUDE.md「搜过没有类测量报两个读数」同源。")
    args = ap.parse_args()

    order = sorted((stamp(f"reports/{p.name}"), p.name)
                   for p in REPORTS.glob("round-*.md"))
    events: dict[str, list[tuple[str, str, str]]] = {}
    scanned = []
    for _, name in order:
        if args.exclude and args.exclude in name:
            continue
        sources = [REPORTS / name]
        if not args.reports_only:
            sources += companion_notes(round_of_report(name))
        for src in sources:
            scanned.append(src.relative_to(ROOT).as_posix())
            for kind, hid, note in scan(src):
                events.setdefault(hid, []).append((name, kind, note))

    rows = []
    for hid, evs in events.items():
        opened = evs[0][0].replace("round-", "").replace(".md", "")
        handovers = [(n, note) for n, k, note in evs if k == "handover"]
        rulings = [(n, note) for n, k, note in evs if k == "ruling"]
        is_open = evs[-1][1] == "handover"
        rows.append((hid, opened, handovers[-1] if handovers else None,
                     rulings[-1] if rulings else None, is_open))

    sel = [r for r in rows if (r[4] or not args.open_only)]
    if args.dest:
        sel = [r for r in sel if r[4] and r[2] and args.dest in r[2][1]]
    for hid, opened, lh, lr, is_open in sorted(sel, key=lambda r: (not r[4], r[0])):
        dest = lh[1] if lh else "—"
        ruled = lr[0].replace("round-", "").replace(".md", "") if lr else "—"
        print(f"{hid:14s} 立项={opened:26s} 最后去向={dest:24s} "
              f"最后定案={ruled:26s} {'OPEN' if is_open else 'CLOSED'}")
    print(f"\n扫描文件 {len(scanned)} 份;总计 {len(rows)} 条,"
          f"未结清 {sum(1 for r in rows if r[4])} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
