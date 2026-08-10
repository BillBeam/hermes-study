#!/usr/bin/env python3
"""R11C 片 D:改正「解析成功却指错文件」的裸锚点(根同名遮蔽)。

背景见底稿 §3.4。这一类**任何现有关卡都发现不了**:`README.md:55` 在仓库根确实是
一个真文件、行号也在范围内,于是关卡满意,而作者说的是
`plugins/memory/supermemory/README.md:55`。

判据是**两条同时成立**,缺一不改:

  1. **归属**:锚点所在小节的标题点名了某个插件(这些底稿的小节标题就叫
     「## 十三、byterover README vs 代码对照(逐条)」),于是目标文件是确定的;
  2. **内容**,两档任一:
     - **T1 逐字**:锚点所在行里锚点之外的反引号片段(过滤规则同 `cell_tokens`)
       或引号里的原文,能在目标文件 [N-12, N+12] 里逐字找到;
     - **T2 比较**:笔记那句话的实词在**目标**那一段里命中得**严格多于**在**根**
       那一段里(平手不算)。归属已由小节标题定死,这一档只回答「目标比根更像它
       说的那个地方吗」——底稿引文常是转述,逐字判据对转述必然失败,而
       「一条指向根的锚点」是**已知错误**,不是安全默认。

归属 + 任一内容档才改;内容两档都不过的**点名留下**,由底稿 §5 移交。

    python3 data/r11c/d-anchor-resolution-shadow-fix.py [--apply]
"""
import re
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[2]
REPO = Path("/home/user/hermes-agent")
sys.path.insert(0, str(STUDY / "scripts"))
import verify_citations as vc  # noqa: E402

APPLY = "--apply" in sys.argv
BAND = 12
FENCE = re.compile(r"^\s*```")

P = "plugins/memory/"
# 小节标题里出现哪个词 -> 这一节的 README/cli.py 指哪个插件
PLUGIN_WORDS = {
    "openviking": P + "openviking", "byterover": P + "byterover",
    "hindsight": P + "hindsight", "supermemory": P + "supermemory",
    "retaindb": P + "retaindb", "mem0": P + "mem0",
    "holographic": P + "holographic", "honcho": P + "honcho",
}

# 只处理这几份 —— 它们的小节标题体例统一、逐条对照 README,归属可判。
FILES = {
    "notes/r6-10-honcho.md": P + "honcho",          # 全篇 honcho,标题不必点名
    "notes/r6-20-openviking-byterover.md": None,
    "notes/r6-30-hindsight-supermemory-retaindb.md": None,
    "notes/r6-40-mem0-holographic.md": None,
    "notes/r6-90-doc-conflict-rulings.md": None,
}

# 显式豁免:这一处笔记自己写明了「**根** README.md:26」,它指的就是仓库根那个。
EXEMPT = {("notes/r6-10-honcho.md", "README.md:26")}

ANCHOR = re.compile(r'(?<![/\w.-])(README\.md|cli\.py):(\d+)(?:-(\d+))?')
_src = {}


def src(rel):
    if rel not in _src:
        p = REPO / rel
        _src[rel] = p.read_text(encoding="utf-8", errors="replace").splitlines() \
            if p.is_file() else []
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
    # 中文底稿常把英文原文用直角/弯引号引起来,那也是逐字引文
    for q in re.findall(r'"([^"]{6,90})"', line) + re.findall(r'“([^”]{6,90})”', line):
        out.append(" ".join(q.split()))
    return out


def band(rel, n, end):
    s = src(rel)
    lo, hi = max(0, n - 1 - BAND), min(len(s), max(end, n + BAND))
    return " ".join(" ".join(x.split()) for x in s[lo:hi])


def main():
    fixed = skipped = 0
    tiers = {}
    notes_out = []
    for rel, forced in FILES.items():
        p = STUDY / rel
        raw = p.read_text(encoding="utf-8")
        lines = raw.splitlines()
        out, in_fence, head = [], False, ""
        for line in lines:
            if FENCE.match(line):
                in_fence = not in_fence
                out.append(line)
                continue
            if in_fence:
                out.append(line)
                continue
            if line.startswith("#"):
                head = line.lower()
            plug = forced
            if plug is None:
                cands = [v for k, v in PLUGIN_WORDS.items() if k in head]
                plug = cands[0] if len(cands) == 1 else None
            if plug is None:
                out.append(line)
                continue

            new, pos, hit = [], 0, False
            for m in ANCHOR.finditer(line):
                name, n = m.group(1), int(m.group(2))
                end = int(m.group(3) or n)
                if (rel, f"{name}:{n}") in EXEMPT:
                    continue
                target = f"{plug}/{name}"
                if not src(target) or n > len(src(target)):
                    notes_out.append(f"  跳过(行号越界或无此文件) {rel}  {name}:{n} -> {target}")
                    skipped += 1
                    continue
                toks = probes(line)
                tier = ""
                if toks and any(t in band(target, n, end) for t in toks):
                    tier = "T1-逐字"      # 引文/符号在目标那一段里逐字找得到
                else:
                    # T2 比较判据:笔记那句话的实词,在**目标**那一段里命中得比在
                    # **根**那一段里多。归属已由小节标题定死,这一条只回答
                    # 「目标比根更像它说的那个地方吗」。严格多,平手不算。
                    words = {w for t in toks for w in re.findall(r"[A-Za-z_][\w.-]{3,}", t)}
                    tb, rb = band(target, n, end), band(name, n, end)
                    ht = sum(1 for w in words if w in tb)
                    hr = sum(1 for w in words if w in rb)
                    if words and ht >= 1 and ht > hr:
                        tier = f"T2-比较({ht}>{hr})"
                if not tier:
                    notes_out.append(f"  跳过(内容判据不过) {rel}  {name}:{n} -> {target}")
                    skipped += 1
                    continue
                tiers[tier.split("-")[0]] = tiers.get(tier.split("-")[0], 0) + 1
                new.append(line[pos:m.start(1)])
                new.append(target)
                pos = m.start(2) - 1  # 保留 ":" 及其后的行号
                hit = True
                fixed += 1
            out.append("".join(new) + line[pos:] if hit else line)
        if APPLY:
            p.write_text("\n".join(out) + ("\n" if raw.endswith("\n") else ""),
                         encoding="utf-8")
    print("\n".join(notes_out))
    print(f"\n{'已改写' if APPLY else '干跑:将改写'} {fixed} 处 {tiers};"
          f"判据不过、点名留下 {skipped} 处")


if __name__ == "__main__":
    main()
