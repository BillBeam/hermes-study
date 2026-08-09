# r9a 底稿 · 01 —— 范围核定、R9 四片拆分,与剩余轮次的重新判定

> 研究对象基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(只读)。
> 溯源约定:凡对代码行为的断言,**锚点单独成行、置于代码块之前**,格式 `路径:行号 @ 863e313`。
> 本文是底稿(证据层)。与其他底稿不同,本文的断言对象**主要是本学习仓库自己的台账**,
> 不是 hermes-agent 源码,所以证据形态以 ```verify 围栏的可复现命令为主——
> 按 CLAUDE.md「shell 命令即证据」,每条命令都已实跑,重跑可复现文中结论。

---

## 1. 开工先核范围

任务书给的范围是「台账中 `layer=L1` 但**从未被任何一轮认领或精读**的全部文件,
当前约 177–179 文件 / 111,926 行」,并要求「开工先核范围」。核定结果:**179 文件 / 111,926 行**,
与任务书上界一致。

判据是台账的两列同时成立:`layer` 列为 `L1`(该文件被判定需要机制精读),
且 `status` 列仍为 `R1-inventoried`(从 R1 盘点之后没有任何一轮把它推进过)。

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{for(i=1;i<=6;i++) sub(/\r$/,"",$i); if($4=="L1" && $6=="R1-inventoried"){n++; l+=$3}} END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
# → 179 文件 / 111926 行
```

> 注意 `sub(/\r$/,"",$i)`:`data/ledger.tsv` 是 CRLF 行尾。不剥 `\r`,`$6` 永远匹配不上
> `R1-inventoried`,命令会**安静地打出 0**。这正是 CLAUDE.md「shell 命令即证据」那条规矩
> 要防的形状——一条重跑给出相反结果的命令比不写更糟。

这 179 个文件里,171 个的 `round` 列是 R8D 刚改出来的显式 `UNCLAIMED`,
另外 8 个挂在 `round=R9`(R8D 表里叫「研究管线」)。两者的 `status` 完全一样,
都是「从未开工」——差别只在计划列上,不在事实列上。

### 1.1 分布

按目录聚合(第二列是行数):

| 位置 | 文件 | 行数 |
|---|---|---|
| `tools/*.py` | 61 | 57,604 |
| `agent/*.py`(不含子包) | 63 | 29,498 |
| `agent/transports/` | 11 | 4,611 |
| `agent/lsp/` | 11 | 4,708 |
| `agent/pet/` | 11 | 3,653 |
| `agent/monitoring/` | 9 | 2,039 |
| `agent/secret_sources/` | 7 | 3,293 |
| `agent/proxy_sources/` | 2 | 2,502 |
| 仓库根 | 4 | 4,018 |

---

## 2. 拆分判据:为什么切四片

**111,926 行装不进一轮。** 历史上每一轮的 L1 精读量是:

| 轮 | L1 文件 | L1 行数 |
|---|---|---|
| R2 | 46 | 68,645 |
| R3 | 32 | 29,234 |
| R4 | 35 | 24,418 |
| R5 | 28 | 45,809 |
| R6 | 27 | 24,423 |
| R7 | 16 | 38,343 |
| R7B | 36 | 43,411 |
| R7C | 47 | 28,282 |
| R8A | 15 | 21,893 |
| R8B | 50 | 43,539 |
| R8D | 52 | 42,284 |

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{for(i=1;i<=6;i++) sub(/\r$/,"",$i); if($4=="L1" && $6 ~ /-deep-read$/){n[$6]++; l[$6]+=$3}} END{for(k in n) printf "%-16s %3d 文件 %6d 行\n",k,n[k],l[k]}' data/ledger.tsv | sort -k4 -rn
```

区间是 **15–52 文件 / 21,893–68,645 行**。111,926 行是这个区间中位数(约 38k)的 **2.9 倍**,
是历史最大单轮(R2 的 68,645)的 **1.63 倍**。所以必须拆。

**切片判据沿用 R8A 定的那一条**:*哪些文件必须同时摆在眼前,一个机制才讲得清*。
按这条判据切出四片:

| 片 | 主题 | 文件 | 行数 |
|---|---|---|---|
| **R9A** | 能力的组织、扩展与委派 | 37 | 38,893 |
| R9B | 多模态与呈现 | 46 | 27,325 |
| R9C | 传输、凭据与可观测 | 47 | 19,274 |
| R9D | 代码智能与工具面 | 49 | 26,434 |

四片的文件数 37–49、行数 19,274–38,893,**全部落在历史单轮区间内**。
R9A 是最大的一片(38,893 行),与 R7 的 38,343 行同级。

划分的完备性是脚本校验过的——无重复、无遗漏、无越界:

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{for(i=1;i<=6;i++) sub(/\r$/,"",$i); if($4=="L1" && $5 ~ /^R9[A-D]$/){n[$5]++; l[$5]+=$3; t++; tl+=$3}} END{for(k in n) printf "%-5s %3d 文件 %6d 行\n",k,n[k],l[k]; printf "合计  %3d 文件 %6d 行\n",t,tl}' data/ledger.tsv | sort
# → 合计 179 文件 / 111926 行,与 §1 核出的目标集逐一相等
```

### 2.1 为什么是四片而不是 R8D 建议的两片

R8D 的 §8 对这 171 个文件的建议是「按内容分四簇,**建议拆两轮**」。本轮改为四轮,理由有二:

1. **两轮装不下。** 179 文件 / 111,926 行切两片是每片约 56,000 行。这个数只有 R2(68,645)
   超过过,而 R2 是**第一个内容轮**、读的是回合主循环这一个高度内聚的机制簇。
   本片的文件彼此独立度高得多(基本一个工具一个文件),56,000 行意味着一轮要讲清
   ~90 个互不相干的机制——那不是精读,是过目。
2. **四簇本来就是四片。** R8D 自己说的是「按内容分**四簇**」。把四个内容簇硬压成两轮,
   等于在轮内再切一次而不记账。既然簇边界已经清楚,让轮边界与簇边界重合,
   报数与叙述都省一次转换。

### 2.2 原「R9 研究管线」不再单列

R8D 的 §8 表里,171 个 UNCLAIMED 文件被提议叫 **R8E**,而 `round=R9` 的 12 个文件
(8 个 L1 + 4 个 L3 配置示例)仍作为独立的「R9 研究管线」轮保留。本轮把两者合并,
理由是**它们在事实层面是同一批东西**:

- 那 8 个 L1 文件的 `status` 同样是 `R1-inventoried`,与 171 个的处境完全一样;
- 它们的内容(`batch_runner.py` / `mini_swe_runner.py` / `trajectory_compressor.py` /
  `toolset_distributions.py` / `agent/moa_loop.py` / `agent/subagent_lifecycle.py` /
  `agent/moa_trace.py` / `agent/delegation_context.py`)**就是 R9A 的委派簇本身**;
- 并行保留两条编号线,会让「按 `round` 列报数」同时出现 `R8E` 与 `R9` 两个桶,
  而它们描述的是同一件没做的事。

四个 `agent/` 文件早有显式规则,**就地改挂 R9A** 而不是在新规则块里重列——
`assign_layers.py` 是首条匹配生效,重列会留下永不命中的死规则。

---

## 3. 台账与分层规则对齐:`UNCLAIMED` 归零

R8D 已经做了第一步:把兜底规则的 `round` 从区间占位符 `"R3-R7"` 改成显式 `UNCLAIMED`,
让「从未认领」在按 `round` 报数时自己跳出来。本轮做第二步——**给它们逐个定轮**。

