# r8a-raw-tools-config-c · tools_config.py:3700-5452

底稿。基线 `NousResearch/hermes-agent @ 863e31318553cda8ad61df681d08175364d4164b`(下称 `863e313`)。
本段 = `hermes_cli/tools_config.py` 第 3700 行到文件末尾 5452 行。为把这一段讲清楚,少量引用了段外
(同文件 96-3699、`hermes_cli/config.py`、`hermes_cli/curses_ui.py`、`tools/mcp_tool.py`、
`agent/auxiliary_client.py`)的定义,均已标注路径。

---

## 0. 这一段在整个模块里的位置

模块 docstring 把 `hermes tools` 的形状讲成三步:选平台 → 勾选 toolset → 给新开的、需要 key 的工具跑
provider 感知的配置;落盘在 `~/.hermes/config.yaml` 的 `platform_toolsets` 键下。
`hermes_cli/tools_config.py:1-10 @ 863e313`

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

3700-5452 正好覆盖这条链路的**后半段 + 全部出口**:

| 区段 | 行 | 干什么 |
| --- | --- | --- |
| 图像/视频/STT 模型选择器 | 3700-4033 | 选完 provider 之后再选具体 model,写 `*.model` |
| provider 落盘核心 | 4035-4140 | `_write_provider_config` + GUI 用的非交互入口 `apply_provider_selection` |
| provider 交互配置 | 4142-4328 | `_configure_provider`:Nous 门禁 → 写 provider 键 → 问 env → post-setup → 模型选择器 |
| vision 专用配置面 | 4330-4491 | vision 不走通用 env 提示,自己有 provider+model 选择器 |
| 简单 env 需求 | 4493-4522 | `TOOLSET_ENV_REQUIREMENTS` 的兜底提示 |
| reconfigure 面 | 4524-4844 | 与上面几乎逐行镜像的"改已配好的工具"分支 |
| CLI 主入口 | 4849-5170 | `tools_command`:summary / 首装线性流 / 老用户菜单循环 |
| MCP 工具交互配置 | 5176-5306 | 探测 MCP server 的工具清单,勾选,写 `tools.include` |
| 非交互 enable/disable/list | 5312-5452 | `hermes tools enable|disable|list` 的后端 |

---

## 1. 机制一:模型选择器族(imagegen / videogen / stt)

### 1.1 解决什么问题

选完"用哪家 provider"之后,还剩"用哪个模型"。这一层的难点不是逻辑,是**目录从哪来**:
in-tree 的 FAL 目录在 `tools/image_generation_tool.py` 里,插件的目录在插件对象上。
这一段用两套并行的取目录方式解决。

### 1.2 怎么实现:in-tree 后端走注册表

`IMAGEGEN_BACKENDS` 是一个"后端 → 目录来源"的小注册表,今天只有 FAL 一家。`hermes_cli/tools_config.py:3670 @ 863e313`

```python
IMAGEGEN_BACKENDS = {
    "fal": {
        "display": "FAL.ai",
        "config_key": "image_gen",
        "catalog_fn": _fal_model_catalog,
    },
}
```

目录函数是**惰性 import**,避免 `hermes tools` 启动时就把整个图像工具模块拉进来。`hermes_cli/tools_config.py:3664 @ 863e313`

```python
def _fal_model_catalog():
    """Lazy-load the FAL model catalog from the tool module."""
    from tools.image_generation_tool import FAL_MODELS, DEFAULT_MODEL
    return FAL_MODELS, DEFAULT_MODEL
```

选择器本体:取目录 → 修复被手改坏的 config 段 → 把"当前模型"顶到第 0 位 → 算列宽 → 打表 → 写回。
`hermes_cli/tools_config.py:3700 @ 863e313`

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
```

"当前模型顶到第 0 位"是**光标默认落点**的设计:`_prompt_choice` 的 `default=0`,配合 curses 的
"取消 = 返回 default",等价于"取消 = 保持现状"。`hermes_cli/tools_config.py:3713 @ 863e313`

```python
    model_ids = list(catalog.keys())
    # Put current model at the top so the cursor lands on it by default.
    ordered = [current_model] + [m for m in model_ids if m != current_model]
```

这条"取消 = 保持现状"的语义来自 `_prompt_choice` 把 `cancel_returns` 钉死成 `default`。
`hermes_cli/tools_config.py:2671 @ 863e313`

```python
def _prompt_choice(question: str, choices: list, default: int = 0) -> int:
    """Single-select menu (arrow keys). Delegates to curses_radiolist."""
    from hermes_cli.curses_ui import curses_radiolist
    return curses_radiolist(question, choices, selected=default, cancel_returns=default)
```

而 curses 层在 **stdin 不是 TTY 时直接返回 cancel_value**,不进事件循环。`hermes_cli/curses_ui.py:501 @ 863e313`

```python
    if not sys.stdin.isatty():
        return cancel_value
```

→ 所以 `_configure_imagegen_model` 的 docstring 说"stdin 非 TTY 时安全"是**成立**的:非 TTY ⇒ 返回 0 ⇒ 选中当前模型 ⇒ 等于没改。
`hermes_cli/tools_config.py:3690 @ 863e313`

```python
    """Prompt the user to pick a model for the given imagegen backend.
```

写回只写一个键:`<config_key>.model`。`hermes_cli/tools_config.py:3746 @ 863e313`

```python
    chosen = ordered[idx]
    cur_cfg["model"] = chosen
    _print_success(f"  Model set to: {chosen}")
```

### 1.3 怎么实现:插件后端走注册表 + 鸭子类型目录

插件目录被**塑形成 FAL 目录的样子**(`{model_id: {...}}`),这样选择器代码原样复用。
`hermes_cli/tools_config.py:3751 @ 863e313`

```python
def _plugin_image_gen_catalog(plugin_name: str):
    """Return ``(catalog_dict, default_model_id)`` for a plugin provider.
```

整段用两层 `try/except Exception: return {}, None` 把插件的任何异常吞掉,退化成"没有目录 ⇒ 不问模型"。
`hermes_cli/tools_config.py:3759 @ 863e313`

```python
    try:
        from agent.image_gen_registry import get_provider
        from hermes_cli.plugins import _ensure_plugins_discovered

        _ensure_plugins_discovered()
        provider = get_provider(plugin_name)
    except Exception:
        return {}, None
    if provider is None:
        return {}, None
    try:
        models = provider.list_models() or []
        default = provider.default_model()
    except Exception:
        return {}, None
    catalog = {m["id"]: m for m in models if isinstance(m, dict) and "id" in m}
    return catalog, default
```

video 版是逐字镜像,只换了 registry 模块。`hermes_cli/tools_config.py:3893 @ 863e313`

```python
def _plugin_video_gen_catalog(plugin_name: str):
```

### 1.4 STT 模型选择器:静态目录 + 一个历史键名例外

STT 没有 registry,直接硬编码一张按 provider 分的目录表,注释声明它与 dashboard、桌面端三处保持同步。
`hermes_cli/tools_config.py:3983 @ 863e313`

```python
STT_MODEL_CATALOG = {
    "local": ["base", "tiny", "small", "medium", "large-v3"],
    "groq": ["whisper-large-v3-turbo", "whisper-large-v3", "distil-whisper-large-v3-en"],
    "openai": ["whisper-1", "gpt-4o-mini-transcribe", "gpt-4o-transcribe", "gpt-transcribe"],
    "elevenlabs": ["scribe_v2", "scribe_v1"],
}
```

ElevenLabs 用 `model_id` 而不是 `model`,靠一张一元映射表兜住。`hermes_cli/tools_config.py:3991 @ 863e313`

```python
_STT_MODEL_CONFIG_KEY = {"elevenlabs": "model_id"}
```

"目录里没有这个 provider ⇒ 静默不问"是**显式设计**,docstring 点名了 xai / deepinfra。
`hermes_cli/tools_config.py:4000 @ 863e313`

```python
    catalog = STT_MODEL_CATALOG.get(stt_provider)
    if not catalog:
        return
```

默认光标落在"当前已配的模型",配不上就落 0。`hermes_cli/tools_config.py:4011 @ 863e313`

```python
    model_key = _STT_MODEL_CONFIG_KEY.get(stt_provider, "model")
    current = str(prov_cfg.get(model_key) or "").strip()
    ordered = list(catalog)
    default_idx = ordered.index(current) if current in ordered else 0
    idx = _prompt_choice("  Select STT model:", ordered, default_idx)
    chosen = ordered[idx]
    prov_cfg[model_key] = chosen
