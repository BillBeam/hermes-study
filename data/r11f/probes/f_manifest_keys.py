#!/usr/bin/env python3
"""R11F 片 F 探针:片内 18 份 plugin.yaml 的顶层键集逐份列全,并标注哪些键
真的被 hermes_cli/plugins.py 的 _parse_manifest 读走。

_parse_manifest 只 data.get() 七个键;其余键**没有 schema 校验、也没有告警**,
静默忽略。本探针把"清单里写了什么"与"加载器读了什么"并排打出来。

用法:python3 f_manifest_keys.py <baseline-root>
"""
import sys
from pathlib import Path

import yaml

BASE = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent").resolve()

# hermes_cli/plugins.py:1657-1669 —— _parse_manifest 返回 PluginManifest 时
# 实际 data.get() 的键(name/version/description/author/requires_env/
# provides_tools/provides_hooks),外加 kind(:1605)。
PARSED = {"name", "version", "description", "author",
          "requires_env", "provides_tools", "provides_hooks", "kind"}

SLICE = ["cron_providers/chronos", "disk-cleanup", "security-guidance",
         "teams_pipeline"]
SLICE += ["memory/" + n for n in ("byterover", "hindsight", "holographic",
                                  "honcho", "mem0", "openviking", "retaindb",
                                  "supermemory")]
SLICE += ["web/" + n for n in ("brave_free", "ddgs", "exa", "firecrawl",
                               "parallel", "searxng", "tavily", "xai")]

all_keys = {}
print("%-28s %s" % ("manifest dir", "top-level keys (* = 加载器不读)"))
for rel in SLICE:
    p = BASE / "plugins" / rel / "plugin.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    marked = []
    for k in data:
        all_keys[k] = all_keys.get(k, 0) + 1
        marked.append(k if k in PARSED else k + "*")
    print("%-28s %s" % (rel, " ".join(marked)))

print()
print("片内不同顶层键 %d 个,按出现次数:" % len(all_keys))
for k, n in sorted(all_keys.items(), key=lambda kv: (-kv[1], kv[0])):
    print("  %-24s %2d  %s" % (k, n, "读" if k in PARSED else "不读"))
