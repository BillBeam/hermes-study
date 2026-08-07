# R2-23 错误分类-重试-故障转移 + prompt cache 断点(子代理底稿)

> 由子代理精读产出,主线抽查定案 a/b/c/d 与 FailoverReason 枚举表。基线 863e31318。
> 范围:error_classifier(1841)、errors(13)、retry_utils(208)、
> chat_completion_helpers(4363)、prompt_caching(393)、rate_limit_tracker(246 交互点)。
>
> **重要发现(新增文档-代码冲突)**:conversation_loop.py:2330-2331 注释写"90s stale-stream
> detection, 60s read timeout"是**注释漂移**——实测流式 stale 默认 180s、读超时默认 120s
> (chat_completion_helpers.py:4063/3028;env-variables.md:802-803 与代码一致);90s 是**非流式**
> stale 基线(run_agent.py:1426)。据此已修正本项目 notes/r2-03 里沿用旧注释的表述。

# R2 精读底稿:错误分类-重试-故障转移 + prompt cache 断点(hermes-agent @ 863e313)

**结论:五机制闭环成立,文档四处需修正。**

分类器把每次 API 失败折叠成 `FailoverReason` + 4 个恢复位;主循环按位分派:重试(带抖动退避)、换凭据、走 fallback 链、压缩上下文或快速失败;interruptible 双路径(流式优先)用轮询线程 + 陈旧检测把"挂死的 HTTP"变成可分类异常;每次重试顶部按当前 provider 重贴 4 断点 prompt cache。以下逐机制精读,证据一律 `路径:行号 @ 863e313` + 逐字摘录。

## 0. 文件范围与实测行数(wc -l)

| 文件 | 实测行数 | 覆盖深度 |
|---|---|---|
| agent/error_classifier.py | 1841 | L1 全文 |
| agent/errors.py | 13 | L1 全文 |
| agent/retry_utils.py | 208 | L1 全文 |
| agent/chat_completion_helpers.py | 4363 | L1 全文 |
| agent/prompt_caching.py | 393 | L1 全文 |
| agent/rate_limit_tracker.py | 246 | L1(与 retry 交互点概述) |
| agent/conversation_loop.py | 7334 | 本簇相关段精读(retry 主循环、调用选择点、断点重贴) |

辅助取证:run_agent.py(非流式 stale 基线)、agent/agent_runtime_helpers.py(restore_primary_runtime、cache policy)、agent/system_prompt.py(静态前缀)、agent/agent_init.py(链构建、api_max_retries)。

---

## 1. 错误分类器(agent/error_classifier.py)

### 问题
每个 provider 用不同的状态码/错误体/措辞表达同一类失败(Z.AI 用 429 表示服务器过载;xAI 用 403 表示欠费;llama.cpp 用 500 表示上下文溢出;OpenRouter 把上游错误包在 `metadata.raw` 里)。散落在重试循环里的字符串匹配无法维护,且误分类的代价是具体的:把"参数不支持"当成上下文溢出会进入压缩死循环,把"证书坏了"当成瞬态错误会烧光重试预算。

### 机制:单入口 + 优先级流水线
`classify_api_error(error, *, provider, model, approx_tokens, context_length, num_messages)` 返回 `ClassifiedError`,恢复决策全部编码在 5 个字段里,主循环不再自行判断:

`agent/error_classifier.py:88-93 @ 863e313`
```python
    # Recovery action hints — the retry loop checks these instead of
    # re-classifying the error itself.
    retryable: bool = True
    should_compress: bool = False
    should_rotate_credential: bool = False
    should_fallback: bool = False
```

流水线顺序(docstring 自述,`agent/error_classifier.py:634-643`):1) provider 特例(content-policy、thinking 签名、tier gate、xAI 订阅)→ 2) HTTP 状态码 → 3) 结构化错误码 → 4) 消息模式 → 5) SSL 证书(fail-fast)→ 5b) SSL 瞬态 → 6) 断连+大会话→溢出 → 7b) stale 熔断器 → 8) 传输类型启发 → 9) unknown。**顺序即语义**:content-policy 必须先于状态码分类(400 安全拦截不能降级成 format_error,`:718-732`);证书校验必须先于 SSL 瞬态(证书错误消息也含 `[ssl:`,`:904-917`)。

输入归一化:状态码沿 `__cause__`/`__context__` 链最多走 5 层提取(`:1680-1696`);错误体同样走链,并会解析 OpenRouter 的 `error.metadata.raw` 内层 JSON(`:682-694`);无 `status_code` 的 `RateLimitError` 类型名强制视为 429(`:656-660`)。

### FailoverReason 枚举全表(枚举定义 `agent/error_classifier.py:24-72`)

