# R10 · 客户端接驳面 —— L2 首轮

界面层吃下四成七,守卫结论再进一层。

本轮是本项目**第一个 L2 大轮**,因此除常规交付外还承担三件事:为 L2/L3 建立**单轮容量先例**、
**定义 L2 的交付判据**、把「界面层」这块 405,902 行拆出一个可复核的进度基准。

---

## 1. 开工先核范围

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$5); if($5=="R10"){n++; l+=$3}} \
    END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

```text
1533 文件 / 405902 行
```

与任务书一致(L2 1,520 / 388,524;L3 13 / 17,378)。

**本轮吃下 A–I 九片 = 556 文件 / 191,657 行**(占 R10 的 36.3% 文件、**47.2%** 行);
**REMAINDER 977 文件 / 214,245 行显式移交 R10B**。拆片脚本自带无重无漏断言:

```verify
cd /home/user/hermes-study && python3 data/r10/probes/make_slices.py
```

```text
        A     11 files   15821 lines  tui_gateway 协议骨架与传输
        B     11 files    9742 lines  tui_gateway 方法面与宿主监管
        C     11 files    5831 lines  acp_adapter 编辑器接驳
        D     82 files   18000 lines  ui-tui 客户端主干
        E     97 files   24682 lines  ui-tui 组件、库与构建脚本
        F    131 files   27170 lines  hermes-ink 终端渲染器
        G    131 files   49274 lines  web 仪表盘前端
        H     80 files   26639 lines  apps/desktop/electron 主进程与后端监管
        I      2 files   14498 lines  native/fts5_cjk 随附头文件(处置)
REMAINDER    977 files  214245 lines  本轮显式不吃下(移交 R10B)
    TOTAL   1533 files  405902 lines
OK: slices partition round=R10 exactly (no overlap, no loss)
```

**不吃完是有依据的决定,不是没做完**:405,902 行是最大 L2 先例(R8D 83,350)的 **4.87 倍**;
R9A 已判「三片不够,至少五片」。主题上有一条自然接缝——「内核如何被接出去」
与「桌面端渲染层长什么样」——本轮取前者。

---

## 2. 台账报数

```verify
cd /home/user/hermes-study && python3 scripts/verify_ledger.py /home/user/hermes-agent data/ledger.tsv
```

```text
OK baseline=863e31318 files=8530 total_lines=2608452
  L1: files=563 lines=522207
  L2: files=2131 lines=671639
  L3: files=1895 lines=602085
  L4: files=560 lines=55902
  LT: files=3381 lines=756619
  SUM == repo total: 2608452
```

守恒成立;**五层文件数与行数与上一轮逐字相同**(只动 `status` 列,分层一列未碰)。
556 个文件 `status` → `R10-structure`。

**恢复必报项 —— `R1-inventoried` 剩余**:

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$6); if($6=="R1-inventoried"){n++; l+=$3}} \
    END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

```text
7180 文件 / 1770699 行
```

(开工 7,736 / 1,962,356,差额正好是本轮的 556 / 191,657。)

---

## 3. L2 交付判据(验收项 ②,本轮定义)

L1 有天然判据(逐机制、断言带行号),**L2 没有**——而 L2 是全仓最大的一层(2,131 文件 / 671,639 行)。
没有判据,`status` 从 `R1-inventoried` 翻成 `R10-structure` 就只是改一次字符串。

| # | 判据 | 复核方式 |
|---|---|---|
| **1 点名到位** | 片内每个文件至少出现一次**全路径** + 一句话角色;同型薄文件可归组,组内仍逐个列全路径 | `data/r10/probes/named_coverage.py` 实测零命中数 |
| **2 接缝穷举** | 每个对外接缝(方法表/端点表/IPC 通道表/导出面/事件表)**逐项列全、不抽样**,给机械枚举命令与条数 | 重跑它给的枚举命令核条数 |
| **3 端到端链** | 至少一条用户动作 → 客户端 → 协议 → 内核 → 界面的链,逐跳带锚点 | 顺锚点走一遍 |
| **4 逐字取证** | 至少 2 个围栏块是逐字源码摘录 | BLOCK-DRIFT 全块比对 |
| **5 记号** | 至少一条 ■/▲/◇/◎ 带锚点 | 抽验定性是否被证据支撑 |

**判据 2 是重心**:L2 与 L1 的差别不是「读得浅」,而是**「读接口面而不读实现体」**。
所以 L2 可以不读实现,**但不能抽样接口**——接口面抽样了,「结构级理解」就退化成「看过几个文件」。

**九片全部达成判据 1**(见 §5),判据 2 有**两片自报部分达成**并如实写进底稿:
片 G(166 个 api 方法名只给枚举命令未再抄表)、片 H(preload 152 个叶函数只给分类计数与枚举脚本)。
片 E 另主动提出一条**口径质疑**:若「36 个组件的 props 契约」也算接缝,它的判据 2 只算做到约六成。
**这三条自报保留在案,不视为达标。**

