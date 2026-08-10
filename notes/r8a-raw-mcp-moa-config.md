# r8a-raw-mcp-moa-config · mcp_config.py + moa_config.py

> 底稿(求全求证)。基线 `863e313`。凡对 hermes-agent 行为的断言,紧跟 `路径:行号 @ 863e313`
> 与代码原文块。本篇覆盖 `hermes_cli/mcp_config.py`(1135 行)与 `hermes_cli/moa_config.py`(509 行)。
> 术语:**MCP** = Model Context Protocol,让 agent 接入外部工具服务器的协议;**MoA** = Mixture of
> Agents,多个「顾问模型」先给建议、再由一个「聚合模型」出最终答案的协同模式。

---

## 0. 一句话定位:两个文件都是「配置面」,但形态完全相反

| | `mcp_config.py` | `moa_config.py` |
|---|---|---|
| 形态 | 命令实现 + 副作用(读写 config.yaml / .env / 网络探针 / OAuth 浏览器流) | **纯函数模块,零 I/O** |
| 与 `hermes_cli/config.py` 的关系 | 直接 `load_config()` / `save_config()` / `get_env_value()` / `save_env_value()` | **完全不接触**;调用方把 `config["moa"]` 这一小块字典传进来 |
| 校验时机 | 保存前 + 探针前(`validate_mcp_server_entry`) | 读时宽容(`normalize_moa_config`)/ 写时严格(`validate_moa_payload`)双闸门 |
| 配置根键 | `mcp_servers` | `moa` |
| 是否在 `DEFAULT_CONFIG` 里 | **否**(全仓 `config_defaults.py` 无 `mcp_servers` 键) | 是(`hermes_cli/config_defaults.py:1754`) |

这个对照本身就是设计要点:MCP 的服务器条目是「用户自带的、每条都可能是任意本地命令」的外部资源,
所以配置面必须带**安全校验 + 探针验证 + 密钥分离**;MoA 的预设是纯参数,所以配置面被压成一个可以
在任何进程、任何线程反复调用的纯 normalize 函数。

---

# 第一部分 · `hermes_cli/mcp_config.py`

## 1. 它解决什么问题

`hermes mcp add/remove/list/test/configure/login/reauth` 这一组子命令的实现。模块自己的 docstring
声明它把配置放在 `~/.hermes/config.yaml` 的 `mcp_servers` 键下。`hermes_cli/mcp_config.py:8 @ 863e313`

```python
configuration in ~/.hermes/config.yaml under the ``mcp_servers`` key.
```

它**不自己开文件**,全部走 `hermes_cli/config.py` 的公共 API。`hermes_cli/mcp_config.py:18 @ 863e313`

```python
from hermes_cli.config import (
    cfg_get,
    load_config,
    save_config,
    get_env_value,
    save_env_value,
    get_hermes_home,  # noqa: F401 — used by test mocks
)
```

`get_hermes_home` 那个 `noqa` 注释是真的:测试确实 monkeypatch 的是 `hermes_cli.mcp_config.get_hermes_home`
这个再导出名,而不是 config 模块里的原名。`tests/hermes_cli/test_mcp_config.py:157 @ 863e313`

```python
            "hermes_cli.mcp_config.get_hermes_home", lambda: tmp_path
```

### 1.1 CLI 参数面(哪些 flag 会变成配置键)

参数定义不在本文件,在 `hermes_cli/subcommands/mcp.py`。`hermes_cli/subcommands/mcp.py:41 @ 863e313`

```python
    mcp_add_p = mcp_sub.add_parser(
        "add", help="Add an MCP server (discovery-first install)"
    )
    mcp_add_p.add_argument("name", help="Server name (used as config key)")
    mcp_add_p.add_argument("--url", help="HTTP/SSE endpoint URL")
```

`--command` 被显式改名成 `dest="mcp_command"`,因为顶层 subparser 用 `args.command` 做路由,
不改名的话 `hermes mcp add --command npx` 会把顶层的 `command` 置空、掉进交互聊天。
`hermes_cli/subcommands/mcp.py:52 @ 863e313`

```python
    mcp_add_p.add_argument(
        "--command", dest="mcp_command", help="Stdio command (e.g. npx)"
    )
```

`--args` 用 `argparse.REMAINDER`,所以它必须是最后一个选项。`hermes_cli/subcommands/mcp.py:55 @ 863e313`

```python
    mcp_add_p.add_argument(
        "--args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Arguments for stdio command; must be the last option",
    )
```

其余 flag:`--auth`(只允许 `oauth` / `header`)、`--preset`、`--connect-timeout`(float)、`--env`(可多值)。
`hermes_cli/subcommands/mcp.py:61 @ 863e313`

```python
    mcp_add_p.add_argument("--auth", choices=["oauth", "header"], help="Auth method")
    mcp_add_p.add_argument("--preset", help="Known MCP preset name")
    mcp_add_p.add_argument(
        "--connect-timeout",
        type=float,
        help="Timeout in seconds for initial connection and tool discovery",
    )
```

---

## 2. 读侧:`_get_mcp_servers`

**解决什么问题**:所有子命令都要拿「当前配置了哪些 MCP server」,并且要能容忍 `mcp_servers` 缺失、
是 `None`、或被手写成非字典。`hermes_cli/mcp_config.py:78 @ 863e313`

```python
def _get_mcp_servers(config: Optional[dict] = None) -> Dict[str, dict]:
    """Return the ``mcp_servers`` dict from config, or empty dict."""
    if config is None:
        config = load_config()
    servers = config.get("mcp_servers")
    if not servers or not isinstance(servers, dict):
        return {}
    return servers
```

**取舍 / 陷阱三条**:

1. 它返回的是 `load_config()` 结果里的**同一个子字典对象**(没有 copy)。`load_config()` 每次都
   deepcopy 一份缓存,所以这里改它不会污染进程缓存;`hermes_cli/config.py:3115 @ 863e313`

   ```python
   def load_config() -> Dict[str, Any]:
   ```

2. 它**不做 `${ENV}` 插值**,也**不做安全过滤**。运行时的读侧 `tools/mcp_tool.py::_load_mcp_config`
   两件都做。`tools/mcp_tool.py:4667 @ 863e313`

   ```python
        safe_servers: Dict[str, dict] = {}
        for name, cfg in _filter_suspicious_mcp_servers(servers).items():
            interpolated = _interpolate_env_vars(cfg)
   ```

3. 它**不认 `HERMES_SAFE_MODE`**。运行时读侧在 safe mode 下直接返回空,CLI 读侧没有这一步 ——
   所以 safe mode 下 `hermes mcp list` 仍然会把服务器列出来。`tools/mcp_tool.py:4655 @ 863e313`

   ```python
        if _env_enabled("HERMES_SAFE_MODE"):
            return {}
   ```

   `env_var_enabled` 的语义是「环境变量被设成 truthy 值」。`utils.py:33 @ 863e313`

   ```python
   def env_var_enabled(name: str, default: str = "") -> bool:
       """Return True when an environment variable is set to a truthy value."""
       return is_truthy_value(os.getenv(name, default), default=False)
   ```

4. 它也**不按 `enabled` 过滤**,所以 `hermes mcp test <disabled-server>` 照样连。

---

## 3. 写侧的三条路径(为什么要三条)

### 3.1 `_save_mcp_server` —— 单键 upsert,带安全否决

**解决什么问题**:CLI 与 Dashboard 加/改一台服务器。它先跑安全校验,有问题就**不保存**并返回 False。
`hermes_cli/mcp_config.py:88 @ 863e313`

```python
def _save_mcp_server(name: str, server_config: dict) -> bool:
    """Add or update a server entry in config.yaml.

    Returns False when a high-signal exfiltration-shaped stdio command is
    rejected. MCP stdio servers are user-chosen local commands, so this blocks
    shell+egress payloads rather than whitelisting command families.
    """
    issues = validate_mcp_server_entry(name, server_config)
```

落盘就是 `load_config` → 改 → `save_config`。`hermes_cli/mcp_config.py:101 @ 863e313`

```python
    config = load_config()
    config.setdefault("mcp_servers", {})[name] = server_config
    save_config(config)
    return True
```

### 3.2 `_remove_mcp_server` —— 删到空就把整个键删掉

`hermes_cli/mcp_config.py:107 @ 863e313`

```python
def _remove_mcp_server(name: str) -> bool:
    """Remove a server from config.yaml.  Returns True if it existed."""
    config = load_config()
    servers = config.get("mcp_servers", {})
    if name not in servers:
        return False
    del servers[name]
    if not servers:
        config.pop("mcp_servers", None)
    save_config(config)
    return True
```

注意 `del servers[name]` 改的是 `config` 里那个子字典(`config.get` 拿到的是引用),所以后面
`save_config(config)` 能看到删除。但若 `mcp_servers` 原本缺失,`config.get("mcp_servers", {})` 返回的是
一个**临时空字典**,此时直接 `return False`,不会误写。

### 3.3 `_replace_mcp_servers` —— 整表替换,专门为了「删除能落盘」

**解决什么问题**:GUI 的 mcp.json 编辑器要支持「删服务器 / 去掉 `enabled: false` / 删嵌套字段」。
走 `/api/config` 的深合并只能加/覆盖键,**永远删不掉键**,于是「编辑看起来成功了但旧条目还在」。
`hermes_cli/mcp_config.py:120 @ 863e313`

```python
def _replace_mcp_servers(servers: Dict[str, dict]) -> Tuple[bool, List[str]]:
    """Replace the WHOLE ``mcp_servers`` map in config.yaml.

    Unlike ``_save_mcp_server`` (per-key upsert), this sets the entire map so
    the GUI's mcp.json editor can delete servers, drop an ``enabled: false``
    flag (re-enable), or remove nested fields and have those *removals* land on
    disk.  A plain ``/api/config`` deep-merge can only add/override keys, never
    delete them — which is why edits appeared to succeed but the old entry
    survived (see MCP tab persistence bug).
```

**全有或全无**:任何一条 entry 有问题,整次保存被拒,避免「一次坏粘贴被部分应用」。
`hermes_cli/mcp_config.py:141 @ 863e313`

```python
    if issues:
        return False, issues
```

空 map 直接删键。`hermes_cli/mcp_config.py:144 @ 863e313`

```python
    config = load_config()
    if servers:
        config["mcp_servers"] = dict(servers)
    else:
        config.pop("mcp_servers", None)
    save_config(config)
    return True, []
```

调用方是 dashboard 路由。`hermes_cli/web_routers/mcp.py:117 @ 863e313`

