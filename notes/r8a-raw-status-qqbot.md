# r8a-raw-status-qqbot · status.py(含 QQBot 环境变量倒置定案)

底稿。求全求证,不求好读。溯源约定:所有 `路径:行号 @ 863e313` 中的路径相对 hermes-agent
仓库根,行号对应 commit `863e31318553cda8ad61df681d08175364d4164b`。

阅读范围:`hermes_cli/status.py` 全文 696 行,逐行读完(分三次 Read:1-250 / 250-499 / 499-696)。
交叉取证涉及 `gateway/config.py`、`cron/scheduler.py`、`hermes_cli/{gateway,setup,doctor,config,
config_defaults,subcommands/status,vercel_auth,active_sessions,models,timefmt,auth}.py`、
`gateway/{status,platform_registry}.py`、`gateway/platforms/api_server.py`、
`tools/tool_backend_helpers.py`、`agent/redact.py`、`plugins/google_meet/node/cli.py`、
`website/docs/**`、`tests/hermes_cli/test_status*.py`。

实跑验证使用只读运行(不改仓库任何文件),`HERMES_HOME` 指向 scratchpad 临时目录,
解释器 `/home/user/hermes-venv/bin/python`。

---

## 0. 一句话结论

`hermes status` 是一个**无状态、无异常边界、纯打印**的诊断面板:它自己不做任何"判定逻辑的
唯一真相",而是把十几个子系统各自的 `*_status()` / `*_snapshot()` / `describe_*()` 结果拼成一屏
文本。它的设计取舍是"永不崩、永不改状态、永不花钱",代价是**判据与真正的运行时判据会各自漂移**
—— 本段查到 4 处已经漂移的地方,QQBot 环境变量倒置是其中最严重的一处。

---

## 1. 文件骨架(696 行都在干什么)

模块 docstring 只有一句话,没有承诺任何契约。`hermes_cli/status.py:1-5 @ 863e313`

```python
"""
Status command for hermes CLI.

Shows the status of all Hermes Agent components.
"""
```

模块顶层导入 `subprocess` 但**全文一次都不调用**,注释明写这是给测试 monkeypatch 用的再导出。
`hermes_cli/status.py:11 @ 863e313`

```python
import subprocess  # noqa: F401 — re-exported for tests that monkeypatch status.subprocess to guard against regressions
```

> 为什么这招有效:`monkeypatch.setattr(status_mod.subprocess, "run", ...)` 拿到的是**共享的
> `subprocess` 模块对象**,给它打补丁会影响进程内所有 `import subprocess; subprocess.run(...)`
> 的调用点(包括 `hermes_cli.gateway` 里的 systemctl 探测)。所以这个"没人用的 import"实际上是
> 一个**全进程 subprocess 拦截把手**。测试用它断言 Termux 视图下不得调用 systemctl,见
> `tests/hermes_cli/test_status.py:39 @ 863e313`。

`PROJECT_ROOT` 在导入期即解析成安装目录的绝对路径,后面直接打印。`hermes_cli/status.py:14 @ 863e313`

```python
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
```

`show_status(args)` 是唯一入口,`args` 只被读一个字段。`hermes_cli/status.py:115-117 @ 863e313`

```python
def show_status(args):
    """Show status of all Hermes Agent components."""
    deep = getattr(args, 'deep', False)
```

之后按固定顺序打印 11 个区块(每块以 `◆ <标题>` 开头):
Environment / API Keys / Auth Providers / [Nous Tool Gateway] / API-Key Providers /
Terminal Backend / Messaging Platforms / Gateway Service / Scheduled Jobs / Sessions /
[Deep Checks],最后打印两行提示尾巴。`hermes_cli/status.py:692-696 @ 863e313`

```python
    print()
    print(color("─" * 60, Colors.DIM))
    print(color("  Run 'hermes doctor' for detailed diagnostics", Colors.DIM))
    print(color("  Run 'hermes setup' to configure", Colors.DIM))
    print()
```

---

## 2. 机制逐条

### 2.1 「尽力显示」的异常策略 —— 解决什么问题

**问题**:诊断面板最容易在"系统坏了"的时候被运行。如果任何一个子系统探测抛异常就整屏崩溃,
面板在最需要它的场景下最没用。

**怎么实现**:全文用了 **11 个独立的 `try/except Exception`**,粒度是"一个区块一个",而不是
函数级。典型:配置读失败退化成空 dict,后面所有 `config.get(...)` 仍然安全。
`hermes_cli/status.py:135-138 @ 863e313`

```python
    try:
        config = load_config()
    except Exception:
        config = {}
```

OAuth 四家一起包一层,任何一家的 import 或调用炸掉,四家一起退化成空 dict。
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

xAI 被**故意拆成单独一个 try**,注释写明理由是不让它的 import 失败拖累上面已经打印的四行。
`hermes_cli/status.py:320-326 @ 863e313`

```python
    # xAI OAuth — separate try/except so an import failure here cannot
    # disrupt the already-printed Nous/Codex/Qwen/MiniMax rows above.
    try:
        from hermes_cli.auth import get_xai_oauth_auth_status
        xai_oauth_status = get_xai_oauth_auth_status() or {}
    except Exception:
        xai_oauth_status = {}
```

**取舍**:这是**静默吞异常**的合法用法(显示层),但代价明确 —— 用户看到的"✗ not logged in"
可能真的是没登录,也可能是探测函数炸了。除了 Nous 之外,大部分区块**不打印错误原因**。
`tests/hermes_cli/test_status.py:148-199 @ 863e313` 把这一策略钉成了行为规格(import 失败 /
函数抛异常 / 函数返回 None 三种都必须不崩且仍打印表头)。

**已被规格钉死的一条**:`hermes status` 绝不触发 OAuth refresh。用的是 refresh-free 快照,
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

> 这是本文件里最值得抄的一条设计:**只读面板必须有一条"只读版"的状态查询 API**,否则
> "看一眼状态"会消耗一次性 refresh token,把用户踢下线。

### 2.2 打勾符号与密钥脱敏

`check_mark` 把 bool 变成绿✓/红✗,是全文所有健康判定的唯一渲染出口。
`hermes_cli/status.py:30-33 @ 863e313`

```python
def check_mark(ok: bool) -> str:
    if ok:
        return color("✓", Colors.GREEN)
    return color("✗", Colors.RED)
```

`redact_key` 是 `agent.redact.mask_secret` 的薄包装,只做一件额外的事:把空值渲染成
DIM 色的 `(not set)`,与 `hermes config` 对齐。`hermes_cli/status.py:35-44 @ 863e313`

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

底层默认保留首 4 尾 4,短于阈值全遮。`agent/redact.py:442-450 @ 863e313`

```python
def mask_secret(
    value: str,
    *,
    head: int = 4,
    tail: int = 4,
    floor: int = 12,
    placeholder: str = "***",
    empty: str = "",
) -> str:
```

`tests/hermes_cli/test_status.py:6-15 @ 863e313` 用一个哨兵值断言完整密钥绝不出现在输出里 ——
这是**面板可以被截图分享**这个隐含契约的唯一守卫。

### 2.3 两个时间格式化器

ISO 时间戳转本地时区,失败原样返回。`hermes_cli/status.py:47-63 @ 863e313`

```python
def _format_iso_timestamp(value) -> str:
    """Format ISO timestamps for status output, converting to local timezone."""
    if not value or not isinstance(value, str):
        return "(unknown)"
```

注意末尾 `Z` 被手工替换成 `+00:00`,因为 Python 3.10 及更早的 `fromisoformat` 不吃 `Z`。
`hermes_cli/status.py:55-56 @ 863e313`

```python
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
```

相对时间委托给 `hermes_cli.timefmt.relative_time`。`hermes_cli/status.py:66-70 @ 863e313`

```python
def _format_relative_ts(ts: float) -> str:
    """Format an epoch timestamp as a short relative age for status output."""
    from hermes_cli.timefmt import relative_time

    return relative_time(ts)
```

`hermes_cli/timefmt.py:15-19 @ 863e313`

```python
def relative_time(ts) -> str:
    """Format a timestamp as relative time (e.g., '2h ago', 'yesterday')."""
    if not ts:
        return "?"
    delta = _time.time() - ts
```

### 2.4 模型标签:兼容 `model` 是 str 也是 dict

**问题**:`config.yaml` 的 `model` 历史上既写过裸字符串,也写过 dict。

**实现**:dict 时取 `model.default`,退到 `model.name`;str 时直接用;都没有就 `(not set)`。
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

行为规格:`tests/hermes_cli/test_status_model_provider.py:33-51 @ 863e313`(dict 形态)。

### 2.5 provider 标签:为什么要额外造一个 `custom`

**场景**:用户把 `model.base_url` 指到自建 LiteLLM/vLLM 网关,但 provider 仍解析成
`openrouter`(OpenRouter 是 OpenAI 兼容协议的默认落点)。面板若照直写 "OpenRouter",用户
会以为自己在打 OpenRouter,排查方向全错。issue #3296 就是这个。

**实现**:先按运行时的解析链拿到 effective provider,若是 `openrouter` 且检测到自定义
base_url(config.yaml 优先,legacy `OPENAI_BASE_URL` 兜底),就改标 `custom`。
`hermes_cli/status.py:85-109 @ 863e313`

```python
def _effective_provider_label() -> str:
    """Return the provider label matching current CLI runtime resolution."""
    requested = resolve_requested_provider()
    try:
        effective = resolve_provider(requested)
    except AuthError:
        effective = requested or "auto"
```

关键判定行。`hermes_cli/status.py:106-107 @ 863e313`

```python
        if config_base_url or get_env_value("OPENAI_BASE_URL"):
            effective = "custom"
```

注释显式声明 config.yaml 是单一真相、env 是 legacy。`hermes_cli/status.py:94-98 @ 863e313`