---

## 4. 移交项定案(逐条给结论,无一「续转」了事)

先回答「本轮的移交收件箱里有什么」。机械普查(`data/r10/probes/handover_census.py`):

```verify
cd /home/user/hermes-study && python3 data/r10/probes/handover_census.py --open-only | tail -3
```

```text
H-R9D-f          9d-l1-completion R11B                       —          OPEN

总计 52 条,其中未结清 26 条
```

**52 条 H-*,26 条未结清,无一条去向写 R10。** 搜索面:19 份报告的全部表格行 + 全语料散文复核。
*方法学坑*:初版脚本按**列序**取「去向」,把定案表的「来源」列读成了去向,
误把已结清的 `H-R8FIX-a` 判为未结清;改成按**表头名**定位列才稳定。

R10 主动认领 4 条,另处置 22 条:

| 移交项 | 处置结论 |
|---|---|
| **H-R8C-e** | **维持 ■,补全成因**:`claims` 验完从未再用于限权,而 job 跨全 profile 搜;**锚点漂 5 行已改正**(`hermes_cli/web_routers/cron.py:148`:`cfg = load_config()`,原写 `:143` 是一行 import) |
| **H-R8C-f** | **拆两半**:前端半边由片 G 结清(`/system` 页 4 个入口,恢复有二次确认但文案不含凭据字样,**备份与下载零确认**);**后端半边归 R11A** —— 没读 import 解包实现就不盖章 |
| **H-R8C-g** | **结清并加重**,新立 **■-R10-01**(见 §6.2) |
| **H-R8FIX-b** | **不结清,判归 R11B 与 H-R8D-g 合并**,并附一次新测量:全部 `notes/` **314 处**失败(125 MISMATCH + 189 MISSING-FILE)+ 按文件分解表,让 R11B 不必重做统计 |
| **H-R9A-a / d / h、H-R8C-a** | **判为「已结清,账目未记」** —— 结清写在底稿散文里,报告定案表没收录,机械普查因此读成 OPEN。这是账目问题,不是欠账 |
| **H-R9B-d** | **确认是真孤儿,但不属 R10**(锚点在 `gateway/relay/media.py`,属网关);**归 R11A**,与同处代码的 H-R9C-d 同轮做 |
| 其余 18 条(R11A 7 / R11B 4 / R11 复盘 5 / R12 前置 1 等) | **确认不属 R10**,并逐条核对锚点在基线上仍解析得到。**两处异常已点名**:H-R8C-e 漂 5 行、H-R8C-f 的 `:12801` 指向注释而非代码(簇首个端点在 `:12812`) |
| **H-R10E-c**(片 E 新提) | **就地判为误报**:它问 `ui-tui/src/sdk/` 11 个文件是否覆盖——**已覆盖,归片 D**。反映的是分片边界对子代理不可见,不是覆盖缺口 |

完整取证见 `notes/r10-90-handover-rulings.md`。

---

## 5. 点名覆盖率(验收项 ③)

```verify
cd /home/user/hermes-study && python3 data/r10/probes/named_coverage.py \
    --scope data/r10/slices/A.txt --scope data/r10/slices/B.txt --scope data/r10/slices/C.txt \
    --scope data/r10/slices/D.txt --scope data/r10/slices/E.txt --scope data/r10/slices/F.txt \
    --scope data/r10/slices/G.txt --scope data/r10/slices/H.txt --scope data/r10/slices/I.txt \
    --exclude notes/r10-01-scope-and-split.md
```

```text
scope files      : 556
corpus files     : 240 (10656372 chars)
excluded from    : ['notes/r10-01-scope-and-split.md']
full-path ZERO   : 0
bare-name ZERO   : 0
```

**本轮 556 个:全路径零命中 0、裸文件名零命中 0。**

**两个读数必须如实说明关系**:剔除承载清单的文件与**不剔除**,两次读数**都是 0/0,完全相同**——
不能说成「剔除后仍达标」,它们**就是同一个数**。原因是本轮的点名是**分散在九份底稿里的交付物本身**
(判据 1 要求每片逐个点名自己范围内的文件并给角色),而不是某一张「为报覆盖率而列的清单」。
R9D 那次污染的来源正是后者,**本轮结构上不存在那个来源**。

对照:**R10 全范围 1,533 个**的零命中是 **931 / 802**,差额即本轮未吃的 REMAINDER。

---

## 6. 定案

### 6.1 记号报数

