#!/usr/bin/env python3
"""负控:原则层条目字段一致性检查(R11F-fix 第 5 项)。

要证的是三件事,每一件都**当场触发一次**、把真实输出打出来:

  F1  缺字段真的会红      —— 把 P60 的 `**陈述**` 从产物文本里摘掉,`FIELD-MISSING` 阻断。
  F2  删要求不能转绿      —— 把 `陈述` 从 `REQUIRED_FIELDS["P"]` 里删掉(边界明令禁止的那条路),
                            `FIELD-UNDECLARED` 立刻接管:它 64/64 全有,却不在声明里。
                            **这两条互相咬住,所以「缺字段」这条要求删不掉。**
  F3  空对象不判绿        —— 一份一条 `P` 都没有的产物,`EMPTY-GATE` 阻断,
                            而不是"零条目全部合规"式的假绿(R8C 记下的那个形状)。

外加 F4 正控:当前真产物零失败,且 `entries` 读数 > 0(绿必然伴随一个可当场核的 N)。

判据从 `scripts/verify_reading_layer.py` **import**,不另起口径 —— 两份实现迟早分叉,
而分叉的那天关卡会开始为一个只有它自己相信的口径打分(与 R11C 可跑性普查同理)。

    python3 data/r11f-fix/probes/principle_fields_negative_control.py
"""
import re
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(STUDY / "scripts"))

import verify_reading_layer as V   # noqa: E402
from build_reading_layer import build_all   # noqa: E402


def product_text():
    _corpus, _refs, built = build_all()
    for rel, text in built:
        if rel == V.PRINCIPLES_REL:
            return text
    raise SystemExit(f"FAIL: 构建结果里没有 {V.PRINCIPLES_REL}")


def show(tag, title, failures, hints, n, ok):
    print(f"\n{'=' * 78}\n{tag} · {title}\n{'=' * 78}")
    print(f"entries={n}  failures={len(failures)}")
    for f in failures[:6]:
        print("  " + f.replace("\t", "  "))
    if len(failures) > 6:
        print(f"  … 另有 {len(failures) - 6} 条")
    for h in hints:
        print("  HINT" + h)
    print(f"断言:{'PASS' if ok else '**FAIL**'}")
    return ok


def main():
    base = product_text()
    rows = []

    # ---- F1:摘掉 P60 的 **陈述** 段
    m = re.search(r"^## P60 · .*$", base, flags=re.M)
    seg_start = base.index("**陈述**", m.end())
    seg_end = base.index("\n\n", seg_start) + 2
    broken = base[:seg_start] + base[seg_end:]
    assert "**陈述**" in base and broken != base
    f, h, n = V.check_principle_fields(broken)
    rows.append(show("F1", "P60 缺 `**陈述**` -> FIELD-MISSING 阻断", f, h, n,
                     any(x.startswith("FIELD-MISSING") and "P60" in x for x in f)))

    # ---- F2:把 `陈述` 从声明里删掉 —— 边界明令禁止的那条转绿路径
    saved = V.REQUIRED_FIELDS["P"]
    V.REQUIRED_FIELDS["P"] = tuple(x for x in saved if x != "陈述")
    try:
        f, h, n = V.check_principle_fields(base)
    finally:
        V.REQUIRED_FIELDS["P"] = saved
    rows.append(show("F2", "从 REQUIRED_FIELDS 删掉「陈述」-> FIELD-UNDECLARED 接管", f, h, n,
                     any(x.startswith("FIELD-UNDECLARED") and "陈述" in x for x in f)))

    # ---- F3:一条 P 都没有的产物
    empty = re.sub(r"^## P\d+ · .*$", "## X1 · 不是原则条目", base, flags=re.M)
    f, h, n = V.check_principle_fields(empty)
    rows.append(show("F3", "产物里一条 `P` 都没有 -> EMPTY-GATE 阻断,不判假绿", f, h, n,
                     any(x.startswith("EMPTY-GATE") for x in f)))

    # ---- F4 正控
    f, h, n = V.check_principle_fields(base)
    rows.append(show("F4", "正控:当前真产物零失败,且 entries > 0", f, h, n,
                     not f and n > 0))

    print(f"\n{'=' * 78}")
    print(f"negative-control F1..F4   PASS={sum(rows)}/{len(rows)}  (F1..F3 负控 + F4 正控)")
    if not all(rows):
        print("FAIL: 有用例没有触发预期的判决")
        return 1
    print("OK: 三种形态均实际触发阻断(缺字段 / 删要求 / 空对象);正控零失败")
    return 0


if __name__ == "__main__":
    sys.exit(main())
