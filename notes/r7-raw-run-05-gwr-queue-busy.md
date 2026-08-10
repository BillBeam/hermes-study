# R7 底稿 · gateway/run.py 第 5 段(7691–9184)—— GatewayRunner 排队机制与 busy 总入口

> 精读范围:`gateway/run.py:7691-9184 @ 863e313`(GatewayRunner 第 2 段)。
> 溯源约定:`路径:行号 @ 863e313` + 逐字代码块(≤25 行/处),行号已用 Read 逐一核实。
> 本段核心:/queue FIFO 三件套、goal continuation 识别、runtime status 持久化、外部 drain、
> 平台熔断、prefill/ephemeral prompt、per-channel model/prompt、reasoning/service-tier 会话覆盖、
> busy 模式装载、restart 超时、后台通知、provider routing、fallback 链热加载、并发会话上限、
> 子代理/压缩判定、`_queue_or_replace_pending_event`、`_prepare_busy_steer_text`、
> 以及本轮最重点 `_handle_active_session_busy_message`(busy 总入口,8742–9182)。

---

## 0. 本段在全局中的位置(调用登记)

`_handle_active_session_busy_message` 不是被 runner 自己调用的,而是**注册进每个平台 adapter**:

`gateway/run.py:11096 @ 863e313`(另两处注册:12468、13410)
```python
            adapter.set_busy_session_handler(self._handle_active_session_busy_message)
```

adapter 侧的挂载点与调用点:
- `gateway/platforms/base.py:3345-3347 @ 863e313` —— `set_busy_session_handler()` 存入 `self._busy_session_handler`;
- `gateway/platforms/base.py:5711-5716 @ 863e313` —— 会话活跃(`_active_sessions` 命中)时先调 busy handler,返回 True 即终止;返回 False/异常则回落 adapter 默认(photo 合并 5721-5724、text 防抖 5726-5734、其余 merge_text 合并 5742-5747):

```python
            if self._busy_session_handler is not None:
                try:
                    if await self._busy_session_handler(event, session_key):
                        return
                except Exception as e:
                    logger.error("[%s] Busy-session handler failed: %s", self.name, e, exc_info=True)
```

在 busy handler 之前,adapter 已经分流掉:bypass 命令(`should_bypass_active_session`,
`hermes_cli/commands.py:75-95 @ 863e313` 的 `busy_policy` 注册表:`dispatch` / `reject` /
`interrupt_then_dispatch`)与 clarify 文本拦截(`base.py:5655-5709`)。所以 busy handler
收到的是「会话忙 + 非 bypass 命令 + 非 clarify 回复」的消息。

另外注意:runner 的 `_handle_message` 内部还有第三份 busy 逻辑(PRIORITY path,
`gateway/run.py:14800-14930 @ 863e313`),处理绕过 adapter 守卫直接进入 runner 的事件,
两处的降级规则(#30170/#56391)刻意保持同构(14887-14918 的注释明确引用
`_handle_active_session_busy_message` 作为 rationale)。这对理解「双层守卫」的文档冲突很关键(见 §21)。

---

## 1. /queue FIFO 三件套:`_enqueue_fifo` / `_promote_queued_event` / `_queue_depth`

### 问题
adapter 的 `_pending_messages` 是**每会话单槽位**dict(photo burst 合并也用它)。/queue 语义要求
「每次调用产出一个完整 agent 回合、严格 FIFO、不合并」,单槽位放不下。设计注释直接写明:

`gateway/run.py:7680-7689 @ 863e313`
```python
    # -------- /queue FIFO helpers --------------------------------------
    # /queue must produce one full agent turn per invocation, in FIFO
    # order, with no merging.  The adapter's _pending_messages dict is a
    # single "next-up" slot (shared with photo-burst follow-ups), so we
    # use it for the head of the queue and an overflow list for the
    # tail.  Enqueue puts new items in the slot when free, otherwise in
    # the overflow.  Promotion (called after each run's drain) moves the
    # next overflow item into the slot so the following recursion picks
    # it up.  Clearing happens on /new and /reset via
    # _handle_reset_command.
```

### 实现:槽位 = 队头,overflow list = 队尾

`gateway/run.py:7691-7703 @ 863e313`
```python
    def _enqueue_fifo(self, session_key: str, queued_event: "MessageEvent", adapter: Any) -> None:
        """Append a /queue event to the FIFO chain for a session."""
        if adapter is None:
            return
        pending_slot = getattr(adapter, "_pending_messages", None)
        if pending_slot is None:
            return
        if session_key in pending_slot:
            self._session_state(session_key).conversation.queued_events.append(
                queued_event
            )
        else:
            pending_slot[session_key] = queued_event
```

- 槽位空 → 直接占槽(队头);槽位有人 → 追加到 `SessionState.conversation.queued_events`(队尾)。
- 队尾存在 runner 侧的 SessionState 里而不是 adapter 里 —— adapter 保持"单槽位"简单契约不动。

**晋升(drain 点唯一调用)**:`gateway/run.py:7722-7734 @ 863e313`
```python
        _q_state = self._peek_session_state(session_key)
        overflow = _q_state.conversation.queued_events if _q_state else None
        if not overflow:
            return pending_event
        next_queued = overflow.pop(0)
        if pending_event is None:
            return next_queued
        if adapter is not None and hasattr(adapter, "_pending_messages"):
            adapter._pending_messages[session_key] = next_queued
        else:
            # No adapter — push back so we don't silently drop the item.
            overflow.insert(0, next_queued)
        return pending_event
```

docstring(7711-7720)讲清两种情形:槽位被 `_dequeue_pending_event` 吃空 → overflow 头直接当作
本次 pending_event 返回;槽位又被别人(如 interrupt 后续)占了 → overflow 头**放进槽位**,让下一层
递归的 drain 去取。adapter 为 None 时回插 overflow 头,不丢消息。

drain 侧配对调用:`gateway/run.py:25480-25487 @ 863e313`
```python
                pending_event = _dequeue_pending_event(adapter, session_key)
                # /queue overflow: after consuming the adapter's "next-up"
                # slot, promote the next queued event into it so the
                # recursive run's drain will see it.  This keeps the slot
                # occupied for the full FIFO chain, which (a) preserves
                # order, and (b) causes any mid-chain /queue to correctly
                # route to overflow rather than jumping the queue.
                pending_event = self._promote_queued_event(session_key, adapter, pending_event)
```

关键性质:**晋升让槽位在整条链存续期间始终被占**,于是链中途新来的 /queue 一定判断到"槽位有人"
而进 overflow,不会插队(a、b 两点注释)。`_dequeue_pending_event` 本身只是薄封装
(`gateway/run.py:2823-2830 @ 863e313`,`adapter.get_pending_message(session_key)`)。

**深度**:`gateway/run.py:7736-7742 @ 863e313`
```python
    def _queue_depth(self, session_key: str, *, adapter: Any = None) -> int:
        """Total pending /queue items for a session — slot + overflow."""
        _q_state = self._peek_session_state(session_key)
        depth = len(_q_state.conversation.queued_events) if _q_state else 0
        if adapter is not None and session_key in getattr(adapter, "_pending_messages", {}):
            depth += 1
        return depth
```

### 调用关系(全量)
- 入队:/queue busy handler(`gateway/run.py:14252`,ack 报深度 14253-14256)、/steer 三处 fallback
  (14281、14304)、Telegram 追发宽限期 queue 模式(14821)、heartbeat 事件(18807)、goal
  continuation(18960)、goal kickoff(`gateway/slash_commands.py:2763`)、
  `_queue_or_replace_pending_event`(8703,见 §17)。
- 深度展示:/status(`gateway/slash_commands.py:558`)。
- 晋升:仅 drain 点 25487。
- 行为规格:`tests/gateway/test_queue_command.py`、`test_queue_consumption.py`、
  `test_steer_fifo_overwrite.py`。

### 设计理由与取舍
- 不改 adapter 契约(单槽位)而在 runner 侧加尾巴:photo burst 合并、STT 缓存等既有槽位语义零改动;
  代价是队列状态劈成两半(adapter 槽 + SessionState 尾),深度、清空、goal 清理都要两处同时处理。
