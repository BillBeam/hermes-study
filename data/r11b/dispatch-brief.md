# R11B 派工书 —— 复盘与清账轮

> 本轮不是内容轮。五片里只有 B1 / B2 是真读代码,A / C / D 是**清账**:
> 更正记录、补校验、去重。**清账不许改变已定案结论的实质**——
> 发现旧结论确应推翻的,作为**新定案单独立项并给证据**,不得就地改写旧结论
> 使它看起来一直是对的。

## 所有片共同的硬约束

### 基线只读
- 学习对象在 `/home/user/hermes-agent`,已 checkout `863e31318553cda8ad61df681d08175364d4164b`。
- **绝不修改基线任何文件、绝不在基线里跑装包/构建**(R8A 有子代理跑 npm 重写了
  `package-lock.json` 的前例)。收工时 `git -C /home/user/hermes-agent status --porcelain` 必须为空。

### 共享资源纪律
- **运行期间不改 `scripts/`**(主线已在派发前改完并自校验)。要新脚本就写进
  `data/r11b/probes/`,并保证**可重跑、不依赖会话专属路径**(用 `git rev-parse --show-toplevel`
  推仓库根,临时目录用 `mktemp -d`)。
- **不装任何东西**:venv(`/home/user/hermes-venv`,已备好 87 个包)、apt、npm、pip 一律不动。
  缺依赖就写进底稿的「需要但没装」一节,交主线。
- 测试用:`cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh <路径>`。

### 证据格式(逐条对照 CLAUDE.md,机械校验)
1. **锚点单独成行,置于块之前**:`路径:行号 @ 863e313`,然后才是代码块。写在块后 = 无声地一条都不校验。
2. ```` ``` ```` 围栏块是**逐字源码摘录,整块每一行**都比对(BLOCK-DRIFT 阻断)。
   要跳段就**拆成两个各自带锚点的块**,别打省略标记。
3. 非源码块用**显式语言标记**:```` ```text ```` / ```` ```console ```` / ```` ```verify ```` / ```` ```shell-session ````。
4. **表格里的锚点必须写成声明式**:锚点后**紧跟**一个反引号摘录,例如
   `` | … | `gateway/relay/media.py:94`:`return "/relay/media/" in (url or "")` | … | ``。
   不这么写就恒记 UNCHECKED、一次都不会被比对。
5. **`` ```verify `` 块 = 重跑能复现该结论的那一条命令**;要钉输出就在**紧跟其后**放
   ```` ```text ```` 块贴逐字输出。本轮该关卡**已是阻断级**,`unpaired` 目标 0。
6. **不写裸文件名**(除非文件真在仓库根)。`base.py` 在基线里有 9 个候选,`__init__.py` 有 171 个。
7. **负结论必须写搜索面**:搜了什么、什么模式、排除了什么。"全仓没有 X"的可信度等于一次 grep 的完备性。
8. **记号**:▲ 文档与代码矛盾;◇ 代码有文档无;■ 代码缺陷;◎ 文档成立但显著保守(字面为真就不是 ▲)。

### 锚点扩展名白名单(别踩空)
`CITE_EXTS = py mdx md yaml yml toml c h sh json tsx ts mjs js nix rs txt`;
另有 `EXTLESS_NAMES` 26 个无扩展名文件(`Dockerfile`、`Makefile`、`.gitignore`、
`hermes-gateway`、`run`、`base`、`type` 等)。

**R11A 派工书在这里写错过一句,本轮更正**(H-R11A-g):派工书当时说
`scripts/hermes-gateway` 不受引用校验保护——**说反了**。它在 `EXTLESS_NAMES` 名单里、
路径又含 `/`,实测**受保护**。真正不受保护的是 **`.ps1` / `.cmd`**(不在 `CITE_EXTS` 里,
且不属无扩展名名单)。指向这两类文件的锚点**连 UNCHECKED 都不记,直接不被当成锚点**。

### 提交纪律(本轮新机制,与你有关的部分)
主线已为每片放了 `data/inflight/<片>.claim`,声明你的产出路径。**在你发出完成信号之前,
这些路径提交不进去**(pre-commit 钩子拦截)。所以:
- **别自己跑 `git commit`**;写文件即可,主线收货后统一落账。
- 产出路径**严格按下面各片的清单**,写到清单外的路径主线可能看不见。

### 双产出与语言
- 你只写**底稿 `notes/r11b-*`**(求全求证,啰嗦没关系)。成品章由主线写。
- **全部产出用中文**;代码、路径、命令、引用原文照抄不译。
- 底稿末尾必须有 **`## 移交`** 一节:每条带**声明式锚点**(锚点 + 紧跟的反引号摘录)+ 一句话现象。
  没有就写「无」。

