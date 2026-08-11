#!/usr/bin/env python3
"""可复算指标关卡(R11D 立,结清 H-R11C-E-c / H-R11C-F-b)。

`chapters/r1-what-is-hermes-agent.md` 里有一张分层表,自称「**下表是当前值,不是历史快照**」,
写的却是 R8B 那一版的手抄件。它**已经被修过一次**(review-1 阻断-2 / M-2),六轮后**原样复发**,
而且这一次连它自己那段教训(「凡是能被脚本算出来的数,正文就不该有第二份手抄件」)
一起过期了。由它推出的「408 个文件被真正处理过」真值是 2,586 —— **错六倍**,
而这是「全仓无黑洞」这个最终目的的**唯一可观测指标**。

三条现有关卡一条都够不到这个形状:`verify_ledger.py` 只校验台账**自身**的守恒,
`verify_citations.py` 只校验**带锚点**的引用(而这张表没有锚点),
`verify_evidence_commands.py` 只重跑 ```verify 块。**手抄件不带锚点,所以它不在任何检查面上。**

## 判据:声明式,不嗅探

正文用一条 HTML 注释**声明**「下面这一段里有哪几个可复算指标」:

    <!-- derived: ledger.L1.files ledger.L1.lines ledger.L2.files ledger.L2.lines -->

脚本从 `data/ledger.tsv` 复算每个键的真值,然后要求那个数**逐字出现**在紧跟其后的
那一段里(千位分隔与否都认)。不出现 = `STALE`,阻断。

**为什么不嗅探**(不去正文里扫「看起来像分层数的数」):`511` 是 L1 的过期值,
也正好是 `chapters/r9b-multimodal-delivery.md` 的行数;`560` 是 L4 文件数,
也是别处的行号。嗅探式判据会把这些全报成命中,而**一个靠猜的关卡会被作者学会忽略**
—— 与 CLAUDE.md 给表格锚点、给 ```text 豁免、给无扩展名文件定的是同一条原则:
**声明,不靠嗅探**。

**代价要如实说**:没写声明的手抄件,本关卡**发现不了**。它把下限从「一个都不查」
抬到「**声明了的必被查**」,不是「正文里所有可复算数都被查了」。要扩覆盖面,
就得把声明补到更多地方去 —— 而补声明这个动作本身是可见的、可被评审的。

## 写入腿(R11F 增):`--sync --since <rev>`

R11D 只造了**校验腿**。于是一次台账变更之后,作者要么手工键入新值,要么留着关卡红着 ——
而**手工键入正是本关卡要治的病**(正文里出现第二份手抄件)。R11F 把写入腿补上。

**两个值都由复算产生,一个都不许手键**:

  * **新值** = 当前工作树 `data/ledger.tsv` 复算;
  * **旧值** = `git show <rev>:data/ledger.tsv` 复算 —— 不存历史状态文件、不猜正文里
    哪个数字是旧值。要替换的那个 token 必须**恰好等于旧真值**,否则拒绝改。

守卫(任何一条不满足就跳过并报出,不猜):

  1. 只在该声明覆盖的区段内替换;
  2. 旧值必须在区段内**出现且只出现一次**(两种写法 `5944` / `5,944` 合并计数);
  3. 新值必须在区段内**尚未出现**(已同步过就不重复动);
  4. 旧值不得同时是**同一条声明里另一个键**的真值(否则替换会张冠李戴)。

    python3 scripts/verify_derived_numbers.py                 # 默认扫 chapters/*.md
    python3 scripts/verify_derived_numbers.py --list          # 打印全部键的当前真值
    python3 scripts/verify_derived_numbers.py --sync --since main   # 复算旧值并就地同步
    python3 scripts/verify_derived_numbers.py chapters/*.md notes/*.md
"""
import contextlib
import re
import subprocess
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
LEDGER = STUDY / "data" / "ledger.tsv"
CHAPTER_ORDER = STUDY / "data" / "chapter-order.tsv"

MARKER = re.compile(r"<!--\s*derived:\s*(?P<keys>[^>]*?)\s*-->")
FENCE = re.compile(r"^\s*```")
QUOTE = re.compile(r"^\s*>")
# 行内代码里的 `<!-- derived: … -->` 是在**讲**这个语法,不是在**用**它。
# 本章的 R11D 更正段就写了一句「表前那行 `<!-- derived: … -->` 声明…」,
# 而关卡第一版把它当成了一条真声明 —— 引用一个标记不是做出一个标记。
INLINE_CODE = re.compile(r"`[^`]*`")


