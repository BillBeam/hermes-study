# R2-20 wire 协议适配器层(子代理底稿)

> 由子代理精读产出并经主线抽查(定案 a/b/c 与关键行号已复核)。基线 863e31318。
> 范围:anthropic/codex_responses/gemini_native/bedrock 四适配器 + vertex/azure/schema 清洗
> + api_mode 判定入口 + backend_identity(纠偏:非身份伪装,是故障域跳过判定)。

I now have complete coverage. Writing the L1 底稿.

---

# R2 底稿 · wire 协议适配器层机制簇（L1 精读）

**基线** `commit 863e31318553cda8ad61df681d08175364d4164b` @ NousResearch/hermes-agent（只读）
**一句话结论**：一个 `api_mode` 枚举把四种线协议分流到四套 adapter，请求出、响应归一都在 adapter 内闭环。

实测行数（`wc -l` @ 863e313）：

| 文件 | 行数 | 文件 | 行数 |
|---|---|---|---|
| agent/anthropic_adapter.py | 3177 | agent/vertex_adapter.py | 228 |
| agent/codex_responses_adapter.py | 1590 | agent/azure_identity_adapter.py | 571 |
| agent/gemini_native_adapter.py | 1127 | agent/gemini_schema.py | 140 |
| agent/bedrock_adapter.py | 1573 | agent/moonshot_schema.py | 269 |
| agent/backend_identity.py | 204 | agent/lmstudio_reasoning.py | 60 |
| hermes_cli/providers.py | 959 | providers/base.py | 238 |
| agent/chat_completion_helpers.py | 4363 | agent/transports/anthropic.py | 251 |
| agent/transports/codex.py | 672 | agent/transports/__init__.py | 68 |

> 术语纠偏（任务描述 ↔ 代码）：任务把 `backend_identity.py` 标为「身份伪装部分」。**这是误配**。`backend_identity.py` 讲的是"故障域 → 是否跳过同一后端候选"（fallback/dedup），与身份伪装无关。真正的**身份伪装（identity spoofing）在 `anthropic_adapter.py`**（伪装成 Claude Code：UA、system 前缀、`Nous Research`→`Anthropic`、`mcp__` 前缀）以及 codex 的 issuer 隔离。本底稿据此把 `backend_identity.py` 归到"取舍/边界工具"一节，身份伪装则在 Anthropic 一节详述。

---

## 1. 全景：api_mode 枚举、承接 adapter、统一分发点

### 1.1 枚举值（4 个真值）

线协议由字符串 `api_mode` 表达，权威映射表在 `hermes_cli/providers.py`：

`hermes_cli/providers.py:435 @ 863e313`
```python
TRANSPORT_TO_API_MODE: Dict[str, str] = {
    "openai_chat": "chat_completions",
    "anthropic_messages": "anthropic_messages",
    "codex_responses": "codex_responses",
    "bedrock_converse": "bedrock_converse",
}
```

四个真值及承接：

| api_mode | 线协议 | 承接 adapter | transport 包装 |
|---|---|---|---|
| `chat_completions` | OpenAI Chat Completions（默认）；Gemini native 是伪装在此模式下的 shim | `gemini_native_adapter.py`（native Gemini）、`gemini_schema.py`/`moonshot_schema.py`/`lmstudio_reasoning.py`（schema/effort 清洗）| `transports/chat_completions.py` |
| `anthropic_messages` | Anthropic Messages `/v1/messages` | `anthropic_adapter.py` | `transports/anthropic.py` |
| `codex_responses` | OpenAI Responses API（Codex/xAI/GitHub Copilot） | `codex_responses_adapter.py` | `transports/codex.py` |
| `bedrock_converse` | AWS Bedrock Converse（boto3，绕过 OpenAI client） | `bedrock_adapter.py` | `transports/bedrock.py` |

注意：`chat_completion_helpers.py:2687` 出现的 `"api_mode": "custom"` 只是 `relay_llm` 流式遥测的 metadata 标签，**不是**第五个分发值。

`agent/vertex_adapter.py` 与 `agent/azure_identity_adapter.py` **不是独立 api_mode**：Vertex 走 `openai_chat`（overlay `auth_type="vertex"`，只解决 OAuth2 取 token + base_url，见 `providers/base.py`），Azure Entra 走 `anthropic_messages`/`chat_completions` 之上的 bearer-hook。

### 1.2 两套 provider 元数据系统（易混）

- **`hermes_cli/providers.py`**：`ProviderDef` + `HermesOverlay`（`providers.py:34`/`:255`），叠在 models.dev 目录之上，字段 `transport`。这是 `determine_api_mode()` 用的老系统。
- **`providers/base.py` 的 `ProviderProfile`**（`providers/base.py:38`）：声明式 profile，字段 `api_mode: str = "chat_completions"`（`:44`），由 `plugins/model-providers/<name>/` 插件注册、`runtime_provider.get_provider_profile()` 消费。它还带请求期钩子：`prepare_messages`（`:117`）、`build_extra_body`（`:125`）、`build_api_kwargs_extras`（`:134`，用于 reasoning 配置放 extra_body 还是 top-level 的分叉）、`get_max_tokens`（`:167`）、`fetch_models`（`:181`）。两套系统的 `transport`/`api_mode` 字段语义等价，代码里并行存在。

### 1.3 统一分发点（"入口在哪"）

api_mode 分发落在 `chat_completion_helpers.py` 两处，都按 `agent.api_mode` if-else：

**(a) 构建请求 kwargs** — `build_api_kwargs(agent, api_messages, tools_for_api)`：

`agent/chat_completion_helpers.py:1157 @ 863e313`
```python
def build_api_kwargs(agent, api_messages: list, tools_for_api: list | None = None) -> dict:
    ...
    if agent.api_mode == "anthropic_messages":       # :1162
        _transport = agent._get_transport()
        ...
    if agent.api_mode == "bedrock_converse":         # :1192
    if agent.api_mode == "codex_responses":          # :1205
    # 落空 → OpenAI chat_completions 直接构 kwargs
```

