# r8a-raw-status —— `hermes_cli/status.py` 全文精读底稿

> 底稿定位：证据层。求全求证，不求好读。
> 溯源约定：凡对 hermes-agent 行为的断言，紧跟 `路径:行号 @ 863e313` 与代码原文块。
> 基线：`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`，只读，全程 `git status --porcelain` 为空。
> 目标文件：`hermes_cli/status.py`，696 行。

## 0. 方法与可复现实验

三次实测都在 `/tmp/.../scratchpad` 下、以 `PYTHONDONTWRITEBYTECODE=1` 运行，
`HERMES_HOME` 指向 scratchpad 下的假家目录，全程未向基线写入任何文件（每次运行后复核
`git -C /home/user/hermes-agent status --porcelain` 为空）：

- `repro_qq.py`：构造 QQ 三种环境变量组合，抓 `hermes status` 的 QQBot 行；
- `repro_crash.py`：6 种损坏 config.yaml / jobs.json / sessions.json，看是否整个崩掉；
- `repro_unguarded.py`：把 `status` 模块里 10 个被调用的外部函数逐个换成抛异常的桩，定位真正没被
  try/except 罩住的调用点。

测试基线：

```
$ PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/hermes_cli/test_status.py -q -p no:cacheprovider
..........                                                               [100%]
10 passed in 1.17s
```

---

## 1. 文件全景

`show_status(args)` 是一个 582 行的顺序过程（115–696），没有中间数据结构，
每一节直接 `print`。唯一的输入开关是 `deep`：

`hermes_cli/status.py:117 @ 863e313`

```python
    deep = getattr(args, 'deep', False)
```

九个输出节，按打印顺序：

| # | 节标题 | 行区间 | 数据来源 |
|---|--------|--------|----------|
| 1 | ◆ Environment | 127–141 | `PROJECT_ROOT` / `sys.version` / `get_env_path()` / `load_config()` / 运行时 provider 解析 |
| 2 | ◆ API Keys | 146–197 | 硬编码 20 条 env 名表 + `get_env_value()`；Anthropic 走 `get_anthropic_key()` |
| 3 | ◆ Auth Providers | 202–339 | `hermes_cli.auth` 的 5 个 `get_*_auth_status*()` 快照函数 |
| 4 | ◆ Nous Tool Gateway | 344–376 | `managed_nous_tools_enabled()` + `get_nous_subscription_features(config)` |
| 5 | ◆ API-Key Providers | 381–417 | 硬编码 6 条 env 元组表 + `get_env_value()`；LM Studio 额外发一次 HTTP 探测 |
| 6 | ◆ Terminal Backend | 422–461 | `config["terminal"]` + `os.getenv()`；vercel 分支调 `describe_vercel_auth()` |
| 7 | ◆ Messaging Platforms | 466–513 | 硬编码 15 条平台表 + `os.getenv()`；再加 `platform_registry.plugin_entries()` |
| 8 | ◆ Gateway Service | 518–549 | `hermes_cli.gateway.get_gateway_runtime_snapshot()` |
| 9 | ◆ Scheduled Jobs / ◆ Sessions | 554–654 | 直接读 `~/.hermes/cron/jobs.json`、`hermes_state.SessionDB`、`sessions.json`、活跃会话注册表 |
| + | ◆ Deep Checks（`--deep`） | 659–690 | `httpx.get(OPENROUTER_MODELS_URL)` + `socket.connect_ex(127.0.0.1:18789)` |

一个值得先记的细节：模块顶端 import 了 `subprocess`，但 `status.py` **全文没有任何一处使用它**
（`grep -n subprocess hermes_cli/status.py` 只有第 11 行这一条）。它存在的唯一目的是给测试提供
一个可 monkeypatch 的锚点：

`hermes_cli/status.py:11 @ 863e313`

```python
import subprocess  # noqa: F401 — re-exported for tests that monkeypatch status.subprocess to guard against regressions
```

即：生产模块为了测试而保留一个未使用的 import，并靠 `# noqa` 压掉 linter。这是"测试探针泄漏进生产
代码"的一个具体样本，后面 §5 会看到它服务的那条测试。

---

## 2. Q1 —— 每一块的数据来源，以及哪些是「自己重新实现了一遍」

### 2.1 三种取值通道，同一个文件里混用

status.py 里同时存在三种读环境变量的方式，语义并不相同：

**(a) `get_env_value(name)`** —— 来自 `hermes_cli.config`，先走 `agent.secret_scope.get_secret`
（profile 作用域感知），再回落 `os.environ`，最后读 `~/.hermes/.env`：

`hermes_cli/config.py:4132-4137 @ 863e313`

```python
    try:
        val = _get_secret(key)
    except UnscopedSecretError:
        raise
    except Exception:
        val = os.environ.get(key)
```

注意 `UnscopedSecretError` 是**向上抛**的，不是吞掉的——这在 §5 会变成一个真实的崩溃面。

**(b) `os.getenv(name, "")`** —— 裸读进程环境，不看 `.env`、不看 profile 作用域。
◆ Messaging Platforms、◆ Terminal Backend、◆ Deep Checks 三节全用这个。

`hermes_cli/status.py:488 @ 863e313`

```python
        token = os.getenv(token_var, "")
```

`hermes_cli/status.py:664 @ 863e313`

```python
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
```

**(c) 专用解析函数** —— 只有 Anthropic 一家享受：

`hermes_cli/status.py:194-197 @ 863e313`

```python
    from hermes_cli.auth import get_anthropic_key
    anthropic_value = get_anthropic_key()
    anthropic_display = redact_key(anthropic_value)
    print(f"  {'Anthropic':<12}  {check_mark(bool(anthropic_value))} {anthropic_display}")
```

(b) 与 (a) 在**标准 CLI 路径下**大体等价，因为 `hermes_cli/main.py:697` 在 import 期就把
`~/.hermes/.env` 灌进了 `os.environ`（`load_hermes_dotenv(project_env=PROJECT_ROOT / ".env")`）。
但两者在 profile 多路复用作用域下不等价：`get_env_value` 是 scope-checked 的，`os.getenv` 不是。
同一份状态报告里一半行走 scope-aware 路径、一半走裸路径，这个不一致本身就是设计缺陷。
`hermes_cli/status.py:664` 的 `os.getenv("OPENROUTER_API_KEY")` 与第 151 行同一个 key 走
`get_env_value` 尤其刺眼——同一个变量，同一次运行，两节用两种通道读。

### 2.2 status 自己重新实现的判定逻辑（本轮统一发现「同一语义多份实现」）

#### (1) API Key 名表：仓库有权威声明，status 手抄了一份，还抄漏了

`hermes_cli/status.py:150-171 @ 863e313`

```python
    keys: dict[str, str | tuple[str, ...]] = {
        "OpenRouter": "OPENROUTER_API_KEY",
        "OpenAI": "OPENAI_API_KEY",
        "Anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN"),
        "Google / Gemini": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        "DeepSeek": "DEEPSEEK_API_KEY",
        "xAI / Grok": "XAI_API_KEY",
        "NVIDIA NIM": "NVIDIA_API_KEY",
        "Z.AI / GLM": "GLM_API_KEY",
        "Kimi": "KIMI_API_KEY",
        "StepFun Step Plan": "STEPFUN_API_KEY",
        "MiniMax": "MINIMAX_API_KEY",
        "MiniMax-CN": "MINIMAX_CN_API_KEY",
        "DeepInfra": "DEEPINFRA_API_KEY",
        "Firecrawl": "FIRECRAWL_API_KEY",
        "Tavily": "TAVILY_API_KEY",
        "Browser Use": "BROWSER_USE_API_KEY",  # Optional — local browser works without this
        "Browserbase": "BROWSERBASE_API_KEY",  # Optional — direct credentials only
        "FAL": "FAL_KEY",
        "ElevenLabs": "ELEVENLABS_API_KEY",
        "GitHub": "GITHUB_TOKEN",
    }
```

权威来源在 `hermes_cli/providers.py`：每个 provider 的 `ProviderDef.api_key_env_vars` 是
「检查这个 provider 的 API key 时该看哪些 env」的单一定义。Z.AI 的声明是三个名字：

`hermes_cli/providers.py:107 @ 863e313`

```python
        extra_env_vars=("GLM_API_KEY", "ZAI_API_KEY", "Z_AI_API_KEY"),
```

status 的 `keys` 表里 Z.AI 只有 `GLM_API_KEY`（第 158 行）。同一个文件往下 200 行，
◆ API-Key Providers 节又把同一份三元组**再抄了一遍**，这次抄全了：

`hermes_cli/status.py:384-400 @ 863e313`

```python
    apikey_providers = {
        "Z.AI / GLM":       ("GLM_API_KEY", "ZAI_API_KEY", "Z_AI_API_KEY"),
        "Kimi / Moonshot":  ("KIMI_API_KEY",),
        "StepFun Step Plan": ("STEPFUN_API_KEY",),
        "MiniMax":          ("MINIMAX_API_KEY",),
        "MiniMax (China)":  ("MINIMAX_CN_API_KEY",),
        "DeepInfra":        ("DEEPINFRA_API_KEY",),
    }
    for pname, env_vars in apikey_providers.items():
        key_val = ""
        for ev in env_vars:
            key_val = get_env_value(ev) or ""
            if key_val:
                break
        configured = bool(key_val)
        label = "configured" if configured else "not configured (run: hermes model)"
        print(f"  {pname:<16} {check_mark(configured)} {label}")
```

于是 Z.AI / GLM、Kimi、StepFun、MiniMax、MiniMax-CN、DeepInfra 这 6 家在**同一次输出里出现两次**，
两次判定用的 env 集合不同。实测（`ZAI_API_KEY=zai-1234567890abcdef`，其余未设）：

```
  Provider:     Z.AI / GLM
  Z.AI / GLM    ✗ (not set)          ← ◆ API Keys（只看 GLM_API_KEY）
  Kimi          ✗ (not set)
  Z.AI / GLM       ✓ configured      ← ◆ API-Key Providers（三元组）
  Kimi / Moonshot  ✗ not configured (run: hermes model)
```

同一份状态报告自相矛盾：上半页说没配，下半页说配了，第一节的 `Provider:` 行还显示运行时选中的
就是 Z.AI / GLM。这是「同一语义多份实现」在**单个文件内部**就已经发散的实例。

