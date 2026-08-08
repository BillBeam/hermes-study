# 全量质量评审 · 第一次(独立评审位)

十章可读,r7 不可读,六处内容错误。

---

## 0. 评审对象与钉死的 commit

| 项 | 值 |
|---|---|
| **被评审 commit** | `38b65bb635f3eee7f758fcfe1087815d3aaa691f`(短 SHA `38b65bb`) |
| 来源分支 | `origin/claude/r8b-cli-trunk-interaction-yobiao` |
| 为什么不是 main | `origin/main` 头是 `fae9b3a`(Merge round 8A);`git merge-base --is-ancestor r8b main` 判否,**main 不含 R8B**,故按任务约定改钉 r8b 分支头 |
| 学习对象基线 | `863e31318553cda8ad61df681d08175364d4164b`,`git status --porcelain` 空,全程只读 |

本报告内所有 `文件:行号@38b65bb` 均以 `sed -n` 在该 commit 的工作树上实测确认;
所有 `路径:行号 @ 863e313` 均为评审位在基线自行取证,未复用产出方给出的行号。

---

## 1. 评审方法与抽样策略(自定,如实申报)

分三条独立取证线,刻意让它们互相不依赖:

**(一)机器可判的部分,全量跑,不抽样。** 先把产出方自己的两道关卡在被评审 commit 上重跑一遍,
再另写四个一次性统计脚本量化引用纪律。这条线覆盖率 100%,结论可复算:

```
python3 scripts/verify_ledger.py   /home/user/hermes-agent data/ledger.tsv     → OK
python3 scripts/verify_citations.py /home/user/hermes-agent chapters/*.md       → FAIL(2)
python3 scripts/verify_citations.py /home/user/hermes-agent reports/*.md        → FAIL(2)
python3 scripts/verify_citations.py /home/user/hermes-agent notes/*-90-*.md ... → FAIL(5)
```

**(二)读者体验,主线亲读,11 章逐章全文读完,不抽样。** 对着 CLAUDE.md 的读者画像与六条硬标准逐条过。
判定用的是"这一节有没有场景开场""这段话该读者能不能复述",而不是"写得好不好"。

**(三)解读正确性,按"承重度"分层抽样,不按篇幅平均。** 抽样口径刻意**避开**带代码块的引用
——那一层 `verify_citations.py` 已经逐字比过了,评审位在那里没有增量价值。选的是:

1. **可复算的数字**(行数、条目数、集合大小、分层加总):凡出现即抽,因为它是**唯一能被
   第三方零成本推翻**的一类断言,也最能检验产出方的自校验纪律;
2. **全称断言**("唯一""全仓无""恒为真""从不"):这类一旦错就是硬错;
3. **顺序 / 优先级断言**(谁先于谁、哪一层做决定):重实现时的分歧点;
4. **跨章讲同一机制处**:一致性只能这样查。

本轮评审位亲自到基线取证 **58 条**断言,其中 **44 条完全成立**、5 条不精确、9 条为内容错误
(9 条归并为 6 条阻断意见)。另有一条独立取证线对 7 份定案卷做了 62 条两侧核实。
计数口径与不重复计数的说明见 §6.2;确认正确的不逐条罗列,只报数。

---

## 2. 总体判断(先给结论)

**这套产出的证据纪律,整体强于绝大多数同类学习笔记,且强度随轮次单调上升。**
本轮抽查的可复算数字里,r8a、r8b、r7c 三章**逐条命中**,包括一些相当苛刻的:

- r8a §3.9 命令注册表整张表(94 / 26 / 120 / 8+1 / 111,再按类目 43+24+24+18+2=111)——**五个数字全对**;
- r8a §4① 的对照实验(`OPTIONAL_ENV_VARS`=151、`_EXTRA_ENV_KEYS`=108、并集 239、重叠 20)——**四个数字全对**;
- r8b §4.3 的 `_HERMES_SUBCOMMANDS`(25)vs `_BUILTIN_SUBCOMMANDS`(68)、差集 44、`['honcho']`、合计 45——
  **连示例名单前 14 项都逐字对上**;
- r7c "94 条注册命令,其中 61 条在网关侧可用"——61 正是仓库自己 `GATEWAY_KNOWN_COMMANDS`
  谓词(`not cli_only or gateway_config_gate`)筛出的条目数,**用词精确到定义**。

**问题集中在三处:**

- **越早的轮次,引用纪律越弱。** r4/r5/r6/r7 四章共 87 处引用不写目录、不带 `@ 863e313`;
  而 r7c(11/11 带 SHA、0 处裸文件名)与 r8a(63/90 带 SHA、0 处裸文件名)几乎无瑕。
  **纪律是补上了,但没有回填**,于是最终《设计蓝图》前半本的溯源强度显著低于后半本。
- **r7 一章在可读性上明显掉队**,且它是唯一一条控制流内容错误的出处。
- **代码侧的自校验强度,没有等量地施加在"定案的另一半"上。** 六条阻断里有**三条**
  (阻断-4、5、6)属于同一形状:**代码侧读对了,判断哪个文档小节/哪个开关/哪几家插件时出了错**。
  根因是可诊断的——`verify_citations.py` 只校验紧跟围栏块的引用,而定案的**文档侧锚点**
  几乎总写成引用块,**从未被任何自动校验覆盖过**(见建议-15,本轮抽查即撞到 5 处锚点漂移)。
  代码侧有脚本兜着,所以稳;文档侧只有人工约定,所以漂——**而 R7C 升格这个脚本时给出的
  理由正是"人工约定这一层已被证明兜不住"。同一句话现在适用于文档侧。**

---

## 3. 逐章「读得下去 / 读不下去」判定

判定基准 = CLAUDE.md 的读者画像:多年后端经验(Go/Java)、**没读过本仓库**、**不熟 LLM provider
与 Python 异步生态**;不查外部资料、不看源码,能顺畅读完并**向他人复述每个机制**。

| 章 | 行数 | 判定 | 一句理由 |
|---|---:|---|---|
| `r1-what-is-hermes-agent.md` | 194 | **读得下去** | 进城地图该有的都有(TL;DR、场景、七部件图、路线),只是表里的数字过期,不挡读 |
| `r2-turn-loop-and-model-access.md` | 513 | **读得下去** | 十一个机制无一例外"场景→设计→取舍",空响应六级阶梯用流程图讲透,全书可读性标杆 |
| `r3-tool-infrastructure.md` | 385 | **读得下去** | "地板优先于开关"一句话立住主题,后面每道防线都能挂回这句上 |
| `r4-execution-environments.md` | 456 | **读得下去** | `pip install` 一条命令的一生串完全章,快照三个事故讲成了故事;扣分只在溯源(见 S1/S2) |
| `r5-session-state-and-persistence.md` | 412 | **读得下去** | 五块划分清楚,"一句继续昨天那个"的开场把持久层的全部难点一次演完 |
| `r6-memory-provider-ecosystem.md` | 347 | **读得下去** | 用 298 秒事故开篇、再看"八个后端在这两道围栏内侧各做了什么",结构非常省读者力气 |
| `r7-gateway-session-core.md` | 343 | **读不下去** | §5 是一段 15 行不分段、塞进约十条定案的文字块,§3.6/§3.8/§3.9 三节无场景开场直接甩类名与常量,该读者读完无法复述 |
| `r7b-platform-integration.md` | 766 | **读得下去** | 开场"四种搞砸的方式"表格极有效,#48300"两个各自正确的保守策略合起来是死锁"讲得读者能复述 |
| `r7c-gateway-periphery-and-scheduling.md` | 564 | **读得下去** | "一台网关的一天"时间线把四个输入面串成叙事,scale-to-zero 那节是全书最好的一段 bug 教学 |
| `r8a-configuration-surface.md` | 1747 | **读得下去** | 篇幅是次长章的 3 倍却不散,靠的是"两套东西一个名字"这条主线;§4 二十条原则偏长,但有编号可跳 |
| `r8b-cli-trunk-and-interaction.md` | 561 | **读得下去** | "配置键有三种死法"是本轮最好的组织发明,`global` 搬家那节把作用域讲成了故事 |

**关于 r7 的判定说明(避免被读成苛刻)**:这一章的**内容**并不比别章弱——memory_monitor
"移植完成、从未接线"的反转是全书最有价值的发现之一(评审位已独立复核成立,见 §6)。
判"读不下去"针对的是**呈现**:同一批素材在 r7c、r8a 里用小标题、表格、引用块拆开了,
在 r7 里压成了连续段落。这是**返工可修**的,不是重做。

---

## 4. 意见清单

分三级:**阻断**(内容错误)/ **建议**(可改进)/ **存疑**(需仲裁)。
凡涉及对 hermes-agent 源码理解的质疑,均先在基线取证并附原文块。

### 4.1 阻断(6 条)

---

#### 【阻断-1】r7 把"忙时消息不往下送"写反了,与基线、与 r7b、与 r7 自己的 §3.4 三重矛盾

**被评审位置**:`chapters/r7-gateway-session-core.md:36-37@38b65bb`

**被质疑原文**(逐字):

> 适配器层先查"这场对话是不是正有回合在跑"——在跑就把消息扣在适配器的
> pending 槽里,**不往下送**(这是双层守卫的第一层,属平台接入面,下一轮细讲)。

**为什么不成立**:忙时适配器**会**往下送。第一层守卫在入槽**之前**先调用网关装进来的忙时策略机,
策略机说"我处理了"就直接 return,根本走不到 pending 槽。

**基线证据(评审位自取)**——适配器侧的调用点:

`gateway/platforms/base.py:5711-5716 @ 863e313`

```python
            if self._busy_session_handler is not None:
                try:
                    if await self._busy_session_handler(event, session_key):
                        return
                except Exception as e:
                    logger.error("[%s] Busy-session handler failed: %s", self.name, e, exc_info=True)
```

这个 handler 由 `GatewayRunner` 装入,三个安装点:

`gateway/run.py:11096 @ 863e313`

```python
            adapter.set_busy_session_handler(self._handle_active_session_busy_message)
```

(另两处同调用:`gateway/run.py:12468`、`gateway/run.py:13410`。)

**三重矛盾**:
1. 与基线矛盾(上引);
2. 与 r7b 矛盾——`chapters/r7b-platform-integration.md:226@38b65bb` 的忙时决策树明确列着
   "问网关的忙时策略机,它说'处理了'就返回 `base.py:5711-5713`";
3. **与 r7 自己矛盾**——r7 §3.4 整节讲的忙时策略机就在 `gateway/run.py:8867-9003`,即网关侧。
   若消息真的"不往下送",§3.4 那一节永远执行不到。

**危害**:这是本章第一节、读者建立心智模型的地方。按此理解,读者会把"忙时四选一"
(interrupt / queue / steer / redirect)整个归给适配器层,而它实际归网关层——
**双层守卫的职责边界正好被划反**,这恰是 r7/r7b 两章合起来最想讲清的一件事。

