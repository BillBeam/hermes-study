#!/usr/bin/env python3
"""跨轮移交项普查:每一条 H-* 的「立项轮 → 最后一次处置轮」与当前是否仍未结清。

为什么要机械做:各轮报告里有**两种**表长得很像 ——
  * 移交表  表头含「去向」,行 = 新立项(未结清);
  * 定案表  表头含「处置结论」或「结论」,行 = 对既有项的处置(结清或改述后续转)。
用列位置去猜会把定案表的「来源」列读成「去向」(R10 开工时主线就这么误读过一次,
把 R8C 已经结清的 H-R8FIX-a 读成了未结清)。本脚本按**表头名**定位列,不按列序。

轮次顺序取自各报告首次进入 git 的日期 + 文件名排序表(见 ORDER),不靠 mtime。

用法:python3 data/r10/probes/handover_census.py [--open-only]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
REPORTS = ROOT / "reports"

# 报告时间序(与 `git log --diff-filter=A` 的日期一致;同日的按轮次名排)
ORDER = [
    "round-1-survey.md", "round-1-capabilities-full.md",
    "round-2-turn-loop.md", "round-3-tool-infrastructure.md",
    "round-4-execution-environments.md", "round-5-session-state-and-persistence.md",
    "round-6-memory-provider-ecosystem.md", "round-7-gateway-session-core.md",
    "round-7b-platform-integration.md", "round-7c-gateway-periphery-and-scheduling.md",
    "round-8a-configuration-surface.md", "round-8-fix-review-1.md",
    "round-8b-cli-trunk-and-interaction.md", "round-8c-dashboard-and-web.md",
    "round-8d-cli-completion.md", "round-9a-capability-organization.md",
    "round-9b-multimodal-delivery.md", "round-9c-external-interfaces.md",
    "round-9d-l1-completion.md",
]

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
