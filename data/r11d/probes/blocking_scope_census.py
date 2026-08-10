#!/usr/bin/env python3
"""R11D 片 B · 装订阻断判定的「作用半径」普查。

**这个探针只回答一个问题:某一类遗留,有多少落在 `chapters/` 里。**

R12 装订的是 `chapters/`,`notes/` / `reports/` / `reviews/` 不进正文。于是一条
遗留是否阻断装订,第一判据就是它的作用半径**与 `chapters/` 有没有交集**。
本探针把 R11C §11.1 那 15 类里**可机械度量**的几类,统一按目录切一刀。

七个读数(逐个对应底稿 §2 的某一条判定):

  [1] 不可解析锚点按目录        —— H-R11C-D-b / -D-d / -D-e 的分母
  [2] `chapters/` 内不可解析锚点逐条 —— H-R11C-D-e 的全部内容
  [3] 镜像型歧义(zh-Hans)按目录 —— H-R11C-D-b 的作用半径
  [4] 自引锚点 来源目录 × 目标目录 —— 第 16 条(R12 重排打断多少)
  [5] `chapters/` 内跨章裸文件名引用 —— 第 16 条被 [4] 漏掉的那一半
  [6] 案号:宽口径 vs 移交普查正则口径 —— 片内号能不能被普查看见
  [7] `chapters/` 的 ```verify 块数与未配对数 —— H-R11B-d 的作用半径

判据全部与既有工具同源,不另起口径:
  - 锚点正则与解析判据取自 `data/r11c/d-anchor-resolution-scan.py`(同一份 `classify`);
  - 案号正则直接从 `data/r11c/probes/handover_census_r11c.py` 读 `ID_RE`,
    所以「普查看不见多少」这个数永远跟着那个脚本走,不会因为本文件抄旧了而失真。

**测量污染(CLAUDE.md「搜过没有」两个读数)**:读数 [6] 的判据是「某案号在语料里
出现过没有」,而**本底稿自己要点名全部 16 条**。默认按前缀剔除本轮承载文件,
`--no-exclude` 给不剔除的那一个读数。**两个都要报。**

**语料默认钉在一个提交上,不读工作树(CLAUDE.md「量『之前』的命令不许钉在会移动的
引用上」)。** 本轮片 A 正在**并发改写** `reports/`(H-R11C-D-f 的锚点补全),实测同一条
命令隔十几分钟跑出两个不同的 `reports/` 读数(UNIQUE-SUFFIX 0 → 57)。所以语料一律用
`git show <rev>:<path>` 取,默认 `--rev df6d450`(R11D 开工杂项提交,片 A/B/C 的共同起点)。
`--worktree` 读工作树,只在明知没有并发写入时用。

用法(在仓库根跑,不依赖任何会话专属路径):

    python3 data/r11d/probes/blocking_scope_census.py [基线仓库] [--no-exclude]
                                                      [--rev <sha>] [--worktree]
"""
import importlib.util
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
RAW = "--no-exclude" in sys.argv
WORKTREE = "--worktree" in sys.argv
REV = "df6d450"
_skip = set()
for _i, _a in enumerate(sys.argv):
    if _a == "--rev" and _i + 1 < len(sys.argv):
        REV = sys.argv[_i + 1]
        _skip.add(_i + 1)
_pos = [a for i, a in enumerate(sys.argv)
        if i > 0 and i not in _skip and not a.startswith("-")]
REPO = Path(_pos[0] if _pos else "/home/user/hermes-agent")
CARRIER = ("r11d-raw-blocking-rulings", "round-11d-")

SELF_DIRS = ("chapters/", "notes/", "reports/", "reviews/", "scripts/", "data/")
CORPUS_DIRS = ("chapters", "notes", "reports", "reviews")

WIDE = re.compile(
    r"(?P<path>\.?[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?P<ext>[A-Za-z0-9]{1,6}))"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?"
)
FENCE = re.compile(r"^\s*```")
CHAPTER_REF = re.compile(r"chapters/[A-Za-z0-9_.-]+\.md")
WIDE_ID = re.compile(r"H-(?:[A-Za-z0-9]+-)+[a-z]\b|(?<![\w-])H-\d{1,2}(?![\w-])")
ZH_MIRROR = "website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/"


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, STUDY / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def corpus():
    if WORKTREE:
        # **不用 `git ls-files`**:它只列已跟踪文件,而「不剔除本轮」这个读数要的
        # 恰恰是**尚未 commit 的当轮底稿**。第一版用了 ls-files,于是剔除与不剔除
        # 两个读数**一字不差** —— 承载文件在两边都不在语料里,而这正是这条规矩
        # (「写一份点名清单就会改变下一次的读数」)要暴露的东西被藏起来的样子。
        out = "\n".join(
            sorted(q.relative_to(STUDY).as_posix()
                   for d in CORPUS_DIRS for q in (STUDY / d).glob("*.md")))
    else:
        out = subprocess.run(["git", "-C", str(STUDY), "ls-tree", "-r",
                              "--name-only", REV],
                             capture_output=True, text=True, check=True).stdout
    for p in sorted(x for x in out.split("\n") if x):
        if not p.endswith(".md") or p.split("/")[0] not in CORPUS_DIRS:
            continue
        if not RAW and any(c in p for c in CARRIER):
            continue
        yield p


def read(rel):
    """语料一律从钉住的那一版取,除非显式 --worktree。"""
    if WORKTREE:
        return (STUDY / rel).read_text(encoding="utf-8", errors="replace")
    r = subprocess.run(["git", "-C", str(STUDY), "show", f"{REV}:{rel}"],
                       capture_output=True, check=True)
    return r.stdout.decode("utf-8", errors="replace")