```python
        # A custom endpoint may be configured either in config.yaml
        # (model.base_url — the canonical location; the runtime treats
        # config.yaml as the single source of truth) or via the legacy
        # OPENAI_BASE_URL env var. Either way, labeling it "OpenRouter"
        # is misleading (#3296).
```

`AuthError` 被吞掉并退回 `requested or "auto"`,意味着**"凭据缺失"这一事实在 Provider 行上
完全看不出来** —— 面板会显示一个看起来正常的 provider 名。行为规格
`tests/hermes_cli/test_status_provider_label.py:17-30 @ 863e313`(三例:config base_url→custom、
空 base_url 保持 openrouter、非 openrouter 不动)。

**取舍/缺陷**:`_effective_provider_label()` 在 `show_status` 里被调用**两次**
(第 141 行打印、第 405 行做 LM Studio 判定),每次都完整跑一遍 `resolve_requested_provider()`
+ `resolve_provider()` + `load_config()`。纯重复开销,无缓存。

### 2.6 API Keys 区块:一张手写表 + 一个"跳过自己"的补丁

表结构:值可以是单个变量名,也可以是候选元组(先到先得)。`hermes_cli/status.py:149-153 @ 863e313`

```python
    # Values may be a single env var name (str) or a tuple of alternates (first found wins).
    keys: dict[str, str | tuple[str, ...]] = {
        "OpenRouter": "OPENROUTER_API_KEY",
        "OpenAI": "OPENAI_API_KEY",
        "Anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN"),
```

解析器。`hermes_cli/status.py:173-181 @ 863e313`

```python
    def _resolve_env(env_ref) -> str:
        """Return first non-empty env var value from a str or tuple of names."""
        if isinstance(env_ref, tuple):
            for candidate in env_ref:
                v = get_env_value(candidate) or ""
                if v:
                    return v
            return ""
        return get_env_value(env_ref) or ""
```

**Anthropic 那一行是死数据**:循环体第一件事就是 `continue` 掉它,真正的 Anthropic 行由下面
专门的 `get_anthropic_key()` 打印(它还能解析 OAuth token)。`hermes_cli/status.py:183-192 @ 863e313`

```python
    for name, env_ref in keys.items():
        # Anthropic already has a dedicated lookup below; keep that as the
        # single source of truth (it also resolves OAuth tokens), skip here
        # so we don't print two "Anthropic" rows.
        if name == "Anthropic":
            continue
        value = _resolve_env(env_ref)
        has_key = bool(value)
        display = redact_key(value)
        print(f"  {name:<12}  {check_mark(has_key)} {display}")
```

`hermes_cli/status.py:194-197 @ 863e313`

```python
    from hermes_cli.auth import get_anthropic_key
    anthropic_value = get_anthropic_key()
    anthropic_display = redact_key(anthropic_value)
    print(f"  {'Anthropic':<12}  {check_mark(bool(anthropic_value))} {anthropic_display}")
```

> 即:`("ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN")` 这个元组**永远不会被读**。留着它有点像
> 文档(说明这两个名字存在),但它是死代码,改它不会改变任何行为 —— 这本身是个陷阱:
> 有人给它加第三个别名会以为生效了。

### 2.7 Auth Providers 区块

五家 OAuth 各打一行主状态 + 若干缩进细节行。Nous 最复杂:它有三个正交的"登录"概念 ——
portal 登录 / inference 凭据存在 / 有 refresh token,面板把前两个合成一个三态标签。
`hermes_cli/status.py:246-251 @ 863e313`

```python
    if nous_logged_in:
        nous_label = "logged in"
    elif nous_inference_present:
        nous_label = "not logged in (Nous inference key configured)"
    else:
        nous_label = "not logged in (run: hermes portal)"
```

只有在本地快照露出某些字段时,才去打 portal 账号接口(避免无谓网络请求)。
`hermes_cli/status.py:224-235 @ 863e313`

```python
    nous_account_info = None
    if (
        nous_status.get("logged_in")
        or nous_status.get("access_token")
        or nous_status.get("portal_base_url")
        or nous_status.get("inference_credential_present")
        or nous_status.get("error_code")
    ):
        try:
            nous_account_info = get_nous_portal_account_info()
        except Exception:
            nous_account_info = None
```

细节行全部是**条件打印**(有值才印),这是面板"不刷屏"的一致手法,例如
`hermes_cli/status.py:282-284 @ 863e313`

```python
    codex_auth_file = codex_status.get("auth_store")
    if codex_auth_file:
        print(f"    Auth file:  {codex_auth_file}")
```

`tests/hermes_cli/test_status.py:123-135 @ 863e313` 把"字段缺失就不能出现该行"钉成规格
(它是靠切分 `xAI OAuth` 到下一个 `◆` 之间的片段来断言的 —— 说明**区块分隔符 `◆` 是被测试
依赖的输出契约**)。

### 2.8 Nous Tool Gateway 区块

**门槛函数**在模块顶层导入,判定"是否有任何托管工具可用"。`hermes_cli/status.py:344 @ 863e313`

```python
    if managed_nous_tools_enabled():
```

它 fail-closed 且吞掉所有异常。`tools/tool_backend_helpers.py:20-32 @ 863e313`

```python
def managed_nous_tools_enabled(*, force_fresh: bool = False) -> bool:
    """Return True when the user is entitled to the Nous Tool Gateway.

    Entitlement is paid Nous Portal service access OR a live free tool pool
    (``tool_gateway_entitled``). Per-category coverage (the pool funds image but
    not video, etc.) is narrowed by callers via ``tool_gateway_entitled_for``;
    this coarse gate only answers "is any managed tool usable at all".

    Tool Gateway availability fails closed on unknown/error entitlement.  We
    intentionally catch all exceptions and return False — never block startup.
    ``force_fresh=True`` is for interactive configuration flows that should
    reflect a just-purchased subscription, credits, or pool grant immediately.
    """
```

有权益时逐 feature 打五态标签。`hermes_cli/status.py:352-364 @ 863e313`

```python
        for feature in features.items():
            if feature.managed_by_nous:
                state = "active via Nous subscription"
            elif feature.active:
                current = feature.current_provider or "configured provider"
                state = f"active via {current}"
            elif feature.included_by_default and features.nous_auth_present:
                state = "included by subscription, not currently selected"
            elif feature.key == "modal" and features.nous_auth_present:
                state = "available via subscription (optional)"
            else:
                state = "not configured"
            print(f"  {feature.label:<15} {check_mark(feature.available or feature.active or feature.managed_by_nous)} {state}")
```

无权益但登录过 / 有 inference key 时,改印一段"为什么用不了"的说明。
`hermes_cli/status.py:365-376 @ 863e313`

```python
    elif nous_logged_in or nous_inference_present:
        # Nous OAuth without entitlement, or an opaque inference key without
        # Portal account information, cannot enable the Tool Gateway.
        print()
        print(color("◆ Nous Tool Gateway", Colors.CYAN, Colors.BOLD))
        message = format_nous_portal_entitlement_message(
            nous_account_info,
            capability="managed web, image, TTS, STT, browser, and Modal tools",
        )
```

`get_nous_subscription_features(config)` 会再读一大批 config.yaml 键(`model.provider`、
`web.backend` / `web.search_backend`、`tts.provider`、`stt.provider`、`browser.cloud_provider`、
`terminal.backend`,以及 toolset 开关 web / image_gen / video_gen / tts / browser / terminal),
见 `hermes_cli/nous_subscription.py:380-407 @ 863e313`

```python
    web_tool_enabled = _toolset_enabled(config, "web")
```

> 这些键**不是 status.py 自己读的**,但它们通过 status.py 传进去的 `config` 影响面板输出,
> 已在第 4 节的键表里标注为「间接」。

### 2.9 API-Key Providers 区块 + LM Studio 探测

第二张手写表,同一批中国区/新兴 provider **再打印一遍**,但候选变量集合与 2.6 那张表**不同**。
`hermes_cli/status.py:384-391 @ 863e313`

```python
    apikey_providers = {
        "Z.AI / GLM":       ("GLM_API_KEY", "ZAI_API_KEY", "Z_AI_API_KEY"),
        "Kimi / Moonshot":  ("KIMI_API_KEY",),
        "StepFun Step Plan": ("STEPFUN_API_KEY",),
        "MiniMax":          ("MINIMAX_API_KEY",),
        "MiniMax (China)":  ("MINIMAX_CN_API_KEY",),
        "DeepInfra":        ("DEEPINFRA_API_KEY",),
    }
```

**实测的自相矛盾**(见第 6 节 D-2):只设 `ZAI_API_KEY` 时,同一屏里
`Z.AI / GLM ✗ (not set)`(API Keys 区块,只认 `GLM_API_KEY`)与
`Z.AI / GLM ✓ configured`(API-Key Providers 区块,认三个别名)同时出现。

LM Studio 只在它是当前 provider 时探测,理由写在注释里(避免噪音)。
`hermes_cli/status.py:402-408 @ 863e313`

```python
    # LM Studio reachability — only probe when it's the active provider so
    # users with foreign configs don't see noise. Auth rejection vs. silent
    # empty list is the most common LM Studio support case.
    if _effective_provider_label() == "LM Studio":
        from hermes_cli.models import probe_lmstudio_models
        model_cfg = config.get("model")
        base = (model_cfg.get("base_url") if isinstance(model_cfg, dict) else None) or get_env_value("LM_BASE_URL") or "http://127.0.0.1:1234/v1"
```

三态判定(None=不可达 / 列表=可达含空表 / AuthError=鉴权拒绝),超时 1.5s。
`hermes_cli/status.py:409-417 @ 863e313`

