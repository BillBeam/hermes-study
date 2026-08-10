# R8C 底稿 · `hermes_cli/auth.py`(9,240 行)+ `hermes_cli/auth_commands.py`(802 行)

> 基线 `863e31318553cda8ad61df681d08175364d4164b`。所有断言的溯源格式为
> `路径:行号 @ 863e313`,锚点单独成行、置于代码块之前。
> 记号:▲ 文档与代码矛盾;◇ 代码有、文档无;■ 代码缺陷;◎ 文档成立但显著保守。

---

## 0. 先把最容易混淆的一条讲清楚:CLI 凭据面 ≠ dashboard 登录

本段研究的 `hermes_cli/auth.py` 是 **"Hermes 拿什么凭据去调用大模型 API"** 这一面。
它管的是**出站(outbound)**方向:Hermes 作为客户端,向 Nous Portal / OpenAI / xAI / MiniMax
等**推理服务商**证明自己的身份,换到一个 `api_key` 或 `access_token`,再拿去发推理请求。

**与之完全无关**的另一面是 dashboard 的浏览器登录,它管的是**入站(inbound)**方向:
一个人打开浏览器访问 Hermes 自己起的 Web 控制台,Hermes 要验证**这个访问者**是不是主人。
那一面的代码在 `hermes_cli/dashboard_auth/` 这个**独立包**里:

```console
$ ls /home/user/hermes-agent/hermes_cli/dashboard_auth/
__init__.py  audit.py  base.py  cookies.py  login_page.py  middleware.py
native_flow.py  prefix.py  public_paths.py  registry.py  routes.py
token_auth.py  ws_tickets.py
```

两者的区别可以一句话记住:

| | `hermes_cli/auth.py` | `hermes_cli/dashboard_auth/` |
|---|---|---|
| 方向 | 出站:Hermes → 模型厂商 | 入站:浏览器用户 → Hermes |
| 凭据是谁的 | 用户在**模型厂商**那里的账号 | 用户在**自己这台 Hermes**上的身份 |
| 落盘位置 | `~/.hermes/auth.json` + `~/.hermes/.env` | cookie / ticket / 中间件会话 |
| 典型产物 | `access_token`(拿去发推理请求) | 会话 cookie、WebSocket ticket |
| 关键词 | device code、refresh token、credential pool | middleware、cookies、ws_tickets |

测试目录里两族文件名也是分开的:`tests/hermes_cli/test_auth_*.py`(本段对象)
与 `tests/hermes_cli/test_dashboard_auth_*.py`(另一面)。**别把两族测试的结论混用。**

### 0.1 ▲ `hermes login` 这个命令**已经不存在了**

任务书里写的"`hermes login` 一族"这个说法,在基线上**已经不成立**。`login_command` 只剩一个
退休公告:

`hermes_cli/auth.py:7740 @ 863e313`
```python
def login_command(args) -> None:
    """Deprecated: use 'hermes model' or 'hermes setup' instead."""
    print("The 'hermes login' command has been removed.")
    print("Use 'hermes auth' to manage credentials,")
    print("'hermes model' to select a provider, or 'hermes setup' for full setup.")
    raise SystemExit(0)
```

子命令解析器**仍然注册**,但故意不给 `help=`,所以 `hermes --help` 里看不到它 ——
目的是让老脚本里的 `hermes login --provider anthropic` 拿到一条**可行动的**提示,
而不是 argparse 的 `invalid choice: 'login'`:

`hermes_cli/subcommands/login.py:12 @ 863e313`
```python
def build_login_parser(subparsers, *, cmd_login: Callable) -> None:
    """Attach the deprecated ``login`` subcommand to ``subparsers``.

    ``hermes login`` was removed in favor of ``hermes auth`` / ``hermes model``
    (the runtime handler in ``hermes_cli/auth.py::login_command`` just prints a
    deprecation message and exits).  The subparser is kept registered so that
    old scripts/aliases invoking ``hermes login [--flags]`` still receive the
    actionable deprecation message rather than an argparse ``invalid choice:
    'login'`` error — but:
```

**所以真正的三个入口是**:

1. `hermes auth ...` → `hermes_cli/auth_commands.py`(凭据池管理,见 §7)
2. `hermes model` / `hermes setup` → `hermes_cli/model_setup_flows.py`(交互式选 provider,
   内部再调 `auth.py` 里的 `_login_*` helper 与 `_update_config_for_provider`)
3. `hermes logout` → `hermes_cli/auth.py:9211` 的 `logout_command`(这个**还活着**)

注意 `auth.py` 里那一族 `_login_openai_codex` / `_login_xai_oauth` / `_login_nous` /
`_login_minimax_oauth` **没有死**,它们只是不再由 `hermes login` 调用,而是由
`model_setup_flows.py` 调用(§6.2 列出调用点)。

### 0.2 ▲ 模块头 docstring 已经过时

`hermes_cli/auth.py:1 @ 863e313`
```python
"""
Multi-provider authentication system for Hermes Agent.

Supports OAuth device code flows (Nous Portal, future: OpenAI Codex) and
traditional API key providers (OpenRouter, custom endpoints). Auth state
is persisted in ~/.hermes/auth.json with cross-process file locking.
```

- 「future: OpenAI Codex」:Codex 的 device-code 流程**已经完整实现**
  (`hermes_cli/auth.py:8075` 的 `_codex_device_code_login`),不是 future。
- 「traditional API key providers (OpenRouter, custom endpoints)」:注册表里
  有 30+ 个 API-key provider(§2 的表),不止 OpenRouter 与 custom。
- 「logout_command() is the CLI entry point」:这条**仍然成立**,是全文里唯一没漂移的一句。

影响:低(只是注释),但它会让第一次读这个文件的人低估 registry 的规模。

---

## 1. 全景:9,240 行分成 17 个横幅段

文件用 `# ===...===` 三行横幅切段。下表按横幅位置给出行号区间与职责。
区间的**上界 = 下一个横幅的起始行减一**。

```verify
# 复现方式(基线只读):
cd /home/user/hermes-agent && grep -n '^# =\|^# ==== ' hermes_cli/auth.py
```

| 行号区间 | 段名(横幅原文) | 职责 / 为什么需要这一块 |
|---|---|---|
| 1–66 | (模块 docstring + import) | 可选依赖 `fcntl`/`msvcrt` 用 try-import 包住,决定跨平台文件锁走哪条路 |
| 67–189 | `Constants` | 所有 portal / 推理 URL 默认值、OAuth client_id、各 provider 的**刷新提前量**(skew)常量 |
| 190–543 | `Provider Registry` | `ProviderConfig` 数据类 + `PROVIDER_REGISTRY` 字典;**一个 provider 长什么样**的单一定义处 |
| 544–567 | `Anthropic Key Helper` | 单函数 `get_anthropic_key()`,给别处一个"随手拿 Anthropic key"的口子 |
| 568–673 | `Kimi Code Endpoint Detection` | 同一个厂商两套 endpoint,靠 key 前缀猜;外加通用的 `has_usable_secret` 与 API-key 解析器 |
| 674–863 | `Z.AI Endpoint Detection` | Z.AI 按套餐/地域分裂成 4 个 endpoint,**登录时主动探测**哪个能用并记下来 |
| 864–995 | `Error Types` | `AuthError` + 限流识别 + OAuth trace 日志(带 token 指纹脱敏) |
| 996–1949 | `Auth Store — persistence layer for ~/.hermes/auth.json` | **本文件的地基**:路径解析、跨进程 flock、原子写、profile↔global 回退、credential pool 读写 |
| 1950–2184 | `Provider Resolution — picks which provider to use` | `resolve_provider()`:别名归一 + 8 级优先链 |
| 2185–2764 | `Timestamp / TTL helpers` | ISO 时间戳解析、过期判定、JWT claim 解码;**外加 Qwen 全套**(见 ◇-1) |
| 2765–3391 | `Spotify auth — PKCE tokens stored in ~/.hermes/auth.json` | 唯一走**回环 PKCE**(本机起 HTTP server 收 callback)的 provider |
| 3392–3559 | `SSH / remote session detection` | 判断"能不能弹出图形浏览器",决定 device-code 还是回环流程,以及 SSH 端口转发提示 |
| 3560–4416 | `OpenAI Codex auth` | Codex 的独立会话(**刻意不共用** `~/.codex/auth.json`)+ 配额探测 + 池冷却 |
| 4417–5068 | `xAI Grok OAuth` | xAI device-code + OIDC discovery + profile→global 写穿 |
| 5069–5125 | `TLS verification helper` | macOS 上 httpx 的 CA 兜底(对应 `test_auth_ssl_macos.py`) |
| 5126–5227 | `OAuth Device Code Flow — generic, parameterized by provider` | **通用** device-code 两步:请求 code、轮询 token。实际只有 Nous 用(见 ◎-1) |
| 5228–6523 | `Nous Portal — token refresh and model discovery` | 全文最大一段:共享 token store(跨 profile)、刷新、隔离(quarantine)、invoke-JWT |
| 6524–7265 | `Status helpers` | `get_*_auth_status()` 一族,`hermes auth status` / doctor / dashboard 的数据源 |
| 7266–9240 | `CLI Commands — login / logout` | 配置写回、模型选择交互、各 provider 的 `_login_*`、MiniMax OAuth(8274 起子横幅)、`logout_command` |

**读这张表的方式**:996–1949(存储层)和 7266–9240(命令层)是"骨架";
中间那些以 provider 命名的段(Codex / xAI / Nous / Spotify / MiniMax / Qwen)是
**同一套模式的 6 次重复实例化**——每个都有 `_read_*_tokens` / `_save_*_tokens` /
`_refresh_*` / `resolve_*_runtime_credentials` / `get_*_auth_status` 五件套。
理解了 Nous 那一份,其余五份只需看差异。

### ◇-1 段名与内容不符:Qwen 整套代码藏在 "Timestamp / TTL helpers" 段里

`Timestamp / TTL helpers` 横幅在 2185,下一个横幅 `Spotify auth` 在 2765。
但 2552–2764 这 200 多行全是 Qwen:

`hermes_cli/auth.py:2552 @ 863e313`
```python
def _qwen_cli_auth_path() -> Path:
    return Path.home() / ".qwen" / "oauth_creds.json"
```

之后 `_read_qwen_cli_tokens` / `_save_qwen_cli_tokens` / `_refresh_qwen_cli_tokens` /
`resolve_qwen_runtime_credentials` / `get_qwen_auth_status` 全在这一段里,**没有自己的横幅**。
同段里还塞了 Nous 的 invoke-JWT 一族(2352–2543)和 Codex 的过期判定(2544)。
影响:靠横幅导航的人(包括我第一遍)会以为 Qwen 没实现。**找 Qwen 要 grep,不要看横幅。**

---

## 2. Provider 矩阵:API key 还是 OAuth,device-code 还是 PKCE

### 2.1 `auth_type` 这个字段是矩阵的轴

`hermes_cli/auth.py:195 @ 863e313`
```python
class ProviderConfig:
    """Describes a known inference provider."""
    id: str
    name: str
    auth_type: str  # "oauth_device_code", "oauth_external", "oauth_minimax", or "api_key"
    portal_base_url: str = ""
    inference_base_url: str = ""
    client_id: str = ""
    scope: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    # For API-key providers: env vars to check (in priority order)
    api_key_env_vars: tuple = ()
    # Optional env var for base URL override
    base_url_env_var: str = ""
```

**▲-1:这行注释漏了三个值。** 注释说 `auth_type` 只有四种取值,但注册表里实际出现了
七种:除注释里的四种外,还有 `"external_process"`(copilot-acp)、`"aws_sdk"`(bedrock)、
`"vertex"`(vertex)。

