#!/usr/bin/env python3
"""把「每一条移交案号的铸号行」逐行导出,供片 C 逐条处置时当工作底表。

R11D 片 C 的处置表要给每条案子写「锚点 + 一句话现象」,而这两样东西**已经写在
它的铸号行里**。手抄 100 多行是引入漂移的最快方式,所以这里机械导出。

输出 TSV:`id  file  lineno  去向/第二列  行原文`
去向列取表格第二列(移交表的惯例位),行原文截断到 400 字符。

    python3 data/r11d/probes/handover_rows_r11d.py                 # 全部
    python3 data/r11d/probes/handover_rows_r11d.py --only-open     # 只导出普查判 OPEN 的
    python3 data/r11d/probes/handover_rows_r11d.py --prefix H-R9D- # 按前缀过滤

语料与 `handover_disposition_r11d.py` 同源(import R11C 普查器,不改它)。
"""
from __future__ import annotations

import argparse
import importlib.util
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = pathlib.Path(subprocess.run(
    ["git", "-C", str(HERE.parent), "rev-parse", "--show-toplevel"],
    capture_output=True, check=True).stdout.decode().strip())

_spec = importlib.util.spec_from_file_location(
    "handover_disposition_r11d", HERE.parent / "handover_disposition_r11d.py")
disp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(disp)
census = disp.census


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="")
    ap.add_argument("--only-open", action="store_true")
    ap.add_argument("--with-round", default=None)
    ap.add_argument("--exclude", default="")
    ap.add_argument("--wide-hints", action="store_true")
    args = ap.parse_args()

    census.ID_RE = disp.WIDE_ID_RE
    if args.wide_hints:
        census.HANDOVER_HINTS = disp.WIDE_HANDOVER_HINTS

    srcs = disp.sources(args.with_round, legacy_corpus=False, exclude=args.exclude)
    open_ids: set[str] = set()
    if args.only_open:
        events: dict[str, list[str]] = {}
        for src in srcs:
            for kind, hid, _n, _h in census.scan(src)[0]:
                events.setdefault(hid, []).append(kind)
        open_ids = {k for k, v in events.items() if v[-1] == "handover"}

    seen: set[str] = set()
    for src in srcs:
        rel = src.relative_to(ROOT).as_posix()
        for lineno, line in enumerate(src.read_text(encoding="utf-8").splitlines(), 1):
            if not line.lstrip().startswith("|"):
                continue
            cells = census.split_row(line)
            ids = disp.WIDE_ID_RE.findall(cells[0]) if cells else []
            for hid in ids:
                if args.prefix and not hid.startswith(args.prefix):
                    continue
                if args.only_open and hid not in open_ids:
                    continue
                if hid in seen:
                    continue
                seen.add(hid)
                second = cells[1] if len(cells) > 1 else ""
                print("\t".join([hid, rel, str(lineno), second[:160],
                                 line.strip()[:400]]))
    print(f"# 导出 {len(seen)} 条", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