- 晋升发生在 drain 而非入队:保证"槽位常占"这一 FIFO 不插队不变式,但依赖 drain 点唯一——若未来
  出现第二个消费槽位的路径,必须同步调用 `_promote_queued_event`(7713-7714 的注释点名了这一契约)。

### 重实现要点
1. 队列 = 头槽(与平台层共享)+ 尾 list(会话状态);入队先试占槽,占不到进尾。
2. 消费点吃掉槽后立刻晋升尾头进槽,维持"链存续期间槽常占"不变式,天然防插队。
3. 晋升要处理"槽已被别人占"的并发:把尾头塞槽等下一轮,而不是覆盖或丢弃。
4. 无 adapter 时回插尾部,任何路径不得静默丢消息。
5. 深度 = 槽占用(0/1)+ 尾长度,供 ack 与 /status 展示。

---

## 2. Goal continuation 的识别与竞态清理

### 问题
/goal 的 judge 会把「继续推进目标」的合成回合经同一条 FIFO 入队(18947-18960 注释:走 FIFO 使
在途用户消息自然优先)。用户 `/goal pause|clear` 可能与已入队的 continuation 竞态;drain 时
goal 也可能已经不再活跃。所以需要:识别合成回合、按需摘除、消费前复核。

### 实现

**识别(前缀匹配)**:`gateway/run.py:7744-7753 @ 863e313`
```python
    @staticmethod
    def _is_goal_continuation_event(event_or_text: Any) -> bool:
        """Return True for synthetic /goal continuation turns.

        Goal continuations are normal queued user-role events, so pause/clear
        must distinguish them from real user /queue messages before removing or
        suppressing them.
        """
        text = getattr(event_or_text, "text", event_or_text) or ""
        return str(text).startswith("[Continuing toward your standing goal]\nGoal:")
```

前缀来源是 `hermes_cli/goals.py:90-128 @ 863e313` 的三个模板(普通/contract/subgoals 版都以
`[Continuing toward your standing goal]\nGoal: ` 开头)。

**清理(pause/clear 竞态)**:`gateway/run.py:7762-7787 @ 863e313`
```python
        removed = 0
        pending_slot = getattr(adapter, "_pending_messages", None) if adapter is not None else None
        if isinstance(pending_slot, dict):
            pending_event = pending_slot.get(session_key)
            if self._is_goal_continuation_event(pending_event):
                pending_slot.pop(session_key, None)
                removed += 1

        _q_state = self._peek_session_state(session_key)
        overflow = _q_state.conversation.queued_events if _q_state else []
        if overflow:
            kept = []
            for queued_event in overflow:
                if self._is_goal_continuation_event(queued_event):
                    removed += 1
                else:
                    kept.append(queued_event)
            _q_state.conversation.queued_events = kept
        return removed
```

只摘合成 continuation,保留真实 /queue;槽和尾都要扫(队列劈两半的直接后果)。
调用点:`gateway/slash_commands.py:2636、2654 @ 863e313`(/goal pause 与 clear)。

**消费前复核**:`gateway/run.py:7782-7791 @ 863e313`(`GoalManager(session_id).is_active()`,
异常按 False 处理)+ drain 点 `gateway/run.py:25692-25697 @ 863e313`:
```python
                    if self._is_goal_continuation_event(pending_event) and not self._goal_still_active_for_session(session_id):
                        logger.info(
                            "Discarding stale goal continuation for session %s — goal is no longer active",
                            session_key or "?",
                        )
                        return result
```

行为规格:`tests/gateway/test_goal_continuation_drain.py`。

### 发现:gate-failed 变体逃逸前缀检查(bug 候选,记入定案)
`hermes_cli/goals.py:133-135 @ 863e313`:
```python
CONTINUATION_PROMPT_GATE_FAILED_TEMPLATE = (
    "[Continuing toward your standing goal — a quality gate failed]\n"
    "Goal: {goal}\n\n"
```
该模板首行带 `— a quality gate failed` 后缀,`startswith("[Continuing toward your standing goal]\nGoal:")`
**匹配不到**。后果:已入队的 gate-failed continuation ① 不会被 `/goal pause|clear` 摘除
(7766/7775 判假),② drain 时不做 `_goal_still_active_for_session` 复核(25692 判假),
会作为普通用户回合照常执行。属于"用文本前缀当类型标签"的脆弱性代表:新增模板忘了同步谓词。

### 重实现要点
1. 合成回合要可识别 —— 但别用文本前缀,给事件加显式 `synthetic_kind` 字段,谓词与模板不会漂移。
2. pause/clear 必须同时清"已入队"的合成回合,且只清合成的(槽+尾两处)。
3. 消费前对合成回合做新鲜度复核(目标是否还活跃),复核失败静默丢弃并留日志。
4. 复核读 DB 失败按"不活跃"处理(宁可丢一条合成回合,不要在目标已清后再跑一轮)。

---

## 3. Runtime status 持久化:`_update_runtime_status` / `_persist_active_agents`

### 问题
dashboard `/api/status` 读 `gateway_state.json`;若只在生命周期切换时写,`active_agents` 在两次
切换之间是陈旧的(一个回合可以完整开始并结束而文件纹丝不动)。

### 实现
`gateway/run.py:7793-7803 @ 863e313`:`_update_runtime_status(gateway_state, exit_reason)` 透传
`restart_requested` 与 `_active_work_count()`,best-effort(裸 except pass)。

`gateway/run.py:7815-7835 @ 863e313`(节选 docstring 的关键三句):
```python
        Deliberately passes ONLY ``active_agents`` — ``gateway_state`` and the
        other fields stay ``_UNSET`` so ``write_runtime_status``'s
        read-merge-write preserves the current lifecycle state (``running`` /
        ``draining`` / …).  Passing ``gateway_state=None`` here would clobber it.
        Best-effort: a failed status write must never disrupt a turn.
```

支撑机制在 `gateway/status.py:980-1029 @ 863e313`:`write_runtime_status` 全参默认 `_UNSET`,
读旧 payload → 仅覆盖显式传入的字段 → 写回(read-merge-write);`None` 是合法值(比如清空
exit_reason),所以必须用哨兵而非 None 区分"没传"。

`_active_work_count`(`gateway/run.py:7381-7387 @ 863e313`)= messaging `_running_agents` +
cron 在飞 + API 在飞 —— 三类工作合并成一个可 drain 总数。

调用节奏:`_persist_active_agents` 在每次回合槽位 claim/release 时调(如 15687),
外部 drain watcher 轮询期间也刷(7904)。

### 重实现要点
1. 状态文件用 read-merge-write + `_UNSET` 哨兵:每个写入者只声明自己拥有的字段,None 保持合法值。
2. "活跃工作数"必须聚合所有执行面(消息/定时/API),否则外部 drain 轮询会提前放行。
3. 每个回合边界都刷 active_agents,让外部观察者近实时;写失败绝不影响回合(best-effort)。
4. 生命周期字段(running/draining)只由生命周期代码写,计数路径绝不碰它。

---

## 4. 外部 drain(可逆静默,不退进程)

### 问题
NAS/dashboard 需要"让 gateway 拒新保旧、跑空后做维护、可随时取消"——不能靠重启实现(Phase 2,
设计代号 D4a,见 7827-7836 的段注释)。

### 实现
进入:`gateway/run.py:7837-7855 @ 863e313` —— 幂等;置 `_external_drain_active`;不打断在飞回合
("the whole point is to let them finish");`_update_runtime_status("draining")`。

退出(关键守卫):`gateway/run.py:7864-7874 @ 863e313`
```python
        if not self._external_drain_active:
            return
        self._external_drain_active = False
        if self._draining or not self._running:
            # A shutdown drain is in progress / the loop has stopped — do not
            # clobber the terminal state back to running.
            logger.info(
                "External drain marker cleared during shutdown — not reverting "
                "to running (shutdown takes precedence)."
            )
            return
```
真正的 shutdown drain(`_draining`)优先级高于外部 drain 取消 —— 绝不把一个正在停机的 gateway
"复活"成 running。

