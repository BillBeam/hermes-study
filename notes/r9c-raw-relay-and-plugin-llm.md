# R9C 底稿 · 中继与插件 LLM —— agent 侧 relay / plugin_llm / Copilot ACP

> 本文件是 R9C **C 片子代理**的证据层底稿,面向"要凭它重实现同等机制的自己"。
> 全部锚点针对基线 `863e313`;锚点一律单独成行、置于代码块之前。
> 覆盖 5 个文件:`agent/relay_llm.py`(1239)、`agent/plugin_llm.py`(1046)、
> `agent/relay_runtime.py`(1036)、`agent/copilot_acp_client.py`(756)、
> `agent/relay_tools.py`(123),合计 4200 行。

---

## 0. 开工前必须先纠正的三个命名陷阱

本簇被交下来时带着一个主题描述:「模型能力的第三类来源:通过 relay 借别人的模型、
通过 plugin 注入自定义 LLM、通过 Copilot ACP 接 GitHub Copilot」。
读完 4200 行后,**前两句的方向都是反的**,第三句准确。先把这三件事钉死,
否则后面每一段都会被带偏:

| 命名 | 直觉理解 | 代码实际是什么 |
|---|---|---|
| agent 侧 `relay_*` | "借别人的模型" | **NVIDIA NeMo Relay**:一个把 LLM 调用/工具调用包进可观测作用域并允许改写的运行时;它不提供任何模型 |
| `plugin_llm` | "插件注入自定义 LLM" | **反向**:宿主把自己已解析好的模型与凭据借给插件用,插件不带自己的 key |
| `copilot_acp_client` | 接 GitHub Copilot | 准确;Hermes 在这里是 **ACP 客户端**,Copilot CLI 是 ACP 代理 |

三条路径的共同点其实不是"第三类模型来源",而是**同一个信任边界问题的三种形态**:
一段不属于 Hermes 主干的代码(第三方 wheel / 插件 / 子进程)要参与到一次模型调用里,
Hermes 分别给了它多大的权限、凭据走到哪一层为止。这条线是本底稿的主线,见 §4。

---

## 1. agent 侧 relay = NVIDIA NeMo Relay,与网关 relay 是**两套同名机制**

### 1.1 先结清主线交下来的那条问题

R9B 定案的 ■ 在 `gateway/relay/media.py:92-94`。本片要回答的是:那个 relay 和
`agent/relay_*.py` 是不是同一套?**不是。两者除了英文单词相同,没有任何代码联系。**

agent 侧三个模块的自我定性,三行 docstring 就说清了:

`agent/relay_runtime.py:1 @ 863e313`

```python
"""Profile-scoped NeMo Relay runtimes owned by the Hermes agent core."""
```

`agent/relay_llm.py:1 @ 863e313`

```python
"""Core NeMo Relay adapters for physical Hermes provider attempts."""
```

`agent/relay_tools.py:1 @ 863e313`

```python
"""Core NeMo Relay adapter for Hermes tool execution."""
```

"NeMo Relay" 是 NVIDIA 的 agent 运行时可观测层(一句话锚定:它定义"作用域 / scope"这种
嵌套执行边界,把每次 LLM 调用、每次工具调用登记成一棵可导出的树,并允许在边界上
**改写**请求)。它由一个外部 Python wheel 提供,Hermes 只在真正需要时才 import:

`agent/relay_runtime.py:1023-1025 @ 863e313`

```python
def _load_nemo_relay() -> Any:
    """Load the binding only when a producer or consumer needs Relay."""
    return importlib.import_module("nemo_relay")
```

网关侧的 relay 则是 Hermes Gateway 自己的「连接器中继」——一个把 Discord/Telegram
这类平台连接器与网关用 WebSocket 接起来的跨仓库协议:

`gateway/relay/__init__.py:1-9 @ 863e313`

```python
"""Relay/connector support package for the Hermes gateway.

EXPERIMENTAL. This package implements the gateway side of the "Gateway Gateway"
relay design: a generic ``RelayAdapter`` plus the wire-serializable
``CapabilityDescriptor`` the connector hands it at handshake time, and the
production ``WebSocketRelayTransport`` that dials the connector. The public API
(module names, descriptor field set, transport protocol) MAY CHANGE without a
deprecation cycle until at least two real Class-1 platforms (Discord + Telegram)
have shaken out the schema.
```

R9B 那条 ■ 所在的函数,属于这条网关中继链路(它判断的是「这个 URL 是不是连接器
把媒体重新托管出来的引用」,判是就挂网关 bearer):

`gateway/relay/media.py:92-94 @ 863e313`

```python
    def is_relay_media_url(self, url: str) -> bool:
        """Is ``url`` a connector re-host reference (needs our bearer to GET)?"""
        return "/relay/media/" in (url or "")
```

**两套体系的凭据也不同源、且被显式隔离。** 网关中继的凭据是 `GATEWAY_RELAY_*`
一族环境变量;子进程环境净化器把它们列为"任何子进程都不得看到"的 Hermes 内部密钥:

`tools/environments/local.py:611-620 @ 863e313`

```python
    # Internal routing hints and Hermes-internal dynamic secrets
    # (``AUXILIARY_<TASK>_API_KEY`` / ``_BASE_URL`` side-LLM credentials,
    # ``GATEWAY_RELAY_*`` relay-auth material) must never reach a child,
    # regardless of ``inherit_credentials`` — a model-driving CLI has no
    # legitimate use for them. See :func:`_is_hermes_internal_secret`.
    for key in list(env):
        if key.startswith(_HERMES_PROVIDER_ENV_FORCE_PREFIX):
            env.pop(key, None)
        elif _is_hermes_internal_secret(key):
            env.pop(key, None)
```

而 NeMo Relay 侧根本没有 Hermes 发放的凭据(见 §1.6)。

**结论(带搜索面的负结论)**:`gateway/` 目录下 **0 处**引用 agent 侧 relay 模块或
`nemo_relay`;`agent/relay_llm.py`、`agent/relay_runtime.py`、`agent/relay_tools.py`
三个文件的 import 段(逐行看过,共 3 段)**没有任何 `gateway.*`**。搜索面 = 全仓 `*.py`,
模式 = `relay_runtime|relay_llm|relay_tools|nemo_relay`,未排除任何目录:

```verify
cd /home/user/hermes-agent && \
  grep -rn "relay_runtime\|relay_llm\|relay_tools\|nemo_relay" --include=*.py gateway/ ; \
  echo "gateway 侧命中数 = $(grep -rn 'relay_runtime\|relay_llm\|relay_tools\|nemo_relay' --include=*.py gateway/ | wc -l)"
```

实测输出 `gateway 侧命中数 = 0`。反向也一样:上面三个文件的 import 全部是
stdlib + `agent.relay_runtime` + `hermes_constants.get_hermes_home`,无 `gateway`。

**所以 R9B 那条 ■ 的凭据面没有因为本片而扩大**:它只影响网关连接器媒体下载,
不触及 agent 侧任何 LLM 路径。

### 1.2 relay_runtime:profile 级宿主 + 会话/轮次/逻辑调用三层作用域

#### 解决什么问题

NeMo Relay 的作用域是**栈**语义(push/pop 必须 LIFO)。Hermes 的执行却是:
多 profile(不同 `HERMES_HOME`)、多会话、会话里有轮次、轮次里有一次"逻辑 LLM 调用"
(同一个 `api_request_id` 下可能发生多次重试和多次 provider 回退)。
`relay_runtime` 的全部工作就是把这个**非栈**的现实映射到一个**栈**上,并保证
任何一处失败都不影响模型结果。

四个作用域名与两个元数据键是全部契约:

`agent/relay_runtime.py:20-25 @ 863e313`

```python
SESSION_SCOPE = "hermes.session"
TURN_SCOPE = "hermes.turn"
LOGICAL_LLM_SCOPE = "hermes.logical_llm_call"
RUNTIME_SCHEMA_KEY = "hermes.relay.schema_version"
RUNTIME_SCHEMA_VERSION = "hermes.relay.runtime.v1"
RUNTIME_INSTANCE_KEY = "hermes.relay.runtime_instance"
```

三层的父子关系:`hermes.session`(ScopeType.Agent)→ `hermes.turn`(Function)
→ `hermes.logical_llm_call`(Function)→ Relay 自己的 llm/tool 执行作用域。

#### 隔离单位是 profile,不是进程

`RelayHostRegistry` 按 profile key(= 解析后的 `HERMES_HOME` 绝对路径)各持有一个宿主。
wheel 装不上或初始化失败时**不抛给调用方**,而是换成一个显式的降级宿主:

`agent/relay_runtime.py:428-436 @ 863e313`

```python
            try:
                host = RelayRuntime(profile_key=key)
            except Exception as exc:
                logger.warning(
                    "Hermes Relay runtime initialization failed", exc_info=True
                )
                host = NoopRelayRuntime(profile_key=key, reason=str(exc))
            self._hosts[key] = host
            return host
```

`agent/relay_runtime.py:367-376 @ 863e313`

```python
@dataclass(frozen=True)
class NoopRelayRuntime:
    """Explicit reduced-capability host for platforms without Relay wheels."""

    profile_key: str
    reason: str

    @property
    def available(self) -> bool:
        return False
```

**设计取舍**:用"显式降级对象"而不是 `None`,好处是所有调用点都能无条件调方法;
代价是它必须逐个补齐宿主接口,而它只补了 4 个(`apply_tool_request_intercepts`、
retain/release/`managed_execution_enabled` 三件套、`shutdown`)。
其余路径靠 `isinstance(host, RelayRuntime)` 判断绕开——也就是说**空对象模式只做了一半**,
真正起作用的还是类型判断。这是可以接受的,但要知道它不是纯 Null Object。

#### 「托管执行」是一个引用计数开关,默认关

这是本模块最重要、也最容易看漏的一件事:**Relay 的会话/轮次作用域是无条件建的,
而 LLM/工具执行走不走 Relay 是有条件的**,条件就是有没有"消费者"按下这个开关:

`agent/relay_runtime.py:57-72 @ 863e313`

