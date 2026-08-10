#!/usr/bin/env python3
"""H-R9C-d 要的全仓普查:测试替身把**被测谓词原样抄了一遍**的地方。

形态(R9C 在 `tests/gateway/relay/test_relay_media.py` 抓到的那个):替身类里定义了一个
与生产代码**同名且函数体逐字相同**的方法。于是这组测试对该谓词的任何改动都无感——
生产代码修好了,测试仍在断言替身里那份旧逻辑,关卡长期空绿。

判据(刻意保守,宁可漏不可滥):
  - 两边函数**同名**;
  - 去掉 docstring 后的函数体 **AST 结构完全一致**(`ast.dump` 逐字比较,忽略行号与格式);
  - 一边在 `tests/` 下,另一边不在;
  - **函数体非平凡**(见 TRIVIAL):`pass` / `return True` / `return self` 这类桩在全仓
    到处同名同体,报出来只是噪音,不是"抄了被测谓词";
  - **该测试文件确实 import 了生产侧那个模块**——否则两个同名同体函数只是巧合,
    而"猜作者指的是哪一次出现"正是本项目一再拒绝的形态。

放宽任一条都会把命中数从两位数抬到三位数,而多出来的全是巧合(实测:只去掉后两条,
命中从 20 涨到 332)。

    python3 data/r11b/probes/test_double_predicate_census.py [基线路径]
默认基线 /home/user/hermes-agent(可用 HERMES_BASELINE 覆盖)。
"""
import ast
import os
import sys
from pathlib import Path


def is_trivial(body: list[ast.stmt]) -> bool:
    """单语句的 pass / return 常量 / return self / raise —— 到处都一样的桩。"""
    if len(body) != 1:
        return False
    s = body[0]
    if isinstance(s, (ast.Pass, ast.Raise)):
        return True
    if isinstance(s, ast.Return):
        v = s.value
        if v is None or isinstance(v, ast.Constant):
            return True
        if isinstance(v, ast.Name) and v.id == "self":
            return True
        if isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name) \
                and v.value.id == "self":
            return True          # return self.foo
    return False


def imported_modules(tree: ast.AST) -> set[str]:
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
            mods.update(f"{n.module}.{a.name}" for a in n.names)
    return mods


def bodies(root: Path):
    """{函数名: [(相对路径, 行号, AST 指纹)]},外加 {测试文件: 导入的模块集合}"""
    out: dict[str, list[tuple[str, int, str]]] = {}
    imports: dict[str, set[str]] = {}
    for p in root.rglob("*.py"):
        if any(part in (".git", "node_modules", "__pycache__") for part in p.parts):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError):
            continue
        rel = p.relative_to(root).as_posix()
        if rel.startswith("tests/"):
            imports[rel] = imported_modules(tree)
        for n in ast.walk(tree):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = list(n.body)
            if body and isinstance(body[0], ast.Expr) and isinstance(
                    getattr(body[0], "value", None), ast.Constant) and isinstance(
                    body[0].value.value, str):
                body = body[1:]          # 去掉 docstring
            if not body:
                continue
            if is_trivial(body):
                continue
            fp = "".join(ast.dump(b, annotate_fields=True) for b in body)
            out.setdefault(n.name, []).append((rel, n.lineno, fp))
    return out, imports


def main(argv: list[str]) -> int:
    root = Path(argv[0] if argv else os.environ.get(
        "HERMES_BASELINE", "/home/user/hermes-agent"))
    idx, imports = bodies(root)
    hits = []
    for name, occs in idx.items():
        tests = [o for o in occs if o[0].startswith("tests/")]
        prod = [o for o in occs if not o[0].startswith("tests/")]
        if not tests or not prod:
            continue
        for t in tests:
            for pr in prod:
                if t[2] != pr[2]:
                    continue
                mod = pr[0][:-3].replace("/", ".")
                if not any(m == mod or m.startswith(mod + ".") or mod.startswith(m + ".")
                           for m in imports.get(t[0], ())):
                    continue
                hits.append((name, t[0], t[1], pr[0], pr[1]))
                break
    hits.sort(key=lambda h: (h[1], h[2]))
    for name, tf, tl, pf, pl in hits:
        print(f"{name}\n    替身 {tf}:{tl}\n    生产 {pf}:{pl}")
    print(f"\n同名同体的测试替身函数:{len(hits)} 处,"
          f"涉及测试文件 {len({h[1] for h in hits})} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
