#!/usr/bin/env python3
"""R11F 片 C:平台适配器契约面的机械枚举(纯 AST,不 import 不执行基线代码)。

契约面 = ``gateway/platforms/base.py`` 的 ``BasePlatformAdapter`` 暴露给子类的成员集,
按子类是否覆写划分成三块:

  A. 抽象方法        —— ``@abstractmethod``,子类**必须**实现(不实现则无法实例化)
  B. 被覆写的可选面  —— 基类给了默认实现,而片内 14 家中**至少一家**覆写了它
  C. 未被任何一家覆写的默认面 —— 14 家全部原样继承

再加一块 D:子类**新增**的成员(基类没有的名字),即适配器自己的内部面。

用法(cwd 任意;基线路径可用 HERMES_BASELINE 覆盖):
    python3 data/r11f/probes/c_adapter_contract.py --summary
    python3 data/r11f/probes/c_adapter_contract.py --abstract
    python3 data/r11f/probes/c_adapter_contract.py --overridden
    python3 data/r11f/probes/c_adapter_contract.py --inherited
    python3 data/r11f/probes/c_adapter_contract.py --additions
    python3 data/r11f/probes/c_adapter_contract.py --counts
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))

# 片 C 的 14 家,按 slices/C.txt 的目录顺序
PLATFORMS = [
    "photon", "a2a", "whatsapp", "line", "buzz", "teams", "simplex",
    "mattermost", "email", "irc", "raft", "ntfy", "homeassistant", "sms",
]


def _decorator_names(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for d in getattr(node, "decorator_list", []):
        cur = d.func if isinstance(d, ast.Call) else d
        while isinstance(cur, ast.Attribute):
            cur = cur.value
        if isinstance(cur, ast.Name):
            out.add(cur.id)
        # 形如 @foo.setter / @abc.abstractmethod:把属性名也收进来
        d2 = d.func if isinstance(d, ast.Call) else d
        if isinstance(d2, ast.Attribute):
            out.add(d2.attr)
    return out


def class_members(cls: ast.ClassDef) -> dict[str, dict]:
    """类体里直接定义的方法/属性 → {kind, abstract, lineno}。"""
    members: dict[str, dict] = {}
    for node in cls.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decs = _decorator_names(node)
        if "property" in decs:
            kind = "property"
        elif "staticmethod" in decs:
            kind = "staticmethod"
        elif "classmethod" in decs:
            kind = "classmethod"
        elif isinstance(node, ast.AsyncFunctionDef):
            kind = "async def"
        else:
            kind = "def"
        prev = members.get(node.name)
        if prev is not None:
            # property + setter 同名:保留首次(property)的行号
            prev["abstract"] = prev["abstract"] or ("abstractmethod" in decs)
            continue
        members[node.name] = {
            "kind": kind,
            "abstract": "abstractmethod" in decs,
            "lineno": node.lineno,
        }
    return members


def find_class(tree: ast.Module, name: str) -> ast.ClassDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def base_face() -> dict[str, dict]:
    src = (BASELINE / "gateway/platforms/base.py").read_text(encoding="utf-8")
    cls = find_class(ast.parse(src), "BasePlatformAdapter")
    assert cls is not None, "BasePlatformAdapter not found in gateway/platforms/base.py"
    return class_members(cls)


def adapter_classes() -> dict[str, tuple[str, int, dict[str, dict]]]:
    """platform -> (类名, 行号, 成员表)。只取直接继承 BasePlatformAdapter 的那个类。"""
    out: dict[str, tuple[str, int, dict[str, dict]]] = {}
    for p in PLATFORMS:
        path = BASELINE / "plugins/platforms" / p / "adapter.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hit = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = {
                b.id if isinstance(b, ast.Name) else getattr(b, "attr", "")
                for b in node.bases
            }
            if "BasePlatformAdapter" in base_names:
                assert hit is None, f"{p}: 不止一个直接子类"
                hit = node
        assert hit is not None, f"{p}: 找不到 BasePlatformAdapter 子类"
        out[p] = (hit.name, hit.lineno, class_members(hit))
    return out


def mark(row: dict[str, dict], name: str) -> str:
    return "Y" if name in row else "."


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--summary"
    base = base_face()
    subs = adapter_classes()
    abstract = sorted(n for n, m in base.items() if m["abstract"])
    overridden = sorted(
        n for n in base
        if not base[n]["abstract"]
        and any(n in subs[p][2] for p in PLATFORMS)
    )
    inherited = sorted(
        n for n in base
        if not base[n]["abstract"]
        and not any(n in subs[p][2] for p in PLATFORMS)
    )

    if mode == "--counts":
        print(f"base_members={len(base)}")
        print(f"abstract={len(abstract)}")
        print(f"overridden_optional={len(overridden)}")
        print(f"inherited_untouched={len(inherited)}")
        print(f"platforms={len(PLATFORMS)}")
        print(f"contract_cells={(len(abstract) + len(overridden)) * len(PLATFORMS)}")
        adds = sum(len([n for n in subs[p][2] if n not in base]) for p in PLATFORMS)
        pub = sum(len([n for n in subs[p][2]
                       if n not in base and not n.startswith("_")])
                  for p in PLATFORMS)
        print(f"additions_total={adds}")
        print(f"additions_public={pub}")
        return

    if mode == "--summary":
        print(f"{'platform':<14} {'class':<22} {'line':>5} "
              f"{'abs':>4} {'ovr':>4} {'add':>4} {'pubadd':>7}")
        for p in PLATFORMS:
            cname, lineno, mem = subs[p]
            a = sum(1 for n in abstract if n in mem)
            o = sum(1 for n in overridden if n in mem)
            add = [n for n in mem if n not in base]
            pub = [n for n in add if not n.startswith("_")]
            print(f"{p:<14} {cname:<22} {lineno:>5} "
                  f"{a:>4} {o:>4} {len(add):>4} {len(pub):>7}")
        return

    if mode in ("--abstract", "--overridden", "--inherited"):
        names = {"--abstract": abstract, "--overridden": overridden,
                 "--inherited": inherited}[mode]
        if mode == "--inherited":
            for n in names:
                print(f"{base[n]['lineno']:>5} {base[n]['kind']:<13} {n}")
            return
        hdr = "".join(f"{p[:4]:>5}" for p in PLATFORMS)
        print(f"{'base_line':>9} {'kind':<13} {'member':<34}{hdr}")
        for n in names:
            cells = "".join(f"{mark(subs[p][2], n):>5}" for p in PLATFORMS)
            print(f"{base[n]['lineno']:>9} {base[n]['kind']:<13} {n:<34}{cells}")
        return

    if mode == "--additions":
        for p in PLATFORMS:
            _, _, mem = subs[p]
            pub = sorted(n for n in mem if n not in base and not n.startswith("_"))
            priv = sorted(n for n in mem if n not in base and n.startswith("_"))
            print(f"## {p}  public+{len(pub)}  private+{len(priv)}")
            for n in pub:
                print(f"   {mem[n]['lineno']:>5} {mem[n]['kind']:<13} {n}")
        return

    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