**(b) 发起非流式请求** — `_dispatch_nonstreaming_api_request(agent, api_kwargs, make_client)`：

`agent/chat_completion_helpers.py:467 @ 863e313`
```python
    if agent.api_mode == "codex_responses":
        request_client = make_client("codex_stream_request")
        return agent._run_codex_stream(
            api_kwargs,
            client=request_client,
            on_first_delta=getattr(agent, "_codex_on_first_delta", None),
        )
    if agent.api_mode == "anthropic_messages":
        # #67142: use a request-local Anthropic client so the stale/interrupt
        # watchdog aborts sockets from the stranger thread while the worker
        # owns the SDK close — never closing the shared client mid-flight.
        request_client = make_client(
            "anthropic_messages_request", kind="anthropic_messages"
        )
        return agent._anthropic_messages_create(api_kwargs, client=request_client)
    if agent.api_mode == "bedrock_converse":
        ...
        client = _get_bedrock_runtime_client(region)
        raw_response = client.converse(**api_kwargs)
        return normalize_converse_response(raw_response)
    ...
    request_client = make_client("chat_completion_request")
    return request_client.chat.completions.create(**api_kwargs)
```

**(c) transport 注册表**：api_mode → transport 类的解析在 `agent/transports/__init__.py:26` `get_transport(api_mode)`，各 transport 模块 import 时自注册（`transports/anthropic.py:251 register_transport("anthropic_messages", ...)`）。agent 侧缓存入口 `run_agent.py:6652 _get_transport()`。transport 只做**格式转换 + 归一化**，不管 client 生命周期/流式（`transports/anthropic.py:1-5` 明说）。

一句话记法：**`determine_api_mode()`（解析期）定 mode → `_get_transport()` 取 transport → `build_api_kwargs()`（出方向）→ `_dispatch_*`（发请求）→ `transport.normalize_response()`（回方向归一为 `NormalizedResponse`/OpenAI 形状）**。`NormalizedResponse`/`ToolCall` 的共享形状定义在 `transports/types.py`，协议私有状态塞进 `provider_data`（如 Codex 的 `call_id`/`response_item_id`、Gemini 的 `thought_signature`）。

---

## 2. api_mode 判定入口（determine_api_mode）

`hermes_cli/providers.py:671-683 @ 863e313`，解析优先级（docstring 自己就把五级顺序写全了）：

```python
def determine_api_mode(provider: str, base_url: str = "", model: str = "") -> str:
    """Determine the API mode (wire protocol) for a provider/endpoint.

    Resolution order:
      1. Host-mandated mode (special endpoints that only accept one protocol).
      2. Nous Portal dual-wire (model-derived; overlay alone is openai_chat).
      3. Known provider → transport → TRANSPORT_TO_API_MODE.
      4. Direct provider checks (bedrock).
      5. Default: 'chat_completions'.

    *model* is optional but required for dual-wire providers (Nous) whose
    transport depends on the catalog id, not just the provider/host.
    """
```

函数体逐级落地（① host 强制）：

`hermes_cli/providers.py:684-686 @ 863e313`

```python
    mandated = host_mandated_api_mode(base_url)
    if mandated is not None:
        return mandated
```

② Nous 双线（注释解释了为什么必须在 transport 查表**之前**开这个口子）：

`hermes_cli/providers.py:688-694 @ 863e313`

```python
    # Nous is dual-wire: anthropic/* → Messages, everything else →
    # chat_completions. The Hermes overlay still advertises openai_chat
    # (the majority of the Portal catalog), so the transport lookup below
    # would pin Claude on the wrong wire without this carve-out.
    provider_norm = (provider or "").strip().lower()
    if provider_norm in {"nous", "nous-portal", "nousresearch"}:
        return nous_api_mode(model)
```

③ provider→transport→mode；④ bedrock 直判；⑤ 兜底：

`hermes_cli/providers.py:696-704 @ 863e313`

```python
    pdef = get_provider(provider)
    if pdef is not None:
        return TRANSPORT_TO_API_MODE.get(pdef.transport, "chat_completions")

    # Direct provider checks for providers not in HERMES_OVERLAYS
    if provider == "bedrock":
        return "bedrock_converse"

    return "chat_completions"
```

> **R11B 引用更正(片 D)**:原文此处是**一个**代码块,把 `determine_api_mode` 从 671 行到函数尾
> 压成 13 行、去掉了 docstring 与两段注释、并在行尾加了 `# 1. host 强制` 这类中文标注
> ——**它长得像逐字摘录,但不是**(签名还被去掉了类型标注,写成
> `def determine_api_mode(provider, base_url="", model="") -> str:`)。
> 现按制度「摘录要跳段时优先拆成两个各自带锚点的块」拆成四块,每块逐字对齐基线并各自受校验;
> 中文的五级标注移到块外的散文里。**结论实质不变**——五级顺序本来就是 docstring 自己写的。

**host 强制**（`providers.py:614 host_mandated_api_mode`）是"覆盖"而非"补空"——即使 session 携带过期的 `chat_completions`（如 `/model` 切换残留），命中的 host 也强制改写。用 hostname 精确匹配（非子串），防 `api.openai.com.attacker.test`（#32243）：
- `api.kimi.com` + 路径 `/coding` → `anthropic_messages`（`:637`）
- `api.anthropic.com` 或 URL 以 `/anthropic` 结尾 → `anthropic_messages`（`:639`）
- 官方 OpenAI host 家族（`is_official_openai_host`，含 `us./eu.api.openai.com`）→ `codex_responses`（`:645`）
- `bedrock-runtime.*.amazonaws.com` → `bedrock_converse`（`:647`）

---

## 3. Anthropic 适配器（agent/anthropic_adapter.py，3177 行）

模块自我定位：翻译内部 OpenAI 风格 ↔ Anthropic Messages，与 codex adapter 同构（`:1-11`）。这是**最重、机制最密**的 adapter。

### 3.1 请求方向翻译

**入口** `build_anthropic_kwargs()`（`:2808`），流水线：

