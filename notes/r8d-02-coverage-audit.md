# r8d-02 · 覆盖复核 —— 内容轮收官前,先问一句"真收口了吗"

> 本卷不读 hermes-agent,读**我们自己的台账**。R8D 是内容轮(R2–R8D)的收官片,
> 收官轮该做的第一件事不是收官,是**核一遍前面到底覆盖没覆盖**。
> 结论:**没有收口**,而且缺口在 `agent/` 与 `tools/` —— 全仓最核心的两个目录。

---

## 1. 一句话

**171 个 L1 文件、104,656 行,被分层规则判为"机制精读",但从来没有任何一轮认领过它们。**
这个数**比 R8D 自己的 L1 量(52 文件 / 42,284 行)还大一倍半**。

```verify
awk -F'\t' 'NR>1{sub(/\r$/,"",$4);sub(/\r$/,"",$5);sub(/\r$/,"",$6);
  if($6=="R1-inventoried" && $4=="L1" && ($5=="R3-R7"||$5=="R3-R4")){n++;l+=$3}}
  END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

实测输出:`171 文件 / 104656 行`。分布:`tools/` 61 文件 / 57,604 行,`agent/` 110 文件 / 47,052 行。

---

## 2. 为什么会漏:规则表与计划散文是两份地图,只有一份有牙齿

分层规则里,`agent/` 与 `tools/` 各有一条**兜底规则**,轮次写的不是某一轮,
而是一个**区间占位符**,并在注释里把认领责任推给了"后续轮次":

`scripts/assign_layers.py:151`(**本学习仓库**,非基线)

```python
    ("agent/*.py", "L1", "R3-R7"),          # 其余 agent/ 文件在后续轮次开工时显式定轮
```

`scripts/assign_layers.py:210`(**本学习仓库**,非基线)

```python
    ("tools/*.py", "L1", "R3-R4"),
```

*(注:本卷的锚点指向的是**本学习仓库**自己的文件,不是基线,因此**不带 `@ 863e313`**——
那个后缀断言的是基线出处,写在本仓文件上是假的。校验器按 `路径:行号` 配对,
对本仓路径同样解析得到,不需要那个后缀。)*

**"后续轮次开工时显式定轮"这件事,一次也没发生过。**
R5 从这两个桶里吸纳过几个文件(规则表里有 `# R5 机制簇补充:…从 R3-R7 桶吸纳` 的注释),
此后 R6/R7/R7B/R7C/R8A/R8B/R8C/R8D **没有一轮回头看过这两个桶**。

于是形成了一条清晰的分界线:

| 文件 | 层 | 轮次列 | 状态 | 是否被规则表**点名** |
|---|---|---|---|---|
| `tools/terminal_tool.py` (3,432) | L1 | R4 | **R4-deep-read** | ✅ 点名了 |
| `tools/registry.py` (956) | L1 | R3 | **R3-deep-read** | ✅ 点名了 |
| `tools/skills_guard.py` | L1 | R3 | **R3-deep-read** | ✅ 点名了 |
| `tools/skills_hub.py` (4,432) | L1 | R3-R4 | ❌ R1-inventoried | ❌ 只在计划散文里 |
| `tools/delegate_tool.py` (3,931) | L1 | R3-R4 | ❌ R1-inventoried | ❌ 只在计划散文里 |
| `agent/curator.py` (2,019) | L1 | R3-R7 | ❌ R1-inventoried | ❌ 只在计划散文里 |

**被规则表点名的,读了;只在计划散文里出现的,没读。**

---

## 3. 最刺眼的一处:R6 的"学习闭环"只读了一半

R1 的轮次规划里,R6 这一行是这么写的:

`reports/round-1-survey.md:692`