顺带：`keys` 表里的 `"Anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN")` 是**死数据**——
循环第一件事就是把它跳过：

`hermes_cli/status.py:183-190 @ 863e313`

```python
    for name, env_ref in keys.items():
        # Anthropic already has a dedicated lookup below; keep that as the
        # single source of truth (it also resolves OAuth tokens), skip here
        # so we don't print two "Anthropic" rows.
        if name == "Anthropic":
            continue
        value = _resolve_env(env_ref)
        has_key = bool(value)
```

真正生效的 `get_anthropic_key()` 查的是三个名字（多一个 `CLAUDE_CODE_OAUTH_TOKEN`），且用
dotenv 优先的 `get_env_value_prefer_dotenv`：

`hermes_cli/auth.py:548-565 @ 863e313`

```python
def get_anthropic_key() -> str:
    """Return the first usable Anthropic credential, or ``""``.

    Checks both the ``.env`` file and the process environment, preferring
    ``~/.hermes/.env`` so a deliberate key rotation isn't shadowed by a stale
    shell export (matches the api-key resolution path — see #20591).  The
    order mirrors the ``PROVIDER_REGISTRY["anthropic"].api_key_env_vars``
    tuple:

        ANTHROPIC_API_KEY -> ANTHROPIC_TOKEN -> CLAUDE_CODE_OAUTH_TOKEN
    """
    from hermes_cli.config import get_env_value_prefer_dotenv

    for var in PROVIDER_REGISTRY["anthropic"].api_key_env_vars:
        value = get_env_value_prefer_dotenv(var) or ""
        if value:
            return value
    return ""
```

修法很说明问题：发现表里那行是错的之后，选择是「在循环里 `continue` 跳过它」而不是「删掉它」。
错误的规格被留在表里，只是不再被执行——下一个读表的人仍然会以为 Anthropic 只有两个 env 名。

#### (2) 消息平台就绪表：全仓第 7 份实现，且是唯一读旧名的那份

`hermes_cli/status.py:469-485 @ 863e313`

```python
    platforms = {
        "Telegram": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_HOME_CHANNEL"),
        "Discord": ("DISCORD_BOT_TOKEN", "DISCORD_HOME_CHANNEL"),
        "WhatsApp": ("WHATSAPP_ENABLED", None),
        "Signal": ("SIGNAL_HTTP_URL", "SIGNAL_HOME_CHANNEL"),
        "Slack": ("SLACK_BOT_TOKEN", None),
        "Email": ("EMAIL_ADDRESS", "EMAIL_HOME_ADDRESS"),
        "SMS": ("TWILIO_ACCOUNT_SID", "SMS_HOME_CHANNEL"),
        "DingTalk": ("DINGTALK_CLIENT_ID", None),
        "Feishu": ("FEISHU_APP_ID", "FEISHU_HOME_CHANNEL"),
        "WeCom": ("WECOM_BOT_ID", "WECOM_HOME_CHANNEL"),
        "WeCom Callback": ("WECOM_CALLBACK_CORP_ID", None),
        "Weixin": ("WEIXIN_ACCOUNT_ID", "WEIXIN_HOME_CHANNEL"),
        "BlueBubbles": ("BLUEBUBBLES_SERVER_URL", "BLUEBUBBLES_HOME_CHANNEL"),
        "QQBot": ("QQ_APP_ID", "QQ_HOME_CHANNEL"),
        "Yuanbao": ("YUANBAO_APP_ID", "YUANBAO_HOME_CHANNEL"),
    }
```

「某个平台配没配好」这个问题，全仓至少有 8 处各自作答（下表按「读什么」列出，
以 QQBot 为切片，因为它是 §4 那个缺陷的载体）：

| # | 位置 | 判定方式 | QQ 相关读法 |
|---|------|----------|-------------|
| 1 | `gateway/config.py` ~2415–2455 | **运行时真值**：构造 `GatewayConfig.platforms` | `QQ_APP_ID` 或 `QQ_CLIENT_SECRET`；home 用 `QQBOT_HOME_CHANNEL`，回落 `QQ_HOME_CHANNEL` 并告警 |
| 2 | `cron/scheduler.py` ~270–290 | cron 投递目标解析 | 主 `QQBOT_HOME_CHANNEL`，legacy 映射到 `QQ_HOME_CHANNEL` |
| 3 | `hermes_cli/gateway.py` `_platform_status()` ~5431–5500 | 优先 `is_connected`，回落 `check_fn`，再按 `token_var` + 平台特例 | `token_var="QQ_APP_ID"`；交互项含 `QQBOT_HOME_CHANNEL` |
| 4 | `hermes_cli/setup.py` ~2217 | "缺 home channel" 提醒 | `QQ_APP_ID` 且 (`QQBOT_HOME_CHANNEL` 或 `QQ_HOME_CHANNEL`) 都无 |
| 5 | `hermes_cli/web_server.py` ~7793 | Web UI 平台卡片 | `required_env = (QQ_APP_ID, QQ_CLIENT_SECRET)`，不含 home |
| 6 | `hermes_cli/dump.py` ~186–201 | `hermes dump` 的"已启用平台" | `os.getenv("QQ_APP_ID")` |
| 7 | `hermes_cli/tools_config.py` ~2083–2086 | 工具集按平台裁剪 | `get_env_value("QQ_APP_ID")` |
| 8 | **`hermes_cli/status.py:483`** | `hermes status` 平台行 | `QQ_APP_ID` + **只读 `QQ_HOME_CHANNEL`（旧名）** |

（另有 `cli.py` ~9789–9808 的旧 CLI 面板，它是唯一**不重抄表**、直接读 `load_gateway_config()`
真值的实现——见 §3.4。）

逐条证据：

`gateway/config.py:2415 @ 863e313`

```python
    qq_app_id = getenv("QQ_APP_ID")
```

`cron/scheduler.py:278 @ 863e313`

```python
    "qqbot": "QQBOT_HOME_CHANNEL",
```

`hermes_cli/setup.py:2217-2220 @ 863e313`

```python
        if get_env_value("QQ_APP_ID") and not (
            get_env_value("QQBOT_HOME_CHANNEL") or get_env_value("QQ_HOME_CHANNEL")
        ):
            missing_home.append("QQBot")
```

`hermes_cli/web_server.py:7793-7799 @ 863e313`

```python
    "qqbot": {
        "name": "QQ Bot",
        "description": "Connect Hermes to a QQ Bot from the QQ Open Platform.",
        "docs_url": "https://q.qq.com",
        "env_vars": ("QQ_APP_ID", "QQ_CLIENT_SECRET", "QQ_ALLOWED_USERS"),
        "required_env": ("QQ_APP_ID", "QQ_CLIENT_SECRET"),
    },
```

`hermes_cli/dump.py:199 @ 863e313`

```python
        "qqbot": "QQ_APP_ID",
```

`hermes_cli/tools_config.py:2085 @ 863e313`

```python
    if get_env_value("QQ_APP_ID"):
```

#### (3) 插件平台就绪判定：仓库已经把这个坑填过一次，status 没跟上

status 对插件注册的平台，直接调 `check_fn()` 并把结果印成 "configured"：

`hermes_cli/status.py:505-513 @ 863e313`

```python
    try:
        from gateway.platform_registry import platform_registry
        for entry in platform_registry.plugin_entries():
            configured = entry.check_fn()
            status_str = "configured" if configured else "not configured"
            label = entry.label
            print(f"  {label:<12}  {check_mark(configured)} {status_str} (plugin)")
    except Exception:
        pass
```

但 `check_fn` 的契约是「**依赖装没装**」，不是「配没配」：

`gateway/platform_registry.py:53 @ 863e313`

```python
    # Returns True when the platform's dependencies are available.
```

而 `hermes_cli/gateway.py` 里同样的展示需求，**已经把这个坑填掉了**，注释还把踩坑经过写清楚了：

`hermes_cli/gateway.py:5440 @ 863e313`

```python
        # Prefer is_connected (checks both env and config.yaml) over
```

`hermes_cli/gateway.py:5431-5459 @ 863e313`

```python
def _platform_status(platform: dict) -> str:
    """Return a plain-text status string for a platform.

    Returns uncolored text so it can safely be embedded in
    curses menu items (ANSI codes break width calculation).
    """
    entry = platform.get("_registry_entry")
    if entry is not None:
        configured = False
        # Prefer is_connected (checks both env and config.yaml) over
        # check_fn (typically just dependency / env presence).
        if entry.is_connected is not None:
            try:
                from gateway.config import PlatformConfig

                synthetic = PlatformConfig(enabled=True)
                configured = bool(entry.is_connected(synthetic))
            except Exception:
                configured = False
        else:
            # No is_connected hook — fall back to check_fn as a coarse
            # "are deps present" gate. Don't fall back when is_connected
            # is defined and returned False; that would let "SDK is
            # installed" override "no token configured" and incorrectly
            # report the platform as ready.
            try:
                configured = bool(entry.check_fn())
            except Exception:
                configured = False
        return "configured" if configured else "not configured"
```

"that would let 'SDK is installed' override 'no token configured' and incorrectly report the
platform as ready" —— 这句话逐字描述的就是 `status.py:508` 现在的行为。同一个仓库、同一个错误、
一处修了一处没修，正是「同一语义多份实现」的代价。

而且 `check_fn` 各插件的实现口径本身就不统一：ntfy 和 IRC 检查的是配置，Telegram/Discord 检查的是依赖。

`plugins/platforms/ntfy/adapter.py:149-159 @ 863e313`

```python
def check_requirements() -> bool:
    """Check whether the ntfy adapter is installable and minimally configured.

    Reads ``NTFY_TOPIC`` directly to avoid the cost of a full
    ``load_gateway_config()`` (which also writes to ``os.environ``) on
    every pre-flight check.
    """
    if not HTTPX_AVAILABLE:
        return False
    topic = os.getenv("NTFY_TOPIC", "").strip()
    return bool(topic)
```

`plugins/platforms/irc/adapter.py:541-551 @ 863e313`