```python
    def retain_managed_execution(self, consumer: str) -> None:
        """Keep managed LLM and tool execution active for one consumer."""
        if not consumer:
            raise ValueError("Relay managed-execution consumer must not be empty")
        with self._execution_consumers_lock:
            self._execution_consumers.add(consumer)

    def release_managed_execution(self, consumer: str) -> None:
        """Release a consumer's managed-execution requirement."""
        with self._execution_consumers_lock:
            self._execution_consumers.discard(consumer)

    def managed_execution_enabled(self) -> bool:
        """Return whether a Hermes-managed consumer needs the Relay pipeline."""
        with self._execution_consumers_lock:
            return bool(self._execution_consumers)
```

两个消费者的调用形状完全一样——注册一个 Relay 订阅者,然后**为这个订阅者**保留托管执行:

`hermes_cli/observability/relay_shared_metrics.py:143-145 @ 863e313`

```python
        self.relay.subscribers.register(self._subscriber_name, self.subscriber)
        self.host.retain_managed_execution(self._subscriber_name)
        self._registered = True
```

全仓只有**两个** `retain_managed_execution` 调用点:

```verify
cd /home/user/hermes-agent && grep -rn "retain_managed_execution" --include=*.py agent hermes_cli plugins | grep -v "def retain"
```

实测输出两行:`hermes_cli/observability/relay_shared_metrics.py:144` 与
`plugins/observability/nemo_relay/__init__.py:231`。前者受 `telemetry.shared_metrics.enabled`
门控,**默认 false**:

`hermes_cli/config_defaults.py:2739-2743 @ 863e313`

```python
    "telemetry": {
        "shared_metrics": {
            "enabled": False,
        },
    },
```

后者要 `hermes plugins enable observability/nemo_relay` 才装载,且还要 ATOF/ATIF/plugins.toml
其中之一真的开着:

`plugins/observability/nemo_relay/__init__.py:224-235 @ 863e313`

```python
    def _sync_managed_execution(self) -> None:
        required = bool(
            self._plugin_config_initialized
            or self.atof_exporter is not None
            or self.settings.atif_enabled
        )
        if required and not self._execution_consumer_retained:
            self.host.retain_managed_execution(self._execution_consumer_name)
            self._execution_consumer_retained = True
        elif not required and self._execution_consumer_retained:
            self.host.release_managed_execution(self._execution_consumer_name)
            self._execution_consumer_retained = False
```

**所以默认安装、默认配置下,一次模型调用完全不经过 Relay。** 这条会在 §1.6 变成一条 ▲。

#### 会话/轮次作用域却是无条件建的

`run_agent.py` 每个任务运行都无条件取一次会话租约并开一个轮次:

`run_agent.py:7812-7818 @ 863e313`

```python
            relay_lease = relay_runtime.SESSION_COORDINATOR.acquire_conversation(
                profile_key=relay_runtime.current_profile_key(),
                session_id=task_context["session_id"],
                platform=task_context["platform"],
                parent_session_id=relay_parent_session_id,
                model=str(getattr(self, "model", None) or ""),
            )
```

`acquire_conversation` → `registry.for_profile(create=True)` → `RelayRuntime(...)` →
`importlib.import_module("nemo_relay")`。**含义:只要 wheel 装着,即使没人要 Relay,
每个 profile 首次运行也会 import 它并 push 一个会话作用域。** 代价是一次 import
+ 每轮两次 push/pop;收益是"插件中途 enable 后立刻有父作用域可挂"。

#### 并发轮次的处理:退出而不是排队

同一 (profile, session) 已有活跃轮次时,新轮次**主动放弃**自己的 Relay 埋点:

`agent/relay_runtime.py:602-614 @ 863e313`

```python
        with self._active_turns_lock:
            active = self._active_turns.get(key)
            if active:
                # A Relay session owns one physical scope stack. Concurrent
                # Hermes turns would create sibling scopes on that stack, but
                # their completion order is not guaranteed to be LIFO.
                turn.relay_enabled = False
                logger.warning(
                    "Skipping Relay instrumentation for concurrent Hermes turn "
                    "%s in session %s",
                    turn_id,
                    lease.session_id,
                )
```

这是把"栈不能并发"这个外部约束直接翻译成"第二个并发轮次不埋点"。取舍很清楚:
**宁可丢一部分观测数据,也不要让 pop 顺序错乱去污染整棵树**。
`relay_enabled=False` 之后,`active_turn()`/`resolve_execution_context()` 都会
把这一轮当作"没有 Relay",于是 LLM/工具照常直连 provider。

#### 统一入口 `resolve_execution_context`

三个执行适配器(`relay_llm.execute` / `execute_async` / `relay_tools.execute` /
`ManagedLlmStream.__init__`)全部以它开场,它是"要不要托管"的唯一判定处:

`agent/relay_runtime.py:842-866 @ 863e313`

```python
def resolve_execution_context(
    session_id: str,
) -> tuple[RelayRuntime | None, RelaySession | None, Any]:
    """Resolve one active turn/session parent for managed Relay execution."""
    inherited_turn = current_turn()
    if inherited_turn is not None and (
        not inherited_turn.relay_enabled or inherited_turn.closed
    ):
        return None, None, None
    turn = active_turn(session_id)
    if (
        turn is not None
        and isinstance(turn.lease.host, RelayRuntime)
        and turn.lease.session is not None
    ):
        session = turn.lease.session
        return turn.lease.host, session, turn.handle or session.handle
    # Managed-execution consumers create and retain the profile host before
    # reaching an out-of-turn adapter. Do not initialize Relay for the default
    # no-consumer path.
    runtime = get_runtime(create=False)
    if runtime is None:
        return None, None, None
    if not runtime.managed_execution_enabled():
        return None, None, None
```

三条退出路径值得记住:(a) 继承来的轮次已关闭/已放弃 → 不托管;
(b) 有匹配的活跃轮次 → 用轮次 handle 当父;(c) 没有轮次但有消费者 → 退回会话级 handle
(这是给"轮次之外的辅助调用"留的口子)。

### 1.3 relay_llm:一次**物理** provider 尝试

#### 逻辑调用 vs 物理尝试

Hermes 一次"模型请求"(一个 `api_request_id`)可能物理上发出多次:重试、
provider 回退、辅助任务的多候选。`relay_llm` 的做法是:
**逻辑调用一个作用域,物理尝试各一个子作用域**。逻辑作用域按 `api_request_id` 缓存在轮次上:

`agent/relay_llm.py:820-832 @ 863e313`

```python
def _logical_parent(
    runtime: relay_runtime.RelayRuntime,
    session: Any,
    parent: Any,
    metadata: dict[str, Any] | None,
) -> tuple[relay_runtime.RelayTurnContext, Any, str] | None:
    turn = relay_runtime.active_turn(session.session_id)
    request_id = str((metadata or {}).get("api_request_id") or "")
    if turn is None or not request_id or turn.lease.host is not runtime:
        return None
    with turn.finalize_lock:
        if turn.closed:
            return None
```

`defer_logical_completion=True` 的调用方(主循环、辅助客户端)负责在自己判定
最终成败后调 `complete_logical_call(api_request_id, outcome=...)` 收口——
所以三次重试在 trace 里是**一个**逻辑调用带三个物理子调用,而不是三个独立调用。

#### 不托管时的形状:一行直通

`agent/relay_llm.py:27-40 @ 863e313`

```python
def execute(
    request: dict[str, Any],
    callback: Callable[[dict[str, Any]], Any],
    *,
    session_id: str,
    name: str,
    model_name: str,
    metadata: dict[str, Any] | None = None,
    defer_logical_completion: bool = False,
) -> Any:
    """Run one non-streaming physical provider attempt through Relay."""
    runtime, session, parent = relay_runtime.resolve_execution_context(session_id)
    if runtime is None or session is None or not runtime.managed_execution_enabled():
        return callback(request)
```

`relay_tools.execute` 是完全对称的:

`agent/relay_tools.py:18-29 @ 863e313`

```python
def execute(
    tool_name: str,
    args: dict[str, Any],
    callback: Callable[[dict[str, Any]], Any],
    *,
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Run one tool call through Relay and return its final arguments."""
    runtime, session, parent = relay_runtime.resolve_execution_context(session_id)
    if runtime is None or session is None or not runtime.managed_execution_enabled():
        return callback(args), args
```

这个形状是整个 Relay 集成"可失效性"的基础:**适配器是一层可拆的壳,拆掉之后
调用方拿到的就是原来的 `callback(request)` 返回值**。

#### Relay 可以改写请求,而且是双向的

托管路径下,Hermes 把请求交给 `relay.llm.execute(name, relay_request, invoke, ...)`,
Relay 在调 `invoke` 时可以把请求换成改写后的版本。`_provider_request` 负责
把"改写"叠回原始 provider 请求上——注意它**不是**直接用 Relay 给的 body:

`agent/relay_llm.py:985-995 @ 863e313`

```python
        # Typed codecs may not represent provider-specific fields. Overlay only
        # values that changed from the codec-facing baseline so unrelated
        # intercepts cannot delete or normalize unknown provider arguments.
        for key in baseline.keys() | intercepted.keys():
            if key not in intercepted:
                final.pop(key, None)
            elif key not in baseline or not _json_equal(
                intercepted[key],
                baseline[key],
            ):
                final[key] = intercepted[key]
```

这一段是本文件最精巧的设计:Relay 的类型化 codec(OpenAI Chat / Anthropic Messages /
OpenAI Responses 三种)只认识标准字段,一旦 round-trip 就会把 provider 私有字段
(如 Anthropic 的 `cache_control`、reasoning 扩展)洗掉。做法是先算一个
"只过 codec、无人改写"的**基线** body,再只把 `intercepted` 与 `baseline` 不同的键
覆盖回原始请求。**即"用差分而不是替换来接受外部改写"**,值得抄。

配套的兜底还有一层:codec 无法表达的消息级扩展字段被显式点名恢复。

`agent/relay_llm.py:19-24 @ 863e313`

```python
_PROVIDER_MESSAGE_EXTENSION_KEYS = frozenset(
    {"reasoning_content", "reasoning_details"}
)
_RELAY_INTERNAL_PROVIDER_HEADERS = frozenset(
    {"x-dynamo-parent-session-id", "x-dynamo-session-id"}
)
```

