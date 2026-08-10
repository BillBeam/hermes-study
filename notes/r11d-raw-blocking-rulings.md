# r11d-raw-blocking-rulings · 装订阻断判定

> **本片任务**:对 `reports/round-11c-pre-binding-cleanup.md` §11.1「装订前遗留清单」
> 那 15 行(14 个具名案号 + 一行「片内其余」)**逐条判定是否阻断 R12 装订**,
> 外加主线本轮新发现的第 16 条(自引锚点)。
> **溯源约定**:指向 hermes-agent 的锚点写 `路径:行号 @ 863e313`;
> 指向本仓库自己的锚点带 commit 钉子(R11D 立),本片一律钉 `@ df6d450`
> —— 那是本轮开工杂项提交,也是片 A / 片 B / 片 C 的共同起点。
> **本片只判定,不清理**:一处 `chapters/` 没改、一个 `scripts/` 没动。

---

## 0. 判定标准(先把「什么叫阻断装订」定义清楚)

R12 装订的**产出是 `chapters/`**,`notes/` / `reports/` / `reviews/` 不进《设计蓝图》正文。
所以判定不能只问「这条还开着吗」,要问「它不清,R12 会出什么事」。三条判据,**任一命中即阻断**:

| 判据 | 问题 | 作用面 |
|---|---|---|
| **甲 · 印错** | 不清,《设计蓝图》**正文**会印出错的 / 缺的 / 会把读者带偏的东西 | `chapters/` 21 份 |
| **乙 · 走错** | 不清,**装订这个动作本身**会走错:作者据它去找会找错文件/行,或据它做的合并、重排基于错的前提 | 不限 `chapters/` |
| **丙 · 关卡红** | 不清,R12 commit 前必跑的关卡会因**存量**(而非 R12 自己的产出)而失败 | 关卡强制范围 = `chapters/` 全部 + 当轮 `notes/` `reports/` |

三条都不中 → **不阻断**。但**不阻断的条目必须写两件事**:*为什么不影响*,以及
*它在什么条件下会变成阻断*。「已确认无影响」一句带过是不允许的 —— 那句话本身不携带任何
可以在下一轮被推翻的内容。

**为什么判据丙要单列。** 甲、乙问的是「内容对不对」,丙问的是「流程过不过」。
R12 是**唯一一轮产出就是 `chapters/`** 的轮次,于是所有历史上「只在 `chapters/` 上跑」的关卡,
在那一轮同时也是「对当轮产出跑」。一条积压只要落在 `chapters/` 上,它在 R12 就从
「历史欠账」变成「当轮失败」。CLAUDE.md 已经把四道关卡的强制范围写死成
`chapters/` 全部 + 当轮 notes/reports:

`CLAUDE.md:225 @ df6d450`

> - **章序与可复算指标两道关卡,每轮 commit 前必跑到退出码 0(R11D 立)**:

**边界必须说死,否则判据甲会无限膨胀。** 一条只活在 `reports/` / `notes/` / `reviews/` 的遗留,
**默认不满足判据甲**。它仍可能因判据乙进来 —— 但要**具体指出它会让装订作者在哪一步走错**,
不能只说「证据不完整所以危险」。本片有两条正是这样进来的(第 15 行的 `H-R11C-F-c` / `-F-d`),
也有若干条正是这样被挡在外面的(`H-R11C-M-a` / `-M-b` / `-A-b`)。

**一条方法上的自律**:本片对「主线声称已结清」的 6 条**不采信声明**,一律自己跑关卡、
自己读文件(见 §3)。核实中确实推翻了一条的**完整性**(`H-R11C-F-a`,见 §3.1)。

---

## 1. 判定表(16 行)

**阻断 4 行**(第 4、6、15、16 行),**已结清 6 行**,**不阻断 6 行**。
「已结清」在本表里是**独立核实过**的结论,不是照抄主线。

| # | 案号 | 阻断? | 一句话依据 | 清理需要做什么 |
|---|---|---|---|---|
| 1 | `H-R11B-d` | **不阻断** | 判据丙作用面为空:`chapters/` 全部 21 章只有 **1 个** ```` ```verify ```` 块且**已配对**,`unpaired=0` | 无需在 R12 前动;等一轮愿意逐条判 C 类正当性的轮次 |
| 2 | `H-R11C-D-f` | **已结清(制度侧)** | `CLAUDE.md:539 @ df6d450`:`  **锚点寻址修正是第四类改动,与「行号漂移」同级(R11D 裁定,结清 H-R11C-D-f)。**` 已入册,锁解除 | 执行侧 70 处在 `reports/`+`reviews/`,不进正文;片 A 本轮在做,做不完也不阻断 R12 |
| 3 | `H-R11C-D-a` | **已结清** | `scripts/verify_citations.py:176 @ df6d450`:`CITE_EXTS = "py` —— 该行末尾三项为 ps1 / css / tsv(全文见 §3.4) | — |
| 4 | `H-R11C-D-b` | **阻断(1 处)** | 264 处镜像歧义里**只有 1 处**落在正文:`chapters/r9a-capability-organization.md:430` 的 `creating-skills.md:178`,▲5 的文档侧指不到唯一文件 | 补成 `website/docs/developer-guide/creating-skills.md:178`:`Hermes never exposes the raw secret value to the model`(判据见 §2.4)。**与第 15 行 H-R11C-D-e 同一处,别做两遍** |
| 5 | `H-R11C-E-c` | **已结清** | `scripts/verify_derived_numbers.py` 已落地,本片实跑 `declared=18  OK=18  STALE=0` | — |
| 6 | `H-R11C-F-a` | **部分阻断** | 重号已修、落点表已立、关卡实跑全绿;但残留 **4 处**「第 N 章」**不点名文件**,关卡明确不猜,R12 重排会静默失配 | R12 重排前把这 4 处改成「章号 + 文件名」同现,或删掉章号只留文件名 |
| 7 | `H-R11C-F-b` | **已结清(带覆盖面说明)** | 关卡是**声明式**的,21 章里只有 `chapters/r1` 写了 `derived` 声明;另有 2 处未声明手抄件(`chapters/r10b:269,271`)**当前值正确** | — |
| 8 | `H-R11C-E-a`/`-b` | **已结清** | 独立复算台账,`chapters/r1` 的分层表与进度段逐个对上(563 / 2,131 / 5,944 / 2,586) | — |
| 9 | `H-R11C-M-a` | **不阻断** | 铸号落点是**追踪机制**问题,零字进正文;R12 的阻断清单是本文件 §1,不是普查输出 | — |
| 10 | `H-R11C-M-b` | **不阻断** | 移交普查的语料**按构造**只有 `reports/` + `notes/`(`corpus dirs = reports notes`),`chapters/` 从不在其中 | — |
| 11 | `H-R11C-M-c` | **不阻断** | 三条都是**运行期确认**;`chapters/` 全语料 `ffmpeg` 命中 **0 份文件**,正文没有任何一句依赖它们 | — |
| 12 | `H-R11C-M-d` | **已结清** | `CLAUDE.md:193 @ df6d450`:`  **分母按语料性质选,下限一律 70% 不下调(R11D 裁定,结清 H-R11C-M-d)。**`;实测 `chapters/` 80.6% 复现 | — |
| 13 | `H-R11C-A-b` | **不阻断** | R8D 那 7 条是 provider 别名/api_mode 的**未决调查**,全语料 `chapters/` 里 `aliyun`/`nemotron`/`vllm`/`trinity`/`Unknown provider` 命中 0 | — |
| 14 | `H-R11C-B-f` | **不阻断(且现象需更正)** | 索引**事实上已存在**:`data/r11c/b-dedup-82-index.tsv:3`:`C02	hermes_cli/config.py	3065,3089,3092	9	4	REAL	R8A/H-7 R8B/H-7 R8B/H-R8FIX-a` —— 拿 `H-7` grep 这张表就到 C02 | 把它**声明**为别名落点即可,不必新建文件 |
| 15 | 片内其余 | **阻断 3 条 / 22 条不阻断** | 25 条里 `H-R11C-D-e`(正文 10 处裸文件名)、`H-R11C-F-c`(正文标记比定案低一级)、`H-R11C-F-d`(同一指标两章两口径)命中判据甲 | 见 §2.15 三张清单 |
| 16 | 自引锚点 615 / 101 → `chapters/` | **条件阻断** | 101 处**零处在 `chapters/` 内**(来源 notes 60 / reviews 34 / reports 7),正文不受影响;但 `chapters/` 内另有 **8 处跨章文件名引用**,R12 一旦改名或合并章文件就断在正文里 | 只要 R12 动章文件名/合并,这 8 处必须同步;不动名则不阻断。另:615 这个数**虚高 138**,见 §2.16 |