```python
def check_requirements() -> bool:
    """Check if IRC is configured.

    Only requires the server and channel — no external pip packages needed.
    """
    server = os.getenv("IRC_SERVER", "")
    channel = os.getenv("IRC_CHANNEL", "")
    # Also accept config.yaml-only configuration (no env vars).
    # The gateway passes PlatformConfig; we just check env for the
    # hermes setup / requirements check path.
    return bool(server and channel)
```

#### (4) 「一次只读诊断」在这里破功：status 可能触发 pip 安装

`plugin_entries()` 会先把所有延迟注册的插件**实际 import 一遍**：

`gateway/platform_registry.py:266-269 @ 863e313`

```python
    def plugin_entries(self) -> list[PlatformEntry]:
        """Return only plugin-registered platform entries."""
        self._resolve_all()
        return [e for e in self._entries.values() if e.source == "plugin"]
```

然后对每个 entry 调 `check_fn()`。而 Telegram 的 `check_fn` 在依赖缺失时会**主动跑 lazy install**：

`plugins/platforms/telegram/adapter.py:395-412 @ 863e313`

```python
def check_telegram_requirements() -> bool:
    """Check if Telegram dependencies are available.

    If python-telegram-bot is missing, attempts to lazy-install it via
    ``tools.lazy_deps.ensure("platform.telegram")``. After a successful
    install, re-imports the SDK and flips ``TELEGRAM_AVAILABLE`` to True
    so the adapter's class-level type aliases get rebound.
    """
    global TELEGRAM_AVAILABLE, Update, Bot, Message, InlineKeyboardButton
    global InlineKeyboardMarkup, LinkPreviewOptions, Application
    global CommandHandler, CallbackQueryHandler, TelegramMessageHandler
    global ContextTypes, filters, ParseMode, ChatType, HTTPXRequest
    if TELEGRAM_AVAILABLE:
        return True
    try:
        from tools.lazy_deps import ensure as _lazy_ensure
        _lazy_ensure("platform.telegram", prompt=False)
    except Exception:
```

`plugins/platforms/telegram/adapter.py:411 @ 863e313`

```python
        _lazy_ensure("platform.telegram", prompt=False)
```

`prompt=False` 意味着**不问用户**。对照本文件自己在 Auth 节的纪律，反差非常刺眼——那里为了
「只读」专门换了一个不刷新 token 的快照函数：

`hermes_cli/status.py:205-222 @ 863e313`

```python
    try:
        from hermes_cli.auth import (
            get_nous_auth_status_local,
            get_codex_auth_status,
            get_qwen_auth_status,
            get_minimax_oauth_auth_status,
        )
        # Read-only display: use the refresh-free snapshot so `hermes status`
        # never performs an OAuth refresh or burns a single-use refresh token.
        nous_status = get_nous_auth_status_local()
        codex_status = get_codex_auth_status()
        qwen_status = get_qwen_auth_status()
        minimax_status = get_minimax_oauth_auth_status()
    except Exception:
        nous_status = {}
        codex_status = {}
        qwen_status = {}
        minimax_status = {}
```

`hermes_cli/auth.py:6724-6731 @ 863e313`

```python
def get_nous_auth_status_local() -> Dict[str, Any]:
    """Refresh-free Nous auth snapshot for read-only display surfaces.

    Unlike :func:`get_nous_auth_status`, this NEVER calls
    ``resolve_nous_runtime_credentials()`` and therefore never performs an
    OAuth refresh POST or consumes a single-use refresh token. It reports the
    persisted auth-store state, classifying the access token with a local
    invoke-JWT decode only.
```

即：同一个函数里，第 205 行处刻意避免消耗一次性 refresh token，第 508 行处却可能装包。
「只读诊断」这条纪律在这个文件里只贯彻了一半。

#### (5) `_effective_provider_label()`：又一份「自定义 base_url 该叫什么」的判定

`hermes_cli/status.py:85-109 @ 863e313`

```python
def _effective_provider_label() -> str:
    """Return the provider label matching current CLI runtime resolution."""
    requested = resolve_requested_provider()
    try:
        effective = resolve_provider(requested)
    except AuthError:
        effective = requested or "auto"

    if effective == "openrouter":
        # A custom endpoint may be configured either in config.yaml
        # (model.base_url — the canonical location; the runtime treats
        # config.yaml as the single source of truth) or via the legacy
        # OPENAI_BASE_URL env var. Either way, labeling it "OpenRouter"
        # is misleading (#3296).
        config_base_url = ""
        try:
            model_cfg = load_config().get("model")
            if isinstance(model_cfg, dict):
                config_base_url = (model_cfg.get("base_url") or "").strip()
        except Exception:
            pass
        if config_base_url or get_env_value("OPENAI_BASE_URL"):
            effective = "custom"

    return provider_label(effective)
```

两个观察：
1. 这个函数在 `show_status` 里被调用**两次**（第 141 行打 Provider 行、第 405 行判断要不要探测
   LM Studio），每次都重跑 `resolve_requested_provider()` + `resolve_provider()`，`openrouter`
   分支下还各多一次 `load_config()`。
2. 第 405 行的判定是拿**显示用标签字符串**比对：

`hermes_cli/status.py:405-417 @ 863e313`

```python
    if _effective_provider_label() == "LM Studio":
        from hermes_cli.models import probe_lmstudio_models
        model_cfg = config.get("model")
        base = (model_cfg.get("base_url") if isinstance(model_cfg, dict) else None) or get_env_value("LM_BASE_URL") or "http://127.0.0.1:1234/v1"
        try:
            models = probe_lmstudio_models(api_key=get_env_value("LM_API_KEY") or "", base_url=base, timeout=1.5)
            if models is None:
                ok, msg = False, f"unreachable at {base}"
            else:
                ok, msg = True, f"reachable ({len(models)} model(s)) at {base}"
        except AuthError:
            ok, msg = False, "auth rejected — set LM_API_KEY"
        print(f"  {'LM Studio':<16} {check_mark(ok)} {msg}")
```

`"LM Studio"` 这个字面量来自 `hermes_cli/providers.py:424` 的标签映射（`"lmstudio": "LM Studio"`）。
把控制流挂在 i18n/展示层字符串上——改一次显示名（哪怕只是加个后缀），这段探测就静默失效。
正确的写法是比对 provider id `"lmstudio"`。

#### (6) `_configured_model_label()`：第三份 model 字段形状解析

`hermes_cli/status.py:73-82 @ 863e313`

```python
def _configured_model_label(config: dict) -> str:
    """Return the configured default model from config.yaml."""
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        model = (model_cfg.get("default") or model_cfg.get("name") or "").strip()
    elif isinstance(model_cfg, str):
        model = model_cfg.strip()
    else:
        model = ""
    return model or "(not set)"
```

`model` 既可以是 str 也可以是 dict、dict 里 `default` 和 `name` 二选一——这套形状规则在
`_effective_provider_label()`（第 101–103 行）、第 407–408 行（LM Studio base_url）里
各自又展开了一遍局部版本，三处都是手写 `isinstance` 分支。

---

## 3. Q2 —— 就绪判定逐条，以及「显示就绪但跑不起来」

### 3.1 判定条件总表

| 显示对象 | 「就绪」的确切条件 | 行号 |
|---|---|---|
| `.env file` | `get_env_path().exists()` | 133 |
| 每个 API Key 行 | `bool(get_env_value(name))`（元组取首个非空） | 173–192 |
| Anthropic | `bool(get_anthropic_key())`（3 个 env，dotenv 优先） | 194–197 |
| Nous Portal | `nous_status["logged_in"]` 或 portal account info 的 `logged_in` | 237–240 |
| Codex / Qwen / MiniMax / xAI OAuth | 对应快照的 `bool(...["logged_in"])` | 277 / 291 / 306 / 328 |
| Nous Tool Gateway 各能力 | `feature.available or feature.active or feature.managed_by_nous` | 364 |
| API-Key Providers 各家 | 元组里任一 `get_env_value` 非空 | 392–400 |
| LM Studio | `probe_lmstudio_models(...) is not None`（HTTP 探测，1.5s） | 409–417 |
| Vercel SDK | `importlib.util.find_spec("vercel") is not None` | 450 |
| Vercel Auth | `describe_vercel_auth().ok` | 449 |
| Sudo | `bool(os.getenv("SUDO_PASSWORD"))` | 460–461 |
| 15 个内建消息平台 | `bool(os.getenv(token_var, ""))` —— **仅第一个 env 非空** | 487–489 |
| 插件平台 | `entry.check_fn()` —— 语义是「依赖装了」 | 508 |
| Gateway | `get_gateway_runtime_snapshot().running` | 524–526 |

### 3.2 「显示就绪但实际跑不起来」——三个实测确认的例子

内建平台行的判定只有一句：

`hermes_cli/status.py:487-502 @ 863e313`

```python
    for name, (token_var, home_var) in platforms.items():
        token = os.getenv(token_var, "")
        has_token = bool(token)
        
        home_channel = ""
        if home_var:
            home_channel = os.getenv(home_var, "")
        # Back-compat: QQBot home channel was renamed from QQ_HOME_CHANNEL to QQBOT_HOME_CHANNEL
        if not home_channel and home_var == "QQBOT_HOME_CHANNEL":
            home_channel = os.getenv("QQ_HOME_CHANNEL", "")
        
        status = "configured" if has_token else "not configured"
        if home_channel:
            status += f" (home: {home_channel})"
        
        print(f"  {name:<12}  {check_mark(has_token)} {status}")
```

`bool(token)` 而已。三个被实测确认的假阳性（同一次运行的实际输出）：

```
--- D: WHATSAPP_ENABLED=false / EMAIL_ADDRESS only / SIGNAL_HTTP_URL only ---
  WhatsApp      ✓ configured
  Signal        ✓ configured
  Email         ✓ configured
```

**(a) `WHATSAPP_ENABLED=false` → 显示 ✓ configured。**
网关的真值判定是布尔解析，并且专门处理了显式关闭：

`gateway/config.py:1890-1891 @ 863e313`

```python
    whatsapp_enabled = is_truthy_value(getenv("WHATSAPP_ENABLED", ""))
    whatsapp_disabled_explicitly = getenv("WHATSAPP_ENABLED", "").lower() in {"false", "0", "no"}
```

`hermes gateway` 的展示层也把它当特例处理，还区分了「已启用但未配对」：

`hermes_cli/gateway.py:5462-5471 @ 863e313`

