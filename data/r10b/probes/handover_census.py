#!/usr/bin/env python3
"""移交项普查(R10B 版):把全部 `H-*` 的立项轮、最后去向、最后定案轮列出来。

R10 版见 data/r10/probes/handover_census.py。本版只改一处:报告的时间序不再是
手工清单,而是向 git 要(见 report_order)。R10 版的清单没有 R10 自己,于是
R10B 开工普查读到的仍是「52 条」——一整轮的移交项静默缺席,输出里毫无痕迹。

    python3 data/r10b/probes/handover_census.py [--open-only]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
REPORTS = ROOT / "reports"

# 报告时间序。R10 版把它写成一张**手工清单**,于是 R10 自己的报告不在表上,
# R10B 开工时跑普查 —— H-R10-a..f 六条一条都没出现,总数仍是 52。
# 「漏了一整轮」和「那一轮没有移交项」在输出里长得一模一样,**没有任何提示**。
# 所以这一版改为向 git 要顺序(首次加入该文件的提交时间),清单不再需要有人记得维护;
# 拿不到 git 时回落到文件名排序,并**明说**自己回落了,而不是安静地少数几条。
def report_order() -> list[str]:
    import subprocess
    names = sorted(p.name for p in REPORTS.glob("round-*.md"))
    stamped = []
    for n in names:
        try:
            out = subprocess.run(
                ["git", "-C", str(ROOT), "log", "--diff-filter=A", "--follow",
                 "--format=%ct", "--", f"reports/{n}"],
                capture_output=True, text=True, check=True).stdout.split()
            ts = int(out[-1]) if out else 0
        except Exception:
            print("WARN: git unavailable, falling back to filename order",
                  file=sys.stderr)
            return names
        stamped.append((ts, n))
    return [n for _, n in sorted(stamped)]


ORDER = report_order()

ID_RE = re.compile(r"H-[A-Za-z0-9]+-[a-z]\b|H-R8FIX-[a-z]\b|(?<![\w-])H-\d{1,2}(?![\w-])")


def split_row(line: str) -> list[str]:
    parts = line.strip().strip("|").split("|")
    return [p.strip() for p in parts]


def scan(path: pathlib.Path):
    """返回 [(kind, ids, dest_or_ruling)],kind ∈ {'handover','ruling'}。"""
    out = []
    header: list[str] | None = None
    kind = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("|"):
            header, kind = None, None
            continue
        cells = split_row(line)
        if set("".join(cells)) <= set("-: "):          # 分隔行
            continue
        if header is None:
            header = cells
            joined = "".join(cells)
            # 「去向」是通用写法;R8-fix 那张表用的是「建议轮次」(同义,列位也不同)
            if "去向" in joined or "建议轮次" in joined:
                kind = "handover"
            elif "处置结论" in joined or "结论" in joined or "复核结果" in joined:
                kind = "ruling"
            else:
                kind = None
            continue
        if kind is None or not cells:
            continue
        ids = ID_RE.findall(cells[0])
        ids = [i for i in ids if i]
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
    args = ap.parse_args()

    events: dict[str, list[tuple[str, str, str]]] = {}
    for name in ORDER:
        p = REPORTS / name
        if not p.exists():
            print(f"WARN missing report: {name}", file=sys.stderr)
            continue
        for kind, hid, note in scan(p):
            events.setdefault(hid, []).append((name, kind, note))

    def rnd(n: str) -> str:
        return n.replace("round-", "").replace(".md", "")

    rows = []
    for hid, evs in events.items():
        opened = next((rnd(n) for n, k, _ in evs if k == "handover"), "?")
        rulings = [(rnd(n), note) for n, k, note in evs if k == "ruling"]
        handovers = [(rnd(n), note) for n, k, note in evs if k == "handover"]
        last_ruling = rulings[-1] if rulings else None
        last_handover = handovers[-1] if handovers else None
        # 未结清 = 最后一次出现是「移交」而不是「定案」
        last_kind = evs[-1][1]
        is_open = last_kind == "handover"
        rows.append((hid, opened, last_handover, last_ruling, is_open))

    def sortkey(r):
        return (0 if r[4] else 1, r[0])

    print(f"{'ID':<16} {'立项':<10} {'最后去向':<16} {'最后定案轮':<10} 状态")
    n_open = 0
    for hid, opened, lh, lr, is_open in sorted(rows, key=sortkey):
        if args.open_only and not is_open:
            continue
        if is_open:
            n_open += 1
        dest = re.sub(r"\*+", "", lh[1])[:26] if lh else "(仅见于定案表)"
        print(f"{hid:<16} {opened:<10} {dest:<26} {(lr[0] if lr else '—'):<10} "
              f"{'OPEN' if is_open else 'closed'}")
    print(f"\n总计 {len(rows)} 条,其中未结清 {sum(1 for r in rows if r[4])} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
