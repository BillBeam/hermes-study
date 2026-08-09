# R9D · 工具面 —— L1 收口

**一句话结论**:守卫认的是工具名,不是效果。

本轮读完台账 `round=R9D` 的 **49 文件 / 26,434 行**(开工先核,与任务书一致),切六片派工;
落实 R9A / R9C 移交中归属本轮的 **7 条**并逐条给出处置结论;**完成 L1 收口**并按 R9C 报告 §3.2
的六项逐项报数;显式宣告 R12 前置条件。

---

## 1. 开工先核范围

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$5); if($5=="R9D"){n++; l+=$3}} \
    END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

```text
49 文件 / 26434 行
```

49 个**全部**是 `layer=L1`、`status=R1-inventoried`(从未开工)。拆六片,加总逐行核过无重无漏:

| 片 | 主题 | 文件 | 行数 |
|---|---|---|---|
| A | LSP 子系统 | 11 | 4,708 |
| B | 文件读写与安全 | 7 | 6,488 |
| C | 看板、待办与定时 | 5 | 4,073 |
| D | 消息外发与平台工具 | 6 | 5,052 |
| E | 网络检索与浏览器供给 | 6 | 2,673 |
| F | 工具网关、澄清与回合杂项 | 14 | 3,440 |
| **合计** | | **49** | **26,434** |

**开工杂项**:沿用 R9C 的惰性安装纪律并**实测**开关有效(不照抄 R9C 结论)。
*一处对 R9C 的更正*:R9C 报告 §1.1 把该开关写在 `hermes_cli.lazy_install`,按该路径 import **失败**,
实际模块是 `tools/lazy_deps.py`;R9C 的**结论**成立,只是模块路径写错。

---

## 2. 台账报数

```verify
cd /home/user/hermes-study && python3 scripts/verify_ledger.py /home/user/hermes-agent data/ledger.tsv
```

```text
OK baseline=863e31318 files=8530 total_lines=2608452
  L1: files=563 lines=522207
  L2: files=2131 lines=671639
  L3: files=1895 lines=602085
  L4: files=560 lines=55902
  LT: files=3381 lines=756619
  SUM == repo total: 2608452
```

五层加总 = **2,608,452**,守恒成立;基线 HEAD 仍是 `863e31318`,工作区干净。
49 个文件的 `status` 全部转为 `R9D-deep-read`。

**恢复必报项 —— `R1-inventoried` 剩余**:

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$6); if($6=="R1-inventoried"){n++; l+=$3}} \
    END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

```text
7736 文件 / 1962356 行
```

(开工时 7,785 文件 / 1,988,790 行,差额正好是本轮的 49 / 26,434。)

---

## 3. L1 收口(R9C 报告 §3.2 的六项,逐项报数)

### 3.1 第 1 项 · 台账归零 —— **达成**

`layer=L1 && status=R1-inventoried` = **0 文件 / 0 行**;
L1 各 `*-deep-read` 加总 = **563 文件 / 522,207 行**,与 L1 总数一致。

### 3.2 第 2 项 · 分层未被搬动 —— **达成,增减均为 0**

R9C 定这一项的理由是:"达成 L1 全读完最省力的办法不是去读,而是把读不动的文件降层到 L2"。
故比对的是**文件集合本身**,基准取自 **R9C 合入 main 的那个 commit**(`75e0261`),不是本地工作区。

```verify
cd /home/user/hermes-study && \
  awk -F'\t' 'NR>1{sub(/\r$/,"",$4); if($4=="L1") print $1}' data/ledger.tsv | sort > /tmp/l1-now.txt && \
  git show 75e0261:data/ledger.tsv | awk -F'\t' 'NR>1{sub(/\r$/,"",$4); if($4=="L1") print $1}' | sort > /tmp/l1-r9c.txt && \
  echo "R9C: $(wc -l < /tmp/l1-r9c.txt)  R9D: $(wc -l < /tmp/l1-now.txt)" && \
  diff /tmp/l1-r9c.txt /tmp/l1-now.txt && echo "DIFF EMPTY"
```

```text
R9C: 563  R9D: 563
DIFF EMPTY
```

**新增 0 行、删除 0 行。** 基准文件同时落库在 `data/r9d/l1-fileset-at-r9c-close.txt`
(sha256 `feeaee3b02ab10e5142ee27cb01cca367bc16bc6da6bdf817e35a56b7b9c2f23`),供任何后续轮次原样复核。

### 3.3 第 3 项 · 守恒仍成立 —— **达成**(见 §2)

