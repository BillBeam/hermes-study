#!/usr/bin/env python3
"""R10B 片 E:枚举 apps/desktop/src/{lib,themes,debug,types} 的导出面与被导入次数。

用法:
    python3 data/r10b/probes/probe_e_exports.py /home/user/hermes-agent [--md]

输出(TSV,表头一行):
    file<TAB>n_exports<TAB>exports(逗号分隔)<TAB>n_importers

- 导出符号:正则扫 `export (const|function|async function|class|type|interface|enum|
  let|var|default)` 与 `export {…}` 再导出;`export * from` 记为 `*from:<模块>`。
- 被导入次数:在 apps/desktop/{src,electron,e2e,scripts} 下 grep 形如
  `from "@/lib/<basename>"` / `from "./<basename>"` / `from "../lib/<basename>"` 的
  模块说明符,按**文件数**去重计数(不含自身)。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

DIRS = ("src/lib", "src/themes", "src/debug", "src/types")

DECL = re.compile(
    r"^export\s+(?:declare\s+)?(?:abstract\s+)?"
    r"(?:async\s+)?(const|let|var|function\*?|class|type|interface|enum)\s+([A-Za-z_$][\w$]*)",
    re.M,
)
NAMED = re.compile(r"^export\s*\{([^}]*)\}", re.M | re.S)
STAR = re.compile(r"^export\s+\*\s+(?:as\s+[\w$]+\s+)?from\s+['\"]([^'\"]+)['\"]", re.M)
DEFAULT = re.compile(r"^export\s+default\b", re.M)


def exports_of(path: str) -> list[str]:
    src = open(path, encoding="utf-8").read()
    out: list[str] = []
    for kind, name in DECL.findall(src):
        out.append(name)
    for body in NAMED.findall(src):
        for piece in body.split(","):
            piece = piece.strip()
            if not piece:
                continue
            piece = piece.split(" as ")[-1].strip()
            piece = piece.removeprefix("type ").strip()
            if piece:
                out.append(piece)
    for mod in STAR.findall(src):
        out.append(f"*from:{mod}")
    if DEFAULT.search(src):
        out.append("default")
    # 去重保序
    seen, uniq = set(), []
    for n in out:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent"
    desk = os.path.join(root, "apps/desktop")
    files: list[str] = []
    for d in DIRS:
        base = os.path.join(desk, d)
        for dirpath, _dirnames, filenames in os.walk(base):
            for fn in sorted(filenames):
                if fn.endswith((".ts", ".tsx")) and not fn.endswith((".test.ts", ".test.tsx")):
                    files.append(os.path.join(dirpath, fn))
    files.sort()

    print("file\tn_exports\texports\tn_importers")
    for f in files:
        rel = os.path.relpath(f, root)
        stem = os.path.basename(f).rsplit(".", 1)[0]
        parent = os.path.basename(os.path.dirname(f))
        try:
            ex = exports_of(f)
        except Exception as exc:  # pragma: no cover
            ex = [f"<ERR:{exc}>"]
        # 谁 import 了它
        pat = rf"from ['\"][^'\"]*(?:{parent}/)?{re.escape(stem)}['\"]"
        cmd = [
            "rg", "-l", "--no-messages", "-e", pat,
            os.path.join(desk, "src"), os.path.join(desk, "electron"),
            os.path.join(desk, "e2e"), os.path.join(desk, "scripts"),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        importers = {p for p in res.stdout.split() if p and os.path.abspath(p) != os.path.abspath(f)}
        print(f"{rel}\t{len(ex)}\t{','.join(ex)}\t{len(importers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