watcher:`gateway/run.py:7881-7911 @ 863e313` —— 1s 轮询 `.drain_request.json`
(presence-based 契约),present→enter、absent→exit;每 tick 兜异常继续(7909-7910);
drain 中顺带 `_persist_active_agents()`(7904,cron/API 工作不在 messaging map 里,轮询方
需要新鲜聚合数)。

marker 新鲜度:`gateway/drain_control.py:210-226 @ 863e313` —— marker 带**实例化 epoch**,
epoch 不匹配视为不存在(NS-570:HERMES_HOME 是持久卷,机器重启后残留 marker 会把新 gateway
永久卡在 draining);无 epoch 的 legacy/损坏 marker 宽松地按"在 drain"处理。

行为规格:`tests/gateway/test_external_drain_control.py`。

### 重实现要点
1. 可逆静默 = 文件 marker + 轮询 reconcile,而不是一次性 RPC:天然幂等、进程重启也能收敛。
2. marker 必须带实例 epoch,持久卷上的残留 marker 才不会 wedge 新进程(fail 方向:损坏 marker 宁可当 drain)。
3. 退出路径要让"真 shutdown"压过"取消外部 drain",终态不可被复活。
4. watcher 每 tick 兜异常;drain 状态下持续刷活跃计数,供外部轮询 `active_agents==0`。
5. 进入/退出都幂等,状态翻转只写 lifecycle 字段(靠 §3 的 merge 写法)。

---

## 5. 平台熔断:`_pause_failed_platform` / `_resume_paused_platform`

### 问题
某平台适配器反复连接失败时,需要手动"停牌"(不再重试)与"复牌"。注意 7943-7946 的澄清:
**reconnect watcher 不会自动 pause** —— 可重试(网络/DNS)失败会在退避上限处无限重试,
瞬时故障自愈;pause 只来自 `/platform pause <name>` 人工操作。

### 实现
`gateway/run.py:7948-7957 @ 863e313`:
```python
        info = getattr(self, "_failed_platforms", {}).get(platform)
        if info is None:
            return
        if info.get("paused"):
            return
        info["paused"] = True
        info["pause_reason"] = reason or "auto-paused after repeated failures"
        # Push next_retry far enough out that even if "paused" is missed
        # by a stale code path, the watcher won't fire on it.
        info["next_retry"] = float("inf")
```
双保险:`paused` 标志 + `next_retry=inf`(旧代码路径漏检标志也不会触发)。随后写
per-platform runtime status(`platform_state="paused"`,7959-7964;写入函数
`_update_platform_runtime_status` 7913-7930,对应 `status.py` 的 platforms 子字典 1018-1027)。

resume(`gateway/run.py:7985-7988 @ 863e313`):清标志、`attempts=0`、
`next_retry = time.monotonic()`(下一 tick 立即重试),状态写 `retrying`;返回 bool 告知
调用方是否真的处于 paused。

### 重实现要点
1. 熔断状态放在 `_failed_platforms[platform]` 一处,pause 只是给条目加标志,不移出队列(/platform list 仍可见)。
2. 防御性双写:标志 + 无穷远的 next_retry,任何一个被尊重都不会误触发。
3. 自动重试与人工停牌分离:可重试故障永不自动 pause,自愈路径保持无人值守。
4. resume 要重置计数并调度立即重试,且返回是否命中(供命令回显)。

---

## 6. Prefill 与 ephemeral system prompt 装载

`_load_prefill_messages`(`gateway/run.py:8001-8033 @ 863e313`):优先级
`HERMES_PREFILL_MESSAGES_FILE` env > 顶层 `prefill_messages_file` > legacy `agent.prefill_messages_file`;
相对路径以 `~/.hermes/` 为基;文件必须是 JSON 数组,任何失败降级为 `[]` 并 warning。
(prefill = 注入到对话开头的历史消息,ephemeral = 不落盘、仅本进程生效。)

`_load_ephemeral_system_prompt`(`gateway/run.py:8035-8046 @ 863e313`):
`HERMES_EPHEMERAL_SYSTEM_PROMPT` env > `agent.system_prompt`,strip 后返回。

重实现要点:env > 顶层 key > legacy key 的三级回退;失败一律空值不炸;相对路径锚定配置目录。

---

## 7. Per-channel model / system prompt 解析

`_resolve_model_for_channel`(`gateway/run.py:8048-8083 @ 863e313`):把优先级规则**委托**给
`hermes_cli/model_switch.py:760` 的 `resolve_effective_model`(session override > channel
override > global default)—— docstring 点名这是与 API server 共用的"单一属主",防止两个
表面再度漂移(引 7dd00bb47d);本调用点 session 档传 None,session /model 覆盖由下游
`_apply_session_model_override` 补:

`gateway/run.py:8079-8083 @ 863e313`
```python
        return resolve_effective_model(
            None,  # session tier applied downstream (_apply_session_model_override)
            override,
            _resolve_gateway_model(user_config),
        )
```

`_get_system_prompt_for_channel`(`gateway/run.py:8085-8111 @ 863e313`):channel_overrides 的
system_prompt 优先,否则全局 `_ephemeral_system_prompt`;legacy `channel_prompts` 走
`event.channel_prompt` 另一条路(8096-8098 注释),此处不重复。

重实现要点:优先级链条只在一个函数实现,所有表面调它;每层调用点用注释交代"本层不管哪一档、
谁在下游补齐",避免双重应用。

---

## 8. Reasoning 配置与 `/reasoning` 会话覆盖

- `_load_reasoning_config`(`gateway/run.py:8113-8128 @ 863e313`):薄封装
  `hermes_constants.py:1099` 的 `resolve_reasoning_config`(per-model override > 全局
  `agent.reasoning_effort`;YAML `False` = 显式禁用)。Closes **#21256**。
- `_parse_reasoning_command_args`(8130-8154):shlex 切词、em-dash 归一成 `--`、任意位置的
  `--global` 提出来,返回 `(value, persist_global)`;默认 session-scoped。
- `_resolve_session_reasoning_config`(8156-8183):session 覆盖(存在即用,含显式 None?——
  注意这里判断的是 `is not None`,即 reasoning 的会话覆盖**不允许**"显式空覆盖",与 service
  tier 不同)> per-model > 全局;`model` 应传会话**生效**模型(含 /model 覆盖),让 per-model
  override 跟着实际运行的模型走。
- `_set_session_reasoning_override`(8185-8198):

`gateway/run.py:8193-8198 @ 863e313`
```python
        # Per-session field write — the old lazy ``self._session_reasoning_overrides
        # = {}`` init replaced the WHOLE dict, racing concurrent sessions'
        # overrides; a SessionState field reset cannot cross sessions.
        self._session_state(session_key).conversation.reasoning_override = (
            None if reasoning_config is None else dict(reasoning_config)
        )
```
历史 bug:惰性初始化整字典赋值会把并发会话的覆盖清掉;改为 SessionState 字段后按会话隔离。

重实现要点:会话级覆盖存进会话状态对象而非 runner 级共享 dict;覆盖值存副本(`dict(...)`)防
调用方后续原地改;解析命令参数时把排版字符(em-dash)归一。

---

## 9. Service tier(/fast)会话覆盖:存在性语义

与 reasoning 的关键差异:覆盖值可以是 `"priority"` **或显式 None(明确要求 normal)**,
所以不能用真值/None 判断,必须用哨兵判"是否设过":

`gateway/run.py:8218-8226 @ 863e313`
```python
        if resolved_session_key:
            _t_state = self._peek_session_state(resolved_session_key)
            if (
                _t_state is not None
                and _t_state.conversation.service_tier_override
                is not _SERVICE_TIER_UNSET
            ):
                return _t_state.conversation.service_tier_override
        return self._load_service_tier()
```
(哨兵 import 自 gateway/run.py:2371 `SERVICE_TIER_UNSET as _SERVICE_TIER_UNSET`。)
写入(8228-8247):`clear=True` 写回哨兵(回落 config),否则存 "priority"/None。
`_load_service_tier`(8249-8266):`fast|priority|on → "priority"`,
`normal|default|standard|off|none|空 → None`,未知值 warning 后 None。

重实现要点:三态配置(未设/显式关/显式开)必须用哨兵而不是 None;config 值做同义词归一并对
未知值 fail-open 成默认。

---

