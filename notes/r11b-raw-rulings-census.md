# r11b-A · 跨轮定案账普查 —— 去重(A-1)与「后轮覆盖已证伪结论」(A-2)

> 本片是 R11B 的**清账**片,不读新代码。产出两件事:
> (A-1)全语料找出「同一处代码 / 同一条断言被立了多个案号」与「同一个案号指了多件不同的事」;
> (A-2)普查「后轮把前轮已证伪的结论 / 修法重新写成结论」。
>
> **溯源约定**:对 hermes-agent 的断言,锚点写 `路径:行号 @ 863e313`,单独成行、置于块前,
> 块内是**逐字源码**。**对本学习仓库自己的产出**(`reports/` `notes/` `chapters/`)一律用
> **`>` 引用块**,不用围栏块 —— 引用块的契约是「找不到就记 UNCHECKED,不判失败」,
> 而本轮的片 C(改 `chapters/` 锚点排版)与片 D(改 41 份历史 `notes/` 的引用)
> **正在同一棵工作树上改行号**。本片引到的每一份产出都**不在**片 C / 片 D 的清单里
> (逐份对过 `data/inflight/*.claim`),所以这些引用现在是 OK 而不是 UNCHECKED;
> 用引用块只是把「万一被改到」的后果从**阻断**降成**记一条 UNCHECKED**。
> 命令输出与本片自造的时间线表用 ```` ```text ```` / ```` ```verify ````,它们不是摘录。
>
> **语料快照**:本片所有计数都在 **`00f09bf`**(R11B 派工那一条 commit)上算,不是工作区。
> 三个探针都把这个 SHA 写死在 `CORPUS_REV` 里,可用 `R11B_CORPUS_REV=` 覆盖。
> 理由同上 —— 与片 C/D 并行,从工作区读会让本底稿的每一个数随它们的进度漂移。

---

## 0. 结论速览

1. **A-1 去重**:去重前(语料自报口径)约 **1,006 条定案**;本片逐条裁决 **10 个合并组**,
   涉及 **32 个案号**(其中 **19 个是定案号**),合并后剩 **10 个实体**,
   **定案号净减 9**,故去重后 **≤ 997 条**。机械候选共 **92 簇**(跨 ≥2 轮),
   本片只裁了其中 10 组,**其余 82 簇未逐一裁决,本片不外推**。
2. **A-1 第二物种(同一案号多实体)**:探针报 **39 个移交号**被 ≥2 处独立铸造,共 **100 个实体**,
   **净多铸 61**。最坏的是 `H-R10B-a` … `H-R10B-g` 这 7 个号,人工核实**各被 3 处**独立铸造
   (探针只数到 2,原因见 §2.5);`H-1` … `H-7` 这 7 个 R8A 主线号,各有 **3–4 个实体**。
   **这个物种与第一个物种方向相反:它让语料自报的移交项数偏低,不是偏高。**
3. **A-2 命中 2 条**(搜索面见 §3.1,三条互补路径,均给出命中数):
   - **A2-1**(派工书给出的种子案):R9C 用本地双服务实验证伪的「只比对 `self._base_url` 就够」,
     在 `notes/r11a-90-handover-rulings.md:70` 被重新写成结论;R11A 全部产出里
     **0 处**提及 302 / 跨源重定向 / `hermes_cli/urllib_security.py`。
   - **A2-2**(本片新发现):R8C 证伪的「静默消失」定性,在 **R8D 的两份底稿**里被当作已定事实再次使用,
     两处都以 `CLAUDE.md` 为出处 —— 而 `CLAUDE.md` 的那句话写于 R8-fix、**在 R8C 改判后从未更新**。
4. **A-2 的成因就是 A-1**:R9C 把改判归档在 `H-R9A-a` 名下(并当场声明 `H-R9A-a` = `H-R9B-d`),
   R10 / R10B 只把 `H-R9B-d` 这个号转下去,R11A 拿着 `H-R9B-d` 回到 R9B 的移交表取原始表述,
   **走不到 R9C 的定案卷**。同一实体的两个案号,把一次改判切断了。
5. **给主线的更正建议**见 §3.6:**不改 `■-R11A-01` 的正文实质**(它成立),而是补一条
   「修法约束」并把 `H-R9A-a` 列为其别名 —— 这样下一次拿到任一案号都能走到同一份卷宗。

---

## 1. 口径(A-1 / A-2 共用)

### 1.1 语料面

`reports/*.md` + `notes/*.md` + `chapters/*.md`,快照 `00f09bf` 上共 **266 份**
(已排除 `notes/r11b-*` —— 本轮各片正在写的文件,含本底稿自己)。

**不含 `reviews/`,理由要写出来**:`reviews/review-1-full-corpus.md` 是独立评审位对**本学习仓库产出**
的评审,它的 ▲ / ■ 指向的是「报告写错了」而不是「hermes-agent 有缺陷」,与本普查的计数单位不同质;
且 CLAUDE.md 定了 `reviews/` 原文不改。它的处置结果已经以 `M-1` … `M-27` 的形式
落进 `reports/round-8-fix-review-1.md`,而那份**在语料面里**,所以评审位的产出并没有被漏掉,
只是按「处置后的形态」计数一次。

**不含 `CLAUDE.md`** 作为计数对象(它不立案号),但 §3.3 把它作为**传播路径**单独取证 ——
这是本片唯一一次把它拉进来。

### 1.2 什么算「一条定案」:案号的四个家族

记号体系跨轮不一致,四种写法都要收:

| 家族 | 形态 | 例 | 作用域 |
|---|---|---|---|
| **H** 移交号 | `H-<轮次或序号>[-后缀]` | `H-7`、`H-R9A-a`、`H-R10B-C-j` | 全项目(理论上) |
| **G** 全局定案号 | 记号 + 轮次 + 序号 | `■-R8B-12`、`▲-R11A-01`、`◇-R8C-a` | 全项目 |
| **S** 片内定案号 | 记号 + 片字母 + 序号 | `■-H-1`、`▲-G-01`、`▲ B-2` | 该片底稿 |
| **L** 轮内裸序号 | 记号 + 裸序号 | `■-1`、`▲2`、`◇-12` | **该文件内** |

**L 家族必须按文件定作用域**:`notes/r9b-raw-pet.md` 的 `■-1` 与 `notes/r9b-raw-tts.md` 的 `■-1`
是两件不同的事。不这么定,全语料会算成同一条。

**S 家族与 H 家族形状撞车**,这一点值得单记:`■-H-1`(R10B 片 H 的第 1 条 ■)与
`H-1`(R8A 的主线移交号)在纯文本里只差一个前缀记号。本片的探针按
**S > G > H > L** 的优先级切分,否则 `▲-H-1` / `◇-H-1` / `◎-H-1` / `■-H-1` 会各贡献一个假的 `H-1`。

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11b/probes/rulings_census.py --summary
```

```text
语料面 ['reports', 'notes', 'chapters'];文件数 266
案号(作用域后)总数 1449;声明位总数 2214
   H  移交号: 278
   G  全局定案号: 48
   S  片内定案号: 99
   L  轮内裸序号: 1024
