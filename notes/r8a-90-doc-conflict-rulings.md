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

### ▲-5 docstring 与代码**语义相反**:说写 `tools.exclude`,实际写 `tools.include`

(线索来自 `notes/r8a-raw-tools-config-c` C-1,主线回源复核后**发现比原报告更严重**。)

`_configure_mcp_tools_interactive` 是 `hermes mcp` 里勾选每个 MCP 服务器要暴露哪些工具的界面。
它的 docstring 说改动落成**排除**项:

`hermes_cli/tools_config.py:5180-5181 @ 863e313`

```python
    a per-server curses checklist.  Writes changes back as ``tools.exclude``
    entries in config.yaml.
```

**代码写的是包含项,并且主动把遗留的排除项删掉:**

`hermes_cli/tools_config.py:5290-5292 @ 863e313`

```python
            tools_cfg["include"] = chosen_names
            # Drop any legacy exclude block — we're include-mode now.
            tools_cfg.pop("exclude", None)
```

**这不是"注释没跟上"那么简单——仓库做过一次有意的、写了理由的迁移**:

`hermes_cli/tools_config.py:5273-5276 @ 863e313`

```python
        # Compute new include list (the chosen tools). We standardize on
        # tools.include across the codebase (catalog installs, hermes mcp
        # configure, and this UI) so a server's on-disk config shape doesn't
        # depend on which UI the user touched last.
```

**理由写得很好**(统一成 include,免得同一个服务器的落盘形态取决于用户最后用了哪个界面),
迁移也做得很干净(顺手删遗留键)。**唯独同一个函数的 docstring 停在了迁移之前,
而且停在了语义正好相反的一侧。**

**危害为什么比一般的注释腐烂大**:`include` 与 `exclude` 是**互为反义**的。
一个信 docstring 的读者会以为"取消勾选一个工具 = 把它加进排除表",
从而推断"没被勾选过的工具默认可用";而真实语义是"勾选的即全集,其余一律不暴露"。
**同一段代码,两种读法给出的可见工具集恰好互补。**

**定案:▲ 成立,性质是「语义反转型 docstring 腐烂」。**
这是 R7B「docstring 也会说谎」、R7C「时间腐烂」之后的第三种形态,
判据也更锋利一条:**凡代码里出现"drop any legacy X"这类迁移善后动作,
就该顺手检查本函数 docstring 里还有没有 X**——迁移会记得改数据,常常忘了改说明。

### ▲-6 FAQ 把配对讲成"先到先得",而代码要求操作员批准

(线索来自 `notes/r8a-raw-pairing-and-config-cmd` F-8A-P12,主线已回源复核确认。)

FAQ 在两处把"DM 配对"这种访问控制模式解释成**谁先发消息谁独占**:

`website/docs/reference/faq.md:411 @ 863e313`

```
| **DM pairing** | First user to message in DM claims exclusive access |
```

`website/docs/reference/faq.md:96 @ 863e313`

```
Yes. The [messaging gateway](../user-guide/messaging/index.md) lets multiple users interact with the same Hermes Agent instance via Telegram, Discord, Slack, WhatsApp, or Home Assistant. Access is controlled through allowlists (specific user IDs) and DM pairing (first user to message claims access).
```

**代码事实恰好相反**:陌生人发第一条消息,入站路径能做的**只有生成一个待批的配对码**:

`gateway/run.py:14479 @ 863e313`

```python
                code = pairing_store.generate_code(
```

紧接着机器人把码回给他,并**明确告诉他去找机主**:

`gateway/run.py:14497-14499 @ 863e313`

```python
                            f"Ask the bot owner to run:\n"
                            f"`hermes {profile_arg}pairing approve "
                            f"{platform_name} {code}`"
```

全仓**只有两个授予点**,都必须由操作员从已认证侧调用
(`gateway/pairing.py:665` 的 `approve_code` 与 `:735` 的 `approve_request`)。
**入站消息路径对这两个函数零调用**——这一点 R7C 已证,本轮复核仍成立。

**定案:▲ 成立。** 这条比一般的文档腐烂更要紧,因为**它错的方向是让人低估暴露面**:
按 FAQ 的说法,运维者会以为"我先给机器人发过消息,所以别人进不来";
真实情况是**没人进得来,直到你自己批准**——听上去更安全,
但它同时意味着**运维者不会去检查待批队列**,而 §4.1 说的 `list_pending`
恰恰是这套机制唯一的可观测面。**说错了机制,顺带说没了操作动作。**

> **判据**:文档写访问控制时,"**谁来做那个授予动作**"是不能省的主语。
> "first user claims access"与"operator approves the first user"在安全上是两个模型,
> 而它们的表面现象(第一个人能用、后来的人不能用)**完全一样**——
> 所以这类错误不会被用户日常使用撞出来。

### ▲-7 迁移注释宣布"新默认值是 OFF",而默认值至今是 `"auto"`

(线索来自 `notes/r8a-raw-migrations-env-secrets` F6,主线已回源复核确认。)

v30→v31 这一步把 `agent.verify_on_stop` 一次性关掉,注释把理由写得很清楚,
其中一句是**对全局的宣告**:

`hermes_cli/config_migrations.py:544-545 @ 863e313`

```python
    # nothing to verify. The new default is OFF. This migration switches
    # existing installs off ONCE, but only when the user never expressed an
```

**但默认值没有跟着改**,而且旁边那段注释还在**为 `"auto"` 辩护**:

`hermes_cli/config_defaults.py:158 @ 863e313`

```python
        "verify_on_stop": "auto",
```

**后果是同一个版本上并存两拨行为不同的用户**:

| | 升级上来的老装 | 全新安装 |
|---|---|---|
| 迁移是否跑过 | 跑过,把 `auto` 改写成 `false` | 没有可迁移的老值 |
| 实际生效值 | **`false`(关)** | **`"auto"`(在 CLI/TUI/桌面上是开)** |

两人版本号相同、配置文件里都没手动设过这个键,行为却相反。

**定案:▲ 成立,性质是"注释宣布了一个没有发生的变更"。**
这比 ▲-5 那种"docstring 与实现相反"更隐蔽:注释在**它自己那段代码的范围内是对的**
(迁移确实把老装关掉了),错的是它替**另一个文件**做的宣告。

> **判据**:迁移注释里凡出现"新默认是 X"这类**跨文件断言**,就该有一条测试把
> `DEFAULT_CONFIG[该键] == X` 钉住。否则迁移与默认值这两处**永远不会一起被改**——
> 它们不在同一个文件、不在同一次 review、也不在同一条测试路径上。

### ▲-8 `hermes status --all` 是个死开关,而文档、help、测试三处都在说它有效

(线索来自 `notes/r8a-raw-status` F12,主线已回源复核确认。)

文档说它是"可分享的脱敏格式":

`website/docs/reference/cli-commands.md:554 @ 863e313`

```
| `--all` | Show all details in a shareable redacted format. |
```

**而 `show_status` 全文只读 `deep` 一个开关**:

`hermes_cli/status.py:117 @ 863e313`

```python
    deep = getattr(args, 'deep', False)
```

主线复核:在 `hermes_cli/status.py` 全文 grep 单词 `all`,只命中两处模块 docstring 里的
英文散文("Shows the status of all Hermes Agent components"),**没有任何一处读它**。

**这条的要害不是"一个开关没接线",而是三条线索合起来制造了很强的"它有效"的错觉**:
文档写了、`--help` 写了、连测试都取名 `test_show_status_all_...` 并且真的传了 `all=True`——
测试当然会过,因为被测代码根本不看这个参数。

**定案:▲ 成立(以代码为准:该选项无任何效果)。**
它与 ■-20(`VALID_BUSY_POLICIES` 有 import 无断言)是同一类错觉的两个变体:
**"这个名字在测试里出现过"被当成了"这个行为被测过"。**
本轮第二次看到,判据同 ■-20:**看断言,不看名字**。

### ▲-9 两处注释对"下限闸门在哪"给出相反答案

(线索来自 `notes/r8a-raw-migrations-env-secrets` F5,主线已回源复核确认。)

注册表这边说闸门在 `run_migrations()` 里:

`hermes_cli/config_migrations.py:653 @ 863e313`

```python
    # every remaining step below. Only configs BELOW 12 are refused by the
```

而实现那边明说**不在**那里,并且解释了为什么故意不放在那里:

`hermes_cli/config.py:2180-2182 @ 863e313`

```python
    # crashes on an ancient config. The floor gate lives here in the wrapper
    # (not in run_migrations) so the registry driver stays a pure mechanism
    # that tests can exercise directly.