| 片 | ■ | ▲ | ◇ | ◎ | 小计 |
|---|---|---|---|---|---|
| A 协议骨架 | 1 | 4 | 3 | 1 | 9 |
| B 方法面与宿主监管 | 4 | 2 | 3 | 1 | 10 |
| C acp_adapter | 4 | 6 | 7 | 1 | 18 |
| D ui-tui 主干 | 2 | 4 | 3 | 1 | 10 |
| E ui-tui 组件与库 | 1 | 5 | 4 | 0 | 10 |
| F hermes-ink | 5 | 0 | 3 | 1 | 9 |
| G web 仪表盘 | 4 | 3 | 3 | 1 | 11 |
| H desktop electron | 5 | 3 | 3 | 1 | 12 |
| I native vendor | 0 | 0 | 3 | 0 | 3 |
| **九片合计** | **26** | **27** | **32** | **7** | **92** |
| 主线另立 ■-R10-01 | +1 | | | | **93** |

### 6.2 ■-R10-01:`install_specs` 把信任推给 manifest,而 manifest 旁边那条路根本没有守卫

R8C 的原话是「dashboard 会 pip install 任意依赖」。**这句要改述,而改述之后更重。**

pip 那一半**有**守卫:spec 必须过 `_spec_is_safe`(`tools/lazy_deps.py:554`,禁 URL、路径、shell 元字符),
端点也在 dashboard 认证闸内。但**同一个函数旁边的 external 那一半没有任何过滤**:

`hermes_cli/web_server.py:5519 @ 863e313`

```python
        if install_cmd:
            try:
                install = _run_setup_command(
                    install_cmd,
                    display=install_cmd,
                    shell=True,
                    timeout=300,
                )
```

`install_cmd` 直接来自 plugin manifest 的 `external_dependencies[].install` 字段,
以 **`shell=True`** 交给 `_run_setup_command`,而 helper 在 `:5365` 用
`executable="/bin/bash" if shell else None`。**这个字段就是一条 `bash -c` 命令。**
(对照:同函数的 `check_cmd` 走 `shlex.split`,`:5395` / `:5480` / `:5552` 三处。)

*一处必须收窄的限定*:可达性这一环**不能照抄 R8D**。文件管理器的根由 `ManagedFilesPolicy`
决定(`hermes_cli/web_server.py:1731` 的 `HERMES_DASHBOARD_FILES_ROOT`、`:1733` 的
`_HOSTED_MANAGED_FILES_ROOT = Path("/opt/data")`),托管形态下锁到 `/opt/data`,
**并非无条件覆盖 `$HERMES_HOME/plugins/`**。确定的是三件事:(a) `install` 字段 = `bash -c`,无过滤;
(b) manifest 取自 bundled 或 `$HERMES_HOME/plugins/`(`plugins/memory/__init__.py:124`);
(c) 端点受认证闸管辖。**「谁能写那个目录」本轮未重验,留 R11A 连同 ■-R8D-02 一起做。**

### 6.3 结构性结论:守卫要重写几遍,取决于接出去几条缝

R9C 的结论是「防线的存在不是覆盖率的证据」(问装了几处);R9D 推进到「要紧的是装在哪一层」。
本轮把它推到下一层:**能力每多接出一条缝,守卫就要多写一遍,而没有人保证四遍写的是同一件事。**

四条缝各有一个反例,由四个互不通气的片各自撞见:

| 缝 | 守卫不一致的实例 |
|---|---|
| JSON-RPC | `pet.gallery` 有 `@_profile_scoped`,同族 `pet.generate` / `pet.hatch` 没有 |
| ACP | 「永久拒绝」被映射成一次性 `deny`;`Default` 模式承诺 "Ask before edits" 而 `skill_manage` 写文件零提示 |
| HTTP | `/api/cron/jobs/{id}/trigger` 必带 profile,`/api/cron/fire` 验完 JWT 不用 claims 限权 |
| Electron IPC | `fs:reveal`/`openDir`/`rename`/`trash` 绕过 `hardening.ts`,同组另 6 条都过 |

**主线独立复核了其中一条**(不照抄):

`tui_gateway/methods_session.py:1480 @ 863e313`

```python
@method("pet.gallery")
@_profile_scoped
def _(rid, params: dict) -> dict:
```

`tui_gateway/methods_session.py:1913 @ 863e313`

```python
@method("pet.hatch")
def _(rid, params: dict) -> dict:
    """Turn a chosen base draft into a full pet — installed but NOT yet active.
```

**这条结论的可迁移形式**:守卫绑在**收口点**(即将读一个路径 / 即将执行一段代码),
四条缝自动都被覆盖;绑在**每条缝的入口**,则缝是加法的、守卫是手工的,
**边缘那条最新的缝必然最先漏**。

### 6.4 三方交叉验证:JSON-RPC 方法总数 = 144

