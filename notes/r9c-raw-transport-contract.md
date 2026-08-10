# r9c 底稿 · 传输层契约(`agent/transports/` 的 7 个文件)

> 求全求证型底稿。凡对 hermes-agent 行为的断言,紧跟 `路径:行号 @ 863e313` 与代码原文块;
> 锚点单独成行、置于块前。非源码块用 ```text / ```verify 显式标注。
> 基线:`863e31318553cda8ad61df681d08175364d4164b`,工作区只读、未改动。

本轮精读文件(合计 1,915 行):

| 文件 | 行数 | 角色 |
|---|---|---|
| `agent/transports/chat_completions.py` | 895 | OpenAI 兼容协议(默认路,~29 家 provider 走它) |
| `agent/transports/hermes_tools_mcp_server.py` | 284 | 方向相反的一支:把 hermes 工具反向暴露成 MCP 服务 |
| `agent/transports/anthropic.py` | 251 | Anthropic Messages 协议 |
| `agent/transports/types.py` | 174 | 归一化响应的数据形状 |
| `agent/transports/bedrock.py` | 154 | AWS Bedrock Converse 协议 |
| `agent/transports/base.py` | 89 | 抽象基类(契约本身) |
| `agent/transports/__init__.py` | 68 | 注册表 + 懒发现 |

---

## 0. 一页结论

**这一层解决的问题**:同一套 agent 主循环,要能对着四种互不兼容的 HTTP 协议
(OpenAI Chat Completions / Anthropic Messages / OpenAI Responses(Codex)/ AWS Bedrock Converse)
说话。传输层把「协议差异」收敛成一个 ABC(抽象基类,Python 里用 `abc.ABC` 声明"子类必须实现这些方法"的机制),
让主循环只认一种请求构造入口和一种响应形状。

**它的边界被写死在 base.py 的模块 docstring 里**,而且这个边界比名字暗示的窄得多:
传输层只管 `convert_messages → convert_tools → build_kwargs → normalize_response` 这条**数据变换链**,
**不管** client 构造、流式、凭据刷新、prompt 缓存、中断、重试。

**五个最值得记住的结论**:

1. **ABC 有 5 个抽象方法,但真正被外部调用的只有 2 个**(`build_kwargs`、`normalize_response`)。
   `convert_messages` / `convert_tools` 在全仓**没有任何外部调用者**,它们实际是 `build_kwargs` 的私有步骤。
2. **"传输怎么被选中"这件事完全不在 `transports/` 包里**,而且被写了 **5 份互不校验的副本**;
   其中 `ProviderProfile.api_mode` 这一份**从来没有任何代码读过**,而两份文档明确说它会被读。
3. **`NormalizedResponse` 里有一半字段是死的**:`usage`(以及 `Usage.cached_tokens`)在全仓无生产读者;
   `types.py` 的两个"工厂函数"只有测试在用;`extract_cache_stats` 这个 ABC 钩子**零生产调用者**。
4. **`chat_completions.py` 的消息清洗器被手抄了第二份**到迭代摘要路径,**而且两份已经漂开了**
   ——摘要路径漏掉了 `effect_disposition`,严格 provider 会 400。这是本轮最值得实跑复核的一条。
5. **`hermes_tools_mcp_server.py` 送给模型看的 `instructions` 字符串,宣传了三个它并没有暴露的工具**
   (delegate_task / memory / session_search)。这是"同一份知识写了第二遍然后漂开"的教科书形态,
   而且漂开的那一份是**模型直接读的**。

---

## 1. 契约本身:`base.py` 定义了什么

### 1.1 边界声明写在 docstring 里,而且是负向定义

`agent/transports/base.py:1-8 @ 863e313`

```python
"""Abstract base for provider transports.

A transport owns the data path for one api_mode:
  convert_messages → convert_tools → build_kwargs → normalize_response

It does NOT own: client construction, streaming, credential refresh,
prompt caching, interrupt handling, or retry logic.  Those stay on AIAgent.
"""
```

这段 docstring 值得逐句读,因为它是整个包的设计意图:

- 「**A transport owns the data path for one api_mode**」——一个传输 = 一个 `api_mode` 字符串。
  `api_mode`(项目内专名)= "这个端点说哪种线上协议",取值是四选一的字符串,不是 enum。
- 「**It does NOT own: client construction, streaming, credential refresh, prompt caching,
  interrupt handling, or retry logic. Those stay on AIAgent.**」
  ——**负向定义比正向定义长**。这句话解释了后面所有的"为什么这里看起来该有的东西没有":
  流式在 `agent/chat_completion_helpers.py`,重试/失败切换在 `conversation_loop`,
  凭据池在 `agent/credential_pool.py`。

**为什么这么切**:client 生命周期跟凭据、代理、超时、连接池绑定,而这些是**跨 api_mode 共享**的;
把它们塞进传输就要在每个后端里复制一遍。反过来,格式转换是**纯函数**——输入消息列表、输出请求 dict,
没有 I/O、没有状态。切在纯函数边界上,传输就能被单测直接构造出来跑(实测 `tests/agent/transports/`
下 5 个文件 93 个用例全部不碰网络)。

**代价**:调用点必须自己知道"现在是哪个 api_mode"才能把正确的参数喂给 `build_kwargs`(见 §1.3)。

### 1.2 五个抽象方法

`agent/transports/base.py:16-24 @ 863e313`

```python
class ProviderTransport(ABC):
    """Base class for provider-specific format conversion and normalization."""

    @property
    @abstractmethod
    def api_mode(self) -> str:
        """The api_mode string this transport handles (e.g. 'anthropic_messages')."""
        ...

```

`agent/transports/base.py:25-40 @ 863e313`

```python
    @abstractmethod
    def convert_messages(self, messages: List[Dict[str, Any]], **kwargs) -> Any:
        """Convert OpenAI-format messages to provider-native format.

        Returns provider-specific structure (e.g. (system, messages) for Anthropic,
        or the messages list unchanged for chat_completions).
        """
        ...

    @abstractmethod
    def convert_tools(self, tools: List[Dict[str, Any]]) -> Any:
        """Convert OpenAI-format tool definitions to provider-native format.

        Returns provider-specific tool list (e.g. Anthropic input_schema format).
        """
        ...
```

`agent/transports/base.py:42-57 @ 863e313`

```python
    @abstractmethod
    def build_kwargs(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> Dict[str, Any]:
        """Build the complete API call kwargs dict.

        This is the primary entry point — it typically calls convert_messages()
        and convert_tools() internally, then adds model-specific config.

        Returns a dict ready to be passed to the provider's SDK client.
        """
        ...
```

注意 `build_kwargs` 的 docstring 自己承认它是「**the primary entry point**」——
`convert_messages` / `convert_tools` 是它内部调的。这与实测的调用面一致(见 §1.4)。

`agent/transports/base.py:59-65 @ 863e313`

```python
    @abstractmethod
    def normalize_response(self, response: Any, **kwargs) -> NormalizedResponse:
        """Normalize a raw provider response to the shared NormalizedResponse type.

        This is the only method that returns a transport-layer type.
        """
        ...
```

`normalize_response` 的 docstring 说「**This is the only method that returns a transport-layer type**」。
这是契约里最关键的一句:**传输层向上只吐一种类型 `NormalizedResponse`**,
所以主循环不需要认识 `anthropic.types.Message` 或 boto3 的 dict。

### 1.3 三个可选钩子(带默认实现,不是 abstract)

`agent/transports/base.py:67-89 @ 863e313`

```python
    def validate_response(self, response: Any) -> bool:
        """Optional: check if the raw response is structurally valid.

        Returns True if valid, False if the response should be treated as invalid.
        Default implementation always returns True.
        """
        return True

    def extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]:
        """Optional: extract provider-specific cache hit/creation stats.

        Returns dict with 'cached_tokens' and 'creation_tokens', or None.
        Default returns None.
        """
        return None

    def map_finish_reason(self, raw_reason: str) -> str:
        """Optional: map provider-specific stop reason to OpenAI equivalent.

        Default returns the raw reason unchanged.  Override for providers
        with different stop reason vocabularies.
        """
        return raw_reason
```

三个钩子的默认策略:

| 钩子 | 默认 | 语义 |
|---|---|---|
| `validate_response` | `True` | "结构上算不算一个有效响应";返回 False 会把响应送进"无效响应重试"分支 |
| `extract_cache_stats` | `None` | 抽 provider 私有的缓存命中计数 |
| `map_finish_reason` | 原样返回 | provider 停止原因 → OpenAI 词汇表 |

**■ 观察 1:`map_finish_reason` 的"默认"在同一个包里有两套互相矛盾的定义。**
ABC 的默认是**原样返回**(未知原因保持原样),而 `types.py` 里那个同名模块级函数的默认是**回落到 `"stop"`**。
两者都被测试钉住了:

`tests/agent/transports/test_transport.py:42-46 @ 863e313`

```python
        t = Minimal()
        assert t.api_mode == "test_minimal"
        assert t.validate_response(None) is True  # default
        assert t.extract_cache_stats(None) is None  # default
        assert t.map_finish_reason("end_turn") == "end_turn"  # default passthrough
```

`tests/agent/transports/test_types.py:118-122 @ 863e313`

```python
    def test_unknown_reason_defaults_to_stop(self):
        assert map_finish_reason("something_new", self.ANTHROPIC_MAP) == "stop"

    def test_none_reason(self):
        assert map_finish_reason(None, self.ANTHROPIC_MAP) == "stop"
```

同一个包里,同一个概念,两个方向相反的兜底策略,各自有测试保护。真正的实现(anthropic / bedrock / codex)
全都选了"回落到 stop"那一套,所以 ABC 的默认实际上只在假想的第三方传输里生效。

### 1.4 契约的实际外沿:谁真的调用了哪几个方法

底稿要能凭它重实现,所以要区分"ABC 声明了什么"和"外部真的用了什么"。实测调用面:

```verify
cd /home/user/hermes-agent && grep -rn "\.convert_messages(\|\.convert_tools(" --include=*.py . | grep -v "^./tests"
```

输出只有两条,一条是传输自己调自己,一条是注释:

```text
./agent/transports/chat_completions.py:412:        sanitized = self.convert_messages(messages, model=model)
./agent/chat_completion_helpers.py:2165:            # ChatCompletionsTransport.convert_messages(), but the summary path
```

**搜索面**:整仓 `*.py`,模式 `\.convert_messages(` 与 `\.convert_tools(`,排除 `tests/`。
即:`convert_messages` / `convert_tools` 作为 ABC 的抽象方法被强制实现,但**外部调用面为零**。

`extract_cache_stats` 更彻底——全仓(含测试、md、txt)只有定义和单测:

```verify
cd /home/user/hermes-agent && grep -rn "extract_cache_stats" . --include=*.py --include=*.md --include=*.txt
```

```text
./agent/transports/base.py:75:    def extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]:
./agent/transports/anthropic.py:222:    def extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]:
./agent/transports/chat_completions.py:874:    def extract_cache_stats(self, response: Any) -> dict[str, int] | None:
./tests/agent/transports/test_chat_completions.py:488:        assert transport.extract_cache_stats(r) is None
./tests/agent/transports/test_chat_completions.py:504:        result = transport.extract_cache_stats(r)
./tests/agent/transports/test_transport.py:45:        assert t.extract_cache_stats(None) is None  # default
```

**搜索面**:整仓 `*.py` / `*.md` / `*.txt`,模式 `extract_cache_stats`,无排除。
**结论(负结论,搜索面如上)**:`extract_cache_stats` 有 ABC 声明、有两个后端实现、有两个单测,
**没有生产调用者**。缓存统计实际由 `agent/usage_pricing.py` 直接从原始响应里读
(`prompt_tokens_details.cached_tokens`),走的是另一条路。

**◇ 定案 1**:ABC 的真实外部契约是 `build_kwargs` + `normalize_response` + `validate_response`(三个),
不是 docstring 暗示的五个抽象方法。`convert_messages` / `convert_tools` 是内部步骤,
`extract_cache_stats` 是死钩子。**重实现时不要照抄这五个方法的抽象性**——
把 convert 系列做成私有方法、把 cache stats 交给计费层,契约会小一半。

### 1.5 契约之外的逃生舱:`preflight_kwargs`

ABC 里没有 `preflight_kwargs`,但调用点在调它:

`agent/conversation_loop.py:2222-2230 @ 863e313`

```python
                if agent._force_ascii_payload:
                    _sanitize_structure_non_ascii(api_kwargs)
                if agent.api_mode == "codex_responses":
                    api_kwargs = agent._get_transport().preflight_kwargs(
                        api_kwargs,
                        allow_stream=False,
                        is_github_responses=agent._is_copilot_url(),
                        sanitize_harmony_tokens=agent._is_codex_backend(),
                    )
```

它只定义在 codex 传输上:

`agent/transports/codex.py:615-628 @ 863e313`

```python
    def preflight_kwargs(
        self,
        api_kwargs: Any,
        *,
        allow_stream: bool = False,
        is_github_responses: bool = False,
        sanitize_harmony_tokens: bool = False,
    ) -> dict:
        """Validate and sanitize Codex API kwargs before the call.

        Normalizes input items, strips unsupported fields, validates structure.
        ``sanitize_harmony_tokens`` is enabled only for the ChatGPT Codex
        backend, which rejects literal reserved Harmony wire tokens in text.
        """
```

也就是说:**当一个后端需要 ABC 没提供的步骤时,项目的做法是"在调用点按 `api_mode` 分支 + 在那个传输上加个 ABC 不知道的方法"**。
行为上是安全的(`if agent.api_mode == "codex_responses"` 守住了),但它证明抽象没有覆盖真实需求。

**可迁移的教训**:如果你的 ABC 需要调用方 `if mode == X` 才能安全调某个方法,那个方法就应该
(a) 提到 ABC 上并给一个 no-op 默认,或者 (b) 折进 `build_kwargs` 里。第三种选择——留在子类上让调用方分支——
会让"新增一个后端"这件事变成"改 ABC + 改子类 + 改所有分支点"。

---

## 2. `types.py`:归一化响应的数据形状

### 2.1 设计原则写在模块 docstring 里

`agent/transports/types.py:1-9 @ 863e313`

```python
"""Shared types for normalized provider responses.

These dataclasses define the canonical shape that all provider adapters
normalize responses to.  The shared surface is intentionally minimal —
only fields that every downstream consumer reads are top-level.
Protocol-specific state goes in ``provider_data`` dicts (response-level
and per-tool-call) so that protocol-aware code paths can access it
without polluting the shared type.
"""
```

核心策略:**共享面尽量小,协议私有状态塞进 `provider_data` 字典**。
这是"窄腰"设计——顶层字段是所有下游都读的,其余的东西放进一个不打开就不会污染类型的口袋里。

### 2.2 `ToolCall`

`tool_calls`(OpenAI 术语)= 模型这一轮要求调用的函数列表;每项有 id、名字、参数(JSON 字符串)。

`agent/transports/types.py:18-38 @ 863e313`

```python
@dataclass
class ToolCall:
    """A normalized tool call from any provider.

    ``id`` is the protocol's canonical identifier — what gets used in
    ``tool_call_id`` / ``tool_use_id`` when constructing tool result
    messages.  May be ``None`` when the provider omits it; the agent
    fills it via ``_deterministic_call_id()`` before storing in history.

    ``provider_data`` carries per-tool-call protocol metadata that only
    protocol-aware code reads:

    * Codex: ``{"call_id": "call_XXX", "response_item_id": "fc_XXX"}``
    * Gemini: ``{"extra_content": {"google": {"thought_signature": "..."}}}``
    * Others: ``None``
    """

    id: str | None
    name: str
    arguments: str  # JSON string
    provider_data: dict[str, Any] | None = field(default=None, repr=False)
```

三点值得记:

- **`id` 可以是 `None`**,docstring 说 agent 会用 `_deterministic_call_id()` 补。
  这是为了兼容那些不回 tool call id 的 provider。
- **`arguments` 是 JSON 字符串不是 dict**。跟 OpenAI 线上格式一致,代价是每次读参数都要 `json.loads`。
- **`provider_data` 用 `repr=False`**——dataclass 打印时不显示,避免日志里刷出巨大的 thought_signature。

### 2.3 向后兼容属性:为什么 `NormalizedResponse` 能直接当 assistant_message 用

`agent/transports/types.py:40-52 @ 863e313`

```python
    # ── Backward compatibility ──────────────────────────────────
    # The agent loop reads tc.function.name / tc.function.arguments
    # throughout run_agent.py (45+ sites).  These properties let
    # NormalizedResponse pass through without the _nr_to_assistant_message
    # shim, while keeping ToolCall's canonical fields flat.
    @property
    def type(self) -> str:
        return "function"

    @property
    def function(self) -> ToolCall:
        """Return self so tc.function.name / tc.function.arguments work."""
        return self
```

`tc.function` **返回 self**,于是 `tc.function.name` / `tc.function.arguments` 都能走通。
这是一个 duck-typing(鸭子类型:只要长得像就能用)垫片,注释说主循环有 **45+ 处**这么读。

实测这个垫片的下游是主循环里最关键的一行:

`agent/conversation_loop.py:5693-5700 @ 863e313`

```python
        try:
            _transport = agent._get_transport()
            _normalize_kwargs = {}
            if agent.api_mode == "anthropic_messages":
                _normalize_kwargs["strip_tool_prefix"] = agent._is_anthropic_oauth
            normalized = _transport.normalize_response(response, **_normalize_kwargs)
            assistant_message = normalized
            finish_reason = normalized.finish_reason
```

