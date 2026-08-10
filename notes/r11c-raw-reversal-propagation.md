# r11c-raw · 片 E · 改判传播型污染的复查 —— 把搜索面扩到成品章与制度文件

> 溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于代码块/引用块之前。
> 引用本学习仓库自己的文件时,校验器先在基线里找、找不到再在本仓库找
> (`scripts/verify_citations.py:656`),所以下面对 `notes/` / `reports/` / `chapters/` /
> `CLAUDE.md` / `data/*/dispatch-brief.md` 的锚点同样是被机械校验的。
> **本片只查不改**:发现的污染点写成清单交主线,不就地改;不改历史 `notes/`。
> 语料钉在 `f440d78`(本片开工时的分支 HEAD);其后片 C(`e44ba85`)已合入,
> 涉及历史 `notes/` 的行号已在定稿前重新核过一遍。

## 任务范围(派工书 §片 E)

R11B 做过一次「后轮覆盖前轮已证伪结论」普查,命中 2 条,但搜索面限于三条方法路径
(改判语普查 / 案号法 / 特征短语法),排除面含 `reviews/`、`data/`、`scripts/`。
本片把搜索面扩到 **成品章 `chapters/`** 与 **制度文件**
(`CLAUDE.md`、`data/*/dispatch-brief.md`、`data/r*/probes/*.py`、`scripts/*.py`),
报出搜索面与命中数,**命中为零也逐条给短语与搜索面**。
前置产出:「已改判结论」清单,逐条记下被推翻的那个说法的**原文**。

---

## 0. 结论(先给)

**一句话:成品章里的改判传播不是「旧说法被抄回来」,而是「当时正确的派生数字以现在时留在了原地」
——判据 1 抓不到它,必须另设判据 2。**

1. **判据 1(短语法)在成品章上命中 0 条真污染。** 29 条已改判结论的不可替换短语(外加 1 条负控)打进
   21 份成品章(12,576 行),剔除负控后字面命中 16 处,**逐处读完全部是成品章在正确叙述那次改判本身**
   (「本章初稿写的是……,是错的,更正依据是……」)。这是**好结果**,不是没搜到:
   R3 定的成品章硬标准把改判写进正文,于是短语必然出现在章里 —— 所以**短语命中不等于污染,
   必须逐处读**;反过来,**零真污染这个结论的可信度就等于这 16 处我逐处读过**。
2. **判据 2(可复算指标的第二份手抄件)命中 2 处,且正是主线给的正控。**
   `chapters/r1-what-is-hermes-agent.md:103-104 @ 25c612f` 的分层表 L1 / L2 两行是手抄件,
   与 `data/ledger.tsv` 复算值不符(L1 手抄 511 / 479,923,真值 563 / 522,207;
   L2 手抄 2,183 / 713,923,真值 2,131 / 671,639),而同章 `:98` 明写「**下表是当前值,不是历史快照**」。
   **同章 `:112` 还留着上一次同样错误的检讨**(review-1 阻断-2:早先印的是 R1 期那一版 412 / 382,770)
   —— **这是同一个病灶在同一张表上的第二次发作**。
3. **判据 3(制度文件的事实定性)命中 1 处真污染:`data/r10/dispatch-brief.md:52`**
   仍把 H-7 的后果写成「把用户的审批黑名单**静默抹掉**」,而该定性已被 R8C 推翻
   (有 stderr 告警 + 逐字备份)。`CLAUDE.md` 那一处 R11B 已挂更正节;**派工书这一处没人碰过**。
   R10B / R11A / R11B / R11C 四份派工书都保留了这条负结论纪律,但都只留纪律、
   **没有抄走那半句已被推翻的事实定性** —— 详见 §3.1:这次没传下去是改写时掉的,不是被改正的。
4. **方法论结论(本片最该被下一轮拿走的一条):案号法在成品章上天然零命中,而
   「天然零命中的搜索面等于没搜」。** R11B 三条路径全部围着案号与改判语转,成品章按制度
   **不写案号**;把同一套判据铺到成品章上,会得到一个漂亮的 0,而正控就活在那个 0 里面。
   凡把一条判据搬到新搜索面,**先证明它在那面上有可能非零**(本片的做法:先用正控试判据)。
5. **顺带发现一条 R11B 自己的漂移(不属本片战场,记移交)**:R11B §3.4 零命中表里
   那条锚点写 `:700`,而 `:700` 上是另一句完全无关的话 ——

   `notes/r9a-h-r8d-c-env-loader-lock.md:700 @ 863e313`

   ```
   所以这里读到的是**净化后**的值,而 `report` 里是净化前的原值。
   ```

   「后果更轻」的前提被推翻那句的**真实位置是 `:730`,差 30 行**;
   它至今记 TABLE-UNCHECKED,**从没被比对过**。

---

## 1. 搜索面

**先说清楚三个面,因为本片的每一条负结论,可信度都等于这三个面的完备性。**

- **源面**(从这里抽「已改判结论」)= `reports/` + `notes/` + `chapters/` + **`reviews/`**
  + **`CLAUDE.md`** + **`data/*/dispatch-brief.md`**。
- **目标面甲**(成品章)= `chapters/*.md`。
- **目标面乙**(制度文件)= `CLAUDE.md` + `data/*/dispatch-brief.md` + `data/r*/probes/*.py`
  + `data/r11c/*.py` + `scripts/*.py`。

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11c/e-reversal-propagation-scan.py --surface
```

```text
源面: 286 份 / 303919 行
目标面-成品章: 21 份 / 12576 行
目标面-制度文件: 98 份 / 14153 行
```

**与 R11B 的源面口径差(不得写成「同一个测量」)。** R11B 的源面是 266 份,排除
`reviews/`、`data/`、`scripts/`;本片是 286 份,把 `reviews/` 与派工书加了回来,
并把语料钉在本片开工时的分支 HEAD(R11B 钉在 `00f09bf`,期间 R11B 自己与 R11C 片 A/C/F 已合入)。
**两个数不可比,差额同时包含「面扩大了」和「语料长大了」两项。**

**加 `reviews/` 的理由**:`reviews/review-1-full-corpus.md` 是全项目**最大的一次集中改判**
——8 条阻断 + 23 条建议,其中至少 6 条直接推翻了成品章正文里的结论。R11B 把它整份排除在源面外,
于是它推翻的那些说法**一条都没进过改判清单**。派工书点名要查的正控(r1 分层表)正属这一类:
它的第一次发作就是 review-1 阻断-2。

`reviews/review-1-full-corpus.md:185 @ 863e313`

```
#### 【阻断-2】r1 的分层表是 R1 期快照,与同 commit 的 `data/ledger.tsv` 不符,却以现在时陈述
```

**排除面(要写出来)**:
- 排除围栏代码块内的行(块里的「不成立」是被引用的基线源码或文档原文,不是本项目在改判)。
- 判据 1 的目标面**不含** `reports/` 与 `notes/` —— 那是 R11B 已经跑过的面,本片是**扩面**,不是重跑。
- 判据 1 的目标面剔除 `r11c-*` 前缀文件与 `data/r11c/`(本轮在写,见 §6 的污染读数)。
- **`reviews/` 只作源面、不作目标面**:按 `CLAUDE.md` 边界,评审报告原文不改、是历史记录,
  它「传播」不到下一轮的产出里去。*这是一条有意的排除,不是遗漏。*

### 1.1 源面上的定案级改判行普查

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11c/e-reversal-propagation-scan.py --ledger
```

```text
# 定案级改判行:131;带案号/评审编号的 63
# 按目录:chapters=1  notes=105  reports=18  reviews=7
```