**追加发现——这个错有出处,而且下一轮已经把它证伪了。** 评审位去核文档侧,
发现 r7 这句话与作者自绘地图的措辞高度重合:

`website/docs/developer-guide/gateway-internals.md:86 @ 863e313`

> 1. **Level 1 — Base adapter** (`gateway/platforms/base.py`): Checks `_active_sessions`. If the
>    session is active, queues the message in `_pending_messages` and sets an interrupt event.
>    **This catches messages *before* they reach the gateway runner.**

r7b 已经把这句话的**后半句**("and sets an interrupt event")作为 ▲1 证伪了
(`chapters/r7b-platform-integration.md:698-701@38b65bb`),评审位复核该证伪**成立**。
但**同一句的最后一句**("catches messages before they reach the gateway runner")
才是 r7 §1"不往下送"的来源,而 r7b 没有点它,r7 也就没有被纠正。

**这条比单点笔误更值得记**:同一句过时文档,一半被证伪、一半被原样采信写进了另一章。
证伪一条文档断言时,**该断言所在的整句/整段都要一并判定**,否则未被点名的那半句会以
"已经查过这里了"的名义活下来。

**建议改法**:把"不往下送"改为"先交给网关装入的忙时策略机;策略机不接手才落进适配器的
pending 槽",并把 `gateway/platforms/base.py:5711-5713 @ 863e313` 作为锚点补上;
同时把 `gateway-internals.md:86` 的"before they reach the gateway runner"补进 r7b 的 ▲1 范围。

---

#### 【阻断-2】r1 的分层表是 R1 期快照,与同 commit 的 `data/ledger.tsv` 不符,却以现在时陈述

**被评审位置**:`chapters/r1-what-is-hermes-agent.md:102-103@38b65bb`(表)、`:22@38b65bb`、`:109@38b65bb`

**被质疑原文**(逐字,表两行):

```
| **L1 机制精读** | harness 核心机制,要逐行读透、能凭笔记重实现 | 412 | 382,770 |
| **L2 结构级理解** | 支撑性代码,画得出结构、定位得到功能,不逐行 | 2,282 | 811,076 |
```

**为什么不成立**:在**同一个被评审 commit** 上跑产出方自己的校验脚本,L1/L2 已完全不是这两行:

```
$ python3 scripts/verify_ledger.py /home/user/hermes-agent data/ledger.tsv
OK baseline=863e31318 files=8530 total_lines=2608452
  L1: files=511 lines=479923
  L2: files=2183 lines=713923
  L3: files=1895 lines=602085
  L4: files=560 lines=55902
  LT: files=3381 lines=756619
  SUM == repo total: 2608452
```

评审位另用 awk 独立复算 `data/ledger.tsv`,得到同样五行,与脚本一致。
L3 / L4 / LT 三行与章节表**完全吻合**,只有 L1 / L2 两行错——因为后续轮次持续把文件从 L2 促升 L1
(`reports/round-6-*.md:32`:412→436;`round-7c:177`:436→446;`round-8a:616`:446→461;
`round-8b:253`:461→511),而 r1 章从未回填。

**连带两处**:
- `:22@38b65bb` "真正的'harness 核心机制'约 **38 万行**" → 应约 48 万行;
- `:109@38b65bb` "**测试(756,619 行)比核心机制(382,770 行)还多**" → 括号里的数过期。
  *(结论本身仍成立:756,619 > 479,923。错的是数,不是判断。)*

**为什么算内容错误而不是建议**:章节表的加总行(8,530 / 2,608,452)是对的,
所以表面上"自洽";一个照 CLAUDE.md 指引跑一遍 `verify_ledger.py` 来核对的读者,
会拿到两行不一致的数字,而**没有任何线索告诉他哪个是当前值**。全仓归层可校验是本项目
第一条验收标准,这张表就是它的门面。

**建议改法**:二选一,由仲裁定——(a) R12 装订时从 `data/ledger.tsv` **重新生成**这张表
(推荐,一次性消灭同类问题);(b) 保留 R1 快照但显式标注"截至 R1",并加一行当前值。

---

#### 【阻断-3】r1 同章内把仓库规模写成 26 万行与 260 万行两个数,差一个数量级

**被评审位置**:`chapters/r1-what-is-hermes-agent.md:94@38b65bb`

**被质疑原文**(逐字):

> 学一个 **26 万行**文本的仓库,最怕"黑洞"——某些文件从来没人交代过。

**为什么不成立**:同章 `:21@38b65bb` 写"全仓 8,530 个文件、**260 万行**文本",
`:107@38b65bb` 的表格合计写 **2,608,452**,`verify_ledger.py` 实测亦为 2,608,452。
26 万是 260 万的十分之一。

**危害**:低(读者几乎必然识别为笔误),但它出现在**全书第一章解释方法论的关键句**里,
而这本书的全部说服力建立在"每个数字都能核"上。**首章的数量级笔误对信任的损伤,
远大于它对理解的损伤。**

**建议改法**:`26 万` → `260 万`。

---

#### 【阻断-4】r7b 的 ▲4 把文档小标题挂错了对象:那三个方法从不在"有基类默认桩"标题下

**被评审位置**:`chapters/r7b-platform-integration.md:714-718@38b65bb`;同源
`notes/r7b-90-doc-conflict-rulings.md:134,136-140@38b65bb`

**被质疑原文**(逐字):

> **▲4**。文档把 `send_exec_approval` / `send_model_picker` / `send_choice_picker`
> 列在"有基类默认桩"的标题下,并说"不覆盖就优雅降级成纯文本"。
> **基类里这三个方法根本不存在**。……后果具体:照文档写适配器的人会去调
> `super().send_exec_approval(...)`,得到 `AttributeError`。

**代码侧成立,文档侧不成立**。基类确实没有这三个方法(评审位复核:
`grep -nE "def (send_exec_approval|send_model_picker|send_choice_picker)" gateway/platforms/base.py` **零命中**)。
但文档从未把它们放在那个标题下——**它们在另一个小节里**:

`gateway/platforms/ADDING_A_PLATFORM.md:103-111 @ 863e313`

```
### Optional methods (have default stubs in base)

| Method | Purpose |
|--------|---------|
| `send_document(chat_id, path, caption)` | Send a file attachment |
| `send_voice(chat_id, path)` | Send a voice message |
| `send_video(chat_id, path, caption)` | Send a video |
| `send_animation(chat_id, path, caption)` | Send a GIF/animation |
| `send_image_file(chat_id, path, caption)` | Send image from local file |
```

这个标题下**只有这五个媒体方法**,而它们在基类里**确实都有实现**:

`gateway/platforms/base.py:3991,4062,4205,4232,4305 @ 863e313`

```python
    async def send_animation(
    async def send_voice(
    async def send_video(
    async def send_document(
    async def send_image_file(
```

**所以该标题对它自己的表格是准确的。** 那三个交互方法在紧随其后的独立小节:

`gateway/platforms/ADDING_A_PLATFORM.md:113-115 @ 863e313`

```
### Interactive UX (recommended if your platform supports tappable buttons)

If your platform supports interactive button/menu messages, implement these for a more polished agent experience. They all degrade gracefully to plain text when not overridden:
```

该小节的**唯一行为承诺**是 "degrade gracefully to plain text when not overridden"——
而 r7b 自己也确认优雅降级真实存在(调用点类型探测)。**文档没有承诺基类桩,
所以"照文档写会 super() 得 AttributeError"这条因果链没有文档侧依据。**

**为什么是阻断**:▲ 的定义是"文档所述与代码矛盾"。这里文档没这么说,矛盾不存在,
这条 ▲ 立不住;而它被计入 r7b"本轮定案 24 条(▲ 7 / ◇ 17)",**污染跨轮 ▲ 计数**,
更会让后续轮次以为这份文档在此处有个待修的 bug。

**建议改法**:撤销该 ▲,或降格改写为——"同一份文档用两个相邻小节表达了**两种不同**的降级机制
(基类桩 vs 调用点类型探测),却从未说明后者;实现者无法从文档得知这三个方法没有基类桩"。
改写后文档锚点必须换成 `:113`/`:115`,不能再挂在 `:103` 上。

---

#### 【阻断-5】r6 说 hooks 声明"三家都与实现不符",实测点名的三家里两家是**相符**的

**被评审位置**:`chapters/r6-memory-provider-ecosystem.md:321-323@38b65bb`;同源
`notes/r6-90-doc-conflict-rulings.md:126-127@38b65bb`

**被质疑原文**(逐字,章):

> **plugin.yaml 声明的 `hooks: [on_session_end]` 类未实现**——而且全仓没有任何代码消费
> plugin.yaml 的 `hooks` 键(加载器只读 description),这个惰性元数据在
> **hindsight、byterover、openviking 三家都与实现不符,是系统性风险**。

**为什么不成立**:基线里声明 `hooks:` 的 memory 插件共 **5 家**,其中 **4 家实现了自己声明的钩子**,
只有 hindsight 一家没实现。被点名的另两家恰好都是**相符**的:

`plugins/memory/byterover/plugin.yaml:8-9 @ 863e313`

```yaml
hooks:
  - on_pre_compress
```

`plugins/memory/byterover/__init__.py:345 @ 863e313`

```python
    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
```

`plugins/memory/openviking/plugin.yaml:7-8 @ 863e313`

```yaml
hooks:
  - on_session_end
```

`plugins/memory/openviking/__init__.py:4599 @ 863e313`

```python
    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
```

评审位对五家逐一实测(`grep -n "def on_" plugins/memory/<name>/__init__.py`):

| provider | plugin.yaml 声明 | 实现 | 相符? |
|---|---|---|---|
| byterover | `on_pre_compress` | `:345 def on_pre_compress` | ✅ |
| openviking | `on_session_end` | `:4599 def on_session_end` | ✅ |
| holographic | `on_session_end` | `:235 def on_session_end` | ✅ |
| honcho | `on_session_end` | `:1386 def on_session_end` | ✅ |
| **hindsight** | `on_session_end` | 只有 `:2040 def on_session_switch` | **❌** |

**危害**:这是 r6 §5 小结里的"元规律",而元规律的作用就是被后续轮次当既有结论引用。
把 **1/5** 写成"三家都不符、是系统性风险",会让下一轮带着一个放大了三倍的风险判断开工——
而 CLAUDE.md 的移交项制度正是为了防止这类失真传递。

**建议改法**:改为"5 家声明 hooks 的插件里,hindsight 一家声明了 `on_session_end` 而未实现";
从名单里移除 byterover 与 openviking;并把"系统性风险"的定性替换为建议-13 给出的**真正**的系统性问题。

---

#### 【阻断-6】r4 把 `container_persistent` 和 `persist_across_processes` 当成同一个开关,于是给出的"什么条件下文档才成立"是错的

