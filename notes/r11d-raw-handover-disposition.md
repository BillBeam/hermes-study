# r11d-raw-handover-disposition · 移交条目逐条处置

> R11D 片 C 底稿(验收项 9)。**先结论表,后论证。**
> 溯源约定:基线锚点 `路径:行号 @ 863e313`;引本仓库自己的文件时,
> 若引的是**后来被有意改掉**的那一版,按 R11D 新立的规矩加 commit 钉子 `@ <sha>`。
> 本底稿刻意**不引 `CLAUDE.md` 与 `scripts/` 的行号**:R11D 开工杂项刚改过这两处
> (`CLAUDE.md` +89 行、`verify_citations.py` 白名单扩容),而片 A 本轮还在改 `reports/`
> —— 往正在动的文件上钉行号,正是本项目反复摔过的那个跤。

---

## 0. 处置口径(四类结论的定义)

派工书要求每条**四选一**。四类的判据写死如下,写进表里的每一格都能对回这四条:

| 结论 | 判据 | 表里必须同时给出 |
|---|---|---|
| **结清** | 该条**诉求的那件事已经做完**(本轮或此前),且能指出做完它的产物 | 产物是什么(文件/裁定/读数) |
| **已被取代** | 该条的内容**被另一条完全覆盖**,继续单独跟踪只会双重记账 | 取代它的案号 |
| **判为不做** | 明确决定不做 | **理由 + 代价**(不做会失去什么) |
| **转 X** | 本轮做不了,交给后续某一轮 | **转给谁 + 为什么现在做不了 + 下一轮第一件事** |

**「续转」这两个字在本底稿里一次都不出现于结论列。** 一条只写「续转」的处置,
等于把「我没读它」写成了一个动作 —— 这正是 R11C 那份词根判据翻车时暴露的东西:
判开闭是人的事,而人如果只写两个字,那件事其实也没做。

**三条口径上的自我约束**,都是本项目已有制度的直接后果:

1. **不用词根判开闭。** 本底稿的所有开闭结论由人给出;探针只负责**发现**与**排队**,
   不改判(`CLAUDE.md` 「机械判据不得用词根去判『开/闭』这类语义」)。
2. **结清写在本轮的处置表里,不写在别处。** 本表表头用**「处置结论」**四个字,
   这是普查认 ruling 的关键词;R11C 实测表头写「处置」时同一张表解析出 **0** 条。
3. **「处置完」不等于「做完」。** 机械口径是「该案最后一次出现在移交表还是定案表」,
   于是**本表一写,这些号在普查里就全部变成 CLOSED,哪怕结论是「转 R12」**。
   这是本轮新铸的 `H-R11D-C-a`(§4),并且本底稿为此**另报一个数**:
   「处置后仍需后续轮做实事的条数」。

---

## 1. 普查前后读数

### 1.1 语料必须先钉住,否则这两个数不可比

本轮有三片并发在写 `reports/` 与 `notes/`,而普查的语料是「全部报告 + 同轮底稿」。
更要命的是:**主线在本轮开工时已经落了 `reports/round-11d-pre-binding-prereq.md`**,
于是 `notes/r11d-*.md`(包括本底稿)**立刻进入语料**。
不钉住语料,同一条命令隔十分钟给出另一个数 —— `CLAUDE.md`「量『之前』的命令不许钉在
会移动的引用上」说的就是这个形状,R11B 记过三次、R11C 又撞五次。

所以本底稿的所有读数都用 `--exclude round-11d` 把本轮整轮排除来取「前读数」,
用同一条 exclude **再显式追加本底稿**来取「后读数」。两条都可重跑。

### 1.2 前读数:同一批文件,三个口径三个数

```verify
cd /home/user/hermes-study && python3 data/r11d/probes/handover_disposition_r11d.py --exclude round-11d --legacy-id 2>&1 | tail -1
```

```text
口径=正则R11C/语料R11C 扫描文件 263 份;总计 97 条,未结清 7 条,另有 3 条入 REVIEW 队列(仍记 CLOSED);认不出表头但含案号的表格行 149 行
```

```verify
cd /home/user/hermes-study && python3 data/r11d/probes/handover_disposition_r11d.py --exclude round-11d 2>&1 | tail -1
```

```text
口径=正则R11D(宽)/语料R11C 扫描文件 263 份;总计 195 条,未结清 104 条,另有 3 条入 REVIEW 队列(仍记 CLOSED);认不出表头但含案号的表格行 229 行
```

```verify
cd /home/user/hermes-study && python3 data/r11d/probes/handover_disposition_r11d.py --exclude round-11d --wide-hints 2>&1 | tail -1
```

```text
口径=正则R11D(宽)/语料R11C 扫描文件 263 份;总计 306 条,未结清 217 条,另有 3 条入 REVIEW 队列(仍记 CLOSED);认不出表头但含案号的表格行 71 行
```

| 口径 | 案号正则 | 移交表表头 | 总条数 | 未结清 | 认不出表头的行 |
|---|---|---|---:|---:|---:|
| **① R11C 原样** | R11C 版 | R11C 版 | 97 | **7** | 149 |
| **② 宽案号正则** | 补片内号 | R11C 版 | 195 | **104** | 229 |
| **③ ② + 宽表头** | 补片内号 | 补「建议…」类 | 306 | **217** | 71 |

**这三行不是三次测量,是三个不同的口径**(`CLAUDE.md`「同一指标多次/多方法测量必须分别标注」)。
① 是 R11C 收口时用的那把尺子;②③ 是本轮为了看清欠账**另配的两把**,理由见 §1.3。

### 1.3 两处让案子从眼前消失的机制(①→②→③ 的差因)

**差因一:案号纪律与普查正则互相打架 —— 整个片内号域对普查不可见(97 → 195)。**

R11B 立的案号纪律要求**片内铸号必须带片标识**(`H-R11C-M-a`、`H-R11B-B1-a`),
而 R11C 普查器认案号的正则是 `H-[A-Za-z0-9]+-[a-z]\b`:吃掉 `R11C` 之后,
下一段是 `-M-a`,`[a-z]` 匹配不到大写的 `M`,**整条正则在这里失配**。
于是每一条**遵守了案号纪律**的片内号,反而**一条都不在账上**。

`data/r11c/probes/handover_census_r11c.py:53`

```
ID_RE = re.compile(r"H-[A-Za-z0-9]+-[a-z]\b|H-R8FIX-[a-z]\b|(?<![\w-])H-\d{1,2}(?![\w-])")
```

这与 R10B 那条「白名单外的锚点不是记 UNCHECKED,是根本不被当成锚点,连分母都进不去」
是同一物种换了个部件 —— 而这一次,**被吞掉的恰好是制度刚刚要求大家去用的那种写法**。

**差因二:移交表的表头认不出,整张表以 UNCLASSIFIED 出现(195 → 306)。**

R11C 认移交表的关键词只有两个:

`data/r11c/probes/handover_census_r11c.py:58`

```
HANDOVER_HINTS = ("去向", "建议轮次")
```

历史上的移交表表头还写过
「建议下一轮做什么」「建议接手方」「建议动作」「建议」「移交至」—— 全部认不出。
最刺眼的一例:**R11C 片 C 自己那 6 条移交**,表头是 `| 编号 | 锚点 + 一句话现象 | 建议动作 |`,
于是它们在 R11C 与 R11D 的默认普查里**都不存在**。

`notes/r11c-raw-bad-evidence.md:499`

```
| 编号 | 锚点 + 一句话现象 | 建议动作 |
```

R11C 已经做对了一半(让认不出的表以 UNCLASSIFIED **可见**),本轮做的是另一半:
**逐类判它们是什么**(§3.4),并量出「判进来之后未结清是 217 不是 7」。

### 1.4 后读数

本底稿落盘后,同一条命令(只多追加本文件)给出:

```verify
cd /home/user/hermes-study && python3 data/r11d/probes/handover_disposition_r11d.py --exclude round-11d --add-note notes/r11d-raw-handover-disposition.md 2>&1 | tail -1
```

```text
口径=正则R11D(宽)/语料R11C 扫描文件 264 份;总计 217 条,未结清 0 条,另有 3 条入 REVIEW 队列(仍记 CLOSED);认不出表头但含案号的表格行 229 行
```

```verify
cd /home/user/hermes-study && python3 data/r11d/probes/handover_disposition_r11d.py --exclude round-11d --wide-hints --add-note notes/r11d-raw-handover-disposition.md 2>&1 | tail -1
```

```text
口径=正则R11D(宽)/语料R11C 扫描文件 264 份;总计 320 条,未结清 103 条,另有 3 条入 REVIEW 队列(仍记 CLOSED);认不出表头但含案号的表格行 71 行
```

| 读数 | 前 | 后 | 说明 |
|---|---:|---:|---|
| 扫描文件 | 263 | 264 | 多的一份是本底稿 |
| 总条数(口径②) | 195 | **217** | +22:本表点名的号里有 22 个此前不在语料中 —— `H-R11B-B1-b` / `-c` / `-d` / `-e`(4)、`H-R8D-B-a`…`-g`(7)、`H-R11C-C-a`…`-f`(6)、本轮新铸 3、通用号 `H-4` 与 `H-6`(2) |
| **未结清(口径②)** | **104** | **0** | 104 条全部在本表里有处置结论 |
| 总条数(口径③) | 306 | **320** | 同上 |
| **未结清(口径③)** | **217** | **103** | 减少的 114 条 = 口径② 那 104 条 + 片 C 6 条 + 通用号 4 条;剩下的 103 条本轮**不逐条处置**,见 §2.6 与 `H-R11D-C-b` |
| REVIEW 队列 | 3 | 3 | **没有降到 0**,而且换了两条 —— 见 §2.2 末尾那段:本表自己的两条「结清」被词根命中 |

> **口径② 那个「0」不能读成「都做完了」。** 机械口径只知道「该案最后一次出现在定案表」。
> 本表 140 行里有 **100** 行结论是「转 X」,它们的实事**一件都还没做**。
> 该读的数在下面这个块里,它不是普查给的,是数本表得到的
> (自校验读数按制度贴 ```` ```text ````,不写进 ```` ```verify ```` —— 一个扫本文件的命令会无限递归):

```text
表内 140 行 = 逐条处置 137 条 + 本轮新铸 3 条(新号也各有去向)
按结论分:结清 28 / 已被取代 8 / 判为不做 4 / 转 X 100
其中「转 X」100 行 = 本轮之后仍需有人做实事的条数
```

---

## 2. 处置结论

> §2 的六张表 + §3.2 别名表 + §4 新号表,合计 **140** 行(逐条处置 137 条 + 本轮新铸 3 条)。
> 表头一律用**「处置结论」**四个字(§0 口径 2)。
> 「转 X」一格里必须能读到三件事:**转给谁 / 为什么现在做不了 / 下一轮第一件事**。

### 2.1 A 组:R11C 报告 §11.1「装订前遗留清单」15 条

