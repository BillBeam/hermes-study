# R8C 底稿 · `hermes_cli/web_server.py` 6249–11049 —— 模型分配 + Provider OAuth 两阶段

> 基线:`863e31318553cda8ad61df681d08175364d4164b`。所有断言溯源格式为
> `路径:行号 @ 863e313`,锚点单独成行放在代码块之前,块内为基线逐字原文。
> 非源码块(我做的表 / shell 输出 / 推演)用 ```text / ```console / ```verify 声明。

**分工声明**:本段**不覆盖** config 读写端点(`PUT /api/config` / `GET /api/config` /
Raw YAML)——那由本轮另一段定案。本底稿只做**模型分配**与 **OAuth 两阶段**。
`_denormalize_config_from_web`(`hermes_cli/web_server.py:6834`)虽然物理上落在
6249 区间内,但它是 config 端点的反归一化器,归另一段;本文只在第 2.6 节提一句
它与 `_normalize_main_model_assignment` 共用同一个"聚合器兜底"语义,作为交叉引用。

---

## 0. 取证环境(报数用)

```console
$ git -C /home/user/hermes-agent rev-parse HEAD
863e31318553cda8ad61df681d08175364d4164b
$ git -C /home/user/hermes-agent status --porcelain
（空)
```

收工复核见第 9 节。venv 包数:

```console
$ /home/user/hermes-venv/bin/pip list | tail -n +3 | wc -l
91
$ ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l
91
```

**⚠ 环境已漂移**:`CLAUDE.md` 记录 R8B 实测为 **87 包**,本轮实测 **91 包**。
按 CLAUDE.md「用例数是环境的函数」的约定,本底稿所有测试数字都以 **91 包**为准,
与 R8B 的数字不可直接相减。我未改动 venv(只跑 `pip list` 读),漂移应来自本轮
其它并行子代理装了平台 extra。

---

## 1. 地图:行号区间 → 职责

### 1.1 区间表

```text
区间              职责                                            归属
-----------------------------------------------------------------------------
6247–6251        段落横幅 "Model assignment"                      本段
6255–6268        _AUX_TASK_SLOTS:11 个辅助槽位的规范顺序          本段
6270–6314        GET  /api/model/options       模型选择器数据源    本段
6315–6391        GET  /api/model/recommended-default 新登录默认模型 本段
6392–6442        GET  /api/model/auxiliary     读辅助槽位当前分配   本段
6443–6458        GET  /api/model/moa           读 MoA 槽位          本段
6459–6532        PUT  /api/model/moa           写 MoA 槽位          本段
6533–6593        POST /api/model/set           ★写入口(异步壳)     本段
6594–6783        _apply_model_assignment_sync  ★写主体(同步)       本段
6784–6833        _infer_provider_on_model_change Config 页扁平字段推断 本段(边缘)
-----------------------------------------------------------------------------
6834–6910        _denormalize_config_from_web                     ◀ 另一段
6911–6931        PUT  /api/config                                 ◀ 另一段
6932–7630        env 变量 / 凭据探针 / custom-endpoints / 凭据校验  ◀ 邻段,非本段
7633–9503        messaging 平台目录 + WhatsApp/Telegram 配对上线    ◀ 邻段,非本段
-----------------------------------------------------------------------------
9504–10042       OAuth Phase 1:目录 + 状态 + disconnect           本段
  9516–9540        _truncate_token         token 脱敏显示
  9541–9614        _anthropic_oauth_status 两来源优先级
  9615–9638        _claude_code_only_status
  9639–9668        _copilot_acp_status
  9669–9747        _OAUTH_PROVIDER_CATALOG 8 张手工卡片
  9748–9843        _resolve_provider_status 状态分派
  9844–9881        disconnect 命令 / 提示(能不能自动断开)
  9882–9931        _build_oauth_catalog     手工卡片 ∪ 统一目录
  9932–9974        GET    /api/providers/oauth
  9975–10042       DELETE /api/providers/oauth/{provider_id}
-----------------------------------------------------------------------------
10043–11046      OAuth Phase 2:浏览器内 PKCE 与 device-code       本段
  10079–10099      会话表 + Anthropic OAuth 常量(可缺失降级)
  10101–10155      会话生命周期(GC / 新建 / profile 归属)
  10156–10212      _save_anthropic_oauth_creds ★凭据落盘
  10213–10239      _start_anthropic_pkce
  10240–10319      _submit_anthropic_pkce      ★码换 token
  10320–10531      _start_device_code_flow     4 个 provider 分支
  10532–10595      _nous_poller
  10596–10679      _minimax_poller
  10680–10750      _xai_device_poller
  10751–10798      设备码错误文案整形
  10799–10941      _codex_full_login_worker
  10942–10979      POST   /{provider_id}/start
  10980–10995      POST   /{provider_id}/submit
  10996–11021      GET    /{provider_id}/poll/{session_id}
  11022–11045      DELETE /sessions/{session_id}
