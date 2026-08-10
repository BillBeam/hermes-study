# r8a-raw-tools-config-a · hermes_cli/tools_config.py:1-1900

底稿。基线 `863e313`,精读对象 `hermes_cli/tools_config.py` 第 1–1900 行(全文 5452 行)。
本段的实际内容 = **声明式注册表**(第 91–749 行)+ **post-setup 安装钩子体系**(第 752–2009 行的前 3/4)。
消费这些声明的解析器(`_get_platform_tools` / `_save_platform_tools` / `_visible_providers` / `provider_readiness_status`)在 1900 行之后,
但"开关粒度与优先级"这个问题必须跨到那边才能答完整,所以本底稿把消费端也溯了源,并在标题里注明「本段外」。

约定:凡断言紧跟 `路径:行号 @ 863e313` + 原文块。路径相对基线仓库根。

---

## 0. 这个模块在系统里的位置

模块自述:两个 CLI 入口共用它,产物落在 `~/.hermes/config.yaml` 的 `platform_toolsets` 键下。`hermes_cli/tools_config.py:4 @ 863e313`

```python
`hermes tools` and `hermes setup tools` both enter this module.
```

```python
Saves per-platform tool configuration to ~/.hermes/config.yaml under
```
`hermes_cli/tools_config.py:8 @ 863e313`

所以本文件是**配置面(control plane)**:它决定"哪些工具的 schema 会被塞进模型请求",但它自己不定义任何工具。
工具组的权威定义在仓库根的 `toolsets.py`。

---

## 1. 机制:toolset 与单个工具的关系 —— 三层名字空间

**解决什么问题**:一个 harness 有上百个工具;逐个工具做开关,配置文件会爆炸,而且用户不知道 `browser_cdp` 是什么。
需要一个"人能理解的粒度"。

**怎么实现**:三层。

**第一层 · 工具名**。`toolsets.py` 里有一个共享列表 `_HERMES_CORE_TOOLS`,枚举 62 个工具名,所有 CLI/消息平台 composite 都引用它。`toolsets.py:31 @ 863e313`

```python
_HERMES_CORE_TOOLS = [
```

**第二层 · toolset**。`TOOLSETS` 字典把工具名分组;一个 toolset 要么直接列 `tools`,要么用 `includes` 组合别的 toolset。
例如 `video` 组只有一个工具:`toolsets.py:134 @ 863e313`

```python
    "video": {
```

**第三层 · platform composite**。平台默认 toolset(`hermes-cli`、`hermes-discord` …)本身也是 TOOLSETS 的条目,
但它的 `tools` 是"整包"。Discord 的包 = 核心 62 个 + 两个 Discord 原生工具:`toolsets.py:486-493 @ 863e313`

```python
    "hermes-discord": {
        "description": "Discord bot toolset - full access (terminal has safety checks via dangerous command approval)",
        "tools": _HERMES_CORE_TOOLS + [
            "discord",
            "discord_admin",
        ],
        "includes": []
    },
```

**tools_config.py 里的 `CONFIGURABLE_TOOLSETS` 是第四个东西:UI 清单,不是权威。** 它只是"给用户看的复选框列表",
每项三元组 `(toolset_name, label, description)`,注释明说这些 key 映射到 `toolsets.py` 的 `TOOLSETS`。`hermes_cli/tools_config.py:93-96 @ 863e313`

```python
# Toolsets shown in the configurator, grouped for display.
# Each entry: (toolset_name, label, description)
# These map to keys in toolsets.py TOOLSETS dict.
CONFIGURABLE_TOOLSETS = [
```

清单第一项(顺序 = TUI 里的显示顺序):`hermes_cli/tools_config.py:97 @ 863e313`

```python
    ("web",             "🔍 Web Search & Scraping",    "web_search, web_extract"),
```

清单末项(computer_use,25 项):`hermes_cli/tools_config.py:123 @ 863e313`

```python
    ("computer_use",     "🖱️  Computer Use (macOS/Windows/Linux)", "background desktop control via cua-driver"),
```

**关键不对称(必须记住)**:`CONFIGURABLE_TOOLSETS` ⊄ `TOOLSETS`,`TOOLSETS` ⊄ `CONFIGURABLE_TOOLSETS`。
- `stt` 在 UI 清单里(第 109 行),但 `toolsets.py` 里**没有** `stt` 这个 toolset(`grep '"stt"' toolsets.py` 无匹配)——它零工具。
- `kanban`、`discord`(作为非配置项被"recover")等在 `TOOLSETS` 里但不在 UI 清单里,由 `_get_platform_tools` 的 recovery 环节补回。`hermes_cli/tools_config.py:2374-2379 @ 863e313`

```python
    # Recover non-configurable platform toolsets (e.g. discord, feishu_doc,
```

**为什么这么设计**:UI 清单要稳定、要可排版(emoji + 中文可读描述),而 toolset 定义要跟着工具实现走。
把两者解耦,新增一个工具不必动 UI;新增一个 UI 分组也不必动工具注册。

**取舍**:两张表会漂移。仓库用三种补丁堵漏:recovery 环节(补回不在 UI 清单里的平台原生 toolset)、
`_RECENTLY_SHIPPED_TOOLSETS`(补回"存盘之后才发布"的 toolset)、以及 `#38798` 的"全无效名"运行时告警。
这三样都是漂移税。

---

## 2. 机制:开关的粒度与优先级 —— 谁压谁

**解决什么问题**:用户可以从 5 个地方表达"我要/不要这个工具组":平台默认包、`hermes tools` 存的显式列表、
`agent.disabled_toolsets` 全局黑名单、凭据自动开、per-job 覆盖。必须有确定的合并顺序。

**完整优先级链**(从低到高;标 ▲ 的实现在本段之外,已溯源):

**(0) 兜底**:平台没存过列表 → 用 `PLATFORMS[platform]["default_toolset"]`;平台连注册表都没有 → 猜 `hermes-{platform}`。▲ `hermes_cli/tools_config.py:2240-2247 @ 863e313`

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

**(1) 隐式推断**:没有显式配置时,把 composite 展开成工具名集合,再对每个 UI 清单 toolset 做**静态成员子集判定**——
toolset 的静态工具全在 composite 里 → 认为它开着。▲ `hermes_cli/tools_config.py:2326-2328 @ 863e313`

```python
            ts_tools = set(resolve_toolset(ts_key, include_registry=False))
            if ts_tools and ts_tools.issubset(all_tool_names):
                enabled_toolsets.add(ts_key)
```