| 案号 | 一句话现象 | 锚点 | 处置结论 |
|---|---|---|---|
| `H-R11B-d` | 可跑性检查里 C 类「非零退出 + stderr 空」27 块的正当性从未逐条判过 | `data/r11c/probes/runnability_census.py:88`:`silent += 1` | **判为不做**。理由:关卡判据已**明确声明**不对这一类表态(`grep` 零命中常常正是结论本身),逐条判要读 27 段上下文,收益低于同等人力放在装订风险上。**代价说清**:那 27 块的正当性**永远不会被判**,其中若混着一块真坏证据,没有任何关卡会叫。R11C 已作同样判定,本轮把它从「本轮不清理」升为**终判**,不再逐轮重问。若本轮片 B 判其为 R12 阻断项,以片 B 为准 |
| `H-R11C-D-f` | `reports/` 50 处 + `reviews/` 20 处可机械补全的锚点,在两条制度下无人可改 | `notes/r11c-raw-anchor-resolution.md:847`:`本片范围外的 70 处可机械补全锚点` | **结清**。该条诉求是「**主线定策**:是否给锚点补全开一个与行号漂移同级的例外」,策已定:R11D 开工杂项把「锚点寻址修正」定为第四类改动(`reports/` 就地补全 + 勘误节点名;`reviews/` 原文不改、另立附录),见 `CLAUDE.md:539 @ df6d450`:`**锚点寻址修正是第四类改动,与「行号漂移」同级(R11D 裁定,结清 H-R11C-D-f)。**`。执行落在本轮片 A |
| `H-R11C-D-a` | 白名单漏 `ps1`/`css`/`tsv`,16 处能解析的锚点连分母都进不去 | `notes/r11c-raw-anchor-resolution.md:842`:`扩展名白名单漏了` | **结清**。`CITE_EXTS` 已补三种扩展名(§3.7 有可重跑证据),全语料前后对比 citations 18,438 → 18,448 已由主线核过 |
| `H-R11C-D-b` | `website/docs/**` 每份文档在 `zh-Hans` 下都有镜像,裸文档名恒有 ≥2 候选(264 处) | `notes/r11c-raw-anchor-resolution.md:843`:`镜像型歧义` | **转 R12 前置**。转给谁:R12 装订前的锚点收口位。现在做不了:它要定的是**一条写法**(引 `website/docs` 一律写全路径、引中文镜像显式写 `website/i18n/zh-Hans/…`),而写法要改 `CLAUDE.md` 成品章硬标准 8,本片无权;且 264 处的改写与本轮片 A 正在改的 `reports/` 是同一批文件,同轮并发改同一行会互相打断。下一轮第一件事:把那条写法写进硬标准 8,再对 264 处逐处补全路径 |
| `H-R11C-E-c` | 全项目没有任何关卡覆盖「正文里可复算指标的第二份手抄件」 | `notes/r11c-raw-reversal-propagation.md:745`:`立关卡的那一轮` | **结清**。`scripts/verify_derived_numbers.py` 已落地为阻断关卡(声明式 `<!-- derived: … -->`,不嗅探),§3.7 有退出码证据 |
| `H-R11C-F-a` | 章号重号 1 处(r7b 被叫作第十一章)+ 7 个章号从未被写出来过 | `notes/r11c-raw-pre-binding-inventory.md:549`:`成品章正文里的章号重号` | **结清**。`scripts/verify_chapter_order.py` + `data/chapter-order.tsv`(章号唯一落点)已落地;`chapters/r11b-the-unwritten-layer.md:255` 已改为第八章,§3.7 有证据 |
| `H-R11C-F-b` | 「章内数字 vs 本仓库另一份可计算数据」三条机械判据一条都没抓到 | `notes/r11c-raw-pre-binding-inventory.md:550`:`本片最严重的一条` | **已被取代**。与 `H-R11C-E-c` 是同一件事的两个提法,同一个关卡(`verify_derived_numbers.py`)一次落地把两条都覆盖了;继续分开跟踪只会双重记账 |
| `H-R11C-E-a` | `chapters/r1` 分层表 L1/L2 两行是过期手抄件,而同段明写「下表是当前值」 | `notes/r11c-raw-reversal-propagation.md:743`:`否则蓝图第一章印错数` | **结清**。表已改为台账真值(L1 563 / 522,207;L2 2,131 / 671,639),并由 `verify_derived_numbers.py` 持续钉住 |
| `H-R11C-E-b` | 同章 `:118` 推出的「408 个文件被真正处理过」错六倍 | `notes/r11c-raw-reversal-propagation.md:744`:`真值 5,944 / 1,495,470` | **结清**。已改为 2,586,并就地写明原判与撤销理由 |
| `H-R11C-M-a` | 治了症状未治根:发现面扩了,但**铸号**仍无单一落点 | `notes/r11c-90-handover-rulings.md:272`:`落地「铸号落点」的那一轮` | **转 R12 前置(制度)**。转给谁:下一轮的开工杂项(制度位)。现在做不了:入册要改 `CLAUDE.md`,本片无权改。下一轮第一件事:把「片内铸的号必须同时在该轮 `*-9x-*` 移交卷里登记一行」写进 `CLAUDE.md`,并**直接拿本底稿 §2.5 那张 64 条登记表当第一次执行**;本轮 §1.3 差因一给了这条比 R11C 更强的证据 —— 不登记的后果不只是「换个文件名模式又会漏」,而是**遵守案号纪律的写法反而一条都不在账上** |
| `H-R11C-M-b` | 普查的「认不出表头」行可见但未逐行判 | `notes/r11c-90-handover-rulings.md:273`:`普查的 135 行` | **结清**。§3.4 把当前 149 行**逐类判完**(22 个表头 → 该计入移交 137 行 / 该计入定案 14 行 / 正当不计入 8 行),并给出量化后果:判进来后未结清从 7 变 217。逐**类**判是正确粒度 —— 同一个表头下的所有行必然同类 |
| `H-R11C-M-c` | `H-R9B-f`/`H-R11A-d`/`H-R11B-f` 三条同族卡在「本轮不扩共享环境」,已连续两轮不关闭 | `notes/r11c-90-handover-rulings.md:274`:`三条同族移交都卡在` | **转「装 extra 轮」**。转给谁:一次显式安排的环境轮。现在做不了:本容器**无 ffmpeg**(§3.8 实测),而本轮纪律禁止装包/动 venv。下一轮第一件事:先解决 ffmpeg 来源(优先 `pip install imageio-ffmpeg` 取静态二进制,不需要 apt;不行再申请放行 apt),装到位后**同一轮内**连做三条:`H-R9B-f` 的 `.ogg` 编解码实跑、`H-R11A-d` 的平台 extra 全量跑、`H-R11B-f` 的 TTS 转码链路 |
| `H-R11C-M-d` | 70% 可校验比例下限与「元工作片」口径不匹配(R11C 实测 65.9%) | `CLAUDE.md:193 @ df6d450`:`**分母按语料性质选,下限一律 70% 不下调(R11D 裁定,结清 H-R11C-M-d)。**` | **结清**。R11D 开工杂项裁定:分母按语料性质选(内容轮 → 当轮 notes;装订轮 → `chapters/` 单独;元工作轮 → 当轮 notes 且自引锚点须带 commit 钉子才计分子),**下限一律 70% 不下调** |
| `H-R11C-A-b` | R8D 片 B 底稿的 7 条移交用通用号 `H-1`…`H-7`,从未进任何账 | `notes/r11c-raw-id-collisions.md:792`:`R12 前置(必须处理)` | **结清**。本轮按 R11C 给 `H-B1-a…e` 建别名的同一套做法,给这 7 条铸规范别名 `H-R8D-B-a`…`-g` 并登记在案(§3.2 别名表)。实质内容(provider 身份映射)是内容工作,随别名一起转,见 §3.2 每条的去向 |
| `H-R11C-B-f` | 32 组合并的别名表尚未落成可查的索引文件;拿着 `H-7` 走不到卷宗 | `notes/r11c-raw-dedup-82.md:660`:`定别名表的那一轮` | **结清**。该索引**其实已经存在**:`data/r11c/b-dedup-82-index.tsv` 的 `cases` 列就是别名表,实测拿 `H-7` 去查确实能走到 `H-R8FIX-a`(§3.3 可重跑)。移交项写的是「尚未落成」,而落成它的正是同一片自己的产出 —— 这是**本轮唯一一条「写移交的人不知道自己已经做完了」** |

**A 组小计:结清 10 / 已被取代 1 / 判为不做 1 / 转 X 3(共 15 条)。**

### 2.2 B 组:REVIEW 队列 13 条 + 同族 `H-R11B-f`(14 条)

REVIEW 队列是 R11C 那份**翻车的词根判据**留下的产物:它命中的 13 条里 6 条是假阳性
(短语被从它的否定里摘出来,如小节标题「无一『续转』了事」)。R11C 已逐条人工裁决,
本轮**不重开已裁决的 10 条**,只对 R11C 判「仍开着」的那几条给终局处置。

| 案号 | 一句话现象 | 锚点 | 处置结论 |
|---|---|---|---|
| `H-R10E-c` | 词根命中来自小节标题的否定语境,不是真续转 | `notes/r11c-90-handover-rulings.md:224`:`处置原文是「就地判为**误报**」` | **结清**。维持 R11C 人工裁决,本轮只做登记,不重开 |
| `H-R8C-a` | 同上,原文是「判为『已结清,账目未记』」 | `notes/r11c-90-handover-rulings.md:225`:`判为『已结清,账目未记』` | **结清**。同上 |
| `H-R8C-e` | 同上,原文「维持 ■,补全成因」+ 锚点漂移已改正 | `notes/r11c-90-handover-rulings.md:226`:`维持 ■,补全成因` | **结清**。同上 |
| `H-R8C-g` | 同上,原文「结清并加重,新立 ■-R10-01」 | `notes/r11c-90-handover-rulings.md:227`:`结清并加重,新立 ■-R10-01` | **结清**。同上 |
| `H-R9A-a` | 同上,账目问题不是欠账 | `notes/r11c-90-handover-rulings.md:228`:`账目问题不是欠账` | **结清**。同上 |
| `H-R8B-b` | 原文「**关闭**,不再续转」,词根出现在否定里 | `notes/r11c-90-handover-rulings.md:229`:`不再续转` | **结清**。同上 |
| `H-R9B-c` | 原文「**关闭并加重**…不再续转」,同上 | `notes/r11c-90-handover-rulings.md:230`:`关闭并加重` | **结清**。同上 |
| `H-R9A-d` | R11B 核实结清写在 `notes/r9b-90-rulings.md` | `notes/r11c-90-handover-rulings.md:231`:`R11B 核实结清写在` | **结清**。同上 |
| `H-R9A-h` | R11B 核实结清写在 `CLAUDE.md`(第三个存放地) | `notes/r11c-90-handover-rulings.md:232`:`第三个存放地` | **结清**。同上。附注:这条正是「结清落点」制度的由来 |
| `H-R11A-f` | 台账 round 归属两桶分给两个 round 值 | `notes/r11c-90-handover-rulings.md:236`:`R11B 写「不动」,**本轮实际做了**` | **结清**。R11C §2.1 实做,分层零变动 |
| `H-R8D-i` | R8D 把「R12 的前置条件」定为「L1 全部 deep-read」,此后每轮只写「不动」 | `notes/r11c-90-handover-rulings.md:234`:`原文只有两个字` | **结清**。**它设的前置条件已经达成**:台账 563 个 L1 文件里,`status` 仍为 `R1-inventoried` 的是 **0** 个,全部落在某一轮的 `*-deep-read` 上(§3.1 可重跑)。此前四轮之所以只能写「不动」,是因为**没有人去量过这个条件是否已经满足** —— 条件是可计算的,而它被当成了一件要等的事 |
| `H-R11A-d` | 平台 extra 的运行期集合仍未确定,要真装一遍全量跑 | `notes/r11c-90-handover-rulings.md:233`:`本轮守共享环境纪律,未装任何 extra` | **转「装 extra 轮」**。转给谁 / 为什么 / 第一件事:与 `H-R11C-M-c` 同一条,见 A 组该行 |
| `H-R9B-f` | `.ogg` 目标下三处走裸 ffmpeg,未实跑确认编解码 | `notes/r11c-90-handover-rulings.md:235`:`维持推定,不关闭` | **转「装 extra 轮」**。同上 |
| `H-R11B-f` | TTS 转码链路同样卡在无 ffmpeg(不在 13 条内,同族一并处置) | `notes/r11b-90-handover-rulings.md:453`:`tools/tts_tool.py:2703` | **转「装 extra 轮」**。同上。三条同轮做,否则它们会各自被推迟第四次 |
| `H-R9B-a` | 词根命中来自 R9C 报告里的一行续转登记,不是独立铸号(本轮 REVIEW 队列里第 14 条,R11C 的 13 条里没有它) | `notes/r11c-raw-id-collisions.md:1`:`# r11c 底稿 · 片 A` | **结清**。其 CLOSED 是真的:该号的实体已在 R9C 定案,语料里那一行只是登记「它去哪」;词根判据把登记行读成了未结清 |

**B 组小计:结清 12 / 转 X 3(共 15 条)。**

> **本表自己当场触发了同一个陷阱,值得写下来。** 加上本底稿之后重跑普查,
> REVIEW 队列仍有 3 条,其中**两条是本表自己的「结清」被词根命中**:
> `H-R11C-M-b` 命中「未结清」——那三个字出自「未结清从 7 变 217」这句**读数**;
> `H-R8D-i` 命中「不动」——出自「此前四轮之所以只能写『不动』」这句**引述**。
> 两次都是把词从它的否定 / 引述里摘出来,与 R11C 那次翻车**一模一样的形状**。
> 这恰恰证明那条制度是对的:**词根只入队列、不改判**。若当初让它改判,
> 本轮两条刚做完的结清会被自动重新打开。

### 2.3 C 组:机械 OPEN 的 7 条,和它们背后被弄丢的 4 个规范号(11 条)

前读数口径① 的 7 条 OPEN,**一条都不是真的没被处置过** —— 它们是两种账目缺陷的产物:

- `H-B1-a…e`:R11C 已判「建别名并登记在案」,但定案行的第一格**用省略号写范围**
  (形如 `H-R11B-B1-a`…`-e`),而**普查只认到范围里的第一个**,
  于是 `-b`…`-e` 四条留在账上开着;
- 而它们的**规范号** `H-R11B-B1-b`…`-e` 只出现在别名表里,那张表表头是
  `| 规范号 | 历史号 | 立项处 | 一句话现象 |` —— 认不出,**四个规范号一次都没进过账**。
- `H-R10G-a…d` 同一个形状:定案行写 `H-R10G-a`…`-d`,只认到 `-a`。

