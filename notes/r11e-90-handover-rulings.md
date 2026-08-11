# R11E · 移交项定案(逐条给结论,收件人一律改为条件式)

> **本文件是 R11E 移交定案的落点。** CLAUDE.md 定过「结清的单一落点是它所属轮次的
> 移交/定案表,写在别处的不算数」;R11C 又补过一句「落点定了不等于落点被读到」,
> 并要求**发现面覆盖该轮全部底稿**。本文件与 `reports/round-11e-reading-layer.md` §6
> 的表是同一份内容,报告那张是摘要,本文件是逐条。
>
> **上游**:片 C 的候选面 `data/r11e/handover-candidates.tsv`(114 条)与底稿
> `notes/r11e-raw-handover.md`(506 行)。片 C 已给出 114 条的 `verdict`,
> 其中 **25 条判「存疑·交主线裁定」**——本文件逐条裁定那 25 条,
> 并复核片 C 的其余 89 条。

## 0. 主线复核片 C 的 89 条

| 片 C 的 verdict | 条数 | 主线复核结论 |
|---|---:|---|
| `本轮结清` | 0 | **认可**。判据一(去向点名阅读层)命中 0 是**真的**:主线独立复跑全语料,唯一命中是 `CLAUDE.md` 本轮自己新写的那条制度——**阅读层这件事没有任何前序轮次要求过**,所以「本轮结清 0」是轮次性质,不是执行力。 |
| `本轮部分结清` | 1 | **认可**(`H-R11D-C-b`)。 |
| `不归属本轮·转R12装订` | 28 | **认可**。抽查 3 条(`H-R11D-B-e`、`H-R11C-F-c`、`H-R11C-F-d`),均确为「要改 `chapters/` 正文」,而本轮边界写死零改动。 |
| `不归属本轮·转内容轮` | 60 | **认可,但按下面的收件人纪律重指**:这 60 条原去向多为「下一轮内容轮」,同样是序数式收件人。它们的条件是**该内容轮覆盖到对应子系统时**。 |
| `存疑·交主线裁定` | 25 | 逐条裁定见 §2。 |

**片 C 独立撞到、主线已自查更正的一条**:「跨章原则清单曾实测 15/17 失同步」在语料里没有出处。
片 C 的搜索面比主线探针**更宽**(`.md/.txt/.py/.tsv` vs 只 `*.md`),并指出
`data/r11c/f-pre-binding-inventory-staleness.txt` 有 10 处 `15/17`——主线复核:
那 10 处**全部是同一条 `H-R11B-C-a` 表格行的重复副本**(片 F 的普查按命中文件重复整表),
**结论不变,但当时那条负结论的搜索面确实不完备**,已把探针扩到四种扩展名并加负向前瞻
(`15/17(?!\d)`,否则 `15/171 个候选够长` 会被误吞 13 处)。按片 C 建议**不铸号**。

## 1. 总裁定:「下一轮」不是收件人

那 25 条的共同形状是:R11D 把去向写成「下一轮」「下一个动 `scripts/` 的轮次」
「下一轮制度位 / 派工书 / 开工杂项」。落到的这一轮是**阅读层轮**,于是:

- **字面上全部命中**——本轮确实动了 `scripts/`(新增两个)、确实加了制度条、确实有开工杂项;
- **实质上一条没动**——本轮改动面里没有 `verify_citations.py`、没有
  `verify_evidence_commands.py`、没有 `data/ledger.tsv`、没有 `data/r10/`、没有任何历史 `notes/`。

**裁定:收件人一律改为条件式**(已入册 CLAUDE.md)。下面把 25 条重指到五个**由条件定义**的
收件人,每条写明**触发条件**——即「什么时候它必须被做」,而不是「谁下一个」。

## 2. 二十五条逐条

### 收件人甲 · 改动引用/证据关卡的那一轮(9 个号 / 8 个实体)

**触发条件:任何一轮修改 `scripts/verify_citations.py` 或 `scripts/verify_evidence_commands.py`
时,必须同批处理本组。** 理由:这一组全部是这两个关卡自身的判据缺陷,分散修会让
「改了关卡却没改它已知的盲区」重演;而关卡一改,全语料读数就会变,那正是该一次把账对齐的时刻。

