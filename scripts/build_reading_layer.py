#!/usr/bin/env python3
"""阅读层派生件的**唯一生产者**(R11E 立)。

`reading/` 下三份派生件——快读层合集、原则层合集、问题索引——都从 `chapters/` 派生。
`chapters/` 是它们**唯一的真源**,本脚本是它们**唯一的写入者**:产物一律生成,
不允许手抄、也不允许直接编辑产物文件。

## 为什么必须是生成的,而不是手抄的

本项目已有两次实证,说明「派生件靠人保持同步」这个方案在本项目的实际节奏下不成立:

  - 跨章原则清单曾实测 **15/17 失同步**(R11C 片 F 盘点);
  - `chapters/r1-what-is-hermes-agent.md` 的分层手抄数字被修过一次
    (review-1 阻断-2 / M-2),**六轮后原样复发**,由它推出的
    「408 个文件被真正处理过」真值是 2,586 —— 错六倍。

两次都不是作者不用心,而是**手抄件不在任何检查面上**:`verify_citations.py` 认
`路径:行号`,`verify_evidence_commands.py` 认 ```verify 块,`verify_derived_numbers.py`
认 `<!-- derived: -->` 声明——一份手抄的 TL;DR 汇编,一条都碰不到。
R11D 给可复算数字定的修法(**立单一落点 + 让脚本去核对**)在这里原样适用,
只是落点从「一张表」变成「三份文档」。

## 三道锁

**锁一:产物全生成。** 三份产物的每一个字节都由本脚本产出。凡引自成品章的文字,
一律**运行时逐字抽取**,不经人手。`verify_reading_layer.py` 重建后与库内产物逐字比对,
不一致即 `PRODUCT-STALE`(阻断)。

**锁二:源节内容钉(`data/r11e/section-digests.tsv`)。** 每一个被引用到的成品章小节,
按「H2 标题 + 节正文」算一个 sha256 钉在表里。`chapters/` 一改,钉子就对不上:
**本脚本自己会拒绝构建**(`SECTION-DRIFT`),关卡同样阻断。

要点在于这两道锁的**分工**:只有锁一,作者可以一句 `--write` 把新内容刷进产物,
**而没有任何人重新读过那一段**——源章改了,产物跟着改了,却没人判断过
「原则是否还成立、问题索引是否还指对地方」。锁二强制这个动作可见:
重新钉(`--restamp`)是一次**显式的、会进 diff 的**声明,意思是「我重读过了」。
锁一防的是**忘了同步**,锁二防的是**不假思索地同步**。

**锁三:非空绿守卫。** 关卡在任何一类比对数为 0 时判 `EMPTY-GATE` 并失败。
一个什么都没比对的关卡也会打印绿字——这正是 R8C 记下的那个形状
(「造一份锚点全写在块后的文件,关卡输出 OK、退出码 0,一条都没校验」)。

## 声明,不靠嗅探

编辑判断(哪几条原则该合并、两条原则冲突时判谁、什么问题该指向哪一节)是**人写的**,
写在 `data/r11e/` 下的编辑源里,并且**声明**它引自哪一章哪一节的哪一段;
本脚本只负责把声明解析出来、去源章里把那一段**逐字取回来**。声明解析不了(章不存在、
节标题对不上、段落锚点在节内找不到或找到多处)一律**报错退出**,不猜。
与 CLAUDE.md 给表格锚点、给 ```text 豁免、给无扩展名文件定的是同一条原则。

## 用法

    python3 scripts/build_reading_layer.py --check      # 默认:重建并与库内产物比对
    python3 scripts/build_reading_layer.py --write      # 重建并写入 reading/
    python3 scripts/build_reading_layer.py --restamp    # 重钉 section-digests.tsv(表示"我重读过了")
    python3 scripts/build_reading_layer.py --stats      # 只打印体量/阅读时长统计
"""
import argparse
import hashlib
import re
import sys
import unicodedata
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
CHAPTERS = STUDY / "chapters"
READING = STUDY / "reading"
DATA = STUDY / "data" / "r11e"
CHAPTER_ORDER = STUDY / "data" / "chapter-order.tsv"
DIGESTS = DATA / "section-digests.tsv"
PRINCIPLES_SRC = DATA / "principles-src.md"
INDEX_SRC = DATA / "problem-index.tsv"

