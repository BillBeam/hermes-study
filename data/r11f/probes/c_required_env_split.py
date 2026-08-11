#!/usr/bin/env python3
"""R11F 片 C:同一件事的两处声明 —— plugin.yaml 的 ``requires_env``
vs ``ctx.register_platform(required_env=[...])``。

两者都叫"这个平台必须有哪些环境变量",但走两条完全不同的消费链:

  plugin.yaml: requires_env
      -> hermes_cli/plugins.py::_parse_manifest  -> PluginManifest.requires_env
      -> hermes_cli/config.py::_inject_platform_plugin_env_vars -> 设置向导输入面

  register_platform(required_env=...)
      -> gateway/platform_registry.py::PlatformEntry.required_env
      -> 网关侧的"这个平台配齐了吗"检查

于是它们可以**各说各话**而没有任何东西会发现。本探针把两边逐平台对齐。

用法(cwd 任意;基线路径可用 HERMES_BASELINE 覆盖):
    python3 data/r11f/probes/c_required_env_split.py --table
    python3 data/r11f/probes/c_required_env_split.py --counts
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


def yaml_requires(p: str) -> list[str]:
    m = yaml.safe_load(
        (BASELINE / "plugins/platforms" / p / "plugin.yaml").read_text(encoding="utf-8")
    ) or {}
    out = []
    for e in (m.get("requires_env") or []):
        if isinstance(e, str):
            out.append(e)
        elif isinstance(e, dict) and e.get("name"):
            out.append(e["name"])
    return out


def registry_required(p: str) -> list[str] | None:
    """register_platform(required_env=...) 的字面量列表;非字面量返回 None。"""
    d = BASELINE / "plugins/platforms" / p
    for f in sorted(d.rglob("*.py")):
        src = f.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr == "register_platform"):
                continue
            for k in node.keywords:
                if k.arg != "required_env":
                    continue
                if isinstance(k.value, ast.List) and all(
                    isinstance(e, ast.Constant) for e in k.value.elts
                ):
                    return [e.value for e in k.value.elts]
                return None
            return []
    return None


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--table"
    rows = []
    for p in PLATFORMS:
        y = yaml_requires(p)
        r = registry_required(p)
        rows.append((p, y, r if r is not None else []))

    if mode == "--counts":
        agree = sum(1 for _, y, r in rows if set(y) == set(r))
        print(f"platforms={len(rows)}")
        print(f"identical_sets={agree}")
        print(f"differing_sets={len(rows) - agree}")
        print(f"yaml_only_total={sum(len(set(y) - set(r)) for _, y, r in rows)}")
        print(f"registry_only_total={sum(len(set(r) - set(y)) for _, y, r in rows)}")
        return

    if mode == "--table":
        print(f"{'platform':<14} {'yaml':>4} {'reg':>4}  {'agree':<5} "
              f"yaml_only | registry_only")
        for p, y, r in rows:
            yo = sorted(set(y) - set(r))
            ro = sorted(set(r) - set(y))
            ok = "Y" if set(y) == set(r) else "-"
            print(f"{p:<14} {len(y):>4} {len(r):>4}  {ok:<5} "
                  f"{','.join(yo) or '(none)'} | {','.join(ro) or '(none)'}")
        return

    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