```

### 1.3 什么算「重复」

按 **(锚点文件, 断言实质)** 判,**不按案号、也不按行号**。理由是语料里现成的反例:同一条缺陷
R9A 锚 `gateway/relay/media.py:92`(函数头)、R9B 起锚 `:94`(那句 `in`),
按行号判会判成两条;而 `H-R9C-d` 与 `■-R11A-01` 锚的是**同一片代码**(中继媒体判定)却是两条
不同断言(前者说测试替身重抄了被测谓词,后者说谓词本身错),按文件判又会误并。

于是本片用**两步**:探针按 (锚点文件, 行号 ±30) 生成**候选簇**,人逐簇读正文判断断言实质。
**探针只负责不漏,判断由人做**,这一点在报数时如实说。

### 1.4 探针与可复现性

三个探针,都在 `data/r11b/probes/`,都自己用 `git rev-parse --show-toplevel` 推仓库根、
用 `git show <CORPUS_REV>:<path>` 读语料:

| 探针 | 作用 |
|---|---|
| `rulings_census.py` | 案号家族汇总;`--clusters` 生成第一物种候选簇;`--species2`、`--id`、`--file` |
| `rulings_id_collisions.py` | 第二物种:按**铸号位**(带锚点的登记行)判同号多实体 |
| `rulings_reversal_scan.py` | A-2:`--reversals` 改判语普查、`--ledger` 定案级改判台账、`--casepass` 案号法 |

---

## 2. A-1:定案去重普查

### 2.1 去重前总数

「去重前总数」取**语料自报口径** —— 各轮报告自己声称的定案数之和。这是一个读者照着报告加一遍
就能得到的数,也是唯一有出处的数。

| 轮次 | 自报 | 出处(本仓库) |
|---|---|---|
| R1 | 54 | `reports/round-1-survey.md:582`:`### 2.16 文档-代码冲突汇总(独立冲突条目,共 54 条)`|
| R2 | 16 | `reports/round-2-turn-loop.md:66`:`## 4. 文档-代码冲突定案(R2 范围,16 条)`|
| R3 | 12 | `reports/round-3-tool-infrastructure.md:72`:`## 6. 文档-代码冲突定案(R3 范围,10 条 + 2 新发现)`|
| R4 | 8 | `reports/round-4-execution-environments.md:83`:`## 4. 文档-代码冲突定案(R4 范围,8 条)`|
| R5 | 20 | `reports/round-5-session-state-and-persistence.md:82`:`## 4. 文档-代码冲突定案(R5 范围,20 条)`|
| R6 | 12 | `reports/round-6-memory-provider-ecosystem.md:74`:`## 4. 文档-代码冲突定案(R6 范围,12 条)`|
| R7 | 17 | `reports/round-7-gateway-session-core.md:75`:`## 4. 文档-代码冲突定案(R7 范围,7 条遗留定案 + 10 条新立,详见 notes/r7-90)`|
| R7B | 24 | `reports/round-7b-platform-integration.md:92`:`## 4. 文档-代码冲突定案(24 条:▲ 7 / ◇ 17;详见 notes/r7b-90)`|
| R7C | 41 | `reports/round-7c-gateway-periphery-and-scheduling.md:86`:`## 4. 定案(`notes/r7c-90`,41 条:▲ 21 / ◇ 14 / ■ 6)`|
| R8A | 71 | `reports/round-8a-configuration-surface.md:284`:`## 4. 定案(`notes/r8a-90`,71 条:▲ 10 / ◇ 6 / ■ 55;另**驳回 1 条、收窄 1 条**)`|
| R8C | 48 | `reports/round-8c-dashboard-and-web.md:280`:`**本轮新立 ■ 13 条、◇ 20+ 条、▲ 10 条、◎ 5 条;跨轮改判 1 条、跨段仲裁 2 条。**`|
| R8D | 57 | `reports/round-8d-cli-completion.md:129`:`**记号合计:▲ 15 / ◇ 20 / ■ 19 / ◎ 3**(逐条证据在各底稿,定案在 `notes/r8d-90-rulings.md`)。`|
| R9A | 143 | `reports/round-9a-capability-organization.md:189-203` 的十三簇表加总 |
| R9B | 59 | `reports/round-9b-multimodal-delivery.md:176`:`合计 59 条。**六簇各自计数,未做跨簇去重**,合计数不宜直接用于跨轮比较。`|
| R9C | 81 | `reports/round-9c-external-interfaces.md:257`:`六片底稿合计 **81 条**:**■ 37 / ▲ 12 / ◇ 28 / ◎ 4**(逐条带锚点,在各片底稿的发现清单)。`|
| R9D | 96 | `reports/round-9d-l1-completion.md:203`:`六片底稿合计 **96 条**:**■ 48 / ▲ 11 / ◇ 31 / ◎ 6**(逐条带锚点,在各片底稿的发现清单)。`|
| R10 | 93 | `reports/round-10-client-interface-layer.md:188`:`\| 主线另立 ■-R10-01 \| +1 \| \| \| \| **93** \|`|
| **小计** | **852** | 17 轮 |

**另有 4 轮没有自报定案数**(R8-fix / R8B / R10B / R11A):它们的报告里只有分条目的定案节,
没有一个合计数。本片按与上表**同一种方式**(每份底稿内的定案号按 (文件, 案号) 计一次,
加上报告与登记卷自己新立的)机械补数:R8-fix **1**、R8B **31**、R10B **92**、R11A **30**,
合计 **154**。

> **去重前总数 ≈ 852 + 154 = 1,006 条。**

**这个数为什么只能是「约」,三条都要说清:**

1. **R1–R4 用的是无记号的编号表**(`| 9 | FailoverReason 驱动恢复未见于文档(R1 ◇) | 证实 | …`),
   机械扫记号一条也扫不到;它们的数只能取报告的自报值。
2. **各轮口径自己就不一致,而且有的轮次已经声明过**。R9A 明写「未做全量跨簇去重,
   上表按簇原样列出,合计数不宜直接相加」;R9B 明写「六簇各自计数,未做跨簇去重」。
3. **底稿与登记卷会重复登记同一条**。R7C 是最极端的:自报 41 条,而机械扫 (文件, 案号)
   得 214 条 —— 差额基本全是「一条 ▲ 在片底稿里叫 `▲-1`、在 `notes/r7c-90-*` 里叫 `▲-4`」这种。
   §2.3 的 M-7 就是这一形态的样本。