# 阅读速度口径:350 字/分钟(验收指定)。正文字符数 = 总字符数 - 代码块内字符数。
READ_CPM = 350

H2 = re.compile(r"^## (.+?)\s*$")
FENCE = re.compile(r"^\s*```")
LIST_ITEM = re.compile(r"^(\s*)(?:\d+[.)]|[-*+])\s+\S")
# r8a 用 ①②③ 圈号、r10 用 **(1)**、r2/r9b 用 markdown 有序列表——三种都要认作"条目起头"。
CIRCLED = re.compile(r"^\*\*[①-⑳]")
PARENED = re.compile(r"^\*\*\(\d+\)")


class BuildError(Exception):
    pass


# ---------------------------------------------------------------- 成品章解析

def read_chapter(path):
    return path.read_text(encoding="utf-8").split("\n")


def h2_sections(lines):
    """切 H2 小节:一节 = 从 `## ` 那一行到**下一个 H2 之前**(含其下的 H3 子节)。

    口径写死在这里,因为体量数、钉子、锚点三者都按它算。把 H3 子节**算进来**是有意的:
    `chapters/r9b-multimodal-delivery.md` 的 `### 4.1` 是第 7 条原则的展开,
    切在 H3 上会把它从源节里切掉,而它恰恰是那一条原则最重的证据。

    围栏块内长得像标题的行(注释里的 `## `)不算标题。
    """
    idx, in_fence = [], False
    for i, line in enumerate(lines):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = H2.match(line)
        if m:
            idx.append((i, m.group(1).strip()))
    out = []
    for k, (i, title) in enumerate(idx):
        end = idx[k + 1][0] if k + 1 < len(idx) else len(lines)
        out.append({"title": title, "start": i, "end": end, "lines": lines[i:end]})
    return out


def normalize_for_digest(section):
    """钉子的口径:H2 标题 + 节正文,逐行剥尾随空白,末尾空行不计。

    剥尾随空白:编辑器自动去尾空格这种与内容无关的改动不该炸钉子。
    其余一律逐字——包括空行位置、标点、全角半角。
    """
    body = [ln.rstrip() for ln in section["lines"]]
    while body and not body[-1]:
        body.pop()
    return "\n".join(body)


def section_digest(section):
    return hashlib.sha256(normalize_for_digest(section).encode("utf-8")).hexdigest()


def github_slug(text, seen):
    """GitHub 的标题锚点算法(github-slugger 同款):小写 → 去标点符号 → 空格转连字符。

    保留字母 / 数字 / 组合记号 / `-` / `_`,其余一律删除——中文标点(`:`、`,`、`——`)
    与 ASCII 标点同样被删。重名标题按出现次序补 `-1`、`-2`。

    **这是本项目第一次生成章内锚点**(`chapters/` 此前 0 处 `](#…)` 链接),
    所以算法只能按 GitHub 的公开实现复刻,无法拿仓库里的既有先例反推。
    关卡会断言每个锚点都能解析回一个真实标题,但「GitHub 渲染出来的 id 与本函数一致」
    这一条**本仓库内无法自证**,如实记在报告的边界申报里。
    """
    s = text.lower()
    kept = []
    for ch in s:
        if ch == " ":
            kept.append(" ")
            continue
        if ch in "-_":
            kept.append(ch)
            continue
        if unicodedata.category(ch)[0] in ("L", "N", "M"):
            kept.append(ch)
    slug = "".join(kept).replace(" ", "-")
    n = seen.get(slug, 0)
    seen[slug] = n + 1
    return slug if n == 0 else f"{slug}-{n}"