片 A(静态枚举 + 运行时 `len(server._methods)`)、片 D(客户端侧对账)、主线(独立 grep)
三次互不通气的测量都得到 **144**。

**三个读数须分别标注,不得混用**:**123** = 五个 `methods_*` 模块之和;
**133** = 全部 `@method`(123 + `server.py` 的 10);**144** = 133 + `@_projects_method` 11 = 服务端方法总数。
片 B 报的是 123,片 A/D 报的是 144,**不是矛盾,是三个不同分母**。

---

## 7. 测试(验收项 ④:passed / failed / **skipped** 三个数都报)

### 7.1 Python 侧(真跑)

选取**不按文件名猜**:严格 import 匹配(73)∪ `tests/{tui_gateway,acp,acp_adapter}/` 下的
`test_*.py` = **86 个文件**。(宽松 grep 多命中 4 个,它们只在 docstring / 断言文本 /
subprocess 字符串里提到模块名——两种模式都不单独可用。)

```verify
cd /home/user/hermes-study && python3 data/r10/probes/parse_pytest_run.py data/r10/measurements/py-tests-full.txt | head -5
```

```text
files parsed          : 86
discovered (运行器自报): 86 files / ~1077 tests
passed=1039  failed=2  skipped=0  zero-run-files=11
```

| 口径 | 读数 |
|---|---|
| 测试文件 | **86** |
| passed | **1,039** |
| failed | **2** |
| **skipped** | **0** |
| **零执行文件** | **11**(收集期报错) |

**11 个零执行文件逐个点名,及各自掩盖的用例数**(合计 **96 个 `def test_`**):

| 文件 | 掩盖用例 | 文件 | 掩盖用例 |
|---|---|---|---|
| `tests/acp/test_server.py` | 30 | `tests/acp/test_events.py` | 7 |
| `tests/acp/test_tools.py` | 23 | `tests/acp/test_named_provider_catalogs.py` | 6 |
| `tests/acp/test_mcp_e2e.py` | 7 | `tests/acp/test_permissions.py` | 5 |
| `tests/acp/test_entry.py` | 4 | `tests/acp_adapter/test_acp_images.py` | 4 |
| `tests/acp_adapter/test_acp_mcp_discovery.py` | 4 | `tests/acp/test_ping_suppression.py` | 3 |
| `tests/acp_adapter/test_acp_commands.py` | 3 | | |

**两个失败与 11 个零执行同源**:`ModuleNotFoundError: No module named 'acp'` ——
`agent-client-protocol` 在 `pyproject.toml:252` 的 `[acp]` 可选 extra 里,**不在 `[dev]`**。
**非代码缺陷、非容器缺陷**,是 `pip install -e ".[dev]"` 装不出全绿套件(H-R8D-j / H-R9B-e 的新实例)。

**一条结构性观察**:同一个缺失依赖产生**两种签名**,取决于 `import` 写在哪——
模块级(`acp_adapter/server.py:18`、`events.py:16`、`tools.py:10`)让整个文件无法收集、**静默零执行**;
函数级(`auth.py:51`、`edit_approval.py:267`、`entry.py:247`)只让单个用例失败、**可见**。
**一个响、一个哑。**

*CLAUDE.md 已知的 6 条本容器必然失败用例,本轮范围内一条都没碰到。*

### 7.2 TypeScript 侧(真跑,在基线之外的副本里)

```verify
cd /home/user/hermes-study && cat data/r10/measurements/vitest-summary.txt
```

```text
 Test Files  138 passed (138)
      Tests  1530 passed | 1 skipped (1531)
   Duration  42.60s (transform 22.45s, setup 0ms, import 53.27s, tests 33.37s, environment 22ms)
########## vitest: web ##########
 Test Files  27 passed (27)
      Tests  191 passed (191)
   Duration  5.19s (transform 1.84s, setup 0ms, import 3.83s, tests 1.30s, environment 4.20s)
```

| 套件 | 文件 | passed | failed | skipped |
|---|---|---|---|---|
| `ui-tui`(含 `hermes-ink`) | 138 | 1,530 | 0 | **1** |
| `web` | 27 | 191 | 0 | **0** |

**唯一那条 skipped 点名**:`ui-tui/packages/hermes-ink/src/utils/execFileNoThrow.test.ts` 的
"without resolveOnExit, await never resolves when daemon inherits stdio",用例名自带
`(documented hang)`——**有意跳过,跑它会挂住整个套件**,掩盖 1 个用例(非整文件)。

**静态清点 ≠ 运行时计数,两个口径分别标注**:`ui-tui` 静态数 `it(`/`test(` 字面量 **1,468** vs
运行时 **1,531**;`web` **189** vs **191**。差额来自 `it.each` 等运行时展开。
**文件数两法一致**(138 / 27)。因此 `apps/desktop` 的静态 4,390 应读作**下界**,不是用例数。