**读法与已知漏报(必须写出来,否则这 131 会被当成完备计数)。** 判据是「表格行 / 标题行 /
引用块首 **且** 带案号或 ▲◇■◎ 记号或 `阻断-N`/`建议-N` 编号 **且** 命中强档改判语」。
它**必然漏掉两类**:

- **`CLAUDE.md` 那条 R11B 更正**:它是引用块、命中「推翻」,但**既无案号也无记号**,
  于是被过滤掉 —— 普查在 `CLAUDE.md` 上报 **0 行**,而那里明明有一条改判。
- **review-1 的 8 条阻断 + 23 条建议**里只有 7 行入账:多数标题(如「阻断-2」那条)
  不含强档改判语,写的是「不符」「挂错」「漏了」。

**`chapters=1` 这个读数值得单看**:21 份成品章里,只有一行同时满足「定案级行 + 记号 + 改判语」——

`chapters/r7-gateway-session-core.md:691 @ 863e313`

```
> **◎ 第四处不算 ▲,原判错了。** 本章早先写的是"四处硬伤全部证伪",第四处是
```

**这就是「案号法/改判语法在成品章上天然近乎零命中」的直接读数**:成品章讲改判用的是散文,
不是台账行。判据 1 因此必须靠内容短语,而不是靠这类结构特征。

**所以 §2 的清单不是从这 131 行机械导出的**,而是人工读源面得到的,131 只是**下界与入口**。
*(这正是 `CLAUDE.md` 那条「机械判据不得用词根去判开/闭这类语义」的同一形状:
普查可以发现、可以排队,不能代替人下结论。)*

---

## 2. 「已改判结论」清单(30 行,其中 E-26 是负控 → 真条目 29 条)

**这份清单本身是产出。** 每条记:被推翻的那个说法(**原文**)、它原来写在哪、
推翻它的轮次与锚点、以及**不可替换短语**(判据 1 用它去目标面搜)。
短语的正则形态在 `data/r11c/e-reversal-propagation-scan.py` 的 `PHRASES` 表里,与本表一一对应。

| 编号 | 被推翻的说法(原文) | 原说法出处 | 改判处(锚点 + 摘录) | 不可替换短语 |
|---|---|---|---|---|
| E-01 | 「容器关机即删」 | `website/docs/user-guide/features/tools.md:88`(基线文档) | `notes/r4-90-doc-conflict-rulings.md:7`:`## 定案 1 ★ tools.md:88 "容器关机即删"(R1 挂起的头号条目)——证伪(对默认态)` | `关机即删` |
| E-02 | 「20+ external messaging platforms」口径偏小,记 ▲ | R1 能力点 99 / R7 定案 A3 原判 | `notes/r7-90-doc-conflict-rulings.md:50`:`### A3. 能力点 99:"20+ external messaging platforms" 口径偏小 —— ◎ 保守表述(原记 ▲,R8-fix 改判)` | `20+ 平台` 与 `▲` 同现 |
| E-03 | 「Tool Search 渐进披露无文档」记 ◇ | R1 能力点 2.5-10 | `notes/r3-90-doc-conflict-rulings.md:16`:`| 7 | ◇ Tool Search 渐进披露(R1 2.5-10) | **证伪(有专门详尽的 tool-search.md)** | r3-20 定案 c |` | `Tool Search` + `无文档` |
| E-04 | 坏 YAML 下把用户的 `approvals.deny`「**静默抹掉**」 | `CLAUDE.md`(R8-fix 卡)与 R8B H-7 叙述 | `notes/r8c-90-rulings.md:387`:`## 7. 改判前轮定案:■-R8B-12 的「静默消失」不成立` | `静默抹掉` / `静默消失` |
| E-05 | 「没有第三个读原始配置后落盘的调用方,H-7 关闭」 | R8B H-7 负结论 | `notes/r8b-90-handover-rulings.md:22`:`## 1. H-7:**重开**——第三个"读原始配置后落盘"的调用方确实存在(原负结论作废)` | `没有第三个` |
| E-06 | `PairingStore()` 与 `PairingStore(profile="default")` 语义差异记 ▲ | R8B 定案 | `notes/r8c-90-rulings.md:217`:`### 5.3 改判:配对库的 profile 语义 —— ▲ 撤销,◇ 加重` | `PairingStore` + `▲` |
| E-07 | 「`waitpid(-1)` 的问题不主张」 | R9A 定案 | `notes/r9d-91-handover-rulings.md:765`:`| **H-R9A-b** | `hermes_cli/kanban_db.py:6941`:`pid, status = os.waitpid(-1, os.WNOHANG)` | **立 ■**,推翻 R9A「不主张」;实证 42→0 降级 + fail-open 后果;R9A 测的 asyncio 侧是唯一结构安全的子集 |` | `waitpid` + `不主张` |
| E-08 | 「那 24 个平台束是 ▲」 | R9D 主线初判 | `notes/r9d-91-handover-rulings.md:516`:`### 5.4 主线初判被推翻:那 24 个平台束不是 ▲,是 ◇` | `24 个平台束` + `▲` |
| E-09 | 「H-R10-f 需起真实网关才能复现」 | R10 移交项 | `reports/round-10b-desktop-application.md:501`:`### 11.3 H-R10-f:静态推演 → 实测复现,而「需起真实网关」这个前提不成立` | `需起真实网关` |
| E-10 | 「H-R9B-a 的病因是抄了一份 STT 清单,修法是 import 权威集合」 | R9B 定案 | `notes/r9c-90-handover-rulings.md:257`:`## 2. H-R9B-a:关闭,但病因要改述` | `抄了一份` + `STT` |
| E-11 | 「▲-10 两条路等价、目前无害」 | R8A ▲-10 | `notes/r8b-90-handover-rulings.md:177`:`### 1.2 并案:这属于 R8A ▲-10 的绕行家族,而 ▲-10 的"目前无害"结论要收回一半` | `目前无害` |
| E-12 | 「H-R8D-c 后果更轻(它喂的是 UI 标签)」 | R8D 移交项 | `notes/r9a-h-r8d-c-env-loader-lock.md:730`:`| **H-R8D-c** | **关闭并加重** | 锚点更正为 666 / 234(§0.2);「后果更轻」的前提被推翻(§3);后果实测两条(§5.2/§5.3)+ 一条负结果(§5.4);定案 ■-R9A-01 |` | `后果更轻` |
| E-13 | 「正确修法 = 比对配置的 connector host / `self._base_url`」(种子案) | R9A / R9B 移交项,R11A 写回 | `notes/r11b-92-fix-regression-correction.md:10`:`**缺陷判定两轮一致,修法被写回了已被证伪的那一条。**` | `比对配置的 connector host` |
| E-14 | r7 章「忙时消息不往下送」 | `chapters/r7-gateway-session-core.md` 初稿 | `reviews/review-1-full-corpus.md:115`:`#### 【阻断-1】r7 把"忙时消息不往下送"写反了,与基线、与 r7b、与 r7 自己的 §3.4 三重矛盾` | `忙时…不往下送` |
| E-15 | r1 章「仓库 26 万行」 | `chapters/r1-what-is-hermes-agent.md` 初稿 | `reviews/review-1-full-corpus.md:229`:`#### 【阻断-3】r1 同章内把仓库规模写成 26 万行与 260 万行两个数,差一个数量级` | `26 万行` |
| E-16 | r7b ▲4:三个方法挂在「有基类默认桩」标题下 | `chapters/r7b-platform-integration.md` 初稿 | `reviews/review-1-full-corpus.md:249`:`#### 【阻断-4】r7b 的 ▲4 把文档小标题挂错了对象:那三个方法从不在"有基类默认桩"标题下` | `有基类默认桩` |
| E-17 | r6「hooks 声明三家都与实现不符,是系统性风险」 | `chapters/r6-memory-provider-ecosystem.md` 初稿 | `reviews/review-1-full-corpus.md:315`:`#### 【阻断-5】r6 说 hooks 声明"三家都与实现不符",实测点名的三家里两家是**相符**的` | `三家都与实现不符` |
| E-18 | r4 把 `container_persistent` 与 `persist_across_processes` 当成同一个开关 | `chapters/r4-execution-environments.md` 初稿 | `reviews/review-1-full-corpus.md:374`:`#### 【阻断-6】r4 把 `container_persistent` 和 `persist_across_processes` 当成同一个开关,于是给出的"什么条件下文档才成立"是错的` | 两个键名同现 + `同一个` |
| E-19 | r7「17 个 ContextVar」 | `chapters/r7-gateway-session-core.md` + 底稿 | `reviews/review-1-full-corpus.md:705`:`#### 【建议-6】r7 的 "17 个 ContextVar" 实为 18,且该误数从底稿原样传进了成品章` | `17 个 ContextVar` |
| E-20 | 「加载器只读 description」 | r6 章 / 底稿 | `reviews/review-1-full-corpus.md:905`:`#### 【建议-12】"加载器只读 description"不成立;清单 schema 里有钩子字段,真正的教训比原诊断更好` | `只读 description` |
| E-21 | r8a「`config.yaml` 有五个读取函数」 | `chapters/r8a-configuration-surface.md` | `reviews/review-1-full-corpus.md:797`:`#### 【建议-9】跨章冲突:r8a 说 `config.yaml` 有五个读取函数,r8b 更正为六个,r8a 未回填也无前向指引` | `五个读取函数` |
| E-22 | r2 把流式挂死/读超时的两个数写成普遍值 | `chapters/r2-turn-loop-and-model-access.md` | `reviews/review-1-full-corpus.md:832`:`#### 【建议-10】r2 把流式挂死/读超时的两个数写成普遍值,漏了配置覆盖与本地 provider 的 900 秒分支` | 超时数字 + 无分支限定 |
| E-23 | 底稿「共 16 条」 | R8 期底稿 | `reviews/review-1-full-corpus.md:1497`:`### A-4【建议-18】底稿说"共 16 条",它自己的表是 17 行,报告写的 17 才是对的` | `共 16 条` |
| E-24 | venv 包数 89 | R8A 同轮底稿 | `reviews/review-1-full-corpus.md:1542`:`### A-6【建议-20】venv 包数报了 87,同轮底稿写 89,而这条报数制度是 R8A 自己立的` | `89 个包` |
| E-25 | round-8b「H-14 结清」 | `reports/round-8b-cli-trunk-and-interaction.md` | `reviews/review-1-full-corpus.md:1522`:`### A-5【建议-19】`round-8b` 报告说 H-14"结清",同一份报告 130 行后说它"未逐处落实"并派生了一条 R11 移交` | `H-14` + `结清` |
| E-26 | **[负控,不是改判条目]** `iron` 当短语用 | `notes/r4-90-doc-conflict-rulings.md` 的自检 grep | `CLAUDE.md:341`:`*理由:r4-90 写进定案的自检 grep 用 `iron` 匹配到了 `env`**`iron`**`ment`,` | `iron` |
| E-27 | r1「8,530 个文件 / 26 万行」同源规模数 | `chapters/r1-what-is-hermes-agent.md` 初稿 | 同 E-15(review-1 阻断-3) | `8,530 个文件` + `26 万` |
| E-28 | 「两次读数相同」这种表述 | R11B 之前的通用写法 | `CLAUDE.md:290`:`**不得表述为「读数相同」**,要写清各自的口径。*R11B 实测三例:未配对 verify 块` | `读数相同` |
| E-29 | 被后轮升格为 ■ 的各种「无害 / 无影响」定性 | 多轮(泛化条目) | 同 E-11 一族 | `业务无影响` / `无实际影响` |
| E-30 | r3「审批短路链两道无条件地板」 | `chapters/r3-tool-infrastructure.md` | `reviews/review-1-full-corpus.md:768`:`#### 【建议-8】r3 的审批短路链漏了第三道无条件地板(sudo stdin guard)` | `两道无条件地板` |