def chapter_slugs(lines):
    """整章的标题 → 锚点映射。必须扫**全部**标题层级并按出现次序编号,
    因为 GitHub 的重名计数器是全文档一个,只数 H2 会把序号算错。"""
    seen, out = {}, {}
    in_fence = False
    for line in lines:
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{1,6}) (.+?)\s*$", line)
        if m:
            title = m.group(2).strip()
            out.setdefault(title, github_slug(title, seen))
    return out


# ---------------------------------------------------------------- 段落切分

def split_units(section):
    """把一节的正文切成"条目"。条目 = 一条列表项 / 一个 `**①…**` 或 `**(1)…**` 段。

    列表项从标记行起,吃掉其后所有缩进行与空行后仍缩进的续行;
    圈号段与括号号段从标记行起,吃到下一个同级标记或下一个标题。
    切不出条目的节返回整节作为单一条目(r8a 那种散文体也要能被指到)。
    """
    lines = section["lines"][1:]  # 去掉 H2 标题行
    starts, in_fence = [], False
    for i, line in enumerate(lines):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if LIST_ITEM.match(line) and not line.startswith((" ", "\t")):
            starts.append(i)
        elif CIRCLED.match(line) or PARENED.match(line):
            starts.append(i)
    if not starts:
        return [{"start": 0, "end": len(lines), "lines": lines}]
    units = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(lines)
        units.append({"start": s, "end": e, "lines": lines[s:e]})
    return units


def first_paragraph(unit_lines):
    """条目的**首段**:从第一行起,连续非空行,遇空行即止。逐字返回。

    口径理由:整条条目在 `chapters/r8a-configuration-surface.md` 里可以长到两千字
    (带表格、引用块、围栏块),整条抄进原则层会把它变成成品章的第二份副本;
    而首段恰好是各章都写成"黑体一句话 + 一句展开"的那一段,是条目的**陈述**本身。
    """
    out = []
    for ln in unit_lines:
        if not ln.strip():
            break
        out.append(ln.rstrip())
    return out


# ---------------------------------------------------------------- 源解析

class Corpus:
    def __init__(self):
        self.order = []          # [(no, path, round, title)]
        self.by_file = {}        # 'chapters/x.md' -> dict
        if not CHAPTER_ORDER.exists():
            raise BuildError(f"缺少章序落点表 {CHAPTER_ORDER}")
        with CHAPTER_ORDER.open(encoding="utf-8") as fh:
            next(fh)
            for raw in fh:
                row = raw.rstrip("\r\n").split("\t")
                if len(row) < 4:
                    continue
                self.order.append((int(row[0]), row[1], row[2], row[3]))
        for no, rel, rnd, title in self.order:
            p = STUDY / rel
            if not p.exists():
                raise BuildError(f"章序落点表指向不存在的文件:{rel}")
            lines = read_chapter(p)
            secs = h2_sections(lines)
            self.by_file[rel] = {
                "no": no, "round": rnd, "title": title, "rel": rel,
                "lines": lines, "sections": secs,
                "by_title": {s["title"]: s for s in secs},
                "slugs": chapter_slugs(lines),
            }

    def chapter(self, rel):
        if rel not in self.by_file:
            raise BuildError(f"未知成品章:{rel}(不在 data/chapter-order.tsv 上)")
        return self.by_file[rel]

    def section(self, rel, title):
        ch = self.chapter(rel)
        if title not in ch["by_title"]:
            near = "、".join(t for t in ch["by_title"] if t[:6] == title[:6]) or "(无相近标题)"
            raise BuildError(f"{rel} 里没有 H2 小节「{title}」;相近的:{near}")
        return ch["by_title"][title]

    def heading(self, rel, title):
        """按**任意层级**的标题定位,返回 (标题, 它所在的 H2 小节)。

        问题索引要指到**小节**,而各章真正的小节粒度是 H3(`### 3.7 …`);
        只认 H2 会把读者送到一个几千字的 `## 3. 逐机制` 门口。锚点因此按 H3 自己算,
        而**钉子仍钉在它所在的那个 H2 上**——`h2_sections` 本来就把 H3 子节含在内,
        所以 H3 改了 H2 的钉子一样会炸,而钉子数不会随索引条数膨胀。
        """
        ch = self.chapter(rel)
        if title not in ch["slugs"]:
            near = "、".join(t for t in ch["slugs"] if t[:5] == title[:5]) or "(无相近标题)"
            raise BuildError(f"{rel} 里没有标题「{title}」;相近的:{near}")
        for sec in ch["sections"]:
            if title == sec["title"] or any(
                    re.match(r"^#{1,6} " + re.escape(title) + r"\s*$", ln) for ln in sec["lines"]):
                return title, sec
        raise BuildError(f"{rel} 的标题「{title}」不在任何 H2 小节内(疑为章标题 H1)")

    def link(self, rel, title=None):
        ch = self.chapter(rel)
        base = f"../{rel}"
        if title is None:
            return base
        slug = ch["slugs"].get(title)
        if slug is None:
            raise BuildError(f"{rel} 的标题「{title}」解析不出锚点")
        return f"{base}#{slug}"

    def tldr(self, rel):
        ch = self.chapter(rel)
        for s in ch["sections"]:
            if s["title"].startswith("TL;DR"):
                return s
        raise BuildError(f"{rel} 没有 TL;DR 小节")

    def principles_section(self, rel):
        ch = self.chapter(rel)
        for s in ch["sections"]:
            if "可迁移" in s["title"]:
                return s
        return None