```

**定案:▲ 成立(以 `config.py` 为准——它与代码一致)。**
严重度低,但值得记:**当一个设计决策的理由写在 A 处、而 B 处的注释描述了迁移前的旧位置时,
去 B 处找实现的人会先读到错的那句。** 注释也有"引用的行号"问题,只是它引的是函数名。

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

**顺带一个数**:这条桥**不走 `load_config()`**,用的是原始读 `read_user_config_raw`
——刻意如此,因为**只有用户真正写下的键才可以被桥进环境**
(先合并默认值的话,`DEFAULT_CONFIG` 的 82 个顶层键会整体变成环境变量)。
算上它,`config.yaml` 的读取方到本条为止已有四个
(`load_config` / `load_cli_config` / `read_raw_config` / `read_user_config_raw`),
**头条那句"两个装载器"其实说少了**;后文 ■-12 还会补上第五个。

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

### ◇-2 对照组:环境变量侧覆盖率 100%,原因值得抄

同一套检索跑 `OPTIONAL_ENV_VARS` 的 151 条静态条目:**零缺口**。

差别不在于有人更勤快,而在于**结构**:每条环境变量的说明是**写在定义字面量里的**
(`description` / `prompt` / `url` / `password` / `category` 四到六个字段),
定义与说明是同一处、同一次编辑;而 `DEFAULT_CONFIG` 的键只有**自由文本注释**,
说明写在另一个仓库(`website/`)的另一个文件里,两处各自演化。

**可迁移的设计原则**:把"这个键是什么"做成**数据结构里的必填字段**,而不是注释。
覆盖率就不再依赖纪律,而是依赖类型。这是本轮最值得带走的一条,详见成品章 §4。

### ◇-3 多个读取方的存在本身全站零文档

`notes/r8a-01` §2.1 那条"同一份 config.yaml 被两个装载器以不同合并语义读取",
在 `website/docs/user-guide/configuration.md` 全文(2,386 行)与 `AGENTS.md` 中
**没有任何提及**。文档呈现的是单一的、统一的配置系统。

对使用者的实际后果:在 CLI/TUI 里设一个嵌套键,与在 config.yaml 里设同一个键给网关用,
**行为可能不同**,而没有任何文档提示需要区分这两件事。

**本轮点清的读取方共五个**,各有各的合并、缓存与优先级姿态:
`load_config`(含 `load_config_readonly`,深合并 + 归一化 + 展开 + managed)/
`load_cli_config`(自带默认值,浅合并)/ `read_raw_config`(原始 + mtime 缓存)/
`read_user_config_raw`(原始、不吞异常;顶层标量→环境桥用它)/
`_load_gateway_config`(原始 + managed 叠加,不合并默认值)。
**■-10 / ■-11 / ■-12 三条缺陷都是这五者之间的差异直接造成的。**

---

## ■ 组:代码内部缺陷(35 条,只记录不修)

| # | 缺陷 | 锚点 | 怎么会踩到 |
|---|---|---|---|
| ■-1 | status 面板 QQBot 兼容分支**恒假**,且分支体是**空操作** | `hermes_cli/status.py:495` | 照官方文档配新名 → 机器人正常但面板不显示 home 频道 |
| ■-2 | `bedrock.discovery` 三个键**全部未接线** | `hermes_cli/config_defaults.py:789` | 改 `refresh_interval` 无任何效果;默认值撞上硬编码常量,改之前看不出来 |
| ■-3 | 两个装载器合并语义不同(深合并 vs `dict.update`) | `cli.py:599` | 在 CLI/TUI 侧设一个嵌套键,会静默清除其同级默认值 |
| ■-4 | `display.copy_shortcut` 是**全仓唯一一次出现** | `hermes_cli/config_defaults.py:1280` | 用户按注释里列的四个取值去设,永远无效 |
| ■-5 | `NOUS_BASE_URL` 在环境变量清单里,但代码读的是另外两个名字 | `hermes_cli/config_defaults.py:3132` | 安装流程会**主动向用户索要**一个没人读的变量 |
| ■-6 | 配对 CLI 捅穿 `PairingStore` 封装(三个私有成员) | `hermes_cli/pairing.py:81` | 私有方法改名 → 运维者最需要的那条诊断路径炸掉 |
| ■-25 | **迁移报告"已添加 15 个键",磁盘上一个也没落**:两条迁移写的值恰好等于 `DEFAULT_CONFIG`,被写入不变式整段剥掉 | `hermes_cli/config.py:2124`(`_persist_migration` 的不变式:等于默认值的一律不落盘)/ `hermes_cli/config_migrations.py:383`(v23 自述的目的正是"让用户能在 config.yaml 里看见/改动这些设置")/ `:231`(v15 同型) | 老用户升级,屏幕上打出 `✓ curator (8 default key(s))`,打开 `config.yaml` 什么都没有;因为 v23 的目的与写入不变式**直接互斥**,而互斥的那一方是静默的。主线运行时确证 |
| ■-26 | **密钥输入的两个平台分支对"一次读一个键"的契约理解不同**:Windows 分支吞掉整个转义序列,POSIX 分支只吞 `\x1b` 本身 | `hermes_cli/secret_prompt.py:46`(共用核心只丢弃 `\x1b`)/ `:95-98`(Windows `read_char` 消费双字节)/ `:116`(POSIX `read_char` 是裸 `read(1)`) | 在 Linux/macOS 上贴完 API key 后按一下 ↑ 想检查,`[A` **静默进了密钥**;注释还写着"转义序列不应变成密钥文本"。约 15 个调用点全是往 `.env` 存 API key,症状是 provider 报 401。主线运行时确证:同一核心,POSIX 得 `'ab[Ac'`,Windows 得 `'abc'` |
| ■-27 | **同一个 managed `.env` 在同一进程里被两个不同解析器读** | `hermes_cli/env_loader.py:588`(python-dotenv,负责灌 `os.environ`)/ `hermes_cli/managed_scope.py:180`(手写弱解析器,负责回答"这键是不是管理员钉的") | 管理员在 managed `.env` 里写 `export FOO=bar`:前者认出键名 `FOO`,后者认成 `'export FOO'` → managed 守卫不触发、`hermes config` 打印字面 `export KEY` |
| ■-28 | **版本号推进排在两段无保护的 `input()` 之后** | `hermes_cli/config.py:2283`(裸 `input()`,无 try)/ `:2365`(版本号在其后才 bump) | 升级时在"是否配置缺失的环境变量"那一问按 Ctrl-C,迁移已跑但版本号没前进 → 下次启动整梯重跑。单独看是幂等的无害重跑,**与 ■-25 叠加就变成"每次启动都说添加了、永远没添加上"** |
| ■-29 | `_known_hermes_env_keys()` 是**死函数**,同一逻辑的活版在 `config.py` | `hermes_cli/env_loader.py:55`(全仓零调用)/ `hermes_cli/config.py:4095`(活版) | 第六例"一个语义写了两次,其中一份死掉";维护者改到死版对行为零效果 |
| ■-30 | **skill 声明配置项时无法要求脱敏**,而补齐流程既不掩码输入也回显结果 | `agent/skill_utils.py:701`(声明 schema 只有 key/description/default/prompt,**无敏感标记**)/ `hermes_cli/config.py:2396`(裸 `input()`)/ `:2403`(`print(f"  ✓ Saved {var['key']} = {value}")`) | 需要 API key 的第三方 skill,只能让用户把密钥**明文打在屏幕上、再被原样回显一遍、然后明文写进 `config.yaml`**;同一个仓库里 `masked_secret_prompt` 就在旁边,env 那条路也有 `password: True` 走掩码。本基线自带 skill 无人声明此类字段,故是**设计缺口**而非现网泄露 |
| ■-31 | **status 判插件平台用 `check_fn()`,而契约是"依赖装了没"**;同仓孪生实现已修好,且**它的注释逐字描述了 status 现在的行为** | `hermes_cli/status.py:508`(`configured = entry.check_fn()`)/ `hermes_cli/gateway.py:5451-5456`(已修,注释:"that would let 'SDK is installed' override 'no token configured' and incorrectly report the platform as ready") | 装了 SDK 但没配 token 的插件平台,`hermes status` 报**已配置**;点开网关菜单看同一个平台,报**未配置** |
| ■-32 | **`hermes doctor` 与 `hermes status` 对同一个环境变量给出相反指令** | `hermes_cli/doctor.py:258`(把 `QQ_HOME_CHANNEL` 列为弃用,催用户改名)/ `hermes_cli/status.py:483`(表里只有旧名)/ `:495`(回落守卫比对的值表里取不到) | 用户听 doctor 的话把变量改成新名 → 机器人照常工作,但 `hermes status` 的 QQBot 行**不再显示 home 频道**,且无任何提示。**照着诊断工具做,另一个诊断工具就瞎了** |
| ■-33 | status 的脱敏**只覆盖 API key**,PII 全明文 | `hermes_cli/status.py:500`(home channel 原样打印,内容可能是手机号/邮箱/OpenID)/ `:434-435`(SSH 主机与用户)/ `:129`(项目绝对路径) | 文档把 `--all` 叫做 "shareable redacted format"(▲-8),用户据此把 status 输出贴进 issue → 贴出去的是手机号和邮箱。API key 那一侧是有测试守着的,做得很好——**问题是"敏感"被等同于"API key"** |
| ■-34 | status 有 **8 处无保护调用点**可以把整条命令打崩,而崩溃抵抗测试**全部集中在一个块** | `hermes_cli/status.py:344-345`(◆ Nous Tool Gateway 整节 344-376 无 try,裸露面最大)/ `:181`/`:189`(`get_env_value` 会显式 `raise UnscopedSecretError`)/ 测试 `tests/hermes_cli/test_status.py:148,159,173,188`(4 个崩溃抵抗用例全在 xAI OAuth 一块) | 排障命令本身崩在半截:前面的输出已经打出来了,后面接一段 traceback。**最需要能跑的那条命令,恰恰在环境不正常时最容易崩** |
| ■-35 | 6 家 provider 在**同一屏里出现两次**,两次用不同的环境变量集合作判断 | `hermes_cli/providers.py:107`(权威声明)/ `hermes_cli/status.py` 两段各自成表 | 只设了 `ZAI_API_KEY` 的用户,在同一屏上同时看到 `Z.AI / GLM ✗ (not set)` 和 `Z.AI / GLM ✓ configured` |
| ■-22 | **两条壳路各测了交集,唯一真分叉两边都没测**:CLI 壳 1 例、GUI 壳 3 例,交集是 request-id 成功路;■-8 那条分叉零覆盖 | `tests/hermes_cli/test_pairing.py:8`(CLI 壳全部)/ `tests/hermes_cli/test_dashboard_admin_endpoints.py:256,276,316`(GUI 壳全部)/ `tests/gateway/test_pairing.py`(29 例,只到 store 层) | ■-8 那个错误提示可以永远存在:store 层测得很密,壳层只测双方一致的那条路,而两把钥匙**唯一**不一致的地方恰好在壳里 |
| ■-23 | `clear-pending` **清的是所有平台**,两个入口都没说清 | `hermes_cli/pairing.py:116` / `hermes_cli/web_server.py:12374`(都不传 platform)/ `gateway/pairing.py:807`(不传即 `_all_platforms`) | 运维者想清掉 Discord 那堆待批,顺手把 Telegram / Slack 的也清了;help 文案 "Clear all pending codes"(`hermes_cli/subcommands/pairing.py:39`)字面不错,但不足以让人预期跨平台 |
| ■-24 | 锁定恢复提示**只有 CLI 有**,且**硬编码了新版路径** | `hermes_cli/pairing.py:96`(提示写死 `~/.hermes/platforms/pairing/`)/ `hermes_cli/web_server.py:12347`(GUI 的 429 无恢复路径) | 老装的文件其实在 `~/.hermes/pairing/`,运维者照提示去删,找不到文件;走面板的运维者则连"可以手删恢复"都不知道 |
| ■-16 | **第二例“默认值撞上硬编码值”**:`resource_attributes["service.name"]` 被无条件覆盖 | `agent/monitoring/gateway_health_export.py:85`(覆盖)/ 默认值恰等于该硬编码值 | 用户改 `service.name` 毫无效果;因默认值==硬编码值,在默认值上验证必然假阳性。同块的 `deployment.environment.name` 却是好的 |
| ■-21 | **bug 修好了、回归测试也写了,但都只落在两条写路径中的一条** | `hermes_cli/web_server.py:6520`(GUI 已修)/ `hermes_cli/moa_cmd.py:127,147`(CLI 未修)/ `tests/hermes_cli/test_moa_set_models_preserves_extra_keys.py:12`(测试 import 的是 GUI 侧) | 手写 `moa.save_traces: true` 开了 trace,跑一次 `hermes moa configure` 换模型,**trace 悄悄关了**;走 dashboard 做同一件事则不会 |
| ■-20 | **名叫 `VALID_BUSY_POLICIES` 的常量不校验任何东西**;唯一引用它的测试 import 了却零断言 | `hermes_cli/commands.py:93`(常量)/ `:75`(裸 `str` 字段)/ `gateway/run.py:14117`(消费方) | `busy_policy` 写错一个字母不报错,该命令在 agent 忙时**从“可执行”静默变成“被拒”**;而文件名 `test_busy_policy_invariants` + import 两条线索合起来制造了“已覆盖”的错觉 |
| ■-19 | **自我拆台的守卫**:检查了成员资格,随后赋的值却没再检查 → `KeyError` 崩栈 | `hermes_cli/tools_config.py:3794-3795`(守卫)/ `:3817`(`catalog[mid]` 崩) | 任何第三方 image_gen / video_gen 插件的 `default_model()` 返回值不在 `list_models()` 里(或为 None),用户在 `hermes tools` 里选中它即崩溃退出;video 版同形(`:3956`) |
| ■-18 | **读-改-写用了两份各自 `load_config()` 的副本,后写的抹掉前一份** | `hermes_cli/tools_config.py:4356`(内层自己重载)/ `:5153-5154`(外层随后存过期副本) | 在 `hermes tools` 里配好 vision 模型 → 主流程随后一存,该值被**清空回默认**;键还在、值没了,比"配置项消失"更难查。主线运行时确证 |
| ■-17 | **`or` 兜底链让“显式 0”无法表达** | `hermes_logging.py:313`(`backup_count or cfg_backup or 3`);正确写法见 `gateway/platforms/base.py:742` | `logging.backup_count: 0`(不留备份)静默变 3;`max_size_mb: 0`、`model_catalog.ttl_hours: 0` 同型。同仓库两种写法并存 |
| ■-15 | **同一进程里两个界面对“cua-driver 装好没有”给出相反答案** | 安装成功判定 `hermes_cli/tools_config.py:1585`(裸 `shutil.which`)vs 就绪判定 `:3273`(走 `_resolved_cua_driver_cmd`,`:760`) | 从 Finder/Dock 启动的 Desktop(PATH 窄)里点安装:实际装到了 `~/.local/bin`,安装器打印“did not complete”,而就绪标志同时报 ready |
| ■-14 | **两级优先级写成了一趟循环**,弱信号在同一次迭代里短路,于是**列表顺序压过信号强度** | `hermes_cli/tools_config.py:3641-3646` | 用过 OpenAI 转录、后来切到 Groq 的用户,进 `hermes tools → Speech-to-Text`,光标默认停在 **OpenAI**;**直接回车就把 provider 悄悄改回去了** |
| ■-13 | **插件 provider 的注入点用类目"显示名"做匹配键**,而稳定键就在同一个 dict 里 | `hermes_cli/tools_config.py:3137/3142/3150/3158/3164`(五处)/ `:484-485`(稳定键 `"web"` 与显示名并列) | 改一个界面文案(大小写、`&` 写法)→ 该类目的插件行**静默消失**;`video_gen` 与 `web` 两个类目**没有任何硬编码 provider**,一改就整类目空掉 |
| ■-12 | **14 个内置人格在网关侧完全不存在** | `cli.py:477`(14 条只在 CLI 默认值里)/ `gateway/slash_commands.py:2502`(网关读法)/ `gateway/run.py:3145`(网关用的是**原始读**,不合并默认值) | 全新安装下,CLI 有 14 个人格可选,而聊天里敲 `/personality` 回"none configured" |
| ■-11 | **一个自称"单一真源、防止各面漂移"的函数,实测在两个面上相差 780 秒** | `tools/clarify_gateway.py:388`(自述)/ `:399`(遗留键优先)/ `cli.py:523`(遗留键的 CLI 默认值 120) | 用户设 `agent.clarify_timeout: 900`(规范键):网关面得 900、CLI 面得 **120**;因 `cli.py` 默认值恒供遗留键 `clarify.timeout`,规范键在 CLI 面**永远无法生效** |
| ■-10 | **两份默认值的第一个真实受害者**:`hermes config set agent.reasoning_effort high` 被判为未知键,并给出会弄坏配置的建议 | `hermes_cli/config.py:4810`(校验)/ `cli.py:8166`(真实读取点)/ `cli.py:479`(它所在的那份默认值) | 命令正确、值也写对了,但打印"不是已知配置键";建议改用 `agent.reasoning_overrides`,而那个键的默认值是 `{}`(字典),照做后思考力度静默失效 |
| ■-9 | `_COMMENTED_SECTIONS` 是**已漂移的死副本** | `hermes_cli/config.py:3473` | 活版是 `_SECURITY_COMMENT`/`_FALLBACK_COMMENT`(:3601/:3609);两份同一句话已不同。维护者改到死版,对用户文件零效果 |
| ■-8 | **两把配对钥匙行为不一致**:CLI 在 request-id 路径上也报"平台被锁定" | `hermes_cli/pairing.py:81` vs `hermes_cli/web_server.py:12346` | 用过期 request-id 批准 + 平台恰好因别的原因锁定 → CLI 告诉运维者"等 N 分钟",而真实原因是请求过期;dashboard 同一操作正确回 404 |
| ■-7 | `OPTIONAL_ENV_VARS` 在 import 时被**原地改写** | `hermes_cli/config.py:5307` | 静态分析(含本项目第一版脚本)只看到 151/308 |

### ■-25 细节:本轮最锋利的一条 —— 两个各自正确的设计,合起来把其中一个变成空操作

(线索来自 `notes/r8a-raw-migrations-env-secrets` F1,**主线已独立跑通复现**,输出见下。)

**先看两边各自的道理,两边都对。**

写入不变式这一侧:迁移**只许写与当前默认值不同的值**,纯默认值一律不落盘。
理由写得非常充分,而且是从一次真实事故里学来的:

`hermes_cli/config.py:2127-2134 @ 863e313`

```python
    THE INVARIANT (single source of truth for the whole migration pipeline):
    a migration may only persist values that DIFFER from the current schema
    default, plus explicit removals/renames of user data. Pure schema defaults
    are never materialised to disk — ``load_config()``'s deep-merge supplies
    them at read time, so writing them adds nothing and actively shadows future
    default changes (see ``save_config``'s docstring). Materialising defaults on
    every version bump is what rewrote hand-curated configs into full
    DEFAULT_CONFIG dumps (the "hermes update / hermes -p blows up my config"
```

**这条不变式是对的**:把默认值写进用户文件,会让用户的文件**冻结**在今天的默认值上,
以后改默认值对他无效——这正是"我的配置被 hermes update 搞坏了"那批报告的根因。

迁移 v23 这一侧:它的**目的**恰恰是把 curator 那一段**写进** `config.yaml`,
而且理由同样充分——**让用户看得见、改得动**:

`hermes_cli/config_migrations.py:387-392 @ 863e313`

```python
    # unification under `auxiliary.curator`) never wrote the curator section
    # to disk. The runtime deep-merge in `load_config()` fills defaults at
    # read time, so the curator *functions*; but users can't see/edit the
    # settings in their `config.yaml`, and `hermes curator status` has no
    # stable logs dir to point at until the first run mkdir's it.
    #
    # This migration:
```

**两句话放在一起就是矛盾**:一个说"等于默认值的不准落盘",另一个说"我就是要把默认值落盘,
好让用户看见"。而 v23 写的值**恰恰全部等于默认值**(它写的就是默认值本身)。

**不变式赢了,而且赢得毫无声响。**

**主线独立复现**(临时 `HERMES_HOME`,`config.yaml` 内容为 `model: my-model` + `_config_version: 22`,
直接调 `_migrate_to_23`):

```
=== results reported by the migration:
{
  "config_added": [
    "curator (8 default key(s))",
    "auxiliary.curator (7 default key(s))"
  ],
  ...
}
=== curator section present on disk?  False
```

**屏幕上报告加了 15 个键,磁盘上一个都没有。** v23 自述的三条目的里,
第 1 条(写 `curator` 段)、第 2 条(写 `auxiliary.curator` 段)**全部落空**,
只有第 3 条(`mkdir logs/curator/`)生效——因为只有它不经过 `_persist_migration`。

**为什么这条比本卷其它条都值得记。**

前面所有"一个语义两份实现"的条目,坏的是**重复**;这一条坏的是**组合**:
两段代码各自都是这个仓库里质量最高的一档(注释详尽、理由指向真实事故、
不变式还专门写了"每个迁移步骤必须走这个 helper,集中化让不变式不可能被单点回归"),
**它们只是从来没有被放在一起想过**。

而它的失败姿态是最坏的那种:**不报错、不警告,而且主动报告成功**。
用户看到 `✓ curator (8 default key(s))`,没有任何理由去打开文件核对。

> **判据三条**:
> 1. **"报告做了什么"必须来自"实际写了什么",不能来自"打算写什么"。**
>    本例里 `results["config_added"]` 是在**调用 `_persist_migration` 之前**填的,
>    它记录的是意图。把它改成从落盘结果反算,这个 bug 当场自曝。
> 2. **全局不变式要配一条"我的写入被不变式吃掉了"的回执。**
>    `_persist_migration` 完全知道自己剥掉了哪些键——它只是没说。
>    一个 `if stripped and not quiet: warn(...)` 就够了。
> 3. **凡是"为了让用户看得见而把默认值写进配置文件"的需求,先问它和
>    "默认值不落盘"是不是同一个系统里的两条互斥规则。** 如果是,
>    正确解法通常不是写文件,而是**让展示面去读默认值**(`hermes config get` 显示
>    "(default) 8" 而不是空),这样两条规则都不用破。

### ■-26 细节:共用核心假设 `read_char()` 返回"一个键",而两个平台分支只有一个真做到

(线索来自 `notes/r8a-raw-migrations-env-secrets` F3,**主线已独立跑通复现**。)

密钥输入被拆成"共用核心 + 两个平台分支",结构本身是好的。核心负责按键语义,
其中一条是**丢弃转义序列**,注释说得很明确:

`hermes_cli/secret_prompt.py:46-48 @ 863e313`

```python
        if ch == "\x1b":
            # Ignore escape itself. Terminals commonly send escape-prefixed
            # navigation/delete sequences; they should not become secret text.
```

**注意它只 `continue` 掉了 `\x1b` 本身。** 这段代码要成立,前提是
`read_char()` **返回的是一个逻辑按键**——一次方向键就是一个 `\x1b`,没有后续字节。

Windows 分支**做到了**:它认出双字节前缀,把第二个字节一起吃掉,再合成一个 `\x1b` 返回。

`hermes_cli/secret_prompt.py:95-98 @ 863e313`

```python
        ch = msvcrt.getwch()
        if ch in {"\x00", "\xe0"}:
            msvcrt.getwch()
            return "\x1b"
```

POSIX 分支**没做到**,它是裸的一次读一个字节:

`hermes_cli/secret_prompt.py:116 @ 863e313`

```python
        return sys.stdin.read(1)
```

于是一次 ↑ 在 POSIX 上是三个字节 `\x1b` `[` `A`:核心丢掉第一个,
**后两个当作普通字符进了密钥**。

**主线独立复现**(直接喂 `_collect_masked_input` 两种 `read_char`,同一份核心):

```
POSIX  (read_char = 1 byte)   -> 'ab[Ac'
WINDOWS(read_char = 1 key)    -> 'abc'
```

**用户可复述的因果**:在 Linux/macOS 上贴完 API key,想按 ↑ 看看上一条、或者按 ← 挪一下光标,
屏幕上只多了两个 `*`(因为掩码就是 `*`,看不出异常),回车存进 `.env`,
然后 provider 一直报 401。**他会去怀疑 key 本身、怀疑复制粘贴、怀疑 provider——
唯独不会怀疑"我按了个方向键"。**

**这不是 ASCII 净化能兜住的**:`[A` 是纯 ASCII,清洗规则看不出问题。
三个现有测试用例也都没喂过转义序列。

> **判据**:**"共用核心 + N 个平台适配器"里,核心对适配器的隐含契约必须写下来并被测。**
> 这里的契约是一句话:"`read_char()` 每次返回**一个逻辑按键**,多字节序列由你合并"。
> 它没写在任何地方,于是两个适配器给出了两种理解,而**核心无法察觉**。
> 最省事的落地方式是给核心配一组**平台无关的表驱动测试**:喂一串按键、断言输出,
> 两个适配器各自用自己的 `read_char` 跑同一张表。本例里只要表里有一行"方向键",
> POSIX 分支在提交时就会红。
>
> 注意它与 ■-22 的形状差异:■-22 是**两个壳都没测**;这里是**核心测了、壳没测**,
> 而 bug 恰好在"核心与壳之间那条没写下来的契约"上。

### ■-31 细节:孪生实现已经修好了,而且它的注释逐字描述了未修那一侧的 bug

(线索来自 `notes/r8a-raw-status` F3,主线已回源复核确认。)

"这个插件平台配好了没有"有两个判定。`status` 这一侧直接问 `check_fn()`:

`hermes_cli/status.py:508 @ 863e313`

```python
            configured = entry.check_fn()
```

网关菜单那一侧**先问 `is_connected`**,只有在没有这个钩子时才回落到 `check_fn`,
并且**明确写下了不能回落的理由**:

`hermes_cli/gateway.py:5451-5456 @ 863e313`

```python
            # No is_connected hook — fall back to check_fn as a coarse
            # "are deps present" gate. Don't fall back when is_connected
            # is defined and returned False; that would let "SDK is
            # installed" override "no token configured" and incorrectly
            # report the platform as ready.
```

**把这段注释的最后一句抄下来,就是 `status.py:508` 今天的行为**:
SDK 装了(`check_fn` 为真)、token 没配(`is_connected` 为假),`status` 报 ready。

**这是本轮"修复只落在一条路上"的第四例,也是最刺眼的一例**——
前三例是"另一条路没人想起来";这一例里,**修好的那条路把 bug 描述得清清楚楚,
就写在同一个仓库、同一个概念、隔着一个文件的地方**,而没人回头看一眼另一条。

> **判据**:**写"不要这样做,否则会 X"的注释时,顺手 grep 一下仓库里还有谁正在这样做。**
> 这类注释是最好的检索线索——它已经把错误行为精确描述出来了。
> 本例只要在写 `gateway.py` 那段注释时 grep 一次 `check_fn()`,就会撞见 `status.py:508`。

### ■-32 细节:两个诊断命令给出相反的指令,照着做的人会把另一个弄瞎

(线索来自 `notes/r8a-raw-status` F2,主线已回源复核确认。这一条把 R7C 移交项①从
"status 有个恒假分支"扩展成了完整因果链。)

`hermes doctor` 把旧名列进弃用表,催用户改成新名:

`hermes_cli/doctor.py:258 @ 863e313`

```python
    ("QQ_HOME_CHANNEL", "QQBOT_HOME_CHANNEL"),
```

而 `hermes status` 的表里**只有旧名**:

`hermes_cli/status.py:483 @ 863e313`

```python
        "QQBot": ("QQ_APP_ID", "QQ_HOME_CHANNEL"),
```

它那条本该兜底的守卫,比对的是**这张表任何一条都取不到的值**(15 条第二元素里没有它):

`hermes_cli/status.py:495 @ 863e313`

```python
        if not home_channel and home_var == "QQBOT_HOME_CHANNEL":
```

**完整因果**:用户跑 `hermes doctor` → doctor 说 `QQ_HOME_CHANNEL` 弃用了,改成
`QQBOT_HOME_CHANNEL` → 用户照做 → 机器人一切正常(网关读的就是新名)→
**但 `hermes status` 的 QQBot 行从此不再显示 home 频道**,而且不给任何提示,
因为 status 只读旧名、回落守卫永不触发、分支体还是空操作。

**更值得记的是子代理跑出来的第三种场景**:两个名字都设着时,status 显示的是**旧名的值**——
而网关运行时用的是新名的值。**这是 status 唯一一次主动说错话**(前两种只是漏说)。

> **判据**:**同一个仓库里的多个诊断命令,必须共享同一份"变量正名/别名"表。**
> 本例里 doctor 有一份弃用映射、status 有一份硬编码表、网关有第三份回落逻辑——
> 三份对同一次改名的理解各不相同。诊断工具之间自相矛盾,比单个工具不准更糟:
> **用户信任诊断输出,并会照着它改配置。**

### ■-22 细节:核心共用是对的,但"壳"没人测,而分叉恰恰只长在壳里

(线索来自 `notes/r8a-raw-pairing-and-config-cmd` F-8A-P3,主线已回源复核确认——
两条 grep 与两次计数都由主线重跑。)

**先说好消息,因为它是 R7C 那笔移交项的正面结案。** R7C 交下来的问题是:
配对批准有 CLI 与 GUI 两个入口,**是不是两套判定**?本轮答案是**不是**——
超时、一次性、大小写、去空格、恒定时间比较、失败计数,**六项逐条无差异**,
因为两个入口都直落同一个 `PairingStore`,判定实现全仓唯一。
**这是本簇里少见的"做对了"的例子**:一个语义,一份实现,两个薄壳。

**坏消息是:测试的密度恰好与风险分布反着来。**

store 层(共用的那份)测得很密:

`tests/gateway/test_pairing.py:1 @ 863e313`

```python
"""Tests for gateway/pairing.py — DM pairing security system."""
```

主线数了一遍:该文件 `def test_` 共 **29** 个
(子代理报的是 28,以主线复核为准——这类小数目差异正是本轮反复出现的
"先写成一个具体的数再去验它"的价值所在)。

而两层壳合起来只有 **4 个**用例。CLI 壳整个文件 43 行、**一个**用例:

`tests/hermes_cli/test_pairing.py:8 @ 863e313`

```python
def test_cli_listed_request_id_and_bot_code_can_be_approved(tmp_path, capsys):
```

GUI 壳三个:

`tests/hermes_cli/test_dashboard_admin_endpoints.py:256 @ 863e313`

```python
    def test_approve_pending_request_id(self):
```

`tests/hermes_cli/test_dashboard_admin_endpoints.py:276 @ 863e313`

```python
    def test_pairing_is_isolated_per_profile(self):
```

`tests/hermes_cli/test_dashboard_admin_endpoints.py:316 @ 863e313`

```python
    def test_unknown_profile_is_rejected(self):
```

**主线复核**:在这两个壳测试文件里 grep `_is_locked_out` / `revoke` / `clear_pending`,
**零命中**。也就是说——

| | CLI 壳 | GUI 壳 |
|---|---|---|
| request-id 成功路 | ✅ 测了 | ✅ 测了 |
| **锁定归因(■-8 的分叉所在)** | ❌ | ❌ |
| code 路径 | ❌ | ❌ |
| revoke | ❌ | ❌ |
| clear-pending | ❌ | ❌ |

**两条路各测了它们一致的那一格,唯一不一致的那一格两边都空着。**

**这就是 ■-8 那个错误提示能一直活着的原因。** 它不是"漏测了一条路",
而是**测试覆盖的形状与缺陷分布正交**:共用核心不会分叉,所以测它测不出分叉;
薄壳会分叉,而薄壳"看起来没什么逻辑,不值得测"。

**本轮该模式的三种形态,到这里凑齐了**:

| | 形态 | 实例 |
|---|---|---|
| 一 | 修了一条路,测了同一条路,另一条没修 | §3.2 managed 叶级合并 / ■-21 moa 写路径 |
| 二 | 两条路都在,只有一条被测 | ■-21 的测试 import 钉在 GUI 侧 |
| 三 | **两条路都被测了,但只测到它们相同的地方** | **■-22(本条)** |

> **判据**:**测试该往"两份实现有可能不一致的地方"放,而不是往"逻辑最多的地方"放。**
> 共用核心测得再密,也证明不了两个壳一致——那是一条**它根本不经过**的信息。
> 具体做法:凡出现"共享核心 + N 个薄壳",就为**每个壳**写一组**同输入同断言**的对照用例
> (哪怕只有三五条),让"两壳行为一致"变成一条会失败的断言。
> 本例里只要有这么一组,■-8 在提交时就会红。

### ■-16 细节:第二例"默认值撞上硬编码值"——这条从个案升级成了模式

(线索来自 `notes/r8a-raw-defaults-b` D5,主线已回源复核确认。)

`monitoring.gateway_health_export.resource_attributes` 允许用户自定义 OTLP 资源属性。
用户填的值确实被收下了(过一层白名单 `_safe_resource_attributes`),**然后被无条件覆盖**:

`agent/monitoring/gateway_health_export.py:85 @ 863e313`

```python
    attrs["service.name"] = "hermes-gateway"
```

而 `DEFAULT_CONFIG` 里这个键的默认值**恰好就是** `"hermes-gateway"`:

`hermes_cli/config_defaults.py` 中 `resource_attributes` 实测为
`{'service.name': 'hermes-gateway', 'deployment.environment.name': 'production'}`。

**于是没人会发现**:想验证"这个键有没有用",在默认值上观察到的行为完全正确;
只有真的改成别的值,才会发现改了等于没改,而那时人会去怀疑 OTLP 后端、采集器、
网络——不会怀疑这个键根本没生效。

**同一个块里的兄弟键是好的**:`deployment.environment.name` 不被覆盖,能正常生效。
**又一次"一个 section 里两个子键一个能用一个不能用"**,与 ▲-2 的 bedrock 完全同型。

**这条的价值在于它把 ▲-2 从个案变成了模式。** 两例独立出现,判据可以固化下来:

> **凡"配置键的默认值 == 代码里的硬编码值",这个键就必须专门验一次接线。**
> 因为这种情形下,**最自然的验证方式(在默认值上跑一遍看看对不对)必然给出假阳性**。
> 反过来说,写代码时应当**刻意让默认值与任何硬编码兜底不同**——
> 哪怕差一点点,也能让"没接线"在第一次测试时就暴露。

### ■-21 细节:bug 修对了、回归测试也写了 —— 但两者都只落在两条路径中的一条

(线索来自 `notes/r8a-raw-mcp-moa-config` D5,主线已回源复核确认,**并因此把"回归测试写在已修好的那一侧"确立为模式**。)

`moa` 这一段配置有两条写入路径:GUI(dashboard)与 CLI。`normalize_moa_config` 返回的是
**封闭 schema**,不含 `save_traces` / `trace_dir` 这类手写键。

**GUI 那条修好了**,而且注释把 issue 号和理由都写上了:

`hermes_cli/web_server.py:6520-6521 @ 863e313`

```python
            # Merge instead of overwrite so that hand-edited keys not declared
            # in MoaConfigPayload (e.g. save_traces, trace_dir) survive a GUI
```

**CLI 那条没修**,仍是整键覆盖:

`hermes_cli/moa_cmd.py:127 @ 863e313`

```python
        cfg["moa"] = normalize_moa_config(moa)
```

`hermes_cli/moa_cmd.py:147 @ 863e313`

```python
        cfg["moa"] = normalize_moa_config(moa)
```

**而 #58819 的回归测试,import 的是 GUI 那一侧:**

`tests/hermes_cli/test_moa_set_models_preserves_extra_keys.py:12 @ 863e313`

```python
from hermes_cli.web_server import MoaConfigPayload, MoaModelSlot, MoaPresetPayload, set_moa_models
```

主线复核:全仓提到 `save_traces` 的测试只有两个文件,另一个
(`tests/agent/test_moa_trace_streamed_capture.py`)测的是 trace 采集本身,不是键保全;
而确实覆盖 `moa_cmd` 的 `tests/hermes_cli/test_moa_config.py` **不碰 `save_traces` / `trace_dir`**。

**用户可复述的因果**:手写 `moa.save_traces: true` 打开 trace → 之后跑一次
`hermes moa configure` 换个模型 → **trace 悄悄关了**,而他只是换了个模型。
走 dashboard 做同一件事则不会。

**这条把一个模式坐实了。** 本轮第二次看到同一形状:

| # | bug | 修在哪条路径 | 回归测试落在哪条 | 另一条 |
|---|---|---|---|---|
| §3.2 | 覆盖时清掉同级键 | managed 层(叶级合并) | **managed 层** | 默认值←用户配置那步仍是浅合并 |
| ■-21 | 覆盖时丢掉未声明的手写键 | GUI 写路径 | **GUI 写路径** | CLI 写路径仍整键覆盖 |

**两次都是:问题被正确诊断、正确修复、正确加了回归测试——但只在发现问题的那条路径上。**
测试用例的 import 语句把它钉死在那一侧,于是孪生路径不但没修,还因为
"这个 bug 有回归测试"而显得已经解决。

> **判据**:修一个 bug 时,先问"**同样的语义在这个仓库里还有第几份实现?**"
> (本轮答案通常是 2)。回归测试**必须逐份覆盖**,或者——更好——
> 借这次修复把多份合并成一份。**只修一份 + 只测一份,产生的不是半个修复,
> 而是一个带着"已修复"标记的、更难再被发现的 bug。**

### ■-20 细节:一个名叫 `VALID_*` 的常量,不校验任何东西

(线索来自 `notes/r8a-raw-commands`,主线已回源复核确认。)

`CommandDef.busy_policy` 决定"agent 正忙时敲这条命令会怎样",合法值只有三个。
仓库把它们写成了一个常量,注释还明说这是"合法值":

`hermes_cli/commands.py:92-94 @ 863e313`

```python
# Valid values for CommandDef.busy_policy (see field docs above).
VALID_BUSY_POLICIES: frozenset[str] = frozenset(
    {"dispatch", "reject", "interrupt_then_dispatch"}
```

**但字段本身是裸 `str`,没有任何地方拿这个常量去校验:**

`hermes_cli/commands.py:75 @ 863e313`

```python
    busy_policy: str = "reject"
```

全仓 grep `VALID_BUSY_POLICIES` 只有**两处**:上面的定义处,
以及 `tests/hermes_cli/test_busy_policy_invariants.py:13` 的 **import**。
而那个测试文件只有两个用例,**都没有引用它**——import 了却从不断言。

**于是它看起来是被覆盖的**:静态检查看到它被 import,人去 grep 也会看到
"它在一个名叫 `test_busy_policy_invariants` 的文件里出现过"。**两种线索都在撒谎。**

**后果**:`busy_policy="dispatchh"` 这种笔误不会有任何报错。消费方直接读字符串:

`gateway/run.py:14117 @ 863e313`

```python
        policy = getattr(cmd_def, "busy_policy", "reject")
```

拼错的值匹配不上任何分支,落到"忙时拒绝"这一侧——
**一条本该在 agent 忙时也能执行的命令,会变成忙时被拒,而且静默。**

> **判据两条**:
> 1. **凡定义了"合法值集合"的常量,就必须有一处真的拿它做校验**——
>    否则它只是一段注释,却顶着一个让人以为有强制力的名字。
>    更省事的做法是让类型系统承担:`busy_policy: Literal["dispatch", "reject", ...]`,
>    这样连常量都不需要,笔误在类型检查阶段就死掉。
> 2. **"某个符号在测试文件里出现过"不等于它被测过。**
>    判断覆盖要看**断言**,不看 import。本例里文件名(`*_invariants`)与 import
>    两条线索叠加,制造了很强的"已覆盖"错觉——而真实断言数是零。

### ■-19 细节:守卫检查了 A,却把 B 赋了进去

`hermes_cli/tools_config.py:3793-3795 @ 863e313`

```python
    current_model = cur_cfg.get("model") or default_model
    if current_model not in catalog:
        current_model = default_model
```

**这个守卫是自我拆台的**:它确认 `current_model` 在 `catalog` 里,不在就换成 `default_model`
——**而 `default_model` 本身从来没被检查过**。于是 `ordered[0]` 可能是个 catalog 里没有的 id,
下一步直接下标取值:

`hermes_cli/tools_config.py:3817 @ 863e313`

```python
        row = _format_imagegen_model_row(mid, catalog[mid], widths)
```

**`KeyError`,`hermes tools` 崩栈退出。** 触发条件:第三方 image_gen / video_gen 插件的
`default_model()` 返回了不在自己 `list_models()` 里的 id(或 `None`)。
video 版同形(`hermes_cli/tools_config.py:3956`)。

> **判据**:"不满足条件就换成兜底值"这种写法,**兜底值必须满足同一个条件**——
> 否则守卫只是把崩溃点往后挪了几行。写法上更稳的是让兜底值参与同一次校验
> (`if current_model not in catalog: current_model = next(iter(catalog), None)`),
> 或在函数入口就断言插件契约。

### ■-18 细节:读-改-写用了两份各自加载的配置,后写的那份把前一份抹掉(主线运行时确证)

(线索来自 `notes/r8a-raw-tools-config-c` D-2,主线**独立跑通复现**。)

`hermes tools` 的主流程 `tools_command` 先加载一份 `config` 拿在手里,
中途调用 `_configure_toolset(...)` 让用户交互配置某个工具。而其中的
`_configure_vision_backend` **不用传进来的那份,自己重新加载**:

`hermes_cli/tools_config.py:4356 @ 863e313`

```python
    config = load_config()
```

它在自己那份上改完并落盘。**然后控制权回到主流程,主流程把手里那份(早已过期的)存了下去:**

`hermes_cli/tools_config.py:5153-5154 @ 863e313`

```python
            _save_platform_tools(config, pkey, new_enabled)
            save_config(config)
```

**主线运行时确证**(同一个 HERMES_HOME,模拟这个调用序列):

```
callee : auxiliary.vision.model = 'my-vision-model'  → save_config(inner)
caller : display.compact = False                     → save_config(outer)   # outer 是过期副本
落盘结果: auxiliary = {'vision': {'model': ''}}
          display.compact = False
```

**用户刚配好的 vision 模型被抹成空串**(回到默认值),而调用方自己那项改动完好。
`save_config` 不做冲突检测,也没有版本/mtime 比对——**后写的那份赢**。

值得注意的是键**没有消失**、而是变成了 `''`:过期副本里那个位置正是默认值 `''`,
于是"显式路径保留"逻辑把它当成用户设过的空值写了回去。
**现象因此更隐蔽:不是"配置项不见了",而是"配置项还在,但值被清空了"。**

`_reconfigure_tool` 是同一形状(`hermes_cli/tools_config.py:4565`)。

> **可迁移的判据**:一个函数如果**接收**了一份配置对象,就**绝不能**自己再 `load_config()`。
> 要么全程传递同一份对象、由最外层统一落盘;要么内层落盘后**把结果回传**给外层刷新。
> 二者选一,不能混。**混用的症状是"我明明设了,一退出就没了",
> 而且因为它依赖调用顺序,单测两个函数各自都会绿。**

### ■-17 细节:`or` 兜底链让"显式 0"无法表达,而同一仓库里有正确写法

(线索来自 `notes/r8a-raw-defaults-b` D3,主线已回源复核确认。)

`logging.backup_count: 0` 的语义显然是"一个备份都不留",但它被 `or` 链吃掉了:

`hermes_logging.py:313 @ 863e313`

```python
    backups = backup_count or cfg_backup or 3
```

`0` 是 falsy,于是静默变成 `3`(默认值实测就是 3)。同型的还有
`logging.max_size_mb: 0` 与 `model_catalog.ttl_hours: 0`(想"每次重取")。

**而同一个仓库里有写对的地方**——用"键在不在"判定,而不是用真值:

`gateway/platforms/base.py:742 @ 863e313`

```python
    if not isinstance(gw, dict) or "max_inbound_media_bytes" not in gw:
```

**两种写法并存**,又一次落在本轮"一个语义两种实现"的谱系里。

> **判据**:配置值的合法域只要包含 `0` / `""` / `[]` / `False` 中任何一个,
> 就**不能**用 `or` 做兜底,必须用"键存在吗"或 `is None` 判定。
> `or` 链把"没设过"和"设成了假值"混为一谈——而对配置来说,
> **"显式关掉"恰恰是用户最需要能表达的意思。**

### ■-15 细节:同一个问题,同一个文件,两个答案

(线索来自 `notes/r8a-raw-tools-config-a` B1,主线已回源复核确认。)

"cua-driver 这个二进制装好了吗"在同一个文件里被回答了两次。**就绪判定**用的是宽解析器:

`hermes_cli/tools_config.py:3273 @ 863e313`

```python
    "cua_driver": lambda: _resolved_cua_driver_cmd() is not None,
```

而这个解析器的 docstring 明说它就是**规范答案**:

`hermes_cli/tools_config.py:761 @ 863e313`

```python
    """Resolve cua-driver exactly as the runtime and Desktop status do."""
```

**安装成功判定却退回了裸 PATH 查找:**

`hermes_cli/tools_config.py:1585 @ 863e313`

```python
        if result.returncode == 0 and shutil.which(driver_cmd):
```

为什么这有区别,被测代码自己解释过——从 Finder/Dock 启动的桌面应用继承的 PATH 很窄,
而上游安装器习惯把二进制放进 `~/.local/bin`:

`tools/computer_use/cua_backend.py:699-703 @ 863e313`

```python
    Desktop apps launched from Finder/Dock often inherit a narrow PATH that
    omits user-local install directories. The upstream cua-driver installer
    commonly places the binary under ``~/.local/bin`` on POSIX systems, so a
    Hermes Desktop/TUI session can otherwise filter out the `computer_use`
    tool even though `hermes computer-use doctor` succeeds from a login shell.
```

**现象**:窄 PATH 的 Desktop 里点"运行设置",安装**其实成功了**,
安装器打印 "cua-driver installing did not complete"、返回 False;
**而同一进程里的就绪标志同时报 ready**。两个界面当着用户的面互相打脸。

**这是本轮"一个语义两处实现"的第六例**,而且是最刺眼的一种:
**规范答案已经存在、还写了 docstring 声明自己是规范答案,安装路径就是没用它。**

### ■-14 细节:两级优先级不能写成一趟循环(主线独立复现)

(线索来自 `notes/r8a-raw-tools-config-b` D-8,主线**独立构造场景跑通复现**。)

provider 选择器要决定光标默认停在哪一行。它有两级判据:**强信号**"这个 provider 当前就是
激活的",**弱信号**"它的 env key 都配齐了,大概是它"。问题是两级判据被写在**同一趟循环**里:

`hermes_cli/tools_config.py:3641-3646 @ 863e313`

```python
    for i, p in enumerate(providers):
        if _is_provider_active(p, config, force_fresh=force_fresh):
            return i
        # Fallback: env vars present → likely configured
        env_vars = p.get("env_vars", [])
        if env_vars and all(get_env_value(v["key"]) for v in env_vars):
```

弱信号在**同一次迭代**里就 `return`,于是**排在前面、只是留着旧 key 的 provider,
会抢在真正激活的 provider 之前命中**——列表顺序压过了信号强度。

**主线复现**:临时 home,`config.yaml` 写 `stt.provider: groq`,
`.env` 里同时留着旧的 `VOICE_TOOLS_OPENAI_KEY` 和在用的 `GROQ_API_KEY`:

```
0 Local Whisper      | active=False | env=[]
1 Nous Subscription  | active=False | env=[]
2 OpenAI             | active=False | env=['VOICE_TOOLS_OPENAI_KEY']
3 Groq               | active=True  | env=['GROQ_API_KEY']
=> cursor index: 2
```

**Groq 是激活的(index 3),光标却停在 OpenAI(index 2)。**

**用户可复述的因果**:以前用 OpenAI 转录、后来切到 Groq(旧 key 没删——没人会删),
再进 `hermes tools` → Speech-to-Text,光标默认落在 OpenAI 上,
**顺手回车确认就把 provider 改回去了**,而他以为自己只是"看了一眼"。

**修法与教训**:两级判据要写成**两趟扫描**——先整轮找强信号,没有再整轮找弱信号。
**把兜底判据放进同一个循环,等于宣布"谁排在前面谁优先",而这从来不是本意。**

### ■-13 细节:稳定键就在旁边,却拿显示名当匹配键

(线索来自 `notes/r8a-raw-tools-config-b` D-12,主线已回源复核确认。)

`hermes tools` 的 provider 选择器要把**插件注册**的后端插进对应类目。五个注入点
**全部拿类目的显示名做匹配**:

`hermes_cli/tools_config.py:3137 @ 863e313`

```python
    if cat.get("name") == "Image Generation":
```

`hermes_cli/tools_config.py:3150 @ 863e313`

```python
    if cat.get("name") == "Web Search & Extract":
```

**而类目字典本来就是用稳定机器键索引的**,显示名只是它旁边的一个展示字段:

`hermes_cli/tools_config.py:484-485 @ 863e313`

```python
    "web": {
        "name": "Web Search & Extract",
```

`"web"` 就在那儿,和 `icon` / `setup_title` / `setup_note` 并列的 `"name"` 显然属于表现层。
**不是"没有稳定标识可用",是"有而不用"。**

**后果的严重程度按类目不同**,而最糟的两个恰好是注释自己点明的:

`hermes_cli/tools_config.py:3145-3147 @ 863e313`

```python
    # Inject plugin-registered web search backends. After PR #25182, this
    # is the SOLE source of provider rows for the Web Search & Extract
    # category — the per-provider hardcoded entries were deleted. The two
```

`hermes_cli/tools_config.py:3140-3141 @ 863e313`

```python
    # Inject plugin-registered video_gen backends. Unlike image_gen,
    # video_gen has NO hardcoded providers — every backend is a plugin.
```

即 `web` 与 `video_gen` **没有任何硬编码 provider 行**,全靠这一次字符串相等注入。
**把 `"Web Search & Extract"` 改成 `"Web Search and Extract"`(或哪天做本地化),
整个类目会变成空的,而且不会有任何报错。**

**这是本轮"跨边界耦合用了不稳定标识"的又一例**,与 ■-12(人格)、■-11(遗留键)同型:
**边界两侧靠一个会因为无关原因变化的值对齐。** 显示名的变化理由(文案、大小写、
本地化、加个 emoji)与"插件该不该注入"**完全无关**——这正是它不能当键的原因。

### ■-12 细节:同一个功能,一个面有 14 个选项,另一个面说"没配置"

`agent.personalities`(给 agent 换人设的预置提示词)**只在 `cli.py` 的默认值里**,
`DEFAULT_CONFIG` 中没有这个键。而网关侧的 `/personality` 命令是这样取值的:

`gateway/slash_commands.py:2502 @ 863e313`

```python
            personalities = cfg_get(config, "agent", "personalities", default={})
```

它拿到的 `config` 来自 `_load_gateway_config()`,而那是一个**原始读**(不合并默认值):

`gateway/run.py:3148-3149 @ 863e313`

```python
    Uses the module-level ``_hermes_home`` (so tests that monkeypatch it
    still see their fixture) and shares the mtime-keyed raw-yaml cache
```

于是取不到任何人格,直接走"未配置"分支:

`gateway/slash_commands.py:2507-2508 @ 863e313`

```python
        if not personalities:
            return t("gateway.personality.none_configured", path=display_hermes_home())
```

**主线实测**(全新 `HERMES_HOME`,`config.yaml` 只有版本号):

| 面 | 人格数 |
|---|---|
| CLI(`CLI_CONFIG`) | **14**(catgirl / kawaii / pirate / shakespeare / noir / uwu …) |
| `load_config()` | **0** |
| 网关原始读 | **0** |

**用户可复述的现象**:在 `hermes chat` 里能用 14 个内置人格;
在聊天平台上敲 `/personality`,机器人回"没有配置任何人格"。
**同一个产品、同一个功能、两种事实。**

**这条同时暴露了第五个读取方**:`_load_gateway_config()`(`gateway/run.py:3145`)——
原始读 + managed 叠加、不合并默认值。加上它,`config.yaml` 的读取方是**五个**,不是四个。

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
(其中 15 个是 `agent.personalities` 及其 14 条人格文本,属数据;其余 13 个是真开关)。

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

## 3.5 主线驳回 / 收窄的子代理结论(复核制度的产出,必须记)

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

### 收窄 · `notes/r8a-raw-config-d` 的"Skill 设置段疑似明文泄露"

**子代理的观察属实,但"泄露"这个定性本轮无法成立,收窄为一条隐患移交。**

属实的部分:`show_config()` 的 Skill 设置段确实**不过脱敏**,直接打印原值:

`hermes_cli/config.py:4453 @ 863e313`

```python
                display_val = str(value) if value else color("(not set)", Colors.DIM)
```

而同一个函数的其他行是脱敏的:

`hermes_cli/config.py:4316 @ 863e313`

```python
    print(f"  Model:        {redact_config_value(config.get('model', 'not set'))}")
```

**同一个函数里两种待遇,这条不一致成立。**

**但"泄露"定不成,三条理由(主线逐条查证)**:

1. **这个声明面不是为密钥设计的。** skill 通过 SKILL.md 的
   `metadata.hermes.config` 声明配置项,字段只有 `key` / `description` /
   `default` / `prompt` —— **没有 `password` 之类的敏感标记**
   (对比 `OPTIONAL_ENV_VARS` 每条都有 `password: bool`)。
   docstring 给的示例是 `wiki.path`(一个路径):

`agent/skill_utils.py:706-710 @ 863e313`

```python
        metadata:
          hermes:
            config:
              - key: wiki.path
                description: Path to the LLM Wiki knowledge base directory
```

2. **skill 的密钥走的是另一条通道**:SKILL.md 的 `env_vars:` 字段
   (`AIRTABLE_API_KEY` / `NOTION_API_KEY` / `MSGRAPH_CLIENT_SECRET` 等),
   落到 `.env`,由别的展示路径处理——不经过这一段。
3. **本基线里没有任何自带 skill 声明过 `metadata.hermes.config`**,
   所以在原装安装上这一段**根本不打印任何东西**。

**定案:不记 ■,收窄为隐患**——残留风险是**第三方 skill** 可以声明一个
形如 `api.token` 的配置项,而这一段既不脱敏、也没有任何机制能识别它是密钥
(schema 里没有可供判断的字段)。移交见 H-9。

**这是本轮第二次收窄子代理结论**(第一次是驳回 F4)。
两次的共同教训:**子代理给出的"疑似 X"必须先问"X 的前提在这个仓库里成立吗"**——
本例中"这个面会承载密钥"这个前提,查三步就否掉了。

---

## 3.6 本轮统一发现的完整清单:同一个语义,这个仓库实现了几份

前面每一条都是单独取证的。摊开放在一起才看得出这不是巧合,而是**这一簇的结构特征**。

| 语义 | 份数 | 位置 | 状态 |
|---|---|---|---|
| **"配好没配好"(某平台是否就绪)** | **8** | `gateway/config.py` / `cron/scheduler.py` / `hermes_cli/gateway.py` / `setup.py` / `web_server.py` / `dump.py` / `tools_config.py` / `status.py` | 只有 `cli.py:9789` 那一份读运行时真值,其余各抄一张 env 表 → ■-31 / ■-35 |
| **`.env` 解析** | **4+** | python-dotenv(`env_loader.py:588`)/ `config._parse_env_value` / `secret_scope.load_env_file` / `managed_scope._parse_env:180` | `secret_scope` 是刻意复用的,`managed_scope` 那份没跟上 → ■-27 |
| **默认值字典** | **2** | `hermes_cli/config_defaults.py:DEFAULT_CONFIG` / `cli.py:441` | 头条:第二份击穿了"单一真源" → ■-10 / ■-11 / ■-12 |
| **配置装载(合并语义)** | **2** | `load_config` 深合并 / `cli.py:599` 一层 `dict.update` | 头条:同一份文件,两种合并 → ■-3 |
| **配对批准入口** | **2 层薄壳 + 1 份核心** | `hermes_cli/pairing.py` / `web_server.py:12335+` → 同一个 `PairingStore` | **核心共用是对的**;分叉只在壳里,而壳零覆盖 → ■-8 / ■-22 |
| **moa 配置写入** | **2** | `web_server.py:6520`(已修)/ `moa_cmd.py:127,147`(未修) | 回归测试只 import 了已修那侧 → ■-21 |
| **单键写入的闸门** | **2** | `config.py:4837+`(三道闸)/ `web_server.py:6921`(一道) | managed 那道是有意分叉;API-key 路由那道无解释 → 移交 H-10 |
| **密钥按键读取** | **2 个平台适配器** | `secret_prompt.py:95`(Windows,对)/ `:116`(POSIX,错) | 核心与适配器之间的契约没写下来 → ■-26 |
| **"Hermes 认识哪些 env 键"** | **2** | `config.py:4095`(活)/ `env_loader.py:55`(死) | 第六例死副本 → ■-29 |
| **注释模板 / 配置文件文案** | **2** | `_SECURITY_COMMENT`/`_FALLBACK_COMMENT`(活)/ `_COMMENTED_SECTIONS`(死且已漂移) | → ■-9 |
| **clarify 超时** | **2 个键 + 2 份默认值** | `clarify.timeout`(遗留)/ `agent.clarify_timeout`(规范) | 自称"单一真源"的函数,实测两面差 780 秒 → ■-11 |
| **cua-driver 装好没有** | **2** | `tools_config.py:1585`(裸 `which`)/ `:3273`(走解析器) | 同一进程两个界面给相反答案 → ■-15 |
| **弃用变量的正名表** | **3** | `doctor.py:258` / `status.py:483` / `gateway/config.py:2432` | 两个诊断命令互相拆台 → ■-32 |
| **skill 禁用名单** | **2** | CLI 侧吃 `load_config()` / 运行时侧读裸 YAML | 配置来源不同(managed 是否叠加) → 存疑,移交 H-12 |

**从这张表里读出来的三件事:**

**一,重复本身不是缺陷,失去同步才是。** 表里没有一行是"作者偷懒复制粘贴";
每一份都有它当时的理由(避免循环 import、避免 bootstrap 期开销、平台差异、
避免 CLI 依赖网关模块)。**代价是把"保持一致"从编译期问题变成了纪律问题**,
而纪律在本簇里的实测通过率是:14 项里**同步失败 12 项**。

**二,失败的形状高度一致:修一处、测一处、另一处静默地留在原地。**
本轮见到四例(§3.2 managed 叶级合并、■-21 moa、■-8 pairing、■-31 status),
其中 ■-31 最刺眼——**修好的那一侧把 bug 的症状逐字写进了注释**。

**三,测试覆盖的形状与缺陷分布正交。** 共用核心测得密(pairing store 29 例),
薄壳几乎不测(4 例);而分叉只可能长在壳里。■-22 与 ■-26 是这条的两个变体。

> **给"造自己的 harness"的一条硬规矩**:允许一个语义有多份实现,
> 但**每多一份,就要同时交付一条"两份必须一致"的可执行断言**——
> 参数化测试、契约测试、启动期自检都行。没有这条断言的第二份实现,
> 应当被视为**未完成的重构**,而不是一个可以合入的现状。

---

## 4. 三笔移交项结论汇总

| 移交项(R7C) | 结论 | 详见 |
|---|---|---|
| ① `status.py` QQBot 环境变量倒置 | ✅ **成立,并更正来源 + 追加"分支体空操作"** | `r8a-01` §3.1 / ▲-4 / ■-1 |
| ② `commands.py` 94 条注册表定义面 | ✅ **94 确认无误**,补齐 94/26/120/111/8 五数关系 | `r8a-01` §3.2 |
| ③ `pairing.py` 与 `web_server.py` 批准入口 | ✅ **结案:不是两套判定,是一份判定 + 两层薄壳**;并记一条封装破坏、一条壳层行为分叉、一条测试盲区 | `r8a-01` §3.3 / `r8a-raw-pairing-and-config-cmd` §2 / ■-6 / ■-8 / ■-22 |

**移交项①的更正**:R7C 写的是"安装向导写新名"。实测新名的来源是
**网关的弃用警告**(`gateway/config.py:2441`)与**官方文档**,不是安装向导。
按本轮并入 `CLAUDE.md` 的新制度,移交项须附锚点文件与一句话现象——
R7C 这条附了锚点文件(`hermes_cli/status.py`),所以本轮没有走偏,只需更正细节;
这正是那条制度想要的效果。

---

## 5. 向后续轮移交(按新制度,逐条附锚点文件 + 一句话现象)

| # | 移交至 | 锚点文件 | 一句话现象 |
|---|---|---|---|
| H-1 | **R8B** | `cli.py:441`(`load_cli_config` 的内联 `defaults`) | **本轮已数清:89 键中 28 个不在 `DEFAULT_CONFIG`(15 个是人格相关,13 个是真开关)**,名单见 ■-10;**未做的是逐个确证这 15 个是否真被读** —— 已证 2 个真被读且收到假警告,其余待查 |
| H-2 | **R8B** | `cli.py:599`(`defaults[key].update(...)`) | 浅合并的**实际影响面**未穷举:哪些从 `CLI_CONFIG` 读的嵌套键**没有**硬编码兜底,那些才是会真出事的 |
| H-3 | **R8C** | `hermes_cli/web_server.py:12320`(`approve_pairing` 路由) | 本轮已读该路由本体并定案 ■-8(与 CLI 的锁定报告不一致);**未查的是它的鉴权层**——`/api/pairing/approve` 由哪一层保证只有已认证管理员可调,需在 R8C 全文精读时确证 |
| H-4 | **R8D** | `hermes_cli/managed_scope.py` | 本轮从 `config.py:3396` 与 `cli.py:624` 两侧读到它,但**没读本体**;managed 层的叶级合并实现与失败姿态未取证 |
| H-5 | **R9/R10** | `ui-tui/src/gatewayTypes.ts:89` 等 TS 侧读取点 | 856 个配置键中有一类**只由 TypeScript 读**;TS 侧是否有自己的默认值(即第三份默认值)未查 |
| H-6 | **R11 复盘** | 本卷 ◇-1 | 105 个零文档键的**清单已在 `data/r8a-config-keys.tsv`**,但未逐条判断"该不该文档化";R11 对表时可直接消费该列 |
| H-9 | **R8D** | `hermes_cli/config.py:4453`(Skill 设置段不脱敏)/ `agent/skill_utils.py:701`(声明 schema 无敏感标记) | 第三方 skill 若声明形如 `api.token` 的配置项,`hermes config` 会明文打印——本基线自带 skill 无人声明该字段,故仅为隐患;修法是给声明 schema 补 `password` 标记,或让该段统一走 `redact_config_value` |
| H-7 | **R8B / R8D** | `hermes_cli/config.py:3065`(`require_readable_config_before_write`) | 该守卫只检查文件**可读**不检查**可解析**;`set/unset_config_value` 各自补了解析检查(见 §3.5),但**是否存在第三个调用方直接 `read_raw_config()` 后落盘**本轮未穷举——若有,坏 YAML 会被静默截断 |
| H-10 | **R8C** | `hermes_cli/web_server.py:6921`(`PUT /api/config` 的三行写入路径) | CLI 的 `set_config_value` 会把 API-key 形状的键改道写 `.env` 并走凭据轮换(`hermes_cli/config.py:4856`),GUI 这条路**全程不经 `_is_env_config_key`**;**未证实的是这条路是否真能被走到**——需查 `_denormalize_config_from_web` 与 `CONFIG_SCHEMA` 是否更早就把 env 键挡在 body 之外。若能走到,等于凭据被写进一个不参与轮换的文件 |
| H-11 | **R8C** | `hermes_cli/web_server.py:12296`(`_pairing_store` 的 docstring 说"不需要 `_profile_scope`")vs `:6914`(`update_config` 用 `with _profile_scope(...)`) | 同一个 dashboard 里**两套 profile 作用域机制**并存:一套传参数、一套装 context。R8C 通读时应清点哪些端点用哪一套、有没有第三套;附带确认「不填 profile」与「填 `default`」指向不同库是否有意(`gateway/pairing.py:424`) |
| H-12 | **R8D** | `hermes_cli/skills_config.py`(CLI 侧吃 `load_config()`)vs `agent/skill_utils.py:401`(运行时侧读裸 YAML) | skill 禁用名单两份实现,且**配置来源不同**——managed 层钉的 `skills.disabled` 疑似只对菜单生效,对运行时无效。子代理标为存疑,主线未取证,R8D 读 skill 子系统时一并确证 |
| H-13 | **R8B/R8C** | `hermes_cli/status.py:508`(`entry.check_fn()`)与 ■-31 已修的孪生 `hermes_cli/gateway.py:5451` | 本轮已定案 status 侧误判;**未做的是把"平台就绪判定"那 8 份逐一对齐核对**(表见 §3.6),确认除 status 外还有几份同样漏了 `is_connected`。这是 §3.6 那张表里份数最多的一项,值得单独一节 |
| H-14 | **R8B** | `hermes_cli/status.py:344-376`(◆ Nous Tool Gateway 整节无 try) | 本轮已定位 8 处可打崩 status 的无保护调用点,并确认 4 个崩溃抵抗用例**全部集中在 xAI OAuth 一个块**;**未做的是给其余 7 处判定"该不该罩"**——排障命令的崩溃姿态本身是一条设计题,值得在 R8B 读 CLI 主干时统一处理 |
