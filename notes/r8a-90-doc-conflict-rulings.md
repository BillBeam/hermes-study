# r8a-90 · 定案卷:文档-代码冲突、文档缺口、代码缺陷

记号沿用前几轮:**▲** = 地图与代码冲突(以代码为准);**◇** = 文档缺口;
**■** = 代码内部缺陷(本项目只记录不修)。溯源约定同 `notes/r8a-01`。

三笔 R7C 移交项的定案在 `notes/r8a-01` §3,本卷不重复,只在 §4 列结论。

---

## ▲ 组:地图与代码冲突

### ▲-1 代码引用了一份不存在的设计文档

整个配置系统里最反直觉的一条优先级规则——managed 层排在 `${VAR}` 展开**之后**,
使管理员钉死的字面量压得住用户的环境变量引用——代码给它标的出处是:

`hermes_cli/config.py:3394-3395 @ 863e313`

```python
        # This deliberately inverts the usual env-over-config precedence for the
        # keys the managed layer pins — see docs/design/managed-scope.md §4.1.
```

**`docs/design/managed-scope.md` 不存在。** `docs/design/` 目录下只有一个文件
(`profile-builder.md`)。真正讲这件事的是 `website/docs/user-guide/managed-scope.md`,
且它**没有 §4.1 这种编号**(全文用标题分节)。

**但内容是对的**——必须说清楚,否则就是把"指针失效"夸大成"没文档"。
那份文档的 "Precedence" 一节把这条反转讲得很准确:

`website/docs/user-guide/managed-scope.md:87-91 @ 863e313`

```
For the keys it pins, managed scope deliberately wins over the shell environment
too — otherwise it would not be "managed." This is the one place that inverts the
usual "an environment variable overrides config.yaml" rule, and it applies only
to the specific keys the managed layer specifies.
```

**定案**:▲ 成立,但性质是**指针失效**(路径腐烂,R7B 定案过的同型),不是内容缺失。
代价:读代码的人按图索骥找不到,大概率就当这条注释是唯一解释,
从而不知道还有一整节讲了它的适用边界("只对 managed 层点名的键成立")。

### ▲-2 文档把 `bedrock.discovery` 讲成可调,但没有任何代码读它

`website/docs/guides/aws-bedrock.md:81-89 @ 863e313`

```
Hermes auto-discovers available models via the Bedrock control plane. You can customize discovery:
```

它给出的三个键(`enabled` / `provider_filter` / `refresh_interval`)在
`DEFAULT_CONFIG` 里确实都有定义:

`hermes_cli/config_defaults.py:789-793 @ 863e313`

```python
        "discovery": {
            "enabled": True,           # Auto-discover models via ListFoundationModels
            "provider_filter": [],     # Only show models from these providers (e.g. ["anthropic", "amazon"])
            "refresh_interval": 3600,  # Cache discovery results for this many seconds
        },
```

**三个键,零读取点。** 真正的实现用的是模块级常量:

`agent/bedrock_adapter.py:1190 @ 863e313`

```python
_DISCOVERY_CACHE_TTL_SECONDS = 3600
```

`agent/bedrock_adapter.py:1221 @ 863e313`

```python
    if cached and (time.time() - cached["timestamp"]) < _DISCOVERY_CACHE_TTL_SECONDS:
```

`provider_filter` 则是个**从没有人传的函数参数**:`discover_bedrock_models` 全仓三个调用点
(`agent/bedrock_adapter.py:399`、`hermes_cli/model_setup_flows.py:2393`、
`hermes_cli/models.py:5241`)**全部只传 region**。

**这一条的毒性在于默认值撞上了硬编码值:** 常量 3600 与文档里写的
`refresh_interval: 3600  # Cache for 1 hour` **相等**,所以用户按文档配一遍、
观察一小时的缓存行为,会得到"配置生效了"的结论。**只有改成别的值才会发现它不生效,
而那时用户会怀疑缓存本身,不会怀疑这个键根本没接线。**

对照组同样重要:同一个 `bedrock:` 块下的 `region` 与 `guardrail.*` 是**接了线的**
(`hermes_cli/runtime_provider.py:2135`、`:2138`、`agent/agent_init.py:1132`)。
**一个 section 里三个子块两个能用一个不能用**,肉眼完全看不出来。

**定案**:▲ 成立(文档描述了不存在的能力),同时记 ■-2。

### ▲-3 文档的优先级模型与代码不符:`.env` 不是"低于 config.yaml 的一层"

`website/docs/user-guide/configuration.md:55-60 @ 863e313`

```
Settings are resolved in this order (highest priority first):
```

文档给的是四级序:CLI 参数 > `config.yaml` > `.env` > 内置默认值,
并在下面的 "Rule of Thumb" 里重申"两边都设了,非密钥设置以 `config.yaml` 为准"。

**代码里不存在这样一条统一的四级链。** `load_config()` 的合并链是
**默认值 → config.yaml → 归一化 → `${VAR}` 展开 → managed**
(`hermes_cli/config.py:3333` 起,详见 `notes/r8a-01` §2.2),
**环境变量根本不是其中一层**。它只以两种方式参与:作为 `${VAR}` 的取值来源,
以及被各消费点**各自直接 `os.getenv`**。

而在第二种方式里,**环境变量常常先被检查、赢过 config.yaml**,与文档的排序正好相反:

`tools/browser_camofox.py:242-245 @ 863e313`

