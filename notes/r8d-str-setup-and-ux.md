# r8d · L2 结构级测绘 —— 安装向导、外观交互与其余子命令(簇 R8D-L2-C)

> 层级:**L2 结构级理解**——目标是"知道什么时候该来翻这个文件",不是逐行精读。
> 基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(只读)。
> 溯源约定:凡对代码行为的断言,锚点 `路径:行号 @ 863e313` 单独成行、置于代码块之前;
> 围栏块内为逐字源码摘录,```verify 围栏为可重跑的自检命令。
> 覆盖:`hermes_cli/` 下 **73 个文件 / 36,557 行**(任务书给的估数是"约 74 个 / 35,000 行";
> 实际清点为 73 个 / 36,557 行,逐文件表在第 6 节,73 行一个不少)。

---

## 0. 快读:这 73 个文件到底是什么

一句话:**它们是 `hermes` 这个命令行工具的"外壳",不是 agent 本体。**

R8A 精读了配置解析链(`config.py` / `config_defaults.py`),R8B 精读了 CLI 主干
(`main.py` / `cli.py` / mixin),R8C 精读了 dashboard。本簇是剩下的那一圈:
**把人的意图翻译成 R8A 那两个文件能读懂的形状**,以及一堆围绕它的小工具。

按"往哪写"分,73 个文件只有三种角色:

| 角色 | 典型文件 | 特征 |
|---|---|---|
| **写配置的**(向导) | `setup.py`、`model_setup_flows.py`、`memory_setup.py`… | 终点永远是 `save_config()` / `save_env_value()` 两个函数 |
| **读配置后渲染的**(外观) | `skin_engine.py`、`banner.py`、`tips.py`… | 纯数据驱动,不改状态 |
| **薄子命令**(一个动词一个文件) | 剩下 50 来个 | 平均 200–400 行,`main.py` 按需 import |

体量的错觉值得说破:**6,796 行的向导(`setup.py` + `model_setup_flows.py`)只调用两个写入函数**;
真正的复杂度在"有多少种 provider 要问不同的问题"(18 个 `_model_flow_*`),而不是在写入逻辑。

---

## 1. (a) 向导与账号 —— 17 个文件 / 12,814 行

### 1.1 这组在系统里干什么

这组是**唯一的"合法写配置入口"**。它们把"你用哪个模型 / 哪个终端后端 / 连哪些聊天平台"
这些问题问出来,然后落盘。分两条线:

- **本地向导线**:`setup.py`(总控 + 7 个 section)→ `model_setup_flows.py`(18 个 provider 分支)
  → 平台专用向导(`setup_whatsapp_cloud.py`、`memory_setup.py`)。
- **Nous 账号线**:`portal_cli.py`(人味入口)→ `nous_account.py`(读:额度/权限)
  / `nous_billing.py`(写:买额度)/ `nous_subscription.py`(订阅决定哪些托管工具可用)
  / `nous_auth_keepalive.py`(后台续期)。这条线是**厂商自营的托管服务**,
  与本地 provider 配置最终汇入同一份 `config.yaml`。

### 1.2 问题 1:6,800 行的向导最终写出去的是什么?怎么和 R8A 的配置链衔接?

**结论:只有两个出口 —— `config.yaml` 和 `.env`,而且用的就是 R8A 精读过的那两个函数。**

`setup.py` 在文件头一次性把配置层的门面全部 import 进来,写入侧只有
`save_config` 与 `save_env_value` 两个:

`hermes_cli/setup.py:138-151 @ 863e313`

```python
# Import config helpers
from hermes_cli.config import (
    cfg_get,
    DEFAULT_CONFIG,
    get_hermes_home,
    get_config_path,
    get_env_path,
    load_config,
    save_config,
    save_env_value,
    remove_env_value,
    get_env_value,
    ensure_hermes_home,
)
```

这两个函数的落点在 R8A 已经定死:

`hermes_cli/config.py:694-700 @ 863e313`

```python
def get_config_path() -> Path:
    """Get the main config file path."""
    return get_hermes_home() / "config.yaml"

def get_env_path() -> Path:
    """Get the .env file path (for API keys)."""
    return get_hermes_home() / ".env"
```

`hermes_cli/config.py:3865-3866 @ 863e313`

```python
def save_env_value(key: str, value: str):
    """Save or update a value in ~/.hermes/.env."""
```

**分工是一条清晰的线:结构化的非机密设置进 `config.yaml`,凭据进 `.env`。**
一次 Vercel 沙箱配置就同时踩两边——运行时类型既进 config 字典也镜像进 .env,token 只进 .env:

`hermes_cli/setup.py:784-785 @ 863e313`

```python
    terminal["vercel_runtime"] = runtime
    save_env_value("TERMINAL_VERCEL_RUNTIME", runtime)
```

token 侧三个键全部只进 `.env`:

`hermes_cli/setup.py:829-833 @ 863e313`

```python
        save_env_value("VERCEL_TOKEN", token)
    if project:
        save_env_value("VERCEL_PROJECT_ID", project)
    if team:
        save_env_value("VERCEL_TEAM_ID", team)
