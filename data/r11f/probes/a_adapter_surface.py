#!/usr/bin/env python3
"""R11F 片 A —— 平台适配器契约面的机械枚举(判据 2)。

只做 AST 静态解析,**不 import 基线任何模块**(基线的可选依赖是惰性安装的,
import 会联网装包;见 CLAUDE.md「惰性安装纪律」)。

对每个适配器输出四个集合:
  ABSTRACT-IMPL   基类 @abstractmethod,子类**实现了**
  ABSTRACT-MISS   基类 @abstractmethod,子类**没实现**(靠 MRO 继承抽象体 = 不可实例化)
  OVERRIDE        基类有具体实现,子类**覆盖**了
  EXTRA           基类没有,子类**自己多出来**的

用法:
    python3 a_adapter_surface.py [基线路径] [--mode summary|table|json]
默认基线路径 /home/user/hermes-agent。
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

BASE_REL = "gateway/platforms/base.py"
BASE_CLASS = "BasePlatformAdapter"
ADAPTERS = [
    ("discord", "plugins/platforms/discord/adapter.py", "DiscordAdapter"),
    ("telegram", "plugins/platforms/telegram/adapter.py", "TelegramAdapter"),
    ("slack", "plugins/platforms/slack/adapter.py", "SlackAdapter"),
]


def _find_class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise SystemExit(f"class {name} not found")


def _decorated_with(node: ast.AST, want: str) -> bool:
    for dec in getattr(node, "decorator_list", []):
        if isinstance(dec, ast.Name) and dec.id == want:
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == want:
            return True
    return False


def methods_of(cls: ast.ClassDef) -> dict:
    """{name: {lineno, is_async, abstract, property, staticmethod, classmethod}}"""
    out = {}
    for item in cls.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[item.name] = {
                "lineno": item.lineno,
                "is_async": isinstance(item, ast.AsyncFunctionDef),
                "abstract": _decorated_with(item, "abstractmethod"),
                "property": _decorated_with(item, "property"),
                "staticmethod": _decorated_with(item, "staticmethod"),
                "classmethod": _decorated_with(item, "classmethod"),
            }
    return out


def class_attrs(cls: ast.ClassDef) -> dict:
    """类体里的 name: type = value / name = value 赋值(适配器的能力开关面)。"""
    out = {}
    for item in cls.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            out[item.target.id] = {
                "lineno": item.lineno,
                "annotated": True,
                "value": ast.unparse(item.value) if item.value is not None else None,
            }
        elif isinstance(item, ast.Assign):
            for tgt in item.targets:
                if isinstance(tgt, ast.Name):
                    out[tgt.id] = {
                        "lineno": item.lineno,
                        "annotated": False,
                        "value": ast.unparse(item.value),
                    }
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    root = Path(args[0]) if args else Path("/home/user/hermes-agent")
    mode = "summary"
    for f in flags:
        if f.startswith("--mode"):
            mode = f.split("=", 1)[1] if "=" in f else "summary"

    base_tree = ast.parse((root / BASE_REL).read_text(encoding="utf-8"))
    base_cls = _find_class(base_tree, BASE_CLASS)
    base_m = methods_of(base_cls)
    base_a = class_attrs(base_cls)
    abstract = {n for n, v in base_m.items() if v["abstract"]}

    result = {
        "base": {
            "path": BASE_REL,
            "class": BASE_CLASS,
            "lineno": base_cls.lineno,
            "methods": len(base_m),
            "abstract": sorted(abstract),
            "attrs": len(base_a),
            "attr_names": sorted(base_a),
        },
        "adapters": {},
    }

    for label, rel, cls_name in ADAPTERS:
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        cls = _find_class(tree, cls_name)
        m = methods_of(cls)
        a = class_attrs(cls)
        names = set(m)
        result["adapters"][label] = {
            "path": rel,
            "class": cls_name,
            "lineno": cls.lineno,
            "methods": len(m),
            "abstract_impl": sorted(abstract & names),
            "abstract_miss": sorted(abstract - names),
            "override": sorted((names & set(base_m)) - abstract),
            "extra": sorted(names - set(base_m)),
            "attrs": len(a),
            "attr_override": sorted(set(a) & set(base_a)),
            "attr_extra": sorted(set(a) - set(base_a)),
            "detail": m,
            "attr_detail": a,
        }

    if mode == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0

    if mode == "table":
        # 每个基类具体方法一行,三家各标 O(覆盖) / -(未覆盖)
        print("method\tbase_line\tabstract\tdiscord\ttelegram\tslack")
        for n in sorted(base_m):
            row = [n, str(base_m[n]["lineno"]), "A" if n in abstract else ""]
            for label, _, _ in ADAPTERS:
                d = result["adapters"][label]
                row.append(str(d["detail"][n]["lineno"]) if n in d["detail"] else "-")
            print("\t".join(row))
        return 0

    b = result["base"]
    print(f"BASE {b['path']}:{b['lineno']} {b['class']}  "
          f"methods={b['methods']} abstract={len(b['abstract'])} class_attrs={b['attrs']}")
    print(f"  abstract: {' '.join(b['abstract'])}")
    for label, _, _ in ADAPTERS:
        d = result["adapters"][label]
        print(f"{label.upper():9s} {d['path']}:{d['lineno']} {d['class']}  methods={d['methods']} "
              f"class_attrs={d['attrs']}")
        print(f"  abstract_impl={len(d['abstract_impl'])} abstract_miss={len(d['abstract_miss'])} "
              f"override={len(d['override'])} extra={len(d['extra'])} "
              f"attr_override={len(d['attr_override'])} attr_extra={len(d['attr_extra'])}")
        if d["abstract_miss"]:
            print(f"  MISS: {' '.join(d['abstract_miss'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
