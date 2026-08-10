# r8a-01 · 范围锚定、R8 四切片、主线独立取证

本篇是 R8A 的主线卷。它记三件事:(1) round=R8 桶怎么切成四片、R8A 边界为什么这么划;
(2) 主线**自己动手**核实的结论(不经子代理);(3) 三笔 R7C 移交项的定案取证过程。
逐段精读的证据在 `notes/r8a-raw-*.md`。

溯源约定:凡断言紧跟 `路径:行号 @ 863e313` 与代码原文块,路径相对 hermes-agent 仓库根,
基线固定 `863e31318553cda8ad61df681d08175364d4164b`。

---

## 1. 范围:R8 切四片,本轮做 R8A

### 1.1 为什么必须切

台账 `round=R8` 桶实测 **268 文件 / 227,803 行**,是 R7C(28,282 行)的 8 倍。
R7C 报告 §10 已判定单轮闭合不了,并给了一版四切片草案。本轮开轮时**逐条复核了那版草案**,
按同一判据重新划线:**哪些文件必须同时摆在眼前,一个机制才讲得清。**

### 1.2 四切片定案(已写入 `scripts/assign_layers.py`,非手改台账)

| 子轮 | 主题 | 文件 | 行数 |
|---|---|---|---|
| **R8A** | **配置面 + 命令注册表**(本轮) | **15** | **21,893** |
| R8B | CLI 主干与子命令树 | 48 | 40,804 |
| R8C | dashboard 与 web 面 | 26 | 36,737 |
| R8D | 其余(kanban / update / proxy / observability…) | 179 | 128,369 |
| — | 合计 | **268** | **227,803** |

合计与切前的 R8 桶**逐位相等**,`round=R8` 残留 0 条。切片规则落在
`scripts/assign_layers.py` 的 RULES 里(首条匹配生效),重生成台账后
`path/kind/lines/status` 四列与切前**逐字节相同**,只有 `layer`/`round` 两列变化。

### 1.3 R8A 的 15 个文件与增删理由

R7C 草案给的 R8A 是 10 文件 / 20,159 行(即 `hermes_cli/` 下全部 `*config*.py`
加 `commands.py`)。**主线复核后加了 5 个文件、没删任何文件**,理由逐条如下:

| 文件 | 行数 | 来源 | 理由 |
|---|---|---|---|
| config_defaults.py | 4313 | 草案 | 配置键的权威定义 |
| config.py | 5434 | 草案 | 解析链总入口 |
| config_migrations.py | 685 | 草案 | schema 版本迁移 |
| tools_config.py | 5452 | 草案 | 工具/toolset 子模式 |
| mcp_config.py | 1135 | 草案 | MCP 子模式 |
| moa_config.py | 509 | 草案 | MoA 子模式 |
| skills_config.py | 202 | 草案 | **`hermes skills` 的开关菜单**(只读写 `skills.disabled` / `skills.platform_disabled`);skill 自带配置项的**声明 schema** 不在这里,在 `agent/skill_utils.py:701` —— 定稿时更正,原写「技能子模式」过宽 |
| fallback_config.py | 101 | 草案 | 供应商回退子模式(**LLM provider 失败转移链**:429/529/503 时换哪个 provider/model)。**与 `config.py` 的 last-known-good 无任何调用关系**——「fallback」在本仓库有三种互不相干的含义 |
| subcommands/config.py | 68 | 草案 | `hermes config` 的 argparse 面 |
| commands.py | 2260 | 草案 | 斜杠命令注册表(R7C 移交) |
| **env_loader.py** | **752** | **新增** | **`.env` → 环境变量这一层不在场,"配置项全表"的「读取点」一列就填不出来**;它是 `OPTIONAL_ENV_VARS` 在 `config.py` 之外**唯一**的另一个导入方 |
| **secret_prompt.py** | **126** | **新增** | `config.py` 在**模块顶部直接导入**它,是配置写入路径里录入密钥的那一半 |
| **status.py** | **696** | **新增** | R7C 移交项①的锚点文件;本身是纯配置读取面板 |
| **pairing.py** | **120** | **新增** | R7C 移交项③的锚点文件(门外那把钥匙) |
| **subcommands/pairing.py** | **40** | **新增** | 同上,是 pairing.py 的 argparse 注册那一半,拆开读没有意义 |

