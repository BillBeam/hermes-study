#!/usr/bin/env python3
"""R11F 片 F 探针:memory 插件的 plugin.yaml 是一个**可执行面**(结清 H-R10G-b)。

结论要点(逐条由本探针实测):
  1. `external_dependencies[].check` 被 shlex.split() 后 subprocess.run(argv) 执行;
  2. 触发它的不是安装动作,而是**读状态**——_memory_provider_setup_info() 被
     GET /api/memory 与 GET /api/dashboard/plugins 的公共路径调到;
  3. 该插件**无需出现在 plugins.enabled 里**:memory 的发现走 plugins/memory/
     自己的 _iter_provider_dirs(),它只看目录里 __init__.py 有没有 MemoryProvider 字样。

探针在临时 HERMES_HOME 下造一个假 provider,check 命令写一个标记文件,
然后只调用 _memory_provider_setup_info() —— 不碰基线,不装任何包,收尾自清理。

用法:HERMES_DISABLE_LAZY_INSTALLS=1 python3 f_memory_manifest_exec.py <baseline-root>
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent").resolve()
tmp = Path(tempfile.mkdtemp(prefix="r11f-f-memexec-"))
try:
    home = tmp / "hermes-home"
    (home / "plugins" / "probeprov").mkdir(parents=True)
    marker = tmp / "MANIFEST_COMMAND_RAN"
    # 目录被认作 memory provider 的唯一条件:__init__.py 前 8192 字节里
    # 出现 "register_memory_provider" 或 "MemoryProvider"。
    (home / "plugins" / "probeprov" / "__init__.py").write_text(
        "# MemoryProvider\n", encoding="utf-8")
    (home / "plugins" / "probeprov" / "plugin.yaml").write_text(
        "name: probeprov\n"
        "version: 0.0.0\n"
        "description: probe\n"
        "external_dependencies:\n"
        "  - name: probe\n"
        "    check: \"/bin/sh -c 'touch %s'\"\n"
        "    install: \"echo never-run-by-this-probe\"\n" % marker,
        encoding="utf-8")

    os.environ["HERMES_HOME"] = str(home)
    os.environ["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
    sys.path.insert(0, str(BASE))

    from plugins.memory import _iter_provider_dirs
    names = [n for n, _ in _iter_provider_dirs()]
    print("discovered memory providers = %d" % len(names))
    print("probeprov discovered without any plugins.enabled entry = %s"
          % ("probeprov" in names))

    from hermes_cli.web_server import _memory_provider_setup_info
    info = _memory_provider_setup_info("probeprov")
    print("marker file created by manifest `check` command = %s" % marker.exists())
    dep = info["external_dependencies"][0]
    # 打印时把随机临时目录名换成占位符,重跑输出才逐字一致。
    print("setup_info dep name=%s check=%s install=%s"
          % (dep["name"], dep["check"].replace(str(marker), "<TMP>/MARKER"),
             dep["install"]))
    print("required_env=%r pip_dependencies=%r"
          % (info["required_env"], info["pip_dependencies"]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)
