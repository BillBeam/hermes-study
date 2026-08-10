# r11c 片 C 底稿 · 55 块可判定的坏证据

> 本片范围:把 `data/r11c/runnability-open.tsv` 列出的 **55 块**「跑不起来的未配对
> ```verify 块」逐块修到能跑,或判定为不修并给理由。可改文件面 = `data/r11c/slice-c-files.txt`
> 里的 31 个历史文件 + 本底稿 + `data/r11c/c-bad-evidence-*`。基线 `/home/user/hermes-agent`
> 停在 `863e31318`,**只读**。溯源约定:`路径:行号 @ 863e313`。

## 0. 读数口径(先说清楚,两个数都写出来)

| 轮次 | 读数 | 分类法 | TIMEOUT | 语料 |
|---|---|---|---|---|
| R11B | **63**(A 22 / B 29 / E 12) | **人工读 stderr** 分类 | 900 s | R11B 合入前 |
| R11C 片 C(本片起点) | **55**(A 7 / B 23 / E 8 / OTHER 17) | **机械判据**,判据从关卡 import | 120 s | R11B 已合入 |

**这不是同一个测量。** 三处口径差同时存在:(a) R11B 是人读 stderr 归类、
R11C 是 `data/r11c/probes/runnability_census.py:35` 的 `classify_failure` 按 stderr 末行
形状机械归类(于是多出一个 R11B 没有的 `OTHER` 桶);(b) 超时上限从 900 s 收到 120 s;
(c) 语料本身在 R11B 合入后变过。**不得写成「读数相同」或「63 减到 55」。**

## 1. 结论(先写结论)

**55 块全部处置完毕,全语料可跑性积压清零(`bad=55 → bad=0`)。**
处置分布:**修好它 28 块**(拆成可重跑命令 + 配对逐字输出,全部通过比对)、
**声明它不是可重跑命令 27 块**(改 ```text / ```shell-session,块正文一字未动)、
**删掉 0 块**。没有一处伪造输出;凡重跑与原文不符的地方(#45 的异常消息句点、
#39 的耗时)都在正文点名,以实跑为准。

三条硬纪律的落地形态:

| 纪律 | 本片怎么执行的 |
|---|---|
| 不许为让关卡变绿而删掉证据 | 27 块「不修」的**全部保留原文**,只换围栏标签 + 块前写明为什么不可重跑 |
| 不许伪造输出 | 27 块不修的判据只有一条:**产生它的东西已经不在仓库里**(node_modules / R9A 探针 / 会话脚手架 / 被省略号吃掉的 `print`)。#51 与 #52 长得几乎一样却一修一不修,分界就在这里 |
| `reports/` 正文不静默改写 | 唯一一处 `reports/round-8-fix-review-1.md:180` 只换围栏标签,写进该报告文末勘误节第 3 条并点名 |

**本片自己也被关卡抓到一次。** §5 那份「全语料还剩几处」的清单,我先按一版有 bug 的判据
手写了 14 行贴进 ```` ```text ````,`verify_evidence_commands.py` 重跑当场报 `EVIDENCE-DIFF`,
指出其中一行**命令根本没产生过**。已如实改正并把过程留在 §5 —— 那正是这条关卡存在的理由。

## 2. 逐块处置(逐批追加)

### 批次 1 —— R8C 那 7 块(#25–#31):非命令内容被写在 ```verify 围栏里

**结论:7 块全部可判定,无一需要「留下说明修不了」。** 其中 4 块是纯说明文字
(取值链、token 来源、两处「搜索面」声明),正当处置是**改标 ```text**;
2 块是「命令 + 输出混排」且命令还被省略号吃掉了关键部分,正当处置是**重建可重跑命令 + 配对输出**
——重建后每一个数都与原块一致,**没有改任何结论**。

| # | 位置(改前行号) | 原病灶 | 处置 |
|---|---|---|---|
| 25 | `notes/r8c-raw-boot-authchain.md:918` | 取值链说明被写成 ```verify | 改 ```text |
| 26 | `notes/r8c-raw-boot-authchain.md:993` | token 两来源说明被写成 ```verify | 改 ```text |
| 29 | `notes/r8c-raw-platform-readiness.md:1199` | §9.1 搜索面声明被写成 ```verify | 改 ```text |
| 30 | `notes/r8c-raw-platform-readiness.md:1237` | §9.3 搜索面声明被写成 ```verify | 改 ```text |
| 27 | `notes/r8c-raw-config-endpoints.md:120` | 命令 + 输出混排,且命令被 `...` 省略 | 重建命令 + 配对输出 |
| 28 | `notes/r8c-raw-config-endpoints.md:330` | 纯输出、没有命令 | 补命令 + 配对输出 |
| 31 | `notes/r8c-raw-sessions-cron-mcp.md:1276` | 「命令 → 结果」混排 | 补可重跑命令 + 配对;原块改 ```text 保留 |

**#27 的重建值得单说:原块的命令是 `python -c "from hermes_cli.web_server import CONFIG_SCHEMA; ..."`
—— 真正算出那 10 行数字的部分全在那个 `...` 里,原作者从未写下来。** 重建时踩到一个真陷阱:
朴素的「dict 且非空才递归」写法给出 `DEFAULT_CONFIG leaves = 719`,与原块的 680 差 39,
而 39 正是同一份底稿 §2.5 记的「值为 `{}` 的空段」数;改成**无条件递归**(空 dict 递归后自然产出
0 个叶子,与 schema 生成同规则)后得 680,`leaves-only` 也从 40 项收敛到原块写的
`['_config_version']` 一项。**这说明重建是对的,不是凑数凑出来的。**