```python
    from hermes_cli.mcp_config import _replace_mcp_servers
```

---

## 4. 安全校验:`hermes_cli/mcp_security.py`(保存与 spawn 双闸门)

**解决什么问题**:MCP stdio transport 天生允许任意本地命令。不能白名单,只能拦「高信号的滥用形状」。
该模块 docstring 说明它拦三类:IOC 黑名单、shell + 网络外传、shell + 写系统持久化面。
`hermes_cli/mcp_security.py:121 @ 863e313`

```python
def validate_mcp_server_entry(name: str, entry: dict[str, Any]) -> list[str]:
```

IOC 是硬编码的 2026-06 `hermes-0day` 攻击 artifact,任何位置命中即整条拒绝。
`hermes_cli/mcp_security.py:80 @ 863e313`

```python
_IOC_SUBSTRINGS = (
    # Attacker SSH public key (the "hermes-0day" persistence key).
    "AAAAC3NzaC1lZDI1NTE5AAAAICBoh1oDC4DnsO1m5mJ4yfEKrQebaFh",
    "hermes-0day",
```

只有当 `command` 的 basename 是 shell 解释器时,才继续查脚本内容;否则直接放行。
`hermes_cli/mcp_security.py:149 @ 863e313`

```python
    command = entry.get("command")
    basename = _command_basename(command)
    if basename not in _SHELL_INTERPRETERS:
        return issues
```

同一个函数也在 spawn 侧被调用,所以手写/预植入的 config.yaml 在执行前也会被拦。
`tools/mcp_tool.py:4613 @ 863e313`

```python
def _filter_suspicious_mcp_servers(servers: Dict[str, dict]) -> Dict[str, dict]:
    """Drop exfiltration-shaped MCP configs before any stdio spawn path."""
```

**取舍**:这是形状检测不是沙箱。`command: python`+任意脚本、`command: npx`+任意包都完全放行;
它只堵住「bash -c 里带 curl / 写 authorized_keys」这两种在野观测到的形状。误报率换检出率,取的是低误报。

---

## 5. 密钥不进 config.yaml:四件套

**解决什么问题**:HTTP MCP server 的 Bearer token 必须能持久化,但 config.yaml 会被用户贴进 issue、
被 GUI 展示、被 profile 同步。方案是:**config.yaml 只存插值模板,真值进 `.env`**。

server 名 → 环境变量名。`hermes_cli/mcp_config.py:153 @ 863e313`

```python
def _env_key_for_server(name: str) -> str:
    """Convert server name to an env-var key like ``MCP_MYSERVER_API_KEY``."""
    suffix = re.sub(r"[^A-Za-z0-9_]", "_", name.upper()).strip("_")
    return f"MCP_{suffix}_API_KEY"
```

存进 config.yaml 的 header 模板。`hermes_cli/mcp_config.py:181 @ 863e313`

```python
    env_key = _env_key_for_server(name)
    return {"Authorization": f"Bearer ${{{env_key}}}"}
```

写 `.env` 并返回安全 header —— 真值只走 `save_env_value`,一次性,不回传。
`hermes_cli/mcp_config.py:192 @ 863e313`

```python
    normalized = _strip_bearer_prefix(token)
    if not normalized or normalized.lower() == "bearer":
        raise ValueError("Bearer token is required")
    save_env_value(_env_key_for_server(name), normalized)
    return _bearer_auth_headers(name)
```

`_strip_bearer_prefix` 是为 #37792 加的:模板本身已经带 `Bearer `,用户又粘了带前缀的 token,
服务器收到 `Bearer Bearer <jwt>` → 401。`hermes_cli/mcp_config.py:169 @ 863e313`

```python
    if stripped[:7].lower() == "bearer ":
        return stripped[7:].strip()
    return stripped
```

行为规格(测试):secret 与 header 分开落盘。`tests/hermes_cli/test_mcp_config.py:537 @ 863e313`

```python
        headers = _save_bearer_auth_token("My Server", "Bearer secret-value")

        assert headers == {
            "Authorization": "Bearer ${MCP_MY_SERVER_API_KEY}",
        }
        assert get_env_value("MCP_MY_SERVER_API_KEY") == "secret-value"
```

`save_env_value` 侧还有一层:managed scope(管理员托管)拒绝、变量名正则校验、denylist、去换行、
非 ASCII 检查。`hermes_cli/config.py:3883 @ 863e313`

```python
    if not _ENV_VAR_NAME_RE.match(key):
        raise ValueError(f"Invalid environment variable name: {key!r}")
    _reject_denylisted_env_var(key)
```

读侧 `get_env_value` 是 **scope-aware** 的:先走 `agent.secret_scope.get_secret`(多路复用 gateway 下按
profile 隔离),再回落 `.env`。`hermes_cli/config.py:4109 @ 863e313`

```python
def get_env_value(key: str) -> Optional[str]:
    """Get a value from ``os.environ`` or ``~/.hermes/.env``, scope-aware.
```

**取舍 / 缺陷**:`_env_key_for_server` 是有损映射 —— `my-server`、`my.server`、`my server` 全部塌到
`MCP_MY_SERVER_API_KEY`。测试自己就把这点固化了。`tests/hermes_cli/test_mcp_config.py:568 @ 863e313`

```python
        assert _env_key_for_server("ink") == "MCP_INK_API_KEY"
        assert _env_key_for_server("my-server") == "MCP_MY_SERVER_API_KEY"
        assert _env_key_for_server("my.server") == "MCP_MY_SERVER_API_KEY"
```

两台名字只差分隔符的服务器会**共用一把 key**,后配的覆盖先配的,而 CLI 只提示 "already configured"。

---

## 6. `--env KEY=VALUE` 的解析

`hermes_cli/mcp_config.py:199 @ 863e313`

```python
def _parse_env_assignments(raw_env: Optional[List[str]]) -> Dict[str, str]:
    """Parse ``KEY=VALUE`` strings from CLI args into an env dict."""
```

变量名必须匹配本模块自己的正则(与 config.py 的同名常量是两份)。
`hermes_cli/mcp_config.py:33 @ 863e313`

```python
_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
```

`hermes_cli/mcp_config.py:212 @ 863e313`

```python
        if not _ENV_VAR_NAME_RE.match(key):
            raise ValueError(f"Invalid --env variable name '{key}'")
```

`--env` 只对 stdio 有意义,给 HTTP server 用会直接报错退出。`hermes_cli/mcp_config.py:446 @ 863e313`

```python
    if url and explicit_env:
        _error("--env is only supported for stdio MCP servers (--command or stdio presets)")
        return
```

---

## 7. 预设 `--preset`

预设表目前**只有一条**。`hermes_cli/mcp_config.py:36 @ 863e313`

```python
_MCP_PRESETS: Dict[str, Dict[str, Any]] = {
    "codex": {
        "command": "codex",
        "args": ["mcp-server"],
    },
}
```

语义是「只在没给 transport 时才填」——给了 `--url` 或 `--command`,预设**整个跳过**(不是逐字段兜底)。
`hermes_cli/mcp_config.py:235 @ 863e313`

```python
    if url or command:
        return url, command, cmd_args, False
```

未知预设名抛 ValueError,被 `cmd_mcp_add` 捕获成一行 `_error`。`hermes_cli/mcp_config.py:231 @ 863e313`

```python
    preset = _MCP_PRESETS.get(preset_name)
    if not preset:
        raise ValueError(f"Unknown MCP preset: {preset_name}")
```

预设支持 `url` 字段,但表里没有任何带 url 的条目 —— 这一支目前是**未被触达的路径**。
`hermes_cli/mcp_config.py:238 @ 863e313`

```python
    url = preset.get("url")
    command = preset.get("command")
    cmd_args = list(preset.get("args") or [])
```

---

## 8. 探针 `_probe_single_server`(本文件最重的一段)

**解决什么问题**:`add` / `test` / `configure` / `login` 都需要「临时连一次、列工具、断开」。

### 8.1 先安全校验,再连

`hermes_cli/mcp_config.py:290 @ 863e313`

```python
    issues = validate_mcp_server_entry(name, config)
    if issues:
        raise ValueError("; ".join(issues))
```

### 8.2 连之前先解 `${ENV}`(#37792)

**这是本段最重要的一处事故修复**:CLI 写的 header 是模板 `Authorization: Bearer ${MCP_X_API_KEY}`,
早期探针**原样发出去**,于是 n8n 之类需要鉴权的服务器返回 401 —— 而运行时加载工具是好的,因为运行时会插值。
`hermes_cli/mcp_config.py:254 @ 863e313`

```python
def _resolve_mcp_server_config(config: dict) -> dict:
    """Resolve ``${ENV}`` placeholders in a server config before connecting.

    Mirrors ``_load_mcp_config()`` in ``tools/mcp_tool.py``: load
    ``~/.hermes/.env`` into ``os.environ`` and recursively interpolate any
    ``${VAR}`` placeholders. The CLI builds header templates like
    ``Authorization: Bearer ${MCP_X_API_KEY}`` but the probe path never
    resolved them, so the discovery probe sent the literal placeholder and
    auth-requiring servers (e.g. n8n) returned 401 — while runtime tool
    loading worked because it interpolates. (#37792)
    """
```

关键细节:**只有在没有活跃 secret scope 时才把 `.env` 灌进 `os.environ`**。有 scope 时(多路复用 gateway
的一次 turn)不能污染进程级环境,否则会把别的 profile 的密钥泄漏出去。
`hermes_cli/mcp_config.py:269 @ 863e313`

```python
    if current_secret_scope() is None:
        try:
            from hermes_cli.env_loader import load_hermes_dotenv
            load_hermes_dotenv()
        except Exception:  # pragma: no cover — defensive
            pass
    return _interpolate_env_vars(config)
```

插值本体在 mcp_tool,支持 `${VAR}` 与 Cursor 风格 `${env:VAR}`,未设置的变量**保留字面占位符**。
`tools/mcp_tool.py:4550 @ 863e313`

```python
    if isinstance(value, str):
        def _replace(m):
            name = _env_ref_name(m.group(1))
            return _get_secret(name, m.group(0)) or m.group(0)
        return _ENV_VAR_PATTERN.sub(_replace, value)
```

行为规格:scope 存在时,解析走 scope 值且不改 `os.environ`。`tests/hermes_cli/test_mcp_config.py:393 @ 863e313`

```python
        monkeypatch.setenv("MCP_SHARED_API_KEY", "default-secret")
        token = set_secret_scope({"MCP_SHARED_API_KEY": "profile-secret"})
```