```

全簇没有第三个写配置的机制:
向导不自己拼 YAML、不自己写文件句柄,全部走 `hermes_cli.config` 的门面。

*(负结论的搜索面:在 73 个文件内检索 `save_config|save_env_value|open(.*config\.yaml|yaml\.dump`,
写入侧命中只有前两者;`backup.py` 例外——它按字节复制整个 HERMES_HOME,不解析配置,见 3.2。)*

**向导的分段结构**是一张三元组表,`hermes setup <section>` 直接按 key 查表:

`hermes_cli/setup.py:2842-2851 @ 863e313`

```python
SETUP_SECTIONS = [
    ("model", "Model & Provider", setup_model_provider),
    ("tts", "Text-to-Speech", setup_tts),
    ("terminal", "Terminal Backend", setup_terminal_backend),
    ("gateway", "Messaging Platforms (Gateway)", setup_gateway),
    ("tools", "Tools", setup_tools),
    ("telemetry", "Shared Metrics", setup_telemetry),
    ("agent", "Agent Settings", setup_agent_settings),
]
```

**衔接处有一个真实踩过的坑,值得单独记:向导持有的 `config` 字典会过期。**
`setup_model_provider` 调用共享的模型选择器(`select_provider_and_model`,住在 `main.py`),
后者有自己的 load/save 周期;向导若在其后用手里的旧字典 `save_config(config)`,
就会把选择器刚写的东西盖掉。修法是**在原地重灌整个字典**:

`hermes_cli/setup.py:904-913 @ 863e313`

```python
    # Re-sync the wizard's config dict from what cmd_model saved to disk.
    # This is critical: cmd_model writes to disk via its own load/save cycle,
    # and the wizard's final save_config(config) must not overwrite those
    # changes with stale values (#4172). Refresh the dict in place so callers
    # that keep the same object see every section the shared model picker may
    # have changed (model, custom_providers, auxiliary, provider metadata, etc.).
    _refreshed = load_config()
    config.clear()
    config.update(_refreshed)
```

这是典型的**"读-改-写"丢更新**:两条链路各自 load/save 同一份文件。
`config.clear()` + `update()` 而不是 `config = _refreshed`,是因为调用方还捏着同一个对象引用。
造自己的 harness 时,这条线索指向一个更根本的设计选择:
**要么全程单一配置对象贯穿,要么每次写入都是"读-合并-写"**;混着来就会出这个 bug。

### 1.3 `model_setup_flows.py` 是什么:一次拆分的中间态

3,151 行,18 个 `_model_flow_*`,但它**不是一个自洽的模块**——它是从 `main.py` 里搬出来的一半:

`hermes_cli/model_setup_flows.py:1-12 @ 863e313`

```python
"""Per-provider model-selection wizard flows for ``hermes setup`` / ``hermes model``.

Extracted from ``hermes_cli/main.py`` as part of the god-file decomposition
campaign (``~/.hermes/plans/god-file-decomposition.md``, Phase 2 — splitting
main.py handler/flow bodies out of the module). These 18 ``_model_flow_*``
functions are the interactive provider-setup branches dispatched by
``select_provider_and_model`` (which stays in main.py).

Behavior-neutral: each function is lifted verbatim. ``select_provider_and_model``
in main.py re-imports them (``from hermes_cli.model_setup_flows import *``-style
explicit import) so existing call sites — and test monkeypatches that target
``hermes_cli.main._model_flow_*`` — keep resolving against main.py's namespace.
```

**导航含义(这才是 L2 要的):调度器在 `main.py`,分支体在这里,双向依赖靠"函数体内延迟 import"打断。**
要读某个 provider 怎么配,来这里;要读"怎么选到这个 provider 的",回 `main.py`。
`__init__` 期不 import `main.py` 是硬约束——违反它就是 import 循环。

顺带一个可迁移的教训:**拆 god-file 时"行为中性"是要付代价的**。
这里的代价是测试仍然 monkeypatch `hermes_cli.main._model_flow_*`,
所以 `main.py` 必须把这些名字重新 re-export 回自己的命名空间——
拆完之后**两个模块都得知道对方存在**,只是知道的时机不同。

### 1.4 账号线的形状

`portal_cli.py` 只有 246 行,但它是**产品意义上的主入口**:`hermes portal` = 一次性完成
OAuth 登录 → 选 Nous 模型 → 切 provider → 问要不要开 Tool Gateway。
它自己**不实现任何一步**,全部委托给同一个 Nous 流程:

`hermes_cli/model_setup_flows.py:398-399 @ 863e313`

```python
def _model_flow_nous(config, current_model="", args=None):
    """Nous Portal provider: ensure logged in, then pick model."""
```

理由写在 `hermes_cli/setup.py:2853` 的 `_run_portal_one_shot` docstring 里:
让 `hermes portal`、`hermes setup --portal`、首次快速安装、`hermes model` 选 Nous
**四条路径共用一个 Nous 上手流程**,不各写一份。

其余账号文件按"读/写/后台"分得很干净:

- `nous_account.py`(789)—— 只读:权益、余额,带内存缓存(`hashlib` / `threading` / `time`)。
- `nous_billing.py`(675)—— 只写:`/api/billing/*` 四个端点(买额度、轮询扣费、自动续费),
  自称 "fail-loud client"。
- `nous_subscription.py`(1302)—— **决定托管工具能不能用**。它被 `setup.py` 在文件头直接 import
  (`get_nous_subscription_features`),所以向导展示哪些工具是订阅的函数。
- `nous_auth_keepalive.py`(189)—— 后台线程续期长会话。

**平台侧的三个"免手抄 token"客户端**是同一个模式的三种实现,值得放一起看:
`telegram_managed_bot.py`(经 Nous 中介服务创建子机器人,token 一次性取回本地)、
`dingtalk_auth.py`(设备码流 + 终端里画二维码)、`memory_oauth.py`(loopback OAuth,
按约定 `plugins.memory.<provider>.oauth_flow` 分派,模块里不写死任何 provider 名)。
`azure_detect.py`(408)则是**探测**而非认证:给一个 Foundry endpoint,猜它是
OpenAI 式还是 Anthropic 式 transport、有哪些模型、上下文多长。

`setup_hidden_env.py` 只有 56 行,但它定义了一条**产品原则**,直接抄下来:

`hermes_cli/setup_hidden_env.py:1-12 @ 863e313`

```python
"""Which platform env vars the setup surfaces hide.

Every messaging platform ships the same handful of knobs that are either set
for the user later or already correct by default. Listing them on a setup form
turns "paste your bot token" into a five-field interrogation where none of the
answers are discoverable — the Discord card asked for a home channel ID you
need Developer Mode to copy, next to a reply-threading preference.

Hiding them is a *presentation* decision only. The env vars keep working
through ``hermes config set``, ``.env``, and ``config.yaml``; the gateway reads
them exactly as before. This module just says what a new user is asked during
setup.
```

**"隐藏 ≠ 移除"这条边界被显式写下来了**,这是 R8A 配置面(856 个键)可用的关键:
向导只是一张**推荐子集**的视图,配置面本身没缩水。

---

## 2. (b) 外观与交互 —— 19 个文件 / 9,022 行

### 2.1 这组在系统里干什么

名义上是"让终端好看",实际上是**三条不同的东西被目录名混在了一起**:

1. **真·外观**:`skin_engine.py` / `skin_cmd.py` / `banner.py` / `colors.py` / `tips.py` /
   `pets.py` / `journey.py` / `cli_output.py` / `timefmt.py`;
2. **输入通道**:`console_engine.py` / `bang_shell.py` / `curses_ui.py` / `callbacks.py` /
   `pt_input_extras.py` / `completion.py` / `clipboard.py`;
3. **真机制**:`voice.py` / `focus_view.py` / `default_soul.py`(详见 2.5)。

### 2.2 问题 2:`console_engine.py` 的 "Safe" 指什么?

`hermes_cli/console_engine.py:1-6 @ 863e313`

```python
"""Safe Hermes Console command engine.

This module backs ``hermes console`` and is intentionally narrower than the
full Hermes CLI. It exposes a curated set of native adapters that can later be
shared by the dashboard console websocket without becoming a raw shell.
"""
```

**"Safe" = "这不是一个 shell"。** 它挡的不是恶意输入,而是"用户以为自己在 bash 里"。
威胁模型是:dashboard 把一个命令框放到浏览器里,**如果它转发给 shell,拿到 dashboard 就等于拿到主机**。
四道闸,按执行顺序:

**闸 1 —— 拒绝一切 shell 语法。** 管道、重定向、`&&`、命令替换、反引号一律不解析,直接报错:

`hermes_cli/console_engine.py:126-132 @ 863e313`

```python
def _contains_shell_syntax(line: str, tokens: Sequence[str]) -> bool:
    if "$(" in line or "`" in line:
        return True
    shell_tokens = {"|", "||", "&", "&&", ";", ">", ">>", "<", "<<", "2>", "2>>"}
    if any(token in shell_tokens for token in tokens):
        return True
    return any(ch in line for ch in "|<>;")
```

最后一行是**字符级兜底**:即使 `shlex` 把 `|` 吃进了某个 token 内部,原始行里出现 `| < > ;` 就否。
这是"宁可误杀"的取舍——它会让 `sessions search "a>b"` 这类合法参数也被拒。

**闸 2 —— 允许清单,不是拒绝清单。** 命令表 `self.commands` 是构造时注册出来的;
查不到就抛错,`_rejection_for` 只是**在抛错前给一条更好看的错误信息**:

`hermes_cli/console_engine.py:1155-1168 @ 863e313`

```python
    def _resolve_command(self, tokens: Sequence[str]) -> tuple[ConsoleCommand, list[str]]:
        rejected = self._rejection_for(tokens)
        if rejected:
            raise ConsoleCommandError(rejected)

        for size in range(min(len(tokens), 3), 0, -1):
            key = tuple(tokens[:size])
            command = self.commands.get(key)
            if command:
                return command, list(tokens[size:])

        available = [" ".join(path) for path in self.commands]
        probe = " ".join(tokens[:2]) if len(tokens) > 1 else tokens[0]
        suggestions = difflib.get_close_matches(probe, available, n=3, cutoff=0.45)
```

**这个次序很重要**:`_rejection_for` 里那张 `blocked_top`(`hermes_cli/console_engine.py:1176-1199`,
含 `gateway` / `serve` / `login` / `setup` / `uninstall` / `update` / `claw` …)
和 `blocked_pairs`(`config edit`、`mcp serve`、`profile alias`、`kanban daemon` …)
**不是安全边界**——它们只是让"为什么不行"可解释。真正的边界是"没注册就没有"。
安全审查时读错这一点,会得出"把某条从 blocklist 里删掉就危险了"的错误结论。

**闸 3 —— 改动型命令要二次确认。** 处理器不直接执行,先返回 `confirm_required` 交给前端:

`hermes_cli/console_engine.py:510-529 @ 863e313`

```python
            if _contains_shell_syntax(raw_line, tokens):
                raise ConsoleCommandError(
                    "Hermes Console does not run shell syntax. Use one supported "
                    "Hermes command at a time."
                )

            builtin = self._execute_builtin(tokens)
            if builtin is not None:
                if raw_line not in {"history", "clear"}:
                    self.history.append(raw_line)
                return builtin

            command, args = self._resolve_command(tokens)
            if command.mutating and not confirmed:
                return ConsoleResult(
                    "confirm_required",
                    command=raw_line,
                    confirmation_message=command.confirmation
                    or f"Run `{command.usage}`?",
                )

```

**闸 4 —— 输出封顶。** `_cap_output` 按 `output_limit` 截断,防止一条 `sessions list` 把 WebSocket 撑爆:

`hermes_cli/console_engine.py:1233-1234 @ 863e313`

```python
        omitted = len(output) - self.output_limit
        return f"{output[:self.output_limit]}\n... output truncated ({omitted} bytes omitted)"
```

**关于闸 2 那两张"拒绝清单"再补一句证据**,因为它极易被读成安全边界。
`_rejection_for` 是在 `_resolve_command` 里**第一步**被调用的,它返回的只是一段文案:

`hermes_cli/console_engine.py:1172-1176 @ 863e313`

```python
    def _rejection_for(self, tokens: Sequence[str]) -> str:
        first = tokens[0]
        if first.startswith("-"):
            return f"{first} is not available in Hermes Console."
        blocked_top = {
```

把 `gateway` 从这张 `blocked_top` 里删掉,`hermes gateway` 也**不会**因此变得可用——
它照样会掉进下面那句 `Unsupported Hermes Console command`,因为它从没被注册进 `self.commands`。

还有一个**不那么"safe"的实现细节**:命令并非真的调用干净的 API,而是重定向
stdout/stderr、调用 CLI 处理器、捕获文本:

`hermes_cli/console_engine.py:56-59 @ 863e313`

```python
def _capture_output(fn: Callable[[], object]) -> str:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = 0
```

所以 console 拿到的是"CLI 打印出来的字",不是结构化结果——它是**对现有 CLI 的反射式复用**,
代价是必须处理 `SystemExit("msg")` 这种"退出码其实是字符串"的惯用法
(`hermes_cli/console_engine.py:68-70` 的注释写明了不处理会崩 REPL)。

### 2.3 ▲:docstring 说"以后可以给 dashboard 用",而 dashboard 早就在用

上面 docstring 的原话是 `can later be shared by the dashboard console websocket`。
但 `/api/console` 已经在用了:

`hermes_cli/web_server.py:15342-15345 @ 863e313`

```python
    try:
        from hermes_cli.console_engine import HermesConsoleEngine

        engine = HermesConsoleEngine(output_limit=_CONSOLE_OUTPUT_LIMIT)
```

而且 `console_engine.py` **自己另一处注释已经知道这件事**——它为此加了 `lru_cache`:

`hermes_cli/console_engine.py:216-218 @ 863e313`

```python
# subcommand module and build a throwaway argparse tree purely to extract help
# summaries. Nothing about the result changes across engine instances, but the
# dashboard opens a fresh HermesConsoleEngine per /api/console connection, so
```

**同一个文件里,头部 docstring 说"将来",第 218 行的注释说"每次连接都新建一个"。**
按 CLAUDE.md 的整句判定要求:被证伪的是 `can later be` 这个时态,
"narrower than the full CLI"和"without becoming a raw shell"两句仍然成立(见 2.2 四道闸)。
记为 **▲-1(模块 docstring 级)**。

### 2.4 问题 3:主题能改到什么程度?能注入行为吗?

**能改的:颜色、spinner 文案、品牌字符串、工具 emoji、两段 Rich 标记的 ASCII 艺术。
不能改的:任何行为。** 主题就是一个扁平的数据结构,字段是穷举的:

`hermes_cli/skin_engine.py:158-178 @ 863e313`

```python
@dataclass
class SkinConfig:
    """Complete skin configuration."""
    name: str
    description: str = ""
    colors: Dict[str, str] = field(default_factory=dict)
    # Paired palettes for terminals whose background polarity differs from the
    # one `colors` was authored against (mirrors the desktop app's
    # colors/darkColors pairing). A consumer that knows the terminal is light
    # prefers `light_colors` (falling back to `colors`), and vice versa for
    # `dark_colors`. Both merge over the default skin's matching block, so
    # partial user skins still resolve to a complete palette.
    light_colors: Dict[str, str] = field(default_factory=dict)
    dark_colors: Dict[str, str] = field(default_factory=dict)
    spinner: Dict[str, Any] = field(default_factory=dict)
    branding: Dict[str, str] = field(default_factory=dict)
    tool_prefix: str = "┊"
    tool_emojis: Dict[str, str] = field(default_factory=dict)  # per-tool emoji overrides
    banner_logo: str = ""    # Rich-markup ASCII art logo (replaces HERMES_AGENT_LOGO)
    banner_hero: str = ""    # Rich-markup hero art (replaces HERMES_CADUCEUS)
```

加载走 `yaml.safe_load`,**没有任何反序列化到对象的路径**:

`hermes_cli/skin_engine.py:793-803 @ 863e313`

```python
def _load_skin_from_yaml(path: Path) -> Optional[Dict[str, Any]]:
    """Load a skin definition from a YAML file."""
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict) and "name" in data:
            return data
    except Exception as e:
        logger.debug("Failed to load skin from %s: %s", path, e)
    return None
```

构建器只从 dict 里**按名取那 10 个字段**,其余键静默丢弃:

`hermes_cli/skin_engine.py:821-826 @ 863e313`

```python
def _build_skin_config(data: Dict[str, Any]) -> SkinConfig:
    """Build a SkinConfig from a raw dict (built-in or loaded from YAML)."""
    # Start with default values as base for missing keys
    default = _BUILTIN_SKINS["default"]
    skin_name = str(data.get("name", "unknown"))
    color_overrides = _mapping_or_empty(data.get("colors"), section="colors", skin_name=skin_name)
```

三个 mapping 段(colors / spinner / branding)类型不对时 `_mapping_or_empty`
(`hermes_cli/skin_engine.py:806-819`)记 warning 后当空段处理。
所以**多写的字段既不会生效也不会报错**。

**负结论 + 搜索面**:在 `hermes_cli/skin_engine.py` 全文按正则
`\b(exec|eval|compile|__import__|importlib|subprocess|os\.system|pickle|yaml\.load)\b` 检索,**零命中**
(注意用了词边界,避免 `env`**`iron`**`ment` 那类假阳性;`yaml.load` 与 `yaml.safe_load`
因词边界而不会互相误命中,文件里只有后者):

```verify
cd /home/user/hermes-agent && \
grep -nE "\b(exec|eval|compile|__import__|importlib|subprocess|os\.system|pickle|yaml\.load)\b" \
  hermes_cli/skin_engine.py; echo "grep exit=$? (1 = 零命中)"
```

**剩下的注入面只有一层:`banner_logo` / `banner_hero` 是 Rich 标记字符串,
`branding.*` 会进提示符和响应框标题。** 也就是说一个恶意 skin 能做的极限是
**伪装 UI 文案**(比如把提示符改成看起来像 shell、把 agent 名字改掉),
这是欺骗,不是代码执行。对一个"用户自己往 `~/.hermes/skins/` 里丢文件"的信任模型,
这个边界是合适的。

**跨界的部分才是这个模块真正值得记的**:

`hermes_cli/skin_engine.py:8-12 @ 863e313`

```python
This module is the source of truth: it resolves the active skin, and the gateway
pushes the resolved palette to the TUI and desktop (see tui_gateway's
``resolve_skin`` / ``skin.changed``). A skin dropped in ~/.hermes/skins/ therefore
themes all three surfaces at once — the theme analogue of the plugin SDK.
```

配套的 `skin_cmd.py`(108 行)把"改一个颜色"做成了**原地改活动 skin 文件**——
改文件即改 mtime,gateway 的 skin watcher 约 1 秒内重绘所有活着的界面;
内置 skin(无文件)会先 fork 成可编辑副本并带上完整调色板。
**这是本簇里唯一一条"文件系统即 IPC"的热重载链路**,和 R8C 的 managed-files 是同一类设计。

**◎-1:docstring 列了 6 个内置 skin,实际有 9 个。** 逐条为真,只是不全:

`hermes_cli/skin_engine.py:128-137 @ 863e313`

```python
==============

- ``default`` — Classic Hermes gold/kawaii (the current look)
- ``ares``    — Crimson/bronze war-god theme with custom spinner wings
- ``mono``    — Clean grayscale monochrome
- ``slate``   — Cool blue developer-focused theme
- ``daylight`` — Light background theme with dark text and blue accents
- ``warm-lightmode`` — Warm brown/gold text for light terminal backgrounds

USER SKINS
```

```verify
cd /home/user/hermes-agent && python3 -c "
import ast
t = ast.parse(open('hermes_cli/skin_engine.py').read())
for n in ast.walk(t):
    g = None
    if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name): g = n.target.id
    elif isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name): g = n.targets[0].id
    if g == '_BUILTIN_SKINS' and isinstance(n.value, ast.Dict):
        k = [e.value for e in n.value.keys]
        print(len(k), k)
