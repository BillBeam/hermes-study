#!/usr/bin/env python3
"""R11F 片 A —— `config.yaml` → 环境变量桥(`apply_yaml_config_fn`)的机械枚举(判据 2)。

三家适配器都把运行期配置读成 `os.getenv("<PLATFORM>_*")`,而 `plugin.yaml` 只声明
4~5 条 env(设置向导的输入面)。其余的入口是 **`_apply_yaml_config`**:
它把 `config.yaml` 的 `<platform>:` 段翻译成 `os.environ[...]` 写入。

本探针在 `_apply_yaml_config` 函数体内 AST 扫两件事:
  写:`os.environ["X"] = ...`        → 该 env 可由 config.yaml 设定
  读:`<platform>_cfg["k"] / .get("k")` 与 `platform_extra_cfg.get("k")` → YAML 键名

再与适配器实际读取的 env 全集(a_manifest_and_env.py 的窄口径)对齐,得出
**env-only**(既不在 manifest、也不在 YAML 桥里)的那一批。

用法: python3 a_yaml_env_bridge.py [基线路径] [--mode summary|bridge|envonly]
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from a_manifest_and_env import env_names_in, load_manifest  # noqa: E402

PLATFORMS = [
    ("discord", "DISCORD_"),
    ("telegram", "TELEGRAM_"),
    ("slack", "SLACK_"),
]
FN = "_apply_yaml_config"


def bridge_of(root: Path, plat: str, prefix: str) -> tuple[int, dict, dict]:
    rel = f"plugins/platforms/{plat}/adapter.py"
    tree = ast.parse((root / rel).read_text(encoding="utf-8"))
    fn = None
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == FN:
            fn = n
    if fn is None:
        raise SystemExit(f"{FN} not found in {rel}")

    writes: dict[str, int] = {}
    reads: dict[str, int] = {}
    for n in ast.walk(fn):
        # os.environ["X"] = ...
        if isinstance(n, ast.Assign):
            for tgt in n.targets:
                if isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Attribute) \
                        and tgt.value.attr == "environ":
                    k = tgt.slice
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        writes.setdefault(k.value, n.lineno)
        # <plat>_cfg["k"] / .get("k") / platform_extra_cfg.get("k")
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) \
                and n.value.id.endswith("_cfg"):
            k = n.slice
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                reads.setdefault(k.value, n.lineno)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "get" and isinstance(n.func.value, ast.Name) \
                and n.func.value.id.endswith("_cfg") and n.args:
            k = n.args[0]
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                reads.setdefault(k.value, n.lineno)
        # "k" in <plat>_cfg
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], ast.In):
            if isinstance(n.left, ast.Constant) and isinstance(n.left.value, str) \
                    and isinstance(n.comparators[0], ast.Name) \
                    and n.comparators[0].id.endswith("_cfg"):
                reads.setdefault(n.left.value, n.lineno)
    return fn.lineno, writes, reads


def adapter_env(root: Path, plat: str, prefix: str) -> dict:
    out: dict[str, tuple[str, int]] = {}
    for py in sorted((root / f"plugins/platforms/{plat}").rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        rel = str(py.relative_to(root))
        for name, ln in env_names_in(py.read_text(encoding="utf-8"), prefix,
                                     narrow=True).items():
            out.setdefault(name, (rel, ln))
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    root = Path(args[0]) if args else Path("/home/user/hermes-agent")
    mode = "summary"
    for f in flags:
        if f.startswith("--mode"):
            mode = f.split("=", 1)[1] if "=" in f else "summary"

    for plat, prefix in PLATFORMS:
        ln, writes, reads = bridge_of(root, plat, prefix)
        man = load_manifest(root / f"plugins/platforms/{plat}/plugin.yaml")
        declared = {e["name"] for e in (man.get("requires_env") or [])} | \
                   {e["name"] for e in (man.get("optional_env") or [])}
        read_env = adapter_env(root, plat, prefix)
        env_only = sorted(set(read_env) - declared - set(writes))
        rel = f"plugins/platforms/{plat}/adapter.py"

        if mode == "bridge":
            print(f"== {rel}:{ln} {FN}  yaml_keys={len(reads)} env_writes={len(writes)}")
            for k, kl in sorted(reads.items()):
                print(f"   yaml\t{k}\t{rel}:{kl}")
            for k, kl in sorted(writes.items()):
                print(f"   env \t{k}\t{rel}:{kl}")
            continue
        if mode == "envonly":
            print(f"== {plat}: env_only={len(env_only)}")
            for k in env_only:
                r, l = read_env[k]
                print(f"   {k}\t{r}:{l}")
            continue

        print(f"{plat:9s} manifest_env={len(declared)} yaml_bridge_env={len(writes)} "
              f"yaml_keys={len(reads)} adapter_reads={len(read_env)} env_only={len(env_only)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