`config.py` 顶部导入 secret_prompt 的实证:

`hermes_cli/config.py:35 @ 863e313`

```python
from hermes_cli.secret_prompt import masked_secret_prompt
```

`env_loader.py` 是 `OPTIONAL_ENV_VARS` 的第二个消费者(全仓仅两处导入):

`hermes_cli/env_loader.py:64 @ 863e313`

```python
    from hermes_cli.config_defaults import OPTIONAL_ENV_VARS
```

**没有纳入 `hermes_cli/profiles.py`(2262 行)**,尽管"profile"听起来像配置分层。
读过它的模块 docstring 后判定它不是配置**解析**的一层,而是**多实例隔离**:每个 profile
是一个独立的 HERMES_HOME 目录,各有自己的 config.yaml。它决定的是"读哪一份配置",
不是"一个键取什么值"。留在 R8B(CLI 主干)更合适。

`hermes_cli/profiles.py:1-8 @ 863e313`

```python
"""
Profile management for multiple isolated Hermes instances.

Each profile is a fully independent HERMES_HOME directory with its own
config.yaml, .env, memory, sessions, skills, gateway, cron, and logs.
Profiles live under ``~/.hermes/profiles/<name>/`` by default.
```

**没有纳入 `hermes_cli/web_server.py`(17,732 行)**:它是 R8C 的主体,整体拉进来会让
R8A 翻倍。但移交项③的第二把钥匙在它里面,故**只读其中配对批准的那几处**、不认领该文件
——这是 R7C 从网关侧读 `commands.py` 消费面的同一种跨界读法。

### 1.4 分层:15 个文件全部 L2 → L1

促升理由与 R6(8 个 memory backend)、R7C(9 个 cron 顶层 .py)同:**轮次主题本体留在 L2,
与「本轮达成 L1 完成标准」直接冲突**。规则写进 `assign_layers.py`,不手改台账。

---

## 2. 主线独立取证(不经子代理)

以下五条由主线亲自读代码、亲自跑代码得出,并作为交叉校验子代理产出的基准。

### 2.1 头条:同一个 config.yaml,两个装载器,合并语义不同

**Hermes 有两个互相独立的配置装载器**,它们读同一个 `~/.hermes/config.yaml`,
但把用户写的嵌套覆盖合并进默认值的方式**不一样**。

装载器一,`hermes_cli/config.py`,**递归深合并**:

`hermes_cli/config.py:2435 @ 863e313`

```python
def _deep_merge(base: dict, override: dict) -> dict:
```

它的 docstring 把设计意图写得很清楚——正是为了不丢兄弟默认值:

`hermes_cli/config.py:2438-2440 @ 863e313`

```python
    Keys in *override* take precedence. If both values are dicts the merge
    recurses, so a user who overrides only ``tts.elevenlabs.voice_id`` will
    keep the default ``tts.elevenlabs.model_id`` intact.
```

装载器二,`cli.py` 的 `load_cli_config()`,自带一份**独立的默认值字面量**:

`cli.py:441 @ 863e313`

```python
    defaults = {
```

合并只用了 `dict.update`,**只有一层**:

`cli.py:599 @ 863e313`

```python
                        defaults[key].update(file_config[key])
```

`dict.update` 对嵌套子树是**整体替换**,不是递归合并。于是同一份 config.yaml,
两个装载器给出不同的结果。**这不是推断,是跑出来的。**

实验:临时 `HERMES_HOME` 下写一份 config.yaml,只设两个嵌套叶子键——

```yaml
compression:
  threshold: 0.75
browser:
  camofox:
    rewrite_loopback_urls: true
```

同一个 HERMES_HOME,两个装载器的结果:

| | `load_config()` | `cli.CLI_CONFIG` |
|---|---|---|
| `compression` 键数 | **28** | **3** |
| `browser.camofox` 键数 | **6** | **1** |
| `browser.camofox.loopback_host_alias` | `host.docker.internal`(默认值保住) | **不存在** |

用户只想打开一个布尔开关,在 CLI/TUI 这一侧却**顺手删掉了同级的全部默认值**;
在网关那一侧则完好无损。

