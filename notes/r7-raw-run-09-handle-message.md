# r7 底稿 · run.py 第 6 段(14328–16276)——`_handle_message` 主入口与入站文本预处理

> 对象:`/home/user/hermes-agent/gateway/run.py` 第 14328–16276 行 @ 863e313(只读基线)。
> 证据格式:`gateway/run.py:行号 @ 863e313` + 逐字摘录(≤25 行/处),行号已用 Read 逐段核实。
> 本段方法清单(行号为 def 起始行):
> - `_handle_message`:14328–15743(约 1416 行,收消息主入口)
> - `_restore_moa_one_shot`:15745–15761
> - `_restore_pending_one_turn_model_override`:15763–15776
> - `_prepare_inbound_message_text`:15778–16184(407 行)
> - `_prepare_profile_scoped_inbound_message_text`:16186–16208
> - `_prepare_clarify_reply_text`:16210–16222
> - `_consume_pending_native_image_paths`:16224–16230
> - `_cache_session_source`:16232–16251
> - `async_session_store`(property):16253–16260
> - `_get_cached_session_source`:16262–16274
>
> **任务描述修正(两处,先说清)**:
> 1. `_is_stale_restart_redelivery` 的调用点**不在** `_handle_message` 里,而在 `/restart` 的
>    处理器 `gateway/slash_commands.py:1538`(`_handle_restart_command` 内);`_handle_message`
>    只是在 15113–15114 把 `/restart` 分发过去。该函数定义在 run.py:18528(第 7/8 段范围)。
> 2. 时间戳注入(`gateway/message_timestamps.py`)**不在** `_prepare_inbound_message_text` 内,
>    而在其调用者 `_handle_message_with_agent` 的 17477–17511(预处理返回后紧接着做),另有
>    历史回放侧注入在 `_build_gateway_agent_history`(run.py:1316,经 5103 传 `inject_timestamps`)。
>    本底稿仍交代两者关系(见 §3.13)。

---

## 0. 全景:`_handle_message` 是什么

`_handle_message(event) -> Optional[str]` 是所有平台适配器(Telegram/Slack/Discord/…)归一化出
`MessageEvent` 后的唯一入口(适配器经 `handle_message` → gateway 的 `_message_handler` 即本函数)。
返回值语义:`str` = 要回给用户的文本;`""` = 已处理但不回话;`None` = 丢弃/已排队。

它按固定顺序过 21 个关卡(阶段),前 19 个都是"能不能进入 agent 回合"的筛选;第 20 阶段抢占
会话槽位(sentinel + run generation + turn lease),第 21 阶段才把事件交给
`_handle_message_with_agent`(run.py:16276,下一段的主角),并用 `finally` 保证释放。

阶段一览(行号为本段内实际顺序,后文逐个展开):

| # | 阶段 | 行号 |
|---|------|------|
| 0 | ContextVar 跨会话泄漏防护(`reset_session_vars`) | 14343–14358 |
| 1 | `is_internal` 判定 | 14360–14362 |
| 2 | Slack ignored-channel 丢弃(#51899) | 14364–14381 |
| 3 | 启动恢复窗口排队 | 14383–14389 |
| 4 | scale-to-zero 真实入站打点 | 14391–14397 |
| 5 | `pre_gateway_dispatch` 插件钩子(skip/rewrite/allow) | 14399–14441 |
| 6 | 鉴权 + 陌生 DM 配对码(含 user_id=None 通道) | 14443–14511 |
| 7 | 会话键计算 `_quick_key` + `/update` 提示应答拦截 | 14521–14587 |
| 8 | clarify 应答拦截 | 14589–14644 |
| 9 | slash-confirm 应答拦截 | 14646–14694 |
| 10 | busy 分流(stale 驱逐→预门命令→busy 分发→queue/steer/redirect/interrupt) | 14696–14957 |
| 11 | 冷路径命令解析(alias 预展开 + slash 访问控制) | 14959–15004 |
| 12 | `command:<canonical>` 钩子(deny/handled/rewrite) | 15006–15059 |
| 13 | 内建命令 if-链(约 50 个;含 5 个 fall-through 型) | 15061–15400 |
| 14 | draining 冷路径拒收 | 15402–15403 |
| 15 | 用户自定义 quick commands(exec/alias,#44727) | 15405–15465 |
| 16 | 插件注册命令 | 15467–15482 |
| 17 | skill bundle / stacked skill / skill 命令 / unknown-command | 15484–15629 |
| 18 | Telegram topic 大厅提醒 | 15635–15642 |
| 19 | 外部 drain 新回合闸门 | 15644–15663 |
| 20 | 抢占会话槽(sentinel + lease + run generation) | 15665–15688 |
| 21 | try/finally:进 agent → goal 续推 → MoA/one-turn 还原 → 释放 | 15690–15743 |

设计上最重要的一点:**筛选阶段全部无锁、可重入**,真正的互斥只靠第 20 阶段的 sentinel 抢占
("claim before any await"),所以前 19 阶段任何 await 都不会造成双 agent。

---

## 1. 阶段 0–5:事件预处理

### 1.1 ContextVar 跨会话泄漏防护(阶段 0)

**问题**:每条消息在独立 asyncio task 里处理,`create_task()` 会用 `copy_context()` 快照
"生成时刻"的上下文。若并发消息 A 已经 `set_session_vars()` 绑定了自己的 `HERMES_SESSION_*`
ContextVar,B 的 task 会继承 A 的会话身份;在 B 自己绑定之前,B 里 spawn 的任何子进程都会经
subprocess-env 桥读到 A 的会话身份(桥上的 `_UNSET`-strip 防护帮不上忙——变量不是 `_UNSET`,
是"被设成了 A")。

**实现**:入口第一件事就把所有会话 ContextVar 重置回 `_UNSET`。

gateway/run.py:14343-14358 @ 863e313
```python
        # 🔴 Cross-session leak guard. This handler runs inside a per-message
        # asyncio task created via create_task(), which snapshots the spawning
        # context with copy_context(). If a *concurrent* message had already
        # bound its session via set_session_vars() when this task was created,
        # we inherited ITS HERMES_SESSION_* ContextVars. Until we bind our own
        # (a few steps down, in _set_session_env), any subprocess spawned here
        # would read the foreign session's identity via the subprocess-env
        # bridge — the _UNSET-strip guard there can't help because the vars are
        # set-to-foreign, not _UNSET. Reset to _UNSET now so that window strips
        # safe (no session) instead of leaking the sibling's. See
        # gateway/session_context.reset_session_vars + the inheritance test.
        try:
            from gateway.session_context import reset_session_vars
            reset_session_vars()
        except Exception:
            logger.debug("reset_session_vars failed at handler entry", exc_info=True)
```

**调用关系**:`gateway/session_context.py:315`(`reset_session_vars`)。其 docstring
(session_context.py:315-338)明确区分 `reset`(回 `_UNSET`="从未绑定",task 开头用)与
`clear`(设 `""`="显式清空、抑制 os.environ 回退",handler 结束用)。行为规格测试:
`tests/tools/test_local_env_session_leak.py`、`tests/gateway/test_session_context_inheritance.py`。

**设计理由/取舍**:选择"入口重置"而不是"改 create_task 传空 context",因为后者要动每个
spawn 点且破坏其他合法继承;重置的代价是入口到 `_set_session_env` 之间的子进程读不到会话
(strip safe),这是有意接受的空窗——"无会话"永远比"别人的会话"安全。

**重实现要点**:
1. 每消息独立 task + ContextVar 会话身份的组合必然有继承泄漏,入口必须显式重置;
2. 重置目标是"从未绑定"哨兵而非空串——两者对 env 回退语义不同,要分成两个 API;
3. 泄漏面在 subprocess env 桥,单测要直接断言子进程 env,而不是只断言 ContextVar;
4. 防护包 try/except——防护本身失败不能挡消息处理。

### 1.2 internal 事件(阶段 1)

gateway/run.py:14360-14362 @ 863e313
```python
        # Internal events (e.g. background-process completion notifications)
        # are system-generated and must skip user authorization.
        is_internal = bool(getattr(event, "internal", False))
```

`event.internal=True` 的事件(后台进程完成通知、重启恢复重放等系统自造事件)贯穿全函数享受
四项豁免:跳过 ignored-channel(14371)、跳过启动恢复排队(14385)、不打 scale-to-zero 时钟
(14396)、跳过插件钩子(14406)、跳过鉴权(14443)、跳过 Telegram 大厅(15635)、跳过外部
drain 闸门(14654 处 `not is_internal`)。设计理由:这些事件不是"用户流量",既不能被用户侧
门禁挡住(否则后台任务结果丢失),也不能算作活跃流量(否则 idle 判定永不成立)。

### 1.3 Slack ignored-channel 最先丢弃(阶段 2,#51899)

**问题(#51899)**:配置了忽略的 Slack 频道,消息仍会走到配对/鉴权/会话建立,产生副作用
(如给陌生人发配对码、建会话状态)。

**实现**:该守卫放在**一切**之前——启动恢复排队、插件钩子、鉴权、会话之前:

gateway/run.py:14364-14381 @ 863e313
```python
        # Ignored-channel guard runs FIRST — before startup-restore queueing,
        # plugin hooks, auth, and session setup — so a configured ignored
        # channel can never reach pairing/auth/session state (#51899).
        # getattr: bare test runners construct GatewayRunner via
        # object.__new__ without config (see AGENTS.md pitfall on
        # object.__new__ test pattern).
        if (
            not is_internal
            and getattr(source, "platform", None) == Platform.SLACK
            and _is_slack_ignored_channel(
                getattr(self, "config", None), getattr(source, "chat_id", None)
            )
        ):
            logger.info(
                "Dropping Slack message from configured ignored channel %s",
                getattr(source, "chat_id", None),
            )
            return None
```

**调用关系**:`gateway/run.py:1289`(模块级 `_is_slack_ignored_channel`,支持 `"*"` 全忽略,
并用 `_slack_parent_channel_id` 把 thread 形 chat_id 归约到父频道)。

**重实现要点**:1) "忽略名单"必须在副作用链最顶端,否则忽略≠无痕;2) 用 `getattr` 容忍
`object.__new__` 裸构造的测试对象(全函数反复出现的仓库惯用法);3) thread id 要归约到父频道
再比对,否则忽略父频道挡不住线程消息。