# ---------------------------------------------------------------- 钉子

def collect_stamped_sections(corpus, refs):
    """refs = {(rel, title)} —— 三份产物实际引用到的全部源节。"""
    rows = []
    for rel, title in sorted(refs):
        sec = corpus.section(rel, title)
        rows.append((rel, title, section_digest(sec), str(len(sec["lines"]))))
    return rows


def load_digests():
    if not DIGESTS.exists():
        return None
    out = {}
    with DIGESTS.open(encoding="utf-8") as fh:
        next(fh)
        for raw in fh:
            row = raw.rstrip("\r\n").split("\t")
            if len(row) < 3:
                continue
            out[(row[0], row[1])] = row[2]
    return out


def write_digests(rows):
    DATA.mkdir(parents=True, exist_ok=True)
    with DIGESTS.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("chapter\tsection\tsha256\tsection_lines\n")
        for r in rows:
            fh.write("\t".join(r) + "\n")


def check_digests(rows, strict=True):
    """返回 (ok, problems)。problems 里每条形如 (kind, rel, title, want, got)。"""
    stamped = load_digests()
    problems = []
    if stamped is None:
        return False, [("NO-STAMP-TABLE", str(DIGESTS), "", "", "")]
    live = {(r[0], r[1]): r[2] for r in rows}
    for key, digest in live.items():
        if key not in stamped:
            problems.append(("UNSTAMPED", key[0], key[1], "", digest))
        elif stamped[key] != digest:
            problems.append(("SECTION-DRIFT", key[0], key[1], stamped[key], digest))
    for key in stamped:
        if key not in live:
            problems.append(("STALE-STAMP", key[0], key[1], stamped[key], ""))
    return (not problems if strict else True), problems


# ---------------------------------------------------------------- 产物 1:快读层

BANNER = ("<!-- 本文件由 scripts/build_reading_layer.py 生成,请勿直接编辑。\n"
          "     真源是 chapters/;改源章后运行 --restamp 再 --write。 -->")


