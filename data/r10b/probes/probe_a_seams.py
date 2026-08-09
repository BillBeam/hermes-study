#!/usr/bin/env python3
"""R10B 片 A 接缝枚举探针 —— 用法:

    python3 data/r10b/probes/probe_a_seams.py /home/user/hermes-agent \
        data/r10b/slices/A.txt

只读扫描,不改基线、不装包。逐项打印片 A 底稿里每张接缝表的条数,
用来复核 notes/r10b-raw-chat-composer.md 报的数字。
"""

import pathlib
import re
import sys


def slice_files(root: pathlib.Path, listing: pathlib.Path):
    return [root / line.strip() for line in listing.read_text().splitlines() if line.strip()]


def count_interface_fields(src: str, header: str) -> int:
    """`interface X {` 到第一个顶格 `}` 之间的一级字段数。"""
    body = re.search(re.escape(header) + r"\s*\{(.*?)\n\}", src, re.S)
    if not body:
        return -1
    return len(re.findall(r"^  \$?[a-zA-Z]+\??\s*[:(]", body.group(1), re.M))


def main() -> int:
    root = pathlib.Path(sys.argv[1])
    listing = pathlib.Path(sys.argv[2])
    files = slice_files(root, listing)

    print(f"slice files            : {len(files)}")
    print(f"slice lines            : {sum(len(f.read_text().splitlines()) for f in files)}")

    # 1. 顶层 export 面
    exports = sum(len(re.findall(r"^export ", f.read_text(), re.M)) for f in files)
    print(f"top-level `export` decls: {exports}")

    # 2. ChatBarProps / ChatBarState
    types_src = (root / "apps/desktop/src/app/chat/composer/types.ts").read_text()
    print(f"ChatBarProps fields    : {count_interface_fields(types_src, 'export interface ChatBarProps')}")

    # 3. COMPOSER_AREAS
    contrib = (root / "apps/desktop/src/app/chat/composer/contrib.ts").read_text()
    areas = re.search(r"export const COMPOSER_AREAS = \{(.*?)\n\} as const", contrib, re.S)
    print(f"COMPOSER_AREAS keys    : {len(re.findall(r'^  [a-zA-Z]+:', areas.group(1), re.M))}")

    # 4. focus 事件总线
    focus = (root / "apps/desktop/src/app/chat/composer/focus.ts").read_text()
    print(f"focus-bus event names  : {len(re.findall(r'^const [A-Z_]+_EVENT = .hermes:', focus, re.M))}")

    # 5. SessionView / PaneMirror
    view = (root / "apps/desktop/src/app/chat/session-view.tsx").read_text()
    print(f"SessionView fields     : {count_interface_fields(view, 'export interface SessionView')}")
    mirror = (root / "apps/desktop/src/app/chat/pane-mirror.ts").read_text()
    print(f"PaneMirror<T> fields   : {count_interface_fields(mirror, 'export interface PaneMirror<T>')}")

    # 6. data-slot DOM 契约
    slots = set()
    for f in files:
        slots.update(re.findall(r'data-slot="([a-z0-9_-]+)"', f.read_text()))
    print(f"data-slot values       : {len(slots)}  {sorted(slots)}")

    # 7. 网关 RPC
    rpcs = set()
    for f in files:
        for m in re.finditer(r"request(?:Gateway)?(?:<[^>]*>)?\(\s*'([a-z][a-z_]*\.[a-z_]+)'", f.read_text()):
            rpcs.add(m.group(1))
    print(f"gateway RPC methods    : {len(rpcs)}  {sorted(rpcs)}")

    # 8. store 面
    mods: dict[str, set[str]] = {}
    for f in files:
        for m in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*'(@/store/[a-z-]+)'", f.read_text(), re.S):
            for part in m.group(1).split(","):
                name = re.sub(r"^type\s+", "", part.strip()).split(" as ")[0].strip()
                if name:
                    mods.setdefault(m.group(2), set()).add(name)
    print(f"store modules imported : {len(mods)}")
    print(f"store symbols imported : {sum(len(v) for v in mods.values())}")
    for mod in sorted(mods):
        print(f"    {mod} ({len(mods[mod])}): {', '.join(sorted(mods[mod]))}")

    # 9. composer/hooks 目录(非测试)
    hooks = sorted((root / "apps/desktop/src/app/chat/composer/hooks").glob("*.ts"))
    hooks = [h for h in hooks if ".test." not in h.name]
    print(f"composer hook modules  : {len(hooks)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
