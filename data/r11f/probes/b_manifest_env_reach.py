#!/usr/bin/env python3
"""R11F 片 B —— 五份 plugin.yaml 的清单键面 + 声明的 env 变量能否被代码读到。

两张表:
  --keys   每份 manifest 的顶层键集(逐份列全,不做并集)
  --env    每条 requires_env / optional_env 的变量名 → 基线里谁在读它

「谁在读它」的判据是**字面量出现**,不是语义:变量名可以被
`os.getenv(NAME)`、`_get_scoped_secret(NAME)` 读,也可以作为
`register_platform(cron_deliver_env_var="NAME")` 这样的注册参数被宿主间接读。
三种写法的共同点只有「这个字符串在某个 .py 里出现过」,所以判据就定在这里,
并按三个互不重叠的面分别报数,让「只有测试提到它」和「文档提到它」当场可见:

  py_prod   非 tests/ 的 .py 里的出现次数(自身 manifest 不计,因为 yaml 不是 .py)
  py_test   tests/ 下的 .py 里的出现次数
  docs      website/ 下的 .md 里的出现次数

py_prod == 0 即「声明了但没有任何生产代码读它」。

用法:
    python3 data/r11f/probes/b_manifest_env_reach.py --keys
    python3 data/r11f/probes/b_manifest_env_reach.py --env
    python3 data/r11f/probes/b_manifest_env_reach.py --env --dead   # 只列 py_prod == 0
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BASELINE = Path("/home/user/hermes-agent")
PLATFORMS = ["dingtalk", "feishu", "google_chat", "matrix", "wecom"]

_TOP_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):")
_ENV_NAME = re.compile(r"^\s*-\s+name:\s*([A-Z][A-Z0-9_]*)\s*$")
_ENV_BLOCK = re.compile(r"^(requires_env|optional_env):")
_SUBFIELD = re.compile(r"^\s+([a-z_]+):")


def manifest_lines(plat: str) -> list[str]:
    p = BASELINE / "plugins" / "platforms" / plat / "plugin.yaml"
    return p.read_text(encoding="utf-8").splitlines()


def top_keys(plat: str) -> list[str]:
    """顶层键 = 顶格且形如 `key:` 的行(YAML 块标量的续行有缩进,不会误吞)。"""
    out: list[str] = []
    for line in manifest_lines(plat):
        m = _TOP_KEY.match(line)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def env_entries(plat: str) -> list[tuple[str, str, list[str]]]:
    """返回 [(block, ENV_NAME, [子字段…])]。"""
    out: list[tuple[str, str, list[str]]] = []
    block = ""
    for line in manifest_lines(plat):
        b = _ENV_BLOCK.match(line)
        if b:
            block = b.group(1)
            continue
        if _TOP_KEY.match(line):
            block = ""
            continue
        if not block:
            continue
        m = _ENV_NAME.match(line)
        if m:
            out.append((block, m.group(1), ["name"]))
            continue
        s = _SUBFIELD.match(line)
        if s and out and s.group(1) != "name":
            out[-1][2].append(s.group(1))
    return out


def _walk(root: Path, suffix: str):
    for p in root.rglob(f"*{suffix}"):
        if "__pycache__" in p.parts or ".git" in p.parts:
            continue
        yield p


_INDEX: dict[str, dict[str, int]] = {}
_FIRST: dict[str, str] = {}


def build_index(names: list[str]) -> None:
    """按**词边界**统计,不用子串:`MATRIX_HOME_CHANNEL` 不该被
    `MATRIX_HOME_CHANNEL_NAME` 顺带记一笔,否则 py_prod==0 这个判据会被稀释。"""
    pats = {n: re.compile(rf"\b{re.escape(n)}\b") for n in names}
    faces = {
        "py_prod": (BASELINE, ".py"),
        "py_test": (BASELINE / "tests", ".py"),
        "docs": (BASELINE / "website", ".md"),
    }
    for face, (root, suffix) in faces.items():
        if not root.is_dir():
            continue
        for p in _walk(root, suffix):
            rel = p.relative_to(BASELINE).as_posix()
            if face == "py_prod" and rel.startswith("tests/"):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name, pat in pats.items():
                n = len(pat.findall(text))
                if not n:
                    continue
                _INDEX.setdefault(name, {}).setdefault(face, 0)
                _INDEX[name][face] += n
                if face == "py_prod" and name not in _FIRST:
                    _FIRST[name] = rel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", action="store_true")
    ap.add_argument("--env", action="store_true")
    ap.add_argument("--dead", action="store_true", help="--env 时只列 py_prod == 0")
    args = ap.parse_args()

    if args.keys:
        print("platform\tn_keys\tkeys")
        for plat in PLATFORMS:
            ks = top_keys(plat)
            print(f"{plat}\t{len(ks)}\t{','.join(ks)}")
        allk: list[str] = []
        for plat in PLATFORMS:
            for k in top_keys(plat):
                if k not in allk:
                    allk.append(k)
        print(f"UNION\t{len(allk)}\t{','.join(sorted(allk))}")
        return 0

    if args.env:
        declared = [(plat, b, n, s) for plat in PLATFORMS
                    for b, n, s in env_entries(plat)]
        build_index([n for _p, _b, n, _s in declared])
        rows = []
        for plat, block, name, subs in declared:
            hit = _INDEX.get(name, {})
            rows.append((plat, block, name, ",".join(subs),
                         hit.get("py_prod", 0), hit.get("py_test", 0),
                         hit.get("docs", 0), _FIRST.get(name, "-")))
        if args.dead:
            rows = [r for r in rows if r[4] == 0]
        print("platform\tblock\tenv\tsubfields\tpy_prod\tpy_test\tdocs\tfirst_py_prod")
        for r in rows:
            print("\t".join(str(x) for x in r))
        print(f"TOTAL\t{len(rows)}")
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
