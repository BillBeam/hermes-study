# R2-21 辅助 LLM 路由 + 模型元数据 + 用量定价(子代理底稿)

> 由子代理精读产出,主线抽查定案 4a/4b 与 _resolve_auto 关键行号。基线 863e31318。
> 范围:auxiliary_client(9976)、model_metadata(3370)、models_dev(903)、
> usage_pricing(1432)、account_usage(902)、credits_tracker(852 概述)。

# R2 L1 精读底稿:辅助 LLM 路由 + 模型元数据 + 用量定价机制簇

辅助任务默认复用主模型,文档"独立链"说法已过时。

- 基线:`NousResearch/hermes-agent @ 863e31318553cda8ad61df681d08175364d4164b`(下文所有 `路径:行号` 均指该 commit,省略 `@ 863e313` 后缀)
- 文件范围与实测行数(`wc -l`):

| 文件 | 行数 | 精读深度 |
|---|---|---|
| agent/auxiliary_client.py | 9,976 | L1(全结构图 + 关键路径逐行) |
| agent/model_metadata.py | 3,370 | L1 |
| agent/models_dev.py | 903 | L1 |
| agent/usage_pricing.py | 1,432 | L1 |
| agent/account_usage.py | 902 | L1 |
| agent/credits_tracker.py | 852 | 概述级 |
| 合计 | 17,435 | |

---

## 1. auxiliary_client.py — 辅助 LLM 路由器

### 1.1 问题

Agent harness 里除了主对话循环,还有大量"副脑"工作:上下文压缩、标题生成、视觉分析、网页摘要、审批判断……每个消费者若各自查 env var、各自建 client、各自写 fallback,会产生 N 份互相漂移的解析逻辑。本模块把这一切收敛为单一解析链。模块头自述:

> agent/auxiliary_client.py:1-5
> ```python
> """Shared auxiliary client router for side tasks.
>
> Provides a single resolution chain so every consumer (context compression,
> session search, web extraction, vision analysis, browser vision) picks up
> the best available backend without duplicating fallback logic.
> ```

### 1.2 辅助任务枚举(与主 agent 的关系)

任务的权威清单在 `hermes_cli/config_defaults.py` 的 `"auxiliary"` 段(hermes_cli/config_defaults.py:831-1070),共 **18 个任务块** + 4 个顶层旋钮:

- 任务块:`vision`、`web_extract`、`compression`、`skills_hub`、`approval`、`mcp`、`title_generation`、`memory_query_rewrite`、`tts_audio_tags`、`triage_specifier`、`kanban_decomposer`、`profile_describer`、`goal_judge`、`curator`、`monitor`、`background_review`、`moa_reference`、`moa_aggregator`
- 顶层旋钮:`transient_retries`(默认 2,hermes_cli/config_defaults.py:838)、`free_only`(hermes_cli/config_defaults.py:846)、`openrouter_model`(hermes_cli/config_defaults.py:852)、`stream_only_base_urls`(hermes_cli/config_defaults.py:859)
- 历史任务 `session_search` 已不再走 LLM(hermes_cli/config_defaults.py:888-891 注释:PR #27590 后该块被移除,残留配置被忽略)
- 插件还可注册新任务(`_get_auxiliary_task_config` 会把插件声明的 defaults 垫在用户配置之下,agent/auxiliary_client.py:7517-7558)

代码中实际以 `task="..."` 调用的还有 `kanban_estimator`(共享 decomposer 配置族),grep 实证:`compression`(29 处)、`title_generation`(13)、`moa_aggregator`(10)、`vision`(7)、`moa_reference`(6)等。

与主 agent 的关系:主循环在每轮开始用 `set_runtime_main()` 把**活跃运行时**(provider/model/base_url/api_key/api_mode)发布到 contextvar(agent/auxiliary_client.py:3055-3103),辅助任务解析时最先读它,其次才读 config.yaml:

> agent/auxiliary_client.py:2667-2669
> ```python
>     override = _runtime_main_value("model")
>     if isinstance(override, str) and override.strip():
>         return override.strip()
> ```

contextvar 保证并发 gateway 会话互不覆盖(3066-3070 docstring);另有加锁的 legacy 全局镜像仅供主线程 test-patch 兼容(`_compat_runtime_main`,3020-3040)。

### 1.3 `_resolve_auto` 完整解析顺序(定案 a 的核心证据)

`_resolve_auto(main_runtime, task)`(agent/auxiliary_client.py:5391-5569)是 `provider: auto`(即默认)时的总入口。逐步:

**Step 0 — 预处理**
- 5408-5409:重置 `auxiliary_is_nous` 标志;`_normalize_main_runtime` 归一 runtime dict(5410)。
- 5422-5435:一次性告警"OPENAI_BASE_URL 残留但 provider 非 custom"的 env 污染。

**Step 1 — 主 provider + 主 model 直接复用(5437-5532)**
- 5444-5445:`main_provider = runtime.provider or _read_main_provider()`;`main_model = runtime.model or _read_main_model()`。
- 5455-5466:MoA 虚拟 provider 解包为聚合器槽位的真实 provider+model,并丢弃 `moa://local` 假端点与占位 key。
- 5468-5512:按 provider 形态决定 explicit base_url/api_key 的传递方式:
  - `custom` + runtime base_url → 匿名 custom 直传(5473-5478);
  - `custom:<name>` 且命名条目存在 → **保留全名**以命中命名 custom 分支、尊重其 `api_mode`(5487-5498,注释明确避免 `/anthropic→/v1` 改写 404);
  - `custom:<name>` 无条目但有 runtime base_url → 塌缩为匿名 custom(5499-5505,#34777);
  - 其余:把主会话正在用的 api_key 钉给辅助调用,避免从池里重选到耗尽的 key(5508-5512)。
- 5513-5520:若主 provider 最近 402 过(unhealthy 缓存)则**跳过 Step 1**,避免每次辅助调用都白付一个 402 RTT。
- 5522-5532:`resolve_provider_client(resolved_provider, main_model, ...)` 成功即返回。

> agent/auxiliary_client.py:5437-5443
> ```python
>     # ── Step 1: main provider + main model → use them directly ──
>     #
>     # This is the primary aux backend for every user.  "auto" means
>     # "use my main chat model for side tasks as well" — including users
>     # on aggregators (OpenRouter, Nous) who previously got routed to a
>     # cheap provider-side default.  Explicit per-task overrides set via
>     # config.yaml (auxiliary.<task>.provider) still win over this.
> ```

**Step 2 — 用户声明的 fallback 策略(5534-5547)**
- 5539-5543:先试 `auxiliary.<task>.fallback_chain`(`_try_configured_fallback_chain`,5110);
- 5544-5547:再试主 agent 顶层 `fallback_providers`/legacy `fallback_model`(`_try_main_fallback_chain`,5289,经 `get_fallback_chain` 与主循环同序)。
- 两条链都会用 `_candidate_context_window` 做上下文窗口筛查:compression 任务要求候选 ≥ `MINIMUM_CONTEXT_LENGTH`(64K),窗口未知(None)则放行(5047-5065、5200-5213)。

**Step 3 — 内置发现链(5549-5569)**
`_get_provider_chain()` 返回固定顺序(运行时构建以便 test patch 生效):

> agent/auxiliary_client.py:3607-3612
> ```python
>     return [
>         ("openrouter", _try_openrouter),
>         ("nous", _try_nous),
>         ("local/custom", _try_custom_endpoint),
>         ("api-key", _resolve_api_key_provider),
>     ]
> ```

逐项跳过 unhealthy 条目;全部失败则 warn 并返回 `(None, None)`(5565-5569)。各 `_try_*`:
- `_try_openrouter`(2479-2514):先信用池、后 `OPENROUTER_API_KEY`;`auxiliary.free_only=true` 时非 `:free` SKU 直接跳过整个 OpenRouter 步(2482-2492),非 free 模型首次启用打 PAID-lane 警告(2465-2476)。
- `_try_nous`(2530-2611):先查跨会话 429 守卫(2534-2545);模型问 Portal 的 recommended-models(区分付费/免费层,2565-2591),失败退 `_NOUS_MODEL`。
- `_resolve_api_key_provider`(2322-2433):按 `PROVIDER_REGISTRY` 顺序遍历 `auth_type == "api_key"` 的 provider,anthropic 需显式配置才参与(2340-2350,防止 Claude Code 凭据被静默挪用),每个 provider 需有已知 aux 模型(`_get_aux_model_for_provider`,700-713:先 `ProviderProfile.default_aux_model`,后硬编码回退表 719-737)。

**Codex 故意不在链中**:

> agent/auxiliary_client.py:3600-3605
> ```python
>     NOTE: ``openai-codex`` is deliberately NOT in this chain.  The
>     ChatGPT-account Codex endpoint only accepts a shifting, undocumented
>     allow-list of model IDs, so falling back to it with a guessed model
>     fails more often than not.  Codex is used only when the user's main
>     provider *is* openai-codex (see Step 1 of ``_resolve_auto``) or when
>     a caller explicitly requests it with a model.
> ```

### 1.4 为什么默认复用主 provider(设计理由)

docstring 直接给出理由(可预测性 > 省钱):

> agent/auxiliary_client.py:5398-5404
> ```python
>       1. User's main provider + main model, regardless of provider type.
>          This means auxiliary tasks (compression, vision, web extraction,
>          session search, etc.) use the same model the user configured for
>          chat.  Users on OpenRouter/Nous get their chosen chat model; users
>          on DeepSeek/ZAI/Alibaba get theirs; etc.  Running aux tasks on the
>          user's picked model keeps behavior predictable — no surprise
>          switches to a cheap fallback model for side tasks.
> ```

反向证据(不复用会怎样)在 xai-oauth 分支注释:若缺这个分支,xAI 订阅用户的所有副任务会被静默重路由到 OpenRouter/Nous 产生"surprise bills"(agent/auxiliary_client.py:5943-5949)。`background_review` 的默认注释还给出成本论证:同模型可复用主 prompt cache,换便宜模型反而要冷写 digest(hermes_cli/config_defaults.py:1029-1039)。

### 1.5 每 task 的 config 覆盖链(`auxiliary.<task>.*`)

`_resolve_task_provider_model(task, provider, model, base_url, api_key)`(7326-7500)是覆盖链的裁决点,优先级:

1. **显式实参永远赢**(7336);
2. **config `auxiliary.<task>.{provider,model,base_url,api_key,key_env/api_key_env,api_mode}`**(7352-7365,key_env 经 `_scoped_key_env` 解析,支持 gateway 多租户 secret scope);
3. **"auto" 哨兵**:`model: auto` 会被降为 None,否则字符串 "auto" 会上线并被 provider 以 200+错误文本"成功"返回,污染压缩输出(7367-7384 注释,含 MoA 槽位同样归一);
4. **MoA provider 解包**(7389-7423);
5. **direct-API 别名**:`provider: openai` → `custom` + `https://api.openai.com/v1`(`_AUX_DIRECT_API_BASE_URLS`,7321-7323;理由:PROVIDER_REGISTRY 无裸 `openai`,用户误配会把 OpenAI 模型名发给 DeepSeek,#31179);
6. **provider+base_url 共存判定**:一等 provider 带 base_url 保留 provider 身份(保 auth/transport 行为),未知 provider 带 base_url 塌缩为 custom(7439-7481);
7. **尾部裁决**(7485-7500):`cfg_base_url+cfg_api_key → custom`;`cfg_base_url+cfg_provider → provider`(让 provider 从 env 解析凭据);`cfg_provider → provider`;否则 `auto`。

其余 per-task 旋钮各有独立 reader:
- `timeout`:`_get_task_timeout`(7561-7572,默认 30s);compression 独享 300s 下限 floor,且显式传参不受 floor 影响(`_effective_aux_timeout`,7575-7589,#54915);
- `extra_body` + `reasoning_effort` 简写(折为 `extra_body.reasoning`,MoA 两任务明确拒绝该键,7592-7635);
- `max_concurrency` → per-task 信号量,限制重试放大(7638-7665,#23324;vision 例外——该键已被其 CPU 池占用);`call_llm` 在流式响应时把释放挂到流消费完成之后(8606-8628);
- `fallback_chain`(5110-5226):逐条 `{provider, model, base_url, api_key/api_key_env, api_mode}`;失败范围语义由 `agent.backend_identity` 统一——**模型级失败**(超时/连接/限流)只跳过失败的那个 (provider,model) 对,**凭据级失败**(401/402)跳过整个 provider(5152-5169)。

公共入口 `get_text_auxiliary_client(task)` / `get_async_text_auxiliary_client(task)`(6485-6526)= `_resolve_task_provider_model` + `resolve_provider_client`。而 `call_llm/async_call_llm`(8562/9398)是完整托管入口(见 1.7)。

### 1.6 client 缓存与生命周期

- 缓存体:`_client_cache: Dict[tuple, tuple]`,上限 64,FIFO 淘汰(6939-6941、7296-7298)。**淘汰时不 close**——别的调用方可能还拿着该对象在请求中,靠引用计数回收(7290-7295 注释)。
- **缓存键**(`_client_cache_key`,6976-7009):`(provider, async_mode, base_url, api_key摘要, api_mode, runtime_key仅auto, is_vision, task仅auto, pool_hint, model)`。要点:
  - api_key 不进明文,字符串取 blake2b-16 摘要,callable 按身份哈希(6966-6973);
  - **model 必须入键**:注释记录了真实事故——MoA 双 advisor 并发同键时,后建者会 close 前者正在用的 client,导致 sibling advisor 伪 APIConnectionError(6998-7006);
  - `auto` 才把 runtime 快照和 task 折进键(因为 auto 可能被 task 级 fallback 策略分流,6993-6996)。
- **异步命中校验**:loop 身份不进键,而是命中时检查 `cached_loop is current_loop and not closed`,失效则强关 httpx 并原位替换——把缓存规模钉在"每配置一条",解决了 gateway 回收线程导致的 fd 耗尽(#10200)与跨 loop 死锁(#2681)(7200-7256)。
- 并发建带锁裁决:输掉竞争的新 client 从未暴露给调用方,可安全立即 close(7300-7305)。
- **失效路径**:
  - 按 provider 清空:`_evict_cached_clients`(4093-4106,凭据刷新后);
  - 按实例清除:`_evict_cached_client_instance`(4108-4141)——连接错误后 client 的 httpx transport 已中毒,`_call_llm_impl` 末尾无条件驱逐(9332-9337,#23432);会顺着 `_real_client` 把包裹同一底层对象的 sync/async shim 一起清掉;
  - Nous 凭据刷新走 `_refresh_nous_auxiliary_client` 原位替换缓存条目(7020-7062)。
- **进程级生命周期**:`neuter_async_httpx_del()` 把 OpenAI SDK `AsyncHttpxClientWrapper.__del__` 打成 no-op(7065-7095,否则 GC 在 prompt_toolkit loop 上调度 aclose 触发 "Event loop is closed");`cleanup_stale_async_clients()` 每轮后清理死 loop 条目(7146-7162);`shutdown_cached_clients()` 退出前统一 close(7131-7143)。

### 1.7 `call_llm` 托管管线与错误階梯(缓存与 fallback 的消费方)

`_call_llm_impl`(8631-9338)顺序:解析 task 配置(8694)→ vision 走专用解析(8701-8726)→ 其余走 `_get_cached_client`(8728-8735)→ client 为 None 时:显式 provider 先试 task fallback_chain 再报错、auto/custom 转全 auto 链(8736-8768)→ `_build_call_kwargs` 统一整形(温度钉死表、max_tokens vs max_completion_tokens、Anthropic 图像块转换等,8787-8799)→ 流式路径直接返回原始迭代器(MoA 聚合器用,8809-8828)。

非流式的错误階梯(每类错误有专用谓词,3722-4092):
1. 同 provider 瞬态重试,指数退避,次数 = `auxiliary.transient_retries`;compression 超时例外——直接跳去 fallback,不再等第二个全额 timeout(8867-8919,#54465);
2. 温度不支持 → 去掉 temperature 重试一次(8921-8935);
3. Nous 专属自愈:模型下架 → 刷新 Portal 推荐模型重试(8996-9015);402 但 Portal 账户实为付费 → 刷新 JWT 重试(9017-9060);401 → 刷新 JWT 重试(9062-9084);
4. 通用 OAuth/凭据刷新 + 缓存驱逐 + 同 provider 重试(9086-9118);
5. 凭据池轮换恢复(9120-…);
6. **最终 fallback 階梯**(9206-9326):`should_fallback` 谓词并集;显式 provider 仅在"容量型错误"(402/连接/429/模型不兼容/无效响应)时越过用户意图;402 时把真实后端标 unhealthy 10 分钟(`_mark_provider_unhealthy`,9240-9248 → 3664-3680,TTL=600s,3635);fallback 顺序:task fallback_chain → (auto) 主 fallback 链 → (auto) `_try_payment_fallback` 走内置发现链跳过失败者(4891-4939) / (显式) `_try_main_agent_model_fallback` 以主聊天模型兜底(4942-5025,含"同 URL 不同模型不应连坐"的真实事故注释 4957-4963)。

unhealthy 缓存刻意只在进程内(3631-3633:双 profile 双 key 场景不应互相传染),每分钟至多一条 skip 日志(3699-3712)。

### 1.8 传输适配层(简述)

`resolve_provider_client`(5673-6483)是唯一 provider→client 路由器,保证返回物都暴露 `.chat.completions.create()`:Codex/Responses API 用 `CodexAuxiliaryClient` 适配(1168-1658),Anthropic Messages 线协议用 `AnthropicAuxiliaryClient`(1660-1875,`_maybe_wrap_anthropic` 依据 api_mode/`/anthropic` 后缀/已知主机判定,1996-2078),Bedrock、Gemini native、Copilot ACP 各有 shim;async 化统一走 `_to_async_client`(5583-5658,按 host 补 OpenRouter/Copilot-vision/Kimi UA/NIM 等 headers)。openai SDK 懒加载代理(`_OpenAIProxy`,65-112)省 ~240ms 冷启动同时保住 `patch("agent.auxiliary_client.OpenAI")` 的测试形态。SDK 内部重试被关掉(`max_retries=0`),让 Hermes 独占重试/超时预算(5655-5657,#54465)。

### 1.9 取舍与重实现要点

取舍:
- **可预测性 vs 成本**:默认副任务烧主模型的钱;逃生阀是 per-task override、`free_only`、`fallback_chain`。
- **单文件巨石(9,976 行)vs 分散**:解析、缓存、重试、计费钩子同文件强内聚,代价是可读性;结构靠区段注释维持。
- **进程内 unhealthy/缓存 vs 跨进程共享**:失败隔离优先(3631-3633)。
- **缓存淘汰不 close**:宁可延迟释放 fd,不冒 close 掉 in-flight client 的险。

重实现最小集:① runtime contextvar 发布/读取;② 三步 auto 链(main-first → 用户 fallback 策略 → 内置发现链);③ task config 裁决函数(显式>config>auto,"auto"哨兵归一);④ (…,api_key 摘要,…,model) 缓存键 + async loop 命中校验;⑤ 402 unhealthy TTL 缓存;⑥ 错误谓词族 + "模型级 vs 凭据级"失败范围区分;⑦ 统一 `.chat.completions.create()` 适配面。

---

## 2. model_metadata.py + models_dev.py — 上下文窗与能力来源

### 2.1 问题

上下文窗口决定压缩阈值、模型准入(64K 下限)、fallback 候选筛查;没有任何单一权威来源:provider 的 `/models` 有的报 provider 限制(Copilot 报 128K 而模型本体 400K)、有的不报(OpenAI schema 不含 context)、社区目录(OpenRouter)会错报(Kimi 32K)、本地服务器随时重载。于是做成**多源仲裁 + 分层缓存 + 错误反推**。

### 2.2 `get_model_context_length` 十步仲裁链

docstring 即规格(agent/model_metadata.py:2494-2516),按序:0 config 显式覆盖(2517-2519)→ 0a MoA 解包到聚合器(2527-2555)→ 0b custom_providers per-model 覆盖(2557-2572)→ 端点作用域元数据(2590-2595)→ **1 持久缓存**(2609-2689,带四类陈旧值失效:Kimi≤32K、MiniMax-M3≤204,800、Grok-4.3≤256,000、Bedrock 低于静态表;Nous URL 与 LM Studio、Codex OAuth 整体绕过缓存)→ 1b Bedrock 静态表+探测(2691-2737)→ 2 真 custom 端点 `/models` 探测 + 本地服务器探测 + Ollama `/api/show`(2746-2806)→ 4 Anthropic `/v1/models`(2808-2814)→ 5 provider 感知分支:Copilot 账户级 `/models`(2830-2841)、Nous Portal 权威探测(2843-2856)、Codex OAuth 账户目录(2857-2870)、GMI(2871-2876)、Ollama 泛化探测(2888-2899)、OpenRouter live(2900-2920)、**models.dev**(2922-2937)→ 6 OpenRouter 目录仅在 provider 未知时兜底(2939-2955)→ 7 本地服务器再探(2957-2965)→ 8 硬编码家族表最长键优先(2967-2976)→ 9 默认 256K + 去重告警(2978-2982)。

关键设计:**只持久化权威来源**。Nous 分支注释:

> agent/model_metadata.py:2848-2853
> ```python
>             # Persist ONLY portal-derived values.  Caching an OR-fallback
>             # value here would freeze in a wrong number on the first portal
>             # blip / auth glitch and step-1 would short-circuit it forever.
>             # OR's catalog is community-maintained and is precisely why the
>             # Kimi/Qwen DEFAULT_CONTEXT_LENGTHS overrides exist
> ```

Codex 同理只持久化 `source == "live"`(2864-2870)。Bedrock 静态表是**下限不是覆盖**:高于表的探测值保留(2660-2665)。

### 2.3 错误反推(从 provider 报错里读真窗口)

- `CONTEXT_PROBE_TIERS = [256K,128K,64K,32K,16K,8K]`(354-361),`get_next_probe_tier` 降档(1516-1521);
- `parse_context_limit_from_error`(1524-1551):7 个正则从错误文本抓极限值,1024–10M 合理性校验;
- `get_context_length_from_provider_error`(1554-1571):**只接受 provider 明说的更低值,不猜**——"Context-overflow recovery must not invent a new model window size";
- 区分两类错误:输入超窗(压缩解决)vs `max_tokens` 过大(`parse_available_output_tokens_from_error`,1574-1696:只降本次输出上限,不动 context_length);
- 消费侧:成功调用后只有"provider 确认过的"探测值才写盘(agent/conversation_loop.py:3310-3313 `_context_probe_persistable` 门)。

### 2.4 缓存策略汇总

| 缓存 | 位置 | TTL | 备注 |
|---|---|---|---|
| OpenRouter 目录 | 内存 + `~/.hermes` 磁盘 | 3600s(agent/model_metadata.py:134) | 网络失败退内存→退磁盘(1197-1210);(5,10) 连接/读取双超时防代理黑洞(1170-1173) |
| 端点 `/models` | 内存 per base_url | 300s(137) | 候选 URL 试 `/v1` 双形态;黑洞端点熔断(1234-1238) |
| 本地探测 | 内存 30s(398)+ 磁盘 300s(248) | | LM Studio 不持久化(可随时重载) |
| 持久上下文 | `~/.hermes/context_length_cache.yaml`(1417-1420) | 无 TTL | 键 `model@base_url`(1437-1444),失效需同步清内存探测缓存与 legacy 键形(1488-1513) |
| Codex OAuth 目录 | 内存,按 token 指纹隔离 | 3600s(2253) | |

### 2.5 models_dev.py — 能力目录

数据源 `https://models.dev/api.json`(agent/models_dev.py:39),社区维护 4000+ 模型 109+ provider(1-9)。核心是 stale-serve 缓存机:

> agent/models_dev.py:370-373
> ```python
>       2. Stale in-memory cache → return immediately and refresh in a single
>          background daemon thread. Callers never block on the network while
>          any cache exists; ``models.dev`` only changes when providers add
>          new models, so stale data is preferable to a foreground timeout.
> ```

要点:内存 fresh(TTL 3600)→ 内存 stale + 单飞后台刷新(`_start_background_refresh_models_dev`,333-358,刷新失败进程级退避 300s)→ 磁盘任意年龄即用(422-449)→ 仅无缓存时前台单飞网络(456-487);`allow_network=False` 供延迟敏感路径(gateway 路由身份检查)零网络(391-401);`_mark_stale_cache_grace` 只前移时间戳防止回退覆盖新刷新(269-279)。失败路径:提交与退避都持 `_models_dev_fetch_lock`,防"失败的后台刷新重臂退避,踩掉刚成功的 force_refresh"(282-315)。

查询面:`lookup_models_dev_context`(490-546,精确→大小写不敏感→`:cloud`/`-cloud` 后缀回退,后者防 kimi-k2.6 落到 OR 的 32768 错值触发 64K 门槛);`get_model_capabilities`(619-677):`tool_call/reasoning` 直读,vision 优先 `modalities.input` 含 "image",`attachment` 仅作回退(643-654);`ModelInfo/ProviderInfo` 数据类含成本、模态、截止日期(57-197)。provider id 映射表 `PROVIDER_TO_MODELS_DEV`(152)。

### 2.6 取舍与重实现要点

取舍:正确性排序为"权威 live 源 > 策展硬编码 > 社区目录 > 默认值",且**缓存只吸收权威值**;代价是解析链极长、每个 provider 一个特判分支。stale-serve 让首轮延迟可控,代价是新模型元数据最多滞后 1 小时 + 退避窗口。

重实现要点:① 分辨"provider 施加的限制"vs"模型本体窗口"(Copilot 案例);② 持久缓存必须带失效谓词(否则第一天的错值永生);③ 错误反推只信 provider 明说的数字;④ 默认值必须告警一次(`_warn_context_length_fallback`,372-385,防 8K 模型静默拿到 256K)。

---

## 3. usage_pricing.py + account_usage.py(+ credits_tracker 概述)

### 3.1 问题

每家 API 的 usage 对象形状不同、缓存 token 语义不同(含不含在 input 里)、价格来源不同(订阅内含/目录 API/官方价目表)。要给会话算钱,必须先归一形状,再按"计费路由"选价源。

### 3.2 usage 归一:4 种形状 → `CanonicalUsage`

`CanonicalUsage`(agent/usage_pricing.py:30-65):五桶 `input/output/cache_read/cache_write/reasoning` + `request_count`;`prompt_tokens = input+cache_read+cache_write`(41-42);`__add__` 支持 MoA 扇出求和,`raw_usage` 弃合并(48-65)。

`normalize_usage(response_usage, provider, api_mode)`(1205-1297)的 4 种形状:

1. **Anthropic**(1228-1232):四字段直读,`input_tokens` 本来就不含缓存;
2. **Codex Responses**(1233-1241):`input_tokens` 总量含缓存,从 `input_tokens_details.cached_tokens/cache_creation_tokens` 拆出后**减法**得净 input;
3. **OpenAI Chat Completions**(1242-1252、1264-1271):`prompt_tokens` 含缓存,`prompt_tokens_details` 拆分再减法;顶层 Anthropic 风格字段(`cache_read_input_tokens`/`cache_creation_input_tokens`)作代理回退(OpenRouter/Vercel/Cline 路由 Claude 时只在顶层给,1246-1251,移植 cline#10266);
4. **DeepSeek 原生**(1255-1263):顶层 `prompt_cache_hit_tokens`:

> agent/usage_pricing.py:1256-1263
> ```python
>             # DeepSeek's native API (api.deepseek.com) reports context-cache
>             # hits as top-level prompt_cache_hit_tokens (+ the complementary
>             # prompt_cache_miss_tokens; prompt_tokens = hit + miss), not the
>             # OpenAI nested shape. Without this, direct DeepSeek sessions
>             # always showed 0 cache-hit tokens (#61871).
>             cache_read_tokens = _to_int(
>                 getattr(response_usage, "prompt_cache_hit_tokens", 0)
>             )
> ```

reasoning tokens 双源:`output_tokens_details.reasoning_tokens`(Responses)优先,`completion_tokens_details.reasoning_tokens`(chat)回退——注释记录了单次调用 21K 隐藏思考 vs 500 可见 token 的实测(1273-1289)。

### 3.3 定价快照结构与路由

- `BillingRoute`(68-73):`(provider, model, base_url, billing_mode)`;`resolve_billing_route`(990-1037)判定四种 billing_mode:
  - `subscription_included`:openai-codex(1004-1005)→ 成本恒 $0、status="included";
  - `official_models_api`:openrouter / nous(1006-1009)→ live 目录价;
  - `official_docs_snapshot`:anthropic、openai/openai-api、minimax(-cn)、google 全家族名归一(1010-1030)、fireworks(1031-1034);
  - `unknown`:custom/local/其余(1035-1037)。
- `PricingEntry`(76-87):五价 + `source/source_url/pricing_version/fetched_at` 溯源字段;`_OFFICIAL_DOCS_PRICING` 是 `(provider, model) → PricingEntry` 的手工快照大表(105-970,约 860 行,含 GPT-5.6 缓存写 1.25x/读 0.10x 等注释);Bedrock/Anthropic 型号名各有归一化(区域前缀 `us./global./apac.`、`4.7→4-7`、尾部 `-v1:0` 剥离,1040-1095)。
- `get_pricing_entry`(1175-1202)选价顺序:included → 零价条目;openrouter → `fetch_model_metadata()`(OR 目录 per-token 价 ×1M,1131-1172);有 base_url → 端点 `/models` 元数据;最后 docs 快照。

### 3.4 成本计算与消费方(行号)

`estimate_usage_cost`(1300-1376):**严格模式**——某桶有用量但缺该桶价,整体返回 `unknown` 而非少算(1325-1346);Decimal 运算;OpenRouter 附"待对账"note(1365-1366)。消费方:

- 主循环:`agent/conversation_loop.py:3225`(normalize)与 `agent/conversation_loop.py:3355`(estimate,MoA 时换用聚合器真实槽位定价,3339-3361;advisor 费用按各自模型价另加,3364-3370);五桶累加进 session 计数(3318-3326);
- 辅助调用:`agent/aux_accounting.py:105/116`,由 `_validate_llm_response` 这个唯一验证卡点触发(agent/auxiliary_client.py:8096-8097),contextvar 携带 `(session_db, session_id)`,MoA 两任务除外防双计(agent/aux_accounting.py:43);
- MoA advisor 逐槽定价:`agent/moa_loop.py:578/593`;Codex 原生环:`agent/codex_runtime.py:143`;`/insights` 报表:`insights.py:66/505/654`;CLI 懒加载转发:`cli.py:96-105`。

### 3.5 account_usage.py — 账户级配额视图

面向 `/usage` 命令的三 provider 快照(`fetch_account_usage`,884-902):
- **Codex**(510-563):三层凭据解析(显式→native resolver 含池回退→直接池,452-507,只捕 `AuthError` 防"静默换成别的池账户的用量");backend 路径按 `/backend-api` 分流 `/wham/...` vs `/api/codex/...`(428-445,镜像 codex-rs);产出 Session/Weekly 双窗 + banked reset credits + 余额;另有 reset credit 兑换流程(587-749);
- **Anthropic**(751-809):仅 OAuth token 可用,`/api/oauth/usage` 映射 5h/7d/Opus周/Sonnet周 四窗(774-779),utilization ≤1 视作小数(785);
- **OpenRouter**(812-881):`/credits` 余额 + `/key` 限额窗与日/周/月用量。
消费方:`cli.py:11441`、`gateway/slash_commands.py:32,5024`、TUI(tui_gateway/methods_session.py:1286)。Nous 侧由 `build_nous_credits_snapshot`/`nous_credits_lines`/`build_credits_view`(137-427)把 credits_tracker 状态渲染成同一快照形状。

### 3.6 credits_tracker.py(概述级)

Nous 推理响应头 `x-nous-credits-*` 的硬化解析器(852 行)。要点:金额只以 micros 整数处理,`int()` 直接解析、**禁止** `int(float())`(2^53 精度损失会悄悄改钱数,62-79);USD 串按 `^-?\d+\.\d{2}$` 原样验证保存、绝不转 float(53、83-87);版本门 `!=1` 即 miss、`>1` 一次性警告(486-493);`subscription_micros` 是唯一允许负值(欠费)的字段(100);枯竭判定**只**看 `paid_access == False`,绝不用 `remaining==0`(127-134);`subscription_limit` 半对出现按双缺处理但整体解析仍成功(fail-open,557-562);`used_fraction` 以 limit 字段而非 `denominator_kind` 为准(137-150)。下游:`evaluate_credits_notices` 升级式通知(266)、`seed_credits_at_session_start`(799)、`_snapshot_from_credits_state` 桥接到 /usage 视图(agent/account_usage.py:283)。

### 3.7 取舍与重实现要点

取舍:成本"宁 unknown 不少算"(严格桶校验)vs 永远给个数;价目快照手工维护(精确、含缓存倍率语义)vs 全靠目录(会缺新模型、缺缓存价)。重实现要点:① 先归一后计价,归一层吸收所有 provider 形状差异(含"总量含缓存需减法"这一契约);② 计费路由与传输路由解耦(billing_mode 四态);③ 每个成本数字带 `source/status/pricing_version` 溯源;④ 辅助调用的计费挂在响应验证唯一卡点上,用 contextvar 免参数穿线。

---

## 4. 定案任务

### 4a. ▲ provider-runtime.md:196 "use their own independent provider auto-detection chain" — **判定:证伪(修正表述)**

原文(website/docs/developer-guide/provider-runtime.md:196):

> `- **Auxiliary tasks**: use their own independent provider auto-detection chain (see Auxiliary model routing above)`

精读结论:辅助任务确实有**自己的解析代码路径**(不参与主循环 `_try_activate_fallback` 的原位换模),这半句在"fallback 不共享激活状态"的上下文里成立;但"independent auto-detection chain"作为对默认行为的描述是**错的**——`_resolve_auto` Step 1(agent/auxiliary_client.py:5437-5532,上文 1.3 全序)**直接复用主 provider + 主 model**,独立发现链(openrouter→nous→local/custom→api-key)只是 Step 3 的兜底,且 Step 2 还优先尊重与主 agent 同源的 `fallback_providers` 配置(5534-5547)——即辅助路由既不"独立"于主运行时,也不"独立"于主 fallback 策略。第一轮在 5437 附近的认定成立并在此给出完整链条作证。同类过时表述还有 fallback-providers.md:14("independent provider resolution for side tasks")。另记一处文档漂移:provider-runtime.md:148-156 只列 6 类辅助任务(含已废弃的"memory flushes"式描述),而 hermes_cli/config_defaults.py:831-1070 实有 18 个任务块;其中 `provider: main` 的写法与代码一致(`_normalize_aux_provider`,agent/auxiliary_client.py:541-548 确有 `main` 别名)。

### 4b. ◇ 用量归一与定价未见于文档 — **判定:证实**

全量 grep `website/docs`:`normalize_usage`、`CanonicalUsage`、`estimate_usage_cost`、`usage_pricing` **零命中**。文档只暴露了机制的两个外围产物:
- session-storage.md:154 列 DB 迁移新增的计费列(`cache_read_tokens … estimated_cost_usd … pricing_version`);
- cli-commands.md:174 列 `--usage-file` 报告字段。

即:四形状归一、计费路由四态、价目快照、严格桶校验、辅助计费卡点等**机制本身完全未被文档描述**。这也符合本簇"实现先于文档"的整体观感。

---

## 5. 本簇对应测试(tests/)

相关测试文件(tests/agent/ 下,LT 层):`test_auxiliary_client.py`(4,428 行)、`test_auxiliary_main_first.py`(559)、`test_auxiliary_runtime_cache_key.py`、`test_auxiliary_transient_retry.py`、`test_auxiliary_concurrency.py`、`test_auxiliary_compression_timeout_floor.py`、`test_auxiliary_relay.py`、`test_auxiliary_config_bridge.py`、`test_auxiliary_transport_autodetect.py`、`test_auxiliary_named_custom_providers.py`、`test_auxiliary_anthropic_pool_fallback_regression.py`、`test_auxiliary_client_xai_oauth_recovery.py` 等;`test_model_metadata.py`(1,360)、`test_model_metadata_local_ctx.py`、`test_models_dev.py`(392);`test_usage_pricing.py`(314)、`test_billing_usage.py`、`test_account_usage.py`、`test_credits_tracker.py`、`test_credits_policy.py`、`test_nous_credits_snapshot.py` 等。

最像行为规格的三个(读代码,未运行):

1. **tests/agent/test_auxiliary_main_first.py** — `_resolve_auto` 的规格书。类 docstring 直书不变量:"`_resolve_auto()` must prefer main provider + main model for every user"(:23-24)。断言的行为:MoA 主用户的辅助调用必须解析到聚合器真实 provider/model 且丢弃 `moa://local` 假端点(:27-85,断言 `call_args.args == ("openrouter", "anthropic/claude-opus-4.8")` 且 `explicit_base_url in (None,"")`);主 provider 不可用时先走 `auxiliary.<task>.fallback_chain`、**不得**碰主链和 OpenRouter(:90-117,`mock_main_chain.assert_not_called()`);auto 请求不得把陈旧 config 模型配到 live fallback provider 上(:122-148,`mock_read_main_model.assert_not_called()`);Nous 视觉任务必须用 Portal 推荐而非文本主模型、Copilot 视觉必须带 vision 头(:241-428)。

2. **tests/agent/test_usage_pricing.py** — 归一与价目快照的规格。断言:DeepSeek 原生 `prompt_cache_hit_tokens=1500` 必须归一为 `cache_read=1500, input=500`(:18-37);OpenAI 兼容代理的顶层 Anthropic 缓存字段回退,`input = 1000-500-300 = 200`(:42-68);价目表不变量——deepseek-v4-pro 必须有价且等于 2026-07 降价后数值(:85-103)、废弃别名 `deepseek-chat/reasoner` 必须与 v4-flash 同价否则会话计费漂移(:108-122)、所有 Bedrock Claude 行必须带缓存价、跨区推理 profile(`us.`/版本尾缀)必须归一命中裸价键(:127-216)、Google/Vertex 各路由共享同一快照(:276-292)。

3. **tests/agent/test_model_metadata.py** — 上下文解析链的规格。断言:Codex OAuth live 目录缓存按 access-token 指纹隔离、探测失败退硬编码、live 值双向纠正陈旧缓存(:361-495);Nous 的 OR 回退值**不得**写入持久缓存、陈旧缓存必须被 Portal 权威值绕过并覆盖(:569-676);custom 端点探测失败要回落硬编码目录而非静默 256K(:714-805);本地 Ollama 优先 Modelfile `num_ctx` 而非 GGUF 训练上限(:806-837);Bedrock Claude 4.6 忽略陈旧 200K 缓存(:838-869);探测梯队严格降序、错误文本解析覆盖 vLLM 各种分隔符变体(:1015-1085)。

---

## 附:本轮观察到的文档-代码冲突清单(供台账)

1. provider-runtime.md:196 与 fallback-providers.md:14 —"独立自动探测链"表述与 `_resolve_auto` Step 1 main-first 事实相悖(定案 4a,证伪/修正);
2. provider-runtime.md:148-156 辅助任务清单(6 类)严重落后于 hermes_cli/config_defaults.py:831-1070(18 块),且含已移除的 session_search 时代口径;
3. 用量归一/定价机制在 website/docs 无任何机制级描述,仅剩 DB 列与 CLI 字段两处外围痕迹(定案 4b,证实);
4. auxiliary_client.py 模块 docstring(:7-15)自述的 auto 链与实现一致(main → OR → Nous → custom → anthropic → api-key),但未提 Step 2 的用户 fallback 策略优先(5534-5547)——模块内注释比模块头新。