```python
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

"空列表 ≠ 不可达"是被底层函数明确承诺的语义。`hermes_cli/models.py:3667-3681 @ 863e313`

```python
def probe_lmstudio_models(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 5.0,
) -> Optional[list[str]]:
    """Probe LM Studio's model listing.

    Returns chat-capable model keys on success, including the valid empty-list
    case when the server is reachable but has no non-embedding models.
    Returns ``None`` on network errors, malformed responses, or empty/invalid
    base URLs.

    Raises ``AuthError`` on HTTP 401/403 so callers can surface token issues
    separately from reachability problems.
    """
```

行为规格 `tests/hermes_cli/test_status_model_provider.py:54-82 @ 863e313`(空列表必须显示
`reachable (0 model(s))`)。

**注意判据用的是显示标签而不是 provider id**:`_effective_provider_label() == "LM Studio"`。
标签由 `provider_label()` 从表里查。`hermes_cli/models.py:2548-2555 @ 863e313`

```python
def provider_label(provider: Optional[str]) -> str:
    """Return a human-friendly label for a provider id or alias."""
    original = (provider or "openrouter").strip()
    normalized = original.lower()
    if normalized == "auto":
        return "Auto"
    normalized = normalize_provider(normalized)
    return _PROVIDER_LABELS.get(normalized, original or "OpenRouter")
```

标签当前确实是 `"LM Studio"`(`hermes_cli/models.py:1119 @ 863e313`)

```python
    ProviderEntry("lmstudio",       "LM Studio",                "LM Studio (Local desktop app with built-in model server)"),
```

**取舍/隐患**:任何人改这个**展示文案**(比如做 i18n、或改成 "LM Studio (local)"),LM Studio
探测就会静默失效,没有任何测试会红。判据应当用 provider id 而不是 label。

### 2.10 Terminal Backend 区块

**backend 解析顺序**:env 优先,config 兜底,默认 `local`。`hermes_cli/status.py:425-429 @ 863e313`

```python
    terminal_cfg = config.get("terminal", {}) if isinstance(config.get("terminal"), dict) else {}
    terminal_env = os.getenv("TERMINAL_ENV", "")
    if not terminal_env:
        terminal_env = terminal_cfg.get("backend", "local")
    print(f"  Backend:      {terminal_env}")
```

> 这与 `hermes_cli/env_loader.py` 里的注释("config.yaml is the documented source of truth for
> terminal.* settings")方向相反 —— 见第 5 节 C-3。

ssh / docker / daytona 三个分支只是打印 env 值与默认值。`hermes_cli/status.py:431-441 @ 863e313`

```python
    if terminal_env == "ssh":
        ssh_host = os.getenv("TERMINAL_SSH_HOST", "")
        ssh_user = os.getenv("TERMINAL_SSH_USER", "")
        print(f"  SSH Host:     {ssh_host or '(not set)'}")
        print(f"  SSH User:     {ssh_user or '(not set)'}")
    elif terminal_env == "docker":
        docker_image = os.getenv("TERMINAL_DOCKER_IMAGE", "python:3.11-slim")
        print(f"  Docker Image: {docker_image}")
    elif terminal_env == "daytona":
        daytona_image = os.getenv("TERMINAL_DAYTONA_IMAGE", "nikolaik/python-nodejs:python3.11-nodejs20")
        print(f"  Daytona Image: {daytona_image}")
```

vercel_sandbox 分支最厚:runtime 三级 fallback、持久化布尔三态(env 未设→读 config、
env 已设→按真值串解析)、SDK 是否装、鉴权模式、以及一条**硬编码的行为契约提示**。
`hermes_cli/status.py:442-458 @ 863e313`

```python
    elif terminal_env == "vercel_sandbox":
        runtime = os.getenv("TERMINAL_VERCEL_RUNTIME") or terminal_cfg.get("vercel_runtime") or "node24"
        persist = os.getenv("TERMINAL_CONTAINER_PERSISTENT")
        if persist is None:
            persist_enabled = bool(terminal_cfg.get("container_persistent", True))
        else:
            persist_enabled = persist.lower() in {"1", "true", "yes", "on"}
        auth_status = describe_vercel_auth()
        sdk_ok = importlib.util.find_spec("vercel") is not None
        sdk_label = "installed" if sdk_ok else "missing (install: pip install 'hermes-agent[vercel]')"
        print(f"  Runtime:      {runtime}")
        print(f"  SDK:          {check_mark(sdk_ok)} {sdk_label}")
        print(f"  Auth:         {check_mark(auth_status.ok)} {auth_status.label}")
        for line in auth_status.detail_lines:
            print(f"  Auth detail:  {line}")
        print(f"  Persistence:  {'snapshot filesystem' if persist_enabled else 'ephemeral filesystem'}")
        print("  Processes:    live processes do not survive cleanup, snapshots, or sandbox recreation")
```

Vercel 鉴权的四态判定不在 status.py,而在专门的 describer 里(OIDC / 完整三件套 / 部分 /
未配置),它只判断变量**存在与否**,不打印任何值。`hermes_cli/vercel_auth.py:19-29 @ 863e313`

```python
def _present(name: str) -> bool:
    return bool(os.getenv(name))


def describe_vercel_auth() -> VercelAuthStatus:
    """Return Vercel auth status without exposing secret values."""

    has_oidc = _present("VERCEL_OIDC_TOKEN")
    token_states = {name: _present(name) for name in _TOKEN_TUPLE_VARS}
```

`hermes_cli/vercel_auth.py:9 @ 863e313`

```python
_TOKEN_TUPLE_VARS = ("VERCEL_TOKEN", "VERCEL_PROJECT_ID", "VERCEL_TEAM_ID")
```

整段行为规格:`tests/hermes_cli/test_status.py:47-75 @ 863e313`(含"token 值不得出现在输出中")。

sudo 只看有没有密码。`hermes_cli/status.py:460-461 @ 863e313`

```python
    sudo_password = os.getenv("SUDO_PASSWORD", "")
    print(f"  Sudo:         {check_mark(bool(sudo_password))} {'enabled' if sudo_password else 'disabled'}")
```

### 2.11 Messaging Platforms 区块(QQ 定案见第 3 节)

一张 15 行的手写表,每项是 `(token 变量, home 频道变量 or None)`。
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

渲染循环:token 存在=configured,home 频道有值就追加 `(home: …)`。
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

**这里"configured"的判据是"单个 token 变量非空"**,而 gateway 真正启用平台的判据往往不同。
例如 Yuanbao 在网关侧要求 **两个**变量都有,而且 app_id 还接受一个别名:
`gateway/config.py:2456-2459 @ 863e313`

```python
    # Yuanbao — YUANBAO_APP_ID preferred
    yuanbao_app_id = getenv("YUANBAO_APP_ID") or getenv("YUANBAO_APP_KEY")
    yuanbao_app_secret = getenv("YUANBAO_APP_SECRET")
    if yuanbao_app_id and yuanbao_app_secret:
```

→ 只设 `YUANBAO_APP_ID`:面板 ✓ configured,网关不启用;只设 `YUANBAO_APP_KEY` + secret:
网关启用,面板 ✗ not configured。QQ 也一样,网关是 `or` 语义:
`gateway/config.py:2415-2417 @ 863e313`

```python
    qq_app_id = getenv("QQ_APP_ID")
    qq_client_secret = getenv("QQ_CLIENT_SECRET")
    if qq_app_id or qq_client_secret:
```

**这张表还漏掉了若干内置平台**:`Platform` 枚举里有 `whatsapp_cloud`、`mattermost`、`matrix`、
`homeassistant` 等,面板表里一个都没有。`gateway/config.py:272-289 @ 863e313`

```python
class Platform(Enum):
    """Supported messaging platforms.

    Built-in platforms have explicit members.  Plugin platforms use dynamic
    members created on-demand by ``_missing_()`` so that
    ``Platform("irc")`` works without modifying this enum.  Dynamic members
    are cached in ``_value2member_map_`` for identity-stable comparisons.
    """
    LOCAL = "local"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    WHATSAPP_CLOUD = "whatsapp_cloud"
    SLACK = "slack"
    SIGNAL = "signal"
    MATTERMOST = "mattermost"
    MATRIX = "matrix"
    HOMEASSISTANT = "homeassistant"
```

### 2.12 插件平台区块 —— 实测在 `hermes status` 路径里恒为空

代码本意是把插件注册的平台也列出来。`hermes_cli/status.py:504-513 @ 863e313`

```python
    # Plugin-registered platforms
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

`plugin_entries()` 只返回**已经被 discover 进注册表**的条目。`gateway/platform_registry.py:266-269 @ 863e313`

```python
    def plugin_entries(self) -> list[PlatformEntry]:
        """Return only plugin-registered platform entries."""
        self._resolve_all()
        return [e for e in self._entries.values() if e.source == "plugin"]
```

而 `hermes status` 这条 CLI 路径**不触发插件发现** —— main.py 里的注释明说内置子命令为了省
~500ms 启动时间跳过了发现,只有 dashboard 这类需要的才显式补一刀。
`hermes_cli/main.py:10460-10466 @ 863e313`

```python
    # plugin discovery for built-in subcommands like ``dashboard`` to
    # save ~500ms startup; we have to trigger it explicitly here because
    # the dashboard's server-side runtime depends on plugin-registered
    # providers (image_gen, web, dashboard_auth, …).
    try:
        from hermes_cli.plugins import discover_plugins
        discover_plugins()
```

对照:`hermes setup gateway` 的平台枚举**会**先发现插件。`hermes_cli/gateway.py:5390-5393 @ 863e313`

```python
    try:
        from hermes_cli.plugins import discover_plugins

        discover_plugins()
```

**实测(只读运行,未改任何文件)**:

```
$ HERMES_HOME=<tmp> python -c "import sys; sys.argv=['hermes','status']; from hermes_cli.main import main; main()"
◆ Messaging Platforms
  Telegram      ✗ not configured
  … (共 15 行,全部来自 status.py 的手写表)
  Yuanbao       ✗ not configured

◆ Gateway Service            ← 一条 (plugin) 行都没有
```