**被评审位置**:`chapters/r4-execution-environments.md:309@38b65bb`;同源
`notes/r4-90-doc-conflict-rulings.md:17,22-23@38b65bb`

**被质疑原文**(逐字,章):

> 以代码为准:**默认跨进程持久,关机不删**;**:88 那句只在把开关关掉时才成立。**

底稿把这层等式写得更明白(`notes/r4-90:22-23@38b65bb`):

> 真相是:**该 flag(代码里的 `persist_across_processes`)** 默认为 True

**为什么不成立**:`container_persistent` 与 `docker_persist_across_processes` 是**两个不同的配置键**,
落到**两个不同的属性**上,管**两件不同的事**。

`tools/terminal_tool.py:1628 @ 863e313`

```python
    persistent = cc.get("container_persistent", True)
```

`tools/terminal_tool.py:1649 @ 863e313`

```python
            persistent_filesystem=persistent, task_id=task_id,
```

`tools/terminal_tool.py:1658 @ 863e313`

```python
            persist_across_processes=cc.get("docker_persist_across_processes", True),
```

两者在 Docker 后端里分道扬镳:

`tools/environments/docker.py:877-878 @ 863e313`

```python
        self._persistent = persistent_filesystem
        self._persist_across_processes = persist_across_processes
```

**而"关机要不要 stop+rm"这个决定只看后者**——评审位读全了清理函数的三态分支:

`tools/environments/docker.py:1958-1969 @ 863e313`

```python
        if force_remove:
            should_stop = True
            should_remove = True
        elif self._persist_across_processes:
            # No-op for the container. Drop the in-process handle so a fresh
            # __init__ will re-probe via labels (and find the running
            # container) instead of trying to reuse a stale Python reference.
            self._container_id = None
            return
        else:
            should_stop = True
            should_remove = True
```

`self._persistent` 在整个清理路径里**只**用来决定是否删 bind-mount 目录,而且还被 `should_remove` 前置:

`tools/environments/docker.py:2011 @ 863e313`

```python
        if should_remove and not self._persistent:
```

**结论**:把 `container_persistent` 设成 `false` **不会**让 ":88 关机即删" 成立——
`_persist_across_processes` 默认仍为 True,清理照样在 `:1966` 提前 return,容器继续跑。
要让 :88 成立,得动**另一个**键 `docker_persist_across_processes: false`,或走 `force_remove=True`。

**为什么是阻断**:定案的**主结论正确**("默认跨进程持久,关机不删"),错的是"**在什么条件下文档才对**"——
而这恰恰是一条读者会照着去操作的信息:一个想要"退出即清理"的运维者,按 r4 的说法去关
`container_persistent`,得到的是"容器还在,只是 bind-mount 目录被删了",**比不动更糟**。
另外 r4 同章 `:295@38b65bb` 用的是**正确**的符号(`persist_across_processes`),
说明这是 §3.7 末尾定案段落的单点混淆,不是全章误解。

**建议改法**:`:309` 改为"要让 :88 成立需设 `terminal.docker_persist_across_processes: false`;
`container_persistent` 管的是另一件事(`/workspace` 与 `/root` 的 bind-mount 目录是否保留),
关掉它不会让容器被删";底稿 `:17,22-23` 同改,并删掉"该 flag(代码里的 `persist_across_processes`)"这个等式。

---

### 4.2 建议(16 条)

---

#### 【建议-1】30% 的成品章引用不写目录,39 处在基线里真的有歧义;且各章自定的溯源约定被自己违反

**被评审位置**:`chapters/r4-*.md`、`r5-*.md`、`r6-*.md`、`r7-*.md`、`r7b-*.md`、`r8b-*.md`(逐处见下表)

各章章首都写着同一条约定,例如 `chapters/r4-execution-environments.md:8@38b65bb`:

> **溯源约定**:`路径:行号 @ 863e313` 指基线 commit `863e31318` 下 hermes-agent 仓库根的
> **相对路径**与行号,可逐条复核。

评审位对 11 章全部 326 处引用做了机器统计(判据:引用里不含 `/`,且该文件名在基线仓库根不存在):

| 章 | 引用总数 | 无目录且根下不存在 | 其中基线同名文件 >1 个(**真歧义**) |
|---|---:|---:|---:|
| r4 | 35 | **33** | 13(`base.py`×7→9 个候选、`tools.md`×3→2、`permissions.py`→2、`browser.md`→2、`browser-supervisor.md`→2) |
| r7 | 34 | 25 | 7(`session.py`×6→3 个候选、`config.py`→4) |
| r5 | 23 | 18 | 2(`memory_manager.py`×2→2 个候选) |
| r6 | 13 | 11 | 8(`__init__.py`×5→**171 个候选**、`memory_manager.py`×2→2、`client.py`→4) |
| r7b | 45 | 8 | 8(`base.py`×8→9 个候选) |
| r8b | 35 | 1 | 1(`server.py`→4 个候选) |
| r2 | 23 | 3 | 0 |
| **r3 / r7c / r8a / r1** | 15/11/90/2 | **0** | **0** |
| 合计 | 326 | **99(30.4%)** | **39** |

**基线证据(取最严重两例)**:

r4 全章七处写 `base.py`,基线里叫 `base.py` 的文件有 9 个
(`gateway/platforms/`、`providers/`、`agent/secret_sources/`、`agent/transports/`、
`hermes_cli/dashboard_auth/`、`hermes_cli/proxy/adapters/`、`tools/environments/`、
以及两个 skills 目录下的)。评审位据代码内容判定 r4 指的是 `tools/environments/base.py`:

`tools/environments/base.py:871-872 @ 863e313`

```python
            f"printf '\\n{self._cwd_marker}%s{self._cwd_marker}\\n' \"$(pwd -P)\""
        )
```

r6 五处写 `__init__.py`(如 `honcho __init__.py:686-704`)。基线里 `__init__.py` 有 **171 个**。
所幸 r6 的写法带了 provider 名前缀,人可以还原为 `plugins/memory/honcho/__init__.py`——
评审位实测该文件 1,550 行,`:686-704` 的内容确与 r6 §3.4 的断言吻合
(`base_wait = min(base_wait, max(0.0, request_timeout))`,即"预算与请求超时取 min")。
**内容是对的,只是路径不合自己定的约定。**

**为什么值得动**:成品章要构成 R12《设计蓝图》正文,面向的正是那个"不看源码"的读者。
`base.py:781-875` 对他不是引用,是谜题。而 r3/r7c/r8a 三章 0 处违反,证明这不是工作量问题。

---

#### 【建议-2】`@ 863e313` 标记在四章里近乎缺席(r5、r6 为 0)

**被评审位置**:同上四章

CLAUDE.md 的证据格式硬要求是"紧跟 `路径:行号 @ 863e313`"。评审位机器统计
(判据:引用后 16 字符内出现 `863e313`):

| 章 | 带 SHA / 引用总数 | 占比 |
|---|---:|---:|
| r7c | 11/11 | **100%** |
| r7b | 36/45 | 80% |
| r2 | 18/23 | 78% |
| r8a | 63/90 | 70% |
| r3 | 10/15 | 67% |
| r8b | 23/35 | 66% |
| r7 | 5/34 | 15% |
| **r4** | **1/35** | **3%** |
| **r5** | **0/23** | **0%** |
| **r6** | **0/13** | **0%** |

r5、r6 的写法是 `(hermes_state.py:743-767)`、`(memory_manager.py:347-361)` 这类纯括号形式,
既无目录也无 SHA。**基线全局钉死,所以这不影响引用的实际有效性**——因此定为建议而非阻断。
但它与建议-1 叠加后,r5/r6 的引用变成"既不知道在哪个目录、也没声明基于哪个 commit"。

---

#### 【建议-3】成品章整体过不了产出方自己的定稿关卡(退出码 1),两处原因都不是"引用引错了"

**被评审位置**:`chapters/r4-execution-environments.md:112@38b65bb`、`chapters/r7b-platform-integration.md:471@38b65bb`

CLAUDE.md(R8A 起)把 `verify_citations.py` 升格为"与台账校验并列的定稿关卡",
要求"跑到退出码 0"。评审位在被评审 commit 上对**全部 11 章**跑:

```
[MISSING-FILE] r4-execution-environments.md:112  base.py
[MISMATCH] r7b-platform-integration.md:471  gateway/platforms/base.py:1451 -> not found within +/-40
      cited: 1. 清洗引号/尾标点
      found: def validate_media_delivery_path(path: str) -> Optional[str]:

citations=309  MISMATCH=1  MISSING-FILE=1  OK=97  UNCHECKED=210
FAIL: 2 citation(s) need fixing
```

两处成因不同,分开处置:

- **r4:112** 是建议-1 的一个实例(裸 `base.py`),脚本无法解析路径。**真实位置已在建议-1 给出**
  (`tools/environments/base.py:871-872`),内容正确。
- **r7b:471** 是**假阳性,但责任在写法**。该处引用后紧跟的围栏块不是源码,而是中文散文判定顺序表:

  `chapters/r7b-platform-integration.md:473-482@38b65bb`

  ```
  1. 清洗引号/尾标点
  2. 展开 ~;非绝对路径 → 拒
  3. resolve(strict=True)   ← 符号链接在此解析,早于一切检查
  ```

  脚本按设计把"引用后的第一个围栏块"当源码比对(见 `scripts/verify_citations.py:15-20` 的说明),
  于是必然失配。评审位已在基线核实 r7b 的**判定顺序本身正确**
  (`gateway/platforms/base.py:1451` 起确为 `validate_media_delivery_path`,
  且第 3 步 `resolve(strict=True)` 确在一切包含性检查之前),**所以这不是解读错误。**

**建议改法**:把这类散文清单改成非围栏形式(缩进列表或引用块),或把引用挪到清单之后。
**更重要的是把"全章集跑一次"纳入每轮流程**——目前的规定是"对本轮全部 notes/ 与 chapters/"跑,
于是 r4:112 从 R4 起一直没人跑到过。

---

#### 【建议-4】R1 附卷两处引用真有 1 行漂移,而脚本的报错指向了同一行里的**另一个**引用,所以一直没人修

**被评审位置**:`reports/round-1-capabilities-full.md:342@38b65bb`、`:826@38b65bb`

脚本报的是:

```
[MISMATCH] round-1-capabilities-full.md:342  agent/model_metadata.py:1518 -> not found within +/-40
[MISMATCH] round-1-capabilities-full.md:826  tools/budget_config.py:11 -> not found within +/-40
```

评审位查证结论:**报错点名的引用是无辜的,真正漂了的是同一行的第一个引用。**

第 342 行的证据行是三个引用并列:

`reports/round-1-capabilities-full.md:342@38b65bb`

> - **证据**:`agent/models_dev.py:11` · `agent/model_metadata.py:1518`

围栏块的内容属于**第一个**引用,而它差 1 行:

