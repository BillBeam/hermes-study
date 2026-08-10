#!/usr/bin/env python3
"""R11C 片 C 附带发现:块正文里的**字面三反引号**会把关卡的块识别正则截断在半路。

关卡用 `NOFENCE = (?:(?!```).)*?` 匹配 ```verify 块正文,所以正文里任何一个字面
三反引号都会被当成块尾:块被截成半截命令再拿去跑。判据就是这一条,不多不少 ——
**按行找出真正的块(开栏 `​```verify`,闭栏为第一条 strip() 后恰为三反引号的行),
再看真正的块正文里有没有出现字面三反引号。**

闭栏判定用 `strip()` 而不是 `rstrip()`:列表里的围栏块是缩进的,
用 `rstrip()` 会认不出缩进的闭栏、把后面几个块并成一个,读数虚高。

    python3 data/r11c/c-bad-evidence-innerfence.py

不依赖会话专属路径:仓库根从本文件位置推出。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "-C", str(Path(__file__).resolve().parent),
                            "rev-parse", "--show-toplevel"],
                           capture_output=True, check=True).stdout.decode().strip())
BT = chr(96) * 3


def main() -> int:
    hits = []
    for d in ("notes", "reports", "chapters"):
        for p in sorted((ROOT / d).rglob("*.md")):
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            i = 0
            while i < len(lines):
                if lines[i].strip() == BT + "verify":
                    j = i + 1
                    while j < len(lines) and lines[j].strip() != BT:
                        j += 1
                    if any(BT in ln for ln in lines[i + 1:j]):
                        hits.append(f"{p.relative_to(ROOT).as_posix()}:{i + 1}")
                    i = j + 1
                else:
                    i += 1
    print(len(hits))
    print(*hits, sep="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