def topdir(rel):
    return rel.split("/")[0]


def main():
    scan = _load("data/r11c/d-anchor-resolution-scan.py", "r11c_scan")
    census = _load("data/r11c/probes/handover_census_r11c.py", "r11c_census")
    census_id = census.ID_RE

    unresolved = Counter()
    chapter_rows = []
    mirror = Counter()
    self_pairs = Counter()
    scripts_owner = Counter()
    ids_wide, ids_seen = Counter(), Counter()

    base_idx = scan.BASE_IDX

    for rel in corpus():
        text = read(rel)
        d = topdir(rel)
        for m in WIDE_ID.findall(text):
            ids_wide[m] += 1
        for m in census_id.findall(text):
            ids_seen[m] += 1
        in_fence = False
        for ln, line in enumerate(text.split("\n"), 1):
            if FENCE.match(line):
                in_fence = not in_fence
            for m in WIDE.finditer(line):
                path, start = m.group("path"), int(m.group("start"))
                prev = line[m.start() - 1] if m.start() else ""
                kind, detail = scan.classify(path, start, prev)
                if kind in ("AMBIGUOUS", "UNIQUE-SUFFIX", "NOT-IN-TREE", "ABSPATH"):
                    unresolved[f"{d}|{kind}"] += 1
                    if d == "chapters":
                        chapter_rows.append((rel, ln, path, start, kind, detail))
                cands = base_idx.get(path, set())
                if len(cands) == 2 and any(c.startswith(ZH_MIRROR) for c in cands):
                    mirror[d] += 1
                # 自引:围栏块内不计(与 self_citation_census.py 同口径)
                if not in_fence and any(path.startswith(s) for s in SELF_DIRS):
                    self_pairs[f"{d}|{topdir(path)}"] += 1
                    # `scripts/` 是**两棵树都有**的顶层目录(基线 73 个文件),
                    # 于是「按前缀判自引」会把 `scripts/run_tests.sh:12` 这类
                    # **基线锚点**算进自引。单列出来,不然 615 这个数是虚的。
                    if path.startswith("scripts/"):
                        in_study = (STUDY / path).is_file()
                        in_base = (REPO / path).is_file()
                        owner = ("两边都有" if in_study and in_base else
                                 "只本仓库有" if in_study else
                                 "只基线有" if in_base else "两边都没有")
                        scripts_owner[owner] += 1

    print(f"语料:{'工作树' if WORKTREE else '钉在 ' + REV};"
          f"{'不剔除本轮承载文件(--no-exclude)' if RAW else '已剔除本轮承载文件'}")
    print("\n[1] 不可解析锚点按目录(AMBIGUOUS/UNIQUE-SUFFIX/NOT-IN-TREE/ABSPATH)")
    per_dir = Counter()
    for k, v in unresolved.items():
        per_dir[k.split("|")[0]] += v
    for d in ("chapters", "notes", "reports", "reviews"):
        print(f"  {d:10s} {per_dir[d]:5d}")

    print(f"\n[2] chapters/ 内不可解析锚点逐条({len(chapter_rows)} 处)")
    for rel, ln, path, start, kind, detail in chapter_rows:
        print(f"  {rel}:{ln}\t{path}:{start}\t{kind}\t{detail}")

    print("\n[3] 镜像型歧义(候选恰为 website/docs + zh-Hans 两份)按目录")
    for d in ("chapters", "notes", "reports", "reviews"):
        print(f"  {d:10s} {mirror[d]:5d}")

    print("\n[4] 自引锚点  来源目录 -> 被指向目录")
    tgt = Counter()
    for k, v in self_pairs.items():
        tgt[k.split("|")[1]] += v
    print("  被指向合计:", dict(sorted(tgt.items())), " 总计", sum(tgt.values()))
    print("  指向 chapters/ 的,按来源:",
          {k.split("|")[0]: v for k, v in sorted(self_pairs.items())
           if k.endswith("|chapters")})
    print("  来源是 chapters/ 的,按目标:",
          {k.split("|")[1]: v for k, v in sorted(self_pairs.items())
           if k.startswith("chapters|")})
    print("  其中以 scripts/ 开头的,按归属:", dict(sorted(scripts_owner.items())))
    print("  扣掉只在基线里的 scripts/ 后,真自引 =",
          sum(self_pairs.values()) - scripts_owner["只基线有"])

    xref = Counter()
    for rel in corpus():
        if topdir(rel) != "chapters":
            continue
        for m in CHAPTER_REF.finditer(read(rel)):
            if m.group(0) != rel:
                xref[m.group(0)] += 1
    print(f"\n[5] chapters/ 内跨章裸文件名引用(不带行号):{sum(xref.values())} 处 / "
          f"{len(xref)} 个被引文件")

    blind = {k: v for k, v in ids_wide.items() if k not in ids_seen}
    print(f"\n[6] 案号:宽口径不同号 {len(ids_wide)};移交普查正则可见 {len(ids_seen)};"
          f"看不见 {len(blind)} 个不同号 / {sum(blind.values())} 次出现")

    vb = defaultdict(int)
    for rel in corpus():
        if topdir(rel) != "chapters":
            continue
        for line in read(rel).split("\n"):
            if line.startswith("```verify"):
                vb[rel] += 1
    print(f"\n[7] chapters/ 的 ```verify 块:{sum(vb.values())} 个,分布 {dict(vb)}")


if __name__ == "__main__":
    main()