`agent/models_dev.py:11-13 @ 863e313`

```
Data resolution order:
  1. In-memory cache (fresh, or stale served immediately while a single
     background daemon thread refreshes)
```

引的是 `:11`(`Data resolution order:`),块首行实际在 **`:12`**。

第 826 行同理,证据行是 `tools/tool_result_storage.py:172-178` · `tools/tool_result_storage.py:114-116` ·
`tools/budget_config.py:11-13`,围栏块属于第一个,而它也差 1 行:

`tools/tool_result_storage.py:171-175 @ 863e313`

```python
    if effective_threshold == float("inf"):
        return content

    if len(content) <= effective_threshold:
        return content
```

引的是 `:172-178`,块首行实际在 **`:171`**,块长 5 行(171-175)。

**根因不在作者,在诊断信息**。脚本的多引用处理是"逐个试,谁匹配算谁"、都不匹配则回落到**最后一个**
(`scripts/verify_citations.py:141-145`):

```python
        # A prose line may carry several citations (the call site AND the callee).
        # The block belongs to whichever one it actually matches.
        elif len(cands) > 1:
            m = next((c for c in cands if matches(c)), m)
```

逻辑本身是对的,但**回落之后的报错文本只印那个回落对象**,于是维护者看到的是
"`tools/budget_config.py:11` 找不到",而那个引用根本没错。这类失配在 R1 附卷里占比极高——
评审位统计该文件 185 个"带围栏块的引用行"中有 **180 行(97.3%)** 是多引用行,
notes/ 只有 87/5329(1.6%),chapters/ 为 0。**误导性报错集中在一个文件里,正好是最早、最少人回看的那份。**

**建议改法**:(a) 修这两处行号(`:11`→`:12`;`:172-178`→`:171-175`);
(b) 给脚本的 MISMATCH 报错加一句"本行有 N 处引用,以下为回落对象",一行代码,能省掉下一个人重做这段查证。

---

#### 【建议-5】r7c 的 `busy_policy` 三个数加起来是 95,而同节自报注册表共 94 条

**被评审位置**:`chapters/r7c-gateway-periphery-and-scheduling.md:167-169@38b65bb`

**被质疑原文**(逐字):

> `busy_policy` 只有三个取值,却是整个控制面的核心:`reject`(69 条,忙时直接拒绝)、
> `dispatch`(23 条,忙时也照跑)、`interrupt_then_dispatch`(**只有 3 条**:
> `/new`、`/reset`、`/stop`)。

**为什么不精确**:前两个数是**注册表条目数**,第三个是**可敲命令名数**,单位不同。
评审位用 AST 直读注册表(不 import、不执行)复算:

```
entries: 94
busy_policy: {'dispatch': 23, 'interrupt_then_dispatch': 2, '<default>': 66, 'reject': 3}
默认 busy_policy = 'reject'   → reject 实为 66+3 = 69 ✓
```

`interrupt_then_dispatch` 落在 **2 条**注册表条目上,`/reset` 是 `new` 的别名:

`hermes_cli/commands.py:106-108 @ 863e313`

```python
    CommandDef("new", "Start a new session (fresh session ID + history)", "Session",
               aliases=("reset",), args_hint="[name]",
               busy_policy="interrupt_then_dispatch", busy_handler="new"),
```

`hermes_cli/commands.py:140-141 @ 863e313`

```python
    CommandDef("stop", "Kill all running background processes", "Session",
               busy_policy="interrupt_then_dispatch", busy_handler="stop"),
```

69 + 23 + 2 = 94 ✓。**机制结论完全正确**(能打断的确实只有 `/new`、`/reset`、`/stop` 三个名字),
只是三个数不能并列相加。

**建议改法**:"`interrupt_then_dispatch`(2 条注册项,对应三个可敲名:`/new`、别名 `/reset`、`/stop`)"。

---

#### 【建议-6】r7 的 "17 个 ContextVar" 实为 18,且该误数从底稿原样传进了成品章

**被评审位置**:`chapters/r7-gateway-session-core.md:145@38b65bb`;同源:`notes/r7-20-identity-state-lease.md:28@38b65bb`

**被质疑原文**(逐字):

> **身份**:`gateway/session_context.py` 用 17 个 `ContextVar`(Python 的任务局部变量,
> asyncio 每个任务一份)承载会话身份

**基线证据**:`grep -c "ContextVar(" gateway/session_context.py` = **18**,逐个列出为
`session_context.py:74-82`(10 个)、`:90`、`:94`、`:96`、`:102`、`:122`、`:126-128`(3 个):

`gateway/session_context.py:126-128 @ 863e313`

```python
_CRON_AUTO_DELIVER_PLATFORM: ContextVar = ContextVar("HERMES_CRON_AUTO_DELIVER_PLATFORM", default=_UNSET)
_CRON_AUTO_DELIVER_CHAT_ID: ContextVar = ContextVar("HERMES_CRON_AUTO_DELIVER_CHAT_ID", default=_UNSET)
_CRON_AUTO_DELIVER_THREAD_ID: ContextVar = ContextVar("HERMES_CRON_AUTO_DELIVER_THREAD_ID", default=_UNSET)
```

**值得记的不是这个 1,是它的路径**:底稿 `notes/r7-20:28` 也写 17,并且引的是
`session_context.py:46,74-128`——**引用范围是对的,数是错的**。说明"底稿→成品章"这一步
没有重新数一遍。这正是双产出制度最容易漏的一格:成品章复核的是**引用是否还对**,
而不是**数字是否还对**。

**建议改法**:17→18;并考虑在流程里加一句——凡成品章出现可复算的计数,装订时重算一次。

---

#### 【建议-7】r7b 把四个各自正确的数字并成了一个不成立的等式

**被评审位置**:`chapters/r7b-platform-integration.md:18-19@38b65bb`

**被质疑原文**(逐字):

> 24 个平台枚举里只剩 9 个内建适配器,其余是 22 个插件 + 1 个能"一对多"的中继。

**四个数分别核,全对**:

- 枚举 24:`gateway/config.py:272` 的 `class Platform(Enum)`,AST 数出 24 个成员;
- 内建适配器 9:`gateway/platforms/` 下 `api_server / bluebubbles / msgraph_webhook / signal /
  webhook / weixin / whatsapp_cloud / yuanbao` 八个 `.py` + `qqbot/` 一个包;
- 插件平台 22:`plugins/platforms/` 下 22 个目录;
- 中继 1:`Platform.RELAY`。

**但它们不构成划分**。评审位把 24 个成员逐个归位:

```
LOCAL(非聊天平台) 1 + 内建 9 + RELAY 1 + 有枚举位的插件平台 13 = 24
```

也就是 24 − 9 = **15**,不是 22 + 1 = 23。反过来,22 个插件目录里有 **10 个**
(`a2a / buzz / google_chat / irc / line / ntfy / photon / raft / simplex / teams`)
**在枚举里没有成员**,走的是 `gateway/platform_registry.py` 的动态注册。

**危害**:一个想复述"hermes 到底支持多少平台、怎么分类"的读者,拿这句话拼不出一致的清单——
而这正是 TL;DR 第 2 条要给他的东西。

**建议改法**:拆成两句——"枚举 24 个成员:1 个本机、9 个内建适配器、1 个中继、13 个插件平台;
另有 9 个插件平台不占枚举位,走动态注册,故 `plugins/platforms/` 下共 22 个目录。"

---

#### 【建议-8】r3 的审批短路链漏了第三道无条件地板(sudo stdin guard)

**被评审位置**:`chapters/r3-tool-infrastructure.md:132-145@38b65bb`(流程图)、`:147@38b65bb`

r3 把链画成 `容器沙箱 → hardline → 用户 deny → 免确认模式 → 永久放行 → 人工审批`,
并在 `:147` 说"hardline 和用户 deny 规则,排在'免确认模式'之前"。

**顺序断言完全正确**,评审位在基线复核逐行吻合。但**两道地板之间还有第三道**,章节未提:

`tools/approval.py:3767-3775 @ 863e313`

```python
    # == Sudo stdin guard ==
    # Like the hardline floor above, this is unconditional: there is never a
    # legitimate reason for the agent to pipe passwords to sudo -S when no
    # SUDO_PASSWORD has been configured.  This must fire BEFORE the yolo
    # check so even yolo/smart approval/mode=off cannot bypass it.
    is_sudo_guess, sudo_guess_desc = _check_sudo_stdin_guard(command)
```

它自己的注释就写着"Like the hardline floor above, this is unconditional"。

**为什么值得补**:r3 §3.2 的论点就是"地板优先于开关",而地板恰好是**三**道不是两道;
`:150` 引用设计者原话讲 hardline 刻意保持很小(测试断言 ≤20 条,评审位已核
`tests/tools/test_hardline_blocklist.py:620`),那么"为什么 sudo 这一条没并进 hardline
而是单列一道"本身就是一个值得讲的取舍。

---

#### 【建议-9】跨章冲突:r8a 说 `config.yaml` 有五个读取函数,r8b 更正为六个,r8a 未回填也无前向指引

**被评审位置**:`chapters/r8a-configuration-surface.md:18@38b65bb`、`:1719@38b65bb`
vs `chapters/r8b-cli-trunk-and-interaction.md:550@38b65bb`

r8a 两处:

> 但**同一份 `config.yaml` 有五个读取函数**,其中两个是完整装载器 (`:18`)
> **◇ 五个 `config.yaml` 读取函数的存在本身,全站零文档。** (`:1719`)

r8b 一处:

> **◇-R8B-b** `config.yaml` 的读取函数应从上一轮的**五个**更正为**六个**;第六个是启动最早期的
> `_config_default_interface_early`(`hermes_cli/main.py:280`)。

**评审位判定 r8b 正确**,第六个读取函数确实存在且确实自己读 YAML:

`hermes_cli/main.py:280-296 @ 863e313`

```python
def _config_default_interface_early() -> str:
    """Return the configured default interface ("cli"/"tui") via a minimal
    YAML read. Best-effort: any error falls back to "cli" (legacy behavior)."""
    global _EARLY_INTERFACE_CACHE
```

**问题不在谁对,在于两章在同一个 commit 上给读者两个数**。CLAUDE.md 的第 6 条硬标准是
"独立可读:不翻底稿、不看源码即可读懂"——只读 r8a 的读者会带走"五个",而这是已被下一轮推翻的数。
R8B 把更正记在自己的报告与章里(做法正确),但没有任何机制把它推回 r8a。

**建议改法**:R12 装订前回填 r8a 两处,或在 r8a 该处加一条"(R8B 更正为六个,见 chapters/r8b §7)"
的就地注记——r7b:744-745 已经示范过这种就地注记的写法,可直接沿用。

---

#### 【建议-10】r2 把流式挂死/读超时的两个数写成普遍值,漏了配置覆盖与本地 provider 的 900 秒分支