**为什么这条不是"立刻炸"而是"结构性隐患"**——必须说清楚,否则就是夸大:
`loopback_host_alias` 这个具体的键**被一层硬编码兜底救了**:

`tools/browser_camofox.py:248-253 @ 863e313`

```python
def _loopback_rewrite_host(camofox_cfg: Dict[str, Any]) -> str:
    """Return the host alias used when rewriting loopback page URLs."""
    return (
        os.getenv("CAMOFOX_LOOPBACK_HOST_ALIAS", "").strip()
        or str(camofox_cfg.get("loopback_host_alias") or "").strip()
        or "host.docker.internal"
    )
```

第三段 `or "host.docker.internal"` 与默认值字面量**重复**,所以键丢了也读回同一个值。
**同一个字面量在仓库里存在三份**(`hermes_cli/config_defaults.py:409`、`cli.py:466`、这里),
丢一份看不出来。这正是隐患难被发现的原因,也是它危险的原因:
**下一个没有硬编码兜底的键就会真的出事,而且现场看不出是合并语义丢的。**

代码自己承认两套并存:

`cli.py:624-627 @ 863e313`

```python
    # Managed scope: overlay administrator-pinned values LAST so they win over
    # the user's config here too. cli.py builds its config independently of
    # hermes_cli.config._load_config_impl (which has its own managed merge), so
    # without this the entire interactive CLI/TUI surface — skin, display prefs,
```

两份默认值的规模差距同样悬殊:`config_defaults.py` 的 `DEFAULT_CONFIG` 有 **82 个顶层键**,
`cli.py` 的内联 `defaults` 只有 **11 个**,且其中 `clarify` 这个键**在 DEFAULT_CONFIG 里根本不存在**
——它只有 CLI 装载器认得。

**重实现要点**:一个配置系统只能有一个装载器。要是历史原因必须有两个,
至少让它们共用同一个 merge 函数和同一份默认值——否则"同一个键在不同进程里取值不同"
这种 bug 没有任何测试形态能稳定抓住。

### 2.2 解析链的真实顺序(装载器一)

`hermes_cli/config.py:3283 @ 863e313`

```python
def _load_config_impl(*, want_deepcopy: bool) -> Dict[str, Any]:
```

顺序是:**默认值深拷贝 → 用户 config.yaml 深合并 → 归一化 → `${VAR}` 展开 → managed 层深合并**。

`hermes_cli/config.py:3333 @ 863e313`

```python
        config = copy.deepcopy(DEFAULT_CONFIG)
```

**环境变量不是这条链上的一层。** 这是理解整个配置面最关键的一点:
`.env` 由 `env_loader` 灌进 `os.environ`,之后它只以两种方式参与——
(a) 作为 `${VAR}` 展开的取值来源;(b) 被各消费点用 `os.getenv` **各自直接读**。
所以像 `QQ_HOME_CHANNEL` 这样的变量与 `load_config()` **毫无关系**,
这也正是 §3.1 那个 bug 能长期存活的土壤:**它根本不在配置系统的校验范围内。**

managed 层的优先级是**故意反常**的——它排在 `${VAR}` 展开**之后**,
所以用户的 `${VAR}` 压不住管理员钉死的字面量:

`hermes_cli/config.py:3391-3395 @ 863e313`

```python
        # Managed scope wins at the leaf. Applied AFTER user expansion so a user
        # ${VAR} cannot shadow a managed literal: managed values are expanded only
        # against the process environment, never against user-config-defined refs.
        # This deliberately inverts the usual env-over-config precedence for the
        # keys the managed layer pins — see docs/design/managed-scope.md §4.1.
```

### 2.3 解析失败不回退到默认值,回退到"上一次好的"

这是本簇最值得抄走的一条设计。YAML 解析失败时**不**退回 DEFAULT_CONFIG,
而是沿用本进程上一次成功加载的配置:

`hermes_cli/config.py:3348-3356 @ 863e313`

```python
            except Exception as e:
                # Last-known-good fallback (port of openai/codex#31188's
                # invariant: a parse failure in a policy/config file must not
                # silently replace the effective policy with an empty/default
                # one). Falling through to DEFAULT_CONFIG here drops EVERY user
                # override — including security-critical ``approvals.deny``
                # rules, which are supposed to block commands even under yolo.
                # A long-running gateway whose user mid-edits config.yaml into
                # broken YAML would silently lose those rules on the next load.
```

