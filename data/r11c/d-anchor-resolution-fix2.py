#!/usr/bin/env python3
"""R11C 片 D 第二遍:用「候选必须长到有这一行」把一部分同名歧义变成确定。

第一遍(`d-anchor-resolution-fix.py`)的判据是「基线里恰好一个文件以它结尾」。
`base.py:5584` 过不了那一关——基线有 9 个 `base.py`。但这 9 个里**只有一个**
(`gateway/platforms/base.py`,6,861 行)长到有第 5,584 行,其余最长的 1,370 行。
**行号本身是判据**,而第一遍没用它。

两条判据同时成立才改:

  1. **长度**:按目录边界结尾匹配的候选里,`len(file) >= N` 的**只剩一个**;
  2. **内容**:锚点所在行里锚点之外的反引号片段(过滤规则同 `cell_tokens`)在
     该候选的 [N-12, N+12] 里逐字找得到 —— 与第一遍改写前的抽样校核同一条判据,
     只是这里**逐条**做,不是抽样,因为长度判据比「唯一候选」弱。

两条都过才改,任一不过点名留下。范围与第一遍完全相同(只 `notes/`,跳围栏块与引用块,
跳片 C 的 31 份,跳 `r11c-*`)。

    python3 data/r11c/d-anchor-resolution-fix2.py [--apply]
"""
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

STUDY = Path(__file__).resolve().parents[2]
REPO = Path("/home/user/hermes-agent")
sys.path.insert(0, str(STUDY / "scripts"))
import verify_citations as vc  # noqa: E402

APPLY = "--apply" in sys.argv
BAND = 12
WIDE = re.compile(
    r"(?P<path>\.?[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?P<ext>[A-Za-z0-9]{1,6}))"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?"
)
FENCE = re.compile(r"^\s*```")
QUOTE = re.compile(r"^\s*>")

paths = [p for p in subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,
                                   text=True, check=True).stdout.split("\n") if p]
IDX = defaultdict(set)
for p in paths:
    parts = p.split("/")
    for k in range(len(parts)):
        IDX["/".join(parts[k:])].add(p)

_src = {}


def src(rel):
    if rel not in _src:
        _src[rel] = (REPO / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    return _src[rel]


def probes(line):
    out = []
    for raw in re.findall(r"`([^`]+)`", line):
        if vc.any_anchor(raw):
            continue
        t = " ".join(raw.split())
        if len(t) < vc.TABLE_MIN_TOKEN or re.fullmatch(r"[\d\W_]+", t):
            continue
        if vc.BARE_PATH.fullmatch(t) or not vc.CODEISH.search(t):
            continue
        out.append(t)
    return out


def main():
    skip = {l.strip() for l in (STUDY / "data/r11c/slice-c-files.txt").read_text().splitlines()
            if l.strip()}
    fixed = 0
    rejected = Counter()
    per_name = Counter()
    left = []
    for f in sorted((STUDY / "notes").glob("*.md")):
        rel = f"notes/{f.name}"
        if rel in skip or f.name.startswith("r11c-"):
            continue
        raw = f.read_text(encoding="utf-8")
        lines = raw.splitlines()
        out, in_fence, n_here = [], False, 0
        for ln, line in enumerate(lines, 1):
            if FENCE.match(line):
                in_fence = not in_fence
                out.append(line)
                continue
            if in_fence or QUOTE.match(line):
                out.append(line)
                continue
            new, pos, hit = [], 0, False
            for m in WIDE.finditer(line):
                p, n = m.group("path"), int(m.group("start"))
                end = int(m.group("end") or n)
                if (REPO / p).is_file() or (STUDY / p).is_file():
                    continue
                cands = IDX.get(p, set())
                if len(cands) < 2:
                    continue                       # 第一遍的地盘
                fit = [c for c in cands if len(src(c)) >= n]
                if len(fit) != 1:
                    rejected["长度判据不唯一"] += 1
                    left.append((rel, ln, f"{p}:{n}", f"{len(fit)}/{len(cands)} 个候选够长"))
                    continue
                target = fit[0]
                toks = probes(line)
                s = src(target)
                lo, hi = max(0, n - 1 - BAND), min(len(s), max(end, n + BAND))
                bandtxt = " ".join(" ".join(x.split()) for x in s[lo:hi])
                if not toks or not any(t in bandtxt for t in toks):
                    rejected["内容判据不过"] += 1
                    left.append((rel, ln, f"{p}:{n}", f"长度可定 -> {target},但内容判据不过"))
                    continue
                new.append(line[pos:m.start("path")])
                new.append(target)
                pos = m.end("path")
                per_name[f"{p} -> {target}"] += 1
                n_here += 1
                fixed += 1
                hit = True
            out.append("".join(new) + line[pos:] if hit else line)
        if n_here and APPLY:
            f.write_text("\n".join(out) + ("\n" if raw.endswith("\n") else ""),
                         encoding="utf-8")
        if n_here:
            print(f"  {'改' if APPLY else '将改'} {n_here:>4}  {rel}")
    print(f"\n{'已改写' if APPLY else '干跑:将改写'} {fixed} 处;"
          f"点名留下 {sum(rejected.values())} 处 {dict(rejected)}")
    print("\n改写最多的 10 个串:")
    for k, v in per_name.most_common(10):
        print(f"  {v:>4}  {k}")
    (STUDY / "data/r11c/d-anchor-resolution-fix2-left.tsv").write_text(
        "file\tline\tanchor\treason\n"
        + "\n".join("\t".join(str(x) for x in r) for r in left) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
