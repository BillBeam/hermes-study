# r8a-raw-tools-config-b · tools_config.py:1900-3700

底稿。范围:`hermes_cli/tools_config.py` 第 1900–3700 行(全文 5452 行),基线
`863e31318553cda8ad61df681d08175364d4164b`(下称 `863e313`)。溯源约定:每条断言后紧跟
`路径:行号 @ 863e313` + 基线原文块。路径相对 hermes-agent 仓库根。

本段的顶层符号(按行号):`valid_post_setup_keys`(2010)、`run_post_setup_command`(2042)、
`_get_enabled_platforms`(2074)、`_platform_toolset_summary`(2090)、`_parse_enabled_flag`(2106)、
`enabled_mcp_server_names`(2123)、`_exempt_explicit_platform_native`(2141)、
`_RECENTLY_SHIPPED_TOOLSETS`(2185)、`_enable_recently_shipped_toolsets`(2188)、
**`_get_platform_tools`(2223,本段核心)**、`_save_platform_tools`(2521)、`_toolset_has_keys`(2617)、
`_prompt_choice`(2671)、`_estimate_tool_tokens`(2683)、`_prompt_toolset_checklist`(2725)、
`_configure_toolset`(2790)、五个 `_plugin_*_providers`(2810/2850/2898/2981/3028)、
`web_provider_capabilities`(2946)、`_visible_providers`(3084)、`_hidden_nous_gateway_message`(3170)、
`_POST_SETUP_INSTALLED`(3189)/`_POST_SETUP_READY`(3264) 及其谓词、
`provider_readiness_status`(3287)、`_toolset_needs_configuration_prompt`(3367)、
`_configure_tool_category`(3436)、`_is_provider_active`(3550)、`_detect_active_provider_index`(3634)、
`IMAGEGEN_BACKENDS`(3670)、`_configure_imagegen_model`(3689)。

---

## 0. 上下文:模块自称做什么

模块 docstring 把本文件定义为"选平台 → 勾工具集 → 给新开的工具跑 provider 感知配置",落盘位置是
`~/.hermes/config.yaml` 的 `platform_toolsets` 键。`hermes_cli/tools_config.py:1-10 @ 863e313`

```python
"""
Unified tool configuration for Hermes Agent.

`hermes tools` and `hermes setup tools` both enter this module.
Select a platform → toggle toolsets on/off → for newly enabled tools
that need API keys, run through provider-aware configuration.

Saves per-platform tool configuration to ~/.hermes/config.yaml under
the `platform_toolsets` key.
"""
```

**但这个自述低估了本段的地位。** 本段的 `_get_platform_tools` 不只是 setup 向导的读函数,而是
**全仓每一个会话决定"这次带哪些工具集"的唯一入口**。实测调用点(非测试):`cli.py:18168`、
`gateway/run.py:19520` 与 `:24318`、`gateway/platforms/api_server.py:2583/3144`、
`gateway/session.py:406/434`、`cron/scheduler.py:244`、`hermes_cli/web_routers/tools.py:58/128`、
`hermes_cli/oneshot.py:327`、`hermes_cli/memory_setup.py:494`、`hermes_cli/commands.py:1928`、
`hermes_cli/prompt_size.py:59`、`hermes_cli/web_server.py:6642`、`hermes_cli/doctor.py:333`、
`hermes_cli/kanban_db.py:8920`、`hermes_cli/cli_commands_mixin.py:762`。所以本段的每一条推断规则
都是**运行时语义**,不是"向导的默认勾选"。

例:cron 走的就是这条路。`cron/scheduler.py:243-245 @ 863e313`

```python
    try:
        from hermes_cli.tools_config import _get_platform_tools  # lazy: avoid heavy import at cron module load
        return sorted(_get_platform_tools(cfg or {}, "cron"))
```

---

## 1. 机制 A:post-setup 钩子的白名单与可脚本化入口

### 解决什么问题

有些 provider 光有 API key 不够,还要装东西:npm 装 agent-browser / Camofox、pip 装
kittentts / piper / ddgs / faster-whisper / langfuse、下载 cua-driver 二进制、跑 Spotify PKCE
向导、跑 xAI OAuth 登录。这些副作用被抽成"post-setup 钩子",键名写在 provider 行的 `post_setup`
字段上,由 `_run_post_setup(key)`(1631,不在本段)执行。

桌面 GUI 需要一个**不重新实现安装逻辑**的后端入口,于是有了
`hermes tools post-setup <key>` 这个子命令 —— GUI 把它 detach 起进程跑。

### 怎么实现

`valid_post_setup_keys()` 把所有可见 provider 声明过的 `post_setup` 收成允许集,注释直说这是给
CLI 子命令和 dashboard 端点做校验的 allowlist,免得调用方拿任意字符串驱动
`_run_post_setup`。`hermes_cli/tools_config.py:2010-2018 @ 863e313`

```python
def valid_post_setup_keys() -> Set[str]:
    """Return the set of post-setup keys declared by any visible provider.

    Collected from ``TOOL_CATEGORIES`` plus the plugin-registered web /
    image-gen / video-gen / browser providers (which can also carry a
    ``post_setup``). This is the allowlist the ``hermes tools post-setup``
    command and the dashboard post-setup endpoint validate against, so a
    caller can't drive ``_run_post_setup`` with an arbitrary key.
    """
```

收集来源是两部分:硬编码的 `TOOL_CATEGORIES`,加四个插件 builder。`hermes_cli/tools_config.py:2019-2039 @ 863e313`

```python
    keys: Set[str] = set()
    for cat in TOOL_CATEGORIES.values():
        for prov in cat.get("providers", []):
            ps = prov.get("post_setup")
            if ps:
                keys.add(ps)
    # Plugin-registered providers can declare their own post_setup hooks.
    for builder in (
        _plugin_web_search_providers,
        _plugin_image_gen_providers,
        _plugin_video_gen_providers,
        _plugin_browser_providers,
    ):
        try:
            for prov in builder():
                ps = prov.get("post_setup")
                if ps:
                    keys.add(ps)
        except Exception:  # pragma: no cover — defensive; plugins optional
            continue
    return keys
```

命令入口做三件事:缺参→退出码 2;不在 allowlist→退出码 2 且把合法键列出来;跑钩子时把任何异常
包成退出码 1。`hermes_cli/tools_config.py:2051-2069 @ 863e313`

```python
    key = getattr(args, "post_setup_key", None)
    if not key:
        _print_error("Usage: hermes tools post-setup <key>")
        return 2
    valid = valid_post_setup_keys()
    if key not in valid:
        _print_error(
            f"Unknown post-setup key: {key!r}. "
            f"Valid keys: {', '.join(sorted(valid)) or '(none)'}"
        )
        return 2
    _print_info(f"Running post-setup hook: {key}")
    try:
        _run_post_setup(key)
    except Exception as exc:  # pragma: no cover — defensive
        _print_error(f"Post-setup failed: {exc}")
        return 1
    _print_success(f"Post-setup '{key}' complete")
    return 0
```

**实测**(装了基线依赖的干净 HERMES_HOME,无插件):
`valid_post_setup_keys()` → `['agent_browser', 'browserbase', 'camofox', 'cua_driver', 'ddgs',
'faster_whisper', 'kittentts', 'langfuse', 'piper', 'spotify', 'xai_grok']`(11 个)。
`_run_post_setup` 的分支恰好覆盖这 11 个:`agent_browser`/`browserbase` 合用一个分支,其余
`camofox`/`cua_driver`/`faster_whisper`/`kittentts`/`piper`/`ddgs`/`spotify`/`langfuse`/`xai_grok`
各一个 `elif`(用 awk 扫 1631–2009 的 `post_setup_key ==` / `in` 行得到)。

### 取舍与两个洞

- **少收了 TTS 插件。** builder 元组里没有 `_plugin_tts_providers`,但 `_plugin_tts_providers`
  明确会把 schema 里的 `post_setup` 透传成 row 字段。`hermes_cli/tools_config.py:3078-3079 @ 863e313`

  ```python
        if schema.get("post_setup"):
            row["post_setup"] = schema["post_setup"]
  ```

  后果:一个注册 TTS provider 的插件,若声明 `post_setup: "my_tts_install"`,picker 会显示它、
  `_configure_provider` 会调 `_run_post_setup`,但 `hermes tools post-setup my_tts_install`
  和 dashboard 端点会拒绝(键不在 allowlist),GUI 的"Run setup"按钮因此对 TTS 插件不可用。

- **allowlist 通过 ≠ 钩子存在。** `_run_post_setup` 的 if/elif 链没有 else 兜底(最后一个分支
  `xai_grok` 结束于 2007,2010 就是下一个 `def`)。所以一个插件声明了未实现的键时,
  `run_post_setup_command` 依然打印 `Post-setup 'x' complete` 并返回 0 —— 一次**静默的假成功**。

---

## 2. 机制 B:平台枚举与"配置过就算启用"

`_get_enabled_platforms` 用凭据存在与否推断哪些平台是"已配置"的,cli 永远在列。
`hermes_cli/tools_config.py:2074-2087 @ 863e313`

```python
def _get_enabled_platforms() -> List[str]:
    """Return platform keys that are configured (have tokens or are CLI)."""
    enabled = ["cli"]
    if get_env_value("TELEGRAM_BOT_TOKEN"):
        enabled.append("telegram")
    if get_env_value("DISCORD_BOT_TOKEN"):
        enabled.append("discord")
    if get_env_value("SLACK_BOT_TOKEN"):
        enabled.append("slack")
    if get_env_value("WHATSAPP_ENABLED"):
        enabled.append("whatsapp")
    if get_env_value("QQ_APP_ID"):
        enabled.append("qqbot")
    return enabled
```

注意这是**硬编码的六个平台**,不含 `api_server`/`cron`/`acp`/`webhook`/`a2a` 等 —— 那些平台的
toolset 仍能通过 `_get_platform_tools(cfg, "<平台>")` 解析,只是不出现在 `hermes tools` 的平台
菜单里。`WHATSAPP_ENABLED` 用的是"非空即真"而不是 `is_truthy_value`,所以 `WHATSAPP_ENABLED=0`
也会把 whatsapp 算成已启用(`get_env_value` 返回字符串 `"0"`,真值)。

`_platform_toolset_summary` 只是它 + `_get_platform_tools` 的笛卡尔,注释点明测试可以显式传
platforms 来摆脱环境变量。`hermes_cli/tools_config.py:2090-2103 @ 863e313`

```python
def _platform_toolset_summary(config: dict, platforms: Optional[List[str]] = None) -> Dict[str, Set[str]]:
    """Return a summary of enabled toolsets per platform.

    When ``platforms`` is None, this uses ``_get_enabled_platforms`` to
    auto-detect platforms. Tests can pass an explicit list to avoid relying
    on environment variables.
    """
    if platforms is None:
        platforms = _get_enabled_platforms()

    summary: Dict[str, Set[str]] = {}
    for pkey in platforms:
        summary[pkey] = _get_platform_tools(config, pkey)
    return summary
```

---

## 3. 机制 C:布尔解析与 MCP 全局启用集

### `_parse_enabled_flag`:YAML 布尔的宽容解析

问题:`config.yaml` 是人手写的,`enabled: yes` / `enabled: "false"` / `enabled: 1` 都可能出现,
而 PyYAML 对 `yes`/`on` 的处理随版本变。所以自己解析。
`hermes_cli/tools_config.py:2106-2120 @ 863e313`

```python
def _parse_enabled_flag(value, default: bool = True) -> bool:
    """Parse bool-like config values used by tool/platform settings."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return default
```

**关键取舍:无法识别的值回落到 `default`(调用处传 True)。** 也就是说 `enabled: maybe` 等于开着。
这是"故障时倾向可用"的设计,代价是打错字的 disable 不生效且无告警。

### `enabled_mcp_server_names`:全仓唯一的 MCP 成员判定

设计意图写在 docstring 里:gateway/CLI 的 `_get_platform_tools` 与 cron 的按 job 解析器共用它,
保证两条路对"哪些 MCP server 算启用"的答案一致。`hermes_cli/tools_config.py:2123-2138 @ 863e313`

```python
def enabled_mcp_server_names(config: dict) -> Set[str]:
    """Names of MCP servers globally enabled in config.yaml.

    Shared by the gateway/CLI platform resolver (``_get_platform_tools``) and
    the cron per-job toolset resolver (``cron.scheduler``) so every path agrees
    on MCP membership. A server is enabled unless its config sets an explicitly
    falsey ``enabled`` (per ``_parse_enabled_flag``: false/0/no/off) — a missing
    flag or an unrecognized value is treated as enabled.
    """
    mcp_servers = (config or {}).get("mcp_servers") or {}
    return {
        str(name)
        for name, server_cfg in mcp_servers.items()
        if isinstance(server_cfg, dict)
        and _parse_enabled_flag(server_cfg.get("enabled", True), default=True)
    }
```

注意 `isinstance(server_cfg, dict)` 这一条:`mcp_servers: {foo: null}`(YAML 里 `foo:` 空值)
会让 foo **不算启用** —— 与"缺 flag 即启用"相反。这不是缺陷,但是个容易踩的不对称。

---

## 4. 机制 D:`_get_platform_tools` —— 平台工具集解析的中枢

这是本段最重的一块(2223–2518,近 300 行),值得逐规则拆。

### 4.0 输入与输出

输入 `config` + `platform`,输出**工具集名的集合**(不是工具名)。签名带一个关键字开关
`include_default_mcp_servers`。`hermes_cli/tools_config.py:2223-2230 @ 863e313`

```python
def _get_platform_tools(
    config: dict,
    platform: str,
    *,
    include_default_mcp_servers: bool = True,
) -> Set[str]:
    """Resolve which individual toolset names are enabled for a platform."""
    from toolsets import resolve_toolset, TOOLSETS
```

### 4.1 两个不同的"显式"

函数里有**两个语义不同的 explicit 判定**,这是理解全函数的钥匙。

第一个:`explicitly_configured` = 这个平台在 `platform_toolsets` 下有一个 list(哪怕是空 list)。
`hermes_cli/tools_config.py:2232-2238 @ 863e313`

```python
    platform_toolsets = config.get("platform_toolsets") or {}
    toolset_names = platform_toolsets.get(platform)
    # Track whether the user explicitly saved a toolset list for this platform
    # (vs. falling back to the platform default). An explicit composite (e.g.
    # ``hermes-discord``) is an opt-in to the platform's native default-off
    # toolsets — see _exempt_explicit_platform_native (#35527).
    explicitly_configured = isinstance(toolset_names, list)
```

缺省回落:平台在 `PLATFORMS` 注册表里就用它的 `default_toolset`,否则(插件平台)按
`hermes-<platform>` 拼名。`hermes_cli/tools_config.py:2240-2247 @ 863e313`