### 1.4 启动恢复窗口排队(阶段 3)

**问题**:gateway 重启后要先重放/恢复中断的会话(startup auto-resume);恢复期间新到的用户
消息若直接处理,会与恢复重放交错、争抢同一会话。

**实现**:恢复进行中(`_startup_restore_in_progress`)时,非 internal、且自身不是恢复重放
(`_hermes_startup_restore_replay` 标志)的事件一律入队后返回:

gateway/run.py:14383-14389 @ 863e313
```python
        if (
            getattr(self, "_startup_restore_in_progress", False)
            and not is_internal
            and not getattr(event, "_hermes_startup_restore_replay", False)
        ):
            self._queue_startup_restore_event(event)
            return None
```

**调用关系**:`gateway/run.py:10229`(`_queue_startup_restore_event`,append 进
`_startup_restore_queue`);`gateway/run.py:10245`(`_drain_startup_restore_queue`,恢复完成后
逐条打上 `_hermes_startup_restore_replay=True` 再经 `adapter.handle_message(event)` 重放——
标志防止重放期间门还没开又被排回队列造成死循环)。

**重实现要点**:1) 恢复窗口用"排队后重放"而非"丢弃",用户无感;2) 重放事件必须带一次性标志
绕过同一道门;3) 队列 drain 经适配器入口走全流程(而不是直接调内部函数),保证与正常消息同管线。

### 1.5 scale-to-zero 真实入站打点(阶段 4)

gateway/run.py:14391-14397 @ 863e313
```python
        # scale-to-zero (Phase 0, 0.B/F13): stamp the gateway-scoped last-inbound
        # clock for real (user-originated) inbound only. Internal/system events
        # (background-process completions, startup-restore replays) are NOT
        # traffic — counting them would keep a genuinely idle gateway awake. This
        # clock is what the idle predicate (gateway/scale_to_zero.is_idle) reads.
        if not is_internal:
            self._scale_to_zero_note_real_inbound()
```

**调用关系**:`gateway/run.py:7586`(`_scale_to_zero_note_real_inbound`);消费方
`gateway/scale_to_zero.py` 的 `is_idle`。要点:idle 时钟只认"人发的",否则系统自噪声让
gateway 永不缩容。

### 1.6 `pre_gateway_dispatch` 插件钩子(阶段 5)

**问题**:插件(如客服接管 ingest)需要在**鉴权之前**处理来自未授权发送者的消息,否则陌生人
消息会先触发配对流程。

**实现**:钩子返回 dict 影响流向——`skip` 丢弃、`rewrite` 换文本继续、`allow`/None 正常:

gateway/run.py:14399-14420 @ 863e313
```python
        # Fire pre_gateway_dispatch plugin hook for user-originated messages.
        # Plugins receive the MessageEvent and may return a dict influencing flow:
        #   {"action": "skip",    "reason": ...}    -> drop (no reply, plugin handled)
        #   {"action": "rewrite", "text":  ...}     -> replace event.text, continue
        #   {"action": "allow"}   /   None          -> normal dispatch
        # Hook runs BEFORE auth so plugins can handle unauthorized senders
        # (e.g. customer handover ingest) without triggering the pairing flow.
        if not is_internal:
            try:
                from hermes_cli.lifecycle import invoke_hook as _invoke_hook
                _hook_results = _invoke_hook(
                    "pre_gateway_dispatch",
                    event=event,
                    gateway=self,
                    # getattr: bare-runner tests build GatewayRunner via
                    # object.__new__ without __init__ (pitfall #17), and the
                    # hook must not fail dispatch over a missing attribute.
                    session_store=getattr(self, "session_store", None),
                )
            except Exception as _hook_exc:
                logger.warning("pre_gateway_dispatch invocation failed: %s", _hook_exc)
                _hook_results = []
```

rewrite 用 `dataclasses.replace(event, text=_new_text)` 换出新 event 并重取 `source`
(gateway/run.py:14434-14439 @ 863e313,`event = dataclasses.replace(event, text=_new_text)`)。

**调用关系**:`hermes_cli/lifecycle.py` 的 `invoke_hook`(同步收集全部插件返回值)。

**重实现要点**:1) 钩子位置在鉴权之前是能力(处理陌生人消息)也是风险(插件可放行任何人),
文档要写明;2) rewrite 用不可变替换而非原地改字段,避免 event 被多处引用时的隐式串改;
3) 钩子异常必须吞掉降级为"无插件",不能让插件炸掉主管线;4) 多插件返回值按序处理,第一个
skip 生效、第一个 rewrite/allow break。

---

## 2. 阶段 6:鉴权与陌生 DM 配对码(14443–14511)

**问题**:开放网关要能让陌生人自助接入(低摩擦),又不能被垃圾消息刷爆或泄露信息(#9337:
配置了 allowlist 的网关给陌生人回配对码既吵又泄露 bot 存在)。

**实现分三叉**:internal 直通;`user_id is None`(Telegram 服务消息/频道转发/匿名管理员/
sender_chat)不能配对但可能被 chat 级 allowlist 授权,交给 `_is_user_authorized` 决定;普通
未授权用户在 DM 且平台策略为 `"pair"` 时发配对码:

gateway/run.py:14443-14465 @ 863e313
```python
        if is_internal:
            pass
        elif source.user_id is None:
            # Messages with no user identity (Telegram service messages,
            # channel forwards, anonymous admin posts, sender_chat) can't
            # be paired, but they can still be authorized via a
            # chat-scoped allowlist (e.g. TELEGRAM_GROUP_ALLOWED_CHATS
            # authorizes every member of the listed chat regardless of
            # sender). Defer to _is_user_authorized so that path runs.
            if not self._is_user_authorized(source):
                logger.debug("Ignoring message with no user_id from %s", source.platform.value)
                return None
        elif not self._is_user_authorized(source):
            logger.warning("Unauthorized user: %s (%s) on %s", source.user_id, source.user_name, source.platform.value)
            # In DMs: offer pairing code. In groups: silently ignore.
            if (
                source.chat_type == "dm"
                and self._get_unauthorized_dm_behavior(
                    source.platform,
                    profile=source.profile,
                )
                == "pair"
            ):
```

配对码发放(限流 → 生成 → 发消息,含多 profile 时 `-p <profile>` 参数提示):

gateway/run.py:14477-14500 @ 863e313
```python
                if pairing_store._is_rate_limited(platform_name, source.user_id):
                    return None
                code = pairing_store.generate_code(
                    platform_name, source.user_id, source.user_name or ""
                )
                if code:
                    adapter = self._adapter_for_source(source)
                    if adapter:
                        store_profile = getattr(pairing_store, "profile", None)
                        profile_arg = (
                            f"-p {store_profile} "
                            if isinstance(store_profile, str)
                            and store_profile
                            and store_profile != "default"
                            else ""
                        )
                        await adapter.send(
                            source.chat_id,
                            f"Hi~ I don't recognize you yet!\n\n"
                            f"Here's your pairing code: `{code}`\n\n"
                            f"Ask the bot owner to run:\n"
                            f"`hermes {profile_arg}pairing approve "
                            f"{platform_name} {code}`"
                        )
