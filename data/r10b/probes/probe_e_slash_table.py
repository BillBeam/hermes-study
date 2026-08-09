#!/usr/bin/env python3
"""R10B 片 E:枚举 apps/desktop/src/lib/desktop-slash-commands.ts 的命令表。

用法:
    python3 data/r10b/probes/probe_e_slash_table.py /home/user/hermes-agent

输出四段:
  1. DESKTOP_COMMAND_SPECS 里的每条 `name: '/x'` + 它的 surface kind
  2. 每条 spec 的 aliases
  3. NO_DESKTOP_SURFACE 四个 reason 桶各自的命令名
  4. 汇总条数(canonical / alias / unavailable / 合计可解析名字)

解析靠正则切块,不解析 TS。改了表的写法(比如把 surface 换行)会让 kind 变 '?';
所以重跑时要先核对 total 数。
"""
from __future__ import annotations

import os
import re
import sys


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent"
    path = os.path.join(root, "apps/desktop/src/lib/desktop-slash-commands.ts")
    src = open(path, encoding="utf-8").read()

    spec_block = src.split("const DESKTOP_COMMAND_SPECS", 1)[1].split("\n]", 1)[0]
    nds_block = src.split("const NO_DESKTOP_SURFACE", 1)[1].split("\n}", 1)[0]

    # 按 `name: '/x'` 切成每条 spec
    parts = re.split(r"(?=name: '/)", spec_block)[1:]
    canonical: list[tuple[str, str, list[str]]] = []
    for part in parts:
        name = re.match(r"name: '([^']+)'", part).group(1)
        kindm = re.search(r"surface: (exec|action|picker|rpc|unavailable)\(", part)
        kind = kindm.group(1) if kindm else "?"
        am = re.search(r"aliases: \[([^\]]*)\]", part)
        aliases = re.findall(r"'([^']+)'", am.group(1)) if am else []
        canonical.append((name, kind, aliases))

    print("== DESKTOP_COMMAND_SPECS ==")
    for name, kind, aliases in canonical:
        extra = f"  aliases={aliases}" if aliases else ""
        print(f"  {name:<16} {kind}{extra}")

    print("== NO_DESKTOP_SURFACE ==")
    buckets: dict[str, list[str]] = {}
    for m in re.finditer(r"(\w+): \[(.*?)\]", nds_block, re.S):
        buckets[m.group(1)] = re.findall(r"'([^']+)'", m.group(2))
    for reason, names in buckets.items():
        print(f"  {reason} ({len(names)}): {' '.join(names)}")

    alias_total = sum(len(a) for _, _, a in canonical)
    nds_total = sum(len(v) for v in buckets.values())
    kinds: dict[str, int] = {}
    for _, kind, _ in canonical:
        kinds[kind] = kinds.get(kind, 0) + 1

    print("== TOTALS ==")
    print(f"  canonical specs      : {len(canonical)}")
    print(f"  aliases              : {alias_total}")
    print(f"  no-desktop-surface   : {nds_total}")
    print(f"  ALL_SPECS (canonical+nds) : {len(canonical) + nds_total}")
    print(f"  resolvable names (ALL_SPECS + aliases) : {len(canonical) + nds_total + alias_total}")
    print(f"  surface kinds        : {dict(sorted(kinds.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