```text
| R6 | 记忆-技能-学习闭环 | memory_manager/provider、plugins/memory/8 后端、learn_prompt、learning_graph*、insights、curator*、skills 全链(tool/manager/hub/guard/usage/ast_audit/commands/bundles)、hermes_state_search + native/fts5_cjk、skills/ 与 optional-skills/ 编目 | notes/r6-*.md |
```

把这一行点名的东西逐个查台账:

| 计划点名 | 实际文件 | 状态 |
|---|---|---|
| memory_manager/provider、plugins/memory/8 后端 | `plugins/memory/**` | ✅ **R6-deep-read** |
| hermes_state_search + native/fts5_cjk | — | ✅ R5 吸纳后读了 |
| `learn_prompt` | `agent/learn_prompt.py` | ❌ **R1-inventoried** |
| `learning_graph*` | `agent/learning_graph.py`、`agent/learning_graph_render.py` | ❌ **R1-inventoried** |
| `insights` | `agent/insights.py` (1,162) | ❌ **R1-inventoried** |
| `curator*` | `agent/curator.py` (2,019) | ❌ **R1-inventoried** |
| skills 全链之 hub | `tools/skills_hub.py` (4,432) | ❌ **R1-inventoried** |
| skills 全链之 tool | `tools/skills_tool.py` (1,963) | ❌ **R1-inventoried** |
| skills 全链之 manager | `tools/skill_manager_tool.py` (1,781) | ❌ **R1-inventoried** |
| skills 全链之 usage | `tools/skill_usage.py` (1,340) | ❌ **R1-inventoried** |
| skills 全链之 guard | `tools/skills_guard.py` | ✅ R3-deep-read(规则表点名了) |

**R6 的簇名是"记忆-技能-学习闭环",它读完了"记忆",没读"技能",没读"学习"。**

而 R1 的顺序理由里,对 R6 的定位是:

`reports/round-1-survey.md:700`

```text
顺序理由:R2-R5 是内核依赖链(循环→工具→环境→状态),先建骨架;R6 学习闭环是本仓库最独特的卖点但依赖前四轮概念;R7-R8 是产品面;R9-R11 外围收敛;R12 综合。每轮工作量以 L1 3-6 万行精读 + 关联测试抽查为度,单轮可在一个会话内完成;如单轮超预算,允许在当轮报告里拆分为 a/b 两个会话并更新台账 round 列。
```

**"本仓库最独特的卖点"——那一半没读。**

---

## 4. 这个洞怎么活过了八轮

因为**每轮的验收都是自洽的**:

- 覆盖守恒查的是 **`layer` 列加总 = 全仓总行数**。171 个文件一直老老实实计在 L1 里,
  加总一直等于 2,608,452。**分层快照永远是绿的**——它压根不看有没有读。
- `status` 列才是"读没读"的唯一可观测指标,而 R7 到 R8B 之间**五轮没人报它**。
  R8-fix 已经因为这件事把"必报 `R1-inventoried` 剩余"写进 CLAUDE.md,理由原话是
  "期间实际仍有 8,122 个文件从未开工"。
- 但**即使报了总数,也看不出这个洞**:8,096 这个数被 3,381 个测试文件(LT,按制度随模块引用)
  和 560 个 L4(有理由排除)撑得很大,171 个核心 L1 文件淹没在里面。

**总数掩盖结构。** 所以本轮起,报"剩余"必须拆开报(见 §5)。

---

## 5. 建议的报数口径:把"剩余"拆成三类

`R1-inventoried` 8,096 文件 / 2,200,133 行,按**性质**拆开是这样:

| 类别 | 文件 | 行 | 说明 |
|---|---|---|---|
| LT 测试(with-module) | 3,381 | 756,619 | 按制度**随模块引用**,不单独开轮。计入"剩余"是记账口径问题,不是欠账 |
| L4 有理由排除 | 560 | 55,902 | 定义上就已完成,status 从未回填 |
| **真正的欠账** | **4,155** | **1,387,612** | 下面这些 |

真正的欠账再拆:

| 归属 | 文件 | 行 | 性质 |
|---|---|---|---|
| **无主 L1(本卷主题)** | **171** | **104,656** | `agent/`+`tools/` 兜底桶,**从未被任何轮认领** |
| R10 L2(界面层) | 1,520 | 388,524 | 计划内 |
| R6 L3(skills/ 编目) | 1,080 | 315,887 | 计划内 |
| R11 L3(website/docs/.plans/locales) | 787 | 263,763 | 计划内 |
| R6 L2(plugins/**) | 243 | 116,078 | 计划内 |
| R11 L2(scripts/docker/nix/.github) | 141 | 43,365 | 计划内 |
| R8D L2(本轮) | 125 | 83,350 | 本轮结清 |
| R8D L1(本轮) | 52 | 42,284 | 本轮结清 |
| R10 L3(i18n) | 13 | 17,378 | 计划内 |
| R1 L3(根 md) | 11 | 4,840 | 计划内 |
| R9 L1 + L3 | 12 | 7,487 | 计划内 |

---

## 6. 处置建议(留给主线报告定,本卷只给依据)

**不建议 R8D 顺手吃掉这 171 个文件。** 理由不是工作量,是**簇的完整性**:
R8D 的切片判据是"哪些文件必须同时摆在眼前,一个机制才讲得清";
`tools/delegate_tool.py`(子 agent 委派)、`tools/skills_hub.py`(技能分发)、
`agent/learning_graph.py`(学习图)彼此之间、以及与 `hermes_cli/**` 之间都没有这种关系。
硬塞进来只会重演"兜底桶"本身的错误——**用容器代替判断**。

建议**新开一轮 R8E**(或在 R9 之前插一轮),簇名按内容分:

| 簇 | 主要文件 | 量 |
|---|---|---|
| 技能与学习闭环(补 R6 的另一半) | `tools/skills_hub.py`、`skills_tool.py`、`skill_manager_tool.py`、`skill_usage.py`、`skills_sync*.py`、`agent/learn_prompt.py`、`learning_graph*.py`、`insights.py`、`curator.py` | ~22k 行 |
| 委派与并发 | `tools/delegate_tool.py`、`async_delegation.py` | ~5.4k 行 |
| 文件与多媒体工具 | `tools/file_operations.py`、`file_tools.py`、`vision_tools.py`、`image_generation_tool.py`、`tts_tool.py`、`transcription_tools.py`、`voice_mode.py`、`wake_word.py` | ~20k 行 |
| 其余 agent/ 与 tools/ | `agent/proxy_sources/`、`agent/display.py`、`agent/lsp/`、`agent/pet/`、`tools/web_tools.py` 等 | ~57k 行 |

**并且:同时修掉产生这个洞的规则。** 兜底规则的 `round` 列不该写区间占位符
(`R3-R7` / `R3-R4`),它让"未认领"看起来像"已计划"。
应改成一个**显式的未认领标记**(如 `UNCLAIMED`),这样任何一轮的报数都会把它顶出来。

---

## 7. 附:本卷的方法学意义

这个洞不是谁偷懒,是**两份地图不同步**:计划散文(报告里的轮次表)是给人读的,
分层规则(`assign_layers.py`)是给机器执行的。**只有后者有后果。**
散文说"R6 读 skills 全链",规则说"skills_hub.py 属于 R3-R4 兜底桶",
两者冲突时,**沉默地生效的是规则**。

这与本项目对 hermes-agent 的核心判据同构——"文档与代码冲突时以代码为准"。
本卷是同一条判据**掉头指向我们自己**的一次应用:

> **我们对 hermes-agent 的作者说:你的 README 是自绘地图,与代码冲突时以代码为准。
> 那么我们的轮次规划表也是自绘地图,与 `assign_layers.py` 冲突时,以规则为准。
> 而规则说:这 171 个文件,没有任何一轮认领过。**
