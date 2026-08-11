#!/usr/bin/env python3
"""阅读层派生件关卡(R11E 立,**落地即阻断**)。

`reading/` 下三份派生件的真源是 `chapters/`。本关卡断言:**源改了而派生件没跟上,
提交不进去**。

## 五项检查

  1. `SECTION-DRIFT` —— 被引用到的每个成品章小节,按「H2 标题 + 节正文」重算 sha256,
     与 `data/r11e/section-digests.tsv` 的钉子比对。对不上即阻断。
     另有 `UNSTAMPED`(产物引了一个没钉过的小节)与 `STALE-STAMP`(钉了一个没人引的小节)。
  2. `PRODUCT-STALE` —— 用 `scripts/build_reading_layer.py` 重建三份产物,与库内文件**逐字**比对。
  3. `ANCHOR-UNRESOLVED` —— 产物里每一条指向 `../chapters/<file>.md#<slug>` 的链接,
     都要能解析回那一章里一个**真实存在**的标题。索引条目"可点击可定位"是验收项,
     那就得有人去点。
  4. `FIELD-MISSING` / `FIELD-UNDECLARED` —— 原则层条目的**字段结构一致性**(R11F-fix 增)。
  5. `EMPTY-GATE` —— 上面任何一类的比对数为 **0** 即失败。

## 第 4 项:同一份产物内,同类条目的字段结构必须一致

`reading/02-principles.md` 的条目分两类:`P`(原则)与 `C`(跨章冲突裁定)。
每一类各有自己的一组字段(产物里表现为**行首的黑体引导词**)。R11F-fix 实测:
64 条 `P` 里 **59 条**有 `陈述`,而 `P60`~`P64` **一条都没有** —— 它们只有
`合并` 与机器抽取的 `源出处`,于是这五条把"这条原则说的是什么"整个交给了源章的原话。
**没有任何东西会报这件事**:产物是脚本生成的、锚点是逐字抽取的、章节钉子全对,
三道既有检查一条都够不到"条目之间长得不一样"这个形状。

判据分两半,**两半互相咬住**,所以不能靠删要求来转绿:

  * **`FIELD-MISSING`(阻断)**:每一类的**必备字段集**在 `REQUIRED_FIELDS` 里**显式声明**,
    该类的每一条都必须有。声明式,与本项目给表格锚点、给 ```text 豁免定的是同一条原则。
  * **`FIELD-UNDECLARED`(阻断,无阈值)**:一个字段若在某一类的**全部**条目里都出现,
    它就**必须**在 `REQUIRED_FIELDS` 里。于是把 `陈述` 从声明里删掉并不能让关卡变绿 ——
    删掉之后它仍然 64/64,立刻以 `FIELD-UNDECLARED` 回来。
    *这一条特意做成「100% ⇒ 必须声明」而不是「≥N% ⇒ 必须声明」:一个带阈值的判据,
    调阈值就是一条转绿的路,而 CLAUDE.md 明令不许那样转绿。代价是它发现不了
    「59/64」这种进行中的漂移 —— 所以另加一行**非阻断**的提示,把覆盖率 ≥50%
    却未声明的字段点名列出来,让下一次漂移在还是 59/64 的时候就被看见。*

**覆盖面要如实说**:本检查管的是**字段在不在**,不管字段里写得好不好。
「`陈述` 是不是只把源出处换句话说」这件事机器判不了,它由
`data/r11f-fix/probes/principle_statement_overlap.py` 报数、由人看。

## 第 4 项为什么必须有

一个什么都没比对的关卡也会打印绿字。R8C 记过这个形状:造一份 5 条引用全部正确、
只是把锚点写在代码块**之后**的文件,`verify_citations.py` 输出
`citations=5 UNCHECKED=5` + `OK: …` + **退出码 0** —— 一条都没校验,而关卡是绿的。
本关卡把三类比对数**打印出来**并在任何一类为 0 时失败,所以"绿"这个信号
必然伴随"比对了 N 处"这个读数,N 可以被读者当场核。

## 落地即阻断,不走分期

CLAUDE.md 里 R7C→R8A、R8C→R8D、R10B→R11A 那套「先报数、后升格」的分期,是为了
不让新关卡对着**自己没造成的历史积压**狂叫。本关卡守的三份产物是**本轮新增的**,
积压恒为 0,所以与 R9B 表格锚点、R11C 可跑性检查同例:落地即阻断。

    python3 scripts/verify_reading_layer.py
    python3 scripts/verify_reading_layer.py --verbose
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 判据一律从生产者 import,不另起口径:两份实现迟早会分叉,而分叉的那一天
# 关卡会开始为一个只有它自己相信的口径打分。
from build_reading_layer import (  # noqa: E402
    STUDY, DIGESTS, BuildError, Corpus, build_all, check_digests,
    collect_stamped_sections, measure,
)

LINK = re.compile(r"\]\(\.\./(?P<rel>chapters/[^)#\s]+\.md)(?:#(?P<slug>[^)\s]*))?\)")

PRINCIPLES_REL = "reading/02-principles.md"
# 条目头:`## P07 · …` / `## C03 · …`。种类就是 id 的字母前缀。
ENTRY_HEAD = re.compile(r"^## (?P<id>(?P<kind>[PC])\d+) · ", re.M)
# 字段 = **行首**的黑体引导词。行首这一条是全部的判据来源:正文中间的加粗是强调,
# 只有起一行的黑体才是这份产物用来标结构的东西(生产者 render_entry 就是这么写的)。
FIELD_LEAD = re.compile(r"^\*\*(?P<name>[^*\n]{1,16})\*\*", re.M)
# 每一类的必备字段集 —— **显式声明**,不从数据里推。改这张表是一次会进 diff 的动作。
REQUIRED_FIELDS = {
    "P": ("陈述", "源出处"),
    "C": ("冲突长什么样", "裁定", "冲突对象", "裁定摘要", "冲突两侧的原文"),
}
UNDECLARED_HINT_RATIO = 0.5   # 只用于**非阻断**的提示行,不参与任何判红


def principle_fields(text):
    """把产物切成条目,回 [(id, kind, {行首黑体字段名})]。"""
    heads = list(ENTRY_HEAD.finditer(text))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.end():end]
        out.append((m.group("id"), m.group("kind"),
                    {f.group("name") for f in FIELD_LEAD.finditer(body)}))
    return out


def check_principle_fields(text):
    """回 (failures, hints, n_entries)。判据见模块开头第 4 项。"""
    entries = principle_fields(text)
    failures, hints = [], []
    for kind, required in sorted(REQUIRED_FIELDS.items()):
        same = [(eid, fields) for eid, k, fields in entries if k == kind]
        if not same:
            failures.append(f"EMPTY-GATE\t{PRINCIPLES_REL}\t种类 {kind} 一条都没解析到,"
                            f"拒绝判绿(必备字段集非空却无对象可查)")
            continue
        for eid, fields in same:
            for name in required:
                if name not in fields:
                    failures.append(
                        f"FIELD-MISSING\t{PRINCIPLES_REL}\t{eid}\t缺字段「{name}」——"
                        f"同类 {len(same)} 条中另有 "
                        f"{sum(1 for _, f in same if name in f)} 条有它")
        universal = set.intersection(*(f for _, f in same)) if same else set()
        for name in sorted(universal - set(required)):
            failures.append(
                f"FIELD-UNDECLARED\t{PRINCIPLES_REL}\t种类 {kind}\t字段「{name}」在全部 "
                f"{len(same)} 条里都有,却不在 REQUIRED_FIELDS 里 —— 要么声明它,"
                f"要么说明为什么它是巧合")
        for name in sorted({n for _, f in same for n in f} - set(required) - universal):
            n = sum(1 for _, f in same if name in f)
            if n / len(same) >= UNDECLARED_HINT_RATIO:
                hints.append(f"      - 种类 {kind}:字段「{name}」{n}/{len(same)} "
                             f"= {n / len(same):.0%},未声明为必备")
    return failures, hints, len(entries)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    try:
        corpus, refs, built = build_all()
    except BuildError as exc:
        print(f"FAIL: 构建失败 —— {exc}", file=sys.stderr)
        return 2

    failures = []

    # ---- 1. 源节钉子
    rows = collect_stamped_sections(corpus, refs)
    ok, problems = check_digests(rows)
    for kind, rel, title, want, got in problems:
        failures.append(f"{kind}\t{rel}\t§ {title}\twant={want[:16]}\tgot={got[:16]}")
    n_sections = len(rows)

    # ---- 2. 产物逐字比对
    n_products = 0
    for rel, text in built:
        p = STUDY / rel
        if not p.exists():
            failures.append(f"PRODUCT-MISSING\t{rel}")
            continue
        n_products += 1
        if p.read_text(encoding="utf-8") != text:
            failures.append(f"PRODUCT-STALE\t{rel}\t(重建结果与库内文件逐字不一致)")

    # ---- 3. 锚点解析
    n_links = 0
    for rel, _text in built:
        p = STUDY / rel
        if not p.exists():
            continue
        for lineno, line in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
            for m in LINK.finditer(line):
                n_links += 1
                target, slug = m.group("rel"), m.group("slug")
                if not (STUDY / target).exists():
                    failures.append(f"ANCHOR-UNRESOLVED\t{rel}:{lineno}\t{target} 不存在")
                    continue
                if not slug:
                    continue
                ch = corpus.chapter(target)
                if slug not in set(ch["slugs"].values()):
                    failures.append(
                        f"ANCHOR-UNRESOLVED\t{rel}:{lineno}\t{target}#{slug} 解析不到标题")

    # ---- 4. 原则层条目的字段结构一致性
    n_entries, field_hints = 0, []
    for rel, text in built:
        if rel != PRINCIPLES_REL:
            continue
        f, field_hints, n_entries = check_principle_fields(text)
        failures.extend(f)

    # ---- 5. 非空绿守卫
    for label, n in (("sections", n_sections), ("products", n_products),
                     ("links", n_links), ("entries", n_entries)):
        if n == 0:
            failures.append(f"EMPTY-GATE\t{label}=0\t(关卡没有比对任何东西,拒绝判绿)")

    if args.verbose:
        for rel, text in built:
            t, pr, mins = measure(text)
            print(f"  {rel}\ttotal={t}\tprose={pr}\tminutes={mins:.1f}")
        for rel, title, digest, nlines in rows:
            print(f"  stamped {digest[:12]}  {rel} § {title}  ({nlines} 行)")

    if field_hints:
        print("HINT: 覆盖率过半却未声明为必备的字段(**不改退出码**;"
              "它是为了让下一次漂移在还没到 100% 时就被看见):")
        for h in field_hints:
            print(h)

    print(f"sections={n_sections} products={n_products} links={n_links} "
          f"entries={n_entries} failures={len(failures)}")
    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        print(f"FAIL: 阅读层与 chapters/ 不同步({len(failures)} 处)。"
              f"读过改动的小节后 `--restamp`,再 `--write`。", file=sys.stderr)
        return 2
    print("OK: reading layer derived from chapters/ and verified in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