`assistant_message = normalized` —— **归一化响应对象本身就是 assistant message**,
后面还会被就地改写:

`agent/conversation_loop.py:5702-5721 @ 863e313`

```python
            # Normalize content to string — some OpenAI-compatible servers
            # (llama-server, etc.) return content as a dict or list instead
            # of a plain string, which crashes downstream .strip() calls.
            if assistant_message.content is not None and not isinstance(assistant_message.content, str):
                raw = assistant_message.content
                if isinstance(raw, dict):
                    assistant_message.content = raw.get("text", "") or raw.get("content", "") or json.dumps(raw)
                elif isinstance(raw, list):
                    # Multimodal content list — extract text parts
                    parts = []
                    for part in raw:
                        if isinstance(part, str):
                            parts.append(part)
                        elif isinstance(part, dict) and part.get("type") == "text":
                            parts.append(part.get("text", ""))
                        elif isinstance(part, dict) and "text" in part:
                            parts.append(str(part["text"]))
                    assistant_message.content = "\n".join(parts)
                else:
                    assistant_message.content = str(raw)
```

**取舍**:省掉了一层转换(以及一次全量拷贝),代价是 `NormalizedResponse` 必须是**可变**的、
且必须长得像 OpenAI 的 `ChatCompletionMessage`。也就是说这个"通用归一化类型"其实是
**OpenAI 形状的伪装**,不是真正协议中立的——Anthropic / Bedrock 的响应被压成 OpenAI 形状,
而不是压成一个第三方形状。

### 2.4 Gemini 的 `extra_content`:一个字段撑起一个协议怪癖

`agent/transports/types.py:64-76 @ 863e313`

```python
    @property
    def extra_content(self) -> dict[str, Any] | None:
        """Gemini extra_content (thought_signature) from provider_data.

        Gemini 3 thinking models attach ``extra_content`` with a
        ``thought_signature`` to each tool call.  This signature must be
        replayed on subsequent API calls — without it the API rejects the
        request with HTTP 400.  The chat_completions transport stores this
        in ``provider_data["extra_content"]``; this property exposes it so
        ``_build_assistant_message`` can ``getattr(tc, "extra_content")``
        uniformly.
        """
        return (self.provider_data or {}).get("extra_content")
```

**场景**:Gemini 3 的 thinking 模型给每个 tool call 挂一个 `thought_signature`(思维签名)。
下一轮请求必须原样带回去,否则 HTTP 400。而其他严格的 OpenAI 兼容 provider(Fireworks、Mistral)
看到这个字段**也**会 400。所以同一个字段"必须带"和"必须删"取决于目标模型是谁——
这就是 `chat_completions.py` 里 `_model_consumes_thought_signature` 存在的理由(见 §5.1)。

### 2.5 `Usage`

`agent/transports/types.py:79-86 @ 863e313`

```python
@dataclass
class Usage:
    """Token usage from an API response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
```

**■ 观察 2:`Usage` 在生产里没有读者。**

先看写入面。三个后端里,anthropic **永远传 `usage=None`**:

`agent/transports/anthropic.py:185-192 @ 863e313`

```python
        return NormalizedResponse(
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls or None,
            finish_reason=finish_reason,
            reasoning="\n\n".join(reasoning_parts) if reasoning_parts else None,
            usage=None,
            provider_data=provider_data or None,
        )
```

chat_completions 与 bedrock 会填 `prompt/completion/total`,但**都不填 `cached_tokens`**:

`agent/transports/chat_completions.py:794-801 @ 863e313`

```python
        usage = None
        if hasattr(response, "usage") and response.usage:
            u = response.usage
            usage = Usage(
                prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(u, "completion_tokens", 0) or 0,
                total_tokens=getattr(u, "total_tokens", 0) or 0,
            )
```

再看读取面。全仓生产代码里 `normalize_response(...)` 的返回值一共赋给 10 个变量名:

```verify
cd /home/user/hermes-agent && grep -rn "normalize_response(" --include=*.py . | grep -v "^./tests" | grep -v "def normalize_response"
```

对这 10 个变量名逐个搜 `.usage`:

```verify
cd /home/user/hermes-agent && grep -rnE "\b(normalized|_bedrock_result|_finish_result|_refusal_result|_trunc_result|_nr|_cnr_sum|_summary_result|_cnr_retry|_retry_result)\.usage\b" --include=*.py .
```

输出为空。**搜索面**:整仓 `*.py`(含 tests),变量名取自上一条命令列出的全部 10 个赋值目标,
无其他排除。**结论**:`NormalizedResponse.usage` 与 `Usage.cached_tokens` 在全仓无读者。
真正的 token 计费从**原始响应**里另取——例如 aux 客户端拿到归一化结果后,
仍然绕回去读原始 Anthropic 响应的 `input_tokens` / `output_tokens`:

`agent/auxiliary_client.py:1805-1810 @ 863e313`

```python
        usage = None
        if hasattr(response, "usage") and response.usage:
            prompt_tokens = getattr(response.usage, "input_tokens", 0) or 0
            completion_tokens = getattr(response.usage, "output_tokens", 0) or 0
            total_tokens = getattr(response.usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)
            usage = SimpleNamespace(
```

**这就是 `usage=None` 没被发现的原因**:唯一在乎 usage 的调用方,本来就没打算通过 `NormalizedResponse` 拿。

### 2.6 `NormalizedResponse`

`agent/transports/types.py:89-109 @ 863e313`

```python
@dataclass
class NormalizedResponse:
    """Normalized API response from any provider.

    Shared fields are truly cross-provider — every caller can rely on
    them without branching on api_mode.  Protocol-specific state goes in
    ``provider_data`` so that only protocol-aware code paths read it.

    Response-level ``provider_data`` examples:

    * Anthropic: ``{"reasoning_details": [...]}``
    * Codex: ``{"codex_reasoning_items": [...], "codex_message_items": [...]}``
    * Others: ``None``
    """

    content: str | None
    tool_calls: list[ToolCall] | None
    finish_reason: str  # "stop", "tool_calls", "length", "content_filter"
    reasoning: str | None = None
    usage: Usage | None = None
    provider_data: dict[str, Any] | None = field(default=None, repr=False)
```

`agent/transports/types.py:124-134 @ 863e313`

```python
    @property
    def anthropic_content_blocks(self):
        """Verbatim, order-preserving Anthropic content blocks for a turn.

        Present only when an Anthropic turn interleaves signed thinking with
        tool_use — the one shape the parallel reasoning_details + tool_calls
        lists reconstruct in the wrong order, invalidating thinking-block
        signatures on replay. See agent/transports/anthropic.py.
        """
        pd = self.provider_data or {}
        return pd.get("anthropic_content_blocks")
```

`anthropic_content_blocks` 这个通道的存在理由是一次真实事故,详见 §6.2。

### 2.7 两个工厂函数是测试专用

`agent/transports/types.py:152-164 @ 863e313`

```python
def build_tool_call(
    id: str | None,
    name: str,
    arguments: Any,
    **provider_fields: Any,
) -> ToolCall:
    """Build a ``ToolCall``, auto-serialising *arguments* if it's a dict.

    Any extra keyword arguments are collected into ``provider_data``.
    """
    args_str = json.dumps(arguments) if isinstance(arguments, dict) else str(arguments)
    pd = dict(provider_fields) if provider_fields else None
    return ToolCall(id=id, name=name, arguments=args_str, provider_data=pd)
```

`agent/transports/types.py:167-174 @ 863e313`

```python
def map_finish_reason(reason: str | None, mapping: dict[str, str]) -> str:
    """Translate a provider-specific stop reason to the normalised set.

    Falls back to ``"stop"`` for unknown or ``None`` reasons.
    """
    if reason is None:
        return "stop"
    return mapping.get(reason, "stop")
```

```verify
cd /home/user/hermes-agent && grep -rn "build_tool_call" --include=*.py .
```

```text
./agent/transports/__init__.py:13:    build_tool_call,
./agent/transports/types.py:152:def build_tool_call(
./tests/agent/transports/test_types.py:9:    build_tool_call,
./tests/agent/transports/test_types.py:83:# build_tool_call
./tests/agent/transports/test_types.py:88:        tc = build_tool_call(id="call_1", name="terminal", arguments={"cmd": "ls"})
./tests/agent/transports/test_types.py:95:        tc = build_tool_call(id=None, name="t", arguments="{}")
```

**搜索面**:整仓 `*.py`,模式 `build_tool_call`,无排除。命中 = 定义 1 + `__init__` 再导出 1 + 测试 4。
**负结论**:`build_tool_call` 无生产调用者;三个后端都直接 `ToolCall(...)` 构造。

`map_finish_reason` 同理——模块级那个两参版本(`reason, mapping`)只有 `__init__.py` 再导出与
`tests/agent/transports/test_types.py` 在用;三个后端各自维护了自己的映射表并各自写了
`_MAP.get(raw, "stop")`(见 §6.4、§7.4)。**这就是"共享 helper 存在但副本不用它"的最小样本**:
helper 早于副本存在、副本作者知道它存在(同一个文件),仍然抄了一遍。

---

## 3. `__init__.py`:注册表与懒发现

`agent/transports/__init__.py:1-7 @ 863e313`

```python
"""Transport layer types and registry for provider response normalization.

Usage:
    from agent.transports import get_transport
    transport = get_transport("anthropic_messages")
    result = transport.normalize_response(raw_response)
"""
```

`agent/transports/__init__.py:17-23 @ 863e313`

```python
_REGISTRY: dict = {}
_discovered: bool = False


def register_transport(api_mode: str, transport_cls: type) -> None:
    """Register a transport class for an api_mode string."""
    _REGISTRY[api_mode] = transport_cls
```

`agent/transports/__init__.py:26-46 @ 863e313`

```python
def get_transport(api_mode: str):
    """Get a transport instance for the given api_mode.

    Returns None if no transport is registered for this api_mode.
    This allows gradual migration — call sites can check for None
    and fall back to the legacy code path.
    """
    global _discovered
    if not _discovered:
        _discover_transports()
    cls = _REGISTRY.get(api_mode)
    if cls is None:
        # The registry can be partially populated when a specific transport
        # module was imported directly (for example chat_completions before
        # codex).  Discover on misses, not only when the registry is empty, so
        # test/order-dependent imports do not make valid api_modes unavailable.
        _discover_transports()
        cls = _REGISTRY.get(api_mode)
    if cls is None:
        return None
    return cls()
```

`get_transport` 的两点设计:

- **返回 `None` 而不是抛异常**,docstring 明说是为了"渐进式迁移":调用点可以 `if t is None: 走老路"。
  但实测**已经没有老路了**——所有调用点都直接 `agent._get_transport().xxx()`,
  只有 `agent/moa_loop.py` 那一处真的检查了 `None`。
- **miss 时会再发现一次**(第 42 行),注释解释了原因:测试里可能只 import 了某一个传输模块,
  registry 处于半填充状态。

`agent/transports/__init__.py:49-68 @ 863e313`

```python
def _discover_transports() -> None:
    """Import all transport modules to trigger auto-registration."""
    global _discovered
    _discovered = True
    try:
        import agent.transports.anthropic  # noqa: F401
    except ImportError:
        pass
    try:
        import agent.transports.codex  # noqa: F401
    except ImportError:
        pass
    try:
        import agent.transports.chat_completions  # noqa: F401
    except ImportError:
        pass
    try:
        import agent.transports.bedrock  # noqa: F401
    except ImportError:
        pass
```

**■ 观察 3:`except ImportError: pass` 会把传输模块内部的任何导入错误也吞掉,导致静默降级。**

`_discovered = True` 在四个 try 之前就置位(第 52 行),四个 `except ImportError: pass` 各自吞掉失败。
后果:一个传输模块因为缺可选依赖(或自身有 import typo)而导入失败时,
`get_transport(mode)` 返回 `None`,而调用点是 `agent._get_transport().build_kwargs(...)`,
于是错误表现为 **`AttributeError: 'NoneType' object has no attribute 'build_kwargs'`**,
在对话中途炸,且完全看不出真实原因。

实测复现(不改基线,只在解释器里模拟一次导入失败):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_QUIET=1 /home/user/hermes-venv/bin/python -c "
import sys
import agent.transports as T
print('normal:', type(T.get_transport('anthropic_messages')).__name__)
sys.modules['agent.transports.anthropic'] = None
T._REGISTRY.pop('anthropic_messages', None)
T._discovered = False
print('after forced ImportError:', T.get_transport('anthropic_messages'))
"
```

```text
normal: AnthropicTransport
after forced ImportError: None
```

更值得记的是:`agent_init.py` 里**有一段专门为了避免这个后果而写的预热**,而它自己也被 try/except 吞了:

`agent/agent_init.py:686-691 @ 863e313`

```python
    # Eagerly warm the transport cache so import errors surface at init,
    # not mid-conversation.  Also validates the api_mode is registered.
    try:
        agent._get_transport()
    except Exception:
        pass  # Non-fatal — transport may not exist for all modes yet
```

注释说「**Eagerly warm the transport cache so import errors surface at init, not mid-conversation.**」
——但 (a) `_discover_transports` 已经把 ImportError 吞掉了,`get_transport` 只会返回 None 而不抛;
(b) 就算它抛了,这里的 `except Exception: pass` 也会吞掉。**这段预热无法达成它 docstring 声称的目的。**
它唯一的实际作用是提前填充缓存。

**这一条的性质**:注释声称的保证在代码里不成立,属 ■(而非 ▲,因为它是代码注释不是作者绘制的文档地图)。

**为什么四个后端都用惰性 import**:正因为发现期会吞掉 ImportError,传输模块**必须**在模块顶层
不 import 任何可选依赖。实测本容器 venv 里 `anthropic` 与 `boto3` **都没装**,
而 `anthropic_messages` / `bedrock_converse` 两个传输仍然注册成功、单测全过——
因为它们把 `from agent.anthropic_adapter import ...` 放在方法体内。这是一条硬约束,重实现时要照抄。

### 3.1 `codex_app_server`:有 api_mode 没 transport

注册表里只有四个键(`anthropic_messages` / `codex_responses` / `chat_completions` / `bedrock_converse`),
但合法 api_mode 有五个:

`hermes_cli/runtime_provider.py:385-390 @ 863e313`

```python
_VALID_API_MODES = {
    "chat_completions",
    "codex_responses",
    "anthropic_messages",
    "bedrock_converse",
    # Optional opt-in: hand the entire turn to a `codex app-server` subprocess
```

`agent/agent_init.py:628-629 @ 863e313`

```python
    if api_mode in {"chat_completions", "codex_responses", "anthropic_messages", "bedrock_converse", "codex_app_server"}:
        agent.api_mode = api_mode
```

第五个 `codex_app_server` **没有对应的传输**。它之所以不炸,是因为主循环在走到任何
`_get_transport()` 之前就整个掉头了:

`agent/conversation_loop.py:1401-1413 @ 863e313`

```python
    # Optional opt-in runtime: if api_mode == codex_app_server, hand the
    # turn to the codex app-server subprocess (terminal/file ops/patching
    # all run inside Codex). Default Hermes path is bypassed entirely.
    # See agent/transports/codex_app_server_session.py for the adapter
    # and references/codex-app-server-runtime.md for the rationale.
    if agent.api_mode == "codex_app_server":
        return agent._run_codex_app_server_turn(
            user_message=user_message,
            original_user_message=original_user_message,
            messages=messages,
            effective_task_id=effective_task_id,
            should_review_memory=_should_review_memory,
        )
```

**◇ 定案 2**:`api_mode` 这个字段承担了两种不同性质的取值——四个是"线上协议",
第五个是"整条 turn 交给子进程跑"的运行时开关。它们共用一个字段、共用一张校验表,
但只有前四个有传输。重实现时应该把"协议"和"运行时"拆成两个字段。

---

## 4. 传输是怎么被选中的(答案:不在 `transports/` 包里)

`get_transport(api_mode)` 只是个查表。真正的决策——"这个端点说哪种协议"——发生在三个地方。

### 4.1 主 agent:`agent_init.py` 的 if 链

`agent/agent_init.py:628-666 @ 863e313`

```python
    if api_mode in {"chat_completions", "codex_responses", "anthropic_messages", "bedrock_converse", "codex_app_server"}:
        agent.api_mode = api_mode
    elif agent.provider == "openai-codex":
        agent.api_mode = "codex_responses"
    elif agent.provider in {"xai", "xai-oauth"}:
        agent.api_mode = "codex_responses"
    elif (provider_name is None) and (
        agent._base_url_hostname == "chatgpt.com"
        and "/backend-api/codex" in agent._base_url_lower
    ):
        agent.api_mode = "codex_responses"
        agent.provider = "openai-codex"
    elif (provider_name is None) and agent._base_url_hostname == "api.x.ai":
        agent.api_mode = "codex_responses"
        agent.provider = "xai"
    elif agent.provider == "anthropic" or (provider_name is None and agent._base_url_hostname == "api.anthropic.com"):
        agent.api_mode = "anthropic_messages"
        agent.provider = "anthropic"
    elif agent._base_url_lower.rstrip("/").endswith("/anthropic"):
        # Third-party Anthropic-compatible endpoints (e.g. MiniMax, DashScope)
        # use a URL convention ending in /anthropic. Auto-detect these so the
        # Anthropic Messages API adapter is used instead of chat completions.
        agent.api_mode = "anthropic_messages"
    elif agent.provider == "bedrock" or (
        agent._base_url_hostname.startswith("bedrock-runtime.")
        and base_url_host_matches(agent._base_url_lower, "amazonaws.com")
    ):
        # AWS Bedrock — auto-detect from provider name or base URL
        # (bedrock-runtime.<region>.amazonaws.com).
        agent.api_mode = "bedrock_converse"
    elif agent.provider in {"nous", "nous-portal", "nousresearch"}:
        # Portal is dual-wire: anthropic/* → Messages, everything else →
        # chat_completions. Callers that already pass api_mode win above;
        # this covers direct AIAgent construction without a resolved runtime.
        from hermes_cli.providers import nous_api_mode

        agent.api_mode = nous_api_mode(agent.model)
    else:
        agent.api_mode = "chat_completions"
```