1. `convert_messages_to_anthropic(messages, base_url, model)`（`:2742`）→ 返回 `(system, anthropic_messages)`。system 被抽成独立参数（Anthropic 用独立 `system` 字段，非 messages 内），带 `cache_control` 时保留为 block 列表（`:2764-2785`）。
2. 逐消息转换：
   - **assistant** `_convert_assistant_message`（`:2048`）：先看有没有 `anthropic_content_blocks`（交错签名 thinking + tool_use 的**逐字有序重放通道**，`:2064`），有则走 `_sanitize_replay_block` 剥离输出专属字段并**用已脱敏的 `tool_calls` 重新填 tool_use.input**（防把模型内联进 tool 参数的密钥重放上线，`:2077-2087`）；否则组装 thinking blocks + text + tool_use。
   - **tool** `_convert_tool_message_to_result`（`:2256`）→ Anthropic `tool_result`，连续 tool 结果合并进同一 user 消息（`:2306`）。
   - **user** `_convert_user_message`（`:2318`）。
3. 后处理 6 连（`:2798-2803`）：`_strip_orphaned_tool_blocks`（孤儿 tool_use/tool_result 剥离，Anthropic 要求 tool_use 的 result 必须在**紧邻的下一条** user 消息，`:2336`）→ `_merge_consecutive_roles`（强制 user/assistant 交替，`:2417`）→ `_ensure_leading_user_turn`（messages[0] 必须 user，`:2619`）→ `_manage_thinking_signatures`（签名管理，见 3.4）→ `_evict_old_screenshots`（只留最近 3 张 computer-use 截图，`:2584`）→ `_scrub_blank_text_blocks`（Anthropic 拒空白 text block，兜底占位 `(empty)`，`:2697`）。
4. **tools** `convert_tools_to_anthropic`（`:1755`）：`{function:{name,description,parameters}}` → `{name,description,input_schema}`，去重（Anthropic 拒重名，`:1767`），schema 过 `_normalize_tool_input_schema`（`:1714`，剥离 nullable union / 顶层 `oneOf/allOf/anyOf`）。
5. **tool_choice 映射**（`:2963`）：`auto/None`→`{type:auto}`；`required`→`{type:any}`；`none`→**直接删除 tools**（Anthropic 无 none）；具体名→`{type:tool,name:...}`。
6. **max_tokens 强制**（`:2875`）：Anthropic 把 `max_tokens` 设为必填且只限输出，`_resolve_anthropic_messages_max_tokens` 让非正值本地报错而非上线 400（port openclaw#66664），并 clamp 到 `context_length-1`（`:2884`）。
7. **reasoning → thinking**（`:2993`）：4.6+ 自适应模型用 `{thinking:{type:"adaptive",display:"summarized"},output_config:{effort}}`（`:2998`，`display:"summarized"` 是为在 4.7+ 让 reasoning 文本不被默认 `omitted` 隐藏）；老模型用 `{thinking:{type:"enabled",budget_tokens}}` + 强制 `temperature=1`（`:3011`）。effort 映射表 `ADAPTIVE_EFFORT_MAP`（`:79`），`xhigh` 在不支持的 4.6 上降级为 `max`（`:3005`）。
8. **4.7+ 采样参数剥离**（`:3021`）：`_forbids_sampling_params` 为真时删 `temperature/top_p/top_k`（4.7 对非默认值 400）。
9. **fast mode**（`:3031`）：仅 Opus 4.6、仅原生 Anthropic，加 `extra_body.speed="fast"` + fast-mode beta header。

### 3.2 响应方向归一

在 `transports/anthropic.py:80 normalize_response()`（非 adapter 内）。要点：
- 逐 content block → `text_parts`/`reasoning_parts`/`tool_calls`；每块过 `_to_plain_data`（`anthropic_adapter.py:1849`，SDK 对象转纯 dict，防循环引用）+ `_sanitize_replay_block`（捕获时就剥离 `parsed_output/caller/citations=None`，防持久化后重放 400，`transports/anthropic.py:117`）。
- **有序块通道**：仅当该轮**既有签名 thinking 又有 tool_use** 时，才把逐字有序 `ordered_blocks` 塞进 `provider_data["anthropic_content_blocks"]`（`:182`）——只有这种交错形状会被并行 list 重建成错误顺序而使签名失效。
- stop_reason 映射 `_STOP_REASON_MAP`（`:234`）：`end_turn`→`stop`、`tool_use`→`tool_calls`、`refusal`→`content_filter`。

### 3.3 流式差异

`create_anthropic_message()`（`:3103`）默认 **prefer_stream**：用 `messages.stream().get_final_message()` 聚合（因某些 Anthropic 兼容网关是 SSE-only，非流式请求也回 event-stream，`:3113-3118`），只有明确不支持流的（受限 Bedrock role）才回退 `create()`（`_is_stream_unavailable_error`，`:3091`）。`on_response` 回调用来抓 httpx response header 里的 Nous Portal `x-nous-credits-*` 余额（`:3128`）。发前 `sanitize_anthropic_kwargs`（`:3059`）剥离 Responses-only 键（`instructions/input/store/parallel_tool_calls`），防 api_mode 翻转竞态把 Responses 形状喂进 Messages SDK（#31673）。

### 3.4 特有机制

**(A) 签名 thinking 管理** `_manage_thinking_signatures`（`:2469`）——按端点类型分流：
- Kimi 系端点：不强制签名，原样重放（`:2514`）。
- DeepSeek `/anthropic`：剥签名保未签名（`:2518`）。
- 第三方端点 或 非最后一条 assistant：剥**所有** thinking block（签名是 Anthropic 专有，第三方无法验，`:2530`）。
- 原生 Anthropic 最后一条 assistant：保签名、未签名降级为 text；若孤儿剥离动过本轮（`_thinking_signature_invalidated`），把**全部** thinking 降级为 text（签名已死，`:2550`）。
- **Nous Portal 是第三方里的例外**：走原生重放路径（`:2487-2502`，Portal 端到端讲 Anthropic thinking 契约）。