-----------------------------------------------------------------------------
11047+           Session detail 端点                              ◀ 出界
```

### 1.2 ◇ 横幅的覆盖范围名不副实

`hermes_cli/web_server.py:6248`

```
# Model assignment — pick provider+model for main slot or auxiliary slots.
# Mirrors the model.options JSON-RPC from tui_gateway but uses REST so the
# Models page (which has no chat PTY open) can drive it.
# ---------------------------------------------------------------------------
```

下一条横幅在 `9504`。也就是说这条横幅**名义上罩住 6249–9503 共约 3250 行**,
而真正属于"模型分配"的只有约 **540 行**(6247–6833)。中间 2700 行是 env 变量、
custom endpoints、凭据探针、messaging 平台目录、WhatsApp/Telegram 配对——
和模型分配毫无关系。**记 ◇**:靠横幅定位这个文件会系统性走偏,必须靠
`grep -n "^@app\.\|^def "` 重建目录。这也是本轮任务描述里"6249 Model assignment"
听起来只有一小块、实际横跨三千行的原因。

### 1.3 为什么需要这几块(逐块讲"解决什么问题")

**为什么要有 `/api/model/*` 这一整簇 REST 端点?** 因为 TUI 里换模型走的是
`tui_gateway` 的 `model.options` JSON-RPC,而那条通道**要求有一个活着的聊天 PTY**。
Dashboard 的 Models 页是一个独立页面,用户可能根本没开聊天。作者的原话:

`hermes_cli/web_server.py:6248`

```
# Model assignment — pick provider+model for main slot or auxiliary slots.
```

`hermes_cli/web_server.py:6279`（`get_model_options` docstring 内)

```
    REST equivalent of the ``model.options`` JSON-RPC on tui_gateway, so the
    dashboard Models page can render the picker without a live chat session.
    The response shape matches ``model.options`` 1:1 so ``ModelPickerDialog``
    can share the same types.
```

→ 这是一条**同形复制**的设计:响应体与 JSON-RPC 1:1 相同,好让前端的
`ModelPickerDialog` 组件两边复用同一套类型定义。代价是同一套语义有两个实现入口
(JSON-RPC 与 REST),后面会看到写入侧确实出现了必须"两边都改"的分叉。

**为什么 `_AUX_TASK_SLOTS` 要在这里硬编码一份?**

`hermes_cli/web_server.py:6253`

```
# Canonical auxiliary task slots. Keep in sync with DEFAULT_CONFIG["auxiliary"]
# in hermes_cli/config.py — listed here for deterministic ordering in the UI.
```

`hermes_cli/web_server.py:6255`

```
_AUX_TASK_SLOTS: Tuple[str, ...] = (
    "vision",
    "web_extract",
    "compression",
    "skills_hub",
    "approval",
    "mcp",
    "title_generation",
    "triage_specifier",
    "kanban_decomposer",
    "profile_describer",
    "curator",
)
```

理由是**UI 需要确定性顺序**,而 `DEFAULT_CONFIG["auxiliary"]` 是个 dict,
遍历顺序虽然在 CPython 3.7+ 是插入序、但语义上不该被 UI 依赖。代价:
这是一份**手工同步的副本**,注释自己写了 "Keep in sync"。**记 ◇**:没有任何
测试或断言强制这两份列表一致——加一个辅助槽位而忘了改这里,GUI 就会静默地
少一行,而配置里那个槽位照常生效。

---

## 2. 模型分配

### 2.1 「主槽位」和「辅助槽位」是什么(给不熟本项目的人)

```text
主槽位 (main slot)
  = 你和 agent 对话时,真正生成回复的那个模型。
    落盘位置:config.yaml 的 model.provider + model.default(可选 base_url / api_key)。
    一个 Hermes 实例只有一个主槽位。

辅助槽位 (auxiliary slots)
  = agent 在后台干杂活时用的模型,每类杂活一个独立槽位,共 11 个:
    看图(vision)、抽网页正文(web_extract)、压缩上下文(compression)、
    技能中枢(skills_hub)、审批判定(approval)、MCP、起标题(title_generation)、
    分诊(triage_specifier)、看板拆解(kanban_decomposer)、
    画像描述(profile_describer)、策展(curator)。
    落盘位置:config.yaml 的 auxiliary.<task>.provider / .model。
    默认值是 provider="auto",意思是"跟主槽位走"。
    用户可以把某个槽位"钉"(pin)到一个更便宜的模型上——例如起标题这种
    杂活没必要用旗舰模型。钉住之后它就**不再跟随主槽位**。

MoA 槽位 (Mixture-of-Agents)
  = 另一类槽位:一组"参考模型"并行答题 + 一个"聚合模型"合稿。
    落盘位置:config.yaml 的 moa.*。由 GET/PUT /api/model/moa 单独管。
```

三者互不干涉,这一点在第 2.4 节会变成一个真实的钱包问题。

### 2.2 一次"在 GUI 里换模型"的完整走法

```text
① 浏览器 POST /api/model/set?profile=<可选>
     body = ModelAssignment{scope:"main", provider, model,
                            base_url?, api_key?, confirm_expensive_model?}

② [跳 1] set_model_assignment (:6533) —— 异步壳
     a. 校验 scope ∈ {main, auxiliary},否则 400
     b. 贵模型闸门:未确认时先算 expensive_model_warning
        —— 注意这一步**故意在 _profile_scope 之外**(见 2.3)
        —— 命中就直接返回 {ok:false, confirm_required:true},不落盘
     c. 把同步主体丢进 asyncio.to_thread

③ [跳 2] _apply_model_assignment_sync (:6594) —— 工作线程内,被 _profile_scope 包住
     a. cfg = load_config()
     b. 主槽位:provider, model = _normalize_main_model_assignment(...)   ← 见 2.5
     c. 从 config 的 providers.<provider> 补 base_url / api_key(仅当请求没带)
     d. model_cfg = _apply_main_model_assignment(...)                    ← 见 2.6
     e. 若切到 nous:additive 地把未配置的工具路由到 Nous Tool Gateway
     f. save_config(cfg)                     ★★ 落盘到 ~/.hermes/config.yaml
     g. 若 provider ∈ {custom, local} 且有 base_url:再注册一条命名
        custom_providers 条目(幂等,按 base_url 去重)
     h. 扫描 11 个辅助槽位,把仍钉在**别的 provider** 上的挑出来 → stale_aux

④ 返回 {ok, scope, provider, model, base_url, gateway_tools, stale_aux}
     前端据此弹"要不要把辅助槽位重置回主模型"的提示
```

关键落盘只有**一次** `save_config(cfg)`,目标是 `~/.hermes/config.yaml`:

`hermes_cli/config.py:3512`

```
    """Save configuration to ~/.hermes/config.yaml.\n
```

`profile` 参数通过 `_profile_scope` 改写 `get_hermes_home()`,从而把同一次写入
重定向到某个 profile 的 home:

`hermes_cli/web_server.py:6580`

```
        def _apply_assignment():
            with _profile_scope(body.profile or profile):
                return _apply_model_assignment_sync(
                    scope, provider, model, task, base_url, api_key
                )

        return await asyncio.to_thread(_apply_assignment)
```

**写入只影响新会话**,当前正在跑的聊天 PTY 不受影响——这是作者明写的:

`hermes_cli/web_server.py:6535`

```
    """Assign a model to the main slot or an auxiliary task slot.

    Writes to ``~/.hermes/config.yaml`` — applies to **new** sessions only.
    The currently running chat PTY (if any) is not affected; use the
    ``/model`` slash command inside a chat to hot-swap that specific session.
    """
```

### 2.3 一个值得学的并发细节:`_profile_scope` 绝不能跨 await

`hermes_cli/web_server.py:6552`

```
        # Expensive-model warning runs BEFORE the profile scope is entered:
        # _profile_scope must never be held across an await (the RLock is
        # reentrant per-thread, so a second coroutine interleaving on the
        # event-loop thread could cross-restore the module globals).
        if model and not body.confirm_expensive_model:
            try:
                from hermes_cli.model_cost_guard import expensive_model_warning

                # Pricing lookup can hit models.dev / a /models endpoint on a
```

**这是本段最值得抄走的设计教训。** `_profile_scope` 的实现方式是"临时改写模块级
全局变量 + 用锁保护,退出时还原"(`hermes_cli/web_server.py:13574` 起,它要同时改写
`load_config/save_config` 看到的 home 和 `SKILLS_DIR` 这类 import 时就绑死的全局)。
锁是 **RLock(可重入)**,而可重入是**按线程**判定的。asyncio 的多个协程跑在**同一个
线程**上,所以协程 A 持锁期间 await 让出,协程 B 在同一线程上再次进入 `_profile_scope`
**不会被阻塞**(RLock 认为是同一个线程的重入),B 退出时会把全局还原成 B 的旧值——
于是 A 醒来后看到的是错的 profile。

修法不是换锁,而是**把 await 挪到 scope 外面**:贵模型定价查询(可能打 models.dev,
必须异步)放在进入 scope 之前;真正需要 scope 的同步主体整体丢进 `asyncio.to_thread`,
在**自己的工作线程**里独占地持有 scope。

> **可迁移原则**:凡是用"临时改写全局 + 还原"实现的上下文隔离,在 asyncio 里
> 都必须整体退到 worker 线程执行,绝不能跨 await 持有。RLock 在协程世界里
> 不提供互斥,它只提供"同线程重入不死锁"。

### 2.4 辅助槽位不跟随主槽位:一个被明确定为"不修"的钱包坑

`hermes_cli/web_server.py:6681`

```
        # Surface auxiliary slots still pinned to a *different* provider than
        # the new main one. Switching the main model does NOT touch aux pins
        # (they're independent, sticky per-task overrides — see
        # auxiliary_client._resolve_auto). A user who switches main away from
        # a now-unpaid provider (e.g. nous with $0 balance) keeps paying 402s
        # on every background aux call until they reset those pins. We never
        # auto-clear them — pinning aux to a cheaper/different model is a
        # legitimate config — but we tell the caller so the UI can offer a
        # "reset to main" nudge instead of silently burning credits.
        new_provider = provider.strip().lower()
```

**故事**:用户余额耗尽,在 GUI 里把主模型从 nous 换到别家。聊天恢复正常了,但
后台每次起标题、抽正文、压上下文仍然打 nous,每次都 402。用户完全看不见——
这些都是后台调用。**为什么不自动清?** 因为"把起标题钉到便宜模型"是完全正当的配置,
自动清会毁掉用户的有意设置。**折中**:不动数据,但把冲突项算出来放进响应的
`stale_aux`,让 UI 主动问一句。

> **可迁移原则**:当"自动修复"和"用户意图"可能冲突时,第三条路是
> **既不改也不沉默**——把冲突计算出来交给 UI,让人来裁决。

顺带,`__reset__` 是这条路的配套:`task == "__reset__"` 时把 11 个槽位全部
复位成 `provider="auto"`、`model=""`,并调 `clear_model_endpoint_credentials`
清掉残留的端点密钥(`hermes_cli/web_server.py:6725` 起)。

### 2.5 `_normalize_main_model_assignment`(`:1423`)在归一什么、为什么必须归一

**场景先行(这是一个真实 bug 的修复)。** Models 页有两条写入路径:

1. "Change" 选择器 —— 发的是**真正的 Hermes provider slug**,没问题。
2. 每张分析卡片上的 "Use as → Main model" 菜单 —— 发的是 `entry.provider`,
   即**分析行里的 billing_provider**;老会话这一列是 NULL,前端就回落到
   **模型 id 的厂商前缀**。

于是 `modelVendor("anthropic/claude-opus-4.6")` 得到 `"anthropic"`,前端就发出
`provider="anthropic"` + `model="anthropic/claude-opus-4.6"`。这是一个
**OpenRouter 风格的带厂商前缀的 slug,配上原生 Anthropic provider**。写进 config 后,
新会话去打 `api.anthropic.com`,得到 400 `model: anthropic/claude-opus-4.6 not found`。
用户看到的现象是:**"我换了模型,但什么都没发生"**。

`hermes_cli/web_server.py:1426`

```
    The Models page has two assignment paths and only one of them was safe:

    - The "Change" picker sends a real Hermes provider slug — fine.
    - The per-card "Use as → Main model" menu sends ``entry.provider``
      from the analytics rows, falling back to the model's VENDOR prefix
      (``modelVendor("anthropic/claude-opus-4.6") == "anthropic"``) when
      the session row has no ``billing_provider`` (older sessions, NULL
      rows).  That wrote ``provider: anthropic`` +
      ``default: anthropic/claude-opus-4.6`` to config — a vendor-prefixed
      OpenRouter slug on the NATIVE Anthropic provider.  New sessions then
      400 against api.anthropic.com ("model: anthropic/claude-opus-4.6 not
      found") and the user reads it as "changing models does nothing".
```

**归一分四步,顺序是要害:**

```text
第 0 步  canonical = normalize_provider(prov_in)          别名折叠(x-ai → xai 等)

第 1 步  用户自声明的 provider 优先解析(:1466 起)
         resolve_user_provider  ← config 的 providers:
         resolve_custom_provider ← config 的 custom_providers:
         命中就**原样返回**(provider.id, model_in),模型 id 一个字都不改。
         理由:自建端点的命名空间(ollama/…, 某代理的前缀)注册表不认识,
               碰了就错。

第 2 步  "厂商前缀冒充 provider" 兜底(:1497 起)
第 3 步  已知原生 provider 的模型 id 格式归一(:1519 起)
```

第 2 步的守卫条件是本函数最微妙的地方:

`hermes_cli/web_server.py:1494`

```
    # ``providers.custom_provider_slug``) -- a bare ``startswith("custom")``
    # would also swallow unrelated unconfigured vendor names that merely
    # happen to start with "custom" (e.g. "customproxy").
    is_custom_provider_slug = canonical == "custom" or canonical.startswith("custom:")
    if (
        canonical not in _KNOWN_PROVIDER_NAMES
        and not is_custom_provider_slug
        and "/" in model_in
    ):
        # Vendor prefix posing as a provider (analytics fallback). Resolve
        # against the user's current provider when it's an aggregator that
        # serves vendor-prefixed slugs; otherwise default to openrouter.
        try:
            cur_cfg = cfg.get("model", {})
            cur_provider = (
                str(cur_cfg.get("provider", "") or "").strip().lower()
                if isinstance(cur_cfg, dict) else ""
            )
        except Exception:
```

**为什么需要 `is_custom_provider_slug` 这条排除?** 因为 `_KNOWN_PROVIDER_NAMES`
里只有裸的 `"custom"` 桶,**从来没有具体的 `custom:<name>`**。所以一个配好的
LiteLLM 代理 `custom:litellm` 配上 `ollama/glm-5.2`(带斜杠),三个条件全部成立,
就会被当成"厂商前缀冒充 provider"**静默改判到 openrouter**——这不是模型 id 被
改花了,是**整个 provider 被换掉了**。第 1 步通常能提前救下它(配置里有这条
custom_provider),但配置漂移(改名、删条目、打错字)时第 1 步落空,这条排除
就是最后一道网。测试把这一层单独钉死:

`tests/hermes_cli/test_normalize_main_model_assignment.py:35`

```
class TestUnresolvedNamedCustomProviderIsNotTreatedAsStrayVendorPrefix:
    """Covers the case where ``resolve_custom_provider`` finds no match --
    e.g. ``custom:litellm`` was configured once, then the entry was renamed
    or dropped from ``custom_providers``, but old sessions/config still
    reference the old slug.
    """

    def test_unresolved_named_custom_provider_slug_is_preserved(self):
        with _no_custom_providers_configured():
            assert _normalize_main_model_assignment("custom:litellm", "ollama/glm-5.2") == (
                "custom:litellm",
                "ollama/glm-5.2",
            )
```

而"厂商前缀冒充"这条主路径同样有钉子:

`tests/hermes_cli/test_normalize_main_model_assignment.py:63`

```
    def test_known_native_provider_still_normalizes_model(self):
        assert _normalize_main_model_assignment(
            "anthropic", "anthropic/claude-opus-4.6"
        ) == ("anthropic", "claude-opus-4-6")
```

注意兜底不是无脑写 openrouter:如果用户**当前就在某个聚合器上**(openrouter /
其它 `_AGGREGATOR_PROVIDERS` 成员),就保留用户当前的聚合器;只有当前不是聚合器
才落到 openrouter。因为带厂商前缀的 slug 本来就是聚合器的方言,用户已经在
聚合器上时改到别家纯属多事。

> **可迁移原则**:UI 传来的"provider"字段可能是三种完全不同的东西——路由目标、
> 计费厂商、模型 id 的命名空间前缀。**在写盘前设一个唯一的归一化收口(chokepoint)**,
> 让所有入口共享同一套判定;注释里作者原话是 "both at this single chokepoint so
> every caller inherits"(`hermes_cli/web_server.py:1440`)。

### 2.6 `_apply_main_model_assignment`(`:1535`):base_url / api_key 的生命周期

这个函数只干一件事:把 (provider, model) 写进 `model` 配置 dict,**顺带决定
旧的 `base_url` 和 `api_key` 该留还是该扔**。规则是"**换 provider 才扔**":

`hermes_cli/web_server.py:1568`

```
    model_cfg["default"] = model
    if base_url.strip():
        model_cfg["base_url"] = base_url.strip()
    elif model_cfg.get("base_url") and new_provider != prev_provider:
        # Switching providers: the old URL belonged to the old provider, drop
        # it so the new provider's default endpoint is used. Same-provider
        # re-assignment keeps the user's configured base_url intact.
        model_cfg["base_url"] = ""
    # The endpoint key follows the same lifecycle as base_url: an explicit key
```

**为什么需要"同 provider 保留"这一条?** 事故原文:

`hermes_cli/web_server.py:1545`

```
    - Otherwise, a stale ``base_url`` is cleared ONLY when switching to a
      *different* provider — that URL belonged to the old provider. When the
      provider is unchanged and no new URL is supplied, the existing
      ``base_url`` is preserved. This keeps a user's custom endpoint (e.g. a
      Xiaomi MiMo Token Plan host, ``https://token-plan-*.xiaomimimo.com/v1``)
      alive when they merely re-pick a model under the same provider — picking
      a model previously wiped it, forcing the registry default and breaking
      Token Plan keys.
```

**故事**:用户买的是小米 MiMo 的 Token Plan,密钥只在专属 host
`https://token-plan-*.xiaomimimo.com/v1` 上有效。他在同一个 provider 下换了个模型,
`base_url` 被清空,请求回落到注册表默认 host,Token Plan 密钥立刻失效。
现象是"换个模型就没法用了"。

`api_key` 走**完全相同的生命周期**,但有一个额外的陷阱——遗留别名 `api`:

`hermes_cli/web_server.py:1580`

```
    if api_key.strip():
        model_cfg["api_key"] = api_key.strip()
        model_cfg.pop("api", None)
    elif (model_cfg.get("api_key") or model_cfg.get("api")) and new_provider != prev_provider:
        # A stale endpoint secret can live under the legacy ``api`` alias with
        # no ``api_key`` (the resolver still reads ``model.api`` as a key), so
        # the switch-clears-the-key path must trigger on either field — else the
        # old endpoint's secret survives in config.yaml and contaminates a later
        # custom resolution. clear_model_endpoint_credentials scrubs both.
        clear_model_endpoint_credentials(model_cfg, clear_api_mode=False)
```

**失效链**(如果只判 `api_key` 不判 `api`):老配置里密钥存在 `model.api` 下、
`model.api_key` 不存在 → 切 provider 时 `model_cfg.get("api_key")` 为假 →
不触发清理 → 旧端点的密钥留在 config.yaml → 后续某次 custom 解析读到
`model.api` 当密钥用 → **把 A 家的密钥发给了 B 家的端点**。这条判定写成
`(api_key or api)` 就是为了堵这个。

另外两个细节:
- `model_cfg.pop("context_length", None)`(`:1592`)——换模型必须丢掉硬编码的
  上下文窗口覆盖,新模型窗口不一样。
- 切 provider 时额外调一次 `clear_model_endpoint_credentials(model_cfg, clear_api_key=False)`
  (`:1590`),清 `api_mode` 之类的端点形态标记。

**上游还有一层补齐**:请求没带 base_url / api_key 时,从 config 的
`providers.<provider>` 条目里补——但**只在请求没带的时候**:

`hermes_cli/web_server.py:6616`

```
        # Fall back to the provider entry's stored key only when the request
        # didn't carry one — same precedence as the base_url fill above. An
        # unconditional overwrite silently discards a key the caller is
        # rotating in, and model.api_key outranks the environment at client
        # construction (#62269), so the stale key keeps authenticating.
```

失效链清楚:无条件覆盖 → 用户正在轮换的新密钥被旧密钥顶掉 → 而
`model.api_key` 的优先级高于环境变量 → **旧密钥继续通过认证**,用户以为
换了密钥其实没换。

### 2.7 MoA 写入的一条独立原则:reject-don't-repair

`hermes_cli/web_server.py:6507`

```
            # Reject-don't-repair: normalize_moa_config() silently swaps any
            # preset containing incomplete slots for the hardcoded defaults —
            # correct tolerance for hand-edited configs at READ time, silent
            # data loss at WRITE time (#64156: desktop autosave of a
            # half-filled slot replaced the user's whole preset). Refuse the
            # save loudly so no client can corrupt config through this route.
            problems = validate_moa_payload(raw)
            if problems:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid MoA config: " + "; ".join(problems),
                )
```

**故事**:桌面端有自动保存。用户在 MoA 编辑器里刚填了一半的槽位,自动保存触发,
把这个半成品 POST 上来。`normalize_moa_config` 作为**读**路径的容错器,遇到不完整
的 preset 会静默换成硬编码默认值——于是用户**整个 preset 被默认值覆盖**,而且没有
任何提示。修法是在写路径上加一道 `validate_moa_payload`,不合格就 422 拒绝。

> **可迁移原则**:同一个 normalize 函数**不能同时服务读和写**。读路径要宽容
> (手改的配置文件得能用),写路径必须严格(宽容 = 静默数据丢失)。

同一段还有一条互补的原则——**merge 而非 overwrite**:

`hermes_cli/web_server.py:6519`

```
            normalized = normalize_moa_config(raw)
            # Merge instead of overwrite so that hand-edited keys not declared
            # in MoaConfigPayload (e.g. save_traces, trace_dir) survive a GUI
            # save.  See issue #58819.
            cfg.setdefault("moa", {}).update(normalized)
```

GUI 的 payload schema 永远是配置全集的子集,直接整块覆盖会抹掉所有 GUI 不认识
但用户手写过的键。

---

## 3. Phase 1 vs Phase 2 的分界:作者自己的说法

`hermes_cli/web_server.py:9504`

```
# ---------------------------------------------------------------------------
# OAuth provider endpoints — status + disconnect (Phase 1)
# ---------------------------------------------------------------------------
#
# Phase 1 surfaces *which OAuth providers exist* and whether each is
# connected, plus a disconnect button. The actual login flow (PKCE for
# Anthropic, device-code for Nous/Codex) still runs in the CLI for now;
# Phase 2 will add in-browser flows. For unconnected providers we return
# the canonical ``hermes auth add <provider>`` command so the dashboard
# can surface a one-click copy.
```

**作者的分期理由,逐字读出来是**:Phase 1 只做**只读可观测性 + 一个破坏性但简单的
动作(断开)**,登录流程"暂时仍然跑在 CLI 里";对没连上的 provider,dashboard
不自己实现登录,而是把标准命令 `hermes auth add <provider>` 吐给用户,让 GUI 做
一键复制。Phase 2 才把登录搬进浏览器。

**这个分期在工程上为什么合理(我的判读,不是作者原话):**

```text
Phase 1 的三个动作,风险与实现成本都极低:
  列举    —— 纯读,数据来自已有的 provider_catalog()
  查状态  —— 纯读,复用 CLI 已有的 get_*_auth_status
  断开    —— 删除已有存储里的条目;不需要任何新的协议实现、
            不需要新的密钥、不需要浏览器与后端的往返

Phase 2 的每一条都要新造机制:
  服务端会话表(带 TTL、带锁、带 GC)
  PKCE 密钥对的生成与保管
  device-code 的后台轮询线程 + 取消语义 + 与保存的原子性
  4 个 provider 各自不同的端点、字段名、时间单位、错误文案
  凭据落盘的权限与原子性
```

也就是说:**Phase 1 = 把已有 CLI 能力做一层只读投影 + 一个删除;
Phase 2 = 真正把 OAuth 协议实现搬进 web 进程。** 先发 Phase 1,用户立刻能在
GUI 里看清"我到底连了哪些账号、token 什么时候过期",这个价值不依赖 Phase 2。

**◎ 一处 Phase 1 注释已被 Phase 2 追平但没更新**:上面注释说
"The actual login flow ... **still runs in the CLI for now**",而 Phase 2
(`:10043` 起)已经把 Anthropic PKCE 和四家 device-code 全都搬进来了。注释保守、
不构成错误(它明说了 "Phase 2 will add"),但读到这里的人如果不往下翻会误判。
记 **◎**,不记 ▲。

**Phase 1 还有一处设计值得单独记**:目录成员是"手工卡片 ∪ 统一目录",不是纯手工:

`hermes_cli/web_server.py:9885`

```
    MEMBERSHIP is the union of:
      1. ``_OAUTH_PROVIDER_CATALOG`` — the explicit, hand-tuned cards that carry
         bespoke flow / status_fn / cli_command (including the api-key Anthropic
         PKCE card and the synthetic claude-code subscription row, which are not
         catalog providers), and
      2. every accounts-tab provider in the unified ``provider_catalog()`` (the
         ``hermes model`` universe) — so any OAuth/external provider added as a
         plugin appears automatically, with sensible defaults, even if no
         explicit card was written for it.
```

配套地,状态分派也有一条兜底分支,不然会出现"成员自动扩展了但状态没扩展"的裂缝:

`hermes_cli/web_server.py:9814`

```
        # No hand-written branch for this provider id: fall through to the
        # canonical slug-driven dispatcher so accounts-tab providers derived
        # from the unified catalog (which carry status_fn=None) still reflect
        # real login state instead of rendering permanently logged-out. This
        # closes the membership-auto-extends-but-status-doesn't gap: add an
        # OAuth/account provider plugin and its card shows the right state.
        raw = hauth.get_auth_status(provider_id)
```

> **可迁移原则**:"手工精修表 ∪ 自动目录"这种并集式注册,必须让**每一条派生
> 逻辑**(状态、图标、能力位)都有自动分支,否则新成员会以"永远登出"这类
> 静默错误状态出现。

---

## 4. PKCE 与 device-code 两条流程

### 4.1 先解释两个术语

```text
PKCE (Proof Key for Code Exchange,读作 "pixy")
  OAuth 授权码流程的加固版。客户端先随机生成一个高熵字符串 code_verifier,
  算出它的 SHA-256 叫 code_challenge。授权请求里**只发 challenge**;
  最后拿授权码换 token 时**才发 verifier**。
  防的是:攻击者截获了授权码,但因为拿不到 verifier,换不到 token。
  前提是 —— verifier 必须始终保密。这一点在 4.4 会出问题。

device code(设备码流程)
  给"没有浏览器、或浏览器和后端不在同一台机器"的场景设计。
  后端先向 provider 要一个短的 user_code + 一个 verification_url,
  显示给用户;用户在**任意另一台设备**上打开那个 URL、输入 code、点批准;
  后端在这期间**不断轮询** token 端点,直到拿到 token 或超时。
  不需要任何回调地址,因此在 SSH、容器、远程桌面里都能用。
```

### 4.2 各自适用什么场景

`hermes_cli/web_server.py:9665`

```
# ``flow`` describes the OAuth shape so the modal can pick the right UI:
# ``pkce`` = open URL + paste callback code, ``device_code`` = show code +
# verification URL + poll, ``external`` = read-only (delegated to a third-party
# CLI like Claude Code or Qwen).
```

作者在 xAI 卡片上明写了选 device-code 的理由:

`hermes_cli/web_server.py:9708`

```
        "id": "xai-oauth",
        "name": "xAI Grok OAuth (SuperGrok / Premium+)",
        # Device code is the default because it works in remote shells,
        # containers, and desktop installs without requiring a reachable
        # 127.0.0.1 callback.
        "flow": "device_code",
```

```text
浏览器能开(且能和用户手动交互)     → pkce   :当前只有 anthropic 一家
浏览器开不了 / 后端在远端容器里      → device_code :nous, openai-codex,
                                                    minimax-oauth, xai-oauth
根本不该由 Hermes 管                → external:qwen-oauth, copilot-acp,
                                                claude-code(凭据归第三方 CLI)
```

注意 **MiniMax 是混血**:结构上是 device-code(user_code + 后台轮询),但叠了
PKCE 做码绑定。作者刻意把它归到 `device_code`,因为**运维体验**上和 Nous 一样:

`hermes_cli/web_server.py:9697`

```
        # MiniMax's flow is structurally device-code (verification URI +
        # user code, backend polls the token endpoint) with a PKCE
        # extension for code-binding. The dashboard renders the same UX
        # as Nous's device-code flow; the PKCE bit is a security
        # extension that doesn't change the operator experience.
        "flow": "device_code",
```

> **可迁移原则**:`flow` 这个字段的语义是"**UI 该长什么样**",不是"协议是什么"。
> 给枚举取名时先想清楚它服务于谁的决策。

### 4.3 `state` / `code_verifier` 存在哪、多久过期、能不能重放

**存在哪:纯内存,进程级单例 dict,不落盘。**

`hermes_cli/web_server.py:10075`

```
# Sessions are kept in-memory only (single-process FastAPI) and time out
# after 15 minutes. A periodic cleanup runs on each /start call to GC
# expired sessions so the dict doesn't grow without bound.

_OAUTH_SESSION_TTL_SECONDS = 15 * 60
```

`hermes_cli/web_server.py:10080`

```
_oauth_sessions: Dict[str, Dict[str, Any]] = {}
_oauth_sessions_lock = threading.Lock()
```

`hermes_cli/web_server.py:10123`

```
def _new_oauth_session(
    provider_id: str,
    flow: str,
    profile: Optional[str] = None,
) -> tuple[str, Dict[str, Any]]:
    """Create + register a new OAuth session, return (session_id, session_dict)."""
    sid = secrets.token_urlsafe(16)
    profile_name = _oauth_profile_name(profile)
    sess = {
        "session_id": sid,
        "provider": provider_id,
        "flow": flow,
        "profile": profile_name,
        "created_at": time.time(),
        "status": "pending",  # pending | approved | denied | expired | error
        "error_message": None,
    }
    with _oauth_sessions_lock:
        _oauth_sessions[sid] = sess
    return sid, sess
```

各字段落点:

```text
session_id     secrets.token_urlsafe(16) = 16 字节 = 128 bit 熵,不可枚举
verifier       仅 PKCE:_start_anthropic_pkce 写 sess["verifier"](:10219)
state          仅 PKCE:sess["state"] = verifier(:10220)  ← 见 4.4,这是问题所在
code_verifier  MiniMax:sess["code_verifier"] = verifier(:10460)
device_code    Nous / xAI:sess["device_code"](:10364, :10508)
profile        写盘时要还原的 profile,后台线程靠它落到正确的 home
```

**注意 MiniMax 的字段名与 Anthropic 不同**(`code_verifier` vs `verifier`),
是两套独立的键,没有共用的 schema。**记 ◇**:会话 dict 是无 schema 的
`Dict[str, Any]`,每个 provider 分支自定字段名,拼写错了不会报错、只会在
poller 里 KeyError。

**多久过期:TTL 是 15 分钟,但只在有人发起新登录时才被真正执行。**

`hermes_cli/web_server.py:10101`

```
def _gc_oauth_sessions() -> None:
    """Drop expired sessions. Called opportunistically on /start."""
    cutoff = time.time() - _OAUTH_SESSION_TTL_SECONDS
    with _oauth_sessions_lock:
        stale = [sid for sid, sess in _oauth_sessions.items() if sess["created_at"] < cutoff]
        for sid in stale:
            _oauth_sessions.pop(sid, None)
```

**搜索面与结论**:在 `hermes_cli/web_server.py` 全文 grep `_gc_oauth_sessions`,
**只有两处**——定义(`:10101`)和唯一调用点(`:10950`,在 `start_oauth_login` 内)。
`_submit_anthropic_pkce`(`:10240`)与 `poll_oauth_session`(`:10996`)的函数体里
**都没有任何 `created_at` / TTL 判定**(我对 `10240–10252` 和 `10996–11021` 逐行
读过,只有 `sess["status"] != "pending"` 这一条状态判定)。

**▲ 结论**:注释说 "Sessions ... **time out after 15 minutes**",但代码里
**没有任何东西让会话自己过期**。没有后台清理任务,没有提交时的时效校验。
一个 3 天前创建的 pending PKCE 会话,只要期间没人发起过新的 OAuth 登录,
它就仍然在 `_oauth_sessions` 里、仍然可提交、其 `code_verifier` 仍然在进程内存里。
"time out after 15 minutes" 这句话只对"发生了下一次 /start"的情况成立。
严重度低(提交端点有 `_require_token` 保护,见 4.5),但**注释与代码不符**,
且长期驻留的 verifier 扩大了内存泄露面。

**能不能重放:**

```text
成功后的重放  —— 不能。成功时 sess["status"] = "approved"(:10313),
                 再次提交在 :10248 被 `if sess["status"] != "pending"` 挡住,
                 直接返回 {ok:false, status:"approved"},不会再打 token 端点。

失败后的重试  —— 可以,无限次。交换失败时 status 被置为 "error"(:10292),
                 之后同样被 :10248 挡住。但**在**第一次交换之前,同一个
                 session_id 可以反复提交不同的 code(每次都会打一次
                 Anthropic token 端点),没有尝试次数上限、没有速率限制。
                 因为端点有 _require_token 保护,这是已认证操作,风险有限。

取消后的竞态  —— 已被专门处理,见 4.6。
```

### 4.4 ★ 本段的重点安全问题:回调端点的鉴权

**先给结论:provider OAuth 根本没有回调端点。** 这是它和 MCP OAuth 最大的结构差异。

**免鉴权名单只放行了 MCP 的回调**,两层中间件各有一份、内容一致:

`hermes_cli/web_server.py:663`

```
    path = request.url.path
    is_mcp_oauth_callback = path.startswith("/api/mcp/oauth/callback/")
    if path.startswith("/api/") and path not in _PUBLIC_API_PATHS and not is_mcp_oauth_callback:
        if not _has_valid_session_token(request) and not _has_valid_query_token(request, path):
            return JSONResponse(
                status_code=401,
```

`hermes_cli/dashboard_auth/middleware.py:52`

```
    "/auth/native/authorize",
    "/auth/native/token",
    "/auth/native/refresh",
    "/auth/password-login",
    "/auth/logout",
    "/login",
    "/api/auth/providers",
    "/api/mcp/oauth/callback/",
    "/assets/",
    "/favicon.ico",
    "/ds-assets/",
    "/fonts/",
    "/fonts-terminal/",
)
```

**负结论的搜索面(逐条列出,便于复核):**

```console
$ grep -rn "\"/api/[^\"]*oauth[^\"]*callback[^\"]*\"\|'/api/[^']*oauth[^']*callback[^']*'" --include=*.py . | grep -v tests/
./hermes_cli/web_routers/mcp.py:276:@router.get("/api/mcp/oauth/callback/{server_name:path}")
./hermes_cli/dashboard_auth/middleware.py:59:    "/api/mcp/oauth/callback/",
./hermes_cli/web_server.py:664:    is_mcp_oauth_callback = path.startswith("/api/mcp/oauth/callback/")
./hermes_cli/web_server.py:12156:    suffix = f"/api/mcp/oauth/callback/{quote(server_name, safe='')}"

$ grep -rn "providers/oauth" --include=*.py . | grep -v tests/ | grep -E "@|route|add_api"
./hermes_cli/web_server.py:9932:@app.get("/api/providers/oauth")
./hermes_cli/web_server.py:9975:@app.delete("/api/providers/oauth/{provider_id}")
./hermes_cli/web_server.py:10942:@app.post("/api/providers/oauth/{provider_id}/start")
./hermes_cli/web_server.py:10980:@app.post("/api/providers/oauth/{provider_id}/submit")
./hermes_cli/web_server.py:10996:@app.get("/api/providers/oauth/{provider_id}/poll/{session_id}")
./hermes_cli/web_server.py:11022:@app.delete("/api/providers/oauth/sessions/{session_id}")
```

排除项:`tests/`(测试不注册生产路由);`web/`、`apps/desktop/`(前端 TS,不注册
后端路由)。搜索模式覆盖了单双引号两种字面量写法与 `@router`/`@app` 两种装饰器。

**结论**:`/api/providers/oauth` 只有 **6 条路由**——list / disconnect / start /
submit / poll / cancel,**没有 callback**。全仓 Python 里唯一的 OAuth 回调路由是
MCP 那一条(`hermes_cli/web_routers/mcp.py:276`)。

**那 PKCE 的授权码怎么回来的?靠人手动粘贴。** redirect_uri 指向的是
**Anthropic 自己托管的页面**,不是 Hermes 的任何端点:

`agent/anthropic_adapter.py:1482`

```
_OAUTH_REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
```

`hermes_cli/web_server.py:10049`

```
#   PKCE (Anthropic):
#     1. POST /api/providers/oauth/anthropic/start
#          → server generates code_verifier + challenge, builds claude.ai
#            authorize URL, stashes verifier in _oauth_sessions[session_id]
#          → returns { session_id, flow: "pkce", auth_url }
#     2. UI opens auth_url in a new tab. User authorizes, copies code.
#     3. POST /api/providers/oauth/anthropic/submit { session_id, code }
```

**所以"防止别人伪造回调"这个问题的答案是:不存在可被伪造的回调面。**
授权码通过**已鉴权的 POST /submit** 进入系统,而不是通过一个必须对公网开放的
GET 回调。这个设计选择本身就消掉了整类回调伪造/CSRF 攻击。

```text
MCP OAuth                              Provider OAuth
------------------------------------   ------------------------------------
有 GET 回调端点,必须免鉴权             无回调端点
(浏览器重定向不会带 session cookie
 到一个任意路径 —— 所以必须开口子)

防伪靠:URL 里的 server_name +          防伪靠:① POST /submit 走完整
        flow 表内的一次性 state                dashboard 鉴权(_require_token)
                                              ② session_id 128 bit 不可枚举
                                              ③ PKCE:verifier 只在服务端,
                                                 攻击者的码换不出 token
```

**但这里有一个真实缺陷。**

### 4.5 ■ 缺陷:dashboard PKCE 既不校验 state,又把 verifier 当 state 发出去

**证据一:start 把 `state` 直接设成 `verifier`。**

`hermes_cli/web_server.py:10213`

```
def _start_anthropic_pkce(profile: Optional[str] = None) -> Dict[str, Any]:
    """Begin PKCE flow. Returns the auth URL the UI should open."""
    if not _ANTHROPIC_OAUTH_AVAILABLE:
        raise HTTPException(status_code=501, detail="Anthropic OAuth not available (missing adapter)")
    verifier, challenge = _generate_pkce_pair()
    sid, sess = _new_oauth_session("anthropic", "pkce", profile=profile)
    sess["verifier"] = verifier
    sess["state"] = verifier  # Anthropic round-trips verifier as state
    params = {
        "code": "true",
        "client_id": _ANTHROPIC_OAUTH_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": _ANTHROPIC_OAUTH_REDIRECT_URI,
        "scope": _ANTHROPIC_OAUTH_SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": verifier,
    }
```

**证据二:submit 收到用户粘贴的 state 后,原样转发,从不比对。**

`hermes_cli/web_server.py:10253`

```
    # Anthropic's redirect callback page formats the code as `<code>#<state>`.
    # Strip the state suffix if present (we already have the verifier server-side).
    parts = code_input.strip().split("#", 1)
    code = parts[0].strip()
    if not code:
        return {"ok": False, "status": "error", "message": "No code provided"}
    state_from_callback = parts[1] if len(parts) > 1 else ""

    exchange_data = json.dumps({
        "grant_type": "authorization_code",
        "client_id": _ANTHROPIC_OAUTH_CLIENT_ID,
        "code": code,
        "state": state_from_callback or sess["state"],
        "redirect_uri": _ANTHROPIC_OAUTH_REDIRECT_URI,
```

**搜索面**:在 `hermes_cli/web_server.py` 全文 grep `state_from_callback` 与
`!= sess["state"]` / `== sess["state"]`,**`state_from_callback` 只出现两次**
——`:10259` 赋值、`:10265` 透传;**没有任何相等性比较**。

**证据三:同一个仓库的 CLI 实现做了这个校验,而且用的是独立随机 state。**

`agent/anthropic_adapter.py:1507`

```
    verifier, challenge = _generate_pkce()
    oauth_state = secrets.token_urlsafe(32)
```

`agent/anthropic_adapter.py:1561`

```
    received_state = splits[1] if len(splits) > 1 else ""

    # Validate state to prevent CSRF (RFC 6749 §10.12)
    if received_state != oauth_state:
        logger.warning("OAuth state mismatch — possible CSRF, aborting")
        return None
```

**这条对照是本缺陷的关键**:CLI 用 `secrets.token_urlsafe(32)` 生成一个**与
verifier 无关**的随机 state,并且**严格比对**。CLI 这条路是出厂即用的,说明
Anthropic 的授权端点**并不要求** `state == verifier`。因此 dashboard 里
`sess["state"] = verifier` 这行注释所称的 "Anthropic round-trips verifier as state"
描述的是 Hermes 自己的选择,而不是 provider 的要求。

**失效链(两条,分开评估严重度):**

```text
链 A —— state 未校验(严重度:中低,PKCE 兜住了)
  1. 攻击者用自己的 Anthropic 账号跑一遍授权,拿到 code_A#state_A
  2. 社工诱使运维在 dashboard 的 PKCE 弹窗里粘贴 code_A#state_A
  3. dashboard 不比对 state,直接用 (code_A, verifier_受害者) 去换 token
  4. → Anthropic 端拒绝(code_A 绑定的是攻击者的 challenge)
  结论:PKCE 的 verifier 绑定救了它,不构成账号注入。
        但 RFC 6749 §10.12 要求的这层纵深防御在 dashboard 路径上是**缺失的**,
        而同仓 CLI 有。任何未来削弱 verifier 绑定的改动(例如为了兼容某个
        provider 而放宽)都会让这条链立刻变成可用攻击。

链 B —— verifier 被当作 state 发进 URL(严重度:中,这是 PKCE 语义的实质降级)
  1. start 把 verifier 塞进 authorize URL 的 state 查询参数(:10222)
  2. 于是 verifier 出现在:浏览器地址栏、浏览器历史、可能的 Referer、
     以及 Anthropic 回调页上显示给用户的那串 `<code>#<state>` 文本里
  3. 用户复制的那一整串 `code#state`,内容等价于 `授权码 + code_verifier`
  4. → 这串文本本身就是一份**自洽的完整凭据**:任何拿到它的人(截图、
     剪贴板嗅探、聊天里贴错窗口、肩窥)都可以在**任意机器上**换出受害者的
     Anthropic token,不需要接触 Hermes
  结论:PKCE 的设计目的正是"授权码泄露也换不到 token",前提是 verifier 保密。
        把 verifier 放进 URL 与用户可见文本,等于把这个前提撤掉,
        PKCE 退化成裸授权码流程。CLI 不存在此问题(state 是独立随机数)。
```

**修法(两行):** `sess["state"] = secrets.token_urlsafe(32)`(与 verifier 解耦),
并在 `:10265` 之前加 `if state_from_callback and state_from_callback != sess["state"]: return error`。
两处都可直接照抄 `agent/anthropic_adapter.py:1507` 与 `:1563`。

**测试覆盖情况(取证)**:`tests/hermes_cli/test_web_oauth_dispatch.py` 的 15 个用例里
**没有一个断言 state 行为**(用例清单见第 8 节);`tests/hermes_cli/test_anthropic_oauth_flow.py`
全文 grep `state` **零命中**。即 CLI 那条 CSRF 校验本身也没有测试钉住。

**记 ■**,失效链如上。

### 4.6 device-code:取消与保存的原子性(一条做得很好的设计)

device-code 的 token 是**后台线程**拿到并保存的,而用户可以随时点"取消"。
朴素实现(先查 cancelled、再保存)有窗口:

`hermes_cli/web_server.py:11028`

```
    """Cancel a pending OAuth session. Token-protected.

    Marks the session dict ``cancelled`` before popping it so any
    background worker still holding a reference to that same dict (e.g.
    the Codex device-code poller) observes the cancellation and stops
    polling/exchanging/saving instead of completing the login after the
    user believed it was aborted.
    """
    _require_token(request)
    with _oauth_sessions_lock:
        sess = _oauth_sessions.get(session_id)
        if sess is not None:
            sess["cancelled"] = True
        _oauth_sessions.pop(session_id, None)
```

两个要点:
1. **先置标志再 pop**。如果直接 pop,后台线程手里那个 dict 引用仍然有效,
   它永远读不到 cancelled,会照常把 token 存下去。
2. **worker 侧把"查标志"和"保存"放进同一个临界区**,用的是同一把锁:

`hermes_cli/web_server.py:10914`

```
        # The cancellation check and the save must be one atomic critical
        # section under the same lock cancel_oauth_session() uses. Checking
        # "cancelled" and then saving as two separate steps left a window
        # where DELETE could flip the flag between them and the worker would
        # still persist tokens after the user believed the login was
        # aborted. Holding the lock across both closes that window: DELETE
        # either lands before this section (worker observes cancelled and
        # returns) or blocks until this section (and the save) is done.
        with _oauth_sessions_lock:
            if sess.get("cancelled"):
                _log.info("oauth/device: openai-codex login cancelled before token save (session=%s)", session_id)
                return
            with _profile_scope(session_profile):
                _save_codex_tokens({
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                })
            sess["status"] = "approved"
```

两条测试把这两点分别钉死(见第 8 节的
`test_cancel_oauth_session_marks_dict_cancelled_before_popping` 与
`test_codex_worker_final_save_is_atomic_with_cancel_delete`)。

> **可迁移原则**:"用户取消"与"后台完成"是一对经典竞态。仅仅从注册表里
> 移除任务是不够的——**后台已持有的引用不会因此失效**。必须(a)在移除前
> 打标志,(b)让后台的"检查 + 提交副作用"共用同一把锁。

### 4.7 poll 端点的"no auth"是什么意思

`hermes_cli/web_server.py:10996`

```
@app.get("/api/providers/oauth/{provider_id}/poll/{session_id}")
async def poll_oauth_session(
    provider_id: str,
    session_id: str,
    profile: Optional[str] = None,
):
    """Poll a session's status (no auth — read-only state).
```

**这句 docstring 容易被误读,必须澄清**。它的意思是"**没有额外的 `_require_token`**",
不是"任何人都能访问"。start / submit / cancel 三个端点都显式调 `_require_token`,
poll 没有。但 poll 的路径以 `/api/` 开头,不在 `PUBLIC_API_PATHS` 里,也不匹配
MCP 回调前缀,所以**仍然被通用的 cookie/session 中间件挡着**(`:665`,见 4.4 引文)。

**取证**:`PUBLIC_API_PATHS` 是精确路径的 frozenset(不是前缀匹配),共 8 条:

`hermes_cli/dashboard_auth/public_paths.py:33`

```
PUBLIC_API_PATHS: frozenset[str] = frozenset({
```

内容为 `/api/health`、`/api/status`、`/api/config/defaults`、`/api/config/schema`、
`/api/model/info`、`/api/dashboard/themes`、`/api/dashboard/plugins`、`/api/cron/fire`
——**不含任何 `/api/providers/oauth/*`**。

另外 poll 的返回体只有 `session_id / status / error_message / expires_at`
(`:11014`),**不含任何 token**,所以即使泄露也无凭据价值。**记 ◎**:注释保守/
措辞误导,但行为是安全的。

---

## 5. 凭据落盘

### 5.1 Anthropic PKCE:写两处,权限 0600,原子写

`hermes_cli/web_server.py:10156`

```
def _save_anthropic_oauth_creds(access_token: str, refresh_token: str, expires_at_ms: int) -> None:
    """Persist Anthropic PKCE creds to both Hermes file AND credential pool.

    Mirrors what auth_commands.add_command does so the dashboard flow leaves
    the system in the same state as ``hermes auth add anthropic``.
    """
```

**目标文件**:

`agent/anthropic_adapter.py:1484`

```
def _get_hermes_oauth_file() -> Path:
    return get_hermes_home() / ".anthropic_oauth.json"
```

即 `~/.hermes/.anthropic_oauth.json`(profile 模式下随 `get_hermes_home()` 重定向)。

**权限与原子性 —— 这里修过一个 TOCTOU:**

`hermes_cli/web_server.py:10169`

```
    # atomic_json_write creates the temp with mode 0o600 (via mkstemp) *before*
    # any content is written, then fsyncs and atomically replaces the target.
    # The previous os.replace + post-hoc chmod left a TOCTOU window in which the
    # OAuth token file was world-readable at the default umask (0o644 on most
    # hosts) between the rename and the chmod. atomic_json_write also preserves
    # the existing file's owner and cleans up its temp on failure.
    from utils import atomic_json_write

    atomic_json_write(oauth_file, payload, indent=2, mode=0o600)
```

**失效链(旧写法)**:`os.replace(tmp, target)` 之后再 `chmod(0o600)`。两步之间
文件已经就位、但权限是 umask 决定的(多数主机 0o644 = **全局可读**)。同机器上
任何本地用户在这个窗口里读一次,就拿到了 access_token + refresh_token。
新写法用 `mkstemp` 在**写入任何内容之前**就把临时文件建成 0600,再原子 rename,
窗口消失。

**这条被两个测试同时钉死**(`tests/hermes_cli/test_web_server_oauth_write.py:27` 与 `:39`),
第二个测试连"必须走 atomic_json_write 且 mode=0o600"这个**实现手段**都断言了,
防止有人改回 chmod 写法却仍然让第一个测试通过:

`tests/hermes_cli/test_web_server_oauth_write.py:39`

```
def test_dashboard_oauth_write_uses_atomic_json_write_with_owner_only_mode(oauth_file, monkeypatch):
    """The OAuth token file must be written 0o600 from creation via
    ``atomic_json_write(mode=0o600)``, so it is never briefly world-readable
    (the old ``os.replace`` + post-hoc ``chmod`` TOCTOU)."""
```

> **可迁移原则**:凡是"写敏感文件"的路径,测试不能只断言最终 mode,还要断言
> **写入手段**。最终 mode 正确的实现里,有一半存在中间窗口。

**第二处落点:credential pool**,尽力而为、失败不影响文件写:

`hermes_cli/web_server.py:10178`

```
    # Best-effort credential-pool insert. Failure here doesn't invalidate
    # the file write — pool registration only matters for the rotation
    # strategy, not for runtime credential resolution.
```

`hermes_cli/web_server.py:10197`

```
        entry = PooledCredential(
            provider="anthropic",
            id=uuid.uuid4().hex[:6],
            label="dashboard PKCE",
            auth_type=AUTH_TYPE_OAUTH,
            priority=0,
            source=f"{SOURCE_MANUAL}:dashboard_pkce",
```

`source` 打上 `manual:dashboard_pkce` 标记,并在插入前先删掉旧的同源条目
(`:10186`),保证 dashboard 反复登录不会堆出一串重复条目。

### 5.2 和 `hermes_cli/auth.py` 的 CLI 登录是同一个存储吗?

**答:对 Anthropic 而言是"两个文件、一个共享的第二存储",不是两套独立体系。**

```text
存储 A  ~/.hermes/.anthropic_oauth.json
        由 agent/anthropic_adapter.py:1484 _get_hermes_oauth_file() 定义
        写者:dashboard 的 _save_anthropic_oauth_creds(hermes_cli/web_server.py:10177)
              CLI 的 run_hermes_oauth_login_pure(agent/anthropic_adapter.py:1501)经
              auth_commands.add_command 落盘
        —— 同一个文件,同一个 helper。**同一存储。**

存储 B  ~/.hermes/auth.json 的 credential_pool 段
        读:hermes_cli/auth.py:1536 read_credential_pool
        agent/credential_pool.load_pool(provider) 是它的对象层封装
        dashboard 与 CLI 都往这里插条目。**同一存储。**

存储 C  ~/.hermes/auth.json 的 providers 段(单例态)
        device-code 系(nous / codex / xai / minimax)的 token 落在这里
        dashboard 的 poller 调的就是 CLI 自己的 persist 函数:
          nous  → persist_nous_credentials     (hermes_cli/web_server.py:10584)
          xai   → _save_xai_oauth_tokens       (hermes_cli/web_server.py:10719)
          codex → _save_codex_tokens           (hermes_cli/web_server.py:10927)
        **同一存储,而且是直接复用 CLI 的写函数。**
```

`hermes_cli/web_server.py:10159`

```
    Mirrors what auth_commands.add_command does so the dashboard flow leaves
    the system in the same state as ``hermes auth add anthropic``.
```

**结论:不是两套存储,是刻意做的"同态"——dashboard 的每条登录路径都调用 CLI
已有的持久化函数,目标是让 GUI 登录后的系统状态与 `hermes auth add` 完全一致。**
所以这里**不记 ◇ 也不记 ■**。

一处值得记的**反向约束**(xAI 分支):dashboard **故意不**往 pool 里额外插条目:

`hermes_cli/web_server.py:10731`

```
            # The singleton write above is the single source of truth: the
            # credential-pool load seeds it as the canonical ``device_code``
            # entry. Do NOT also insert a parallel ``manual:dashboard_*`` pool
            # entry — that duplicates the single-use refresh token across two
            # entries and triggers rotation churn / ``refresh_token_reused``.
```

**失效链**:OAuth refresh token 多数是**一次性**的(用一次就轮换)。同一个
refresh token 存在两个 pool 条目里,两个条目各自去刷新,第二个必然拿到
`refresh_token_reused` 错误,表现为随机的认证失败。所以 xAI 只写单例、让
pool 自己 seed。**这与 Anthropic 分支(既写文件又插 pool)的差异是有意的**,
因为 Anthropic 的 pool 条目是 `manual:dashboard_pkce` 且插入前先删同源旧条目。

### 5.3 ▲ 一处代码内部的注释与代码冲突(与 disconnect 相关)

`agent/credential_sources.py:289`

```
    """Codex tokens live in TWO places: our auth store AND ~/.codex/auth.json.

    refresh_codex_oauth_pure() writes both every time, so clearing only
    the Hermes auth store is not enough — _seed_from_singletons() would
    re-import from ~/.codex/auth.json on the next load_pool() call and
    the removal would be instantly undone.  We suppress instead of
    deleting Codex CLI's file, so the Codex CLI itself keeps working.
```

但 `_seed_from_singletons` 的 codex 分支明写它**不**从 `~/.codex/auth.json` 导入:

`agent/credential_pool.py:2764`

```
        # Hermes owns its own Codex auth state — we do NOT auto-import from
        # ~/.codex/auth.json at pool-load time.  OAuth refresh tokens are
        # single-use, so sharing them with Codex CLI / VS Code causes
        # refresh_token_reused race failures.  Users who want to adopt
        # existing Codex CLI credentials get a one-time, explicit prompt
        # via `hermes auth openai-codex`.
        if isinstance(tokens, dict) and tokens.get("access_token"):
```

**记 ▲**:`agent/credential_sources.py:291-293` 描述的"会从 `~/.codex/auth.json` 重新导入"
这一行为在 `agent/credential_pool.py:2764-2769` 已被明确取消(理由正是 refresh token
一次性)。该 docstring 是**过时的**,它为 suppression 给出的理由已不成立
(suppression 本身仍有用——它挡的是 `auth.json` 单例的重新 seed,见
`agent/credential_pool.py:2757`——但 docstring 说的挡的是**另一件事**)。
这不影响运行时正确性,但会误导读代码的人去 `~/.codex/auth.json` 找残留。
**以代码为准。**

---

## 6. disconnect 做得干净吗?

### 6.1 三层拦截,再删

`hermes_cli/web_server.py:9975`

```
@app.delete("/api/providers/oauth/{provider_id}")
async def disconnect_oauth_provider(
    provider_id: str,
    request: Request,
    profile: Optional[str] = None,
):
    """Disconnect an OAuth provider. Token-protected (matches /env/reveal)."""
    _require_token(request)
```

拦截逻辑集中在这个函数:

`hermes_cli/web_server.py:9869`

```
def _oauth_provider_disconnect_hint(provider: Dict[str, Any], status: Dict[str, Any]) -> Optional[str]:
    """Return the manual disconnect path when the API cannot clear this provider."""
    if provider.get("flow") == "external":
        if _oauth_provider_disconnect_command(provider):
            # The GUI offers a one-click "run in terminal" path; this hint is the
            # fallback wording for surfaces that only show text.
            return "Managed outside Hermes — run the disconnect command to remove it."
        return "Managed by that provider's CLI; remove it there."
    if status.get("source") == "env_var":
        return "Remove the API key from Settings → Keys instead."
    return None
```

```text
拦截 1  flow == "external"  → 400 拒绝
        (qwen-oauth / copilot-acp / claude-code / 所有目录派生的 external 卡片)
        理由见 :9846 —— "we never delete files another CLI owns on the
        user's behalf via a silent API call"
        补偿:对 claude-code 给出可在内嵌终端里**由用户亲眼看着执行**的命令
              (:9861,macOS 还带 Keychain 条目删除)

拦截 2  status.source == "env_var" → 400 拒绝,引导去 Settings → Keys
        (这一条很重要,见 6.3)

拦截 3  上面两条各判两次:一次用空 status(便宜、先挡 external),
        一次用真实 status(:9998 与 :10005)。先挡再算状态,
        避免为一个注定被拒的请求去做昂贵的状态探测。
```

### 6.2 真删的两条路径

`hermes_cli/web_server.py:10011`

```
        # above so we never pretend to remove ~/.claude/* credentials owned by the CLI.
        if provider_id == "anthropic":
            cleared = False
            try:
                from agent.anthropic_adapter import _get_hermes_oauth_file
                oauth_file = _get_hermes_oauth_file()
                if oauth_file.exists():
                    oauth_file.unlink()
                    cleared = True
            except Exception:
                pass
            # Also clear the credential pool entry if present.
            try:
                from hermes_cli.auth import clear_provider_auth
                cleared = clear_provider_auth("anthropic") or cleared
            except Exception:
                pass
            _log.info("oauth/disconnect: %s", provider_id)
            return {"ok": bool(cleared), "provider": provider_id}
```

`clear_provider_auth` 做的是**真删,不是删引用**:

`hermes_cli/auth.py:1920`

```
        cleared = False
        if target in providers:
            del providers[target]
            cleared = True
        if target in pool:
            del pool[target]
            cleared = True

        if auth_store.get("active_provider") == target:
            auth_store["active_provider"] = None
            cleared = True

        if not cleared:
            return False
        _save_auth_store(auth_store)
    return True
```

`del providers[target]` 与 `del pool[target]` 都是从 dict 里整块删除后重写
`auth.json`——token 字面量不再出现在文件里。**不是只清引用。**

**覆盖面盘点(anthropic)**:

```text
~/.hermes/.anthropic_oauth.json          ✔ unlink
auth.json providers["anthropic"]         ✔ del
auth.json credential_pool["anthropic"]   ✔ del(含 manual:dashboard_pkce 条目)
~/.claude/.credentials.json              ✘ 故意不动 —— 它是 claude-code 那张
                                            external 卡片的领地,已被拦截 1 挡住
环境变量 ANTHROPIC_API_KEY 等            ✘ 故意不动 —— 被拦截 2 挡住,引导去 Keys 页
```

**结论:在它声明的职责范围内是干净的**,没有"删了引用留了 token"的情况。
边界之外的两处都**先拒绝再解释**,而不是假装删掉。

### 6.3 残留搜索:我搜了什么、排除了什么

```text
搜索面
  1. grep -rn "clear_provider_auth" --include=*.py .
     → 生产代码调用点仅 3 处:hermes_cli/web_server.py:10025(anthropic 分支)、
       hermes_cli/web_server.py:10033(通用分支)、tui_gateway/methods_complete.py:464
       + 定义处 hermes_cli/auth.py:1898 + 内部调用 hermes_cli/auth.py:9229
  2. 追 clear_provider_auth 的删除范围 → hermes_cli/auth.py:1920-1935(上引)
  3. 追 pool 的实际后备存储:agent/credential_pool.load_pool
     → hermes_cli/auth.py:1536 read_credential_pool → auth.json 的
       credential_pool 段。**pool 不是独立文件**,所以 del pool[target] 即已覆盖。
  4. 追"删了会不会自己长回来":agent/credential_pool.py 的三处
     is_source_suppressed 门(:2461 _seed_from_singletons、
     :2878 _seed_from_env、:3018 _seed_custom_pool)
  5. 对照 CLI 的 remove 路径:hermes_cli/auth_commands.py:485-497
     + agent/credential_sources.py 的 RemovalStep 注册表(:387-438)

排除项
  - tests/ 下的调用(不影响运行时残留)
  - MCP OAuth 的 token 存储(另一子系统,R6 已覆盖)
  - ~/.claude/、~/.codex/、~/.qwen/ 等第三方 CLI 自有文件
    —— 代码**明确声明不碰**,不算 Hermes 的残留
```

**发现的两条不对称,都不构成"token 没删干净",但值得移交:**

**◇ 不对称一:dashboard disconnect 不写 suppression,CLI remove 写。**

CLI 的 `hermes auth remove` 走 RemovalStep 注册表,统一做"源特定清理 + 抑制":

`hermes_cli/auth_commands.py:484`

```
    from agent.credential_sources import find_removal_step
    from hermes_cli.auth import suppress_credential_source

    step = find_removal_step(provider, removed.source)
    if step is None:
        # Unregistered source — e.g. "manual", which has nothing external
        # to clean up.  The pool entry is already gone; we're done.
        return

    result = step.remove_fn(provider, removed)
    for line in result.cleaned:
        print(line)
    if result.suppress:
        suppress_credential_source(provider, removed.source)
```

dashboard 的 disconnect(`:10032`)**只调 `clear_provider_auth`,不调
`find_removal_step`,也不调 `suppress_credential_source`**。

**这在当前代码下不导致 token 复活**,因为 device-code 系(nous/codex/xai/minimax)
的 seed 源就是 `auth.json` 的 providers 段,而它已被 `clear_provider_auth` 删掉;
env 系被拦截 2 挡在门外。所以**记 ◇ 不记 ■**。但这是一条**脆弱的对称性**:
一旦将来有 provider 新增一个外部 seed 源(像 codex 曾经那样),CLI 会因为
suppression 而正确,dashboard 会因为没有 suppression 而"点了断开,下次 load_pool
又回来了"。这条不对称没有任何测试守护。

**◇ 不对称二:profile 作用域下的断开可能是无效操作,且不解释原因。**

`clear_provider_auth` 读写的是**当前作用域**的 auth.json(`_load_auth_store()`
→ `_auth_file_path()`),而**状态读取**有一条 global-root 回落:

`hermes_cli/auth.py:1539`

```
    In profile mode, the profile's credential pool is authoritative. If a
    provider has no entries in the profile, entries from the global-root
    ``auth.json`` are used as a read-only fallback — so workers spawned in a
    profile can see providers that were only authenticated at global scope.
```

**推演**(未实跑,因为需要构造 profile + 全局双存储):

```text
前提:凭据只在 global root 认证过,用户在 profile=work 的 dashboard 里点断开
1. DELETE /api/providers/oauth/nous?profile=work
2. _profile_scope("work") → clear_provider_auth("nous") 读 work 的 auth.json
3. work 里没有 providers["nous"]、没有 credential_pool["nous"]、
   active_provider 也不是 nous  → 三个分支都不命中
4. hermes_cli/auth.py:1932 `if not cleared: return False`
5. 端点返回 {"ok": false, "provider": "nous"},**没有任何 message/hint**
6. 列表刷新时状态仍是 logged_in=True(读走了 global 回落)
用户看到:点了断开,没报错,provider 还连着,没有任何解释。
```

行为上是**安全的**(它没撒谎说成功了),但 `{"ok": false}` 不带原因,与
拦截 1 / 拦截 2 那种"400 + 明确 hint"的体验完全不同。**记 ◇**,并作为移交项。

---

## 7. 记号汇总

```text
号  位置                                        一句话
--------------------------------------------------------------------------------
■   hermes_cli/web_server.py:10220 + :10265     dashboard PKCE 把 code_verifier
                                                当 state 发进 authorize URL,且
                                                提交时从不比对 state;同仓 CLI
                                                (agent/anthropic_adapter.py:1508/:1563)
                                                用独立随机 state 并严格比对。
                                                失效链见 4.5(链 A 中低、链 B 中)。
▲   hermes_cli/web_server.py:10075              注释称会话 "time out after 15
                                                minutes",但唯一的 GC 只在
                                                /start 时触发(:10950 是
                                                _gc_oauth_sessions 的唯一调用点),
                                                submit/poll 无任何时效校验。
▲   agent/credential_sources.py:291             docstring 称 _seed_from_singletons
                                                会从 ~/.codex/auth.json 重新导入,
                                                但 agent/credential_pool.py:2764 明写
                                                "we do NOT auto-import"。以代码为准。
◇   hermes_cli/web_server.py:6248               "Model assignment" 横幅名义罩住
                                                6249–9503 约 3250 行,实际相关
                                                只有约 540 行,中间是 env /
                                                custom endpoints / messaging。
◇   hermes_cli/web_server.py:6253               _AUX_TASK_SLOTS 是
                                                DEFAULT_CONFIG["auxiliary"] 的
                                                手工副本,注释写了 "Keep in sync"
                                                但无任何测试强制一致。
◇   hermes_cli/web_server.py:10130              OAuth 会话是无 schema 的
                                                Dict[str, Any],各 provider 分支
                                                自定字段名(anthropic 用
                                                "verifier",minimax 用
                                                "code_verifier",:10460),拼错只在
                                                poller 里 KeyError。
◇   hermes_cli/web_server.py:10032              dashboard disconnect 不走
                                                RemovalStep、不写 suppression;
                                                CLI 的 auth remove 两者都做
                                                (hermes_cli/auth_commands.py:487)。当前不
                                                致 token 复活,但对称性无测试守护。
◇   hermes_cli/web_server.py:10038              profile 作用域下断开一条只存在于
                                                global-root 的凭据,返回
                                                {"ok": false} 且不带任何原因,
                                                UI 仍显示已连接。
◎   hermes_cli/web_server.py:9509               Phase 1 注释称登录 "still runs in
                                                the CLI for now",Phase 2 已把
                                                PKCE 与四家 device-code 搬进来;
                                                注释保守未更新,不构成错误。
◎   hermes_cli/web_server.py:11002              poll 的 "no auth" 指的是"没有额外
                                                的 _require_token",通用 session
                                                中间件仍然拦着(它不在
                                                PUBLIC_API_PATHS 的 8 条里),
                                                且返回体不含 token。措辞误导、
                                                行为安全。
```

---

## 8. 测试作为行为规格

### 8.1 实跑报数

按任务要求的方式自找测试文件:

```console
$ ls tests/hermes_cli | grep -iE "oauth|model|anthropic|copilot|minimax"
（67 个文件)
```

**第一批:直接命中本段符号的 10 个文件**(用
`grep -rln "api/providers/oauth|_start_anthropic_pkce|_submit_anthropic_pkce|_start_device_code_flow|disconnect_oauth_provider|_oauth_sessions|_save_anthropic_oauth_creds"`
与 `grep -rln "api/model/set|_apply_model_assignment_sync|_normalize_main_model_assignment|_apply_main_model_assignment|api/model/options|api/model/auxiliary|api/model/moa|recommended-default"` 反查得到):

```console
$ cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
    bash scripts/run_tests.sh \
    tests/hermes_cli/test_web_oauth_dispatch.py \
    tests/hermes_cli/test_web_server_oauth_write.py \
    tests/hermes_cli/test_dashboard_oauth_endpoints_server_gate.py \
    tests/hermes_cli/test_dashboard_auth_middleware.py \
    tests/hermes_cli/test_provider_parity.py \
    tests/hermes_cli/test_normalize_main_model_assignment.py \
    tests/hermes_cli/test_main_model_custom_provider_normalization.py \
    tests/hermes_cli/test_moa_set_models_preserves_extra_keys.py \
    tests/hermes_cli/test_web_server.py \
    tests/hermes_cli/test_web_server_profile_unification.py

=== Summary: 10 files, 195 tests passed, 0 failed (100% complete) in 11.9s (8 workers) ===
```

**第二批:任务指定的整个 grep 清单(67 个文件)**:

```console
$ FILES=$(ls tests/hermes_cli/*.py | grep -iE "oauth|model|anthropic|copilot|minimax")
$ HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh $FILES

Discovered 67 test files (~375 tests)
=== Summary: 67 files, 413 tests passed, 0 failed (100% complete) in 16.2s (8 workers) ===
```

```text
报数汇总(环境:venv 91 包 — 注意与 CLAUDE.md 记录的 R8B 87 包不同)
  第一批  10 文件 / 195 用例 / 0 失败
  第二批  67 文件 / 413 用例 / 0 失败(含第一批中的 7 个)
  容器已知限制(无 IPv6 / root / 离线)在本批文件里**一个都没触发**。
```

### 8.2 `test_web_oauth_dispatch.py` 的 15 条用例读作行为规格

```text
用例(tests/hermes_cli/test_web_oauth_dispatch.py)                        钉住的是
--------------------------------------------------------------------------------
:71  test_minimax_login_does_not_launch_anthropic_flow                    pkce 分派必须
     ← 对应 hermes_cli/web_server.py:10963 的注释:pkce 分支硬绑 provider_id ==      按 id 显式白名单
       "anthropic",任何未来标 pkce 的新 provider 若不加显式分支,
       会**静默跑起 Anthropic 的授权流程**(这正是给 MiniMax 修的 bug)
:113 test_oauth_provider_status_uses_profile_query                        状态读走 profile
:140 test_oauth_start_stores_profile_for_background_completion            后台线程写回正确 profile
:176 test_codex_dashboard_start_rewords_device_authorization_error        错误文案整形
:226 test_codex_dashboard_worker_stops_polling_after_cancel               取消后停轮询
:297 test_codex_worker_final_save_is_atomic_with_cancel_delete            取消/保存原子性(4.6)
:399 test_cancel_oauth_session_marks_dict_cancelled_before_popping        先置标志再 pop(4.6)
:431 test_nous_dashboard_poller_preserves_effective_scope_when_token_
     omits_scope                                                          scope 回填
:483 test_xai_oauth_listed_as_device_code_flow                            目录元数据
:493 test_accounts_offers_every_oauth_provider_from_catalog               并集成员完整性
:514 test_oauth_catalog_marks_external_providers_not_disconnectable       external 不可断开
:537 test_external_oauth_disconnect_rejected_before_auth_mutation         **拒绝必须发生在
                                                                          任何 auth 变更之前**
:552 test_env_sourced_oauth_status_is_not_disconnectable                  拦截 2(env_var)
:569 test_xai_dashboard_poller_seeds_single_entry_and_clears_suppression   单条目 + 解抑制(5.2)
:667 test_status_falls_through_to_generic_dispatcher_for_catalog_only_
     provider                                                             状态兜底分支(第 3 节)
```

`:537` 那条写法很讲究——它用"故意抛异常的假函数"来证明代码根本没走到那一步:

`tests/hermes_cli/test_web_oauth_dispatch.py:541`

```
    def fail_clear_provider_auth(provider_id=None):
        raise AssertionError("external providers must not reach clear_provider_auth")
```

> **可迁移原则**:要断言"某条路径没有被执行",把该路径上的函数替换成**会爆炸的
> 桩**,比事后检查状态更可靠——后者可能因为副作用恰好幂等而漏掉。

**空白点**:15 条里**没有一条覆盖 `state`**;`test_anthropic_oauth_flow.py` 全文
grep `state` 零命中。即第 4.5 节的 ■ 不但代码里没有校验,测试层也没有任何
守护(连 CLI 那条已存在的校验都没被钉住,可以被误删而不被发现)。

---

## 9. 基线只读边界复核

```console
$ git -C /home/user/hermes-agent rev-parse HEAD
863e31318553cda8ad61df681d08175364d4164b
$ git -C /home/user/hermes-agent status --porcelain
（空)
```

**一处需要交代的副作用(非违规)**:仓库自带的测试运行器
`scripts/run_tests.sh` 会写 `test_durations.json` 与各处 `__pycache__/`。
两者都在 `.gitignore` 里(`test_durations.json` 见 `.gitignore:35`),
`git status --porcelain` 为空,**没有任何被跟踪文件被改动**。这是仓库自身
设计的行为,不是本轮引入的污染。我全程未在基线目录下运行任何 npm / pip /
git checkout / git clean;所有临时文件写在 `/tmp` 下的 scratchpad。

---

## 10. 引用校验报数

```console
$ cd /home/user/hermes-study && python3 scripts/verify_citations.py \
    /home/user/hermes-agent notes/r8c-raw-model-oauth.md
citations=77  OK=59  UNCHECKED=18
可校验比例 OK/77 = 76.6%
OK: every code-block-backed citation matches the baseline
$ echo $?
0
```

```text
citations   77     全部 `路径:行号 @ 863e313` 引用
OK          59     带代码块、与基线逐字比对通过
UNCHECKED   18     散文中的路径:行号(无代码块),不计失败
可校验比例  76.6%  高于 70% 下限
```

**`--fix` 使用记录(按 CLAUDE.md 要求交代)**:首轮跑出 12 处 MISMATCH,
**全部是纯行号漂移**——校验器在邻近行找到了逐字相同的内容(偏移 1–6 行),
属"无歧义漂移",故用 `--fix` 修正后**不带 `--fix` 裸跑复核**,得到上面的
退出码 0 与 OK 行。

**⚠ 校验器本轮正在被并发修改(给下一轮的提醒)**:我的一次校验运行崩在
`NameError: name 'block_drift' is not defined`(`scripts/verify_citations.py:342`
调用了当时尚未写入的 `:148` 定义)。查证:`git status` 显示
`scripts/verify_citations.py` 为 `M`,mtime 距该次运行仅数秒——本轮有另一个
子代理正在给它加 `block_drift`(该函数的注释里自称 "(R8C)")。我随后**连跑三次
均 rc=0、数字一致**(76/59/17),故上面的报数有效;但**本轮任何"校验通过"的
结论都是对某一时刻的脚本版本而言的**,合稿时应在脚本定稿后统一重跑一遍全部
`notes/` 与 `chapters/`。

此外我手工复核了 17 条 UNCHECKED(散文型)锚点:逐条 `sed -n "${n}p"` 读出
目标行确认语义匹配,其中修正了 8 处漂移(`hermes_cli/web_server.py` 的
`10471→10448`、`10074→10075`、`6819→6829`、`10480→10465`、`10455→10460`、
`10514→10508`、`10921→10927`、`6716→6725`),并把 text 表格里的裸文件名
(`web_server.py:…`、`auth.py:…` 等)全部补全为可从基线仓库根解析的路径。

---

## 11. 本段未覆盖 / 存疑(移交项,每条带锚点 + 一句话现象)

1. **`_start_device_code_flow` 的 minimax 分支用了 `asyncio.get_event_loop()`
   而其余三家用 `get_running_loop()`**
   锚点:`hermes_cli/web_server.py:10448`
   现象:同一个函数里,nous(`:10360`)与 xai(`:10504`)写的是
   `asyncio.get_running_loop().run_in_executor(...)`,minimax 写的是
   `asyncio.get_event_loop().run_in_executor(...)`。`get_event_loop()` 在
   Python 3.12+ 的协程上下文里已产生 DeprecationWarning,3.14 起行为进一步收紧。
   未验证本仓库支持的 Python 版本下是否已告警——需要下一轮读 `pyproject.toml`
   的 `requires-python` 后判定是 ■ 还是无害不一致。

2. **`_codex_full_login_worker` 的 10 秒阻塞握手**
   锚点:`hermes_cli/web_server.py:10396`
   现象:codex 分支在 `/start` 里 `deadline = time.monotonic() + 10`,轮询
   `await asyncio.sleep(0.1)` 等后台线程回填 `user_code`,超时返回 504。
   注释自称原因是"没重构 auth.py 就没法只抽出 start 步骤"。未评估:并发多个
   codex 登录时这 10 秒会不会占满事件循环上的其它请求(它是 `await sleep`,
   理论上不阻塞,但每 100ms 抢一次 `_oauth_sessions_lock` 这把**同步锁**)。

3. **`_oauth_sessions` 是进程内单例,与多 worker 部署的兼容性**
   锚点:`hermes_cli/web_server.py:10075`
   现象:注释写 "Sessions are kept in-memory only (**single-process FastAPI**)"。
   未查证:dashboard 是否存在多 worker / 多进程的启动方式(如 uvicorn --workers
   或 gunicorn)。若存在,`/start` 与 `/submit` 落到不同进程会直接 404
   "Unknown or expired session"。需要下一轮读 dashboard 的启动路径确认。

4. **`_resolve_provider_status` 的 openai-codex 分支可能返回 `source="env_var"`**
   锚点:`hermes_cli/web_server.py:9769`
   现象:该分支写 `"source": raw.get("source") or "openai_codex"`,即 source
   来自 `hauth.get_codex_auth_status()` 的返回。若它能返回 `"env_var"`,
   则拦截 2(`:9877`)会把 codex 也判成不可断开。未追进
   `get_codex_auth_status` 确认其 source 取值域。

5. **`_denormalize_config_from_web` 与本段的 `_infer_provider_on_model_change`
   共用聚合器兜底语义**
   锚点:`hermes_cli/web_server.py:6829`
   现象:`_infer_provider_on_model_change` 在 `"/" in name` 且当前非聚合器时
   `return "openrouter", name`,注释明说这是"哨兵值,真正的聚合器由
   `_normalize_main_model_assignment` 解析"。也就是 Config 页的扁平 Model 字段
   与 Models 页的选择器**最终收口在同一个函数**。本段未验证 Config 页那条路径
   的完整走法(属另一段的 `PUT /api/config`),交叉点记在此供合稿时对齐。

6. **`_oauth_provider_disconnect_command` 只对 claude-code 生成命令**
   锚点:`hermes_cli/web_server.py:9861`
   现象:函数对 `flow == "external"` 的 provider 才返回命令,且只有
   `id == "claude-code"` 有实现,qwen-oauth / copilot-acp 一律返回 None
   → 走 "Managed by that provider's CLI; remove it there." 这句泛泛提示。
   未评估:qwen 的 `~/.qwen/oauth_creds.json` 有现成的 RemovalStep
   (`agent/credential_sources.py:425`),为什么 GUI 不复用它给出命令。

7. **MiniMax `expired_in` 的单位启发式**
   锚点:`hermes_cli/web_server.py:10465`
   现象:注释说 MiniMax 的 `expired_in` "could be a unix-ms timestamp OR a
   seconds-from-now duration",代码在 `:10471` 用 `> 1_000_000_000_000` 做阈值区分。
   该阈值对应 2001-09-09,作为"毫秒时间戳 vs 秒数"的判别是安全的,但这是
   provider 契约不清导致的猜测。未查证 `_minimax_poll_token` 里的同款启发式
   是否与此处完全一致(注释称 "Mirror the heuristic",未逐字比对)。