```
$ python -c "from gateway.platform_registry import platform_registry as r; print(len(r.plugin_entries()))"
0
$ python -c "from hermes_cli.plugins import discover_plugins as d; d(); from gateway.platform_registry import platform_registry as r; print(len(r.plugin_entries()))"
23
```

发现之后的 23 个里包含 `irc / matrix / mattermost / line / teams / google_chat / ntfy /
simplex / photon / a2a / buzz / raft / homeassistant` —— 这些平台**在 `hermes status` 里永远
看不到**。同时 `telegram / discord / slack / email / sms / dingtalk / feishu / wecom /
whatsapp / wecom_callback` 已经迁成插件(`plugins/platforms/` 下都有目录),它们之所以还能显示,
纯粹是因为 status.py 的手写表里也硬编码了一份 —— 一旦插件发现在某条路径上被触发,这些平台
**会打印两行**(一行来自手写表,一行带 `(plugin)` 后缀)。

还有一个**语义错配**:插件行把 `check_fn()` 的结果标成 "configured",但注册表对该回调的定义是
"依赖是否可用",不是"是否配置好了"。`gateway/platform_registry.py:53-54 @ 863e313`

```python
    # Returns True when the platform's dependencies are available.
    check_fn: Callable[[], bool]
```

实测 `discover_plugins()` 之后 `check_fn()` 为 True 的有 telegram / discord / slack / whatsapp /
feishu / wecom / mattermost / homeassistant / photon / a2a —— 在**完全空配置**的环境下。
也就是说这些行如果真被打印出来,会全部显示 "✓ configured",而实际上一个都没配。

### 2.13 Gateway Service 区块

主路径用统一快照,except 分支按平台猜一个"unknown"。`hermes_cli/status.py:521-536 @ 863e313`

```python
    try:
        from hermes_cli.gateway import get_gateway_runtime_snapshot, _format_gateway_pids

        snapshot = get_gateway_runtime_snapshot()
        is_running = snapshot.running
        print(f"  Status:       {check_mark(is_running)} {'running' if is_running else 'stopped'}")
        print(f"  Manager:      {snapshot.manager}")
        if snapshot.gateway_pids:
            print(f"  PID(s):       {_format_gateway_pids(snapshot.gateway_pids)}")
        if snapshot.has_process_service_mismatch:
            print("  Service:      installed but not managing the current running gateway")
        elif _is_termux() and not snapshot.gateway_pids:
            print("  Start with:   hermes gateway")
            print("  Note:         Android may stop background jobs when Termux is suspended")
        elif snapshot.service_installed and not snapshot.service_running:
            print("  Service:      installed but stopped")
```

manager 文案由快照给,Termux 分支在快照函数里。`hermes_cli/gateway.py:1306-1313 @ 863e313`

```python
def get_gateway_runtime_snapshot(system: bool = False) -> GatewayRuntimeSnapshot:
    """Return a unified view of gateway liveness for the current profile."""
    gateway_pids = tuple(find_gateway_pids())
    if is_termux():
        return GatewayRuntimeSnapshot(
            manager="Termux / manual process",
            gateway_pids=gateway_pids,
        )
```

except 分支是"猜平台"的降级文案。`hermes_cli/status.py:537-549 @ 863e313`

```python
    except Exception:
        if _is_termux():
            print(f"  Status:       {color('unknown', Colors.DIM)}")
            print("  Manager:      Termux / manual process")
        elif sys.platform.startswith('linux'):
            print(f"  Status:       {color('unknown', Colors.DIM)}")
            print("  Manager:      systemd/manual")
        elif sys.platform == 'darwin':
            print(f"  Status:       {color('unknown', Colors.DIM)}")
            print("  Manager:      launchd")
        else:
            print(f"  Status:       {color('N/A', Colors.DIM)}")
            print("  Manager:      (not supported on this platform)")
```

> gateway 存活判定的真相是 **PID 文件**,不是端口。`gateway/status.py:4-11 @ 863e313`
> ```python
> Provides PID-file based detection of whether the gateway daemon is running,
> ```
> 这一点与第 2.16 节的端口探测直接冲突。

### 2.14 Scheduled Jobs 区块

jobs.json 路径固定在 `<HERMES_HOME>/cron/jobs.json`。`hermes_cli/status.py:557-559 @ 863e313`

```python
    jobs_file = get_hermes_home() / "cron" / "jobs.json"
    if jobs_file.exists():
        import json
```

读文件、数 job、区分 active 与 total。`hermes_cli/status.py:564-567 @ 863e313`

```python
                data = json.load(f)
                jobs = data.get("jobs", [])
                enabled_jobs = [j for j in jobs if j.get("enabled", True)]
                print(f"  Jobs:         {len(enabled_jobs)} active, {len(jobs)} total")
```

任何读取失败都退化成一行文案,不打印原因。`hermes_cli/status.py:568-571 @ 863e313`

```python
        except Exception:
            print("  Jobs:         (error reading jobs file)")
    else:
        print("  Jobs:         0")
```

`enabled` 缺省视为 True。`hermes_cli/status.py:566 @ 863e313`

```python
                enabled_jobs = [j for j in jobs if j.get("enabled", True)]
```

BOM 容忍是真的踩过坑(有专门测试 `tests/hermes_cli/test_jobs_json_utf8_bom.py`)。
`hermes_cli/status.py:561-563 @ 863e313`

```python
            # utf-8-sig: same dialect as cron/jobs.load_jobs — Windows editors
            # may leave a UTF-8 BOM that plain utf-8 json.load rejects.
            with open(jobs_file, encoding="utf-8-sig") as f:
```

### 2.15 Sessions 区块 + 并发槽位

会话数以 `state.db` 为准,失败退到 `sessions.json`(迁移前的老装机)。
`hermes_cli/status.py:579-582 @ 863e313`

```python
    # Gateway session count: state.db is the source of truth (#9006);
    # fall back to sessions.json for pre-migration installs.
    _session_count = None
    _gateway_rows = []
```

用 `getattr` + `callable` 做鸭子类型探测,兼容旧 SessionDB 没有这个方法的情况;`finally` 里
关连接,避免 SQLite 句柄泄漏。`hermes_cli/status.py:584-592 @ 863e313`

```python
        from hermes_state import SessionDB
        _db = SessionDB()
        try:
            _lister = getattr(_db, "list_gateway_sessions", None)
            if callable(_lister):
                _gateway_rows = _lister(active_only=True) or []
                _session_count = len(_gateway_rows)
        finally:
            _db.close()
```

最新活跃时间取所有行的最大值。`hermes_cli/status.py:599-604 @ 863e313`

```python
        freshest = max(
            (float(r.get("last_active") or 0) for r in _gateway_rows),
            default=0.0,
        )
        if freshest > 0:
            print(f"  Last activity:{_format_relative_ts(freshest):>13}")
```

fallback 路径过滤掉下划线开头的元数据键。`hermes_cli/status.py:606-616 @ 863e313`

```python
        sessions_file = get_hermes_home() / "sessions" / "sessions.json"
        if sessions_file.exists():
            import json
            try:
                with open(sessions_file, encoding="utf-8") as f:
                    data = json.load(f)
                    _entries = {
                        k: v for k, v in data.items()
                        if not str(k).startswith("_")
                    } if isinstance(data, dict) else {}
                    print(f"  Active:       {len(_entries)} session(s)")
```

槽位区块的存在理由写得很清楚:上限是**跨界面共享的**,被拒的界面往往不是占坑的那个。
`hermes_cli/status.py:622-633 @ 863e313`

```python
    # Slot usage, only when max_concurrent_sessions is set. The cap is shared
    # across CLI, desktop/TUI and the messaging gateway, so the surface that
    # gets rejected is rarely the one holding the slots — without this the only
    # way to find out is reading runtime/active_sessions.json by hand.
    try:
        from hermes_cli.active_sessions import (
            active_session_registry_snapshot,
            format_age,
            resolve_max_concurrent_sessions,
        )

        _cap = resolve_max_concurrent_sessions(config)
```

上限键有 fallback 链:顶层 `max_concurrent_sessions` → `gateway.max_concurrent_sessions`。
`hermes_cli/active_sessions.py:56-70 @ 863e313`

```python
def resolve_max_concurrent_sessions(config: Any) -> Optional[int]:
    """Resolve top-level max_concurrent_sessions with gateway.* fallback."""
    raw: Any = None
    key = "max_concurrent_sessions"
    if isinstance(config, dict):
        if "max_concurrent_sessions" in config:
            raw = config.get("max_concurrent_sessions")
        else:
            gateway_cfg = config.get("gateway")
            if isinstance(gateway_cfg, dict):
                raw = gateway_cfg.get("max_concurrent_sessions")
                key = "gateway.max_concurrent_sessions"
    else:
        raw = getattr(config, "max_concurrent_sessions", None)
    return coerce_max_concurrent_sessions(raw, key=key)
```

满槽变黄。`hermes_cli/status.py:641-647 @ 863e313`

```python
        _full = len(_held) >= _cap
        print(
            "  Slots:        "
            + color(
                f"{len(_held)}/{_cap} in use", Colors.YELLOW if _full else Colors.GREEN
            )
        )
```

### 2.16 Deep Checks 区块

只在 `--deep` 时跑,两件事:OpenRouter 连通性(10s 超时的真实 HTTP)与端口探测。
`hermes_cli/status.py:659-676 @ 863e313`

```python
    if deep:
        print()
        print(color("◆ Deep Checks", Colors.CYAN, Colors.BOLD))
        
        # Check OpenRouter connectivity
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        if openrouter_key:
            try:
                import httpx
                response = httpx.get(
                    OPENROUTER_MODELS_URL,
                    headers={"Authorization": f"Bearer {openrouter_key}"},
                    timeout=10
                )
                ok = response.status_code == 200
                print(f"  OpenRouter:   {check_mark(ok)} {'reachable' if ok else f'error ({response.status_code})'}")
            except Exception as e:
                print(f"  OpenRouter:   {check_mark(False)} error: {e}")
```

