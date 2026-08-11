#!/usr/bin/env python3
"""阅读层派生件关卡(R11E 立,**落地即阻断**)。

`reading/` 下三份派生件的真源是 `chapters/`。本关卡断言:**源改了而派生件没跟上,
提交不进去**。

## 四项检查

  1. `SECTION-DRIFT` —— 被引用到的每个成品章小节,按「H2 标题 + 节正文」重算 sha256,
     与 `data/r11e/section-digests.tsv` 的钉子比对。对不上即阻断。
     另有 `UNSTAMPED`(产物引了一个没钉过的小节)与 `STALE-STAMP`(钉了一个没人引的小节)。
  2. `PRODUCT-STALE` —— 用 `scripts/build_reading_layer.py` 重建三份产物,与库内文件**逐字**比对。
  3. `ANCHOR-UNRESOLVED` —— 产物里每一条指向 `../chapters/<file>.md#<slug>` 的链接,
     都要能解析回那一章里一个**真实存在**的标题。索引条目"可点击可定位"是验收项,
     那就得有人去点。
  4. `EMPTY-GATE` —— 上面任何一类的比对数为 **0** 即失败。

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

    # ---- 4. 非空绿守卫
    for label, n in (("sections", n_sections), ("products", n_products), ("links", n_links)):
        if n == 0:
            failures.append(f"EMPTY-GATE\t{label}=0\t(关卡没有比对任何东西,拒绝判绿)")

    if args.verbose:
        for rel, text in built:
            t, pr, mins = measure(text)
            print(f"  {rel}\ttotal={t}\tprose={pr}\tminutes={mins:.1f}")
        for rel, title, digest, nlines in rows:
            print(f"  stamped {digest[:12]}  {rel} § {title}  ({nlines} 行)")

    print(f"sections={n_sections} products={n_products} links={n_links} "
          f"failures={len(failures)}")
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