**未跑部分,如实申报**:`apps/desktop` 的 **490 个测试文件一个都没跑**(需 Electron 运行时,
本容器装不动),其 19 个 Playwright e2e 还要浏览器。
**R10 范围内行数最大的一块,执行验证是空白的**;片 H 的结论全部建立在静态阅读上。

---

## 8. 关卡读数(验收项 ⑤:两个口径分别报)

| 范围 | citations | OK | 可校验比例 | 阻断项 |
|---|---|---|---|---|
| **当轮 notes(报告口径,受 70% 下限约束)** | 666 | 461 | **69.2%** ⚠ **低于下限** | 0 |
| **定稿全量**(`chapters/*` 全部 + 当轮 notes + 本报告) | 1,103 | 685 | **62.1%** | 0 |
| 本轮成品章单独 | 4 | 3 | 75.0% | 0 |

*定稿全量那一行为何也低于 70%:它是**合并**比例,被 17 章历史成品章稀释
(成品章是「求读」的,大量引用天然是散文体区域指路),这是 R8C 已定的口径——
**70% 下限约束的是当轮 notes,不是 `chapters/`**。故该行不单独构成失败项;
真正需要解释的是当轮 notes 那 69.2%,见 §8.1。*

**0 MISMATCH / 0 BLOCK-DRIFT / 0 TABLE-DRIFT / 0 TABLE-OUT-OF-RANGE,退出码 0,全程未用 `--fix`。**
台账关、首句关同绿。表格锚点:当轮 notes `table_anchors=667 OK=356`。

### 8.1 低于下限的成因,与「是否需要调整口径」的判断

**先如实说:69.2% 就是低于 70%,不四舍五入、不辩解为达标。**

**成因是单片主导,不是全面滑坡。** 逐份读数:

| 底稿 | citations | OK | 比例 |
|---|---|---|---|
| `r10-raw-tui-gateway-skeleton.md` | 55 | 55 | **100%** |
| `r10-raw-desktop-electron.md` | 57 | 57 | **100%** |
| `r10-raw-hermes-ink.md` | 67 | 67 | **100%** |
| `r10-raw-native-vendor.md` | 20 | 18 | 90.0% |
| `r10-raw-ui-tui-components.md` | 39 | 32 | 82.1% |
| `r10-raw-ui-tui-core.md` | 66 | 49 | 74.2% |
| `r10-raw-tui-gateway-methods.md` | 87 | 64 | 73.6% |
| `r10-raw-web-dashboard.md` | 79 | 57 | 72.2% |
| `r10-96-ts-suites.md` | 2 | 2 | 100% |
| `r10-90-handover-rulings.md` | 14 | 5 | 35.7% |
| **`r10-raw-acp-adapter.md`** | **180** | **55** | **30.6%** |

**九片里八片达标或接近**;拖低的是 `r10-raw-acp-adapter.md` 一份(180 条引用、占全轮 27%)。
**剔除它,当轮 notes 是 (666−180)=486 条 / (461−55)=406 OK = 83.5%。**

**判断:口径需要调整,但本轮不改,提案交 R11 复盘。** 三条理由:

1. **判据 2 与块级比例在结构上互相拉扯。** 判据 2 要求接缝逐项列全,而穷举表的自然单位是
   「锚点 + 一句话」,不是逐字代码块。**判据 2 做得越实,分母越大而分子不变,比例必然下掉。**
   片 C 正是判据 2 做得最狠的一片(11 张穷举表)。
2. **表级证据被排除在分子之外。** 表格锚点的机械校验(R9B 的 TABLE-OK)在脚本里**单独计数、
   不进可校验比例**。片 C 有 39 个表格锚点、33 个已机械核过,这件事在 30.6% 上完全不体现。
   但**合并也救不了**:(461+356)/(666+667) = **61.3%**,更低。
   这说明问题不在合并两个计数器,而在**用块级比例衡量表级产出**。
3. **不能为了过关去造代码块。** CLAUDE.md 自己写过同型的话(「一份天然全是散文引用的成品章
   不该被逼着为了过关去造代码块」)。让片 C 给 180 个锚点各补一段摘录,
   只会把它变厚,不会让它更可信。

**提案(交 R11 复盘裁定,本轮不擅改 CLAUDE.md)**:L1 证据轮沿用 70% 块级下限不变;
**L2 结构轮改用「表格锚点声明率」为下限指标**——即「写进表格的锚点里,有多少写成了
可被机械校验的声明式」。片 C 该指标是 33/39 = **84.6%**,与它 30.6% 的块级比例是两回事,
而前者才反映它的证据纪律。

---

## 9. 单轮容量报数(验收项 ①,L2/L3 首个先例)