**这份清单的完备性(负结论,必须给出限度)。** 30 条不是「全部改判」,是**源面上定案级改判行
(131 行,§1.1)去重归并后、且能取到「被推翻说法原文」的那些**。已知未纳入的:
(a) 各轮 `▲/◇` 定案里对**基线文档**的证伪(如 `notes/r6-90-doc-conflict-rulings.md:21` 那类)
—— 它们推翻的是**基线作者的地图**,不是本项目自己的结论,传播到成品章里是**应该**的;
(b) 同一份底稿内部的自我更正(R11B 已定为不算「后轮覆盖」,本片沿用);
(c) 片 A / 片 B / 片 C 本轮正在铸的新定案 —— 它们还没定稿。

---

## 3. 判据 1:短语法打进目标面

**结论:字面命中 15 处(成品章),制度文件 42 处;逐处读完,成品章 0 处真污染,
制度文件 1 处真污染(`data/r10/dispatch-brief.md:52`)。**

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11c/e-reversal-propagation-scan.py --phrases | tail -5
```

```text
E-27	chapters=1	institutional=0	review-1 阻断-3 同源:规模数字
E-28	chapters=0	institutional=1	R11B:同名指标多次测量不得写成「读数相同」
E-29	chapters=0	institutional=0	泛化:被后轮升格为 ■ 的「无害」定性
E-30	chapters=0	institutional=0	review-1 建议-8:审批短路链实为三道
# 合计 chapters=75 institutional=42 (r11c-* 剔除)
```

**75 里有 59 是 E-26 这条负控贡献的。** E-26 的短语是 `iron`,它在成品章里 59 次命中
**全部**来自 `tools/env`**`iron`**`ments/base.py` 这个路径 —— 这正是 `CLAUDE.md` 记下的那次
自检 grep 事故的同一物种,本片把它**留在表里当负控**,证明「短语法会误吞」不是假想:

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11c/e-reversal-propagation-scan.py --phrases --only E-26
```

```text
E-26	chapters=59	institutional=32	[负控] r4-90 自检 grep 的 `iron` 误匹配 env`iron`ment
# 合计 chapters=59 institutional=32 (r11c-* 剔除)
```

*(E-26 在 `PHRASES` 表里标着「负控」,**不计入真改判条目**;它在这里的作用是让
「短语法会误吞」这句话有一个可重跑的数,而不是一句提醒。)*

**剔除负控后成品章 75 − 59 = 16 处**,分布在 E-01 / E-04 / E-14 / E-16 / E-17 / E-20 / E-27。
逐处读的结果:

| 命中位置 | 判定 | 理由 |
|---|---|---|
| `chapters/r4-execution-environments.md:797`:`- **`website/docs/user-guide/features/tools.md:88 @ 863e313` "容器关机即删" —— 证伪(对默认态)**。默认 persist、清理对容器 no-op、容器跨进程存活` | **非污染** | 章在陈述「这条文档已被证伪」,方向与改判一致 |
| `chapters/r7b-platform-integration.md:784`(E-14) | **非污染** | 章在复盘 r7 那次写反,引号里的是被推翻的原话 |
| `chapters/r7b-platform-integration.md:835`(E-16) | **非污染** | 「**为什么从 ▲ 降到 ◇。** 本章初稿写的是……」—— 正在讲改判 |
| `chapters/r6-memory-provider-ecosystem.md:497,503`(E-17) | **非污染** | 497 是引号内的原说法,503 紧接着说「把 1/5 说成三家都不符……会让下一轮带着一个放大三倍的判断开工」 |
| `chapters/r6-memory-provider-ecosystem.md:496,505`(E-20) | **非污染** | 496 引原说法,505 是「**错误二:加载器不是"只读 description"**」 |
| `chapters/r1-what-is-hermes-agent.md:21 @ 25c612f`:`- **规模**:全仓 8,530 个文件、260 万行文本。Python 是主体(核心逻辑),TypeScript 是界面层,`(E-27) | **非污染** | 写的是「8,530 个文件、260 万行」,正是阻断-3 改判后的正确值 |
| `chapters/*` 的 E-04 八处 | **非污染(短语误吞)** | 八处讲的都是别的「静默丢」(会话历史 / memory hooks / 网关 wake / 审批出口),与 `approvals.deny` 无关 |

