#!/usr/bin/env python3
"""R11F 片 F 探针:cron_providers/chronos 走通用插件路径会怎样。

chronos 的清单没有 kind:,启发式只认 memory / model-provider,于是它被判成
kind="standalone" —— 也就是「用户在 plugins.enabled 里打开就加载」的那一类。
可它的 register() 调的是 ctx.register_cron_scheduler(),而真正的 PluginContext
上没有这个方法(只有 plugins/cron_providers/__init__.py 里那个 _ProviderCollector 假 ctx 有)。

本探针直接跑宿主的 _load_plugin(),打印它记下的 error。
用法:HERMES_DISABLE_LAZY_INSTALLS=1 python3 f_chronos_ctx_gap.py <baseline-root>
"""
import os
import sys
from pathlib import Path

BASE = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent").resolve()
sys.path.insert(0, str(BASE))
os.environ["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
os.environ.setdefault("HERMES_HOME", "/nonexistent-hermes-home-r11f")

from hermes_cli.plugins import PluginContext, PluginManager  # noqa: E402

mgr = PluginManager()
rows = mgr._scan_directory(
    BASE / "plugins",
    source="bundled",
    skip_names={"memory", "context_engine", "platforms", "model-providers"},
)
chronos = next(m for m in rows if m.key == "cron_providers/chronos")
ctx = PluginContext(chronos, mgr)

reg = sorted(n for n in dir(ctx) if n.startswith("register_"))
print("PluginContext register_* methods: %d" % len(reg))
for n in reg:
    print("  " + n)
print("hasattr(ctx, 'register_cron_scheduler') = %s" % hasattr(ctx, "register_cron_scheduler"))

mgr._load_plugin(chronos)
loaded = mgr._plugins["cron_providers/chronos"]
print("after _load_plugin: enabled=%s error=%r" % (loaded.enabled, loaded.error))