```python
    token_var = platform.get("token_var", "")
    if not token_var:
        return "not configured"
    val = get_env_value(token_var)
    if token_var == "WHATSAPP_ENABLED":
        if val and val.lower() == "true":
            session_file = get_hermes_home() / "whatsapp" / "session" / "creds.json"
            if session_file.exists():
                return "configured + paired"
            return "enabled, not paired"
```

status 用 `bool("false")` == True，直接报 ✓。同样的 bug 也存在于
`hermes_cli/tools_config.py:2083`（`if get_env_value("WHATSAPP_ENABLED"):`）和
`hermes_cli/dump.py:187`（`os.getenv(env)`）。三份实现，同一个错。

**(b) 只设 `EMAIL_ADDRESS` → 显示 ✓ configured**，而邮件适配器还需要密码 + IMAP + SMTP；
**(c) 只设 `SIGNAL_HTTP_URL` → 显示 ✓ configured**，而 Signal 还需要 `SIGNAL_ACCOUNT`。
`hermes gateway` 的同一判定有「partially configured」这个中间态：

`hermes_cli/gateway.py:5473-5488 @ 863e313`

```python
    if platform.get("key") == "signal":
        account = get_env_value("SIGNAL_ACCOUNT")
        if val and account:
            return "configured"
        if val or account:
            return "partially configured"
        return "not configured"
    if platform.get("key") == "email":
        pwd = get_env_value("EMAIL_PASSWORD")
        imap = get_env_value("EMAIL_IMAP_HOST")
        smtp = get_env_value("EMAIL_SMTP_HOST")
        if all([val, pwd, imap, smtp]):
            return "configured"
        if any([val, pwd, imap, smtp]):
            return "partially configured"
        return "not configured"
```

**(d) 插件平台**：§2.2(3) 已证，`check_fn()` 对 Telegram/Discord 语义是「SDK 装了」，
装了 SDK 但没设 token 也会印 ✓ configured (plugin)。

### 3.3 「显示未就绪但实际能跑」

**Z.AI / GLM**：只设 `ZAI_API_KEY` 或 `Z_AI_API_KEY` 时，◆ API Keys 节报 `✗ (not set)`
（第 158 行只查 `GLM_API_KEY`），但运行时按 `hermes_cli/providers.py:107` 的三元组是能取到 key 的。
§2.2(1) 的实测输出已证。

### 3.4 唯一一份「读真值」的实现，可以当反例参照

`cli.py` 的旧 CLI 面板不抄 env 表，直接问 `load_gateway_config()` 要构造好的
`config.platforms`，并从中取 home channel：

`cli.py:9789 @ 863e313`

```python
            config = load_gateway_config()
```

`cli.py:9802 @ 863e313`

```python
                pconfig = config.platforms.get(platform)
```

这条路径不可能出现 `WHATSAPP_ENABLED=false` 报 ✓ 的问题，也不可能读错 home channel 变量名——
因为它读的就是运行时那份对象。status 之所以没这么做，可以猜是为了避免 `load_gateway_config()`
的开销/副作用（ntfy 的注释提到它「also writes to os.environ」），但代价是把 8 份判定散在全仓。

---

## 4. Q3 —— QQBot 环境变量缺陷全案

### 4.1 两个名字：谁是真的

**`QQBOT_HOME_CHANNEL` 是当前正名；`QQ_HOME_CHANNEL` 是改名前的旧名，全仓已判定为 deprecated。**

运行时（网关构造 `HomeChannel` 的地方）主读正名、回落旧名并打告警：

`gateway/config.py:2432-2443 @ 863e313`

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

cron 调度器的 home-target 表也是正名为主、旧名为 legacy 映射：

`cron/scheduler.py:277-289 @ 863e313`

```python
    "bluebubbles": "BLUEBUBBLES_HOME_CHANNEL",
    "qqbot": "QQBOT_HOME_CHANNEL",
    "whatsapp": "WHATSAPP_HOME_CHANNEL",
    "whatsapp_cloud": "WHATSAPP_CLOUD_HOME_CHANNEL",
}

# Legacy env var names kept for back-compat.  Each entry is the current
# primary env var → the previous name.  _get_home_target_chat_id falls
# back to the legacy name if the primary is unset, so users who set the
# old name before the rename keep working until they migrate.
_LEGACY_HOME_TARGET_ENV_VARS = {
    "QQBOT_HOME_CHANNEL": "QQ_HOME_CHANNEL",
}
```

`OPTIONAL_ENV_VARS`（合法 env 名白名单）两个都列，并注明旧名的身份：

`hermes_cli/config.py:288-289 @ 863e313`

```python
    "QQ_APP_ID", "QQ_CLIENT_SECRET", "QQBOT_HOME_CHANNEL", "QQBOT_HOME_CHANNEL_NAME",
    "QQ_HOME_CHANNEL", "QQ_HOME_CHANNEL_NAME",  # legacy aliases (pre-rename, still read for back-compat)
```

但**元数据表（`DEFAULT_CONFIG` 侧的 env 描述表）只登记正名**，旧名没有条目（`grep QQ_HOME_CHANNEL
hermes_cli/config_defaults.py` 无结果）：

`hermes_cli/config_defaults.py:4142-4146 @ 863e313`

```python
    "QQBOT_HOME_CHANNEL": {
        "description": "Default QQ channel/group for cron delivery and notifications",
        "prompt": "QQ Home Channel",
        "category": "messaging",
    },
```

`hermes gateway` 的交互式配置向导写入的也是正名：

`hermes_cli/gateway.py:5330 @ 863e313`

```python
                "name": "QQBOT_HOME_CHANNEL",
```

`hermes doctor` 把旧名列进「弃用 env」表，会主动催用户改名：

`hermes_cli/doctor.py:249-260 @ 863e313`

```python
_DEPRECATED_ENV_VARS: tuple[tuple[str, str], ...] = (
    # HERMES_TOOL_PROGRESS is fully unsupported since the v12 config support
    # floor removed its only consumer (the v3→4 migration) — it is silently
    # ignored. HERMES_TOOL_PROGRESS_MODE is still read by the gateway as a
    # back-compat fallback but remains deprecated.
    ("HERMES_TOOL_PROGRESS", "display.tool_progress in config.yaml — ignored/unsupported since config floor v12"),
    ("HERMES_TOOL_PROGRESS_MODE", "display.tool_progress in config.yaml"),
    ("TERMINAL_CWD", "terminal.cwd in config.yaml"),
    ("MESSAGING_CWD", "terminal.cwd in config.yaml"),
    ("QQ_HOME_CHANNEL", "QQBOT_HOME_CHANNEL"),
    ("QQ_HOME_CHANNEL_NAME", "QQBOT_HOME_CHANNEL_NAME"),
)
```

`hermes_cli/doctor.py:320-325 @ 863e313`

```python
    for legacy, replacement in findings:
        check_warn(
            f"Deprecated: {legacy}",
            f"(use {replacement} instead)",
        )
        check_info(f"Replace {legacy} → {replacement} (warn-only; not auto-migrated here)")
```

文档也只教正名：`website/docs/user-guide/messaging/qqbot.md:51` 写
`` | `QQBOT_HOME_CHANNEL` | OpenID for cron/notification delivery | — | ``；
`website/docs/reference/environment-variables.md:476` 同。旧名在整个 `website/` 下**零出现**。

**结论：正名 = `QQBOT_HOME_CHANNEL`。文档、向导、doctor、cron、网关运行时全部以它为准。
唯独 `hermes status` 读的是旧名。**

（另一半的 `QQ_APP_ID` 没有改名问题——它在全仓 9 处一致，是 QQ Bot 的 App ID，见 §2.2(2) 表。）

### 4.2 那个守卫想做什么，为什么永远不触发

表里 QQBot 一行填的是旧名：

`hermes_cli/status.py:483 @ 863e313`

```python
        "QQBot": ("QQ_APP_ID", "QQ_HOME_CHANNEL"),
```

循环里的守卫比较的却是正名：

`hermes_cli/status.py:495 @ 863e313`

```python
        if not home_channel and home_var == "QQBOT_HOME_CHANNEL":
```

`hermes_cli/status.py:496 @ 863e313`

```python
            home_channel = os.getenv("QQ_HOME_CHANNEL", "")
```

**守卫的本意**：从 then 分支能反推出来——它想在「主名（正名）取不到」时回落到旧名，
和 `gateway/config.py:2432-2443` 的逻辑一模一样。也就是说，写这个守卫的人假定第 483 行的
`home_var` 是 `"QQBOT_HOME_CHANNEL"`。

**为什么永远不触发**：`home_var` 的取值只可能来自第 469–485 行那张表的第二个元素。
把 15 条全列一遍（§3.2 已引），第二元素的取值集合是：

```
TELEGRAM_HOME_CHANNEL, DISCORD_HOME_CHANNEL, None, SIGNAL_HOME_CHANNEL, None,
EMAIL_HOME_ADDRESS, SMS_HOME_CHANNEL, None, FEISHU_HOME_CHANNEL, WECOM_HOME_CHANNEL,
None, WEIXIN_HOME_CHANNEL, BLUEBUBBLES_HOME_CHANNEL, QQ_HOME_CHANNEL, YUANBAO_HOME_CHANNEL
```

`"QQBOT_HOME_CHANNEL"` 不在其中。守卫是**死代码**：无论环境怎么设，第 495 行的条件恒为 False。
一行修复即可（把 483 行第二元素改成 `"QQBOT_HOME_CHANNEL"`，守卫立刻活过来并与网关行为对齐），
但在基线 `863e313` 上它没被修。

### 4.3 用户实际看到什么（三组实测输出）

关键点：**这里不会报错。症状是"该显示的东西没显示"，以及更糟的"显示了运行时不会用的那个值"。**

实测（`QQ_APP_ID=app-123` 恒定，只变 home channel 变量）：

```
--- A: canonical QQBOT_HOME_CHANNEL (what the docs tell you) ---
  QQBot         ✓ configured

--- B: legacy QQ_HOME_CHANNEL (what doctor tells you to rename away) ---
  QQBot         ✓ configured (home: openid-LEGACY)

--- C: both set ---
  QQBot         ✓ configured (home: openid-LEGACY)
```

对照第 498–502 行的拼串逻辑（`status` 只在 `home_channel` 非空时才追加 `(home: ...)`）：

