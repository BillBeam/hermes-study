#!/usr/bin/env python3
"""R11F 片 D 探针:插件清单(plugin.yaml / manifest.json)键面 + 钩子注册面对账。

回答三个问题,全部机械枚举、不抽样:

  1. 片 D 每份 manifest 的**顶层键集**逐份列全(判据 2 的清单面);
  2. `plugin.yaml` 的 `hooks:` 取值 vs 模块里 `ctx.register_hook("...")` 的实参 —— 两侧对账;
  3. 全仓 97 份 `plugin.yaml` 里 `hooks:` 与 `provides_hooks:` 各被几份声明
     (加载器只读后者,见 hermes_cli/plugins.py:1664)。

只做正则/文本解析,不 import PyYAML(基线 venv 之外的解释器也能跑),
更不 import 被测模块 —— 因此不触发惰性安装、无网络副作用。

用法:
    python3 d_manifest_surface.py <基线根> [slice|census|hooks]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SLICE_MANIFESTS = [
    "plugins/dashboard_auth/basic/plugin.yaml",
    "plugins/dashboard_auth/drain/plugin.yaml",
    "plugins/dashboard_auth/nous/plugin.yaml",
    "plugins/dashboard_auth/self_hosted/plugin.yaml",
    "plugins/observability/langfuse/plugin.yaml",
    "plugins/observability/nemo_relay/plugin.yaml",
]
SLICE_JSON_MANIFESTS = [
    "plugins/kanban/dashboard/manifest.json",
    "plugins/hermes-achievements/dashboard/manifest.json",
]
HOOK_MODULES = {
    "plugins/observability/langfuse/plugin.yaml":
        "plugins/observability/langfuse/__init__.py",
    "plugins/observability/nemo_relay/plugin.yaml":
        "plugins/observability/nemo_relay/__init__.py",
}

TOP_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):")
LIST_ITEM_RE = re.compile(r"^\s+-\s+(.+?)\s*$")
REGISTER_HOOK_RE = re.compile(r"""ctx\.register_hook\(\s*["']([^"']+)["']""")


def top_keys(path: Path) -> list[str]:
    """顶层键 = 行首无缩进且形如 `key:` 的行,按出现顺序、去重。"""
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = TOP_KEY_RE.match(line)
        if m and m.group(1) not in keys:
            keys.append(m.group(1))
    return keys


def block_items(path: Path, key: str) -> list[str]:
    """取顶层 `key:` 之下、到下一个顶层键为止的 `- item` 列表项。"""
    items: list[str] = []
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if TOP_KEY_RE.match(line):
            inside = line.split(":", 1)[0] == key
            continue
        if inside:
            m = LIST_ITEM_RE.match(line)
            if m:
                items.append(m.group(1))
    return items


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/user/hermes-agent")
    mode = sys.argv[2] if len(sys.argv) > 2 else "slice"

    if mode == "slice":
        for rel in SLICE_MANIFESTS:
            print(f"{rel}\t{','.join(top_keys(root / rel))}")
        for rel in SLICE_JSON_MANIFESTS:
            data = json.loads((root / rel).read_text(encoding="utf-8"))
            print(f"{rel}\t{','.join(data.keys())}")
        return 0

    if mode == "hooks":
        # 清单声明 vs 代码注册,逐条对账
        for man_rel, mod_rel in HOOK_MODULES.items():
            declared = block_items(root / man_rel, "hooks")
            registered = REGISTER_HOOK_RE.findall(
                (root / mod_rel).read_text(encoding="utf-8")
            )
            only_declared = [h for h in declared if h not in registered]
            only_registered = [h for h in registered if h not in declared]
            print(f"{man_rel}")
            print(f"  declared({len(declared)}): {','.join(declared)}")
            print(f"  registered({len(registered)}): {','.join(registered)}")
            print(f"  declared_only: {','.join(only_declared) or '-'}")
            print(f"  registered_only: {','.join(only_registered) or '-'}")
        return 0

    if mode == "census":
        all_man = sorted((root / "plugins").rglob("plugin.yaml"))
        with_hooks = [p for p in all_man if "hooks" in top_keys(p)]
        with_provides = [p for p in all_man if "provides_hooks" in top_keys(p)]
        print(f"plugin.yaml total\t{len(all_man)}")
        print(f"top-level key 'hooks'\t{len(with_hooks)}")
        print(f"top-level key 'provides_hooks'\t{len(with_provides)}")
        for p in with_hooks:
            print(f"  hooks: {p.relative_to(root)}")
        return 0

    print(f"unknown mode: {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