```

生成失败(限流/满额/锁定)时回一句"Too many pairing requests"并记限流,使后续消息静默
(gateway/run.py:14501-14510 @ 863e313,`pairing_store._record_rate_limit(...)`)。

**调用关系**:
- `gateway/authz_mixin.py:386` `_is_user_authorized`:五层判定(per-platform allow-all →
  env allowlist → 配对 approved 表 → 全局 allow-all → 默认拒),HA/Webhook 平台恒真
  (连接自身已认证),relay 平台信任上游认证(authz_mixin.py:403-430);
- `gateway/authz_mixin.py:785` `_get_unauthorized_dm_behavior`:决定 `"pair"`/`"ignore"`,
  优先级:平台级显式配置 > Email 默认 ignore(收件箱不是聊天,#见 docstring)> 全局显式配置 >
  adapter dm_policy > **配置了 allowlist 则默认 ignore(#9337)** > 无任何限制才默认 pair;
- `gateway/authz_mixin.py:371` `_pairing_store_for`:多路复用时按 `source.profile` 选
  per-profile PairingStore,回退全局 `self.pairing_store`(隔离各 profile 的白名单);
- `gateway/pairing.py:609` `generate_code`:码只存盐化 SHA-256(pairing.py:620-621
  "The code is NOT stored in plaintext"),常量:`CODE_TTL_SECONDS=3600`、
  `RATE_LIMIT_SECONDS=600`、`MAX_PENDING_PER_PLATFORM=3`(pairing.py:51-56);
  `_is_rate_limited`/`_record_rate_limit` 在 pairing.py:816/826;批准走 CLI
  `hermes pairing approve`(pairing.py:665 `approve_code`)。

**设计理由/取舍**:
- 配对方向是"陌生人拿码 → 管理员在 CLI 批准",而非"管理员发码给陌生人":码本身不授予任何
  权限(只是 pending 请求的凭据),所以泄露码无害,批准动作留在 owner 手里;
- 群聊里未授权一律静默——群里回配对码等于向整群暴露 bot 且刷屏;
- 限流对"发码"与"拒绝提示"一视同仁,防连发 DM 刷屏;
- `user_id=None` 不直接丢——chat 级 allowlist(如 `TELEGRAM_GROUP_ALLOWED_CHATS`)语义是
  "这个群的一切成员",服务消息也该被覆盖。

**重实现要点**:
1. 未授权 DM 的默认行为必须依 allowlist 是否存在而翻转(开放网关 pair、受限网关 ignore);
2. 配对码只存哈希 + TTL + per-platform pending 上限 + 失败锁定,四件套齐了才敢开放;
3. 限流状态要覆盖"拒绝路径",否则拒绝消息本身成为刷屏放大器;
4. 无 user_id 的消息走"chat 级授权"通道而不是早退;
5. 多 profile 网关按 profile 分 pairing store,并把 `-p` 参数拼进提示命令,否则 owner 批错库。

---

## 3. 阶段 7–9:三类"待答复"拦截(14513–14694)

这三个拦截解决同一类问题:**gateway 之外有个流程在等用户下一条消息作答**(detached 更新进程 /
agent 的 clarify 工具 / 危险 slash 的确认),必须在命令分发与 agent 回合之前截住,否则答复会被
当成普通聊天送进 LLM。三者共同的边界:**已识别的 slash 命令一律放行**——用户此刻显然想执行
命令而不是作答。

### 3.1 会话键计算(14521)

gateway/run.py:14521-14522 @ 863e313
```python
        _quick_key = self._session_key_for_source(source)
        _up_state = self._peek_session_state(_quick_key)
```

**调用关系**:`gateway/run.py:6679` `_session_key_for_source` → 优先
`session_store._generate_session_key(source)`(gateway/session.py:1725),回退模块级
`build_session_key`(gateway/session.py:1058)。键格式(session.py:1096-1132):
`<ns>:<platform>:<chat_type>:...`,ns 默认 `agent:main`(多 profile 时换 namespace);DM 附
chat_id(+thread_id;无 chat_id 回退 participant_id 防跨用户串史);群聊附 chat_id
(+per-user id,受 `group_sessions_per_user` 控制)+thread_id(默认线程共享,
`thread_sessions_per_user=False`);Slack 额外插 workspace `scope_id`。
`_peek_session_state`(run.py:5841)是"只读不建"版的 `_session_state`(run.py:5832)。

### 3.2 `/update` 提示应答拦截(14513–14587)

**问题**:`/update` 起的 detached 更新进程要问用户 y/n(它写 `.update_prompt.json`,watcher
转发给用户);用户的回答要写回 `.update_response` 文件供更新进程继续。但若不识别 slash,
`/new`、`/help` 会被当成答案静默吞掉。

**实现**:`update_prompt_pending` 置位时,`/approve|/yes`→"y"、`/deny|/no`→"n"、其他已识别
命令→空答案(取 prompt 默认值)并放行命令、其余文本→原样作答。写文件用 tmp+replace 原子写:

gateway/run.py:14548-14561 @ 863e313
```python
            if response_text:
                response_path = _hermes_home / ".update_response"
                prompt_path = _hermes_home / ".update_prompt.json"
                try:
                    tmp = response_path.with_suffix(".tmp")
                    tmp.write_text(response_text, encoding="utf-8")
                    tmp.replace(response_path)
                    prompt_path.unlink(missing_ok=True)
                except OSError as e:
                    logger.warning("Failed to write update response: %s", e)
                    return f"✗ Failed to send response to update process: {e}"
                _up_state.persistent.update_prompt_pending = False
                label = response_text if len(response_text) <= 20 else response_text[:20] + "…"
                return f"✓ Sent `{label}` to the update process."
```

已识别命令的"写空答案解锁"分支(14568–14587):否则 detached 进程会阻塞在 stdin 直到
watcher 30 分钟超时(注释 14562-14567:"unblock the detached update subprocess by writing a
blank response so `_gateway_prompt` returns the prompt's default")。命令识别经
`hermes_cli/commands.py` 的 `resolve_command`(14535)。

**重实现要点**:1) 跨进程问答用文件信箱(prompt.json / response 文件)+ 原子写;2) pending 态
下已识别命令必须"先解锁再放行",两头都不能卡;3) 回执裁剪到 20 字防刷屏。

### 3.3 clarify 应答拦截(14589–14644)

**问题**:agent 的 clarify 工具(向用户提问并阻塞等待)挂起时,用户下一条消息就是答案,
必须送回 clarify 的 resolve 通道而不是开新回合。

**实现**:查 `tools/clarify_gateway.get_pending_for_session(_quick_key,
include_choice_prompts=True)`(14596-14599);语音答复先转写(`_prepare_clarify_reply_text`,
见 §7),转写失败保留 pending 并静默返回(14605-14612);slash 开头放行(14617);其余文本经
`resolve_text_response_for_session` 解析("2" 映射到第二个选项,任意文本成自定义答案):

gateway/run.py:14617-14625 @ 863e313
```python
            if _raw_clarify_reply and not _raw_clarify_reply.startswith("/"):
                _resolved = _clarify_mod.resolve_text_response_for_session(
                    _quick_key, _raw_clarify_reply,
                )
                if _resolved:
                    logger.info(
                        "Gateway intercepted clarify text response (session=%s, id=%s)",
                        _quick_key, _pending_clarify.clarify_id,
                    )
```

答复被接受后恢复平台 typing 指示(14632-14640,`resume_typing_for_chat`——clarify 等待期间
暂停了指示;不恢复的话 Slack 会静默到三分钟心跳才动),最后 `return ""` 防适配器双发
(14641-14644:"Acknowledge with empty string so adapters that emit the agent's response
don't double-post. The agent itself will produce the next user-facing message.")。

**调用关系**:`tools/clarify_gateway.py:179`(`get_pending_for_session`)、`:316`
(`resolve_text_response_for_session`);语音路径 `_pending_event_audio_paths`
(run.py:21706)、`_transcribe_pending_audio_event_once`(run.py:21715)。

**重实现要点**:1) "agent 在等提问答案"是会话级状态,入口必须先查再分发;2) 语音答案要先转写、
转写空则保留 pending(用户可重试,超时 agent 拿空答案解锁);3) 拦截成功返回空串而非答案文本,
下一条用户可见消息由被解锁的 agent 产出;4) 恢复 typing 指示是易漏的 UX 细节。

### 3.4 slash-confirm 应答拦截(14646–14694)

**问题**:`/reload-mcp` 等危险 slash 弹确认后,用户的 `/approve`/`/always`/`/cancel` 要接到
confirm 通道;但 `tools/approval.py` 的危险命令审批若同时挂起,`/approve` 必须优先解锁那边
阻塞中的工具线程。

gateway/run.py:14652-14664 @ 863e313
```python
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
```

关键词匹配双通道:命令形(`/approve|/yes|/ok|/confirm`→once,`/always|/remember`→always,
`/cancel|/no|/deny|/nevermind`→cancel)与裸词形(`_norm_reply = _raw_reply.lstrip("!/")`,
14671——Slack 线程里 `/` 被平台吞,提示文案教用户打 `!always`,而适配器只重写
`!<已注册命令>`,`always`/`cancel` 不是注册命令所以 `!` 会活到这里)。匹配则
`await _slash_confirm_mod.resolve(...)`(14687);不匹配且 pending 已过期则
`clear_if_stale`——"用户显然翻篇了",不让确认卡死正常使用(14691-14694)。

**调用关系**:`tools/slash_confirm.py:71/84/99`(`get_pending`/`clear_if_stale`/`resolve`);
`tools/approval.py:2526`(`has_blocking_approval`)。

**重实现要点**:1) 多个"等确认"子系统并存时要定死优先级(工具审批 > slash 确认);2) 平台吞
`/` 的现实要求接受 `!`/裸词等替代形;3) stale confirm 必须能被无关消息冲掉,不能永久拦路;
4) `always` 选项落盘记忆,确认器 API 要区分 once/always/cancel 三值而非布尔。

---

## 4. 阶段 10:busy 分流——agent 正在跑时来了新消息(14696–14957)

这是全函数最重的一段。总原则(14696-14698 注释):默认立即打断(interrupt)保证低延迟,但有
一长串例外把打断降级为排队。

### 4.1 stale 锁驱逐(14704–14755)

**问题**:handler 挂死/崩溃会泄漏 running 槽,把会话永久锁死。难点:改成"不活动超时"后,
活跃任务可以合法跑几小时,单看墙钟龄不能驱逐。

**实现**:`HERMES_AGENT_TIMEOUT`(默认 1800s)作为**空闲**阈值;取 agent 的
`get_activity_summary()` 读 `seconds_since_activity`;拿不到摘要视为 idle=inf;另设墙钟
极限(`max(timeout*10, 7200)`)兜底 agent 对象已被 GC 的情形。sentinel 永不驱逐:

gateway/run.py:14714-14720 @ 863e313
```python
            _stale_agent = _quick_state.turn.agent
            # Never evict the pending sentinel — it was just placed moments
            # ago during the async setup phase before the real agent is
            # created.  Sentinels have no get_activity_summary(), so the
            # idle check below would always evaluate to inf >= timeout and
            # immediately evict them, racing with the setup path.
            _stale_idle = float("inf")  # assume idle if we can't check