理由是安全的:`approvals.deny` 是拦命令的规则,退回默认值等于**用户手一抖把防线拆了**。
另外损坏的文件会被另存一份 `.bak`,且**绝不原地改写用户的文件**:

`hermes_cli/config.py:45 @ 863e313`

```python
def _backup_corrupt_config(config_path: Path) -> Optional[Path]:
```

### 2.4 缓存签名里为什么要塞一份环境快照

缓存键是 (用户文件 mtime_ns, size, managed 文件 mtime_ns, size),
但**光有文件签名不够**——还要记下这次展开是对着哪些环境变量值做的:

`hermes_cli/config.py:3324-3329 @ 863e313`

```python
            # File signatures match, but the cached expansion is only valid if
            # every ${VAR} it was expanded against still has the same value.
            # Without this, a load_config() that ran before load_hermes_dotenv()
            # pins unexpanded literals (e.g. auxiliary.<task>.api_key) for the
            # life of the process (#58514).
```

**故事**:进程里有人在 `.env` 还没加载时就调了一次 `load_config()`,
那次展开把 `${OPENAI_API_KEY}` 原样留成了字面量并进了缓存;
之后 `.env` 加载了、环境有值了,但文件没变、签名没变,缓存**永远命中**,
于是这个进程到死都拿着一个没展开的假 key。修法是把"展开时依赖的环境值"一起做进缓存有效性判据。

**重实现要点**:凡缓存"计算结果",缓存键必须覆盖**全部输入**,而不只是那个最显眼的输入
(文件)。这类 bug 的现象是"重启就好",最难查。

### 2.5 配置项全表:856 个键 / 151 个环境变量,以及一条方法论教训

用 `scripts/config_table.py` 从 `DEFAULT_CONFIG` 与 `OPTIONAL_ENV_VARS` 的
**字面量 AST** 抽取(不 import、不执行),得到:

- `DEFAULT_CONFIG`:**856 个键**(137 个分支节点 + **719 个叶子键**)
- `OPTIONAL_ENV_VARS`:**151 条**环境变量

`config_defaults.py` 自称是纯数据叶子模块,这是 AST 抽取可行的前提:

`hermes_cli/config_defaults.py:1-5 @ 863e313`

```python
"""Default configuration data for Hermes Agent.

Pure-data leaf module: DEFAULT_CONFIG and OPTIONAL_ENV_VARS, extracted
verbatim from hermes_cli/config.py. Must not import from hermes_cli.config.
"""
```

**方法论教训(主线自己踩的坑,必须记下)**:第一版脚本只扫 `*.py` 统计读取点,
得出"8 个键零读取点"的结论。逐条手工复核后**推翻了其中 7 条**——
它们不是死键,而是**根本不由 Python 读**:

| 键 | 真正的读取点 |
|---|---|
| `display.show_cost` | `ui-tui/src/gatewayTypes.ts:89` |
| `dashboard.show_token_analytics` | `web/src/App.tsx:423` |
| `display.tui_agents_nudge` | `ui-tui/src/app/createGatewayEventHandler.ts:502` |
| `display.tui_auto_resume_recent` | `ui-tui/src/app/createGatewayEventHandler.ts:686` |
| `terminal.font_family` | `apps/desktop/src/app/settings/terminal-font-setting.tsx:25` |

**这是关于这个配置面的一条结构性事实,不只是脚本 bug**:相当一部分配置键
**跨语言边界消费** —— Python 侧只负责把合并好的配置经 `config.get` RPC 发出去,
真正的读取与语义判断发生在 TypeScript 客户端(`ui-tui/`、`web/`、`apps/desktop/`)里。
任何只扫 Python 的"谁读这个键"分析,对这一大类键**结构性失明**。
脚本已改为按语言分列 `py_sites` / `ts_sites`。

**这同时是对 R7C「接线核查要查有没有人调用它的方法」那条规律的补充**:
还要查**是不是同一种语言在调用**。

---

## 3. 三笔 R7C 移交项定案