### 8.3 超时:探针的默认值与运行时/文档不一致

`hermes_cli/mcp_config.py:302 @ 863e313`

```python
    config = _resolve_mcp_server_config(config)
    if connect_timeout is None:
        raw_timeout = config.get("connect_timeout", 30)
        try:
            connect_timeout = max(1.0, float(raw_timeout))
        except (TypeError, ValueError):
            connect_timeout = 30.0
```

运行时的默认是 60。`tools/mcp_tool.py:334 @ 863e313`

```python
_DEFAULT_CONNECT_TIMEOUT = 60    # seconds for initial connection per server
```

外层还有 +10 秒的兜底 timeout(内层 `asyncio.wait_for` 管连接,外层管整个协程)。
`hermes_cli/mcp_config.py:372 @ 863e313`

```python
        _run_on_mcp_loop(_probe(), timeout=connect_timeout + 10)
```

测试把这两层都钉住了。`tests/hermes_cli/test_mcp_config.py:336 @ 863e313`

```python
        assert mcp_config._probe_single_server(
            "supabase", {"connect_timeout": 300}
        ) == []
        assert captured["inner_timeout"] == 300.0
        assert captured["outer_timeout"] == 310.0
```

### 8.4 能力探测门控(prompts / resources)

**事故经过**:"Test server" 探针以前无条件发 `prompts/list` 和 `resources/list`。Unreal 的 MCP server
回 `Call to unknown method 'prompts/list'`,于是日志里出现硬错误;而文档推荐的 `tools.prompts: false`
根本压不住它,因为探针从不读配置。修法是两道门:先读用户配置,再看服务器是否 advertise。
`hermes_cli/mcp_config.py:334 @ 863e313`

```python
                tools_filter = config.get("tools") or {}
                prompts_enabled = _parse_boolish(
                    tools_filter.get("prompts"), default=True
                )
                resources_enabled = _parse_boolish(
                    tools_filter.get("resources"), default=True
                )
```

`hermes_cli/mcp_config.py:347 @ 863e313`

```python
                def _advertises(cap_attr: str) -> bool:
                    # When no capability info was captured (legacy fixtures /
                    # older servers) preserve the old always-try behaviour.
                    if advertised_caps is None:
                        return True
                    return getattr(advertised_caps, cap_attr, None) is not None
```

`hermes_cli/mcp_config.py:356 @ 863e313`

```python
                if prompts_enabled and _advertises("prompts"):
```

`_parse_boolish` 的取值集合(注意它认 `on`/`off`)。`tools/mcp_tool.py:5656 @ 863e313`

```python
def _parse_boolish(value: Any, default: bool = True) -> bool:
    """Parse a bool-like config value with safe fallback."""
```

`details` 是 out-param,专门为了不破坏已有 CLI 调用方的返回形状。`hermes_cli/mcp_config.py:278 @ 863e313`

```python
def _probe_single_server(
    name: str, config: dict, connect_timeout: Optional[float] = None, *, details: Optional[dict] = None
) -> List[Tuple[str, str]]:
```

用它的是 dashboard 的 test 路由。`hermes_cli/web_routers/mcp.py:169 @ 863e313`

```python
            tools = _probe_single_server(name, servers[name], details=details)
```

### 8.5 异常解包

MCP SDK 用 anyio task group,错误被包成 `ExceptionGroup`,报出来是 "unhandled errors in a TaskGroup"。
`hermes_cli/mcp_config.py:405 @ 863e313`

```python
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
```

`hermes_cli/mcp_config.py:373 @ 863e313`

```python
    except BaseException as exc:
        raise _unwrap_exception_group(exc) from None
```

**取舍**:只取 `exceptions[0]`。多个并发子任务同时失败时,后面的错误被丢弃。

---

## 9. `hermes mcp add` 的完整走法

顺序:解析 env → 应用 preset → 校验 transport → 查重 → 组 config → 安全校验 → 认证 → **探针** →
工具选择 → 保存。

`--args` 后如果第一项是 `--`(REMAINDER 常见形状),会被吃掉。`hermes_cli/mcp_config.py:424 @ 863e313`

```python
    if cmd_args and cmd_args[0] == "--":
        cmd_args = cmd_args[1:]
```

transport 缺失时给三行示例。`hermes_cli/mcp_config.py:451 @ 863e313`

```python
    if not url and not command:
        _error("Must specify --url <endpoint>, --command <cmd>, or --preset <name>")
```

组装出的 server entry 形状(这就是写进 config.yaml 的 schema)。`hermes_cli/mcp_config.py:467 @ 863e313`

```python
    if url:
        server_config["url"] = url
    else:
        server_config["command"] = command
        if cmd_args:
            server_config["args"] = cmd_args
        if explicit_env:
            server_config["env"] = explicit_env
    if raw_connect_timeout is not None:
        server_config["connect_timeout"] = raw_connect_timeout
```

OAuth 分支:只对 HTTP + `--auth oauth`。`hermes_cli/mcp_config.py:487 @ 863e313`

```python
    if url and auth_type == "oauth":
```

OAuth provider 构建失败时不写 `auth: oauth`,并询问是否无认证继续。`hermes_cli/mcp_config.py:493 @ 863e313`

```python
            oauth_auth = get_manager().get_or_build_provider(
                name, url, server_config.get("oauth")
            )
```

Header 认证分支(默认分支:`--auth header` 或没给 `--auth`)。`hermes_cli/mcp_config.py:520 @ 863e313`

```python
            if auth_type == "header" or not auth_type:
                env_key = _env_key_for_server(name)
                existing_key = get_env_value(env_key)
                if existing_key:
                    _success(f"{env_key}: already configured")
                else:
                    api_key = _prompt("API key / Bearer token", password=True)
                    if api_key:
                        server_config["headers"] = _save_bearer_auth_token(
                            name, api_key
                        )
                        _success(f"Saved to {display_hermes_home()}/.env as {env_key}")
```

连不上时可以「先存成 disabled」。`hermes_cli/mcp_config.py:546 @ 863e313`

```python
        if _confirm("Save config anyway (you can test later)?", default=False):
            server_config["enabled"] = False
            if _save_mcp_server(name, server_config):
                _success(f"Saved '{name}' to config (disabled)")
```

工具选择:选全部就**不写 `tools` 键**(默认即全开),选部分才写 `tools.include`。
`hermes_cli/mcp_config.py:602 @ 863e313`

```python
        server_config.setdefault("tools", {})["include"] = chosen_names
```

`hermes_cli/mcp_config.py:613 @ 863e313`

```python
    server_config["enabled"] = True
    if _save_mcp_server(name, server_config):
```

---

## 10. `list` / `test` / `configure`

### 10.1 `cmd_mcp_list`

`enabled` 的字符串解释在这里是**第三套语义**(只认 `true/1/yes`,不认 `on`)。
`hermes_cli/mcp_config.py:711 @ 863e313`

```python
        enabled = cfg.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() in {"true", "1", "yes"}
        status = color("✓ enabled", Colors.GREEN) if enabled else color("✗ disabled", Colors.DIM)
```

运行时用的是 `_parse_boolish`(认 `on`)。`tools/mcp_tool.py:6559 @ 863e313`

```python
        enabled = _parse_boolish(cfg.get("enabled", True), default=True)
```

### 10.2 `cmd_mcp_test` 的 header 掩码

`hermes_cli/mcp_config.py:753 @ 863e313`

```python
            if isinstance(v, str) and ("key" in k.lower() or "auth" in k.lower()):
                # Mask the value (accepts ${VAR} and Cursor-style ${env:VAR})
                resolved = _ENV_VAR_PATTERN.sub(lambda m: os.getenv(_env_ref_name(m.group(1)), ""), v)
```

注意这里用的是**裸 `os.getenv`**,不是 scope-aware 的 `_interpolate_env_vars` —— 与同文件
`_resolve_mcp_server_config` 的取值口径不一致(见「可疑缺陷」)。

### 10.3 `cmd_mcp_configure`

先硬性要求 TTY(curses 清单)。`hermes_cli/mcp_config.py:966 @ 863e313`

```python
    import sys as _sys
    if not _sys.stdin.isatty():
        print("Error: 'hermes mcp configure' requires an interactive terminal.", file=_sys.stderr)
        _sys.exit(1)
```

预选逻辑复用**运行时同一套匹配语义**(精确名 + fnmatch glob),并且 import 失败时降级为纯精确匹配。
`hermes_cli/mcp_config.py:1009 @ 863e313`

```python
    try:
        from tools.mcp_tool import matches_name_filter
    except ImportError:  # pragma: no cover — defensive fallback
        def matches_name_filter(tool_name, patterns):
            return tool_name in patterns
```

`tools/mcp_tool.py:5637 @ 863e313`

```python
def matches_name_filter(tool_name: str, patterns: set[str]) -> bool:
```

无变化就不写盘。`hermes_cli/mcp_config.py:1046 @ 863e313`

```python
    if chosen == pre_selected:
        _info("No changes made.")
        return
```

写盘时是「全选 → 删 `tools` 键;部分 → 写 `include` 并删 `exclude`」。
`hermes_cli/mcp_config.py:1051 @ 863e313`

```python
    config = load_config()
    server_entry = cfg_get(config, "mcp_servers", name, default={})

    if len(chosen) == total:
        # All selected → remove include/exclude (register all)
        server_entry.pop("tools", None)
    else:
        chosen_names = [tool_names[i] for i in sorted(chosen)]
        server_entry.setdefault("tools", {})
        server_entry["tools"]["include"] = chosen_names
        server_entry["tools"].pop("exclude", None)

    config.setdefault("mcp_servers", {})[name] = server_entry
    save_config(config)
```

`cfg_get` 是全仓通用的安全多级取值。`hermes_cli/config.py:2886 @ 863e313`

```python
def cfg_get(cfg: Optional[Dict[str, Any]], *keys: str, default: Any = None) -> Any:
```

---

## 11. OAuth:`login` / `reauth`

`_reauth_oauth_server` 是 `login` 与 `reauth` 的共用体。`hermes_cli/mcp_config.py:787 @ 863e313`

```python
def _reauth_oauth_server(name: str, server_config: dict) -> bool:
    """Force a fresh OAuth flow for one server. Returns True on success.
```

先拒绝非 OAuth 服务器。`hermes_cli/mcp_config.py:799 @ 863e313`

```python
    if server_config.get("auth") != "oauth":
```

超时地板 315 秒 = OAuth 回调窗口 300 秒 + 余量,和 GUI 走同一个数。
`hermes_cli/mcp_config.py:829 @ 863e313`