```python
    env_value = _env_flag("CAMOFOX_REWRITE_LOOPBACK_URLS")
    if env_value is not None:
        return env_value
    return bool(camofox_cfg.get("rewrite_loopback_urls"))
```

环境变量有值就直接返回,`config.yaml` 里的 `browser.camofox.rewrite_loopback_urls`
**根本没机会参与**。这与"config.yaml 胜过 .env"直接矛盾。

有意思的是文档自己在别处泄了底——讲 provider 超时那段特意声明
"the configured value wins over the legacy `HERMES_API_TIMEOUT` env var"
(`website/docs/user-guide/configuration.md:87`)。**如果全局规则真的是"config 胜 env",
这句话就不必写。** 需要逐处声明,恰恰说明没有全局规则。

**"每个消费点自己决定"还不够准确——连读凭据的公共函数本身都有两个方向相反的版本。**
(此条由 `notes/r8a-raw-config-c` §1.3 发现,主线已回源逐行复核确认。)

链 A `get_env_value`:**先 `os.environ`,`.env` 兜底**——

`hermes_cli/config.py:4138-4143 @ 863e313`

```python
    if val is not None:
        return val

    # Then check .env file
    env_vars = load_env()
    return env_vars.get(key)
```

链 B `get_env_value_prefer_dotenv`:**先 `.env`,`os.environ` 兜底**——

`hermes_cli/config.py:4146 @ 863e313`

```python
def get_env_value_prefer_dotenv(key: str) -> Optional[str]:
```

链 B 存在的理由写在自己的 docstring 里,而且是个真实事故:

`hermes_cli/config.py:4149-4153 @ 863e313`

```python
    Used for Hermes-managed credentials where a deliberate edit to ``.env``
    must take precedence over a stale value inherited from the parent shell
    (Codex CLI, test scripts, login profile exports). Without this, rotating
    a key in ``.env`` mid-session leaves callers serving the stale shell
    value and produces persistent 401s.
```

**因果经过**:用户的登录脚本(或上一层 CLI)往环境里导出过一个旧密钥;用户密钥过期后
去改 `~/.hermes/.env`,改对了;但读取链是"环境优先",于是仍然拿旧值去打 API,
**持续 401**,而用户看着自己刚改好的 `.env` 完全不明白。修法是给这类
"Hermes 自己管理的凭据"换一条相反的链。

**两条链还有一个更细的分歧**:链 A 用 `val is not None` 判命中,
所以 `os.environ` 里一个**空串**也算命中并直接返回空串,不会再去看 `.env`;
链 B 用 `if val:` 判真值,空串会继续往下走。**对一个刚被清空的槽位,两条链给出不同答案。**

**定案**:▲ 成立,且比初判更强。真实模型是:**config.yaml 有一条统一的合并链;
环境变量这一侧没有统一规则——不但每个消费点自己决定谁先谁后,
连公共读取函数都提供了两个方向相反的版本供调用方挑。**
文档把这一整摊简化成"低于 config.yaml 的一层",这个简化在最需要它的时候
(排查"我明明配了为什么不生效")恰好是错的。

### ▲-4 QQBot 环境变量:文档只讲新名,面板只读旧名

取证与因果经过见 `notes/r8a-01` §3.1(R7C 移交项①)。
`website/docs` 中 `QQBOT_HOME_CHANNEL` 出现 3 次、`QQ_HOME_CHANNEL` **0 次**;
`hermes_cli/status.py:483` 的表里写死旧名。**定案:▲ 成立,同时记 ■-1。**

**收尾补一条,它改变了这条定案的性质判断。** 主线实测两张 env 注册表对这次改名的处置:

`hermes_cli/config.py:289 @ 863e313`

```python
    "QQ_HOME_CHANNEL", "QQ_HOME_CHANNEL_NAME",  # legacy aliases (pre-rename, still read for back-compat)
```

| 变量 | `_EXTRA_ENV_KEYS`(认识) | `OPTIONAL_ENV_VARS`(推荐) | 文档 |
|---|---|---|---|
| `QQBOT_HOME_CHANNEL` | ✅ | ✅ | ✅ 3 处 |
| `QQ_HOME_CHANNEL` | ✅ | ❌ | ❌ 0 处 |

**配置系统这一侧把改名做得完全正确**:旧名仍被认识(老配置不坏)、不被推荐、不进文档。
另外实测:108 个 `_EXTRA_ENV_KEYS` 里有 **8 个零文档**,而这 8 个里就有
`QQ_HOME_CHANNEL` 与 `QQ_HOME_CHANNEL_NAME` —— **它们零文档是对的,不是缺口**
(废弃别名本就不该出现在文档里)。

**所以 ▲-4 的性质不是"文档没跟上",而是"`status.py` 没跟上"**,
而 `status.py` 恰恰是**直接读环境变量、完全绕过配置系统**的那一段。
**这条定案因此从"某处笔误"升格为一条结构性结论:配置系统的纪律,管不到不走配置系统的代码。**

---

## ◇ 组:文档缺口

### ◇-1 856 个配置键里 **105 个全站零提及**(这是本条唯一站得住的数)

用 `scripts/config_table.py` 从 `DEFAULT_CONFIG` 字面量 AST 抽取全部 **856 个键**
(719 叶子 + 137 分支),对六类文档面(`.env.example` / `AGENTS.md` / `README*` /
`CONTRIBUTING*` / `website/docs/**` / `docs/**`)逐键检索:**105 个键零命中**。

