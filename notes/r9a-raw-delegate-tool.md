# r9a 底稿 · 委派工具本体 —— `tools/delegate_tool.py`(3,931 行)

> 研究对象基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(只读)。
> 溯源约定:凡对代码行为的断言,**锚点单独成行、置于代码块之前**,格式 `路径:行号 @ 863e313`。
> 本文是底稿(证据层),面向"要凭它重实现同等机制"的自己,求全求证、允许啰嗦。
> 表格里的行号列**不带冒号**,是为了让引用校验器只对"锚点 + 紧跟的代码块"这一种形状计数;
> 表格是索引,不是证据。
>
> **术语一次性锚定**(下文不再解释):
> - **harness** = 把 LLM 包成一个能自己调工具、自己循环的"跑步机"的那层宿主代码。
> - **委派 / delegation** = 主 agent 把一段活丢给一个新起的子 agent,自己只收摘要。
> - **toolset** = 工具集合的命名分组(`web` / `terminal` / `file` …),开关以组为单位。
> - **contextvar** = Python 的"任务局部变量",跨线程不自动继承,要 `copy_context()` 显式拷。
> - **TLS(thread-local storage)** = 线程局部存储,每个线程一份、互不可见。
> - **ACP** = 一种把外部 agent 进程当 provider 用的子进程传输协议(本文只当"另一条出口"看)。

---

## 0. 3,931 行分成哪几段

| 区间 | 段名 | 管什么 |
|---|---|---|
| 1–56 | 模块头 + 黑名单 | 模块 docstring、import、`DELEGATE_BLOCKED_TOOLS`(子 agent 永远拿不到的 5 个工具) |
| 59–133 | 子 agent 审批回调 + 常量 | `_subagent_auto_deny` / `_subagent_auto_approve` / `MAX_DEPTH=1` / 并发默认 3 |
| 136–218 | 运行期全局状态 | 暂停开关 `_spawn_paused`、活跃子 agent 注册表 `_active_subagents`、`interrupt_subagent` |
| 221–462 | 观测数据整形 | 尾部输出抽取、工具参数脱敏(URL 去凭据)、错误判定启发式 |
| 465–711 | 配置读取器(9 个) | 并发上限 / 超时 / 深度 / 编排开关 / MCP 继承 / 复合 toolset 展开 |
| 714–787 | 预算与事件常量 | 迭代 50、摘要 24000 字符、心跳 30s、`DelegateEvent` 枚举 |
| 790–958 | 子 agent 提示词与裁剪 | `_build_child_system_prompt`、`_strip_blocked_tools`、`_blocked_toolsets_for_role` |
| 960–1159 | 进度回调工厂 | 把子 agent 的每次工具调用中继到父 agent 的 spinner / gateway 回调 |
| 1162–1617 | **`_build_child_agent`** | 造孩子:角色定级、toolset 求交、凭据解析、`AIAgent(...)` 构造、身份打标、注册 |
| 1620–1793 | 超时诊断转储 | 0 次 API 调用就超时的那种"黑盒"专用 dump |
| 1796–1968 | 摘要预算 | 按父 agent 剩余上下文动态裁剪子 agent 摘要,全文溢写到磁盘 |
| 1971–2628 | **`_run_single_child`** | 跑孩子:租凭据、开心跳、注册、提交到 1-worker 守护池、整形结果、finally 收尾 |
| 2631–2795 | 锁与收尾 | 三把模块锁、父 agent 级串行化锁、`_finalize_child_results`、插件用的单孩子生命周期 |
| 2798–3410 | **`delegate_task`** | 模型入口:前置闸 → 建全部孩子 → `_execute_and_aggregate` → 同步返回 or 后台派发 |
| 3413–3662 | 凭据与配置解析 | 子 agent 凭据池归属、`delegation.*` 凭据束解析、`_load_config` |
| 3665–3869 | Schema | 动态重建的工具描述(把用户真实的并发/深度上限写进给模型看的文字里) |
| 3872–3931 | 注册 | `registry.register(...)`,以及"模型侧一律后台"的那个 lambda |

**读法建议**:1.4 → 1.5 → 1.6 三节是主干,其余都是挂在主干上的。

---

## 1. 一次委派的完整走法

### 1.1 先把场景演出来

用户在 CLI 里说:"帮我同时查三件事:WebAssembly 现状、RISC-V 现状、量子纠错进展。"
模型决定不自己一条条查(那会把三份原始资料全灌进自己的上下文),而是发出一次工具调用:

```text
delegate_task(tasks=[
  {"goal": "Research WebAssembly ...", "context": "..."},
  {"goal": "Research RISC-V ...",      "context": "..."},
  {"goal": "Research quantum ...",     "context": "..."},
])
```

下面这一节要回答的是:**从这一行到父 agent 屏幕上出现三段摘要之间,一共发生了什么。**

### 1.2 第 0 步:模型看到的 schema 是"每轮现编"的

工具描述不是写死的字符串,而是每次 `get_definitions()` 都按当前配置重建——目的是让模型
读到的"最多 3 个"是**这个用户真实的 3**,而不是框架默认值。

`tools/delegate_tool.py:3769-3789 @ 863e313`
```python
def _build_dynamic_schema_overrides() -> dict:
    """Return per-call schema overrides reflecting current config.

    Plugged into ToolEntry.dynamic_schema_overrides so every
    get_definitions() pass rewrites the description fields to the user's
    actual limits.
    """
    overrides_params = {
        **DELEGATE_TASK_SCHEMA["parameters"],
    }
    # Deep-copy properties so we don't mutate the static schema dict.
    overrides_params["properties"] = {
        k: dict(v) for k, v in DELEGATE_TASK_SCHEMA["parameters"]["properties"].items()
    }
    overrides_params["properties"]["tasks"]["description"] = _build_tasks_param_description()
    overrides_params["properties"]["role"]["description"] = _build_role_param_description()

    return {
        "description": _build_top_level_description(),
        "parameters": overrides_params,
    }
```

三个 **模型侧没有的参数**,是理解后面一切的前提:

1. **没有 `toolsets`**——模型不能给孩子挑工具,也就不能给孩子挑出自己没有的工具。
2. **没有 `max_iterations`**——schema 的 `properties` 里根本没有这一项。
3. **`background` 有,但被声明为"已废弃 / 被忽略"**。

`tools/delegate_tool.py:3854-3865 @ 863e313`
```python
            "background": {
                "type": "boolean",
                "description": (
                    "DEPRECATED / IGNORED. Top-level single and batch "
                    "delegations run in the background automatically — you do "
                    "not need to (and cannot) opt in or out. A single result or "
                    "consolidated batch result re-enters the conversation when "
                    "the work finishes; just continue working in the meantime. "
                    "Setting this has no effect; the parameter remains only for "
                    "backward compatibility."
                ),
            },
```

### 1.3 第 1 步:两个 handler,只有一个是活路径

工具注册在文件末尾。注册用的 lambda 是**兜底**,真正跑的是 `run_agent` 里的拦截。

`tools/delegate_tool.py:3915-3931 @ 863e313`
```python
registry.register(
    name="delegate_task",
    toolset="delegation",
    schema=DELEGATE_TASK_SCHEMA,
    handler=lambda args, **kw: delegate_task(
        goal=args.get("goal"),
        context=args.get("context"),
        tasks=_strip_model_hidden_task_fields(args.get("tasks")),
        max_iterations=args.get("max_iterations"),
        role=args.get("role"),
        background=_model_background_value(args, kw.get("parent_agent")),
        parent_agent=kw.get("parent_agent"),
    ),
    check_fn=check_delegate_requirements,
    emoji="🔀",
    dynamic_schema_overrides=_build_dynamic_schema_overrides,
)
```

`run_agent.py:7658-7667 @ 863e313`
```python
        _is_subagent = getattr(self, "_delegate_depth", 0) > 0
        return _delegate_task(
            goal=function_args.get("goal"),
            context=function_args.get("context"),
            tasks=_strip_model_hidden_task_fields(function_args.get("tasks")),
            max_iterations=function_args.get("max_iterations"),
            role=function_args.get("role"),
            background=(not _is_subagent),
            parent_agent=self,
        )
```

**要点**:`background=(not _is_subagent)`。也就是——

- 顶层模型发起的委派:**一律后台**(模型无权选择);
- 编排者子 agent(`_delegate_depth > 0`)发起的委派:**一律同步**,因为它必须在自己这一轮里
  拿到工人的结果才能合成摘要,而且它并不拥有那个"结果该回哪去"的 gateway 会话。

注意 `max_iterations=function_args.get("max_iterations")` 仍然被传下去了——schema 里没有这个字段,
但如果哪个缓存的旧 schema 或某个 provider 塞了一个进来,它会走到 `delegate_task`,然后被**丢掉**(见 1.4)。

### 1.4 第 2 步:`delegate_task()` 的前置闸

按代码顺序,一次调用要过 9 道闸:

| # | 闸 | 不过时的表现 |
|---|---|---|
| 1 | 必须有 `parent_agent` | `tool_error`,直接返回 |
| 2 | 全局 spawn 暂停开关 | `tool_error`,提示用 TUI 的 `p` 或 `delegation.pause` RPC 解除 |
| 3 | role 归一化 | 未知 role 记 warning 并降级为 `leaf` |
| 4 | 深度上限 | `tool_error`,报出当前 depth 与 `max_spawn_depth` |
| 5 | `max_iterations` 归一 | 静默丢弃调用方给的值,一律用配置值 |
| 6 | 委派凭据解析 | `ValueError` → `tool_error` |
| 7 | `tasks` 若是字符串则尝试 JSON 反序列化 | 解析失败给出可读错误 |
| 8 | 任务条数 ≤ `max_concurrent_children` | `tool_error`,**不静默截断** |
| 9 | 每个 task 必须是 dict 且有非空 `goal` | `tool_error`,点名第几个 |

闸 1、2:

`tools/delegate_tool.py:2821-2831 @ 863e313`
```python
    if parent_agent is None:
        return tool_error("delegate_task requires a parent agent context.")

    # Operator-controlled kill switch — lets the TUI freeze new fan-out
    # when a runaway tree is detected, without interrupting already-running
    # children.  Cleared via the matching `delegation.pause` RPC.
    if is_spawn_paused():
        return tool_error(
            "Delegation spawning is paused. Clear the pause via the TUI "
            "(`p` in /agents) or the `delegation.pause` RPC before retrying."
        )
```

闸 4(深度):

`tools/delegate_tool.py:2845-2856 @ 863e313`
```python
    # Depth limit — configurable via delegation.max_spawn_depth,
    # default 2 for parity with the original MAX_DEPTH constant.
    depth = getattr(parent_agent, "_delegate_depth", 0)
    max_spawn = _get_max_spawn_depth()
    if depth >= max_spawn:
        return tool_error(
            f"Delegation depth limit reached (depth={depth}, "
            f"max_spawn_depth={max_spawn}). Raise "
            f"delegation.max_spawn_depth in config.yaml if deeper "
            f"nesting is required (no hard ceiling, but each level "
            f"multiplies API cost)."
        )
```

闸 5(迭代预算的归属权):**配置说了算,模型说的不算**。这是一处很值得抄的设计——
模型给的值只可能把预算**改小**,于是用户会莫名其妙地看到孩子早退。

`tools/delegate_tool.py:2858-2872 @ 863e313`
```python
    # Load config
    cfg = _load_config()
    default_max_iter = cfg.get("max_iterations", DEFAULT_MAX_ITERATIONS)
    # Model-supplied max_iterations is ignored — the config value is authoritative
    # so users get predictable budgets. The kwarg is retained for internal callers
    # and tests; a model-emitted value here would only shrink the budget and
    # surprise the user mid-run. Log and drop it if one slips through from a
    # cached tool schema or a stale provider.
    if max_iterations is not None and max_iterations != default_max_iter:
        logger.debug(
            "delegate_task: ignoring caller-supplied max_iterations=%s; "
            "using delegation.max_iterations=%s from config",
            max_iterations, default_max_iter,
        )
    effective_max_iter = default_max_iter
```

闸 8(宽度):注意它把"并发上限"直接当成了"批量条数上限"——这两件事在这里是同一个数。

`tools/delegate_tool.py:2885-2900 @ 863e313`
```python
    max_children = _get_max_concurrent_children()
    recovered_tasks, tasks_error = _recover_tasks_from_json_string(tasks)
    if tasks_error:
        return tool_error(tasks_error)
    if recovered_tasks is not None:
        tasks = recovered_tasks

    if tasks and isinstance(tasks, list):
        if len(tasks) > max_children:
            return tool_error(
                f"Too many tasks: {len(tasks)} provided, but "
                f"max_concurrent_children is {max_children}. "
                f"Either reduce the task count, split into multiple "
                f"delegate_task calls, or increase "
                f"delegation.max_concurrent_children in config.yaml."
            )
```

过闸之后,**先建实时转写日志,再建全部孩子**。转写日志是旁路:每个任务一个 append-only 文本文件,
用户可以 `tail -f` 看孩子干活,而不必等合并摘要。

`tools/delegate_tool.py:2926-2939 @ 863e313`
```python
    # Live transcripts: one pre-headered append-only log per task under
    # cache/delegation/live/<delegation_id>/task-<n>.log so the caller can
    # tail each child's operations while it runs (side-channel only — zero
    # effect on message content or prompt caching). Best-effort: on failure
    # live_paths is empty and delegation proceeds exactly as before.
    from tools.delegation_live_log import (
        create_live_transcripts,
        update_manifest_statuses,
        wrap_progress_callback,
    )

    live_deleg_id, live_writers, live_paths = create_live_transcripts(
        task_list, context
    )
```

然后是本文件里一个很容易被忽略、但极其重要的细节:**在造第一个孩子之前,先把"结果该唤醒谁"记下来**。
因为造孩子会调 `set_current_session_id(child.session_id)`,把会话 id 的 contextvar 与 `os.environ`
双双改成孩子的内部 id;等后面后台派发时再去读就已经晚了。

`tools/delegate_tool.py:2941-2951 @ 863e313`
```python
    # Capture the ORIGINATING session's wake target BEFORE any child agent is
    # constructed: _build_child_agent() -> AIAgent() -> agent_init calls
    # set_current_session_id(child.session_id), which clobbers the
    # HERMES_SESSION_ID ContextVar and os.environ with the subagent's internal
    # id before the background-dispatch code below would read it. The
    # request-scoped chat_id binding (the raw X-Hermes-Session-Id on
    # api_server) is untouched by child construction, so read it here and
    # thread it through the dispatch.
    from tools.async_delegation import _current_origin_session_id

    _origin_wake_sid = _current_origin_session_id()
```

建孩子的循环(**在主线程上串行建完**,不是边跑边建):

`tools/delegate_tool.py:2958-2983 @ 863e313`
```python
    children = []
    for i, t in enumerate(task_list):
        # Per-task role beats top-level; normalise again so unknown
        # per-task values warn and degrade to leaf uniformly.
        effective_role = _normalize_role(t.get("role") or top_role)
        child = _build_child_preserving_parent_tools(
            task_index=i,
            goal=t["goal"],
            context=t.get("context"),
            # Subagents always inherit the parent's toolsets; the model
            # cannot choose or narrow them (no model-facing toolsets arg).
            toolsets=None,
            model=creds["model"],
            max_iterations=effective_max_iter,
            task_count=n_tasks,
            parent_agent=parent_agent,
            override_provider=creds["provider"],
            override_base_url=creds["base_url"],
            override_api_key=creds["api_key"],
            override_api_mode=creds["api_mode"],
            override_request_overrides=creds.get("request_overrides"),
            override_max_tokens=creds.get("max_output_tokens"),
            override_acp_command=creds.get("command"),
            override_acp_args=creds.get("args"),
            role=effective_role,
        )
```

`toolsets=None` 那一行是硬编码的——再次确认:模型无法给孩子选工具。

### 1.5 第 3 步:`_build_child_agent` —— 孩子怎么出生

#### 1.5.1 角色定级:唯一一处降级点

`tools/delegate_tool.py:1236-1245 @ 863e313`
```python
    # ── Role resolution ─────────────────────────────────────────────────
    # Honor the caller's role only when BOTH the kill switch and the
    # child's depth allow it.  This is the single point where role
    # degrades to 'leaf' — keeps the rule predictable.  Callers pass
    # the normalised role (_normalize_role ran in delegate_task) so
    # we only deal with 'leaf' or 'orchestrator' here.
    child_depth = getattr(parent_agent, "_delegate_depth", 0) + 1
    max_spawn = _get_max_spawn_depth()
    orchestrator_ok = _get_orchestrator_enabled() and child_depth < max_spawn
    effective_role = role if (role == "orchestrator" and orchestrator_ok) else "leaf"
```