"
```
实测输出 `9 ['default', 'ares', 'mono', 'slate', 'daylight', 'warm-lightmode', 'poseidon', 'sisyphus', 'charizard']`。
按 CLAUDE.md「字面为真就不是 ▲」判为 **◎** 而非 ▲——每一条 bullet 都对,只是漏了三个。
(判定有张力:这是一张挂在 "BUILT-IN SKINS" 标题下、看起来穷举的清单,漏 1/3。
仍取 ◎,以保住 ▲ 的跨轮可比性;把这个张力写在这里是为了让它可被有意推翻。)

### 2.5 问题 6:哪些"外观模块"其实承担了真机制?

**七个。** 按"误判代价"从高到低:

**① `bang_shell.py`(212)—— 名字最像玩具,实则是一条真实的命令执行通道。**
`!git status` 直接在会话工作目录里跑,不经过模型:

`hermes_cli/bang_shell.py:9-16 @ 863e313`

```python
A user-typed command still goes through the SAME dangerous-pattern approval
gate the terminal tool uses (``tools.approval.check_all_command_guards``),
reached here through ``tools.terminal_tool._check_all_guards`` so the CLI
approval callback and Docker host-access handling behave identically.

CLI-only by design: gateway/API/cron sessions have their own shells and no
composer, so :func:`bang_shell_enabled` gates the feature off there.
"""
```

**设计要点有两个,都可迁移**:(a) 它复用 R3 精读过的审批闸,而不是"用户自己敲的就免检"——
**"人类直接输入"不构成豁免理由**,因为剪贴板和终端泄漏都能让人敲下不是自己写的命令;
(b) 它刻意**不进对话历史**——零 token、不扰乱 role 交替、不破坏 prompt cache。
第二点是把"UI 便利"和"上下文经济"同时解决的漂亮取舍。

**② `voice.py`(1060)—— 完全不是外观。** 它是 TUI gateway 的
`voice.record` / `voice.toggle` / `voice.tts` 三个 JSON-RPC 方法的**进程级有状态后端**,
包着 `tools.voice_mode` 与 `tools.tts_tool`,并刻意让可选音频依赖
(sounddevice / faster-whisper / numpy)在**调用时**而不是启动时才 ImportError。

**③ `callbacks.py`(253)—— 审批 UI 的传输层。** 把 terminal_tool 的交互式提示
(clarify / sudo / approval)桥进 prompt_toolkit 事件循环:

`hermes_cli/callbacks.py:1-7 @ 863e313`

```python
"""Interactive prompt callbacks for terminal_tool integration.

