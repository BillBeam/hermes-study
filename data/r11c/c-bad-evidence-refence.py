#!/usr/bin/env python3
"""R11C 片 C:把「原理上跑不出原值」的 ```verify 块改标 ```text,并在块前插入声明。

为什么这一类不是「修好它」:块里的命令要 `apps/desktop/node_modules`(vitest / eslint)
或一个装了 typescript 的 checkout 提供 NODE_PATH。基线 `/home/user/hermes-agent` 是**只读
git checkout,没有 node_modules**;补它只能在基线里 `npm ci`,那会弄脏全项目每一条
`路径:行号 @ 863e313` 所依赖的引用基准(CLAUDE.md 边界第一条)。R10B 当时跑在基线之外
一份**会话专属副本**上,该目录已随会话消失。派工书片 C 对这种情形的规定是
「改成 ```text 声明它不是可重跑命令,并在正文写明为什么」,**而不是伪造一个看起来合理的输出**。

处置只改围栏与插入声明,**块正文一个字符都不动** —— 逐字匹配,匹配不到就报错退出,
不做模糊替换,也绝不删除任何证据。

    python3 data/r11c/c-bad-evidence-refence.py --check   # 只报能不能逐字匹配上
    python3 data/r11c/c-bad-evidence-refence.py           # 执行

目标块从 `data/r11c/c-bad-evidence-blocks.json`(由 c-bad-evidence-scan.py 生成)按
(文件, 行号) 取正文,所以名单里写的是坐标而不是手抄的命令 —— 手抄一遍就是又一次
「摘录与原文不符」的机会。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BLOCKS = ROOT / "data/r11c/c-bad-evidence-blocks.json"

WHY_NODE = """基线是只读 checkout、**没有 `apps/desktop/node_modules`**;补它只能在基线里 `npm ci`,
那会弄脏全项目的引用基准(CLAUDE.md 边界第一条)。R10B 跑它用的是基线之外一份
**会话专属副本**,该目录已随会话消失 —— 所以这条命令在新容器里**原理上跑不出原值**。
按派工书如实声明,不伪造输出;块正文一字未动。"""

DECL = {
    "vitest": ("**R11C 片 C 改:围栏由 ```verify 改为 ```text —— 它不是可重跑命令。**\n"
               "vitest 要 `apps/desktop/node_modules`,而" + WHY_NODE),
    "eslint": ("**R11C 片 C 改:围栏由 ```verify 改为 ```text —— 它不是可重跑命令。**\n"
               "eslint 要该工程自己的 flat config 与插件,也就是 `apps/desktop/node_modules`,而"
               + WHY_NODE),
    "nodepath": ("**R11C 片 C 改:围栏由 ```verify 改为 ```text —— 它不是可重跑命令。**\n"
                 "命令自己的第一行注释就写着「需要一个装了 typescript 的 checkout 提供 NODE_PATH」,\n"
                 "指的是 R10B 那份**会话专属** TS 副本;" + WHY_NODE),
}

# (文件, 该块在 blocks.json 里的起始行号, 用哪段声明)
TARGETS: list[tuple[str, int, str]] = [
    ("notes/r10b-raw-build-package.md", 1358, "vitest"),
    ("notes/r10b-raw-build-package.md", 1370, "vitest"),
    ("notes/r10b-raw-capability-panels.md", 1247, "vitest"),
    ("notes/r10b-raw-capability-panels.md", 1259, "vitest"),
    ("notes/r10b-raw-chat-composer.md", 1508, "eslint"),
    ("notes/r10b-raw-chat-composer.md", 1669, "vitest"),
    ("notes/r10b-raw-i18n-l3.md", 99, "nodepath"),
    ("notes/r10b-raw-i18n-l3.md", 834, "vitest"),
    ("notes/r10b-raw-lib-themes.md", 1870, "vitest"),
    ("notes/r10b-raw-message-render.md", 1403, "vitest"),
    ("notes/r10b-raw-pane-shell-ui.md", 1444, "vitest"),
    ("notes/r10b-raw-settings-billing.md", 1300, "vitest"),
    ("notes/r10b-raw-shell-overlays.md", 1405, "vitest"),
    ("notes/r10b-raw-store-state.md", 1396, "vitest"),
]


def main(argv: list[str]) -> int:
    check = "--check" in argv
    recs = {(r["file"], r["line"]): r for r in json.loads(BLOCKS.read_text())}
    bad = 0
    for path, line, key in TARGETS:
        rec = recs.get((path, line))
        if rec is None:
            print(f"NO-RECORD {path}:{line}")
            bad += 1
            continue
        old = "```verify\n" + rec["body"] + "```"
        new = DECL[key] + "\n\n```text\n" + rec["body"] + "```"
        p = ROOT / path
        text = p.read_text(encoding="utf-8")
        n = text.count(old)
        if n != 1:
            print(f"NOT-UNIQUE({n}) {path}:{line}")
            bad += 1
            continue
        print(f"{'WOULD-FIX' if check else 'FIXED'} {path}:{line} [{key}]")
        if not check:
            p.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"targets={len(TARGETS)} problems={bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
