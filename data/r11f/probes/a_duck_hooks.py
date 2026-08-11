#!/usr/bin/env python3
"""R11F 片 A —— 宿主对适配器的**鸭子类型可选钩子**面(判据 2)。

`BasePlatformAdapter` 的 ABC 只强制 4 个方法,其余 122 个是有默认实现的具体方法。
但真正的契约不止 ABC:宿主还会用 `getattr(adapter, "<名字>", 默认)` 去**探**一批
适配器**可以有、也可以没有**的属性/方法。这批名字不在 ABC 里、不在 `PlatformEntry` 里,
也不在 `plugin.yaml` 里 —— 它们只以字符串字面量的形式活在宿主源码中。

本探针在宿主侧目录里 AST 扫 `getattr(<变量>, "<名>", ...)`,把 `<变量>` 名形如
adapter / _adapter / self._adapter / adapters[...] 的那些收集起来,再按
「基类有没有这个名字」「三家适配器各自有没有」分类。

用法: python3 a_duck_hooks.py [基线路径] [--mode summary|table]
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

HOST_DIRS = ["gateway", "hermes_cli"]
BASE_REL = "gateway/platforms/base.py"
ADAPTERS = [
    ("discord", "plugins/platforms/discord/adapter.py", "DiscordAdapter"),
    ("telegram", "plugins/platforms/telegram/adapter.py", "TelegramAdapter"),
    ("slack", "plugins/platforms/slack/adapter.py", "SlackAdapter"),
]
# getattr 的第一个实参长什么样才算「这是个适配器」
ADAPTER_VARS = {"adapter", "_adapter", "self._adapter", "adp", "a",
                "self.adapter", "target_adapter", "live_adapter",
                "primary_adapter", "src_adapter", "platform_adapter"}


def _names_of_class(path: Path, cls_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == cls_name:
            out = set()
            for item in n.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.add(item.name)
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    out.add(item.target.id)
                elif isinstance(item, ast.Assign):
                    for t in item.targets:
                        if isinstance(t, ast.Name):
                            out.add(t.id)
            # 再收**类体内任意方法**里的 self.X = ... / self.X: T = ...
            # (实例属性也算「有」)。注意必须同时认 AnnAssign:基线大量写
            # `self._pending_messages: Dict[str, MessageEvent] = {}`,
            # 只认 Assign 会把它们全判成「基类没有」—— 本探针初版就是这么错的。
            for item in n.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for s in ast.walk(item):
                    tgts = []
                    if isinstance(s, ast.Assign):
                        tgts = s.targets
                    elif isinstance(s, ast.AnnAssign):
                        tgts = [s.target]
                    for t in tgts:
                        if isinstance(t, ast.Attribute) \
                                and isinstance(t.value, ast.Name) \
                                and t.value.id == "self":
                            out.add(t.attr)
            return out
    raise SystemExit(f"{cls_name} not found in {path}")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    root = Path(args[0]) if args else Path("/home/user/hermes-agent")
    mode = "summary"
    for f in flags:
        if f.startswith("--mode"):
            mode = f.split("=", 1)[1] if "=" in f else "summary"

    hits: dict[str, list[str]] = {}
    for d in HOST_DIRS:
        for py in sorted((root / d).rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            rel = str(py.relative_to(root))
            for n in ast.walk(tree):
                if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                        and n.func.id == "getattr" and len(n.args) >= 2):
                    continue
                obj = ast.unparse(n.args[0])
                if obj not in ADAPTER_VARS:
                    continue
                key = n.args[1]
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    hits.setdefault(key.value, []).append(f"{rel}:{n.lineno}")

    base_names = _names_of_class(root / BASE_REL, "BasePlatformAdapter")
    impls = {label: _names_of_class(root / rel, cls)
             for label, rel, cls in ADAPTERS}

    rows = []
    for name in sorted(hits):
        rows.append((name, name in base_names,
                     [name in impls[l] for l, _, _ in ADAPTERS],
                     hits[name][0], len(hits[name])))

    if mode == "table":
        print("hook\tin_base\tdiscord\ttelegram\tslack\tfirst_probe_site\tprobe_sites")
        for name, inb, flags_, site, cnt in rows:
            print("\t".join([name, "Y" if inb else "N",
                             *["Y" if f else "-" for f in flags_], site, str(cnt)]))
        return 0

    not_in_base = [r for r in rows if not r[1]]
    print(f"duck-typed hooks probed on adapters: {len(rows)} "
          f"(probe sites {sum(r[4] for r in rows)})")
    print(f"  in BasePlatformAdapter     : {len(rows) - len(not_in_base)}")
    print(f"  NOT in BasePlatformAdapter : {len(not_in_base)}")
    for name, _inb, flags_, site, cnt in not_in_base:
        who = " ".join(l for (l, _, _), f in zip(ADAPTERS, flags_) if f) or "(三家都无)"
        print(f"    {name}\t{site}\tx{cnt}\t实现方: {who}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