These bridge terminal_tool's interactive prompts (clarify, sudo, approval)
into prompt_toolkit's event loop. Each function takes the HermesCLI instance
as its first argument and uses its state (queues, app reference) to coordinate
with the TUI.
"""
```

它还 import 了 `save_env_value_secure` 和 `masked_secret_prompt`——
**"缺 key 时当场问、当场落盘"这条路径经过这里**。改审批 UX 必来此文件。

**④ `default_soul.py`(76)—— 系统提示词的种子。** `DEFAULT_SOUL_MD` 是首次运行时
写进 HERMES_HOME 的 SOUL.md 模板,也就是 agent 的人格底稿;文件里还留着旧安装脚本
(install.sh / install.ps1 / docker/SOUL.md)写过的**遗留样板**,用于识别"用户没改过"。
按行数它排在本簇倒数第九,按语义它属于 R5 的提示词工程。

**⑤ `focus_view.py`(166)—— 会改真配置。** `/focus` 不是自己实现隐藏,而是
把 `tool_progress_mode` 掰到 `"off"` 并**记住用户原来的值**,让既有抑制路径干活,
关闭时逐字还原。它是"新功能复用旧开关"的教科书写法,但代价是**它写的是真状态**——
崩溃在中间会留下一个被改过的 `tool_progress_mode`。

**⑥ `curses_ui.py`(997)—— `hermes tools` / `hermes skills` 的多选界面。**
这两个命令决定 **agent 有哪些工具、加载哪些技能**,所以这个"UI 组件"是
工具集配置的**唯一交互入口**;它自带无 curses 终端的编号式降级路径。

**⑦ `pt_input_extras.py`(163)—— 在启动时给第三方库打补丁。**
往 prompt_toolkit 的全局 `ANSI_SEQUENCES` 表里塞映射,让 Kitty / xterm
`modifyOtherKeys` 协议发出的字节序列解码成 Hermes 已绑定的按键元组。
**它是进程级全局副作用**,单独成模块的理由就是"不 import 整个 CLI 也能测"。

顺带两个"半机制":`clipboard.py`(568)靠 osascript / powershell.exe / wl-paste / xclip
**拉起外部进程**取剪贴板图片(粘贴图片进对话的入口,也是一处子进程面);
`completion.py`(319)**遍历活的 argparse 树**生成 bash/zsh/fish 补全脚本——
和 `console_engine._extracted_summaries` 是同一种反射技巧,同一处真相来源。

剩下真的只是好看:`tips.py`(启动随机提示语料库)、`colors.py`(38 行 ANSI + `NO_COLOR` 支持)、
`timefmt.py`(30 行相对时间)、`cli_output.py`(77 行,把 setup / tools_config / mcp_config /
memory_setup 四份重复的 print/prompt 收敛成一份)。
`pets.py` 与 `journey.py` 介于两者之间:前者会往 config.yaml 写 `display.pet.*` 并从
公共 petdex 图库**下载安装**;后者是 `agent.learning_graph` 的终端渲染视图,数据不在这里。

### 2.6 问题 5:`input_sanitize.py` 防的是什么攻击?

**结论:它不防攻击。这是一个名字比职责大的模块。**

`hermes_cli/input_sanitize.py:1-13 @ 863e313`

```python
"""Sanitize user prompt text leaked from terminal / paste control sequences."""

from __future__ import annotations

import re

_BRACKETED_PASTE_BOUNDARY_START = re.compile(r"(^|[\s\n>:\]\)])\[200~")
_BRACKETED_PASTE_BOUNDARY_END = re.compile(r"\[201~(?=$|[\s\n<\[\(\):;.,!?])")
_BRACKETED_PASTE_DEGRADED_START = re.compile(r"(^|[\s\n>:\]\)])00~")
_BRACKETED_PASTE_DEGRADED_END = re.compile(r"01~(?=$|[\s\n<\[\(\):;.,!?])")

# Corruption signature from desktop bracketed-paste leaks (#62557).
_DESKTOP_PASTE_ARTIFACT = "~[[e"
```

它处理的**只有两件事**,都是"终端解析失败留下的垃圾":

1. **bracketed paste 包裹符泄漏**。终端在粘贴内容前后发 `ESC[200~` / `ESC[201~`
   告诉程序"这段是粘贴的";正常情况下 prompt_toolkit 吃掉它们。解析失败时它们
   **以字面文本形式留在缓冲区**,于是用户的 prompt 里凭空多出 `[200~`。
   canonical 形式(带 ESC 或 `^[`)无条件删,**退化的可见形式**(`[200~` / `00~`)
   只在边界处删——docstring 明说是为了让 `literal[200~tag` 这种真实字面量活下来。
2. **桌面端的 `~[[e` 连续损坏串**(issue #62557),只在**末尾连续出现 ≥4 次**时才截掉。

**它没有做的事(负结论 + 搜索面)**:全文 70 行里没有任何通用 ANSI/CSI/OSC 剥离,
没有 `\x1b` 之外的控制字符处理,没有零宽字符 / BiDi override 处理。
唯一出现的 `\x1b` 是那两个粘贴包裹符的字面量(`hermes_cli/input_sanitize.py:30-31`)。
所以**它挡不住"把 ANSI 转义序列藏进网页/文件、让 agent 读进 prompt"这类攻击**——
那条路的防线在别处(`tools.ansi_strip.strip_ansi`,`hermes_cli/console_engine.py:23` 就 import 了它)。

还有一处**调用面不对称**,值得记而不宜判为缺陷:

```verify
cd /home/user/hermes-agent && \
grep -rn "collapse_repeated_input_artifacts\|sanitize_user_prompt_text" --include=*.py . \
  | grep -v "^./tests/" | grep -v "^./hermes_cli/input_sanitize.py"
```
实测只有两行,都在 `tui_gateway/methods_prompt.py`。也就是说:

`hermes_cli/input_sanitize.py:65-70 @ 863e313`

```python
def sanitize_user_prompt_text(text: str) -> str:
    """Normalize user-authored prompt text before persistence or model input."""
    if not isinstance(text, str) or not text:
        return text
    cleaned = strip_leaked_bracketed_paste_wrappers(text)
    return collapse_repeated_input_artifacts(cleaned)
```

**合成入口 `sanitize_user_prompt_text` 只有 TUI gateway 调**:

`tui_gateway/methods_prompt.py:69-73 @ 863e313`

```python
    from hermes_cli.input_sanitize import sanitize_user_prompt_text

    sid = params.get("session_id", "")
    raw_text = params.get("text", "")
    text = sanitize_user_prompt_text(raw_text) if isinstance(raw_text, str) else raw_text
```

**而经典 CLI 只包了前一半**(该包装函数被 `cli.py:16293` / `16453` / `17413` 三处调用):

`cli.py:3486-3489 @ 863e313`

```python
def _strip_leaked_bracketed_paste_wrappers(text: str) -> str:
    from hermes_cli.input_sanitize import strip_leaked_bracketed_paste_wrappers

    return strip_leaked_bracketed_paste_wrappers(text)
```

`~[[e` 折叠因此在经典 CLI 路径上不生效。**这多半是刻意的**——注释说该损坏签名来自
"desktop bracketed-paste leaks",而桌面端正是走 TUI gateway 的那条路。
记为 **◇-3(结构不对称,附因)**,不判 ■。

---

## 3. (c) 迁移、备份与其余子命令 —— 37 个文件 / 14,721 行

### 3.1 这组在系统里干什么

一句话:**`main.py` 的 37 个"按需 import 的动词"。** 没有共同主题,共同点是形状:
每个文件一个 `hermes <verb>`(或一个跨界面共享的 `/slash`),**import 期无副作用**,
`main.py` 在需要时才挂 argparse 子解析器。这个约定被反复写进 docstring
(`curator.py`、`pets.py` 都明说 "no side effects at import time")——
它是**启动延迟**的设计,不是洁癖:`hermes status` 不该为 `hermes backup` 付 import 代价。

按功能可以再分四小堆:

- **备份 / 迁移**:`backup.py`(1904)、`claw.py`(809,OpenClaw 迁移)、
  `codex_runtime_plugin_migration.py`(757)、`codex_runtime_switch.py`(279)、
  `migrate.py`(115)+ `xai_retirement.py`(274,xAI 2026-05-15 退役检测)。
- **跨界面共享的命令体**:`slash_exec.py`、`write_approval_commands.py`、
  `suggestions_cmd.py`、`blueprint_cmd.py`、`approval_mode.py`、`codex_runtime_switch.py`。
  **这一小堆是本簇最重要的结构模式**,见 4.1。
- **诊断 / 运维**:`dump.py`、`prompt_size.py`、`inventory.py`、`sqlite_safe_read.py`、
  `browser_connect.py`、`build_info.py`。
- **配置类子命令**:`plugins_cmd.py`、`mcp_picker.py`、`mcp_startup.py`、`bundles.py`、
  `fallback_cmd.py`、`moa_cmd.py`、`toolset_validation.py`、`timeouts.py`、`platforms.py`、
  `model_search.py`、`model_cost_guard.py`、`profile_describer.py`、`approvals_suggest.py`、
  `context_switch_guard.py`、`oneshot.py`、`send_cmd.py`、`web_deps.py`。

### 3.2 问题 4:`backup.py` 与 dashboard `/api/ops/import` 是同一套格式吗?备份包里含不含凭据?

**答案一:是同一套,而且是同一份代码——dashboard 端就是 fork 一个 `hermes import` 子进程。**

`hermes_cli/web_server.py:12892-12904 @ 863e313`

```python
@app.post("/api/ops/import")
async def run_import(body: ImportRequest):
    archive = (body.archive or "").strip()
    if not archive:
        raise HTTPException(status_code=400, detail="archive path is required")
    if not os.path.isfile(archive):
        raise HTTPException(status_code=404, detail=f"Archive not found: {archive}")
    args = ["import", archive]
    if body.force:
        args.append("--force")
    try:
        proc = _spawn_hermes_action(args, "import")
    except Exception as exc:
```

`/api/ops/backup` 同理:

`hermes_cli/web_server.py:12841-12843 @ 863e313`

```python
@app.post("/api/ops/backup")
async def run_backup(body: BackupRequest):
    args = ["backup"]
```

**dashboard 在备份这件事上没有自己的实现,只有一层 HTTP 到 CLI 的转发。**
配套还有 `/api/ops/import-upload`(先落盘到暂存目录再走同一条 CLI)与
`/api/ops/backup/download`(把归档当附件下发,带 `_path_is_under` 的目录逃逸检查)。

**答案二:含,而且是明文的。这是刻意设计,不是疏漏。**

三条互相印证的证据:

**(a) 排除表里没有 `.env` / `auth.json`。** 排除的只有 PID 与锁文件:

`hermes_cli/backup.py:82-88 @ 863e313`

```python
    ".db-wal",
    ".db-shm",
    ".db-journal",
)

# File names to skip (runtime state that's meaningless on another machine)
_EXCLUDED_NAMES = {
```

```verify
cd /home/user/hermes-agent && python3 -c "
import ast
t = ast.parse(open('hermes_cli/backup.py').read())
for n in ast.walk(t):
    g = None
    if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name): g = n.target.id
    elif isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name): g = n.targets[0].id
    if g in ('_EXCLUDED_NAMES', '_EXCLUDED_DIRS'):
        vals = sorted(e.value for e in n.value.elts)
        print(g, '->', vals)
        print('   .env excluded?', '.env' in vals, '| auth.json excluded?', 'auth.json' in vals)
"
```
实测两张表都是 `False / False`;`_EXCLUDED_NAMES` 只有
`['.backup.lock', 'cron.pid', 'gateway.pid']`。

**(b) 代码把这三个文件明确当机密对待——restore 时收紧到 0600。**

`hermes_cli/backup.py:127-128 @ 863e313`

```python
# zipfile.open() drops Unix mode bits on extract; restore tightens these to 0600.
_SECRET_FILE_NAMES = {".env", "auth.json", "state.db"}
```

**(c) 它还会把 HERMES_HOME 之外的 provider 配置一起打包,理由写得很直白。**

`hermes_cli/backup.py:130-135 @ 863e313`

```python
# Reserved archive subtree for provider state that lives OUTSIDE HERMES_HOME
# (e.g. ~/.honcho, ~/.hindsight). The active memory provider declares these via
# MemoryProvider.backup_paths(); they're stored under this prefix encoded
# relative to the user's home directory, and restored to their original
# home-relative location on import. Anything not under home is skipped.
_EXTERNAL_PREFIX = "_external/"
```

落盘时对这些外部凭据同样收紧权限:

`hermes_cli/backup.py:934-940 @ 863e313`

```python
                    with zf.open(member) as src, open(target, "wb") as dst:
                        dst.write(src.read())
                    # External provider configs commonly hold credentials.
                    if target.suffix in {".json", ".env", ".conf"} or target.name in _SECRET_FILE_NAMES:
                        try:
                            os.chmod(target, 0o600)
                        except OSError:
```

**归档本身无加密、无口令**——普通 deflate zip:

`hermes_cli/backup.py:701-703 @ 863e313`

```python
    with _atomic_output_path(out_path) as archive_path, zipfile.ZipFile(
        archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6
    ) as zf:
```

甚至**"这是不是一个 Hermes 备份"的判据就是"里面有没有 `.env`"**:

`hermes_cli/backup.py:816-828 @ 863e313`

```python
    markers = {"config.yaml", ".env", "state.db"}
    found = set()
    for n in names:
        # Could be at the root or one level deep (if someone zipped the directory)
        basename = Path(n).name
        if basename in markers:
            found.add(basename)

    if not found:
        return False, (
            "zip does not appear to be a Hermes backup "
            "(no config.yaml, .env, or state databases found)"
        )
```

**安全含义,分清事实与判断:**

- **事实**:`hermes backup` 产出的 zip 是一份**未加密的完整凭据集**
  (所有 provider API key、OAuth token、会话数据库、平台配对信息)。
- **事实**:该 zip 可经 `/api/ops/backup/download` 通过 HTTP 下载。
- **判断(设计取舍,不判 ■)**:这对一个"整机搬家"工具是**合理默认**——
  备份的意义就是能恢复,剔掉凭据的备份恢复不出可用系统;`0600` 与
  `_path_is_under` 说明作者知道这是敏感物。
- **判断(值得移交)**:风险不在 `backup.py`,在**它与 dashboard 认证强度的乘积**。
  "谁能打开 dashboard,谁就能一键下载全部凭据"这个命题的真假,取决于 R8C 测绘的
  `/api/ops/*` 认证链,不取决于本文件。**本簇不下这个结论**,列为移交项 H-C1。

**顺带厘清一个容易搞混的点:`backup.py` 里有三种归档形态,只有第一种能被 `import` 吃。**

| 形态 | 入口 | 形态 | 用途 |
|---|---|---|---|
| 全量 zip | `run_backup` / `_write_full_zip_backup` | `.zip` | `hermes backup`;`run_import` 的唯一输入 |
| 快照 | `create_quick_snapshot` | **时间戳目录**,非 zip | `/snapshot`、`hermes backup --quick`;只抓 `_QUICK_STATE_FILES`(`hermes_cli/backup.py:1090` 那张表,含 `state.db` / `config.yaml` / `.env` / `auth.json` / cron / 配对存储等) |
| 升级前 / 迁移前 | `create_pre_update_backup` / `create_pre_migration_backup` | 目录快照 + 保留策略 | `hermes update` / 配置迁移的安全网(issue #15733) |

另外两处**已被踩过的坑**在注释里保存得很好,值得抄进自己的 harness:
(a) `_EXCLUDED_DIRS` 里的 `.venv` / `node_modules` / `.cache` 不是洁癖,是修
"备份卡了几天 / 426543 个文件"的真实故障;(b) `_IMPORT_SKIP_NAMES`
(`gateway_state.json`、各种 pid / lock / `processes.json`)是**导入侧**的过滤——
把源机器的"网关当时在运行"状态恢复到另一台机器上,会让容器卡在 starting(NS-508 / NS-501);
注释明说"老备份没有这些排除项,所以导入时也要再滤一遍,不能信归档内容"。
**这是一条通用原则:向后兼容的过滤必须放在读侧,写侧的过滤只对未来生效。**

### 3.3 这组里几个值得单独知道的文件

**`sqlite_safe_read.py`(415)—— 一个 POSIX 陷阱的专用防线。** 它的存在理由是
POSIX 建议锁的一个反直觉性质:**同一进程内对同一文件的任意 `close()` 会取消该进程持有的全部锁**。
于是"用 `open(db, 'rb')` 探一下文件头"就能取消另一个线程 `VACUUM` 正持有的 EXCLUSIVE 锁:

`hermes_cli/sqlite_safe_read.py:25-33 @ 863e313`

```python
---------
1. **Never** ``open()`` a database file that may have live connections in this
   process. Ask SQLite instead -- :func:`page_count_bytes` reads the same
   header field via ``PRAGMA``, over the existing connection, taking no new
   descriptor.
2. Byte-level probes are only safe **before any connection exists** for that
   path (first-open validation). Route those through
   :func:`read_header_bytes_preopen`, which refuses once a connection has been
   registered for the path.
```

模块维护一个**连接注册表**并用 `_live_lock` 把"检查 + 系统调用 + 注册表变更"
做成三段原子临界区(open+register / close+unregister / check+read)。
Hermes 的拓扑(gateway、dispatcher、dashboard、TUI、CLI、cron、kanban 都开同一个 `state.db`)
正好是这个 bug 的高发形状。**这是本簇技术含量最高的一个文件**,与 R5 的会话存储直接相关。

**`oneshot.py`(502)—— 一条绕开 `cli.py` 的旁路,且默认免审批。**

`hermes_cli/oneshot.py:219-222 @ 863e313`

```python
    # Auto-approve any shell / tool approvals.  Non-interactive by
    # definition — a prompt would hang forever.
    os.environ["HERMES_YOLO_MODE"] = "1"
    os.environ["HERMES_ACCEPT_HOOKS"] = "1"
```

理由成立(没有 TTY,弹审批就是死锁),但**这是全簇最锋利的一处安全取舍**:
`hermes -z "..."` 在脚本 / CI 里跑,拿的是完整工具集、跳过全部危险命令确认。

同一个文件还有第二个不显然的决定:

`hermes_cli/oneshot.py:230-231 @ 863e313`

```python
    # to its inline/synchronous path. See declare_stateless_channel().
    declare_stateless_channel()
```

一次性模式没有下一轮,若不声明无状态,`delegate_task` 会被强制走后台、
子代理结果**全部被丢弃**(没人排空 `process_registry.completion_queue`)。
**"没有下一轮"会连锁影响异步子系统**,这是设计 harness 时容易漏的一类耦合。

**`dump.py`(449)—— 反面教材的正面写法。** 它生成"可以贴进 Discord/GitHub 求助"的
环境摘要,默认对每个 API key 只打印 `set` / `not set`,只有 `--show-keys` 才打印掩码后的值:

`hermes_cli/dump.py:398-401 @ 863e313`

```python
        val = os.getenv(env_var, "")
        if show_keys and val:
            display = _redact(val)
        else:
```

而掩码本身是转调 `agent.redact.mask_secret`:

`hermes_cli/dump.py:115-123 @ 863e313`

```python
def _redact(value: str) -> str:
    """Redact all but first 4 and last 4 chars.

    Thin wrapper over :func:`agent.redact.mask_secret`. Returns ``""`` for
    an empty value (matches the historical behavior of this helper —
    ``hermes dump`` formats empty values as blank, not as ``"(not set)"``).
    """
    from agent.redact import mask_secret
    return mask_secret(value)
```

它还会检测一种真实误诊:**key 只在当前 shell 里、不在 `.env` 里**,
于是 launchd / systemd / desktop 启动的后台进程看不到它——dump 会显式加注
"shell only",省得支持人员追一个幻影。

**`plugins_cmd.py`(2082)—— 供应链面。** 插件从 Git 仓库克隆进 `~/.hermes/plugins/`,
支持完整 URL 与 `owner/repo` 简写(解析到 GitHub)。信任模型是**明示但不阻断**:

`hermes_cli/plugins_cmd.py:573-577 @ 863e313`

```python
    if git_url.startswith(("http://", "file://")):
        console.print(
            "[yellow]Warning:[/yellow] Using insecure/local URL scheme. "
            "Consider using https:// or git@ for production installs.",
        )
```

即 `http://` 只警告不拒绝;装完后若插件带 `after-install.md` 会用 Rich 渲染出来。
**装插件 = 执行第三方代码**,这条线与 R3 的工具注册、R8C 的 skills/plugins 端点相接。

**`web_deps.py`(153)—— R8C 那堆 `web_routers/` 能存在的原因。**

`hermes_cli/web_deps.py:16-22 @ 863e313`

```python
Design: **late binding, state stays in web_server.**  ``late(name)`` returns a
thin proxy that resolves ``hermes_cli.web_server.<name>`` *at call time*.  This
is cycle-safe (the import happens inside the call, long after both modules are
initialised) and keeps ``web_server``'s runtime behaviour byte-identical:
monkeypatching an attribute on ``web_server`` is still authoritative because
every call re-reads the attribute from the live module.
"""
```

**同一个 god-file 拆分难题的第二种解法**——对比 1.3 的 `model_setup_flows.py`
(靠"函数体内延迟 import"),这里是"每次调用都重新查属性的代理"。
两者的共同约束都是**测试 monkeypatch 必须继续在原模块上生效**;
这条约束比"消除循环 import"更强,也更少被人预料到。

**`approvals_suggest.py`(482)—— 从会话库里挖审批历史。**
Hermes **没有审批决策台账**:`always` 落进 `config.yaml` 的 `command_allowlist`,
`once`/`session` 只在内存里。真正持久的是 `state.db` 里的每一次 `terminal` 工具调用
及其 `role='tool'` 结果(含 `"BLOCKED: User denied …"`)。
这个命令**把会话库当审批日志反查**,给出 allowlist 提案。
**"缺一张表就从别的表反推"是个很实用的模式**,也提醒:会话库里存着比对话更多的东西。

---

## 4. 跨组结构模式(这三组共享的东西)

### 4.1 "共享命令体":同一条 `/slash` 在 CLI / gateway / TUI 上必须完全一致

本簇有 6 个文件是同一个模式的实例:`slash_exec.py`、`write_approval_commands.py`、
`suggestions_cmd.py`、`blueprint_cmd.py`、`approval_mode.py`、`codex_runtime_switch.py`。
形状一模一样:**逻辑住在这里,各界面只负责自己的装饰**(Rich 标记 / emoji+markdown /
`_telegramize_command_mentions`),返回值是一个中立的 `CommandReply`。

`slash_exec.py` 的 docstring 把这个契约写得最清楚:`CommandDef.execute`
(`hermes_cli/commands.py`,R8A 已精读)存的是 `EXECUTORS` 里的一个**键名**,
各界面用 `run_execute(key)` 解析。**注册表存键、不存函数**,
所以命令定义可以被序列化、被 gateway 跨进程使用。

**可迁移原则:凡是"同一个命令在 N 个界面上都要有"的系统,
必须先定义一个界面无关的返回类型,否则 N 份实现一定会漂。**
`suggestions_cmd.py` 的 docstring 直接把理由写成了目的:
"Keeping the logic here (not in cli.py / gateway/run.py) means the two surfaces can never drift."

### 4.2 反射式复用 CLI 表面

三处独立地"遍历活的 argparse 树来获取真相":
`completion.py`(生成 shell 补全)、`console_engine._extracted_summaries`(生成命令摘要)、
以及 console 通过 `_capture_output` 捕获 CLI 的 stdout。
**共同收益**:CLI 加一个子命令,补全和 console 自动跟上,不存在"忘了同步清单"。
**共同代价**:拿到的是**为人排版的文本**,不是结构化数据;
`console_engine` 因此得处理 `SystemExit("msg")`、剥状态栏页脚(`_strip_console_status_footer`)、
剥 ANSI(`tools.ansi_strip`)。这是"复用广度"换"接口质量"的典型交易。

### 4.3 `hermes_cli/__init__.py`:92 行,但是一个进程级副作用

包 `__init__` 在 import 时就跑了 `_ensure_utf8()`:

`hermes_cli/__init__.py:88-92 @ 863e313`

```python
        os.environ.setdefault("PYTHONUTF8", "1")
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")


