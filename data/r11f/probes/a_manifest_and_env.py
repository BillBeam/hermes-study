#!/usr/bin/env python3
"""R11F 片 A —— manifest 键面 + env 变量面的机械枚举(判据 2)。

两件事:
  (1) 三份 plugin.yaml 的**顶层键集**与 requires_env / optional_env 的
      **每一条 name 与子字段**,逐份列全(设置向导的输入面);
  (2) 三个适配器**源码里实际读取**的 `<PLATFORM>_*` 环境变量名(AST 扫
      os.environ / os.getenv / _env_flag 之类的字面量实参),与 manifest
      声明的那一份**求差**。

yaml 用 PyYAML 解析;若不可用则退回极简行解析(本片三份 manifest 结构固定)。
不 import 基线任何模块。

用法: python3 a_manifest_and_env.py [基线路径] [--mode summary|env|manifest]
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

PLATFORMS = [
    ("discord", "DISCORD_"),
    ("telegram", "TELEGRAM_"),
    ("slack", "SLACK_"),
]
MANIFEST = "plugins/platforms/{p}/plugin.yaml"


def load_manifest(path: Path) -> dict:
    try:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    # 退化解析:只认本片三份 manifest 的固定形态
    data, cur_list, cur_item = {}, None, None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", raw)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val in ("", ">", ">-", "|"):
                data[key] = [] if key.endswith("_env") else ""
                cur_list = data[key] if isinstance(data[key], list) else None
            else:
                data[key] = val.strip('"')
                cur_list = None
            cur_item = None
            continue
        m = re.match(r"^\s+- name:\s*(.*)$", raw)
        if m and cur_list is not None:
            cur_item = {"name": m.group(1).strip().strip('"')}
            cur_list.append(cur_item)
            continue
        m = re.match(r"^\s+([a-z_]+):\s*(.*)$", raw)
        if m and cur_item is not None:
            cur_item[m.group(1)] = m.group(2).strip().strip('"')
    return data


ENV_CALL_NAMES = {"getenv", "_env_bool"}   # os.getenv(...) / _env_bool(...)


def _is_env_read(node: ast.AST) -> bool:
    """node 是否是一次「读环境变量」的表达式(窄口径)。"""
    if isinstance(node, ast.Call):
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr in ENV_CALL_NAMES:
            return True
        if isinstance(fn, ast.Name) and fn.id in ENV_CALL_NAMES:
            return True
        # os.environ.get(...)
        if isinstance(fn, ast.Attribute) and fn.attr == "get":
            v = fn.value
            if isinstance(v, ast.Attribute) and v.attr == "environ":
                return True
    if isinstance(node, ast.Subscript):
        v = node.value
        if isinstance(v, ast.Attribute) and v.attr == "environ":
            return True
    return False


def env_names_in(src: str, prefix: str, narrow: bool = False) -> dict:
    """返回 {ENV_NAME: 首次出现行号}。

    宽口径(narrow=False):任意字符串字面量以 prefix 开头且全为 [A-Z0-9_]。
      —— 覆盖那些先塞进元组常量(如 `_GATE_ENV_KEYS`)再循环读的名字,
         代价是会吞进同形状的**非** env 字面量(实测 1 处:SLACK_AVAILABLE 是
         模块注入命名空间的字典键)。
    窄口径(narrow=True):只认直接出现在 os.getenv / os.environ.get /
      os.environ[...] / _env_bool(...) 里的字面量。
      —— 代价是漏掉常量表间接读法。
    f-string 拼接两个口径都不计(无法静态定名)。
    """
    out: dict[str, int] = {}
    tree = ast.parse(src)
    if narrow:
        holders = [n for n in ast.walk(tree) if _is_env_read(n)]
        walker = [c for h in holders for c in ast.walk(h)]
    else:
        walker = list(ast.walk(tree))
    for node in walker:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if v.startswith(prefix) and re.fullmatch(r"[A-Z0-9_]+", v):
                if v not in out or node.lineno < out[v]:
                    out[v] = node.lineno
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    root = Path(args[0]) if args else Path("/home/user/hermes-agent")
    mode = "summary"
    for f in flags:
        if f.startswith("--mode"):
            mode = f.split("=", 1)[1] if "=" in f else "summary"

    for p, prefix in PLATFORMS:
        mpath = root / MANIFEST.format(p=p)
        man = load_manifest(mpath)
        req = [e["name"] for e in (man.get("requires_env") or [])]
        opt = [e["name"] for e in (man.get("optional_env") or [])]
        declared = set(req) | set(opt)

        # 该平台目录下**全部** .py 里出现的 <PREFIX>* 字面量(两个口径各扫一遍)
        found: dict[str, tuple[str, int]] = {}
        narrow: dict[str, tuple[str, int]] = {}
        for py in sorted((root / f"plugins/platforms/{p}").rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            rel = str(py.relative_to(root))
            src = py.read_text(encoding="utf-8")
            for name, ln in env_names_in(src, prefix).items():
                if name not in found:
                    found[name] = (rel, ln)
            for name, ln in env_names_in(src, prefix, narrow=True).items():
                if name not in narrow:
                    narrow[name] = (rel, ln)

        if mode == "manifest":
            print(f"== {MANIFEST.format(p=p)}")
            print(f"   top_keys({len(man)}): {' '.join(sorted(man))}")
            for label, lst in (("requires_env", man.get("requires_env") or []),
                               ("optional_env", man.get("optional_env") or [])):
                for e in lst:
                    sub = " ".join(sorted(k for k in e if k != "name"))
                    print(f"   {label}: {e['name']}  [{sub}]")
            continue

        if mode == "env":
            print(f"== {p}: declared={len(declared)} literal={len(found)} "
                  f"undeclared={len(set(found) - declared)}")
            for name in sorted(set(found) - declared):
                rel, ln = found[name]
                mark = "" if name in narrow else "  (间接:常量表)"
                print(f"   {name}\t{rel}:{ln}{mark}")
            continue

        if mode == "envnarrow":
            print(f"== {p}: declared={len(declared)} envcall={len(narrow)} "
                  f"undeclared={len(set(narrow) - declared)}")
            for name in sorted(set(narrow) - declared):
                rel, ln = narrow[name]
                print(f"   {name}\t{rel}:{ln}")
            continue

        print(f"{p:9s} manifest_keys={len(man)} requires_env={len(req)} optional_env={len(opt)} "
              f"literal={len(found)} envcall={len(narrow)} "
              f"undeclared_literal={len(set(found) - declared)} "
              f"undeclared_envcall={len(set(narrow) - declared)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
