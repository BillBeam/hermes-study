#!/usr/bin/env python3
"""R11C 片 D:逐条人工确证过的锚点改正(机械判据够不到的那些)。

每一条都在底稿 §3.3 里写明了「原文是什么、真实位置是什么、凭什么确定」。
脚本只负责**精确替换 + 出现次数断言**,不做任何判断 —— 判断在底稿里。

  python3 data/r11c/d-anchor-resolution-manual-fixes.py [--apply]
"""
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[2]
APPLY = "--apply" in sys.argv

# (文件, 原串, 新串, 期望出现次数)
FIXES = [
    # --- 真写错:路径多了一段 ---
    # run_agent.py 在基线**仓库根**,不在 agent/ 下。:3710 = inject_new_comments_from_env(self)
    ("notes/r7c-90-doc-conflict-rulings.md",
     "agent/run_agent.py:3710", "run_agent.py:3710", 2),

    # --- 真写错:文档名对不上基线里的实际文件名 ---
    # :802 = HERMES_STREAM_READ_TIMEOUT(120)、:803 = HERMES_STREAM_STALE_TIMEOUT(180),
    # 正是这两条笔记断言「与文档一致」的那两个默认值。
    ("notes/r2-03-streaming.md",
     "env-variables.md:802-803",
     "website/docs/reference/environment-variables.md:802-803", 1),
    ("notes/r2-23-classify-retry-fallback-cache.md",
     "env-variables.md:802-803",
     "website/docs/reference/environment-variables.md:802-803", 1),
    # 基线里这份文档叫 context-compression-and-caching.md;:396 = "### Strategy: system_and_3"
    ("notes/r2-90-doc-conflict-rulings.md",
     "compression-caching.md:396",
     "website/docs/developer-guide/context-compression-and-caching.md:396", 1),
    # 本仓库自引,同小节其余锚点都写了 notes/ 前缀,只有这一处漏了
    ("notes/r8a-90-doc-conflict-rulings.md",
     "raw-config-b.md:1227", "notes/r8a-raw-config-b.md:1227", 1),

    # --- 裸名碰巧解析到仓库根上另一个真文件(行号越界暴露) ---
    # 根 README.md 只有 264 行;honcho README :334 = "### Hardcoded Limits"、
    # :339 = "| Peer card fetch tokens | 200 |",正是笔记引的那句
    ("notes/r6-90-doc-conflict-rulings.md",
     "`README.md:334-339`", "`plugins/memory/honcho/README.md:334-339`", 1),
    # 根 setup.py 只有 74 行;hermes_cli/setup.py :3535 = value = prompt(...)、
    # :3558 = tools = var.get("tools", []),与表格两行讲的 key 一致
    ("notes/r8a-raw-defaults-b.md", "`setup.py:3535`", "`hermes_cli/setup.py:3535`", 1),
    ("notes/r8a-raw-defaults-b.md", "`setup.py:3558`", "`hermes_cli/setup.py:3558`", 1),

    # --- 作者有意省略中段(`...`),补回全路径 ---
    ("notes/r7b-10-base-adapter-contract.md",
     "website/i18n/zh-Hans/.../gateway-internals.md:86",
     "website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/developer-guide/"
     "gateway-internals.md:86", 1),
    ("notes/r7c-90-doc-conflict-rulings.md",
     "website/i18n/.../webhooks.md:452-460",
     "website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/user-guide/messaging/"
     "webhooks.md:452-460", 1),
    ("notes/r7c-raw-webhook-signing-docgap.md",
     "website/i18n/zh-Hans/.../messaging/webhooks.md:452-460",
     "website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/user-guide/messaging/"
     "webhooks.md:452-460", 1),
    ("notes/r7c-raw-slash-b.md",
     "tests/gateway/test_48031_...py:77-87",
     "tests/gateway/test_48031_model_switch_after_auto_reset.py:77-87", 1),
    ("notes/r9b-raw-present.md",
     "website/i18n/zh-Hans/.../configuration.md:1255",
     "website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/user-guide/"
     "configuration.md:1255", 1),
    ("notes/r9d-raw-lsp.md",
     "website/docs/.../lsp.md:284", "website/docs/user-guide/features/lsp.md:284", 1),
]


def main():
    bad = 0
    for rel, old, new, want in FIXES:
        p = STUDY / rel
        s = p.read_text(encoding="utf-8")
        got = s.count(old)
        mark = "OK " if got == want else "!! "
        if got != want:
            bad += 1
        print(f"{mark}{rel}  {old!r} x{got} (期望 {want})")
        if got == want and APPLY:
            p.write_text(s.replace(old, new), encoding="utf-8")
    print(f"\n{'已改写' if APPLY else '干跑'} {len(FIXES) - bad} 条,出现次数不符 {bad} 条")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
