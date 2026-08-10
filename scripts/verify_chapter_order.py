#!/usr/bin/env python3
"""章序关卡(R11D 立,结清 H-R11C-F-a)。

《设计蓝图》的章号此前**没有落点**:1–17 只存在于 `reports/round-9d-l1-completion.md`
§8.2 那张表的序号列,18–21 散在各轮报告与合并提交(= PR 描述)里。于是有两种错同时活着:

  - **重号**:`chapters/r11b-the-unwritten-layer.md:255` 把 r7b 称作第十一章,
    而第十一章是 r8b。它能活下来是因为**章号不在任何关卡的检查面上** ——
    `verify_citations.py` 认 `路径:行号`,`verify_evidence_commands.py` 认 ```verify 块,
    两者都读不到「第十一章」这四个字;而那一行**同时**写了章号和文件名,文件名是对的,
    所以任何以文件名为线索的检查都会放行。
  - **声明缺口**:3/4/5/6/8/9/10 共 7 个章号,全语料 + `git log --all` 一次都没被写出来过。

修法是给章号定**单一落点**(`data/chapter-order.tsv`),再让本脚本去核对,而不是
指望作者每次写「第 N 章」时都去数一遍。

四项检查:

  1. **重号为 0**            —— 落点表里 chapter 列不得重复。
  2. **每章有且仅有一个章号** —— 落点表与 `chapters/*.md` 是双射:磁盘上每份成品章
     在表里恰好出现一次,表里每一行都指向一份存在的文件。
  3. **章号连续**            —— 1..N 无缺口(缺口意味着装订时会印出一个空章号)。
  4. **正文章号与落点表一致** —— 扫散文里的「第 N 章」;**同一行若还点了某份成品章的
     文件名**,落点表必须把 N 映射到那一份。这一条正是抓 r11b:255 那种错的。

**为什么第 4 项只对 `chapters/` 阻断**:`notes/` 与 `reports/` 是历史记录,它们**理应**
逐字引用一个错的章号来报告这个错(`notes/r11c-raw-pre-binding-inventory.md:203` 那张
逐号对照表就是)。把它们一并阻断,等于要求报告一个错的人先把错抹掉 —— 与
CLAUDE.md「写一份点名清单就会改变下一次的读数」同一个坑。非 `chapters/` 的不一致
仍然**打印**出来(记 ADVISORY),只是不改退出码:可见,但不逼着改。

**跳围栏块与引用块**:两者的契约都是逐字摘录(`verify_citations.py:666` FENCE /
`:676` QUOTE 同款),摘录里出现的章号是**别人的话**,不该按本表判。

**只认「声明」,不靠嗅探**:一句「第二章讲的是怎么调用一个模型」没有点名文件,
本脚本记 UNVERIFIABLE 并计数,**不去猜**它指哪一章 —— 与 CLAUDE.md 给
```text/console/verify 那一栏定的是同一条原则。

    python3 scripts/verify_chapter_order.py                 # 默认扫 chapters/*.md
    python3 scripts/verify_chapter_order.py chapters/*.md notes/*.md reports/*.md
"""
import re
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
MANIFEST = STUDY / "data" / "chapter-order.tsv"

_CN_DIGIT = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
             "七": 7, "八": 8, "九": 9}

# 「第 N 章」的三种写法都要认:第十一章 / 第 7 章(阿拉伯数字 + 空格)/ 第7章。
# R11C 片 F 的原始正则漏掉了带空格那种,而那 4 处正是唯一一处成品章互引章号的地方。
MENTION = re.compile(r"第\s*([0-9]+|[一二三四五六七八九十]+)\s*章")
FENCE = re.compile(r"^\s*```")
QUOTE = re.compile(r"^\s*>")


def cn2int(s):
    """一 / 十 / 十一 / 二十 / 二十一 -> int;认不出返回 None(不猜)。"""
    if s.isdigit():
        return int(s)
    if "十" not in s:
        return _CN_DIGIT.get(s)
    head, _, tail = s.partition("十")
    tens = _CN_DIGIT.get(head, 1) if head else 1
    ones = _CN_DIGIT.get(tail, 0) if tail else 0
    return tens * 10 + ones


def load_manifest():
    rows = []
    with MANIFEST.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\r\n")
            if not line or lineno == 1:
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                sys.exit(f"FAIL: {MANIFEST.name}:{lineno} 字段不足 4 列")
            rows.append({"chapter": int(parts[0]), "file": parts[1],
                         "round": parts[2], "title": parts[3], "lineno": lineno})
    return rows