### 3.4 第 4 项 · 点名覆盖率 —— **本轮 49 个 0/0;历史积压 40 → 39,且揭出一处测量污染**

**本轮新增的 49 个:全路径零命中 0、裸文件名零命中 0。** 且不止"提过一次"——
**49 个每一个都至少有 1 处带行号锚点**(最薄的 `agent/lsp/__init__.py` 那 1 处,
承载的是一条 ■+▲:`hermes lsp restart` 跨进程为空操作)。

**历史积压部分必须分两个读数报,不得合并:**

| 口径 | 全路径零命中 | 裸文件名零命中 |
|---|---|---|
| 朴素(含本轮那张积压清单表) | 17 文件 / 1,023 行 | 0 文件 / 0 行 |
| **剔除该清单表(以此为准)** | **38 文件 / 7,710 行** | **10 文件 / 2,781 行** |

**朴素读数不可采信,原因是本轮自己造成的测量污染。** 该测量的判据是"路径字符串在语料里出现过没有",
而本轮为了履行"逐个点名"的要求,把 40 个积压文件写进了 `notes/r9d-01-scope-and-l1-closeout.md` §3.3 的表——
**点名这个动作本身把被点名文件变成了"已命中"**。

**证据是两族的表现差异**:表里 R2/R4/R6/R7B 那些我写的是**全路径**,它们全部翻成命中;
R8B 那 18 个我写的是**裸文件名**,它们**全部仍是零命中**。裸名零命中变成 0,同理。

**所以本轮对历史积压的真实贡献是 40 → 38,清掉 2 个**
(`agent/jiter_preload.py`,F 片讲启动期惰性 import 时真的引用了它;另一个 `hermes_cli/subcommands/` 下的文件由
移交取证组 D 在讲凭据落盘链路时引用)。真实积压按原属轮归并:**R2 3 / R4 4 / R6 2 / R7B 12 / R8B 17 = 38 文件 / 7,710 行**,
逐个点名见 `notes/r9d-01-scope-and-l1-closeout.md` §3.3 与 §3.4。

**归属(结清 H-R9C-e 的"需指定补齐轮次")**:全部 38 个归 **R11B**。建议按重量分两片——
R7B 那 12 个占积压行数的 63.8%(4,960 行,`yuanbao_proto.py` 一个就 1,418 行)单独排一片;
R8B 那 17 个平均 60 行、多为薄壳,一节讲完即可;R2/R4/R6 那 9 个零散并入。

**给 R11B 的告诫**:**这个测量对"报告它"不是幂等的**,重测时必须把承载积压清单的文件从语料里剔除,
否则会读到虚高的改善。*本轮差一点把 18/0 当成成绩写进报告;拦住它的是"这个数好得不合常理"
这一下犹豫,**不是任何关卡——没有任何脚本会发现这种污染**。*

### 3.5 第 5 项 · 关卡 —— **达成**(见 §6)

### 3.6 第 6 项 · 对 R12 的宣告 —— 见 §8

---

## 4. 移交项定案(7 条,逐条给出处置结论,无一"续转")

主线独立取证,不转述子代理;子代理取证书另有四份,对读结果写在各条。
完整取证见 `notes/r9d-91-handover-rulings.md`。

| 移交项 | 处置结论 |
|---|---|
| **H-R9A-b** | **立 ■,推翻 R9A「不主张」** |
| **H-R9A-c** | **维持 ■,但改述定性**:是收尾验证门变窄,**非**审批旁路 |
| **H-R9A-e** | **维持 ■,方向定死为 fail-open** |
| **H-R9A-f** | **维持 ■,改述两处**:风险类型、覆盖率口径 |
| **H-R9A-g** | **关闭**;**主线初判被推翻并更正** |
| **H-R9C-a** | **三段拆分(经取证组 D 证据修订)**:env 分支非缺陷;stored 分支**由 ■ 降为设计缺口**;**真正的 ■ 是下游裸 `urlopen` 跨源 302 带走 Bearer** |
| **H-R9C-b** | **关闭并改述**:原担心形态不成立;补读完成,**新增 ■ = `cmd_setup` 验证前落盘** |

### 4.1 三条值得单独说的

**H-R9A-b —— R9A 的负结论关闭了调查,而它测的恰是唯一安全的那一侧。**
R9A 记"asyncio 侧三次实测未复现,不主张"。本轮用**基线真函数**实证:
阻塞 `subprocess` 侧 `Popen.wait()` 与 `subprocess.run().returncode` 都从 **42 降级为 0**,
**且无任何日志**——一次失败被报成成功。受害现场 `gateway/platforms/webhook_filters.py:279`
的安全判据(非零 = 拒绝该 webhook)因此从"拒绝"翻成"放行",方向是 **fail-open**。
收尸者与受害者同在网关进程,默认每 60 秒一次。