```python
        _login_connect_timeout = server_config.get("connect_timeout")
        try:
            _login_connect_timeout = float(_login_connect_timeout)
        except (TypeError, ValueError):
            _login_connect_timeout = 0.0
        _login_connect_timeout = max(_login_connect_timeout, 315.0)
```

300 秒确实是 mcp_oauth 的回调轮询窗口。`tools/mcp_oauth.py:916 @ 863e313`

```python
        timeout = 300.0
```

GUI 侧同样是 315。`hermes_cli/web_server.py:12206 @ 863e313`

```python
                        connect_timeout=max(float(cfg.get("connect_timeout", 0) or 0), 315),
```

`force_interactive_oauth()` 让「非 TTY 但用户在场」(桌面端/被 agent 拉起的终端)也能开浏览器。
`tools/mcp_oauth.py:326 @ 863e313`

```python
def force_interactive_oauth():
```

`hermes_cli/mcp_config.py:835 @ 863e313`

```python
        with force_interactive_oauth():
            tools = _probe_single_server(
                name, server_config, connect_timeout=_login_connect_timeout
            )
```

**「探针成功 ≠ 认证成功」这条教训**:Google Drive 官方 server 不支持 RFC 7591 动态客户端注册,注册 400,
但它允许**无鉴权**的 `initialize` + `tools/list`,于是探针能列出工具、CLI 报「Authenticated — N tools」,
而后续每一次真实工具调用都挂到超时。修法是查磁盘上到底有没有落 token。
`hermes_cli/mcp_config.py:847 @ 863e313`

```python
        if not _oauth_tokens_present(name):
```

`hermes_cli/mcp_config.py:381 @ 863e313`

```python
def _oauth_tokens_present(name: str) -> bool:
    """Return True if an OAuth token file exists on disk for ``name``.
```

注意它在异常时**返回 True(放行)**,宁可漏报也不误判成功失败。`hermes_cli/mcp_config.py:391 @ 863e313`

```python
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("Could not check OAuth tokens for '%s': %s", name, exc)
        # Be permissive on unexpected errors: don't block a real success.
        return True
```

失败时打印的自建 OAuth client 配置模板 —— 这里出现了 `oauth.client_id` / `oauth.client_secret` 两个键。
`hermes_cli/mcp_config.py:863 @ 863e313`

```python
            print(color("        oauth:", Colors.DIM))
            print(color("          client_id: \"<your-oauth-client-id>\"", Colors.DIM))
            print(color("          client_secret: \"<your-oauth-client-secret>\"", Colors.DIM))
```

`reauth --all` **串行**执行,因为人一次只能完成一个浏览器流程。`hermes_cli/mcp_config.py:930 @ 863e313`

```python
        oauth_servers = [
            (n, c) for n, c in servers.items()
            if c.get("auth") == "oauth" and c.get("url")
        ]
```

`hermes_cli/mcp_config.py:940 @ 863e313`

```python
        for n, c in oauth_servers:
            print()
            print(color(f"  ── {n} ──", Colors.CYAN + Colors.BOLD))
            if _reauth_oauth_server(n, c):
                succeeded += 1
```

`remove` 时顺带清 OAuth token,走 manager 以便驱逐进程内缓存。`hermes_cli/mcp_config.py:645 @ 863e313`

```python
        from tools.mcp_oauth_manager import get_manager
        get_manager().remove(name)
        _success("Cleaned up OAuth tokens")
    except Exception:
        pass
```

---

## 12. 分发器

`serve` / `picker` / `catalog` / `install` 是**懒加载**的旁路,其余走 handler 表。
`hermes_cli/mcp_config.py:1077 @ 863e313`

```python
    if action == "serve":
        from mcp_serve import run_mcp_server
        run_mcp_server(verbose=getattr(args, "verbose", False))
        return
```

`hermes_cli/mcp_config.py:1100 @ 863e313`

```python
    handlers = {
        "add": cmd_mcp_add,
        "remove": cmd_mcp_remove,
        "rm": cmd_mcp_remove,
        "list": cmd_mcp_list,
        "ls": cmd_mcp_list,
        "test": cmd_mcp_test,
        "configure": cmd_mcp_configure,
        "config": cmd_mcp_configure,
        "login": cmd_mcp_login,
        "reauth": cmd_mcp_reauth,
    }
```

无子命令时**先跑 picker 再打帮助**(不是打帮助)。`hermes_cli/mcp_config.py:1117 @ 863e313`

```python
        # No subcommand — drop the user into the catalog picker. This is the
        # "try enabling and it flows you into setup" UX matching `hermes plugin`.
        from hermes_cli.mcp_picker import run_picker
        run_picker()
```

---

# 第二部分 · `hermes_cli/moa_config.py`

## 13. 定位:纯函数,零 I/O,零环境变量

全文件 509 行,**没有任何 `open` / `load_config` / `os.environ` / `os.getenv`**。它只做三件事:
把任意形状的 `moa` 配置块 normalize 成一个封闭 schema、在写边界上做严格校验、编解码一个 base64 marker。
所有调用方自己负责 I/O,统一是 `load_config().get("moa")`。例:`agent/moa_loop.py:2371 @ 863e313`

```python
        moa_cfg = normalize_moa_config(load_config().get("moa") or {})
```

`hermes_cli/model_switch.py:1421 @ 863e313`

```python
            _moa_cfg = normalize_moa_config(load_config().get("moa") or {})
```

**为什么这么设计**:MoA 的 preset 在 agent 循环里每个 tool iteration 都要解析一次
(`resolve_moa_preset` 每次都整块重 normalize + 重校验),纯函数才能被上层随便加缓存。
`agent/moa_loop.py:1861 @ 863e313`

```python
        # Resolve the preset once per (config st_mtime_ns, preset_name).
        # resolve_moa_preset re-normalizes + re-validates the whole moa
        # config block on every call, and create() runs once per tool-loop
        # iteration — a serial cold-start cost before the parallel fan-out
        # can begin (#66793). Keyed on the config FILE's mtime_ns (not a
        # config-object attribute, which load_config()'s dicts don't carry),
        # so a config edit invalidates on the next call.
```

## 14. 默认值(模块级常量)

`hermes_cli/moa_config.py:11 @ 863e313`

```python
MOA_MARKER_PREFIX = "__HERMES_MOA_TURN_V1__"
DEFAULT_MOA_PRESET_NAME = "default"

DEFAULT_MOA_REFERENCE_MODELS: list[dict[str, str]] = [
    {"provider": "openai-codex", "model": "gpt-5.5"},
    {"provider": "openrouter", "model": "deepseek/deepseek-v4-pro"},
]

DEFAULT_MOA_AGGREGATOR: dict[str, str] = {
    "provider": "openrouter",
    "model": "anthropic/claude-opus-4.8",
}

DEFAULT_MOA_REFERENCE_TIMEOUT: float | None = None
```

`config_defaults.py` 里的 `moa` 默认块与之**部分重合但不等价**(那边没有 temperature / fanout /
reference_timeout / degraded_reference_policy / reference_max_tokens,却多了 `save_traces` / `trace_dir`)。
`hermes_cli/config_defaults.py:1754 @ 863e313`

```python
    "moa": {
        "default_preset": "default",
        "active_preset": "",
```

`hermes_cli/config_defaults.py:1763 @ 863e313`

```python
        "save_traces": False,
        "trace_dir": "",
```

## 15. 「读时宽容 / 写时严格」双闸门 —— 本文件的核心设计