**"覆盖率 87.7%"这个说法本轮被自己推翻了,过程值得记下来。** 我先想给一个严格下界:
只统计**点分全路径**(如 `display.show_cost`)在文档里逐字出现的键。实测结果是
**0 个,0.0%**。原因不是文档差,是**文档根本不用这种写法**——它写 YAML 块:

```yaml
display:
  show_cost: false        # Show estimated $ cost in the CLI status bar
```

所以"点分路径匹配"量的是**排版习惯**,不是覆盖情况,这个下界没有意义。
另一头,退回**叶子名**匹配得到 87.7%,但叶子名如 `enabled` / `timeout` / `mode`
在文档里到处都是,会把大量没被文档化的键算成"已覆盖"
(表里 `ambiguous=AMBIG` 一列标出了 **121 个**这类键)。

**结论:0% 和 87.7% 是两个都不可用的边界,真实覆盖率落在中间且无法用检索定量。**
本条唯一可靠的数是那 **105 个键——它们的叶子名在全部文档面上一次都没出现过**,
这是一个**保守的、确定成立的**缺口下界。后续轮次(H-6)应据此清单逐条判断,
而不是继续引用任何百分比。

### ◇-1b 补充:`DEFAULT_CONFIG` 并不是全部合法配置键

上面那 856 个键还有一个**范围上的**限定,必须写清楚,否则这张表会被误当成全集。
代码里另有一个"已知根键"集合,是**两个集合的并集**:

`hermes_cli/config.py:1881 @ 863e313`

```python
_KNOWN_ROOT_KEYS = frozenset(DEFAULT_CONFIG.keys()) | _EXTRA_KNOWN_ROOT_KEYS
```

**主线先把它误读成了"根键校验白名单",复核后更正——它不是。**
`_KNOWN_ROOT_KEYS` 全仓**只有一个使用点**,而且那里不是"拒绝未知根键",
只是给四个"看起来放错地方的 provider 字段"做去重判断:

`hermes_cli/config.py:2045 @ 863e313`

```python
        if key not in _KNOWN_ROOT_KEYS and key in _CUSTOM_PROVIDER_LIKE_FIELDS:
```

**配置的根层是故意开放世界的**,理由写得非常清楚,而且指向一个本轮才发现的机制:

`hermes_cli/config.py:2037-2041 @ 863e313`

```python
    # Only provider-like fields (base_url, api_key, …) are flagged. Arbitrary
    # unknown top-level keys are deliberately NOT warned about: top-level
    # scalars are bridged into os.environ (gateway/run.py, hermes send) so
    # users can feed skills and external apps env-style keys from config.yaml
    # — a closed-world allowlist can never enumerate those.
```

### ◇-1d 又一处"表外键":`terminal.*` 的配置→环境桥与默认值不同构

(此条由 `notes/r8a-raw-defaults-a` §3.3 发现,主线已用 AST + 运行时集合运算复核确认。)

`terminal.*` 的消费方 `tools/terminal_tool.py` **只读环境变量**(同一份工具要在
TUI / dashboard PTY / gateway worker 等子进程里跑),所以 `config.py` 提供一张显式映射表
把配置键投影成 env:

`hermes_cli/config.py:3183-3184 @ 863e313`

```python
TERMINAL_CONFIG_ENV_MAP = {
    "backend": "TERMINAL_ENV",
```

**这张表有 30 个键,与 `DEFAULT_CONFIG["terminal"]` 双向不同构**(主线实测):

- **在桥表里、不在默认值里的 8 个**:`docker_orphan_reaper` / `docker_persist_across_processes` /
  `lifetime_seconds` / `sandbox_dir` / `ssh_host` / `ssh_key` / `ssh_port` / `ssh_user`
  —— 又一批**合法但表外**的配置键,且这次是**嵌套层**的(不受 ◇-1b 那 23 个根键覆盖);
- **在默认值里、不在桥表里的 6 个** —— 这些键设了也不会传到 `terminal_tool`。

**这使"配置项全表"的边界又收窄一层**:856 个键是 `DEFAULT_CONFIG` 的全集,
但**不是"用户能在 config.yaml 里合法写下的键"的全集**——后者还包括
23 个额外根键的整棵子树、以及像这 8 个一样散落在各投影表里的嵌套键。
**已在 `scripts/config_table.py` 的开头说明里声明此边界。**

### ◇-1c 第三条桥:config.yaml 的顶层标量会变成环境变量(方向与 `${VAR}` 相反)

顺着上面那条注释查到了本轮**最后一个、也是最反直觉的机制**:

`gateway/run.py:2057-2060 @ 863e313`

```python
        # Top-level simple values (fallback only — don't override .env)
        for _key, _val in _cfg.items():
            if isinstance(_val, (str, int, float, bool)) and _key not in os.environ:
                os.environ[_key] = str(_val)
```

**`config.yaml` 里每一个顶层标量键都会被灌进 `os.environ`**(仅当环境里还没有同名变量)。
这意味着两件事:

1. **两个系统之间的桥是双向的。** `${VAR}` 是"环境 → 配置";这条是"配置 → 环境"。
   所以用户可以在 `config.yaml` 里写一个任意名字的顶层标量,给**技能脚本和外部程序**
   当环境变量用 —— 这也正是**根层不能做闭世界校验**的原因:那些键名按定义无法穷举。