| 案号 | 一句话现象 | 锚点 | 处置结论 |
|---|---|---|---|
| `H-B1-b` | 历史号(无轮次前缀),R11C 已建别名 | `notes/r11c-90-handover-rulings.md:203`:`H-R11B-B1-b` | **已被取代**。被规范号 `H-R11B-B1-b` 取代;实质处置见下一行 |
| `H-B1-c` | 同上 | `notes/r11c-90-handover-rulings.md:204`:`H-R11B-B1-c` | **已被取代**。被 `H-R11B-B1-c` 取代 |
| `H-B1-d` | 同上 | `notes/r11c-90-handover-rulings.md:205`:`H-R11B-B1-d` | **已被取代**。被 `H-R11B-B1-d` 取代 |
| `H-B1-e` | 同上 | `notes/r11c-90-handover-rulings.md:206`:`H-R11B-B1-e` | **已被取代**。被 `H-R11B-B1-e` 取代 |
| `H-R11B-B1-b` | 全仓可能还有别的手写重定向守卫沿用 `next_request` 判定式,片 B1 没做普查 | `gateway/platforms/yuanbao_media.py:229`:`if response.is_redirect and response.next_request:` | **转 代码缺陷复核轮**。转给谁:R12 之后第一个吃基线内容的轮次。现在做不了:要在全仓找「自己写重定向跟随」的实现并逐个判,是内容工作,本轮是装订前的元工作轮。下一轮第一件事:以 `is_redirect` / `next_request` / `follow_redirects` 三个串在 `gateway/` 与 `tools/` 下做一次普查,再逐个对照共享助手的正确写法 |
| `H-R11B-B1-c` | 环境变量目录会驱动设置向导,而其中至少 `QQ_SANDBOX` 无任何读取方 | `hermes_cli/config_defaults.py:4152`:`"QQ_SANDBOX": {` | **转 配置面普查轮**。转给谁:接手 `data/r8a-env-vars.tsv` 那批资产的轮次。现在做不了:要判「这份目录整体有多少条是死的」,需要对 151 条静态环境变量逐条找读取方,是内容工作。下一轮第一件事:拿 `data/r8a-env-vars.tsv` 当输入,对每个变量名在基线做一次读取方普查,产出「死条目」清单 |
| `H-R11B-B1-d` | 基线里「写进注释的待办」有多少、多久没动,是可量化的地图腐烂指标,没统计 | `gateway/platforms/media_cache.py:33`:`but is intentionally NOT migrated here` | **判为不做**。理由:这是一个**新指标**而不是一条欠账 —— 它不指向任何一个未定的结论,做完只增加一个数。代价:失去一个「地图腐烂程度」的第二观测量(现有的是跨轮 ▲ 计数);若 R12 装订时想要这个数,判据现成(在基线搜 `TODO` / `FIXME` / `intentionally NOT` 类注释并取 blame 年龄) |
| `H-R11B-B1-e` | 片 B1 那 12 个文件的台账 `status` 仍是 `R7B-deep-read`,没反映 R11B 的重读 | `gateway/platforms/media_cache.py:1`:`"""Shared mime↔extension dispatch for inbound (downloaded) platform media.` | **转 下一轮开工杂项**。转给谁:下一轮开工时改台账的那一步。现在做不了:`data/ledger.tsv` 不在本片 claim 里,而本轮另有两片正在拿台账做读数(可复算指标关卡、分层快照 diff),中途改它会让那些读数不可比。下一轮第一件事:把片 B1 的 12 个文件与片 B2 的 26 个文件的 `status` 从 `R7B-deep-read` 等改为 `R11B-deep-read`,改完跑一次 `scripts/verify_ledger.py` 确认分层加总不变 |
| `H-R10G-b` | `/api/memory/providers/{name}/setup` 除 pip 外还会 `shlex.split()` 执行 manifest 里的命令 | `hermes_cli/web_server.py:5468`:`def _install_memory_provider_external_dependencies(` | **转 代码缺陷复核轮**。转给谁:同 `H-R11B-B1-b`。现在做不了:要判这条是不是可利用面,须实跑一次 manifest 安装链路,属内容工作。下一轮第一件事:读 `_install_memory_provider_external_dependencies` 全函数,确认 manifest 来源是否可由非本机用户投喂 |
| `H-R10G-c` | `typecheck` 指向 `files: []` 的 solution tsconfig,疑为空转 | `web/package.json:12`:`    "typecheck": "tsc -p . --noEmit",` | **转 任何能跑前端工具链的一轮**。现在做不了:本容器未装 `web/` 的 node 依赖,而本轮纪律禁止装包。下一轮第一件事:`npm ci` 后分别跑 `npm run typecheck` 与 `tsc -b`,比对两者报出的错误条数 —— 若前者恒为 0 而后者非 0,空转成立 |
| `H-R10G-d` | 插槽三张名单(声明 30 / 实渲染 31 / 文档 28)两两不等 | `web/src/plugins/slots.ts:18`:`/** Slot locations the built-in shell renders. Plugins declaring any of` | **转 R12 装订**。转给谁:R12 处理 ▲ 计数的那一节。现在做不了:三张名单的差集要落成 ▲ 还是 ◇ 取决于「文档少列」算不算矛盾,而记号定义的适用在装订时统一判。下一轮第一件事:把三张名单的差集列成表,逐个按 `CLAUDE.md` 记号定义定档(▲ / ◇ / ◎) |

**C 组小计:已被取代 4 / 判为不做 1 / 转 X 6(共 11 条)。**

### 2.4 D 组:R11C 六片底稿 `## 移交` 节的其余 25 条

R11C 六片加主线共铸 **39** 个片内号(片 A 4 / B 6 / C 6 / D 9 / E 6 / F 4,主线 M 4),
其中 14 条已被 R11C 报告 §11.1 提上去(= A 组),这里处置剩下的 25 条。
**片 C 那 6 条在默认普查里根本不存在**(表头「建议动作」认不出,§1.3 差因二),
本表是它们第一次被写进定案。

