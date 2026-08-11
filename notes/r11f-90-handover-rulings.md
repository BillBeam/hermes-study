# R11F 移交项定案(逐条给处置结论,无一「续转」了事)

> 溯源约定:指向 hermes-agent 的锚点写作 `路径:行号 @ 863e313`;
> 指向本仓库的锚点为工作树相对路径。

## 0. 本轮的移交收件箱里有什么

R11E 片 C 把移交候选整理成 `data/r11e/handover-candidates.tsv`,共 114 条,
四种 verdict。R11E 另立五个**条件式收件人**(甲/乙/丙/丁/戊),
把 25 条存疑项从「下一轮」重指到由**触发条件**定义的收件人。

R11F 要回答的是:**这 114 条里,哪些的触发条件在本轮成立?**

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{c[$3]++} END{for(k in c) print c[k]"\t"k}' data/r11e/handover-candidates.tsv | sort -rn
```

```text
60	不归属本轮·转内容轮
28	不归属本轮·转R12装订
25	存疑·交主线裁定
1	本轮部分结清
```

## 1. 触发条件逐个核实(先判"归不归我",再判"怎么处置")

R11E 的五个收件人各自由一个**可核实的动作**定义。本轮逐条核实:

| 收件人 | 触发条件 | 本轮成立? | 核实方式 |
|---|---|---|---|
| **甲** 引用/证据关卡维护 | 修改 `scripts/verify_citations.py` 或 `verify_evidence_commands.py` | **否** | `git diff --name-only main...HEAD` 对这两个文件为空 |
| **乙** 移交普查升格 | 把移交普查提升为 `scripts/verify_handover_*.py` | **否** | 该文件不存在 |
| **丙** 历史产出清理 | 派出以修改历史 `notes/`/`reports/`/`reviews/` 为任务的分片 | **否** | 本轮六片的 claim 声明路径均为 `notes/r11f-raw-*` 与 `data/r11f/*` |
| **丁** 制度位 | 新增或修改 `CLAUDE.md` 证据规则 | **是** | 本轮入册 3 条证据规则 |
| **戊** 台账维护 | 改动台账 `status` 列 | **是** | 本轮 243 行 `R1-inventoried` → `R11F-structure`,另 38 行改复合状态 |

甲、乙的否定是**机械可核**的:

```verify
cd /home/user/hermes-study && git diff --name-only main...HEAD -- scripts/verify_citations.py scripts/verify_evidence_commands.py | wc -l && ls scripts/verify_handover_*.py 2>/dev/null | wc -l
```

```text
0
0
```

**丙的否定要说清搜索面**(CLAUDE.md:负结论必须写出搜索面):
判据是「本轮是否派出以修改历史产出为任务的分片」。搜索面 = 本轮全部六份 claim 的
`path:` 声明行,即 `data/inflight/r11f-*.claim`。全部声明落在 `notes/r11f-raw-*.md`、
`data/r11f/<片>/*`、`data/r11f/probes/<片>_*.py` 三种模式内,**无一条指向历史轮次的产出**。
这条否定的可信度等于这个搜索面的完备性:它**不覆盖**"某片未声明就去改了历史文件"的情形 ——
那种情形由提交守卫的第二张网(非阻断提示)与收工时的 `git diff --stat main...HEAD` 兜底,
本轮两者均已核(见报告 §9)。

## 2. 戊 · `H-R11B-B1-e` —— **结清**

`notes/r11d-raw-handover-disposition.md:254` 的 `H-R11B-B1-e`

> 片 B1 那 12 个文件的台账 `status` 仍是 `R7B-deep-read`,没反映 R11B 的重读

R11B 片 B1/B2 对 38 个 L1 文件做了补读(两片合计落了 75 + 43 条带行号锚点的断言),
但**台账 `status` 一列没动**,仍停在各自原轮次的值。清单落库在 `data/r11b/backlog-38.tsv`。

**处置:结清,但不按 R11D 建议的写法。**

R11D 的建议是「把 status 从 `R7B-deep-read` 等**改为** `R11B-deep-read`」。
本轮**不采用**:那样会抹掉"原本哪一轮读的"这条线索,而这正是 CLAUDE.md 在
round 列上反复要保住的东西(R11A 改判 `skills/**` 的理由、R11C 保留 227/16 两桶的理由,
都是同一条)。**覆盖式改写会让 R2/R4/R6/R7B/R8B 五个轮次的工作在账面上消失。**

改为**复合状态** `<原值>+R11B-deep-read`。这不是本轮发明的写法 ——
台账里早有先例:`R8D-structure+R9A-deep-read[1380-2840,6755-9178]`。

改动分布:

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{for(i=1;i<=NF;i++) sub(/\r$/,"",$i); if($6 ~ /\+R11B-deep-read$/) c[$6]++} END{n=0; for(k in c){printf "%-34s %d\n",k,c[k]; n+=c[k]}; printf "合计 %d\n", n}' data/ledger.tsv | sort
```

```text
R2-deep-read+R11B-deep-read        3
R4-deep-read+R11B-deep-read        4
R6-deep-read+R11B-deep-read        2
R7B-deep-read+R11B-deep-read       12
R8B-deep-read+R11B-deep-read       17
合计 38
```

五层加总不变(`scripts/verify_ledger.py` 复核 `SUM == repo total: 2608452`)。

## 3. 丁 · 三条全部入册 —— **结清**

`notes/r11e-90-handover-rulings.md:97` 的 `H-R11C-C-b`

三条的触发条件都是「下一次改 `CLAUDE.md` 证据规则的轮次」,本轮成立。

| 号 | 未入册的那条规矩 | 本轮入册为 |
|---|---|---|
| `H-R11C-C-b`(余半条) | 证据块不得依赖另一个块产生的文件 | 「**证据块必须自足**」——生产者块带 `tee` 被判 MUTATING 永不跑,消费块每次都跑、每次都报错,是一条**两头都坏**的稳定失败 |
| `H-R11C-C-d` | 省略号只能省别处逐字写过的部分 | 「**省略号只能省「别处已逐字写过」的部分**」——不许省掉产生输出的 `print` 与脚手架,否则重建要靠猜 |
| `H-R11D-A-c` | 同类批量作业须有人工复核环节 | 「**同类批量作业必须有人工复核环节**」——use-mention 盲区(锚点被当作**讨论对象**时机械补全会让该句自我否定)不是正则能补的洞 |

**本轮当场用了第三条。** §4 判定 60 条「转内容轮」时,机械普查给出 `IN-SCOPE=0`;
我没有直接采信,而是手工抽了 4 条我**独立怀疑与插件有关**的案子回源核对
(`H-R9D-D-g` feishu、`H-R10G-b` memory manifest、`H-R9D-D-b` QQBot、`H-R11B-B2-b` provider 名单),
四条的锚点分别落在 `tools/feishu_doc_tool.py`、`hermes_cli/web_server.py`、
`tools/send_message_tool.py`、`hermes_cli/subcommands/memory.py` —— **无一在 `plugins/` 下**,
与机械结论一致。**过目 4 条,驳回 0 条。**

## 4. 60 条「转内容轮」—— **明确不属 R11F**,并铸 `H-R11F-M-b`

R11F 是 R11A 之后的第一个内容轮,于是这 60 条字面上全部落到本轮头上。
**逐条核实的结论是:一条都不属于本轮。**

判据是机械的:沿每条的 `source` 栏回到它的原始记录行,抽出其中能在基线上解析的路径,
看它落在哪棵子树。

```verify
cd /home/user/hermes-study && python3 data/r11f/probes/handover_scope_r11f.py 2>&1 | tail -12
```

```text

OUT 指向的顶层目录分布:
  tools            23
  agent            19
  hermes_cli       9
  (锚点未解析到基线路径)     7
  gateway          1
  website          1
  cron             1
  tests            1

source 栏解析不到原始记录行的条数 = 0
```

把语料从 60 条放宽到全部 114 条,结果一样:

```verify
cd /home/user/hermes-study && python3 - <<'PY'
import csv, re
from pathlib import Path
STUDY = Path('.'); BASE = Path('/home/user/hermes-agent')
PATHY = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+\.(?:py|yaml|yml|md|mjs|js|ts|tsx|toml|json|sh|c|h))")
SRC = re.compile(r"^([\w./-]+\.md):(\d+)$")
cache = {}
def srcline(s):
    m = SRC.match(s.strip())
    if not m: return ""
    rel = m.group(1)
    if rel not in cache:
        p = STUDY / rel
        cache[rel] = p.read_text(encoding='utf-8').split("\n") if p.exists() else []
    L = cache[rel]; i = int(m.group(2)) - 1
    return L[i] if 0 <= i < len(L) else ""
scope = set()
for f in sorted(Path('data/r11f/slices').glob('*.txt')):
    for line in f.read_text().splitlines():
        if line.strip(): scope.add(line.split("\t")[0])
rows = list(csv.DictReader(open('data/r11e/handover-candidates.tsv', newline=''), delimiter='\t'))
hits = []
for r in rows:
    blob = f"{r['anchor']} {r['one_line']} {srcline(r['source'])}"
    ps = [p for p in PATHY.findall(blob) if (BASE / p).exists() and p.startswith('plugins/')]
    if ps: hits.append((r['case_id'], r['verdict'], sorted(set(ps))))
print(f"候选 {len(rows)} 条,锚点解析到 plugins/ 的 = {len(hits)}")
for c, v, p in hits: print(f"  {c} [{v}] {', '.join(p)}")
print(f"其中落在 R11F 243 文件清单内的 = {sum(1 for _c,_v,p in hits if any(x in scope for x in p))}")
PY
```

```text
候选 114 条,锚点解析到 plugins/ 的 = 1
  H-R11B-D-d [不归属本轮·转R12装订] plugins/memory/honcho/cli.py
其中落在 R11F 243 文件清单内的 = 0
```

唯一那条命中也不在本轮清单内:`plugins/memory/honcho/cli.py` 是 **L1**、R6 已精读,
而本轮范围是 L2 的 243 个。

> **这一节的三个证据块,第一版全部被 `verify_evidence_commands.py` 判 `EVIDENCE-DIFF`,
> 三处都是我自己造成的**,如实记下:(a) 上面那张状态分布表的列宽是我**手工对齐**的,
> 与命令真实输出差一个空格;(b) `tail -12` 我贴了 13 行;(c) 我在 ```` ```text ```` 块里
> **手写了一句解释**(就是刚移到块外的那句)。第三处正是这道关卡设立的理由 ——
> 「一段从未由该命令产生过的输出被写进底稿,而数字看起来完全合理」。
> 人工评审抓不住这一类,因为它要求评审者真的去跑那条命令。

**这不是"推走",是一条真结论,而且它指出 R11E 的裁定只治好了一半。**

R11E 裁定「**『下一轮』不是收件人**」,理由是一条写给"下一轮"的移交项落到任何一轮都
字面命中、实质未必相干。**「内容轮」是同一个病的另一个词**:内容轮之间差别极大 ——
R11F 读 `plugins/`,而这 60 条压倒性地指向 `tools/`(23)、`agent/`(19)、`hermes_cli/`(9)。
把它们全领走是假装做了,全推走是假装没收到;**唯一诚实的做法是把收件人定义换成子树**。

铸 `H-R11F-M-b`,并给出建议的收件人定义(**按基线子树,不按轮次性质**):

| 建议收件人 | 触发条件 | 本批条数 |
|---|---|---:|
| **己** 工具面复核 | 任何一轮以 `tools/**` 为主要范围 | 23 |
| **庚** 内核面复核 | 任何一轮以 `agent/**` 为主要范围 | 19 |
| **辛** CLI 面复核 | 任何一轮以 `hermes_cli/**` 为主要范围 | 9 |
| **壬** 装 extra 后复跑 | 任何一轮在报告里申报扩充了 venv 的平台/媒体 extra | 7(锚点未解析到基线路径的那批,多为"要装了才能跑") |
| 其余 | 各自 1 条,见探针输出 | 2 |

### 4.1 **本节的结论被本轮自己推翻了一条**(片 F 到货后补,不改上文)

上面 §4 的结论是「60 条一条都不属于本轮」。**这条结论有一个例外,而且是本轮自己做掉的**:
片 F 结清并加强了 `H-R10G-b` —— 那正是 60 条里的一条。

**机械那一半没错**:`H-R10G-b` 的代码锚点是 `hermes_cli/web_server.py:5468`,
确实不在 `plugins/` 下,探针把它归进 `OUT` 是对的。

**错的是我从这个事实推出的结论**:我从「锚点不在范围内」推出了「本轮推不动它」。
这两件事不是一回事 —— **一条案子可以横跨两棵子树**:
它的**消费方**在 `hermes_cli/web_server.py`(不在本轮),
它的**数据**是 `plugins/memory/*/plugin.yaml`(**在本轮,而且正是本轮要穷举的清单面**)。
被执行的那行命令写在 `plugins/memory/byterover/plugin.yaml:6 @ 863e313`:

```
    install: "curl -fsSL https://byterover.dev/install.sh | sh"
