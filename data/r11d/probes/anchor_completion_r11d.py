#!/usr/bin/env python3
"""R11D 片 A:按 R11D 裁定,把 `reports/` 与 `reviews/` 里「基线唯一候选」的裸文件名锚点补全。

裁定见 CLAUDE.md「锚点寻址修正是第四类改动」:一条锚点由**它指向谁**(结论)与
**怎么写出这个地址**(寻址)两部分组成;补全只动后者,与「行号漂移」同型,故与它同级。

判据只有一条(别的一概不猜):基线 863e313 里**恰好一个**文件的路径以这个串结尾
(按目录边界匹配)。`run.py` -> `gateway/run.py` 走这条;`__init__.py`(171 个候选)、
`base.py`(9 个)一律不动 —— 猜错比不修更糟,一个指向错文件的锚点看起来完全正常。

**两处绝不改写**,因为改了就是在伪造证据(与 R11C 片 D 同一口径,也是
`verify_citations.py` 自己跳过的两处):

  - 围栏块 ``` **内部**:契约是逐字源码摘录,改它 = 让摘录与基线不符(BLOCK-DRIFT);
    ```verify 块里改写命令更会让它跑出别的输出。
  - 引用块 `>` **内部**:可能是逐字文档摘录,同理。

写入范围按裁定分两档:

  - `reports/`  —— 就地补全(`--apply` 才落盘),每一处由调用方在该报告文末勘误节点名;
  - `reviews/`  —— **一个字都不改**,只出对照表(`--scope reviews` 永远不落盘)。

「基线唯一」之外还有一类:**只在本仓库(hermes-study)里唯一**的裸文件名
(如 `verify_citations.py` -> `scripts/verify_citations.py`)。本脚本**只报不改**:
裁定给的判据写的是基线,而自引锚点另有「commit 钉子」那条规矩管着(浮在一棵会动的树上),
两件事不该在同一次改动里混做。

用法:

    python3 data/r11d/probes/anchor_completion_r11d.py                      # 干跑两档,报数
    python3 data/r11d/probes/anchor_completion_r11d.py --scope reports --apply
    python3 data/r11d/probes/anchor_completion_r11d.py --tsv data/r11d/anchor-completion.tsv
"""
import argparse
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
REPO = Path("/home/user/hermes-agent")
APPLIED_TSV = "data/r11d/anchor-completion-applied.tsv"

# 与 R11C 片 D 同一条宽正则:先宽匹配,再靠 unique_target() 收紧。
WIDE = re.compile(
    r"(?P<path>\.?[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?P<ext>[A-Za-z0-9]{1,6}))"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?"
)
FENCE = re.compile(r"^\s*```")
QUOTE = re.compile(r"^\s*>")

# 严格围栏:整行只有反引号 + 可选语言标记。`verify_citations.py` 用的是上面那条**宽**正则
# (`^\s*```),于是一句缩进散文里提到 ```` ```mermaid ```` 也会被当成围栏行、**翻转其后整份
# 文件的奇偶**。本脚本改写范围必须与关卡一致(所以照抄宽正则),但落盘前用这条严格正则做负控:
# 断言每一处待改写的位置在**严格口径**下也确实不在围栏里 —— 宽口径漏判会少改(安全),
# 误判才会改到摘录里(伪造证据),而这条断言正是拦后者的。
STRICT_FENCE = re.compile(r"^\s{0,3}(?P<ticks>`{3,})\s*[A-Za-z0-9_+-]*\s*$")


def ls(root: Path):
    out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                         text=True, check=True).stdout
    return [p for p in out.split("\n") if p]


def suffix_index(paths):
    """path -> 所有「按目录边界以它结尾」的全路径。'run.py' 命中 'gateway/run.py'。"""
    idx = defaultdict(set)
    for p in paths:
        parts = p.split("/")
        for k in range(len(parts)):
            idx["/".join(parts[k:])].add(p)
    return idx


BASE_IDX = suffix_index(ls(REPO))
STUDY_IDX = suffix_index(ls(STUDY))
_LEN = {}


def flen(root: Path, rel: str) -> int:
    key = str(root / rel)
    if key not in _LEN:
        try:
            _LEN[key] = len((root / rel).read_text(encoding="utf-8",
                                                   errors="replace").splitlines())
        except OSError:
            _LEN[key] = -1
    return _LEN[key]


