# r8b-90 · R8A 移交项定案

> 溯源约定:`路径:行号 @ 863e313` + 代码原文块。实跑环境见 `notes/r8b-02`。
> 本轮认领 R8A 移交里标注 **R8B** 的 **7** 条:H-1 / H-2 / H-7 / H-13 / H-14 / H-16 / H-17
> (H-1 / H-2 已在 `notes/r8b-02` 单独结清,此处只记结论)。
> *(R8-fix 修正,review-1 建议-23 / M-27:原写"6 条"却列了 7 个编号,下方结论表也是 7 行;
> 按 R8A 移交表,标注含 R8B 的确实是这 7 条。这落在开篇的"本轮范围"声明上,
> 下一轮据此对账会拿到一个错的分母。)*

| 移交项 | R8A 标注轮次 | 本轮结论 | R8-fix 复核 |
|---|---|---|---|
| H-1 | R8B | **结清**,并升格出 ■-R8B-01(详见 `notes/r8b-02` §1) | 维持 |
| H-2 | R8B | **结清**,影响面穷举 = 4 子树 / 24 叶,14 个真出事(`notes/r8b-02` §2) | 维持 |
| H-7 | R8B / R8D | ~~结清,负结论~~ → **重开:负结论不成立**(见 §1.0) | **改判**,派生 H-R8FIX-a |
| H-13 | R8B / R8C | **部分结清 + 明确移交 R8C**(见 §4) | 维持 |
| H-14 | R8B | ~~结清,给出判据~~ → **部分结案 + 派生移交**(见 §3) | **改述**,派生 H-R8B-b |
| H-16 | R8B | **结清,负结论:是有意的,而且是本仓库做对的样本**(见 §2) | 维持 |
| H-17 | R8B / R8C | **确认存在**;原"后果比子代理报的窄"的收窄**部分撤销**(见 §5) | **改判** |

---

## 1. H-7:**重开**——第三个"读原始配置后落盘"的调用方确实存在(原负结论作废)

> ### ⚠ R8-fix 重开(review-1 附录 A-1 / M-19)
>
> **本节原来的结论是"没有被截断。H-7 关闭。"——这个负结论不成立,现予撤销。**
> 存在这样的第三个调用方,它不是迁移流水线,而是 `hermes_cli/auth.py` 的
> `_update_config_for_provider`。下面的 §1.0 是重开后的定案,原 §1 正文
> (迁移流水线那条线)**全部保留且全部成立**——它只是**没有穷举完调用点**。
>
> **为什么这条最重、且必须重开**:正结论错了会被下一个读者撞见;**负结论错了会关闭调查**。
> 本卷写下"H-7 关闭",按 CLAUDE.md 的移交制度,后续轮次不会再回来看这里。
> 而这条负结论的成立与否**完全取决于"全仓调用点有没有数全"**——那是一次 grep 的完备性,
> 没有任何机制校验。**本轮唯一真正的方法论教训在这里,不在结论本身。**

### 1.0 定案 ■-R8B-12:坏一个缩进,`approvals.deny` 静默消失

> **改号说明(R8C 开轮更正)**:本条 R8-fix 新立时编为 **■-R8B-08**,与
> `reports/round-8b-cli-trunk-and-interaction.md:181` **既有的** ■-R8B-08
> (「mixin 与 `cli.py` 之间 35 个方法名的隐式跨文件接口」)**撞号**——
> 两条不同的缺陷共用一个编号。**现把本条改为 ■-R8B-12**,R8B 报告里那条
> 保持 ■-R8B-08 不动(它是先占号的一方,且已被 R8B 报告正文多处引用)。
> **依据**:R8B 系列已用编号为 ■-R8B-01 至 ■-R8B-10,**■-R8B-11 与 ■-R8B-12 均未被占用**;
> 取 12 而非最小可用的 11,是 R8C 开轮任务书的指定,**11 因此成为一个永久空号**——
> 写在这里是为了让后来者查到 11 缺失时知道那不是丢了一条定案。
> R8-fix 报告 `reports/round-8-fix-review-1.md:294`(M-19 行)仍写作 ■-R8B-08:
> 按 CLAUDE.md「`reports/` 正文不静默改写」,那处**留在原样**,更正记在该报告的勘误节。

**失效链**(四步,每步都在基线取过证):

**第一步**,`_update_config_for_provider` 调那道守卫,然后读原始配置:

`hermes_cli/auth.py:7270 @ 863e313`

```python
def _update_config_for_provider(
```

`hermes_cli/auth.py:7293 @ 863e313`

```python
    require_readable_config_before_write(config_path)
```

`hermes_cli/auth.py:7295 @ 863e313`

```python
    config = read_raw_config()
```

**第二步**,那道守卫只查**可读**,不查**可解析**——它做的全部事情就是 `stat()` 加读一个字节:

`hermes_cli/config.py:3066 @ 863e313`

```python
    """Refuse to replace an existing config.yaml that cannot be read."""
```

`hermes_cli/config.py:3081 @ 863e313`

```python
            f.read(1)
```

**第三步**,`read_raw_config()` 在**解析失败**时返回空字典:

`hermes_cli/config.py:2962 @ 863e313`

```python
            _warn_config_parse_failure(config_path, e)
```

`hermes_cli/config.py:2963 @ 863e313`

```python
            return {}
```

**第四步**,从 `:7295` 到 `:7329` 之间**没有任何解析检查、也没有空判**,终点是整文件替换:

`hermes_cli/auth.py:7327 @ 863e313`

```python
    config["model"] = model_cfg
```

`hermes_cli/auth.py:7329 @ 863e313`

```python
    atomic_yaml_write(config_path, config, sort_keys=False)
```

**后果**:用户把 `config.yaml` 改坏(哪怕只是一个缩进),再跑一次会走到这条路的命令
(`hermes login` 一族),落盘文件就**只剩 `model:` 一段**,其余配置——**包括 `approvals.deny`**
——静默消失。用户失去的是**安全配置**,而失去它的动作是"登录"。

### 1.1 全部调用点复核:五个裸写点,四个各自把洞堵上了,只有一个没有

R8A 移交时问的是"是否存在第三个直接 `read_raw_config()` 后落盘的调用方"。
把问题扩成"**全仓有哪些绕过 `atomic_config_write` 直接对 config 路径落盘的点,各自怎么处理解析失败**",
答案更硬:

```verify
$ grep -rn "atomic_yaml_write(config_path\|atomic_yaml_write(get_config_path" --include=*.py . | grep -v "^./tests/"
./hermes_cli/auth.py:7329
./hermes_cli/auth.py:7397
./hermes_cli/config.py:3112          # ← 这是 atomic_config_write 自己的函数体,不算绕行
./hermes_cli/config.py:4995
./hermes_cli/config.py:5123
./hermes_cli/credential_lifecycle.py:174
```

逐个读过之后:

| 写入点 | 函数 | 怎么读的 | 解析失败时 | 判定 |
|---|---|---|---|---|
| `config.py:4995` | `set_config_value` | 内联 `fast_safe_load` + 自己的 try/except | 打印 YAML 错误后 `sys.exit(1)` | ✅ fail-closed |
| `config.py:5123` | `unset_config_value` | 同上 | 同上 | ✅ fail-closed |
| `auth.py:7397` | `_reset_config_provider` | `read_raw_config()` | `if not config: return config_path`(`:7389`) | ✅ 有空判 |
| `credential_lifecycle.py:174` | 凭据清理 | 内联 `fast_safe_load` + try/except | `return []` | ✅ fail-closed |
| **`auth.py:7329`** | **`_update_config_for_provider`** | **`read_raw_config()`** | **无任何检查** | ❌ **整文件截断** |

**这张表才是这条定案的真正价值。** 仓库里有**四种**把这个洞堵上的写法,
其中一种(`auth.py:7397` 的 `if not config: return`)**就在同一个文件、隔 68 行**。
所以这不是"团队不知道要防",而是**同一语义的五份实现里有一份没跟上**——
R8A / R8B 反复讲的那个形状,这次落在了**安全不变式**上。

### 1.2 并案:这属于 R8A ▲-10 的绕行家族,而 ▲-10 的"目前无害"结论要收回一半

R8A 的 ▲-10(`notes/r8a-90` §▲-10)已经指出:`atomic_config_write` 的 docstring 自称
"The single chokepoint every config-update path should use instead of calling
`utils.atomic_yaml_write` directly",而 `save_config` 绕过了它。
**`auth.py:7329` 是同一家族的第三个成员**,应并案记录。