*而 asyncio 侧的两次测量必须分别标注*:主线 8 次 **0 次**被抢(全 42);
取证组 A 5 次 **1 次**被抢(`[42,255,42,42,42]`)。合起来的正确结论**不是**"asyncio 安全",
而是**失败可见度不同**:asyncio 被抢记 `255` **并打 warning**(响亮),阻塞侧静默记 `0`。
**R9A 选的那一侧,即使出事也会大声喊,因此最不可能在三次试跑里表现成一个需要主张的问题。**

**H-R9A-g —— 主线初判被推翻,更正依据是一个我没想到要查的维度:文档定稿的那一刻。**
初稿把漏列的 31 个整体判 ▲。取证组 C 取了定稿 commit `b7bd17710`(2026-05-05)的快照,
主线用 `git show` 独立复核(**不切换基线工作区**):当时 `TOOLSETS` 共 54 键
= 非 `hermes-*` **30** + `hermes-*` **24**,而**文档列的 30 个与当时的非 `hermes-*` 集合严格相等**。
作者做的是**「能力 toolset」子类的完整枚举,平台族是有意排除**。故拆判:

| 家族 | 个数 | 记号 |
|---|---|---|
| `hermes-<平台>` 捆绑包 | 24 | **◇**(文档没说错,只是没写出这条规则) |
| 能力 toolset(`x_search`/`video_gen`/`bfl`/`computer_use`/`context_engine`/`project`/`coding`) | 7 | **▲** |
| `messaging`/`moa`/`rl`(代码已无) | 3 | **▲** |

*为什么这个更正重要:**判 ▲ 是在说"作者画错了地图",判 ◇ 是在说"地图没画这一块"。**
对那 24 个,作者画对了——他画的是另一张图,只是没写图例。把它算成 ▲ 既冤枉作者,
也让 ▲ 这个跨轮"地图腐烂程度"指标失真。*
另**更正 R9A 的锚点** `AGENTS.md:971-974` → `971-975`:原范围**漏掉整整一行 8 个键**,
照它去截取只数得出 22 个而非 30 个。**R9A 的"漏 28"也改正为 31**(58−27,而非 58−30)。

**H-R9A-e —— 方向定死为 fail-open,这是它是不是 ■ 的关键。**
同一个 `_run_approval_gate`:父线程 `approved=False`(要求审批)→ 裸 `submit` 的 worker
`approved=True`(**自动放行**)→ 包进 `copy_context()` 再提交,又变回 `False`。
主线独立重跑,读数与取证组 B 完全一致。
*机制里有一条值得记住的形态*:下游确实有 `copy_context()`,但它在**已经身处 worker 线程时**取快照——
**源头断了,后面每一处 `copy_context` 都在忠实地复制"空"**。

---

## 5. 定案

### 5.1 记号报数

六片底稿合计 **96 条**:**■ 48 / ▲ 11 / ◇ 31 / ◎ 6**(逐条带锚点,在各片底稿的发现清单)。
主线另定案 7 条移交项(记号见 §4)。

| 片 | ■ | ▲ | ◇ | ◎ | 小计 |
|---|---|---|---|---|---|
| A LSP | 12 | 4 | 8 | 1 | 25 |
| B 文件读写与安全 | 10 | 1 | 4 | 1 | 16 |
| C 看板、待办与定时 | 7 | 1 | 4 | 1 | 13 |
| D 消息外发与平台工具 | 5 | 3 | 5 | 1 | 14 |
| E 检索与浏览器供给 | 7 | 2 | 3 | 1 | 13 |
| F 工具网关与回合杂项 | 7 | 0 | 7 | 1 | 15 |
| **合计** | **48** | **11** | **31** | **6** | **96** |

### 5.2 主线实跑复核的七条(抽验,不照抄底稿)

