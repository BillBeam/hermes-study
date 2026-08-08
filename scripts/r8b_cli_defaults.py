#!/usr/bin/env python3
"""R8B · 结算 R8A 移交的 H-1 / H-2。

H-1: `cli.py` 的 `load_cli_config` 内联 `defaults` 里,哪些键**不在** `DEFAULT_CONFIG`
     ——即"CLI 专属键"。R8A 已数清 28 个,本脚本重算以复核。

H-2: `cli.py` 的 `defaults[key].update(file_config[key])` 是**一层** update。
     真正的受害集合 = **深度 >= 3 的键**(`top.sub.leaf`):用户只要在 `top.sub` 下写任一
     叶子,`defaults[top][sub]` 整个被替换,**同级兄弟叶子全部丢失**。
     本脚本枚举该集合,并对每个受害叶子统计其读取点**有没有硬编码兜底**
     ——没有兜底的那些才是会真出事的。

AST 遍历沿用 R8A `scripts/config_table.py` 的做法(逐节点走,不 literal_eval 整棵树:
`DEFAULT_CONFIG` 里含非字面量值,整树 literal_eval 会失败)。

用法:
    python3 scripts/r8b_cli_defaults.py /home/user/hermes-agent
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path


def literal(node: ast.AST) -> str:
    """把值节点还原成一个可打印的字面量串;还原不了就给类型占位符。"""
    try:
        return repr(ast.literal_eval(node))
    except Exception:
        return f"<expr:{type(node).__name__}>"


def find_dict(tree: ast.Module, name: str, *, inside: str | None = None) -> tuple[ast.Dict, int]:
    """找一个 dict 字面量赋值。inside 给定时,只在该函数体内找。"""
    scopes: list[ast.AST] = []
    if inside:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == inside:
                scopes.append(node)
    else:
        scopes.append(tree)
    for scope in scopes:
        body = ast.walk(scope) if inside else scope.body
        for node in body:
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == name:
                        if isinstance(node.value, ast.Dict):
                            return node.value, node.lineno
    raise SystemExit(f"没找到 dict 字面量 {name}" + (f" (in {inside})" if inside else ""))


def flatten(d: ast.Dict, prefix: str = "") -> list[tuple[str, str, int, bool]]:
    """(dotted_key, default_literal, lineno, is_branch),递归。"""
    out: list[tuple[str, str, int, bool]] = []
    for k_node, v_node in zip(d.keys, d.values):
        if not isinstance(k_node, ast.Constant) or not isinstance(k_node.value, str):
            continue
        key = f"{prefix}{k_node.value}"
        is_branch = isinstance(v_node, ast.Dict) and bool(v_node.keys)
        out.append((key, literal(v_node), k_node.lineno, is_branch))
        if is_branch:
            out.extend(flatten(v_node, prefix=f"{key}."))
    return out


def nested_victims(d: ast.Dict) -> dict[str, tuple[list[str], int]]:
    """H-2 受害集合:`top.sub` 本身是 dict 且叶子数 >= 2 时,这些叶子互为"连坐"。

    只有一个叶子的子树被整体替换也不会丢别的东西,故排除。
    返回 {"top.sub": ([leaf, ...], sub 的行号)}。
    """
    victims: dict[str, tuple[list[str], int]] = {}
    for tk, tv in zip(d.keys, d.values):
        if not isinstance(tk, ast.Constant) or not isinstance(tv, ast.Dict):
            continue
        for sk, sv in zip(tv.keys, tv.values):
            if not isinstance(sk, ast.Constant) or not isinstance(sv, ast.Dict):
                continue
            leaves = [n.value for n in sv.keys
                      if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            if len(leaves) >= 2:
                victims[f"{tk.value}.{sk.value}"] = (sorted(leaves), sk.lineno)
    return victims


_HAS_FALLBACK = re.compile(r"""\.get\(\s*['"]([\w.]+)['"]\s*,""")
_NO_FALLBACK = re.compile(r"""\.get\(\s*['"]([\w.]+)['"]\s*\)""")


def scan_read_sites(repo: Path, leaf: str) -> tuple[int, int, list[str]]:
    """全仓 .py 里该叶子键名的读取点,分"有兜底 / 无兜底"计数。"""
    try:
        out = subprocess.run(
            ["grep", "-rn", "--include=*.py", "-e", f"'{leaf}'", "-e", f'"{leaf}"', str(repo)],
            capture_output=True, text=True, timeout=180,
        ).stdout
    except Exception:
        return 0, 0, []
    with_fb, without_fb, samples = 0, 0, []
    for line in out.splitlines():
        if leaf in _HAS_FALLBACK.findall(line):
            with_fb += 1
        elif leaf in _NO_FALLBACK.findall(line):
            without_fb += 1
            if len(samples) < 3:
                parts = line.split(":", 2)
                samples.append(parts[0].replace(str(repo) + "/", "") + ":" + parts[1])
    return with_fb, without_fb, samples


def main() -> None:
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")
    cli_tree = ast.parse((repo / "cli.py").read_text(encoding="utf-8"))
    dc_tree = ast.parse((repo / "hermes_cli" / "config_defaults.py").read_text(encoding="utf-8"))

    cli_d, cli_lineno = find_dict(cli_tree, "defaults", inside="load_cli_config")
    dc_d, dc_lineno = find_dict(dc_tree, "DEFAULT_CONFIG")

    flat_cli = flatten(cli_d)
    flat_dc = flatten(dc_d)
    cli_keys = {k for k, *_ in flat_cli}
    dc_keys = {k for k, *_ in flat_dc}

    # ---------------- H-1 ----------------
    cli_only = sorted(cli_keys - dc_keys)
    print(f"# H-1  cli.py:{cli_lineno} `defaults`  vs  config_defaults.py:{dc_lineno} DEFAULT_CONFIG")
    print(f"cli.py defaults 展开键数 : {len(cli_keys)}")
    print(f"DEFAULT_CONFIG 展开键数  : {len(dc_keys)}")
    print(f"CLI 专属键(H-1)        : {len(cli_only)}")
    print("\n## H-1 名单(键 / 默认值 / 定义行)")
    by_key = {k: (v, ln) for k, v, ln, _ in flat_cli}
    for k in cli_only:
        v, ln = by_key[k]
        print(f"  cli.py:{ln}\t{k}\t{v}")

    # ---------------- H-2 ----------------
    victims = nested_victims(cli_d)
    print("\n\n# H-2  一层 update 的受害集合(深度>=3 且兄弟叶子>=2 的子树)")
    print("(用户在这些子树下写任一叶子,同级其余叶子全部丢失)")
    at_risk: list[tuple[str, str, int, int, list[str]]] = []
    total_leaves = 0
    for subtree, (leaves, ln) in sorted(victims.items()):
        print(f"\n### {subtree}   cli.py:{ln}   ({len(leaves)} 个叶子)")
        for leaf in leaves:
            total_leaves += 1
            with_fb, without_fb, samples = scan_read_sites(repo, leaf)
            flag = "  <== 无兜底!" if (without_fb and not with_fb) else ""
            print(f"    {leaf:<30} 读取点 有兜底={with_fb:<4} 无兜底={without_fb:<4}{flag}")
            if without_fb and not with_fb:
                at_risk.append((subtree, leaf, with_fb, without_fb, samples))

    print(f"\n受害子树 {len(victims)} 个,涉及叶子 {total_leaves} 个;"
          f"其中**全部读取点都无兜底**的 {len(at_risk)} 个")
    print("\n## H-2 结论候选(全部读取点都无兜底 —— 这些才是会真出事的)")
    for subtree, leaf, _wf, wo, samples in sorted(at_risk, key=lambda r: -r[3]):
        print(f"  {subtree}.{leaf}: 无兜底读取点={wo} 例:{'; '.join(samples)}")


if __name__ == "__main__":
    main()
