# r7 底稿 · gateway/run.py 第 7 段(16276–18967)—— `_handle_message_with_agent` 回合编排核心

> 溯源约定:`gateway/run.py:行号 @ 863e313`,引用为基线 commit 863e31318553cda8ad61df681d08175364d4164b 的逐字摘录。
> 本段主体是 `_handle_message_with_agent`(16276–18293,约 2019 行),之后是一组配套方法
> (`_reset_notice_session_info`、`_format_session_info`、`_check_slash_access`、`_sibling_thread_run_keys`、
> `_is_stale_restart_redelivery`、suggestions/blueprint 命令、goal/heartbeat 管理、goal 续跑)直到 18967。
>
> **与任务简报的出入(先记录)**:简报中"agent 获取/复用/新建(缓存判据)、TurnRunner/回调装配、跑回合"
> 并不在本段行区间内 —— 本段在 17548 调用 `self._run_agent(...)`,该方法定义在 `gateway/run.py:24112 @ 863e313`
> (`_run_agent_inner` 在 24265),属于后续段。本段负责的是**回合前编排**(会话解析→租约→hygiene→上下文装配)
> 与**回合后收尾**(结果归一→持久化→缓存再基线→媒体/footer→异常兜底)。本段确实调用的缓存相关入口是
> `_evict_cached_agent`(23374)与 `_refresh_agent_cache_message_count`(23149),已在对应小节交代。

---

## 0. 段落总览与调用骨架

`_handle_message_with_agent` 是 gateway 收到一条平台消息后、真正跑 agent 的那条主干。它由
`_handle_message` 内层(见 `gateway/run.py:15691 @ 863e313`)在占住 `_running_agents` 哨兵、
分配 run generation 之后调用;返回后 `_handle_message` 做 goal 续跑判定(15713),并在 `finally`
里释放 running-agent 槽位与 turn lease(15739/15743)。

```python
# gateway/run.py:15690-15691 @ 863e313
        try:
            _agent_result = await self._handle_message_with_agent(event, source, _quick_key, _run_generation)
```

```python
# gateway/run.py:15740-15743 @ 863e313
            # Turn lease (#64934): release THIS turn's lease token — keyed by
            # (routing key, run generation) so this unwind can only ever free
            # the lease its own turn acquired, never a newer turn's.
            self._release_turn_lease(_quick_key, _run_generation)
```

方法内部阶段(行号均为本段实测):