"唯一一处降级"是有意的:调用方传进来的 role 已经被 `_normalize_role` 洗过(只剩 leaf/orchestrator),
这里只按**全局开关**和**深度**两条硬约束再降一次。规则因此可预测:
`effective_role = orchestrator` ⟺ 调用方要 orchestrator **且** 开关开 **且** `child_depth < max_spawn_depth`。

#### 1.5.2 身份:一个 id 贯穿事件、注册表、file_state、TUI

`tools/delegate_tool.py:1247-1256 @ 863e313`
```python
    # ── Subagent identity (stable across events, 0-indexed for TUI) ─────
    # subagent_id is generated here so the progress callback, the
    # spawn_requested event, and the _active_subagents registry all share
    # one key.  parent_id is non-None when THIS parent is itself a subagent
    # (nested orchestrator -> worker chain).
    subagent_id = f"sa-{task_index}-{_uuid.uuid4().hex[:8]}"
    parent_subagent_id = getattr(parent_agent, "_subagent_id", None)
    tui_depth = max(0, child_depth - 1)  # 0 = first-level child for the UI

    delegation_cfg = _load_config()
```

`tui_depth = child_depth - 1` 是给界面看的(0 = 第一层孩子),`child_depth` 是给策略看的(1 = 第一层孩子)。
两套编号并存,读代码时容易踩。

#### 1.5.3 toolset 求交(详见第 3 节)

#### 1.5.4 凭据:三层优先级 + 一处"别信父 agent 的属性"

优先级是 `delegation.*` 配置覆盖 > 父 agent 继承。

`tools/delegate_tool.py:1376-1382 @ 863e313`
```python
    # Resolve effective credentials: config override > parent inherit
    effective_model = model or parent_agent.model
    effective_provider = override_provider or getattr(parent_agent, "provider", None)
    effective_base_url = override_base_url or parent_agent.base_url
    if not override_base_url:
        effective_base_url = _inherit_parent_base_url(parent_agent, effective_base_url)
    effective_api_key = override_api_key or parent_api_key
```

`_inherit_parent_base_url` 解决的是一个很具体的事故:父 agent 的 `base_url` 属性可能还留着旧配置里的
OpenRouter 地址,而它**实际在用**的 OpenAI 客户端早已指向本地 Ollama。孩子若继承那个属性,
就会拿着本地的假 key 去 OpenRouter 撞 401。

`tools/delegate_tool.py:1166-1173 @ 863e313`
```python
def _inherit_parent_base_url(parent_agent, fallback_base_url: Optional[str]) -> Optional[str]:
    """Return the base URL the parent is actually calling, not a stale attribute.

    ``parent_agent.base_url`` can still carry a leftover OpenRouter URL from an
    old config while the live OpenAI client in ``_client_kwargs`` already points
    at local Ollama. Subagents must inherit the active endpoint or they 401
    against OpenRouter with a dummy/local key.
    """
```

`api_mode`(走哪种线协议:OpenAI 的 chat_completions / Anthropic 的 messages / Codex 的 responses)
**不无脑继承**,这里有三条分支:

`tools/delegate_tool.py:1394-1405 @ 863e313`
```python
    _parent_provider = getattr(parent_agent, "provider", None) or ""
    _effective_provider_norm = (effective_provider or "").strip().lower()
    if override_api_mode is not None:
        effective_api_mode = override_api_mode
    elif _effective_provider_norm in {"nous", "nous-portal", "nousresearch"}:
        from hermes_cli.providers import nous_api_mode

        effective_api_mode = nous_api_mode(effective_model)
    elif effective_provider != _parent_provider:
        effective_api_mode = None  # force re-derivation from provider's defaults
    else:
        effective_api_mode = getattr(parent_agent, "api_mode", None)
```

第二条分支(Nous Portal)是"同一个 provider 内部双线协议"的补丁:`anthropic/*` 走 Messages、
其余走 chat_completions,同 provider 继承会把一个 Hermes/Qwen 子 agent 钉死在父 agent 的 Claude 线上。

#### 1.5.5 `AIAgent(...)`:一次性把所有继承决定摊开

这段是全文件最值得逐行读的 40 行——**它就是"隔离边界"的定义**。

`tools/delegate_tool.py:1509-1531 @ 863e313`
```python
    from agent.delegation_context import delegated_child_context

    with delegated_child_context():
        child = AIAgent(
            base_url=effective_base_url,
            api_key=effective_api_key,
            model=effective_model,
            provider=effective_provider,
            api_mode=effective_api_mode,
            acp_command=effective_acp_command,
            acp_args=effective_acp_args,
            max_iterations=max_iterations,

            reasoning_config=child_reasoning,
            prefill_messages=getattr(parent_agent, "prefill_messages", None),
            fallback_model=parent_fallback,
            enabled_toolsets=child_toolsets,
            disabled_toolsets=child_disabled_toolsets,
            quiet_mode=True,
            ephemeral_system_prompt=child_prompt,
            log_prefix=f"[subagent-{task_index}]",
            platform="subagent",
            skip_context_files=True,
```

`tools/delegate_tool.py:1531-1552 @ 863e313`
```python
            skip_context_files=True,
            skip_memory=True,
            clarify_callback=None,
            thinking_callback=child_thinking_cb,
            session_db=getattr(parent_agent, "_session_db", None),
            parent_session_id=getattr(parent_agent, "session_id", None),
            providers_allowed=child_providers_allowed,
            providers_ignored=child_providers_ignored,
            providers_order=child_providers_order,
            provider_sort=child_provider_sort,
            provider_require_parameters=child_provider_require_parameters,
            provider_data_collection=child_provider_data_collection,
            request_overrides=(
                dict(override_request_overrides or {})
                if override_provider
                else dict(getattr(parent_agent, "request_overrides", {}) or {})
            ),
            openrouter_min_coding_score=child_openrouter_min_coding_score,
            tool_progress_callback=child_progress_cb,
            iteration_budget=None,  # fresh budget per subagent
            **child_optional_kwargs,
        )
```

逐项读:

- `quiet_mode=True` / `log_prefix="[subagent-N]"` / `platform="subagent"` —— 孩子不抢父 agent 的显示。
- `ephemeral_system_prompt=child_prompt` —— **注意这不是"替换"系统提示词,是"追加"**(证据见本节末尾的补注)。
- `skip_context_files=True` / `skip_memory=True` —— 不注入项目上下文文件、不装载 memory 提供方。
- `clarify_callback=None` —— 孩子物理上没有问用户的通道。
- `session_db=parent._session_db` + `parent_session_id=parent.session_id` —— **会话库是共享的**,
  孩子有自己的 `session_id` 但写在同一个库里,并记下父会话。
- `iteration_budget=None` —— 注释写得很直白:**每个子 agent 一份全新预算**。
  于是"父 + 全部子"的总迭代数可以超过父 agent 自己的 `max_iterations`。**没有全局迭代预算。**
- `fallback_model=parent_fallback` —— 继承父 agent 的降级链,孩子也能在限流时换 provider。

**补注:`ephemeral_system_prompt` 是"追加"不是"替换"。** 会话循环把它拼在有效系统提示词后面:

`agent/conversation_loop.py:989-990 @ 863e313`
```python
        if agent.ephemeral_system_prompt:
            effective = (effective + "\n\n" + agent.ephemeral_system_prompt).strip()
```

所以孩子拿到的是「Hermes 完整基座提示词 + 那段聚焦任务说明」,不是一份精简提示词。
这一点在重实现时很容易搞反:如果真的换成精简提示词,孩子会丢掉基座里关于工具用法、
安全约束、输出规范的全部约定。

出生后再补打一批标记:

`tools/delegate_tool.py:1553-1567 @ 863e313`
```python
    child._print_fn = getattr(parent_agent, "_print_fn", None)
    # Now the child exists, its session id can ride on every relayed event
    # (including the spawn_requested below — first emit happens after this).
    child_session_ref["session_id"] = getattr(child, "session_id", "") or ""
    # Set delegation depth so children can't spawn grandchildren
    child._delegate_depth = child_depth
    # Stash the post-degrade role for introspection (leaf if the
    # kill switch or depth bounded the caller's requested role).
    child._delegate_role = effective_role
    # Stash subagent identity for nested-delegation event propagation and
    # for _run_single_child / interrupt_subagent to look up by id.
    child._subagent_id = subagent_id
    child._parent_subagent_id = parent_subagent_id
    child._subagent_goal = goal
    child._parent_turn_id = getattr(parent_agent, "_current_turn_id", "") or ""
```

#### 1.5.6 挂到父 agent 的中断链上 + 触发 `subagent_start` 钩子

`tools/delegate_tool.py:1584-1600 @ 863e313`
```python
    # Register child for interrupt propagation
    if hasattr(parent_agent, "_active_children"):
        lock = getattr(parent_agent, "_active_children_lock", None)
        if lock:
            with lock:
                parent_agent._active_children.append(child)
        else:
            parent_agent._active_children.append(child)

    # Announce the spawn immediately — the child may sit in a queue
    # for seconds if max_concurrent_children is saturated, so the TUI
    # wants a node in the tree before run starts.
    if child_progress_cb:
        try:
            child_progress_cb("subagent.spawn_requested", preview=goal)
        except Exception as exc:
            logger.debug("spawn_requested relay failed: %s", exc)
```

`tools/delegate_tool.py:1602-1615 @ 863e313`
```python
    try:
        from hermes_cli.lifecycle import invoke_hook as _invoke_hook
        _invoke_hook(
            "subagent_start",
            parent_session_id=getattr(parent_agent, "session_id", None),
            parent_turn_id=getattr(parent_agent, "_current_turn_id", "") or "",
            parent_subagent_id=parent_subagent_id,
            child_session_id=getattr(child, "session_id", None),
            child_subagent_id=subagent_id,
            child_role=effective_role,
            child_goal=goal,
        )
    except Exception:
        logger.debug("subagent_start hook invocation failed", exc_info=True)
```

父 agent 侧的中断传播就靠 `_active_children` 这张表:

`run_agent.py:3149-3158 @ 863e313`
```python
        # Propagate interrupt to any running child agents (subagent delegation)
        with self._active_children_lock:
            children_copy = list(self._active_children)
        for child in children_copy:
            try:
                if hard_cancel:
                    request_hard_interrupt(child, message)
                else:
                    child.interrupt(message)
            except Exception as e:
```

### 1.6 第 4 步:`_run_single_child` —— 孩子跑起来

#### 1.6.1 先租一把凭据

`tools/delegate_tool.py:1995-2005 @ 863e313`
```python
    child_pool = getattr(child, "_credential_pool", None)
    leased_cred_id = None
    if child_pool is not None:
        leased_cred_id = child_pool.acquire_lease()
        if leased_cred_id is not None:
            try:
                leased_entry = child_pool.current()
                if leased_entry is not None and hasattr(child, "_swap_credential"):
                    child._swap_credential(leased_entry)
            except Exception as exc:
                logger.debug("Failed to bind child to leased credential: %s", exc)
```

#### 1.6.2 心跳线程:让父 agent 在"等孩子"期间看起来还活着

问题场景:gateway 有一个"多久没活动就杀掉 agent"的超时。父 agent 一进 `delegate_task` 就不再产生活动,
于是十分钟后自己被杀,孩子还在跑。心跳线程每 30 秒把孩子的活动情况"盖"到父 agent 上。

`tools/delegate_tool.py:2022-2036 @ 863e313`
```python
    def _heartbeat_loop():
        while not _heartbeat_stop.wait(_HEARTBEAT_INTERVAL):
            if parent_agent is None:
                continue
            touch = getattr(parent_agent, "_touch_activity", None)
            if not touch:
                continue
            # Pull detail from the child's own activity tracker
            desc = f"delegate_task: subagent {task_index} working"
            try:
                child_summary = child.get_activity_summary()
                child_tool = child_summary.get("current_tool")
                child_iter = child_summary.get("api_call_count", 0)
                child_max = child_summary.get("max_iterations", 0)
                child_activity_ts = child_summary.get("last_activity_ts")
```

心跳同时兼任**停滞检测**:三个信号(迭代号、当前工具名、最后活动时间戳)全部不动才算一个 stale 周期。

`tools/delegate_tool.py:2044-2060 @ 863e313`
```python
                iter_advanced = child_iter > _last_seen_iter[0]
                tool_changed = child_tool != _last_seen_tool[0]
                activity_advanced = (
                    child_activity_ts is not None
                    and (
                        _last_seen_activity_ts[0] is None
                        or child_activity_ts > _last_seen_activity_ts[0]
                    )
                )
                if iter_advanced or tool_changed or activity_advanced:
                    _last_seen_iter[0] = child_iter
                    _last_seen_tool[0] = child_tool
                    if child_activity_ts is not None:
                        _last_seen_activity_ts[0] = child_activity_ts
                    _stale_count[0] = 0
                else:
                    _stale_count[0] += 1
```

超过阈值时它**不杀孩子,而是停止心跳**——把判决权交还给 gateway 的不活动超时。

`tools/delegate_tool.py:2067-2080 @ 863e313`
```python
                stale_limit = (
                    _HEARTBEAT_STALE_CYCLES_IN_TOOL
                    if child_tool
                    else _HEARTBEAT_STALE_CYCLES_IDLE
                )
                if _stale_count[0] >= stale_limit:
                    logger.warning(
                        "Subagent %d appears stale (no progress for %d "
                        "heartbeat cycles, tool=%s) — stopping heartbeat",
                        task_index,
                        _stale_count[0],
                        child_tool or "<none>",
                    )
                    break  # stop touching parent, let gateway timeout fire
```

阈值分两档,依据是"孩子当前是否在某个工具里":

`tools/delegate_tool.py:748-750 @ 863e313`
```python
_HEARTBEAT_STALE_CYCLES_IDLE = 15  # 15 * 30s = 450s idle between turns → stale
_HEARTBEAT_STALE_CYCLES_IN_TOOL = 40  # 40 * 30s = 1200s stuck on same tool → stale
DEFAULT_TOOLSETS = ["terminal", "file", "web"]
```

#### 1.6.3 task_id 与 cwd 种子

孩子把自己的 `subagent_id` 当 `task_id` 用(与 file_state、注册表、TUI 事件共用一把钥匙),
并把父 agent 当前的工作目录**种**进自己的 cwd 记录里。

`tools/delegate_tool.py:2143-2158 @ 863e313`
```python
        import uuid as _uuid

        child_task_id = _subagent_id or f"subagent-{task_index}-{_uuid.uuid4().hex[:8]}"
        parent_task_id = getattr(parent_agent, "_current_task_id", None)
        # Seed the child's session-cwd record from the parent's (cwd rearch):
        # children share the parent's container, and today they inherit the
        # parent's live env.cwd implicitly. Seeding at spawn preserves that
        # starting directory while keeping the child's subsequent `cd`s
        # isolated in its own record (a child's cd no longer bleeds back into
        # the parent once readers flip to the record store).
        try:
            from tools.terminal_tool import get_session_cwd, record_session_cwd

            record_session_cwd(child_task_id, get_session_cwd(parent_task_id))
        except Exception as e:
            logger.debug("Child cwd seed failed: %s", e)
```

#### 1.6.4 真正的执行:1 worker 的守护线程池

`tools/delegate_tool.py:2164-2180 @ 863e313`
```python
        # Run child with an optional hard timeout (off by default —
        # result(timeout=None) blocks until the child finishes). Stuck-child
        # protection comes from the heartbeat staleness monitor instead.
        child_timeout = _get_child_timeout()
        # Daemon worker (tools.daemon_pool): a timed-out child is abandoned
        # below; a stdlib non-daemon worker would then block interpreter
        # exit at atexit-join time if the child never unwinds.
        from tools.daemon_pool import DaemonThreadPoolExecutor
        _timeout_executor = DaemonThreadPoolExecutor(
            max_workers=1,
            # Install a non-interactive approval callback in the worker thread
            # so dangerous-command prompts from the subagent don't fall back to
            # input() and deadlock the parent's prompt_toolkit TUI.
            # Callback (deny vs approve) is governed by delegation.subagent_auto_approve.
            initializer=_set_subagent_approval_cb,
            initargs=(_get_subagent_approval_callback(),),
        )
```

`tools/delegate_tool.py:2196-2213 @ 863e313`
```python
        def _run_with_thread_capture():
            _worker_thread_holder["t"] = threading.current_thread()
            from agent.delegation_context import delegated_child_context

            with delegated_child_context(str(getattr(child, "session_id", "") or "")):
                return child.run_conversation(
                    user_message=goal,
                    task_id=child_task_id,
                    stream_callback=_relay_child_text,
                )

        _child_context = contextvars.copy_context()
        _child_future = _timeout_executor.submit(
            _child_context.run,
            _run_with_thread_capture,
        )
        try:
            result = _child_future.result(timeout=child_timeout)
```