*为什么 #29 / #30 不重建成命令:它们是「负结论的搜索面」声明 —— 五条 grep 模式加逐条判读,
判读部分(哪几处是判定、哪几处是配置向导)不是任何命令的输出。按 CLAUDE.md
「非源码围栏用显式语言标记而不是靠脚本猜」,如实标 ```text 就是正确处置。*

### 批次 2 —— R10 / R10B 的 17 块:node 工具链与会话专属检出

**结论:17 块里 14 块判「不修,如实声明」,3 块判「修好它」并已修到配对逐字比对通过。**
分界线是**这条命令到底需不需要 `node_modules`**:需要的原理上跑不出原值(基线是只读
checkout,补 node_modules 只能在基线里 `npm ci`,那会弄脏全项目的引用基准);
只读源码的(find / grep)换成基线路径就能原样重跑。

**14 块声明为不可重跑**(改 ```text + 块前声明,块正文一字未动),清单与执行器见
`data/r11c/c-bad-evidence-refence.py`(逐字匹配,匹配不到即报错退出,不做模糊替换):
`r10b-raw-build-package.md` ×2、`capability-panels` ×2、`chat-composer` ×2、`i18n-l3` ×2、
`lib-themes` ×1、`message-render` ×1、`pane-shell-ui` ×1、`settings-billing` ×1、
`shell-overlays` ×1、`store-state` ×1。其中 13 块是 `npx vitest` / `npx eslint`,
1 块是 `NODE_PATH=/home/user/r10b-ts/...` 的 i18n 叶子键探针 —— 它的第一行注释自己就写着
「需要一个装了 typescript 的 checkout 提供 NODE_PATH」。

**3 块修好了:**

| # | 位置(改前行号) | 病灶 | 修法 | 钉住的读数 |
|---|---|---|---|---|
| 3 | `notes/r10b-raw-build-package.md:946` | 两条命令 + 输出伪装成 `#` 注释混排;第二条 `ls` 是**故意失败**的(那正是 ▲ 的证据) | 合成一条命令,`ls` 报错并进 stdout 并显式打退出码 | `scripts/dev-sandbox.sh` / `exit=2` |
| 14 | `notes/r10b-raw-message-render.md:1418` | `cd` 到已消失的 `/home/user/r10b-ts/...`;结果写成 `# → 53` | 换基线路径 + 配对 | `53` / grep `exit=1` |
| 17 | `notes/r10b-raw-settings-billing.md:1317` | 同上 | 换基线路径 + 补退出码 + 配对 | `exit=1`(零命中) |

**#14 / #17 补退出码这件事本身是判据升级,不只是排版。** 一条零命中的 grep 与一条
路径不存在的 grep 在底稿里长得一模一样(都是「无输出」),而这两者的含义相反 ——
`grep: apps/shared/src: No such file or directory` 正是 #17 原样重跑时的 stderr。
把 `echo "exit=$?"` 钉进配对块,「零命中」这个结论才真的被证据支撑。

### 批次 3 —— 7 块「换个跑法就能跑」的:cwd / 缩进 / 跨块临时文件 / 故意失败

**结论:7 块全部判「修好它」,全部改到配对逐字比对通过,无一伪造输出。**
这批的共同点是**结论本身没问题,坏的是命令的可重跑形态**。

| # | 位置(改前行号) | 病灶 | 修法 | 钉住的读数 |
|---|---|---|---|---|
| 1 | `notes/r10-raw-ui-tui-components.md:1393` | cwd 写在注释里(「在 ui-tui 下跑」) | 注释变成真 `cd` + 配对 | 12 / 空 / 8 / 空;24-36、37-45 |
| 2 | `notes/r10-raw-ui-tui-core.md:658` | 读 `/tmp/handled.txt`,该文件由**另一个块**用 `tee` 生成 | 客户端处理集就地算出,脚本自足 | 63 / 45 / 交集 41 / 只服务端 22 |
| 32 | `notes/r8d-raw-update-pipeline.md:2630` | `ls -a .gitmodules` **故意失败**,报错走 stderr | `2>&1` 把报错并进 stdout + 补退出码 + 配对 | 不存在 / 23 / 0 / 零命中 |
| 40 | `notes/r9a-raw-curator.md:49` | cwd 写在注释里 | 注释变成真 `cd` + 配对 | `0` + 三行(全在 `curator.py`) |
| 46 | `notes/r9a-raw-research-pipeline.md:1761` | 列表缩进带进 `-c` 字符串;且用系统 `python3`(无 `rich`) | 命令顶格 + 改用项目 venv + 配对 | `False` / `[]` / `23` |
| 49 | `notes/r9a-raw-skills-sync.md:743` | 同上(a) | 命令顶格;原 ```console 改 ```text 使其被比对 | 三个 `False` |
| 53 | `notes/r9b-raw-video.md:2352` | `pip show` 对未装包**退出 1 且提示走 stderr** | `2>&1 | tail -1`,结论由输出内容承载 | `WARNING: Package(s) not found: fal-client` |