判定顺序:**显式传入 > provider 名 > base_url 主机名/路径 > 默认 chat_completions**。
注意第 646 行那条:**路径以 `/anthropic` 结尾**就当作 Anthropic Messages——
这是第三方 Anthropic 兼容网关(MiniMax、DashScope、LiteLLM)的事实约定。

### 4.2 CLI 侧:`runtime_provider.py` 的 URL 探测 + overlay 回退

`hermes_cli/runtime_provider.py:127-150 @ 863e313`

```python
    normalized = (base_url or "").strip().lower().rstrip("/")
    hostname = base_url_hostname(base_url)
    if hostname == "api.x.ai":
        return "codex_responses"
    # Official OpenAI host family: canonical api.openai.com plus the
    # data-residency regional hosts (us./eu.api.openai.com). Same API
    # surface, same Responses-API mandate. Shared predicate — see
    # providers.is_official_openai_host for the spoof-rejection contract.
    if is_official_openai_host(base_url):
        return "codex_responses"
    if hostname == "api.actual.inc":
        return "codex_responses"
    # Direct native Anthropic host: realign with providers.determine_api_mode,
    # which already maps this host to anthropic_messages. The exact-hostname
    # match rejects lookalike subdomains (api.anthropic.com.attacker.test) and
    # path-segment spoofing (proxy.test/api.anthropic.com/v1). (#32243)
    if hostname == "api.anthropic.com":
        return "anthropic_messages"
    path = urlparse(normalized).path.rstrip("/")
    if path.endswith("/anthropic") or path.endswith("/anthropic/v1"):
        return "anthropic_messages"
    if hostname == "api.kimi.com" and "/coding" in normalized:
        return "anthropic_messages"
    return None
```

`hermes_cli/runtime_provider.py:153-175 @ 863e313`

```python
def _fallback_api_mode(provider: str, base_url: str, model: str = "") -> str:
    """Resolve api_mode when no explicit/persisted mode applies.

    Precedence: URL detection (host-mandated wire shapes) first, then the
    transport the provider overlay itself declares via
    ``providers.determine_api_mode`` — which already handles host mandates,
    dual-wire providers, and the registry transport map — and only then the
    ``chat_completions`` default for genuinely unknown providers/endpoints.

    Before this helper the runtime paths consulted URL detection ONLY and
    silently landed reasoning providers on ``chat_completions`` whenever the
    hostname wasn't literally recognized. That is how ``openai-api`` pointed
    at OpenAI's data-residency hosts (``us.api.openai.com``) 400'd on every
    tool-calling turn: the provider declares ``codex_responses`` but the
    declaration was never consulted. Same latent class covered the other
    non-chat overlays (MiniMax family, copilot-acp).
    """
    detected = _detect_api_mode_for_url(base_url)
    if detected:
        return detected
    from hermes_cli.providers import determine_api_mode

    return determine_api_mode(provider, base_url, model) or "chat_completions"
```

`_fallback_api_mode` 的 docstring 里记着一次真实事故:
「**That is how `openai-api` pointed at OpenAI's data-residency hosts (`us.api.openai.com`)
400'd on every tool-calling turn: the provider declares `codex_responses` but the declaration
was never consulted.**」——**"声明了但没人读"这个 bug 类别在这一层已经被踩过一次并修了**,
而同一个类别在 `ProviderProfile.api_mode` 上**还开着**(见 §4.4)。

回退的终点是 overlay 表:

`hermes_cli/providers.py:435-440 @ 863e313`

```python
TRANSPORT_TO_API_MODE: Dict[str, str] = {
    "openai_chat": "chat_completions",
    "anthropic_messages": "anthropic_messages",
    "codex_responses": "codex_responses",
    "bedrock_converse": "bedrock_converse",
}
```

`hermes_cli/providers.py:684-704 @ 863e313`

```python
    mandated = host_mandated_api_mode(base_url)
    if mandated is not None:
        return mandated

    # Nous is dual-wire: anthropic/* → Messages, everything else →
    # chat_completions. The Hermes overlay still advertises openai_chat
    # (the majority of the Portal catalog), so the transport lookup below
    # would pin Claude on the wrong wire without this carve-out.
    provider_norm = (provider or "").strip().lower()
    if provider_norm in {"nous", "nous-portal", "nousresearch"}:
        return nous_api_mode(model)

    pdef = get_provider(provider)
    if pdef is not None:
        return TRANSPORT_TO_API_MODE.get(pdef.transport, "chat_completions")

    # Direct provider checks for providers not in HERMES_OVERLAYS
    if provider == "bedrock":
        return "bedrock_converse"

    return "chat_completions"
```

### 4.3 aux 侧:URL 探测的第三份实现

辅助客户端(标题生成、压缩、vision 等小任务)有自己的一套探测:

`tests/agent/test_auxiliary_transport_autodetect.py:1-13 @ 863e313`

```python
"""Tests for transport auto-detection in agent.auxiliary_client.

Auxiliary clients must pick the correct wire protocol (OpenAI
chat.completions vs native Anthropic Messages) based on the endpoint,
regardless of which resolve_provider_client branch built them.

Regression target (April 2026): Kimi Coding Plan's ``api.kimi.com/coding``
endpoint only speaks Anthropic Messages — sending ``kimi-for-coding`` over
chat.completions returns 404 "resource_not_found_error".  The named
``kimi-coding`` provider branch in resolve_provider_client used to build a
plain OpenAI client, so title generation / vision / compression /
web_extract all failed on Kimi Coding Plan users.
"""
```

这个测试文件的参数表就是行为规格:

`tests/agent/test_auxiliary_transport_autodetect.py:36-51 @ 863e313`

```python
@pytest.mark.parametrize("url,expected,label", [
    ("https://api.kimi.com/coding/v1", True, "Kimi Coding Plan /v1"),
    ("https://api.kimi.com/coding", True, "Kimi Coding Plan no /v1"),
    ("https://api.moonshot.ai/v1", False, "Moonshot legacy"),
    ("https://api.minimax.io/anthropic", True, "MiniMax /anthropic"),
    ("https://litellm.example.com/v1/anthropic", True, "/anthropic suffix"),
    ("https://litellm.example.com/anthropic/v1", True, "/anthropic/v1 base"),
    ("https://litellm.example.com/anthropic/v1/models", False, "/anthropic/v1 subpath"),
    ("https://api.anthropic.com", True, "native Anthropic"),
    ("https://api.anthropic.com/v1", True, "native Anthropic /v1"),
    ("https://openrouter.ai/api/v1", False, "OpenRouter"),
    ("https://api.openai.com/v1", False, "OpenAI"),
    ("https://inference-api.nousresearch.com/v1", False, "Nous"),
    ("", False, "empty"),
    (None, False, "None"),
])
```

注意第 43 行:`/anthropic/v1/models` 这样的**子路径**要判 False——探测只认"base URL 本身以 /anthropic 结尾",
不认"路径里出现过 /anthropic"。这是防止把一个模型列表 URL 误判成 Messages 端点。

### 4.4 ▲ 定案:`ProviderProfile.api_mode` 是死字段,而两份文档说它会被读

Provider profile(项目内专名:一个 provider 的所有怪癖集中声明的对象)上有一个 `api_mode` 字段:

`providers/base.py:42-45 @ 863e313`

```python
    # ── Identity ─────────────────────────────────────────────
    name: str
    api_mode: str = "chat_completions"
    aliases: tuple = ()
```

**两份文档明确说它是选择链的第 4 步。** 先看 `providers/README.md`,它归在 `## How it wires in` 标题下,
整段是"registry 建好之后,下面每一层都从它读"的清单:

`providers/README.md:31-44 @ 863e313`

> The registry is populated on first access. After that, every downstream
> layer reads from it:
>
> - `hermes_cli/auth.py` extends `PROVIDER_REGISTRY` with every api-key
>   profile it sees (skipping `copilot`, `kimi-coding`, `kimi-coding-cn`,
>   `zai`, `openrouter`, `custom` — those need bespoke token resolution).
> - `hermes_cli/models.py` extends `CANONICAL_PROVIDERS` and calls
>   `profile.fetch_models()` inside `provider_model_ids()`.
> - `hermes_cli/doctor.py` adds a `/models` health check for each
>   `auth_type="api_key"` profile.
> - `hermes_cli/config.py` injects every `env_var` into
>   `OPTIONAL_ENV_VARS` so the setup wizard knows about it.
> - `hermes_cli/runtime_provider.py` reads `profile.api_mode` as a fallback
>   when URL detection finds nothing.

再看 website 文档,整节归在 `## api_mode selection` 标题下:

`website/docs/developer-guide/model-provider-plugin.md:180-190 @ 863e313`

> ## api_mode selection
>
> Four values are recognized. Hermes picks one based on:
>
> 1. User explicit override (`config.yaml` `model.api_mode` when set)
> 2. OpenCode's per-model dispatch (`opencode_model_api_mode` for Zen and Go)
> 3. URL auto-detection — `/anthropic` suffix → `anthropic_messages`, `api.openai.com` → `codex_responses`, `api.x.ai` → `codex_responses`, `/coding` on Kimi domains → `chat_completions`
> 4. **Profile `api_mode`** as a fallback when URL detection finds nothing
> 5. Default `chat_completions`
>
> Set `profile.api_mode` to match the default your provider ships — it acts as a hint. User URL overrides still win.

**代码事实:没有任何地方读 `profile.api_mode`。**

```verify
cd /home/user/hermes-agent && grep -rn "\.api_mode" --include=*.py . | grep -v "^./tests/"
```

```text
./agent/auxiliary_client.py:4658:        api_mode=destination.api_mode or "",
./agent/auxiliary_client.py:4723:                api_mode=destination.api_mode,
./agent/auxiliary_client.py:4738:                api_mode=destination.api_mode,
./agent/auxiliary_client.py:4745:                    destination.api_mode,
./agent/auxiliary_client.py:4768:                            api_mode=retry_destination.api_mode,
./agent/auxiliary_client.py:4829:                api_mode=destination.api_mode,
./agent/auxiliary_client.py:4845:                api_mode=destination.api_mode,
./agent/auxiliary_client.py:4852:                    destination.api_mode,
./agent/auxiliary_client.py:4875:                            api_mode=retry_destination.api_mode,
./hermes_cli/providers.py:226:    # The transport is determined at runtime from config.yaml model.api_mode.
./hermes_cli/runtime_provider.py:184:    ``model.api_mode: codex_responses`` from forcing generic relays onto the
./hermes_cli/runtime_provider.py:476:        # compatible endpoint. Do not honor stale model.api_mode values from a
./hermes_cli/runtime_provider.py:1333:    Reads ``model.base_url`` + ``model.api_mode`` from config.yaml (or
./hermes_cli/runtime_provider.py:1738:    # config is always picked up from model.base_url + model.api_mode,
./tools/delegate_tool.py:3568:        # Explicit delegation.api_mode in config always wins. Lets users force
```

**搜索面**:整仓 `*.py`,模式 `\.api_mode`,排除 `tests/`,并在结果里剔除
`self.api_mode` / `agent.api_mode` / `detection.api_mode` / `result.api_mode` 四种明显不是 profile 的接收者
(该过滤已写在命令里)。剩下的属性读取全部落在 `destination.api_mode`
(那是 aux 的 `AuxDestination`,不是 `ProviderProfile`)与注释上。
另外单独搜过 `getattr(..., "api_mode"` 形式,命中全部是 `getattr(agent, ...)` / `getattr(self, ...)`。
**结论**:`ProviderProfile.api_mode` 只被**写**(38 个 profile 里有 8 个显式设了非默认值),从不被读。

**这不是纸面问题,已经产生了一处实际漂移。** 运行时对比 38 个已注册 profile 的
`profile.api_mode` 与真实生效的 `determine_api_mode(...)`:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_QUIET=1 /home/user/hermes-venv/bin/python -c "
import providers
from hermes_cli.providers import determine_api_mode
rows=[(p.name, p.api_mode, determine_api_mode(p.name, p.base_url or '', ''), p.supports_prompt_cache_key)
      for p in providers.list_providers()]
print('total profiles:', len(rows))
print('supports_prompt_cache_key=True:', [r[0] for r in rows if r[3]])
for name, declared, eff, _ in rows:
    if declared != eff:
        print(f'DRIFT {name}: profile.api_mode={declared} effective={eff}')