**一句话把阻断项收拢**:R12 装订前**必须清**的只有三件事 ——
(a) `chapters/` 里 **10 处**无法从仓库根解析的裸文件名锚点(第 4 行 + 第 15 行的 `D-e`,同一份清单);
(b) `chapters/r8d` 的一处标记与 `chapters/r8d` / `chapters/r9c` 的一处跨章口径冲突(第 15 行的 `F-c` / `F-d`);
(c) 装订**动手时**同步的两类引用(第 6 行 4 处不点名章号 + 第 16 行 8 处跨章文件名)。

---

## 2. 逐条论证

### 2.1 `H-R11B-d` —— C 类 27 块静默 exit-1 · **不阻断**

**现象。** R11C §11.1 第一行:未配对的 ```` ```verify ```` 块里,有一批**退出码非零但 stderr 为空**的,
关卡的判据是「非零退出 **且** 有 stderr」才判 `EVIDENCE-RUNFAIL`,于是这一类既不失败、也没人判过正当性。

`reports/round-11c-pre-binding-cleanup.md:453 @ df6d450`

> | `H-R11B-d` | C 类 27 块静默 exit-1 的正当性仍未判 | `data/r11c/probes/runnability_census.py:88`:`silent += 1          # C 类:正当性未判,不计入坏证据` | 任一轮 |

**判定依据:判据丙的作用面为空。** 这一类只能通过「关卡在 R12 变红」伤到装订,
而关卡的强制范围里属于存量的那一半是 `chapters/`。实跑:

```verify
python3 scripts/verify_evidence_commands.py chapters/*.md | grep -E 'paired=|runnability'
```

```text
verify-blocks paired=1  unpaired=0  differing=0  timedout=0
runnability   ran=0  runfail=0  skipped-mutating=0
```

`chapters/` 21 份合起来只有 **1 个** ```` ```verify ```` 块,而且**已配对**、`differing=0`。
`unpaired=0` 意味着 C 类(未配对块的一个子集)在 `chapters/` 上的规模**必然是 0** ——
不是「查了没有」,是**集合上不可能有**。

**为什么不影响。** 这一条完全活在历史 `notes/` 里。它既不进正文(判据甲不中),
也不会让装订作者找错文件(判据乙不中:它说的是「某条命令的退出码没人判过」,
不是「某个锚点指错了」)。

**什么条件下变成阻断。** 两种:(1) 有一轮把可跑性检查的**强制范围**从
「`chapters/` + 当轮」扩到全语料 —— 那一刻这 27/28 块立刻变成当轮失败;
(2) R12 自己在成品章里新写 ```` ```verify ```` 块并且不配 ```` ```text ````。第 (2) 种是 R12 的自律问题,不是这条积压。

**本轮重跑的读数(不钉数,理由随后)。**

```text
$ HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11c/probes/runnability_census.py
readonly_unpaired=541 exit0=513 silent_exit1=28 bad=0 skipped_mutating=155
bad_by_kind=(none)
baseline_porcelain_changed=False
```

**为什么这条读数不写成 ```` ```verify ```` 块**:它耗时约二十分钟(要真跑五百多条命令),
而 CLAUDE.md 把本片底稿放进每轮 commit 前的强制范围 —— 钉进去等于让此后**每一次** commit
承担这个代价;同时它的语料含 `reports/`,而**取这条读数时片 A 正在并发改写那里**
(该片此后已收到完成信号,但读数是那之前取的)。所以这里如实标注:**读数 28,
口径 = 全语料(chapters/notes/reports/reviews/data)、读工作树、取数时 `reports/` 正被改写**,
与 R11C 报的 27 **不是同一次测量的两个值**,是两次不同口径的测量
(语料在长;CLAUDE.md「同一指标多次/多方法测量必须分别标注」)。**它不改变本条判定**,
因为判定只依赖 `chapters/` 那个 0。

---

### 2.2 `H-R11C-D-f` —— 70 处锚点无人可改 · **已结清(制度侧)**,执行侧不阻断

见 §3.5 的独立核实。这里只记判定:**制度锁已解除**,而**执行**(`reports/` 50 处 +
`reviews/` 20 处)**不阻断 R12** —— 两个目录都不进《设计蓝图》正文。

**为什么不影响。** 判据甲不中(不进正文)。判据乙也不中,而且理由是**制度自己给的**:

`CLAUDE.md:558 @ df6d450`

> *装订后不误导读者的保证在于:`reviews/` 不进《设计蓝图》正文(R12 只装订
> `chapters/`),而附录与原文同目录并列、由原文件名直接指到,读者不会先撞见坏锚点。*

判据丙不中:`reports/` / `reviews/` 的历史文件不在 R12 的强制范围内
(强制范围是 `chapters/` 全部 + **当轮** notes/reports)。

**什么条件下变成阻断。** 如果 R12 决定把某份 `reviews/` 或 `reports/` 的内容**搬进**
成品章(例如把 review-1 的结论写成一节),被搬进去的那一段里的坏锚点当场满足判据甲。
**装订时凡从这两个目录搬文字,必须连锚点一起核。**

---

### 2.3 `H-R11C-D-a` —— 白名单漏 ps1/css/tsv · **已结清**

见 §3.4 的独立核实。**不阻断**,因为它已经不存在了。

**什么条件下会再变成阻断**:白名单是**有限枚举**,而它的失效方式是「有人写了一个新扩展名的锚点」。
本片的探针用的是**宽正则**(任意 1–6 位扩展名,不查白名单),所以若 `chapters/` 里有
白名单外的锚点,它会出现在读数 [1]/[2] 里 —— 而那两处读数里 `chapters/` 只有 `.py` 与 `.md`,
**说明现有成品章锚点的扩展名全部在表上**。
R12 若在成品章里引入新扩展名(如 `.rb`、`.go`、`.proto`),那些锚点会**连分母都进不去** ——
这正是 R10B 给这一类定的性质,比 UNCHECKED 更隐蔽。

---

### 2.4 `H-R11C-D-b` —— zh-Hans 镜像歧义 · **阻断,但只有 1 处**

**现象。** `website/docs/**` 每份文档在 `website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/`
下都有同名镜像,于是**任何裸文档名恒有 ≥2 个候选**,机械判据永远定不了。

**作用半径按目录切一刀:**

```verify
python3 data/r11d/probes/blocking_scope_census.py /home/user/hermes-agent | sed -n '/^\[3\]/,+4p'
```

```text
[3] 镜像型歧义(候选恰为 website/docs + zh-Hans 两份)按目录
  chapters       1
  notes        200
  reports       50
  reviews       10
```

**264 处里只有 1 处落在正文**,就是这一处:

`chapters/r9a-capability-organization.md:430 @ df6d450`

> | ▲5 | `creating-skills.md:178` | 密钥 **never** 给模型 | 第三方密钥经沙箱透传可被模型读到 |

**判据甲命中。** 这一格是一条 ▲ 定案的**文档侧**,而 ▲ 的成立就靠「文档在这一行这么说」。
读者要复核它,必须知道是哪一份 `creating-skills.md`。两个候选的第 178 行**说的是完全不同的两件事**:

`website/docs/developer-guide/creating-skills.md:178 @ 863e313`