`hermes_cli/auth.py:263 @ 863e313`
```python
    "copilot-acp": ProviderConfig(
        id="copilot-acp",
        name="GitHub Copilot ACP",
        auth_type="external_process",
        inference_base_url=DEFAULT_COPILOT_ACP_BASE_URL,
        base_url_env_var="COPILOT_ACP_BASE_URL",
    ),
```

`hermes_cli/auth.py:480 @ 863e313`
```python
    "bedrock": ProviderConfig(
        id="bedrock",
        name="AWS Bedrock",
        auth_type="aws_sdk",
        inference_base_url="https://bedrock-runtime.us-east-1.amazonaws.com",
        api_key_env_vars=(),
        base_url_env_var="BEDROCK_BASE_URL",
    ),
```

影响:中。这不是纯注释问题——`auth_type` 是**运行时分派键**,
`resolve_api_key_provider_credentials` 拿它做守卫:

`hermes_cli/auth.py:7150 @ 863e313`
```python
    pconfig = PROVIDER_REGISTRY.get(provider_id)
    if not pconfig or pconfig.auth_type != "api_key":
        raise AuthError(
            f"Provider '{provider_id}' is not an API-key provider.",
            provider=provider_id,
            code="invalid_provider",
        )
```

新增一种 `auth_type` 就要同步一处分派,而注释没有维护成"全集清单",
下一个改这里的人容易漏掉分派点。

### 2.2 完整矩阵表

`PROVIDER_REGISTRY` 字面量在 `hermes_cli/auth.py:210–520`。下表按 auth_type 归类。
"流程"一列里:**device-code** = 终端显示一串短码,用户去另一台设备的浏览器输入并批准,
CLI 同时轮询 token 端点;**PKCE** = 授权码流程 + 证明密钥
(Proof Key for Code Exchange:客户端先自己生成一个随机 `code_verifier`,把它的 SHA-256
摘要 `code_challenge` 随授权请求发出,换 token 时再出示原始 verifier,
从而在没有 client_secret 的公开客户端上防止授权码被中途窃取)。

| provider id | 显示名 | auth_type | 凭据获取方式 | 备注 |
|---|---|---|---|---|
| `nous` | Nous Portal | `oauth_device_code` | **device-code**(通用实现) | 唯一使用 §5126 通用 device-code 函数的 provider |
| `openai-codex` | OpenAI Codex | `oauth_external` | **device-code**(自写) | `hermes_cli/auth.py:8075`,端点 `auth.openai.com/api/accounts/deviceauth/usercode` |
| `xai-oauth` | xAI Grok OAuth (SuperGrok / Premium+) | `oauth_external` | **device-code**(自写) | `hermes_cli/auth.py:7890`;token 端点靠 OIDC discovery 拿 |
| `qwen-oauth` | Qwen OAuth | `oauth_external` | **不自己登录**,读 `~/.qwen/oauth_creds.json` | 借用 Qwen CLI 的会话,只负责刷新 |
| `minimax-oauth` | MiniMax (OAuth · minimax.io) | `oauth_minimax` | **PKCE + user-code 混合** | 见 §2.4 |
| `anthropic` | Anthropic | `api_key`(注册表里) | **但也支持 PKCE OAuth** | 见 ▲-2 |
| `copilot` | GitHub Copilot | `api_key` | env `COPILOT_GITHUB_TOKEN`/`GH_TOKEN`/`GITHUB_TOKEN`,再换 API token | 走 `hermes_cli/copilot_auth.py` |
| `copilot-acp` | GitHub Copilot ACP | `external_process` | 本地子进程,无凭据 | `acp://copilot` |
| `bedrock` | AWS Bedrock | `aws_sdk` | AWS 凭据链 | `api_key_env_vars=()` |
| `vertex` | Google Vertex AI | `vertex` | 服务账号 JSON / ADC | `inference_base_url=""`(每请求现算) |
| `openai-api` | OpenAI API | `api_key` | `OPENAI_API_KEY` | |
| `lmstudio` | LM Studio | `api_key` | `LM_API_KEY`(可无鉴权) | 无 key 时塞占位符 |
| `gemini` | Google AI Studio | `api_key` | `GOOGLE_API_KEY` / `GEMINI_API_KEY` | |
| `zai` | Z.AI / GLM | `api_key` | `GLM_API_KEY` / `ZAI_API_KEY` / `Z_AI_API_KEY` | 登录时探测 4 个 endpoint |
| `kimi-coding` / `kimi-coding-cn` | Kimi / Moonshot(+ China) | `api_key` | `KIMI_API_KEY` 等 | `sk-kimi-` 前缀改道 |
| `stepfun` `arcee` `gmi` `actual` `minimax` `minimax-cn` `alibaba` `alibaba-coding-plan` `deepseek` `xai` `nvidia` `ai-gateway` `opencode-zen` `opencode-go` `kilocode` `huggingface` `xiaomi` `tencent-tokenhub` `ollama-cloud` `azure-foundry` | (各自) | `api_key` | 各自 env 变量 | 纯粹的 "key + base_url" 条目 |

**注册表不是全集。** 文件尾部有一段自动扩展:凡是 `providers/` 插件目录里声明的
api-key provider,只要不在上表、也不在黑名单里,就自动补进 `PROVIDER_REGISTRY`:

`hermes_cli/auth.py:509 @ 863e313`
```python
# Auto-extend PROVIDER_REGISTRY with any api-key provider registered in
# providers/ that is not already declared above.  New providers only need a
# plugins/model-providers/<name>/ plugin — no edits to this file required.
try:
    from providers import list_providers as _list_providers_for_registry
```

黑名单在 `hermes_cli/auth.py:533`,排除 `copilot / kimi-coding / kimi-coding-cn / zai /
openrouter / custom`,理由是前四个有自定义 token 解析、后两个被 `resolve_provider()`
特判(注释明说 `openrouter not in PROVIDER_REGISTRY` 这个条件被依赖)。

### 2.3 ▲-2:`anthropic` 在注册表里是 `api_key`,但实际支持 PKCE OAuth

注册表条目:

`hermes_cli/auth.py:355 @ 863e313`
```python
    "anthropic": ProviderConfig(
        id="anthropic",
        name="Anthropic",
        auth_type="api_key",
        inference_base_url="https://api.anthropic.com",
        api_key_env_vars=("ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"),
        base_url_env_var="ANTHROPIC_BASE_URL",
    ),
```

但命令层把它列进了"支持 OAuth"的集合:

`hermes_cli/auth_commands.py:36 @ 863e313`
```python
# Providers that support OAuth login in addition to API keys.
_OAUTH_CAPABLE_PROVIDERS = {"anthropic", "nous", "openai-codex", "xai-oauth", "qwen-oauth", "minimax-oauth"}
```

而 `hermes auth add anthropic` 走的确实是 PKCE:

`hermes_cli/auth_commands.py:224 @ 863e313`
```python
    if provider == "anthropic":
        from agent import anthropic_adapter as anthropic_mod

        creds = anthropic_mod.run_hermes_oauth_login_pure()
```

实现在另一个文件:

`agent/anthropic_adapter.py:1501 @ 863e313`
```python
def run_hermes_oauth_login_pure() -> Optional[Dict[str, Any]]:
    """Run Hermes-native OAuth PKCE flow and return credential state."""
    import secrets
    import time
    import webbrowser

    verifier, challenge = _generate_pkce()
    oauth_state = secrets.token_urlsafe(32)
```

**结论:`auth_type` 字段描述的是"注册表把这个 provider 当哪类处理",不是
"这个 provider 只能怎么登录"。** Anthropic 的 OAuth 路径完全绕开了 `auth.py` 的
provider registry,住在 `agent/anthropic_adapter.py`。这是 §2.2 表里
"anthropic 一格要写两行"的原因,也是任何"照着 auth_type 统计有几个 OAuth provider"
的做法会算错的原因。

### 2.4 MiniMax 是唯一的 "PKCE + user-code" 混合流程

MiniMax 既生成 PKCE 三元组(verifier / challenge / **state**),又走 user-code 显示:

`hermes_cli/auth.py:8338 @ 863e313`
```python
def _minimax_pkce_pair() -> tuple:
    """Generate (code_verifier, code_challenge_S256, state) for MiniMax OAuth."""
    import secrets
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    return verifier, challenge, state
```

授权请求把 `code_challenge` 与 `state` 一起发出,响应里必须回带同一个 `state`,
否则判为 CSRF:

`hermes_cli/auth.py:8383 @ 863e313`
```python
    if payload.get("state") != state:
        raise AuthError(
            "MiniMax OAuth state mismatch (possible CSRF).",
            provider="minimax-oauth", code="state_mismatch",
        )
```

拿到的却不是回环 redirect,而是一个 **user_code + verification_uri**,像 device-code 那样让用户去输:

`hermes_cli/auth.py:8511 @ 863e313`
```python
        verification_url = str(code_data["verification_uri"])
        user_code = str(code_data["user_code"])

        print()
        print("To continue:")
        print(f"  1. Open: {verification_url}")
        print(f"  2. If prompted, enter code: {user_code}")
```

grant type 也印证了这一点(不是标准的 `device_code` grant):

`hermes_cli/auth.py:90 @ 863e313`
```python
MINIMAX_OAUTH_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:user_code"
```

**取舍解读**:PKCE 的 challenge 在这里不是为了保护回环 redirect(根本没有 redirect),
而是为了把"谁发起的授权"绑定到"谁来兑换 token"——在 device-code 语义下补上
device-code 规范本身没有的 verifier 绑定。`hermes_cli/web_server.py:10422` 的注释也是这么说的。

### ◎-1:通用 device-code 实现只有 Nous 一个用户

`hermes_cli/auth.py:5128` 的横幅写着 "OAuth Device Code Flow — **generic, parameterized by provider**"。
但 `_request_device_code` 把端点路径写死成 Nous Portal 的形状:

`hermes_cli/auth.py:5137 @ 863e313`
```python
    response = client.post(
        f"{portal_base_url}/api/oauth/device/code",
        data={
            "client_id": client_id,
            **({"scope": scope} if scope else {}),
        },
    )
```

Codex(`/api/accounts/deviceauth/usercode`,JSON body)、xAI(`XAI_OAUTH_DEVICE_CODE_URL`,
form body)、MiniMax(`/oauth/code`)三家的端点形状都不一样,所以各自重写了一份。
"generic" 只兑现到"参数化了 portal_base_url / client_id / scope"这个程度。
影响:低,但读横幅会高估复用度——实际是**四份 device-code 轮询循环并存**。

---

## 3. 凭据落到哪:三个落点 + 一条分流规则

### 3.1 三个落点(以及被排除的第四个)

| 落点 | 内容 | 权限 | 谁写 |
|---|---|---|---|
| `~/.hermes/auth.json` | OAuth token(access/refresh/expires)、`active_provider`、`credential_pool`、`suppressed_sources` | 文件 `0o600`,父目录 `0o700` | `_save_auth_store` (`hermes_cli/auth.py:1284`) |
| `~/.hermes/.env` | **API key 形状的键**(见 §4) | 新建 `0o600`;已存在则**保留原权限** | `save_env_value` (`hermes_cli/config.py:3865`) |
| `~/.hermes/config.yaml` | `model.provider` / `model.base_url` / `model.default` —— **只有路由信息,不含密钥** | 未特殊设限 | `_update_config_for_provider` (`hermes_cli/auth.py:7270`) |
| ~~系统钥匙串~~ | **不作为落点** | — | 见 §3.5 |

另有两个"外部借用"的读取点(Hermes **读**、原则上不写):

- `~/.codex/auth.json`(Codex CLI 的会话)—— 只读,docstring 把这条写成契约:

`hermes_cli/auth.py:3940 @ 863e313`
```python
def _import_codex_cli_tokens() -> Optional[Dict[str, str]]:
    """Try to read tokens from ~/.codex/auth.json (Codex CLI shared file).
    
    Returns tokens dict if valid and not expired, None otherwise.
    Does NOT write to the shared file.
    """
```

- `~/.qwen/oauth_creds.json`(Qwen CLI 的会话)—— 这个**会写**,见 §3.4。

以及一个跨 profile 的共享点:`<hermes-root>/shared/nous_auth.json`,见 §3.6。

### 3.2 谁决定落哪一个

分三层,互不重叠:

1. **OAuth token → 永远 `auth.json`。** 没有分支。所有 `_save_*_tokens` 最终都收敛到
   `_save_auth_store`(Qwen 是唯一例外,见 §3.4)。
2. **`hermes config set <key> <value>` → 由 `_is_env_config_key(key)` 决定 `.env` 还是
   `config.yaml`。** 这是唯一的动态分流点,见 §4。
3. **provider 路由(哪个 provider、哪个 base_url、哪个默认模型)→ 永远 `config.yaml`。**
   由 `_update_config_for_provider` 写,见 §6。

### 3.3 权限:auth.json 走 O_EXCL 原子创建,`.env` 走"保留原权限"

`auth.json` 的写入路径把 TOCTOU 窗口彻底关掉了——不是"先建后 chmod",而是
**os.open 时就带上 0600**:

`hermes_cli/auth.py:1284 @ 863e313`
```python
def _save_auth_store(auth_store: Dict[str, Any], target_path: Optional[Path] = None) -> Path:
    # target_path=None preserves the existing contract (write the active
    # store at _auth_file_path()). An explicit path lets callers persist a
    # specific store — e.g. the global-root write-through for rotating xAI
    # OAuth grants (#43589) — reusing this function's atomic O_EXCL + 0o600
    # write so the root auth.json gets the same TOCTOU-safe treatment.
    auth_file = target_path if target_path is not None else _auth_file_path()
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    # Tighten parent dir to 0o700 so siblings can't traverse to creds.
    # No-op on Windows (POSIX mode bits not enforced); ignore failures.
    # secure_parent_dir refuses to chmod / or top-level dirs (#25821).
    secure_parent_dir(auth_file)
```

`hermes_cli/auth.py:1299 @ 863e313`
```python
    tmp_path = auth_file.with_name(f"{auth_file.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    try:
        # Create with 0o600 atomically via os.open(O_EXCL) + fdopen to close
        # the TOCTOU window where default umask (often 0o644) briefly exposed
        # OAuth tokens to other local users between open() and chmod().
        # Mirrors agent/google_oauth.py (#19673) and tools/mcp_oauth.py (#21148).
        fd = os.open(
            str(tmp_path),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            stat.S_IRUSR | stat.S_IWUSR,
        )
```

写完后还有一次**兜底 chmod** + 目录 fsync(保证 rename 落盘):

`hermes_cli/auth.py:1330 @ 863e313`
```python
    # Restrict file permissions to owner only
    try:
        auth_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return auth_file
```

**这一段有配套的行为规格测试**,并且测试自己把 umask 调成 `0o022` 让 race "可观测":

`tests/hermes_cli/test_auth_toctou_file_modes.py:41 @ 863e313`
```python
def test_save_auth_store_writes_0o600_with_0o700_parent(tmp_path, monkeypatch):
    """``_save_auth_store`` must land ``auth.json`` at 0o600 and parent at 0o700."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    old_umask = os.umask(0o022)  # make the race observable if it regresses
```

**`.env` 的策略不一样**:已存在的文件**保留原权限**,只有新建时才收紧:

`hermes_cli/config.py:3925 @ 863e313`
```python
    fd, tmp_path = tempfile.mkstemp(dir=str(env_path.parent), suffix='.tmp', prefix='.env_')
    # Preserve original permissions so Docker volume mounts aren't clobbered.
    original_mode = None
    if env_path.exists():
        try:
            original_mode = stat.S_IMODE(env_path.stat().st_mode)
        except OSError:
            pass
```

`hermes_cli/config.py:3938 @ 863e313`
```python
        atomic_replace(tmp_path, env_path)
        # Preserve the original file mode (e.g. 0640 for Docker volume mounts)
        # instead of letting _secure_file unconditionally tighten to 0600.
        if original_mode is not None:
            try:
                os.chmod(env_path, original_mode)
            except OSError:
                pass
        else:
            _secure_file(env_path)
```

**取舍**:`.env` 常被 Docker volume 挂载并需要 group 可读(`0640`),硬收 `0600`
会让容器读不到。代价是:一个原本就是 `0644` 的 `.env`,Hermes 写入 API key 后
**仍然是 `0644`** —— Hermes 不会替你收紧。`auth.json` 没有这个顾虑(它是 Hermes 私产),
所以无条件 `0600`。

Qwen 的写入(§3.4)复用了同一套 O_EXCL 模式:

`hermes_cli/auth.py:2589 @ 863e313`
```python
    # Create with 0o600 atomically via os.open(O_EXCL) — closes the TOCTOU
    # window where write_text() + post-write chmod briefly exposed tokens
    # at process umask (typically 0o644). See #19673, #21148.
    fd = os.open(
        str(tmp_path),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        stat.S_IRUSR | stat.S_IWUSR,
    )
```

### 3.4 ◇-2:Qwen 是唯一一个**写回别人家凭据文件**的 provider

其他所有 provider 的 token 都落在 `~/.hermes/auth.json`。Qwen 不是:

`hermes_cli/auth.py:2552 @ 863e313`
```python
def _qwen_cli_auth_path() -> Path:
    return Path.home() / ".qwen" / "oauth_creds.json"
```

`_save_qwen_cli_tokens`(`hermes_cli/auth.py:2581`)**直接覆写 Qwen CLI 自己的凭据文件**。
这与 Codex 的设计**正好相反**——Codex 段的横幅明确说要避开这种做法:

`hermes_cli/auth.py:3561 @ 863e313`
```python
# OpenAI Codex auth — tokens stored in ~/.hermes/auth.json (not ~/.codex/)
#
# Hermes maintains its own Codex OAuth session separate from the Codex CLI
# and VS Code extension. This prevents refresh token rotation conflicts
# where one app's refresh invalidates the other's session.
```

**影响 / 取舍**:Qwen 走的是"我不自己登录,只当 Qwen CLI 会话的续命工具"路线,
所以刷新结果必须写回原文件,否则 Qwen CLI 下次会拿着已被轮换掉的 refresh_token 失败。
代价是 Hermes 对一个不属于自己的文件有写权,且和 Codex 段建立的原则相冲突。
未见文档说明这个不一致(在 `hermes_cli/` 与 `website/docs` 中未搜到 Qwen 写回的说明,
搜索面见 §9)。

### 3.5 负结论:**没有任何系统钥匙串集成**

搜索面与结果:

```console
$ cd /home/user/hermes-agent
$ grep -n "keyring\|keychain\|Keychain\|libsecret\|wincred\|credential_manager\|SecretService" \
      hermes_cli/auth.py hermes_cli/auth_commands.py
(无输出)

$ grep -rn "^import keyring\|^from keyring\|import keyring" --include=*.py .
(无输出)

$ grep -rn "find-generic-password\|security add-generic" --include=*.py .
./agent/anthropic_adapter.py:972:            ["security", "find-generic-password",
```

排除项:搜索包含全仓所有 `.py`,排除 `.git`。唯一命中在 `agent/anthropic_adapter.py`,
而且是**只读借用**——读 Claude Code 自己存在 macOS 钥匙串里的条目,不是 Hermes 的落点:

`agent/anthropic_adapter.py:969 @ 863e313`
```python
    try:
        # Read the "Claude Code-credentials" generic password entry
        result = subprocess.run(
            ["security", "find-generic-password",
             "-s", "Claude Code-credentials",
             "-w"],
```

**结论:Hermes 从不把自己的凭据写进任何操作系统钥匙串。** 全部落文件,靠 POSIX
权限位 + O_EXCL 保护。这是一个明确的设计选择(跨平台一致 + 容器友好),
代价是 Windows 上没有强制的权限保护(测试文件自己声明了这一点,
`tests/hermes_cli/test_auth_toctou_file_modes.py:31` 直接 skip Windows)。

### 3.6 跨 profile 的第四个落点:共享 Nous store

`hermes_cli/auth.py:5232 @ 863e313`
```python
# -----------------------------------------------------------------------------
# Shared Nous token store — lets OAuth credentials persist across profiles
# so a new `hermes --profile <name> auth add nous --type oauth` can one-tap
# import instead of running the full device-code flow every time.
#
# File lives at ${HERMES_SHARED_AUTH_DIR}/nous_auth.json, defaulting to
# ``<hermes-root>/shared/nous_auth.json`` where ``<hermes-root>`` is what
# ``get_default_hermes_root()`` returns — ``~/.hermes`` on Linux/macOS,
# ``%LOCALAPPDATA%\hermes`` on native Windows, or the Docker/custom root.
# It is OUTSIDE any named profile's HERMES_HOME so named profiles (which
# typically live under ``<hermes-root>/profiles/<name>/``) all see the
# same file.
```

这解释了为什么**只有 Nous** 有第三把锁(`_nous_shared_store_lock`),
以及为什么 `_auth_store_lock` 的 docstring 要专门规定锁序(§5.3)。

---

## 4. 凭据轮换:`_is_env_config_key` 这条改道规则

### 4.1 规则在哪、判据是什么

判据函数(注意:它**只**被 `hermes config set` 一族调用,不被登录流程调用):

`hermes_cli/config.py:1152 @ 863e313`
```python
def _is_env_config_key(key: str) -> bool:
    """Return whether `hermes config set` routes this key to .env."""
    if "." in key:
        return False
    key_upper = key.upper()
    api_keys = [
        'OPENROUTER_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'VOICE_TOOLS_OPENAI_KEY',
        'EXA_API_KEY', 'PARALLEL_API_KEY', 'FIRECRAWL_API_KEY', 'FIRECRAWL_API_URL',
        'FIRECRAWL_GATEWAY_URL', 'TOOL_GATEWAY_DOMAIN', 'TOOL_GATEWAY_SCHEME',
        'TOOL_GATEWAY_USER_TOKEN', 'TAVILY_API_KEY',
        'BROWSERBASE_API_KEY', 'BROWSERBASE_PROJECT_ID', 'BROWSER_USE_API_KEY',
        'FAL_KEY', 'TELEGRAM_BOT_TOKEN', 'DISCORD_BOT_TOKEN',
        'TERMINAL_SSH_HOST', 'TERMINAL_SSH_USER', 'TERMINAL_SSH_KEY',
        'SUDO_PASSWORD', 'SLACK_BOT_TOKEN', 'SLACK_APP_TOKEN',
        'GITHUB_TOKEN', 'HONCHO_API_KEY',
    ]
    return (
        key_upper in api_keys
        or key_upper.endswith(('_API_KEY', '_TOKEN', '_SECRET'))
        or key_upper.startswith('TERMINAL_SSH')
    )
```

**判据拆解(四条,或关系)**:

1. **短路否定**:key 里含 `.` 一律返回 False。理由:带点的是 config.yaml 的嵌套路径
   (如 `tts.provider`),不可能是环境变量名。
2. **白名单命中**:26 个硬编码名字。注意里面有几个**不是密钥**:
   `FIRECRAWL_API_URL`、`FIRECRAWL_GATEWAY_URL`、`TOOL_GATEWAY_DOMAIN`、
   `TOOL_GATEWAY_SCHEME`、`BROWSERBASE_PROJECT_ID`——它们进 `.env` 是因为
   "和同族密钥放一起才好管",不是因为它们敏感。