`hermes_cli/status.py:500 @ 863e313`

```python
            status += f" (home: {home_channel})"
```

三个场景逐条解释：

**A（按文档配的用户）**：设了 `QQBOT_HOME_CHANNEL`。status 第 493 行去读 `QQ_HOME_CHANNEL`
（空），第 495 行守卫不触发，`home_channel` 保持 `""`，于是 `(home: ...)` 整段不打印。
用户看到 `QQBot ✓ configured`，**没有任何提示说 home channel 设没设**。他会合理地怀疑自己
配错了、cron 投递不到 QQ——而实际上网关那边（`gateway/config.py:2432`）读得好好的。
`hermes status` 在这里给出的是**假阴性静默**：不报错、不警告、什么都不说。

**B（老用户，用的旧名）**：status 显示 `(home: openid-LEGACY)`，看起来一切正常。
但同一台机器上跑 `hermes doctor`，会拿到 `Deprecated: QQ_HOME_CHANNEL (use QQBOT_HOME_CHANNEL
instead)` 的警告（`hermes_cli/doctor.py:258` + `:320-325`）。
**用户按 doctor 的建议改名 → status 里的 `(home: ...)` 消失了。** 两个诊断命令给出相反的信号：
doctor 说旧名该淘汰，status 只认旧名。这是最容易让人绕进去的路径。

**C（两个都设，迁移过渡期）**：这是**唯一一个 status 主动说了错话的场景**。
网关真正生效的是 `QQBOT_HOME_CHANNEL`（`gateway/config.py:2432` 先读正名，非空就不看旧名），
而 status 显示的是 `openid-LEGACY`。**用户在 status 里看到的 home channel，正是运行时不会使用的那个。**
排障时按这个值去核对，只会越查越乱。

**用户可复述的因果（一句话版）**：
> 你按文档把 QQ 的 home channel 写成 `QQBOT_HOME_CHANNEL`（或者按 `hermes doctor` 的提示从
> `QQ_HOME_CHANNEL` 改成了它）→ `hermes status` 的 QQBot 那行从此不再显示 `(home: …)` →
> 因为 status 的平台表里 QQBot 这条硬编码的还是改名前的 `QQ_HOME_CHANNEL`
> （`hermes_cli/status.py:483`），而旁边那个本该做回落的守卫比对的是
> `"QQBOT_HOME_CHANNEL"`（`:495`）——这个值表里任何一条都取不到，守卫是死代码。
> 真正生效的是 `QQBOT_HOME_CHANNEL`（`gateway/config.py:2432`），所以你的配置没问题，
> 是这个状态面板看错了变量。

---

## 5. Q4 —— 崩溃抵抗

### 5.1 被 try/except 罩住的块（逐个列出）

| 块 | 行区间 | 捕获范围 | 失败时的表现 |
|---|---|---|---|
| `load_config()` | 135–138 | `except Exception` | `config = {}`，静默 |
| `_effective_provider_label` 里的 `resolve_provider` | 88–91 | **仅 `AuthError`** | 回落到 `requested or "auto"` |
| `_effective_provider_label` 里的 `load_config` | 100–105 | `except Exception: pass` | `config_base_url` 保持 `""` |
| 4 个 OAuth 快照（Nous/Codex/Qwen/MiniMax） | 205–222 | `except Exception` | 四个 dict 全置空 |
| `get_nous_portal_account_info()` | 232–235 | `except Exception` | `None` |
| xAI OAuth（**独立的一个 try**，注释说明理由） | 322–326 | `except Exception` | `{}` |
| LM Studio 探测 | 409–416 | **仅 `AuthError`** | 打 "auth rejected" |
| 插件平台整段循环 | 505–513 | `except Exception: pass` | **整段静默消失** |
| Gateway 快照 | 521–549 | `except Exception` | 按平台打 "unknown / systemd/manual / launchd / N/A" |
| `cron/jobs.json` 解析 | 560–569 | `except Exception` | "Jobs: (error reading jobs file)" |
| `SessionDB` 查询 | 583–595 | `except Exception` | 回落 `sessions.json` |
| `sessions.json` 解析 | 609–618 | `except Exception` | "Active: (error reading sessions file)" |
| `resolve_max_concurrent_sessions` | 626–635 | `except Exception` | `_cap = None`，整个 Slots 块跳过 |
| `active_session_registry_snapshot` | 637–640 | `except Exception` | `_held = []` |
| deep: OpenRouter 探测 | 666–676 | `except Exception as e` | 打 "error: {e}" |
| deep: 端口探测 | 679–690 | **仅 `OSError`** | 静默跳过 |

xAI 那个独立 try 的存在理由，作者自己写在注释里（第 320–321 行）：
「so an import failure here cannot disrupt the already-printed Nous/Codex/Qwen/MiniMax rows above」。
这说明作者对"分块隔离"是有意识的——只是没有贯彻到全文。

### 5.2 **没有**被罩住的调用点（实测确认会把整个 `hermes status` 打崩）

`repro_unguarded.py` 逐个把外部依赖换成 `raise RuntimeError("boom")`，结果：

```
[CRASHED ] A: managed_nous_tools_enabled raises      -> status.py:344
[CRASHED ] B: get_nous_subscription_features raises  -> status.py:345
[CRASHED ] C: get_env_value raises                   -> status.py:189 -> status.py:181
[CRASHED ] D: resolve_requested_provider raises      -> status.py:141 -> status.py:87
[CRASHED ] E: resolve_provider raises non-AuthError  -> status.py:141 -> status.py:89
[CRASHED ] F: get_hermes_home raises                 -> status.py:557
[CRASHED ] G: get_env_path raises                    -> status.py:132
[CRASHED ] H: describe_vercel_auth raises            -> status.py:449
[SURVIVED] I: provider == LM Studio, probe unreachable
[SURVIVED] J: (未触发，条件不满足)
```

逐个的源位置：

`hermes_cli/status.py:344 @ 863e313`

```python
    if managed_nous_tools_enabled():
```

`hermes_cli/status.py:345 @ 863e313`

```python
        features = get_nous_subscription_features(config)
```

—— ◆ Nous Tool Gateway 整节（344–376）**没有任何 try/except**。
实践中 `managed_nous_tools_enabled()` 自己内部 `except Exception: return False`
（`tools/tool_backend_helpers.py:43-44`），所以 A 在真实运行里不会发生；
但 `get_nous_subscription_features(config)` 只在内部保护了 `get_nous_portal_account_info`
（`hermes_cli/nous_subscription.py:358-364`），后面几十行 config 形状解析是裸的。
这一节是本文件**最大的无保护面**。

`hermes_cli/status.py:87 @ 863e313`

```python
    requested = resolve_requested_provider()
```

`hermes_cli/status.py:89 @ 863e313`

```python
        effective = resolve_provider(requested)
```

—— 第 88 行的 `try` 只捕 `AuthError`。`resolve_provider` 抛别的异常（配置解析失败、
provider registry 加载失败）就直接穿透到顶。而 `resolve_requested_provider()` 在 try 之外，
完全无保护。注意 `_effective_provider_label()` 被调用两次（141、405），任一次抛都是全崩。

`hermes_cli/status.py:181 @ 863e313`

```python
        return get_env_value(env_ref) or ""
```

`hermes_cli/status.py:189 @ 863e313`

```python
        value = _resolve_env(env_ref)
```

—— ◆ API Keys 整个循环（183–197）没有 try。而 `get_env_value` 是**会抛**的：
`UnscopedSecretError` 被显式 `raise` 而非吞掉（`hermes_cli/config.py:4134-4135`，§2.1 已引）。
在 profile 多路复用作用域下这条路径是活的。

`hermes_cli/status.py:132 @ 863e313`

```python
    env_path = get_env_path()
```

`hermes_cli/status.py:557 @ 863e313`

```python
    jobs_file = get_hermes_home() / "cron" / "jobs.json"
```

—— 家目录解析本身无保护。`get_hermes_home()` 会做 `ensure_hermes_home()` 级别的目录创建/
chown（`hermes_cli/config.py` 的 `_resolve_hermes_uid_gid` 注释提到 Docker 场景的
`PermissionError [Errno 13]`），只读文件系统或权限错配下这一句能把整个 status 打掉。
注意第 557 行位置很靠后——前面 8 节都已经打印出来了，用户会看到一份**打了一半然后 traceback**
的输出，这比完全不输出更难判断。

`hermes_cli/status.py:449 @ 863e313`

```python
        auth_status = describe_vercel_auth()
```

—— vercel 分支（442–458）无 try。同段的
`importlib.util.find_spec("vercel")`（第 450 行）在特定情况下也会抛
（模块已 import 但 `__spec__` 为 None 时 `ValueError`）。

另外两处不构成实际风险但结构上同样裸露：第 406 行的
`from hermes_cli.models import probe_lmstudio_models` 在 try 之外（ImportError 会崩）；
第 194 行的 `from hermes_cli.auth import get_anthropic_key` 同理。

### 5.3 配置损坏 / 外部命令缺失：实测都不崩

`repro_crash.py` 六组，全部 `[SURVIVED]`（末行都跑到了 footer `Run 'hermes setup' to configure`）：

```
[SURVIVED] 1 invalid YAML (load_config raises)
[SURVIVED] 2 wrong shapes: model list / terminal str / web int
[SURVIVED] 3 terminal.backend non-string (int)
[SURVIVED] 4 corrupt cron/jobs.json + sessions.json
[SURVIVED] 5 max_concurrent_sessions garbage
[SURVIVED] 6 empty config.yaml
```

- 1：`load_config()` 抛 → 135–138 兜住 → `config = {}`。（注意它是 `load_config` 自己
  先打了一段很长的 stderr 警告并把损坏文件备份成 `.corrupt.<ts>.bak`，然后返回默认配置；
  status 这一层其实没接到异常。）
- 3：`terminal.backend = 7` → `terminal_env` 变成 int → 第 431/436/439/442 行的
  `== "ssh"` 等比较全部 False → 打出 `Backend:      7`。不崩，但**静默显示一个不存在的后端名**。
- 4：两个 JSON 解析块各自有 `except Exception`，打出 `(error reading ...)`。

