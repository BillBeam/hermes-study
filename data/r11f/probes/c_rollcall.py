#!/usr/bin/env python3
"""R11F 片 C:59 个文件的点名底料 —— 逐个抽首行/模块 docstring 首句/顶层符号数。

只做**机械抽取**,不做归类;归类与一句话角色写在底稿里(那是人的活)。
用它是为了保证「一个都不漏」:清单直接来自 data/r11f/slices/C.txt,
而不是来自我记得哪些文件。

用法(cwd = hermes-study 仓库根;基线路径可用 HERMES_BASELINE 覆盖):
    python3 data/r11f/probes/c_rollcall.py --list      # 59 行:路径 + 行数
    python3 data/r11f/probes/c_rollcall.py --brief     # 路径 + 首句/首行
    python3 data/r11f/probes/c_rollcall.py --counts
    python3 data/r11f/probes/c_rollcall.py --bykind    # 按扩展名归类计数
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))
SLICE = Path(__file__).resolve().parents[1] / "slices" / "C.txt"


def rows() -> list[tuple[str, int]]:
    out = []
    for line in SLICE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        path, lines = line.rsplit("\t", 1)
        out.append((path, int(lines)))
    return out


def first_sentence(path: str) -> str:
    p = BASELINE / path
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"<unreadable: {e}>"
    if path.endswith(".py"):
        try:
            doc = ast.get_docstring(ast.parse(text))
        except SyntaxError:
            doc = None
        if doc:
            s = doc.strip().split("\n\n")[0].replace("\n", " ")
            return " ".join(s.split())[:150]
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith(("#!", "<!--")):
            return " ".join(s.split())[:150]
    return "<empty>"


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--list"
    rs = rows()

    if mode == "--counts":
        print(f"files={len(rs)}")
        print(f"lines={sum(n for _, n in rs)}")
        missing = [p for p, _ in rs if not (BASELINE / p).exists()]
        print(f"missing_from_baseline={len(missing)}")
        plats = sorted({p.split("/")[2] for p, _ in rs})
        print(f"platforms={len(plats)}")
        print(f"platform_names={','.join(plats)}")
        return

    if mode == "--bykind":
        kinds: dict[str, list[int]] = {}
        for p, n in rs:
            ext = p.rsplit(".", 1)[-1] if "." in p.rsplit("/", 1)[-1] else "(none)"
            kinds.setdefault(ext, []).append(n)
        for ext, ns in sorted(kinds.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            print(f"{ext:<10} files={len(ns):>3} lines={sum(ns):>6}")
        return

    if mode == "--list":
        for p, n in rs:
            print(f"{n:>5}  {p}")
        return

    if mode == "--brief":
        for p, n in rs:
            print(f"{p}  [{n}]")
            print(f"    {first_sentence(p)}")
        return

    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