#### 请求头也一并接受 Relay 改写(只剔两个内部头)

`agent/relay_llm.py:1002-1014 @ 863e313`

```python
    headers = getattr(request, "headers", None)
    if isinstance(headers, dict):
        headers = {
            key: value
            for key, value in headers.items()
            if str(key).lower() not in _RELAY_INTERNAL_PROVIDER_HEADERS
        }
    if headers:
        final["extra_headers"] = {
            **dict(final.get("extra_headers") or {}),
            **headers,
        }
    return final
```

**信任边界读法**:Relay 侧返回的任意 header 会被合并进 `extra_headers` 发给 provider,
只有 `x-dynamo-*` 两个内部头被剔除。也就是说一个 Relay 拦截器可以给出站请求加/改
任意头,**包括 `Authorization`**。这不是提权(NeMo Relay 是进程内 wheel,本就全权),
但它意味着**"启用 NeMo Relay 观测" = 把出站模型请求的最终形态交给第三方 wheel**。
文档没有讲这一点,见 §1.6 的 ◇。

#### 流式:自建事件循环,把 async 流拉成同步迭代器

`ManagedLlmStream` 是本文件行数最多的部分。要点四条:

1. `asyncio.new_event_loop()` + `run_until_complete(anext(...))` —— Hermes 的
   provider 工作线程是同步的,而 Relay 的流是 async 的,于是每个托管流自带一个循环。
2. `_raw_chunks` 保留 provider 原始 chunk 对象;若 Relay 吐回的 chunk 与某个原始
   chunk JSON 等价,就**返回原始对象**而不是重新构造的 namespace(保住下游的
   duck-typing);不等价才置 `output_modified=True` 并走 `_chunk_adapter`。
3. `_preserve_pending_provider_chunks()`:Relay 在 provider 已经出完 chunk 之后
   才失败(后处理失败),不让它吃掉已经拿到的内容——把未投递的原始 chunk 换成
   一个普通迭代器继续供货,并把逻辑调用记成 success。
4. `stream_current` 在已有运行中事件循环时**直接返回原始 stream**,不建嵌套托管流
   ——因为同一线程上再 `run_until_complete` 会炸。

第 3 条的实现:

`agent/relay_llm.py:631-640 @ 863e313`

```python
    def _preserve_pending_provider_chunks(self) -> None:
        """Switch a failed Relay stream to its undelivered provider chunks."""
        pending = [raw for _encoded, raw in self._raw_chunks]
        self._raw_chunks.clear()
        loop = self._loop
        relay_stream = self._stream
        self._loop = None
        self._stream = iter(pending)
        self._raw_stream_resource = None
        self._accept_chunk = None
```

第 4 条连同它的历史事故说明(两条 issue 号)都写在 docstring 里:

`agent/relay_llm.py:269-293 @ 863e313`

```python
    """Run a provider stream under the inherited Hermes turn when present.

    When ``completed_response_predicate`` is set and the stream_factory returns
    a complete response instead of an iterator (e.g. AnthropicAuxiliaryClient
    and other shims that ignore ``stream=True``), unwrap and return the
    completed response directly. This mirrors the pre-Relay behavior where
    ``call_llm(stream=True)`` returned the raw response and the consumer's
    own ``hasattr(stream, "choices")`` check handled it (#11732, #55933) —
    without the unwrap the response stays trapped as ``final_response`` on the
    inner ManagedLlmStream and the outer consumer sees an empty stream.
    """
    turn = relay_runtime.active_turn()
    if turn is None:
        return stream_factory(request)
    if _has_running_event_loop():
        # Managed provider callbacks execute on the Relay session's event
        # loop. A nested ManagedLlmStream built here would be synchronously
        # iterated on that same loop thread, which asyncio forbids
        # ("Cannot run the event loop while another loop is running").
        # Return the raw factory result instead: the outer managed stream
        # already provides Relay tracking for the enclosing attempt, and its
        # own completed_response_predicate traps a completed response (e.g.
        # the MoA facade's auxiliary ``call_llm(stream=True)`` returning a
        # full response when an adapter ignores ``stream=True``).
        return stream_factory(request)
```

第 3 条与非流式的 `_recover_successful_callback`、`relay_tools` 里那段
"post-processing failed after dispatch success" 是同一条原则的三处实现:
**provider 已经成功的结果永远优先于 Relay 的后处理错误**。工具侧那处最短,
最能看清这条原则:

`agent/relay_tools.py:66-77 @ 863e313`

```python
        if (
            isinstance(exc, Exception)
            and callback_error is None
            and "value" in raw_result
        ):
            logger.warning(
                "NeMo Relay tool post-processing failed after dispatch success; "
                "returning the Hermes tool result",
                exc_info=True,
            )
            return raw_result["value"], observed_args
        raise
```

### 1.4 relay_tools:一次工具调用,以及 Relay 的**改写在授权之前**

工具侧只有 123 行,但它决定了一件比 LLM 侧更敏感的事:Relay 能改写工具参数,
那么改写发生在 Hermes 的审批/护栏**之前**还是**之后**?

答案写在被调函数的 docstring 里:

`agent/tool_executor.py:489 @ 863e313`

```python
    """Run Relay rewrites before Hermes policy and dispatch exactly once."""
```

结构是:`relay_tools.execute(name, args, _hermes_pipeline, ...)`,
即把"Hermes 的完整策略流水线"当作 Relay 的回调传进去:

`agent/tool_executor.py:637-648 @ 863e313`

```python
    result, _relay_args = relay_tools.execute(
        function_name,
        function_args,
        _hermes_pipeline,
        session_id=str(getattr(agent, "session_id", "") or ""),
        metadata={
            "task_id": effective_task_id or "",
            "turn_id": getattr(agent, "_current_turn_id", "") or "",
            "api_request_id": getattr(agent, "_current_api_request_id", "") or "",
            "tool_call_id": tool_call_id or "",
        },
    )
```

`_hermes_pipeline(relay_args)` 内部才依次跑 request middleware → pre_tool_call 钩子
→ 审批 → 护栏 → 真正 dispatch。**所以 Relay 改写后的参数要重新过一遍审批**,
这是正确的顺序(反过来就是"审批批的和执行的不是同一份参数")。

还有第二条 Relay 改写通道,挂在 middleware 层:

`hermes_cli/middleware.py:134-146 @ 863e313`

```python
    session_id = str(context.get("session_id") or "")
    skip_relay = bool(context.pop("skip_relay", False))
    if session_id and not skip_relay:
        from agent import relay_runtime

        relay_args = relay_runtime.apply_tool_request_intercepts(
            session_id=session_id,
            tool_name=tool_name,
            args=current_args,
        )
        if relay_args != current_args:
            current_args = _safe_copy(relay_args)
            trace.append({"source": "nemo_relay"})
```

`agent/relay_runtime.py:271-280 @ 863e313`

```python
    def apply_tool_request_intercepts(
        self,
        *,
        session_id: str,
        tool_name: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply Relay request rewriting before Hermes authorizes a tool call."""
        if not self.managed_execution_enabled():
            return args
```

注意 `_hermes_pipeline` 调 middleware 时传了 `skip_relay=True`,避免同一次调用被
Relay 改写两遍。这两条通道的分工是:`relay.tools.execute` 是**包裹**(能看到结果、
能改结果),`relay.tools.request_intercepts` 是**纯请求改写**(不参与执行)。

### 1.5 relay 三条路径的凭据流向

**结论:NeMo Relay 集成里 Hermes 不向 Relay 发放任何凭据。** 依据:

- 三个模块的 import 段无 auth/credential 相关模块(逐行看过,见 §1.1)。
- 传给 Relay 的只有:请求 body(`_jsonable(request)`)、`metadata`(`task_id`/`turn_id`/
  `api_request_id`/`tool_call_id`/`call_role`/`api_mode`/`retry_count`)、model 名、provider 名。
- 但请求 body **本身就含凭据以外的全部内容**(system prompt、全部消息、工具 schema);
  且 `extra_headers` 若由调用方带入 `request`,也会被 `_jsonable` 序列化进 Relay 请求体。

所以准确的说法是:**Hermes 不给 Relay 密钥,但把"密钥能换到的一切"给了 Relay**
——完整对话内容、工具参数与工具结果。这在信任模型上和给密钥的差别没有直觉上那么大,
是启用该插件时真正要评估的东西。

### 1.6 relay 部分的定案

#### ▲-R9C-1 · 插件 README 声称核心"无论插件是否启用都路由经 Relay",与代码相反

`plugins/observability/nemo_relay/README.md:171-173 @ 863e313`

> Hermes core routes provider and tool execution through NeMo Relay managed APIs
> regardless of whether this plugin is enabled. To install adaptive interceptors
> on those boundaries, include an adaptive component in the same `plugins.toml`:

按 CLAUDE.md 的判定要求,把整段与它所属标题一并判:该段落在
"## Enablement" 之后、"### Dynamic Plugins" 之前,讲的是 plugins.toml 配置;
第一句是对**核心行为**的全称陈述,第二句才转到 adaptive 拦截器的装法。

**第一句被代码证伪。** `relay_llm.execute` / `relay_tools.execute` 在
`not runtime.managed_execution_enabled()` 时直接 `return callback(...)`
(锚点见 §1.3 的两个块),而 `managed_execution_enabled()` 只有两个消费者会打开
(§1.2),两个都默认关。也就是说:**默认状态下 provider 与 tool 执行完全不经过
NeMo Relay managed API;真正"无论插件是否启用"的是会话/轮次作用域,不是执行路由。**
这一句恰好把有条件的和无条件的两件事说反了。

现成的行为规格就是仓库自己的用例:

`tests/agent/test_relay_tools.py:39-62 @ 863e313`

```python
def test_tool_adapter_bypasses_relay_without_an_active_consumer(
    relay_turn, monkeypatch
):
    relay = relay_turn
    runtime = relay_runtime.get_runtime()
    assert runtime is not None
    runtime.release_managed_execution("test.relay_tools")
    args = {"command": "pwd"}

    monkeypatch.setattr(
        relay.tools,
        "execute",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("inactive Relay must not manage the tool call")
        ),
    )

    result, final_args = relay_tools.execute(
        "terminal",
        args,
        lambda value: value,
        session_id="session-1",
    )

```

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
  HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/agent/test_relay_tools.py