| # | 条目 | 复核结果 |
|---|---|---|
| 1 | `tools/file_operations.py:1071` 原子写 `trap` 清理 | **复现**:基线写法残留临时文件、正确写法不残留;与同函数 `:1006` docstring "never leak" 相反。复核不手抄源码,直接 `ast.literal_eval` 取基线那一行 |
| 2 | `website/docs/user-guide/security.md:288` "always blocked" 五项 | **复现**:唯 `auth.json` 未被挡;`write_file_tool` 返回 `verified: true`,主凭据库被整体覆盖 |
| 3 | `agent/lsp/servers.py:209` ceiling 差一层 | **复现**:LSP 工作区根逃出 git 工作树 |
| 4 | `tools/file_operations.py:1674` `patch` 绕过读禁清单 | **复现**:`read_file` 判拒绝、`patch` 判成功,两个明文 `api_key` 逐字进 diff |
| 5 | cron `no_agent` 绕开审批闸 | **复现全链四步**;负结论复核:`cron/` 下 **9** 个 `.py` 中四个审批标识符唯一命中是一行注释 |
| 6 | `tools/send_message_tool.py:2106` 禁令被 `cronjob` 的 `deliver` 一跳绕过 | **复现**:同一 `_send_to_platform` 引擎,目标是模型可写的自由字符串 |
| 7 | `agent/tool_dispatch_helpers.py:584` 提示注入白名单 | **复现**:用被测代码自己的判据跑,`x_search` 被包装 = `False` |

**抽验不是全验**:七条分属五片、七种性质,各片其余断言以其底稿自证为准,主线未逐条重跑。

### 5.3 结构性结论:**守卫认的是工具名,不是效果**

R9C 的结论是"**防线的存在不是覆盖率的证据**"(问的是**装了几处**)。
本轮六片互不通气,却各自撞见同一形态,把问题推进了一层——**要紧的不是装了几处,是装在了哪一层**:

| 装了守卫的门 | 同效果的另一扇门 |
|---|---|
| `read_file` 查读禁清单 | `patch` 不查,还把明文密钥写进 diff |
| 写禁清单盖住 `.env` / PKCE / `mcp-tokens` | `auth.json` 不在表里,可整体覆盖 |
| `bws_cache.json` 有 7 处守卫 | `op_cache.json` 有 0 处 |
| 收尾验证门认 `write_file` / `patch` | `sed -i` / `execute_code` 改的文件不触发 |
| 审批闸挂在 agent 回合上 | cron `no_agent` 没有回合 |
| `send_message` 刻意不注册给模型 | `cronjob` 的 `deliver` 是模型可写的任意目标 |
| 提示注入包装白名单 2 个名字 | `x_search` 不在上面 |
| 审批上下文靠 contextvars 传 | 一处裸 `submit`,下游 `copy_context` 全在复制"空" |

**八个实例,由六个互不通气的精读片 + 主线移交取证分别发现。**

**并且这不是挑出来的孤例——本轮把它做成了一次机械枚举**(`data/r9d/probes/name_keyed_guard_census.py`,
AST 扫全仓非测试 `.py`,找"模块级纯字符串 set/frozenset 且与已注册工具名有 ≥2 交集"的常量):
**全仓 17 个这样的常量,其中 10 个只列 ≤5 个工具**;
而 §5.2 人工撞见的那两条(`_UNTRUSTED_TOOL_NAMES`、`FILE_MUTATING_TOOL_NAMES`)
**正好落在这张表的最底下一档(各 2 个元素)**。
*说清楚它证明什么:**这不是缺陷检测器**,一个 2 元素常量完全可能是对的。
它证明的是"按工具名列举"在本仓库是普遍写法,因而那 8 个实例是这种写法在最窄档上的必然结果,
不是我从犄角旮旯挑出来的。*

**表里还有一条最能说明问题的对照**:仓库对"哪些工具会改东西"有**两个答案**——
`agent/tool_guardrails.py:41` 的 `MUTATING_TOOL_NAMES` 有 16 个名字、**包含 `terminal` 与 `execute_code`**;
而 §3.1 那个收尾验证门用的是 `agent/tool_result_classification.py:9` 的 2 元素集合。
**仓库知道 `terminal` 会改文件——它在隔壁模块里写着;这条知识只是没有被用在需要它的那一层。**
**可迁移的一句话**:守卫要绑在**收口点**上(即将读一个路径 / 即将发一次请求 / 即将执行一段代码),
而不是绑在每个工具的入口各判一次——因为**工具是一直在加的,而新工具不会自动继承旧守卫**。

**一条自我印证**:`x_search` **同时**是"代码有、`AGENTS.md` 未列"的 7 个能力 toolset 之一,
**又是**提示注入白名单漏掉的那一个。两处遗漏彼此独立(一个文档、一个代码),
却指向同一件事——**列表式的守卫在列表的边缘腐烂,而边缘正是最新、最少人走的那些工具。**

---

## 6. 关卡读数