def build_quickread(corpus, refs):
    out = [BANNER, "", "# 快读层 · 21 章 TL;DR 合集",
           "",
           "> **这份文档是什么**:《设计蓝图》21 个成品章的 TL;DR 逐字汇编,按装订章序排列。",
           "> 用途是**一口气读完拿到全貌**——每章的 TL;DR 本来就是照「读这一段就有全貌」写的,",
           "> 把它们接起来就是一条不下钻的快读路径。",
           ">",
           "> **它不是摘要**:正文一个字都没有改写,全部逐字来自成品章。要下钻,点每节的章标题。",
           "> 溯源约定沿用成品章:`路径:行号 @ 863e313` 指基线 commit `863e31318` 下 hermes-agent 仓库根的相对路径与行号。",
           ""]
    for no, rel, rnd, title in corpus.order:
        sec = corpus.tldr(rel)
        refs.add((rel, sec["title"]))
        out.append("---")
        out.append("")
        out.append(f"## 第 {no} 章 · {title}")
        out.append("")
        out.append(f"来源:[`{rel}`]({corpus.link(rel, sec['title'])}) § {sec['title']}({rnd})")
        out.append("")
        body = [ln.rstrip() for ln in sec["lines"][1:]]
        while body and not body[0]:
            body.pop(0)
        while body and not body[-1]:
            body.pop()
        out.extend(body)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------- 产物 2:原则层

FIELD = re.compile(r"^(family|src|merge|merge-why|conflict-with|ruling|note|scope):\s*(.*)$")
SRC_SPEC = re.compile(r"^(?P<rel>chapters/[^\s]+\.md)\s*§\s*(?P<sec>.+?)\s*¶\s*(?P<anchor>.+?)\s*$")
ENTRY = re.compile(r"^## (?P<id>[PC]\d+)\s*·\s*(?P<title>.+?)\s*$")


def parse_principles_src():
    if not PRINCIPLES_SRC.exists():
        raise BuildError(f"缺少原则层编辑源 {PRINCIPLES_SRC}")
    entries, cur = [], None
    for lineno, raw in enumerate(PRINCIPLES_SRC.read_text(encoding="utf-8").split("\n"), 1):
        m = ENTRY.match(raw)
        if m:
            if cur:
                entries.append(cur)
            cur = {"id": m.group("id"), "title": m.group("title"), "src": [],
                   "family": "", "merge": [], "merge-why": "", "conflict-with": [],
                   "ruling": "", "note": "", "scope": "", "body": [], "lineno": lineno}
            continue
        if cur is None:
            continue
        f = FIELD.match(raw)
        if f:
            key, val = f.group(1), f.group(2).strip()
            if key == "src":
                s = SRC_SPEC.match(val)
                if not s:
                    raise BuildError(
                        f"{PRINCIPLES_SRC}:{lineno} src 写法不合规,应为 "
                        f"`chapters/<file>.md § <H2 标题> ¶ <段落锚点>`,实际:{val}")
                cur["src"].append(s.groupdict())
            elif key in ("merge", "conflict-with"):
                cur[key].extend([x.strip() for x in val.split(",") if x.strip()])
            else:
                cur[key] = val
            continue
        cur["body"].append(raw)
    if cur:
        entries.append(cur)
    if not entries:
        raise BuildError(f"{PRINCIPLES_SRC} 里一个条目都没有")
    return entries


def resolve_src(corpus, spec, ctx):
    """把一条 src 声明解析成 (小节, 逐字首段)。找不到或有歧义一律报错,不猜。"""
    sec = corpus.section(spec["rel"], spec["sec"])
    units = split_units(sec)
    hits = [u for u in units if any(spec["anchor"] in ln for ln in u["lines"])]
    if not hits:
        raise BuildError(f"{ctx}:在 {spec['rel']} § {spec['sec']} 里找不到段落锚点「{spec['anchor']}」")
    if len(hits) > 1:
        raise BuildError(
            f"{ctx}:段落锚点「{spec['anchor']}」在 {spec['rel']} § {spec['sec']} 里命中 "
            f"{len(hits)} 个条目,有歧义——请把锚点写长到唯一")
    excerpt = first_paragraph(hits[0]["lines"])
    if not excerpt:
        raise BuildError(f"{ctx}:段落锚点「{spec['anchor']}」命中的条目首段为空")
    return sec, excerpt