2. **这条桥再一次与文档的优先级相反。** 注释里明写 `fallback only — don't override .env`,
   判据是 `_key not in os.environ`:**环境已有值就不覆盖**。
   文档说"两边都设了以 `config.yaml` 为准",这条桥恰恰相反。

**顺带一个数**:这条桥**直接读 config.yaml,不走 `load_config()`**(注释自己说的
"This bridge reads config.yaml directly (not via load_config)"),
所以它是本轮点到的**第四个**读配置文件的地方
(`load_config` / `load_cli_config` / `read_raw_config` / 这条桥),
每个各有各的合并与优先级姿态。**头条那条"两个装载器"其实说少了。**

第二个集合是手工维护的 **23 个根键**,代码注释说得很坦白:

`hermes_cli/config.py:1850-1854 @ 863e313`

```python
# DEFAULT_CONFIG is the single source of truth for documented roots; keep this
# set derived so new defaults (skills, security, browser, …) are accepted
# automatically. A few optional/legacy roots are valid on disk but intentionally
# absent from DEFAULT_CONFIG (omitted when unused / alternate schema forms).
```

**"documented roots"这个限定词是关键**:`DEFAULT_CONFIG` 是**已文档化根键**的
单一真源,不是**全部合法根键**的真源。这 23 个里包括 `mcp_servers`(MCP 服务器定义)、
`platforms`(每平台设置)、`platform_toolsets`(每平台工具集,由安装向导写)、
`image_gen` / `video_gen`、以及一批网关认的"顶层便捷写法"。

**后果**:它们**没有默认值、没有嵌套键定义**,于是
`mcp_servers` / `platforms` 之下的任何子键**都不在这 856 个里**,
本轮的配置项全表对那几棵子树**零覆盖**。
脚本已增补 `data/r8a-extra-root-keys.tsv` 把这 23 个显式列出来,
让这个洞是**可见的**,而不是被一张"看起来很全"的表盖住。

### ◇-2 对照组:环境变量侧覆盖率 100%,原因值得抄

同一套检索跑 `OPTIONAL_ENV_VARS` 的 151 条静态条目:**零缺口**。

差别不在于有人更勤快,而在于**结构**:每条环境变量的说明是**写在定义字面量里的**
(`description` / `prompt` / `url` / `password` / `category` 四到六个字段),
定义与说明是同一处、同一次编辑;而 `DEFAULT_CONFIG` 的键只有**自由文本注释**,
说明写在另一个仓库(`website/`)的另一个文件里,两处各自演化。

**可迁移的设计原则**:把"这个键是什么"做成**数据结构里的必填字段**,而不是注释。
覆盖率就不再依赖纪律,而是依赖类型。这是本轮最值得带走的一条,详见成品章 §4。

### ◇-3 两个装载器的存在本身全站零文档

`notes/r8a-01` §2.1 那条"同一份 config.yaml 被两个装载器以不同合并语义读取",
在 `website/docs/user-guide/configuration.md` 全文(2,386 行)与 `AGENTS.md` 中
**没有任何提及**。文档呈现的是单一的、统一的配置系统。

对使用者的实际后果:在 CLI/TUI 里设一个嵌套键,与在 config.yaml 里设同一个键给网关用,
**行为可能不同**,而没有任何文档提示需要区分这两件事。

---

## ■ 组:代码内部缺陷(11 条,只记录不修)

| # | 缺陷 | 锚点 | 怎么会踩到 |
|---|---|---|---|
| ■-1 | status 面板 QQBot 兼容分支**恒假**,且分支体是**空操作** | `hermes_cli/status.py:495` | 照官方文档配新名 → 机器人正常但面板不显示 home 频道 |
| ■-2 | `bedrock.discovery` 三个键**全部未接线** | `hermes_cli/config_defaults.py:789` | 改 `refresh_interval` 无任何效果;默认值撞上硬编码常量,改之前看不出来 |
| ■-3 | 两个装载器合并语义不同(深合并 vs `dict.update`) | `cli.py:599` | 在 CLI/TUI 侧设一个嵌套键,会静默清除其同级默认值 |
| ■-4 | `display.copy_shortcut` 是**全仓唯一一次出现** | `hermes_cli/config_defaults.py:1280` | 用户按注释里列的四个取值去设,永远无效 |
| ■-5 | `NOUS_BASE_URL` 在环境变量清单里,但代码读的是另外两个名字 | `hermes_cli/config_defaults.py:3132` | 安装流程会**主动向用户索要**一个没人读的变量 |
| ■-6 | 配对 CLI 捅穿 `PairingStore` 封装(三个私有成员) | `hermes_cli/pairing.py:81` | 私有方法改名 → 运维者最需要的那条诊断路径炸掉 |
| ■-11 | **一个自称"单一真源、防止各面漂移"的函数,实测在两个面上相差 780 秒** | `tools/clarify_gateway.py:388`(自述)/ `:399`(遗留键优先)/ `cli.py:523`(遗留键的 CLI 默认值 120) | 用户设 `agent.clarify_timeout: 900`(规范键):网关面得 900、CLI 面得 **120**;因 `cli.py` 默认值恒供遗留键 `clarify.timeout`,规范键在 CLI 面**永远无法生效** |
| ■-10 | **两份默认值的第一个真实受害者**:`hermes config set agent.reasoning_effort high` 被判为未知键,并给出会弄坏配置的建议 | `hermes_cli/config.py:4810`(校验)/ `cli.py:8166`(真实读取点)/ `cli.py:479`(它所在的那份默认值) | 命令正确、值也写对了,但打印"不是已知配置键";建议改用 `agent.reasoning_overrides`,而那个键的默认值是 `{}`(字典),照做后思考力度静默失效 |
| ■-9 | `_COMMENTED_SECTIONS` 是**已漂移的死副本** | `hermes_cli/config.py:3473` | 活版是 `_SECURITY_COMMENT`/`_FALLBACK_COMMENT`(:3601/:3609);两份同一句话已不同。维护者改到死版,对用户文件零效果 |
| ■-8 | **两把配对钥匙行为不一致**:CLI 在 request-id 路径上也报"平台被锁定" | `hermes_cli/pairing.py:81` vs `hermes_cli/web_server.py:12346` | 用过期 request-id 批准 + 平台恰好因别的原因锁定 → CLI 告诉运维者"等 N 分钟",而真实原因是请求过期;dashboard 同一操作正确回 404 |
| ■-7 | `OPTIONAL_ENV_VARS` 在 import 时被**原地改写** | `hermes_cli/config.py:5307` | 静态分析(含本项目第一版脚本)只看到 151/308 |