**(B) 三态鉴权（build_anthropic_client `:777`）**——按 base_url/key 形状选 auth header：
- Kimi `/coding` → `api_key` + `User-Agent: claude-code/0.1.0`（否则 403，`:859`）
- `_requires_bearer_auth`（MiniMax/Azure/Palantir Foundry/Nous Portal）→ `auth_token`（Bearer 而非 x-api-key，`:868`）
- 第三方端点 → `api_key`（跳过 OAuth 检测，`:878`）
- OAuth token（`_is_oauth_token` 判 `sk-ant-`(非 api)/`eyJ`/`cc-`，`:407`）→ Bearer + Claude Code 身份 header（见 C）
- 普通 key → x-api-key（`:897`）
- 收尾：Bearer-only 时清 `client.api_key=None`，防 SDK 从 env `ANTHROPIC_API_KEY` 补出双鉴权（`:910`）。

**(C) Claude Code 身份伪装（is_oauth 路径，build_anthropic_kwargs `:2887`）**——四步：
1. system 前置 `You are Claude Code, Anthropic's official CLI for Claude.`（`_CLAUDE_CODE_SYSTEM_PREFIX`，`:395`/`:2890`）
2. **product 名替换**（绕服务端内容过滤）：

   `agent/anthropic_adapter.py:2903 @ 863e313`
   ```python
   text = text.replace("Hermes Agent", "Claude Code")
   text = text.replace("Hermes agent", "Claude Code")
   text = text.replace("hermes-agent", "claude-code")
   text = text.replace("Nous Research", "Anthropic")
   ```
3. **tool 名 `mcp__` 双下划线化**（`_to_oauth_wire_name`，`:2927`）：Anthropic 订阅计费分类器把单下划线 `mcp_` 当第三方 app 指纹并 400，故 `read_file`→`mcp__read_file`、`mcp_linear_get_issue`→`mcp__linear_get_issue`；`normalize_response` 用注册表反解回原名（`transports/anthropic.py:134`）。
4. client header（`build_anthropic_client:892`）：`anthropic-beta: ...,claude-code-20250219,oauth-2025-04-20`（`_OAUTH_ONLY_BETAS:357`）+ `user-agent: claude-code/<version> (external, cli)` + `x-app: cli`。version 通过 `claude --version` 动态探测（`_detect_claude_code_version:370`，fallback `2.1.74`）——Anthropic 会拒版本太旧的 OAuth 请求。

**(D) OAuth 凭据刷新链** `resolve_anthropic_token()`（`:1357`）——5 级优先级：`ANTHROPIC_TOKEN` → `CLAUDE_CODE_OAUTH_TOKEN` → `ANTHROPIC_API_KEY` → Claude Code 凭据文件（`~/.claude/.credentials.json` + macOS Keychain `read_claude_code_credentials:1040`，两源按 expiresAt 调和）→ Hermes credential_pool。刷新单用（single-use）竞态处理是亮点：`_refresh_oauth_token`（`:1159`）**先重读 live 凭据**，若 Claude Code 已自行轮换就直接采纳其新 token，避免拿已失效的 refresh_token 去 POST（`:1180-1191`）。刷新走 `refresh_anthropic_oauth_pure`（`:1095`，client_id `9d1c250a-...`，端点 `platform.claude.com` 优先、`console.anthropic.com` 兜底）。写回 `_write_claude_code_credentials`（`:1212`）用 `O_EXCL` + `0600` 原子写（防 TOCTOU 泄露 OAuth token）。

> 关键取舍：token endpoint UA 用 `axios/1.7.9`（`_OAUTH_TOKEN_USER_AGENT:1481`）而非 `claude-code/`——实测 `claude-code/*` UA 在 token endpoint 被 429（UA 前缀限流）；但 **inference 路径**仍必须 `claude-code/` UA。同一伪装，两条路径两个 UA，是被经验校准出来的。

### 3.5 Anthropic 侧取舍

- SDK `max_retries=0`（`:842`），把 429/5xx 重试全权交给 Hermes 外层循环（尊重 `Retry-After`）——SDK 默认 retry 会忽略 Retry-After 双重重试烧配额（#26293）。
- `import anthropic` 延迟到 `_get_anthropic_sdk()`（`:49`），省 ~220ms 冷启动。
- 各种"空白 text block"防御（`_safe_text:1954`、`_scrub_blank_text_blocks`）源于 Anthropic 硬拒空白 text 的 400，且坏 block 会被逐轮重放**永久卡死 session**——占位符自愈是刻意设计。

---

## 4. Codex Responses 适配器（agent/codex_responses_adapter.py，1590 行）

模块定位：纯格式转换 + 归一，无状态（`:1-9`）。服务 OpenAI Codex / xAI / GitHub Copilot 等 Responses 端点。

### 4.1 请求方向翻译

`_chat_messages_to_responses_input()`（`:410`）：OpenAI messages → Responses input items。
- user/assistant text → `{role, content}`，多模态过 `_chat_content_to_responses_parts`（`:154`，`input_text`/`output_text`/`input_image`，且 Responses 拒 assistant 里 input_text、user 里 output_text，故按 role 选 text 类型）。
- assistant 的 `codex_reasoning_items`（encrypted_content）重放（`:490`）。
- assistant 的 `codex_message_items` 逐字重放（保 prefix-cache，`:545`）。
- tool_calls → `function_call`（`:644`），call_id 过 `_clamp_responses_call_id`（>64 字符 sha256 压缩，#73492，`:269`）。
- tool → `function_call_output`（`:687`），支持数组形态多模态输出。

**preflight 校验** `_preflight_codex_api_kwargs()`（`:933`）：强制 `store=False`（`:1025`，因 Hermes 不用服务端存储，带 id 会 404）、`{model,instructions,input}` 必填、allowed_keys 白名单（`:1029`，多余字段直接 ValueError）、xAI 模型额外剥 slash-enum（`:1132`，HuggingFace ID `Qwen/...` 会让 xAI 400）。

### 4.2 响应方向归一