| 范围 | citations | OK | 可校验比例 | 阻断项 |
|---|---|---|---|---|
| **当轮 notes(报告口径,受 70% 下限约束)** | 740 | 555 | **75.0%** | 0 |
| 定稿全量(`chapters/*.md` + 当轮 notes + 当轮 report) | 1,163 | 771 | 66.3% | 0 |
| 本轮成品章单独 | 23 | 22 | **95.7%** | 0 |
| 本轮报告单独(表格锚点 13,OK 7) | 2 | 0 | — | 0 |

*口径说明(R8C 定)*:**70% 下限约束的是当轮 notes**,不是 `chapters/`。
成品章是"求读"的,大量引用天然是散文体区域指路;定稿全量那一行打印的是**合并**比例,
被 11 章历史成品章稀释,**不是本轮的可校验率**。报告本身只有 2 条 `verify` 引用(声明式非源码),
其证据密度体现在 13 个表格行内锚点上(7 个已机械校验,6 个指向本仓库产出文件、
校验器只对基线取证故记 UNCHECKED)。

**0 MISMATCH / 0 BLOCK-DRIFT / 0 TABLE-DRIFT / 0 TABLE-OUT-OF-RANGE,退出码 0,全程未用 `--fix`。**
台账关、首句关同绿。基线 `863e313` 全程干净(每次交付后各断言一次 `git status --porcelain` 为空)。

六章 UNCHECKED ≥90% 的「疑似锚点排版不合规」提示照常打印,是 H-R8D-g 的已知欠账(归 R11B),**本轮未动**。

---

## 7. 测试(按 CLAUDE.md 连环境一起记)

**两个口径必须分开报,不得合并:**

| 口径 | 测试文件 | passed | failed |
|---|---|---|---|
| **主线合并去重全量(一次测量)** | **133** | **1,829** | **2** |
| 各片自报读数之和(一个求和,片间可能重复计入) | 102 | 1,246 | 2 |

主线口径的测试文件按**"是否 import 本轮模块"**选取(不按文件名猜),并排除两个裸包名
`agent` / `tools`(不排除会命中 1,107 个文件,那是"覆盖半个仓库"而非"覆盖本轮")。
**R9C 明写它只有求和、没有合并测量,本轮补上了这次测量。**

**唯二失败**,两条同源,**非代码缺陷、非用例脆性,而是本项目自己的开工纪律造成的**:
`tests/tools/test_web_tools_config.py::TestParallelClientConfig` 两例,报错点名
`security.md`... 实为 `security.allow_lazy_installs=false` —— 正是本轮设的
`HERMES_DISABLE_LAZY_INSTALLS=1`。**这一条反过来是个有价值的测量**:不设该开关时,
跑这个文件会**联网安装 `parallel-web==0.4.2` 到共享 venv**,即 R8A 立"必须记 venv 包数"
那条规矩要防的漂移。本轮把它从**静默的环境变更**变成了**一条可见的失败**。
**我有意没有去掉开关重跑来"确认"**——那正好会把 venv 从 87 改成 88;这是一处**有意不做的验证**。

**跳过情况(本项目此前口径下的一处错判,已撤回)**:合并全量共 **11 条跳过、分布在 6 个文件**,
其中 **1 个文件整体被跳过**——`tests/tools/test_send_message_tool.py`,
一个模块级 `pytest.importorskip('telegram')` **掩盖了 47 个 `def test_`**,
而它正是 D 片主文件(`tools/send_message_tool.py`,2,116 行)的主测试,运行器那一行仍显示 `✓`。
*留痕*:本轮初稿曾写"无整文件静默跳过",**是错的**——运行器把 "skipped" 缩写成 `s`
(`(1s, 1.1s)` 里的 `1s` 是"1 个跳过"不是"1 秒"),我那次 grep 的搜索面根本没覆盖它。
详见 `notes/r9d-92-mainline-tests-and-crosschecks.md` §1.2。

**CLAUDE.md 已知的 6 条必然失败用例,本轮范围内一条都没碰到。**

**环境**:venv **开工 87 包 / 收工 87 包**,两种数法(`pip list` 去表头、`site-packages/*.dist-info`)
在收工时**均为 87**。**本轮期间未发生任何安装**——`HERMES_DISABLE_LAZY_INSTALLS=1` 开工实测有效
并写进六份派工书与四份取证书,十个子代理交付时均自报 `installed_any_package: false`,
主线在每次收件时复核 venv 计数。Python 3.11.15。

---

## 8. R12 前置条件宣告(验收项 ②)