**外部命令**：status.py 自己**不 shell out**（§1 已证 `subprocess` 未被使用）。
唯一可能调外部命令的是 `get_gateway_runtime_snapshot()`（systemctl/launchctl），
它整个在 521–549 的 try 里，且 except 分支按平台给出降级文案。所以「systemctl 不存在」
这类情况不会崩，只会显示 `Status: unknown / Manager: systemd/manual`。

### 5.4 `tests/hermes_cli/test_status.py` —— 10 个用例逐个列出

文件共 239 行，**10 个测试函数**（4 个模块级 + 6 个在 `class TestShowStatusXaiOAuth` 内）。
其中**明确针对崩溃抵抗的有 4 个**，全部只覆盖 xAI OAuth 这一个块。

| # | 行 | 名称 | 测什么 | 属于崩溃抵抗？ |
|---|---|---|---|---|
| 1 | 6 | `test_show_status_all_does_not_print_tavily_key_value` | 设 `TAVILY_API_KEY` 为哨兵串，断言输出含 "Tavily" 但**不含哨兵值** —— 脱敏回归 | 否（脱敏） |
| 2 | 18 | `test_show_status_termux_gateway_section_skips_systemctl` | Termux 环境下 Gateway 节不得调 `subprocess.run`（把 `status.subprocess.run` 换成会 `AssertionError` 的桩），并断言输出 Termux 文案 | 否（副作用约束） |
| 3 | 47 | `test_show_status_reports_vercel_backend_contract` | vercel_sandbox 后端的 Runtime/SDK/Auth/Persistence/Processes 五行内容，且断言 `"oidc-token" not in output` | 否（内容契约 + 顺带脱敏） |
| 4 | 110 | `TestShowStatusXaiOAuth::test_logged_in_shows_auth_store` | `auth_store` 存在时打印 `Auth file:` 行 | 否 |
| 5 | 123 | `::test_no_auth_store_line_when_field_absent` | `auth_store` 缺失时 xAI 段内不得出现 `Auth file:` | 否 |
| 6 | 148 | `::test_import_failure_does_not_crash_show_status` | `delattr` 掉 `get_xai_oauth_auth_status` → `show_status` 仍跑完，输出含 `◆ Auth Providers` | **是** |
| 7 | 159 | `::test_import_failure_does_not_break_other_oauth_providers` | 同上，额外断言 Nous / MiniMax 行仍在（隔离性） | **是** |
| 8 | 173 | `::test_status_function_exception_does_not_crash` | `get_xai_oauth_auth_status` 抛 `RuntimeError("backend unreachable")` → 不上抛 | **是** |
| 9 | 188 | `::test_status_function_returns_none_does_not_crash` | 返回 `None` → 走 `or {}` 兜底，打 "not logged in (run: hermes auth add xai-oauth)" | **是** |
| 10 | 202 | `test_show_status_reports_gateway_session_last_activity` | 假 `SessionDB` 返回两行 → 断言 "Active: 2 session(s)" + "Last activity:" + "1m ago"（#72016） | 否 |

四个崩溃抵抗用例的原文：

`tests/hermes_cli/test_status.py:148-157 @ 863e313`

```python
    def test_import_failure_does_not_crash_show_status(self, monkeypatch, capsys, tmp_path):
        """show_status must complete even when get_xai_oauth_auth_status cannot be imported."""
        import hermes_cli.auth as auth_mod
        status_mod = _base_xai_mocks(monkeypatch, tmp_path)
        monkeypatch.delattr(auth_mod, "get_xai_oauth_auth_status", raising=False)

        status_mod.show_status(SimpleNamespace(all=False, deep=False))
        out = capsys.readouterr().out

        assert "◆ Auth Providers" in out
```

`tests/hermes_cli/test_status.py:159-171 @ 863e313`

```python
    def test_import_failure_does_not_break_other_oauth_providers(self, monkeypatch, capsys, tmp_path):
        """Nous/Codex/MiniMax rows must still appear when xAI import fails."""
        import hermes_cli.auth as auth_mod
        status_mod = _base_xai_mocks(monkeypatch, tmp_path)
        monkeypatch.setattr(auth_mod, "get_nous_auth_status_local",
                            lambda: {"logged_in": True}, raising=False)
        monkeypatch.delattr(auth_mod, "get_xai_oauth_auth_status", raising=False)

        status_mod.show_status(SimpleNamespace(all=False, deep=False))
        out = capsys.readouterr().out

        assert "Nous Portal" in out
        assert "MiniMax OAuth" in out
```

`tests/hermes_cli/test_status.py:173-186 @ 863e313`

```python
    def test_status_function_exception_does_not_crash(self, monkeypatch, capsys, tmp_path):
        """show_status must not propagate an exception raised by get_xai_oauth_auth_status."""
        import hermes_cli.auth as auth_mod
        status_mod = _base_xai_mocks(monkeypatch, tmp_path)

        def _raises():
            raise RuntimeError("backend unreachable")

        monkeypatch.setattr(auth_mod, "get_xai_oauth_auth_status", _raises, raising=False)

        status_mod.show_status(SimpleNamespace(all=False, deep=False))
        out = capsys.readouterr().out

        assert "◆ Auth Providers" in out
```

`tests/hermes_cli/test_status.py:188-199 @ 863e313`

```python
    def test_status_function_returns_none_does_not_crash(self, monkeypatch, capsys, tmp_path):
        """get_xai_oauth_auth_status returning None must be handled gracefully."""
        import hermes_cli.auth as auth_mod
        status_mod = _base_xai_mocks(monkeypatch, tmp_path)
        monkeypatch.setattr(auth_mod, "get_xai_oauth_auth_status",
                            lambda: None, raising=False)

        status_mod.show_status(SimpleNamespace(all=False, deep=False))
        out = capsys.readouterr().out

        assert "xAI OAuth" in out
        assert "not logged in (run: hermes auth add xai-oauth)" in out
```

第 2 个用例（Termux）就是 §1 里那个未使用 `subprocess` import 的消费者：

`tests/hermes_cli/test_status.py:18-46 @ 863e313`

```python
def test_show_status_termux_gateway_section_skips_systemctl(monkeypatch, capsys, tmp_path):
    from hermes_cli import status as status_mod
    import hermes_cli.auth as auth_mod
    import hermes_cli.gateway as gateway_mod

    monkeypatch.setenv("TERMUX_VERSION", "0.118.3")
    monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")
    monkeypatch.setattr(status_mod, "get_env_path", lambda: tmp_path / ".env", raising=False)
    monkeypatch.setattr(status_mod, "get_hermes_home", lambda: tmp_path, raising=False)
    monkeypatch.setattr(status_mod, "load_config", lambda: {"model": "gpt-5.4"}, raising=False)
    monkeypatch.setattr(status_mod, "resolve_requested_provider", lambda requested=None: "openai-codex", raising=False)
    monkeypatch.setattr(status_mod, "resolve_provider", lambda requested=None, **kwargs: "openai-codex", raising=False)
    monkeypatch.setattr(status_mod, "provider_label", lambda provider: "OpenAI Codex", raising=False)
    monkeypatch.setattr(auth_mod, "get_nous_auth_status_local", lambda: {}, raising=False)
    monkeypatch.setattr(auth_mod, "get_codex_auth_status", lambda: {}, raising=False)
    monkeypatch.setattr(auth_mod, "get_xai_oauth_auth_status", lambda: {}, raising=False)
    monkeypatch.setattr(gateway_mod, "find_gateway_pids", lambda exclude_pids=None: [], raising=False)

    def _unexpected_systemctl(*args, **kwargs):
        raise AssertionError("systemctl should not be called in the Termux status view")

    monkeypatch.setattr(status_mod.subprocess, "run", _unexpected_systemctl)

    status_mod.show_status(SimpleNamespace(all=False, deep=False))

    output = capsys.readouterr().out
    assert "Manager:      Termux / manual process" in output
    assert "Start with:   hermes gateway" in output
    assert "systemd (user)" not in output
```

**测试覆盖的空洞**（对照 §5.2 的 8 个裸露点）。注意区分「执行到」与「有断言」：
10 个用例都是端到端跑完 `show_status`，所以每一节都被**执行**，但断言只落在下面这几处——
没有断言的地方，行为怎么变都不会让 CI 变红。

- ◆ Messaging Platforms（466–513）：**0 条断言**。QQBot 那条缺陷（F1）因此没有任何测试能发现——
  全仓 `grep QQ_HOME_CHANNEL tests/` 只命中 `tests/hermes_cli/test_doctor.py:1383-1384`
  （在 doctor 测试里 `delenv` 清场），status 侧一条都没有。同理 F5（WhatsApp=false）、
  F6（Email/Signal 半配）也无人守。
- ◆ Nous Tool Gateway（344–376）：**0 条断言**，且测试环境下 `managed_nous_tools_enabled()`
  返回 False、`nous_logged_in` 也为 False，整块被 `if/elif` 跳过——连执行都没有。
- ◆ API Keys 的循环：只有第 1 个用例侧面覆盖（Tavily 值不外泄），env 名表本身无断言，
  所以 F7（Z.AI 三元组抄漏）、F8（Anthropic 死数据）都不会被发现。
- 配置损坏路径：**0 个用例**（我在 §5.3 手工补了 6 组，全通过）。
- 4 个崩溃用例全部集中在 xAI OAuth 一个块上——它们是某次 xAI 相关改动的回归测试，
  不是对 status 整体健壮性的系统性覆盖。

---

## 6. Q5 —— 输出形态与脱敏

### 6.1 纯文本，没有任何 JSON 模式

`hermes status` 的参数只有两个，都是 `store_true`：

`hermes_cli/subcommands/status.py:17-28 @ 863e313`

```python
    status_parser = subparsers.add_parser(
        "status",
        help="Show status of all components",
        description="Display status of Hermes Agent components",
    )
    status_parser.add_argument(
        "--all", action="store_true", help="Show all details (redacted for sharing)"
    )
    status_parser.add_argument(
        "--deep", action="store_true", help="Run deep checks (may take longer)"
    )
    status_parser.set_defaults(func=cmd_status)
```

整个配置可观测面（`hermes status` / `hermes dump` / `hermes doctor`）**没有一个提供
机器可读输出**：`hermes dump` 的唯一开关是 `--show-keys`
（`hermes_cli/subcommands/dump.py:24-28`），`hermes doctor` 是 `--fix` / `--ack`
（`hermes_cli/subcommands/doctor.py:22-33`）。想程序化消费状态只能解析带 ANSI 色码和
Unicode 框线的文本。

