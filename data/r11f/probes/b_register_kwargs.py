#!/usr/bin/env python3
"""R11F 片 B —— `ctx.register_platform(...)` 注册面逐参数枚举。

适配器交给宿主的第三个面(前两个是 ABC 实现面与鸭子契约面):
`register(ctx)` 里那一串关键字参数。`hermes_cli/plugins.py:953` 的签名只固定了
6 个形参,其余全部走 `**entry_kwargs` 转发给 `PlatformEntry` 数据类,
所以**这个面的真实形状只能从调用点读出来**,读签名读不到。

纯 AST。对每个 `register_platform` 调用列出:平台名、用到的关键字、
以及 `PlatformEntry` 声明了但该平台没传的字段。

用法:
    python3 data/r11f/probes/b_register_kwargs.py           # 每个调用点的关键字
    python3 data/r11f/probes/b_register_kwargs.py --matrix  # 平台 × 关键字 交叉表
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

BASELINE = Path("/home/user/hermes-agent")
ENTRY_FILE = "gateway/platform_registry.py"
ENTRY_CLASS = "PlatformEntry"

SLICE_FILES = [
    "plugins/platforms/dingtalk/adapter.py",
    "plugins/platforms/feishu/adapter.py",
    "plugins/platforms/google_chat/adapter.py",
    "plugins/platforms/matrix/adapter.py",
    "plugins/platforms/wecom/adapter.py",
]


def entry_fields() -> list[str]:
    tree = ast.parse((BASELINE / ENTRY_FILE).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == ENTRY_CLASS:
            out = []
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    out.append(stmt.target.id)
            return out
    raise SystemExit(f"{ENTRY_CLASS} not found in {ENTRY_FILE}")


def calls() -> list[tuple[str, str, int, list[str]]]:
    """[(file, platform_name, lineno, [kwargs…])]"""
    out = []
    for rel in SLICE_FILES:
        path = BASELINE / rel
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr == "register_platform"):
                continue
            kws = [k.arg for k in node.keywords if k.arg]
            name = ""
            for k in node.keywords:
                if k.arg == "name" and isinstance(k.value, ast.Constant):
                    name = str(k.value.value)
            out.append((rel, name, node.lineno, kws))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", action="store_true", help="平台 × 关键字 交叉表")
    args = ap.parse_args()

    fields = entry_fields()
    cs = calls()

    if args.matrix:
        used = sorted({k for _f, _n, _l, ks in cs for k in ks})
        print("kwarg\t" + "\t".join(n for _f, n, _l, _k in cs) + "\tin_PlatformEntry")
        for k in used:
            row = ["Y" if k in ks else "-" for _f, _n, _l, ks in cs]
            print(f"{k}\t" + "\t".join(row) + "\t" +
                  ("Y" if k in fields else "NO"))
        print(f"\nPlatformEntry 字段数\t{len(fields)}")
        print(f"片 B 用到的关键字数\t{len(used)}")
        print("片 B 一个都没用到的 PlatformEntry 字段\t" +
              ",".join(f for f in fields if f not in used))
        return 0

    print("file\tplatform\tlineno\tn_kwargs\tkwargs")
    for rel, name, lineno, ks in cs:
        print(f"{rel}\t{name}\t{lineno}\t{len(ks)}\t{','.join(ks)}")
    print(f"TOTAL_CALLS\t{len(cs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
