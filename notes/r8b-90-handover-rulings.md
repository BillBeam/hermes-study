# r8b-90 · R8A 移交项定案

> 溯源约定:`路径:行号 @ 863e313` + 代码原文块。实跑环境见 `notes/r8b-02`。
> 本轮认领 R8A 移交里标注 **R8B** 的 6 条:H-1 / H-2 / H-7 / H-13 / H-14 / H-16 / H-17
> (H-1 / H-2 已在 `notes/r8b-02` 单独结清,此处只记结论)。

| 移交项 | R8A 标注轮次 | 本轮结论 |
|---|---|---|
| H-1 | R8B | **结清**,并升格出 ■-R8B-01(详见 `notes/r8b-02` §1) |
| H-2 | R8B | **结清**,影响面穷举 = 4 子树 / 24 叶,14 个真出事(`notes/r8b-02` §2) |
| H-7 | R8B / R8D | **结清,负结论**(见 §1) |
| H-13 | R8B / R8C | **部分结清 + 明确移交 R8C**(见 §4) |
| H-14 | R8B | **结清,给出判据**(见 §3) |
| H-16 | R8B | **结清,负结论:是有意的,而且是本仓库做对的样本**(见 §2) |
| H-17 | R8B / R8C | **确认存在,但后果比子代理报的窄**(见 §5) |

---

## 1. H-7:没有第三个"读原始配置后落盘"的调用方(负结论)

**R8A 的问题**:`require_readable_config_before_write`(`hermes_cli/config.py:3065`)
只检查文件**可读**不检查**可解析**;`set/unset_config_value` 各自补了解析检查,
**但是否存在第三个直接 `read_raw_config()` 后落盘的调用方**未穷举
——若有,坏 YAML 会被静默截断。

**候选锁定**:全仓 `read_raw_config()` 调用点里,真正会**落盘**的是**迁移流水线**
——每个迁移步骤都拿 `read_raw_config()` 的结果原地改后交给 `_persist_migration`:

`hermes_cli/config.py:2142 @ 863e313`

```python
    ``read_raw_config()`` after in-place mutations (including key removals);
```

而 `_persist_migration` 是不带 `merge_existing` 的直写:

`hermes_cli/config.py:2147 @ 863e313`

```python
    save_config(config)
```

**这正是 H-7 描述的形态**:读原始 → 改 → 落盘,中间没有解析守卫。
若 `read_raw_config()` 因 YAML 坏了返回 `{}`,落盘就会把用户的配置截断成近乎空文件。

**实跑判定(13 行、含未闭合 flow sequence 的坏 YAML)**:

```
read_raw_config() 对坏 YAML 的返回 = {}
migrate_config warnings = []
config_added = []
before sha1 = acd488cb7918c808514ffaf15eab2beaa903fcee   before bytes = 137
after  sha1 = acd488cb7918c808514ffaf15eab2beaa903fcee   after  bytes = 137
RESULT: 文件逐字节未改
```

**没有被截断。H-7 关闭。**

**但"为什么没被截断"值得单独记一笔,因为它不是写路径上的守卫拦住的。**
坏 YAML 下版本检查的返回是:

```
坏 YAML 下 check_config_version() = (33, 33)
=> 迁移阶梯是否会跑: False
```

即**当前版本 == 最新版本**,于是迁移阶梯**整个没跑**,自然没有任何写。
对照组(合法但无 `_config_version` 键的两行配置):

```
合法但无版本键的配置 read_raw_config() = {'model': {'default': 'gpt-5'}}
check_config_version() = (0, 33)
```

**报 `(0, 33)`,阶梯正常跑** —— 与 `migrate_config` 注释里写的行为一致:

`hermes_cli/config.py`(`migrate_config` 注释)`@ 863e313`

```python
    # A config with NO ``_config_version`` key at all is NOT floor-refused:
    # that shape is a fresh minimal config (profile clones write bare keys;
    # users hand-write two-line configs), not an ancient install. Those get
    # the normal ladder (the retired <12 steps were no-ops for configs
    # lacking the legacy keys they migrated) and a fresh version stamp —
    # the historical behavior.
```

**差别的来源是"坏 YAML 与文件不存在在这一层无法区分"**——这正是那个守卫的 docstring
自己点名的病根:

`hermes_cli/config.py:3099 @ 863e313`

```python
    Root cause this guards: ``read_raw_config()`` returns ``{}`` for BOTH an
```