`_normalize_codex_response(response, issuer_kind)`（`:1232`）→ `(SimpleNamespace assistant_message, finish_reason)`。
- 逐 output item：`message`（含 `commentary`/`analysis` phase 文本改走 reasoning 通道、不进 content，`:1367`）、`reasoning`（抓 `encrypted_content`，`:1391`）、`function_call`/`custom_tool_call`（`:1419`/`:1442`）。
- **finish_reason 判定**（`:1554`）是核心复杂度：server-side 内建工具 call（web_search_call 等，`_SERVER_SIDE_TOOL_CALL_TYPES:1321`）的 `in_progress` 状态**不翻** incomplete（否则烧 3 次续写重试）；reasoning-only + `status=completed` 对 Codex/xAI/GitHub 判 `incomplete`（还在想），对其他 issuer 信任 provider 的 `stop`（#64434，`:1580`）。
- **两处救援**：tool-call 文本泄漏检测（`_TOOL_CALL_LEAK_PATTERN:71`，模型把 `to=functions.foo{json}` 当文本吐出、无结构化 function_call → 判 incomplete 触发续写，`:1492`）；xAI grok 把最终答案塞进 reasoning `<response>` 分隔符里 → 提升为 content（`:1519`）。

### 4.3 特有机制

**(A) Harmony token 中和** `_neutralize_harmony_tokens()`（`:89`）——ChatGPT Codex backend 保留 Harmony 线协议 token `<|start|>`/`<|end|>`/`<|channel|>` 等，文本里出现字面拼写会被在推理前 `invalid_prompt: Request blocked` 拒掉。中和策略：把半角 `<|x|>` 替换成全角管道 `<｜x｜>`（`_FULLWIDTH_PIPE:86`，源码仍可读、但不是保留 token）。且处理 Cf 类隐藏字符（U+200B 会被 backend 先剥掉再检测，故把所有 Unicode format control 视作可被移除，防"藏字符再拼回 token"绕过，`:98-124`）。`_neutralize_harmony_structure`（`:127`）递归处理 JSON，但**拒绝**在 object key 里出现保留 token（改 key 会破坏 tool schema 契约，直接 ValueError）。

**门控**：中和只对 ChatGPT Codex backend 开启——`conversation_loop.py:2229/2389` 传 `sanitize_harmony_tokens=agent._is_codex_backend()` → `transports/codex.py:621 preflight_kwargs` → `codex_responses_adapter.py:965`。对 xAI/其他 Responses 端点关闭（gate off 时字节级保留，见测试 4.5）。

**(B) encrypted_content issuer 隔离** `_classify_responses_issuer()`（`:28`）——`reasoning.encrypted_content` 密封到签发端点，把 Codex 铸的 blob 重放给 xAI 必得 `HTTP 400 invalid_encrypted_content`。issuer kind：`xai_responses`/`github_responses`/`codex_backend`/`other:<base_url>`。归一时 `_normalize_codex_response` 把 issuer 盖章到每个 reasoning item 的 `_issuer_kind`（`:1398`）；重放时 `_chat_messages_to_responses_input` 的 `current_issuer_kind` 守卫（`:508`）丢弃跨 issuer 的 reasoning item（未盖章的 legacy item 放行）。issuer 由 `transports/codex.py:193 _resolve_issuer_kind` 从 build_kwargs/convert_messages 的 params 推得并缓存 `_last_issuer_kind`（`:187`）供 normalize 回填。

**(C) GitHub Copilot connection 隔离**（`:439`）：`is_github_responses` 时无条件删 `codex_message_items` 的 `id`（Copilot 把 id 绑到具体 backend connection，凭据轮换/重启/负载均衡换连接都会让 stale id 401 "input item ID does not belong to this connection"，#32716）。

### 4.4 取舍

- `store=False` 是硬约束（`:1026`），换来无服务端状态但要求 encrypted_content 自包含。
- call_id 用**确定性** `deterministic_call_id`（`:257`），随机 UUID 会让每次请求 prefix 变化打穿 OpenAI prompt cache。

### 4.5 与文档一致性

Harmony 中和、issuer 隔离在 `README/AGENTS.md/website/docs` **完全无记载**（grep `harmony` 只命中 creative skills；`provider-runtime.md:139` 只说 Codex 用 Responses API + 独立凭据，未提中和/隔离）。属"代码有、文档无"。

---

## 5. Gemini native 适配器（agent/gemini_native_adapter.py，1127 行）

**关键定位**：Gemini **保持 `api_mode='chat_completions'`**（`:1-8`），本文件是一个**伪装成 OpenAI SDK 的 shim**，把 OpenAI 形状请求转成 Gemini native `models/{model}:generateContent` 再转回来——因为 Google 的 OpenAI-compat 端点对多轮 agent/tool loop 太脆（auth churn、tool 重放、thought-signature）。

### 5.1 请求方向

`build_gemini_request()`（`:518`）→ `_build_gemini_contents()`（`:358`）：
- system → `systemInstruction`（独立字段，`:453`）；assistant→`model` role；tool→`user` role 的 `functionResponse`（`:372`）。
- tool_call → `functionCall` part（`_translate_tool_call_to_gemini:302`），**thoughtSignature 必带**：跨 provider fallback（如从 xAI/Anthropic 掉到 Gemini）原 tool_call 无 Gemini 签名时填哨兵 `"skip_thought_signature_validator"`（`:324`，否则 Gemini 3 thinking 模型 400 INVALID_ARGUMENT）。
- **交替修复**（`:424-451`）：Gemini 拒连续同 role；但**不能**把人类 user 文本折进只含 functionResponse 的 user content（Gemini 3 会 200 但把文本当 tool 结果续写），故在两者间插占位 model turn `[The previous response was interrupted...]`（`_INTERRUPTED_RESPONSE_PLACEHOLDER:297`，仿 gemini-cli#28700）。
- tools → `functionDeclarations`（`_translate_tools_to_gemini:460`），参数过 `sanitize_gemini_tool_parameters`（见 §7）。
- **maxOutputTokens 默认**（`:545`）：native 端点省略该字段**不**等于满预算而是应用低内部默认导致截断，故 None 时默认 `65535`（`GEMINI_DEFAULT_MAX_OUTPUT_TOKENS:49`）——与 OpenAI-compat 语义相反，这是本 adapter 存在的一个具体理由。

