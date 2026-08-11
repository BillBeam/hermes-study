#!/usr/bin/env python3
"""CLAUDE.md「每轮 commit 前必须运行的范围」的**单一落点**(R11F-fix 立,本轮第 4 项)。

## 它补的是什么洞

CLAUDE.md 把强制范围写成了一段**散文里的 shell**:

    python3 scripts/verify_citations.py /home/user/hermes-agent \\
        chapters/*.md reading/*.md notes/rN-*.md reports/round-N-*.md

于是「关卡实际跑了哪些文件」这件事**只存在于作者当时敲进终端的那一行里**,
既不在关卡的输出里,也不在任何检查面上。R11F 的收官报告 §11 把这一行记成

    verify_citations.py(定稿全量 = `chapters/` + 当轮 `notes/` + 本报告)

—— `reading/` 掉了。它是 R11E 才并进强制范围的一段(理由:成品章的锚点会被
逐字派生进快读层,**语料里带锚点却不在检查面上的东西,正是本项目反复栽的那一类**),
掉了之后关卡照样绿、报告照样报数,**没有任何东西会指出少跑了一段**。
R11F 报的 `citations=726 OK=589`(81.1%)因此测的是一个**比强制范围小**的语料。

修法与本项目给章号、给可复算数字定的是同一条:**立单一落点,让脚本去核对**。
范围写在这里一份,两道关卡都 `--round <N>` 从这里取;关卡把解析结果
(每一段各多少个文件)**打印出来**,于是一份报告里的引用读数自带它的取数范围。

## 空段即失败(EMPTY-SCOPE)

任何一段解析出 **0 个文件**就直接 FAIL,不静默跳过。理由与 R11E 给阅读层关卡定的
`EMPTY-GATE` 一字不差:**一个什么都没扫的关卡也会打印绿字**。少一段 `reading/`
正是 R11F 那次的形状 —— 空段必须是一次有声的失败,而不是一个更小的分母。

*(段本身不许在这里被"跳过"。要新增或删除一段,改的是这份表,而那是一次会进 diff、
会被评审看见的改动 —— 与「补一条 `<!-- derived: -->` 声明」是同一种可见性。)*

    from mandatory_scope import resolve, format_scope
    files, breakdown = resolve(["11f"])       # -> [Path, ...], [(段名, 模式, 个数)]
"""
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]

# 与 CLAUDE.md「每轮 commit 前必须运行的范围」逐字对应。顺序即报数顺序。
SEGMENTS = (
    ("chapters", "chapters/*.md"),          # 成品章全部
    ("reading", "reading/*.md"),            # 派生阅读层全部(R11E 并入)
    ("notes", "notes/r{round}-*.md"),       # 本轮底稿
    ("reports", "reports/round-{round}-*.md"),  # 本轮报告
)


def resolve(rounds):
    """把轮次号展开成 CLAUDE.md 强制范围的文件清单。

    rounds 是一个或多个轮次标识(如 ["11f"] 或 ["11f", "11f-fix"])。
    与轮次无关的两段(chapters / reading)只取一次。
    回 (files, breakdown);任一段为空即 SystemExit。
    """
    files, breakdown, seen = [], [], set()
    for name, pattern in SEGMENTS:
        if "{round}" in pattern:
            hits, shown = [], []
            for rnd in rounds:
                pat = pattern.format(round=rnd)
                shown.append(pat)
                hits.extend(sorted(STUDY.glob(pat)))
            pattern = " ".join(shown)
        else:
            hits = sorted(STUDY.glob(pattern))
        fresh = [p for p in hits if str(p) not in seen]
        seen.update(str(p) for p in fresh)
        breakdown.append((name, pattern, len(fresh)))
        files.extend(fresh)
    empty = [f"{n} ({p})" for n, p, c in breakdown if c == 0]
    if empty:
        raise SystemExit(
            "FAIL [EMPTY-SCOPE]: 强制范围里有段解析出 0 个文件 —— " + "; ".join(empty) +
            "\n      少跑一段不会让关卡变红,只会让分母变小(R11F 就是这么丢掉 reading/ 的)。"
            "\n      要么这一段真的不该在强制范围里(那就改 scripts/mandatory_scope.py 的"
            " SEGMENTS,让它进 diff),要么轮次号写错了。")
    return files, breakdown


def format_scope(rounds, breakdown):
    total = sum(c for _, _, c in breakdown)
    parts = "  ".join(f"{n}={c}" for n, _, c in breakdown)
    return f"scope=CLAUDE.md/mandatory round={','.join(rounds)}  files={total}  ({parts})"


def take_round_args(argv):
    """从 argv 里摘出 `--round <N>`(可重复,也可 `--round a,b`),回 (rounds, 剩余 argv)。"""
    rounds, rest, i = [], [], 0
    while i < len(argv):
        if argv[i] == "--round" and i + 1 < len(argv):
            rounds.extend(part for part in argv[i + 1].split(",") if part)
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    return rounds, rest


if __name__ == "__main__":
    import sys

    rounds, rest = take_round_args(sys.argv[1:])
    if not rounds:
        raise SystemExit(__doc__)
    files, breakdown = resolve(rounds)
    print(format_scope(rounds, breakdown))
    if "--list" in rest:
        for f in files:
            print(f.relative_to(STUDY))
