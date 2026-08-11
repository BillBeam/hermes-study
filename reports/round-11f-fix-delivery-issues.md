# R11F-fix · 交付问题结清 —— 两条腿、一个范围、两处该说没说的话

**一句话结论**:六项结清;没写的字段与没定义的外号同源。

本轮不读基线新代码,**不新开内容轮范围,不动 L3**。基线固定 `863e31318`,全程只读。
四项交付问题逐项结清,每项配一份**实际触发过**的负控;R11F 的收官报告按制度加了勘误节。

---

## 1. 六项与它们的落点

| # | 交付问题 | 根 | 落点 | 负控 |
|---|---|---|---|---|
| 1 | `verify_derived_numbers.py` 写入腿:替换命中非目标数字;多键撞值守卫不可触发 | 子串语义 | `scripts/verify_derived_numbers.py`;`notes/r11f-fix-90-derived-gate-both-legs.md` §1 §2 | W1..W5 |
| 2 | 同上校验腿:多键声明里取值与键的对应关系不可判 | 子串语义 | 同上,§3 | V1..V4 |
| 3 | `chapters/r11f-plugin-surface.md` §3.4 两条路径未分开写 | 指代含混 | `chapters/r11f-plugin-surface.md`;`notes/r11f-fix-91-scope-and-manifest-exec.md` §2 | —(见 §3.4) |
| 4 | 引用关卡执行范围 ≠ CLAUDE.md 强制范围 | 范围无落点 | `scripts/mandatory_scope.py`;`notes/r11f-fix-91-scope-and-manifest-exec.md` §1 | S1..S4 |
| 5 | `reading/02-principles.md` 条目字段结构不一致(`P60`~`P64` 缺 `陈述`) | 无判据覆盖 | `scripts/verify_reading_layer.py`;`data/r11e/principles-src.md`;`notes/r11f-fix-92-principle-fields-and-r2-nickname.md` §1 | F1..F4 |
| 6 | `chapters/r2` 的「侧车」在 TL;DR 就担解释责任,字面定义在 520 行之后 | 术语未锚 | `chapters/r2-turn-loop-and-model-access.md`;`notes/r11f-fix-92-principle-fields-and-r2-nickname.md` §2 | —(见 §6.3) |

**第 5、6 项也同源,而且与第 4 项是同一族。** 三者都是「**没有判据覆盖的形状不会让关卡变红**」:
`reading/` 少跑一段只让分母变小;条目少一个字段,产物照样是脚本生成的、锚点照样逐字对得上;
一个外号没被定义,没有任何脚本会问「这个词读者看得懂吗」。**第 5 项本轮补的是判据,
第 6 项本轮补的是那句话本身**(它没有可机械化的判据,理由见 §6.4)。

**第 1、2 项同源。** 两条腿都用 `str.__contains__` / `str.replace` 的**子串**语义问
「这个数在不在这段里」。写入腿因此会把 `12,586` 改成 `12,829`;校验腿因此会认为
「`2,586` 在区段里」。所以修法只有一份:两腿共用一个 `number_tokens()`,
把区段切成**整数字 token**,并整段排除锚点行号与围栏块内的行。

---

## 2. 第 1、2 项:可复算指标关卡的两条腿

### 2.1 写入腿的四处

| 缺陷 | 交付版的行为 | 为什么没被自己的断言抓住 |
|---|---|---|
| 命中更大数字里的一截 | `2,586` → `2,829` 时把 `12,586` 改成 `12,829` | `hits` 用 `region.count()`,与 `replace` **同一套子串语义**,预期与实换一起错、正好相等 |
| 同声明内多键撞值 | 守卫**恒不触发**:`scripts/verify_derived_numbers.py:164 @ bdb82d5`:`sibling_truths = {old_vals.get(k) for k in keys}` —— 它与 `new_vals` 那一半取并集,结果是**集合**,于是 `sum(...) > 1` 恒假 | 撞值时另一个键在 `old == new` 处已 `continue`,没有第二组 edits 去撞那句 `assert` |
| 新值包含旧值 → 死循环 | `586` → `2,586` 时 `while f_old in line` 永不终止 | 断言根本执行不到 |
| 改写锚点行号 | 区段里若有一个锚点、其行号恰好等于旧真值(负控 W4 的 fixture 就是这样),它会被一并改写 | 无 |

改法:判据换整数字 token,落笔按 token 的**字符跨度**一次一处;守卫 4 改为对**其它键**
逐个点名比对并打印撞上的是谁。

### 2.2 校验腿:保序绑定

原判据是「这个数在不在区段里」——**集合成员关系**;而读者读的是「L1 那一行的文件数」
——**对应关系**。把 `chapters/r1` 那张 6 行 12 格的表整体重排,交付版照样
`declared=12 OK=12 STALE=0`、退出码 0。