```python
    if toolset_names is None or not isinstance(toolset_names, list):
        plat_info = PLATFORMS.get(platform)
        if plat_info:
            default_ts = plat_info["default_toolset"]
        else:
            # Plugin platform — derive toolset name from platform key
            default_ts = f"hermes-{platform}"
        toolset_names = [default_ts]
```

一个真实踩过的坑:YAML 会把裸数字键(如 MCP server 名 `12306`)解析成 int,后面 `sorted()`
混类型会炸,所以先统一 str。`hermes_cli/tools_config.py:2249-2251 @ 863e313`

```python
    # YAML may parse bare numeric names (e.g. ``12306:``) as int.
    # Normalise to str so downstream sorted() never mixes types.
    toolset_names = [str(ts) for ts in toolset_names]
```

第二个:`has_explicit_config` = 保存的列表里**直接出现了某个可配置工具集键**。
`hermes_cli/tools_config.py:2253-2264 @ 863e313`

```python
    configurable_keys = {ts_key for ts_key, _, _ in CONFIGURABLE_TOOLSETS}
    plugin_ts_keys = _get_plugin_toolset_keys()
    platform_default_keys = {p["default_toolset"] for p in PLATFORMS.values()}

    # If the saved list contains any configurable keys directly, the user
    # has explicitly configured this platform — use direct membership.
    # This avoids the subset-inference bug where composite toolsets like
    # "hermes-cli" (which include all _HERMES_CORE_TOOLS) cause disabled
    # toolsets to re-appear as enabled.
    has_explicit_config = any(ts in configurable_keys for ts in toolset_names)
```

**两者不等价**:`platform_toolsets: {cli: []}` 或 `{cli: [hermes-cli]}` 时
`explicitly_configured=True` 而 `has_explicit_config=False`。后面 4.4 的 x_search 缺陷就是这个
缝里长出来的。

### 4.2 分支一:直接成员制 + 复合工具集补齐

用户明确列了可配置键时,以直接成员为准并按平台过滤。
`hermes_cli/tools_config.py:2264-2268 @ 863e313`

```python
    if has_explicit_config:
        enabled_toolsets = {
            ts for ts in toolset_names
            if ts in configurable_keys and _toolset_allowed_for_platform(ts, platform)
        }
```

混合配置(`[hermes-cli, spotify]`)如果只取直接成员,复合名会被丢掉,会话就只剩 spotify 没有原生
工具。所以把复合名展开成工具全集,再反查哪些可配置工具集是它的子集。
`hermes_cli/tools_config.py:2269-2282 @ 863e313`

```python
        # Mixed config: composite toolset alongside configurables (e.g.
        # ``[hermes-cli, spotify]`` after enabling Spotify via ``hermes
        # tools``). Without expansion the composite name is silently dropped,
        # leaving sessions with only the configurable opt-ins and no native
        # tools. Mirror the else-branch's subset inference, but apply
        # _DEFAULT_OFF_TOOLSETS only to the implicit expansion — anything the
        # user explicitly listed (e.g. ``spotify``) must survive.
        composite_tools = set()
        for ts_name in toolset_names:
            if ts_name in configurable_keys or ts_name in plugin_ts_keys:
                continue
            if ts_name not in TOOLSETS:
                continue
            composite_tools.update(resolve_toolset(ts_name))
```

### 4.3 `include_registry=False`:反查必须比"静态成员",不能比"运行时成员"(#49622)

这是本函数最精妙、也最容易重实现错的一条。

**场景**:`delegation` 工具集在 `toolsets.py` 里静态写着 `[delegate_task]`;某个插件/桌面覆盖层
在运行时又往 `delegation` 里注册了一个 `delegate_cli`。平台复合 `hermes-cli` 是**静态枚举工具名**
的,它当然没列 `delegate_cli`。如果反查时拿"合并后的运行时成员"去做子集判断,
`{delegate_task, delegate_cli} ⊄ hermes-cli 的工具集` → 整个 `delegation` 被判为"未启用"。
一个插件装上去,反而把无关工具集整片关掉。

修法:反查一律用 `resolve_toolset(..., include_registry=False)`。
`hermes_cli/tools_config.py:2286-2295 @ 863e313`

```python
            for ts_key, _, _ in CONFIGURABLE_TOOLSETS:
                if not _toolset_allowed_for_platform(ts_key, platform):
                    continue
                # Compare the toolset's STATIC membership: a tool registered
                # into a toolset (e.g. delegate_cli -> delegation, desktop-only
                # read_terminal -> terminal) that the composite never listed must
                # not drop the whole toolset. See issue #49622.
                ts_tools = set(resolve_toolset(ts_key, include_registry=False))
                if ts_tools and ts_tools.issubset(composite_tools):
                    expanded.add(ts_key)
```

同一条规则在 else 分支重复一次(2326)、在非可配置回收里再重复一次(2404)、在
`_enable_recently_shipped_toolsets` 里第四次(2215)。`resolve_toolset` 的参数文档也点名了这个
调用方。`toolsets.py:730-737 @ 863e313`

```python
        include_registry (bool): When True (default), include tools that
            plugins/overlays registered into a toolset. When False, resolve only
            the static ``TOOLSETS`` definition (includes are still resolved, but
            statically). Platform reverse-mapping uses False so a registry-added
            tool cannot drop the whole toolset from inference (see #49622 and
            ``_get_platform_tools``).
```

注意 `ts_tools and ...` 这个前置:空工具集(`set() ⊆ 任何集合`)否则会被永远判为启用。

### 4.4 `_DEFAULT_OFF_TOOLSETS` 与它的四个豁免

默认关闭集写在 156 行。`hermes_cli/tools_config.py:156 @ 863e313`

```python
_DEFAULT_OFF_TOOLSETS = {"homeassistant", "spotify", "discord", "discord_admin", "video", "video_gen", "x_search", "a2a"}
```

**豁免 1(平台自名)**:平台名与某默认关闭工具集同名时(如 `homeassistant` 平台 + `homeassistant`
工具集),保留;但平台受限工具集不吃这个后门(discord 平台上的 `discord` 工具集仍默认关)。
`hermes_cli/tools_config.py:2348-2354 @ 863e313`

```python
        # Legacy safety: if the platform's own name matches a default-off
        # toolset (e.g. `homeassistant` platform + `homeassistant` toolset),
        # keep that toolset enabled on first install.  Skip this dodge for
        # platform-restricted toolsets — those are always opt-in even on
        # their own platform (e.g. `discord` + `discord` should stay OFF).
        if platform in default_off and platform not in _TOOLSET_PLATFORM_RESTRICTIONS:
            default_off.remove(platform)
```

**豁免 2(HASS_TOKEN)**:配了 Home Assistant token 就是显式 opt-in,别再被默认关闭剥掉;
注释还留了事故记录 —— #14798 让 cron 遵守按平台工具配置之后,Norbert 的 HA 定时任务集体失效。
`hermes_cli/tools_config.py:2355-2363 @ 863e313`

```python
        # Home Assistant is already runtime-gated by its check_fn (requires
        # HASS_TOKEN to register any tools). When a user has configured
        # HASS_TOKEN, they've explicitly opted in — don't also strip it via
        # _DEFAULT_OFF_TOOLSETS, which would silently drop HA from platforms
        # (e.g. cron) that run through _get_platform_tools without an
        # explicit saved toolset list. Without this, Norbert's HA cron jobs
        # regressed after #14798 made cron honor per-platform tool config.
        if "homeassistant" in default_off and _homeassistant_credentials_present():
            default_off.remove("homeassistant")
```

凭据探测走 profile 感知的 secret_scope,吞掉一切异常。`hermes_cli/tools_config.py:200-207 @ 863e313`

```python
def _homeassistant_credentials_present() -> bool:
    """Return whether the active profile has a Home Assistant token."""
    try:
        from agent.secret_scope import get_secret

        return bool((get_secret("HASS_TOKEN", "") or "").strip())
    except Exception:
        return False
```

**豁免 3(x_search 自动开启)**:`x_search` 是自成一集的单工具集,不在平台复合里,子集反查永远
抓不到它,所以要显式注入。注释明确写了"只在用户尚未保存显式列表时触发"。
`hermes_cli/tools_config.py:2330-2345 @ 863e313`

```python
        # Auto-enable ``x_search`` when xAI credentials are configured.
        # Unlike ``homeassistant`` (whose ``ha_*`` tools live inside the
        # platform composite and thus pass the subset check above),
        # ``x_search`` is its own one-tool toolset that the composite does
        # NOT include, so the subset loop never picks it up. Inject it
        # directly here, mirroring the HASS_TOKEN → ``homeassistant`` rule
        # below: once you have working creds, you don't have to also click
        # through ``hermes tools`` to flip the toolset on. Only fires when
        # the user has not yet saved an explicit toolset list — once they
        # do, the saved list is authoritative.
        x_search_auto_enabled = (
            _toolset_allowed_for_platform("x_search", platform)
            and _xai_credentials_present()
        )
        if x_search_auto_enabled:
            enabled_toolsets.add("x_search")
```

再对称地把它从 default_off 里摘掉,不然刚加的又被减掉。`hermes_cli/tools_config.py:2364-2368 @ 863e313`

```python
        # Symmetric carve-out for x_search auto-enable (see the inject
        # block above). Without this, the default_off subtraction would
        # strip the entry we just added.
        if x_search_auto_enabled and "x_search" in default_off:
            default_off.remove("x_search")
```

凭据探测:先试 OAuth token 存储(读不到会抛 `AuthError`,已核对
`hermes_cli/auth.py:4479-4485` 在无凭据时 raise),再试 `XAI_API_KEY`。
`hermes_cli/tools_config.py:179-197 @ 863e313`

```python
    try:
        from hermes_cli.auth import _read_xai_oauth_tokens

        _read_xai_oauth_tokens()
        return True
    except Exception:
        pass
    try:
        from tools.xai_http import get_env_value as _xai_get_env_value

        if str(_xai_get_env_value("XAI_API_KEY") or "").strip():
            return True
    except Exception:
        pass
    try:
        from agent.secret_scope import get_secret
    except ImportError:  # pragma: no cover — secret_scope is in-repo
        return bool(str(os.environ.get("XAI_API_KEY") or "").strip())
    return bool(str(get_secret("XAI_API_KEY") or "").strip())
```

> **可疑缺陷 D-1(已实测复现)**:注释说的"保存了显式列表就不再触发"用的是 `has_explicit_config`
> 的语义,而不是 `explicitly_configured`。用户在 `hermes tools` 里**取消勾选全部工具集**,
> `_save_platform_tools` 写出 `platform_toolsets: {cli: []}`;下次解析走 else 分支,
> x_search 被注入并保留。实测:
> ```
> $ XAI_API_KEY=dummy  _get_platform_tools({'platform_toolsets': {'cli': []}}, 'cli')
> -> ['kanban', 'x_search']
> ```
> 同一个函数在 2445 处**明确定义并尊重**了"显式空选"契约(见 4.8),此处却绕过了它。
> 怎么踩到:配过 `XAI_API_KEY` 或做过 xAI OAuth 的用户,在某个平台上清空所有工具集,期望零工具,
> 实际仍带着 `x_search`(以及 `kanban`,见 4.6)。