## 10. busy 模式装载:`busy_input_mode` 与 legacy `busy_text_mode`

`_load_busy_input_mode`(`gateway/run.py:8277-8288 @ 863e313`):env
`HERMES_GATEWAY_BUSY_INPUT_MODE` > `display.busy_input_mode`;合法值 `queue|steer`,
**其余一律 `interrupt`(默认)**。

`_load_busy_text_mode`(8290-8312):
```python
        # Legacy explicit override wins for backward compat.
        legacy = os.getenv("HERMES_GATEWAY_BUSY_TEXT_MODE", "").strip().lower()
        if not legacy:
            cfg = _load_gateway_runtime_config()
            legacy = str(cfg_get(cfg, "display", "busy_text_mode", default="") or "").strip().lower()
        if legacy == "interrupt":
            return "interrupt"
        if legacy == "queue":
            return "queue"
        # No explicit legacy knob → follow busy_input_mode.
        input_mode = GatewayRunner._load_busy_input_mode()
        return "queue" if input_mode == "queue" else "interrupt"
```
(`gateway/run.py:8301-8312 @ 863e313`)语义:`busy_input_mode` 是唯一真源;老用户显式设过
`busy_text_mode` 的继续生效(兼容既有 queue 部署),新装机跟随 input_mode;steer 不出现在
text_mode 值域(steer 在上游 input_mode 层处理)。

装载点:`gateway/run.py:5906-5907 @ 863e313`(`__init__`),并镜像给每个 adapter
(11102/12474/13418 `adapter._busy_text_mode = self._busy_text_mode`)—— adapter 用它决定
text 防抖候选(`gateway/platforms/base.py:5726` `_is_queue_text_debounce_candidate`)。

重实现要点:新旧两个旋钮并存时,把"新钮为真源、旧钮仅显式设置时生效"的仲裁收进一个装载函数;
装载结果一次性算好(进程级),busy 路径高频读不再碰 config。

---

## 11. Restart drain 超时装载

- `_load_restart_drain_timeout`(`gateway/run.py:8314-8331 @ 863e313`):env
  `HERMES_RESTART_DRAIN_TIMEOUT` > `agent.restart_drain_timeout`;解析在
  `gateway/restart.py:69` `parse_restart_drain_timeout`(默认常量 gateway/restart.py:23)。注意
  8322-8330 的 warning 技巧:解析器失败会静默回默认,所以外层"值==默认 且原始串确实非法"时才补
  warning —— 既不重复告警,又不吞掉用户的错字。