三处最能说明「命中 ≠ 污染」的原文:

`chapters/r7b-platform-integration.md:835 @ 863e313`

```
> **为什么从 ▲ 降到 ◇。** 本章初稿写的是"文档把这三个方法列在『有基类默认桩』的标题下"——
```

`chapters/r6-memory-provider-ecosystem.md:505 @ 863e313`

```
**错误二:加载器不是"只读 description"。** 清单解析器一次读 8 个字段,其中就有一个**钩子字段**:
```

`chapters/r4-execution-environments.md:797 @ 863e313`

```
- **`website/docs/user-guide/features/tools.md:88 @ 863e313` "容器关机即删" —— 证伪(对默认态)**。默认 persist、清理对容器 no-op、容器跨进程存活
```

**所以判据 1 在成品章上的真命中 = 0,而这个 0 是逐处读出来的,不是搜不到。**
**成品章把改判写进正文,是 R3 硬标准要求的**(「改判处就地写明原判是什么、为什么撤、依据是什么」),
所以**短语必然出现在章里** —— 判据 1 用在成品章上,天然是一个「高召回、低精度」的筛子,
它的产出必须靠人读完才算数。

### 3.1 制度文件的 42 处:唯一一处真污染

E-05(`没有第三个`)6 处、E-04(`静默抹掉`)3 处、E-28 1 处,其余 32 处是 E-26 负控。
E-05 的 6 处全部是「负结论的成本」这条纪律**拿它当反例**,方向与改判一致:

`CLAUDE.md:344 @ 25c612f`

```
- **负结论的成本(R8-fix,review-1 附录 A-1/A-2)**:"全仓没有 X""没有第三个调用方"
```

逐处读后只有一处是把**已被推翻的事实定性**当结论用:

`data/r10/dispatch-brief.md:51 @ 863e313`

```
  *(历史教训:一条"没有第三个读原始配置后落盘的调用方"的负结论关闭了调查,
  而漏掉的那个会在坏 YAML 下把用户的审批黑名单静默抹掉。
```

而 R8C 已经推翻「静默」这个定性:

`notes/r8c-90-rulings.md:387 @ 863e313`

```
## 7. 改判前轮定案:■-R8B-12 的「静默消失」不成立
```

R8C 在同一节里逐字引了被推翻的那句原文:

`notes/r8c-90-rulings.md:398 @ 863e313`

```
> 落盘文件就只剩 `model:` 一段,其余配置——包括 `approvals.deny`——静默消失。**
```

推翻它的是基线代码自己:同一次运行会把坏文件**逐字快照**下来,并对每个坏文件打第一次告警。

`hermes_cli/config.py:114 @ 863e313`

```
    first warning for a given broken file we also snapshot it to a
```

`CLAUDE.md` 的同一句已由 R11B 挂上更正节:

`CLAUDE.md:351 @ 25c612f`

```
  > **R11B 更正**:此处原写"把用户的 `approvals.deny` **静默抹掉**"。该定性已被 **R8C 推翻**
```

**为什么派工书这一处比 `CLAUDE.md` 那一处更值得记。** `CLAUDE.md` 是**一份**、人人读、
R11B 已经在它上面留了更正;派工书是**每轮一份、按上一轮的抄**,一条错的表述留在里面,
下一轮复制模板时会**再生一份**。R11A 就有一条错的说法这样活过一轮(H-R11A-g)。
本片实测:这条只在 R10 那一份里,**R10B / R11A / R11B / R11C 四份都没有抄走它**:

```verify
cd "$(git rev-parse --show-toplevel)" && grep -c "静默抹掉" data/r10/dispatch-brief.md data/r10b/dispatch-brief.md data/r11a/dispatch-brief.md data/r11b/dispatch-brief.md data/r11c/dispatch-brief.md
```

```text
data/r10/dispatch-brief.md:1
data/r10b/dispatch-brief.md:0
data/r11a/dispatch-brief.md:0
data/r11b/dispatch-brief.md:0
data/r11c/dispatch-brief.md:0
```

**这是一条好消息,但它不是「模板不会传染」的证据** —— R10B 起这段被改写成了更短的
一句话纪律:

`data/r10b/dispatch-brief.md:91 @ 863e313`

```
「全仓没有 X」「没有第三个调用方」这类**全称否定**,可信度等于一次 grep 的完备性,
```

**事实定性那半句是在改写中掉的,不是被改正的** —— 新版本压根没提后果是什么。
换句话说:**这次没传下去是运气,不是机制。**

---

## 4. 判据 2:可复算指标的「第二份手抄件」—— 为什么必须另设,以及正控

**结论:命中 3 处,全在 `chapters/r1-what-is-hermes-agent.md`。两处是主线给的正控
(分层表 L1 / L2),第三处是本判据自己找出来的、正控没提的:`R1-inventoried` 剩余量
写 8,122 文件 / 2,236,870 行,台账真值是 5,944 / 1,495,470 —— 差 2,178 个文件。**

### 4.1 为什么判据 1 抓不到正控(先回答派工书的那个问题)

派工书给的正控是 `chapters/r1-what-is-hermes-agent.md:98-123 @ 25c612f` 的分层表整段过期。
**用 §2 的清单去搜,一定搜不到它**,原因有三层,每一层都得说清:

1. **案号法**:成品章按制度不写案号(读数见下),
   所以 R11B 那条路径在成品章上的命中数**恒为一个与内容无关的小数**。
2. **短语法**:被推翻的说法是「L1 = 412 / 382,770」。**那串数字已经被 review-1 修掉了**,
   现在章里印的是 511 / 479,923 —— 它**在改判发生时是对的**。
   拿旧短语去搜,只会搜到章里那段自我检讨(`:112`),而正控本身**不含任何旧短语**。
3. **更根本的一层**:根本没有任何一条改判说过「511 是错的」。
   **这类过期不是被谁推翻的,是被时间推翻的**——它的真值是一个**移动的函数**,
   而正文把某一天的取值以现在时钉住了。改判清单里根本不会有它的条目。

第 1 层的读数:

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11c/e-reversal-propagation-scan.py --casedensity
```

```text
chapters: 案号出现 9 次,分布在 2 份
notes: 案号出现 1414 次,分布在 95 份
reports: 案号出现 421 次,分布在 13 份
```

**21 份成品章合计只出现 9 次案号,分布在 2 份里;`notes/` 是 1,414 次 / 95 份。**
这就是「案号法在成品章上天然近乎零命中」的读数 —— 案号密度差了**两个数量级**,
**而 R11B 的路径 ② 完全建立在案号上**。正则与 R11B 探针里的 `RE_H` / `RE_G` 逐字相同,不另起口径。

**这个测量必须报两个读数(它对本轮自身不幂等)。** 上面是**钉住的 commit** 口径;
同一条判据读**工作区**时,本片取数当时 `notes/` 是 **1,673 次 / 99 份** —— 多出的 259 次来自
本片自己的底稿(写满了 `H-R11C-E-*`)与**当时并发在写的片 B / 片 C**。
`chapters/` 两个口径都是 9(本轮不改成品章),`reports/` 都是 421。
**差额全在 `notes/` 这一格,而它恰好是本片要拿来当对照的那一格** ——
若照工作区口径写,这份底稿会把自己的案号算进「案号密度高」的证据里。

*那个 1,673 **故意不配 ```verify 块**:它量的正是一棵**正在动的工作树**
(片 C 已于 `e44ba85` 合入、片 B / 片 D 仍在写),重跑必然给出别的数。
按「shell 命令即证据」那条规矩,**跑不出原值的命令不许伪装成可重跑的证据**;
这里要说明的现象恰恰就是「它会变」,所以它以一次带口径的历史读数出现,而不是一条关卡钉住的数。*