端口探测。`hermes_cli/status.py:678-690 @ 863e313`

```python
        # Check gateway port
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', 18789))
            sock.close()
            # Port in use = gateway likely running
            port_in_use = result == 0
            # This is informational, not necessarily bad
            print(f"  Port 18789:   {'in use' if port_in_use else 'available'}")
        except OSError:
            pass
```

**18789 与 gateway 无关**(见第 6 节 D-4):全仓 grep,这个数字只出现在 status.py 和
google_meet 插件的 node 服务里。`plugins/google_meet/node/cli.py:31 @ 863e313`

```python
    run.add_argument("--port", type=int, default=18789)
```

真正会监听端口的内置平台是 api_server,默认 8642。`gateway/platforms/api_server.py:150-151 @ 863e313`

```python
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8642
```

---

## 3. 【定案】QQBot 环境变量倒置

移交项原文:*"安装向导写的是新环境变量名,而 status 面板读的是旧名,且用于向后兼容的分支恒假。"*

**结论:三条全部成立**,并且我在实跑中复现了用户可见现象。下面给完整论证链。

### 3.1 新名与旧名分别是什么

**新名(canonical)= `QQBOT_HOME_CHANNEL`;旧名(legacy)= `QQ_HOME_CHANNEL`。**

网关配置层把新名写死成主键,旧名只作兜底并打 deprecation 警告 —— 这是"哪个是新名"的权威判据。
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

`hermes doctor` 把旧名列进"已废弃环境变量",提示改用新名。`hermes_cli/doctor.py:258 @ 863e313`

```python
    ("QQ_HOME_CHANNEL", "QQBOT_HOME_CHANNEL"),
```

配置键白名单里也标了 legacy。`hermes_cli/config.py:288-289 @ 863e313`

```python
    "QQ_APP_ID", "QQ_CLIENT_SECRET", "QQBOT_HOME_CHANNEL", "QQBOT_HOME_CHANNEL_NAME",
    "QQ_HOME_CHANNEL", "QQ_HOME_CHANNEL_NAME",  # legacy aliases (pre-rename, still read for back-compat)
```

变量元数据表里只登记新名。`hermes_cli/config_defaults.py:4142-4146 @ 863e313`

```python
    "QQBOT_HOME_CHANNEL": {
        "description": "Default QQ channel/group for cron delivery and notifications",
        "prompt": "QQ Home Channel",
        "category": "messaging",
    },
```

注意:`QQ_APP_ID` **没有**改名 —— 改名只发生在 home channel 这一对(以及 `*_NAME`、
`*_THREAD_ID` 变体)。所以 status.py 表里的 token 变量 `QQ_APP_ID` 是对的,错的只是 home 变量。

### 3.2 谁写新名

**(a) 交互式向导** `_setup_qqbot()` —— QR 扫码或手输凭据后,把 home channel 写成新名。
`hermes_cli/gateway.py:6126-6141 @ 863e313`

```python
    # ── Home channel ──
    if user_openid:
        print()
        if prompt_yes_no(
            f"  Use your QQ user ID ({user_openid}) as the home channel?", True
        ):
            save_env_value("QQBOT_HOME_CHANNEL", user_openid)
            print_success(f"  Home channel set to {user_openid}")
    else:
        print()
        home_channel = prompt(
            "  Home channel OpenID (for cron/notifications, or empty)", password=False
        )
        if home_channel:
            save_env_value("QQBOT_HOME_CHANNEL", home_channel.strip())
            print_success(f"  Home channel set to {home_channel.strip()}")
```

**(b) 通用平台向导表** `_PLATFORMS`(供 `hermes setup gateway` 逐项提问)也用新名。
`hermes_cli/gateway.py:5329-5334 @ 863e313`

```python
            {
                "name": "QQBOT_HOME_CHANNEL",
                "prompt": "Home channel (user/group OpenID for cron delivery, or empty)",
                "password": False,
                "help": "OpenID to deliver cron results and notifications to.",
            },
```

**(c) 桌面应用**的 messaging 设置面板也是新名。`apps/desktop/src/app/messaging/index.tsx:108 @ 863e313`

```tsx
  QQBOT_HOME_CHANNEL: { advanced: true },
```

**(d) 文档**只写新名。`website/docs/user-guide/messaging/qqbot.md:51 @ 863e313`

```markdown
| `QQBOT_HOME_CHANNEL` | OpenID for cron/notification delivery | — |
```

`website/docs/reference/environment-variables.md:476 @ 863e313`

```markdown
| `QQBOT_HOME_CHANNEL` | QQ user/group openID for cron delivery and notifications |
```

**(e) 消费侧**(cron 投递)以新名为主键、旧名为 legacy fallback,做法与网关一致。
`cron/scheduler.py:278 @ 863e313`

```python
    "qqbot": "QQBOT_HOME_CHANNEL",
```

`cron/scheduler.py:283-289 @ 863e313`

```python
# Legacy env var names kept for back-compat.  Each entry is the current
# primary env var → the previous name.  _get_home_target_chat_id falls
# back to the legacy name if the primary is unset, so users who set the
# old name before the rename keep working until they migrate.
_LEGACY_HOME_TARGET_ENV_VARS = {
    "QQBOT_HOME_CHANNEL": "QQ_HOME_CHANNEL",
}
```

`cron/scheduler.py:1043-1053 @ 863e313` —— **这是本仓库"新名主 + 旧名兜底"的标准写法**:

```python
def _get_home_target_chat_id(platform_name: str) -> str:
    """Return the configured home target chat/room ID for a delivery platform."""
    env_var = _resolve_home_env_var(platform_name)
    if not env_var:
        return ""
    value = os.getenv(env_var, "")
    if not value:
        legacy = _LEGACY_HOME_TARGET_ENV_VARS.get(env_var)
        if legacy:
            value = os.getenv(legacy, "")
    return value
```

**(f) 另一处 CLI 检查(`hermes setup` 的"没设 home 频道"提醒)写得完全正确 —— 两个名字都查**。
这条最能说明 status.py 是被漏改的那一处。`hermes_cli/setup.py:2217-2220 @ 863e313`

```python
        if get_env_value("QQ_APP_ID") and not (
            get_env_value("QQBOT_HOME_CHANNEL") or get_env_value("QQ_HOME_CHANNEL")
        ):
            missing_home.append("QQBot")
```

### 3.3 谁读旧名

**只有 status.py。** 表里 QQBot 的 home 变量直接写死成旧名:`hermes_cli/status.py:483 @ 863e313`

```python
        "QQBot": ("QQ_APP_ID", "QQ_HOME_CHANNEL"),
```

读取点:`hermes_cli/status.py:492-493 @ 863e313`

```python
        if home_var:
            home_channel = os.getenv(home_var, "")
```

### 3.4 back-compat 分支恒假 —— 逐字论证

分支原文:`hermes_cli/status.py:494-496 @ 863e313`

```python
        # Back-compat: QQBot home channel was renamed from QQ_HOME_CHANNEL to QQBOT_HOME_CHANNEL
        if not home_channel and home_var == "QQBOT_HOME_CHANNEL":
            home_channel = os.getenv("QQ_HOME_CHANNEL", "")
```

逐字分析条件 `not home_channel and home_var == "QQBOT_HOME_CHANNEL"`:

1. `home_var` 的取值来源**只有一处**:`for name, (token_var, home_var) in platforms.items()`
   (`hermes_cli/status.py:487 @ 863e313`),即 `platforms` 字典的第二个元素。
2. `platforms` 是 `show_status` 函数体内的**字面量**(`hermes_cli/status.py:469-485 @ 863e313`),
   在赋值到迭代之间没有任何写操作,也不暴露给外部,无法被 monkeypatch 之外的方式改动。
3. 枚举该字面量的全部 15 个 `home_var` 值:
   `TELEGRAM_HOME_CHANNEL`、`DISCORD_HOME_CHANNEL`、`None`、`SIGNAL_HOME_CHANNEL`、`None`、
   `EMAIL_HOME_ADDRESS`、`SMS_HOME_CHANNEL`、`None`、`FEISHU_HOME_CHANNEL`、
   `WECOM_HOME_CHANNEL`、`None`、`WEIXIN_HOME_CHANNEL`、`BLUEBUBBLES_HOME_CHANNEL`、
   **`QQ_HOME_CHANNEL`**、`YUANBAO_HOME_CHANNEL`。
4. **没有任何一个等于 `"QQBOT_HOME_CHANNEL"`。** 因此 `home_var == "QQBOT_HOME_CHANNEL"`
   在这个循环的每一次迭代中都为 `False`,与 `home_channel` 的取值无关。
5. 插件平台走的是**另一个循环**(`hermes_cli/status.py:507 @ 863e313`),不经过这段代码,
   也不产生 `home_var`。

→ **定案:该 `if` 条件恒假,第 496 行是不可达代码。** 该说法成立,不需要推翻。

**它的意图**:注释说的迁移方向("从 QQ_HOME_CHANNEL 改名为 QQBOT_HOME_CHANNEL")与网关、
cron、doctor 三处一致,是对的。正确的写法应当是表里放**新名**、fallback 读**旧名**;实际代码
把这两个名字**互换了位置**(表里放旧名、fallback 判定拿新名去比对),所以整个 back-compat
机制原地空转。这正是"倒置"二字的准确含义。

### 3.5 用户会看到什么(实跑复现)

**场景 A(最常见):用向导配好 QQBot。** 向导把 `QQBOT_HOME_CHANNEL` 写进 `~/.hermes/.env`
(证据见上文 3.2 (a) 的 `save_env_value("QQBOT_HOME_CHANNEL", ...)`)。用真实 CLI 入口跑
`hermes status`,实测输出:

```
$ cat $HERMES_HOME/.env
QQ_APP_ID=102xxxx
QQ_CLIENT_SECRET=sekret
QQBOT_HOME_CHANNEL=openid-FROM-WIZARD

$ python -c "import sys; sys.argv=['hermes','status']; from hermes_cli.main import main; main()" | grep QQBot
  QQBot         ✓ configured
```

→ **home 频道那一段完全不显示。** 用户看到的是"配好了但没有 home 频道",而实际上 cron 投递
是正常的(`cron/scheduler.py:1043-1053` 会正确解析)。这是一个**诊断假阴性**:面板说没有,
真相是有。用户接下来最可能做的事是"再设一遍 home 频道",而向导会写同一个变量,现象不变 ——
形成排查死循环。

**场景 B:老用户还在用旧名。** `QQ_HOME_CHANNEL=openid-LEGACY`:

```
  QQBot         ✓ configured (home: openid-LEGACY)
```

→ 显示正常。但 `hermes doctor` 会告诉他这个变量已废弃、请改成 `QQBOT_HOME_CHANNEL`
(`hermes_cli/doctor.py:258 @ 863e313`)。**他一照做,status 里的 home 频道就消失了。**
即:修复一个 deprecation 警告会让面板变差 —— 这是最容易让用户误判"我把配置改坏了"的组合。

**场景 C:其他平台无影响。** 该分支恒假,对 Telegram/Discord/… 十四个平台没有任何副作用,
所以这个 bug **只在 QQBot 一行上可见**,不会被其他平台的测试捕获。

**为什么一直没被发现**:`tests/` 下没有任何测试断言 status.py 的 QQBot 行 —— 我 grep 了
`tests/hermes_cli/test_status*.py` 全部三个文件,没有 "QQ" 字样;涉及 QQ 的测试
(`tests/gateway/test_qqbot*.py`、`tests/hermes_cli/test_doctor.py:1383-1384`)全部针对
网关/doctor,不覆盖面板。

---

## 4. 配置键 / 环境变量穷举

### 4.1 config.yaml 键(status.py 直接读)

| 键 | 默认 | 读取点 | 读它的函数 | fallback 链 |
|---|---|---|---|---|
| `model` | 无 | `hermes_cli/status.py:75` | `_configured_model_label` | 可为 str 或 dict |
| `model.default` | 无 | `hermes_cli/status.py:77` | `_configured_model_label` | → `model.name` → `(not set)` |
| `model.name` | 无 | `hermes_cli/status.py:77` | `_configured_model_label` | 上一条的兜底 |
| `model.base_url` | 无 | `hermes_cli/status.py:103` | `_effective_provider_label` | → env `OPENAI_BASE_URL`;命中则 provider 标 `custom` |
| `model.base_url` | 无 | `hermes_cli/status.py:408` | `show_status`(LM Studio) | → env `LM_BASE_URL` → `http://127.0.0.1:1234/v1` |
| `terminal` | `{}` | `hermes_cli/status.py:425` | `show_status` | 非 dict 时退化成 `{}` |
| `terminal.backend` | `local` | `hermes_cli/status.py:428` | `show_status` | **env `TERMINAL_ENV` 优先**,config 兜底 |
| `terminal.vercel_runtime` | `node24` | `hermes_cli/status.py:443` | `show_status` | env `TERMINAL_VERCEL_RUNTIME` → config → `node24` |
| `terminal.container_persistent` | `True` | `hermes_cli/status.py:446` | `show_status` | 仅当 env `TERMINAL_CONTAINER_PERSISTENT` **未设**时才读 config |
| `max_concurrent_sessions` | 无(None=不显示槽位) | `hermes_cli/active_sessions.py:61-62` | `resolve_max_concurrent_sessions` | → `gateway.max_concurrent_sessions` |
| `gateway.max_concurrent_sessions` | 无 | `hermes_cli/active_sessions.py:66` | 同上 | 顶层键的兜底 |

**间接**(status.py 把 `config` 整个传下去,由被调方读):
`model.provider`、`web.backend`、`web.search_backend`、`tts.provider`(默认 `edge`)、
`stt.provider`(默认 `local`)、`browser.cloud_provider`、`terminal.backend`,以及六个 toolset
开关 —— 全部在 `hermes_cli/nous_subscription.py:380-407 @ 863e313`,入口是
`hermes_cli/status.py:345`。

### 4.2 环境变量(status.py 直接读,分两类读法)

**A. 经 `get_env_value()` 读(会回落到 `~/.hermes/.env`,且走 secret_scope 作用域检查)**

读法定义:`hermes_cli/config.py:4109-4121 @ 863e313`

```python
def get_env_value(key: str) -> Optional[str]:
    """Get a value from ``os.environ`` or ``~/.hermes/.env``, scope-aware.

    The ``os.environ`` read routes through ``agent.secret_scope.get_secret``
    so that, under an active profile scope (multiplexed gateway turn), this
    is scope-checked rather than leaking another profile's raw ``os.environ``
    value. ``get_secret`` encodes the whole policy: global vars pass through;
    scope is authoritative under multiplexing (miss -> None, no environ
    fallthrough); when multiplexing is off it behaves exactly like the
    legacy ``os.environ`` read. Its siblings ``get_env_value_prefer_dotenv``
    and ``gateway.config._getenv`` already work this way — this was the last
    scope-blind reader of the trio (#67027).
    """
```

| 变量 | 默认 | 读取点 | 备注 |
|---|---|---|---|
| `OPENAI_BASE_URL` | — | `hermes_cli/status.py:106` | legacy;命中 → provider 标 `custom` |
| `OPENROUTER_API_KEY` | — | `hermes_cli/status.py:181`(表 151) | |
| `OPENAI_API_KEY` | — | 同上(表 152) | |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_TOKEN` | — | 表 153 | **死数据**,循环 187-188 跳过;实际走 `get_anthropic_key()`(194-195) |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | — | 表 154 | 元组,先到先得 |
| `DEEPSEEK_API_KEY` | — | 表 155 | |
| `XAI_API_KEY` | — | 表 156 | |
| `NVIDIA_API_KEY` | — | 表 157 | |
| `GLM_API_KEY` | — | 表 158 | 与 384 行那张表**不一致**(见 D-2) |
| `KIMI_API_KEY` | — | 表 159 / 386 | |
| `STEPFUN_API_KEY` | — | 表 160 / 387 | |
| `MINIMAX_API_KEY` | — | 表 161 / 388 | |
| `MINIMAX_CN_API_KEY` | — | 表 162 / 389 | |
| `DEEPINFRA_API_KEY` | — | 表 163 / 390 | |
| `FIRECRAWL_API_KEY` | — | 表 164 | |
| `TAVILY_API_KEY` | — | 表 165 | 有专门的"不得泄漏"测试 |
| `BROWSER_USE_API_KEY` | — | 表 166 | 注释:可选,本地浏览器不需要 |
| `BROWSERBASE_API_KEY` | — | 表 167 | 注释:仅直连凭据 |
| `FAL_KEY` | — | 表 168 | |
| `ELEVENLABS_API_KEY` | — | 表 169 | |
| `GITHUB_TOKEN` | — | 表 170 | |
| `ZAI_API_KEY` / `Z_AI_API_KEY` | — | `hermes_cli/status.py:385` | 只在第二张表里被认 |
| `LM_BASE_URL` | `http://127.0.0.1:1234/v1` | `hermes_cli/status.py:408` | config `model.base_url` 优先 |
| `LM_API_KEY` | `""` | `hermes_cli/status.py:410` | 401/403 → `auth rejected — set LM_API_KEY` |

**B. 经裸 `os.getenv()` 读(不回落 .env、不走 secret_scope)**

| 变量 | 默认 | 读取点 | 备注 |
|---|---|---|---|
| `TERMINAL_ENV` | `""` → config `terminal.backend` → `local` | `hermes_cli/status.py:426` | env 覆盖 config |
| `TERMINAL_SSH_HOST` | `""` → 显示 `(not set)` | `:432` | 仅 ssh 分支 |
| `TERMINAL_SSH_USER` | `""` → 显示 `(not set)` | `:433` | 仅 ssh 分支 |
| `TERMINAL_DOCKER_IMAGE` | `python:3.11-slim` | `:437` | 仅 docker 分支 |
| `TERMINAL_DAYTONA_IMAGE` | `nikolaik/python-nodejs:python3.11-nodejs20` | `:440` | 仅 daytona 分支 |
| `TERMINAL_VERCEL_RUNTIME` | → config `terminal.vercel_runtime` → `node24` | `:443` | |
| `TERMINAL_CONTAINER_PERSISTENT` | 未设→config(默认 True);已设→真值集 `{1,true,yes,on}` | `:444-448` | **注意**:设成 `""` 会被判为 False,而不是回落 config |
| `SUDO_PASSWORD` | `""` | `:460` | 仅判空,不显示值 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_HOME_CHANNEL` | `""` | `:488` / `:493`(表 470) | |
| `DISCORD_BOT_TOKEN` / `DISCORD_HOME_CHANNEL` | `""` | 表 471 | |
| `WHATSAPP_ENABLED` | `""` | 表 472 | home 变量为 `None`;而 cron 侧有 `WHATSAPP_HOME_CHANNEL` |
| `SIGNAL_HTTP_URL` / `SIGNAL_HOME_CHANNEL` | `""` | 表 473 | |
| `SLACK_BOT_TOKEN` | `""` | 表 474 | home 变量为 `None`;cron 侧有 `SLACK_HOME_CHANNEL` |
| `EMAIL_ADDRESS` / `EMAIL_HOME_ADDRESS` | `""` | 表 475 | |
| `TWILIO_ACCOUNT_SID` / `SMS_HOME_CHANNEL` | `""` | 表 476 | |
| `DINGTALK_CLIENT_ID` | `""` | 表 477 | home 变量为 `None`;cron 侧有 `DINGTALK_HOME_CHANNEL` |
| `FEISHU_APP_ID` / `FEISHU_HOME_CHANNEL` | `""` | 表 478 | |
| `WECOM_BOT_ID` / `WECOM_HOME_CHANNEL` | `""` | 表 479 | |
| `WECOM_CALLBACK_CORP_ID` | `""` | 表 480 | |
| `WEIXIN_ACCOUNT_ID` / `WEIXIN_HOME_CHANNEL` | `""` | 表 481 | |
| `BLUEBUBBLES_SERVER_URL` / `BLUEBUBBLES_HOME_CHANNEL` | `""` | 表 482 | |
| **`QQ_APP_ID` / `QQ_HOME_CHANNEL`** | `""` | 表 483 | **home 用了旧名 —— 本段核心缺陷** |
| `QQ_HOME_CHANNEL`(第二次) | `""` | `:496` | 恒假分支内,**不可达** |
| `YUANBAO_APP_ID` / `YUANBAO_HOME_CHANNEL` | `""` | 表 484 | 网关还认 `YUANBAO_APP_KEY`,面板不认 |
| `OPENROUTER_API_KEY`(第二次) | `""` | `:664` | deep 分支,**这里用的是 `os.getenv` 而非 `get_env_value`** |

**C. 间接读到的环境变量**(status.py 不出现变量名,但影响输出)

| 变量 | 读取点 | 途径 |
|---|---|---|
| `VERCEL_OIDC_TOKEN` | `hermes_cli/vercel_auth.py:26` | `describe_vercel_auth()`(status.py:449) |
| `VERCEL_TOKEN` / `VERCEL_PROJECT_ID` / `VERCEL_TEAM_ID` | `hermes_cli/vercel_auth.py:9,27` | 同上 |
| `TERMUX_VERSION` / `PREFIX` | `hermes_constants.is_termux` | status.py:532、538 |
| `HERMES_HOME` | `hermes_cli/config.py:698-700` | `get_env_path()` / `get_hermes_home()` |

`hermes_cli/config.py:698-700 @ 863e313`

```python
def get_env_path() -> Path:
    """Get the .env file path (for API keys)."""
    return get_hermes_home() / ".env"