### 5.2 响应方向

`translate_gemini_response()`（`:616`）→ 构造 OpenAI 形状 `SimpleNamespace`（`.choices[0].message`）：
- part 里 `thought is True` 的 text → reasoning（`:632`）；普通 text → content；`functionCall` → tool_call（id 随机 `call_<uuid>`，`:644`），thoughtSignature 存进 `extra_content.google.thought_signature`（`:650`）。
- finish_reason 映射（`_map_gemini_finish_reason:572`）：`MAX_TOKENS`→`length`、`SAFETY/RECITATION`→`content_filter`。usage 从 `usageMetadata` 映射，含 `cachedContentTokenCount`（`:656`）。

### 5.3 流式

`_stream_completion()`（`:1072`）打 `:streamGenerateContent?alt=sse`，`_iter_sse_events`（`:735`）解析 SSE，`translate_stream_event`（`:760`）逐 event 转 OpenAI chunk。tool-call 参数做**增量 diff**（记 `last_arguments`，只发新增部分，`:800-807`），因 Gemini 每 event 重发全量 args。`AsyncGeminiNativeClient`（`:1096`）用 `asyncio.to_thread` 包同步 client。

### 5.4 特有机制/取舍

- 自建 `GeminiNativeClient`（`:956`）暴露 `.chat.completions.create()` 门面，让上层 45+ 处 OpenAI 调用零改动。选用时机：`is_native_gemini_base_url()`（`:62`，`generativelanguage.googleapis.com` 且非 `/openai` 结尾）判真则在 `agent_runtime_helpers.py:2284` 构造它。
- 鉴权/quota 诊断丰富：`probe_gemini_tier`（`:72`，探 free/paid）、`is_free_tier_quota_error`（`:149`）、`is_standard_key_auth_error`（`:166`，Google 2026-06 起拒 legacy Standard key 的误导性 401 → 给正确指引 `_STANDARD_KEY_GUIDANCE:189`）。
- header 里 UA `hermes-agent/<ver> (gemini-native)` + `X-Goog-Api-Client`（`:1001`，partner integration 约定）。

---

## 6. Bedrock Converse 适配器（agent/bedrock_adapter.py，1573 行）

定位：走 boto3 直连 Converse API，**绕过 OpenAI client**（`:1-28`）；与 anthropic_adapter 同构。

### 6.1 请求方向

`build_converse_kwargs()`（`:1018`）→ `convert_messages_to_converse()`（`:601`）：
- system → 独立 `system` block 列表（`:627`，空白部分整块丢弃）。
- assistant tool_calls → `{"toolUse":{toolUseId,name,input}}`（`:680`，input 是 dict 非 JSON 字符串）。
- tool → `{"toolResult":{toolUseId,content}}` 放进 **user** role（`:647`）。
- 严格 user/assistant 交替：连续同 role 合并（`:692`/`:704`）；首条须 user、末条须 user，否则插占位（`:713-719`）。
- 图片 `image_url` data: URL **解码成裸 bytes**（`:582`，boto3 会在 wire 层再编码，传 base64 字符串会双编码 → "Failed to sanitize image" #33317）。
- tools → `{"toolSpec":{name,description,inputSchema:{json:params}}}`（`convert_tools_to_converse:488`）；非 tool-calling 模型（DeepSeek R1 等）**剥 tools 并 warn**（`:1068`，否则 ValidationException 重试死循环）。
- **prompt cache**（`:1043`/`:1078`）：支持 cache 的模型在 system 末尾、倒数第二条 message 末尾插 `{"cachePoint":{"type":"default"}}`（checkpoint 到不含最新轮，仿 Anthropic system_and_3 策略）。
- 采样参数受 `_forbids_sampling_params`（复用 anthropic_adapter，`:1048`）门控。

### 6.2 响应方向

`normalize_converse_response()`（`:741`）→ OpenAI 形状 `SimpleNamespace`：
- content block：`text`/`reasoningContent`（→reasoning_content）/`toolUse`（→tool_call，arguments 用 `json.dumps`，`:771`）。
- stop_reason 映射 `_converse_stop_reason_to_openai`（`:728`）：`tool_use`→`tool_calls`、`guardrail_intervened`→`content_filter`。
- **usage 语义修正**（`:790`）：Converse 的 `inputTokens` 不含 cache read/write（与 OpenAI 相反），故 `prompt_tokens = input + cacheRead + cacheWrite`，还原 OpenAI"总量含 cache"约定 + 暴露 Anthropic 命名的 cache 字段。

### 6.3 流式

`stream_converse_with_callbacks()`（`:845`）消费 boto3 `converse_stream()` 事件流，事件序列 `messageStart/contentBlockStart/Delta/Stop/messageStop/metadata`（`:891` 起）。回调分离：`on_text_delta`（仅无 tool_use 时触发）、`on_tool_start`、`on_reasoning_delta`（Claude 4.6+ 的 reasoningContent）、`on_event`（每 event 触发的 wire 级 liveness 信号，供 watchdog 区分"还在收"与"卡死"，`:891-900`）。tool 参数增量拼接 `input_json`（`:932`），contentBlockStop 时 `json.loads`（`:946`）。**流式降级**（`call_converse_stream:1133`）：IAM 允许 InvokeModel 但拒 InvokeModelWithResponseStream 时（`is_streaming_access_denied_error:228`）回退非流式 `converse()`（`:1173`）。

### 6.4 特有机制/取舍

