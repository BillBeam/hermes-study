#!/usr/bin/env python3
"""R11C 片 D:对 1,603 处「根同名遮蔽」锚点做内容判定 —— 它到底指哪一个?

对每一处裸锚点 `name:N`,拿锚点所在行里锚点**之外**的反引号片段当探针
(过滤规则与 `verify_citations.py` 的 `cell_tokens` 同款),分别问:

  探针出现在 **根上那个文件** 的 [N-BAND, N+BAND] 里吗?
  探针出现在 **别处某个同名文件** 的 [N-BAND, N+BAND] 里吗?

四种判决:

  ROOT-OK      只有根上那个对上   -> 锚点没问题(裸名但指对了)
  OTHER-ONLY   只有别处那个对上   -> **锚点指错了文件**,且可给出正确候选
  BOTH         两边都对上         -> 探针不具区分力,人工
  NEITHER      两边都对不上       -> 探针不合用(或行号也漂了),人工
  NO-PROBE     行内没有可用探针   -> 给不出判据

**这是判据,不是结论**:OTHER-ONLY 才是本探针要交出来的东西,其余三档一律不动。

    python3 data/r11c/d-anchor-resolution-rootshadow-judge.py [--band 12] [--tsv 出.tsv]
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

BAND = 12
TSV = None
for i, a in enumerate(sys.argv):
    if a == "--band":
        BAND = int(sys.argv[i + 1])
    if a == "--tsv":
        TSV = Path(sys.argv[i + 1])

WIDE = re.compile(
    r"(?P<path>\.?[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?P<ext>[A-Za-z0-9]{1,6}))"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?"
)
FENCE = re.compile(r"^\s*```")


def ls(root):
    return [p for p in subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                                      text=True, check=True).stdout.split("\n") if p]


paths = ls(REPO)
root_files = {p for p in paths if "/" not in p}
by_base = defaultdict(set)
for p in paths:
    by_base[p.split("/")[-1]].add(p)
shadowed = {n for n in root_files if len(by_base[n]) > 1}

_src = {}


def src(rel):
    if rel not in _src:
        _src[rel] = (REPO / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    return _src[rel]


def band_text(rel, start, end):
    s = src(rel)
    lo, hi = max(0, start - 1 - BAND), min(len(s), max(end, start + BAND))
    return " ".join(" ".join(x.split()) for x in s[lo:hi])


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
    tally = Counter()
    rows = []
    for d in ("chapters", "notes", "reports", "reviews"):
        for f in sorted((STUDY / d).glob("*.md")):
            if f.name.startswith(("r11c-", "round-11c-")):
                continue
            in_fence = False
            for ln, line in enumerate(f.read_text(encoding="utf-8",
                                                  errors="replace").splitlines(), 1):
                if FENCE.match(line):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                for m in WIDE.finditer(line):
                    p = m.group("path")
                    if p not in shadowed:
                        continue
                    start = int(m.group("start"))
                    end = int(m.group("end") or start)
                    toks = probes(line)
                    if not toks:
                        tally["NO-PROBE"] += 1
                        continue
                    root_hit = any(t in band_text(p, start, end) for t in toks)
                    others = []
                    for cand in sorted(by_base[p] - {p}):
                        if start > len(src(cand)):
                            continue
                        if any(t in band_text(cand, start, end) for t in toks):
                            others.append(cand)
                    if root_hit and not others:
                        tally["ROOT-OK"] += 1
                    elif others and not root_hit:
                        tally["OTHER-ONLY"] += 1
                        rows.append((f"{d}/{f.name}", ln, f"{p}:{start}",
                                     ";".join(others), toks[0][:70]))
                    elif others and root_hit:
                        tally["BOTH"] += 1
                    else:
                        tally["NEITHER"] += 1
    tot = sum(tally.values())
    print(f"根同名遮蔽锚点 = {tot} 处,band=+/-{BAND}")
    for k in ("ROOT-OK", "OTHER-ONLY", "BOTH", "NEITHER", "NO-PROBE"):
        print(f"  {k:<12} {tally[k]:>5}")
    print(f"\nOTHER-ONLY(只有别处那个对得上 = 锚点指错文件)明细 {len(rows)} 条:")
    for r in rows:
        print(f"  {r[0]}:{r[1]}  {r[2]} -> {r[3]}   探针: {r[4]}")
    if TSV:
        with TSV.open("w", encoding="utf-8") as fh:
            fh.write("file\tline\tanchor\tbetter_candidates\tprobe\n")
            for r in rows:
                fh.write("\t".join(str(x) for x in r) + "\n")


if __name__ == "__main__":
    main()