def build_principles(corpus, refs):
    entries = parse_principles_src()
    principles = [e for e in entries if e["id"].startswith("P")]
    conflicts = [e for e in entries if e["id"].startswith("C")]
    families = []
    for e in principles:
        if e["family"] and e["family"] not in families:
            families.append(e["family"])

    out = [BANNER, "", "# 原则层 · 可迁移的设计原则合集",
           "",
           "> **这份文档是什么**:《设计蓝图》各章「可迁移的设计原则」一节的合集,"
           "**以原则为条目重组,不以章为条目**。",
           "> 一条原则若在多章各说了一次,这里只出现一次,并列出它在哪几章被独立印证过——"
           "**被多章独立印证,本身就是这条原则强度的证据**。",
           ">",
           "> **为什么要脱章重组**:这一层的价值在于**脱离 hermes-agent 仍然成立**。"
           "按章排列会把原则绑回它被发现的那个子系统上;",
           "> 按原则排列才能看出「这条在四个互不相干的子系统里各被撞见一次」。",
           ">",
           "> **每条的「源出处」是机器抽取的**:引自成品章的文字逐字取自 `chapters/`,"
           "由 `scripts/build_reading_layer.py` 在构建时抽取,不经人手;",
           "> 「陈述」与「展开」是本轮的编辑产物(重新表述,不引入源章中不存在的新断言)。",
           ""]
    out.append(f"**规模**:{len(principles)} 条原则 · {len(families)} 个族 · "
               f"{len(conflicts)} 组跨章冲突已裁定。")
    out.append("")
    out.append("## 目录")
    out.append("")
    for fam in families:
        out.append(f"**{fam}**")
        out.append("")
        for e in principles:
            if e["family"] != fam:
                continue
            out.append(f"- [{e['id']} · {e['title']}](#{github_slug(e['id'] + ' · ' + e['title'], {})})"
                       f" —— 印证于 {len(e['src'])} 章")
        out.append("")
    if conflicts:
        out.append("**跨章冲突裁定**")
        out.append("")
        for e in conflicts:
            out.append(f"- [{e['id']} · {e['title']}](#{github_slug(e['id'] + ' · ' + e['title'], {})})")
        out.append("")

    for fam in families:
        out.append("---")
        out.append("")
        out.append(f"# 族:{fam}")
        out.append("")
        for e in principles:
            if e["family"] != fam:
                continue
            out.extend(render_entry(corpus, e, refs))

    if conflicts:
        out.append("---")
        out.append("")
        out.append("# 跨章冲突与裁定")
        out.append("")
        out.append("> 这里收录的是**两章各自成立、放在一起却互相拉扯**的原则对。"
                   "本项目的规矩是**点名并裁定,不静默取其一**——")
        out.append("> 静默取其一会让读者以为另一半不存在,而它明明在另一章里被独立论证过。")
        out.append("")
        for e in conflicts:
            out.extend(render_entry(corpus, e, refs, conflict=True))
    return "\n".join(out).rstrip() + "\n"