H-R8D-i 把 R12 前置定为**"L1 全部 deep-read"**。

### 8.1 宣告:**按字面口径满足;但附一条必须一并读的限定**

- **字面满足**:`layer=L1 && status=R1-inventoried` = **0**,L1 全部 563 个文件 `status` 均为 `*-deep-read`,
  且**分层未被搬动**(增减 0),**守恒成立**。前置条件的可观测判据全部达成。
- **限定**:**38 个 L1 文件(7,710 行)在全部产出语料里没有任何一条可溯源断言**(§3.4)。
  按本项目的证据格式,这意味着它们的 `status` 列**高于实际交付**。
  **"L1 全部 deep-read"在台账意义上为真,在"每个文件都被明确交代"这个最终目的意义上尚有 38 个缺口。**

**主线判断:R12 可以启动,不必等 R11B。** 理由:R12 的任务是**装订与全局重构**已有的 17 章成品章,
而那 38 个缺口文件**没有一个是任何一章的主题**(逐个核过:17 个是 `hermes_cli/subcommands/` 薄壳、
12 个是 `gateway/platforms/` 的 qqbot/yuanbao 具体适配、9 个零散)。
**但这条限定必须写进 R12 的正文**,不能以"L1 已收口"的名义掩盖。

### 8.2 R12 待装订的成品章清单(17 章)

| # | 章 | 主题 |
|---|---|---|
| 1 | `chapters/r1-what-is-hermes-agent.md` | 这是什么 |
| 2 | `chapters/r2-turn-loop-and-model-access.md` | 回合循环与模型接入 |
| 3 | `chapters/r3-tool-infrastructure.md` | 工具基础设施 |
| 4 | `chapters/r4-execution-environments.md` | 执行环境 |
| 5 | `chapters/r5-session-state-and-persistence.md` | 会话状态与持久化 |
| 6 | `chapters/r6-memory-provider-ecosystem.md` | 记忆 provider 生态 |
| 7 | `chapters/r7-gateway-session-core.md` | 网关会话核心 |
| 8 | `chapters/r7b-platform-integration.md` | 平台接入 |
| 9 | `chapters/r7c-gateway-periphery-and-scheduling.md` | 网关周边与调度 |
| 10 | `chapters/r8a-configuration-surface.md` | 配置面 |
| 11 | `chapters/r8b-cli-trunk-and-interaction.md` | CLI 主干与交互 |
| 12 | `chapters/r8c-dashboard-and-web.md` | 仪表盘与 Web |
| 13 | `chapters/r8d-self-custody.md` | 自托管 |
| 14 | `chapters/r9a-capability-organization.md` | 能力组织 |
| 15 | `chapters/r9b-multimodal-delivery.md` | 多模态交付 |
| 16 | `chapters/r9c-external-interfaces.md` | 对外接驳面 |
| 17 | **`chapters/r9d-tool-surface-and-guard-placement.md`** | **工具面(本轮)** |

**R12 装订前需要先处理的两笔欠账**(均非阻塞,但会影响成品质量):
(a) H-R8D-g:六章 UNCHECKED ≥90%,锚点排版不合规,归 R11B;
(b) §3.4 那 38 个点名缺口,归 R11B。

---

## 9. 诚实申报

1. **主线的一处判定被子代理证据推翻(H-R9A-g)**:我把漏列的 31 个 toolset 整体判 ▲,
   **错在没去查"文档定稿那一刻"这个时间维度**。取证组 C 取了定稿快照,证明当时文档集合与
   非 `hermes-*` 集合**严格相等**。已更正为 24 ◇ + 7 ▲ + 3 ▲,底稿与成品章同步改正并写明撤回理由。
2. **主线的一处过强表述被收紧(H-R9A-b)**:初稿写"asyncio 侧结构上安全",过强。
   两次测量读数不同(主线 8 次 0 被抢、取证组 A 5 次 1 被抢),**已分别标注、不合并表述**。
3. **主线的一处错判已撤回(测试跳过)**:初稿写"无整文件静默跳过"为**假**,
   病因是运行器把 "skipped" 缩写成 `s`、我的 grep 搜索面没覆盖到。**它是被 D 片子代理
   在自己范围内报出同一现象而暴露的**,不是被关卡发现的。
4. **一处测量污染,由本轮自己造成(§3.4)**:点名覆盖率的朴素读数 18/0 看起来是大幅改善,
   实为本轮"逐个点名"那张表把被点名文件变成了"已命中"。真实读数 39/10。
   **没有任何脚本会发现这种污染**;拦住它的是"这个数好得不合常理"这一下犹豫。
