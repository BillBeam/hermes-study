#!/usr/bin/env python3
"""R10B 片 E:枚举 apps/desktop/src/global.d.ts 的类型契约面。

用法:
    python3 data/r10b/probes/probe_e_global_dts.py /home/user/hermes-agent [what]

what ∈ {bridge, decls, diff}(默认 bridge)
  bridge — `window.hermesDesktop` 的**顶层成员**(缩进 6 空格的 `name:` / `name?:`),
           带行号。
  decls  — global.d.ts 里 `declare global { ... }` 内的 interface / type 声明名。
  diff   — bridge 成员 vs `electron/preload.ts` 里 `contextBridge.exposeInMainWorld`
           对象的顶层键,两边取差集。

判定规则一律是**缩进宽度 + 行首正则**,不解析 TS;所以它是「机械枚举」,
不是类型检查。任何一侧改了缩进风格都会让它失真——重跑时先看它报的两个 total。
"""
from __future__ import annotations

import os
import re
import sys

MEMBER_RE = re.compile(r"^(?P<indent> +)(?P<name>[A-Za-z_$][\w$]*)\??\s*:")
DECL_RE = re.compile(r"^\s*(?:export\s+)?(interface|type)\s+([A-Za-z_$][\w$]*)")


def bridge_members(path: str, indent: int) -> list[tuple[int, str]]:
    """顶层 hermesDesktop 成员:进入 `hermesDesktop: {` 之后 indent 宽度的 `name:`。"""
    out: list[tuple[int, str]] = []
    depth = None
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    inside = False
    brace = 0
    for i, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        if not inside:
            if re.search(r"\bhermesDesktop\s*:\s*\{", line):
                inside = True
                brace = 1
            continue
        # 括号计数,退出即结束
        m = MEMBER_RE.match(line)
        if m and len(m.group("indent")) == indent:
            out.append((i, m.group("name")))
        brace += line.count("{") - line.count("}")
        if brace <= 0:
            break
    assert depth is None or True
    return out


def decls(path: str) -> list[tuple[int, str, str]]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            m = DECL_RE.match(line.rstrip("\n"))
            if m:
                out.append((i, m.group(1), m.group(2)))
    return out


def preload_keys(path: str) -> list[tuple[int, str]]:
    """`contextBridge.exposeInMainWorld('hermesDesktop', { ... })` 的顶层键。"""
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    out: list[tuple[int, str]] = []
    inside = False
    brace = 0
    for i, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        if not inside:
            if "exposeInMainWorld" in line and "hermesDesktop" in line:
                inside = True
                brace = line.count("{") - line.count("}")
            continue
        m = re.match(r"^ {2}([A-Za-z_$][\w$]*)\s*:", line)
        if m and brace == 1:
            out.append((i, m.group(1)))
        brace += line.count("{") - line.count("}")
        if brace <= 0:
            break
    return out


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent"
    what = sys.argv[2] if len(sys.argv) > 2 else "bridge"
    gd = os.path.join(root, "apps/desktop/src/global.d.ts")
    pl = os.path.join(root, "apps/desktop/electron/preload.ts")

    if what == "bridge":
        rows = bridge_members(gd, 6)
        for line, name in rows:
            print(f"{line}\t{name}")
        print(f"total\t{len(rows)}")
    elif what == "decls":
        rows = decls(gd)
        for line, kind, name in rows:
            print(f"{line}\t{kind}\t{name}")
        print(f"total\t{len(rows)}")
    elif what == "diff":
        declared = {n for _, n in bridge_members(gd, 6)}
        exposed = {n for _, n in preload_keys(pl)}
        print(f"declared_in_global_dts\t{len(declared)}")
        print(f"exposed_in_preload\t{len(exposed)}")
        print("-- declared but NOT exposed --")
        for n in sorted(declared - exposed):
            print(f"  {n}")
        print("-- exposed but NOT declared --")
        for n in sorted(exposed - declared):
            print(f"  {n}")
    else:
        print(f"unknown mode: {what}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