def render_entry(corpus, e, refs, conflict=False):
    out = ["---", "", f"## {e['id']} · {e['title']}", ""]
    body = [ln.rstrip() for ln in e["body"]]
    while body and not body[0]:
        body.pop(0)
    while body and not body[-1]:
        body.pop()
    if body:
        out.extend(body)
        out.append("")
    if e["merge"]:
        out.append(f"**合并**:{', '.join(e['merge'])}。{e['merge-why']}")
        out.append("")
    if e["conflict-with"]:
        out.append(f"**冲突对象**:{', '.join(e['conflict-with'])}")
        out.append("")
    if e["ruling"]:
        out.append(f"**裁定**:{e['ruling']}")
        out.append("")
    if e["scope"]:
        out.append(f"**适用边界**:{e['scope']}")
        out.append("")
    if e["note"]:
        out.append(f"**注**:{e['note']}")
        out.append("")
    label = "冲突两侧的原文" if conflict else "源出处"
    out.append(f"**{label}**(逐字抽取自成品章,勿手改):")
    out.append("")
    for spec in e["src"]:
        sec, excerpt = resolve_src(corpus, spec, f"{e['id']}")
        refs.add((spec["rel"], spec["sec"]))
        ch = corpus.chapter(spec["rel"])
        out.append(f"[第 {ch['no']} 章 · {ch['title']}]({corpus.link(spec['rel'], spec['sec'])})"
                   f" § {spec['sec']}")
        out.append("")
        out.extend(excerpt)
        out.append("")
    return out


# ---------------------------------------------------------------- 产物 3:问题索引

def parse_index_src():
    if not INDEX_SRC.exists():
        raise BuildError(f"缺少问题索引编辑源 {INDEX_SRC}")
    rows, order = {}, []
    with INDEX_SRC.open(encoding="utf-8") as fh:
        header = next(fh).rstrip("\r\n").split("\t")
        want = ["group", "problem", "chapter", "section", "why"]
        if header != want:
            raise BuildError(f"{INDEX_SRC} 表头应为 {want},实际 {header}")
        for lineno, raw in enumerate(fh, 2):
            if not raw.strip():
                continue
            row = raw.rstrip("\r\n").split("\t")
            if len(row) != 5:
                raise BuildError(f"{INDEX_SRC}:{lineno} 应有 5 列,实际 {len(row)}")
            group, problem, chapter, section, why = row
            key = (group, problem)
            if key not in rows:
                rows[key] = []
                order.append(key)
            rows[key].append((chapter, section, why))
    if not order:
        raise BuildError(f"{INDEX_SRC} 里一个条目都没有")
    return order, rows


def build_index(corpus, refs):
    order, rows = parse_index_src()
    groups = []
    for group, _problem in order:
        if group not in groups:
            groups.append(group)
    pointed = set()
    for key in order:
        for chapter, section, _why in rows[key]:
            pointed.add((chapter, section))

    out = [BANNER, "", "# 问题索引 · 从「我遇到了什么问题」进书",
           "",
           "> **这份文档是什么**:一份**倒排索引**——入口是**问题**,不是模块名。",
           "> 你在造自己的 harness 时撞见一个具体麻烦(模型返回空了、"
           "工具输出把上下文撑爆了、定时任务重启后跑了两遍……),",
           "> 从这里查它,直接落到某一章的某一节。",
           ">",
           "> **为什么入口必须是问题**:按模块名建的索引只有「已经知道答案在哪」的人用得上;",
           "> 而工作中真正的入口是**症状**。这一层的用途是随时检索,所以它按症状组织。",
           ">",
           "> 每条指向 `章 § 小节`,链接可点击可定位。链接与小节标题由 "
           "`scripts/build_reading_layer.py` 在构建时从 `chapters/` 解析,不手写。",
           ""]
    out.append(f"**规模**:{len(order)} 个问题入口 · {len(groups)} 个问题域 · "
               f"指向 {len({c for c, _ in pointed})} 章 / {len(pointed)} 个小节。")
    out.append("")
    out.append("## 问题域目录")
    out.append("")
    for g in groups:
        n = sum(1 for k in order if k[0] == g)
        out.append(f"- [{g}](#{github_slug(g, {})}) —— {n} 条")
    out.append("")

    for g in groups:
        out.append("---")
        out.append("")
        out.append(f"## {g}")
        out.append("")
        for key in order:
            if key[0] != g:
                continue
            out.append(f"### {key[1]}")
            out.append("")
            for chapter, section, why in rows[key]:
                title, sec = corpus.heading(chapter, section)
                refs.add((chapter, sec["title"]))
                ch = corpus.chapter(chapter)
                out.append(f"- [第 {ch['no']} 章 · {ch['title']} § {title}]"
                           f"({corpus.link(chapter, title)}) —— {why}")
            out.append("")

    # 未被任何问题指向的章,必须显式列出(验收项 3)
    unpointed = [(no, rel, title) for no, rel, rnd, title in corpus.order
                 if rel not in {c for c, _ in pointed}]
    out.append("---")
    out.append("")
    out.append("## 未被任何问题指向的章")
    out.append("")
    if not unpointed:
        out.append("**没有**——21 章每一章都至少被一个问题入口指到。")
    else:
        out.append("以下章没有出现在上面任何一条问题里。列出来而不是掩盖,"
                   "因为「查不到」和「没有」对读者是两回事:")
        out.append("")
        for no, rel, title in unpointed:
            out.append(f"- **第 {no} 章 · {title}**([`{rel}`]({corpus.link(rel)}))")
    out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------- 体量统计