**所以本片对成品章另设的判据是「不预设答案」的**:运行期从权威源复算,
再去目标面找同名指标的手抄件 —— 判据里不出现任何一个具体数字。

### 4.2 判据 2 的机械形态与结果

判据:**凡是能被脚本从权威源算出的项目级指标,正文里的第二份手抄件必须与之相等。**
权威源 = `data/ledger.tsv`(分层五行 + `status` 列的 `R1-inventoried` 剩余量)。

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11c/e-reversal-propagation-derived.py
```

```text
STALE chapters/r1-what-is-hermes-agent.md:103 L1 手抄=(511, 479923) 台账真值=(563, 522207)
STALE chapters/r1-what-is-hermes-agent.md:104 L2 手抄=(2183, 713923) 台账真值=(2131, 671639)
ok    chapters/r1-what-is-hermes-agent.md:105 L3 手抄=(1895, 602085) 台账真值=(1895, 602085)
ok    chapters/r1-what-is-hermes-agent.md:106 L4 手抄=(560, 55902) 台账真值=(560, 55902)
ok    chapters/r1-what-is-hermes-agent.md:107 LT 手抄=(3381, 756619) 台账真值=(3381, 756619)
# 分层表手抄件:STALE=2
STALE chapters/r1-what-is-hermes-agent.md:119 R1-inventoried 手抄邻域=[408, 8122, 8530, 2236870] 台账真值=(5944, 1495470)
# R1-inventoried 手抄件:STALE=1
# 覆盖面:成品章「现在时 + 数字」的行 16 行;本判据可复算的指标 2 个(分层表、R1-inventoried)
```

**正控被抓到了,而且是被「运行期复算」抓到的,不是被我事先知道答案抓到的**
—— 同一次运行里 L3 / L4 / LT 三行判 `ok`,与 `CLAUDE.md` 记的「L3/L4/LT 连续五轮一字未改」一致;
若判据是照着答案写的,它不会顺手把这三行判对。

### 4.3 三处命中的原文

`chapters/r1-what-is-hermes-agent.md:98 @ 25c612f`

```
五个层(`data/ledger.tsv` 台账,`scripts/verify_ledger.py` 校验)。**下表是当前值,不是历史快照**
```

`chapters/r1-what-is-hermes-agent.md:103-104 @ 25c612f`

```
| **L1 机制精读** | harness 核心机制,要逐行读透、能凭笔记重实现 | 511 | 479,923 |
| **L2 结构级理解** | 支撑性代码,画得出结构、定位得到功能,不逐行 | 2,183 | 713,923 |
```

`chapters/r1-what-is-hermes-agent.md:118-119 @ 25c612f`

```
**不**回答"它学过没有"。后者在台账的 `status` 列里,当前仍有 **8,122 个文件 / 2,236,870 行**
停在 `R1-inventoried`(= 只盘点过、没开工),即 8,530 − 8,122 = **408 个文件**被真正处理过。
```

**同一个 8,122 在 `CLAUDE.md` 里是对的**,因为它在那里是一句**历史陈述**:

`CLAUDE.md:219 @ 25c612f`

```
  R7 起这条线索中断了五轮,期间实际仍有 8,122 个文件从未开工。*
```

**同一个数,一处写成「R7 起…期间」是史实,一处写成「当前仍有」就是错的** ——
差别不在数字,在时态。这也说明成品章那处不是抄错了,是**抄对了然后没跟着走**。

**第三处比正控严重。** 它不只是一个数过期:章里那句「**8,530 − 8,122 = 408 个文件**被真正处理过」
是一句**推导**,现在的真值是 8,530 − 5,944 = **2,586 个文件**。
读者拿到的不是一个旧数字,是一个**关于项目进度的、错了六倍的判断**
—— 而 `CLAUDE.md` 立「每轮报告恢复必报项」这条规矩,正是因为「全仓无黑洞」这个最终目的的
**唯一可观测指标就是 `status` 列**。

### 4.4 第二次发作:同一张表、同一个病、同一份检讨还挂在旁边

章里紧挨着分层表的那段引用块,写的就是这张表**上一次**过期时的检讨:

`chapters/r1-what-is-hermes-agent.md:112 @ 25c612f`

```
> 早先本章印的是 R1 期那一版(412 / 382,770 与 2,282 / 811,076),**却以现在时陈述**——
```

`chapters/r1-what-is-hermes-agent.md:114 @ 25c612f`

```
> 现已改为从台账取值(review-1 阻断-2 / M-2)。**教训**:凡是能被脚本算出来的数,
```

**「现已改为从台账取值」这句话本身是不成立的**:改的是**那一次的取值**,不是取值的**方式**
—— 正文里仍是一份手抄件,没有任何机制让它跟着台账走。
`CLAUDE.md` 立的关卡里没有一条覆盖这个形状:`verify_ledger.py` 校验的是台账自身,
`verify_citations.py` 校验的是**引用**与基线是否一致 —— 而这张表**不是引用**,
它没有 `路径:行号` 锚点,自然也不在任何一个关卡的分母里。

### 4.5 传播半径(两个口径,不得写成同一个数)

过期值在全语料的分布。**这不是缺陷计数**:`reports/` 是某一轮的历史记录,
写着当轮真值是**正确**的;只有**以现在时陈述**的位置才是污染。

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11c/e-reversal-propagation-derived.py --blast | grep -E '^#|口径'
```

```text
# 过期值(带千分位者):2,183 479,923 713,923
2,183	散文口径	命中 5	chapters=1 notes=1 reports=2 reviews=1
2,183	脚本输出口径	命中 11	notes=7 reports=3 reviews=1
479,923	散文口径	命中 11	chapters=2 notes=3 reports=4 reviews=2
479,923	脚本输出口径	命中 4	reports=3 reviews=1
713,923	散文口径	命中 5	chapters=1 notes=1 reports=2 reviews=1
713,923	脚本输出口径	命中 4	reports=3 reviews=1
```

**两个口径分别标注**:「散文口径」量带千分位的写法(`479,923`),「脚本输出口径」量裸写法
(`479923`,即 `verify_ledger.py` 打印的形态,且已排除同一行里已被散文口径计过的)。
`2,183` 的裸口径 11 处**含噪音**——`2183` 在语料里也可能是行号或字节数,本片未逐处读它,
**故这一格只作上界,不作结论**。裸 `511` / `560` 这类三位数完全不量,理由与 E-26 负控相同。

### 4.6 判据 2 的覆盖限度(必须写,否则是谎报覆盖率)

- 本判据只覆盖**两个**有权威源可复算的项目级指标;成品章里「现在时 + 数字」的行共 **16 行**
  (上面 verify 块最后一行的读数)。
- 另外 14 行**逐行读过**,全部是**基线派生**的数(`_config_version` 当前 33、
  profile 名正则 6 份、`hermes_cli/dashboard_auth/middleware.py` 的 123 条路由、
  R8D 那 25 个顺序语义测试……)。**基线钉在 `863e313` 不动,所以它们不会因项目推进而过期**
  —— 这正是 `@ 863e313` 这条约定在做的事。
