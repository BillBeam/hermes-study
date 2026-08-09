#!/usr/bin/env python3
"""R10 分片:把台账里 round=R10 的 1,533 个文件确定性地分配到 A..I 九片 + REMAINDER。

只读 data/ledger.tsv,输出 data/r10/slices/<片>.txt(每行一个仓库相对路径)
与 data/r10/slices/_summary.tsv(片 / 文件数 / 行数)。

判定规则是「首条匹配生效」,与 scripts/assign_layers.py 同构;
任何 round=R10 的文件若一条都不匹配,会落进 REMAINDER —— 那是本轮显式不吃下的部分,
不是漏网:REMAINDER 也会被写成清单并报数。

重跑:python3 data/r10/probes/make_slices.py
"""
from __future__ import annotations

import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
LEDGER = ROOT / "data" / "ledger.tsv"
OUTDIR = ROOT / "data" / "r10" / "slices"

# tui_gateway 拆两片:协议骨架(传输/事件/进程 I/O)与方法面(JSON-RPC 方法 + 宿主监管)
_TG_SKELETON = {
    "server.py", "entry.py", "transport.py", "ws.py", "method_ctx.py",
    "event_publisher.py", "_stdin_recovery.py", "loop_noise.py",
    "turn_marker.py", "render.py", "__init__.py",
}

# 首条匹配生效
RULES = [
    ("A", lambda p: p.startswith("tui_gateway/") and p.split("/", 1)[1] in _TG_SKELETON),
    ("B", lambda p: p.startswith("tui_gateway/")),
    ("C", lambda p: p.startswith("acp_adapter/")),
    ("F", lambda p: p.startswith("ui-tui/packages/")),
    ("D", lambda p: any(p.startswith(f"ui-tui/src/{d}/") for d in
                        ("app", "sdk", "domain", "hooks", "config", "protocol", "types", "content"))),
    ("D", lambda p: p.startswith("ui-tui/src/") and p.count("/") == 2),  # ui-tui/src 直属文件
    ("E", lambda p: p.startswith("ui-tui/")),  # components + lib + scripts + 根文件
    ("G", lambda p: p.startswith("web/")),
    ("H", lambda p: p.startswith("apps/desktop/electron/")),
    ("I", lambda p: p.startswith("native/")),
]

SLICE_TITLES = {
    "A": "tui_gateway 协议骨架与传输",
    "B": "tui_gateway 方法面与宿主监管",
    "C": "acp_adapter 编辑器接驳",
    "D": "ui-tui 客户端主干",
    "E": "ui-tui 组件、库与构建脚本",
    "F": "hermes-ink 终端渲染器",
    "G": "web 仪表盘前端",
    "H": "apps/desktop/electron 主进程与后端监管",
    "I": "native/fts5_cjk 随附头文件(处置)",
    "REMAINDER": "本轮显式不吃下(移交 R10B)",
}


def classify(path: str) -> str:
    for name, pred in RULES:
        if pred(path):
            return name
    return "REMAINDER"


def main() -> int:
    rows = []
    with LEDGER.open(encoding="utf-8", newline="") as fh:
        for rec in csv.DictReader(fh, delimiter="\t"):
            if (rec["round"] or "").strip() != "R10":
                continue
            rows.append((rec["path"].strip(), int(rec["lines"]), (rec["layer"] or "").strip()))

    buckets: dict[str, list[tuple[str, int]]] = {}
    for path, lines, _layer in rows:
        buckets.setdefault(classify(path), []).append((path, lines))

    OUTDIR.mkdir(parents=True, exist_ok=True)
    summary = []
    for name in list(SLICE_TITLES):
        items = sorted(buckets.get(name, []))
        (OUTDIR / f"{name}.txt").write_text(
            "".join(f"{p}\n" for p, _ in items), encoding="utf-8")
        summary.append((name, SLICE_TITLES[name], len(items), sum(n for _, n in items)))

    with (OUTDIR / "_summary.tsv").open("w", encoding="utf-8") as fh:
        fh.write("slice\ttitle\tfiles\tlines\n")
        for name, title, nf, nl in summary:
            fh.write(f"{name}\t{title}\t{nf}\t{nl}\n")

    tot_f = sum(s[2] for s in summary)
    tot_l = sum(s[3] for s in summary)
    for name, title, nf, nl in summary:
        print(f"{name:>9}  {nf:>5} files {nl:>7} lines  {title}")
    print(f"{'TOTAL':>9}  {tot_f:>5} files {tot_l:>7} lines")
    assert tot_f == len(rows), f"file count drift: {tot_f} != {len(rows)}"
    assert tot_l == sum(n for _, n, _ in rows), "line count drift"
    print("OK: slices partition round=R10 exactly (no overlap, no loss)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