- **双客户端路径**：Anthropic Claude 模型（`is_anthropic_bedrock_model:459`）走 `build_anthropic_bedrock_client`（`anthropic_adapter.py:915`，用 SDK 的 `AnthropicBedrock`，拿 full Claude 特性 + `context-1m` beta 解锁 1M 窗口，否则 Bedrock 上被封 200K）；非 Claude 走 Converse。
- client 缓存 + stale-connection 剔除（`invalidate_runtime_client:120`、`is_stale_connection_error:172` 按 traceback 模块判定）。
- 鉴权走 AWS 默认凭据链（IAM/SSO/env，`has_aws_credentials:325`、`resolve_bedrock_region:356`），零 API key 管理。boto3 延迟 import（`:45`/`_require_boto3:64`），非 [all] extra（lazy_deps 按需装）。

---

## 7. Schema/effort 清洗模块（chat_completions 模式下的 provider 特化）

这三个模块**不改 api_mode**，是 `chat_completions` 线上按模型/provider 打的补丁，在 `transports/chat_completions.py` 内调用。

**gemini_schema.py（140 行）** `sanitize_gemini_schema()`（`:37`）：白名单 `_GEMINI_SCHEMA_ALLOWED_KEYS`（`:11`，剥 `$schema`/`additionalProperties` 等 Gemini `Schema` 子集外的键），递归 properties/items/anyOf；`integer/number/boolean` 的 enum 值**字符串化**（Gemini 要求 enum 全 string，`:83`）；`required` 严格过滤到本节点 `properties` 里存在的名（MCP server 常发 required-无-properties 的坏 schema 会整请求 400，port kilocode#11955，`:118`）。

**moonshot_schema.py（269 行）** `_repair_schema()`（`:44`）修 Moonshot flavored JSON Schema 三规则：每个属性须带 `type`（`_fill_missing_type:162` 启发式推断）、`anyOf` 的 type 须在子节点非父（`:90`，且塌缩 null 分支）、object 须带 `required` 数组即使空（`_ensure_required_array:143`）。`is_moonshot_model()`（`:246`）按模型名（含 aggregator 前缀 `kimi-*`/`moonshot*`/`k3`）识别，`transports/chat_completions.py:450/644` 处调用 `sanitize_moonshot_tools`。

**lmstudio_reasoning.py（60 行）** `resolve_lmstudio_effort()`（`:35`）：把 Hermes effort ladder 映射到 LM Studio 词汇（`off→none`/`on→medium`，`max/ultra→xhigh` clamp），再 clamp 到模型 `allowed_options`；越界返回 `None`（"省略字段"让 server 用模型默认，而非静默换一个 effort）。

---

## 8. 取舍/边界工具：backend_identity.py（204 行）

**再次纠偏**：非身份伪装，而是**故障域 → 跳过判定**的单一 owner。核心洞见（`:14-26`）：`provider` 混淆了三条独立身份轴，每类故障作废不同轴：
- `CREDENTIAL`（401/402）作废共享凭据面 → `same_credential_surface`（`:132`）
- `ENDPOINT`（DNS/连接拒绝）作废端点 → `same_endpoint`（`:152`）
- `MODEL`（超时/过载/429/不兼容）只作废单个模型部署 → `same_deployment`（`:161`）

`classify_failure_scope`（`:70`）把 reason 字符串映射到 `FailureScope`，`should_skip_candidate`（`:189`）是唯一 skip 谓词。设计取舍：不可证的轴一律答"不同"（try 一次最多浪费一个 RTT，胜过误跳导致 failover 搁浅）。`_both_first_class`（`:114`）用 `PROVIDER_REGISTRY` 区分"同 host 不同注册 provider（xai-oauth vs xai，凭据不同 #70893）"与"同 URL 两个 custom alias（同后端 #22548）"。

---

## 9. 定案任务结论

**(a) ◇ Nous Portal 双线协议路由（providers.py:666 按模型前缀选协议）+ ▲ 文档缺口 → 证实（修正行号）**

代码证实。核心是 `nous_api_mode()`（`providers.py:652`），模型前缀判定在：

`hermes_cli/providers.py:666 @ 863e313`
```python
    if str(model or "").strip().lower().startswith("anthropic/"):
        return "anthropic_messages"
    return "chat_completions"
```

Portal 把 `anthropic/*` 目录服务在 native `/v1/messages`，其余走 OpenAI-compat `/chat/completions`（`:652-668` docstring）。`determine_api_mode`（`:693`）对 `{nous,nous-portal,nousresearch}` 走这条 carve-out——因为 Hermes overlay 对整个 Nous 目录只标 `openai_chat`（`providers.py:57`），不 carve 会把 Claude 钉在错线上。空/未知 model 兜底 `chat_completions`（历史 Nous transport，更安全）。Portal 端点还带三处特化：Bearer JWT 鉴权（`_requires_bearer_auth`→`_is_nous_portal_endpoint:561`，只信 prod host + `NOUS_INFERENCE_BASE_URL` override host，拒 lookalike）、verbatim 目录 id（`build_anthropic_kwargs:2869` 跳过 normalize_model_name 保 `anthropic/claude-opus-4.8` 前缀+点）、签名 thinking 原生重放（`_manage_thinking_signatures` 例外，`:2487`）、`tags`/`session_id` body 字段合并到 Messages 线（`_merge_nous_portal_messages_extra_body`，`chat_completion_helpers.py:1188`）。

**▲ 文档缺口**：`website/docs/developer-guide/provider-runtime.md` 列了"Nous Portal"（`:47`）但**只字未提双线/模型前缀路由**；README/AGENTS.md 亦无。属"代码有、文档无"的自绘地图缺口。任务给的行号 `666` 与 863e313 实测一致（`nous_api_mode` 内的前缀判定）。

**(b) ◇ Codex Responses 的 Harmony 中和 → 证实**

见 §4.3(A)。`_neutralize_harmony_tokens`（`codex_responses_adapter.py:89`）把 `<|start|>` 等保留 token 换全角管道，处理 Cf 隐藏字符防绕过。门控在 ChatGPT Codex backend（`agent._is_codex_backend()` → `sanitize_harmony_tokens`）。文档无记载。

**(c) ◇ Anthropic OAuth / Claude Code 身份伪装 → 证实**

