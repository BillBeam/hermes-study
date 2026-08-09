#!/usr/bin/env python3
"""片 F 工具名对账(R10B)。

用法:
    python3 data/r10b/probes/probe_f_tool_names.py /home/user/hermes-agent

左边:桌面渲染层 `TOOL_META`(tool/fallback-model/index.ts)的键 —— 有专属图标/
色调/三段标题文案的工具名。
右边:Python 内核 `registry.register(name="…")` 注册的工具名(tools/*.py,
支持 `register(` 后换行的写法)。

只对账「渲染层点名了哪些工具」这一面。渲染层没点名的内核工具走通用回落
(PREFIX_META / titleForTool),那是设计,不是缺口;所以脚本把
「渲染层有、内核无」单独列出——那才是死行。
"""
import re
import sys
from pathlib import Path

META_KEY = re.compile(r'^  ([a-z_0-9]+): \{')
REG = re.compile(r'registry\.register\(\s*name="([a-z_0-9]+)"', re.S)


def ui_tool_meta(root: Path) -> list[str]:
    src = (root / 'apps/desktop/src/components/assistant-ui/tool/fallback-model/index.ts').read_text().splitlines()
    start = next(i for i, l in enumerate(src) if l.startswith('const TOOL_META'))
    keys = []
    for line in src[start + 1:]:
        if line.startswith('}'):
            break
        m = META_KEY.match(line)
        if m:
            keys.append(m.group(1))
    return keys


def kernel_tools(root: Path) -> set[str]:
    names: set[str] = set()
    for py in sorted((root / 'tools').rglob('*.py')):
        names.update(REG.findall(py.read_text(encoding='utf-8', errors='replace')))
    return names


def main() -> int:
    root = Path(sys.argv[1])
    ui = ui_tool_meta(root)
    kernel = kernel_tools(root)
    missing = [n for n in ui if n not in kernel]
    print(f'TOOL_META keys        : {len(ui)}')
    print(f'kernel registered     : {len(kernel)}')
    print(f'UI-only (dead rows)   : {len(missing)} -> {", ".join(missing)}')
    print(f'kernel-only (generic) : {len(kernel - set(ui))}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
