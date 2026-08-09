#!/usr/bin/env python3
"""R10B 片D 探针:枚举「网关事件类型 → 落到哪些 store 模块」。

用法:
    python3 data/r10b/probes/probe_d_event_to_store.py /home/user/hermes-agent [--tsv]

做法(纯文本,不执行):
  1. 在 apps/desktop/src/app/session/hooks/use-message-stream/gateway-event.ts 的
     import 段建立「符号 → 来源模块」映射(只收 '@/store/...' 与 './...'/'../..' 之外的 store)。
  2. 用 `event.type === '<t>'` / `<CONST>.has(event.type)` 切分 if-else 链的分支区间。
  3. 分支区间内出现的 store 符号 → 该事件类型触达的 store 模块集合。
输出 TSV: eventType  startLine  endLine  store1,store2,...
"""
import re
import sys
import pathlib

SRC = 'apps/desktop/src/app/session/hooks/use-message-stream/gateway-event.ts'
EQ = re.compile(r"event\.type === '([^']+)'")
SETHAS = re.compile(r'(\w+_EVENT_TYPES)\.has\(event\.type\)')
IMP = re.compile(r"^import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+'(@/store/[^']+)'", re.S | re.M)


def main():
    root = pathlib.Path(sys.argv[1])
    text = (root / SRC).read_text(encoding='utf-8')
    lines = text.splitlines()

    sym2mod = {}
    for m in IMP.finditer(text):
        mod = m.group(2).split('/')[-1]
        for raw in m.group(1).split(','):
            name = raw.strip().removeprefix('type ').strip()
            if name:
                sym2mod[name] = mod

    # branch starts
    marks = []
    for i, line in enumerate(lines):
        if 'else if' in line or re.match(r'\s*if \(event\.type', line) or 'event.type ===' in line:
            types = EQ.findall(line)
            sets = SETHAS.findall(line)
            if types or sets:
                marks.append((i, types + [f'<{s}>' for s in sets]))
    # de-dup: a multi-type condition spanning lines (309-313) yields several marks
    merged = []
    for i, types in marks:
        if merged and i - merged[-1][0] <= 5 and not lines[i].lstrip().startswith('} else'):
            merged[-1][1].extend(types)
        else:
            merged.append([i, list(types)])

    rows = []
    for idx, (i, types) in enumerate(merged):
        end = merged[idx + 1][0] if idx + 1 < len(merged) else len(lines)
        body = '\n'.join(lines[i:end])
        mods = sorted({mod for sym, mod in sym2mod.items()
                       if re.search(r'\b' + re.escape(sym) + r'\b', body)})
        rows.append(('|'.join(types), i + 1, end, ','.join(mods)))

    if len(sys.argv) > 2 and sys.argv[2] == '--tsv':
        for r in rows:
            print('\t'.join(str(x) for x in r))
    print(f'# import-mapped store symbols={len(sym2mod)} '
          f'from {len(set(sym2mod.values()))} store modules', file=sys.stderr)
    print(f'# event branches={len(rows)}, distinct event types='
          f'{len({t for r in rows for t in r[0].split("|") if not t.startswith("<")})}',
          file=sys.stderr)


if __name__ == '__main__':
    main()
