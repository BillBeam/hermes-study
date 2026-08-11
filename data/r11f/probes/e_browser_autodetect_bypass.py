#!/usr/bin/env python3
"""R11F 片 E 探针:browser 自动探测分支绕过注册表。

`agent/browser_registry.py` 用 33 行 docstring 写清了三条选择规则,并把它们实现在
`_resolve()` 里;`_LEGACY_PREFERENCE = ("browser-use", "browserbase")` 是那条
「传统偏好顺序」。而真正的派发器 `tools/browser_tool._get_cloud_provider()`
在**自动探测分支**里直接 `BrowserUseProvider()` / `BrowserbaseProvider()` 新建实例,
既不读注册表、也不碰 `_LEGACY_PREFERENCE`。

本探针在**同一份注册表状态**下问两条路径:注册一个名叫 `browser-use`、
`is_available()` 恒 True 的 provider(模拟用户装在 ~/.hermes/plugins/browser/ 下、
按 `register_provider` 文档化的「同名覆盖」语义顶掉内建那一个),`browser.cloud_provider`
不设。若 `_resolve(None)` 拿到它而 `_get_cloud_provider()` 拿不到,就证明自动探测
分支绕过了注册表。

不需要任何真实凭据;不发网络请求;HERMES_HOME 指向临时目录。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))


def main() -> int:
    os.environ["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
    os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="r11f-e-br-")
    for var in ("BROWSER_USE_API_KEY", "BROWSERBASE_API_KEY",
                "BROWSERBASE_PROJECT_ID", "FIRECRAWL_API_KEY"):
        os.environ.pop(var, None)
    sys.path.insert(0, str(BASELINE))

    from agent import browser_registry
    from agent.browser_provider import BrowserProvider

    class ThirdPartyBrowserUse(BrowserProvider):
        """A stand-in for a user-installed override of the `browser-use` name."""

        @property
        def name(self) -> str:
            return "browser-use"

        def is_available(self) -> bool:
            return True

        def create_session(self, task_id):
            return {"session_name": "probe", "bb_session_id": "probe",
                    "cdp_url": "ws://probe", "features": {}}

        def close_session(self, session_id):
            return True

        def emergency_cleanup(self, session_id):
            return None

    browser_registry._reset_for_tests()
    browser_registry.register_provider(ThirdPartyBrowserUse())

    resolved = browser_registry._resolve(None)
    print(f"registry._resolve(None) -> {type(resolved).__name__ if resolved else None}")

    import tools.browser_tool as bt

    bt._cached_cloud_provider = None
    bt._cloud_provider_resolved = False
    dispatched = bt._get_cloud_provider()
    print(f"browser_tool._get_cloud_provider() -> "
          f"{type(dispatched).__name__ if dispatched else None}")
    print(f"registered under 'browser-use': "
          f"{type(browser_registry.get_provider('browser-use')).__name__}")
    print(f"same object ? {resolved is dispatched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