def truth(ledger_text=None):
    """从 data/ledger.tsv 复算全部可复算键。

    data/ledger.tsv 是 CRLF 行尾 —— 不剥 CR,layer/status 两列永远匹配不上,
    而那正是 CLAUDE.md 拿来当反例的形状(安静地打出 0)。

    传 ledger_text 则从那份文本复算(`--sync` 用它复算**旧**真值),不读工作树。
    """
    files, lines = {}, {}
    inv_files = inv_lines = tot_files = tot_lines = 0
    with _ledger_lines(ledger_text) as fh:
        next(fh)
        for raw in fh:
            row = raw.rstrip("\r\n").split("\t")
            if len(row) < 6:
                continue
            n = int(row[2])
            layer = row[3].rstrip("\r")
            status = row[5].rstrip("\r")
            files[layer] = files.get(layer, 0) + 1
            lines[layer] = lines.get(layer, 0) + n
            tot_files += 1
            tot_lines += n
            if status == "R1-inventoried":
                inv_files += 1
                inv_lines += n
    out = {}
    for layer in files:
        out[f"ledger.{layer}.files"] = files[layer]
        out[f"ledger.{layer}.lines"] = lines[layer]
    out["ledger.total.files"] = tot_files
    out["ledger.total.lines"] = tot_lines
    out["ledger.inventoried.files"] = inv_files
    out["ledger.inventoried.lines"] = inv_lines
    # 「被真正处理过」= 全仓 − 仍停在 R1-inventoried。这就是 chapters/r1:118 那条派生数。
    out["ledger.processed.files"] = tot_files - inv_files
    out["ledger.processed.lines"] = tot_lines - inv_lines
    if CHAPTER_ORDER.exists():
        with CHAPTER_ORDER.open(encoding="utf-8") as fh:
            out["chapters.count"] = sum(1 for i, _ in enumerate(fh) if i)
    return out


@contextlib.contextmanager
def _ledger_lines(ledger_text):
    if ledger_text is None:
        with LEDGER.open(encoding="utf-8") as fh:
            yield fh
    else:
        yield iter(ledger_text.split("\n"))


def ledger_at(rev):
    """取某个 rev 的 data/ledger.tsv 原文。旧真值由它复算,不存历史状态文件。"""
    return subprocess.run(
        ["git", "-C", str(STUDY), "show", f"{rev}:data/ledger.tsv"],
        capture_output=True, text=True, check=True).stdout


def forms(n):
    """一个数在正文里的两种合法写法:563 与 522,207。"""
    return {str(n), f"{n:,}"}


def sync(targets, old_vals, new_vals):
    """把区段内的旧真值就地换成新真值。两个值都来自复算;不满足守卫就跳过并报出。"""
    changes, skipped = [], []
    for path in targets:
        rel = str(path.resolve().relative_to(STUDY)) if path.is_absolute() else str(path)
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        in_fence, edits = False, []
        for i, line in enumerate(lines):
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence or QUOTE.match(line):
                continue
            m = MARKER.search(INLINE_CODE.sub("", line))
            if not m:
                continue
            keys = m.group("keys").split()
            body_start = i + 1
            while body_start < len(lines) and not lines[body_start].strip():
                body_start += 1
            body_end = body_start
            while body_end < len(lines) and lines[body_end].strip():
                body_end += 1
            region = "\n".join(lines[body_start:body_end])
            sibling_truths = {old_vals.get(k) for k in keys} | {new_vals.get(k) for k in keys}
            for key in keys:
                if key not in new_vals or key not in old_vals:
                    continue
                new, old = new_vals[key], old_vals[key]
                if old == new:
                    continue
                if any(f in region for f in forms(new)):
                    continue                                    # 守卫 3:已同步
                hits = sum(region.count(f) for f in forms(old))
                if hits == 0:
                    skipped.append(f"[SKIP] {rel}:{i + 1} {key} 旧真值 {old:,} 在区段内找不到,"
                                   f"不猜该改哪个数")
                    continue
                if sum(1 for v in sibling_truths if v == old) > 1:
                    skipped.append(f"[SKIP] {rel}:{i + 1} {key} 旧真值 {old:,} 同时是同一条"
                                   f"声明里另一个键的真值,替换会张冠李戴")
                    continue
                # 同一个派生值在一段里出现多次是**正常的**:r1 那段既写「仍有 5,944 个文件」,
                # 又写「8,530 − 5,944 = 2,586」。第一版要求"恰好 1 次",于是这一条永远同步不了,
                # 而只换其中一处会把那句算式改成错的。真正的护栏是上面那条**同声明内不撞值**,
                # 撞不上就说明这段里每一次 old 都是这个键 —— 全换。
                edits.append((body_start, body_end, key, old, new, hits))
        for body_start, body_end, key, old, new, hits in edits:
            done = 0
            for j in range(body_start, body_end):
                for f_old, f_new in ((f"{old:,}", f"{new:,}"), (str(old), str(new))):
                    while f_old in lines[j]:
                        lines[j] = lines[j].replace(f_old, f_new, 1)
                        done += 1
                        changes.append(f"  {rel}:{j + 1}  {key}  {f_old} -> {f_new}")
            assert done == hits, f"{key}: 预期换 {hits} 处,实换 {done} 处"
        if edits:
            path.write_text("\n".join(lines), encoding="utf-8")
    return changes, skipped