- `_load_restart_after_turn_timeout`(8333-8354,**#77184** in-band restart 等 idle 的超时):
  与上者同构,但 env 判断用 `is not None and strip()!=""`,因为 **`0` 是合法值**(8344-8345
  注释),不能用真值判断。

重实现要点:解析失败回默认的解析器 + 外层"原始值非空且非法才告警"的组合;`0` 合法的数值配置
不得用 truthiness 短路。

---

## 12. 后台进程通知模式

`_load_background_notifications_mode`(`gateway/run.py:8356-8382 @ 863e313`):四档
`all|result|error|off`(8360-8364 docstring);env > `display.background_process_notifications`;
YAML `False` 映射为 `off`(8370-8371);非法值 warning 后回 `all`。
消费方是后台进程 watcher(terminal notify_on_complete 路径,本段之外)。

重实现要点:布尔样式的 YAML 值(False)要显式映射进枚举;默认档选"最吵"的 all,fail-loud。

---

## 13. Provider routing 与 fallback 模型链(#60955)

### 问题
fallback 链(主 provider 失败时依次切换的 provider 列表)原先在进程启动时冻结在
`self._fallback_model`,gateway 运行期间改 config 不生效——而同进程的 cron 每次 job 都重读,
行为不一致(**#60955**)。

### 实现
- `_load_provider_routing`(8384-8394):canonical loader(managed overlay + `${VAR}` 展开)读
  `provider_routing`,fail-open 成 `{}`。
- `_load_fallback_model`(8396-8413):`get_fallback_chain(cfg)`
  (`hermes_cli/fallback_config.py:80`)—— `fallback_providers` 优先、legacy `fallback_model`
  合并在后。
- **热刷新** `_refresh_fallback_model`(8415-8460):每次 agent create/reuse 前重读磁盘。
  关键取舍在 8434-8439:

`gateway/run.py:8435-8443 @ 863e313`
```python
            # Raw primitive (raises on parse failure) is required here: the
            # canonical fail-open loader would return {} on a torn mid-edit
            # write and WIPE the last known-good chain. The overlay/expansion
            # below fixes the managed-scope/${VAR} drift without losing that.
            cfg = read_user_config_raw(cfg_path)
            try:
                from hermes_cli import managed_scope
                cfg = managed_scope.apply_managed_overlay(cfg)
            except Exception:
                pass
```
即:**故意不用 fail-open loader** —— 用户非原子写 config 的撕裂瞬间,fail-open 会返回 `{}`
从而清掉最后已知好链;raw 读会抛异常 → 走 8452-8458 的"保留 last known-good"分支。只有
**读成功且确实没配** 才清链(8459)。overlay/`${VAR}` 展开在 raw 读之后手工补,兼得两边。

- **应用到缓存 agent** `_apply_fallback_chain_to_agent`(8462-8496):
  - cooldown 守卫(8475-8480):agent 正处于已激活 fallback 的限速冷却期
    (`_fallback_activated` 且 `_rate_limited_until > monotonic()`)时**跳过改写**——那段
    回合级生命周期归 `restore_primary_runtime` 管;
  - 否则整链替换 `_fallback_chain/_fallback_model`,未激活时重置 `_fallback_index=0`;
  - **仅当链内容真变了**才清 `_unavailable_fallback_keys`(8493-8496)——config 编辑代表用户
    动过手(比如补了凭据),被记为不可用的条目应该重试;而逐消息的 no-op 刷新不清,保留 memo
    的限速价值。

行为规格:`tests/gateway/test_fallback_chain_reload.py`、`test_fallback_eviction.py`。

### 重实现要点
1. 会被运行期编辑的配置,读取点选"每次使用前刷新",且撕裂写要能与"确实删了配置"区分
   (raise-on-parse-failure + 保留 last known-good)。
2. 对缓存对象热更新时,避开"该对象正处于自治状态机的中间态"(fallback 冷却期),属主唯一。
3. 失败 memo 的失效时机绑定"配置内容变化"而非"每次刷新",兼顾重试与限速。
4. 新旧配置键合并时固定优先序(`fallback_providers` 前、legacy 后),在读取函数里一次定死。

---

## 14. 并发会话上限:`_claim_active_session_slot`

### 实现(两级检查:进程内 + 跨进程)
- `_snapshot_running_agents`(8498-8503):滤掉 `_AGENT_PENDING_SENTINEL`(gateway/run.py:2465 定义的
  占位对象,表示"槽已 claim 但 AIAgent 未建好")。
- `_get_max_concurrent_sessions`(8505-8512)→ `hermes_cli/active_sessions.py:56`
  `resolve_max_concurrent_sessions`(顶层 `max_concurrent_sessions`,回退 `gateway.*`)。
- 进程内预检 `_active_session_limit_message`(8514-8526):未配置→放行;**本会话已在跑→放行**
  (追发不算新会话);`_running_agent_count() < max` →放行;否则返回
  `hermes_cli/active_sessions.py:99` 的拒绝文案(点名占坑者:"slots 由 CLI/desktop/gateway 共享,被拒的
  往往不是占坑的那个表面",99-114)。
- 跨进程取租约:`gateway/run.py:8534-8555 @ 863e313`
```python
        if self._is_session_running(session_key):
            return None, None
        local_limit_message = self._active_session_limit_message(session_key)
        if local_limit_message is not None:
            return None, local_limit_message
        try:
            from hermes_cli.active_sessions import try_acquire_active_session

            platform = source.platform.value if source and source.platform else "gateway"
            return try_acquire_active_session(
                session_id=session_key,
                surface=f"gateway:{platform}",
                config=getattr(self, "config", None),
                metadata={
                    "platform": platform,
                    "chat_id": getattr(source, "chat_id", "") or "",
                    "user_id": getattr(source, "user_id", "") or "",
                },
            )
        except Exception as exc:
            logger.warning("Failed to claim active session slot: %s", exc)
            return None, None
```
(metadata 处为省行号缩写;原文 8546-8551 传 platform/chat_id/user_id。)
`try_acquire_active_session`(hermes_cli/active_sessions.py:271-291):cap 未启用时返回 **no-op 租约**,
调用方可无条件 `release()`;异常时 `(None, None)` = fail-open(上限机制失效不至于拒绝所有消息)。

### 调用点与时序
`gateway/run.py:15665-15688 @ 863e313`:claim 放在 `_handle_message` 里**任何 await 之前**——
从这里到 `_run_agent` 注册真 agent 之间有大量 yield 点(hooks、vision、STT、压缩),没有
sentinel 的话第二条消息会穿过"already running"守卫造出重复 agent、写坏 transcript。claim 成功后
`turn.agent = _AGENT_PENDING_SENTINEL`、记 `started_ts`、`_persist_active_agents()`。

### 重实现要点
1. 并发上限做两级:进程内快速预检(免费)+ 跨进程文件租约(权威);任何一级异常都 fail-open。
2. "同会话追发"不占新槽 —— 上限只约束**新会话**并发。
3. 租约对象统一返回(cap 关闭时给 no-op 租约),调用方 release 无需分支。
4. claim 必须在首个 await 之前同步完成,并立刻放 sentinel 占位,关闭重复 agent 竞窗。
5. 拒绝文案要点名占坑者(跨表面共享槽时,被拒者通常不是元凶)。

---

## 15. 子代理活跃判定:`_agent_has_active_subagents`(#30170)

### 问题(事故)
**#30170**:`AIAgent.interrupt()` 会同步级联到父 agent 的 `_active_children` 每个子代理
(证据:`run_agent.py:3149-3158 @ 863e313`):
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
```
于是 `busy_input_mode='interrupt'`(默认)下,用户一句闲聊追问就把跑了几分钟的
`delegate_task` 子代理全部打断,产生无信号的 fallback 级联。

### 实现
`gateway/run.py:8574-8593 @ 863e313`:
```python
        if running_agent is None or running_agent is _AGENT_PENDING_SENTINEL:
            return False
        children = getattr(running_agent, "_active_children", None)
        # AIAgent always initialises this as a concrete list (see
        # agent/agent_init.py). Reject anything that isn't a real
        # collection — this guards against ``MagicMock()._active_children``
        # auto-creating a truthy stub in tests and triggering the demotion
        # against an agent that doesn't actually have subagents.
        if not isinstance(children, (list, tuple, set)):
            return False
        if not children:
            return False
        lock = getattr(running_agent, "_active_children_lock", None)
        try:
            if lock is not None:
                with lock:
                    return bool(children)
            return bool(children)
        except Exception:
            return False
```
要点:类型白名单挡 MagicMock 自动属性(测试真实伤过);先无锁快查再持锁复核;任何异常返回
False(safe-by-default:判定坏了退回既有 interrupt 行为,而不是把 interrupt 永久变 queue)。
显式 `/stop` `/new` 走 `_interrupt_and_clear_session`,**不受**此降级影响(8567-8570 docstring)
—— 操作员始终有强停开关。

行为规格:`tests/gateway/test_subagent_protection_30170.py`。

### 重实现要点
1. "打断"与"追问"是两种意图:默认 interrupt 只应作用于无子任务的轻回合,有子任务在飞时自动降级为排队。
2. 探测别人对象的内部状态时:类型白名单 + 持锁读 + 异常一律返回"不降级"(保守失败方向要想清楚)。
3. 给操作员留显式逃生门(/stop 不走降级路径),并在 ack 文案里教育用户(见 §19k)。

---

## 16. 压缩飞行中判定:`_session_has_compression_in_flight`(#56391,#23975)

### 问题(事故)
压缩(上下文历史压缩+会话 id 轮转)本身已经对 interrupt 免疫(**#23975**),但 gateway 的
interrupt busy 模式仍会**对轮转前的父会话开启新回合**,压缩随后落地把 id 换掉,新回合成了
"孤儿压缩兄弟"(**#56391**)。解法同样是把 interrupt 降级成 queue,等压缩+轮转落地。

### 实现
`gateway/run.py:8595-8647 @ 863e313`。两段阻塞源都 `asyncio.to_thread` 下放
(8611-8614 读 session_store、8632-8635 查 SQLite `get_compression_lock_holder`),
docstring 注明"大 state.db 不能冻住事件循环(#5)"。失败方向刻意不对称:
- `AttributeError/TypeError`(对象形状不对,多半是测试桩)→ False;
- 其他异常 → **True**(fail-closed):

`gateway/run.py:8639-8647 @ 863e313`
```python
        except Exception:
            logger.warning(
                "Compression in-flight check failed while reading lock holder "
                "for session %s; treating compression as active to avoid "
                "interrupting a possible parent-session rotation",
                session_id,
                exc_info=True,
            )
            return True
```
`_lookup_session_id_under_store_lock`(8649-8656):同步帮手在线程池里持 store 锁读
`session_key → session_id` 映射(`# noqa: SLF001` 注明是有意的私有访问)。

### 重实现要点
1. "正在做不可打断的结构性变更(压缩/轮转)"要有可查询的权威信号 —— 这里用 DB 里的压缩锁持有者。
2. 判定函数的失败方向按错误类别拆:形状错误(桩/降级环境)→ 不干预;真实读失败 → 保守当作"在压缩"。
3. 所有可能阻塞的 IO(文件锁+JSON、SQLite SELECT)放线程池,busy 路径不能卡事件循环。
4. 与 §15 相同的降级模式复用同一个 queue 入口,用户可感知(ack 文案区分两种降级原因)。

---

## 17. `_queue_or_replace_pending_event`(#28503)与 32 条上限

### 问题(事故)
**#28503**:busy queue 模式下连发文本,旧实现 `merge_pending_message_event(merge_text=False)`
会**静默覆盖**单槽位 —— 第二条把第一条顶掉。

### 实现
`gateway/run.py:8678-8715 @ 863e313`(核心分支):
```python
        pending_slot = getattr(adapter, "_pending_messages", None)
        existing = pending_slot.get(session_key) if isinstance(pending_slot, dict) else None
        if existing is not None and (
            getattr(existing, "message_type", None) == MessageType.PHOTO
            or event.message_type == MessageType.PHOTO
            or bool(getattr(existing, "media_urls", None))
            or bool(getattr(event, "media_urls", None))
        ):
            # Preserve photo-burst / media-merge semantics for the head slot.
            merge_pending_message_event(
                adapter._pending_messages,
                session_key,
                event,
                merge_text=event.message_type == MessageType.TEXT,
            )
            return

        if self._queue_depth(session_key, adapter=adapter) >= self._BUSY_QUEUE_MAX_PENDING:
            logger.warning(
                "Dropping busy-mode follow-up for session %s — pending queue at cap (%d).",
                session_key,
                self._BUSY_QUEUE_MAX_PENDING,
            )
            return

        self._enqueue_fifo(session_key, event, adapter)
```
(8697-8700 warning 原文省略为 `...`。)规则:头槽或新事件**涉媒体**→ 沿用
`merge_pending_message_event`(`gateway/platforms/base.py:2438-2497 @ 863e313`:photo+photo
合 burst、媒体互补合并、text+text 仅在 merge_text 时拼接)保住相册语义;纯文本 → 走 §1 的
FIFO,每条自成一回合。

上限:`gateway/run.py:2658-2664` 段注释 + `_BUSY_QUEUE_MAX_PENDING = 32`(8664)——
卡死的 agent + 连点的用户会让 overflow 无界增长;32 回合远超真实对话积压又不威胁内存;
超限**丢弃并 warning**(8695-8701),不是拒绝入队报错给用户。

调用点:busy handler 的 draining 分支(8768)、未 steer/redirect 的兜底入队(8994)、
PRIORITY path 的 draining/queue/steer-fallback/两个降级(14853、14861、14885、14901、14917)。

### 重实现要点
1. 同一个"忙时收纳"入口统一三类语义:媒体合并(相册)、文本 FIFO(保消息边界)、深度上限。
2. 上限保护针对 overflow 无界增长,数值取"远超真实积压、不伤内存",超限丢弃要留日志。
3. 判断"涉媒体"要看双方(槽内既有事件与新事件)的 message_type 与 media_urls。

---

## 18. `_prepare_busy_steer_text`:语音折叠(#58780 前半)

### 问题
fresh/queued 语音都会走正常入站 STT 管线,但 **steer 成功的消息绕过该队列**;纯语音追问文本为空,
steer 模式就静默退化成 queue 模式(**#58780**)。

### 实现
`gateway/run.py:8726-8740 @ 863e313`:
```python
        text = (event.text or "").strip()
        if not self._pending_event_audio_paths(event):
            return text

        adapter = self._adapter_for_source(event.source)
        enriched_text, successful_transcripts = await self._transcribe_and_echo_pending_voice(
            event,
            adapter,
            event.source,
            text,
            log_context="Busy-steer",
        )
        if not successful_transcripts:
            return text
        return (enriched_text or text).strip()
```
docstring(8708-8724)的三个设计点:① 只有 voice-message 媒体走自动 STT,音频**文件附件**不转
(与 `_prepare_inbound_message_text` 同一契约);② 转写失败保留 caption,让 steer fallback 把
事件按原样入队,不丢消息;③ 强制路由经 `_transcribe_and_echo_pending_voice`
(`gateway/run.py:21786`,与 interrupt monitor、pending-drain 共享的**唯一**带外转写咽喉)——
转写结果缓存在事件上,每条平台消息**至多一次 STT 调用**;若 steer 稍后退回 queue,drain 复用
缓存转写、不二次计费、echo 也按计数台账不重发。

### 重实现要点
1. 绕过主管线的旁路(steer)要自带同等预处理,否则某类输入(语音)会静默改变模式语义。
2. 带外转写全仓库收敛到一个咽喉函数:事件上缓存转写 + echo 计数,天然幂等,模式回退不重复付费。
3. 失败路径返回原文本,让下游 fallback 机制兜底,不在预处理层丢事件。

---

## 19. `_handle_active_session_busy_message`(8742–9182):busy 总入口逐阶段

契约:`async (event, session_key) -> bool`;True = 已处理(adapter 直接 return),
False = 回落 adapter 默认合并/防抖路径(见 §0)。以下按代码顺序。

### a. 授权门(#17775)8743-8757
冷路径 `_handle_message` 建会话前查 `_is_user_authorized`(`gateway/authz_mixin.py:386`),
busy 热路径原先**不查** —— 共享群(Slack/Telegram/Discord)里未授权用户可向别人正跑着的会话
注入消息。修复:同一检查,不过则 warning + `return True`(静默丢弃,**不能** return False,
否则回落 adapter 又给排进队列)。行为规格:`tests/gateway/test_busy_session_auth_bypass.py`。

### b. draining 分流 8759-8785
gateway 正在 restart/stop drain 时:`_queue_during_drain_enabled()`
(`gateway/run.py:7674-7678 @ 863e313`)
```python
    def _queue_during_drain_enabled(self) -> bool:
        # Both "queue" and "steer" modes imply the user doesn't want messages
        # to be lost during restart — queue them for the newly-spawned gateway
        # process to pick up.  "interrupt" mode drops them (current behaviour).
        return self._restart_requested and self._busy_input_mode in {"queue", "steer"}
```
= **restart**(不是 stop)且模式为 queue/steer → `_queue_or_replace_pending_event` 入队给
重启后的新进程接手,回执"queued for the next turn after it comes back";否则只回执"不收新回合"。
回执发送的 reply_to 规则(8776-8782):Telegram DM+thread → reply_anchor;Telegram 有 thread
(论坛话题)→ None(靠 metadata 落话题);其余 → 引用原消息 id。

### c. 审批词路由(#46866)8787-8860
**事故因果**:agent 阻塞等危险命令审批 → 用户回 "yes" → 旧逻辑把它当普通追问排到"审批解决后
才能开始的下一回合"后面 → 审批超时自动 deny —— 死锁。斜杠形式 `/approve` `/deny` 在 adapter
的 bypass 守卫已放行(busy_policy="dispatch",`hermes_cli/commands.py:143-145`),这里补的是
**裸词**(Signal/SMS 用户自然打 "yes" 而不是 "/approve")。

门闩:`tools/approval.py:2526-2529 @ 863e313`
```python
def has_blocking_approval(session_key: str) -> bool:
    """Check if a session has one or more blocking gateway approvals waiting."""
    with _lock:
        return bool(_gateway_queues.get(session_key))
```
**只有确实有阻塞审批时**才做词表匹配 —— 这就是"闲聊里的 yes 不会误触发危险命令"的消歧器
(8798-8801 注释点名设计意图)。词表(8812-8813):approve = `{approve,yes,ok,okay,confirm,y,👍}`,
deny = `{deny,no,reject,cancel,n,👎}`;另识别 `always`/`session` 修饰词(8820-8825)。

实现手法(8827-8837):**改写 event.text 为规范 `/approve [args]` 或 `/deny`** 再调既有 slash
处理器(`gateway/slash_commands.py:5377 / 5435`)—— 复用解析+i18n+resume-typing,不重造;
注释强调必须用字面 `/`(`is_command()` 只认 `/`,不认平台显示前缀 `!`)。slash 处理器的返回文案
在此路径没有人自动发送,所以 8843-8853 自己 `_unwrap_ephemeral` 后 `_send_with_retry` 补发。
整段包 try/except:路由失败 warning 后**继续走 busy 处理**(8855-8860),不吞消息。
行为规格:`tests/gateway/test_plaintext_approval_routing.py`。

### d. adapter 缺失 → False;internal 合成事件 → False(8862-8879)
`gateway/run.py:8878-8879 @ 863e313`
```python
        if getattr(event, "internal", False):
            return False
```
背景(8867-8877 注释):异步委托完成(`delegate_task(background=true)`)与后台进程完成
(terminal notify_on_complete)以 internal MessageEvent 回注原会话;若按用户 TEXT 处理,默认
interrupt 模式会**打断当前回合**还发"⚡ Interrupting"ack —— 与"完成通知只在空闲时作为新回合浮出、
绝不劈进正跑回合"的不变式相反。返回 False 让 base adapter 静默排队(无 interrupt 无 ack),
当前回合结束后级联。行为规格:`tests/gateway/test_internal_event_never_interrupts_busy_session.py`。

### e. busy_text_mode==queue 的让路(8884-8891)
```python
        effective_mode = self._busy_input_mode
        busy_text_mode = getattr(self, "_busy_text_mode", "interrupt")
        if (
            event.message_type == MessageType.TEXT
            and busy_text_mode == "queue"
            and effective_mode != "steer"
        ):
            return False
```
(`gateway/run.py:8884-8891 @ 863e313`)TEXT + legacy queue 且非 steer → 交还 adapter,
由 adapter 的 text 防抖窗口(`base.py:5726-5734`)合并突发多段输入。steer 模式例外
(steer 想立即注入,不等防抖)。

### f-h. 模式仲裁:两个自动降级 → steer → redirect

先取 `running_agent = _busy_state.turn.agent`(8881-8882),然后**在尝试 steer 之前**做两个
interrupt→queue 自动降级(顺序:subagents 先、compression 后,各自 logger.info 说明原因):

`gateway/run.py:8905-8926 @ 863e313`(压缩段节选)
```python
        demoted_for_subagents = (
            effective_mode == "interrupt"
            and self._agent_has_active_subagents(running_agent)
        )
        if demoted_for_subagents:
            ...
            effective_mode = "queue"
        demoted_for_compression = (
            effective_mode == "interrupt"
            and await self._session_has_compression_in_flight(session_key)
        )
        if demoted_for_compression:
            ...
            effective_mode = "queue"
```
注意短路经济学:两个降级只对 `interrupt` 模式判定;compression 检查(要摸 DB)排在后面,且
subagents 已降级成 queue 后不再触发(`effective_mode == "interrupt"` 不成立)。

**steer 分支**(8929-8961,含 #58780 后半):
```python
        if effective_mode == "steer":
            steer_text = await self._prepare_busy_steer_text(event)
            # A follow-up qualifies for steering when it is plain text, OR
            # when every attachment is STT-eligible voice media whose
            # transcript was just folded into steer_text — otherwise a voice
            # note in steer mode silently degrades to queue mode (#58780).
            _steer_media_urls = getattr(event, "media_urls", None) or []
            _steer_all_voice = bool(_steer_media_urls) and (
                len(self._pending_event_audio_paths(event)) == len(_steer_media_urls)
            )
            can_steer = (
                steer_text
                and (
                    (
                        event.message_type == MessageType.TEXT
                        and not event.media_urls
                        and not event.media_types
                    )
                    or _steer_all_voice
                )
                and running_agent is not None
                and running_agent is not _AGENT_PENDING_SENTINEL
                and hasattr(running_agent, "steer")
            )
```
(`gateway/run.py:8929-8952 @ 863e313`)可 steer 条件:有文本载荷 ×(纯文本 或 **全部附件都是
已折叠转写的语音**)× agent 真实存在 × 有 `steer()`。`running_agent.steer()`
(`run_agent.py:3229-3263 @ 863e313`)不打断当前工具:把文本暂存 `_pending_steer`(多次调用
换行拼接,线程安全),agent 循环在当前工具批次自然结束后把它**追加到最后一个 tool result 的
内容里**,模型下一轮迭代看到 —— 保持消息角色交替(改既有 tool 消息而非插新 user 回合,
`agent/agent_init.py:791-799` 注释)。steer 抛异常或拒收 → `effective_mode = "queue"`(8959-8961),
消息不丢。

**redirect 分支**(8962-8976):interrupt 模式、纯文本、agent 真实存在、
`_supports_active_turn_redirect is True`(`agent/agent_init.py:789 @ 863e313` 置 True)且有
`redirect()` 时,优先尝试 `running_agent.redirect(text)`(`run_agent.py:3265-3303`:普通模型
请求中只取消该请求,保留已完成消息/工具结果,把纠正作为真实 user 消息重试;工具执行中降级为
steer;codex_app_server 用原生 `turn/steer`)。redirect 失败 → `redirected=False`,落回下面的
硬 interrupt。注意 `is True` 严判:再次防 MagicMock 真值陷阱。

### i. FIFO 入队与消息边界(#43066 sub-bug 2)8978-8994
```python
        # Store the message so it's processed as the next turn after the
        # current run finishes (or is interrupted).  Skip this for a
        # successful steer — the text already landed inside the run and
        # must NOT also be replayed as a next-turn user message.
        ...
        if not steered and not redirected:
            self._queue_or_replace_pending_event(session_key, event)
```
(`gateway/run.py:8978-8994 @ 863e313`;中略注释讲 #43066)事故因果:interrupt 模式(或 steer
回退 queue)下连续两条文本,旧 `merge_pending_message_event(merge_text=True)` 把它们**换行拼成
一个回合**,消息边界被毁(**#43066 sub-bug 2**)。改走 §17 的 FIFO 入口:每条文本自成一回合、
按到达序;媒体仍保相册合并。steer/redirect 成功则**跳过入队** —— 文本已进当前 run,再排一遍
会重放。

### j. interrupt 执行(9000-9024)
```python
        if (
            effective_mode == "interrupt"
            and not redirected
            and running_agent
            and running_agent is not _AGENT_PENDING_SENTINEL
        ):
            try:
                _interrupt_text = event.text
                _media_urls = getattr(event, "media_urls", None) or []
                if self._pending_event_audio_paths(event):
                    _interrupt_text, _ = await self._transcribe_and_echo_pending_voice(
                        event, adapter, event.source, event.text or "",
                        log_context="Voice-busy-interrupt",
                    )
                elif not _interrupt_text and _media_urls:
                    _interrupt_text = _build_media_placeholder(event)
                running_agent.interrupt(_interrupt_text)
            except Exception:
                pass  # don't let interrupt failure block the ack
```
(`gateway/run.py:9003-9024 @ 863e313`,签名行折行微调)interrupt 前先把语音转写(同一咽喉,
缓存复用)或媒体占位符准备成 interrupt message,`AIAgent.interrupt()`
(`run_agent.py:3028-3161`)置 `_interrupt_requested` + 中断消息、级联子代理、通知工具线程。
注意:**事件此刻已经在 pending 队列里**(步骤 i),interrupt 只是让当前回合尽快退出,退出后的
drain(§1)把它作为下一回合取走 —— 这就是 interrupt 模式"打断 + 复用排队通道"的组合设计。

### k. busy ack(9026-9182)
1. 总开关 env `HERMES_GATEWAY_BUSY_ACK_ENABLED`(默认 true),关了直接 return True(9029-9032)
   —— 放在防抖**之前**,"不给从未发出的 ack 盖时间戳"(9027-9028 注释)。
2. 30s 防抖(9037-9041):`turn.busy_ack_ts` 距今 <30s → 静默处理不再发(注释:也避免为一条
   注定不发的 ack 再读一次 config)。
3. steer ack 独立开关(9050-9065):env `HERMES_GATEWAY_BUSY_STEER_ACK_ENABLED` >
   per-platform display 设置 `busy_steer_ack_enabled`(默认 true)—— 移动端会话可以让 steer
   完全无声(类比 STT echo 抑制)。
4. 状态详情(9072-9098):`busy_ack_detail` per-platform 开关;开则取
   `running_agent.get_activity_summary()`(`run_agent.py:4001`)拼 "N min elapsed /
   iteration i/max / running: tool"。
5. 四种文案(9100-9133):steer "⏩ Steered…arrives after the next tool call" /
   redirect "↪ Redirected…" / queue+子代理降级 "⏳ Subagent working…(use /stop to cancel
   everything)"(#30170 的教育文案,9111-9114 注释:让用户知道追问没杀掉子代理、并发现 /stop)
   / queue+压缩降级 "⏳ Compressing context…" / 普通 queue "⏳ Queued for the next turn…" /
   interrupt "⚡ Interrupting current task…"。
6. 首触 onboarding(9139-9162):`agent/onboarding.py:26` `BUSY_INPUT_FLAG`、
   `busy_input_hint_gateway(mode)`(agent/onboarding.py:36,按实际生效模式措辞)、`is_seen`/`mark_seen`
   (agent/onboarding.py:211/216,原子 YAML 写持久化到 config.yaml,一台安装只提示一次)。
7. 发送(9164-9180):Telegram anchor 规则同 §19b;发送失败仅 debug 日志。

行为规格:`tests/gateway/test_busy_session_ack.py`、`test_steer_command.py`、
`tests/run_agent/test_steer.py`。

### busy 总入口·重实现要点
1. 入口顺序即优先级:授权 → 生命周期(draining)→ 阻塞态短路(审批)→ 事件类别(internal/媒体/
   legacy 旋钮)→ 模式仲裁 → 收纳 → 打断 → 回执;每层要么终结(True)、要么显式让路(False)。
2. 热路径必须重演冷路径的安全检查(授权),且拒绝时要"终结"而不是"让路",否则守卫被下游好意撤销。
3. 模式是"期望",仲裁是"现实":steer/redirect 失败回退 queue、interrupt 遇子代理/压缩自动降级,
   每次降级都要 log + 差异化 ack 讲原因、给逃生门。
4. "已注入当前回合"(steer/redirect 成功)与"排下一回合"互斥,防重放;interrupt 则刻意二者兼有
   (先入队再打断,复用统一 drain)。
5. ack 是独立可关的礼貌层:总开关→防抖→模式细分开关→详情开关→首触教育,任何一步失败不影响输入
   已被处理的事实。
6. 词表式意图识别(yes/no)必须挂在强门闩(has_blocking_approval)之后,并复用规范命令处理器
   而非重造解析。

---

## 20. 调用关系速查(对方文件:行号 @ 863e313)

| 本段成员 | 依赖/被调 |
|---|---|
| `_enqueue_fifo`/`_promote_queued_event`/`_queue_depth` | adapter `_pending_messages`;drain 点 gateway/run.py:25480-25487;/queue gateway/run.py:14252;/steer gateway/run.py:14281/14304;goal gateway/run.py:18960、gateway/slash_commands.py:2763;heartbeat gateway/run.py:18807;/status gateway/slash_commands.py:558 |
| `_is_goal_continuation_event` 等 | 模板 hermes_cli/goals.py:90-147;GoalManager.is_active(hermes_cli/goals.py);gateway/slash_commands.py:2636/2654;drain gateway/run.py:25692 |
| `_update_runtime_status`/`_persist_active_agents` | gateway/status.py:980 write_runtime_status(`_UNSET` merge) |
| 外部 drain 三函数 | gateway/drain_control.py:210 drain_requested(epoch,NS-570) |
| `_pause/_resume_paused_platform` | `_failed_platforms`(reconnect watcher 段);status.py platforms 子字典 |
| `_resolve_model_for_channel` | hermes_cli/model_switch.py:760 resolve_effective_model;`_get_channel_override`;`_resolve_gateway_model` |
| `_load_reasoning_config` | hermes_constants.py:1099 resolve_reasoning_config |
| fallback 链三函数 | hermes_cli/fallback_config.py:80 get_fallback_chain;hermes_cli/config.read_user_config_raw;managed_scope.apply_managed_overlay;agent `_fallback_*` 字段 |
| `_claim_active_session_slot` | hermes_cli/active_sessions.py:56/99/271;调用点 gateway/run.py:15672 |
| `_agent_has_active_subagents` | run_agent.py:3150-3159(interrupt 级联);agent/agent_init.py(_active_children 初始化) |
| `_session_has_compression_in_flight` | session_store 私有锁;`_session_db._db.get_compression_lock_holder` |
| `_queue_or_replace_pending_event` | gateway/platforms/base.py:2438 merge_pending_message_event |
| `_prepare_busy_steer_text` | gateway/run.py:21706 `_pending_event_audio_paths`;gateway/run.py:21786 `_transcribe_and_echo_pending_voice` |
| busy 总入口 | 注册 gateway/run.py:11096/12468/13410 → base.py:3345/5711;tools/approval.py:2526;gateway/slash_commands.py:5377/5435;run_agent.py:3028/3229/3265/4001;agent/onboarding.py:26/36/211/216;gateway/display_config.resolve_display_setting |

---

## 21. 文档-代码冲突候选(▲=冲突,◇=表述不完整/易误导)

**▲21-1 `website/docs/developer-guide/gateway-internals.md:86 @ 863e313`(双层守卫 Level 1)**
> "Level 1 — Base adapter …: Checks `_active_sessions`. If the session is active, queues the
> message in `_pending_messages` and sets an interrupt event."

代码:adapter 命中活跃会话后**首先回调 runner 的 busy handler**(base.py:5711-5716),排队只是
handler 返回 False/未注册时的兜底;且兜底路径是 merge/防抖(base.py:5721-5747),**不设任何
interrupt event** —— interrupt 决策完全在 runner 侧(gateway/run.py:9003-9024)。"sets an interrupt
event"描述的是早已不存在的旧机制。

**▲21-2 `gateway-internals.md:88`(Level 2)**
> "Everything else triggers `running_agent.interrupt()`."

代码:interrupt 只是 `busy_input_mode` 三态之一(默认),之上还有:queue/steer 模式(8884-8961)、
redirect 优先(8962-8976)、subagents 自动降级 #30170(8905-8915)、压缩自动降级 #56391
(8916-8926)、internal 事件绝不打断(8878-8879)、审批词路由(8787-8860)、draining 分流
(8759-8785)。"everything else → interrupt" 与实现相差一整个决策树。

**◇21-3 `gateway-internals.md:88/132` 的 bypass 命令清单**
文档列 `/stop /new /queue /status /approve /deny`;代码真源是 `hermes_cli/commands.py` 的
`busy_policy` 注册表(75-95、105-173):`dispatch` 档还包括 /background /steer /goal /heartbeat
/subgoal /agents /start 等,/new /stop 是 `interrupt_then_dispatch`,/moa 是带专用文案的
`reject`。文档清单既不完整也没体现三档策略。

**◇21-4 `gateway-internals.md:59-61`(Message Flow 第 2 步)**
"If agent is running for this session → queue message, set interrupt event" —— 同 21-1,
漏掉 busy handler 委托这一层,把三处逻辑(adapter 兜底、busy handler、PRIORITY path)压扁成
一句过时描述。

**(代码内部发现,非文档冲突,归入定案)** gate-failed goal continuation 模板
(`hermes_cli/goals.py:134`)逃逸 `_is_goal_continuation_event` 前缀(gateway/run.py:7753),
pause/clear 摘除与 drain 新鲜度复核对它均失效(§2)。

---

## 22. 覆盖清单(7691–9184 全部成员)

| 行号 | 成员 | 小节 |
|---|---|---|
| 7691-7703 | `_enqueue_fifo` | §1 |
| 7705-7734 | `_promote_queued_event` | §1 |
| 7736-7742 | `_queue_depth` | §1 |
| 7744-7753 | `_is_goal_continuation_event` | §2 |
| 7755-7780 | `_clear_goal_pending_continuations` | §2 |
| 7782-7791 | `_goal_still_active_for_session` | §2 |
| 7793-7803 | `_update_runtime_status` | §3 |
| 7805-7825 | `_persist_active_agents` | §3 |
| 7837-7855 | `_enter_external_drain` | §4 |
| 7857-7879 | `_exit_external_drain` | §4 |
| 7881-7911 | `_drain_control_watcher` | §4 |
| 7913-7930 | `_update_platform_runtime_status` | §5 |
| 7937-7973 | `_pause_failed_platform` | §5 |
| 7975-7999 | `_resume_paused_platform` | §5 |
| 8001-8033 | `_load_prefill_messages` | §6 |
| 8035-8046 | `_load_ephemeral_system_prompt` | §6 |
| 8048-8083 | `_resolve_model_for_channel` | §7 |
| 8085-8111 | `_get_system_prompt_for_channel` | §7 |
| 8113-8128 | `_load_reasoning_config`(#21256) | §8 |
| 8130-8154 | `_parse_reasoning_command_args` | §8 |
| 8156-8183 | `_resolve_session_reasoning_config` | §8 |
| 8185-8198 | `_set_session_reasoning_override` | §8 |
| 8200-8226 | `_resolve_session_service_tier` | §9 |
| 8228-8247 | `_set_session_service_tier_override` | §9 |
| 8249-8266 | `_load_service_tier` | §9 |
| 8268-8275 | `_load_show_reasoning` | §10 |
| 8277-8288 | `_load_busy_input_mode` | §10 |
| 8290-8312 | `_load_busy_text_mode` | §10 |
| 8314-8331 | `_load_restart_drain_timeout` | §11 |
| 8333-8354 | `_load_restart_after_turn_timeout`(#77184) | §11 |
| 8356-8382 | `_load_background_notifications_mode` | §12 |
| 8384-8394 | `_load_provider_routing` | §13 |
| 8396-8413 | `_load_fallback_model` | §13 |
| 8415-8460 | `_refresh_fallback_model`(#60955) | §13 |
| 8462-8496 | `_apply_fallback_chain_to_agent`(#60955) | §13 |
| 8498-8503 | `_snapshot_running_agents` | §14 |
| 8505-8512 | `_get_max_concurrent_sessions` | §14 |
| 8514-8526 | `_active_session_limit_message` | §14 |
| 8528-8555 | `_claim_active_session_slot` | §14 |
| 8557-8593 | `_agent_has_active_subagents`(#30170) | §15 |
| 8595-8647 | `_session_has_compression_in_flight`(#56391/#23975/#5) | §16 |
| 8649-8656 | `_lookup_session_id_under_store_lock` | §16 |
| 8658-8664 | `_BUSY_QUEUE_MAX_PENDING` 注释+常量 | §17 |
| 8666-8703 | `_queue_or_replace_pending_event`(#28503) | §17 |
| 8705-8740 | `_prepare_busy_steer_text`(#58780) | §18 |
| 8742-9182 | `_handle_active_session_busy_message`(#17775/#46866/#30170/#56391/#58780/#43066) | §19 |
| 9184- | `_drain_active_agents`(仅起始行,属下一段) | 不在本段 |
