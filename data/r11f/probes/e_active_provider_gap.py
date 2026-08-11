#!/usr/bin/env python3
"""R11F 片 E 探针:image_gen 的「active provider」在两条路径上不是同一个东西。

判据
----
`agent/image_gen_registry.py` 的模块 docstring 声称本注册表被 ``image_generate``
工具消费、且 ``image_gen.provider`` 未设时由 ``get_active_provider()`` 兜底
(单 provider → fal → None)。本探针在同一进程里对**同一份注册表状态**分别问两条路径:

  A. ``agent.image_gen_registry.get_active_provider()``
  B. ``tools.image_generation_tool._dispatch_to_plugin_provider(...)``

配置里 ``image_gen.provider`` 不设。若两者给出不同答案,docstring 的
"consumed by the image_generate tool to dispatch each call to the active backend"
就与代码矛盾。

对照组:``video_gen`` 的同一对路径 —— ``agent.video_gen_registry.get_active_provider()``
与 ``tools.video_generation_tool`` 的调用点。

只读、离线、不发任何网络请求;HERMES_HOME 指向临时目录,不碰用户配置。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))


def main() -> int:
    os.environ["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
    tmp = tempfile.mkdtemp(prefix="r11f-e-")
    os.environ["HERMES_HOME"] = tmp
    # 明确清空可能让 provider 自称可用的凭据,读数才可复现。
    for var in (
        "FAL_KEY", "OPENAI_API_KEY", "XAI_API_KEY", "DEEPINFRA_API_KEY",
        "KREA_API_KEY", "OPENROUTER_API_KEY",
    ):
        os.environ.pop(var, None)
    sys.path.insert(0, str(BASELINE))

    from agent import image_gen_registry, video_gen_registry
    from agent.image_gen_provider import ImageGenProvider, success_response
    from agent.video_gen_provider import VideoGenProvider

    class SoloImage(ImageGenProvider):
        @property
        def name(self) -> str:
            return "probe-solo-image"

        def is_available(self) -> bool:
            return True

        def generate(self, prompt, aspect_ratio="landscape", **kwargs):
            return success_response(
                image="probe://image", model="m", prompt=prompt,
                aspect_ratio=aspect_ratio, provider=self.name,
            )

    class SoloVideo(VideoGenProvider):
        @property
        def name(self) -> str:
            return "probe-solo-video"

        def is_available(self) -> bool:
            return True

        def generate(self, prompt, **kwargs):
            return {"success": True, "provider": self.name}

    image_gen_registry._reset_for_tests()
    video_gen_registry._reset_for_tests()
    image_gen_registry.register_provider(SoloImage())
    video_gen_registry.register_provider(SoloVideo())

    out = {}

    # --- A. 注册表自己的 active 解析 --------------------------------------
    act_img = image_gen_registry.get_active_provider()
    out["image.registry.get_active_provider"] = act_img.name if act_img else None
    act_vid = video_gen_registry.get_active_provider()
    out["video.registry.get_active_provider"] = act_vid.name if act_vid else None

    # --- B. 工具侧的实际派发 -----------------------------------------------
    import tools.image_generation_tool as igt

    dispatched = igt._dispatch_to_plugin_provider("probe prompt", "square")
    if dispatched is None:
        out["image.tool.dispatch"] = None  # None = 落回内建 FAL 路径
    else:
        out["image.tool.dispatch"] = json.loads(dispatched).get("provider")

    import tools.video_generation_tool as vgt

    src = (BASELINE / "tools" / "video_generation_tool.py").read_text().splitlines()
    out["video.tool.calls_get_active_provider"] = any(
        "get_active_provider()" in line for line in src
    )
    src_img = (BASELINE / "tools" / "image_generation_tool.py").read_text().splitlines()
    out["image.tool.calls_get_active_provider"] = any(
        "get_active_provider()" in line for line in src_img
    )
    out["_vgt_module_loaded"] = vgt.__name__

    for key in (
        "image.registry.get_active_provider",
        "image.tool.dispatch",
        "image.tool.calls_get_active_provider",
        "video.registry.get_active_provider",
        "video.tool.calls_get_active_provider",
    ):
        print(f"{key} = {out[key]!r}")

    agree_img = (out["image.registry.get_active_provider"] == out["image.tool.dispatch"])
    print(f"image: registry-active == tool-dispatch ? {agree_img}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