```

### 4.3 关于 A/B 两种读法在实践中的差异

`.env` 在 CLI 启动时会被灌进 `os.environ`,所以裸 `os.getenv` 在正常 CLI 路径下也能读到
`.env` 的值(我在 3.5 场景 A 的实跑里验证了这一点 —— `QQ_APP_ID` 只写在 .env 里,面板照样
显示 configured)。`cli.py:226-231 @ 863e313`

```python
from hermes_cli.env_loader import load_hermes_dotenv
```

差异仍然存在于两处:(1) **多档案复用同一进程**时,`get_env_value` 走 secret_scope 隔离,裸
`os.getenv` 不走;(2) `.env` 加载失败/未加载的嵌入式调用路径(如测试直接 import
`show_status`)下,两者结果不同。顺带澄清一个容易想歪的点:`load_hermes_dotenv` 的清理动作
**范围很窄**,不会把 `.env` 里没有的 `QQ_HOME_CHANNEL` 从 `os.environ` 里删掉。
`hermes_cli/env_loader.py:114-131 @ 863e313`

```python
def _clear_known_keys_missing_from_dotenv(path: Path) -> None:
    """Remove inherited profile-managed Hermes keys absent from ``.env``.

    After the profile's ``.env`` has been loaded with ``override=True``,
    scan the file for which profile-managed keys it explicitly defines and
    delete any such key that exists in ``os.environ`` but is *not* present
    in the file.

    Scope is deliberately NARROW: only ``_PROFILE_MANAGED_ENV_KEYS`` —
    behavioral routing keys (ACP auth method, copilot-ACP endpoints) that a
    parent Hermes process injects and that silently change *which provider
    path* a profile uses. Provider API keys (OPENAI_API_KEY, …) are
    intentionally excluded: users legitimately export those in their shell
    (``export OPENAI_API_KEY=…`` is a documented flow — see
    ``tests/hermes_cli/test_dump_env_visibility.py``), and a startup scrub
    cannot distinguish a shell export from parent-process leakage. Clearing
    the full known-key set would delete user-exported credentials on every
    ``hermes`` invocation.
```

---

## 5. 文档 / 注释与代码的出入

**C-1 「将来时」docstring 腐烂 —— 不在 `hermes_cli/status.py`,在 `gateway/status.py:10`。**

R7C 的移交描述写的是"status.py",但全文 grep 后确认 `hermes_cli/status.py` 里**没有任何**
`will`/`TODO`/`FIXME`/`future` 字样。腐烂的这句在**另一个** status.py 里:
`gateway/status.py:7-11 @ 863e313`

```python
The PID file lives at ``{HERMES_HOME}/gateway.pid``.  HERMES_HOME defaults to
``~/.hermes`` but can be overridden via the environment variable.  This means
separate HERMES_HOME directories naturally get separate PID files — a property
that will be useful when we add named profiles (multiple agents running
concurrently under distinct configurations).
```

而 named profiles **早已上线**:有独立模块 `hermes_cli/profiles.py`、有 profile 目录布局、
有卸载/备份的 profile 处理路径。`hermes_cli/profiles.py:268 @ 863e313`

```python
    """Return the directory where named profiles are stored.
```

→ **定案:该腐烂 docstring 确实存在,位置是 `gateway/status.py:10`(不是 `hermes_cli/status.py`)。**
应改成现在时("named profiles rely on this property")。

**C-2 `--all` 参数被声明但从未被读。** 解析器声明了它,还写了 help 文案:
`hermes_cli/subcommands/status.py:22-24 @ 863e313`

```python
    status_parser.add_argument(
        "--all", action="store_true", help="Show all details (redacted for sharing)"
    )
```

而 `show_status` 全文只读 `deep` 一个字段(`hermes_cli/status.py:117 @ 863e313`),grep
`args\.` 在 status.py 里**零命中**。→ `hermes status --all` 与 `hermes status` 输出完全一致。
help 文案对用户是**主动误导**。(测试 `tests/hermes_cli/test_status.py:11` 还在传 `all=True`,
说明这个参数曾经有语义。)

**C-3 `terminal.backend` 的"真相源"方向相反。** env_loader 注释说 config.yaml 是 terminal.*
的文档化真相源,`.env` 里的陈旧 `TERMINAL_ENV` 是需要被压制的问题:
`hermes_cli/env_loader.py:515-518 @ 863e313`

```python
    # config.yaml is the documented source of truth for terminal.* settings,
    # but the dotenv loads above run with override=True — so a stale
    # TERMINAL_ENV=docker left in ~/.hermes/.env (e.g. written by an older
    # `hermes setup` before the user switched terminal.backend in config.yaml)
```

而 status.py 的解析顺序是 **env 优先、config 兜底**(`hermes_cli/status.py:426-428`)。两者
方向不一致 —— 面板显示的 backend 可能不是运行时真正会用的 backend。

**C-4 插件平台行把"依赖可用"写成"configured"。** 注册表定义见
`gateway/platform_registry.py:53-54 @ 863e313`,面板措辞见 `hermes_cli/status.py:508-509 @ 863e313`

```python
            configured = entry.check_fn()
            status_str = "configured" if configured else "not configured"
```

实测在**完全空配置**下有 10 个插件的 `check_fn()` 返回 True。

**C-5 文档只写新名,面板读旧名。** `website/docs/user-guide/messaging/qqbot.md:117 @ 863e313`

```markdown
- Check `QQBOT_HOME_CHANNEL` for cron/notification delivery
```

用户照着文档设了新名,`hermes status` 却看不到。文档是对的,代码是错的。

---

## 6. 可疑缺陷清单(只记不修)

**D-1 【最严重】QQBot home channel 名字倒置 + 恒假 back-compat 分支。**
`hermes_cli/status.py:483` + `:494-496 @ 863e313`。怎么踩到:任何按向导/文档配置 QQBot 的用户,
`hermes status` 永远不显示 home 频道;老用户听 `hermes doctor` 的话改名后,显示反而消失。
详见第 3 节。修法就是把 483 行改成 `("QQ_APP_ID", "QQBOT_HOME_CHANNEL")` —— 改完 495 行那个
分支自动变成活代码,一行改两个 bug。

**D-2 同一屏内 Z.AI 判据不一致。** API Keys 区块只认一个变量。`hermes_cli/status.py:158 @ 863e313`

```python
        "Z.AI / GLM": "GLM_API_KEY",
```

API-Key Providers 区块认三个别名。`hermes_cli/status.py:385 @ 863e313`

```python
        "Z.AI / GLM":       ("GLM_API_KEY", "ZAI_API_KEY", "Z_AI_API_KEY"),
```

同一次运行的实测输出:

```
$ ZAI_API_KEY=zaikey-abcdef123456 hermes status
  Provider:     Z.AI / GLM
  Z.AI / GLM    ✗ (not set)      ← API Keys 区块
  Z.AI / GLM       ✓ configured  ← API-Key Providers 区块