**被评审位置**:`chapters/r2-turn-loop-and-model-access.md:180-181@38b65bb`

**被质疑原文**(逐字):

> 具体数字:**180 秒没有新内容就杀掉连接重连,读超时 120 秒**,连续 5 次因挂死被杀就触发熔断

**两个数确实是默认值**,评审位复核成立:

`agent/chat_completion_helpers.py:4063 @ 863e313`

```python
        _stream_stale_timeout_base = env_float("HERMES_STREAM_STALE_TIMEOUT", 180.0)
```

`agent/chat_completion_helpers.py:3028 @ 863e313`

```python
            _stream_read_timeout = env_float("HERMES_STREAM_READ_TIMEOUT", 120.0)
```

**但两条都不是无条件的**,而 r2 的句式("具体数字")读起来像无条件:

`agent/chat_completion_helpers.py:4058-4061 @ 863e313`

```python
    # Provider-configured stale timeout takes priority over env default.
    _cfg_stale = get_provider_stale_timeout(agent.provider, agent.model)
    if _cfg_stale is not None:
        _stream_stale_timeout_base = _cfg_stale
```

紧随其后的注释还给出第三档:本地 provider(Ollama / oMLX / llama-cpp)容忍 **900 秒**静默,
理由是大上下文 prefill 可能 300+ 秒。读超时侧同样有 `is_local_endpoint(agent.base_url)`
分支把 120 秒抬到 `_base_timeout`。

**为什么值得改**:r2 §3.3 紧接着就用"注释写 90/60、实际 180/120"这个插曲论证"要给每个数字配行号、
逼自己去核对"——**在这个论证里给出一个漏了两档覆盖的数,是同一类型的失准**。
r2 后文列了"只有四种情况退回非流式",说明作者习惯交代分支,这里应属遗漏而非取舍。

**建议改法**:改为"云端 provider 默认 180 / 120 秒(provider 配置可覆盖;本地端点自动放宽到 900 秒)"。

---

#### 【建议-11】报告首句"≤20 字"的计数口径未声明,三份新报告按任一口径都超,一份附卷无结论句

**被评审位置**:`reports/round-7c-*.md`、`reports/round-8a-*.md`、`reports/round-8b-*.md`、
`reports/round-1-capabilities-full.md`(各文件首句)

CLAUDE.md:"第一句 ≤20 字结论"。评审位机器统计各报告首句(剥去 Markdown 标记):

| 报告 | 含"一句话结论:"前缀 | 剥去前缀后 |
|---|---:|---:|
| round-2 / 3 / 4 / 5 / 6 | 17-19 | 11-13 ✓ |
| round-7 | 24 | 17 ✓ |
| round-7b | 21 | 15 ✓ |
| **round-7c** | 26 | **21** ✗ |
| **round-8a** | 26 | **21** ✗ |
| **round-8b** | 26 | **23** ✗ |
| round-1-survey | 29 | 23 ✗ |
| **round-1-capabilities-full** | — | **无结论句**(首行为"主卷:reports/round-1-survey.md") |

这是本报告里最轻的一条,单列的理由只有一个:**规则本身没定计数口径**
("一句话结论:"这六个字算不算),于是它无法被脚本判定,只能靠人看——
而这正是 R8A 把引用校验升格为脚本关卡时给出的理由。

**建议改法**:要么在 CLAUDE.md 里写明"不含前缀标签、以第一个句号为界",顺手加进
`verify_ledger.py` 或一个新的三行脚本;要么承认它是软约定并从"硬要求"里移出去。
附卷是否豁免(它是主卷的数据附件,本身不承载结论)也请一并定。

---

#### 【建议-12】"加载器只读 description"不成立;清单 schema 里有钩子字段,真正的教训比原诊断更好

**被评审位置**:`chapters/r6-memory-provider-ecosystem.md:322@38b65bb`;同源
`notes/r6-90-doc-conflict-rulings.md:45@38b65bb`

**被质疑原文**(逐字):

> 全仓没有任何代码消费 plugin.yaml 的 `hooks` 键(**加载器只读 description**)

**为什么不成立**:清单解析器一次读 **8 个**字段,其中就有一个钩子字段:

`hermes_cli/plugins.py:1657-1668 @ 863e313`

```python
            return PluginManifest(
                name=name,
                version=str(data.get("version", "")),
                description=data.get("description", ""),
                author=data.get("author", ""),
                requires_env=data.get("requires_env", []),
                provides_tools=data.get("provides_tools", []),
                provides_hooks=data.get("provides_hooks", []),
                source=source,
```

`hermes_cli/plugins.py:293 @ 863e313`

```python
    provides_hooks: List[str] = field(default_factory=list)
```

**于是真实诊断变了,而且变得更有价值**:schema 里的钩子字段叫 `provides_hooks`,
而五家插件写的都是 `hooks:`——**一个非 schema 键,被解析器静默丢弃**。
评审位另测:`grep -rn "provides_hooks" plugins/` **零命中**,即 bundled 插件**无一使用正确键名**。

**两种诊断给后续轮次的启示完全相反**:
- 原诊断("声明性元数据无消费者")指向 **分发机制缺失** → 后续会去找"该由谁来消费 hooks";
- 真实情况("清单 schema 有字段,但所有人都拼错了键名,且拼错不报错")指向
  **清单缺 schema 校验** → 后续该做的是给 manifest 加未知键告警。

**这才是 r6 想要的那个"系统性风险"**(接阻断-5):不是"三家声明与实现不符",
而是"schema 键名写错零反馈,于是五家全部写错、四家的钩子实现白写了"。

**建议改法**:删掉"加载器只读 description";改述为——钩子字段是 `provides_hooks`
(`hermes_cli/plugins.py:293,1664`),五家插件写的 `hooks:` 属非 schema 键被静默丢弃,
全仓 bundled 插件无一使用 `provides_hooks`。

---

#### 【建议-13】r7 把一句字面为真的文档记成"硬伤/证伪",污染 ▲ 计数

**被评审位置**:`chapters/r7-gateway-session-core.md:325@38b65bb`;同源
`notes/r7-90-doc-conflict-rulings.md:50,57@38b65bb`

r7 §5 开头说 `gateway-internals.md` "四处硬伤**全部证伪**",第四处是:

> "20+ 平台"显著低估(枚举 24 显式成员 + 22 插件平台)

**括号里的数评审位复核全对**(枚举 24 见 `gateway/config.py:272` 的 `class Platform(Enum)`,
插件目录 22 见 `ls plugins/platforms/`)。**但文档那句话是真的**:

`website/docs/developer-guide/gateway-internals.md:9 @ 863e313`

```
The messaging gateway is the long-running process that connects Hermes to 20+ external messaging platforms through a unified architecture.
```

24 ≥ 20,"20+" 成立。底稿 `notes/r7-90:57@38b65bb` 自己也写了 "'20+'字面不算错",
却仍裁为"证伪"并计入 ▲。

**为什么值得单列**:▲ 在本项目里的定义是"文档所述与代码矛盾"。
把一个**保守但为真**的表述计入 ▲,会让"▲ 条数"这个贯穿 R2-R8B 的跨轮指标不可比——
r7 报"四处硬伤",实为三处;而 ▲ 计数正是各轮报告用来衡量"地图腐烂程度"的主要数字。

**建议改法**:新增一个记号(如 ◎ 保守表述)或归入 ◇,裁决改为
"文档成立但显著保守:24 枚举成员 + 22 插件目录";并把 r7 的"四处硬伤"改为三处。

---

#### 【建议-14】"围栏格式碰撞"是三处校验失败的共同成因,不是三个独立错误

**被评审位置**:`chapters/r7b-platform-integration.md:471@38b65bb`(见建议-3)、
`notes/r3-90-doc-conflict-rulings.md:30-34@38b65bb`

`verify_citations.py` 的契约是"引用后紧跟的第一个围栏块 = 源码摘录"
(`scripts/verify_citations.py:14-19`)。于是任何**放在引用后的非源码围栏块**都会被判失配。
本轮在三处踩到同一个坑,成因完全一致:

| 位置 | 围栏块里装的是 | 引用本身 |
|---|---|---|
| `chapters/r7b-*.md:473-482` | 中文散文判定顺序清单 | `gateway/platforms/base.py:1451-1527` **正确** |
| `notes/r3-90-*.md:31-34` | **shell 会话记录**(`grep ... → 空`) | `tools/approval.py:520` **正确** |
| `reports/round-1-capabilities-full.md:342/826` | 源码,但行号差 1(见建议-4) | 前置引用漂移 1 行 |

第二处评审位独立复核:引用完全正确,`tools/approval.py:520` 确为
`def detect_hardline_command(command: str) -> tuple:`;围栏块里的
`grep UNRECOVERABLE_BLOCKLIST tools/ agent/ model_tools.py → 空` 这个**断言也成立**
(全仓该符号只在 `website/docs/user-guide/security.md:101` 与其 zh-Hans 镜像 `:87` 出现,零 `.py` 命中)。
**所以这是一条完全正确的定案,却让整个 rulings 集永久卡在退出码 1 上。**

**为什么并成一条报**:分开看是三个"格式小问题",合起来是**一条制度性障碍**——
R8A 把这个脚本升格成"跑到退出码 0 才算过关"的定稿关卡,而当前 chapters 与 rulings **两个集合都过不了**,
且**没有一处是引用引错了内容**。关卡长期红着,它的信号价值就归零了。

**建议改法**(任一即可,推荐第一个):
1. 给脚本加一条豁免——围栏块首行若不出现在被引文件的 ±WINDOW 窗口内、**且**该块看起来不是源码
   (例如以 `$`、`>`、中文字符开头),记 UNCHECKED 而非 MISMATCH;
2. 或约定:非源码块一律不紧跟引用(改用缩进列表/引用块),并把这条写进 CLAUDE.md 的证据格式。

---

#### 【建议-15】文档侧引用锚点是校验脚本的盲区,本轮抽查即撞到 5 处漂移

**被评审位置**:`notes/r3-90-doc-conflict-rulings.md:13@38b65bb`、
`notes/r5-90-doc-conflict-rulings.md:87@38b65bb`、
`notes/r7b-90-doc-conflict-rulings.md:89,94@38b65bb`、
`notes/r4-90-doc-conflict-rulings.md:99-104@38b65bb`

`verify_citations.py` 只校验**紧跟围栏块**的引用。而"文档-代码冲突定案"的文档侧几乎总是写成
`> blockquote`(引用块),**从不进围栏**,于是**整个文档侧锚点集合从未被任何自动校验覆盖过**。
本轮定向抽查即撞到 5 处行号漂移(每处评审位都用 `grep -n` 定位了真实行):

