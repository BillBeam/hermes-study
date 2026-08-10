# r11b-91 · 证据命令关卡的覆盖面 —— 配对率是稀释指标,欠账是另一个数

> 主线亲自取证。溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于块前。
> 本篇所有语料统计都**钉在某个提交上**(`--rev`),因为语料每写一份底稿就变一次;
> 本仓库 HEAD 可达提交总数见 §5。

## 0. 一句话

**该提的不是配对率,是那个五轮没动过的 758。**

## 1. 起点:任务书给的读数是怎么来的

R11A 的报告写的是 757:

`reports/round-11a-ops-and-delivery.md:100 @ 863e313`

```
**未配对的 verify 块:全语料 757 个**(见下表),**本轮自己的产出 0 个未配对**。
```

本轮用**关卡自己的两条正则**(`PAIR` / `ANY_VERIFY`,不另起口径)重数,
把语料钉在 R11A 开工前的那个提交上:

```verify
python3 data/r11b/probes/evidence_pairing_census.py --rev ef9f625 | tail -1
```

```text
verify_blocks=935 paired=177 unpaired=758 paired_pct=18.9% files_with_verify=108
```

**935 / 177 / 18.9% 对上了**,而它对应的提交是 `ef9f625` ——**R11A 合入前的 main**,
也就是 **R11A 还没写下任何一个字的时刻**。R11A 收官时的同一测量是:

```verify
python3 data/r11b/probes/evidence_pairing_census.py --rev 97ad57e | tail -1
```

```text
verify_blocks=1006 paired=248 unpaired=758 paired_pct=24.7% files_with_verify=115
```

### 1.1 两处必须分别标注的读数差(不写成"读数相同")

| 指标 | 读数 A | 读数 B | 差因 |
|---|---|---|---|
| 未配对块 | **757**(R11A 报告) | **758**(本轮整语料一次跑) | 逐文件扫描超时跳过了 `notes/r9d-92-mainline-tests-and-crosschecks.md`,该文件 10 块 9 配对,R11A 已把**配对侧** 168+9=177 对平,**未配对侧的 +1 没对** |
| 有 verify 块的文件数 | **111**(R11A) | **108**(本轮) | 口径不同:R11A 用 `grep -q '```verify'`(见 `data/r11a/probes/evidence_backlog_sweep.sh:30`:`grep -q '```verify' "$f" \|\| continue`),字面串出现即计入;本轮用关卡正则,要求块结构完整 |

两者各自在自己的口径下都对。列出来是因为**同一个名字的指标有两个数时,读者有权知道是哪一个**。

## 2. 核心发现:配对率会自己涨,欠账不会

把 R11A 那一轮的六个提交逐个量一遍:

```verify
for r in ef9f625 6880c91 1ee2876 026850e b94396f 97ad57e; do \
  printf "%-10s %s\n" "$r" "$(python3 data/r11b/probes/evidence_pairing_census.py --rev $r | tail -1)"; done
```

```text
ef9f625    verify_blocks=935 paired=177 unpaired=758 paired_pct=18.9% files_with_verify=108
6880c91    verify_blocks=935 paired=177 unpaired=758 paired_pct=18.9% files_with_verify=108
1ee2876    verify_blocks=943 paired=185 unpaired=758 paired_pct=19.6% files_with_verify=110
026850e    verify_blocks=970 paired=212 unpaired=758 paired_pct=21.9% files_with_verify=112
b94396f    verify_blocks=977 paired=219 unpaired=758 paired_pct=22.4% files_with_verify=113
97ad57e    verify_blocks=1006 paired=248 unpaired=758 paired_pct=24.7% files_with_verify=115
```

**`unpaired` 一格没动:六个提交、整整一轮,恒等于 758。** 而配对率从 18.9% 涨到 24.7%。

涨的那 5.8 个百分点**没有清掉一个单位的欠账**,全部来自分母被本轮新写的配对块稀释。
这与历轮在「可校验比例」上踩过的坑是同一个:

`reports/round-9a-capability-organization.md:329 @ 863e313`

```
| **H-R8D-g**(续转) | R11B | `chapters/r2-*` / `r4-*` / `r5-*` / `r6-*` / `r7-*` / `r7b-*` 六章 | 校验器逐章点名 UNCHECKED ≥90%;本轮全量比例升到 73.5% 是稀释所致,**欠账未动** |
```

**所以「把配对率从 18.9% 提上去」这个提法本身是错的靶子**:它是一个**只要继续写规范底稿
就会自己上升**的比值,而要修的东西(那 758 块)可以一动不动。
本篇后面报的一切,都以 **`unpaired` 的绝对数**为准。

## 3. 那 758 块能不能都配对?—— 先看它们是什么

`data/r11b/probes/evidence_block_profile.py` 按「能不能安全重跑」给它们分型。
分型判据是文本的(是否出现装包/写文件/改仓库动作),
只有 DEADPATH 一型依赖当前文件系统——**这一型的读数天然随环境变,不钉**。

工作区读数(本轮开工后、五片写入前):

| 型 | 未配对 | 已配对 | 含义 |
|---|---|---|---|
| MUTATING | **158** | 42 | 会装包 / 写文件 / 改仓库,**关卡不该自动跑它** |
| DEADPATH | 5 | 3 | 引用的绝对路径此刻不存在 |
| READONLY | **595** | 203 | 只读,可以跑 |

**MUTATING 那 158 块是硬约束,不是懒惰**:语料里真有往基线里装依赖的命令,
例如 `notes/r10-96-ts-suites.md` 那条 `npm install --workspace ui-tui --workspace web`。
一个"把所有 verify 块都跑一遍"的关卡会**自己把基线弄脏**,而基线洁净正是
`scripts/verify_ledger.py` 每轮第一件事要断言的东西。

