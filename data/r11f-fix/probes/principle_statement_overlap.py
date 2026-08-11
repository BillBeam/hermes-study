#!/usr/bin/env python3
"""探针:原则层「陈述」的两种重复度(R11F-fix 第 5 项的内容侧证据)。

字段关卡只管**字段在不在**。而本轮补的五条 `陈述` 还要满足两条内容要求:
**不与既有条目重复**、**不只是源出处的换句话说**。这两条机器判不了对错,
但**判得了程度** —— 本探针把两个比值算出来,让"新补的五条有没有比既有条目更像"
成为一个可当场核的数,而不是作者的自我评价。

两个读数(都用**字符 3-gram 的 Jaccard 交比**,中文按字切,先剥掉 markdown 与标点):

  echo   陈述 与**它自己那条**「源出处」逐字块的重合度 —— 高 = 换句话说
  twin   陈述 与**其它每一条**陈述的最高重合度 —— 高 = 与既有条目重复

判据是**分布**,不是阈值:R11F-fix 之前就存在的 59 条给出参照带,
新补的 5 条(P60~P64)必须落在带内。**这不是一道关卡**,它不改任何退出码 ——
一个靠阈值判"写得像不像"的关卡,调阈值就是一条转绿的路。

    python3 data/r11f-fix/probes/principle_statement_overlap.py
"""
import re
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(STUDY / "scripts"))

from build_reading_layer import build_all   # noqa: E402
from verify_reading_layer import ENTRY_HEAD, PRINCIPLES_REL   # noqa: E402

NEW = {"P60", "P61", "P62", "P63", "P64"}
DROP = re.compile(r"[\s`*\[\]()·—…:：,、。;;!!??\"'「」『』()<>/#|\-]+")


def grams(s, n=3):
    s = DROP.sub("", s)
    return {s[i:i + n] for i in range(len(s) - n + 1)} if len(s) >= n else set()


def jaccard_in(a, b):
    """a 有多少落在 b 里(方向性交比,不是对称 Jaccard):|a∩b| / |a|。"""
    ga, gb = grams(a), grams(b)
    return len(ga & gb) / len(ga) if ga else 0.0


def split_entries(text):
    heads = list(ENTRY_HEAD.finditer(text))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        yield m.group("id"), m.group("kind"), text[m.end():end]


def parts(body):
    """回 (陈述段, 源出处整块)。源出处从 `**源出处**` 那行之后一直到条目末尾。"""
    st = ""
    m = re.search(r"^\*\*陈述\*\*(.*?)(?=\n\n)", body, flags=re.M | re.S)
    if m:
        st = m.group(1)
    k = body.find("**源出处**")
    src = body[k:] if k >= 0 else ""
    return st, src


def band(vals):
    v = sorted(vals)
    n = len(v)
    return v[0], v[n // 2], v[-1]


def main():
    _c, _r, built = build_all()
    text = next(t for rel, t in built if rel == PRINCIPLES_REL)
    rows = []
    for eid, kind, body in split_entries(text):
        if kind != "P":
            continue
        st, src = parts(body)
        if not st:
            print(f"FAIL: {eid} 没有 **陈述** —— 本探针假定字段关卡已经过了")
            return 1
        rows.append((eid, st, src))

    stmts = {eid: st for eid, st, _ in rows}
    out = []
    for eid, st, src in rows:
        echo = jaccard_in(st, src)
        twin = max((jaccard_in(st, other) for oid, other in stmts.items() if oid != eid),
                   default=0.0)
        twin_id = max(((jaccard_in(st, other), oid) for oid, other in stmts.items()
                       if oid != eid), default=(0.0, "-"))[1]
        out.append((eid, echo, twin, twin_id))

    old = [(e, t) for eid, e, t, _ in out if eid not in NEW]
    new = [(eid, e, t, w) for eid, e, t, w in out if eid in NEW]
    print(f"P 条目 {len(out)} 条:既有 {len(old)} 条为参照带,新补 {len(new)} 条受检\n")
    for label, idx in (("echo(与自己的源出处)", 0), ("twin(与其它条目的最高值)", 1)):
        lo, mid, hi = band([p[idx] for p in old])
        print(f"{label:28s} 既有 59 条:min={lo:.3f}  中位={mid:.3f}  max={hi:.3f}")
    print()
    print(f"{'条目':6s} {'echo':>7s} {'twin':>7s}  最像的那一条")
    for eid, e, t, w in sorted(new):
        print(f"{eid:6s} {e:7.3f} {t:7.3f}  {w}")
    print()
    e_lo, e_mid, e_hi = band([p[0] for p in old])
    t_lo, t_mid, t_hi = band([p[1] for p in old])
    over_max = [eid for eid, e, t, _ in new if e > e_hi or t > t_hi]
    over_mid = [eid for eid, e, t, _ in new if e > e_mid or t > t_mid]
    print(f"既有 59 条的上界:echo<={e_hi:.3f}  twin<={t_hi:.3f}")
    print(f"既有 59 条的中位:echo={e_mid:.3f}  twin={t_mid:.3f}")
    if over_max:
        print(f"**超出上界**:{', '.join(over_max)} —— 需要人看一眼是不是真的重复了")
    elif over_mid:
        print(f"落在带内但高于中位:{', '.join(over_mid)} —— 值得人再读一遍")
    else:
        print("新补五条在**两个读数上都低于既有 59 条的中位**:"
              "它们比典型的既有条目**更不像**自己的源出处,也**更不像**别的条目。"
              "「落在带内」是弱结论,「全部低于中位」才是这次要报的那一个。")
    print(f"\n*参照带本身要如实说:既有条目里 echo 的最大值是 {e_hi:.3f}"
          f"(存在陈述被其源出处逐字覆盖的条目),所以「不超上界」几乎不构成约束;"
          f"上面用的是中位。这条参照带的下限由 R11F-fix 记录,不代表既有条目都写得好。*")
    print("\n(本探针不改退出码:它报的是程度,不是对错。)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