三个设计点:

1. **`contextvars.copy_context()`**:孩子在另一个线程跑,但会话 key、审批上下文等 contextvar
   必须跟过去,否则孩子的审批请求会找不到会话队列。
2. **`DaemonThreadPoolExecutor`**:标准库的 `ThreadPoolExecutor` 会在 `atexit` 里**无条件 join**
   所有 worker,一个卡死的孩子就能让解释器永远退不出去。这个子类把 worker 设为 daemon 且不注册进
   `_threads_queues`(证据见紧接本列表后的引文)。
3. **`result(timeout=child_timeout)`**,而 `child_timeout` 默认是 `None`,即**默认无墙钟超时**。

守护池的理由,原文写得比任何转述都清楚:

`tools/daemon_pool.py:1-10 @ 863e313`
```python
"""Shared daemon-thread ThreadPoolExecutor.

Stdlib ``ThreadPoolExecutor`` workers are non-daemon AND are registered in
``concurrent.futures.thread._threads_queues``, whose atexit hook
(``_python_exit``) joins every worker unconditionally — even after
``shutdown(wait=False)``.  A single wedged worker (tool blocked on network
I/O, hung provider daemon, stuck subagent) therefore blocks interpreter
exit forever.  This is the root cause of multi-minute CLI exits on long
sessions: every abandoned concurrent-tool batch leaves workers that the
exit hook insists on joining.
```

#### 1.6.5 结果整形

`tools/delegate_tool.py:2330-2350 @ 863e313`
```python
        summary = result.get("final_response") or ""
        completed = result.get("completed", False)
        interrupted = result.get("interrupted", False)
        api_calls = result.get("api_calls", 0)

        # The child emits the literal "(empty)" sentinel (see run_agent.py) when
        # it gives up after repeated empty-LLM-response retries — typically a
        # transport bug (misrouted provider, adapter returning empty
        # ChatCompletion, etc.). Treat it as a failure so the parent surfaces
        # it instead of silently accepting zero-content "success".
        _empty_sentinel = summary.strip() == "(empty)"

        if interrupted:
            status = "interrupted"
        elif summary and not _empty_sentinel:
            # A summary means the subagent produced usable output.
            # exit_reason ("completed" vs "max_iterations") already
            # tells the parent *how* the task ended.
            status = "completed"
        else:
            status = "failed"
```

`(empty)` 这个哨兵值来自 `run_agent`:模型连续返回空内容、重试耗尽后写下的字面量。
这里把它当失败处理,免得父 agent 收到一个"成功但没内容"的假摘要。

还有一处跨 agent 的文件一致性提醒——**如果孩子改了父 agent 之前读过的文件,就在摘要尾巴上贴一条警告**:

`tools/delegate_tool.py:2441-2452 @ 863e313`
```python
        # Cross-agent file-state reminder.  If this subagent wrote any
        # files the parent had already read, surface it so the parent
        # knows to re-read before editing — the scenario that motivated
        # the registry.  We check writes by ANY non-parent task_id (not
        # just this child's), which also covers transitive writes from
        # nested orchestrator→worker chains.
        try:
            if parent_task_id and parent_reads_snapshot:
                sibling_writes = file_state.writes_since(
                    parent_task_id, wall_start, parent_reads_snapshot
                )
                if sibling_writes:
```

### 1.7 第 5 步:结果怎么回到父 agent

`_execute_and_aggregate()` 是同步与后台**共用**的那段:它既跑单任务也跑批量,join 完所有孩子,
做一次收尾,返回一个合并 dict。

单任务不进线程池:

`tools/delegate_tool.py:3007-3011 @ 863e313`
```python
        if n_tasks == 1:
            # Single task -- run directly (no thread pool overhead)
            _i, _t, child = children[0]
            result = _run_single_child(_i, _t["goal"], child, parent_agent)
            results.append(result)
```

批量进线程池,并且**不用 `as_completed`**,而是 0.5 秒一轮的 `wait(FIRST_COMPLETED)`,
为的是能在轮询间隙检查父 agent 是否被中断:

`tools/delegate_tool.py:3035-3045 @ 863e313`
```python
                # Poll futures with interrupt checking.  as_completed() blocks
                # until ALL futures finish — if a child agent gets stuck,
                # the parent blocks forever even after interrupt propagation.
                # Instead, use wait() with a short timeout so we can bail
                # when the parent is interrupted.
                # Map task_index -> child agent, so fabricated entries for
                # still-pending futures can carry the correct _delegate_role.
                _child_by_index = {i: child for (i, _, child) in children}

                pending = set(futures.keys())
                while pending:
```

父 agent 中断时:已完成的收结果,没完成的**伪造**一条 `status="interrupted"` 的条目,然后 break。

`tools/delegate_tool.py:3070-3084 @ 863e313`
```python
                            else:
                                entry = {
                                    "task_index": idx,
                                    "status": "interrupted",
                                    "summary": None,
                                    "error": "Parent agent interrupted — child did not finish in time",
                                    "api_calls": 0,
                                    "duration_seconds": 0,
                                    "_child_role": getattr(
                                        _child_by_index.get(idx), "_delegate_role", None
                                    ),
                                }
                            results.append(entry)
                            completed_count += 1
                        break
```

收尾三件事(摘要裁剪 → memory → 钩子 + 成本汇总),统一在 `_finalize_child_results` 里,
并且**用一把父 agent 级的锁串行化**——因为嵌套编排时可能有多个批次同时在给同一个父 agent 收尾。

`tools/delegate_tool.py:2668-2679 @ 863e313`
```python
def _finalize_child_results(
    results: List[Dict[str, Any]],
    task_list: List[Dict[str, Any]],
    children: List[tuple[int, Dict[str, Any], Any]],
    parent_agent,
) -> None:
    """Apply host-owned summary, memory, hook, and cost contracts once."""
    with _parent_finalization_lock(parent_agent):
        _apply_summary_budget(results, parent_agent)
        child_by_index = {index: child for index, _task, child in children}

        if parent_agent and getattr(parent_agent, "_memory_manager", None):
```

孩子的花费被**折算回父 agent 的会话成本**(否则底部状态栏会严重低估子 agent 密集的会话):

`tools/delegate_tool.py:2734-2745 @ 863e313`
```python
        if children_cost_total > 0.0:
            try:
                current = float(
                    getattr(parent_agent, "session_estimated_cost_usd", 0.0) or 0.0
                )
                parent_agent.session_estimated_cost_usd = current + children_cost_total
                if getattr(parent_agent, "session_cost_source", "none") in {
                    None,
                    "",
                    "none",
                }:
                    parent_agent.session_cost_source = "subagent"
```

最后分两条出口。

**出口一:同步路径。** 直接把合并 dict 序列化成 JSON 字符串返回给工具执行器。

`tools/delegate_tool.py:3409-3410 @ 863e313`
```python
    # ----- Synchronous path -----
    return json.dumps(_execute_and_aggregate(), ensure_ascii=False)
```

**出口二:后台路径。** 把 `_execute_and_aggregate` 当作 runner 交给异步派发,立刻返回一个句柄。
注意 `note` 字段是写给模型看的**行为指令**("别等、别轮询,继续干活")——harness 用工具返回值
直接管教模型的行为,这一手很值得抄。

`tools/delegate_tool.py:3358-3379 @ 863e313`
```python
        if dispatch.get("status") == "dispatched":
            n = len(_goals)
            note = (
                "Subagent is running in the background. You and the user can "
                "keep working; its full result re-enters the conversation as a "
                "new message when it finishes. Do not wait or poll — just "
                "continue."
                if n == 1 else
                f"{n} subagents are running in parallel in the background. You "
                f"and the user can keep working; they wait on each other and "
                f"their consolidated results re-enter the conversation as a "
                f"single message once ALL of them finish. Do not wait or poll "
                f"— just continue."
            )
            payload = {
                "status": "dispatched",
                "mode": "background",
                "count": n,
                "delegation_id": dispatch["delegation_id"],
                "goals": _goals,
                "note": note,
            }
```

后台路径还有两处降级,都很务实。

**降级一:会话本身收不了异步结果**(无状态 HTTP 请求、一次性 Kanban worker)→ 改为同步执行,
并在结果里附一句"你要的后台在这个会话里不可用,已经同步跑完了"。

`tools/delegate_tool.py:3222-3236 @ 863e313`
```python
        if not _async_ok:
            logger.info(
                "delegate_task: async delivery unsupported on this session "
                "runtime; running the batch synchronously instead."
            )
            _sync_result = _execute_and_aggregate()
            if isinstance(_sync_result, dict):
                _sync_result["note"] = (
                    "background=true is not available in this session — it cannot "
                    "receive a detached subagent result after the turn ends (a "
                    "one-shot runner such as `hermes -z`, a cron job, a Kanban "
                    "worker, or a stateless HTTP endpoint). The subagent(s) ran "
                    "SYNCHRONOUSLY and the result is included above."
                )
            return json.dumps(_sync_result, ensure_ascii=False)
```

**降级二:异步池满** → 同样退回同步(这条正是 7.3 ■1 的现场)。

`tools/delegate_tool.py:3390-3407 @ 863e313`
```python
        # Pool at capacity / schedule failure — children are still attached
        # (we detach above only on the parent list, but the async unit was
        # never accepted, so re-attaching isn't needed: we just run inline).
        logger.info(
            "delegate_task: async pool at capacity (%s); running the whole "
            "batch synchronously instead.",
            dispatch.get("error", "rejected"),
        )
        _cap_result = _execute_and_aggregate()
        if isinstance(_cap_result, dict):
            _cap_result["note"] = (
                "The background delegation pool was at capacity "
                "(delegation.max_concurrent_children), so the subagent(s) ran "
                "SYNCHRONOUSLY and the result is included above. Raise "
                "delegation.max_concurrent_children in config.yaml to allow "
                "more concurrent background delegations."
            )
        return json.dumps(_cap_result, ensure_ascii=False)
```

### 1.8 一张走法总览(非源码块)

```text
模型 tool_call
  └─ run_agent._dispatch_delegate_task        background = (深度==0)
       └─ delegate_task()
            ├─ 9 道前置闸(暂停/深度/宽度/凭据/参数)
            ├─ create_live_transcripts()      每任务一个 tail -f 日志
            ├─ _current_origin_session_id()   ← 必须在造孩子之前读
            ├─ for each task:  _build_child_preserving_parent_tools()
            │      └─ _build_child_agent()
            │           ├─ 角色定级(唯一降级点)
            │           ├─ toolset 求交 + 黑名单裁剪
            │           ├─ 凭据/api_mode/降级链解析
            │           ├─ AIAgent(...)  ← 隔离边界在这 40 行里
            │           ├─ 打标记(_delegate_depth/_subagent_id/…)
            │           ├─ 挂进 parent._active_children(中断链)
            │           └─ hook: subagent_start
            └─ _execute_and_aggregate()
                 ├─ n==1 → 直接 _run_single_child
                 ├─ n>1  → DaemonThreadPoolExecutor(max_children) + wait(0.5s) 轮询
                 │            └─ 每个孩子内部再开一个 1-worker 守护池跑 run_conversation
                 ├─ _finalize_child_results()   摘要预算 / memory / subagent_stop / 成本汇总
                 └─ 关闭实时转写 + 返回合并 dict
       ├─ 同步 → json.dumps(合并 dict)             (编排者子 agent 走这条)
       └─ 后台 → dispatch_async_delegation_batch() (顶层模型走这条,立刻返回句柄)
```

---

## 2. 隔离边界:共享什么、不共享什么

### 2.1 总表(索引;逐条证据见 2.2 起)

| 维度 | 共享? | 依据(节) |
|---|---|---|
| 对话历史 | **不共享**,孩子是全新会话 | 1.5.5 |
| 系统提示词 | **共享基座** + 追加任务段 | 1.5.5 |
| 项目上下文文件 / memory 装载 | 不共享 | 1.5.5 |
| 会话数据库 | **共享同一个 `session_db`**,孩子有自己的 session_id | 1.5.5 |
| 进程 | **共享**(同一个 Python 进程,孩子是线程) | 1.6.4 |
| 文件系统 / 终端容器 | **共享**(孩子的 task_id 被折叠回 `default`) | 2.3 |
| cwd 记录 | 各自一份,出生时从父 agent 种一次 | 1.6.3 |
| file_state 读写台账 | 各自一个 bucket,跨 bucket 有"别人改了你读过的文件"提醒 | 1.6.5 |
| 凭据 / API key | **共享**(或按配置整体替换),凭据池按 provider 归属共享 | 2.4 |
| 审批与安全策略 | **共享且不可绕过**,仅"交互式提问"这一层被替换 | 2.2 |
| Kanban 调度身份 | **显式失效**(专门做了隔离) | 2.5 |
| 迭代预算 | **不共享,各自全新一份**;无全局总预算 | 1.5.5 / 6.4 |
| 上下文窗口预算 | 单向:孩子的摘要按父 agent**剩余**窗口裁剪 | 5.5 |
| 花费 | 汇总回父 agent | 1.7 |

### 2.2 审批与安全策略:**子 agent 不能绕过父 agent 的闸门**

这是本轮被点名要专查的一条。结论:**不能绕过**;能被改的只有"没人可问时怎么办"这一层默认答案。

#### 2.2.1 问题的由来

子 agent 跑在 worker 线程里。CLI 的交互式审批回调存在 `tools/terminal_tool.py` 的 **TLS** 里,
worker 线程继承不到。没有回调时,危险命令审批会回落到 `input()`——而 `input()` 在 worker 线程里
会和父 agent 那个占着 stdin 的 prompt_toolkit TUI **死锁**。

`tools/delegate_tool.py:62-75 @ 863e313`
```python
# Subagents run inside a ThreadPoolExecutor worker. The CLI's interactive
# approval callback is stored in tools/terminal_tool.py's threading.local(),
# so worker threads do NOT inherit it. Without a callback,
# prompt_dangerous_approval() falls back to input() from the worker thread,
# which deadlocks against the parent's prompt_toolkit TUI that owns stdin.
#
# Fix: install a non-interactive callback into every subagent worker thread
# via ThreadPoolExecutor(initializer=_set_subagent_approval_cb, initargs=(cb,)).
# The callback is chosen by the `delegation.subagent_auto_approve` config:
#   false (default) → _subagent_auto_deny (safe; matches leaf tool blocklist)
#   true            → _subagent_auto_approve (opt-in YOLO for cron/batch)
# Both emit a logger.warning for audit; gateway sessions are unaffected
# because they resolve approvals via tools/approval.py's per-session queue,
# not through these TLS callbacks.
```

#### 2.2.2 修法:给 worker 线程装一个非交互回调

`tools/delegate_tool.py:2172-2180 @ 863e313`
```python
        _timeout_executor = DaemonThreadPoolExecutor(
            max_workers=1,
            # Install a non-interactive approval callback in the worker thread
            # so dangerous-command prompts from the subagent don't fall back to
            # input() and deadlock the parent's prompt_toolkit TUI.
            # Callback (deny vs approve) is governed by delegation.subagent_auto_approve.
            initializer=_set_subagent_approval_cb,
            initargs=(_get_subagent_approval_callback(),),
        )
```

`tools/delegate_tool.py:103-114 @ 863e313`
```python
def _get_subagent_approval_callback():
    """Return the callback to install into subagent worker threads.

    Config key: delegation.subagent_auto_approve (bool, default False).
    Reads via the same _load_config() path as the rest of delegate_task so
    priority is config.yaml > (no env override for this knob) > default.
    """
    cfg = _load_config()
    val = cfg.get("subagent_auto_approve", False)
    if is_truthy_value(val):
        return _subagent_auto_approve
    return _subagent_auto_deny
```

默认 `_subagent_auto_deny` 返回 `"deny"`——**比父 agent 更严**,不是更松。

`tools/delegate_tool.py:76-87 @ 863e313`
```python
def _subagent_auto_deny(command: str, description: str, **kwargs) -> str:
    """Auto-deny dangerous commands in subagent threads (safe default).

    Returns 'deny' so the subagent sees a refusal it can recover from, and
    never calls input() (which would deadlock the parent TUI).
    """
    logger.warning(
        "Subagent auto-denied dangerous command: %s (%s). "
        "Set delegation.subagent_auto_approve: true to allow.",
        command, description,
    )
    return "deny"
```

#### 2.2.3 为什么"绕不过":硬闸在回调之前