| 案号 | 一句话现象 | 锚点 | 处置结论 |
|---|---|---|---|
| `H-R11C-A-a` | `tsv` 不在锚点白名单,指向 `data/ledger.tsv` 的锚点连分母都进不去 | `notes/r11c-raw-id-collisions.md:791`:`R12 前置(制度)` | **已被取代**。与 `H-R11C-D-a` 指同一处 `CITE_EXTS`,同一次修改(补 `ps1` / `css` / `tsv` 三种扩展名)把两条一并解决 |
| `H-R11C-A-c` | 片内定案号写成 `▲-H-2` / `■-H-3`,与移交号 `H-2`/`H-3` 在纯文本里无法区分 | `notes/r11c-raw-id-collisions.md:793`:`片内定案号写成` | **转 R12 装订**。转给谁:R12 统一记号与案号的那一步。现在做不了:改写记号会动 `notes/r10b-raw-capability-panels.md` 的正文,而该文件不在本片 claim 里,本轮另有片在并发改历史产出。下一轮第一件事:把该文件里的 `▲-H-2`/`■-H-3` 改写为 `▲-R10B-H-2` 形式,再重跑 R11C 的撞号普查确认那 3 个被污染实体消失 |
| `H-R11C-A-d` | 「某案子被处置过没有」这类测量会被上一轮的普查清单污染 | `notes/r11c-raw-id-collisions.md:794`:`R12 前置(方法论)` | **已被取代**。诉求(「必须报剔除与不剔除两个读数」)已是 `CLAUDE.md` 的在册条款(R11B 定,结清 `H-R9D-e` + `H-R10B-b`);本轮 §3.5 就是一次执行,不需要第二个案号跟踪同一条规矩 |
| `H-R11C-B-a` | C40 一族三条独立定案是同一形态在三个子系统各犯一次,R12 应合成一节 | `notes/r11c-raw-dedup-82.md:655`:`同一形态在三个子系统各犯一次` | **转 R12 装订**。转给谁:R12 的跨章合并位。现在做不了:合并是写作决定,要在三章都在手上时做。下一轮第一件事:把 `sticker_cache`(R7C ◇-4)、`DebugSession`(R9D ■-6)、`HOOKS_DIR`(R7C ◇3)三处放进同一节,以「同一形态三次复发」开场 |
| `H-R11C-B-b` | R9A `◇-5` 与 R7C `◇-5` 同号不同实体,撞号普查漏网一例 | `notes/r11c-raw-dedup-82.md:656`:`第二物种漏网一例` | **转 R12 前置(撞号收口)**。转给谁:下一次做撞号普查的位置。现在做不了:要给其中一个改号并回改所有引用点,属跨文件改写,本片 claim 只覆盖本底稿。下一轮第一件事:把这两条与 `H-R11C-B-c` 一起纳入 R11C 片 A 那份 100 实体清单重跑一次,确认「第二物种」(同号不同实体且都在同一文件邻近)一个不漏 |
| `H-R11C-B-c` | R9C `■-7` 与 R9D `■-7` 同号不同实体,漏网二例 | `notes/r11c-raw-dedup-82.md:657`:`第二物种漏网二例` | **转 R12 前置(撞号收口)**。同上,与 `H-R11C-B-b` 同一次做 |
| `H-R11C-B-d` | `rulings_census.py` 的 `is_decl()` 用子串匹配判声明位,案号总数偏高 | `notes/r11c-raw-dedup-82.md:658`:`改探针的那一轮` | **转 改探针的那一轮**。转给谁:下一次动 `data/r11b/probes/rulings_census.py` 的位置。现在做不了:该探针在 `data/r11b/` 下,是历史轮次的资产,本片纪律不改他轮探针。下一轮第一件事:把 `is_decl()` 的子串匹配换成带边界的正则,重跑并与旧读数逐条 diff —— 预期方向是**案号总数下降**,凡上升的都是新 bug |
| `H-R11C-B-e` | C16 的 `■-24` 与 M-4 的 `◇6` 前半重合、后半不重合,是 32 组之外唯一需要人再看一眼的边界情形 | `notes/r11c-raw-dedup-82.md:659`:`前半重合、后半不重合` | **转 R12 装订**。转给谁:R12 决定这两条是否并成一节的写作位。现在做不了:判「前半重合」算不算同一条,取决于装订时那一节讲什么。下一轮第一件事:把 `■-24`(GUI 无恢复提示)与 `◇6`(硬编码新版路径)两段原文并排读一遍,再决定合并还是交叉引用 |
| `H-R11C-C-a` | `NOFENCE` 遇到块内字面三反引号会把块截断,一个本来配对的块被记成未配对 | `notes/r11c-raw-bad-evidence.md:501`:`会把块截断在那里` | **转 下一个动 `scripts/` 的轮次**。现在做不了:要改 `scripts/verify_evidence_commands.py`,本片无权改 `scripts/`。下一轮第一件事:给 `NOFENCE` 加「闭栏必须独占一行」的约束,改前先在全语料量一遍会新增多少 unpaired |
| `H-R11C-C-b` | 生产者块带 `tee` 被判 MUTATING 永不跑,消费块每次都跑,必然 `FileNotFoundError` | `notes/r11c-raw-bad-evidence.md:502`:`消费块每次都跑` | **转 下一轮派工书**。现在做不了:病灶本身 R11C 已修(消费块改成自足),残留的诉求是「把『证据块不得依赖另一个块产生的文件』写进派工书」,而派工书由主线派发时写,不是底稿能落的。下一轮第一件事:派工书加这一条,并在 `data/inflight/README.md` 同步一句 |
| `H-R11C-C-c` | R9A 五个场景探针的脚本从未进过版本控制,读数在新容器里不可重跑 | `notes/r11c-raw-bad-evidence.md:503`:`脚本从未进过版本控制` | **转 需要复用 ■-R9A-01 / ■-R9A-02 的那一轮**(条件触发)。现在做不了:重写五个 env-loader 场景探针是内容工作,而本轮没有任何结论依赖它们。下一轮(指真要用这两条定案的那一轮)第一件事:先重写探针跑出读数,再决定这两条定案维持还是改判;在那之前现有读数只能当线索 |
| `H-R11C-C-d` | 证据块里的省略号吃掉了产生输出的 `print` 与脚手架,重建必须猜 | `notes/r11c-raw-bad-evidence.md:504`:`省略号吃掉的不只是前言` | **转 下一轮制度位**。现在做不了:诉求是立一条规则(「证据块里的省略号只能省已在同一份底稿别处逐字写过的部分」),入册要改 `CLAUDE.md`。下一轮第一件事:把该句写进「shell 命令即证据」那一条之下,并量一遍全语料有多少 verify 块含省略号 |
| `H-R11C-C-e` | 输出里一个 `->` 被 `REDIRECT_WRITE` 读成写重定向,整块判 MUTATING 永不执行 | `notes/r11c-raw-bad-evidence.md:505`:`整块判 MUTATING` | **转 下一个动 `scripts/` 的轮次**。现在做不了:同 `H-R11C-C-a`。下一轮第一件事:给 `REDIRECT_WRITE` 排除 `->`,**改之前先量一遍全语料会新增多少 RUNFAIL**,按 R7C→R8A 那套分期落地 |
| `H-R11C-C-f` | 5 处**配对块**漂移(命令与贴出的输出对不上),不在片 C 的 55 口径内 | `notes/r11c-raw-bad-evidence.md:506`:`贴 3 行、实跑 37 行` | **转 下一轮证据清理位**。现在做不了:5 处分散在 5 份历史底稿里,而本片 claim 只覆盖本底稿;并发改历史 notes 是 R11C 明确记过的翻车形状。下一轮第一件事:对这 5 处逐个重跑其 verify 块,把实跑输出原样贴回 text 块(注意其中 `lib-themes:1831` 是**配对的死路径块**,要先修路径) |
| `H-R11C-D-c` | 「解析成功」是假保证:1,543 处裸锚点解析到仓库根同名文件,而这些名字在树的别处也有 | `notes/r11c-raw-anchor-resolution.md:844`:`「解析成功」是假保证` | **转 下一个动 `scripts/` 的轮次**。现在做不了:要给关卡加一档非阻断提示(basename 在基线里 >1 个时打印「疑似根遮蔽」),判据现成但落在 `scripts/`。下一轮第一件事:把 `data/r11c/d-anchor-resolution-rootshadow.py` 的判据收进 `verify_citations.py`,并按 R8C 的先例先只报数 |
| `H-R11C-D-d` | 859 处同名歧义一处没猜,其中 103 处已被长度判据定到唯一候选 | `notes/r11c-raw-anchor-resolution.md:845`:`859 处同名歧义一处没猜` | **转 R12 前置(锚点收口)**。现在做不了:103 处需人工过一眼,519 处需按小节上下文批处理,工作量与本轮验收项冲突。下一轮第一件事:先做那 103 处(长度已定,只欠一眼确认),明细在 `data/r11c/d-anchor-resolution-fix2-left.tsv` |
| `H-R11C-D-e` | 成品章 10 处违反硬标准 8(写了裸文件名) | `notes/r11c-raw-anchor-resolution.md:846`:`成品章 10 处违反硬标准 8` | **转 R12 装订**。现在做不了:`chapters/` 不在本片 claim 里,且本轮已有裁定「装订轮用 `chapters/` 单独口径」,改动统一放在装订。下一轮第一件事:前 9 处照抄 R11C §3.5 那张长度判据表补全路径;第 10 处等 `H-R11C-D-b` 的写法定下来 |
| `H-R11C-D-g` | 片 C 的 31 份里还有 143 处可机械补全锚点,另有 105 处在围栏/引用块内 | `notes/r11c-raw-anchor-resolution.md:848`:`片 C 的 31 份里还有 143 处` | **转 R12 前置(锚点收口)**。现在做不了:143 处可直接跑 `data/r11c/d-anchor-resolution-fix.py`,但那 31 份是历史 `notes/`,与本轮片 A 的改动面相邻;块内 105 处需逐块判「逐字摘录还是笔记自己的话」,不可批处理。下一轮第一件事:先跑那 143 处的脚本(判据与片 D 相同),块内 105 处单列一批人工过 |
| `H-R11C-D-h` | 3 处省略中段的路径写在手工列宽对齐的 ```text 表里,补全会破坏对齐 | `notes/r11c-raw-anchor-resolution.md:849`:`补全会破坏对齐` | **转 R12 装订**。现在做不了:要么整表重排、要么改成 markdown 表格,都是对历史底稿的格式改写,本片不碰。下一轮第一件事:把 `notes/r9a-h-r8d-ef-surveys.md` 那张对齐表改成 markdown 表格,顺手把三处真实路径写全(路径已查明) |
| `H-R11C-D-i` | `vc.citations()` 无左侧 lookbehind,绝对路径被从中间切一刀(全语料 12 处) | `notes/r11c-raw-anchor-resolution.md:850`:`无左侧 lookbehind` | **转 下一个动 `scripts/` 的轮次**。现在做不了:要改 `CITE` 正则并新增 `ABSOLUTE` 一档,落在 `scripts/`。下一轮第一件事:给 `CITE` 加与 `CITE_EXTLESS` 同款的 lookbehind,并把以 `/` 开头的锚点单列一档(计入分母、不阻断) |
| `H-R11C-E-d` | R8C 已推翻的「静默抹掉」定性被写进了派工书模板,且那半句是掉了不是被改正 | `notes/r11c-raw-reversal-propagation.md:746`:`接手派工书模板的那一轮` | **转 下一轮派工书**。与 `H-R11C-C-b` 同一次做。现在做不了:派工书模板由主线派发时写。下一轮第一件事:在 `data/r10/dispatch-brief.md` 那段就地写明「R8C 已推翻『静默』定性」,而不是把半句删掉 —— 删掉正是它会复发的原因 |
| `H-R11C-E-e` | `notes/r11b-raw-rulings-census.md:783` 表内锚点 `:700` 的真实位置是 `:730`,差 30 行 | `notes/r11c-raw-reversal-propagation.md:747`:`修锚点的那一轮` | **转 下一轮 notes 锚点位**。现在做不了:要改的是 `notes/r11b-raw-rulings-census.md`,不在本片 claim 里(本轮片 A 的面是 `reports/` 与 `reviews/`)。下一轮第一件事:把该处 `:700` 改成 `:730`,**并给它补一个声明式摘录** —— 它至今记 TABLE-UNCHECKED,不补摘录的话改完仍然没有任何校验读它 |
| `H-R11C-E-f` | 定案级改判行普查在 `CLAUDE.md` 上报 0 行,而那里确有一条改判(制度文件的改判不带号) | `notes/r11c-raw-reversal-propagation.md:748`:`下一次做同类普查的那一轮` | **转 下一次做同类普查的那一轮**。现在做不了:判据要求改判行带案号或记号,而制度文件的改判天然不带号;放宽判据要先量误吞。下一轮第一件事:给判据加一条「`CLAUDE.md` 里以『**Rxx 更正**』开头的引用块一律计入」,并前后对比全语料读数 |
| `H-R11C-F-c` | 第 13 章把 `urllib_security` 的覆盖缺口记 ◇,而 R9D 已就同一处新立 ■ | `notes/r11c-raw-pre-binding-inventory.md:551`:`R12 装订时升级标记` | **转 R12 装订**。现在做不了:`chapters/` 不在本片 claim 里,且升级记号会改动第 13 章 §5 的合计行,而那是跨轮可比口径。下一轮第一件事:把该处 ◇ 升为 ■ 并**加脚注说明**,不直接改 §5 合计数 |
| `H-R11C-F-d` | 同一个「`urllib_security` 采纳率」被两章用两种口径各报一次,两章都没写口径 | `notes/r11c-raw-pre-binding-inventory.md:552`:`R12 补口径或统一` | **转 R12 装订**。现在做不了:同上,要改两章正文。下一轮第一件事:给两处各补一句口径(第 13 章「4 个文件 5 处采用 / 60 多个裸调用点」,第 16 章「25 个自拼凭据头的调用点里 2 个」),这是 `CLAUDE.md`「同一指标多次/多方法测量必须分别标注」在**跨章**场景下的第一例 |

**D 组小计:已被取代 2 / 转 X 23(共 25 条)。**

### 2.5 E 组:从未进过任何账的 64 条(R9D 片内 45 + R11B 片内 19)

**这一组是本轮最重的发现,它不在派工书点名的范围里。** 派工书给的范围是
「未结清 16 条 + REVIEW 13 条 + R11C 各片移交」;把案号正则放宽到能认出**片内号**
之后,另有 64 条从未在任何一次移交普查里出现过 —— 它们**全部遵守了案号纪律**
(带片标识),而正是这一点让 R11C 的正则认不出它们(§1.3 差因一)。

规模对照:`H-R11C-A-b` 当初把「R8D 7 条通用号从未进账」称作
「规模是 `H-R10B-a` 的 3.5 倍」;**这 64 条是它的 9 倍**。

而且它们**并不是格式不合规**。以 R9D 片 A 那张表为例,表头用的正是普查认识的
「建议轮次」,四列俱全 —— 唯一「不合规」的地方,是它的编号遵守了案号纪律:

`notes/r9d-raw-lsp.md:1887`

```
| 编号 | 锚点 | 一句话现象 | 建议轮次 |
```

**R9D 那 45 条的去向,写的都是已经过去的轮次。** 45 条里绝大多数写「R10 缺陷汇总」
「R10 网关片」「下一轮安全面复核」,而 R10 / R10B / R11A / R11B / R11C 五轮都已结束。
点名覆盖率(两个读数,§3.5):**剔除本轮承载清单后,45 条里 39 条在铸号文件之外零命中**。

#### 组级三问(对下面 41 条「转 代码缺陷复核轮」的行逐字适用)

- **转给谁**:R12 装订之后第一个**吃基线内容**的轮次(代码缺陷复核位)。
- **为什么现在做不了**:R11D 是装订前的**元工作轮**,不吃内容;这 41 条每条都要读基线
  代码、多数还要实跑复现(LSP 需要装语言服务器、file-io 需要 Docker、kanban 需要多租户脚手架),
  与本轮「不装包、不动 venv、基线只读」的纪律直接冲突。
- **下一轮第一件事**:每条铸号行都自带一个复现编号(`实跑 P6`、`见 §4 ■2`……),
  **先按那个编号把复现跑通**,跑不通的先判「是复现坏了还是结论坏了」,再谈修法。
  这一步不能跳:R9D 的复现脚本有一部分从未进版本控制(见 `H-R11C-C-c`)。

| 案号 | 一句话现象 | 锚点 | 处置结论 | 铸号位 |
|---|---|---|---|---|
| `H-R9D-A-a` | 外层预算不随 `wait_mode` 走,`full` 模式下 8s < 内层 10s,基线快照必超时并把 `(server, root)` 永久标 broken(实跑 P6) | `agent/lsp/manager.py:313`:`t = max(8.0, self._wait_timeout + 3.0)` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-lsp.md:1889`:`H-R9D-A-a` |
| `H-R9D-A-b` | 服务器拒绝 pull 时该循环空转,2s 发 6855 次请求(实跑 P7) | `agent/lsp/client.py:894`:`pull_task = asyncio.create_task(self._pull_document_diagnostics(abs_path))` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-lsp.md:1890`:`H-R9D-A-b` |
| `H-R9D-A-c` | 用 git 根查按逐服务器根建的客户端池,marker 在子目录时必空,基线滚动静默失效(实跑 P8) | `agent/lsp/manager.py:530`:`client = self._clients.get((srv.server_id, ws))` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-lsp.md:1891`:`H-R9D-A-c` |
| `H-R9D-A-d` | 「非 git 目录」被永久负缓存,文档教的 `git init` 在本进程内无效(实跑 P2) | `agent/lsp/workspace.py:87`:`_workspace_cache[str(start_path)] = (None, False)` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-lsp.md:1892`:`H-R9D-A-d` |
| `H-R9D-A-e` | `hermes lsp which` 漏了 `_recipe_pkg_for` 别名映射,与 `status` 对同一服务器给出相反答案(实跑 P5) | `agent/lsp/cli.py:252`:`recipe = INSTALL_RECIPES.get(server_id)` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-lsp.md:1893`:`H-R9D-A-e` |
| `H-R9D-A-f` | 外层取消抛的 `CancelledError` 不被捕获,`_cleanup_process()` 不跑,语言服务器进程泄漏(实跑 P10) | `agent/lsp/client.py:278`:`except Exception:` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-lsp.md:1894`:`H-R9D-A-f` |
| `H-R9D-A-g` | ceiling 差一层,项目根可以解析到 git 工作树之外(实跑 P1) | `agent/lsp/servers.py:209`:`ceiling=os.path.dirname(workspace) if workspace else None,` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-lsp.md:1895`:`H-R9D-A-g` |
| `H-R9D-A-h` | 同步 `subprocess.run(timeout=300)` 跑在 LSP 后台事件循环上,而外层只有 8s ——**推定**首次自动安装必然把服务器打成 broken,需 | `agent/lsp/install.py:238`:`bin_path = try_install("pyright", ctx.install_strategy)` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-lsp.md:1896`:`H-R9D-A-h` |
| `H-R9D-B-a` | `patch` 无读禁、无脱敏,返回的 unified diff 把 `auth.json` / 项目 `.env` 的明文密钥原样交给模型(实跑复现,见 ■-3) | `tools/file_operations.py:1782`:`diff = self._unified_diff(content, new_content, path)` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-file-io-safety.md:1705`:`H-R9D-B-a` |
| `H-R9D-B-c` | 写禁清单里没有 `auth.json`,`write_file` 可整体覆盖主凭据库;而 `website/docs/user-guide/security.md` 的 “Pr | `agent/file_safety.py:50`:`str(hermes_home / "cache" / "bws_cache.enc.json"),` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-file-io-safety.md:1707`:`H-R9D-B-c` |
| `H-R9D-B-d` | 单引号内的 `\"` 是字面量,trap 触发时 `rm` 删的是一个名字带引号的路径,临时文件从不被清理(最小 bash 复现见 ■-4) | `tools/file_operations.py:1071`:`"trap 'rm -f \\\"$tmp\\\"' EXIT; "` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-file-io-safety.md:1708`:`H-R9D-B-d` |
| `H-R9D-B-e` | sha256 写后校验"验证不了"与"验证通过"输出相同,于是 `write_file` 指向已存在目录时报成功、内容落进目录里的隐藏 `.hermes-tmp.*`(实跑复现 | `tools/file_operations.py:1612`:`if hash_result.exit_code == 0 and hash_result.stdout.strip():` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-file-io-safety.md:1709`:`H-R9D-B-e` |
| `H-R9D-B-f` | `total_lines` 来自 `wc -l`(数换行符),无尾换行文件少 1,于是边界情形下末行被静默丢弃且 `truncated=False`(实跑复现,见 ■-7) | `tools/file_operations.py:1227`:`truncated = total_lines > end_line` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-file-io-safety.md:1710`:`H-R9D-B-f` |
| `H-R9D-B-h` | 模块级写禁快照零消费者,且 `_HOME` 在 import 时求值、不认 HERMES_HOME/profile(全仓搜索见 ◇-2) | `tools/file_operations.py:52`:`WRITE_DENIED_PATHS = build_write_denied_paths(_HOME)` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-file-io-safety.md:1712`:`H-R9D-B-h` |
| `H-R9D-B-b` | 同类的 `cache/op_cache.json`(1Password 明文值)不在任何守卫表里,且因此可被 skill 声明式挂进沙箱(实跑复现,见 ■-2) | `agent/file_safety.py:284`:`os.path.join("cache", "bws_cache.json"),` | **已被取代**。R9D 自陈「结清 R9C D 片 ■-1 在本片的部分」,R11B 片 A 的 `H-R11B-A-g` 已认定 R9C `■-1` 与 R9D `■-2` 是同一条;单独跟踪即双重记账 | 铸于 `notes/r9d-raw-file-io-safety.md:1706`:`H-R9D-B-b` |
| `H-R9D-B-g` | 容器后端不做 `resolve()` 而读禁判定在宿主 `resolve()`,推定容器内软链可绕过读禁 —— **未取证**,需要 Docker 环境 | `tools/file_tools.py:374`:`container_paths = _uses_container_paths(task_id)` | **转 有容器环境的轮次**。转给谁:能起 Docker 后端的那一轮。为什么现在做不了:结论是**推定**(容器内软链绕过读禁),证实它必须在容器里造软链实跑,本容器没有 Docker。第一件事:起一个容器后端任务,在容器内建指向宿主读禁路径的软链,调 `read_file` 看是否穿透 | 铸于 `notes/r9d-raw-file-io-safety.md:1711`:`H-R9D-B-g` |
| `H-R9D-C-a` | `no_agent` 脚本执行路径上 `cron/*.py` 里零个审批调用,`approvals.cron_mode: deny` 对它无效;模型写脚本进 `~/.herme | `cron/scheduler.py:2288`:`# choice explicit here keeps the allowed surface small and auditable.` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-kanban-todo-cron.md:1582`:`H-R9D-C-a` |
| `H-R9D-C-b` | `_handle_link` 缺 `_enforce_worker_task_ownership`,worker 实测可把外国租户的 `ready` 卡降级为 `todo` 并 | `tools/kanban_tools.py:1510`:`"""Add a parent→child dependency edge after the fact."""` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-kanban-todo-cron.md:1583`:`H-R9D-C-b` |
| `H-R9D-C-c` | 只看终态工具**调用过**不看**成功过**,一次被判官驳回的 `kanban_complete` 就永久关掉守卫(见 §4 ■1) | `agent/kanban_stop.py:62`:`name = str(msg.get("name") or "")` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-kanban-todo-cron.md:1584`:`H-R9D-C-c` |
| `H-R9D-C-d` | 同一个 lambda 里 `attach_to_session` 未转发,schema 承诺与行为不一致(见 §4 ■6) | `tools/cronjob_tools.py:1181`:`script=args.get("script"),` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-kanban-todo-cron.md:1585`:`H-R9D-C-d` |
| `H-R9D-C-e` | 全仓唯一只认 env、不认 `is_dispatcher_owned_worker` ContextVar 的看板消费者(见 §4 ■3) | `agent/kanban_stop.py:34`:`task = (os.environ.get("HERMES_KANBAN_TASK") or "").strip()` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-kanban-todo-cron.md:1586`:`H-R9D-C-e` |
| `H-R9D-C-f` | 多条缺 id 的待办折叠成一条,静默丢计划(见 §4 ■4) | `tools/todo_tool.py:199`:`item_id = str(item.get("id", "")).strip() or "?"` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-kanban-todo-cron.md:1587`:`H-R9D-C-f` |
| `H-R9D-D-a` | 该 NOTE 声称模型不能自主外发,但 `cronjob` 的 `deliver` 是模型可写的自由目标字符串,经  直通同一引擎;需要一轮把 cron 片与本片合起来定案这条 | `tools/send_message_tool.py:2106`:`# NOTE: ` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-messaging-platform-tools.md:1651`:`H-R9D-D-a` |
| `H-R9D-D-b` | QQBot 无插件、无 `max_message_length`,超长消息被静默切断且返回 `success: True`,无 warning | `tools/send_message_tool.py:2042`:`payload = {"content": message[:4000], "msg_type": 0}` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-messaging-platform-tools.md:1652`:`H-R9D-D-b` |
| `H-R9D-D-c` | 模型给的 `channel_id`/`message_id` 零格式校验直接拼进 URL;urllib 实测不归一化 `..`;同片 HA 为同一形状专门加了白名单正则() | `tools/discord_tool.py:88`:`url = f"{DISCORD_API_BASE}{path}"` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-messaging-platform-tools.md:1653`:`H-R9D-D-c` |
| `H-R9D-D-d` | 本片唯一"凭据跟着重定向走"的客户端(实跑复现 Authorization 跨 origin 保留);仓库已有  未被使用 | `tools/discord_tool.py:108`:`with urllib.request.urlopen(req, timeout=timeout) as resp:` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-messaging-platform-tools.md:1654`:`H-R9D-D-d` |
| `H-R9D-D-e` | 47 个用例(含 Slack/Signal/Matrix/WhatsApp 等与 Telegram 无关的)被一个可选依赖整文件跳过,运行器仍显示 ✓;下一轮报测试数时要把它当 | `tests/tools/test_send_message_tool.py:16`:`_HAS_TELEGRAM = pytest.importorskip("telegram", reason="python-telegram-bot not installed") is not None` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-messaging-platform-tools.md:1655`:`H-R9D-D-e` |
| `H-R9D-D-f` | 配了 `HASS_TOKEN` 即自动启用()且无任何逐次审批;审批片若已定案 hermes 的审批只覆盖 terminal/file,需要显式把"物理设备控制无审批"写进结论 | `tools/homeassistant_tool.py:345`:`def _check_ha_available() -> bool:` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-messaging-platform-tools.md:1656`:`H-R9D-D-f` |
| `H-R9D-D-g` | 可用性探针只查 `lark_oapi` 是否可导入,真实可用条件是  注入的线程局部客户端;装了 SDK 的任何会话都会看到 5 个必失败的工具 | `tools/feishu_doc_tool.py:54`:`def _check_feishu():` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-messaging-platform-tools.md:1657`:`H-R9D-D-g` |
| `H-R9D-D-h` | Read and participate in a Discord server. Actions include `search_members`, `fetch_messa | `website/docs/reference/tools-reference.md:242` | **转 R12 装订**。转给谁:R12 汇总文档-代码冲突的那一节。为什么现在做不了:它是一条 ▲ 定档,要与其他 ▲ 一起看才可比。第一件事:按 `CLAUDE.md` 记号定义把它定档(▲ / ◎),并入跨轮 ▲ 计数 | 铸于 `notes/r9d-raw-messaging-platform-tools.md:1658`:`H-R9D-D-h` |
| `H-R9D-E-a` | 什么都没配时返回硬编码后端名,该名字在注册表里**总能取到对象**,于是把注册表的可用性回落路径整条短路(■-1 的直接机制) | `tools/web_tools.py:270`:`    return "firecrawl"  # default (backward compat)` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-search-browser-supply.md:1425`:`H-R9D-E-a` |
| `H-R9D-E-b` | 集合含 `"xai"`,但其上方注释断言 xai「不是注册的 provider」—— 证明它已经是;注释指定的同步动作从未执行 | `tools/web_tools.py:171` 的 `_LEGACY_WEB_BACKENDS` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-search-browser-supply.md:1426`:`H-R9D-E-b` |
| `H-R9D-E-c` | 代码自己承认分发器会静默换后端,与同文件 `_resolve` docstring 的「不静默换后端」承诺直接冲突(■-2) | `agent/web_search_registry.py:239`:`gate and the dispatcher silently drops to` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-search-browser-supply.md:1427`:`H-R9D-E-c` |
| `H-R9D-E-d` | 集合只含 `web_extract` / `web_search`,`x_search` 的第三方内容既不被包装也不被威胁扫描(■-3) | `agent/tool_dispatch_helpers.py:584`:`_UNTRUSTED_TOOL_NAMES = frozenset({` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-search-browser-supply.md:1428`:`H-R9D-E-d` |
| `H-R9D-E-e` | 进程级缓存无 multiplex 豁免,而同文件 `:1468` 的 `if get_hermes_home_override() is not None:` 有——姐妹站点漏 | `tools/browser_tool.py:753`:`    if _cloud_provider_resolved:` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-search-browser-supply.md:1429`:`H-R9D-E-e` |
| `H-R9D-E-f` | 该函数与 `_LEGACY_PREFERENCE` 只被测试引用,生产选择逻辑在  里另写了一份(■-4) | `agent/browser_registry.py:113`:`def _resolve(configured: Optional[str]) -> Optional[BrowserProvider]:` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-search-browser-supply.md:1430`:`H-R9D-E-f` |
| `H-R9D-E-g` | 文档承诺站点黑名单覆盖 `web_search`/`web_extract`,实测 `web_search` 完全不覆盖、`web_extract` 只在 firecrawl  | `website/docs/user-guide/security.md:639` 的 `The blocklist is enforced across` | **转 R12 装订**。转给谁 / 为什么 / 第一件事:同 `H-R9D-D-h`,两条一起定档 | 铸于 `notes/r9d-raw-search-browser-supply.md:1431`:`H-R9D-E-g` |
| `H-R9D-F-a` | webhook 的「安全子集」含 `clarify`,而  分支只写日志就报 success,agent 会为一个没人能答的问题阻塞到 `agent.clarify_timeo | `toolsets.py:94`:`    "clarify",` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-gateway-clarify-turn-misc.md:1990`:`H-R9D-F-a` |
| `H-R9D-F-b` | 字面量标签集不认 `<think type="x">`,推理内容随流式增量原样送达用户;而  的未闭合正则用 `\b[^>]*>` 接受属性、会把整条回复吃空——同一输入两条路 | `agent/think_scrubber.py:89`:`    _OPEN_TAGS: Tuple[str, ...] = tuple(f"<{name}>" for name in _OPEN_TAG_NAMES)` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-gateway-clarify-turn-misc.md:1991`:`H-R9D-F-b` |
| `H-R9D-F-c` | 高危确认语过期保护对**不带 `timestamp`** 的历史消息完全不生效;该字段由持久化层写入,需在会话存储片确认哪些恢复路径带时间戳 | `agent/replay_cleanup.py:304`:`            ts = msg.get("timestamp")` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-gateway-clarify-turn-misc.md:1992`:`H-R9D-F-c` |
| `H-R9D-F-d` | `"-1"` 子串会命中 `2026-1-5` 这类日期,一次成功的 `read_file` 结果因内容含 `[command interrupted]` 被整块从回放历史删除 | `agent/replay_cleanup.py:37`:`    if "exit_code" in lowered and ("130" in lowered or "-1" in lowered):` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-gateway-clarify-turn-misc.md:1993`:`H-R9D-F-d` |
| `H-R9D-F-e` | environ\[` 零命中),「凭据是否继承给子进程」这个问题需要去找真正 spawn 的模块(`tools/code_execution_tool.py`、`tools/t | `agent/process_bootstrap.py:1`:`"""Process-level bootstrap helpers for ` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-gateway-clarify-turn-misc.md:1994`:`H-R9D-F-e` |
| `H-R9D-F-f` | 用 `netloc`(保留大小写)而非 `hostname`(小写化)比对,`https://TOOL-GATEWAY.…` 被判非托管、bearer 不发;当前所有调用方都自 | `tools/managed_tool_gateway.py:298`:`    return bool(actual.scheme) and (actual.scheme, actual.netloc) == (expected.scheme, expected.netloc)` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-gateway-clarify-turn-misc.md:1995`:`H-R9D-F-f` |
| `H-R9D-F-g` | 任意 hook 注入上下文以 0644 落盘、目录 0755、无任何清理机制;对照 | `tools/hook_output_spill.py:216`:`        spill_path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-gateway-clarify-turn-misc.md:1996`:`H-R9D-F-g` |
| `H-R9D-F-h` | 在模块 import 时定格 profile 感知的 `get_hermes_home()`,多 profile 网关下三个工具的调试日志会写进 import 时那个 prof | `tools/debug_helpers.py:47`:`        self.log_dir = get_hermes_home() / "logs"` | **转 代码缺陷复核轮**(组级三问) | 铸于 `notes/r9d-raw-gateway-clarify-turn-misc.md:1997`:`H-R9D-F-h` |

#### R11B 三片的 19 条(片 A 8 / 片 B2 5 / 片 D 6)

这 19 条与 R9D 那 45 条同因(片内号 + 案号正则失配),但**性质不同**:它们多数是
账目 / 记号 / 关卡类的元工作,其中 **6 条其实已经被做掉了**,只是账上没记。

| 案号 | 一句话现象 | 锚点 | 处置结论 | 铸号位 |
|---|---|---|---|---|
| `H-R11B-A-a` | `■-R11A-01` 把 R9C 已证伪的修法(只比 `self._base_url`)重新写成结论;更正写法见 §3.6,**主线执行,本片不改** | `gateway/relay/media.py:94`:`return "/relay/media/" in (url or "")` | **结清**。去向写「R11B 主线(本轮)」,主线**确实做了**:`notes/r11b-92-fix-regression-correction.md` 就是这条的产物(以 R9C 实证为准重写修法) | 铸于 `notes/r11b-raw-rulings-census.md:881`:`H-R11B-A-a` |
| `H-R11B-A-b` | 仓库自带的正确修法在 R11A 全部产出里零提及(实测 3 份文件各 0 命中);它是 `■-R11A-01` 缺的那一层 | `hermes_cli/urllib_security.py:31`:`class SafeCredentialRedirectHandler(urllib.request.HTTPRedirectHandler):` | **转 R12 装订**。转给谁:R12 讲 `■-R11A-01` 那一节。为什么现在做不了:要把「仓库自带的正确修法」写进正文,是写作动作,`chapters/` 不在本片 claim 里。第一件事:在该节补一段 `SafeCredentialRedirectHandler`,说明它正是 `■-R11A-01` 缺的那一层 | 铸于 `notes/r11b-raw-rulings-census.md:882`:`H-R11B-A-b` |
| `H-R11B-A-c` | `H-R10B-a` 三处独立铸号中的一处,R11A 只结清了 `scripts/` 那一处;本条从未被任何轮处置,且因号已标结清而不会被发现 | `tui_gateway/methods_session.py:1800`:`@method("pet.generate")` | **结清**。R11C 片 A 已就地结清并新立 `■-R11C-A-01`(原文那一格写的是「是,`■-R11C-A-01`;`H-R11B-A-c` 本身**关闭**」);该结清写在一张「项 / 结论」两列表里,案号在第二格,故普查读不到 —— 本行是它第一次进账 | 铸于 `notes/r11b-raw-rulings-census.md:883`:`H-R11B-A-c` |
| `H-R11B-A-d` | 同上,`H-R10B-a` 的第三处铸号(R10B 片 H);插件未声明 `defaultEnabled`,同样随号被误判为已结清 | `apps/desktop/src/plugins/gateway-pill/plugin.tsx:350`:`const plugin: HermesPlugin = {` | **结清**。同上,R11C 片 A 结清并新立 `■-R11C-A-02` | 铸于 `notes/r11b-raw-rulings-census.md:884`:`H-R11B-A-d` |
| `H-R11B-A-e` | 同一条断言 R7C 记 ▲、R8A 记 ◇;跨轮 ▲ 计数被 CLAUDE.md 定义为「地图腐烂程度」指标,记号不一致使它不可比 | `gateway/pairing.py:18`:`Storage: ~/.hermes/pairing/` | **转 R12 装订**。转给谁:R12 统一记号的那一步。为什么现在做不了:同一条断言 R7C 记 ▲、R8A 记 ◇,要改哪一边取决于装订时 ▲ 的口径。第一件事:按 `CLAUDE.md` 记号定义重判这一条(文档所述与代码矛盾才是 ▲),改后重算跨轮 ▲ 计数 | 铸于 `notes/r11b-raw-rulings-census.md:885`:`H-R11B-A-e` |
| `H-R11B-A-f` | 「静默抹掉」写于 R8-fix,R8C 已改判该定性,该句从未更新,并已被 R8D 两份底稿原样复用 | `hermes_cli/config.py:75`:`backup_path = config_path.with_name(f"{config_path.name}.corrupt.{ts}.bak")` | **结清**。`CLAUDE.md` 已就地补上「R11B 更正」引用块(原写「静默抹掉」,R8C 已推翻:有 stderr + 日志告警且原文件被逐字备份) | 铸于 `notes/r11b-raw-rulings-census.md:886`:`H-R11B-A-f` |
| `H-R11B-A-g` | R9C `■-1` 与 R9D `■-2` 是同一条(R9D 自陈「结清 R9C D 片 ■-1 在本片的部分」),跨轮 ■ 计数因此多算一条 | `agent/file_safety.py:284`:`os.path.join("cache", "bws_cache.json"),` | **转 R12 装订**。转给谁:R12 算跨轮 ■ 计数的那一步。为什么现在做不了:R9C `■-1` 与 R9D `■-2` 是同一条,合并会改动两章的合计行,而合计行是跨轮可比口径。第一件事:合并这两条并加脚注,不静默改合计数 | 铸于 `notes/r11b-raw-rulings-census.md:887`:`H-R11B-A-g` |
| `H-R11B-A-h` | R7C 两份底稿互不通气各铸 `▲-1`,登记卷统成 `▲-4` —— 去重是本项目已有的动作,但只在轮内做过,没有跨轮别名表 | `cron/scheduler.py:334`:`_running_job_ids: set = set()` | **转 R12 装订**。转给谁:同上。为什么现在做不了:R7C 两份底稿各铸 `▲-1`、登记卷统成 `▲-4`,去重要跨轮别名表,而别名表本身刚在 R11C 落成(`data/r11c/b-dedup-82-index.tsv`)。第一件事:拿该索引重算 R7C 的 ▲ 条数 | 铸于 `notes/r11b-raw-rulings-census.md:888`:`H-R11B-A-h` |
| `H-R11B-B2-a` | 包的接线图列了一个全仓不存在的 `capture.py`(该行是它的续行),而它描述的 PNG 尺寸嗅探实际在  与  **各写了一份**;需确认这是「计划中的拆分未发生」还是 | `tools/computer_use/__init__.py:26`:`overlay if the backend did not).` | **转 R12 装订**。转给谁:R12 讲 computer_use 的那一节。为什么现在做不了:去向写「主线定案 `■-B2-01` 时一并判」,而该定案在 R11B 未落;判它要读包的接线图与 `tool.py` 的实际实现。第一件事:确认 `capture.py` 全仓不存在、把 PNG 尺寸嗅探的真实位置写进正文 | 铸于 `notes/r11b-raw-backlog-light.md:1516`:`H-R11B-B2-a` |
| `H-R11B-B2-b` | help 文本硬编码 7 个 provider,目录扫描实测 8 个(漏 `supermemory`);本片只查了这一处手抄名单,**未做全仓「provider 名单手抄本」普 | `hermes_cli/subcommands/memory.py:19`:`"Available providers: honcho, openviking, mem0, hindsight,\n"` | **转 名单手抄点普查轮**。转给谁:下一个吃配置面的内容轮。为什么现在做不了:R11B 只查了 memory provider 一处 help 文本,「全仓 provider/toolset 名单手抄本」普查是内容工作。第一件事:在基线搜硬编码的 provider / toolset 名单串,与目录扫描结果逐个对表 | 铸于 `notes/r11b-raw-backlog-light.md:1517`:`H-R11B-B2-b` |
| `H-R11B-B2-c` | 这张 30 行静态表是「断连是否会触发压缩删历史」的唯一守门人(),但**没有任何机制保证新推理模型上架时有人来加行**;需确认是否有 CI/脚本对着 models.dev 目 | `agent/reasoning_timeouts.py:62`:`_REASONING_STALE_TIMEOUT_FLOORS: tuple[tuple[str, int], ...] = (` | **转 代码缺陷复核轮**。转给谁:同 E 组组级三问。为什么现在做不了:要查 `models.dev` 目录同步链路,而本容器该目录条目数实测为 0(离线),查不出真值。第一件事:先解决 models.dev 目录可用性,再判这张 30 行静态表在新模型上的覆盖缺口 | 铸于 `notes/r11b-raw-backlog-light.md:1518`:`H-R11B-B2-c` |
| `H-R11B-B2-d` | CSRF state 用 `!=` 直接比,非常量时间;MCP 侧(r6 章 §3.8)记的是「SDK 生成并常量时间比对」。本片判**不构成可利用面**(state 是 `s | `plugins/memory/honcho/oauth_flow.py:365`:`    if returned_state != state:` | **判为不做**。理由:R11B 自己已判**不构成可利用面**(state 是 `secrets.token_urlsafe(32)`),且去向原文就写「仅记录,不建议改」。代价:若 R12 要讲「两套 OAuth 的取舍」,这条常量时间比对的差异就得现查;代价可接受,因为它不指向任何未定结论 | 铸于 `notes/r11b-raw-backlog-light.md:1519`:`H-R11B-B2-d` |
| `H-R11B-B2-e` | 拆分只做了一半:42 个 builder 模块 vs `main()` 里仍内联的 16 个顶层组;本片按「弱 ▲」记(▲-B2-02),**是否计入跨轮 ▲ 计数交主线** | `hermes_cli/subcommands/__init__.py:5`:`into one 3,300-line function. This package breaks that tree apart: each` | **转 R12 装订**。转给谁:R12 决定弱 ▲ 是否计入跨轮 ▲ 计数的那一步。为什么现在做不了:`▲-B2-02`(拆分只做了一半)算不算 ▲,取决于装订时 ▲ 的口径,与 `H-R11B-A-e` 同一个判断。第一件事:两条一起定档 | 铸于 `notes/r11b-raw-backlog-light.md:1520`:`H-R11B-B2-e` |
| `H-R11B-D-a` | 锚点指向第三方 pip 包,基线里没有该文件,校验器恒记 MISSING-FILE(3 处)。笔记**已**用 ` @ mcp==1.28.1 site-packages` 声 | `notes/r6-60-mcp-oauth-cleanup.md:58` 的 `mcp/client/auth/oauth2.py:66-69 @ mcp==1.28.1 site-packages` | **转 下一个动 `scripts/` 的轮次**。为什么现在做不了:要给校验器加 `NON-BASELINE` 一档(锚点的 ` @ ` 后缀不是基线 sha 时),落在 `scripts/`,本片无权改。第一件事:加该档并计入分母不阻断,与 `H-R11C-D-i` 的 `ABSOLUTE` 一档同源、同一次做 | 铸于 `notes/r11b-raw-notes-citation-cleanup.md:591`:`H-R11B-D-a` |
| `H-R11B-D-b` | 该文 15 个块是「每行以自己的行号开头」的行号栏体例,校验器无法比对,本片改标 ```text;实测行号栏 **102/103 准确**(§4.2 可重跑) | `notes/r3-10-approval-security.md:56` 的 `tools/approval.py:3754` | **转 下一个动 `scripts/` 的轮次**。为什么现在做不了:要让校验器识别「每行以自己行号开头」的行号栏块,落在 `scripts/`。第一件事:按每行自己声明的行号比对,落地后把 R11B 临时改标的 ```text 改回代码围栏 | 铸于 `notes/r11b-raw-notes-citation-cleanup.md:592`:`H-R11B-D-b` |
| `H-R11B-D-c` | 自引**本仓库**脚本,该文件每轮增补都在变长,行号必然再漂(本轮已从 162 漂到 307) | `notes/r8d-02-coverage-audit.md:39` 的 `scripts/assign_layers.py:307-308` | **结清**。诉求是「定一条自引写法」,R11D 开工杂项已定:**自引锚点的 commit 钉子** `路径:行号 @ <sha>`,校验器用 `git show` 取那一版比对(`scripts/verify_citations.py` 的 `pinned_source`);这正是该条给的两个备选之外更好的第三个 | 铸于 `notes/r11b-raw-notes-citation-cleanup.md:593`:`H-R11B-D-c` |
| `H-R11B-D-d` | `notes/r7-raw-session-py.md` 等 41 个文件里仍有 **1,334 / 3,314(40.3%)** 个锚点路径无法从仓库根解析(`run.py` | `notes/r6-10-honcho.md:677` 的 `plugins/memory/honcho/cli.py:1113` | **转 R12 前置(锚点收口)**。转给谁:同 `H-R11C-D-d`。为什么现在做不了:41 个文件里 1,334 处锚点无法从仓库根解析,散文锚点缺内容判据需人工。第一件事:先补「有同名歧义」的那批(`__init__.py` / `base.py`),它们的候选集最大、危害最大 | 铸于 `notes/r11b-raw-notes-citation-cleanup.md:594`:`H-R11B-D-d` |
| `H-R11B-D-e` | 原文贴的 docstring **基线全仓不存在**(§6.1 负结论搜索面已给),是转述被当逐字摘录;`notes/r4-30-browser-automation.md`  | `notes/r4-01-environment-abstraction.md:38` 的 `tools/environments/base.py:374` | **转 R12 装订**。转给谁:R12 决定「证据完整性」类发现是否单独记账的那一步。为什么现在做不了:它问的是要不要新开一类记号,属装订期的口径决定。第一件事:判这一处(转述被当逐字摘录)是否值得单列一类;R11B 已按基线原文回抄,结论未动 | 铸于 `notes/r11b-raw-notes-citation-cleanup.md:595`:`H-R11B-D-e` |
| `H-R11B-D-f` | 本片清理**新暴露** 51 处 `BLOCK-DRIFT`,清理前一处都没报过——因为 MISSING-FILE / MISMATCH 在前一层就把它挡住了(§3.3) | (铸号行内无声明式锚点) | **结清**。诉求就是「记录为关卡性质」——**失败是分层的,修好上层会长出下层**,记录已在该底稿完成;R11C 片 D 对 `chapters/` 做同样的事时独立复现了同一现象,该性质已被二次确认,无进一步待办 | 铸于 `notes/r11b-raw-notes-citation-cleanup.md:596`:`H-R11B-D-f` |

**E 组小计:结清 6 / 已被取代 1 / 判为不做 1 / 转 X 56(共 64 条)。**

> 五组合计 130 条,加 §3.2 的 7 个别名号与 §4 的 3 个新号 = 表内 140 行。
> 按结论分:**结清 28 / 已被取代 8 / 判为不做 4 / 转 X 100**(§1.4 那个 ```text 块的来源)。

### 2.6 F 组:只有在「宽表头」口径下才看得见的另外 113 条 —— 本轮**不逐条处置**

口径③(补上「建议下一轮/建议接手/建议动作/建议/移交至」这些表头)比口径② 多出
**113** 条未结清。构成:

```verify
sed 's/-[a-z]$//' data/r11d/handover-widehints-only-ids.txt | sort | uniq -c | sort -rn | awk '{printf "%s %s\n", $2, $1}' | head -8
```

```text
H-R10B-C 12
H-R10H 10
H-R10C 8
H-R10A 8
H-K 8
H-G 8
H-R10D 7
H-R11C-C 6
```

| 来源 | 条数 | 本轮怎么办 |
|---|---:|---|
| R10 / R10B 片内号(`H-R10A`…`H-R10I`、`H-R10B-C/F/I`、`H-G`、`H-K`) | 89 | **不逐条处置**,立 `H-R11D-C-b` |
| R11A 片内号(`H-R11A-A`、`H-R11A-C`) | 10 | 同上 |
| R11C 片 C 的 6 条 | 6 | **已逐条处置**,号见 §2.4 D 组 |
| 无片标识的通用号(8 条) | 8 | 号见本表下一段;其中 R8D 片 B 那批见 §3.2 别名表,其余随 `H-R11D-C-b` |

那 8 个通用号是:H-3、H-4、H-6、H-7、H-9、H-12、H-15、H-18(此处刻意不加反引号,
以免这一行被普查读成一次定案 —— 它不是)。

**为什么不逐条处置(这是一个「判为不做」而不是遗漏)**:派工书给的范围是
「R11C 收口时的未结清 + REVIEW 队列 + R11C 各片移交」,这 99 条(89 + 10)
既不在那个范围里,也不是本轮测量的目标 —— 它们是**换一把尺子才量出来的**。
逐条读 99 条历史移交并给结论,要重跑十几份底稿的上下文,超出本片一轮的量,
而**草率给结论比不给更糟**:一条写着「转 R12」却没人读过的处置,
会让下一轮以为它被判过(这正是 `H-R10B-a` 那三处欠账消失的机制)。
代价如实说:这 99 条在下一轮之前**仍然不在任何账上**,和它们此前的状态一样。

---

## 3. 逐条论证

### 3.1 `H-R8D-i`:它设的 R12 前置条件**已经达成**,而没有人量过

R8D 把 R12 的前置条件定为「L1 全部 deep-read」。此后 R11B 写「不动」、R11C 写
「不归属本轮,去向 R12 前置不变」—— **四轮里没有一轮去量过这个条件是否已经满足**。
它是可计算的:台账 `data/ledger.tsv` 的 `layer` 列 + `status` 列就够了。

```verify
awk -F'\t' 'NR>1{sub(/\r$/,"",$4); sub(/\r$/,"",$6); if($4=="L1"){n++; if($6 ~ /deep-read$/) d++; if($6=="R1-inventoried") o++}} END{printf "L1 共 %d 文件;deep-read %d;仍为 R1-inventoried %d\n", n, d, o}' data/ledger.tsv
```

```text
L1 共 563 文件;deep-read 563;仍为 R1-inventoried 0
```

563 个 L1 文件**全部**落在某一轮的 `*-deep-read` 上,没有一个停在只盘点过的状态。
**条件达成,`H-R8D-i` 结清。**

> 这条的教训比它本身重要:**一条移交项如果写的是「等某个条件满足」,
> 而那个条件是可计算的,那么每一轮该做的动作是「量一次」而不是「写不动」。**
> 「不动」这两个字连续出现四轮,而实际上它可能早就该关了。
> 注意 `awk` 里的 `sub(/\r$/,"",$6)`:`data/ledger.tsv` 是 CRLF 行尾,不剥 CR 的话
> `$6` 永远匹配不上,这条命令会安静地打出 0 —— `CLAUDE.md` 已经为这个形状写过一次告诫。

### 3.2 `H-R11C-A-b`:给 R8D 片 B 的七条通用号铸别名并登记

R8D 片 B(`notes/r8d-raw-provider-identity.md`,provider / 模型的身份、目录与路由)
用通用号 `H-1`…`H-7` 写了 7 条移交,而 R8D 主线移交表用的是 `H-R8D-a`…`-j` 且内容无一重合。
于是这 7 条**从来没有进过任何账**,更糟的是:语料里别轮写的 `H-1`…`H-7` 都带着「结清」,
机械普查会把它们读成已结清。

处置方式沿用 R11C 给 `H-B1-a…e` 建别名的同一套做法 —— 那张别名表的第一行是:

`notes/r11c-90-handover-rulings.md:202`

```
| `H-R11B-B1-a` | `H-B1-a` | `notes/r11b-raw-backlog-r7b.md:2604`:`| H-B1-a | R11B 主线 / 成品章 |` | 片 B1 铸号未带轮次前缀,五条同源 |
```

并**吸取它的教训**:R11C 的定案行把范围写成 `H-R11B-B1-a`…`-e`,
普查只认到第一个,于是 `-b`…`-e` 四条仍挂着开(§2.3)。**本表把每一个号单独写满。**

| 案号 | 一句话现象 | 锚点 | 处置结论 |
|---|---|---|---|
| `H-R8D-B-a`(原 `H-1`) | 六个 provider 别名在两处映射表里给出不同结果 | `hermes_cli/models.py:1282`:`_PROVIDER_ALIASES = {` | **转 代码缺陷复核轮**。转给谁 / 为什么 / 第一件事:同 §2.5 组级三问;第一件事具体为「把 `hermes_cli/models.py` 与 `hermes_cli/auth.py` 两张别名表对表,列出全部分歧项」 |
| `H-R8D-B-b`(原 `H-2`) | 字符串 `qwen` 在 picker 侧 = DashScope、运行时侧 = Qwen | `hermes_cli/models.py:1335`:`"qwen": "alibaba",` | **转 代码缺陷复核轮**。第一件事:确认 picker 与运行时两条路径上 `qwen` 各自解析成什么,判是否会选错凭据 |
| `H-R8D-B-c`(原 `H-3`) | `HERMES_OVERLAYS.get(slug)` 用 CLI slug 查 models.dev slug 键,9/43 落空 | `hermes_cli/provider_catalog.py:127`:`overlay = HERMES_OVERLAYS.get(slug)` | **转 代码缺陷复核轮**。第一件事:枚举 43 个 slug,确认落空的 9 个当前是否真被 registry/profile 兜住 |
| `H-R8D-B-d`(原 `H-4`) | `vllm`/`llamacpp`/`llama.cpp`/`llama-cpp` 映到 `local`,而 `get_provider('local')` 返回 `None` | `hermes_cli/providers.py:402`:`"vllm": "local",` | **转 代码缺陷复核轮**。第一件事:确认这是死靶点还是真会被走到(找 `get_provider` 的全部调用方) |
| `H-R8D-B-e`(原 `H-5`) | 传入 models.dev 空间的 provider 名时所有分支落空、模型名原样返回 | `hermes_cli/model_normalize.py:493`:`provider = _normalize_provider_alias(target_provider)` | **转 代码缺陷复核轮**。第一件事:找是否存在真会这么调的路径;R8D 当时未找到,负结论的搜索面需重给 |
| `H-R8D-B-f`(原 `H-6`) | 两张 host→api_mode 表互为补集,直接调 `determine_api_mode` 的路径结果不同 | `hermes_cli/providers.py:614`:`def host_mandated_api_mode(base_url: str = "") -> Optional[str]:` | **转 代码缺陷复核轮**。第一件事:把两张表并成一张对照表,标出互为补集的那些 host |
| `H-R8D-B-g`(原 `H-7`) | `_VENDOR_PREFIXES` 重复键 `"trinity"` | `hermes_cli/model_normalize.py:61`:`"trinity": "arcee-ai",` | **判为不做**。理由:R8D 自陈「无行为影响」——字典字面量重复键在 Python 里后者覆盖前者,两处值需先确认是否相同;它的价值只在「lint 覆盖面」这个话题上。代价:若 R12 要讲「仓库有哪些静态检查没开」,这个实例要现找 |

**七条全部登记在案。** 实质内容随别名一起转,不是本轮能做的内容工作。

### 3.3 `H-R11C-B-f`:它要的索引**已经存在**,写移交的人不知道自己做完了

移交原文:「32 组合并的别名表尚未落成一份可查的索引文件;B-01 这种『四轮两号』的实体,
下一次有人拿着 `H-7` 去查,仍然走不到 `H-R8FIX-a` 的卷宗」。
而同一片的产出 `data/r11c/b-dedup-82-index.tsv` 的 `cases` 列就是那张别名表。
直接按它描述的那个用法试一次:

```verify
cd /home/user/hermes-study && grep -P "\bH-7\b" data/r11c/b-dedup-82-index.tsv | cut -f1,2,7 | head -3
```

```text
C02	hermes_cli/config.py	R8A/H-7 R8B/H-7 R8B/H-R8FIX-a R8C/H-R8FIX-a R8FIX/H-R8FIX-a R8C/◎-2 R8A/▲-10 R8C/▲-1 R8C/▲-2 R8C/▲-3
C68	hermes_cli/config.py	R8A/■-25 R8B/H-7
```

拿着 `H-7` 一次 grep 就走到了 `H-R8FIX-a`,**正是它说走不到的那条路**。故判**结清**。
残留的是另一个问题(「读者怎么知道有这份索引」),那属于 `H-R11C-M-a` 要定的登记落点,
不在本条诉求内 —— 本条诉求是「落成一份可查的索引文件」。

### 3.4 `H-R11C-M-b`:149 行「认不出表头」逐**类**判完

R11C 让这些行可见,但没判。**判的正确粒度是表头而不是行** —— 同一个表头下的每一行
必然同类。当前(钉住语料)149 行分布在 **22 个**不同表头上:

```verify
cd /home/user/hermes-study && python3 data/r11c/probes/handover_census_r11c.py --unclassified --exclude round-11d 2>&1 | awk -F'表头\[' 'NF>1{split($2,a,"]"); print a[1]}' | sort -u | wc -l
```

```text
22
```

| 类别 | 表头(条数) | 判定 |
|---|---|---|
| **真移交表,表头没被认出** | `建议下一轮做什么`(15+6)、`建议下一轮`(10+8)、`建议接手方`(8)、`建议接手`(8+7)、`建议`(8+7+6)、`建议动作`(7+4)、`移交至`(17)、无第四列的 `id/# + 锚点 + 现象`(9+7) | **该计入 handover**。合计 **137 行** |
| **真定案表,表头没被认出** | `移交项 / 结清处 / 主线复核`(3)、`案号 / 被判误报的那个实体 / 读到的正文 / 复核`(4)、`片内号 / 铸号位 / … / 本片定档`(7) | **该计入 ruling**。合计 **14 行** |
| **正当不该计入** | `位置 / 原写 / 改为 / 依据`(3,勘误表)、`条目 / 命中的词 / 它所在的原句 / 原句的意思`(3,R11C 那次翻车的记录)、`差异 / 成因`(1)、`处 / 原锚点与摘录 / 改为 / 说明`(1,锚点对照) | **不计入**。合计 **8 行** |

判进来之后的量化后果就是 §1.2 的口径③:**未结清从 7 变 217**。
`H-R11C-M-b` 由此**结清**(它要的是「逐行判」,给出的是逐类判 + 后果读数);
真正落地「让普查读到这 137 行」要改探针,而 `data/r11c/` 是历史轮次资产、
`scripts/` 本片无权改 —— 那一半立为 `H-R11D-C-c`(§4)。

### 3.5 R9D 那 45 条:点名覆盖率的**两个读数**

`CLAUDE.md` 规定:凡判据是「某字符串在语料里出现过没有」的测量,**必须报剔除本轮
承载清单与不剔除两个读数**。本节正是那类测量,而且它对「报告它」这个动作不幂等 ——
本底稿点了这 45 个号,写完之后朴素读数必然归零。

```verify
cd /home/user/hermes-study && for id in $(awk -F'\t' '$1 ~ /^H-R9D-[A-F]-/ {print $1}' data/r11d/handover-open-rows.tsv); do src=$(awk -F'\t' -v i="$id" '$1==i{print $2}' data/r11d/handover-open-rows.tsv); n=$(grep -rlF "$id" --include='*.md' --include='*.py' --include='*.tsv' . 2>/dev/null | grep -v '^./.git/' | grep -v "$src" | grep -v 'r11d' | wc -l); echo "$id $n"; done | awk '{s+=$2; if($2==0)z++} END{printf "剔除本轮:命中文件数合计 %d,零命中 %d 条 / 共 45 条\n", s, z}'
```

```text
剔除本轮:命中文件数合计 18,零命中 39 条 / 共 45 条
```

```verify
cd /home/user/hermes-study && for id in $(awk -F'\t' '$1 ~ /^H-R9D-[A-F]-/ {print $1}' data/r11d/handover-open-rows.tsv); do src=$(awk -F'\t' -v i="$id" '$1==i{print $2}' data/r11d/handover-open-rows.tsv); n=$(grep -rlF "$id" --include='*.md' --include='*.py' --include='*.tsv' . 2>/dev/null | grep -v '^./.git/' | grep -v "$src" | wc -l); echo "$id $n"; done | awk '{if($2==0)z++} END{printf "不剔除:零命中 %d 条 / 共 45 条\n", z+0}'
```

```text
不剔除:零命中 0 条 / 共 45 条
```

**两个读数差得刺眼:不剔除时「45 条全部被点过名」,剔除后才看到 39 条从未被任何
别的文件提过。** 那 6 条例外全部出自 R11C 片 B 的 82 簇去重(它们作为重复簇成员被扫到),
**没有一条是被当成移交项处理过的**。

搜索面写清楚(负结论的成本):`grep -rlF` 定长串匹配,面 = 仓库根下全部
`*.md` + `*.py` + `*.tsv`,排除 `.git/`、排除该号自己的铸号文件;
「剔除」那一读数另排除路径含 `r11d` 的一切(本轮承载清单)。
**不含** `.json` / `.txt` / 无扩展名文件 —— 若某个号只在这些文件里被提过,本测量看不见。

### 3.6 R11D 开工杂项已实际结清的那批:逐条证据

A 组有 8 条判「结清」的依据都在 R11D 开工杂项(提交 `df6d450`)。逐条给可重跑证据:

```verify
cd /home/user/hermes-study && python3 scripts/verify_chapter_order.py >/dev/null 2>&1; echo "verify_chapter_order 退出码=$?"; python3 scripts/verify_derived_numbers.py >/dev/null 2>&1; echo "verify_derived_numbers 退出码=$?"; grep -c 'ps1|css|tsv' scripts/verify_citations.py; sed -n '255p' chapters/r11b-the-unwritten-layer.md
```

```text
verify_chapter_order 退出码=0
verify_derived_numbers 退出码=0
2
- 平台接驳的主干在第八章 `chapters/r7b-platform-integration.md`;本章是它的边角补遗。
```

- `H-R11C-F-a`:`verify_chapter_order.py` 存在且退出码 0;`chapters/r11b:255` 已从「第十一章」改为「第八章」。
- `H-R11C-E-c` / `H-R11C-F-b`:`verify_derived_numbers.py` 存在且退出码 0。
- `H-R11C-D-a`:`CITE_EXTS` 里已含 `ps1|css|tsv`。
- `H-R11C-E-a` / `-b`:`chapters/r1` 的分层表与 `:118` 段已改为台账真值,并由上面那道
  可复算指标关卡持续钉住(这正是「修一次又过期六轮」这个形状的机制化解法)。
- `H-R11C-D-f` / `H-R11C-M-d`:两条制度裁定已写进 `CLAUDE.md`,锚点见 A 组表。

### 3.7 三条同族(`H-R9B-f` / `H-R11A-d` / `H-R11B-f`)为什么只能转

它们卡的是同一件事:本容器**没有 ffmpeg**。

```verify
command -v ffmpeg >/dev/null 2>&1 && echo "ffmpeg: 有" || echo "ffmpeg: 不存在"
```

```text
ffmpeg: 不存在
```

而本轮纪律禁止装包、禁止动 venv、禁止 apt。三条都要求「真装一遍再跑」,
在这个约束下**做不了任何一条**,而 R11B / R11C 两轮的处置(「维持推定,不关闭」)
是对的 —— 不把「没跑成」写成「不成立」。
本轮给的增量是把三条**合并成一次环境安排**(见 A 组 `H-R11C-M-c` 那一格的第一件事),
并指出一条不需要 apt 的路径:`pip install imageio-ffmpeg` 自带静态 ffmpeg 二进制。
**这条路径本轮未实测**(禁止装包),它是给下一轮的起点,不是结论。

---

## 4. 本轮新铸的号

**案号纪律**:片内铸号必须带片标识,一个号只指一个实体。本片是 R11D 片 C,
故新号一律 `H-R11D-C-*`;§3.2 的七个别名号属 R8D 片 B 的历史实体,按其原轮次片位铸为 `H-R8D-B-*`。

| 案号 | 一句话现象 | 锚点 | 处置结论 |
|---|---|---|---|
| `H-R11D-C-a` | 机械口径把「已处置」等同于「已结清」:一张处置表一写,表里的号在普查里**全部变 CLOSED**,哪怕结论是「转 R12」。本表 90 条「转 X」就是这样在账面上消失的 | `data/r11c/probes/handover_census_r11c.py:79`:`# 判开闭是人的事,普查的事是别让任何一条从眼前消失。` | **转 落地铸号落点的那一轮**(与 `H-R11C-M-a` 同一次做)。为什么现在做不了:修法要么改普查器(`data/r11c/` 是历史资产、`scripts/` 本片无权),要么给处置表加一个机器可读的「是否仍需后续动作」列并入册,两者都要制度位。第一件事:给移交表/定案表定一个 `后续` 列(值域 `无` / `转<轮>`),普查按该列而不是按「出现在哪张表」判开闭 |
| `H-R11D-C-b` | 宽表头口径下另有 **99** 条片内号(R10 / R10B 89 + R11A 10)+ 4 个通用号从未进任何账,本轮**未逐条处置** | `data/r11d/handover-widehints-only-ids.txt:1`:`H-12` | **转 下一轮开工杂项**。为什么现在做不了:超出本片派工范围,逐条读要重跑十几份底稿的上下文;草率给结论比不给更糟(见 §2.6)。第一件事:拿 `data/r11d/handover-open-rows-widehints.tsv` 当输入,先按**铸号文件**分批(每份底稿一批),每批先判「这批的去向轮次过去了没有」,再逐条给四选一 |
| `H-R11D-C-c` | 移交普查的**案号正则与案号纪律互斥**(片内号一条都认不出),且 137 行真移交表因表头认不出而不计入;两处修法都落在本片无权改的文件里 | `data/r11c/probes/handover_census_r11c.py:53`:`ID_RE = re.compile(r"H-[A-Za-z0-9]+-[a-z]\b` | **转 把移交普查收进 `scripts/` 的那一轮**。为什么现在做不了:`data/r11c/probes/` 是历史轮次资产(本轮纪律明令不改),而 `scripts/` 本片无权改;本片的做法是**import 它、只换正则与语料**,这只解决了测量,没解决关卡。第一件事:把 `handover_census_r11c.py` 提升为 `scripts/verify_handover_ledger.py`,合入本片的宽正则(`H-(?:[A-Za-z0-9]+-)+[a-z]\b`)与宽表头名单,**落地前先跑一次前后对比**(预期 97 → 306) |

**`H-R8D-B-a`…`-g` 七个别名号见 §3.2**,它们不是新实体,是给已有实体补一个符合案号纪律的名字。

---

## 5. 自校验读数

自校验读数按制度贴在 ```` ```text ```` 里,**不写进 ```` ```verify ````** ——
一个「跑校验器扫本文件」的命令会被 `verify_evidence_commands.py` 重跑,从而无限递归。

```text
$ python3 scripts/verify_citations.py /home/user/hermes-agent notes/r11d-raw-handover-disposition.md
citations=5  OK=5
可校验比例 OK/5 = 100.0%
table_anchors=206  OK=154  UNCHECKED=52
OK: every code-block-backed citation matches the baseline
(退出码 0)

$ python3 scripts/verify_evidence_commands.py notes/r11d-raw-handover-disposition.md
verify-blocks paired=13  unpaired=0  differing=0  timedout=0
runnability   ran=0  runfail=0  skipped-mutating=0
OK: every paired ```verify command reproduces its pasted output
(退出码 0)

$ git -C /home/user/hermes-agent status --porcelain | wc -l
0
```

**表格锚点声明率单独报,不并入可校验比例**(R11B 定):`table_anchors=206  OK=154`
= **74.8%**。剩下 52 条 UNCHECKED 全部是「一格里第二个锚点没跟摘录」这一类
(如现象格里顺带提到的路径),不是移交锚点本身。
E 组那 64 行的**铸号位**锚点本轮全部改成声明式(摘录 = 该行上的案号本身),
理由是它们是下一轮唯一会被当作起点直接使用的东西。

### 本片没查证的部分(如实申报)

1. **E 组 64 条的实质**没有逐条重新取证。本片读的是它们的**铸号行**
   (锚点 + 一句话现象 + 去向),没有回到基线复核每条缺陷是否仍成立。
   处置结论针对的是**账目状态与去向**,不是缺陷判定本身。
2. **F 组 99 条**(`H-R11D-C-b`)本轮**一条都没读**,只做了计数与分组。
3. `pip install imageio-ffmpeg` 能否解决三条同族的 ffmpeg 依赖,**本轮未实测**
   (纪律禁止装包),它是给下一轮的起点,不是结论。
4. 口径③ 那份「宽表头」名单是**本片自定**的(补了「建议下一轮/建议接手/建议动作/
   建议/移交至/本片定档」六个词根),它没有经过前后误吞对比 ——
   落地成关卡前必须按 R10B 扩白名单时那套做法量一遍(已写进 `H-R11D-C-c` 的第一件事)。
5. 「R9D 45 条的去向轮次已全部过去」这个负结论的搜索面见 §3.5,
   **不含** `.json` / `.txt` / 无扩展名文件。

---

## 完成信号

片 C 收工。产出:

- `notes/r11d-raw-handover-disposition.md`(本文件)
- `data/r11d/probes/handover_disposition_r11d.py` —— import R11C 普查器,只换案号正则与语料;
  `--exclude` / `--add-note` 用来把读数钉住(本轮三片并发写 `reports/` 与 `notes/`)
- `data/r11d/probes/handover_rows_r11d.py` —— 导出每条案号的铸号行(工作底表)
- `data/r11d/probes/handover_rowgen_r11d.py` —— 从铸号行**机械生成**处置表的锚点,不手抄
- `data/r11d/handover-open-rows.tsv`(104 条)、
  `data/r11d/handover-open-rows-widehints.tsv`(217 条)、
  `data/r11d/handover-widehints-only-ids.txt`(113 条)

三条自校验读数见 §5,`data/r11c/` 与 `scripts/` 与 `chapters/` 与 `CLAUDE.md` 零改动,
基线 `git status --porcelain` 为 **0** 行。
`data/inflight/r11d-c-handover-disposition.claim` **未动**(claim 不许生产者自己关)。