| 阶段 | 行区间 | 内容 |
|---|---|---|
| A | 16276–16303 | 入站日志 + Telegram DM-topic thread_id 恢复 |
| B | 16305–16375 | 会话解析三步:get_or_create → 异步委托 pinning → topic 绑定 tip-walk + switch_session |
| C | 16376–16413 | auto-reset 一次性消费、会话边界清理、session:start hook |
| D | 16415–16446 | SessionContext 构建、task-local env、pinned context prompt、sidecar notes 容器 |
| E | 16450–16530 | auto-reset 系统注记 + 用户可见通知(含 continuity note) |
| F | 16532–16566 | topic/channel 绑定的 auto-skill 注入 |
| G | 16568–16593 | **turn lease 领取(#64934)** |
| H | 16595–17345 | 历史装载 + **session hygiene 预压缩**(本段最大机制) |
| I | 17347–17440 | 首消息 onboarding、home channel 一次性提示 |
| J | 17442–17518 | 语音频道 sidecar、入站消息预处理(vision)、时间戳元数据化 |
| K | 17517–17563 | sidecar 暂存、adapter generation 绑定、agent:start hook、调用 `_run_agent` |
| L | 17565–17600 | typing 停止、stale generation 结果丢弃 |
| M | 17602–17671 | 响应归一:hidden-reasoning 哨兵、`(empty)` 哨兵、intentional silence、空响应归一 |
| N | 17673–17705 | 压缩改名后的 session_id 同步(身份守卫 + 租约随迁) |
| O | 17707–17785 | reasoning 展示、runtime footer |
| P | 17787–17828 | agent:end hook、进程 watcher 派发、watch 事件 drain |
| Q | 17837–18083 | **transcript 持久化决策矩阵**(上下文溢出/瞬态失败/正常三分) |
| R | 18085–18176 | update_session、agent 缓存计数再基线、静默抑制、语音回复、already_sent 尾处理 |
| S | 18178–18290 | 异常路径:typing 清理、用户消息补写、状态码提示 |
| — | 18291–18293 | finally:恢复 session env contextvar |

之后的配套方法在 §12–§18。

---

## 1. 阶段 A/B —— 会话解析:三步定案,一处收口

### 1.1 问题

gateway 的路由键(routing key / quick_key)与持久会话(session_id)是**多对一**关系:
`/resume`、Telegram topic 绑定、压缩改名(compression rotation)、异步委托完成回投都会让
"键→id" 映射移动。会话解析必须在**一处**顺序完成,后续所有步骤(租约、装载、落盘)才有稳定对象。
相关事故:#20470/#29712/#33414(绑定指向压缩前父会话,反复重载超大 transcript)、
#55578/#57498(异步委托完成注入错会话)。

### 1.2 实现

**第一步:Telegram DM-topic thread_id 恢复**(lobby 形态的回复被钉回用户最近活跃的 topic):

```python
# gateway/run.py:16293-16299 @ 863e313
        recovered = await asyncio.to_thread(self._recover_telegram_topic_thread_id, source)
        if recovered is not None:
            logger.info(
                "telegram topic recovery: chat=%s user=%s %r -> %s",
                source.chat_id, source.user_id, source.thread_id, recovered,
            )
            source = dataclasses.replace(source, thread_id=recovered)
```

`_recover_telegram_topic_thread_id`(`gateway/run.py:6851 @ 863e313`)只改写 lobby 形态
(thread_id 为空或 General),**非 lobby 的未知 thread_id 保持不动** —— 那多半是新建 topic 的第一条消息,
改写会把新 topic 的回答劫持进旧 lane:

```python
# gateway/run.py:6874-6881 @ 863e313
        inbound = str(source.thread_id or "")
        is_lobby = not inbound or inbound in self._TELEGRAM_GENERAL_TOPIC_IDS
        if not is_lobby:
            # A non-lobby, unknown thread_id is most likely the first message in
            # a brand-new Telegram DM topic. Preserve it so it can be recorded
            # as a new independent lane below instead of hijacking the latest
            # existing topic binding.
            return None
```

**第二步:get_or_create + 异步委托 pinning**。事件 metadata 里带 `gateway_session_id`
(异步子代理完成后回投时钉的发起会话)则走 `_resolve_async_delegation_session`:

```python
# gateway/run.py:16305-16317 @ 863e313
        session_entry = await self.async_session_store.get_or_create_session(source)
        session_key = session_entry.session_key
        pinned_session_id = str(
            (getattr(event, "metadata", None) or {}).get("gateway_session_id") or ""
        ).strip()
        if pinned_session_id:
            resolved_entry = await self._resolve_async_delegation_session(
                session_entry,
                pinned_session_id,
            )
            if resolved_entry is None:
                return
            session_entry = resolved_entry
```

`_resolve_async_delegation_session`(`gateway/run.py:13928 @ 863e313`)是 **fail-closed** 的谱系验证:
- 发起会话行不存在 → 丢弃注入(#55578);
- 发起会话已结束且 `end_reason != "compression"` → 丢弃(绝不复活被 /new 覆盖的会话);
- `end_reason == "compression"` → 沿 `get_compression_tip`(`hermes_state.py:5719 @ 863e313`)
  走到链尾 child,再验证当前路由确实拥有这条谱系(`gateway/run.py:14014-14033`:当前 session_id
  必须 ∈ {父, tip},或其自身 tip == 同一 target),否则丢弃;
- 通过后经 `advance_compression_session` / `switch_session` 正式换绑(14050–14059,#57498)。

**第三步:Telegram topic 绑定的 tip-walk 与 switch_session 收口**。绑定表若指向压缩前父会话,
先 tip-walk 到链尾,再**经 SessionStore 换绑**(而不是就地改 `session_entry.session_id`):

```python
# gateway/run.py:16352-16360 @ 863e313
                if bound_session_id and bound_session_id != session_entry.session_id:
                    # Route the override through SessionStore so the session_key
                    # → session_id mapping is persisted to disk and the previous
                    # lane session is ended cleanly. Mutating session_entry in
                    # place here created a split-brain state where the JSON
                    # index pointed at one id but code downstream used another.
                    switched = await self.async_session_store.switch_session(session_key, bound_session_id)
                    if switched is not None:
                        session_entry = switched
```

tip-walk 本身(16336–16351)注明治愈 #20470/#29712/#33414;走完后若绑定指向的是父,
还回写绑定(16363–16370,`reason="compression-tip-walk"`)。无绑定则记录新绑定(16371–16375)。

调用关系:`get_or_create_session` → `gateway/session.py:2291 @ 863e313`(AsyncSessionStore
1189 是 to_thread 包装,SessionStore 1206 是同步实现);`switch_session` → `gateway/session.py:2993`,
其中对旧会话做 `promote_to_session_reset(db_end_session_id, "session_switch")`
(session.py:3034–3042)防止陈旧 end 事件复活覆盖用户的 /resume 选择(#61220 类)。

### 1.3 设计理由与取舍

- **解析集中在方法头部、一次定案**:后面的 turn lease 注释(16568)明确写 "Session resolution
  is FINAL here" —— 租约按解析后的 session_id 上锁才有意义。
- **一切换绑走 SessionStore**:磁盘 JSON 索引与内存对象保持一致,避免 split-brain(16352 注释)。
- **异步委托 fail-closed**:宁可丢注入(结果仍留在 delegation 记录里可查),不冒错投风险。
- 取舍:三步解析每条消息都要走(含两次 to_thread + 可能多次 DB 查),换取正确性;tip-walk
  对非压缩父会话是 O(1) 原样返回("cheap and safe",16334–16335)。

### 1.4 重实现要点

1. 路由键与持久会话 id 分离时,必须有单点"解析收口",且所有换绑操作走同一持久化通道。
2. 压缩改名要留"父→子"链(end_reason=compression + tip 查询),所有指向父的外部引用(绑定表、
   委托回投)读取时 walk 到 tip 并回写。
3. 异步完成回投必须做谱系所有权验证,验证不过 fail-closed 丢弃,不 fallback 到"当前会话"。
4. lobby 形态的路由缺失可以用"最近活跃绑定"恢复,但未知且非 lobby 的新 lane 必须保留。

---

## 2. 阶段 C —— auto-reset 的一次性消费与会话边界

### 2.1 问题

会话被后台自动重置(idle/daily/suspended)后,第一条新消息需要:清掉上一段会话的所有
per-session 覆盖(/model、/reasoning 等),驱逐缓存 agent(防压缩摘要泄漏旧历史),
并且这些清理**只发生一次** —— 否则后续消息反复触发,把用户在两回合之间新设的覆盖也清掉(#48031)。

### 2.2 实现

```python
# gateway/run.py:16379-16395 @ 863e313
        _was_auto_reset = getattr(session_entry, "was_auto_reset", False)
        if _was_auto_reset:
            # Treat auto-reset as a full conversation boundary — clear every
            # conversation-scoped per-session dict in one funnel call so the
            # fresh session does not inherit the previous conversation's
            # model/reasoning overrides, a queued "/model switched" note, or
            # a stale resolved-model cache (#48031, #58403). See
            # _CONVERSATION_SCOPED_STATE.
            self._clear_conversation_scope(session_key, reason="auto_reset")
            # Evict the cached agent so the fresh session does not inherit the
            # previous conversation's context_compressor._previous_summary —
            # the cache is keyed on the stable session_key, so an auto-reset
            # otherwise reuses the old agent and leaks prior history into new
            # compaction summaries. Mirrors /reset and the compression-exhausted
            # path (#9893). Covers daily/idle/suspended auto-reset.
            self._evict_cached_agent(session_key)
            session_entry.was_auto_reset = False
```

- `_clear_conversation_scope`(`gateway/run.py:22917 @ 863e313`)是**唯一的会话边界漏斗**:
  历史上每个边界各自维护手抄 pop-list,新增字典后清单漂移,#48031/#58403/#10702/#35809
  全是"边界 X 忘了字典 Y"型 bug;现在结构化 `state.conversation.clear()` 一次清完。
- `is_fresh_reset` 同样一次性消费(16403–16406,#6508),并与 `created_at == updated_at`、
  `_was_auto_reset` 共同判定 `_is_new_session`,触发 `session:start` hook(16407–16413)。

### 2.3 重实现要点

1. 一次性标志(was_auto_reset / is_fresh_reset)读取即清零,单一消费点。
2. 会话边界清理做成漏斗函数 + 声明式字段清单,禁止各调用点手抄 pop-list。
3. agent 缓存按稳定 key 缓存时,任何会话边界都必须显式驱逐,否则压缩器内部状态
   (`_previous_summary`)跨会话泄漏。

---

## 3. 阶段 D —— pinned context prompt 与 sidecar notes:保卫 prompt cache

### 3.1 问题

每回合注入的"会话上下文提示"(平台、chat 名、home channel 等)如果每次重渲染,
渲染器的任何非确定性都会让系统提示逐回合漂移 → agent 缓存判定为"系统提示变了" → 重建 agent
→ provider 端 prompt cache(前缀缓存)全废。同理,"仅本回合必须送达"的注记若追加进系统提示,
turn1 有 / turn2 无本身就是一次必然的 diff。

### 3.2 实现

```python
# gateway/run.py:16431-16439 @ 863e313
        # Build the context prompt to inject.  The render is pinned per
        # session, keyed by a hash of the exact renderer inputs
        # (_ephemeral_change_key).  A key hit reuses the pinned bytes verbatim
        # so the composed system prompt cannot drift turn-over-turn; a key
        # miss (thread rename, /sethome, redact_pii flip, ...) re-renders
        # once — the only legitimate cache busts.
        context_prompt = self._pinned_session_context_prompt(
            context, _redact_pii, session_key
        )
```

`_pinned_session_context_prompt`(`gateway/run.py:23270 @ 863e313`)按
`_ephemeral_change_key`(23295,对渲染输入元组做 sha256;维护不变式:任何会改变渲染字节的输入
必须进 key,由 `tests/gateway/test_prompt_tail_freeze.py` 的 parity test 守护)命中即逐字复用。

sidecar notes(16442–16446):auto-reset 注记、onboarding、VC 状态等"一次性注记"改走
**当前用户消息的 api_content 边车**,在 `run_sync → build_turn_context` 消费,不再碰系统提示:

```python
# gateway/run.py:17513-17518 @ 863e313
        # Stage the collected must-deliver notes for this turn's agent run
        # (one-shot; consumed in run_sync).  Staged AFTER the message_text
        # early-out above so an aborted turn cannot leak its notes into the
        # next turn's user message.
        if turn_sidecar_notes and session_key:
            self._set_pending_turn_sidecar_notes(session_key, turn_sidecar_notes)
```

暂存/消费:`_set_pending_turn_sidecar_notes`(23224)写入
`SessionState.conversation.sidecar_notes`,`_consume_pending_turn_sidecar_notes`(23230)读后清空。
语音频道注记 `_voice_channel_sidecar_note`(23240)只在 VC 状态**变化**时返回注记
(含"离开频道"),不变则 None —— 因为成员/发言序列化几乎每回合都不同,进系统提示等于每条消息
重建 agent + 重新 key prompt cache(17442–17451 注释)。

### 3.3 重实现要点

1. 系统提示中的"环境快照"要 pin 住字节,cache key = 渲染输入哈希;渲染函数的非确定性由 pin 隔离。
2. key 的字段集合与渲染输入之间要有 parity 测试守护(漏字段=陈旧,多字段=多余重渲染,前者更糟)。
3. 一次性注记走用户消息边车,绝不进系统提示;暂存必须在"回合确定会跑"之后(early-out 之后)才落位。
4. 高频变化的环境状态(VC 成员)以"变化才注入"的差分方式送达,系统提示只留静态指针行。

---

## 4. 阶段 E/F —— auto-reset 通知与 auto-skill 注入

**auto-reset 系统注记**(16450–16471):按 `auto_reset_reason`(suspended/daily/
resume_pending_expired/idle)生成不同的 `[System note: ...]`,并对 Slack/Discord 这类长活频道
追加 `build_channel_continuity_note`(`gateway/session.py:977 @ 863e313`)—— 指向**同频道**
上一段会话,让 agent 用 session_search 找回上下文而不是翻到无关的最近会话;确定性、零额外
API/DB 调用(#36220,16460–16464 注释)。注记进 sidecar,不进系统提示。

**用户可见通知**(16477–16526):suspended / resume_pending_expired **无条件通知**
(用户的活跃会话被静默替换,必须告知可 /resume);idle/daily 尊重 `policy.notify` 且要求
`reset_had_activity`(空会话不打扰):

```python
# gateway/run.py:16484-16492 @ 863e313
                had_activity = getattr(session_entry, 'reset_had_activity', False)
                # Suspended and restart-recovery-expired sessions always notify
                # regardless of policy.notify — the user had an active session
                # that was silently replaced, so they need to know they can
                # /resume it.  Idle/daily resets respect the policy flag.
                should_notify = reset_reason in {"suspended", "resume_pending_expired"} or (
                    policy.notify
                    and had_activity
                    and platform_name not in policy.notify_exclude_platforms
                )
```

通知里附 `_reset_notice_session_info`(见 §12)的模型/上下文信息块;整段 try/except 包裹,
通知失败不影响回合(16525–16526)。

**auto-skill**(16536–16566):topic/channel 绑定的技能只在 `_is_new_session` 时注入 ——
老会话的历史里已经有技能内容,重复注入只涨上下文。支持单名或有序列表,把技能 payload 拼在
用户原文**之前**(16557–16560),加载失败仅告警。

重实现要点:重置通知按"用户是否会被惊讶"分级(静默替换必须通知);技能注入以会话为幂等单位;
continuity 提示要确定性可再生,不引入额外 IO。

---

## 5. 阶段 G —— turn lease(#64934):按 session_id 串行化 [装载→跑→落盘]

### 5.1 问题(#64934)

busy 守卫都按**路由键**记账(adapter `_active_sessions`、runner `_running_agents`),
但 transcript 归 **session_id** 所有,而 `switch_session` 使键→id 多对一(第二个聊天 /resume
同名会话、CLI 连续性换绑、异步委托 pinning、topic tip-walk)。两个路由键映到同一 session_id 时,
两回合在两个 agent 对象上并发跑,任何 per-key 守卫都看不到冲突;落盘按完成序而非到达序交织,
身份标记去重还可能整行吞掉,第二回合的历史基线没见过第一回合 → transcript 留下永久的
`user;user` 交替楔子,`repair_message_sequence` 每次请求都在重修(`gateway/turn_lease.py:3-15 @ 863e313`)。

### 5.2 实现

领取点在会话解析定案之后、`load_transcript` 之前:

```python
# gateway/run.py:16582-16593 @ 863e313
        _lease_registry = getattr(self, "_turn_leases", None)
        if _lease_registry is not None:
            _lease_token = await _lease_registry.acquire(
                session_entry.session_id,
                owner_key=_quick_key,
                generation=run_generation,
                timeout=_float_env("HERMES_AGENT_TIMEOUT", 1800),
            )
            if _lease_token is not None:
                _lease_state = self._session_state(_quick_key).turn
                _lease_state.lease_token = _lease_token
                _lease_state.lease_generation = run_generation
```

注册表在构造器初始化(`gateway/run.py:6000 @ 863e313`
`self._turn_leases = SessionTurnLeaseRegistry()`);token 存进
`SessionState.turn.lease_token / lease_generation`(`gateway/session_state.py:74-75 @ 863e313`,
注释明确这两个字段**不**由 `TurnState.clear()` 清理,归 dispatch finally 所有,52–76)。

`SessionTurnLeaseRegistry`(`gateway/turn_lease.py:115 @ 863e313`)的安全性质(9–47 模块注释):

- **acquire**(154–213):同 id 已被持有 → WARNING 点名两把路由键并排队等待;等待超时
  (默认与 agent 不活动超时同刻度 1800s,66)→ **fail-open**,返回 `degraded=True` 的 token,
  本回合不串行化地照跑("never a wedged session"),ERROR 说明写交织风险(192–208)。
- **release**(274–302):幂等 + 身份校验 —— 只有"当前 holder 恰是这枚 token"才真正放锁,
  陈旧 unwind 永远放不掉新回合的租约(#28686 的所有权教训,29–33)。
- **rebind**(215–272):压缩中途改名时把**同一把锁对象**登记到新 id 下(旧映射闲置后被逐),
  两个 id 的竞争者串到同一把锁;只有当前 holder 能 rebind;若目标 id 已有活租约则拒绝并大声记日志
  (fail-open,不合并两个串行化域,250–267)。
- **容量**(61,139–152):上限 512,只逐"无 holder 无 waiter"的闲置项,活租约永不被逐
  ("correctness beats the cap")。

释放在 `_handle_message` 的 finally(15743)经 `_release_turn_lease`(22859):按
(routing key, generation) 取 token,先摘下再调 `registry.release`;generation 不符直接 False:

```python
# gateway/run.py:22876-2883 @ 863e313
        turn = state.turn
        if turn.lease_token is None or turn.lease_generation != run_generation:
            return False
        token = turn.lease_token
        turn.lease_token = None
        turn.lease_generation = None
        try:
            return registry.release(token)
```

租约随改名迁移的两个调用点:hygiene 改名(17172–17174)与 agent 结果改名(17684–17686),
经 `_rebind_turn_lease`(22888)。

已知边界(`gateway/turn_lease.py:40-47`):CLI 进程经 CLI-连续性共享会话在任何进程内锁之外
(需要 DB 级租约,另行设计);进程内、单事件循环可见域与被它扩展的路由键守卫一致(117–121)。

### 5.3 设计理由与取舍

- **为什么锁 session_id 而不是加强 per-key 守卫**:冲突本质是"多键一 id",任何 key 维度守卫
  结构性看不见;同键消息根本到不了领取点(adapter+runner 双守卫拦住),所以锁在非别名路径上
  **零竞争**(16574–16576 注释)。
- **为什么 fail-open**:楔死会话比偶发写交织更糟;超时刻度对齐回合自身的"卡死"判定。
- **为什么 generation 入 token**:/stop、/new 会 bump generation,旧回合 unwind 时只可能
  释放自己那代的租约。

### 5.4 重实现要点

1. 串行化边界要选在"资源身份最终确定"之后(解析收口后、装载前),并覆盖到落盘完成(dispatch finally)。
2. 锁 token 记 (owner, generation),释放走身份校验 + 幂等;绝不允许陈旧 unwind 释放新持有者。
3. 超时 fail-open + 大声 ERROR,并把降级状态记在 token 上使其 release 成为 no-op。
4. 资源 id 中途轮换时,用"同一锁对象登记到新 id"实现租约随迁,而不是搬 asyncio 内部状态。
5. 注册表容量控制只逐闲置项;正确性优先于上限。

---

## 6. 阶段 H —— session hygiene 预压缩(16595–17345):回合前的安全网

### 6.1 问题(#628、#2153、#74136、#76354、#79624 等)

长活 gateway 会话的 transcript 会长到"每条新消息都要重放超大历史",反复触发截断/上下文失败
(#628)。更糟的死亡螺旋:API 断连 → 拿不到 token 数据 → 不触发压缩 → 更大的请求 → 更多断连
(#2153)。所以在 agent 启动**之前**检测并主动压缩。

### 6.2 触发判定

历史 ≥4 条才考虑(16613)。阈值有意**高于** agent 自身压缩器(0.85 vs 0.50):hygiene 是
两回合之间长过头的安全网,agent 自己的压缩器拿着精确 token 数在工具循环里做常规管理;
hygiene 曾设 0.50,导致长会话每回合都提前压缩(16619–16632 注释)。配置解析(16642–16766)
依次读 model/compression 配置、经 `_resolve_session_agent_runtime`(6933)解析运行时、
`should_clear_context_pin_async` 判定 context_length pin 是否随路由变化失效、custom_providers
的 per-model context_length 兜底;idle 超时 30s、总上限 600s(且 clamp 到 ≥ 单个 idle 窗口,
16695–16699,否则延长循环成死代码)、失败冷却 300s。

token 来源优先级与硬上限:

```python
# gateway/run.py:16785-16791 @ 863e313
                _stored_tokens = session_entry.last_prompt_tokens
                if _stored_tokens > 0:
                    _approx_tokens = _stored_tokens
                    _token_source = "actual"
                else:
                    _approx_tokens = estimate_messages_tokens_rough(history)
                    _token_source = "estimated"
```

粗估会高 30–50%,但只是提前触发,无害;历史上曾用 1.4x 乘数补偿,结果 85%*1.4=119% 超过模型上限,
~200K 模型(GLM-5)永远触发不了(16792–16798 注释,教训)。消息数硬阀 5000(可配)兜住
"拿不到 token 数据"的死亡螺旋(#2153,16800–16816)。

**持久化冷却**:触发后先查 DB 里的压缩失败冷却(与 agent 内压缩路径同一张表),内存 dict 会随
重启清零、反复触发同一个失败压缩把会话存储楔死(#74136):

```python
# gateway/run.py:16833-16840 @ 863e313
                            if _cooldown_state and _cooldown_state.get("remaining_seconds", 0) > 0:
                                logger.info(
                                    "Session hygiene: skipping compression for %s; "
                                    "previous failure cooldown active for %.1fs",
                                    session_entry.session_id,
                                    _cooldown_state["remaining_seconds"],
                                )
                                _needs_compress = False
```

### 6.3 hygiene agent 的构建

喂给压缩器的是**全量 transcript(含 tool 行)** —— 只滤 user/assistant 曾把压缩器饿死:
tool 结果才是上下文大头,`_prune_old_tool_results` 看不到它们,短的过滤历史还会踩
protect-first/last 提前返回,结果什么都没压(#3854,16864–16876 注释)。

```python
# gateway/run.py:16895-16912 @ 863e313(节选)
                                _hyg_agent = AIAgent(
                                    **_hyg_runtime,
                                    model=_hyg_model,
                                    max_iterations=4,
                                    quiet_mode=True,
                                    skip_memory=True,
                                    enabled_toolsets=["memory"],
                                    session_id=session_entry.session_id,
                                    session_db=_hyg_session_db,
                                )
                                _seed_hygiene_system_prompt(
                                    _hyg_agent,
                                    _hyg_session_row,
                                )
                                # If compression must rebuild instead of retaining
                                # the cached prompt, make the persisted result
                                # deliberately stale for every real gateway surface.
                                _hyg_agent.platform = _GATEWAY_HYGIENE_PLATFORM
```

- `_seed_hygiene_system_prompt`(`gateway/run.py:465 @ 863e313`):hygiene agent 跳过 memory
  provider 初始化,若让压缩顺带持久化一个重建的系统提示,会把外部 provider 块从活会话里剥掉;
  所以**seed 持久化过的原提示**,取不到就 seed 空串。
- `_GATEWAY_HYGIENE_PLATFORM = "gateway_hygiene"`(run.py:88):万一压缩重建了提示,平台标记
  让所有真实 surface 都视其为陈旧,真实回合会用完整初始化的 provider 重建。
- `compression_in_place = True`(16924):hygiene 跑在用户回合之前、已拥有会话绑定,优先
  就地压实(同 id 下归档旧行)而不是铸继续 child 再回publish 给 SessionStore/topic 绑定。
- `_end_session_on_close = False`(16937):close() 绝不能终结活的 gateway 会话行。

### 6.4 进度感知等待(#76354)

压缩跑在 executor 线程,等待策略是 **idle 预算而非总预算**:worker 流式生成摘要、每 token 调
`CompressionCommitFence.touch_progress`(`agent/conversation_compression.py:491 @ 863e313`),
慢而不停的推理模型不断续期;总上限兜住"退化的涓流"。#76354 S3 的修正:每片等待额度按
"距上次进度"扣减,否则静默可以逼近 2x 配置超时:

```python
# gateway/run.py:16963-16997 @ 863e313(节选)
                                        while True:
                                            _slice = max(
                                                _hyg_timeout_seconds
                                                - _hyg_commit_fence.seconds_since_progress(),
                                                0.005,
                                            )
                                            try:
                                                _compressed, _ = await asyncio.wait_for(
                                                    asyncio.shield(_hyg_future),
                                                    timeout=_slice,
                                                )
                                                break
                                            except asyncio.TimeoutError:
                                                _hyg_waited = time.monotonic() - _hyg_wait_started
                                                _idle = _hyg_commit_fence.seconds_since_progress()
                                                if (
                                                    _idle < _hyg_timeout_seconds
                                                    and _hyg_waited < _hyg_total_ceiling_seconds
                                                ):
                                                    ...
                                                    continue
                                                raise
```

真超时后的取消协商(16999–17032):`try_cancel_before_commit`(conversation_compression.py:521)
在 commit 边界前抢占;`commit_in_flight`(575)是无锁相位标记,防止挂死的 commit 抱着 fence 锁
让本循环空转(F1);取消失败=worker 恰在超时前跨过 commit 边界 → **消费完成结果**而不是把成功
压实当超时(17018–17024);取消成功 → `release_cancelled_compression_lock`(678,holder 限定、
无 ABA)立刻释放持久压缩锁(F4),`_defer_agent_cleanup_until_future_done`(run.py:9558)把
agent 清理挂到脱缰 future 完成之后,记冷却、盖 provenance 戳、给用户发可见超时警告(17070–17093)。
非超时 unwind(KeyboardInterrupt/取消)先 `revoke_commit_admission`(591)再抛,保证脱缰 worker
永远无法事后 commit(17094–17111,F2)。

### 6.5 结果三态与"写前不换绑"

```python
# gateway/run.py:17117-17121 @ 863e313
                                    _hyg_new_sid = _hyg_agent.session_id
                                    _hyg_rotated = _hyg_new_sid != session_entry.session_id
                                    _hyg_in_place = bool(
                                        getattr(_hyg_agent, "_last_compaction_in_place", False)
                                    )
```

- **rotated**(改名铸 child):先 `rewrite_transcript(new_sid, compressed)`
  (`gateway/session.py:3357 @ 863e313`)**写成功后**才 `session_entry.session_id = new_sid`、
  `_rebind_turn_lease`、`_save()`、同步 topic 绑定(17150–17180)。写失败 → fail closed 当作
  没改名,活 entry 留在原会话,对话不丢(17154–17165)。"write-before-repoint" 镜像手动
  /compress 的修法:先换绑再写失败 = 活 entry 指向全新空会话,对话静默消失(17143–17149 注释)。
- **in_place**:`archive_and_compact()` 已在 `_compress_context` 内部完成归档+压实,**绝不能**
  再 `rewrite_transcript` —— 那会走 `replace_messages(active_only=False)` 把归档行也全删
  (静默数据丢失,#61145;17122–17132 注释)。
- **两者皆非**:失败态。无条件 rewrite 会把原始消息删光只留摘要(永久数据丢失,#21301;
  镜像 /compress 的 #44794/#39704 修法),所以保留原 transcript、计数沿用压缩前值并 WARNING
  (17200–17213)。

### 6.6 冷却阶梯与恢复判定(#79624)

成功与否不能只看数字:失败态复用压缩前计数,"数字没变"会被误读为成功、每次楔死运行都清零连败。
判定提取成可单测的纯函数:

```python
# gateway/run.py:222-228 @ 863e313
    if aborted:
        return False
    if not (rotated or in_place):
        return False
    return compression_made_progress(
        msg_count, new_count, approx_tokens, new_tokens
    )
```

(`hygiene_compaction_recovered`,run.py:187;docstring 187–221 说明 token 比较必须走共享的
`compression_made_progress`:approx 可能是 provider 实报而 new 永远是粗估,裸 `<` 既漏真赢也把
噪声当赢;#39548。)恢复则 `_reset_hygiene_failure_streak`(173)。

失败冷却是 **x1/x3/x9 乘数阶梯**(`_hygiene_cooldown_for_failure`,run.py:135):agent 内的
绝对阶梯(60→300→900)对 hygiene 结构性不可达 —— hygiene 每次新建 AIAgent、`bind_session_state`
把内存连败计数清零,永远只record 平坦冷却(#79624);连败改存 `PersistentState` 跨 agent 存活。
落库走 `_record_hygiene_cooldown`(231):与 agent 内路径同列
`compression_failure_cooldown_until`(#74136),error 参数必须转发,否则把 in-conversation
路径记的原因 clobber 成 NULL(244–248)。

### 6.7 abort 与 aux 模型回退的用户可见性

- 压缩器 abort(未产出摘要,原样返回,零丢失):记冷却 + provenance 戳
  (`AGENT_COMPRESSION_COOLDOWN`)+ **强制脱敏**(provider 异常文本可能含凭据,
  `redact_sensitive_text(_err, force=True)`,17289–17290)后把警告直接发进聊天 ——
  agent.log 在 TG/Discord 上不可见,用户需要知道会话"冻结"在当前尺寸,可 /compress 重试或
  /reset(17229–17307)。
- 配置的 auxiliary.compression 模型失败、静默回退主模型成功:仍单独通知(只有用户能修配置,
  静默恢复会藏住问题,17308–17331)。

finally(17332–17340):驱逐缓存 agent(下一回合按当前 SOUL.md/memory/skills 重建系统提示);
清理未被 defer 时 off-loop 释放 hygiene agent 资源。整个 hygiene 大块再包一层
`except Exception: logger.warning`(17342–17345)—— hygiene 永不阻断回合。

### 6.8 重实现要点

1. 回合前安全网与回合内常规压缩要**双阈值分离**(0.85 vs 0.50),职责不同;安全网只兜"两回合之间长过头"。
2. token 判定优先用上一回合 API 实报,粗估只做保守回退;另设与 token 无关的消息数硬阀断死亡螺旋。
3. 失败冷却必须持久化(DB),且带乘数阶梯;连败计数放在比 worker 生命周期更长的层。
4. 长任务等待用"进度感知 idle 预算 + 总上限";取消要与 commit 边界协商(可取消/已跨界/挂死三态),
   任何 unwind 路径先撤销 commit 准入。
5. 压缩结果三态(rotated/in_place/failure)各自的持久化动作严格互斥;改名遵循 write-before-repoint;
   串行化租约随改名迁移。
6. 压缩失败/回退对用户可见(发进聊天),错误文本强制脱敏。

---

## 7. 阶段 I/J —— onboarding、home channel、消息预处理

- **首消息 onboarding**(17351–17386):`not history and not has_any_sessions()`
  (`gateway/session.py:2269`)才触发,即"这台安装的第一条消息"。默认注入简短自我介绍 sidecar;
  可选 profile-build 路径(onboarding.profile_build=ask 且未 offered)换成征询式建档指令,
  `mark_seen` 落盘保证**至多 offer 一次**。注释再次强调走 sidecar 不走系统提示(17347–17350):
  turn1 有/turn2 无 = 必然的提示 diff + agent 重建。
- **home channel 一次性提示**(17390–17440):新会话且平台非 LOCAL/WEBHOOK、且从
  secret scope → os.environ → yaml → 次级 profile 配置四层都查不到 home channel 时,发一条
  "输入 /sethome 把本聊天设为 home"的提示。Slack 特判为 `/hermes sethome`(裸 `/sethome`
  未注册,会报 "app did not respond",17424–17432)。
- **消息预处理**(17468–17475):`_prepare_profile_scoped_inbound_message_text`(16186)
  处理附件(图片走 vision 工具急切生成文字描述,附本地路径供后续 vision_analyze 复查;
  按 media_type 过滤非图片),返回 None 则整回合放弃。
- **时间戳元数据化**(17483–17511):无条件剥离消息前缀时间戳、把事件时间存成 metadata
  (persist_user_message / persist_user_timestamp),**只有渲染**(模型看到的前缀)受
  `gateway.message_timestamps.enabled`(默认关)控制 —— 存储永远干净、时间永远保留,展示可后悔。

重实现要点:一次性提示都要有持久化的 seen 标志;"存储干净 + 展示可配"分离;预处理返回 None
必须发生在 sidecar 暂存之前(17513–17516 注释:aborted 回合不得把注记泄漏给下一回合)。

---

## 8. 阶段 K/L —— 跑回合与陈旧结果丢弃

**回合发起**(17529–17563):emit `agent:start`(消息截断 500);记录
`_run_start_session_id`(供压缩后同步做身份守卫)与 monotonic 起点;调 `_run_agent`
(定义 24112,下一段),传入 message/context_prompt/history/source/session_id/session_key/
run_generation/回复锚点/channel_prompt/moa_config/persist_* /message_type。
`_bind_adapter_run_generation`(23049)先把本代 generation 写到 adapter 的 active-session
事件上,使延迟的 post-delivery 回调能被"注册它的那一代"释放。

**typing 停止**(17565–17584):优先 `_stop_typing_with_metadata`(Slack AI status 按
thread/workspace 定界,必须带与投递路径相同的路由 metadata),回退 `stop_typing`。

**陈旧结果丢弃**(17586–17600):跑完后若 generation 已不是当前代(期间被 /stop、/new bump),
整个结果弃掉,并弹掉本代注册的 post-delivery 回调(优先带 generation 的
`pop_post_delivery_callback`,回退直接 pop 字典):

```python
# gateway/run.py:17586-17600 @ 863e313(节选)
            if not self._is_session_run_current(_quick_key, run_generation):
                logger.info(
                    "Discarding stale agent result for %s — generation %d is no longer current",
                    _quick_key or "?",
                    run_generation,
                )
                _stale_adapter = self._adapter_for_source(source)
                if getattr(type(_stale_adapter), "pop_post_delivery_callback", None) is not None:
                    _stale_adapter.pop_post_delivery_callback(
                        _quick_key,
                        generation=run_generation,
                    )
                ...
                return None
```

`_is_session_run_current`(23041)读 `SessionState.persistent.run_generation` 比对。

重实现要点:每回合发起前绑定 generation;结果消费点统一做代际校验;被弃结果要连同其注册的
延迟副作用(回调)一起清理。

---

## 9. 阶段 M —— 响应归一:三种"空"与一种"故意的空"

1. **hidden-reasoning 哨兵**(17602–17610,#51628):重试耗尽的哨兵文本("Codex response
   remained incomplete after 3 continuation attempts")同时充当 final_response 与 error,
   若原样投递,同频道的 peer agent 会把它当成完整助手回合摄取。
   `_is_gateway_hidden_reasoning_incomplete_turn`(run.py:3530)判定:partial 且 error 含
   "remained incomplete after" 且 final 为空或仅回声哨兵 —— **任何真正不同的 final 文本都必须投递**。
2. **`(empty)` 哨兵**(17624–17629):模型历经 nudge/prefill/empty-retry/fallback 仍无可见
   内容的内部哨兵,转译成人话("模型处理工具结果后未返回响应……"),避免看起来像 bug。
3. **intentional silence**(17611–17617):`is_intentional_silence_agent_result`
   (gateway/response_filters)判定 [SILENT]/NO_REPLY;它**不是**空响应,是投递决策 ——
   transcript 照常持久化助手回合以保持交替,只抑制出站投递(18115–18125)。
4. **空响应归一**(17667–17671)`_normalize_empty_agent_response`(run.py:3445):
   - failed → 上下文类错误给 /compact 提示,否则截断 error 给重试提示(#18765);
   - interrupted 且 api_calls==0 → 消息根本没被处理(残留 /stop 中断旗,#44212),提示重发;
     interrupted 且做过工作 → 有意静默,放行;
   - api_calls>0 无文本 → partial 给"processing stopped",否则"completed but no response";
   - api_calls==0 且非 failed/interrupted/partial → post-/stop 代际竞态的静默丢弃模式(#31884),
     提示"上一回合仍在清理,请重发"。
   随后 `_sanitize_gateway_final_response`(run.py:699)做平台级清洗。

另:`_should_clear_resume_pending_after_turn`(run.py:3554)只在"真正成功完成"
(非 interrupted/failed/partial/error 且 completed≠False)时清 `clear_resume_pending`
(`gateway/session.py:2780`)与重启失败计数(17655–17663)—— 软中断可能伪装成正常空结果,
清了标记 = 重启自动恢复失去信号。

重实现要点:空响应必须分类归因(失败/中断/竞态/静默),各给可执行提示;"故意的静默"是投递层
概念,不改 transcript;恢复标记只被"确证成功"清除。

---

## 10. 阶段 N/O/P —— session_id 同步、展示装饰、回合后派发

**压缩后 session_id 同步**(17673–17705):agent 结果里的 session_id 与当前不同(agent 内压缩
改名)时,**身份守卫**:只有 `session_entry.session_id == _run_start_session_id`(期间没被
/new 等移动)才接受改名,随后 `_rebind_turn_lease` → `_save()` →
`_record_gateway_session_peer`(session.py:1986)→ 同步 topic 绑定;否则跳过并记日志
(17697–17705)—— 后写者是生命周期转换,不是压缩。

**reasoning 展示**(17707–17763):`_resolve_gateway_display_bool` 按平台解析 show_reasoning
(Mattermost 要求显式 per-platform opt-in —— 这是草稿文本不是正式答案);>15 行折叠;
样式 per-platform(Discord 默认 `-# ` subtext,另有 blockquote/code;code 样式要先
`escape_code_fences_for_display` 防内层 ``` 破坏外层围栏)。

**runtime footer**(17765–17785):默认关(display.runtime_footer.enabled=false);只加在
回合**最终**消息上;流式已投递正文时无法改已发送文本,改在 already_sent 分支尾发一条小消息
(18163–18173)。

**agent:end + watcher 派发**(17787–17828):emit `agent:end`;
`process_registry.pending_watchers` **原子摘批**(整体换新 list 而不是 clear(),防 yield 间隙
并发追加的 watcher 被 clear 吞掉,17797–17800),每个 watcher 起 task、每 100 个让出一次循环;
watch 事件从共享 completion_queue drain(`_drain_gateway_watch_events`,run.py:3410),
只注入 watch 型事件 —— 异步委托完成同乘此队列但归 boot 时启动的 `_async_delegation_watcher`
单一消费者所有(17812–17816)。

重实现要点:改名同步必须带"发起时快照"身份守卫;共享队列多消费者时按事件类型划分所有权;
批量摘取用 swap 而非 clear。

---

## 11. 阶段 Q/R —— transcript 持久化决策矩阵与缓存再基线

### 11.1 三分决策(17837–17890)

```python
# gateway/run.py:17861-17871 @ 863e313
            is_context_overflow_failure = agent_failed_early and (
                bool(agent_result.get("compression_exhausted"))
                or any(p in _err_str_for_classify for p in (
                    "context length", "context size", "context window",
                    "maximum context", "token limit", "too many tokens",
                    "reduce the length", "exceeds the limit",
                    "request entity too large", "prompt is too long",
                    "payload too large", "input is too long",
                ))
                or ("400" in _err_str_for_classify and len(history) > 50)
            )
```

- **上下文溢出失败**:什么都不写 —— 写入用户消息只会让会话更大、下条消息同样失败,死循环
  (#1630、#9893)。匹配词组刻意用多词短语,避免 "rate limit exceeded"/"invalid auth token"
  误中(17856–17860 注释,与 run_agent.py 的分类器一致)。
- **瞬态失败**(429/超时/5xx):**只写用户消息** —— 会话没超限,静默丢弃用户消息会让 agent
  重试时忘了刚才被问什么(#7100)。带 message_id 去重:Telegram 瞬态失败后重投递会造成重复
  用户回合(#47237,`has_platform_message_id`,session.py:3338):

```python
# gateway/run.py:18010-18015 @ 863e313
                _skip_persist = (
                    event.message_id
                    and await self.async_session_store.has_platform_message_id(
                        session_entry.session_id, str(event.message_id)
                    )
                )
```

  hidden-reasoning 未完成回合同规则(不让 peer 频道把它当完整回合摄取,#51628)。
- **正常回合**:先在**新会话**头写 `session_meta` 行(完整 tools 定义 + model + platform,
  17953–17964,使 transcript 自描述);再按 `history_offset`(agent 实际收到的过滤后历史长度,
  不是含 session_meta 的 len(history))切出本回合新消息逐行 append,skip system 行,
  首个 user 行附 platform message_id(供 Yuanbao 引用解析等按原 id 回查,18061–18079)。
  `agent_persisted`(默认 `self._session_db is not None`)让 append 走 `skip_db` —— agent 已
  经由 `_flush_messages_to_session_db` 落库,gateway 再写就是重复写 bug(#860/#42039);codex
  app-server 运行时自己 flush 后报 `agent_persisted=True`(17966–17976 注释)。

### 11.2 compression_deferred vs compression_exhausted(17892–17944)

- **deferred**:并发压缩者持锁、会话只是**暂时**不可压 —— 绝不重置,下条消息自然重试
  (#69870;salvaged from #49874)。
- **exhausted**:会话**永久**过大 → `reset_session`(session.py:2886)+ 驱逐缓存 agent +
  `_clear_conversation_scope(reason="compression_exhausted_reset")`,并且**必须重同步 topic 绑定**:
  本回合早些时候 agent-result 同步已把绑定改写到臃肿 child,不重同步的话下条消息又被 binding-heal
  walk 切回臃肿 child、重载超大 transcript、再次 exhausted,**永远循环**(#35809 —— 对
  #9893/#10063 自动重置的回归;17922–17935 注释)。响应尾部追加"会话已自动重置"说明(17940–17944)。

### 11.3 update_session 与缓存计数再基线(18085–18113)

`update_session(session_key, last_prompt_tokens=...)`(session.py:2638)只留上下文窗口跟踪;
然后 `_refresh_agent_cache_message_count`(23149):跨进程缓存一致性守卫(#45966)在 agent
**构建时**快照 message_count、复用时从不刷新 —— 本进程自己的回合写行涨了计数,下一回合守卫
误判"别的进程改了 transcript"而重建 agent,**每回合重建、prompt cache 全废**。所以在本回合
**全部**写入完成后(含 session_meta 行 —— 旧位置在 session_meta 之前刷新,快照少 1,每个新
会话的 turn2 必然误触发)再快照一次;4 元组缓存里 session_id 不匹配(同 key 不同会话,#54947)
则**不动快照**,否则污染原会话的基线(18093–18113 注释 + 23196–23222 实现)。

### 11.4 重实现要点

1. 失败持久化按"会话是否超限"二分:超限一字不写,瞬态只写用户消息 + 平台 message_id 去重。
2. transcript 自描述:新会话首行写工具定义与模型快照。
3. 双写问题用显式 `agent_persisted` 契约解决,默认值与运行时是否有 DB 对齐,允许未来运行时 opt-out。
4. "暂时不可压(锁竞争)"与"永久不可压(耗尽)"必须区分,前者保守重试、后者重置且**同步所有
   外部指针**(绑定表),否则治愈路径被指针拉回病灶。
5. 缓存一致性快照的刷新点必须覆盖"本进程全部写入之后",并做会话身份校验。

---

## 12. 阶段 S + 辅助:异常路径与 `_reset_notice_session_info` / `_format_session_info`

**异常路径**(18178–18290):先带 metadata 停 typing(失败回合不能留下悬挂状态);
`logger.exception` 全量入日志但**绝不向用户暴露原始异常**(信息泄漏);若 agent 还没进
`run_conversation`(provider/httpx 初始化失败)就崩了,agent 自己没机会持久化本回合用户消息,
这里查最近 10 行 transcript、内容不同才补写一次(18205–18240)。状态码提示映射:401(API key /
`claude /login`)、402(配额)、429(区分 plan usage_limit_reached —— 读 body 的
resets_in_seconds 折算小时 —— 与瞬态限速)、529(过载)、400/500+历史>50(按上下文溢出处理,
给 /compact 建议)(18245–18290)。finally 恢复 task-local session env(`_clear_session_env`,
21370)。

**`_reset_notice_session_info`**(18295–18313,#59003):multiplex 时必须在服务该 source 的
profile 作用域里解析模型/上下文,否则横幅广告 base 配置的模型而会话实际跑 profile 的模型;
方法内进 scope,要求经 `asyncio.to_thread` 调(scope 下可能做凭据刷新、上下文长度 HTTP 探测
等阻塞工作,不得上事件循环)—— 16513–16516 的调用点确实如此。

**`_format_session_info`**(18315–18433):解析 model/provider/context_length(config pin →
route_identity 判定 pin 是否随路由失效 → custom_providers 兜底 → `get_model_context_length`),
输出 `◆ Model / ◆ Provider / ◆ Context(来源标注 config/detected/default)`;上下文来源标注
让"本地模型跌到 128K 默认值"这类检测失误一眼可见;localhost 类 endpoint 额外显示。

重实现要点:面向用户的错误分层(日志全量、用户脱敏 + 可执行提示);多租户/多 profile 下,
任何"当前配置"展示都必须在正确作用域内解析;阻塞解析统一 to_thread。

---

## 13. `_check_slash_access`(18438–18478)—— 双路径共用的命令门禁

冷路径与 running-agent 路径的 slash 分发**共用**本方法,使 in-flight agent 无法绕过 admin/user
门禁(18442–18445 docstring)。策略解析在 `gateway/slash_access.policy_for_source`;向后兼容:
操作者未设 `allow_admin_from` → `policy.enabled=False` → 永远放行。拒绝消息带可运行命令预览
(最多 12 个 + /whoami 指引)或"无命令可用,找管理员"文案。

重实现要点:门禁必须是纯函数式单点,由所有分发路径调用;默认未配置=不启用(不破坏既有安装);
拒绝信息要指路。

---

## 14. `_sibling_thread_run_keys`(18486–18523)—— per-user 线程模式下的 /stop 可见性

问题:`thread_sessions_per_user=True` 时每个参与者的 key 是
`agent:main:{platform}:{chat_type}:{chat_id}:{thread_id}:{user_id}`,别人启动的 run 对本人的
/stop 不可见。实现:拼 `agent:main:platform:chat_type:chat_id:thread_id` 前缀,匹配
`key == prefix or key.startswith(prefix + ":")`(精确或再多一段 user_id;裸 startswith 会误配
"id 恰为前缀延伸"的无关线程),过滤掉 pending 哨兵与自己的 key,只返回**真在跑**的 agent keys:

```python
# gateway/run.py:18512-18523 @ 863e313
        prefix = ":".join(
            ["agent:main", platform, chat_type, str(chat_id), str(thread_id)]
        )
        matches = []
        for key, agent in self._running_agent_items():
            if key == own_key:
                continue
            if agent is _AGENT_PENDING_SENTINEL or not agent:
                continue
            if key == prefix or key.startswith(prefix + ":"):
                matches.append(key)
        return matches
```

返回空列表 ≠ 授权:调用方仍须自行做权限门禁(18498–18500 docstring)。

重实现要点:结构化 key 的前缀匹配必须以分隔符终结;枚举返回"候选",授权判定留给调用方。

---

## 15. `_is_stale_restart_redelivery`(18528–18607)—— /restart 重投递的三重判据

问题(注释引 issue #18528):上一个 gateway 处理 /restart 时写下
`.restart_last_processed.json`(platform + update_id);进程重启后 Telegram 会把同一条
/restart 重投递,若不识别就再次重启 → 无限循环。仅 Telegram 适用(唯一暴露跨会话数值
update 序的平台,显式白名单防未来平台被误门禁,18546–18553)。

判据链:
1. **marker 缺失**:比对无从做起,但若本进程确证"刚从聊天发起的 /restart 启动"
   (`_booted_from_restart` 且开机 <60s)则抑制;标志**一次性消费**,同会话稍后真 /restart 仍被尊重
   (18556–18577)。绝不吞新鲜启动上的第一次 /restart(启动无 marker → 标志本来就是 False)。
2. **update_id 比较**:`event.platform_update_id > recorded_uid` → 不是重投递(18584–18588)。
3. **同或更旧的 update_id**:若 `_booted_from_restart` → 无论 wall time 都算该次重启的重投递
   (服务托管重启排空 adapter/cron/在途投递可以合法超过 5 分钟),一次性消费(18590–18598);
   否则 marker 必须 <5 分钟(合法老 marker,例如 notify 没发出去的崩溃恢复,不得吞掉用户新
   /restart,18600–18607)。

重实现要点:重投递去重 = 平台序号 + 持久 marker + 进程启动来源三信号互补;所有布尔信号一次性
消费;时间窗兜底 marker 失效。

---

## 16. suggestions / blueprint 命令(18617–18680)

两者同构:从 event.source 构造 origin(platform/chat_id/chat_name/thread_id,使被接受的
建议/蓝图 job 能回投本聊天),委托给 `hermes_cli.suggestions_cmd.handle_suggestions_command` /
`hermes_cli.blueprint_cmd.handle_blueprint_command`(`surface="gateway"`)—— CLI/TUI/gateway
共享处理器,"never drift"。blueprint 返回 `BlueprintCommandResult`:`text` 展示给用户;
`agent_seed` 非空时分发点把 `event.text` 重写为 seed 落回 agent(/steer 模式),由 agent
会话式收集槽位值(18650–18656 docstring)。异常都降级为文本错误消息。

重实现要点:多 surface 命令共享单一处理器 + surface 参数;命令результат可以携带"转交 agent
继续"的 seed,而不是命令层硬编码交互。

---

## 17. goal 与 heartbeat(18685–18962)—— 回合边界的续跑机制

### 17.1 goal(Ralph-style 循环)

- `_goal_max_turns_from_config`(18685–18704):GatewayConfig 是 dataclass 不含顶层 `goals`
  块,所以经 `hermes_cli.config.load_config()` 兜底,默认 20。
- `_get_goal_manager_for_event`(18706–18726):按事件解析会话,返回绑定 session_id 的
  `GoalManager`(hermes_cli/goals)。
- `_post_turn_goal_continuation`(18885–18962):由 `_handle_message` 在
  `_handle_message_with_agent` 返回**非空 final 文本**后调用(15707–15717;空响应跳过 ——
  判官对错误回合几乎总说 continue,会在错误上打转)。流程:goal 不活跃即返回;收集后台进程
  快照;`mgr.evaluate_after_turn(final, user_initiated=True, background_processes=...)`;
  判官状态行经 `_defer_goal_status_notice_after_delivery`(18842)**延迟到主响应投递之后**发 ——
  判官跑在响应产出后、adapter 发送前,直接发会出现 "✓ Goal achieved" 先于答案本身
  (18931–18936 注释);adapter 无 post-delivery 回调能力时回退为直接 await 发送(不静默丢弃)。
  续跑 prompt 经 `_enqueue_fifo`(7691)走 adapter FIFO:

```python
# gateway/run.py:18947-18960 @ 863e313
        # Enqueue via the adapter's FIFO so a user message already in
        # flight preempts the continuation naturally.
        try:
            adapter = self._adapter_for_source(source)
            _quick_key = self._session_key_for_source(source)
            if adapter and _quick_key:
                cont_event = MessageEvent(
                    text=prompt,
                    message_type=MessageType.TEXT,
                    source=source,
                    message_id=None,
                    channel_prompt=None,
                )
                self._enqueue_fifo(_quick_key, cont_event, adapter)
```

  —— 同队列意味着真实用户消息自然优先/插队,续跑不与用户抢会话。

### 17.2 heartbeat

- `_get_heartbeat_manager_for_event`(18728–18746):同构返回 `HeartbeatManager`。
- `_register_heartbeat_watch`(18748–18762):`quick_key → (source, session_id)` 注册表,
  **内存态是有意设计**:heartbeat 的 STATE 在 SessionDB 持久,但**触发**在新 gateway 进程里
  要等用户再碰 /heartbeat 才恢复;"durable schedules belong to cron"(18753–18755 docstring)。
- `_start_heartbeat_poller`(18769–18819):幂等启动单个 gateway 级轮询 task,每
  `POLL_SECONDS` 醒来:busy 会话(`quick_key in self._running_agents`)把 tick 合并到下次空闲
  轮询;`has_heartbeat()` 为假即摘表;`due_prompt()` 到期则合成 MessageEvent 走同一
  `_enqueue_fifo`。task 挂进 `_background_tasks` 防 GC。

### 17.3 重实现要点

1. 自续跑(goal/heartbeat)注入必须与真实用户消息走**同一条 FIFO**,天然让位。
2. 判官/状态类消息的显示顺序用 post-delivery 回调保证,注册失败回退直接发送而非丢弃。
3. 空/错误回合不触发续跑判定,防错误循环。
4. "状态持久、调度易失"是合法设计,但必须写明恢复语义;真正的持久调度交给 cron 层。
5. 轮询器单例 + 幂等启动 + busy 合并,避免 per-session 定时器军备。

---

## 18. 文档-代码冲突候选(待与 README/website/docs 对照定案)

1. **hygiene 阈值 0.85 vs 压缩文档**:代码注释明说 hygiene 阈值有意高于 agent 压缩器
   (0.85 vs 0.50,`gateway/run.py:16620-16626 @ 863e313`)。若 docs/website 只写"50% 触发压缩"
   而未区分 gateway 预压缩安全网,即为冲突候选。
2. **heartbeat 重启语义**:`gateway/run.py:18753-18755 @ 863e313` 明言 firing 在新进程中
   需用户再碰 /heartbeat 才恢复("documented; durable schedules belong to cron")。
   若用户文档宣称 heartbeat 跨重启自动恢复触发,即冲突。
3. **AGENTS.md 禁 source-reading test 并点名本文件**:`gateway/run.py:199-202 @ 863e313`
   (`hygiene_compaction_recovered` docstring)称 "AGENTS.md bans outright, naming this file"。
   需在 AGENTS.md 核实该条款存在与表述(若不存在则注释本身过期)。
4. **`_format_session_info` 的默认 provider 显示**:`gateway/run.py:18425 @ 863e313`
   `f"◆ Provider: {provider or 'openrouter'}"` 把无 provider 显示为 openrouter;若文档称默认
   provider 为其他值,或实际请求路径默认并非 openrouter,此展示即误导(展示层假设,候选)。
5. **任务简报 vs 代码结构**(内部记录,非作者文档):TurnRunner/agent 缓存判据实际在
   `_run_agent`/`_run_agent_inner`(24112/24265),不在 16276–18293;下轮读该段时对齐。

---

## 19. 本段调用关系速查

| 本段调用 | 目标 | 说明 |
|---|---|---|
| get_or_create_session / switch_session / reset_session | gateway/session.py:2291 / 2993 / 2886 | 会话解析与边界 |
| load_transcript / rewrite_transcript / append_to_transcript / update_session | gateway/session.py:3380 / 3357 / 3104 / 2638 | transcript 读写 |
| has_platform_message_id / has_any_sessions / clear_resume_pending | gateway/session.py:3338 / 2269 / 2780 | 去重、onboarding、恢复标记 |
| build_session_context / build_session_context_prompt / build_channel_continuity_note | gateway/session.py:3455 / 479 / 977 | 上下文构建 |
| _record_gateway_session_peer | gateway/session.py:1986 | 改名后 peer 记录 |
| AsyncSessionStore(to_thread 包装)/ SessionStore | gateway/session.py:1189 / 1206 | 异步桥 |
| SessionTurnLeaseRegistry.acquire/rebind/release | gateway/turn_lease.py:154 / 215 / 274 | 回合租约 |
| TurnState.lease_token/lease_generation | gateway/session_state.py:74-75 | token 存放(TurnLeaseTokenView 299 为旧接口兼容视图) |
| get_compression_tip | hermes_state.py:5719 | 压缩链尾查询 |
| CompressionCommitFence(touch_progress/seconds_since_progress/try_cancel_before_commit/commit_in_flight/revoke_commit_admission/release_cancelled_compression_lock) | agent/conversation_compression.py:445/491/500/521/575/591/678 | hygiene 等待与取消协商 |
| AIAgent / _compress_context | run_agent.py | hygiene 压缩执行体 |
| _run_agent(下一段) | gateway/run.py:24112 | 真正跑回合 |
| _release_turn_lease / _rebind_turn_lease / _clear_conversation_scope | gateway/run.py:22859 / 22888 / 22917 | 释放/随迁/边界漏斗 |
| _refresh_agent_cache_message_count / _evict_cached_agent | gateway/run.py:23149 / 23374 | agent 缓存维护 |
| _resolve_async_delegation_session | gateway/run.py:13928 | 委托 pinning |
| _recover_telegram_topic_thread_id / _is_telegram_topic_lane / _record_/_sync_telegram_topic_binding | gateway/run.py:6851 / 6745 / 6806 / 6825 | topic 路由 |
| _normalize_empty_agent_response 等模块级归一函数 | gateway/run.py:3445 / 3530 / 3554 | 结果归一 |
| hygiene 辅助(cooldown ladder / recovered / record / seed prompt) | gateway/run.py:135 / 187 / 231 / 465 | hygiene 决策 |
| _enqueue_fifo / _session_key_for_source / _adapter_for_source | gateway/run.py:7691 / 6679 / 13886 附近 | 派发基础设施 |

## 20. 本段涉及 issue 清单(用于交叉验证)

#628 #860 #1630 #2153 #3854 #6508 #7100 #9893 #10063 #10702 #18528 #18765 #20470 #21301
#28686 #29712 #30479 #31066 #31110 #31884 #33414 #35809 #36220 #39548 #39704 #42039 #44212
#44794 #45966 #47237 #48031 #49874 #51628 #54947 #55578 #57498 #58403 #59003 #60671 #61145
#61220 #64934 #69870 #74136 #76354 #79624