def main(argv):
    targets = [Path(a) for a in argv[1:]] or sorted((STUDY / "chapters").glob("*.md"))
    rows = load_manifest()
    fails = []

    # --- 检查 1:重号为 0 ---
    seen = {}
    for r in rows:
        if r["chapter"] in seen:
            fails.append(f"[DUP-CHAPTER] 章号 {r['chapter']} 重复:"
                         f"{seen[r['chapter']]['file']} 与 {r['file']}")
        seen[r["chapter"]] = r

    # --- 检查 2:落点表与磁盘双射 ---
    on_disk = {f"chapters/{p.name}" for p in (STUDY / "chapters").glob("*.md")}
    in_table = {}
    for r in rows:
        if r["file"] in in_table:
            fails.append(f"[DUP-FILE] {r['file']} 在落点表里出现 2 次"
                         f"(章号 {in_table[r['file']]} 与 {r['chapter']})")
        in_table[r["file"]] = r["chapter"]
        if not (STUDY / r["file"]).exists():
            fails.append(f"[MISSING-FILE] 落点表 {MANIFEST.name}:{r['lineno']} "
                         f"指向不存在的文件 {r['file']}")
    for f in sorted(on_disk - set(in_table)):
        fails.append(f"[UNNUMBERED] {f} 在磁盘上但没有章号 —— 每章有且仅有一个章号")

    # --- 检查 3:章号连续 ---
    nums = sorted(seen)
    if nums and nums != list(range(1, len(nums) + 1)):
        missing = sorted(set(range(1, max(nums) + 1)) - set(nums))
        fails.append(f"[GAP] 章号不连续,缺 {missing}")

    # --- 检查 4:正文章号与落点表一致 ---
    by_num = {r["chapter"]: r["file"] for r in rows}
    basename = {Path(r["file"]).name: r["chapter"] for r in rows}
    # r11b 那种错的形状:同一行既写章号、又写文件名(全路径或裸文件名),两者不一致。
    stems = {Path(r["file"]).name.split("-")[0]: r["chapter"] for r in rows}
    checked = advisory = unverifiable = 0

    for path in targets:
        rel = str(path.resolve().relative_to(STUDY)) if path.is_absolute() else str(path)
        blocking = rel.startswith("chapters/")
        try:
            lines = path.read_text(encoding="utf-8").split("\n")
        except OSError as exc:
            fails.append(f"[UNREADABLE] {rel}: {exc}")
            continue
        in_fence = False
        for i, line in enumerate(lines, 1):
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence or QUOTE.match(line):
                continue
            hits = MENTION.findall(line)
            if not hits:
                continue
            # 同一行点到的成品章(全路径优先,其次裸文件名)
            named = {basename[n] for n in basename if n in line}
            for raw in hits:
                num = cn2int(raw)
                if num is None:
                    continue
                if not named:
                    unverifiable += 1
                    continue
                if num in named:
                    checked += 1
                    continue
                want = by_num.get(num, "(该章号不存在)")
                got = sorted(Path(by_num[c]).name for c in named if c in by_num)
                msg = (f"[CHAPTER-MISMATCH] {rel}:{i}  「第{raw}章」= {want},"
                       f"但同行点的是 {', '.join(got)}"
                       f"(其章号 {sorted(named)})")
                if blocking:
                    fails.append(msg)
                else:
                    advisory += 1
                    print("  [ADVISORY] " + msg[len("[CHAPTER-MISMATCH] "):])

    print(f"chapters={len(rows)}  重号={sum(1 for f in fails if f.startswith('[DUP'))}  "
          f"未编号={sum(1 for f in fails if f.startswith('[UNNUMBERED]'))}")
    print(f"正文章号提及:一致={checked}  未点名文件(不猜)={unverifiable}  "
          f"非 chapters/ 的不一致={advisory}(记 ADVISORY,不改退出码)")
    if advisory:
        print("  ADVISORY 说明:历史记录理应逐字引用错的章号来报告它,故不阻断。")
    if fails:
        for f in fails:
            print(f)
        print(f"FAIL: {len(fails)} 项章序检查未通过")
        return 1
    print("OK: 章号无重号、与磁盘双射、连续,且成品章正文引用与落点表一致")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