但 ▲-10 当时的定性是"**当前两条路等价,所以这不是一个现在会出事的缺陷**;它的危害在时间维度上"。
**这半句现在要收回**:绕行点不止两个,而第三个**并不等价**——它少了空判,现在就会出事。
▲-10 那条判据("'唯一收口'这类制度性声明,必须由一条测试或一次 grep 断言来兑现")因此从
"预防性建议"升为"**已经兑现了代价**的判据"。

**还有一层比 ▲-10 更深的**:即便老老实实走 `atomic_config_write` 这个"唯一收口",
它跑的也只是 `require_readable_config_before_write`——**同样只查可读、不查可解析**。
它的 docstring 也只声称守 "an unreadable-but-present file",从没声称守坏 YAML:

`hermes_cli/config.py:3099 @ 863e313`

```python
    Root cause this guards: ``read_raw_config()`` returns ``{}`` for BOTH an
```

所以正确的结论不是"该走收口而没走",而是:**这个收口本身就不覆盖解析失败那一支**,
四个安全的写入点是各自**在收口之外**补的检查。**"把所有人赶进一个收口"这个方案,
在收口能力不足时反而会制造虚假的安全感**——这是本条相对 ▲-10 的增量。

### 1.3 与 r8a 那条安全叙事的正面冲突

`chapters/r8a-configuration-surface.md` 用整节讲"解析失败退回上一次好的,而不是退回默认值",
理由原文是"配置里有 `approvals.deny`……退回默认值等于**用户存了个错别字,防线就自己拆了**"。
**那一节讲的是 `load_config`;而这条路走的是 `read_raw_config`,它返回 `{}`。**
同一个安全不变式,在另一条读取路径上根本不成立。r8a 那节的机制描述没错,
错的是**把它当成了全局不变式**——它只是 `load_config` 这一条路径上的不变式。

### 1.4 移交

**H-7 重开,并派生 H-R8FIX-a(见 §7)**:本轮只定案 `auth.py:7329` 一处并复核了五个裸写点;
**没有**做的是"给 `require_readable_config_before_write` 补解析检查是否会破坏
'全新安装 / 空文件'语义"这项设计判断,也没有跑运行时复现(本卡不改被测仓库、不建 venv)。

---

## 1.9 原 §1 正文(迁移流水线那条线,结论仍成立,仅作废其"H-7 关闭"的推论)

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

**迁移流水线这条路上没有被截断——这一点仍然成立。**
*(R8-fix:原文此处写的是"H-7 关闭"。**该推论作废**:没被截断的是**迁移流水线**,
而 H-7 问的是"有没有第三个调用方"。答案是有,见 §1.0。**只证伪了一个候选,
不等于穷举了候选集**——这正是负结论最容易犯的错。)*

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

**关于"缓存被空 dict 覆盖":原判整体收窄,现予部分撤销。**

> ### ⚠ R8-fix 修正(review-1 附录 A-2 / M-20)
>
> 本节原来写的是:"`_APPLIED_HOMES` 是 `set`,`:251` 是 `.clear()` 而非赋值,
> **全程没有'用空 dict 覆盖'的写法**"。**这个全称否定与基线矛盾,收窄失去了它声明的依据。**
>
> 原判只核了 `_APPLIED_HOMES` **一个容器**,而 R8A 说的是这条路径写的**那批全局字典**。
> 无锁那条路径上就有一次**无守卫的整体赋值**:
>
> `hermes_cli/env_loader.py:664 @ 863e313`
>
> ```python
>         values: dict[str, str] = {}
> ```
>
> `hermes_cli/env_loader.py:669 @ 863e313`
>
> ```python
>         _SECRET_SOURCE_VALUES_BY_HOME[home_key] = values
> ```
>
> `values` 只收 `name in os.environ` 的项,**完全可以是空 dict**
> (provenance 有项、但值都不在环境里)。而**加锁的孪生写法恰恰有守卫**:
>
> `hermes_cli/env_loader.py:236 @ 863e313`
>
> ```python
>     if values:
> ```
>
> **这道 `if values:` 的有无,正是本节自己确认的那个"锁不对称"的另一面**——
> 不只是锁,连空值守卫也只加在了两条路里的一条上。
>
> **为什么这条要算错而不是算不精确**:收窄一条移交项等于**缩小后续轮次的排查面**,
> 而这里收窄的理由是一个**可被一行代码推翻**的全称否定,被收掉的恰好是
> "无锁路径会写空字典"——**H-17 原本要查的就是这件事**。
> 教训与 §1 的负结论同源:**"全仓没有 X" 这类断言的成本,等于一次 grep 的完备性;
> 写下它之前必须把搜索面写出来,否则它只是"我没看见"的另一种说法。**