3. **形状匹配(这条才是"API-key 形状")**:大写后以 `_API_KEY` / `_TOKEN` / `_SECRET`
   结尾。**这是覆盖面最大的一条**——任何 `<厂商>_API_KEY` 都自动命中,
   所以 §2.2 表里几十个 provider 的 key 一个都不用往白名单里加。
4. **前缀匹配**:`TERMINAL_SSH*`(SSH 主机/用户/私钥路径)。

**覆盖哪些键**——用第 3 条反推:`PROVIDER_REGISTRY` 里所有
`api_key_env_vars`(`OPENAI_API_KEY`、`DEEPSEEK_API_KEY`、`XAI_API_KEY`、
`MINIMAX_API_KEY`、`NVIDIA_API_KEY`、`HF_TOKEN`、`GH_TOKEN`、`GITHUB_TOKEN`、
`OLLAMA_API_KEY`、`KILOCODE_API_KEY` …)**全部命中**;
唯一的例外是 `GOOGLE_API_KEY` / `GEMINI_API_KEY` / `LM_API_KEY` / `FAL_KEY` 这类
以 `_API_KEY` 结尾的也命中,而 **`FAL_KEY`** 靠白名单兜住(它不以 `_API_KEY` 结尾)。

**◇-3:`ANTHROPIC_TOKEN` 与 `CLAUDE_CODE_OAUTH_TOKEN` 靠第 3 条命中,不在白名单里。**
`ANTHROPIC_API_KEY` 在白名单里显式列出,但同一个 provider 的另外两个 env var 不在
(`hermes_cli/auth.py:355` 的 `api_key_env_vars`)。它们仍然会改道 `.env`,
因为都以 `_TOKEN` 结尾。这不是 bug,但说明白名单是历史沉积,不是设计上的完整清单。

### 4.2 调用点:三处,都在 `hermes config set` 一族

```console
$ grep -rn "_is_env_config_key" --include=*.py /home/user/hermes-agent
hermes_cli/config.py:1152:def _is_env_config_key(key: str) -> bool:
hermes_cli/config.py:4857:    if _is_env_config_key(key):
hermes_cli/config.py:5049:    if _is_env_config_key(key):
hermes_cli/config.py:5081:    if _is_env_config_key(key):
```

主调用点(任务书给的 `config.py:4856` 锚点指的就是这里,实际判据在 4857):

`hermes_cli/config.py:4856 @ 863e313`
```python
    # Check if it's an API key (goes to .env)
    if _is_env_config_key(key):
        # Unified lifecycle: also rotates any config.yaml mirror of the old
        # value so a stale higher-precedence copy can't win (#62269).
        from hermes_cli.credential_lifecycle import save_provider_env_credential

        save_provider_env_credential(key.upper(), value)
        print(f"✓ Set {key} in {get_env_path()}")
        return
```

### 4.3 轮换为什么不能只写 `.env`:镜像清洗

`save_provider_env_credential` 不只是写 `.env`,它做三件事:

`hermes_cli/credential_lifecycle.py:213 @ 863e313`
```python
def save_provider_env_credential(env_var: str, value: str) -> Dict[str, Any]:
    """Save/update a credential in ``.env`` and reconcile every mirror.

    After the ``.env`` write, any config.yaml mirror that held the PREVIOUS
    value of this var (``model.api_key`` etc.) is updated to the new value so
    a stale higher-precedence copy cannot shadow the rotation (#62269).
    Suppressed ``env:<VAR>`` pool sources are re-enabled so a deliberate
    re-add through the UI behaves like ``hermes auth add``.
    """
    from hermes_cli.config import load_env, save_env_value

    old_value = load_env().get(env_var)
    save_env_value(env_var, value)

    config_updates: List[str] = []
    if value and old_value and old_value != value:
        config_updates = _scrub_config_yaml_mirrors(old_value, value)
```

