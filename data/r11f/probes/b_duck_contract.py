#!/usr/bin/env python3
"""R11F 片 B —— 「鸭子契约面」枚举:ABC 之外、宿主用 getattr/hasattr 找的可选协议。

`BasePlatformAdapter` 只有 4 个 @abstractmethod。真正的适配器契约比 ABC 大得多:
宿主(gateway/ cron/ hermes_cli/ agent/ tools/)会用
`getattr(adapter, "xxx", None)` / `hasattr(adapter, "xxx")` 去问适配器
「你支不支持 xxx」。这些名字**不在 ABC 上**,所以 b_adapter_contract.py 把它们
归进 PLUGIN-ONLY —— 但它们其实是契约的一部分,只是没写进基类。

本探针把这一层挖出来:
  1. 从 b_adapter_contract 拿到片 B 六个适配器类的 PLUGIN-ONLY 成员名;
  2. 在宿主代码里找 `getattr(<任意>, "<名字>"…)` / `hasattr(<任意>, "<名字>")`
     形式的**字符串字面量**引用(AST,不是文本 grep —— 避免命中同名注释/文档);
  3. 命中即判为 DUCK(隐式契约),未命中判为 PRIVATE(真·插件私有)。

宿主面 = 基线里除 tests/ 与 plugins/ 之外的全部 .py。
排除 plugins/ 是有意的:一个插件自己 getattr 自己的方法不构成宿主契约。

用法:
    python3 data/r11f/probes/b_duck_contract.py             # 摘要
    python3 data/r11f/probes/b_duck_contract.py --full      # DUCK 全表
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b_adapter_contract import ADAPTERS, BASELINE, class_members, BASE_FILE, BASE_CLASS  # noqa: E402

HOST_EXCLUDE_PREFIXES = ("tests/", "plugins/")


def host_duck_names() -> dict[str, list[str]]:
    """{被 getattr/hasattr 问到的名字: [出现的文件:行, …]}"""
    out: dict[str, list[str]] = {}
    for path in BASELINE.rglob("*.py"):
        if "__pycache__" in path.parts or ".git" in path.parts:
            continue
        rel = path.relative_to(BASELINE).as_posix()
        if rel.startswith(HOST_EXCLUDE_PREFIXES):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"),
                             filename=rel)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            fname = fn.id if isinstance(fn, ast.Name) else (
                fn.attr if isinstance(fn, ast.Attribute) else "")
            if fname not in {"getattr", "hasattr"}:
                continue
            if len(node.args) < 2:
                continue
            arg = node.args[1]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.setdefault(arg.value, []).append(f"{rel}:{node.lineno}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()

    base = class_members(BASELINE / BASE_FILE, BASE_CLASS)
    duck = host_duck_names()

    rows: list[tuple[str, str, int, int, str]] = []
    for plat, rel, cls in ADAPTERS:
        mem = class_members(BASELINE / rel, cls)
        for name, meta in sorted(mem.items()):
            if name in base:
                continue  # 已在 ABC 上,不算隐式契约
            sites = duck.get(name, [])
            if sites:
                rows.append((plat, name, meta["lineno"], len(sites), sites[0]))

    if args.full:
        print("platform\tmember\tadapter_lineno\thost_sites\tfirst_host_site")
        for r in rows:
            print("\t".join(str(x) for x in r))
        print(f"TOTAL\t{len(rows)}")
        return 0

    print("平台\tPLUGIN-ONLY 里被宿主 getattr/hasattr 问到的(DUCK)\t该平台 PLUGIN-ONLY 合计")
    for plat, rel, cls in ADAPTERS:
        mem = class_members(BASELINE / rel, cls)
        po = [n for n in mem if n not in base]
        d = [n for n in po if n in duck]
        print(f"{plat}\t{len(d)}\t{len(po)}")
    names = sorted({r[1] for r in rows})
    print(f"不同的 DUCK 名字合计\t{len(names)}")
    print("\t".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
