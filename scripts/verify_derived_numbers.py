#!/usr/bin/env python3
"""可复算指标关卡(R11D 立,结清 H-R11C-E-c / H-R11C-F-b;R11F 补写入腿;R11F-fix 重做两条腿的判据)。

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

脚本从 `data/ledger.tsv` 复算每个键的真值,然后要求那些数**按声明顺序**出现在紧跟其后的
那一段里(千位分隔与否都认)。

**为什么不嗅探**(不去正文里扫「看起来像分层数的数」):`511` 是 L1 的过期值,
也正好是 `chapters/r9b-multimodal-delivery.md` 的行数;`560` 是 L4 文件数,
也是别处的行号。嗅探式判据会把这些全报成命中,而**一个靠猜的关卡会被作者学会忽略**
—— 与 CLAUDE.md 给表格锚点、给 ```text 豁免、给无扩展名文件定的是同一条原则:
**声明,不靠嗅探**。

**代价要如实说**:没写声明的手抄件,本关卡**发现不了**。它把下限从「一个都不查」
抬到「**声明了的必被查**」,不是「正文里所有可复算数都被查了」。要扩覆盖面,
就得把声明补到更多地方去 —— 而补声明这个动作本身是可见的、可被评审的。

## 数字 token:两条腿共用的唯一判据(R11F-fix 立)

R11D / R11F 两条腿都用 `str.__contains__` 判「这个数在不在区段里」。子串判定有两个后果,
一个假绿一个真坏,而**两条腿栽的是同一个坑**,所以判据只写一份、两条腿共用:

  * 假绿(校验腿):真值 `2586` 会在 `12,586` 里「找得到」,于是一个从来没写对过的数照样 OK;
    锚点 `notes/x.md:2586` 的行号同理。
  * 真坏(写入腿):`str.replace` 会把 `12,586` 改成 `12,829`,而 `hits` 计数用的是同一套
    子串语义,所以那句 `assert done == hits` **恒成立**,永远抓不到自己刚造的这处损坏。

`number_tokens()` 把区段切成**数字 token**:`\d{1,3}(?:,\d{3})+` 或 `\d+`,两侧不许贴
字母/数字/逗号/小数点。于是 `12,586` 是**一个** token(不含 `2,586`),`L1`、`R1-inventoried`、
`81.1%` 里的数字**根本不是** token。另外两类整段排除:

  * **锚点里的行号**(`路径.扩展名:行号`)—— 它是 `verify_citations.py` 的资产,
    写入腿动它就是当场造一处引用漂移;校验腿认它就是拿别人的行号冒充自己的真值。
  * **围栏块内的行** —— 区段里若混进 ```` ``` ```` 块,那是源码摘录,不是正文里的手抄件。

## 校验腿:多键声明要判「哪个数对哪个键」(R11F-fix,本轮第 2 项)

`<!-- derived: ledger.L1.files ledger.L1.lines … -->` 一条声明覆盖 12 个键、一张 6 行的表。
R11D 的判据是**逐键各问一次「这个数在不在区段里」**,于是**把整张表的数字打乱重排,
关卡照样全绿** —— 它判的是集合成员关系,而读者读的是「L1 那一行的文件数」。

改为**保序绑定**:区段的数字 token 按出现顺序排好,声明里的键按声明顺序逐个去认领,
每个键认领**它之后的第一个**等值 token(贪心最早匹配 —— 子序列匹配的标准结论:
存在任何一种保序匹配,贪心最早就一定能找到,所以不会误报)。于是:

  * 键 ↔ token 的对应关系是**确定的**,`--explain` 直接打印出来(行号 + 列号 + 原文);
  * 值在区段里有、但顺序不对 → `ORDER`(阻断)。整表重排、两行对调,都在这里被抓住;
  * 值在区段里根本没有 → `STALE`(阻断,原判据保留)。

声明的顺序就是作者对「这段里这些数按什么次序出现」的**声明**,仍然是声明式判据。
r1 那张表的 12 个键,声明顺序本来就是表的行序 × 列序。

**覆盖面要如实说**:两个键真值相同时,谁认领哪个 token 由顺序决定,交换它们无法被区分
—— 这是保序判据的固有边界,`--explain` 会把 `=` 标出来让它可见。

## 写入腿(R11F 增,R11F-fix 重做):`--sync --since <rev>`

R11D 只造了**校验腿**。于是一次台账变更之后,作者要么手工键入新值,要么留着关卡红着 ——
而**手工键入正是本关卡要治的病**(正文里出现第二份手抄件)。

**两个值都由复算产生,一个都不许手键**:

  * **新值** = 当前工作树 `data/ledger.tsv` 复算;
  * **旧值** = `git show <rev>:data/ledger.tsv` 复算 —— 不存历史状态文件、不猜正文里
    哪个数字是旧值。要替换的那个 token 必须**恰好等于旧真值**,否则拒绝改。

守卫(任何一条不满足就跳过并报出,不猜):

  1. 只在该声明覆盖的区段内替换,且只替换**整个数字 token**(见上);
  2. 旧真值必须在区段内**作为 token 出现过**;找不到就不猜该改哪个数;
  3. 新真值已在区段内出现、且旧真值已不在 → 判**已同步**,静默跳过;
     两者**同时**出现 → 判**歧义**,报出并跳过(那一段被人手动改过一半);
  4. 旧真值不得同时是**同一条声明里另一个键**的旧真值或新真值 —— 撞了就是张冠李戴。

**守卫 4 在 R11F 版里是死代码**(R11F-fix 查出):它写的是

    sibling_truths = {old_vals.get(k) for k in keys} | {new_vals.get(k) for k in keys}
    if sum(1 for v in sibling_truths if v == old) > 1:

`sibling_truths` 是**集合**,集合里等于 `old` 的元素**至多一个**,所以那个 `> 1`
**恒为假,守卫从未被触发过一次**。改为对**其它键**逐个点名比对,并在跳过时打印撞上的是谁。
负控 `data/r11f-fix/probes/derived_write_negative_control.py` 里 W2 就是它:
两个键旧真值相同时,R11F 版把两处都换成了 A 的新值,B 的那一格从此永远是错的。

    python3 scripts/verify_derived_numbers.py                 # 默认扫 chapters/*.md
    python3 scripts/verify_derived_numbers.py --list          # 打印全部键的当前真值
    python3 scripts/verify_derived_numbers.py --explain       # 打印键 ↔ token 的绑定
    python3 scripts/verify_derived_numbers.py --sync --since <sha>   # 复算旧值并就地同步
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

# 数字 token:千分位形式优先(否则 `12,586` 会被切成 `12` 和 `586`)。
# 两侧的守卫读作:左边不许贴 字母/数字/下划线/小数点/逗号(挡掉 `L1`、`12,586` 的尾段、
# `81.1` 的小数部分),右边不许贴 字母/数字/下划线/逗号,也不许后跟 `.数字`(挡掉 `81.1` 的整数部分)。
NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+|\d+)(?![\w,]|\.\d)")
# `路径.扩展名:行号` —— 锚点里的行号是 verify_citations.py 的资产,两条腿都整段排除。
ANCHOR = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_./\-]*\.[A-Za-z0-9]{1,6}:\d+(?:-\d+)?")


class Tok:
    """区段里的一个数字 token:它在哪一行、哪一列、原文怎么写的、值是多少。"""

    __slots__ = ("line", "col", "raw", "val")

    def __init__(self, line, col, raw, val):
        self.line, self.col, self.raw, self.val = line, col, raw, val

    def where(self):
        return f"{self.line + 1}:{self.col + 1}"


def number_tokens(lines, start, end):
    """区段 [start, end) 内的数字 token,按出现顺序。围栏块内的行与锚点行号整段排除。"""
    out, in_fence = [], False
    for j in range(start, end):
        line = lines[j]
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        blocked = [m.span() for m in ANCHOR.finditer(line)]
        for m in NUM.finditer(line):
            a, b = m.span()
            if any(a < hi and lo < b for lo, hi in blocked):
                continue
            out.append(Tok(j, a, m.group(), int(m.group().replace(",", ""))))
    return out


def declarations(lines):
    """逐条 `<!-- derived: … -->` 声明,连同它覆盖的区段边界。

    区段 = 跳过空行后紧跟的那一段连续非空行(表格没有空行,段落也没有)。
    两条腿共用这一个函数 —— R11F 版校验腿走 `region_after()`、写入腿另算一遍
    `body_start/body_end`,两份等价代码是判据分叉的现成入口。
    """
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
        body_start = i + 1
        while body_start < len(lines) and not lines[body_start].strip():
            body_start += 1
        body_end = body_start
        while body_end < len(lines) and lines[body_end].strip():
            body_end += 1
        yield i, m.group("keys").split(), body_start, body_end


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
    """取某个 rev 的 data/ledger.tsv 原文。旧真值由它复算,不存历史状态文件。

    R11F 版用 `check=True`,于是一个取不到的 rev 直接抛 CalledProcessError 的 traceback。
    R11F 报告 §5.1 那个 ```verify 块钉的正是 `--since main`,而 `main` 上没有
    `data/ledger.tsv` —— 关卡因此在 EVIDENCE-DIFF 里显示为一段 traceback。
    (这同时是 CLAUDE.md「量之前的命令不许钉在会移动的引用上」的又一次重演:
    `main` 是分支名,不是提交。)报清楚,别抛栈。
    """
    proc = subprocess.run(["git", "-C", str(STUDY), "show", f"{rev}:data/ledger.tsv"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"FAIL: 取不到 {rev}:data/ledger.tsv —— {proc.stderr.strip().splitlines()[-1]}\n"
            f"      --since 要给一个**取得到台账的提交**(建议直接给 sha,分支名会移动)。")
    return proc.stdout


def forms(n):
    """一个数在正文里的两种合法写法:563 与 522,207。"""
    return {str(n), f"{n:,}"}


def bind(keys, toks, vals):
    """保序绑定:键按声明顺序,各认领其后第一个等值 token。

    返回 [(key, tok_or_None, verdict)],verdict ∈ {OK, ORDER, STALE, UNKNOWN-KEY}。
    贪心最早匹配 —— 存在任何保序匹配时它必然成功,所以 ORDER 不会误报。
    """
    out, pos = [], 0
    for key in keys:
        if key not in vals:
            out.append((key, None, "UNKNOWN-KEY"))
            continue
        want = vals[key]
        hit = next((i for i in range(pos, len(toks)) if toks[i].val == want), None)
        if hit is not None:
            out.append((key, toks[hit], "OK"))
            pos = hit + 1
        elif any(t.val == want for t in toks):
            out.append((key, None, "ORDER"))
        else:
            out.append((key, None, "STALE"))
    return out


def sync(targets, old_vals, new_vals):
    """把区段内的旧真值就地换成新真值。两个值都来自复算;不满足守卫就跳过并报出。"""
    changes, skipped = [], []
    for path in targets:
        rel = str(path.resolve().relative_to(STUDY)) if path.is_absolute() else str(path)
        lines = path.read_text(encoding="utf-8").split("\n")
        edits = []
        for i, keys, body_start, body_end in declarations(lines):
            toks = number_tokens(lines, body_start, body_end)
            for key in keys:
                if key not in new_vals or key not in old_vals:
                    continue
                new, old = new_vals[key], old_vals[key]
                if old == new:
                    continue
                hits = [t for t in toks if t.val == old]
                fresh = [t for t in toks if t.val == new]
                if fresh and not hits:
                    continue                                    # 守卫 3:已同步,静默
                if fresh and hits:
                    skipped.append(f"[SKIP] {rel}:{i + 1} {key} 新旧真值 {old:,} / {new:,} "
                                   f"在区段内同时出现({hits[0].where()} 与 {fresh[0].where()}),"
                                   f"不猜该动哪一个")
                    continue
                if not hits:
                    skipped.append(f"[SKIP] {rel}:{i + 1} {key} 旧真值 {old:,} 在区段内"
                                   f"找不到(整数字 token 口径),不猜该改哪个数")
                    continue
                # 守卫 4:同一条声明里另一个键的真值撞上了 old,换过去就是张冠李戴。
                # R11F 版把候选装进 set 再数,于是这一条恒为假、一次都没触发过。
                rivals = [k for k in keys if k != key
                          and old in (old_vals.get(k), new_vals.get(k))]
                if rivals:
                    skipped.append(f"[SKIP] {rel}:{i + 1} {key} 旧真值 {old:,} 同时是同一条"
                                   f"声明里 {', '.join(rivals)} 的真值,替换会张冠李戴")
                    continue
                # 同一个派生值在一段里出现多次是**正常的**:r1 那段既写「仍有 5,944 个文件」,
                # 又写「8,530 − 5,944 = 2,586」。要求"恰好 1 次"会让这一条永远同步不了,
                # 而只换其中一处会把那句算式改成错的。护栏是上面那条**同声明内不撞值**,
                # 撞不上就说明这段里每一个等值 token 都是这个键 —— 全换。
                for t in hits:
                    edits.append((t, key, old, new))
        # 按 (行, 列) 倒序落笔:同一行上的多处替换不会让后面的列偏移失效。
        for t, key, old, new in sorted(edits, key=lambda e: (e[0].line, e[0].col), reverse=True):
            line = lines[t.line]
            if line[t.col:t.col + len(t.raw)] != t.raw:
                raise SystemExit(f"FAIL: {rel}:{t.line + 1} token 位置在落笔前已失效"
                                 f"(期望 {t.raw!r});未写入任何文件")
            # 千分位跟着**原 token 的写法**走(作者写 `522207` 就别替他加逗号)。
            # 例外:旧值 < 1000 时它根本没有逗号可写,那不是作者的选择 —— 新值
            # 跨过 1000 就该用本文档通行的千分位写法。
            repl = f"{new:,}" if ("," in t.raw or old < 1000 <= new) else str(new)
            lines[t.line] = line[:t.col] + repl + line[t.col + len(t.raw):]
            changes.append(f"  {rel}:{t.line + 1}  {key}  {t.raw} -> {repl}")
        if edits:
            path.write_text("\n".join(lines), encoding="utf-8")
    return changes, skipped


def check(targets, vals, explain=False):
    """校验腿。返回 (declared, ok, fails, report_lines)。"""
    fails, report, declared, ok = [], [], 0, 0
    for path in targets:
        rel = str(path.resolve().relative_to(STUDY)) if path.is_absolute() else str(path)
        try:
            lines = path.read_text(encoding="utf-8").split("\n")
        except OSError as exc:
            fails.append(("UNREADABLE", f"[UNREADABLE] {rel}: {exc}"))
            continue
        for i, keys, body_start, body_end in declarations(lines):
            toks = number_tokens(lines, body_start, body_end)
            bound = bind(keys, toks, vals)
            twins = {v for v in (vals.get(k) for k in keys)
                     if sum(1 for k in keys if vals.get(k) == v) > 1}
            for key, tok, verdict in bound:
                declared += 1
                if verdict == "OK":
                    ok += 1
                    dup = "  =(同声明内有另一个键真值相同,顺序即绑定)" \
                        if vals[key] in twins else ""
                    if explain:
                        report.append(f"  {rel}:{i + 1}  {key} = {vals[key]:,} "
                                      f"↔ {rel}:{tok.where()} {tok.raw!r}{dup}")
                elif verdict == "UNKNOWN-KEY":
                    fails.append(("UNKNOWN-KEY",
                                  f"[UNKNOWN-KEY] {rel}:{i + 1}  未知键 {key};可用键见 --list"))
                elif verdict == "ORDER":
                    at = [t.where() for t in toks if t.val == vals[key]]
                    fails.append(("ORDER",
                                  f"[ORDER] {rel}:{i + 1}  {key} 复算真值 {vals[key]:,} "
                                  f"在区段内出现于 {', '.join(at)},但**不在声明顺序上** —— "
                                  f"这一段的数与键对不上号(值被重排或串行了)"))
                else:
                    fails.append(("STALE",
                                  f"[STALE] {rel}:{i + 1}  {key} 复算真值 {vals[key]:,},"
                                  f"但紧跟其后的段落里没有这个数字 token —— "
                                  f"更大数字的一截(12,586 里的 2,586)、锚点行号"
                                  f"(x.md:2586)、围栏块内的源码摘录,三者都不算"))
    return declared, ok, fails, report


def main(argv):
    raw = argv[1:]
    # `--since <rev>` 的那个 rev 不是目标文件 —— 第一版漏了这一条,于是 `main` 被
    # 当成一份要扫的 md,报 FileNotFoundError。
    skip_idx = {k + 1 for k, a in enumerate(raw) if a == "--since"}
    args = [a for k, a in enumerate(raw) if not a.startswith("--") and k not in skip_idx]
    vals = truth()
    if "--list" in raw:
        for k in sorted(vals):
            print(f"{k}\t{vals[k]}\t{vals[k]:,}")
        return 0

    targets = [Path(a) for a in args] or sorted((STUDY / "chapters").glob("*.md"))

    if "--sync" in raw:
        rev = None
        for k, a in enumerate(raw):
            if a == "--since" and k + 1 < len(raw):
                rev = raw[k + 1]
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

    declared, ok, fails, report = check(targets, vals, explain="--explain" in raw)
    for line in report:
        print(line)
    kinds = {k: sum(1 for t, _ in fails if t == k)
             for k in ("STALE", "ORDER", "UNKNOWN-KEY", "UNREADABLE")}
    print(f"declared={declared}  OK={ok}  STALE={kinds['STALE']}  "
          f"ORDER={kinds['ORDER']}  UNKNOWN-KEY={kinds['UNKNOWN-KEY']}")
    if fails:
        for _, f in fails:
            print(f)
        print(f"FAIL: {len(fails)} 个已声明的可复算指标与台账真值对不上")
        return 1
    print("OK: every declared derived number matches the ledger, in declared order")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
