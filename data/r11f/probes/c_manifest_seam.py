#!/usr/bin/env python3
"""R11F 片 C:14 份平台 plugin.yaml 的清单面机械枚举。

三个面:
  1. 顶层键面   —— 每份 manifest 声明了哪些顶层键(逐份列全,不是列全仓那 15 个)
  2. env 面     —— requires_env / optional_env 每条变量名 + 每条用了哪些子字段
  3. 消费面     —— 顶层键被哪个消费者读:
       plugins   = hermes_cli/plugins.py::_parse_manifest(8 键)
       config    = hermes_cli/config.py::_inject_platform_plugin_env_vars(4 键)
       none      = 两个消费者都不读

用法(cwd 任意;基线路径可用 HERMES_BASELINE 覆盖):
    python3 data/r11f/probes/c_manifest_seam.py --keys
    python3 data/r11f/probes/c_manifest_seam.py --keymatrix
    python3 data/r11f/probes/c_manifest_seam.py --env
    python3 data/r11f/probes/c_manifest_seam.py --envfields
    python3 data/r11f/probes/c_manifest_seam.py --counts
    python3 data/r11f/probes/c_manifest_seam.py --secretcheck
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))

PLATFORMS = [
    "photon", "a2a", "whatsapp", "line", "buzz", "teams", "simplex",
    "mattermost", "email", "irc", "raft", "ntfy", "homeassistant", "sms",
]

# hermes_cli/plugins.py::_parse_manifest 实际 data.get(...) 的键
PLUGINS_READS = {
    "name", "kind", "version", "description", "author",
    "requires_env", "provides_tools", "provides_hooks",
}
# hermes_cli/config.py::_inject_platform_plugin_env_vars 实际 manifest.get(...) 的键
CONFIG_READS = {"label", "name", "requires_env", "optional_env"}

# config.py 的 password 启发式后缀
SECRET_SUFFIXES = ("_TOKEN", "_SECRET", "_KEY", "_PASSWORD", "_JSON")


def load(p: str) -> dict:
    path = BASELINE / "plugins/platforms" / p / "plugin.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def consumers(key: str) -> str:
    tags = []
    if key in PLUGINS_READS:
        tags.append("plugins")
    if key in CONFIG_READS:
        tags.append("config")
    return "+".join(tags) if tags else "NONE"


def env_entries(m: dict, block: str):
    """yield (name, meta_dict) —— 条目可以是裸字符串或 dict。"""
    for entry in (m.get(block) or []):
        if isinstance(entry, str):
            yield entry, {}
        elif isinstance(entry, dict) and entry.get("name"):
            yield entry["name"], entry


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--keys"
    mans = {p: load(p) for p in PLATFORMS}

    if mode == "--keys":
        for p in PLATFORMS:
            keys = list(mans[p].keys())
            print(f"{p:<14} {len(keys):>2}  {' '.join(keys)}")
        return

    if mode == "--keymatrix":
        allkeys = sorted({k for m in mans.values() for k in m})
        hdr = "".join(f"{p[:4]:>5}" for p in PLATFORMS)
        print(f"{'key':<22}{'reader':>9}  {'n':>2}{hdr}")
        for k in allkeys:
            cells = "".join(f"{('Y' if k in mans[p] else '.'):>5}" for p in PLATFORMS)
            n = sum(1 for p in PLATFORMS if k in mans[p])
            print(f"{k:<22}{consumers(k):>9}  {n:>2}{cells}")
        return

    if mode == "--env":
        for p in PLATFORMS:
            req = [n for n, _ in env_entries(mans[p], "requires_env")]
            opt = [n for n, _ in env_entries(mans[p], "optional_env")]
            print(f"## {p}  requires_env={len(req)} optional_env={len(opt)}")
            for n in req:
                print(f"   R  {n}")
            for n in opt:
                print(f"   O  {n}")
        return

    if mode == "--envfields":
        fields: dict[str, int] = {}
        for p in PLATFORMS:
            for block in ("requires_env", "optional_env"):
                for _, meta in env_entries(mans[p], block):
                    for f in meta:
                        fields[f] = fields.get(f, 0) + 1
        for f, n in sorted(fields.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"{n:>4}  {f}")
        return

    if mode == "--secretcheck":
        # config.py 口径复算:哪些 env 会被当成密码字段
        for p in PLATFORMS:
            for block in ("requires_env", "optional_env"):
                for n, meta in env_entries(mans[p], block):
                    is_secret = bool(meta.get("password") or meta.get("secret"))
                    if not is_secret and not meta.get("password") is False:
                        is_secret = any(n.upper().endswith(s) for s in SECRET_SUFFIXES)
                    looks_secret = any(n.upper().endswith(s) for s in SECRET_SUFFIXES)
                    if looks_secret and not is_secret:
                        print(f"PLAINTEXT {p:<14} {block:<13} {n}")
        return

    if mode == "--counts":
        allkeys = sorted({k for m in mans.values() for k in m})
        req = sum(len(list(env_entries(mans[p], "requires_env"))) for p in PLATFORMS)
        opt = sum(len(list(env_entries(mans[p], "optional_env"))) for p in PLATFORMS)
        names = {n for p in PLATFORMS for b in ("requires_env", "optional_env")
                 for n, _ in env_entries(mans[p], b)}
        print(f"manifests={len(PLATFORMS)}")
        print(f"distinct_top_keys={len(allkeys)}")
        print(f"unread_top_keys={len([k for k in allkeys if consumers(k) == 'NONE'])}")
        print(f"requires_env_entries={req}")
        print(f"optional_env_entries={opt}")
        print(f"distinct_env_names={len(names)}")
        return

    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