status 的输出还带 Box-drawing 与 `◆ / ✓ / ✗` 符号（120–122、128 等），并通过
`hermes_cli.colors.color()` 上色——`hermes_cli/console_engine.py:1279` 里的 `/status`
斜杠命令就得先 `_capture_output(...)` 再 `_strip_console_status_footer(...)` 事后剥文案。

### 6.2 `--all` 是死开关（文档-代码冲突）

`show_status` **全文没有读过 `args.all`**（唯一的 `getattr` 是第 117 行取 `deep`）。
文档却写着它有明确语义：

`website/docs/reference/cli-commands.md:554 @ 863e313`

```
| `--all` | Show all details in a shareable redacted format. |
```

parser 的 help 也写着 "Show all details (redacted for sharing)"（`hermes_cli/subcommands/status.py:23`）。
更有意思的是，测试第 1 例的函数名叫 `test_show_status_all_does_not_print_tavily_key_value`，
并且传的是 `all=True`：

`tests/hermes_cli/test_status.py:6-15 @ 863e313`

```python
def test_show_status_all_does_not_print_tavily_key_value(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    sentinel = "NONSECRET_SENTINEL_VALUE_DO_NOT_PRINT_123456"
    monkeypatch.setenv("TAVILY_API_KEY", sentinel)

    show_status(SimpleNamespace(all=True, deep=False))

    output = capsys.readouterr().out
    assert "Tavily" in output
    assert sentinel not in output
```

这个测试的断言本身是对的（脱敏确实生效），但它**营造了 `--all` 有效的假象**：
名字里带 `all`、参数传了 `all=True`，读测试的人会以为在验证 `--all` 路径。实际上传 `all=False`
结果一模一样。文档-代码冲突按项目规则以代码为准：**`--all` 当前是无操作**。

### 6.3 脱敏：API key 层完整，PII 层完全没有

脱敏的唯一入口：

`hermes_cli/status.py:35-44 @ 863e313`

```python
def redact_key(key: str) -> str:
    """Redact an API key for display.

    Thin wrapper over :func:`agent.redact.mask_secret`. Preserves the
    "(not set)" placeholder in dim color to match ``hermes config``'s
    output (previously this variant was missing the DIM color —
    consolidated via PR that also introduced ``mask_secret``).
    """
    from agent.redact import mask_secret
    return mask_secret(key, empty=color("(not set)", Colors.DIM))
```

`agent/redact.py:482-486 @ 863e313`

```python
    if not value:
        return empty
    if len(value) < floor:
        return placeholder
    return f"{value[:head]}...{value[-tail:]}"
```

默认 `head=4, tail=4, floor=12`：

`agent/redact.py:447 @ 863e313`

```python
    floor: int = 12,
```

即 <12 字符全遮成 `***`，否则显示 `头4...尾4`。输出长度固定，不泄露密钥长度。

**覆盖到的**：◆ API Keys 节 20 行全部经 `redact_key`（第 191、196 行），Anthropic 同。
◆ API-Key Providers 节干脆不打值，只打 `configured / not configured`（第 399–400 行）。
◆ Messaging Platforms 节的 token **不打印**（第 488 行只取 `bool`）。
`SUDO_PASSWORD` 只打 enabled/disabled：

`hermes_cli/status.py:461 @ 863e313`

```python
    print(f"  Sudo:         {check_mark(bool(sudo_password))} {'enabled' if sudo_password else 'disabled'}")
```

Vercel 的凭据也只做存在性判断（`describe_vercel_auth` 的 docstring 明写
"without exposing secret values"，`hermes_cli/vercel_auth.py:24`），测试第 3 例断言
`"oidc-token" not in output` 是这条纪律的回归保护。

**没覆盖到的 —— PII / 拓扑信息全部明文**：

1. **home channel 值全文打印**（第 500 行，§4.3 已引）。这一栏的实际内容包括
   `SMS_HOME_CHANNEL`（手机号）、`EMAIL_HOME_ADDRESS`（邮箱）、`SIGNAL_HOME_CHANNEL`（手机号）、
   各 IM 的用户/群 OpenID。实测输出里 `(home: openid-LEGACY)` 是原样打印的。
   `--all` 文档承诺的是 "shareable redacted format"，而这些值**没有任何遮蔽**。
2. **SSH 主机与用户名**明文：

`hermes_cli/status.py:434 @ 863e313`

```python
        print(f"  SSH Host:     {ssh_host or '(not set)'}")
```

（第 435 行同理打 `SSH User`。）

3. **`PROJECT_ROOT` 与各 auth 文件绝对路径**明文（第 129、284、298、335 行），
   在 `~` 形式下会带出用户名。
4. **Nous portal / inference base URL** 明文（第 265、267 行）；LM Studio 的 `base` 明文
   （第 412、414 行）——若用户把凭据放在 URL 里就会连带打印。
5. **各 provider 的 error 字符串原样打印**（第 275、289、304、318、339 行），内容来自
   `state["last_auth_error"]["message"]` 等上游字段，status 不做任何过滤。
   *复核：未找到把 token 写进 message 的路径，判为「存疑」而非确认。*
6. **deep 模式的异常文本**原样打印（第 676 行 `error: {e}`）。key 在 header 里不在 URL 里，
   httpx 异常文本一般不含 key。*判为「存疑」。*

小结：**"不泄露 API key" 这条做到了且有测试守着；"可安全分享" 这条没做到，而且文档明确承诺了。**

---

## 7. 其它零散观察

- **`◆ Sessions` 有两套数据源**：优先 `hermes_state.SessionDB.list_gateway_sessions`
  （注释标 `#9006` 说 state.db 是 source of truth），回落 `sessions.json`
  （第 583–620 行）。回落分支统计的是 dict 里不以 `_` 开头的键数——两套口径不完全等价
  （前者 `active_only=True`，后者是文件里的全部条目）。
- **`Last activity` 那行的格式串少一个空格**：`f"  Last activity:{...:>13}"`（第 604 行），
  其余行都是 `"  Xxx:        "` 对齐。测试断言的是 `"Last activity:" in output`，所以没暴露。
- **Slots 块的取值**：`resolve_max_concurrent_sessions(config)` 返回 falsy 就整块跳过
  （第 636 行 `if _cap:`），所以"没设上限"和"取值失败"在输出上不可区分。
- **deep 模式的端口号 18789 是硬编码**（第 683 行），不读配置里的 gateway 端口；
  用户改了端口后 `Port 18789: available` 这行就变成噪音。
- **deep 模式的 OpenRouter 探测用 `os.getenv`**（第 664 行），与第 151 行的
  `get_env_value("OPENROUTER_API_KEY")` 不同源（§2.1）。

---

## 发现清单

> 格式：一句话症状 + 锚点 + 复核结论。

### F1（本轮重点）status 平台表把 QQBot 的 home channel 写成了改名前的旧名，旁边的回落守卫因此成为死代码
- **症状**：设了正名 `QQBOT_HOME_CHANNEL` 的用户，`hermes status` 的 QQBot 行**不显示** `(home: …)`；
  两个都设时显示的是**运行时不会使用的**旧名值。
- **锚点**：`hermes_cli/status.py:483`（表里是 `"QQ_HOME_CHANNEL"`）、
  `hermes_cli/status.py:495`（守卫比对 `"QQBOT_HOME_CHANNEL"`，该值在 469–485 的表里任何一条都取不到）；
  正名真值在 `gateway/config.py:2432`。
- **复核结论**：**确认**。三组实测输出见 §4.3；表的 15 条第二元素已逐条枚举，`"QQBOT_HOME_CHANNEL"` 确实不在集合内。
  一行可修（483 行第二元素改正名）。

### F2 `hermes doctor` 与 `hermes status` 对 QQ home channel 给出相反信号
- **症状**：doctor 警告 `Deprecated: QQ_HOME_CHANNEL (use QQBOT_HOME_CHANNEL instead)`；
  用户照做改名后，status 里的 home channel 显示反而消失。
- **锚点**：`hermes_cli/doctor.py:258` + `hermes_cli/doctor.py:320-325`（催改名）
  vs `hermes_cli/status.py:483`（只认旧名）。
- **复核结论**：**确认**。是 F1 的用户可感知后果，单列因为它是"两个诊断命令互相打架"这一类问题。

### F3 status 用 `check_fn()` 判定插件平台就绪，而同仓 `hermes gateway` 已把这个坑修好并在注释里写明了原因
- **症状**：装了 Telegram/Discord SDK 但没设 token 的用户，会看到 `Telegram ✓ configured (plugin)`。
- **锚点**：`hermes_cli/status.py:508`（`configured = entry.check_fn()`）；
  契约定义 `gateway/platform_registry.py:53`（"dependencies are available"）；
  已修版本 `hermes_cli/gateway.py:5431-5459`，其注释原文即"that would let 'SDK is installed'
  override 'no token configured' and incorrectly report the platform as ready"。
- **复核结论**：**确认**（代码级确定；未做端到端实测，因为需要真实装插件）。

### F4 `hermes status` 可能触发 pip 安装 —— 一个自称只读的诊断命令有写副作用
- **症状**：`plugin_entries()` 会 import 全部延迟插件，随后对每个 entry 调 `check_fn()`；
  Telegram/Discord 的 `check_fn` 在依赖缺失时会 `_lazy_ensure(..., prompt=False)`（不问用户直接装）。
- **锚点**：`hermes_cli/status.py:507-508`、`gateway/platform_registry.py:266-269`、
  `plugins/platforms/telegram/adapter.py:411`。
- **复核结论**：**确认（路径成立）**，但触发条件是"插件管理器已在本进程注册了延迟加载器
  且依赖缺失且 lazy install 未被禁用"，我未在容器里实际触发（会写文件，违反基线只读约束）。
  与之对照的是同文件 205–214 行为了只读而刻意选用 refresh-free 快照——同一文件内纪律不一致。