| 定案位置 | 引的锚点 | 真实位置 | 该锚点上实际是什么 |
|---|---|---|---|
| `notes/r3-90:13` | `tools-runtime.md:96` | **:91** | :96 是下一节的无关散文("Toolsets are named bundles of tools…") |
| `notes/r5-90:87` | `prompt-assembly.md:31,39` | :31 对,**:39→:38** | :39 是相邻那条讲 memory/profile 属 volatile 的,并非被质疑对象 |
| `notes/r7b-90:89` | `ADDING_A_PLATFORM.md:135` | **:125** | :135 是空行 |
| `notes/r7b-90:94` | `ADDING_A_PLATFORM.md:66-70` | **:55-61** | :66-69 已是"mixin 必须排在基类前"的说明 |
| `notes/r4-90:99-104` | `tool.py:1330`、`cua_backend.py:2050-2053`、`:29-33` | :1333、:2058、:13-14 | :1330 在 docstring 里;:2050-2053 是另一个方法的 `finally:` 拆卸段 |

**每一处的结论都成立**——评审位复核了全部五条的实质断言,无一被推翻。
问题纯粹是锚点:**一个照锚点去复核的读者会落在无关文字上,然后合理地怀疑整条定案。**
而这正是本项目把引用校验升格为关卡时想消灭的那种失败。

**加重一层**:`notes/r3-90:13` 那个错锚点已经**被两份 R1 报告继承**
(`reports/round-1-survey.md:599`、`reports/round-1-capabilities-full.md:939`),
只改 rulings 一处会留下两份陈旧副本——这正是 r8a/r8b 反复讲的"同一语义多份实现"形状,
出现在了本项目自己的产出上。

**建议改法**:把 `verify_citations.py` 的适用面从"紧跟围栏块的引用"扩到"紧跟围栏块**或引用块**的引用",
文档侧照样能逐字比对(文档也在基线里,`resolve()` 已经能解析 `.md`);
或者约定文档侧摘录也用围栏。**这是本轮性价比最高的一条工程改动**:它一次性覆盖了
本报告 §6.3 第 2 条申报的最大缺口。

---

#### 【建议-16】r4-90 写在定案里的自检 grep 命令,重跑不出它声称的结果

**被评审位置**:`notes/r4-90-doc-conflict-rulings.md:120-121@38b65bb`

**被质疑原文**(逐字):

> 对本簇 7 个远端/其他后端文件 grep `iron|egress|HTTPS_PROXY` **零命中**

**为什么不成立**:`iron` 是 `env`**`iron`**`ment` 的子串,所以这条命令对**每一个**后端文件都命中。
评审位实测:

```
$ for f in tools/environments/*.py; do printf "%s %s\n" "$(grep -icE 'iron|egress|HTTPS_PROXY' $f)" "$f"; done
5 tools/environments/daytona.py
4 tools/environments/ssh.py
6 tools/environments/singularity.py
5 tools/environments/modal.py
4 tools/environments/managed_modal.py
7 tools/environments/vercel_sandbox.py
```

命中全部来自 `BaseEnvironment` / 模块 docstring 里的 "Environment" 一词。

**结论本身是对的**——评审位换成词界模式复核,r4 的判断成立:

```
$ grep -rnE "iron[-_]proxy|IRON_|\begress\b|HTTPS_PROXY" tools/environments/*.py | grep -v docker.py
(空)
```

且 Docker 独占接线确认于 `tools/environments/docker.py:393` 的
`def _egress_proxy_args_for_docker() -> tuple[list[str], dict[str, str], list[str]]:`。

**为什么值得改**:CLAUDE.md 的证据标准是"**使读报告本身即完成验证**"。
一条抄进底稿的命令,如果重跑给出的结果与结论相反,读者要么以为结论错了、要么以为自己环境不对——
**它比不写命令更糟**。这类"命令与结论不符"是脚本抓不到的(它只比对代码块与源码),
只能靠约定:**凡把 shell 命令写进证据,必须是重跑能复现该结论的那一条**。

