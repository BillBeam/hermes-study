#!/usr/bin/env python3
"""R11F 片 F 探针:用宿主自己的扫描器枚举 plugins/ 顶层的清单发现结果。

不 import 任何插件模块 —— 只调用 PluginManager._scan_directory(),它读 plugin.yaml
并做 __init__.py 文本启发式。输出 key / kind / source,用来证明:

  * plugins/web/<name>  -> key="web/<name>", kind="backend"(→ bundled backend 自动加载)
  * plugins/cron_providers/chronos -> key="cron_providers/chronos", kind="standalone"
    (它既不在 skip_names 里,清单也没写 kind,启发式又只认 memory / model-provider)

用法:HERMES_DISABLE_LAZY_INSTALLS=1 python3 f_scanner_kinds.py <baseline-root>
"""
import os
import sys
from pathlib import Path

BASE = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent").resolve()
sys.path.insert(0, str(BASE))
os.environ["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
os.environ.setdefault("HERMES_HOME", "/nonexistent-hermes-home-r11f")

from hermes_cli.plugins import PluginManager, _VALID_PLUGIN_KINDS  # noqa: E402

mgr = PluginManager()
rows = mgr._scan_directory(
    BASE / "plugins",
    source="bundled",
    skip_names={"memory", "context_engine", "platforms", "model-providers"},
)
print("VALID_KINDS=" + ",".join(sorted(_VALID_PLUGIN_KINDS)))
print("top-level manifests found: %d" % len(rows))
for m in sorted(rows, key=lambda x: x.key):
    print("  key=%-28s kind=%-13s name=%s" % (m.key, m.kind, m.name))