**收窄后仍然成立的部分**:`_APPLIED_HOMES` 这**一个**容器确实是 `set`、`:251` 确实是
`.clear()` 而非赋值,这一处不涉及空 dict 覆盖;且 CPython 下 `set.add` / `in` / `dict.clear`
都是 GIL 原子操作,**不会撕裂出损坏的容器**。
**被撤销的是把这一处的结论推广成全称判断。**

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

**定案 ■-R8B-02(中置信,R8-fix 修订后)**:锁不对称属实,成立的后果有**三**条——
**(a) 重复拉取**、**(b) 非原子重置**、**(c) 无锁路径 `:669` 对
`_SECRET_SOURCE_VALUES_BY_HOME[home_key]` 的无守卫整体赋值可写入空 dict,
而加锁孪生 `:236` 有 `if values:` 守卫**。
不成立的只有"容器被撕裂损坏"这一种读法。**未在运行时复现**——需要一个能让两个线程
同时首次触达同一 home 的真实场景(R8A 猜的网关热重载 + 首轮路由是合理候选,本轮没有构造出来)。
**按 R8A 立的规矩,报"代码确证、运行时未复现",不写成已复现。**
**(c) 使 H-17 的原判在此成立,故本条对 R8C 的移交范围恢复到收窄前。**

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
| H-R8B-c | R8C | 平台就绪判定("某平台是否配好了")的 8 份实现 —— `gateway/config.py`、`cron/scheduler.py`、`hermes_cli/gateway.py`、`hermes_cli/setup.py`、`hermes_cli/web_server.py`、`hermes_cli/dump.py`、`hermes_cli/tools_config.py`、`hermes_cli/status.py`;运行时真值那一份在 `cli.py:9789`(仓库根 `cli.py`)。原表见 R8A `notes/r8a-90` §3.6 | 逐份对齐的清点未做,落点与 web 面重叠更大 |
| **H-R8FIX-a** | **R8C / R8D** | `hermes_cli/config.py:3065`(`require_readable_config_before_write` 只 `stat()` + `read(1)`)+ `hermes_cli/auth.py:7329` | H-7 重开后剩下的设计判断:**给该守卫补一道解析检查会不会破坏"全新安装 / 空文件"语义**?五个裸写点里四个各自在收口之外补了检查(见 §1.1),说明"补在收口里"可能才是对的落点,但没有验证过。**本卡未做运行时复现**(不改被测仓库、未建 venv) |

> **R8-fix 修正(review-1 建议-22 / M-26)**:H-R8B-c 的"锚点"列原来**只有一句描述加一个
> 指向另一份文档表格的指针,没有任何文件路径**——正是 CLAUDE.md 明令禁止的形态。
> 更麻烦的是被指向的 `notes/r8a-90` §3.6 那 8 个位置**全是裸文件名、无行号**,
> 而歧义比评审位报的还大——本卡实测四个名字在基线里都有多个候选:
> `gateway.py` 2 个、`dump.py` 2 个、`status.py` 3 个、`setup.py` **4 个**
> (评审位说 `setup.py` 两处、`dump.py` 仓库根不存在,方向对,数少了)。
> **所以 R8C 拿到这条时仍需重新定位,移交项的目的落空。**
> 上面已把 8 个位置全部展开为可解析路径,判定依据是"哪一份真的在读平台 env 表":
>
> ```verify
> $ for f in hermes_cli/gateway.py hermes_cli/subcommands/gateway.py setup.py hermes_cli/setup.py \
>            hermes_cli/dump.py hermes_cli/subcommands/dump.py hermes_cli/status.py gateway/status.py ; do
>     printf "%s  %s\n" "$(grep -c TELEGRAM_BOT_TOKEN $f)" "$f" ; done
> 1  hermes_cli/gateway.py          0  hermes_cli/subcommands/gateway.py
> 0  setup.py                       5  hermes_cli/setup.py
> 1  hermes_cli/dump.py             0  hermes_cli/subcommands/dump.py
> 1  hermes_cli/status.py           0  gateway/status.py
> ```
> 同表的 H-R8B-a 是达标写法(给了 `config_defaults.py:2129` + `config.py:4660`),
> **作者知道怎么写,只是这一条没写**——所以这是执行问题,不是标准不清。