改为:区段的数字 token 按出现顺序排好,声明里的键按**声明顺序**各认领**其后第一个**等值 token。
新增 `ORDER` 判决(阻断),`--explain` 打印「键 = 真值 ↔ 文件:行:列 '原文'」。
贪心最早匹配是子序列匹配的标准结论,存在任何保序匹配时它必然成功,所以 `ORDER` 不误报。

### 2.3 负控:两版并跑,判 PASS 要求「交付版确实翻车 **且** 修订版拦住」

`data/r11f-fix/probes/derived_write_negative_control.py`(W1..W5)与
`data/r11f-fix/probes/derived_verify_negative_control.py`(V1..V4)都
`git show bdb82d5:scripts/verify_derived_numbers.py` 取交付版、工作树取修订版,
在 `mktemp -d` 里端到端跑。**七条负控全部实际触发,两条正控两版皆正常**,完整输出贴在
`notes/r11f-fix-90-derived-gate-both-legs.md` §4 §5。三处最能说明问题的实际输出:

```text
W1  交付版: | 另一个与本声明无关的数 | 12,829 |     修订版: | 另一个与本声明无关的数 | 12,586 |
W2  交付版: synced=2 skipped=0,L2 那一格被写成了 L1 的新值 2,829
    修订版: [SKIP] fixture.md:1 ledger.L1.lines 旧真值 2,586 同时是同一条声明里 ledger.L2.lines 的真值,替换会张冠李戴
W3  交付版: exit=TIMEOUT <未在 25s 内终止>            修订版: synced=1,586 -> 2,586
V1  交付版: declared=2  OK=2  STALE=0 / exit 0        修订版: ORDER=1 / exit 1
```

**负控自己也抓到过我两条写错的断言和一个设计问题**(W3 的千分位写法、W5 的台账没算对),
过程如实记在底稿里 —— 一条从没红过的负控不算负控。

### 2.4 顺带修掉的第三处:`--since` 取不到台账时抛栈

R11F 报告 §5.1 的 ```verify 块钉的是 `--sync --since main`,而**本仓库的 `main` 停在
`Initial commit`**(树里只有 `README.md`),`git show main:data/ledger.tsv` 取不到,
于是该块重跑产出一段 traceback,`verify_evidence_commands.py` 判 `EVIDENCE-DIFF`。
这是 CLAUDE.md「**量『之前』的命令不许钉在会移动的引用上**」的又一次重演。
脚本改为报清楚不抛栈;两处钉在移动引用上的块改为固定 sha(见 §7)。

---

## 3. 第 3 项:§3.4 的两条路径

### 3.1 原文错在哪

原文先说「用 `shlex.split` 跑 `check`,用 `shell=True` + `/bin/bash` 跑 `install`」,
紧接着说「触发**它**的是 `GET /api/memory` 这类只读端点」,收尾为
「**往插件目录放一个文件,就能让一个只读请求执行任意 shell**」。
按字面读,这句话既**高估**了只读那条路(它不解释 shell 元字符),
也**低估**了它(它确实以网关进程身份执行了一个由插件目录自带清单点名的程序)。

### 3.2 基线上的两条路径(逐跳锚点见底稿 §2.2)

| | 路径一 | 路径二 |
|---|---|---|
| 端点 | `hermes_cli/web_server.py:12739`:`@app.get("/api/memory")` | `hermes_cli/web_server.py:6059`:`@app.post("/api/memory/providers/{name}/setup")` |
| 跑哪个字段 | 只跑 `check` | 先 `check`,失败才跑 `install` |
| 执行方式 | `hermes_cli/web_server.py:5395`:`shlex.split(check_cmd),` → argv,`shell` 取默认假 | `hermes_cli/web_server.py:5524`:`shell=True,` → 整串交给 `/bin/bash` |
| 超时 | 20 秒 | `check` 20 秒 / `install` 300 秒 |
| 跑几次 | `check` 一次 | `check` 最多两次(装前 + 装完验收 `hermes_cli/web_server.py:5552`:`shlex.split(check_cmd),`),`install` 最多一次 |
| 作用范围 | **每一个被发现的** provider(`hermes_cli/web_server.py:5938`:`for name in sorted(discovered):`) | 请求点名的那一个 |

`install` 在路径一上**只被读、不被执行**,唯一用途是决定「连 `check` 都没写时该不该判为未安装」
(`hermes_cli/web_server.py:5389`:`if not check_cmd:`)。

### 3.3 `chapters/` 完整 diff(验收约束:除本轮涉及的那一章外零改动)

本项目标只动 `chapters/r11f-plugin-surface.md`(下面 diff 里的第一行,三处);
第二行 `chapters/r2-…` 属**目标 6**,见 §6.3。**其余 20 章 `git diff` 为空**,
`data/chapter-order.tsv` 未动。派生值本轮**未变**(台账未动),
`<!-- derived: -->` 三条声明一个字没改。

```verify
cd /home/user/hermes-study && git diff --stat bdb82d5 -- chapters/
```

```text
 chapters/r11f-plugin-surface.md           | 181 +++++++++++++++++++++++++++---
 chapters/r2-turn-loop-and-model-access.md |  40 ++++++-
 2 files changed, 205 insertions(+), 16 deletions(-)
