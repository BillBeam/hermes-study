#!/usr/bin/env python3
"""R11E · 把片 A / 片 B 的问题索引候选合并成 `data/r11e/problem-index.tsv`。

两片各读一半成品章(A:第 1–11 章;B:第 12–21 章),用**同一份固定域词表**产出候选。
词表统一是合并的前提,但**措辞不会自动一致**:片 A 收工时就点明了这一点 ——
`group` + `problem` 两列逐字相同才会被产品合并成一个条目,于是**措辞就是主键**,
而两片各自独立写出来的同一个问题必然写法不同。实测:合并前
**A 118 问题 / B 115 问题,逐字相同的 0 个**。

## 归一化表是**声明式**的

下面 `CANON` 里每一条写明:把哪一片的哪句话,改写成哪一句。**不做模糊匹配、不算相似度**
—— 一个靠相似度合并的索引会把两个不同的问题并成一个,而读者无从发现。
判据与本项目给表格锚点、给 ```text 豁免定的一样:**声明,不靠嗅探**。

归一化只做两件事:改 `problem` 文本,或改 `group` 归属。**不删行、不改 chapter/section/why**
—— 那三列是两片各自的取证结果,主线无权替它们改。

## 合并后仍然分开的近义问题

有意保留而没有合并的,在 `KEPT_APART` 里逐条写明理由。这一份和 `CANON` 一样重要:
一个只记录「合并了什么」的表,读者无法判断「没合并的是漏了还是有意的」。

用法:
    python3 data/r11e/probes/merge_problem_index.py            # 打印合并账
    python3 data/r11e/probes/merge_problem_index.py --write    # 写 data/r11e/problem-index.tsv
"""
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[3]
A = STUDY / "data" / "r11e" / "index-a.tsv"
B = STUDY / "data" / "r11e" / "index-b.tsv"
OUT = STUDY / "data" / "r11e" / "problem-index.tsv"

VOCAB = [
    "模型与推理调用", "工具与执行", "会话、状态与上下文", "接入与多平台",
    "配置与凭据", "安全、权限与边界", "可靠性、故障与恢复",
    "部署、运维与升级", "界面与客户端", "工程方法与项目治理",
]

# (来源片, 原 group, 原 problem) -> (新 group, 新 problem)
CANON = {
    # M1 副本漂移:两片各写了一遍同一个问题
    ("B", "工程方法与项目治理", "同一件事写了两遍,两份悄悄漂开了,怎么在漂的那一刻就发现?"):
        ("工程方法与项目治理", "同一个语义在仓库里有好几份实现,怎么防止它们悄悄分叉?"),
    # M2 文档不腐烂
    ("B", "工程方法与项目治理", "同样是文档,为什么有的一年就烂了,有的一条断言都没错?"):
        ("工程方法与项目治理", "怎么才能让文档不腐烂,除了靠自觉还有别的手段吗?"),
    # M3 文档与代码冲突:片 B 的问法侧重「画错还是没画」,是同一个入口的下位问题
    ("B", "工程方法与项目治理", "文档跟代码对不上,怎么分辨地图画错了还是地图没画这一块?"):
        ("工程方法与项目治理", "文档和代码对不上时该信谁,冲突要怎么记录才不白费?"),
    # M4 抓回来的文本里藏指令
    ("B", "安全、权限与边界", "网页搜索回来的文本里藏着指令,模型会照着做吗?"):
        ("安全、权限与边界", "抓回来的网页里藏着忽略之前的指令,进上下文之前该做什么?"),
    # M5 升级半途崩:两片连**域**都判得不同。归到「部署、运维与升级」——
    #    升级是交付链上的动作,把它放进「可靠性」会让读者在故障域里找部署问题。
    ("B", "可靠性、故障与恢复", "升级到一半断电,连 import 都失败了,程序怎么自己救自己?"):
        ("部署、运维与升级", "升级到一半崩了,连修复命令都敲不进去怎么办?"),
    # M6 prompt cache:A 问「什么会弄脏」,B 问「索引该放哪」,是同一条缓存不变量的两端
    ("B", "模型与推理调用", "能力包索引一变提示词缓存就全废,它该放在提示词的哪个位置?"):
        ("模型与推理调用", "长对话的 prompt 缓存老是失效,哪些操作会把它弄脏?"),
    # M7 多平台抽象
    ("B", "接入与多平台", "20 多个平台的消息长度上限和限流各不相同,该怎么抽象?"):
        ("接入与多平台", "我要支持很多聊天平台,又不想让差异漏进内核,该怎么抽象?"),
}