```

怎么踩到:用 `ZAI_API_KEY` 这个别名的用户会在同一屏看到自相矛盾的两行,无法判断到底配没配。

**D-3 `keys` 表里的 Anthropic 元组是死数据。** `hermes_cli/status.py:153` 定义、`:187-188`
无条件 `continue`。怎么踩到:有人给它加第四个 Anthropic 别名(如 `CLAUDE_API_KEY`),以为
生效了,实际毫无效果 —— 真正的读取在 `get_anthropic_key()` 里。

**D-4 deep check 探测的 18789 与 gateway 无关。** `hermes_cli/status.py:683,688 @ 863e313`。
全仓 grep,18789 只出现在 status.py 与 `plugins/google_meet/node/`;gateway 存活判定用的是
PID 文件(`gateway/status.py:4`),唯一会绑端口的内置平台 api_server 默认 8642
(`gateway/platforms/api_server.py:151`)。怎么踩到:用户跑 `hermes status --deep` 看到
"Port 18789: available",按注释 "Port in use = gateway likely running" 理解成"网关没跑",
而实际网关可能正在运行;反过来,装了 google_meet node 服务的 Mac 上会显示 "in use",
被误读成网关在跑。

**D-5 插件平台区块在 `hermes status` 路径上恒为空,且异常被静默吞掉。**
`hermes_cli/status.py:505-513 @ 863e313` 的 `except Exception: pass` 会把注册表任何问题一起吞掉,
无法区分"没有插件平台"和"注册表炸了"。实测该区块在真实 CLI 下输出 0 行。怎么踩到:
用 IRC / Matrix / Mattermost / LINE / Teams 的用户在 `hermes status` 里完全看不到自己的平台,
会以为没装上。

**D-6 「configured」判据与网关启用判据不同源。** 面板对每个平台只看一个 token 变量
(`hermes_cli/status.py:488`),而 `gateway/config.py` 各平台的启用条件各异(QQ 是 `or`、
Yuanbao 是 `and` 且 app_id 有别名)。怎么踩到:只设 `YUANBAO_APP_ID` 时面板 ✓ 但网关不启用;
只设 `QQ_CLIENT_SECRET` 时网关启用但面板 ✗。

**D-7 LM Studio 探测用展示标签做判据。** `hermes_cli/status.py:405 @ 863e313` 比较的是
`_effective_provider_label()` 的**人类可读文案**。怎么踩到:任何对 provider 展示名的改动
(i18n、加后缀)都会让这段探测静默失效,而现有测试因为 monkeypatch 了 `provider_label`,
**不会**发现。

**D-8 LM Studio 分支里 `from hermes_cli.models import probe_lmstudio_models` 无 try 保护。**
`hermes_cli/status.py:406 @ 863e313`,且 `except` 只捕 `AuthError`
(`hermes_cli/status.py:415`)。怎么踩到:如果 `probe_lmstudio_models` 抛出非 `AuthError`
的异常(它的 docstring 承诺不会,但这是一个跨模块的隐含契约),整个 `hermes status` 会崩在
中途 —— 前面几屏已打印,后面的 Gateway/Sessions 全部丢失。这是全文唯一没有异常兜底的探测点。

**D-9 `_effective_provider_label()` 被完整跑两遍。** `hermes_cli/status.py:141` 与 `:405`。
每次都触发 `resolve_requested_provider()` + `resolve_provider()` + `load_config()`。纯浪费,
且如果这两次调用之间状态变化(不太可能但非零),Provider 行与 LM Studio 探测会不自洽。

**D-10 `AuthError` 被吞成"看起来正常的 provider 名"。** `hermes_cli/status.py:88-91 @ 863e313`

```python
    try:
        effective = resolve_provider(requested)
    except AuthError:
        effective = requested or "auto"
```

怎么踩到:凭据缺失导致 `resolve_provider` 抛 `AuthError` 时,面板 Provider 行照样显示一个
正常的 provider 名,不给任何提示 —— 用户以为 provider 没问题,实际一跑就 401。

**D-11 `TERMINAL_CONTAINER_PERSISTENT=""` 的三态判定有坑。**
`hermes_cli/status.py:444-448 @ 863e313`:判的是 `persist is None`(未设),不是 falsy。
设成空串会走 `"".lower() in {...}` → False,**不会**回落 config 的 `True` 默认值。
怎么踩到:`.env` 里写了 `TERMINAL_CONTAINER_PERSISTENT=` 的用户,面板会说 "ephemeral filesystem"。

**D-12 `subprocess` 的 monkeypatch 把手是全局副作用。** `hermes_cli/status.py:11`。
测试打的是共享模块对象的属性(`tests/hermes_cli/test_status.py:39`),意味着补丁会波及**同一
进程内所有**用 `subprocess.run` 的代码。作为回归守卫有效,但作用域远超注释暗示的范围;
在并行测试进程内混用时容易出难查的串扰。

---

## 7. 配套测试(本段的行为规格)

| 文件 | 覆盖什么 |
|---|---|
| `tests/hermes_cli/test_status.py` | 密钥不外泄(:6)、Termux 网关视图不调 systemctl(:18)、Vercel 后端契约含 token 不外泄(:47)、xAI OAuth 行的四种降级(:110-199)、gateway 会话 last_active(:202) |
| `tests/hermes_cli/test_status_model_provider.py` | `model` 为 dict 时的 Model/Provider 行(:33);LM Studio 空列表须显示 reachable(:54) |
| `tests/hermes_cli/test_status_provider_label.py` | `_effective_provider_label` 的三条分支:config base_url→custom(:17)、空 base_url 保持 openrouter(:22)、非 openrouter 不动(:27) |
| `tests/hermes_cli/test_jobs_json_utf8_bom.py` | jobs.json 带 BOM 时 status 不报错(:38 引用 status_mod) |
| `tests/hermes_cli/test_subprocess_timeouts.py` | 把 `hermes_cli/status.py` 列入必须有超时的文件清单(:11) |

跑通记录(只读运行,未改基线):

```
$ HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
    tests/hermes_cli/test_status.py tests/hermes_cli/test_status_provider_label.py \
    tests/hermes_cli/test_status_model_provider.py
=== Summary: 3 files, 15 tests passed, 0 failed (100% complete) in 1.6s (8 workers) ===
```

**规格空白**(这些行为没有任何测试覆盖,因此发生腐烂时不会红):
Messaging Platforms 整块(含 QQ home channel)、插件平台块、Scheduled Jobs 块、
Terminal 的 ssh/docker/daytona 三个分支、deep check 两项、API Keys 与 API-Key Providers
两张表的一致性、`--all` 参数。

QQ 相关的测试都在别处、不覆盖面板:`tests/gateway/test_qqbot.py`、
`tests/gateway/test_qqbot_scope_paths.py`、`tests/gateway/test_qqbot_credential_isolation.py`、
`tests/hermes_cli/test_doctor.py:1383-1384`(deprecation 清单)。

---

## 8. 重实现要点(从零重写一个 `status` 面板必须知道的)

1. **只读面板必须有配套的"只读版"状态 API。** 最容易犯也最贵的错是让状态查询触发 OAuth
   refresh —— 一次性 refresh token 会被烧掉,用户"看一眼状态"就被踢下线。hermes 的做法是
   为面板专门提供 `get_nous_auth_status_local()`(`hermes_cli/auth.py:6724`),显式承诺
   NEVER refresh。设计时就要把"读"和"解析凭据"分成两个 API。

2. **异常边界的粒度 = 一个显示区块。** 函数级 try 会让一个子系统的失败吃掉整屏;行级 try
   会让代码不可读。区块级是正确粒度,并且每个区块的降级输出要**明确表示"未知"而不是"没有"**
   —— 这是 hermes 没做好的地方(大多数区块降级成 ✗,与"确实没配"无法区分)。

3. **判据必须与运行时同源,否则一定漂移。** 本段查到的所有实质缺陷(D-1/D-2/D-6/D-7)都是
   同一个根因:面板抄了一份判定逻辑。正确做法是让运行时暴露"这个平台/provider 是否启用"的
   查询函数,面板只调不判。hermes 在 gateway 侧已经有 `PORT_BINDING_PLATFORM_VALUES` 这种
   "single source of truth"注释的先例(`gateway/config.py:376-383`),但没推到面板。

4. **环境变量改名要一次改完三处:写入方、读取方、面板/诊断方。** 并且 back-compat fallback
   要写成**数据驱动**(`{新名: 旧名}` 映射表 + 一个统一的解析函数),不要写成 if 判断 ——
   `cron/scheduler.py:287-289` + `:1043-1053` 是正确范式,`hermes_cli/status.py:494-496` 是
   反例:硬编码的 if 判断把新旧名字写反了,而且这种错误 grep 不出来、类型检查抓不到、
   没有测试会红。

5. **面板的平台/provider 清单不能手写。** hermes 有三份清单(status.py 的两张表、
   gateway/config.py 的 Platform 枚举、platform_registry 的插件注册表),已经互相不一致。
   清单必须来自注册表,面板只负责渲染。如果注册表需要显式发现(如插件),面板要么触发发现,
   要么**明说自己没发现**,不能静默打印空列表(D-5)。

6. **"依赖可用" ≠ "已配置" ≠ "已启用" ≠ "在运行",四个概念要分开。** hermes 的插件行把
   `check_fn()`(依赖可用)标成 "configured",在空配置下会显示一排 ✓。设计时给注册表条目
   四个独立谓词,面板显式选一个。

7. **诊断面板本身要有输出契约测试。** 至少三类:(a) 密钥绝不出现在输出中;(b) 每个区块在
   探测失败时仍打印表头且不崩;(c) 每一条 env→显示的映射至少一条断言。hermes 有 (a) 和 (b)
   但缺 (c),QQ 这个 bug 才能活到今天。

8. **不要在面板里硬编码端口/路径这类"魔数"。** D-4 的 18789 是典型:它当年可能对过,现在
   指向的是另一个插件的服务。任何面板显示的常量都应该从它的真正拥有者那里 import。

---

## 9. 未确证 / 存疑

- **18789 是否曾经是 gateway 的历史端口**:未确证。基线仓库只读,未查 git 历史(按边界不做
  git 操作)。当前基线里它只与 google_meet 插件相关。
- **`hermes status --all` 是否在某个更早版本有语义**:未确证,只能从测试仍传 `all=True`
  (`tests/hermes_cli/test_status.py:11`)推测曾经有过;当前代码零引用。
- **插件平台区块在哪些进程里会真的打印**:确证了 `hermes status` 走不到;未逐一验证
  desktop/web dashboard 是否会在同进程内先触发 `discover_plugins()` 再调 `show_status`
  —— 若会,则会出现第 2.12 节说的重复行。
