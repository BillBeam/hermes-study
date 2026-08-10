# r11b-90 · 移交项定案(主线独立取证)

> 本轮(R11B)归属的移交项,全部由主线亲自取证,不转述子代理。
> 溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于块前。
> 引用本学习仓库自己的文件时,校验器先在基线找、找不到再在本仓库找
> (`scripts/verify_citations.py:656`),所以对 `notes/` / `reports/` 的锚点同样被机械校验。
> 实验只用 `127.0.0.1` 上的本地端口,不出网、不碰基线。

## 0. 先修普查工具本身:它看不见一整轮

数移交项之前得先确认普查读得到东西。R10B 版普查只扫 `reports/`:

`data/r10b/probes/handover_census.py:17 @ 863e313`

```python
ROOT = pathlib.Path(__file__).resolve().parents[3]
REPORTS = ROOT / "reports"
```

而 R11A 的报告把移交与定案**整节挪进了底稿**:

`reports/round-11a-ops-and-delivery.md:508 @ 863e313`

```
见 `notes/r11a-90-handover-rulings.md` §10 的**七条**(H-R11A-a..g),此处不重复。
```

于是 **R11A 的 15 条定案与 7 条新立项,在普查里一条都不存在**。
「漏了一整轮」和「那一轮没有移交项」在输出里长得一模一样——
**这正是 R10B 自己修过的物种换了个轴复发**:R10 版把报告时间序写成手工清单于是漏掉整轮,
R10B 改成向 git 要顺序,却把**语料面**继续钉死在 `reports/`。

本轮的 `data/r11b/probes/handover_census_r11b.py` 把语料面改成
「报告 + 与该轮同名的移交/定案底稿」,并保留 `--reports-only` 以便前后对比:

```verify
echo "R10B 口径: $(python3 data/r11b/probes/handover_census_r11b.py --reports-only | tail -1)"
echo "R11B 口径: $(python3 data/r11b/probes/handover_census_r11b.py | tail -1)"
```

```text
R10B 口径: 扫描文件 22 份;总计 66 条,未结清 32 条
R11B 口径: 扫描文件 45 份;总计 80 条,未结清 26 条
```

**14 条移交项此前完全不在账上;6 条显示 OPEN 实为已定案。**
下面的逐条定案以 **80 条 / 未结清 26 条** 为基数。

### 0.1 结清记录还有第三个存放地

`H-R9A-h` 的结清写在 **CLAUDE.md** 里(表格锚点纳入校验那一节),既不在报告定案表、
也不在移交底稿。**两个存放地是 R10 的发现,第三个是本轮的。**
本轮不再扩语料面去追它——见 §H-R10-c 的定案:**问题不在普查扫得不够宽,在结清没有单一落点。**

---

## 1. 本轮归属的 21 条(6 条去向 R11B + 15 条去向 R11 复盘)

### H-R11A-a —— ■-R11A-01 的修法写回了已证伪的版本

**定案:关闭。缺陷判定维持,修法按 R9C 实证更正。不立新案号。**

全部证据、更正落点与可重跑探针见 `notes/r11b-92-fix-regression-correction.md`。
一句话:主机校验作用在**发起前**的 URL 上,凭据是在 `urlopen` 跟随 **302 之后**被带走的,
所以「比对 `self._base_url`」判通过而 bearer 照样外泄。

### H-R11A-b —— LSP 快照路径漏传 `timeout=`

**定案:关闭,现象属实,锚点与修法均成立。**

同一个函数的两个调用点,一个传 `timeout=` 一个不传:

`agent/lsp/manager.py:486 @ 863e313`

```python
            fresh = await client.wait_for_diagnostics(file_path, version, mode=self._wait_mode)
```

`agent/lsp/manager.py:514 @ 863e313`

```python
                file_path, version, mode=self._wait_mode, timeout=self._wait_timeout
```

移交项说「修法是补传,不是调大 `:313` 的 8.0」——**成立**:`:313` 的算式是外层预算,
调大它只是让外层等得更久,不改变内层没有超时上限这件事。

### H-R11A-c —— ▲-R11A-01(Termux 特例的理由已作废)

**定案:关闭,维持 ▲。基线只读,无后续动作。**

`pyproject.toml:330 @ 863e313`