**问题**:同一份 normalize 逻辑,读的时候必须宽容(手写坏 YAML 不能把 agent 弄崩),写的时候宽容
就变成了**静默数据损坏**(客户端发来半填的 slot,整个 preset 被换成硬编码默认值,#64156)。

宽容侧:`hermes_cli/moa_config.py:372 @ 863e313`

```python
def normalize_moa_config(raw: Any) -> dict[str, Any]:
    """Return validated MoA config with named presets.

    Backward compatible with the first PR shape where ``moa`` itself contained
    ``reference_models`` and ``aggregator`` directly.
    """
```

严格侧:`hermes_cli/moa_config.py:247 @ 863e313`

```python
def validate_moa_payload(raw: Any) -> list[str]:
    """Return the problems ``normalize_moa_config`` would silently paper over.

    ``normalize_moa_config`` is deliberately tolerant: at *read* time a
    hand-edited config must degrade to defaults rather than crash the agent.
    That same tolerance at *write* time is a corruption engine — a client that
    sends a half-filled slot gets its whole preset silently replaced with the
    hardcoded defaults (#64156). API write paths call this first and reject
    invalid payloads loudly instead of saving something the user never chose.

    Returns a list of human-readable problems; empty means safe to save.
    """
```

两侧必须**逐字对齐**,靠一对镜像函数保证:`_clean_slot`(丢)与 `_slot_problem`(说出为什么丢)。
`hermes_cli/moa_config.py:225 @ 863e313`

```python
def _slot_problem(slot: Any) -> str | None:
    """Return a human-readable problem for a slot ``_clean_slot`` would drop.

    None means the slot is complete and valid. Mirrors ``_clean_slot`` exactly
    so the write-boundary validator (``validate_moa_payload``) and the
    tolerant runtime normalizer can never disagree about what is acceptable.
    """
```

这条契约有测试兜底。`tests/hermes_cli/test_moa_config.py:145 @ 863e313`

```python
def test_validate_moa_payload_agrees_with_clean_slot():
    """Contract: a payload validate accepts must survive normalize UNCHANGED in
    its slots — validate and _clean_slot can never disagree (else a payload
    could pass validation and still be swapped for defaults)."""
```

调用严格侧的只有 dashboard 写路由。`hermes_cli/web_server.py:6513 @ 863e313`

```python
            problems = validate_moa_payload(raw)
```

**CLI 的写路径(`hermes moa configure`)并不调用它** —— 见「可疑缺陷 D5」。

## 16. slot 清洗 `_clean_slot`

`hermes_cli/moa_config.py:194 @ 863e313`

```python
def _clean_slot(slot: Any, *, include_enabled: bool = False) -> dict[str, Any] | None:
    if not isinstance(slot, dict):
        return None
    provider = str(slot.get("provider") or "").strip()
    model = str(slot.get("model") or "").strip()
    if not provider or not model:
        return None
```

**递归 MoA 的防线在这里**:`provider: moa` 的 slot 直接判无效。运行时也有守卫,但那要跑到 turn 中间才暴露。
`hermes_cli/moa_config.py:206 @ 863e313`

```python
    if provider.lower() == "moa":
        return None
```

清洗后的 slot 是**封闭 schema**:`provider` / `model` + 可选 `reasoning_effort` / `max_tokens`
(+ 引用槽的 `enabled`)。`hermes_cli/moa_config.py:208 @ 863e313`

```python
    clean: dict[str, Any] = {"provider": provider, "model": model}
    effort = _clean_reasoning_effort(slot.get("reasoning_effort"))
    if effort:
        clean["reasoning_effort"] = effort
```

`hermes_cli/moa_config.py:217 @ 863e313`

```python
    slot_mt = _coerce_int_or_none(slot.get("max_tokens"))
    if slot_mt is not None:
        clean["max_tokens"] = slot_mt
    if include_enabled:
        clean["enabled"] = _coerce_bool(slot.get("enabled"), True)
```

**取舍**:任何用户手写的额外 slot 字段(比如 `api_mode`、`base_url`)都会被**静默丢弃**。
这是有意的 —— `api_mode` / `base_url` / `api_key` 由运行时的 `resolve_runtime_provider` 推导,不进配置。
`agent/moa_loop.py:375 @ 863e313`

```python
        if rt.get("api_mode"):
            out["api_mode"] = rt["api_mode"]
```

`reasoning_effort` 的清洗把 `false` 归一成字符串 `"none"`。`hermes_cli/moa_config.py:165 @ 863e313`

```python
def _clean_reasoning_effort(value: Any) -> str | None:
    """Return a canonical per-slot reasoning effort, or None when unset/invalid."""
    from hermes_constants import parse_reasoning_effort

    if value is None or value is True:
        return None
    parsed = parse_reasoning_effort(value)
    if parsed is None:
        return None
    if parsed.get("enabled") is False:
        return "none"
    return parsed.get("effort")
```

底层规则:`false` → `{"enabled": False}`;`None` / `True` → `None`(即「用默认」)。
`hermes_constants.py:959 @ 863e313`

```python
    if effort is False:
        return {"enabled": False}
    if effort is None or effort is True:
        return None
```

## 17. coercion 家族逐个

| 函数 | 无效/缺省时返回 | 特别处 |
|---|---|---|
| `_coerce_float_or_none` | `None` = 不发这个参数 | 不挡 bool |
| `_coerce_reference_timeout` | `None` = 继承 auxiliary 超时 | **显式挡 bool**,且挡非有限值/非正值 |
| `_coerce_degraded_reference_policy` | `"loud"` | 只认 `loud` / `silent` |
| `_coerce_int` | 传入的 default | 先 int 再 float 兜底 |
| `_coerce_int_or_none` | `None` = 不设上限 | 非正数也归 None |
| `_coerce_fanout` | `"user_turn"` | 同时接受 dict 形式 |
| `_coerce_bool` | 传入的 default | 未知字符串回 default |
| `coerce_privacy_filter` | `""` = 关 | bool `True` → `"full"` |

温度:`None` 的语义是「**不把 temperature 放进请求**」,与单模型 agent 一致。
`hermes_cli/moa_config.py:31 @ 863e313`

```python
def _coerce_float_or_none(value: Any) -> float | None:
    """Coerce to a float, or None when unset/blank/invalid.

    Used for optional sampling params (reference_temperature /
    aggregator_temperature) where None means 'don't send the parameter —
    provider default applies', matching how a single-model Hermes agent
    never sends temperature unless explicitly configured.
    """
```

顾问超时:`None` = 继承 `auxiliary.moa_reference.timeout`(默认 900 秒),**不设人为上限**,
因为长思考顾问模型合法地跑超过 5 分钟。`hermes_cli/moa_config.py:47 @ 863e313`

```python
def _coerce_reference_timeout(value: Any) -> float | None:
    """Return a finite positive advisor timeout, or None to inherit.

    ``None`` (the default) means "no per-preset override": the reference
    fan-out inherits the ``auxiliary.moa_reference.timeout`` config value
    (900s by default) via ``call_llm``'s own resolution, exactly like every
    other auxiliary task. An explicit finite positive per-preset value is
    honored as-is — no artificial cap, since long-thinking advisor models
    legitimately run far beyond five minutes.
    """
```

那个 900 确实在 DEFAULT_CONFIG 里。`hermes_cli/config_defaults.py:1049 @ 863e313`

```python
        "moa_reference": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 900,
```

只有它显式挡了 bool。`hermes_cli/moa_config.py:57 @ 863e313`

```python
    if value is None or value == "" or isinstance(value, bool):
        return DEFAULT_MOA_REFERENCE_TIMEOUT
```

失败顾问的披露策略:未知值**响亮回落**到 `loud`。`hermes_cli/moa_config.py:68 @ 863e313`

```python
def _coerce_degraded_reference_policy(value: Any) -> str:
    """Normalize failed-advisor disclosure policy; unknown values fail loud."""
    policy = str(value or "loud").strip().lower()
    return policy if policy in {"loud", "silent"} else "loud"
```

**fan-out 节奏**是本文件最有信息量的一个键:它决定顾问跑几次,直接乘在费用和延迟上。
`hermes_cli/moa_config.py:104 @ 863e313`

```python
def _coerce_fanout(value: Any) -> str:
    """Normalize the fan-out cadence; unknown values fall back to default.

    Canonical values are the strings ``per_iteration``, ``user_turn``, and
    ``every_n:<N>`` (N >= 2). The ``every_n`` cadence also accepts the mapping
    form ``{mode: every_n, n: N}`` from hand-edited YAML and normalizes it to
    the canonical string, so the rest of the pipeline (presets, flattened
    view, runtime) only ever sees one shape. ``every_n:1`` semantically means
    "run every iteration" and collapses to ``per_iteration``; anything
    unparseable falls back to ``user_turn`` (the default — cheapest cadence;
    see #67199).
    """
```

dict 形式先归一,再走字符串通路。`hermes_cli/moa_config.py:116 @ 863e313`

```python
    if isinstance(value, dict):
        # Mapping form: {mode: every_n, n: 3}. Non-every_n mapping modes fall
        # through to the string path below (e.g. {mode: user_turn}).
        mode = str(value.get("mode") or "").strip().lower()
        if mode == "every_n":
            n = _coerce_int(value.get("n"), 0)
            if n >= 2:
                return f"every_n:{n}"
            return "per_iteration" if n == 1 else "user_turn"
        value = mode
```

`hermes_cli/moa_config.py:129 @ 863e313`

```python
    if mode.startswith("every_n"):
        _, sep, rest = mode.partition(":")
        n = _coerce_int(rest.strip(), 0) if sep else 0
        if n >= 2:
            return f"every_n:{n}"
        if n == 1:
            return "per_iteration"
    return "user_turn"
```

隐私过滤三态。`hermes_cli/moa_config.py:139 @ 863e313`

```python
def coerce_privacy_filter(value: Any) -> str:
    """Normalize ``moa.privacy_filter`` to '' (off), 'display', or 'full'.

    - ``''`` (empty string): filter off — the default. ``false``/``None``/
      unknown values land here so a hand-edited config degrades to prior
      behavior (tolerant-read contract).
    - ``'display'``: redact user-visible surfaces only — the reference blocks
      shown in the UI and the saved MoA trace records. The aggregator still
      sees raw advisor text, so answer quality is unaffected.
    - ``'full'``: additionally redact the advisor text injected into the
      aggregator prompt (issue #59959's literal ask). A hand-edited boolean
      ``true`` maps here because the issue framed the toggle as "redact
      before passing to the aggregator".
    """
```

## 18. preset 归一与「扁平兼容视图」

`_normalize_preset` 的输入宽容度:`reference_models` 可以是 JSON 字符串(手写 config.yaml)、可以是单个
mapping、可以是任意坏类型。`hermes_cli/moa_config.py:317 @ 863e313`

```python
    raw_refs = raw.get("reference_models")
    # reference_models may be a JSON string (hand-edited config.yaml) or a list.
    if isinstance(raw_refs, str):
        try:
            raw_refs = json.loads(raw_refs)
        except (json.JSONDecodeError, ValueError):
            raw_refs = []
```

`hermes_cli/moa_config.py:324 @ 863e313`

```python
    if not isinstance(raw_refs, list):
        # A hand-edited scalar / single mapping (or a bad type) must degrade to
        # defaults instead of crashing the iteration, mirroring the tolerance
        # for the scalar fields below (reference_temperature / max_tokens).
        raw_refs = [raw_refs] if isinstance(raw_refs, dict) else []
```

全部被丢光就回默认。`hermes_cli/moa_config.py:329 @ 863e313`

```python
    refs = [_clean_slot(item, include_enabled=True) for item in raw_refs]
    refs = [item for item in refs if item is not None]
    if not refs:
        refs = _default_reference_models()
```

`reference_max_tokens` 的注释给出了性能依据(延迟与输出 token 相关系数 ~0.88,封顶大致把 per-turn
墙钟时间砍半),且**只封顶顾问,不封顶聚合器**。`hermes_cli/moa_config.py:355 @ 863e313`

```python
        "reference_max_tokens": _coerce_int_or_none(raw.get("reference_max_tokens")),
```

顶层归一:先吃 `presets`,吃不到就把整个 `moa` 块当成一个叫 `default` 的 preset(向后兼容第一版 PR 形状)。
`hermes_cli/moa_config.py:381 @ 863e313`

```python
    presets_raw = raw.get("presets")
    presets: dict[str, dict[str, Any]] = {}
    if isinstance(presets_raw, dict):
        for name, preset in presets_raw.items():
            clean_name = str(name or "").strip()
            if clean_name:
                presets[clean_name] = _normalize_preset(preset)

    # Legacy flat config becomes the default preset.
    if not presets:
        presets[DEFAULT_MOA_PRESET_NAME] = _normalize_preset(raw)
```

`hermes_cli/moa_config.py:393 @ 863e313`

```python
    default_name = str(raw.get("default_preset") or "").strip()
    if not default_name or default_name not in presets:
        default_name = next(iter(presets), DEFAULT_MOA_PRESET_NAME)
    if default_name not in presets:
        presets[default_name] = _default_preset()
```

返回值同时给「按名字取」和「扁平兼容视图」两套。**扁平视图取的是 `default_preset`,不是 `active_preset`**。
`hermes_cli/moa_config.py:403 @ 863e313`

```python
    active = presets[default_name]
    return {
        "default_preset": default_name,
        "active_preset": active_name,
        "presets": presets,
        # Compatibility/flattened view for existing dashboard/desktop callers.
        "reference_models": deepcopy(active["reference_models"]),
```

`resolve_moa_preset` 同样只看 `default_preset`,且**不检查 preset 的 `enabled`**。
`hermes_cli/moa_config.py:431 @ 863e313`

```python
def resolve_moa_preset(config: Any, name: str | None = None) -> dict[str, Any]:
    cfg = normalize_moa_config(config)
    preset_name = str(name or cfg.get("default_preset") or DEFAULT_MOA_PRESET_NAME).strip()
```

找不到时抛的是可行动的错误(列出可用名 + 给命令)。`hermes_cli/moa_config.py:439 @ 863e313`

```python
        raise MoAPresetNotFoundError(
            f"MoA preset '{preset_name}' was not found. Available presets: "
            f"{available}. Run `hermes moa list`."
        )
```

且被分类成**不可重试、不可 failover**。`tests/hermes_cli/test_moa_config.py:104 @ 863e313`

```python
    assert result.reason == FailoverReason.model_not_found
    assert result.retryable is False
    assert result.should_fallback is False
```

`exact_moa_preset_name` 是唯一读 preset 级 `enabled` 的地方:**隐式**匹配(用户裸打 `/model <name>`)
必须尊重 `enabled: false`,否则名字撞车会把会话静默切到 MoA 虚拟 provider(#55187);**显式**选择
(`--provider moa` / 模型选择器)仍然可达。`hermes_cli/moa_config.py:446 @ 863e313`

```python
def exact_moa_preset_name(config: Any, text: str) -> str | None:
    """Return the preset name iff ``text`` exactly matches an *enabled* preset.
```

`hermes_cli/moa_config.py:463 @ 863e313`

```python
    preset = cfg["presets"].get(wanted)
    if preset is None or not preset.get("enabled", True):
        return None
    return wanted
```

调用点在 model switch 的 PATH B。`hermes_cli/model_switch.py:1422 @ 863e313`

```python
            _moa_match = exact_moa_preset_name(_moa_cfg, raw_input)
```

slot 级 `enabled` 在运行时被过滤。`agent/moa_loop.py:1895 @ 863e313`

```python
        reference_models = [
            slot for slot in (preset.get("reference_models") or [])
            if slot.get("enabled", True)
        ]
```

## 19. 一次性 marker 协议(encode / decode)

设计意图:给「只能发纯文本」的前端一条把 MoA 配置塞进一次 turn 的通道。
`hermes_cli/moa_config.py:478 @ 863e313`

```python
def encode_moa_turn(prompt: str, config: Any = None, preset: str | None = None) -> str:
    """Encode a /moa one-shot turn for frontends that can only send text."""
```

解码在 conversation_loop 的入口,对**原始用户消息**做前缀匹配。`agent/conversation_loop.py:1274 @ 863e313`

```python
    if moa_config is None:
        try:
            from hermes_cli.moa_config import decode_moa_turn

            _decoded_message, _decoded_moa_config = decode_moa_turn(user_message)
```

解码失败一律**原样返回**,不抛。`hermes_cli/moa_config.py:490 @ 863e313`

```python
def decode_moa_turn(message: Any) -> tuple[str, dict[str, Any] | None]:
    """Decode a hidden /moa one-shot marker."""
    if not isinstance(message, str) or not message.startswith(MOA_MARKER_PREFIX):
        return message, None
```

`hermes_cli/moa_config.py:495 @ 863e313`

```python
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8"))
    except Exception:
        return message, None
```

**但现在 `/moa` 已经不走 marker 了**:CLI 与 gateway 都改成切到 `moa` 虚拟 provider + 一次性还原。
`cli.py:10333 @ 863e313`

```python
            self.requested_provider = "moa"
            self.provider = "moa"
            self.model = preset
```

`gateway/run.py:15384 @ 863e313`

```python
                _moa_state.conversation.model_override = {
                    "provider": "moa",
                    "model": preset,
```

于是 `encode_moa_turn` / `build_moa_turn_prompt` 在生产代码里**没有调用方**(仅测试 import),
而解码器仍然在线 —— 见「可疑缺陷 D7」。

`moa_usage()` 的文案与上面这套行为一致。`hermes_cli/moa_config.py:508 @ 863e313`

```python
def moa_usage() -> str:
    return "Usage: /moa <prompt>  (runs one prompt through the default MoA preset, then restores your model; pick a preset from the model picker to switch for the session)"
```

---

## 20. 配置键穷举

### 20.1 `mcp_servers.*`(由 `mcp_config.py` 读或写)

| 键 | 默认 | 读/写点(`@ 863e313`) | 备注 |
|---|---|---|---|
| `mcp_servers` | 不在 DEFAULT_CONFIG | `hermes_cli/mcp_config.py:82`(读)/ `:102`(写) | 缺失/非 dict → `{}` |
| `mcp_servers.<n>.url` | — | `hermes_cli/mcp_config.py:468` | HTTP transport;与 `command` 二选一 |
| `mcp_servers.<n>.command` | — | `hermes_cli/mcp_config.py:470` | stdio transport;安全校验的主要对象 |
| `mcp_servers.<n>.args` | — | `hermes_cli/mcp_config.py:472` | 仅 stdio;首项 `--` 会被剥掉 |
| `mcp_servers.<n>.env` | — | `hermes_cli/mcp_config.py:474` | 仅 stdio;`--env` 给 HTTP 会报错 |
| `mcp_servers.<n>.headers` | — | `hermes_cli/mcp_config.py:528` / `:535` | 只存 `${MCP_<N>_API_KEY}` 模板 |
| `mcp_servers.<n>.auth` | 无(缺省=无认证) | `hermes_cli/mcp_config.py:497` 写 / `:799` `:932` 读 | 实际只会被写成 `"oauth"` |
| `mcp_servers.<n>.oauth` | — | `hermes_cli/mcp_config.py:495` | 传给 `get_or_build_provider` |
| `mcp_servers.<n>.oauth.client_id` | — | `hermes_cli/mcp_config.py:864`(仅打印指引) | 本文件不读,交给 mcp_oauth |
| `mcp_servers.<n>.oauth.client_secret` | — | `hermes_cli/mcp_config.py:865`(仅打印指引) | 同上 |
| `mcp_servers.<n>.enabled` | `True` | `hermes_cli/mcp_config.py:711` 读 / `:547` `:613` 写 | CLI 只认 `true/1/yes` 字符串 |
| `mcp_servers.<n>.connect_timeout` | 探针 `30`,运行时 `60` | `hermes_cli/mcp_config.py:304` / `:829` | login 路径地板 315 |
| `mcp_servers.<n>.tools` | 无(=全开) | `hermes_cli/mcp_config.py:697` `:997` `:1056` | 全选时删键 |
| `mcp_servers.<n>.tools.include` | — | `hermes_cli/mcp_config.py:1060` | 精确名或 fnmatch glob |
| `mcp_servers.<n>.tools.exclude` | — | `hermes_cli/mcp_config.py:1000` 读 / `:1061` 删 | CLI 从不写它,只删 |
| `mcp_servers.<n>.tools.prompts` | `True` | `hermes_cli/mcp_config.py:336` | 门控探针的 `prompts/list` |
| `mcp_servers.<n>.tools.resources` | `True` | `hermes_cli/mcp_config.py:339` | 门控探针的 `resources/list` |

`timeout` / `ssl_verify` / `client_cert` / `transport` / `keepalive_interval` / `idle_timeout_seconds` /
`max_lifetime_seconds` / `skip_preflight` / `sampling` / `elicitation` 等键存在于文档与
`tools/mcp_tool.py`,但 **`mcp_config.py` 本身既不写也不读**(它只是原样保存用户给的 dict)。

### 20.2 `moa.*`(由 `moa_config.py` 归一)

| 键 | 默认 | 归一点(`@ 863e313`) | 备注 |
|---|---|---|---|
| `moa` | 见 `hermes_cli/config_defaults.py:1754` | 由调用方 `load_config().get("moa")` | 本文件不读文件 |
| `moa.default_preset` | `"default"` | `hermes_cli/moa_config.py:393` | 名字不存在时回落到第一个 preset |
| `moa.active_preset` | `""` | `hermes_cli/moa_config.py:399` | 名字不存在时归 `""` |
| `moa.privacy_filter` | `""` | `hermes_cli/moa_config.py:422` | `''` / `display` / `full` |
| `moa.presets` | 见下 | `hermes_cli/moa_config.py:381` | 空则把整块当 legacy 扁平 preset |
| `moa.presets.<p>.enabled` | `True` | `hermes_cli/moa_config.py:337` | 只影响隐式名字匹配 |
| `moa.presets.<p>.reference_models` | 两条内建 | `hermes_cli/moa_config.py:329` | 接受 JSON 字符串 / 单 dict |
| `…reference_models[].provider` | — | `hermes_cli/moa_config.py:197` | 空则整槽丢弃 |
| `…reference_models[].model` | — | `hermes_cli/moa_config.py:198` | 空则整槽丢弃 |
| `…reference_models[].reasoning_effort` | 无 | `hermes_cli/moa_config.py:209` | `false` → `"none"` |
| `…reference_models[].max_tokens` | `None` | `hermes_cli/moa_config.py:217` | 覆盖 preset 级 `reference_max_tokens` |
| `…reference_models[].enabled` | `True` | `hermes_cli/moa_config.py:221` | 运行时过滤 |
| `moa.presets.<p>.aggregator` | 见常量 | `hermes_cli/moa_config.py:334` | 同 slot schema,无 `enabled` |
| `moa.presets.<p>.reference_temperature` | `None` | `hermes_cli/moa_config.py:340` | None = 不发该参数 |
| `moa.presets.<p>.aggregator_temperature` | `None` | `hermes_cli/moa_config.py:341` | 同上 |
| `moa.presets.<p>.reference_timeout` | `None` | `hermes_cli/moa_config.py:342` | None = 继承 `auxiliary.moa_reference.timeout` |
| `moa.presets.<p>.degraded_reference_policy` | `"loud"` | `hermes_cli/moa_config.py:343` | 只认 `loud` / `silent` |
| `moa.presets.<p>.max_tokens` | `4096` | `hermes_cli/moa_config.py:346` | 聚合器输出上限 |
| `moa.presets.<p>.reference_max_tokens` | `None` | `hermes_cli/moa_config.py:355` | 只封顶顾问 |
| `moa.presets.<p>.fanout` | `"user_turn"` | `hermes_cli/moa_config.py:368` | `user_turn` / `per_iteration` / `every_n:N` |
| `moa.reference_models` 等(扁平) | — | `hermes_cli/moa_config.py:391` | legacy 形状,整块当 `default` preset |
| `moa.save_traces` | `False` | 本文件**不处理** | `hermes_cli/config_defaults.py:1763`;被 normalize 丢弃 |
| `moa.trace_dir` | `""` | 本文件**不处理** | 同上 |
| `auxiliary.moa_reference.timeout` | `900` | 本文件只在 docstring 提及 | `hermes_cli/config_defaults.py:1054` |

### 20.3 环境变量

| 变量 | 类型 | 读/写点 | 说明 |
|---|---|---|---|
| `MCP_<SERVER>_API_KEY` | 动态生成 | 写 `hermes_cli/mcp_config.py:195`;读 `hermes_cli/mcp_config.py:522` | 名字由 `_env_key_for_server` 生成;config.yaml 里只留 `${…}` 模板 |
| 任意 `${VAR}` / `${env:VAR}` | 用户在 server entry 里写的 | 解析 `tools/mcp_tool.py:4550`;掩码 `hermes_cli/mcp_config.py:755` | 未设置则保留字面占位符 |
| `HERMES_HOME` | 间接 | `hermes_constants.py:779`(`display_hermes_home`) | 决定 config.yaml / .env 路径;profile 切换即换它 |
| `HERMES_SAFE_MODE` | 间接 | `tools/mcp_tool.py:4655` | **CLI 读侧不认**,只影响运行时加载 |

`moa_config.py` 里**没有任何环境变量**(全文件无 `os` import)。

---

## 21. 文档 / 注释与代码的出入

**▲ C1 — `connect_timeout` 默认值三套并存。** 文档说 60。
`website/docs/reference/mcp-config-reference.md:58 @ 863e313`

```
| `connect_timeout` | number | both | Initial connection timeout in seconds (default: `60`) |
```

运行时确实是 60(`tools/mcp_tool.py:334`),但 CLI 探针写死 30。`hermes_cli/mcp_config.py:304 @ 863e313`

```python
        raw_timeout = config.get("connect_timeout", 30)
```

后果:一台冷启动 40 秒的 server,`hermes mcp add` / `hermes mcp test` 报连接失败,但真正跑 agent 时能连上。

**▲ C2 — `--command` 的 dest 注释指错了文件。** mcp_config 说这个 dest 改名在 `hermes_cli/main.py`。
`hermes_cli/mcp_config.py:419 @ 863e313`

```python
    # Read from `mcp_command` (set by --command via explicit dest) — see
    # mcp_add_p.add_argument("--command", dest="mcp_command", ...) in
    # hermes_cli/main.py for why the dest is renamed.
```

实际在 `hermes_cli/subcommands/mcp.py`(main.py 全文没有 `mcp_add_p`)。
`hermes_cli/subcommands/mcp.py:52 @ 863e313`

```python
    mcp_add_p.add_argument(
        "--command", dest="mcp_command", help="Stdio command (e.g. npx)"
    )
```

**◇ C3 — 模块 docstring 列的子命令不全。** 它只列了 `add/remove/list/test/configure`。
`hermes_cli/mcp_config.py:4 @ 863e313`

```python
Implements ``hermes mcp add/remove/list/test/configure`` for interactive
```

实际还实现了 `login` / `reauth`,并分发 `serve` / `picker` / `catalog` / `install`。
`hermes_cli/mcp_config.py:1109 @ 863e313`

```python
        "login": cmd_mcp_login,
        "reauth": cmd_mcp_reauth,
```

**◇ C4 — 文档提到的 `mcp_servers.yaml` 文件不存在。**
`website/docs/user-guide/features/mcp.md:860 @ 863e313`

```
- The embedded `hermes mcp serve` exposes a **stdio-only** MCP server today. If you need an HTTP MCP server, run a separate adapter — or, much more commonly, use the MCP **client** side of Hermes, which already speaks both stdio and HTTP (`url` + `headers` in `mcp_servers.yaml` / `config.yaml`; see [HTTP servers](#http-servers) above).
```

全仓 `.py` 里没有任何地方读 `mcp_servers.yaml`(唯一出现处是这句文档和它的中文翻译)。

**◇ C5 — 「preset 只提供默认值,同命令行的其他参数仍然生效」说法过强。**
`website/docs/user-guide/features/mcp.md:376 @ 863e313`

```
For well-known MCP servers, `hermes mcp add` accepts a `--preset` flag that fills in the transport details so you don't have to look up the command and args. The preset only supplies defaults — anything else (env vars, headers, filtering) you pass on the same command line still wins.
```

代码是**整体跳过**而不是逐字段兜底:只要给了 `--url` 或 `--command`,预设的 `args` 也一起不生效。
`hermes_cli/mcp_config.py:235 @ 863e313`

```python
    if url or command:
        return url, command, cmd_args, False
```

即 `hermes mcp add x --preset codex --command /opt/codex` 得到的是 `command: /opt/codex` 且**没有 args**。

**◇ C6 — `_resolve_mcp_server_config` docstring 说「把 `~/.hermes/.env` 载入 `os.environ`」,但代码只在
没有活跃 secret scope 时才这么做。** docstring:`hermes_cli/mcp_config.py:257 @ 863e313`

```python
    Mirrors ``_load_mcp_config()`` in ``tools/mcp_tool.py``: load
```

代码:`hermes_cli/mcp_config.py:269 @ 863e313`

```python
    if current_secret_scope() is None:
```

---

## 22. 可疑缺陷(只记录不修)

**D1 — `hermes mcp add` 在用户把 token 输成 `Bearer` 时抛未捕获的 ValueError。**
`_prompt` 会 strip,所以输入 `"Bearer "` 变成 `"Bearer"`(真值),进入 `_save_bearer_auth_token`;
`_strip_bearer_prefix` 因为要求前缀是 `"bearer "`(带空格)而不剥离,于是命中「只剩 bearer」的拒绝分支。
`hermes_cli/mcp_config.py:192 @ 863e313`

```python
    normalized = _strip_bearer_prefix(token)
    if not normalized or normalized.lower() == "bearer":
        raise ValueError("Bearer token is required")
```

调用点没有 try。`hermes_cli/mcp_config.py:527 @ 863e313`

```python
                    if api_key:
                        server_config["headers"] = _save_bearer_auth_token(
                            name, api_key
                        )
```

**怎么会踩到**:用户从文档里复制 `Bearer <TOKEN>` 但只粘了前半截,CLI 直接吐 traceback 而不是提示重输。
测试只覆盖了直接调用 `_save_bearer_auth_token` 的 ValueError,没覆盖 CLI 路径。
`tests/hermes_cli/test_mcp_config.py:544 @ 863e313`

```python
    def test_empty_token_is_rejected(self):
```

**D2 — 用户回答「需要认证」但直接回车,服务器被静默保存成无认证。**
`existing_key` 为空、`api_key` 也为空时,两个 `if` 都不触发,`server_config` 里根本没有 `headers`。
`hermes_cli/mcp_config.py:533 @ 863e313`

```python
                # Set header with env var interpolation
                if existing_key:
                    server_config["headers"] = _bearer_auth_headers(name)
```

**怎么会踩到**:回车跳过输入 → 探针 401 → 用户以为是服务器问题;或者探针恰好放行(见 OAuth 那段的
Google Drive 情形)→ 存下一个永远调不通的条目。全程无任何提示。

**D3 — `--auth` 在 stdio 路径下被完全忽略。** OAuth 分支要求 `url`,header 分支在 `elif url:` 里。
`hermes_cli/mcp_config.py:487 @ 863e313`

```python
    if url and auth_type == "oauth":
```

**怎么会踩到**:`hermes mcp add x --command foo --auth oauth` 静默成功、不写任何 auth,也不警告。

**D4 — `enabled` 的字符串解释在 CLI 与运行时不一致。** CLI 列表:
`hermes_cli/mcp_config.py:713 @ 863e313`

```python
            enabled = enabled.lower() in {"true", "1", "yes"}
```

运行时:`tools/mcp_tool.py:6559 @ 863e313`

```python
        enabled = _parse_boolish(cfg.get("enabled", True), default=True)
```

**怎么会踩到**:手写 `enabled: "on"`(YAML 引号内)时,`hermes mcp list` 显示 disabled,而 agent 实际加载它;
反过来手写 `enabled: "maybe"` 时 CLI 显示 disabled、运行时按 default=True 加载。诊断会指向错误方向。

**D5 — `hermes moa configure` / `hermes moa delete` 会丢掉 `moa.save_traces` 与 `moa.trace_dir`。**
`normalize_moa_config` 返回的是**封闭 schema**,不含这两个键;`agent`/`web_server` 侧用 `.update()` 合并
以保留它们(#58819 的修法),CLI 侧却是整键覆盖。`hermes_cli/web_server.py:6520 @ 863e313`

```python
            # Merge instead of overwrite so that hand-edited keys not declared
            # in MoaConfigPayload (e.g. save_traces, trace_dir) survive a GUI
            # save.  See issue #58819.
            cfg.setdefault("moa", {}).update(normalized)
```

CLI:`hermes_cli/moa_cmd.py:127 @ 863e313`

```python
        cfg["moa"] = normalize_moa_config(moa)
        save_config(cfg)
```

`hermes_cli/moa_cmd.py:147 @ 863e313`

```python
        cfg["moa"] = normalize_moa_config(moa)
        save_config(cfg)
        print(f"Deleted MoA preset: {preset_name}")
```

**怎么会踩到**:手写 `moa.save_traces: true` 开了 trace,之后跑一次 `hermes moa configure` 换模型,
trace 就悄悄关了。#58819 的回归测试只测了 `set_moa_models`(GUI 路径)。
`tests/hermes_cli/test_moa_set_models_preserves_extra_keys.py:12 @ 863e313`

```python
from hermes_cli.web_server import MoaConfigPayload, MoaModelSlot, MoaPresetPayload, set_moa_models
```

**D6 — `hermes moa configure` 也不过 `validate_moa_payload`。** GUI 侧「reject-don't-repair」的保护
在 CLI 侧不存在;CLI 直接把 normalize 结果写盘,坏 slot 被静默替换成默认。见 D5 的两处 `cfg["moa"] = …`。

**D7 — `normalize_moa_config` 里有一段可证明不可达的死代码,`_default_preset()` 因此整个变成死函数。**
`hermes_cli/moa_config.py:389 @ 863e313`

```python
    # Legacy flat config becomes the default preset.
    if not presets:
        presets[DEFAULT_MOA_PRESET_NAME] = _normalize_preset(raw)
```

到这一步 `presets` 必非空,所以 `next(iter(presets), …)` 一定返回一个已存在的键,下面这个 `if` 永假:
`hermes_cli/moa_config.py:396 @ 863e313`

```python
    if default_name not in presets:
        presets[default_name] = _default_preset()
```

而 `_default_preset` 的唯一引用就是这一行。`hermes_cli/moa_config.py:296 @ 863e313`

```python
def _default_preset() -> dict[str, Any]:
```

**怎么会踩到**:不会踩到(这正是问题)—— 它是 `_normalize_preset` 之外的**第二份默认 preset 定义**,
两份键集必须手工保持同步,却没有任何测试或调用路径会发现它们漂移。

**D8 — `moa.active_preset` 是记账键,没有任何读它来选 preset 的生产代码。**
`resolve_moa_preset` 用的是 `default_preset`。`hermes_cli/moa_config.py:433 @ 863e313`

```python
    preset_name = str(name or cfg.get("default_preset") or DEFAULT_MOA_PRESET_NAME).strip()
```

它只被显示、被删除时清空、被前端来回传。`hermes_cli/moa_cmd.py:82 @ 863e313`

```python
    active = cfg.get("active_preset") or "(off)"
```

**怎么会踩到**:用户在 GUI 里「选中」一个 preset,`hermes moa list` 显示 `Active in config: X`,
但下一次 `/moa` 或 MoA 虚拟 provider 用的仍是 `default_preset`。

**D9 — `set_active_moa_preset` / `list_moa_presets` / `encode_moa_turn` / `build_moa_turn_prompt` 是死代码。**
仅测试(或无任何地方)引用。`hermes_cli/moa_config.py:469 @ 863e313`

```python
def set_active_moa_preset(config: Any, name: str | None) -> dict[str, Any]:
```

`hermes_cli/moa_config.py:426 @ 863e313`

```python
def list_moa_presets(config: Any) -> list[str]:
```

**D10 — marker 解码是一条无生产生产者的输入面。** 任何以 `__HERMES_MOA_TURN_V1__` 开头的**用户消息**
都会被解码成一份 MoA 配置并接管这一轮的 provider/model 选择,而生产代码里已经没有东西会产出这个前缀。
`agent/conversation_loop.py:1278 @ 863e313`

```python
            _decoded_message, _decoded_moa_config = decode_moa_turn(user_message)
```

**怎么会踩到**:经由不可信通道(Discord / Slack / gateway HTTP)进来的消息,只要带这个前缀,
就能指定用哪个 provider+model 跑这一轮。递归 MoA 被 `_clean_slot` 挡住,但 provider/model 选择不受限。
未确证的部分:我没有逐条追查每个 gateway 入口是否会把外部文本原样送到
`agent/conversation_loop.py:1278` 的 `user_message`,所以只标为「输入面」,不断言可利用。

**D11 — `cmd_mcp_test` 的 header 掩码用裸 `os.getenv`,与同文件的 scope-aware 解析口径不一致。**
`hermes_cli/mcp_config.py:755 @ 863e313`

```python
                resolved = _ENV_VAR_PATTERN.sub(lambda m: os.getenv(_env_ref_name(m.group(1)), ""), v)
```

对照 scope-aware 的那条路径。`tools/mcp_tool.py:4548 @ 863e313`

```python
    from agent.secret_scope import get_secret as _get_secret
```

**怎么会踩到**:多 profile 场景下,`hermes mcp test` 打印的掩码取自进程环境(可能是另一个 profile 的值,
或干脆为空显示 `***`),而同一次命令里真正发出去的 header 用的是 scope 里的值 —— 掩码可能对不上实际凭据。

**D12 — `_unwrap_exception_group` 只取第一个子异常。** `hermes_cli/mcp_config.py:406 @ 863e313`

```python
        exc = exc.exceptions[0]
```

**怎么会踩到**:transport 层与 auth 层同时失败时,用户只看到其中一个原因(且顺序不确定)。

**D13 — `_coerce_float_or_none` / `_coerce_int` / `_coerce_int_or_none` 都不挡 bool,只有
`_coerce_reference_timeout` 挡。** `hermes_cli/moa_config.py:74 @ 863e313`

```python
def _coerce_int(value: Any, default: int) -> int:
```

**怎么会踩到**:手写 `max_tokens: true` → `int(True)` = 1,聚合器被限制成 1 个 token 输出;
手写 `reference_temperature: true` → 1.0(而不是「未设置」)。两处都无警告。

**D14 — `moa_config.py` 的测试文件有多段只剩标题、没有测试的空节。**
`tests/hermes_cli/test_moa_config.py:168 @ 863e313`

```python
# --- fanout cadence normalization (every_n) ---
```

`tests/hermes_cli/test_moa_config.py:177 @ 863e313`

```python
# --- privacy_filter normalization ---
```

**怎么会踩到**:`_coerce_fanout` 的 `every_n` 解析、`coerce_privacy_filter` 的三态映射在这个文件里
**没有单元测试**(行为规格散落在 `tests/run_agent/test_moa_fanout_cadence.py` 与
`tests/run_agent/test_moa_privacy_filter.py` 的端到端测试里)。改归一逻辑时容易漏。

---

## 23. 配套测试(行为规格)

| 文件 | 覆盖什么 |
|---|---|
| `tests/hermes_cli/test_mcp_config.py` | list / remove / add(HTTP、stdio+env、preset)/ test / 探针超时 / `${ENV}` 解析与 secret scope / 能力门控 / bearer 前缀与落盘分离 / `_env_key_for_server` / dispatcher / login 的假成功与真成功 / reauth --all 顺序与部分失败 |
| `tests/hermes_cli/test_mcp_security.py` | `validate_mcp_server_entry` 的三类形状 |
| `tests/hermes_cli/test_mcp_add_command_dest.py` | `--command` 的 dest 改名回归 |
| `tests/hermes_cli/test_mcp_tools_config.py` | `tools` 过滤键 |
| `tests/hermes_cli/test_mcp_dashboard_oauth.py` | dashboard 复用 `_get_mcp_servers` 的 OAuth 路径 |
| `tests/hermes_cli/test_mcp_discovery_timing.py` | 发现耗时 |
| `tests/tools/test_mcp_capability_gating.py`、`tests/tools/test_mcp_utility_capability_gating.py` | 运行时侧的同一套能力门控 |
| `tests/hermes_cli/test_moa_config.py` | 默认命名 preset / 禁用 preset 不参与隐式匹配 / preset 缺失错误可行动且不可重试 / validate 与 `_clean_slot` 的一致性契约 |
| `tests/hermes_cli/test_moa_set_models_preserves_extra_keys.py` | GUI 写路径保留 `save_traces` / `trace_dir` |
| `tests/cli/test_moa_command.py` | `/moa` 斜杠命令 + `decode_moa_turn` |
| `tests/run_agent/test_moa_fanout_cadence.py` | `fanout` 三种节奏的端到端行为 |
| `tests/run_agent/test_moa_privacy_filter.py` | `privacy_filter` 三态的端到端行为 |
| `tests/agent/test_moa_slot_max_tokens.py`、`test_moa_reasoning_effort.py`、`test_moa_slot_api_mode.py` | 每槽参数如何进入请求 |

实跑记录(基线 + venv):

```
$ HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
    tests/hermes_cli/test_mcp_config.py tests/hermes_cli/test_moa_config.py
=== Summary: 2 files, 36 tests passed, 0 failed (100% complete) in 1.4s (8 workers) ===
```

---

## 24. 重实现要点

如果要从零重写这两块配置面,以下八条是必须知道的:

1. **把「外部资源配置」和「参数配置」当两种东西写。** 外部资源(MCP server)的配置面必须绑三件套:
   保存前安全校验、保存后可探针验证、密钥不落主配置;参数配置(MoA preset)应该做成**零 I/O 纯函数**,
   否则运行时热路径没法缓存它(`agent/moa_loop.py:1861` 那段 mtime 缓存就是被逼出来的)。

2. **同一份归一逻辑必须开两个闸门:读时宽容、写时严格,并且用一对镜像函数把两者钉死。**
   `_clean_slot` / `_slot_problem` 是范本 —— 前者「丢」,后者「说出为什么丢」,再加一条契约测试证明
   validate 放行的东西 normalize 不会改。只做宽容侧的代价是 #64156 那种「半填表单吞掉整个 preset」。

3. **删除必须有专门的写 API。** 深合并型的配置写入永远删不掉键。要么像 `_replace_mcp_servers` 那样提供
   整表替换(并且全有或全无地校验),要么在 schema 上支持显式 tombstone。别指望 `PATCH` 能删东西。

4. **密钥走「config 存模板、.env 存真值、读时插值」三段式,并且插值必须 scope-aware。**
   注意两个坑:(a) 模板构造函数要 CLI 与 GUI 共用,否则两边产出的 config 不是字节等价的;
   (b) **每一条会用到这份 config 的路径都要插值** —— #37792 就是探针路径漏了插值,把
   `Bearer ${MCP_X_API_KEY}` 字面量发出去。掩码/展示路径也算一条(见 D11)。

5. **「探针连上了」不等于「认证成功了」。** 很多 MCP server 允许无鉴权的 `initialize` + `tools/list`。
   成功判定必须查一个**真实副作用**(token 是否落盘),否则会给出假成功,而故障要到第一次真实工具调用
   超时才暴露。

6. **能力探测要双重门控:用户配置 + 服务器 advertise,并且在没有能力信息时保持旧的「都试一下」。**
   只做其中一道,要么压不住报错(用户配置被忽略),要么老服务器/旧 fixture 全部失能。

7. **超时常量要有唯一权威。** 本仓 `connect_timeout` 的默认值在探针(30)、运行时(60)、文档(60)
   三处漂移,还有一个 OAuth 专用地板(315)在 CLI 和 GUI 各写一遍。至少要把默认值提到一个常量、
   把「交互式 OAuth 需要更长地板」做成一个具名函数。

8. **bool-ish / int-ish 解析要全仓一套。** 本仓至少有三套 `enabled` 字符串语义(`mcp_config` 的
   `{true,1,yes}`、`mcp_tool._parse_boolish` 的 `{true,1,yes,on}`、`config.py` 的「不在
   `{false,0,no,off}` 里就为真」)。写归一函数时还要显式决定 **bool 是不是合法的数字输入** ——
   `int(True) == 1` 这条 Python 陷阱在 `max_tokens: true` 上会变成「输出 1 个 token」。