**定案 ◇-R8B-a(信息类,不记 ■)**:坏 YAML 之所以没被迁移流水线截断,
**是因为它被当成了"全新安装、已是最新版",而不是因为写路径上有守卫**。
保护是**副作用**而非设计。连带的可观察后果是:**配置坏掉时版本检查会报"已是最新"**,
排障者若只看版本号会被误导。

**但必须公平记一条**:这条误导**不是无声的**。同一次运行里 stderr 打了一段很明确的警告,
还自动存了一份损坏副本:

```
⚠️  hermes config: Failed to parse .../config.yaml: while parsing a flow sequence
  in ".../config.yaml", line 5, column 9
did not find expected ',' or ']'
  ... Falling back to default config — every user override (auxiliary providers,
  fallback chain, model settings) is being IGNORED. Fix the YAML and restart.
  A copy of the corrupted file was saved to .../config.yaml.corrupt.20260808-102922.bak.
```

`ls` 确认 `.corrupt.<时间戳>.bak` 确实落了盘。
**"版本号说谎"与"stderr 说实话"同时成立,所以这条只作信息记录,不升为缺陷。**

---

## 2. H-16:v16 不删旧键是有意的,而且是本仓库做对的那个样本(负结论)

**R8A 的疑虑**:`config_migrations.py:250-266` 的 v16 把
`display.tool_progress_overrides` 搬进 `display.platforms` 后**不删旧键**,
与 v12 / v17 / v29 / v33 的"搬完就删"风格不一致;
"若无意,它就是又一个'旧键恒存在'的种子——■-11 那条 780 秒漂移正是这么来的"。

**结论:有意,而且三处证据互相印证,最关键的是它的优先级顺序与 ■-11 恰好相反。**

**证据一 —— 读取端明说旧键是"仍然支持的向后兼容路径"**:

`gateway/display_config.py:16 @ 863e313`

```python
Backward compatibility: ``display.tool_progress_overrides`` is still read as a
fallback for ``tool_progress`` when no ``display.platforms`` entry exists.  A
config migration (version bump) automatically moves the old format into the new
``display.platforms`` structure.
```

**证据二 —— 默认值那侧专门写了"不再播种"**:

`hermes_cli/config_defaults.py:1201 @ 863e313`

```python
        # NOTE: display.tool_progress_overrides is deprecated and no longer
        # seeded here — use display.platforms. A user-set value is still
        # honored at runtime (gateway display_config back-compat read) and
        # folded into display.platforms by the v15→16 migration.
```

**证据三 —— 优先级:规范键先查,遗留键只当兜底**:

`gateway/display_config.py:213 @ 863e313`

```python
    # 1. Explicit per-platform override (display.platforms.<platform>.<key>)
    platforms = display_cfg.get("platforms") or {}
    plat_overrides = platforms.get(platform_key)
    if isinstance(plat_overrides, dict):
        val = plat_overrides.get(setting)
        if val is not None:
            return _normalise(setting, val)

    # 1b. Backward compat: display.tool_progress_overrides.<platform>
```

### 2.1 与 ■-11 的对照:同一道题,一个做对一个做错,差三处

R8A 的 ■-11(`clarify` 780 秒漂移)与本条是**同一道题**:新旧键并存怎么办。
逐项对照:

| | ■-11 `clarify.timeout`(做错) | H-16 `tool_progress_overrides`(做对) |
|---|---|---|
| 旧键是否被播种进默认值 | **是**(`cli.py:523` 钉死 120)→ "没设过"永远为假 | **否**(`config_defaults.py:1201` 明说不播种)→ 存在即"用户真设过" |
| 查询顺序 | **遗留键优先**,规范键兜底 | **规范键优先**,遗留键兜底 |
| 迁移是否会覆盖已有规范值 | — | **否**:`if "tool_progress" not in platforms[plat]` 才写 |

第三点的原文:

`hermes_cli/config_migrations.py:258 @ 863e313`

```python
            if "tool_progress" not in platforms[plat]:
                platforms[plat]["tool_progress"] = mode
```

**可迁移的结论**:"旧键不删"本身**不是**缺陷,危险的是它与另外两件事叠加
——**旧键被默认值播种**(于是"是否设过"这个判断永久失真)+ **旧键优先**。
三者只要缺一个,旧键长期留在磁盘上都是安全的。
R8A 从 ■-11 得到的教训是"凡依赖'这个键没被设过'的判断,必须做在重复默认值所在的那一层";
**本条把它补全成一条更好用的判据:先保证"存在 == 用户设过",再让规范键赢。**