### F5 `WHATSAPP_ENABLED=false` 被判为「已配置 ✓」
- **症状**：显式关闭 WhatsApp 的用户在 status 里看到 `WhatsApp ✓ configured`。
- **锚点**：`hermes_cli/status.py:488`（`bool(os.getenv(token_var, ""))`）；
  真值判定 `gateway/config.py:1890-1891`（`is_truthy_value` + 显式 disable 集合）。
- **复核结论**：**确认**（实测输出 §3.2）。同一错误在 `hermes_cli/tools_config.py:2083`、
  `hermes_cli/dump.py:187` 各存在一份；`hermes_cli/gateway.py:5466` 是唯一处理正确的。

### F6 Email / Signal 只要设了第一个 env 就报 ✓，缺其余必填项无提示
- **症状**：只设 `EMAIL_ADDRESS`（缺密码/IMAP/SMTP）或只设 `SIGNAL_HTTP_URL`（缺 `SIGNAL_ACCOUNT`）→ 显示 ✓ configured。
- **锚点**：`hermes_cli/status.py:475`、`:473`、`:487-489`；
  完整判定 `hermes_cli/gateway.py:5473-5488`（有 "partially configured" 中间态）。
- **复核结论**：**确认**（实测输出 §3.2）。

### F7 同一份输出里 Z.AI / Kimi 等 6 家出现两次，两次判定用不同 env 集合，可自相矛盾
- **症状**：只设 `ZAI_API_KEY` 时，同一屏出现 `Z.AI / GLM ✗ (not set)` 和 `Z.AI / GLM ✓ configured`。
- **锚点**：`hermes_cli/status.py:158`（只查 `GLM_API_KEY`）vs `hermes_cli/status.py:385`（查三元组）；
  权威声明 `hermes_cli/providers.py:107`。
- **复核结论**：**确认**（实测输出 §2.2）。这是"同一语义多份实现"在单文件内发散的最短样本。

### F8 `keys` 表里 Anthropic 那条是死数据，修法是「跳过」而不是「删掉」
- **症状**：表里写 2 个 env 名，真实生效的是 3 个（多 `CLAUDE_CODE_OAUTH_TOKEN`）且用 dotenv 优先解析。
- **锚点**：`hermes_cli/status.py:153`（死数据）、`:187-188`（`continue` 跳过）、
  `hermes_cli/auth.py:548-565`（真实实现）。
- **复核结论**：**确认**。错误规格被保留在表里，只是不再执行——下一个读表的人仍会被误导。

### F9 ◆ Nous Tool Gateway 整节没有任何 try/except，是本文件最大的无保护面
- **症状**：`get_nous_subscription_features(config)` 抛异常 → 整个 `hermes status` traceback，
  且已打印的前三节留在屏幕上（半截输出）。
- **锚点**：`hermes_cli/status.py:344`、`hermes_cli/status.py:345`（344–376 全段裸奔）。
- **复核结论**：**确认**（`repro_unguarded.py` A/B 两例实测 CRASHED，栈内层帧分别是 status.py:344 / :345）。
  实践风险中等：`managed_nous_tools_enabled` 自身 fail-closed，`get_nous_subscription_features`
  只保护了 portal 调用那一段。

### F10 另有 6 处无保护调用点会把整个 status 打崩
- **症状**：各自抛异常时无兜底。
- **锚点**：`hermes_cli/status.py:87`（`resolve_requested_provider`，在 try 之外）、
  `:89`（`resolve_provider`，try 只捕 `AuthError`）、
  `:181` / `:189`（`get_env_value`，而它会显式 `raise UnscopedSecretError`，见 `hermes_cli/config.py:4134-4135`）、
  `:132`（`get_env_path`）、`:557`（`get_hermes_home`，位置很靠后 → 半截输出）、
  `:449`（`describe_vercel_auth`）。
- **复核结论**：**确认**（`repro_unguarded.py` C–H 六例实测全部 CRASHED，附栈内层帧）。

### F11 插件平台整段循环共用一个 `except Exception: pass`，一个插件出错则整段静默消失
- **症状**：某插件 `check_fn()` 抛异常 → 剩余插件行**一行都不打**，且没有任何提示。
- **锚点**：`hermes_cli/status.py:505-513`（try 包住整个 for，except 分支是 `pass`）。
- **复核结论**：**确认**（代码级）。对比 `hermes_cli/gateway.py:5445-5459` 是**每个 entry 各自** try。

### F12 `--all` 是死开关，但文档、help、测试名三处都在宣称它有语义
- **症状**：`hermes status --all` 与 `hermes status` 输出完全一致。
- **锚点**：`hermes_cli/status.py:117`（只取 `deep`，全文无 `args.all`）；
  `hermes_cli/subcommands/status.py:23`（help 文案）；
  `website/docs/reference/cli-commands.md:554`（"shareable redacted format"）；
  `tests/hermes_cli/test_status.py:6`（函数名带 `all`、传 `all=True`，制造有效假象）。
- **复核结论**：**确认**（文档-代码冲突，按项目规则以代码为准）。

### F13 脱敏只覆盖 API key，PII（手机号/邮箱/OpenID/SSH 主机与用户）全明文
- **症状**：`hermes status` 的输出直接贴进 issue 会带出 home channel（可能是手机号/邮箱）、
  SSH 主机与用户名、项目绝对路径。而 `--all` 的文档承诺是 "shareable redacted format"。
- **锚点**：`hermes_cli/status.py:500`（home channel 原样拼进 status 串）、
  `:434`（SSH Host）、`:435`（SSH User）、`:129`（PROJECT_ROOT）；
  脱敏实现 `agent/redact.py:482-486`（只被 `redact_key` 用于 API Keys 节）。
- **复核结论**：**确认**。API key 侧无遗漏（有测试 `test_status.py:6` 守着），PII 侧完全无遮蔽。

### F14 LM Studio 探测的触发条件挂在展示用标签字符串上
- **症状**：`if _effective_provider_label() == "LM Studio":` —— 改一次 provider 显示名，这段探测静默失效。
- **锚点**：`hermes_cli/status.py:405`；标签来源 `hermes_cli/providers.py:424`（`"lmstudio": "LM Studio"`）。
- **复核结论**：**确认**。应比对 provider id `"lmstudio"` 而非 label。

### F15 `_effective_provider_label()` 在一次 `show_status` 里被调用两次，重复做 provider 解析与 `load_config`
- **症状**：第 141 行与第 405 行各调一次；openrouter 分支下每次还额外 `load_config()`。
- **锚点**：`hermes_cli/status.py:141`、`hermes_cli/status.py:405`、`hermes_cli/status.py:100-105`。
- **复核结论**：**确认**（纯性能/一致性问题，两次之间若 env 变化理论上可给出不一致结果）。

### F16 生产模块保留一个未使用的 `import subprocess` 仅为给测试提供 monkeypatch 锚点
- **症状**：`status.py` 全文不用 `subprocess`，靠 `# noqa: F401` 压 linter。
- **锚点**：`hermes_cli/status.py:11`；消费者 `tests/hermes_cli/test_status.py:39`
  （`monkeypatch.setattr(status_mod.subprocess, "run", _unexpected_systemctl)`）。
- **复核结论**：**确认**。测试意图（Termux 下不得调 systemctl）是合理的，但探针方式让生产模块背了一个假 import。

### F17 `terminal.backend` 是非法值时静默显示该值，无任何校验
- **症状**：`terminal: {backend: 7}` → 输出 `Backend:      7`，且后续所有分支都不匹配，
  用户看不出自己配错了。
- **锚点**：`hermes_cli/status.py:425-429`（取值与打印）、`:431` 起的一串 `==` 比较。
- **复核结论**：**确认**（`repro_crash.py` 第 3 组实测 SURVIVED 且打印 `Backend: 7`）。

### F18 整个配置可观测面（status / dump / doctor）都没有机器可读输出
- **症状**：想程序化消费状态只能解析带 ANSI 色码和 Unicode 框线的文本。
- **锚点**：`hermes_cli/subcommands/status.py:17-28`（只有 `--all` / `--deep`）；
  `hermes_cli/subcommands/dump.py:24-28`（只有 `--show-keys`）；
  `hermes_cli/subcommands/doctor.py:22-33`（只有 `--fix` / `--ack`）。
- **复核结论**：**确认**。旁证：`hermes_cli/console_engine.py:1279` 里 `/status` 斜杠命令
  只能 `_capture_output` 再事后剥文案。

### F19 deep 模式的 gateway 端口写死 18789，不读配置
- **症状**：改过 gateway 端口的用户，`Port 18789: available` 这行恒为噪音。
- **锚点**：`hermes_cli/status.py:683`（`sock.connect_ex(('127.0.0.1', 18789))`）。
- **复核结论**：**确认**（代码级；同段注释自称 "informational, not necessarily bad"，
  说明作者知道它信息量低，但没解决取值来源问题）。

### F20 status 的平台判定是全仓第 8 份实现，而仓库里已有一份「读真值」的正确做法
- **症状**：「某平台配好没有」在全仓有 8 处各自作答（表见 §2.2(2)），彼此口径不一致（F5/F6 是其后果）。
- **锚点**：`hermes_cli/status.py:469-485`（第 8 份，硬编码 env 表）；
  正确参照 `cli.py:9789`（`config = load_gateway_config()`）+ `cli.py:9802`
  （`pconfig = config.platforms.get(platform)` —— 读运行时构造好的对象，不重抄表）。
- **复核结论**：**确认**。这是本轮统一发现「同一语义多份实现」在配置可观测面的完整样本。

### F21 status 侧对消息平台节零断言覆盖，F1/F5/F6 因此都无法被 CI 发现
- **症状**：`tests/hermes_cli/test_status.py` 的 10 个用例虽然都端到端执行了第 466–513 行，
  但**没有一条断言**落在那一节的输出上——该节行为怎么变都不会让 CI 变红。
- **锚点**：`tests/hermes_cli/test_status.py`（全文 239 行，10 个测试函数已在 §5.4 逐个列出，
  断言目标分别是：Tavily 脱敏 / Termux 免 systemctl / Vercel 五行契约 / xAI 四例崩溃抵抗 /
  xAI 两例显示 / 会话 last_active）。
- **复核结论**：**确认**。`grep QQ_HOME_CHANNEL tests/` 仅命中 `tests/hermes_cli/test_doctor.py:1383-1384`
  （doctor 测试里的 `delenv` 清场），status 侧一条都没有。
