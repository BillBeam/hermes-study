#!/usr/bin/env python3
"""R10B 片D 探针:枚举 apps/desktop/src/hermes.ts 的对外方法面与它打的后端路径。

用法:
    python3 data/r10b/probes/probe_d_hermes_api.py /home/user/hermes-agent [--tsv|--sum]

对每个 `export [async] function NAME(` 抓取:
  - 行号
  - 函数体内第一处 `path: '<...>'` / `path: `<...>`` (REST 路径,已把 ${...} 归一为 {})
  - 函数体内第一处 gateway 调用方法名 `.request('<m>'` / `.notify('<m>'`
输出 TSV:name  line  kind(rest|rpc|bridge|pure)  target
"""
import re
import sys
import pathlib

FUNC = re.compile(r'^export (?:async )?function (\w+)')
PATH = re.compile(r"path:\s*[`'\"]([^`'\"]*)")
RPC = re.compile(r"\.(?:request|notify|call)(?:<[^>]*>)?\(\s*'([^']+)'")
BRIDGE = re.compile(r'window\.hermesDesktop\.(\w+)')


def main():
    root = pathlib.Path(sys.argv[1])
    mode = sys.argv[2] if len(sys.argv) > 2 else '--tsv'
    src = (root / 'apps/desktop/src/hermes.ts').read_text(encoding='utf-8').splitlines()
    starts = [(i, FUNC.match(l).group(1)) for i, l in enumerate(src) if FUNC.match(l)]
    rows = []
    for idx, (i, name) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(src)
        body = '\n'.join(src[i:end])
        m = PATH.search(body)
        if m:
            rows.append((name, i + 1, 'rest', re.sub(r'\$\{[^}]*\}', '{}', m.group(1))))
            continue
        m = RPC.search(body)
        if m:
            rows.append((name, i + 1, 'rpc', m.group(1)))
            continue
        m = BRIDGE.search(body)
        if m:
            rows.append((name, i + 1, 'bridge', f'window.hermesDesktop.{m.group(1)}'))
            continue
        rows.append((name, i + 1, 'pure', ''))
    if mode == '--tsv':
        for r in rows:
            print('\t'.join(str(x) for x in r))
    kinds = {}
    for r in rows:
        kinds[r[2]] = kinds.get(r[2], 0) + 1
    print(f'# exported functions={len(rows)} {kinds}', file=sys.stderr)
    print(f'# distinct REST paths={len({r[3] for r in rows if r[2] == "rest"})}', file=sys.stderr)


if __name__ == '__main__':
    main()