---

## 3. H-14:status 的崩溃姿态 —— 给判据,不逐处开药

**R8A 的问题**:已定位 8 处可打崩 `hermes status` 的无保护调用点,
4 个崩溃抵抗用例**全部集中在 xAI OAuth 一个块**;
"未做的是给其余 7 处判定'该不该罩'——排障命令的崩溃姿态本身是一条设计题"。

**本轮定案(设计判据,而非逐处补 try)**:

`hermes status` 是**排障命令**。排障命令的读者**已经处在"某处坏了"的状态**,
它的价值全部来自**把还能读到的信息尽量读全**。因此判据是:

> **凡"读某一个子系统的状态"的区块,异常必须被局部罩住并就地显示为该区块的失败;
> 凡"决定整张报告怎么渲染"的前置步骤(终端宽度、配置根、profile 解析),异常可以外抛。**
>
> 判据的落点不是"重要不重要",而是**失败的作用域**:
> 一个平台探测崩了只该让那一行显示 `error`,不该让用户看不到另外 15 行本来正常的信息。
> **排障命令最坏的失败模式,是因为一个坏区块而隐藏了本可暴露病因的好区块。**

按此判据,R8A 定位的 8 处里,**属于"读某子系统状态"的都该罩**,
而现状是只有 xAI OAuth 那一块罩了——**不是因为它更重要,而是因为它先炸过**。
这正是 R8A ■ 组里反复出现的形态:**保护跟着事故走,而不是跟着判据走**,
于是覆盖面永远等于历史事故集合。

**为什么本轮不逐处开药**:`hermes_cli/status.py` 的 `round` 列是 **R8A**、
`status` 已是 `R8A-deep-read`,逐处清点属该文件的收尾;本轮给判据即结清 H-14 的
"该不该罩"这一问,**逐处落实记为 H-R8B-b 移交 R11 复盘**(那时可与 §4 的 8 份实现一起做)。

---

## 4. H-13:平台就绪判定的 8 份实现 —— 本轮核到 R8B 能核的部分

**R8A 的问题**:已定案 status 侧误判(与已修的孪生 `hermes_cli/gateway.py:5451` 对照);
"未做的是把'平台就绪判定'那 8 份逐一对齐核对"。

**本轮立场**:这 8 份的**落点分布在 R8A(status.py)、R8C(web_server.py)与网关侧**,
**只有其中属 CLI 主干的部分在本轮范围内**。R8A 把它标为 "R8B/R8C" 两栖,
本轮据实拆开:**判据已在 §3 给出(同一条:失败作用域),
逐份对齐的清点工作与 R8C 的 web 面重叠更大,整体移交 R8C**,记为 **H-R8B-c**。

**不假报覆盖**:本轮没有逐份跑完 8 个实现的对照表。
写在这里而不是让它悄悄消失——这是 R8A 立 H-18 那条制度的直接沿用。

---

## 5. H-17:锁不对称属实,但后果比子代理报的窄

**R8A 转述的子代理判断**:`env_loader.py:614-669`(无锁)vs `:184`(有
`_SECRET_SOURCE_CACHE_LOCK`),"网关热重载线程与首轮路由线程并发时可能出现同一 home
双份 fetch,或**缓存被空 dict 覆盖**"。

**锁不对称属实。** `_APPLIED_HOMES` 的全部触点:

```
51:_APPLIED_HOMES: set[str] = set()
52:_SECRET_SOURCE_CACHE_LOCK = threading.RLock()
184:    with _SECRET_SOURCE_CACHE_LOCK:
191:    if home_key in _APPLIED_HOMES:
228:    _APPLIED_HOMES.add(home_key)
251:    _APPLIED_HOMES.clear()
615:    if home_key in _APPLIED_HOMES:
653:    _APPLIED_HOMES.add(home_key)
```

`:191` / `:228` 在 `:184` 的锁内;**`:615` / `:653` 与 `:251` 都在锁外**
——三条改写路径里**只有一条持锁**。

**但"缓存被空 dict 覆盖"这个说法不成立,应予收窄。**
`_APPLIED_HOMES` 是 `set`,`:251` 是 `.clear()` 而非赋值,全程没有"用空 dict 覆盖"的写法;
且 CPython 下 `set.add` / `in` / `dict.clear` 都是 GIL 原子操作,**不会撕裂出损坏的容器**。