见 §3.4(C)(D)。四步伪装（system 前缀 + product 名替换 `Nous Research→Anthropic` + `mcp__` 前缀 + claude-code UA/beta header）确凿在 `build_anthropic_kwargs:2887` 与 `build_anthropic_client:886`。凭据刷新链（单用 refresh_token 竞态先重读、`platform.claude.com` 迁移、原子写）在 `resolve_anthropic_token:1357` / `_refresh_oauth_token:1159`。文档**部分记载**：`provider-runtime.md:132-137` 讲"优先可刷新的 Claude Code 凭据"，但**未提伪装/冒充**（UA spoof、product 名替换、mcp__ 计费规避）——伪装部分是文档盲区。

---

## 10. 对应测试文件（tests/，behavior spec 候选）

各 adapter 的测试清单：
- **Anthropic**：`test_anthropic_adapter.py`(77KB)、`test_anthropic_mcp_prefix_strip.py`、`test_anthropic_oauth_pkce.py`、`test_anthropic_oauth_ua_prefix.py`、`test_anthropic_thinking_block_order.py`、`test_anthropic_kimi_signed_thinking_replay.py`、`test_anthropic_kwargs_sanitize.py`、`test_anthropic_whitespace_text_blocks.py`、`test_anthropic_output_field_leak.py`、`test_anthropic_keychain.py`、`test_anthropic_token_scope_isolation.py`、`test_deepseek_anthropic_thinking.py`、`test_kimi_coding_anthropic_thinking.py`、`test_minimax_provider.py`
- **Codex**：`tests/agent/test_codex_responses_adapter.py`、`tests/agent/transports/test_codex_transport.py`、`tests/run_agent/test_run_agent_codex_responses.py`、`test_codex_xai_oauth_recovery.py`
- **Gemini**：`test_gemini_native_adapter.py`、`test_gemini_schema.py`、`test_gemini_free_tier_gate.py`、`test_gemini_standard_key_guidance.py`
- **Bedrock**：`test_bedrock_adapter.py`(46KB)、`test_bedrock_integration.py`、`test_bedrock_1m_context.py`、`test_bedrock_empty_text_blocks.py`、`tests/agent/transports/test_bedrock_transport.py`
- **Nous/Moonshot/Azure/Vertex/LMStudio**：`test_nous_portal_anthropic_wire.py`、`test_moonshot_schema.py`、`test_azure_identity_adapter.py`、`test_vertex_adapter.py`、`test_lmstudio_reasoning.py`

### 挑 3 个最像行为规格的（读代码，未运行）

**① `tests/agent/test_nous_portal_anthropic_wire.py`（双线路由的可执行契约）**
六节 docstring 直接把机制列成契约（`:1-14`）。`TestApiModeRouting`（`:35`）参数化断言 `anthropic/claude-opus-5`、`ANTHROPIC/Claude-Sonnet-5`（大小写不敏感）等 → `nous_api_mode(...) == "anthropic_messages"`（`:47`），并**反向**断言裸 `claude-opus-4.8`（无 vendor 前缀）→ `chat_completions`（`:51`，Portal id 必带前缀）。`test_determine_api_mode_honors_the_model_for_nous`（`:56`）断言跳过 resolve 的 caller（fallback/switch）仍靠 model 定线，且无 model → `chat_completions` 兜底（`:75`）。`TestRuntimeResolution`（`:78`）验端到端 resolved dict 带 model-derived mode，且 target_model 压过持久化 default（mid-session /model 切换）。这是定案任务(a)的行为化证据。

**② `tests/agent/test_anthropic_mcp_prefix_strip.py`（OAuth 身份伪装的 tool 名往返）**
docstring 直述计费分类器约束（`:1-13`）。请求侧 `TestAnthropicOAuthOutgoingPrefix`（`:105`）断言 `build_anthropic_kwargs(is_oauth=True)` 后：`mcp_linear_get_issue`→`mcp__linear_get_issue`（`:137`，且不双前缀 `mcp__mcp_`）、混合集 `read_file`/`mcp_linear_get_issue`/`terminal` 全落 `mcp__*`，核心不变式"**无单下划线 mcp_ 上线**"逐名断言（`:155`）。响应侧 `TestAnthropicMcpPrefixStrip`（`:62`）用 fake 注册表断言 `normalize_response(strip_tool_prefix=True)` 把 `mcp__read_file` 反解回 `read_file`（`:79`），`strip_tool_prefix=False` 时原样保留（`:94`）。这是定案任务(c)身份伪装的行为化证据。

**③ `tests/agent/test_codex_responses_adapter.py`（Harmony 中和 + issuer 隔离 + finish_reason）**
`test_codex_preflight_gate_off_preserves_harmony_tokens_byte_for_byte`（`:27`）断言门控关时保留字节；`test_harmony_neutralizer_defangs_only_reserved_control_tokens`（`:39`）断言 `<|start|>`→`<｜start｜>` 而 Qwen 的 `<|im_start|>` 等非保留 token 原样（`:45`）；`test_harmony_neutralizer_upgrades_zwsp_and_is_idempotent`（`:48`）断言 U+200B 隐藏形被规整且幂等（`:53-55`）；`test_codex_api_preflight_rejects_reserved_token_in_structural_key`（`:106`）断言 object key 里的保留 token 抛错（不可安全中和）；`test_normalize_codex_response_treats_summary_only_reasoning_as_incomplete`（`:201`）断言 `codex_backend` issuer 的 summary-only reasoning → `finish_reason="incomplete"` 且不落 `codex_reasoning_items`（`:224-227`）；`test_chat_messages_to_responses_input_clamps_oversized_call_id`（`:273`）断言 >64 call_id 被压且 function_call 与 output 仍配对（`:300-303`）。这是定案任务(b) + §4 归一逻辑的行为化证据。

---

**证据可复核性说明**：以上所有 `路径:行号` 均对 863e313 工作树 `wc -l`/`Read` 实测；断言处紧跟原文块。`backend_identity.py` 与任务标注"身份伪装"的错配已在开头与 §8 显式记录（本身即学习产出）。