### 完成信号
写完后,**最后一条消息**里明确写:`片<X> 完成`,并列出你实际写了哪些文件、各多少行。
主线只认这条信号,不看文件形态。

---

## 片 A · 跨轮定案账:去重普查 + 「后轮覆盖前轮已证伪结论」普查

**产出**:`notes/r11b-raw-rulings-census.md`,探针 `data/r11b/probes/rulings_*.py`
(可选,但普查口径要能重跑)。

### A-1 定案去重普查

**背景(这是本片存在的理由)**:`notes/r9c-90-handover-rulings.md:11` 的表头写着
`| **H-R9A-a** = **H-R9B-d** | R9A 移交(去向写「R9C 或立即」),R9B 已取证 | **改判:维持 ■,但移交项给的修法不足以修好它**`
——R9C 已经认定这两个是同一条并定了案。而 `reports/round-11a-ops-and-delivery.md:494` 的
`- **■-R11A-01**(由 H-R9B-d 升格):`gateway/relay/media.py:94` 用**子串**决定要不要带`
又把它立成新条目。**同一处代码现在有三个案号**(H-R9A-a / H-R9B-d / ■-R11A-01)。

**任务**:全语料普查同类重复,给出**去重后的定案总数**、**合并的条目对**、**合并规则**。

口径要自己定死并写出来,至少覆盖:
- **语料面**:`reports/*.md` + `notes/*.md` + `chapters/*.md`(说清楚含不含 `reviews/`,给理由)。
- **什么算「一条定案」**:注意记号体系**跨轮不一致**——R7B 那种是轮内序号
  (`reports/round-7b-platform-integration.md:99` 的 `- **▲2** `/stop` 与 `/approve` 不同路`),
  R8B 之后才是 `■-R8B-12` 这种全局号。两种都要收。
- **什么算「重复」**:建议按 (锚点文件, 断言实质) 判,不要只按案号或只按行号——
  同一缺陷在不同轮可能锚到 `:92`(函数头)与 `:94`(那句 `in`)。
- **合并规则**:哪个案号留、哪个作别名、留哪一轮的结论。

**已知要特别查的两类**:
1. **同一实体多案号**(上面那条是样板)。
2. **同一案号多实体**——`H-R9B-d` 这个号在三个地方指三件不同的事:
   - `notes/r9b-raw-tts.md:1744` 的 `H-R9B-d | `tools/tts_tool.py:1666``(TTS 标签正则)
   - `notes/r9b-raw-video.md:2879` 的 `### H-R9B-d:插件侧 3 个 provider(1,639 行)本轮未精读`
   - `reports/round-9b-multimodal-delivery.md:454` 的中继媒体 bearer(才是被续转的那个)
   各片底稿各自铸号、和报告的正式表撞了。**这是第二个物种,单独统计、单独给规则。**

**报数要求**:去重前总数、去重后总数、合并对清单、无法合并的条目 + 各自保留的理由。

### A-2 「后轮覆盖前轮已证伪结论」普查