5. **一处证据格式自查修掉的错**:`notes/r9d-91` 初稿把一条 grep 的输出抄成 3 行(实为 4 行),
   与"shell 命令即证据:必须是重跑能复现该结论的那一条"相悖,已改为原样粘贴并留痕。
6. **就地更正子代理一处搜索面计数**:C 片写"`cron/` 下全部 8 个 `.py`",与其自列的 9 个文件名不符,
   已改为 9。**搜索面的数字写错,是负结论最不能有的瑕疵。**
7. **一次任务中断后的恢复**:本轮后台工作流被中断过一次,按 `resumeFromRunId` 恢复,
   9 个已完成代理走缓存、仅第 10 个重跑。恢复前已断言基线干净、venv 87。
8. **未取证部分**:各片底稿均设「未取证/推定」节。影响面最大的三条——
   (a) H-R9A-b 的生产实际命中率仅静态推算(60s tick × 短窗口),**未实测**,
   且 §4.1 的实验是**主动制造窗口**来证明降级机制,不是在真实时序下等到的;
   (b) H-R9A-f 的严重度取决于 browse.sh 目录能否由任意第三方投稿,**容器离线,本仓库内不可消解**;
   (c) H-R9A-c / H-R9A-e 的最后一段("模型改文件后验证门不触发"、"子代理确实会调审批")
   均为静态全链对读,未在真实回合里端到端跑——需真实 provider 凭据,项目边界明写不配置。
9. **本轮未做的事**:未跑真实模型/计费/云端点,未配置任何凭据;
   `chapters/` 六章的 UNCHECKED 欠账未动;§3.4 那 38 个积压未就地补读(本轮责任是点名 + 归属)。
10. **一处边界违反,自查发现并已修复(本轮)**:边界明写"不把任何会话、模型标识、
    背景信息写入仓库产物"。本轮初稿的三条 ```verify 命令里,复现脚本的路径带着
    **会话专属的 scratchpad 目录名(含会话 UUID)**——那是会话信息写进了产物。
    **修法不是删掉路径,而是把三个探针脚本落库**到 `data/r9d/probes/`
    (`l1_named_coverage.py` / `h_r9a_b_repro.py` / `h_r9a_b_run_variant.py`,
    另加 `h_r9a_e_ctx_probe.py`),命令改用仓库相对路径并**重跑确认三条全部复现**。
    这比删路径更好:证据从"某次会话里跑过"变成"任何人 clone 下来都能重跑"。
    *这条边界不在任何关卡覆盖面内,是自查撞见的;R9C 也曾在提交信息上违反过同一条边界。*