### 2.2 机械候选:同一处代码被多个案号声明

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11b/probes/rulings_census.py --clusters --window 30 --min-rounds 2 --summary && python3 data/r11b/probes/rulings_census.py --clusters --window 30 --min-rounds 3 --summary
```

```text
# 同一处代码(同文件 ±30 行)被 ≥2 个案号、跨 ≥2 轮声明:92 簇
# 同一处代码(同文件 ±30 行)被 ≥2 个案号、跨 ≥3 轮声明:9 簇
```

跨 ≥3 轮的 9 簇按案号数排序,头三簇是:`gateway/relay/media.py`(7 个案号 / 6 轮)、
`hermes_cli/config.py:3065-3092`(9 个案号 / 4 轮)、`gateway/pairing.py:414-437`(5 个案号 / 3 轮)。
本片逐簇读正文裁决,结果见下。

### 2.3 逐组裁决:10 个合并组

**保留规则见 §2.6。** 表里「号数」含移交号,「定案号」只数 ▲◇■◎。

| 组 | 实体(一处代码 / 一条断言) | 涉及案号 | 号数 | 定案号 | 建议保留 |
|---|---|---|---|---|---|
| **M-1** | 中继媒体 bearer 用**子串**决定发不发 | `■-01`(R9A)、`H-R9A-a`、`H-R9B-d`、`■-R11A-01`、`H-R11A-a` | 5 | 2 | `■-R11A-01` |
| **M-2** | `_SECRET_SOURCES` 两条写路径只有一条持锁 | `H-R8C-d`、`H-R8D-c`、`■-R9A-01` | 3 | 1 | `■-R9A-01` |
| **M-3** | `cache/op_cache.json` 不在读禁清单,可被挂进沙箱 | R9C `■-1`、R9D `■-2`、`H-R9D-B-b` | 3 | 2 | R9D `■-2`(超集) |
| **M-4** | 配对存储路径过时(模块 docstring + CLI 恢复提示) | R7C `▲3`、R8A `◇3`、R8A `◇6` | 3 | 3 | R7C `▲3`(先立) |
| **M-5** | 第一层守卫「设置中断事件」不存在 | R7 `▲21-1`、R7B `▲ B-1`、r7b 章 `▲1` | 3 | 3 | R7B `▲ B-1`(定案轮) |
| **M-6** | `running` 是文档里的幽灵状态 | r7c-sched-a `▲-1`、r7c-sched-b `▲-1`、r7c-90 `▲-4` | 3 | 3 | `▲-4`(登记卷已统号) |
| **M-7** | LSP 外层预算 < 内层 | R9D `■1`、`H-R9D-A-a`、`H-R9D-a` | 3 | 1 | `H-R9D-a`(R11A 已结清) |
| **M-8** | think scrubber 不认带属性的推理标签 | R9D `■-4`、`H-R9D-F-b`、`H-R9D-c` | 3 | 1 | `H-R9D-c` |
| **M-9** | dashboard `install_specs` 的 external 分支无过滤 | `H-R8C-g`、`■-R10-01`、`H-R10-d` | 3 | 1 | `■-R10-01` |
| **M-10** | `AGENTS.md` toolset 清单与代码不符 | R9A `▲-3`(moa 底稿)、r9a 章 `▲4`、`H-R9A-g` | 3 | 2 | `H-R9A-g`(R9D 已改判) |
| **合计** | **10 个实体** | | **32** | **19** | **定案号净减 9** |

下面逐组给证据。**只有 M-1 / M-3 / M-4 / M-5 / M-6 是跨轮重复**,其余五组是同轮内多号。

---

#### M-1 中继媒体 bearer(5 个案号,跨 6 轮)

判定函数只做子串包含,没有主机比较:

`gateway/relay/media.py:92-94 @ 863e313`

```python
    def is_relay_media_url(self, url: str) -> bool:
        """Is ``url`` a connector re-host reference (needs our bearer to GET)?"""
        return "/relay/media/" in (url or "")
```

它的唯一消费者就是「要不要挂 bearer」:

`gateway/relay/media.py:164 @ 863e313`

```python
        needs_auth = self.is_relay_media_url(url)
```

而正确的比较值就在同一个类的构造里:

`gateway/relay/media.py:80 @ 863e313`

```python
        self._base_url = base_url.rstrip("/")
```

**同一件事被立了 5 个号**,时间序:

```text
R9A  ■-01        reports/round-9a-capability-organization.md:163   主线定案
R9A  H-R9A-a     reports/round-9a-capability-organization.md:321   移交表,锚 media.py:92
R9B  H-R9B-d     reports/round-9b-multimodal-delivery.md:454       移交表,锚 media.py:94(重新铸号)
R9C  (改判)      notes/r9c-90-handover-rulings.md:11               表头写「H-R9A-a = H-R9B-d」
R11A ■-R11A-01   reports/round-11a-ops-and-delivery.md:494         「由 H-R9B-d 升格」
R11A H-R11A-a    notes/r11a-90-handover-rulings.md:413             移交 R11B
```

**R9A 一轮之内就铸了两个号**(`■-01` 定案 + `H-R9A-a` 移交),这是本项目的结构性来源:
**一条「既定案又移交」的条目天然拿两个号**。R9C 在表头声明过 `H-R9A-a` = `H-R9B-d`:

`notes/r9c-90-handover-rulings.md:11`

> | **H-R9A-a** = **H-R9B-d** | R9A 移交(去向写「R9C 或立即」),R9B 已取证 | **改判:维持 ■,但移交项给的修法不足以修好它**;正确修法已在仓库内,实测有效 |

**不并入本组的两条,理由各写一句**:

- **`H-R9C-d`** 锚的是测试替身 —— 它把被测谓词逐字抄了一遍,于是替身永远同意本体:

  `tests/gateway/relay/test_relay_media.py:72-73 @ 863e313`

  ```python
      def is_relay_media_url(self, url: str) -> bool:
          return "/relay/media/" in (url or "")
  ```

  断言是「测试替身重抄了被测谓词,于是关卡长期空绿」—— 讲的是**测试的形态**,不是谓词本身错。
  R10 自己也把两者并列而不合并(`reports/round-10-client-interface-layer.md:135`
  写「与同处代码的 H-R9C-d 同轮做」)。**同处代码 ≠ 同条断言。**
- **`gateway/relay/adapter.py:471` / `:477`** 的两处同形态子串判断:

  `gateway/relay/adapter.py:471 @ 863e313`

  ```python
                      if "/relay/media/" not in url:
  ```

  R11A 已经把它们写在 `■-R11A-01` 的同一条里(「同形态在 … 另有 2 处」),
  **它们是一条定案的三个位点,不是三条定案**。

#### M-2 `_SECRET_SOURCES` 的锁不对称(3 个案号)

无锁的那条写路径:

`hermes_cli/env_loader.py:666 @ 863e313`

```python
            _SECRET_SOURCES[name] = applied.source
```

R8C 铸 `H-R8C-d` 移交 R8D;R8D 没结清,**改铸 `H-R8D-c`** 再移交 R9;R9A 一次把两个号一起结清并定
`■-R9A-01`。R9A 的底稿标题自己就把两个号写在一起:

`notes/r9a-h-r8d-c-env-loader-lock.md:1`

> # r9a 底稿 · 结清 H-R8D-c / H-R8C-d —— `_SECRET_SOURCES` 的两条写路径与那把只有一边拿的锁

**这是「未结清就换号」的样板**:R8D 只是把 R8C 的移交项原样续转,却给了新号,
于是同一件事在移交账上占两格。合并规则(§2.6 R-2)正是从这里来的。

#### M-3 `op_cache.json` 不在守卫表(3 个案号,跨 R9C / R9D)

读禁清单里有 Bitwarden 的明文缓存,没有 1Password 的:

`agent/file_safety.py:274-285 @ 863e313`

```python
    credential_file_names = (
        "auth.json",
        "auth.lock",
        ".anthropic_oauth.json",
        ".env",
        "webhook_subscriptions.json",
        os.path.join("auth", "google_oauth.json"),
        # Bitwarden Secrets Manager disk cache: stores plaintext secret values
        # to avoid re-fetching across back-to-back CLI invocations. The file
        # was introduced by #31968 but not added to this guard.
        os.path.join("cache", "bws_cache.json"),
    )
```

R9C 在 `notes/r9c-raw-secret-sources.md` 立 `■-1`(带实跑复现),
R9D 在 `notes/r9d-raw-file-io-safety.md` 立 `■-2` 并另铸 `H-R9D-B-b`。
**R9D 自己知道这是同一条**,写在小节的第一句里:

`notes/r9d-raw-file-io-safety.md:1344`

> **强度:实跑复现。**(这条结清 R9C D 片 ■-1 在本片的部分)

**保留 R9D `■-2`**:它是超集 —— R9C 只查了读禁清单一张表,R9D 逐一核了四张
(读禁 / 写禁 / 媒体投递禁 / 面板文件 API 禁),并给了搜索面。
**这是「后轮加重」而不是「后轮重复」的正例,但账上仍是两个 ■,跨轮 ■ 计数因此多算一条。**

#### M-4 配对存储路径过时(3 个案号,跨 R7C / R8A,**且记号不一致**)

模块 docstring 说存在旧路径:

`gateway/pairing.py:18 @ 863e313`

```
Storage: ~/.hermes/pairing/
```

实际新装走的是 `platforms/pairing`:

`gateway/pairing.py:59 @ 863e313`

```python
PAIRING_DIR = get_hermes_dir("platforms/pairing", "pairing")
```

R7C 立 `▲3`「配对数据存储路径过时」:

`notes/r7c-raw-authz-pairing.md:1640`

> ### ▲3 配对数据存储路径过时

它的正文同时点了 `gateway/pairing.py:18` 的 docstring **和** CLI 里那条硬编码新路径的恢复提示:

`hermes_cli/pairing.py:96-97 @ 863e313`

```python
            "  To reset sooner, delete the '_lockout:{0}' entry from "
            "~/.hermes/platforms/pairing/_rate_limits.json\n".format(platform)