**背景**:`notes/r9c-90-handover-rulings.md` §1.2 用**本地双服务实验**证明
「只比对 `self._base_url`」这个修法**不足以**修好该缺陷:`urllib.request.urlopen` 默认跟随
302 **且把 `Authorization` 原样带到新主机**,于是主机校验判通过、bearer 照样泄漏;
正确修法是仓库自带的 `hermes_cli/urllib_security.py:31` 的 `SafeCredentialRedirectHandler`。
而 `notes/r11a-90-handover-rulings.md:70` 又写
`而正确的比较值**就在同一个类的构造里**,同一文件里还被用来拼规范 URL:` ——
**把 R9C 已证伪的修法重新写成了结论。**

**任务**:普查**其他**定案是否存在同型倒退(后轮把前轮已证伪的结论/修法重新写成结论)。

**这条的验收特别严**:必须报出**搜索面**与**命中数**;
**命中为零也必须给出搜索面,不许只写「未发现」**。搜索面至少要说清:
扫了哪些文件、用什么模式找「改判/推翻/证伪/不足以/实测仍」这类改判语,
怎么把改判语和它所改判的对象配对,排除了什么。

**注意**:A-2 只做**普查与取证**,`■-R11A-01` 那条本身的更正由**主线**执行
(它牵涉报告勘误节的写法)。你把证据、范围、以及「更正该怎么写」的建议给足即可。

---

## 片 B1 · 历史欠账:R7B 那 12 个 L1 文件(4,960 行)

**产出**:`notes/r11b-raw-backlog-r7b.md`

**背景**:`reports/round-9d-l1-completion.md:338` 的
`- **限定**:**38 个 L1 文件(7,710 行)在全部产出语料里没有任何一条可溯源断言**(§3.4)。`
——台账把它们标成了 `*-deep-read`,但**全部产出语料里没有任何一条断言引用过它们的路径**。
`status` 列在这些文件上**高于实际交付**。R9D 的责任是点名 + 归属,**补读归本轮**。

**你的 12 个文件**(全在 `/home/user/hermes-agent/`,清单也在 `data/r11b/backlog-38.tsv` 里 `round=R7B` 的行):

| 文件 | 行 | 裸名也零命中 |
|---|---|---|
| `gateway/platforms/yuanbao_proto.py` | 1418 | |
| `gateway/platforms/yuanbao_media.py` | 665 | Y |
| `gateway/platforms/qqbot/chunked_upload.py` | 602 | |
| `gateway/platforms/yuanbao_sticker.py` | 558 | Y |
| `gateway/platforms/qqbot/keyboards.py` | 461 | Y |
| `gateway/platforms/msgraph_webhook.py` | 453 | |
| `gateway/platforms/qqbot/onboard.py` | 220 | Y |
| `gateway/platforms/media_cache.py` | 202 | Y |
| `gateway/relay/command_manifest.py` | 145 | Y |
| `gateway/platforms/qqbot/__init__.py` | 91 | |
| `gateway/platforms/qqbot/constants.py` | 74 | |
| `gateway/platforms/qqbot/utils.py` | 71 | |

**交付判据**:每个文件**至少一条带行号锚点的可溯源断言**,且断言要有内容
(讲清它解决什么问题 / 在链路里的位置 / 有什么取舍),不是"这个文件存在"。
**标 Y 的 5 个优先级最高**——它们连基名都没被提过,基本可断定从没被讲过。

按机制成簇写,不必一文件一节。R7B 章(`chapters/r7b-platform-integration.md`)是这一簇的成品章,
写之前先读它,**看清楚哪些机制它已经讲了、这 12 个文件在其中处于什么位置**——
你的产出要能被主线接进 R11B 成品章,并让 R7B 章的空缺被明确交代。

---

## 片 B2 · 历史欠账:R2 / R4 / R6 / R8B 那 26 个 L1 文件(2,750 行)