**豁免 4(平台原生工具集,#35527)**:`_exempt_explicit_platform_native` 只在
`explicitly_configured` 时生效,把"受限到本平台"的默认关闭工具集从 default_off 里摘掉。
`hermes_cli/tools_config.py:2141-2160 @ 863e313`

```python
def _exempt_explicit_platform_native(
    default_off: Set[str], platform: str, *, explicitly_configured: bool
) -> None:
    """Let platform-native default-off toolsets through on explicit config.

    Toolsets that are both in ``_DEFAULT_OFF_TOOLSETS`` and restricted to
    ``platform`` via ``_TOOLSET_PLATFORM_RESTRICTIONS`` (currently
    ``discord``/``discord_admin`` on the discord platform) are the platform's
    own native tools. They are kept off for *unconfigured* platforms (security
    opt-in), but once a user explicitly saves a toolset list for the platform
    the composite they chose (e.g. ``hermes-discord``, which contains those
    tools) is an opt-in — stripping them silently defeats the explicit
    configuration (#35527). Mutates ``default_off`` in place.
    """
    if not explicitly_configured:
        return
    for ts in list(default_off):
        allowed = _TOOLSET_PLATFORM_RESTRICTIONS.get(ts)
        if allowed is not None and platform in allowed:
            default_off.discard(ts)
```

**实测验证 #35527**:
```
discord 显式 ['hermes-discord','file'] -> [..., 'discord', 'discord_admin', 'file', ...]
discord 未配置 {}                       -> [...] 无 discord / discord_admin
telegram 显式 ['hermes-telegram','file']-> [...] 无 discord / discord_admin
```
最后一条同时验证了 `_toolset_allowed_for_platform` 的平台限制。
`hermes_cli/tools_config.py:216-228 @ 863e313`

```python
_TOOLSET_PLATFORM_RESTRICTIONS: Dict[str, Set[str]] = {
    "discord": {"discord"},
    "discord_admin": {"discord"},
}


def _toolset_allowed_for_platform(ts_key: str, platform: str) -> bool:
    """Return True if ``ts_key`` is configurable on ``platform``.

    Toolsets without a restriction entry are allowed everywhere (the default).
    """
    allowed = _TOOLSET_PLATFORM_RESTRICTIONS.get(ts_key)
    return allowed is None or platform in allowed
```

**分支不对称(设计如此)**:has_explicit_config 分支里 `default_off` **只作用于隐式展开**
(2297–2307),用户直接列出的键(如 `spotify`)不受减法影响;else 分支里 `default_off` 作用于整个
结果(2372)。

### 4.5 新工具集回填:`_RECENTLY_SHIPPED_TOOLSETS`

**解决什么问题**:保存一次 `hermes tools` 就把平台的复合名冻成一份显式清单,**之后再也没有任何
代码往这份清单里加东西**。于是新版本新增的工具集,对"从没点过 picker、还留在 `[hermes-cli]`"
的用户会自动继承,对"点过一次 picker"的用户永远缺席。这条常量就是恢复这个对等性的补丁。
`hermes_cli/tools_config.py:2163-2185 @ 863e313`

```python
#: Toolsets young enough that absence from a saved ``platform_toolsets`` list
#: means "never offered" rather than "declined".
#:
#: Saving ``hermes tools`` (or one toggle in the desktop Toolsets UI) replaces
#: a platform's composite with a frozen explicit list, and nothing ever adds to
#: that list — so a toolset shipped afterwards stays off forever for anyone who
#: has touched the picker, while everyone still on ``[hermes-cli]`` inherits it
#: on upgrade. Listing it here restores that parity.
#:
#: MUST ship in the same release as the toolset it names, and be emptied in the
#: next one. The inference only holds while no released build has put the
#: toolset on a checklist: once one has, a user who unchecks it writes a config
#: byte-identical to one saved before the toolset existed (the record below is
#: only written from that point on), and this rule turns their opt-out back on.
#: Landing late — or leaving an entry here for a second release — converts a
#: back-fill into a stuck checkbox.
#:
#: Not gated on a Nous sign-in here: the six ``bfl_flux3_*`` tools carry
#: ``check_fn=check_bfl_requirements``, so an enabled toolset still ships zero
#: schemas to a user with no Nous credential — the same split Home Assistant
#: uses. Probing the portal from this path would put a network call on every
#: CLI start, gateway session and cron tick.
_RECENTLY_SHIPPED_TOOLSETS = frozenset({"bfl"})
```

实现:先读"这个平台的 checklist 曾经展示过哪些内建工具集"这本账(`known_builtin_toolsets`),
在账上=主动拒绝,跳过。`hermes_cli/tools_config.py:2198-2205 @ 863e313`

```python
    from toolsets import resolve_toolset

    offered = (config.get("known_builtin_toolsets") or {}).get(platform)
    declined = {str(ts) for ts in offered} if isinstance(offered, list) else set()

    plat_info = PLATFORMS.get(platform)
    default_ts = plat_info["default_toolset"] if plat_info else f"hermes-{platform}"
    composite_tools = None
```

再加一道"对等性"闸:**只在"如果继续留在复合名上也会被启用"的平台上回填**,窄复合
(hermes-acp / hermes-webhook)保持窄。`hermes_cli/tools_config.py:2207-2220 @ 863e313`

```python
    for ts_key in sorted(_RECENTLY_SHIPPED_TOOLSETS):
        if ts_key in enabled_toolsets or ts_key in declined:
            continue
        if not _toolset_allowed_for_platform(ts_key, platform):
            continue
        # Parity is the whole justification, so only enable the toolset where
        # staying on the composite would have enabled it anyway. Deliberately
        # narrow composites (hermes-acp, hermes-webhook) stay narrow.
        ts_tools = set(resolve_toolset(ts_key, include_registry=False))
        if composite_tools is None:
            composite_tools = set(resolve_toolset(default_ts))
        if not ts_tools or not ts_tools.issubset(composite_tools):
            continue
        enabled_toolsets.add(ts_key)
```

调用点只有 has_explicit_config 分支一处(else 分支本来就走复合推断,不需要回填)。
`hermes_cli/tools_config.py:2309 @ 863e313`

```python
        _enable_recently_shipped_toolsets(enabled_toolsets, config, platform)
```

三条"取消途径"仍然有效,docstring 逐条列了。`hermes_cli/tools_config.py:2191-2196 @ 863e313`

```python
    """Turn on toolsets that shipped after this platform's saved list.

    Either way of saying no outlives this: unchecking in ``hermes tools``
    records the toolset in ``known_builtin_toolsets`` so it reads as declined
    from then on, and ``agent.disabled_toolsets`` is subtracted after every
    rule in :func:`_get_platform_tools`. Mutates ``enabled_toolsets`` in place.
```

**实测**:`{'platform_toolsets': {'cli': ['file','terminal']}}` → `['bfl','file','kanban','terminal']`
—— bfl 被回填,kanban 被回收(4.6)。

### 4.6 非可配置工具集回收(kanban 从哪来)

`hermes tools` 的 checklist 只列 `CONFIGURABLE_TOOLSETS` + 插件工具集。平台复合里还有一批**不在
checklist 上**的工具集(kanban、feishu_doc、feishu_drive、discord 平台原生等),它们既不会被用户
勾上,也就不会出现在保存的列表里。所以要在**两条分支之后**统一回收 —— 注释点名"必须在两个分支
都跑,否则保存一次就把它们悄悄丢了"。`hermes_cli/tools_config.py:2374-2391 @ 863e313`

```python
    # Recover non-configurable platform toolsets (e.g. discord, feishu_doc,
    # feishu_drive).  These are part of the platform's default composite but
    # absent from CONFIGURABLE_TOOLSETS, so they can't appear in the TUI
    # checklist or in a user-saved config.  Must run in BOTH branches —
    # otherwise saving via `hermes tools` (which flips has_explicit_config
    # to True) silently drops them.
    _plat_info = PLATFORMS.get(platform)
    _default_ts = _plat_info["default_toolset"] if _plat_info else f"hermes-{platform}"
    platform_tool_universe = set(resolve_toolset(_default_ts))
    configurable_tool_universe = set()
    for ck in configurable_keys:
        configurable_tool_universe.update(resolve_toolset(ck))
    claimed = set()
    for ts_key in enabled_toolsets:
        claimed.update(resolve_toolset(ts_key))
    skip = configurable_keys | plugin_ts_keys | platform_default_keys
    skip |= {k for k in TOOLSETS if k.startswith("hermes-")}
    skip |= set(_DEFAULT_OFF_TOOLSETS) - {platform}
```

回收循环有四道过滤:跳过 skip 集、跳过复合(有 includes)、跳过 posture 工具集(如 `coding`,
那是 `agent/coding_context.py` 的会话级选择而非平台能力)、按静态成员判子集。
`hermes_cli/tools_config.py:2392-2411 @ 863e313`

```python
    for ts_key, ts_def in TOOLSETS.items():
        if ts_key in skip:
            continue
        if ts_def.get("includes"):
            continue
        # Posture toolsets (e.g. ``coding``) are session-level selections made
        # by agent/coding_context.py — not per-platform capabilities to recover.
        if ts_def.get("posture"):
            continue
        # Static membership (see #49622): a registry-added tool absent from the
        # platform composite must not block recovery of a non-configurable
        # toolset whose authored tools the composite does list.
        ts_tools = set(resolve_toolset(ts_key, include_registry=False))
        if not ts_tools or not ts_tools.issubset(platform_tool_universe):
            continue
        if ts_tools.issubset(configurable_tool_universe):
            continue
        if not ts_tools.issubset(claimed):
            enabled_toolsets.add(ts_key)
            claimed.update(ts_tools)
```

`claimed` 的作用是**去重**:一个工具已经被某个已启用工具集覆盖,就不再为它单独回收一个工具集。
`skip |= set(_DEFAULT_OFF_TOOLSETS) - {platform}` 保证 a2a 之类默认关的插件工具集不会从这条路
偷偷回来(除非平台就叫 a2a)。

这条规则在 `_checklist_toolset_keys` 的 docstring 里有配套说明:UI 打印增删 diff 时必须把范围
限制在 checklist 真正展示过的键上,否则会出现"- kanban"这种用户根本没勾过的假删除。
`hermes_cli/tools_config.py:281-296 @ 863e313`

```python
def _checklist_toolset_keys(platform: str) -> Set[str]:
    """Return the toolset keys the ``hermes tools`` checklist actually offers
    for ``platform``.

    This mirrors exactly what ``_prompt_toolset_checklist`` renders:
    ``_get_effective_configurable_toolsets()`` (built-in + plugin toolsets),
    filtered by ``_toolset_allowed_for_platform``. The checklist's returned
    selection can therefore only ever be a subset of this universe.

    Non-configurable toolsets that ``_get_platform_tools`` resolves at read
    time — ``kanban`` and other check_fn-gated toolsets, recovered platform
    composites, MCP server names — are NOT in this set because the checklist
    never shows them. Use this to scope the added/removed diff the UI prints,
    so ``hermes tools`` never claims to add or remove a toolset the user was
    never given a checkbox for. The underlying config is unaffected — those
    entries are preserved by ``_save_platform_tools`` regardless.
    """
```

### 4.7 插件工具集的三态

插件工具集不是二值而是三值:**显式列出 = 开;在默认关集里 = 关;未在"已知"账上 = 默认开;
在账上但不在配置里 = 用户关掉了**。`hermes_cli/tools_config.py:2413-2433 @ 863e313`

```python
    # Plugin toolsets: enabled by default unless explicitly disabled, or
    # unless the toolset is in _DEFAULT_OFF_TOOLSETS (e.g. spotify —
    # shipped as a bundled plugin but user must opt in via `hermes tools`
    # so we don't ship 7 Spotify tool schemas to users who don't use it).
    # A plugin toolset is "known" for a platform once `hermes tools`
    # has been saved for that platform (tracked via known_plugin_toolsets).
    # Unknown plugins default to enabled; known-but-absent = disabled.
    if plugin_ts_keys:
        known_map = config.get("known_plugin_toolsets", {}) or {}
        known_for_platform = set(known_map.get(platform, []) or [])
        for pts in plugin_ts_keys:
            if pts in toolset_names:
                # Explicitly listed in config — enabled
                enabled_toolsets.add(pts)
            elif pts in _DEFAULT_OFF_TOOLSETS:
                # Opt-in plugin toolset — stay off until user picks it
                continue
            elif pts not in known_for_platform:
                # New plugin not yet seen by hermes tools — default enabled
                enabled_toolsets.add(pts)
            # else: known but not in config = user disabled it
```

这套"账本区分未知与拒绝"的模式,与 4.5 的 `known_builtin_toolsets` 是同一套设计,只是一个用于
插件、一个用于内建。

### 4.8 context engine 的运行时工具

上下文引擎(默认 `compressor`)的工具是运行时提供的,不在任何静态复合里。非默认引擎要保留它的
恢复/状态工具,但**必须尊重"显式空选"契约**。`hermes_cli/tools_config.py:2435-2451 @ 863e313`

```python
    # Context-engine tools are runtime-provided by the active engine, so they
    # are not part of any static platform composite. When a non-default engine
    # is selected, keep its recovery/status tools available even after a user
    # saves an explicit platform toolset list. Preserve the explicit empty-list
    # contract: selecting no configurable tools means no context-engine tools
    # either unless the user adds ``context_engine`` manually later.
    context_cfg = config.get("context") or {}
    if not isinstance(context_cfg, dict):
        context_cfg = {}
    context_engine_name = str(context_cfg.get("engine") or "compressor").strip().lower()
    explicit_empty_selection = (
        platform in platform_toolsets
        and isinstance(platform_toolsets.get(platform), list)
        and not toolset_names
    )
    if context_engine_name and context_engine_name != "compressor" and not explicit_empty_selection:
        enabled_toolsets.add("context_engine")
```

这段代码是全函数唯一显式定义 `explicit_empty_selection` 的地方 —— 也正是 D-1 缺陷的对照组。

### 4.9 MCP:直通、allowlist 与 `no_mcp` 哨兵

先算"既不是可配置键、也不是插件键、也不是平台默认名"的直通条目 —— 自定义工具集名与 MCP server
名都落在这里。`hermes_cli/tools_config.py:2453-2461 @ 863e313`

```python
    # Preserve any explicit non-configurable toolset entries (for example,
    # custom toolsets or MCP server names saved in platform_toolsets).
    explicit_passthrough = {
        ts
        for ts in toolset_names
        if ts not in configurable_keys
        and ts not in plugin_ts_keys
        and ts not in platform_default_keys
    }
```

规则:默认所有全局启用的 MCP server 对所有平台可见;平台显式列了 server 名就当 allowlist;
`no_mcp` 哨兵关掉全部。`hermes_cli/tools_config.py:2463-2481 @ 863e313`

```python
    # MCP servers are expected to be available on all platforms by default.
    # If the platform explicitly lists one or more MCP server names, treat that
    # as an allowlist. Otherwise include every globally enabled MCP server.
    # Special sentinel: "no_mcp" in the toolset list disables all MCP servers.
    enabled_mcp_servers = enabled_mcp_server_names(config)
    # Allow "no_mcp" sentinel to opt out of all MCP servers for this platform
    if "no_mcp" in toolset_names:
        explicit_mcp_servers = set()
        enabled_toolsets.update(explicit_passthrough - enabled_mcp_servers - {"no_mcp"})
    else:
        explicit_mcp_servers = explicit_passthrough & enabled_mcp_servers
        enabled_toolsets.update(explicit_passthrough - enabled_mcp_servers)
    if include_default_mcp_servers:
        if explicit_mcp_servers or "no_mcp" in toolset_names:
            enabled_toolsets.update(explicit_mcp_servers)
        else:
            enabled_toolsets.update(enabled_mcp_servers)
    else:
        enabled_toolsets.update(explicit_mcp_servers)
```

cron 用一个镜像函数复刻了完全相同的三条语义,docstring 里逐条写明。
`cron/scheduler.py:197-205 @ 863e313`

```python
    ``mcp_*`` call with "Unknown tool". This restores parity with
    ``_get_platform_tools`` MCP semantics:

      * ``no_mcp`` sentinel present  -> no MCP servers (sentinel stripped)
      * one or more MCP server names already listed -> treat as an allowlist,
        add nothing further (the user named exactly the servers they want)
      * otherwise -> union in every globally-enabled MCP server
    """
```

**实测**(`include_default_mcp_servers=True`):
```
cfg = {'platform_toolsets': {'cli': ['file','other']},
       'mcp_servers': {'other': {'enabled': True}, 'third': {}}}
-> ['bfl','file','kanban','other']            # allowlist 生效,third 被排除
cfg = {'platform_toolsets': {'cli': ['file','no_mcp']}, 'mcp_servers': {'other': {'enabled': True}}}
-> ['bfl','file','kanban']                    # 哨兵生效且自身被剥掉
```

> **可疑缺陷 D-2(已实测复现)**:被全局禁用的 MCP server 名一旦写进 `platform_toolsets`,
> 既**穿透了全局禁用**,又**废掉了 allowlist**。
> ```
> cfg = {'platform_toolsets': {'cli': ['file','mysrv']},
>        'mcp_servers': {'mysrv': {'enabled': False}, 'other': {'enabled': True}}}
> -> ['bfl','file','kanban','mysrv','other']
> ```
> 机理:`mysrv` 不在 `enabled_mcp_servers` 里,于是 2474 行把它当作"非 MCP 的直通工具集名"
> 塞进结果;同时 `explicit_mcp_servers` 为空 → 2478 行走"没有 allowlist"分支 → 把 `other`
> 也加进来。怎么踩到:用户在 `mcp_servers` 里把某个 server `enabled: false` 临时下线,但那个
> server 名早已被 `_save_platform_tools` 作为 `preserved_entries` 留在 `platform_toolsets` 里
> (见 5 节)——全局开关看上去失效了,而且平台的 allowlist 意图同时被破坏。

### 4.10 `agent.disabled_toolsets` 是最后一道减法

`hermes_cli/tools_config.py:2483-2491 @ 863e313`

```python
    # Honor agent.disabled_toolsets from config.yaml — allows users to
    # globally suppress specific toolsets (e.g. "memory") across all
    # platforms without per-platform toolset configuration.  This runs
    # last so it overrides everything above.
    agent_cfg = config.get("agent") or {}
    disabled_toolsets = agent_cfg.get("disabled_toolsets") or []
    if disabled_toolsets:
        disabled_set = {str(ts) for ts in disabled_toolsets}
        enabled_toolsets -= disabled_set
```

实测 `{'agent': {'disabled_toolsets': ['file']}, 'platform_toolsets': {'cli': ['file','terminal']}}`
→ `['bfl','kanban','terminal']`:显式勾选也拦不住它。这正是 `_save_platform_tools` 要做对账
(见 5 节)的原因。

### 4.11 #38798:全无效配置的一次性运行时告警

配置里全是无效工具集名(如迁移把 `hermes-cli` 写成了 `hermes`)时,`resolve_toolset` 对每个名字
都返回 `[]`,平台**静默地**没有任何原生工具。这里在解析点补一次告警。
`hermes_cli/tools_config.py:2493-2516 @ 863e313`

```python
    # #38798: if this platform was explicitly configured but every toolset name
    # is invalid (e.g. a migration or hand-edit left `hermes` instead of
    # `hermes-cli`), resolve_toolset() returns [] for each and the platform ends
    # up with no native tools — silently, with no error. Surface it at the point
    # tools are resolved for a session so an already-corrupted config is caught
    # at runtime, not only during the next `hermes update`/`hermes doctor`.
    _explicit = platform_toolsets.get(platform)
    if isinstance(_explicit, list) and _explicit:
        from toolsets import validate_toolset

        _named = [str(t) for t in _explicit if isinstance(t, str) and t]
        if (
            _named
            and not any(validate_toolset(t) for t in _named)
            and platform not in _warned_invalid_platform_toolsets
        ):
            _warned_invalid_platform_toolsets.add(platform)
            logger.warning(
                "platform '%s' has no valid toolsets configured (unknown "
                "name(s): %s) - tools will be unavailable. Run `hermes tools` "
                "to reconfigure. See issue #38798.",
                platform,
                ", ".join(_named),
            )
```

去重靠一个模块级集合,注释说明是"每平台一次"而不是"每次解析一次"。
`hermes_cli/tools_config.py:73-76 @ 863e313`

```python
# Platforms already warned about an all-invalid platform_toolsets list, so the
# runtime check in _get_platform_tools warns once per platform instead of on
# every tool resolution for a persistently-corrupt config (#38798).
_warned_invalid_platform_toolsets: Set[str] = set()
```

注意告警条件是 `not any(...)`(全部无效才报),部分无效不报 —— 有测试钉住这个边界
(`tests/hermes_cli/test_tools_config.py:63` `test_partially_valid_platform_toolsets_no_runtime_warning`)。
另外这是**进程级**去重集合,长驻的 gateway 进程只会看到一次;而 `_warned_invalid_platform_toolsets`
从不清空,测试之间需要手动重置。

---

## 5. 机制 E:`_save_platform_tools` —— 写回、两本账、与全局禁用对账

### 保护 MCP 名不被 picker 清掉

`hermes_cli/tools_config.py:2521-2535 @ 863e313`

```python
def _save_platform_tools(config: dict, platform: str, enabled_toolset_keys: Set[str]):
    """Save the selected toolset keys for a platform to config.

    Preserves any non-configurable toolset entries (like MCP server names)
    that were already in the config for this platform.
    """
    config.setdefault("platform_toolsets", {})

    # Drop platform-scoped toolsets that don't apply here.  Prevents the
    # "Configure all platforms" checklist (or a hand-edited config.yaml)
    # from turning on, say, the `discord` toolset for Telegram.
    enabled_toolset_keys = {
        ts for ts in enabled_toolset_keys
        if _toolset_allowed_for_platform(ts, platform)
    }
```

平台默认复合名也必须排除,否则下次读会覆盖用户的取消勾选。
`hermes_cli/tools_config.py:2542-2558 @ 863e313`

```python
    # Also exclude platform default toolsets (hermes-cli, hermes-telegram, etc.)
    # These are "super" toolsets that resolve to ALL tools, so preserving them
    # would silently override the user's unchecked selections on the next read.
    platform_default_keys = {p["default_toolset"] for p in PLATFORMS.values()}

    # Get existing toolsets for this platform
    existing_toolsets = cfg_get(config, "platform_toolsets", platform, default=[])
    if not isinstance(existing_toolsets, list):
        existing_toolsets = []
    existing_toolsets = [str(ts) for ts in existing_toolsets]

    # Preserve any entries that are NOT configurable toolsets and NOT platform
    # defaults (i.e. only MCP server names should be preserved)
    preserved_entries = {
        entry for entry in existing_toolsets
        if entry not in configurable_keys and entry not in platform_default_keys
    }
```

`no_mcp` 是唯一被主动丢弃的保留项 —— 因为 picker 没有它的复选框,不清掉用户就永远回不去。
`hermes_cli/tools_config.py:2559-2566 @ 863e313`

```python
    # Opening `hermes tools` is the user's opt-in to reconfigure tools, so treat
    # saving from the picker as consent to clear the "no_mcp" sentinel. The
    # picker has no checkbox for no_mcp, so without this users who once set it
    # by hand could never re-enable MCP servers through the UI.
    preserved_entries.discard("no_mcp")

    # Merge preserved entries with new enabled toolsets
    config["platform_toolsets"][platform] = sorted(enabled_toolset_keys | preserved_entries)
```

这条 `preserved_entries` 规则正是 D-2 的另一半:被全局禁用的 MCP server 名会一直被保留在
`platform_toolsets` 里。

### 两本"已知"账

插件账:`hermes_cli/tools_config.py:2568-2575 @ 863e313`

```python
    # Track which plugin toolsets are "known" for this platform so we can
    # distinguish "new plugin, default enabled" from "user disabled it".
    if plugin_keys:
        # setdefault does NOT replace a present-but-null key ("known_plugin_toolsets:"
        # in config.yaml parses to None) — normalize before indexing into it.
        if not isinstance(config.get("known_plugin_toolsets"), dict):
            config["known_plugin_toolsets"] = {}
        config["known_plugin_toolsets"][platform] = sorted(plugin_keys)
```

内建账:`hermes_cli/tools_config.py:2577-2586 @ 863e313`

```python
    # Same record for builtin toolsets: which ones this platform's checklist
    # has actually put in front of the user. Without it, a toolset the user
    # unchecks here is indistinguishable from one that shipped after they
    # saved, and _enable_recently_shipped_toolsets would turn it straight back
    # on. Recorded from the full catalog, since that is what the picker showed.
    if not isinstance(config.get("known_builtin_toolsets"), dict):
        config["known_builtin_toolsets"][platform] = sorted(
```

> **文档-代码出入 C-1**:注释说"Recorded from the full catalog, since that is what the picker
> showed" —— 但 picker(`_prompt_toolset_checklist`)展示的是
> `_get_effective_configurable_toolsets()` **再过滤掉平台不允许的和 `_CONFIG_ONLY_TOOLSETS`**
> (2742–2746),而这里记录的是**未过滤的裸 `CONFIGURABLE_TOOLSETS`**,且不含插件工具集。
> 于是账本会把 `stt`(config-only,从不上 checklist)以及非 discord 平台上的
> `discord`/`discord_admin` 记成"已展示给用户"。后果目前是潜伏的:若将来
> `_RECENTLY_SHIPPED_TOOLSETS` 里放进一个 config-only 或平台受限的工具集,回填会对已保存用户
> 静默失效。

### 与 `agent.disabled_toolsets` 对账(#49995)

**解决什么问题**:`_get_platform_tools` 把 `agent.disabled_toolsets` 当最后一道减法,所以
picker 里勾上一个在该列表里的工具集会"保存成功但永远不生效"。Blank Slate 安装预置了约 27 个
工具集在这个列表里,桌面 Toolsets UI 因此大面积失灵。`hermes_cli/tools_config.py:2588-2600 @ 863e313`

```python
    # Reconcile with agent.disabled_toolsets. _get_platform_tools() applies
    # that list as a final override AFTER reading platform_toolsets.<platform>,
    # so a toolset listed there stays permanently OFF no matter what this
    # function writes — the toggle "saves" but silently can't ever take
    # effect. Blank Slate installs pre-populate this list with ~27 toolsets,
    # making most of the desktop Toolsets UI unusable for re-enabling
    # anything (issue #49995).
    #
    # Only toolsets the user just explicitly enabled FOR THIS PLATFORM are
    # cleared from the global disabled list — toolsets the user did not
    # touch (still unchecked) or that remain disabled on other platforms
    # are left alone, so agent.disabled_toolsets keeps working as a
    # cross-platform suppression list for anything not actively re-enabled.
```

`hermes_cli/tools_config.py:2601-2614 @ 863e313`

```python
    agent_cfg = config.get("agent")
    if isinstance(agent_cfg, dict):
        disabled_toolsets = agent_cfg.get("disabled_toolsets")
        if isinstance(disabled_toolsets, list) and disabled_toolsets:
            newly_enabled = enabled_toolset_keys - preserved_entries
            if newly_enabled:
                remaining = [
                    ts for ts in disabled_toolsets
                    if str(ts) not in newly_enabled
                ]
                if remaining != disabled_toolsets:
                    agent_cfg["disabled_toolsets"] = remaining
```

> **命名/文档出入 C-2**:变量叫 `newly_enabled`,注释说"the user just explicitly enabled",
> 但它算的是 `本次勾选的全部键 - 保留条目`,即**当前所有勾着的**,不是"这次新勾的"。
> 语义后果不大(重复清理是幂等的),但读代码时容易误以为有一个 before/after diff。

`save_config(config)` 在函数末尾一次性落盘 —— 也就是说 `_save_platform_tools` 是**唯一**的写点,
其余修改 config 的函数(如 `_configure_imagegen_model`)都只改内存对象,靠调用方保存。

---

## 6. 机制 F:`_toolset_has_keys` —— "这个工具集配齐钥匙了吗"

三段式,顺序有讲究。`hermes_cli/tools_config.py:2617-2626 @ 863e313`

```python
def _toolset_has_keys(
    ts_key: str,
    config: dict = None,
    *,
    force_fresh: bool = False,
    features: Optional[NousSubscriptionFeatures] = None,
) -> bool:
    """Check if a toolset's required API keys are configured."""
    if config is None:
        config = load_config()
```

**第一段:vision 特判。** 它不看 env 而是真去解析一个可用的 client。
`hermes_cli/tools_config.py:2628-2635 @ 863e313`

```python
    if ts_key == "vision":
        try:
            from agent.auxiliary_client import resolve_vision_provider_client

            _provider, client, _model = resolve_vision_provider_client()
            return client is not None
        except Exception:
            return False
```

这与 `TOOLSET_ENV_REQUIREMENTS` 的注释是一致的:vision 的那条 `OPENROUTER_API_KEY` 只是
"占位标记",从不被读也从不被提示。`hermes_cli/tools_config.py:740-749 @ 863e313`

```python
# `vision` is listed here only so it registers as a *configurable* toolset
# (the value gates the reconfigure menu + the "[no API key]" suffix). Its
# actual setup runs through `_configure_vision_backend()` — a full
# provider+model picker like `hermes model` — NOT this single-key prompt, so
# users are never forced onto OpenRouter. `_toolset_has_keys("vision")`
# resolves via `resolve_vision_provider_client()`, so the tuple below is never
# prompted or read for vision; it's purely a presence marker.
TOOLSET_ENV_REQUIREMENTS = {
    "vision":     [("OPENROUTER_API_KEY",   "https://openrouter.ai/keys")],
}
```

**第二段:Nous 托管网关短路。** 六个可托管能力,只要订阅里"可用或被托管",就算配好了。
`hermes_cli/tools_config.py:2637-2644 @ 863e313`

```python
    if ts_key in {"web", "image_gen", "video_gen", "tts", "stt", "browser"}:
        if features is None:
            features = get_nous_subscription_features(
                config, force_fresh=force_fresh
            )
        feature = features.features.get(ts_key)
        if feature and (feature.available or feature.managed_by_nous):
            return True
```

**第三段:provider 感知 + 简单 env 兜底。** 任一可见 provider 的 env 全配齐即为真;
零 env 的 provider(Edge TTS、Local Browser)直接为真。`hermes_cli/tools_config.py:2646-2666 @ 863e313`

```python
    # Check TOOL_CATEGORIES first (provider-aware)
    cat = TOOL_CATEGORIES.get(ts_key)
    if cat:
        for provider in _visible_providers(
            cat,
            config,
            force_fresh=force_fresh,
            features=features,
        ):
            env_vars = provider.get("env_vars", [])
            if not env_vars:
                return True  # No-key provider (e.g. Local Browser, Edge TTS)
            if all(get_env_value(e["key"]) for e in env_vars):
                return True
        return False

    # Fallback to simple requirements
    requirements = TOOLSET_ENV_REQUIREMENTS.get(ts_key, [])
    if not requirements:
        return True
    return all(get_env_value(var) for var, _ in requirements)
```

**取舍**:"零 env provider 即为真"是这个函数最大的语义妥协 —— Local Browser 没 key 但需要装
npm 包和 Chromium。这一妥协后来被 `provider_readiness_status`(见 9 节)和
`_toolset_needs_configuration_prompt`(见 10 节)分别打补丁,但 `_toolset_has_keys` 本身没改。

`get_env_value` 是 profile scope 感知的 —— 多路复用 gateway 会话里不会串读别的 profile 的
`os.environ`。`hermes_cli/config.py:4109-4121 @ 863e313`

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

---

## 7. 机制 G:工具 token 估算与 checklist UI

### 为什么要估 token

工具 schema 是每轮都发的固定开销。勾多了直接吃掉上下文预算,用户看不见。所以 checklist 底部实时
显示"这些勾选大约值多少 token"。

实现:tiktoken `cl100k_base` 对 OpenAI 格式的 schema JSON 计数,**进程级缓存**。
`hermes_cli/tools_config.py:2679-2694 @ 863e313`

```python
# Module-level cache so discovery + tokenization runs at most once per process.
_tool_token_cache: Optional[Dict[str, int]] = None


def _estimate_tool_tokens() -> Dict[str, int]:
    """Return estimated token counts per individual tool name.

    Uses tiktoken (cl100k_base) to count tokens in the JSON-serialised
    OpenAI-format tool schema.  Triggers tool discovery on first call,
    then caches the result for the rest of the process.

    Returns an empty dict when tiktoken or the registry is unavailable.
    """
    global _tool_token_cache
    if _tool_token_cache is not None:
        return _tool_token_cache
```

序列化形状刻意与实际发给 API 的形状对齐。`hermes_cli/tools_config.py:2713-2722 @ 863e313`

```python
    counts: Dict[str, int] = {}
    for name in registry.get_all_tool_names():
        schema = registry.get_schema(name)
        if schema:
            # Mirror what gets sent to the API:
            # {"type": "function", "function": schema}
            text = _json.dumps({"type": "function", "function": schema})
            counts[name] = len(enc.encode(text))
    _tool_token_cache = counts
    return _tool_token_cache
```

**取舍**:`import model_tools` 触发全量工具发现,是个重导入;缓存换来只付一次。但缓存**把失败也
缓存了**:tiktoken 或 registry 任一不可用时写入 `{}` 并永久返回空(2701/2710),同一进程内不再
重试 —— 对 CLI 无所谓,对长驻 gateway 进程意味着一次瞬时导入失败就永久没有 token 估算。

### checklist:标签、预选、实时状态行

`hermes_cli/tools_config.py:2739-2746 @ 863e313`

```python
    effective_all = _get_effective_configurable_toolsets()
    # Drop platform-scoped toolsets that don't apply to this platform, and
    # config-only capabilities (stt) that have no per-platform toggle.
    effective = [
        (k, l, d) for (k, l, d) in effective_all
        if _toolset_allowed_for_platform(k, platform)
        and k not in _CONFIG_ONLY_TOOLSETS
    ]
```

`_CONFIG_ONLY_TOOLSETS` 的定义解释了为什么 stt 要被挡在 checklist 外:它发零个 schema,开关在
自己的 config 段。`hermes_cli/tools_config.py:159-165 @ 863e313`

```python
# Config-only capabilities: they appear in `hermes tools` for provider/API-key
# configuration (TOOL_CATEGORIES) but are NOT model toolsets — they ship zero
# tool schemas and their on/off switch lives in their own config section
# (e.g. ``stt.enabled``), not ``platform_toolsets``. Excluded from the
# per-platform enable/disable checklist; configured via the "Reconfigure an
# existing tool" flow and the GUI provider matrix instead.
_CONFIG_ONLY_TOOLSETS = {"stt"}
```

`[no API key]` 后缀的判定:`hermes_cli/tools_config.py:2748-2756 @ 863e313`

```python
    labels = []
    for ts_key, ts_label, ts_desc in effective:
        suffix = ""
        if (
            not _toolset_has_keys(ts_key, force_fresh=force_fresh)
            and (TOOL_CATEGORIES.get(ts_key) or TOOLSET_ENV_REQUIREMENTS.get(ts_key))
        ):
            suffix = "  [no API key]"
        labels.append(f"{ts_label}  ({ts_desc}){suffix}")
```

> **可疑缺陷 D-3(性能)**:`and` 的短路顺序把**便宜的字典查表放在了昂贵的调用之后**。
> `_toolset_has_keys(ts_key, force_fresh=force_fresh)` 每次调用都:(a) `config=None` →
> 重新 `load_config()`(2625–2626);(b) 对 web/image_gen/video_gen/tts/stt/browser 六个键,
> 以及经 `_visible_providers` 的每个 TOOL_CATEGORIES 键,**在 `features=None` 下**重新
> `get_nous_subscription_features(config, force_fresh=True)`。而
> `force_fresh=True` 明确会打网络:`hermes_cli/nous_account.py:328-332 @ 863e313`
>
> ```python
>     """Return normalized Nous Portal account entitlement information.
>
>     By default, a valid unexpired OAuth access JWT is used as a low-latency
>     local account snapshot. ``force_fresh=True`` always calls
>     ``/api/oauth/account`` and bypasses the short-lived cache. JWT claims are
> ```
>
> `_prompt_toolset_checklist` 的 `force_fresh` 默认就是 True(2730)。CONFIGURABLE_TOOLSETS
> 现有 26 项,于是渲染一次 checklist 会做 26 次 `load_config()` 和数次到十余次 Portal 往返。
> 怎么踩到:网络慢或 Portal 抖动时,`hermes tools` 在显示复选框前长时间无输出。
> 修法很轻:把条件两侧调换,或把 `config` 和一份 `features` 快照传下去(这两个参数本来就存在)。

`cancel_returns=pre_selected` 意味着**按 ESC 取消 = 返回当前选择**。
`hermes_cli/tools_config.py:2778-2785 @ 863e313`

```python
    chosen = curses_checklist(
        f"Tools for {platform_label}",
        labels,
        pre_selected,
        cancel_returns=pre_selected,
        status_fn=status_fn,
    )
    return {effective[i][0] for i in chosen}
```

调用方拿到返回值后照常继续走保存流程。`hermes_cli/tools_config.py:4895-4902 @ 863e313`

```python
            current_enabled = _get_platform_tools(config, pkey, include_default_mcp_servers=False)

            # Uncheck toolsets that should be off by default
            checklist_preselected = current_enabled - _DEFAULT_OFF_TOOLSETS

            # Show checklist
            new_enabled = _prompt_toolset_checklist(pinfo["label"], checklist_preselected, pkey)
```

> **可疑缺陷 D-4**:因此**在 checklist 上按 ESC 也会把平台的隐式复合冻结成显式清单**。
> 2166–2170 的注释把"冻结"描述成保存动作的后果,但取消也会触发。怎么踩到:用户打开
> `hermes tools` 看一眼、按 ESC 退出,从此这个平台的 `platform_toolsets` 变成冻结列表,
> 后续版本新增的工具集不再自动继承(只有 `_RECENTLY_SHIPPED_TOOLSETS` 里那一个能回填)。

---

## 8. 机制 H:插件 provider 注入 —— 五个同构 builder + `_visible_providers`

### 解决什么问题

历史上 web / image_gen / video_gen / browser 的 provider 是硬编码在 `TOOL_CATEGORIES` 里的。
插件化之后,provider 从注册表来。但 picker 的渲染、选择、写配置逻辑不想为插件另写一套 —— 于是
让 builder **把插件 provider 翻译成与硬编码行完全同构的 dict**。

五个 builder 结构几乎逐字相同(image_gen 2810 / video_gen 2850 / web 2898 / browser 2981 /
tts 3028),差别只在:导入哪个 registry、row 里放什么 marker 字段。以 web 为例:
`hermes_cli/tools_config.py:2931-2942 @ 863e313`

```python
        row = {
            "name": schema.get("name", provider.display_name),
            "badge": schema.get("badge", ""),
            "tag": schema.get("tag", ""),
            "env_vars": schema.get("env_vars", []),
            "web_backend": name,
            "web_search_plugin_name": name,
        }
        # Optional pass-through fields the schema can opt into.
        if schema.get("post_setup"):
            row["post_setup"] = schema["post_setup"]
        rows.append(row)
```

marker 字段一览(决定下游写哪个 config 键):

| builder | 行号 | marker 字段 | 写入的 config 键 |
|---|---|---|---|
| `_plugin_image_gen_providers` | 2810 | `image_gen_plugin_name` | `image_gen.provider` |
| `_plugin_video_gen_providers` | 2850 | `video_gen_plugin_name` | `video_gen.provider` |
| `_plugin_web_search_providers` | 2898 | `web_backend` + `web_search_plugin_name` | `web.backend` |
| `_plugin_browser_providers` | 2981 | `browser_provider` + `browser_plugin_name` | `browser.cloud_provider` |
| `_plugin_tts_providers` | 3028 | `tts_provider` + `tts_plugin_name` | `tts.provider` |

web 的 row 特意同时填 `web_backend`(旧字段,被 setup/selection 助手消费)和
`web_search_plugin_name`(信息标记),就是为了让 picker 对硬编码行和插件行行为完全一致。
`hermes_cli/tools_config.py:2899-2906 @ 863e313`

```python
    """Build picker-row dicts from plugin-registered web search providers.

    Each returned dict is a regular ``TOOL_CATEGORIES`` provider row. It
    populates both ``web_backend`` (legacy field consumed by setup +
    selection helpers) and ``web_search_plugin_name`` (informational
    marker) so the picker behaves identically whether a provider is
    hardcoded or plugin-registered.
```

TTS 是唯一"插件与内建共存"的类目,所以多一道防影子内建的过滤 —— 注释直说注册表本身已经拒绝,
这里是第二道防线。`hermes_cli/tools_config.py:3038-3044 @ 863e313`

```python
    Defensive: plugins whose name collides with a built-in TTS provider
    are filtered out — even though the registry already rejects them
    at registration time, a future code path that registers directly
    via :func:`agent.tts_registry.register_provider` could slip
    through. Filtering here keeps the picker invariant.
    """
    try:
        from agent.tts_registry import _BUILTIN_NAMES, list_providers
```

`hermes_cli/tools_config.py:3058-3061 @ 863e313`

```python
        # Defensive: reject built-in shadowing at the picker layer too.
        if name.lower().strip() in _BUILTIN_NAMES:
            continue
        try:
```

所有五个 builder 都用同一套"整块 try/except 返回 []"的失败模式,并对每个 provider 的
`get_setup_schema()` 单独 try —— **一个坏插件不能让整个类目消失**。这是明确的容错取舍,
代价是坏插件完全静默(无 log)。

### `web_provider_capabilities`:按能力分流

`hermes_cli/tools_config.py:2946-2956 @ 863e313`

```python
def web_provider_capabilities(backend: str) -> list:
    """Return the capabilities (``search`` / ``extract``) a web backend supports.

    Consults the plugin registry's provider instance (``supports_search`` /
    ``supports_extract``) so the Capabilities GUI can offer per-capability
    selection (``web.search_backend`` / ``web.extract_backend``) only where it
    makes sense — e.g. ddgs and brave-free are search-only. Falls back to both
    capabilities when the backend isn't registered (hardcoded setup-flow rows
    like the managed Firecrawl entries resolve before plugin discovery in some
    test contexts, and firecrawl itself supports both).
    """
```

兜底返回 `["search", "extract"]`(2970)—— 乐观兜底,未注册的 backend 会被当成两种能力都支持。

### `_visible_providers`:可见性策略 + 注入点

**策略**:Nous 托管行**永远显示**(哪怕未登录),因为 picker 要广告这个能力存在;选中它才走内联
Portal 登录 + 权益检查。`hermes_cli/tools_config.py:3091-3098 @ 863e313`

```python
    """Return provider entries visible for the current auth/config state.

    Nous-managed Tool Gateway rows (``managed_nous_feature``) are always
    shown — even to logged-out / unentitled users — so the picker advertises
    that the capability exists.  Selecting one drives an inline Nous Portal
    login + entitlement check (see ``_configure_provider``); the row only
    *activates* the gateway once paid access is confirmed.
    """
```

**唯一的例外是 pool-only 用户的视频生成行**:免费工具池不覆盖 `fal-video`,显示了也只会被拒。
`hermes_cli/tools_config.py:3102-3112 @ 863e313`

```python
    # Pool-only users (entitled to managed tools via the free tool pool but with
    # no paid access) get image gen but NOT video gen — the pool doesn't fund
    # `fal-video`. Rather than advertise a managed video row that would be denied
    # on select, hide it for them. Logged-out users still see it (advertising)
    # and paid users are entitled to it.
    pool_only = bool(
        acct
        and acct.logged_in
        and acct.paid_service_access is not True
        and acct.tool_gateway_entitled
    )
```

两条过滤规则:`hermes_cli/tools_config.py:3114-3133 @ 863e313`

```python
    for provider in cat.get("providers", []):
        # Nous-managed Tool Gateway rows stay visible regardless of auth —
        # selecting one drives an inline Portal login. A `requires_nous_auth`
        # row that is NOT a managed gateway feature (pure pre-auth UX) is
        # still hidden until the user is logged in.
        if (
            provider.get("requires_nous_auth")
            and not provider.get("managed_nous_feature")
            and not features.nous_auth_present
        ):
            continue
        # Hide the managed video-gen row from pool-only users — their free tool
        # pool doesn't cover video, so showing it would only lead to a denial.
        if (
            pool_only
            and provider.get("managed_nous_feature") == "video_gen"
            and not (acct and acct.tool_gateway_entitled_for("fal-video"))
        ):
            continue
        visible.append(provider)
```

`tool_gateway_entitled_for` 的语义(付费全覆盖,免费池按 coverage 逐项):
`hermes_cli/nous_account.py:120-127 @ 863e313`

```python
    def tool_gateway_entitled_for(self, category: str) -> bool:
        """Whether a specific tool category is entitled. Paid users are entitled
        everywhere; free tool-pool users only where ``coverage[category]`` is
        true (e.g. image but not video)."""
        if self.paid_service_access is True:
            return True
        ta = self.tool_access
        return bool(ta and ta.enabled and ta.coverage.get(category) is True)
```

**注入点用类目的 display name 做 key**,不是 ts_key:`hermes_cli/tools_config.py:3135-3143 @ 863e313`

```python
    # Inject plugin-registered image_gen backends (OpenAI today, more
    # later) so the picker lists them alongside FAL / Nous Subscription.
    if cat.get("name") == "Image Generation":
        visible.extend(_plugin_image_gen_providers())

    # Inject plugin-registered video_gen backends. Unlike image_gen,
    # video_gen has NO hardcoded providers — every backend is a plugin.
    if cat.get("name") == "Video Generation":
        visible.extend(_plugin_video_gen_providers())
```

五个注入分支分别匹配 `"Image Generation"` / `"Video Generation"` / `"Web Search & Extract"` /
`"Browser Automation"` / `"Text-to-Speech"`。**这是脆弱耦合**:类目的显示名一改(哪怕只是大小写
或加个 `&`),插件行就静默消失,没有任何断言保护。类目 dict 里明明有 ts_key 作为字典键,却用了
显示字符串。

### 死代码:`_hidden_nous_gateway_message`

`hermes_cli/tools_config.py:3170-3186 @ 863e313`

```python
def _hidden_nous_gateway_message(
    cat: dict,
    config: dict,
    capability: str,
    *,
    force_fresh: bool = False,
) -> str:
    """Deprecated: Nous Tool Gateway rows are no longer hidden.

    Previously this returned a "log in / upgrade" banner shown above a
    category when its Nous-managed rows were filtered out for unentitled
    users. Those rows are now always listed (see ``_visible_providers``), and
    the login + entitlement guidance happens inline when the user selects one
    (``ensure_nous_portal_access``). Kept as a no-op so call sites stay simple;
    always returns an empty string.
    """
    return ""
```

后果:`_configure_tool_category` 里两处 `if hidden_nous_message:` 是**恒假分支**
(3473–3475、3485–3487),连同 3447–3452 的构造调用一起是纯开销的死代码。

---

## 9. 机制 I:`provider_readiness_status` —— 诚实的 Ready 判定

### 解决什么问题

老的 GUI"Ready"药丸是**客户端启发式**:零 env 变量的行一律显示 Ready。于是未登录的
"Nous Subscription"行、没装 npm 包的"Local Browser"行都显示 Ready,点下去才失败。这个函数把判定
搬到服务端并且拆成四态。`hermes_cli/tools_config.py:3294-3313 @ 863e313`

```python
    """Compute an honest readiness state for a provider picker row.

    Returns one of:

    - ``"ready"``       — usable as-is (keys set / entitled / installed).
    - ``"needs_keys"``  — declares env vars and at least one is unset.
    - ``"needs_auth"``  — needs a sign-in: Nous Portal login/entitlement for
      managed Tool Gateway rows, or xAI Grok OAuth / XAI_API_KEY for
      ``post_setup: "xai_grok"`` rows.
    - ``"needs_setup"`` — keyless row whose ``post_setup`` install hook has
      verifiably not run yet (see ``_POST_SETUP_READY``).

    Keyless ≠ usable: this is the server-side truth the GUI "Ready" pill
    renders from (the old client-side heuristic showed Ready for every
    zero-env-var row, including logged-out Nous Subscription rows).

    ``features`` (a ``NousSubscriptionFeatures``) can be passed to avoid
    re-fetching portal state per row. ``is_active`` is the completed-setup
    fallback signal for post_setup hooks with no registered installed-check
    (selecting a row runs its hook, so the active row has been set up).
    """
```

判定顺序:**env 变量优先,且是 early-return**。`hermes_cli/tools_config.py:3315-3319 @ 863e313`

```python
    env_vars = provider.get("env_vars", [])
    if env_vars:
        if all(get_env_value(e["key"]) for e in env_vars):
            return "ready"
        return "needs_keys"
```

然后是 Nous 授权 + 逐类目权益。`hermes_cli/tools_config.py:3321-3342 @ 863e313`

```python
    managed_feature = provider.get("managed_nous_feature")
    if provider.get("requires_nous_auth") or managed_feature:
        if features is None:
            features = get_nous_subscription_features(config)
        if not features.nous_auth_present:
            return "needs_auth"
        if managed_feature:
            # Same per-category entitlement gate the CLI applies at selection
            # time (free tool-pool users get image gen but not video gen).
            acct = features.account_info
            category = MANAGED_FEATURE_COVERAGE_CATEGORY.get(managed_feature)
            entitled = bool(
                acct
                and acct.logged_in
                and (
                    acct.tool_gateway_entitled_for(category)
                    if category
                    else acct.tool_gateway_entitled
                )
            )
            if not entitled:
                return "needs_auth"
```

`MANAGED_FEATURE_COVERAGE_CATEGORY` 是"能力名 → 计费类目"的映射,注意 stt 与 tts 共用
`openai-audio`。`hermes_cli/nous_subscription.py:37-47 @ 863e313`

```python
MANAGED_FEATURE_COVERAGE_CATEGORY: Dict[str, str] = {
    "web": "firecrawl",
    "image_gen": "fal",
    "video_gen": "fal-video",
    "tts": "openai-audio",
    # STT shares the TTS coverage category: both ride the managed
    # "openai-audio" gateway endpoint (speech + transcriptions).
    "stt": "openai-audio",
    "browser": "browser-use",
    "modal": "modal",
}
```

最后是 post_setup 安装态。三层:xai_grok 走凭据检查;有注册谓词就跑谓词;无谓词则拿"是不是当前
激活 provider"当"装过了"的信号。`hermes_cli/tools_config.py:3347-3364 @ 863e313`

```python
    post_setup = provider.get("post_setup")
    if post_setup:
        if post_setup == "xai_grok":
            return "ready" if _xai_credentials_present() else "needs_auth"
        predicate = _POST_SETUP_READY.get(post_setup)
        if predicate is not None:
            try:
                return "ready" if predicate() else "needs_setup"
            except Exception:
                # Flaky detection must not manufacture a warning state.
                return "ready"
        # No reliable installed-check registered → treat the active-provider
        # signal as "setup completed" (selecting the row runs the hook).
        if is_active is None:
            is_active = _is_provider_active(provider, config)
        return "ready" if is_active else "needs_setup"

    return "ready"
```

谓词表 `_POST_SETUP_READY` 覆盖 9 个键,并明确说明为什么 `xai_grok` 不在表里。
`hermes_cli/tools_config.py:3258-3274 @ 863e313`

```python
# post_setup_key -> predicate(): True when the install side-effect is already
# satisfied. Used by ``provider_readiness_status`` to decide whether a keyless
# post_setup row (KittenTTS, Piper, Local Browser, …) is honestly "ready" or
# still "needs_setup". Mirrors the installed-checks ``_run_post_setup`` itself
# performs before installing. ``xai_grok`` is intentionally absent — it is a
# credential bootstrap, not an install, and is handled as an auth check.
_POST_SETUP_READY: dict = {
    "kittentts": lambda: _module_installed("kittentts"),
    "piper": lambda: _module_installed("piper"),
    "faster_whisper": lambda: _module_installed("faster_whisper"),
    "ddgs": lambda: _module_installed("ddgs"),
    "langfuse": lambda: _module_installed("langfuse"),
    "agent_browser": lambda: _agent_browser_installed(),
    "browserbase": lambda: _cloud_agent_browser_installed(),
    "camofox": lambda: _camofox_installed(),
    "cua_driver": lambda: _resolved_cua_driver_cmd() is not None,
}
```

`_module_installed` 用 `find_spec` 而不是真 import,避免重副作用。
`hermes_cli/tools_config.py:3220-3227 @ 863e313`

```python
def _module_installed(module_name: str) -> bool:
    """Cheap importable-without-importing check (no heavy side effects)."""
    import importlib.util

    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False
```

`_agent_browser_installed` 里藏着一个跨进程缓存失效的处理:安装发生在 spawn 出去的
`hermes tools post-setup` 子进程,而探测跑在长驻的 web-server/CLI 进程 —— 后者的
`tools.browser_tool` 可能缓存了安装前的"Chromium 缺失"。所以显式打掉那个缓存。
`hermes_cli/tools_config.py:3240-3249 @ 863e313`

```python
    # The install hook runs in a spawned ``hermes tools post-setup`` process,
    # but this probe runs in the long-lived web-server/CLI process, whose
    # browser_tool module may have cached a stale "Chromium missing" result
    # from before the install. Drop the cache (when the module is loaded) so
    # the readiness pill flips to Ready right after a successful setup run.
    bt = sys.modules.get("tools.browser_tool")
    if bt is not None:
        bt._cached_chromium_installed = None

    return _local_browser_runnable()
```

`_camofox_installed` 直接看 node_modules 路径。`hermes_cli/tools_config.py:3252-3255 @ 863e313`

```python
def _camofox_installed() -> bool:
    """True when the Camofox npm package ``_run_post_setup("camofox")``
    installs is already in node_modules."""
    return (PROJECT_ROOT / "node_modules" / "@askjo" / "camofox-browser").exists()
```

> **可疑缺陷 D-5(已实测复现)**:env-vars 分支是 early-return,所以**同时声明 env_vars 和
> post_setup 的 provider,只要 key 配齐就报 "ready",安装检查被完全跳过**。
> 基线里至少三行是这种形状:
> - Camofox(`CAMOFOX_URL` + `post_setup: "camofox"`)`hermes_cli/tools_config.py:648-656 @ 863e313`
>
>   ```python
>                 "name": "Camofox",
>   ```
>   `hermes_cli/tools_config.py:656 @ 863e313`
>   ```python
>                 "post_setup": "camofox",
>   ```
> - Langfuse Cloud / Self-Hosted(两个 `HERMES_LANGFUSE_*` key + `post_setup: "langfuse"`)
> - Browserbase 插件行(两个 key + `post_setup: "browserbase"`)
>   `plugins/browser/browserbase/provider.py:281-299 @ 863e313`
>
>   ```python
>     def get_setup_schema(self) -> Dict[str, Any]:
>   ```
>
> 实测:
> ```
> CAMOFOX_URL=http://localhost:9377
> _camofox_installed() -> False
> provider_readiness_status(camofox_row, {}) -> 'ready'
> ```
> 怎么踩到:用户在 GUI 里填了 Camofox URL(该 key 还带默认值 `http://localhost:9377`,
> 配置流程很可能直接写入),药丸显示 Ready,但 `@askjo/camofox-browser` 从没装过,
> 一用就失败。`_POST_SETUP_READY` 里为 camofox / browserbase 写好的谓词在这条路上永远不被调用。
> 修法:把 post_setup 检查从 early-return 之后挪到 env 检查通过之后再串一道。

---

## 10. 机制 J:`_toolset_needs_configuration_prompt` —— 何时该弹配置流程

### 事故背景(#22737)

cua-driver 那种"零 key、只有安装副作用"的 provider,老代码走 `_toolset_has_keys` 兜底:
零 env → 返回 True → 判定"不需要配置" → `hermes tools` 写好配置打印 `✓ Saved` 就退出,
**安装从来没跑过**。用户勾了 Computer Use,什么也没发生。测试文件把这段事故写在开头。
`tests/hermes_cli/test_post_setup_gating.py:1-12 @ 863e313`

```python
"""Tests for the post_setup install-state gate in `_toolset_needs_configuration_prompt`.

Regression coverage for the cua-driver silent-no-op bug (issue #22737).

When a no-key provider's only install side-effect is a `post_setup` hook
(cua-driver, etc.), the gate function used to fall through to the
`_toolset_has_keys` catch-all, which returned True for any provider with
empty `env_vars` — causing `hermes tools` to write the toolset to config
and exit `✓ Saved` without ever invoking the post_setup install. These
tests pin the new predicate-aware behaviour so the regression doesn't
sneak back in.
"""
```

### 修法

在类目的所有可见 provider 上跑一遍安装态检查,任一未满足就强制走配置流程(配置流程里会调
`_run_post_setup`)。`hermes_cli/tools_config.py:3374-3385 @ 863e313`

```python
    cat = TOOL_CATEGORIES.get(ts_key)
    if not cat:
        return not _toolset_has_keys(ts_key, config, force_fresh=force_fresh)

    # If any visible provider has a registered post_setup install-state
    # check that hasn't been satisfied (e.g. cua-driver binary not on
    # PATH yet), force the configuration flow so `_configure_provider`
    # invokes `_run_post_setup` and the install actually runs.
    for provider in _visible_providers(cat, config, force_fresh=force_fresh):
        post_setup = provider.get("post_setup")
        if post_setup and not _post_setup_already_installed(post_setup):
            return True
```

`_POST_SETUP_INSTALLED` 是**opt-in 表**,当前只有一项,并写清了准入条件。
`hermes_cli/tools_config.py:3189-3204 @ 863e313`

```python
_POST_SETUP_INSTALLED: dict = {
    # post_setup_key -> predicate(): True when the install side-effect
    # is already satisfied. Used by `_toolset_needs_configuration_prompt`
    # to force the provider-setup flow when a no-key provider still needs
    # a binary/dependency install (otherwise an already-configured user
    # who toggles the toolset on via `hermes tools` gets a silent no-op
    # because the gate sees "no env vars to ask about" and skips the
    # provider-setup flow that would have run the post_setup hook).
    #
    # Only entries here are gated; other post_setup hooks (kittentts,
    # piper, agent_browser, etc.) keep their existing behaviour. Add an
    # entry when (a) the post_setup is the ONLY install side-effect for
    # a no-key provider, and (b) an installed-state check is cheap and
    # doesn't trigger a heavy import.
    "cua_driver": lambda: _resolved_cua_driver_cmd() is not None,
}
```

未注册的键一律"当作已装",谓词抛异常也一样 —— 注释与测试都强调这是为了不把用户困在无限配置循环里。
`hermes_cli/tools_config.py:3207-3217 @ 863e313`

```python
def _post_setup_already_installed(post_setup_key: str) -> bool:
    """Return True when the post_setup install side-effect is satisfied."""
    predicate = _POST_SETUP_INSTALLED.get(post_setup_key)
    if predicate is None:
        # No install-state check registered → assume satisfied (don't
        # change behaviour for hooks we haven't explicitly opted in).
        return True
    try:
        return bool(predicate())
    except Exception:
        return True
```

**注意两张谓词表的分工**:`_POST_SETUP_INSTALLED`(1 项)决定"要不要弹配置",
`_POST_SETUP_READY`(9 项)决定"GUI 药丸显示什么"。同名 key `cua_driver` 的 lambda 写了两遍
(3203 与 3273),**逐字重复**。二者可以合并但作者刻意分开,理由写在 3198–3202:
`_POST_SETUP_INSTALLED` 的准入门槛更高(必须是"唯一安装副作用"且检查便宜)。

### 每个类目的"配好了没"判定

`hermes_cli/tools_config.py:3387-3395 @ 863e313`

```python
    if ts_key == "tts":
        tts_cfg = config.get("tts", {})
        return not isinstance(tts_cfg, dict) or "provider" not in tts_cfg
    if ts_key == "web":
        web_cfg = config.get("web", {})
        return not isinstance(web_cfg, dict) or "backend" not in web_cfg
    if ts_key == "browser":
        browser_cfg = config.get("browser", {})
        return not isinstance(browser_cfg, dict) or "cloud_provider" not in browser_cfg
```

image_gen 特殊:in-tree FAL 配好了,或任一插件 provider `is_available()`,就算配好。
`hermes_cli/tools_config.py:3396-3414 @ 863e313`

```python
    if ts_key == "image_gen":
        # Satisfied when the in-tree FAL backend is configured OR any
        # plugin-registered image gen provider is available.
        if fal_key_is_configured():
            return False
        try:
            from agent.image_gen_registry import list_providers
            from hermes_cli.plugins import _ensure_plugins_discovered

            _ensure_plugins_discovered()
            for provider in list_providers():
                try:
                    if provider.is_available():
                        return False
                except Exception:
                    continue
        except Exception:
            pass
        return True
```

video_gen 同构但无 in-tree 兜底(3415–3431),其余走 `_toolset_has_keys`(3433)。

---

## 11. 机制 K:`_configure_tool_category` 与 provider 激活判定

### 单 provider vs 多 provider

`hermes_cli/tools_config.py:3454-3461 @ 863e313`

```python
    # Check Python version requirement
    if cat.get("requires_python"):
        req = cat["requires_python"]
        if sys.version_info < req:
            print()
            _print_error(f"  {name} requires Python {req[0]}.{req[1]}+ (current: {sys.version_info.major}.{sys.version_info.minor})")
            _print_info("  Upgrade Python and reinstall to enable this tool.")
            return
```

> **死代码 D-6**:基线里**没有任何类目声明 `requires_python`**(全仓 grep `requires_python`
> 只有 3455/3456 两处读取,零处声明)。这个分支是恒不触发的扩展点。

> **死配置 D-7**:反过来,`TOOL_CATEGORIES["computer_use"]` 声明了 `platform_gate`,
> `hermes_cli/tools_config.py:691 @ 863e313`
>
> ```python
>         "platform_gate": ["darwin", "win32", "linux"],
> ```
>
> 但全仓没有任何代码读它(grep `platform_gate` 只命中这一处声明,以及
> `gateway/authz_mixin.py` 里同名但无关的函数 `_platform_gate_env`,和
> `tools/computer_use/permissions.py:34` 一句"mirrors the toolset platform_gate"的注释)。
> `_configure_tool_category` 只检查 `requires_python`,不检查 `platform_gate`。
> 怎么踩到:今天没影响(三个值覆盖了所有支持平台);未来若某类目声明一个真正收窄的
> `platform_gate`,它会被完全忽略,picker 在不支持的 OS 上照样展示。

多 provider 时构造标签,`[active]` / `[configured]` 两种状态 + Nous 订阅星标。
`hermes_cli/tools_config.py:3504-3516 @ 863e313`

```python
        provider_choices = []
        for p in providers:
            badge = f" [{p['badge']}]" if p.get("badge") else ""
            tag = f" — {p['tag']}" if p.get("tag") else ""
            configured = ""
            env_vars = p.get("env_vars", [])
            if not env_vars or all(get_env_value(v["key"]) for v in env_vars):
                if _is_provider_active(p, config, force_fresh=force_fresh):
                    configured = " [active]"
                elif not env_vars:
                    configured = ""
                else:
                    configured = " [configured]"
```

`hermes_cli/tools_config.py:3517-3528 @ 863e313`

```python
            # Mark Nous-managed entries. Logged-in paid subscribers get the
            # "included" star; everyone else gets a "via Nous Portal" hint so
            # it's clear selecting the row triggers a Portal login. The rows
            # are always shown now (see _visible_providers) — selecting one
            # drives an inline login + entitlement check.
            sub_marker = ""
            if p.get("managed_nous_feature"):
                if _nous_logged_in:
                    sub_marker = "  ★ Included with your Nous subscription"
                else:
                    sub_marker = "  ★ via Nous Portal (login on select)"
            provider_choices.append(f"{p['name']}{badge}{tag}{configured}{sub_marker}")
```

"Skip"选项追加在末尾,选中它靠 `provider_idx >= len(providers)` 判定 —— 隐式约定"skip 一定是
最后一项"。`hermes_cli/tools_config.py:3530-3545 @ 863e313`

```python
        # Add skip option
        provider_choices.append("Skip — keep defaults / configure later")

        # Detect current provider as default
        default_idx = _detect_active_provider_index(
            providers,
            config,
            force_fresh=force_fresh,
        )

        provider_idx = _prompt_choice(f"  {title}:", provider_choices, default_idx)

        # Skip selected
        if provider_idx >= len(providers):
            _print_info(f"  Skipped {name}")
            return
```

### `_is_provider_active`:六种 marker 的分派

优先级从上到下:image_gen 插件 → video_gen 插件(且非托管)→ 托管能力 → tts/stt/browser/web/
imagegen 的普通 marker。`hermes_cli/tools_config.py:3556-3567 @ 863e313`

```python
    """Check if a provider entry matches the currently active config."""
    plugin_name = provider.get("image_gen_plugin_name")
    if plugin_name:
        image_cfg = config.get("image_gen", {})
        return isinstance(image_cfg, dict) and image_cfg.get("provider") == plugin_name

    video_plugin_name = provider.get("video_gen_plugin_name")
    if video_plugin_name and not provider.get("managed_nous_feature"):
        video_cfg = config.get("video_gen", {})
        return isinstance(video_cfg, dict) and video_cfg.get("provider") == video_plugin_name

    managed_feature = provider.get("managed_nous_feature")
```

注意 **image_gen 分支没有 `and not managed_nous_feature` 这一条,video_gen 有**。这是个不对称
(今天无害:托管 image 行是硬编码的,不带 `image_gen_plugin_name`;但插件若某天注册一个托管
image 行,它会走错分支)。

托管 image/video 的"激活"要同时满足三件事:feature 是托管的、`provider` 未被改成非 fal、
`use_gateway` 没被显式设成假。`hermes_cli/tools_config.py:3573-3581 @ 863e313`

```python
        if managed_feature == "image_gen":
            image_cfg = config.get("image_gen", {})
            if isinstance(image_cfg, dict):
                configured_provider = image_cfg.get("provider")
                if configured_provider not in {None, "", "fal"}:
                    return False
                if image_cfg.get("use_gateway") is not None and not is_truthy_value(image_cfg.get("use_gateway"), default=False):
                    return False
            return feature.managed_by_nous
```

非托管 stt 有个"未设 = local"的默认约定,托管路径(3596–3600)没有对应处理。
`hermes_cli/tools_config.py:3609-3620 @ 863e313`

```python
    if provider.get("tts_provider"):
        return cfg_get(config, "tts", "provider") == provider["tts_provider"]
    if provider.get("stt_provider"):
        # Default stt.provider is "local" — an unset key means Local Whisper.
        current = cfg_get(config, "stt", "provider") or "local"
        return current == provider["stt_provider"]
    if "browser_provider" in provider:
        current = cfg_get(config, "browser", "cloud_provider")
        return provider["browser_provider"] == current
    if provider.get("web_backend"):
        current = cfg_get(config, "web", "backend")
        return current == provider["web_backend"]
```

`"browser_provider" in provider` 用 `in` 而不是 `.get()` truthiness —— 因为
`browser_provider: "local"` 之类空串风险,以及要区分"字段缺失"与"字段为空"。

### `_detect_active_provider_index` 的顺序缺陷

`hermes_cli/tools_config.py:3640-3648 @ 863e313`

```python
    """Return the index of the currently active provider, or 0."""
    for i, p in enumerate(providers):
        if _is_provider_active(p, config, force_fresh=force_fresh):
            return i
        # Fallback: env vars present → likely configured
        env_vars = p.get("env_vars", [])
        if env_vars and all(get_env_value(v["key"]) for v in env_vars):
            return i
    return 0
```

> **可疑缺陷 D-8(已实测复现)**:"env 配齐了 → 大概是它"这个兜底**在同一个循环内逐项短路**,
> 而不是作为第二遍扫描。于是一个排在前面、只是配了 key 的 provider 会**抢在真正激活的
> provider 之前**返回。
>
> 实测(STT 类目,`stt.provider: groq`,同时设了 `VOICE_TOOLS_OPENAI_KEY` 和 `GROQ_API_KEY`):
> ```
> 0 Local Whisper local []
> 1 Nous Subscription openai []
> 2 OpenAI openai ['VOICE_TOOLS_OPENAI_KEY']
> 3 Groq groq ['GROQ_API_KEY']
> _is_provider_active -> Groq=True,其余 False
> _detect_active_provider_index -> 2      # 光标停在 OpenAI,不是 Groq
> ```
> 怎么踩到:用过 OpenAI 转录、后来切到 Groq 的用户,重新进 `hermes tools` → Speech-to-Text,
> 光标默认落在 OpenAI 上;直接回车就把 provider 悄悄改回去了。
> 修法:先整轮扫 `_is_provider_active`,没命中再整轮扫 env 兜底。

---

## 12. 机制 L:图像生成模型选择器(本段末尾)

`IMAGEGEN_BACKENDS` 是个"每 backend 一份目录"的注册表,注释说明它是为将来的 Replicate /
Stability 准备的扩展点。`hermes_cli/tools_config.py:3651-3662 @ 863e313`

```python
# ─── Image Generation Model Pickers ───────────────────────────────────────────
#
# IMAGEGEN_BACKENDS is a per-backend catalog. Each entry exposes:
#   - config_key:        top-level config.yaml key for this backend's settings
#   - model_catalog_fn:  returns an OrderedDict-like {model_id: metadata}
#   - default_model:     fallback when nothing is configured
#
# This prepares for future imagegen backends (Replicate, Stability, etc.):
# each new backend registers its own entry; the FAL provider entry in
# TOOL_CATEGORIES tags itself with `imagegen_backend: "fal"` to select the
# right catalog at picker time.
```

> **文档-代码出入 C-3**:注释承诺三个字段 `config_key` / `model_catalog_fn` / `default_model`,
> 实际的 dict 只有三个字段且名字不同:`display` / `config_key` / `catalog_fn`,没有
> `model_catalog_fn`,也没有 `default_model`(默认模型由 `catalog_fn` 返回的第二个值给出)。
> `hermes_cli/tools_config.py:3670-3676 @ 863e313`
>
> ```python
> IMAGEGEN_BACKENDS = {
>     "fal": {
>         "display": "FAL.ai",
>         "config_key": "image_gen",
>         "catalog_fn": _fal_model_catalog,
>     },
> }
> ```
>
> 怎么踩到:按注释注册新 backend 的人会写 `model_catalog_fn`,而 `_configure_imagegen_model`
> 在 3700 行取 `backend["catalog_fn"]()` → KeyError。

目录懒加载,避免在 CLI 启动时导入图像工具模块。`hermes_cli/tools_config.py:3664-3667 @ 863e313`

```python
def _fal_model_catalog():
    """Lazy-load the FAL model catalog from the tool module."""
    from tools.image_generation_tool import FAL_MODELS, DEFAULT_MODEL
    return FAL_MODELS, DEFAULT_MODEL
```

选择器本体处理了"当前模型不在目录里"和"config 段被写成非 dict"两种脏数据。
`hermes_cli/tools_config.py:3700-3715 @ 863e313`

```python
    catalog, default_model = backend["catalog_fn"]()
    if not catalog:
        return

    cfg_key = backend["config_key"]
    cur_cfg = config.setdefault(cfg_key, {})
    if not isinstance(cur_cfg, dict):
        cur_cfg = {}
        config[cfg_key] = cur_cfg
    current_model = cur_cfg.get("model") or default_model
    if current_model not in catalog:
        current_model = default_model

    model_ids = list(catalog.keys())
    # Put current model at the top so the cursor lands on it by default.
    ordered = [current_model] + [m for m in model_ids if m != current_model]
```

把当前模型置顶 + `_prompt_choice(default=0)`,配合 `curses_radiolist` 的
`cancel_returns=default`,使 ESC 等价于"保持当前选择"。函数只改内存不落盘(无 `save_config`),
落盘由调用方负责。

---

## 13. 配置键与环境变量全表(本段)

### config.yaml 键

| 键(点分路径) | 默认 | 读取点 @863e313 | 读它的函数 | 语义 / fallback 链 |
|---|---|---|---|---|
| `platform_toolsets.<platform>` | 无 → `[PLATFORMS[p].default_toolset]`,插件平台 → `["hermes-<p>"]` | `hermes_cli/tools_config.py:2232-2247` | `_get_platform_tools` | 非 list 一律当缺省;元素强制 str 化(YAML 数字键) |
| `platform_toolsets.<platform>`(写) | — | `hermes_cli/tools_config.py:2566` | `_save_platform_tools` | `sorted(勾选键 ∪ 保留条目)`;`no_mcp` 被丢弃 |
| `platform_toolsets.<platform>`(读旧值) | `[]` | `hermes_cli/tools_config.py:2548` | `_save_platform_tools` | 经 `cfg_get`,非 list 归零 |
| `known_plugin_toolsets.<platform>` | `{}` / 缺失 | 读 `:2421-2422`;写 `:2570-2575` | `_get_platform_tools` / `_save_platform_tools` | 区分"新插件默认开"与"用户关掉";present-but-null 会被规范化成 `{}` |
| `known_builtin_toolsets.<platform>` | 缺失 | 读 `:2200`;写 `:2582-2586` | `_enable_recently_shipped_toolsets` / `_save_platform_tools` | 在账 = 曾展示过 = 缺席即拒绝;非 list 视作空 |
| `mcp_servers` | `{}` | `hermes_cli/tools_config.py:2132` | `enabled_mcp_server_names` | `(config or {}).get(...) or {}` 双兜底 |
| `mcp_servers.<name>.enabled` | `True` | `hermes_cli/tools_config.py:2137` | `enabled_mcp_server_names` → `_parse_enabled_flag` | 仅 false/0/no/off 关;无法识别值 → 开;值非 dict → 该 server 不算启用 |
| `agent.disabled_toolsets` | `[]` | 读 `:2487-2491`;对账 `:2601-2612` | `_get_platform_tools` / `_save_platform_tools` | 最后一道全局减法,压过一切 |
| `context.engine` | `"compressor"` | `hermes_cli/tools_config.py:2441-2444` | `_get_platform_tools` | 非 dict → `{}`;非 compressor 时注入 `context_engine` 工具集,但尊重显式空选 |
| `tts.provider` | 无 | `:3594`(托管)/ `:3610`(普通)/ 判定 `:3388-3389` | `_is_provider_active` / `_toolset_needs_configuration_prompt` | 缺键 = 未配置 |
| `stt.provider` | `"local"` | `:3599`(托管)/ `:3613`(普通) | `_is_provider_active` | 普通路径 `or "local"`;托管路径无此兜底 |
| `web.backend` | 无 | `:3606`(托管)/ `:3619`(普通)/ 判定 `:3391-3392` | 同上 | 缺键 = 未配置 |
| `web.search_backend` / `web.extract_backend` | — | 仅 docstring `hermes_cli/tools_config.py:2951-2952` | `web_provider_capabilities` | 本段只描述不读写 |
| `browser.cloud_provider` | 无 | `:3602`(托管)/ `:3616`(普通)/ 判定 `:3394-3395` | 同上 | 缺键 = 未配置 |
| `image_gen.provider` | 无(视同 `"fal"`) | `:3560` / `:3576` / `:3625` | `_is_provider_active` | `{None,"","fal"}` 都算 FAL |
| `image_gen.use_gateway` | 缺省假 | `:3579` / `:3629` | `_is_provider_active` | 经 `is_truthy_value(..., default=False)`;显式假会否掉托管激活 |
| `image_gen.model` | `catalog_fn` 的第二返回值 | 读 `:3709`,写 `:3747` | `_configure_imagegen_model` | 不在目录里就回落默认;不落盘,靠调用方 `save_config` |
| `video_gen.provider` | 无(视同 `"fal"`) | `:3565` / `:3586` | `_is_provider_active` | 同 image_gen |
| `video_gen.use_gateway` | 缺省假 | `:3588` | `_is_provider_active` | 同 image_gen |
| `tts.piper.voice` | `en_US-lessac-medium` | 提示文本 `hermes_cli/tools_config.py:1859` | `_run_post_setup("piper")` | 本段只打印指引,不读该键 |
| `computer_use.cua_telemetry` | 默认关 | 仅 docstring `hermes_cli/tools_config.py:771` | `_cua_driver_env`(转交 `cua_backend`) | 本段不直接读 |

### 环境变量

| 变量 | 读取点 @863e313 | 读它的函数 | 说明 |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `hermes_cli/tools_config.py:2077` | `_get_enabled_platforms` | 非空即"telegram 已配置" |
| `DISCORD_BOT_TOKEN` | `hermes_cli/tools_config.py:2079` | 同上 | |
| `SLACK_BOT_TOKEN` | `hermes_cli/tools_config.py:2081` | 同上 | |
| `WHATSAPP_ENABLED` | `hermes_cli/tools_config.py:2083` | 同上 | **非空即真**,`WHATSAPP_ENABLED=0` 也算开 |
| `QQ_APP_ID` | `hermes_cli/tools_config.py:2085` | 同上 | |
| `XAI_API_KEY` | 存在性 `hermes_cli/tools_config.py:189/196/197`;post-setup 读 `:1954`、写 `:2000` | `_xai_credentials_present` / `_run_post_setup("xai_grok")` | fallback 链:xAI OAuth token store → `tools.xai_http.get_env_value` → `agent.secret_scope.get_secret` → `os.environ`(仅 secret_scope 导入失败时) |
| `HASS_TOKEN` | `hermes_cli/tools_config.py:205` | `_homeassistant_credentials_present` | 经 `agent.secret_scope.get_secret`(profile 感知);异常 → False |
| `HASS_URL` | 声明于 `hermes_cli/tools_config.py:670`,默认 `http://homeassistant.local:8123` | `_toolset_has_keys` / `provider_readiness_status` 遍历 `env_vars` | |
| `CAMOFOX_URL` | 声明于 `hermes_cli/tools_config.py:652`,默认 `http://localhost:9377` | 同上 | 见 D-5 |
| `HERMES_LANGFUSE_PUBLIC_KEY` / `_SECRET_KEY` / `_BASE_URL` | 声明于 `hermes_cli/tools_config.py:717-733` | 同上 | `_BASE_URL` 默认 `http://localhost:3000` |
| `BROWSER_USE_API_KEY` | `override_env_vars` 于 `hermes_cli/tools_config.py:639` | 托管 browser 行 | 托管行本身 `env_vars: []` |
| `VOICE_TOOLS_OPENAI_KEY` / `OPENAI_API_KEY` | `override_env_vars` 于 `:341` / `:434`;`env_vars` 于 `:348` / `:441` | TTS / STT 行 | |
| `FAL_KEY` | `override_env_vars` 于 `:541` / `:561` | 托管 image/video 行 | |
| `FIRECRAWL_API_KEY` / `FIRECRAWL_API_URL` | `override_env_vars` 于 `:507` | 托管 web 行 | |
| `GROQ_API_KEY` / `ELEVENLABS_API_KEY` / `DEEPINFRA_API_KEY` | STT 行 `env_vars` `:452-480` 区段 | 同上 | |
| `BROWSERBASE_API_KEY` / `BROWSERBASE_PROJECT_ID` | `plugins/browser/browserbase/provider.py:286-295` | 插件 schema → picker row | |
| `HERMES_CUA_DRIVER_CMD` | `hermes_cli/tools_config.py:757`(本段经 `_resolved_cua_driver_cmd` 间接用于 `:3203`/`:3273`) | `_cua_driver_cmd` / `resolve_cua_driver_cmd` | 覆盖 cua-driver 可执行文件;`tools/computer_use/cua_backend.py:728-734` 说明"给了 override 就绝不静默换别的二进制" |
| `HERMES_HOME` | 本段不直接读,但决定 `~/.hermes/config.yaml` 与 `.env` 位置 | `hermes_cli.config` | 测试用它隔离(见 `tests/hermes_cli/test_post_setup_gating.py:22`) |

`env_vars` 项的通用读法是 `get_env_value(e["key"])`(`hermes_cli/tools_config.py:2658` 与
`:3317`),即 `os.environ`(经 secret_scope)→ `~/.hermes/.env`。

---

## 14. 文档-代码出入汇总

| # | 文档怎么说 | 代码怎么做 | 溯源 |
|---|---|---|---|
| C-1 | `known_builtin_toolsets` "Recorded from the full catalog, since that is what the picker showed" | 记的是裸 `CONFIGURABLE_TOOLSETS`,未按平台过滤、未剔除 `_CONFIG_ONLY_TOOLSETS`、不含插件;picker 三者都做了 | `hermes_cli/tools_config.py:2581` vs `:2742-2746` |
| C-2 | `newly_enabled` / "the user just explicitly enabled" | 实际是"本次勾选的全部 - 保留条目",不是新增 diff | `hermes_cli/tools_config.py:2605` |
| C-3 | `IMAGEGEN_BACKENDS` 每项暴露 `config_key` / `model_catalog_fn` / `default_model` | 实际字段是 `display` / `config_key` / `catalog_fn`,默认模型由 `catalog_fn` 第二返回值给 | `hermes_cli/tools_config.py:3655-3657` vs `:3670-3676` |
| C-4 | x_search 自动开启"Only fires when the user has not yet saved an explicit toolset list" | 判定用的是 `has_explicit_config`;保存了空列表或纯复合列表时仍会触发 | `hermes_cli/tools_config.py:2337-2339` vs `:2262` |
| C-5 | cron 文档写 `_DEFAULT_OFF_TOOLSETS ({moa, homeassistant, rl})` | 实际是 `{homeassistant, spotify, discord, discord_admin, video, video_gen, x_search, a2a}`,`moa`/`rl` 都不在其中 | `cron/scheduler.py:235` vs `hermes_cli/tools_config.py:156` |
| C-6 | 模块 docstring 把本文件说成 `hermes tools` / `hermes setup tools` 的入口 | `_get_platform_tools` 同时是 gateway / cron / api_server / oneshot / doctor / kanban 等 15+ 个非交互路径的运行时工具解析器 | `hermes_cli/tools_config.py:1-10` vs 上文 §0 调用点清单 |

---

## 15. 可疑缺陷汇总(只记录不修)

| # | 现象 | 怎么会踩到 | 溯源 |
|---|---|---|---|
| D-1 | 显式空工具集列表 + xAI 凭据 → `x_search` 自动回来 | 用户在 picker 里取消全部勾选期望零工具;实测 `{'platform_toolsets':{'cli':[]}}` → `['kanban','x_search']` | `hermes_cli/tools_config.py:2340-2345` vs `:2445-2449` |
| D-2 | `mcp_servers.<n>.enabled: false` 的 server 若留在 `platform_toolsets` 里,既穿透全局禁用又废掉 allowlist | 用户临时下线某 MCP server,但名字被 `_save_platform_tools` 作为 `preserved_entries` 留着;实测多带出被禁 server + 全部启用 server | `hermes_cli/tools_config.py:2472-2479` + `:2555-2558` |
| D-3 | 渲染一次 toolset checklist = N 次 `load_config()` + 多次 Portal 网络往返 | `and` 短路顺序把便宜的表查询放在昂贵调用之后,且不传 `config`/`features`;`force_fresh` 默认 True | `hermes_cli/tools_config.py:2751-2754` + `:2730` + `hermes_cli/nous_account.py:330-332` |
| D-4 | 在 checklist 上按 ESC 也会把隐式复合冻结成显式列表 | `cancel_returns=pre_selected`,调用方不区分"取消"与"确认" | `hermes_cli/tools_config.py:2782` + `:4901` |
| D-5 | 同时有 env_vars 和 post_setup 的 provider,key 配齐即报 `ready`,安装检查被跳过 | Camofox / Langfuse / Browserbase 三类行;实测 `_camofox_installed()=False` 时仍返回 `'ready'` | `hermes_cli/tools_config.py:3315-3319` vs `:3264-3274` |
| D-6 | `requires_python` 分支恒不触发 | 无任何类目声明该字段(全仓仅两处读取) | `hermes_cli/tools_config.py:3455` |
| D-7 | `platform_gate` 是死配置,从不被读 | 未来收窄的 gate 会被静默忽略 | `hermes_cli/tools_config.py:691` |
| D-8 | provider picker 默认光标可能停在"配了 key 但未激活"的行上 | STT:`stt.provider=groq` + 设了 `VOICE_TOOLS_OPENAI_KEY` → 索引返回 2(OpenAI)而非 3(Groq);回车即改回去 | `hermes_cli/tools_config.py:3641-3648` |
| D-9 | 插件 TTS provider 的 `post_setup` 不在 `valid_post_setup_keys()` 里 | `hermes tools post-setup <key>` 和 dashboard 端点会拒绝,GUI"Run setup"对 TTS 插件不可用 | `hermes_cli/tools_config.py:2026-2031` vs `:3078-3079` |
| D-10 | 声明了未实现 post_setup 键的插件,CLI 会打印"complete"并返回 0 | `_run_post_setup` 的 if/elif 链无 else 兜底;allowlist 通过 ≠ 实现存在 | `hermes_cli/tools_config.py:2062-2069`(+ 1631–2007 的分支链) |
| D-11 | `_estimate_tool_tokens` 把失败也永久缓存 | 长驻进程一次瞬时导入失败 → 该进程此后永无 token 估算 | `hermes_cli/tools_config.py:2699-2702` |
| D-12 | `_visible_providers` 用类目**显示名**做插件注入的 key | 改一个显示字符串(大小写、`&`)插件行就静默消失,无断言保护 | `hermes_cli/tools_config.py:3137/3142/3150/3158/3164` |
| D-13 | 所有 `_plugin_*_providers` 的 `except: return []` / `continue` 静默吞异常 | 一个坏插件让整个类目的插件行消失,日志里什么也没有 | `hermes_cli/tools_config.py:2826-2827` 等五处同构 |
| D-14 | `WHATSAPP_ENABLED=0` 会把 whatsapp 算成已启用平台 | 用 `get_env_value(...)` 真值判断而非 `is_truthy_value` | `hermes_cli/tools_config.py:2083` |
| D-15 | `_is_provider_active` 的 image_gen 插件分支缺 `and not managed_nous_feature`(video_gen 有) | 今天无害;若插件注册托管 image 行会走错分支 | `hermes_cli/tools_config.py:3557-3565` |

---

## 16. 配套测试(行为规格)

- `tests/hermes_cli/test_tools_config.py`(744 行,28 tests)—— 本段主规格。覆盖:#38798 告警的
  全无效/全有效/部分有效三态(`:36/:53/:63`)、HASS_TOKEN 豁免与 profile 感知(`:83/:104`)、
  discord 工具集不泄漏到其他平台(`:125`)、vision 的 codex auth(`:141`)、
  `_save_platform_tools` 保留 MCP 名(`:158`)、数字 MCP server 名不炸 sorted(`:312`)、
  `_get_effective_configurable_toolsets` 对捆绑插件去重(`:432`)、kanban 不进 diff(`:476`)、
  `_visible_providers` 复用 feature 快照(`:548/:580`)、以及 `_RECENTLY_SHIPPED_TOOLSETS` 的四条
  规格(`:680` 回填 / `:696` 取消勾选粘住 / `:710` `agent.disabled_toolsets` 仍压过 /
  `:721` 窄复合保持窄)。
- `tests/hermes_cli/test_post_setup_gating.py`(42 行,2 tests)—— #22737 的回归钉:
  cua-driver 不在 PATH 时 `_toolset_needs_configuration_prompt("computer_use", {})` 必须为 True;
  谓词抛异常必须当"已满足"。
- `tests/hermes_cli/test_tool_token_estimation.py`(101 行)—— `_estimate_tool_tokens` 的缓存与
  降级。
- `tests/cli/test_cli_tools_command.py`(101 行)—— CLI 层。
- `tests/cron/test_scheduler.py` —— cron 侧 MCP 语义镜像。
- `tests/gateway/test_api_server_toolset.py`、`tests/gateway/test_session_api.py`、
  `tests/gateway/test_api_server.py` —— gateway 消费侧。
- picker 相关:`tests/hermes_cli/test_tts_picker.py`、`test_stt_picker.py`、
  `test_image_gen_picker.py`、`test_video_gen_picker.py`。
- `tests/hermes_cli/test_setup_blank_slate.py` —— #49995 对账场景。

**实跑结果**(`HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh
tests/hermes_cli/test_tools_config.py tests/hermes_cli/test_post_setup_gating.py
tests/hermes_cli/test_tool_token_estimation.py`):
`3 files, 32 tests passed, 0 failed`。

---

## 17. 重实现要点

如果要从零重写这一段(平台工具集解析 + provider 配置),必须知道:

1. **"保存"是一个不可逆的语义跃迁,必须显式建模。** 平台从"隐式复合名"变成"冻结的显式清单"
   之后,再没有任何东西会往清单里加东西 —— 新版本的新工具集对这些用户永远缺席。
   hermes 用 `_RECENTLY_SHIPPED_TOOLSETS` 打补丁,并被迫写下"必须与工具集同版本发布、下一版
   必须清空"的运维约束(`:2172-2178`)。**更好的设计是给保存的清单打上 schema 版本号**,
   升级时按版本做迁移,而不是靠一个必须手工维护的常量。

2. **反查(工具名 → 工具集)必须比静态成员,不能比运行时成员。** 否则任何往工具集里注册工具的
   插件/覆盖层都会把该工具集整片关掉(#49622)。这意味着你的工具集解析 API 从第一天起就要有
   `include_registry` 这样的开关,而不是事后加。

3. **"零 API key" ≠ "可用"。** 至少要区分四态:keys 缺 / 需要登录 / 需要安装 / 就绪。
   hermes 的 `provider_readiness_status` 是这个教训的产物,但它自己还留着一个 early-return
   把"有 key 且配齐"直接判为就绪(D-5)—— 正确做法是**每一维独立判定后取交集**,而不是
   按优先级 early-return。

4. **区分"从没问过"与"问过被拒"需要一本账。** hermes 有两本(`known_plugin_toolsets` /
   `known_builtin_toolsets`)。没有这本账,"新能力默认开"和"尊重用户关掉"这两条需求是矛盾的。
   账要记的是**当时展示给用户的全集**,不是当前的全集,也不能是未过滤的原始目录(C-1)。

5. **全局禁用列表与逐平台勾选必须双向对账。** 一个"最后再减一次"的全局黑名单会让 UI 的开关
   "保存成功但永不生效"(#49995)。写入侧必须在保存时把用户刚开的项从黑名单里摘掉,
   否则用户会陷入"点了没反应"的死循环。

6. **一个凭据/开关的 fallback 链要在一个地方定义,并被所有消费者共用。** hermes 把
   `enabled_mcp_server_names` 明确定位成"gateway/CLI 与 cron 共用的唯一 MCP 成员判定"
   (`:2126-2128`),但 cron 仍然复刻了一遍 allowlist/哨兵的三条规则(`cron/scheduler.py:190`)
   —— 结果是两处必须同步演进。**要么共用函数,要么共用数据结构,不要共用注释。**

7. **picker 的"当前选中项"检测要分两遍扫。** 先扫"真的激活",全都不匹配再扫"看起来配过了"。
   在一个循环里混着做,前面的弱信号会盖掉后面的强信号(D-8),而这个 bug 的后果是
   "用户回车一下就把配置改回去了"。

8. **插件注入点用稳定标识(注册键)而不是显示字符串。** hermes 用类目 display name 匹配注入
   (`cat.get("name") == "Image Generation"`),改一个文案就静默失去所有插件 provider(D-12)。
