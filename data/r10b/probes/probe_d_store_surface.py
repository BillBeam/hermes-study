#!/usr/bin/env python3
"""R10B 片D 探针:枚举 apps/desktop/src/store/ 每个模块的 state 形状与 action 面。

用法:
    python3 data/r10b/probes/probe_d_store_surface.py /home/user/hermes-agent [--tsv|--md|--sum]

分类规则(纯文本扫描,不 import、不执行):
  state   : export const $NAME = <atom|map|persistentAtom|persisted*|deepMap>(...)
  computed: export const $NAME = computed(...)
  action  : export [async] function NAME(...)
  type    : export type / export interface
  const   : 其余 export const(常量、选择器工厂、React 组件等)
输出按文件一行,或 --tsv 逐条。
"""
import re
import sys
import pathlib

STATE_CTOR = re.compile(
    r'^export const (\$?[A-Za-z_][\w]*)(?::[^=]+)?\s*=\s*'
    r'(atom|map|deepMap|persistentAtom|persistentMap|persistedAtom|persistBooleanAtom)\b'
)
COMPUTED = re.compile(r'^export const (\$?[A-Za-z_][\w]*)(?::[^=]+)?\s*=\s*computed\b')
OTHER_CONST = re.compile(r'^export const (\$?[A-Za-z_][\w]*)')
FUNC = re.compile(r'^export (?:async )?function (\w+)')
TYPE = re.compile(r'^export (?:type|interface) (\w+)')
REEXPORT = re.compile(r'^export \{ ([^}]+) \}')


def scan(path: pathlib.Path):
    out = {'state': [], 'computed': [], 'action': [], 'type': [], 'const': []}
    for i, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        for kind, rx in (('state', STATE_CTOR), ('computed', COMPUTED),
                         ('action', FUNC), ('type', TYPE)):
            m = rx.match(line)
            if m:
                out[kind].append((m.group(1), i))
                break
        else:
            m = OTHER_CONST.match(line)
            if m:
                out['const'].append((m.group(1), i))
                continue
            m = REEXPORT.match(line)
            if m:
                for n in m.group(1).split(','):
                    out['state'].append((n.strip() + '(re-export)', i))
    return out


def main():
    root = pathlib.Path(sys.argv[1])
    mode = sys.argv[2] if len(sys.argv) > 2 else '--md'
    files = sorted(p for p in (root / 'apps/desktop/src/store').glob('*.ts')
                   if not p.name.endswith('.test.ts'))
    tot = {k: 0 for k in ('state', 'computed', 'action', 'type', 'const')}
    for p in files:
        r = scan(p)
        for k in tot:
            tot[k] += len(r[k])
        rel = p.relative_to(root)
        if mode == '--tsv':
            for k, items in r.items():
                for name, ln in items:
                    print(f'{rel}\t{ln}\t{k}\t{name}')
        elif mode == '--md':
            def j(k, cap=99):
                v = [n for n, _ in r[k]]
                return ', '.join(f'`{x}`' for x in v[:cap]) or '—'
            print(f'| `{rel}` | {len(open(p).readlines())} | {j("state")} | '
                  f'{j("computed")} | {j("action")} |')
    if mode == '--sum':
        print(f'files={len(files)}')
    for k in ('state', 'computed', 'action', 'type', 'const'):
        print(f'# TOTAL {k}={tot[k]}', file=sys.stderr)
    print(f'# TOTAL files={len(files)}', file=sys.stderr)


if __name__ == '__main__':
    main()