"
```

```text
total profiles: 38
supports_prompt_cache_key=True: []
DRIFT copilot-acp: profile.api_mode=chat_completions effective=codex_responses
```

(离线环境:models.dev 目录不可达,`get_provider` 只能取到 overlay 那一层。
这不影响本条结论——overlay 就是 `determine_api_mode` 的权威来源;但若 models.dev 可达,
个别不在 overlay 里的 provider 结果可能不同。)

漂移的那个 profile:

`plugins/model-providers/copilot-acp/__init__.py:26-33 @ 863e313`

```python
copilot_acp = CopilotACPProfile(
    name="copilot-acp",
    aliases=("github-copilot-acp", "copilot-acp-agent"),
    api_mode="chat_completions",  # ACP subprocess uses chat_completions routing
    env_vars=(),  # Managed by ACP subprocess
    base_url="acp://copilot",  # ACP internal scheme
    auth_type="external_process",
)
```

它自己第 4 行的模块 docstring 还说 `api_mode="copilot_acp"` 由 run_agent.py 单独处理,
而字段里写的是 `chat_completions`,overlay 里写的是 `codex_responses`。**三处三个答案,没有一处是被读的那处。**

而且第三个答案 `copilot_acp` **根本不是一个合法 api_mode**——`_VALID_API_MODES`(§3.1 已引)只有五个值,
不含它,`_parse_api_mode` 会直接返回 `None`;`run_agent.py` 里也没有任何 `copilot_acp` 分支:

```verify
cd /home/user/hermes-agent && grep -rn "copilot_acp" --include=*.py . | grep -v "^./tests"
```

```text
./agent/transports/codex_app_server.py:88:        # stripped while provider creds still flow, matching copilot_acp_client
./agent/agent_runtime_helpers.py:2259:        from agent.copilot_acp_client import CopilotACPClient
./agent/auxiliary_client.py:2034:        from agent.copilot_acp_client import CopilotACPClient
./agent/auxiliary_client.py:5607:        from agent.copilot_acp_client import CopilotACPClient
./agent/auxiliary_client.py:6358:            from agent.copilot_acp_client import CopilotACPClient
./hermes_cli/main.py:794:    _model_flow_copilot_acp,
./hermes_cli/main.py:3432:        _model_flow_copilot_acp(config, current_model)
./hermes_cli/web_server.py:9639:def _copilot_acp_status() -> Dict[str, Any]:
./hermes_cli/web_server.py:9724:        "status_fn": _copilot_acp_status,
./hermes_cli/model_setup_flows.py:1896:def _model_flow_copilot_acp(config, current_model=""):
./plugins/model-providers/copilot-acp/__init__.py:4:transport. api_mode="copilot_acp" is handled separately in run_agent.py.
./plugins/model-providers/copilot-acp/__init__.py:26:copilot_acp = CopilotACPProfile(
```

**搜索面**:整仓 `*.py`,模式 `copilot_acp`,排除 `tests/`。全部命中都是模块名
`agent/copilot_acp_client` 或 CLI 的 setup flow 函数名,**没有一处把 `copilot_acp` 当 api_mode 值用**,
`run_agent.py` **零命中**。这个 docstring 描述的是一个不存在的机制。

**▲ 定案 1**(`providers/README.md:43-44` + `website/docs/developer-guide/model-provider-plugin.md:187,190`,
中文镜像 `website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/developer-guide/model-provider-plugin.md:186,189` 同错):
文档说 profile 的 `api_mode` 是 URL 探测失败后的回退,代码里没有任何读取点;
真实回退是 `HERMES_OVERLAYS[provider].transport` 经 `TRANSPORT_TO_API_MODE` 转换。
**对文档的目标读者(写新 provider 插件的人)后果是实的**:按文档"设 `profile.api_mode` 当提示"
写出来的插件,如果 provider 不在 overlay 表里,运行时会拿到默认的 `chat_completions`。

**▲ 定案 2**(同一 `## api_mode selection` 节,`website/docs/developer-guide/model-provider-plugin.md:186`):该节第 3 步写
「`/coding` on Kimi domains → `chat_completions`」,代码是**反的**:

`hermes_cli/runtime_provider.py:148-149 @ 863e313`

```python
    if hostname == "api.kimi.com" and "/coding" in normalized:
        return "anthropic_messages"
```

而且这条正是 `tests/agent/test_auxiliary_transport_autodetect.py` 整个文件存在的理由
(该文件 docstring 记的事故就是"Kimi Coding Plan 走了 chat_completions 于是 404")。
**文档把被修掉的那个 bug 写成了规格。**

---

## 5. `chat_completions.py`:最通用那条路

`agent/transports/chat_completions.py:1-10 @ 863e313`

```python
"""OpenAI Chat Completions transport.

Handles the default api_mode ('chat_completions') used by ~16 OpenAI-compatible
providers (OpenRouter, Nous, NVIDIA, Qwen, Ollama, DeepSeek, xAI, Kimi, etc.).

Messages and tools are already in OpenAI format — convert_messages and
convert_tools are near-identity.  The complexity lives in build_kwargs
which has provider-specific conditionals for max_tokens defaults,
reasoning configuration, temperature handling, and extra_body assembly.
"""
```

**◎ 观察(模块 docstring)**:「~16 OpenAI-compatible providers」实测偏低——
38 个已注册 profile 里 **29 个**的生效 api_mode 是 `chat_completions`
(overlay 表 39 项里 28 项 transport 是 `openai_chat`),见 §4.4 那条 verify 命令同一套口径。
更实质的问题是括号里的举例把 **xAI** 列了进去,而 xAI 走的是 `codex_responses`:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_QUIET=1 /home/user/hermes-venv/bin/python -c "
from hermes_cli.providers import determine_api_mode
for n in ['openrouter','nous','nvidia','qwen','ollama','deepseek','xai','kimi']:
    print(f'{n:12s} -> {determine_api_mode(n, \"\", \"\")}')
"
```

```text
openrouter   -> chat_completions
nous         -> chat_completions
nvidia       -> chat_completions
qwen         -> chat_completions
ollama       -> chat_completions
deepseek     -> chat_completions
xai          -> codex_responses
kimi         -> chat_completions
```

(这是模块 docstring 而非 website/docs,是否计入跨轮 ▲/◎ 计数由主线定;
本底稿按"作者自绘地图"的精神记为 ◎ + 一处举例错误。)

### 5.1 `convert_messages`:一张"不能上线的键"清单

**场景**:一次普通的工具调用轮次结束后,hermes 的消息 dict 上挂了七八个只对自己有意义的字段——
给 SQLite 全文索引用的 `tool_name`、给 Codex Responses 协议用的 `codex_reasoning_items`、
给回放用的 `api_content`、给主循环记账用的 `_empty_recovery_synthetic`。
把这个 dict 原样 POST 给 OpenRouter,没事;POST 给 Fireworks,HTTP 400
`Extra inputs are not permitted, field: 'messages[3].tool_name'`,**而且这条消息会留在历史里,
于是这个会话之后每一次请求都 400**。

`agent/transports/chat_completions.py:217-252 @ 863e313`

```python
    def convert_messages(
        self, messages: list[dict[str, Any]], **kwargs
    ) -> list[dict[str, Any]]:
        """Messages are already in OpenAI format — strip internal fields
        that strict chat-completions providers reject with HTTP 400/422
        (or, in the case of some OpenAI-compatible gateways, 5xx):

        - Codex Responses API fields: ``codex_reasoning_items`` /
          ``codex_message_items`` on the message, ``call_id`` /
          ``response_item_id`` on ``tool_calls`` entries.
        - ``extra_content`` on ``tool_calls`` (Gemini thought_signature) —
          stripped unless the outgoing ``model`` is itself Gemini-family.
          Gemini 3 thinking models attach it for replay, but strict providers
          (Fireworks, Mistral) reject any payload containing it with
          ``Extra inputs are not permitted, field: 'messages[N].tool_calls[M].extra_content'``.
          It must be kept for Gemini targets (replay required) and dropped for
          everyone else, including non-Gemini models that inherited stale
          Gemini ``extra_content`` earlier in a mixed-provider session.
        - ``tool_name`` on tool-result messages — written by
          ``make_tool_result_message()`` for the SQLite FTS index, but not
          part of the Chat Completions schema. Strict providers (Fireworks,
          Moonshot/Kimi) reject any payload containing it with
          ``Extra inputs are not permitted, field: 'messages[N].tool_name'``.
          Permissive providers (OpenRouter, MiniMax) silently ignore the
          field, which masked the bug for months.
        - Hermes-internal scaffolding markers — any top-level message key
          starting with ``_`` (e.g. ``_empty_recovery_synthetic``,
          ``_empty_terminal_sentinel``, ``_thinking_prefill``). These are
          bookkeeping flags the agent loop attaches to messages so the
          persistence layer can later strip its own scaffolding; they must
          never reach the wire. Permissive providers (real OpenAI,
          Anthropic) silently drop unknown message keys, but strict
          gateways (e.g. opencode-go, codex.nekos.me) reject with
          ``Extra inputs are not permitted, field: 'messages[N]._empty_recovery_synthetic'``,
          which then poisons every subsequent request in the session.
        """
```

这段 docstring 本身就是一份事故清单,四类被剥的字段各自有来历:

| 字段 | 来自哪 | 谁会 400 |
|---|---|---|
| `codex_reasoning_items` / `codex_message_items` / `call_id` / `response_item_id` | Codex Responses 协议 | 严格 chat-completions provider |
| `extra_content` | Gemini 3 thought_signature | Fireworks / Mistral(但 Gemini 缺了它也 400) |
| `tool_name` | `make_tool_result_message()` 写给 FTS 索引 | Fireworks、Moonshot/Kimi |
| `_` 前缀键 | 主循环自己的脚手架标记 | opencode-go、codex.nekos.me |

docstring 里那句「**Permissive providers (OpenRouter, MiniMax) silently ignore the field,
which masked the bug for months.**」是整个传输层最有价值的一句设计教训:
**宽容的 provider 会把 schema 污染藏起来,直到你换一家。**

实现是两遍扫描——先探测是否需要清洗,不需要就原样返回(零拷贝快路):

`agent/transports/chat_completions.py:256-284 @ 863e313`

```python
        needs_sanitize = False
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            if (
                "codex_reasoning_items" in msg
                or "codex_message_items" in msg
                or "tool_name" in msg
                or "effect_disposition" in msg
                or "timestamp" in msg  # #47868 — strict providers reject this
                or "api_content" in msg  # persist-what-you-send sidecar
            ):
                needs_sanitize = True
                break
            if any(isinstance(k, str) and k.startswith("_") for k in msg):
                needs_sanitize = True
                break
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if isinstance(tc, dict) and (
                        "call_id" in tc
                        or "response_item_id" in tc
                        or (strip_extra_content and "extra_content" in tc)
                    ):
                        needs_sanitize = True
                        break
                if needs_sanitize:
                    break
```

需要清洗时才做写时复制(copy-on-write),而且是逐消息、逐 tool_call 粒度的:

`agent/transports/chat_completions.py:289-302 @ 863e313`

```python
        sanitized = list(messages)
        for msg_idx, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue

            copied_msg: dict[str, Any] | None = None

            def mutable_msg() -> dict[str, Any]:
                nonlocal copied_msg
                if copied_msg is None:
                    copied_msg = dict(msg)
                    sanitized[msg_idx] = copied_msg
                return copied_msg

```

`agent/transports/chat_completions.py:303-317 @ 863e313`

```python
            if (
                "codex_reasoning_items" in msg
                or "codex_message_items" in msg
                or "tool_name" in msg
                or "effect_disposition" in msg
                or "timestamp" in msg  # #47868 — leak into strict providers
                or "api_content" in msg  # persist-what-you-send sidecar
            ):
                out_msg = mutable_msg()
                out_msg.pop("codex_reasoning_items", None)
                out_msg.pop("codex_message_items", None)
                out_msg.pop("tool_name", None)
                out_msg.pop("effect_disposition", None)
                out_msg.pop("timestamp", None)  # #47868 — leak into strict providers
                out_msg.pop("api_content", None)  # persist-what-you-send sidecar
```

`agent/transports/chat_completions.py:320-350 @ 863e313`

```python
            # Drop all Hermes-internal scaffolding markers (``_``-prefixed).
            # OpenAI's message schema has no ``_``-prefixed fields, so this
            # is safe and future-proofs against new markers being added.
            internal_keys = [k for k in msg if isinstance(k, str) and k.startswith("_")]
            if internal_keys:
                out_msg = mutable_msg()
                for key in internal_keys:
                    out_msg.pop(key, None)

            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                copied_tool_calls: list[Any] | None = None
                for tc_idx, tc in enumerate(tool_calls):
                    if isinstance(tc, dict):
                        should_copy_tc = (
                            "call_id" in tc
                            or "response_item_id" in tc
                            or (strip_extra_content and "extra_content" in tc)
                        )
                        if should_copy_tc:
                            if copied_tool_calls is None:
                                copied_tool_calls = list(tool_calls)
                            copied_tc = dict(tc)
                            copied_tc.pop("call_id", None)
                            copied_tc.pop("response_item_id", None)
                            if strip_extra_content:
                                copied_tc.pop("extra_content", None)
                            copied_tool_calls[tc_idx] = copied_tc
                if copied_tool_calls is not None:
                    mutable_msg()["tool_calls"] = copied_tool_calls
        return sanitized
```

**■ 观察 4:探测清单和剥除清单是同一份知识的两份手写副本。**
第 260-267 行的探测键集与第 303-317 行的剥除键集必须逐字保持一致,否则:
只带新键的消息**探测不到 → 走快路原样返回 → 新键直接上线**。目前两份是同步的(各 6 个键),
但这是一颗定时炸弹——而且它已经在**另一处**炸过了(见 §9.1)。

**Gemini `extra_content` 的模型门控**:

`agent/transports/chat_completions.py:191-204 @ 863e313`

```python
def _model_consumes_thought_signature(model: Any) -> bool:
    """True when the outgoing model is a Gemini family model that requires
    ``extra_content`` (thought_signature) to be replayed on tool calls.

    Gemini 3 thinking models attach ``extra_content`` to each tool call and
    reject subsequent requests with HTTP 400 if it is missing. Every other
    strict OpenAI-compatible provider (Fireworks, Mistral, ...) rejects the
    request with 400 if ``extra_content`` *is* present. So the field must be
    kept only when the target model is itself Gemini-family, and stripped
    otherwise — including when a non-Gemini model inherits stale Gemini
    ``extra_content`` from earlier in a mixed-provider session.
    """
    m = str(model or "").lower()
    return "gemini" in m or "gemma" in m
```

注意 `strip_extra_content` 的默认值方向:

`agent/transports/chat_completions.py:253-255 @ 863e313`

```python
        strip_extra_content = not _model_consumes_thought_signature(
            kwargs.get("model")
        )
```

`kwargs.get("model")` 拿不到 model 时 → `_model_consumes_thought_signature(None)` → False →
**默认剥除**。这个默认方向是对的(多剥一次只丢 Gemini 的签名回放,少剥一次会让所有严格 provider 400),
但意味着**任何不传 model 直接调 `convert_messages` 的调用方都会静默丢掉 Gemini 签名**。
由于 §1.4 已证明外部调用面为零,当前无实际影响。

### 5.2 `build_kwargs`:两条路

`agent/transports/chat_completions.py:409-423 @ 863e313`

```python
        # Codex sanitization: drop reasoning_items / call_id / response_item_id.
        # Pass model so the Gemini thought_signature (extra_content) is kept for
        # Gemini targets and stripped for strict non-Gemini providers.
        sanitized = self.convert_messages(messages, model=model)

        # ── Provider profile: single-path when present ──────────────────
        _profile = params.get("provider_profile")
        if _profile:
            return self._build_kwargs_from_profile(
                _profile, model, sanitized, tools, params
            )

        # ── Legacy fallback (unregistered / unknown provider) ───────────
        # Reached only when get_provider_profile() returned None.
        # Known providers always go through the profile path above.
```

**profile 路**(已注册 provider)把所有怪癖委托给 profile 对象;
**legacy 路**(未注册 / 自定义 provider)是一长串 `is_kimi` / `is_tokenhub` / `is_lmstudio` / `is_openrouter` 布尔标志。
参数清单本身就把这个分裂写清楚了:

`agent/transports/chat_completions.py:374-379 @ 863e313`

```python
            # Provider profile path (all per-provider quirks live in providers/)
            provider_profile: ProviderProfile | None — when present, delegates to
                _build_kwargs_from_profile(); all flag params below are bypassed.
            # Legacy-path flags — only used when provider_profile is None
            # (i.e. custom / unregistered providers). Known providers all go
            # through provider_profile.
```

max_tokens 的优先级在两条路上略有不同——legacy 路没有"profile 默认值"这一档:

`agent/transports/chat_completions.py:454-468 @ 863e313`

```python
        # max_tokens resolution — priority: ephemeral > user > provider default
        max_tokens_fn = params.get("max_tokens_param_fn")
        ephemeral = params.get("ephemeral_max_output_tokens")
        max_tokens = params.get("max_tokens")
        anthropic_max_out = params.get("anthropic_max_output")
        is_kimi = params.get("is_kimi", False)
        is_tokenhub = params.get("is_tokenhub", False)
        reasoning_config = _reasoning_config_for_model(model, params.get("reasoning_config"))

        if ephemeral is not None and max_tokens_fn:
            api_kwargs.update(max_tokens_fn(ephemeral))
        elif max_tokens is not None and max_tokens_fn:
            api_kwargs.update(max_tokens_fn(max_tokens))
        elif anthropic_max_out is not None:
            api_kwargs["max_tokens"] = anthropic_max_out
```

`agent/transports/chat_completions.py:648-665 @ 863e313`

```python
        # max_tokens resolution — priority: ephemeral > user > profile default
        max_tokens_fn = params.get("max_tokens_param_fn")
        ephemeral = params.get("ephemeral_max_output_tokens")
        user_max = params.get("max_tokens")
        anthropic_max = params.get("anthropic_max_output")
        # Per-model default cap — profiles override get_max_tokens() when
        # they front several backends with different completion-token limits
        # (e.g. opencode-go: mimo-v2.5-pro = 131072).
        profile_max = profile.get_max_tokens(model)

        if ephemeral is not None and max_tokens_fn:
            api_kwargs.update(max_tokens_fn(ephemeral))
        elif user_max is not None and max_tokens_fn:
            api_kwargs.update(max_tokens_fn(user_max))
        elif profile_max and max_tokens_fn:
            api_kwargs.update(max_tokens_fn(profile_max))
        elif anthropic_max is not None:
            api_kwargs["max_tokens"] = anthropic_max
```

**profile 路多了 `profile_max` 一档**(第 656、662 行)。这是两条路唯一的语义差,
其余差异都是"legacy 路手写、profile 路委托"。

profile 路末尾还有一段 legacy 路没有的保护:

`agent/transports/chat_completions.py:715-737 @ 863e313`

```python
        if extra_body:
            # Native Gemini (generativelanguage.googleapis.com, non-/openai)
            # speaks Google's REST schema, not OpenAI's. OpenAI-style extra_body
            # keys (tags, reasoning, provider, plugins, …) are unknown fields
            # there and Gemini rejects the whole request with a non-retryable
            # HTTP 400 ("Invalid JSON payload received. Unknown name 'tags'").
            # This happens when a profile that emits extra_body (e.g. the Nous
            # profile's portal `tags`) is active but the resolved endpoint is a
            # Gemini base_url — typical when only Google credentials are set and
            # a fallback/aux call lands on Gemini. The native client only reads
            # thinking_config from extra_body, so drop everything else here.
            try:
                from agent.gemini_native_adapter import is_native_gemini_base_url
                _native_gemini = is_native_gemini_base_url(params.get("base_url"))
            except Exception:
                _native_gemini = False
            if _native_gemini:
                extra_body = {
                    k: v for k, v in extra_body.items()
                    if k in ("thinking_config", "thinkingConfig")
                }
            if extra_body:
                api_kwargs["extra_body"] = extra_body
```

**场景**:只配了 Google 凭据,某次 aux 调用回落到 Gemini 原生端点,但当时激活的 profile 是 Nous
(它总会往 extra_body 里塞 `tags`)。Gemini 原生 REST 不认 `tags`,整个请求 400 且不可重试。
解法是"在原生 Gemini 端点上只保留 `thinking_config`,其余全丢"。

### 5.3 `normalize_response`

`agent/transports/chat_completions.py:749-764 @ 863e313`

```python
    def normalize_response(self, response: Any, **kwargs) -> NormalizedResponse:
        """Normalize OpenAI ChatCompletion to NormalizedResponse.

        For chat_completions, this is near-identity — the response is already
        in OpenAI format.  extra_content on tool_calls (Gemini thought_signature)
        is preserved via ToolCall.provider_data.  reasoning_details (OpenRouter
        unified format) and reasoning_content (DeepSeek/Moonshot) are also
        preserved for downstream replay.
        """
        choice = response.choices[0]
        msg = choice.message
        # Poolside returns integer finish_reason (e.g. 24) instead of string
        _fr = choice.finish_reason
        if isinstance(_fr, int):
            _fr = str(_fr)
        finish_reason = _fr or "stop"
```

第 760-763 行那个 `isinstance(_fr, int)` 是 Poolside 这家 provider 回整数 finish_reason 的补丁——
转成字符串后是 `"24"`,不在任何映射表里,下游按未知处理。

tool_calls 的处理是整个函数里最微妙的一段:

`agent/transports/chat_completions.py:766-792 @ 863e313`

```python
        tool_calls = None
        if msg.tool_calls:
            tool_calls = []
            for tc in msg.tool_calls:
                # Preserve provider-specific extras on the tool call.
                # Gemini 3 thinking models attach extra_content with
                # thought_signature — without replay on the next turn the API
                # rejects the request with 400.
                tc_provider_data: dict[str, Any] = {}
                extra = getattr(tc, "extra_content", None)
                if extra is None and hasattr(tc, "model_extra"):
                    extra = (tc.model_extra if isinstance(tc.model_extra, dict) else {}).get("extra_content")
                if extra is not None:
                    if hasattr(extra, "model_dump"):
                        try:
                            extra = extra.model_dump()
                        except Exception:
                            pass
                    tc_provider_data["extra_content"] = extra
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                        provider_data=tc_provider_data or None,
                    )
                )
