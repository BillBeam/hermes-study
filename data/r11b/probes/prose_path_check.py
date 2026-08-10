#!/usr/bin/env python3
"""自查:正文散文里提到的文件路径,是不是真的解析得到。

`verify_citations.py` 只配对「锚点 + 紧跟的块」,**散文里随手写的路径它不管**
(R11A 报告 `:465` 已点出这一点)。于是报告正文可以引一个不存在的路径,而两道关卡全绿。
本探针补这个口子:把围栏块外、反引号里的**像路径的串**挑出来,逐个在基线与本仓库解析。

判定:
  - 只看反引号内的串,且必须含 `/` 或已知扩展名 —— 不猜裸词;
  - 允许结尾 `:行号` 与 `:起-止`;
  - 允许通配符(`chapters/r2-*.md` 这类指代一组文件),用 glob 判存在;
  - 基线找不到就在本学习仓库找,两边都找不到才算 MISSING。

    python3 data/r11b/probes/prose_path_check.py <file.md> [...]
退出码 1 = 有解析不到的路径。
"""
import glob as globmod
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "-C", str(Path(__file__).resolve().parent),
                            "rev-parse", "--show-toplevel"],
                           capture_output=True, check=True).stdout.decode().strip())
BASELINE = Path(os.environ.get("HERMES_BASELINE", "/home/user/hermes-agent"))

TICK = re.compile(r"`([^`\n]+)`")
EXTS = ("py mdx md yaml yml toml c h sh json tsx ts mjs js nix rs txt tsv "
        "js jsx css html ps1 cmd").split()
LINESUF = re.compile(r":\d+(?:-\d+)?$")


def looks_like_path(s: str) -> bool:
    s = LINESUF.sub("", s).strip()
    if not s or " " in s or s.startswith(("-", "$", "http")):
        return False
    # 占位符不是路径:`<hex>`、`{base_url}/…` 是在描述形状,不是在指一个文件。
    if any(c in s for c in "<>{}"):
        return False
    # 仓库外的绝对路径不归本检查管(本检查只问「仓库里的路径写对没有」)。
    if s.startswith("/") and not s.startswith((str(BASELINE), str(ROOT))):
        return False
    if "/" in s:
        return True
    # `.ps1` 这种**光是一个扩展名**的串不是文件名,要求点号前有词干。
    return any(s.endswith("." + e) and len(s) > len(e) + 1 for e in EXTS)


def resolves(s: str) -> bool:
    s = LINESUF.sub("", s).strip().rstrip("/")
    for root in (BASELINE, ROOT):
        if (root / s).exists():
            return True
        if any(ch in s for ch in "*?[") and globmod.glob(str(root / s)):
            return True
    return False


def main(argv: list[str]) -> int:
    bad = 0
    total = 0
    for arg in argv:
        p = Path(arg)
        if not p.is_file():
            print(f"skip (not a file): {p}")
            continue
        infence = False
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace")
                                 .splitlines(), 1):
            if line.lstrip().startswith("```"):
                infence = not infence
                continue
            if infence:
                continue
            for m in TICK.finditer(line):
                s = m.group(1)
                if not looks_like_path(s):
                    continue
                total += 1
                if not resolves(s):
                    bad += 1
                    print(f"[PROSE-PATH-MISSING] {p}:{n}  `{s}`")
    print(f"\nprose paths checked={total}  missing={bad}")
    if bad:
        print("FAIL: 正文散文里有解析不到的路径")
        return 1
    print("OK: every prose path resolves in the baseline or this repo")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