_ensure_utf8()
```

它把非 UTF-8 的 stdout/stderr(Windows cp1252、latin-1 / C / POSIX locale 的最小 Debian、
树莓派)就地 `reconfigure` 成 UTF-8——因为 CLI 到处打印 `┌│├└─` 和 `⚕`,
在非 UTF-8 编码下会抛 `UnicodeEncodeError` **在命令开始前就崩**(原文举例:全新树莓派上的 `hermes setup`)。
**只有在真的修过流之后才设 PYTHONUTF8/PYTHONIOENCODING**,健康主机上零改动。
它与 `hermes_cli/stdio.py::configure_windows_stdio()` 分层:这里是最早的平台无关兜底,
那边是入口点之后的 Windows 专属加料。

**导航含义:任何"import 了 hermes_cli 就发生了什么"的疑问,答案都在这 92 行里。**

---

## 5. 本簇定案:▲ / ◇ / ■ / ◎

判定说明:本簇没有触及 README / 仓库根 AGENTS.md / website/docs,
以下 ▲ 与 ◎ **全部是模块 docstring 级**(代码内自述),
与历次"作者自绘地图"级 ▲ 分开计数,避免污染跨轮 ▲ 指标。

| 记号 | 内容 | 证据 |
|---|---|---|
| **▲-1** | `console_engine.py` docstring 说 console 引擎 "can later be shared by the dashboard console websocket";dashboard 早已在用,同文件第 218 行的注释还为此加了 `lru_cache`。同句其余两个断言("narrower than the full CLI"、"without becoming a raw shell")成立。 | `hermes_cli/console_engine.py:1-6` vs `hermes_cli/web_server.py:15342-15345` + `hermes_cli/console_engine.py:216-218` |
| **▲-2** | `banner.py` docstring:"Pure display functions with no HermesCLI state dependency." 后半句为真(确实不依赖 `HermesCLI` 实例),**前半句被证伪**:同文件有 `check_for_updates()`(跑 `git ls-remote` / 数 commit,带 6 小时磁盘缓存 `~/.hermes/.update_check`)与 `prefetch_update_check()`(起 daemon 线程),共 7 处 `subprocess.run`。取证见下方 ▲-2 附证。 | `hermes_cli/banner.py:1-4`;`hermes_cli/banner.py:276-281`、`hermes_cli/banner.py:514-521` |
| **◇-1** | `oneshot.py` 的 `-z` 模式**默认 `HERMES_YOLO_MODE=1`**,跳过全部危险命令审批。理由(无 TTY,弹窗即死锁)写在注释里,但这一安全语义未见于本簇任何面向用户的说明文本。 | `hermes_cli/oneshot.py:219-222` |
| **◇-2** | `hermes backup` 产出的 zip **未加密**且**刻意包含** `.env` / `auth.json` / `state.db`,并额外收纳 HERMES_HOME 之外的 provider 凭据目录(`_external/`)。"是不是 Hermes 备份"的判据本身就是"含不含 `.env`"。 | `hermes_cli/backup.py:127-128`、`hermes_cli/backup.py:701-703`、`hermes_cli/backup.py:816-828`、`hermes_cli/backup.py:934-940` |
| **◇-3** | `sanitize_user_prompt_text`(含 `~[[e` 折叠)**只有 TUI gateway 调**;经典 CLI 四处调用点只用前一半 `strip_leaked_bracketed_paste_wrappers`。附因:该损坏签名来自桌面端,而桌面端走 TUI gateway,故大概率刻意。 | `hermes_cli/input_sanitize.py:65-70`;`tui_gateway/methods_prompt.py:69,73`;`cli.py:3486-3489,16293,16453,17413` |
| **◇-4** | `console_engine._rejection_for` 的 `blocked_top` / `blocked_pairs` **不是安全边界**,只是把"未注册"的报错说得更好听——真边界是 `self.commands` 这张允许清单。读成拒绝清单会得出相反的安全结论。 | `hermes_cli/console_engine.py:1155-1168`、`hermes_cli/console_engine.py:1172-1225` |
| **◎-1** | `skin_engine.py` docstring 的 "BUILT-IN SKINS" 清单列 6 个,`_BUILTIN_SKINS` 实有 9 个(多 `poseidon` / `sisyphus` / `charizard`)。逐条为真、不全,按"字面为真就不是 ▲"判 ◎。 | `hermes_cli/skin_engine.py:128-137` + 上文 ```verify``` 块 |

**▲-2 附证。** 被证伪的"Pure display functions"具体指这两个函数:

`hermes_cli/banner.py:276-281 @ 863e313`

```python
def check_for_updates() -> Optional[int]:
    """Check whether a Hermes update is available.

    Two paths: if ``HERMES_REVISION`` is set (nix builds embed it), compare
    it to upstream main via ``git ls-remote``. Otherwise look for a local
    git checkout and count commits behind ``origin/main``.
```

`hermes_cli/banner.py:514-521 @ 863e313`

```python
def prefetch_update_check():
    """Kick off update check in a background daemon thread."""
    def _run():
        global _update_result
        _update_result = check_for_updates()
        _update_check_done.set()
    t = threading.Thread(target=_run, daemon=True)
    t.start()
```

```verify
cd /home/user/hermes-agent && grep -c "subprocess.run(" hermes_cli/banner.py
```
实测 `7`(`grep -c` 数的是**命中行数**,不是出现次数;此处二者相同,行号为
166 / 192 / 241 / 263 / 365 / 423 / 461)。docstring 的后半句("no HermesCLI state dependency")确实成立——
这些函数都不接收 `HermesCLI` 实例;被证伪的只有"Pure display functions"这一半。
**按 CLAUDE.md 的整句判定要求,两半分别定案,不把一句话整体判死。**

**■:本簇 0 条。** 搜索面说明:本轮为 L2 结构级,**未做逐分支精读**,
只在读到的路径上留意缺陷;`backup.py` 的凭据打包、`oneshot.py` 的 YOLO
都判为**有据的设计取舍**而非缺陷(两处都有解释性注释,且都有配套缓解:0600 / 路径逃逸检查 / 无 TTY 前提)。
**不宣称"本簇无缺陷"**——只宣称"在本轮读过的路径上没发现需要判 ■ 的"。

---

## 6. 逐文件角色表(73 个文件,覆盖交代)

### (a) 向导与账号 —— 17 个 / 12,814 行

| 文件 | 行 | 一句话角色 |
|---|---:|---|
| `hermes_cli/setup.py` | 3645 | 交互向导总控:7 个 section 表 + 平台/工具子流程;出口只有 `save_config` / `save_env_value` |
| `hermes_cli/model_setup_flows.py` | 3151 | 18 个 `_model_flow_*` provider 配置分支,从 `main.py` 拆出;调度器仍在 `main.py` |
| `hermes_cli/setup_whatsapp_cloud.py` | 541 | WhatsApp Cloud API 向导:Meta 要的 6 项凭据 + 收件人白名单,自动生成 verify token |
| `hermes_cli/memory_setup.py` | 578 | `hermes memory setup/status`:按插件系统自动发现 memory provider,curses 选择后走其 config schema |
| `hermes_cli/setup_hidden_env.py` | 56 | 声明各平台在 setup 表单里**隐藏**哪些 env 键;纯展示决策,不影响可配置性 |
| `hermes_cli/init_command.py` | 150 | `/init`:构造一条让 agent 自己生成/更新项目 AGENTS.md 的提示词(对标 Codex `/init`) |
| `hermes_cli/nous_subscription.py` | 1302 | Nous 订阅 → 托管工具能力映射;`setup.py` 靠它决定展示哪些工具 |
| `hermes_cli/nous_account.py` | 789 | Nous Portal 账号权益/余额的**只读**归一化查询,带内存缓存 |
| `hermes_cli/nous_billing.py` | 675 | Nous Portal `/api/billing/*` **写**侧客户端:买额度、轮询扣费、自动续费 |
| `hermes_cli/nous_auth_keepalive.py` | 189 | 长会话 Portal 凭据的后台续期线程 |
| `hermes_cli/portal_cli.py` | 246 | `hermes portal`:一次性 Nous 上手(OAuth→选模型→切 provider→Tool Gateway),全部委托 `_model_flow_nous` |
| `hermes_cli/telegram_managed_bot.py` | 358 | Telegram Managed Bots 客户端:经 Nous 中介建子机器人,免手抄 BotFather token |
| `hermes_cli/dingtalk_auth.py` | 291 | 钉钉设备码授权三步流(init→begin→poll),终端里渲染二维码 |
| `hermes_cli/slack_cli.py` | 282 | `hermes slack manifest`:生成把每个 gateway 命令注册成 Slack 原生斜杠命令的 manifest JSON |
| `hermes_cli/vercel_auth.py` | 70 | 报告 Vercel Sandbox 认证状态(`VERCEL_TOKEN`/`PROJECT_ID`/`TEAM_ID` 三元组是否齐全) |
| `hermes_cli/azure_detect.py` | 408 | Azure Foundry endpoint 探测:transport 形态、可用模型、上下文长度 |
| `hermes_cli/memory_oauth.py` | 83 | memory provider OAuth 的 HTTP 路由(由 web_server 挂载);按约定路径分派,不写死 provider 名 |

### (b) 外观与交互 —— 19 个 / 9,022 行

| 文件 | 行 | 一句话角色 |
|---|---:|---|
| `hermes_cli/console_engine.py` | 1636 | `hermes console` 与 dashboard `/api/console` 的命令引擎:允许清单 + 拒 shell 语法 + 改动确认 + 输出封顶 |
| `hermes_cli/skin_engine.py` | 1068 | 主题 SDK 与唯一真相源:`~/.hermes/skins/*.yaml` → CLI/TUI/桌面三端统一调色板;纯数据,无行为注入 |
| `hermes_cli/curses_ui.py` | 997 | curses 多选组件(含无 curses 的编号降级),是 `hermes tools` / `hermes skills` 的交互入口 |
| `hermes_cli/banner.py` | 907 | 欢迎横幅、ASCII 艺术、技能摘要**与更新检查**(`git ls-remote` + 后台线程 + 6h 缓存)|
| `hermes_cli/voice.py` | 1060 | TUI gateway `voice.record/toggle/tts` 的进程级有状态后端;可选音频依赖延迟到调用时才 ImportError |
| `hermes_cli/pets.py` | 502 | `hermes pets`:浏览/安装公共 petdex 宠物、选活动吉祥物(写 `display.pet.*` 到 config.yaml) |
| `hermes_cli/tips.py` | 485 | 启动随机提示语料库(斜杠命令、CLI flag、配置、快捷键、工具、网关、技能、profile) |
| `hermes_cli/journey.py` | 357 | `hermes journey`:技能/记忆时间线条形图 + 星座滚动器;图数据在 `agent.learning_graph` |
| `hermes_cli/focus_view.py` | 166 | `/focus` 精简输出模式:把 `tool_progress_mode` 掰到 `off` 并记住原值,复用既有抑制路径 |
| `hermes_cli/pt_input_extras.py` | 163 | 启动时给 prompt_toolkit 的全局 `ANSI_SEQUENCES` 打补丁,支持 Kitty / xterm `modifyOtherKeys` |
| `hermes_cli/bang_shell.py` | 212 | `!<cmd>` 免模型 shell 模式;走与 terminal 工具**同一套**危险命令审批;仅 CLI 可用 |
| `hermes_cli/callbacks.py` | 253 | 把 terminal_tool 的 clarify/sudo/approval 提示桥进 prompt_toolkit 事件循环;含缺 key 时的落盘路径 |
| `hermes_cli/skin_cmd.py` | 108 | `hermes skin` list/set:原地改活动 skin 的**单个**颜色;改文件即触发 gateway 热重绘 |
| `hermes_cli/colors.py` | 38 | 共享 ANSI 色码 + `should_use_color()`(尊重 `NO_COLOR`、`TERM=dumb`、非 TTY) |
| `hermes_cli/cli_output.py` | 77 | 共享 print_info/success/warning/error + `prompt()`;收敛四个模块里重复的实现 |
| `hermes_cli/clipboard.py` | 568 | 跨平台剪贴板取图(osascript / PowerShell / wl-paste / xclip),无 Python 依赖,走外部进程 |
| `hermes_cli/default_soul.py` | 76 | 首次运行写入 HERMES_HOME 的 SOUL.md 默认模板 + 旧安装脚本的遗留样板(用于识别"未改过") |
| `hermes_cli/timefmt.py` | 30 | 相对时间格式化;从 `main.py` 提出来,好让轻量命令不必 import 整个 CLI |
| `hermes_cli/completion.py` | 319 | 遍历活的 argparse 树生成 bash/zsh/fish 补全脚本,无硬编码命令表 |

### (c) 迁移、备份与其余子命令 —— 37 个 / 14,721 行

| 文件 | 行 | 一句话角色 |
|---|---:|---|
| `hermes_cli/backup.py` | 1904 | `hermes backup` / `import`:全量 zip + 快照目录 + 升级/迁移前备份;含明文凭据,restore 收 0600 |
| `hermes_cli/plugins_cmd.py` | 2082 | `hermes plugins`:从 Git 仓库装/更新/删/列插件;`http://` 只警告不拒 |
| `hermes_cli/claw.py` | 809 | `hermes claw`:OpenClaw 迁移(预览→迁移→清理),支持 preset / 迁移密钥 / 跳过快照 |
| `hermes_cli/curator.py` | 850 | `hermes curator`:`agent/curator.py` + `tools/skill_usage.py` 的薄壳(状态表、触发、暂停、pin) |
| `hermes_cli/inventory.py` | 856 | provider/model 清单的共享底座:dashboard `/api/model/options`、TUI `model.*`、交互 picker 三处共用 |
| `hermes_cli/codex_runtime_plugin_migration.py` | 757 | 把 Hermes 的 MCP 配置与已装插件翻译进 `~/.codex/config.toml`,供 codex 子进程使用 |
| `hermes_cli/codex_runtime_switch.py` | 279 | `/codex-runtime`:在 `auto` 与 `codex_app_server` 间切 `model.openai_runtime`;CLI 与 gateway 共用 |
| `hermes_cli/migrate.py` | 115 | `hermes migrate ...` 的 CLI 处理器,目前只有 `migrate xai` |
| `hermes_cli/xai_retirement.py` | 274 | 纯逻辑:遍历配置字典,报出对 2026-05-15 退役 xAI 模型的引用;无 I/O,doctor 与 migrate 共用 |
| `hermes_cli/oneshot.py` | 502 | `-z` 一次性模式:绕开 `cli.py`,只出最终文本;**默认 `HERMES_YOLO_MODE=1`**,并声明无状态通道 |
| `hermes_cli/send_cmd.py` | 489 | `hermes send`:把 stdin 文本经 `send_message_tool` 发到任一已配置消息平台(给 ops 脚本/cron 用) |
| `hermes_cli/dump.py` | 449 | `hermes dump`:可贴进 issue 的纯文本环境摘要;key 默认只报 set/not set,`--show-keys` 才掩码显示 |
| `hermes_cli/approvals_suggest.py` | 482 | 从 `state.db` 的 terminal 调用与 BLOCKED 结果反推 allowlist 提案(系统没有专门的审批台账) |
| `hermes_cli/browser_connect.py` | 423 | 把 Hermes 挂到本地 Chromium 系 CDP 端口的共享助手(含找空闲调试端口) |
| `hermes_cli/sqlite_safe_read.py` | 415 | 防"任意 close() 取消本进程全部 POSIX 建议锁"的连接注册表 + 安全探测 API |
| `hermes_cli/fallback_cmd.py` | 377 | `hermes fallback`:管理主模型失败(限流/过载/连接错)时的回退 provider 链 |
| `hermes_cli/prompt_size.py` | 375 | `hermes prompt-size`:构造一个真实检查用 agent,报系统提示词各段的字节/字符占比 |
| `hermes_cli/mcp_picker.py` | 322 | `hermes mcp picker`(也是 `hermes mcp` 默认):按当前状态路由到装/启/停/卸/配工具 |
| `hermes_cli/mcp_startup.py` | 260 | CLI/TUI 都安全的后台 MCP 发现助手(线程 + `nullcontext`) |
| `hermes_cli/blueprint_cmd.py` | 318 | `/blueprint` 的跨界面共享实现:对话式填自动化蓝图(dashboard 有表单,聊天界面靠逐条问) |
| `hermes_cli/profile_describer.py` | 288 | 读 profile 的技能/模型/记忆片段,让辅助 LLM 生成 1–2 句 profile 描述 |
| `hermes_cli/slash_exec.py` | 272 | 注册表持有的斜杠命令执行器表:`CommandDef.execute` 存**键名**,各界面用 `run_execute` 解析 |
| `hermes_cli/write_approval_commands.py` | 209 | `/memory`、`/skills` 写审批子命令(list/approve/reject/diff/mode)的 CLI+gateway 共享实现 |
| `hermes_cli/context_switch_guard.py` | 203 | 会话中途换到低上下文 provider 时,提前警告下一轮会触发预压缩(#23767 的一部分) |
| `hermes_cli/bundles.py` | 229 | `hermes bundles`:技能捆绑包(一个 YAML 命名一组技能,一个 `/<bundle>` 斜杠命令加载) |
| `hermes_cli/web_deps.py` | 153 | dashboard 拆分出的 `web_routers/` 的**晚绑定接缝**:`late(name)` 每次调用重查 `web_server.<name>` |
| `hermes_cli/suggestions_cmd.py` | 153 | `/suggestions` 的 CLI+gateway 共享实现(列出/采纳/忽略待处理建议) |
| `hermes_cli/moa_cmd.py` | 152 | Mixture of Agents 的配置助手,复用 `inventory.py` 的 picker 上下文 |
| `hermes_cli/model_cost_guard.py` | 134 | 昂贵模型的二次确认助手(用 `Decimal` 算价),供各模型选择界面共用 |
| `hermes_cli/approval_mode.py` | 87 | 审批模式的持久化命令逻辑;刻意**不重建活 agent**,以保住 prompt cache 前缀 |
| `hermes_cli/platforms.py` | 84 | 平台元数据的单一真相源(`PLATFORMS`),供 skills_config 与 tools_config 共用 |
| `hermes_cli/timeouts.py` | 82 | 解析 `providers.<id>.request_timeout_seconds` / 模型级 `timeout_seconds`,非法值一律回 `None` |
| `hermes_cli/toolset_validation.py` | 74 | 校验 `platform_toolsets` 配置段的纯函数(源于 #38798:迁移把 `hermes-cli` 写成了不存在的 `hermes`) |
| `hermes_cli/input_sanitize.py` | 70 | 清掉泄漏进 prompt 的 bracketed-paste 包裹符与桌面端 `~[[e` 损坏串;**不是通用 ANSI 防线** |
| `hermes_cli/build_info.py` | 51 | 烘焙进镜像的构建元数据;Docker 镜像无 `.git`,`git rev-parse` 取不到时的替代来源 |
| `hermes_cli/model_search.py` | 50 | 模型 id 的 picker 专用搜索别名(如 `k3` ↔ `kimi-…`);与 TS 侧两份同名文件需手工同步 |
| `hermes_cli/__init__.py` | 92 | 包入口;import 时即跑 `_ensure_utf8()`,就地把非 UTF-8 的 stdout/stderr 修成 UTF-8 |

---

## 7. 移交项(带锚点 + 一句话现象)

| 编号 | 锚点文件 | 一句话现象 | 建议归属 |
|---|---|---|---|
| **H-C1** | `hermes_cli/web_server.py:12840-12888`(`/api/ops/backup`、`/api/ops/backup/download`) | 备份 zip 含明文 `.env` + `auth.json`(见 3.2),且可经 dashboard HTTP 直接下载;**"谁能开 dashboard 谁就能拿走全部凭据"是否成立,取决于 R8C 测绘的 `/api/ops/*` 认证链**,本簇未判定 | 与 R8C dashboard 认证结论合并判定 |
| **H-C2** | `hermes_cli/oneshot.py:219-222` | `-z` 模式无条件设 `HERMES_YOLO_MODE=1`;需确认它是否也被 cron / gateway / CI 路径间接触发(本簇只确认了 `-z` 这一条入口,**未做全仓调用面搜索**) | 下一轮做 `HERMES_YOLO_MODE` 全仓写入点搜索 |
| **H-C3** | `hermes_cli/console_engine.py:605`(`_register_broad_cli_surface`) | console 的允许清单是**运行时注册**出来的(反射 argparse + `_register_command_family`),本轮未逐条枚举最终命令集;"console 到底能跑哪些命令"目前只有代码能回答,没有静态清单 | 若要评估 dashboard console 的实际权限面,需实例化引擎导出 `self.commands` |
| **H-C4** | `hermes_cli/model_setup_flows.py:1-12` + `hermes_cli/web_deps.py:16-22` | 同一个 god-file 拆分问题在本仓有**两种互不相同的解法**(延迟 import vs 晚绑定代理),两者共同的真实约束都是"测试 monkeypatch 必须继续在原模块生效" | R12 蓝图的"渐进式拆分"一节可直接引用这组对照 |
| **H-C5** | `hermes_cli/banner.py:276`(`check_for_updates`) | 更新检查会跑 `git ls-remote` 访问上游,缓存在 `~/.hermes/.update_check`(6 小时);本簇未查它在离线/受限网络下的降级路径是否完整 | 与 R8A 的"离线可用性"线索合并 |

---

## 8. 延伸

- 配置写入侧的落点(`save_config` / `save_env_value` 的完整语义、managed scope、denylist):
  `notes/r8a-raw-config-*.md`、`chapters/r8a-configuration-surface.md`。
- `select_provider_and_model` 调度器与 CLI 主干:`notes/r8b-raw-cli-*.md`、
  `chapters/r8b-cli-trunk-and-interaction.md`。
- dashboard 端点与认证链(H-C1 依赖):`notes/r8c-raw-dashboard-auth.md`、
  `chapters/r8c-dashboard-and-web.md`。
- 审批闸本体(`bang_shell` / `callbacks` / `approvals_suggest` 依赖的下层):
  `notes/r3-10-approval-security.md`。