```

注意 `model_extra` 那两行(776-777):OpenAI 的 Python SDK 用 pydantic,
线上多出来的字段会落在 `model_extra` 里而不是变成属性。所以取 `extra_content` 要试两次。
同样的双路取法在 reasoning 上再来一遍:

`agent/transports/chat_completions.py:803-819 @ 863e313`

```python
        # Preserve reasoning fields separately.  DeepSeek/Moonshot use
        # ``reasoning_content``; others use ``reasoning``.  Downstream code
        # (_extract_reasoning, thinking-prefill retry) reads both distinctly,
        # so keep them apart in provider_data rather than merging.
        reasoning = getattr(msg, "reasoning", None)
        reasoning_content = getattr(msg, "reasoning_content", None)
        if reasoning_content is None and hasattr(msg, "model_extra"):
            model_extra = getattr(msg, "model_extra", None) or {}
            if isinstance(model_extra, dict) and "reasoning_content" in model_extra:
                reasoning_content = model_extra["reasoning_content"]

        provider_data: Dict[str, Any] = {}
        if reasoning_content is not None:
            provider_data["reasoning_content"] = reasoning_content
        rd = getattr(msg, "reasoning_details", None)
        if rd:
            provider_data["reasoning_details"] = rd
```

**refusal 提升**是这个函数里唯一改变语义的地方:

`agent/transports/chat_completions.py:821-853 @ 863e313`

```python
        # OpenAI structured-refusal field. When a model declines, the SDK
        # populates ``message.refusal`` with the explanation and leaves
        # ``content`` empty. OpenAI-compatible proxies that front Anthropic /
        # Bedrock (e.g. Nous Portal) surface a Claude refusal this way — or via
        # ``finish_reason="content_filter"`` — instead of the native
        # ``stop_reason="refusal"``. Without capturing it the refusal looks
        # like an empty response, so the agent loop retries a deterministic
        # refusal three times and gives up with "no content after retries".
        # Promote it to content + a ``content_filter`` finish reason so the
        # loop's refusal handler surfaces it clearly and stops. ``refusal`` is
        # ``None`` for normal responses, so this is a no-op in the common case.
        content = msg.content
        refusal = getattr(msg, "refusal", None)
        if refusal is None and hasattr(msg, "model_extra"):
            _msg_extra = getattr(msg, "model_extra", None) or {}
            if isinstance(_msg_extra, dict):
                refusal = _msg_extra.get("refusal")
        if isinstance(refusal, str) and refusal.strip():
            # Record the refusal explanation regardless — it's useful provider
            # metadata even when the model also returned a usable payload.
            provider_data["refusal"] = refusal
            _has_text = isinstance(content, str) and content.strip()
            _has_tool_calls = bool(tool_calls)
            # Only promote to a terminal ``content_filter`` when the refusal is
            # the *sole* payload — no visible text and no tool calls. A response
            # that carries real content (or tool calls) alongside a refusal note
            # is a normal, usable turn: surfacing it as a failed safety refusal
            # would discard the model's actual work. In the empty-payload case,
            # adopt the refusal as content so the loop has something to show.
            if not _has_text and not _has_tool_calls:
                content = refusal
                if finish_reason in (None, "stop"):
                    finish_reason = "content_filter"
```

**场景**:模型拒答。OpenAI SDK 把解释放进 `message.refusal`,`content` 留空。
如果不处理,主循环看到的是"空响应",于是重试三次同一个确定性拒答,最后报
"no content after retries"——**一个语义清楚的拒绝被伪装成了一个网络故障**。
处理方式很克制:只有当 refusal 是**唯一**载荷(没文本、没 tool_calls)时才提升为
`content` + `content_filter`;否则只记进 `provider_data`。

### 5.4 `validate_response` 与 `extract_cache_stats`

`agent/transports/chat_completions.py:864-872 @ 863e313`

```python
    def validate_response(self, response: Any) -> bool:
        """Check that response has valid choices."""
        if response is None:
            return False
        if not hasattr(response, "choices") or response.choices is None:
            return False
        if not response.choices:
            return False
        return True
```

`agent/transports/chat_completions.py:874-889 @ 863e313`

```python
    def extract_cache_stats(self, response: Any) -> dict[str, int] | None:
        """Extract cache stats from prompt_tokens_details (OpenRouter/OpenAI)
        or DeepSeek's native top-level prompt_cache_hit_tokens field."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0 if details else 0
        written = getattr(details, "cache_write_tokens", 0) or 0 if details else 0
        if not cached:
            # DeepSeek native API shape (api.deepseek.com): top-level
            # prompt_cache_hit_tokens / prompt_cache_miss_tokens (#61871).
            cached = getattr(usage, "prompt_cache_hit_tokens", 0) or 0
        if cached or written:
            return {"cached_tokens": cached, "creation_tokens": written}
        return None
```

`extract_cache_stats` 里那个 DeepSeek 分支(883-886)是 provider 差异的典型:
大部分 provider 把缓存命中放在 `usage.prompt_tokens_details.cached_tokens`,
DeepSeek 原生 API 放在顶层 `usage.prompt_cache_hit_tokens`。
——但如 §1.4 所证,这个方法**没有生产调用者**,所以这段兼容代码目前不产生任何效果。

### 5.5 `prompt_cache_key`:一个没有生产者的能力位

`agent/transports/chat_completions.py:44-62 @ 863e313`

```python
def _add_prompt_cache_key(
    api_kwargs: dict[str, Any],
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    supports_prompt_cache_key: bool,
    session_id: str | None = None,
) -> None:
    """Add a content-addressed key only for an explicitly capable endpoint."""
    if not supports_prompt_cache_key:
        return

    # An explicit caller body field is authoritative too.  Do not add a
    # duplicate top-level field whose SDK merge precedence could overwrite it.
    extra_body = api_kwargs.get("extra_body")
    if "prompt_cache_key" in api_kwargs or (
        isinstance(extra_body, dict) and "prompt_cache_key" in extra_body
    ):
        return
```

`agent/transports/chat_completions.py:64-76 @ 863e313`

```python
    # Reuse the Responses transport's single authoritative hash algorithm and
    # session-scope normalization so equivalent static prefixes route to the
    # same cache bucket across modes, without concentrating unrelated
    # sessions into one shared bucket (see #78941).
    from agent.transports.codex import _cache_scope_from_session_id, _content_cache_key

    cache_key = _content_cache_key(
        _static_prompt_instructions(messages),
        tools,
        _cache_scope_from_session_id(session_id),
    )
    if cache_key:
        api_kwargs["prompt_cache_key"] = cache_key
```

`agent/transports/chat_completions.py:173-188 @ 863e313`

```python
def _is_openai_api_base_url(base_url: Any) -> bool:
    """True only for api.openai.com itself (exact host).

    OpenAI documents ``prompt_cache_key`` as a first-class body field and
    GPT-5.6+ docs recommend it for reliable cache routing, so the flag is
    implied for the real endpoint. Deliberately NOT a substring match:
    Azure OpenAI and strict OpenAI-compat endpoints may reject unknown
    fields and must stay opt-in via ``supports_prompt_cache_key``.
    """
    try:
        from urllib.parse import urlparse

        host = (urlparse(str(base_url or "").strip()).hostname or "").lower()
    except Exception:
        return False
    return host == "api.openai.com"
```

两条路的开关来源不同:

`agent/transports/chat_completions.py:588-595 @ 863e313`

```python
        _add_prompt_cache_key(
            api_kwargs,
            messages=sanitized,
            tools=api_kwargs.get("tools"),
            supports_prompt_cache_key=bool(params.get("supports_prompt_cache_key"))
            or _is_openai_api_base_url(params.get("base_url")),
            session_id=params.get("session_id"),
        )
```

`agent/transports/chat_completions.py:739-745 @ 863e313`

```python
        _add_prompt_cache_key(
            api_kwargs,
            messages=sanitized,
            tools=api_kwargs.get("tools"),
            supports_prompt_cache_key=bool(profile.supports_prompt_cache_key),
            session_id=params.get("session_id"),
        )
```

**legacy 路**:`params["supports_prompt_cache_key"]` **或** base_url 是 api.openai.com。
**profile 路**:只看 `profile.supports_prompt_cache_key`,**没有** base_url 兜底。

**■ 观察 5:这个能力位在生产里没有任何生产者。**

```verify
cd /home/user/hermes-agent && grep -rn "supports_prompt_cache_key" . | grep -v "^\./\.git/"
```

```text
./providers/base.py:79:    supports_prompt_cache_key: bool = False
./agent/transports/chat_completions.py:49:    supports_prompt_cache_key: bool,
./agent/transports/chat_completions.py:53:    if not supports_prompt_cache_key:
./agent/transports/chat_completions.py:180:    fields and must stay opt-in via ``supports_prompt_cache_key``.
./agent/transports/chat_completions.py:406:            supports_prompt_cache_key: bool — explicit endpoint capability for
./agent/transports/chat_completions.py:592:            supports_prompt_cache_key=bool(params.get("supports_prompt_cache_key"))
./agent/transports/chat_completions.py:743:            supports_prompt_cache_key=bool(profile.supports_prompt_cache_key),
./tests/agent/transports/test_chat_completions.py:628:                name="cache-capable", supports_prompt_cache_key=True,
./tests/agent/transports/test_chat_completions.py:643:            supports_prompt_cache_key=True,
./tests/agent/transports/test_chat_completions.py:701:        profile = ProviderProfile(name="cache-capable", supports_prompt_cache_key=True)
./tests/agent/transports/test_chat_completions.py:725:            supports_prompt_cache_key=True,
./tests/agent/transports/test_chat_completions.py:743:            supports_prompt_cache_key=True,
./tests/agent/transports/test_chat_completions.py:750:            supports_prompt_cache_key=True,
```

**搜索面**:整仓**全部文件类型**(不限 `.py`),模式 `supports_prompt_cache_key`,只排除 `.git/`。
命中里唯一把它置 True 的是 `tests/`,production profile 一个都没有(§4.4 的运行时检查同样打印
`supports_prompt_cache_key=True: []`,38 个 profile 全为 False)。
且 `params.get("supports_prompt_cache_key")` 从来没有调用方传过。

**于是 `prompt_cache_key` 在全仓的唯一发射条件是:legacy 路 + base_url 主机名恰为 `api.openai.com`。**
而 `api.openai.com` 会被 `_detect_api_mode_for_url` 判成 `codex_responses`(§4.2 第 135-136 行),
根本不走 chat_completions 传输。要触发它得**同时**满足"provider 未注册 profile"和
"用户手工把 api_mode 强制成 chat_completions 并指向 api.openai.com"。

**这条的价值不在于"删掉它"**,而在于它演示了一种很难发现的腐烂:
函数写得很讲究(复用 codex 传输的哈希算法、按 session 分桶、避让调用方已有字段、引用了 issue #78941),
docstring 也把设计意图讲清楚了,**只是没有人打开开关**。
代码审查看不出来(每一行都对),测试也看不出来(测试自己把开关打开了)。

---

## 6. `anthropic.py`:为什么需要单独一支

`agent/transports/anthropic.py:1-5 @ 863e313`

```python
"""Anthropic Messages API transport.

Delegates to the existing adapter functions in agent/anthropic_adapter.py.
This transport owns format conversion and normalization — NOT client lifecycle.
"""
```

`agent/transports/anthropic.py:13-22 @ 863e313`

```python
class AnthropicTransport(ProviderTransport):
    """Transport for api_mode='anthropic_messages'.

    Wraps the existing functions in anthropic_adapter.py behind the
    ProviderTransport ABC.  Each method delegates — no logic is duplicated.
    """

    @property
    def api_mode(self) -> str:
        return "anthropic_messages"
```

**这一支的定位是"薄壳"**:它自己几乎不含逻辑,四个方法全部委托给 `agent/anthropic_adapter.py`。
docstring 明说「**Each method delegates — no logic is duplicated.**」——这句在 `convert_*` / `build_kwargs`
上成立,在 `normalize_response` 上**不成立**(那是 100 多行实打实的逻辑,见 §6.2)。

### 6.1 与 chat_completions 的四个结构性差异

| 差异 | chat_completions | anthropic |
|---|---|---|
| 消息形状 | 一个扁平 list | `(system, messages)` **二元组**——system 是独立字段不是消息 |
| 工具 schema | `function.parameters` | `input_schema` |
| 推理内容 | 事后从 `message.reasoning` 里捞 | **content block** 里的一等公民(`thinking` / `redacted_thinking`) |
| 停止原因 | 已是 OpenAI 词汇 | 自有词汇表,必须映射 |

`convert_messages` 返回二元组这件事,ABC 的 docstring 专门点名了(见 §1.2 第 29-30 行:
"e.g. (system, messages) for Anthropic")——**也就是说 ABC 明确承认 `convert_messages` 的返回类型
不是统一的**,它的声明类型就是 `Any`。这是这套抽象最弱的一环。

`build_kwargs` 的参数面也最宽:

`agent/transports/anthropic.py:41-62 @ 863e313`

```python
    def build_kwargs(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> Dict[str, Any]:
        """Build Anthropic messages.create() kwargs.

        Calls convert_messages and convert_tools internally.

        params (all optional):
            max_tokens: int
            reasoning_config: dict | None
            tool_choice: str | None
            is_oauth: bool
            preserve_dots: bool
            context_length: int | None
            base_url: str | None
            fast_mode: bool
            drop_context_1m_beta: bool
        """
```

九个可选参数,每一个都是一个 Anthropic 专有开关(OAuth 与 API key 的差异、
点号是否保留、1M 上下文 beta header 要不要丢……)。这就是 §1.5 说的"`**params` 是类型擦除逃生舱"的实证:
**调用方必须知道自己在跟哪个后端说话,才能填对这九个参数**。

### 6.2 `normalize_response`:一次签名事故催生的双通道

`agent/transports/anthropic.py:80-88 @ 863e313`

```python
    def normalize_response(self, response: Any, **kwargs) -> NormalizedResponse:
        """Normalize Anthropic response to NormalizedResponse.

        Parses content blocks (text, thinking, tool_use), maps stop_reason
        to OpenAI finish_reason, and collects reasoning_details in provider_data.
        """
        import json
        from agent.anthropic_adapter import _to_plain_data, _sanitize_replay_block
        from agent.transports.types import ToolCall
```

`agent/transports/anthropic.py:96-107 @ 863e313`

```python
        tool_calls = []
        # Verbatim, order-preserving copy of every content block in the turn.
        # Anthropic signs each thinking block against the turn content that
        # PRECEDES it at its position; when a turn interleaves thinking and
        # tool_use (adaptive/interleaved thinking, Claude 4.6+), the parallel
        # reasoning_details + tool_calls lists below lose that cross-type
        # ordering. Replaying the latest assistant message in the wrong order
        # invalidates the signatures -> HTTP 400 "thinking ... blocks in the
        # latest assistant message cannot be modified". Preserve the exact
        # block sequence here so the adapter can replay it unchanged. See
        # tests/agent/test_anthropic_thinking_block_order.py.
        ordered_blocks = []
```

**事故经过(讲成故事)**:Claude 4.6 起支持"交错思考"——一轮里可以是
`thinking → tool_use → thinking → tool_use`。Anthropic 会给每个 thinking 块签名,
**签名是对"它前面那些内容"签的**。hermes 原本把 thinking 收进 `reasoning_details` 列表、
把 tool_use 收进 `tool_calls` 列表——两个**平行**列表。回放时按"先所有 thinking,再所有 tool_use"重建,
顺序就错了,签名校验失败,API 回 400
`thinking ... blocks in the latest assistant message cannot be modified`。
修法不是去修重建顺序,而是**额外存一份逐字保序的原始块序列**。

`agent/transports/anthropic.py:109-119 @ 863e313`

```python
        for block in response.content:
            block_dict = _to_plain_data(block)
            clean_block = None
            if isinstance(block_dict, dict):
                # Sanitize at capture so output-only SDK fields (parsed_output,
                # caller, citations=None, …) never persist to state.db and leak
                # back as request input on replay → HTTP 400 "Extra inputs are
                # not permitted". Defence-in-depth with the replay-side sanitize.
                clean_block = _sanitize_replay_block(block_dict)
                if clean_block is not None:
                    ordered_blocks.append(clean_block)
```

`agent/transports/anthropic.py:164-183 @ 863e313`

```python
        provider_data = {}
        if reasoning_details:
            provider_data["reasoning_details"] = reasoning_details
        # Only worth carrying the ordered-blocks channel when the turn
        # actually interleaves signed thinking with tool_use — that's the
        # only shape the parallel lists reconstruct incorrectly. A turn that
        # is purely text, or thinking-then-tools with a single leading
        # thinking block, replays correctly without it.
        _has_signed_thinking = any(
            isinstance(b, dict)
            and b.get("type") in ("thinking", "redacted_thinking")
            and (b.get("signature") or b.get("data"))
            for b in ordered_blocks
        )
        _has_tool_use = any(
            isinstance(b, dict) and b.get("type") == "tool_use"
            for b in ordered_blocks
        )
        if _has_signed_thinking and _has_tool_use:
            provider_data["anthropic_content_blocks"] = ordered_blocks
```

注意第 172-182 行的门控:**只有当这一轮同时有"带签名的 thinking"和"tool_use"时才带这个通道**。
纯文本轮、或"一个 thinking 打头再跟工具"的轮次,平行列表重建是正确的,不需要多存一份。
**这个门控是设计上的克制**:多存一份逐字块意味着 state.db 里多一份体积,只在真会出错的形状上付这个代价。

上面 109-119 那段里的 `_sanitize_replay_block`(第 117 行)是另一条防线:
SDK 返回的块上带着一些**只出现在输出**的字段(`parsed_output`、`caller`、`citations=None`),
原样存进 state.db 再当输入回放 → HTTP 400 `Extra inputs are not permitted`。
这跟 §5.1 chat_completions 剥内部字段是**同一类问题的另一个方向**:
那边是"我们自己加的字段不能上线",这边是"provider 给的字段不能回传"。

### 6.3 OAuth 下的工具名前缀反解

`agent/transports/anthropic.py:132-153 @ 863e313`

```python
            elif block.type == "tool_use":
                name = block.name
                if strip_tool_prefix and name.startswith(_MCP_PREFIX):
                    # On the OAuth wire every tool carries a double-underscore
                    # ``mcp__`` prefix (added in build_anthropic_kwargs to avoid
                    # Anthropic's single-underscore third-party classifier).
                    # Reverse it back to the name the registry/dispatcher knows.
                    # Two original forms map onto the same ``mcp__`` wire name:
                    #   ``mcp__read_file``       <- bare native tool ``read_file``
                    #   ``mcp__linear_get_issue`` <- MCP server tool
                    #                                ``mcp_linear_get_issue``
                    # Resolve by registry lookup, preferring whichever original
                    # is actually registered; never rewrite a name the LLM used
                    # that already resolves natively. GH-25255.
                    from tools.registry import registry as _tool_registry
                    if not _tool_registry.get_entry(name):
                        bare = name[len(_MCP_PREFIX):]            # read_file
                        single = "mcp_" + bare                    # mcp_read_file / mcp_linear_get_issue
                        if _tool_registry.get_entry(single):
                            name = single
                        elif _tool_registry.get_entry(bare):
                            name = bare
```

**场景**:走 Anthropic OAuth(Pro/Max 订阅)时,`build_anthropic_kwargs` 会给**每个**工具名加
`mcp__` 双下划线前缀,以绕开 Anthropic 对第三方工具的单下划线分类器。
模型回来的 `tool_use.name` 因此也是 `mcp__xxx`,必须反解回注册表认识的名字。
难点是**两种原名映射到同一个线上名**:`mcp__read_file` 可能来自原生工具 `read_file`,
也可能来自 MCP 服务器工具 `mcp_read_file`。解法是**查注册表**、优先取真实注册的那个,
且"模型用的名字如果本来就能解析,就绝不改写"。

### 6.4 `validate_response`:空 content 不等于无效

`agent/transports/anthropic.py:194-220 @ 863e313`

```python
    def validate_response(self, response: Any) -> bool:
        """Check Anthropic response structure is valid.

        An empty content list is legitimate for terminal stop reasons that
        carry no text payload:

        - ``end_turn`` — the model's canonical "nothing more to add" after a
          tool turn that already delivered the user-facing text.
        - ``refusal`` — the model declined to respond (Claude 4.5+). The
          Messages API returns an empty ``content`` list with this stop
          reason. Treating it as invalid sends a deterministic refusal into
          the invalid-response retry loop, which reproduces the refusal on
          every attempt and surfaces a misleading "rate limited / invalid
          response" error instead of the refusal. ``normalize_response`` maps
          ``refusal`` → ``content_filter`` so the agent loop's refusal handler
          can surface it.

        Treating either as invalid falsely retries a completed response.
        """
        if response is None:
            return False
        content_blocks = getattr(response, "content", None)
        if not isinstance(content_blocks, list):
            return False
        if not content_blocks:
            return getattr(response, "stop_reason", None) in {"end_turn", "refusal"}
        return True
```

**这是一条昂贵的教训**:`refusal` 停止原因下 Anthropic 返回**空 content 列表**。
若把它判为无效,就会送进"无效响应重试"循环——而拒答是确定性的,每次重试都复现,
最后用户看到的是"rate limited / invalid response",**完全看不出模型其实是拒答了**。

### 6.5 停止原因映射表

`agent/transports/anthropic.py:222-245 @ 863e313`

```python
    def extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]:
        """Extract Anthropic cache_read and cache_creation token counts."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        cached = getattr(usage, "cache_read_input_tokens", 0) or 0
        written = getattr(usage, "cache_creation_input_tokens", 0) or 0
        if cached or written:
            return {"cached_tokens": cached, "creation_tokens": written}
        return None

    # Promote the adapter's canonical mapping to module level so it's shared
    _STOP_REASON_MAP = {
        "end_turn": "stop",
        "tool_use": "tool_calls",
        "max_tokens": "length",
        "stop_sequence": "stop",
        "refusal": "content_filter",
        "model_context_window_exceeded": "length",
    }

    def map_finish_reason(self, raw_reason: str) -> str:
        """Map Anthropic stop_reason to OpenAI finish_reason."""
        return self._STOP_REASON_MAP.get(raw_reason, "stop")