```

注意 `"local"` 目录把 `base` 放第 0 位而不是 `tiny`——这是刻意的,因为 `stt.local.model` 的 schema 默认就是 `base`
(实测 `DEFAULT_CONFIG["stt"]["local"] == {'model': 'base', ...}`),而 dashboard 的下拉是按体积排的
`["tiny", "base", ...]`。`hermes_cli/web_server.py:923 @ 863e313`

```python
    "stt.local.model": {
```

### 1.5 xAI Imagine 的存储三选一

唯一一个"provider 特有的额外问题":xAI 生成的媒体是否留存 + 公开 URL 是否过期。同一个函数被
image_gen 与 video_gen 复用,靠 `section_name` 参数区分。`hermes_cli/tools_config.py:3833 @ 863e313`

```python
def _configure_xai_imagine_storage(section_name: str, config: dict) -> None:
```

三条分支写的键完全不同(禁用时只写 `enabled=False`,不清 `public_url` / `expires_after`)。
`hermes_cli/tools_config.py:3861 @ 863e313`

```python
    if idx == 1:
        storage_cfg["enabled"] = False
        _print_success("  xAI stored public URLs disabled")
    elif idx == 2:
        storage_cfg["enabled"] = True
        storage_cfg["public_url"] = True
        storage_cfg["expires_after"] = 2 * 24 * 60 * 60
        _print_success("  xAI stored public URLs enabled for 2 days")
    else:
        storage_cfg["enabled"] = True
        storage_cfg["public_url"] = True
        storage_cfg["expires_after"] = None
```

### 1.6 取舍

- **好处**:目录来源可插拔;"当前项顶到第 0 位 + 取消 = default"让非交互环境天然幂等,不需要额外的 `--yes` 分支。
- **代价**:同一段表格渲染逻辑被抄了三遍(image / plugin-image / plugin-video),其中 video 版把
  `_format_imagegen_model_row` 抄成了内联 f-string 且**多了两个前导空格**,导致 image 选择器的行与表头错位
  (见 §9 缺陷 D-6)。
- **代价**:插件目录完全信任 `default_model()` 的返回值在 `list_models()` 里(见 §9 缺陷 D-1)。

---

## 2. 机制二:provider 落盘的单一真相 `_write_provider_config`

### 2.1 解决什么问题

同一个"用户选了某个 provider"的事实,有两个入口会发生:CLI 交互配置,和桌面 GUI 的
`PUT .../provider` 端点。两边如果各写各的键,就会出现"GUI 改了 CLI 认不出来"。这个函数被抽出来当唯一写入点。
`hermes_cli/tools_config.py:4035 @ 863e313`

```python
def _write_provider_config(provider: dict, config: dict, *, managed_feature) -> None:
    """Persist the provider/backend config keys for a selected provider.

    This is the pure, non-interactive core of :func:`_configure_provider` —
    it writes ``tts.provider`` / ``browser.cloud_provider`` / ``web.backend``
    and the ``use_gateway`` flags based on the provider's markers, but does
    NOT prompt for env vars, run post-setup hooks, gate on Nous auth, or run
    interactive model pickers. Both the CLI configurator and the desktop GUI
    ``PUT .../provider`` endpoint call through here so there is one code path.
    """
```

### 2.2 怎么实现:provider 行上的"标记字段"决定写哪个键

provider 行(来自 `TOOL_CATEGORIES` 或插件注入)携带 `tts_provider` / `stt_provider` /
`browser_provider` / `web_backend` 这类标记;函数按标记逐个写。`hermes_cli/tools_config.py:4046 @ 863e313`

```python
    if provider.get("tts_provider"):
        tts_cfg = config.setdefault("tts", {})
        tts_cfg["provider"] = provider["tts_provider"]
        tts_cfg["use_gateway"] = bool(managed_feature)
```

browser 用 `in` 而不是 `.get()` 判断,因为 `browser_provider: "local"` 也要算"选中了 local"而不是"没标记"。
`hermes_cli/tools_config.py:4057 @ 863e313`

```python
    # Set browser cloud provider in config if applicable
    if "browser_provider" in provider:
        bp = provider["browser_provider"]
        browser_cfg = config.setdefault("browser", {})
        if bp:
            browser_cfg["cloud_provider"] = bp
        browser_cfg["use_gateway"] = bool(managed_feature)
```

### 2.3 `use_gateway` 的两条对称写法

`use_gateway` 是"这个能力是否走 Nous Tool Gateway(Nous 托管、按订阅计费的工具后端)"的开关。
有专属配置段的类目(web/tts/stt/browser)在上面已顺手写了;没有专属段的(image_gen / video_gen)走通用分支;
选了非托管 provider 则**反向清掉**旧的 `use_gateway`。`hermes_cli/tools_config.py:4071 @ 863e313`

```python
    # For tools without a specific config key (e.g. image_gen), still
    # track use_gateway so the runtime knows the user's intent.
    if managed_feature and managed_feature not in {"web", "tts", "stt", "browser"}:
        config.setdefault(managed_feature, {})["use_gateway"] = True
    elif not managed_feature:
        # User picked a non-gateway provider — find which category this
        # belongs to and clear use_gateway if it was previously set.
        for cat_key, cat in TOOL_CATEGORIES.items():
            if provider in cat.get("providers", []):
                section = config.get(cat_key)
                if isinstance(section, dict) and section.get("use_gateway"):
                    section["use_gateway"] = False
                break
```

注意这里的 `provider in cat.get("providers", [])` 是 **dict 值相等**匹配,不是 identity;而**插件注入的
provider 行根本不在 `TOOL_CATEGORIES[...]["providers"]` 里**(它们由 `_visible_providers` 事后 extend 进来,
`hermes_cli/tools_config.py:3135 @ 863e313`)

```python
    # Inject plugin-registered image_gen backends (OpenAI today, more
```

所以这个 `elif` 分支对插件行是空转。实际不出问题,是因为插件行要么带 `web_backend`/`tts_provider` 之类标记
(上面已写 `use_gateway=False`),要么由 `_select_plugin_image_gen_provider` / `apply_provider_selection` 显式补写。

### 2.4 GUI 侧的非交互入口

`apply_provider_selection` 是给桌面 GUI 用的:按名字在**同一份可见 provider 列表**里找行,然后只写配置,
不问 key、不跑安装钩子、不做 Portal 登录。`hermes_cli/tools_config.py:4086 @ 863e313`

```python
def apply_provider_selection(ts_key: str, provider_name: str, config: dict) -> None:
```

它用 `force_fresh=True` 拿可见列表,保证 GUI 的选项与 CLI 的选项同源。`hermes_cli/tools_config.py:4100 @ 863e313`

```python
    cat = TOOL_CATEGORIES.get(ts_key)
    if cat is None:
        raise KeyError(f"Toolset has no configurable category: {ts_key}")

    providers = _visible_providers(cat, config, force_fresh=True)
    provider = next((p for p in providers if p.get("name") == provider_name), None)
    if provider is None:
        raise KeyError(f"Unknown provider {provider_name!r} for toolset {ts_key!r}")

    managed_feature = provider.get("managed_nous_feature")
    _write_provider_config(provider, config, managed_feature=managed_feature)
```

插件 image/video 行在这里补写 `provider` + `use_gateway`(不跑模型选择器,GUI 有自己的流程)。
`hermes_cli/tools_config.py:4116 @ 863e313`

```python
    plugin_name = provider.get("image_gen_plugin_name")
    if plugin_name:
        img_cfg = config.setdefault("image_gen", {})
        if not isinstance(img_cfg, dict):
            img_cfg = {}
            config["image_gen"] = img_cfg
        img_cfg["provider"] = plugin_name
        img_cfg["use_gateway"] = bool(managed_feature)
```

in-tree FAL 的处理是一条**只在"当前值是别的东西"时才回写 fal**的补丁式逻辑。`hermes_cli/tools_config.py:4134 @ 863e313`

```python
    # In-tree FAL imagegen backend: keep image_gen.provider on the legacy
    # path (mirrors _configure_provider).
    if provider.get("imagegen_backend"):
        img_cfg = config.setdefault("image_gen", {})
        if isinstance(img_cfg, dict) and img_cfg.get("provider") not in {None, "", "fal"}:
            img_cfg["provider"] = "fal"
```

这条与 reconfigure 分支的写法不一致(reconfigure 无条件写 `"fal"` 且顺手写 `use_gateway=False`),见 §9 缺陷 D-4。

---

## 3. 机制三:`_configure_provider` —— 交互配置的主干

### 3.1 执行顺序(这是本函数最重要的事实)

`hermes_cli/tools_config.py:4142 @ 863e313`

```python
def _configure_provider(
```

顺序是:**Nous 门禁 → 打印回显 → 写 provider 键 → (无 env)post-setup + 模型选择器 → (有 env)逐个问 key →
post-setup → 模型选择器**。关键点:**写配置发生在问 key 之前**。`hermes_cli/tools_config.py:4212 @ 863e313`

```python
    # Persist the provider/backend config keys + use_gateway flags. Shared
    # with the GUI provider-select endpoint via apply_provider_selection so
    # there is a single source of truth for these writes.
    _write_provider_config(provider, config, managed_feature=managed_feature)
```

### 3.2 Nous 门禁的两条路

托管网关行(`managed_nous_feature`)走**内联登录**:选中即触发 Portal 登录 + 权益校验,失败就整段 return。
`hermes_cli/tools_config.py:4157 @ 863e313`

```python
    if managed_feature:
        from hermes_cli.nous_subscription import (
            MANAGED_FEATURE_COVERAGE_CATEGORY,
            ensure_nous_portal_access,
        )

        if not ensure_nous_portal_access(
            capability=f"{provider.get('name', 'the Nous Tool Gateway')}",
            coverage_category=MANAGED_FEATURE_COVERAGE_CATEGORY.get(managed_feature),
        ):
            _print_warning(
                "  Not enabled — Nous Portal access is required for this backend."
            )
            return
```

纯"预授权 UX 行"(有 `requires_nous_auth` 但没有托管特性)走旧门禁:必须已登录 **且** `paid_service_access is True`。
`hermes_cli/tools_config.py:4172 @ 863e313`

```python
    # Pure pre-auth UX rows (requires_nous_auth without a managed gateway
    # feature) keep the old gate. Managed rows are handled by the inline
    # login above, so don't double-check them here.
    if provider.get("requires_nous_auth") and not managed_feature:
        features = get_nous_subscription_features(config, force_fresh=force_fresh)
        entitled = bool(
            features.account_info and features.account_info.paid_service_access is True
        )
```

### 3.3 "无 env 变量"的快路径

零 key 的 provider(Edge TTS、Local Browser、cua-driver)直接跑 post-setup 安装钩子,然后分流到各自的模型选择器。
`hermes_cli/tools_config.py:4217 @ 863e313`

```python
    if not env_vars:
        if provider.get("post_setup"):
            _run_post_setup(provider["post_setup"])
        _print_success(f"  {provider['name']} - no configuration needed!")
```

托管行会额外提示计费归属。`hermes_cli/tools_config.py:4221 @ 863e313`

```python
        if managed_feature:
            _print_info("  Requests for this tool will be billed to your Nous subscription.")
```

分流优先级:image 插件 → video 插件 → in-tree imagegen → STT。前两者 `return`,后两者继续往下走。
`hermes_cli/tools_config.py:4235 @ 863e313`

```python
        # Imagegen backends prompt for model selection after backend pick.
        backend = provider.get("imagegen_backend")
        if backend:
            _configure_imagegen_model(backend, config)
```

托管 STT 不问模型,因为网关自己钉死了模型。`hermes_cli/tools_config.py:4245 @ 863e313`

```python
        # STT providers prompt for model selection after provider pick
        # (skipped for managed rows — the gateway pins the model).
        if provider.get("stt_provider") and not managed_feature:
            _configure_stt_model(provider["stt_provider"], config)
        return
```

### 3.4 "有 env 变量"的慢路径 + Portal 软广

BYOK(自带 key)的 provider,如果同类目里还存在一个 Nous 托管兄弟行,就打一行灰字广告;已登录 Nous 的用户不打。
`hermes_cli/tools_config.py:4252 @ 863e313`

```python
    all_configured = True
    # If this BYOK provider lives in a category that ALSO has a
    # Nous-managed sibling, show a single dim hint so users know
    # they can avoid the key entirely via a Portal subscription.
    # Suppressed when the user is already authed to Nous.
    _show_portal_hint = False
    if env_vars and not managed_feature and not provider.get("requires_nous_auth"):
```

env 提示循环:**已存在的 key 不再问**(这是"新开工具"流,不是 reconfigure 流)。`hermes_cli/tools_config.py:4280 @ 863e313`

```python
    for var in env_vars:
        existing = get_env_value(var["key"])
        if existing:
            _print_success(f"  {var['key']}: already configured")
            # Don't ask to update - this is a new enable flow.
            # Reconfigure is handled separately.
```

有 `default` 的字段按明文问(不是秘密,例如 base URL),没有的按密码问。`hermes_cli/tools_config.py:4291 @ 863e313`

```python
            default_val = var.get("default", "")
            if default_val:
                value = _prompt(f"    {var.get('prompt', var['key'])}", default_val)
            else:
                value = _prompt(f"    {var.get('prompt', var['key'])}", password=True)

            if value:
                save_env_value(var["key"], value)
                _print_success("    Saved")
            else:
                _print_warning("    Skipped")
                all_configured = False
```

`_prompt` 的语义:回车返回 default,Ctrl-C / EOF 返回空串。`hermes_cli/cli_output.py:43 @ 863e313`

```python
def prompt(
```

**post-setup 只在全部 key 都拿到时才跑**——这是把"安装重物"绑到"配置完整"上的一个闸门。
`hermes_cli/tools_config.py:4304 @ 863e313`

```python
    # Run post-setup hooks if needed
    if provider.get("post_setup") and all_configured:
        _run_post_setup(provider["post_setup"])
```

### 3.5 取舍

- **好处**:一条 `_write_provider_config` 让 CLI / GUI / 非交互三面同源;门禁分两路避免对托管行重复校验。
- **代价(重要)**:配置键先落盘、key 后问。用户在 key 提示处直接回车跳过,`web.backend: firecrawl`
  之类已经写进 config 了,而 key 没有 → 运行期该能力直接坏掉,且下次 `hermes tools` 因为
  `_toolset_needs_configuration_prompt("web")` 只看 `"backend" in web_cfg`
  (`hermes_cli/tools_config.py:3390 @ 863e313`)

  ```python
      if ts_key == "web":
  ```

  而认为"已配好",**不会再提示**。要修必须走 reconfigure 菜单。这是本段最容易踩的坑。
- **代价**:`all_configured=False` 时函数**静默走完**——不打印任何"配置不完整"的结论,也不回滚已写的键。

---

## 4. 机制四:vision 的"另类"配置面

### 4.1 解决什么问题

vision(看图)是一个 **auxiliary task(辅助任务:不由主模型跑、单独选 provider+model 的子任务)**,
它的 provider/model 来自 `auxiliary.vision.*`,而不是某个 `TOOL_CATEGORIES` 条目。如果按通用 env 流走,
用户会被硬塞一个 `OPENROUTER_API_KEY`。作者的解法是给 vision 一条专属分支。
`hermes_cli/tools_config.py:4330 @ 863e313`

```python
def _configure_vision_backend() -> None:
    """Interactive vision-backend configuration.

    Vision is an auxiliary task whose provider/model are resolved from
    ``auxiliary.vision.{provider,model,base_url}`` in config.yaml (see
    ``agent/auxiliary_client.resolve_vision_provider_client``). Rather than
    forcing the user onto OpenRouter, let them pick any authenticated
    provider + model — the same surface as ``hermes model`` — or point at a
    custom OpenAI-compatible endpoint. "Auto" leaves the config keys empty so
    the resolver uses the main model / aggregator fallback chain.
    """
```

`TOOLSET_ENV_REQUIREMENTS` 里那条 vision 记录只是"注册成可配置 toolset"的占位,注释自己说清了永不被读。
`hermes_cli/tools_config.py:740 @ 863e313`

```python
# `vision` is listed here only so it registers as a *configurable* toolset
```

### 4.2 四选一

`hermes_cli/tools_config.py:4348 @ 863e313`

```python
    choices = [
        "Auto — use your main model / aggregator fallback (recommended)",
        "Pick a provider and model",
        "Custom OpenAI-compatible endpoint — base URL, API key, model",
        "Skip",
    ]
```

**Auto 是"删键"而不是"写 auto"**——把五个覆盖键全 pop 掉,让 resolver 走自己的回退链。
`hermes_cli/tools_config.py:4366 @ 863e313`

```python
    if idx == 0:
        # Auto: clear any pinned override so the resolver auto-detects.
        for key in ("provider", "model", "base_url", "api_key", "api_mode"):
            vision_cfg.pop(key, None)
        save_config(config)
```

自定义端点分支:**key 存 .env,base_url/model 存 config.yaml**,并且必须把 `provider` 钉成 `"custom"`,
否则 resolver 会忽略 base_url。`hermes_cli/tools_config.py:4378 @ 863e313`

```python
    if idx == 2:
        base_url = _prompt("    Base URL (blank for OpenAI)").strip() or "https://api.openai.com/v1"
        is_native_openai = base_url_hostname(base_url) == "api.openai.com"
        key_label = "    OPENAI_API_KEY" if is_native_openai else "    API key"
        api_key = _prompt(key_label, password=True)
```

`hermes_cli/tools_config.py:4390 @ 863e313`

```python
        save_env_value("OPENAI_API_KEY", api_key.strip())
        # Only base_url + model go to config.yaml; the key is the secret.
        # Pin provider="custom" so the resolver routes through this endpoint —
        # leaving it at the "auto" default would make _resolve_task_provider_model
        # ignore the base_url (it only honors base_url when paired with an
        # api_key in config or a non-auto provider).
        vision_cfg["provider"] = "custom"
        vision_cfg["base_url"] = base_url
```

`api_mode` 确实是 resolver 会读的键(不是笔误),读点在:`agent/auxiliary_client.py:7365 @ 863e313`

```python
        cfg_api_mode = str(task_config.get("api_mode", "")).strip() or None
```

### 4.3 provider+model 选择器复用 `hermes model` 的行源

`hermes_cli/tools_config.py:4410 @ 863e313`

```python
def _configure_vision_provider_model(config: dict, vision_cfg: dict) -> None:
    """Provider + model picker for vision, mirroring the ``/model`` surface.
```

行来自共享底座 `build_aux_picker_rows`,所以用户自己在 `providers:` / `custom_providers:` 里配的端点也会出现。
`hermes_cli/tools_config.py:4433 @ 863e313`

```python
    try:
        providers = build_aux_picker_rows(
            current_provider=current_provider,
            current_model=current_model,
            current_base_url=current_base_url,
            max_models=40,
        )
```

选完 provider 后**顺手清掉旧的自定义端点覆盖**(避免 base_url 与 provider 打架)。
`hermes_cli/tools_config.py:4484 @ 863e313`

```python
    vision_cfg["provider"] = slug
    vision_cfg["model"] = model
    # A provider selection supersedes any prior custom endpoint override.
    vision_cfg.pop("base_url", None)
    vision_cfg.pop("api_key", None)
    save_config(config)
```

注意这里 pop 了 `base_url` / `api_key` 但**没 pop `api_mode`**;§4.2 的自定义端点分支同样不清 `api_mode`。
一条手改进 config 的 `auxiliary.vision.api_mode: anthropic_messages` 会跨越两次重配存活下来。

### 4.4 取舍与后果

- **好处**:vision 不被绑死在 OpenRouter;"Auto = 删键"让默认值继续跟随全局回退链演进。
- **代价(重大)**:`_configure_vision_backend` **自己 `load_config()` 又自己 `save_config()`**,
  完全不接受调用者传进来的 config dict。`hermes_cli/tools_config.py:4356 @ 863e313`

  ```python
      config = load_config()
  ```

  而它的调用者(`tools_command` / `_reconfigure_tool`)持有一份**更早加载的**config,并会在之后再存一次。
  `save_config` 默认 `merge_existing=False`,是整文档替换。`hermes_cli/config.py:3510 @ 863e313`

  ```python
      merge_existing: bool = False,
  ```

  → vision 的设置被后一次保存**覆盖回默认值**。见 §9 缺陷 D-2(已实测复现)。
- **代价**:自定义端点无论域名是什么都把 key 存进 `OPENAI_API_KEY`,会污染其它读该变量的路径。

---

## 5. 机制五:reconfigure 面(4524-4844)

### 5.1 解决什么问题

"已经配过的工具想换 provider / 换 key"。它和 enable 流最大的区别是**已有 key 也要问**(回车保留)。

入口先算"哪些工具值得出现在列表里":有类目或有 env 需求,且(已有 key 或在任一平台上开着)。
`hermes_cli/tools_config.py:4531 @ 863e313`

```python
    configurable = []
    for ts_key, ts_label, _ in _get_effective_configurable_toolsets():
        cat = TOOL_CATEGORIES.get(ts_key)
        reqs = TOOLSET_ENV_REQUIREMENTS.get(ts_key)
        if cat or reqs:
            if (
                _toolset_has_keys(ts_key, config, force_fresh=force_fresh)
                or _toolset_enabled_for_reconfigure(ts_key, config)
            ):
                configurable.append((ts_key, ts_label))
```

"开着但没配完"也要能进来,理由写在 `_toolset_enabled_for_reconfigure` 的 docstring 里——否则用户只能靠
"关掉再开"来补配置。`hermes_cli/tools_config.py:4570 @ 863e313`

```python
def _toolset_enabled_for_reconfigure(ts_key: str, config: dict) -> bool:
    """Return True if a configurable toolset is enabled anywhere.

    Reconfigure must include enabled-but-unconfigured categories so users can
    finish provider/API-key setup without disabling and re-enabling the toolset.
    """
```

默认光标落在最后一项 "Cancel",这是"破坏性菜单默认不动"的取向。`hermes_cli/tools_config.py:4546 @ 863e313`

```python
    choices = [label for _, label in configurable]
    choices.append("Cancel")

    idx = _prompt_choice("  Which tool would you like to reconfigure?", choices, len(choices) - 1)
```

### 5.2 与 enable 流的差异点(逐条)

**(a) 类目选择器没有 "Skip" 行。** 对比 `_configure_tool_category` 会追加
`"Skip — keep defaults / configure later"`(`hermes_cli/tools_config.py:3531 @ 863e313`)

```python
        provider_choices.append("Skip — keep defaults / configure later")
```

reconfig 版没有,直接就是 provider 列表 → 取消 = 选中"当前活跃的那个"。`hermes_cli/tools_config.py:4641 @ 863e313`

```python
        default_idx = _detect_active_provider_index(
            providers,
            config,
            force_fresh=force_fresh,
        )

        provider_idx = _prompt_choice("  Select provider:", provider_choices, default_idx)
```

**(b) 打印回显的时候顺便落盘。** enable 流的回显与落盘是分开的(回显在 4190-4210,落盘在 4215);
reconfig 流把两件事写在一起,并且 browser 的 `local` 分支**显式写 `cloud_provider="local"`**
(enable 流靠 `if bp:` 也会写,但代码形状不同)。`hermes_cli/tools_config.py:4711 @ 863e313`

```python
    if "browser_provider" in provider:
        bp = provider["browser_provider"]
        browser_cfg = config.setdefault("browser", {})
        if bp == "local":
            browser_cfg["cloud_provider"] = "local"
            _print_success("  Browser set to local mode")
        elif bp:
            browser_cfg["cloud_provider"] = bp
            _print_success(f"  Browser cloud provider set to: {bp}")
        browser_cfg["use_gateway"] = bool(managed_feature)
```

**(c) 通用 `use_gateway` 分支多了一层非 dict 修复。** `hermes_cli/tools_config.py:4729 @ 863e313`

```python
    if managed_feature and managed_feature not in {"web", "tts", "stt", "browser"}:
        section = config.setdefault(managed_feature, {})
        if not isinstance(section, dict):
            section = {}
            config[managed_feature] = section
        section["use_gateway"] = True
```

**(d) FAL 回写策略相反。** reconfig 无条件写 `provider="fal"` 且写 `use_gateway=False`。
`hermes_cli/tools_config.py:4762 @ 863e313`

```python
            if backend == "fal":
                img_cfg = config.setdefault("image_gen", {})
                if isinstance(img_cfg, dict):
                    img_cfg["provider"] = "fal"
                    img_cfg["use_gateway"] = False
```

**(e) env 循环:已有 key 会回显前 8 位,并且总是问一遍。** `hermes_cli/tools_config.py:4772 @ 863e313`

```python
    for var in env_vars:
        existing = get_env_value(var["key"])
        if existing:
            _print_info(f"  {var['key']}: configured ({existing[:8]}...)")
        url = var.get("url", "")
        if url:
            _print_info(f"  Get yours at: {url}")
        default_val = var.get("default", "")
        value = _prompt(f"    {var.get('prompt', var['key'])} (Enter to keep current)", password=not default_val)
        if value and value.strip():
            save_env_value(var["key"], value.strip())
            _print_success("    Updated")
        else:
            _print_info("    Kept current")
```

注意 `_prompt` **没传 default**,所以"回车 = 空串 = 保留现值",而 enable 流是"回车 = 采用 default 值"。
两个流对同一个带 default 的字段行为不同。

**(f) post-setup 无条件跑**(enable 流要 `all_configured`)。`hermes_cli/tools_config.py:4787 @ 863e313`

```python
    if provider.get("post_setup"):
        _run_post_setup(provider["post_setup"])
```

**(g) 简单需求分支同样把 vision 特判掉,理由写在注释里。** `hermes_cli/tools_config.py:4818 @ 863e313`

```python
    if ts_key == "vision":
        # Vision has its own provider/model picker (any provider, like
        # `hermes model`). Run it directly so reconfigure doesn't fall back to
        # the generic single-key prompt (which would re-ask for OPENROUTER_API_KEY).
        _configure_vision_backend()
        return
```

与 enable 流的 `_configure_simple_requirements` 不同:后者会先看"已经有 key 了就别问"。
`hermes_cli/tools_config.py:4495 @ 863e313`

```python
    if ts_key == "vision":
        if _toolset_has_keys("vision"):
            return
        _configure_vision_backend()
        return
```

### 5.3 取舍

- **好处**:两条流分开,语义清晰(enable = 只补缺,reconfig = 全都问一遍)。
- **代价**:两条流是**手工镜像**的,已经出现 §5.2 的 (b)(d)(e)(f) 四处行为分叉;任何一处改动都要记得改两边。
  这是这一段最大的可维护性负债。
- **代价**:回显 key 前 8 位会把秘密的前缀打到终端/日志里(4775、4836 两处)。

---

## 6. 机制六:`tools_command` —— CLI 主入口(4849-5170)

### 6.1 三种模式

`hermes_cli/tools_config.py:4849 @ 863e313`

```python
def tools_command(args=None, first_install: bool = False, config: dict = None):
```

docstring 说明了 `config` 参数的存在理由:setup 向导要让 `platform_toolsets` 写进**它自己的 dict**,
以便活到向导最后那次 `save_config()`。`hermes_cli/tools_config.py:4856 @ 863e313`

```python
        config: Optional config dict to use.  When called from the setup
            wizard, the wizard passes its own dict so that platform_toolsets
            are written into it and survive the wizard's final save_config().
```

**模式 1 — `--summary`**:纯打印,提前 return。`hermes_cli/tools_config.py:4867 @ 863e313`

```python
    if getattr(args, "summary", False):
        total = len(_get_effective_configurable_toolsets())
```

**模式 2 — 首装线性流**:不给平台菜单,逐平台走一遍勾选 + 配置 + 保存。
`hermes_cli/tools_config.py:4892 @ 863e313`

```python
    if first_install:
        for pkey in enabled_platforms:
            pinfo = PLATFORMS[pkey]
            current_enabled = _get_platform_tools(config, pkey, include_default_mcp_servers=False)

            # Uncheck toolsets that should be off by default
            checklist_preselected = current_enabled - _DEFAULT_OFF_TOOLSETS

            # Show checklist
            new_enabled = _prompt_toolset_checklist(pinfo["label"], checklist_preselected, pkey)
```

注意首装流**把 `pkey` 传给了 checklist**(第三个位置参数)。这是老用户流没做的事(见 §9 缺陷 D-3)。

首装流会先让 Nous 订阅把它能托管的能力自动配好,再决定还剩哪些要手工配。
`hermes_cli/tools_config.py:4921 @ 863e313`

```python
            auto_configured = apply_nous_managed_defaults(
                config,
                enabled_toolsets=new_enabled,
                force_fresh=True,
            )
```

`hermes_cli/tools_config.py:4934 @ 863e313`

```python
            to_configure = [
                ts_key for ts_key in sorted(new_enabled)
                if (TOOL_CATEGORIES.get(ts_key) or TOOLSET_ENV_REQUIREMENTS.get(ts_key))
                and ts_key not in auto_configured
            ]
```

**模式 3 — 老用户菜单循环**。菜单项是动态拼的,索引偏移量用四个变量硬算。
`hermes_cli/tools_config.py:4970 @ 863e313`

```python
    if len(platform_keys) > 1:
        platform_choices.append("Configure all platforms (global)")
    platform_choices.append("Reconfigure an existing tool's provider or API key")

    # Show MCP option if any MCP servers are configured
    _has_mcp = bool(config.get("mcp_servers"))
    if _has_mcp:
        platform_choices.append("Configure MCP server tools")

    platform_choices.append("Done")

    # Index offsets for the extra options after per-platform entries
    _global_idx = len(platform_keys) if len(platform_keys) > 1 else -1
    _reconfig_idx = len(platform_keys) + (1 if len(platform_keys) > 1 else 0)
    _mcp_idx = (_reconfig_idx + 1) if _has_mcp else -1
    _done_idx = _reconfig_idx + (2 if _has_mcp else 1)
```

`-1` 是"该项不存在"的哨兵,靠 `_prompt_choice` 永不返回负数来保证不会误命中。

### 6.2 "选中但没配完也要开配置"这条规则

这是这段的核心业务规则:**勾选没变 ≠ 不用配**。Web Search 已经勾着但 `web.backend` 缺失,也得进配置。
`hermes_cli/tools_config.py:5098 @ 863e313`

```python
        # Selected toolsets still missing provider/API-key setup must open
        # configuration even when the checklist selection itself didn't
        # change (e.g. Web Search already enabled but web.backend missing).
        # Mirrors the "Configure all platforms (global)" flow above.
        selected_to_configure = [
            ts_key for ts_key in sorted(new_enabled)
            if (TOOL_CATEGORIES.get(ts_key) or TOOLSET_ENV_REQUIREMENTS.get(ts_key))
            and _toolset_needs_configuration_prompt(
                ts_key,
                config,
                force_fresh=True,
            )
        ]
```

然后"新加的但没在上面处理过的"再补一轮,靠集合差避免重复问。`hermes_cli/tools_config.py:5142 @ 863e313`

```python
            # Configure newly enabled toolsets that need API keys, skipping
            # any already handled by the selected-tool pass above.
            for ts_key in sorted(added - selected_to_configure_set):
```

### 6.3 打印的 diff 被"清单宇宙"限缩

`_get_platform_tools` 在读的时候会解析出用户从没见过的条目(`kanban`、平台复合 toolset、MCP server 名),
直接做差集会打出莫名其妙的 `- kanban`。解法是把 diff 与 `_checklist_toolset_keys(platform)` 取交。
`hermes_cli/tools_config.py:5126 @ 863e313`

```python
            # Scope the printed diff to the checklist's universe (see
            # _checklist_toolset_keys) so non-configurable toolsets like
            # ``kanban`` aren't reported as added/removed.
            _diff_universe = _checklist_toolset_keys(pkey)
            added = (new_enabled - current_enabled) & _diff_universe
            removed = (current_enabled - new_enabled) & _diff_universe
```

`_checklist_toolset_keys` 的定义与 checklist 渲染逻辑严格对齐。`hermes_cli/tools_config.py:281 @ 863e313`

```python
def _checklist_toolset_keys(platform: str) -> Set[str]:
```

**但是**:第 5125 行判断"要不要保存"的那个 `!=` **没有**被同样限缩:

`hermes_cli/tools_config.py:5125 @ 863e313`

```python
        if new_enabled != current_enabled or selected_to_configure:
```

见 §9 缺陷 D-5。

### 6.4 收尾

`hermes_cli/tools_config.py:5166 @ 863e313`

```python
    print()
    from hermes_constants import display_hermes_home
    print(color(f"  Tool configuration saved to {display_hermes_home()}/config.yaml", Colors.DIM))
    print(color("  Changes take effect on next 'hermes' or gateway restart.", Colors.DIM))
```

"下次启动才生效"是这个配置面的**根本取舍**:它只改 config.yaml,不热更新任何运行中的进程。

---

## 7. 机制七:MCP 工具交互配置(5176-5306)

### 7.1 解决什么问题

一个 MCP server(Model Context Protocol:外挂工具服务器)可能暴露几十个工具,全塞进 schema 会烧 context。
这个流程去**实连**每台 server 拿工具清单,让用户勾选,写回过滤器。
`hermes_cli/tools_config.py:5176 @ 863e313`

```python
def _configure_mcp_tools_interactive(config: dict):
    """Probe MCP servers for available tools and let user toggle them on/off.

    Connects to each configured MCP server, discovers tools, then shows
    a per-server curses checklist.  Writes changes back as ``tools.exclude``
    entries in config.yaml.
    """
```

**这段 docstring 与代码矛盾**(实际写 `include`),见 §8 冲突 C-1。

### 7.2 预选状态的三态推导

`hermes_cli/tools_config.py:5246 @ 863e313`

```python
        # Determine which tools are currently enabled
        pre_selected: Set[int] = set()
        tool_names = [t[0] for t in tools]
        for i, tool_name in enumerate(tool_names):
            if include_list:
                # Include mode: only included tools are selected
                if tool_name in include_list:
                    pre_selected.add(i)
            elif exclude_list:
                # Exclude mode: everything except excluded
                if tool_name not in exclude_list:
                    pre_selected.add(i)
            else:
                # No filter: all enabled
                pre_selected.add(i)
```

这与运行期的过滤优先级一致(include 压 exclude)。`tools/mcp_tool.py:5837 @ 863e313`

```python
    #   include takes precedence over exclude
```

`tools/mcp_tool.py:5847 @ 863e313`

```python
    def _should_register(tool_name: str) -> bool:
```

### 7.3 落盘:统一到 include,并且"全选 = 无过滤器"

`hermes_cli/tools_config.py:5273 @ 863e313`

```python
        # Compute new include list (the chosen tools). We standardize on
        # tools.include across the codebase (catalog installs, hermes mcp
        # configure, and this UI) so a server\'s on-disk config shape doesn\'t
        # depend on which UI the user touched last.
        chosen_names = [tool_names[i] for i in sorted(chosen)]
```

`hermes_cli/tools_config.py:5283 @ 863e313`

```python
        if len(chosen) == len(tools):
            # All tools enabled — clear filters (cleanest config shape; the
            # server\'s native tool set is the active set, and any tools the
            # server adds later are auto-enabled).
            tools_cfg.pop("exclude", None)
            tools_cfg.pop("include", None)
        else:
            tools_cfg["include"] = chosen_names
            # Drop any legacy exclude block — we\'re include-mode now.
            tools_cfg.pop("exclude", None)
```

"全选就删过滤器"是有语义后果的取舍:server 以后新增的工具会**自动开启**;而 include 模式下新增工具默认关闭。

只有真的改了才存盘。`hermes_cli/tools_config.py:5301 @ 863e313`

```python
    if any_changes:
        save_config(config)
```

### 7.4 enabled 判定与别处不一致

这里用了一个字面量集合而不是模块里现成的 `_parse_enabled_flag`。`hermes_cli/tools_config.py:5191 @ 863e313`

```python
    enabled_names = [
        k for k, v in mcp_servers.items()
        if v.get("enabled", True) not in {False, "false", "0", "no", "off"}
    ]
```

而真正去探测的 `probe_mcp_server_tools` 用的是自己那套解析。`tools/mcp_tool.py:6635 @ 863e313`

```python
    enabled = {
```

`hermes_cli/tools_config.py:2106 @ 863e313`

```python
def _parse_enabled_flag(value, default: bool = True) -> bool:
```

后果:`enabled: "False"`(大写 F 字符串)在这里算"启用",在 `_parse_enabled_flag` 里算"禁用"。
本函数只用 `enabled_names` 做**提示文案与失败清单**,所以后果限于"报告了一台其实没探的 server 连不上"。

另外 `probe_mcp_server_tools()` 不接收 config 参数,它自己重新读盘;所以**同一次会话里刚改还没存的
mcp_servers 变更不会反映到探测结果**。

---

## 8. 机制八:非交互 enable / disable / list(5312-5452)

### 8.1 分派

`hermes_cli/tools_config.py:5389 @ 863e313`

```python
def tools_disable_enable_command(args):
    """Enable, disable, or list tools for a platform.

    Built-in toolsets use plain names (e.g. ``web``, ``memory``).
    MCP tools use ``server:tool`` notation (e.g. ``github:create_issue``).
    """
```

用 `":"` 是否出现来区分内建 toolset 与 MCP 工具。`hermes_cli/tools_config.py:5408 @ 863e313`

```python
    targets: List[str] = args.names
    toolset_targets = [t for t in targets if ":" not in t]
    mcp_targets = [t for t in targets if ":" in t]
```

两级校验:未知名字 + 平台受限名字,各自打错、各自剔除,剩下的照做(**部分成功**语义)。
`hermes_cli/tools_config.py:5412 @ 863e313`

```python
    valid_toolsets = {ts_key for ts_key, _, _ in CONFIGURABLE_TOOLSETS} | _get_plugin_toolset_keys()
    unknown_toolsets = [t for t in toolset_targets if t not in valid_toolsets]
```

`hermes_cli/tools_config.py:5419 @ 863e313`

```python
    # Reject platform-scoped toolsets on platforms that don't allow them.
    restricted_targets = [
        t for t in toolset_targets
        if not _toolset_allowed_for_platform(t, platform)
    ]
```

平台限制表本身很小。`hermes_cli/tools_config.py:216 @ 863e313`

```python
_TOOLSET_PLATFORM_RESTRICTIONS: Dict[str, Set[str]] = {
```

### 8.2 两个 apply 函数

toolset 用集合加减,然后立刻 `_save_platform_tools`(它内部自己会 `save_config`)。
`hermes_cli/tools_config.py:5312 @ 863e313`

```python
def _apply_toolset_change(config: dict, platform: str, toolset_names: List[str], action: str):
    """Add or remove built-in toolsets for a platform."""
    enabled = _get_platform_tools(config, platform, include_default_mcp_servers=False)
    if action == "disable":
        updated = enabled - set(toolset_names)
    else:
        updated = enabled | set(toolset_names)
    _save_platform_tools(config, platform, updated)
```

`hermes_cli/tools_config.py:2521 @ 863e313`

```python
def _save_platform_tools(config: dict, platform: str, enabled_toolset_keys: Set[str]):
```

MCP 用 **exclude 列表**(与交互 UI 的 include 相反)。`hermes_cli/tools_config.py:5330 @ 863e313`

```python
    for target in targets:
        server_name, tool_name = target.split(":", 1)
        if server_name not in mcp_servers:
            failed_servers.add(server_name)
            continue
        tools_cfg = mcp_servers[server_name].setdefault("tools", {})
        exclude = list(tools_cfg.get("exclude") or [])
        if action == "disable":
            if tool_name not in exclude:
                exclude.append(tool_name)
        else:
            exclude = [t for t in exclude if t != tool_name]
        tools_cfg["exclude"] = exclude
```

见 §9 缺陷 D-7。

### 8.3 list 输出

内建与插件 toolset 分两块打,MCP 打过滤器摘要。`hermes_cli/tools_config.py:5347 @ 863e313`

```python
def _print_tools_list(enabled_toolsets: set, mcp_servers: dict, platform: str = "cli"):
```

`hermes_cli/tools_config.py:5374 @ 863e313`

```python
    if mcp_servers:
        print()
        print("MCP servers:")
        for srv_name, srv_cfg in mcp_servers.items():
            tools_cfg = srv_cfg.get("tools") or {}
            exclude = tools_cfg.get("exclude") or []
            include = tools_cfg.get("include") or []
```

结尾的"成功列表"三重过滤。`hermes_cli/tools_config.py:5444 @ 863e313`

```python
    successful = [
        t for t in targets
        if t not in unknown_toolsets
        and t not in restricted_targets
        and (":" not in t or t.split(":")[0] not in failed_servers)
    ]
```

---

## 9. 配置键与环境变量清单(本段专项交付物)

### 9.1 config.yaml 键

| 键 | 默认 | 读/写点(@863e313) | 备注 |
| --- | --- | --- | --- |
| `image_gen.model` | 由 `catalog_fn()` 返回的 `DEFAULT_MODEL`;插件则 `provider.default_model()` | 写 `tools_config.py:3747`、`:3829`;读 `:3709`、`:3793` | fallback 链:`cur_cfg["model"]` → `default_model`;若当前值不在目录里回落 default |
| `image_gen.provider` | 无(缺省即"legacy FAL 路径") | 写 `:3882`、`:4122`、`:4139`、`:4244`、`:4324`、`:4765`、`:4808`;读 `:3560`、`:3576`、`:3625` | `{None, "", "fal"}` 三值等价于 FAL |
| `image_gen.use_gateway` | 无 | 写 `:3883`、`:4074`、`:4123`、`:4766`、`:4809` | `is_truthy_value(..., default=False)` 解析(`:3629`) |
| `image_gen.xai.storage.enabled` | 无 | 写 `:3862`、`:3865`、`:3870` | 三选一 |
| `image_gen.xai.storage.public_url` | 无 | 写 `:3866`、`:3871` | 禁用分支不清此键 |
| `image_gen.xai.storage.expires_after` | 无 | 写 `:3867`(172800)、`:3872`(None) | 秒 |
| `video_gen.model` | `provider.default_model()` | 写 `:3974`;读 `:3932` | 同 image |
| `video_gen.provider` | 无 | 写 `:4027`、`:4131`;读 `:3565`、`:3585` | |
| `video_gen.use_gateway` | 无 | 写 `:4028`、`:4132` | `_select_plugin_video_gen_provider` 的 `use_gateway=` 参数默认 False(`:4021`) |
| `video_gen.xai.storage.*` | 无 | 写 `:4032` → `:3862` 起 | 与 image 同一函数 |
| `tts.provider` | 无 | 写 `:4048`、`:4701`;读 `:3594`、`:3610` | |
| `tts.use_gateway` | 无 | 写 `:4049`、`:4702` | |
| `stt.provider` | `"local"`(读取侧兜底,`:3613`) | 写 `:4054`、`:4707` | `_configure_provider` 只打印不写(`:4197`),真正写在 `_write_provider_config` |
| `stt.use_gateway` | 无 | 写 `:4055`、`:4708` | |
| `stt.<provider>.model` | `stt.local.model` schema 默认 `"base"` | 写 `:4017`;读 `:4012` | provider ∈ {local, groq, openai} |
| `stt.elevenlabs.model_id` | 无 | 写 `:4017`(key 由 `:3991` 映射) | 历史键名例外 |
| `browser.cloud_provider` | 无 | 写 `:4062`、`:4715`、`:4718`;读 `:3602`、`:3616` | `bp` 为空串时不写(`:4061`) |
| `browser.use_gateway` | 无 | 写 `:4063`、`:4720` | |
| `web.backend` | 无 | 写 `:4068`、`:4725`;读 `:3605`、`:3619` | |
| `web.use_gateway` | 无 | 写 `:4069`、`:4726` | |
| `<managed_feature>.use_gateway` | 无 | 写 `:4074`、`:4734` | 通用兜底,`managed_feature ∉ {web,tts,stt,browser}` 时才用 |
| `auxiliary.vision.provider` | schema 默认 `"auto"` | 写 `:4396`(`"custom"`)、`:4484`(provider slug);删 `:4369` | |
| `auxiliary.vision.model` | schema 默认 `""` | 写 `:4399`、`:4485`;删 `:4401`、`:4369` | |
| `auxiliary.vision.base_url` | schema 默认 `""` | 写 `:4397`;删 `:4369`、`:4487` | |
| `auxiliary.vision.api_key` | schema 默认 `""` | 只删不写:`:4369`、`:4488` | key 走 .env |
| `auxiliary.vision.api_mode` | 不在 schema 默认里;resolver 读 `agent/auxiliary_client.py:7365` | 只在 `:4369` 被删 | 自定义端点/provider 分支都不清它 |
| `mcp_servers` | 无 | 读 `:4975`、`:5185`、`:5328` | 存在与否决定菜单是否出现 MCP 项 |
| `mcp_servers.<n>.enabled` | `True` | 读 `:5193` | 与 `_parse_enabled_flag` 判定不一致 |
| `mcp_servers.<n>.tools.include` | 无 | 读 `:5234`;写 `:5290`;删 `:5288` | 交互 UI 的落盘形状 |
| `mcp_servers.<n>.tools.exclude` | 无 | 读 `:5235`;写 `:5342`;删 `:5287`、`:5292` | CLI `disable` 的落盘形状 |
| `platform_toolsets.<platform>` | 无(缺省回落平台复合 toolset,`:2247`) | 写 `:2566`(经 `_save_platform_tools`);读 `:2232` | 本段所有保存最终都过这里 |
| `known_plugin_toolsets.<platform>` | 无 | 写 `:2575` | 段外,但 `tools_command` 每次保存都会写 |
| `known_builtin_toolsets.<platform>` | 无 | 写 `:2584` | 同上 |
| `agent.disabled_toolsets` | 无 | 读写 `:2601-2612` | 保存时会把"本次显式启用"的项从中剔除 |
| `context.engine` | `"compressor"` | 读 `:2444` | 影响 `_get_platform_tools` 是否隐式加 `context_engine` |

`cfg_get(config, "platform_toolsets", platform, default=[])` 是点分读取器。`hermes_cli/config.py:2886 @ 863e313`

```python
def cfg_get(cfg: Optional[Dict[str, Any]], *keys: str, default: Any = None) -> Any:
```

### 9.2 环境变量

| 变量 | 类型 | 读/写点 | 备注 |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | 写 | `tools_config.py:4390 @ 863e313` | vision 自定义端点分支**无论域名**都存这个名字 |
| provider 行的 `env_vars[].key`(动态,如 `VOICE_TOOLS_OPENAI_KEY`、`FAL_KEY`、`BROWSERBASE_API_KEY`…) | 读+写 | 读 `:4281`、`:4632`、`:4773`;写 `:4298`、`:4782` | 键名来自 `TOOL_CATEGORIES`(`:321` 起)与插件 `get_setup_schema()` |
| `OPENROUTER_API_KEY` | 名义读+写 | `TOOLSET_ENV_REQUIREMENTS`(`:748`),消费点 `:4505`、`:4516`、`:4834`、`:4839` | **实际不可达**:vision 在两个函数开头都被特判 return(`:4495`、`:4818`),而这是表里唯一一条 |
| `TELEGRAM_BOT_TOKEN` / `DISCORD_BOT_TOKEN` / `SLACK_BOT_TOKEN` / `WHATSAPP_ENABLED` / `QQ_APP_ID` | 读 | `_get_enabled_platforms`,`hermes_cli/tools_config.py:2074 @ 863e313` | `tools_command:4862` 调用;决定菜单列几个平台 |
| `HERMES_HOME` | 间接 | 经 `load_config` / `save_config` / `save_env_value`,`hermes_cli/config.py:3865 @ 863e313` | 决定 config.yaml 与 .env 的位置 |
| `HERMES_CUA_DRIVER_CMD` | 读 | `hermes_cli/tools_config.py:755 @ 863e313` | 段外,但 `_run_post_setup("cua_driver")` 会走到 |

env 写入统一走 `save_env_value` → `~/.hermes/.env`;读取走 `get_env_value`,它先查 scope 化的 `os.environ`
再查 .env。`hermes_cli/config.py:4109 @ 863e313`

```python
def get_env_value(key: str) -> Optional[str]:
```

---

## 10. 文档 / 注释与代码的出入

**C-1. `_configure_mcp_tools_interactive` docstring 说写 `tools.exclude`,代码写 `tools.include`。**
docstring:`hermes_cli/tools_config.py:5180 @ 863e313`

```python
    a per-server curses checklist.  Writes changes back as ``tools.exclude``
```

代码:`hermes_cli/tools_config.py:5290 @ 863e313`

```python
            tools_cfg["include"] = chosen_names
```

同函数下方的注释已经写对了(`:5273` 那段),说明是 docstring 漏改。以代码为准:**写 include**。

**C-2. `IMAGEGEN_BACKENDS` 的说明注释列的字段名与实际字段对不上。**
注释说条目有 `model_catalog_fn` 与 `default_model`:`hermes_cli/tools_config.py:3655 @ 863e313`

```python
#   - model_catalog_fn:  returns an OrderedDict-like {model_id: metadata}
```

实际字典里是 `catalog_fn`,且**没有** `default_model`(默认模型由 `catalog_fn()` 的第二个返回值给):
`hermes_cli/tools_config.py:3674 @ 863e313`

```python
        "catalog_fn": _fal_model_catalog,
```

**C-3. `_hidden_nous_gateway_message` 已是永久返回空串的 no-op,但三个调用点仍在拼参数、判空、逐行打印。**
`hermes_cli/tools_config.py:3177 @ 863e313`

```python
    """Deprecated: Nous Tool Gateway rows are no longer hidden.
```

调用点之一(reconfig):`hermes_cli/tools_config.py:4603 @ 863e313`

```python
    hidden_nous_message = _hidden_nous_gateway_message(
```

这不是矛盾,而是**已确认的死代码**:`if hidden_nous_message:`(`:4614`、`:4621`)恒假。

**C-4. `STT_MODEL_CATALOG` 的"三处保持同步"注释只对了两处半。**
`hermes_cli/tools_config.py:3980 @ 863e313`

```python
# Kept in sync with the dashboard selects (hermes_cli/web_server.py
```

实测:桌面端 `apps/desktop/src/app/settings/constants.ts:265` 的 `stt.provider` 含 `mistral` 且有
`stt.mistral.model` 枚举,而本表没有 mistral(CLI 也确实没有 mistral 的 provider 行,`grep "stt_provider"`
只有 local/openai/groq/xai/elevenlabs/deepinfra)。另外 `local` 的顺序与另外两处不同(见 §1.4,是刻意的)。

**C-5. `_configure_imagegen_model` 的 docstring 说"写到 `config[backend_config_key]["model"]`",
措辞暗示 backend 可自定义 config 段;今天只有一个 backend,`config_key` 恒为 `image_gen`。** 不算错,记录以免误判扩展性。

---

## 11. 可疑缺陷(只记录不修)

**D-1(会崩)· 插件模型选择器信任 `default_model()` 一定在 `list_models()` 里。**
`hermes_cli/tools_config.py:3793 @ 863e313`

```python
    current_model = cur_cfg.get("model") or default_model
    if current_model not in catalog:
        current_model = default_model
```

第二行"修正"之后没有再校验,`ordered[0]` 可能是一个不在 catalog 里的 id(或 `None`),接着
`hermes_cli/tools_config.py:3817 @ 863e313`

```python
        row = _format_imagegen_model_row(mid, catalog[mid], widths)
```

直接 `KeyError`。**怎么踩到**:任何第三方 image_gen / video_gen 插件的 `default_model()` 返回值与
`list_models()` 不一致(或返回 None),用户在 `hermes tools` 里选中它 → `hermes tools` 崩栈退出。
video 版同样(`hermes_cli/tools_config.py:3956 @ 863e313`)

```python
        meta = catalog[mid]
```

**实测复现**(注册一个 `default_model()` 返回 `'not-in-catalog'` 的假 provider):
`_configure_imagegen_model_for_plugin('badp', {})` → `CRASH KeyError 'not-in-catalog'`。

**D-2(丢配置)· vision 的设置会被调用者随后那次 `save_config` 覆盖回默认值。**
`_configure_vision_backend` 自己加载/保存 config:`hermes_cli/tools_config.py:4356 @ 863e313`

```python
    config = load_config()
```

而调用它的 `tools_command` 持有一份更早的 config,并在配置完之后再存一次:
`hermes_cli/tools_config.py:5153 @ 863e313`

```python
            _save_platform_tools(config, pkey, new_enabled)
            save_config(config)
```

`_reconfigure_tool` 同样:`hermes_cli/tools_config.py:4565 @ 863e313`

```python
        _reconfigure_simple_requirements(ts_key)

    save_config(config)
```

`save_config` 默认整文档替换(`hermes_cli/config.py:3510 @ 863e313`)

```python
    merge_existing: bool = False,
```

**怎么踩到 / 实测**:临时 HERMES_HOME 下,先 `load_config()` 拿 caller 副本 → 另一份 fresh config 写入
`auxiliary.vision.provider="custom"` + `base_url` 并 `save_config` → 再 `save_config(caller)`。
落盘结果为 `auxiliary.vision.provider: auto` / `base_url: ''`。也就是说,用户在 `hermes tools` 里配的
vision provider/model **每次都会被同一次命令的收尾保存抹掉**。

**D-3(丢配置)· 老用户流调用 checklist 时漏传 platform,平台受限 toolset 会被无声删除。**
首装流传了 pkey:`hermes_cli/tools_config.py:4901 @ 863e313`

```python
            new_enabled = _prompt_toolset_checklist(pinfo["label"], checklist_preselected, pkey)
```

老用户流没传(第三个位置参数缺失,函数签名默认 `platform="cli"`):`hermes_cli/tools_config.py:5092 @ 863e313`

```python
        new_enabled = _prompt_toolset_checklist(
            pinfo["label"],
            current_enabled,
            force_fresh=True,
        )
```

签名:`hermes_cli/tools_config.py:2725 @ 863e313`

```python
def _prompt_toolset_checklist(
```

"Configure all platforms (global)" 分支同样漏传:`hermes_cli/tools_config.py:5012 @ 863e313`

```python
            new_enabled = _prompt_toolset_checklist(
```

**怎么踩到 / 实测**:config 为 `{'platform_toolsets': {'discord': ['discord','discord_admin','web','memory']}}`,
按老用户流的调用方式跑 `_prompt_toolset_checklist('Discord', current_enabled, force_fresh=False)`,返回集合中
`discord` / `discord_admin` 均为 False;而 `_checklist_toolset_keys('discord')` 含这两项,所以
`(current - new) & universe == ['discord','discord_admin']` → UI 打印 `- Discord`、`- Discord Server Admin`
并写盘删除。用户只是打开 `hermes tools` → Configure Discord 看一眼、什么都不改,就丢了两个 toolset。

**D-4(形状不一致)· FAL 的 `image_gen.provider` 回写策略在 configure / reconfigure 两条流里相反。**
configure:`hermes_cli/tools_config.py:4243 @ 863e313`

```python
            if isinstance(img_cfg, dict) and img_cfg.get("provider") not in {None, "", "fal"}:
```

reconfigure:`hermes_cli/tools_config.py:4763 @ 863e313`

```python
                img_cfg = config.setdefault("image_gen", {})
                if isinstance(img_cfg, dict):
                    img_cfg["provider"] = "fal"
                    img_cfg["use_gateway"] = False
```

**怎么踩到**:两条路径产生的 config.yaml 形状不同(一个不写 provider 键,一个写 `"fal"` 且写
`use_gateway: false`)。运行期两者等价(`_is_provider_active` 把三值视为同一,`:3628`),但
diff / 备份 / GUI 对比会出现无意义抖动;也让"配置是否被显式设置过"这一信息不可靠。

**D-5(恒真分支 → 每次都"保存")· 保存判定没有像 diff 一样被 `_diff_universe` 限缩。**
`hermes_cli/tools_config.py:5125 @ 863e313`

```python
        if new_enabled != current_enabled or selected_to_configure:
```

`current_enabled` 来自 `_get_platform_tools`,会解析出 checklist 从不展示的条目(`stt` 被
`_CONFIG_ONLY_TOOLSETS` 排除、`kanban`、`context_engine`、平台复合项);`new_enabled` 只可能是
checklist 宇宙的子集。**两者几乎必然不等** → 每次进入平台配置都判定为"有变更",打印
`✓ Saved ... configuration` 却一条 `+`/`-` 都不打(diff 被限缩了)。
`_CONFIG_ONLY_TOOLSETS` 定义:`hermes_cli/tools_config.py:165 @ 863e313`

```python
_CONFIG_ONLY_TOOLSETS = {"stt"}
```

**D-6(错位)· image 选择器的表头有两个前导空格,数据行没有。**
表头:`hermes_cli/tools_config.py:3726 @ 863e313`

```python
        f"  {'Model':<{widths['model']}}  "
```

数据行:`hermes_cli/tools_config.py:3682 @ 863e313`

```python
        f"{model_id:<{widths['model']}}  "
```

video 版的内联实现反而对齐了:`hermes_cli/tools_config.py:3958 @ 863e313`

```python
            f"  {mid:<{widths['model']}}  "
```

**怎么踩到**:`hermes tools` → Image Generation → 选模型时列名与列值错开两格。纯观感,但暴露了
"同一段渲染被抄三份"这件事。

**D-7(静默无效)· `hermes tools disable <server>:<tool>` 写 exclude,而交互 UI 把 server 设成 include 模式。**
写入端:`hermes_cli/tools_config.py:5336 @ 863e313`

```python
        exclude = list(tools_cfg.get("exclude") or [])
```

运行期优先级:`tools/mcp_tool.py:5848 @ 863e313`

```python
        if include_set:
```

**怎么踩到**:用户先用 `hermes tools` → "Configure MCP server tools" 勾掉几个工具(于是 server 变成
`tools.include: [...]`),之后再用 `hermes tools disable github:create_issue`。命令打印
`Disabled: github:create_issue`,但 `include` 存在 ⇒ exclude 被完全忽略 ⇒ 该工具**照样注册**。
反向也一样:`enable` 只从 exclude 里删名字,不会把工具加进 include。

**D-8(死循环 + 反复联网)· 非 TTY 下 `hermes tools` 永不退出。**
`_prompt_choice` 在非 TTY 恒返回 default;主菜单的 default 是 0(第一个平台),而 "Done" 的索引 ≥1。
`hermes_cli/tools_config.py:4987 @ 863e313`

```python
    while True:
        idx = _prompt_choice("Select an option:", platform_choices, default=0)

        # "Done" selected
        if idx == _done_idx:
            break
```

**怎么踩到 / 实测**:`HERMES_HOME=$(mktemp -d) python -c "...tools_command(Namespace(summary=False))" < /dev/null`
在 25 秒超时前循环了 6 轮,每轮都打印 `✓ Saved 🖥️  CLI configuration`,并且每轮都**重新触发**
`computer_use` 的 cua-driver 安装(`curl` 到 `cua.ai`,日志里 403)与 `Nous Portal login?` 提示。
也就是说,任何把 `hermes tools` 放进脚本/CI/管道的用法都会变成一个不停重装、不停打 HTTP 的忙循环。
(能循环下去还因为 D-5 让"有变更"恒真;即使 D-5 修了,循环本身也不会停,只是不再反复存盘。)

**D-9(顺序)· provider 配置键先落盘,API key 后问;跳过 key 后配置停留在"看起来配好了"的状态。**
见 §3.5。`hermes_cli/tools_config.py:4308 @ 863e313`

```python
    if all_configured:
```

`all_configured=False` 时函数直接结束,既不打印失败结论也不回滚。

**D-10(泄露前缀)· reconfigure 回显已存 key 的前 8 位。**
`hermes_cli/tools_config.py:4775 @ 863e313`

```python
            _print_info(f"  {var['key']}: configured ({existing[:8]}...)")
```

同样在 `hermes_cli/tools_config.py:4836 @ 863e313`

```python
            _print_info(f"  {var}: configured ({existing[:8]}...)")
```

**怎么踩到**:用户把 `hermes tools` 的输出贴进 issue / 录屏,`sk-proj-`、`fal-…` 之类的前缀外泄。
对短 key 更危险。

**D-11(计数口径不一致)· `--summary` 的分子含 MCP server,分母只有 configurable toolsets。**
summary 走 `_platform_toolset_summary`,后者用 `_get_platform_tools` 的默认参数
`include_default_mcp_servers=True`:`hermes_cli/tools_config.py:2090 @ 863e313`

```python
def _platform_toolset_summary(config: dict, platforms: Optional[List[str]] = None) -> Dict[str, Set[str]]:
```

`hermes_cli/tools_config.py:2227 @ 863e313`

```python
    include_default_mcp_servers: bool = True,
```

`hermes_cli/tools_config.py:2475 @ 863e313`

```python
    if include_default_mcp_servers:
```

而菜单里的每一处计数都显式传 `False`(`:4964`、`:5077`、`:5162`)。
**怎么踩到**:配了 MCP server 的用户,`hermes tools --summary` 会打出类似 `(29/26)` 的分数,并把
server 名当成 toolset 列进 `✓` 清单。

**D-12(无声丢弃)· `hermes tools enable stt` 会写进 config,但下一次交互保存会把它删掉。**
`stt` 在 `CONFIGURABLE_TOOLSETS` 里(`hermes_cli/tools_config.py:109 @ 863e313`)

```python
    ("stt",             "🎙️ Speech-to-Text",           "voice transcription (gateway voice messages + voice mode)"),
```

所以通过 `valid_toolsets` 校验(`:5412`)并被写入 `platform_toolsets`;但它同时在 `_CONFIG_ONLY_TOOLSETS`
里,checklist 不展示它(`hermes_cli/tools_config.py:2742 @ 863e313`)

```python
    effective = [
```

而 `_save_platform_tools` 的 `preserved_entries` 只保留**非 configurable** 的条目
(`hermes_cli/tools_config.py:2555 @ 863e313`)

```python
    preserved_entries = {
```

⇒ `stt` 既不在 `new_enabled` 里也不被保留 ⇒ 下次任何一次 `hermes tools` 交互保存就把它删了。
而且 `stt` 本来就零 tool schema,写进 `platform_toolsets` 本身也是无意义的。

---

## 12. 配套测试(行为规格)

| 文件 | 覆盖本段的什么 |
| --- | --- |
| `tests/hermes_cli/test_tools_config.py` | `TestImagegenModelPicker`(3689 选择器写盘 / 非 TTY 语义 / 非 dict 段自愈)、`test_vision_picker_custom_endpoint`(4378 分支:base_url+model 进 config、key 进 env、provider 钉 custom)、`test_kanban_not_reported_as_removed_in_diff`(5126 的 diff 限缩)、`test_first_install_nous_auto_configures_video_gen`(4921) |
| `tests/hermes_cli/test_image_gen_picker.py` | `_plugin_image_gen_catalog`(3751)、`_configure_provider` 走插件行写 `image_gen.provider`+`model`(4225→3876)、`_is_provider_active` 插件行压过托管行 |
| `tests/hermes_cli/test_video_gen_picker.py` | `TestReconfigureWritesProvider`(4749/4797 的插件 video 分支)、插件行注入、active 判定 |
| `tests/hermes_cli/test_stt_picker.py` | `TestConfigWrites`(4052/4705)、`TestModelPicker`(3994)、`TestConfigOnlyExclusion`(`_CONFIG_ONLY_TOOLSETS`)、`TestPostSetup` |
| `tests/hermes_cli/test_tts_picker.py` | TTS provider 行与 `tts.provider` 落盘 |
| `tests/hermes_cli/test_mcp_tools_config.py` | `_configure_mcp_tools_interactive`(5176):写 include 而非 exclude、空工具 server 跳过 |
| `tests/hermes_cli/test_tools_disable_enable.py` | `tools_disable_enable_command`(5389):disable 内建、未知 server 报错、list 打印 exclude、部分成功 |
| `tests/cli/test_cli_tools_command.py` | `/tools` 斜杠命令如何调这套后端 |
| `tests/hermes_cli/test_post_setup_gating.py` | `_toolset_needs_configuration_prompt` 的 post_setup 闸门(3382,决定 4218/4305 会不会跑) |
| `tests/hermes_cli/test_tool_token_estimation.py` | `_estimate_tool_tokens`(2683),checklist 底部的 token 估算 |

**没有测试覆盖的**(与 §11 对应):D-2(vision 覆盖)、D-3(平台参数)、D-5(保存判定)、D-7(include/exclude
互斥)、D-8(非 TTY 死循环)、D-11(summary 计数)、D-12(stt 写入被删)。`test_mcp_tools_config.py` 里有多段
连续空行,形似删掉过用例。

---

## 13. 重实现要点(从零写这套配置面必须知道的)

1. **"provider 落盘"必须是一个纯函数,并且是唯一写入点。** `_write_provider_config` 的存在理由就是让
   CLI、GUI、非交互三个面共享同一段键写入逻辑。做自己的 harness 时,先定义
   `write_provider_selection(provider_row, config) -> None`(不 IO、不提示、不联网),交互层只负责收集输入。
   否则必然出现本段 §5.2 那种"两条流手工镜像后逐渐分叉"的负债。

2. **配置对象的所有权要么全程传递,要么全程不传递,不能混。** 本段最严重的两个 bug(D-2、D-3)都源自
   "有的函数吃调用者的 config,有的函数自己 load/save"。要么让所有配置函数接受并只修改传入的 dict,由最外层
   统一保存;要么全部走 `save_config(..., merge_existing=True)` 式的**局部合并**写入。

3. **非交互(非 TTY)必须是一等公民,而不是"取消语义"的副产品。** 把"取消 = 返回默认值"当成非 TTY 的兜底,
   在单选择器层面很优雅(§1.2),但一旦外面套了 `while True` 菜单就变成死循环(D-8)。正确做法:在进入任何
   交互循环之前显式检测 `stdin.isatty()`,非 TTY 直接走 summary/报错路径。

4. **"要不要提示配置"与"配置是否完整"是两个谓词,必须分开。** 本段用
   `_toolset_needs_configuration_prompt` 只看"provider 键存不存在"(如 `"backend" in web_cfg`),
   而 key 是否真的填了由 `_toolset_has_keys` 管。因为落盘早于问 key(D-9),两个谓词会不一致。
   重实现时把落盘挪到 key 收集之后,或者让"完整性"谓词同时校验键与凭据。

5. **过滤器只留一种形状。** MCP 的 include/exclude 双形状 + "include 压 exclude" 的优先级,让 CLI 与 TUI
   两个入口写出互相看不见的配置(D-7)。要么只留白名单,要么让所有写入点先把对方形状归一化。

6. **diff 宇宙(展示什么)与状态宇宙(存了什么)必须显式区分,并且两处都用同一个宇宙。**
   本段已经想到了这点(`_checklist_toolset_keys`),但只用在打印上,没用在"是否有变更"的判定上(D-5)。
   规则:凡是拿"UI 返回值"和"运行期解析值"做集合运算的地方,都必须先投影到 UI 宇宙。

7. **插件返回的一切都要当不可信输入校验。** `default_model()` 与 `list_models()` 的一致性没有被校验就直接
   `catalog[mid]`(D-1)。凡是跨插件边界的数据,取完立刻做一次归一化 + 校验,失败退化成"这个 provider 不可选"
   而不是崩栈。

8. **秘密永远不回显,哪怕只是前缀。** `existing[:8]` 这种"友好提示"在 issue / 录屏里就是泄露(D-10)。
   用"已配置(长度 N,更新时间 T)"代替前缀回显。