### ■-11 细节:本轮最强的一条 —— "单一真源"被第二份默认值击穿

顺着 ■-10 的名单查 `clarify.timeout` 时撞见的,**主线运行时实测**。

`tools/clarify_gateway.py` 提供一个解析澄清超时的函数,docstring 把设计意图写得斩钉截铁:

`tools/clarify_gateway.py:388-389 @ 863e313`

```python
    Single source of truth shared by every surface (messaging gateway, CLI,
    TUI/desktop) so the timeout can't drift between them.  Resolution order:
```

它的解析顺序是**遗留键优先**:

`tools/clarify_gateway.py:399-401 @ 863e313`

```python
    raw = (config.get("clarify") or {}).get("timeout")
    if raw is None:
        raw = (config.get("agent") or {}).get("clarify_timeout", 3600)
```

即先看顶层遗留键 `clarify.timeout`,没有才看规范键 `agent.clarify_timeout`。
**这本身没问题** —— 前提是"没设过遗留键"时 `raw` 为 `None`。

**问题在于 `cli.py` 的那份默认值把遗留键钉死了:**

`cli.py:522-523 @ 863e313`

```python
        "clarify": {
            "timeout": 120,  # Seconds to wait for a clarify answer before auto-proceeding
```

于是在 CLI 侧,`clarify.timeout` **永远存在**(值 120),`raw` **永远不是 None**,
规范键 `agent.clarify_timeout` **永远轮不到**。

**实测(同一份 config.yaml,只设了规范键 `agent.clarify_timeout: 900`)**:

| 调用面 | 传入的配置对象 | 得到的超时 |
|---|---|---|
| 网关(`get_clarify_timeout`,`tools/clarify_gateway.py:426`) | `load_config()` | **900** ✅ |
| CLI(`cli.py:13195`) | `CLI_CONFIG` | **120** ❌ |
| CLI 回调(`hermes_cli/callbacks.py:32`) | `CLI_CONFIG` | **120** ❌ |

三个调用点,两个传 `CLI_CONFIG`:

`hermes_cli/callbacks.py:32 @ 863e313`

```python
    timeout = resolve_clarify_timeout(CLI_CONFIG)
```

`tools/clarify_gateway.py:426 @ 863e313`

```python
        return resolve_clarify_timeout(load_config() or {})
```

**结论:一个为"防止各面漂移"而写的单一真源函数,在两个面上相差 780 秒
(900 vs 120),而且用户设的规范键在 CLI 面根本没有生效路径。**
函数本身完全正确;击穿它的是**第二份默认值**。

**对照组必须给,否则这条会被误读成"这仓库到处都坏"。**
同一形状在 `terminal` 上**被正确处理了**:

`cli.py:639-643 @ 863e313`

```python
    # Normalize config key: the new config system (hermes_cli/config.py) and all
    # documentation use "backend", the legacy cli-config.yaml uses "env_type".
    # Accept both, with "backend" taking precedence (it's the documented key).
    if "backend" in terminal_config:
        terminal_config["env_type"] = terminal_config["backend"]
```

实测用户只设 `terminal.backend: docker`,CLI 侧 `env_type` 正确得到 `docker`。
**作者知道这个坑,并在 `terminal` 上补了归一化。**

**关键差别是归一化写在哪一层**:`terminal` 那次写在 **`load_cli_config` 内部**
(即那份重复默认值自己的家里);`clarify` 的解析写在**共享 helper** 里,
而那个 helper 不知道世界上还有第二份默认值。

**这是本轮头条最有力的收尾,教训也因此更精确**:
重复默认值的危害不止于"多维护一份",它会**让别处正确的抽象失效**;
而**凡依赖"这个键没被设过"的判断,必须做在重复默认值所在的那一层**——
只有那一层知道它们存在,写在共享层的判断再正确也会被架空。
失效点距病根有三跳(第二份默认值 → 遗留键恒存在 → 优先级恒走遗留分支),
现场排查几乎不可能反推回去。

### ■-10 细节:两份默认值的第一个真实受害者(线索来自 `r8a-raw-defaults-a` D-1,主线运行时复核)

`agent.reasoning_effort` 是**真实被支持、真实被读**的键:

`cli.py:8165-8167 @ 863e313`

```python
        self.reasoning_config = _parse_reasoning_config(
            CLI_CONFIG["agent"].get("reasoning_effort", "")
        )
```