```toml
    # Removed from [all] on 2026-05-12 (covered by lazy-install):
```

四份 README 仍以「`.[all]` 会拉进 Android 不兼容的语音依赖」解释 Termux 特例,
而该依赖已于 2026-05-12 移出 `[all]`。**按整句判定**:前半句(Termux 装 `.[termux]`)成立,
后半句的**理由**已作废——这正是 CLAUDE.md 要求「把整句一并判定」的形态。

### H-R11A-e —— 证据命令关卡不捕 `TimeoutExpired`

**定案:关闭,本轮修掉并配负控。**

`scripts/verify_evidence_commands.py:46 @ 863e313`

```python
TIMEOUT = 900
```

一条超时命令让整轮扫描**中途崩掉,其后文件一个没查**,而它打印出来的仍是一份
看起来完整的失败列表。**这与 R10B 立本关卡时抓到的形态同类**:输出看起来对,覆盖面其实是空的。

修法与负控见 §3。

### H-R11A-g —— R11A 派工书写反了一句

**定案:关闭,已在本轮派工书更正。**

R11A 派工书说 `scripts/hermes-gateway` 不受引用校验保护。**说反了**:

`scripts/verify_citations.py:254 @ 863e313`

```python
    "base", "dashboard", "finish", "hermes", "hermes-gateway",
```

它在 `EXTLESS_NAMES` 里、路径又含 `/`,**受保护**。真正不受保护的是 `.ps1` / `.cmd`
——不在 `CITE_EXTS` 也不在无扩展名名单,指向它们的锚点**连 UNCHECKED 都不记**。
本轮派工书 `data/r11b/dispatch-brief.md` 已按此更正,并写明理由(派工书是下一轮会复制的模板)。

### H-R8D-g / H-R8FIX-b / H-R9C-e —— 三笔历史欠账

**定案:三笔均在本轮清理,读数见报告 §其三。** 分别由片 C(六章锚点排版)、
片 D(全 notes 314 处)、片 B1+B2(38 个 L1 文件)执行,主线复核。

### H-R9D-f —— 底稿里的会话专属路径

**定案:关闭。UUID 那一档本轮清零,目录那一档给出名单并移交。**

`notes/r9c-raw-secret-sources.md:280` 原文(更正前)是一条 `cd /tmp/claude-0/…/<会话标识>/scratchpad`。
全语料静态普查(搜索面:`notes/ chapters/ reports/ reviews/ data/` 下全部 `*.md`,
用关卡自己的 `ANY_VERIFY` 取块,模式 `/tmp/claude-N/-home-user-hermes-study/<hex>`
与 `/home/user/<非 hermes-agent|hermes-study|hermes-venv|.hermes>`)结果分两档:

| 档 | 块数 | 文件数 | 性质 |
|---|---|---|---|
| 含**会话标识** | **12** | 3 | **边界违反**(不把会话信息写进仓库产物),必须清 |
| 仅含会话临时目录(无标识) | 21 | 13 | 可移植性缺陷 |

**12 块全部处置完毕**,处置方式**不是**改路径了事:那些脚本**只存在于当轮 scratchpad、从未落库**,
所以命令重跑本来就复现不了任何东西。```` ```verify ```` 这个围栏声明的是
「重跑能复现该结论」,而这个声明是假的——**本轮把假声明撤掉**,改标 ```` ```console ````,
并在每处就地写明原判、撤因与依据。**结论本身一律不动。**

复核(全仓零残留):

```verify
grep -rEn "/tmp/claude-[0-9]+/-home-user-hermes-study/[0-9a-f-]{8,}" \
    notes/ chapters/ reports/ reviews/ data/ scripts/ | wc -l
```

```text
0
```

*本轮自己也踩了同一个坑*:探针生成的失败明细文件原样落库,把语料里的 10 处会话标识
**又抄了一遍进仓库**。已在 `data/r11b/probes/evidence_runnability_sweep.py` 里加抹除,
并重生成明细。**取证工具会把它读到的东西带进仓库**,这一条值得单列。

### H-R9D-e + H-R10B-b —— 测量对「报告它」不幂等

**定案:合并关闭,并入册。** 两条说的是同一件事的两个尺度:
H-R9D-e 是点名覆盖率这一个测量的毛病,H-R10B-b 指出**所有扫语料的探针**都有这个性质
——探针会被写它的那一轮污染。