**#2 是这批里最值得记的一个,因为它暴露了两个关卡之间的一条缝。**
它读的 `/tmp/handled.txt` 由同一份底稿 §3.2 那条命令用 `tee` 写出,而 `tee` 命中关卡的
MUTATING 分类器(`scripts/verify_evidence_commands.py:116`:`|rm\s+-|mv\s+|cp\s+|chmod\s+|chown\s+|tee\s+|mkdir\s+`),
于是**生产者永远不跑、消费者每次都跑** —— 消费者必然 `FileNotFoundError`。
修法不是去掉 `tee`(那会让生产块变成待跑),而是**让消费者自足**:用与生产者完全相同的
`^      case '…'` 正则就地扫同一个文件。**任何跨块的临时文件在这套关卡下都是这个形状**,
见移交 `H-R11C-C-b`。

**#46 的第二重病灶(系统 `python3` 缺 `rich`)是本轮才暴露的**:R9A 当时的会话里
`python3` 想必解析到别处。改用 `/home/user/hermes-venv/bin/python` 后三个读数与原文逐字一致
—— 也就是说**原结论对,原命令错**,正是 CLAUDE.md「一条重跑给出相反结果的命令比不写更糟」
所指的那一类的温和版本(这里是"跑不出来",不是"跑出相反结果")。

### 批次 4 —— 19 块 `$` 提示符转录与探针输出

**结论:19 块里 13 块判「修好它」(拆成可重跑命令 + 配对逐字输出)、6 块判「不修,如实声明」。**
「不修」的 6 块全部落在同一条判据上:**产生这段输出的东西已经不在仓库里**
—— 5 块是 R9A 场景探针的输出而探针从未进过版本控制,1 块的省略号连 `print` 语句一起吃掉了。

**修好的 15 块**(全部配对通过):

| # | 位置(改前行号) | 钉住的读数 |
|---|---|---|
| 21 | `notes/r3-90-doc-conflict-rulings.md:32` | 代码面零命中;全仓只命中两份互为翻译的文档 |
| 22 | `notes/r7b-90-doc-conflict-rulings.md:175` | `send_slash_confirm`/`send_clarify` 在 3745/3780;另三个方法零命中 |
| 23 | `notes/r7b-90-doc-conflict-rulings.md:307` | 文档面零命中;`.py` 面四处 |
| 24 | `notes/r8b-90-handover-rulings.md:142` | 六个 `atomic_yaml_write` 写入点 |
| 33 | `notes/r9a-h-r8d-c-env-loader-lock.md:68` | 5 个模块级可变全局 + 3 个常量的行号表 |
| 39 | `notes/r9a-h-r8d-c-env-loader-lock.md:621` | `4 files, 124 tests passed, 0 failed` |
| 41 | `notes/r9a-raw-egress.md:345` | 7 处网络调用点(含 2 处自认的误命中) |
| 42 | `notes/r9a-raw-egress.md:505` | (A) 6 import / (B) 只有 docker.py / (C) 两处非接线 |
| 43 | `notes/r9a-raw-egress.md:1184` | 18 处 logger 调用点 |
| 44 | `notes/r9a-raw-egress.md:1566` | 4 个未回填的 header-auth 键 |
| 45 | `notes/r9a-raw-egress.md:1678` | 65534 / 65535 / **65536(越界)** |
| 50 | `notes/r9a-raw-verification.md:1398` | 全仓 10 处,非测试 3 处 |
| 51 | `notes/r9a-raw-verification.md:1520` | `unverified` → `passed kind=lint changed_paths=[]` / `nudge: None` |

**#39 的处置里有一条判断值得写下来:不是所有输出都该被逐字钉住。**
原块贴的是 `=== Summary: 4 files, 124 tests passed, 0 failed (100% complete) in 3.1s (8 workers) ===`,
而本轮重跑是 **2.6s** —— 耗时是机器噪声。把它钉进配对块,关卡就会按机器快慢随机报错,
那正是「一条关卡开始狂叫,作者就学会忽略它」的起点。所以配对块只取 Summary 的**稳定投影**
(`grep -oE "Summary: … files, … tests passed, … failed \(…% complete\)"`),
三个真读数一个不少。**同理 #45:本容器 CPython 的 `OverflowError` 消息带句点
(`port must be 0-65535.`),原块抄的没有 —— 这一处逐字差异已在正文点名,以实跑为准。**

**#51 是本片唯一一次「把省略号补回去」。** 它的前言写作 `... (同上建 Node 工程 p) ...`,
而那段前言逐字就在同一节 (a) 块里;补全后三行输出与原块**逐字一致**,
说明原结论对、原命令不完整。**#52 长得几乎一样却判了不修**,分界线是:
它的省略号**连产生那三行输出的 `print` 一起吃掉了**,重建就必须猜那三行是怎么打出来的
——猜出来的命令一旦跑出「看起来合理」的输出,就是伪造。**能补的补,要猜的不补。**

**6 块声明为不可重跑:**

| # | 位置 | 理由 |
|---|---|---|
| 34 | `notes/r9a-h-r8d-c-env-loader-lock.md:503` | 场景 1 探针输出;探针脚本未进版本控制 |
| 35 36 | 同上 `:529` `:540` | 场景 2 无锁/有锁两半 |
| 37 | 同上 `:557` | 场景 3(时序测量,含 49.3 ms 这类不可重复的数) |
| 38 | 同上 `:582` | 场景 4(300 轮对撞) |
| 52 | `notes/r9a-raw-verification.md:1544` | 省略号吃掉了 `print`,重建必须猜 |
| (附带) | `notes/r9a-h-r8d-c-env-loader-lock.md:499` 的 `[自证]` | **不在 55 之列的同型块**,顺手一并声明,见下 |

