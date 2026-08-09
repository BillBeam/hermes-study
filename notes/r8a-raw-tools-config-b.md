# r8a-raw-tools-config-b · tools_config.py:1900-3700

底稿。求全求证,不求好读。基线 `863e313`,文件全长 5452 行,本稿覆盖 **1900-3700**。
所有 `路径:行号` 均相对 `/home/user/hermes-agent`。

---

## 0. 上下文:这个模块在干什么

模块 docstring 说清了唯一的持久化落点。`hermes_cli/tools_config.py:8 @ 863e313`

```python
Saves per-platform tool configuration to ~/.hermes/config.yaml under
```

一句话:**`hermes tools` / `hermes setup tools` 的全部实现**。选平台 → 勾选 toolset →
对新开的、需要 API key 的 toolset 走 provider 感知的配置流程 → 写回 `config.yaml`。

本段(1900-3700)恰好覆盖这条链路的**中段**:

| 区段 | 内容 |
|---|---|
| 1900-2008 | `_run_post_setup` 的尾三个分支(spotify / langfuse / xai_grok) |
| 2010-2069 | post-setup 白名单 + 非交互 CLI 入口 |
| 2072-2185 | 平台枚举、bool 解析、MCP 全局启用集、默认关闭豁免、"新上线 toolset" 常量 |
| 2188-2518 | **`_get_platform_tools`** —— 全仓最重要的"这个平台到底开了哪些 toolset"解析器 |
| 2521-2666 | `_save_platform_tools` 写回 + `_toolset_has_keys` 三级判定 |
| 2671-2785 | 菜单 helper、token 估算、勾选清单 |
| 2790-3186 | 插件 provider 注入(image/video/web/browser/tts)+ `_visible_providers` |
| 3189-3364 | 安装态探针 + `provider_readiness_status`(GUI "Ready" 药丸的服务端真相) |
| 3367-3547 | 是否需要弹配置 + 分类配置 UI |
| 3550-3648 | "当前激活的是哪个 provider" |
| 3651-3700(及溢出到 3914) | image/video gen 模型选择器 |

`_get_platform_tools` 的消费者遍布全仓:CLI(`cli.py:18169`)、gateway
(`gateway/run.py:19521`、`gateway/session.py:412`)、api_server、cron
(`cron/scheduler.py:245`)、Web GUI(`hermes_cli/web_routers/tools.py:74`)。
**它是"工具可见性"的唯一权威**,所以它的每一条规则都是全局语义。

---

## 1. 机制:post-setup 钩子的白名单与非交互入口

### 1.1 解决什么问题

GUI(Capabilities 面板)点"Run setup"时,不能把安装逻辑在前端再实现一遍;它需要一个
**稳定、可脚本化、无交互**的后端目标。同时,这个目标接受一个字符串 key 并据此执行
`npm install` / `pip install` / 下载二进制 —— 如果不加校验,就是一个任意命令分发器。

### 1.2 怎么实现

白名单从数据里**推导**而不是手写:遍历 `TOOL_CATEGORIES` 里每个 provider 的 `post_setup`,
再加上四类插件 provider builder 声明的 `post_setup`。`hermes_cli/tools_config.py:2019 @ 863e313`

```python
    keys: Set[str] = set()
    for cat in TOOL_CATEGORIES.values():
        for prov in cat.get("providers", []):
            ps = prov.get("post_setup")
            if ps:
                keys.add(ps)
```

插件那一半用 try/except 逐 builder 兜底,插件炸了不影响白名单的其余部分。
`hermes_cli/tools_config.py:2026 @ 863e313`

```python
    for builder in (
        _plugin_web_search_providers,
        _plugin_image_gen_providers,
        _plugin_video_gen_providers,
        _plugin_browser_providers,
    ):
```

**注意 `_plugin_tts_providers` 不在这个元组里。** TTS 插件如果声明了 `post_setup`
(`_plugin_tts_providers` 明确会透传它,见 `hermes_cli/tools_config.py:3078`),
这个 key 就进不了白名单 —— 见 §14 缺陷 D1。

CLI 入口先查 key 再执行,未知 key 返回退出码 2 并列出全部合法 key。
`hermes_cli/tools_config.py:2055 @ 863e313`

```python
    valid = valid_post_setup_keys()
    if key not in valid:
        _print_error(
            f"Unknown post-setup key: {key!r}. "
            f"Valid keys: {', '.join(sorted(valid)) or '(none)'}"
        )
        return 2
```

### 1.3 为什么这么设计 / 取舍

- **取舍 1**:白名单由数据推导 → 加 provider 即自动获得合法 key,不会忘记同步;
  代价是白名单**依赖插件发现**,插件没装时同一个 key 会变成非法。GUI 与 CLI 在
  不同进程里跑,插件发现状态可能不一致。
- **取舍 2**:`run_post_setup_command` 把 `_run_post_setup` 的一切异常吞成退出码 1。
  `hermes_cli/tools_config.py:2063 @ 863e313`

```python
    try:
        _run_post_setup(key)
    except Exception as exc:  # pragma: no cover — defensive
        _print_error(f"Post-setup failed: {exc}")
        return 1
```

  好处:GUI 拿到确定的退出码。坏处:堆栈丢失,只剩 `str(exc)`。

### 1.4 本段内的三个 post-setup 分支

**spotify**(`hermes_cli/tools_config.py:1883 @ 863e313`)—— 直接复用完整的
`hermes auth spotify` 向导,用 `SimpleNamespace` 伪造 argparse 命名空间。

```python
    elif post_setup_key == "spotify":
```

它把 `SystemExit` 单独接住,理由写在注释里:用户中途放弃不应让 toolset 启用失败。
`hermes_cli/tools_config.py:1903 @ 863e313`

```python
        except SystemExit as exc:
```

**langfuse**(`hermes_cli/tools_config.py:1912 @ 863e313`)—— 装 SDK **并且**把
`observability/langfuse` 插件写进 `plugins.enabled`。

```python
    elif post_setup_key == "langfuse":
```

这是本段唯一一个 post-setup 钩子**跨模块写别的配置**的例子:
`hermes_cli/tools_config.py:1928 @ 863e313`

```python
            from hermes_cli.plugins_cmd import _get_enabled_set, _save_enabled_set
```

它同时接受 `observability/langfuse` 和裸 `langfuse` 两种已启用写法(见 1930 行),
说明插件启用集里存在两种命名风格,这里做了兼容读、单一风格写。

**xai_grok**(`hermes_cli/tools_config.py:1942 @ 863e313`)—— 唯一一个"凭据引导"型钩子,
不装任何东西。

```python
    elif post_setup_key == "xai_grok":
```

先探测 OAuth 登录态,再探测 `XAI_API_KEY`,任一命中就直接返回。
`hermes_cli/tools_config.py:1954 @ 863e313`

```python
        existing_api_key = get_env_value("XAI_API_KEY")
```

都没有才弹三选一菜单(OAuth 浏览器登录 / 粘贴 key / 跳过),粘贴分支落盘:
`hermes_cli/tools_config.py:2000 @ 863e313`

```python
                save_env_value("XAI_API_KEY", api_key)
```

设计意图很明确:xAI 的多个 picker 行(TTS、Video Gen、x_search)都声明
`env_vars: []`,把认证 UX 全部收敛到这一个钩子里,避免每个行各写一遍。
代价:`provider_readiness_status` 必须为 `xai_grok` 开一个特例分支(见 §9)。

---

## 2. 机制:平台枚举与逐平台汇总

`_get_enabled_platforms` 用"有没有 token"当作"平台是否配置了"的代理。
`hermes_cli/tools_config.py:2076 @ 863e313`

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

- `cli` 恒定存在(硬编码在列表初值)。
- 这是**硬编码 5 个平台**,而 `PLATFORMS` 来自 `hermes_cli/platforms` 注册表
  (`hermes_cli/tools_config.py:310`)。新增平台不会自动出现在这里 —— 一个明确的
  "两套平台真相"分裂点(见 §14 缺陷 D2)。
- `WHATSAPP_ENABLED` 被当**存在性**判断,不解析真假:`WHATSAPP_ENABLED=false` 也算启用。

`_platform_toolset_summary` 只是把上面的列表逐个喂给 `_get_platform_tools`,
并允许测试显式传入平台列表以摆脱环境变量依赖。`hermes_cli/tools_config.py:2090 @ 863e313`

```python
def _platform_toolset_summary(config: dict, platforms: Optional[List[str]] = None) -> Dict[str, Set[str]]:
```

---

## 3. 机制:bool 解析与 MCP 全局启用集

### 3.1 `_parse_enabled_flag`

解决的问题:YAML 里 `enabled:` 可能是 bool / int / 字符串 / 缺失。
`hermes_cli/tools_config.py:2106 @ 863e313`

```python
def _parse_enabled_flag(value, default: bool = True) -> bool:
```

字符串白名单是双向且封闭的:`hermes_cli/tools_config.py:2114 @ 863e313`

```python
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return default
```

**关键取舍**:无法识别的值(`"maybe"`、`"disabled"`、`"n"`)落到 `default`,
调用方传 `default=True` 时就是"识别不了就当开着"。这是刻意的 fail-open,
写错拼写不会静默丢工具 —— 但也意味着 `enabled: "off "` 能关掉(strip 了),
`enabled: "nope"` 关不掉。

### 3.2 `enabled_mcp_server_names`

`hermes_cli/tools_config.py:2132 @ 863e313`

```python
    mcp_servers = (config or {}).get("mcp_servers") or {}
    return {
        str(name)
        for name, server_cfg in mcp_servers.items()
        if isinstance(server_cfg, dict)
        and _parse_enabled_flag(server_cfg.get("enabled", True), default=True)
    }
```

- 值不是 dict 的条目被**静默丢弃**(`mcp_servers: {foo: null}` → foo 不算启用)。
- `str(name)` 是为了 YAML 把 `12306:` 解析成 int 的情况(测试
  `test_numeric_mcp_server_name_does_not_crash_sorted` 就盯这个)。