- **反过来说,`@ 863e313` 只免疫「基线派生」的数,不免疫「项目派生」的数**,
  而后者恰好没有任何约定、也没有任何关卡。判据 2 命中的 3 处,全部落在这个缺口里。

---

## 5. 判据 3:制度文件里对基线行为的事实定性

**结论:除 §3.1 那一处(`data/r10/dispatch-brief.md:52`)外,再无命中。**
另外两条可复算的制度断言当场复核**为真**,不是命中。

**搜索面**:`CLAUDE.md`(1 份)+ `data/*/dispatch-brief.md`(5 份)+ `data/r*/probes/*.py`
(74 份)+ `data/r11c/*.py` + `scripts/*.py`,合计 98 份 / 14,153 行(§1 的读数)。
**判据**:(a) §2 清单的 30 条短语全量打进这个面(结果见 §3);
(b) 制度文件里**可复算的自述数**逐条复算。

(b) 的两条:

`CLAUDE.md:98 @ 25c612f`

```
  `py mdx md yaml yml toml c h sh json tsx ts mjs js nix rs txt`(见
```

```verify
cd "$(git rev-parse --show-toplevel)" && sed -n 169p scripts/verify_citations.py
```

```text
CITE_EXTS = "py|mdx|md|yaml|yml|toml|c|h|sh|json|tsx|ts|mjs|js|nix|rs|txt"
```

**一致**。第二条,`CLAUDE.md` 说 `EXTLESS_NAMES` 取自基线实际存在的无扩展名文件、共 26 个:

```verify
cd "$(git rev-parse --show-toplevel)" && python3 -c "
import re
src = open('scripts/verify_citations.py', encoding='utf-8').read()
m = re.search(r'EXTLESS_NAMES = frozenset\(\{(.*?)\}\)', src, re.S)
print('EXTLESS_NAMES 条数 =', len(re.findall(r'\"[^\"]+\"', m.group(1))))
"
```

```text
EXTLESS_NAMES 条数 = 26
```

**一致**。

**探针 docstring 的负结论**:74 份 `data/r*/probes/*.py` 里,把已改判结论当结论用的 **0 处**。
搜索面 = 全部 74 份的全文(不限 docstring —— 只搜 docstring 会漏掉行内注释,
而 `data/r11c/probes/handover_census_r11c.py:71` 那条 `iron` 注释正是行内的);
模式 = §2 的 30 条短语 + `静默|不成立|证伪|推翻|没有第三个|关机即删|只读 description|三家`。
命中的只有两类:**引用本项目自己的方法论教训**(如 `iron` 那条),
以及 `data/r11b/probes/rulings_reversal_scan.py` 的 docstring 在描述它自己的用途。

`data/r11c/probes/handover_census_r11c.py:71 @ 863e313`

```
# 这就是 r4-90 那条 `iron` 匹配到 `env`**`iron`**`ment` 的自检 grep,换了个部件。
```

```verify
cd "$(git rev-parse --show-toplevel)" && grep -lE '静默抹掉|静默消失|没有第三个|关机即删|只读 description|三家都与实现不符|后果更轻|目前无害|需起真实网关' data/r10/probes/*.py data/r10b/probes/*.py data/r11a/probes/*.py data/r11b/probes/*.py data/r11c/probes/*.py 2>/dev/null; echo "exit=$?"
```

```text
exit=1
```

*(`grep -l` 零命中退出 1、无 stderr —— 这正是 `CLAUDE.md` 记的那种「静默 exit-1」形态,
所以这里显式回显 `exit=$?`,让「零命中」这个结论本身可见,而不是靠一个空输出去暗示。)*

---

## 6. 测量污染:剔除与不剔除两个读数

**结论:两个读数不同(institutional 42 vs 48),差额 6 处全部来自 `data/r11c/`
—— 其中 3 处来自 R11C 派工书本身,1 处来自并发的片 F 探针,2 处来自片 A / 片 C 的探针。
本片自己的底稿不进目标面,所以它对判据 1 的读数**污染为零**,但那是面的定义带来的,不是运气。**

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11c/e-reversal-propagation-scan.py --phrases --keep-r11c | tail -1
```

```text
# 合计 chapters=75 institutional=48 (r11c-* 计入)
```

差额逐项:

| 条目 | 剔除 | 不剔除 | 多出来的位置 |
|---|---|---|---|
| E-21 `五个读取函数` | 0 | 1 | `data/r11c/f-pre-binding-inventory-scan.py:368`:`# 「五个读取函数」被 R8B 更正为六个,是本项目已知的成品章陈旧形态。` |
| E-26(负控)`iron` | 32 | 34 | `data/r11c/a-id-collisions-audit.py` 与 `data/r11c/probes/handover_census_r11c.py:71`:`# 这就是 r4-90 那条 `iron` 匹配到 `env`**`iron`**`ment` 的自检 grep,换了个部件。` |
| E-28 `读数相同` | 1 | 4 | `data/r11c/dispatch-brief.md:43`:`11. **同一指标多次/多方法测量分别标注**,不得写成「读数相同」。` 等 3 处 |

污染源的原文,两条各贴一处:

`data/r11c/dispatch-brief.md:43 @ 863e313`

```
11. **同一指标多次/多方法测量分别标注**,不得写成「读数相同」。
```

`data/r11c/f-pre-binding-inventory-scan.py:368 @ 863e313`

```
    # 「五个读取函数」被 R8B 更正为六个,是本项目已知的成品章陈旧形态。
```

**这三行是这条制度存在的理由的活样本。** 最尖锐的是 E-28:**派发本片这个动作本身**
把命中数从 1 抬到 4,因为派工书里写着我要搜的那个短语。
其次是 E-21:**并发的片 F** 在它的探针注释里点名了「五个读取函数」这条已改判结论,
于是我在同一轮里搜自己兄弟片的产出。**没有任何脚本会发现这两种污染。**

**本片底稿为什么污染为零**:`notes/r11c-raw-reversal-propagation.md` 是 `notes/` 文件,
而判据 1 的目标面是 `chapters/` + 制度文件,**`notes/` 不在其中**(§1 排除面第 2 条)。
换句话说,零污染是**面的定义**给的,不是「我写得小心」。
**若下一轮把目标面扩到 `notes/`,这份底稿会为几乎每一条 E-xx 贡献命中**
—— 因为 §2 那张表逐条抄了被推翻说法的原文。届时必须按前缀剔除 `r11c-*`。

---

## 7. 逐条结果表(命中为零的也逐条给短语与搜索面)

搜索面对全部 30 条一致:**目标面甲** = `chapters/*.md` 21 份 / 12,576 行;
**目标面乙** = 制度文件 98 份 / 14,153 行(剔除 `r11c-*` 后 90 份);语料钉在 `f440d78`。
「真命中」列 = 逐处读后判定为**把已被推翻的说法当结论用**的处数。

