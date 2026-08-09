#!/usr/bin/env python3
"""把本轮实际覆盖的文件的 status 列更新为 R10-structure。

只动 status 列,不动 path/kind/lines/layer/round —— 分层由 scripts/assign_layers.py 管,
本脚本绝不搬动分层(「达成覆盖最省力的办法不是去读,而是把读不动的文件降层」这条要防的正是它)。

**只更新本轮真正吃下的 A..I 九片(556 个文件)**;REMAINDER 的 977 个保持
`R1-inventoried` 不动 —— 它们本轮没开工,把它们标成已读就是虚报。

`data/ledger.tsv` 是 **CRLF** 行尾,读写都要保持,否则整表 diff 会炸。

用法:python3 data/r10/probes/update_ledger_status.py [--apply]
      不带 --apply 只报会改多少行(dry-run)。
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
LEDGER = ROOT / "data" / "ledger.tsv"
SLICES = ROOT / "data" / "r10" / "slices"
NEW_STATUS = "R10-structure"


def main() -> int:
    apply = "--apply" in sys.argv

    covered: set[str] = set()
    for name in "ABCDEFGHI":
        for line in (SLICES / f"{name}.txt").read_text(encoding="utf-8").splitlines():
            if line.strip():
                covered.add(line.strip())
    print(f"本轮覆盖清单: {len(covered)} 个文件")

    raw = LEDGER.read_bytes().decode("utf-8")
    lines = raw.split("\r\n")
    header, body = lines[0], lines[1:]
    cols = header.split("\t")
    i_path, i_status = cols.index("path"), cols.index("status")

    changed = 0
    seen: set[str] = set()
    out = [header]
    for ln in body:
        if not ln:
            out.append(ln)
            continue
        f = ln.split("\t")
        if f[i_path] in covered:
            seen.add(f[i_path])
            if f[i_status] != NEW_STATUS:
                f[i_status] = NEW_STATUS
                changed += 1
            ln = "\t".join(f)
        out.append(ln)

    missing = covered - seen
    if missing:
        print(f"FAIL: {len(missing)} 个覆盖清单里的路径在台账中找不到:")
        for p in sorted(missing)[:10]:
            print("   ", p)
        return 1

    print(f"将改写 status -> {NEW_STATUS} 的行数: {changed}")
    if apply:
        LEDGER.write_bytes("\r\n".join(out).encode("utf-8"))
        print("已写回(保持 CRLF)")
    else:
        print("dry-run,未写回。加 --apply 生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
