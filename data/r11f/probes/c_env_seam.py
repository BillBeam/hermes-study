#!/usr/bin/env python3
"""R11F 片 C:声明的 env(plugin.yaml)vs 适配器实际读取的 env(源码 AST)。

清单面(requires_env/optional_env)是**设置向导的输入面**;适配器源码里的
``os.environ[...]`` / ``os.getenv(...)`` / ``os.environ.get(...)`` 是**运行期的读取面**。
两者不是同一个集合,差集就是接缝的缝隙:

  DECLARED_ONLY —— 向导会问,但该平台目录下没有任何 .py 读它
  READ_ONLY     —— 代码在读,但向导从不问(用户无从发现)

只统计**字面量**键名(AST ast.Constant),动态拼接的键名数不进来 —— 这是本探针的
已知下限,用 --dynamic 可以看到有多少处非字面量读取。

用法(cwd 任意;基线路径可用 HERMES_BASELINE 覆盖):
    python3 data/r11f/probes/c_env_seam.py --counts
    python3 data/r11f/probes/c_env_seam.py --diff
    python3 data/r11f/probes/c_env_seam.py --read-only
    python3 data/r11f/probes/c_env_seam.py --declared-only
    python3 data/r11f/probes/c_env_seam.py --dynamic
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import yaml

BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))

PLATFORMS = [
    "photon", "a2a", "whatsapp", "line", "buzz", "teams", "simplex",
    "mattermost", "email", "irc", "raft", "ntfy", "homeassistant", "sms",
]


def declared(p: str) -> set[str]:
    path = BASELINE / "plugins/platforms" / p / "plugin.yaml"
    m = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: set[str] = set()
    for block in ("requires_env", "optional_env"):
        for entry in (m.get(block) or []):
            if isinstance(entry, str):
                out.add(entry)
            elif isinstance(entry, dict) and entry.get("name"):
                out.add(entry["name"])
    return out


def _env_reads(tree: ast.AST) -> tuple[set[str], int]:
    """(字面量键名集合, 非字面量读取处数)。"""
    names: set[str] = set()
    dynamic = 0
    for node in ast.walk(tree):
        key = None
        is_read = False
        # os.environ["X"] / os.environ.get("X") / os.getenv("X")
        if isinstance(node, ast.Subscript):
            v = node.value
            if isinstance(v, ast.Attribute) and v.attr == "environ":
                is_read, key = True, node.slice
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in ("getenv", "get"):
                base = f.value
                ok = (isinstance(base, ast.Attribute) and base.attr == "environ") or (
                    isinstance(base, ast.Name) and base.id == "os" and f.attr == "getenv")
                if ok:
                    is_read = True
                    key = node.args[0] if node.args else None
        if not is_read:
            continue
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            names.add(key.value)
        elif key is not None:
            dynamic += 1
    return names, dynamic


def read_by(p: str) -> tuple[set[str], int]:
    d = BASELINE / "plugins/platforms" / p
    names: set[str] = set()
    dynamic = 0
    for f in sorted(d.rglob("*.py")):
        n, dy = _env_reads(ast.parse(f.read_text(encoding="utf-8")))
        names |= n
        dynamic += dy
    return names, dynamic


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--counts"
    rows = {}
    for p in PLATFORMS:
        dec = declared(p)
        rd, dy = read_by(p)
        rows[p] = (dec, rd, dy)

    if mode == "--counts":
        dec_only = sum(len(d - r) for d, r, _ in rows.values())
        rd_only = sum(len(r - d) for d, r, _ in rows.values())
        both = sum(len(d & r) for d, r, _ in rows.values())
        print(f"declared_total={sum(len(d) for d, _, _ in rows.values())}")
        print(f"read_literal_total={sum(len(r) for _, r, _ in rows.values())}")
        print(f"declared_and_read={both}")
        print(f"declared_only={dec_only}")
        print(f"read_only={rd_only}")
        print(f"dynamic_reads={sum(dy for _, _, dy in rows.values())}")
        return

    if mode == "--diff":
        print(f"{'platform':<14} {'dec':>4} {'read':>5} {'both':>5} "
              f"{'decOnly':>8} {'readOnly':>9} {'dyn':>4}")
        for p in PLATFORMS:
            d, r, dy = rows[p]
            print(f"{p:<14} {len(d):>4} {len(r):>5} {len(d & r):>5} "
                  f"{len(d - r):>8} {len(r - d):>9} {dy:>4}")
        return

    if mode == "--read-only":
        for p in PLATFORMS:
            d, r, _ = rows[p]
            extra = sorted(r - d)
            if extra:
                print(f"## {p}  +{len(extra)}")
                for n in extra:
                    print(f"   {n}")
        return

    if mode == "--declared-only":
        for p in PLATFORMS:
            d, r, _ = rows[p]
            miss = sorted(d - r)
            if miss:
                print(f"## {p}  -{len(miss)}")
                for n in miss:
                    print(f"   {n}")
        return

    if mode == "--dynamic":
        for p in PLATFORMS:
            _, _, dy = rows[p]
            print(f"{p:<14} {dy:>3}")
        return

    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