11. **一处历史同型问题,本轮未修(点名移交)**:同样的会话路径出现在**此前五轮**的底稿里
    (`notes/r8c-raw-config-endpoints.md`、`notes/r8d-raw-credentials-security.md`、
    `notes/r9a-raw-skills-agent-side.md`、`notes/r9a-raw-skills-sync.md`、
    `notes/r9c-raw-secret-sources.md`)。**本轮只修自己造成的部分**,历史部分立 H-R9D-f 移交,
    因为改动它们要连带复核各自的 ```verify 是否仍能复现,不宜在收口轮顺手做。
12. **基线洁净的一处如实交代**:跑测试会在基线工作区生成 `test_durations.json`,
    它被基线自己的 `.gitignore:35` 覆盖,故 `git status --porcelain` 为空、
    **所有已跟踪文件逐字未变**(`git diff HEAD` 为空),`路径:行号 @ 863e313` 引用不受影响。收工已清除。

---

## 10. 待提供项(不自行猜测或伪造)

| 项 | 用途 | 阻塞的结论 |
|---|---|---|
| 外网可达 browse.sh | 查该 skills 目录能否由任意第三方投稿 | H-R9A-f 的严重度分级(■ 成立不受影响) |
| 真实 provider 凭据 | 在真实回合里端到端跑子代理审批链、验证门不触发 | H-R9A-c / H-R9A-e 最后一段的实证等级 |
| `[telegram]` 平台 extra | 让 `test_send_message_tool.py` 那 47 个用例真跑 | D 片主文件的行为规格覆盖 |
| `parallel-web` SDK | 让 `TestParallelClientConfig` 两例真跑 | E 片 parallel provider 的覆盖 |

---

## 11. 移交清单(每条带声明式锚点 + 一句话现象)

| 移交项 | 去向 | 锚点 | 现象 |
|---|---|---|---|
| **H-R9D-a** | R11A | `agent/lsp/manager.py:313`:`t = max(8.0, self._wait_timeout + 3.0)` | 注释自陈"外层预算必须大于内层",但 `lsp.wait_mode: full` + 默认 `wait_timeout=5.0` 时外层 8s < 内层 10s,**不变式被文档化的配置组合打破**,首次超时即把该 (server, root) 永久标 broken |
| **H-R9D-b** | R11A | `tools/thread_context.py:118`:`return ctx.run(_inner)` | 返回的包装器不能并发复用,第二个并发调用抛 `RuntimeError: cannot enter context`;与 H-R9A-e 是同一套上下文传播设施的两个缺口 |
| **H-R9D-c** | R11A | `agent/think_scrubber.py:89`:`_OPEN_TAGS: Tuple[str, ...] = tuple(f"<{name}>" for name in _OPEN_TAG_NAMES)` | 带属性的推理标签在流式路径下完整泄露给用户、在非流式路径下把整条回复吃空——同一输入两条路径结果相反 |
| **H-R9D-d** | R11A | `tools/managed_tool_gateway.py:298`:`(actual.scheme, actual.netloc) == (expected.scheme, expected.netloc)` | 托管网关信任闸门对主机名大小写敏感(用 `netloc` 而非 `hostname`),且 `TOOL_GATEWAY_SCHEME=http` 可让 Nous bearer 走明文 |
| **H-R9D-f** | R11B | `notes/r9c-raw-secret-sources.md:280`:`cd /tmp/claude-0/-home-user-hermes-study/` | 此前五轮底稿的 ```verify 命令里带会话专属 scratchpad 路径(含会话 UUID),既违反"不写会话信息进产物"的边界,也让那些命令**换个会话就跑不了**;修时须连带复核各自能否复现 |
| **H-R9D-e** | R11 复盘 | 本报告 §3.4 | 点名覆盖率测量**对"报告它"不幂等**;重测必须剔除承载积压清单的文件,否则读到虚高改善 |
| **H-R9C-e**(改述后续转) | R11B | 本报告 §3.4 的 **38 / 10** | 已标 `*-deep-read` 但全语料零点名的历史积压,建议按 R7B 12 个单独一片 + R8B 18 个一节 + R2/R4/R6 9 个并入 |
| **H-R8D-g**(续转) | R11B | `chapters/r2-turn-loop-and-model-access.md` 等六章 | 校验器逐章点名 UNCHECKED ≥90%;**本轮未动** |
| **H-R8D-h**(续转) | R11 复盘 | `notes/r8d-str-setup-and-ux.md` 的两条 docstring 级 ▲ | 模块 docstring 级 ▲ 与"作者自绘地图"级 ▲ 是否分开计数,仍需统一裁定 |
| **H-R8D-j / H-R9B-e**(续转) | R11A | `pyproject.toml:157`:`[project.optional-dependencies]`(`dev` 在 `:175`,`python-telegram-bot` 在 `:176` 的 `messaging`) | `pip install -e ".[dev]"` 装不出全绿套件;本轮新增形态:`importorskip` 让 **47 个用例**整文件不跑而运行器显示 `✓` |
| **H-R9C-c**(续转) | R11A | `agent/transports/__init__.py:53`:`except ImportError:` | 分不清"可选包没装"与"自己模块里的 import bug",两者都被吞掉 |
| **H-R9C-d**(续转) | R11 复盘 | `tests/gateway/relay/test_relay_media.py:73`:`return "/relay/media/" in (url or "")` | 测试替身重抄被测谓词导致关卡长期空绿;值得做一次全仓普查 |

*(各片底稿另有 50 余条簇内移交项,均带锚点,留在各自底稿的移交节,不在本表重复。)*

---

## 12. 下一轮建议

1. **L1 已收口,R12 前置按字面满足**(§8),但 R12 正文必须带上那 38 个点名缺口的限定。
2. **R11B 的两笔欠账建议合并做**:六章锚点排版(H-R8D-g)与 38 个点名缺口(H-R9C-e)都是
   "回头补证据"的性质,同一轮做可以共用一次全量校验。
3. **本轮结构性结论值得单独立一次普查**(建议 R11 复盘):
   把"守卫绑在工具名上"这个形态做成一次全仓机械检查——
   枚举所有"按工具名判定"的 `frozenset` / 白名单常量,逐个问"同效果的工具是否都在里面"。
   本轮那 8 个实例全部是人工撞见的,**这类形态本应可以机械枚举**。