**建议改法**:把命令换成上面那条词界版本;并考虑给这类"自检命令"约定一个标记
(如 ```` ```verify ```` 围栏),将来可以做成真正可跑的检查。

---

### 4.3 存疑(2 条,待仲裁)

---

#### 【存疑-1】r8a 的头条对照实验("105 个键零提及")建立在一个本章自己声明不可信的匹配器上

**被评审位置**:`chapters/r8a-configuration-surface.md:25-27@38b65bb`、`:1256-1259@38b65bb`
vs 同章 `:1266-1271@38b65bb`

r8a 的第一原则(章节自称"本轮最强的一条,而且有对照实验支撑")是:

| | 数量 | 全站零提及 |
|---|---|---|
| 配置键(`DEFAULT_CONFIG`) | 856 | **105** |
| 环境变量(`OPTIONAL_ENV_VARS`) | 151 | **0** |

**评审位能确认的部分**:两个数与产出方自己的资产逐字吻合。
`data/r8a-config-keys.tsv` 856 行(去表头),`docs` 列为空的正好 **105** 行;
`data/r8a-env-vars.tsv` 151 行,`docs` 列**无一行为空**。
并且评审位**独立**从基线 AST 复算了相关基数:`OPTIONAL_ENV_VARS` = 151、
`_EXTRA_ENV_KEYS` = 108、并集 239、重叠 20——与 `:1741-1742` 的申报完全一致。

**评审位不能确认的部分**:那 105 是不是真的"零提及"。它来自 `scripts/config_table.py` 的
文档匹配启发式,而**同一章在 12 行之后声明这个匹配器不可用于相邻指标**:

`chapters/r8a-configuration-surface.md:1266-1271@38b65bb`

> **顺带一条方法论的自我更正**:本轮原想给出一个"文档覆盖率百分比",最后**放弃了**。
> 按点分全路径(`display.show_cost`)匹配得到 **0.0%** ——因为文档写的是 YAML 块,
> 根本不用点分写法……按叶子名匹配得到 87.7% ——而 `enabled` / `timeout` 这类叶子名
> 在文档里到处都是,严重高估。**两个边界都不可用,所以本章不报覆盖率**

**为什么是存疑而不是建议**:这个自我克制是**优点**,评审位不打算把它读成缺陷。
但同一个匹配器,用来算百分比时被判为"两个边界都不可用",用来算"零提及"时被当作确定成立,
两者的可靠性论证并不对称——"零提及"仍然依赖"叶子名口径不会漏报"这个前提,
而按 `:1269` 自己的描述,叶子名口径的问题是**高估**覆盖(即**低估**零提及数),
方向上对结论有利,但没有给出边界。

**评审位没有独立重算这 105 条**(需要对 856 个键各做一次多口径文档检索,超出本轮预算),
因此不作判定,提交仲裁:是否要求给这个数补一句口径声明与误差方向,
或抽样 N 条人工复核后把结论改成"至少 N 个键零提及"。**不建议改动结论本身**——
"配置键靠注释、环境变量靠必填字段"这个机制解释,评审位认为独立成立。

---

#### 【存疑-2】r7 的返工范围:是"重排 §5 + 补三节场景",还是整章重写

**被评审位置**:`chapters/r7-gateway-session-core.md:319-335@38b65bb`(§5)、
`:236@38b65bb`(§3.6 起)、`:281@38b65bb`(§3.8 起)、`:291@38b65bb`(§3.9 起)

§3 的"每个机制以一次具体请求或一次具体故障的走法开场"是 CLAUDE.md 第 2 条硬标准。
评审位逐节点检 r7 §3 的九节:

| 节 | 开场 | 合标准 |
|---|---|---|
| 3.1 会话键 | **场景**:同一个人今天在 DM 里…… | ✓ |
| 3.2 contextvars/SessionState | **场景重演**(§1 的串线事故) | ✓ |
| 3.3 租约/run generation | **事故重讲**(#64934) | ✓ |
| 3.4 忙时策略 | **场景**:agent 正在跑一个几分钟的任务 | ✓ |
| 3.5 流式桥 | **场景**:模型在 agent 的工作线程里同步吐 token | ✓ |
| **3.6 看护面** | **原则先行**:判定"卡没卡"的钟只有一个 | **✗** |
| 3.7 带外注入 | **场景**:你让 agent 后台跑一个长任务 | ✓ |
| **3.8 agent 缓存** | 构建一个 `AIAgent`……很贵,网关按会话键缓存它 | **✗** |
| **3.9 多 profile** | 单实例可以同时跑多个 profile…… | **✗** |

§5(`:319-335`)是**一段 17 行不分段**的文字,内含约十条独立定案(示例会话键的 `private` 槽、
multiplex 命名空间、忙时守卫过时、DM 配对方向写反、"20+ 平台"低估、scale-to-zero 文档缺失、
`_TELEGRAM_NOISY_STATUS_RE`、profile_routing docstring、start() 返回值退化、memory_monitor 未接线、
两个 bug 候选),中间夹着括号引用和"识别谓词与模板集合脱耦的反例"这类高度压缩的表述。
对比 r7c §5(分四类、每类一个小标题)与 r8a §5(逐条 ▲-N 编号),同一体量的内容差异明显。

**评审位的判定是 §3 中三节 + §5 需要返工,不是整章重写**——r7 的内容质量与别章齐平,
memory_monitor 那条反转评审位已独立复核成立(基线 `grep -rn memory_monitor --include=*.py`
在非 tests 目录下只命中 `gateway/memory_monitor.py` 自身的定义行,无任何生产调用点),
r7 报的 `run.py` 27,146 行、`session_stall.py` 121 行、`stream_events.py` 171 行、
`stream_dispatch.py` 132 行、`stream_consumer.py` 2,410 行**五个行数逐一实测吻合**。

提交仲裁的原因是**成本归属**:按"读不下去"处理意味着 r7 要进返工队列,
而 R12 的定位是"只做装订与全局重构,不再从底稿从头合成"。
返工 r7 是修正卡的活还是 R12 的活,由仲裁定。评审位不代为决定。

---

## 5. 移交清单(交后续修正卡执行;评审位不改正文)

按"改动成本 / 影响面"排,同级按章序:

| # | 级别 | 锚点文件 + 行号 | 一句话现象 | 建议动作 |
|---|---|---|---|---|
| M-1 | 阻断 | `chapters/r7-gateway-session-core.md:36-37` | 写成"忙时消息不往下送",而 `base.py:5711-5713` 会先调网关装入的 `_busy_session_handler` | 改写该句 + 补锚点 |
| M-2 | 阻断 | `chapters/r1-what-is-hermes-agent.md:102-103` | L1/L2 两行(412/382,770、2,282/811,076)是 R1 快照,同 commit 实测为 511/479,923、2,183/713,923 | 表改为从 `data/ledger.tsv` 生成,或标注"截至 R1"并补当前值 |
| M-3 | 阻断 | `chapters/r1-what-is-hermes-agent.md:22`、`:109` | 连带两处仍写"约 38 万行"/"382,770" | 随 M-2 一并更新 |
| M-4 | 阻断 | `chapters/r1-what-is-hermes-agent.md:94` | 写"26 万行文本",同章 `:21` 与表格合计为 260 万 | 26 万 → 260 万 |
| M-4a | 阻断 | `chapters/r7b-platform-integration.md:714-718` + `notes/r7b-90-*.md:134,136-140` | ▲4 把三个交互方法挂在"有基类默认桩"标题下,而 `ADDING_A_PLATFORM.md:103` 那个标题下只有五个媒体方法(基类均有实现),交互方法在 `:113` 另一小节 | 撤销或降格改写,文档锚点换 `:113`/`:115` |
| M-4b | 阻断 | `chapters/r6-memory-provider-ecosystem.md:321-323` + `notes/r6-90-*.md:126-127` | 称 hooks 声明"三家都与实现不符",实测 5 家声明中 4 家相符,仅 hindsight 不符 | 改为"1/5(hindsight)";移除 byterover、openviking |
| M-4c | 阻断 | `chapters/r4-execution-environments.md:309` + `notes/r4-90-*.md:17,22-23` | 把 `container_persistent` 等同于 `persist_across_processes`,于是"关掉开关 :88 就成立"是错的——清理三态只看后者(`docker.py:1958-1969`) | 改为需设 `terminal.docker_persist_across_processes: false`;删掉两键等式 |
| M-5 | 建议 | `chapters/r4-*.md`(33 处)、`r7-*.md`(25)、`r5-*.md`(18)、`r6-*.md`(11)、`r7b-*.md`(8)、`r8b-*.md`(1) | 99 处引用不写目录,39 处在基线有同名歧义(`__init__.py` 171 个候选、`base.py` 9 个) | 批量补目录前缀;r4 的 `base.py` = `tools/environments/base.py` 已定位 |
| M-6 | 建议 | 同 M-5 四章 | `@ 863e313` 缺失(r5 0/23、r6 0/13、r4 1/35、r7 5/34) | 随 M-5 一并补 |
| M-7 | 建议 | `chapters/r7b-platform-integration.md:473-482` | 引用后的围栏块是中文散文判定表,使 `verify_citations.py` 对全章集必然 FAIL | 改用缩进列表/引用块,或把引用挪到清单后 |
| M-8 | 建议 | `reports/round-1-capabilities-full.md:342`、`:826` | 各有 1 行漂移(`models_dev.py:11`→`:12`;`tool_result_storage.py:172-178`→`:171-175`),脚本报错却点名同行的另一个引用 | 修两处行号;并给 `scripts/verify_citations.py` 的 MISMATCH 文本加"本行 N 处引用,以下为回落对象" |
| M-9 | 建议 | `chapters/r7c-*.md:167-169` | `reject 69 + dispatch 23 + interrupt_then_dispatch 3 = 95`,超出同节自报的 94;`/reset` 是 `new` 的别名 | 改为"2 条注册项 / 三个可敲名" |
| M-10 | 建议 | `chapters/r7-*.md:145` 与 `notes/r7-20-identity-state-lease.md:28` | "17 个 ContextVar",实测 18(`session_context.py:74-128`) | 两处同改 17→18 |
| M-11 | 建议 | `chapters/r7b-*.md:18-19` | 24/9/22/1 四数各自正确但不构成划分(24−9=15,且 10 个插件平台无枚举位) | 拆成两句陈述 |
| M-12 | 建议 | `chapters/r3-*.md:132-145`、`:147` | 审批短路链漏了第三道无条件地板 sudo stdin guard(`approval.py:3767-3775`) | 流程图与正文各补一格 |
| M-13 | 建议 | `chapters/r8a-*.md:18`、`:1719` | 说"五个读取函数",已被 `chapters/r8b-*.md:550` 更正为六个,r8a 未回填 | 回填,或按 r7b:744-745 的样式加就地注记 |
| M-14 | 建议 | `chapters/r2-*.md:180-181` | 180/120 秒写成普遍值,漏 provider 配置覆盖与本地端点 900 秒分支 | 加"云端默认 / 可覆盖 / 本地放宽"三档限定 |
| M-15 | 建议 | `CLAUDE.md` 验收标准"第一句 ≤20 字" | 计数口径未定义,r7c/r8a/r8b 三份按任一口径都超,附卷无结论句 | 定义口径并脚本化,或降为软约定;一并定附卷是否豁免 |
| M-16 | 建议 | 流程(非某文件) | "对本轮全部 chapters/ 跑引用校验"使 r4:112 自 R4 起从未被跑到 | 改为每轮对**全部** chapters/ 跑一次 |
| M-16a | 建议 | `scripts/verify_citations.py`(校验面) | 文档侧锚点从不被校验(只查紧跟围栏块的引用),抽查即撞 5 处漂移:`tools-runtime.md:96→91`、`prompt-assembly.md:39→38`、`ADDING_A_PLATFORM.md:135→125`、`:66-70→:55-61`、`cua_backend.py:2050-2053→:2058` | 把适用面扩到"引用块",或约定文档摘录也用围栏;**本轮性价比最高的一条** |
| M-16b | 建议 | `notes/r3-90-*.md:13` 及其两份继承 `reports/round-1-survey.md:599`、`reports/round-1-capabilities-full.md:939` | 同一个错锚点(`tools-runtime.md:96`)已被两份 R1 报告继承 | 三处同改为 `:91` |
| M-16c | 建议 | `notes/r3-90-*.md:31-34`、`chapters/r7b-*.md:473-482` | 引用后紧跟的围栏块装的是 shell 记录 / 中文清单,使脚本对两个集合永久 FAIL,而引用本身都正确 | 给脚本加非源码块豁免,或约定非源码块不紧跟引用 |
| M-16d | 建议 | `notes/r4-90-*.md:120-121` | 写进底稿的自检 grep 用 `iron` 匹配到 `environment`,重跑不出声称的"零命中"(结论仍成立) | 换成 `iron[-_]proxy\|IRON_\|\begress\b\|HTTPS_PROXY` |
| M-16e | 建议 | `chapters/r7-gateway-session-core.md:325` + `notes/r7-90-*.md:50,57` | 把 `gateway-internals.md:9` 的 "20+ platforms"(24≥20,字面为真)记成"硬伤/证伪",污染 ▲ 计数 | 改归 ◇ 或新增"保守表述"记号;"四处硬伤"改三处 |
| M-16f | 建议 | `chapters/r6-*.md:322` + `notes/r6-90-*.md:45` | "加载器只读 description" 不成立(解析器读 8 字段含 `provides_hooks`);真问题是五家插件都写了非 schema 键 `hooks:` 被静默丢弃 | 改述;这才是 r6 想要的那个"系统性风险" |
| M-17 | 存疑 | `chapters/r8a-*.md:25-27`、`:1256-1259` | "105 个键零提及"依赖的匹配器,被同章 `:1266-1271` 判为不可用于相邻指标 | 仲裁:补口径与误差方向声明,或抽样复核后改成"至少 N 个" |
| M-18 | 存疑 | `chapters/r7-*.md:319-335`、`:236`、`:281`、`:291` | §5 为 17 行不分段、含约十条定案;§3.6/3.8/3.9 无场景开场 | 仲裁:返工归修正卡还是归 R12 |

---

## 6. 抽样范围与未覆盖部分(如实申报)

### 6.1 已全量覆盖(非抽样)

- **11 个成品章全文读完**(6,288 行),逐章过六条硬标准,逐章给判定;
- **三道机器校验在被评审 commit 上全量重跑**:`verify_ledger.py`(通过)、
  `verify_citations.py` 分别跑 chapters(309 条引用,FAIL 2)、reports(647 条,FAIL 2)、
  10 份 rulings 卷(562 条,FAIL 5);
- **引用纪律全量统计**:11 章 326 处引用逐处判"是否可从仓库根解析""是否带 SHA",
  并对 chapters/reports/notes 全量统计多引用行占比(0% / 97.3% / 1.6%);
- **`data/ledger.tsv` 独立复算**(awk 重算五层文件数与行数,与脚本一致);
- **`data/r8a-config-keys.tsv`、`r8a-env-vars.tsv`、`r8a-extra-root-keys.tsv` 行数与 docs 列分布复算**;
- **12 份报告的首句长度**逐份机器统计;各轮报告的台账报数逐份对照(确认是逐轮快照、演进链自洽:
  412→436→446→461→511,与 `ledger.tsv` 现值 511 收口)。

### 6.2 抽样回源(评审位亲自到基线取证的 58 条断言)

**计数口径先声明,免得被误读**:下表只统计**评审位本人打开基线文件、亲自比对过**的断言。
一条断言只要被评审位复核过就计一次,**不论它最初是评审位自己挑中的、还是由第二条取证线
(定案卷两侧核实,见下)标出来的**——所以下表**不与**第二条线的数字相加,那会重复计数。

| 章 | 亲核数 | 成立 | 不精确 | 错 |
|---|---:|---:|---:|---:|
| r1 | 4 | 1 | 0 | 3(其中 2 条同源) |
| r2 | 3 | 2 | 1 | 0 |
| r3 | 4 | 3 | 1 | 0 |
| r4 | 5 | 4 | 0 | 1 |
| r5 | 2 | 2 | 0 | 0 |
| r6 | 5 | 3 | 0 | 2 |
| r7 | 9 | 6 | 1 | 2 |
| r7b | 7 | 5 | 1 | 1 |
| r7c | 6 | 5 | 1 | 0 |
| r8a | 10 | 10 | 0 | 0 |
| r8b | 3 | 3 | 0 | 0 |
| **合计** | **58** | **44** | **5** | **9** |

("错"9 条 → 阻断 6 条:r1 的 3 条合为阻断-2/3,r4 的 1 条为阻断-6,r6 的 2 条为阻断-5 与建议-12,
r7 的 2 条为阻断-1 与建议-6,r7b 的 1 条为阻断-4。"不精确"5 条 → 建议-5/7/8/10/13。)

**第二条取证线:定案卷两侧核实。** 口径不同——不是挑承重断言,而是**逐条**把定案引的
**代码**与引的**文档原文**都拉出来比对。覆盖 7 份定案卷、共 1,252 行(全读):

| 范围 | 逐条核实 | 该线判定成立 | 标出待查 | 经评审位亲核后立案 |
|---|---:|---:|---:|---:|
| `notes/r2-90` + `r3-90` + `r4-90` + `r5-90`(514 行) | 35 | 29 | 8 | 4 |
| `notes/r6-90` + `r7-90` + `r7b-90`(738 行) | 27 | 16 | 12 | 4 |
| **合计** | **62** | **45** | **20** | **8** |

**"标出待查 20 条、只立案 8 条"这个落差是有意的,请仲裁注意其含义**:
本报告的立案门槛是"评审位自己到基线取到证据",凡未亲核的一律不写进正文。
立案的 8 条 = 阻断-4/5/6 + 建议-12/13/14/15/16(建议-15 一条合并了 5 处锚点漂移),
它们已计入上面那张 58 条的表。
**其余 12 条未立案 ≠ 已澄清,而是本轮未复核**,应与 §6.3 的未覆盖项同等对待。

评审位亲测确认成立、值得记名的强断言(供仲裁抽验):
`_budget_grace_call` 全仓只被置 False(r1/r2);hardline 先于 yolo 且 `UNRECOVERABLE_BLOCKLIST`
只存在于文档(r3);七种后端工厂恰好七个 `env_type ==` 分支、iron-proxy 只接线
`tools/environments/docker.py`(r4);写重试三档 60/20/0.5 秒(r5);
`_EXTERNAL_PREFETCH_TIMEOUT_S = 8.0` 与 298 秒事故 docstring(r6);
memory_monitor 无生产调用点、五个模块行数(r7);`base.py` 6,861 行、`Platform` 枚举 24 成员(r7b);
94 条命令 / 61 条网关可用(r7c);注册表整张表五个数、151/108/239/20、`SUPPORT_FLOOR_VERSION=12`、
`_config_version=33`、v31 注释"new default is OFF" vs 默认仍 `"auto"`、`--all` 死开关、
18789 端口属 google_meet(r8a);`whoami` 在 `cli.py` 零命中、25/68/44/`['honcho']`/45(r8b)。

### 6.3 明确未覆盖(不声明就等于谎报覆盖率)

1. **`notes/` 底稿的内容正确性大部分未审**。全部 117,351 行里,本轮**只**深入了 7 份定案卷
   (`r2-90`/`r3-90`/`r4-90`/`r5-90`/`r6-90`/`r7-90`/`r7b-90`,共 1,252 行,§6.2 第二条线),
   且其中仍有大量条目被明确申报为未核(r2 的 11 行、r3 的 5 行含"7 项 MCP 客户端安全机制"这条
   该文件最大的未验断言、r5 的 A5/B3/C1/C4/D3/E1-E5/F1-F3、r6 的定案 1/2/10/11/12、
   r7 的 A5/A6/B1/B2/B4/B5/B6/B7/B10/B11/D1/D2、r7b 的 B-7 等)。
   **`notes/r7c-90`(490 行)、`notes/r8a-90`(2,121 行,71 条定案)、`notes/r8b-90`(407 行)三份完全未审**
   ——这三份恰好是条目最多的三份。`r7-raw-*`、`r7c-raw-*`、`r8a-raw-*`、`r8b-raw-*` 共 40 余份
   分段底稿完全未读。其余底稿只被当作**核对参照**用(判断某个数是"章节笔误"还是"底稿传下来的",见建议-6)。
2. **文档侧证据只做了 8 条定向抽查,未系统核实**。定案最常见的失效方式是**文档被转述走形**,
   评审位为此专门抽了 8 条**文档原文**去基线逐字核,**8 条全部成立**(见 §6.4),
   但这只是全部定案(R2-R8B 合计逾 200 条)的一个零头,且是评审位**自选**的样本,不是随机抽样。
   **"以代码为准"这条铁律,本轮在代码侧验得较实,在文档侧仍是抽样级。** 这是本次评审最大的缺口。
3. **r8a 的 105 个"零提及"配置键未逐条复核**(见存疑-1)。
4. **测试未运行**。CLAUDE.md 的可选 venv 未重建,故各轮报告里的用例数
   (R2 225、R3 589、R4 664、R5 1,360、R6 659、R7B 1,102、R7C 1,081、R8A 3,183/3,190 等)
   **一个都没有独立复现**。这些数按 CLAUDE.md 自己的说明"是环境的函数",
   评审位无法在不建同规格 venv 的前提下判定。
5. **`data/capability-mining.json` 与 R1 附卷 170 条能力点**只抽了 2 条(即建议-4 的两处),
   其余 168 条的代码摘录未核。
6. **章节的 Mermaid 图只做了静态检查,未实渲染。** 静态检查已全量跑过并通过:11 章共 **18 个**
   ```mermaid 围栏(围栏语言标记全部正确),其中 **224 个节点标签**,剥去 `<br/>` 后
   **0 个**含裸尖括号——即第 5 条硬标准的两条机械子项均满足。但评审位**未在 GitHub 页面实际渲染**,
   故"必须 GitHub 页面直接渲染"这一条**未做端到端验证**(布局溢出、subgraph 嵌套等只有实渲才看得出)。
7. **原定规模被压缩,且对抗复验环节被整段砍掉**。评审位原计划分 19 路对全部章节、报告、
   定案卷做深核,并对**每一条**候选意见做一次"默认它是错的、尽力推翻它"的独立复验;
   实测算力预算不足以在合理时间内跑完,遂收敛为"主线全量亲读 + 两路定案卷审计"。
   两个后果必须说清:
   - **§6.2 那 58 条亲核结论,没有一条经过第二方的"尽力推翻"复验。** 本报告为每条意见都附了
     可复算的基线原文块,正是为了让仲裁能零成本推翻。
   - **§6.2 第二条线提出的 20 条里,12 条未被复核,因此未立案**(见 §6.2 说明)。
   另有两份定案卷范围(`r7c-90`/`r8a-90`/`r8b-90` 与全部 12 份报告的格式与报数复算)
   在本报告定稿时尚未产出结果,故其结论**一律未纳入**——报告只写已亲自复核的部分。

### 6.4 文档侧定向抽查(8 条,全部成立)

因为这是评审位一开始就认定的最大风险面(定案的另一半是"文档究竟怎么说的"),单列报数。
判据:去基线打开定案点名的那个文档文件那一行,**逐字**比对定案的转述。

| # | 定案出处 | 定案的转述 | 基线文档原文核验 |
|---|---|---|---|
| 1 | r3 §3.2 / §5 | 安全文档称底线与 `UNRECOVERABLE_BLOCKLIST` 同步,而该符号代码里不存在 | ✓ `website/docs/user-guide/security.md:101` 逐字含 "kept in sync with `tools/approval.py::UNRECOVERABLE_BLOCKLIST`";全仓该符号**只**出现在此文件与其 zh-Hans 镜像,真符号为 `tools/approval.py:434` 的 `HARDLINE_PATTERNS` |
| 2 | r4 §3.7 / §5 | `tools.md:88` 说"关机即删",`:90` 又给 `container_persistent` 开关,同页自相矛盾 | ✓ `website/docs/user-guide/features/tools.md:88` 末句逐字 "The container is stopped and removed on shutdown.";`:90` 逐字 "the `container_persistent` flag that controls whether `/workspace` and `/root` survive across Hermes restarts" |
| 3 | r4 §3.3 / §5 | `README:29` 只说 Daytona+Modal 提供 serverless 持久化、措辞是"空闲时休眠",漏了 Vercel | ✓ `README.md:29` 逐字 "Daytona and Modal offer serverless persistence — your agent's environment hibernates when idle and wakes on demand";同行确实列了七个后端含 Vercel Sandbox,但持久化只点了两家 |
| 4 | r7b ▲1 | 开发者文档说第一层守卫"入槽**并设置中断事件**" | ✓ `website/docs/developer-guide/gateway-internals.md:86` 逐字 "queues the message in `_pending_messages` and sets an interrupt event"(并见阻断-1:同句最后一分句也过时,尚未被证伪) |
| 5 | r7c §5 其一 | 接入文档让你去 `_deliver_result()` 改一张 `platform_map`,而 cron 目录里该词零命中 | ✓ `gateway/platforms/ADDING_A_PLATFORM.md:256` 标题为 "## 8. Cron Delivery (`cron/scheduler.py`)",`:258` 逐字 "Add to `platform_map` in `_deliver_result()`";`_deliver_result` 确在 `cron/scheduler.py:1467`;`grep -rn platform_map cron/` **零命中**(全仓残留均为另一符号 `_merge_platform_map`) |
| 6 | r7c §5 其三 | 契约文档让你调 `GatewayRunner._resolve_slash_confirm(...)`,该方法全仓不存在 | ✓ 该标识符全仓仅出现两次,均为说明文字(`gateway/slash_commands.py:5210` 注释、`gateway/platforms/base.py:3766` docstring),**无任何 `def`** |
| 7 | r8a ▲-6 | FAQ 两处写 "First user to message in DM claims exclusive access" | ✓ `website/docs/reference/faq.md:411` 逐字命中;`:96` 亦逐字含 "DM pairing (first user to message claims access)" |
| 8 | r8b §7 | `configuration.md:1646` 教用户设 `display.compact`,而读取分支是死代码 | ✓ 文档侧行号与内容命中;代码侧 `cli.py:4223` 形参 `compact: bool = False`、`:4248` 判 `is not None`,故配置分支不可达 |

**这 8 条的分布是有意的**:覆盖 r3 / r4 / r7b / r7c / r8a / r8b 六轮,并刻意各取一种腐烂形态
(符号名滞后、同页自相矛盾、清单漏项、分句半过时、路径失效、幽灵 API、方向写反、死分支)。
**8/8 成立,说明产出方在文档侧的转述纪律与代码侧同级。** 但样本量不足以外推到全部定案。

---

## 7. 给仲裁的四句话

1. **六条阻断没有一条是"机制理解错"。** 三条是数字/数量级写错(阻断-2/3 与 5),
   三条是"代码读对了、指错了对象"(阻断-1 指错层、阻断-4 指错文档小节、阻断-6 指错配置键)。
   §6.2 亲核的 58 条里,凡涉及"这个机制为什么这样设计"的**全部成立**。
   **这套产出的解读质量可信,需要修的是精确指向。**
2. **一条工程改动能同时消掉三类问题:把引用校验的适用面从"围栏块"扩到"引用块"**
   (M-16a)。它一次覆盖了阻断-4(文档小节指错)、建议-15(5 处锚点漂移)、
   以及本报告 §6.3 第 2 条申报的最大缺口。**代码侧因为有脚本兜着所以稳,文档侧因为只有人工
   约定所以漂**——R7C 当初升格这个脚本的理由,今天原封不动地适用于文档侧。
3. **引用纪律的回填有时限压力**(M-5 / M-6 / M-16)。r3/r7c/r8a 三章 0 处违规,证明标准可达;
   但 R12 一旦装订,《设计蓝图》前半本就会带着 99 处不可解析引用出版,届时再改成本更高。
4. **本报告自身的覆盖是不均衡的,请按 §6.3 打折使用。** 11 章全读、机器校验全量;
   但 `notes/r7c-90`、`notes/r8a-90`(71 条定案)、`notes/r8b-90` 三份**完全未审**,
   全部测试用例数**一个未复现**,且原定的对抗复验环节被整段砍掉。
   **本轮最该被继续追的方向,是那三份未审的定案卷**——按已审七份的命中率(45/62 成立、
   8 条经复核立案)线性外推,它们里面大概还有可立案的条目。
