#!/usr/bin/env python3
"""R9D 结构性结论的机械化检验:全仓有多少条「按工具名判定」的守卫?

本章的论点是「守卫绑在工具名上,而不是绑在效果上」,证据是 8 个人工撞见的实例。
人工实例的问题是**无法排除挑选偏差**。本脚本把这个形态做成一次可重跑的枚举:

  找出所有**模块级、由字符串字面量构成的 set / frozenset 常量**,
  其元素与「已注册工具名集合」有交集 —— 即"按工具名列举"的常量;
  报出每个常量覆盖了多少个已注册工具、漏掉多少。

**这不是缺陷检测器**:一个只列 2 个名字的常量完全可能是对的(它本就只该管那两个)。
它回答的是一个更弱但可验证的问题:**这种"按名字列举工具"的写法在本仓库有多普遍?**

不 import 被测代码(纯 AST),不写基线。
用法:python3 name_keyed_guard_census.py /home/user/hermes-agent
"""
import ast
import sys
from pathlib import Path


def registered_tool_names(repo: Path) -> set:
    """从 toolsets.py 的 TOOLSETS 字面量里收集全部工具名(不 import)。"""
    names = set()
    tree = ast.parse((repo / "toolsets.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "TOOLSETS" for t in node.targets
        ):
            for v in node.value.values:
                if not isinstance(v, ast.Dict):
                    continue
                for k, vv in zip(v.keys, v.values):
                    if isinstance(k, ast.Constant) and k.value == "tools":
                        for e in ast.walk(vv):
                            if isinstance(e, ast.Constant) and isinstance(e.value, str):
                                names.add(e.value)
    return names


def string_set_constants(repo: Path):
    """产出 (path, lineno, const_name, {字符串元素}) —— 模块级字符串集合常量。"""
    for py in sorted(repo.rglob("*.py")):
        rel = py.relative_to(repo).as_posix()
        if rel.startswith("tests/") or "/node_modules/" in rel:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in tree.body:                      # 只看模块级
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            tgt = node.targets[0]
            if not isinstance(tgt, ast.Name):
                continue
            val = node.value
            elts = None
            if isinstance(val, ast.Set):
                elts = val.elts
            elif (isinstance(val, ast.Call) and getattr(val.func, "id", None) == "frozenset"
                  and val.args and isinstance(val.args[0], (ast.Set, ast.List, ast.Tuple))):
                elts = val.args[0].elts
            if not elts:
                continue
            strs = {e.value for e in elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)}
            if strs and len(strs) == len(elts):
                yield rel, node.lineno, tgt.id, strs


def main():
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")
    tools = registered_tool_names(repo)
    print(f"已注册工具名(取自 toolsets.py 的 TOOLSETS/tools):{len(tools)} 个\n")

    rows = []
    for rel, lineno, name, strs in string_set_constants(repo):
        hit = strs & tools
        if len(hit) >= 2:                 # 至少命中 2 个才算「按工具名列举」
            rows.append((len(hit), len(strs), len(tools) - len(hit), rel, lineno, name))

    rows.sort(key=lambda r: (-r[0], r[3]))
    print(f"{'命中':>4}{'元素':>5}{'未覆盖':>7}  位置")
    for hit, size, missing, rel, lineno, name in rows:
        print(f"{hit:>4}{size:>5}{missing:>7}  {rel}:{lineno}  {name}")

    print(f"\n合计:{len(rows)} 个「按工具名列举」的模块级常量")
    if rows:
        small = [r for r in rows if r[0] <= 5]
        print(f"其中只列 ≤5 个工具的:{len(small)} 个")


if __name__ == "__main__":
    main()