```

驱逐动作 = 先 `_invalidate_session_run_generation(reason="stale_running_agent_eviction")`
再 `_release_running_agent_state`(14751-14755)——先作废代数再清槽,防被驱逐者的迟到 unwind
回写。

**重实现要点**:1) 驱逐判据用"最近活动时间"而非"开始时间";2) 哨兵对象必须豁免(它天生没有
活动摘要);3) 驱逐 = 作废代数 + 清槽,顺序不能反;4) 拿不到活动摘要时按 idle 处理但配墙钟
极限双保险。

### 4.2 busy 时的 slash 命令(14757–14792)

`_is_session_running(_quick_key)`(run.py:5848)为真进入 busy 分支。顺序:
1. `/status`、`/context` **预门**直接答(14769-14772)——用户任何时候都能看状态;
2. `_check_slash_access` 门禁(14780-14783)——镜像冷路径,防"趁 busy 绕过权限"(注释
   14774-14779);
3. 其余已识别命令统一进 `_dispatch_busy_slash_command`:

gateway/run.py:14785-14792 @ 863e313
```python
            # Any recognized slash command: dispatch according to its
            # declared busy_policy (dispatch / interrupt_then_dispatch /
            # reject). Unrecognized commands and plain text fall through
            # to the interrupt/queue logic below.
            if _cmd_def_inner:
                return await self._dispatch_busy_slash_command(
                    event, _cmd_def_inner, _quick_key, source,
                )
```

**调用关系**:`gateway/run.py:14098` `_dispatch_busy_slash_command`(本段紧前):解析顺序
busy_handler 专用变体(start/stop/new/queue/steer/egress/goal)→ `busy_policy=="dispatch"`
的正常 handler 白名单 → 兜底拒绝文案。其 docstring(14108-14114)点名 #5057、#6252、#10370:
不拒绝而放去 interrupt 的话,/model 等命令会"打断 agent 且被安全网静默丢弃,产生零字符响应"。
策略声明在 `hermes_cli/commands.py` 的 `CommandDef.busy_policy/busy_handler` 上——**消灭了
per-command if 链**(这正是与旧文档冲突处,见 §10)。

### 4.3 不打断的降级路径(14794–14918)

按序七种降级,全部 `return None`(排队/吸收):
1. **照片跟发**(14794-14799):Telegram 相册多 update 近同时到达,photo-only 跟发不打断,
   `merge_pending_message_event(adapter._pending_messages, ...)` 交适配器批处理吸收
   (`gateway/platforms/base.py:2438`);
2. **Telegram 3 秒宽限**(14801-14829):文本消息在 run 开始 `HERMES_TELEGRAM_FOLLOWUP_GRACE_SECONDS`
   (默认 3.0s)内到达 → 排队合并(用户连发两条当一条);
3. **sentinel 期**(14831-14850):agent 还在异步 setup,真身未注册。`/stop` 强清 sentinel 解锁
   ("⚡ Force-stopped."),其他消息合并排队等 agent 起来后消费;
4. **draining**(14851-14858):按 `_queue_during_drain_enabled()` 决定排队或拒绝,返回带
   `_status_action_gerund()`(restarting/shutting down…)的提示;
5. **queue 模式**(14859-14862):`_busy_input_mode == "queue"` 时 `_queue_or_replace_pending_event`
   (run.py:8666);
6. **steer 模式**(14863-14886):纯文本注入运行中 agent 的 `agent.steer(text)`;空文本/无
   steer 方法/steer 拒绝则回退 queue;
7. **两大保护性降级**:

gateway/run.py:14887-14902 @ 863e313
```python
            # #30170 — Subagent protection (PRIORITY path). Same rationale
            # as ``_handle_active_session_busy_message``: an interrupt
            # cascades through ``_active_children`` and aborts in-flight
            # delegate_task work. Demote to queue semantics when the
            # parent is currently driving subagents so a conversational
            # follow-up doesn't destroy minutes of subagent progress.
            # /stop reaches its dedicated handler above, so the operator
            # still has a clean escape hatch.
            if self._agent_has_active_subagents(running_agent):
                logger.info(
                    "PRIORITY interrupt demoted to queue for session %s "
                    "because the running agent has active subagents (#30170)",
                    _quick_key,
                )
                self._queue_or_replace_pending_event(_quick_key, event)
                return None
```

压缩保护同构(14903-14918,#56391):压缩本身抗打断(#23975),但此处 interrupt 会**对
旋转前的父会话开新回合**,压缩完成后把 session_id 旋走,分叉出孤儿兄弟会话——所以排队等
压缩+旋转落地。`_agent_has_active_subagents` 在 run.py:8558(读 `_active_children` 且拒绝
MagicMock 假真值),`_session_has_compression_in_flight` 在 run.py:8595。

### 4.4 redirect → interrupt(14919–14957)

纯文本且运行时声明 `_supports_active_turn_redirect` 时先试 `running_agent.redirect(text)`
(重定向当前回合、保留已显示上下文);失败或不支持才走成熟的 interrupt 路径。interrupt 前:
语音先转写并回显(`_transcribe_and_echo_pending_voice`,run.py:21786),无文本纯媒体则造占位
(`_build_media_placeholder`,run.py:2721),然后 `running_agent.interrupt(_interrupt_text)`。
末尾注释(14954-14956)交代一处已修的泄漏:`self._pending_messages` 曾只写不读、无限增长,
真正的打断消息走 `adapter._pending_messages` 由 `_run_agent` 消费,故删除。

**busy 分流整体重实现要点**:
1. busy 策略做成命令元数据(busy_policy/busy_handler)而非 if 链,新命令声明即生效;
2. "打断降级为排队"的判据清单要显式:照片跟发、启动宽限、sentinel、drain、子代理在跑、
   压缩在飞——每条都是真实事故换来的;
3. `/stop` 在每条降级路径上都必须保有逃生门(sentinel 强清、busy_handler 专用变体);
4. redirect(保上下文)> steer(注入)> interrupt(重启回合)三级能力协商,按运行时声明降级;
5. 打断携带的文本要预处理(语音转写/媒体占位),否则 agent 收到空打断。

---

## 5. 阶段 11–13:冷路径命令解析与内建命令(14959–15400)

### 5.1 解析与别名预展开(14959–14993)

`event.get_command()` 取词 → `resolve_command` 归一别名到 canonical(14962-14971;注释:
"dispatch and hook names don't depend on the exact alias the user typed")。**alias 型
quick command 预展开**(14977-14993):typed 命令不在注册表时查 `config.quick_commands`,
alias 型把 `event.text` 改写成 `/<target> <args>` 再重解析——这样
`/model openai/gpt-5.5 --provider openrouter` 这类 alias 目标能进内建 `/model` handler
(注释 14973-14976:"Preserve built-in precedence; aliases only need early handling when
the typed command is not already known")。

### 5.2 slash 访问控制 + `command:<canonical>` 钩子(14995–15059)

`_check_slash_access(source, canonical)`(run.py:18438)只在操作员配置了 `allow_admin_from`
时生效;未配置=全员全命令(向后兼容),配置后非管理员只能跑 `user_allowed_commands` + 永allow
底座(/help、/whoami);纯聊天不受影响(14995-15000 注释)。

钩子 `command:<canonical>` 经 `self.hooks.emit_collect` 收集返回值(15023-15026),
dict 里 `decision` 四值:`allow`/空=继续,`deny`=挡下(可带 message),`handled`=插件已处理
(可带 message),`rewrite`=改写成 `/{command_name} {raw_args}` 重解析后 break(15048-15059)。
注释(15006-15012)说明这替代了旧的 fire-and-forget `emit()`:返回值开始被尊重,但不返回值的
telemetry 钩子行为不变。

**重实现要点**:1) 别名在"访问控制之前"归一,门禁必须查 canonical 而非 typed 名;2) 命令钩子
的四值决策协议(allow/deny/handled/rewrite)覆盖了拦截、代理、改写三种插件需求;3) rewrite 后
必须重跑 resolve,让后续 if 链看到新 canonical。

### 5.3 内建命令 if-链(15061–15400)

约 50 个 `if canonical == "...": return await self._handle_*_command(event)` 直分发(handler
多在 `gateway/slash_commands.py` mixin)。值得单独交代的形态:

**(a)破坏性命令包确认**:`/new`(15061-15075)与 `/undo`(15245-15266)不直接执行,包进
`_maybe_confirm_destructive_slash`(run.py:20483)——闭包封装真正动作,由 slash-confirm 机制
(§3.4)决定是否弹确认。`/new` 前还查 Telegram topic 大厅(15062-15063:大厅里 `/new` 提示去
开新 topic 而非重置)。`/undo` 解析数字参数生成不同确认文案。

**(b)fall-through 型(改写 event.text 后不 return,落到 agent 回合)**:共 5.5 个:
- `/learn`(15128-15154):`build_learn_prompt`(agent/learn_prompt.py)把回合改写成"按标准
  自学技能"的提示,先发 ack,再落洞——注释:"Mirrors the /blueprint fall-through so role
  alternation is preserved. No engine, works on any backend";
- `/init`(15156-15182):`build_init_prompt_for_cwd`(hermes_cli/init_command.py)同构,
  按提示词里是否含 "UPDATE the existing AGENTS.md" 决定 ack 文案;
- `/blueprint`(15214-15240):`_handle_blueprint_command` 返回物挂 `agent_seed` 才落洞
  (seed 作为普通 user 回合进 agent,agent 逐槽位问用户再调 cronjob 工具),否则直接回文本;
- `/queue`(15328-15335)与 `/steer`(15337-15350):无 agent 在跑时的 `/steer` 没有注入
  目标,剥掉前缀当普通消息发——"(no agent is running; sending as a normal message)";
- `/moa`(15360-15394)见 §6。

**(c)`/start`**(15083-15085):Telegram 的平台 ping,直接 `return ""` 不当命令。

**(d)`/egress`**(15099-15102):同步调 `hermes_cli/proxy_cli.format_status_text`,唯一
不走 handler 方法的内建命令。

**设计理由/取舍**:if-链 vs 表驱动——冷路径保留 if 链因为许多命令有前置逻辑(确认包装、
fall-through 改写、topic 检查),表驱动只在 busy 路径(`_dispatch_busy_slash_command`)做了,
那里恰好都是"无前置逻辑的直分发"。fall-through 型的共同设计:**把命令变成一条用户回合**而非
旁路引擎,保住 role 交替(user/assistant 严格轮替是许多 provider 的硬约束),且天然适配任何
后端模型。

**重实现要点**:1) 破坏性命令统一走确认包装器,闭包延迟执行;2) "提示词改写 + 落洞"是给
命令加 LLM 能力的最省路径(无独立引擎、保 role 交替);3) ack 先行发送(用户立即有反馈,
agent 第一问可能在几秒后);4) fall-through 分支绝不能 return,注释要写明(仓库在每处都写了)。

---

## 6. `/moa` one-shot 与还原(15360–15394 + 15745–15776)

**问题**:MoA(Mixture of Agents,多模型扇出聚合的虚拟 provider)想提供"就这一条消息用 MoA"
的糖,不改变会话模型;难点是**还原必须在任何退出路径上发生**,否则一次异常就让会话永久卡在
MoA(每条后续消息都静默扇出多模型,费用放大)。

**实现——设置侧**(15380-15394):把先前的 `model_override` 存到 event 上
(`event._moa_restore_override`),再把会话 override 换成 MoA 虚拟 provider,驱逐缓存 agent,
打 `_moa_disable_after_turn` 标记:

gateway/run.py:15380-15392 @ 863e313
```python
            try:
                event.text = moa_payload
                _moa_state = self._session_state(_quick_key)
                event._moa_restore_override = _moa_state.conversation.model_override
                _moa_state.conversation.model_override = {
                    "provider": "moa",
                    "model": preset,
                    "base_url": "moa://local",
                    "api_key": "moa-virtual-provider",
                    "api_mode": "chat_completions",
                }
                self._evict_cached_agent(_quick_key)
                event._moa_disable_after_turn = True
