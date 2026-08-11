#!/usr/bin/env python3
"""R11D · 点名覆盖率:本轮触及的文件清单被语料点到了没有(验收项 7)。

本轮触及的文件清单 = `data/chapter-order.tsv` 里的 **21 份成品章**(章序落库把它们
一次性全部点了名,这正是「其一」的产物)。

CLAUDE.md「『搜过没有』类测量必须报两个读数」:这类测量对**报告它**这个动作**不幂等**
—— 写一份点名清单,就会把下一次的读数抬上去。所以必须
(a) 剔除本轮承载清单/点名的文件,(b) 剔除与不剔除两个读数都报。

**承载文件**(本轮因为要报告这件事才点名的):`data/chapter-order.tsv`、
`notes/r11d-*`、`reports/round-11d-*`、`data/r11d/**`、以及 `scripts/verify_chapter_order.py`。

两种点名方式分开数,因为它们**不是同一个测量**:
  - **全路径**:`chapters/r8c-dashboard-and-web.md` —— 无歧义。
  - **裸文件名**:`r8c-dashboard-and-web.md` —— 成品章的文件名在本仓库唯一,
    所以对本清单而言裸名也定得住;但它在别的清单上不一定,故分开报。

用法:
    python3 data/r11d/probes/named_coverage_r11d.py
"""
import subprocess
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
CARRIER_PREFIX = ("data/chapter-order.tsv", "notes/r11d-", "reports/round-11d-",
                  "data/r11d/", "scripts/verify_chapter_order.py")


def tracked():
    out = subprocess.run(["git", "-C", str(STUDY), "ls-files"],
                         capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\n") if p]


def is_carrier(p):
    return any(p.startswith(c) for c in CARRIER_PREFIX)


def main():
    rows = []
    with (STUDY / "data" / "chapter-order.tsv").open(encoding="utf-8") as fh:
        for i, raw in enumerate(fh):
            if i:
                rows.append(raw.rstrip("\r\n").split("\t")[1])

    corpus = [p for p in tracked() if p.endswith((".md", ".py", ".tsv", ".sh"))]
    text = {}
    for p in corpus:
        try:
            text[p] = (STUDY / p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

    def zero_hits(needle_of, exclude_carrier):
        zero = []
        for target in rows:
            needle = needle_of(target)
            hit = False
            for p, body in text.items():
                if p == target:                      # 自己不算被点名
                    continue
                if exclude_carrier and is_carrier(p):
                    continue
                if needle in body:
                    hit = True
                    break
            if not hit:
                zero.append(target)
        return zero

    print(f"清单:data/chapter-order.tsv 的 {len(rows)} 份成品章")
    print(f"语料:{len(text)} 份 tracked 文本文件")
    print()
    for label, fn in (("全路径", lambda t: t),
                      ("裸文件名", lambda t: t.split("/")[-1])):
        for excl, tag in ((False, "不剔除承载清单"), (True, "剔除承载清单")):
            z = zero_hits(fn, excl)
            print(f"{label} / {tag}:零命中 {len(z)} 份"
                  + (f" -> {', '.join(z)}" if z else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