本轮实测证实它仍然咬人:38 个文件的重测,**剔除与不剔除承载清单的文件读数不同**
(见报告 §其三),而**没有任何脚本会发现这种污染**。

**入册**:凡「在语料里搜 X 出现过没有」这类测量,报数时必须
**(a) 剔除本轮承载清单/点名的文件,(b) 剔除与不剔除两个读数都报**。

### H-R10-c + H-R10B-f —— 结清记录有多个存放地

**定案:合并关闭。普查语料面已扩(§0),但根因判定改述。**

R10 的表述是「结清记录有两个存放地(报告定案表 / 底稿散文),机械普查只看得到前者」,
R10B-f 补的是「普查的输入面靠手工清单维护」。本轮把输入面改成向 git 要 + 语料面扩到底稿后,
**又发现了第三个存放地(CLAUDE.md,见 §0.1)**。

**所以根因不是「普查扫得不够宽」——扩一次就发现一个新存放地,这是个追不完的靶子。**
根因是**结清没有单一权威落点**。定案:普查的语料面扩到底稿(已做)是止血;
**真正的规则是「一条移交项的结清必须写进它所属轮次的移交/定案表」**,写在别处的不算数。
入册后,普查的输入面就有了明确契约,而不是继续追加扫描目录。

### H-R10-b —— 70% 下限该不该改口径

**定案:不改分子口径;表格锚点声明率**单独报**,不并入可校验比例。**

R10 的提案是把表格锚点计进可校验比例(片 C 33/39 = 84.6% vs 块级 30.6%)。
**驳回,理由是本轮自己量出来的**:见 `notes/r11b-91-evidence-gate-coverage.md` §2 ——
一个把「好写的那一类」并进分子的比值,**只要继续写就会自己上升**,而欠账可以一动不动。
R11A 那一轮的配对率 18.9% → 24.7%,`unpaired` 恒等于 758。
把表格锚点并进分子会一次性抬高比例,却**不会让任何一条此前未被校验的引用变成被校验**。

**但 R10 指出的结构冲突是真的**(判据 2 做得越实,分母越大而分子不变)。
所以采纳它的另一半:**表格锚点声明率作为独立指标报**,与块级比例并列,两个数都写进报告。
脚本已经这么打印了(`table_anchors=… OK=…` 单独计数),本轮把它定为**必报项**。

### H-R8B-a —— 顶层死键 `personalities`

**定案:关闭,现象属实;定性为「设计题已提取,基线只读不改」。**

`hermes_cli/config_defaults.py:2129 @ 863e313`

```python
    "personalities": {},
```

而所有真实读取点走的都是 `agent` 层级,例如:

`hermes_cli/commands.py:2028 @ 863e313`

```python
            personalities = (load_cli_config().get("agent") or {}).get("personalities", {}) or {}
```

顶层那一份还被免除了校验告警:

`hermes_cli/config.py:4660 @ 863e313`

```python
    "personalities",
```

**可迁移的设计原则**(这才是本项目要的产出):**一个「开放字典」豁免名单,会把
「用户写错层级」和「用户自定义扩展」变成同一个无声成功。** 豁免名单该记录它豁免的**理由**,
否则它就是一个专门用来掩盖错层级的机制。

### H-R8B-b —— `status.py` 8 处无保护调用点

**定案:关闭,判据已给、设计原则已提取;逐处「该不该罩」不再续转。**

裸露面最大的那一节确实无 `try`:

`hermes_cli/status.py:344 @ 863e313`

```python
    if managed_nous_tools_enabled():
```

`:344-376` 整节 `try:` 出现 **0** 次(搜索面:该行区间内 grep `try:`)。

**为什么不再续转**:hermes_cli 已由 R8B / R8D 读完,没有"下一个读 CLI 的轮次"可承接;
而本项目**只读基线**,逐处判「该不该罩」不会产出代码改动,只会产出设计判断。
判断已可给出:**排障命令的崩溃姿态本身是设计题——最需要能跑的那条命令,
恰恰在环境不正常时最容易崩。** 正确姿态是每个探测块独立降级(打印"✗ 无法探测"并继续),
而不是整条命令半途 traceback。此结论写进本轮成品章的「可迁移的设计原则」。

