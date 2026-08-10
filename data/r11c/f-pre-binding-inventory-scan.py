#!/usr/bin/env python3
"""R11C 片 F 探针:装订前状态盘点(只读,不改任何文件)。

用法(在 /home/user/hermes-study 下):

    python3 data/r11c/f-pre-binding-inventory-scan.py [--repo /home/user/hermes-agent]

产出三张表 + 一份文本:

  data/r11c/f-pre-binding-inventory-chapters.tsv  成品章清单(文件/轮次/行数/标题/结构计数)
  data/r11c/f-pre-binding-inventory-overlap.tsv   跨章锚点重叠簇(机械候选,需人工裁决)
  data/r11c/f-pre-binding-inventory-numbering.tsv 全语料「第 N 章」声明位置(重号/跳号审计)
  data/r11c/f-pre-binding-inventory-staleness.txt 成品章被后续轮次点名 + 改判语的位置

三个判据都写死在本文件里,重跑即复现:

  * 锚点:直接 import `scripts/verify_citations.py` 的 `citations()`,与关卡同一套正则,
    不另起炉灶(否则两边口径会漂)。
  * 重叠簇:同一基线源文件、行号相距 <= WINDOW(默认 30,沿用 R11B 定案去重的窗口)
    且被 >= 2 章引用 —— 这只是**候选**,不是判决。同文件邻近处的不同断言必然混在里面,
    要逐簇读正文再判(与 R11B 合并规则第 5 条同源)。
  * 陈旧:后续轮次的 reports/ 与 notes/ 里,某成品章文件名出现处 ±CTX 行内带改判语。

注意:本脚本不写任何会话专属路径,输出里的路径一律相对仓库根。
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[2]
WINDOW = 30          # 同源文件内两个锚点算「同一处代码」的行距上限
CTX = 3              # 陈旧扫描:章名出现处上下文行数

# 章的规范顺序 = 轮次推进顺序。这不是本脚本发明的:它与
# reports/round-9d-l1-completion.md §8.2 那张 17 章表逐行一致,
# 后面 4 章按各自 PR 描述里的章号续排。
CHAPTER_ORDER = [
    "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r7b", "r7c", "r8a", "r8b",
    "r8c", "r8d", "r9a", "r9b", "r9c", "r9d", "r10", "r10b", "r11a", "r11b",
]

# 轮次的时间序(用于「后续轮次」判定)。含没有成品章的轮次。
ROUND_SEQ = [
    "1", "2", "3", "4", "5", "6", "7", "7b", "7c", "8a", "8-fix", "8b",
    "8c", "8d", "9a", "9b", "9c", "9d", "10", "10b", "11a", "11b", "11c",
]
ROUND_RANK = {r: i for i, r in enumerate(ROUND_SEQ)}

REVISION_WORDS = [
    "改判", "推翻", "撤回", "收回", "更正", "订正", "勘误", "证伪",
    "不成立", "原判", "已改为", "应读作", "实为", "有误", "写错",
]
REVISION_RE = re.compile("|".join(REVISION_WORDS))

CN_NUM = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
    "九": 9, "十": 10,
}
# 允许「第 7 章」这种带空格的写法。R11C 片 F 实测:不允许空格时,
# chapters/r7c-gateway-periphery-and-scheduling.md 里 4 处「第 7 章」全部漏掉,
# 而那正是唯一一处**成品章之间互相引用章号**的地方 —— 章号审计最该看的位置。
CHAPTER_NUM_RE = re.compile(r"第\s*([一二三四五六七八九十百零〇0-9]+)\s*章")

FENCE_LINE = re.compile(r"^\s*```")

# 片 F 自身的承载文件:章号/点名类测量对「报告它」这个动作不幂等
# (CLAUDE.md「搜过没有类测量必须报两个读数」)。派工书本身也点了两个章号。
F_CARRIERS = {
    "notes/r11c-raw-pre-binding-inventory.md",
    "data/r11c/dispatch-brief.md",
}


def is_f_carrier(rel: str) -> bool:
    return rel in F_CARRIERS or rel.startswith("data/r11c/f-pre-binding-inventory")


def cn_to_int(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + CN_NUM.get(s[1:], 0)
    if "十" in s:
        head, _, tail = s.partition("十")
        base = CN_NUM.get(head)
        if base is None:
            return None
        return base * 10 + (CN_NUM.get(tail, 0) if tail else 0)
    return CN_NUM.get(s)


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "vc", STUDY / "scripts" / "verify_citations.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def chapter_round(name: str) -> str:
    return re.match(r"(r[0-9]+[a-d]?)-", name).group(1)


def round_of_path(path: str) -> str | None:
    """把 reports/notes 的文件名映射到轮次标识(去掉 `r` 前缀,与 ROUND_SEQ 同形)。"""
    base = Path(path).name
    m = re.match(r"round-([0-9]+[a-z]*(?:-fix)?)-", base)
    if m:
        tag = m.group(1)
        return tag if tag in ROUND_RANK else tag.split("-")[0]
    m = re.match(r"r([0-9]+[a-d]?)[-.]", base)
    if m:
        return m.group(1)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="/home/user/hermes-agent")
    args = ap.parse_args()
    repo = Path(args.repo)
    vc = load_verifier()

    def resolve(p: str) -> Path:
        return repo / p

    out_dir = STUDY / "data" / "r11c"
    chapters = sorted((STUDY / "chapters").glob("*.md"))

    def outside_fences(text: str):
        """(行号, 行文),跳过围栏块内部 —— 与关卡 `check_note` 同口径。

        判据 A 第一版没有这一步,于是**摘录块里的 `路径:行号`** 也被当成本章的锚点。
        r9c 那段 grep 输出(```text 块里的 `./agent/file_safety.py:50:` 等 10 行)
        因此凭空造出多个「跨章重叠」。关卡本身早就跳过围栏
        (`scripts/verify_citations.py:667` 起的 FENCE 分支),判据 A 也必须跳。
        """
        inside = False
        for i, ln in enumerate(text.splitlines(), 1):
            if FENCE_LINE.match(ln):
                inside = not inside
                continue
            if not inside:
                yield i, ln

    def chapter_anchors(text: str):
        """本章正文(非围栏内)的全部锚点:(源文件, 源行号, 章内行号)。"""
        for i, ln in outside_fences(text):
            for m in vc.citations(ln, resolve):
                yield m.group("path"), int(m.group("start")), i

    # ---------------- 1. 成品章清单 ----------------
    rows = []
    anchors_by_chapter: dict[str, list[tuple[str, int]]] = {}
    for ch in chapters:
        text = ch.read_text(encoding="utf-8")
        lines = text.splitlines()
        rnd = chapter_round(ch.name)
        title = lines[0].lstrip("# ").strip() if lines else ""
        h2 = sum(1 for ln in lines if ln.startswith("## "))
        h3 = sum(1 for ln in lines if ln.startswith("### "))
        fences = sum(1 for ln in lines if ln.startswith("```"))
        mermaid = sum(1 for ln in lines if ln.startswith("```mermaid"))
        cites = list(chapter_anchors(text))
        anchors_by_chapter[ch.name] = [(pth, ln) for pth, ln, _ in cites]
        srcfiles = {pth for pth, _, _ in cites}
        pos = CHAPTER_ORDER.index(rnd) + 1 if rnd in CHAPTER_ORDER else 0
        rows.append([
            str(pos), ch.name, rnd, str(len(lines)), str(h2), str(h3),
            str(fences // 2), str(mermaid), str(len(cites)), str(len(srcfiles)),
            title,
        ])
    rows.sort(key=lambda r: int(r[0]))
    p = out_dir / "f-pre-binding-inventory-chapters.tsv"
    p.write_text(
        "pos\tfile\tround\tlines\th2\th3\tcode_blocks\tmermaid\tcitations"
        "\tdistinct_src_files\ttitle\n"
        + "".join("\t".join(r) + "\n" for r in rows),
        encoding="utf-8",
    )
    print(f"[1] chapters -> {p.relative_to(STUDY)}  ({len(rows)} 章)")

    # ---------------- 2. 跨章锚点重叠簇 ----------------
    by_src: dict[str, list[tuple[int, str]]] = {}
    for name, anchors in anchors_by_chapter.items():
        for src, line in anchors:
            by_src.setdefault(src, []).append((line, name))
    ch_line_of = {}
    for ch in chapters:
        for pth, sline, lineno in chapter_anchors(
                (STUDY / "chapters" / ch.name).read_text(encoding="utf-8")):
            ch_line_of.setdefault((ch.name, pth, sline), lineno)
    clusters = []
    for src, entries in by_src.items():
        entries.sort()
        cur: list[tuple[int, str]] = []
        for line, name in entries:
            if cur and line - cur[-1][0] > WINDOW:
                clusters.append((src, cur))
                cur = []
            cur.append((line, name))
        if cur:
            clusters.append((src, cur))
    multi = []
    for src, entries in clusters:
        chs = sorted({n for _, n in entries})
        if len(chs) >= 2:
            lo, hi = entries[0][0], entries[-1][0]
            multi.append([
                src, f"{lo}-{hi}", str(len(chs)), ",".join(chs),
                ";".join(
                    f"{n}#{ch_line_of.get((n, src, l), 0)}->{src}:{l}"
                    for l, n in entries),
            ])
    multi.sort(key=lambda r: (-int(r[2]), r[0]))
    p = out_dir / "f-pre-binding-inventory-overlap.tsv"
    p.write_text(
        "src_file\tline_span\tn_chapters\tchapters\thits\n"
        + "".join("\t".join(r) + "\n" for r in multi),
        encoding="utf-8",
    )
    print(f"[2] overlap  -> {p.relative_to(STUDY)}  ({len(multi)} 簇跨 >=2 章)")

    # ---------------- 3. 章号声明审计 ----------------
    #
    # 章号从来没有一个权威落点:它散在 §8.2 那张 17 章表、各轮报告、
    # **以及 git 提交信息(= PR 描述)** 里。所以三处都要扫,否则审计出来的
    # 「跳号」大半是「声明在别处」。
    scan_dirs = ["chapters", "reports", "notes", "reviews", "data", "scripts"]
    decl = []
    for d in scan_dirs:
        for f in sorted((STUDY / d).rglob("*.md")) + sorted((STUDY / d).rglob("*.py")):
            rel = f.relative_to(STUDY).as_posix()
            for i, ln in enumerate(f.read_text(encoding="utf-8", errors="replace")
                                   .splitlines(), 1):
                for m in CHAPTER_NUM_RE.finditer(ln):
                    n = cn_to_int(m.group(1))
                    decl.append([
                        str(n) if n else "?", m.group(0), f"{rel}:{i}",
                        "carrier" if is_f_carrier(rel) else d,
                        ln.strip()[:160],
                    ])
    # git 提交信息(PR 描述的落点)
    import subprocess
    log = subprocess.run(
        ["git", "log", "--all", "--format=%x01%h%x02%s%n%b"],
        cwd=STUDY, capture_output=True, text=True, check=True,
    ).stdout
    for entry in log.split("\x01"):
        if not entry.strip():
            continue
        sha, _, body = entry.partition("\x02")
        for ln in body.splitlines():
            for m in CHAPTER_NUM_RE.finditer(ln):
                n = cn_to_int(m.group(1))
                decl.append([
                    str(n) if n else "?", m.group(0), f"git:{sha.strip()}",
                    "gitlog", ln.strip()[:160],
                ])
    decl.sort(key=lambda r: (int(r[0]) if r[0].isdigit() else 999, r[2]))
    p = out_dir / "f-pre-binding-inventory-numbering.tsv"
    p.write_text(
        "num\tliteral\twhere\tcorpus\tline\n"
        + "".join("\t".join(r) + "\n" for r in decl),
        encoding="utf-8",
    )
    n_carrier = sum(1 for r in decl if r[3] == "carrier")
    print(f"[3] numbering-> {p.relative_to(STUDY)}  ({len(decl)} 处「第 N 章」"
          f",其中片 F 承载文件贡献 {n_carrier} 处;剔除后 {len(decl) - n_carrier} 处)")

    # ---------------- 4. 陈旧扫描:两条互相独立的线索 ----------------
    #
    # 线索甲(点名法):后续轮次的 reports/notes 里**直接写出成品章文件名**、
    #   且上下文 ±CTX 行带改判语。命中率高但覆盖窄 —— 后轮改判前轮结论时
    #   往往只谈机制、不点名章。
    # 线索乙(锚点法):成品章引用了某个基线位置,后续轮次在**同一位置 ±WINDOW 行**
    #   也有引用,且那一处上下文带改判语。它不依赖后轮是否想起了这一章。
    out = []
    targets = {ch.name: chapter_round(ch.name).lstrip("r") for ch in chapters}
    later_files = []
    for d in ("reports", "notes"):
        for f in sorted((STUDY / d).glob("*.md")):
            rel = f.relative_to(STUDY).as_posix()
            later_files.append((rel, round_of_path(rel),
                                f.read_text(encoding="utf-8", errors="replace")))

    for rel, src_round, text in later_files:
        src_rank = ROUND_RANK.get(src_round, -1)
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            for chname, chrnd in targets.items():
                if chname not in ln:
                    continue
                if src_rank <= ROUND_RANK.get(chrnd, 999):
                    continue
                lo, hi = max(0, i - CTX), min(len(lines), i + CTX + 1)
                ctx = "\n".join(lines[lo:hi])
                if REVISION_RE.search(ctx):
                    out.append(
                        f"=== [甲/点名] {chname}  <-  {rel}:{i + 1}"
                        f"  (轮次 {src_round} > {chrnd})\n{ctx}\n"
                    )

    # 线索乙
    ch_anchor_index: dict[str, list[tuple[int, str, int]]] = {}
    for ch in chapters:
        for pth, sline, lineno in chapter_anchors(
                (STUDY / "chapters" / ch.name).read_text(encoding="utf-8")):
            ch_anchor_index.setdefault(pth, []).append((sline, ch.name, lineno))
    seen = set()
    for rel, src_round, text in later_files:
        src_rank = ROUND_RANK.get(src_round, -1)
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            hits = [m for m in vc.citations(ln, resolve)
                    if m.group("path") in ch_anchor_index]
            if not hits:
                continue
            lo, hi = max(0, i - CTX), min(len(lines), i + CTX + 1)
            ctx = "\n".join(lines[lo:hi])
            if not REVISION_RE.search(ctx):
                continue
            for m in hits:
                src, start = m.group("path"), int(m.group("start"))
                for cstart, chname, chline in ch_anchor_index[src]:
                    if abs(cstart - start) > WINDOW:
                        continue
                    if src_rank <= ROUND_RANK.get(targets[chname], 999):
                        continue
                    key = (chname, chline, rel, i)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(
                        f"=== [乙/锚点] chapters/{chname}:{chline}"
                        f" 引 {src}:{cstart}  <-  {rel}:{i + 1} 引 {src}:{start}"
                        f"  (轮次 {src_round} > {targets[chname]})\n{ctx}\n"
                    )
    p = out_dir / "f-pre-binding-inventory-staleness.txt"
    p.write_text("\n".join(out), encoding="utf-8")
    print(f"[4] staleness-> {p.relative_to(STUDY)}  ({len(out)} 处命中)")

    # ---------------- 5. 数量断言的跨轮对表 ----------------
    #
    # 「五个读取函数」被 R8B 更正为六个,是本项目已知的成品章陈旧形态。
    # 它可以机械地找:成品章里的「<反引号符号> … N 个」与**后续轮次**语料里
    # 同一符号旁的另一个数并列出来。命中是**候选**,不是判决 —— 同一个符号
    # 在不同语境下本来就可以有不同的计数(条目数 vs 调用点数),要逐条读。
    num_re = re.compile(r"(\d+)\s*(个|条|处|种|份|层|道|次|张|项|棵|片|把|例)")
    cn_units = "个条处种份层道次张项棵片把例"
    cn_small = "一二三四五六七八九十两"
    cn_num_re = re.compile(f"([{cn_small}]+)\\s*([{cn_units}])")
    tick = re.compile(r"`([A-Za-z_][A-Za-z0-9_./]{3,})`")

    def claims(text: str):
        """产出 (符号, 数字, 量词, 行号, 行文)。符号取同一行最近的反引号标识符。"""
        for i, ln in enumerate(text.splitlines(), 1):
            syms = tick.findall(ln)
            if not syms:
                continue
            for m in num_re.finditer(ln):
                for s in syms:
                    yield s, m.group(1), m.group(2), i, ln.strip()
            for m in cn_num_re.finditer(ln):
                v = cn_to_int(m.group(1).replace("两", "二"))
                if v is None:
                    continue
                for s in syms:
                    yield s, str(v), m.group(2), i, ln.strip()

    ch_claims: dict[tuple[str, str], list] = {}
    for ch in chapters:
        rnd = chapter_round(ch.name).lstrip("r")
        for s, n, u, i, ln in claims(ch.read_text(encoding="utf-8")):
            ch_claims.setdefault((s, u), []).append((ch.name, rnd, n, i, ln))
    rows = []
    for rel, src_round, text in later_files:
        src_rank = ROUND_RANK.get(src_round, -1)
        for s, n, u, i, ln in claims(text):
            for chname, chrnd, cn, ci, cln in ch_claims.get((s, u), []):
                if cn == n or src_rank <= ROUND_RANK.get(chrnd, 999):
                    continue
                rows.append([
                    s, u, f"chapters/{chname}:{ci}", cn, f"{rel}:{i}", n,
                    cln[:120], ln[:120],
                ])
    seen_rows = set()
    uniq = []
    for r in rows:
        k = (r[0], r[1], r[2], r[4])
        if k in seen_rows:
            continue
        seen_rows.add(k)
        uniq.append(r)
    p = out_dir / "f-pre-binding-inventory-numeric.tsv"
    p.write_text(
        "symbol\tunit\tchapter_at\tchapter_n\tlater_at\tlater_n"
        "\tchapter_line\tlater_line\n"
        + "".join("\t".join(r) + "\n" for r in uniq),
        encoding="utf-8",
    )
    print(f"[5] numeric  -> {p.relative_to(STUDY)}  ({len(uniq)} 对候选)")

    # ---------------- 6. 跨章重复的另外三条判据 ----------------
    #
    # 判据 A(§2 的 overlap 表)只抓「同一处代码被两章各引一次」。它抓不到
    # 三种同样要在 R12 合并的重复,所以另立三条,各自单独出表、各自可重跑:
    #
    #   B 术语重复锚定 —— 成品章硬标准 1 要求每章首次出现的术语给一句话解释,
    #     而硬标准 6 要求每章独立可读,于是**同一个术语被 N 章各锚定一次是制度
    #     的必然产物**,不是谁写错了。R12 装订成一本书时它就变成重复。
    #     判据:同一术语在 ≥2 章里各自出现在一行「术语 + 解释标记」的句子里。
    #   C 事故重复讲述 —— 硬标准 4 要求真实 issue 讲成故事。同一个 issue 编号
    #     出现在 ≥2 章 = 同一件事被讲了两遍。
    #   D 定案重复 —— 同一个基线**文件**上的 ▲/◇/■/◎ 定案出现在 ≥2 章的
    #     「§5 地图与代码的出入」里。比判据 A 宽(不要求行号相近),
    #     因为一条定案的作用域常常是整个文件。
    #
    # 三条都只产出**候选**。判据 A 的经验(同文件邻近处的不同断言必然混进来)
    # 在这里同样成立,逐条读正文才是判决。
    def strip_fences(text: str):
        """产出 (行号, 行文),跳过围栏块内部。"""
        inside = False
        for i, ln in enumerate(text.splitlines(), 1):
            if ln.lstrip().startswith("```"):
                inside = not inside
                continue
            if not inside:
                yield i, ln

    ch_text = {ch.name: ch.read_text(encoding="utf-8") for ch in chapters}

    # --- B 术语重复锚定 ---
    #
    # 解释标记只看**同一行 + 下一行**:硬标准 1 要的是「首次出现给一句话解释」,
    # 那句解释在排版上要么与术语同行、要么紧跟一行。窗口再放宽就会把
    # 「这一段里恰好提到过该术语」也算成锚定。
    EXPLAIN = ("即", "指的是", "是指", "就是", "也就是", "含义是", "意思是",
               "这里的", "所谓", "缩写", "全称", "译作", "可以理解为", "的意思",
               "——", "本质上是", "是一", "是把", "是给", "是让")
    term_re = re.compile(
        r"`([A-Za-z][A-Za-z0-9_.:+-]{2,30})`"
        r"|(?<![A-Za-z])([A-Z]{2,6})(?![A-Za-z])"
    )
    term_hits: dict[str, list[tuple[str, int, str]]] = {}
    for name, text in ch_text.items():
        rows = list(strip_fences(text))
        seen_in_ch: set[str] = set()
        for idx, (i, ln) in enumerate(rows):
            nxt = rows[idx + 1][1] if idx + 1 < len(rows) else ""
            if not any(w in ln + " " + nxt for w in EXPLAIN):
                continue
            for m in term_re.finditer(ln):
                t = m.group(1) or m.group(2)
                if t in seen_in_ch:
                    continue
                seen_in_ch.add(t)
                term_hits.setdefault(t, []).append((name, i, ln.strip()[:120]))
    rows_b = []
    for t, hits in sorted(term_hits.items()):
        chs = sorted({h[0] for h in hits})
        if len(chs) < 2:
            continue
        rows_b.append([
            "B-term", t, str(len(chs)), ",".join(chs),
            " || ".join(f"{h[0]}:{h[1]}" for h in hits),
        ])
    rows_b.sort(key=lambda r: (-int(r[2]), r[1]))

    # --- C 事故重复讲述 ---
    issue_re = re.compile(r"(?:issues?/|#)(\d{3,5})\b")
    issue_hits: dict[str, list[tuple[str, int, str]]] = {}
    for name, text in ch_text.items():
        for i, ln in strip_fences(text):
            for m in issue_re.finditer(ln):
                issue_hits.setdefault(m.group(1), []).append(
                    (name, i, ln.strip()[:120]))
    rows_c = []
    for num, hits in sorted(issue_hits.items(), key=lambda kv: int(kv[0])):
        chs = sorted({h[0] for h in hits})
        if len(chs) < 2:
            continue
        rows_c.append([
            "C-issue", f"#{num}", str(len(chs)), ",".join(chs),
            " || ".join(f"{h[0]}:{h[1]}" for h in hits),
        ])

    # --- D 定案重复 ---
    # 锚点取「标记行 ±1 行」:定案常写成两行(结论一行、锚点一行),
    # 只看同一行会漏掉一半 —— 实测 109 个标记行里只有 19 行自带锚点。
    MARKERS = "▲◇■◎"
    marker_hits: dict[str, list[tuple[str, int, str]]] = {}
    for name, text in ch_text.items():
        all_lines = text.splitlines()
        for i, ln in strip_fences(text):
            if not any(mk in ln for mk in MARKERS):
                continue
            ctx = "\n".join(all_lines[max(0, i - 2):i + 1])
            for m in vc.citations(ctx, resolve):
                marker_hits.setdefault(m.group("path"), []).append(
                    (name, i, ln.strip()[:120]))
    rows_d = []
    for src, hits in sorted(marker_hits.items()):
        chs = sorted({h[0] for h in hits})
        if len(chs) < 2:
            continue
        rows_d.append([
            "D-ruling", src, str(len(chs)), ",".join(chs),
            " || ".join(f"{h[0]}:{h[1]}" for h in hits),
        ])
    rows_d.sort(key=lambda r: (-int(r[2]), r[1]))

    p = out_dir / "f-pre-binding-inventory-dupes.tsv"
    p.write_text(
        "kind\tkey\tn_chapters\tchapters\thits\n"
        + "".join("\t".join(r) + "\n" for r in rows_b + rows_c + rows_d),
        encoding="utf-8",
    )
    print(f"[6] dupes    -> {p.relative_to(STUDY)}"
          f"  (B 术语 {len(rows_b)} / C 事故 {len(rows_c)} / D 定案 {len(rows_d)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