# 近义但**有意不合并**的,逐条写明理由(读者要能判断没合并是有意的)
KEPT_APART = [
    ("A 模块写好了、测试也绿,怎么确认它真的被接线调用过?",
     "B 守卫写好了却有一条路不问它,这种漏接怎么数出来?",
     "前者问「这个模块有没有人调」,后者问「这道守卫有几条路绕过」——"
     "分母不同(模块 vs 路径),落点也不同(工程方法 vs 安全)。合并会让安全那条失去它的域。"),
    ("A 功能坏了,现象却和一切正常长得一模一样,这类静默失败怎么抓?",
     "B 测试全绿,可它其实什么都没验,这种情况怎么发现?",
     "前者是**产品**的静默失败,后者是**测试**的静默失败。读者带着这两种处境来时,"
     "想看的不是同一批小节。"),
    ("A 我想让 agent 跨会话记住用户的偏好,这套记忆该怎么接进来、存在哪?",
     "B 上一次会话摸索出来的经验,下一次怎么还能用得上?",
     "前者是记忆 provider 的接入(第 6 章一族机制),后者是学习产出/技能沉淀"
     "(第 14 章)。同样是「跨会话」,机制完全不同。"),
    ("A 一条回复里有 emoji,平台却说超长拒收,该怎么数长度、怎么切?",
     "B(已并入 M7 的那条)",
     "M7 并的是**抽象层怎么设计**;这一条问的是**一次具体拒收怎么排查**。"
     "保留它,是因为倒排索引的入口应当允许「我现在正卡在这」这种具体处境。"),
]


def load(path, tag):
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").split("\n")):
        if not i or not line.strip():
            continue
        f = line.split("\t")
        if len(f) != 5:
            sys.exit(f"FAIL: {path.name} 第 {i+1} 行 {len(f)} 列")
        rows.append((tag, *f))
    return rows


def main():
    rows = load(A, "A") + load(B, "B")
    before = {(g, p) for _t, g, p, _c, _s, _w in rows}

    out, applied = [], set()
    for tag, g, p, ch, sec, why in rows:
        key = (tag, g, p)
        if key in CANON:
            g, p = CANON[key]
            applied.add(key)
        if g not in VOCAB:
            sys.exit(f"FAIL: 域「{g}」不在词表里")
        out.append((g, p, ch, sec, why))
    after = {(g, p) for g, p, _c, _s, _w in out}

    unused = set(CANON) - applied
    if unused:
        for u in sorted(unused):
            print(f"  [BAD] 归一化表里有一条没匹配上(原文可能被改过):{u}")
        sys.exit("FAIL: 归一化表与候选文件对不上")

    # 排序:域按词表次序;域内问题按它指向的**最小章号**,让索引在域内大致按书序走
    chapter_no = {}
    order_rows = (STUDY / "data" / "chapter-order.tsv").read_text(encoding="utf-8").split("\n")
    for r in order_rows[1:]:
        if r.strip():
            f = r.split("\t")
            chapter_no[f[1]] = int(f[0])
    first_ch, first_seen = {}, {}
    for i, (g, p, ch, _s, _w) in enumerate(out):
        k = (g, p)
        first_ch[k] = min(first_ch.get(k, 99), chapter_no.get(ch, 99))
        first_seen.setdefault(k, i)
    out.sort(key=lambda r: (VOCAB.index(r[0]), first_ch[(r[0], r[1])],
                            first_seen[(r[0], r[1])]))

    n_cross = sum(1 for k in after
                  if len({chapter_no[r[2]] for r in out if (r[0], r[1]) == k}) > 1)
    print(f"合并前:A+B 共 {len(rows)} 行 / {len(before)} 个问题(逐字相同的 0 个)")
    print(f"归一化:{len(CANON)} 条(全部命中)")
    print(f"合并后:{len(out)} 行 / {len(after)} 个问题;跨章问题 {n_cross} 个")
    print(f"有意不合并的近义对:{len(KEPT_APART)} 组(理由见本脚本 KEPT_APART)")
    dist = {}
    for g, p, *_ in out:
        dist.setdefault(g, set()).add(p)
    print("\n域分布(不同问题):")
    for g in VOCAB:
        print(f"  {g:<22}{len(dist.get(g, ())):>4}")

    if "--write" in sys.argv:
        with OUT.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write("group\tproblem\tchapter\tsection\twhy\n")
            for r in out:
                fh.write("\t".join(r) + "\n")
        print(f"\nwrote {OUT.relative_to(STUDY)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