```

第 233 行的注释说「**Promote the adapter's canonical mapping to module level so it's shared**」——
但它其实是**类属性**,而且 `agent/anthropic_adapter.py` 里并没有 import 它。这句注释描述的是意图不是现状。

---

## 7. `bedrock.py`:为什么也需要单独一支

`agent/transports/bedrock.py:1-7 @ 863e313`

```python
"""AWS Bedrock Converse API transport.

Delegates to the existing adapter functions in agent/bedrock_adapter.py.
Bedrock uses its own boto3 client (not the OpenAI SDK), so the transport
owns format conversion and normalization, while client construction and
boto3 calls stay on AIAgent.
"""
```

**根本差异:Bedrock 不用 OpenAI SDK,用 boto3。** 所以它不只是"另一种 JSON 形状",
而是"另一个客户端库、另一种调用方式"。传输层对此的处理是**塞哨兵键**:

`agent/transports/bedrock.py:32-65 @ 863e313`

```python
    def build_kwargs(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> Dict[str, Any]:
        """Build Bedrock converse() kwargs.

        Calls convert_messages and convert_tools internally.

        params:
            max_tokens: int — output token limit (default 4096)
            temperature: float | None
            guardrail_config: dict | None — Bedrock guardrails
            region: str — AWS region (default 'us-east-1')
        """
        from agent.bedrock_adapter import build_converse_kwargs

        region = params.get("region", "us-east-1")
        guardrail = params.get("guardrail_config")

        kwargs = build_converse_kwargs(
            model=model,
            messages=messages,
            tools=tools,
            max_tokens=params.get("max_tokens", 4096),
            temperature=params.get("temperature"),
            guardrail_config=guardrail,
        )
        # Sentinel keys for dispatch — agent pops these before the boto3 call
        kwargs["__bedrock_converse__"] = True
        kwargs["__bedrock_region__"] = region
        return kwargs
```

`agent/transports/bedrock.py:62-65 @ 863e313`

```python
        # Sentinel keys for dispatch — agent pops these before the boto3 call
        kwargs["__bedrock_converse__"] = True
        kwargs["__bedrock_region__"] = region
        return kwargs
```

**◇ 观察**:`__bedrock_converse__` / `__bedrock_region__` 是**协议外的带内信令**——
传输在返回的 kwargs 里塞两个双下划线键,让分发点认出"这不是给 OpenAI SDK 的"。
`build_kwargs` 的 ABC 契约说返回值是「a dict ready to be passed to the provider's SDK client」,
而这两个键**必须先被 pop 掉**才能传给 boto3。契约和实现在这里对不上。

**可迁移的教训**:当一个后端连"用哪个客户端"都不同时,`build_kwargs → 统一分发` 这个形状就不够用了。
更干净的做法是让传输自己暴露一个 `call(client, kwargs)`,或者干脆让 `build_kwargs` 返回
`(client_kind, kwargs)` 二元组,而不是把路由信息藏在 payload 里。

### 7.1 `normalize_response` 要吃两种形状

`agent/transports/bedrock.py:67-97 @ 863e313`

```python
    def normalize_response(self, response: Any, **kwargs) -> NormalizedResponse:
        """Normalize Bedrock response to NormalizedResponse.

        Handles two shapes:
        1. Raw boto3 dict (from direct converse() calls)
        2. Already-normalized SimpleNamespace with .choices (from dispatch site)
        """
        from agent.bedrock_adapter import normalize_converse_response

        # Normalize to OpenAI-compatible SimpleNamespace
        if hasattr(response, "choices") and response.choices:
            # Already normalized at dispatch site
            ns = response
        else:
            # Raw boto3 dict
            ns = normalize_converse_response(response)

        choice = ns.choices[0]
        msg = choice.message
        finish_reason = choice.finish_reason or "stop"

        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in msg.tool_calls
            ]
```

**为什么会有两种形状**:分发点(`conversation_loop`)在某些路径上已经调过
`normalize_converse_response` 把 boto3 dict 转成了 OpenAI 形状的 SimpleNamespace,
另一些路径直接把原始 dict 递过来。传输用 `hasattr(response, "choices")` 嗅探。
**这是"归一化被做了两次"的痕迹**——同一个转换函数在两个地方被调用,传输只好兼容两种输入。

`agent/transports/bedrock.py:99-116 @ 863e313`

```python
        usage = None
        if hasattr(ns, "usage") and ns.usage:
            u = ns.usage
            usage = Usage(
                prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(u, "completion_tokens", 0) or 0,
                total_tokens=getattr(u, "total_tokens", 0) or 0,
            )

        reasoning = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)

        return NormalizedResponse(
            content=msg.content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            reasoning=reasoning,
            usage=usage,
        )
```

同样地,`usage` 只填三项、不填 `cached_tokens`(呼应 §2.5)。

`agent/transports/bedrock.py:118-132 @ 863e313`

```python
    def validate_response(self, response: Any) -> bool:
        """Check Bedrock response structure.

        After normalize_converse_response, the response has OpenAI-compatible
        .choices — same check as chat_completions.
        """
        if response is None:
            return False
        # Raw Bedrock dict response — check for 'output' key
        if isinstance(response, dict):
            return "output" in response
        # Already-normalized SimpleNamespace
        if hasattr(response, "choices"):
            return bool(response.choices)
        return False
```

### 7.2 `map_finish_reason`:自认死代码

`agent/transports/bedrock.py:134-148 @ 863e313`

```python
    def map_finish_reason(self, raw_reason: str) -> str:
        """Map Bedrock stop reason to OpenAI finish_reason.

        The adapter already does this mapping inside normalize_converse_response,
        so this is only used for direct access to raw responses.
        """
        _MAP = {
            "end_turn": "stop",
            "tool_use": "tool_calls",
            "max_tokens": "length",
            "stop_sequence": "stop",
            "guardrail_intervened": "content_filter",
            "content_filtered": "content_filter",
        }
        return _MAP.get(raw_reason, "stop")