def classify(path: str, start: int):
    """返回 (类别, 目标全路径或说明)。类别:
       RESOLVED      已能从仓库根解析,不动
       BASELINE-ONE  基线唯一候选 —— 可机械补全
       STUDY-ONE     只在本仓库唯一 —— 只报不改
       AMBIGUOUS     多候选,一律不动
       OUT-OF-RANGE  唯一候选但行号越界 —— 候选存疑,交人工
       NOT-IN-TREE   两棵树都找不到
    """
    if (REPO / path).is_file() or (STUDY / path).is_file():
        return "RESOLVED", path
    for idx, root, tag in ((BASE_IDX, REPO, "BASELINE"), (STUDY_IDX, STUDY, "STUDY")):
        c = idx.get(path, set())
        if len(c) > 1:
            return "AMBIGUOUS", f"{len(c)} 个候选({tag})"
        if len(c) == 1:
            only = next(iter(c))
            n = flen(root, only)
            if n < 0 or start > n:
                return "OUT-OF-RANGE", f"{only} 只有 {n} 行,锚点 :{start}"
            return f"{tag}-ONE", only
    return "NOT-IN-TREE", ""


def read_at(rev, rel):
    """rev 为 None 读工作树,否则读该提交那一版 —— 让「改之前是多少」可复现。"""
    if rev is None:
        return (STUDY / rel).read_text(encoding="utf-8")
    r = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=STUDY,
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def list_at(rev, d):
    if rev is None:
        return [f"{d}/{f.name}" for f in sorted((STUDY / d).glob("*.md"))]
    out = subprocess.run(["git", "ls-tree", "--name-only", f"{rev}:{d}"], cwd=STUDY,
                         capture_output=True, text=True, check=True).stdout
    return sorted(f"{d}/{n}" for n in out.split("\n") if n.endswith(".md"))


# 本轮的**承载清单**:勘误节与附录本身就要逐字列出那些坏锚点,于是普查会再数到它们。
# CLAUDE.md「『搜过没有』类测量必须报两个读数」正是为这种不幂等的测量立的:
# 写一份点名清单就会改变下一次的读数,而没有任何脚本会发现这种污染。
CARRIER_FILE = "reviews/review-1-anchor-corrections.md"
CARRIER_HEAD = "## 勘误(R11D:锚点寻址补全)"