结果是 `UNCLAIMED` 桶归零,同时**未认领文件在按 `round` 列报数时仍然可见**
(它们现在挂在 R9A/R9B/R9C/R9D 名下,`status` 仍是 `R1-inventoried`):

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$5); if($5=="UNCLAIMED") n++} END{printf "UNCLAIMED=%d\n", n+0}' data/ledger.tsv
# → UNCLAIMED=0
```

重生成后台账仍满足覆盖守恒(五层加总 = 全仓总行数):

```verify
cd /home/user/hermes-study && python3 scripts/verify_ledger.py /home/user/hermes-agent data/ledger.tsv
# → OK baseline=863e31318 files=8530 total_lines=2608452 ... SUM == repo total: 2608452
```

**这里要说清一个容易混淆的点**:`round` 列是**计划**,`status` 列是**事实**。
把 `UNCLAIMED` 换成 `R9B` 并不代表那些文件读过了——它们的 `status` 仍是 `R1-inventoried`。
R8D 之所以要造 `UNCLAIMED` 这个值,是因为当时的占位符 `"R3-R7"` 让「没人认领」
**伪装成**「已经计划好了」。现在计划是真的了,而事实列照旧诚实。

---

## 4. 剩余轮次的重新判定(R9 / R10 / R11)

任务书要求复核 R8D 对 R9/R10/R11 的判断,理由是那些判断建立在「内容轮已收口」的假设上,
而该假设已被推翻。

**先说公道话:R8D 的 §8 表本身没有漏账。** 它的七行里含「R6 补 | `plugins/**` + skills/ 编目 |
1,323 | 431,965」这一行,数字与本轮实测一致。被推翻的假设影响的不是**范围**,
而是**每轮装得下多少**——因为那个判断当时是靠「历史单轮做得完」这个先例外推的。
本轮实测发现:**这个外推对 L2 只有一个先例,对 L3 一个先例都没有。**

### 4.1 当前剩余全量(排除 L4 有理由排除层与 LT 测试层)

| 计划轮 | 文件 | 行数 | 主层 |
|---|---|---|---|
| R9A | 41 | 39,110 | L1(+4 个 L3 配置示例) |
| R9B | 46 | 27,325 | L1 |
| R9C | 47 | 19,274 | L1 |
| R9D | 49 | 26,434 | L1 |
| R6 遗留 | 1,323 | 431,965 | L2 + L3 |
| R10 | 1,533 | 405,902 | L2 + L3 |
| R11 | 928 | 307,128 | L2 + L3 |
| R1 遗留 | 11 | 4,840 | L3(根 `.md`) |
| **合计** | **3,978** | **1,261,978** | |

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{for(i=1;i<=6;i++) sub(/\r$/,"",$i); if($6=="R1-inventoried" && $4!="L4" && $4!="LT"){n[$5]++; l[$5]+=$3; tf++; tl+=$3}} END{for(k in n) printf "%-8s %5d 文件 %8d 行\n",k,n[k],l[k]; printf "%-8s %5d 文件 %8d 行\n","合计",tf,tl}' data/ledger.tsv | sort
```

### 4.2 关键发现:L3 整层零先例,L2 只有一个先例

这是本轮对 R8D 判断做的最实质的修正。

**L3 从来没有任何一轮完成过任何一个文件。** 1,895 个 L3 文件,`status` 清一色 `R1-inventoried`:

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{for(i=1;i<=6;i++) sub(/\r$/,"",$i); if($4=="L3") s[$6]++} END{for(k in s) printf "%s=%d\n",k,s[k]}' data/ledger.tsv
# → R1-inventoried=1895   (只有这一个状态,没有任何 *-cataloged)
```

**L2 完成过的最大单轮是 R8D 的 125 文件 / 83,350 行**,而且这是「结构级」而非精读:

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{for(i=1;i<=6;i++) sub(/\r$/,"",$i); if($4=="L2" && $6!="R1-inventoried"){n[$6]++; l[$6]+=$3}} END{for(k in n) printf "%-18s %3d 文件 %6d 行\n",k,n[k],l[k]}' data/ledger.tsv | sort -k4 -rn
# 最大一行 → R8D-structure  125 文件  83350 行
```

据此重判:

| 判断项 | R8D 的判断 | 本轮判断 | 依据 |
|---|---|---|---|
| **R11 是否要拆** | 拆成 R11A / R11B | **仍然要拆,拆法不变**——R11A 141 文件 / 43,365 行 L2,R11B 787 文件 / 263,763 行 L3 | R8D 的三条理由与本轮实测数字**逐一复核一致**;它给的独立旁证(两个切块的边界与 L2/L3 层边界完全重合)本轮复算仍成立 |
| **R11A 是不是一个满轮** | 是,43,365 行,与 R8B 的 43,539 行同级 | **降级为「大概率是,但这是跨层外推」** | 43,539 那个数是 **L1** 的量;R11A 是 L2。目前唯一的大体量 L2 先例(R8D 125 文件 / 83,350 行)说明 L2 的单轮容量**比 L1 大**,所以 R11A 可能偏小——但只有一个样本,不足以定 |
| **R11B 是不是一个满轮** | 是,单轮 | **不能判定** | L3 零先例。263,763 行 L3 该怎么切,**没有任何数据支撑**。R8D 说它是单轮,本轮认为这是无依据的乐观 |
| **R10 拆几片** | 建议拆三片(桌面端 / web / 终端 UI) | **三片不够,至少五片** | R10 是 405,902 行 L2,是目前最大 L2 先例(83,350)的 **4.87 倍**。切三片是每片约 135,000 行,仍是先例的 1.6 倍 |
| **R6 遗留** | 需要认领 | **需要认领,且它是剩余里最没底的一块** | 431,965 行中 315,887 行是 L3(零先例),116,078 行是 L2 |

### 4.3 一条给后续轮的方法学建议(不是本轮定案)

L2/L3 的单轮容量目前是**猜**出来的,而 L1 的容量是十一轮实测出来的。
建议**下一个做 L2 或 L3 的轮次,把「这一轮实际吃下多少」当作产出的一部分显式报数**,
让后面的轮次有先例可依。在那之前,任何「R11B 单轮足够」这类话都应当标注为未经验证。

---

## 5. L1 是否全量 deep-read:**未达成**

任务书要求给出这个判定。答案是**未达成**,并给出剩余范围:

本轮(R9A)结束后,L1 层的 563 个文件里:

| | 文件 | 行数 |
|---|---|---|
| 已 deep-read(R2–R8D + 本轮 R9A) | 421 | 449,174 |
| **仍未 deep-read** | **142** | **73,033** |
| L1 合计 | 563 | 522,207 |

剩余的 142 文件 / 73,033 行**全部**在已定轮的 R9B / R9C / R9D 三片里:

| 片 | 文件 | 行数 |
|---|---|---|
| R9B 多模态与呈现 | 46 | 27,325 |
| R9C 传输、凭据与可观测 | 47 | 19,274 |
| R9D 代码智能与工具面 | 49 | 26,434 |

即:**L1 全量 deep-read 还差三轮**,且这三轮的范围已经逐文件定死,不再有无主文件。

这条判定对 R12 有直接后果。R8D 的 H-R8D-i 判定「R12 的前置条件是『L1 全部 deep-read』
而非『R11 做完』」——本轮复核**同意该判定**,并把它量化:R12 的前置条件是
**再做完 R9B / R9C / R9D 三轮**,与 R10 / R11 的进度无关。

---

## 6. 测试作为行为规格(R9A 范围)

按 CLAUDE.md,测试是行为规格参照(LT 层),报测试数**必须一并记环境**。

**环境**(开工时实测):

```verify
ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l && /home/user/hermes-venv/bin/pip list 2>/dev/null | tail -n +3 | wc -l && /home/user/hermes-venv/bin/python -V
# → 87 / 87 / Python 3.11.15
```

即 CLAUDE.md 记录的基线组合:`[dev]` extra + `aiohttp==3.14.1` + `brotlicffi==1.2.0.1`,
共 **87 个包**,与 R8B 实测的 87 一致(R8C/R8D 期间曾被子代理装到 93–97,本轮是干净重建)。

**结果:132 个测试文件,1,202 个用例,0 失败。**

```verify
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh $(python3 - <<'EOF'
import pathlib, re
pats = [r"tests/agent/test_(curator|insights|learn_prompt|learning_|verification_|verify_hooks|skill_|external_skills|ghost_skill|org_skill|memory_skill|moa_|subagent_)", r"tests/tools/test_(skills_|skill_|delegate|async_delegation|delegation_live_log|blueprints|write_verification)", r"tests/hermes_cli/test_(skills_|curator_|moa_|banner_skills|chat_skills)", r"tests/cli/test_(cli_async_delegation|cli_delegate|cli_insights|cli_preloaded_skills|cli_reload_skills|moa_command|cli_interrupt_subagent)", r"tests/run_agent/test_(moa_|verification_continuation_budget|file_mutation_verifier)", r"tests/gateway/test_(subagent_protection|async_delegation_session_binding|delegation_session_id_leak|agents_command_delegations|moa_one_shot_restore|reload_skills|unavailable_skill_hint|fresh_reset_skill_injection)", r"tests/tui_gateway/test_(delegation_session_lifecycle|moa_reference_emit|subagent_child_mirror)", r"tests/(test_batch_runner_|test_trajectory_compressor|test_mini_swe_runner|test_minisweagent_path|test_toolset_distributions|test_iron_proxy|test_delegate_cascade|test_background_review_|test_evidence_store|test_plugin_skills|test_session_skill_previews)", r"tests/integration/test_batch_runner", r"tests/cron/test_(blueprint_catalog|rewrite_skill_refs)"]
print(" ".join(str(p) for p in sorted(pathlib.Path("tests").rglob("test_*.py")) if any(re.match(x, str(p)) for x in pats)))
EOF
)
# → === Summary: 132 files, 1202 tests passed, 0 failed (100% complete) in <挂钟时间>s (8 workers) ===
#   两次实跑分别为 59.6s 与 51.0s —— 文件数/用例数/失败数三个数完全一致,
#   只有挂钟时间不同,所以结论取前三个数,不取时间。
```

**这个 0 失败值得说明,以免下一轮误判。** CLAUDE.md 记录了本类容器已知会必然失败的 5 个用例
(无 IPv6 / 以 root 运行 / 无 models.dev 目录),R8D 全仓跑还遇到 31 文件 75 用例失败
(缺各平台 extra)。R9A 范围之所以全绿,是因为这一簇的测试**不依赖那些缺失的 extra**,
而不是因为环境变好了。**换一个范围仍然会看到那些失败。**

---

## 7. 本文与其他底稿的关系

本文只管范围、拆分与台账。机制本身在同轮的其他底稿里:

| 底稿 | 覆盖 |
|---|---|
| `notes/r9a-raw-skills-hub.md` | skills 中枢与工具面 |
| `notes/r9a-raw-skills-sync.md` | skills 分发、来源与用量 |
| `notes/r9a-raw-skills-agent-side.md` | skills 在 agent 进程内的接入 |
| `notes/r9a-raw-curator.md` | 学习闭环 · 策展侧 |
| `notes/r9a-raw-learning-graph.md` | 学习闭环 · 图谱与后台复盘 |
| `notes/r9a-raw-verification.md` | 验证闭环 |
| `notes/r9a-raw-delegate-tool.md` | 委派主干 |
| `notes/r9a-raw-async-delegation.md` | 异步委派与子代理生命周期 |
| `notes/r9a-raw-moa.md` | MoA 多智能体循环 |
| `notes/r9a-raw-research-pipeline.md` | 研究管线 / 批处理 / 轨迹 |
| `notes/r9a-raw-egress.md` | 出站流量约束(结清 H-R8D-d) |
| `notes/r9a-h-r8d-b-kanban-db.md` | 结清 H-R8D-b |
| `notes/r9a-h-r8d-c-env-loader-lock.md` | 结清 H-R8D-c / H-R8C-d |
| `notes/r9a-h-r8d-ef-surveys.md` | 结清 H-R8D-e / H-R8D-f |