| 编号 | 短语 | 字面命中(章/制度) | 真命中 | 逐处判定 |
|---|---|---|---|---|
| E-01 | `关机即删` | 1 / 0 | 0 | 章在陈述该文档已被证伪 |
| E-02 | `20+ 平台` + `▲` | 0 / 0 | 0 | 零命中 |
| E-03 | `Tool Search` + `无文档` | 0 / 0 | 0 | 零命中 |
| E-04 | `静默抹掉`/`静默消失` | 8 / 3 | **1** | 章 8 处讲别的「静默丢」;制度 3 处里 `data/r10/dispatch-brief.md:52` 是真命中 |
| E-05 | `没有第三个` | 0 / 6 | 0 | 6 处全是「负结论的成本」这条纪律在引用它当反例 |
| E-06 | `PairingStore` + `▲` | 0 / 0 | 0 | 零命中 |
| E-07 | `waitpid` + `不主张` | 0 / 0 | 0 | 零命中 |
| E-08 | `24 个平台束` + `▲` | 0 / 0 | 0 | 零命中 |
| E-09 | `需起真实网关` | 0 / 0 | 0 | 零命中 |
| E-10 | `抄了一份` + `STT` | 0 / 0 | 0 | 零命中 |
| E-11 | `目前无害` | 0 / 0 | 0 | 零命中 |
| E-12 | `后果更轻` | 0 / 0 | 0 | 零命中 |
| E-13 | `比对配置的 connector host` | 0 / 0 | 0 | 零命中(种子案未进成品章) |
| E-14 | `忙时…不往下送` | 1 / 0 | 0 | r7b 章在复盘那次写反 |
| E-15 | `26 万行` | 0 / 0 | 0 | 零命中(阻断-3 已修净) |
| E-16 | `有基类默认桩` | 1 / 0 | 0 | r7b 章在讲「为什么从 ▲ 降到 ◇」 |
| E-17 | `三家都与实现不符` | 2 / 0 | 0 | r6 章引原说法 + 紧接着改判 |
| E-18 | 两键名 + `同一个` | 0 / 0 | 0 | 零命中 |
| E-19 | `17 个 ContextVar` | 0 / 0 | 0 | 零命中 |
| E-20 | `只读 description` | 2 / 0 | 0 | r6 章引原说法 + 「错误二」 |
| E-21 | `五个读取函数` | 0 / 0 | 0 | 零命中(剔除 r11c-* 后;见 §6) |
| E-22 | 超时数 + 无分支限定 | 0 / 0 | 0 | 零命中 |
| E-23 | `共 16 条` | 0 / 0 | 0 | 零命中 |
| E-24 | `89 个包` | 0 / 0 | 0 | 零命中 |
| E-25 | `H-14` + `结清` | 0 / 0 | 0 | 零命中 |
| E-26 | `iron`(**负控**) | 59 / 32 | — | 全部是 `env`**`iron`**`ment` 路径,示范短语法误吞 |
| E-27 | `8,530 个文件` + `26 万` | 1 / 0 | 0 | r1 章 `:21` 写的是改判后的 260 万行 |
| E-28 | `读数相同` | 0 / 1 | 0 | `CLAUDE.md:290` 是纪律本身 |
| E-29 | `业务无影响` 等 | 0 / 0 | 0 | 零命中 |
| E-30 | `两道无条件地板` | 0 / 0 | 0 | 零命中 |

**判据 2 与判据 3 的逐条结果见 §4 / §5**(判据 2:3 命中 / 2 指标;判据 3:1 命中 / 2 复算断言)。

**零命中条目的可信度限度(负结论必须说清)**:上表**字面零命中 20 条**
(两个面都是 0;另有 E-05 / E-28 字面有命中但真命中为 0),
**它们只证明「这条短语在这两个面上不出现」**。它不排除三种情形:(a) 同一条结论以**别的措辞**活在成品章里;
(b) 结论被**图**(Mermaid 节点标签)承载 —— 本片未对图内文本另设判据;
(c) 结论被**概括**成一句不含任何原短语的话。
**(a)(c) 两类正是判据 2 那一族的东西**,而判据 2 目前只覆盖 2 个可复算指标,**远不是全面**。

---

## 8. 交主线的污染点清单(本片只查不改)

按 `CLAUDE.md` 的改法边界分类。**本片一个字都没改。**

| # | 位置 | 现状 | 应改成 | 依据 | 改法归属 |
|---|---|---|---|---|---|
| P-1 | `chapters/r1-what-is-hermes-agent.md:103 @ 25c612f`:`| **L1 机制精读** | harness 核心机制,要逐行读透、能凭笔记重实现 | 511 | 479,923 |` | L1 = 511 / 479,923 | 563 / 522,207 | `data/ledger.tsv` 复算(§4.2) | `chapters/` 直接改正文 |
| P-2 | `chapters/r1-what-is-hermes-agent.md:104 @ 25c612f`:`| **L2 结构级理解** | 支撑性代码,画得出结构、定位得到功能,不逐行 | 2,183 | 713,923 |` | L2 = 2,183 / 713,923 | 2,131 / 671,639 | 同上 | `chapters/` 直接改正文 |
| P-3 | `chapters/r1-what-is-hermes-agent.md:118 @ 25c612f`:`**不**回答"它学过没有"。后者在台账的 `status` 列里,当前仍有 **8,122 个文件 / 2,236,870 行**` | 8,122 / 2,236,870,且推出「408 个文件被处理过」 | 5,944 / 1,495,470,推出 **2,586** | 同上 | `chapters/` 直接改正文 |
| P-4 | `chapters/r1-what-is-hermes-agent.md:111 @ 25c612f`:`> L1 的轨迹是 412(R1)→ 436(R6)→ 446(R7C)→ 461(R8A)→ **511**(R8B),L2 相应递减。` | 轨迹停在 R8B | 轨迹应续到当前(563) | 同上 | `chapters/` 直接改正文 |
| P-5 | `data/r10/dispatch-brief.md:52`:`  而漏掉的那个会在坏 YAML 下把用户的审批黑名单静默抹掉。` | 「静默抹掉」 | 「截断落盘 —— 有 stderr 告警、有带时间戳逐字备份」 | R8C 改判(§3.1) | 派工书是历史派工记录,建议照 `reports/` 的办法挂勘误,不静默改写 |

**P-1…P-4 建议同时改掉病根,而不只是改数**(否则第三次发作只是时间问题)。
两条可选的病根修法:
- **甲(最小)**:把这段数字换成一句「跑 `scripts/verify_ledger.py` 会打印当前五行」
  + 一个**带日期的快照**,即章里那段检讨自己给的教训(`:114`「凡是能被脚本算出来的数,
  正文就不该有第二份手抄件;抄了就得说清抄的是哪一天」)。
- **乙(有关卡)**:把 `data/r11c/e-reversal-propagation-derived.py` 的判据收进
  `scripts/`,进入每轮必跑的关卡集合。**本片不做这件事**——按派工书,子代理运行期不得动 `scripts/`。

---

## 9. 与 R11B 的口径差(三处,均不得写成「读数相同」)

| 指标 | R11B 读数 | 本片读数 | 口径差 |
|---|---|---|---|
| 源面文件数 | 266 份 | 286 份 | R11B 排除 `reviews/` 与派工书,且语料钉在 `00f09bf`;本片纳入并钉在 `f440d78`(其间 R11B 与 R11C 片 A/C/F 已合入)。**差额同时含「面扩大」与「语料长大」两项,不可归因于单一原因** |
| 定案级改判行 | 83(带案号 33) | 131(带案号/评审编号 63) | 除源面差外,本片的行类型多认了「引用块首」,并把 `阻断-N`/`建议-N` 计为编号 |
| 「后轮覆盖」命中 | 2 条 | 判据 1 真命中 1 条 + 判据 2 命中 3 处 + 判据 3 复核 2 条为真 | **完全不同的判据**:R11B 查 `reports/`+`notes/` 的案号与短语;本片查 `chapters/`+制度文件,且新增了「可复算指标手抄件」这一族。R11B 的 2 条(种子案 + `CLAUDE.md`)**本片未重测**,不计入 |

---

## 10. 未做 / 需要但没装

- **未做**:成品章里的 **Mermaid 图内文本**未另设判据(§7 限度 (b))。图节点标签也会承载结论,
  且它不进散文行的正则。