### 3.1 移交项① · status.py 的 QQBot 环境变量:**成立,且比移交描述更严重**

R7C 的移交描述是"安装向导写新名、status 面板读旧名,且 back-compat 分支恒假"。
主线独立取证后**确认结论、更正来源、并追加一条**。

事实一:status 面板的平台表里,QQBot 的 home 变量写死为**旧名**:

`hermes_cli/status.py:483 @ 863e313`

```python
        "QQBot": ("QQ_APP_ID", "QQ_HOME_CHANNEL"),
```

事实二:紧随其后的"向后兼容"分支,判据是 `home_var` 等于**新名**:

`hermes_cli/status.py:494-496 @ 863e313`

```python
        # Back-compat: QQBot home channel was renamed from QQ_HOME_CHANNEL to QQBOT_HOME_CHANNEL
        if not home_channel and home_var == "QQBOT_HOME_CHANNEL":
            home_channel = os.getenv("QQ_HOME_CHANNEL", "")
```

**这个分支静态恒假**。`home_var` 的取值全部来自上面那张表,而全表 11 个非 None 的 home 变量是:
`TELEGRAM_HOME_CHANNEL` / `DISCORD_HOME_CHANNEL` / `SIGNAL_HOME_CHANNEL` /
`EMAIL_HOME_ADDRESS` / `SMS_HOME_CHANNEL` / `FEISHU_HOME_CHANNEL` / `WECOM_HOME_CHANNEL` /
`WEIXIN_HOME_CHANNEL` / `BLUEBUBBLES_HOME_CHANNEL` / **`QQ_HOME_CHANNEL`** / `YUANBAO_HOME_CHANNEL`
—— **`QQBOT_HOME_CHANNEL` 不在其中**。全文 `QQBOT_HOME_CHANNEL` 只出现 2 次:
上面那条注释和那个恒假判据,**没有第三处**。

**追加发现(R7C 未提):即使该分支能进,它也是个空操作。** 分支体读的是
`QQ_HOME_CHANNEL` —— 与三行之上主路径已经读过的**同一个变量**:

`hermes_cli/status.py:492-493 @ 863e313`

```python
        if home_var:
            home_channel = os.getenv(home_var, "")
```

`home_var` 此时就是 `"QQ_HOME_CHANNEL"`,所以分支体与主路径完全重复。
**这是双重缺陷:判据恒假,且分支体即使执行也无效。** 作者的本意从注释看得很清楚——
主读新名、回退旧名——但那张表始终没跟着改名,于是代码与自己的注释**正好反了**。

事实三:**网关侧方向是对的**,而且它才是真正在跑的那个:

`gateway/config.py:2432-2441 @ 863e313`

```python
        qq_home = getenv("QQBOT_HOME_CHANNEL", "").strip()
        qq_home_name_env = "QQBOT_HOME_CHANNEL_NAME"
        if not qq_home:
            # Back-compat: accept the pre-rename name and log a one-time warning.
            legacy_home = getenv("QQ_HOME_CHANNEL", "").strip()
            if legacy_home:
                qq_home = legacy_home
                qq_home_name_env = "QQ_HOME_CHANNEL_NAME"
                logging.getLogger(__name__).warning(
                    "QQ_HOME_CHANNEL is deprecated; rename to QQBOT_HOME_CHANNEL "
                    "in your .env for consistency with the platform key."
                )
```

**更正 R7C 描述的一处**:"新名"的来源不是安装向导,而是(a)网关这条弃用警告,
(b)官方文档。`website/docs` 里 `QQBOT_HOME_CHANNEL` 出现 3 次、
`QQ_HOME_CHANNEL` 出现 **0 次**:

`website/docs/reference/environment-variables.md:476 @ 863e313`

```
| `QQBOT_HOME_CHANNEL` | QQ user/group openID for cron delivery and notifications |
```

**用户可复述的因果经过**:用户照官方文档配 `QQBOT_HOME_CHANNEL`,或者原本用旧名、
看到网关警告"请改名"后照做 → 机器人一切正常 → 但 `hermes status` 从此**不再显示 home 频道**
(那一行只剩 "configured",`(home: …)` 后缀消失)。**面板惩罚了照做的人**,
而且没有任何报错提示是面板错了,用户只会怀疑自己配错了。

