# r7c-raw-slash-b · `gateway/slash_commands.py` 第 2000–4000 行

> 底稿。基线 `863e31318553cda8ad61df681d08175364d4164b`(下称 `863e313`)。
> 溯源约定:凡对代码行为的断言,紧跟 `路径:行号 @ 863e313` + 代码原文块。
> 精读区间 **2000–4000**(全文 5693 行);为交代上下文,少量引用区间外代码时会显式标注
> 「区间外」。

---

## 0. 本切片一句话

**这 2000 行是 gateway 侧 22 个「会话/配置类」slash 命令的处理器本体:每个都是
「自己 split() 解析 → 直接改 runner 的进程内状态 → 顺手把 config.yaml 读-改-写回去 →
evict 缓存 agent → 返回一段 i18n 文本」,没有统一的参数解析层、没有统一的确权层、
没有统一的输出层;唯一被抽象出来的共用件是三个:`_save_gateway_config_key`(配置写)、
`_try_send_choice_picker`(交互式选择器)、`_request_slash_confirm`(审批确认)。**

---

## 1. 结构总览

`gateway/slash_commands.py` 只有一个类 `GatewaySlashCommandsMixin`(`gateway/slash_commands.py:101 @ 863e313`),
`GatewayRunner` 通过 MRO 继承它。模块头部说明了这次拆分的动机:

```python
# gateway/slash_commands.py:1-14 @ 863e313
"""Gateway slash-command handlers for GatewayRunner.

Extracted from ``gateway/run.py`` (god-file decomposition Phase 3b). These are
the in-session slash commands (/model, /reset, /usage, /compress, ...) the
gateway dispatches from ``_handle_message``. There are 42 of them (~3,200 LOC);
lifting them into a mixin that ``GatewayRunner`` inherits keeps every
``self._handle_*_command`` dispatch + test reference working via the MRO, while
removing the bulk from run.py.

Module-level run.py helpers a handler needs (``_hermes_home``,
``_load_gateway_config``, ``_resolve_gateway_model``, etc.) are imported lazily
inside the handler body — a deferred ``from gateway.run import ...`` resolves at
call time (run.py fully loaded by then), avoiding an import cycle.
"""
```

> 注:文档字符串说 "42 of them (~3,200 LOC)",实测 `_handle_*_command` 定义 **52 个**、
> 文件 **5693 行**。见 §4 ◇-01。

**切片内容分布**(行区间 → 内容):

| 行区间 | 内容 | 备注 |
|---|---|---|
| 2000–2059 | `/model` **picker 回调**尾部:config.yaml 持久化 + 确认文案 | 属 `_on_model_selected_scoped`(起于 1812,区间外) |
| 2061–2086 | `_on_model_selected` — profile 作用域包装 + `send_model_picker` 调用 | |
| 2088–2121 | `/model` **无参文本兜底**:列出已认证 provider | |
| 2123–2166 | `/model` **打字路径**:skew guard → `switch_model`(off-loop)→ 预检警告增强 | |
| 2167–2398 | `_finish_switch()` — 换模型的「提交事务」:agent 原地换 → 会话 DB → 覆盖表 → 写透 → evict → config.yaml → 文案 | |
| 2400–2445 | **贵模型确认闸**:`_request_slash_confirm`(本切片与审批体系的接口) | |
| 2447–2491 | `/codex-runtime` | |
| 2492–2560 | `/personality` | |
| 2562–2601 | `/retry` | |
| 2603–2773 | `/goal`(9 个子命令 + 契约解析) | |
| 2775–2845 | `/heartbeat` | |
| 2847–2889 | `/refine` | |
| 2891–2940 | `/subgoal` | |
| 2942–2989 | `/undo [N]` | |
| 2991–3060 | `/sethome` | |
| 3062–3141 | `/voice` | |
| 3143–3189 | `/rollback` | |
| 3191–3246 | `/diff` | |
| 3248–3279 | `_gateway_session_diff` — `/diff session` | |
| 3281–3299 | `_fenced_truncated_diff` — **本切片唯一的通用截断器** | |
| 3301–3336 | `/background` | |
| 3338–3359 | `_save_gateway_config_key` — **配置写共用件** | |
| 3361–3416 | `_apply_reasoning_selection` — 打字/点选共用的 reasoning 应用器 | |
| 3418–3444 | `_reasoning_picker_choices` | |
| 3446–3482 | `_try_send_choice_picker` — **选择器共用件** | |
| 3484–3575 | `/reasoning` | |
| 3577–3616 | `/memory` | |
| 3618–3677 | `/skills`(仅写审批复核面) | |
| 3679–3762 | `/fast` | |
| 3764–3779 | `/approvals` | |
| 3781–3796 | `/yolo` | |
| 3798–3860 | `/verbose` | |
| 3862–3946 | `/footer` | |
| 3948–3968 | `/compress` — profile 作用域包装 | |
| 3970–4000+ | `/compress` 本体开头(参数解析 + `--preview`)| 本体在 4331 结束,区间外 |

**一个贯穿全切片的形状**:每个 handler 都是
`event.get_command_args()` → 手写 `split()/lower()/集合匹配` → 副作用 → 返回 `str`。
`event.get_command_args()` 本身做两件事(`gateway/platforms/base.py:2149-2158 @ 863e313`):

```python
    def get_command_args(self) -> str:
        """Get the arguments after a command."""
        if not self.is_command():
            return self.text
        command_text = (self.text or "").lstrip()
        parts = command_text.split(maxsplit=1)
        args = parts[1] if len(parts) > 1 else ""
        # iOS auto-corrects -- to — (em dash) and - to – (en dash)
        args = args.replace("\u2014\u2014", "--").replace("\u2014", "--").replace("\u2013", "-")
        return args
```

**这就是全平台唯一的「命令行 tokenizer」**:它只负责剥掉命令名和修 iOS 智能破折号,
之后每个 handler 各自为政。全切片只有 `/model`(转交 `hermes_cli.model_switch.parse_model_switch_args`)、
`/codex-runtime`(转交 `crs.parse_args`)、`/reasoning` 与 `/fast`(共用
`_parse_reasoning_command_args`)、`/compress`(转交 `hermes_cli.partial_compress`)
把解析外包给了单一属主模块;其余 17 个命令都是 handler 内联手写。

---

## 2. 逐命令 / 逐机制

### 2.1 `/model` — 切片里唯一的「事务型」命令(1671–2445,切片覆盖 2000–2445)

#### 2.1.1 语法与参数解析

Docstring(区间外,1672–1682)声明了 6 种形态:`/model`、`/model <name>`、
`--once` / `--session` / `--global` / `--provider <p>`。解析全部外包:

```python
# gateway/slash_commands.py:1700-1717 @ 863e313(区间外,为理解 2000+ 必需)
        # Parse --provider, --global, --session, --once, and --refresh flags
        # via the shared single-owner parser (hermes_cli.model_switch).
        request = parse_model_switch_args(raw_args)
        ...
        if request.errors:
            # Gateway decoration: "❌ " prefix over the canonical error copy.
            return f"❌ {request.error_messages()[0]}"
        persist_global = resolve_persist_behavior(
            is_global_flag, is_session, is_once=one_turn, explicit_provider=explicit_provider,
        )
```

**设计取舍**:错误文案由 CLI 侧的解析器产出,gateway 只加一个 `❌ ` 前缀——
「单一属主 + 平台装饰」。代价是 gateway 无法给出平台特化的纠错提示(比如 Slack 上
应提示 `!model` 而非 `/model`)。

`resolve_persist_behavior` 的优先级(`hermes_cli/model_switch.py:607-620 @ 863e313`):
`--once` > `--session` > `--global` > `--provider`(默认不持久化)> `model.persist_switch_by_default`。

#### 2.1.2 两条提交路径:picker 回调 vs `_finish_switch`

`/model` 有两条**几乎重复但不完全一致**的提交代码:

- **picker 回调** `_on_model_selected_scoped`(1812–2059,切片覆盖 2000–2059)
- **打字路径** `_finish_switch`(2167–2398)

两者的提交步骤同为 7 步:①`switch_model`(off-loop)②预检压缩警告 ③缓存 agent
原地 `switch_model()` ④会话 DB `update_session_model` ⑤`_pending_model_notes`
⑥`_session_model_overrides` + 写透 session store ⑦`_evict_cached_agent` ⑧config.yaml。

**共同点(2000–2009 / 2317–2334)—— #25107 的修法**:

```python
# gateway/slash_commands.py:2317-2330 @ 863e313
                    # See the picker handler above for why custom providers need an
                    # explicit set-or-clear instead of the old lone truthy check (#25107).
                    _is_custom_target = str(result.target_provider or "").strip().lower() == "custom"
                    if result.base_url:
                        model_cfg["base_url"] = result.base_url
                    elif _is_custom_target:
                        model_cfg.pop("base_url", None)
                    if _is_custom_target:
                        if result.api_mode:
                            model_cfg["api_mode"] = result.api_mode
                        else:
                            model_cfg.pop("api_mode", None)
                    else:
                        clear_model_endpoint_credentials(model_cfg, clear_base_url=True)
```

picker 侧同形代码在 `gateway/slash_commands.py:1994-2005 @ 863e313`(切片内 2000–2005)。

**关键差异(三处,都在切片内可验证)**:

| 步骤 | picker 回调 | `_finish_switch` | 后果 |
|---|---|---|---|
| `was_auto_reset` 消费 | **无** | 2211–2212 有 | 自动重置后**点选**换模型仍会丢(#48031 只修了打字路径) |
| `--once` 一次性还原 | **无** | 2243–2250 登记 `_pending_one_turn_model_restores` | `/model --once`(裸命令)在 picker 平台被静默降级为 `--session` |
| `--once` 跳过写透 | **无**(1936–1945 无条件写透) | 2264–2273 `if not one_turn:` | 同上;还会跨重启存活 |

证据 —— `_finish_switch` 的两处 once 处理:

```python
# gateway/slash_commands.py:2243-2250 @ 863e313
            if one_turn:
                if not hasattr(self, "_pending_one_turn_model_restores"):
                    self._pending_one_turn_model_restores = {}
                self._pending_one_turn_model_restores[session_key] = (
                    restore_snapshot or {"had_override": False, "override": None}
                )
            elif hasattr(self, "_pending_one_turn_model_restores"):
                self._pending_one_turn_model_restores.pop(session_key, None)
```

```python
# gateway/slash_commands.py:2256-2269 @ 863e313
            # /model --once is intentionally EXCLUDED from the write-through:
            # a one-turn override must never survive a restart. The persisted
            # value stays at the pre-once state (the prior session override,
            # or nothing), which is exactly what the finally-restore reverts
            # the in-memory dict to. (#29923 review defect: the original
            # implementation wrote through, so a crash before the restore
            # rehydrated the once-model permanently.)
            if not one_turn:
                try:
                    await self.async_session_store.set_model_override(
                        session_key,
                        self._session_model_overrides[session_key],
                    )
```

而 picker 回调的写透**无条件**:

```python
# gateway/slash_commands.py:1933-1945 @ 863e313(区间外,与 2000+ 同一闭包)
                        # Write-through the non-secret parts to the session
                        # store so the picked model survives a gateway restart
                        # (api_key is never persisted).
                        try:
                            await _self.async_session_store.set_model_override(
                                _session_key,
                                _self._session_model_overrides[_session_key],
                            )
```

`restore_snapshot` 全文只出现两次(1765 定义、2247 使用),`grep` 证实 picker 闭包
从不引用它——所以 `/model --once`(不带模型名,在 Telegram/Discord 上会弹 picker)
的一次性语义在 picker 路径**根本不存在**。这是 ◇-02。

`_pending_one_turn_model_restores` 的消费方在区间外:`gateway/run.py:15731 @ 863e313`
在回合 `finally` 中调 `_restore_pending_one_turn_model_override`(定义在
`gateway/run.py:15763 @ 863e313`)。

#### 2.1.3 失败路径:失败的换模型必须是 no-op(#50163)

```python
# gateway/slash_commands.py:2186-2200 @ 863e313
                except Exception as exc:
                    # In-place swap rolled the agent back to the OLD working
                    # model/client and re-raised.  Abort the commit: skip DB
                    # persist, session override, cache eviction, and config
                    # write so a failed switch is a no-op rather than a dead
                    # conversation (#50163).  Without this early return the
                    # next message rebuilds a broken agent from the override.
                    logger.warning("In-place model switch failed for cached agent: %s", exc)
                    return t(
                        "gateway.model.error_prefix",
                        error=(
                            f"Model switch to {result.new_model} failed ({exc}); "
                            f"staying on {current_model}."
                        ),
                    )
```

**为什么这么设计**:`_session_model_overrides` 是「下一回合重建 agent 的唯一依据」。
一旦写进去指向坏模型,而缓存 agent 又被 evict,下一条消息就会从坏 override 重建一个
死 agent——对话永久失联。所以必须**先验证原地换成功,再提交所有其它状态**。这就是
把 7 步做成「事务」的原因:agent 原地换是唯一可回滚的一步,把它放最前当 prepare。

#### 2.1.4 事故:换模型冻结网关(#20525 / #41289)

**因果**:用户在 Telegram 敲 `/model`(无参)。`list_picker_providers` 是同步函数,
provider 缓存过期时会走 `urllib` 同步 HTTP 拉取。它直接跑在 asyncio 事件循环上 →
整个网关冻结 120–150 秒("application did not respond",所有平台轮询停摆)。
`switch_model()` 同类,冷缓存时 `requests.get` 15s 超时。

**修法**:三处 `asyncio.to_thread` 包裹(两处在切片内):

```python
# gateway/slash_commands.py:2092-2104 @ 863e313
            try:
                # Offload blocking provider-listing off the event loop so the
                # gateway doesn't freeze on a stale-cache HTTP fetch. See #41289.
                providers = await asyncio.to_thread(
                    list_authenticated_providers,
                    ...
                    max_models=5,
```

```python
# gateway/slash_commands.py:2127-2142 @ 863e313
        # Offload the switch off the event loop — switch_model() can fall
        # through to a synchronous models.dev HTTP fetch (requests.get, 15s
        # timeout) on a cold/expired cache, which freezes the gateway
        # otherwise. See #20525, #41289.
        result = await asyncio.to_thread(
            _switch_model,
            raw_input=model_input,
            ...
        )
```

测试 `tests/gateway/test_model_command_async_offload.py` 把这条契约钉成了
**变异可存活**的断言(必须经 `asyncio.to_thread` 派发、不得直接调用)。

#### 2.1.5 stale-code 守卫:`_model_switch_skew_guard`

区间外定义(`gateway/slash_commands.py:72-99 @ 863e313`),切片内在
`gateway/slash_commands.py:2124-2126 @ 863e313` 调用:

```python
        skew_error = _model_switch_skew_guard()
        if skew_error:
            return skew_error
```

**问题**:长跑网关把模块留在内存;有人在磁盘上 `git pull` 之后,换模型触发一次
首次 lazy import,撞上过期的缓存依赖,报出莫名其妙的
`cannot import name 'env_float' from 'utils'`。守卫检测 boot 版本 vs 磁盘版本不一致
就拒绝换模型,提示重启。Docstring 自己承认这是**局部治标**:

```python
# gateway/slash_commands.py:94-98 @ 863e313
    Intentionally scoped to model switching — the known, highest-risk trigger.
    Any first-time lazy import on a stale process is technically exposed; we
    don't guard every import site, only this one.
```

#### 2.1.6 输出:确认卡片

`gateway/slash_commands.py:2336-2398 @ 863e313`——逐行 `t(...)` 拼 i18n 键:
switched / provider_label / context_label / max_output_label / capabilities_label /
prompt_caching_enabled / warning_prefix / saved_global | session_only_hint。
上下文长度用 `resolve_display_context_length_async`(2358)——注意这是 **async** 版本,
而 picker 分支(2032)同样用 async 版;但 `enrich_model_switch_warnings_for_gateway`
是同步的,所以额外套了 `to_thread`(2155)。缓存提示的判据很硬编码:

```python
# gateway/slash_commands.py:2380-2386 @ 863e313
            # Cache notice
            cache_enabled = (
                (base_url_host_matches(result.base_url or "", "openrouter.ai") and "claude" in result.new_model.lower())
                or result.api_mode == "anthropic_messages"
            )
            if cache_enabled:
                lines.append(t("gateway.model.prompt_caching_enabled"))
```

> 「prompt cache(提示缓存)」= provider 侧对请求前缀做的复用折扣;这里只在
> OpenRouter+claude 或 anthropic_messages 模式下宣称开启。

#### 2.1.7 多 profile 作用域:只有 `/model` 和 `/compress` 做了

```python
# gateway/slash_commands.py:2061-2073 @ 863e313
                    async def _on_model_selected(
                        _chat_id: str, model_id: str, provider_slug: str
                    ) -> str:
                        if _picker_profile_home is None:
                            return await _on_model_selected_scoped(
                                _chat_id, model_id, provider_slug
                            )
                        from gateway.run import _profile_runtime_scope

                        with _profile_runtime_scope(_picker_profile_home):
                            return await _on_model_selected_scoped(
                                _chat_id, model_id, provider_slug
                            )
```

全 5693 行的 mixin 里,`_resolve_profile_home_for_source` 只出现 3 次:
`/profile`(358)、`/model`(1697)、`/compress`(3966)。见 §4 ◇-06。

### 2.2 `/codex-runtime`(2447–2491)

```python
# gateway/slash_commands.py:2461-2464 @ 863e313
        raw_args = event.get_command_args().strip() if event else ""
        new_value, errors = crs.parse_args(raw_args)
        if errors:
            return "❌ " + "\n❌ ".join(errors)
```

副作用:`crs.apply(cfg, new_value, persist_callback=save_config if new_value is not None else None)`
(2473–2477)——**无参时传 `None` 作为 persist_callback**,即「查询不落盘」。
真正变更时 evict 缓存 agent:

```python
# gateway/slash_commands.py:2479-2487 @ 863e313
        # On a real change, evict the cached agent so the new runtime takes
        # effect on the next message rather than waiting for cache TTL.
        if result.success and new_value is not None and result.requires_new_session:
            try:
                session_key = self._session_key_for_source(event.source)
                self._evict_cached_agent(session_key)
            except Exception:
                logger.debug("could not evict cached agent after codex-runtime change",
                             exc_info=True)
```

输出:`f"{'✓' if result.success else '✗'} {result.message}"`(2489–2490)——
**不走 i18n**,与 `/model` 的全 `t()` 风格不一致。

### 2.3 `/personality`(2492–2560)

参数:`args = event.get_command_args().strip().lower()`(2497)——**整串小写**,
所以 personality 名字必须是小写键才能命中(2542 `elif args in personalities`)。

三分支:无参列表 / `none|default|neutral` 清除 / 命中则设置。副作用是**双写**:

```python
# gateway/slash_commands.py:2546-2555 @ 863e313
            try:
                if "agent" not in config or not isinstance(config.get("agent"), dict):
                    config["agent"] = {}
                config["agent"]["system_prompt"] = new_prompt
                atomic_config_write(config_path, config)
            except Exception as e:
                return t("gateway.personality.save_failed", error=str(e))

            # Update in-memory so it takes effect on the very next message.
            self._ephemeral_system_prompt = new_prompt
```

**取舍**:落盘 + 进程内变量双写,换来「下一条消息立刻生效」而不必 evict agent。
但它写的是**全局 system_prompt**,不是会话级——一个人在 Telegram 改人格,
Discord 上的会话下次重建 agent 时也会拿到。

**一个小缺陷**:预览截断只作用在 `system_prompt` 上,`description` 不截断:

```python
# gateway/slash_commands.py:2513-2518 @ 863e313
            for name, prompt in personalities.items():
                if isinstance(prompt, dict):
                    preview = prompt.get("description") or prompt.get("system_prompt", "")[:50]
                else:
                    preview = prompt[:50] + "..." if len(prompt) > 50 else prompt
```

`[:50]` 绑在 `prompt.get("system_prompt", "")` 上,`or` 的左操作数 `description`
原样输出。一个 5000 字的 description 会整段进消息。

### 2.4 `/retry`(2562–2601)

**做的事**:找最后一条**真实**用户消息 → 截断 transcript 到它之前 → 用它伪造一个
新 `MessageEvent` → 重新走 `_handle_message`。

```python
# gateway/slash_commands.py:2568-2580 @ 863e313
        # Find the last *real* user message. Timeline bookkeeping rows carry
        # role=user + display_kind (model_switch / async_delegation_complete /
        # auto_continue / hidden); clients never count them as user turns.
        # Without this filter /retry rewrote the transcript around a marker
        # and re-sent opaque bookkeeping text (same class as the TUI ordinal).
        last_user_msg = None
        last_user_idx = None
        for i in range(len(history) - 1, -1, -1):
            msg = history[i]
            if msg.get("role") == "user" and not msg.get("display_kind"):
                last_user_msg = msg.get("content", "")
                last_user_idx = i
                break
```

> 「display_kind」= transcript 行上的展示分类标记;带它的 role=user 行是**时间线记账行**
> (比如「模型刚被切换」的提示),不是用户真的说过的话。

**副作用与失败路径**:
- `rewrite_transcript(session_id, truncated)`(2587)——真正落盘的截断;
- `session_entry.last_prompt_tokens = 0`(2589)——**只改内存,不落盘**
  (对比 `/compress` 在 4254 调 `update_session(...)` 落盘);
- 重入 `self._handle_message(retry_event)`(2601)。

**伪造事件丢了什么**:

```python
# gateway/slash_commands.py:2592-2598 @ 863e313
        retry_event = MessageEvent(
            text=last_user_msg,
            message_type=MessageType.TEXT,
            source=source,
            raw_message=event.raw_message,
            channel_prompt=event.channel_prompt,
        )
```

没有 `message_id`(回复锚点丢失)、没有 `media_urls`/`media_types`(重试一条带图消息
会丢图)、没有 `auto_skill`。对比 `/goal` 的 kickoff 事件(2756–2762)就带了 `message_id`。

**回归钉子**:`tests/gateway/test_retry_response.py`——"/retry must return the agent
response, not None";`tests/gateway/test_retry_replacement.py::test_gateway_retry_replaces_last_user_turn_in_transcript`。

### 2.5 `/goal`(2603–2773)—— 切片里子命令最多的命令

**语法**(实测,以代码为准):

| 形态 | 行号 | 行为 |
|---|---|---|
| `/goal` / `/goal status` | 2621–2622 | `mgr.status_line()` |
| `/goal show` | 2625–2626 | status + `render_contract()` |
| `/goal pause` | 2628–2639 | 暂停 + 清 pending continuation |
| `/goal resume` | 2641–2645 | |
| `/goal clear\|stop\|done` | 2647–2657 | 清空 + 清 pending continuation |
| `/goal wait <pid> [reason]` | 2660–2675 | 把目标循环挂在某个进程上 |
| `/goal unwait` | 2678–2681 | |
| `/goal gate [list\|add <cmd>\|remove <N>\|rm <N>\|clear]` | 2684–2713 | 确定性质量闸 |
| `/goal draft <objective>` | 2718–2732 | 用辅助 LLM 起草完成契约 |
| 其它文本 | 2735–2773 | 解析内联 `field: value` 契约 + 设为新目标 |

**参数解析全部手写**,典型:

```python
# gateway/slash_commands.py:2660-2669 @ 863e313
        if lower == "wait" or lower.startswith("wait "):
            wait_arg = args[len("wait"):].strip()
            if not wait_arg:
                return "Usage: /goal wait <pid> [reason]"
            wtokens = wait_arg.split(None, 1)
            try:
                pid = int(wtokens[0])
            except ValueError:
                return "/goal wait: <pid> must be an integer process id."
            reason = wtokens[1].strip() if len(wtokens) > 1 else ""
```

注意 `lower.startswith("wait ")` 的判据用的是**小写串**,而切片再从**原串** `args`
上按同样长度切——大小写不同但长度相同,所以 `/goal WAIT 123` 也能工作。这是有意的
(保住 reason 的原始大小写),但很脆:任何 unicode 大小写变长的情况(如 `ı`→`I`)
会切错位。

**副作用最重的分支是「设新目标」**:

```python
# gateway/slash_commands.py:2750-2765 @ 863e313
        # Queue the goal text as an immediate first turn so the agent
        # starts making progress. The post-turn hook takes over after.
        adapter = self.adapters.get(event.source.platform) if event.source else None
        _quick_key = self._session_key_for_source(event.source) if event.source else None
        if adapter and _quick_key:
            try:
                kickoff_event = MessageEvent(
                    text=state.goal,
                    message_type=MessageType.TEXT,
                    source=event.source,
                    message_id=event.message_id,
                    channel_prompt=event.channel_prompt,
                )
                self._enqueue_fifo(_quick_key, kickoff_event, adapter)
            except Exception as exc:
                logger.debug("goal kickoff enqueue failed: %s", exc)
```

`_enqueue_fifo` 定义在 `gateway/run.py:7691 @ 863e313`。即:**`/goal <text>` 会立刻
造出一个用户回合**,而不是等下一条消息。

**「运行中」保护不在这里,在调度层**:`_busy_goal_command`(`gateway/run.py:14319-14338 @ 863e313`):

```python
        _is_control = (
            not _goal_arg
            or _goal_arg in {"status", "pause", "resume", "clear", "stop", "done", "unwait"}
            or _goal_verb in {"wait", "gate"}
        )
        if _is_control:
            return await self._handle_goal_command(event)
        return "Agent is running — use /goal status / pause / clear / wait mid-run, or /stop before setting a new goal."
```

**白名单漏了 `show`**——`/goal show` 是纯查询(2625–2626 只读 `status_line()` +
`render_contract()`),但在 agent 运行时会被拒。见 §4 ◇-05。

### 2.6 `/heartbeat`(2775–2845)

> 「heartbeat(心跳)」= 给当前会话设一条循环提示词:会话空闲且间隔到了,
> 网关轮询器就把它当成一条普通用户消息灌进 FIFO。

**解析**(2814–2823),两种写法:

```python
# gateway/slash_commands.py:2814-2823 @ 863e313
        # Set: `/heartbeat every 10m <prompt>` (also accepts `10m <prompt>`).
        tokens = args.split(None, 2)
        interval = None
        prompt = ""
        if tokens and tokens[0].lower() == "every" and len(tokens) >= 2:
            interval = parse_interval(f"every {tokens[1]}")
            prompt = tokens[2] if len(tokens) > 2 else ""
        elif tokens:
            interval = parse_interval(tokens[0])
            prompt = args[len(tokens[0]):].strip() if interval and interval > 0 else ""
```

**三态返回值的巧思**:`parse_interval` 用 `None` = 「不是间隔」、`-1` = 「间隔太小」
(`hermes_cli/heartbeat.py:68-85 @ 863e313`),让 handler 能给出两条不同错误:

```python
# gateway/slash_commands.py:2825-2833 @ 863e313
        if interval is None:
            return (
                "Usage: /heartbeat every <interval> <prompt>  (e.g. /heartbeat every 10m Check CI)\n"
                "Also: /heartbeat status | pause | resume | clear"
            )
        if interval < 0:
            return f"Interval too small — minimum is {MIN_INTERVAL_SECONDS}s."
        if not prompt.strip():
            return "Usage: /heartbeat every <interval> <prompt> — the prompt is required."
```

**注册/注销 watch 是分散的**:`resume` 注册(2804–2805)、`clear` 注销(2810–2811)、
`set` 注册(2839–2840);`pause` **不注销**(2796–2798)——靠 manager 的状态位挡住,
watch 仍在。这是有意的(pause→resume 不需要重建 watch),但意味着 watch 表会积累
已暂停的会话。

输出全部硬编码英文(2798/2803/2806/2812/2831/2841–2845),**不走 i18n**。

### 2.7 `/refine`(2847–2889)

前置条件三连,是切片里唯一显式检查「agent 是否在跑」的 handler:

```python
# gateway/slash_commands.py:2855-2869 @ 863e313
        args = (event.get_command_args() or "").strip()
        quick_key = self._session_key_for_source(event.source) if event.source else None
        if not quick_key:
            return "Refine unavailable (no session)."
        if quick_key in self._running_agents:
            return "Agent is running — wait for the turn to finish, then /refine."

        agent = None
        cache_lock = getattr(self, "_agent_cache_lock", None)
        if cache_lock is not None:
            with cache_lock:
                cached = self._agent_cache.get(quick_key)
                agent = cached[0] if isinstance(cached, tuple) else cached if cached else None
        if agent is None:
            return "Nothing to refine yet — send a message first."
```

注意 `cached[0] if isinstance(cached, tuple) else cached if cached else None`——
对缓存条目形状做**两种**兼容(元组 vs 裸 agent),而 `/model` 的两处(2170–2177)
只认元组形状 `cached_entry[0]`。命名/形状漂移。

副作用:`agent._spawn_background_review(...)`(2877–2882)——对
`agent._session_messages` 的快照跑后台线程复盘,不动活会话。
`review_skills` 由工具名探测(2875):`"skill_manage" in getattr(agent, "valid_tool_names", set())`。

### 2.8 `/subgoal`(2891–2940)

`verb/rest` 二段解析(2909–2911),三分支:`remove <n>` / `clear` / 其余当新 subgoal。
边界:`/subgoal remove abc` → `int(rest.split()[0])` ValueError → 明确报错(2916–2919)。
返回索引用 `len(mgr.state.subgoals)`(2939)——**不是** `add_subgoal` 的返回值,
所以并发下可能报错索引。

### 2.9 `/undo [N]`(2942–2989)

```python
# gateway/slash_commands.py:2955-2964 @ 863e313
        # Parse optional turn count: "/undo" → 1, "/undo 3" → 3.
        n = 1
        raw_args = event.get_command_args().strip()
        if raw_args:
            try:
                n = int(raw_args.split()[0])
            except (ValueError, IndexError):
                return t("gateway.undo.invalid_count", arg=raw_args.split()[0])
            if n < 1:
                n = 1
```

**解析漂移(切片内 vs 调度层)**:同一次 `/undo` 调用链上有**两个** N 解析器,
容错策略相反。调度层是宽容的:

```python
# gateway/run.py:15250-15256 @ 863e313(区间外)
            _undo_n = 1
            _undo_raw = event.get_command_args().strip()
            if _undo_raw:
                try:
                    _undo_n = max(1, int(_undo_raw.split()[0]))
                except (ValueError, IndexError):
                    _undo_n = 1
```

于是 `/undo -y`(文档给 CLI 建议的「跳过确认」写法,`website/docs/reference/slash-commands.md:310`)
在 gateway 上会:调度层当成 N=1 → 弹确认框("removes the last user/assistant exchange")
→ 用户点 Approve → handler 里 `int("-y")` 抛错 → 返回 `invalid_count`。
**先确认后报错**,用户体验上是纯噪声。见 §4 ◇-07。

副作用:`rewind_session`(2967,软删除 `active=0`,保留审计)+ `last_prompt_tokens = 0`
(内存)+ `_evict_cached_agent`(2978)。**注意 2977 用 `build_session_key(source)`
而不是 `self._session_key_for_source(source)`**——切片内其它所有地方都用后者。

```python
# gateway/slash_commands.py:2974-2980 @ 863e313
        # Evict the cached agent so the next turn rebuilds from the active-only
        # transcript and memory providers refresh their per-session caches.
        try:
            session_key = build_session_key(source)
            self._evict_cached_agent(session_key)
        except Exception as e:
            logger.debug("undo: cached-agent eviction skipped: %s", e)
```

输出:回显被撤回的原文,**截到 200 字符**(2983)。

### 2.10 `/sethome`(2991–3060)

> 「home channel(主频道)」= 网关主动外发(cron 通知、后台任务结果)时的默认目的地。

**唯一做「传输层身份鉴别」的命令**。经 relay(上游中继)投递的消息不可信,
必须由 relay adapter 声明它确实代理了这个逻辑平台:

```python
# gateway/slash_commands.py:3001-3015 @ 863e313
        via_relay = getattr(source, "delivered_via_upstream_relay", False) is True
        if via_relay:
            adapter_for_source = getattr(self, "_adapter_for_source", None)
            relay_adapter = adapter_for_source(source) if callable(adapter_for_source) else None
            fronts_platform = getattr(relay_adapter, "fronts_platform", None)
            if (
                source.platform in {None, Platform.LOCAL, Platform.RELAY}
                or not getattr(source, "user_id", None)
                or not callable(fronts_platform)
                or not fronts_platform(source.platform)
            ):
                return t(
                    "gateway.set_home.save_failed",
                    error="Relay does not authenticate this logical home target",
                )
```

**三重写**(3038 config.yaml / 3047–3048 legacy env / 3054–3058 内存 config):

```python
# gateway/slash_commands.py:3035-3058 @ 863e313
        # config.yaml is canonical because it can persist the authenticated
        # logical-target provenance required by Relay after a restart.
        try:
            persist_home_channel(home, enabled_if_new=not via_relay)
        except Exception as e:
            return t("gateway.set_home.save_failed", error=e)

        # Preserve legacy home env vars for existing cron/setup consumers.
        env_key = _home_target_env_var(platform_name)
        thread_env_key = _home_thread_env_var(platform_name)
        try:
            from hermes_cli.config import save_env_value
            save_env_value(env_key, str(chat_id))
            save_env_value(thread_env_key, str(thread_id or ""))
        except Exception as e:
            logger.warning("Home config saved but legacy env persistence failed: %s", e)

        # Keep the running gateway config in sync too. The pre-restart
        # notification path reads self.config before the process reloads config.
        platform_config = getattr(self, "config").platforms.setdefault(
            source.platform,
            PlatformConfig(enabled=not via_relay),
        )
        platform_config.home_channel = home
```

失败策略分层:config.yaml 写失败 = 命令失败(3039–3040 return);env 写失败 = 只 warn
(3049–3050)。合理——env 是遗留兼容面。

`enabled_if_new=not via_relay`(3038)和 `PlatformConfig(enabled=not via_relay)`(3056):
经 relay 设的 home **不自动启用**该原生平台适配器。

### 2.11 `/voice`(3062–3141)

参数 `.strip().lower()`(3064)。六分支 + 默认切换:
`on|enable` / `off|disable` / `tts` / `channel|join` / `leave` / `status` / 其余=toggle。

三种模式值:`"voice_only"` / `"off"` / `"all"`。存进 `self._voice_mode[voice_key]`
(键由 `_voice_key(platform, chat_id)` 生成,`gateway/run.py:6352 @ 863e313`),
每次改都 `self._save_voice_modes()` 立即落盘。

**双写适配器**:除了 runner 侧的 mode,还要把 auto-TTS 开关推给 adapter
(3075 / 3081 / 3087 / 3123 / 3129)——两套状态,靠调用点纪律保持一致。

裸 `/voice` 的返回值设计值得学:既执行切换,又追加发现性说明:

```python
# gateway/slash_commands.py:3131-3141 @ 863e313
            # Bare /voice still toggles, but append an explainer so users
            # discover the on/off/tts/status subcommands (and, on Discord,
            # live voice-channel join/leave). The toggle result is shown
            # first via the {toggle} placeholder.
            supports_voice_channels = adapter is not None and hasattr(
                adapter, "join_voice_channel"
            )
            channels = (
                t("gateway.voice.help_channels") if supports_voice_channels else ""
            )
            return t("gateway.voice.help", toggle=toggle_line, channels=channels)
```

**能力探测用 `hasattr(adapter, ...)`(实例)**,而 picker 用
`getattr(type(adapter), ..., None)`(类)——见 §2.16 的对比。

冗余:`adapter` 在 3069 取过一次,status 分支在 3101 又取一遍(同一个值)。

### 2.12 `/rollback`(3143–3189)

无参 = 列表(3163–3165);有参先试 `int(arg)-1` 当序号,`ValueError` 则整串当 hash:

```python
# gateway/slash_commands.py:3172-3182 @ 863e313
        target_hash = None
        try:
            idx = int(arg) - 1
            if 0 <= idx < len(checkpoints):
                target_hash = checkpoints[idx]["hash"]
            else:
                return t("gateway.rollback.invalid_number", max=len(checkpoints))
        except ValueError:
            target_hash = arg

        result = mgr.restore(cwd, target_hash)
```

**工作目录来源是环境变量**:`cwd = os.getenv("TERMINAL_CWD", str(Path.home()))`(3160)。
`/diff` 同(3219)。即这两个命令看的是**网关进程级的 cwd**,不是每会话的——
多会话同时用会互相看到对方的 diff。

### 2.13 `/diff`(3191–3246)+ `/diff session`(3248–3279)+ 截断器(3281–3299)

**解析是「无序标志扫描」**,未知 token 被静默丢弃:

```python
# gateway/slash_commands.py:3206-3217 @ 863e313
        stat_only = False
        mode = "working"
        for arg in args.split():
            low = arg.lower()
            if low in ("--stat", "stat"):
                stat_only = True
            elif low in ("staged", "--staged", "cached", "--cached"):
                mode = "staged"
            elif low in ("all", "--all", "head"):
                mode = "all"
            elif low == "session":
                mode = "session"
```

`collect_working_diff` 其实支持 `paths` 参数(`tools/working_diff.py:70-77 @ 863e313`),
但 gateway 只传两个位置参数:

```python
# gateway/slash_commands.py:3226 @ 863e313
        result = await asyncio.to_thread(collect_working_diff, cwd, mode)
```

所以 gateway 上 `/diff src/foo.py` 与裸 `/diff` 完全等价(路径被静默忽略)。
CLI 侧文档写了 `[path...]`,messaging 侧文档没写——文档没错,但**行为差异只能靠
读两张表推断**。

**输出三层截断**(这是全切片最完整的截断样本):

```python
# gateway/slash_commands.py:3196-3202 @ 863e313
        The diff body is truncated hard here (messaging surfaces are not a
        pager); platform senders additionally split/clamp long messages to
        per-platform limits, the same way tool-progress output is truncated
        in three layers before delivery.
```

第一层 untracked 列表封顶 15 条(3241–3242);第二层 diff 正文:

```python
# gateway/slash_commands.py:3281-3299 @ 863e313
    @staticmethod
    def _fenced_truncated_diff(diff: str, max_lines: int = 60,
                               max_chars: int = 3000) -> str:
        """Fence a diff body, truncating to messaging-friendly size."""
        diff_lines = diff.splitlines()
        truncated = False
        if len(diff_lines) > max_lines:
            diff = "\n".join(diff_lines[:max_lines])
            truncated = True
        if len(diff) > max_chars:
            diff = diff[:max_chars]
            truncated = True
        note = ""
        if truncated:
            note = (
                f"\n... (truncated — {len(diff_lines)} lines total; "
                "use /diff --stat for a summary)"
            )
        return f"```diff\n{diff}{note}\n```"
```

**注意 `max_chars` 的字符裁剪不管代码围栏**:`diff[:3000]` 可能切在多字节字符
或围栏内部,但因为整体外面再包一层 ```` ```diff ```` 围栏,结果是安全的
(内层不会有裸的 ``` 除非 diff 本身含 ```)。第三层是平台发送侧的分片
(`gateway/run.py:3982-4001 @ 863e313` 展示了同类的 `MAX_MESSAGE_LENGTH` /
`max_message_length_for_chat` 逐聊天解析,那段是 tool-progress 的)。

**回归钉子**:`tests/gateway/test_diff_command.py::test_diff_long_output_truncated`。

### 2.14 `/background`(3301–3336)

```python
# gateway/slash_commands.py:3312-3336 @ 863e313
        source = event.source
        task_id = f"bg_{datetime.now().strftime('%H%M%S')}_{os.urandom(3).hex()}"

        event_message_id = self._reply_anchor_for_event(event)

        # Forward image/audio attachments so the background agent can see them.
        media_urls = list(event.media_urls) if event.media_urls else []
        media_types = list(event.media_types) if event.media_types else []

        # Fire-and-forget the background task
        _task = asyncio.create_task(
            self._run_background_task(
                prompt, source, task_id,
                event_message_id=event_message_id,
                media_urls=media_urls,
                media_types=media_types,
            )
        )
        self._background_tasks.add(_task)
        _task.add_done_callback(self._background_tasks.discard)

        preview = prompt[:60] + ("..." if len(prompt) > 60 else "")
        return t("gateway.background.started", preview=preview, task_id=task_id)
```

**`self._background_tasks.add` + `add_done_callback(discard)` 是标准的 asyncio 强引用
惯用法**——不持引用的话 `create_task` 返回的 Task 可能被 GC 掉,任务静默消失。
task_id 用 `HHMMSS + 3 字节随机`,同一秒内碰撞概率 ~1/16M,可接受但不是全局唯一。

**回归钉子**:`tests/gateway/test_background_command.py`(无参/别名 `/bg`/空 prompt
三种 usage 路径,以及无凭据时的错误投递)。

### 2.15 `_save_gateway_config_key`(3338–3359)—— 配置写共用件

```python
# gateway/slash_commands.py:3338-3359 @ 863e313
    def _save_gateway_config_key(self, key_path: str, value) -> bool:
        """Save a dot-separated key to config.yaml (shared by /reasoning, /fast
        and their interactive pickers)."""
        from gateway.run import _hermes_home
        from hermes_cli.config import read_user_config_raw
        config_path = _hermes_home / "config.yaml"
        try:
            # Write-back round-trip: raw read is correct (merged defaults must
            # not be persisted back to the user's file).
            user_config = read_user_config_raw(config_path)
            keys = key_path.split(".")
            current = user_config
            for k in keys[:-1]:
                if k not in current or not isinstance(current[k], dict):
                    current[k] = {}
                current = current[k]
            current[keys[-1]] = value
            atomic_config_write(config_path, user_config)
            return True
        except Exception as e:
            logger.error("Failed to save config key %s: %s", key_path, e)
            return False
```

**「raw read 而非 merged read」这条纪律在切片里出现 5 次**(1957–1959、2282–2284、
3345–3347、3596–3598、3651–3653),原因每次都写在注释里:合并过默认值的配置
写回去会把 Hermes 的内置默认**固化**进用户文件,以后升级默认值就改不动了。
这是自研 harness 值得抄的一条。

**返回 bool 而非抛异常**,让调用方能降级:`/reasoning --global` 写失败时退回会话级
(3405–3412)、`/fast --global` 同(3716–3727)。

### 2.16 `/reasoning` 簇(3361–3575)

#### `_apply_reasoning_selection`(3361–3416)—— 打字与点选的单一应用点

```python
# gateway/slash_commands.py:3368-3373 @ 863e313
        """Apply a /reasoning argument (typed or picked) and return the reply.

        Single application path shared by the typed `/reasoning <arg>` branch
        and the interactive choice picker, so both surfaces stay in lockstep
        with the canonical parser.
        """
```

**这是切片里最好的一个设计**,与 `/model` 的「picker 与打字两份重复提交代码」
形成鲜明对照(§2.1.2)。四类取值:

```python
# gateway/slash_commands.py:3378-3402 @ 863e313
        # Display toggle (per-platform)
        if value in {"show", "on"}:
            self._show_reasoning = True
            self._save_gateway_config_key(
                f"display.platforms.{platform_key}.show_reasoning", True
            )
            return t("gateway.reasoning.display_set_on", platform=platform_key)
        if value in {"hide", "off"}:
            self._show_reasoning = False
            self._save_gateway_config_key(
                f"display.platforms.{platform_key}.show_reasoning", False
            )
            return t("gateway.reasoning.display_set_off", platform=platform_key)

        if value == "reset":
            if persist_global:
                return t("gateway.reasoning.reset_global_unsupported")
            self._set_session_reasoning_override(session_key, None)
            self._reasoning_config = self._load_reasoning_config()
            self._evict_cached_agent(session_key)
            return t("gateway.reasoning.reset_done")

        parsed = parse_reasoning_effort(value)
        if parsed is None:
            return t("gateway.reasoning.unknown_arg", arg=value)
```

**跨平台泄漏点**:`self._show_reasoning` 是**进程级**变量,但落盘的键是
**每平台**的 `display.platforms.<key>.show_reasoning`。投递时的取值
(`gateway/run.py:17711-17718 @ 863e313`)是「优先读每平台键,读不到就用
`self._show_reasoning` 作默认」。所以在 Telegram 敲 `/reasoning hide`,
会把**所有没有显式每平台键的平台**的默认值也翻掉,而回复文案却说
`"🧠 ✓ Reasoning display: **OFF** for **{platform}**"`(`locales/en.yaml:212 @ 863e313`)。
文案夸大了作用域。

#### `_parse_reasoning_command_args`(区间外,`gateway/run.py:8139-8162 @ 863e313`)

```python
        text = str(raw_args or "").strip().replace("—", "--")
        ...
        try:
            tokens = shlex.split(text)
        except ValueError:
            tokens = text.split()

        persist_global = False
        value_tokens = []
        for token in tokens:
            if token == "--global":
                persist_global = True
            else:
                value_tokens.append(token)
        return " ".join(value_tokens).strip().lower(), persist_global
```

`shlex.split` 失败(引号不配对)时降级到 `str.split()`——不因为一个引号让命令报错。
被 `/reasoning`(3498)与 `/fast`(3691)复用。测试
`tests/gateway/test_reasoning_command.py:69-71` 钉住 ASCII 与全角破折号两种 `--global`。

#### `_try_send_choice_picker`(3446–3482)—— 选择器共用件

```python
# gateway/slash_commands.py:3454-3482 @ 863e313
        """Send an interactive choice picker when the platform supports it.

        Mirrors the `/model` picker gate: the capability is detected on the
        adapter *type* (``send_choice_picker``), and a failed send falls back
        to the text path (returns False) instead of erroring the command.
        """
        adapter = getattr(self, "_adapter_for_source")(event.source)
        has_picker = (
            adapter is not None
            and getattr(type(adapter), "send_choice_picker", None) is not None
        )
        if not has_picker:
            return False
        try:
            metadata = self._thread_metadata_for_source(
                event.source, self._reply_anchor_for_event(event)
            )
            result = await adapter.send_choice_picker(...)
            return bool(getattr(result, "success", False))
        except Exception as e:
            logger.warning("send_choice_picker failed, falling back to text: %s", e)
            return False
```

**能力探测在类上而非实例上**——这是刻意的:`BasePlatformAdapter` **没有**
`send_choice_picker` / `send_model_picker` 的默认实现(在 `gateway/platforms/base.py`
里 grep 不到这两个名字),所以 `getattr(type(adapter), ...)` 是真探测。
对比 `send_slash_confirm`:base **有**默认实现(3745–3778),返回
`SendResult(success=False, error="Not supported")`,所以那条路只能靠**返回值**判断,
不能靠 `hasattr`。两种能力协商范式并存于同一文件。

**实现矩阵**(全仓 grep):

| adapter | `send_model_picker` | `send_choice_picker` | `send_slash_confirm` |
|---|---|---|---|
| Discord | 7357 | 7419 | 7144 |
| Telegram | 5648 | 5722 | 5518 |
| Matrix | 2588 | 2669 | — |
| Slack | — | — | 6454 |
| WhatsApp Cloud | — | — | `gateway/platforms/whatsapp_cloud.py:903` |
| Relay | — | — | `gateway/relay/adapter.py:1763` |
| base(默认) | 无 | 无 | `gateway/platforms/base.py:3745`(返回不支持) |

Slack 有确认按钮但**没有** picker;Matrix 有 picker 但**没有**确认按钮。
两个交互面各自演化,没有统一的「交互能力」抽象。

#### `/reasoning` 本体(3484–3575)

无参 → 先试 picker,失败落回文本状态卡(3549–3569);有参 → 直接走应用器(3572–3575)。
源规范化与 `/model` 同(#30479):

```python
# gateway/slash_commands.py:3499-3503 @ 863e313
        # Normalize the source (Telegram DM topic recovery) before deriving
        # the override key so storage matches the key the next message turn
        # reads — same fix as /model (#30479).
        _reasoning_source = await asyncio.to_thread(self._normalize_source_for_session_key, event.source)
        session_key = self._session_key_for_source(_reasoning_source)
```

**但后面又用了未规范化的 `event.source`**(3511、3542、3549 传入 `event`),
所以 `_resolve_session_reasoning_config(source=event.source, session_key=session_key, ...)`
的两个入参来自不同的 source。同一个 #30479 的坑,只补了一半。

有效模型用会话覆盖而非 config 默认(3507–3509)——这一点做对了,和 `/fast` 相反(§2.19)。

### 2.17 `/memory`(3577–3616)

整个 handler 就是一个转发器 + 一个 `set_mode_fn` 闭包:

```python
# gateway/slash_commands.py:3595-3616 @ 863e313
        def _set_approval(enabled: bool):
            # Write-back round-trip: raw read is correct (merged defaults must
            # not be persisted back to the user's file).
            from hermes_cli.config import read_user_config_raw
            user_config = read_user_config_raw(config_path)
            user_config.setdefault("memory", {})["write_approval"] = bool(enabled)
            atomic_config_write(config_path, user_config)
            # New setting must take effect next message → drop cached agent.
            self._evict_cached_agent(session_key)

        # Apply approved writes against a fresh on-disk store (the gateway has
        # no long-lived agent; the store persists to the same MEMORY/USER.md).
        # load_on_disk_store() honors the user's configured char limits.
        store = load_on_disk_store()

        out = handle_pending_subcommand(
            wa.MEMORY, args, memory_store=store, set_mode_fn=_set_approval,
        )
        if out is None:
            out = ("Unknown /memory subcommand. Use: pending, approve <id>, "
                   "reject <id>, approval <on|off>.")
        return out
```

**`handle_pending_subcommand` 才是真正的 CLI/gateway 共用参数解析器**
(`hermes_cli/write_approval_commands.py`),`None` 返回值 = 「不认识这个子命令」,
由调用方给出平台化的 usage 文本。这是切片里第二个「单一属主 + 平台装饰」样板。

### 2.18 `/skills`(3618–3677)—— 只有写审批复核面

**双重门**:CommandDef 的 `gateway_config_gate="skills.write_approval"`
(`hermes_cli/commands.py:258 @ 863e313`)+ handler 内部再判一次,
且**留了「门关了但还有积压」的逃生口**:

```python
# gateway/slash_commands.py:3643-3648 @ 863e313
        gate_on = wa.write_approval_enabled(wa.SKILLS)
        wants_toggle = bool(args) and args[0].lower() in {"approval", "mode"}
        if not gate_on and not wants_toggle and wa.pending_count(wa.SKILLS) == 0:
            return ("Skill write approval is off (skills.write_approval). "
                    "Enable it with /skills approval on, then review staged "
                    "writes here with /skills pending.")
```

**为什么**:门被关掉后仍有 staged 写在盘上,如果一并挡住就永远取不出来了。
docstring 3625–3627 明说 "also answers when staged writes still exist after the
gate was turned off (so they are never stranded)"。

输出截断(切片里第二个显式截断点):

```python
# gateway/slash_commands.py:3668-3677 @ 863e313
        # Chat bubbles can't hold a full skill diff — truncate and point at
        # the real review surface. (Note: `hermes skills diff <name>` is a
        # *different* command — it diffs a bundled skill against its stock
        # version — so we point at the pending JSON file, not that command.)
        if args and args[0].lower() == "diff" and len(out) > 3000:
            pending_id = args[1] if len(args) > 1 else "<id>"
            out = (out[:3000]
                   + "\n… (truncated — full diff in "
                     f"~/.hermes/pending/skills/{pending_id}.json)")
        return out
```

注释里还专门记了一处**命名冲突**:`/skills diff <id>`(写审批)vs
`hermes skills diff <name>`(对比内置技能)——同名不同义。

### 2.19 `/fast`(3679–3762)

> 「Priority Processing / Fast Mode」= OpenAI/Anthropic 的加价加速档;在请求里表现为
> `service_tier`。

复用 `/reasoning` 的解析器(3691),然后一个**致命的作用域不匹配**:

```python
# gateway/slash_commands.py:3692-3700 @ 863e313
        session_key = self._session_key_for_source(event.source)
        self._service_tier = self._resolve_session_service_tier(
            session_key=session_key
        )

        user_config = _load_gateway_config()
        model = _resolve_gateway_model(user_config)
        if not model_supports_fast_mode(model):
            return t("gateway.fast.not_supported")
```

`_resolve_gateway_model` 只读 config.yaml(`gateway/run.py:3256-3269 @ 863e313`),
**完全不看会话级 `/model` 覆盖**。所以:`/model gpt-5 --session` 之后 `/fast`
仍按 config 里的旧模型判定支持性。对比 `/reasoning` 在 3507–3509 明确读了会话覆盖。
同一文件、相邻两个命令,对「当前模型是什么」给出两种答案。见 §4 ◇-04。

`_apply_fast_selection`(3702–3730)是打字/点选共用应用器(同 `/reasoning` 的范式),
`--global` 写失败降级到会话级:

```python
# gateway/slash_commands.py:3715-3730 @ 863e313
            if persist:
                if self._save_gateway_config_key("agent.service_tier", saved_value):
                    # Global write supersedes any session override.
                    self._set_session_service_tier_override(
                        session_key, None, clear=True
                    )
                    self._evict_cached_agent(session_key)
                    return t("gateway.fast.saved", label=label)
                # Config write failed — fall back to a session override so the
                # user's choice still applies (mirrors /reasoning --global).
                self._set_session_service_tier_override(session_key, tier)
                self._evict_cached_agent(session_key)
                return t("gateway.fast.session_only", label=label)
```

`tier` 的取值是 `"priority"` / `None`,而落盘值是 `"fast"` / `"normal"`——
**内部表示与持久化表示不同**(3704–3711),转换只此一处。

### 2.20 `/approvals`(3764–3779)—— 切片里唯一的「二次鉴权」

```python
# gateway/slash_commands.py:3764-3779 @ 863e313
    async def _handle_approvals_command(self, event: MessageEvent) -> str:
        """Show or persist the profile-wide dangerous-command approval mode."""
        from gateway.slash_access import policy_for_source
        from hermes_cli.approval_mode import run_approval_mode_command

        requested = event.get_command_args().strip() or None
        # This mutates profile-wide security policy. The central slash gate can
        # allow selected commands to non-admin users, so enforce admin again at
        # this side-effect boundary. Unconfigured policies remain unrestricted.
        policy = policy_for_source(self.config, event.source)
        if requested and not policy.is_admin(event.source.user_id):
            return "Only gateway admins can change the persistent approval mode."
        result = run_approval_mode_command(requested)
        # Approval checks load config dynamically; do not evict the cached agent
        # or alter its system prompt/tool schema (prompt-cache prefix is sacred).
        return result.message
```

三条可迁移的原则都写在注释里:
1. **中心闸可被配置放宽,所以副作用边界要再判一次**(纵深防御);
2. **只有写操作需要 admin,读状态不需要**(`if requested and ...`);
3. **审批模式变更不 evict agent**——因为 `tools/approval.py` 每次检查都重读配置,
   而 evict 会打断 prompt cache 前缀。这与切片里几乎所有其它配置类命令
   (`/reasoning` `/fast` `/memory` `/skills` `/codex-runtime`)相反,是**刻意的例外**。

`run_approval_mode_command`(`hermes_cli/approval_mode.py:34-80 @ 863e313`)有个
巧妙处理:`set_config_value` 遇到 managed scope 会打 stderr + `SystemExit`,
在 slash 命令里那会杀掉 worker,所以用 `redirect_stdout/redirect_stderr` 捕获后
转成返回值。

**回归钉子**:`tests/gateway/test_approvals_command.py::test_gateway_rejects_non_admin_persistent_approval_change`。

### 2.21 `/yolo`(3781–3796)

```python
# gateway/slash_commands.py:3789-3796 @ 863e313
        session_key = self._session_key_for_source(event.source)
        current = is_session_yolo_enabled(session_key)
        if current:
            disable_session_yolo(session_key)
            return EphemeralReply(t("gateway.yolo.disabled"))
        else:
            enable_session_yolo(session_key)
            return EphemeralReply(t("gateway.yolo.enabled"))
```

切片内唯一返回 `EphemeralReply` 的命令。`EphemeralReply` 是 `str` 子类
(`gateway/platforms/base.py:2375-2400 @ 863e313`),对所有把返回值当文本的下游
完全透明,只有 `isinstance` 检查能区分——用来请求「TTL 后自动删除这条系统提示」。

**状态存在 `tools/approval.py` 的模块级表**(不是 runner 上),所以进程内任何持有
session_key 的地方都能读到,不需要 runner 反向引用。这和 `tools/slash_confirm.py`
的设计动机完全一致(见 §3)。

### 2.22 `/verbose`(3798–3860)

配置门 + 循环切换。门:

```python
# gateway/slash_commands.py:3812-3823 @ 863e313
        # --- check config gate ------------------------------------------------
        try:
            user_config = _load_gateway_config()
            gate_enabled = is_truthy_value(
                cfg_get(user_config, "display", "tool_progress_command"),
                default=False,
            )
        except Exception:
            gate_enabled = False

        if not gate_enabled:
            return t("gateway.verbose.not_enabled")
```

循环 **5 档**:

```python
# gateway/slash_commands.py:3826 @ 863e313
        cycle = ["off", "new", "all", "verbose", "log"]
```

读当前值走 `display_config` 解析器(每平台):

```python
# gateway/slash_commands.py:3835-3840 @ 863e313
        # Read current effective mode for this platform via the resolver
        from gateway.display_config import resolve_display_setting
        current = resolve_display_setting(user_config, platform_key, "tool_progress", "all")
        if current not in cycle:
            current = "all"
        idx = (cycle.index(current) + 1) % len(cycle)
        new_mode = cycle[idx]
```

**注意写路径没用 `_save_gateway_config_key`**,而是就地手搓三层 setdefault + 落盘
(3844–3853)——同一个文件里有两套等价的配置写法。

**回归钉子**:`tests/gateway/test_verbose_command.py`(默认关闭 / 开启后循环 /
带引号的 `"false"` 也算关)。

### 2.23 `/footer`(3862–3946)—— **参数解析是死代码**

```python
# gateway/slash_commands.py:3882-3891 @ 863e313
        # --- parse argument -------------------------------------------------
        arg = ""
        try:
            text = (getattr(event, "message", None) or "").strip()
            if text.startswith("/"):
                parts = text.split(None, 1)
                if len(parts) > 1:
                    arg = parts[1].strip().lower()
        except Exception:
            arg = ""
```

`MessageEvent` **没有 `message` 字段**。用 AST 枚举其全部字段
(`gateway/platforms/base.py:2054-2153 @ 863e313`):
`text, message_type, source, raw_message, message_id, platform_update_id, media_urls,
media_types, reply_to_message_id, reply_to_text, reply_to_author_id, reply_to_author_name,
reply_to_is_own_message, prompt_response, auto_skill, channel_prompt, channel_context,
internal, metadata, timestamp` + 三个方法 `is_command / get_command / get_command_args`。
**没有 `message`。** 全仓 grep 也没有任何代码给事件对象赋 `.message`。

⇒ `arg` 恒为 `""` ⇒ 恒走 `elif arg == "": new_state = not effective["enabled"]`(3915–3916)
⇒ **gateway 上 `/footer on`、`/footer off`、`/footer status` 全部退化成「切换」**。
`/footer status` 甚至会**改状态**(它本该只读)。

正确写法就在同文件其它 21 个 handler 里:`event.get_command_args()`。这是命名漂移
(`.message` 大概率是从某个别的事件类型抄来的)造成的静默失效。见 §4 ▲-01。

写路径与 `/verbose` 同样手搓(3921–3928),读走 `resolve_footer_config`(3899)。
预览用 `format_runtime_footer`(3937–3943)。

### 2.24 `/compress` 外层(3948–3968)+ 参数解析(3970–4032)

**外层是 profile 密钥作用域包装**,注释把事故讲得很清楚:

```python
# gateway/slash_commands.py:3948-3968 @ 863e313
    async def _handle_compress_command(self, event: MessageEvent) -> str:
        """Profile-scoping wrapper around manual /compress.

        Multiplexed gateways resolve credentials through the fail-closed
        per-profile secret scope (``agent.secret_scope``, Workstream A). The
        agent turn installs it via ``_run_agent``'s wrapper, but slash-command
        dispatch does not — so manual /compress reached the compressor's
        provider resolution unscoped and died with ``UnscopedSecretError``
        (``get_secret('OPENROUTER_BASE_URL') called with no profile secret
        scope active``). Install the source profile's scope around the whole
        handler, mirroring ``_run_agent``. Single-profile gateways skip this
        — zero behavior change.
        """
        if not getattr(getattr(self, "config", None), "multiplex_profiles", False):
            return await self._handle_compress_command_inner(event)

        from gateway.run import _profile_runtime_scope

        profile_home = self._resolve_profile_home_for_source(event.source)
        with _profile_runtime_scope(profile_home):
            return await self._handle_compress_command_inner(event)
```

**这是「slash 分发路径没有装 agent 回合的那套上下文」这一整类问题的样本**。
`_run_agent` 装了 secret scope,slash dispatch 没装 → 任何在 slash 里做 provider
解析的命令都会踩。切片里只有 `/compress` 和 `/model` 打了补丁。

**参数解析(切片内 3990–4006)是「先剥标志、再位置解析」两段式**:

```python
# gateway/slash_commands.py:3990-4006 @ 863e313
        # Parse args: either a focus topic (full compress) or the
        # boundary-aware "here [N]" form (partial compress).
        from hermes_cli.partial_compress import (
            extract_compress_flags,
            parse_partial_compress_args,
            rejoin_compressed_head_and_tail,
            split_history_for_partial_compress,
            summarize_compress_preview,
        )
        from agent.conversation_compression import (
            finalize_context_engine_compression_notification,
        )
        _raw_args = (event.get_command_args() or "").strip()
        # Strip --preview/--dry-run/--aggressive before positional parsing
        # so the flags coexist with 'here [N]' / focus-topic forms.
        _raw_args, _preview, _aggressive = extract_compress_flags(_raw_args)
        partial, keep_last, focus_topic = parse_partial_compress_args(_raw_args)
```

`extract_compress_flags`(`hermes_cli/partial_compress.py:111-142 @ 863e313`)扫描
token,剥掉 `--preview|--dry-run|--dryrun|--aggressive`,其余原样保留顺序 →
交给 `parse_partial_compress_args`(同文件 55–99)识别 `here [N]` / `up to here` /
`--keep N`,剩下的当 focus topic。**这是全切片唯一一个「标志与位置参数正交」的解析器**,
其它命令要么只支持位置(`/goal` `/heartbeat`),要么标志必须写在特定位置。

**`--aggressive` 是明确的「不支持」而非静默忽略**:

```python
# gateway/slash_commands.py:4008-4015 @ 863e313
        _agg_note = ""
        if _aggressive:
            # LLM-free hard truncation is not supported on this surface —
            # it would need its own transcript-persistence branch outside
            # the guarded _compress_context rotation machinery (#44794).
            _agg_note = t("gateway.compress.aggressive_unsupported")
            if not _preview:
                return _agg_note
```

对应文案:`locales/en.yaml:111 @ 863e313`
`"--aggressive is not supported; use '/compress here [N]' to keep only recent exchanges, or /undo to drop turns."`
——**拒绝时给出替代方案**,值得抄。

`--preview` 是纯只读路径(4017–4032):不建 agent、不写盘、不改会话。

前置门:`if not history or len(history) < 4: return t("gateway.compress.not_enough")`(3987–3988)。

**回归钉子**:`tests/gateway/test_compress_preview.py`(`test_preview_with_here_boundary`、
`test_aggressive_dry_run_shows_preview_plus_note`)、`tests/gateway/test_compress_focus.py`、
`tests/gateway/test_compress_command.py`(8 个,含多 profile 密钥作用域与
「in-place 不做破坏性 rewrite」)。

---

## 3. 审批解析器专章(R7B 移交项)

### 3.0 结论先行

**hermes-agent 有两套完全独立的「审批」机制,共用同一批用户词汇(`/approve` `/deny`
`always` `cancel`)但语义、ID 策略、超时、幂等全部不同。切片内的
`/model` 贵模型确认闸(2400–2445)走的是第二套。**

| 维度 | A. 工具审批(危险命令) | B. slash-confirm(慢/贵/破坏性命令) |
|---|---|---|
| 状态模块 | `tools/approval.py`(模块级) | `tools/slash_confirm.py`(模块级,167 行) |
| 谁在等 | agent 工作线程阻塞在 `Event.wait()` | 没人阻塞;handler 已返回,回调后置 |
| 命令 | `/approve` `/deny`(`gateway/slash_commands.py:5377` / `5435`,区间外) | `/approve` `/always` `/cancel`(在 `_handle_message` 里被拦截) |
| 选项 | `once` / `session` / `always` / `deny` | `once` / `always` / `cancel` |
| **ID 匹配** | **无**。按 session_key FIFO | **有**。`confirm_id` 不匹配即 no-op |
| 模糊匹配 | 无(只有同义词集合) | 无(只有同义词集合) |
| 超时 | `approvals.timeout`,默认 300s(`tools/approval.py:2970-2981`) | `DEFAULT_TIMEOUT_SECONDS = 300`(`tools/slash_confirm.py:48`) |
| 幂等 | `queue.pop(0)` / `queue.clear()`,二次调用返回 0 | pop-before-run |
| 优先级 | **高**。同时存在时工具审批赢 | 低(`gateway/run.py:14663`) |
| 触发者 | agent 调危险工具 | 用户敲一个需确认的 slash 命令 |

### 3.1 B 套:切片内的调用点

```python
# gateway/slash_commands.py:2400-2443 @ 863e313
        # Expensive-model confirmation gate (typed /model <name> path).
        # The pickers (Telegram/Discord inline keyboards, TUI, dashboard)
        # already confirm via their own UI affordances; this covers the
        # direct text command, which previously bypassed the guard.
        # expensive_model_warning() may hit models.dev or a /models endpoint
        # on a cache miss, so run it off the event loop.
        _cost_warning = None
        try:
            from hermes_cli.model_cost_guard import expensive_model_warning

            _cost_warning = await asyncio.to_thread(
                expensive_model_warning,
                result.new_model,
                provider=result.target_provider,
                base_url=result.base_url or current_base_url or "",
                api_key=result.api_key or current_api_key or "",
                model_info=result.model_info,
            )
        except Exception:
            _cost_warning = None
        if _cost_warning is not None:
            async def _on_cost_confirm(choice: str) -> str:
                if choice == "cancel":
                    return (
                        f"🟡 Model switch cancelled. Current model unchanged "
                        f"({current_model or 'unknown'})."
                    )
                # "once" and "always" both proceed — there is no persistent
                # opt-out for the cost guard (each expensive switch should be
                # an explicit decision).
                return await _finish_switch()

            _p = self._typed_command_prefix_for(event.source.platform)
            return await self._request_slash_confirm(
                event=event,
                command="model",
                title="Expensive Model Warning",
                message=(
                    f"⚠️ **Expensive Model Warning**\n\n{_cost_warning.message}\n\n"
                    f"_Text fallback: reply `{_p}approve` to switch or `{_p}cancel` to keep "
                    "the current model._"
                ),
                handler=_on_cost_confirm,
            )
```

**三个可迁移的点**:
1. **确认闸在「解析、鉴权、执行准备都做完」之后才插入**——`_finish_switch` 是个闭包,
   把「已经算好的提交动作」延迟到用户点头之后。这样确认闸不需要重新解析参数。
2. **`always` 被刻意当成 `once`**:成本守卫**没有**持久化豁免。注释说明了理由。
   对比破坏性命令的 `always`(会落盘 `approvals.destructive_slash_confirm: false`)。
3. **文本兜底提示用 `_typed_command_prefix_for`**(§3.8)——Slack/Matrix 上
   `/` 被平台占用,提示必须写 `!approve`。

### 3.2 B 套:`_request_slash_confirm` 的实现(`gateway/run.py:20595-20661 @ 863e313`,区间外)

```python
    async def _request_slash_confirm(
        self,
        *,
        event: MessageEvent,
        command: str,
        title: str,
        message: str,
        handler,
    ) -> Optional[str]:
        """Ask the user to confirm an expensive slash command.

        ``handler`` is an async callable ``handler(choice: str) -> str``
        where ``choice`` is ``"once"``, ``"always"``, or ``"cancel"``.
        The handler runs on the event loop when the user responds; its
        return value is sent back as a gateway message.

        Returns a short acknowledgment string to send immediately (before
        the user's response).  If buttons rendered successfully the ack
        is ``None`` (buttons are self-explanatory); if we fell back to
        text the message itself IS the ack.
        """
```

三个关键实现细节:

**(a) counter 的防御性初始化** —— 为裸测试 runner 兜底:

```python
# gateway/run.py:20621-20630 @ 863e313
        # Bare-runner test harnesses (object.__new__(GatewayRunner)) skip
        # __init__ and don't have the counter attribute — fall back to a
        # local counter so tests don't AttributeError.  Real runs always
        # have the instance attribute.
        counter = getattr(self, "_slash_confirm_counter", None)
        if counter is None:
            import itertools as _itertools
            counter = _itertools.count(1)
            self._slash_confirm_counter = counter
        confirm_id = f"{next(counter)}"
```

`confirm_id` 只是进程内单调计数——**不是全局唯一 ID**,重启后从 1 重来。够用,
因为它只在 `(session_key, confirm_id)` 对里比对,且 300s 过期。

**(b) 先注册再发送,防按钮竞态**:

```python
# gateway/run.py:20631-20633 @ 863e313
        # Register the pending confirm FIRST so a super-fast button click
        # cannot race the send_slash_confirm return.
        _slash_confirm_mod.register(session_key, confirm_id, command, handler)
```

**(c) 按钮成功 → 返回 `None`(不发冗余文本);按钮失败 → 把提示文本本身当回复**:

```python
# gateway/run.py:20656-20661 @ 863e313
        if used_buttons:
            # Buttons rendered — no redundant text ack.
            return None
        # Text fallback — return the prompt message as the direct reply.
        return message
```

这就是「按钮/文本双通道」的收口。

### 3.3 B 套:`tools/slash_confirm.py` —— 全平台共用的状态与解析

**为什么放模块级**:

```python
# tools/slash_confirm.py:18-21 @ 863e313
State is stored module-level (like ``tools.approval``) so platform
adapters can resolve callbacks without needing a backreference to the
``GatewayRunner`` instance.  The CLI path (``cli.py``) uses a local
synchronous variant — see ``_prompt_slash_confirm`` there.
```

**register 的覆盖语义**(每会话只留一个待确认):

```python
# tools/slash_confirm.py:51-68 @ 863e313
def register(session_key, confirm_id, command, handler) -> None:
    """Register a pending slash-command confirmation.

    Overwrites any prior pending confirm for the same ``session_key`` — the
    user invoking a new confirmable command supersedes the stale one.
    """
    with _lock:
        _pending[session_key] = {
            "confirm_id": confirm_id,
            "command": command,
            "handler": handler,
            "created_at": time.time(),
        }
```

**resolve 的四道闸(ID / 幂等 / 超时 / 异常)**:

```python
# tools/slash_confirm.py:115-140 @ 863e313
    with _lock:
        entry = _pending.get(session_key)
        if not entry:
            return None
        if entry.get("confirm_id") != confirm_id:
            # Stale confirm_id — superseded by a newer prompt on the same session.
            return None
        # Pop before we run the handler to prevent duplicate callbacks
        # (e.g. button double-click) from running it twice.
        _pending.pop(session_key, None)
        if time.time() - float(entry.get("created_at", 0) or 0) > timeout:
            return None
        handler = entry.get("handler")
        command = entry.get("command", "?")

    if not handler:
        return None
    try:
        result = await handler(choice)
    except Exception as exc:
        logger.error(
            "Slash-confirm handler for /%s raised: %s",
            command, exc, exc_info=True,
        )
        return f"❌ Error handling confirmation: {exc}"
    return result if isinstance(result, str) else None
```

**顺序很讲究**:`pop` 在超时检查**之前**——即「超时的条目也要清掉」,而不是留着
让下次再撞一次。锁在 `await handler(...)` **之前**释放,handler 可以做任意 async 工作
而不阻塞其它会话。

**跨线程兜底**:`resolve_sync_compat`(143–167)给「按钮回调不在事件循环线程上」的
适配器用,`safe_schedule_threadsafe` + `fut.result(timeout=30)`。

### 3.4 B 套:文本兜底的**词表解析器**(`gateway/run.py:14646-14694 @ 863e313`,区间外)

这就是本轮要找的「全平台共用的审批解析面」:

```python
        # Intercept messages that are responses to a pending /reload-mcp
        # (or future) slash-confirm prompt.  Recognized confirm replies are
        # /approve, /always, /cancel (plus short aliases).  Anything else
        # falls through to normal dispatch — a stale pending confirm does
        # NOT block other commands.
        #
        # Important: if a dangerous-command approval is ALSO pending (agent
        # blocked inside tools/approval.py), the tool approval takes
        # precedence — /approve there unblocks the waiting tool thread.
        # Slash-confirm only catches /approve when no tool approval is live.
        from tools import slash_confirm as _slash_confirm_mod
        _pending_confirm = _slash_confirm_mod.get_pending(_quick_key)
        _tool_approval_live = False
        try:
            from tools.approval import has_blocking_approval
            _tool_approval_live = has_blocking_approval(_quick_key)
        except Exception:
            _tool_approval_live = False
        if _pending_confirm and not _tool_approval_live:
            _raw_reply = (event.text or "").strip()
            # Accept bang-prefixed replies (`!always`, `!cancel`) verbatim.
            # Slack/Matrix instruction text shows the `!` prefix (typed `/`
            # is blocked in Slack threads), but the adapters only rewrite
            # `!<known-command>` — `always`/`cancel` are confirm keywords,
            # not registered commands, so the `!` survives to here.
            _norm_reply = _raw_reply.lstrip("!/").lower()
            _cmd_reply = event.get_command()
            _confirm_choice = None
            if _cmd_reply in {"approve", "yes", "ok", "confirm"}:
                _confirm_choice = "once"
            elif _cmd_reply in {"always", "remember"}:
                _confirm_choice = "always"
            elif _cmd_reply in {"cancel", "no", "deny", "nevermind"}:
                _confirm_choice = "cancel"
            elif _norm_reply in {"approve", "approve once", "once"}:
                _confirm_choice = "once"
            elif _norm_reply in {"always", "always approve"}:
                _confirm_choice = "always"
            elif _norm_reply in {"cancel", "nevermind", "no"}:
                _confirm_choice = "cancel"
            if _confirm_choice is not None:
                _resolved = await _slash_confirm_mod.resolve(
                    _quick_key, _pending_confirm.get("confirm_id"), _confirm_choice,
                )
                return _resolved or ""
            # Stale pending + unrelated command: drop the pending state so
            # the confirm doesn't block normal usage indefinitely.  The user
            # clearly moved on.
            _slash_confirm_mod.clear_if_stale(_quick_key)
```

**逐条拆解(这是要背下来的部分)**:

1. **优先级仲裁**:两套审批都待决时,工具审批赢。因为 A 套有线程真的阻塞着,
   拖不起;B 套只是个闭包,可以等。
2. **两级词表**:先按「命令形式」匹配(`event.get_command()`,即 `/approve`),
   再按「裸词形式」匹配(`_norm_reply`,即用户直接打 `always`)。
3. **`!` 前缀专门处理**:适配器只重写 `!<已注册命令名>`;`always` / `cancel` 不是
   注册命令,所以 `!always` 会带着 `!` 一路到这里,必须 `lstrip("!/")`。
   **这是「平台前缀重写」与「非命令关键词」之间的一个真实缝隙**。
4. **不匹配 = 放行 + 清陈旧态**:待确认状态**绝不阻塞**其它命令。用户显然换话题了,
   `clear_if_stale` 按 300s 门限清理。
5. **词表不对称**:命令形式认 `confirm`、`ok`、`remember`;裸词形式不认。
   裸词形式认 `approve once`;命令形式不认(`/approve once` 会被
   `get_command()` 解析成 `approve` → once,恰好等价,巧合)。
   `deny` 只出现在命令形式的 cancel 集合里。**没有任何模糊匹配 / 前缀匹配 /
   编辑距离**——全是硬编码集合。

### 3.5 B 套:全平台调用面(grep 结果)

**发起方(`_request_slash_confirm` 调用点,共 3 处 + 1 个二级封装)**:

| 位置 | 命令 | 说明 |
|---|---|---|
| `gateway/slash_commands.py:2433` | `/model` | 贵模型闸(**本切片内**) |
| `gateway/slash_commands.py:5233` | `/reload-mcp` | 门 `approvals.mcp_reload_confirm` |
| `gateway/run.py:20587` | `/new` `/reset` `/undo`(经 `_maybe_confirm_destructive_slash`) | 门 `approvals.destructive_slash_confirm` |
| `gateway/run.py:15066` / `15260` | 上一行那个封装的两个调用点 | |

**解析方(`slash_confirm.resolve` 调用点)**:

| 位置 | 触发 |
|---|---|
| `gateway/run.py:14687` | 文本兜底(全平台) |
| `gateway/relay/adapter.py:1919` | relay 的结构化 `prompt_response` |
| `gateway/platforms/whatsapp_cloud.py:1869` | `sc:<choice>:<confirm_id>` 按钮 |
| Telegram / Discord / Slack 适配器 | 各自的按钮回调(经 `send_slash_confirm` 注册的 state) |

**relay 侧的收敛写法值得抄**(未知 option 一律降级到最保守的选项):

```python
# gateway/relay/adapter.py:1913-1921 @ 863e313
            elif kind == "slash_confirm":
                from tools import slash_confirm as slash_confirm_mod

                choice = (
                    option_id if option_id in {"once", "always", "cancel"} else "cancel"
                )
                result_text = await slash_confirm_mod.resolve(
                    session_key, str(state.get("confirm_id") or ""), choice
                )
```

同文件 exec_approval 分支(1888–1896)同理:`option_id if option_id in
{"once","session","always","deny"} else "deny"` —— **fail-closed**。

### 3.6 A 套:`/approve` `/deny` 的解析器(区间外,`gateway/slash_commands.py:5377-5495 @ 863e313`)

`/approve` 的解析(5410–5420):

```python
        # Parse args: support "all", "all session", "all always", "session", "always"
        args = event.get_command_args().strip().lower().split()
        resolve_all = "all" in args
        remaining = [a for a in args if a != "all"]

        if any(a in {"always", "permanent", "permanently"} for a in remaining):
            choice = "always"
        elif any(a in {"session", "ses"} for a in remaining):
            choice = "session"
        else:
            choice = "once"
```

**「集合成员 + any()」而非位置解析**:`all` 可以在任意位置,`session`/`always`
同理。未知 token 被静默忽略(降级为 `once`)。

`/deny` 的解析(5462–5471)不同,因为要保留自由文本 reason:

```python
        raw_args = event.get_command_args().strip()
        tokens = raw_args.split()
        resolve_all = bool(tokens) and tokens[0].lower() == "all"
        if resolve_all:
            reason = raw_args[len(tokens[0]):].strip()
        else:
            reason = raw_args
        # Cap to a sane one-liner; the agent only needs a short hint.
        if reason:
            reason = reason[:280].strip()
```

`all` **只认首位**(否则 `/deny this is not allowed` 里的 "all" 会误判)。
reason 截到 280 字符。

**幂等 / 陈旧态**:两者都先判 `has_blocking_approval`,并顺手清 `_pending_approvals`
里的孤儿:

```python
# gateway/slash_commands.py:5404-5408 @ 863e313
        if not has_blocking_approval(session_key):
            if session_key in self._pending_approvals:
                self._pending_approvals.pop(session_key)
                return t("gateway.approval_expired")
            return t("gateway.approve.no_pending")
```

**ID 匹配:没有。** `resolve_gateway_approval`(`tools/approval.py:2490-2523 @ 863e313`)
只按 session_key 取 FIFO 队列:

```python
    with _lock:
        queue = _gateway_queues.get(session_key)
        if not queue:
            return 0
        if resolve_all:
            targets = list(queue)
            queue.clear()
        else:
            targets = [queue.pop(0)]
        if not queue:
            _gateway_queues.pop(session_key, None)

    for entry in targets:
        entry.result = choice
        if reason:
            entry.reason = reason
        entry.event.set()
    return len(targets)
```

**关键推论:连按钮点击也没有 ID 语义。** 适配器里的 `approval_id` **只**用作
「本地 map 里查 session_key」的键,查到后就丢掉了:

```python
# gateway/platforms/whatsapp_cloud.py:1796-1820 @ 863e313
        if button_id.startswith("appr:"):
            parts = button_id.split(":", 2)
            if len(parts) != 3:
                return False
            _, approval_id, choice = parts
            session_key = self._exec_approval_state.pop(approval_id, None)
            if not session_key:
                logger.info(
                    "[whatsapp_cloud] approval tap with no matching state "
                    "(approval_id=%s) — likely stale; falling back to text",
                    approval_id,
                )
                return False
            ...
            count = resolve_gateway_approval(session_key, choice)
```

`.pop(approval_id)` 提供**单次幂等**(同一个按钮点两次,第二次找不到 state);
但**不提供目标定位**——resolve 仍然解决队列里最老的那个。所以「并行子代理同时
弹了两个审批,用户点了第二个的按钮」→ 实际批准的是第一个。这是 A 套的固有设计,
`resolve_all=True`(`/approve all`)是官方给出的规避方式。

**返回给用户的计数**:`count` 为 0 时不能说「已批准」,必须说「已过期/已被处理」——
relay 与 whatsapp 都专门处理了这一点:

```python
# gateway/relay/adapter.py:1903-1904 @ 863e313
                if not count:
                    label = "⌛ Approval expired — no command was waiting."
```

```python
# gateway/platforms/whatsapp_cloud.py:1826-1828 @ 863e313
            # Send confirmation message — paralleling Telegram's UX.  A tap
            # that lands after the wait timed out (count == 0) must not claim
            # the command was approved: it was already denied fail-closed.
```

**超时**:`_get_approval_timeout()`(`tools/approval.py:2970-2981 @ 863e313`)
默认 300s,注释记了一个真实教训:

```python
    """Read the approval timeout from config. Defaults to 300 seconds.

    The default matches DEFAULT_CONFIG["approvals"]["timeout"]. Gateway
    approvals arrive as push notifications the user may not see for a couple
    of minutes; 60s proved too tight in practice (Telegram taps landed after
    the wait had already failed closed).
    """
```

**回归钉子**:`tests/gateway/test_approve_deny_commands.py`(13 个,含
`test_resolve_single_pops_oldest_fifo`、`test_approve_all_resolves_multiple`、
`test_deny_with_reason_attaches_reason`、`test_yes_does_not_execute_pending_command`、
`test_parallel_subagent_approvals`、`test_approval_prompt_routes_to_originating_session`)。

### 3.7 A/B 之外的第三条线:`_maybe_confirm_destructive_slash`

(`gateway/run.py:20483-20592 @ 863e313`,区间外,但与切片内 `/model` 闸同源)

它是 B 套之上的**策略层**:读 `approvals.destructive_slash_confirm` 门 → 关则直接执行
→ 开则包一层三选一。`always` 分支的失败处理特别老实:

```python
# gateway/run.py:20560-20569 @ 863e313
                else:
                    # The user did approve this run, so the action still goes
                    # ahead, but the preference did not stick and the prompt
                    # will be back next time. Say so rather than promising an
                    # opt-out that was never written.
                    note = (
                        "\n\n⚠️ Could not save that preference (config.yaml is not "
                        "writable), so /clear, /new, /reset, and /undo will ask "
                        "again next time. To silence it permanently, set "
                        "`approvals.destructive_slash_confirm: false` in config.yaml."
                    )
```

**「不要承诺你没做到的事」** —— 写盘失败时不谎称已记住。测试
`tests/gateway/test_destructive_slash_always_persist_report.py` 5 个用例专门钉这个。

### 3.8 `_typed_command_prefix_for`(切片外定义 106–117,切片内 2432 使用)

```python
# gateway/slash_commands.py:106-117 @ 863e313
    def _typed_command_prefix_for(self, platform) -> str:
        """Return the prefix users can always type to reach Hermes commands.

        Reads the adapter's ``typed_command_prefix`` capability flag
        (default "/"). Slack and Matrix return "!" because typed "/"
        commands are blocked in Slack threads / reserved by Matrix clients;
        their adapters rewrite "!command" to "/command" on receive.
        Instruction text built for those platforms must show the prefix
        that actually works when typed.
        """
        adapter = self.adapters.get(platform) if getattr(self, "adapters", None) else None
        return getattr(adapter, "typed_command_prefix", "/") if adapter is not None else "/"
```

**审批提示文本必须平台化**,否则 Slack 用户照抄 `/approve` 会被 Slack 自己吞掉。

---

## 4. ▲/◇ 候选

> ▲ = 文档与代码矛盾;◇ = 代码有而文档无 / 内部不一致。

### ▲-01 `/footer on|off|status` 在 gateway 上完全失效(严重)

**文档侧**:
- `website/docs/reference/slash-commands.md:266`(**Messaging** 表):
  `` | `/footer [on|off|status]` | Toggle the runtime-metadata footer on final replies (shows model, context %, and cwd). | ``
- `website/docs/reference/slash-commands.md:90`(CLI 表)同形。
- 注册表 `hermes_cli/commands.py:223-225 @ 863e313`:
  ```python
    CommandDef("footer", "Toggle gateway runtime-metadata footer on final replies",
               "Configuration", args_hint="[on|off|status]",
               subcommands=("on", "off", "status"), busy_policy="dispatch"),
  ```
  ——注册表还会把这三个子命令喂给 Telegram BotCommand 菜单与自动补全。

**代码侧**:`gateway/slash_commands.py:3885 @ 863e313` 读的是不存在的
`event.message`(见 §2.23),`arg` 恒为 `""`,恒走 toggle 分支(3915–3916)。
`MessageEvent` 字段清单见 `gateway/platforms/base.py:2061-2153 @ 863e313`,无 `message`。

**判定**:▲。文档与注册表描述的三态参数在 gateway 上一个都不生效;`/footer status`
还有副作用。CLI 侧另有实现(`hermes_cli/cli_commands_mixin.py:3070`),不受影响。

### ▲-02 `/reasoning full|clamp` 在 gateway 上被拒

**文档侧**:`website/docs/reference/slash-commands.md:245`(**Messaging** 表,
`## Messaging slash commands` 起于第 216 行):
`` | `/reasoning [level|show|hide|full|clamp] [--global]` | Change reasoning effort (levels up to `max` / `ultra`) or toggle reasoning display (`full` / `clamp` included). `--global` persists to config. | ``

**代码侧**:`_apply_reasoning_selection` 只认 `show|on` / `hide|off` / `reset` /
`parse_reasoning_effort` 能解析的值(`gateway/slash_commands.py:3379-3402 @ 863e313`)。
`parse_reasoning_effort`(`hermes_constants.py:947-971 @ 863e313`)只接受
`none|false|disabled` 与 `VALID_REASONING_EFFORTS = ("minimal","low","medium","high","xhigh","max","ultra")`
(`hermes_constants.py:942-944 @ 863e313`)。`full`/`clamp` → `None` →
`t("gateway.reasoning.unknown_arg", arg=value)`。

`full`/`clamp` 确为 **CLI 独有**(`hermes_cli/cli_commands_mixin.py:3234` `if arg in {"full","all"}`、
`3242` `if arg in {"clamp","collapse","short"}`)。

**判定**:▲。messaging 表把 CLI 独有的两个动词写成了两侧通用。

### ▲-03 AGENTS.md 的「新增 slash 命令」步骤指向已搬走的位置

**文档侧**:`AGENTS.md:407 @ 863e313`
「3. If the command is available in the gateway, add a handler in `gateway/run.py`:」
(「Adding a Slash Command」小节起于 `AGENTS.md:395`)。
AGENTS.md 全文 grep 不到 `slash_commands.py`。

**代码侧**:handler 已在 Phase 3b 搬到 `gateway/slash_commands.py`
(模块 docstring `gateway/slash_commands.py:1-8 @ 863e313`)。`gateway/run.py` 只留
`if canonical == ...` 分发(如 `gateway/run.py:15191` 的 footer)。

**判定**:▲(半对半错:分发确实还在 run.py,handler 本体不在)。

### ▲-04 `/verbose` 的档位数,文档 4 档 vs 代码 5 档

**文档侧**:`website/docs/reference/slash-commands.md:80`
「Cycle tool progress display: off → new → all → verbose.」

**代码侧**:`gateway/slash_commands.py:3826 @ 863e313`
`cycle = ["off", "new", "all", "verbose", "log"]`,含第五档 `log`。
注册表 `hermes_cli/commands.py:216-217 @ 863e313` 描述里**有** `-> log`。

**判定**:▲(website 文档漏 `log`,注册表是对的)。

### ◇-01 模块 docstring 的规模数字已过期

`gateway/slash_commands.py:5 @ 863e313` 说 "There are 42 of them (~3,200 LOC)";
实测 `_handle_*_command` 定义 **52 个**、文件 **5693 行**。

### ◇-02 `/model --once` 在 picker 路径被静默降级

`--once` 的一次性还原(`gateway/slash_commands.py:2243-2250`)与「跳过写透」
(2264–2273)只存在于 `_finish_switch`;picker 回调闭包(1812–2059)两者皆无,
且写透无条件(1936–1945)。`restore_snapshot` 全文只在 1765/2247 出现。
文档 `slash-commands.md:77` 只说 "`--once` applies to the next turn only",
未区分打字/点选。测试 `tests/gateway/test_48031_...py:77-87` 是 AST 断言
「模块里某处有 `was_auto_reset = False`」,**不区分路径**,所以两处缺口都没被钉住。

### ◇-03 `/goal` 的 5 个子命令在 messaging 文档里缺席

代码有:`show`(2625)、`wait <pid> [reason]`(2660)、`unwait`(2678)、
`gate [list|add|remove|clear]`(2684)、`draft <objective>`(2718)、内联
`field: value` 契约解析(2738–2742)。
`website/docs/reference/slash-commands.md:252`(messaging 表)只列
`status / pause / resume / clear`。注册表 `hermes_cli/commands.py:159-161` **列全了**
(`args_hint="[text | draft <text> | show | gate add <cmd> | pause | resume | clear | status | wait <pid> | unwait]"`)。
⇒ website 文档落后于注册表与代码。

### ◇-04 `/fast` 的支持性判定忽略会话级模型覆盖

`gateway/slash_commands.py:3697-3700` 用 `_resolve_gateway_model(_load_gateway_config())`,
而 `_resolve_gateway_model`(`gateway/run.py:3256-3269 @ 863e313`)只读 config.yaml。
相邻的 `/reasoning` 在 `gateway/slash_commands.py:3507-3509` 明确读了
`_session_model_overrides`。同一文件两种「当前模型」定义。

### ◇-05 `/goal show` 在 agent 运行时被拒(纯查询却进不了白名单)

`_busy_goal_command` 白名单(`gateway/run.py:14319-14323 @ 863e313`)含
`status/pause/resume/clear/stop/done/unwait` 与前缀 `wait|gate`,**不含 `show`**;
而 `show` 的实现(`gateway/slash_commands.py:2625-2626`)只读两个 render 函数。

### ◇-06 多 profile 作用域只覆盖 3 个命令

`_resolve_profile_home_for_source` 在 5693 行的 mixin 里只出现 3 次:
`/profile`(358)、`/model`(1697)、`/compress`(3966)。
其余写 config 的命令都用 `from gateway.run import _hermes_home`(2494/2498、3341/3343、
3585/3593、3634/3641、3807/3809、3876/3879),而 `_hermes_home` 是
**import 时的一次性快照**(`gateway/run.py:1822 @ 863e313` `_hermes_home = get_hermes_home()`),
不受 `set_hermes_home_override` 契约变量影响。
对照:读路径 `_load_gateway_config` **是** profile 感知的
(`gateway/run.py:3137-3142 @ 863e313` 的 `_gateway_config_home()` 会先看 override)。
⇒ 多 profile 网关上,`/personality` `/reasoning --global` `/fast --global` `/memory approval`
`/skills approval` `/verbose` `/footer` 全部写到**默认 profile** 的 config.yaml。

### ◇-07 `/undo` 有两个容错策略相反的 N 解析器

调度层 `gateway/run.py:15250-15256`(宽容,坏输入→1)vs handler
`gateway/slash_commands.py:2955-2964`(严格,坏输入→报错)。
后果:`/undo -y`(文档 `slash-commands.md:310` 给 CLI 建议的写法)在 gateway 上
先弹确认框、批准后再报参数错误。

### ◇-08 `_resolve_slash_confirm` 是幽灵 API

`gateway/platforms/base.py:3766 @ 863e313` 的适配器契约文档写:
「Button callbacks MUST be routed back through the gateway by calling
``GatewayRunner._resolve_slash_confirm(confirm_id, choice)``」。
全仓 grep:该方法**不存在**,只在这条 docstring 与
`gateway/slash_commands.py:5210` 的一句注释里出现。
真实契约是适配器直接调 `tools.slash_confirm.resolve(session_key, confirm_id, choice)`
(whatsapp 1869、relay 1919、run.py 14687 都是这么做的)。
⇒ 照 base.py 文档写新适配器会写不出来。

### ◇-09 `tools/slash_confirm.py` docstring 说「目前只有 /reload-mcp」

`tools/slash_confirm.py:3-5 @ 863e313`:
「Slash commands that have a non-destructive but expensive side effect worth
surfacing to the user (currently only ``/reload-mcp``, ...)」。
实际调用方有 4 类:`/reload-mcp`、`/model` 贵模型闸(**2433,本切片**)、
`/new` `/reset` `/undo`(经 `_maybe_confirm_destructive_slash`)。
`gateway/platforms/base.py:3758-3760` 的 "the current caller is ``/reload-mcp``, which
invalidates the provider prompt cache" 同病。

### ◇-10 `/compress --preview|--dry-run` 在 website 文档里缺席

注册表 `hermes_cli/commands.py:130-131 @ 863e313` 写了
`args_hint="[here [N] | focus topic | --preview|--dry-run]"`,代码还额外支持
`--dryrun`、`--keep N`、`up to here`(`hermes_cli/partial_compress.py:55-99, 111-142 @ 863e313`)。
`website/docs/reference/slash-commands.md:47` 与 `:236` 都只写了 `here [N]` 与 focus topic。

### ◇-11 gateway 的破坏性确认在文档里被写成「CLI 才有」

`website/docs/reference/slash-commands.md:297-299`:
「**The CLI** prompts before running slash commands that throw away unsaved session state.」
但 `_maybe_confirm_destructive_slash` 是 `GatewayRunner` 的方法
(`gateway/run.py:20483 @ 863e313`),在 `/new`(15066)与 `/undo`(15260)分发处生效,
并在 Telegram/Discord/Slack/WhatsApp 上渲染按钮。

### ◇-12 `/diff <path>` 在 gateway 上被静默忽略

`collect_working_diff` 支持 `paths`(`tools/working_diff.py:70-77 @ 863e313`),
gateway 只传 `(cwd, mode)`(`gateway/slash_commands.py:3226`),未知 token 在
3208–3217 的扫描里被丢弃。CLI 文档 `:49` 写了 `[path...]`,messaging 文档 `:248`
没写——文档没矛盾,但「同名命令两侧语义不同」只能靠读两张表推断。

### ◇-13 输出层风格不统一(i18n vs 硬编码英文)

走 `t(...)` 的:`/model` `/personality` `/retry` `/undo` `/sethome` `/voice`
`/rollback` `/diff` `/background` `/reasoning` `/fast` `/verbose` `/footer` `/compress` `/yolo`。
硬编码英文的:`/codex-runtime`(2464、2489–2490)、`/goal` 的 wait/unwait/gate/draft
分支(2663、2668、2673、2675、2680–2681、2696–2713、2721、2772)、`/heartbeat` 全部
(2789、2798、2803、2806、2812、2827–2833、2838、2841–2845)、`/refine` 全部
(2858、2860、2869、2873、2884、2886–2889)、`/subgoal` 全部(2903、2915、2919、
2923–2924、2929、2932–2933、2938、2940)、`/skills`(3646–3648、3664–3666、3675–3676)、
`/approvals`(3775)、`/memory` 的 usage 兜底(3614–3615)。
⇒ 新命令一律不接 i18n,老命令接了。这条边界与「命令新旧」相关,不与「命令重要性」相关。

---

## 5. issue 溯源(切片内 2000–4000 出现的编号)

| # | 行号 | 什么输入 → 什么现象 → 为什么 → 怎么修 |
|---|---|---|
| **#41289** | 2094、2130 | 用户敲 `/model`(无参)→ 网关整体冻结 120–150s,所有平台"application did not respond",排队的 agent 全部延迟启动 → `list_picker_providers` / `list_authenticated_providers` / `switch_model` 都是同步函数,provider 磁盘缓存过期时会走 `urllib`/`requests` 同步 HTTP(15s 超时),而它们直接在 asyncio 事件循环上执行 → 三处全部 `asyncio.to_thread` 包裹。修法从 #41304 移植(那次改的是搬家前的 `gateway/run.py`)。测试 `tests/gateway/test_model_command_async_offload.py` 用「必须经 to_thread 派发、不得直接调用」的双向断言把它钉成变异可存活。 |
| **#20525** | 2130 | 同上的更早一例,专指 `switch_model()` 落到 models.dev 的 `requests.get`。 |
| **#50163** | 2191(及 picker 侧 1883) | 用户 `/model <一个坏模型>` → 换模型失败,但下一条消息起整个对话变砖 → `cached_entry[0].switch_model()` 内部会把 agent 回滚到旧模型再抛;旧代码接住异常后仍继续提交:写会话 DB、写 `_session_model_overrides`、evict 缓存 agent。下一回合从坏 override 重建 agent → 死 → 对话丢失 → 在 `except` 里**提前 return**,跳过 DB 持久化、override 写入、缓存驱逐、config 写入。「失败的换模型必须是 no-op」。 |
| **#34850** | 2203(及 picker 侧 1896) | 用户在 Telegram `/model X` → 仪表盘上该会话仍显示旧模型 → 换模型只改了进程内 override,没写会话 DB → 在两条提交路径都加 `_session_db.update_session_model(session_id, result.new_model)`。 |
| **#48031** | 2210 | 会话因空闲/每日/挂起被自动重置后,用户的**第一条**消息就是 `/model X` → 该次切换生效,但**下一条普通消息**之后模型又变回 config 默认,而会话 DB 里却记着新模型(双源分歧)→ slash 路径不经过消费 `was_auto_reset` 的那段消息处理逻辑,所以标志仍为 True;下一条消息的自动重置清理块先跑,把刚存的 override 一起清掉 → 两处消费:`gateway/run.py` 的清理块捕获到局部变量后立刻置 False;`gateway/slash_commands.py:2211-2212` 在写 override **之前**消费。**注意 picker 路径未修**(◇-02)。 |
| **#29923** | 2261 | `/model X --once` 后网关在还原前崩溃 → 重启后 once 模型**永久**生效 → 初版实现把 once override 也写透到了 session store,重启会 rehydrate 它 → `if not one_turn:` 包住写透(2264)。注释明确记为 "review defect",即 code review 阶段发现的缺陷,不是线上事故。 |
| **#25107** | 2318(及 picker 侧 1993) | 用户切到一个 **custom provider**,而该 provider 的解析器返回**空** `base_url` → config.yaml 里留着上一个 endpoint 的 `base_url`,`api_mode` 从来没被写进去过 → 旧代码是两个**独立**的 `if`:`if result.base_url: 写` 和 `if 非custom: clear`。命名 provider 走第二个 if 总会清干净,所以 bug 隐形;custom + 空 base_url 时**两个分支都不触发** → 对 custom 目标做**显式的 set-or-clear**(2319–2328)。测试 `tests/gateway/test_25107_stale_base_url_api_mode.py` 同时覆盖 picker 与打字两条路径。 |
| **#30479** | 3501(`/model` 侧同一修法在 1760) | Telegram **DM topic**(私聊话题)里敲 `/reasoning high` → 设置不生效 → slash 路径直接用原始 source 派生 session_key,而普通消息回合会先做 DM topic 恢复(normalize)再派生;两者算出的 key 不同,写进去的 override 下一回合读不到 → 在派生 key 前先 `await asyncio.to_thread(self._normalize_source_for_session_key, source)`。**注意 `/reasoning` 只修了一半**:3511/3542/3549 仍传未规范化的 `event.source`。 |

**切片边界外但同一 handler 内的相邻编号**(供交叉参考):#49066 / #49176(picker 与
打字的持久化行为分裂,1954)、#44794 / #39704 / #61145 / #38763 / #50422 / #3854 / #6217
(`/compress` 本体 4012–4251)、#35994 / #53175(off-loop 清理,4301 与模块常量 56)。