| 值 | 触发条件(分类点) | 标志位 | 恢复动作(conversation_loop.py 消费点) |
|---|---|---|---|
| `auth` | 401(`:1021-1032`);403 非计费(`:1052-1056`);消息含 `_AUTH_PATTERNS`(`:1642-1648`);xAI Grok 订阅错误(SSE error 帧、无状态码,`:842-850`) | retryable=False, rotate=True(401/消息路径), fallback=True | provider 专属凭据刷新(codex `:3953-3963`、vertex `:3964-3969`…)→ 池轮转 `:3861-3868` → auth failover 上链 `:4509-4525` → 终局引导 |
| `auth_permanent` | **分类器从不产生**(仅枚举定义 `:29`、`is_auth` 属性 `:97`、context_compressor.py:79 消费)——预留给"刷新后仍失败"的上层标注 | — | abort |
| `billing` | 402 无瞬态信号(`_classify_402` `:1253-1279`);403/404/400/消息路径命中 `_BILLING_PATTERNS`(`:104-124`);结构化码 `_BILLING_ERROR_CODES`(`:134-143`,含 xAI `personal-team-blocked:spending-limit`) | retryable=False, rotate=True, fallback=True | Nous 付费凭据刷新一次 `:3844-3859` → 池轮转 → 立即上链 `:4426-4492`;终局回 `billing_block` 结构 `:5525-5528` |
| `rate_limit` | 429 默认分支(`:1151-1156`);402/400/无状态码 + 瞬态用量信号(`try again`/`resets at`…,`:1264-1271`, `:1429-1435`, `:1577-1583`) | retryable=True, rotate=True, fallback=True | Retry-After 优先(上限 600s,`:5531-5547`)→ 池轮转 → 立即上链(rate-limit 属 eager fallback `:4426-4430`) |
| `upstream_rate_limit` | 429 且 body 是 OpenRouter "Provider returned error" 包裹(`_is_openrouter_upstream_error` `:1798-1825`) | retryable=True, rotate=**False**, fallback=True | 换模型不换 key:绕过池恢复直接上链(`:4460-4466`);凭据是健康的,轮转会白白封禁 key ~24min(注释 `:1135-1140`) |
| `overloaded` | 503/529 无溢出体(`:1225`);429 + `_OVERLOADED_PATTERNS`(`:1130-1134`,Z.AI 用 429 表达过载 #14038);纯消息 `overloaded`(`:1596-1600`) | retryable=True(不 rotate!) | 同 key 退避重试;retry_count≥2 后算 transport failure 允许上链(`:4431-4450`) |
| `server_error` | 500/502 默认(`:1206`);5xx 兜底(`:1248`);空响应公告文案(`_EMPTY_PROVIDER_RESPONSE_PATTERNS`,显式 should_compress=False,`:1194-1199`, `:1398-1403`, `:1622-1627`) | retryable=True | 退避重试 |
| `timeout` | 传输异常类型表 `_TRANSPORT_ERROR_TYPES`(`:527-545`)/内建 Timeout/Connection/OSError(`:996-997`);408(`:1235-1236`);SSL 瞬态告警(`:927-928`);消息 `timed out`(`:1672-1673`);断连+推理模型(`:955-957`);stale 熔断 RuntimeError(retryable=False+fallback,`:983-992`) | retryable=True(熔断除外) | 重建客户端重试;连续失败后 transport failover 上链 |
| `ssl_cert_verification` | `_SSL_CERT_VERIFY_PATTERNS`(`certificate verify failed` 等,`:575-584`),在 SSL 瞬态之前检查 | retryable=False, fallback=False | 立即失败 + 可操作提示(仿 Claude Code v2.1.199,注释 `:568-571`);终局文案 `:5152-5156` |
| `context_overflow` | 400/500/503/消息命中 `_CONTEXT_OVERFLOW_PATTERNS`(`:275-319`);错误码 `context_length_exceeded`(`:1519-1524`);断连+大会话启发(`:961-969`);400 generic+大会话启发(`:1466-1479`) | retryable=True, should_compress=True | 压缩后重试(不 failover——换 provider 解决不了超长) |
| `payload_too_large` | 413(`:1114-1119`);消息含 `_PAYLOAD_TOO_LARGE_PATTERNS`(`:219-229`) | retryable=True, compress=True | 压缩重试;GitHub Models 8K 特判直接判死 `:4606-4629` |
| `image_too_large` | 400/消息命中 `_IMAGE_TOO_LARGE_PATTERNS`(Anthropic 5MB/8000px,`:236-246`),在 overflow 之前检查(shrink 更便宜,`:1309-1316`) | retryable=True | 原地缩图重试一次(`:3876-3891`) |
| `model_not_found` | 404/400 + `_MODEL_NOT_FOUND_PATTERNS`(`:322-340`,含 OpenRouter "no endpoints found that support tool use" PR#58446);裸 id 缺前缀目录核对(`_model_id_missing_known_prefix` `:343-365`,#78796);错误码表(`:1512-1517`);MoAPresetNotFoundError(`:883-884`) | retryable=False, fallback=True | 上链换模型。注意:**generic 404 归 unknown 可重试**(`:1102-1112`)——本地端点 URL 配错不该被误报成模型缺失 |
| `provider_policy_blocked` | OpenRouter 账户隐私守卫 404/400(`_PROVIDER_POLICY_BLOCKED_PATTERNS` `:427-431`) | retryable=False, fallback=**False** | 直接展示错误体里的修复 URL——账户级设置,换 provider 无效(注释 `:420-426`) |
| `content_policy_blocked` | 逐字 provider 安全拦截短语表(`:450-478`,OpenAI cyber/moderation、Anthropic safety、`content_filter`、MiniMax `new_sensitive` #32421),**流水线第一优先**(`:727-732`) | retryable=False, fallback=True | 立即上链;流式路径把它盖章到 partial-stub 上(`_content_filter_terminated`,chat_completion_helpers.py:4315-4338) |
| `format_error` | 400 兜底(`:1482-1486`);4xx 兜底(`:1239-1244`);5xx 携带请求校验信号(`:1176-1185`);无效消息数组(`_INVALID_MESSAGE_BODY_PATTERNS` `:383-390`,空 stub 400 不许进压缩循环);MoA 适配器 shape bug(fallback=False,`:868-876`) | retryable=False, fallback=True(多数) | 快速失败→上链 |
| `invalid_encrypted_content` | 400 + Responses replay blob 校验失败(码/消息,`:1323-1337`, `:1526-1531`) | retryable=True, fallback=False | 关闭本会话 reasoning replay、剥离缓存项、重试一次(`:4118-4145`) |
| `multimodal_tool_content_unsupported` | 400/消息命中 `_MULTIMODAL_TOOL_CONTENT_PATTERNS`(`:259-272`,#27344),在 image/overflow 之前(`:1296-1307`) | retryable=True | 剥 tool 消息里的图片、给 (provider,model) 记会话级降级标记、重试一次(`:3905-3909`) |
| `thinking_signature` | 400 + `thinking` + (`signature`\|`cannot be modified`\|`must remain as they were`)(`:752-765`),不 gate provider(OpenRouter 会代理 Anthropic 错误) | retryable=True, compress=False | 从 api_messages 剥 `reasoning_details` 重试(canonical 历史不动,防持久化污染,`:4081-4102`) |
| `long_context_tier` | 429 + `extra usage` + `long context`(Anthropic 分层门,`:767-777`) | retryable=True, compress=True | 压缩进普通层 |
| `oauth_long_context_beta_forbidden` | 400 + `long context beta` + `not yet available`(`:787-796`) | retryable=True | 会话级禁用 1M beta、重建 Anthropic 客户端、重试一次(`:3932-3951`,PR#17680 选了反应式恢复而非无条件摘 beta) |
| `llama_cpp_grammar_pattern` | 400 + `error parsing grammar` 等(`:806-821`) | retryable=True | 从 `agent.tools` 剥 `pattern`/`format` 重试一次(`:4156-4181`) |
| `unknown` | 兜底(`:1001`);generic 404(`:1109-1112`) | retryable=True | 退避重试 |

### 设计理由与取舍
- **模式表全部带出处注释**(issue 号:#14038、#15297、#18028、#27344、#32421、#52310、#58446、#78796、opencode#37848 移植),每条都是一次真实误分类的补丁。取舍:子串匹配脆弱(措辞一改就漏),换来的是零依赖、O(patterns) 且可在注释里逐条审计。
- **两个启发式是唯一的"赌"**:断连+大会话→溢出(`approx_tokens > context_length*0.6` 或小窗口下 `>120000`/`>200 条`,`:961-963`)与 400 generic+大会话→溢出(0.4/80000/80,`:1470-1472`)。两者都被多层前置排除项保护(空响应公告、无效消息体、参数校验、推理模型断连改判 timeout `:938-957`)。
- `unknown` 保守可重试:错误分类宁可多试三次,不可把可恢复错误判死。

### 重实现要点
1) 先归一化(状态码/错误体沿 cause 链提取,拆开聚合器包裹),再匹配;2) 恢复语义编码成正交布尔位而不是让调用方 switch 枚举;3) 顺序敏感的模式(cert vs ssl-alert、throttling vs too-many-tokens、unsupported-parameter vs max_tokens)必须写测试钉死;4) 给"服务器过载"留独立于 rate_limit 的通道,否则单 key 用户会被轮转逻辑饿死。

---

## 2. 重试退避(agent/retry_utils.py + conversation_loop 主循环)

### 机制
**抖动指数退避**(`agent/retry_utils.py:117-128`):

```python
    exponent = max(0, attempt - 1)
    if exponent >= 63 or base_delay <= 0:
        delay = max_delay
    else:
        delay = min(base_delay * (2 ** exponent), max_delay)
```
抖动为 `uniform(0, jitter_ratio*delay)`(默认 0.5),种子混入进程内带锁单调计数器 `time.time_ns() ^ (tick * 0x9E3779B9)`(`:124-126`)——目的写在模块 docstring:防多会话同击同一限流 provider 的 thundering-herd(`:1-6`)。

**主循环参数**(conversation_loop.py):
- 重试上限 `agent._api_max_retries`,默认 3,配置 `agent.api_max_retries`,下限钳 1(agent_init.py:1837-1843,#11616)。
- 分类错误路径:`Retry-After` 头优先、上限 600s(Anthropic Tier-1 重置 ~171s,120s 上限会提前撞墙,#26293,`conversation_loop.py:5538-5544`),否则:

`agent/conversation_loop.py:5547 @ 863e313`
```python
wait_time = _retry_after if _retry_after else jittered_backoff(retry_count, base_delay=2.0, max_delay=60.0)
```
- 无效响应(空 choices 等)路径用更宽的 5s/120s(`:2701`)。
- 退避睡眠切成 0.2s 片,片间查中断并保留 redirect(`:5583-5607`)。

**Provider 自适应层**:Z.AI Coding GLM-5.2 的 429 code-1305 过载,先走 3 次短退避,之后走 30/60/90/120s 长表 + 0.2 抖动(`adaptive_rate_limit_backoff` `retry_utils.py:162-191`);因为默认 max_retries=3 会让长表成死代码,循环检测到该错误时把上限抬到 `short+len(table)+1=8`(`zai_coding_overload_retry_ceiling` `:194-208`;消费点 conversation_loop.py:4442-4446)。

`parse_retry_after_seconds`(`retry_utils.py:38-87`)同时接受裸值和 headers 映射,支持数值与 RFC7231 HTTP-date,负值钳 0——被网关侧与测试共享。

### 与 rate_limit_tracker 的交互(概述)
rate_limit_tracker.py 是**纯被动观测**:解析 12 个 `x-ratelimit-*` 头(`:8-20`)为 `RateLimitState`,供 `/usage` 展示。捕获点在流建立回调:`agent._capture_rate_limits(response)`(chat_completion_helpers.py:3108),落到 `agent._rate_limit_state`(run_agent.py:3791-3806)。它进入 retry 决策的唯一路径是 Nous:429 到来时 `is_genuine_nous_rate_limit(headers=…, last_known_state=agent._rate_limit_state)` 用**上一次成功响应的桶状态**区分"账户真限流"(记入跨会话共享文件、跳过重试直接上链)与"上游容量瞬断"(正常退避)(conversation_loop.py:4547-4593)。Retry-After 等待值不从这里取,单独读错误响应头。

### 重实现要点
指数+抖动+上限三件套是底线;Retry-After 必须裁剪上限防病态值;把 provider 特例做成 `(wait, reason_label)` 纯函数注入主循环,而不是在循环里再长 if;**重试上限与退避表长度要有共享常量防脱钩**(`_ZAI_CODING_OVERLOAD_SHORT_ATTEMPTS` 的注释就是一次脱钩事故记录,`retry_utils.py:29-35`)。

---

## 3. Fallback 多级链(chat_completion_helpers.py: try_activate_fallback + agent_runtime_helpers.py: restore_primary_runtime)

### 链的构成
配置 `fallback_model`(单 dict 兼容)或列表 → 过滤出 provider+model 均非空的项(agent_init.py:1403-1411)。游标 `_fallback_index` 从 0 起。

### 推进协议(核心,chat_completion_helpers.py:1730-2115)
`try_activate_fallback(agent, reason)` 每调一次消费一个链元素;跳过用**递归重入**实现:

`agent/chat_completion_helpers.py:1764,1781-1782 @ 863e313`
```python
    if agent._fallback_index >= len(agent._fallback_chain):
        ...
        return False
    fb = agent._fallback_chain[agent._fallback_index]
    agent._fallback_index += 1
```
跳过路径(每条都 `return agent._try_activate_fallback(reason)` 吃下一个):本会话已标记不可用的 key(`_unavailable_fallback_keys`,`:1788-1790`)、字段无效(`:1793-1794`)、Nous 本地无 token(`:1796-1805`)、**与当前失败后端同一身份**(`BackendIdentity.build` + `should_skip_candidate`,身份语义集中在 agent.backend_identity,#22548/#70893/#62984,`:1812-1830`)、resolve 不出客户端(`:1855-1860`)、激活抛异常(`:2111-2115`)。

### 冷却与 #24996 防回放风暴
- rate_limit/billing/upstream_rate_limit 且正在离开 primary 时:指数冷却 `60*2^n` 封顶 14400s 写入 `_rate_limited_until`(`:1742-1763`);计数器由成功 restore 清零。
- 非限流原因走完非空链:armed 5s 短冷却(`_FALLBACK_EXHAUSTED_COOLDOWN_S=5.0` `:58`),取 `max` 不缩短已有窗口(`:1771-1780`)——否则网关每条消息 restore→重放全链,80k token 上下文 × 每 provider 重编组能把宿主打进 swap(注释 `:49-57`)。

### 切换时同步的运行时状态(`:1917-2109`,全景清单)
1) `_config_context_length=None`(防继承旧模型上下文窗,#22387);2) `model/provider/requested_provider/base_url/api_mode` 五元组;3) `_transport_cache.clear()`;4) `_fallback_activated=True`;5) **凭据池重绑**:池 provider ≠ fb provider 则清池并 `load_pool(fb_provider)`(#33163,`:1943-1969`);6) 客户端重建(anthropic_messages 走原生客户端 + OAuth 判定 `:1976-1988`;OpenAI 线保留 `_custom_headers` 防 Kimi 403 `:1989-2008`;有配置 timeout 立刻重建主客户端 `:2009-2014`);7) `sync_credential_pool_entry_id`;8) **缓存策略重评**:`_use_prompt_caching, _use_native_cache_layout = agent._anthropic_prompt_cache_policy(...)`(`:2019-2027`);9) 压缩器 `update_model`(新上下文窗,`:2039-2059`);10) reasoning_config 重解析(#21256,`:2065-2081`);11) 系统提示词身份行重写(见下);12) 状态通知(缓冲行 + `_pending_fallback_notice` 一次性成功通告 `:2087-2100`);13) stale 熔断计数清零(streak 度量的是旧 provider,#58962,`:2105-2109`)。

api_mode 判定链(`:1871-1915`):openai-codex→codex_responses;nous 走 `nous_api_mode(model)` 双线;anthropic 名称/`/anthropic` 后缀/api.anthropic.com 主机→anthropic_messages(#32243/#49247);Azure 强制 chat_completions;直连 OpenAI 或 GPT-5.x 需求→codex_responses;bedrock 主机→bedrock_converse。

### 身份重写与缓存温度
`rewrite_prompt_model_identity`(`:1672-1698`)只改缓存提示词里**最后一次出现**的 `Model:`/`Provider:` 行且不落库——failover 后新后端反正冷缓存,而 primary 恢复时把行改回去,提示词与存储副本字节一致、前缀缓存继续命中(restore 侧回写:agent_runtime_helpers.py:1722-1723)。进行中的请求由 `_sync_failover_system_message`(conversation_loop.py:969-993)刷新 `api_messages[0]`,且 `_rewrite_system_content_blocks`(`:934-966`)在系统消息已被拆成 [static, volatile] 两块时只改尾块文本,保住两个断点。

### Turn-scoped:restore_primary_runtime(agent_runtime_helpers.py:1449-1729)
每个新 turn 顶部调用,fallback 因此是**回合作用域**。要点:
- `_fallback_activated=False` 时也要重置 `_fallback_index=0`(链耗尽但未激活会永久卡死游标,#20465,`:1460-1469`);
- 门 1:`_rate_limited_until > time.monotonic()` → 留在 fallback(`:1471-1472`);
- 门 2(reset-aware):凭据池 `next_available_at()`(订阅型 provider 的 5 小时/每周窗口)未到 → 跳过 restore,避免"每回合两次缓存失效 + 两次全量重编组的必败尝试"(`:1495-1524`),fail-open;
- 恢复 13 类状态(模型五元组、客户端、缓存策略两标志、压缩器、池重绑+重选最优 entry #25205/#56885、reasoning_config),然后 `_fallback_activated=False; _fallback_index=0; _rate_limit_backoff_count=0`(`:1709-1712`)+ 清 stale streak + 身份行回写。

### 主循环触发点(conversation_loop.py,全集)
Nous 跨会话限流守卫(`:2163`)、空/畸形响应 eager(`:2605`)、无效响应重试耗尽(`:2678`)、限流/计费/上游限流 eager + transport≥2 次(`:4451-4492`,带 `_pool_may_recover_from_rate_limit` 例外 #11314)、auth 刷新失败(`:4519`)、非重试客户端错误(`:5126`)、重试耗尽(`:5349`,其前的一次性 primary transport 恢复会重置 `_fallback_index=0`/`_fallback_activated=False` 重开链,`:5333-5344`)、流式内层某些路径(`:6822`)。每次成功激活后统一:`retry_count=0; compression_attempts=0; _retry.primary_recovery_attempted=False`。

### 重实现要点
链推进要幂等可重入(游标+递归跳过);冷却写在"离开 primary"处、清在"成功回到 primary"处;**切换即全量运行时同步**——漏掉任何一项都是已编号的事故(池 #33163、上下文窗 #22387、缓存 #72626、reasoning #21256、headers #27907 同类);身份判等单独成模块,禁止在链逻辑里手写比较。

---

## 4. Interruptible 调用(chat_completion_helpers.py)

### 线程模型
非流式 `interruptible_api_call`(`:663-1153`):请求跑在 daemon 工作线程,主线程 `t.join(timeout=0.3)` 轮询(`:931-935`),每 ~30s 触活动心跳 + 改写等待提示(`:943-963`)。**中断如何打断 HTTP**:每请求独立客户端注册进 holder;关闭按调用线程分派——工作线程自己 `finally` 时 pop+真关;**陌生线程(轮询/看门狗)只 shutdown socket、绝不 close**,让工作线程阻塞的 recv 以 EPIPE/EOF 解开、FD 由属主释放(#29507 的 FD 复用事故:刚关的 TLS FD 被内核重分给 kanban.db,残留 SSL BIO 往 SQLite 头里写了 24 字节 TLS 记录):

`agent/chat_completion_helpers.py:730-737 @ 863e313`
```python
        with request_client_lock:
            request_client = request_client_holder.get("client")
            owner_tid = request_client_holder.get("owner_tid")
            stranger_thread = (
                request_client is not None
                and owner_tid is not None
                and owner_tid != threading.get_ident()
            )
```
中断时先置请求局部 `_request_cancelled` 再强关,工作线程据此把随之而来的传输错误当作预期后果吞掉,不当网络故障上报、不烧重试(#6600 级联中断挂 7 分钟的修复,`:697-705`, `:1127-1146`)。

### 陈旧检测(非流式)
基线 `_compute_non_stream_stale_timeout`:配置 → env `HERMES_API_CALL_STALE_TIMEOUT` → 推理模型下限 → **默认 90s**(2026-05 从 300s 降下来,让 fallback 更快接管),按上下文放大(>100k→≥240s,>50k→≥150s),隐式默认 + 本地端点 → `inf`(run_agent.py:1387-1447)。超时即陌生线程杀连接、`_bump_stale_streak`、合成 `TimeoutError`(`:1071-1125`)。Codex 另有三层:TTFB 无首字节 120s 默认(大请求放宽/可 strict)、事件空闲 12–180s 按体量、硬顶 `HERMES_CODEX_HARD_TIMEOUT_SECONDS=1500s`(#64507,`:814-920`)。

### 跨回合熔断(#58962)
`_consecutive_stale_streams`:每次 stale 击杀 +1,成功完成/换 provider/restore 清零;达 `HERMES_STREAM_STALE_GIVEUP=5` 时**入口即抛**、零网络等待(`:334-345`);分类器把该 RuntimeError 判成 `timeout, retryable=False, should_fallback=True`(error_classifier.py:983-992),第一击就上链——否则每次重试都瞬间撞熔断、烧光 max_retries 才 failover(实测 494 连败 3 天,注释 `:302-311`)。

### 内联直呼路径
`should_use_direct_api_call`(`:514-555`):cron 回合(#62151)与委派子代理(#60203)处于嵌套线程池,再压一层 interrupt worker 会在 socket 打开前死锁 → `direct_api_call`(`:566-660`)在会话线程内联执行,注册 `_active_request_abort` 保持跨线程可中断,15s 心跳防 stall monitor 误杀(`:558-563`)。

### 流式 `interruptible_streaming_api_call`(`:2528-4349`)
分发:直呼上下文→非流式入口;codex→借 `_codex_on_first_delta` 走非流式入口(其内部本就是流);bedrock→专用分支(boto3 EventStream 无法外部取消,看门狗只能弃调用、evict 客户端、靠熔断跨回合升级,`:2740-2773`);其余 chat_completions/anthropic_messages 走主体。

主体两层循环:
- **内层**(worker 内)`HERMES_STREAM_RETRIES=2` 即最多 3 次流尝试(`:3729-3732`);瞬态判定 = httpx 超时/连接错 + SSE error 帧措辞表 + 流解析错 + `EmptyStreamError`(`:3775-3782`, `:3898-3918`)。**已发 token 后的流死**:默认不重试(避免复读),唯一例外是 tool-call 在途且错误瞬态——静默重试并重置累积器/打"reconnecting"标(Clawdbot 式窄门,`:3796-3888`)。零 chunk 无 finish_reason → `EmptyStreamError`(`:3450-3459`);tool 参数半截且无 finish_reason → partial-stream stub(诚实报"流中断"而不是伪造 length 走加 max_tokens 死路,`:3461-3498`);纯文本无 finish_reason 同理(#32086,`:3505-3519`)。尝试有代际 fence(`_stream_attempt_state`),被取代的流的 chunk 丢弃计数(`:2947-3002`)。
- **外层**(主线程)0.3s 轮询:30s 心跳;**陈旧流检测**——`last_chunk_time` 距今超过阈值即杀客户端、bump streak、重置计时让内层重连(`:4164-4217`)。阈值:配置 → `HERMES_STREAM_STALE_TIMEOUT` 默认 **180s**,本地端点 900s(可配),按上下文放大 240/300s,推理模型下限表再抬(`:4058-4116`)。
- **httpx 读超时**:`HERMES_STREAM_READ_TIMEOUT` 默认 **120s**;本地端点抬到总超时;云端若 stale 阈值更大则抬平——否则 socket 读超时先于拥有重试与诊断权的 stale 检测器开火,杀掉健康的思考长停顿(`:3023-3058`)。connect/pool 钳 30/60s(握手不该吃推理预算,`:3059-3061`)。
- 错误后若已有部分投递:返回 `PARTIAL_STREAM_STUB_ID` + `finish_reason=length` 的 stub 让续写机制接管,`tool_calls=None` 防执行半截调用;吞掉前先用分类器盖 content-filter 章(`:4245-4343`)。

**⚠ 数字定案**:任务书沿用第一轮标注"90s 陈旧流检测/60s 读超时"。实测:**流式 stale 默认 180s、读超时默认 120s**(上引 `:4063`, `:3028`;website/docs/reference/environment-variables.md:802-803 与代码一致);**90s 是非流式 stale 基线**(run_agent.py:1426)。"90s/60s"仅存于 conversation_loop.py:2330-2331 的旧注释——这是一处**代码内注释漂移**,记录如下:

`agent/conversation_loop.py:2329-2331 @ 863e313`
```python
                # Always prefer the streaming path — even without stream
                # consumers.  Streaming gives us fine-grained health
                # checking (90s stale-stream detection, 60s read timeout)
```

### 重实现要点
1) "谁 close"必须按线程属主分派,陌生线程只 shutdown;2) 中断要有请求局部取消令牌,让自己造成的传输错误可识别;3) stale 检测与 SDK 读超时必须协调排序(检测器拥有恢复权,超时不得抢跑);4) 熔断计数属于 provider,换 provider 必清;5) 无 finish_reason 的流尾是三岔口(空流/半截工具/半截文本),各有不同下场,压成一种都是事故。

---

## 5. Prompt cache 断点(agent/prompt_caching.py,393 行全文)

### 问题
Anthropic 每请求最多 4 个 `cache_control` 断点。要同时满足:跨会话复用稳定系统前缀、会话内复用滚动历史、断点别浪费在 provider 会忽略的位置、failover 后按新 provider 政策重贴。

### 默认布局(模块 docstring 即规格,`:1-8`)
```
The default layout uses 4 cache_control breakpoints: the static system
prefix, the end of the system prompt, and the last 2 non-system messages.
When a static system prefix is unavailable, it falls back to one system
breakpoint plus the last 3 messages.
```

### 4 断点分配算法逐行(`apply_anthropic_cache_control` `:348-393`)
1. 空列表直返;浅拷贝列表,`_build_marker(ttl)` 造 `{"type":"ephemeral"}`(1h 加 `ttl`,`:96-101`)。
2. `messages[0]` 是 system → 深拷贝后交 `_apply_system_cache_markers`(`:373-380`),返回已用断点数:
   - 存储的 system 字符串以 `static_system_prefix` 开头且后缀非空 → 拆成两个 text part,前缀与后缀各带 marker,**用 2 个断点**(`:140-153`)。前缀块跨会话稳定(新会话也命中),后缀含时间戳/身份行等易变尾。
   - 后缀为空(整条即前缀)→ 整条打 1 个 marker——两段式会产生空 text block,原生 Anthropic 400(`:154-158`)。
   - 前缀缺失/不匹配 → 整条 1 个(legacy)。
3. `remaining = 4 - breakpoints_used`(`:382`)→ 取**能携带 marker 的**非 system 消息的末 `remaining` 条,各深拷贝后打 marker(`:383-391`)。有前缀时 remaining=2(末 2 条),无前缀时 remaining=3(即 legacy "system_and_3")。

### `_can_carry_marker` 排除规则(`:72-93`)
原生 Anthropic 布局:一律可(适配器会把顶层 marker 迁进块内)。envelope 布局(OpenRouter 等)只认 content part 内 marker,因此排除:空 content 消息(纯 tool_calls 的 assistant 空转)、空 tool 消息、list 末元素非 dict 的 content——这些位置的顶层 marker 会被 provider 无声忽略,**白烧 1/4 断点**:

`agent/prompt_caching.py:77-81 @ 863e313`
```python
    On the native Anthropic layout every message works (top-level markers are
    relocated by the adapter). On the envelope layout (OpenRouter et al.) only
    markers inside content parts are honored: empty-content messages (e.g.
    assistant turns that are pure tool_calls) and empty tool messages would
    receive a top-level marker the provider ignores — wasting one of the four
```
`_apply_cache_marker`(`:35-69`)是写入端镜像:str→包成单 text part;list→标最后一个 dict part;tool 消息原生放顶层、envelope 空则跳过(OpenRouter 顶层 tool marker 会**静默挂死**,`:47-52`)。谓词与写入端必须逐条一致(`:88-92` 注释明说)。

### direct_native_tool_cache 布局(`build_prompt_cache_plan` `:299-345`)
仅当目的地是 api.anthropic.com 原生 Messages 线(`_direct_native_anthropic_tool_cache_capability`,agent_runtime_helpers.py:1922-1936)且有工具时启用:断点分配改为——静态前缀 1 个(`mark_suffix=False, fallback_to_whole=False`,易变尾不标,`:330-337`)+ `planned_tools[-1]` 1 个(工具数组自成缓存段,`:338`)+ `_completed_transaction_endpoint_indexes(...)[-2:]` 2 个(`:339-343`)。端点选择算法(`:247-296`):只在**完整事务的合法末端**放断点——assistant(tool_calls) 后连续 tool 结果串的最后一条、非最末的 user 跳过、空 assistant 跳过、普通完结消息;半截事务(tool_calls 无结果)不设点,防止把必然要变的位置缓存住。plan 是 `PromptCachePlan(messages, tools)` 请求局部深拷贝,canonical 注册表永不带 marker(`:308-311`)。

### 剥离与 failover 重贴(#72626)
`strip_anthropic_cache_control`(`:166-216`):去顶层与 part 级 marker;**只把"装饰产物形状"**(单 text part,或 system 的两段拆分,且 part 键 ⊆ {type,text})拍回字符串——`""`-join 可证字节还原;有 `citations` 等额外键或天然多 part 的内容保结构只摘 marker;part 字典 copy-on-write,因为 content 可能别名持久历史(`:180-186`)。工具侧 `strip_anthropic_tool_cache_control` 深拷贝后 pop(`:219-225`)。

贴点时机:初次装饰在**所有转录变换之后、retry 循环之前**(conversation_loop.py:1838-1870,注释解释:早贴会把 str 变 list,躲过空白规范化,同一消息在滚动窗内外字节不同,精确破坏断点要保护的前缀)。**每次重试尝试顶部重贴**:

`agent/conversation_loop.py:2202-2208 @ 863e313`
```python
                # Same story for prompt-cache decoration (#72626): try_activate_
                # fallback refreshes the policy flags, but the decorated list
                # still carries the primary's breakpoints (or none). Strip and
                # re-render for the current provider before building kwargs.
                api_messages, _moa_prepared_request, tools_for_api = (
                    _redecorate_prompt_cache_for_provider(
```
`_redecorate_prompt_cache_for_provider`(`:1030-1100`)以**变异后的在飞请求**为源(保留缩图/ASCII 清洗等恢复成果)strip→按当前 `_use_prompt_caching/_use_native_cache_layout` 重建 plan;还兜住 cache-off primary 恢复的会话 failover 到 cache-on provider 时静态前缀缺失的情况(`_ensure_cached_system_prompt_static`→`reconstruct_static_prefix`,重建的 stable 层必须是存储提示词的字面前缀才启用,失败按存储串 memoize 防热路径反复 I/O,system_prompt.py:602-653)。

静态前缀来源:`build_system_prompt` 按 stable/context/volatile 三层拼装,`agent._cached_system_prompt_static = parts["stable"]`(system_prompt.py:578-580);策略函数 `anthropic_prompt_cache_policy`(agent_runtime_helpers.py:2059-2178+)决定 `(should_cache, native_layout)`:原生 Anthropic→(True,True);OpenRouter/Nous Claude、Kimi(#25970)、Qwen 家族→envelope;MoA 解析到真实聚合器再递归;`_cache_disabled` 一票否决(#33555/#76085)。

### 取舍与重实现要点
存储层永远是单一字符串/干净结构,缓存形状只存在于请求局部拷贝——代价是每次请求 deepcopy+重贴,换来 failover/压缩/持久化互不污染。重实现:1) 断点是稀缺预算,先写"哪里的 marker 会被忽略"的谓词,写入端与谓词共用判定;2) 静态前缀用"字面 startswith"校验而非信任重建;3) strip 必须可证字节还原,否则前缀缓存反被 strip 破坏;4) 空 text block、顶层 tool marker 等 provider 地雷要写成测试。

---

## 6. 定案任务

**a) ▲ provider-runtime.md:180 —— 证伪(文档描述的是已被替换的单级实现)。**
文档:`website/docs/developer-guide/provider-runtime.md:179 @ 863e313`
```
   - Returns `False` immediately if already activated or not configured
```
实际代码里 `_fallback_activated` **从不作为提前返回条件**(它只在成功时置 True,`chat_completion_helpers.py:1931`);返回 False 的唯一条件是链耗尽 `_fallback_index >= len(_fallback_chain)`(`:1764`),同一回合可多次调用逐级推进(第 3 节已引原文)。文档同页 `:173` 称触发点在 "run_agent.py 的主循环",实际主循环在 agent/conversation_loop.py(触发点全集见第 3 节)。测试佐证:tests/run_agent/test_provider_fallback.py:76 `test_advances_index`、`:91` `test_skips_unconfigured_provider_to_next`。

**b) ▲ context-compression-and-caching.md:396 —— 证伪其"默认"地位,修正为回退布局。**
文档 `:396-406` 把 "system_and_3"(system + 末 3 条)当作唯一策略。实际默认(有静态前缀时)是 **静态前缀 + system 尾 + 末 2 条**(prompt_caching.py:1-8 模块 docstring 即规格,第一轮认定正确);system_and_3 仅在 `static_system_prefix` 缺失/不匹配时回退(`:382-389`:`remaining = 4 - breakpoints_used`,前缀命中时 used=2)。文档还完全未提第三种 direct_native_tool_cache 布局(前缀+tools[-1]+末 2 事务端点,`:322-343`)。

**c) ▲ agent-loop.md:108 —— 证伪;第一轮认定成立。**
文档:`website/docs/developer-guide/agent-loop.md:108`:"API requests are wrapped in `_interruptible_api_call()`"。实际选择点 `agent/conversation_loop.py:2348 @ 863e313`:
```python
                _use_streaming = True
```
默认永远优先流式(注释 `:2329-2339`:"Always prefer the streaming path — even without stream consumers…for health checking"),分发在 `:2391-2394` → `agent._interruptible_streaming_api_call(...)`;非流式仅四个豁免:`_disable_streaming` 会话标记(`:2352-2353`)、copilot-acp(`:2358-2363`)、MoA 无消费者(`:2373-2374`)、测试 Mock 客户端(`:2375-2381`)。两函数关系:`interruptible_streaming_api_call`(chat_completion_helpers.py:2528)在 codex/直呼上下文**委派回** `_interruptible_api_call`(`:2553-2565`),后者对 codex 内部仍是流(`_run_codex_stream`)。附加发现:该选择点注释里的 "90s stale-stream detection, 60s read timeout"(`:2330-2331`)与代码实际默认 180s/120s 不符(见第 4 节定案),属注释漂移,应记入文档-代码冲突台账。

**d) ◇ FailoverReason 枚举驱动恢复未见于文档 —— 证实。**
`grep -rn "FailoverReason\|error_classifier\|classify_api_error" website/docs README.md AGENTS.md` 零命中。整个"分类→恢复位→主循环分派"机制(本簇的中枢)只存在于代码与测试中;provider-runtime.md 的 fallback 叙述停留在无分类器时代(触发点列的是裸 HTTP 状态码,`provider-runtime.md:173-176`)。

---

## 7. 测试对应(tests/ 行为规格)

本簇直接对应的测试文件(agent/run_agent 层,均 LT):`tests/agent/test_error_classifier.py`(1085)、`test_prompt_caching.py`(469)、`test_rate_limit_tracker.py`、`test_failover_identity.py`(354)、`test_turn_retry_state.py`、`test_non_stream_stale_timeout.py`、`test_codex_ttfb_watchdog.py`、`test_cascading_interrupt_6600.py`、`test_reasoning_stale_timeout_floor.py`、`test_unsupported_{parameter,temperature}_retry.py`;`tests/test_retry_utils.py`(210);`tests/run_agent/`:`test_provider_fallback.py`(347)、`test_24996_fallback_exhaustion_cooldown.py`(232)、`test_32646_fallback_429_after_timeout.py`(324)、`test_conversation_fallback_state.py`、`test_nous_429_fallback_reentry.py`、`test_nous_fallback_unavailable.py`、`test_init_fallback_on_exhausted_pool.py`、`test_fallback_reasoning_override.py`、`test_fallback_credential_isolation.py`、`test_stream_interrupt_retry.py`、`test_retry_status_buffer.py`、`test_jsondecodeerror_retryable.py`、`test_auth_provider_failover.py`、`test_switch_model_fallback_prune.py`。

**最像行为规格的 4 个:**

1. **tests/agent/test_error_classifier.py** —— 分类器的逐条契约:枚举成员齐全性(`:49-77`)、状态码/错误体沿 cause 链提取(`:101-134`)、401→auth+rotate、402 瞬态/计费二分、404 四分(计费/policy-block/model/generic-unknown)、429 三分(overload 体→overloaded 不轮转 `:310`;正常→rotate `:324`;上游包裹→upstream)、408→timeout 可重试(`:278`)、证书错误不可重试而 SSL 瞬态可(`:818`, `:834`)、大会话裸断连仍进压缩(`:789`)、无状态码 RateLimitError 强制 429(`:856`)。这份文件就是枚举表的可执行版本。
2. **tests/agent/test_prompt_caching.py** —— 断点预算与请求局部性:`test_t20880_...`(`:59-88`)断言工具重负载原生布局下 tools[-1] 带 marker、跨回合共享事务端点、`marker_count <= 4`;`test_copies_sections_and_keeps_canonical_tools_plain`(`:92-114`)断言 canonical messages/tools 字节不变、plan 是新对象、恰 4 marker;`test_unmarkable_endpoint_does_not_consume_a_slot`(`:116-130`)断言半截 tool_call 不烧断点;`test_static_prefix_equal_to_whole_prompt_emits_no_empty_block`(`:132-157`)断言零空 text block 上线。
3. **tests/run_agent/test_provider_fallback.py** —— 链协议规格:非法项过滤(`:51-63`)、耗尽返回 False(`:72`)、游标推进(`:76`)、未配置/抛异常 provider 递归跳到下一个(`:91`, `:107`)、fallback provider 的 env key 解析(`:122`)、Nous 双线 api_mode(anthropic 模型走 Messages 线,`:149`)、与当前后端同身份的链项跳过及全自指链返回 False(`:265-296`)、xai-oauth→xai 同宿主同模型允许(`:312`,身份轴规格)。
4. **tests/run_agent/test_24996_fallback_exhaustion_cooldown.py** —— 冷却语义的精确规格(冻结 `time.monotonic` 断言到秒):非限流耗尽 armed 恰好 `frozen + 5.0`(`:50-80`);无链不 armed(`:82`);限流耗尽保 60s 不被 5s 覆盖(`:91-112`);已有更长窗口取 max 不缩短(`:114-132`);连续限流指数 60→120→240 封顶 4h、restore 成功清零计数(`:135-196`)。

---

## 8. 机制簇总图(重实现者的一页纸)

```
API call ──interruptible(流式优先; 陌生线程只shutdown; stale=90s非流/180s流; 熔断@5)
   │ 异常
   ▼
classify_api_error ──→ ClassifiedError{reason, retryable, compress, rotate, fallback}
   │
   ├─ reason 专属一次性恢复(缩图/剥reasoning_details/关replay/剥pattern/关1M beta…)──continue
   ├─ rotate → 凭据池轮转 ──continue
   ├─ compress → 压缩重试 ──continue
   ├─ fallback(eager: 限流/计费/上游; auth刷新失败; 非重试客户端错; 重试耗尽)
   │     └─ try_activate_fallback: 游标推进+跳过+13项运行时同步+冷却
   │           └─ 成功: retry_count=0, 重贴cache断点, 同步system身份 ──continue
   ├─ retryable → Retry-After(≤600s) 或 jittered_backoff(2s/60s) [+Z.AI自适应] ──continue
   └─ 终局: 分reason文案 + failure_reason 返回
下一turn: restore_primary_runtime(门: _rate_limited_until / 池next_available_at)
```

未覆盖遗留(交后续轮):`agent/backend_identity.py`(身份判等语义)、`agent/credential_pool.py`(轮转细节)、`agent/nous_rate_guard.py`(跨会话断路器)、bedrock/codex 适配器内部——本簇只到其接口。