```

R8A 又把 docstring 那一半单独立成 `◇3`:

`notes/r8a-raw-pairing-and-config-cmd.md:1229`

> | ◇3 | `gateway/pairing.py:18` 模块 docstring "Storage: ~/.hermes/pairing/" | 新装实际是 `~/.hermes/platforms/pairing/`（`gateway/pairing.py:59` + `hermes_constants.py:280`） | **源码内自述过时**，只对老装成立 |

把 CLI 提示那一半立成 `◇6`。

**记号还不一致:R7C 记 ▲,R8A 记 ◇。** CLAUDE.md 把 ▲ 条数定义成
「贯穿各轮、用来衡量地图腐烂程度的跨轮指标」,一条断言在一轮记 ▲、在另一轮记 ◇,
**这个跨轮指标就不可比**。两个记号哪个对不是本片要裁的(源码内自述过时算不算「文档」是另一个问题,
它是 `H-R8D-h` 的正题),**本片只报「同一条断言被两轮用不同记号各记一次」这个事实**。

#### M-5 第一层守卫「设置中断事件」(3 个案号,跨 R7 / R7B)

三处指同一句文档:

`website/docs/developer-guide/gateway-internals.md:86 @ 863e313`

> 1. **Level 1 — Base adapter** (`gateway/platforms/base.py`): Checks `_active_sessions`. If the session is active, queues the message in `_pending_messages` and sets an interrupt event. This catches messages *before* they reach the gateway runner.

R7 在 `notes/r7-raw-run-05-gwr-queue-busy.md` 的「文档-代码冲突候选」节记 `▲21-1`(候选,未定案),
R7B 定案为 `▲ B-1`「证伪」,R7B 成品章又以 `▲1` 复述。

这一组是本项目**设计上就会产生**的形态:R7 记的是「候选」,R7B 记的是「定案」,
成品章记的是「本章第 1 条」。三个号各有正当理由。合并规则(§2.6 R-4)因此把它判为
**「不同层级的同一实体」——账上并成一条,但三处都保留、互为别名**,不删任何一处。

#### M-6 `running` 幽灵状态(3 个案号,**同轮内两份底稿撞号**)

在飞状态只存在于内存:

`cron/scheduler.py:334 @ 863e313`

```python
_running_job_ids: set = set()
```

R7C 的两份 cron 底稿**互不通气**,各自把这条立成 `▲-1`:

`notes/r7c-raw-cron-sched-a.md:491`

> ### ▲-1 `state: "running"` 是文档里的幽灵状态，代码从不写

`notes/r7c-raw-cron-sched-b.md:1405`

> ### ▲-1 `running` 不是真实的作业状态

R7C 的登记卷把它们统成 `▲-4`:

`notes/r7c-90-doc-conflict-rulings.md:300`

> - **▲-4** `cron-internals.md:73,92` 的 `running` 是**幽灵状态**:全仓 state 写入点

**这一组是好消息**:登记卷**已经**做了合并,R7C 自报 41 条而不是 214 条正是因为它统了号。
它同时说明:**去重是本项目已有的动作,只是没有跨轮做、也没有留下别名表。**

#### M-7 / M-8 LSP 预算与 think scrubber(各 3 个案号,同轮内)

`agent/lsp/manager.py:313 @ 863e313`

```python
            t = max(8.0, self._wait_timeout + 3.0)
```

`agent/think_scrubber.py:89 @ 863e313`

```python
    _OPEN_TAGS: Tuple[str, ...] = tuple(f"<{name}>" for name in _OPEN_TAG_NAMES)