## 4. 把 595 块真跑一遍:关卡看不见的那一类失败

配对块比对输出;**未配对块一次都没被执行过**。于是有两种失败:

- **(a) 跑得通但输出与贴的不一致** —— 只有配对块查得到(R10B 立本关卡的动机)。
- **(b) 根本跑不通** —— 配对与否都没查过。**它对「重跑能复现该结论的那一条命令」
  是更彻底的违反**:(a) 是数对不上,(b) 是根本没有"重跑"这回事。

`data/r11b/probes/evidence_runnability_sweep.py` 只跑 READONLY 那一型,
跑前跑后各记一次基线 `git status --porcelain` 行数。本次结果:

```text
readonly_unpaired=595 exit0=504 nonzero=90 timeout=1 error=0
baseline_porcelain_before=0 after=0 CLEAN
```

*(这一段不钉 ```` ```text ```` 配对:命令的输出**依赖执行环境**,这正是本节要证明的性质。
把它钉死会造出一个换台机器就红的关卡。)*

90 个非零退出按 stderr 归类:

| 类 | 数 | 说明 |
|---|---|---|
| A 块里混进了输出/散文 | **22** | ```` ```verify ```` 围栏里贴的不是命令,是**命令 + 输出**混排,重跑必然报 `command not found` 或 bash 语法错 |
| B 引用的路径此刻不存在 | **29** | 其中 **17** 处是**会话专属绝对路径**(`/home/user/r10b-ts`、含会话 UUID 的 scratchpad),另 12 处是相对路径的 cwd 假设 |
| C stderr 空且 exit 1 | 27 | 多半是 `grep` 零命中,**很可能正当**(结论本身就是"零命中") |
| D 超时 | 1 | 900 秒上限内没跑完 |
| E 其他运行期错误 | 12 | Python `SyntaxError` / `KeyError`、Node 崩溃 |

**A + B + E = 63 块**(占 595 的 10.6%)是**可判定的坏证据**:它们声称自己是
"重跑能复现该结论的那一条命令",而重跑给不出任何结论。
**配对率无论提到多少,都发现不了这 63 块中的任何一块**——配对只比对作者选择去钉的那些。

C 那 27 块本轮**不判**:`grep` 零命中退出 1 是正当的,而把它们逐条判开需要读上下文。
如实说明:这 27 块的正当性**未经确认**,不计入 63,也不算已清。

## 5. 结论与建议(其四的答复)

**不维持现状,但也不去追配对率。** 三条:

1. **先修 H-R11A-e,这是前置**。关卡对每条命令给 900 秒上限却**不捕 `TimeoutExpired`**:

   **本轮已修**,那一行现在是(修复带来的行号移动一并写出):

   `scripts/verify_evidence_commands.py:59 @ 863e313`

   ```python
   TIMEOUT = int(os.environ.get("HERMES_EVIDENCE_TIMEOUT", "900"))
   ```

   一条超时命令会让整轮扫描**中途崩掉,其后文件一个没查**,而它打印出来的仍是一份
   看起来完整的失败列表。上面 §4 的 `timeout=1` 说明这不是假想:语料里现在就有一条。
   **在这个 bug 修掉之前,任何"扩大关卡覆盖面"的做法都会放大它。**

2. **加一个「可跑性」检查,先只报数不阻断**,沿用本项目三次用过的分期
   (R7C→R8A 引用校验、R8C→R8D 全块比对、R10B→R11A 证据命令):
   对 READONLY 型的未配对块只断言"跑得通",不比对输出。
   它抓的是 A/B/E 那 63 块,而这三类正是**人工评审最抓不住**的
   ——评审者要真的去跑那条命令才看得见。

3. **不把配对定为强制**。理由不是省事:强制配对会把 758 块逼出 758 个
   "跑一遍看着对就贴上"的 ```` ```text ```` 块,而 R10B 立这道关卡时抓到的原始形态,
   正是**手工裁剪过的输出**。用一个会自己上升的比值去驱动,得到的是仪式,不是证据。

**本轮做到哪一步**:第 1 条已在本轮修掉(见 §6),第 2 条本轮**只给测量与设计**,
不落地——它要改 `scripts/`,而本轮的子代理纪律是运行期不改共享资源;
且按上面自己的分期理由,新检查该在积压有人认领的那一轮落地。**据此立 H-R11B-c。**

## 6. H-R11A-e 的修法与负控

见 `notes/r11b-90-handover-rulings.md` §H-R11A-e。

## 移交

| 移交项 | 去向 | 锚点 | 现象 |
|---|---|---|---|
| **H-R11B-b** | 清理历史底稿的那一轮 | `notes/r10-96-ts-suites.md:1`:`# r10-96 · TypeScript 测试套件的真实执行(主线)` | 63 块可判定的坏证据(A 22 / B 29 / E 12)逐条明细在 `data/r11b/evidence-runnability-failures.txt`,本轮只测量未逐条修 |
| **H-R11B-c** | 落地可跑性检查的那一轮 | `scripts/verify_evidence_commands.py:59`:`TIMEOUT = int(os.environ.get("HERMES_EVIDENCE_TIMEOUT", "900"))` | §5 第 2 条的「只断言跑得通、不比对输出」检查本轮未落地;落地时须先确认 §6 的超时修复在册 |
| **H-R11B-d** | 任一轮 | `data/r11b/evidence-runnability-failures.txt:1`:`[1] notes/r10-raw-acp-adapter.md` | C 类 27 块(stderr 空 + exit 1)的正当性**未经确认**,本轮既未判正当也未判坏 |