`delegation.subagent_auto_approve: true` 只影响审批链**最后**那一段。前面几道闸是读全局配置的
纯函数,与是不是子 agent 无关,而且都排在 yolo 旁路**之前**:

`tools/approval.py:3441-3463 @ 863e313`
```python
    # Hardline floor: commands with no recovery path (rm -rf /, mkfs, dd
    # to raw device, shutdown/reboot, fork bomb, kill -1) are blocked
    # unconditionally, BEFORE the yolo bypass.  Opting into yolo is
    # trusting the agent with your files and services, not trusting it
    # to wipe the disk or power the box off.
    is_hardline, hardline_desc = detect_hardline_command(command)
    if is_hardline:
        logger.warning("Hardline block: %s (command: %s)", hardline_desc, command[:200])
        return _hardline_block_result(hardline_desc, command)

    # User-defined deny rules (approvals.deny in config.yaml): like the
    # hardline floor, these fire BEFORE the yolo bypass — a deny rule is the
    # user saying "never, even under yolo".
    deny_pattern = _match_user_deny_rule(command)
    if deny_pattern is not None:
        logger.warning("User deny rule %r blocked command: %s",
                       deny_pattern, command[:200])
        return _user_deny_block_result(deny_pattern)

    # --yolo: bypass all approval prompts. Gateway /yolo is session-scoped;
    # CLI --yolo remains process-scoped via the env var for local use.
    if _YOLO_MODE_FROZEN or is_current_session_yolo_enabled():
        return {"approved": True, "message": None}
```

即:**hardline 兜底**(`rm -rf /`、`mkfs`、关机、fork 炸弹……)与 **`approvals.deny` 用户黑名单**
在任何旁路之前触发,子 agent 一样撞墙。`subagent_auto_approve` 能改的只有"危险模式命中之后、
需要人点头"的那一步。

#### 2.2.4 gateway 会话根本不走这个回调

在 gateway(Telegram/Discord/Slack/API server)里,审批走的是 `tools/approval.py` 的
**按会话排队**机制,而它排在 CLI 回调分支**之前**:

`tools/approval.py:3212-3220 @ 863e313`
```python
    if approval_callback is None:
        try:
            from tools.terminal_tool import _get_approval_callback
            approval_callback = _get_approval_callback()
        except Exception:
            approval_callback = None

    is_cli = _is_interactive_cli()
    is_gateway = _is_gateway_approval_context()
```

`tools/approval.py:3260-3270 @ 863e313`
```python
    if is_gateway or env_var_enabled("HERMES_EXEC_ASK"):
        # Interactive gateway round-trip when a notify callback is
        # registered for this session (Discord/Telegram/Slack embed +
        # buttons, same mechanism as check_dangerous_command). Blocks the
        # agent thread until the user answers; the agent never sees
        # "approval_required" on this path — it gets a definitive
        # approved/BLOCKED outcome.
        notify_cb = None
        with _lock:
            notify_cb = _gateway_notify_cbs.get(session_key)

```

孩子的会话 key 是通过 `contextvars.copy_context()` 跟过去的(1.6.4),所以孩子的危险命令
**会真的弹到用户手机上**。

#### 2.2.5 一个继承方向常被忽略:会话级"本次批准"缓存也继承

`tools/approval.py:3208-3210 @ 863e313`
```python
    session_key = get_current_session_key()
    if is_approved(session_key, pattern_key):
        return {"approved": True, "message": None}
```

`get_current_session_key()` 在孩子这边解析到的是**父会话**的 key(contextvar 拷过去了),
于是父 agent 之前对某个模式点过的 "session / always",**孩子直接享用**。
这是设计上说得通的(同一个人同一次会话),但重实现时要意识到:它是一条**放松**方向的继承。

#### 2.2.6 判据(可复现)

```verify
cd /home/user/hermes-agent && grep -n "_match_user_deny_rule\|detect_hardline_command\|_YOLO_MODE_FROZEN" tools/approval.py | sed -n '1,20p'
```
读法:凡 `_match_user_deny_rule` / `detect_hardline_command` 的调用点都出现在同一函数中
`_YOLO_MODE_FROZEN` 判断之前,即"用户黑名单与硬底线先于一切旁路"。

**搜索面(负结论:"`delegate_tool.py` 里没有第二条审批旁路")**:

```verify
cd /home/user/hermes-agent && grep -niE "yolo|approv|deny|allowlist|permanent" tools/delegate_tool.py
```

实测 **31 行命中**,分四类、无第五类:
(a) 本节讲的那套子 agent 回调(第 43、60–114、2174–2179 行);
(b) `_blocked_toolsets_for_role` 的注释里把黑名单 toolset 叫作 "deny toolsets"(第 922、926、1297 行)
    —— 是工具集裁剪,不是审批;
(c) 第 3185 行 `from tools.approval import get_current_session_key`,只**读**会话 key,不改审批状态;
(d) 第 3248、3259 行是解释"为什么不能在这里读 approval contextvar"的注释。
文件里**没有**对 `approve_session` / `approve_permanent` / `_YOLO_MODE_FROZEN` / `set_yolo` /
`save_permanent_allowlist` 的任何调用或赋值——即子 agent 侧不写入任何审批状态,
它只能在既定审批链的**最后一环**回答 deny 或 once。

### 2.3 文件系统:**孩子和父 agent 在同一个容器里**

这条最反直觉。孩子确实拿到了自己的 `task_id`,但终端层**故意**把它折叠回 `default`:

`tools/terminal_tool.py:1274-1284 @ 863e313`
```python
def _resolve_container_task_id(task_id: Optional[str]) -> str:
    """
    Map a tool-call ``task_id`` to the container/sandbox key used by
    ``_active_environments``.

    The top-level agent passes ``task_id=None`` and lands on ``"default"``.
    ``delegate_task`` children pass their own subagent ID so that
    file-state tracking, the active-subagents registry, and TUI events stay
    distinct per child -- but we deliberately collapse that ID back to
    ``"default"`` here so subagents share the parent's long-lived container
    (one bash, one /workspace, one set of installed packages).
```

`tools/terminal_tool.py:1298-1306 @ 863e313`
```python
    _ISOLATION_KEYS = frozenset({
        "docker_image", "modal_image", "singularity_image",
        "daytona_image", "env_type",
    })
    if task_id and task_id in _task_env_overrides:
        overrides = _task_env_overrides[task_id]
        if set(overrides.keys()) & _ISOLATION_KEYS:
            return task_id
    return "default"
```

所以:**一个 bash、一个 /workspace、一套已装的包**,父子共用。孩子写的文件父 agent 立刻看得到
(这正是 1.6.5 那条"重新读一遍再改"提醒存在的原因)。

孩子**私有**的只有 cwd 记录:出生时从父 agent 种一份,之后孩子自己 `cd` 不会回灌给父 agent。

`tools/delegate_tool.py:2147-2156 @ 863e313`
```python
        # Seed the child's session-cwd record from the parent's (cwd rearch):
        # children share the parent's container, and today they inherit the
        # parent's live env.cwd implicitly. Seeding at spawn preserves that
        # starting directory while keeping the child's subsequent `cd`s
        # isolated in its own record (a child's cd no longer bleeds back into
        # the parent once readers flip to the record store).
        try:
            from tools.terminal_tool import get_session_cwd, record_session_cwd

            record_session_cwd(child_task_id, get_session_cwd(parent_task_id))
```

### 2.4 凭据:共享池,按 provider / 端点身份归属

`tools/delegate_tool.py:3418-3435 @ 863e313`
```python
    """Resolve a credential pool for the child agent.

    Rules:
    1. Same provider as the parent -> share the parent's pool so cooldown state
       and rotation stay synchronized.
    2. Different provider -> try to load that provider's own pool.
    3. No pool available -> return None and let the child keep the inherited
       fixed credential behavior.

    Custom endpoints are a special case: every direct ``delegation.base_url``
    runtime collapses to ``provider="custom"``, so bare provider equality would
    treat two *different* custom endpoints as interchangeable and let the child
    inherit the parent's pool. Leasing from that pool then overwrites the
    child's delegated ``base_url`` with the parent's endpoint (issue #7833).
    We therefore resolve custom runtimes by endpoint identity (the
    ``custom:<name>`` pool key derived from the base_url) and only share the
    parent's pool when both resolve to the *same* custom endpoint.
    """
```

值得抄的是"自定义端点"那一支:所有直连 `delegation.base_url` 的运行时都会塌缩成
`provider="custom"`,单看 provider 字符串会把**两个不同的自建端点**当成可互换的,
于是孩子从父 agent 的池里租到一把凭据,顺带把自己的 `base_url` 覆盖成父 agent 的端点。
修法是改用"端点身份"(`custom:<name>` 池键)比较。

`tools/delegate_tool.py:3445-3455 @ 863e313`
```python
    if effective_provider == "custom":
        try:
            from agent.credential_pool import get_custom_provider_pool_key, load_pool

            child_key = get_custom_provider_pool_key(effective_base_url)
            if child_key is None:
                # Unregistered endpoint (raw delegation.base_url with no
                # matching custom_providers entry) -> no shared pool exists.
                # Keep the child's fixed delegated credential rather than
                # risk inheriting the parent's custom endpoint.
                return None
```

### 2.5 Kanban 调度身份:**显式失效**,而且是用 contextvar 而非改 env

场景:父 Hermes 进程本身可能就是一个 Kanban 看板的 worker,环境里有 `HERMES_KANBAN_TASK` 等变量。
孩子跑在同一个进程里,如果照单全收,一个不相干的子 agent 就能把 worker 的任务标记完成、覆盖真实结果。

`agent/delegation_context.py:97-105 @ 863e313`
```python
def is_dispatcher_owned_worker_context() -> bool:
    """Return True only when this execution owns the dispatcher's Kanban task.

    The single predicate every ``HERMES_KANBAN_*`` identity gate should use
    before trusting those vars.  False for delegate_task children and for cron
    jobs fired in-process from a worker.
    """
    if _DELEGATED_CHILD_CONTEXT.get():
        return False
```

为什么用 contextvar 而不是清 `os.environ`——理由写得很好,值得抄:

`agent/delegation_context.py:85-88 @ 863e313`
```python
    Scoped via ContextVar rather than by clearing ``os.environ``: the env is
    process-global and shared with the worker's own claim heartbeat, the
    gateway's Kanban watchers, and concurrent cron jobs on the parallel pool, so
    mutating it would starve the worker's claim and race those readers.
```

跨进程边界(execute_code 的沙箱要 fork)时,再把标记落成一个环境变量并擦掉 Kanban 变量:

`agent/delegation_context.py:133-139 @ 863e313`
```python
def scrub_kanban_env(env: Mapping[str, str] | MutableMapping[str, str]) -> dict[str, str]:
    """Return *env* with dispatcher-only Kanban variables removed."""
    cleaned = dict(env)
    for key in KANBAN_ENV_KEYS:
        cleaned.pop(key, None)
    cleaned[DELEGATED_CHILD_ENV_MARKER] = "1"
    return cleaned
```

---

## 3. 工具集裁剪:子集,由**父 agent + 角色**决定,模型无权参与

### 3.1 黑名单(5 个工具,写死)

`tools/delegate_tool.py:47-56 @ 863e313`
```python
# Tools that children must never have access to
DELEGATE_BLOCKED_TOOLS = frozenset(
    [
        "delegate_task",  # no recursive delegation
        "clarify",  # no user interaction
        "memory",  # no writes to shared MEMORY.md
        "send_message",  # no cross-platform side effects
        "cronjob",  # no scheduling more work in the parent's name
    ]
)
```

### 3.2 孩子的 toolset 从哪来:四条分支

`tools/delegate_tool.py:1262-1293 @ 863e313`
```python
    parent_enabled = getattr(parent_agent, "enabled_toolsets", None)
    if parent_enabled is not None:
        parent_toolsets = set(parent_enabled)
    elif parent_agent and hasattr(parent_agent, "valid_tool_names"):
        # enabled_toolsets is None (all tools) — derive from loaded tool names
        import model_tools

        parent_toolsets = {
            ts
            for name in parent_agent.valid_tool_names
            if (ts := model_tools.get_toolset_for_tool(name)) is not None
        }
    else:
        parent_toolsets = set(DEFAULT_TOOLSETS)

    if toolsets:
        # Intersect with parent — subagent must not gain tools the parent lacks.
        # Expand composite toolsets (e.g. hermes-cli) so that individual
        # toolset names (e.g. web, terminal) are recognised during intersection.
        expanded_parent = _expand_parent_toolsets(parent_toolsets)
        child_toolsets = [t for t in toolsets if t in expanded_parent]
        if _get_inherit_mcp_toolsets():
            child_toolsets = _preserve_parent_mcp_toolsets(
                child_toolsets, parent_toolsets
            )
        child_toolsets = _strip_blocked_tools(child_toolsets)
    elif parent_agent and parent_enabled is not None:
        child_toolsets = _strip_blocked_tools(parent_enabled)
    elif parent_toolsets:
        child_toolsets = _strip_blocked_tools(sorted(parent_toolsets))
    else:
        child_toolsets = _strip_blocked_tools(DEFAULT_TOOLSETS)
```

关键点:

- `enabled_toolsets is None` 在这套代码里表示"全开",不是"没有"。所以要从父 agent
  **实际加载的工具名**反查 toolset,否则孩子会被误判成"父 agent 什么都没有"。
- 显式传了 `toolsets` 时做**求交**:`[t for t in toolsets if t in expanded_parent]`
  ——孩子拿不到父 agent 没有的工具。(注意:模型走不到这一支,`delegate_task` 硬传 `None`;
  这一支是给 `agent/subagent_lifecycle.py` 的插件 API 用的。)
- `_expand_parent_toolsets` 处理"复合 toolset"问题:父 agent 只声明了 `hermes-cli`(一个大包),
  孩子要 `web`,朴素的字符串求交会拒绝。展开办法是按**工具名子集关系**补齐。

`tools/delegate_tool.py:684-700 @ 863e313`
```python
    parent_tool_names: set = set()
    for ts_name in parent_toolsets:
        ts_def = TOOLSETS.get(ts_name)
        if ts_def:
            parent_tool_names.update(ts_def.get("tools", []))

    if not parent_tool_names:
        return set(parent_toolsets)

    expanded = set(parent_toolsets)
    for ts_name, ts_def in TOOLSETS.items():
        if ts_name in expanded:
            continue
        ts_tools = ts_def.get("tools", [])
        if ts_tools and set(ts_tools).issubset(parent_tool_names):
            expanded.add(ts_name)
    return expanded
```

### 3.3 两层裁剪:先删整组,再减单工具

第一层 `_strip_blocked_tools`——只删"整组都在黑名单里"的 toolset,外加两个特判:

`tools/delegate_tool.py:900-918 @ 863e313`
```python
def _strip_blocked_tools(toolsets: List[str]) -> List[str]:
    """Remove toolsets that contain only blocked tools.

    The strip set is derived from DELEGATE_BLOCKED_TOOLS plus the explicit
    composite/scenario toolsets (delegation, code_execution) that have no
    one-to-one tool. This keeps the blocklist and the strip set in lockstep
    so new blocked tools can't silently leak through as toolset names.
    """
    # Composite toolsets that should never pass through to children, even
    # though their individual tools aren't all in DELEGATE_BLOCKED_TOOLS.
    _COMPOSITE_BLOCKED_TOOLSETS = frozenset({"delegation"})
    blocked_toolset_names = {
        name
        for name, defn in TOOLSETS.items()
        if name in _COMPOSITE_BLOCKED_TOOLSETS
        or all(t in DELEGATE_BLOCKED_TOOLS for t in defn.get("tools", []))
    }
    blocked_toolset_names.add("kanban")
    return [t for t in toolsets if t not in blocked_toolset_names]
```

第二层:混装的平台大包(`hermes-cli`、`hermes-telegram` …)不能整组删(里面还有有用工具),
于是把"恰好只含某一个黑名单工具"的 toolset 当作 **deny 列表**传给 `AIAgent`,
让 `model_tools` 在复合展开**之后**再减一次,并且这个限制会被 agent 存进 `disabled_toolsets`,
**扛得住后续 registry / MCP 刷新**。

`tools/delegate_tool.py:921-939 @ 863e313`
```python
def _blocked_toolsets_for_role(role: str) -> List[str]:
    """Return one-tool deny toolsets for a delegated child role.

    ``_strip_blocked_tools`` can remove fully blocked toolsets, but it must keep
    mixed platform bundles such as ``hermes-cli`` because those also contain
    useful tools. Passing these exact deny toolsets to AIAgent lets
    ``model_tools`` subtract blocked names *after* composite expansion, and the
    restriction survives later registry/MCP refreshes through the agent's
    stored ``disabled_toolsets``.
    """
    blocked_names = set(DELEGATE_BLOCKED_TOOLS)
    if role == "orchestrator":
        blocked_names.discard("delegate_task")
    return sorted(
        name
        for name, defn in TOOLSETS.items()
        if defn.get("tools")
        and set(defn.get("tools", ())).issubset(blocked_names)
    )
```