| 口径 | 读数 |
|---|---|
| 本轮吃下(含 I 片 vendored 处置) | **556 文件 / 191,657 行**,九片 |
| 本轮吃下(**扣掉** I 片 14,498 行随附头文件) | **554 文件 / 177,159 行** |
| 每片平均(A–H 八片精读) | **69.3 文件 / 22,145 行** |
| 唯一 L2 先例 R8D | 4 片 / 125 文件 / 83,350 行 → 每片 **31.3 文件 / 20,838 行** |

**最稳定的单位是「行/片」,不是「文件/片」**:R8D 每片 20,838 行、R10 每片 22,145 行,
**相差 6.3%**;而每片文件数差 **2.2 倍**(31.3 → 69.3)——界面层是大量小文件,
R8D 读的是 `hermes_cli/` 的大文件。**所以后续轮的容量单位应当是约 20,000–22,000 行一片。**

**推算**:

| 剩余 | 文件 | 行 | 按 ~21,500 行/片 | 轮数 |
|---|---|---|---|---|
| **R10 REMAINDER** | 977 | 214,245 | ≈ 10 片 | **1 轮**(R10B) |
| **R11A**(运维基建 L2) | 141 | 43,365 | ≈ 2 片 | 1 轮,**明显偏小** |
| **R11B**(文档编目 L3) | 787 | 263,763 | ≈ 12 片(**若** L3 与 L2 同速率) | **不可判定** |

**三条限定必须跟着数字一起读**:
1. R10B 那 1 轮有已知缺口——`apps/desktop` 的 490 个测试跑不动。
2. R11A 只有本轮的 22.6%,**建议与 R11B 的清账部分合并成一轮**,不单开。
3. **L3 到本轮为止仍然零先例。** 本轮的 13 个 L3 文件(`apps/desktop/src/i18n/*`)落在 REMAINDER 里,
   **本轮没碰**。所以「L3 单轮容量」R10 **没有资格给数**——R9A 的方法学建议只完成了 L2 那一半。

---

## 10. 环境与资源账(验收项 ⑧)

| 资源 | 开工 | 收工 | 期间安装 |
|---|---|---|---|
| Python 共享 venv | **87**(`pip list` 去表头 87、`dist-info` 87,两法一致) | **87**(两法一致) | **0** |
| node 副本(基线之外) | 0 | **466** | 466,来源 npmjs.org |

**venv 全程零安装**,九个子代理均自报未装包;派工书明写禁止 `pip`/`npm`。
Python 3.11.15。

**node 的 466 个包**由**主线**在**派发子代理之前**安装到 `/home/user/r10-ts/hermes-agent`
(用 `git archive` 从基线导出的副本),触发场景 = 跑 `ui-tui` / `web` 的 vitest。
**它不进 venv 计数**,两者是不同资源。

**一处必须更正的读数**:片 G 自报「venv 仍 36 条」——**那是系统 python3 的读数,不是 venv**。
不更正会被读成「发生过卸载」。

**基线洁净**:全程 `git status --porcelain` 为空;跑完 86 个 Python 测试后
`git diff HEAD` 仍为空(**已跟踪文件逐字未变**,`.pyc` 落在基线自己的 `.gitignore` 覆盖面内)。
HEAD 全程 `863e31318553cda8ad61df681d08175364d4164b`。

---

## 11. 诚实申报

1. **本轮只吃下 R10 的 47.2%(行)。** REMAINDER 977 文件 / 214,245 行**没有开工**,
   其 `status` 仍是 `R1-inventoried`,未虚报。
2. **一次基础设施事故,烧掉 686,202 子代理 token / 约 19.2 分钟,产出为 0。**
   第一次派工走工作流编排器,12 个子代理**全部报废**——编排器路径的权限层把每一次
   `Bash`/`Read` 的参数改写成不合法形状(报错自陈 "The tool input from the model was valid")。
   栈顶报错是「结构化输出重试超限」,只看栈顶会去改 schema。用一次十秒探针分辨出
   「普通子代理路径正常、编排器路径坏了」,改道后九片全部正常。详见
   `data/r10/measurements/dispatch-incident.md`。
3. **主线差一点用产物形态推断完成。** 事故中途看到「12 个 agent 都 started、已推进到第三阶段」,
   据此差点判定前两阶段完成——实际全在失败。后来片 A 的文件静止 15 分钟又继续增长,
   再次印证:**文件存在、体量够大、甚至不再变动,都不是完成信号。**
4. **主线的一次假阴性,由子代理的结论纠正。** 复核片 F 的「15 个构建产物当源码提交」时,
   主线用 `sourceMappingURL=data:application/json;base64` 搜得 0,一度以为对不上;
   实际标记含 `charset=utf-8;`。**给出相反结果的是主线的命令,不是子代理的结论。**
