#!/usr/bin/env python3
"""把 R11A 实际覆盖的文件的 status 列更新为 R11A-structure(L2)/ R11A-aware(L3)。

只动 status 列,不动 path/kind/lines/layer —— 分层与 round 由
`scripts/assign_layers.py` 管,本脚本绝不搬动分层
(「达成覆盖最省力的办法不是去读,而是把读不动的文件降层」这条要防的正是它)。

**两个 status,不合并**:L2 片给 `R11A-structure`(结构级理解),L3 校准片给
`R11A-aware`(知悉用途)。两层的交付判据不同(L2 五条 vs `data/r10b/l3-criteria.md`
的 L3 五条),用同一个字符串标注会让台账再也分不出「读到哪一层」——
而 `status` 列是"全仓无黑洞"这个最终目的的唯一可观测指标。

**只更新真正到货并通过验收的片。** 未到货的片不改:把没开工的标成已读就是虚报。
用 `--only` 指定本次要落账的片。

`data/ledger.tsv` 是 **CRLF** 行尾,读写都要保持,否则整表 diff 会炸。

用法:python3 data/r11a/probes/update_ledger_status.py [--apply] [--only ABC]
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
LEDGER = ROOT / "data" / "ledger.tsv"
SLICES = ROOT / "data" / "r11a" / "slices"

SCOPE_FILE = {"A": "scope-L2-A.txt", "B": "scope-L2-B.txt", "C": "scope-L3-C.txt"}
STATUS_BY_SLICE = {"A": "R11A-structure", "B": "R11A-structure", "C": "R11A-aware"}


def main() -> int:
    apply = "--apply" in sys.argv
    only = None
    for i, a in enumerate(sys.argv):
        if a == "--only" and i + 1 < len(sys.argv):
            only = set(sys.argv[i + 1])
    want = {k: v for k, v in STATUS_BY_SLICE.items() if only is None or k in only}
    if not want:
        print("没有选中任何片(--only 里的片号不在 A/B/C 内)")
        return 1

    covered: dict[str, str] = {}
    for name, status in sorted(want.items()):
        n = 0
        for line in (SLICES / SCOPE_FILE[name]).read_text(encoding="utf-8").splitlines():
            if line.strip():
                covered[line.strip()] = status
                n += 1
        print(f"  片 {name}: {n} 个文件 -> {status}")
    print(f"本轮覆盖清单: {len(covered)} 个文件,片 = {''.join(sorted(want))}")

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
            target = covered[f[i_path]]
            if f[i_status] != target:
                f[i_status] = target
                changed += 1
            ln = "\t".join(f)
        out.append(ln)

    missing = set(covered) - seen
    if missing:
        print(f"FAIL: {len(missing)} 个覆盖清单里的路径在台账中找不到:")
        for p in sorted(missing)[:10]:
            print("   ", p)
        return 1

    print(f"将改写 status 的行数: {changed}")
    if apply:
        LEDGER.write_bytes("\r\n".join(out).encode("utf-8"))
        print("已写回(保持 CRLF)")
    else:
        print("dry-run,未写回。加 --apply 生效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
