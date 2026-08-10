#!/usr/bin/env python3
"""证据命令关卡的覆盖面普查:全语料有多少 ```verify 块,多少配了 ```text 块。

口径**直接复用 `scripts/verify_evidence_commands.py` 的两条正则**,不另起一套——
一个用自己口径去量另一个关卡的普查,量到的是自己的定义,不是关卡的覆盖面。

用法:python3 data/r11b/probes/evidence_pairing_census.py [--by-file] [--unpaired] [--rev REV]

`--rev` 读**某个提交里的**语料而不是工作区。没有它,这个数会随每一份新底稿变动,
于是「935 / 177 / 18.9%」这种读数在报告里既无法复核、也说不清量的是哪一刻的语料
——正是 CLAUDE.md 要求「统计须给可重跑计数命令与口径」所指的那种数。
不依赖会话专属路径:仓库根从本文件位置推出。
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "-C", str(Path(__file__).resolve().parent),
                            "rev-parse", "--show-toplevel"],
                           capture_output=True, check=True).stdout.decode().strip())
sys.path.insert(0, str(ROOT / "scripts"))
from verify_evidence_commands import PAIR, ANY_VERIFY  # noqa: E402

SCOPE = ("notes", "chapters", "reports", "reviews", "data")


def iter_corpus(rev: str | None):
    """(展示名, 正文) 序列。rev 为 None 时读工作区,否则读该提交。"""
    if rev is None:
        for d in SCOPE:
            for p in sorted((ROOT / d).rglob("*.md")):
                yield p.relative_to(ROOT).as_posix(), p.read_text(
                    encoding="utf-8", errors="replace")
        return
    names = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", rev],
                           capture_output=True, check=True).stdout.decode().splitlines()
    for name in sorted(names):
        if not name.endswith(".md") or name.split("/")[0] not in SCOPE:
            continue
        blob = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{name}"],
                              capture_output=True, check=True).stdout
        yield name, blob.decode("utf-8", errors="replace")


def main(argv: list[str]) -> int:
    by_file = "--by-file" in argv
    show_unpaired = "--unpaired" in argv
    rev = argv[argv.index("--rev") + 1] if "--rev" in argv else None
    tot = paired = 0
    rows = []
    unpaired_files = []
    for name, text in iter_corpus(rev):
        n = len(ANY_VERIFY.findall(text))
        if not n:
            continue
        k = len(PAIR.findall(text))
        tot += n
        paired += k
        rows.append((n, k, name))
        if k < n:
            unpaired_files.append((n - k, name))

    if by_file:
        for n, k, name in sorted(rows, reverse=True):
            print(f"{n:5d} verify {k:5d} paired  {name}")
    if show_unpaired:
        for miss, name in sorted(unpaired_files, reverse=True)[:25]:
            print(f"{miss:5d} unpaired  {name}")
    pct = 100.0 * paired / tot if tot else 0.0
    print(f"verify_blocks={tot} paired={paired} unpaired={tot - paired} "
          f"paired_pct={pct:.1f}% files_with_verify={len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