**真正成立的后果有两条:**

**(a) 典型的 check-then-act 竞态 → 重复 fetch。** `:615` 查、`:653` 才写,两者之间隔着
一整次外部密钥拉取。两个线程同时首次触达同一 home 时,**都会通过 `:615` 的检查、
都会真去 Bitwarden/1Password 拉一次**。而这个标记位存在的唯一目的就是防止重复拉取:

`hermes_cli/env_loader.py:648 @ 863e313`

```python
    # A real fetch attempt happened (success OR error).  Mark the home now
    # so the 3-5 import-time load_hermes_dotenv() calls per startup don't
    # re-fetch / re-print — error retries within one process are opt-in via
```

**注释自己说了"每次启动有 3-5 次调用",即高频重入是常态**;单线程下靠标记位挡住,
并发下这个挡板有一个与网络往返一样宽的窗口。

**(b) `reset_secret_source_cache()` 的三个容器是分三步清的**(`:251-253`),
**整体不是原子的**。清到一半时另一线程完成 `:653` 的 `add`,可能留下
"home 已标记为 applied、但 `_SECRET_SOURCES` 已被清空"的组合。

**定案 ■-R8B-02(中置信)**:锁不对称属实,后果是**重复拉取 + 非原子重置**,
**不是**容器损坏。**未在运行时复现**——需要一个能让两个线程同时首次触达同一 home 的
真实场景(R8A 猜的网关热重载 + 首轮路由是合理候选,但本轮没有构造出来)。
**按 R8A 立的规矩,报"代码确证、运行时未复现",不写成已复现。**

---

## 6. H-18 结转:约 50 条未复核候选里,属 R8B 的部分

**任务书要求**:R8A 的 H-18 记录了约 50 条未逐条复核的候选缺陷(附 11 个文件锚点),
**其中落入 R8B 范围者,本轮一并复核定案或明确移交**。

**做法(可复现)**:对 R8A 的 13 份 `notes/r8a-raw-*.md`,先定位各自"可疑缺陷清单"小节的起始行,
**只在该行之后的区域**里抽锚点,再按 R8B 文件集过滤。逐份计数:

| 底稿 | 清单区 R8B 锚点行 | 清单区总锚点行 |
|---|---|---|
| r8a-raw-migrations-env-secrets.md | 20 | 212 |
| r8a-raw-pairing-key.md | 7 | 33 |
| r8a-raw-mcp-moa-config.md | 3 | 109 |
| r8a-raw-commands.md | 2 | 117 |
| r8a-raw-config-a.md | 2 | 22 |
| r8a-raw-config-c.md | 1 | 9 |
| r8a-raw-defaults-b.md | 1 | 18 |
| 其余 6 份 | 0 | 108 |

去重后,**落在 R8B 文件集的锚点共 9 个**(排除 `subcommands/config.py`
与 `subcommands/pairing.py` —— R8A 已精读并认领):

```
cli.py:53   cli.py:4449   cli.py:4546   cli.py:10333
hermes_cli/main.py:3300   hermes_cli/main.py:11159   hermes_cli/main.py:11601
hermes_cli/main.py:12590  hermes_cli/subcommands/mcp.py:52   hermes_bootstrap.py:55
```

**第一条结论(结构性,值得记)**:**H-18 的残余绝大多数不在 R8B 范围内。**
那 11 份底稿写的是**配置面**,锚点自然压倒性地落在 `config*.py` / `env_loader.py` /
`status.py` 等 R8A 文件上;R8B 文件只是被**顺带引用**(多数是"某配置键的消费者是 CLI"这类
关系性提及,不是对 CLI 代码本身的缺陷主张)。**逐条看下来,9 个锚点里只有 1 条是
真正针对 R8B 范围可判定的缺陷主张。**

### 6.1 唯一一条可判定的:D4,已复核确认

`notes/r8a-raw-defaults-b.md` 的 **D4** 主张:存在**被代码读取却不在 `DEFAULT_CONFIG` 里**
的键,点名 `model_catalog.excluded_providers`(两处读)与 `gateway.proxy_url`,
后果是"`hermes config check` 不提示、dashboard 无字段"。

**主线复核:属实。** AST 展开 `DEFAULT_CONFIG` 求交:

```
model_catalog.excluded_providers       in DEFAULT_CONFIG: False
gateway.proxy_url                      in DEFAULT_CONFIG: False
model_catalog                          in DEFAULT_CONFIG: True
gateway                                in DEFAULT_CONFIG: True
```

读取点确实存在,且其中一处正在 R8B 范围内:

`hermes_cli/main.py:3300 @ 863e313`

```python
    # Honor ``model_catalog.excluded_providers`` so the CLI ``hermes model``
```

`hermes_cli/main.py:3307 @ 863e313`

```python
        for p in (config.get("model_catalog", {}) or {}).get("excluded_providers") or []
```

**而本轮能补上 R8A 没说的那一半:为什么它不报警。**
`model_catalog` 正在**开放字典白名单**里:

`hermes_cli/config.py:4662 @ 863e313`

```python
    "model_catalog",
```

该常量(`_OPEN_DICT_TOP_LEVEL_KEYS`,`hermes_cli/config.py:4654 @ 863e313`)的语义是
"这些顶层键之下接受任意用户自定义子键,schema 不深查"。
于是 `model_catalog.excluded_providers` **既不在 schema 里、也永远不会被校验器质疑**。

**这与 §1(H-1)里 `personalities` 那条是同一个机制**:
`_OPEN_DICT_TOP_LEVEL_KEYS` 让一整片子树免除校验,
**代价是这片子树里"真被读的键"与"打错的键"从校验器看完全一样**。
`personalities` 那条是用户写错层级不报警,这条是仓库自己的键不进 schema 也不报警——
**同一个豁免,一次坑用户,一次坑维护者。**

**定案:D4 属实,归 ◇(文档/schema 缺口)而非 ■**,与 R8A ◇-1 同族,
清单已在 `data/r8a-config-keys.tsv`,**逐条判断"该不该文档化"仍属 H-6(R11 复盘)**,
本轮不重复认领。

### 6.2 其余 8 个锚点:逐条判定为"非 R8B 缺陷主张"

逐条读过后归类:`cli.py:53` / `cli.py:4546` / `cli.py:10333` / `subcommands/mcp.py:52`
是**关系性引用**("这个配置键的消费者是 CLI 的某一行"),不含对 CLI 代码的缺陷主张;
`cli.py:4449` 与 `hermes_bootstrap.py:55` 是**引用被论证对象的上下文**;
`main.py:11159` / `:11601` / `:12590` 出现在配对流程的调用链叙述里,
其缺陷主张的落点是 `pairing.py` / `authz_mixin.py`(R8A / R8C 面),不是 `main.py` 本身。

### 6.3 如实交代边界

**本轮只复核了"锚点落在 R8B 文件集"的那 9 条,没有复核 H-18 的全部约 50 条。**
这是任务书划的范围(落入 R8B 范围者),但必须写清楚:
**H-18 的主体(配置面残余)仍然未复核,继续挂在 R11 复盘名下**,
锚点与行号沿用 R8A 报告 §10 与 `notes/r8a-90` §5 的原始记录,本轮未做任何删改。

**一条方法学观察**:H-18 这类"我知道我没做完"的移交,**最大的价值不是清单本身,
而是它让下一轮能用一次机械过滤(定位清单区 → 抽锚点 → 按文件集过滤)就判定
"这块欠账与我这轮有没有关系"**——本轮做这件事的成本是几分钟,
而如果 R8A 当初只写"还有一些没查",这几分钟会变成"要么全读一遍、要么假装不存在"。
**移交项带锚点的制度,在这一轮第一次收到了利息。**

---

## 7. 本轮新开的移交

| 编号 | 建议轮次 | 锚点 | 一句话现象 |
|---|---|---|---|
| H-R8B-a | R11 复盘 | `hermes_cli/config_defaults.py:2129`(顶层死键 `personalities`)+ `hermes_cli/config.py:4660` | 顶层 `personalities` 无任何读取点,而其注释("add your own entries here")把用户往错的层级引;`_OPEN_DICT_TOP_LEVEL_KEYS` 又为这个错层级免除了校验告警。该不该删属配置面收尾判断 |
| H-R8B-b | R11 复盘 | `hermes_cli/status.py` R8A 定位的 8 处无保护调用点 | §3 已给"该不该罩"的判据,**逐处落实未做** |
| H-R8B-c | R8C | 平台就绪判定的 8 份实现(表见 R8A `notes/r8a-90` §3.6) | 逐份对齐的清点未做,落点与 web 面重叠更大 |