它在 `cli.py` 的内联默认值里(`cli.py:479`),**不在 `DEFAULT_CONFIG["agent"]` 里**;
而 `hermes config set` 的键名校验只认 `DEFAULT_CONFIG`,不认得就在同级里找近似名:

`hermes_cli/config.py:4810 @ 863e313`

```python
            sibling_suggestion = _suggest_closest_key(seg, set(node.keys()))
```

**主线实跑,原样抄录:**

```
✓ Set agent.reasoning_effort = high in .../config.yaml
⚠ 'agent.reasoning_effort' is not a recognized config key — it was saved anyway, but Hermes may not read it.
  Did you mean: agent.reasoning_overrides
```

**三处同时错**:值写对了、CLI 也会读(所以警告是**假的**);
建议的 `agent.reasoning_overrides` 默认值是 `{}`(**字典**),
用户照做写成字符串后思考力度**静默失效**,而正确的那行已被他删掉。

**这条把本轮头条从"结构性隐患"坐实成"已发生的用户可见故障"**,
且比 camofox 那例强得多(后者被三份重复字面量掩盖,现象为零)。
**根因同一个:两份默认值,而校验器只认其中一份。**

**受影响面不是一个键,主线已把它数出来。** 用 AST 展开 `cli.py` 的内联 `defaults`
得 **89 个键**,与 `DEFAULT_CONFIG` 求差:**28 个键只存在于 CLI 那份默认值里**
(其中 13 个是 `agent.personalities.*` 的人格文本,属数据;其余 15 个是真开关)。

抽 6 个实跑 `hermes config set`,**5 个复现了假警告**:

| 键 | 假警告 | 是否真被读 |
|---|---|---|
| `model.default` | ❌ 无 | —(走根级 model 归一化,躲过了) |
| `agent.verbose` | ✅ 有 | 未确证 |
| `agent.system_prompt` | ✅ 有 | **是**,`cli.py:4488` |
| `agent.reasoning_effort` | ✅ 有 | **是**,`cli.py:8166` |
| `clarify.timeout` | ✅ 有 | 未确证(`clarify` 整棵子树只在 CLI 默认值里) |
| `code_execution.timeout` | ✅ 有 | 未确证 |
| `terminal.lifetime_seconds` | ✅ 有 | 未确证 |

`agent.system_prompt` 的读取点:

`cli.py:4488 @ 863e313`

```python
            or CLI_CONFIG["agent"].get("system_prompt", "")
```

**已确证至少两个真实被读的键会收到假警告**(`agent.reasoning_effort`、`agent.system_prompt`);
其余 13 个开关**是否真被读、假警告是否同样有害,未逐个确证**,
连同完整名单移交 R8B(见 H-1 / H-2 —— `cli.py` 本就是 R8B 的主体)。
**本轮的结论限定为:这不是孤例,是一个至少 15 个开关的家族,其中已证 2 个真出事。**

### ■-9 细节:一份**已经漂移**的死副本(第五例"一个语义写了两次")

(线索来自 `notes/r8a-raw-config-c` F3 说"`_COMMENTED_SECTIONS` 是死代码";
主线复核**确认它是死的,并发现比"死"更值得记的一点**。)

`save_config()` 会往用户的 `config.yaml` 末尾追加几段**被注释掉的配置模板**
(本轮运行时实验里亲眼见到它写出了 Security 与 Fallback Model 两段)。
真正被写出去的是这两个常量:

`hermes_cli/config.py:3601 @ 863e313`

```python
            parts.append(_SECURITY_COMMENT)
```

`hermes_cli/config.py:3609 @ 863e313`

```python
            parts.append(_FALLBACK_COMMENT)
```

而**第三个常量 `_COMMENTED_SECTIONS` 全仓零引用**(除定义处):

`hermes_cli/config.py:3473 @ 863e313`

```python
_COMMENTED_SECTIONS = """
```

它装的是**同样这两段**的一份旧副本。**而且两份已经不一样了** —— 同一句话的活版与死版:

活版(会写进用户文件),`hermes_cli/config.py:3432-3434 @ 863e313`

```python
# Secret redaction is ON by default — strings that look like API keys,
# tokens, and passwords are masked in tool output, logs, and chat
# responses before the model or user ever sees them. Set redact_secrets
```

死版(不会),`hermes_cli/config.py:3475-3476 @ 863e313`

```python
# Secret redaction is ON by default. Set to false to pass tool output,
# logs, and chat responses through unmodified (e.g. for redactor dev).
```

**这是本轮"一个语义写了两次"的第五例,也是最有说服力的一例——因为漂移已经发生了。**
维护者要更新 provider 列表或安全说明时,`_COMMENTED_SECTIONS` 看起来完全像那个该改的地方
(名字最像"就是这些注释段"),改完却对用户文件毫无影响。
**风险不在于死代码占地方,在于它长得比活代码更像正主。**

### ■-4 细节:一个只存在于自己定义处的键

`hermes_cli/config_defaults.py:1280 @ 863e313`

```python
        "copy_shortcut": "auto",  # "auto" (platform default) | "ctrl_c" | "ctrl_shift_c" | "disabled"
```

全仓(含所有语言、含 `tests/`、含 `website/`)对 `copy_shortcut` 的命中数是 **1**,
就是上面这一行。注释煞有介事地列出四个合法取值,**没有一个被任何代码消费**。