- 这个函数被 cron 调度器直接复用(`cron/scheduler.py:212`),docstring 明确说
  "让 gateway/CLI 解析器与 cron 每作业解析器对 MCP 成员资格达成一致"。
  **这是一个刻意抽出来的共享真相点**,不是顺手的 helper。

---

## 4. 机制:平台原生 default-off toolset 的显式配置豁免

### 4.1 问题场景

`discord` / `discord_admin` 两个 toolset 同时满足两个条件:在
`_DEFAULT_OFF_TOOLSETS` 里(`hermes_cli/tools_config.py:156 @ 863e313`)

```python
_DEFAULT_OFF_TOOLSETS = {"homeassistant", "spotify", "discord", "discord_admin", "video", "video_gen", "x_search", "a2a"}
```

又被 `_TOOLSET_PLATFORM_RESTRICTIONS` 限定只能在 discord 平台出现
(`hermes_cli/tools_config.py:216 @ 863e313`)

```python
_TOOLSET_PLATFORM_RESTRICTIONS: Dict[str, Set[str]] = {
```

于是:用户在 discord 平台显式保存了 `hermes-discord` 这个复合 toolset(它**包含**
discord 工具),读回来时 default-off 又把它剥掉了 —— 用户的显式选择被静默推翻(#35527)。

### 4.2 实现

`hermes_cli/tools_config.py:2155 @ 863e313`

```python
    if not explicitly_configured:
        return
    for ts in list(default_off):
        allowed = _TOOLSET_PLATFORM_RESTRICTIONS.get(ts)
        if allowed is not None and platform in allowed:
            default_off.discard(ts)
```

原地修改传入的 `default_off` 集合。语义:**"平台自己的原生工具,在该平台被显式配置过
之后不再算 default-off"**。未配置平台(新装)仍然保持关闭 —— 安全 opt-in 不变。

取舍:`explicitly_configured` 的定义只是"`platform_toolsets.<platform>` 是个 list"
(`hermes_cli/tools_config.py:2238`),不区分是用户勾的还是迁移脚本写的。

---

## 5. 机制:"上一版之后才上线的 toolset" 回填

### 5.1 问题场景(值得完整复述)

保存一次 `hermes tools`(或桌面 UI 里拨一个开关)会把该平台的复合 toolset
`[hermes-cli]` **替换成一份冻结的显式清单**,而且**没有任何路径会往这份清单里加东西**。
后果:此后新发布的 toolset,对"点过 picker 的人"永远是关的;对"还停在 `[hermes-cli]`
的人"升级即自动获得。两拨用户行为分叉。

### 5.2 实现

一个"当期发布窗口"常量:`hermes_cli/tools_config.py:2185 @ 863e313`

```python
_RECENTLY_SHIPPED_TOOLSETS = frozenset({"bfl"})
```

它的注释是本文件里最长的一段规程,核心约束是:**必须与它点名的 toolset 同一版发布,
并在下一版清空**。理由:一旦某个已发布版本把该 toolset 放上过 checklist,用户取消勾选
写出的配置与"该 toolset 存在之前保存的配置"**逐字节相同**,这条规则就会把用户的
opt-out 又打开。晚到一版或多留一版,回填就变成"卡死的复选框"。

回填函数先读"这个平台的 checklist 曾经展示过哪些内置 toolset"这份台账:
`hermes_cli/tools_config.py:2200 @ 863e313`

```python
    offered = (config.get("known_builtin_toolsets") or {}).get(platform)
```

出现在 `offered` 里就说明用户见过并主动取消 → 视为 declined,不回填。

然后逐个候选判断:`hermes_cli/tools_config.py:2207 @ 863e313`

```python
    for ts_key in sorted(_RECENTLY_SHIPPED_TOOLSETS):
        if ts_key in enabled_toolsets or ts_key in declined:
            continue
        if not _toolset_allowed_for_platform(ts_key, platform):
            continue
```

最后一道闸:**只在"留在复合 toolset 上本来也会得到它"的平台回填**,
即该 toolset 的静态成员必须是平台默认复合的子集。
`hermes_cli/tools_config.py:2215 @ 863e313`

```python
        ts_tools = set(resolve_toolset(ts_key, include_registry=False))
        if composite_tools is None:
            composite_tools = set(resolve_toolset(default_ts))
        if not ts_tools or not ts_tools.issubset(composite_tools):
            continue
        enabled_toolsets.add(ts_key)
```

`composite_tools` 惰性计算 —— 只有真有候选要判断时才解析平台复合。

### 5.3 取舍

- **对齐(parity)是唯一正当性**,所以刻意窄的复合(`hermes-acp`、`hermes-webhook`)
  保持窄。测试 `test_platforms_whose_composite_excludes_it_are_left_narrow` 就是钉这条。
- 用户仍有两条独立的"不要"通道:取消勾选(写进 `known_builtin_toolsets`)、
  `agent.disabled_toolsets`(在所有规则之后减掉)。
- 注释明确写了**为什么不在这里查 Nous 登录态**:六个 `bfl_flux3_*` 工具带
  `check_fn=check_bfl_requirements`,没凭据时 schema 数为 0;在这条路径上探测门户
  会让每次 CLI 启动 / gateway 会话 / cron tick 都带一次网络调用。
  —— 这是"分层门控"的范例:**toolset 开关(便宜、本地)与工具注册门控(贵、运行时)分离**。

---

## 6. 机制:`_get_platform_tools` —— 七段解析流水线(本段核心)

签名与唯一开关:`hermes_cli/tools_config.py:2223 @ 863e313`

```python
def _get_platform_tools(
    config: dict,
    platform: str,
    *,
    include_default_mcp_servers: bool = True,
) -> Set[str]:
```

`include_default_mcp_servers=False` 目前只有 discord 会话
(`gateway/session.py:439`)与测试在用。

### 6.0 读入与归一

`hermes_cli/tools_config.py:2232 @ 863e313`

```python
    platform_toolsets = config.get("platform_toolsets") or {}
    toolset_names = platform_toolsets.get(platform)
```

`explicitly_configured` = 是不是个 list(2238 行)。缺失/非 list 就回落到平台默认复合:
`hermes_cli/tools_config.py:2240 @ 863e313`

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

**插件平台的约定式命名**:`hermes-<platform>`。`resolve_toolset` 那边有对应的
自动生成逻辑(`toolsets.py:769` 附近判断 `name.startswith("hermes-")`)。

元素强制转字符串,防 YAML 把 `12306:` 解析成 int 后 `sorted()` 混类型崩溃:
`hermes_cli/tools_config.py:2251 @ 863e313`

```python
    toolset_names = [str(ts) for ts in toolset_names]
```

### 6.1 分叉:显式配置 vs 复合推断

`hermes_cli/tools_config.py:2262 @ 863e313`

```python
    has_explicit_config = any(ts in configurable_keys for ts in toolset_names)
```

注意 `has_explicit_config` ≠ `explicitly_configured`:前者是"清单里出现了任一
**可配置 toolset key**",后者只是"是个 list"。两个变量在同一函数里共存,语义相近
但含义不同 —— 阅读时最容易搞混的地方。

#### 6.1a 显式分支(2264-2309)

直接成员判定,不做子集推断 —— 注释说明这是为了避开"复合 toolset 含全部核心工具,
导致被禁用的 toolset 又被推断成启用"的 bug:
`hermes_cli/tools_config.py:2264 @ 863e313`

```python
    if has_explicit_config:
        enabled_toolsets = {
            ts for ts in toolset_names
            if ts in configurable_keys and _toolset_allowed_for_platform(ts, platform)
        }
```

**混合配置**(`[hermes-cli, spotify]`,即勾了 Spotify 之后的典型形态)要额外处理,
否则复合名被静默丢弃,会话就只剩 opt-in 的那一个 toolset,原生工具全没了:
`hermes_cli/tools_config.py:2284 @ 863e313`

```python
        if composite_tools:
            expanded = set()
            for ts_key, _, _ in CONFIGURABLE_TOOLSETS:
                if not _toolset_allowed_for_platform(ts_key, platform):
                    continue
```

子集推断用的是**静态成员**(`include_registry=False`),这是 #49622 的修复:
`hermes_cli/tools_config.py:2293 @ 863e313`

```python
                ts_tools = set(resolve_toolset(ts_key, include_registry=False))
                if ts_tools and ts_tools.issubset(composite_tools):
                    expanded.add(ts_key)
```

原因:`get_toolset()` 会把插件/overlay/桌面注册进来的工具并进 toolset,而平台复合
枚举的是静态工具名列表 —— 用合并后的集合做子集判断,只要有一个插件工具加入,
整个 toolset 就被判成"不在复合里"而整体掉线。

`default_off` **只作用于隐式展开的部分**,用户显式列出的(如 `spotify`)必须活下来:
`hermes_cli/tools_config.py:2297 @ 863e313`

```python
            default_off = set(_DEFAULT_OFF_TOOLSETS)
            if platform in default_off and platform not in _TOOLSET_PLATFORM_RESTRICTIONS:
                default_off.remove(platform)
            if "homeassistant" in default_off and _homeassistant_credentials_present():
                default_off.remove("homeassistant")
```

回填只在这个分支调用(复合分支本来就会拿到):
`hermes_cli/tools_config.py:2309 @ 863e313`

```python
        _enable_recently_shipped_toolsets(enabled_toolsets, config, platform)
```

#### 6.1b 复合推断分支(2310-2372)

先把所有复合名解析成工具名全集:`hermes_cli/tools_config.py:2313 @ 863e313`

```python
        all_tool_names = set()
        for ts_name in toolset_names:
            all_tool_names.update(resolve_toolset(ts_name))
```

再反查每个可配置 toolset 的静态成员是否是子集(同样 `include_registry=False`)。
`hermes_cli/tools_config.py:2326 @ 863e313`

```python
            ts_tools = set(resolve_toolset(ts_key, include_registry=False))
```

**`x_search` 特判**:它是单工具 toolset,不在任何平台复合里,所以子集循环永远选不中它。
`hermes_cli/tools_config.py:2340 @ 863e313`

```python
        x_search_auto_enabled = (
            _toolset_allowed_for_platform("x_search", platform)
            and _xai_credentials_present()
        )
```

三条 default-off 豁免依次落地,每条都对应一次真实回归:
`hermes_cli/tools_config.py:2353 @ 863e313`

```python
        if platform in default_off and platform not in _TOOLSET_PLATFORM_RESTRICTIONS:
```

(平台名与 toolset 名同名时的兼容,如 homeassistant 平台 + homeassistant toolset)

`hermes_cli/tools_config.py:2362 @ 863e313`

```python
        if "homeassistant" in default_off and _homeassistant_credentials_present():
```

(#14798 让 cron 遵守逐平台工具配置后,HA cron 作业回归 —— 有 `HASS_TOKEN` 即视为 opt-in)

最后统一减去:`hermes_cli/tools_config.py:2372 @ 863e313`

```python
        enabled_toolsets -= default_off
```

**两个分支的不对称是刻意的**:显式分支不做 `x_search` 自动启用(2336-2339 注释:
"一旦用户保存了显式清单,该清单即权威"),也不在最后统一减 default_off。

### 6.2 非可配置平台 toolset 回收(2374-2411)

问题:`discord`、`feishu_doc`、`feishu_drive` 这类 toolset 属于平台默认复合,但不在
`CONFIGURABLE_TOOLSETS` 里 —— checklist 永远不显示它们,用户保存的配置里也永远没有它们。
如果不回收,保存一次 `hermes tools` 就把它们永久丢掉。

`hermes_cli/tools_config.py:2380 @ 863e313`

```python
    _plat_info = PLATFORMS.get(platform)
    _default_ts = _plat_info["default_toolset"] if _plat_info else f"hermes-{platform}"
    platform_tool_universe = set(resolve_toolset(_default_ts))
```

跳过集合:`hermes_cli/tools_config.py:2389 @ 863e313`

```python
    skip = configurable_keys | plugin_ts_keys | platform_default_keys
    skip |= {k for k in TOOLSETS if k.startswith("hermes-")}
    skip |= set(_DEFAULT_OFF_TOOLSETS) - {platform}
```

三条筛选(必须在平台宇宙内 / 不能已被可配置 toolset 全覆盖 / 不能已被已启用集合覆盖):
`hermes_cli/tools_config.py:2405 @ 863e313`

```python
        if not ts_tools or not ts_tools.issubset(platform_tool_universe):
            continue
        if ts_tools.issubset(configurable_tool_universe):
            continue
        if not ts_tools.issubset(claimed):
            enabled_toolsets.add(ts_key)
            claimed.update(ts_tools)
```

`claimed` 边遍历边增长,**结果依赖 `TOOLSETS` 的字典迭代顺序**:两个互相部分重叠的
非可配置 toolset,谁先被遍历谁被加入,后者可能因 `issubset(claimed)` 而被跳过。
Python 3.7+ 里 dict 顺序 = 定义顺序,所以是确定的,但**它是"定义顺序即语义"的隐式耦合**。

另外这里跳过了 `posture` toolset(如 `coding`)—— 那是会话级选择,由
`agent/coding_context.py` 管,不是平台能力(2397-2400 注释)。

### 6.3 插件 toolset 的三态(2413-2433)

`hermes_cli/tools_config.py:2420 @ 863e313`

```python
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

三态编码:**在清单里 = 开;不在清单且未被记录过 = 新插件,默认开;不在清单但被记录过
= 用户关过**。`known_plugin_toolsets` 就是把"缺席"这个二义信号拆成两个的台账。
这与 §5 的 `known_builtin_toolsets` 是**同一套思想的两次实例化**。

### 6.4 context_engine 注入(2435-2451)

`hermes_cli/tools_config.py:2441 @ 863e313`

```python
    context_cfg = config.get("context") or {}
    if not isinstance(context_cfg, dict):
        context_cfg = {}
    context_engine_name = str(context_cfg.get("engine") or "compressor").strip().lower()
```

非默认引擎(≠ `compressor`)时把 `context_engine` toolset 补进去,因为这些工具是
**引擎运行时提供的**,不属于任何静态平台复合。

保留"显式空选"契约:`hermes_cli/tools_config.py:2445 @ 863e313`

```python
    explicit_empty_selection = (
        platform in platform_toolsets
        and isinstance(platform_toolsets.get(platform), list)
        and not toolset_names
    )
```

用户存了 `[]` 就是"我一个工具都不要",此时不注入。

### 6.5 直通项与 MCP 服务器语义(2453-2481)

`hermes_cli/tools_config.py:2455 @ 863e313`

```python
    explicit_passthrough = {
        ts
        for ts in toolset_names
        if ts not in configurable_keys
        and ts not in plugin_ts_keys
        and ts not in platform_default_keys
    }
```

MCP 的三条规则:**默认全开;平台清单里出现任一 MCP 服务器名 → 该清单变成白名单;
出现 `no_mcp` 哨兵 → 全关**。`hermes_cli/tools_config.py:2467 @ 863e313`

```python
    enabled_mcp_servers = enabled_mcp_server_names(config)
    # Allow "no_mcp" sentinel to opt out of all MCP servers for this platform
    if "no_mcp" in toolset_names:
        explicit_mcp_servers = set()
        enabled_toolsets.update(explicit_passthrough - enabled_mcp_servers - {"no_mcp"})
    else:
        explicit_mcp_servers = explicit_passthrough & enabled_mcp_servers
        enabled_toolsets.update(explicit_passthrough - enabled_mcp_servers)
```

`hermes_cli/tools_config.py:2475 @ 863e313`

```python
    if include_default_mcp_servers:
        if explicit_mcp_servers or "no_mcp" in toolset_names:
            enabled_toolsets.update(explicit_mcp_servers)
        else:
            enabled_toolsets.update(enabled_mcp_servers)
```

`or "no_mcp" in toolset_names` 是**必须的**:`explicit_mcp_servers` 在 no_mcp 分支
被置空,没有这一项就会掉进 else 把全部 MCP 服务器加回来。

注意 `no_mcp` 与显式 MCP 名共存时,MCP 名被**一并丢弃**(2471 行的双重减法),
即 `no_mcp` 优先级最高。

### 6.6 全局压制(2483-2491)

`hermes_cli/tools_config.py:2487 @ 863e313`

```python
    agent_cfg = config.get("agent") or {}
    disabled_toolsets = agent_cfg.get("disabled_toolsets") or []
```

在**所有规则之后**减去 —— 这是文档承诺的"一个开关到处关掉 X"。

### 6.7 全无效配置的运行时告警(2493-2516)

场景:迁移或手改把 `hermes-cli` 写成了 `hermes`,`resolve_toolset` 对每个名字都返回
`[]`,平台静默失去全部原生工具。修复是在**解析点**报警,而不是只在
`hermes update` / `hermes doctor` 里查(#38798)。

`hermes_cli/tools_config.py:2499 @ 863e313`

```python
    _explicit = platform_toolsets.get(platform)
    if isinstance(_explicit, list) and _explicit:
        from toolsets import validate_toolset
```

`hermes_cli/tools_config.py:2504 @ 863e313`

```python
        if (
            _named
            and not any(validate_toolset(t) for t in _named)
            and platform not in _warned_invalid_platform_toolsets
        ):
```

去重靠模块级集合(`hermes_cli/tools_config.py:76`),每平台每进程只警告一次 ——
因为这个函数在每次工具解析时都会被调用。

告警本身:`hermes_cli/tools_config.py:2510 @ 863e313`

```python
            logger.warning(
                "platform '%s' has no valid toolsets configured (unknown "
                "name(s): %s) - tools will be unavailable. Run `hermes tools` "
                "to reconfigure. See issue #38798.",
```

`validate_toolset` 只认 `TOOLSETS` / 插件 toolset / registry 别名,**不认 MCP 服务器名**:
`toolsets.py:895 @ 863e313`

```python
def validate_toolset(name: str) -> bool:
```

→ 见 §14 缺陷 D3(纯 MCP 白名单配置会触发误报警告)。

---

## 7. 机制:`_save_platform_tools` 写回与三份台账

`hermes_cli/tools_config.py:2521 @ 863e313`

```python
def _save_platform_tools(config: dict, platform: str, enabled_toolset_keys: Set[str]):
```

### 7.1 先按平台过滤

`hermes_cli/tools_config.py:2532 @ 863e313`

```python
    enabled_toolset_keys = {
        ts for ts in enabled_toolset_keys
        if _toolset_allowed_for_platform(ts, platform)
    }
```

防止"配置所有平台"的 checklist 或手改 config 把 `discord` toolset 打开在 Telegram 上。

### 7.2 保留非可配置项

`hermes_cli/tools_config.py:2548 @ 863e313`

```python
    existing_toolsets = cfg_get(config, "platform_toolsets", platform, default=[])
```

`hermes_cli/tools_config.py:2555 @ 863e313`

```python
    preserved_entries = {
        entry for entry in existing_toolsets
        if entry not in configurable_keys and entry not in platform_default_keys
    }
```

**平台默认复合(`hermes-cli` 等)被刻意排除在保留之外** —— 它们解析成全部工具,
保留下来会在下次读取时静默推翻用户取消的勾选(2542-2545 注释)。
这正是 §5 那个"冻结清单"问题的根因。

`no_mcp` 被主动清除:`hermes_cli/tools_config.py:2563 @ 863e313`

```python
    preserved_entries.discard("no_mcp")
```

理由:picker 没有 no_mcp 复选框,不清的话手工设过 no_mcp 的用户永远无法从 UI 重新开启 MCP。
**副作用**:用户手写的 `no_mcp` 会被任何一次 `hermes tools` 保存静默抹掉。

### 7.3 三份台账写入

主配置:`hermes_cli/tools_config.py:2566 @ 863e313`

```python
    config["platform_toolsets"][platform] = sorted(enabled_toolset_keys | preserved_entries)
```

插件台账(注意 `setdefault` 不会替换"存在但为 null"的键,所以先做类型检查):
`hermes_cli/tools_config.py:2573 @ 863e313`

```python
        if not isinstance(config.get("known_plugin_toolsets"), dict):
            config["known_plugin_toolsets"] = {}
        config["known_plugin_toolsets"][platform] = sorted(plugin_keys)
```

内置台账(记录 **checklist 展示过的全目录**,不是用户勾中的):
`hermes_cli/tools_config.py:2582 @ 863e313`

```python
    if not isinstance(config.get("known_builtin_toolsets"), dict):
        config["known_builtin_toolsets"] = {}
```

### 7.4 与 `agent.disabled_toolsets` 的对账(#49995)

问题:Blank Slate 安装会预填约 27 个 toolset 到 `agent.disabled_toolsets`,而
`_get_platform_tools` 把它当最终否决 —— 桌面 Toolsets UI 里的开关"保存成功"却永远不生效。

`hermes_cli/tools_config.py:2601 @ 863e313`

```python
    agent_cfg = config.get("agent")
    if isinstance(agent_cfg, dict):
        disabled_toolsets = agent_cfg.get("disabled_toolsets")
        if isinstance(disabled_toolsets, list) and disabled_toolsets:
```

`hermes_cli/tools_config.py:2605 @ 863e313`

```python
            newly_enabled = enabled_toolset_keys - preserved_entries
            if newly_enabled:
                remaining = [
                    ts for ts in disabled_toolsets
                    if str(ts) not in newly_enabled
                ]
```

注释声称"只有用户刚刚为这个平台显式启用的 toolset 才被从全局禁用表里清掉"。
**代码实际做的是**:清掉本次保存中**所有被勾中**的 toolset(`preserved_entries` 只含
MCP 名/自定义 toolset,与 `enabled_toolset_keys` 几乎不相交,减法基本是恒等)。
"刚刚启用"这个语义完全依赖调用方的预勾选来自 `_get_platform_tools`(已减过
disabled_toolsets,所以被禁的显示为未勾)。**换一个调用方(传入完整集合的 GUI 批量保存)
就会把整张全局禁用表清空。** 见 §14 缺陷 D4。

最后整份落盘:`hermes_cli/tools_config.py:2614 @ 863e313`

```python
    save_config(config)
```

---

## 8. 机制:`_toolset_has_keys` 三级判定

`hermes_cli/tools_config.py:2617 @ 863e313`

```python
def _toolset_has_keys(
```

**第 0 级 —— vision 特判**(不走 env var,走真实 client 解析):
`hermes_cli/tools_config.py:2628 @ 863e313`

```python
    if ts_key == "vision":
        try:
            from agent.auxiliary_client import resolve_vision_provider_client

            _provider, client, _model = resolve_vision_provider_client()
            return client is not None
        except Exception:
            return False
```

**第 1 级 —— Nous 托管特征**(六个能力可以完全不配 key 而由订阅网关提供):
`hermes_cli/tools_config.py:2637 @ 863e313`

```python
    if ts_key in {"web", "image_gen", "video_gen", "tts", "stt", "browser"}:
```

`feature.available or feature.managed_by_nous` 任一为真即返回 True(2643 行)。

**第 2 级 —— provider 感知**:任一可见 provider 满足即可;**零 env_vars 的 provider
无条件算满足**。`hermes_cli/tools_config.py:2655 @ 863e313`

```python
            env_vars = provider.get("env_vars", [])
            if not env_vars:
                return True  # No-key provider (e.g. Local Browser, Edge TTS)
            if all(get_env_value(e["key"]) for e in env_vars):
                return True
```

**这一行就是 cua-driver 静默 no-op bug(#22737)的源头**:computer_use 的 provider
没有 env_vars,于是"有 key",于是不弹配置,于是 `_run_post_setup("cua_driver")` 永不执行,
`hermes tools` 打印 `✓ Saved` 后什么也没装。修复不在这里,而在
`_toolset_needs_configuration_prompt`(§10)。

**第 3 级 —— 简单需求表**:`hermes_cli/tools_config.py:2663 @ 863e313`

```python
    requirements = TOOLSET_ENV_REQUIREMENTS.get(ts_key, [])
    if not requirements:
        return True
    return all(get_env_value(var) for var, _ in requirements)
```

表里目前只有 vision 一条(`hermes_cli/tools_config.py:747`),而 vision 在第 0 级
就返回了 —— 注释也承认这条元组"永远不会被读到,纯粹是可配置性标记"。

`get_env_value` 本身带 scope 感知 fallback 链:`hermes_cli/config.py:4109 @ 863e313`

```python
def get_env_value(key: str) -> Optional[str]:
```

链条为 `agent.secret_scope.get_secret` → `os.environ`(get_secret 抛非 Unscoped 异常时)
→ `~/.hermes/.env`。

---

## 9. 机制:token 估算与勾选清单

### 9.1 `_estimate_tool_tokens`

解决的问题:让用户在勾选时**看见每个选择的上下文代价**。
`hermes_cli/tools_config.py:2680 @ 863e313`

```python
_tool_token_cache: Optional[Dict[str, int]] = None
```

`hermes_cli/tools_config.py:2697 @ 863e313`

```python
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
```

序列化格式刻意与实际发给 API 的一致:`hermes_cli/tools_config.py:2714 @ 863e313`

```python
    for name in registry.get_all_tool_names():
        schema = registry.get_schema(name)
        if schema:
            # Mirror what gets sent to the API:
            # {"type": "function", "function": <schema>}
            text = _json.dumps({"type": "function", "function": schema})
            counts[name] = len(enc.encode(text))
```

取舍:
- `cl100k_base` 是 OpenAI 的分词器,对 Claude / Llama / Qwen 只是**近似**。
  但目的是相对比较(勾这个贵多少),不是精确计费,近似足够。
- 触发 `import model_tools` = **全量工具发现**,是重导入。缓存到进程级,
  且 tiktoken 或 registry 任一不可用就返回 `{}`,UI 退化为不显示成本条,不报错。
- 缓存**永不失效**:同进程内插件热加载后计数不会更新。

### 9.2 `_prompt_toolset_checklist`

`hermes_cli/tools_config.py:2725 @ 863e313`

```python
def _prompt_toolset_checklist(
```

过滤两类:平台不适用的、config-only 的(`stt`):
`hermes_cli/tools_config.py:2742 @ 863e313`

```python
    effective = [
        (k, l, d) for (k, l, d) in effective_all
        if _toolset_allowed_for_platform(k, platform)
        and k not in _CONFIG_ONLY_TOOLSETS
    ]
```

`[no API key]` 后缀的条件是**两个都要满足**:没 key **且** 该 toolset 确实有 key 概念
(在 TOOL_CATEGORIES 或 TOOLSET_ENV_REQUIREMENTS 里)。
`hermes_cli/tools_config.py:2751 @ 863e313`

```python
        if (
            not _toolset_has_keys(ts_key, force_fresh=force_fresh)
            and (TOOL_CATEGORIES.get(ts_key) or TOOLSET_ENV_REQUIREMENTS.get(ts_key))
        ):
```

**这里的 `_toolset_has_keys` 不传 config**,于是每个 toolset 都会 `load_config()`
一次(有 mtime 缓存,但每次仍付 deepcopy ~135µs);更重的是 `force_fresh` 默认 `True`
(2730 行),对 6 个网关能力 toolset 各触发一次**绕过缓存的门户 HTTP 调用**:
`hermes_cli/nous_account.py:361 @ 863e313`

```python
    if not force_fresh:
```

见 §14 缺陷 D5。

实时成本条对**选中集合的并集**去重后求和 —— 因为多个 toolset 会共享同一个工具:
`hermes_cli/tools_config.py:2768 @ 863e313`

```python
        def status_fn(chosen: set) -> str:
            # Collect unique tool names across all selected toolsets
            all_tools: set = set()
            for idx in chosen:
                all_tools.update(resolve_toolset(ts_keys[idx]))
```

---

## 10. 机制:插件 provider 注入(五个 builder + `_visible_providers`)

### 10.1 五个 builder 的统一形状

五个函数(image_gen / video_gen / web_search / browser / tts)**结构完全同构**:
try-import 注册表 → `_ensure_plugins_discovered()` → `list_providers()` →
逐个取 `get_setup_schema()` → 组装成一个与硬编码 `TOOL_CATEGORIES` provider 行
同形状的 dict + 一个路由标记。

image_gen:`hermes_cli/tools_config.py:2837 @ 863e313`

```python
        row = {
            "name": schema.get("name", provider.display_name),
            "badge": schema.get("badge", ""),
            "tag": schema.get("tag", ""),
            "env_vars": schema.get("env_vars", []),
            "image_gen_plugin_name": provider.name,
        }
```

web_search 多写一个**遗留字段**,让上下游代码不用区分插件与硬编码:
`hermes_cli/tools_config.py:2931 @ 863e313`

```python
        row = {
            "name": schema.get("name", provider.display_name),
            "badge": schema.get("badge", ""),
            "tag": schema.get("tag", ""),
            "env_vars": schema.get("env_vars", []),
            "web_backend": name,
            "web_search_plugin_name": name,
        }
```

browser 同理(`browser_provider` 是写进 `browser.cloud_provider` 的遗留键):
`hermes_cli/tools_config.py:3013 @ 863e313`

```python
        row = {
            "name": schema.get("name", provider.display_name),
            "badge": schema.get("badge", ""),
            "tag": schema.get("tag", ""),
            "env_vars": schema.get("env_vars", []),
            "browser_provider": name,
            "browser_plugin_name": name,
        }
```

TTS 多一层防御:即便注册表已在注册时拒绝影子命名,picker 层再过滤一次:
`hermes_cli/tools_config.py:3059 @ 863e313`

```python
        if name.lower().strip() in _BUILTIN_NAMES:
            continue
```

**设计要点**:插件不需要知道 picker 存在,只需实现 `get_setup_schema()` 返回一个
`{name, badge, tag, env_vars, post_setup?}` 字典。**适配层在 harness 这一侧**,
插件侧零耦合。每个 builder 都用 `except Exception: return []` 整体兜底 ——
插件炸了 picker 少几行,不会打不开。

### 10.2 `web_provider_capabilities`

`hermes_cli/tools_config.py:2946 @ 863e313`

```python
def web_provider_capabilities(backend: str) -> list:
```

问 provider 实例 `supports_search()` / `supports_extract()`,让 GUI 只在有意义处
提供 `web.search_backend` / `web.extract_backend` 的分能力选择(ddgs、brave-free 只搜不抓)。
未注册时**回落到两者都支持**:`hermes_cli/tools_config.py:2970 @ 863e313`

```python
    return ["search", "extract"]
```

这是 fail-open:宁可多给一个选项,也不要在测试上下文(插件尚未发现)里把
硬编码 firecrawl 行的能力判成空。

### 10.3 `_visible_providers` —— 可见性 + 注入的合流点

`hermes_cli/tools_config.py:3084 @ 863e313`

```python
def _visible_providers(
```

**pool-only 用户**(登录了、无付费访问、但有免费工具池额度):
`hermes_cli/tools_config.py:3107 @ 863e313`

```python
    pool_only = bool(
        acct
        and acct.logged_in
        and acct.paid_service_access is not True
        and acct.tool_gateway_entitled
    )
```

两条过滤:
`hermes_cli/tools_config.py:3119 @ 863e313`

```python
        if (
            provider.get("requires_nous_auth")
            and not provider.get("managed_nous_feature")
            and not features.nous_auth_present
        ):
            continue
```

(纯 pre-auth UX 行未登录时隐藏;**托管网关行始终可见** —— 广告效果,选中时才走内联登录)

`hermes_cli/tools_config.py:3127 @ 863e313`

```python
        if (
            pool_only
            and provider.get("managed_nous_feature") == "video_gen"
            and not (acct and acct.tool_gateway_entitled_for("fal-video"))
        ):
            continue
```

(免费池不覆盖 `fal-video`,与其展示一个选中即被拒的行,不如藏掉)

注入五连,**全部以人类可读的分类显示名做 dispatch**:
`hermes_cli/tools_config.py:3137 @ 863e313`

```python
    if cat.get("name") == "Image Generation":
        visible.extend(_plugin_image_gen_providers())
```

`hermes_cli/tools_config.py:3164 @ 863e313`

```python
    if cat.get("name") == "Text-to-Speech":
        visible.extend(_plugin_tts_providers())
```

**没有 `"Speech-to-Text"` 分支**,而 STT 插件注册钩子是存在的
(`hermes_cli/plugins.py:936 @ 863e313`)

```python
        from agent.transcription_registry import register_provider as _register_stt_provider
```

→ 见 §14 缺陷 D6。

### 10.4 `_hidden_nous_gateway_message` —— 已退役的空实现

`hermes_cli/tools_config.py:3170 @ 863e313`

```python
def _hidden_nous_gateway_message(
```

docstring 自陈"Deprecated … Kept as a no-op so call sites stay simple; always returns
an empty string",实现就一行:`hermes_cli/tools_config.py:3186 @ 863e313`

```python
    return ""
```

四处调用点(3447 / 3473 / 3485,以及 4603 / 4614 / 4621 —— 在我这段之外)的
`if hidden_nous_message:` 分支全是**永不执行的死代码**。

---

## 11. 机制:安装态探针与 `provider_readiness_status`

### 11.1 两张不同用途的谓词表

**表 A `_POST_SETUP_INSTALLED`** —— 只服务"要不要强制打开配置流程"。
`hermes_cli/tools_config.py:3189 @ 863e313`

```python
_POST_SETUP_INSTALLED: dict = {
```

只有一条:`hermes_cli/tools_config.py:3203 @ 863e313`

```python
    "cua_driver": lambda: _resolved_cua_driver_cmd() is not None,
```

准入标准写在注释里:(a) post_setup 是该无 key provider 的**唯一**安装副作用,
(b) 安装态检查**便宜且不触发重导入**。

未注册的 key **一律视为已满足**(不改变既有行为),谓词抛异常也视为已满足:
`hermes_cli/tools_config.py:3209 @ 863e313`

```python
    predicate = _POST_SETUP_INSTALLED.get(post_setup_key)
    if predicate is None:
        # No install-state check registered → assume satisfied (don't
        # change behaviour for hooks we haven't explicitly opted in).
        return True
```

后者由测试 `test_post_setup_predicate_exception_does_not_block` 钉住:
一个坏掉的检查不能把用户困在无限配置循环里。

**表 B `_POST_SETUP_READY`** —— 服务 GUI 的 "Ready" 药丸。
`hermes_cli/tools_config.py:3264 @ 863e313`

```python
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

注释明确 `xai_grok` **故意缺席**:它是凭据引导不是安装,由认证分支处理。

### 11.2 三个探针的细节

`_module_installed` 用 `find_spec` 而不是 `import` —— 避免副作用与耗时:
`hermes_cli/tools_config.py:3220 @ 863e313`

```python
def _module_installed(module_name: str) -> bool:
```

`_agent_browser_installed` 做了一件很脏但必要的事:**戳掉别的模块的私有缓存**。
`hermes_cli/tools_config.py:3245 @ 863e313`

```python
    bt = sys.modules.get("tools.browser_tool")
    if bt is not None:
        bt._cached_chromium_installed = None
```

原因写在 docstring:安装跑在 spawn 出去的 `hermes tools post-setup` 子进程里,
而这个探针跑在长驻的 web-server/CLI 进程里,后者可能缓存了安装前的
"Chromium missing"。不清缓存,药丸装完也不变绿。
**这是跨进程副作用与进程内缓存冲突的典型症状**,解法是"探针负责让缓存失效"。

`_camofox_installed` 是纯路径存在性检查:`hermes_cli/tools_config.py:3255 @ 863e313`

```python
    return (PROJECT_ROOT / "node_modules" / "@askjo" / "camofox-browser").exists()
```

`PROJECT_ROOT` 是包安装位置的上一级(`hermes_cli/tools_config.py:78`),
与 `_run_post_setup("camofox")` 的安装目标(1759 行)一致 —— 探针镜像安装逻辑。

`_cloud_agent_browser_installed` 只查 CLI 在不在,因为云 provider 自带 Chromium:
`hermes_cli/tools_config.py:3277 @ 863e313`

```python
def _cloud_agent_browser_installed() -> bool:
```

**"本地浏览器 = CLI + Chromium"与"云浏览器 = 仅 CLI"分成两个 hook key**
(`agent_browser` vs `browserbase`)是一次真实事故的产物:注释(639-645 行)说,
云行原本用 `agent_browser`,导致没装本地 Chromium 的机器上这行**永远显示 needs setup**。

### 11.3 `provider_readiness_status` 的判定顺序

`hermes_cli/tools_config.py:3287 @ 863e313`

```python
def provider_readiness_status(
```

顺序是:**env_vars → 认证 → post_setup 安装态**。

`hermes_cli/tools_config.py:3315 @ 863e313`

```python
    env_vars = provider.get("env_vars", [])
    if env_vars:
        if all(get_env_value(e["key"]) for e in env_vars):
            return "ready"
        return "needs_keys"
```

**这个 early return 让所有"既有 env_vars 又有 post_setup"的行永远走不到安装态检查。**
见 §14 缺陷 D7。

认证分支复用与 CLI 选中时相同的**逐分类**权益门:
`hermes_cli/tools_config.py:3321 @ 863e313`

```python
    managed_feature = provider.get("managed_nous_feature")
    if provider.get("requires_nous_auth") or managed_feature:
```

分类映射来自 `hermes_cli/nous_subscription.py:37 @ 863e313`

```python
MANAGED_FEATURE_COVERAGE_CATEGORY: Dict[str, str] = {
```

注意登录且有权益后**故意 fall through** 而不是直接 return ready(3343-3345 注释):
托管行也可能带本机安装钩子。

post_setup 分支:`hermes_cli/tools_config.py:3347 @ 863e313`

```python
    post_setup = provider.get("post_setup")
    if post_setup:
        if post_setup == "xai_grok":
            return "ready" if _xai_credentials_present() else "needs_auth"
```

谓词抛异常时**返回 ready 而不是 needs_setup**(3355-3357):
"不稳定的探测不得制造一个警告状态"。这是一条明确的产品级取舍:
宁可漏报也不误报。

没有注册探针时,退回"当前激活的 provider 即视为已安装完成"
(选中一行就会跑它的 hook):`hermes_cli/tools_config.py:3360`。

---

## 12. 机制:是否需要弹配置(`_toolset_needs_configuration_prompt`)

`hermes_cli/tools_config.py:3367 @ 863e313`

```python
def _toolset_needs_configuration_prompt(
```

不在 TOOL_CATEGORIES 的直接回落 `_toolset_has_keys`(3374-3376)。在的话,
**先做 #22737 的修复**:任一可见 provider 的 post_setup 安装态未满足即强制走配置流程。
`hermes_cli/tools_config.py:3382 @ 863e313`

```python
    for provider in _visible_providers(cat, config, force_fresh=force_fresh):
        post_setup = provider.get("post_setup")
        if post_setup and not _post_setup_already_installed(post_setup):
            return True
```

然后是四个"这一类的配置落点在哪个 config 键"的特判:
`hermes_cli/tools_config.py:3387 @ 863e313`

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

image_gen 的判据是"in-tree FAL 已配置 **或** 任一插件 provider 可用":
`hermes_cli/tools_config.py:3396 @ 863e313`

```python
    if ts_key == "image_gen":
```

video_gen 没有 in-tree 后备,只问插件:`hermes_cli/tools_config.py:3415 @ 863e313`

```python
    if ts_key == "video_gen":
```

兜底:`hermes_cli/tools_config.py:3433 @ 863e313`

```python
    return not _toolset_has_keys(ts_key, config, force_fresh=force_fresh)
```

**注意 post_setup 循环是"任一未装即弹"**:如果某分类里有多个带 post_setup 的 provider,
即便用户已经配好并激活了另一个,只要那个未装的 provider 可见,就会被反复拉进配置流程。
目前只有 `cua_driver` 注册在表 A 里,所以只影响 computer_use,尚未暴露。

---

## 13. 机制:分类配置 UI 与"谁是当前激活 provider"

### 13.1 `_configure_tool_category`

`hermes_cli/tools_config.py:3436 @ 863e313`

```python
def _configure_tool_category(
```

Python 版本门(**当前无数据触发,见 §14 缺陷 D8**):
`hermes_cli/tools_config.py:3455 @ 863e313`

```python
    if cat.get("requires_python"):
```

单 provider 直配,多 provider 弹菜单:`hermes_cli/tools_config.py:3463 @ 863e313`

```python
    if len(providers) == 1:
```

菜单标签三段拼装(badge / tag / 配置态 / Nous 标记):
`hermes_cli/tools_config.py:3504 @ 863e313`

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

跳过项追加在最后,用**索引越界**判断跳过:
`hermes_cli/tools_config.py:3531 @ 863e313`

```python
        provider_choices.append("Skip — keep defaults / configure later")
```

`hermes_cli/tools_config.py:3543 @ 863e313`

```python
        if provider_idx >= len(providers):
            _print_info(f"  Skipped {name}")
            return
```

`providers` 为空时也走 else 分支,菜单只有一个 "Skip",索引 0 ≥ 0 成立 → 优雅跳过。

### 13.2 `_is_provider_active`

`hermes_cli/tools_config.py:3550 @ 863e313`

```python
def _is_provider_active(
```

判定顺序:image 插件 → video 插件(带托管守卫)→ 托管特征 → 各类 `*_provider` 键。

`hermes_cli/tools_config.py:3557 @ 863e313`

```python
    plugin_name = provider.get("image_gen_plugin_name")
```

`hermes_cli/tools_config.py:3562 @ 863e313`

```python
    video_plugin_name = provider.get("video_gen_plugin_name")
    if video_plugin_name and not provider.get("managed_nous_feature"):
```

**不对称**:video 分支显式排除托管行,image 分支没有 —— 见 §14 缺陷 D9。

托管 image/video 的"激活"定义相当微妙:**未显式选别的 provider,且未把
`use_gateway` 显式设为假**:`hermes_cli/tools_config.py:3573 @ 863e313`

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

`stt` 的默认值语义单独写死在这里:**未设置 = local**。
`hermes_cli/tools_config.py:3611 @ 863e313`

```python
    if provider.get("stt_provider"):
        # Default stt.provider is "local" — an unset key means Local Whisper.
        current = cfg_get(config, "stt", "provider") or "local"
        return current == provider["stt_provider"]
```

非托管 FAL 行的激活条件写死了 `== "fal"`:`hermes_cli/tools_config.py:3621 @ 863e313`

```python
    if provider.get("imagegen_backend"):
```

—— `IMAGEGEN_BACKENDS` 号称为未来后端预留,但这里硬编码了 fal,新后端加进
`IMAGEGEN_BACKENDS` 也不会被判成 active。

### 13.3 `_detect_active_provider_index`

`hermes_cli/tools_config.py:3634 @ 863e313`

```python
def _detect_active_provider_index(
```

`hermes_cli/tools_config.py:3641 @ 863e313`

```python
    for i, p in enumerate(providers):
        if _is_provider_active(p, config, force_fresh=force_fresh):
            return i
        # Fallback: env vars present → likely configured
        env_vars = p.get("env_vars", [])
        if env_vars and all(get_env_value(v["key"]) for v in env_vars):
            return i
    return 0
```

**同一次循环里两个 return** —— fallback 在遍历完之前就可能命中,导致
"排在前面、只是配了 key"的 provider 抢走 "排在后面、真正激活" 的默认高亮。
见 §14 缺陷 D10。

---

## 14'. 机制:image / video gen 模型选择器(3651-3700 及其自然结尾 3914)

`_fal_model_catalog` 惰性从工具模块取表,避免模块导入期的重依赖:
`hermes_cli/tools_config.py:3664 @ 863e313`

```python
def _fal_model_catalog():
    """Lazy-load the FAL model catalog from the tool module."""
    from tools.image_generation_tool import FAL_MODELS, DEFAULT_MODEL
    return FAL_MODELS, DEFAULT_MODEL
```

后端注册表:`hermes_cli/tools_config.py:3670 @ 863e313`

```python
IMAGEGEN_BACKENDS = {
    "fal": {
        "display": "FAL.ai",
        "config_key": "image_gen",
        "catalog_fn": _fal_model_catalog,
    },
}
```

选择器主体(3689-3748)的四个动作:取目录 → 修复被写坏的 config 段 → 把当前模型置顶
→ 按列宽格式化。修复分支值得记:`hermes_cli/tools_config.py:3705 @ 863e313`

```python
    cur_cfg = config.setdefault(cfg_key, {})
    if not isinstance(cur_cfg, dict):
        cur_cfg = {}
        config[cfg_key] = cur_cfg
```

(测试 `test_picker_repairs_corrupt_config_section` 就钉这个)

当前模型置顶,让光标默认落在它上面:`hermes_cli/tools_config.py:3709 @ 863e313`

```python
    current_model = cur_cfg.get("model") or default_model
    if current_model not in catalog:
        current_model = default_model
```

列宽用**全体模型 id 的最大长度**,而不是选中项:
`hermes_cli/tools_config.py:3719 @ 863e313`

```python
        "model": max(len(m) for m in model_ids),
```

写回:`hermes_cli/tools_config.py:3747 @ 863e313`

```python
    cur_cfg["model"] = chosen
```

插件版目录把 provider 自报的 `list_models()` 规整成同一形状:
`hermes_cli/tools_config.py:3774 @ 863e313`

```python
    catalog = {m["id"]: m for m in models if isinstance(m, dict) and "id" in m}
```

插件版选择器(3778-3830)几乎逐行复制内置版 —— **两份平行实现**,
差别只在目录来源和 `config_key` 固定为 `image_gen`。同样的复制在
`_plugin_video_gen_catalog`(`hermes_cli/tools_config.py:3893 @ 863e313`)

```python
def _plugin_video_gen_catalog(plugin_name: str):
```

xAI Imagine 的存储三选一(唯一一个写三层嵌套 config 的地方):
`hermes_cli/tools_config.py:3843 @ 863e313`

```python
    storage_cfg = xai_cfg.setdefault("storage", {})
```

`hermes_cli/tools_config.py:3861 @ 863e313`

```python
    if idx == 1:
        storage_cfg["enabled"] = False
        _print_success("  xAI stored public URLs disabled")
    elif idx == 2:
        storage_cfg["enabled"] = True
        storage_cfg["public_url"] = True
        storage_cfg["expires_after"] = 2 * 24 * 60 * 60
```

选中插件 image provider 的落盘(**同时把 use_gateway 关掉**):
`hermes_cli/tools_config.py:3882 @ 863e313`

```python
    img_cfg["provider"] = plugin_name
    img_cfg["use_gateway"] = False
```

—— 与 `_is_provider_active` 的托管判定(3579)正好互为反向:选插件即退出网关。

---

## 14. 配置键与环境变量总表

### 14.1 config.yaml 键

| 键 | 默认 | 读/写行 | 语义与 fallback |
|---|---|---|---|
| `platform_toolsets.<platform>` | 无 → `[<平台默认复合>]` | 读 `tools_config.py:2232-2247`;写 `:2566` | 非 list 即回落平台默认;元素强制 `str()` |
| `known_builtin_toolsets.<platform>` | 无 → 空集 | 读 `:2200`;写 `:2584` | checklist 展示过的**全目录**,用于区分"取消勾选"与"当时不存在" |
| `known_plugin_toolsets.<platform>` | 无 → 空集 | 读 `:2421`;写 `:2575` | 同上,插件版;写前做 `isinstance(...,dict)` 归一(null 键陷阱) |
| `mcp_servers.<name>.enabled` | `True` | 读 `:2137` | 经 `_parse_enabled_flag`;非 dict 的条目静默丢弃;无法识别的字符串 → True |
| `agent.disabled_toolsets` | `[]` | 读 `:2488`;写(裁剪)`:2612` | 在所有规则**之后**减去;保存 picker 时会被裁剪 |
| `context.engine` | `"compressor"` | 读 `:2444` | `str(x or "compressor").strip().lower()`;非 compressor → 注入 `context_engine` toolset |
| `tts.provider` | 无 | 读 `:3389`(存在性)、`:3594`、`:3610` | 缺失即"需要配置" |
| `web.backend` | 无 | 读 `:3392`、`:3605`、`:3619` | 同上 |
| `browser.cloud_provider` | 无 | 读 `:3395`、`:3602`、`:3616` | 同上 |
| `stt.provider` | `"local"`(隐式) | 读 `:3599`、`:3613` | 唯一显式写出默认的:`cfg_get(...) or "local"` |
| `image_gen.provider` | 无(视同 fal) | 读 `:3560`、`:3576`、`:3625`;写 `:3882` | `{None,"","fal"}` 三值等价于"未选别家" |
| `image_gen.use_gateway` | `False` | 读 `:3579`、`:3629`;写 `:3883` | 经 `is_truthy_value(..., default=False)` |
| `image_gen.model` | 后端 `DEFAULT_MODEL` | 读 `:3709`、`:3793`;写 `:3747`、`:3829` | 不在目录内即回落默认 |
| `image_gen.xai.storage.enabled` | 无 | 写 `:3862`/`:3865`/`:3870` | 三选一菜单 |
| `image_gen.xai.storage.public_url` | 无 | 写 `:3866`、`:3871` | |
| `image_gen.xai.storage.expires_after` | 无 | 写 `:3867`(172800)、`:3872`(None) | None = 永不过期 |
| `video_gen.provider` | 无(视同 fal) | 读 `:3565`、`:3585` | |
| `video_gen.use_gateway` | `False` | 读 `:3588` | |
| `video_gen.xai.storage.*` | 无 | 由 `_configure_xai_imagine_storage("video_gen", ...)` 写(调用点 `:4032`,在本段外) | |
| `plugins.enabled` | — | 由 langfuse 钩子经 `plugins_cmd._save_enabled_set` 写(`:1934`) | 跨模块写入 |

### 14.2 环境变量

| 变量 | 读取点 | 读它的函数 | 说明 |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `tools_config.py:2077` | `_get_enabled_platforms` | 仅存在性 |
| `DISCORD_BOT_TOKEN` | `:2079` | 同上 | |
| `SLACK_BOT_TOKEN` | `:2081` | 同上 | |
| `WHATSAPP_ENABLED` | `:2083` | 同上 | **只判存在,不解析真假** |
| `QQ_APP_ID` | `:2085` | 同上 | |
| `XAI_API_KEY` | `:1954` 读、`:2000` 写 | `_run_post_setup("xai_grok")` | 另在 `_xai_credentials_present`(`:189`/`:196`/`:197`)读三次:`tools.xai_http` → `os.environ` → `secret_scope` |
| `HASS_TOKEN` | `:205`(经 `_homeassistant_credentials_present`) | `_get_platform_tools` 在 `:2300`/`:2362` 调用 | 有 token → homeassistant 脱离 default-off |
| `OPENROUTER_API_KEY` | `:748` 表项,由 `_toolset_has_keys:2666` 读 | 实际不可达(vision 在 `:2628` 先返回) | 纯"可配置性标记" |
| `HERMES_CUA_DRIVER_CMD` | `:757` | `_cua_driver_cmd`,经 `_resolved_cua_driver_cmd` 被 `_POST_SETUP_INSTALLED`/`_POST_SETUP_READY` 用 | 空串 → `"cua-driver"` |
| 任意 provider `env_vars[].key` | `:2658`、`:3317`、`:3510`、`:3646` | `_toolset_has_keys` / `provider_readiness_status` / `_configure_tool_category` / `_detect_active_provider_index` | 全部经 `get_env_value`(scope → environ → `.env`) |
| `CAMOFOX_URL` | 作为 provider env_var(`tools_config.py:652`) | 同上 | 带 `default: http://localhost:9377` |
| `BROWSERBASE_API_KEY` / `BROWSERBASE_PROJECT_ID` | `plugins/browser/browserbase/provider.py:288`/`:293` | 同上 | |
| `BROWSER_USE_API_KEY` | `plugins/browser/browser_use/provider.py:316`;另作 `override_env_vars`(`tools_config.py:639`) | 同上 | |
| `FIRECRAWL_API_KEY` | `plugins/browser/firecrawl/provider.py:166`;`override_env_vars`(`tools_config.py:507`) | 同上 | |
| `FAL_KEY` | `override_env_vars`(`tools_config.py:541`、`:561`) | 托管行覆盖 | |
| `VOICE_TOOLS_OPENAI_KEY` / `OPENAI_API_KEY` | `override_env_vars`(`tools_config.py:341`、`:434`) | 托管 TTS/STT 行覆盖 | |
| `HERMES_HOME` | 本段不直接读;`_cua_install_home` 等使用 | — | 测试通过它做隔离 |

---

## 15. 文档 / 注释与代码的出入

**C1 —— `IMAGEGEN_BACKENDS` 的字段说明整段过期。** 注释说条目暴露
`config_key` / `model_catalog_fn` / `default_model`。`hermes_cli/tools_config.py:3653 @ 863e313`

```python
# IMAGEGEN_BACKENDS is a per-backend catalog. Each entry exposes:
```

实际字典有 `display` / `config_key` / `catalog_fn`,**没有** `model_catalog_fn`,
**没有** `default_model`(默认值是 `catalog_fn()` 返回元组的第二项):
`hermes_cli/tools_config.py:3670 @ 863e313`

```python
IMAGEGEN_BACKENDS = {
```

**C2 —— `_visible_providers` docstring 自相矛盾。** 它说托管网关行"always shown —
even to logged-out / unentitled users":`hermes_cli/tools_config.py:3093 @ 863e313`

```python
    Nous-managed Tool Gateway rows (``managed_nous_feature``) are always
```

但同函数 `hermes_cli/tools_config.py:3127-3132` 就为 pool-only 用户隐藏了托管 video_gen 行。
"always" 应为 "always, except the managed video row for pool-only users"。

**C3 —— `_save_platform_tools` 的 disabled_toolsets 注释说得比代码窄。**
注释说"Only toolsets the user just explicitly enabled FOR THIS PLATFORM are cleared":
`hermes_cli/tools_config.py:2596 @ 863e313`

```python
    # Only toolsets the user just explicitly enabled FOR THIS PLATFORM are
```

代码清掉的是本次保存里**所有被勾中**的 toolset(`enabled_toolset_keys - preserved_entries`,
而 `preserved_entries` 与之几乎不相交)。"just"这个限定由调用方的预勾选来源保证,
不由本函数保证。

**C4 —— 官方文档说 `agent.disabled_toolsets` 总是最后生效、无条件删除。**
`website/docs/user-guide/configuration.md:740 @ 863e313`

```markdown
This applies **after** per-platform tool config (`platform_toolsets` written by
```

对**读**路径成立(`tools_config.py:2491`),但对**写**路径不成立:跑一次
`hermes tools` 并保留某 toolset 勾选,就会把它从 `agent.disabled_toolsets` 里删掉
(`tools_config.py:2607-2612`)。文档没有提到这条自动裁剪。

**C5 —— `_hidden_nous_gateway_message` 的 docstring 是准确的("always returns an
empty string"),但四处调用点的分支代码没有随之删除**,构成注释诚实、代码残留的组合。

**C6 —— 测试文件里留下了没有测试体的注释块。**
`tests/hermes_cli/test_tools_config.py:632 @ 863e313`

```python
# ── Post-setup readiness predicates for the browser rows ─────────────────────
```

该注释块之后到 640 行的下一个注释块之间没有任何测试函数 —— 说明这组
readiness 谓词的回归测试被删过而说明文字留了下来。

---

## 16. 可疑缺陷(只记录不修)

**D1 —— `valid_post_setup_keys` 漏掉 TTS 插件的 post_setup。**
builder 元组只有四个(`tools_config.py:2026-2031`),不含 `_plugin_tts_providers`,
但后者会透传 `post_setup`(`tools_config.py:3078`)。
**怎么踩到**:装一个声明了 `post_setup` 的 TTS 插件 → GUI 点"Run setup" →
`hermes tools post-setup <key>` 报 "Unknown post-setup key" 退出码 2;
`_run_post_setup` 里若无对应分支则本就 no-op,但 CLI 的报错会把用户引向"key 非法"
而非"钩子未实现"。

**D2 —— `_get_enabled_platforms` 与 `PLATFORMS` 注册表是两套真相。**
前者硬编码 5 个平台的 token 环境变量(`tools_config.py:2076-2087`),后者来自
`hermes_cli.platforms` 注册表(`tools_config.py:310`)。
**怎么踩到**:新增一个 gateway 平台并注册进 `platforms`,`hermes tools` 的
"配置所有平台"流程仍不会列出它,因为汇总走的是 `_get_enabled_platforms`。

**D3 —— 纯 MCP 白名单配置会触发误导性的 "no valid toolsets" 警告。**
`validate_toolset` 不认 MCP 服务器名(`toolsets.py:895-912`),而
`platform_toolsets.<p> = ["github"]`(只想要某个 MCP 服务器、不要原生工具)是
第 6.5 节明确支持的用法。
**怎么踩到**:此配置每进程记一条 `logger.warning("... tools will be unavailable ...")`
(`tools_config.py:2510`),而实际上 MCP 工具是正常可用的 —— 用户按提示跑
`hermes tools` 重配,反而会因 §7.2 的 `no_mcp` 清除/复合排除逻辑改变其配置。

**D4 —— `newly_enabled` 的减法几乎是恒等,语义靠调用方兜着。**
`tools_config.py:2605`:`enabled_toolset_keys` 来自 checklist(全是可配置 key),
`preserved_entries` 全是非可配置项,两者交集通常为空。
**怎么踩到**:任何直接调用 `_save_platform_tools` 并传入"当前完整启用集"的调用方
(而非"用户新勾的"),都会把 `agent.disabled_toolsets` 里所有与之同名的条目清空 ——
全局压制表被一次平台级保存清掉。

**D5 —— `_prompt_toolset_checklist` 在渲染前可能发起多次绕过缓存的门户 HTTP 调用。**
`force_fresh` 默认 `True`(`tools_config.py:2730`),标签循环对每个 toolset 调
`_toolset_has_keys(ts_key, force_fresh=force_fresh)`(`tools_config.py:2752`),
其中 6 个网关能力 key 会进入 `get_nous_subscription_features(force_fresh=True)`
→ `get_nous_portal_account_info(force_fresh=True)` → 绕过缓存打 `/api/oauth/account`
(`hermes_cli/nous_account.py:361`)。且未传 `config`,每次还 `load_config()` 一遍。
**怎么踩到**:离线或门户慢时,`hermes tools` 的勾选界面出现明显卡顿甚至逐次超时。
(`_visible_providers` 已支持传入 `features` 快照复用,测试
`test_visible_providers_reuses_logged_out_feature_snapshot` 钉的就是这条路径;
但 checklist 这一侧没用上。)

**D6 —— 插件注册的 STT provider 永远进不了 picker。**
`hermes_cli/plugins.py:936` 提供了 `register_transcription_provider` 钩子,
`agent/transcription_registry.py:102` 有 `list_providers()`,但 `_visible_providers`
的注入分支只覆盖 Image Generation / Video Generation / Web Search & Extract /
Browser Automation / Text-to-Speech(`tools_config.py:3137-3165`),**没有
Speech-to-Text**。
**怎么踩到**:写一个 STT 插件,`hermes tools` → Speech-to-Text 里看不到它;
只能手改 `stt.provider`。

**D7 —— 有 env_vars 的 provider 即使安装钩子没跑,GUI 也报 "ready"。**
`provider_readiness_status` 在 `tools_config.py:3316-3319` 就 return 了,永远到不了
`tools_config.py:3351` 的 `_POST_SETUP_READY` 查表。而 Camofox 行同时有
`CAMOFOX_URL`(`tools_config.py:652`)和 `post_setup: "camofox"`(`tools_config.py:656`),
Browserbase / Browser Use / Firecrawl 三个云行同样是"有 key + post_setup: browserbase"
(`plugins/browser/browserbase/provider.py:299` 等)。
**结果**:`_POST_SETUP_READY["camofox"]` **完全不可达**;
`_POST_SETUP_READY["browserbase"]` 只对唯一的零 key 行(Nous Subscription 浏览器行,
`tools_config.py:635`)可达。
**怎么踩到**:填好 Browserbase 的两个 key 但从未装 agent-browser CLI → 药丸显示
Ready → 点运行 → 运行时才失败。

**D8 —— `requires_python` 分支无数据可触发。**
`tools_config.py:3455` 读 `cat.get("requires_python")`,而全文件搜索显示只有
3455/3456 两处出现该字符串,`TOOL_CATEGORIES` 里没有任何条目声明它。死分支。

**D9 —— `_is_provider_active` 的 image/video 插件分支不对称。**
video 分支带 `and not provider.get("managed_nous_feature")` 守卫(`tools_config.py:3563`),
image 分支没有(`tools_config.py:3557-3560`)。
**怎么踩到**:若将来某个托管 Nous image 行同时带 `image_gen_plugin_name`,
它会走进插件分支比对 `image_gen.provider`,绕过 3573 行那套
`use_gateway` / provider 三值的托管判定,菜单默认高亮与 `[active]` 标记都会错。

**D10 —— `_detect_active_provider_index` 的 env-var 兜底会抢在真正激活的 provider 之前。**
`tools_config.py:3641-3648` 在**同一次遍历**里既判 active 又判 env-var 兜底。
**怎么踩到**:用户配过 provider A 的 key 但当前激活的是排在后面的 provider B,
打开 `hermes tools` 重配该分类时,菜单默认高亮落在 A;闭眼回车就把 provider 从 B 换成 A。

**D11 —— 模型选择器在 `default_model` 不在目录里时会 KeyError。**
`tools_config.py:3709-3711` 把 `current_model` 回落到 `default_model` 但不再校验,
随后 `tools_config.py:3817` 直接 `catalog[mid]`。
**怎么踩到**:一个插件的 `default_model()` 返回了不在 `list_models()` 里的 id
(或返回 None),选择器抛 KeyError 打断整个 `hermes tools` 流程。

**D12 —— 非可配置 toolset 回收的结果依赖 `TOOLSETS` 定义顺序。**
`tools_config.py:2409-2411` 的 `claimed` 集合边遍历边扩张。
**怎么踩到**:两个部分重叠的非可配置 toolset,调整 `toolsets.py` 里的定义顺序
就会改变哪个被回收 —— 一次纯排版的改动可能静默改变某平台的工具集。

**D13 —— `hermes tools` 保存会静默抹掉手工设置的 `no_mcp`。**
`tools_config.py:2563` 无条件 `preserved_entries.discard("no_mcp")`。
**怎么踩到**:用户手写 `no_mcp` 关掉某平台的全部 MCP 服务器,之后为了别的原因
跑一次 `hermes tools` 保存,MCP 服务器全部悄悄恢复。这是"UI 可达性"与
"手工配置不被破坏"的一次明确取舍,选了前者,但没有任何提示。

---

## 17. 配套测试(行为规格)

| 文件 | 覆盖本段的哪一块 |
|---|---|
| `tests/hermes_cli/test_tools_config.py` | 主规格:#38798 无效配置告警(36/53/63)、HASS_TOKEN → homeassistant(83/104)、discord 平台隔离(125)、vision key 判定(141)、MCP 名保留(158)、数字 MCP 名不崩(312)、`IMAGEGEN_BACKENDS`(348-372)、模型选择器含"修复损坏配置段"(374-431)、插件 toolset 去重(432)、checklist 差异范围(476)、`_visible_providers` 复用 features 快照(548/580)、`_RECENTLY_SHIPPED_TOOLSETS` 四条(680/696/710/721) |
| `tests/hermes_cli/test_post_setup_gating.py` | `_toolset_needs_configuration_prompt` 的 post_setup 门(#22737)与"谓词抛异常不得卡死"(18/31) |
| `tests/hermes_cli/test_tool_token_estimation.py` | `_estimate_tool_tokens` |
| `tests/hermes_cli/test_stt_picker.py` | `_checklist_toolset_keys` 排除 `stt`、`_configure_stt_model` |
| `tests/hermes_cli/test_image_gen_picker.py` | `_plugin_image_gen_catalog` |
| `tests/hermes_cli/test_video_gen_picker.py` / `test_tts_picker.py` | 对应插件 picker |
| `tests/hermes_cli/test_tools_disable_enable.py` | 非交互 enable/disable(消费 `_get_platform_tools`/`_save_platform_tools`) |
| `tests/cli/test_cli_tools_command.py` | `hermes tools` 命令层 |
| `tests/gateway/test_api_server_toolset.py` | gateway 侧对 `_get_platform_tools` 的依赖 |
| `tests/cron/test_scheduler.py` | cron 复用 `enabled_mcp_server_names` / `_get_platform_tools` |
| `tests/hermes_cli/test_setup_blank_slate.py` | Blank Slate 写 `platform_toolsets` + `agent.disabled_toolsets`(D4/C4 的上游) |
| `tests/hermes_cli/test_aux_picker_inventory.py` | provider 行清单一致性 |

---

## 18. 重实现要点(从零重写这段必须知道的)

1. **"平台启用了哪些 toolset"必须是一个纯函数,且全仓只有一份。**
   CLI、五个 gateway 平台、cron、Web GUI 全部调用同一个
   `_get_platform_tools(config, platform)`。任何一处另写一份推断逻辑,
   就会出现"CLI 里有的工具 cron 里没有"这类不可复现的报障。
   同理,MCP 成员判定被单独抽成 `enabled_mcp_server_names` 供 cron 复用。

2. **"用户没选它"和"当时还没有它"是两个不同的信号,配置文件里必须能区分。**
   把选择存成"冻结的显式清单"会永久丢掉未来新增项。解法是**同时记录
   "UI 展示过什么"**(`known_builtin_toolsets` / `known_plugin_toolsets`),
   把"缺席"这个二义信号拆成"declined"与"never offered"。
   代价是要维护一个"当期发布窗口"常量(`_RECENTLY_SHIPPED_TOOLSETS`),
   并接受它有严格的生命周期纪律(同版上线、下版清空)。

3. **子集反向推断必须用静态成员,不能用运行时合并后的成员。**
   插件/overlay 往 toolset 里注册一个工具,就会让"toolset ⊆ 平台复合"这个判断失败,
   整个 toolset 掉线(#49622)。所以 `resolve_toolset` 必须提供
   `include_registry=False` 这个开关,反向映射一律用它。

4. **能力开关要分两层:便宜的本地开关 + 昂贵的运行时门控。**
   toolset 是否"开启"必须能在不发网络请求的前提下判定(`_get_platform_tools`
   每次会话/每次 cron tick 都要跑);"有没有凭据、有没有权益"交给工具自己的
   `check_fn` 在注册 schema 时判。这条是 `_RECENTLY_SHIPPED_TOOLSETS` 注释里
   写得最清楚的一条设计原则。

5. **插件 provider 的适配层放在 harness 侧,插件只暴露一个 `get_setup_schema()`。**
   五个 builder 结构完全同构,把插件返回的 schema 翻译成 picker 行 +
   一个路由标记(`*_plugin_name`),并保留遗留字段(`web_backend`、`browser_provider`)
   让下游代码不必区分来源。每个 builder 整体 try/except,插件炸了只少几行。
   **不要用分类的人类可读显示名做 dispatch**(本实现用了 `cat["name"] == "Image Generation"`),
   改个标题就会静默丢掉全部插件 provider;用稳定的 key。

6. **"就绪"必须是服务端算出来的真相,不能是"没有 env_vars 就绿灯"。**
   拆成 `needs_keys` / `needs_auth` / `needs_setup` / `ready` 四态,并给每个安装钩子
   注册一个**便宜的安装态谓词**。两条纪律:谓词抛异常一律当 ready(不制造假警告);
   判定顺序不能让 env_vars 短路掉安装态检查(本实现踩了这个坑,见 D7)。

7. **配置写回要显式列出"保留什么"而不是"删除什么"。**
   `_save_platform_tools` 的核心是三条决策:可配置 key 用新值覆盖、
   平台默认复合**必须丢弃**(否则下次读取时全量解析会推翻取消勾选)、
   其余(MCP 名/自定义 toolset)原样保留。任何"顺手保留"都会变成静默覆盖。

8. **给"全局压制列表"想清楚它与 UI 的关系。**
   `agent.disabled_toolsets` 作为读路径最后一道否决很干净,但它会让 UI 开关
   "保存成功却不生效"(#49995)。本实现的补救是保存时裁剪该列表 —— 这让
   "读路径最后生效"这条不变式在写路径上被打破了,文档也没跟上(C4)。
   若重来,更好的做法可能是:UI 在渲染时就显示"此 toolset 被全局禁用",
   并让用户显式决定是否解除,而不是保存时静默改写另一个键。
