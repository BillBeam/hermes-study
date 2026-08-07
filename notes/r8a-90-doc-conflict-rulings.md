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
`config.yaml` 的根键校验白名单是**两个集合的并集**:

`hermes_cli/config.py:1881 @ 863e313`

```python
_KNOWN_ROOT_KEYS = frozenset(DEFAULT_CONFIG.keys()) | _EXTRA_KNOWN_ROOT_KEYS
```

第二个集合是手工维护的 **24 个根键**,代码注释说得很坦白:

`hermes_cli/config.py:1850-1854 @ 863e313`

```python
# DEFAULT_CONFIG is the single source of truth for documented roots; keep this
# set derived so new defaults (skills, security, browser, …) are accepted
# automatically. A few optional/legacy roots are valid on disk but intentionally
# absent from DEFAULT_CONFIG (omitted when unused / alternate schema forms).
```

**"documented roots"这个限定词是关键**:`DEFAULT_CONFIG` 是**已文档化根键**的
单一真源,不是**全部合法根键**的真源。这 24 个里包括 `mcp_servers`(MCP 服务器定义)、
`platforms`(每平台设置)、`platform_toolsets`(每平台工具集,由安装向导写)、
`image_gen` / `video_gen`、以及一批网关认的"顶层便捷写法"。

**后果**:它们**没有默认值、没有嵌套键定义**,于是
`mcp_servers` / `platforms` 之下的任何子键**都不在这 856 个里**,
本轮的配置项全表对那几棵子树**零覆盖**。
脚本已增补 `data/r8a-extra-root-keys.tsv` 把这 24 个显式列出来,
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

## ■ 组:代码内部缺陷(只记录不修)

| # | 缺陷 | 锚点 | 怎么会踩到 |
|---|---|---|---|
| ■-1 | status 面板 QQBot 兼容分支**恒假**,且分支体是**空操作** | `hermes_cli/status.py:495` | 照官方文档配新名 → 机器人正常但面板不显示 home 频道 |
| ■-2 | `bedrock.discovery` 三个键**全部未接线** | `hermes_cli/config_defaults.py:789` | 改 `refresh_interval` 无任何效果;默认值撞上硬编码常量,改之前看不出来 |
| ■-3 | 两个装载器合并语义不同(深合并 vs `dict.update`) | `cli.py:599` | 在 CLI/TUI 侧设一个嵌套键,会静默清除其同级默认值 |
| ■-4 | `display.copy_shortcut` 是**全仓唯一一次出现** | `hermes_cli/config_defaults.py:1280` | 用户按注释里列的四个取值去设,永远无效 |
| ■-5 | `NOUS_BASE_URL` 在环境变量清单里,但代码读的是另外两个名字 | `hermes_cli/config_defaults.py:3132` | 安装流程会**主动向用户索要**一个没人读的变量 |
| ■-6 | 配对 CLI 捅穿 `PairingStore` 封装(三个私有成员) | `hermes_cli/pairing.py:81` | 私有方法改名 → 运维者最需要的那条诊断路径炸掉 |
| ■-7 | `OPTIONAL_ENV_VARS` 在 import 时被**原地改写** | `hermes_cli/config.py:5307` | 静态分析(含本项目第一版脚本)只看到 151/308 |

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
清单和文档里的旧名没删。而清单不是死数据——它驱动"缺哪些变量"的盘点:

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

**这条的价值不在缺陷本身,在方法论**:凡"权威清单"类数据结构,先问一句
**"它在运行时会不会被别人改"**。本项目第一版抽取脚本就栽在这里,
差点把一份只有 49% 的清单当成全表交付给 R12。

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
| H-1 | **R8B** | `cli.py:441`(`load_cli_config` 的内联 `defaults`) | 11 个顶层键的第二份默认值,其中 `clarify` 在 `DEFAULT_CONFIG` 里不存在;需查清 CLI 专属键还有哪些、谁读 |
| H-2 | **R8B** | `cli.py:599`(`defaults[key].update(...)`) | 浅合并的**实际影响面**未穷举:哪些从 `CLI_CONFIG` 读的嵌套键**没有**硬编码兜底,那些才是会真出事的 |
| H-3 | **R8C** | `hermes_cli/web_server.py` 的配对批准路由 | 本轮只读了批准处;dashboard 的鉴权层级与 CLI 是否等价,需在 R8C 全文精读时复核 |
| H-4 | **R8D** | `hermes_cli/managed_scope.py` | 本轮从 `config.py:3396` 与 `cli.py:624` 两侧读到它,但**没读本体**;managed 层的叶级合并实现与失败姿态未取证 |
| H-5 | **R9/R10** | `ui-tui/src/gatewayTypes.ts:89` 等 TS 侧读取点 | 856 个配置键中有一类**只由 TypeScript 读**;TS 侧是否有自己的默认值(即第三份默认值)未查 |
| H-6 | **R11 复盘** | 本卷 ◇-1 | 105 个零文档键的**清单已在 `data/r8a-config-keys.tsv`**,但未逐条判断"该不该文档化";R11 对表时可直接消费该列 |
