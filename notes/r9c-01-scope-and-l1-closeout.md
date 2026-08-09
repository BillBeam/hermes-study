# r9c-01 · 本轮范围核对 与 L1 收口条件

> 主线产出。溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于块前。
> 本篇不含 hermes-agent 行为断言,数据全部来自本仓库台账,命令均可重跑。

## 1. 开工先核范围

任务书写 R9C 为 47 文件 / 19,274 行。台账实测一致:

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$5); if($5=="R9C"){n++; l+=$3}} \
    END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

```text
47 文件 / 19274 行
```

47 个文件全部是 `layer=L1`、`status=R1-inventoried`,即**从未开工**。

### 1.1 主题与拆片

本片的共同主线是**「harness 与外部世界之间的账」**:模型能力从哪些非主路径接进来、
密钥从哪里取、钱怎么算、自己的运行状态往外说给谁。按此拆六片派工:

| 片 | 主题 | 文件 | 行数 | 底稿 |
|---|---|---|---|---|
| A | Codex 传输族(app-server / responses 两套协议) | 4 | 2,696 | `notes/r9c-raw-codex-transport.md` |
| B | 传输层契约本体 + chat_completions / anthropic / bedrock | 7 | 1,915 | `notes/r9c-raw-transport-contract.md` |
| C | 中继与插件 LLM(relay / plugin_llm / copilot ACP) | 5 | 4,200 | `notes/r9c-raw-relay-and-plugin-llm.md` |
| D | 密钥来源(Bitwarden / 1Password / 外部命令 / 缓存) | 8 | 3,823 | `notes/r9c-raw-secret-sources.md` |
| E | 可观测性与外发(监控 / OTLP / trace / webhook / TLS) | 13 | 3,164 | `notes/r9c-raw-monitoring-egress.md` |
| F | 计费额度 + 三个具体 HTTP 客户端 | 10 | 3,476 | `notes/r9c-raw-billing-and-http-clients.md` |
| **合计** | | **47** | **19,274** | |

移交项定案另立 `notes/r9c-90-handover-rulings.md`(主线独立取证,不转述子代理)。

## 2. 恢复必报项:R1-inventoried 剩余

CLAUDE.md 要求每轮报告必报此项(理由:分层快照几乎不动,读者从分层列读不出"还剩多少没开工")。

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$6); if($6=="R1-inventoried"){n++; l+=$3}} \
    END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

R9C 开工时:**7,832 文件 / 2,008,064 行**。
本轮 47 个文件转 `R9C-deep-read` 后应为 **7,785 文件 / 1,988,790 行**(收工复核见报告)。

## 3. L1 全量 deep-read 的剩余判定(验收项 ②)

### 3.1 现状

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$4); sub(/\r$/,"",$6); \
    if($4=="L1"){t++; tl+=$3; if($6=="R1-inventoried"){n++; l+=$3}}} \
    END{printf "L1 合计 %d 文件 / %d 行;其中未开工 %d 文件 / %d 行\n", t, tl, n, l}' data/ledger.tsv
```

```text
L1 合计 563 文件 / 522207 行;其中未开工 96 文件 / 45708 行
```

未开工的 96 个全部落在两轮里,**没有第三轮**:

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$4); sub(/\r$/,"",$5); sub(/\r$/,"",$6); \
    if($4=="L1" && $6=="R1-inventoried"){n[$5]++; l[$5]+=$3}} \
    END{for(k in n) printf "%-6s %d 文件 / %d 行\n", k, n[k], l[k]}' data/ledger.tsv | sort
```

```text
R9C    47 文件 / 19274 行
R9D    49 文件 / 26434 行
```

**结论:R9D 是 L1 的最后一片。** R9C 收工后 L1 只余 R9D 的 49 文件 / 26,434 行。
R9B 报告把剩余轮次由三轮更新为两轮,本轮复核该判定成立,不再变更。

### 3.2 收口条件不能只看 status 列 —— 一次实测

一个自然的收口判据是「`layer=L1 && status=R1-inventoried` 归零」。**这个判据不够,已实测。**

把已标 `*-deep-read` 的 467 个 L1 文件路径,拿去在产出语料里做精确子串搜索:

| 语料 | 全路径零命中 | 连裸文件名也零命中 |
|---|---|---|
| `notes/` + `chapters/` | 42 文件 / 8,234 行 | 14 文件 / 5,150 行 |
| `notes/` + `chapters/` + `reports/` | **40 文件 / 7,811 行** | **11 文件 / 2,820 行** |

**两行是不同语料下的两次独立测量,不是同一读数的两种写法。** 报告采信下面一行(语料最全,对既有产出最宽容)。

也就是说:467 个"已 deep-read"里,有 **40 个文件的路径在全部产出里一次也没出现过**;
其中 **11 个连裸文件名都搜不到**——这 11 个在任何形式上都没被提及过。

**"路径没出现"不等于"没读过"**:一份底稿理论上可以描述某文件而不写它的路径。
但本项目的证据格式要求断言紧跟 `路径:行号`,所以**路径零命中意味着该文件上没有任何一条可溯源断言**。
这已经足以说明 status 列在这 40 个文件上**高于实际交付**。

### 3.3 R9D 收口那一轮需要报数的项(建议清单)

给出「收口那一轮报数哪些项才算真的读完」。前四项为**硬条件**,缺一不可:

1. **台账归零**:`layer=L1 && status=R1-inventoried` 的计数 = **0 文件 / 0 行**;
   且 L1 各 `*-deep-read` 状态行数加总 = **563 文件 / 522,207 行**。
2. **分层未被搬动**(最关键,防的是最省事的作弊):报出收口时 L1 的**文件集合**与
   R9C 收工时的 L1 集合逐行 diff,增减必须为 0。
   *理由:达成"L1 全读完"最省力的办法不是去读,而是把读不动的文件降层到 L2。
   只报 status 列的话,这种搬动完全不可见。*
3. **守恒仍成立**:`verify_ledger.py` 通过,五层加总 = 2,608,452,基线工作区干净。
4. **点名覆盖率**:对全部 563 个 L1 文件跑 §3.2 那个精确子串搜索,报出
   **全路径零命中数**与**裸文件名零命中数**。R9D 自己新增的 49 个必须是 **0 / 0**;
   历史积压的 40 / 11 若不清,**必须在报告里点名列出**,并明确它归哪一轮补
   (不得以"L1 已收口"的名义掩盖)。
5. **关卡**:定稿全量 `verify_citations.py` 零 MISMATCH、零 BLOCK-DRIFT、零 TABLE-DRIFT、
   零 TABLE-OUT-OF-RANGE,退出码 0;当轮 notes 口径可校验比例 ≥70%。
6. **对 R12 的宣告**:H-R8D-i 把 R12 的前置条件定为"L1 全部 deep-read"。收口轮须**显式宣告**
   该前置是否满足——满足则同时给出 R12 待装订的成品章清单(届时应为 17 章);
   若第 4 项有未清积压,则宣告"前置**未**满足",并给出补齐计划。

*第 4 项是本轮新加的,依据就是 §3.2 的实测:没有它,"L1 读完了"只是台账里的一列字。*