**产出**:`notes/r11b-raw-backlog-light.md`

背景同片 B1。你的 26 个(清单见 `data/r11b/backlog-38.tsv` 里 `round` 为 R2/R4/R6/R8B 的行):

- **R8B 17 个薄壳**(1,023 行,`hermes_cli/subcommands/` 下):`backup.py` `claw.py` `console.py`
  `debug.py` `hooks.py` `import_cmd.py` `insights.py` `logs.py` `memory.py` `model.py`
  `plugins.py` `prompt_size.py` `skin.py` `slack.py` `tools.py` `uninstall.py` `webhook.py`
  (注意:清单里 18 个中有 1 个已被覆盖,以 TSV 为准)。平均 60 行,多为转发壳。
  **一节讲完即可**,但要讲出这一层**为什么存在**(壳与实现分离得到了什么),
  并点出其中形态不同的那几个。
- **R2 3 个**:`agent/oneshot.py`(158)、`agent/reasoning_timeouts.py`(231,Y)、
  `agent/thinking_timeout_guidance.py`(136,Y)
- **R4 4 个**:`tools/close_terminal_tool.py`(70,Y)、`tools/computer_use/__init__.py`(45)、
  `tools/environments/__init__.py`(14)、`tools/read_terminal_tool.py`(93,Y)
- **R6 2 个**:`plugins/memory/honcho/config_schema.py`(324)、
  `plugins/memory/honcho/oauth_flow.py`(656)

交付判据同 B1:每个文件至少一条**带行号**的可溯源断言,标 Y 的优先。
R6 那 2 个(980 行)是本片最重的,别被 17 个薄壳挤掉。

---

## 片 C · 历史欠账 H-R8D-g:六章锚点排版(UNCHECKED ≥90%)

**产出**:直接改 `chapters/` 六章正文 + 底稿 `notes/r11b-raw-chapter-anchors.md` 记录改法与发现。

**背景**:`reports/round-8d-cli-completion.md:430` 的
`| **H-R8D-g** | R11B | `chapters/r2-*.md`、`r4-*`、`r5-*`、`r6-*`、`r7-*`、`r7b-*` 六章 | 校验器排版提示逐章点名:UNCHECKED 占比 ≥90%,拉低全量可校验比例到 68.5% |`
这六章的锚点写在**代码块之后**并用散文隔开,于是**每一条引用都配不上块**、全部记 UNCHECKED
——关卡一路是绿的,**实际一条都没校验过**。

**清理前读数(主线实测,你要复现它作为起点)**:
```
chapters/r2-turn-loop-and-model-access.md: UNCHECKED 21/21 = 100.0%
chapters/r4-execution-environments.md:     UNCHECKED 36/40 = 90.0%
chapters/r5-session-state-and-persistence.md: UNCHECKED 23/23 = 100.0%
chapters/r6-memory-provider-ecosystem.md:  UNCHECKED 13/14 = 92.9%
chapters/r7-gateway-session-core.md:       UNCHECKED 31/33 = 93.9%
chapters/r7b-platform-integration.md:      UNCHECKED 36/39 = 92.3%
全 chapters:citations=441 OK=234 UNCHECKED=207 可校验比例 53.1%
```

**任务**:把这六章的锚点改成制度要求的排版(**单独成行、置于块前**),使它们真正被校验。

**关键**:改排版之后,这些引用**第一次真正被比对**,**必然会暴露出真漂移**。
这正是本项目 R8C 的经验(只比首行的校验器对"锚到了隔壁同形状的段落"完全无感)。
所以:
- 漂移**就地改正行号**(`chapters/` 属"直接改正文"那一类)。
- 若发现摘录与基线**实质不符**(不是行号漂,是抄错/抄漏/凭空补),**在底稿里逐条点名**,
  正文按基线原文改正,并在底稿写清"原文是什么、基线是什么、为什么这是抄错不是漂移"。