`tools/delegate_tool.py:1295-1315 @ 863e313`
```python
    # Blocked tools also live inside mixed platform bundles (hermes-cli,
    # hermes-telegram, etc.) that _strip_blocked_tools must keep because they
    # carry useful tools too. Pass exact one-tool deny toolsets through to the
    # child so model_tools subtracts the blocked names AFTER composite
    # expansion, and the restriction survives later registry/MCP refreshes.
    raw_parent_disabled = getattr(parent_agent, "disabled_toolsets", None)
    if isinstance(raw_parent_disabled, (list, tuple, set)):
        inherited_disabled = [str(name) for name in raw_parent_disabled]
    else:
        inherited_disabled = []
    if effective_role == "orchestrator":
        # Role grants delegate_task explicitly, matching the unconditional
        # delegation toolset re-add below.
        inherited_disabled = [
            name for name in inherited_disabled if name != "delegation"
        ]
    child_disabled_toolsets = list(
        dict.fromkeys(
            inherited_disabled + _blocked_toolsets_for_role(effective_role) + ["kanban"]
        )
    )
```

编排者把被第一层删掉的 `delegation` 无条件加回来——**能力来自角色,不来自继承**:

`tools/delegate_tool.py:1317-1322 @ 863e313`
```python
    # Orchestrators retain the 'delegation' toolset that _strip_blocked_tools
    # removed.  The re-add is unconditional on parent-toolset membership because
    # orchestrator capability is granted by role, not inherited — see the
    # test_intersection_preserves_delegation_bound test for the design rationale.
    if effective_role == "orchestrator" and "delegation" not in child_toolsets:
        child_toolsets.append("delegation")
```

### 3.4 MCP toolset 的单独通道

MCP(把外部工具服务器接进来的协议)toolset 在"孩子被窄化"时默认**保留**,由
`delegation.inherit_mcp_toolsets`(默认 true)控制:

`tools/delegate_tool.py:651-669 @ 863e313`
```python
def _get_inherit_mcp_toolsets() -> bool:
    """Whether narrowed child toolsets should keep the parent's MCP toolsets."""
    cfg = _load_config()
    return is_truthy_value(cfg.get("inherit_mcp_toolsets"), default=True)


def _is_mcp_toolset_name(name: str) -> bool:
    """Return True for canonical MCP toolsets and their registered aliases."""
    if not name:
        return False
    if str(name).startswith("mcp-"):
        return True
    try:
        from tools.registry import registry

        target = registry.get_toolset_alias_target(str(name))
    except Exception:
        target = None
    return bool(target and str(target).startswith("mcp-"))
```

### 3.5 与 `toolset_distributions.py` 的关系:**没有关系**

**搜索面**:`grep -rn "toolset_distributions" --include=*.py .`(全仓,含测试)共 5 处命中:
它自己的 docstring 1 处、`tests/test_toolset_distributions.py` 2 处、`batch_runner.py` 2 处。
`tools/delegate_tool.py` **不在其中**。该文件是**数据生成批处理**用的 toolset 采样分布表
(给每条 prompt 按概率抽一组 toolset),与运行期委派无关。

```verify
cd /home/user/hermes-agent && grep -rn "toolset_distributions" --include=*.py .
```

委派侧真正的 toolset 权威来源是根目录 `toolsets.py` 的 `TOOLSETS` 字典(`tools/delegate_tool.py`
在第 35 行 import 它)与 `tools/registry.py`。

### 3.6 `execute_code` **不被裁**(而这是一条需要盯住的通道)

黑名单里没有 `execute_code`,`_COMPOSITE_BLOCKED_TOOLSETS` 里也没有 `code_execution`。
测试把这一点固化成了行为规格:

`tests/tools/test_delegate.py:637-643 @ 863e313`
```python
class TestBlockedTools(unittest.TestCase):

    def test_execute_code_not_blocked(self):
        """Children retain execute_code (programmatic tool calling) so they
        can batch mechanical work instead of burning reasoning iterations
        (Teknium, Jul 2026)."""
        self.assertNotIn("execute_code", DELEGATE_BLOCKED_TOOLS)
```

`execute_code` 让孩子在沙箱里写 Python 并通过 RPC 反向调工具。它的 RPC 白名单是**独立的 7 个工具**,
**不含 `delegate_task`**,所以孩子无法用它绕过"不许再委派":

`tools/code_execution_tool.py:63-71 @ 863e313`
```python
SANDBOX_ALLOWED_TOOLS = frozenset([
    "web_search",
    "web_extract",
    "read_file",
    "write_file",
    "search_files",
    "patch",
    "terminal",
])
```

但白名单的求交有一处**回退放宽**,见第 9 节移交项 H-3:

`tools/code_execution_tool.py:1090-1093 @ 863e313`
```python
    session_tools = set(enabled_tools) if enabled_tools else set()
    sandbox_tools = frozenset(SANDBOX_ALLOWED_TOOLS & session_tools)
    if not sandbox_tools:
        sandbox_tools = SANDBOX_ALLOWED_TOOLS
```

---

## 4. 递归深度:默认扁平,提升是显式 opt-in

### 4.1 常量与语义

`tools/delegate_tool.py:127-133 @ 863e313`
```python
MAX_DEPTH = 1  # flat by default: parent (0) -> child (1); grandchild rejected unless max_spawn_depth raised.
# Configurable depth cap consulted by _get_max_spawn_depth; MAX_DEPTH
# stays as the default fallback and is still the symbol tests import.
_MIN_SPAWN_DEPTH = 1
# No upper ceiling on spawn depth — like max_concurrent_children, depth has a
# floor of 1 and no ceiling. Deeper trees multiply API cost, so the default
# stays flat (MAX_DEPTH = 1); raising the config knob is an explicit opt-in.
```

`max_spawn_depth = N` 的含义是:深度 `0..N-1` 的 agent 可以再派,深度 `N` 是叶子地板。
默认 1 ⇒ 父(0)可以派,孩子(1)不能再派。

### 4.2 三道各自独立的闸

| 闸 | 位置 | 作用 |
|---|---|---|
| A. 工具根本不在孩子手里 | `_strip_blocked_tools` 删掉 `delegation` 组 | 叶子孩子的 schema 里没有 `delegate_task` |
| B. 角色降级 | `_build_child_agent` 的 `orchestrator_ok` | `child_depth >= max_spawn` 时 orchestrator 静默降 leaf |
| C. 运行期深度检查 | `delegate_task` 开头 | 即使工具漏进去了,调用也会被 `tool_error` 拒掉 |

闸 C:

`tools/delegate_tool.py:2847-2856 @ 863e313`
```python
    depth = getattr(parent_agent, "_delegate_depth", 0)
    max_spawn = _get_max_spawn_depth()
    if depth >= max_spawn:
        return tool_error(
            f"Delegation depth limit reached (depth={depth}, "
            f"max_spawn_depth={max_spawn}). Raise "
            f"delegation.max_spawn_depth in config.yaml if deeper "
            f"nesting is required (no hard ceiling, but each level "
            f"multiplies API cost)."
        )
```

**超限时的表现**:返回一个 `tool_error` 字符串(模型能读懂并改道),不是异常、不是静默失败。
错误文案把当前 depth、当前 `max_spawn_depth` 和"没有硬上限,但每一层乘一次 API 成本"都写进去了。

### 4.3 上限的形状:有地板,**没有天花板**

`tools/delegate_tool.py:610-631 @ 863e313`
```python
    cfg = _load_config()
    val = cfg.get("max_spawn_depth")
    if val is None:
        return MAX_DEPTH
    try:
        ival = int(val)
    except (TypeError, ValueError):
        logger.warning(
            "delegation.max_spawn_depth=%r is not a valid integer; " "using default %d",
            val,
            MAX_DEPTH,
        )
        return MAX_DEPTH
    floored = max(_MIN_SPAWN_DEPTH, ival)
    if floored != ival:
        logger.warning(
            "delegation.max_spawn_depth=%d below floor %d; using %d",
            ival,
            _MIN_SPAWN_DEPTH,
            floored,
        )
    return floored
```

`max(_MIN_SPAWN_DEPTH, ival)` 只做下限钳制,**没有任何上限钳制**。并发上限同理
(`max(1, int(val))`,>10 时只打一条一次性成本警告)。

### 4.4 循环检测:**没有**基于内容的环检测

**搜索面**:

```verify
cd /home/user/hermes-agent && grep -niE "cycle|visited|seen|dedup|fingerprint|hash" tools/delegate_tool.py
cd /home/user/hermes-agent && grep -niE "\bloop\b" tools/delegate_tool.py
```

第一条实测 25 行命中,全部落在三类里:(a) 心跳停滞检测的 `_HEARTBEAT_STALE_CYCLES_*`
与 `_last_seen_*` 三元组(第 748–749、2013–2075 行);(b) 字面量 "lifecycle" 里含 "cycle"
(第 400、767、1042、1603、2651、2756、2762、2957、3276、3291 行);(c) 一处 "orchestrator lifecycle events"。
第二条只有 1 行命中,是第 2987 行注释里的 "reach the agent loop"。
**没有任何"这个 goal / 这棵子树我派过了"的判断。**

所以**唯一的防跑飞手段是深度上限 + 宽度上限 + 每轮生成数上限(6.5)**。
重实现时要意识到:一个模型完全可以在**不同轮**里反复派同一个语义等价的任务,harness 不会拦;
也没有任何机制阻止 A 委派 B、B(作为 orchestrator)再委派一个和 A 目标相同的任务
——只要深度还够,树就会长下去。

### 4.5 深度事实被写进孩子的提示词(避免模型幻想自己能力)

`tools/delegate_tool.py:839-849 @ 863e313`
```python
    if role == "orchestrator":
        child_note = (
            "Your own children MUST be leaves (cannot delegate further) "
            "because they would be at the depth floor — you cannot pass "
            "role='orchestrator' to your own delegate_task calls."
            if child_depth + 1 >= max_spawn_depth
            else "Your own children can themselves be orchestrators or leaves, "
            "depending on the `role` you pass to delegate_task. Default is "
            "'leaf'; pass role='orchestrator' explicitly when a child "
            "needs to further decompose its work."
        )
```

`tools/delegate_tool.py:866-869 @ 863e313`
```python
            "final summary, not your workers.\n\n"
            f"NOTE: You are at depth {child_depth}. The delegation tree "
            f"is capped at max_spawn_depth={max_spawn_depth}. {child_note}"
        )
```

这条很值得抄:**把 harness 的真实约束写成提示词里的字面事实**,而不是让模型去猜。

---

## 5. 失败、超时、中断:父 agent 看到什么,有没有泄漏

### 5.1 默认无墙钟超时(这是一次有理由的回退)

`tools/delegate_tool.py:727-732 @ 863e313`
```python
# No default wall-clock cap on child agents: legitimate heavy subagent work
# (deep reviews, research fan-outs, slow reasoning models) was being killed
# mid-task. Errors should come from what the child actually does; stuck-child
# detection lives in the heartbeat staleness monitor below. Users can opt back
# in via delegation.child_timeout_seconds.
DEFAULT_CHILD_TIMEOUT: Optional[float] = None
```

`tools/delegate_tool.py:571-592 @ 863e313`
```python
    cfg = _load_config()
    val = cfg.get("child_timeout_seconds")
    if val is not None:
        try:
            parsed = float(val)
        except (TypeError, ValueError):
            logger.warning(
                "delegation.child_timeout_seconds=%r is not a valid number; "
                "using default (no timeout)",
                val,
            )
        else:
            return None if parsed <= 0 else max(30.0, parsed)
    env_val = os.getenv("DELEGATION_CHILD_TIMEOUT_SECONDS")
    if env_val:
        try:
            parsed = float(env_val)
        except (TypeError, ValueError):
            pass
        else:
            return None if parsed <= 0 else max(30.0, parsed)
    return DEFAULT_CHILD_TIMEOUT
```

注意 `max(30.0, parsed)`:开了就有 30 秒地板,`0` 或负数表示关闭。

### 5.2 超时/异常发生时:先"请求中断",再造一条结构化结果

`tools/delegate_tool.py:2212-2230 @ 863e313`
```python
        try:
            result = _child_future.result(timeout=child_timeout)
        except Exception as _timeout_exc:
            # Signal the child to stop so its thread can exit cleanly.
            try:
                interrupted = child is not None and request_hard_interrupt(child)
                if not interrupted and child is not None and hasattr(child, "_interrupt_requested"):
                    child._interrupt_requested = True
            except Exception:
                pass

            is_timeout = isinstance(_timeout_exc, (FuturesTimeoutError, TimeoutError))
            duration = round(time.monotonic() - child_start, 2)
            logger.warning(
                "Subagent %d %s after %.1fs",
                task_index,
                "timed out" if is_timeout else f"raised {type(_timeout_exc).__name__}",
                duration,
            )
```

`request_hard_interrupt` 用 `inspect.getattr_static` 先证明方法真的存在,免得把
`MagicMock` 之类的动态代理当成实现了新 ABI:

`agent/interrupt_compat.py:9-26 @ 863e313`
```python
def request_hard_interrupt(agent: Any, message: str | None = None) -> bool:
    """Request an explicit stop, falling back to the legacy interrupt ABI.

    New agents expose ``hard_interrupt(message=None)``. Third-party agents and
    old test doubles may only expose ``interrupt(message=None)``; keep those
    usable without sending the newer ``hard_cancel=`` keyword they do not know.
    Returns ``False`` only when neither callable is available.
    """
    # Avoid treating a dynamic ``__getattr__`` proxy (notably an unspecced
    # ``MagicMock`` or a third-party RPC facade) as if it genuinely implements
    # the new ABI. Static lookup proves the attribute exists on the instance or
    # its type before normal descriptor binding retrieves the callable.
    try:
        inspect.getattr_static(agent, "hard_interrupt")
    except AttributeError:
        interrupt = None
    else:
        interrupt = getattr(agent, "hard_interrupt", None)
```

父 agent 拿到的那条结果长这样(**结构化字段,不用解析文案**):

`tools/delegate_tool.py:2298-2315 @ 863e313`
```python
            return {
                "task_index": task_index,
                "status": "timeout" if is_timeout else "error",
                "summary": None,
                "error": _err,
                "exit_reason": "timeout" if is_timeout else "error",
                "api_calls": child_api_calls,
                "duration_seconds": duration,
                "timeout_seconds": child_timeout if is_timeout else None,
                "timed_out_after_seconds": duration if is_timeout else None,
                "timeout_phase": (
                    "before_first_llm_call" if is_timeout and child_api_calls == 0
                    else "after_llm_calls" if is_timeout
                    else None
                ),
                "_child_role": getattr(child, "_delegate_role", None),
                "diagnostic_path": diagnostic_path,
            }
```

`timeout_phase` 区分 `before_first_llm_call` / `after_llm_calls`,是很实用的一刀:
前者说明根本没走到模型请求(提示词过大被拒、凭据解析卡住、传输层挂了),后者说明卡在某次调用/工具里。

### 5.3 0 次 API 调用就超时 → 写一份诊断转储

`tools/delegate_tool.py:1735-1750 @ 863e313`
```python
        _w("## Worker thread stack at timeout")
        if worker_thread is not None and worker_thread.is_alive():
            frames = _sys._current_frames()
            worker_frame = frames.get(worker_thread.ident)
            if worker_frame is not None:
                stack = _traceback.format_stack(worker_frame)
                for frame_line in stack:
                    for sub in frame_line.rstrip().split("\n"):
                        _w(f"  {sub}")
            else:
                _w("  <worker frame not available>")
        elif worker_thread is None:
            _w("  <no worker thread handle>")
        else:
            _w("  <worker thread already exited>")
        _w("")
```

`tools/delegate_tool.py:1757-1778 @ 863e313`
```python
        _w("## All thread stacks at timeout")
        try:
            frames = _sys._current_frames()
            by_ident = {
                th.ident: th for th in _threading.enumerate() if th.ident
            }
            worker_ident = worker_thread.ident if worker_thread else None
            dumped = 0
            for ident, frame in frames.items():
                if ident == worker_ident:
                    continue  # already dumped above
                if dumped >= 40:
                    _w(f"  <{len(frames) - dumped - 1} more threads omitted>")
                    break
                th = by_ident.get(ident)
                name = th.name if th else f"ident={ident}"
                daemon = " daemon" if (th and th.daemon) else ""
                _w(f"  --- {name}{daemon} ---")
                for frame_line in _traceback.format_stack(frame):
                    for sub in frame_line.rstrip().split("\n"):
                        _w(f"    {sub}")
                dumped += 1
```