---

## 6. 测试(钉住本切片行为的文件)

| 测试文件 | 钉住的行为 |
|---|---|
| `tests/gateway/test_model_command_async_offload.py` | `/model` 两处 provider 列举必须经 `asyncio.to_thread`(#41289),断言双向(不得直接调用) |
| `tests/gateway/test_model_command_context_offload.py` | `/model` 的上下文长度解析不得阻塞事件循环 |
| `tests/gateway/test_model_command_expensive_confirm.py` | 贵模型闸四条路径:有警告→返回确认提示且**不切换**;`once`→切换;`cancel`→不切换;便宜模型→直接切换无提示。用 `_fake_request_slash_confirm` 替身(104–108) |
| `tests/gateway/test_25107_stale_base_url_api_mode.py` | custom provider 空 base_url 时,picker 与打字两条路径都必须 set-or-clear `base_url`/`api_mode` |
| `tests/gateway/test_model_picker_persist.py` | picker 回调必须遵循 `persist_global`(#49066/#49176);用假 picker adapter 捕获 `on_model_selected` 后直接调用 |
| `tests/gateway/test_model_command_flat_string_config.py` | config.yaml 里 `model: <字符串>`(扁平)时 `--global` 不得抛 `TypeError`(对应 2286–2300) |
| `tests/gateway/test_model_switch_persistence.py` | 会话 override 替换全部字段 / 无 override 返回原值 / once 快照还原(87–150) |
| `tests/gateway/test_48031_model_switch_after_auto_reset.py` | AST 不变式:run.py 清理块与 slash_commands.py 模型路径都必须 `was_auto_reset = False` |
| `tests/gateway/test_session_model_override_persistence.py` / `_routing.py` / `_credential_pool.py` | override 的落盘/路由/凭据池行为 |
| `tests/gateway/test_choice_picker.py` | 裸 `/reasoning`、裸 `/fast` 在支持的适配器上发 picker;**点选结果与打字结果一致**;`/fast` 点选默认会话级 |
| `tests/gateway/test_reasoning_command.py` | `_parse_reasoning_command_args("high --global") == ("high", True)`、`("—global xhigh") == ("xhigh", True)`;会话 override 优先于配置 |
| `tests/gateway/test_reasoning_config_per_model.py` | 按模型的 reasoning 覆盖解析 |
| `tests/gateway/test_fast_command.py` | `--global` 落盘 `agent.service_tier`;会话 override 胜过配置默认;路由注入 priority 不改运行时 |
| `tests/gateway/test_voice_command.py` | `/voice off`、on→off 切换、落盘持久化、**平台隔离**(不同平台的 voice_key 互不影响) |
| `tests/gateway/test_voice_mode_platform_isolation.py` | 同上的专项 |
| `tests/gateway/test_diff_command.py` | `/diff` 长输出被截断;`/diff session` 报告累计变更;无变更时的文案 |
| `tests/gateway/test_background_command.py` | 无 prompt / `/bg` 别名 / 空 prompt 三种 usage;无凭据时投递错误;成功时投递结果;`/background` 出现在 help 与自动补全里 |
| `tests/gateway/test_compress_preview.py` | `--preview` + `here N` 边界;`--aggressive --dry-run` 出预览**加**不支持说明 |
| `tests/gateway/test_compress_focus.py` | focus topic 透传到 `_compress_context` |
| `tests/gateway/test_compress_command.py` | 8 例:自动压缩关闭时手动仍可用;aux 模型失败即使恢复也要提示;**in-place 不做破坏性 rewrite**(#61145);保留 platform 与 gateway_session_key(#50422);tool 消息要传给压缩器(#3854);多 profile 密钥作用域;单 profile 跳过解析;清理不阻塞事件循环(#35994/#53175) |
| `tests/gateway/test_verbose_command.py` | 默认关闭;开启后循环;`"false"`(带引号)也算关 |
| `tests/gateway/test_footer_command_mid_run.py` | `/footer` 在 agent 运行时必须进它自己的 handler,而不是 busy 兜底文案。**没有任何测试覆盖 `/footer on|off|status` 的参数**——▲-01 因此从未被发现 |
| `tests/gateway/test_yolo_command.py` | `/yolo` 只影响当前会话 |
| `tests/gateway/test_approvals_command.py` | 非 admin 不能改持久化审批模式 |
| `tests/gateway/test_undo_rewind_session.py` | `rewind_session` 默认 1 回合 / N 回合 |
| `tests/gateway/test_retry_replacement.py` | `/retry` 替换 transcript 里最后一个用户回合 |
| `tests/gateway/test_retry_response.py` | `/retry` 必须返回 agent 响应而非 None |
| `tests/gateway/test_destructive_slash_confirm.py` | 门开时注册 pending confirm;`always` 落盘 opt-out 并执行 |
| `tests/gateway/test_destructive_slash_always_persist_report.py` | 5 例:落盘失败要如实报告失败 / 成功报成功 / 抛异常也报失败 / `once` 既不落盘也不加注 / `cancel` 不落盘 |
| `tests/gateway/test_approve_deny_commands.py` | A 套审批 13 例(FIFO、`all`、`session`、reason、并行子代理、路由到发起会话、契约变量优先于被污染的 environ) |
| `tests/gateway/test_plaintext_approval_routing.py` | 裸 `yes` 只在有 pending 审批时才被消费 |
| `tests/gateway/test_35994_reset_button_deadlock.py` | 确认按钮 handler 不得在事件循环里同步阻塞 |
| `tests/gateway/test_goal_max_turns_config.py` / `test_goal_status_notice.py` / `test_goal_verdict_send.py` / `test_goal_continuation_drain.py` | `/goal` 周边 |
| `tests/gateway/test_telegram_model_picker.py` / `test_discord_model_picker.py` | 两个平台的 picker 渲染 |

**覆盖空洞(值得记进报告)**:
- `/footer` 参数解析:零覆盖(▲-01);
- `/model --once` 的 picker 路径:零覆盖(◇-02);
- `/heartbeat` `/refine` `/subgoal` `/rollback` `/sethome` `/personality`(gateway 侧)
  `/codex-runtime`:`tests/gateway/` 下 grep 不到直接驱动它们 handler 的测试。

---

## 7. 重实现要点(造自己的 harness 时抄什么、避什么)

**抄**:

1. **「解析器单一属主 + 平台装饰」**。`/model` 把 flag 解析交给
   `hermes_cli.model_switch.parse_model_switch_args`,gateway 只加 `❌ ` 前缀
   (1709–1711,区间外);`/memory` `/skills` 把子命令解析交给 `handle_pending_subcommand`,
   用 `None` 返回值表示「不认识」,由平台侧补 usage 文本(3613–3615、3663–3666)。
   这样 CLI 与 messaging 永远不会解析出不同结果。
2. **「一个应用器,两个入口」**。`_apply_reasoning_selection`(3361)与
   `_apply_fast_selection`(3702)让打字和点选走同一段代码。反例就在同文件:
   `/model` 的 picker 与打字各写一份提交逻辑,结果三处行为分叉(§2.1.2)。
   **凡是「同一个语义有两个 UI 入口」,先抽应用器再接 UI。**
3. **「失败的状态变更必须是 no-op」**。#50163 的修法(2186–2200):把唯一可回滚的
   一步(agent 原地换模型)放在事务最前面当 prepare,失败就提前 return,后面
   6 步一步都不做。
4. **「读-改-写必须读 raw,不读 merged」**。切片里 5 处都写了同一条注释。
   把内置默认合并后写回用户文件 = 把默认值固化,以后升级改不动。
5. **确认闸的双通道收口**:`_request_slash_confirm` 用「按钮成功→返回 None,
   按钮失败→把提示文本当回复」把两条路收在一个返回值里
   (`gateway/run.py:20655-20661`);状态放模块级而非 runner 上,适配器回调不需要
   反向引用(`tools/slash_confirm.py:18-21`)。
6. **确认状态的四道闸**:ID 比对(防被新提示取代的旧按钮)、pop-before-run
   (防双击)、超时(300s)、handler 异常兜成用户可读文案
   (`tools/slash_confirm.py:115-140`)。**顺序**:pop 在超时检查之前。
7. **fail-closed 的选项归一**:relay 把未知 option 一律映射到最保守值
   (`cancel` / `deny`,`gateway/relay/adapter.py:1888-1896, 1913-1917`)。
8. **拒绝时给替代方案**:`--aggressive` 不支持,但文案直接告诉你用
   `/compress here [N]` 或 `/undo`(`locales/en.yaml:111`)。
9. **不要承诺没做到的事**:`always` 落盘失败时明说「下次还会问」
   (`gateway/run.py:20560-20569`),而不是照抄成功文案。
10. **副作用边界二次鉴权**:`/approvals` 在中心闸之外再判一次 admin,
    理由写在注释里(「中心闸可以被配置放宽」,3770–3775)。
11. **该 evict 的 evict,不该 evict 的别 evict**:配置类命令普遍
    `_evict_cached_agent`;但审批模式变更**刻意不 evict**,因为审批检查每次重读配置,
    而 evict 会打断 prompt cache 前缀(3777–3778)。**「什么时候不能动 prompt 前缀」
    要成为 harness 的一等约束。**
12. **`AsyncSessionStore` 的 `__getattr__` 代理**(`gateway/session.py:1189-1203 @ 863e313`)——
    12 行代码让整个同步 SessionStore 的每个方法自动获得 `asyncio.to_thread` 包装。
    slash handler 里所有 `await self.async_session_store.xxx()` 都天然离线程。
13. **asyncio 火后不管任务要持强引用**:`self._background_tasks.add(_task)` +
    `add_done_callback(discard)`(3332–3333)。

**避**:

1. **不要在 handler 里手写第 23 个 `split()`**。切片里 17 个命令各写各的,
   于是同一个 `/undo` 在调度层和 handler 层有两套相反的容错(◇-07),
   `/footer` 读了个不存在的属性也没人发现(▲-01)。**做一个声明式的参数 spec**
   (注册表里已经有 `args_hint` / `subcommands` 字段了——让它**可执行**而不只是文案)。
2. **不要让「能力探测」有两种范式**。`hasattr(adapter, "join_voice_channel")`(实例)
   与 `getattr(type(adapter), "send_choice_picker", None)`(类)与
   「调用后看 `SendResult.success`」(`send_slash_confirm`)三种并存,
   区别只在 base 有没有默认实现。**统一成显式的 capability 集合。**
3. **不要让「当前模型是什么」有两个答案**(◇-04)。
4. **不要在多租户 harness 里用 import 时快照的 home 路径**(◇-06)。
   `_hermes_home = get_hermes_home()` 在 import 时求值,契约变量覆盖对它无效;
   读路径是 profile 感知的、写路径不是,这种不对称最难查。
5. **审批的目标定位要么真做,要么明说没有**。A 套的按钮里带着 `approval_id`,
   却只用它查 session_key,resolve 仍按 FIFO(§3.6)——ID 看起来像目标定位,
   实际不是。并行子代理场景下用户点第二个按钮会批准第一个请求。
   **要么把 ID 传到 resolver,要么别在 payload 里放 ID。**
6. **适配器契约文档里的方法名必须存在**(◇-08 的 `_resolve_slash_confirm`)。
7. **`--once` 之类的一次性语义,必须在「所有入口」都实现**,否则用户学到的规则会骗他
   (◇-02)。
8. **输出截断要有统一层**。切片里有 4 个独立的魔数(diff 60行/3000字、
   skills diff 3000字、background 预览 60字、undo 预览 200字、personality 预览 50字、
   deny reason 280字),每个都硬编码在 handler 里。**做一个
   `truncate_for_chat(text, kind)`,让平台上限参与计算。**

---

## 8. 与本切片相关但在区间外的必读

- `gateway/slash_commands.py:106-117` — `_typed_command_prefix_for`(2432 使用)
- `gateway/slash_commands.py:1671-1999` — `/model` 前半(picker 构建、无参分支)
- `gateway/slash_commands.py:5377-5495` — `/approve` `/deny`(§3.6)
- `gateway/run.py:14646-14694` — slash-confirm 文本兜底解析器(§3.4)
- `gateway/run.py:20483-20661` — `_maybe_confirm_destructive_slash` + `_request_slash_confirm`
- `gateway/run.py:14083-14160`、`14307-14326` — busy 分发表与 `_busy_goal_command`
- `gateway/run.py:15731`、`15763-15777` — `--once` 还原的消费点
- `tools/slash_confirm.py`(167 行,全文)
- `tools/approval.py:2490-2529`、`2970-2981` — `resolve_gateway_approval` / `has_blocking_approval` 与超时
- `gateway/platforms/base.py:2054-2158`(MessageEvent)、`2375-2400`(EphemeralReply)、
  `3745-3778`(`send_slash_confirm` 契约)
- `hermes_cli/commands.py:105-235` — 本切片命令的 CommandDef(`busy_policy` /
  `gateway_config_gate` / `args_hint` / `subcommands`)