```

**实现——还原侧**在 `finally`(15721-15731,见 §8)调用:

gateway/run.py:15745-15761 @ 863e313(节选)
```python
    def _restore_moa_one_shot(self, event: "MessageEvent", quick_key: str) -> None:
        """Revert a ``/moa <prompt>`` one-shot model override after its turn.

        Called from the ``finally`` of the message-handling path so the revert
        fires whether the turn succeeded, raised, or was interrupted. A no-op
        unless ``event._moa_disable_after_turn`` is set. ``_moa_restore_override``
        carries the prior per-session override (``None`` means the user had no
        override, so the MoA override is cleared outright).
        """
        if not getattr(event, "_moa_disable_after_turn", False):
            return
        try:
            _restore = getattr(event, "_moa_restore_override", None)
            self._session_state(quick_key).conversation.model_override = _restore
            self._evict_cached_agent(quick_key)
        except Exception:
            pass
```

**姊妹机制** `_restore_pending_one_turn_model_override`(15763-15776):`/model <name> --once`
的还原。快照不放 event 而放 `SessionState.conversation.one_turn_restore`
(gateway/session_state.py:97;由 slash_commands.py 的 /model handler 写入,
slash_commands.py:1677 "--once — switch for the next turn only"),finally 里取出置空后经
`_restore_session_model_override`(run.py:22782)还原。

**取舍对比**:MoA 快照挂在**event 对象**上(turn 私有,event 出作用域即丢——这正是注释
15722-15729 强调必须放 finally 的原因);--once 快照挂在**会话状态**上(命令回合与生效回合是
两个回合,必须跨 event 存活)。两者选择不同载体是由"设置与生效是否同回合"决定的。

**重实现要点**:1) one-shot 覆盖的还原必须放 finally,成功/异常/打断三路全覆盖;2) 快照载体
按生命周期选:同回合挂 event,跨回合挂会话态;3) 还原后必须驱逐缓存 agent(agent 按模型签名
缓存,不驱逐就继续用 MoA agent);4) `None` 快照语义 = "原本无覆盖 → 清除",不能跳过。

---

## 7. 阶段 14–19:quick/plugin/skill 命令与两道闸门(15402–15663)

### 7.1 draining 冷路径(15402-15403)

busy 分支之外的第二个 drain 检查:非命令消息在 drain 中直接拒
(`"⏳ Gateway is {gerund} and is not accepting new work right now."`)。位置在内建命令 if-链
**之后**——/status、/restart 等命令在 drain 期间仍可用。

### 7.2 用户 quick commands(15405–15465,#44727)

**问题(#44727)**:quick command 不在命令注册表,15001 行的早门(只对 registry-known 生效)
管不到它;`type:exec` 的 quick command 在 gateway 进程里跑 shell,非管理员本可借此绕过权限。

**实现**:命中 quick_commands 后**对 raw typed 名补一次 `_check_slash_access`**(15421-15423);
exec 型用净化过的环境跑(防凭据泄漏),输出再过一次脱敏:

gateway/run.py:15428-15446 @ 863e313(节选)
```python
                        try:
                            # Sanitize env to prevent credential leakage —
                            # quick commands run in the gateway process which
                            # has all API keys in os.environ.
                            from tools.environments.local import build_subprocess_env
                            sanitized_env = build_subprocess_env()
                            proc = await asyncio.create_subprocess_shell(
                                exec_cmd,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                                env=sanitized_env,
                            )
                            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                            output = (stdout or stderr).decode().strip()
                            # Redact any remaining sensitive patterns in output
                            if output:
                                from agent.redact import redact_sensitive_text
                                output = redact_sensitive_text(output)
                            return output if output else "Command returned no output."
```

alias 型在此处第二次出现(15453-15463)——与 14977 的预展开互补:预展开只处理"typed 名不是
内建"的情况,此处兜住"alias 目标本身还要落进后续 skill/plugin 分发"的情况。

**重实现要点**:1) 任何"配置文件里长出来的命令"都要与注册表命令同权限模型,门禁按 typed 名
补查;2) gateway 进程执 shell 三件套:净化 env、30s 超时、输出脱敏;3) alias 需要在两个位置
展开(内建优先级前 / 后),注意不要造成循环展开。

### 7.3 插件命令(15467–15482)

`hermes_cli.plugins.get_plugin_command_handler(command.replace("_", "-"))`——下划线归一到连
字符,适配 Telegram 自动补全的下划线形(注释指向 `hermes_cli/commands.py:_build_telegram_menu`)。
handler 可同步可异步(`asyncio.iscoroutine` 判定)。

### 7.4 skill bundle / stacked skills / 单 skill / unknown(15484–15629)

顺序:bundle 优先(`/bundle` 一次装多技能,`agent/skill_bundles.py` 的
`resolve_bundle_command_key`/`build_bundle_invocation_message`,15493-15519)→ 单 skill
(`agent/skill_commands.py` 的 `resolve_skill_command_key`,处理 Telegram 下划线回环)→
栈式(`/skill-a /skill-b do XYZ` 最多 5 个,`split_stacked_skill_commands` +
`build_stacked_skill_invocation_message`,注释"Inspired by Claude Code v2.1.199")。

**per-platform disabled 双重校验(#58888)**:`get_skill_commands()` 扫描时只应用全局禁用表,
gateway 单进程服务多平台,env 推平台不可信,故 bundle 路径显式传 `platform=`(15500-15508),
单 skill 与 stacked 的每个成员都在此处再查 `get_disabled_skill_names(platform=...)`
(15537-15545、15561-15581)——否则"给平台 A 禁用的技能"能借栈式装载混进来。

**unknown-command 兜底**(15601-15627):不是内建/插件/skill/已知未装技能 → 回
"Unknown command `/{command}`" 而非静默把 `/xyz` 当自由文本喂 LLM(注释:防"model inventing
a delegate_task call"式静默失败)。先经 `_check_unavailable_skill`(run.py:3059)区分
"已知但禁用/未安装"给出可操作指引。

**重实现要点**:1) 命令分发优先级要固定成文:内建 > quick > 插件 > bundle > skill > unknown;
2) skill 装载=改写 event.text 落洞进 agent(与 /learn 同型);3) 进程级缓存(skill 扫描)与
per-platform 配置之间的缝要在分发点补检,且栈式的每个成员都要查;4) 未知命令必须显式报错,
静默转发给 LLM 是事故源。

### 7.5 Telegram topic 大厅(15635–15642)

topic 模式开启后,主 DM(General topic)变"大厅":非命令消息只回一条提醒(带防抖
`_should_send_telegram_lobby_reminder`,run.py:6758——"forgets 十连发不给十条")或静默。
判定 `_is_telegram_topic_root_lobby`(run.py:6736,General topic id 兼容 `""` 与 `"1"` 两种
客户端行为,见 6731-6734 注释)。用 `asyncio.to_thread` 包 SessionDB 同步读。

### 7.6 外部 drain 新回合闸门(15644–15663)

**问题**:NAS(编排层)要安全地对 gateway 做维护动作,需要"in-flight 只减不增"的保证,
消除 TOCTOU(检查时 0、动作时又来新回合)。

gateway/run.py:15654-15663 @ 863e313
```python
        if self._external_drain_active and not is_internal:
            logger.info(
                "Refusing new turn for session %s — external drain active.",
                _quick_key,
            )
            return (
                "⏳ This agent is draining for a maintenance action and isn't "
                "accepting new turns right now. It'll be back in a moment — "
                "please resend shortly."
            )