**为什么要 dump 全部线程而不只是 worker**:worker 自己的栈常常停在"等另一个辅助线程",
只看它无法区分"卡在 HTTP 之前"和"provider 慢"。这条经验值得抄。

### 5.4 收尾:`finally` 里做了 7 件事

`tools/delegate_tool.py:2604-2628 @ 863e313`
```python
        # Close tool resources (terminal sandboxes, browser daemons,
        # background processes, httpx clients) so subagent subprocesses
        # don't outlive the delegation.
        try:
            if hasattr(child, "close"):
                child.close()
        except Exception:
            logger.debug("Failed to close child agent after delegation")

        # The AIAgent turn boundary normally closes the child scope itself. This
        # fallback covers failures before that boundary starts, but must not pop
        # a scope while a timed-out child worker is still unwinding.
        try:
            from agent import relay_runtime

            runtime = relay_runtime.get_runtime(create=False)
            child_session_id = str(getattr(child, "session_id", "") or "")
            child_turn_is_active = relay_runtime.SESSION_COORDINATOR.has_active_turn(
                profile_key=relay_runtime.current_profile_key(),
                session_id=child_session_id,
            )
            if runtime is not None and child_session_id and not child_turn_is_active:
                runtime.unregister_subagent({"child_session_id": child_session_id})
        except Exception:
            logger.debug("Failed to close child Relay session after delegation")
```

顺序是:停心跳并 join(≤5s)→ 摘掉注册表条目 → 归还凭据租约 → 恢复进程级工具名全局 →
从父 agent 的 `_active_children` 摘掉 → `child.close()` → 关 Relay 子会话作用域。

`child.close()` 的 6 步:

`run_agent.py:4209-4218 @ 863e313`
```python
    def close(self) -> None:
        """Release all resources held by this agent instance.

        Cleans up subprocess resources that would otherwise become orphans:
        - Background processes tracked in ProcessRegistry
        - Terminal sandbox environments
        - Browser daemon sessions
        - Computer-use backend sessions and target/ref state
        - Active child agents (subagent delegation)
        - OpenAI/httpx client connections
```

**但这 6 步分两类,效果差别很大**(见 5.7):第 1~4 步都按 `task_id` 查表,
而这里传的 `task_id` 是**孩子的 `session_id`**——孩子的终端资源却是记在折叠后的 `"default"` 名下的,
所以这几步对子 agent 基本查不到东西。真正会动手的是第 5、6 步,它们操作的是**对象状态**:

`run_agent.py:4256-4275 @ 863e313`
```python
        # 5. Close active child agents
        try:
            with self._active_children_lock:
                children = list(self._active_children)
                self._active_children.clear()
            for child in children:
                try:
                    child.close()
                except Exception:
                    pass
        except Exception:
            pass

        # 6. Close the OpenAI/httpx client
        try:
            client = getattr(self, "client", None)
            if client is not None:
                self._close_openai_client(client, reason="agent_close", shared=True)
                self.client = None
        except Exception:
```

**这里有一个不对称,记为 ■(见 7.3)**:紧随其后的 Relay 收尾**专门**判断了"超时的孩子可能还在
展开中"并据此跳过,而上面的 `child.close()` 没有任何这类判断。

`tools/delegate_tool.py:2613-2626 @ 863e313`
```python
        # The AIAgent turn boundary normally closes the child scope itself. This
        # fallback covers failures before that boundary starts, but must not pop
        # a scope while a timed-out child worker is still unwinding.
        try:
            from agent import relay_runtime

            runtime = relay_runtime.get_runtime(create=False)
            child_session_id = str(getattr(child, "session_id", "") or "")
            child_turn_is_active = relay_runtime.SESSION_COORDINATOR.has_active_turn(
                profile_key=relay_runtime.current_profile_key(),
                session_id=child_session_id,
            )
            if runtime is not None and child_session_id and not child_turn_is_active:
                runtime.unregister_subagent({"child_session_id": child_session_id})
```

### 5.5 摘要预算:不让 N 份摘要撑爆父 agent 的上下文

`tools/delegate_tool.py:1916-1928 @ 863e313`
```python
def _apply_summary_budget(results: List[Dict[str, Any]], parent_agent) -> None:
    """Trim subagent summaries in-place so the batch can't overflow the
    parent's context window, spilling full text to disk so nothing is lost.

    The effective per-summary cap is the MIN of:
      - the dynamic headroom budget (remaining parent context ÷ batch size), and
      - the static ``delegation.max_summary_chars`` ceiling (0 = disabled).

    When a summary exceeds the cap, its full text is written to a file and the
    in-context summary becomes a head slice plus a pointer to that file. This
    addresses issue/PR #9126: batch fan-out returned N full summaries verbatim,
    blowing the parent context and (on rate-limited providers) triggering a
    compression/429 death spiral.
```

动态额度 = 父 agent **剩余** headroom × 0.5 ÷ 批量条数,再与静态上限取 min;低于 2000 字符时给地板。

`tools/delegate_tool.py:1900-1910 @ 863e313`
```python
        # Reserve the compressor's output budget so we measure INPUT headroom.
        reserved = getattr(compressor, "max_tokens", 0) or 0
        headroom_tokens = context_length - int(used_tokens) - int(reserved)
        if headroom_tokens <= 0:
            # Parent is already over budget — give each summary only the floor.
            return _MIN_SUMMARY_CHARS

        batch_token_budget = int(headroom_tokens * _SUMMARY_HEADROOM_FRACTION)
        per_summary_tokens = batch_token_budget // max(1, n_summaries)
        per_summary_chars = per_summary_tokens * 4  # ~4 chars/token
        return max(_MIN_SUMMARY_CHARS, per_summary_chars)
```

超额时**不是简单截断**:保留头 75% + 尾 25%(尾巴里通常是"改了哪些文件 / 遇到什么问题"),
中间溢写到磁盘,并在页脚给出精确的 `read_file offset=` 让父 agent 能翻回去。

`tools/delegate_tool.py:1850-1864 @ 863e313`
```python
    footer_lines = [
        "",
        "─" * 8 + " [SUMMARY TRUNCATED] " + "─" * 8,
        f"Showing {len(head):,} chars (head) + {len(tail):,} chars (tail) "
        f"of {original_len:,} total — trimmed to protect the parent's context window.",
    ]
    if spill_path:
        # read_file is 1-indexed; +2 moves past the last head line shown.
        middle_start_line = head.count("\n") + 2
        footer_lines.append(f"Full subagent output saved to: {spill_path}")
        footer_lines.append(
            f'To read the omitted middle: read_file path="{spill_path}" '
            f"offset={middle_start_line} limit=200  (the file is the complete "
            f"summary; raise/lower offset to page through it)."
        )
```

溢写目录选得也有讲究:`cache/delegation` 是被只读挂进远程后端(Docker/Modal/SSH)的,
所以父 agent 在任何后端上都能用 `read_file` 翻这份全文。

`tools/delegate_tool.py:1796-1805 @ 863e313`
```python
def _spill_summary_to_file(task_index: int, summary: str) -> Optional[str]:
    """Write a subagent's full summary to the delegation cache and return path.

    Mirrors web_extract's ``_store_full_text``: the file lands in
    ``cache/delegation`` which is mounted read-only into remote backends
    (Docker/Modal/SSH) via ``credential_files._CACHE_DIRS``, so the parent's
    terminal/``read_file`` tools can page through the complete text on any
    backend. Returns the absolute path, or None on failure (best-effort:
    the trimmed head+tail is still returned to the parent regardless).
    """
```

### 5.6 孤儿与泄漏:一份清点

| 资源 | 谁负责回收 | 超时被抛弃时的下场 |
|---|---|---|
| worker 线程 | 无人 join;`shutdown(wait=False)` | **被抛弃**,但因为是 daemon,不阻塞解释器退出 |
| 孩子的后台进程(`terminal(background=True)`) | **进程退出前基本没人**(见 5.7) | 活到进程级 `kill_all()` |
| 终端容器 / 沙箱 | 故意不回收(共享的,见 5.7) | 保留 |
| 孩子的 httpx / OpenAI 客户端 | `child.close()` 第 6 步 | 可能在孩子仍在请求中时被关(■2,7.3) |
| 孙子 agent | `child.close()` 第 5 步 | 递归 close |
| 凭据租约 | `finally` 的 `release_lease` | 正常归还 |
| `_active_subagents` 条目 | `finally` 的 `_unregister_subagent` | 正常摘除 |
| 心跳线程 | `finally` 的 `_heartbeat_stop.set()` + join(5s) | 正常停 |
| 实时转写文件 | `update_manifest_statuses` + 保留文件 | 保留(有 7 天清理) |
| 父 agent 的 `_active_children` | `finally` 的 `remove` | 正常摘除 |

### 5.7 一个贯穿性的键错位:`task_id` 与 `session_id`

孩子的工具调用用的是 `child_task_id`(= `subagent_id`,1.6.3),而终端层又把它**折叠**成
`"default"`(2.3),于是后台进程实际登记在 `"default"` 名下:

`tools/terminal_tool.py:2692-2696 @ 863e313`
```python
                    proc_session = process_registry.spawn_local(
                        command=command,
                        cwd=effective_cwd,
                        task_id=effective_task_id,
                        session_key=session_key,
```

而 `AIAgent.close()` 拿去查表的键是**孩子的 `session_id`**:

`run_agent.py:4225-4229 @ 863e313`
```python
        # 1. Kill background processes for this task
        try:
            from tools.process_registry import process_registry
            process_registry.kill_all(task_id=task_id)
        except Exception:
```

三个键(`session_id` / `subagent_id` / `"default"`)互不相等,所以 `close()` 的第 1~4 步对子 agent
**查不到任何东西**。这不全是坏事——`cleanup_vm` 的 docstring 明说共享容器**不该**在会话关闭时被拆:

`tools/terminal_tool.py:1927-1934 @ 863e313`
```python
    session-lifecycle semantics: this function is called from
    ``AIAgent.close()`` (TUI session close, gateway session teardown) and the
    per-turn cleanup branch for non-persistent envs, both of which should
    honor the user's persist-mode preference. Stopping the container here
    would defeat the "ONE long-lived container shared across sessions"
    contract — exactly the bug Ben reported when the container was killed
    on every TUI session close.

```

**净效果**:子 agent 起的后台进程会活到**进程级** `kill_all()`(gateway 关闭 / CLI 退出 / TUI RPC),
而不是活到子 agent 结束。重实现时这是一个必须自己决定的问题:
"孩子的后台进程该跟孩子一起死,还是跟容器一起活?"——这套代码选了后者,但**没有在任何文档里说**。
搜索面:

```verify
cd /home/user/hermes-agent && grep -rn "kill_all(" --include=*.py .
```

实测全仓 13 处命中(含 4 处测试与 1 处 docstring)。其中**带 `task_id=` 参数**的生产调用只有
`run_agent.py` 第 4228 行一处;其余生产调用——`gateway/run.py` 第 12696 行(gateway 关闭)、
`hermes_cli/cli_commands_mixin.py` 第 467 行(CLI 退出)、`tui_gateway/methods_tools.py` 第 44 行
与 `tui_gateway/server.py` 第 12618 行(TUI RPC)——都是**无参全杀**。

---

## 6. 并发:同时能跑几个,共享资源怎么串行化

### 6.1 并发上限在哪一行

`tools/delegate_tool.py:120-126 @ 863e313`
```python
_DEFAULT_MAX_CONCURRENT_CHILDREN = 3
# One-shot guard: the high-concurrency cost advisory is emitted at most once
# per process. _get_max_concurrent_children() runs on every get_definitions()
# schema rebuild (via _build_top_level_description / _build_tasks_param_description),
# so without this flag a config of max_concurrent_children>10 spams the log on
# every turn / agent spawn even when delegate_task is never called.
_HIGH_CONCURRENCY_WARNED = False
```

`tools/delegate_tool.py:491-520 @ 863e313`
```python
    cfg = _load_config()
    val = cfg.get("max_concurrent_children")
    if val is not None:
        try:
            result = max(1, int(val))
            if result > 10:
                global _HIGH_CONCURRENCY_WARNED
                if not _HIGH_CONCURRENCY_WARNED:
                    _HIGH_CONCURRENCY_WARNED = True
                    logger.warning(
                        "delegation.max_concurrent_children=%d: each child consumes API tokens "
                        "independently. High values multiply cost linearly.",
                        result,
                    )
            return result
        except (TypeError, ValueError):
            logger.warning(
                "delegation.max_concurrent_children=%r is not a valid integer; "
                "using default %d",
                val,
                _DEFAULT_MAX_CONCURRENT_CHILDREN,
            )
            return _DEFAULT_MAX_CONCURRENT_CHILDREN
    env_val = os.getenv("DELEGATION_MAX_CONCURRENT_CHILDREN")
    if env_val:
        try:
            return max(1, int(env_val))
        except (TypeError, ValueError):
            return _DEFAULT_MAX_CONCURRENT_CHILDREN
    return _DEFAULT_MAX_CONCURRENT_CHILDREN
```

优先级:`config.yaml` 的 `delegation.max_concurrent_children` > 环境变量
`DELEGATION_MAX_CONCURRENT_CHILDREN` > 默认 3。**只有地板 1,没有天花板**;>10 时打一次成本警告
(用 `_HIGH_CONCURRENCY_WARNED` 做一次性守卫,因为这个函数每次重建 schema 都会被调到)。

### 6.2 同一个数字管两件事

`tools/delegate_tool.py:526-540 @ 863e313`
```python
def _get_max_async_children() -> int:
    """Concurrency cap for background (``background=true``) delegations.

    DEPRECATED KNOB: ``delegation.max_async_children`` has been unified into
    ``delegation.max_concurrent_children`` — one cap governs both a single
    synchronous batch's parallelism and how many background delegation units
    may run at once. When at capacity, a new async dispatch is REJECTED (not
    queued) so a runaway model can't pile up unbounded background work; the
    caller falls back to running the work synchronously.

    A leftover ``max_async_children`` in config.yaml is ignored (the config
    migration removes it, folding a raised value into
    ``max_concurrent_children``); we log a one-time deprecation warning if
    one is still present.
    """
```

- **一批之内的并行度**:`DaemonThreadPoolExecutor(max_workers=max_children)`。
- **同时在跑的后台委派"单元"数**:满了就**拒绝**(不排队),调用方退回同步执行。

`tools/async_delegation.py:1003-1012 @ 863e313`
```python
        if running >= max_async_children:
            return {
                "status": "rejected",
                "error": (
                    f"Async delegation capacity reached ({max_async_children} "
                    f"running). Wait for one to finish (its result will re-enter "
                    f"the chat), or raise delegation.max_concurrent_children in "
                    f"config.yaml to allow more concurrent background units."
                ),
            }
```

### 6.3 线程池的形状:两层

```text
父 agent 线程
  └─ DaemonThreadPoolExecutor(max_workers = max_concurrent_children)   ← 批量层
       └─ 每个 _run_single_child 内部再开
            DaemonThreadPoolExecutor(max_workers=1, initializer=装审批回调) ← 单孩子层
                 └─ contextvars.copy_context().run(child.run_conversation)
```

两层的理由各自独立:批量层给并行度,单孩子层给"可超时 + 可装线程局部审批回调"。
**审批回调只装在单孩子层**,所以真正跑 `run_conversation` 的那个线程一定有回调。

### 6.4 共享资源怎么串行化

| 共享资源 | 手段 | 位置 |
|---|---|---|
| `model_tools._last_resolved_tool_names`(进程级全局) | `_CHILD_CONSTRUCTION_LOCK` 包住构造,构造后立刻还原 | `_build_child_preserving_parent_tools` |
| 父 agent 的收尾副作用(摘要/memory/hook/成本) | 父 agent 对象上挂一把 `RLock`,首次用时双检加锁创建 | `_parent_finalization_lock` |
| `_active_subagents` 注册表 | 模块级 `threading.Lock` | `_register_subagent` 等 |
| spawn 暂停标志 | 模块级 `threading.Lock` | `set_spawn_paused` |
| stdout / TUI | 不用锁,改用 `spinner.print_above` 或父 agent 的 `_safe_print` | `_emit_parent_console` |

工具名全局的存救:

`tools/delegate_tool.py:2636-2647 @ 863e313`
```python
def _build_child_preserving_parent_tools(**kwargs):
    """Build a child without leaking its resolved toolset into the parent."""
    import model_tools

    with _CHILD_CONSTRUCTION_LOCK:
        parent_tool_names = list(model_tools._last_resolved_tool_names)
        try:
            child = _build_child_agent(**kwargs)
        finally:
            model_tools._last_resolved_tool_names = parent_tool_names
    child._delegate_saved_tool_names = parent_tool_names
    return child
```

父 agent 级锁的双检创建:

`tools/delegate_tool.py:2650-2665 @ 863e313`
```python
def _parent_finalization_lock(parent_agent) -> threading.RLock:
    """Return the per-parent lock that serializes lifecycle side effects."""
    if parent_agent is None:
        return _PARENT_FINALIZATION_FALLBACK_LOCK
    lock = getattr(parent_agent, "_subagent_finalization_lock", None)
    if lock is not None:
        return lock
    with _PARENT_FINALIZATION_LOCK_GUARD:
        lock = getattr(parent_agent, "_subagent_finalization_lock", None)
        if lock is None:
            lock = threading.RLock()
            try:
                setattr(parent_agent, "_subagent_finalization_lock", lock)
            except Exception:
                return _PARENT_FINALIZATION_FALLBACK_LOCK
    return lock
```

stdout 不用锁,而是走父 agent 的打印函数——因为 ACP / gateway API 这类 stdio 宿主要把非协议输出
重定向到 stderr,裸 `print()` 会污染 JSON-RPC 帧:

`tools/delegate_tool.py:942-957 @ 863e313`
```python
def _emit_parent_console(parent_agent, line: str) -> None:
    """Emit a human-readable progress line to the parent's console.

    Routes through ``parent_agent._safe_print`` when available so headless
    stdio hosts (ACP, gateway API) can redirect non-protocol output to
    stderr via their configured ``_print_fn``. A bare ``print()`` would
    otherwise land on stdout and corrupt JSON-RPC framing.
    """
    printer = getattr(parent_agent, "_safe_print", None)
    if callable(printer):
        try:
            printer(line)
            return
        except Exception:
            pass
    print(line)
```

### 6.5 还有两道**不在本文件**的宽度闸

一次模型回复里可能包含**多个** `delegate_task` tool_call(本文件只管单次调用内部的条数),
所以 `run_agent` 又截了一刀:

`run_agent.py:4587-4592 @ 863e313`
```python
        from tools.delegate_tool import _get_max_concurrent_children
        max_children = _get_max_concurrent_children()
        delegate_count = sum(1 for tc in tool_calls if tc.function.name == "delegate_task")
        if delegate_count <= max_children:
            return tool_calls
        kept_delegates = 0
```

以及每轮(turn)的子 agent 生成总数上限(默认 50,`tool_loop_guardrails.loop_caps.max_subagents`):

`agent/tool_guardrails.py:483-487 @ 863e313`
```python
        if tool_name == "delegate_task":
            cap = caps.max_subagents
            if not cap:
                return None
            spawn_count = _subagent_spawn_count(args)
```

`hermes_cli/config_defaults.py:555-558 @ 863e313`
```python
        "loop_caps": {
            "max_web_searches": 50,   # max web_search calls per turn (0 = unlimited)
            "max_subagents": 50,      # max subagents spawned per turn (0 = unlimited)
        },
```

`agent/tool_guardrails.py:613-624 @ 863e313`
```python
def _subagent_spawn_count(args: Mapping[str, Any]) -> int:
    """How many subagents a single delegate_task call spawns.

    delegate_task runs in one of two modes: a batch (``tasks`` is a non-empty
    list, one child per item) or a single task (``goal``). Count the batch size
    when present, otherwise 1, so the session subagent cap reflects real spawns
    rather than delegate_task invocations.
    """
    tasks = args.get("tasks") if isinstance(args, Mapping) else None
    if isinstance(tasks, list) and tasks:
        return len(tasks)
    return 1
```

### 6.6 运行期可观测 + 可操控

模块级保留三样东西,供 TUI 的 `/agents` 覆盖层与 gateway 的
`delegation.pause` / `delegation.status` / `subagent.interrupt` RPC 使用:

`tools/delegate_tool.py:136-151 @ 863e313`
```python
# ---------------------------------------------------------------------------
# Runtime state: pause flag + active subagent registry
#
# Consumed by the TUI observability layer (overlay/control surface) and the
# gateway RPCs `delegation.pause`, `delegation.status`, `subagent.interrupt`.
# Kept module-level so they span every delegate_task invocation in the
# process, including nested orchestrator -> worker chains.
# ---------------------------------------------------------------------------

_spawn_pause_lock = threading.Lock()
_spawn_paused: bool = False

_active_subagents_lock = threading.Lock()
# subagent_id -> mutable record tracking the live child agent.  Stays only
# for the lifetime of the run; _run_single_child is the owner.
_active_subagents: Dict[str, Dict[str, Any]] = {}
```

`tools/delegate_tool.py:184-205 @ 863e313`
```python
def interrupt_subagent(subagent_id: str) -> bool:
    """Request that a single running subagent stop at its next iteration boundary.

    Does not hard-kill the worker thread (Python can't); sets the child's
    interrupt flag which propagates to in-flight tools and recurses into
    grandchildren via AIAgent.interrupt().  Returns True if a matching
    subagent was found.
    """
    with _active_subagents_lock:
        record = _active_subagents.get(subagent_id)
    if not record:
        return False
    agent = record.get("agent")
    if agent is None:
        return False
    try:
        if not request_hard_interrupt(agent, f"Interrupted via TUI ({subagent_id})"):
            return False
    except Exception as exc:
        logger.debug("interrupt_subagent(%s) failed: %s", subagent_id, exc)
        return False
    return True
```

`list_active_subagents` 返回**副本**并剔掉 `agent` 对象,这样任何线程都能安全快照:

`tools/delegate_tool.py:208-218 @ 863e313`
```python
def list_active_subagents() -> List[Dict[str, Any]]:
    """Snapshot of the currently running subagent tree.

    Each record: {subagent_id, parent_id, depth, goal, model, started_at,
    tool_count, status}.  Safe to call from any thread — returns a copy.
    """
    with _active_subagents_lock:
        return [
            {k: v for k, v in r.items() if k != "agent"}
            for r in _active_subagents.values()
        ]
```

### 6.7 中继事件里的脱敏

孩子的每次工具调用都会中继给父 agent / 钩子,参数**不原样带出**,只留参数名和"副作用目标",
且 URL 会被重建以剥掉 `user:password@`:

`tools/delegate_tool.py:334-351 @ 863e313`
```python
    if key in _TOOL_INPUT_URL_KEYS:
        try:
            parsed = urlsplit(bounded)
            if parsed.scheme and parsed.netloc:
                hostname = parsed.hostname
                if not hostname:
                    return None
                # ``SplitResult.netloc`` includes ``user:password@``. Rebuild
                # the authority from parsed host/port so hook-visible history
                # cannot carry URL credentials. Bracket IPv6 literals before
                # appending a validated port.
                host = f"[{hostname}]" if ":" in hostname else hostname
                port = parsed.port
                netloc = f"{host}:{port}" if port is not None else host
                return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
        except ValueError:
            return None
    return bounded
```

---

## 7. 与地图的出入

记号:▲ = 文档与代码矛盾;◇ = 代码有、文档无;■ = 代码缺陷;◎ = 文档成立但显著保守。

### 7.1 ▲(8 条)

**▲1 —— `AGENTS.md` 的 "## Delegation (`delegate_task`)" 一节说"默认父 agent 等孩子",与代码相反。**
整段判定:该段共 3 句。第 1 句里的 "isolated context + terminal session" 一半错(容器共用,并入 ▲7);
第 2 句"默认父 agent 等孩子"**整句错**;第 3 句描述的异步机制**真实存在**,但它给出的触发条件
("With `background=true`")错——模型根本设不了这个参数。

`AGENTS.md:985-989 @ 863e313`
> `tools/delegate_tool.py` spawns a subagent with an isolated
> context + terminal session. By default the parent waits for the
> child's summary before continuing its own loop. With `background=true`,
> Hermes returns a delegation id immediately and the result re-enters the
> conversation later through the async-delegation completion queue.

代码:顶层模型侧**一律后台**,`background` 参数被 schema 明确标为 DEPRECATED / IGNORED
(证据见 1.2、1.3)。"默认等"只对**编排者子 agent**成立(`_delegate_depth > 0`),
而这一段讲的是 `delegate_task` 总体。

**▲2 —— `AGENTS.md` 说单任务可以传 `toolsets`。**

`AGENTS.md:993 @ 863e313`
> - **Single:** pass `goal` (+ optional `context`, `toolsets`).

代码:`DELEGATE_TASK_SCHEMA` 的 `properties` 只有 `goal` / `context` / `tasks` / `role` / `background`
(1.2 的 3854 行块所在的同一个字典),`delegate_task` 里更是硬传 `toolsets=None`(1.4 的 2958 块)。
`delegation.md` 第 158 行反而写对了("does not accept a model-facing
`toolsets` parameter")——两份地图自相矛盾。

**▲3 —— `AGENTS.md` 说 `max_spawn_depth` 默认 2。**

`AGENTS.md:1004-1005 @ 863e313`
> own workers. Gated by `delegation.orchestrator_enabled` (default true)
> and bounded by `delegation.max_spawn_depth` (default 2).

代码:`MAX_DEPTH = 1`(4.1)。`delegation.md` 第 303 行与 `configuration.md` 第 2270 行都写的是 1。

**▲4 —— `configuration.md` 说 `max_spawn_depth` 被"钳制到 1–3"。**

`website/docs/user-guide/configuration.md:2270 @ 863e313`
>   max_spawn_depth: 1                        # Delegation tree depth cap (1-3, clamped). 1 = flat (default): parent spawns leaves that cannot delegate. 2 = orchestrator children can spawn leaf grandchildren. 3 = three levels.

同一断言在 `configuration.md` 第 2284 行的散文里再说一次:"`max_spawn_depth` controls the
delegation tree depth (clamped to 1-3)"。代码只有下限钳制、无上限(4.3 的 610–631 块;注释里明说 "No upper ceiling on spawn depth")。
同一仓库的 `delegation.md` 第 303 行写的是 "There is no upper ceiling" —— 两份文档互相打架,代码站 `delegation.md`。

**▲5 —— `configuration.md` 说 `delegation.api_key` 缺省时回落到 `OPENAI_API_KEY`。**

`website/docs/user-guide/configuration.md:2267 @ 863e313`
>   # api_key: "local-key"                    # API key for base_url (falls back to OPENAI_API_KEY)

同一句在 `configuration.md` 第 1151 行再出现一次。代码:缺省时返回 `None`,由 `_build_child_agent` 回落到
**父 agent 的 key**,而且 docstring 明说这正是为了让 `MINIMAX_API_KEY` / `DASHSCOPE_API_KEY`
这类不放在 `OPENAI_API_KEY` 里的 provider 免于重复配置。

`tools/delegate_tool.py:3536-3542 @ 863e313`
```python
        # When delegation.api_key is not set, return None so _build_child_agent
        # falls back to the parent agent's API key via the credential inheritance
        # path (effective_api_key = override_api_key or parent_api_key). This
        # lets providers that store their key in a non-OPENAI_API_KEY env var
        # (e.g. MINIMAX_API_KEY, DASHSCOPE_API_KEY) work without requiring
        # callers to duplicate the key under delegation.api_key.
        api_key = configured_api_key  # None → inherited from parent in _build_child_agent
```

**▲6 —— `delegation.md` 的 "## Max Iterations" 一节教用户在调用里传 `max_iterations`。**
整节判定:小节标题 "Max Iterations",正文一句 + 一段示例代码,示例里的参数在 schema 里不存在、
且在实现里被显式丢弃。

`website/docs/user-guide/features/delegation.md:171 @ 863e313`
> Each subagent has an iteration limit (default: 50) that controls how many tool-calling turns it can take:

紧随其后的示例(第 174–178 行)写着 `max_iterations=10  # Simple task, don't need many turns`。
代码见 1.4 闸 5(2858–2872 块):调用方给的值只会被 `logger.debug` 记一笔然后丢掉。
括号里的 "(default: 50)" 本身是对的,错的是"你可以在调用里设它"这层暗示 + 示例。

**▲7 —— "每个子 agent 有自己的终端会话(与父 agent 分离)"。**

`website/docs/user-guide/features/delegation.md:327 @ 863e313`
> - Each subagent gets its **own terminal session** (separate from the parent)

代码:`_resolve_container_task_id` **故意**把子 agent 的 task_id 折叠回 `"default"`,
注释原文是 "so subagents share the parent's long-lived container (one bash, one /workspace,
one set of installed packages)"(2.3)。孩子私有的只有 cwd 记录与 file_state bucket。
本文件自己的模块 docstring 第 12 行 "Its own task_id (own terminal session, file ops cache)"
同样是这个说法,一并列在 8.1。

**▲8 —— 超时诊断转储的内容清单被写多了。**

`website/docs/user-guide/features/delegation.md:206 @ 863e313`
> With a hard cap configured, if a subagent times out having made **zero** API calls (usually: provider unreachable, auth failure, or tool-schema rejection), `delegate_task` writes a structured diagnostic to `~/.hermes/logs/subagent-timeout-<session>-<timestamp>.log` containing the subagent's config snapshot, credential-resolution trace, any early error messages, and stack traces for **all** live threads (not just the child's own) — a child parked waiting on a nested helper thread is indistinguishable from a slow provider without the full picture.

实际写入的小节只有 9 个:Timeout / Goal / Child config / Toolsets / Prompt-schema sizes /
Activity summary / Worker thread stack / All thread stacks / Notes。**没有 credential-resolution trace,
也没有 early error messages**。文件名里的 `<session>` 实为 `subagent_id`(`sa-<idx>-<8 位 hex>`)。

`tools/delegate_tool.py:1654-1656 @ 863e313`
```python
        subagent_id = getattr(child, "_subagent_id", None) or f"idx{task_index}"
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        dump_path = logs_dir / f"subagent-timeout-{subagent_id}-{ts}.log"
```

判据(可复现):对 `_dump_subagent_timeout_diagnostic` 函数体
`grep -n '_w("## '` 得到的 9 个小节标题即为全部内容。

```verify
cd /home/user/hermes-agent && sed -n '1640,1793p' tools/delegate_tool.py | grep -n '_w("## '
```

### 7.2 ◇(代码有、文档无)

- **◇1 实时转写日志的 `manifest.json` 与"父 agent 也能读"这件事**在 `delegation.md` 第 272–286 行有,
  但**返回给模型的 payload 里还带了一段 `live_transcripts_hint` 文案**(1.7 的 3358–3379 块),
  即 harness 主动教模型"你可以 `tail -f` 这些文件看孩子干活"。文档没提这条对模型的指令。
- **◇2 `delegation.subagent_auto_approve` 的语义**在 `AGENTS.md` 第 1009 行只作为配置键名出现,
  没有任何文档说明"默认是 auto-**deny**,不是继承父 agent 的审批模式"。这是安全相关的默认值,
  在 `website/docs` 全文检索不到解释(见下方搜索面)。
- **◇3 子 agent 摘要末尾会被追加"你读过的文件被孩子改了"提醒**(1.6.5),文档未述。
- **◇4 `delegate_task` 的顶层描述里有一条"孩子的摘要是自述,不是已核实的事实"的行为规则**,
  要求模型对外部副作用(上传/远程写/发布)自行取证。这是很有价值的一条 harness 设计,文档未述。

`tools/delegate_tool.py:3703-3708 @ 863e313`
```python
        "- Child summaries are SELF-REPORTS, not verified facts: a child "
        "claiming \"uploaded successfully\" or \"file written\" may be wrong. "
        "For external side effects (uploads, remote writes, publishing), "
        "require a verifiable handle (URL, ID, absolute path) and verify it "
        "yourself — fetch the URL, stat the file, read back the content — "
        "before telling the user the operation succeeded.\n"
```

**◇2 的搜索面**:`grep -rn "subagent_auto_approve" website/ AGENTS.md README.md` 全部命中如下,
只有 `AGENTS.md` 的配置键罗列一处,无任何语义说明。

```verify
cd /home/user/hermes-agent && grep -rn "subagent_auto_approve" website/ AGENTS.md README.md
```

### 7.3 ■(代码缺陷,2 条)

**■1 —— 异步池满退回同步执行时,孩子已经被从父 agent 的中断链上摘掉了,而注释声称"仍然挂着"。**

顺序是确定的:先摘链(第 3278–3288 行),后判断派发结果;派发被拒时才走同步。