def measure(text):
    """总字符数 / 去代码块后的正文字符数 / 按 350 字每分钟的阅读时长。"""
    total = len(text)
    body, in_fence = [], False
    for line in text.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            body.append(line)
    prose = len("\n".join(body))
    return total, prose, prose / READ_CPM


PRODUCTS = [
    ("reading/01-quickread.md", build_quickread),
    ("reading/02-principles.md", build_principles),
    ("reading/03-problem-index.md", build_index),
]


def build_all():
    corpus = Corpus()
    refs = set()
    built = []
    for rel, fn in PRODUCTS:
        built.append((rel, fn(corpus, refs)))
    return corpus, refs, built


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="重建并与库内产物比对(默认)")
    g.add_argument("--write", action="store_true", help="重建并写入 reading/")
    g.add_argument("--restamp", action="store_true", help="重钉 section-digests.tsv")
    g.add_argument("--stats", action="store_true", help="只打印体量统计")
    args = ap.parse_args()

    try:
        corpus, refs, built = build_all()
    except BuildError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    rows = collect_stamped_sections(corpus, refs)

    if args.restamp:
        write_digests(rows)
        print(f"restamped {len(rows)} sections -> {DIGESTS.relative_to(STUDY)}")
        return 0

    ok, problems = check_digests(rows)
    if not ok:
        for kind, rel, title, want, got in problems:
            print(f"{kind}\t{rel}\t{title}\twant={want[:16]}\tgot={got[:16]}", file=sys.stderr)
        print(f"FAIL: 源节钉子对不上({len(problems)} 处)。"
              f"确认重读过改动的小节后运行 --restamp。", file=sys.stderr)
        return 2

    if args.stats:
        tot_t = tot_p = tot_m = 0
        for rel, text in built:
            t, p, m = measure(text)
            tot_t, tot_p, tot_m = tot_t + t, tot_p + p, tot_m + m
            print(f"{rel}\ttotal={t}\tprose={p}\tminutes={m:.1f}")
        print(f"ALL\ttotal={tot_t}\tprose={tot_p}\tminutes={tot_m:.1f}")
        return 0

    if args.write:
        READING.mkdir(parents=True, exist_ok=True)
        for rel, text in built:
            (STUDY / rel).write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {rel} ({len(text)} chars)")
        return 0

    bad = 0
    for rel, text in built:
        p = STUDY / rel
        if not p.exists():
            print(f"PRODUCT-MISSING\t{rel}", file=sys.stderr)
            bad += 1
        elif p.read_text(encoding="utf-8") != text:
            print(f"PRODUCT-STALE\t{rel}", file=sys.stderr)
            bad += 1
    print(f"sections_stamped={len(rows)} products={len(built)} stale={bad}")
    if bad:
        print("FAIL: 产物与 chapters/ 不同步。核对后运行 --write。", file=sys.stderr)
        return 2
    print("OK: reading layer in sync with chapters/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
