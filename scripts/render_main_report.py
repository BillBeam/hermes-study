#!/usr/bin/env python3
"""Render the main-volume capability chapter (section 二) from mining JSON.

Output: markdown to stdout. The full-detail appendix is rendered separately
by render_capabilities.py into reports/round-1-capabilities-full.md.
"""
import json
import re
import sys

COMPACT = "--compact" in sys.argv

VAL = {"high": "高", "medium": "中", "low": "低"}
# (module_idx, cap_idx) rendered in full detail in the showcase section
SHOWCASE = [(0, 1), (0, 9), (1, 2), (2, 5), (3, 1), (3, 7),
            (4, 0), (4, 10), (5, 0), (8, 4), (9, 0), (10, 4)]
SHOWCASE_COMPACT = [(0, 1), (0, 9), (1, 2), (3, 1), (4, 10), (5, 0), (8, 4), (10, 4)]
# curated significant standalone conflicts for compact mode: (module_idx, conflict_idx)



def first_sentence(text: str, limit: int = 88) -> str:
    s = re.split(r"[。;;]", text.strip())[0]
    return (s[:limit] + "…") if len(s) > limit else s


def short_scale(text: str, limit: int = 60) -> str:
    s = re.split(r"[。;;,]", text.strip())[0]
    return (s[:limit] + "…") if len(s) > limit else s


def render_full(c: dict) -> list[str]:
    out = []
    flags = []
    if c.get("hidden_from_docs"):
        flags.append("◇未见于文档")
    if c.get("doc_mismatch"):
        flags.append("▲文档不符")
    flag = ("  **[" + "、".join(flags) + "]**") if flags else ""
    out.append(f"\n**{c['name']}**{flag}\n")
    out.append(f"- 解决:{c['problem']}")
    out.append(f"- 实现:{c['implementation']}")
    evs = c.get("evidence", [])
    out.append("- 证据:" + " · ".join(f"`{e['loc']}`" for e in evs))
    if evs:
        lines = [ln.rstrip() for ln in evs[0]["excerpt"].strip("\n").splitlines()][:5]
        out.append("  ```")
        out.extend("  " + ln for ln in lines)
        out.append("  ```")
    out.append(f"- 规模:{c['scale']}")
    out.append(f"- 学习价值:{VAL[c['learning_value']]} — {c['learning_reason']}")
    if c.get("doc_mismatch"):
        out.append(f"- ▲ 文档不符:{c['doc_mismatch']}")
    return out