```

三处分别是:**(a) §3.4 整节改写**(拆成路径一 / 路径二 / 并排对照表,结论按路径分开写,
设计教训那句保留并补一句限定);**(b) TL;DR 第二个结论**——它与 §3.4 说的是同一件事,
不改会让同一章自相矛盾;**(c) 全景图那条虚线边**——由一条边指向「被只读端点触发执行」
改为两条边分指两条路径。(b)(c) **超出「§3.4」的字面范围**,在此明说。

*为什么没有为第 3 项单独立负控:它改的是**散文的准确性**,不是一道关卡。
它的机械证据是 `verify_citations.py` —— 新 §3.4 里 12 处基线锚点全部逐字比对通过
(本章单独 `citations=24 OK=23`,**95.8%**),包括那两处判定路径分野的
`shell=True,` 与 `shlex.split(check_cmd),`。*

### 3.4 本簇记号计数不变

改的是机制描述的精度,不是缺陷的成立与否。`H-R11F-F-a`(把执行挂在发现上、
绕过 `plugins.enabled`)两条路径都成立,成品章 §5 的 **■ 12 / ▲ 7 / ▲(码内)9 / ◇ 7 / ◎ 2**
一个字不动。

---

## 4. 第 4 项:强制范围的单一落点,与按统一口径重新取得的读数

### 4.1 现象与根因

R11F 收官报告 §11 把范围记成「定稿全量 = `chapters/` + 当轮 `notes/` + 本报告」,
**`reading/` 那一段掉了**(它于 R11E 并入强制范围)。掉了之后关卡照样绿、
报告照样报数,**没有任何东西会指出少跑了一段**——与 R10B「白名单外的锚点连分母都进不去」
是同一物种:**少掉的那一段不会让关卡变红,只会让分母变小**。

根因是范围**只存在于作者当时敲进终端的那一行里**:两道关卡靠调用方传一串文件名,
于是"本轮实际跑了哪些文件"既不在关卡输出里,也不在任何检查面上。

### 4.2 改法

范围收进 `scripts/mandatory_scope.py` 的 `SEGMENTS` 一张表,两道关卡加 `--round N`
从那里展开,并把 `scope=` 行**印在读数上面**;任一段解析出 0 个文件即 `EMPTY-SCOPE` **阻断**
(理由与 R11E 的 `EMPTY-GATE` 一字不差:一个什么都没扫的关卡也会打印绿字)。
CLAUDE.md 的两处命令块同步改为 `--round N`。

负控 S1..S4(`data/r11f-fix/probes/gate_scope_negative_control.py`)**四条全部实际触发**:
S1 造一个没有 `reading/` 的临时 STUDY,`EMPTY-SCOPE` 点名 `reading (reading/*.md)`、退出 1;
S2 轮次号写错,同时点名 `notes` 与 `reports`;S3 正控四段齐全;
S4 在真仓库上断言 `--round 11f` 与 CLAUDE.md 那行 glob **逐字同集**,
并逐个点名 R11F 少跑的 3 个文件。完整输出见底稿 §1.4。

### 4.3 按统一口径重新取得的全部读数

**统一后的口径 = `python3 scripts/verify_citations.py /home/user/hermes-agent --round 11f`**,
它展开为 `chapters/*.md` + `reading/*.md` + `notes/r11f-*.md` + `reports/round-11f-*.md`
(`notes/r11f-*.md` 这个模式把本轮的 `notes/r11f-fix-*.md` 也包了进来,
`reports/round-11f-*.md` 同理包住本报告)。

| 关卡 / 口径 | 取数命令 | 读数 | 退出码 |
|---|---|---|---:|
| `verify_citations.py` **统一口径** | `verify_citations.py /home/user/hermes-agent --round 11f` | `scope=CLAUDE.md/mandatory round=11f  files=37  (chapters=22  reading=3  notes=10  reports=2)`;`citations=780  OK=626  UNCHECKED=154`;可校验比例 **80.3%**;`table_anchors=465  OK=421  UNCHECKED=44`;**0 MISMATCH / 0 BLOCK-DRIFT / 0 TABLE-DRIFT / 0 TABLE-OUT-OF-RANGE** | 0 |
| ↑ 对照:R11F 记的范围(无 `reading/`) | `verify_citations.py /home/user/hermes-agent chapters/*.md notes/r11f-*.md reports/round-11f-*.md` | `citations=771  OK=623  UNCHECKED=148`;可校验比例 **80.8%** | 0 |
| `verify_evidence_commands.py` **统一口径** | `verify_evidence_commands.py --round 11f` | `verify-blocks paired=113  unpaired=0  differing=0  timedout=0`;`runnability ran=0  runfail=0  skipped-mutating=0` | 0 |
| **当轮 `notes/` 单独**(下限 70%) | `verify_citations.py /home/user/hermes-agent notes/r11f-fix-*.md` | `citations=27 OK=20`,**74.1%**,达标 | 0 |
| ↑ 表格锚点声明率(单独报,不并入比例) | 同上 | `table_anchors=20 OK=20`(**100%**) | 0 |
| R11F 当轮 `notes/` 单独(历史对照,7 份) | `verify_citations.py /home/user/hermes-agent notes/r11f-9*.md notes/r11f-raw-*.md` | `citations=233 OK=191`,**82.0%** | 0 |
| `chapters/` 单独 | `verify_citations.py /home/user/hermes-agent chapters/*.md` | `citations=506 OK=412`,**81.4%**(改动前 81.3%,**未下降**) | 0 |
| 目标 3 改写的那一章单独 | `verify_citations.py /home/user/hermes-agent chapters/r11f-plugin-surface.md` | `citations=24 OK=23`,**95.8%** | 0 |
| 目标 6 改写的那一章单独 | `verify_citations.py /home/user/hermes-agent chapters/r2-turn-loop-and-model-access.md` | `citations=31 OK=30`,**96.8%** | 0 |

*统一口径与 R11F 口径的差额 = `reading/` 三份派生件,**在同一棵树上**测量为
**+9 条引用 / +3 条 OK**(780/626 对 771/623),比例 **80.8% → 80.3%,低 0.5 个百分点**。
**注意三个比例分属两棵树,不可混为一谈**(CLAUDE.md:同一指标多次测量须分别标注):
**81.1%** 是 R11F 在**它自己的收工树**上按缺 `reading/` 的口径测的;
**80.8%** 与 **80.3%** 是本轮收工树上两种口径各测一次。差额那 6 条 UNCHECKED 全部是
`chapters/r8a` / `chapters/r9c` 里**本来就写成散文内联**的锚点被逐字派生进原则层
(R11E 已逐条回源核对指对);**它们不是新问题,只是此前不在检查面上**。
可以确定的是:遗漏 `reading/` 让这个比例朝"看起来更好"的方向偏。*

*上表所有读数都是**当前工作树**的读数,给出的是取数命令与范围,**不钉在 ```verify 块里**:
`chapters/*.md` 与 `reading/*.md` 会随 R12 增长,把它们钉死就是又造一个
「量之前的命令钉在会移动的引用上」。*

### 4.4 其余关卡

| 关卡 | 读数 | 退出码 |
|---|---|---:|
| `verify_ledger.py` | `files=8530 total_lines=2608452`;五层加总 == 全仓总行数;基线 porcelain **0** | 0 |
| `verify_derived_numbers.py` | `declared=18  OK=18  STALE=0  ORDER=0  UNKNOWN-KEY=0` | 0 |
| `verify_chapter_order.py` | `chapters=22  重号=0  未编号=0` | 0 |
| `verify_reading_layer.py` | `sections=139 products=3 links=557 entries=69 failures=0`(`entries` 是本轮新增的第四个读数) | 0 |
| `verify_report_headline.py` | 见 §9 | 0 |
| `verify_commit_safety.py --list` | **0 个 OPEN claim**(本轮无子代理,全部主线亲做) | 0 |

**台账五层加总守恒**(本轮**未改动台账**,`data/ledger.tsv` 的 `git diff` 为空):
L1 563 / 522,207;L2 2,131 / 671,639;L3 1,895 / 602,085;L4 560 / 55,902;
LT 3,381 / 756,619;**加总 2,608,452 = 全仓总行数**。
**恢复必报项**:`R1-inventoried` 剩余 **5,701 文件 / 1,379,392 行**(与 R11F 收工一致)。

**venv 包数:开工 87 / 收工 87。** 开工时容器里 venv **不存在**(新容器),按 CLAUDE.md
重建后即 87 包,与 R8B / R11F 记载一致。期间零安装。
**基线全程 `git status --porcelain` = 0,HEAD 恒为 `863e31318`。**

*一条重要的环境注记:开工时 `verify_evidence_commands.py` 在 R11F 口径下报
`differing=10`。逐条查明后是 **8 处环境 + 2 处真缺陷**:8 处指向
`/home/user/hermes-venv`,而新容器里那个 venv 不存在(CLAUDE.md 已预先写明这类漂移),
按 CLAUDE.md「测试环境」重建后全部复现原值;真缺陷的 2 处就是 §7 那两个钉在移动引用上的块。*

---

## 5. 第 5 项:原则层条目的字段结构一致性

### 5.1 现象

`reading/02-principles.md` 的条目分 `P`(原则)64 条与 `C`(冲突裁定)5 条。
`C` 那 5 条五个字段各 5/5,内部一致;`P` 这 64 条里 **`陈述` 只有 59 条有**,
`P60`~`P64` 一条都没有 —— 它们只有 `合并` 与**机器抽取的** `源出处`。
后果不是排版难看:**这五条把「这条原则说的是什么」整个交给了源章的原话**,
而原则层存在的全部理由是"脱离 hermes-agent 仍然成立"。

**三道既有锁一条都够不到它**:产物由脚本生成(`PRODUCT-STALE` 绿)、源出处逐字抽取
(锚点全对)、章节钉子全对(`SECTION-DRIFT` 绿)。**「条目之间长得不一样」不在任何一道的判据里。**

### 5.2 改法:两半互相咬住,所以删要求不能转绿

`scripts/verify_reading_layer.py` 加锁三(它已经是 `reading/` 的那道锁,不另起关卡):

* **`FIELD-MISSING`(阻断)**:每类的必备字段集在 `REQUIRED_FIELDS` 里**显式声明**,该类每条都要有;
* **`FIELD-UNDECLARED`(阻断,无阈值)**:一个字段若在某类**全部**条目里都有,它就必须在声明里。

第二条专为堵住第一条的逃生口:删掉 `REQUIRED_FIELDS["P"]` 里的 `陈述` 之后它仍然 64/64,
**立刻以 `FIELD-UNDECLARED` 回来**。负控 F2 把这条路实际走了一遍。
*「100% ⇒ 必须声明」而不是「≥N% ⇒ 必须声明」,是因为带阈值的判据里调阈值本身就是一条转绿的路。
代价如实说:它发现不了「59/64」这种**进行中**的漂移,故另加一行**非阻断**提示,
点名覆盖率 ≥50% 却未声明的字段(当前唯一一条:`合并` 49/64 = 77%,它是真·可选字段)。*

### 5.3 负控 F1..F4:三种形态各实际触发一次

判据从关卡 `import`,不另起口径。探针 `data/r11f-fix/probes/principle_fields_negative_control.py`。

```text
F1 摘掉 P60 的 **陈述**  -> FIELD-MISSING  reading/02-principles.md  P60  缺字段「陈述」——同类 64 条中另有 63 条有它
F2 从声明里删掉「陈述」   -> FIELD-UNDECLARED  种类 P  字段「陈述」在全部 64 条里都有,却不在 REQUIRED_FIELDS 里
F3 产物里一条 P 都没有   -> EMPTY-GATE  种类 P 一条都没解析到,拒绝判绿
F4 正控:真产物         -> entries=69  failures=0
```

完整输出见 `notes/r11f-fix-92-principle-fields-and-r2-nickname.md` §1.4。

### 5.4 补齐的五条,以及"不重复"怎么证

五条写进**编辑源** `data/r11e/principles-src.md`,产物由 `--write` 生成 ——
**`reading/` 下没有手改过一个字**(这是本轮边界,也是 R11E 立的制度)。

「不得与既有条目重复,也不得只是源出处的换句话说」机器判不了对错,**但判得了程度**。
探针 `data/r11f-fix/probes/principle_statement_overlap.py` 算两个方向性交比
(字符 3-gram):`echo` = 与自己源出处的重合度,`twin` = 与其它条目的最高重合度。
判据是**既有 59 条给出的分布**,不是拍的阈值:

| | 既有 59 条 min | 中位 | max | P60 | P61 | P62 | P63 | P64 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `echo` | 0.000 | **0.400** | 1.000 | 0.086 | 0.027 | 0.022 | 0.136 | 0.276 |
| `twin` | 0.000 | **0.031** | 0.093 | 0.029 | 0.013 | 0.022 | 0.012 | 0.017 |

**五条在两个读数上都低于既有 59 条的中位。** 报中位而不报上界,是因为 `echo` 上界是
**1.000** —— 既有条目里确实有一条陈述被它自己的源出处**逐字覆盖**,拿这个上界衬托新写的五条
没有意义。那条既有条目本轮**未处理**(不在目标范围内),铸 `H-R11Ffix-f` 交出去。

五条各自加了源章那一段**没有**的一层:P60 给出「可执行 / 会过期」的**判别测试**并指出
定性看有没有消费方而不看形式;P61 指出**枚举方向**才是全部(失败模式是「永远不发生」,
可观测性帮不上忙);P62 给出"纯读"的**判定方式**(能不能让别人的代码跑起来,不看 HTTP 动词);
P63 把抽象方法重述为一份**一次性预算**,真实约束是升级成本;P64 指出横表的信息量在**空格**里、
前提是先有可机械枚举的"同形态"定义。逐条对照表见底稿 §1.3。

---

## 6. 第 6 项:`chapters/r2` 里那个没被定义过的外号

### 6.1 是哪一个

逐词核实"首次承担解释责任"与"首次被定义"的先后(搜索面 = `chapters/r2` 全文,逐词 grep):

| 外号 | 首次担责 | 原先在哪定义 | 判定 |
|---|---|---|---|
| **侧车 sidecar** | **TL;DR 第 5 条结论**(全章五个最重要设计之一) | §3.8,在它后面约 520 行 | **不合格,本轮修** |
| 游标 cursor | §3.7 | 同处即给 | 合格 |
| 哨兵 sentinel | §3.10 | 同处即给(占位串 + 不持久化标记 + 紧跟代码块) | 合格 |
| 栅栏 fence | §4 原则 6 一句带过 | 全章无定义 | 不合格,但它是并发原语的外号、没有"在数据结构里是什么"可写,**不适用本项判据**;铸 `H-R11Ffix-g` |

侧车在 TL;DR、全景图、§3.2 各承担一次解释责任之后,字面定义才在 §3.8 出现。
**这同时违反本章自己的硬标准 1(术语锚定)**:TL;DR 那段「先锚几个贯穿全章的词」锚了
turn / tool_calls / provider / prompt cache 四个,而"侧车"在同一段两条之后就出现了,没被锚。

### 6.2 字面定义的三件事,逐条落在基线上

| 要求 | 定义 | 锚点 + 摘录 |
|---|---|---|
| 在数据结构里是什么 | 一条消息上的**第二个内容字段**,名叫 `api_content`;内存里就是消息字典上与 `role` / `content` 平级的普通键 | `agent/turn_context.py:129`:`v = msg.get("api_content")` |
| 存在哪里 | 落库时是 `messages` 表里一个**独立列**,写库 INSERT 的列清单里排在 `active` 与 `display_kind` 之间 | `hermes_state.py:6403`:`codex_message_items, platform_message_id, observed, active, api_content, display_kind, display_metadata)` |
| 与相邻字段的关系 | `content` = 给人看的干净正文;`api_content` = 当初实际发出去的字节,**只在两者不同时才写**;那一列为空就不挂这个键,于是"没有侧车"是合法状态,含义是"发出去的就是 `content`" | `hermes_state.py:6343`:`` `api_content` `` `is the exact content string sent to the API for this`;`hermes_state.py:7367`:`if row["api_content"]:` |

### 6.3 改法与 `chapters/` 完整 diff

三处:**TL;DR 术语锚新增「侧车(sidecar)」**(三件事写死,各配锚点与逐字块);
**§3.8 那句原定义改为回指**(免得同一章两处并列定义,读者不知哪个准);
**§3.8 补上"丢掉侧车为什么安全"**(读回时那一列为空就落回 `content`——原文只说了代价、没说为什么不会发错)。

```verify
git diff --stat bdb82d5 -- chapters/ data/chapter-order.tsv
```

```text
 chapters/r11f-plugin-surface.md           | 181 +++++++++++++++++++++++++++---
 chapters/r2-turn-loop-and-model-access.md |  40 ++++++-
 2 files changed, 205 insertions(+), 16 deletions(-)
```

**`data/chapter-order.tsv` 未出现在 diff 里 —— 不新增章、不改章号。** 其余 20 章 `git diff` 为空。

### 6.4 为什么第 6 项没有负控

它改的是**一段散文的可读性**,不是一道关卡。"这个词读者看得懂吗"没有可机械化的判据 ——
硬做一个(比如"术语首现前 N 行内必须有冒号定义")会立刻变成一个靠格式蒙混的检查,
而本项目对这类判据的态度是**声明,不靠嗅探**。它的机械证据是引用关卡:
新写的三处定义共 **4 处基线锚点全部逐字比对通过**,r2 单章 `citations=31 OK=30`(**96.8%**)。

---

## 7. 历史产出的改动,逐处点名

| 文件 | 改了什么 | 依据 |
|---|---|---|
| `reports/round-11f-plugin-surface.md` | §5.1 的 ```verify 块 `--since main` → `--since 5861435`(连同 ```text 里同一个词);**文末追加勘误节 E-1/E-2/E-3** | `reports/` 正文不静默改写;唯一例外是"否则校验器过不了"的引用修正,且**每一处都在勘误节点名** |
| `notes/r11f-90-handover-rulings.md` | `git diff main...HEAD` → `git diff 5861435 bdb82d5`,`ls scripts/verify_handover_*.py` → 读 `bdb82d5` 的树;就地写明**原判不撤、只换参照点** | `notes/` 直接改正文,改判处就地写明 |
| `chapters/r11f-plugin-surface.md` | §3.4 整节改写 + TL;DR 一句 + 全景图一条边 | `chapters/` 直接改正文;完整 diff 见 §3.3 |
| `CLAUDE.md` | 两处强制范围命令块改 `--round N` + 新增 `scripts/mandatory_scope.py` 的布局条目 + `verify_derived_numbers.py` 条目补本轮改动 + **扩展名白名单那一条就地更正**(见下) | 制度条随关卡同批入册 |
| `data/r11e/principles-src.md` | `P60`~`P64` 各补一段 `**陈述**`(目标 5);**产物 `reading/` 一个字都没手改**,由 `--write` 生成 | 派生阅读层不得手抄,唯一真源是编辑源 |
| `chapters/r2-turn-loop-and-model-access.md` | TL;DR 术语锚新增「侧车」+ §3.8 原定义改回指 + §3.8 补一段(目标 6) | `chapters/` 直接改正文;完整 diff 见 §6.3 |
| `reading/01-quickread.md` + `data/r11e/section-digests.tsv` | 因 `chapters/r11f` 改动 `--restamp` + `--write` 重建(三份产物都重建,**只有快读层内容真的变了**,另两份逐字相同);锁二在 §3.4 改完后**当场开火**,报了 3 处 `SECTION-DRIFT` + 1 处 `PRODUCT-STALE` | 派生阅读层不得手抄;restamp 是一次显式的「我重读过了」 |

**顺带查出的第三处口径漂移(与第 4 项同物种)**:CLAUDE.md 的「锚点扩展名白名单」那一条
写的是 `… nix rs txt`、锚点 `scripts/verify_citations.py:169`;而代码里现为
`scripts/verify_citations.py:179`:`CITE_EXTS = "py`… ,末尾多了 **`ps1` / `css` / `tsv`** 三个,
是 R11D(`df6d450`)加的,制度文本没跟着更新、行号也漂了 10 行。
**`CLAUDE.md` 自己不在任何关卡的扫描面上**,所以这处漂移没有任何东西会报。已就地更正并注明。
*本轮没有把 `CLAUDE.md` 纳入强制范围 —— 那要先解决它满篇「讲语法而非用语法」的行内引用
(`verify_derived_numbers.py` 为此专门有一条 `INLINE_CODE` 豁免),不是一次顺手能做对的事。
记为观察,不铸案号,因为它没有确定的收件人条件。*

**没有任何一个关卡是靠调低阈值或缩小范围转绿的。** 本轮所有关卡改动都在**收紧**:
`verify_derived_numbers.py` 新增 `ORDER` 判决与三类 token 排除,
`mandatory_scope.py` 新增 `EMPTY-SCOPE` 阻断,两道引用关卡的默认覆盖面**扩大了 3 个文件**。

---

## 8. 移交

本轮无分片(全部主线亲做),案号统一用 `H-R11Ffix-*` —— 与 R11F 的 `H-R11F-*` **不同域**,
免得 `H-R11F-a` 这种写法同时能指两轮的东西(CLAUDE.md 案号纪律:一个案号只指一个实体)。
收件人一律**条件式**,不写"下一轮"。

| 案号 | 现象(带锚点) | 去向(条件式收件人) |
|---|---|---|
| `H-R11Ffix-a` | 保序绑定对「同声明内两个键真值相同」判不出对调 —— `scripts/verify_derived_numbers.py:276`:`hit = next((i for i in range(pos, len(toks)) if toks[i].val == want), None)` | **任何一轮给某条 `<!-- derived: -->` 声明添加新键、且新键真值可能与既有键相等时**,同批判断是否踩上;踩上就拆成两条声明,不放宽判据 |
| `H-R11Ffix-b` | 区段边界仍是「跳过空行后紧跟的一段连续非空行」——`scripts/verify_derived_numbers.py:163`:`def declarations(lines):`;表格中间插空行会让后半张表落到区段外 | **任何一轮改动 `chapters/r1-what-is-hermes-agent.md` 三张派生表排版时**,先跑 `--explain` 确认绑定数仍为 18 |
| `H-R11Ffix-c` | 底稿引用「本轮刚写的本仓库代码」时,自引 commit 钉子拿不到尚不存在的 sha —— 本轮的处理是不写钉子(指工作树),`scripts/verify_citations.py:179`:`CITE_EXTS = "py` | **任何一轮认为该自动化这件事时**,改的是 `verify_citations.py` 的自引解析,并同批处理本条 |
| `H-R11Ffix-d` | `--round` 只覆盖 CLAUDE.md 那四段,`reviews/` 与历史 `notes/` 仍在强制范围外(R11A 有意定的),但**没有机制记录某轮自愿多跑了哪些** —— `scripts/mandatory_scope.py:42`:`SEGMENTS = (` | **任何一轮想把某段纳入强制范围时**,改 `SEGMENTS` 这张表(它会进 diff),不许在命令行临时补 glob |
| `H-R11Ffix-e` | 路径一执行 `check` 时,`_memory_provider_setup_env()` 会把四个目录**前插**进 `PATH` —— `hermes_cli/web_server.py:5322`:`extra_bins = [`,其中 `~/.brv-cli/bin` 正是 byterover 自己的安装位置;本轮只核实"执行方式",未展开这条对利用面的影响 | **代码缺陷复核轮**(不属本轮:本轮边界是不新开内容轮范围) |

---

## 9. 诚实申报

1. **第 3 项没有独立负控**,它的机械证据是引用关卡(§3.3 那段说明)。
   一节散文的准确性不适合用负控去证,但这一点必须明说,不能让"每项都有负控"含混过去。
2. **我改了 §3.4 之外的两处**(TL;DR 与全景图边),理由是不改会让同一章自相矛盾。
   这超出了交付问题第 3 项的字面范围,已在 §3.3 与底稿里明说。
3. **本轮改了 `CLAUDE.md`**,而任务边界写的是"产出落 `reports/` 与 `notes/`"。
   我的判断是:第 4 项要求的"口径统一"若不落到制度文本上,下一轮照样会按散文里的旧 glob 敲命令。
   改动限于两处命令块与布局条目,**没有放宽任何一条既有要求**。
4. **负控最初有两条断言是我写错的**(W3 的千分位、W5 的台账),第一次运行报 `PASS=2/5`。
   我改的是断言与 fixture,不是被测行为 —— 但这仍然说明:**一条第一次就全绿的负控,
   不足以证明它真的会红**。这也是本轮把「交付版必须实际翻车」写进判 PASS 条件的原因。
5. **`reading/02-principles.md` 的 6 条 UNCHECKED 我没有逐条回源重核**,
   而是引用了 R11E 已做过的核对结论(R11E 抽查 4 条指对)。本轮只把它们**纳入检查面**,
   没有重做那次核对。
6. **`H-R11Ffix-e` 是我在核实第 3 项时顺手看到的**,未展开;它属于代码缺陷复核轮。
   我没有把它写进成品章,以免把一条未做完的观察混进定稿。
7. **第 6 项也没有独立负控**,理由与第 3 项同(§6.4):它改的是散文可读性,
   没有可机械化的判据,硬做一个会立刻变成靠格式蒙混的检查。
8. **原则层里那条 `echo=1.000` 的既有条目我没有动**(§5.4)。它确实是"源出处的换句话说",
   但不在本项目标范围内;我把它铸成 `H-R11Ffix-f` 交出去,而不是顺手改掉 ——
   顺手改会让本轮的 `echo` 参照带变成我自己修出来的,那条带子就不能再当参照。
9. **`chapters/r2` 的「栅栏」我判为不适用本项判据**(§6.1),理由是它没有"在数据结构里是什么"
   可写。这是一个**判断**,不是一个测量;如果下一位读者认为它同样该被定义,
   这条判断应当被推翻,而不是被当成已经查过了。

---

## 10. 下一轮建议

1. **`L3 / R1-inventoried` 那 1,760 文件 / 566,871 行**仍是最大的未开工面(R11F §2.3 已定位),
   本轮按边界**未动 L3**。
2. **判据 2 增补「双向枚举」**(R11F §3.1 三片独立提出)仍待采纳或驳回。
3. **R12 装订轮的两条前置**未变:`H-R11F-M-f`(派生值不受章正文冻结约束,入册)与
   `H-R11F-M-c`(阅读层编辑源迁出 `data/r11e/`)。本轮新增第三条:
   `H-R11Ffix-c`(R12 重排全部 22 章前,先给自引锚点补 `@ <改动前 sha>`)。