5. **一条负结论由主线补完搜索面。** 片 F 的「fork 无许可声明」自陈只查了文件名;
   主线补全文搜索,`ui-tui/packages/hermes-ink/` 下 `MIT License|Copyright (c)|SPDX-License|Licensed under`
   **零命中**,无 LICENSE 文件,`package.json` 无 `license` 字段——**结论比该片自报更强**。
6. **■-R10-01 的可达性被主线主动收窄。** 初版把链条写成「文件管理器能写 `$HERMES_HOME`」,
   复核发现那是转述 R8D 且与 `ManagedFilesPolicy` 不符,已改为「未重验,留 R11A」。
   **收窄之后这条 ■ 没那么好看,但它是对的。**
7. **一条边界违反,自查发现并修复。** 本轮首个提交带了 `Claude-Session` 与
   `Co-Authored-By` 尾部(会话与模型标识),违反「不把会话/模型标识写进仓库产物」,
   已 `--amend` 剥除,此后每次提交自查。
   *历史情况如实报:`main` 上已有 **148** 个提交带该尾部(R9B 及更早;R9C/R9D 已停用)。
   **本轮不重写已推送的共享历史**——重写的风险高于这条违反本身。*
8. **一个关卡自身的口子,两片互不通气地各自撞见。** `scripts/verify_citations.py:169` 的
   `CITE` 正则扩展名白名单是 `py|md|yaml|yml|toml|c|sh|json|ts|tsx|js`,**不含 `h`/`mjs`/`nix`/`rs`**。
   这些锚点**连"引用"都不算**——既不校验,也不计入 UNCHECKED,**比 UNCHECKED 更隐蔽**。
   全语料量化:白名单外的真锚点 **16 处**(`.h` 13 / `.mjs` 2 / `.nix` 1)。
   **本轮不改 `scripts/`**(边界:子代理运行期间不改;而它们运行到本轮很晚)——立 **H-R10-a** 交 R11A。
   *修的时候要当心*:同一次扫描里 `sqlite.org:443` 也长成「路径:行号」,naive 放宽会开始「校验」主机名。
9. **判据 2 的三处自报未达标已在案**(片 G、片 H 部分达成,片 E 提出口径质疑),不粉饰。
10. **几乎全部结论是静态阅读。** §6.2 的 `bash -c`、§6.3 的四条缝不一致、
    开篇那条重连 bug,**都没有运行时复现**;需要真实凭据或起服务,项目边界明写不配置。
11. **正文路径与底稿锚点一致性已自查**(验收项 ⑥):本报告正文出现的每个文件路径
    均取自已通过机械校验的锚点或主线亲自复核过的位置;机械校验只覆盖锚点、不覆盖散文路径,
    此项为人工自查,**声明已查**。

---

## 12. 待提供项(不自行猜测或伪造)

| 项 | 用途 | 阻塞的结论 |
|---|---|---|
| `agent-client-protocol==0.9.0`(`[acp]` extra) | 让 11 个零执行文件的 **96 个用例**真跑 | 片 C 的 ACP 方法名/通知变体的第一手取证 |
| Electron 运行时 + Playwright 浏览器 | 跑 `apps/desktop` 的 490 个测试 | 片 H 全部结论的执行验证 |
| 外网可达 `sqlite.org` | 与官方 amalgamation 逐字 diff | 片 I 的「逐字上游」由 5 条旁证升为全等证明 |
| 真实 provider 凭据 / 可起的网关 | 端到端复现重连 bug、跨 profile 触发、`bash -c` 链 | §6.2 / §6.3 / §1 的实证等级 |

---

## 13. 移交清单(每条带声明式锚点 + 一句话现象)