### ■-5 细节:安装流程会索要一个死变量

`OPTIONAL_ENV_VARS["NOUS_BASE_URL"]` 带着完整的 `description` 与 `prompt` 字段,
而全仓 Python 读的是**另外两个更具体的名字**:

`hermes_cli/auth.py:8799 @ 863e313`

```python
        or os.getenv("NOUS_PORTAL_BASE_URL")
```

`hermes_cli/auth.py:8804 @ 863e313`

```python
        or os.getenv("NOUS_INFERENCE_BASE_URL")
```

`NOUS_BASE_URL` 是**拆分之前的旧名**,拆成 portal / inference 两个之后,
清单和文档里的旧名没删。

**而这恰好违反了本仓库自己写明的规则** ——(此条规则由 `notes/r8a-raw-defaults-b` §3.2 发现,
主线已实测复核。)代码维护**两张**环境变量表,分工写得极清楚:

`hermes_cli/config.py:261-263 @ 863e313`

```python
# Env var names written to .env that aren't in OPTIONAL_ENV_VARS
# (managed by setup/provider flows directly).
_EXTRA_ENV_KEYS = frozenset({
```

规则的说明在 `config_defaults.py` 末尾,拿一个废弃键当例子:

`hermes_cli/config_defaults.py:4290-4296 @ 863e313`

```python
    # HERMES_TOOL_PROGRESS_MODE is deprecated — tool progress is configured via
    # display.tool_progress in config.yaml (off|new|all|verbose|log). The
    # gateway still falls back to HERMES_TOOL_PROGRESS_MODE for backward
    # compatibility, so it lives in _EXTRA_ENV_KEYS (known to reload and
    # compatibility paths) but is intentionally NOT listed here:
    # OPTIONAL_ENV_VARS feeds user-facing surfaces (dashboard keys page, setup
    # checklists) and deprecated knobs shouldn't be offered there.
```

**即:"运行时认识的键"与"向用户推荐的键"是两张表;废弃键从后者摘除、在前者保留。**
这是一条很好的设计原则。主线实测三点:
`HERMES_TOOL_PROGRESS_MODE` 确实**在** `_EXTRA_ENV_KEYS`、**不在** `OPTIONAL_ENV_VARS`(规则被遵守);
而 `NOUS_BASE_URL` **在** `OPTIONAL_ENV_VARS`(带完整 `description` + `prompt`)、
**不在** `_EXTRA_ENV_KEYS` —— **正好反了**。
**所以 ■-5 不是一条普通的陈旧条目,而是这条已被明确写下的规则的一次违反。**

而清单不是死数据——它驱动"缺哪些变量"的盘点:

`hermes_cli/config.py:985 @ 863e313`

```python
        for var_name, info in OPTIONAL_ENV_VARS.items():
```

**于是这是一个比"死配置键"更糟的形态:系统会主动提示用户去配置一个不存在的东西。**

### ■-7 细节:"纯数据叶子模块"只对模块成立,不对它导出的字典成立

`config_defaults.py` 开篇自述纯数据(`notes/r8a-01` §2.5 已引)。
模块本身确实不 import 任何东西,但它导出的 `OPTIONAL_ENV_VARS`
**会被 `hermes_cli.config` 在 import 时原地灌满**:

`hermes_cli/config.py:5337 @ 863e313`

```python
_inject_profile_env_vars()
```

实测(同一个 dict 对象):**import 前 151 条,import `hermes_cli.config` 后 308 条。**

**而同一个模块里的 `DEFAULT_CONFIG` 没有这个问题** —— 这个对照是本条的关键:

| | AST 静态抽取 | import 后运行时 | 一致? |
|---|---|---|---|
| `DEFAULT_CONFIG` | 856 键(137 分支 / 719 叶子 / 82 根) | 856 键(137 / 719 / 82) | ✅ **逐位相等** |
| `OPTIONAL_ENV_VARS` | 151 条 | **308 条** | ❌ 翻倍 |

**同一个"纯数据叶子模块"导出的两个字典,一个是真不可变的,另一个被别人当成注册表在灌。**
所以"这个模块是纯数据"这句话对**模块**成立,对**它导出的每个对象**不成立——
必须逐个对象验证,不能从模块的自述推断。
(本项目的配置项全表因此对 `DEFAULT_CONFIG` 侧是可信全集,对环境变量侧只是 49%。)

**这条的价值不在缺陷本身,在方法论**:凡"权威清单"类数据结构,先问一句
**"它在运行时会不会被别人改"**。本项目第一版抽取脚本就栽在这里,
差点把一份只有 49% 的清单当成全表交付给 R12。

---

## 3.5 主线驳回的子代理结论(复核制度的产出,必须记)

本轮子代理产出质量很高,但主线逐条回源复核时**驳回了一条**,记在这里,
因为"驳回什么"和"确认什么"同等重要。

### 驳回 · `notes/r8a-raw-config-c` 的 F4:"坏 YAML 会被 `hermes config set` 静默截断"

**子代理的论证**:写前守卫 `require_readable_config_before_write` 只做 `f.read(1)`
(只检查**可读**,不检查**可解析**),而 `read_raw_config()` 对坏 YAML 返回 `{}`;
因此跑 `hermes config set X Y` 会拿到空字典,写出一个只剩少量键的新文件,
用户其余配置从磁盘消失。

**前半段属实**(守卫确实只读一个字节),**但结论不成立**。