```

实测 3 passed / 0 failed。

#### ◇-R9C-2 · Relay 能改写出站请求体与请求头,`website/docs` 里没有任何 NeMo Relay 页面

搜索面:`website/docs/**`,不区分大小写搜 `nemo relay` / `nemo_relay`,唯一命中是
`website/docs/user-guide/features/built-in-plugins.md`(内置插件清单里的一行条目)。
即**正式文档站没有 NeMo Relay 的机制页**,改写能力(§1.3 的 body 差分覆盖、
§1.3 的 header 合并、§1.4 的两条工具改写通道)只在插件 README 里以
"adaptive interceptors" 一词一笔带过。对一个能改 `Authorization` 头的机制,
这属于"代码有、文档无"。

#### ■-R9C-3 · `_jsonable` / `_json_equal` 在 relay_llm 与 relay_tools 里是**语义不同**的同名副本

`agent/relay_llm.py:1187-1208 @ 863e313`

```python
def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    model_dump = getattr(type(value), "model_dump", None)
    if callable(model_dump):
        try:
            return _jsonable(value.model_dump(mode="json"))
        except Exception:
            pass
    try:
        attributes = {
            str(key): item
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    except (TypeError, AttributeError):
        return str(value)
    return _jsonable(attributes) if attributes else str(value)
```

`agent/relay_tools.py:86-102 @ 863e313`

```python
def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _jsonable(model_dump(mode="json"))
        except Exception:
            pass
    try:
        return _jsonable(vars(value))
    except (TypeError, AttributeError):
        return str(value)
```

三处实质差异:

| 差异 | relay_llm 版 | relay_tools 版 |
|---|---|---|
| `model_dump` 取法 | 取自 `type(value)`,避免触发实例属性代理 | 取自实例 |
| 私有属性 | `if not str(key).startswith("_")` 过滤掉 | 不过滤,`vars()` 原样序列化 |
| `vars()` 为空 | 回落 `str(value)` | 返回空 dict |

第一条是 relay_llm 侧特意修过的(有专门用例
`tests/agent/test_relay_llm.py:191` `test_jsonable_does_not_probe_dynamic_attributes`),
**relay_tools 侧没有同步**。第二条的后果具体:一个返回自定义对象的工具,其
`_`-前缀私有属性会被原样写进 Relay trace / ATOF 导出;而 LLM 侧同样的对象不会。
严重性判为低(工具结果绝大多数是 str/dict),但这是"同一个 bug 修了一半"的典型形态。

`_json_equal` 同样分叉:relay_llm 版异常时 `return False`,relay_tools 版
异常时 `return left == right`。后者会让不可序列化对象走 Python 相等语义,
可能把"Relay 改过的结果"误判成"没改",于是返回原始结果——方向上是保守的,不算缺陷,
但两份实现的失败语义不一致本身就是维护风险。

#### 观察(非缺陷)· relay_runtime 的一部分公开 API 只有测试在用

搜索面:全仓 `*.py`,排除 `agent/relay_runtime.py` 自身。
`get_host`、模块级 `emit_mark`、`get_session_handle`、以及按名字引用的
`NoopRelayRuntime`,**非测试调用方均为 0**;
观测插件自己实现了 `mark()` 直接调 `relay.scope.event`,不走模块级 `emit_mark`。
`NoopRelayRuntime.available` / `.reason` 两个字段也没有非测试读者。
这说明"显式降级宿主"这个设计的**可观测部分**(告诉使用者为什么降级)还没有接出去。

---

## 2. plugin_llm:宿主把模型借给插件,不是插件注入模型

### 2.1 它解决什么问题(模块自己讲得很清楚)

`agent/plugin_llm.py:1 @ 863e313`

```python
"""
Plugin LLM facade — host-owned LLM access for trusted plugins.
==============================================================
```

场景是:一个插件(网关适配器、hook、slash 命令、定时任务)自己想调一次模型。
在此之前插件只能扩展既有子系统(`register_tool` / `register_platform` /
`register_memory_provider`),没有"我要自己发一次模型请求"的正规入口。
于是要么插件自带 API key(用户要配两遍、密钥多一份落盘),要么去 import 内部模块。
`plugin_llm` 就是那条正规入口。

**方向必须记牢:凭据全程留在宿主,插件拿到的只有文本与用量。**

`agent/plugin_llm.py:33-48 @ 863e313`

```python
The host owns provider routing, auth resolution, timeouts, and
fallback. The plugin never sees raw OAuth tokens or API keys. All
override knobs (``provider=``, ``model=``, ``agent_id=``,
``profile=``) are gated behind explicit per-plugin trust flags in
``config.yaml``::

    plugins:
      entries:
        my-plugin:
          llm:
            allow_provider_override: true
            allow_model_override: true
            allowed_providers: [openrouter, anthropic]   # optional
            allowed_models:    [openai/gpt-4o-mini]       # optional
            allow_agent_id_override: false
            allow_profile_override: false
```

### 2.2 扩展点契约:怎么注册、怎么被发现

**没有注册。** 这是它和 `register_tool` 那一族最大的不同——插件不注册任何东西,
它是**被给予**一个对象。发现路径是 `PluginContext` 上一个惰性 property:

`hermes_cli/plugins.py:365-369 @ 863e313`

```python
        if self._llm is None:
            from agent.plugin_llm import PluginLlm
            plugin_id = self.manifest.key or self.manifest.name
            self._llm = PluginLlm(plugin_id=plugin_id)
        return self._llm
```

- **身份来源**:`manifest.key or manifest.name`。嵌套插件(如 `memory/honcho`)
  用路径派生 key,扁平插件用 manifest 的 `name:`。这个 id 就是配置里
  `plugins.entries.<id>.llm.*` 的键。
- **懒构造**:第一次访问 `ctx.llm` 才 import `agent.plugin_llm`(避免插件发现期
  的循环依赖)。
- **单例**:每个 `PluginContext` 一个,缓存在 `self._llm`。

对外暴露的 API 面是 4 个方法(`complete` / `complete_structured` /
`acomplete` / `acomplete_structured`)+ 文件末尾这份显式导出清单:

`agent/plugin_llm.py:1036-1046 @ 863e313`

```python
__all__ = [
    "PluginLlm",
    "PluginLlmTextInput",
    "PluginLlmImageInput",
    "PluginLlmInput",
    "PluginLlmUsage",
    "PluginLlmCompleteResult",
    "PluginLlmStructuredResult",
    "PluginLlmTrustError",
    "make_plugin_llm_for_test",
]
```

注意 `make_plugin_llm_for_test` 也在 `__all__` 里,但它的 docstring 明写
"Not part of the public plugin API"——**导出清单与文档意图在这一项上不一致**,
是那种"迟早会被某个插件作者当公开 API 用"的小口子。

### 2.3 能覆盖什么:四个独立的信任开关,默认全关

`_resolve_trust_policy(plugin_id)` 每次调用都重读 `config.yaml`,不缓存:

`agent/plugin_llm.py:202-208 @ 863e313`

```python
def _resolve_trust_policy(plugin_id: str) -> _TrustPolicy:
    """Read ``plugins.entries.<plugin_id>.llm`` from config.yaml.

    Missing config → fully restrictive policy (default deny on every
    override). The policy is resolved per-call rather than cached so
    config edits take effect without restarting the agent.
    """
```

任何一层缺失(没有 `plugins` / 没有 `entries` / 没有本插件条目 / 没有 `llm` 块)
都 `return _TrustPolicy(plugin_id=...)`,即"全默认 = 全拒绝"的策略对象——
**fail-closed 是靠"数据类默认值即拒绝"实现的,不是靠一串 if 判断**。这是本模块
最值得抄的一处:把安全默认放进类型定义,而不是放进控制流。

允许清单的强制转换有一处细节值得抄:`["*"]` 表示任意;而**空列表 `[]` 表示全拒**:

`agent/plugin_llm.py:183-196 @ 863e313`

```python
def _coerce_allowlist(raw: Any) -> tuple[Optional[frozenset], bool]:
    """Coerce a YAML list into ``(frozenset_or_None, allow_any)``.

    ``["*"]`` (or any list containing ``"*"``) → ``(frozenset(), True)``.
    Any other list → ``(frozenset({...}), False)``.
    Missing / non-list → ``(None, False)`` meaning "no allowlist."
    """
    if not isinstance(raw, list):
        return None, False
    normalized = [_normalize_ref(item) for item in raw if isinstance(item, str)]
    allow_any = "*" in normalized
    cleaned = {item for item in normalized if item and item != "*"}
    if allow_any and not cleaned:
        return frozenset(), True
    if cleaned:
        return frozenset(cleaned), allow_any
    return frozenset(), allow_any
```

`[]` 时 `allow_any=False`、`cleaned` 为空,前两个 `return` 都不成立,
落到最后一行给出空 frozenset + `allow_any=False`,
后续 `normalized not in policy.allowed_providers` 恒真 → 全拒。
也就是"写了清单但写空"不会被当成"没写清单"。

四个开关各自独立判定,任一违规都抛,不静默降级。后两个开关的判定长这样
(注意最后一行:`requested_agent_id` 被**原样**返回,这是 ■-R9C-5 的起点):

`agent/plugin_llm.py:313-329 @ 863e313`

```python
    if requested_agent_id and not policy.allow_agent_id_override:
        raise PluginLlmTrustError(
            f"Plugin {policy.plugin_id!r} cannot run completions against a "
            f"non-default agent id (set plugins.entries.{policy.plugin_id}."
            f"llm.allow_agent_id_override to true to allow)."
        )

    if requested_profile:
        if not policy.allow_profile_override:
            raise PluginLlmTrustError(
                f"Plugin {policy.plugin_id!r} cannot override the auth profile "
                f"(set plugins.entries.{policy.plugin_id}.llm.allow_profile_override "
                f"to true to allow)."
            )
        final_profile = requested_profile.strip()

    return final_provider, final_model, requested_agent_id, final_profile
```

### 2.4 失败怎么隔离

三层:

1. **信任门失败** → `PluginLlmTrustError(PermissionError)` 直接抛给插件,
   错误信息里带上要设哪个配置键。这是**故意不静默降级**的:静默忽略 override
   会让插件以为自己用的是 A 模型其实是 B。
2. **配置读取失败** → `_resolve_trust_policy` 的 `except Exception` 返回最严策略。
3. **schema 校验** → `jsonschema` 未安装时 debug 日志跳过校验(JSON 仍解析);
   装了且校验失败则抛 `ValueError`。

注意第 3 层的取舍:**可选依赖缺失时是"放宽"而不是"拒绝"**,与信任门的 fail-closed
方向相反。理由说得通(schema 只是输出形状约束,不是权限),但值得在自己实现时明确写下来。

### 2.5 定案:两个被门控却不落地的 override

#### ■-R9C-4(本片最值得复核)· `profile=` 通过信任门后被塞进请求体发给 provider,宿主无人消费

`agent/plugin_llm.py:945-958 @ 863e313`

```python
        from agent.auxiliary_client import call_llm
        merged_extra = dict(extra_body or {})
        if profile_override:
            merged_extra.setdefault("metadata", {})["auth_profile"] = profile_override
        response = call_llm(
            task=None,
            provider=provider_override,
            model=model_override,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            extra_body=merged_extra or None,
        )
```

异步孪生分支是逐字相同的一份:

`agent/plugin_llm.py:989-996 @ 863e313`

```python
        from agent.auxiliary_client import async_call_llm
        merged_extra = dict(extra_body or {})
        if profile_override:
            merged_extra.setdefault("metadata", {})["auth_profile"] = profile_override
        response = await async_call_llm(
            task=None,
            provider=provider_override,
            model=model_override,
```

**负结论 + 搜索面**:`auth_profile` 这个键在全仓的写者是上面两行,**读者一个也没有**。
搜索面 = 仓库根递归,扩展名 `*.py *.ts *.tsx *.md *.yaml *.yml *.json`,
排除 `node_modules`,不排除 `tests/`:

```verify
cd /home/user/hermes-agent && grep -rn "auth_profile" \
  --include=*.py --include=*.ts --include=*.tsx --include=*.md \
  --include=*.yaml --include=*.yml --include=*.json . | grep -v node_modules
```

实测 11 行命中,其中只有 `agent/plugin_llm.py:948` 与 `:992` 与本机制有关;
其余是 `hermes_cli/web_server.py` 的 `_oauth_profile_name`(OAuth profile 名,另一回事)、
一条测试文件的 docstring、以及 openclaw 迁移脚本读源仓库的 `auth-profiles.json`。

**两个后果:**

(a) **`allow_profile_override: true` 是空开关。** 文档把它写成"让插件请求某个
已存的鉴权 profile(例如同一 provider 下的另一个 OAuth 账号)"——

`website/docs/developer-guide/plugin-llm-access.md:362-364 @ 863e313`

>         # Allow the plugin to request a specific stored auth profile
>         # (e.g. a different OAuth account on the same provider).
>         allow_profile_override: false

——但打开它以后,凭据选择**一点变化都没有**,调用仍走默认 profile。
运营者会以为自己做了一次授权决策,实际什么也没发生。

(b) **profile 名会被发到第三方。** `extra_body` 一路进到 `_build_call_kwargs`,
`merged_extra` 非空即写进 SDK 的 `extra_body`:

`agent/auxiliary_client.py:8043-8044 @ 863e313`

```python
    if merged_extra:
        kwargs["extra_body"] = merged_extra
```

再由 OpenAI SDK 并入请求 JSON body。于是 `{"metadata": {"auth_profile": "work"}}`
出现在发给 provider 的请求里。泄露量很小(一个用户自定义的 profile 名),
但它是**纯粹的净损失**:没有任何本地收益。

#### ■-R9C-5 · `agent_id=` 通过信任门后只写进返回值,不影响任何路由

`_check_overrides` 把 `requested_agent_id` **原样**返回(第三个位置,见 §2.3 的块
末行 `return final_provider, final_model, requested_agent_id, final_profile`),
四个调用点全部只把它用在结果对象上:

```verify
cd /home/user/hermes-agent && grep -n "eff_agent" agent/plugin_llm.py
```

实测 8 行:4 行是解包 `_check_overrides` 的返回,4 行是
`agent_id=eff_agent or "default"` 写进结果 dataclass。`_invoke_sync` / `_invoke_async`
的形参里**根本没有 agent 相关参数**:

`agent/plugin_llm.py:919-930 @ 863e313`

```python
    def _invoke_sync(
        self,
        *,
        messages: List[Dict[str, Any]],
        provider_override: Optional[str],
        model_override: Optional[str],
        profile_override: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
        timeout: Optional[float],
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str, Any]:
```

而门控的报错措辞是"cannot run completions against a non-default agent id"
(§2.3 的块,`agent/plugin_llm.py:315`),文档表格也把它列成一项能力:

`website/docs/developer-guide/plugin-llm-access.md:379 @ 863e313`

> | `agent_id=`     | denied  | `allow_agent_id_override: true`  |

**即"开了也没有跨 agent 调用"**。与 ■-R9C-4 同型:一个被认真守卫、认真报错、
认真写进文档的开关,后面没有接线。两者一起看,说明这个模块的信任门是
**先于**它要守卫的能力落地的——门修好了,门后的房间还没盖。

#### 观察 · 用例只覆盖信任门,不覆盖 override 的下游效果

`tests/agent/test_plugin_llm.py:297` 的 `test_complete_passes_through_trusted_overrides`
断言的是注入的 `sync_caller` 收到了 `profile_override == "work"`——注入 caller 恰好
绕开了 `_invoke_sync` 里那段 `auth_profile` 代码。也就是说**现有 26 个用例全绿,
和上面两条 ■ 并不矛盾**,因为没有任何用例走默认 caller 路径去看下游。

---

## 3. copilot_acp_client:Hermes 当 ACP 客户端,把 Copilot CLI 当模型后端

### 3.1 ACP 是什么,以及本仓库里它有**两个方向**

ACP(Agent Client Protocol,代理-客户端协议)是编辑器与编码代理之间的一套
JSON-RPC 2.0 over stdio 协议:一端是**客户端**(编辑器,提供文件系统、权限提示),
另一端是**代理**(会调模型、会要求读写文件)。

本仓库同时实现了两个方向,且**只有一个方向有文档**:

| 方向 | 实现 | Hermes 的角色 |
|---|---|---|
| `acp_adapter/server.py` | `HermesACPAgent` | Hermes 是**代理**,被 Zed 之类的编辑器驱动 |
| `agent/copilot_acp_client.py` | `CopilotACPClient` | Hermes 是**客户端**,驱动 Copilot CLI |

`website/docs/developer-guide/acp-internals.md` 通篇只讲第一个方向
(全文 181 行,搜 `copilot` 命中 0 次)。第二个方向在 `website/docs/integrations/providers.md`
里只有 provider 选择层面的三行说明,没有协议层描述。

### 3.2 它把自己伪装成 OpenAI 客户端

`agent/copilot_acp_client.py:1-7 @ 863e313`

```python
"""OpenAI-compatible shim that forwards Hermes requests to `copilot --acp`.

This adapter lets Hermes treat the GitHub Copilot ACP server as a chat-style
backend. Each request starts a short-lived ACP session, sends the formatted
conversation as a single prompt, collects text chunks, and converts the result
back into the minimal shape Hermes expects from an OpenAI client.
"""
```

伪装的全部实现就是两个壳类:

`agent/copilot_acp_client.py:383-393 @ 863e313`

```python
class _ACPChatCompletions:
    def __init__(self, client: "CopilotACPClient"):
        self._client = client

    def create(self, **kwargs: Any) -> Any:
        return self._client._create_chat_completion(**kwargs)


class _ACPChatNamespace:
    def __init__(self, client: "CopilotACPClient"):
        self.completions = _ACPChatCompletions(client)
```

**注意:只有 `.chat.completions.create`,没有 `.responses`。** 这一点在 §3.6 会变成
一条跨文件不一致。

上游怎么拿到它:

`agent/agent_runtime_helpers.py:2258-2261 @ 863e313`

```python
    if agent.provider == "copilot-acp" or str(client_kwargs.get("base_url", "")).startswith("acp://copilot"):
        from agent.copilot_acp_client import CopilotACPClient

        client = CopilotACPClient(**client_kwargs)
```

即用一个假的 URL scheme `acp://copilot` 当路由标记。provider 注册表里它是
`auth_type="external_process"`:

`hermes_cli/auth.py:263-269 @ 863e313`

```python
    "copilot-acp": ProviderConfig(
        id="copilot-acp",
        name="GitHub Copilot ACP",
        auth_type="external_process",
        inference_base_url=DEFAULT_COPILOT_ACP_BASE_URL,
        base_url_env_var="COPILOT_ACP_BASE_URL",
    ),
```

`command` / `args` 由 agent 初始化时塞进 client_kwargs:

`agent/agent_init.py:1171-1173 @ 863e313`

```python
            if agent.provider == "copilot-acp":
                client_kwargs["command"] = agent.acp_command
                client_kwargs["args"] = agent.acp_args
```

### 3.3 为什么它不在 `agent/transports/` 下

`agent/transports/` 是**响应归一化**层:注册表按 `api_mode` 字符串给出一个
transport 实例,它的职责是 `normalize_response(raw_response)` → `NormalizedResponse`。
`copilot_acp_client` 的职责完全不同——它是**客户端对象**(替代 `OpenAI(...)` 实例),
负责建立连接、发请求、拿回一个已经长得像 OpenAI 响应的对象。

两者是流水线上前后两段:client 产出 raw response,transport 归一化它。
`copilot-acp` 用的 transport 仍然是 `chat_completions` 那一个,因为
`_create_chat_completion` 已经把 ACP 结果拼成了 OpenAI 形状
(`SimpleNamespace(choices=[...], usage=..., model=...)`)。

同目录下的 `agent/transports/codex_app_server.py` 是个有意思的反例:它也 spawn 子进程,
却在 transports 下——因为它实现的是一个真正的 `api_mode`(`codex_app_server`),
而 `copilot_acp` 从来不是一个 api_mode(见 §3.6)。该文件的注释还直接点名了本文件
的凭据处理作为参照:

`agent/transports/codex_app_server.py:85-90 @ 863e313`

```python
        # session token, AUXILIARY_* side-LLM keys, GATEWAY_RELAY_* auth — none
        # of which a coding subprocess has any use for. Route through the
        # centralized helper so Tier-1 + dynamic-internal secrets are always
        # stripped while provider creds still flow, matching copilot_acp_client
        # (#29157 sibling spawn-site gap).
        spawn_env = hermes_subprocess_env(inherit_credentials=True)
```

**可迁移的判据**:"要不要放进 transports"看的是**它是否引入一种新的线协议形状**,
而不是"它是否跨进程"。

### 3.4 握手、鉴权与一次请求的完整走法

一次 `create()` 的生命周期是**一个短命子进程**:

1. `subprocess.Popen([command] + args, stdin/stdout/stderr=PIPE, text=True,
   cwd=self._acp_cwd, env=_build_subprocess_env())`;两个守护线程分别读 stdout(逐行 JSON)
   与 stderr(保留最后 40 行做诊断)。
2. `initialize` → `session/new` → `session/prompt`,三个 JSON-RPC 请求,自增 id。
3. `finally: self.close()` —— **每次请求结束都 terminate 子进程**。

`agent/copilot_acp_client.py:620-644 @ 863e313`

```python
        try:
            _request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {
                        "fs": {
                            "readTextFile": True,
                            "writeTextFile": True,
                        }
                    },
                    "clientInfo": {
                        "name": "hermes-agent",
                        "title": "Hermes Agent",
                        "version": "0.0.0",
                    },
                },
            )
            session = _request(
                "session/new",
                {
                    "cwd": self._acp_cwd,
                    "mcpServers": [],
                },
            ) or {}
```

**鉴权:Hermes 一侧不做任何鉴权。** ACP 协议本身有 `authenticate` 方法,这里没调;
`api_key` 字段被填成常量字符串,只是为了让上游"provider 必须有 key"的检查通过:

`hermes_cli/auth.py:7256-7263 @ 863e313`

```python
    return {
        "provider": provider_id,
        "api_key": "copilot-acp",
        "base_url": base_url.rstrip("/"),
        "command": resolved_command or command,
        "args": args,
        "source": "process",
    }
```

**真正的鉴权发生在 Copilot CLI 自己的 `copilot login` 会话里,Hermes 完全不参与。**
`resolve_external_process_provider_credentials` 唯一做的"认证检查"是
`shutil.which(command)` 找得到二进制。

命令与参数来自环境变量,默认 `copilot --acp --stdio`:

`agent/copilot_acp_client.py:62-74 @ 863e313`

```python
def _resolve_command() -> str:
    return (
        os.getenv("HERMES_COPILOT_ACP_COMMAND", "").strip()
        or os.getenv("COPILOT_CLI_PATH", "").strip()
        or "copilot"
    )


def _resolve_args() -> list[str]:
    raw = os.getenv("HERMES_COPILOT_ACP_ARGS", "").strip()
    if not raw:
        return ["--acp", "--stdio"]
    return shlex.split(raw)
```

对话怎么过去:**整段对话被拍平成一个纯文本 prompt**,工具 schema 以 JSON 附在文本里,
并要求模型用 `<tool_call>{...}</tool_call>` 块输出工具调用:

`agent/copilot_acp_client.py:137-145 @ 863e313`

```python
def _format_messages_as_prompt(
    messages: list[dict[str, Any]],
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: Any = None,
) -> str:
    sections: list[str] = [
        "You are being used as the active ACP agent backend for Hermes.",
        "Use ACP capabilities to complete tasks.",
```

回来再用两个正则把 tool_call 抠出来(先 XML 块,一个都没抠到才退到裸 JSON):

`agent/copilot_acp_client.py:36-37 @ 863e313`

```python
_TOOL_CALL_BLOCK_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_TOOL_CALL_JSON_RE = re.compile(r"\{\s*\"id\"\s*:\s*\"[^\"]+\"\s*,\s*\"type\"\s*:\s*\"function\"\s*,\s*\"function\"\s*:\s*\{.*?\}\s*\}", re.DOTALL)
```

即**协议级 tool-calling 被降级成了 prompt 约定 + 文本解析**。
`usage` 全部填 0,`stream=True` 时把一次性结果切成两个假 chunk
(一个带 delta、一个带 usage)。这是接入代价:token 计费、prompt cache、
真正的流式增量,这条路径上全部拿不到。

### 3.5 凭据流向与信任边界(本片最实的一段)

**出方向(Hermes → 子进程):**

`agent/copilot_acp_client.py:102-110 @ 863e313`

```python
def _build_subprocess_env() -> dict[str, str]:
    # Copilot ACP is a model-driving CLI executor: it legitimately needs LLM
    # provider credentials. Route through the central helper so Tier-1 secrets
    # (gateway bot tokens, GitHub auth, infra) are still stripped (#29157).
    env = hermes_subprocess_env(inherit_credentials=True)
    home = _resolve_home_dir()
    env["HOME"] = home
    from hermes_constants import apply_subprocess_home_env
    apply_subprocess_home_env(env)
```

`inherit_credentials=True` 意味着 **LLM provider 的 API key 全部传给 Copilot CLI 子进程**;
只有 Tier-1(网关 bot token、GitHub 认证、远程算力密钥)与 Hermes 内部动态密钥
(`AUXILIARY_*`、`GATEWAY_RELAY_*`)被剥掉(§1.1 的块)。
文件里那句注释把理由写明了:它是"model-driving CLI executor",合法需要模型凭据。

`grep -rn 'inherit_credentials=True'` 是仓库自己设计的审计入口(helper docstring 里写着),
这条设计值得抄:**把"哪些子进程还能拿到密钥"变成一次 grep 就能列全的清单**。

另一条相关硬化在 env 加载器侧:决定"跑哪个二进制、带什么参数"的四个键被列为
profile 托管键,启动时若不在本 profile 的 `.env` 里就从 `os.environ` 抹掉,
防止父进程/外部 shell 悄悄改写子进程命令行:

`hermes_cli/env_loader.py:76-83 @ 863e313`

```python
_PROFILE_MANAGED_ENV_KEYS: frozenset[str] = frozenset({
    "HERMES_ACP_AUTH_METHOD",
    "HERMES_ACP_AUTO_APPROVE",
    "HERMES_COPILOT_ACP_COMMAND",
    "HERMES_COPILOT_ACP_ARGS",
    "COPILOT_CLI_PATH",
    "COPILOT_ACP_BASE_URL",
})
```

**入方向(子进程 → Hermes),这是真正的信任边界:** 子进程可以主动向 Hermes 发请求。
Hermes 在 `initialize` 里**主动声明**自己提供文件读写能力,然后自己实现服务端:

`agent/copilot_acp_client.py:702-709 @ 863e313`

```python
        if method == "session/request_permission":
            response = _permission_denied(message_id)
        elif method == "fs/read_text_file":
            try:
                path = _ensure_path_within_cwd(str(params.get("path") or ""), cwd)
                block_error = get_read_block_error(str(path))
                if block_error:
                    raise PermissionError(block_error)
```

三条策略:

1. `session/request_permission` → **一律拒绝**,即代理想要任何额外授权都拿不到。
2. `fs/read_text_file` / `fs/write_text_file` → **自动服务,不问用户**,
   仅受三道闸:必须绝对路径且 `resolve()` 后在 session cwd 之内;
   `get_read_block_error` / `get_write_denied_error`;读出的内容强制脱敏
   `redact_sensitive_text(content, force=True)`。
3. 其他任何方法 → JSON-RPC `-32601` 拒绝。

第 1 条的实现是一个固定的"取消"应答,不是错误:

`agent/copilot_acp_client.py:125-134 @ 863e313`

```python
def _permission_denied(message_id: Any) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "result": {
            "outcome": {
                "outcome": "cancelled",
            }
        },
    }
```

第 2 条的路径闸:

`agent/copilot_acp_client.py:370-380 @ 863e313`

```python
def _ensure_path_within_cwd(path_text: str, cwd: str) -> Path:
    candidate = Path(path_text)
    if not candidate.is_absolute():
        raise PermissionError("ACP file-system paths must be absolute.")
    resolved = candidate.resolve()
    root = Path(cwd).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError(f"Path '{resolved}' is outside the session cwd '{root}'.") from exc
    return resolved
```

写侧的第二道闸是一个只在 `HERMES_WRITE_SAFE_ROOT` 被设置时才收紧的策略,
默认只挡受保护的系统/凭据文件:

`agent/file_safety.py:166-177 @ 863e313`

```python
def get_write_denied_error(path: str, *, verb: str = "Write") -> Optional[str]:
    """Return a user/model-facing error when writes to ``path`` are blocked."""
    denial = _classify_write_denial(path)
    if denial is None:
        return None
    if denial == "safe_root":
        roots_display = os.pathsep.join(sorted(get_safe_write_roots()))
        return (
            f"{verb} denied: '{path}' is outside HERMES_WRITE_SAFE_ROOT "
            f"({roots_display}). Unset the variable or add this path's directory prefix."
        )
    return f"{verb} denied: '{path}' is a protected system/credential file."
```

**要点:第 2 条完全绕开了 Hermes 的审批系统。** 搜索面 = `agent/copilot_acp_client.py`
全文的每一条 import(3 条模块级仓内 import:`agent.file_safety`、`agent.redact`、
`tools.environments.local`;2 条函数内延迟 import:`hermes_constants` 的
`apply_subprocess_home_env`、`hermes_cli._subprocess_compat` 的 `windows_hide_flags`)。
**其中没有 `tools/approval.py`,没有 `tools/registry.py`,没有任何 hook 分发。**
也就是说 Copilot 子进程在 cwd 内的读写,不产生任何审批提示、不进审批账本、
不受 `approvals.deny` 约束。

而它所依赖的那道闸,`file_safety` 自己声明**不是安全边界**:

`agent/file_safety.py:217-219 @ 863e313`

```python
    **This is NOT a security boundary.** The terminal tool runs as the
    same OS user with shell access; the agent can still ``cat auth.json``
    or ``cat ~/.hermes/.env`` and exfiltrate the file. The read-deny exists
```

综合判断:这不是一个可以直接叫"漏洞"的东西——用户主动选了
`--provider copilot-acp`,等于把 cwd 交给 Copilot;而且 `resolve()` 会解开符号链接,
cwd 外逃逸被堵住了。但**"Copilot 在你的工作目录里可以无提示读写"这件事没有写在任何文档里**,
按记号规则计一条 ◇。

### 3.6 定案

#### ■-R9C-6 · `copilot-acp` 的 api_mode 在三处声明,三处不一致(未证明可达)

三处声明:

- `hermes_cli/providers.py:92` 的 overlay:`transport="codex_responses"`
- `plugins/model-providers/copilot-acp/__init__.py:29` 的 profile:`api_mode="chat_completions"`
- `hermes_cli/runtime_provider.py:2032` 的运行时解析:硬编码 `"chat_completions"`

`hermes_cli/providers.py:91-96 @ 863e313`

```python
    "copilot-acp": HermesOverlay(
        transport="codex_responses",
        auth_type="external_process",
        base_url_override="acp://copilot",
        base_url_env_var="COPILOT_ACP_BASE_URL",
    ),
```

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

overlay 会经 `TRANSPORT_TO_API_MODE` 变成 api_mode,实测:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_HOME=/tmp/hermes-r9c-probe \
  /home/user/hermes-venv/bin/python -c \
  "from hermes_cli.providers import determine_api_mode; print('copilot-acp ->', determine_api_mode('copilot-acp'))"
```

实测输出 `copilot-acp -> codex_responses`。

**为什么这是个缺陷而不只是冗余**:`CopilotACPClient` 只有 `.chat.completions`
(§3.2 的块),没有 `.responses`。若哪条路径真的用了 `determine_api_mode` 的结果,
就会走 Responses 调用面而拿到 AttributeError。**仓库其实知道这件事**——
两处热路径都对 `copilot-acp` / `acp://copilot` / `acp+tcp://` 做了显式排除:

`agent/agent_init.py:716-722 @ 863e313`

```python
    if (
        api_mode is None
        and agent.api_mode == "chat_completions"
        and agent.provider != "copilot-acp"
        and not str(agent.base_url or "").lower().startswith("acp://copilot")
        and not str(agent.base_url or "").lower().startswith("acp+tcp://")
        and not agent._is_azure_openai_url()
```

`agent/conversation_loop.py:2354-2363 @ 863e313`

```python
                # CopilotACPClient communicates via subprocess stdio and
                # returns a plain SimpleNamespace — not an iterable
                # stream.  Mirror the ACP exclusion used for Responses
                # API upgrade (lines ~1083-1085).
                elif (
                    agent.provider in {"copilot-acp"}
                    or str(agent.base_url or "").lower().startswith("acp://copilot")
                    or str(agent.base_url or "").lower().startswith("acp+tcp://")
                ):
                    _use_streaming = False
```

**主路径当前被挡住了**:`resolve_runtime_provider` 在 copilot-acp 分支硬编码
`api_mode: "chat_completions"`,先于任何 `_fallback_api_mode` 生效:

`hermes_cli/runtime_provider.py:2028-2039 @ 863e313`

```python
    if provider == "copilot-acp":
        creds = resolve_external_process_provider_credentials(provider)
        return {
            "provider": "copilot-acp",
            "api_mode": "chat_completions",
            "base_url": creds.get("base_url", "").rstrip("/"),
            "api_key": creds.get("api_key", ""),
            "command": creds.get("command", ""),
            "args": list(creds.get("args") or []),
            "source": creds.get("source", "process"),
            "requested_provider": requested_provider,
        }
```

**我没有证明存在可达路径。** 两条候选都要求 api_mode 先被清空,
而 copilot-acp 走的解析分支不会清空它:

`hermes_cli/model_switch.py:1702-1706 @ 863e313`

```python
    _mandated_mode = host_mandated_api_mode(base_url)
    if _mandated_mode is not None:
        api_mode = _mandated_mode
    elif not api_mode:
        api_mode = determine_api_mode(target_provider, base_url)
```

`agent/agent_runtime_helpers.py:2377-2382 @ 863e313`

```python
    # ── Determine api_mode if not provided ──
    # Pass model so dual-wire providers (Nous Portal anthropic/* → Messages)
    # resolve correctly; without it determine_api_mode falls back to the
    # openai_chat overlay default.
    if not api_mode:
        api_mode = determine_api_mode(new_provider, base_url, model=new_model)
```

作为对照,`_fallback_api_mode` 的 docstring 明确把 copilot-acp 当成
"应当按声明的非 chat transport 路由"的例子——说明作者相信那个 overlay 值是对的:

`hermes_cli/runtime_provider.py:163-169 @ 863e313`

```python
    silently landed reasoning providers on ``chat_completions`` whenever the
    hostname wasn't literally recognized. That is how ``openai-api`` pointed
    at OpenAI's data-residency hosts (``us.api.openai.com``) 400'd on every
    tool-calling turn: the provider declares ``codex_responses`` but the
    declaration was never consulted. Same latent class covered the other
    non-chat overlays (MiniMax family, copilot-acp).
    """
```

**建议主线把这条当"待复核的潜在缺陷",而不是已证实的 bug。**

#### ■-R9C-7(低危)· 插件 profile 的 docstring 指向一个不存在的 api_mode 和一个不相关的文件

`plugins/model-providers/copilot-acp/__init__.py:1-6 @ 863e313`

```python
"""GitHub Copilot ACP provider profile.

copilot-acp uses an external ACP subprocess — NOT the standard
transport. api_mode="copilot_acp" is handled separately in run_agent.py.
The profile captures auth + endpoint metadata for registry migration.
"""
```

两处不成立:(a) 字符串 `copilot_acp` 作为 api_mode **全仓只出现在这条 docstring 里**
(搜索面:全仓 `*.py` + `*.md`,模式 `copilot_acp"` 与 `'copilot_acp'`,唯一命中即本行);
(b) 分派点在 `agent/agent_runtime_helpers.py:2258` 与 `agent/agent_init.py:1171`,
`run_agent.py` 里没有 copilot-acp 的客户端构造(它的 60 处 `copilot` 命中都不在这条链路上)。
**按记号规则不计 ▲**:▲ 是用来度量 README / AGENTS.md / website/docs 这张"作者自绘地图"
腐烂程度的跨轮指标,源码内 docstring 不进那个计数,故记 ■(过期注释)。

#### ◇-R9C-8 · Copilot 子进程在 session cwd 内可无提示读写,文档未述

依据见 §3.5。搜索面:`website/docs/developer-guide/acp-internals.md`(全文,`copilot` 0 命中)、
`website/docs/integrations/providers.md` 的 `### GitHub Copilot` 一节(219-241 行,
只讲 provider 选择与两个环境变量)。

#### ◎-R9C-9 · providers.md 对 copilot-acp 环境变量的列举保守

`website/docs/integrations/providers.md:235-239` 的表格只列了
`HERMES_COPILOT_ACP_COMMAND` 与 `HERMES_COPILOT_ACP_ARGS` 两个;
代码实际还认 `COPILOT_CLI_PATH`(`agent/copilot_acp_client.py:65`,见 §3.4 的块)与
`COPILOT_ACP_BASE_URL`(`hermes_cli/auth.py:268`,见 §3.2 的块)。
参考手册那张表是齐的:

`website/docs/reference/environment-variables.md:31-34 @ 863e313`

> | `HERMES_COPILOT_ACP_COMMAND` | Override Copilot ACP CLI binary path (default: `copilot`) |
> | `COPILOT_CLI_PATH` | Alias for `HERMES_COPILOT_ACP_COMMAND` |
> | `HERMES_COPILOT_ACP_ARGS` | Override Copilot ACP arguments (default: `--acp --stdio`) |
> | `COPILOT_ACP_BASE_URL` | Override Copilot ACP base URL |

所以字面无假、只是 providers.md 那张表不全,按规则记 ◎ 不记 ▲。

---

## 4. 三条路径的凭据流向与信任边界汇总

这是本片的主线红线。三条路径的信任模型差别极大:

| 路径 | 第三方代码在哪 | Hermes 给它什么 | Hermes 不给什么 | 边界靠什么守 |
|---|---|---|---|---|
| NeMo Relay | 进程内(Python wheel `nemo_relay`) | 完整请求体、全部消息、工具参数与结果、模型/provider 名 | 不发放 API key/token(三个模块 import 段无 auth 模块) | **没有边界**:同进程,且能改写请求体与请求头 |
| plugin_llm | 进程内(插件模块) | 只有结果文本、用量、provider/model 名 | 原始 OAuth token 与 API key(模块 docstring 明述) | `config.yaml` 的四个 `allow_*_override`,默认全关 |
| Copilot ACP | 独立子进程 | 全部 LLM provider 环境变量凭据 + cwd 内文件读写 | Tier-1 密钥(网关 bot token / GitHub 认证 / 远程算力)、`AUXILIARY_*`、`GATEWAY_RELAY_*` | 进程边界 + `hermes_subprocess_env` 剥离 + cwd 包含检查 + 脱敏 |

**三条结论:**

1. **"不给密钥"和"安全"不是一回事。** NeMo Relay 拿不到 key,但拿得到 key 能换来的
   全部内容,还能改写出站请求。plugin_llm 才是真正意义上的"降权":它连内容都只拿结果。
2. **唯一有真实隔离边界的是 ACP**,因为它跨进程;也正因为跨进程,它反而是三条里
   **凭据传得最多**的一条(整份 provider 密钥)。隔离与授权是两个正交维度。
3. **三条路径的授权门都在"配置/环境"层,没有一条走运行时审批。** 工具侧的
   Relay 改写是唯一一处显式安排了"改写在授权之前"的(§1.4),这是本簇最值得抄的一条。

---

## 5. 测试作行为规格

全部用 `HERMES_DISABLE_LAZY_INSTALLS=1` + `HERMES_PYTHON=/home/user/hermes-venv/bin/python`
跑 `scripts/run_tests.sh`。**环境:venv 87 个包**
(`pip list` 去表头计数,与 `site-packages/*.dist-info` 目录数一致;
`nemo_relay` / `jsonschema` / `openai` 三者均可 import,所以本片没有 skip 掉的用例)。

| 批次 | 文件 | passed | failed |
|---|---|---|---|
| relay 核心 | test_relay_llm / test_relay_tools / test_auxiliary_relay | 28 | 0 |
| plugin + ACP | test_plugin_llm / test_copilot_acp_client / test_copilot_acp_deprecation / plugins/test_nemo_relay_plugin | 51 | 0 |
| relay 运行时 + e2e | hermes_cli/test_relay_shared_metrics_runtime / test_relay_shared_metrics / e2e/test_relay_native_anthropic_stream | 151 | 0 |
| **合计** | **10 个文件** | **230** | **0** |

**0 failed,因此没有需要归因的失败**(容器的 6 条已知必然失败用例都不在本片范围内)。

最有规格价值的三个用例:

**(a) 无消费者时必须完全绕开 Relay** —— §1.6 已全文引用
`tests/agent/test_relay_tools.py:39-62`,是 ▲-R9C-1 的直接反证。

**(b) `_jsonable` 不得触发动态属性** —— 这正是 ■-R9C-3 里"只修了一半"的那一半,
用例只钉在 relay_llm 侧:

`tests/agent/test_relay_llm.py:191-199 @ 863e313`

```python
def test_jsonable_does_not_probe_dynamic_attributes():
    class DynamicProviderObject:
        def __getattr__(self, name):
            raise AssertionError(f"unexpected dynamic attribute lookup: {name}")

        def __str__(self):
            return "opaque-provider-object"

    assert relay_llm._jsonable(DynamicProviderObject()) == "opaque-provider-object"
```

把同一个对象喂给 `relay_tools._jsonable` 会走 `getattr(value, "model_dump", None)`
→ 触发 `__getattr__` → 抛 AssertionError,即两份实现在这个用例下行为不同。
(这是**代码推演,不是实测**——我没有为 relay_tools 侧写并运行对照用例。)

**(c) ACP 入方向两道闸** —— 读侧脱敏与写侧根目录约束各一条:

`tests/agent/test_copilot_acp_client.py:74-78 @ 863e313`

```python
    def test_read_text_file_redacts_sensitive_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            secret_file = root / "config.env"
            secret_file.write_text("OPENAI_API_KEY=sk-proj-abc123def456ghi789jkl012")
```

写侧的对应用例是 `tests/agent/test_copilot_acp_client.py:138`
`test_write_text_file_respects_safe_root`。

`tests/agent/test_copilot_acp_deprecation.py` 是一整个文件在测一件小事:
如何从 stderr 里区分**已废弃的 `gh copilot` 扩展**与**新的 `@github/copilot` CLI**。
判据是"必须同时命中产品名 `gh-copilot` 和一个废弃标记词",因为新 CLI 的横幅里
也会出现 `copilot-cli` 字样。这是"错误信息即产品"的好例子——认错了就会给用户
一条把他引向错误安装命令的提示。

基线在全部测试跑完后 `git status --porcelain` 为空(已确认两次)。

---

## 6. 发现清单(按严重性排序)

锚点与摘录同格,便于脚本校验;详述见对应小节。

| 记号 | 锚点 · 摘录 | 一句话现象 |
|---|---|---|
| ■-R9C-4 | `agent/plugin_llm.py:948` → `merged_extra.setdefault("metadata", {})["auth_profile"] = profile_override` | 该键全仓无读者,`allow_profile_override` 是空开关,且 profile 名被塞进请求体发给 provider(§2.5) |
| ■-R9C-5 | `agent/plugin_llm.py:329` → `return final_provider, final_model, requested_agent_id, final_profile` | 被门控的 agent id 只写进结果对象,不进任何调用参数,开了也不会跨 agent(§2.5) |
| ▲-R9C-1 | `plugins/observability/nemo_relay/README.md:171` → `Hermes core routes provider and tool execution through NeMo Relay managed APIs` | 与代码相反:默认无消费者时 LLM/工具执行完全绕开 Relay,无条件的是会话/轮次作用域(§1.6) |
| ■-R9C-6 | `hermes_cli/providers.py:92` → `transport="codex_responses",` | 与同一 provider 另两处声明冲突,而 ACP 客户端没有 `.responses` 面;**未证明可达**(§3.6) |
| ◇-R9C-8 | `agent/copilot_acp_client.py:704` → `elif method == "fs/read_text_file":` | fs 分支绕开 Hermes 审批系统,Copilot 子进程在 cwd 内可无提示读写,文档未述(§3.5) |
| ■-R9C-3 | `agent/relay_tools.py:93` → `model_dump = getattr(value, "model_dump", None)` | 与 relay_llm 版 `_jsonable` 语义分叉,且不过滤 `_` 私有属性,同一个 bug 只修了一半(§1.6) |
| ◇-R9C-2 | `agent/relay_llm.py:1010` → `final["extra_headers"] = {` | Relay 可改写任意出站请求头(含 Authorization),website/docs 无 NeMo Relay 机制页(§1.6) |
| ■-R9C-7 | `plugins/model-providers/copilot-acp/__init__.py:4` → `api_mode="copilot_acp" is handled separately in run_agent.py.` | 该 api_mode 字符串全仓只存在于这条注释,分派点也不在 run_agent.py(§3.6) |
| ◎-R9C-9 | `website/docs/integrations/providers.md:238` → `HERMES_COPILOT_ACP_COMMAND` | 该环境变量表只列两个键,漏掉同样生效的 `COPILOT_CLI_PATH` 与 `COPILOT_ACP_BASE_URL`(§3.6) |

**最值得主线实跑复核的两条**:

1. **■-R9C-4**(`agent/plugin_llm.py:948`)。复核成本极低(一次 grep 即可),
   影响是一条**被文档承诺、被信任门守卫、但完全没接线**的授权能力,
   且顺带把用户的 profile 名发给第三方。它同时是"负结论"的正面样本:
   我把搜索面写全了,主线可以直接重跑那条 grep 判定我是否漏搜。
2. **▲-R9C-1**(`plugins/observability/nemo_relay/README.md:171`)。复核办法是
   跑 `tests/agent/test_relay_tools.py` 那个 bypass 用例 + 数
   `retain_managed_execution` 的调用点。它决定了"启用观测插件"这件事的默认语义,
   是读这套 relay 代码时最容易被文档带偏的一处。

---

## 7. 我未取证 / 属于推定的部分

1. **NeMo Relay wheel 内部行为全部是推定。** `nemo_relay` 是外部包,本片只读了
   Hermes 侧的调用面。"codec 会洗掉 provider 私有字段""`request_intercepts` 能改参数"
   这些结论来自 Hermes 侧代码的注释与防御性写法(§1.3 的差分覆盖),
   **我没有反编译或阅读 wheel 源码去确认**。
2. **■-R9C-6 的可达性未证明。** 我只证明了 `determine_api_mode("copilot-acp")`
   返回 `codex_responses`,以及 ACP 客户端没有 `.responses`。中间"是否存在一条
   把这个返回值真正用到 ACP agent 上的路径"没有跑通,见 §3.6 的说明。
3. **ACP 未真跑。** 容器里没有 `copilot` CLI,本片没有实际起过 ACP 子进程;
   握手序列、`session/update` 的 chunk 形状、`fs/*` 的实际触发都只来自代码与用例。
   `acp+tcp://` 这个第二 scheme 在 `hermes_cli/auth.py:7248` 被特判为"无需本地二进制",
   但 `CopilotACPClient` 只实现了 stdio spawn——**我没有找到 TCP 变体的实现**,
   也没有把这条写成结论(可能在 Copilot CLI 侧,也可能是未完工路径)。
4. **plugin_llm 的 `extra_body` 泄露路径只追到 `_build_call_kwargs`。**
   我确认了 `merged_extra` 会写进 `kwargs["extra_body"]`
   (`agent/auxiliary_client.py:8043-8044`),**没有**逐 provider 确认每条
   wire(Anthropic Messages / Responses / Bedrock)都会把它序列化进请求体——
   OpenAI Chat 一条是确定的。
5. **本片没有覆盖 `agent/monitoring/`。** 它的模块 docstring 把轨迹捕获显式划给了
   本簇,是相邻但未读的一块:

`agent/monitoring/__init__.py:12-14 @ 863e313`

```python
Deliberately out of scope here: run/model/tool trajectory capture, usage
analytics, and any content-bearing signal. Those planes are served by the
NeMo Relay integration and its Hermes-owned subscribers.
```
6. **`_reset_for_tests` / `_reset_active_turns_for_tests` 之外的并发正确性未验证。**
   `RelayTurnContext` 的 `finalize_lock` / `logical_llm_lock` 嵌套顺序看起来一致
   (总是 finalize 外、logical 内),但我没有做穷举检查,也没有跑并发压力用例。

---

## 8. 自校验读数

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent \
    notes/r9c-raw-relay-and-plugin-llm.md
```

实测读数(退出码 0):

```console
citations=98  OK=78  UNCHECKED=20
可校验比例 OK/98 = 79.6%
table_anchors=9  OK=9   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
OK: every code-block-backed citation matches the baseline
```

| 项 | 值 |
|---|---|
| citations | 98 |
| OK | 78 |
| UNCHECKED | 20 |
| 可校验比例 | 79.6%(≥ 70% 下限) |
| 表格行内锚点 | 9,全部 OK |
| MISMATCH | 0 |
| BLOCK-DRIFT | 0 |
| TABLE-DRIFT | 0 |
| TABLE-OUT-OF-RANGE | 0 |
| MISSING-FILE | 0 |
| 退出码 | 0 |

20 条 UNCHECKED 全部是**散文区域指路**(重复引用某处已带块的锚点、或指向
某个测试/函数名让读者自己去看),不是"块写在锚点之后"的排版问题——
脚本的「疑似锚点排版不合规」提示未触发。

**本底稿全部代码块由脚本从基线逐行抽取生成,不是手抄**,
以杜绝 CLAUDE.md 里点名的 BLOCK-DRIFT 那一类"手抄时抄漏半行"。
