# r9c 底稿 · Codex 传输族 —— 把 OpenAI Codex 接成一个模型后端的两条路

> 本篇是 R9C-A 片的证据层底稿,面向"要凭它重实现同等机制的自己"。
> 溯源约定:凡对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` 单独成行、置于代码块之前;
> 围栏块为基线逐字摘录,`>` 引用块为文档摘录,```verify 块为可重跑的自检命令。

## 0. 覆盖范围与方法

本片精读 4 个文件,合计 2,696 行:

| 文件 | 行数 | 一句话职责 |
|---|---|---|
| `agent/transports/codex_app_server_session.py` | 1292 | 会话适配器:一个 Hermes 会话 = 一条 Codex thread,驱动 turn、投影事件、桥接审批、翻译取消 |
| `agent/transports/codex.py` | 672 | `api_mode="codex_responses"` 的 transport:只管请求体构造与响应归一化 |
| `agent/transports/codex_app_server.py` | 418 | 线级 JSON-RPC 2.0 over stdio 客户端 + `codex` 二进制版本门 |
| `agent/transports/codex_event_projector.py` | 314 | 把 Codex 的 `item/*` 事件投影成 OpenAI 形状的 `{role, content, tool_calls}` 消息 |

方法:先读四个文件全文,再顺着调用方(`agent/codex_runtime.py`、`agent/conversation_loop.py`、
`hermes_cli/runtime_provider.py`、`run_agent.py`)确认每个机制的真实入口,最后跑 19 个相关测试文件
作行为规格,并对可疑处写最小复现。`agent/transports/base.py` 与 `types.py` 只作契约参照(归 B 片),
不在本篇做逐文件精读。

基线只读,全程未改动;测试跑完后 `git -C /home/user/hermes-agent status --porcelain` 为空。

---

## 1. 全景:同一个 "OpenAI 模型",两条完全不同的接法

### 1.1 问题是什么

Hermes 想接 OpenAI 的 Codex,面对的其实是**两个不同的产品形态**:

1. **Responses API**——一个 HTTP 端点(`/v1/responses`)。Hermes 自己拥有 agent 循环:
   自己发系统提示、自己列工具、自己收 `tool_calls`、自己执行工具、自己把结果拼回去再发一轮。
   Codex 只是"一个会调用函数的模型"。
2. **Codex CLI 的 app-server**——一个本地子进程(`codex app-server`),它**自己就是一个 agent**:
   有自己的 shell / apply_patch / 沙箱 / 计划器 / MCP 客户端。Hermes 把整个 turn 交给它,
   自己退化成一个壳(会话库、斜杠命令、网关、记忆与技能复盘)。

这两条路的**边界完全不同**,所以代码里是两套东西,只是共用一个 "codex" 名字前缀:

```text
                     用户一次提问
                          │
            ┌─────────────┴──────────────┐
            │ api_mode == ?              │
            ▼                            ▼
   "codex_responses"              "codex_app_server"
   ─────────────────              ──────────────────
   ResponsesApiTransport          CodexAppServerSession
   (agent/transports/codex.py)    (…/codex_app_server_session.py)
        │ 只造 kwargs / 归一化响应        │ 驱动整个 turn
        │                                 ├─ CodexAppServerClient  (…/codex_app_server.py)
        │                                 │    JSON-RPC 2.0 / NDJSON / stdio
        ▼                                 └─ CodexEventProjector    (…/codex_event_projector.py)
   HTTP POST /v1/responses                     item/* → {role,content,tool_calls}
   (流式/重试/取消由 Hermes 主循环拥有)         │
                                                ▼
                                        codex app-server 子进程
                                        (自己的 shell/沙箱/MCP/插件)
```

### 1.2 两条路径怎么选

选择发生在 CLI 的运行时解析层,不在 transport 层。`api_mode` 先按 provider / base_url / 模型名
推导出 `codex_responses` 或 `chat_completions`,**然后**再被一个显式开关改写成 `codex_app_server`:

`hermes_cli/runtime_provider.py:419-442 @ 863e313`

```python
def _maybe_apply_codex_app_server_runtime(
    *,
    provider: str,
    api_mode: str,
    model_cfg: Optional[Dict[str, Any]],
) -> str:
    """Optional opt-in: rewrite api_mode → "codex_app_server" for OpenAI/Codex
    providers when the user has explicitly enabled that runtime via
    `model.openai_runtime: codex_app_server` in config.yaml.

    Default behavior is preserved: when the key is unset, "auto", or empty,
    this function is a no-op. Only providers in {"openai", "openai-codex"}
    are eligible — other providers (anthropic, openrouter, etc.) cannot be
    rerouted through codex.

    Returns the (possibly-rewritten) api_mode."""
    if not model_cfg:
        return api_mode
    if provider not in {"openai", "openai-codex"}:
        return api_mode
    runtime = str(model_cfg.get("openai_runtime") or "").strip().lower()
    if runtime == "codex_app_server":
        return "codex_app_server"
    return api_mode
```

三点值得注意:

- **只允许收窄,不允许扩散**:仅 `provider ∈ {openai, openai-codex}` 可被改写;
  其它 provider(anthropic / openrouter / …)即使写了这个键也是 no-op。
- **默认完全惰性**:键不存在、为空、为 `auto` 时函数原样返回,默认行为一字不变。
- **`codex_app_server` 是 `_VALID_API_MODES` 的成员**,所以它同样能从
  `model.api_mode` 直接持久化——这一点后面 §2.8 会引出一个版本门的洞。

而 `codex_responses` 这一侧的 transport 是**注册制**的,模块导入即自注册:

`agent/transports/codex.py:669-672 @ 863e313`

```python
# Auto-register on import
from agent.transports import register_transport  # noqa: E402

register_transport("codex_responses", ResponsesApiTransport)
```

对应地,`codex_app_server` **没有** transport 注册项——它不走 `get_transport()`,
而是在 `agent/conversation_loop.py` 里被一条 `if agent.api_mode == "codex_app_server"` 早返回
劫持到 `agent/codex_runtime.run_codex_app_server_turn()`。这是理解全篇的关键分界:
**`codex.py` 是一个 transport,`codex_app_server_session.py` 是一个 runtime。**

---

## 2. `codex_app_server.py` —— 线级 JSON-RPC 客户端

### 2.1 协议是什么

模块开头就把协议讲完了,这是全篇最省事的一段文档:

`agent/transports/codex_app_server.py:1-15 @ 863e313`

