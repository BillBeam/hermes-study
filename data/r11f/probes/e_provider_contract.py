#!/usr/bin/env python3
"""R11F 片 E 探针:provider 契约面横向表(逐项列全,不抽样)。

对 image_gen / video_gen / browser 三个能力域,分别:
  1. 从各自 ABC(agent/image_gen_provider.py、agent/video_gen_provider.py、
     agent/browser_provider.py)AST 抽出**抽象方法**与**带默认实现的方法**;
  2. 对片 E 内每个 provider 实现 AST 抽出它定义了哪些方法;
  3. 输出三态:IMPL(实现了抽象方法) / OVR(覆写了带默认的) / -(未覆写) /
     EXTRA(基类里没有的新方法,不含单下划线私有)。

纯 AST,不 import 基线代码,故无惰性安装风险。
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))

DOMAINS = {
    "image_gen": {
        "abc_file": "agent/image_gen_provider.py",
        "abc_class": "ImageGenProvider",
        "impls": [
            ("deepinfra", "plugins/image_gen/deepinfra/__init__.py"),
            ("fal", "plugins/image_gen/fal/__init__.py"),
            ("krea", "plugins/image_gen/krea/__init__.py"),
            ("openai", "plugins/image_gen/openai/__init__.py"),
            ("openai-codex", "plugins/image_gen/openai-codex/__init__.py"),
            ("openrouter", "plugins/image_gen/openrouter/__init__.py"),
            ("xai", "plugins/image_gen/xai/__init__.py"),
        ],
    },
    "video_gen": {
        "abc_file": "agent/video_gen_provider.py",
        "abc_class": "VideoGenProvider",
        "impls": [
            ("deepinfra", "plugins/video_gen/deepinfra/__init__.py"),
            ("fal", "plugins/video_gen/fal/__init__.py"),
            ("xai", "plugins/video_gen/xai/__init__.py"),
        ],
        "extra_bases": [("OpenAICompatibleVideoGenProvider", "agent/video_gen_provider.py")],
    },
    "browser": {
        "abc_file": "agent/browser_provider.py",
        "abc_class": "BrowserProvider",
        "impls": [
            ("browser-use", "plugins/browser/browser_use/provider.py"),
            ("browserbase", "plugins/browser/browserbase/provider.py"),
            ("firecrawl", "plugins/browser/firecrawl/provider.py"),
        ],
    },
}


def _class_node(path: Path, class_name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise SystemExit(f"class {class_name} not found in {path}")


def _methods(cls: ast.ClassDef):
    """Return {name: is_abstract} for methods defined directly on cls."""
    out = {}
    for item in cls.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            abstract = any(
                (isinstance(d, ast.Name) and d.id == "abstractmethod")
                or (isinstance(d, ast.Attribute) and d.attr == "abstractmethod")
                for d in item.decorator_list
            )
            out[item.name] = abstract
    return out


def _first_class_in(path: Path, base_hint: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for b in node.bases:
                bname = b.id if isinstance(b, ast.Name) else getattr(b, "attr", "")
                if base_hint in bname or bname in base_hint:
                    return node
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            return node
    raise SystemExit(f"no class in {path}")


def main() -> int:
    for domain, spec in DOMAINS.items():
        abc_cls = _class_node(BASELINE / spec["abc_file"], spec["abc_class"])
        abc_methods = _methods(abc_cls)
        order = sorted(abc_methods, key=lambda n: (not abc_methods[n], n))
        print(f"### {domain}  ABC={spec['abc_class']}  ({spec['abc_file']})")
        print("methods on ABC: " + ", ".join(
            f"{n}{'*' if abc_methods[n] else ''}" for n in order
        ) + "   (* = @abstractmethod)")
        for label, rel in spec["impls"]:
            cls = _first_class_in(BASELINE / rel, spec["abc_class"])
            impl = _methods(cls)
            cells = []
            for n in order:
                if n in impl:
                    cells.append(f"{n}={'IMPL' if abc_methods[n] else 'OVR'}")
                else:
                    cells.append(f"{n}=-")
            extra = sorted(n for n in impl if n not in abc_methods and not n.startswith("__"))
            base_names = [
                b.id if isinstance(b, ast.Name) else getattr(b, "attr", "?")
                for b in cls.bases
            ]
            print(f"  {label:<13} class={cls.name} base={'+'.join(base_names)}")
            print(f"    {' '.join(cells)}")
            print(f"    EXTRA: {', '.join(extra) if extra else '(none)'}")
        for bname, brel in spec.get("extra_bases", []):
            cls = _class_node(BASELINE / brel, bname)
            impl = _methods(cls)
            cells = []
            for n in order:
                if n in impl:
                    cells.append(f"{n}={'IMPL' if abc_methods[n] else 'OVR'}")
                else:
                    cells.append(f"{n}=-")
            extra = sorted(n for n in impl if n not in abc_methods and not n.startswith("__"))
            print(f"  [mixin] {bname}")
            print(f"    {' '.join(cells)}")
            print(f"    EXTRA: {', '.join(extra) if extra else '(none)'}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