```

注释(15644-15653)交代协议:`.drain_request.json` 由 `_drain_control_watcher`
(gateway/drain_control.py 配套)观察置位;"D4a: stop accepting new turns FIRST, then NAS
polls until active_agents==0";internal 事件豁免;marker 移除即可逆。

---

## 8. 阶段 20–21:抢占会话槽与 try/finally(15665–15743)

### 8.1 claim before any await(15665–15688)

**问题**:从这里到 `_run_agent` 注册真 AIAgent 之间有大量 await(钩子、视觉增强、STT、会话
卫生压缩);没有先占位,第二条消息会穿过 "already running" 检查,给同一会话起重复 agent,
**写坏 transcript**。

gateway/run.py:15672-15688 @ 863e313
```python
        _active_session_lease, _limit_message = self._claim_active_session_slot(
            _quick_key,
            source,
        )
        if _limit_message is not None:
            logger.info(
                "Rejecting new active session %s: max_concurrent_sessions reached",
                _quick_key,
            )
            return _limit_message
        _claim_state = self._session_state(_quick_key)
        if _active_session_lease is not None:
            _claim_state.turn.lease = _active_session_lease
        _claim_state.turn.agent = _AGENT_PENDING_SENTINEL
        _claim_state.turn.started_ts = time.time()
        self._persist_active_agents()
        _run_generation = self._begin_session_run_generation(_quick_key)
```

四步:1) 跨进程槽位租约 `_claim_active_session_slot`(run.py:8528,经
`hermes_cli/active_sessions.try_acquire_active_session` 落盘,附并发上限
`max_concurrent_sessions` 拒绝文案);2) 本进程 sentinel 占位
(`_AGENT_PENDING_SENTINEL = object()`,run.py:2465——身份哨兵,busy 分支 14833 用 `is`
识别);3) `_persist_active_agents`(run.py:7805)持久化 in-flight 计数供仪表盘;4) 领取
run generation(run.py:23014:"Monotonic by design (#28686): incremented here, NEVER reset"
——/stop、/new 通过再 +1 作废旧回合,迟到结果可识别丢弃)。

### 8.2 try:进 agent + goal 续推(15690–15720)

主调用 `await self._handle_message_with_agent(event, source, _quick_key, _run_generation)`
(15691;函数在 16276,下一段)。返回后做 **goal continuation**:取最终文本(dict 的
`final_response` 或 str),非空才请 judge 评估 standing `/goal`(标记完成/预算暂停/把续推
提示塞回 adapter FIFO 驱动下一回合);空响应(被打断/出错)跳过——"the judge would almost
always say 'continue' and we'd loop on error"(15704-15707 注释)。judge 全程 try/except:
"a broken judge never breaks normal message handling"(15696-15697)。会话条目经
`self.async_session_store.get_or_create_session(source)`(15709)取。
**调用关系**:`_post_turn_goal_continuation`(run.py:18885)。

### 8.3 finally:四连释放(15721–15743)

gateway/run.py:15721-15743 @ 863e313
```python
        finally:
            # MoA one-shot restore must run on EVERY exit path, not just
            # success. The restore data lives on the per-turn event object
            # (_moa_restore_override), which is discarded once the event goes
            # out of scope — so if _handle_message_with_agent raises, a restore
            # in the try block would be skipped and the MoA override would leak
            # permanently (every later message silently fans out through MoA).
            # Putting it in finally guarantees the revert on success, exception,
            # and interrupt alike.
            self._restore_moa_one_shot(event, _quick_key)
            self._restore_pending_one_turn_model_override(_quick_key)
            # Unconditional release covers every exit path. _release_running_agent_state
            # is idempotent (pop-on-absent is harmless) and, called without a
            # run_generation guard, always clears the slot regardless of which
            # generation it holds. This evicts the zombie left when session_reset
            # bumps the generation (N -> N+1) mid-flight: gen-N's guarded release
            # inside _run_agent returns False, and the old sentinel-only check here
            # missed the leftover real agent — locking the session out forever (#28686).
            self._release_running_agent_state(_quick_key)
            # Turn lease (#64934): release THIS turn's lease token — keyed by
            # (routing key, run generation) so this unwind can only ever free
            # the lease its own turn acquired, never a newer turn's.
            self._release_turn_lease(_quick_key, _run_generation)
```

两级释放的分工(#28686 vs #64934):
- `_release_running_agent_state`(run.py:22802)**无代数守卫**调用——顶层 finally 是"本回合
  链路的最外层",无条件清槽正是修 #28686 的手段(mid-flight 被 /new 抬代数后,`_run_agent`
  内部带守卫的释放返回 False,旧代码只查 sentinel 漏掉真 agent → 会话永锁);它统一收拢了
  曾经散落漂移的 `del self._running_agents[key]`(见其 docstring 22808-22815),会话级持久
  状态(model override、voice mode、pending approvals)明确不清;
- `_release_turn_lease`(run.py:22859)**带代数**调用——lease token 按 (key, generation)
  存,旧回合 unwind 只可能释放自己那代的令牌,registry 的身份检查再拒一层(#64934);另有
  `_rebind_turn_lease`(run.py:22888)处理压缩中途旋转 session_id 时令牌跟随(#64934
  rotation-alias window)。

**重实现要点**:
1. "先占位再 await"是 gateway 并发模型的基石;占位物用身份哨兵,busy 分支必须能区分
   sentinel 与真 agent(/stop 对 sentinel 是强清而非 interrupt);
2. run generation 单调递增、永不回卷,作废=+1;所有迟到写回都带代数校验;
3. 顶层 finally 的释放必须**无守卫**(它是最后防线),内层释放必须**带守卫**(防旧清新);
4. 跨进程租约(文件)与进程内槽位(内存)双层,并发上限在租约层实施;
5. one-shot 覆盖还原放 finally 首位(先还原状态再释放槽,后续排队消息看到的才是干净会话)。

---

## 9. 入站文本预处理:`_prepare_inbound_message_text`(15778–16184)

**问题**:正常入站与 busy 排队后重放的 follow-up 曾走两条预处理路径,行为漂移(发言人前缀、
图片增强、STT、文档注、回复上下文、@ 引用在两条路上不一致)。本函数把全部预处理收拢成单管线,
docstring(15786-15798)明示:"Keep the normal inbound path and the queued follow-up path on
the same preprocessing pipeline"。副作用契约:模型支持原生视觉且带图时,把图片路径缓存到
会话态(`persistent.native_image_paths`),由调用者在 `run_conversation` 处消费成多模态回合;
列表为空则说明已走文本化路径(图片描述已并入文本)。

处理顺序(顺序本身是设计——后 prepend 的注在最上面):

### 9.1 STT 预备文本与缓冲重置(15799–15814)

`event._gateway_pending_stt_text` 存在(打断路径已转写过)则用它,避免二次转写;入口先
`_consume_pending_native_image_paths(session_key)` 清本会话残留缓冲(15814,注释:"Reset
only this session's per-call buffer; other sessions may be concurrently preparing")——
session_key 优先用调用者传入的,保证"写键=消费键"(15808-15811 注释)。

### 9.2 共享会话发言人前缀(15816–15840,#17916)

多人共享会话(`is_shared_multi_user_session`,gateway/session.py:1017)给消息加
`[发言人] ` 前缀。两个安全细节:

gateway/run.py:15821-15840 @ 863e313(节选)
```python
        if _is_shared_multi_user and source.user_name:
            # source.user_name is the platform display name — attacker-
            # influenceable on any platform that lets participants set their
            # own name. Neutralize embedded newlines/control chars before
            # interpolating it into every message in the shared session, or
            # a hostile name can masquerade as a fake markdown section
            # (mirrors the same field's treatment in
            # build_session_context_prompt via _format_untrusted_prompt_value).
            _safe_user_name = neutralize_untrusted_inline_text(source.user_name)
            # On Slack, expose the current author's verifiable user ID next to
            # the display name (#17916): "mention me again" requests need a
            # trusted `<@U...>` target for the CURRENT speaker — display names
            # are ambiguous and historical mentions may point at someone else.
            # The user_id comes from the Slack event envelope (not
            # user-editable text), so it does not need neutralization.
            if source.platform == Platform.SLACK and source.user_id:
                _safe_user_name = (
                    f"{_safe_user_name} | Slack user <@{source.user_id}>"
                )
            message_text = f"[{_safe_user_name}] {message_text}"
