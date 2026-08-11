#!/usr/bin/env python3
"""R11F 片 D 探针:dashboard_auth 四个 provider 对宿主 ABC 的实现面矩阵。

判据 2 的认证面枚举。对 `hermes_cli/dashboard_auth/base.py` 的
`DashboardAuthProvider` 抽象基类,逐项列出:

  * ABC 侧:@abstractmethod 名单 + 可选能力开关(supports_*)的默认值;
  * 四个 provider 侧:哪些方法**自己定义了**、哪些**继承基类**、
    有没有**多出来的**公开方法,以及各自把哪些 supports_* 翻成 True。

「实现了但只是 raise NotImplementedError」与「真的实现了」要分开 ——
drain 那种只做 token 能力的 provider 会把五个交互方法定义出来只为抛异常,
只看"有没有 def"会把它数成全实现。所以额外判定函数体是否只抛异常。

纯 AST,不 import 被测模块(无惰性安装副作用)。

用法:
    python3 d_auth_provider_matrix.py <基线根>
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ABC_FILE = "hermes_cli/dashboard_auth/base.py"
ABC_NAME = "DashboardAuthProvider"
PROVIDERS = {
    "basic": "plugins/dashboard_auth/basic/__init__.py",
    "drain": "plugins/dashboard_auth/drain/__init__.py",
    "nous": "plugins/dashboard_auth/nous/__init__.py",
    "self_hosted": "plugins/dashboard_auth/self_hosted/__init__.py",
}


def find_class(tree: ast.AST, name: str) -> ast.ClassDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def subclass_of(node: ast.ClassDef, base: str) -> bool:
    for b in node.bases:
        if isinstance(b, ast.Name) and b.id == base:
            return True
        if isinstance(b, ast.Attribute) and b.attr == base:
            return True
    return False


def body_only_raises(fn: ast.AST) -> bool:
    """函数体除 docstring 外只有一条 raise —— 即"定义了但没实现"。"""
    stmts = list(getattr(fn, "body", []))
    if stmts and isinstance(stmts[0], ast.Expr) and isinstance(
        getattr(stmts[0], "value", None), ast.Constant
    ) and isinstance(stmts[0].value.value, str):
        stmts = stmts[1:]
    return len(stmts) == 1 and isinstance(stmts[0], ast.Raise)


def class_methods(node: ast.ClassDef) -> dict[str, tuple[int, bool, bool]]:
    """名字 -> (行号, 是否 abstractmethod, 是否只抛异常)"""
    out: dict[str, tuple[int, bool, bool]] = {}
    for item in node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_abstract = any(
            (isinstance(d, ast.Name) and d.id == "abstractmethod")
            or (isinstance(d, ast.Attribute) and d.attr == "abstractmethod")
            for d in item.decorator_list
        )
        out[item.name] = (item.lineno, is_abstract, body_only_raises(item))
    return out


def class_flags(node: ast.ClassDef) -> dict[str, str]:
    """类体里的简单赋值(name = literal),取 supports_* / name / display_name。"""
    out: dict[str, str] = {}
    for item in node.body:
        target = None
        value = None
        if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
            target, value = item.targets[0].id, item.value
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            target, value = item.target.id, item.value
        if target and isinstance(value, ast.Constant):
            out[target] = repr(value.value)
    return out


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/user/hermes-agent")

    abc_tree = ast.parse((root / ABC_FILE).read_text(encoding="utf-8"))
    abc_node = find_class(abc_tree, ABC_NAME)
    assert abc_node is not None, "ABC not found"
    abc_methods = class_methods(abc_node)
    abstract = [m for m, (_, a, _) in abc_methods.items() if a]
    optional = [m for m, (_, a, _) in abc_methods.items() if not a and not m.startswith("_")]
    abc_flags = class_flags(abc_node)

    print(f"ABC {ABC_FILE}:{abc_node.lineno} {ABC_NAME}")
    print(f"  abstract({len(abstract)}): {','.join(abstract)}")
    print(f"  concrete-optional({len(optional)}): {','.join(optional)}")
    print(f"  capability defaults: " + ",".join(
        f"{k}={v}" for k, v in abc_flags.items() if k.startswith("supports_")
    ))
    print()

    contract = set(abstract) | set(optional)
    for label, rel in PROVIDERS.items():
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        impl = next(
            (n for n in ast.walk(tree)
             if isinstance(n, ast.ClassDef) and subclass_of(n, ABC_NAME)),
            None,
        )
        assert impl is not None, f"no {ABC_NAME} subclass in {rel}"
        methods = class_methods(impl)
        flags = class_flags(impl)
        real, stub, missing = [], [], []
        for m in sorted(contract):
            if m not in methods:
                missing.append(m)
            elif methods[m][2]:
                stub.append(f"{m}@{methods[m][0]}")
            else:
                real.append(f"{m}@{methods[m][0]}")
        extra = sorted(
            m for m in methods
            if m not in contract and not m.startswith("_")
        )
        print(f"{rel}:{impl.lineno} class {impl.name}")
        print(f"  identity: " + ",".join(
            f"{k}={flags[k]}" for k in ("name", "display_name") if k in flags
        ))
        print(f"  capability overrides: " + (",".join(
            f"{k}={v}" for k, v in flags.items() if k.startswith("supports_")
        ) or "(none — all ABC defaults)"))
        print(f"  implemented({len(real)}): {','.join(real)}")
        print(f"  stub-raises({len(stub)}): {','.join(stub) or '-'}")
        print(f"  inherited-not-overridden({len(missing)}): {','.join(missing) or '-'}")
        print(f"  extra-public({len(extra)}): {','.join(extra) or '-'}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