```python
"""Codex app-server JSON-RPC client.

Speaks the protocol documented in codex-rs/app-server/README.md (codex 0.125+).
Transport is newline-delimited JSON-RPC 2.0 over stdio: spawn `codex app-server`,
do an `initialize` handshake, then drive `thread/start` + `turn/start` and
consume streaming `item/*` notifications until `turn/completed`.

This module is the wire-level speaker only. Higher-level concerns (event
projection into Hermes' display, approval bridging, transcript projection into
AIAgent.messages, plugin migration) live in sibling modules.

Status: optional opt-in runtime gated behind `model.openai_runtime ==
"codex_app_server"`. Hermes' default tool dispatch is unchanged when this
runtime is not selected.
"""
```

拆开说:

- **传输**:换行分隔的 JSON-RPC 2.0(NDJSON over stdio)。每行一个完整 JSON 对象。
  没有 Content-Length 头(和 LSP 不同),所以解析器就是 `readline` + `json.loads`。
- **握手**:`initialize` 请求 + `initialized` 通知(和 LSP 同款两步)。
- **会话**:`thread/start` 开一条 thread(≈ 一次对话),`turn/start` 开一个 turn(≈ 一次提问)。
- **流式**:turn 期间服务端持续推 `item/*` 通知(`item/started`、`item/completed`、
  各类 `outputDelta`),直到 `turn/completed`。
- **反向请求**:服务端会**主动发请求**给客户端(审批),客户端必须回 `result` 或 `error`。
  这是 JSON-RPC 双向性的实际用途,也是这个客户端必须区分三种入站帧的原因。

### 2.2 为什么是同步 + 线程,而不是 asyncio

`agent/transports/codex_app_server.py:57-67 @ 863e313`

```python
    Threading model:
      - Spawning thread (caller) drives request/response pairs synchronously.
      - One reader thread parses stdout, dispatches replies to the right
        pending future, and routes notifications + server-initiated requests
        to bounded queues that the caller drains on their own cadence.
      - One reader thread captures stderr for diagnostics; codex emits
        tracing logs there at RUST_LOG-controlled levels.

    Intentionally NOT async. AIAgent.run_conversation() is synchronous and
    runs on the main thread; layering asyncio just to drive a stdio child
    creates surprising interrupt semantics. We use blocking queues with
```

设计取舍很清楚:`AIAgent.run_conversation()` 是同步的、跑在主线程上;为了驱动一个 stdio 子进程
而把整条链路 async 化,会让中断语义变得难以预测(`KeyboardInterrupt` 落在哪个 task 上、
取消传播到哪一层)。代价是必须自己管两条 reader 线程和三个队列;收益是调用方仍然是一个
"发出去 → 阻塞等 → 拿到结果"的普通函数。

**这段 docstring 里有一处与实现不符**:它说通知与服务端请求进的是 "bounded queues"(有界队列),
而实际构造的是**无界** `queue.Queue()`:

`agent/transports/codex_app_server.py:143-156 @ 863e313`

```python
        self._next_id = 1
        self._pending: dict[int, _Pending] = {}
        self._pending_lock = threading.Lock()
        self._notifications: queue.Queue = queue.Queue()
        self._server_requests: queue.Queue = queue.Queue()
        self._stderr_lines: list[str] = []
        self._stderr_lock = threading.Lock()
        self._closed = False
        self._initialized = False

        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_reader.start()
```

对照同一个类里 stderr 的处理——那里是**真的**做了界:

`agent/transports/codex_app_server.py:369-371 @ 863e313`

```python
                    # Bound memory: keep last 500 lines.
                    if len(self._stderr_lines) > 500:
                        self._stderr_lines = self._stderr_lines[-500:]
```

后果:如果 codex 高速推 `outputDelta` 而消费侧(`run_turn` 的轮询循环)因为一次审批阻塞在
用户输入上,通知会在内存里无限堆积。`_Pending.queue` 才是唯一真正有界的队列(`maxsize=1`)。
这是本文件的 ■-3(见 §8)。

### 2.3 子进程环境:一次真实的收敛

`agent/transports/codex_app_server.py:79-94 @ 863e313`

```python
        # codex app-server is a model-driving CLI executor: it runs a
        # model-chosen agentic loop that executes shell commands, so it
        # legitimately needs LLM provider credentials (inherit_credentials=True)
        # to authenticate against the model endpoint. But the previous
        # `os.environ.copy()` also handed it every Tier-1 Hermes secret — gateway
        # bot tokens, GitHub auth, Modal/Daytona infra tokens, the dashboard
        # session token, AUXILIARY_* side-LLM keys, GATEWAY_RELAY_* auth — none
        # of which a coding subprocess has any use for. Route through the
        # centralized helper so Tier-1 + dynamic-internal secrets are always
        # stripped while provider creds still flow, matching copilot_acp_client
        # (#29157 sibling spawn-site gap).
        spawn_env = hermes_subprocess_env(inherit_credentials=True)
        if env:
            spawn_env.update(env)
        if codex_home:
            spawn_env["CODEX_HOME"] = codex_home
```

这段注释本身就是一个可迁移的设计教训:**"model-driving CLI 需要 provider 凭据"不等于
"它需要你所有的密钥"**。原先的 `os.environ.copy()` 把网关 bot token、GitHub 认证、
Modal/Daytona 基建 token、看板会话 token、`AUXILIARY_*` 侧 LLM key、`GATEWAY_RELAY_*`
全都交给了一个会执行任意 shell 命令的子进程。修法是走集中式的
`hermes_subprocess_env(inherit_credentials=True)`:Tier-1 与内部动态密钥永远剥离,
provider 凭据按开关放行。`inherit_credentials=True` 本身被设计成 grep 得到的审计锚点。

### 2.4 Kanban 沙箱开洞

`agent/transports/codex_app_server.py:96-124 @ 863e313`

```python
        app_server_args = list(extra_args or [])
        # Kanban workers must be able to write their handoff/status back to
        # the board DB, which lives outside the per-task workspace. Keep the
        # Codex sandbox on, but add the Kanban root as the only extra writable
        # root. Without this, codex-runtime workers finish their actual work
        # but crash/block when kanban_complete/kanban_block writes SQLite.
        if spawn_env.get("HERMES_KANBAN_TASK"):
            kanban_db = spawn_env.get("HERMES_KANBAN_DB")
            kanban_root = (
                os.path.dirname(kanban_db)
                if kanban_db
                else spawn_env.get(
                    "HERMES_KANBAN_ROOT",
                    os.path.join(
                        spawn_env.get("HERMES_HOME", os.path.expanduser("~/.hermes")),
                        "kanban",
                    ),
                )
            )
            app_server_args.extend(
                [
                    "-c",
                    'sandbox_mode="workspace-write"',
                    "-c",
                    f'sandbox_workspace_write.writable_roots=["{kanban_root}"]',
                    "-c",
                    "sandbox_workspace_write.network_access=false",
                ]
            )
```

问题场景:看板(Kanban)worker 在 codex 沙箱里干活,活干完了要把 handoff/status 写回
board 的 SQLite,而那个库在 per-task 工作区**外面**。不开洞的话 worker 能完成实际工作、
却在 `kanban_complete` 写库时崩住。做法是保持 `workspace-write` 沙箱不变,只把看板根目录
加成额外可写根,并显式关掉网络。走的是 codex 自己的 `-c key=value` 命令行覆盖,
不去改用户的 `~/.codex/config.toml`。

这里有一处**文档与代码矛盾**(▲-2,详见 §8):文档声称加进去的是"board DB 目录 **加上
dispatcher 钉住的每一个 Kanban 路径**",而代码只加了**一个**根。

### 2.5 四种帧的分派

`agent/transports/codex_app_server.py:339-356 @ 863e313`

```python
    def _dispatch(self, msg: dict) -> None:
        # Reply (has id + result/error, no method)
        if "id" in msg and ("result" in msg or "error" in msg):
            with self._pending_lock:
                pending = self._pending.pop(msg["id"], None)
            if pending is not None:
                try:
                    pending.queue.put_nowait(msg)
                except queue.Full:  # pragma: no cover - defensive
                    pass
            return
        # Server-initiated request (has id + method)
        if "id" in msg and "method" in msg:
            self._server_requests.put(msg)
            return
        # Notification (no id)
        if "method" in msg:
            self._notifications.put(msg)
```

分派规则是纯结构判定,不看 method 名:

| 入站帧 | 判据 | 去向 |
|---|---|---|
| 响应 | 有 `id`,且有 `result` 或 `error` | 按 id 找 `_pending`,塞进那个 `maxsize=1` 队列 |
| 服务端请求 | 有 `id` 且有 `method` | `_server_requests` 队列 |
| 通知 | 无 `id`,有 `method` | `_notifications` 队列 |
| 其它 | —— | 静默丢弃(没有 else 分支) |

值得学的一点:stdout 上出现**非 JSON** 行时不抛异常、也不静默吞掉,而是塞进 stderr 诊断缓冲:

`agent/transports/codex_app_server.py:318-334 @ 863e313`

```python
            for line in iter(self._proc.stdout.readline, b""):
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    # Non-JSON output is unexpected on stdout; tracing belongs
                    # on stderr. Surface it via stderr buffer for diagnostics.
                    with self._stderr_lock:
                        self._stderr_lines.append(
                            f"<non-json on stdout> {line[:200]!r}"
                        )
                    continue
                self._dispatch(msg)
```

理由写在注释里:tracing 本该走 stderr,stdout 上的非 JSON 是**协议异常**,
但它不该让整条 reader 线程死掉——它该变成一条用户能看到的诊断线索。

### 2.6 请求/超时/错误

`agent/transports/codex_app_server.py:213-241 @ 863e313`

```python
    def request(
        self,
        method: str,
        params: Optional[dict] = None,
        timeout: float = 30.0,
    ) -> dict:
        """Send a JSON-RPC request and block on the response. Returns `result`,
        raises CodexAppServerError on `error`."""
        rid = self._take_id()
        q: queue.Queue = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[rid] = _Pending(queue=q, method=method)
        self._send({"id": rid, "method": method, "params": params or {}})
        try:
            msg = q.get(timeout=timeout)
        except queue.Empty:
            with self._pending_lock:
                self._pending.pop(rid, None)
            raise TimeoutError(
                f"codex app-server method {method!r} timed out after {timeout}s"
            )
        if "error" in msg:
            err = msg["error"]
            raise CodexAppServerError(
                code=err.get("code", -1),
                message=err.get("message", ""),
                data=err.get("data"),
            )
        return msg.get("result", {})
```

要点:

- 超时是**每次调用一个数**,不是全局。超时后**主动把 `_pending` 条目摘掉**,
  这样迟到的响应到达时 `_dispatch` 找不到 pending 就直接丢弃,不会污染下一次调用。
- JSON-RPC 的 `error` 被翻译成 `CodexAppServerError`(带 code / message / data),
  与 `TimeoutError` 分成两类——上层的 `run_turn` 正是靠这两类的区分做不同的退化处理。
- `CodexAppServerError` 是一个 `@dataclass` 且继承 `RuntimeError`,所以既能 `raise`
  又能当结构化数据读字段。

### 2.7 关闭:先温柔后强硬

`agent/transports/codex_app_server.py:185-203 @ 863e313`

```python
    def close(self, timeout: float = 3.0) -> None:
        """Close stdin and wait for the subprocess to exit, escalating to kill."""
        if self._closed:
            return
        self._closed = True
        try:
            if self._proc.stdin and not self._proc.stdin.closed:
                self._proc.stdin.close()
        except Exception:
            pass
        try:
            self._proc.terminate()
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                self._proc.kill()
                self._proc.wait(timeout=1.0)
            except Exception:
                pass
```

三级:关 stdin(让 codex 自己看到 EOF 退出)→ `terminate()` 等 `timeout` 秒 →
`kill()` 再等 1 秒。两条 reader 线程是 daemon,不参与 join。

### 2.8 版本门:存在,但不在运行时路径上

`agent/transports/codex_app_server.py:387-392 @ 863e313`

```python
def check_codex_binary(
    codex_bin: str = "codex", min_version: tuple[int, int, int] = MIN_CODEX_VERSION
) -> tuple[bool, str]:
    """Verify codex CLI is installed and meets minimum version.

    Returns (ok, message). Used by setup wizard and runtime startup."""
```

docstring 说 "Used by setup wizard and **runtime startup**"。但全仓只有一个调用方:

```verify
cd /home/user/hermes-agent && grep -rnI --exclude-dir=.git --exclude-dir=__pycache__ \
    "check_codex_binary" .
```

搜索面:仓库根下**全部文本文件**(不加 `--include`;`-I` 跳过二进制,
`--exclude-dir` 只剔 `.git/` 与 `__pycache__/`,不剔任何源码目录),模式为字面量
`check_codex_binary`。结果只有:定义处(`codex_app_server.py:387`)、
`hermes_cli/codex_runtime_switch.py` 的包装 `check_codex_binary_ok` 及其唯一调用点、以及测试。
`CodexAppServerSession.ensure_started()` / `CodexAppServerClient.__init__` 里**没有**任何版本检查
(见 §4.2 摘录)。

也就是说版本门只在 `/codex-runtime` 这条**切换命令**上生效。而文档明确告诉用户可以绕过它:

`website/docs/user-guide/features/codex-app-server-runtime.md:194 @ 863e313`

> You can also set it manually in `~/.hermes/config.yaml`:

手改 config.yaml 的用户、或者装完之后把 codex 降级/卸载的用户,拿到的不是那句
"Run: npm i -g @openai/codex",而是一个 `FileNotFoundError` 从 `subprocess.Popen` 里抛出来
(`ensure_started` 只捕获 `CodexAppServerError` 与 `TimeoutError`,见 §4.6),
最终由 `codex_runtime.py` 的宽 `except Exception` 兜成一句
"Codex app-server turn failed: …"。这是 ■-4。

顺带:`MIN_CODEX_VERSION = (0, 125, 0)`,而文档写的是 0.130.0 或更新:

`website/docs/user-guide/features/codex-app-server-runtime.md:155 @ 863e313`

>    codex --version   # 0.130.0 or newer

文档比代码**更严**——不构成矛盾(◎-1),但两处数字来源不同,任何一方改动都不会惊动另一方。

---

## 3. `codex_event_projector.py` —— 把别人的 agent 事件流翻译回自家消息形状

### 3.1 解决什么问题

Hermes 的自我改进回路(记忆复盘、技能提示)读的是标准 OpenAI 形状的消息数组:
`{role, content, tool_calls, tool_call_id}`。app-server runtime 下这套消息**根本不存在**——
真正发生的事是 codex 内部的 `item/*` 事件。投影器就是这两个世界之间的翻译器。

`agent/transports/codex_event_projector.py:1-27 @ 863e313`

```python
"""Projects codex app-server events into Hermes' messages list.

The translator that lets Hermes' memory/skill review keep working under the
Codex runtime: it converts Codex `item/*` notifications into the standard
OpenAI-shaped `{role, content, tool_calls, tool_call_id}` entries that
`agent/curator.py` already knows how to read.

Codex emits items with a discriminator field `type`:
  - userMessage         → {role: "user", content}
  - agentMessage        → {role: "assistant", content}
  - reasoning           → stashed in the assistant's "reasoning" field
  - commandExecution    → assistant tool_call(name="exec") + tool result
  - fileChange          → assistant tool_call(name="apply_patch") + tool result
  - mcpToolCall         → assistant tool_call(name=f"mcp.{server}.{tool}") + tool result
  - dynamicToolCall     → assistant tool_call(name=tool) + tool result
  - plan/hookPrompt/collabAgentToolCall → recorded as opaque assistant notes

Each item maps to AT MOST one assistant entry + one tool entry, preserving
Hermes' message-alternation invariants (system → user → assistant → user/tool
→ assistant → ...). Multiple Codex tool calls within one Codex turn produce
multiple consecutive (assistant, tool) pairs, which is the same shape Hermes
already produces for parallel tool calls.

Counters tracked alongside projection:
  - tool_iterations: ticks once per completed tool-shaped item. Used by
    AIAgent._iters_since_skill (skill nudge gate, default threshold 10).
"""
```

**核心不变量**:每个 item 至多产生"一条 assistant + 一条 tool",从而保住 Hermes 的
消息交替不变式(system → user → assistant → user/tool → assistant → …)。
多个工具调用产生多组连续的 (assistant, tool) 对——这恰好和 Hermes 自己处理并行工具调用时
产出的形状一致,所以下游一行代码都不用改。

### 3.2 只在 `item/completed` 物化

`agent/transports/codex_event_projector.py:78-89 @ 863e313`

```python
    def project(self, notification: dict) -> ProjectionResult:
        """Project a single notification. Idempotent for non-completion events;
        only `item/completed` and `turn/completed` materialize messages."""
        method = notification.get("method", "")
        params = notification.get("params", {}) or {}

        # We only materialize messages on `item/completed`. Streaming deltas
        # (`item/<type>/outputDelta`, `item/<type>/delta`) are display-only and
        # don't enter the messages list — same way Hermes already only writes
        # the assistant message after the streaming completion event.
        if method != "item/completed":
            return ProjectionResult()
```

`item/started`、各类 `outputDelta` 一律返回空 `ProjectionResult()`。这条规则把"显示"和"历史"
彻底分开:流式增量只喂给显示层(见 §4.8 的 `on_event` 桥),消息数组只在 item 完成时增长。
和 Hermes 自己的流式路径同构——那边也是"流完了才写 assistant 消息"。

分派本体是一串 `if item_type == ...`:

`agent/transports/codex_event_projector.py:91-115 @ 863e313`

```python
        item = params.get("item") or {}
        item_type = item.get("type") or ""
        item_id = item.get("id") or ""

        if item_type == "agentMessage":
            return self._project_agent_message(item)
        if item_type == "reasoning":
            self._pending_reasoning.extend(item.get("summary") or [])
            self._pending_reasoning.extend(item.get("content") or [])
            return ProjectionResult()
        if item_type == "commandExecution":
            return self._project_command(item, item_id)
        if item_type == "fileChange":
            return self._project_file_change(item, item_id)
        if item_type == "mcpToolCall":
            return self._project_mcp_tool_call(item, item_id)
        if item_type == "dynamicToolCall":
            return self._project_dynamic_tool_call(item, item_id)
        if item_type == "userMessage":
            return self._project_user_message(item)

        # Unknown / rare items (plan, hookPrompt, collabAgentToolCall, etc.)
        # — record as opaque assistant note so memory review can still see
        # *something* happened, but don't fabricate tool_call structure.
        return self._project_opaque(item, item_type)
```

### 3.3 确定性 call_id

`agent/transports/codex_event_projector.py:37-47 @ 863e313`

```python
def _deterministic_call_id(item_type: str, item_id: str) -> str:
    """Stable id for tool_call message correlation.

    Uses the codex item id directly when present (already a uuid); falls back
    to a content hash so replay produces the same id across sessions and
    prefix caches stay valid. See AGENTS.md Pitfall #16 (deterministic IDs in
    tool call history)."""
    if item_id:
        return f"codex_{item_type}_{item_id}"
    digest = hashlib.sha256(f"{item_type}".encode()).hexdigest()[:16]
    return f"codex_{item_type}_{digest}"
```

为什么必须确定性:这些 id 会进消息历史,而消息历史是 **prompt 前缀缓存**的一部分。
一个 `uuid4()` 会让同一段历史在每次会话重放时产生不同的字节,前缀缓存全部作废。
仓库把这条抬到了硬不变量的高度——`agent/message_sanitization.py` 的注释专门说明
投影器这套 id 方案**故意不与** chat 侧的 `deterministic_call_id` 合并,因为合并会改 id、
从而作废已有缓存。

### 3.4 逐类型投影:以 `commandExecution` 为样板

`agent/transports/codex_event_projector.py:142-149 @ 863e313`

```python
    def _project_command(self, item: dict, item_id: str) -> ProjectionResult:
        call_id = _deterministic_call_id("exec", item_id)
        args = {
            "command": item.get("command") or "",
            "cwd": item.get("cwd") or "",
        }
        assistant_msg = {
            "role": "assistant",
```

工具名被固定成 `exec_command`,参数被压成 `{command, cwd}` 的 JSON。
结果侧则把非零退出码前置成人类可读的标记:

`agent/transports/codex_event_projector.py:162-176 @ 863e313`

```python
        if self._pending_reasoning:
            assistant_msg["reasoning"] = "\n".join(self._pending_reasoning)
            self._pending_reasoning = []
        output = item.get("aggregatedOutput") or ""
        exit_code = item.get("exitCode")
        if exit_code is not None and exit_code != 0:
            output = f"[exit {exit_code}]\n{output}"
        tool_msg = {
            "role": "tool",
            "tool_call_id": call_id,
            "content": output,
        }
        return ProjectionResult(
            messages=[assistant_msg, tool_msg], is_tool_iteration=True
        )
```

`fileChange` 同理,但**故意不内联文件内容**——只留 `{kind, path}` 摘要,
因为 patch 正文可以非常大,而这条消息是要长期留在历史里、反复进 prompt 的。

MCP 调用这里有一个容易看漏的细节:**call_id 的输入用 `mcp__server__tool`,
而对外暴露的工具名用 `mcp.server.tool`**:

`agent/transports/codex_event_projector.py:217-222 @ 863e313`

```python
    def _project_mcp_tool_call(self, item: dict, item_id: str) -> ProjectionResult:
        server = item.get("server") or "mcp"
        tool = item.get("tool") or "unknown"
        # Mirror the native MCP tool-name convention (mcp__server__tool) so the
        # deterministic call_id input stays consistent with registration names.
        call_id = _deterministic_call_id(f"mcp__{server}__{tool}", item_id)
```

`agent/transports/codex_event_projector.py:226-238 @ 863e313`

```python
        assistant_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": f"mcp.{server}.{tool}",
                        "arguments": _format_tool_args(args),
                    },
                }
            ],
```

前者对齐 Hermes 原生 MCP 工具的注册名(所以 id 生成的输入与注册名一致),
后者是给人看的显示名。两套命名共存是有意的,但它是本文件最容易在重构中被"统一"掉的地方。

### 3.5 reasoning 的暂存语义

Codex 把推理作为**独立的 item** 发出来,而 Hermes 把 reasoning 挂在 assistant 消息上。
投影器的做法是:reasoning item 只累积、不产出消息;下一条产生 assistant 消息的 item
(agentMessage 或任一工具项)把累积内容取走并清空。这个 "take and clear" 模式在
`_project_agent_message` / `_project_command` / `_project_file_change` /
`_project_mcp_tool_call` / `_project_dynamic_tool_call` 五处**逐字重复**:

`agent/transports/codex_event_projector.py:119-125 @ 863e313`

```python
    def _project_agent_message(self, item: dict) -> ProjectionResult:
        text = item.get("text") or ""
        msg: dict[str, Any] = {"role": "assistant", "content": text}
        if self._pending_reasoning:
            msg["reasoning"] = "\n".join(self._pending_reasoning)
            self._pending_reasoning = []
        return ProjectionResult(messages=[msg], final_text=text)
```

后果是:如果一个 turn 以 reasoning item 结尾(被中断、或 codex 只想了没说),
`_pending_reasoning` 里的内容会**留在投影器实例上**;而投影器是 `run_turn` 里 new 出来的
局部对象,turn 结束即丢弃,所以那段推理**被静默丢弃**。这是可接受的取舍(推理不是必须持久化的),
但值得在重实现时明确写下来。

### 3.6 兜底:未知 item 变成不透明笔记

`agent/transports/codex_event_projector.py:300-314 @ 863e313`

```python
    def _project_opaque(self, item: dict, item_type: str) -> ProjectionResult:
        # Record the existence of the item without inventing tool_calls.
        # Memory review will see this and may or may not save anything.
        try:
            payload = json.dumps(item, ensure_ascii=False)[:1500]
        except (TypeError, ValueError):
            payload = repr(item)[:1500]
        return ProjectionResult(
            messages=[
                {
                    "role": "assistant",
                    "content": f"[codex {item_type}] {payload}",
                }
            ]
        )
```

设计原则值得抄:**面对一个还在演进的上游协议,未知事件既不能丢、也不能瞎编结构**。
丢了记忆复盘就看不到"发生过什么";瞎编 `tool_calls` 会让下游按工具调用去配对 `tool_call_id`,
产生一条永远等不到结果的悬空调用。折中是产出一条纯文本 assistant 笔记。

一个由此产生的**不一致**(◇-2):`agent/codex_runtime.py` 的显示桥把 `webSearch` 列进了
"值得画工具气泡"的 item 类型集合,但投影器**没有** `webSearch` 分支,于是它落进 `_project_opaque`
——即历史里它是一条 `[codex webSearch] {...}` 文本,`is_tool_iteration=False`,
**不计入技能提示计数器**。显示上是一次工具调用,历史与计数上不是。

---

## 4. `codex_app_server_session.py` —— 会话适配器(本片的重心)

### 4.1 一次 `run_turn` 的完整走法

```text
run_turn(user_input)
  ├─ ensure_started()                    # 幂等:spawn + initialize + thread/start
  │    └─ 失败 → TurnResult(error=…, should_retire=True) 直接返回
  ├─ 若 interrupt 已置位 → 立刻返回 interrupted=True(不清标志前的抢跑保护)
  ├─ turn/start  (timeout=10)
  │    ├─ CodexAppServerError → 先试 OAuth 分类,否则 error+stderr 尾巴
  │    └─ TimeoutError       → 视为子进程卡死,should_retire=True
  ├─ deadline = now + turn_timeout(默认 600s)
  └─ while now < deadline and not turn_complete:
        ① interrupt 置位?      → turn/interrupt,interrupted=True,break
        ② 子进程死了?          → OAuth 分类 / stderr 尾巴,should_retire=True,break
        ③ 工具完成后静默超时?  → turn/interrupt,error=…,should_retire=True,break
        ④ 有服务端请求(审批)? → 先排空最多 8 条通知 → 处理审批 → continue
        ⑤ 取一条通知(默认阻塞 0.25s)
             ├─ 不属于本 turn → 丢弃
             ├─ on_event 显示桥
             ├─ token usage / compaction 记账
             ├─ fileChange 追踪(给审批提示用)
             ├─ 投影 → projected_messages / tool_iterations / final_text
             └─ method == "turn/completed" → turn_complete=True,读 status/error
     收尾:
        - 有 final_text 但没等到 turn/completed → 接受它,记一条 warning
        - 否则 → turn/interrupt + interrupted + error + should_retire
```

签名与三个超时旋钮:

`agent/transports/codex_app_server_session.py:470-487 @ 863e313`

```python
    def run_turn(
        self,
        user_input: Any,
        *,
        turn_timeout: float = 600.0,
        notification_poll_timeout: float = 0.25,
        post_tool_quiet_timeout: float = 90.0,
    ) -> TurnResult:
        """Send a user message and block until turn/completed, while
        forwarding server-initiated approval requests and projecting items
        into Hermes' messages shape.

        post_tool_quiet_timeout: if codex emits a tool completion and then
        goes quiet for this many seconds without emitting another item or
        `turn/completed`, fast-fail and mark the session for retirement.
        Mirrors openclaw beta.8's post-tool completion watchdog (#81697)
        so a wedged codex doesn't burn the full turn deadline.
        """
```

### 4.2 启动:权限档"故意不发"

`agent/transports/codex_app_server_session.py:315-346 @ 863e313`

```python
    def ensure_started(self) -> str:
        """Spawn the subprocess, do the initialize handshake, and start a
        thread. Returns the codex thread id. Idempotent — repeated calls
        return the same thread id."""
        if self._thread_id is not None:
            return self._thread_id
        if self._client is None:
            self._client = self._client_factory(
                codex_bin=self._codex_bin, codex_home=self._codex_home
            )
        self._client.initialize(
            client_name="hermes",
            client_title="Hermes Agent",
            client_version=_get_hermes_version(),
        )
        # Permission selection is intentionally NOT sent on thread/start.
        # Two reasons (live-tested against codex 0.130.0):
        #   1. `thread/start.permissions` is gated behind the experimentalApi
        #      capability on this codex version — we'd have to opt in during
        #      initialize and accept the unstable surface.
        #   2. Even with experimentalApi declared and the correct shape
        #      (`{"type": "profile", "id": "..."}`, not `{"profileId": ...}`),
        #      codex requires a matching `[permissions]` table in
        #      ~/.codex/config.toml or it fails the request with
        #      'default_permissions requires a [permissions] table'.
        # Letting codex pick its default (`:read-only` unless the user has
        # configured otherwise in their codex config.toml) is the standard
        # codex CLI workflow and avoids fighting codex's own validation.
        # Users who want a write-capable profile configure it in their
        # ~/.codex/config.toml the same way they would for any codex usage.
        params: dict[str, Any] = {"cwd": self._cwd}
        result = self._client.request("thread/start", params, timeout=15)
```

这段注释是全篇最有价值的"取舍记录"之一:作者试过在 `thread/start` 里带权限档,
被 codex 0.130.0 的两道关卡挡回来——(1) 该字段被 `experimentalApi` 能力位门控,
要用就得在 initialize 里声明并接受不稳定接口;(2) 即使声明了、形状也写对了
(`{"type": "profile", "id": …}` 而不是 `{"profileId": …}`),codex 仍要求
`~/.codex/config.toml` 里有匹配的 `[permissions]` 表,否则整个请求失败。
结论是**不跟上游的校验较劲**:让 codex 用它自己的默认档,权限由用户在 codex 自己的配置里定。

由此产生一个**惰性配置面**(■-5):`_permission_profile` 仍然被算出来,但只进了一行日志——

`agent/transports/codex_app_server_session.py:52-61 @ 863e313`

```python
# Permission profile mapping mirrors the docstring in PR proposal:
# Hermes' tools.terminal.security_mode → Codex's permissions profile id.
# Defaults if config is missing → workspace-write (matches Codex's own default).
_HERMES_TO_CODEX_PERMISSION_PROFILE = {
    "auto": "workspace-write",
    "approval-required": "read-only-with-approval",
    "unrestricted": "full-access",
    # Backstop alias used by some skills/tests.
    "yolo": "full-access",
}
```

`agent/transports/codex_app_server_session.py:289-294 @ 863e313`

```python
        self._permission_profile = (
            permission_profile or _HERMES_TO_CODEX_PERMISSION_PROFILE.get(
                os.environ.get("HERMES_TERMINAL_SECURITY_MODE", "auto"),
                "workspace-write",
            )
        )
```

`agent/transports/codex_app_server_session.py:367-372 @ 863e313`

```python
        logger.info(
            "codex app-server thread started: id=%s profile=%s cwd=%s",
            self._thread_id[:8],
            self._permission_profile,
            self._cwd,
        )
```

```verify
cd /home/user/hermes-agent && grep -rnI --exclude-dir=.git --exclude-dir=__pycache__ \
    "HERMES_TERMINAL_SECURITY_MODE" .
```

搜索面:仓库根下全部文本文件(不加 `--include`;只剔 `.git/` 与 `__pycache__/`),
模式为字面量 `HERMES_TERMINAL_SECURITY_MODE`。**唯一命中就是上面这一处读取**——
没有任何地方**写**它,也没有任何地方消费 `_permission_profile`。
`_HERMES_TO_CODEX_PERMISSION_PROFILE` 映射的三个值(`workspace-write` /
`read-only-with-approval` / `full-access`)与文档给用户看的三个档位
(`:workspace` / `:read-only` / `:danger-no-sandbox`)也不是同一套词汇。

### 4.3 thread id 的跨版本兼容

`agent/transports/codex_app_server_session.py:347-366 @ 863e313`

```python
        # Cross-fill thread.id/sessionId — different codex versions have
        # serialized this under either key. Mirrors openclaw beta.8's
        # tolerance fix so future codex drops/renames don't KeyError us
        # at handshake time.
        thread_obj = result.get("thread") or {}
        thread_id = (
            thread_obj.get("id")
            or thread_obj.get("sessionId")
            or result.get("sessionId")
            or result.get("threadId")
        )
        if not thread_id:
            raise CodexAppServerError(
                code=-32603,
                message=(
                    "codex thread/start returned no thread id "
                    f"(payload keys: {sorted(result.keys())})"
                ),
            )
        self._thread_id = thread_id
```

四个候选键位轮着取(`thread.id` / `thread.sessionId` / `sessionId` / `threadId`),
取不到就抛一个**带 payload 键名列表**的错误。这是接一个尚未冻结的上游协议时的标准手法:
**读多写少**——读的时候宽容,写的时候只写一种形状;失败时把你看到的实际形状打进错误里,
否则用户报的 bug 你无从复现。

### 4.4 多路复用隔离:一条连接上不止一个 thread

`agent/transports/codex_app_server_session.py:132-165 @ 863e313`

```python
def _notification_belongs_to_turn(
    note: dict,
    *,
    thread_id: Optional[str],
    turn_id: Optional[str],
) -> bool:
    """Return whether a multiplexed notification belongs to this turn.

    Codex app-server can carry parent and hosted subagent threads over one
    JSON-RPC connection.  An explicitly foreign child or
    stale-turn event must not mutate the active parent's transcript or mark
    its turn complete.  Unscoped notifications remain accepted for protocol
    compatibility.
    """
    if not isinstance(note, dict):
        return False

    observed_thread_id, observed_turn_id = _notification_scope_ids(note)

    if (
        thread_id is not None
        and observed_thread_id is not None
        and str(observed_thread_id) != str(thread_id)
    ):
        return False

    if (
        turn_id is not None
        and observed_turn_id is not None
        and str(observed_turn_id) != str(turn_id)
    ):
        return False

    return True
```

规则是"**显式外来才拒**":只有当本地已知 id 与观测到的 id **都存在且不等**时才判定为外来;
观测不到 id 的通知一律放行(协议兼容)。配套的 `_notification_scope_ids` 在三个位置、
两种命名风格(camelCase 与 snake_case)里找 id:

`agent/transports/codex_app_server_session.py:95-129 @ 863e313`

```python
def _notification_scope_ids(
    note: dict,
) -> tuple[Optional[str], Optional[str]]:
    """Extract the thread/turn identity carried by a notification."""
    if not isinstance(note, dict):
        return None, None
    params = note.get("params") or {}
    if not isinstance(params, dict):
        return None, None

    nested_turn = params.get("turn") or {}
    nested_item = params.get("item") or {}

    observed_thread_id = params.get("threadId") or params.get("thread_id")
    if observed_thread_id is None and isinstance(nested_turn, dict):
        observed_thread_id = (
            nested_turn.get("threadId")
            or nested_turn.get("thread_id")
        )
    if observed_thread_id is None and isinstance(nested_item, dict):
        observed_thread_id = (
            nested_item.get("threadId")
            or nested_item.get("thread_id")
        )

    observed_turn_id = params.get("turnId") or params.get("turn_id")
    if observed_turn_id is None and isinstance(nested_turn, dict):
        observed_turn_id = nested_turn.get("id") or nested_turn.get("turnId")
    if observed_turn_id is None and isinstance(nested_item, dict):
        observed_turn_id = (
            nested_item.get("turnId")
            or nested_item.get("turn_id")
        )

    return observed_thread_id, observed_turn_id
```

代价:一条**没带任何 scope 的陈旧通知**会被当成本 turn 的。收益:codex 换了字段名不会
让整个 runtime 变哑。这条取舍在 `compact_thread` 里被**收紧**了(见 §4.9)。

### 4.5 取消的三个入口

| 入口 | 触发者 | 机制 |
|---|---|---|
| `request_interrupt()` | `AIAgent.interrupt()`(跨线程) | 置 `threading.Event`,由 turn 循环下一轮观察到后发 `turn/interrupt` |
| 超时/看门狗 | turn 循环自己 | 同样走 `_issue_interrupt` |
| `close()` | 会话退休 / 进程退出 | 关 stdin → terminate → kill |

`agent/transports/codex_app_server_session.py:397-400 @ 863e313`

```python
    def request_interrupt(self) -> None:
        """Idempotent: signal the active turn loop to issue turn/interrupt
        and unwind. Called by AIAgent's _interrupt_requested path."""
        self._interrupt_event.set()
```

`agent/transports/codex_app_server_session.py:983-996 @ 863e313`

```python
    def _issue_interrupt(self, turn_id: Optional[str]) -> None:
        if self._client is None or self._thread_id is None or turn_id is None:
            return
        try:
            self._client.request(
                "turn/interrupt",
                {"threadId": self._thread_id, "turnId": turn_id},
                timeout=5,
            )
        except CodexAppServerError as exc:
            # "no active turn to interrupt" is fine — already done.
            logger.debug("turn/interrupt non-fatal: %s", exc)
        except TimeoutError:
            logger.warning("turn/interrupt timed out")
```

`_issue_interrupt` 把 "no active turn to interrupt" 当作正常情况吞掉(debug 级),
只有超时才 warning。这是对的:中断是**尽力而为**,turn 可能刚好自己结束了。

还有一个非取消的旁路——`turn/steer`,把用户中途的补充话塞进正在跑的 turn:

`agent/transports/codex_app_server_session.py:402-427 @ 863e313`

```python
    def request_steer(self, text: str) -> bool:
        """Append user guidance to the active Codex turn via ``turn/steer``."""
        cleaned = str(text or "").strip()
        if not cleaned:
            return False
        with self._active_turn_lock:
            turn_id = self._active_turn_id
            thread_id = self._thread_id
            client = self._client
        if not turn_id or not thread_id or client is None:
            return False
        try:
            response = client.request(
                "turn/steer",
                {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": cleaned}],
                    "expectedTurnId": turn_id,
                },
                timeout=10,
            )
        except (CodexAppServerError, TimeoutError):
            logger.debug("turn/steer rejected for active Codex turn", exc_info=True)
            return False
        accepted_turn_id = response.get("turnId") if isinstance(response, dict) else None
        return accepted_turn_id in {None, turn_id}
```

注意 `expectedTurnId`:这是一个**乐观并发**的写法,防止用户的补充话落到下一个 turn 上。
返回值判定是 `accepted_turn_id in {None, turn_id}`——服务端不回 turnId 也算接受。

**这里是 ■-2 的现场**:`request_steer` 读 `_active_turn_id` 时特意加了
`_active_turn_lock`,说明它**被设计成跨线程调用**;而 `run_agent.py` 的
`interrupt()` / steer 入口确实在别的线程上。但 `CodexAppServerClient` 的
`_take_id()` 与 `_send()` **都没有锁**:

`agent/transports/codex_app_server.py:293-312 @ 863e313`

```python
    def _take_id(self) -> int:
        # JSON-RPC ids only need to be unique per-connection. A simple
        # monotonically increasing int is the common choice and matches what
        # codex's own clients use.
        rid = self._next_id
        self._next_id += 1
        return rid

    def _send(self, obj: dict) -> None:
        if self._closed:
            raise RuntimeError("codex app-server client is closed")
        if self._proc.stdin is None:
            raise RuntimeError("codex app-server stdin not available")
        try:
            self._proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
            self._proc.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:
            raise RuntimeError(
                f"codex app-server stdin closed unexpectedly: {exc}"
            ) from exc
```

两个线程同时 `request()` 时:`self._next_id += 1` 不是原子操作,可能发出两条同 id 的请求,
后注册的 `_pending[rid]` 会覆盖前一个,被覆盖的那个调用方只能阻塞到自己的 timeout;
`_send` 对 `bufsize=0` 的裸管道并发写,超过 `PIPE_BUF` 的帧还可能交错。
而这个类自己的 docstring(§2.2)写的是 "Spawning thread (caller) drives request/response
pairs synchronously"——**唯一的生产消费者违反了它自己声明的线程模型**。

### 4.6 超时:四层,各管各的

| 层 | 默认值 | 触发后 |
|---|---|---|
| `initialize` | 10s | `RuntimeError`/`TimeoutError` → 由 `ensure_started` 的调用方兜 |
| `thread/start` | 15s | 同上,`should_retire=True` |
| `turn/start` | 10s | 视为子进程卡死,`should_retire=True` |
| turn 整体 `turn_timeout` | 600s | `turn/interrupt` + `interrupted` + `should_retire` |
| 工具后静默 `post_tool_quiet_timeout` | 90s | 提前熔断,不烧满 600s |

最后这条"工具后静默看门狗"是本文件最有意思的机制:

`agent/transports/codex_app_server_session.py:596-609 @ 863e313`

```python
            if (
                last_tool_completion_at is not None
                and (time.monotonic() - last_tool_completion_at)
                    > post_tool_quiet_timeout
            ):
                self._issue_interrupt(result.turn_id)
                result.interrupted = True
                result.error = (
                    f"codex went silent for "
                    f"{post_tool_quiet_timeout:.0f}s after a tool result; "
                    f"retiring app-server session."
                )
                result.should_retire = True
                break
```

它只在**刚完成一个工具项之后**武装,任何后续活动都会解除:

`agent/transports/codex_app_server_session.py:708-718 @ 863e313`

```python
            if projection.is_tool_iteration:
                result.tool_iterations += 1
                # Arm/refresh the post-tool quiet watchdog whenever a
                # tool-shaped item completes.
                last_tool_completion_at = time.monotonic()
            else:
                # Any non-tool projected activity (assistant message,
                # status update, etc.) means codex is still producing
                # output — clear the quiet timer so we don't fast-fail.
                if projection.messages or projection.final_text is not None:
                    last_tool_completion_at = None
```

为什么单挑"工具完成之后"这个时刻:那是 codex 最容易卡住的位置(工具跑完了、
下一步模型调用挂了),而普通的"模型正在想"本来就可能安静很久。用一个 90 秒的窄窗口
换掉 600 秒的宽窗口,前提是**只在明确知道对面刚有过动作的时候**才计时。

另有一条兜底,在 deadline 到了但已经拿到过完整 assistant 文本时,接受它而不是判失败:

`agent/transports/codex_app_server_session.py:760-772 @ 863e313`

```python
        if (
            not turn_complete
            and not result.interrupted
            and result.final_text
            and result.error is None
        ):
            logger.warning(
                "codex app-server turn reached deadline after a completed "
                "assistant message but before turn/completed; accepting "
                "the assistant text as the terminal response"
            )
            turn_complete = True

```

### 4.7 错误分类:四条分支 + 一个保守的 OAuth 分类器

`agent/transports/codex_app_server_session.py:231-251 @ 863e313`

```python
def _classify_oauth_failure(*parts: str) -> Optional[str]:
    """Return a user-friendly re-auth hint if any of the provided strings
    look like a codex OAuth/token-refresh failure; otherwise None.

    Used for both `turn/start` JSON-RPC errors and post-mortem stderr
    inspection when the subprocess exits unexpectedly. Conservative on
    purpose — we only redirect users to `codex login` when the signal
    is strong, so unrelated runtime failures still surface verbatim.
    """
    haystack = " ".join(p for p in parts if p).lower()
    if not haystack:
        return None
    for needle in _OAUTH_REFRESH_FAILURE_HINTS:
        if needle in haystack:
            return (
                "Codex authentication failed — your ChatGPT/Codex login "
                "looks expired or invalid. Run `codex login` to refresh, "
                "then retry. (Fall back to default runtime with "
                "`/codex-runtime auto` if the issue persists.)"
            )
    return None
```

分类器的输入既包括 JSON-RPC 的 error message,也包括 codex 的 stderr 尾巴——
后者是关键,因为 token 刷新失败往往先出现在 stderr 里、然后进程才死。
关键词表刻意保守(`invalid_grant` / `401 unauthorized` / `no auth profile` / `oauth` …),
理由写得很清楚:**只有在信号足够强时才把用户引到 `codex login`,否则原样透出**。
一个乱猜的"你需要重新登录"比一句看不懂的原始错误更糟。

它在四个位置被复用:`turn/start` 的 RPC 错误、`turn/start` 超时、循环里发现子进程已死、
`turn/completed` 带非成功状态。四处的共同结构是"先试分类,不中就退回带 stderr 尾巴的通用消息":

`agent/transports/codex_app_server_session.py:431-466 @ 863e313`

```python
    def _format_error_with_stderr(
        self,
        prefix: str,
        exc: Any = "",
        *,
        tail_lines: int = _STDERR_TAIL_LINES,
    ) -> str:
        """Build a user-facing error string for codex failures.

        Appends the last few lines of codex's stderr buffer when available,
        passed through agent.redact with force=True so secrets in provider
        error responses (auth headers, query-string tokens, sk-* keys) never
        leak into chat output or trajectories. The codex CLI's own error
        text ('Internal error', 'turn/start failed: ...') is otherwise
        opaque and forces users to re-run with verbose flags to diagnose
        config / provider / auth-bridge problems.

        Use this for the generic / catch-all branches. Specific
        classifications (OAuth via _classify_oauth_failure, post-tool wedge
        watchdog) already produce a clean hint and should be used instead.
        """
        exc_str = str(exc) if exc != "" and exc is not None else ""
        base = f"{prefix}: {exc_str}" if exc_str else prefix
        if self._client is None:
            return base
        try:
            tail = self._client.stderr_tail(tail_lines)
        except Exception:  # pragma: no cover - diagnostic best-effort
            return base
        if not tail:
            return base
        joined = "\n".join(line.rstrip() for line in tail if line)
        if not joined.strip():
            return base
        redacted = redact_sensitive_text(joined, force=True)
        return f"{base}\ncodex stderr (last {len(tail)} lines):\n{redacted}"
```

注意 `redact_sensitive_text(joined, force=True)`:provider 的错误响应里经常带着
Authorization 头、query-string token、`sk-*` key,而这段文本会进聊天输出和 trajectory。
**把子进程的诊断输出当作不可信文本对待**,是这里值得抄的一条。

`turn/completed` 分支的状态处理:

`agent/transports/codex_app_server_session.py:734-758 @ 863e313`

```python
            if method == "turn/completed":
                turn_complete = True
                turn_status = (
                    (note.get("params") or {}).get("turn") or {}
                ).get("status")
                if turn_status and turn_status not in {"completed", "interrupted"}:
                    err_obj = (
                        (note.get("params") or {}).get("turn") or {}
                    ).get("error")
                    if err_obj:
                        err_msg = _format_responses_error(err_obj, str(turn_status))
                        # If the turn failed for an auth/refresh reason,
                        # rewrite the error into a re-auth hint AND mark
                        # the session for retirement.
                        stderr_blob = "\n".join(
                            self._client.stderr_tail(40)
                        )
                        hint = _classify_oauth_failure(err_msg, stderr_blob)
                        if hint is not None:
                            result.error = hint
                            result.should_retire = True
                        else:
                            result.error = self._format_error_with_stderr(
                                f"turn ended status={turn_status}", err_msg
                            )
```

`interrupted` 被当作**成功的终态**(不在报错集合里),因为那是用户自己按的。

### 4.8 审批桥:协议翻译,不做策略

`agent/transports/codex_app_server_session.py:998-1009 @ 863e313`

```python
    def _handle_server_request(self, req: dict) -> None:
        """Translate a codex server request (approval) into Hermes' approval
        flow, then send the response.

        Method names verified live against codex 0.130.0 (Apr 2026):
          item/commandExecution/requestApproval — exec approvals
          item/fileChange/requestApproval       — apply_patch approvals
          item/permissions/requestApproval      — permissions changes
                                                  (we decline; user controls
                                                  permission profile in
                                                  ~/.codex/config.toml).
        """
```

`agent/transports/codex_app_server_session.py:1016-1027 @ 863e313`

```python
        if method == "item/commandExecution/requestApproval":
            decision = self._decide_exec_approval(params)
            self._client.respond(rid, {"decision": decision})
        elif method == "item/fileChange/requestApproval":
            decision = self._decide_apply_patch_approval(params)
            self._client.respond(rid, {"decision": decision})
        elif method == "item/permissions/requestApproval":
            # Codex sometimes asks to escalate permissions mid-turn. We
            # always decline — the user already chose their permission
            # profile in ~/.codex/config.toml and surprise escalations
            # shouldn't be silently accepted.
            self._client.respond(rid, {"decision": "decline"})
```

四条已知的服务端请求 + 一条必答的兜底:

`agent/transports/codex_app_server_session.py:1048-1054 @ 863e313`

```python
        else:
            # Unknown server request — codex can extend this surface. Reject
            # cleanly so codex doesn't hang waiting for us.
            logger.warning("Unknown codex server request: %s", method)
            self._client.respond_error(
                rid, code=-32601, message=f"Unsupported method: {method}"
            )
```

**未知方法必须回错误,不能不回**——JSON-RPC 的服务端请求是阻塞的,不回等于让 codex 挂死。
这是双向 RPC 里最容易忘的一条纪律。

策略与协议的分层写得很明确:

`agent/transports/codex_app_server_session.py:1056-1068 @ 863e313`

```python
    def _decide_exec_approval(self, params: dict) -> str:
        """Decide a Codex exec approval request.

        This is protocol-level routing only — it carries NO Hermes
        approval-mode/timeout logic. The Hermes-side resolution happens
        upstream: ``agent/codex_runtime.py`` derives
        ``auto_approve_exec`` from the canonical
        ``tools.approval.is_approval_bypass_active()`` (which reads
        ``approvals.mode`` via ``tools.approval._get_approval_mode``),
        and ``self._approval_callback`` itself runs the shared approval
        gate (mode + ``approvals.timeout``) in ``tools/approval.py``.
        Keep it that way — do not re-read approval config here.
        """
```

即:审批模式(`approvals.mode`)、超时(`approvals.timeout`)、bypass 判定
全部留在 `tools/approval.py` 这个共享核心里;这里只做**线值翻译**:

`agent/transports/codex_app_server_session.py:1244-1264 @ 863e313`

```python
def _approval_choice_to_codex_decision(choice: str) -> str:
    """Map Hermes approval choices onto codex's CommandExecutionApprovalDecision
    / FileChangeApprovalDecision wire values.

    Hermes returns 'once', 'session', 'always', or 'deny'.
    Codex expects 'accept', 'acceptForSession', 'decline', or 'cancel'
    (verified against codex-rs/app-server-protocol/src/protocol/v2/item.rs
    on codex 0.130.0).

    This mapping is Codex-protocol-semantic and intentionally lives here,
    NOT in tools/approval.py: the Hermes approval mode/timeout resolution
    and the choice itself come from the shared core (tools/approval.py);
    only the wire-value translation is local.
    """
    if choice in {"once",}:
        return "accept"
    if choice in {"session", "always"}:
        return "acceptForSession"
    # "deny" and "timeout" both map to decline — codex has no wire value for
    # "prompt expired"; the Hermes-side messaging already distinguishes them.
    return "decline"
```

`deny` 与 `timeout` 都映射到 `decline`,注释说明了原因:codex 的线值里没有"提示超时"这个概念,
而 Hermes 侧的措辞已经区分了两者。没有回调时**一律 fail-closed 返回 `decline`**。

审批提示的信息补全是一个协议缺口的绕行:codex 的 fileChange 审批参数**不带变更集**,
所以适配器自己从 `item/started` 缓存一份摘要,审批时按 `itemId` 取回:

`agent/transports/codex_app_server_session.py:1138-1154 @ 863e313`

```python
    def _track_pending_file_change(self, note: dict) -> None:
        """Maintain self._pending_file_changes from item/started + item/completed
        notifications. Lets the apply_patch approval prompt show what's
        actually changing — codex's approval params don't carry the data."""
        method = note.get("method", "")
        params = note.get("params") or {}
        item = params.get("item") or {}
        if item.get("type") != "fileChange":
            return
        item_id = item.get("id") or ""
        if not item_id:
            return
        if method == "item/started":
            changes = item.get("changes") or []
            if not changes:
                self._pending_file_changes[item_id] = "1 change pending"
                return
```

缓存在 `item/completed` 时清除。文档如实承认了这个机制的边界:

`website/docs/user-guide/features/codex-app-server-runtime.md:410 @ 863e313`

> - **No inline patch preview in approval prompts when codex doesn't track the changeset.** Codex's `fileChange` approval params don't always carry the changeset. Hermes caches the data from the corresponding `item/started` notification when possible, but if approval arrives before the item has streamed, the prompt falls back to whatever `reason` codex provides.

### 4.9 记账:token 用量与压缩边界

Codex **不把 token 用量放在 `turn/completed` 上**,而是单独发一条通知:

`agent/transports/codex_app_server_session.py:1188-1209 @ 863e313`

```python
def _apply_token_usage_notification(result: TurnResult, note: dict) -> None:
    """Capture Codex app-server token usage updates for caller accounting.

    Codex does not put token usage on turn/completed. It emits a separate
    thread/tokenUsage/updated notification containing cumulative totals and
    the latest turn breakdown.
    """
    if not isinstance(note, dict) or note.get("method") != "thread/tokenUsage/updated":
        return
    params = note.get("params") or {}
    token_usage = params.get("tokenUsage") or {}
    if not isinstance(token_usage, dict):
        return
    last = token_usage.get("last")
    total = token_usage.get("total")
    if isinstance(last, dict):
        result.token_usage_last = dict(last)
    if isinstance(total, dict):
        result.token_usage_total = dict(total)
    window = token_usage.get("modelContextWindow")
    if isinstance(window, int) and window > 0:
        result.model_context_window = window
```

压缩边界则要同时认新旧两种形状——新版是 `contextCompaction` item,旧版是已废弃的
`thread/compacted` 通知:

`agent/transports/codex_app_server_session.py:1212-1241 @ 863e313`

```python
def _apply_compaction_notification(result: TurnResult, note: dict) -> None:
    """Capture Codex-native context compaction boundaries.

    Recent app-server builds expose compaction as a ContextCompaction item.
    Older builds also emit the deprecated thread/compacted notification. Both
    mean the underlying Codex thread history has been compacted.
    """
    if not isinstance(note, dict):
        return
    method = note.get("method") or ""
    params = note.get("params") or {}
    if not isinstance(params, dict):
        return

    if method == "thread/compacted":
        result.compacted = True
        result.thread_id = params.get("threadId") or result.thread_id
        result.turn_id = params.get("turnId") or result.turn_id
        return

    if method not in {"item/started", "item/completed"}:
        return

    item = params.get("item") or {}
    if not isinstance(item, dict) or item.get("type") != "contextCompaction":
        return

    result.compacted = True
    result.thread_id = params.get("threadId") or result.thread_id
    result.turn_id = params.get("turnId") or result.turn_id
```

`compact_thread()` 则是"主动触发一次 Codex 原生压缩"。它和 `run_turn` 的**关键差异**是:
`thread/compact/start` **不返回 turn id**,所以在 `turn/started` 到达之前,
任何可终结/可投影的事件都不能归到这次压缩上:

`agent/transports/codex_app_server_session.py:880-909 @ 863e313`

```python
            if result.turn_id is None:
                if method == "turn/started":
                    if (
                        observed_thread_id is not None
                        and str(observed_thread_id) != str(self._thread_id)
                    ):
                        logger.debug(
                            "ignoring foreign compact turn/started: thread=%s",
                            observed_thread_id,
                        )
                        continue
                    if observed_turn_id is None:
                        logger.debug(
                            "ignoring compact turn/started without a turn id"
                        )
                        continue
                    result.turn_id = str(observed_turn_id)
                elif observed_turn_id is not None or method in {
                    "item/completed",
                    "turn/completed",
                }:
                    # thread/compact/start does not return a turn id. Until the
                    # new turn/started arrives, any terminal/projectable event
                    # is stale or cannot be safely attributed to this compaction.
                    logger.debug(
                        "ignoring codex notification before compact turn start: "
                        "method=%s",
                        method,
                    )
                    continue
```

这是对 §4.4 那条"宽容"规则的**局部收紧**:在还不知道自己 turn id 的窗口里,
宁可丢弃也不误收。两处规则不同、且都写明了理由,是好的工程记录。

### 4.10 ■-1:审批前置排空会吞掉本 turn 的 `turn/completed`

这是本片最重的一条。`run_turn` 在处理服务端请求(审批)之前,会**先排空最多 8 条通知**,
理由是让 `_pending_file_changes` 在做审批决策前是最新的:

`agent/transports/codex_app_server_session.py:611-622 @ 863e313`

```python
            # Drain any server-initiated requests (approvals) before
            # reading notifications, so the codex side isn't blocked.
            sreq = self._client.take_server_request(timeout=0)
            if sreq is not None:
                # Drain any pending notifications first so per-turn state
                # (e.g. _pending_file_changes for fileChange approvals) is
                # up to date when we make the approval decision. Bounded
                # to avoid starving the server-request response.
                for _ in range(8):
                    pending = self._client.take_notification(timeout=0)
                    if pending is None:
                        break
```

这个内层循环把主循环的处理逻辑抄了一遍(显示桥、记账、fileChange 追踪、投影、
`<turn_aborted>` 标记),但**唯独漏了 `method == "turn/completed"` 这一支**:

`agent/transports/codex_app_server_session.py:654-670 @ 863e313`

```python
                    if proj.is_tool_iteration:
                        result.tool_iterations += 1
                        last_tool_completion_at = time.monotonic()
                    if proj.final_text is not None:
                        result.final_text = proj.final_text
                        if _has_turn_aborted_marker(proj.final_text):
                            turn_complete = True
                            result.interrupted = True
                            result.error = (
                                result.error
                                or "codex reported turn_aborted"
                            )
                self._handle_server_request(sreq)
                # Activity counts as live signal — reset the post-tool
                # quiet timer so an approval round-trip doesn't trip it.
                last_tool_completion_at = None
                continue
```

于是:一条本 turn 的 `turn/completed` 如果恰好在审批往返的排空窗口里被取出来,
它会被投影器忽略(投影器只认 `item/completed`)、`turn_complete` 不会被置位、
turn 的 `status`/`error` 也不会被读取。主循环随后继续空转到 `turn_timeout`。

同一事件序列,唯一差别是"审批请求是否在队列里"。下面这条命令自带三个用例、可重跑
(`turn_timeout` 缩到 3 秒,生产默认 600 秒):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_QUIET=1 \
/home/user/hermes-venv/bin/python - <<'PY'
import time
from agent.transports.codex_app_server_session import (
    CodexAppServerSession, _ServerRequestRouting)

class C:                                   # minimal stand-in for CodexAppServerClient
    def __init__(self, **k): self.n, self.s, self.req = [], [], []
    def initialize(self, **k): return {}
    def request(self, m, p=None, timeout=30.0):
        self.req.append(m)
        return {"thread": {"id": "T1"}} if m == "thread/start" else (
               {"turn": {"id": "U1"}} if m == "turn/start" else {})
    def notify(self, *a, **k): pass
    def respond(self, *a, **k): pass
    def respond_error(self, *a, **k): pass
    def take_notification(self, timeout=0.0):
        if self.n: return self.n.pop(0)
        if timeout > 0: time.sleep(min(timeout, .001))
    def take_server_request(self, timeout=0.0):
        return self.s.pop(0) if self.s else None
    def stderr_tail(self, n=20): return []
    def is_alive(self): return True
    def close(self): pass

APPROVAL = {"id": "a1", "method": "item/commandExecution/requestApproval",
            "params": {"command": "pwd", "cwd": "/tmp"}}
MSG = {"method": "item/completed", "params": {"threadId": "T1", "turnId": "U1",
       "item": {"type": "agentMessage", "id": "m1", "text": "done"}}}
DONE_OK = {"method": "turn/completed", "params": {"threadId": "T1",
           "turn": {"id": "U1", "status": "completed", "error": None}}}
DONE_FAIL = {"method": "turn/completed", "params": {"threadId": "T1",
             "turn": {"id": "U1", "status": "failed",
                      "error": {"message": "upstream 500"}}}}

def run(label, approval, notes):
    c = C()
    if approval: c.s.append(APPROVAL)
    c.n.extend(notes)
    s = CodexAppServerSession(cwd="/tmp", client_factory=lambda **k: c,
                              request_routing=_ServerRequestRouting(auto_approve_exec=True))
    t = time.monotonic()
    r = s.run_turn("hi", turn_timeout=3.0, notification_poll_timeout=0.01)
    print(f"{label:22s} elapsed={time.monotonic()-t:4.2f}s final={r.final_text!r} "
          f"interrupted={r.interrupted} retire={r.should_retire} error={r.error!r}")

run("no-approval",   False, [MSG, DONE_OK])
run("drained",       True,  [MSG, DONE_OK])
run("drained,failed", True, [DONE_FAIL])
PY
```

实测输出(第二行是被测代码自己打的 warning):

```text
no-approval            elapsed=0.00s final='done' interrupted=False retire=False error=None
codex app-server turn reached deadline after a completed assistant message but before turn/completed; accepting the assistant text as the terminal response
drained                elapsed=3.00s final='done' interrupted=False retire=False error=None
drained,failed         elapsed=3.00s final='' interrupted=True retire=True error='turn timed out after 3.0s'
```

三个用例读法:

- **`no-approval`**:同样两条通知,没有审批挂着 → 0.00 秒返回,一切正常。
- **`drained`**:多了一条待处理的审批请求 → **3.00 秒**(= 烧满 `turn_timeout`)才返回。
  §4.6 那条"有 final_text 就接受"的兜底救回了**结果**,但救不回**延迟**:生产上是等满 600 秒。
- **`drained,failed`**:这一轮没有 assistant 文本(codex 直接以 `status=failed` +
  `error={"message": "upstream 500"}` 结束)→ 兜底不成立,走到
  `not turn_complete and not result.interrupted` 分支:

`agent/transports/codex_app_server_session.py:773-784 @ 863e313`

```python
        if not turn_complete and not result.interrupted:
            # Hit the deadline. Issue interrupt to stop wasted compute, and
            # tell the caller to retire the session — a turn that never
            # finished is a strong sign codex is wedged in a way the next
            # turn shouldn't inherit.
            self._issue_interrupt(result.turn_id)
            result.interrupted = True
            if not result.error:
                result.error = self._format_error_with_stderr(
                    f"turn timed out after {turn_timeout}s"
                )
            result.should_retire = True
```

  于是**真实错因 `upstream 500` 被整条丢弃,替换成一句伪造的 "turn timed out after 3.0s"**,
  并额外触发一次不必要的会话退休(`retire=True`)与一次多余的 `turn/interrupt`。
  这是"负结论错了会关闭调查"的镜像——一个错误的正结论会把下一个读者引到错误的方向。

现有测试只覆盖了这个排空窗口里出现**外来**(子 thread)`turn/completed` 的情形
(`tests/agent/transports/test_codex_app_server_session.py::TestRunTurn::test_foreign_completion_in_server_request_drain_is_ignored`),
本 turn 自己的那条从未被测。

**修法**(供重实现参考):把内层排空改成调用与主循环同一个 `_handle_notification()`,
而不是抄一份;或者退一步——把排空到的通知**塞回队列**,只做 fileChange 追踪。
根因是**同一段协议处理逻辑被复制成两份,其中一份少了一支**。

---

## 5. `codex.py` —— Responses 协议 transport

### 5.1 定位:只管"这一次请求长什么样"

`agent/transports/codex.py:1-6 @ 863e313`

```python
"""OpenAI Responses API (Codex) transport.

Delegates to the existing adapter functions in agent/codex_responses_adapter.py.
This transport owns format conversion and normalization — NOT client lifecycle,
streaming, or the _run_codex_stream() call path.
"""
```

这条边界很重要:客户端生命周期、流式、重试、取消、凭据刷新**都不在这里**,
在 `AIAgent` / `conversation_loop` / `codex_runtime.run_codex_stream` 里。
本文件是一个**纯函数式的格式层**,只有一处状态(`_last_issuer_kind`,见 §5.3)。

真正的转换全部委托给 `agent/codex_responses_adapter.py`,并且是**函数体内 import**:

`agent/transports/codex.py:203-216 @ 863e313`

```python
    def convert_messages(self, messages: List[Dict[str, Any]], **kwargs) -> Any:
        """Convert OpenAI chat messages to Responses API input items."""
        from agent.codex_responses_adapter import _chat_messages_to_responses_input
        issuer = self._resolve_issuer_kind(kwargs)
        self._last_issuer_kind = issuer
        return _chat_messages_to_responses_input(
            messages,
            is_xai_responses=kwargs.get("is_xai_responses") is True,
            is_github_responses=kwargs.get("is_github_responses") is True,
            replay_encrypted_reasoning=bool(
                kwargs.get("replay_encrypted_reasoning", True)
            ),
            current_issuer_kind=issuer,
        )
```

延迟 import 的实际作用是打断循环依赖(adapter 反过来要用 agent 的东西),
代价是每次调用都要走一次模块缓存查找。

### 5.2 prompt cache key:三层演化,每一层都有事故

这是本文件最密的一段,值得逐层拆。

**第一层:cron 的 session_id 里带每次触发的时间戳。**

`agent/transports/codex.py:13-16 @ 863e313`

```python
# Cron fires build session_id as ``cron_<job_id>_<YYYYMMDD_HHMMSS>`` (see
# cron/scheduler.py). The trailing timestamp is per-fire noise; stripped so
# repeat fires of the same job share a cache scope (see #51395/#52295).
_CRON_SESSION_ID_RE = re.compile(r"^(cron_.+)_\d{8}_\d{6}$")
```

`agent/transports/codex.py:19-28 @ 863e313`

```python
def _cache_scope_from_session_id(session_id: Optional[str]) -> str:
    """Normalize a physical session_id into a stable logical cache scope.

    Every non-cron session_id already identifies one conversation/agent
    instance (main run, a specific child/subagent, a sibling child, ...),
    so it is used unchanged. Only cron's per-fire timestamp needs stripping.
    """
    sid = str(session_id or "")
    match = _CRON_SESSION_ID_RE.match(sid)
    return match.group(1) if match else sid
```

现象:定时任务每次触发生成 `cron_<job>_<YYYYMMDD_HHMMSS>`,直接拿它当缓存键,
于是**每一次触发都是冷缓存**。剥掉时间戳后同一个 job 的历次触发共享缓存作用域。

**第二层:光有 scope 还不够,得内容寻址。**

`agent/transports/codex.py:142-157 @ 863e313`

```python
    """Content-address the prompt cache key within a logical cache scope.

    Returns ``pck_<sha256[:24]>`` of (scope_id + instructions + sorted tool
    schemas), or None when there is nothing static to key on. The cache key
    is a routing hint only — never a correctness boundary — so two requests
    sharing a scope, system prompt, and tool set intentionally resolve to the
    same warm prefix bucket.

    ``scope_id`` (pass ``_cache_scope_from_session_id(session_id)``) keeps
    unrelated sessions — independent conversations, main vs. child/subagent,
    sibling children — from concentrating onto the same bucket merely because
    their static prefix matches (see #78941), while still letting recurring
    cron fires of one job share a stable key across their timestamped
    session_ids (the original #51395/#52295 fix this built on). Sorting tools
    by name keeps the hash insertion-order independent.
    """
```

`agent/transports/codex.py:158-173 @ 863e313`

```python
    if not instructions and not tools:
        return None
    tools_part = ""
    if tools:
        sorted_tools = sorted(
            (t for t in tools if isinstance(t, dict)),
            key=lambda t: str(t.get("name") or t.get("type") or ""),
        )
        tools_part = json.dumps(
            sorted_tools, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
    # \x00 separators so a scope/instructions/tools boundary can't be forged
    # by content that happens to contain the same bytes.
    content = f"{scope_id}\x00{instructions or ''}\x00{tools_part}"
    digest = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:24]
    return f"pck_{digest}"
```

三个细节值得抄:

- **工具按名字排序后再序列化**,让哈希与插入顺序无关。否则工具注册顺序一变(而语义没变)
  缓存就全丢。
- **`\x00` 作分隔符**,防止内容里恰好含有分隔字节从而伪造 scope/instructions/tools 的边界。
- 注释里明确写了 "The cache key is a routing hint only — never a correctness boundary"。
  这句定性决定了后面所有取舍都可以"宁可撞桶也不要冷启动"。

**第三层:scope 必须进哈希,否则不相关的会话会撞到同一个桶。**
`scope_id` 进哈希是为了让"独立会话 / 主 agent 与子 agent / 兄弟子 agent"不会仅仅因为
静态前缀相同就挤到同一个后端桶上。

**收尾:长度上界。**

`agent/transports/codex.py:34-45 @ 863e313`

```python
def _bounded_prompt_cache_key(value: Any) -> Optional[str]:
    """Return a provider-safe cache key without changing session identity."""
    if value is None:
        return None
    key = str(value).strip()
    if not key:
        return None
    if len(key) <= 64:
        return key
    # Match _content_cache_key's compact, collision-resistant routing-key shape.
    digest = hashlib.sha256(key.encode("utf-8", errors="replace")).hexdigest()[:24]
    return f"pck_{digest}"
```

超过 64 字符就换成 `pck_<sha256[:24]>`。注意它被应用了**三次**(build_kwargs 顶层、
xAI 的 extra_body、preflight),因为 `request_overrides` 可以在任何一层塞进一个超长值。

**落到线上是三个不同的位置**,取决于后端:

`agent/transports/codex.py:371-394 @ 863e313`

```python
        session_id = params.get("session_id")
        # prompt_cache_key is content-addressed from the static prefix
        # (instructions + tools) scoped by session, NOT the raw session_id —
        # recurring cron jobs carry a per-fire timestamp in session_id
        # (cron_<id>_<ts>) that made every run cache-cold, so the scope strips
        # that suffix (see _cache_scope_from_session_id). session_id is left
        # untouched for transcript isolation and the cache-scope routing
        # headers below. Falls back to session_id when there is no static
        # content to hash.
        _cache_scope = _cache_scope_from_session_id(session_id)
        cache_key = _content_cache_key(
            instructions, response_tools, _cache_scope
        ) or _cache_scope
        # xAI Responses takes prompt_cache_key in extra_body (set further
        # down); GitHub Models opts out of cache-key routing entirely.
        if not is_github_responses and not is_xai_responses and cache_key:
            kwargs["prompt_cache_key"] = cache_key

        cache_retention = _default_prompt_cache_retention_for_request(
            model,
            params.get("base_url"),
        )
        if cache_retention:
            kwargs.setdefault("prompt_cache_retention", cache_retention)
```

`agent/transports/codex.py:462-486 @ 863e313`

```python
        if is_codex_backend:
            # The Codex backend rejects body-level ``extra_headers`` with
            # HTTP 400, but the OpenAI SDK's ``extra_headers`` kwarg maps
            # to actual HTTP request headers (not body fields).  ``session_id``
            # carries the raw physical session id — transcript/identity, per
            # the #57012 contract — while ``x-client-request-id`` mirrors the
            # body's effective ``prompt_cache_key`` so header and body always
            # agree on the same routing bucket instead of diverging (#78941).
            final_cache_key = kwargs.get("prompt_cache_key") or _bounded_prompt_cache_key(_cache_scope)
            if session_id or final_cache_key:
                existing_extra_headers = kwargs.get("extra_headers")
                merged_extra_headers: Dict[str, str] = {}
                if isinstance(existing_extra_headers, dict):
                    merged_extra_headers.update(
                        {
                            str(key): str(value)
                            for key, value in existing_extra_headers.items()
                            if key and value is not None
                        }
                    )
                if session_id:
                    merged_extra_headers["session_id"] = str(session_id)
                if final_cache_key:
                    merged_extra_headers["x-client-request-id"] = final_cache_key
                kwargs["extra_headers"] = merged_extra_headers
```

Codex 后端这一段的教训很具体:**body 级 `extra_headers` 会被拒(HTTP 400),
但 SDK 的 `extra_headers` kwarg 映射的是真正的 HTTP 头**。而 `session_id` 头走**原始**
物理会话 id(身份),`x-client-request-id` 头走**effective 的 cache key**(路由)——
两者刻意分开,并且保证头与 body 指向同一个桶而不是各说各话。

### 5.3 `issuer_kind`:本文件唯一的状态

Responses API 的 reasoning 块是**签发端专属**的:xAI 签发的加密推理块喂回给 OpenAI 会被拒。
所以每次构造请求时要把"这次是谁签发的"记下来,响应归一化时盖到 reasoning item 上,
下一轮再把外来签发者的块丢掉。

`agent/transports/codex.py:182-201 @ 863e313`

```python
    # Issuer kind of the most recent build_kwargs / convert_messages call.
    # Used as a fallback when normalize_response is invoked without an
    # explicit ``issuer_kind`` kwarg, so reasoning items captured from a
    # response are stamped with the endpoint that minted them. Plain class
    # attribute default; mutated on the instance, not the class.
    _last_issuer_kind: Optional[str] = None

    @property
    def api_mode(self) -> str:
        return "codex_responses"

    def _resolve_issuer_kind(self, params: Dict[str, Any]) -> str:
        """Classify the current Responses endpoint from transport params."""
        from agent.codex_responses_adapter import _classify_responses_issuer
        return _classify_responses_issuer(
            is_xai_responses=params.get("is_xai_responses") is True,
            is_github_responses=params.get("is_github_responses") is True,
            is_codex_backend=params.get("is_codex_backend") is True,
            base_url=params.get("base_url"),
        )
```

`agent/transports/codex.py:275-281 @ 863e313`

```python
        # Resolve the issuing endpoint for this call. Stashed on the
        # transport so normalize_response can stamp it onto reasoning
        # items captured from the response, and passed to the input
        # converter so foreign-issuer reasoning blocks in history are
        # dropped before the API rejects them.
        issuer_kind = self._resolve_issuer_kind(params)
        self._last_issuer_kind = issuer_kind
```

`agent/transports/codex.py:542-548 @ 863e313`

```python
        # Issuer for this response = explicit kwarg if the caller knows it,
        # otherwise the stash from the matching build_kwargs/convert_messages
        # call. Either way it gets stamped onto reasoning items so future
        # turns can detect a model swap and drop foreign-issuer blobs.
        issuer_kind = kwargs.get("issuer_kind") or self._last_issuer_kind
        # _normalize_codex_response returns (SimpleNamespace, finish_reason_str)
        msg, finish_reason = _normalize_codex_response(response, issuer_kind=issuer_kind)
```

这套"实例上暂存"的写法能成立,前提是 `AIAgent._get_transport()` **按 api_mode 缓存实例**
(`run_agent.py` 里的 `_transport_cache`);而 `agent.transports.get_transport()` 本身
**每次 `return cls()` 新建**。也就是说:**这个机制的正确性依赖调用方缓存,
而 transport 自己没有任何东西能保证这一点**——这是一条隐式契约(◇-1)。

### 5.4 reasoning effort:四张钳表叠加

`agent/transports/codex.py:293-306 @ 863e313`

```python
        _effort_clamp = {"minimal": "low"}
        if "gpt-5.6" in (model or "").lower():
            # Ultra is the Codex product tier; the Responses API wire value is max.
            _effort_clamp["ultra"] = "max"
        if params.get("is_xai_responses", False):
            # xAI Responses tops out at high; keep generic stronger values usable.
            _effort_clamp.update({"xhigh": "high", "max": "high", "ultra": "high"})
        if (params.get("provider") or "").strip().lower() == "actual":
            # Actual Computer relays to SGLang/vLLM backends that accept only
            # none/low/medium/high/max for reasoning effort — a forwarded
            # xhigh/ultra fails with a wrapped HTTP 400 ("Expecting value:
            # line 1 column 1"). Clamp Hermes' wider set to the supported one.
            _effort_clamp.update({"xhigh": "high", "ultra": "max"})
        reasoning_effort = _effort_clamp.get(reasoning_effort, reasoning_effort)
```

Hermes 内部的 effort 词汇比任何单一 provider 都宽(`minimal/low/medium/high/xhigh/max/ultra`),
所以每个后端要各自往下钳:

| 条件 | 钳位 |
|---|---|
| 总是 | `minimal → low` |
| 模型名含 `gpt-5.6` | `ultra → max`(Ultra 是产品名,线值叫 max) |
| xAI Responses | `xhigh/max/ultra → high` |
| provider == `actual` | `xhigh → high`,`ultra → max` |

`actual` 那条的注释特别有教育意义:它中继到 SGLang/vLLM,只认
`none/low/medium/high/max`;转发 `xhigh` 会得到一个**被包装过的** HTTP 400
(`Expecting value: line 1 column 1`)——即上游把非 JSON 错误页塞给了 SDK 的 JSON 解析器。
**一个来自三层之外的、看起来像解析 bug 的错误,根因是一个枚举值不被支持。**

xAI 还有一条**模型级**的门:即使 effort 合法,某些 grok 模型也会对 `reasoning.effort` 回 400,
所以要么在白名单里、要么整个 `reasoning` 键都不发:

`agent/transports/codex.py:396-412 @ 863e313`

```python
        if reasoning_enabled and is_xai_responses:
            from agent.model_metadata import grok_supports_reasoning_effort

            # Ask xAI to echo back encrypted reasoning items so we can
            # replay them on subsequent turns for cross-turn coherence.
            # See agent/codex_responses_adapter._chat_messages_to_responses_input
            # for the May 2026 reversal of the earlier suppression gate.
            kwargs["include"] = (
                ["reasoning.encrypted_content"] if replay_encrypted_reasoning else []
            )
            # xAI rejects `reasoning.effort` on grok-4 / grok-4-fast / grok-3
            # / grok-code-fast / grok-4.20-0309-* with HTTP 400 even though
            # those models reason natively. Only send the effort dial when
            # the target model is on the allowlist; otherwise send no
            # `reasoning` key at all and let the model reason on its own.
            if grok_supports_reasoning_effort(model):
                kwargs["reasoning"] = {"effort": reasoning_effort}
```

### 5.5 xAI 的 `web_search` 命名冲突

`agent/transports/codex.py:48-53 @ 863e313`

```python
# Wire-name used when Hermes keeps client-side web_search on xAI Responses.
# A function literally named ``web_search`` collides with Grok's native
# server-side tool (incomplete hang or HTTP 400 duplicate names); this alias
# avoids that while still dispatching through Hermes's configured provider
# (Firecrawl / Tavily / …). Mapped back to ``web_search`` in normalize_response.
_XAI_CLIENT_WEB_SEARCH_ALIAS = "hermes_web_search"
```

事故经过(可复述版):Hermes 把自己的网页搜索工具声明成一个普通函数,名字就叫 `web_search`。
在 xAI 的 `/v1/responses` 上,grok 有一个**服务端执行**的同名内建工具。
把一个 `function` 声明成 `web_search`,请求会被 grok 当成"要用内建搜索",
但它又不是 `{"type": "web_search"}` 那种声明,于是搜索**发起了却永远对不上账**——
turn 停在 incomplete,再重试三次。2026-06 在 grok-composer-2.5-fast 上实测复现。

修法是两种模式,按用户配置的搜索后端选:

`agent/transports/codex.py:330-344 @ 863e313`

```python
        if is_xai_responses and response_tools:
            has_client_web_search = any(
                isinstance(t, dict) and t.get("name") == "web_search"
                for t in response_tools
            )
            if has_client_web_search:
                if _xai_prefers_native_web_search():
                    filtered = [
                        t for t in response_tools
                        if not (isinstance(t, dict) and t.get("name") == "web_search")
                    ]
                    filtered.append({"type": "web_search"})
                    response_tools = filtered
                else:
                    response_tools = _rename_client_web_search_for_xai(response_tools)
```

- **原生模式**:把客户端的 `web_search` 函数**删掉**,换成 `{"type": "web_search"}`。
  注意是 1:1 替换,**只在原本就有客户端 `web_search` 时才做**——绝不额外授予一个新能力。
- **客户端模式**:保留 Hermes 的分发(这样 `web.backend` 配置才有意义),
  但把线上的名字改成 `hermes_web_search`,让 grok 抢不走。

解析失败时**fail-closed 到原生**:

`agent/transports/codex.py:56-78 @ 863e313`

```python
def _xai_prefers_native_web_search() -> bool:
    """True when xAI Responses should use Grok's native ``web_search`` built-in.

    Delegates to the web-search registry's provider resolution (which reads
    ``web.search_backend`` / ``web.backend`` from config) and checks whether
    the resolved provider is xAI. Falls back to the legacy ``_get_search_backend``
    probe when the registry has no providers loaded. On any resolution failure,
    returns True (fail-closed to native — preserves the #48108 incomplete-hang
    fix rather than risk reintroducing it).
    """
    try:
        from agent.web_search_registry import get_active_search_provider

        provider = get_active_search_provider()
        if provider is not None:
            return getattr(provider, "name", None) == "xai"

        from tools.web_tools import _get_search_backend

        return (_get_search_backend() or "").strip().lower() == "xai"
    except Exception:
        # Fail closed to native — same behavior as pre-fix main.
        return True
```

别名在归一化时被换回来,闭环:

`agent/transports/codex.py:560-563 @ 863e313`

```python
                # Undo the xAI client-path wire alias so Hermes dispatches
                # the real ``web_search`` tool (Firecrawl / etc.).
                if name == _XAI_CLIENT_WEB_SEARCH_ALIAS:
                    name = "web_search"
```

### 5.6 `tools` 必须整键省略,不能传 `None`

`agent/transports/codex.py:346-369 @ 863e313`

```python
        # ``tools`` MUST be omitted entirely when there are no functions to
        # expose: the openai SDK's ``responses.stream()`` / ``responses.parse()``
        # eagerly call ``_make_tools(tools)`` which does ``for tool in tools``
        # without a None guard, so passing ``tools=None`` raises
        # ``TypeError: 'NoneType' object is not iterable`` before any HTTP
        # request is issued (openai==2.24.0).  Reported for the
        # ``openai-codex`` / ``gpt-5.5`` combo on chatgpt.com/backend-api/codex
        # (#32892) when the agent runs without external tools registered.
        kwargs = {
            "model": model,
            "instructions": instructions,
            "input": _chat_messages_to_responses_input(
                payload_messages,
                is_xai_responses=is_xai_responses,
                is_github_responses=is_github_responses,
                replay_encrypted_reasoning=replay_encrypted_reasoning,
                current_issuer_kind=issuer_kind,
            ),
            "store": False,
        }
        if response_tools:
            kwargs["tools"] = response_tools
            kwargs["tool_choice"] = "auto"
            kwargs["parallel_tool_calls"] = True
```

这是一条纯粹的 SDK 陷阱:openai 2.24.0 的 `responses.stream()` / `parse()` 会 eager 地
`for tool in tools`,没有 None 守卫,所以 `tools=None` 会在**发出任何 HTTP 请求之前**
抛 `TypeError: 'NoneType' object is not iterable`。触发条件是"agent 没有注册任何外部工具"——
一个听起来不会发生、但在 `-q` 单问单答场景下天天发生的组合。
`tool_choice` 与 `parallel_tool_calls` 也跟着一起只在有工具时才设。

### 5.7 归一化与校验

`agent/transports/codex.py:589-613 @ 863e313`

```python
    def validate_response(self, response: Any) -> bool:
        """Check Codex Responses API response has valid output structure.

        Returns True only if response.output is a non-empty list. Also treats
        terminal content-filter incomplete responses as valid: the Responses API
        may return status=incomplete with incomplete_details.reason='content_filter'
        and no output items. That is a provider refusal signal, not a malformed
        response, and must reach normalization so the agent loop can use the
        content-policy / fallback path instead of invalid-response retries.

        Does NOT check output_text fallback — the caller handles that with
        diagnostic logging for stream backfill recovery.
        """
        if response is None:
            return False
        output = getattr(response, "output", None)
        if not isinstance(output, list) or not output:
            status = str(getattr(response, "status", "") or "").strip().lower()
            incomplete_details = getattr(response, "incomplete_details", None)
            if isinstance(incomplete_details, dict):
                reason = str(incomplete_details.get("reason") or "").strip().lower()
            else:
                reason = str(getattr(incomplete_details, "reason", "") or "").strip().lower()
            return status == "incomplete" and reason == "content_filter"
        return True
```

`validate_response` 的**唯一非平凡分支**是:`status="incomplete"` 且
`incomplete_details.reason="content_filter"` 且没有任何 output 项时,**判为有效**。
理由写在 docstring 里——那是 provider 的拒答信号,不是坏响应;必须让它走到归一化,
好让 agent 循环走内容策略/降级路径,而不是当成"响应损坏"去重试。
注意它同时兼容 `incomplete_details` 是 dict 和是对象两种形状。

归一化则把 Responses 的 output 项摊平成 `NormalizedResponse`,并把协议专属的东西
(`codex_reasoning_items` / `codex_message_items` / `reasoning_details`)塞进 `provider_data`:

`agent/transports/codex.py:571-587 @ 863e313`

```python
        # Extract reasoning items for provider_data
        provider_data = {}
        if msg and hasattr(msg, "codex_reasoning_items") and msg.codex_reasoning_items:
            provider_data["codex_reasoning_items"] = msg.codex_reasoning_items
        if msg and hasattr(msg, "codex_message_items") and msg.codex_message_items:
            provider_data["codex_message_items"] = msg.codex_message_items
        if msg and hasattr(msg, "reasoning_details") and msg.reasoning_details:
            provider_data["reasoning_details"] = msg.reasoning_details

        return NormalizedResponse(
            content=msg.content if msg else None,
            tool_calls=tool_calls,
            finish_reason=finish_reason or "stop",
            reasoning=msg.reasoning if msg and hasattr(msg, "reasoning") else None,
            usage=None,  # Codex usage is extracted separately in normalize_usage()
            provider_data=provider_data or None,
        )
```

`usage=None` 是刻意的——Codex 的用量在别处单独抽取。

`map_finish_reason` 则**没有生产调用方**:

`agent/transports/codex.py:652-666 @ 863e313`

```python
    def map_finish_reason(self, raw_reason: str) -> str:
        """Map Codex response.status to OpenAI finish_reason.

        Codex uses response.status ('completed', 'incomplete') +
        response.incomplete_details.reason for granular mapping.
        This method handles the simple status string; the caller
        should check incomplete_details separately for 'max_output_tokens'.
        """
        _MAP = {
            "completed": "stop",
            "incomplete": "length",
            "failed": "stop",
            "cancelled": "stop",
        }
        return _MAP.get(raw_reason, "stop")
```

```verify
cd /home/user/hermes-agent && grep -rnI --exclude-dir=.git --exclude-dir=__pycache__ \
    --exclude-dir=tests "map_finish_reason" .
```

搜索面:仓库根下全部文本文件(不加 `--include`;剔除 `.git/`、`__pycache__/` 与 `tests/`),
模式为字面量 `map_finish_reason`;另加一次对带引号的 `"map_finish_reason"` /
`'map_finish_reason'`(动态 `getattr` 分发)的搜索,**零命中**。命中项只有:各 transport 的定义、`base.py` 的默认实现、
`types.py` 里一个同名但独立的模块级 helper、`__init__.py` 的再导出,
以及 `agent/conversation_loop.py:2776` 唯一一处调用——而那一处在
`elif agent.api_mode == "anthropic_messages":` 分支内。`codex_responses` 的 finish_reason
是在 conversation_loop 里就地算的(要读 `incomplete_details.reason` 做更细的区分),
根本不经过 transport。所以 `ResponsesApiTransport.map_finish_reason` 只被测试执行(◇-3)。

---

## 6. 与 `base.py` / `types.py` 契约的关系(参照,不逐文件精读)

`ProviderTransport` 抽象基类定义的数据路径是
`convert_messages → convert_tools → build_kwargs → normalize_response`,
并明确声明它**不拥有**客户端构造、流式、凭据刷新、prompt 缓存、中断、重试。
`ResponsesApiTransport` 完全落在这个契约里,只有两点值得记:

1. **它多带了一个协议专属方法** `preflight_kwargs()`,不在基类上。
   调用方在 `conversation_loop` 里以 `agent.api_mode == "codex_responses"` 显式分支调用它。
2. **`build_kwargs` 里其实做了 prompt 缓存的 key 计算**——而基类 docstring 说
   transport 不拥有 prompt caching。这不算矛盾:它算的是**缓存键这个请求字段**,
   不是缓存的存取。但这是基类边界描述与实现最接近的一处摩擦点,重实现时值得先把话说清。

`codex_app_server_session.py` 这一族**完全不在** `ProviderTransport` 契约里——
它不是 transport,没有 `api_mode` 属性,不进注册表。它与外界的契约是 `TurnResult` 这个
dataclass,由 `agent/codex_runtime.py` 消费:

`agent/transports/codex_app_server_session.py:64-86 @ 863e313`

```python
@dataclass
class TurnResult:
    """Result of one user→assistant→tool turn through the codex app-server."""

    final_text: str = ""
    projected_messages: list[dict] = field(default_factory=list)
    tool_iterations: int = 0
    interrupted: bool = False
    error: Optional[str] = None  # Set if turn ended in a non-recoverable error
    turn_id: Optional[str] = None
    thread_id: Optional[str] = None
    token_usage_last: Optional[dict[str, Any]] = None
    token_usage_total: Optional[dict[str, Any]] = None
    model_context_window: Optional[int] = None
    compacted: bool = False
    # Hint to the caller that the underlying codex subprocess is likely
    # wedged (turn-level timeout fired, post-tool watchdog tripped, or
    # token-refresh failure killed the child). The caller should retire
    # the session so the next turn respawns codex from scratch instead
    # of riding a CPU-spinning or auth-broken process. Mirrors openclaw
    # beta.8's "retire timed-out app-server clients" fix.
    should_retire: bool = False

```

`should_retire` 是这个契约里最有意思的字段:它把"这个子进程还能不能接着用"这个判断
**留给会话层做、让调用方执行**。会话层知道细节(deadline 烧完了 / 看门狗跳了 /
OAuth 死了 / 进程没了),调用方拥有生命周期(它才知道该不该 close 并置空)。
职责切得很干净。

---

## 7. 测试作行为规格

跑法(全部带 `HERMES_DISABLE_LAZY_INSTALLS=1`,避免导入期联网装包污染共享 venv):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
  HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
  tests/agent/transports/test_codex_app_server_session.py \
  tests/agent/transports/test_codex_event_projector.py \
  tests/agent/transports/test_codex_app_server_runtime.py \
  tests/agent/transports/test_codex_transport.py
```

三批合计 **19 个文件 / 269 个用例 / 全部通过 / 0 失败**:

| 批次 | 文件数 | 通过 | 失败 |
|---|---|---|---|
| `tests/agent/transports/test_codex_*` | 4 | 146 | 0 |
| `tests/agent/test_codex_*` | 7 | 61 | 0 |
| `tests/run_agent/`+`tui_gateway/`+`cron/` 的 codex 用例 | 8 | 62 | 0 |

环境记录(按 CLAUDE.md 要求):venv 为 `/home/user/hermes-venv`,
`pip list` 去表头计 **87 个包**,`site-packages/*.dist-info` 计 **87 个**,与 R8B 记录一致;
未安装任何新包。

**没有失败,所以本片无"代码缺陷 / 用例脆性 / 容器限制"的失败分诊**。
容器已知的 6 条必然失败用例(无 IPv6、以 root 运行、离线无 models.dev、SQLite 3.45.1)
都不在 codex 相关文件里。

这些测试作为行为规格,最值得当"规范"读的几条:

| 用例 | 钉住的行为 |
|---|---|
| `test_thread_start_passes_cwd_only` | `thread/start` 只带 `cwd`,不带权限档(§4.2 的取舍被测试锁死) |
| `test_foreign_completion_in_server_request_drain_is_ignored` | 排空窗口里的**外来** `turn/completed` 必须被丢弃;本 turn 的那条**未被测**(§4.10) |
| `test_post_tool_watchdog_uses_monotonic_clock` | 看门狗必须用 `time.monotonic()`,不能用墙钟(改系统时间不能误触发) |
| `test_post_tool_watchdog_resets_on_further_activity` | 任何后续活动解除看门狗 |
| `test_final_agent_message_without_turn_completed_is_recovered` | §4.6 的"有 final_text 就接受"兜底 |
| `test_dead_subprocess_detected_between_iterations` | 子进程死了要在循环里被发现,不等 deadline |
| `test_thread_id_under_thread_key` / `test_missing_thread_id_raises` | §4.3 的跨版本键位兼容 |
| `test_turn_start_failure_attaches_redacted_stderr_tail` | 错误里必须带**脱敏后**的 stderr 尾巴 |
| `test_apply_patch_prompt_summarizes_pending_changes` | §4.8 的 fileChange 摘要补全 |
| `test_exec_falls_back_to_session_cwd` | codex 不给 cwd 时用会话 cwd,审批提示不能是空的 |

---

## 8. 定案清单

### 8.1 ▲-1 取证:「HOME environment variable passthrough」整段已过期

按 CLAUDE.md 的规矩,一条文档断言要连它所在的整句/整段一并判定,并确认它归哪个标题管。
这一句归 `## HOME environment variable passthrough` 这个标题:

`website/docs/user-guide/features/codex-app-server-runtime.md:326 @ 863e313`

> ## HOME environment variable passthrough

断言本体是一整句,里面有三个可判定的分句:

`website/docs/user-guide/features/codex-app-server-runtime.md:328 @ 863e313`

> Hermes does NOT rewrite `HOME` when spawning the codex app-server subprocess (we use `os.environ.copy()` and only overlay `CODEX_HOME` and `RUST_LOG`). This means:

**分句 (a)「we use `os.environ.copy()`」——假。** 代码走的是集中式的
`hermes_subprocess_env(inherit_credentials=True)`,它在 `os.environ.copy()` 之上还剥掉了
Tier-1 密钥与 Hermes 内部动态密钥(见 §2.3 的 `codex_app_server.py:79-94` 摘录)。
helper 自身:

`tools/environments/local.py:606-610 @ 863e313`

```python
    env = os.environ.copy()

    # Tier 1 — always strip.
    for key in _ALWAYS_STRIP_KEYS:
        env.pop(key, None)
```

**分句 (b)「only overlay `CODEX_HOME` and `RUST_LOG`」——假。** 同一个 helper 还会设
`PYTHONUTF8`、注入 `HERMES_HOME`、写 `HERMES_REAL_HOME` 与 `HOME`、剥 venv 标记、
注入会话上下文;`CodexAppServerClient` 自己也允许调用方通过 `env=` 参数覆盖任意键。
而且生产路径上 `codex_home` 是 `None`(`agent/codex_runtime.py` 构造
`CodexAppServerSession` 时不传),所以 `CODEX_HOME` **根本没被 overlay**:

`tools/environments/local.py:627-632 @ 863e313`

```python
    # Windows UTF-8 safety for spawned processes (#31420).
    env.setdefault("PYTHONUTF8", "1")

    _inject_context_hermes_home(env)
    from hermes_constants import apply_subprocess_home_env
    apply_subprocess_home_env(env)
```

**分句 (c)「Hermes does NOT rewrite `HOME`」——有条件为假。** 上面那行
`apply_subprocess_home_env(env)` 就是专门改 `HOME` 的:

`hermes_constants.py:932-939 @ 863e313`

```python
def apply_subprocess_home_env(env: dict[str, str]) -> None:
    """Apply Hermes' subprocess HOME contract to *env* in-place."""
    real_home = get_real_home(env)
    if real_home:
        env["HERMES_REAL_HOME"] = real_home
    home = get_subprocess_home(env)
    if home:
        env["HOME"] = home
```

`get_subprocess_home()` 在 `terminal.home_mode: profile` 下返回 profile home,
在容器内(`is_container()` 为真且存在 profile home)也返回 profile home——两种情况下
子进程看到的 `HOME` 都被改写。文档紧接着据此推出的两条后果
(「codex 的 shell 能找到 `~/.gitconfig`、`~/.aws`」)因此在容器部署下不成立。

*(第 (c) 条我只做了代码路径判读,没有在本容器实起一个子进程打印 HOME;见 §10 第 4 条。)*

### 8.2 ▲-2 取证:Kanban 可写根只加了一个,文档说加了一组

这一句归 `### Kanban (multi-agent worktree dispatch)` 这个标题:

`website/docs/user-guide/features/codex-app-server-runtime.md:88 @ 863e313`

> ### Kanban (multi-agent worktree dispatch)

文档断言(整段最后一句,含它自己引用的 issue):

`website/docs/user-guide/features/codex-app-server-runtime.md:102 @ 863e313`

> The kanban tools are gated by `HERMES_KANBAN_TASK` env var the dispatcher sets — that var is propagated to the codex subprocess (codex inherits env) and from there to the spawned `hermes-tools` MCP server subprocess. So the tools see the right task id and gate correctly. For Codex app-server workers, Hermes also passes narrow app-server sandbox overrides when `HERMES_KANBAN_TASK` is present: keep `workspace-write` sandboxing, add the **board DB directory plus every Kanban path the dispatcher pinned** as extra writable roots (`HERMES_KANBAN_WORKSPACES_ROOT`, `HERMES_KANBAN_WORKSPACE`, legacy `HERMES_KANBAN_ROOT` — deduplicated, DB-dir first), and keep network disabled by default. This avoids the brittle `:danger-no-sandbox` workaround while letting `kanban_complete` / `kanban_block` update the board DB **and** letting workers write reports/artifacts under workspace mounts that live outside the DB directory (e.g. `/media/.../kanban-workspaces/...` on a separate drive — [issue #27941](https://github.com/NousResearch/hermes-agent/issues/27941)).

代码侧(§2.4 已摘录 `codex_app_server.py:96-124`)只做了两件事:
把 `HERMES_KANBAN_DB` 的**目录**取出来,取不到才退到 `HERMES_KANBAN_ROOT`(或默认
`$HERMES_HOME/kanban`),然后把**这一个**路径写进 `sandbox_workspace_write.writable_roots`。
没有去重、没有"DB 目录在前"的排序(因为只有一个元素),
也从不读 `HERMES_KANBAN_WORKSPACES_ROOT` 或 `HERMES_KANBAN_WORKSPACE`。

```verify
cd /home/user/hermes-agent && grep -rnI --exclude-dir=.git --exclude-dir=__pycache__ \
    "writable_roots" .
cd /home/user/hermes-agent && grep -rnI --exclude-dir=__pycache__ \
    "HERMES_KANBAN_WORKSPACES_ROOT\|HERMES_KANBAN_WORKSPACE" agent/transports/ ; echo "exit=$?"
```

搜索面:第一条在仓库根下全部文本文件(不加 `--include`;只剔 `.git/` 与 `__pycache__/`)
搜字面量 `writable_roots`,**全仓只有两处命中**——`agent/transports/codex_app_server.py:120`
与一处断言它的测试。第二条把搜索面限定在 `agent/transports/`(即构造 `codex app-server` 启动参数的
那个目录,也就是上一条命中的 `:120` 所在处)搜两个变量名,**零命中,`exit=1`**。
需要说明搜索面为什么这么划:这两个变量在 `agent/` 别处确实出现
(`agent/secret_scope.py` 的密钥作用域名单、`agent/prompt_builder.py` 的看板提示词文本),
但那些都不是"构造 codex 沙箱参数"的位置;文档断言讲的是沙箱可写根,
所以判定面就是构造那串 `-c sandbox_workspace_write.writable_roots=...` 的代码。

**用户可见后果**:文档自己引的 issue #27941 描述的正是"工作区挂在另一块盘上、
不在 board DB 目录下"的场景。按代码,那种 worker 在 codex 沙箱里仍然写不了自己的工作区,
只能写 DB 目录。文档把一个**未实现的修复**写成了已完成的行为。

### 8.3 清单

记号:■ = 代码缺陷;▲ = 文档所述与代码矛盾;◇ = 代码有、文档无;◎ = 文档成立但显著保守。

| 记号 | 锚点 | 现象 |
|---|---|---|
| ■-1 | `agent/transports/codex_app_server_session.py:619` | 审批前置排空循环没有 `turn/completed` 分支:本 turn 的完成通知若落在这个窗口里会被吞掉,turn 空转到 `turn_timeout`(默认 600s);若该轮没有 assistant 文本,真实错因还会被替换成伪造的 "turn timed out" 并触发不必要的会话退休。已用最小复现实测(§4.10) |
| ■-2 | `agent/transports/codex_app_server.py:293` | `_take_id()` / `_send()` 无锁,而 `request_steer` / `request_interrupt` 被设计并实际从另一线程调用(`run_agent.py:3287` / `:3098`),可产生重复 JSON-RPC id(受害者阻塞到自身 timeout)与并发裸管道写 |
| ■-3 | `agent/transports/codex_app_server.py:146` | 类 docstring 声称通知走 "bounded queues",实际是无界 `queue.Queue()`;同类里 stderr 明确限 500 行。审批阻塞期间 codex 高速推 delta 会无界堆内存 |
| ■-4 | `agent/transports/codex_app_server.py:392` | `check_codex_binary` docstring 写 "Used by setup wizard and runtime startup",但全仓唯一调用方是 `/codex-runtime` 切换命令;`ensure_started()` 不做任何版本/存在性检查,手改 config.yaml 或事后降级 codex 的用户拿到的是裸 `FileNotFoundError` 而非安装提示 |
| ■-5 | `agent/transports/codex_app_server_session.py:289` | `_permission_profile` 与 `_HERMES_TO_CODEX_PERMISSION_PROFILE` 是惰性配置面:只进了一行日志;其数据源 `HERMES_TERMINAL_SECURITY_MODE` 在全仓仅此一处被读、无处被写;映射出的档位名与文档给用户的档位名也不是同一套词汇 |
| ▲-1 | `website/docs/user-guide/features/codex-app-server-runtime.md:328` | "HOME environment variable passthrough" 整段三处断言全部过期:代码不用 `os.environ.copy()`(用 `hermes_subprocess_env`,剥 Tier-1/内部密钥)、不止 overlay `CODEX_HOME`+`RUST_LOG`(还有 `HOME`/`HERMES_REAL_HOME`/`PYTHONUTF8`/`HERMES_HOME`/会话上下文)、且在容器内或 `terminal.home_mode: profile` 下**确实会**改写 `HOME` |
| ▲-2 | `website/docs/user-guide/features/codex-app-server-runtime.md:102` | 文档称给 codex 沙箱加的可写根是"board DB 目录 + dispatcher 钉住的每一个 Kanban 路径(`HERMES_KANBAN_WORKSPACES_ROOT`、`HERMES_KANBAN_WORKSPACE`、legacy `HERMES_KANBAN_ROOT`,去重、DB 目录在前)";代码只加**一个**根,且从不读前两个变量。文档自己引的 #27941(工作区在另一块盘上)因此并未被修 |
| ◇-1 | `agent/transports/codex.py:187` | `_last_issuer_kind` 的正确性依赖调用方缓存 transport 实例(`run_agent.py` 的 `_transport_cache`),而 `agent/transports/get_transport()` 每次 `return cls()` 新建;这条隐式契约不在基类、不在文档 |
| ◇-2 | `agent/transports/codex_event_projector.py:112` | `webSearch` item 在显示桥里算工具气泡,在投影器里落进 `_project_opaque`:历史里是一条文本笔记、`is_tool_iteration=False`,不计入技能提示计数器 |
| ◇-3 | `agent/transports/codex.py:652` | `ResponsesApiTransport.map_finish_reason` 无生产调用方(`codex_responses` 的 finish_reason 在 conversation_loop 就地计算),只被测试执行 |
| ◎-1 | `website/docs/user-guide/features/codex-app-server-runtime.md:155` | 文档要求 codex ≥ 0.130.0,代码的 `MIN_CODEX_VERSION` 是 (0,125,0),模块 docstring 写 "codex 0.125+"。文档更严、字面为真,但两处数字互不联动 |

**最值得主线实跑复核的两条**:■-1(有自带的最小复现,3 秒可验;后果是 600 秒挂起 + 错误信息被替换)
与 ▲-2(一条 grep 即可证伪,且是有实际用户后果的文档-代码分叉)。

---

## 9. 可迁移的设计原则

1. **"接一个模型"和"接一个 agent"是两件事,不要用一个抽象硬套。**
   Responses 路径落在 transport 契约里(纯格式层),app-server 路径根本不进这个契约
   (它是 runtime,契约是 `TurnResult`)。硬要统一只会造出一个两边都不合身的接口。

2. **投影而不是改造下游。** 记忆/技能复盘不需要知道 codex 存在——把外来事件翻译成
   下游本来就认识的形状,是比"给下游加一个 codex 分支"便宜得多的接法。前提是
   翻译时守住下游的不变量(消息交替、`tool_call_id` 配对)。

3. **未知事件既不能丢也不能瞎编结构。** `_project_opaque` 产出纯文本笔记,
   不产出 `tool_calls`——因为一条伪造的工具调用会在下游制造一个永远配不上的 `tool_call_id`。

4. **超时要分层,并且窄窗口只在你确知对面刚动过的时候武装。**
   600 秒的 turn deadline 是保底;90 秒的"工具后静默"看门狗只在一个工具项刚完成后计时,
   任何后续活动解除它。用一个窄窗口换掉宽窗口的前提是**你知道现在应该有动静**。

5. **子进程的诊断输出是不可信文本。** stderr 尾巴要进错误消息(否则用户无从诊断),
   但必须先过脱敏(provider 错误里常带 Authorization 头和 `sk-*`)。

6. **凭据继承是一个开关,不是一个默认值。** "它需要 provider 凭据"不等于
   "它需要你所有的密钥"。集中式 env 构造 + 一个 grep 得到的审计标记
   (`inherit_credentials=True`)比每个 spawn 点各自 `os.environ.copy()` 可控得多。

7. **双向 RPC 里,未知的服务端请求必须回错误。** 不回等于让对面挂死。
   这条纪律在 `_handle_server_request` 的 else 分支里,是最容易被"以后再补"掉的一行。

8. **接未冻结的上游协议:读宽写窄,失败时把你看到的形状打进错误里。**
   `thread/start` 的四键位跨版本兼容、`_notification_scope_ids` 的双命名风格是正面样本;
   而"显式外来才拒"这条宽容规则在 `compact_thread` 里被局部收紧、并写明了理由,
   是"宽容有边界"的正面样本。

9. **缓存键是路由提示,不是正确性边界——把这句话写进代码。**
   一旦定性明确,"工具排序后哈希""scope 进哈希""长度上界换哈希"这些取舍就都不需要再争论。

10. **同一段协议处理逻辑不要复制两份。** ■-1 的根因不是某个判断写错了,
    而是排空循环抄了主循环的一份、少了一支。要么抽成一个函数,要么让排空只做它必须做的事。

---

## 10. 未取证 / 推定

如实列出本片**没有**跑通或没有实证的部分:

1. **没有真跑过 `codex app-server`。** 本容器没有 `codex` 二进制、无 ChatGPT/Codex 凭据、
   离线。所有 app-server 行为都是读代码 + 用 `client_factory` 注入假客户端得到的,
   **没有一条是对真实 codex 0.130.0 的实测**。代码注释里那些 "verified live against
   codex 0.130.0" 的断言(权限档被 `experimentalApi` 门控、审批方法名、
   `CommandExecutionApprovalDecision` 的线值集合)我**只能转述,不能证实**。
2. **■-2 的并发窗口未实证。** 我论证的是"两个线程会调用同一个无锁函数"这一**结构事实**
   (锁的缺失是代码可见的,跨线程调用点也是代码可见的),但**没有**构造出一次实际的
   id 冲突或管道交错。重复 id 的概率取决于 CPython 字节码层面的调度点,我没有量化。
3. **`_send` 对 `bufsize=0` 裸管道的部分写风险未实证。** POSIX 对阻塞管道的
   `write()` 承诺正常完成时返回全部字节数,所以这条只在被信号打断的边缘情形下成立。
   我把它列为 ■-2 的次要论据,**没有**单独定案。
4. **▲-1 的 HOME 改写路径未在本容器实跑。** 我读到 `apply_subprocess_home_env` 会在
   `terminal.home_mode: profile` 或 `is_container()` 为真时写 `env["HOME"]`,
   但**没有**实际起一个子进程去打印它看到的 HOME。`is_container()` 的判定逻辑我没有细读。
5. **`agent/codex_responses_adapter.py` 只读了被 `codex.py` 调用的函数签名与用途**,
   没有精读。`_chat_messages_to_responses_input` / `_normalize_codex_response` /
   `_preflight_codex_api_kwargs` / `_classify_responses_issuer` 的内部行为
   本篇一律按"委托出去了"处理,未取证。
6. **流式路径(`run_codex_stream`)、TTFB 看门狗、`run_codex_create_stream_fallback`
   本篇没有精读**——它们在 `agent/codex_runtime.py`,不在本片 4 个文件里。
   本篇关于"codex.py 不拥有流式"的说法来自模块 docstring 与调用点结构,
   不是对流式实现的分析。
7. **◇-2(webSearch 计数)只做了代码路径推演**,没有构造一个 `webSearch` item
   跑一遍投影器 + 显示桥来实测计数器差异。
8. **"没有第三个 codex 传输路径"这类全称否定本篇未写。** 我只写了三条有明确搜索面的
   负结论(`check_codex_binary` 的调用方、`HERMES_TERMINAL_SECURITY_MODE` 的读写点、
   `map_finish_reason` 的生产调用方),每条的搜索面都写在了它旁边。

---

## 11. 自校验读数

命令:

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent \
    notes/r9c-raw-codex-transport.md
```

实测输出:

```text
citations=91  OK=86  UNCHECKED=5
可校验比例 OK/91 = 94.5%
table_anchors=12  UNCHECKED=12   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
OK: every code-block-backed citation matches the baseline
```

退出码 **0**。四类阻断项:**MISMATCH=0 / BLOCK-DRIFT=0 / TABLE-DRIFT=0 /
TABLE-OUT-OF-RANGE=0 / MISSING-FILE=0**。可校验比例 **94.5%**,高于 70% 下限。
5 条 UNCHECKED 全部是散文里的跨节交叉引用(指向本篇别处已摘录过的区域),
以及 `verify` 声明式非源码块,不是排版问题;单文件 UNCHECKED 占比 5.5%,远低于 90% 提示线。

全部 86 个受校验块由脚本从基线逐字生成(不手抄),未使用 `--fix`。