**负结论的搜索面(R9A 探针为何找不到)**:`ls data/` 列出 `r10 / r10b / r11a / r11b / r11c / r9d`
六个轮次目录,**没有 `r9a`**;再以 `find . -path ./.git -prune -o -name "*.py" -print | grep -i r9a`
搜全仓 Python 文件名,只命中 `data/r9d/probes/` 下三个 **R9D 自己**为复查 R9A 而写的文件
(`h_r9a_b_repro.py` / `h_r9a_b_run_variant.py` / `h_r9a_e_ctx_probe.py`),
**没有一个是 R9A 当轮那五个场景探针**。排除面:未搜 `.git` 内部历史(那不是现役产出)。

**那个「附带」块是本片的一个额外发现,值得单独记(见移交 `H-R11C-C-e`)。**
`notes/r9a-h-r8d-c-env-loader-lock.md:492` 那块 `[自证] 桩生效:get_secret_source -> 'bitwarden';…`
与 #34–#38 完全同型(探针输出被写在 ```verify 里),**却不在这 55 之列** ——
因为它的正文里有一个 `->`,而关卡的 `REDIRECT_WRITE` 正则
(`scripts/verify_evidence_commands.py:121`:`REDIRECT_WRITE = re.compile(r"(?<![0-9<>])>\s*(?!/dev/null)[^\s|&;]+")`)
把 `-> 'bitwarden'` 读成了一次写重定向,于是整块被判 MUTATING、**永不执行**。
`notes/r9a-raw-verification.md` §7.5 (a) 那块也一样(输出里有 `-> kind=test`)。
**「被分类器藏起来的坏块」是这 55 之外的一整类**,数目不在本片测量口径内。

### 批次 6 —— 2 块依赖会话脚手架的(#47 #48)

**结论:2 块判「不修,如实声明」,与 #52 同一条判据 —— 重建必须猜。**