def region_after(lines, idx):
    """声明覆盖的范围:跳过空行后,紧跟的那一段连续非空行(表格没有空行,段落也没有)。"""
    i = idx + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    out = []
    while i < len(lines) and lines[i].strip():
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def main(argv):
    raw = argv[1:]
    # `--since <rev>` 的那个 rev 不是目标文件 —— 第一版漏了这一条,于是 `main` 被
    # 当成一份要扫的 md,报 FileNotFoundError。
    skip_idx = {k + 1 for k, a in enumerate(raw) if a == "--since"}
    args = [a for k, a in enumerate(raw) if not a.startswith("--") and k not in skip_idx]
    vals = truth()
    if "--list" in argv[1:]:
        for k in sorted(vals):
            print(f"{k}\t{vals[k]}\t{vals[k]:,}")
        return 0

    targets = [Path(a) for a in args] or sorted((STUDY / "chapters").glob("*.md"))

    if "--sync" in argv[1:]:
        rev = None
        for k, a in enumerate(argv[1:]):
            if a == "--since" and k + 2 <= len(argv[1:]):
                rev = argv[1:][k + 1]
        if not rev:
            print("FAIL: --sync 必须带 --since <rev>(旧真值由该 rev 的台账复算,不手键)",
                  file=sys.stderr)
            return 2
        old = truth(ledger_at(rev))
        changes, skipped = sync(targets, old, vals)
        for s in skipped:
            print(s)
        print(f"synced={len(changes)}  skipped={len(skipped)}  (旧真值复算自 {rev})")
        for c in changes:
            print(c)
        return 0

    fails, declared, ok = [], 0, 0

    for path in targets:
        rel = str(path.resolve().relative_to(STUDY)) if path.is_absolute() else str(path)
        try:
            lines = path.read_text(encoding="utf-8").split("\n")
        except OSError as exc:
            fails.append(f"[UNREADABLE] {rel}: {exc}")
            continue
        in_fence = False
        for i, line in enumerate(lines):
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence or QUOTE.match(line):
                continue
            m = MARKER.search(INLINE_CODE.sub("", line))
            if not m:
                continue
            body = region_after(lines, i)
            for key in m.group("keys").split():
                declared += 1
                if key not in vals:
                    fails.append(f"[UNKNOWN-KEY] {rel}:{i + 1}  未知键 {key};"
                                 f"可用键见 --list")
                    continue
                if any(f in body for f in forms(vals[key])):
                    ok += 1
                else:
                    fails.append(
                        f"[STALE] {rel}:{i + 1}  {key} 复算真值 {vals[key]:,},"
                        f"但紧跟其后的段落里找不到这个数")

    print(f"declared={declared}  OK={ok}  STALE={len(fails)}")
    if fails:
        for f in fails:
            print(f)
        print(f"FAIL: {len(fails)} 个已声明的可复算指标与台账真值不符")
        return 1
    print("OK: every declared derived number matches the ledger")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