| 号 | 处置结论 | 一句话现象 | 锚点 |
|---|---|---|---|
| `H-R11B-D-a` + `H-R11D-M-c` | **并案** → 本轮铸 `H-R11E-M-a`,转甲 | 同一实体两个号:`resolve()` 只认基线与本仓库两棵树,第三方 pip 包的**正确**引用被报成 `MISSING-FILE`(3 处,同一份 `notes/r6-60`) | `notes/r11d-raw-handover-disposition.md:399` 的 `H-R11B-D-a` |
| `H-R11B-D-b` | 转甲 | 「每行以自己行号开头」的行号栏体例块校验器无法比对,R11B 临时改标 ```text 未改回 | `notes/r11d-raw-handover-disposition.md:400` 的 `H-R11B-D-b` |
| `H-R11C-C-a` | 转甲 | `NOFENCE` 遇块内字面三反引号会截断块,本来配对的块被记成未配对 | `notes/r11d-raw-handover-disposition.md:278` 的 `H-R11C-C-a` |
| `H-R11C-C-e` | 转甲 | 输出里一个 `->` 被 `REDIRECT_WRITE` 读成写重定向,整块判 MUTATING 永不执行 | `notes/r11d-raw-handover-disposition.md:282` 的 `H-R11C-C-e` |
| `H-R11C-D-c` | 转甲 | 「解析成功」是假保证:1,543 处裸锚点解析到仓库根同名文件 | `notes/r11d-raw-handover-disposition.md:284` 的 `H-R11C-D-c` |
| `H-R11C-D-i` | 转甲 | `citations()` 无左侧 lookbehind,绝对路径被从中间切一刀(全语料 12 处) | `notes/r11d-raw-handover-disposition.md:289` 的 `H-R11C-D-i` |
| `H-R11D-A-a` | 转甲 | 一句以三反引号开头的散文翻转其后整份文件的围栏奇偶,从此一条锚点不扫 | `reports/round-11d-pre-binding-prereq.md:832` 的 `H-R11D-A-a` |
| `H-R11D-A-b` | 转甲 | 一个锚点挂五处各取一行的合成摘录,撞上 BLOCK-DRIFT 的单起点契约 | `reports/round-11d-pre-binding-prereq.md:833` 的 `H-R11D-A-b` |

### 收件人乙 · 把移交普查提升为 `scripts/` 关卡的那一轮(6 条)

**触发条件:任何一轮把移交普查从 `data/*/probes/` 提升为 `scripts/verify_handover_*.py` 时。**
理由:这六条互相咬合——案号正则、声明位判据、处置列、表头识别、铸号落点、
无号改判——分开修任何一条都会被另一条的口径吃掉。

| 号 | 处置结论 | 一句话现象 | 锚点 |
|---|---|---|---|
| `H-R11D-C-a` | **本轮部分结清**,余下转乙 | 机械口径把「已处置」等同「已结清」,R11D 那 100 条「转 X」因此在账面上消失。**本轮已入册**「移交表必须有机器可读的处置列」并给出实做(`verdict` 五选一);**普查器仍不读这一列**,那一半转乙 | `reports/round-11d-pre-binding-prereq.md:842` 的 `H-R11D-C-a` |
| `H-R11D-B-a` | 转乙 | 案号正则匹配不了三段式片内号:177 个号 / 276 次出现对普查完全隐形,比它能看见的 178 个还多 | `reports/round-11d-pre-binding-prereq.md:837` 的 `H-R11D-B-a` |
| `H-R11D-C-c` | 转乙 | 案号正则与案号纪律互斥,且 137 行真移交表因表头认不出而不计入 | `reports/round-11d-pre-binding-prereq.md:844` 的 `H-R11D-C-c` |
| `H-R11C-B-d` | 转乙 | `rulings_census.py` 的 `is_decl()` 用子串匹配判声明位,案号总数偏高 | `notes/r11d-raw-handover-disposition.md:276` 的 `H-R11C-B-d` |
| `H-R11C-M-a` | 转乙 | 治了症状未治根:发现面扩了,铸号仍无单一落点,那张 64 条登记表未执行 | `notes/r11d-raw-handover-disposition.md:191` 的 `H-R11C-M-a` |
| `H-R11C-E-f` | 转乙 | 定案级改判行普查在 `CLAUDE.md` 上报 0 行,而那里确有一条改判(制度文件的改判不带号) | `notes/r11d-raw-handover-disposition.md:292` 的 `H-R11C-E-f` |

### 收件人丙 · 下一个开「历史产出清理片」的轮次(6 条)

**触发条件:任何一轮派出以修改历史 `notes/` / `reports/` / `reviews/` 为任务的分片时。**
理由:这六条都要动历史产出,而历史产出是**多片并发编辑最容易撞车**的地方
(R9B / R10B / R11A 连续三轮在这上面翻车),必须由一个专门的片一次做完。

| 号 | 处置结论 | 一句话现象 | 锚点 |
|---|---|---|---|
| `H-R11D-A-e` | 转丙 | `reports` 87 + `reviews` 17 = **104 处**多候选裸锚点一处未动 | `reports/round-11d-pre-binding-prereq.md:836` 的 `H-R11D-A-e` |
| `H-R11D-M-b` | 转丙 | **30 处**把自引路径挂在基线 sha `863e313` 上(类别错误:该 sha 指的是另一个仓库) | `reports/round-11d-pre-binding-prereq.md:829` 的 `H-R11D-M-b` |
| `H-R11D-A-d` | 转丙 | `reviews/review-1-full-corpus.md:643` 的自引锚点无钉子,校验器 ±40 窗口原理上够不到 | `reports/round-11d-pre-binding-prereq.md:835` 的 `H-R11D-A-d` |
| `H-R11C-C-f` | 转丙 | 5 处配对 verify 块漂移(命令与贴出的输出对不上),分散在 5 份历史底稿 | `notes/r11d-raw-handover-disposition.md:283` 的 `H-R11C-C-f` |
| `H-R11C-E-e` | 转丙 | `notes/r11b-raw-rulings-census.md:783` 表内锚点 `:700` 真实位置是 `:730`,差 30 行 | `notes/r11d-raw-handover-disposition.md:291` 的 `H-R11C-E-e` |
| `H-R11C-E-d` | 转丙 | R8C 已推翻的「静默抹掉」定性被写进 `data/r10/dispatch-brief.md`,且那半句是掉了不是被改正 | `notes/r11d-raw-handover-disposition.md:290` 的 `H-R11C-E-d` |

### 收件人丁 · 下一次改 `CLAUDE.md` 的轮次(3 条)

**触发条件:任何一轮新增或修改 CLAUDE.md 的证据规则时。**

| 号 | 处置结论 | 一句话现象 | 锚点 |
|---|---|---|---|
| `H-R11C-C-b` | **本轮部分结清**,余下转丁 | 生产者块带 `tee` 判 MUTATING 永不跑,消费块每次都跑,必然报错。**本轮已做两件**:(a) 三份派工书均写入「凡数必配输出块」;(b) 把「派工书必须落库」入册并补出 `data/r11e/dispatch-brief.md`,使该条**今后可机械核验**。**「证据块不得依赖另一个块产生的文件」这一条本身尚未入册 CLAUDE.md**,转丁 | `notes/r11d-raw-handover-disposition.md:279` 的 `H-R11C-C-b` |
| `H-R11C-C-d` | 转丁 | 证据块里的省略号吃掉了产生输出的 `print` 与脚手架,重建必须猜;「省略号只能省别处逐字写过的部分」未入册 | `notes/r11d-raw-handover-disposition.md:281` 的 `H-R11C-C-d` |
| `H-R11D-A-c` | 转丁 | use-mention 盲区:锚点被当作**讨论对象**时,机械补全会让该句自我否定;「同类批量作业须有人工复核环节」未入册 | `reports/round-11d-pre-binding-prereq.md:834` 的 `H-R11D-A-c` |

### 收件人戊 · 下一个改动 `data/ledger.tsv` 的轮次(1 条)

**触发条件:任何一轮改动台账 `status` 列时。** 本轮边界写死「台账 status 不因本轮变更」,
所以本轮**原理上**做不了。

| 号 | 处置结论 | 一句话现象 | 锚点 |
|---|---|---|---|
| `H-R11B-B1-e` | 转戊 | 片 B1 12 个 + 片 B2 26 个 = **38 个**文件的台账 `status` 仍是 `R7B-deep-read` 等旧值,没反映 R11B 的重读 | `notes/r11d-raw-handover-disposition.md:254` 的 `H-R11B-B1-e` |

## 3. 本轮新铸的号(3 个,均带轮次标识)

| 号 | 现象 | 去向(条件式) | 锚点 |
|---|---|---|---|
| `H-R11E-M-a` | `H-R11B-D-a` 与 `H-R11D-M-c` 是**同一实体**(同一份 `notes/r6-60`、同样 3 处第三方包锚点、同一条修法),两个号各自在账上活着,任一处被标结清,另一处**因号已闭而不会再被发现**——正是 R11B 案号纪律要防的形态 | 甲(改引用关卡的那一轮),并案后只留本号 | `notes/r11d-raw-handover-disposition.md:399` 的 `H-R11B-D-a` |
| `H-R11E-M-c` | `scripts/run_tests.sh` 不打印聚合 skipped 行,每一轮都要自己写一次解析,而两轮写出了两个口径(R11D 报 **132**,R11E 报 **239**;R11E 已直接复核单文件 `pytest -q` 给出 `11 skipped` 与自己的解析一致,而 R11D 的方法未落库、无从复跑) | 乙,或任一改 `scripts/` 的轮次:把 `data/r11e/probes/test_totals_r11e.py` 收进 `scripts/` | `data/r11e/probes/test_totals_r11e.py:1` 的 `R11E · 从 run_tests.sh 完整日志汇总 passed / failed / skipped` |
| `H-R11E-M-b` | 问题索引的粒度只到 H3,而 `chapters/r8a-configuration-surface.md` 的 `4. 可迁移的设计原则` 是一个 **385 行、无任何 H3 子节**的 H2,索引只能把读者送到它门口(本轮 3 条索引指向它) | R12 装订轮:切 H3 后这 3 行可直接改指 | `chapters/r8a-configuration-surface.md:1253` 的 `## 4. 可迁移的设计原则` |

## 4. 如实申报:本文件没做的

- **片 C 未复核 R11D 已关闭的 40 条**,主线也未复核——本轮不重开已结清账。
- **60 条「转内容轮」只做了收件人形式复核**,未逐条取证其实质;它们的实质取证条件是
  对应内容轮覆盖到该子系统时。
- `H-R11D-C-b` 名下 113 行片 C 只读了铸号行,主线未加核。
- 原则层 59 条 + 5 组冲突裁定,片 C 只抽查了四个串、未通读;**主线自己是作者**,
  故本条不构成独立复核——如实记下这一点,不假装它被第二双眼睛看过。