**主线实测**:临时 home 放一份 13 行、含 `approvals.deny` 与多个键的 config.yaml,
末行故意写成坏 YAML(未闭合的 flow 序列),然后调 `set_config_value('display.compact','false')`。
结果:命令**拒绝执行并退出**,打印

```
✗ Cannot parse .../config.yaml: while parsing a flow sequence
  The file contains a YAML syntax error. Fix the error
  in your config file first, then retry.
  (hermes config edit will open it in your editor.)
```

**文件逐字节未改**(仍 13 行,内容一致),目录下也没有产生任何新文件。

**原因**:`set_config_value` 并不走 `read_raw_config()`,它**自己再解析一次**并在失败时
硬退出:

`hermes_cli/config.py:4883,4885-4891 @ 863e313`

```python
            with open(config_path, encoding="utf-8") as f:
```

`hermes_cli/config.py:4885-4891 @ 863e313`

```python
        except Exception as exc:
            print(
                f"✗ Cannot parse {config_path}: {exc}\n"
                f"  The file contains a YAML syntax error. Fix the error\n"
                f"  in your config file first, then retry.\n"
                f"  (hermes config edit will open it in your editor.)",
                file=sys.stderr,
            )
            sys.exit(1)
```

同样的守卫在 `unset_config_value` 里也有一份(`hermes_cli/config.py:5102`)。
即**两个用户可达的写入命令都各自挡住了坏 YAML**。

**定案:F4 驳回。** 子代理的失误在于——它读到了 `require_readable_config_before_write`
只检查可读,就推断"没有解析检查",而没有继续读**调用方紧接着的那几行**。
真正的检查不在共用守卫里,而在每个写命令自己身上。

**这条驳回本身有价值**:它说明"共用守卫弱"不等于"整条路径弱",
判定一条写路径安不安全,必须看**调用方的完整序列**,不能只看它调用的守卫函数。
残留的合理疑问是:**是否存在某个不经这两个命令、直接 `read_raw_config()` 后落盘的调用方**
——那才是 F4 描述的形态。本轮未穷举,列为移交项 H-7。

---

## 4. 三笔移交项结论汇总

| 移交项(R7C) | 结论 | 详见 |
|---|---|---|
| ① `status.py` QQBot 环境变量倒置 | ✅ **成立,并更正来源 + 追加"分支体空操作"** | `r8a-01` §3.1 / ▲-4 / ■-1 |
| ② `commands.py` 94 条注册表定义面 | ✅ **94 确认无误**,补齐 94/26/120/111/8 五数关系 | `r8a-01` §3.2 |
| ③ `pairing.py` 与 `web_server.py` 批准入口 | ✅ **结案**,并记一条封装破坏 | `r8a-01` §3.3 / ■-6 |

**移交项①的更正**:R7C 写的是"安装向导写新名"。实测新名的来源是
**网关的弃用警告**(`gateway/config.py:2441`)与**官方文档**,不是安装向导。
按本轮并入 `CLAUDE.md` 的新制度,移交项须附锚点文件与一句话现象——
R7C 这条附了锚点文件(`hermes_cli/status.py`),所以本轮没有走偏,只需更正细节;
这正是那条制度想要的效果。

---

## 5. 向后续轮移交(按新制度,逐条附锚点文件 + 一句话现象)

| # | 移交至 | 锚点文件 | 一句话现象 |
|---|---|---|---|
| H-1 | **R8B** | `cli.py:441`(`load_cli_config` 的内联 `defaults`) | **本轮已数清:89 键中 28 个不在 `DEFAULT_CONFIG`(13 个是人格文本,15 个是真开关)**,名单见 ■-10;**未做的是逐个确证这 15 个是否真被读** —— 已证 2 个真被读且收到假警告,其余待查 |
| H-2 | **R8B** | `cli.py:599`(`defaults[key].update(...)`) | 浅合并的**实际影响面**未穷举:哪些从 `CLI_CONFIG` 读的嵌套键**没有**硬编码兜底,那些才是会真出事的 |
| H-3 | **R8C** | `hermes_cli/web_server.py:12320`(`approve_pairing` 路由) | 本轮已读该路由本体并定案 ■-8(与 CLI 的锁定报告不一致);**未查的是它的鉴权层**——`/api/pairing/approve` 由哪一层保证只有已认证管理员可调,需在 R8C 全文精读时确证 |
| H-4 | **R8D** | `hermes_cli/managed_scope.py` | 本轮从 `config.py:3396` 与 `cli.py:624` 两侧读到它,但**没读本体**;managed 层的叶级合并实现与失败姿态未取证 |
| H-5 | **R9/R10** | `ui-tui/src/gatewayTypes.ts:89` 等 TS 侧读取点 | 856 个配置键中有一类**只由 TypeScript 读**;TS 侧是否有自己的默认值(即第三份默认值)未查 |
| H-6 | **R11 复盘** | 本卷 ◇-1 | 105 个零文档键的**清单已在 `data/r8a-config-keys.tsv`**,但未逐条判断"该不该文档化";R11 对表时可直接消费该列 |
| H-7 | **R8B / R8D** | `hermes_cli/config.py:3065`(`require_readable_config_before_write`) | 该守卫只检查文件**可读**不检查**可解析**;`set/unset_config_value` 各自补了解析检查(见 §3.5),但**是否存在第三个调用方直接 `read_raw_config()` 后落盘**本轮未穷举——若有,坏 YAML 会被静默截断 |