- **未做**:判据 2 只覆盖 2 个可复算的项目级指标。**其余项目级派生数(如各轮报告里的
  citations / OK / 可校验比例、venv 包数)在成品章里没有出现**,故本轮没有第三个指标可查;
  但这不等于将来不会有。
- **未做**:`reviews/` 只作源面。若将来有第二次评审,评审报告之间的相互引用会成为新的传播路径。
- **需要但没装**:无。本片只读语料、读 `data/ledger.tsv`、读 `scripts/verify_citations.py`,
  **未跑基线代码、未装任何包、未动 venv**。
- **基线**:全程只读。

```verify
cd "$(git rev-parse --show-toplevel)" && git -C /home/user/hermes-agent status --porcelain | wc -l
```

```text
0
```

---

## 移交

| 移交项 | 去向 | 锚点 + 现象 |
|---|---|---|
| **H-R11C-E-a** | R12 装订前(**必须**,否则蓝图第一章印错数) | `chapters/r1-what-is-hermes-agent.md:103 @ 25c612f`:`| **L1 机制精读** | harness 核心机制,要逐行读透、能凭笔记重实现 | 511 | 479,923 |` —— 分层表 L1/L2 两行是手抄件,与 `data/ledger.tsv` 复算值(563 / 522,207;2,131 / 671,639)不符,而同段明写「下表是当前值」。**第二次发作**,第一次是 review-1 阻断-2 |
| **H-R11C-E-b** | R12 装订前(**必须**) | `chapters/r1-what-is-hermes-agent.md:118 @ 25c612f`:`**不**回答"它学过没有"。后者在台账的 `status` 列里,当前仍有 **8,122 个文件 / 2,236,870 行**` —— 真值 5,944 / 1,495,470;由它推出的「408 个文件被真正处理过」真值是 2,586,**错了六倍**,且这是「全仓无黑洞」的唯一可观测指标 |
| **H-R11C-E-c** | 立关卡的那一轮 | `scripts/verify_ledger.py:1`:`#!/usr/bin/env python3` —— 全项目**没有任何关卡**覆盖「正文里可复算指标的第二份手抄件」这个形状:`verify_ledger.py` 只校验台账自身,`verify_citations.py` 只校验带锚点的引用,而这张表没有锚点。判据已实现为 `data/r11c/e-reversal-propagation-derived.py`,建议收进 `scripts/` |
| **H-R11C-E-d** | 接手派工书模板的那一轮 | `data/r10/dispatch-brief.md:52`:`  而漏掉的那个会在坏 YAML 下把用户的审批黑名单静默抹掉。` —— 把 R8C 已推翻的「静默」定性写进了派工书;R10B 起该段被改写、那半句是**掉了**而不是**被改正**,故机制上仍会复发 |
| **H-R11C-E-e** | 修锚点的那一轮(与片 D 同族) | `notes/r11b-raw-rulings-census.md:783`:`| 「H-R8D-c 后果更轻」 | `notes/r9a-h-r8d-c-env-loader-lock.md:700` 的 `「后果更轻」的前提被推翻` | `后果更轻` / `_SECRET_SOURCES` 在 R9B 及以后 | **0 命中**:R9B 的引用是在改锚点行号,不涉及定性 |` —— 表内锚点 `:700` 的真实位置是 `:730`,差 30 行;它至今记 TABLE-UNCHECKED,**R11B / R11C 两轮引用关卡都没读过它** |
| **H-R11C-E-f** | 下一次做同类普查的那一轮 | `data/r11c/e-reversal-propagation-scan.py:105`:`def ledger_lines():` —— 定案级改判行普查在 `CLAUDE.md` 上报 **0 行**,而那里确有一条改判(`CLAUDE.md:351` 的 R11B 更正):判据要求带案号或记号,而制度文件的改判**不带号**。与 R11C 主线在 `CLAUDE.md` 里记的「认不出表头的表必须以 UNCLASSIFIED 出现」同一物种 |

---

## 11. 自校验读数

`python3 scripts/verify_citations.py /home/user/hermes-agent notes/r11c-raw-reversal-propagation.md`
—— **退出码 0**,0 MISMATCH / 0 BLOCK-DRIFT / 0 TABLE-DRIFT / 0 TABLE-OUT-OF-RANGE:

```text
citations=31  OK=23  UNCHECKED=8
可校验比例 OK/31 = 74.2%
table_anchors=53  OK=35  UNCHECKED=18
OK: every code-block-backed citation matches the baseline
```

*(这个读数**对「报告它」这个动作不幂等**:每在正文里多写一个锚点,分母就涨一。
写本节的过程中 citations 自己从 29 涨到 31,比例随之在 75.9% / 73.3% / 71.0% 之间跳,
**跳动全部由本节自己造成**。与 `CLAUDE.md` 记的「点名覆盖率」污染同一物种;
上面贴的是**全文定稿之后**重跑的那一次读数。)*

`python3 scripts/verify_evidence_commands.py notes/r11c-raw-reversal-propagation.md`
—— **退出码 0**:

```text
verify-blocks paired=13  unpaired=0  differing=0  timedout=0
runnability   ran=0  runfail=0  skipped-mutating=0
OK: every paired ```verify command reproduces its pasted output
```

*(按 `CLAUDE.md`「自校验读数不能写进 ```verify 块」——一个跑校验器扫本文件的命令会无限递归,
故这两组数贴在 ```` ```text ```` 里。)*

**证据命令关卡在本片抓到过一次真错**,值得记下来:§4.1 的「案号密度」那条 verify 块,
第一版贴的输出**是我按预期写的、从未由该命令产生过** —— 重跑得到空输出,关卡判 `differing=1`。
真跑之后的结论比原来那个更强(成品章 9 次 vs `notes/` 1,414 次),但**原来那个数是编的**。
这正是 `CLAUDE.md` 立这条关卡时点名要防的形态:「一段从未由该命令产生过的 diff 被写进了底稿,
数字看起来完全合理」。**人工评审抓不住这一类,因为它要求评审者真的去跑那条命令。**

---

## 完成信号

**片 E 完成。** 产出三个文件:

1. `notes/r11c-raw-reversal-propagation.md`(本文件)—— 含「已改判结论」清单 30 条
   (§2,逐条带被推翻说法的原文)、三条判据的搜索面与逐条结果(§3 / §4 / §5)、
   污染两读数(§6)、逐条结果表含全部零命中条目(§7)、
   **交主线的污染点清单 P-1…P-5(§8)**、与 R11B 的三处口径差(§9)、移交 6 条。
2. `data/r11c/e-reversal-propagation-scan.py` —— 判据 1 与搜索面清点(`--surface` / `--ledger`
   / `--phrases` / `--keep-r11c` / `--casedensity`),`PHRASES` 表与 §2 清单一一对应,含 E-26 负控。
3. `data/r11c/e-reversal-propagation-derived.py` —— 判据 2(可复算指标的第二份手抄件),
   运行期从 `data/ledger.tsv` 复算,不预设答案;`--blast` 报过期值传播半径(两个口径)。

**关键结论**:正控(`chapters/r1-what-is-hermes-agent.md:98-123 @ 25c612f` 分层表)**被判据 2 抓到**,
判据 1 抓不到 —— 原因逐层写在 §4.1。判据 2 另外抓出正控**未提及**的第三处
(`:118` 的 `R1-inventoried` 剩余量,错 2,178 个文件,由它推出的进度判断错六倍)。

**本片未改任何文件**:不改 `chapters/`、不改历史 `notes/`、不改 `CLAUDE.md`、不改 `scripts/`、
不动基线。**未 commit、未 push。claim 由主线关。**
