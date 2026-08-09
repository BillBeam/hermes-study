#!/usr/bin/env python3
"""片 F 导出面枚举器(R10B)。

用法:
    python3 data/r10b/probes/probe_f_exports.py <hermes-agent 根> <清单文件>

对清单里每个 .ts/.tsx 文件,用正则抓顶层 `export` 声明(named / default /
re-export),输出 `路径<TAB>行号<TAB>导出名`。纯文本扫描,不做 TS 解析——
目的是给「接口面逐项列全」一个可重跑的条数,不是做类型检查。
"""
import re
import sys
from pathlib import Path

PATTERNS = [
    # export const/let/var/function/class/type/interface/enum NAME
    re.compile(r'^export\s+(?:declare\s+)?(?:async\s+)?(?:const|let|var|function|class|type|interface|enum)\s+([A-Za-z_$][\w$]*)'),
    # export default function NAME / export default class NAME
    re.compile(r'^export\s+default\s+(?:async\s+)?(?:function|class)\s*([A-Za-z_$][\w$]*)?'),
]
BRACE = re.compile(r'^export\s+(?:type\s+)?\{([^}]*)\}')
STAR = re.compile(r"^export\s+\*\s+from\s+['\"]([^'\"]+)['\"]")
DEFAULT_EXPR = re.compile(r'^export\s+default\s+(?!function|class)')


def scan(path: Path):
    out = []
    for lineno, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        if not line.startswith('export'):
            continue
        m = STAR.match(line)
        if m:
            out.append((lineno, f'*from:{m.group(1)}'))
            continue
        m = BRACE.match(line)
        if m:
            for piece in m.group(1).split(','):
                piece = piece.strip()
                if not piece:
                    continue
                piece = re.sub(r'^type\s+', '', piece)
                name = piece.split(' as ')[-1].strip()
                if name:
                    out.append((lineno, name))
            continue
        matched = False
        for pat in PATTERNS:
            m = pat.match(line)
            if m:
                out.append((lineno, m.group(1) or 'default'))
                matched = True
                break
        if matched:
            continue
        if DEFAULT_EXPR.match(line):
            out.append((lineno, 'default'))
    return out


def main() -> int:
    root = Path(sys.argv[1])
    listing = Path(sys.argv[2])
    total = 0
    files = 0
    for rel in listing.read_text().split():
        if not rel.endswith(('.ts', '.tsx')):
            continue
        p = root / rel
        rows = scan(p)
        files += 1
        total += len(rows)
        for lineno, name in rows:
            print(f'{rel}\t{lineno}\t{name}')
    print(f'# files={files} exports={total}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