`notes/r9a-raw-skills-agent-side.md` 的这两块用 `HERMES_HOME=$SC/h4`(#47,§ ■-1)
与 `HERMES_HOME=$SC/h5`(#48,§ ■-2)指向 R9A 会话 scratchpad 下**手搭的 skill 脚手架**,
重跑分别抛 `KeyError: 'content'` 与 `TypeError: cannot unpack non-iterable NoneType object`
—— 都是「脚手架不在了,函数拿到空数据」的下游表现,不是被测代码的问题。

**为什么不能重建**:该底稿自己在末尾交代「所有 `HERMES_HOME=$SC/hN` 的实测环境都建在会话
scratchpad 下」,而**脚手架的内容从未被写下来** —— `plugskill/SKILL.md` 的正文、
`/pbundle` / `/combo` / `/alpha` / `/beta` 这几个 bundle 的定义,底稿里一处都没有。
造一份 SKILL.md 就能让命令跑通并打出「看起来合理」的输出,而那恰恰是伪造。
与 #51 的分界线还是同一条:**能补的补(前言逐字就在同一节里),要猜的不补。**

这两块与 #52 一起构成移交 `H-R11C-C-d`:**证据块里的省略号只能省「已在同一份底稿别处
逐字写过」的部分。**

### 批次 5 —— 2 块被关卡自己的正则截断的(#0 #20)+ 1 块在 `reports/` 里的(#54)

**结论:#0 与 #20 不是作者写错,是关卡的形状缺陷;#54 按 `reports/` 规矩只改围栏标签、写进勘误节。**

**#0 / #20 —— 块正文里的字面三反引号会把块识别正则截断在半路。**
关卡用 `NOFENCE`(见 `scripts/verify_evidence_commands.py:101`:
`NOFENCE = r"(?:(?!\x60\x60\x60).)*?"`)匹配块正文,所以**正文里任何一个字面三反引号
都会被当成块的结尾**。这两块偏偏都是「检查围栏块」的自查脚本,非提到围栏不可:

- `notes/r10-raw-native-vendor.md:770` —— 自查 7 处 `.h` 锚点的围栏块。被截断后跑出
  `SyntaxError: unterminated string literal (detected at line 13)`。
- `notes/r11b-raw-notes-citation-cleanup.md:257` —— 自查 `r3-10` 行号栏的逐行审计。
  **这一块下方本来就配了 ```text 块,但那次配对从未成立过**:`PAIR` 正则同样在字面反引号处
  截断,于是关卡把它记成**未配对**块、再拿半截脚本去跑。改完之后它才第一次真的被比对。

改法:脚本里不写字面反引号,用 `chr(96) * 3` 构造,**语义完全相同**。改完两块都配对通过,
读数分别是 `checked=7 problems=0` 与 `gutter-lines=103 verbatim=88 differing=15`
—— 与两份底稿正文原本声称的数字**逐字一致**。

**这一类在全语料里还剩几处?实测 0 —— 但我第一次量错了,过程记在这里。**

**判据**:按行找出真正的块(开栏 `​```verify`,闭栏为**第一条 `strip()` 后恰为三反引号的行**),
再看真正的块正文里有没有出现字面三反引号。工具:`data/r11c/c-bad-evidence-innerfence.py`。

```verify
python3 data/r11c/c-bad-evidence-innerfence.py
```

```text
0
```

**这个 0 是「含本片底稿在内」的读数。剔除本片底稿(`notes/r11c-*`)后仍是 0** ——
两个读数相同,原因是本底稿在**改到 0 之前**自己也命中过一次:上面那条对账命令原本
在 Python 里写了字面 `'\x60\x60\x60verify\n'`,于是本底稿被判据点名
(`notes/r11c-raw-bad-evidence.md:308`),同时关卡也报 `EVIDENCE-RUNFAIL`
(半截命令 → `SyntaxError`)。**本片自己踩了自己写的 `H-R11C-C-a`。**
改成 `chr(96) * 3` 后两个读数才都归零 —— 这正是「报告这个测量的动作会改变读数」的实例,
按 CLAUDE.md 两个读数都写在这里。

**第一版判据把闭栏写成 `rstrip() != BT`,读数是 14,那 14 里绝大多数是假的。**
列表里的围栏块是缩进的(`   ```` ``` ````),`rstrip()` 认不出缩进的闭栏,
于是扫描越过它一路并吞后面几个块,把邻块里的反引号算到前一个块头上。
换成 `strip()` 之后读数是 0。**两个数不是「同一个测量做了两遍」,是两条不同的判据**
——按 CLAUDE.md「同一指标多次/多方法测量必须分别标注」,两个都写在这里,口径如上。

*这次量错是被关卡当场抓住的,值得照实写下来:我先按第一版判据的输出手写了一份 14 行清单
贴进 ```` ```text ````,`verify_evidence_commands.py` 重跑后报 `EVIDENCE-DIFF`,
指出清单里有一行(`reports/round-8a-configuration-surface.md:830`)**命令根本没产生过**。
那正是 R10B 立这条关卡时抓到的第四种形态(「一段从未由该命令产生过的输出被写进底稿,
数字看起来完全合理」)。**人工评审抓不住这一类,因为它要求评审者真的去跑那条命令。***

**0 不是空跑出来的 —— 负控证明判据抓得住。** 把改前的两份原文取出放进一个临时树,
用同一条判据跑:

*(R11C 主线更正,只改取证方式不改结论:原命令写的是 `git show HEAD:`,而**本轮 commit 一落,
`HEAD` 就成了清理后**,负控于是从 2 跑成 0 —— 一个"证明判据抓得住"的负控反过来证明了
判据抓不住。这与 R11B 报告 §7.2 记下的第三处**完全同型、同一个片号、隔一轮原样重演**。
改钉本轮开工点 `b419bc1`(R11B 合入 main 那个提交)。)*

```verify
SCR=$(mktemp -d); mkdir -p "$SCR/notes"; \
  git show b419bc1:notes/r10-raw-native-vendor.md > "$SCR/notes/r10-raw-native-vendor.md"; \
  git show b419bc1:notes/r11b-raw-notes-citation-cleanup.md > "$SCR/notes/r11b-raw-notes-citation-cleanup.md"; \
  python3 - "$SCR" <<'PY'
import sys
from pathlib import Path
BT, hits = chr(96) * 3, []
for p in sorted(Path(sys.argv[1]).rglob("*.md")):
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip() == BT + "verify":
            j = i + 1
            while j < len(lines) and lines[j].strip() != BT:
                j += 1
            if any(BT in ln for ln in lines[i + 1:j]):
                hits.append(f"{p.name}:{i + 1}")
            i = j + 1
        else:
            i += 1
print("negative-control hits =", len(hits))
print(*sorted(hits), sep="\n")
PY
```

```text
negative-control hits = 2
r10-raw-native-vendor.md:770
r11b-raw-notes-citation-cleanup.md:257
```

即:**改前恰好命中这两块、改后全语料 0**。所以这一类在本轮**已清零**,
但它是关卡形状造成的、随时会因为下一个人写自查脚本而复发,故仍记移交 `H-R11C-C-a`
(需要改 `scripts/`,本片无权改)。

**#54 `reports/round-8-fix-review-1.md:180`。** 与 #24 是**同一条命令的两份副本**。
按 CLAUDE.md「`reports/` 正文不静默改写」:**不**拆成命令 + 配对输出(那是改写正文),
只把围栏标签由 ```verify 换成 ```shell-session —— 它本来就是 shell 会话转录,
而 `shell-session` 是 CLAUDE.md 已列的声明式非源码围栏。**块内容逐字未动**,
六个命中点、`config.py:3112` 那句旁注、结论全部原样保留。
改动已写进该报告文末勘误节第 3 条并点名。要机械核验这六个写入点,以 `notes/` 那份为准
(#24,已拆成配对块)。

## 3. 收尾读数与逐类对账

### 3.1 清理后的全语料读数

```verify
cat data/r11c/c-bad-evidence-census-after.txt
```

```text
readonly_unpaired=538 exit0=510 silent_exit1=28 bad=0 skipped_mutating=155
bad_by_kind=(none)
baseline_porcelain_changed=False
```

| 指标 | 清理前 | 清理后 | 差 |
|---|---|---|---|
| `readonly_unpaired`(被真跑的未配对只读块) | 593 | **538** | **−55** |
| `exit0` | 510 | 510 | 0 |
| `silent_exit1`(退出非零但无 stderr,正当性未判) | 28 | 28 | 0 |
| `bad`(本片的清理对象) | **55** | **0** | **−55** |
| `skipped_mutating` | 156 | **155** | **−1** |

*本片底稿定稿后又整跑了一次普查(此时本底稿已在语料内),四个数与上表**逐个相同**:`readonly_unpaired=538 exit0=510 silent_exit1=28 bad=0 skipped_mutating=155`。相同是有原因的、不是巧合:本底稿的 7 个 ```verify 块**全部配对**,而普查只跑未配对块,所以它一个块也没往池子里加。*

**逐类对账(不靠「差数正好对上」这种巧合式论证,直接量块)。**
对片 C 那 31 个文件,用关卡自己的 `PAIR` / `ANY_VERIFY` / `is_mutating`
分别量改前与改后。

*(R11C 主线更正,只改取证方式不改结论:原命令用 `git show HEAD:` 取「改前」,
而本轮 commit 一落 `HEAD` 就是改后,于是 before 与 after 读成同一份、delta 全变 0。
与上面负控那处**同一物种、同一份底稿里的第二例**。改钉本轮开工点 `b419bc1`。)*

```verify
cd /home/user/hermes-study && python3 - <<'PY'
import subprocess, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from verify_evidence_commands import PAIR, ANY_VERIFY, is_mutating
files = Path('data/r11c/slice-c-files.txt').read_text().split()
agg = {}
for tag, get in (('before', lambda f: subprocess.run(['git', 'show', f'b419bc1:{f}'],
                                                     capture_output=True, text=True).stdout),
                 ('after', lambda f: Path(f).read_text(encoding='utf-8'))):
    v = pr = u = mu = 0
    for f in files:
        s = get(f)
        paired = {x.group('cmd') for x in PAIR.finditer(s)}
        OPEN = chr(96) * 3 + 'verify\n'   # 不写字面围栏,否则本块自己被 NOFENCE 截断
        bodies = [x.group(0)[len(OPEN):-3] for x in ANY_VERIFY.finditer(s)]
        v += len(bodies); pr += len(paired)
        for b in bodies:
            if b in paired or not b.strip():
                continue
            mu += is_mutating(b.strip()); u += not is_mutating(b.strip())
    agg[tag] = (v, pr, u, mu)
    print(f'{tag:6s} verify-blocks={v:4d} paired={pr:3d} readonly-unpaired={u:4d} mutating-unpaired={mu:3d}')
b, a = agg['before'], agg['after']
print(f'delta  verify={a[0]-b[0]:+d} paired={a[1]-b[1]:+d} '
      f'readonly-unpaired={a[2]-b[2]:+d} mutating-unpaired={a[3]-b[3]:+d}')
PY
```

```text
before verify-blocks= 282 paired= 13 readonly-unpaired= 211 mutating-unpaired= 58
after  verify-blocks= 254 paired= 41 readonly-unpaired= 156 mutating-unpaired= 57
delta  verify=-28 paired=+28 readonly-unpaired=-55 mutating-unpaired=-1
```

**读法:−55 拆成两笔,两笔都由上表直接读出,没有余数。**

- **−28:改标围栏。** `verify-blocks` 少 28(27 → ```text,1 → ```shell-session)。
  其中 **1 块原本被判 MUTATING**(`[自证]` 那块,正文里的 `->` 被读成写重定向),
  所以它减在 `mutating-unpaired` 上(58 → 57),**只有 27 块减在 readonly 池里**。
- **−28:变成配对块。** `paired` 从 13 涨到 41。配对块归比对腿管,**不进普查的 readonly 池**。
- 27 + 28 = **55**,与 `bad` 的 −55 逐个对上;`exit0` 与 `silent_exit1` **一动不动**,
  说明我没有顺手把本来跑得通的块或那 28 块「静默 exit-1」搅进来。

### 3.2 两个读数的口径差(R11B 的 63 vs 本轮的 55)

**这不是同一个测量,不得写成「63 减到 55」。** 三处口径差同时存在:

| | R11B | R11C 片 C |
|---|---|---|
| 分类法 | **人工读 stderr** 分 A/B/E | **机械判据**,判据从关卡 import(`data/r11c/probes/runnability_census.py:35` 的 `classify_failure`) |
| 桶 | A 22 / B 29 / E 12 = 63 | A 7 / B 23 / E 8 / **OTHER 17** = 55(机械版多一个「归不进三类」的桶) |
| TIMEOUT | 900 s | 120 s |
| 语料 | R11B 合入**前** | R11B 合入**后** |

**本片报的是 55 那一版**,因为它可重算:同一条判据任何一轮重跑都得同一个数,
而「人工读 stderr」不可重放。**两个数都写在这里,谁也不是谁的修正。**

### 3.3 关卡自查读数

| 关卡 | 范围 | 结果 |
|---|---|---|
| `verify_evidence_commands.py` | 本片底稿 | `paired=7 unpaired=0 differing=0 timedout=0` / `ran=0 runfail=0` / **exit 0** |
| `verify_citations.py` | 本片底稿 | `citations=13 OK=0 UNCHECKED=13` / `table_anchors=47 OK=6 UNCHECKED=41` / **exit 0** |
| `verify_citations.py` | 改过的 31 个文件 | `citations=2230 OK=1813 UNCHECKED=417`,**可校验比例 81.3%** / `table_anchors=760 OK=470 UNCHECKED=290` / 0 MISMATCH / 0 BLOCK-DRIFT / 0 TABLE-DRIFT / 0 TABLE-OUT-OF-RANGE / **exit 0** |

*上面两行是**定稿时实测**的自校验读数,**故意没有写成 ```verify + ```text 配对块**。
理由现摆在本轮的失败清单里:`notes/r10b-raw-capability-panels.md:1335` 与
`notes/r10b-raw-chat-composer.md:1750` 正是把「校验器扫本文件」的输出钉成了配对块 ——
**那是一个不动点**,此后任何一次编辑都会让它漂,而漂的原因与证据质量无关(见 §4)。
CLAUDE.md R11B 那条「自校验读数不能写进 ```verify 块」防的是无限递归,
这里多防一层:**自指的计数不该被钉死。***

*而且这个计数对「报告它」这个动作**不幂等**:上一版把读数写成 `citations=11` 之后重跑,读数变成了 13 —— 那两条新增就是**解释这件事的那段话里的锚点**。与 CLAUDE.md 给「搜过没有」类测量定的那条规矩同一个物种:**写下读数会改变读数**。*

**本片底稿的可校验比例是 0%,这个数得解释清楚,不能当成没达标就算了。**
`verify_citations.py` 把锚点**解析到基线** `/home/user/hermes-agent`,
而本底稿的研究对象是**学习仓库自己的证据块** —— 10 条锚点全是 `notes/…` 与 `scripts/…`
这样的学习仓库路径,基线里根本没有这些文件,于是**结构上不可能有一条 OK**。
70% 下限的口径是「当轮 notes 这一堆**对 hermes-agent 的**证据层产出」,本底稿不在那个口径里。
**要造几个基线代码块把比例拉上去是容易的,但那是给关卡表演,不是证据。**
底稿里所有 `路径:行号` 的正确性由另一条腿保证:它们来自
`data/r11c/c-bad-evidence-scan.py` 机器产出的 `data/r11c/c-bad-evidence-blocks.json`,
不是手抄的。

**逐块表里的行号一律是「改前」坐标**(`git show HEAD:<file>` 可复现),
因为块被改后位置全变了,而下一轮要对照的是**当时那 55 块是哪 55 块**:

```verify
python3 -c "import json;d=json.load(open('data/r11c/c-bad-evidence-blocks.json'));
print('blocks_scanned =', len(d));
print('bad_at_scan_time =', sum(1 for r in d if r['kind'] not in ('OK','SILENT','MUTATING')))"
```

```text
blocks_scanned = 269
bad_at_scan_time = 55
```

### 3.4 基线只读自查

```verify
git -C /home/user/hermes-agent status --porcelain; git -C /home/user/hermes-agent rev-parse HEAD
```

```text
863e31318553cda8ad61df681d08175364d4164b
```

`status --porcelain` 无输出 = 基线干净;HEAD 仍是基线 commit。
全程未在基线内落任何文件,未装任何包(所有执行基线代码的命令都带
`HERMES_DISABLE_LAZY_INSTALLS=1`);venv 包数保持 **87**。

## 4. 本片测量口径之外的三类(都不在 55 里,逐条移交)

**说清楚这三类是什么,比把它们混进 55 里更有用。** 55 的口径是
「**未配对**的**只读** verify 块,重跑时**非零退出且有 stderr**」。下面三类各自落在这个口径之外:

1. **配对块的漂移**(`EVIDENCE-DIFF`):这 31 个文件里有 **5 处**。它们是配对块,
   归比对腿管,普查的 `bad` 根本不数它们。
2. **被 MUTATING 分类器藏住的坏块**:正文里一个 `->` 就足以让整块被判 MUTATING、永不执行。
3. **被 `NOFENCE` 正则截断的块**:本轮已清零,但成因在关卡的形状里,会复发。

第 1 类**不是我改出来的**,有直接证据:把两份 `verify_citations.py` 自查块所在文件的
**HEAD 原文**取出来单独跑,计数与改后完全相同 ——

```verify
cd /home/user/hermes-study && T=$(mktemp -d) && \
  for f in notes/r10b-raw-capability-panels.md notes/r10b-raw-chat-composer.md; do \
    git show "HEAD:$f" > "$T/$(basename $f)"; \
    python3 scripts/verify_citations.py /home/user/hermes-agent "$T/$(basename $f)" \
      | grep -E "^citations="; \
  done
```

```text
citations=58  OK=46  UNCHECKED=12
citations=81  OK=60  UNCHECKED=21
```

改后同一条命令对现役文件给出的也是 `58/46/12` 与 `81/60/21`(见 §3.3 那一轮实跑),
**两者一致,所以这 5 处漂移在我动手之前就在**。它们的形态是 R10B 立这条关卡时点名的那一种
——**贴进底稿的输出是手工裁剪过的**:

| 位置 | 贴了几行 | 实跑几行 | 一句话现象 |
|---|---|---|---|
| `notes/r10b-raw-capability-panels.md:1335` | 4 | 5 | 数字全对,但把 `table_anchors=` 行末的「(表格行内锚点…)」括号裁掉了 |
| `notes/r10b-raw-chat-composer.md:1750` | 4 | 5 | 同上裁剪,**且 `table_anchors` 的 OK/UNCHECKED 是 13/18,实跑 14/17** |
| `notes/r10b-raw-lib-themes.md:672` | 6 | 48 | 探针打 48 行,只贴了 6 行汇总 |
| `notes/r10b-raw-lib-themes.md:1831` | 3 | 0 | **配对**的 vitest 块,`cd /home/user/r10b-ts/...` 已不存在,stdout 为空 |
| `notes/r10b-raw-settings-billing.md:358` | 3 | 37 | 探针打 37 行,只贴了 3 行 |

## 移交

| 编号 | 锚点 + 一句话现象 | 建议动作 |
|---|---|---|
| `H-R11C-C-a` | `scripts/verify_evidence_commands.py:101` 的 `NOFENCE` —— 块正文里出现**字面三反引号**时,`NOFENCE = (?:(?!```).)*?` 会把块截断在那里,于是一个本来配对的块被记成未配对,再拿半截命令去跑 | 需要改 `scripts/`(本片无权)。本轮两处已通过改脚本写法(`chr(96) * 3`)绕开,全语料现为 0(判据与负控见 `data/r11c/c-bad-evidence-innerfence.py`),但成因在关卡里,**下一个写自查脚本的人会再踩**。建议给 `NOFENCE` 加「闭栏必须独占一行」的约束 |
| `H-R11C-C-b` | `notes/r10-raw-ui-tui-core.md:341`:`| sed -E "s/.*'([a-z_.]+)'/\1/" | sort -u | tee /tmp/handled.txt | wc -l` —— 生产者带 `tee` 被判 MUTATING **永不跑**,消费块每次都跑,于是消费块必然 `FileNotFoundError` | 本轮已把该消费块改成自足。**任何跨块临时文件在这套关卡下都是这个形状**,建议写进下一轮派工书:证据块不得依赖另一个块产生的文件 |
| `H-R11C-C-c` | `notes/r9a-h-r8d-c-env-loader-lock.md:515`:`[场景1] 只 hydrate 了 homeB` —— R9A 五个场景探针的**脚本从未进过版本控制**(全仓无 `data/r9a/`),这些读数在任何新容器里都不可重跑 | 本轮已如实声明为不可重跑。若后续轮要再用 ■-R9A-01 / ■-R9A-02 这两条定案,**必须先重写探针**;现有读数只能当线索,不能当证据 |
| `H-R11C-C-d` | `notes/r9a-raw-verification.md:1577`:`... (建 p,package.json 内容为 "{}" —— 无 scripts) ...` 与 `notes/r9a-raw-skills-agent-side.md:2602`:`cd /home/user/hermes-agent && HERMES_HOME=$SC/h4` —— 省略号吃掉的不只是前言,还有产生输出的 `print` / 脚手架内容,重建必须猜 | 已声明不可重跑。规则建议:**证据块里的省略号只能省「已在同一份底稿别处逐字写过」的部分**,否则等于把命令删了一半 |
| `H-R11C-C-e` | `scripts/verify_evidence_commands.py:121`:`REDIRECT_WRITE = re.compile(r"(?<![0-9<>])>\s*(?!/dev/null)[^\s|&;]+")` —— 输出里一个 `->`(如 `get_secret_source -> 'bitwarden'`)就被读成写重定向,整块判 MUTATING、**永不执行**;`notes/r9a-h-r8d-c-env-loader-lock.md:499` 与 `notes/r9a-raw-verification.md` §7.5 (a) 两块正是这样躲过 55 的 | 需要改 `scripts/`。建议给 `REDIRECT_WRITE` 排除 `->`;**改之前先量一遍全语料会新增多少 RUNFAIL**,按 R7C→R8A 那套分期落地 |
| `H-R11C-C-f` | 5 处**配对块**漂移,见 §4 表(如 `notes/r10b-raw-settings-billing.md:358`:`python3 data/r10b/probes/probe_c_billing_codes.py /home/user/hermes-agent` 贴 3 行、实跑 37 行) | **不在片 C 的 55 口径内,本片未改**。它们是「贴进底稿的输出被手工裁剪」这一类,和本片修的是两个测量。建议单独立项,处置时注意其中 `lib-themes:1831` 是**配对的**死路径块,与本片批次 2 同源 |

## 完成信号

**片 C 完成。** 产出与改动:

- **新建底稿**:`notes/r11c-raw-bad-evidence.md`(本文件)。
- **改过的历史产出 31 个**:`data/r11c/slice-c-files.txt` 里的 30 个 `notes/` +
  1 个 `reports/`(后者只换围栏标签 + 文末勘误节第 3 条,正文未改写)。
- **新建工具与数据**(均在 `data/r11c/c-bad-evidence-*` 允许面内):
  `c-bad-evidence-scan.py`(定位 55 块的行号与整块原文)、
  `c-bad-evidence-refence.py`(批次 2 的逐字匹配改标器)、
  `c-bad-evidence-innerfence.py`(字面三反引号截断判据)、
  `c-bad-evidence-blocks.json`(扫描产出)、`c-bad-evidence-census-after.txt`(清理后普查)。
  另**删除**了首批(已回滚那一批)留下的未跟踪脚本 `data/r11c/c-bad-evidence-declare-node.py`
  —— 它从未被执行过,而留下两个功能重叠、只有一个真跑过的改标器,
  正是「这份产出是哪条命令生成的」这类歧义的来源。
- **未做**:未 commit、未 push(主线统一提交);未动 `scripts/`、`CLAUDE.md`、台账、`chapters/`;
  未动基线(`git -C /home/user/hermes-agent status --porcelain` 为空);未装任何包。
