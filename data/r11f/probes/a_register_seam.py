#!/usr/bin/env python3
"""R11F 片 A —— 插件→宿主注册面(`ctx.register_platform`)的机械枚举(判据 2)。

宿主侧契约是 `gateway/platform_registry.py` 的 `PlatformEntry` 数据类字段全集
(`hermes_cli/plugins.py::register_platform` 把额外 kwargs 原样转发给它,
未知键由 dataclass 构造器抛 TypeError —— 所以字段表就是**完整**的可传键集)。

对三家适配器分别列出:传了哪些键、值是什么、**没传**哪些键。

用法: python3 a_register_seam.py [基线路径] [--mode summary|table]
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ENTRY_REL = "gateway/platform_registry.py"
ENTRY_CLASS = "PlatformEntry"
ADAPTERS = [
    ("discord", "plugins/platforms/discord/adapter.py"),
    ("telegram", "plugins/platforms/telegram/adapter.py"),
    ("slack", "plugins/platforms/slack/adapter.py"),
]
# register_platform 自己吃掉的位置/具名参数(其余走 **entry_kwargs)
EXPLICIT = ["name", "label", "adapter_factory", "check_fn",
            "validate_config", "required_env", "install_hint"]
# PlatformEntry 里由宿主填、插件不该传的
HOST_SET = {"source"}


def entry_fields(root: Path) -> list[tuple[str, int, str | None]]:
    tree = ast.parse((root / ENTRY_REL).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == ENTRY_CLASS:
            return [(i.target.id, i.lineno,
                     ast.unparse(i.value) if i.value is not None else None)
                    for i in n.body if isinstance(i, ast.AnnAssign)]
    raise SystemExit(f"{ENTRY_CLASS} not found")


def register_call(root: Path, rel: str) -> tuple[int, dict[str, str]]:
    """找 register() 里那次 ctx.register_platform(...),返回 (行号, {kw: 源码})。"""
    tree = ast.parse((root / rel).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        fn = n.func
        if isinstance(fn, ast.Attribute) and fn.attr == "register_platform":
            kw = {k.arg: ast.unparse(k.value) for k in n.keywords if k.arg}
            # 位置实参按 register_platform 的形参顺序补名
            for i, a in enumerate(n.args):
                if i < len(EXPLICIT):
                    kw.setdefault(EXPLICIT[i], ast.unparse(a))
            return n.lineno, kw
    raise SystemExit(f"register_platform call not found in {rel}")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    root = Path(args[0]) if args else Path("/home/user/hermes-agent")
    mode = "summary"
    for f in flags:
        if f.startswith("--mode"):
            mode = f.split("=", 1)[1] if "=" in f else "summary"

    fields = entry_fields(root)
    names = [f[0] for f in fields]
    passable = [n for n in names if n not in HOST_SET]

    calls = {label: register_call(root, rel) for label, rel in ADAPTERS}

    if mode == "table":
        print("field\tentry_line\tdefault\tdiscord\ttelegram\tslack")
        for n, ln, dflt in fields:
            row = [n, str(ln), "-" if dflt is None else dflt]
            for label, _ in ADAPTERS:
                row.append(calls[label][1].get(n, "—"))
            print("\t".join(row))
        return 0

    print(f"ENTRY {ENTRY_REL}::{ENTRY_CLASS}  fields={len(fields)} "
          f"plugin_passable={len(passable)} (host-set: {' '.join(sorted(HOST_SET))})")
    for label, rel in ADAPTERS:
        ln, kw = calls[label]
        unknown = sorted(set(kw) - set(names))
        missing = [n for n in passable if n not in kw]
        print(f"{label:9s} {rel}:{ln}  passed={len(kw)} omitted={len(missing)} "
              f"unknown={len(unknown)}")
        print(f"  passed : {' '.join(sorted(kw))}")
        print(f"  omitted: {' '.join(missing)}")
        if unknown:
            print(f"  UNKNOWN(会让 dataclass 抛 TypeError): {' '.join(unknown)}")
    common = set.intersection(*[set(calls[l][1]) for l, _ in ADAPTERS])
    print(f"COMMON   三家都传的键 = {len(common)}: {' '.join(sorted(common))}")
    for label, _ in ADAPTERS:
        only = set(calls[label][1]) - set.union(
            *[set(calls[o][1]) for o, _ in ADAPTERS if o != label])
        print(f"ONLY-{label:9s} {' '.join(sorted(only)) or '(无)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