- **不得为了过关删掉引用或把代码块改成 ```text**。豁免只给真的不是源码的块。
- 有的引用**本来就是散文指路**(如"这一簇的实现在 `gateway/session.py` 一带"),
  那种保持散文即可,不必硬造代码块——`chapters/` 是求读的。**在底稿里把这类点清楚数目**,
  说明剩余 UNCHECKED 里有多少是这种正当散文。

**自校验**(每改完一章就跑,最后整体跑一遍):
```
python3 scripts/verify_citations.py /home/user/hermes-agent chapters/<改的那章>.md
```
必须 0 MISMATCH / 0 BLOCK-DRIFT / 0 TABLE-DRIFT / 0 TABLE-OUT-OF-RANGE。
`--fix` 只用于**无歧义**行号漂移,**用后必须不带 `--fix` 再裸跑一遍确认**。

**底稿要报**:逐章清理前后的 UNCHECKED 读数、全 chapters 合并可校验比例前后、
本次暴露出的真漂移条数与逐条明细、判为"正当散文引用"的条数。

---

## 片 D · 历史欠账 H-R8FIX-b:全 notes 314 处 MISMATCH / MISSING-FILE

**产出**:直接改历史 `notes/` 正文 + 底稿 `notes/r11b-raw-notes-citation-cleanup.md`。

**背景**:`reports/round-10-client-interface-layer.md:528` 的
`| **H-R8FIX-b**(合并后续转) | R11B | 本报告 §4 的 **314 处**与按文件分解表 | 与 H-R8D-g 合并做,共用一次全量校验 |`
定稿关卡的强制范围一直是"`chapters/` 全部 + **本轮** notes/reports",
**已完成轮次的 notes 从来不在范围里**,于是攒下 314 处。

**清理前读数(主线实测)**:`citations=16612 MISMATCH=125 MISSING-FILE=189 OK=10828 UNCHECKED=5470`,
可校验比例 65.2%。**逐条明细已存 `data/r11b/notes-citation-backlog.txt`(314 行),分布在 41 个文件。**

**范围红线(重要)**:
- **只改文件名不以 `r11b-` 开头的历史 notes**。`notes/r11b-*.md` 是本轮其他片**正在写**的文件,
  **绝对不要碰,也不要让 `--fix` 扫到它们**。跑校验器时**显式列出你要处理的文件**,
  不要用 `notes/*.md` 通配符。
- 你的 41 个文件清单可从 `data/r11b/notes-citation-backlog.txt` 第一列取。

**两类失败,处置不同**:
1. **MISSING-FILE(189 处)**:多数是**裸文件名缺目录**(如 `credential_pool.py` 28 处集中在
   `notes/r2-22-credential-pool.md`)。要**补成能从仓库根解析的完整路径**。
   基线里同名歧义是真的(`__init__.py` 171 个候选),所以**每条都要确认指的是哪一个**,
   别按最像的那个填。确认不了的**记为未决并在底稿点名**,不要瞎填。
2. **MISMATCH(125 处)**:行号漂移或摘录不符。无歧义漂移可用 `--fix`;
   `not found within ±40` 的要人判——**判不出来的宁可留着并点名**,也不要改摘录去迁就行号
   (那是把证据改成和错误一致,正是这个关卡要防的)。

**制度约束**:`notes/` 属"**直接改正文**"那一类,改判处**就地写明"原判是什么、为什么撤、依据是什么"**。
**但清账只更正记录,不改变结论实质**——若你发现某条旧结论**确实错了**(不是引用漂了,是结论错了),
**不要就地改结论**,而是在你的底稿里**单独立项、给证据**,交主线定案。

**底稿要报**:清理前后读数(citations / MISMATCH / MISSING-FILE / OK / UNCHECKED / 可校验比例)、
按文件的前后分解、未决条目逐条点名(带锚点)、以及**你改了但不确定的**逐条点名。