`tools/delegate_tool.py:3275-3288 @ 863e313`
```python
        # Detach every child from the parent's interrupt-propagation list — the
        # batch's lifecycle is owned by the async registry now, not the parent
        # turn. _build_child_agent attached them (correct for sync runs).
        if hasattr(parent_agent, "_active_children"):
            _ac_lock = getattr(parent_agent, "_active_children_lock", None)
            for _c in _child_agents:
                try:
                    if _ac_lock:
                        with _ac_lock:
                            parent_agent._active_children.remove(_c)
                    else:
                        parent_agent._active_children.remove(_c)
                except ValueError:
                    pass
```

`tools/delegate_tool.py:3390-3398 @ 863e313`
```python
        # Pool at capacity / schedule failure — children are still attached
        # (we detach above only on the parent list, but the async unit was
        # never accepted, so re-attaching isn't needed: we just run inline).
        logger.info(
            "delegate_task: async pool at capacity (%s); running the whole "
            "batch synchronously instead.",
            dispatch.get("error", "rejected"),
        )
        _cap_result = _execute_and_aggregate()
```

注释的落点是 "so re-attaching isn't needed"(所以不必重新挂回去)——**这个判断是错的**:
父 agent 侧的中断传播**只**遍历 `_active_children`(1.5.6 的 run_agent 3149–3158 块),
而"内联同步执行"恰恰是这张表唯一起作用的场景。孩子已不在表里,`/stop` 够不着它们。
另一条取消通道 `_batch_interrupt` 只交给了异步注册表,而这一支恰恰是"注册表拒绝了本次派发"。

对照组:**另一条**同步回退——"这个会话根本收不了异步结果"那一条(1.7 的 3222–3236 块)——
发生在第 3222 行、**早于**第 3278 行的摘链,所以它不受影响。两条回退只差 60 行,行为却不同,
这也是这条 ■ 容易被漏掉的原因。

后果分两种:

- `n_tasks >= 2`:批量循环仍会轮询 `parent_agent._interrupt_requested`(1.7 的 3035–3045 块),
  父 agent 的这一轮能结束,但**孩子从未收到中断信号**,继续在后台线程里烧 token。
- `n_tasks == 1`:走的是"直接调用 `_run_single_child`"那一支(1.7 的 3007–3011 块),
  **完全没有中断轮询**;父 agent 这一轮会一直阻塞到孩子自己结束,`/stop` 两边都够不着。

判据(可复现,纯读码):下面这条命令的输出里,`delegate_task` 体内的两处
`_active_children.remove`(3284 / 3286)必须**早于**容量回退处的 `_execute_and_aggregate()`(3398),
而"会话收不了异步结果"那条回退(3227)必须**早于**摘链。两个大小关系都成立即证实本条。
(输出里的 2598 / 2600 属于 `_run_single_child` 的 `finally`,3178 是注释,3410 是同步出口,均无关。)

```verify
cd /home/user/hermes-agent && grep -n "_active_children.remove\|_execute_and_aggregate()" tools/delegate_tool.py
```

**■2 —— `child.close()` 在超时抛弃孩子后无条件调用,而紧随其后的 Relay 收尾专门防了这件事。**

同一个 `finally` 块里,`child.close()`(5.4 的 2604–2611 段)没有任何"worker 是否还在跑"的判断;
下面 15 行的 Relay 收尾却显式写了 "must not pop a scope while a timed-out child worker is still
unwinding" 并用 `has_active_turn` 挡住(5.4 的 2613–2626 块)。

而超时路径的抛弃是确定的:`request_hard_interrupt` 只是**请求**停止(协作式,下一次迭代边界才生效),
`_timeout_executor.shutdown(wait=False)` 不等,函数随即 return 进 `finally`。

**受影响的具体是哪两步**:`close()` 的第 1~4 步按 `task_id` 查表,对子 agent 查不到东西(5.7),
所以真正会在"孩子还在跑"时动手的是——

- **第 5 步**:遍历并 `close()` 孩子自己的孙子 agent(递归拆);
- **第 6 步**:`self.client = None` 并关掉 OpenAI / httpx 客户端 —— 孩子的 worker 线程可能
  正卡在一次未完成的 HTTP 请求上(超时的最常见形态就是"卡在某次 API 调用里",见 5.2 的
  `after_llm_calls` 分支)。

判据(可复现,纯读码):在 `_run_single_child` 的 `finally` 中,`child.close()` 的调用点
不被任何 `has_active_turn` / `is_alive` / `join` 类判断包裹,而其后 15 行的 Relay 段被包裹。

```verify
cd /home/user/hermes-agent && sed -n '2600,2630p' tools/delegate_tool.py
```

严重性判断:这是**竞态窗口**而非必然故障——超时本来就默认关闭(5.1),开了才可能撞上;
且各清理步骤各自 try/except。但它与同一个 `finally` 块内另一处的处理不一致,属于"防了一半"。

### 7.4 ◎(文档成立但显著保守,1 条)+ 已核对无异议项

**已核对无异议(不计任何记号)** —— `delegation.md` 第 341 行的对照表写 execute_code
"7 tools via RPC",与 `SANDBOX_ALLOWED_TOOLS` 的 7 个完全一致,既不保守也不夸张。

**◎1** —— `delegation.md` 第 24 行写 "Up to 3 concurrent subagents by default (configurable, no hard ceiling)"。
成立且准确。真正保守的是它没说"这个 3 同时也是**单次调用的任务条数上限**"——超过就直接报错,
不是排队(1.4 闸 8)。读者容易以为可以提交 10 条任务、按 3 并发排队跑。

---

## 8. 代码内自述与代码不符(不计入 ▲/■,但重实现时会被误导)

**8.1** 模块 docstring 第 12 行 "Its own task_id (own terminal session, file ops cache)" —— 见 ▲7,
容器是共用的。

`tools/delegate_tool.py:10-13 @ 863e313`
```python
Each child gets:
  - A fresh conversation (no parent history)
  - Its own task_id (own terminal session, file ops cache)
  - The parent's toolsets, with child-only blocked tools stripped
```

**8.2** `_strip_blocked_tools` 的 docstring 说复合黑名单包含 `code_execution`,代码里只有 `delegation`。
测试 `test_execute_code_not_blocked` 固化的是代码那一侧(3.6)。

`tools/delegate_tool.py:901-910 @ 863e313`
```python
    """Remove toolsets that contain only blocked tools.

    The strip set is derived from DELEGATE_BLOCKED_TOOLS plus the explicit
    composite/scenario toolsets (delegation, code_execution) that have no
    one-to-one tool. This keeps the blocklist and the strip set in lockstep
    so new blocked tools can't silently leak through as toolset names.
    """
    # Composite toolsets that should never pass through to children, even
    # though their individual tools aren't all in DELEGATE_BLOCKED_TOOLS.
    _COMPOSITE_BLOCKED_TOOLSETS = frozenset({"delegation"})
```

**8.3** `delegate_task` 里深度闸的注释说 "default 2 for parity with the original MAX_DEPTH constant",
而 `MAX_DEPTH = 1`。

`tools/delegate_tool.py:2845-2846 @ 863e313`
```python
    # Depth limit — configurable via delegation.max_spawn_depth,
    # default 2 for parity with the original MAX_DEPTH constant.
```

**8.4** `_dump_subagent_timeout_diagnostic` 的 docstring 说写到 `~/.hermes/logs/subagent-<sid>-<ts>.log`,
实际文件名是 `subagent-timeout-<sid>-<ts>.log`。

`tools/delegate_tool.py:1632-1636 @ 863e313`
```python
    See issue #14726: users hit "subagent timed out after 300s with no response"
    with zero API calls and no way to inspect what happened. This helper
    writes a dedicated log under ``~/.hermes/logs/subagent-<sid>-<ts>.log``
    capturing the child's config, system-prompt / tool-schema sizes, activity
    tracker snapshot, and the worker thread's Python stack at timeout.
```

**8.5** `_build_child_system_prompt` 的签名默认 `max_spawn_depth: int = 2`,与 `MAX_DEPTH = 1` 不一致。
实际调用点总是显式传参,所以不影响行为,但读签名会误判默认值。

`tools/delegate_tool.py:795-803 @ 863e313`
```python
def _build_child_system_prompt(
    goal: str,
    context: Optional[str] = None,
    *,
    workspace_path: Optional[str] = None,
    role: str = "leaf",
    max_spawn_depth: int = 2,
    child_depth: int = 1,
) -> str:
```

**8.6** `_run_single_child` 第 1991 行的 `_saved_tool_names` 赋值后**从未被读**(`finally` 里用的是
另一个名字 `saved_tool_names`,重新从 `child` 上取)。死变量,不影响行为。

`tools/delegate_tool.py:1987-1993 @ 863e313`
```python
    # Restore parent tool names using the value saved before child construction
    # mutated the global. This is the correct parent toolset, not the child's.
    import model_tools

    _saved_tool_names = getattr(
        child, "_delegate_saved_tool_names", list(model_tools._last_resolved_tool_names)
    )
```

判据:

```verify
cd /home/user/hermes-agent && grep -n "_saved_tool_names" tools/delegate_tool.py
```
输出四行:1991(赋值)、2586(**另一个名字** `saved_tool_names`)、2646(在别的函数里设属性)、
1992(1991 那条语句的续行)。1991 那个带前导下划线的名字没有任何读取点。

---

## 9. 移交项(每条带锚点文件 + 一句话现象)

- **H-1(■1 的处置)**:`tools/delegate_tool.py` 第 3390 行 —— 异步池满退回同步时,孩子已在第 3278–3288 行
  被从 `parent_agent._active_children` 摘除,注释却写 "children are still attached";
  `n_tasks==1` 时该批次完全没有中断轮询。
  测试覆盖初查为**零**——搜索面:`grep -rniE "capacity|rejected" tests/tools/test_delegate*.py`
  对 7 个 delegate 测试文件命中 0 行,即容量回退这一支没有任何用例。
- **H-2(■2 的处置)**:`tools/delegate_tool.py` 第 2607 行 —— `child.close()` 在超时抛弃路径上无条件执行,
  而同一 `finally` 块第 2613–2626 行的 Relay 收尾显式判断了 "timed-out child worker is still unwinding"。
  需要判断 `close()` 的各步骤(`process_registry.kill_all` / `cleanup_vm` / `cleanup_browser`)
  在孩子仍活跃时是否真的有害——这要读 `tools/process_registry.py` 与 `tools/environments/`,超出本轮范围。
- **H-3(跨文件,影响隔离结论)**:`tools/code_execution_tool.py` 第 1092 行 ——
  `if not sandbox_tools: sandbox_tools = SANDBOX_ALLOWED_TOOLS`:当孩子的 toolset 与那 7 个白名单
  **交集为空**时,回退把 7 个**全部**授予,包括 `terminal` / `write_file` / `patch`。
  一个被窄化到只剩(比如)`vision` 的子 agent,可能经由 `execute_code` 重新拿到写文件与执行命令的能力。
  需要 R9 的 execute_code 负责人确认此路径在子 agent 场景下能否真的走到。
- **H-4(文档修订面)**:`AGENTS.md` 第 985–1005 行一节有 3 条 ▲(▲1/▲2/▲3),
  且与 `website/docs/user-guide/features/delegation.md` 自相矛盾;
  `configuration.md` 第 2267 行与第 2270 行各 1 条(▲4/▲5)。
  若后续轮次要统计"地图腐烂程度",本簇合计 ▲ 8 条(其中 5 条集中在两份文件的 delegation 段)。
- **H-6(生命周期口径,需要 R9 的 terminal / process_registry 负责人确认)**:
  `run_agent.py:4228` 用 `task_id=self.session_id` 调 `process_registry.kill_all`,
  而子 agent 的后台进程登记在折叠后的 `"default"` 名下(`tools/terminal_tool.py:2695`),
  两个键不相等,所以子 agent 的 `terminal(background=True)` 进程活到**进程级**全杀为止。
  现象:一次跑完的子 agent 留下的后台进程,在同一个 CLI 会话里用 `process` 工具仍然列得出来。
  需要确认这是有意的(与共享容器一致)还是漏网。
- **H-5(没有查完)**:`tools/async_delegation.py`(1,515 行)是后台委派的另一半——
  停滞监视器、持久化完成事件、重启恢复、所有权认领。本轮只读到了它的容量拒绝分支(6.2)。
  `tools/delegation_live_log.py`(424 行)同理,只确认了接口形状。

---

## 10. 可迁移的设计要点(造自己的 harness 时抄什么)

1. **让"给模型看的工具描述"随配置动态重建。** 模型读到的"最多 3 个"是这个用户的真实 3。
   代价是每次 `get_definitions()` 都要读一次配置——所以要么像这里一样用 readonly 加载器
   跳过深拷贝,要么加缓存。
2. **把 harness 的硬约束写成提示词里的字面事实**(4.5)。比"让模型自己发现被拒绝"省一整轮。
3. **能力来自角色,不来自继承**(3.3 的 delegation 无条件加回)。继承式授权在深度 ≥2 时会变得
   不可推理:一个 orchestrator 的孩子是否能派,不该取决于它爷爷的 toolset 长什么样。
4. **降级只在一个地方发生**(1.5.1)。role 的降级、深度的钳制、开关的否决全部收在
   `_build_child_agent` 的四行里,规则因此可以一句话说清。
5. **默认更严,而不是默认继承**(2.2)。子 agent 线程的审批默认 deny;开放是显式 opt-in 的一个配置键。
   同时把**不可协商的那部分**(hardline + 用户黑名单)放在所有旁路之前,让 opt-in 也绕不过去。
6. **超时不是首选的止损手段。** 这套代码把默认墙钟超时**去掉了**,改用"心跳 + 三信号停滞检测",
   并且检测到停滞时**不杀**,而是停止给上游续命、让上游那层原本就有的超时去开枪(1.6.2)。
   理由很硬:合法的重活(深度代码审查、大扇出调研、慢推理模型)会被固定墙钟误杀,
   而误杀是不可恢复的;停滞检测的误判只是"晚一点被上游收掉"。
7. **孩子的输出必须按父 agent 的剩余上下文来裁,而不是按固定字符数。**(5.5)
   N 份摘要同时进场才是真正的溢出源;裁的时候保头也保尾,并把全文落到一个**父 agent 真的能读到的位置**。
8. **异步的降级路径要想清楚。** 这里有两条:会话本身收不了异步结果、异步池满,
   两条都退回同步并**在结果里告诉模型发生了什么**——而不是失败或静默改变语义。
9. **进程级全局状态要"存-改-还"。** `model_tools._last_resolved_tool_names` 是个典型:
   造孩子会改它,于是构造被一把锁包住,构造完立刻还原,并把快照挂在孩子身上供 `finally` 二次还原(6.4)。
10. **观测面要一开始就设计成可寻址的。** 一个 `subagent_id` 同时是:进度事件的 key、
    活跃注册表的 key、file_state 的 task_id、TUI 控制(kill/pause)的目标、诊断文件名的一部分。
    这让"杀掉第 2 个孩子"这种操作根本不需要新增映射表。
11. **中继给上游的东西要脱敏。** 工具参数只保留参数名 + 副作用目标,URL 重建以剥掉凭据(6.7)。
    钩子和 UI 是会被落盘、被转发的。
12. **抛弃线程要用 daemon 池。** 标准库 `ThreadPoolExecutor` 的 `atexit` 会无条件 join 所有 worker,
    一个卡死的孩子就能让 CLI 永远退不出去(1.6.4)。

---

## 11. 延伸

- 后台委派的另一半:`tools/async_delegation.py`、`tools/delegation_live_log.py`(本轮未精读)。
- 插件侧的子 agent 生命周期 API:`agent/subagent_lifecycle.py`,它复用本文件的
  `_build_child_preserving_parent_tools` 与 `_run_child_lifecycle`。
  **它是 `toolsets` 求交那一支(3.2)的唯一实际调用方** —— 搜索面:
  `grep -rn "_build_child_preserving_parent_tools\|_build_child_agent" --include=*.py .` 排除 `tests/` 后
  共 15 行命中,其中**调用**(而非定义/注释)只有两处:`tools/delegate_tool.py:2963`(硬传 `toolsets=None`)
  与 `agent/subagent_lifecycle.py:225`(可传 `allowed_toolsets`)。
- 行为规格参照:`tests/tools/test_delegate.py`(63 个用例)、`test_delegate_toolset_scope.py`、
  `test_delegate_kanban_isolation.py`、`test_delegate_summary_budget.py`、
  `test_delegate_subagent_timeout_diagnostic.py`、`test_delegate_composite_toolsets.py`。
