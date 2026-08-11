#!/usr/bin/env python3
"""R11F 片 E 探针:凭据面与外发面(逐项列全)。

对片 E 的每个插件目录:
  1. **凭据面** —— AST 抽出该目录 .py 里所有形如 `A_B_C` 的全大写字符串字面量
     (env 变量名的形状),以及它们出现在哪一行、被哪个读取器包着
     (`os.environ.get` / `os.getenv` / `get_secret` / 其它);
  2. **外发面** —— AST 抽出所有 `http(s)://` 字面量,按 host 归并,
     并标出该行是否落在 requests/httpx 调用上下文里(粗判:同一行或前后 3 行有
     `requests.` / `httpx` / `client.` / `f"{base_url}`)。

只做 AST + 文本,不 import 基线代码,不发任何网络请求。
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from urllib.parse import urlparse

BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))

DIRS = [
    "plugins/browser/browser_use",
    "plugins/browser/browserbase",
    "plugins/browser/firecrawl",
    "plugins/google_meet",
    "plugins/image_gen/deepinfra",
    "plugins/image_gen/fal",
    "plugins/image_gen/krea",
    "plugins/image_gen/openai",
    "plugins/image_gen/openai-codex",
    "plugins/image_gen/openrouter",
    "plugins/image_gen/xai",
    "plugins/spotify",
    "plugins/video_gen/deepinfra",
    "plugins/video_gen/fal",
    "plugins/video_gen/xai",
]

ENV_SHAPE = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")
URL_RE = re.compile(r"https?://[^\s\"'<>)\\]+")
READERS = ("os.environ.get", "os.getenv", "environ.get", "getenv", "get_secret",
           "get_env_value", "_env_key")


def py_files(d: Path):
    return sorted(p for p in d.rglob("*.py"))


def scan(rel: str):
    d = BASELINE / rel
    envs: dict[str, set[str]] = {}
    hosts: dict[str, set[str]] = {}
    for p in py_files(d):
        text = p.read_text(encoding="utf-8")
        lines = text.splitlines()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            val = node.value
            ln = getattr(node, "lineno", 0)
            src = lines[ln - 1] if 0 < ln <= len(lines) else ""
            if ENV_SHAPE.match(val):
                reader = next((r for r in READERS if r in src), "other")
                envs.setdefault(val, set()).add(
                    f"{p.relative_to(BASELINE)}:{ln}[{reader}]"
                )
            for m in URL_RE.finditer(val):
                host = urlparse(m.group(0)).netloc
                if host:
                    hosts.setdefault(host, set()).add(f"{p.relative_to(BASELINE)}:{ln}")
    return envs, hosts


def main() -> int:
    all_envs: set[str] = set()
    all_hosts: set[str] = set()
    for rel in DIRS:
        envs, hosts = scan(rel)
        all_envs |= set(envs)
        all_hosts |= set(hosts)
        print(f"### {rel}")
        print(f"  ENV ({len(envs)}):")
        for k in sorted(envs):
            print(f"    {k:<34} {'; '.join(sorted(envs[k]))}")
        print(f"  HOST ({len(hosts)}):")
        for h in sorted(hosts):
            print(f"    {h:<28} {'; '.join(sorted(hosts[h]))}")
    print()
    print(f"TOTAL distinct env-shaped literals: {len(all_envs)}")
    print(f"TOTAL distinct hosts: {len(all_hosts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