def main() -> None:
    data = json.load(open("data/capability-mining.json"))
    out = []
    ncaps = sum(len(m["capabilities"]) for m in data)
    nhid = sum(1 for m in data for c in m["capabilities"] if c.get("hidden_from_docs"))
    nmis = sum(1 for m in data for c in m["capabilities"] if c.get("doc_mismatch"))
    nconf = sum(len(m.get("doc_conflicts", [])) for m in data)
    out.append(
        f"由 14 路子系统并行深挖汇总:能力点 **{ncaps}** 个,其中 **◇ {nhid}** 个为『代码有、官方文档没讲』,"
        f"**▲ {nmis}** 个附带『文档宣称与代码不符』记录,另有 **{nconf}** 条独立文档-代码冲突(2.17 节收录重点,全量见附卷)。\n\n"
        f"呈现方式:本节(主卷)给出每个子系统的机制综述 + 全部能力点目录(问题/证据落点/规模/价值)+ 12 条跨子系统精选详述(2.16);"
        f"**每一条能力点的完整四要素与逐字代码摘录见附卷 `reports/round-1-capabilities-full.md`**(由 `data/capability-mining.json` 渲染,"
        f"约 37 万字符,超出单条消息承载,故拆卷)。证据可信度:从 14 路产出中抽样 15 条 `路径:行号` 断言逐一与基线源码比对,15/15 逐字命中。\n"
    )
    for mi, m in enumerate(data):
        out.append(f"\n### 2.{mi + 1} {m['module']}\n")
        out.append(m.get("overview", "").strip() + "\n")
        kf = m.get("key_files", [])
        if kf:
            tops = ", ".join(f"`{f['path']}`({f['lines']})" for f in kf[:6])
            out.append(f"关键文件(共 {len(kf)} 个,行数实测,全表见附卷):{tops} 等\n")
        out.append(f"**能力点目录(共 {len(m['capabilities'])} 条):**\n")
        showcase = SHOWCASE_COMPACT if COMPACT else SHOWCASE
        for ci, c in enumerate(m["capabilities"]):
            marks = ""
            if c.get("hidden_from_docs"):
                marks += " ◇"
            if c.get("doc_mismatch"):
                marks += " ▲"
            locs = c["evidence"][0]["loc"] if c.get("evidence") else "?"
            more = f" 等{len(c['evidence'])}处" if len(c.get("evidence", [])) > 1 else ""
            star = "★" if (mi, ci) in showcase else ""
            if COMPACT:
                out.append(
                    f"{ci + 1}. **{c['name']}**{marks}{star} — `{locs}`{more};{VAL[c['learning_value']]}。"
                )
            else:
                out.append(
                    f"{ci + 1}. **{c['name']}**{marks}{star} — {first_sentence(c['problem'])}。"
                    f"证据:`{locs}`{more};规模:{short_scale(c['scale'])};价值:{VAL[c['learning_value']]}。"
                )
    if COMPACT:
        out.append("\n### 2.15 精选详述(8 条,★ 标于上文目录;全部 170 条完整四要素详述见仓库主卷与附卷)\n")
        for mi, ci in SHOWCASE_COMPACT:
            out.extend(render_full(data[mi]["capabilities"][ci]))
    else:
        out.append("\n### 2.15 精选详述(12 条,★ 标于上文目录;全部 170 条同格式详述见附卷)\n")
        for mi, ci in SHOWCASE:
            out.extend(render_full(data[mi]["capabilities"][ci]))
    # conflicts
    all_conflicts = [cf for m in data for cf in m.get("doc_conflicts", [])]
    if COMPACT:
        shown = all_conflicts[:20]
        out.append(f"\n### 2.16 文档-代码冲突(独立条目,共 {len(all_conflicts)} 条;此处 20 条,全量见仓库主卷 2.16)\n")
    else:
        shown = all_conflicts
        out.append(f"\n### 2.16 文档-代码冲突汇总(独立冲突条目,共 {len(all_conflicts)} 条)\n")
        out.append("以下为矿工在能力点之外单独记录的全部独立冲突(压缩为单句;完整版含上下文见 JSON);与能力点绑定的 ▲ 条目见各自目录项。\n")
    for k, cf in enumerate(shown, 1):
        out.append(
            f"{k}. {first_sentence(cf['claim'], 130)} → **实际**:{first_sentence(cf['reality'], 130)}"
            f"(`{cf['evidence_loc']}`)"
        )
    out.append("\n### 2.17 全局观察(跨子系统)\n")
    out.append(
        "1. **恢复阶梯 + 一次性守卫**是全仓最一致的工程签名:空响应、截断、限流、OAuth 失效、流中断、更新失败、平台断连——"
        "每种失败都有专用有界重试阶梯,并用一次性布尔守卫防死循环(`agent/turn_retry_state.py:43`、`hermes_cli/update_cmd.py` 等)。\n"
        "2. **prompt cache 字节级稳定**是贯穿性设计约束(api_content 侧车、冻结记忆快照、缓存感知斜杠命令、压缩滞回),"
        "AGENTS.md 将其列为最高设计红线,代码与宣称一致——这是少数『文档与代码高度一致』的主题。\n"
        "3. **单体巨文件 + 循环依赖 + 函数内延迟 import** 是快速演化的代价;全仓约 30 个 >2000 行的 Python 文件承载了核心机制,"
        "学习必须以机制为单位切片,而非以文件为单位。\n"
        "4. **安全层出乎意料地厚**:命令审批、SSRF DNS 钉扎、威胁模式扫描、secret 卫生、供应链钉死、注入围栏散布在每个子系统,"
        "而官方 README 只轻描淡写提 security 一页——◇ 类能力点近三分之一与安全相关。\n"
    )
    print("\n".join(out))


if __name__ == "__main__":
    main()
