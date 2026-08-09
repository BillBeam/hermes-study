#!/usr/bin/env python3
"""R11A 片A — 安装器的「环境变量输入面」机械枚举。

三分法(声明式,不靠嗅探):

  A. 自默认输入 —— 同一行写成 `NAME="${NAME:-默认}"` / `NAME=${NAME:?...}`。
     这是 shell 里"环境里有就用环境的,没有就用默认"的标准写法,是最明确的旋钮。
  B. 纯外部读 —— 以 `${NAME:-...}` 读,但脚本里**从未**给 NAME 赋过值。
     例:`PREFIX`、`TERMUX_VERSION`(Termux 注入)、`PYTHONPATH`(继承来的要清掉)。
  C. 读+赋值(非自默认)—— 被 `${NAME:-}` 读,且脚本别处也给它赋过值。
     **机械上判不了**它是不是外部旋钮:`${INSTALL_DIR:-<unset>}` 是内部状态的空值兜底,
     而 `[ -z "${ANDROID_API_LEVEL:-}" ] && ANDROID_API_LEVEL=$(getprop ...)`
     是"环境里有就用、没有就探测"的真旋钮,两者形状一样。
     所以 C **不是"不算"桶,是"逐条人工判定"桶**,底稿里给出逐条裁决。

A + B = 机械可判定的输入面下界;C 需人工裁决后并入。

install.ps1 用 `$env:NAME` 读环境,PowerShell 里这个形式**只可能**是环境变量,
所以那边不需要这套区分,直接枚举。

用法:
    python3 data/r11a/probes/probe_a_env_face.py /home/user/hermes-agent
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

READ = re.compile(r"\$\{([A-Z][A-Z0-9_]*):[-?]")
ASSIGN = re.compile(
    r"(?:^|[;&|(\s])(?:local\s+|export\s+|declare\s+-\w+\s+)?([A-Z][A-Z0-9_]*)="
    r"|read\s+(?:-\w+\s+)*([A-Z][A-Z0-9_]*)\b"
    r"|for\s+([A-Z][A-Z0-9_]*)\s+in\b"
)
PS_ENV = re.compile(r"\$env:([A-Za-z_][A-Za-z0-9_]*)")


def sh_face(path: Path) -> tuple[list[str], list[str], list[str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    read = {m.group(1) for m in READ.finditer(text)}
    assigned: set[str] = set()
    self_default: set[str] = set()
    for line in text.splitlines():
        for m in ASSIGN.finditer(line):
            for g in m.groups():
                if not g:
                    continue
                assigned.add(g)
                if re.search(r"\b" + re.escape(g) + r"=[^\n]*\$\{" + re.escape(g) + r":[-?]", line):
                    self_default.add(g)
    a = sorted(read & self_default)
    b = sorted(read - assigned)
    c = sorted((read & assigned) - self_default)
    return a, b, c


def ps_face(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return sorted({m.group(1) for m in PS_ENV.finditer(text)})


def main() -> int:
    base = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/hermes-agent")
    for rel in ("scripts/install.sh", "scripts/lib/node-bootstrap.sh"):
        a, b, c = sh_face(base / rel)
        print(f"[{rel}] 输入面 = A自默认 {len(a)} + B纯外部读 {len(b)} = {len(a) + len(b)}")
        for n in a:
            print(f"  A {n}")
        for n in b:
            print(f"  B {n}")
        print(f"[{rel}] C 读+赋值,需人工裁决 {len(c)}: " + " ".join(c))
        print()
    ps = ps_face(base / "scripts/install.ps1")
    print(f"[scripts/install.ps1] $env: 读取 {len(ps)} 个:")
    for n in ps:
        print(f"  {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