**失效链(这是 #62269 的教训,值得完整讲一遍)**:
用户曾经把某个 key 同时写进了 `config.yaml` 的 `model.api_key`(比如通过
custom provider 配置)和 `.env`。`config.yaml` 的优先级**更高**。
后来用户轮换密钥,只 `hermes config set XXX_API_KEY <新值>` —— 新值写进 `.env`,
但 `config.yaml` 里那份**旧值**还在,而且赢。表现:用户明明换了 key,请求还是用旧 key
打过去,报 401,而 `hermes config get` 显示的是新 key。修法就是上面这段:
写完 `.env` 后,拿 `old_value` 去 `config.yaml` 里做一次全量替换。

第三件事是**解除抑制**:

`hermes_cli/credential_lifecycle.py:231 @ 863e313`
```python
    # A prior UI/CLI removal may have suppressed this env source; a fresh
    # save is an explicit re-add, so lift the suppression for every provider
    # that reads this var.
    try:
        from hermes_cli.auth import unsuppress_credential_source

        for provider in _providers_for_env_var(env_var):
            unsuppress_credential_source(provider, f"env:{env_var}")
    except Exception:
        pass
```

"抑制"(suppression)是 `auth.json` 里的一张 `suppressed_sources` 表,
记录"用户明确删掉过这个来源,不要再自动把它塞回凭据池":

`hermes_cli/auth.py:1717 @ 863e313`
```python
def suppress_credential_source(provider_id: str, source: str) -> None:
    """Mark a credential source as suppressed so it won't be re-seeded."""
    with _auth_store_lock():
        auth_store = _load_auth_store()
        suppressed = auth_store.setdefault("suppressed_sources", {})
        provider_list = suppressed.setdefault(provider_id, [])
        if source not in provider_list:
            provider_list.append(source)
        _save_auth_store(auth_store)
```

结构是 `{provider_id: [source, ...]}`。重新写入凭据等于用户改主意,所以要清掉。
`auth_commands.py` 里 `auth add` 也做同样的事,注释把这叫"一致的 re-engagement 模式":

`hermes_cli/auth_commands.py:180 @ 863e313`
```python
    # Clear ALL suppressions for this provider — re-adding a credential is
    # a strong signal the user wants auth re-enabled.  This covers env:*
    # (shell-exported vars), gh_cli (copilot), claude_code, qwen-cli,
    # device_code (codex), etc.  One consistent re-engagement pattern.
    # Matches the Codex device_code re-link pattern that predates this.
```

### 4.4 与之配套:读取侧的 "`.env` 优先于 `os.environ`"

轮换要生效,读取侧必须**先看 `.env` 再看进程环境**,否则父进程继承下来的陈旧
`export` 会盖住新写的 `.env`:

`hermes_cli/auth.py:648 @ 863e313`
```python
    from hermes_cli.config import get_env_value_prefer_dotenv
    for env_var in pconfig.api_key_env_vars:
        # Prefer ~/.hermes/.env over os.environ so a deliberate key rotation
        # in the user's .env file isn't shadowed by a stale shell export
        # inherited from a parent process (Codex CLI, test runners, etc.).
        val = (get_env_value_prefer_dotenv(env_var) or "").strip()
        if has_usable_secret(val):
            return val, env_var
```

"usable" 的判据自己也是一层过滤——**空、太短、占位符字样都不算数**:

`hermes_cli/auth.py:618 @ 863e313`
```python
def has_usable_secret(value: Any, *, min_length: int = 4) -> bool:
    """Return True when a configured secret looks usable, not empty/placeholder."""
    if not isinstance(value, str):
        return False
    cleaned = value.strip()
    if len(cleaned) < min_length:
        return False
    if cleaned.lower() in _PLACEHOLDER_SECRET_VALUES:
        return False
    return True
```

(对应测试:`tests/hermes_cli/test_auth_usable_secret.py`,本轮实跑通过。)

**API-key 的完整来源优先级**(`_resolve_api_key_provider_secret`,`hermes_cli/auth.py:630`):
`copilot` 特判 → `.env` → `os.environ` → credential pool(`auth.json`)。
凭据池是**最后**的兜底,来源标记成 `credential_pool:<provider>`。

---

## 5. token 刷新与过期

### 5.1 什么时候算"该刷了":提前量(skew)

每家一个常量,单位秒:

`hermes_cli/auth.py:83 @ 863e313`
```python
ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 120       # refresh 2 min before expiry
```

| provider | 常量 | 值 | 定义处 |
|---|---|---|---|
| Nous | `ACCESS_TOKEN_REFRESH_SKEW_SECONDS` | 120 | `hermes_cli/auth.py:83` |
| Codex | `CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS` | 120 | `hermes_cli/auth.py:111` |
| xAI | `XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS` | **3600** | `hermes_cli/auth.py:122` |
| Qwen | `QWEN_ACCESS_TOKEN_REFRESH_SKEW_SECONDS` | 120 | `hermes_cli/auth.py:125` |
| Spotify | `SPOTIFY_ACCESS_TOKEN_REFRESH_SKEW_SECONDS` | 120 | `hermes_cli/auth.py:131` |
| MiniMax | `MINIMAX_OAUTH_REFRESH_SKEW_SECONDS` | 60 | `hermes_cli/auth.py:95` |

xAI 的 3600 是个异类。它**不是**随手写大的,常量上方有一段完整的理由——
为 gateway / cron 这类"半小时才碰一次 provider"的负载留出余量:

`hermes_cli/auth.py:117 @ 863e313`
```python
# xAI/Grok OAuth access tokens are intentionally short-lived (about 6h in
# current SuperGrok flows). A two-minute refresh window is too narrow for
# gateway/cron workloads that may only touch the provider every 30 minutes,
# leaving brief but noisy credential-expiry gaps. Refresh up to one hour
# early so ordinary runtime calls keep the token warm without user reauth.
XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 3600
```

**注意这段注释的前提**:"about 6h" 的 token。6 小时 token 配 1 小时 skew 完全合理。
问题出在这个前提**后来不成立了**——device-code 登录发的是 15 分钟 token,
于是同一个常量从"合理余量"变成"永远在刷"。这是一个值得完整复述的事故:

`hermes_cli/auth.py:4653 @ 863e313`
```python
def _xai_proactive_refresh_skew_seconds(access_token: str) -> int:
    """How far before JWT ``exp`` to proactively refresh xAI OAuth tokens.

    SuperGrok sessions can still ship multi-hour access tokens, where the
    gateway-oriented :data:`XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS` window
    makes sense. Device-code logins often return ~15-minute JWTs; applying
    the full hour-long skew to those forces a refresh on *every* credential
    resolution (chat turn, Imagine tool call, ``hermes auth status``, …),
    which burns single-use refresh tokens and races concurrent callers into
    ``invalid_grant`` quarantine.
    """
```

**因果经过**:xAI 的 skew 设成 1 小时,是为了配合"多小时有效期"的 SuperGrok token。
但 device-code 登录发的是 **15 分钟** 的 JWT。15 分钟 < 1 小时 ⇒
`_xai_access_token_is_expiring(token, 3600)` **永远为真** ⇒ 每一次凭据解析
(每个聊天轮次、每次工具调用、每次 `hermes auth status`)都触发一次刷新 ⇒
OAuth refresh_token 是**单次使用**的,连续刷新把它烧光 ⇒ 并发的两个调用者
拿着同一个已被消费的 refresh_token 去换 ⇒ 服务端回 `invalid_grant` ⇒
`_is_terminal_xai_oauth_refresh_error` 判定为终局失败 ⇒ 凭据被隔离(quarantine)⇒
**用户被登出,必须重新登录**。

修法是让 skew 跟着 token 的实际剩余寿命走:

`hermes_cli/auth.py:4677 @ 863e313`
```python
        remaining = float(exp) - time.time()
        if remaining <= 0:
            return max_skew
        if remaining <= 45 * 60:
            return min(120, max_skew)
        return max_skew
```

剩余寿命 ≤ 45 分钟的 token,skew 压到 120 秒;否则才用 1 小时。

### 5.2 续失败怎么办:分"暂时"与"终局"两类

三个 provider 各有一个终局判定器:
`_is_terminal_nous_refresh_error`(`hermes_cli/auth.py:5474`)、
`_is_terminal_xai_oauth_refresh_error`(`hermes_cli/auth.py:5484`)、
`_is_terminal_codex_oauth_refresh_error`(`hermes_cli/auth.py:5501`)。

- **暂时失败**(网络超时、429 配额):原样抛出,**不动磁盘上的 token**。
  下一次调用还会再试。
- **终局失败**(400/401/403、`invalid_grant`、token 被吊销):走 **quarantine(隔离)**——
  把 access/refresh token 从磁盘上抹掉,但**保留路由元数据**,并记一条
  `last_auth_error`。目的是让下一次调用**快速失败**,而不是再打一次注定失败的网络请求。

判定"终局"靠的是 `AuthError` 上的 `code` + `relogin_required` 两个字段,**不是** HTTP
状态码本身——状态码在更早的层已经被翻译成 code:

`hermes_cli/auth.py:5484 @ 863e313`
```python
def _is_terminal_xai_oauth_refresh_error(exc: Exception) -> bool:
    """True when retrying the same xAI OAuth refresh token cannot succeed.

    ``xai_refresh_failed`` covers HTTP 400/401/403 from the token endpoint
    (invalid_grant, token revoked, refresh_token_reused).
    ``xai_auth_missing_refresh_token`` means the pool entry has no refresh
    token at all — retrying will never work.
    Both carry ``relogin_required=True``; transient failures (429, 5xx) do not.
    """
    return (
        isinstance(exc, AuthError)
        and exc.provider == "xai-oauth"
        and exc.code in {"xai_refresh_failed", "xai_auth_missing_refresh_token"}
        and bool(exc.relogin_required)
    )
```

注意它还比对了 `exc.provider` —— 一个来自别的 provider 的同名 code 不会被误判成
xAI 的终局失败。

xAI 的隔离现场(可以完整看到"抹哪些字段、留哪些字段"):

`hermes_cli/auth.py:5024 @ 863e313`
```python
                    if _is_terminal_xai_oauth_refresh_error(exc):
                        # Terminal failure (HTTP 400/401/403 — invalid_grant, token revoked).
                        # Clear dead tokens from auth.json so subsequent sessions fail fast
                        # without a network retry. Mirrors credential_pool.py quarantine.
                        try:
                            _q_store = _load_auth_store()
                            _q_state = _load_provider_state(_q_store, "xai-oauth") or {}
                            _q_tokens = dict(_q_state.get("tokens") or {})
                            _q_tokens.pop("access_token", None)
                            _q_tokens.pop("refresh_token", None)
                            _q_state["tokens"] = _q_tokens
```

Nous 的隔离多做一件事:**先记取证日志再抹**,而且专门规定必须用 `warning` 级别:

`hermes_cli/auth.py:5530 @ 863e313`
```python
    """Keep routing metadata but remove dead OAuth material so it is not replayed."""
    # Forensic logging BEFORE we clear the token material. A hosted agent
    # can take a terminal invalid_grant and get quarantined here silently: the
    # only downstream signal is a "No access token found" WARNING once the pool
    # is already empty, which is too late to root-cause. A managed log drain may
    # be WARNING-only, so this MUST be logger.warning (INFO never reaches it).
```

**refresh_token 本身不会被写进日志**,只写 SHA-256 前 12 位指纹:

`hermes_cli/auth.py:5537 @ 863e313`
```python
    # Redaction safety: emit ONLY the 12-char SHA-256 hex prefix of the refresh
    # token (correlates to NAS's refreshTokenHash without leaking the secret) plus
    # sizes/booleans. NEVER pass a raw token/agent_key into the log call — Hermes
    # has a known bug class where credential-shaped literals get corrupted in logs.
```

**Codex 还有第四条路:自愈(self-heal)。** 终局失败时先别放弃,去
`~/.codex/auth.json` 捞一份 Codex CLI 刚轮换过的新 token:

`hermes_cli/auth.py:3910 @ 863e313`
```python
    except AuthError as exc:
        # Self-heal cross-store refresh_token rotation. Hermes keeps its OWN
        # Codex OAuth token (per profile + top-level), separate from the Codex
        # CLI's ~/.codex/auth.json. OAuth refresh_tokens are single-use, so when
        # the Codex CLI (or another Hermes process) rotates the shared token,
        # this frozen copy's refresh_token goes stale and the refresh fails with
        # a relogin-required error (invalid_grant / refresh_token_reused / 401).
        # Before surfacing that as a hard 401 to the turn, adopt the canonical
        # fresh token from ~/.codex/auth.json (the Codex CLI keeps it current) so
        # idle profiles / desktop sessions recover automatically instead of
        # 401'ing until a manual re-auth. Transient failures (e.g. 429 quota)
        # keep relogin_required=False — the stored token is still valid there, so
        # we never self-heal those and re-raise unchanged.
        if not getattr(exc, "relogin_required", False):
            raise
```

(行为规格:`tests/hermes_cli/test_auth_codex_self_heal.py`,本轮实跑通过。)

### 5.3 并发续会不会重复续:三层防护

**第一层:跨进程 flock。** 所有 auth.json 的读-改-写都包在 `_auth_store_lock()` 里,
底层是 `fcntl.flock` / Windows `msvcrt.locking`,并且**按线程可重入**:

`hermes_cli/auth.py:1121 @ 863e313`
```python
    """Cross-process advisory flock helper.

    Reentrant per-thread via ``holder.depth``. Falls back to a depth-only
    guard when neither ``fcntl`` nor ``msvcrt`` is available (rare).
    Callers supply their own ``threading.local`` so independent locks
    (e.g. profile auth.json vs shared Nous store) don't share reentrancy
    state — that would let one lock's reentrant acquisition silently skip
    the other's kernel-level flock.
    """
```

注意最后那句取舍:**每把锁必须有自己的 `threading.local`**。如果共用一个,
线程在持有 A 锁的情况下去拿 B 锁,`depth > 0` 会让它直接跳过 B 的内核 flock ——
看起来拿到了,实际没有。所以有 `_auth_lock_holder_for(target_path)`
(`hermes_cli/auth.py:1104`)按规范化路径分配 holder。

**锁序被写进 docstring 当契约**:

`hermes_cli/auth.py:1194 @ 863e313`
```python
    ``target_path`` is required for profile-to-global write-throughs. A profile
    lock does not protect the distinct global auth store; each path therefore
    uses its own reentrancy tracker and kernel lock.

    Lock ordering invariant: when this lock is held together with
    ``_nous_shared_store_lock``, acquire ``_auth_store_lock`` FIRST
    (outer) and the shared Nous lock SECOND (inner). All runtime
    refresh paths follow this order; violating it risks deadlock
    against a concurrent import on the shared store.
    """
```

**第二层:拿到锁后重新读、重新判(double-check)。** 这是"不重复续"的关键。
xAI 的写法最清楚——锁外判一次决定要不要进临界区,进去后**把整套判断重做一遍**:

`hermes_cli/auth.py:4996 @ 863e313`
```python
    if should_refresh:
        with _auth_store_lock(timeout_seconds=max(float(AUTH_LOCK_TIMEOUT_SECONDS), refresh_timeout_seconds + 5.0)):
            data = _read_xai_oauth_tokens(_lock=False)
            tokens = dict(data["tokens"])
            access_token = str(tokens.get("access_token", "") or "").strip()
            discovery = dict(data.get("discovery") or {})
            token_endpoint = str(discovery.get("token_endpoint", "") or "").strip()
            redirect_uri = str(data.get("redirect_uri", "") or "").strip()
            effective_skew = (
                int(refresh_skew_seconds)
                if refresh_skew_seconds is not None
                else _xai_proactive_refresh_skew_seconds(access_token)
            )
            should_refresh = bool(force_refresh)
            if (not should_refresh) and refresh_if_expiring:
                should_refresh = _xai_access_token_is_expiring(access_token, effective_skew)
            if should_refresh:
```

两个进程同时发现 token 快过期 → 都想刷 → A 先拿到锁,刷完写盘、放锁 →
B 拿到锁,**重读磁盘**,发现 token 已经是新的、不再 expiring → `should_refresh` 变 False →
**不刷**。单次使用的 refresh_token 只被消费一次。

Nous 走的是另一种写法:**整个读-判-刷-写都在锁内**,连"要不要刷"的判断都在锁里,
所以天然没有 double-check 的必要:

`hermes_cli/auth.py:5870 @ 863e313`
```python
    with _provider_state_transaction("nous") as (
        auth_store,
        state,
        state_source_path,
    ):
```

`hermes_cli/auth.py:5910 @ 863e313`
```python
        with _nous_shared_store_lock(timeout_seconds=max(timeout_seconds + 5.0, AUTH_LOCK_TIMEOUT_SECONDS)):
            merged_shared = _merge_shared_nous_oauth_state(state)
            access_token = state.get("access_token")
            refresh_token = state.get("refresh_token")
```

`hermes_cli/auth.py:5921 @ 863e313`
```python
            if not _is_expiring(state.get("expires_at"), refresh_skew_seconds):
```

注意这里 `_provider_state_transaction` 本身就实现了"锁 → 读 → 再锁源 → **重读源**"
这套两阶段,因为 profile 模式下真正的状态可能在 global auth.json 里:

`hermes_cli/auth.py:1370 @ 863e313`
```python
    """Lock the active auth store and any global fallback source in order.

    Profile-backed refresh paths must take the global auth-store lock before
    any provider-specific shared-store lock. Re-reading the source after the
    target lock is acquired prevents both stale refreshes and whole-file lost
    updates without inverting the documented auth -> shared lock order.
    """
```

**第三层:进程内 5 秒记忆(memo)。** 光有锁还不够——启动时几十个"托管工具"的
健康检查会同时来要 token,每个都要付两次跨进程文件锁的代价:

`hermes_cli/auth.py:5860 @ 863e313`
```python
    global _RESOLVE_TOKEN_CACHE
    # Memo: collapse the startup burst of managed-tool check_fns into one
    # network refresh. Only cache a successful, non-forced resolution for a
    # short window; force_fresh / error paths bypass and don't populate it.
```

memo 的安全性论证写在快速路径旁边——**能进 memo 的 token 至少还有 skew 秒寿命
(≥120s),5 秒的 memo 不可能发出一个已过期的 token**:

`hermes_cli/auth.py:5924 @ 863e313`
```python
                # Populate the memo on the valid-token fast path too: the
                # startup burst usually finds a *valid* token, but each
                # check_fn call still pays two cross-process file locks and
                # state reads to reach this return. The token has at least
                # refresh_skew_seconds (>= 120s) of life here, so a 5s memo
                # can never serve an expired token.
```

**第四层(池维度):写回时按 `last_status_at` 新旧合并。** 凭据池不是单条 token,
写回时若直接覆盖会丢掉另一个进程刚写的冷却状态:

`hermes_cli/auth.py:1662 @ 863e313`
```python
    Re-read the on-disk pool under the same lock and merge entries present on
    disk but missing from ``entries``. Those were added by another process after
    the caller loaded its in-memory snapshot; without this merge a later
    rotation/exhaustion rewrite drops the concurrent credential.

    For entries present on BOTH sides, status fields are merged by
    ``last_status_at`` recency via ``_merge_disk_cooldown_state`` so a stale
    snapshot cannot erase a cooldown/quarantine another process just wrote.
```

### 5.4 ■-R8C-A(新):`_load_auth_store` 的读失败契约只在自己这层成立,
###        `_load_global_auth_store` 把它吞掉了

`_load_auth_store` 有一条**刻意**的设计:**读不出来(OSError)要抛,不能降级成空 store**,
因为这个模块有约 15 处"读-改-写",降级成空再存一次就等于**抹掉全部凭据**:

`hermes_cli/auth.py:1220 @ 863e313`
```python
    try:
        raw = json.loads(auth_file.read_text(encoding="utf-8"))
    except OSError:
        # The file exists (checked above) but could not be READ: EMFILE under
        # fd exhaustion, EACCES, EIO, a stalled network mount. None of those
        # mean the contents are bad, and this module does read-modify-write in
        # ~15 places, so degrading to an empty store here is one
        # _save_auth_store() away from erasing every stored credential.
        # Fail loudly instead and leave the file on disk untouched.
```

(行为规格:`tests/hermes_cli/test_auth_store_read_failure.py`,三种 errno 参数化,本轮实跑通过。)

**但 global 回退路径把这个契约整个包在 bare except 里**:

`hermes_cli/auth.py:1081 @ 863e313`
```python
    try:
        return _load_auth_store(global_path)
    except Exception:
        # A malformed global store must not break profile reads. The
        # profile's own auth store is still authoritative.
        return {}
```

**现象**:profile 模式下,如果 **global** 的 `~/.hermes/auth.json` 因 EMFILE / EACCES /
挂载卡死而读不出来,`read_credential_pool()` 会静默地返回"该 provider 在 global 没有条目",
于是 `is_provider_explicitly_configured()` 第 4 步查不到池条目——而这一步正是
"用户到底有没有显式配过这个 provider"的最后一道判据:

`hermes_cli/auth.py:1868 @ 863e313`
```python
    # 4. Check persisted credential-pool entries that came from EXPLICIT flows
    # the user initiated inside Hermes (manual add / device-code / PKCE), plus
    # env-backed pool entries. This intentionally excludes ambient borrowed
    # sources like gh_cli / claude_code / qwen-cli.
    try:
        for entry in read_credential_pool(normalized):
```

四步全不命中就返回 False,于是可能判定为"用户没配过这个 provider",进而拒绝使用
本来存在的凭据。用户看到的是"没登录",而不是"读不出来"。

**为什么我把它标 ■ 而不是设计取舍**:注释说的理由是 "malformed global store"(格式损坏),
而 `_load_auth_store` **已经**把格式损坏单独处理了(走 `except Exception` 那支,
备份成 `.json.corrupt` 后返回空 store,不抛)。也就是说,能抛到这里的**只有 OSError**,
恰恰是上面那段注释论证"不该降级"的那一类。这里的 `except Exception` 捕获面
比它声称的理由宽。

**影响评估(诚实说)**:比 ■-R8B-12 轻一档——这是**只读**路径,不会写盘,
不会丢数据,只会让一个本可用的 global 凭据在 profile 里暂时不可见,
且故障消失后自动恢复。但它确实让"读失败要响亮"这条契约在 profile 模式下失效了。
**本轮未写复现测试**,证据是上述两处代码的语义对照,不是实跑。

---

## 6. `_update_config_for_provider`(`hermes_cli/auth.py:7270`)一带的完整上下文

> ■-R8B-12(原 ■-R8B-08)已在 R8B 定案,本节**不重证**,只补齐现场上下文。

### 6.1 它到底写了什么:两个文件,两次写

`hermes_cli/auth.py:7270 @ 863e313`
```python
def _update_config_for_provider(
    provider_id: str,
    inference_base_url: str,
    default_model: Optional[str] = None,
) -> Path:
    """Update config.yaml and auth.json to reflect the active provider.

    When *default_model* is provided the function also writes it as the
    ``model.default`` value.  This prevents a race condition where the
    gateway (which re-reads config per-message) picks up the new provider
    before the caller has finished model selection, resulting in a
    mismatched model/provider (e.g. ``anthropic/claude-opus-4.6`` sent to
    MiniMax's API).
    """
```

**第一次写:`auth.json`,只改一个字段 `active_provider`。**

`hermes_cli/auth.py:7284 @ 863e313`
```python
    # Set active_provider in auth.json so auto-resolution picks this provider
    with _auth_store_lock():
        auth_store = _load_auth_store()
        auth_store["active_provider"] = provider_id
        _save_auth_store(auth_store)
```

**第二次写:`config.yaml`,整文件替换。**

`hermes_cli/auth.py:7290 @ 863e313`
```python
    # Update config.yaml model section
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    require_readable_config_before_write(config_path)

    config = read_raw_config()
```

写进去的是 `model` 这个 section 的四个键:`provider`、`base_url`、
(可能的)`default`、以及**清理**掉的旧 custom-provider 内联凭据:

`hermes_cli/auth.py:7305 @ 863e313`
```python
    model_cfg["provider"] = provider_id
    if inference_base_url and inference_base_url.strip():
        model_cfg["base_url"] = inference_base_url.rstrip("/")
    else:
        # Clear stale base_url to prevent contamination when switching providers
        model_cfg.pop("base_url", None)

    # Clear stale endpoint credentials left over from a previous custom provider.
    # Built-in providers resolve credentials from env/auth state, not inline
    # model.api_key.
    from hermes_cli.config import clear_model_endpoint_credentials

    clear_model_endpoint_credentials(model_cfg)
```

还有一条**跨 provider 的模型名兼容**处理——OpenRouter 风格的 `厂商/模型` 名字
在直连 API 上必然报错,所以切走时要换掉:

`hermes_cli/auth.py:7319 @ 863e313`
```python
    # When switching to a non-OpenRouter provider, ensure model.default is
    # valid for the new provider.  An OpenRouter-formatted name like
    # "anthropic/claude-opus-4.6" will fail on direct-API providers.
    if default_model:
        cur_default = model_cfg.get("default", "")
        if not cur_default or "/" in cur_default:
            model_cfg["default"] = default_model
```

最后一步就是 ■-R8B-12 的落点:

`hermes_cli/auth.py:7327 @ 863e313`
```python
    config["model"] = model_cfg

    atomic_yaml_write(config_path, config, sort_keys=False)
    return config_path
```

**注意 `config` 这个变量**:它是第 7295 行 `read_raw_config()` 的返回值。
如果 YAML 解析失败,`read_raw_config()` **返回 `{}`**:

`hermes_cli/config.py:2958 @ 863e313`
```python
        try:
            with open(config_path, encoding="utf-8") as f:
                data = fast_safe_load(f) or {}
        except Exception as e:
            _warn_config_parse_failure(config_path, e)
            return {}
```

于是 7327 的 `config["model"] = model_cfg` 变成"给一个空字典加一个键",
7329 把这个**只有 model 一节**的字典整文件写回去——用户的 tools / gateway / memory /
custom_providers 等所有配置节全部消失。

**而守卫为什么没拦住**:它只检查"能不能读到第一个字节",完全不碰 YAML 语法:

`hermes_cli/config.py:3065 @ 863e313`
```python
def require_readable_config_before_write(config_path: Optional[Path] = None) -> None:
    """Refuse to replace an existing config.yaml that cannot be read."""
    if config_path is None:
        config_path = get_config_path()
    try:
        config_path.stat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RuntimeError(
            f"Refusing to overwrite {config_path}: existing config.yaml cannot be accessed "
            f"({exc}). Fix the file permissions or move it aside first."
        ) from exc

    try:
        with open(config_path, "rb") as f:
            f.read(1)
    except OSError as exc:
        raise RuntimeError(
            f"Refusing to overwrite {config_path}: existing config.yaml cannot be read "
            f"({exc}). Fix the file permissions or move it aside first."
        ) from exc
```

**补充一条 R8B 可能没提的上下文**:仓库里**已经有**一个专门为这个类别设计的
"唯一写入口",而且它的 docstring 把根因说得一清二楚:

`hermes_cli/config.py:3089 @ 863e313`
```python
def atomic_config_write(config_path: Path, data: Any, **kwargs: Any) -> None:
    """Fail-closed atomic write for ``config.yaml``.

    The single chokepoint every config-update path should use instead of
    calling :func:`utils.atomic_yaml_write` directly. It runs
    :func:`require_readable_config_before_write` first, so a full-file
    replacement can never silently clobber an existing ``config.yaml`` that
    degraded to an empty dict on read (permission error, broken mount,
    transient I/O). New-file creation still works when the path is absent.

    Root cause this guards: ``read_raw_config()`` returns ``{}`` for BOTH an
    absent file and an unreadable-but-present file. Callers that read then
    overwrite can't tell the two apart, so an unreadable config would be
    replaced with only defaults or the single edited section. Routing every
    write through this helper enforces the invariant in one place rather than
    relying on each of ~15 independent write sites to remember the guard.
```

**关键观察**:根因描述里列的三种情况是 "permission error, broken mount, transient I/O"
——**全是 I/O 层的**,**没有列 YAML 语法错误**。所以这不是"作者忘了用 chokepoint"
(`_update_config_for_provider` 手写的 `require_readable_config_before_write` +
`atomic_yaml_write` 与 `atomic_config_write` **等价**),
而是**这个 chokepoint 的语义本身就没覆盖"可读但不可解析"这一类**。
换句话说:即使把 7329 改成调 `atomic_config_write`,■-R8B-12 **依然存在**。
修法必须动 `require_readable_config_before_write` 的判据(加一次 parse 试探),
或者动 `read_raw_config` 的返回契约(用哨兵值区分"不存在"与"解析失败")。

### 6.2 谁调它:9 个调用点,全部是"切换 provider"语义

```console
$ grep -rn "_update_config_for_provider" --include=*.py /home/user/hermes-agent \
      | grep -v "^.*tests/"
hermes_cli/auth.py:7270:def _update_config_for_provider(
hermes_cli/auth.py:7774:                    config_path = _update_config_for_provider("openai-codex", ...)
hermes_cli/auth.py:7797:                config_path = _update_config_for_provider("openai-codex", base_url)
hermes_cli/auth.py:7814:    config_path = _update_config_for_provider("openai-codex", ...)
hermes_cli/auth.py:7841:                    config_path = _update_config_for_provider(
hermes_cli/auth.py:7882:    config_path = _update_config_for_provider("xai-oauth", ...)
hermes_cli/auth.py:9195:        config_path = _update_config_for_provider(
hermes_cli/model_setup_flows.py:593:        _update_config_for_provider("nous", inference_url)
hermes_cli/model_setup_flows.py:706:        _update_config_for_provider("openai-codex", DEFAULT_CODEX_BASE_URL)
hermes_cli/model_setup_flows.py:787:        _update_config_for_provider("xai-oauth", base_url)
hermes_cli/model_setup_flows.py:835:        _update_config_for_provider("qwen-oauth", DEFAULT_QWEN_BASE_URL)
hermes_cli/model_setup_flows.py:890:    _update_config_for_provider("minimax-oauth", creds["base_url"])
```

**触发路径**(既然 `hermes login` 已死):用户跑 `hermes model` 或 `hermes setup`
→ `model_setup_flows.py` 里对应的 `*_flow` 函数 → OAuth 登录 → `_update_config_for_provider`。
`auth.py` 内部那 6 处则是 `_login_openai_codex` / `_login_xai_oauth` / `_login_nous`
自己在成功后写回。

**一次成功的 Codex 登录到底写了什么(把 7748–7819 串起来)**:

1. 先看 Hermes 自己的 auth store 里有没有可用凭据(`resolve_codex_runtime_credentials`),
   有且没过期就问用户"复用吗?" → 复用则**只调 `_update_config_for_provider`**
   (`hermes_cli/auth.py:7774`),不写 token。
2. 再看 `~/.codex/auth.json` 有没有 Codex CLI 的凭据,问"导入吗?" →
   导入则 `_save_codex_tokens` + `_update_config_for_provider`(`:7797`)。
3. 都不行才跑 device-code(`_codex_device_code_login`),
   然后 `_save_codex_tokens(creds["tokens"], creds.get("last_refresh"))`
   + `_update_config_for_provider`(`:7814`)。

`hermes_cli/auth.py:7810 @ 863e313`
```python
    creds = _codex_device_code_login()

    # Save tokens to Hermes auth store
    _save_codex_tokens(creds["tokens"], creds.get("last_refresh"))
    config_path = _update_config_for_provider("openai-codex", creds.get("base_url", DEFAULT_CODEX_BASE_URL))
```

**所以一次登录的落盘清单是**:
`auth.json.providers["openai-codex"].tokens`(token 本体)+
`auth.json.active_provider`(= `openai-codex`)+
`config.yaml.model.provider` / `.base_url`(可能还有 `.default`)。
**`.env` 一个字节都不写**——OAuth provider 与 `.env` 无关。

### 6.3 那个"有空判的孪生函数":`_reset_config_provider`(`hermes_cli/auth.py:7381`)

`hermes_cli/auth.py:7381 @ 863e313`
```python
def _reset_config_provider() -> Path:
    """Reset config.yaml provider back to auto after logout."""
    config_path = get_config_path()
    if not config_path.exists():
        return config_path
    require_readable_config_before_write(config_path)

    config = read_raw_config()
    if not config:
        return config_path

    model = config.get("model")
    if isinstance(model, dict):
        model["provider"] = "auto"
        if "base_url" in model:
            model["base_url"] = OPENROUTER_BASE_URL
    atomic_yaml_write(config_path, config, sort_keys=False)
    return config_path
```

**它是干什么的**:logout 的镜像操作。`_update_config_for_provider` 把
`model.provider` 设成具体 provider;这个把它设回 `"auto"`,并把 `base_url`
指回 OpenRouter。由 `logout_command` 调用:

`hermes_cli/auth.py:9226 @ 863e313`
```python
    should_reset_config = _should_reset_config_provider_on_logout(target)
    provider_name = get_auth_provider_display_name(target)

    if clear_provider_auth(target) or should_reset_config:
        if should_reset_config:
            _reset_config_provider()
```

**两者为什么会分叉——这是本节最值得记住的一点。**

差别只有第 7389–7390 那两行 `if not config: return config_path`。
在坏 YAML 场景下:

| | `_update_config_for_provider` | `_reset_config_provider` |
|---|---|---|
| `read_raw_config()` 返回 | `{}` | `{}` |
| 下一步 | `config["model"] = model_cfg`(给空字典塞键) | `if not config: return` —— **直接退出,不写** |
| 结果 | **整文件被替换成只有 model 一节** | **文件原样保留** |

**分叉的成因(推演,非代码断言)**:两个函数的语义天然不同。
`_reset_config_provider` 的工作是"改一个已存在的值",空配置意味着"没什么可改的",
`if not config: return` 是**顺手写出来的自然逻辑**,作者未必是为了防 clobber。
`_update_config_for_provider` 的工作是"设置一个值",空配置意味着"从头建",
`config["model"] = ...` 同样是自然逻辑。两条自然逻辑在"YAML 坏了"这个
**两人都没考虑过**的输入上,恰好一个安全一个危险。

`_reset_config_provider` 里还有另一个防御是 `_update_config_for_provider` 没有的:
`if not config_path.exists(): return`(第 7384–7385 行)——不存在就不创建。
而 `_update_config_for_provider` 反过来会 `mkdir(parents=True)` 并创建。
这同样是语义差异(reset 不该凭空造配置;set 应该)。

**结论**:这不是"一个函数漏抄了另一个函数的守卫",而是**两个语义不同的函数各自
写对了自己的主线逻辑,而正确性依赖的是一个两者都没显式处理的边界条件**。
这也是为什么 §6.1 说"改 chokepoint 才是真修法"——靠 code review 让每个写点
都记得抄一行 `if not config` 是 R7C/R8B 反复证明兜不住的那种约定。

---

## 7. `auth_commands.py` 与 `auth.py` 的分工

### 7.1 结论:命令层 vs 实现层,但**不是**干净的一刀切

**支撑分工判断的三条依据**:

**依据 1 —— 模块 docstring 与 import 方向。** `auth_commands.py` 第一行就把范围
限定在"凭据池子命令",并且 `import hermes_cli.auth as auth_mod`
(单向:commands → auth,`auth.py` 从不 import `auth_commands`):

`hermes_cli/auth_commands.py:1 @ 863e313`
```python
"""Credential-pool auth subcommands."""

from __future__ import annotations

import math
import sys
import time
from types import SimpleNamespace
import uuid
```

`hermes_cli/auth_commands.py:30 @ 863e313`
```python
import hermes_cli.auth as auth_mod
from hermes_cli.auth import PROVIDER_REGISTRY
```

反向验证(负结论):

```console
$ grep -n "auth_commands" /home/user/hermes-agent/hermes_cli/auth.py
(无输出)
```

**依据 2 —— `auth_commands.py` 是纯粹的 argparse 动作分派。** 802 行里没有任何
网络请求、没有任何文件锁、没有任何 token 刷新:

`hermes_cli/auth_commands.py:778 @ 863e313`
```python
def auth_command(args) -> None:
    action = getattr(args, "auth_action", "")
    if action == "add":
        auth_add_command(args)
        return
    if action == "list":
        auth_list_command(args)
        return
    if action == "remove":
        auth_remove_command(args)
        return
    if action == "reset":
        auth_reset_command(args)
        return
    if action == "status":
        auth_status_command(args)
        return
    if action == "logout":
        auth_logout_command(args)
        return
    if action == "spotify":
        auth_spotify_command(args)
        return
    # No subcommand — launch interactive mode
    _interactive_auth()
```

**依据 3 —— 每个动作都把实质工作转手给 `auth.py` 或 `agent/credential_pool.py`。**
最极端的例子是 logout,整个函数体就是一次转发(还顺手造了个假 `args`):

`hermes_cli/auth_commands.py:529 @ 863e313`
```python
def auth_logout_command(args) -> None:
    auth_mod.logout_command(SimpleNamespace(provider=getattr(args, "provider", None)))
```

status 同理:

`hermes_cli/auth_commands.py:513 @ 863e313`
```python
    status = auth_mod.get_auth_status(provider)
```

Spotify 也是纯转发:

`hermes_cli/auth_commands.py:533 @ 863e313`
```python
def auth_spotify_command(args) -> None:
    action = str(getattr(args, "spotify_action", "") or "login").strip().lower()
    if action in {"", "login"}:
        auth_mod.login_spotify_command(args)
        return
```

### 7.2 分工的**两处例外**(所以说"不是干净的一刀切")

**例外 1:`auth_commands.py` 自己持有 provider 的 OAuth 分派逻辑。**
`auth_add_command` 里对 anthropic / nous / openai-codex / xai-oauth / qwen-oauth /
minimax-oauth 各写了一段 `if provider == ...`(`hermes_cli/auth_commands.py:224–436`),
并且自己组装 `PooledCredential` 对象。这段逻辑本可以住在 `auth.py`。

它甚至持有一条**只有它知道的业务决策**——Codex 多账号不能走单例保存路径:

`hermes_cli/auth_commands.py:316 @ 863e313`
```python
        # Add a distinct, self-contained pool entry per account (matching the
        # qwen-oauth / minimax-oauth multi-account patterns, and the
        # xai-oauth path below) instead of routing through the singleton
        # ``_save_codex_tokens`` save path.
        # The singleton round-trip collapsed every added account into the
        # latest login: a second ``hermes auth add openai-codex`` overwrote
        # the first account's singleton-mirrored ``device_code`` entry rather
        # than creating an independent one (#39236). ``manual:device_code``
        # entries refresh from their own token pair, so they need no singleton
        # shadow.
```

**这条值得讲成故事**:用户跑两次 `hermes auth add openai-codex`,想加两个 ChatGPT 账号。
第一次加成功。第二次加完,**第一个账号消失了**。原因是 `_save_codex_tokens` 是
"单例"语义(auth.json 里 Codex 只有一份 `providers["openai-codex"]`),
它会往池里镜像一条 `device_code` 来源的条目;第二次登录覆盖了那份单例,
镜像条目也跟着被覆盖。修法是**绕开单例**,让 `auth add` 直接造独立的
`manual:device_code` 池条目——这类条目用自己那对 token 刷新,不需要单例影子。

**例外 2:`auth_commands.py` 直接调 `auth.py` 的私有函数(前导下划线)。**
至少 6 处:`auth_mod._read_shared_nous_state()`(:257)、
`auth_mod._nous_shared_store_path()`(:260)、
`auth_mod._try_import_shared_nous_state(...)`(:274)、
`auth_mod._nous_device_code_login(...)`(:289)、
`auth_mod._codex_device_code_login()`(:311)、
以及 `from hermes_cli.auth import _load_auth_store, unsuppress_credential_source`(:187)。

**影响**:`auth.py` 里那些 `_` 开头的函数**不是真正的私有**,它们是
`auth_commands.py` 与 `model_setup_flows.py` 依赖的事实公开 API。
重构 `auth.py` 时不能靠"下划线 = 可以随便改"这个惯例。

### 7.3 一句话分工

> `auth_commands.py` = **`hermes auth` 这一个命令的 UI 层**(argparse 分派、
> 交互提示、输出格式化、池条目组装);
> `auth.py` = **凭据的领域层**(注册表、存储、锁、OAuth 流程、刷新、状态查询),
> 同时**还兼着** `hermes logout` 与各 `_login_*` 的命令实现(§7 的"不干净"就在这里)。

`auth.py` 的 7266 段横幅自称 "CLI Commands — login / logout",
但这一段里塞的 1,975 行既有命令实现(`logout_command`)、又有配置写回
(`_update_config_for_provider`)、又有交互式模型选择(`_prompt_model_selection`,
288 行)、又有 MiniMax 的完整 OAuth 协议实现(8274–8780)。
**这是全文件里职责最混杂的一段**,也是 9,240 行这个体量的主要来源之一。

---

## 8. 实跑测试(行为规格)

### 8.1 环境

```console
$ /home/user/hermes-venv/bin/pip list | tail -n +3 | wc -l
87
$ id -u
0
```

venv 87 个包(`[dev]` extra + `aiohttp 3.14.1` + `brotlicffi 1.2.0.1`),以 root 运行,
容器无 IPv6、离线无 models.dev 目录 —— 与 CLAUDE.md 记录的 R8B 环境一致。

### 8.2 结果:14 个文件 / 125 用例 / 全绿

```console
$ cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
    bash scripts/run_tests.sh tests/hermes_cli/test_auth_commands.py \
    tests/hermes_cli/test_auth_provider_gate.py tests/hermes_cli/test_auth_codex_provider.py \
    tests/hermes_cli/test_auth_codex_quota_probe.py tests/hermes_cli/test_auth_codex_self_heal.py \
    tests/hermes_cli/test_auth_nous_provider.py tests/hermes_cli/test_auth_profile_fallback.py \
    tests/hermes_cli/test_auth_qwen_provider.py tests/hermes_cli/test_auth_ssl_macos.py \
    tests/hermes_cli/test_auth_store_read_failure.py tests/hermes_cli/test_auth_toctou_file_modes.py \
    tests/hermes_cli/test_auth_usable_secret.py tests/hermes_cli/test_auth_xai_oauth_provider.py \
    tests/hermes_cli/test_auth_loopback_ssh_hint.py

=== Summary: 14 files, 125 tests passed, 0 failed (100% complete) in 4.1s (8 workers) ===
```

**失败 0,跳过 0**(runner 汇总行不单列 skip;`grep -i skip` 在整份输出里无命中)。
本轮**没有**踩到 CLAUDE.md 记录的 5 个已知环境性失败——那 5 个分别在
`test_browser_connect_dual_stack.py` / `test_migrate_xai.py` / `test_gateway_service.py` /
`test_approvals_suggest.py` / `test_xai_provider_labels.py`,都不在 `test_auth_*` 这一族里。

**特别说明 `test_auth_toctou_file_modes.py` 在 root 下仍然通过**:它断言的是
`stat.S_IMODE(...) == 0o600`,即**写出来的 mode 位**,不是"能否读取"。
root 绕过的是权限**检查**,不是权限**设置**,所以 `os.open(..., S_IRUSR|S_IWUSR)`
写出的 mode 位在 root 下照样是 0600。(对比 CLAUDE.md 记的
`test_migrate_xai.py` 失败,那个断言的是 `chmod 000` 后应抛 `PermissionError`,
是"检查"类,才会被 root 破坏。)

`test_auth_ssl_macos.py` 在 Linux 下通过,是因为它 mock 了 `platform.system()`
而不是真的要 macOS。

### 8.3 这些测试当规格用,最有价值的三份

| 测试文件 | 它固定了什么行为契约 |
|---|---|
| `tests/hermes_cli/test_auth_store_read_failure.py` | OSError 必须**抛**、必须**保留原文件**;只有真损坏才降级 + 备份,且**没备份成功就不许在日志里说备份了** |
| `tests/hermes_cli/test_auth_toctou_file_modes.py` | 三个凭据写入点必须落 `0o600`、父目录 `0o700`,且必须是 O_EXCL **创建时**就对 |
| `tests/hermes_cli/test_auth_provider_gate.py` | `is_provider_explicitly_configured` 的四步判据:借来的凭据(gh_cli / claude_code / qwen-cli)**不算**用户显式配置 |

### 8.4 引用校验报数与「可校验比例」的结构性说明

```console
$ cd /home/user/hermes-study && python3 scripts/verify_citations.py \
      /home/user/hermes-agent notes/r8c-raw-auth-py.md; echo "EXIT=$?"

citations=130  OK=79  UNCHECKED=51
可校验比例 OK/130 = 60.8%  << 低于 70% 下限
OK: every code-block-backed citation matches the baseline
EXIT=0
```

**MISMATCH = 0,退出码 0,过关。** 首跑曾有 10 处 MISMATCH(全部为行号漂移,
其中 2 处是 `try:` 这种非唯一首行导致的定位歧义),已逐条手工核对基线后修正;
**未使用 `--fix`**,修正后裸跑复核如上。

**可校验比例 60.8% 低于 70% 报告下限,原因是结构性的,如实拆账**:

| 类别 | 条数 | 说明 |
|---|---|---|
| OK(带代码块、逐字比对通过) | 79 | 全部实质断言 |
| UNCHECKED — grep/shell 输出内的 `path:line` | 17 | `console` 围栏里的检索证据本身(如 §6.2 的调用点清单),其内容就是路径行号,无法也不该再配代码块 |
| UNCHECKED — §9 定案表 + §10 移交项的锚点 | ~28 | CLAUDE.md **要求**移交项必须附「锚点文件 + 行号」;这些锚点指向的结论多数已在正文用代码块证过,此处是索引不是新断言 |
| UNCHECKED — 正文交叉引用 | ~6 | 如"见 §3.4"式的回指 |

**没有为凑比例制造代码块**——`scripts/verify_citations.py` 自己的模块 docstring
(第 68 行一带)明确警告 "Making it blocking would push authors to manufacture code
blocks to clear a gate, which is worse than the disease"。本轮据此把比例如实报低,
并把 4 处**原本只有散文断言、但确实该有证据**的地方补成了代码块
(§2.1 的 `auth_type` 分派守卫、§5.1 的 xAI skew 立法理由、§5.2 的终局错误判定器、
§5.4 的 `is_provider_explicitly_configured` 第 4 步)。

---

## 9. 本段的 ▲ / ◇ / ■ / ◎ 汇总

| 编号 | 类型 | 锚点 | 现象 | 影响 |
|---|---|---|---|---|
| ▲-0 | ▲ | `hermes_cli/auth.py:7740` | `hermes login` 已删除,只剩 deprecation stub;任务书与旧文档里的"`hermes login` 一族"说法失效 | 中:找入口会找错 |
| ▲-1 | ▲ | `hermes_cli/auth.py:201` | `auth_type` 注释只列 4 种取值,实际有 7 种(多 `external_process` / `aws_sdk` / `vertex`) | 中:新增 auth_type 时容易漏分派点 |
| ▲-2 | ▲ | `hermes_cli/auth.py:355` vs `hermes_cli/auth_commands.py:36` | `anthropic` 注册表标 `api_key`,但命令层把它列入 `_OAUTH_CAPABLE_PROVIDERS` 且实际走 PKCE(实现在 `agent/anthropic_adapter.py:1501`) | 中:按 auth_type 统计 OAuth provider 会算错 |
| ▲-3 | ▲ | `hermes_cli/auth.py:1` | 模块 docstring 说 Codex 是 "future",实际已完整实现(`:8075`) | 低 |
| ◇-1 | ◇ | `hermes_cli/auth.py:2552` | Qwen 全套(200+ 行)藏在 "Timestamp / TTL helpers" 横幅段下,无自己的横幅 | 低:靠横幅导航会以为没实现 |
| ◇-2 | ◇ | `hermes_cli/auth.py:2581` | Qwen 是唯一**写回**第三方 CLI 凭据文件(`~/.qwen/oauth_creds.json`)的 provider,与 Codex 段 `:3561` 明确建立的"不共用"原则相反,无文档说明 | 中:安全审计面 |
| ◇-3 | ◇ | `hermes_cli/auth.py:2869` | `_oauth_pkce_code_verifier` / `_oauth_pkce_code_challenge` 是 `_spotify_code_verifier` / `_spotify_code_challenge`(`:2859`/`:2864`)的**逐字副本**,全仓**零调用者** | 低:死代码,但读者会以为有通用 PKCE 基建 |
| ◇-4 | ◇ | `hermes_cli/config.py:1152` | `_is_env_config_key` 白名单里混进 4 个**非密钥**键(`FIRECRAWL_API_URL`、`FIRECRAWL_GATEWAY_URL`、`TOOL_GATEWAY_DOMAIN`、`TOOL_GATEWAY_SCHEME`、`BROWSERBASE_PROJECT_ID`) | 低:它们只是"和同族密钥一起管" |
| ■-R8C-A | ■ | `hermes_cli/auth.py:1084` | `_load_global_auth_store` 用 `except Exception: return {}` 吞掉 `_load_auth_store` 刻意抛出的 OSError,理由(注释)只说 "malformed store",而损坏路径在 `:1229` 已被单独处理——能抛到这里的**只有** OSError | 低-中:只读路径,不丢数据;但 profile 模式下 global 凭据会静默不可见,用户看到"没登录"而非"读不出来"。**未写复现测试** |
| ◎-1 | ◎ | `hermes_cli/auth.py:5128` | 横幅自称 "generic, parameterized by provider" 的 device-code 实现,端点路径写死 Nous 形状(`:5138`),实际只有 Nous 用;Codex/xAI/MiniMax 各自重写 | 低:高估复用度 |
| ◎-2 | ◎ | `hermes_cli/config.py:3089` | `atomic_config_write` 自称 "single chokepoint … can never silently clobber",但其根因描述只覆盖 I/O 类失败,**不覆盖 YAML 语法错误**——即 ■-R8B-12 即使改用它也不会被修掉 | **中-高**:会误导修 ■-R8B-12 的人走错方向 |

**搜索面声明(用于上述负结论)**:
- 钥匙串:`grep -rn` 全仓 `.py`,模式 `keyring|keychain|Keychain|libsecret|wincred|credential_manager|SecretService`
  与 `find-generic-password|security add-generic`;排除 `.git`。唯一命中 `agent/anthropic_adapter.py:972`(只读借用)。
- `_oauth_pkce_code_*` 调用者:`grep -rn "_oauth_pkce_code" .` **不限文件类型**、排除 `.git`,仅命中两处定义。
- `auth.py` 反向依赖 `auth_commands`:`grep -n "auth_commands" hermes_cli/auth.py`,无输出。
- `_is_env_config_key` 调用点:`grep -rn --include=*.py` 全仓,4 处(1 定义 + 3 调用,全在 `config.py`)。

---

## 10. 本段未覆盖 / 存疑(每条带锚点 + 一句话现象)

1. **`_prompt_model_selection` 288 行未读**
   —— 锚点 `hermes_cli/auth.py:7435`;现象:登录成功后的交互式模型选择,含
   `_confirm_expensive_model_selection`(`:7401`)这样的"贵模型二次确认"逻辑,
   与凭据无关但占了 7266 段近 300 行,本轮只确认它存在、未读实现。

2. **Codex 配额探测与池冷却整块未精读**
   —— 锚点 `hermes_cli/auth.py:4166` 的 `_probe_codex_quota_restored`;现象:
   Codex 池条目被标 exhausted 后有一条主动探测恢复的路径(`:4251` 的
   `clear_codex_pool_quota_cooldowns` 会批量清冷却),本轮只跑了它的测试
   (`test_auth_codex_quota_probe.py`,通过),未读实现逻辑。

3. **Z.AI 四 endpoint 探测的具体判据未读**
   —— 锚点 `hermes_cli/auth.py:694` 的 `_probe_single_zai_endpoint`;现象:
   注释说 Z.AI 按"通用 vs coding 套餐"×"国际 vs 中国"分裂,一个 key 在错的
   endpoint 上返回 "Insufficient balance",本轮未读它靠什么响应特征判定"能用"。

4. **Spotify 回环 PKCE 的 callback handler 未读**
   —— 锚点 `hermes_cli/auth.py:2924` 的 `_make_spotify_callback_handler`;现象:
   这是全仓唯一在 CLI 侧起本地 HTTP server 收 OAuth callback 的地方
   (`_spotify_wait_for_callback` 在 `:2962`),与 device-code 的取舍对比很有价值,
   本轮只确认了它的存在与 `_spotify_validate_redirect_uri`(`:2900`)会校验回环地址。

5. **■-R8C-A 未写复现测试**
   —— 锚点 `hermes_cli/auth.py:1084`;现象:我的判断基于
   "`:1229` 的 `except Exception` 已经吃掉了所有解析类错误,所以能传播到 `:1084`
   的只剩 OSError" 这条代码语义推演,**没有实跑**一个"让 global auth.json 返回 EACCES
   然后观察 profile 侧凭据可见性"的用例。下一轮若要升格为定案,需要补这个测试。

6. **`suppressed_sources` 的完整生命周期未追**
   —— 锚点 `hermes_cli/auth.py:1717` 的 `suppress_credential_source`;现象:
   本轮只看到"谁清除抑制"(`hermes_cli/auth_commands.py:185`、`hermes_cli/credential_lifecycle.py:234`),
   没有系统追查"谁**设置**抑制"以及抑制状态如何影响 `credential_pool` 的自动播种。

7. **`get_auth_status` 一族 700 行(6524–7265)只扫未读**
   —— 锚点 `hermes_cli/auth.py:7033` 的 `get_auth_status`;现象:它是
   `hermes auth status` / doctor / dashboard 三处共用的数据源,内部按 provider 分派到
   6 个 `get_*_auth_status`,还有 `_auth_file_cache_key`(`:6613`)这样的缓存失效机制
   (`invalidate_nous_auth_status_cache` 在 `:6627`),本轮未读缓存的正确性论证。

8. **`model_setup_flows.py` 未纳入本段范围**
   —— 锚点 `hermes_cli/model_setup_flows.py:404`;现象:`hermes login` 死后,
   它才是 OAuth 登录的**真实**用户入口(5 个 `_update_config_for_provider` 调用点),
   但它不在本轮分配的两个文件里,其 flow 的完整走法(尤其失败回滚)未取证。