```
The user can skip setup and keep loading the skill. Hermes never exposes the raw secret value to the model. Gateway and messaging sessions show local setup guidance instead of collecting secrets in-band.
```

中文镜像的同一行讲的是环境变量透传,**没有** `never` 那半句。所以 ▲5 指的是英文那份 ——
**内容判据是唯一的**,不需要作者猜。补全动作:`creating-skills.md:178` →
`website/docs/developer-guide/creating-skills.md:178`。

**这一处与第 15 行 `H-R11C-D-e` 的第 10 处是同一处**,清理时按一份清单做,不要做两遍。

**其余 260 处为什么不阻断**:全在 `notes/`(200)、`reports/`(50)、`reviews/`(10),不进正文。
**什么条件下变成阻断**:同 §2.2 —— R12 从这三处搬文字进章时。

---

### 2.5 `H-R11C-E-c` —— 没有关卡覆盖「可复算指标的第二份手抄件」· **已结清**

见 §3.3。**不阻断**。

---

### 2.6 `H-R11C-F-a` —— 章号重号 · **部分阻断**(残留 4 处)

主线已修的那一半见 §3.1,核实通过。这里记**核实中查出、主线未处置**的那一半。

关卡自己就把这个缺口打印出来了:

```verify
python3 scripts/verify_chapter_order.py
```

```text
chapters=21  重号=0  未编号=0
正文章号提及:一致=1  未点名文件(不猜)=4  非 chapters/ 的不一致=0(记 ADVISORY,不改退出码)
OK: 章号无重号、与磁盘双射、连续,且成品章正文引用与落点表一致
```