| 移交项 | 去向 | 锚点 | 现象 |
|---|---|---|---|
| **H-R10-a** | R11A(**实由 R10B 结清**) | `scripts/verify_citations.py:169`:`CITE_EXTS = "py\|mdx\|md\|yaml\|yml\|toml\|c\|h\|sh\|json\|tsx\|ts\|mjs\|js\|nix\|rs\|txt"` | 扩展名白名单不含 `h`/`mjs`/`nix`/`rs`,这些锚点连"引用"都不算,不校验也不计 UNCHECKED;放宽时须避免把 `sqlite.org:443` 当锚点 |
| **H-R10-b** | R11 复盘 | 本报告 §8.1 | L2 轮的 70% 块级下限与判据 2 结构冲突;提案改用「表格锚点声明率」,片 C 是 33/39 = 84.6% vs 块级 30.6% |
| **H-R10-c** | R11 复盘 | 本报告 §4 与 `data/r10/probes/handover_census.py` | 移交项的结清记录有两个存放地(报告定案表 / 底稿散文),机械普查只看得到前者,4 条已结清项长期显示 OPEN |
| **H-R10-d** | R11A | `hermes_cli/web_server.py:5524`:`shell=True` | manifest 的 `install` 字段以 `bash -c` 执行、无过滤;需连同 ■-R8D-02 重验「谁能写 `$HERMES_HOME/plugins/`」才能定级 |
| **H-R10-e** | R10B | `data/r10/slices/REMAINDER.txt` 的 977 行清单 | 本轮显式未吃的 977 文件 / 214,245 行,含 `apps/desktop/src/` 816 文件与全部 13 个 L3 文件 |
| **H-R10-f** | R10B / R11A | `ui-tui/src/gatewayClient.ts:221`:`this.subscribed = false` | 网关重启后订阅开关无复位路径(唯一开启点在 `drain()`,唯一调用点在依赖恒定的 mount effect);**静态推演,未实测**,需起真实网关复现 |
| **H-R8C-f**(后端半边) | R11A | `hermes_cli/web_server.py:12892`:`@app.post("/api/ops/import")` | 「来源校验仅 basename」需读 import 解包实现才能证成或证伪,本轮只结清前端半边 |
| **H-R9B-d**(改判后续转) | R11A | `gateway/relay/media.py:94` 的 `is_relay_media_url` | 去向原写 R9C 但四个 R9 轮次均未处置,确认为真孤儿;与同处代码的 H-R9C-d 同轮做 |
| **H-R8FIX-b**(合并后续转) | R11B | 本报告 §4 的 **314 处**与按文件分解表 | 与 H-R8D-g 合并做,共用一次全量校验 |
| **制度四条确认在册** | — | `CLAUDE.md` | 表格行内锚点(:68)、shell 命令即证据(:176)、移交项格式(:180)、负结论的成本(:207)、异步产出完成判定(:214)**均在册**;**但 H-R9B-g 的惰性安装纪律不在册**——R9C/R9D 实际都在用,建议 R11 复盘补写 |

*(各片底稿另有 60 余条簇内移交项,均带锚点,留在各自底稿的移交节,不在本表重复。)*

---

## 14. 下一轮建议

1. **R10B 接着做 REMAINDER 的 977 文件**,起点是 `data/r10/slices/REMAINDER.txt`;
   **先解决 Electron 依赖**,否则桌面端整块继续缺执行验证。
2. **R11A 明显偏小(本轮的 22.6%),建议与 R11B 的清账部分合并**,而不是单开一轮。
3. **L3 仍是零先例**,`R11B` 的 12 片是外推。建议 R10B 顺手吃下 REMAINDER 里那 13 个 L3 文件
   (`apps/desktop/src/i18n/`,17,378 行)并**显式报数**,给 L3 建立第一个数据点。
4. **H-R10-a(关卡口子)建议在 R11A 开工杂项阶段就修**,它是所有后续轮的公共设施。

---

## 勘误(R10B 补记)

本报告正文不静默改写;唯一例外是引用行号漂移必须就地改正,否则校验器过不了——
**每一处都在此点名**(CLAUDE.md「历史产出的改法」)。

R10B 在开工杂项里结清了本报告 §11.8 / §13 提出的 **H-R10-a**,改动了
`scripts/verify_citations.py` 的 `CITE` 正则。该文件是本报告自己引用的对象,
于是本报告里两处指向它的锚点当场失效:

| 处 | 原锚点与摘录 | 改为 | 说明 |
|---|---|---|---|
| §11.8 正文 | `scripts/verify_citations.py:158`(白名单所在行) | `scripts/verify_citations.py:169` | 白名单已提取为具名常量 `CITE_EXTS`,行号随之移动 |
| §13 移交表 H-R10-a 行 | `:158` + 旧正则字面量作声明式摘录 | `:169` + `CITE_EXTS = "..."` 新字面量 | 旧字面量在基线**已不存在**,留着就是一条断言错位置的锚点 |

**只改了行号与随之失效的摘录字面量,结论文字一字未动。** H-R10-a 的去向列
原写 R11A,已注明「实由 R10B 结清」——去向是当时的计划,结清是后来的事实,两者都留在表里。

*另记一条口径差,不是错误:§11.8 报「白名单外的真锚点 **16 处**(`.h` 13 / `.mjs` 2 / `.nix` 1)」,
R10B 用 `data/r10b/probes/cite_ext_scan.py` 全语料重扫得 **17 处**(`.h` 13 / `.mjs` 2 / `.nix` 2)。
差的那 1 处是 `notes/r9a-raw-research-pipeline.md` 里的 `nix/lib.nix` —— R10 的扫描面是
chapters + 当轮 notes,R10B 的扫描面是 `chapters/` + `notes/` + `reports/` + `reviews/` 全部。
**两个数都对,分母不同**,按「同一指标的多次测量须分别标注读数」记在此处。*
