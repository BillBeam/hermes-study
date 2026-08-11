#!/usr/bin/env python3
"""R11F 片 C:``ctx.register_platform(...)`` 注册面的机械枚举(纯 AST)。

平台插件往宿主注册能力**只有一个入口**:``register(ctx)`` 里的 ``ctx.register_platform()``。
它的 kwargs 直落 ``gateway/platform_registry.py`` 的 ``PlatformEntry`` 数据类字段
(``register_platform`` 只显式接 8 个参数,其余 ``**entry_kwargs`` 原样转发,
未知键由 dataclass 构造器抛 TypeError)。

所以「注册面」= PlatformEntry 的全部字段 × 14 家实际传了哪些。

用法(cwd 任意;基线路径可用 HERMES_BASELINE 覆盖):
    python3 data/r11f/probes/c_register_seam.py --fields
    python3 data/r11f/probes/c_register_seam.py --matrix
    python3 data/r11f/probes/c_register_seam.py --values
    python3 data/r11f/probes/c_register_seam.py --counts
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))

PLATFORMS = [
    "photon", "a2a", "whatsapp", "line", "buzz", "teams", "simplex",
    "mattermost", "email", "irc", "raft", "ntfy", "homeassistant", "sms",
]


def entry_fields() -> list[tuple[str, str]]:
    """PlatformEntry 的字段列表 (name, 'required'|'default')。"""
    src = (BASELINE / "gateway/platform_registry.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls = next(n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef) and n.name == "PlatformEntry")
    out = []
    for node in cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.append((node.target.id,
                        "default" if node.value is not None else "required"))
    return out


def find_register_call(p: str) -> tuple[str, int, dict[str, str]]:
    """(相对路径, 行号, {kwarg: 值的源码单行摘要})。"""
    d = BASELINE / "plugins/platforms" / p
    for f in sorted(d.rglob("*.py")):
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr == "register_platform"):
                continue
            kw = {}
            for k in node.keywords:
                if k.arg is None:
                    kw["**"] = "**kwargs"
                    continue
                seg = ast.get_source_segment(src, k.value) or "?"
                kw[k.arg] = " ".join(seg.split())
            rel = str(f.relative_to(BASELINE))
            return rel, node.lineno, kw
    raise AssertionError(f"{p}: 找不到 register_platform 调用")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--matrix"
    fields = entry_fields()
    fnames = [n for n, _ in fields]
    calls = {p: find_register_call(p) for p in PLATFORMS}

    if mode == "--fields":
        for n, req in fields:
            used = sum(1 for p in PLATFORMS if n in calls[p][2])
            print(f"{n:<24} {req:<9} used_by={used:>2}")
        return

    if mode == "--counts":
        print(f"entry_fields={len(fields)}")
        print(f"platforms={len(PLATFORMS)}")
        print(f"cells={len(fields) * len(PLATFORMS)}")
        never = [n for n in fnames if not any(n in calls[p][2] for p in PLATFORMS)]
        print(f"fields_never_passed={len(never)}")
        print(f"never_passed={','.join(never)}")
        extra = sorted({k for p in PLATFORMS for k in calls[p][2]
                        if k not in fnames and k != "**"})
        print(f"kwargs_not_entry_fields={','.join(extra) if extra else '(none)'}")
        total = sum(len([k for k in calls[p][2] if k != "**"]) for p in PLATFORMS)
        print(f"kwargs_passed_total={total}")
        return

    if mode == "--matrix":
        hdr = "".join(f"{p[:4]:>5}" for p in PLATFORMS)
        print(f"{'PlatformEntry field':<24}{'kind':>9} {'n':>2}{hdr}")
        for n, req in fields:
            cells = "".join(f"{('Y' if n in calls[p][2] else '.'):>5}"
                            for p in PLATFORMS)
            cnt = sum(1 for p in PLATFORMS if n in calls[p][2])
            print(f"{n:<24}{req:>9} {cnt:>2}{cells}")
        return

    if mode == "--values":
        for p in PLATFORMS:
            rel, lineno, kw = calls[p]
            print(f"## {p}  {rel}:{lineno}  kwargs={len(kw)}")
            for k in fnames:
                if k in kw:
                    v = kw[k]
                    print(f"   {k:<22} {v[:96]}")
            for k in sorted(kw):
                if k not in fnames:
                    print(f"   {k:<22} {kw[k][:96]}   <-- NOT a PlatformEntry field")
        return

    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
