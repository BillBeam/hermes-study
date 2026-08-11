#!/usr/bin/env python3
"""R11F · 判定 R11E 那 60 条「转内容轮」里哪些真属于本轮(验收项 8 的前置)。

## 问题

R11E 片 C 把 114 条移交候选分成四档,其中 **60 条**判「不归属本轮·转内容轮」。
R11F 是 R11A 之后的**第一个内容轮**,于是这 60 条字面上全部落到本轮头上 ——
而 R11E 自己刚裁定过「**『下一轮』不是收件人**」:一条写给"下一轮"的移交项,
落到任何一轮都字面命中、实质未必相干。

**「内容轮」同样不是收件人。** 内容轮之间差别极大:R11F 读的是 `plugins/`,
而这 60 条里有大量是 `tools/` 的代码缺陷复核、`gateway/` 的重定向守卫、
装 extra 才能跑的编解码链路。把它们全领走是假装做了,全推走是假装没收到。

## 第一版为什么不成立(留在这里,因为它本身是本轮的一条结论)

第一版对 `anchor` 与 `one_line` 两栏抽路径,结果 **60 条里 58 条「锚点未解析到基线路径」**。
不是移交项没锚点,是**这张表里的 `anchor` 栏指的是「案子记在哪」(本仓库的
`notes/r11d-raw-handover-disposition.md:356` 之类),不是「案子指向哪段基线代码」**。
两者都叫"锚点",但只有后者能回答"这条归不归我这一轮"。

CLAUDE.md 的移交项格式明写要「锚点文件 + 一句话现象 —— 写清**在哪个文件**
(最好带行号)」;候选表满足了字面(有 anchor 栏、有 one_line 栏),
**丢掉的恰好是让下一轮能自己判断范围的那一半**。已铸 `H-R11F-M-a`。

## 判据(机械,只回答"锚点指向哪棵子树")

对每条**沿 `source` 栏回到它的原始记录行**(本仓库 `文件:行号`),读那一行,
从中抽出形如 `路径:行号` 或裸路径的片段,按**基线仓库的顶层目录**归类。
回源是必须的:候选表自己不带基线锚点(见上)。
**只判"指向哪里",不判"该不该做"** ——
后者在报告里逐条由人给结论(CLAUDE.md:「机械判据不得用词根去判开/闭这类语义」)。

三档输出:
  * `IN-SCOPE`   —— 锚点解析到 `plugins/` 下,且该文件在本轮 243 个文件清单里;
  * `PLUGIN-ADJ` —— 锚点解析到 `plugins/` 下,但**不在**本轮清单里
                    (例:`plugins/model-providers/` 是 R2 的,`plugins/memory/**/*.py` 是 R6 的);
  * `OUT`        —— 其余,附它指向的顶层目录,供报告逐条给条件式收件人。

    python3 data/r11f/probes/handover_scope_r11f.py
"""
import csv
import re
import sys
from collections import Counter
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
CAND = STUDY / "data/r11e/handover-candidates.tsv"
SCOPE = STUDY / "data/r11f/slices"
BASELINE = Path("/home/user/hermes-agent")

# 基线里的路径片段:至少一个 `/`,扩展名在白名单上(与 verify_citations.py 同源思路)
PATHY = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+\.(?:py|yaml|yml|md|mjs|js|ts|tsx|toml|json|sh|c|h))")


SRC = re.compile(r"^(?P<file>[\w./-]+\.md):(?P<line>\d+)$")
_cache: dict[str, list[str]] = {}


def src_line(source: str) -> str:
    """回到 source 指的那一行原始记录,返回其正文;解析不到返回空串。"""
    m = SRC.match(source.strip())
    if not m:
        return ""
    rel = m.group("file")
    if rel not in _cache:
        p = STUDY / rel
        _cache[rel] = p.read_text(encoding="utf-8").split("\n") if p.exists() else []
    lines = _cache[rel]
    i = int(m.group("line")) - 1
    return lines[i] if 0 <= i < len(lines) else ""


def main() -> int:
    scope = set()
    for f in sorted(SCOPE.glob("*.txt")):
        for line in f.read_text().splitlines():
            if line.strip():
                scope.add(line.split("\t")[0])
    if not scope:
        print("FAIL: 本轮文件清单为空", file=sys.stderr)
        return 2

    rows = list(csv.DictReader(CAND.open(newline=""), delimiter="\t"))
    target = [r for r in rows if r["verdict"] == "不归属本轮·转内容轮"]
    print(f"候选总数={len(rows)}  其中「转内容轮」={len(target)}  本轮文件清单={len(scope)}")

    buckets = {"IN-SCOPE": [], "PLUGIN-ADJ": [], "OUT": []}
    tops = Counter()
    unresolved_src = 0
    for r in target:
        blob = f"{r['anchor']} {r['one_line']} {src_line(r['source'])}"
        paths = [p for p in PATHY.findall(blob) if (BASELINE / p).exists()]
        if not src_line(r["source"]):
            unresolved_src += 1
        inb = [p for p in paths if p in scope]
        adj = [p for p in paths if p.startswith("plugins/") and p not in scope]
        if inb:
            buckets["IN-SCOPE"].append((r["case_id"], sorted(set(inb))))
        elif adj:
            buckets["PLUGIN-ADJ"].append((r["case_id"], sorted(set(adj))))
        else:
            t = sorted({p.split("/")[0] for p in paths}) or ["(锚点未解析到基线路径)"]
            buckets["OUT"].append((r["case_id"], t))
            for x in t:
                tops[x] += 1

    for k in ("IN-SCOPE", "PLUGIN-ADJ", "OUT"):
        print(f"\n=== {k}  {len(buckets[k])} 条 ===")
        for cid, info in sorted(buckets[k]):
            print(f"  {cid:<16} {', '.join(info)}")
    print("\nOUT 指向的顶层目录分布:")
    for t, n in tops.most_common():
        print(f"  {t:<16} {n}")
    print(f"\nsource 栏解析不到原始记录行的条数 = {unresolved_src}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