```

`neutralize_untrusted_inline_text` 在 gateway/session.py:457(去换行/控制符,防显示名伪装成
markdown 段落做提示注入)。#17916:Slack 上附加信封来源的 `<@U...>`,让"再@我一次"有可信
目标——显示名歧义且历史 mention 可能指别人。

### 9.3 频道回填上下文(15843–15846)

`event.channel_context`(历史回填块,即任务描述所称"观察上下文")prepend 成
`{channel_context}\n\n[New message]\n{message_text}`;刻意放在发言人前缀**之后**,前缀只属于
触发消息、不套在回填块上(15843-15845 注释)。

### 9.4 媒体分类与四路处理(15848–16043)

逐附件分类(15853-15872):`_event_media_is_image(event, i)`(run.py:2679)按**该附件自身
MIME** 判图,仅 MIME 未知时才信消息级 PHOTO 类型——注释(15858-15862):否则与图同发的文档
被误路由成图,provider 400;`MessageType.AUDIO`(音频文件附件,永不 STT)与
`MessageType.VOICE`(语音消息,总是 STT)严格分流(15865-15866 注释);视频入 `video_paths`。

**图片:native vs text 路由**(15874-15924):`_decide_image_input_mode`(run.py:21424,
依据 agent/image_routing.py)决定;决策含阻塞网络 IO(models.dev 拉取、Ollama `/api/show`
探测),用 `asyncio.to_thread` 下放,注释(15877-15882):否则"单张图路由会卡住整个 gateway
事件循环(所有会话)"。native → 写 `persistent.native_image_paths` 延迟到 run_conversation
挂载;text → 先解析本会话真实运行时(`_resolve_session_agent_runtime`,run.py:6933)并以
`scoped_runtime_main`(agent/auxiliary_client.py)绑定,再 `_enrich_message_with_vision`
(run.py:21497)预跑 vision_analyze 把描述并入文本——绑定注释(15901-15904):增强发生在
AIAgent.run_conversation 之前,不能依赖进程级全局镜像。

**语音 STT + 回显**(15926-15958):`_enrich_message_with_transcription`(run.py:21566)
返回 (新文本, 成功转写列表);配置开启时把每条转写 `🎙️ "..."` 回显给用户
(`_should_echo_stt_transcripts`,run.py:19267)。15950-15958 的注释是一条完整事故复盘:
转写失败时旧代码直接 `adapter.send` 一条硬编码英文提示,绕过 LLM 产生**双回复**——预制英文
片段被 TTS 用错误语言念出 + LLM 的本地化正确回复;修法是增强步骤只在提示词里留中性标记,
让 LLM 产出单条用户语言回复,硬编码发送删除。

**音频文件/视频占位注**(15960-15996):不内联内容,注入
`[The user sent an audio file attachment: '<名>'. It is saved at: <路径>. ... transcribe or
process it yourself ... instead of asking the user to describe it.]`;路径经
`to_agent_visible_cache_path`(tools/credential_files.py)翻译成容器内可见路径(Docker 后端
下 cache 目录自动挂载到 `/root/.hermes/cache/*`,16037-16039 注释);显示名做
`re.sub(r'[^\w.\- ]', '_')` 消毒,且从 `<ts>_<id>_<原名>` 的缓存文件名剥出原名(split("_",2))。

**文档兜底**(15998-16043):对**未被前三路认领**的每个附件发"路径指向注"
(`_build_document_context_note`,run.py:2743);MIME 空/octet-stream 时按扩展名表
(`_TEXT_EXTENSIONS`)与 `mimetypes.guess_type` 补猜。注释(16004-16010)点明动机:混在
PHOTO/VOICE 消息里的文档(消息级类型≠DOCUMENT)也要以可读缓存文件形式到达 agent,而不是
因消息级类型不对被静默丢弃。

### 9.5 Discord message_id 注入(16045–16062)

**问题**:reply/react/pin 工具需要触发消息 id,但 id 每回合都变,烤进
`build_session_context_prompt()` 会打爆 agent 缓存签名——每条消息重建 AIAgent、摧毁
prompt cache。**实现**:静态系统提示里放"IDs block"指路,易变 id 走每回合用户内容:
`[Triggering message id: `...` — use as `message_id` for reply/react/pin via the discord
tools.]`(16058-16061);仅 Discord 工具已加载时注入(`_disc_tools_loaded`,
gateway/session.py)。**要点**:易变数据永远放 per-turn 内容,不放缓存前缀——这是全仓
prompt-cache 纪律在预处理层的体现。

### 9.6 回复引用指针(16064–16078)

gateway/run.py:16064-16078 @ 863e313(节选)
```python
        if getattr(event, "reply_to_text", None) and event.reply_to_message_id:
            # Always inject the reply-to pointer — even when the quoted text
            # already appears in history. The prefix isn't deduplication, it's
            # disambiguation: it tells the agent *which* prior message the user
            # is referencing. History can contain the same or similar text
            # multiple times, and without an explicit pointer the agent has to
            # guess (or answer for both subjects). Token overhead is minimal.
            reply_snippet = event.reply_to_text[:500]
            if getattr(event, "reply_to_is_own_message", False):
                message_text = (
                    f'[Replying to your previous message: "{reply_snippet}"]\n\n'
                    f"{message_text}"
                )
            else:
                message_text = f'[Replying to: "{reply_snippet}"]\n\n{message_text}'
```

设计立场写死在注释里:引用指针是**消歧义**不是去重,即使史里已有同文也注入(500 字截断,
token 开销可忽略);区分"回复 bot 自己的消息"两种措辞。

### 9.7 `@` 上下文引用展开(16080–16182)

`@文件/目录` 引用经 `preprocess_context_references_async`(agent/context_references.py)展开
进上下文;预算依赖模型上下文长度,解析链:config 的 `model.context_length`(仅当会话实际
模型=配置模型且路由身份未漂移——`should_clear_context_pin_async`,hermes_cli/route_identity.py)
→ per-custom-provider 限额(`get_custom_provider_context_length`)→
`get_model_context_length_async`(agent/model_metadata.py)。16105-16111 的注释又是一条
事故复盘:此处曾抄 HermesCLI 用 `self._model/self._base_url`,GatewayRunner 根本没有这些属性,
AttributeError 被静默吞掉,**该功能从未运行过**——修法是与卫生压缩块(~11080)同式改用
`_resolve_session_agent_runtime`。`_ctx_result.blocked` 时把 warnings 发给用户并 `return None`
(拒绝注入,不进 agent,16170-16177);展开成功则替换文本。

**`_prepare_inbound_message_text` 重实现要点**:
1. 所有入站变换收拢单函数,正常路径与排队重放共用,防两线漂移;
2. prepend 链的顺序=最终阅读顺序的倒序,发言人前缀只贴触发消息;
3. 一切用户可控字符串(显示名、文件名)入提示词前消毒;信封来源的 id 可信、可原样用;
4. 附件按**每附件 MIME** 分桶,消息级类型只作 MIME 缺失时的回退;未认领附件必须有兜底注;
5. 易变元数据(message_id、时间戳)走 per-turn 内容,严禁进缓存系统提示;
6. 预处理里的网络 IO 一律 to_thread,预处理用的模型运行时要显式解析绑定,不碰进程全局。

---

## 10. 其余小件(16186–16274)

### 10.1 `_prepare_profile_scoped_inbound_message_text`(16186–16208)

多路复用(`config.multiplex_profiles`)时把 §9 包进
`_profile_runtime_scope(self._resolve_profile_home_for_source(source))`(run.py:1938 /
24209)——预处理内的 `load_config`、skill 查找等都要落在**路由到的 profile 的 HOME** 下;
非复用直通。要点:profile 作用域要包住整个预处理而不是各取各的,否则半个函数读 A 配置半个读 B。

### 10.2 `_prepare_clarify_reply_text`(16210–16222)

clarify 拦截(§3.3)的取文本器:无语音 → `event.text.strip()`;有语音 →
`_transcribe_pending_audio_event_once`(run.py:21715,"once"=结果缓存回 event,后续路径不
重转写)取成功转写,`"\n\n"` 连接。

### 10.3 `_consume_pending_native_image_paths`(16224–16230)

gateway/run.py:16224-16230 @ 863e313
```python
    def _consume_pending_native_image_paths(self, session_key: str) -> List[str]:
        state = self._peek_session_state(session_key)
        if state is None or not state.persistent.native_image_paths:
            return []
        paths = list(state.persistent.native_image_paths)
        state.persistent.native_image_paths = []
        return paths
```

"取即清"的一次性缓冲:§9.4 native 路由写入,`run_conversation` 调用点消费构造多模态回合;
按 session_key 隔离,防并发会话互踩。重实现要点:跨函数传递 per-turn 附件用会话态一次性
缓冲 + 消费即清,双端键必须同源(15808-15811 的"写键=消费键"注释)。

### 10.4 `_cache_session_source` / `_get_cached_session_source`(16232–16251 / 16262–16274)

活跃会话 source 的 LRU 缓存(`OrderedDict` + `move_to_end` + 上限 `_session_sources_max`
默认 512 逐出最旧):存的是 `dataclasses.replace(source)` 快照(防调用方后续改动污染缓存)。
用途:后台流程(通知、goal 续推、定时任务)需要"这个会话最近从哪个平台/哪个 chat 来"以便
回投递,而那时手头只有 session_key。读侧命中也 `move_to_end` 刷新热度。

### 10.5 `async_session_store` property(16253–16260)

gateway/run.py:16253-16260 @ 863e313
```python
    @property
    def async_session_store(self) -> AsyncSessionStore:
        """Return the single async facade for this runner's SessionStore."""
        facade = getattr(self, "_async_session_store", None)
        if facade is None or facade._store is not self.session_store:
            facade = AsyncSessionStore(self.session_store)
            self._async_session_store = facade
        return facade
```

懒建 + **身份校验**的单例门面:`facade._store is not self.session_store` 时重建——测试或
profile 切换替换底层 store 后,旧门面绝不能继续代理旧 store。`AsyncSessionStore` 在
gateway/session.py:1189(把同步 SQLite store 的方法 to_thread 化,供事件循环安全调用)。
重实现要点:同步存储 + 异步门面的组合里,门面缓存必须校验底层身份,否则热替换后静默错库。

---

## 11. `_handle_message` 与时间戳注入的关系(任务描述修正的展开)

时间戳机制分三件,均不在本段函数内但由本段管线触达:
1. **开关**:模块级 `_message_timestamps_enabled`(run.py:1296)读
   `gateway.message_timestamps.enabled`,**默认 OFF**(1299-1302 注释:给所有 gateway 用户的
   每条消息加 `[Tue 2026-04-28 13:40:53 CEST]` 前缀改变模型所见,必须显式开启);
2. **当前回合**:`_handle_message_with_agent` 在 `_prepare_profile_scoped_inbound_message_text`
   返回后立即处理(run.py:17477-17511):**无论开关**都先
   `strip_leading_message_timestamps` 把前缀剥出、时间落 metadata(存储永远干净、时间不丢),
   仅"模型看到的渲染"受开关控制(`render_user_content_with_timestamp`);
3. **历史回放**:`_build_gateway_agent_history(..., inject_timestamps=...)`(run.py:1316,
   调用点 5103)在回放时按存储 metadata 每条渲染一次。
`gateway/message_timestamps.py` 提供 `coerce/format/render/strip` 四函数,文件头注释点明
核心不变量:"persisted message content should stay clean so replay does not accumulate
`[timestamp] [timestamp] ...` prefixes across turns"。
**重实现要点**:时间戳"存元数据、渲染时注入、入库前剥离"三分离,防复利前缀;开关只管渲染,
不管采集。

---

## 12. 文档-代码冲突候选(website/docs/developer-guide/gateway-internals.md)

按 CLAUDE.md 约定,以代码为准,列 5 处:

**▲C1 DM Pairing Flow 方向完全颠倒(重大)**。
gateway-internals.md:102-109 @ 863e313:
```text
### DM Pairing Flow

Admin: /pair
Gateway: "Pairing code: ABC123. Share with the user."
New user: ABC123
Gateway: "Paired! You're now authorized."
```
代码(run.py:14455-14500,§2):**陌生用户** DM bot → bot 把配对码发给**陌生用户** →
**owner 在 CLI** 跑 `hermes pairing approve <platform> <code>` 批准。且
`hermes_cli/commands.py` 中**不存在** `/pair` 网关命令(grep 全文件无该命令定义);也不存在
"新用户把码发回 bot 即通过"的路径(批准只走 CLI `approve_code`,pairing.py:665)。文档描述的
流程在代码里一步都对不上。

**▲C2 "Running-Agent Guard" 的 if-链与 `self._running_agents` 字典已不存在**。
gateway-internals.md:126-129 @ 863e313:
```python
if _quick_key in self._running_agents:
    if canonical == "model":
        return "⏳ Agent is running — wait for it to finish or /stop first."
```
代码:busy 判定是 `self._is_session_running(_quick_key)`(14757)读
`SessionState.turn.agent`(run.py:5848);per-command if 链已被 `CommandDef.busy_policy/
busy_handler` + 单一解析器 `_dispatch_busy_slash_command`(14098)取代(14758-14762 注释
明言 "no per-command if-chain here");`_running_agents` 字典本身已被 SessionState 结构化
替代(`_release_running_agent_state` docstring 22808-22815 称其为被替换的旧散点)。

**▲C3 Message Flow 步骤顺序与代码相反**。
gateway-internals.md:62-67 说 `_handle_message` 依次:resolve session key → check
authorization → slash dispatch → check running agent。代码顺序:鉴权(14443-14511)在
**session key 计算(14521)之前**;busy 检查(14757)在**冷路径 slash 分发(15061 起)之前**。
且文档只字未提代码里实际存在的前置关卡:ignored-channel(14364)、startup-restore 排队
(14383)、pre_gateway_dispatch 钩子(14399)、三类待答复拦截(14513-14694)、外部 drain
闸门(15654)、会话槽抢占(15672)。

**▲C4 "Everything else triggers running_agent.interrupt()" 过时**。
gateway-internals.md:88。代码里 interrupt 只是 busy 处理的**最后回退**:此前有照片吸收、
Telegram 宽限、queue/steer 模式、#30170 子代理降级、#56391 压缩降级、redirect 优先
(14794-14953,§4.3-4.4)。文档口径下会得出"任何跟发都会打断子代理任务"的错误结论。

**◇C5 会话键格式描述过简(方向对、细节丢)**。
gateway-internals.md:70-80 给出 `agent:main:{platform}:{chat_type}:{chat_id}`。实际
`build_session_key`(session.py:1058-1132)在此之外还有:多 profile namespace 替换
`agent:main`、Slack workspace `scope_id` 插段、群聊默认 **附加 per-user id**
(`group_sessions_per_user=True` 默认开)、thread_id 段、DM 无 chat_id 时的 participant 回退。
文档自己的示例 `agent:main:telegram:private:123456789` 中 `private` 亦与代码的 chat_type
取值 `dm`(session.py:1103 `if source.chat_type == "dm"`)不符。"Never construct session
keys manually" 的告诫与代码一致(run.py:6679 确实统一走 build_session_key/店内生成)。

---

## 13. 引用的 issue 清单(本段内注释点名)

| issue | 位置 | 一句话 |
|---|---|---|
| #51899 | 14366 | 忽略频道守卫必须先于配对/鉴权/会话 |
| #9337 | authz_mixin.py:806 | 配了 allowlist 就不该给陌生人发配对码 |
| #17916 | 15831 | Slack 共享会话给发言人附可信 `<@U...>` id |
| #30170 | 14887 | interrupt 级联杀子代理 → busy 降级为 queue |
| #56391 / #23975 | 14903-14906 | 压缩在飞时 interrupt 分叉孤儿会话 → 排队 |
| #28686 | 15738 / 23025 | 代数抬升后残留真 agent 永锁会话 → finally 无守卫清槽;代数单调不回卷 |
| #64934 | 15741 / 22859-22900 | turn lease 按 (key, generation) 键,旧 unwind 释放不了新租约;旋转跟随 |
| #44727 | 15420 | quick command 绕过 slash 门禁 → 按 typed 名补查 |
| #58888 | 15504 / 15561 | skill 进程级缓存 vs per-platform 禁用 → 分发点逐个再查 |
| #5057 #6252 #10370 | 14114 | busy 时命令被 interrupt+静默吞 → 声明式 busy 拒绝 |
| #18528 | 18562(定义处,调用在 slash_commands.py:1538) | /restart 重投递自激重启环 |

## 14. 本段调用关系速查(对方文件:行号)

- `gateway/session_context.py:315` reset_session_vars(入口防泄漏)
- `gateway/authz_mixin.py:130/371/386/785` _adapter_for_source / _pairing_store_for /
  _is_user_authorized / _get_unauthorized_dm_behavior
- `gateway/pairing.py:609/665/816/826` generate_code / approve_code / _is_rate_limited /
  _record_rate_limit(常量 51-56)
- `hermes_cli/commands.py` resolve_command / GATEWAY_KNOWN_COMMANDS / CommandDef.busy_policy
- `tools/clarify_gateway.py:179/316`、`tools/slash_confirm.py:71/84/99`、
  `tools/approval.py:2526`(三类待答复)
- `gateway/platforms/base.py:2438` merge_pending_message_event(排队合并)
- `gateway/session.py:457/1017/1058/1189/1725` neutralize_untrusted_inline_text /
  is_shared_multi_user_session / build_session_key / AsyncSessionStore / _generate_session_key
- `gateway/slash_commands.py`(命令 handler mixin;/restart 内 1538 调 _is_stale_restart_redelivery)
- 本文件内:5832/5841/5848(会话态)、6679(键)、6736(topic 大厅)、6933(运行时解析)、
  7586(scale-to-zero)、7691/8666(排队)、8528(租约)、8558/8595(两降级判据)、
  10229/10245(启动恢复队列)、14098(busy 分发)、18438(slash 门禁)、18885(goal 续推)、
  20483(破坏性确认)、21424/21497/21566(图/视/听增强)、21706/21715/21786(语音)、
  22782/22802/22859/22888(还原与释放)、23014/23029/23041(run generation)
- `tools/environments/local.py` build_subprocess_env、`agent/redact.py` redact_sensitive_text
  (quick exec)
- `agent/learn_prompt.py`、`hermes_cli/init_command.py`、`agent/skill_bundles.py`、
  `agent/skill_commands.py`、`agent/skill_utils.py`(fall-through 与 skill 分发)
- `agent/context_references.py`、`agent/model_metadata.py`、`hermes_cli/route_identity.py`
  (@ 引用展开)
- `gateway/message_timestamps.py`(时间戳;注入点在 17477-17511 与 1316,见 §11)
- `tools/credential_files.py` to_agent_visible_cache_path(容器路径翻译)
