#!/usr/bin/env python3
"""R11F 片 F 探针:全仓 plugin.yaml 的 `hooks:` 键普查。

要点:hermes_cli/plugins.py:1664 读的是 `provides_hooks`,而全仓 0 份清单写它;
写的都是 `hooks:`。于是这个键**从来没有被任何加载器读过、更没有被校验过**,
两套不同词汇表(插件 VALID_HOOKS / MemoryProvider ABC 生命周期方法)
在同一个键名下并存而无人发现。

用法:python3 f_hooks_key_census.py <baseline-root>
"""
import sys
from pathlib import Path

import yaml

BASE = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent").resolve()
sys.path.insert(0, str(BASE))
from hermes_cli.plugins import VALID_HOOKS  # noqa: E402

rows = []
n_provides_hooks = 0
for p in sorted(BASE.glob("plugins/**/plugin.yaml")):
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if "provides_hooks" in data:
        n_provides_hooks += 1
    hooks = data.get("hooks")
    if hooks:
        rows.append((str(p.relative_to(BASE)), list(hooks)))

print("manifests declaring `hooks:`        = %d" % len(rows))
print("manifests declaring `provides_hooks:` = %d   <- the key the parser reads"
      % n_provides_hooks)
print()
bad = []
for rel, hooks in rows:
    marks = []
    for h in hooks:
        ok = h in VALID_HOOKS
        marks.append(h if ok else h + " [NOT IN VALID_HOOKS]")
        if not ok:
            bad.append((rel, h))
    print("  %-46s %s" % (rel, ", ".join(marks)))
print()
print("hook names not in VALID_HOOKS: %d" % len(bad))
for rel, h in bad:
    print("  %s -> %s" % (rel, h))