注意 `include_registry=False`:必须比**静态**成员,否则一个插件往 `terminal` 组里注册了新工具,
composite 没列它,整个 `terminal` 组就被判定为关(issue #49622)。

**(2) 显式列表压过隐式**:只要存盘列表里出现**任何一个** UI 清单 key,就走"直接成员"分支。▲ `hermes_cli/tools_config.py:2262 @ 863e313`

```python
    has_explicit_config = any(ts in configurable_keys for ts in toolset_names)
```

这是本文件最重要的一行:它把"整组开/关"和"单个 toolset 覆盖"接在一起 —— **一旦用户在 `hermes tools` 里存过盘,
存盘列表就是白名单,composite 的推断退居次席**(混合列表 `[hermes-cli, spotify]` 里 composite 仍会被展开,
但展开结果要再减 `_DEFAULT_OFF_TOOLSETS`,而用户显式列的 `spotify` 不减)。▲ `hermes_cli/tools_config.py:2297 @ 863e313`

```python
            default_off = set(_DEFAULT_OFF_TOOLSETS)
```

**(3) MCP 服务器名共用同一个列表**。`platform_toolsets` 里出现的非 toolset 名被当作 MCP server 名;
列了就是白名单,没列就把全局启用的都放进来;哨兵 `no_mcp` 一票否决。▲ `hermes_cli/tools_config.py:2466-2469 @ 863e313`

```python
    # Special sentinel: "no_mcp" in the toolset list disables all MCP servers.
    enabled_mcp_servers = enabled_mcp_server_names(config)
    # Allow "no_mcp" sentinel to opt out of all MCP servers for this platform
    if "no_mcp" in toolset_names:
```

**(4) `agent.disabled_toolsets` 最后减,压过以上一切**。▲ `hermes_cli/tools_config.py:2483-2491 @ 863e313`

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

**(4') 写回时反向和解**:因为 (4) 是最后一道减法,单纯往 `platform_toolsets` 写"开"是**写不进去的**——
存盘看似成功,读取时又被减掉。`_save_platform_tools` 因此在存盘时把"本次显式开启的 key"从全局黑名单里剔除。▲ `hermes_cli/tools_config.py:2601-2612 @ 863e313`

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

**(5) 更上层还有 per-job 覆盖**:cron 的每个 job 可带 `enabled_toolsets`,它整个短路掉 `_get_platform_tools`。`cron/scheduler.py:240-242 @ 863e313`

```python
    per_job = job.get("enabled_toolsets")
    if per_job:
        return _merge_mcp_into_per_job_toolsets(list(per_job), cfg or {})
```

**(6) 最后一道闸不在配置里,在工具自己身上**:`check_fn`。即使 toolset 开着,工具的 `check_fn` 不过 schema 也不注册。
本段的注释把这个分工说得很清楚(以 `x_search` 为例):`hermes_cli/tools_config.py:153-154 @ 863e313`

```python
# `hermes tools` → X (Twitter) Search setup walks users through credential
# setup. The tool's check_fn means the schema still won't appear to the
```

**取舍**:六层优先级,没有一个地方能"一眼看全"。代价是排障困难(一个工具没出现在 schema 里,
可能是 6 个原因之一),收益是每一层都对应一个真实的、独立演化的需求方(平台默认 / 用户交互 / 全局策略 / 任务级 / 运行时凭据)。

---

## 3. 机制:默认开哪些 —— 两套彼此独立的"默认关"

**解决什么问题**:新装用户不该被 25 个 toolset 的 schema 淹没(token 成本 + 模型注意力),
也不该在没配凭据时看到一堆必然失败的工具。

**实现一 · composite 成员资格(真正的主开关)**。不在 `_HERMES_CORE_TOOLS` 里的工具,其 toolset 永远过不了 §2(1) 的子集判定。
实测(对 `toolsets.py` 的 `_HERMES_CORE_TOOLS` 做成员检查):`video_analyze`、`video_generate`、`x_search`、Spotify、Discord 的工具**都不在**核心包里;
只有 `ha_*`(Home Assistant)、`computer_use`、`bfl_flux3_*` 在。

**实现二 · `_DEFAULT_OFF_TOOLSETS` 显式减法**。`hermes_cli/tools_config.py:156 @ 863e313`

```python
_DEFAULT_OFF_TOOLSETS = {"homeassistant", "spotify", "discord", "discord_admin", "video", "video_gen", "x_search", "a2a"}
```

它的注释给了两条"为什么":视频生成是小众、付费、慢;`x_search` 无凭据时无意义。`hermes_cli/tools_config.py:146-152 @ 863e313`

```python
# Video gen is off by default — it's a niche, paid, slow feature. Users
# who want it opt in via `hermes tools` → Video Generation, which walks
# them through provider + model selection.
#
# X search is off by default for users without xAI credentials, but
# auto-enables when SuperGrok OAuth tokens are stored OR XAI_API_KEY is
# set — mirroring the HASS_TOKEN → homeassistant auto-enable below. The
```

**这两套的交集只有 `homeassistant` 和 `discord`/`discord_admin`**:它们的工具确实在 composite 里(`ha_*` 在核心包;
`discord`/`discord_admin` 在 `hermes-discord` 包里),所以只有对它们,`_DEFAULT_OFF_TOOLSETS` 的减法才真正起作用。
对 `spotify`(插件 toolset)它起的是另一个作用 —— 见 §5。对 `video` / `video_gen` / `x_search` / `a2a`,这行减法是**冗余的保险**。

**实现三 · 凭据存在即自动开(两处对称)**。Home Assistant:▲ `hermes_cli/tools_config.py:2362-2363 @ 863e313`

```python
        if "homeassistant" in default_off and _homeassistant_credentials_present():
            default_off.remove("homeassistant")
```

`x_search` 需要**两步**(注入 + 免减),因为它的工具不在 composite 里,子集判定捞不到它:▲ `hermes_cli/tools_config.py:2340-2345 @ 863e313`

```python
        x_search_auto_enabled = (
            _toolset_allowed_for_platform("x_search", platform)
            and _xai_credentials_present()
        )
        if x_search_auto_enabled:
            enabled_toolsets.add("x_search")
```

▲ `hermes_cli/tools_config.py:2367-2368 @ 863e313`

```python
        if x_search_auto_enabled and "x_search" in default_off:
            default_off.remove("x_search")
```

**关键限制**:自动开只在 else 分支(无显式配置)里。注释明写"用户一旦存盘,存盘列表就是权威"。`hermes_cli/tools_config.py:2337-2339 @ 863e313`

```python
        # through ``hermes tools`` to flip the toolset on. Only fires when
        # the user has not yet saved an explicit toolset list — once they
        # do, the saved list is authoritative.
```

**凭据探针本身(本段内)**。xAI:先试 OAuth 令牌存储,再试 `XAI_API_KEY`(三条 fallback)。`hermes_cli/tools_config.py:168 @ 863e313`

```python
def _xai_credentials_present() -> bool:
```

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

这里"`_read_xai_oauth_tokens()` 不抛异常即视为有凭据"是安全的:该函数在无令牌/缺 access_token/缺 refresh_token 时都抛 `AuthError`。`hermes_cli/auth.py:4479-4484 @ 863e313`

```python
    if not state:
        raise AuthError(
            "No xAI OAuth credentials stored. Select xAI Grok OAuth (SuperGrok / Premium+) in `hermes model`.",
            provider="xai-oauth",
            code="xai_auth_missing",
            relogin_required=True,
        )
```

Home Assistant 探针走 profile-scoped secret,不读 `.env`:`hermes_cli/tools_config.py:200-207 @ 863e313`

```python
def _homeassistant_credentials_present() -> bool:
    """Return whether the active profile has a Home Assistant token."""
    try:
        from agent.secret_scope import get_secret

        return bool((get_secret("HASS_TOKEN", "") or "").strip())
    except Exception:
        return False
```

**实现四 · `_CONFIG_ONLY_TOOLSETS`:根本不是 toolset 的"能力"**。`hermes_cli/tools_config.py:159-165 @ 863e313`

```python
# Config-only capabilities: they appear in `hermes tools` for provider/API-key
# configuration (TOOL_CATEGORIES) but are NOT model toolsets — they ship zero
# tool schemas and their on/off switch lives in their own config section
# (e.g. ``stt.enabled``), not ``platform_toolsets``. Excluded from the
# per-platform enable/disable checklist; configured via the "Reconfigure an
# existing tool" flow and the GUI provider matrix instead.
_CONFIG_ONLY_TOOLSETS = {"stt"}
```

这个注释是准确的:`stt.enabled` 确实是真键,读它的是 `tools/transcription_tools.py:157-161 @ 863e313`

```python
def is_stt_enabled(stt_config: Optional[dict] = None) -> bool:
    """Return whether STT is enabled in config."""
    if stt_config is None:
        stt_config = _load_stt_config()
    enabled = stt_config.get("enabled", True)
```

GUI 侧的写入端同样按 `_CONFIG_ONLY_TOOLSETS` 分叉:`hermes_cli/web_routers/tools.py:88-91 @ 863e313`

```python
        target_platform = _toolset_configuration_platform(name)
        if name in _CONFIG_ONLY_TOOLSETS:
            # Config-only capabilities (stt) have no per-platform toolset —
            # their switch is their own config section (e.g. stt.enabled).
```

**实现五 · `_RECENTLY_SHIPPED_TOOLSETS` 反向补丁**(本段外,但和"默认开哪些"同一话题)。
`hermes_cli/tools_config.py:2185 @ 863e313`

```python
_RECENTLY_SHIPPED_TOOLSETS = frozenset({"bfl"})
```

它的设计约束值得抄:**必须与它命名的 toolset 同一个 release 发布,下一个 release 必须清空**,
否则用户的"取消勾选"会被当成"没见过"再打开。`hermes_cli/tools_config.py:2172-2178 @ 863e313`

```python
#: MUST ship in the same release as the toolset it names, and be emptied in the
#: next one. The inference only holds while no released build has put the
#: toolset on a checklist: once one has, a user who unchecks it writes a config
#: byte-identical to one saved before the toolset existed (the record below is
#: only written from that point on), and this rule turns their opt-out back on.
#: Landing late — or leaving an entry here for a second release — converts a
#: back-fill into a stuck checkbox.
```

---

## 4. 机制:平台限定(toolset × platform 的可见性矩阵)

**解决什么问题**:Discord 服务器管理工具对 Telegram 用户毫无意义,但如果每个平台的清单都列 25 项,清单就成了噪音。

**怎么实现**:一张"限制表",不在表里的 toolset 处处可用(默认放行)。`hermes_cli/tools_config.py:216-219 @ 863e313`

```python
_TOOLSET_PLATFORM_RESTRICTIONS: Dict[str, Set[str]] = {
    "discord": {"discord"},
    "discord_admin": {"discord"},
}
```

判定函数(注意 `allowed is None` 才放行,空集合会全部拒绝):`hermes_cli/tools_config.py:222-228 @ 863e313`

```python
def _toolset_allowed_for_platform(ts_key: str, platform: str) -> bool:
    """Return True if ``ts_key`` is configurable on ``platform``.

    Toolsets without a restriction entry are allowed everywhere (the default).
    """
    allowed = _TOOLSET_PLATFORM_RESTRICTIONS.get(ts_key)
    return allowed is None or platform in allowed
```

这个谓词在**三个地方**同时生效,构成"读—写—展示"的闭环:
- 读:`_get_platform_tools` 的两个分支都过滤(§2)。
- 写:`_save_platform_tools` 先剪掉不适用的 key,防止"配置所有平台"把 discord toolset 写进 telegram。▲ `hermes_cli/tools_config.py:2532-2535 @ 863e313`

```python
    enabled_toolset_keys = {
        ts for ts in enabled_toolset_keys
        if _toolset_allowed_for_platform(ts, platform)
    }
```

- 展示:`_checklist_toolset_keys` = 清单实际渲染的全集。`hermes_cli/tools_config.py:298-303 @ 863e313`

```python
    return {
        ts_key
        for ts_key, _, _ in _get_effective_configurable_toolsets()
        if _toolset_allowed_for_platform(ts_key, platform)
        and ts_key not in _CONFIG_ONLY_TOOLSETS
    }
```

它存在的理由写得很好:**diff 的范围必须等于用户能看见的复选框范围**,否则 `hermes tools` 会宣称"添加了 X",
而 X 是 recovery 环节自动补的、用户从没见过的 toolset。`hermes_cli/tools_config.py:290-295 @ 863e313`

```python
    Non-configurable toolsets that ``_get_platform_tools`` resolves at read
    time — ``kanban`` and other check_fn-gated toolsets, recovered platform
    composites, MCP server names — are NOT in this set because the checklist
    never shows them. Use this to scope the added/removed diff the UI prints,
    so ``hermes tools`` never claims to add or remove a toolset the user was
    never given a checkbox for. The underlying config is unaffected — those
```

**"无平台上下文的 UI 该写到哪个平台"**:GUI 的 toolset 开关没有平台选择器,默认写 `cli`;
但一个被限制到 discord 的 toolset 写进 `cli` 会被 `_save_platform_tools` 静默丢弃、UI 却报成功,
所以要重定向到它支持的平台(取字典序最小)。`hermes_cli/tools_config.py:239-242 @ 863e313`

```python
    allowed = _TOOLSET_PLATFORM_RESTRICTIONS.get(ts_key)
    if not allowed or default in allowed:
        return default
    return sorted(allowed)[0]
```

**平台注册表本身**是从 `hermes_cli/platforms.py` 派生的,dict-of-dicts 形态是为兼容旧的 `PLATFORMS[key]["label"]` 写法。`hermes_cli/tools_config.py:308-313 @ 863e313`

```python
from hermes_cli.platforms import PLATFORMS as _PLATFORMS_REGISTRY

PLATFORMS = {
    k: {"label": info.label, "default_toolset": info.default_toolset}
    for k, info in _PLATFORMS_REGISTRY.items()
}
```

22 个内置平台,每个带 `default_toolset`:`hermes_cli/platforms.py:22 @ 863e313`

```python
    ("cli",            PlatformInfo(label="🖥️  CLI",            default_toolset="hermes-cli")),
```

---

## 5. 机制:插件 toolset 的合流与去重

**解决什么问题**:插件也想往 `hermes tools` 的清单里加一行,但内置条目和 bundled 插件可能撞 key(如 `spotify`)。

**怎么实现**:内置在前、插件追加在后,key 撞了以内置为准。`hermes_cli/tools_config.py:256-268 @ 863e313`

```python
    result = list(CONFIGURABLE_TOOLSETS)
    seen = {ts_key for ts_key, _, _ in result}
    try:
        from hermes_cli.plugins import discover_plugins, get_plugin_toolsets
        discover_plugins()  # idempotent — ensures plugins are loaded
        for entry in get_plugin_toolsets():
            if entry[0] in seen:
                continue
            seen.add(entry[0])
            result.append(entry)
    except Exception:
        pass
    return result
```

**为什么内置赢**:注释说没有去重的话,"reconfigure existing" 会把同一个 toolset 列两次。`hermes_cli/tools_config.py:248-253 @ 863e313`

```python
    Plugin toolsets are appended at the end so they appear after the
    built-in toolsets in the TUI checklist. A plugin whose toolset key
    already appears in ``CONFIGURABLE_TOOLSETS`` is skipped — bundled
    plugins (e.g. ``plugins/spotify``) share their toolset key with the
    built-in entry, and we want the built-in label/description to win.
    Without the dedupe, ``hermes tools`` → "reconfigure existing" would
```

**插件 toolset 的三态默认**(本段外,但只有看了它才知道 `_DEFAULT_OFF_TOOLSETS` 对插件的作用):
显式列出 → 开;在 `_DEFAULT_OFF_TOOLSETS` → 关;不在 `known_plugin_toolsets[platform]`(= 装了新插件,用户没见过)→ 默认开。▲ `hermes_cli/tools_config.py:2423-2433 @ 863e313`

```python
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

**GUI 的 label 清洗**:注册表 label 形如 `<emoji> <title>`,HTTP API 要去掉前缀 emoji。判据是"首个 token 不含任何 ASCII 字母数字"。`hermes_cli/tools_config.py:133-138 @ 863e313`

```python
    text = (label or "").strip()
    if not text:
        return text
    parts = text.split(None, 1)
    if len(parts) == 2 and parts[0] and not any(ch.isascii() and ch.isalnum() for ch in parts[0]):
        return parts[1].strip()
    return text
```

注释明确只有 HTTP API 调它,CLI/TUI 用原始 label。`hermes_cli/tools_config.py:130-131 @ 863e313`

```python
    Registry labels use ``<emoji> <title>``; plugin toolsets prefix with ``🔌``.
    CLI/TUI keeps the raw ``label`` — only HTTP APIs call this helper.
```

---

## 6. 机制:`TOOL_CATEGORIES` —— provider 矩阵(第二张注册表)

**解决什么问题**:`CONFIGURABLE_TOOLSETS` 回答"要不要这组工具";但 `tts` / `web` / `browser` 这类能力还要回答
"用哪家 provider、要哪些 key、装了没有"。这是一张正交的表。`hermes_cli/tools_config.py:317-321 @ 863e313`

```python
# Maps toolset keys to their provider options. When a toolset is newly enabled,
# we use this to show provider selection and prompt for the right API keys.
# Toolsets not in this map either need no config or use the simple fallback.

TOOL_CATEGORIES = {
```

表里 10 个 key:`tts`、`stt`、`web`、`image_gen`、`video_gen`、`x_search`、`browser`、`homeassistant`、`spotify`、`computer_use`、`langfuse`(实为 11)。
**注意 `langfuse` 不在 `CONFIGURABLE_TOOLSETS` 也不在 `_CONFIG_ONLY_TOOLSETS`** —— 它只是一个可配置项。

### 6.1 provider 行的字段词汇表(逐字段,全部来自本段)

| 字段 | 语义 | 示例行 |
|---|---|---|
| `name` / `badge` / `tag` | 显示用 | `hermes_cli/tools_config.py:328-330` |
| `env_vars` | 需要的 key 列表,每项 `{key, prompt, url?, default?}` | `:348` |
| `tts_provider` / `stt_provider` / `web_backend` / `browser_provider` / `imagegen_backend` / `video_gen_plugin_name` | 选中后写回 config 的**后端名**(每个 category 用自己的字段名) | `:331`、`:423`、`:503`、`:628`、`:542`、`:566` |
| `requires_nous_auth` | 需要 Nous 登录 | `:339` |
| `managed_nous_feature` | 走 Nous 托管网关的能力名 | `:340` |
| `override_env_vars` | 选它时要**清掉**的自有 key(否则自带 key 会盖过托管网关) | `:341` |
| `post_setup` | 安装钩子 key,见 §7 | `:357` |
| `platform_gate` | (category 级)声称限制 OS —— **无人读取,见 §10** | `:691` |
| `setup_title` / `setup_note` | picker 的标题与提示 | `:486-487` |

Nous 托管行的完整形态(TTS):`hermes_cli/tools_config.py:334-341 @ 863e313`

```python
                "name": "Nous Subscription",
                "badge": "subscription",
                "tag": "Managed OpenAI TTS billed to your subscription",
                "env_vars": [],
                "tts_provider": "openai",
                "requires_nous_auth": True,
                "managed_nous_feature": "tts",
                "override_env_vars": ["VOICE_TOOLS_OPENAI_KEY", "OPENAI_API_KEY"],
```

带 key 的普通行:`hermes_cli/tools_config.py:347-349 @ 863e313`

```python
                "env_vars": [
                    {"key": "VOICE_TOOLS_OPENAI_KEY", "prompt": "OpenAI API key", "url": "https://platform.openai.com/api-keys"},
                ],
```

带默认值的行(Camofox / Home Assistant / Langfuse 自托管):`hermes_cli/tools_config.py:652-653 @ 863e313`

```python
                    {"key": "CAMOFOX_URL", "prompt": "Camofox server URL", "default": "http://localhost:9377",
                     "url": "https://github.com/jo-inc/camofox-browser"},
```

### 6.2 顺序即默认:第 0 行是回车落点

`browser` 的注释把这条 UX 约束写成了硬要求:免费本地后端必须排第一,回车不能落在付费的 Nous 网关行上。`hermes_cli/tools_config.py:611-615 @ 863e313`

```python
        # non-provider UX setup-flow rows remain here. "Local Browser" is
        # listed FIRST so it is the default-highlighted (index 0) choice on a
        # fresh install — pressing Enter must land on the free, no-key local
        # backend, never on the paid Nous Subscription gateway row:
        #   - "Local Browser" — non-cloud option, no CloudBrowserProvider.
```

### 6.3 硬编码行 vs 插件注入行

`web` / `image_gen` / `video_gen` / `browser` / `tts` 五个 category 的**真正 provider 行是运行时注入的**,
表里留下的只是"非 provider 的 UX 流程行"(订阅行、自托管行、本地行)。`hermes_cli/tools_config.py:489-497 @ 863e313`

```python
        # Per-provider rows are injected at runtime from
        # plugins.web.<vendor>.provider via _plugin_web_search_providers()
        # in _visible_providers(). Only non-provider UX setup-flow rows
        # for the firecrawl backend are listed here:
        #   - "Nous Subscription" — managed Firecrawl billed via Nous
        #     subscription (requires_nous_auth + override_env_vars).
        #   - "Firecrawl Self-Hosted" — points firecrawl at a private
        #     Docker instance via FIRECRAWL_API_URL only.
        # See PR #25182 for the migration rationale.
```

注入点在本段外,按 `cat["name"]` **字符串**分派:▲ `hermes_cli/tools_config.py:3137-3138 @ 863e313`

```python
    if cat.get("name") == "Image Generation":
        visible.extend(_plugin_image_gen_providers())
```

`video_gen` 甚至**没有任何硬编码 provider**,全靠插件。▲ `hermes_cli/tools_config.py:3140-3143 @ 863e313`

```python
    # Inject plugin-registered video_gen backends. Unlike image_gen,
    # video_gen has NO hardcoded providers — every backend is a plugin.
    if cat.get("name") == "Video Generation":
        visible.extend(_plugin_video_gen_providers())
```

### 6.4 `TOOLSET_ENV_REQUIREMENTS`:退化的第三张表

只剩一个条目,而且**它的值从不被读**——注释说 `vision` 列在这里只是为了"注册成一个可配置 toolset"。`hermes_cli/tools_config.py:740-750 @ 863e313`

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

对应的消费端确实对 `vision` 特判、根本不看这张表:▲ `hermes_cli/tools_config.py:2628-2635 @ 863e313`

```python
    if ts_key == "vision":
        try:
            from agent.auxiliary_client import resolve_vision_provider_client

            _provider, client, _model = resolve_vision_provider_client()
            return client is not None
        except Exception:
            return False
```

而通用回退分支(对**其它**没有 `TOOL_CATEGORIES` 条目的 toolset)是"无要求即视为已配好":▲ `hermes_cli/tools_config.py:2662-2666 @ 863e313`

```python
    # Fallback to simple requirements
    requirements = TOOLSET_ENV_REQUIREMENTS.get(ts_key, [])
    if not requirements:
        return True
    return all(get_env_value(var) for var, _ in requirements)
```

---

## 7. 机制:post-setup 钩子体系

**解决什么问题**:很多 provider 不是"填个 key 就能用",还要 `npm install`、`pip install`、下载 Chromium、装二进制、跑 OAuth。
这些副作用必须能被 CLI 交互流程、GUI"运行设置"按钮、以及非交互脚本三方共用。

**怎么实现**:provider 行声明一个字符串 `post_setup`,`_run_post_setup(key)` 是一个大 if/elif 分派。`hermes_cli/tools_config.py:1631-1632 @ 863e313`

```python
def _run_post_setup(post_setup_key: str):
    """Run post-setup hooks for tools that need extra installation steps."""
```

**本段内的 11 个 hook key**(按出现顺序):`agent_browser`、`browserbase`(同一分支)、`camofox`、`cua_driver`、
`faster_whisper`、`kittentts`、`piper`、`ddgs`、`spotify`、`langfuse`、`xai_grok`。

**allowlist 而非任意调用**:`hermes tools post-setup <key>` 与 dashboard 端点都先过一遍"所有可见 provider 声明过的 key"集合。`hermes_cli/tools_config.py:2019-2024 @ 863e313`

```python
    keys: Set[str] = set()
    for cat in TOOL_CATEGORIES.values():
        for prov in cat.get("providers", []):
            ps = prov.get("post_setup")
            if ps:
                keys.add(ps)
```

**注意**:allowlist 由 `TOOL_CATEGORIES` + 四个插件 builder 生成 —— 所以 `ddgs` 这个 hook 只有在
`plugins/web/ddgs/provider.py` 被发现时才在 allowlist 里(该插件确实声明了它)。

**为什么要一个可脚本化入口**:GUI 不重实现安装逻辑,而是 spawn 一个子进程。`hermes_cli/tools_config.py:2045-2049 @ 863e313`

```python
    Runs the install/bootstrap hook a provider declares (npm install for
    browser/Camofox, pip install for kittentts/piper/ddgs, cua-driver fetch,
    etc.). This is the stable, scriptable target the dashboard spawns so the
    GUI can drive backend setup without re-implementing the install logic.
    Returns a process exit code (0 ok, 2 unknown key).
```

### 7.1 Windows"终端闪窗"抑制

**解决什么问题**:GUI spawn 的是一个无 console 的子进程;它再 spawn `npm.cmd`/`pip`/`powershell` 时,
Windows 会给每个 console 子进程**新开一个窗口**,用户点一次"运行设置"闪一屏黑框。

**怎么实现**:统一的 `creationflags` 供给函数,POSIX 返回 0 所以可以无条件传。`hermes_cli/tools_config.py:60-71 @ 863e313`

```python
    from hermes_cli._subprocess_compat import windows_hide_flags

    flags = windows_hide_flags()
    if not flags:
        return 0
    if streams_to_console:
        try:
            if sys.stdout is not None and sys.stdout.isatty():
                return 0
        except Exception:
            pass
    return flags
```

**取舍**:`streams_to_console=True` 的子进程(不重定向 stdio 的实时安装输出)如果也隐藏,
输出就掉进一个不可见的 console 里 —— 所以只在"当前进程自己没有可用 console"时才隐藏。`hermes_cli/tools_config.py:53-58 @ 863e313`

```python
    ``streams_to_console=True`` marks children spawned WITHOUT stdio
    redirection (live installer output, e.g. the verbose cua-driver install).
    Hiding those in an interactive console session would silently swallow
    their output into an invisible console, so the flag is only applied when
    the current process has no usable console of its own (stdout is a
    pipe/log file — exactly the GUI-spawn case that flashes).
```

选 `CREATE_NO_WINDOW` 而不是 `DETACHED_PROCESS` 的理由:后者会断掉 stdio 继承,`capture_output` 就废了。`hermes_cli/tools_config.py:46-49 @ 863e313`

```python
    parent materializes a brand-new console window — the "terminal flash"
    users see when clicking "Run setup". ``CREATE_NO_WINDOW`` (via
    :func:`hermes_cli._subprocess_compat.windows_hide_flags`) suppresses it
    without breaking ``capture_output`` — unlike ``DETACHED_PROCESS``, stdio
```

### 7.2 `_pip_install` 三级降级

**解决什么问题**:Windows 安装器用 `uv venv` 建虚拟环境,而 `uv venv` **不装 pip**。
所有直接 `[sys.executable, '-m', 'pip', 'install']` 的 hook 在新装机上一律 `No module named pip`。

**怎么实现**:uv → pip → ensurepip+pip 三级。`hermes_cli/tools_config.py:791-796 @ 863e313`

```python
    Strategy (in order):
    1. ``uv pip install`` if uv is on PATH — fast, doesn't need pip in the venv.
    2. ``python -m pip install`` — works on stdlib venvs.
    3. ``python -m ensurepip --upgrade`` then retry pip — covers ``uv venv``
       which creates a venv WITHOUT pip.
```

uv 用的是**托管 uv**(`ensure_uv()`),不是裸 `which`,因为 `$HERMES_HOME/bin` 不在 PATH 上。`hermes_cli/tools_config.py:814-816 @ 863e313`

```python
    from hermes_cli.managed_uv import ensure_uv

    uv_bin = ensure_uv()
```

venv 根靠 `sys.executable` 上跳两级推出,再作为 `VIRTUAL_ENV` 传给 uv:`hermes_cli/tools_config.py:805-806 @ 863e313`

```python
    venv_root = Path(sys.executable).parent.parent
    uv_env = {**os.environ, "VIRTUAL_ENV": str(venv_root)}
```

uv 失败**不**直接返回,而是继续落到 pip —— 因为失败可能只是解析冲突/网络。`hermes_cli/tools_config.py:829-830 @ 863e313`

```python
            # Fall through to pip — uv may have failed for an unrelated reason
            # (resolution conflict, network), and pip might handle it.
```

ensurepip 也失败时**合成**一个 `CompletedProcess`,让调用方走统一的失败路径而不是吃异常。`hermes_cli/tools_config.py:851-856 @ 863e313`

```python
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            # Synthesize a result so callers see a clean failure path.
            return subprocess.CompletedProcess(
                pip_cmd, returncode=1, stdout="",
                stderr=f"pip not available and ensurepip failed: {e}",
            )
```

### 7.3 browser hook:一个 key 两种语义 + 三步

`agent_browser`(本地)与 `browserbase`(云)共用同一分支,但**云 provider 在第 2 步就返回**,不装 Chromium。`hermes_cli/tools_config.py:1674-1678 @ 863e313`

```python
        # Step 2: only the local browser provider actually needs Chromium on
        # disk. Cloud providers (Browserbase, Browser Use, Firecrawl) host
        # their own Chromium and don't need the local install.
        if post_setup_key != "agent_browser":
            return
```

这解释了 §6.1 里 Nous 托管浏览器行为什么声明 `post_setup: "browserbase"` 而不是 `agent_browser`:`hermes_cli/tools_config.py:640-645 @ 863e313`

```python
                # Cloud hook: installs the agent-browser CLI only. Browser Use
                # hosts its own Chromium, so the local-Chromium install (and
                # the local-Chromium readiness gate) must not apply here —
                # with "agent_browser" this row read "needs setup" forever on
                # machines without a local Chromium build.
                "post_setup": "browserbase",
```

Node 也走"托管优先"(`find_node_executable` 而非 `which`),并且用绝对路径以便 Windows 执行 `.cmd` shim。`hermes_cli/tools_config.py:1641-1642 @ 863e313`

```python
        npm_bin = find_node_executable("npm")
        npx_bin = find_node_executable("npx")
```

`--workspaces=false` 是为了不把 `apps/desktop`(Electron + node-pty)拖下来。`hermes_cli/tools_config.py:1655 @ 863e313`

```python
                [npm_bin, "install", "--silent", "--workspaces=false"],
```

Docker 里跳过 Chromium 安装(镜像已烘焙,且运行期通常无写权限):`hermes_cli/tools_config.py:1700-1703 @ 863e313`

```python
        if _running_in_docker():
            _print_warning(
                "    Chromium is missing but you're running in Docker."
            )
```

装完要**手动失效**缓存,否则同进程内后续检查还是"没装":`hermes_cli/tools_config.py:1743-1744 @ 863e313`

```python
                import tools.browser_tool as _bt
                _bt._cached_chromium_installed = None
```

### 7.4 其余 hook 的共同形状

`faster_whisper` / `kittentts` / `piper` / `ddgs` / `langfuse` 都是同一模板:
`__import__` 探测 → `_pip_install` → 打印后续可调的配置键 / 手动命令。例如 `hermes_cli/tools_config.py:1790-1796 @ 863e313`

```python
        import subprocess
        try:
            __import__("faster_whisper")
            _print_success("    faster-whisper is already installed")
            return
        except ImportError:
            pass
```

`kittentts` 直接钉死一个 GitHub release wheel URL(版本 0.8.1),不是 PyPI:`hermes_cli/tools_config.py:1820-1823 @ 863e313`

```python
        wheel_url = (
            "https://github.com/KittenML/KittenTTS/releases/download/"
            "0.8.1/kittentts-0.8.1-py3-none-any.whl"
        )
```

`langfuse` 的 hook 除了装 SDK,还**顺手把插件写进 `plugins.enabled`**(bundled 插件默认不加载):`hermes_cli/tools_config.py:1927-1935 @ 863e313`

```python
        try:
            from hermes_cli.plugins_cmd import _get_enabled_set, _save_enabled_set
            enabled = _get_enabled_set()
            if "observability/langfuse" in enabled or "langfuse" in enabled:
                _print_success("    Plugin observability/langfuse already enabled")
            else:
                enabled.add("observability/langfuse")
                _save_enabled_set(enabled)
                _print_success("    Plugin observability/langfuse enabled")
```

`spotify` 的 hook 是**跑另一个 CLI 命令**,并且刻意吞掉 `SystemExit`,让"OAuth 没走完"不至于让 toolset 启用失败。`hermes_cli/tools_config.py:1903-1907 @ 863e313`

```python
        except SystemExit as exc:
            # User aborted the wizard, or OAuth failed — don't fail the
            # toolset enable; they can retry with `hermes auth spotify`.
            _print_warning(f"    Spotify login did not complete: {exc}")
            _print_info("    Run later: hermes auth spotify")
```

`xai_grok` 是**凭据引导**而非安装:先查 OAuth,再查 `XAI_API_KEY`,都没有才弹三选一。`hermes_cli/tools_config.py:1949-1954 @ 863e313`

```python
        try:
            from hermes_cli.auth import get_xai_oauth_auth_status
            oauth_logged_in = bool(get_xai_oauth_auth_status().get("logged_in"))
        except Exception:
            oauth_logged_in = False
        existing_api_key = get_env_value("XAI_API_KEY")
```

它是本段内唯一写入 env 的 hook:`hermes_cli/tools_config.py:2000 @ 863e313`

```python
                save_env_value("XAI_API_KEY", api_key)
```

**为什么 `xai_grok` 在 readiness 表里缺席**(本段外的对照):它是 auth 不是 install。▲ `hermes_cli/tools_config.py:3262-3263 @ 863e313`

```python
# performs before installing. ``xai_grok`` is intentionally absent — it is a
# credential bootstrap, not an install, and is handled as an auth check.
```

---

## 8. 机制:cua-driver 安装器(本段最复杂的一块工程)

**解决什么问题**:Computer Use 需要一个上游(trycua/cua)的 Rust 二进制。它没有 PyPI 包,只有 `install.sh` / `install.ps1`,
上游还有并发锁、prerelease tag、Release-Please 抢跑等一堆坑。

### 8.1 三种调用模式

`hermes_cli/tools_config.py:918-925 @ 863e313`

```python
    * ``upgrade=False`` — original post-setup behaviour: skip if already
      installed, install otherwise. Used by the toolset enable flow where
      we don't want to surprise the user with a network fetch.
    * ``upgrade=True`` — always re-run the installer (or call ``cua-driver
      update`` if the binary supports it). Used by ``hermes update`` and
      by ``hermes computer-use install --upgrade``.
```

`require_confirmed_update` 的取舍写得很直白:`hermes update` 对每个用户都跑,一次不确定的检查不该换来几分钟静默重装。`hermes_cli/tools_config.py:927-934 @ 863e313`

```python
    can't positively confirm that a newer release exists — the driver is
    too old for the verb, the GitHub check failed, we're offline, or the
    probe timed out — keep the installed version and return instead of
    falling through to the full upstream installer. ``hermes update`` sets
    this so a broken update check costs seconds, not a multi-minute silent
    reinstall on every update (the upstream installer runs up to
    ``_CUA_INSTALLER_TIMEOUT`` and install.ps1's concurrency lock can add
    a further ~600s wait on Windows). ``hermes computer-use install
```

### 8.2 删掉的资产探针 —— 一份很好的"别重复上游逻辑"教材

`hermes_cli/tools_config.py:868-876 @ 863e313`

```python
# The asset-probe that lived here used to hit `/releases/latest` on
# trycua/cua and inspect the release's asset list before piping the
# installer to bash. It was broken in two places:
#
#   1. cua-driver-rs releases are marked **prerelease** on every cut,
#      and GitHub's `/releases/latest` endpoint explicitly skips
#      prereleases. On the live trycua/cua repo today, `/releases/latest`
#      returns the Python `cua-agent v0.8.3` package (zero binary
#      assets) instead of `cua-driver-rs-v0.6.0` (19 binary assets).
```

结论:信任上游安装器;升级路径改问二进制自己(`cua-driver check-update --json`)。`hermes_cli/tools_config.py:887-893 @ 863e313`

```python
# Resolution: trust the upstream installer. For fresh installs, run
# install.sh directly — it errors clean if the target arch has no
# asset. For the upgrade path, `cua_driver_update_check()` (which calls
# `cua-driver check-update --json`) gives us the canonical update
# answer from the binary itself — same tag-resolution as the installer,
# no Python-side duplication.
```

### 8.3 版本 pin:一个真实的发布竞态

Release Please 会在**资产发布之前**就把 `main` 上的 baked 版本号 bump 上去;这个窗口里不 pin 就 404。
所以拿 `check-update` 报的 `latest_version`(来自 Releases API,资产已发布)去 pin,并且只接受纯数字点号格式。`hermes_cli/tools_config.py:1069-1073 @ 863e313`

```python
            import re as _re

            _latest = str(_state.get("latest_version") or "").strip().lstrip("vV")
            if _re.fullmatch(r"\d+(\.\d+)*", _latest):
                confirmed_version = _latest
```

pin 通过环境变量传给两个上游脚本:`hermes_cli/tools_config.py:1459-1462 @ 863e313`

```python
    if pin_version:
        # Both upstream installers (install.sh and install.ps1) honour
        # CUA_DRIVER_RS_VERSION over their baked default.
        installer_env["CUA_DRIVER_RS_VERSION"] = pin_version
```

### 8.4 超时值不是拍脑袋的

660 = 上游锁的 600s 陈旧窗口 + 60s 余量。短于它 → 每次都在上游自愈之前被杀,永久"总是超时"。`hermes_cli/tools_config.py:1110-1118 @ 863e313`

```python
# Ceiling for one upstream-installer run. Must exceed the installer's own
# stale-lock recovery window: _install-rust.sh serializes concurrent installs
# with a lock dir at ~/.cua-driver/packages/.install.lock.d and only
# force-releases a dead holder's lock after LOCK_STALE_AFTER_SECONDS=600 of
# waiting. With a shorter Python-side timeout, a stale lock means every run
# gets killed before the installer's recovery can fire — a permanent
# "always times out" wedge (issue #58762). 660s = 600s lock window + 60s
# headroom for the actual download/swap.
_CUA_INSTALLER_TIMEOUT = 660
```

### 8.5 陈旧锁的清理:两套平台原语

POSIX:读锁目录里的 `pid=`,`os.kill(pid, 0)` 探活;活着就不动,`PermissionError` 也当活着。`hermes_cli/tools_config.py:1251-1260 @ 863e313`

```python
        if holder_pid is not None:
            try:
                os.kill(holder_pid, 0)  # windows-footgun: ok — function early-returns on win32
                # Holder alive → a concurrent install is running; don't touch.
                return
            except ProcessLookupError:
                pass  # dead holder → stale, clear below
            except PermissionError:
                # Alive but owned by someone else — treat as live.
                return
```

读不到 pid 时,退化到"年龄 ≥ 上游自己的陈旧阈值才清"。`hermes_cli/tools_config.py:1261-1270 @ 863e313`

```python
        else:
            # No readable pid. Only clear if the lock is old enough that the
            # upstream installer itself would consider it reclaimable.
            import time as _time
            try:
                age = _time.time() - lock_dir.stat().st_mtime
            except OSError:
                return
            if age < _CUA_LOCK_STALE_AFTER:
                return
```

Windows:`install.ps1` 用 `FileShare::None` 持锁,所以用同样的原语(零共享 `CreateFileW`)去探;
并且加 `FILE_FLAG_DELETE_ON_CLOSE` 让"探测成功即原子删除",消掉探测与删除之间的窗口。`hermes_cli/tools_config.py:1147-1151 @ 863e313`

```python
    ``install.ps1`` serializes installs with a ``FileStream`` opened using
    ``FileShare::None``. Mirror that primitive with a zero-share
    ``CreateFileW`` probe. ``FILE_FLAG_DELETE_ON_CLOSE`` removes an unlocked
    leftover atomically when the probe handle closes, avoiding a gap where a
    new installer could acquire the file between our probe and deletion.
```

### 8.6 下载后执行,而不是 `bash -c "$(curl …)"`

理由三条:无 `shell=True`、无命令替换、mkstemp 文件名不可预测且 0600(避开多用户机上的符号链接 TOCTOU)。`hermes_cli/tools_config.py:1411-1416 @ 863e313`

```python
        # Download-then-exec instead of `bash -c "$(curl …)"`: no shell=True,
        # no command substitution, and the script lands in a mkstemp file
        # (unpredictable name, 0600) rather than a fixed /tmp path — avoiding
        # both the shell-injection surface and a symlink/TOCTOU race on
        # multi-user machines. The manual hint stays the upstream one-liner
        # since that's what the docs/README teach.
```

### 8.7 超时要杀整棵树

POSIX 用独立进程组 + `killpg`,否则孙子进程活着继续占锁,后续每次运行都卡死。`hermes_cli/tools_config.py:1469-1475 @ 863e313`

```python
    # POSIX: run the installer in its own process group so a timeout kill
    # takes out the whole `curl | bash` pipeline (and the exec'd
    # _install-rust.sh), not just the outer shell. Otherwise the surviving
    # grandchildren keep holding the install lock, wedging every later run.
    popen_kwargs = {}
    if not is_windows:
        popen_kwargs["start_new_session"] = True
```

Windows 没有进程组,改用 `psutil` 枚举后代、叶到根 kill。`hermes_cli/tools_config.py:1483-1486 @ 863e313`

```python
                # PowerShell may leave download/install helpers alive after its
                # direct process is killed. Those descendants inherit stdout
                # and can keep both communicate() and install.lock wedged, so
                # collect the tree first and kill it leaf-up.
```

### 8.8 静默模式下把安装器输出写进 update.log

`hermes update` 的 stdout 是一个镜像流对象,直接取它的 `_log` 句柄写全文,终端不回显。`hermes_cli/tools_config.py:1566-1572 @ 863e313`

```python
            # Preserve the full installer output. During `hermes update`,
            # sys.stdout is the mirroring _UpdateOutputStream whose `_log`
            # handle is ~/.hermes/logs/update.log — write straight to it so
            # the captured "Next steps" wall is kept in full (success AND
            # failure), without echoing it to the terminal.
            if result.stdout:
                _update_log = getattr(sys.stdout, "_log", None)
```

### 8.9 Windows autostart 的引号 bug 修复

老版 `install.ps1` 用命令字符串拼接 `& C:\Users\Name With Spaces\...`,PowerShell 在第一个空格处截断。
修法是改用 `Start-Process -FilePath/-ArgumentList` 结构化参数。`hermes_cli/tools_config.py:1306-1312 @ 863e313`

```python
    Older install.ps1 builds invoked
    ``& C:\\Users\\Name With Spaces\\...\\cua-driver`` from an elevated
    PowerShell command string, which PowerShell split at the first space. If
    the installer left the scheduled task missing, retry by
    launching the resolved binary through Start-Process's structured
    ``-FilePath`` / ``-ArgumentList`` parameters instead of interpolating a
    path into a command string.
```

同时它自己做了一次 PowerShell 单引号转义:`hermes_cli/tools_config.py:1280-1282 @ 863e313`

```python
def _ps_single_quote(value: str) -> str:
    """Return a PowerShell single-quoted string literal."""
    return "'" + value.replace("'", "''") + "'"
```

---

## 9. 配置键与环境变量(本段穷举)

### 9.1 config.yaml 键(本段直接读/写,或本段注释声明)

| 键 | 默认 | 读取点 @863e313 | 备注 |
|---|---|---|---|
| `platform_toolsets.<platform>` | 无 → 退化到平台 composite | `hermes_cli/tools_config.py:2232`(读)、`:2566`(写) | 本模块的主产物;既装 toolset key 也装 MCP server 名 |
| `known_plugin_toolsets.<platform>` | `{}` | `:2421`(读)、`:2575`(写) | 区分"新插件默认开"与"用户关掉了" |
| `known_builtin_toolsets.<platform>` | 无 | `:2200`(读)、`:2584`(写) | 区分"取消勾选"与"发布晚于存盘" |
| `agent.disabled_toolsets` | `[]` | `:2488` | 全局黑名单,**最后一道减法**;`_save_platform_tools` 会反向剔除 |
| `mcp_servers.<name>.enabled` | 缺省/无法识别 = True | `:2137` | 由 `_parse_enabled_flag` 解析 true/1/yes/on vs false/0/no/off |
| `context.engine` | `"compressor"` | `:2444` | 非默认引擎时自动加 `context_engine` toolset |
| `stt.enabled` | `True` | `tools/transcription_tools.py:161` | `_CONFIG_ONLY_TOOLSETS` 的开关所在(本段注释 `:162` 声明) |
| `stt.local.model` | 见下 | 本段仅在提示文案里出现 `:1803` | 真实读点在 `tools/transcription_tools.py`(`_normalize_local_model` 的告警文案 `:286` 引用同一路径) |
| `stt.provider` | `"local"` | 本段外 `:3613` | picker 写回 |
| `tts.piper.voice` | `DEFAULT_PIPER_VOICE` | `tools/tts_tool.py:2627` | 本段提示文案 `:1859` 指向它,**已核对属实** |
| `tts.provider` | 无 | 本段外 `:3389`(存在性判定) | picker 写回 |
| `web.backend` | 无 | 本段外 `:3392` | |
| `browser.cloud_provider` | 无 | 本段外 `:3395` | |
| `video_gen.provider` / `video_gen.use_gateway` | 无 | 本段注释 `:562-565` 声明,写入在本段外 | 选 Nous 托管行时置 `fal` + `True` |
| `computer_use.cua_telemetry` | `False`(= 关遥测) | `tools/computer_use/cua_backend.py:240` | 本段经 `_cua_driver_env()` `:776-778` 间接使用 |
| `plugins.enabled` | — | `hermes_cli/plugins_cmd._get_enabled_set` | `langfuse` hook 会往里加 `observability/langfuse`(`:1933`) |

`mcp_servers` 的"缺省即启用"语义:`hermes_cli/tools_config.py:2127-2129 @ 863e313`

```python
    the cron per-job toolset resolver (``cron.scheduler``) so every path agrees
    on MCP membership. A server is enabled unless its config sets an explicitly
    falsey ``enabled`` (per ``_parse_enabled_flag``: false/0/no/off) — a missing
```

### 9.2 环境变量(本段出现的**全部**)

**A. 本段代码直接 `os.environ` / `get_env_value` 读的:**

| 变量 | 默认 | 读取点 | 语义 / fallback |
|---|---|---|---|
| `HERMES_CUA_DRIVER_CMD` | `"cua-driver"` | `hermes_cli/tools_config.py:757` | cua-driver 可执行名覆盖;上游 `cua_backend` 里它是**权威**(设了就不再退回 PATH 搜索) |
| `CUA_DRIVER_RS_HOME` | `~/.cua-driver` | `:1129` | 上游安装器的 package home,用于定位锁 |
| `CUA_DRIVER_RS_VERSION` | 不设 | `:1462`(**写**给子进程) | pin 安装版本 |
| `VIRTUAL_ENV` | `Path(sys.executable).parent.parent` | `:806`(**写**给 uv) | 让 uv 知道装到哪个 venv |
| `XAI_API_KEY` | 无 | `:1954`(读)、`:2000`(写)、`:189`/`:196`/`:197`(三条 fallback) | xAI 直连计费 |
| `HASS_TOKEN` | 无 | `:205`(经 `agent.secret_scope.get_secret`) | 有它就自动开 homeassistant toolset |
| `PLAYWRIGHT_BROWSERS_PATH` | — | 仅注释 `:1684` | 说明 Docker 内跳过 Chromium 安装的理由 |

`_cua_driver_cmd` 的完整实现(注意 `.strip()` + `or`,空串等同未设):`hermes_cli/tools_config.py:755-757 @ 863e313`

```python
def _cua_driver_cmd() -> str:
    """Return the configured cua-driver override, or the bare default name."""
    return os.environ.get("HERMES_CUA_DRIVER_CMD", "").strip() or "cua-driver"
```

`_cua_install_home` 的 fallback 链:`hermes_cli/tools_config.py:1126-1131 @ 863e313`

```python
def _cua_install_home() -> "Path":
    """Package home shared by the upstream POSIX and Windows installers."""
    return Path(
        os.environ.get("CUA_DRIVER_RS_HOME")
        or str(Path.home() / ".cua-driver")
    )
```

**B. 本段以 `TOOL_CATEGORIES` 数据形式声明、由通用 prompt/写入路径处理的(全部 15 个):**

| 变量 | 声明处 | 归属 provider | 有默认值? |
|---|---|---|---|
| `VOICE_TOOLS_OPENAI_KEY` | `:348`(tts)、`:441`(stt) | OpenAI TTS / OpenAI STT | 否 |
| `OPENAI_API_KEY` | `:341`、`:434`(仅出现在 `override_env_vars`) | Nous 托管行要清掉它 | 否 |
| `ELEVENLABS_API_KEY` | `:364`(tts)、`:466`(stt) | ElevenLabs | 否 |
| `MISTRAL_API_KEY` | `:374` | Mistral Voxtral TTS | 否 |
| `GEMINI_API_KEY` | `:383` | Google Gemini TTS | 否 |
| `DEEPINFRA_API_KEY` | `:408`(tts)、`:478`(stt) | DeepInfra | 否 |
| `GROQ_API_KEY` | `:450` | Groq STT | 否 |
| `FIRECRAWL_API_KEY` | `:507`(仅 `override_env_vars`) | web / Nous 托管 | 否 |
| `FIRECRAWL_API_URL` | `:507`、`:515` | Firecrawl 自托管 | 否 |
| `FAL_KEY` | `:541`(image_gen)、`:561`(video_gen),均仅 `override_env_vars` | Nous 托管 FAL | 否 |
| `XAI_API_KEY` | `:597` | x_search 直连 | 否 |
| `BROWSER_USE_API_KEY` | `:639`(仅 `override_env_vars`) | Nous 托管浏览器 | 否 |
| `CAMOFOX_URL` | `:652` | Camofox | **是**:`http://localhost:9377` |
| `HASS_TOKEN` | `:668` | Home Assistant | 否 |
| `HASS_URL` | `:669` | Home Assistant | **是**:`http://homeassistant.local:8123` |
| `HERMES_LANGFUSE_PUBLIC_KEY` | `:718`、`:727` | Langfuse 云/自托管 | 否 |
| `HERMES_LANGFUSE_SECRET_KEY` | `:719`、`:728` | Langfuse 云/自托管 | 否 |
| `HERMES_LANGFUSE_BASE_URL` | `:729` | Langfuse 自托管 | **是**:`http://localhost:3000` |
| `OPENROUTER_API_KEY` | `:748`(`TOOLSET_ENV_REQUIREMENTS`) | vision —— **从不被读**,见 §6.4 | 否 |

Home Assistant 两个键(唯一同时给 token 和 URL 的 provider):`hermes_cli/tools_config.py:667-670 @ 863e313`

```python
                "env_vars": [
                    {"key": "HASS_TOKEN", "prompt": "Home Assistant Long-Lived Access Token"},
                    {"key": "HASS_URL", "prompt": "Home Assistant URL", "default": "http://homeassistant.local:8123"},
                ],
```

**C. 本段注释显式声明"没有这个变量"的**:cua-driver 没有版本 pin 用的 env var(用户侧)。`hermes_cli/tools_config.py:701-704 @ 863e313`

```python
                    # cua-driver reads HOME/TMPDIR from the process env, no
                    # extra keys required. Set HERMES_CUA_DRIVER_CMD to use a
                    # specific binary (e.g. a local build); there is no
                    # version-pin env var.
```

**D. 紧邻本段之外、但同属"配置面"的平台探测变量**(为完整性列出):
`TELEGRAM_BOT_TOKEN` / `DISCORD_BOT_TOKEN` / `SLACK_BOT_TOKEN` / `WHATSAPP_ENABLED` / `QQ_APP_ID`。▲ `hermes_cli/tools_config.py:2076-2087 @ 863e313`

```python
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
```

**所有 `get_env_value` 的统一 fallback 链**(本段所有 key 读取都经它):`os.environ`(经 profile scope 检查)→ `~/.hermes/.env`。`hermes_cli/config.py:4109 @ 863e313`

```python
def get_env_value(key: str) -> Optional[str]:
```

---

## 10. 文档 / 注释与代码的出入

**(D1) `_DEFAULT_OFF_TOOLSETS` 注释声称这些 toolset "仍在 `_HERMES_CORE_TOOLS` 里" —— 8 个里 7 个不成立。**
`hermes_cli/tools_config.py:142-144 @ 863e313`

```python
# Toolsets that are OFF by default for new installs.
# They're still in _HERMES_CORE_TOOLS (available at runtime if enabled),
# but the setup checklist won't pre-select them for first-time users.
```

对 `toolsets.py` 的 `_HERMES_CORE_TOOLS`(62 个名字)做成员检查:`video_analyze`、`video_generate`、`x_search`、
Spotify 工具、`discord`、`discord_admin` 全部**不在**里面;只有 `ha_*`(homeassistant)在。
`a2a` 甚至**不是一个 toolset**(`toolsets.py` 里 `grep a2a` 零匹配)。
**后果**:读注释的人会以为"把 video_gen 打开就能用",实际还必须让工具进入平台 composite,或走插件 toolset 路径。

**(D2) `cron/scheduler.py` 的 docstring 把 `_DEFAULT_OFF_TOOLSETS` 写成 `{moa, homeassistant, rl}`。** `cron/scheduler.py:235 @ 863e313`

```python
    _DEFAULT_OFF_TOOLSETS ({moa, homeassistant, rl}) are removed by
```

实际集合见 `hermes_cli/tools_config.py:156`,`moa` 和 `rl` 都已不在其中。
**后果**:测试 `tests/hermes_cli/test_tools_config.py` 里还在断言 `"moa" not in cron_enabled` —— 该断言现在恒真,
不是因为 `_DEFAULT_OFF_TOOLSETS` 减掉了它,而是因为 `moa` 压根不在 composite 里。守护变成了空守护。

**(D3) `toolsets.py` 的 `hermes-cron` 注释同样过期(写成 `moa, homeassistant`)。** `toolsets.py:472-473 @ 863e313`

```python
        # them down per the platform config. _DEFAULT_OFF_TOOLSETS (moa,
        # homeassistant) are excluded by _get_platform_tools() unless
```

**(D4) `platforms.py` 说 tools_config 应该用 `get_all_platforms()`,但 tools_config 直接 import 了静态 `PLATFORMS`。**
`hermes_cli/platforms.py:67-70 @ 863e313`

```python
def get_all_platforms() -> "OrderedDict[str, PlatformInfo]":
    """Return PLATFORMS merged with any plugin-registered platforms.

    Plugin platforms are appended after builtins.  This is the function
```

而本段是 `hermes_cli/tools_config.py:308 @ 863e313`

```python
from hermes_cli.platforms import PLATFORMS as _PLATFORMS_REGISTRY
```

**后果**:插件注册的平台不会出现在 `tools_config.PLATFORMS`,于是
(a) `_get_platform_tools` 走 `f"hermes-{platform}"` 猜名分支;
(b) `platform_default_keys`(`:2255`、`:2545`)不含插件平台的 composite 名,于是该名字会被当成"非配置项"保留进 `platform_toolsets`,
    进而在下次读取时可能与用户勾选并存 —— 而对内置平台,composite 名是被刻意剔除的(`:2542-2545` 注释说保留它会静默覆盖用户的取消勾选)。
(c) `tools_disable_enable_command` 直接拒绝插件平台(`:5399`)。

**(D5) `TOOL_CATEGORIES["computer_use"]["platform_gate"]` 是死字段。** `hermes_cli/tools_config.py:690-691 @ 863e313`

```python
        # Wayland via XWayland). Per-host gaps surface via `computer-use doctor`.
        "platform_gate": ["darwin", "win32", "linux"],
```

全仓 `grep platform_gate` 只有三处:本行、`gateway/authz_mixin.py` 里同名但语义无关的 `_platform_gate_env`、
以及 `tools/computer_use/permissions.py:34` 的一句注释("mirrors the toolset platform_gate")——**没有任何代码读取这个键**。
真实的平台限制发生在 `install_cua_driver` 内部的 `platform.system()` 判定(`:951`)。
**怎么会踩到**:有人以为在 category 上加 `platform_gate` 就能把某能力藏起来,结果它在所有平台的清单里照常出现。

---

## 11. 可疑缺陷(只记录,不修)

**(B1) 安装成功判定用 `shutil.which`,比安装检测用的解析器窄。**
安装前的检测用的是能搜索 `~/.local/bin`、`~/.cargo/bin`、`/opt/homebrew/bin` 的解析器:`hermes_cli/tools_config.py:966-967 @ 863e313`

```python
    driver_cmd = _cua_driver_cmd()
    binary = _resolved_cua_driver_cmd()
```

但安装**之后**的成功判定退回了裸 PATH 查找:`hermes_cli/tools_config.py:1585 @ 863e313`

```python
        if result.returncode == 0 and shutil.which(driver_cmd):
```

`driver_cmd` 是个裸名(`"cua-driver"`),`shutil.which` 只搜 PATH。上游安装器常装到 `~/.local/bin`:
`tools/computer_use/cua_backend.py:699-704 @ 863e313`

```python
    Desktop apps launched from Finder/Dock often inherit a narrow PATH that
    omits user-local install directories. The upstream cua-driver installer
    commonly places the binary under ``~/.local/bin`` on POSIX systems, so a
    Hermes Desktop/TUI session can otherwise filter out the `computer_use`
    tool even though `hermes computer-use doctor` succeeds from a login shell.
```

**怎么会踩到**:从 Finder/Dock 启动的 Desktop(PATH 窄)里点"运行设置",安装其实成功了,
但本函数打印 "cua-driver installing did not complete"、返回 False。同一个进程里 `_POST_SETUP_READY["cua_driver"]`
用的却是 `_resolved_cua_driver_cmd()`(`:3273`),会报 ready —— 两个界面互相打脸。

**(B2) npm 安装失败后仍继续装 Chromium。** `agent_browser` 分支里 `npm install` 失败只打印警告,不 return;
随后仍会走到 Chromium 安装,而 `local_ab` 判定会失败、退回 `npx -y agent-browser`(网络下载)。`hermes_cli/tools_config.py:1659-1665 @ 863e313`

```python
            if result.returncode == 0:
                _print_success("    Node.js dependencies installed")
            else:
                from hermes_constants import display_hermes_home
                _print_warning(f"    npm install failed - run manually: cd {display_hermes_home()}/hermes-agent && npm install --workspaces=false")
                if result.stderr:
                    _print_info(f"      {result.stderr.strip()[:200]}")
```

**怎么会踩到**:离线/私有 registry 环境下,一次失败的 npm install 之后还要再等一次(最多 600s 超时)的 `npx` 拉取。

**(B3) `VIRTUAL_ENV` 是从 `sys.executable` 猜的,系统 Python 下会指向系统前缀。** `hermes_cli/tools_config.py:805 @ 863e313`

```python
    venv_root = Path(sys.executable).parent.parent
```

**怎么会踩到**:用系统 `/usr/bin/python3` 跑 `hermes tools post-setup piper`,`VIRTUAL_ENV=/usr`,
`uv pip install` 会拿这个当目标环境(uv 对不含 `pyvenv.cfg` 的目录通常会报错,但错误信息会指向一个用户没设过的 `VIRTUAL_ENV`,极难自诊)。

**(B4) 三个"静默吞异常"点会把插件 toolset 变成幽灵。**
`hermes_cli/tools_config.py:266-267 @ 863e313`

```python
    except Exception:
        pass
```

`hermes_cli/tools_config.py:277-278 @ 863e313`

```python
    except Exception:
        return set()
```

**怎么会踩到**:某个插件 import 期抛异常 → `_get_plugin_toolset_keys()` 返回空集 →
`_get_platform_tools` 里 `plugin_ts_keys` 为空 → 该插件的 toolset key 若已存在 `platform_toolsets` 中,
会落进 `explicit_passthrough`(`:2455-2461`),再被当成"非 MCP 的显式项"原样保留;
而 `_save_platform_tools` 也不会再写 `known_plugin_toolsets`(`:2570`),于是"用户关掉了"这个事实被抹掉。
整个过程无日志。

**(B5) `stt` 同时在 `CONFIGURABLE_TOOLSETS` 和 `configurable_keys` 里,是一个"零工具的显式配置触发器"。**
`_get_platform_tools` 的 `configurable_keys` 直接来自 `CONFIGURABLE_TOOLSETS`(不减 `_CONFIG_ONLY_TOOLSETS`):`hermes_cli/tools_config.py:2253 @ 863e313`

```python
    configurable_keys = {ts_key for ts_key, _, _ in CONFIGURABLE_TOOLSETS}
```

**怎么会踩到**:手工把 `platform_toolsets: {cli: [stt]}` 写进 config(或任何非清单来源的写入),
`has_explicit_config` 立刻为真,平台从 composite 推断切到"直接成员"模式,而 `stt` 在 `toolsets.py` 里根本不存在 →
`resolve_toolset("stt")` 为空 → 该平台只剩 recovery 补回来的东西。清单本身不会产生这种配置(`_checklist_toolset_keys` 排除了 stt),
所以这是一个"只有 API/手改才踩得到"的坑。

**(B6) `_toolset_configuration_platform` 用 `sorted(allowed)[0]` 定夺目标平台。**
`hermes_cli/tools_config.py:242 @ 863e313`

```python
    return sorted(allowed)[0]
```

**怎么会踩到**:目前每个受限 toolset 只允许一个平台,恒定无歧义;一旦某个 toolset 允许两个平台(如 `{discord, slack}`),
GUI 开关就会静默只写字典序第一个平台,另一个平台的用户点开关"成功但无效"。

**(B7) `_warned_invalid_platform_toolsets` 是进程级全局集合,没有清理入口(测试自己 `discard`)。**
`hermes_cli/tools_config.py:73-76 @ 863e313`

```python
# Platforms already warned about an all-invalid platform_toolsets list, so the
# runtime check in _get_platform_tools warns once per platform instead of on
# every tool resolution for a persistently-corrupt config (#38798).
_warned_invalid_platform_toolsets: Set[str] = set()
```

**怎么会踩到**:长驻 gateway 进程里,用户修好 config 又改坏,第二次不会再告警;测试必须手动 `discard`(见 `tests/hermes_cli/test_tools_config.py:41-42`)。

**(B8) `install_cua_driver` 里 `import shutil` 遮蔽模块级 `shutil`(无害但易误读)。** `hermes_cli/tools_config.py:946-948 @ 863e313`

```python
    import platform as _plat
    import shutil
    import subprocess
```

模块顶部已 `import shutil`(`:15`);函数内重复 import 只是把同一模块绑到局部名。不是 bug,但让"哪个 shutil"这类审查变噪。

---

## 12. 配套测试(行为规格)

直接针对本段的:

- `tests/hermes_cli/test_tools_config.py` —— 主规格。导入面覆盖了本段几乎所有导出符号(`:11-31`),
  含 `#38798` 全无效名告警、`#35527` discord 平台原生豁免、HASS_TOKEN 自动开、`_checklist_toolset_keys` 作用域、
  `CONFIGURABLE_TOOLSETS` 与插件去重(`:434`)、`_visible_providers` 的 pool-only 隐藏(`:571`/`:607`)。
- `tests/hermes_cli/test_install_cua_driver.py` —— §8 的全部规格:
  不支持平台静默/告警、`/Applications` 不可写跳过、`require_confirmed_update` 的四种走法、
  超时上限必须 > 上游锁窗口(`:620`)、POSIX 新会话(`:626`)、Windows 后代树 kill(`:651`)、
  下载后执行 argv 列表(`:754`)、临时脚本清理(`:774`)、版本 pin 与 `v` 前缀归一化(`:847`/`:854`)、
  以及"资产探针必须已被删除"(`:379`)。
- `tests/hermes_cli/test_post_setup_gating.py` —— `_POST_SETUP_INSTALLED` 谓词:缺 cua-driver 必须强制走设置流;
  谓词抛异常不得阻塞。
- `tests/hermes_cli/test_stt_picker.py` —— `_CONFIG_ONLY_TOOLSETS` 的行为规格:`stt` 必须在 `CONFIGURABLE_TOOLSETS` 里、
  必须不在 `_checklist_toolset_keys("cli")` 里、而 `tts` 必须在(`:112-117`)。
- `tests/hermes_cli/test_tts_picker.py` / `test_image_gen_picker.py` / `test_video_gen_picker.py` —— `TOOL_CATEGORIES` 各 category 的 provider 行规格。
- `tests/hermes_cli/test_tool_token_estimation.py` —— 用 `CONFIGURABLE_TOOLSETS` 的 key 列表估 token。
- `tests/hermes_cli/test_tools_disable_enable.py` / `test_mcp_tools_config.py` —— 非交互开关与 MCP 分支。
- `tests/cron/test_scheduler.py` —— `_get_platform_tools(cfg, "cron")` 的消费端规格。
- `tests/hermes_cli/test_setup_blank_slate.py` —— Blank Slate 预置 `agent.disabled_toolsets` 的场景(#49995 的来源)。
- `tests/hermes_cli/test_web_server_profile_unification.py` —— patch `valid_post_setup_keys` 验证 GUI 端点的 allowlist。

---

## 13. 重实现要点(从零重写这一层必须知道的)

1. **把"工具组定义"和"UI 清单"分成两张表,但一开始就写好对账机制。** 本仓库为漂移付了三个补丁
   (recovery 环节 `:2374`、`_RECENTLY_SHIPPED_TOOLSETS` `:2185`、`#38798` 运行时告警 `:2493`)。
   我会把 UI 清单**从**工具组定义生成(加一个 `ui: {label, desc, default_off}` 字段),而不是维护第二张手写表。

2. **"默认关"必须只有一个机制。** 本仓库有两个(composite 成员资格 + `_DEFAULT_OFF_TOOLSETS` 减法),
   结果注释(§10 D1)和测试(§10 D2)都失真了。选一个:要么组不进默认包,要么进包再减,不要都做。

3. **存盘即冻结是这套设计的核心决定,必须显式承认它的代价。** `has_explicit_config`(`:2262`)一旦为真,
   以后所有新增能力对该用户都默认关。要么像本仓库那样打 `_RECENTLY_SHIPPED_TOOLSETS` 补丁(且必须严格一版就清),
   要么改成"存正负两个 delta 列表"(存 `+spotify` / `-memory`)而不是存全量快照 —— 后者从根上没有这个问题。

4. **"最后一道全局减法"必须有反向和解。** `agent.disabled_toolsets` 在读路径最后减(`:2483`),
   导致写路径的开关静默失效;补救是在写时剔除(`:2601`)。设计时就该规定:**任何单调覆盖层都要成对提供"写时清除"**。

5. **凭据驱动的自动启用要和"用户已表态"互斥。** 本仓库把自动开只放在 else 分支(`:2337-2339`),
   并且对不在 composite 里的 toolset 要做"注入 + 免减"两步(`x_search` `:2340`/`:2367`)。
   这两步很容易只写一半 —— 写测试时要覆盖"有凭据 + 已存盘"这个组合。

6. **provider 矩阵要区分三类行**:真 provider(插件注入)、托管订阅行(`requires_nous_auth` + `managed_nous_feature` + `override_env_vars`)、
   纯 UX 行(本地/自托管)。第三类没有 key 但**不等于就绪**,必须有独立的 readiness 判定(`provider_readiness_status` `:3287`)
   和"已安装"谓词表(`_POST_SETUP_READY` `:3264`),否则 GUI 会对每个零 key 行都亮绿灯。

7. **顺序即默认**:picker 第 0 行是回车落点,免费/本地必须排第一(`:610-614`)。这是一条应该写进设计文档的硬规则。

8. **安装钩子要有一个非交互、可被 GUI spawn 的稳定入口 + allowlist**(`hermes tools post-setup <key>` `:2042`,
   allowlist `:2010`),并且**同一个"是否已安装"判据必须在安装成功判定、readiness 判定、强制配置判定三处共用一份实现** ——
   本仓库正是在这里出了 B1。
