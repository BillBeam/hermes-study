#!/usr/bin/env python3
"""R11E 片 C:生成 `data/r11e/handover-candidates.tsv`。

**分工写死**:锚点、案号、来源行号一律**机械取自** `handover_scope_r11e.py`
(它读 R11D 的两份定案层文件),**不手抄** —— 手抄一个行号,下一轮就找错地方。
`verdict` 与 `one_line` 是**人写的判断**,写在本文件的 `JUDGED` / 组规则里,
一条一条对得上底稿 `notes/r11e-raw-handover.md` 的论证。

判开闭 / 判归属是人的事(`CLAUDE.md`「机械判据不得用词根去判『开/闭』这类语义」);
本脚本只做两件机械的事:**取锚点** 和 **保证一个案号只出一行**。

    python3 data/r11e/probes/handover_candidates_r11e.py           # 打到 stdout
    python3 data/r11e/probes/handover_candidates_r11e.py --check   # 只自检,不输出表
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = pathlib.Path(subprocess.run(
    ["git", "-C", str(HERE.parent), "rev-parse", "--show-toplevel"],
    capture_output=True, check=True).stdout.decode().strip())

_spec = importlib.util.spec_from_file_location(
    "handover_scope_r11e", HERE.parent / "handover_scope_r11e.py")
scope = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scope)

V_DONE = "本轮结清"
V_PART = "本轮部分结清"
V_R12 = "不归属本轮·转R12装订"
V_CONTENT = "不归属本轮·转内容轮"
V_OPEN = "存疑·交主线裁定"
VOCAB = {V_DONE, V_PART, V_R12, V_CONTENT, V_OPEN}

# ---------------------------------------------------------------- 组规则
# 键 = R11D 那一格「处置结论 / 去向」的开头(剥 ** 之后);值 = (verdict, 理由后缀)。
# 组规则只覆盖**去向已经点名了一个非本轮收件人**的条目;凡去向写「下一轮」这类
# 未点名收件人的,一律落到 JUDGED 里逐条判 —— 因为「下一轮」恰好就是本轮。
GROUPS: list[tuple[str, str, str]] = [
    ("转 代码缺陷复核轮", V_CONTENT,
     "R11D 判「转代码缺陷复核轮」,要读基线代码并实跑复现;本轮不吃新内容,不动基线"),
    ("转「装 extra 轮」", V_CONTENT,
     "R11D 判「转装 extra 轮」,要装可选依赖后跑基线用例;本轮禁装包、禁动 venv"),
    ("转 配置面普查轮", V_CONTENT,
     "要对 151 条静态环境变量逐条在基线找读取方,是内容工作;本轮不吃新内容"),
    ("转 名单手抄点普查轮", V_CONTENT,
     "要在基线搜硬编码 provider/toolset 名单并与目录扫描对表,是内容工作"),
    ("转 有容器环境的轮次", V_CONTENT,
     "要在 Docker 容器内造软链实跑读禁绕过;本容器无 Docker,且本轮不跑基线"),
    ("转 任何能跑前端工具链的一轮", V_CONTENT,
     "要 npm ci 后比对 tsc -b 与 npm run typecheck;本轮禁装任何包"),
    ("转 需要复用 ■-R9A-01", V_CONTENT,
     "要重写五个 env-loader 场景探针并实跑基线取读数,是内容工作"),
    ("转 R12 装订", V_R12,
     "R11D 判「转 R12 装订」,落点在 chapters/ 正文或装订期口径;本轮 chapters/ 零改动"),
    ("转 R12 前置(锚点收口)", V_R12,
     "R11D 判「R12 前置(锚点收口)」,是装订前的锚点批处理;本轮无锚点片,历史 notes/ 不动"),
    ("转 R12 前置(撞号收口)", V_R12,
     "R11D 判「R12 前置(撞号收口)」,要给实体改号并回改全部引用点;本轮不做跨文件改号"),
    ("转 R12 前置", V_R12,
     "R11D 判「R12 前置」;要定的写法要改 CLAUDE.md 成品章硬标准 8 并回改 264 处,不在本轮范围"),
]

# ---------------------------------------------------------------- 逐条判
# 去向写「下一轮 / 任一轮 / 下一个动 scripts 的轮次」这类**未点名收件人**的条目。
# 「下一轮」在 R11D 落笔时还没有收件人,而它落到的这一轮是阅读层轮 —— 所以每条都要
# 回答同一个问题:本轮到底做没做。做没做以**产物与提交**为准,不以去向措辞为准。
_S = "本轮(截至 701945d)未做:"
JUDGED: dict[str, tuple[str, str]] = {
    # —— 落在 scripts/ 关卡侧的六条 + 两条 R11D 新铸 ——
    "H-R11C-C-a": (V_OPEN, "去向「下一个动 scripts/ 的轮次」;" + _S
                   + "本轮确实动了 scripts/(新增 build_reading_layer.py / verify_reading_layer.py),"
                     "但未碰 verify_evidence_commands.py 的 NOFENCE。字面命中、实质未做,收件人请主线重指"),
    "H-R11C-C-e": (V_OPEN, "去向「下一个动 scripts/ 的轮次」;" + _S
                   + "REDIRECT_WRITE 仍把输出里的 -> 读成写重定向。同 H-R11C-C-a,字面命中、实质未做"),
    "H-R11C-D-c": (V_OPEN, "去向「下一个动 scripts/ 的轮次」;" + _S
                   + "verify_citations.py 未加「根遮蔽」提示档。同上"),
    "H-R11C-D-i": (V_OPEN, "去向「下一个动 scripts/ 的轮次」;" + _S
                   + "CITE 正则未加左侧 lookbehind、未立 ABSOLUTE 档。同上"),
    "H-R11B-D-a": (V_OPEN, "去向「下一个动 scripts/ 的轮次」;" + _S
                   + "未立 NON-BASELINE 档。**并请主线并案**:与 R11D 主线新铸的 H-R11D-M-c "
                     "是同一实体(同一份 notes/r6-60、同样 3 处第三方包锚点、同一条修法)"),
    "H-R11B-D-b": (V_OPEN, "去向「下一个动 scripts/ 的轮次」;" + _S
                   + "校验器仍不识别「每行以自己行号开头」的行号栏块,R11B 临时改标的 ```text 未改回"),
    "H-R11D-M-c": (V_OPEN, "R11D 主线新铸,去向「加第三个根」;" + _S
                   + "resolve() 仍只认两棵树。与 H-R11B-D-a 同一实体,请主线并成一个号"),
    "H-R11D-C-c": (V_OPEN, "去向「把移交普查收进 scripts/ 的那一轮」;" + _S
                   + "本片沿用 R11D 探针(import 不改),未把它提升为 scripts/verify_handover_ledger.py，"
                     "也未跑 97→306 的前后对比"),
    # —— 落在制度位 / 派工书 / 开工杂项的六条 ——
    "H-R11C-M-a": (V_OPEN, "去向自写「下一轮的开工杂项(制度位)」,而本轮开工杂项已落"
                   "(b39fe88 只入册了阅读层制度条);铸号单一落点未立,那张 64 条登记表未执行"),
    "H-R11C-C-d": (V_OPEN, "去向「下一轮制度位」,本轮 CLAUDE.md 改了但未写入「省略号只能省别处逐字写过的部分」,"
                   "也未量全语料含省略号的 verify 块数"),
    "H-R11C-C-b": (V_OPEN, "去向「下一轮派工书」;仓库内无 data/r11e/dispatch-brief.md(R11D 同样未留),"
                   "「证据块不得依赖另一个块产生的文件」是否写进本轮派工书**无法机械核验**"),
    "H-R11C-E-d": (V_OPEN, "去向「下一轮派工书」,要就地更正 data/r10/dispatch-brief.md 里 R8C 已推翻的「静默」定性;"
                   "本轮提交面不含 data/r10/"),
    "H-R11B-B1-e": (V_OPEN, "去向「下一轮开工杂项」,要把片 B1 12 个 + 片 B2 26 个文件的 status 改 R11B-deep-read;"
                    "本轮提交面不含 data/ledger.tsv"),
    "H-R11D-C-a": (V_OPEN, "R11D 新铸:机械口径把「已处置」等同「已结清」,要给移交表加机器可读的「后续」列;"
                   "本片产出的 TSV 恰好是这种列的一次实做(verdict 五选一),但既未入册也未改普查器,是否算部分结清交主线"),
    # —— R11D 片 A 的五条,去向一律只写「下一轮」——
    "H-R11D-A-a": (V_OPEN, "R11D 片 A 铸,去向只写「下一轮」;" + _S
                   + "散文里的三反引号仍会翻转其后整份文件的围栏奇偶,修法在 verify_citations.py"),
    "H-R11D-A-b": (V_OPEN, "R11D 片 A 铸,去向只写「下一轮」;" + _S
                   + "「一个锚点挂五处合成摘录」算不算合法锚点形态,本轮未定"),
    "H-R11D-A-c": (V_OPEN, "R11D 片 A 铸,去向只写「下一轮」;" + _S
                   + "use-mention 盲区未入册为「同类批量作业须有人工复核环节」"),
    "H-R11D-A-d": (V_OPEN, "R11D 片 A 铸,去向只写「下一轮」;" + _S
                   + "reviews/ 那处无钉子自引锚点仍报 not found,按裁定不改 reviews/ 正文"),
    "H-R11D-A-e": (V_OPEN, "R11D 片 A 铸,去向只写「下一轮」;" + _S
                   + "reports 87 + reviews 17 = 104 处多候选裸锚点一处未动"),
    # —— 其余逐条 ——
    "H-R11C-C-f": (V_OPEN, "去向「下一轮证据清理位」,5 处配对 verify 块漂移分散在 5 份历史底稿;"
                   "本轮无证据清理片,历史 notes/ 按边界不动"),
    "H-R11C-E-e": (V_OPEN, "去向「下一轮 notes 锚点位」,要把 notes/r11b-raw-rulings-census.md 表内 :700 改 :730 并补声明式摘录;"
                   "本轮提交面不含该文件"),
    "H-R11C-E-f": (V_OPEN, "去向「下一次做同类普查的那一轮」;本片做的是移交归属普查,不是定案级改判行普查,"
                   "判据未加「CLAUDE.md 里以『Rxx 更正』开头的引用块一律计入」那一条"),
    "H-R11C-B-d": (V_OPEN, "去向「改探针的那一轮」,要把 rulings_census.py 的 is_decl() 子串匹配换成带边界正则;"
                   "本片只 import R11D 探针未改 data/r11b/ 的历史资产"),
    "H-R11D-M-b": (V_OPEN, "R11D 主线铸,去向「任一轮」:30 处自引路径挂了基线 sha(类别错误);"
                   "本轮无锚点片,且改动面落在历史 notes/reports,按边界不动"),
    "H-R11D-B-a": (V_OPEN, "R11D 片 B 铸,去向「R12 前置或任一改普查的轮次」;本片沿用 R11D 的宽正则绕过该缺陷,"
                   "但普查器本身未改,177 个片内号对原口径仍隐形"),
    # —— 需要改 chapters/ 的,按派工书规则一律转 R12 ——
    "H-R11D-B-e": (V_R12, "R11D 写「建议下一轮:补声明」,而补的是 chapters/r10b 里两处台账手抄件的 "
                   "<!-- derived: --> 声明 —— 落点在 chapters/ 正文,本轮边界写死零改动。"
                   "**它与本轮新立的防手抄关卡是同一族**:两者都在补「手抄件不在任何检查面上」这个口子"),
    "H-R11D-B-b": (V_R12, "R11D 判「R12 重排之前」:4 处「第 N 章」不点名文件,关卡按「不猜」记未点名=4;"
                   "改法要动 chapters/ 正文。本轮 reading/03 的章链接由 data/chapter-order.tsv 机械生成,"
                   "演示了「章号 + 文件名同现」的写法,但没有也不能改正文里那 4 处"),
    "H-R11D-B-c": (V_R12, "R11D 判「R12 装订(改名/合并时)同步」:chapters/ 内 8 处跨章裸文件名;本轮 chapters/ 零改动"),
    "H-R11D-B-d": (V_R12, "R11D 判「R12 前置」:R11C §11.1 最后一行逐片计数两种读法都对不上;"
                   "更正落在 reports/round-11c 的正文,按制度只能走文末勘误节,不是本轮的活"),
    "H-R11D-B-f": (V_R12, "R11D 判「R12 开工第一件事」:101 处指向 chapters/ 的自引锚点未钉 commit;"
                   "补钉子要动 notes/reviews/reports,且必须在 R12 动章之前做,不在本轮范围"),
    "H-R11D-M-d": (V_CONTENT, "R11D 主线铸:acp / teams extra 未装致 12 个文件零执行、掩盖 ≥118 个 def test_;"
                   "与 H-R9B-f / H-R11A-d / H-R11B-f 同族,要装包实跑,本轮禁装包"),
    # —— 本片做掉了一部分的那一条 ——
    "H-R11D-C-b": (V_PART, "R11D 判「下一轮开工杂项」的 99 条片内号 + 4 个通用号(宽表头口径下 113 行)。"
                   "本片**做了归属筛查**:113 行逐行过关键词并人工读命中,0 条属阅读层,"
                   "2 条是「写进成品章」类写作建议(H-R10H-f / H-R10H-i)、其余是基线代码缺陷。"
                   "**未做**的是 R11D 要的四选一处置与「去向轮次过去了没有」的逐条判定"),
}


def build() -> list[tuple[str, str, str, str, str]]:
    rows = scope.collect()
    out = []
    for cid, v in rows.items():
        dest = v["dest"].replace("**", "")
        if re.match(r"^(结清|已被取代|判为不做)", dest):
            continue  # R11D 已关闭的 40 条,本片不重开(理由见底稿 §1.4)
        if cid in JUDGED:
            verdict, why = JUDGED[cid]
        else:
            hit = next((g for g in GROUPS if dest.startswith(g[0])), None)
            if hit is None:
                verdict, why = V_OPEN, f"去向「{dest[:40]}」本片未能归类,交主线裁定"
            else:
                verdict, why = hit[1], hit[2]
        phen = re.sub(r"\s+", " ", v["one_line"]).replace("**", "").strip()
        one = f"{phen[:110]} —— {why}"
        anchor = f"`{v['source']}` 的 `{cid}`"
        out.append((cid, v["source"], verdict, one, anchor))
    out.sort(key=lambda r: (list(VOCAB).index(r[2]) if False else r[2], r[0]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    rows = build()

    ids = [r[0] for r in rows]
    dup = [k for k, n in collections.Counter(ids).items() if n > 1]
    bad = [r[0] for r in rows if r[2] not in VOCAB]
    tabs = [r[0] for r in rows if any("\t" in c for c in r)]
    assert not dup, f"一个案号出了多行:{dup}"          # 案号纪律:一个号只指一个实体
    assert not bad, f"verdict 不在五选一里:{bad}"
    assert not tabs, f"字段里有制表符:{tabs}"
    unjudged = set(JUDGED) - set(ids)
    assert not unjudged, f"JUDGED 里有条目没出现在普查结果中(案号写错了?):{sorted(unjudged)}"

    c = collections.Counter(r[2] for r in rows)
    if args.check:
        print(f"rows={len(rows)}  " + "  ".join(f"{k}={c[k]}" for k in sorted(c)))
        return 0

    print("case_id\tsource\tverdict\tone_line\tanchor")
    for r in rows:
        print("\t".join(r))
    print(f"# {len(rows)} 条;" + " / ".join(f"{k} {c[k]}" for k in sorted(c)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