```

**这正是本轮入册的那条规矩要防的形态**,而我在写下它的同一轮里犯了它:
> 机械判据不得用词根去判「开/闭」这类语义 …… **判开闭是人的事,普查的事是别让任何一条从眼前消失。**

我让普查替我下了「不属本轮」这个结论,而它只被授权回答「锚点指向哪棵子树」。
§3 我对 4 条**我自己怀疑**的案子做了人工复核 —— 但复核的判据仍是「锚点在不在 `plugins/`」,
**问的是同一个问题,所以得到同一个错**。人工复核环节要防的不是"机器算错了",
是"这个判据本身够不够" ——`H-R10G-b` 的一句话现象里写着 `manifest`,
一个真正独立的复核会在那里停下来。

**处置**:`H-R10G-b` 记为**本轮结清**(实做见片 F 的 `H-R11F-F-a`);
§4 其余 59 条的判定不变 —— 但判定的**理由**要收窄成机械那一半能支撑的那句:
「它们的代码锚点不在本轮范围内」,而不是「本轮推不动它们」。
**推不推得动,需要逐条读它的现象描述,本轮只对其中 5 条做到了这一点。**
铸 `H-R11F-M-e`:另外 54 条**未经这一层复核**,下一个内容轮不得直接引用 §4 的结论。

## 5. 另一条本轮实做的:`H-R11E-M-c` —— **结清**

`reports/round-11e-reading-layer.md:600` 的 `H-R11E-M-c`

去向写的是「乙,或**任一改 `scripts/` 的轮次**:把汇总解析收进 `scripts/`」。
本轮改了 `scripts/`(开工杂项),故触发条件成立。

实做:`data/r11e/probes/test_totals_r11e.py` → `scripts/test_totals.py`,
并增补零执行清单解析。**口径不变是直接验过的**,不是假定的 ——
两版跑同一份 R11F 日志都给 `skipped=247`(见报告 §8)。

## 6. 本轮新铸

| 号 | 现象 | 收件人(条件式) |
|---|---|---|
| `H-R11F-M-a` | 移交候选表的 `anchor` 栏指的是「案子记在哪」(本仓库 md 的行号),不是「案子指向哪段基线代码」,于是下一轮**无法从这张表机械判断范围**;本轮首版普查因此在 60 条里 58 条报"锚点未解析到基线路径",回源到 `source` 栏才可解析。锚点例:`data/r11e/handover-candidates.tsv:2` 的 `` `notes/r11d-raw-handover-disposition.md:257` 的 `H-R10G-d` `` | 乙(移交普查升格轮):候选表加一列 `code_anchor` |
| `H-R11F-M-b` | 「内容轮」和「下一轮」一样不是收件人:60 条转内容轮的案子里 `IN-SCOPE=0`,它们指向 `tools/`(23)/`agent/`(19)/`hermes_cli/`(9) | 见 §4 建议的按子树收件人;由下一个立收件人制度的轮次采纳或驳回 |
| `H-R11F-M-c` | 阅读层的三份编辑源与钉表被硬编码在 `scripts/build_reading_layer.py:77` 的 `DATA = STUDY / "data" / "r11e"`,于是**此后每一轮加章都要去编辑 R11E 的目录**;R11F 已被迫这么做。锚点:`scripts/build_reading_layer.py:77`:`DATA = STUDY / "data" / "r11e"` | 任一改 `scripts/build_reading_layer.py` 的轮次:把三份源迁到 `data/reading/` 并一次性改引用 |
