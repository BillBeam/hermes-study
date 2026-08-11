#!/usr/bin/env python3
"""R11F 片 E 探针:provider 注册面的**运行期**枚举(不是数目录)。

目录数 ≠ provider 数:`plugins/image_gen/openrouter/` 一个目录注册**两个** provider
(`openrouter` 与 `nous`)。所以注册面必须让插件真的跑一遍 `register(ctx)` 再问注册表,
而不是数 `plugins/<域>/*/` 的子目录。

做法:先断言惰性安装封印生效(`tools.lazy_deps._allow_lazy_installs() is False`),
再 `discover_plugins()`,然后列出三个注册表里的每一个 provider:name / display_name /
类 / 类所在文件。HERMES_HOME 指向临时目录,不碰用户配置,不发网络请求。
"""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
from pathlib import Path

BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))


def main() -> int:
    os.environ["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
    os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="r11f-e-reg-")
    sys.path.insert(0, str(BASELINE))

    from tools.lazy_deps import _allow_lazy_installs

    print(f"lazy-install seal: _allow_lazy_installs() = {_allow_lazy_installs()}")
    if _allow_lazy_installs():
        print("REFUSING to discover plugins while lazy installs are enabled")
        return 2

    from hermes_cli.plugins import discover_plugins

    discover_plugins()

    from agent import browser_registry, image_gen_registry, video_gen_registry

    total = 0
    for label, mod in (
        ("image_gen", image_gen_registry),
        ("video_gen", video_gen_registry),
        ("browser", browser_registry),
    ):
        providers = mod.list_providers()
        print(f"### {label}: {len(providers)} registered")
        for p in providers:
            src = inspect.getsourcefile(type(p)) or "?"
            rel = os.path.relpath(src, BASELINE)
            print(f"    {p.name:<14} display={p.display_name!r:<26} "
                  f"class={type(p).__name__} @ {rel}")
        total += len(providers)
    print(f"TOTAL providers registered across the three registries: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