def scan(rel: str, rev=None, drop_carrier: bool = False):
    """产出 (行号, 类别, 原串, 目标, 是否在块内)。块内的一律不改,但要计数。"""
    text = read_at(rev, rel)
    if text is None:
        return
    if drop_carrier:
        if rel == CARRIER_FILE:
            return
        text = text.split(CARRIER_HEAD)[0]
    lines = text.splitlines()
    in_fence = False
    for ln, line in enumerate(lines, 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        blocked = in_fence or bool(QUOTE.match(line))
        for m in WIDE.finditer(line):
            kind, target = classify(m.group("path"), int(m.group("start")))
            yield ln, kind, f'{m.group("path")}:{m.group("start")}', target, blocked


def rewrite(rel: str, apply: bool):
    """只改 BASELINE-ONE 且不在块内的。返回 [(行号, 原锚点, 新锚点)]。"""
    raw = (STUDY / rel).read_text(encoding="utf-8")
    lines = raw.splitlines()
    in_fence = False
    out, hits = [], []
    for ln, line in enumerate(lines, 1):
        if FENCE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence or QUOTE.match(line):
            out.append(line)
            continue
        buf, pos, touched = [], 0, False
        for m in WIDE.finditer(line):
            kind, target = classify(m.group("path"), int(m.group("start")))
            if kind != "BASELINE-ONE":
                continue
            buf.append(line[pos:m.start("path")])
            buf.append(target)
            pos = m.end("path")
            touched = True
            span = m.group(0)[len(m.group("path")):]
            hits.append((ln, m.group("path") + span, target + span))
        out.append("".join(buf) + line[pos:] if touched else line)
    if hits and apply:
        (STUDY / rel).write_text("\n".join(out) + ("\n" if raw.endswith("\n") else ""),
                                 encoding="utf-8")
    return hits


def strict_fenced(rel: str):
    """严格口径下位于围栏内部的行号集合。"""
    lines = (STUDY / rel).read_text(encoding="utf-8").splitlines()
    inside, opener, out = False, None, set()
    for ln, line in enumerate(lines, 1):
        m = STRICT_FENCE.match(line)
        if m and not inside:
            inside, opener = True, len(m.group("ticks"))
            continue
        if m and inside and len(m.group("ticks")) >= opener:
            inside = False
            continue
        if inside:
            out.add(ln)
    return out, inside


def audit_fences(dirs):
    """负控:待改写位置在严格口径下也必须在围栏外;并点名两种口径分歧的来源行。"""
    bad, flips = [], []
    for d in dirs:
        for f in sorted((STUDY / d).glob("*.md")):
            rel = f"{d}/{f.name}"
            strict, unclosed = strict_fenced(rel)
            for ln, old, _new in rewrite(rel, False):
                if ln in strict:
                    bad.append((rel, ln, old))
            lines = f.read_text(encoding="utf-8").splitlines()
            for ln, line in enumerate(lines, 1):
                if FENCE.match(line) and not STRICT_FENCE.match(line):
                    flips.append((rel, ln, line.strip()[:60]))
            if unclosed:
                flips.append((rel, 0, "严格口径下文件以未闭合围栏结尾"))
    print("== 负控:待改写位置 vs 严格围栏口径 ==")
    print(f"  落在严格围栏内部的待改写位置:{len(bad)}  (必须为 0)")
    for r in bad:
        print("   ", r)
    print(f"  两种口径分歧的围栏行(宽口径认、严格口径不认):{len(flips)}")
    # 只打位置不打原文:原文含三反引号,贴进 ```text 配对块会把块截断。
    for rel, ln, _text in flips:
        print(f"    {rel}:{ln}")
    return len(bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["reports", "reviews", "both"], default="both")
    ap.add_argument("--apply", action="store_true",
                    help="仅对 reports/ 生效;reviews/ 按裁定原文不改")
    ap.add_argument("--tsv", help="把逐条普查写到这个 TSV")
    ap.add_argument("--audit-fences", action="store_true", help="只跑围栏负控")
    ap.add_argument("--rev", help="普查读该提交那一版而不是工作树(--apply 永远只动工作树)")
    ap.add_argument("--drop-carrier", action="store_true",
                    help="普查剔除本轮承载清单(勘误节 + 附录),报第二个读数")
    ap.add_argument("--census-only", action="store_true",
                    help="只打普查小结(输出短、可钉进 ```verify/```text 配对)")
    args = ap.parse_args()

    dirs = ["reports", "reviews"] if args.scope == "both" else [args.scope]
    if args.audit_fences:
        raise SystemExit(1 if audit_fences(dirs) else 0)
    if args.apply and audit_fences(dirs):
        raise SystemExit("负控未过,拒绝落盘")
    rows, tally = [], Counter()
    for d in dirs:
        for rel in list_at(args.rev, d):
            for ln, kind, cite, target, blocked in scan(rel, args.rev,
                                                        args.drop_carrier):
                if kind == "RESOLVED":
                    continue
                tag = kind + ("+IN-BLOCK" if blocked else "")
                tally[(d, tag)] += 1
                rows.append((rel, ln, cite, tag, target))

    print(f"== 普查(RESOLVED 不计;树={args.rev or '工作树'};"
          f"承载清单{'已剔除' if args.drop_carrier else '未剔除'}) ==")
    for (d, k), v in sorted(tally.items(), key=lambda kv: (kv[0][0], -kv[1])):
        print(f"  {d:<8} {v:>4}  {k}")

    if args.census_only:
        return

    applied = []
    for d in dirs:
        apply = args.apply and d == "reports"
        total, files = 0, 0
        print(f"\n== {d}/ {'落盘补全' if apply else '干跑'} ==")
        for f in sorted((STUDY / d).glob("*.md")):
            rel = f"{d}/{f.name}"
            hits = rewrite(rel, apply)
            if hits:
                files += 1
                total += len(hits)
                print(f"  {len(hits):>3}  {rel}")
                for ln, old, new in hits:
                    print(f"        :{ln}  {old}  ->  {new}")
                    if apply:
                        applied.append((rel, ln, old, new))
        print(f"  小计:{total} 处 / {files} 份")

    if applied:
        # 落盘明细供人工写勘误节用。**勘误节由人写不由脚本贴**:每份报告的勘误节要说的
        # 是「这一处为什么算寻址修正而不是改结论」,那是判断,不是模板填空。
        p = STUDY / APPLIED_TSV
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("file\tline\told\tnew\n"
                     + "\n".join("\t".join(str(x) for x in r) for r in applied) + "\n",
                     encoding="utf-8")
        print(f"\n改写明细 -> {APPLIED_TSV}({len(applied)} 行)")

    if args.tsv:
        p = STUDY / args.tsv
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("file\tline\tcitation\tclass\ttarget\n"
                     + "\n".join("\t".join(str(x) for x in r) for r in rows) + "\n",
                     encoding="utf-8")
        print(f"\n普查明细 -> {args.tsv}({len(rows)} 行)")


if __name__ == "__main__":
    main()