`未点名文件(不猜)=4` —— 这 4 处「第 N 章」**只写了章号,没写文件名**,
关卡按「声明,不靠嗅探」的原则**明确不猜**(与 CLAUDE.md 给 ```` ```text ```` 那一栏定的是同一条原则)。
逐处是:

```verify
grep -rnE "第\s*([0-9]+|[一二三四五六七八九十]+)\s*章" chapters/ | grep -v r11b
```

```text
chapters/r8d-self-custody.md:259:第二章讲的是"怎么调用一个模型"。这一节是**上游那半**:在调用之前,
chapters/r7c-gateway-periphery-and-scheduling.md:110:    CORE["会话核心(第 7 章)<br/>GatewayRunner + session<br/>一条消息 → 一次 agent 回合"]
chapters/r7c-gateway-periphery-and-scheduling.md:262:判据来自 agent 的活动时间戳 —— 和第 7 章讲过的三个看门狗**共用同一口钟**。
chapters/r7c-gateway-periphery-and-scheduling.md:389:全系统没有一个权威定义。对比一下第 7 章里已经定案的正例 ——
chapters/r7c-gateway-periphery-and-scheduling.md:464:顺带更正上一轮的一处定位:第 7 章曾把"看板评论 steer"归到网关的看板 watcher 文件里。
chapters/r1-what-is-hermes-agent.md:5:> 它由哪些部分组成、每部分大致干什么、以及后面的章节该按什么顺序读。这是《设计蓝图》的第一章,
```

(六行里 `r7c:110` 在 mermaid 围栏内、`r1:5` 在 `>` 引用块内,关卡两种块都跳过 ——
所以计数是 **4**,不是 6。跳块的理由与 `verify_citations.py` 同源:块里的字是别人的话。)

**逐处核对当前指向,四处全部正确**:落点表里第 2 章 = `chapters/r2-turn-loop-and-model-access.md`
(主题「回合主循环与模型接入」= "怎么调用一个模型"),第 7 章 = `chapters/r7-gateway-session-core.md`
(主题「网关会话核心与多路复用」= GatewayRunner + 看门狗)。**所以这不是当前的错。**

关卡为什么不猜,它自己写着 —— 而这正是这 4 处会静默活下去的机制:

`scripts/verify_chapter_order.py:35 @ df6d450`

> **只认「声明」,不靠嗅探**:一句「第二章讲的是怎么调用一个模型」没有点名文件,
> 本脚本记 UNVERIFIABLE 并计数,**不去猜**它指哪一章 —— 与 CLAUDE.md 给

**判据甲以「R12 重排」为前提命中。** R12 要合并、加分部、重排 21 章 —— 章号是**最会变的东西**,
而这 4 处**没有任何机制**会在章号变化时提醒作者。它们与 `chapters/r11b:255` 那处重号
唯一的区别就是「同行有没有写文件名」,而那处重号**活了六轮**正是因为没人查。

**清理需要做什么。** 两个选项,任选:(a) 把这 4 处写成「第 N 章 `chapters/xxx.md`」
—— 关卡当场纳入检查面;(b) 删掉章号只留主题词(如「上一章讲模型调用」)。
**推荐 (a)**:成品章里跨章指路是有价值的,而 (a) 的成本是一行加一个文件名。

---

### 2.7 `H-R11C-F-b` —— 章内数字 vs 可计算数据 · **已结清,但覆盖面要如实说**

见 §3.3 的独立核实(关卡已立并实跑全绿)。这里补一条**核实中查出的覆盖面事实**。

关卡是**声明式**的:正文写 `<!-- derived: … -->` 才会被复算。全 21 章里**只有 `chapters/r1`
写了声明**(4 处)。于是 R11C 那句「这类过期没有任何判据在查」现在准确的说法是:
**「声明了的在查,没声明的照旧没人查」**。脚本自己把这个代价写在文件头,不藏:

`scripts/verify_derived_numbers.py:1 @ df6d450`

> #!/usr/bin/env python3

我按「哪些数会自己变」把台账派生值在 `chapters/` 里搜了一遍,**搜索面 = 21 份成品章全文,
模式 = 分层五行的文件数与行数、总数 8,530 / 2,608,452、`R1-inventoried` 的两个数、
以及被它们推出的进度数(含带千分位与不带两种写法)**,剔除 `chapters/r1` 后**只剩 2 处**:

```verify
grep -nE '8,530|1,895|602,085' chapters/r10b-desktop-application.md
```

```text
269:本项目把全仓 8,530 个文件分成五层:L1 逐机制精读、L2 结构级理解、
271:——1,895 个文件 / 602,085 行,没有人说过「知悉用途」交付到什么程度算读过。
```

两处**当前值都正确**(台账复算 L3 = 1,895 / 602,085,总文件数 8,530,见 §3.2 的复算块)。

**为什么不阻断**:当前印出来的数是对的,读者读到的不是错的。
**什么条件下变成阻断**:只要有**任何一轮**改动 L3 的归层或全仓文件总数,
`chapters/r10b:269` 与 `:271` 会**静默过期** —— 与 `chapters/r1` 那次一模一样的形态,
而这一次关卡**同样看不见**(没有声明)。
**建议(不属本片权限)**:给这两行补 `<!-- derived: … -->` 声明,成本是两行注释。

---

### 2.8 `H-R11C-E-a`/`-b` —— `chapters/r1` 过期数字 · **已结清**

见 §3.2 的独立复算。**不阻断**。
**什么条件下会再变成阻断**:关卡是声明式的,而 `chapters/r1` 的声明**已经写全**(4 处覆盖 18 个数)。
真正的复发面是**新写的章**:R12 若在装订时写导言、总览、统计表,那些数如果不带声明,
就回到 R8-fix / R11C 两次踩过的同一个坑。

---

### 2.9 `H-R11C-M-a` —— 铸号也要定单一落点 · **不阻断**

**现象。** R11B 定了「结清的单一落点」,但**铸号**在哪儿铸没有落点,于是一个案号可以在
任意底稿里出生,普查得靠猜去哪找。

**判定:三条判据都不中。** 它零字进正文(甲);它不会让装订作者找错文件 —— 它让人
**找不到**,而 R12 的阻断清单是**本文件 §1** 这张表,不是普查输出(乙);它不在任何关卡里(丙)。

**什么条件下变成阻断。** 一旦有人**拿移交普查的输出当「装订前清完了吗」的判据**,
这条立刻变成阻断 —— 而且是**最坏的那种**:普查会给出一个看起来很干净的
「未结清 7 条」,而真实情况见 §2.10 与 §4 的 `H-R11D-B-a`。
**本片明确不建议 R12 用普查输出做这个判断。**

---

### 2.10 `H-R11C-M-b` —— 149 行「认不出表头」未逐行判 · **不阻断**

**判定依据是构造性的**:移交普查的语料**只有 `reports/` 与 `notes/`**,`chapters/` 从不在其中。

```verify
python3 -c "
import importlib.util as u
s = u.spec_from_file_location('c', 'data/r11c/probes/handover_census_r11c.py')
m = u.module_from_spec(s); s.loader.exec_module(m)
for x in ['H-R11C-D-f', 'H-R11B-A-c', 'H-R10B-a', 'H-B1-e', 'H-7']:
    print(x, m.ID_RE.findall(x))
print('corpus dirs =', m.REPORTS.name, m.NOTES.name)
"
```

```text
H-R11C-D-f []
H-R11B-A-c []
H-R10B-a ['H-R10B-a']
H-B1-e ['H-B1-e']
H-7 ['H-7']
corpus dirs = reports notes
```

最后一行 `corpus dirs = reports notes` 就是证明:脚本的两个语料常量分别是 `reports` 与 `notes`,
再无第三个。(同一个块的前五行服务于 §4 的 `H-R11D-B-a`,一次跑出两个读数,不重复跑。)所以这 149 行**在原理上不可能落在 `chapters/`**,判据甲、丙都不中。

**为什么不影响。** 「认不出表头」意味着普查**没有把这些行归类成移交或定案**,
但按 R11C 自己定的规矩,它们**仍然被打印出来**(UNCLASSIFIED)——
即「可见但未判」,而不是「消失」。可见的东西不会让装订作者走错。

**什么条件下变成阻断。** 与 §2.9 同一个条件:有人拿普查的「未结清 N 条」当装订前的清账判据。

**一条如实交代**:本片重跑普查得到的 UNCLASSIFIED 行数**高于** R11C 报的 135
(语料在长,且片 A 正在并发改写 `reports/`)。**本片不钉这个数** —— 一个钉在正被
并发改写的语料上的读数,正是 CLAUDE.md「量『之前』的命令不许钉在会移动的引用上」
连着两轮记的那种错。判定不依赖它。

---

### 2.11 `H-R11C-M-c` —— 三条同族卡在「不扩共享环境」· **不阻断**

**现象。** `H-R9B-f`(`.ogg` 目标下 ffmpeg 走 Vorbis 还是 Opus)、`H-R11A-d`(平台 extra 装齐后
的运行期用例集合)、`H-R11B-f`(同上),三条都需要**扩共享环境**才能确认,已连续两轮维持不关闭。

**判定依据:正文里没有任何一句依赖它们。** 搜索面 = `chapters/` 全部 21 份 .md 全文,
模式 = 字面 `ffmpeg`(大小写敏感),不排除任何文件:

```verify
grep -rlc 'ffmpeg' chapters/ | wc -l
```

```text
0
```

**0 份文件命中**。`.ogg` / Opus / Vorbis 这条线索在成品章里**根本没有被写出来过**,
所以它确认不确认都不改变正文一个字。

**为什么不影响。** R11B 的定案本身就写清了边界:静态代码上的推定成立,缺的只是运行期确认,
而且**明确拒绝把「没跑成」写成「不成立」**:

`notes/r11b-90-handover-rulings.md:369 @ df6d450`

> **定案:维持推定,不关闭;本轮无法证实,原因是环境而非分析。**

一条**被正确标注为「推定」且没有进正文**的结论,不构成装订风险。

**什么条件下变成阻断。** 如果 R12 在装订时把这条推定写进某一章、并且**写成断言**
(而不是「静态代码上推定如此,运行期未确认」),那一刻它满足判据甲。
**装订时凡把 `notes/` 里的推定升级成正文陈述,必须保留它的证据等级。**

---

### 2.12 `H-R11C-M-d` —— 70% 下限与元工作片口径 · **已结清**

见 §3.6。**不阻断**。

---

### 2.13 `H-R11C-A-b` —— R8D 7 条通用号从未进任何账 · **不阻断**

**现象。** R8D 片底稿的移交表用 `H-1`…`H-7`(通用号,与别轮的 `H-1`…`H-7` 同域),
且这 7 条与 R8D 主线的 `H-R8D-a…j` **内容无一重合**,于是它们从未进入任何账。

`notes/r8d-raw-provider-identity.md:2700 @ df6d450`

> | # | 锚点 | 一句话现象 | 建议 |

**判定依据:7 条现象无一进正文。** 搜索面 = `chapters/` 全部 21 份 .md 全文,
模式 = 这 7 条各自的**特征串**(`aliyun` / `nemotron` / `vllm` / `llamacpp` / `trinity` /
`Unknown provider` / `qwen`),大小写不敏感,不排除任何文件:

```verify
grep -ric 'aliyun\|nemotron\|vllm\|llamacpp\|trinity\|Unknown provider\|qwen' chapters/ | grep -v ':0$' | wc -l
```

```text
0
```

**命中这些串的成品章为 0 份。**(顺带说明一个容易误判的干扰项:`chapters/` 里确实有多处
「别名」二字,但讲的是 shell 别名快照、配置键别名、斜杠命令别名,与 provider 身份映射无关。)

**为什么不影响。** 这 7 条自己就标着「需确认」「潜在」「未证实的风险」——
它们是**未决调查**,不是已取证结论。一条未决调查不写进正文,恰恰是对的。

**什么条件下变成阻断。** 与 §2.11 同型:R12 若把它们中的任何一条写进正文当结论。
另有一个更隐蔽的条件:R8D 的**成品章**(`chapters/r8d-self-custody.md`)在
§5 报了本簇合计 `▲ 12 / ◇ 8 / ■ 10 / ◎ 1`;如果 R12 装订时要**跨章汇总**记号数,
而这 7 条被谁「顺手补进」某个合计,那个合计就成了一个没有卷宗的数。

---

### 2.14 `H-R11C-B-f` —— 32 组合并的别名表没有索引 · **不阻断**,且现象需要更正

**现象(R11C 原话)**:「拿着 `H-7` 仍然走不到 `H-R8FIX-a` 的卷宗」。

**本片的更正:那张可查的索引事实上已经存在。**

`data/r11c/b-dedup-82-index.tsv:3 @ df6d450`

```
C02	hermes_cli/config.py	3065,3089,3092	9	4	REAL	R8A/H-7 R8B/H-7 R8B/H-R8FIX-a R8C/H-R8FIX-a R8FIX/H-R8FIX-a R8C/◎-2 R8A/▲-10 R8C/▲-1 R8C/▲-2 R8C/▲-3
```

`cases` 列把同一簇里的所有案号(含跨轮别名)并列写在一行,所以
`grep H-7 data/r11c/b-dedup-82-index.tsv` **一步就到 C02**,而 C02 同行就写着 `H-R8FIX-a`。
缺的不是文件,是**把这张表声明为别名落点**这个动作。

**为什么不影响装订。** 判据甲不中(不进正文);判据乙**曾经**是它最有可能命中的一条 ——
「装订作者拿着旧案号查不到卷宗」—— 但上面的更正把它取消了:查得到。

**什么条件下变成阻断。** 如果 R12 采纳 `H-R11C-B-a` 的建议(把 C40 那一族三条独立定案
合成一节),作者需要**逐簇**回溯卷宗;那时若索引没被声明为落点、作者不知道它存在,
就会退回「一条条 grep 全语料」。所以**本片建议主线在移交里点名这张表的路径**,
这是零成本的。

---

### 2.15 「片内其余」· **不能整行判**:阻断 3 条,不阻断 22 条

这一行是 15 行里**唯一一行没有案号**的,而它罩着的恰恰是**唯一含正文缺陷**的一批。

**先纠正这一行自己的计数。** 逐片数一遍 R11C 六份底稿的移交表:

```verify
for s in A:id-collisions B:dedup-82 C:bad-evidence D:anchor-resolution E:reversal-propagation F:pre-binding-inventory; do k=${s%%:*}; f=notes/r11c-raw-${s##*:}.md; printf "片 %s: %s 条\n" "$k" "$(grep -oE "H-R11C-$k-[a-z]\b" "$f" | sort -u | wc -l)"; done
```

```text
片 A: 4 条
片 B: 6 条
片 C: 6 条
片 D: 9 条
片 E: 6 条
片 F: 4 条
```

合计 **35 条**;§11.1 已具名的片内号是 10 条(`A-b`/`B-f`/`D-a`/`D-b`/`D-f`/`E-a`/`E-b`/`E-c`/`F-a`/`F-b`),
所以「其余」应为 **25 条**。而该行写的是「片 A 4 条 / 片 B 5 条 / 片 C 6 条 / 片 D 其余 /
片 E 4 条 / 片 F 3 条」——**两种读法都对不上**:按「全部」读,片 B 应是 6、片 E 应是 6、片 F 应是 4;
按「扣掉已具名」读,片 A 应是 3、片 E 应是 3、片 F 应是 2。**两种读法各有 3 片不符。**
加上 §4 的 `H-R11D-B-a`(这 35 个号**没有一个**能被移交普查看见),结论是:
**这一行既不是可靠的指针,也没有任何机械清单兜底。**

#### (a) 阻断 3 条

**`H-R11C-D-e` —— 成品章 10 处违反硬标准 8(不写裸文件名)。判据甲直接命中。**

```verify
python3 data/r11d/probes/blocking_scope_census.py /home/user/hermes-agent | grep -E '^\[2\]|^  chapters/r'
```

```text
[2] chapters/ 内不可解析锚点逐条(10 处)
  chapters/r7b-platform-integration.md:226	base.py:5584	AMBIGUOUS	9 个候选
  chapters/r7b-platform-integration.md:229	base.py:5611	AMBIGUOUS	9 个候选
  chapters/r7b-platform-integration.md:230	base.py:5627	AMBIGUOUS	9 个候选
  chapters/r7b-platform-integration.md:231	base.py:5656	AMBIGUOUS	9 个候选
  chapters/r7b-platform-integration.md:232	base.py:5711	AMBIGUOUS	9 个候选
  chapters/r7b-platform-integration.md:233	base.py:5715	AMBIGUOUS	9 个候选
  chapters/r7b-platform-integration.md:234	base.py:5731	AMBIGUOUS	9 个候选
  chapters/r7b-platform-integration.md:235	base.py:5746	AMBIGUOUS	9 个候选
  chapters/r8b-cli-trunk-and-interaction.md:197	server.py:5811	AMBIGUOUS	4 个候选
  chapters/r9a-capability-organization.md:430	creating-skills.md:178	AMBIGUOUS	2 个候选
```

CLAUDE.md 对这一条的措辞已经把危害说尽了:

`CLAUDE.md:476 @ df6d450`

> 8. **引用必须能从仓库根解析(R8-fix,review-1 建议-1 / M-5)**:成品章里不写裸文件名,

前 9 处**目标已被行号判据定死**,不需要作者猜:

```verify
cd /home/user/hermes-agent && for f in $(git ls-files | grep -E '/(base|server)\.py$'); do printf "%6s  %s\n" "$(wc -l < $f)" "$f"; done
```

```text
  2510  acp_adapter/server.py
   336  agent/secret_sources/base.py
    89  agent/transports/base.py
  6861  gateway/platforms/base.py
   306  hermes_cli/dashboard_auth/base.py
   108  hermes_cli/proxy/adapters/base.py
   298  hermes_cli/proxy/server.py
   200  plugins/google_meet/node/server.py
   238  providers/base.py
   875  skills/productivity/docx/scripts/office/validators/base.py
   875  skills/productivity/powerpoint/scripts/office/validators/base.py
  1370  tools/environments/base.py
 14006  tui_gateway/server.py
```

`base.py:5584`…`:5754` 只有 `gateway/platforms/base.py`(6,861 行)长得到;
`server.py:5811` 只有 `tui_gateway/server.py`(14,006 行)长得到 —— 其余候选最长 2,510 行。
第 10 处是 §2.4 那个镜像歧义,内容判据同样唯一。**所以这 10 处是纯机械补全,零判断。**

*一个必须说清的边界*:前 9 处**写在围栏块里**(r7b 那 8 处在一张 ASCII 流程图内、
r8b 那 1 处在一张对照表内),`verify_citations.py` 跳块,所以**关卡永远不会因为它们变红**。
它们只伤读者,不伤关卡 —— 这正是判据甲存在的理由:**一条不会让任何脚本变红的缺陷,
仍然可以是阻断项。**

**`H-R11C-F-c` —— 正文的标记比项目自己的定案低一级。判据甲命中。**

`chapters/r8d-self-custody.md:328 @ df6d450`

> 代价是这个保护**只在 4 个文件 5 处采用**,而全仓有 60 多个裸 `urlopen` 调用。◇

这里记的是 ◇(代码有、文档无)。而 R9D 就同一个缺口的一个具体后果立了 ■:

`notes/r9d-91-handover-rulings.md:713 @ df6d450`

> | **下游用裸 `urlopen` 而非 `open_credentialed_url`** | **■(本条真正该留下的那一条)** | 跨源 302 把 `billing:manage` 的 Bearer 原样送到新目的地,**与来源无关** |

**读者会被带偏的具体方式**:◇ 读起来是「文档没写而已」,■ 是「已确证的缺陷」。
一个照着第 13 章读的人会以为这只是覆盖率不高,而项目自己已经把它的一个后果定成了
**凭据泄漏**。同一册书里两个等级并存,且低的那个印在正文、高的那个只在底稿。

**清理需要做什么**:片 F 已经给了正确的处置形状,本片同意并原样转述 ——
**升级标记 + 加脚注,但不要直接改 §5 的合计数**(`chapters/r8d-self-custody.md:539` 的
`▲ 12 / ◇ 8 / ■ 10 / ◎ 1` 是「本簇」口径、跨轮可比,动它会污染跨轮指标)。

**`H-R11C-F-d` —— 同一指标两章两口径,两章都没写口径。判据甲命中。**

`chapters/r8d-self-custody.md:328 @ df6d450`

> 代价是这个保护**只在 4 个文件 5 处采用**,而全仓有 60 多个裸 `urlopen` 调用。◇

`chapters/r9c-external-interfaces.md:22 @ df6d450`

> 307/308 语义、防 addheaders 绕过)。全仓 25 个"自拼凭据头 + 标准库发出去"的调用点里,

第 13 章说「5 处 / 60 多」,第 16 章说「2 个 / 25」。**装订成一册后,这两个数会被同一个读者
在同一本书里读到**,而两章都没写自己的分母是什么(一个数的是「裸 `urlopen` 调用点」,
另一个数的是「自拼凭据头 + 标准库发出」的调用点 —— 后者是前者的子集)。
CLAUDE.md 对这个形态有现成的规矩:

`CLAUDE.md:329 @ df6d450`

> - **同一指标多次/多方法测量必须分别标注(R11B 定)**:同一个名字的指标出现两个数时,

**清理需要做什么**:两章各补一句口径(不改数)。这是本册第一例**跨章**的同名指标冲突 ——
散在两轮时谁都不算错,**装订这个动作本身**把它变成了错。

#### (b) 不阻断的 22 条 —— 按「为什么不影响 / 何时变阻断」归三类

| 类 | 条目 | 为什么不影响正文 | 什么条件下变阻断 |
|---|---|---|---|
| **关卡自身的缺陷**(6 条) | `C-a` 内层反引号截断、`C-e` `->` 被读成写重定向、`D-i` 绝对路径被切一刀、`B-d` 子串匹配虚增案号、`A-a` tsv 白名单(已随 `D-a` 一并结清)、`E-f` 制度文件改判不带号故普查报 0 | 它们改变的是**关卡看得见什么**,不改变正文印什么;`chapters/` 现有 479 条引用在现关卡下 `OK=386 / UNCHECKED=93`,无 MISMATCH | 任一轮修这些缺陷时若不做全语料前后对比,可能一次性把 `chapters/` 打红(R10B 立的规矩就是防这个) |
| **历史证据的可重跑性**(6 条) | `C-b` 跨块临时文件、`C-c` R9A 探针从未进版本控制、`C-d` 省略号吃掉脚手架、`C-f` 5 处配对块被手工裁剪、`D-g` 143+105 处未补锚点、`D-h` 对齐表里的省略路径 | 全部在 `notes/`;`chapters/` 的唯一一个 ```` ```verify ```` 块已配对且 `differing=0` | R12 若要复核某条章内断言而回头去跑那些块,会跑不起来 —— 这是判据乙,但需**具体到哪一章的哪一句**才成立,目前未发现 |
| **追踪与方法论**(10 条) | `A-c`/`A-d`、`B-a`/`B-b`/`B-c`/`B-e`、`D-c`/`D-d`、`E-d`/`E-e` | 都是案号、普查口径、派工书模板一类,零字进正文 | `B-a`(C40 一族建议合成一节)与 `A-c`(`▲-H-2` 号形)是 R12 **执行清单**的输入,不是阻断项;把它们当阻断会让清单和账本各存一份,正是「结清的单一落点」要防的 |

*两条需要单独说明的*:
- **`D-c`(「解析成功」可以是假保证)在 `chapters/` 里有 26 处同形态**(裸 `AGENTS.md` /
  `README.md` / `cli.py`,均能从基线根解析、但别处还有同名)。它们**不违反硬标准 8**
  —— 该标准明写「除非该文件真的就在基线仓库根」,这三个都在根上。抽验
  `chapters/r4-execution-environments.md:266` 的 `README.md:29`,指向的正是根 README
  第 29 行那句 "Seven terminal backends",**指对了**。故不阻断。
  **何时变阻断**:R12 若新增裸名锚点而不核根遮蔽,或基线根文件被别处同名文件替换(基线不动,故实际不会)。
- **`B-e`(`■-24` 与 `◇6` 前半重合)**:这两个**片内编号**在 `chapters/` 里零命中。
  搜索面 = `chapters/` 全部 21 份 .md 全文,模式 = 字面 `■-24` / `■24` / `◇6` / `◇-6`
  四种写法,不排除任何文件:

```verify
grep -rn -- '■-24\|■24\|◇6\|◇-6' chapters/ | wc -l
```

```text
0
```

  *要说准的一点*:成品章**确实**用记号编号(`▲1`…`▲5`、`◇-2` 之类),只是那是**每章自己的**
  一套局部编号,与 R11C 片 B 讨论的 R8B/M-4 片内号不是同一套。所以不阻断。

---

### 2.16 第 16 条:自引锚点 615 处 / 101 处指向 `chapters/` · **条件阻断**

**现象(主线本轮新发现)。** 基线锚点有 `@ 863e313` 钉死,而指向本仓库自己的锚点没有钉子,
浮在一棵会动的树上;R12 重排 21 章会一起打断。

```verify
python3 data/r11d/probes/blocking_scope_census.py /home/user/hermes-agent | sed -n '/^\[4\]/,+5p'
```

```text
[4] 自引锚点  来源目录 -> 被指向目录
  被指向合计: {'chapters': 101, 'data': 37, 'notes': 198, 'reports': 72, 'reviews': 15, 'scripts': 192}  总计 615
  指向 chapters/ 的,按来源: {'notes': 60, 'reports': 7, 'reviews': 34}
  来源是 chapters/ 的,按目标: {'scripts': 3}
  其中以 scripts/ 开头的,按归属: {'只基线有': 138, '只本仓库有': 54}
  扣掉只在基线里的 scripts/ 后,真自引 = 477
```

**判定分三层,结论不一样:**

**(1) 101 处指向 `chapters/` 的锚点 —— 不阻断正文。** 按来源看,`notes` 60 / `reviews` 34 /
`reports` 7,**来源里没有 `chapters/`**。也就是说《设计蓝图》正文**不含任何一条指向本书自己
某一行**的锚点,R12 重排后正文里不会印出一个失效地址。判据甲不中;判据丙也不中 ——
`reviews/` 与历史 `notes/` `reports/` 不在关卡强制范围内。

**(2) 判据乙**:R12 分批改章时,先改的那批会让 `notes/` 里指向它的锚点当场漂,
而作者接着读 `notes/` 找下一批的证据 —— **这是真的会让作者找错行**。
但它有一个现成、零成本的解:CLAUDE.md 本轮已立 commit 钉子,
**R12 只要在动章之前把这 101 处补上 `@ <改动前的 sha>`,漂移就不会发生**
(补钉子不改「指向谁」,与锚点寻址补全同型)。所以本片判它**不阻断**,
但列为 R12 的**开工第一件事**,而不是收尾项。

**(3) `chapters/` 内 8 处跨章文件名引用 —— 条件阻断,判据甲。**
这一类**不带行号**,所以上面那个普查看不见它们:

```verify
python3 data/r11d/probes/blocking_scope_census.py /home/user/hermes-agent | grep -E '^\[5\]|^\[6\]'
```

```text
[5] chapters/ 内跨章裸文件名引用(不带行号):8 处 / 6 个被引文件
[6] 案号:宽口径不同号 355;移交普查正则可见 178;看不见 177 个不同号 / 276 次出现
```

```verify
grep -roE 'chapters/[A-Za-z0-9_.-]+\.md' chapters/*.md | awk -F: '$1 != $2' | sort | uniq -c | sort -rn
```

```text
      1 chapters/r9d-tool-surface-and-guard-placement.md:chapters/r9c-external-interfaces.md
      1 chapters/r8d-self-custody.md:chapters/r8c-dashboard-and-web.md
      1 chapters/r8d-self-custody.md:chapters/r8b-cli-trunk-and-interaction.md
      1 chapters/r8d-self-custody.md:chapters/r8a-configuration-surface.md
      1 chapters/r8a-configuration-surface.md:chapters/r8b-cli-trunk-and-interaction.md
      1 chapters/r7b-platform-integration.md:chapters/r7-gateway-session-core.md
      1 chapters/r11b-the-unwritten-layer.md:chapters/r8b-cli-trunk-and-interaction.md
      1 chapters/r11b-the-unwritten-layer.md:chapters/r7b-platform-integration.md
```

这 8 处是正文里读者会点的路标(如「平台接驳的主干在第八章 `chapters/r7b-platform-integration.md`」)。
**只要 R12 改章文件名或合并章文件,它们就指向不存在的文件,而且印在正文里。**
若 R12 保留全部 21 个文件名,则它们不受影响 —— 故判**条件阻断**。

**一条对 615 这个数的更正(本片新查,主线已采纳)。** `scripts/` 是**基线与本仓库都有**的
顶层目录(基线 73 个文件),而原普查按**前缀**判自引,于是 `scripts/run_tests.sh:12` 这类
**基线锚点**被算进了自引。上面第 5 行:`只基线有: 138`。
**真自引 = 615 − 138 = 477。** 这不改变 101 那个关键数(基线没有 `chapters/` 目录,
不可能掺进来),但 615 作为「R12 会打断多少」的规模感是**虚高 29%** 的。
主线已把判据从「前缀」改成「解析结果」:

`data/r11d/probes/self_citation_census.py:39`

```
    return (STUDY / p).is_file() and not (REPO / p).is_file()
```

**两个探针为什么给出不同的数,必须说清口径(CLAUDE.md「同一指标多次/多方法测量必须分别标注」)。**
本节引用的 615 / 101 是**本片探针**的读数:判据 = 前缀(故含 138 处基线 `scripts/`),
语料 = **钉在 `df6d450`**。主线修正后的探针在**工作树**上会报出更大的数
(指向 `chapters/` 的从 101 涨到 107),而涨的那几处**正是本轮几份在写的底稿里
新写的 `chapters/…:行号` 锚点** —— 包括本文件自己。
**这是「搜过没有」那条规矩说的不幂等在自引锚点上的同一形态**:
写一份「R12 会打断多少条自引锚点」的报告,这个动作本身就会把那个数抬高。
判定不受影响(101 与 107 都是「零处在 `chapters/` 内」),但**引用这个数时必须带上口径与时点**。

---

## 3. 独立核实:主线声称已结清的 6 条

**方法**:不读主线的结论,只跑关卡、只读文件。六条里 **5 条核实通过**,
**1 条(`H-R11C-F-a`)通过了它声称的那一半,但另一半未处置**(§2.6 已展开)。

### 3.1 `H-R11C-F-a`(章号重号)—— **通过一半**

```verify
python3 scripts/verify_chapter_order.py
```

```text
chapters=21  重号=0  未编号=0
正文章号提及:一致=1  未点名文件(不猜)=4  非 chapters/ 的不一致=0(记 ADVISORY,不改退出码)
OK: 章号无重号、与磁盘双射、连续,且成品章正文引用与落点表一致
```

`重号=0  未编号=0`,双射与连续都过。就地核对被修的那一行:

`chapters/r11b-the-unwritten-layer.md:255 @ df6d450`

> - 平台接驳的主干在第八章 `chapters/r7b-platform-integration.md`;本章是它的边角补遗。

落点表把第 8 章映到 `chapters/r7b-platform-integration.md`,**一致**;
R11C 记的「第十一章」已不复存在。R11C 那条还说「7 个章号从未被写出来过」——
`data/chapter-order.tsv` 现在给全部 21 章都写了号,这一半也成立。
**未处置的一半 = `未点名文件(不猜)=4`,见 §2.6。**

### 3.2 `H-R11C-E-a`/`-b`(`chapters/r1` 过期数字)—— **通过**

不看主线的说法,直接从台账复算:

```verify
awk -F'\t' 'NR>1{sub(/\r$/,"",$4); l[$4]+=$3; f[$4]++} END{for(k in l) printf "%s\t%d\t%d\n", k, f[k], l[k]}' data/ledger.tsv | sort
```

```text
L1	563	522207
L2	2131	671639
L3	1895	602085
L4	560	55902
LT	3381	756619
```

再读章里现在印的数:

```verify
sed -n '105,106p;131,132p' chapters/r1-what-is-hermes-agent.md
```

```text
| **L1 机制精读** | harness 核心机制,要逐行读透、能凭笔记重实现 | 563 | 522,207 |
| **L2 结构级理解** | 支撑性代码,画得出结构、定位得到功能,不逐行 | 2,131 | 671,639 |
**不**回答"它学过没有"。后者在台账的 `status` 列里,当前仍有 **5,944 个文件 / 1,495,470 行**
停在 `R1-inventoried`(= 只盘点过、没开工),即 8,530 − 5,944 = **2,586 个文件**被真正处理过。
```

逐个对上:L1 563 / 522,207、L2 2,131 / 671,639;`R1-inventoried` 5,944 / 1,495,470;
8,530 − 5,944 = 2,586。R11C 记的 511 / 479,923 与 8,122 / 2,236,870 / 408 **全部不存在了**。

### 3.3 `H-R11C-E-c` + `H-R11C-F-b`(没有关卡覆盖手抄件)—— **通过**

```verify
python3 scripts/verify_derived_numbers.py
```

```text
declared=18  OK=18  STALE=0
OK: every declared derived number matches the ledger
```

关卡存在、可跑、退出码 0,`declared=18` 覆盖 `chapters/r1` 的 4 处声明。
**覆盖面的如实说明见 §2.7**(21 章里只有 1 章写了声明;另有 2 处未声明手抄件,当前值正确)。

### 3.4 `H-R11C-D-a`(白名单漏 ps1/css/tsv)—— **通过**

```verify
grep -n 'CITE_EXTS = ' scripts/verify_citations.py
```

```text
176:CITE_EXTS = "py|mdx|md|yaml|yml|toml|c|h|sh|json|tsx|ts|mjs|js|nix|rs|txt|ps1|css|tsv"
```

三种扩展名都在表上。**顺带结清 `H-R11C-A-a`** —— 那一条要的正是 `tsv`,同一次改动覆盖了。

### 3.5 `H-R11C-D-f`(70 处无人可改)—— **制度侧通过**

`CLAUDE.md:539 @ df6d450`

> **锚点寻址修正是第四类改动,与「行号漂移」同级(R11D 裁定,结清 H-R11C-D-f)。**

裁定给出了判据(「改的是指向谁,还是怎么写地址」)、两个目录各自的程序
(`reports/` 就地补全 + 勘误节点名;`reviews/` 原文不改、另立附录),以及一条硬边界
(「两处都不得顺手改正文的其他任何字」)。**制度锁确已解除**;执行由片 A 本轮进行,
**其完成与否不影响本条判定**(§2.2)。

### 3.6 `H-R11C-M-d`(70% 下限口径)—— **通过**

`CLAUDE.md:193 @ df6d450`

> **分母按语料性质选,下限一律 70% 不下调(R11D 裁定,结清 H-R11C-M-d)。**

裁定里那个「装订轮用 `chapters/` 单独口径、实测 80.6%」的事实前提,本片独立复跑复现:

```verify
python3 scripts/verify_citations.py /home/user/hermes-agent chapters/*.md | sed '/^$/d'
```

```text
citations=479  OK=386  UNCHECKED=93
可校验比例 OK/479 = 80.6%
table_anchors=33  OK=5  UNCHECKED=28   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
OK: every code-block-backed citation matches the baseline
```

**80.6%** 与裁定里写的一致,`citations=479 OK=386` 也一致。**通过。**
*(这条**可以**写成 ```` ```verify ```` 块:它扫的是 `chapters/`,不是本文件,
所以不触发 CLAUDE.md 那条「自校验读数会无限递归」的禁令。§5 里扫本文件的那三条则不行。)*

---

## 4. 移交

**铸号带片标识(CLAUDE.md 案号纪律),一个号只指一个实体。**

| 案号 | 去向 | 锚点 + 摘录 | 一句话现象 |
|---|---|---|---|
| **H-R11D-B-a** | **R12 前置(或任一改普查的轮次)** | `data/r11c/probes/handover_census_r11c.py:53 @ df6d450`:`ID_RE = re.compile(r"H-[A-Za-z0-9]+-[a-z]`(整行见 §2.10 的负控输出) | 移交普查的案号正则**匹配不了三段式片内号**(`H-R11C-D-f` / `H-R11B-A-c` 实测 `[]`),而 CLAUDE.md 案号纪律**要求**片内铸号带片标识、即必然三段。全语料 **177 个不同号 / 276 次出现**对普查完全隐形,比它能看见的 178 个还多;R11C §11.1 那 14 个具名号**一个都不在普查输出里** |
| **H-R11D-B-b** | **R12 装订(重排之前)** | `chapters/r7c-gateway-periphery-and-scheduling.md:262 @ df6d450`:`判据来自 agent 的活动时间戳 —— 和第 7 章讲过的三个看门狗**共用同一口钟**。` | 4 处「第 N 章」**不点名文件**,章序关卡按「不猜」原则记 `未点名文件(不猜)=4`;当前四处指向全部正确,但 R12 重排后没有任何机制会提醒它们过期 —— 与活了六轮的 `r11b:255` 只差「同行有没有写文件名」 |
| **H-R11D-B-c** | **R12 装订(改名/合并时)** | `chapters/r11b-the-unwritten-layer.md:255 @ df6d450`:`- 平台接驳的主干在第八章 ` | `chapters/` 内 **8 处**跨章**裸文件名**引用(不带行号,故自引锚点普查看不见)。R12 一旦重命名或合并章文件,这 8 处在**正文里**指向不存在的文件 |
| **H-R11D-B-d** | **R12 前置** | `reports/round-11c-pre-binding-cleanup.md:467 @ df6d450`:`片 A 4 条 / 片 B 5 条 / 片 C 6 条 / 片 D 其余` | §11.1 最后一行的逐片计数**两种读法都对不上**(实为 A 4 / B 6 / C 6 / D 9 / E 6 / F 4,合计 35,其余 25);它罩着的 25 条里含**全部 3 条正文缺陷**,而叠加 `H-R11D-B-a` 后**没有任何机械清单**兜住它们 |
| **H-R11D-B-e** | **建议下一轮** | `chapters/r10b-desktop-application.md:271 @ df6d450`:`——1,895 个文件 / 602,085 行,没有人说过「知悉用途」交付到什么程度算读过。` | 可复算指标关卡是**声明式**的,21 章里只有 `chapters/r1` 写了声明;这 2 处台账手抄件**当前值正确但无声明**,L3 或全仓总数一变即静默过期 —— 与 `chapters/r1` 那次同型,且关卡同样看不见 |
| **H-R11D-B-f** | **R12 开工第一件事** | `data/r11d/probes/self_citation_census.py:1 @ df6d450`:`#!/usr/bin/env python3` | 101 处指向 `chapters/` 的自引锚点(来源 `notes` 60 / `reviews` 34 / `reports` 7)**没有 commit 钉子**;R12 分批改章时,先改的那批会让作者随后读到的 `notes/` 锚点当场漂。补钉子是零判断动作,但必须**在动章之前**做 |

**一条给主线的更正(不铸号,因为它是对既有数的更正;主线已采纳)**:`self_citation_census.py`
原按前缀判自引,把**基线的** `scripts/`(73 个文件)算了进去,实测 **138 处**;
自引真值 **477**,不是 615。判据现已改为「本仓库解析得到、且基线解析不到」
(`data/r11d/probes/self_citation_census.py:39`)。`chapters/` 那 101 处不受影响 ——
但它在工作树上会随本轮几份在写的底稿一起涨(实测已到 107),引用时必须带口径与时点,见 §2.16。

---

## 5. 自校验读数

按 CLAUDE.md「自校验读数不能写进 ```` ```verify ```` 块」,以下一律贴 ```` ```text ````。

```text
$ python3 scripts/verify_citations.py /home/user/hermes-agent notes/r11d-raw-blocking-rulings.md
citations=28  OK=20  UNCHECKED=8
可校验比例 OK/28 = 71.4%
table_anchors=12  OK=10  UNCHECKED=2   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
OK: every code-block-backed citation matches the baseline
退出码 0

$ python3 scripts/verify_evidence_commands.py notes/r11d-raw-blocking-rulings.md
verify-blocks paired=21  unpaired=0  differing=0  timedout=0
runnability   ran=0  runfail=0  skipped-mutating=0
OK: every paired ```verify command reproduces its pasted output
退出码 0

$ git -C /home/user/hermes-agent status --porcelain | wc -l
0
```

**读数怎么读**:`71.4%` 高于 70% 下限(本轮属 CLAUDE.md 说的**元工作轮**口径:分母是当轮 notes,
自引锚点须带 commit 钉子才计分子 —— 本片全部自引锚点都钉了 `@ df6d450`)。
关卡本身在全绿时不单独打印 `MISMATCH=0` 一类的行,上面贴的是**它实际输出的全部内容**,
没有补字;`OK: every code-block-backed citation matches the baseline` 这一句即等价于零失败。

**「搜过没有」类测量的两个读数(CLAUDE.md 定)。** §2.15 的片内案号计数与 §2.16 的
自引锚点普查,判据都是「某个串在语料里出现过没有」,而**本底稿自己要点名全部 16 条**。
本片的处理不是事后剔除,而是**结构上让污染不可能发生**:探针默认把语料**钉在 `df6d450`**
(本轮开工杂项提交),而本文件在那一版里**还不存在**。两个读数:

```text
(a) 钉在 df6d450(默认)                        :看不见 177 个不同号 / 276 次出现
(b) --worktree(剔除本片底稿与本轮报告)         :看不见 192 个不同号 / 537 次出现
(c) --worktree --no-exclude(什么都不剔除)      :看不见 198 个不同号 / 604 次出现
```

(c) − (b) = **6 个不同号 / 67 次出现**,正好是**本文件自己**铸的 6 个号与点的名 ——
这条规矩说的「对『报告它』这个动作不幂等」,在这里是一个可以逐项对上的差额。
(b) − (a) = 15 个号 / 261 次,来自**片 C 的在途底稿**(`data/inflight/r11d-c-*.claim`
仍是 `signal: OPEN`)与本轮报告;它会随那两份文件继续长,所以**正文引用的一律是 (a)**。

*写这条时踩到并修掉的一个坑,值得记下来*:探针第一版在 `--worktree` 下用 `git ls-files` 取语料,
而当轮底稿**尚未 commit、是未跟踪文件**,于是它在「剔除」和「不剔除」两种模式下**都不在语料里**
——两个读数**一字不差**,看起来完美地证明了「没有污染」。**一个恒等的两读数,
说明的不是干净,是没测到。** 改为在 `--worktree` 下直接 glob 文件系统后,差额才显出来。

**表格锚点声明率单独报(CLAUDE.md R11B 定,不并入可校验比例)**:`table_anchors=12  OK=10`,
声明率 **83.3%**。**剩下 2 处为什么校验不了,是一条值得记下来的结构性限制**:
它们的目标行是**中文散文**(`chapters/r9a:430` 的 ▲5 表格行、`chapters/r7c:262`),
而表格锚点的摘录要通过 `cell_tokens` 的 `CODEISH` 一关 ——
该判据**故意**要求摘录长得像代码(带标识符/路径/调用的标点,或有大写字母),
理由与它拒绝「一个反引号里的小写英文词」是同一条:一个在文件里到处都是的散文片段,
找得到也证明不了锚点该指哪。**推论:移交表里指向本仓库散文行的锚点,原理上进不了这道校验。**
本片能配的都配了(10/12),配不上的两处如实留 UNCHECKED,不去造一个假的代码式摘录来凑比例。
*另一条实测经验:表格单元格以 `\|` 分隔,所以**摘录里含管道符的锚点会被切断**,
写成反斜杠转义也一样 —— 本片有三处(`CITE_EXTS`、`ID_RE`、移交表 `H-R11D-B-d`)
因此从 UNCHECKED 变 OK,改法是把摘录截到第一个管道符之前。**同一个坑还会让整行表格多出两列**
(Markdown 按管道符切列),本片收工前逐行核了列数,0 处异常。*

**本片产出**:`notes/r11d-raw-blocking-rulings.md`(本文件)、
`data/r11d/probes/blocking_scope_census.py`(唯一探针 —— 七个读数,判据从 R11C 既有工具
`import`,不另起口径;`--rev` / `--worktree` 两个开关)、
`data/r11d/blocking-scope-census.txt`(默认口径的完整输出快照,正文各 verify 块是它的切片)。
**未新建任何其他文件,未改动任何既有文件。**
**基线只读**:本片全程未执行任何基线代码,唯一涉及基线的命令是 `git ls-files` 与 `wc -l`
(§2.15 的候选长度表),均为只读;仍按纪律核了 porcelain(见上)。

## 完成信号

**片 B 完成。** 任务是「R11C §11.1 那 15 类 + 主线新发现的第 16 条,逐条判定是否阻断装订」,已完成:
**16 行全部出判定**(阻断 4 行 / 已结清 6 行 / 不阻断 6 行),主线声称已结清的 6 条**独立核实
5 条通过、1 条只通过一半**,另铸 6 条移交号并给出 1 条对既有数的更正。
**未改动任何 `chapters/`、`scripts/`、`CLAUDE.md`、台账、基线;未 commit / add / push;
未动 claim 文件;未装任何包。**