```

两条都是 R9D 一轮内三个号:片底稿的 `■`(`■1` / `■-4`)、片自己的移交号
(`H-R9D-A-a` / `H-R9D-F-b`)、主线移交表的号(`H-R9D-a` / `H-R9D-c`)。
**形态与 M-1 里 R9A 的「■-01 + H-R9A-a」完全一样**:一条既定案又移交的条目拿两个号,
再加上片内铸号就是三个。

#### M-9 dashboard 装依赖(3 个案号,跨 R8C / R10)

`hermes_cli/web_server.py:5519-5521 @ 863e313`

```python
        if install_cmd:
            try:
                install = _run_setup_command(
```

R8C 铸 `H-R8C-g`「dashboard 会 pip install 任意依赖」;R10 结清它并**改述**,
新立 `■-R10-01`(pip 那一半有守卫,external 那一半没有),同轮又铸 `H-R10-d` 移交定级问题。
**三个号,一处代码,断言从「pip 任意」改述成「external 无守卫」——实质变了但对象没变。**

#### M-10 `AGENTS.md` toolset 清单(3 个案号,同轮内)

R9A 的 moa 底稿立 `▲-3`、成品章列 `▲4`、主线移交表铸 `H-R9A-g`。R9D 结清时把它
**拆成 24 个平台族 ◇ + 7 个能力 toolset ▲**,并更正了锚点范围。**本片只登记「同一条被三个号指过」**,
拆分本身是 R9D 的定案,不动。

### 2.4 剩余 82 簇:未逐一裁决,不外推

`--clusters` 给出 92 簇,本片裁了 10 组。**剩下 82 簇本片没有逐簇读正文**,
因此**不给「去重后总数」的外推值**。从抽样看,这 82 簇里既有真重复
—— 例如 CLI 配对命令里这一行,被 R8A 四个号(`■-6` / `■-8` / `■-24` / `◇6`)从四个角度各说了一次:

`hermes_cli/pairing.py:81 @ 863e313`

```python
    elif store._is_locked_out(platform):
```


也有大量「同一文件邻近处的不同断言」(如 `hermes_cli/web_server.py:12296-12321` 那一簇里,
`H-3` 讲鉴权层、`H-11` 讲 profile 作用域、`▲-2` 讲 docstring,三件事)。
**按比例外推会把后者也算成重复,那正是这条规矩要防的形状。**

### 2.5 第二物种:同一个案号指了多件不同的事

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11b/probes/rulings_id_collisions.py
```

```text
# 铸号位总数(带锚点的登记行):387
# 有铸号位的移交号:261
# 被 ≥2 处独立铸造(锚点不相交)的移交号:39,共 100 个实体,净多铸 61
```

**判据(比第一物种保守,漏报优于误报)**:只认**铸号位** —— 案号出现在行首(表格首格 / 加粗段首 /
小节标题)且**带着自己的锚点**。同一个号如果在两个不同产出文件里各这样登记过一次、
且两处锚点文件不相交,才算撞号。「同一条移交项的结清写在另一个文件里」不会被算成两个实体
(它们锚同一批文件)。

**三个亚种,各有不同的成因:**

**(a) 同轮不同片各铸一套(最普遍)。** R9B 的 `H-R9B-1` … `H-R9B-6` —— pet 片铸的第 1 号是看板状态表:

`notes/r9b-raw-pet.md:1389`

> | H-R9B-1 | `hermes_cli/pets.py:182`:`states = [s for s in STATE_ROWS if s in {e.value for e in PetState}]` | `--cycle` 实测只产出 `['idle','failed','waiting','review']`,漏 wave/jump/run(■-1) | 若 R10+ 做"回归型缺陷"专题,这是一个干净样本:同一行代码在 `STATE_ROWS` 换值前后行为不同 |

而语音输入片铸的同一个号是另一件事:

`notes/r9b-raw-voicein.md:1798`

> **H-R9B-1(必做,■-1 的收口)** ——

第 6 号同样撞:pet 片指网关的取消 token 集合、voicein 片指唤醒词喂音频接口。

`notes/r9b-raw-pet.md:1394`

> | H-R9B-6 | `tui_gateway/server.py:8225`:`_pet_cancelled: set[str] = set()` | 生成取消用一个模块级全局 set 存 token,未见清理策略 | 属网关簇,本轮只到边界为止;交给做 `tui_gateway` 的轮次 |

`notes/r9b-raw-voicein.md:1826`

> **H-R9B-6** —— `tools/wake_word.py:1439`:`def feed_audio(*, owner: object, pcm_int16) -> bool:`

R9A 的 `H-9A-1` … `H-9A-6` 更极端:**三份底稿**(`r9a-raw-learning-graph.md`、`r9a-raw-moa.md`、
`r9a-raw-skills-hub.md`)各铸了一整套同名的 6–8 个号。

**(b) 片内铸号与主线正式号撞。** R9B 主线在报告 §9 铸 `H-R9B-a` … `H-R9B-g`,
而 `notes/r9b-raw-tts.md:1741-1746` 与 `notes/r9b-raw-video.md` **又各铸了一套 a–f**。
`H-R9B-d` 因此在三个地方指三件事:主线的中继媒体 bearer、tts 底稿的 xAI 语音标签正则、
video 底稿的「插件侧 3 个 provider 未精读」。R9A 的 `H-R9A-a` … `H-R9A-d` 同型
(主线 + `r9a-h-r8d-b-kanban-db.md` + `r9a-raw-egress.md` 三套)。

**(c) 跨轮同号复用。** R8A 的主线移交号 `H-1` … `H-7`,被 `notes/r8d-raw-provider-identity.md:2702-2708`、
`notes/r9a-raw-delegate-tool.md:2844-2868`(只到 `H-6`)、
`notes/r9a-raw-research-pipeline.md:2298-2304` **各重铸了一整套**。
于是 `H-3` 这个号在语料里指**四件事**:R8A 的 dashboard 配对鉴权(R8C 已结清)、
R8D 的 provider slug 覆盖表、R9A 委派片的代码执行隔离、R9A 研究管线片的压缩逻辑重复。

**最坏的一组是 `H-R10B-a` … `H-R10B-g`,7 个号各 3 处独立铸造:**

```text
notes/r10-raw-tui-gateway-methods.md:1648-1654   R10 预先给下一轮铸的一套(tui_gateway/*)
reports/round-10b-desktop-application.md:702-708 R10B 主线移交表的一套(scripts/、data/)
notes/r10b-raw-capability-panels.md:1353-1359    R10B 片 H 自己铸的一套(apps/desktop/*)
```

而 R11A 结清了其中两个号:

`notes/r11a-90-handover-rulings.md:11`

> | **H-R10B-a** 无扩展名锚点 | **结清** | `scripts/verify_citations.py:245`:`EXTLESS_NAMES = frozenset({` + 负控 13 条断言 |

**「H-R10B-a 结清」这句话,在账面上读起来像三条都结清了,实际只结清了三分之一。**
另外两条至今没有任何一轮处置过 —— 一条是 RPC 方法的匿名 handler:

`tui_gateway/methods_session.py:1800-1801 @ 863e313`

```python
@method("pet.generate")
def _(rid, params: dict) -> dict:
```

另一条是桌面插件未声明 `defaultEnabled`:

`apps/desktop/src/plugins/gateway-pill/plugin.tsx:350 @ 863e313`

```tsx
const plugin: HermesPlugin = {
```

**而且不会有人发现它们没被处置** —— 因为号已经被标成结清了。
这是第二物种**唯一一处已经造成实质后果**的地方,列进 §移交。

**方向要说清**:第一物种让定案总数**偏高**(一件事数了多次);
第二物种让移交项总数**偏低**(多件事共用一个号,账上只占一格)。两者不能相互抵消。

**探针的误差如实说,三个方向都要交代:**

- **误报 4 个**:`H-17` / `H-R8D-e` / `H-R9A-g` / `H-R8C-f`。它们只是「同一条的结清写在另一个文件里」,
  锚点自然换了一批,不是撞号。**39 − 4 = 真撞号 35 个。**
- **漏报至少 1 个**:`H-R9B-6` 在 voicein 底稿的锚点写在标题**下一行之外**,被更窄的判据滤掉,
  但 §(a) 已逐字取证它确实撞号。所以真值 **≥35**。
- **实体数系统性偏低**:探针只认**基线里真实存在**的锚点,于是「锚点指向本学习仓库自己的
  `scripts/` / `data/`」的那些铸号位一个都不算。`H-R10B-a` … `H-R10B-g` 的第三处
  (`reports/round-10b-desktop-application.md:702-708`,锚 `scripts/verify_citations.py:169`、
  `data/r10b/probes/cite_ext_scan.py:60` 等)正是这样掉出统计的 —— **探针报 2 个实体,
  实际 3 个**,§(c) 上面那三行是人工核实的结果。**净多铸 61 是下界。**
- **一个已知的形状混淆**:`■-H-3`(R10B 片 H 的第 3 条 ■)在纯文本里含 `H-3`,
  本探针没有做 §1.2 那套 S/G/H/L 优先级切分(`rulings_census.py` 做了),
  于是 `H-3` 的 4 个实体里有 1 个是它。**同一个理由,两个探针的处理不同,这里点名。**

### 2.6 合并规则(建议定稿)

| # | 规则 | 依据 |
|---|---|---|
| **R-1** | **一条实体只保留一个「现行号」,其余全部作为别名保留、不删。** 现行号写在实体的最新一次定案处 | `reviews/` 与 `reports/` 都不许静默改写;删号会让历史引用悬空 |
| **R-2** | **现行号取「最后一次给出实质结论」的那个号**,不取最早的 | M-2:R9A 的 `■-R9A-01` 才带实测,R8C/R8D 两个号只是转手 |
| **R-3** | **「定案号 + 移交号」成对出现时,现行号取定案号**;移交号降为别名 | M-1 / M-7 / M-8 都是这个形态;移交号的语义是「还没做完」,做完了就该让位 |
| **R-4** | **候选簇 / 定案 / 成品章三层各自的号不算重复计数**,但要在实体上并成一条 | M-5:R7 的 `▲21-1` 是候选,R7B 的 `▲ B-1` 是定案,章里的 `▲1` 是叙述序号 |
| **R-5** | **同处代码但断言实质不同的,不合并**,并在两条里互相点名 | `H-R9C-d`(测试替身)vs `■-R11A-01`(谓词本身) |
| **R-6** | **一条定案的多个位点(同一错误形态被复制 N 次)算一条**,位点列在同一条里 | `gateway/relay/adapter.py:471` / `:477`,R11A 已这么做 |
| **R-7** | **片内铸号必须带片标识**(如 `H-R9B-D-1` 而不是 `H-R9B-1`) | §2.5 三个亚种全是没有片标识造成的;R9D 与 R10B 的片已经这么做了(`H-R9D-F-b`、`H-R10B-C-i`),**照抄它们即可** |

### 2.7 去重后总数

> **去重前 ≈ 1,006 条 → 本片裁决后 ≤ 997 条**(定案号净减 9)。

**「≤」不是修辞**:剩余 82 簇未裁决,真值只会更低;而第二物种的 61 个净多铸**不进这个数**
(它们是移交项,不是定案)。

**一条对下一轮有用的观察**:9 条净减里有 **5 条是跨轮重复**(M-1 / M-3 / M-4 / M-5 / M-6),
**4 条是同轮内多号**(M-7 / M-8 / M-9 / M-10)。同轮内那 4 条**不是错误** ——
「定案 + 移交」拿两个号是制度设计的结果。真正该修的是跨轮那 5 条,
而它们全都发生在**没有别名表**的地方。

---

## 3. A-2:「后轮覆盖前轮已证伪结论」普查

### 3.1 搜索面

**必须先说清怎么搜的 —— 这一条的可信度等于检索的完备性。** 三条互补路径:

**路径 ① 改判语普查(找出「哪些结论被证伪过」)。**
语料 = §1.1 的 266 份;只在**围栏块外**的行上匹配;`## 勘误` 节**不排除**(勘误正是改判的载体)。
模式分两档,逐词都在语料里真实出现过:

- **强档**(明说「前面那个说法不成立」):`证伪|推翻|改判|撤销|作废|收回|不成立|不足以|原判|驳回|重开|堵不住`
- **弱档**(修正 / 缩小但未否定):`收窄|关闭并改述|是错的|判错|误判|更正|改述`

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11b/probes/rulings_reversal_scan.py --reversals 2>/dev/null | head -1
```

```text
# 语料 266 份(排除 r11b-*);改判语命中行 强档 755 / 强+弱 1145
```

**755 条强档命中里绝大多数不是「改判本项目的定案」**,而是在描述被测代码(如「该保证不成立」)。
所以要收窄到**定案级**:命中行必须是**表格行或标题行**(定案与移交都登记在这两种行里),
且带案号或记号:

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11b/probes/rulings_reversal_scan.py --ledger
```

```text
# 定案级改判行:83;其中带案号的 33
```

**路径 ② 案号法(机械、完备)。** 对上面 33 条带案号的改判行,取其案号,在**轮次序更晚**的
产出里搜同一案号的全部出现(`ORDER` 常量给出轮次时间序),逐条人判。

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11b/probes/rulings_reversal_scan.py --casepass
```

```text
# 定案级改判行 83;带案号 33;其中案号在更晚轮次再出现的 14
```

**路径 ③ 特征短语法(补路径 ② 的漏)。** 路径 ② 只覆盖**带案号**的改判(33/83)。
剩下 50 条改判的对象是一句话而不是一个号,机械搜不到。做法:对每条改判,
取被推翻的那句话里**一个不可替换的中文短语**,全语料 grep,按轮次序看有没有后轮复现。
本片实际取的短语(逐个跑过):`静默消失` / `静默抹掉`、`H-7 关闭`、`20+ 平台` / `20+ external`、
`容器关机即删`、`Tool Search`、`NOT mirrored` / `不会镜像`、`waitpid`、`平台族`、
`PairingStore`、`真实网关`、`native_stt_available` / `BUILTIN_STT_PROVIDERS`、
`atomic_config_write`、`后果更轻`、`_base_url`。

**排除了什么(要写出来):**
- 排除 `reviews/`(理由见 §1.1)、`data/`、`scripts/`。
- 排除围栏块内的行(块里的「不成立」是被引用的源码或文档原文,不是本项目在改判)。
- 排除 `notes/r11b-*`(本轮在写)。
- **同一文件内的自我改判不算命中**:一份底稿在正文里先写 A、后面又写「A 不成立」,
  是同一份产出的自我更正,不是「后轮覆盖」。路径 ② 里的 `f2 != rel` 就是这条。

### 3.2 命中 1(种子案):■-R11A-01 覆盖 R9C 的证伪

**R9C 证伪了什么。** R9C 用本地双服务实验证明,移交项给的修法(「比对配置的 connector host /
`self._base_url`」)**不足以**修好该缺陷:

`notes/r9c-90-handover-rulings.md:72`

> R9A / R9B 两轮给的修法都是「比对配置的 connector host / `self._base_url`,而非放宽或收紧子串」。**这条修法必要,但不充分。**

`notes/r9c-90-handover-rulings.md:76`

> 实验:`RelayMediaClient` 的 `_base_url` 与被请求 URL 主机**完全相同**(故建议的主机校验必然通过),重定向目标换到另一个本地端口 / 另一个主机名。

原因是 `urllib.request.urlopen` 默认跟随 302 且把 `Authorization` 原样带到新主机;
仓库里现成的正确修法是:

`hermes_cli/urllib_security.py:31-32 @ 863e313`

```python
class SafeCredentialRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Preserve request headers only while redirects stay on one origin."""
```

**R11A 怎么覆盖的。** R11A 把 `H-R9B-d` 升格为 `■-R11A-01`,正文重新把被证伪的那半句写成结论:

`notes/r11a-90-handover-rulings.md:70`

> 而正确的比较值**就在同一个类的构造里**,同一文件里还被用来拼规范 URL:

而 R11A 的**全部产出**里 **0 处**提及 302 / 跨源重定向 / `urllib_security`:

```verify
cd "$(git rev-parse --show-toplevel)" && for f in reports/round-11a-ops-and-delivery.md notes/r11a-90-handover-rulings.md chapters/r11a-ops-and-delivery.md; do printf '%s %s\n' "$(git show 00f09bf:$f | grep -cE 'urllib_security|SafeCredentialRedirect|跨源|重定向|302')" "$f"; done
```

```text
0 reports/round-11a-ops-and-delivery.md
0 notes/r11a-90-handover-rulings.md
0 chapters/r11a-ops-and-delivery.md
```

**定性要准确:`■-R11A-01` 的缺陷判定本身完全成立**,它甚至比移交项更完整(补了可达性链条、
补了另外 2 个同形态位点、给了搜索面)。**被覆盖掉的只有「修法」那一层** ——
读者按 `■-R11A-01` 去修,会以为把 `in` 换成 origin 比较就完事,而 R9C 已经实测证明那样仍然泄漏。

### 3.3 命中 2(本片新发现):R8D 两处覆盖 R8C 对「静默消失」的证伪

**R8C 证伪了什么。** R8-fix 立 `■-R8B-12`,后果写成「其余配置——包括 `approvals.deny`——静默消失」。
R8C 实测:失效链成立,但**「静默」两个字不成立** —— 同一次运行打了指名道姓的告警,
并写了一份逐字相同的带时间戳备份,而那份备份**正是为这件事准备的**:

`hermes_cli/config.py:114 @ 863e313`

```python
    first warning for a given broken file we also snapshot it to a
```

**R8D 怎么覆盖的。** R8C 之后的 R8D,在两份底稿里把「静默抹掉」当作已定事实再次使用:

```verify
cd "$(git rev-parse --show-toplevel)" && for f in notes/r8c-90-rulings.md notes/r8d-raw-extensions.md notes/r8d-raw-root-and-boundary.md; do git show 00f09bf:$f | grep -n '静默消失\|静默抹掉' | sed "s|^|$f:|"; done
```

```text
notes/r8c-90-rulings.md:387:## 7. 改判前轮定案:■-R8B-12 的「静默消失」不成立
notes/r8c-90-rulings.md:398:> 落盘文件就只剩 `model:` 一段,其余配置——包括 `approvals.deny`——静默消失。**
notes/r8c-90-rulings.md:470:- 「静默消失」和「告警 + 留备份后截断」是**两个不同严重级别**的东西。
notes/r8c-90-rulings.md:663:**跨轮改判 1 条**:■-R8B-12 的「静默消失」定性推翻(本卷 §7)。
notes/r8d-raw-extensions.md:2263:`approvals.deny` 静默抹掉)的**正确解法**,而且就写在同一个仓库里。
notes/r8d-raw-root-and-boundary.md:2066:3. **`utils.atomic_*` 与 R8B 的 H-7(坏 YAML 静默抹掉 `approvals.deny`)是否同源。**
```

**传播路径查到了,而且它比这两处本身更值得记:两处都写明出处是 `CLAUDE.md`。**

`notes/r8d-raw-extensions.md:2262`

> 这正是 CLAUDE.md 里 R8B 的 H-7 移交项描述的那类事故(坏 YAML 下把用户的

`CLAUDE.md` 的那句话写在 R8-fix 那一卡(commit `fafcb96`,2026-08-08),
即 **R8C 改判之前**;R8C 之后它**从未更新**。而 `CLAUDE.md` 是每轮开工必读、
且写进每份派工书的文件 —— **一条过时表述放在那里,等于每轮给所有子代理发一次。**

**这一条与种子案的区别要讲清**:种子案是「后轮没读到前轮的改判」;
这一条是「前轮的改判没有回写到那份人人都读的文件里」。**后者的传播面大得多,
而且它不会被任何一轮的移交项清单发现**,因为 `CLAUDE.md` 不在移交账上。

**顺带核一个锚点(不是缺陷,免得下一轮再查一遍)**:`CLAUDE.md` 写 `hermes_cli/auth.py:7270`,
R8B / R8-fix / R8C 写 `:7329`。**两者都对**,指的是同一条路径的两端 —— 前者是函数头:

`hermes_cli/auth.py:7270 @ 863e313`

```python
def _update_config_for_provider(
```

后者是那次整文件替换的落盘语句:

`hermes_cli/auth.py:7329 @ 863e313`

```python
    atomic_yaml_write(config_path, config, sort_keys=False)
```

**不是漂移。**

### 3.4 逐条排除的候选:命中为零的那些,以及搜的是什么

路径 ②/③ 逐条查过、**结论为「无后轮复现」**的改判(负结论,故把搜索面写在表里):

| 被证伪的结论 | 改判处 | 搜的短语 / 案号 | 结果 |
|---|---|---|---|
| 「H-7 关闭,没有第三个读原始配置后落盘的调用方」 | `notes/r8b-90-handover-rulings.md:22`:`## 1. H-7:**重开**——第三个"读原始配置后落盘"的调用方确实存在(原负结论作废)` | `H-7 关闭` + 案号 `H-7` | **0 命中**:R8B 之后无任何一轮把它当结论;R8B 报告正文那句已由文末勘误节兜住 |
| 「20+ 平台低估」记 ▲ | `notes/r7-90-doc-conflict-rulings.md:50`:`### A3. 能力点 99:"20+ external messaging platforms" 口径偏小 —— ◎ 保守表述(原记 ▲,R8-fix 改判)` | `20+ 平台` / `20+ external` | **0 命中**:R8-fix 之后无一轮再把它计进 ▲;`chapters/r7-*` 已按 ◎ 叙述 |
| 「容器关机即删」 | `notes/r4-90-doc-conflict-rulings.md:7`:`## 定案 1 ★ tools.md:88 "容器关机即删"(R1 挂起的头号条目)——证伪(对默认态)` | `关机即删` | **0 命中**:R4 之后仅在 `chapters/r4-*` 以「证伪」形式出现 |
| 「Tool Search 渐进披露无文档」记 ◇ | `notes/r3-90-doc-conflict-rulings.md:16`:`| 7 | ◇ Tool Search 渐进披露(R1 2.5-10) | **证伪(有专门详尽的 tool-search.md)** | r3-20 定案 c |` | `Tool Search` | **0 命中**:R5 两处引用都把它当「文档完全正确」的正例 |
| 「H-R9A-b waitpid 不主张」 | `notes/r9d-91-handover-rulings.md:765` 的 `**立 ■**,推翻 R9A「不主张」` | `waitpid` 在 R10 / R10B / R11A 全部产出 | **0 命中**(该短语在 R9D 之后的语料里一次都没出现) |
| 「24 个平台束是 ▲」 | `notes/r9d-91-handover-rulings.md:516`:`### 5.4 主线初判被推翻:那 24 个平台束不是 ▲,是 ◇` | `平台族` 在 R10 / R10B / R11A | **0 命中** |
| 「`PairingStore()` 与 `PairingStore(profile="default")` 语义差异记 ▲」 | `notes/r8c-90-rulings.md:217`:`### 5.3 改判:配对库的 profile 语义 —— ▲ 撤销,◇ 加重` | `PairingStore` 在 R8D 及以后 | **0 命中** |
| 「H-R10-f 需起真实网关才能复现」 | `reports/round-10b-desktop-application.md:501`:`### 11.3 H-R10-f:静态推演 → 实测复现,而「需起真实网关」这个前提不成立` | `H-R10-f` / `真实网关` 在 R11A | **1 处提及但非复现**:`reports/round-11a-ops-and-delivery.md:86` 讲的是探针路径失效,与该前提无关 |
| 「H-R9B-a 病因是抄了一份,修法是 import 权威集合」 | `notes/r9c-90-handover-rulings.md:257`:`## 2. H-R9B-a:关闭,但病因要改述` | `native_stt_available` / `BUILTIN_STT_PROVIDERS` 在 R9D 及以后 | **0 命中** |
| 「▲-10 两条路等价、目前无害」 | `notes/r8b-90-handover-rulings.md:167`:`### 1.2 并案:这属于 R8A ▲-10 的绕行家族,而 ▲-10 的"目前无害"结论要收回一半` | `atomic_config_write` 在 R8C 及以后 | **0 命中**:R8C 的每一处引用都在讲「它修不掉 ■-R8B-12」,方向与改判一致 |
| 「H-R8D-c 后果更轻」 | `notes/r9a-h-r8d-c-env-loader-lock.md:700` 的 `「后果更轻」的前提被推翻` | `后果更轻` / `_SECRET_SOURCES` 在 R9B 及以后 | **0 命中**:R9B 的引用是在改锚点行号,不涉及定性 |

**一条正面样本值得单记**:R9C 那次改判**被 R9D 正确承接过**——

`notes/r9d-90-handover-credential-landing.md:358`

> R9C 对 H-R9A-a 的定案说"只做主机校验而不换成 `open_credentialed_url`,**实测仍会泄漏**"——

**所以这不是「改判天生留不住」,而是「它在两轮之后、换了个案号回来时留不住」。**

### 3.5 成因:A-1 是 A-2 的成因

把 §3.2 的时间线和 §2.3 的 M-1 叠在一起看,链条是完整的:

1. **R9C** 把改判归档在 `H-R9A-a` 名下,并在同一行声明 `H-R9A-a` = `H-R9B-d`。
2. **R10** 在同一张表的**相邻两行**里,一行说 `H-R9A-a` 已结清、另一行说 `H-R9B-d` 是真孤儿:

`reports/round-10-client-interface-layer.md:134`

> | **H-R9A-a / d / h、H-R8C-a** | **判为「已结清,账目未记」** —— 结清写在底稿散文里,报告定案表没收录,机械普查因此读成 OPEN。这是账目问题,不是欠账 |

`reports/round-10-client-interface-layer.md:135`

> | **H-R9B-d** | **确认是真孤儿,但不属 R10**(锚点在 `gateway/relay/media.py`,属网关);**归 R11A**,与同处代码的 H-R9C-d 同轮做 |

3. **R10B** 只复核了 `H-R9B-d` 的锚点解析,未触碰它与 `H-R9A-a` 的等价关系。
4. **R11A** 拿着 `H-R9B-d` 回到 **R9B 的移交表**取原始表述(「正确比较值 `self._base_url`
   就在同一个类里」),照着它取证并升格 —— **R9C 的卷宗在 `H-R9A-a` 名下,路上没有任何一步会经过它。**

**这就是为什么 §2.6 的 R-1(别名不删、写进现行号)不是账目洁癖:**
一个实体两个号,而改判只归档在其中一个号下,**下一轮走另一个号就一定读不到改判**。

### 3.6 「更正该怎么写」的建议(交主线执行)

**原则:清账不改变已定案结论的实质。** `■-R11A-01` 的缺陷判定成立,**不撤、不改述**。
要补的是它缺的那一层,以及断掉的索引。

1. **在 `reports/round-11a-ops-and-delivery.md` 文末勘误节加一条**(报告正文不静默改写):
   点明 `■-R11A-01` 由 `H-R9B-d` 升格,而 `H-R9B-d` 已由 R9C 与 `H-R9A-a` 并案并改判过;
   `■-R11A-01` 给出的修法方向(比对 `self._base_url`)**必要但不充分**,
   完整修法见 `notes/r9c-90-handover-rulings.md` §1.2 与 `hermes_cli/urllib_security.py:31`。
   **勘误节只加不减,不动 §8.2 正文。**
2. **在 `notes/r11a-90-handover-rulings.md` §1 直接改正文**(`notes/` 属「直接改正文」那一类),
   在「而正确的比较值就在同一个类的构造里」之后补一段,写明:原判是什么(只比 `_base_url` 即可)、
   为什么撤(R9C 本地双服务实验:主机校验通过、302 后 bearer 仍到新主机)、依据是什么
   (`notes/r9c-90-handover-rulings.md:72,76` + 仓库自带 `SafeCredentialRedirectHandler`)。
3. **建立别名**:在 `■-R11A-01` 的登记处写「= `H-R9A-a` = `H-R9B-d` = R9A `■-01`」,
   并按 §2.6 R-1 保留全部旧号。**这一条才是防复发的那一条** —— 前两条修的是这一次,它修的是下一次。
4. **`CLAUDE.md` 的「静默抹掉」那句(§3.3)**:建议把它改成 R8C 改判后的准确表述
   (「会在坏 YAML 下把用户的 `approvals.deny` 截断落盘 —— 有告警、有带时间戳备份,
   但用户不看 stderr 就发现不了」)。**这句话是用来讲『负结论错了会关闭调查』这条道理的,
   道理不受影响;受影响的是它顺带传播的那个事实定性。**
   属改 `CLAUDE.md`,不在本片授权范围,交主线。

---

## 4. 未做 / 需要但没装

- **未做**:剩余 82 个候选簇未逐簇裁决(§2.4),故「去重后总数」只给上界。
- **未做**:第二物种的 35 个真撞号,本片只逐条**判定**了它们是撞号,**没有为每个号提出新号**。
  按 §2.6 R-7,建议由 R12 装订时统一加片标识,而不是本轮改历史底稿(改了会让所有跨轮引用失效)。
- **需要但没装**:无。本片只读语料与基线,未跑基线代码,未装任何包。
- **基线**:全程只读;收工时 `git -C /home/user/hermes-agent status --porcelain` 为空。

---

## 5. 本片自校验读数

```verify
cd "$(git rev-parse --show-toplevel)" && python3 scripts/verify_citations.py /home/user/hermes-agent notes/r11b-raw-rulings-census.md | tail -n +2
```

```text
citations=59  OK=42  UNCHECKED=17
可校验比例 OK/59 = 71.2%
table_anchors=39  OK=29  UNCHECKED=10   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
OK: every code-block-backed citation matches the baseline
```

**证据命令关卡的读数只能写成散文,不能写成 ```` ```verify ```` 块,理由值得记下来:**
`scripts/verify_evidence_commands.py` 会**重跑块里的命令**,而块里如果写的就是它自己扫本文件,
就成了无限递归(本片第一版这么写过,当场挂住)。本片的读数是
**`paired=9  unpaired=0  differing=0`**,退出码 0。
**给后续轮的一条制度提示:自校验读数天然不能自证,要么写成散文,要么由主线在另一份文件里钉。**

**17 条 UNCHECKED 是什么**(逐类交代,不含糊过去):全部是**散文区域指路** ——
「R9A 锚 `gateway/relay/media.py:92`(函数头)」这种句子里的锚点,后面跟的是散文不是块。
它们本来就不是「这段代码逐字长这样」的断言,造一个块去迁就关卡才是错的。
**10 条 TABLE-UNCHECKED** 里有 8 条是 §2.1 那张自报表 —— 摘录是**中文小节标题**,
而表格行内校验只接受「像代码」的摘录(`cell_tokens` 要求有标点或大写字母),
纯中文标题过不了那道形状判据。**这是关卡的已知覆盖边界,不是本片排版不合规。**

---

## 移交

| 移交项 | 去向 | 锚点 | 一句话现象 |
|---|---|---|---|
| **H-R11B-A-a** | R11B 主线(本轮) | `gateway/relay/media.py:94`:`return "/relay/media/" in (url or "")` | `■-R11A-01` 把 R9C 已证伪的修法(只比 `self._base_url`)重新写成结论;更正写法见 §3.6,**主线执行,本片不改** |
| **H-R11B-A-b** | R11B 主线 / R12 | `hermes_cli/urllib_security.py:31`:`class SafeCredentialRedirectHandler(urllib.request.HTTPRedirectHandler):` | 仓库自带的正确修法在 R11A 全部产出里零提及(实测 3 份文件各 0 命中);它是 `■-R11A-01` 缺的那一层 |
| **H-R11B-A-c** | R12 前置 | `tui_gateway/methods_session.py:1800`:`@method("pet.generate")` | `H-R10B-a` 三处独立铸号中的一处,R11A 只结清了 `scripts/` 那一处;本条从未被任何轮处置,且因号已标结清而不会被发现 |
| **H-R11B-A-d** | R12 前置 | `apps/desktop/src/plugins/gateway-pill/plugin.tsx:350`:`const plugin: HermesPlugin = {` | 同上,`H-R10B-a` 的第三处铸号(R10B 片 H);插件未声明 `defaultEnabled`,同样随号被误判为已结清 |
| **H-R11B-A-e** | R12 装订 | `gateway/pairing.py:18`:`Storage: ~/.hermes/pairing/` | 同一条断言 R7C 记 ▲、R8A 记 ◇;跨轮 ▲ 计数被 CLAUDE.md 定义为「地图腐烂程度」指标,记号不一致使它不可比 |
| **H-R11B-A-f** | R11B 主线(制度) | `hermes_cli/config.py:75`:`backup_path = config_path.with_name(f"{config_path.name}.corrupt.{ts}.bak")` | `CLAUDE.md:274` 的「静默抹掉」写于 R8-fix,R8C 已改判该定性,该句从未更新,并已被 R8D 两份底稿原样复用 |
| **H-R11B-A-g** | R12 装订 | `agent/file_safety.py:284`:`os.path.join("cache", "bws_cache.json"),` | R9C `■-1` 与 R9D `■-2` 是同一条(R9D 自陈「结清 R9C D 片 ■-1 在本片的部分」),跨轮 ■ 计数因此多算一条 |
| **H-R11B-A-h** | R12 装订 | `cron/scheduler.py:334`:`_running_job_ids: set = set()` | R7C 两份底稿互不通气各铸 `▲-1`,登记卷统成 `▲-4` —— 去重是本项目已有的动作,但只在轮内做过,没有跨轮别名表 |