### H-R8C-h —— 空 `Test*` 类与守错方向的不变量

**定案:普查完成并给出三个口径的读数;R8C 点名的那一个确认无任何测试保护;
逐条判断 docstring 方向是否相反 = 本轮未做,单独立项。**

R8C 点名的那个类确实是空的:

`tests/cron/test_scheduler.py:1608 @ 863e313`

```python
class TestHomeTargetEnvVarRegistry:
```

它 docstring 声明的不变量是 `_HOME_TARGET_ENV_VARS` 必须涵盖每个平台。
**搜索面**:`tests/` 全树 grep `_HOME_TARGET_ENV_VARS`(不含 `__pycache__`),
命中 2 处——**一处是这个空类自己的 docstring,一处是 `tests/gateway/test_google_chat.py:1592` 的注释**。
**没有任何一条断言。** 生产侧定义在:

`cron/scheduler.py:264 @ 863e313`

```python
_HOME_TARGET_ENV_VARS = {
```

**三个口径必须分别标注,不是同一个数**:

| 口径 | 读数 |
|---|---|
| R8C 报的(「还有 13 个」,即含被点名者共 14) | **13 / 14** |
| 本轮口径甲:类体去掉 docstring 后为空 | **15** |
| 本轮口径乙:类内无任何 `test_*` 方法 | **30**(其中 22 个所在文件连模块级 `test_*` 函数都没有) |

口径乙更宽,因为一个类可以有 fixture 或辅助方法却没有测试。**三个数都对,各自口径不同**。

### H-R9C-d —— 测试替身重抄被测谓词

**定案:关闭,全仓普查已做,给出 20 处名单。**

R9C 点名的那处确实是逐字重抄:

`tests/gateway/relay/test_relay_media.py:72 @ 863e313`

```python
    def is_relay_media_url(self, url: str) -> bool:
```

普查工具 `data/r11b/probes/test_double_predicate_census.py`,判据刻意保守:同名 + 函数体
AST 完全一致 + 非平凡体 + **该测试文件确实 import 了生产侧那个模块**。
**正控**:R9C 的那处必须被命中——命中了(`is_relay_media_url`,替身 `:72` ↔ 生产 `gateway/relay/media.py:92`)。

```verify
python3 data/r11b/probes/test_double_predicate_census.py | tail -1
```

```text
同名同体的测试替身函数:20 处,涉及测试文件 8 个
```

**放宽判据的代价是实测过的**:只去掉「非平凡体」与「须 import」两条,命中从 **20** 涨到 **332**,
多出来的全是 `return True` / `pass` / `return self` 这类到处同名同体的桩。
**这两个数不是同一个测量,分别标注。**

### H-R10B-d —— `hello-runtime` 是否该从 L2 降到 L4

**定案:不改分层,改判理由;并新增一条 ▲。**

R10B 片 H 的取证(全仓不可达)**成立**:搜索面 = 全仓 grep `hello-runtime` 与 `plugin\.runtime`
(排除 `node_modules`),前者命中 1 处(该文件自身的 id 字段),后者命中 **0** 处。
真正的插件发现走 glob,而该 glob **匹配不到它**:

`apps/desktop/src/contrib/plugins.ts:16 @ 863e313`

```typescript
const modules = import.meta.glob<{ default: HermesPlugin }>('../plugins/*/plugin.{ts,tsx}', { eager: true })
```

**但不该降到 L4。** L4 的语义是「有理由排除」,即我们**主动决定不学它**;
而这个文件刚刚**产出了一条发现**,正好相反。它自己的头注释声称被运行时加载:

`apps/desktop/src/plugins/hello-runtime/plugin.runtime.js:2 @ 863e313`

```javascript
 * Runtime-loaded example — this file is NOT bundled as a module: it ships as
```

**没有任何代码这样加载它**——`runtime-loader.ts:13` 与 `plugins-store.ts:3` 提到
「in-repo runtime example」的地方都是**注释,不是 import**。
**记 ▲-R11B-01**:模块头注释声称的装载路径在代码里不存在。
**维持 L2,status 照常。**

### H-R8D-h —— 模块 docstring 级 ▲ 是否与地图级 ▲ 分开计数

