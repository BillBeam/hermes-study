#!/usr/bin/env python3
"""R11A 片B 探针:枚举 docker/s6-rc.d/ 下的 s6-rc 服务与 bundle。

只读文件系统,不启动任何容器。用法:

    python3 data/r11a/probes/probe_b_s6.py /home/user/hermes-agent

输出每个条目一行:名字<TAB>type<TAB>dependencies<TAB>contents<TAB>有无 finish。
s6-rc 的约定:目录里有 `type` 文件的是服务(longrun/oneshot),
`type` 缺失但有 `contents.d/` 的是 bundle;`dependencies.d/` 里每个
空文件名 = 一条依赖边;`contents.d/` 里每个空文件名 = bundle 成员。
"""
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")
    base = root / "docker" / "s6-rc.d"
    rows = []
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        typ = (d / "type").read_text(encoding="utf-8").strip() if (d / "type").is_file() else "(bundle)"
        deps = ",".join(sorted(p.name for p in (d / "dependencies.d").iterdir())) if (d / "dependencies.d").is_dir() else "-"
        cont = ",".join(sorted(p.name for p in (d / "contents.d").iterdir())) if (d / "contents.d").is_dir() else "-"
        rows.append((d.name, typ, deps, cont, "yes" if (d / "finish").is_file() else "no"))
    if len(sys.argv) > 2 and sys.argv[2] == "--count":
        svc = [r for r in rows if r[1] != "(bundle)"]
        print(f"{len(svc)} services / {len(rows) - len(svc)} bundles")
        return 0
    print("name\ttype\tdependencies\tcontents\tfinish")
    for r in rows:
        print("\t".join(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
