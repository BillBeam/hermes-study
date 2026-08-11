#!/usr/bin/env python3
"""R11F 片 E 探针:片内 14 份 plugin.yaml 的键集全表 + 「谁读它」判定。

两件事:
  1. 逐份列全每个 manifest 的顶层键(不抽样),以及 requires_env / provides_* 的
     每一条取值;
  2. 把观测到的每个键与 `hermes_cli/plugins.py::_parse_manifest` 里
     `data.get("<键>")` 的实际读取面对照,标出 READ / UNREAD。

判据是**解析结果**而非印象:读取面从基线源码 AST 抽取
(`_parse_manifest` 函数体内所有 `data.get("字面量", ...)`),不是手抄的清单。

纯读文件 + AST,不 import 基线代码。
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))

SLICE_E_MANIFESTS = [
    "plugins/browser/browser_use/plugin.yaml",
    "plugins/browser/browserbase/plugin.yaml",
    "plugins/browser/firecrawl/plugin.yaml",
    "plugins/google_meet/plugin.yaml",
    "plugins/image_gen/deepinfra/plugin.yaml",
    "plugins/image_gen/fal/plugin.yaml",
    "plugins/image_gen/krea/plugin.yaml",
    "plugins/image_gen/openai/plugin.yaml",
    "plugins/image_gen/openai-codex/plugin.yaml",
    "plugins/image_gen/openrouter/plugin.yaml",
    "plugins/image_gen/xai/plugin.yaml",
    "plugins/spotify/plugin.yaml",
    "plugins/video_gen/deepinfra/plugin.yaml",
    "plugins/video_gen/fal/plugin.yaml",
    "plugins/video_gen/xai/plugin.yaml",
]


def parser_read_keys() -> set[str]:
    """AST-extract the literal keys `_parse_manifest` pulls off the YAML dict."""
    tree = ast.parse((BASELINE / "hermes_cli" / "plugins.py").read_text(encoding="utf-8"))
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_parse_manifest":
            fn = node
            break
    if fn is None:
        raise SystemExit("_parse_manifest not found")
    keys = set()
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "data"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            keys.add(node.args[0].value)
    return keys


def top_keys(path: Path) -> list[str]:
    """Top-level YAML keys, in file order. Manifests here are flat + simple."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line[0] in " \t#":
            continue
        if ":" in line:
            out.append(line.split(":", 1)[0].strip())
    return out


def list_values(path: Path, key: str) -> list[str]:
    """Values of a simple `key:` / `  - item` block."""
    lines = path.read_text(encoding="utf-8").splitlines()
    out, inside = [], False
    for line in lines:
        if line.startswith(f"{key}:"):
            inside = True
            continue
        if inside:
            stripped = line.strip()
            if stripped.startswith("- "):
                out.append(stripped[2:].strip())
            elif stripped and not line[0].isspace():
                break
    return out


def main() -> int:
    read = parser_read_keys()
    print("parser read-set (_parse_manifest, AST): " + ", ".join(sorted(read)))
    print()
    observed: dict[str, list[str]] = {}
    for rel in SLICE_E_MANIFESTS:
        p = BASELINE / rel
        keys = top_keys(p)
        for k in keys:
            observed.setdefault(k, []).append(rel)
        detail = []
        for k in ("requires_env", "optional_env", "provides_tools",
                  "provides_browser_providers", "provides_web_providers",
                  "hooks", "provides_hooks", "platforms", "pip_dependencies"):
            if k in keys:
                detail.append(f"{k}=[{', '.join(list_values(p, k))}]")
        print(f"{rel}")
        print(f"    keys: {', '.join(keys)}")
        if detail:
            print(f"    {'; '.join(detail)}")
    print()
    print(f"manifests: {len(SLICE_E_MANIFESTS)}   distinct top-level keys: {len(observed)}")
    for k in sorted(observed):
        state = "READ  " if k in read else "UNREAD"
        print(f"  {state} {k:<28} x{len(observed[k])}")
    unread = [k for k in observed if k not in read]
    print(f"UNREAD keys in slice E: {len(unread)} -> {', '.join(sorted(unread)) or '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