**定案:分开计数。地图级 ▲ 保持原义,码内 ▲ 另立一栏。**

依据是 CLAUDE.md 自己给 ▲ 划的范围:「README / 仓库根 AGENTS.md / website/docs 是作者自绘地图」。
模块 docstring 不在这三者之内。**把它并进同一个计数,会让「地图腐烂程度」这个跨轮指标
不再可比**——这与 R8-fix 当初把 ◎ 从 ▲ 里拆出来的理由是同一条(字面为真就不是 ▲)。

**记法**:码内矛盾记 **▲(码内)**,与地图级 ▲ 在报告里**分两行报**,不合并。
本轮的 ▲-R11B-01(上一条)即按此记为**码内**。
片 B2 移交的 `H-R11B-B2-e`(`subcommands/__init__.py` 自称 "each subcommand group owns a builder")
同属码内,按此裁定。

### H-R9B-f —— `.ogg` 目标下的 ffmpeg 编解码

**定案:维持推定,不关闭;本轮无法证实,原因是环境而非分析。**

```verify
command -v ffmpeg >/dev/null && echo present || echo absent
```

```text
absent
```

本容器无 ffmpeg,而本轮纪律是**不扩共享环境**(装 ffmpeg 属 apt 级改动)。
**不把「没跑成」写成「不成立」**:R9B 的推定(裸 ffmpeg 默认 Vorbis,而 Gemini 分支显式
`-acodec libopus`)在静态代码上仍然成立,缺的只是运行期确认。**续转,并写明确认它需要什么**
——一次愿意装 ffmpeg 的轮次,与 H-R11A-d(需装 extra)可同轮做。

---

## 2. 不归属本轮的 5 条(给出状态,不做定案)

| 移交项 | 去向 | 本轮处置 |
|---|---|---|
| **H-R11A-d** | 需装 extra 的轮次 | 不动。本轮守共享环境纪律,未装任何 extra。建议与 H-R9B-f 同轮做 |
| **H-R11A-f** | 接手 `plugins/` 的那一轮 | 不动。`round=R6` 名下 243 个 L2 文件 status 未动,理由见 R11A §6.6 |
| **H-R8D-i** | R12 前置 | 不动 |
| **H-R9A-d** | 「R9B/R9C 任一」 | **确认为已结清、账目未记**:`notes/r9b-90-rulings.md` 的结论表已写 `H-R9A-d(结清,现象属实但两侧都要修正)`,普查因列名匹配读成移交。本轮 §H-R10-c 的入册规则正是为它这一类 |
| **H-R9A-h** | 「制度(下一轮开工时)」 | **确认为已结清**,结清写在 CLAUDE.md(表格锚点纳入校验那一节)。即 §0.1 的第三个存放地 |

---

## 3. H-R11A-e 的修法与负控

见 §3 的实现说明与 `data/r11b/probes/evidence_gate_timeout_negative_control.sh`。

## 移交

| 移交项 | 去向 | 锚点 | 现象 |
|---|---|---|---|
| **H-R11B-e** | 任一轮 | `tests/cron/test_scheduler.py:1608`:`class TestHomeTargetEnvVarRegistry:` | 口径乙的 30 个无 `test_*` 方法的 `Test*` 类,**逐条判断其 docstring 声明的不变量方向是否与真实 bug 相反**,本轮未做;名单可用 `data/r11b/probes/` 同款 AST 扫描重生成 |
| **H-R11B-f** | 一次愿意装 ffmpeg / 平台 extra 的轮次 | `tools/tts_tool.py:2703`:`conv_cmd = [ffmpeg, "-i", wav_path, "-y", "-loglevel", "error", output_path]` | H-R9B-f 与 H-R11A-d 都卡在同一件事上:本项目至今没有一轮愿意扩共享环境,于是两条运行期确认永远排不上 |
| **H-R11B-g** | 清理历史底稿的那一轮 | `notes/r10b-raw-i18n-l3.md:1`:`# r10b 片 I · `apps/desktop` 的 i18n 语言包与国际化装配 —— 底稿(L3 知悉用途)` | H-R9D-f 的第二档:21 个 verify 块含会话临时目录(无会话标识),换个会话跑不了;名单在 `data/r11b/session-path-verify-blocks.txt` |
