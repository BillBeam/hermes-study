#!/usr/bin/env python3
"""R11C 片 D:补全路径**之前**的独立内容校核。

「基线里唯一候选」是一条**结构**判据。它可能整类地错:如果作者当年心里想的是一个
基线里**根本不存在**的文件,而恰好只有一个同名文件,判据照样给出唯一候选。
所以在改写 1,781 处之前,拿一条**内容**判据抽样对一遍。

判据:锚点所在那一行(散文/表格)里,取锚点**之外**的反引号片段当探针
(与 `verify_citations.py` 的 `cell_tokens` 同款过滤:太短的、纯符号的、
本身就是文件名的、没有代码形状的都丢掉),问它是否出现在候选文件
`[行号-BAND, 行号+BAND]` 这一段里。命中 = 这条补全在内容上说得通。

**这不是证明**,是抽样旁证:没有反引号片段的行给不出判据(NO-PROBE),
命中率要连同 NO-PROBE 的比例一起报,不许只报命中率。

    python3 data/r11c/d-anchor-resolution-validate.py [--band 12] [--seed 11]
"""
import random
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

STUDY = Path(__file__).resolve().parents[2]
REPO = Path("/home/user/hermes-agent")
sys.path.insert(0, str(STUDY / "scripts"))
import verify_citations as vc  # noqa: E402

BAND = 12
SEED = 11
for i, a in enumerate(sys.argv):
    if a == "--band":
        BAND = int(sys.argv[i + 1])
    if a == "--seed":
        SEED = int(sys.argv[i + 1])

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


def collect():
    skip = {l.strip() for l in (STUDY / "data/r11c/slice-c-files.txt").read_text().splitlines()
            if l.strip()}
    out = []
    for f in sorted((STUDY / "notes").glob("*.md")):
        rel = f"notes/{f.name}"
        if rel in skip or f.name.startswith("r11c-"):
            continue
        in_fence = False
        for ln, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence or QUOTE.match(line):
                continue
            for m in WIDE.finditer(line):
                p, start = m.group("path"), int(m.group("start"))
                if (REPO / p).is_file() or (STUDY / p).is_file():
                    continue
                c = BASE_IDX.get(p, set())
                if len(c) != 1:
                    continue
                only = next(iter(c))
                out.append((rel, ln, line, p, start, only))
    return out


def probes(line, m_path):
    """行内可用作内容探针的反引号片段(排除锚点自身)。"""
    toks = []
    for raw in re.findall(r"`([^`]+)`", line):
        if vc.any_anchor(raw):
            continue
        t = " ".join(raw.split())
        if len(t) < vc.TABLE_MIN_TOKEN or re.fullmatch(r"[\d\W_]+", t):
            continue
        if vc.BARE_PATH.fullmatch(t):
            continue
        if not vc.CODEISH.search(t):
            continue
        toks.append(t)
    return toks


def main():
    cands = collect()
    random.Random(SEED).shuffle(cands)
    hit = miss = noprobe = 0
    misses = []
    for rel, ln, line, p, start, only in cands:
        toks = probes(line, p)
        if not toks:
            noprobe += 1
            continue
        src = (REPO / only).read_text(encoding="utf-8", errors="replace").splitlines()
        lo, hi = max(0, start - 1 - BAND), min(len(src), start - 1 + BAND)
        band = " ".join(" ".join(x.split()) for x in src[lo:hi])
        if any(t in band for t in toks):
            hit += 1
        else:
            miss += 1
            if len(misses) < 25:
                misses.append((rel, ln, f"{p}:{start}", only, toks[0][:60]))
    tot = hit + miss
    print(f"待补全总数 = {len(cands)}")
    if not cands:
        # 任务二跑完之后这里就是 0 —— 待补全的都补完了。这不是错误,
        # 而且它必须**不报错**:关卡会重跑未配对的 verify 块,一个
        # ZeroDivisionError 会被判 EVIDENCE-RUNFAIL 而阻断整轮 commit。
        print("(本片任务二已把可机械补全的那批改完,故为 0;"
              "改写前的读数抄录在底稿 §3.1.1,声明为不可重跑快照。)")
        return
    print(f"有内容探针的 = {tot}   无探针(NO-PROBE) = {noprobe}"
          f"  ({noprobe * 100.0 / len(cands):.1f}%)")
    print(f"band=+/-{BAND} 命中 = {hit}   未命中 = {miss}"
          f"   命中率 = {hit * 100.0 / tot:.1f}%")
    print("\n未命中样例(最多 25 条,人工看是探针不合用还是补全错了):")
    for r in misses:
        print(f"  {r[0]}:{r[1]}  {r[2]} -> {r[3]}   探针: {r[4]}")


if __name__ == "__main__":
    main()