**定案:▲ 成立(代码内部缺陷 ■ 亦成立),并更正来源、追加"分支体空操作"一条。**

### 3.2 移交项② · commands.py 的 94 条注册表:**数字确认,并补齐三组派生视图**

R7C 报称 94 条,主线独立复核**确认**。数法:导入模块后数 `COMMAND_REGISTRY` 的元素个数。

`hermes_cli/commands.py:102 @ 863e313`

```python
COMMAND_REGISTRY: list[CommandDef] = [
```

实测:**94 个 `CommandDef`,94 个互异的规范名,26 个别名,合计 120 个可敲的 token。**

但对外暴露的扁平字典只有 **111** 条——差 9 个,原因是 `gateway_only` 的命令被过滤掉了:

`hermes_cli/commands.py:378-381 @ 863e313`

```python
COMMANDS: dict[str, str] = {}
for _cmd in COMMAND_REGISTRY:
    if not _cmd.gateway_only:
        COMMANDS[f"/{_cmd.name}"] = _build_description(_cmd)
```

实测 `gateway_only` 有 **8 条**(`start` / `topic` / `approve` / `deny` / `sethome` /
`commands` / `restart` / `platform`),带 **1 个**别名,共 9 个 token
—— **120 − 9 = 111**,与 `len(COMMANDS)` 逐位吻合;
按类目再分:Session 43 / Configuration 24 / Tools & Skills 24 / Info 18 / Exit 2 = **111**,亦吻合。

**这才是这张表的真正形态:一份定义 + 多个各自过滤的派生视图**(CLI 扁平字典、
分类字典、子命令补全表、Telegram 菜单)。"94"这个数只对定义面成立,
问"到底有多少条命令"必须先问"对谁而言"。

**定案:■ 无缺陷;R7C 的 94 确认无误。本轮补齐 94 / 26 / 120 / 111 / 8 五个数及其关系。**

### 3.3 移交项③ · 配对批准的两把钥匙

R7C 证明了"门只能从外面开"(批准函数的调用点全在已认证侧),但没读钥匙本身。
CLI 这把钥匙全文 120 行,入口是:

`hermes_cli/pairing.py:11 @ 863e313`

```python
def pairing_command(args):
```

它对 `gateway.pairing.PairingStore` 是**纯外部调用者**,但**捅穿了封装**——
直接调了三个下划线私有成员:

`hermes_cli/pairing.py:81 @ 863e313`

```python
    elif store._is_locked_out(platform):
```

`hermes_cli/pairing.py:86 @ 863e313`

```python
        limits = store._load_json(store._rate_limit_path())
```

为什么要这么干,代码自己解释了——是为了把两种"批准失败"区分开:

`hermes_cli/pairing.py:82-84 @ 863e313`

```python
        # Disambiguate: approve_code returns None for both invalid codes
        # and lockout. Tell the operator it's lockout so they don't chase
        # a "wrong code" rabbit hole (#10195).
```

**取舍读得出来**:`approve_code` 对"码错了"和"被锁定"都返回 `None`
—— 这在**面向攻击者**时是对的(两种失败不可区分,否则失败差异本身就是枚举信道,
R7C 已定案过这一点),但对**运维者**是灾难(操作员对着正确的码干瞪眼)。
作者的解法是让**已认证侧**的 CLI 越过公开接口去读内部状态,把区分度只给运维者。
**这个取舍是对的,实现方式是脆的**:私有方法改名或改签名,CLI 会在运维者最需要它的
那条路径上炸掉,而这条路径几乎不会有人在日常中走到。

**重实现要点**:当"对外不可区分、对内要可区分"同时成立时,应当**显式提供一个
仅限已认证侧的诊断 API**,而不是让调用方去捅私有成员。这是一个该有而没有的接口。

第二把钥匙(dashboard)在 `hermes_cli/web_server.py` 内,本轮只读其批准处,
不认领该文件(它属 R8C)。取证见 `notes/r8a-raw-pairing-key.md`。

---

## 4. 配套测试(行为规格)

见 `notes/r8a-95-tests.md`。主线一次性扫了 **170 个文件 / 3,183 个用例,全部通过、0 失败**。
