#!/usr/bin/env python3
"""R11F 片 B —— 适配器对宿主 ABC 的实现面机械枚举。

把 `gateway/platforms/base.py` 里 `BasePlatformAdapter` 的成员面(抽象方法 /
具体方法 / 属性)与片 B 五家平台适配器的类体逐项对照,输出:

  IMPL-ABSTRACT   覆写了基类的 @abstractmethod
  MISS-ABSTRACT   基类要求但该适配器没实现(靠 MRO 上别处或根本没有 → 实例化会炸)
  OVERRIDE        覆写了基类的具体方法(改了宿主默认行为)
  PLUGIN-ONLY     基类没有、适配器自造的方法(插件私有面,不是契约面)

纯 AST,不 import 被测代码(基线可选依赖是惰性联网安装的)。

用法:
    python3 data/r11f/probes/b_adapter_contract.py            # 摘要
    python3 data/r11f/probes/b_adapter_contract.py --full     # 全表 TSV
    python3 data/r11f/probes/b_adapter_contract.py --kind MISS-ABSTRACT
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

BASELINE = Path("/home/user/hermes-agent")
BASE_FILE = "gateway/platforms/base.py"
BASE_CLASS = "BasePlatformAdapter"

# 片 B 的适配器类:(平台名, 文件, 类名)
ADAPTERS = [
    ("dingtalk", "plugins/platforms/dingtalk/adapter.py", "DingTalkAdapter"),
    ("feishu", "plugins/platforms/feishu/adapter.py", "FeishuAdapter"),
    ("google_chat", "plugins/platforms/google_chat/adapter.py", "GoogleChatAdapter"),
    ("matrix", "plugins/platforms/matrix/adapter.py", "MatrixAdapter"),
    ("wecom", "plugins/platforms/wecom/adapter.py", "WeComAdapter"),
    ("wecom_callback", "plugins/platforms/wecom/callback_adapter.py",
     "WecomCallbackAdapter"),
]


def _decorator_names(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for d in getattr(node, "decorator_list", []):
        cur = d
        if isinstance(cur, ast.Call):
            cur = cur.func
        parts = []
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        if parts:
            out.add(".".join(reversed(parts)))
    return out


def class_members(path: Path, class_name: str) -> dict[str, dict]:
    """返回 {成员名: {lineno, abstract, kind}}(只看该类自己的类体,不含嵌套类)。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            members: dict[str, dict] = {}
            for stmt in node.body:
                if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                decos = _decorator_names(stmt)
                if "property" in decos:
                    kind = "property"
                elif "staticmethod" in decos:
                    kind = "staticmethod"
                elif "classmethod" in decos:
                    kind = "classmethod"
                elif isinstance(stmt, ast.AsyncFunctionDef):
                    kind = "async def"
                else:
                    kind = "def"
                members[stmt.name] = {
                    "lineno": stmt.lineno,
                    "abstract": "abstractmethod" in decos,
                    "kind": kind,
                }
            return members
    raise SystemExit(f"class {class_name} not found in {path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="打印全表 TSV")
    ap.add_argument("--kind", help="只打印某一类(IMPL-ABSTRACT/MISS-ABSTRACT/OVERRIDE/PLUGIN-ONLY)")
    ap.add_argument("--platform", help="只看某个平台")
    args = ap.parse_args()

    base = class_members(BASELINE / BASE_FILE, BASE_CLASS)
    abstracts = {n for n, m in base.items() if m["abstract"]}

    rows: list[tuple[str, str, str, str, int]] = []
    for plat, rel, cls in ADAPTERS:
        if args.platform and args.platform != plat:
            continue
        mem = class_members(BASELINE / rel, cls)
        for name, meta in sorted(mem.items()):
            if name in abstracts:
                kind = "IMPL-ABSTRACT"
            elif name in base:
                kind = "OVERRIDE"
            else:
                kind = "PLUGIN-ONLY"
            rows.append((plat, name, kind, meta["kind"], meta["lineno"]))
        for name in sorted(abstracts - set(mem)):
            rows.append((plat, name, "MISS-ABSTRACT", base[name]["kind"], 0))

    if args.kind:
        rows = [r for r in rows if r[2] == args.kind]

    if args.full or args.kind:
        print("platform\tmember\tkind\tform\tlineno")
        for r in rows:
            print("\t".join(str(x) for x in r))
        return 0

    print(f"{BASE_CLASS}: 成员 {len(base)},其中 @abstractmethod {len(abstracts)}")
    print("平台\tIMPL-ABSTRACT\tMISS-ABSTRACT\tOVERRIDE\tPLUGIN-ONLY\t类体成员合计")
    for plat, _rel, _cls in ADAPTERS:
        if args.platform and args.platform != plat:
            continue
        sub = [r for r in rows if r[0] == plat]
        c = {k: sum(1 for r in sub if r[2] == k) for k in
             ("IMPL-ABSTRACT", "MISS-ABSTRACT", "OVERRIDE", "PLUGIN-ONLY")}
        total = c["IMPL-ABSTRACT"] + c["OVERRIDE"] + c["PLUGIN-ONLY"]
        print(f"{plat}\t{c['IMPL-ABSTRACT']}\t{c['MISS-ABSTRACT']}\t"
              f"{c['OVERRIDE']}\t{c['PLUGIN-ONLY']}\t{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
