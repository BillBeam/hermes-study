#!/usr/bin/env python3
"""R11F 片 D 探针:dashboard 插件的 HTTP 路由面机械枚举。

判据 2(接缝穷举)的枚举工具。用 AST 而非正则:装饰器可以跨行、路径可以是常量拼接,
正则只在"当前写法恰好规整"时正确,而本探针要给出的是**穷举**保证。

对每个 `@router.<method>("<path>")` 输出:
    文件相对路径 / 装饰器行号 / HTTP 方法 / 路径 / 处理函数名 / 函数定义行号 / 是否 async
    / 处理函数的形参表(= 该路由的请求面:路径参数、Query、请求体模型、上传件)

用法:
    python3 d_route_surface.py <基线根> [--tsv]

不 import 被测模块(纯 AST 解析),因此不触发惰性安装、不产生任何网络副作用。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# 片 D 范围内所有声明了 dashboard HTTP 面的文件(取自 manifest.json 的 "api" 键)
TARGETS = [
    "plugins/kanban/dashboard/plugin_api.py",
    "plugins/hermes-achievements/dashboard/plugin_api.py",
]

HTTP_METHODS = {
    "get", "post", "put", "patch", "delete", "head", "options", "trace",
    "websocket", "api_route", "add_api_route",
}


def decorator_calls(node: ast.AST):
    """产出 (method, path, deco_lineno) —— 只认 <名字>.<方法>(...) 形式的装饰器。"""
    for deco in getattr(node, "decorator_list", []):
        if not isinstance(deco, ast.Call):
            continue
        func = deco.func
        if not isinstance(func, ast.Attribute):
            continue
        method = func.attr
        if method not in HTTP_METHODS:
            continue
        owner = func.value.id if isinstance(func.value, ast.Name) else "<expr>"
        path = None
        if deco.args:
            first = deco.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                path = first.value
            else:
                path = f"<非字面量:{ast.dump(first)[:40]}>"
        for kw in deco.keywords:
            if kw.arg == "path" and isinstance(kw.value, ast.Constant):
                path = kw.value.value
        yield owner, method, path, deco.lineno


def signature(node) -> str:
    """形参表:`名字:注解` 逗号连接。注解用源码文本还原,取不到时留空。"""
    parts = []
    a = node.args
    for arg in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
        ann = ""
        if arg.annotation is not None:
            try:
                ann = ast.unparse(arg.annotation)
            except Exception:
                ann = "?"
        parts.append(f"{arg.arg}:{ann}" if ann else arg.arg)
    return ",".join(parts)


def scan(root: Path):
    rows = []
    for rel in TARGETS:
        src = (root / rel).read_text(encoding="utf-8")
        tree = ast.parse(src, filename=rel)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for owner, method, path, deco_lineno in decorator_calls(node):
                rows.append({
                    "file": rel,
                    "deco_line": deco_lineno,
                    "owner": owner,
                    "method": method.upper(),
                    "path": path,
                    "handler": node.name,
                    "def_line": node.lineno,
                    "async": isinstance(node, ast.AsyncFunctionDef),
                    "params": signature(node),
                })
    rows.sort(key=lambda r: (r["file"], r["deco_line"]))
    return rows


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(args[0]) if args else Path("/home/user/hermes-agent")
    tsv = "--tsv" in sys.argv
    rows = scan(root)
    if tsv:
        print("file\tdeco_line\tmethod\tpath\thandler\tdef_line\tasync\tparams")
        for r in rows:
            print(f"{r['file']}\t{r['deco_line']}\t{r['method']}\t{r['path']}\t"
                  f"{r['handler']}\t{r['def_line']}\t{int(r['async'])}\t{r['params']}")
    else:
        for r in rows:
            print(f"{r['file']}:{r['deco_line']}\t{r['method']:9s} {r['path']:45s} "
                  f"-> {r['handler']} ({'async ' if r['async'] else ''}def @ :{r['def_line']})")
    per_file = {}
    for r in rows:
        per_file[r["file"]] = per_file.get(r["file"], 0) + 1
    for f, n in sorted(per_file.items()):
        print(f"# {f}: {n}", file=sys.stderr)
    print(f"# TOTAL routes: {len(rows)}", file=sys.stderr)
    # 装饰器 owner 一致性:若出现第二个 owner,说明有第二张 router,枚举面就不完整了
    owners = sorted({r["owner"] for r in rows})
    print(f"# decorator owners: {owners}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
