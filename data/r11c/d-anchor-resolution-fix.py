#!/usr/bin/env python3
"""R11C 片 D 任务二:把「基线里唯一候选」的裸文件名锚点补成全路径。

判据(只有这一条,别的一概不猜):基线 863e313 里**恰好一个**文件的路径以这个串
结尾(按目录边界匹配)。`run.py` -> `gateway/run.py` 走这条;`__init__.py`(171 个候选)、
`base.py`(9 个)一律不动 —— 猜错比不修更糟,一个指向错文件的锚点看起来完全正常。

**两处绝不改写**,因为改了就是在伪造证据:

  - 围栏块**内部**。```` ``` ```` 块的契约是**逐字源码摘录**;基线源码里本来就带
    `foo.py:123` 字样的行不在少数,改写它等于让摘录与基线不符(BLOCK-DRIFT),
    而 ```` ```verify ```` 块里改写命令会让它跑出别的输出。
  - 引用块(`>`)**内部**。它可能是逐字文档摘录,同理。

这两处正是 `verify_citations.py` 自己跳过的两处(`:666` FENCE / `:676` QUOTE),
所以「本脚本改的范围」= 「关卡会读的范围」,两边口径一致。

范围:只改 `notes/`。`chapters/` 本轮只报不改;`reports/` 按 CLAUDE.md 正文不静默改写;
`reviews/` 原文不改;`data/r11c/slice-c-files.txt` 里 31 个文件归片 C;`r11c-*` 是本轮在途产出。

    python3 data/r11c/d-anchor-resolution-fix.py            # 干跑,只报数
    python3 data/r11c/d-anchor-resolution-fix.py --apply    # 落盘
"""
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

STUDY = Path(__file__).resolve().parents[2]
REPO = Path("/home/user/hermes-agent")
APPLY = "--apply" in sys.argv

WIDE = re.compile(
    r"(?P<path>\.?[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?P<ext>[A-Za-z0-9]{1,6}))"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?"
)
FENCE = re.compile(r"^\s*```")
QUOTE = re.compile(r"^\s*>")


def suffix_index(paths):
    idx = defaultdict(set)
    for p in paths:
        parts = p.split("/")
        for k in range(len(parts)):
            idx["/".join(parts[k:])].add(p)
    return idx


def ls(root):
    return [p for p in subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                                      text=True, check=True).stdout.split("\n") if p]


BASE_IDX = suffix_index(ls(REPO))
STUDY_IDX = suffix_index(ls(STUDY))
_LEN = {}


def flen(root: Path, rel: str) -> int:
    k = str(root / rel)
    if k not in _LEN:
        try:
            _LEN[k] = len((root / rel).read_text(encoding="utf-8",
                                                 errors="replace").splitlines())
        except OSError:
            _LEN[k] = -1
    return _LEN[k]


def unique_target(path: str, start: int):
    """(全路径, 哪棵树) 或 None。行号越界即拒绝 —— 那说明候选很可能不是它。"""
    if (REPO / path).is_file() or (STUDY / path).is_file():
        return None  # 已经能解析,不动
    for idx, root, tag in ((BASE_IDX, REPO, "baseline"), (STUDY_IDX, STUDY, "study")):
        c = idx.get(path, set())
        if len(c) == 1:
            only = next(iter(c))
            n = flen(root, only)
            if n < 0 or start > n:
                return None  # 行号越界:候选存疑,交人工
            return only, tag
        if len(c) > 1:
            return None  # 歧义,一律不猜
    return None


def targets():
    skip = {l.strip() for l in (STUDY / "data/r11c/slice-c-files.txt").read_text().splitlines()
            if l.strip()}
    for f in sorted((STUDY / "notes").glob("*.md")):
        rel = f"notes/{f.name}"
        if rel in skip or f.name.startswith("r11c-"):
            continue
        yield f, rel


def main():
    changed_files = 0
    total = 0
    per_name = Counter()
    skipped_in_block = 0
    for f, rel in targets():
        raw = f.read_text(encoding="utf-8")
        lines = raw.splitlines()
        in_fence = False
        out = []
        n_here = 0
        for line in lines:
            if FENCE.match(line):
                in_fence = not in_fence
                out.append(line)
                continue
            if in_fence or QUOTE.match(line):
                for m in WIDE.finditer(line):
                    if unique_target(m.group("path"), int(m.group("start"))):
                        skipped_in_block += 1
                out.append(line)
                continue

            new, pos, hit = [], 0, False
            for m in WIDE.finditer(line):
                t = unique_target(m.group("path"), int(m.group("start")))
                if not t:
                    continue
                full, _tag = t
                new.append(line[pos:m.start("path")])
                new.append(full)
                pos = m.end("path")
                per_name[f"{m.group('path')} -> {full}"] += 1
                n_here += 1
                hit = True
            if hit:
                new.append(line[pos:])
                out.append("".join(new))
            else:
                out.append(line)

        if n_here:
            changed_files += 1
            total += n_here
            if APPLY:
                f.write_text("\n".join(out) + ("\n" if raw.endswith("\n") else ""),
                             encoding="utf-8")
            print(f"  {'改' if APPLY else '将改'} {n_here:>4}  {rel}")

    print(f"\n{'已改写' if APPLY else '干跑:将改写'} {total} 处,涉及 {changed_files} 份 notes/")
    print(f"因位于围栏块 / 引用块内部而**故意跳过** {skipped_in_block} 处(改了就是伪造摘录)")
    print("\n改写最多的 15 个串:")
    for k, v in per_name.most_common(15):
        print(f"  {v:>4}  {k}")


if __name__ == "__main__":
    main()