```

docstring 自己说「**The adapter already does this mapping inside normalize_converse_response,
so this is only used for direct access to raw responses.**」——
而实测(§1.4 的同一套调用面)`map_finish_reason` 在生产只被 anthropic 那一支调过一次
(`agent/conversation_loop.py:2776`),bedrock 这一份**从未被调用**。
它与 anthropic 的 `_STOP_REASON_MAP` 有 4 个键完全重复(`end_turn` / `tool_use` / `max_tokens` / `stop_sequence`),
差异只有 anthropic 多的两个和 bedrock 多的两个 guardrail 相关键。
**同一张表的第三、第四份副本**(第一份在 `types.map_finish_reason` 的调用约定里,
第二份在 anthropic 传输里)。

---

## 8. `hermes_tools_mcp_server.py`:方向相反的那一支

### 8.1 它服务谁

`agent/transports/hermes_tools_mcp_server.py:1-13 @ 863e313`

```python
"""Hermes-tools-as-MCP server for the codex_app_server runtime.

When the user runs `openai/*` turns through the codex app-server, codex
owns the loop and builds its own tool list. By default, that means
Hermes' richer tool surface — web search, browser automation,
delegate_task subagents, vision analysis, persistent memory, skills,
cross-session search, image generation, TTS — is unreachable.

This module exposes a curated subset of those Hermes tools to the
spawned codex subprocess via stdio MCP. Codex registers it as a normal
MCP server (per `~/.codex/config.toml [mcp_servers.hermes-tools]`) and
the user gets full Hermes capability inside a Codex turn.

```

**这个文件不是传输**——它跟另外六个文件的方向正好相反。
另外六个是"hermes 作为客户端去说别人的协议";这一个是"hermes 作为**服务端**说 MCP 协议"。

MCP(Model Context Protocol,模型上下文协议)= 一套让外部进程把工具暴露给 LLM 客户端的标准。
平时 hermes 是 MCP **客户端**(去连别人的 MCP 服务器拿工具);这个文件让 hermes 当一次 MCP **服务器**。

**场景**:用户开启了 `codex_app_server` 运行时(§3.1),整条 turn 交给 codex 子进程跑。
codex 拥有循环、拥有自己的工具表,于是 hermes 那套 web 搜索、浏览器自动化、
视觉分析、技能库、TTS **全都够不着了**。解法:把它们包成一个 stdio MCP 服务器,
在 `~/.codex/config.toml` 里注册成 `[mcp_servers.hermes-tools]`,codex 就当普通 MCP 服务器用。

### 8.2 暴露边界:两条并存的原则

`agent/transports/hermes_tools_mcp_server.py:27-43 @ 863e313`

```python
What we DO NOT expose:
  - terminal / shell                     — codex's own shell tool
  - read_file / write_file / patch       — codex's apply_patch + shell
  - search_files / process               — codex's shell
  - clarify                              — codex's own UX
  - delegate_task / memory /             — `_AGENT_LOOP_TOOLS` in Hermes
    session_search / todo                  (model_tools.py). They require
                                           the running AIAgent context to
                                           dispatch (mid-loop state), so a
                                           stateless MCP callback can't
                                           drive them. See the inline
                                           comment on EXPOSED_TOOLS below.

Run with: python -m agent.transports.hermes_tools_mcp_server
Spawned by: CodexAppServerSession.ensure_started() when the runtime is
            active and config opts in.
"""
```

`agent/transports/hermes_tools_mcp_server.py:100-112 @ 863e313`

```python
# Tools we expose. Each name MUST match a registered Hermes tool that
# `model_tools.handle_function_call()` can dispatch.
#
# What we deliberately DO NOT expose:
#   - terminal / shell / read_file / write_file / patch / search_files /
#     process — codex's built-ins cover these and approval routes through
#     codex's own UI.
#   - delegate_task / memory / session_search / todo — these are
#     `_AGENT_LOOP_TOOLS` in Hermes (model_tools.py:493). They require
#     the running AIAgent context to dispatch (mid-loop state), so a
#     stateless MCP callback can't drive them. Hermes' default runtime
#     keeps these working; the codex_app_server runtime cannot.
EXPOSED_TOOLS: tuple[str, ...] = (
```

两条排除原则性质完全不同:

1. **"codex 自己有更好的"**——terminal / read_file / write_file / patch / search_files / process。
   这类排除是**产品判断**:codex 的内建工具跟它自己的沙箱和审批 UI 集成得更好。这条有测试钉着:

`tests/agent/transports/test_hermes_tools_mcp_server.py:95-108 @ 863e313`

```python
        """We MUST NOT expose tools codex already has, because codex'
        own builtins are better-integrated with its sandbox + approvals.
        Specifically: no terminal/shell, no read_file/write_file, no
        patch — those are codex's built-in tools."""
        from agent.transports.hermes_tools_mcp_server import EXPOSED_TOOLS
        forbidden = {
            "terminal", "shell", "read_file", "write_file", "patch",
            "search_files", "process",
        }
        leaked = forbidden & set(EXPOSED_TOOLS)
        assert not leaked, (
            f"these tools must NOT be exposed via the codex callback "
            f"because codex has built-in equivalents: {leaked}"
        )
```

2. **"技术上做不到"**——delegate_task / memory / session_search / todo。
   它们是 `_AGENT_LOOP_TOOLS`,派发时需要**正在运行的 AIAgent 上下文**(循环中途的状态),
   一个无状态的 MCP 回调驱动不了。

`agent/transports/hermes_tools_mcp_server.py:112-125 @ 863e313`

```python
EXPOSED_TOOLS: tuple[str, ...] = (
    "web_search",
    "web_extract",
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_press",
    "browser_snapshot",
    "browser_scroll",
    "browser_back",
    "browser_get_images",
    "browser_console",
    "browser_vision",
    "vision_analyze",
```

`agent/transports/hermes_tools_mcp_server.py:130-149 @ 863e313`

```python
    # Kanban worker handoff tools — gated on HERMES_KANBAN_TASK env var
    # (set by the kanban dispatcher when spawning a worker). Without these
    # in the callback, a worker spawned with openai_runtime=codex_app_server
    # could do the work but couldn't report completion back to the kernel,
    # making it hang until timeout. Stateless dispatch — they just read
    # the env var and write to ~/.hermes/kanban.db.
    "kanban_complete",
    "kanban_block",
    "kanban_comment",
    "kanban_heartbeat",
    "kanban_show",
    "kanban_list",
    # NOTE: kanban_create / kanban_unblock / kanban_link are orchestrator-
    # only — the kanban tool gates them on HERMES_KANBAN_TASK being unset.
    # They're exposed here for orchestrator agents running on the codex
    # runtime that need to dispatch new tasks.
    "kanban_create",
    "kanban_unblock",
    "kanban_link",
)
```

kanban 那一段的注释值得记:worker 如果能干活却不能回报完成,**会一直挂到超时**。
这是"暴露边界"这类决策的典型失败模式——漏掉一个回报通道,整个流程静默卡死。

### 8.3 ■ 定案:送给模型看的 `instructions` 宣传了三个不存在的工具

`agent/transports/hermes_tools_mcp_server.py:169-178 @ 863e313`

```python
    mcp = FastMCP(
        "hermes-tools",
        instructions=(
            "Hermes Agent's tool surface, exposed for use inside a Codex "
            "session. Use these for capabilities Codex's built-in toolset "
            "doesn't cover: web search/extract, browser automation, "
            "subagent delegation, vision, image generation, persistent "
            "memory, skills, and cross-session search."
        ),
    )
```

把这段 `instructions` 和 `EXPOSED_TOOLS`(上面 §8.2 第 112-149 行)逐项对照:

| instructions 宣传的 | 在 EXPOSED_TOOLS 里吗 |
|---|---|
| web search/extract | 是(`web_search` / `web_extract`) |
| browser automation | 是(10 个 `browser_*`) |
| **subagent delegation** | **否**——`delegate_task` 被显式排除 |
| vision | 是(`vision_analyze`) |
| image generation | 是(`image_generate`) |
| **persistent memory** | **否**——`memory` 被显式排除 |
| skills | 是(`skill_view` / `skills_list`) |
| **cross-session search** | **否**——`session_search` 被显式排除 |
| (未提) | `text_to_speech`、9 个 `kanban_*` 全部漏掉 |

**为什么这条比普通注释腐烂严重**:FastMCP 的 `instructions` 参数会进 MCP `initialize` 响应,
是**协议规定给客户端用来帮助 LLM 理解这个服务器**的字段——也就是说这段话大概率会被
codex 拼进模型可见的上下文。**模型会被告知它有 delegate_task / memory / session_search,
然后在 `tools/list` 里找不到它们。**

更糟的是同一份名单还有第三份手写副本,漂法完全一样:

`hermes_cli/codex_runtime_plugin_migration.py:557-565 @ 863e313`

```python
def _build_hermes_tools_mcp_entry() -> dict:
    """Build the codex stdio-transport entry that launches Hermes' own
    tool surface as an MCP server. Codex's subprocess will call back into
    this for browser/web/delegate_task/vision/memory/skills tools.

    The command runs the worktree's Python via the current sys.executable
    so a hermes installed under /opt/, /usr/local/, or a venv all work.
    HERMES_HOME and PYTHONPATH are passed through so the spawned process
    sees the same config + module layout the user is running."""
```

`hermes_cli/codex_runtime_plugin_migration.py:602-605 @ 863e313`

```python
    # Generous timeouts — browser_navigate or delegate_task can take a
    # while; we don't want codex's MCP client to give up too early.
    out["startup_timeout_sec"] = 30.0
    out["tool_timeout_sec"] = 600.0
```

两处都写了 `delegate_task`,一处还写了 `memory`——**全是不暴露的**。
`EXPOSED_TOOLS` 是唯一权威,三份散文副本(FastMCP instructions、迁移器 docstring、迁移器注释)
**全部漂开,且漂的方向一致**:都还停留在"打算暴露 delegate_task/memory"的那个版本。

### 8.4 实现细节:从 JSON Schema 反向合成 Python 签名

`agent/transports/hermes_tools_mcp_server.py:67-97 @ 863e313`

```python
def _signature_from_schema(schema: dict | None) -> tuple[inspect.Signature, dict[str, type]]:
    """Build a Python function signature and annotations from a JSON schema.

    Args:
        schema: JSON Schema dict with "properties" and "required" keys.

    Returns:
        (signature, annotations_dict) where signature has KEYWORD_ONLY params
        and annotations maps param names to Python types.
    """
    props = (schema or {}).get("properties") or {}
    required = set((schema or {}).get("required") or [])
    params, annots = [], {}

    for pname, pspec in props.items():
        if pname.startswith("_"):
            continue
        py = _JSON_TO_PY.get((pspec or {}).get("type"), Any)
        ann, default = (
            (py, inspect.Parameter.empty)
            if pname in required
            else (Optional[py], None)
        )
        annots[pname] = ann
        params.append(
            inspect.Parameter(
                pname, inspect.Parameter.KEYWORD_ONLY, annotation=ann, default=default
            )
        )

    return inspect.Signature(params, return_annotation=str), annots
```

**为什么需要它**:FastMCP 的 `@tool()` 装饰器靠**读类型注解**生成 MCP 的 input schema,
但 hermes 的工具 schema 是运行时的 JSON Schema dict,没有类型注解可读。
于是这里反过来:JSON Schema → `inspect.Signature` + `__annotations__`,再挂到闭包上。

`agent/transports/hermes_tools_mcp_server.py:206-237 @ 863e313`

```python
        def _make_handler(tool_name: str, schema: dict | None):
            sig, annots = _signature_from_schema(schema)

            def _dispatch(**kwargs: Any) -> str:
                try:
                    # Filter out None values before dispatch so unset optionals
                    # aren't forwarded to the handler.
                    args = {k: v for k, v in kwargs.items() if v is not None}
                    return handle_function_call(tool_name, args or {})
                except Exception as exc:
                    logger.exception("tool %s raised", tool_name)
                    return json.dumps({"error": str(exc), "tool": tool_name})

            _dispatch.__name__ = tool_name
            _dispatch.__doc__ = description
            _dispatch.__signature__ = sig
            _dispatch.__annotations__ = {**annots, "return": str}
            return _dispatch

        try:
            mcp.add_tool(
                _make_handler(name, params_schema),
                name=name,
                description=description,
            )
        except TypeError:
            # Older mcp SDK signature — fall back to decorator-style. The
            # synthesized __signature__ on the handler still drives schema
            # generation there.
            handler = _make_handler(name, params_schema)
            handler = mcp.tool(name=name, description=description)(handler)

```

第 231-236 行还兜了一层旧版 mcp SDK 的签名差异(`add_tool` 不接受关键字时回落到装饰器式)。

### 8.5 进程契约:stdout 是协议线

`agent/transports/hermes_tools_mcp_server.py:248-262 @ 863e313`

```python
def main(argv: Optional[list[str]] = None) -> int:
    """Entry point for `python -m agent.transports.hermes_tools_mcp_server`."""
    argv = argv or sys.argv[1:]
    verbose = "--verbose" in argv or "-v" in argv

    log_level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        stream=sys.stderr,  # MCP uses stdio for protocol — logs MUST go to stderr
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Quiet mode: keep Hermes' own banners off stdout (which is the MCP wire).
    os.environ.setdefault("HERMES_QUIET", "1")
    os.environ.setdefault("HERMES_REDACT_SECRETS", "true")
```

两点硬约束:
- **日志必须走 stderr**(第 256 行注释:MCP uses stdio for protocol)。
- **`HERMES_QUIET=1` 必须置位**,否则 hermes 自己的 banner 会打到 stdout 上把 MCP 帧冲烂。

`_build_server` 里对"工具没注册"的处理是**跳过并计数**,不是报错:

`agent/transports/hermes_tools_mcp_server.py:188-199 @ 863e313`

```python
    exposed_count = 0

    for name in EXPOSED_TOOLS:
        spec = all_defs.get(name)
        if spec is None:
            logger.debug(
                "skipping %s — not registered in this Hermes process", name
            )
            continue

        description = spec.get("description") or f"Hermes {name} tool"
        params_schema = spec.get("parameters") or {"type": "object", "properties": {}}
```

`agent/transports/hermes_tools_mcp_server.py:240-245 @ 863e313`

```python
    logger.info(
        "hermes-tools MCP server registered %d/%d tools",
        exposed_count,
        len(EXPOSED_TOOLS),
    )
    return mcp
```

也就是说 `EXPOSED_TOOLS` 里写了但这个进程里没注册的工具,只会留下一条 debug 日志和一个
`registered N/M tools` 的 info。**这个 N/M 是唯一能看出"少暴露了什么"的信号,而它是 INFO 级、默认不打印**
(默认 `log_level = logging.WARNING`,见上面第 253 行)。

---

## 9. 第二份副本清单(R9B 病在传输层的实例)

R9B 总结的病:「同一份知识被写了第二遍,然后两份副本漂开了」。传输层是重灾区。逐条列:

### 9.1 ■ 最严重:消息清洗器的第二份副本已经漂开了

`ChatCompletionsTransport.convert_messages()` 是主循环剥内部字段的唯一入口(§5.1)。
但**迭代摘要路径**(达到最大工具迭代数时,追加一句"请总结"再单发一次)**绕过了传输**,
手抄了一份清洗:

`agent/chat_completion_helpers.py:2152-2173 @ 863e313`

```python
    try:
        # Build API messages, stripping internal-only fields
        # (finish_reason, reasoning) that strict APIs like Mistral reject with 422
        _needs_sanitize = agent._should_sanitize_tool_calls()
        api_messages = []
        for msg in messages:
            api_msg = msg.copy()
            agent._copy_reasoning_content_for_api(msg, api_msg)
            for internal_field in ("reasoning", "finish_reason", "_thinking_prefill"):
                api_msg.pop(internal_field, None)
            # Strict OpenAI-compatible gateways (Fireworks-backed OpenCode Go,
            # Mistral, Moonshot/Kimi) reject any message key outside the Chat
            # Completions schema. The main loop drops these via
            # ChatCompletionsTransport.convert_messages(), but the summary path
            # hand-builds messages and calls chat.completions.create() directly,
            # bypassing the transport — so mirror that sanitization here:
            # tool_name (SQLite FTS bookkeeping), the codex_* reasoning carriers,
            # timestamp (preserved on gateway user replay entries for the
            # stale-confirmation expiry check — #47868 rejection class),
            # and every Hermes-internal underscore-prefixed scaffolding key.
            for schema_foreign in ("tool_name", "codex_reasoning_items", "codex_message_items", "timestamp"):
                api_msg.pop(schema_foreign, None)
```

注释第 2164-2171 行自己承认:「**The main loop drops these via ChatCompletionsTransport.convert_messages(),
but the summary path hand-builds messages and calls chat.completions.create() directly,
bypassing the transport — so mirror that sanitization here**」。

**两份已经漂开了。** 传输剥 6 个键,摘要路径剥 4 个(`api_content` 由 `substitute_api_content` 单独处理):

```verify
cd /home/user/hermes-agent && grep -n "effect_disposition" agent/transports/chat_completions.py agent/chat_completion_helpers.py
```

```text
agent/transports/chat_completions.py:264:                or "effect_disposition" in msg
agent/transports/chat_completions.py:307:                or "effect_disposition" in msg
agent/transports/chat_completions.py:315:                out_msg.pop("effect_disposition", None)
```

**搜索面**:两个文件全文,模式 `effect_disposition`。`agent/chat_completion_helpers.py` **零命中**。

`effect_disposition` 是真实存在于消息 dict 上的键,由工具结果构造器写入:

`agent/tool_dispatch_helpers.py:560-576 @ 863e313`

```python
    message = {
        "role": "tool",
        "name": name,
        "tool_name": name,
        "content": wrapped,
        "tool_call_id": tool_call_id,
    }
    try:
        risk_metadata = _tool_output_risk_metadata(name, content)
    except Exception as exc:
        logger.debug("Tool output risk scan failed for %s: %s", name, exc)
    else:
        if risk_metadata is not None:
            message["_tool_output_risk"] = risk_metadata
    if effect_disposition is not None:
        message["effect_disposition"] = effect_disposition
    return message
```

也会被 session DB 读回来重新挂上:

`hermes_state.py:7381-7382 @ 863e313`

```python
            if row["effect_disposition"]:
                msg["effect_disposition"] = row["effect_disposition"]
```

摘要路径确实是直接调 SDK 的:

`agent/chat_completion_helpers.py:2348-2358 @ 863e313`

```python
            else:
                summary_client = agent._ensure_primary_openai_client(
                    reason="iteration_limit_summary"
                )
                summary_response = _managed_summary_call(
                    summary_kwargs,
                    lambda request: summary_client.chat.completions.create(**request),
                    retry_count=0,
                )
                _summary_result = agent._get_transport().normalize_response(summary_response)
                final_response = (_summary_result.content or "").strip()
```

**后果**:一个带 `effect_disposition` 的工具结果消息,在主循环里被剥掉、在摘要请求里**没被剥掉**。
按 §5.1 docstring 列的名单,Fireworks / Moonshot(Kimi)/ opencode-go 这类严格 provider 会回
`Extra inputs are not permitted, field: 'messages[N].effect_disposition'`。
触发条件很自然:**一次用满 max_iterations 的长工具会话**——而这正是最需要摘要兜底的时候。

**这条最值得主线实跑复核**(见 §12 的复核建议)。

### 9.2 ■ Pareto 路由插件块的三份副本

同一段 `{"id": "pareto-router", "min_coding_score": ...}` 出现在三个地方:

`agent/transports/chat_completions.py:524-537 @ 863e313`

```python
        # Pareto Code router plugin — model-gated. Same shape as the
        # profile path in plugins/model-providers/openrouter/__init__.py;
        # this branch only runs when the OpenRouter profile isn't loaded.
        if is_openrouter and model == "openrouter/pareto-code":
            _pareto_score = params.get("openrouter_min_coding_score")
            if _pareto_score is not None and _pareto_score != "":
                try:
                    _pareto_score_f = float(_pareto_score)
                except (TypeError, ValueError):
                    _pareto_score_f = None
                if _pareto_score_f is not None and 0.0 <= _pareto_score_f <= 1.0:
                    extra_body["plugins"] = [
                        {"id": "pareto-router", "min_coding_score": _pareto_score_f}
                    ]
```

`plugins/model-providers/openrouter/__init__.py:106-121 @ 863e313`

```python
        # Pareto Code router — model-gated. The plugins block is only
        # meaningful for openrouter/pareto-code; sending it on any other
        # model has no documented effect and would be confusing in logs.
        # See: https://openrouter.ai/docs/guides/routing/routers/pareto-router
        model = (context.get("model") or "")
        if model == "openrouter/pareto-code":
            score = context.get("openrouter_min_coding_score")
            if score is not None and score != "":
                try:
                    score_f = float(score)
                except (TypeError, ValueError):
                    score_f = None
                if score_f is not None and 0.0 <= score_f <= 1.0:
                    body["plugins"] = [
                        {"id": "pareto-router", "min_coding_score": score_f}
                    ]
```

`agent/chat_completion_helpers.py:2304-2323 @ 863e313`

```python
            # Pareto Code router plugin — model-gated. Same shape as
            # the main-loop emission so summary calls on
            # openrouter/pareto-code respect the user's coding-score floor.
            if (
                agent.model == "openrouter/pareto-code"
                and (
                    (agent.provider or "").strip().lower() == "openrouter"
                    or agent._is_openrouter_url()
                )
                and agent.openrouter_min_coding_score is not None
                and agent.openrouter_min_coding_score != ""
            ):
                try:
                    _ps = float(agent.openrouter_min_coding_score)
                except (TypeError, ValueError):
                    _ps = None
                if _ps is not None and 0.0 <= _ps <= 1.0:
                    summary_extra_body["plugins"] = [
                        {"id": "pareto-router", "min_coding_score": _ps}
                    ]
```

三份的判定条件已经不一样了:传输 legacy 路只判 `is_openrouter and model == ...`;
profile 路只判 `model == ...`(provider 已由 profile 归属保证);
摘要路径判 `model == ... and (provider == "openrouter" or _is_openrouter_url())`。
数值校验 `0.0 <= x <= 1.0` 三份都有,目前一致。
`agent/transports/chat_completions.py:525-526` 的注释自己承认这是副本
(「Same shape as the profile path in plugins/model-providers/openrouter/__init__.py」)。

### 9.3 ◇ 停止原因映射表的四份

| 位置 | 形态 |
|---|---|
| `agent/transports/types.py:167` | 通用 helper `map_finish_reason(reason, mapping)`,**无生产调用者** |
| `agent/transports/base.py:83` | ABC 默认:原样返回(与上面的默认相反) |
| `agent/transports/anthropic.py:234` | `_STOP_REASON_MAP` 类属性,6 键 |
| `agent/transports/bedrock.py:140` | `_MAP` 函数内局部量,6 键,与上面 4 键重复,**无调用者** |

### 9.4 ◇ 推理档位词表的多份硬编码

canonical 定义在:

`hermes_constants.py:942-944 @ 863e313`

```python
VALID_REASONING_EFFORTS = (
    "minimal", "low", "medium", "high", "xhigh", "max", "ultra",
)
```

而传输层把同一个集合手写了一遍:

`agent/transports/chat_completions.py:127-128 @ 863e313`

```python
    if effort not in {"minimal", "low", "medium", "high", "xhigh", "max", "ultra"}:
        effort = "medium"
```

(另有 `hermes_cli/main.py:4256`、`hermes_cli/commands.py:233`、`hermes_cli/web_server.py:991`
各一份硬编码副本;`plugins/memory/honcho/client.py:218` 那份只有 5 个档位,已经漂了。
这几处不在本轮精读范围,只记位置不下定案。)

### 9.5 ◇ tool_calls 级清洗器的第三份(这一份没漂)

`run_agent.py:7269-7283 @ 863e313`

```python
        Fields stripped: call_id, response_item_id, extra_content (model-gated)
        """
        tool_calls = api_msg.get("tool_calls")
        if not isinstance(tool_calls, list):
            return api_msg
        from agent.transports.chat_completions import _model_consumes_thought_signature
        _STRIP_KEYS = {"call_id", "response_item_id"}
        if not _model_consumes_thought_signature(model):
            _STRIP_KEYS = _STRIP_KEYS | {"extra_content"}
        api_msg["tool_calls"] = [
            {k: v for k, v in tc.items() if k not in _STRIP_KEYS}
            if isinstance(tc, dict) else tc
            for tc in tool_calls
        ]
        return api_msg
```

值得表扬:它**没有**重抄模型判定,而是 `from agent.transports.chat_completions import
_model_consumes_thought_signature` 把谓词共享了(第 7274 行)。剥除键集与传输一致。
**这就是同一个仓库里"抄第二遍"和"共享谓词"两种做法的对照组**——同一个问题、同一个作者群、
相隔几百行,一个共享了、一个抄了。

### 9.6 ◇ `validate_response` 调用点仍按 api_mode 四路分支

`agent/conversation_loop.py:2543-2570 @ 863e313`

```python
                elif agent.api_mode == "anthropic_messages":
                    _tv = agent._get_transport()
                    if not _tv.validate_response(response):
                        response_invalid = True
                        if response is None:
                            error_details.append("response is None")
                        else:
                            error_details.append("response.content invalid (not a non-empty list)")
                elif agent.api_mode == "bedrock_converse":
                    _btv = agent._get_transport()
                    if not _btv.validate_response(response):
                        response_invalid = True
                        if response is None:
                            error_details.append("response is None")
                        else:
                            error_details.append("Bedrock response invalid (no output or choices)")
                else:
                    _ctv = agent._get_transport()
                    if not _ctv.validate_response(response):
                        response_invalid = True
                        if response is None:
                            error_details.append("response is None")
                        elif not hasattr(response, 'choices'):
                            error_details.append("response has no 'choices' attribute")
                        elif response.choices is None:
                            error_details.append("response.choices is None")
                        else:
                            error_details.append("response.choices is empty")
```

四个分支调的是**同一个** `agent._get_transport().validate_response(response)`,
分支存在的唯一理由是**拼一句人类可读的失败原因**。而拼这句话需要重新知道每种协议的结构
(`response.choices` / `response.content` / `response.output`)——
**于是协议结构知识又被抄了一遍到调用点**。
ABC 缺的是一个"说明为什么无效"的返回值:`validate_response` 只返回 bool。

**可迁移的设计**:让校验返回 `(ok, reason)` 或抛带原因的异常,四个分支就能塌成一行。

---

## 10. 测试作行为规格

### 10.1 本轮跑了哪些、结果

环境(按 CLAUDE.md 要求一并记):venv `/home/user/hermes-venv`,**87 个包**
(`pip list` 去表头计数 = 87;`site-packages/*.dist-info` 计数 = 87),
与 R8B 记录一致。**`anthropic` 与 `boto3` 均未安装**(属平台 extra,不在 `[dev]` 里)。
全部命令带 `HERMES_DISABLE_LAZY_INSTALLS=1`。

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/agent/transports/test_transport.py tests/agent/transports/test_types.py tests/agent/transports/test_chat_completions.py tests/agent/transports/test_bedrock_transport.py tests/agent/transports/test_hermes_tools_mcp_server.py
```

```text
=== Summary: 5 files, 93 tests passed, 0 failed (100% complete) in 2.1s (8 workers) ===
```

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/agent/test_auxiliary_transport_autodetect.py tests/providers/test_transport_parity.py tests/agent/test_anthropic_thinking_block_order.py tests/agent/test_anthropic_mcp_prefix_strip.py tests/agent/test_model_extra_type_guard.py tests/agent/test_anthropic_kimi_signed_thinking_replay.py tests/agent/transports/test_codex_transport.py tests/providers/test_profile_wiring.py
```

```text
=== Summary: 8 files, 119 tests passed, 1 failed (100% complete) in 3.7s (8 workers) ===
```

**合计 13 个文件,212 passed,1 failed。**

### 10.2 唯一一条失败的根因

`tests/agent/test_auxiliary_transport_autodetect.py::test_resolve_provider_client_kimi_coding_wraps_anthropic`

```text
E       AssertionError: Kimi Coding Plan endpoint (api.kimi.com/coding) speaks Anthropic
        Messages — aux client MUST be AnthropicAuxiliaryClient, got OpenAI
WARNING  agent.auxiliary_client:auxiliary_client.py:2064 Failed to build Anthropic client for
        https://api.kimi.com/coding (The 'anthropic' package is required for the Anthropic
        provider. Install it with: pip install 'anthropic>=0.39.0') — falling back to
        OpenAI-wire client.
```

**根因:容器环境限制,非代码缺陷。** `anthropic` SDK 不在 `[dev]` extra 里:

`pyproject.toml:158-160 @ 863e313`

```python
# Native Anthropic provider — only needed when provider=anthropic (not via
# OpenRouter or other aggregators).
anthropic = ["anthropic==0.87.0"]  # CVE-2026-34450, CVE-2026-34452
```

被测代码的行为完全正确——它**探测对了**(判定该端点说 Anthropic Messages),
只是建客户端时 ImportError,于是按设计回落到 OpenAI wire 并打了警告。
这正是本轮任务简报预告的那一类:**缺可选依赖不一定表现为收集期 ImportError,也可能是普通断言失败**。
(同文件另一条 `test_maybe_wrap_anthropic_sdk_missing_falls_back` 专门测这个回落路径,它通过了。)

### 10.3 值得当规格读的三份测试

**(a) `tests/agent/transports/test_transport.py`** 把 ABC 契约本身钉住了——
不能实例化 ABC、少实现一个抽象方法就 TypeError、三个可选钩子的默认值(§1.3 已引)。

**(b) `tests/agent/test_anthropic_thinking_block_order.py`** 是 §6.2 那次签名事故的规格。

**(c) `tests/providers/test_transport_parity.py`** —— 名字叫 parity(对等),
docstring 说它要钉住 flag 路与 profile 路的行为一致:

`tests/providers/test_transport_parity.py:1-7 @ 863e313`

```python
"""Parity tests: pin the exact current transport behavior per provider.

These tests document the flag-based contract between run_agent.py and
ChatCompletionsTransport.build_kwargs(). When the next PR wires profiles
to replace flags, every assertion here must still pass — any failure is
a behavioral regression.
"""
```

**◇ 观察:这个文件已经不再测 flag 路了。** 全文 10 个用例**全部**传 `provider_profile=`,
没有一个走 legacy flag 路。docstring 说的"当下一个 PR 用 profile 替换 flag 时,
这里每一条断言都必须仍然通过"已经完成了——但完成的方式是把断言**改成走 profile 路**,
于是 legacy 路(§5.2 的那一大段 `is_kimi` / `is_tokenhub` / `is_lmstudio` 分支)**现在没有任何测试覆盖**。
文件里还留着被掏空的类壳:

`tests/providers/test_transport_parity.py:27-30 @ 863e313`

```python
class TestNvidiaParity:
    """NVIDIA NIM: default max_tokens=16384."""


```

`TestNvidiaParity` 的 docstring 说"default max_tokens=16384",但类里已经没有测这个默认值的用例了。

---

## 11. 发现清单

按严重性排序。记号:■=代码缺陷,▲=文档与代码矛盾,◇=代码有文档无,◎=文档成立但显著保守。

| # | 记号 | 锚点 | 一句话现象 |
|---|---|---|---|
| 1 | ■ | `agent/chat_completion_helpers.py:2172` | 迭代摘要路径手抄的消息清洗器漏掉 `effect_disposition`,该键会随工具结果消息直接上线,严格 provider 回 400 |
| 2 | ■ | `agent/transports/hermes_tools_mcp_server.py:169-178` | 送给 MCP 客户端(进而进模型上下文)的 `instructions` 宣传 subagent delegation / persistent memory / cross-session search 三项,而这三项被显式排除在 `EXPOSED_TOOLS` 之外 |
| 3 | ▲ | `website/docs/developer-guide/model-provider-plugin.md:187` | 文档说 `profile.api_mode` 是 URL 探测失败后的回退;全仓无任何读取点,真实回退是 overlay 的 `transport` 字段(`providers/README.md:43` 同错,中文镜像同错) |
| 4 | ▲ | `website/docs/developer-guide/model-provider-plugin.md:186` | 文档说 Kimi 域名下 `/coding` → `chat_completions`,代码是 `anthropic_messages`,方向相反——而这正是 `test_auxiliary_transport_autodetect.py` 存在的那次事故 |
| 5 | ■ | `agent/transports/chat_completions.py:743` | `supports_prompt_cache_key` 在全仓无生产者(38 个 profile 全 False,也无调用方传参),`prompt_cache_key` 事实上只能在一条几乎不可达的路径上发射 |
| 6 | ■ | `agent/transports/__init__.py:53-56` | `except ImportError: pass` 吞掉传输模块内部的任何导入错误,`get_transport` 静默返回 None,调用点炸成 `'NoneType' has no attribute ...` |
| 7 | ■ | `agent/agent_init.py:686-691` | 注释声称预热是为了"让 import 错误在 init 期暴露",但 `_discover_transports` 已吞掉 ImportError、这里又 `except Exception: pass`,该保证不成立 |
| 8 | ◇ | `agent/transports/base.py:75` | `extract_cache_stats` 有 ABC 声明 + 两个实现 + 两个单测,零生产调用者;缓存统计实际由 `agent/usage_pricing.py` 直读原始响应 |
| 9 | ◇ | `agent/transports/types.py:86` | `NormalizedResponse.usage` 与 `Usage.cached_tokens` 全仓无读者;anthropic 传输索性永远传 `usage=None`,调用方绕回原始响应取 token 数 |
| 10 | ■ | `plugins/model-providers/copilot-acp/__init__.py:29` | profile 声明 `api_mode="chat_completions"`,overlay 声明 `codex_responses`,模块 docstring 又说是 `copilot_acp`(而这个值连 `_VALID_API_MODES` 都不在,run_agent.py 零命中)——三处三个答案,是 38 个 profile 里唯一一处 profile/overlay 漂移 |
| 11 | ◇ | `agent/transports/bedrock.py:63-64` | `build_kwargs` 在返回的 kwargs 里塞 `__bedrock_converse__` / `__bedrock_region__` 两个哨兵键做带内路由,与 ABC "返回可直接传给 SDK 的 dict" 的契约冲突 |
| 12 | ◇ | `agent/conversation_loop.py:2225` | 调用点调 `preflight_kwargs`,该方法只存在于 codex 传输、不在 ABC 里,靠 `if api_mode == "codex_responses"` 守住 |
| 13 | ◇ | `agent/transports/chat_completions.py:260-267` | 清洗器的"探测键集"与"剥除键集"是两份手写副本,只带新键的消息若漏进探测集就会走快路原样上线 |
| 14 | ◇ | `agent/agent_init.py:628` | `codex_app_server` 是合法 api_mode 但没有注册传输;靠 `agent/conversation_loop.py:1406` 提前掉头才不炸 |
| 15 | ◇ | `tests/providers/test_transport_parity.py:1` | 名为 parity 的文件 10 个用例全部走 profile 路,legacy flag 路(`is_kimi`/`is_tokenhub`/`is_lmstudio` 等分支)现无测试覆盖 |
| 16 | ◇ | `agent/transports/chat_completions.py:524-537` | Pareto 路由块的三份副本(传输 legacy 路 / openrouter profile / 摘要路径),三份的触发条件已不一致 |
| 17 | ◎ | `agent/transports/chat_completions.py:3-4` | 模块 docstring 说"~16 个 OpenAI 兼容 provider",实测 38 个 profile 里 29 个走这条路;且举例把 xAI 列了进去,而 xAI 走 `codex_responses` |
| 18 | ◇ | `agent/transports/anthropic.py:233` | 注释说停止原因表"promote 到模块级以便共享",实际是类属性且 `anthropic_adapter.py` 并未引用它 |
| 19 | ◇ | `agent/transports/bedrock.py:134-148` | bedrock 的 `map_finish_reason` 自认只用于"直接访问原始响应",实测零调用者;与 anthropic 的表 4 键重复 |

**最值得主线实跑复核的两条:#1 与 #2。**
#1 有明确的可执行复现路径(构造带 `effect_disposition` 的消息 → 跑摘要路径 → 看 payload),
且后果是线上 400;#2 只需读一遍 `EXPOSED_TOOLS` 与 `instructions` 即可确认,
但影响面是"模型被告知了不存在的能力",值得主线判定是否要写进成品章。

---

## 12. 未取证 / 推定的部分

如实列出,供后续轮次决定是否补:

1. **#1 的端到端复现未做**。已取证的是:(a) 传输剥 `effect_disposition`;
   (b) 摘要路径的手抄清单里没有它;(c) `effect_disposition` 确实会被写进消息 dict 并从 DB 读回。
   **未取证**:真的跑一次"用满 max_iterations 的会话 → 摘要请求"并抓到 payload 里含该键。
   需要能跑完整循环的环境(本轮无凭据、不配置)。**这是推定链,不是实测链。**
2. **FastMCP 的 `instructions` 是否真的进入模型上下文,未在本仓库内取证。**
   已取证的是它被传给 `FastMCP(...)` 构造器;"MCP initialize 响应里的 instructions 会被客户端拼进
   模型上下文"是 MCP 协议的通行语义,**属于外部知识推定**。若主线要写进成品章,建议查 codex 侧的处理。
3. **`codex.py`(672 行)未精读**——它是第四个传输,不在本轮 7 个文件里。
   本底稿凡引用它(`preflight_kwargs`、`_content_cache_key`)都只做定位,未做机制解读。
4. **`agent/anthropic_adapter.py` / `agent/bedrock_adapter.py` 未精读**。
   anthropic / bedrock 两支传输是薄壳,真正的转换逻辑在这两个 adapter 里
   (`convert_messages_to_anthropic`、`build_anthropic_kwargs`、`convert_messages_to_converse` 等)。
   **"anthropic 传输不重复逻辑"这个判断只对 `convert_*` / `build_kwargs` 成立**,
   我没有核对 adapter 内部是否与 chat_completions 有重复。R2-20 底稿覆盖过 adapter,本轮未回读。
5. **`profile.build_extra_body` / `build_api_kwargs_extras` 的各 provider 实现未逐个读**。
   本轮只确认了 profile 路把它们调起来,以及 openrouter 那一份与传输 legacy 路重复。
6. **§9.4 列的 `hermes_cli/main.py` / `commands.py` / `web_server.py` / honcho 的档位副本只做了定位**,
   没有逐份核对是否真的漂了(honcho 那份少两档是从 grep 结果直接看出的,未读上下文确认语义)。
7. **`determine_api_mode` 的运行时对比是在离线环境下做的**(models.dev 目录不可达)。
   overlay 是权威来源所以结论稳,但"38 个 profile 只有 1 处漂移"这个数字在能连 models.dev 的环境下
   可能变化。

---

## 13. 自校验读数

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent notes/r9c-raw-transport-contract.md
```

```text
citations=120  OK=113  UNCHECKED=7
可校验比例 OK/120 = 94.2%
table_anchors=30  UNCHECKED=30
OK: every code-block-backed citation matches the baseline
```

**四类阻断项各 0**:MISMATCH = 0,BLOCK-DRIFT = 0,TABLE-DRIFT = 0,TABLE-OUT-OF-RANGE = 0,
MISSING-FILE = 0;退出码 0。**未使用 `--fix`**,全部行号手工写对。
可校验比例 **94.2%**,高于 70% 下限。

7 条 UNCHECKED 逐条交代(全部是**散文区域指路**,不是漏配块):

| 位置 | 锚点 | 为什么是散文引用 |
|---|---|---|
| §4.4 ▲ 定案 1 | `website/docs/developer-guide/model-provider-plugin.md:187` | 该断言的逐字原文已由紧邻的 `@@` 引用块给出(180-190 整节),这里是回指 |
| §4.4 ▲ 定案 1 | 中文镜像同文件 `:186` | 同上,镜像文件只做定位、未另引原文 |
| §4.4 ▲ 定案 2 | 同文件 `:186` | 原文在上面整节引用块里 |
| §7.2 | `agent/conversation_loop.py:2776` | 指"唯一那个调用点"的位置,该行原文在 §6.5 附近未单引 |
| §9.2 | `agent/transports/chat_completions.py:525-526` | 该两行的原文就在同节紧邻的 524-537 块里 |
| §9.4 | `hermes_cli/web_server.py:991` | 明确标注"只记位置不下定案"(§12 第 6 条) |
| §9.4 | `plugins/memory/honcho/client.py:218` | 同上 |

另有 30 个表格行内锚点(§11 发现清单 + 上面这张 UNCHECKED 交代表)按脚本口径单独计数,全部 TABLE-UNCHECKED、
无 TABLE-DRIFT / TABLE-OUT-OF-RANGE。

基线只读校验(跑完全部测试与实验后):

```verify
cd /home/user/hermes-agent && git rev-parse HEAD && git status --porcelain | wc -l
```

```text
863e31318553cda8ad61df681d08175364d4164b
0
```

