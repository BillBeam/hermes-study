# r7 底稿 · gateway/run.py 第 9 段(21424-23758)——媒体 enrich、后台完成事件投递、turn lease、agent 缓存治理

> 对象:GatewayRunner 方法段,gateway/run.py:21424-23758 @ 863e313。
> 证据格式:`路径:行号 @ 863e313` + 逐字摘录(≤25 行/处)。hermes-agent 只读。
> 本段是 gateway 的"后台事件回注 + 会话状态生命周期 + agent 缓存复用"核心:上承第 8 段的
> 消息主流程(_handle_message_with_agent),下接 proxy/stream 段(23758 起)。

---

## 1. `_decide_image_input_mode`(21424-21495)——按"本回合实际生效模型"决定图像走原生还是文本

**问题**:用户发图时,gateway 要决定把像素直接附在 user turn(native)还是先用 vision 辅助模型
预分析、把描述文本前置(text)。难点:gateway 会话可有 `/model` 覆盖(不在 config.yaml 里),
而图像预处理发生在 AIAgent 设置 auxiliary_client 运行时全局量**之前**——若只看持久化默认模型,
`/model` 切到视觉模型后仍会走 text 模式(#29135 的 gateway 侧变体)。

**实现**:优先解析"即将运行的这次 agent turn 会用的运行时包"。

gateway/run.py:21439-21443 @ 863e313
```python
        Gateway sessions can have /model overrides that live outside
        config.yaml. Image preprocessing runs before AIAgent sets the
        auxiliary_client runtime globals, so resolve the same per-session
        runtime bundle the upcoming agent turn will use instead of consulting
        only the persisted default model.
```

gateway/run.py:21455-21463 @ 863e313
```python
            needs_session_runtime = not resolved_provider or not resolved_model
            has_session_identity = source is not None or session_key
            if needs_session_runtime and has_session_identity:
                try:
                    turn_model, runtime_kwargs = self._resolve_session_agent_runtime(
                        source=source,
                        session_key=session_key,
                        user_config=cfg,
                    )
```

会话运行时解析失败→回落 `_read_main_provider()/_read_main_model()`(agent/auxiliary_client.py);
整体异常→回落 `"text"`(gateway/run.py:21493-21495 @ 863e313,fail-safe:文本模式永远可用)。

**决策表本体**在 agent/image_routing.py:461-507 @ 863e313:配置 `agent.image_input_mode`
显式 native/text 直接生效;auto 时查主模型 vision 能力,支持→native;不支持→text
(显式 auxiliary.vision 配置只作为 text 兜底,不抢占原生视觉,#29135)。

agent/image_routing.py:487-491 @ 863e313
```python
    # auto: prefer native vision when the main model supports it. An
    # explicit auxiliary.vision config acts as a *fallback* for text-only
    # main models — it should not preempt native vision on a model that
    # can natively inspect the pixels (issue #29135).
```

**调用关系**:调用方 gateway/run.py:15883(inbound 消息预处理段,以 bound method 传入);
依赖 agent/image_routing.py:461 `decide_image_input_mode`、agent/auxiliary_client.py
`_read_main_model/_read_main_provider`、本类 `_resolve_session_agent_runtime`。

**取舍**:每回合重解析运行时包有成本,但保证 `/model` 切换后图像路由立即一致;
所有异常吞掉降级 text 而非报错——图像路由错误不值得断消息流。

**重实现要点**:
1. 图像路由必须以"本回合生效模型"为准,不能用全局默认——会话级模型覆盖是常态。
2. auto 模式的优先级:主模型原生视觉 > 辅助视觉兜底;辅助配置不应抢占原生能力。
3. 全链路 fail-safe 到 text 模式(预分析文本任何模型都能消费)。
4. 尺寸处理选反应式(发全尺寸、被 4xx 拒后 shrink 重试)而非按 provider 上限表主动缩
   (agent/image_routing.py:510-521 @ 863e313:上限表会过期,静默降质是更坏的失败)。

---

## 2. `_enrich_message_with_vision`(21497-21564)——预分析描述 + 缓存路径双注入

**实现**:对每张图调用 `tools/vision_tools.vision_analyze_tool`,通用 prompt 要求详尽描述;
成功→注入描述 + 本地缓存路径;失败→注入"没看清 + 你可自己用 vision_analyze 看"的路径提示。

gateway/run.py:21536-21543 @ 863e313
```python
                if result.get("success"):
                    description = result.get("analysis", "")
                    description = sanitize_context(description)
                    enriched_parts.append(
                        f"[The user sent an image~ Here's what I can see:\n{description}]\n"
                        f"[If you need a closer look, use vision_analyze with "
                        f"image_url: {path} ~]"
                    )
```

**设计理由**(docstring 21506-21510):双注入使模型 (1) 无需额外工具调用即知图里是什么;
(2) 需要细节时可用 vision_analyze 二次检视。描述过 `sanitize_context`
(agent/memory_manager)防注入。失败分支也给路径——把"看图"能力交还给 agent 而非丢弃。

**重实现要点**:
1. 预分析结果 + 原始路径都注入:一次省 tool call,二次可下钻。
2. 外部内容(视觉模型输出)入 prompt 前必须 sanitize。
3. 失败不静默:注入带路径的失败标记,agent 可自救。

---

## 3. 语音转写 enrich 与"转写一次、回显一次"族(21566-21829)

### 3.1 `_enrich_message_with_transcription`(21566-21704)

**问题群**:
- STT 关闭时要给 agent 一个含时长的语音占位(21590-21609:`_probe_audio_duration`);
- STT 返回 success 但空转写(静音/听不清)→ 注入空引号会让 agent"回复空气"甚至循环(#41603);
- 失败文案若提到"未配置 STT/setup 指引"会**持久化进历史**,之后每回合模型都主动兜售 STT 配置建议
  ——历史污染(prompt poisoning)。

**实现**:配置 STT 失败→本地 STT 兜底(21631-21642);空转写→哨兵注记:

gateway/run.py:21645-21657 @ 863e313
```python
                    # Speech-to-text can return success=True with an empty or
                    # whitespace-only transcript on silence, cut-off, or
                    # inaudible audio. Emitting empty quotes ('""') makes the
                    # agent reply to nothing and can loop, so that case gets a
                    # clear sentinel note instead (#41603).
                    if not (transcript or "").strip():
                        enriched_parts.append(
                            "[The user sent a voice message but it came through "
                            "empty or inaudible — speech-to-text returned no "
                            "words. Do not guess at the content; ask the user "
                            "to resend or type it out.]"
                        )
                        continue
```

成功转写以**纯引号行**注入(21659-21664:早期"Here's what they said"措辞被模型读成
元指令,导致它评论语音模式而不是回复内容)。失败→中性最小标记 + agent 可见音频路径:

gateway/run.py:21666-21676 @ 863e313
```python
                else:
                    error = result.get("error", "unknown error")
                    # All failure branches: a single, minimal, neutral marker.
                    # Do NOT mention "no STT provider configured", "setup
                    # instructions", or the "hermes-agent-setup" skill, and do
                    # NOT claim a direct message was sent — those phrases get
                    # persisted in conversation history and poison every later
                    # turn, so the model keeps volunteering STT-setup advice
                    # even after transcription starts working. The cause is
                    # logged for operator diagnosis but kept out of the
                    # LLM-visible prompt.
                    logger.info("Voice transcription failed for %s: %s", path, error)
```

另:Discord 适配器的空文本占位 `"(The user sent a message with no text content)"`
在成功转写后被剥除(21694-21703,冗余信息)。返回 `(enriched_text, successful_transcripts)`
二元组,后者供调用方回显。

### 3.2 转写缓存 + 回显计数(21715-21829)

**问题**:语音 follow-up 事件会被两条路径消费——interrupt monitor 先"看"、pending-drain 后
"用",两者需要同一份转写,但平台消息只允许一次 STT 调用与一次回显。

**实现**:`_transcribe_pending_audio_event_once`(21715-21743)把结果缓存在事件对象属性
`_gateway_pending_stt_text/_transcripts` 上,二次调用直接取缓存。
`_echo_pending_stt_transcripts_once`(21745-21784)用**计数**而非布尔跟踪已回显数:

gateway/run.py:21757-21766 @ 863e313
```python
        The already-echoed transcripts are tracked as a COUNT rather than a
        single boolean.  ``merge_pending_message_event`` can append a second
        voice note to an event whose first transcript was already echoed and
        invalidates the transcription cache; the re-run transcription then
        returns the earlier transcripts as a prefix of the new list, so
        echoing only the unsent tail suppresses the repeat while still
        surfacing the newly merged note.  A count rather than a set of seen
        values because two separate notes that transcribe identically are two
        distinct deliveries and both must be echoed.
```

`_transcribe_and_echo_pending_voice`(21786-21829)是统一入口:interrupt/monitor/backup/drain
四类路径都走它(调用点 gateway/run.py:8731、9013、14944、24938、25220、25322、25508)。

**重实现要点**:
1. 注入 LLM 历史的失败文案必须"中性最小"——任何指导性措辞都会被持久化并污染后续回合。
2. success≠有内容:空转写需哨兵注记,禁止空引号。
3. 同一媒体的 STT 结果缓存在事件对象上(单次转写),回显用计数支持事件合并后的增量尾部。
4. 转写回显用引号原样注入,不加叙述性包装(包装会被模型当元指令)。

---

## 4. `_build_process_event_source`(21831-21907)——合成事件的路由必须来自事件自身

**问题**:后台进程完成事件要注回原会话。若回落到"当前活跃前台事件的 source",会把 A 话题的
完成通知注进 B 话题(cross-topic bleed)。

**实现**:三级解析,全部基于事件/会话键自身:
1. session_store 持久化 origin(21845-21850:`self.session_store._entries.get(session_key).origin`);
2. 内存缓存 `_get_cached_session_source`(21858-21860;`_session_sources` 是 512 上限的
   OrderedDict,gateway/run.py:6052-6053 @ 863e313);
3. `_parse_session_key`(gateway/run.py:3352)从结构化键解析 platform/chat_type/chat_id,
   再与事件字段合并;三者仍缺→warning 并返回 None(21871-21879)。

gateway/run.py:21833-21837 @ 863e313
```python
        """Resolve the canonical source for a synthetic background-process event.

        Prefer the persisted session-store origin for the event's session key.
        Falling back to the currently active foreground event is what causes
        cross-topic bleed, so don't do that.
        """
```

平台名做**白名单校验**:`Platform(platform_name)` 后再查内建集合与插件注册表,拒绝任意字符串
造出动态伪成员:

gateway/run.py:21882-21892 @ 863e313
```python
            platform = Platform(platform_name)
            # Reject arbitrary strings that create dynamic pseudo-members.
            # Built-in platforms are always valid; plugin platforms must be
            # registered in the platform registry.
            if platform.value not in _BUILTIN_PLATFORM_VALUES:
                try:
                    from gateway.platform_registry import platform_registry
                    if not platform_registry.is_registered(platform.value):
                        raise ValueError(platform_name)
                except Exception:
                    raise ValueError(platform_name)
```

**重实现要点**:
1. 后台事件路由铁律:只信事件自带/持久化的路由元数据,绝不回落"当前前台会话"。
2. 路由字段多级解析(持久 store → 内存缓存 → 键解析),每级失败可降级。
3. 反序列化出的平台标识必须过注册表白名单(枚举 + 插件注册),防伪成员注入。

---

## 5. `_inject_watch_notification`(21909-22020)——完成事件注入,与 gateway/wake.py 的分工【重点】

**问题**:watch/完成通知要作为**合成用户消息**重新进入目标会话跑一个 agent turn。三种目标:
(a) 常规推送型平台(Discord/Slack…);(b) api_server 会话——它绑定的是**裸 session id**
(X-Hermes-Session-Id,见 `_bind_api_server_session`,gateway/run.py:21924 注释),
`_build_process_event_source` 解析不出路由,返回 None;(c) 路由能解析但适配器不可推送。

**返回值三态**(docstring 21915-21919):`True`=适配器接受;`False`=可重试失败;
`None`=无 gateway 路由(不可重试)。且明确声明**非事务边界**:适配器接受后进程崩溃仍可能
造成 durable at-least-once 重放。

**分支 1:无路由 + 有裸 session id → deliver_wake 自投**:

gateway/run.py:21935-21945 @ 863e313
```python
            if raw_sid:
                adapter = self.adapters.get(Platform.API_SERVER)
                from gateway.wake import adapter_supports_push, deliver_wake
                if adapter is not None and not adapter_supports_push(adapter):
                    try:
                        logger.info(
                            "Watch pattern notification — waking api_server "
                            "session %s via self-post",
                            raw_sid,
                        )
                        await deliver_wake(adapter, text=synth_text, session_id=raw_sid)
                        return True
```

**分支 2:有路由但适配器不可推送**(api_server 却带了路由元数据的情形)——不能走
handle_message,因为它会用 `build_session_key()` 派生键,永远匹配不上裸 session id 的会话:

gateway/run.py:21974-21981 @ 863e313
```python
        if not _wake_push_ok(adapter):
            # Non-push adapter (api_server) resolved WITH routing metadata:
            # its chat_id is the raw session id (see _bind_api_server_session,
            # which binds chat_id = session_id). handle_message would run the
            # wake under a build_session_key()-derived key that never matches
            # the raw X-Hermes-Session-Id session — self-post instead.
            from gateway.wake import deliver_wake
            raw_sid = str(evt.get("origin_session_id") or "").strip() or str(source.chat_id or "")
```

**分支 3:常规推送型 → 构造 internal MessageEvent 走 handle_message**(22002-22017),
`internal=True` 标记合成消息,`metadata["gateway_session_id"]=parent_session_id` 把子代理
完成定向到 spawn 它的那次会话。

**与 gateway/wake.py 的关系**:`adapter_supports_push`(gateway/wake.py:45-53 @ 863e313)读
适配器类属性 `supports_async_delivery`(未声明视为可推送);`deliver_wake`
(gateway/wake.py:56-94)对可推送适配器构造 internal MessageEvent 走 `handle_message`,
对不可推送适配器用裸 session id 向 in-pod API server **自 POST /v1/chat/completions**
(`_self_post_chat_completion`,gateway/wake.py:97+),且要求 API_SERVER_KEY 已配置——
无鉴权时会话续传被 403,宁可大声报错也不让 wake 落进没人看的指纹派生新会话:

gateway/wake.py:45-53 @ 863e313
```python
def adapter_supports_push(adapter: Any) -> bool:
    """Whether this adapter can push a message to the user after a turn ends.

    Mirrors ``gateway.session_context.async_delivery_supported`` but reads the
    capability off the adapter class (``supports_async_delivery``) instead of
    the request-scoped contextvar — background watchers run outside any bound
    session context. Adapters that don't declare the flag are push-capable.
    """
    return bool(getattr(adapter, "supports_async_delivery", True))
```

**调用关系**:被 `_deliver_completion_notification`(22181)与 post-turn watch 事件 drain
(gateway/run.py:17824)直接调用;分支 1/2 调 gateway/wake.py:56 `deliver_wake`。

**重实现要点**:
1. 后台唤醒需要两条通道:推送型平台注合成消息;pull 型(OpenAI 兼容 API server)只能自 POST
   回自己的 HTTP 入口,带上原 session id 头。
2. 两类会话键(结构化派生键 vs 裸外部 id)不可混:裸 id 会话走 handle_message 必然 miss。
3. 返回值三态(成功/可重试/不可路由)让上层 durable 状态机能诚实转移。
4. 明示一致性等级:adapter 接受 ≠ 送达,崩溃窗口内 at-least-once。

---

## 6. 完成投递识别/分类/投递(22022-22224)——生命周期内去重 + durable 声明式认领

### 6.1 `_completion_delivery_identity`(22022-22041)

producer 稳定身份:async_delegation → `(type, delegation_id, "")`;进程 completion →
`(type, session_id, started_at)`——带 spawn epoch 是因为 session id 可被显式复用,
同 id 不同 incarnation 必须视为不同完成。**legacy 事件无 started_at → 返回 None,
放弃去重而不是冒险吞掉真实完成**:

gateway/run.py:22025-22030 @ 863e313
```python
        """Return a producer-stable identity when one is available.

        Delegation UUIDs identify one producer completion. Process session IDs
        are normally unique too, but include the persisted spawn epoch so an
        explicitly reused ID represents a distinct process incarnation. Legacy
        process events without ``started_at`` are delivered without deduplication
        rather than risking suppression of a real completion.
        """
```

### 6.2 `_classify_completion_target`(22043-22094)——投递前置裁决(#65838)

**问题**:#65838 类 bug——adapter 接受≠送达,内层 #55578 resolver 在 adapter 接受**之后**
仍可能 fail-closed,若那时才发现目标会话没了,durable 行已被误 ack 为 delivered。

**实现**:接受前预检父会话,给出三态裁决:
- `deliver`:父会话活着,或因 compression 轮转结束但已验证有活的 continuation(tip);
- `terminal`:父会话不存在,或在显式用户边界(/new)结束——永远送不到,durable 行应
  terminally dropped 而非假 ack 或永久重放;
- `retry`:瞬态不确定(DB 不可用 / 轮转进行中 continuation 尚不可见)→释放 claim 让后续重试,
  attempt 上限兜底。

gateway/run.py:22076-22084 @ 863e313
```python
        if not parent.get("ended_at"):
            return "deliver"
        if parent.get("end_reason") != "compression":
            return "terminal"
        try:
            tip_session_id = await session_db.get_compression_tip(parent_session_id)
            if not tip_session_id or tip_session_id == parent_session_id:
                # Rotation caught mid-flight: parent is compression-ended but
                # its continuation isn't visible yet. Retry, don't drop.
                return "retry"
```

### 6.3 `_deliver_completion_notification`(22096-22224)——双层去重 + durable 状态机

**层 1(跨进程,仅 async_delegation)**:SQLite durable claim。
`claim_completion_delivery`(tools/async_delegation.py:383-401 @ 863e313)用
`UPDATE ... WHERE delivery_state='pending' AND (delivery_claim IS NULL OR
delivery_claimed_at < now-300)` 的条件更新做跨进程互斥(300s claim 超时可抢占),
attempt 在 claim 时即计数;行不存在(legacy)→ 返回 True 直接放行。

**层 2(单 gateway 生命周期)**:内存 inflight set + delivered LRU(retention 2048,
gateway/run.py:6059-6063 @ 863e313):

gateway/run.py:22170-22177 @ 863e313
```python
        if identity is not None:
            with self._completion_delivery_lock:
                if (
                    identity in self._completion_deliveries_inflight
                    or identity in self._completion_deliveries_delivered
                ):
                    return None
                self._completion_deliveries_inflight.add(identity)
```

**状态转移**:注入 True → 标 delivered + `complete_completion_delivery`
(async_delegation.py:472-484:`delivery_state='delivered'`);注入 False/异常 →
finally 释放 inflight + `release_completion_delivery`(async_delegation.py:414-448:
attempts 达 `_MAX_DELIVERY_ATTEMPTS` 则收敛为 terminal `dropped`,否则回 pending);
预检 terminal → `drop_completion_delivery`(async_delegation.py:450-470:标 dropped,
"keeps the ack honest"且防重启重放)。

gateway/run.py:22127-22134 @ 863e313
```python
            parent_session_id = str(evt.get("parent_session_id") or "").strip()
            if parent_session_id:
                # Pre-flight (#65838-class): adapter acceptance is NOT proof of
                # delivery — the inner #55578 resolver can still fail closed
                # inside the message pipeline AFTER the adapter accepted, which
                # would falsely acknowledge the durable row as delivered.
                # Verify the target here, before acceptance, and give drops an
                # honest durable disposition.
                verdict = await self._classify_completion_target(parent_session_id)
```

**一致性声明**(22099-22105 docstring + 6054-6058 注释):单 gateway 内闭合重复,
**不承诺跨进程 exactly-once**;durable 重放状态唯一属主是 tools.async_delegation,
gateway 不另设账本。

**重实现要点**:
1. 去重身份必须 producer 稳定且含 incarnation 维度(id+epoch);拿不到就放弃去重,宁重勿失。
2. 跨进程互斥用 DB 条件更新(claim + 超时抢占 + attempt 预算),内存层只闭合本进程竞态。
3. ack 语义三分:delivered / dropped(terminal,诚实)/ pending(retry);
   "投不出去"与"投出去了"必须是不同的持久态,否则要么假 ack 要么永久重放。
4. 预检要区分"永久没了"(用户边界)与"暂时看不见"(compression 轮转中)——后者 retry。
5. attempt 预算在 claim 时计,claim-release 循环也消耗预算,防无限重放。

---

## 7. async delegation 路由补全 + 空闲 watcher(22226-22295)

`_enrich_async_delegation_routing`(22226-22245):后台子代理完成事件只带 session_key
(daemon worker 拿不到 spawn 时的逐消息路由元数据),从键解析回填 platform/chat_id 等;
CLI 起源(空键)不处理,gateway 上自然不路由。

`_async_delegation_watcher`(22247-22295):**覆盖 IDLE 情形**——`delegate_task(background=true)`
的子代理跑在 async-delegation daemon executor 上,没有 per-process watcher 任务,若完成时
没有 agent turn 在跑,只有 post-turn drain 能看到事件(可能永远等不到)。此 watcher 每 2s
peek 共享 completion_queue,**只消费 async_delegation 类型,其余 requeue**(避免抢别的
消费者的事件);投递 False/异常→事件放回队列重试:

gateway/run.py:22264-22280 @ 863e313
```python
            try:
                # Peek the queue for async-delegation events. We must NOT
                # consume watch/completion events here (other drains own them),
                # so requeue anything that isn't ours.
                requeue = []
                async_events = []
                while not _pr.completion_queue.empty():
                    try:
                        evt = _pr.completion_queue.get_nowait()
                    except Exception:
                        break
                    if evt.get("type") == "async_delegation":
                        async_events.append(evt)
                    else:
                        requeue.append(evt)
                for evt in requeue:
                    _pr.completion_queue.put(evt)
```

**共享队列的三消费者分工**(gateway/run.py:17807-17817 @ 863e313 post-turn drain 注释 +
`_drain_gateway_watch_events` 3410-3437):watch_match/watch_disabled → post-turn drain;
进程 completion → per-process watcher 任务;async_delegation → 本 watcher(boot 时
`_spawn_supervised` 启动,gateway/run.py:11531)。`_drain_gateway_watch_events` 先整批
detach 再 requeue 非己方事件,避免 `while not empty()` 里 requeue 造成死循环。

**重实现要点**:
1. 多消费者共享一条队列时,每类事件要有唯一属主;peek 型消费者必须先整批取出再 requeue。
2. 后台完成的"空闲投递"需要独立轮询者,post-turn 钩子只覆盖"恰有 turn 在跑"的情形。
3. 投递失败把事件放回队列(at-least-once),幂等靠上面第 6 节的去重层。

---

## 8. `_run_process_watcher`(22297-22485)——每进程 watcher 任务

**功能**:每个带 check_interval 的后台进程一个 asyncio 任务,周期检查,按
`display.background_process_notifications` 模式(all/result/error/off,
`_load_background_notifications_mode` gateway/run.py:8357-8382,env
`HERMES_BACKGROUND_NOTIFICATIONS` 优先,`false`→off)推送;进程退出/被杀自动收尾。

**四条退出路径**:
1. off 且非 agent_notify:静默等退出,只记日志(22327-22336);
2. agent_notify 且完成未被消费:构造 completion 事件走第 6 节投递管线(合成 agent turn);
3. 完成已被 wait/log 消费:跳过一切通知(#65379);
4. 其余:按模式直接 `adapter.send` 文本通知(非会话消息,`_non_conversational_metadata`)。

**#10156 与 #65379 的消费语义**:`poll()` 只读、**故意不标记 consumed**——状态查询不得吞掉
投递回合;`wait/log` 已把退出码和输出内联返回给 agent,再推原始"[Background process ...
finished]"就是同一完成的重复投递:

gateway/run.py:22405-22416 @ 863e313
```python
                # --- Normal text-only notification ---
                # Skip when the agent already consumed this completion via
                # wait/log (#65379): process(wait) returned the exit code and
                # output inline, so the raw "[Background process ... finished
                # with exit code ...]" message would be a duplicate delivery
                # of the same completion. The agent_notify branch above
                # already honors _completion_consumed; without this check its
                # skip FALLS THROUGH to this block and re-delivers the output
                # the agent is actively summarizing. poll() is read-only and
                # intentionally does not mark consumed (#10156), so a status
                # check never suppresses this message.
                if _pr_check.is_completion_consumed(session_id):
```

(`is_completion_consumed`:tools/process_registry.py:1217-1219 @ 863e313。)

**输出处理链**(agent_notify 分支,22356-22374):strip_ansi → redact_terminal_output
(命令感知脱敏)→ 命令本身 `_redact_gateway_user_facing_secrets` → **行边界截断**
(#23284:保尾部 ~2000 字符但 snap 到前一个换行,前置截断标记,通知绝不从行中间开始):

gateway/run.py:22363-22372 @ 863e313
```python
                    # Truncate at line boundaries so notifications never start
                    # mid-line (fixes #23284). Keep the last ~2000 chars but
                    # snap to the nearest preceding newline, then prepend a
                    # truncation marker when output was cut.
                    _LIMIT = 2000
                    if len(_raw) > _LIMIT:
                        _tail = _raw[-_LIMIT:]
                        _nl = _tail.find("\n")
                        _tail = _tail[_nl + 1:] if _nl != -1 else _tail
                        _out = f"[… output truncated — showing last {len(_tail)} chars]\n{_tail}"
```

投递 False(可重试)→ `continue` 下一轮再试(22399-22403:进程已 terminal,状态不会丢)。
运行中新输出仅在 all 模式且非 agent_notify 时推(22456-22483,尾部 500 字符,同样脱敏)。

**spawn 位置**:启动恢复(gateway/run.py:11464,crash-recovery checkpoint 的
pending_watchers,批 100 带 yield 防 O(n²) 阻塞)与 post-turn(17802,
`process_registry.pending_watchers` 整批 detach 防并发丢失)。

**重实现要点**:
1. 通知模式(all/result/error/off)与"agent 要不要被叫醒"(agent_notify)是两个正交开关。
2. 消费语义分级:读状态(poll)不消费,取结果(wait/log)消费;消费过的完成不得二次投递。
3. 用户可见输出三段处理:ANSI 剥离 → 秘密脱敏 → 行边界截断。
4. watcher 列表整批 detach(赋新 list)而非 clear(),防并发追加被吞。

---

## 9. cache busting 配置键(22487-22605)——哪些配置变更必须重建缓存 agent

**问题**:AIAgent 构造时把一批配置**冻进**实例(压缩器参数、上下文长度、工具 schema、
memory provider…),gateway 常驻运行中用户改 config.yaml,若缓存 agent 不失效,改动被
静默忽略,直到碰巧发生别的驱逐(换模型、/reset)。

**实现**:显式清单 `_CACHE_BUSTING_CONFIG_KEYS`(22497-22519):model.context_length/
max_tokens、compression.* 全套阈值、agent.disabled_toolsets、memory.provider、
checkpoints.*。`_extract_cache_busting_config`(22564-22605)拉平为 `section.key` dict;
缺失键记 None(**"absent"与"present-and-null"都参与签名**);legacy `checkpoints: true`
布尔式配置也兼容(22582-22585)。此外并入**工具注册表 generation**:

gateway/run.py:22571-22576 @ 863e313
```python
        The live tool registry generation is included too.  MCP reloads and
        dynamic MCP tool-list changes mutate the registry without necessarily
        changing config.yaml.  Cached AIAgent instances freeze their tool
        schemas at construction time, so a registry generation change must
        rebuild the agent before the next turn.
```

**Honcho 身份键**(22521-22562):peer_name/ai_peer/pin_peer_name/runtime_peer_prefix/
user_peer_aliases 住在 honcho.json 而非 config.yaml,**仅当 memory.provider==honcho 时读取**,
且按 honcho.json 的 mtime_ns 记忆化(`_HONCHO_CACHE_BUSTING_MEMO`,单槽 memo,22559 整字典
替换)——避免每条消息 stat+parse;非 honcho 时填 None 占位保持签名维度稳定(22600-22603)。

**重实现要点**:
1. "构造期冻结"的配置必须有显式失效清单,清单即文档(新增冻结配置=加一行)。
2. 缺失与 null 区分参与签名;签名维度集合要稳定(不因 provider 不同而增减键)。
3. 动态工具面(MCP 热加载)用注册表 generation 计数纳入签名,不依赖配置文件变更。
4. 外部文件型配置按 mtime 记忆化读取,签名计算在每条消息热路径上要廉价。

---

## 10. `_agent_config_signature`(22607-22679)——agent 缓存复用判据【重点】

**机制**:对 [model、api_key 指纹、base_url、provider、requested_provider、api_mode、
enabled_toolsets(排序)、ephemeral_prompt、cache_keys(排序)、user_id、user_id_alt、
skip_context_files] 做 JSON 序列化 + sha256 取 16 hex。签名变→弃缓存重建;不变→复用
(保住冻结的 system prompt 与工具 schema,换 provider prompt cache 命中)。
调用点:gateway/run.py:4583-4592(缓存查询前计算,同处传入 user_id/user_id_alt/
skip_context_files)。

**含什么、为何**:
- **api_key 全串 sha256 指纹**而非前缀——OAuth/JWT 常见公共前缀(`eyJhbGci`)会造成换号后
  假命中:

gateway/run.py:22646-22652 @ 863e313
```python
        import hashlib, json as _j

        # Fingerprint the FULL credential string instead of using a short
        # prefix. OAuth/JWT-style tokens frequently share a common prefix
        # (e.g. "eyJhbGci"), which can cause false cache hits across auth
        # switches if only the first few characters are considered.
        _api_key = str(runtime.get("api_key", "") or "")
        _api_key_fingerprint = hashlib.sha256(_api_key.encode()).hexdigest() if _api_key else ""
```

- **user_id/user_id_alt**:Honcho 在首消息 init 时把用户身份冻进 HonchoSessionManager;
  共享线程会话键(thread_sessions_per_user=False 时 build_session_key 故意不含参与者 id)
  下若不进签名,第二个用户会复用第一个用户的 agent,消息记到别人的 Honcho peer 头上
  (#27371 的 per-user-peer 契约被破坏)。**取舍**:共享线程里按用户重建 agent,
  用 prompt-cache 温度换记忆归属正确:

gateway/run.py:22630-22643 @ 863e313
```python
        ``user_id`` and ``user_id_alt`` are the runtime user identities
        carried by the current message's gateway source.  They participate
        in the cache key because the Honcho memory provider freezes them
        into ``HonchoSessionManager`` at first-message init (see
        ``plugins/memory/honcho/__init__.py::_do_session_init``).  Without
        them in the signature, a shared-thread session_key (one in which
        ``build_session_key`` intentionally omits the participant ID,
        e.g. ``thread_sessions_per_user=False``) would reuse the cached
        AIAgent across distinct users, causing the second user's messages
        to be attributed to the first user's resolved Honcho peer.  This
        broke #27371's per-user-peer contract in multi-user gateways.
        Per-user agent rebuilds in shared threads trade prompt-cache
        warmth for correct memory attribution.
```

- **skip_context_files**:改变冻结 system prompt 的内容(context files 进/出),toggle 必须重建
  (22671-22674)。
- **ephemeral_prompt**:会话上下文提示词并入(注意第 19 节的 pin 机制保证其字节稳定)。

**不含什么、为何**:
- **reasoning_config 排除**——它逐消息设在缓存 agent 上,不影响 system prompt 与工具
  (22665-22666 注释);
- 逐消息可变但不进冻结面的东西(思考深度、service tier)都不该赔上缓存。

gateway/run.py:22664-22667 @ 863e313
```python
                sorted(enabled_toolsets) if enabled_toolsets else [],
                # reasoning_config excluded — it's set per-message on the
                # cached agent and doesn't affect system prompt or tools.
                ephemeral_prompt or "",
```

**重实现要点**:
1. 签名的判据 = "是否改变构造期冻结面(system prompt / 工具 schema / 客户端身份)";
   逐回合可变参数一律排除,否则缓存形同虚设。
2. 凭据入签名用全串哈希,绝不用前缀。
3. 集合型输入(toolsets、cache_keys)先排序再序列化,`sort_keys=True` + `default=str` 保稳定。
4. 多用户共享会话键时,用户身份必须入签名(记忆归属 > 缓存命中)。
5. 签名短截(16 hex)够用——它只做等值比较,不做安全承诺。

---

## 11. session model override:rehydrate / apply / snapshot / restore(22681-22800)

**`_rehydrate_session_model_override`(22681-22741)**:`/model` 覆盖原为纯内存态,
gateway 重启即静默回落全局默认模型。修复:`/model` 时把**非机密部分**(model/provider/
base_url)写透 session store(/new 时清),重启后首次使用时读回,凭据走正常运行时解析
**重新求取**——api_key 永不落盘:

gateway/run.py:22684-22693 @ 863e313
```python
        ``_session_model_overrides`` is in-memory only, so before persistence
        a restart silently reverted every session to the global default model.
        The non-secret parts (model/provider/base_url) are written through to
        the session store when /model runs (and cleared on /new); here we read
        them back on first use and re-resolve credentials via the normal
        runtime provider resolution — api_key is never persisted to disk.

        No-op when an in-memory override already exists (live state wins) or
        when the store has nothing persisted (e.g. the user ran /new, which
        clears both the in-memory dict and the persisted field).
        ```
```

凭据重解析失败→保留无凭据覆盖,后续 `_resolve_session_agent_runtime` 用 env 解析兜底再叠加
model/provider(22720-22736)。调用点:gateway/run.py:6955(会话键解析后)。

**`_apply_session_model_override`(22743-22771)**:覆盖优先于 config.yaml 默认;None 值字段
跳过(部分覆盖不得踩掉有效默认);有 api_key 无 credential_pool 时按 provider 补池。
调用点:gateway/run.py:7044。

**snapshot/restore(22773-22794)**:`/model --once` 一回合切换——切换前
`_snapshot_session_model_override` 捕获 `{had_override, override}`,回合后
`_restore_pending_one_turn_model_restores`(gateway/run.py:15763-15776)经
`_restore_session_model_override` 还原,**并顺手 `_evict_cached_agent`**(22794:模型变了,
缓存 agent 必须弃)。`had_override` 区分"原本就没有覆盖"(还原为 None)与"有旧覆盖"(还原旧值)。

**`_is_intentional_model_switch`(22796-22800)**:供 config-drift 检测用——缓存 agent 的
model 与 config 默认不符时,若匹配活跃 /model 覆盖则是**有意切换**,不触发重建
(调用点 gateway/run.py:25439)。

**重实现要点**:
1. 会话级覆盖要持久化,但按"机密/非机密"分治:配置落盘,凭据每次重解析。
2. 内存态优先于持久态(live state wins);会话边界两边一起清。
3. 一次性覆盖 = snapshot(含"曾经没有"这一态)+ finally 还原 + 缓存驱逐。
4. 部分覆盖合并时 None 跳过,避免半份覆盖清掉默认值。

---

## 12. `_release_running_agent_state`(22802-22857)——running-turn 状态的唯一释放漏斗

**问题**:散落各处的 `del self._running_agents[key]` 曾漂移:有的只弹 `_running_agents`,
有的带 `_running_agents_ts`,只有一处清 `_busy_ack_ts`——每个漏掉的条目是 per-session
per-gateway-lifetime 的小型持久泄漏。

**实现**:收敛为单方法:释放跨进程 active-session slot lease(`state.turn.lease.release()`)
→ `state.turn.clear()` 结构化清空(agent/started_ts/lease/busy_ack_ts,
gateway/session_state.py:77-87 @ 863e313)→ `_persist_active_agents()` 刷新 dashboard 读数。
**turn-lease token 故意不清**(#64934,`_release_turn_lease` 独占属主);跨回合持久态
(model_override、voice_mode、pending_approvals…)不碰。带 `run_generation` 参数时先过
所有权守卫:

gateway/run.py:22826-22836 @ 863e313
```python
        When ``run_generation`` is provided, only clear the slot if that
        generation is still current for the session.  This prevents an
        older async run whose generation was bumped by /stop or /new from
        clobbering a newer run's state during its own unwind.  Returns
        True when the slot was cleared, False when an ownership guard
        blocked it.
        """
        if not session_key:
            return False
        if run_generation is not None and not self._is_session_run_current(
            session_key, run_generation
        ):
            return False
```

**重实现要点**:
1. 同一组状态的释放必须单点漏斗化,call site 复制 pop-list 必然漂移。
2. 释放按生命周期分层:turn 态一起清,conversation/persistent 态各有属主。
3. 异步 unwind 释放共享槽前必须验 generation 所有权,防旧回合踩新回合。

---

## 13. `_release_turn_lease` / `_rebind_turn_lease`(22859-22915)——turn lease 生命周期【重点】

**背景(#64934)**:多个路由键可映射到同一 session_id(alias:topic tip-walk、pinning、
/resume),两个键同时来消息会并发执行 [load history → run → flush],交错写坏 transcript。
`TurnLeaseRegistry`(gateway/turn_lease.py)按 **session_id** 维护 asyncio 锁,acquire 在
`_handle_message_with_agent` 的 history 加载前(gateway/run.py:16584-16593:token 与
run_generation 一起存进 `state.turn.lease_token/lease_generation`),超时 fail-open 返回
degraded token(turn 不串行化但绝不 wedge,turn_lease.py:191-207)。

**`_release_turn_lease`(22859-22886)**:token 存储按 (routing key, run generation) 配对,
双重防护——本方法只在 `turn.lease_generation == run_generation` 时弹 token;registry.release
(turn_lease.py:274-300)再做 holder 身份校验(`lease.holder is not token` → no-op),
stale unwind 永远释放不了新回合的锁:

gateway/run.py:22863-22868 @ 863e313
```python
        Companion to the acquisition in ``_handle_message_with_agent``
        (#64934). The token map is keyed by (routing key, run generation), so
        this can only ever free the lease its own turn acquired — a stale
        unwind whose generation was bumped by /stop or /new pops ITS token,
        and the registry's identity check refuses it if a newer turn already
        holds the lease. Idempotent and safe for bare test runners built via
        ``object.__new__`` (getattr defaults).
```

**`_rebind_turn_lease`(22888-22915)**:compression 可在回合中途轮转
`session_entry.session_id`,flush 目标变成新 id——串行化边界必须跟着走,否则解析到新 id 的
alias 键能开一个 lease 看不见的并发回合(#64934 rotation-alias 窗口)。调用点:
gateway/run.py:17172(hygiene 预压缩轮转)、17684(agent 内压缩轮转)。registry.rebind
(turn_lease.py:215-272)机制:**同一 `_SessionLease` 对象再注册到新 id**(旧映射留着等
idle 驱逐),两个 id 的 acquirer 串行在同一把锁上,不动 asyncio 内部;仅当前 holder 可
rebind;新 id 已有活锁时 merge 不可行→大声记日志、token 留在旧 id(fail-open,绝不
mid-turn 等待造成死锁):

gateway/turn_lease.py:229-238 @ 863e313
```python
        Mechanism: the SAME ``_SessionLease`` object is registered under the
        new id (the old mapping stays until it goes idle and is evicted), so
        acquirers on either id serialize against one lock — no lock state is
        moved, no asyncio internals are touched. Only the current holder can
        rebind (identity-checked like release), and the token follows to the
        new id so release frees the shared object.
```

**重实现要点**:
1. 串行化域按**持久会话 id**建锁,而非路由键——alias 才是并发根源。
2. token = (owner, generation) 双元身份,释放两级校验(本地 generation + registry holder 同一性)。
3. 会话 id 轮转时不迁移锁,而是**别名注册**同一锁对象;释放走 token 跟随的新 id。
4. 一切冲突路径 fail-open + 大声日志:降级为不串行,绝不 wedge 会话。
5. 幂等释放:degraded/re-release/stale 全是安全 no-op。

---

## 14. `_clear_conversation_scope`(22917-22968)+ 边界安全态清理(22970-23012)——唯一会话边界漏斗

**问题**:/new、/resume、auto-reset、过期 finalize、compression-exhausted auto-reset 这些
边界各自维护手抄 pop-list,每加一个 per-session dict 就漂移一次——#48031、#58403、#10702、
#35809 全是"边界 X 忘了 dict Y"(如 /new 清了 /model 覆盖却没清 --once 快照)。

**实现**:单一漏斗 = `state.conversation.clear()` 结构化清空
(gateway/session_state.py:113-129:model_override/one_turn_restore/reasoning_override/
service_tier_override/last_resolved_model/queued_events/sidecar_notes/ephemeral_pin/vc_last
九个字段一次归零)+ legacy 普通 dict 存量按 `_CONVERSATION_SCOPED_STATE` 注册表逐键弹
(gateway/run.py:2490-2506:该 tuple 现在保留是为 (a) 尚未折入 SessionState 的
`_pending_model_notes` 等,(b) 测试的公共契约)+ `_clear_session_boundary_security_state`:

gateway/run.py:22923-22932 @ 863e313
```python
        THE single conversation-boundary funnel. Call this — and nothing
        else — whenever a session_key crosses a conversation boundary:
        /new, /resume, auto-reset (idle/daily/suspended), expiry
        finalization, and the compression-exhausted auto-reset.

        Why a funnel: these boundaries used to each carry a hand-copied
        pop-list of the per-session dicts, and the lists drifted every time
        a new dict was added (#48031, #58403, #10702, #35809 were all
        "boundary X forgot dict Y" bugs — e.g. /new cleared the /model
        override but not the /model --once restore snapshot).
```

**作用域三分**(22937-22944 docstring):conversation 态清;turn 态不清
(`_release_running_agent_state` 与 dispatch finally 属主);**idle agent-cache 驱逐不是
会话边界**——会话还活着,恢复回合要从这些覆盖重建。调用点:gateway/run.py:12012(过期
finalize)、16387(auto_reset)、17919(/new 类边界)。

**`_clear_session_boundary_security_state`(22970-23012)**:边界必须作废的控制面——
pending skills-reload 注记、`persistent.approvals`(危险命令批准)、
`update_prompt_pending`、tools/slash_confirm 状态、tools/approval 的会话级批准
(`clear_session`)。安全态单列一个方法:它们住在 PersistentState(不随 conversation.clear
清),但**绝不能跨边界存活**(旧会话批准的危险命令不能自动放行新会话)。

**重实现要点**:
1. 边界清理 = 结构化状态类 + 单一漏斗方法;"加字段自动被所有边界清"是设计目标。
2. 状态按生命周期建模成三层(turn / conversation / persistent),清理属主各一,互不越权。
3. 安全授权类状态跨边界必须作废,即使它生命周期上属于 persistent 层。
4. 保留 legacy 注册表兼容测试契约,是渐进迁移的常见收尾形态。

---

## 15. run generation 四方法(23014-23063)——单调回合代币

`_begin_session_run_generation`:每个顶层 gateway turn 领一个单调递增 token;
`_invalidate_session_run_generation` 就是"再 bump 一次 + 记日志";
`_is_session_run_current` 比对;`_bind_adapter_run_generation` 把 generation 挂到 adapter
的 active-session interrupt event 上(供 adapter 侧识别过期回合)。

gateway/run.py:23017-23027 @ 863e313
```python
        Every top-level gateway turn gets a monotonically increasing token.
        If a later command like /stop or /new invalidates that token while the
        old worker is still unwinding, the late result can be recognized and
        dropped instead of bleeding into the fresh session.
        """
        if not session_key:
            return 0
        persistent = self._session_state(session_key).persistent
        # Monotonic by design (#28686): incremented here, NEVER reset.
        persistent.run_generation = int(persistent.run_generation) + 1
        return persistent.run_generation
```

**为何住 persistent 层且永不重置**(#28686,亦见 gateway/run.py:2484-2485 注释):清零会让
旧回合的 generation 意外"重新有效",打破 stale-run 检测。空 session_key 返回 0 且
`_is_session_run_current` 对空键恒 True(23043-23044,无键=无并发域)。

**重实现要点**:
1. "取消"建模为代币失效而非任务杀死:老 worker 自己 unwind,晚到结果凭代币识别丢弃。
2. 代币必须单调且永不重置——重置等于制造 ABA。
3. 失效 = 领新代币,同一原语两用(开始新回合 / 作废旧回合)。

---

## 16. `_interrupt_and_clear_session`(23065-23147)——中断 + 状态清理的组合动作

**流程**:(1) 对运行中 agent `request_hard_interrupt`,并捕获其 turn 进程 task_id 与
baseline;(2) **先 bump generation 再调度 reaper 线程**,闭包携带 bump 后的 generation:

gateway/run.py:23089-23098 @ 863e313
```python
        # Bump the generation *before* scheduling the reap thread and capture
        # the post-bump value: task_id is session-scoped (task_id ==
        # session_id), so if a replacement turn claims this session and
        # spawns its own process before the reap thread actually runs, that
        # claim bumps the generation again. The closure below then sees a
        # stale generation and skips — the replacement turn's own baseline
        # covers its own cleanup, so nothing is left permanently unreaped.
        _generation_at_interrupt = self._invalidate_session_run_generation(
            session_key, reason=invalidation_reason
        )
```

`_reap_gateway_turn_processes`(gateway/run.py:2841-2900)在 daemon 线程上按 baseline 杀
"该回合起动的"后台进程;`is_still_current` 闭包防止杀掉替换回合的新进程(task_id 是会话
粒度而非回合粒度,replacement turn 的进程会落在同一 task_id 下);空 task_id 直接返回
(2861-2864:空 id 会匹配所有 sessionless 进程)。

(3) 调 adapter 的 `interrupt_session_activity`(用 `inspect.signature` 探测是否接受
metadata,23119-23131——适配器接口渐进演化的兼容层);(4) 消费并丢弃 pending message、
清 `pending_command_text`;(5) `release_running_state=True` 时释放 turn 态 + **驱逐缓存
agent**(#44212):

gateway/run.py:23138-23147 @ 863e313
```python
            # Evict the cached agent: ``_interrupt_requested`` is only
            # cleared by the turn finalizer, so on a hung or still-draining
            # run the flag survives the lock release and kills the session's
            # NEXT message at the top of the tool loop (interrupted=True,
            # api_calls=0, empty response — silently swallowed, #44212).
            # Evicting mirrors the /new and /model paths: the next message
            # rebuilds the agent from session history, while the old agent
            # object keeps its interrupt flag so a hung drain still dies
            # when it unblocks.
            self._evict_cached_agent(session_key)
```

调用点:gateway/run.py:14190、14208(/stop、/new 类命令路径)。

**重实现要点**:
1. 中断的完整语义 = 中断标志 + 代币作废 + 子进程 reap + 适配器活动打断 + 状态释放 + 缓存驱逐,
   缺一个就有对应的事故(#44212 是缺"驱逐")。
2. 中断标志留在旧 agent 对象上(挂死的 drain 解冻时自杀),新消息用重建的干净 agent。
3. reaper 与 replacement turn 的竞态用"闭包携带中断时刻 generation"解决。
4. 对第三方接口(adapter 方法签名)用运行时探测做前向兼容。

---

## 17. `_refresh_agent_cache_message_count`(23149-23222)——跨进程一致性守卫的自写豁免

**问题(#45966)**:缓存 agent 旁存了构建时的 on-disk `message_count` 快照,下一回合比对
DB 现值,不一致→判定"别的进程改了 transcript"→重建 agent。但快照在 agent **构建时**取,
本回合自己写入 user/assistant/tool 行就会推高计数——不重刷快照的话,**每回合都会自己触发
重建**,per-conversation prompt cache 全灭。

**实现**:回合完成、agent flush 后重新快照现计数,使守卫只对**其他进程**的改动开火。
持锁校验缓存条目仍是同一 agent(重建/驱逐竞态则放弃);**4 元组(#54947)条目若快照
session_id 与当前不同——缓存属于同 session_key 下另一个会话——不动快照**,否则会拿当前
会话的计数腐蚀原会话的基线,切回去时守卫误触发;legacy 3 元组保形重写:

gateway/run.py:23206-23222 @ 863e313
```python
                # If the snapshot was taken for a different session_id
                # (same session_key, different conversation), leave the
                # snapshot alone — the current session_id's count belongs
                # to a different DB row (#54947).
                _snapshot_sid = cached[3] if len(cached) > 3 else None
                if _snapshot_sid is not None and _snapshot_sid != session_id:
                    return
                if cached[2] != _live:
                    if _snapshot_sid is None:
                        # Legacy 3-tuple: preserve the original 3-element
                        # shape so existing entries stay compatible with
                        # callers that index ``cached[2]`` directly.
                        _cache[session_key] = (cached[0], cached[1], _live)
                    else:
                        _cache[session_key] = (
                            cached[0], cached[1], _live, _snapshot_sid,
                        )
```

fail-safe:DB 错误保持旧快照,最坏多一次不必要重建(23170-23172)。调用点:
gateway/run.py:18111、25763(回合收尾两条路径);17641 注明有一处**故意推迟**。

**重实现要点**:
1. "外部改动检测"守卫必须豁免自己的写入:写后重新基线化。
2. 快照更新要持锁验证"还是同一个条目"(anti-ABA)。
3. 多会话共用缓存键时,快照必须绑定 session_id,跨会话不得互相覆写基线。
4. 缓存条目结构演化(3 元组→4 元组)保形兼容旧索引方式。

---

## 18. sidecar notes(23224-23268)——一次性"必达注记"通道

`_set_pending_turn_sidecar_notes` / `_consume_pending_turn_sidecar_notes`:staging 在
`conversation.sidecar_notes`,消费即清(one-shot)。staged 未消费的注记不得漏进未来会话
——所以它在 `_CONVERSATION_SCOPED_STATE` 注册(gateway/run.py:2502-2505:
"session keys are source-derived and REUSED")。写入点 gateway/run.py:17518,消费点 4914
(agent turn 组装 user message 时)。

`_voice_channel_sidecar_note`(23240-23268):Discord 语音频道上下文**只在变化时**注入
`[Voice channel now: ...]`(含离开频道→"not connected");上次值存
`conversation.vc_last`。**设计理由**:VC 成员/说话状态逐回合序列化会持续搅动 prompt
(打破 prefix cache 且噪音),diff-only 注入把它变成事件流。

**重实现要点**:
1. 环境状态(在哪个语音频道)以 diff 事件注入,不逐回合全量序列化——prompt 稳定性优先。
2. one-shot 通道必须挂在 conversation 生命周期上,防跨会话泄漏(键会被复用)。

---

## 19. pinned session context prompt / ephemeral change key(23270-23372)

**问题**:会话上下文提示(平台/频道/用户名/home channel…渲染出的 system prompt 组件)若每
回合重渲,渲染器的任何非确定性(dict 序、集合序)都会改变字节→系统提示变→prompt cache 全 miss。

**实现**:per-session pin。`_ephemeral_change_key`(23295-23372)把
`build_session_context_prompt` **实际渲染的全部输入**打包哈希(platform、chat_id/thread/
type/name/topic、user_name/id、profile、shared_multi_user_session、Discord id 组、
Discord/Slack 工具加载门、connected_platforms、home_channels、redact_pii、home 显示路径);
键命中→pin 的字节**逐字复用**;miss→重渲 + 重 pin(改名、改 topic、/sethome、redact 开关
都是正当 bust):

gateway/run.py:23299-23305 @ 863e313
```python
        This key decides when the pinned per-session context-prompt bytes are
        reused verbatim vs re-rendered.  The maintained invariant (guarded by
        the parity test in tests/gateway/test_prompt_tail_freeze.py): any
        input whose change alters the rendered bytes MUST appear here —
        omission means a stale pinned prompt (cosmetic staleness); inclusion
        of an extra field only costs a spurious re-render.
```

**不对称错误代价**是键设计的核心:漏字段=陈旧(化妆性错误),多字段=多一次重渲(便宜)。
两个精细点:(1) Discord message_id 只取**有无**("1"/"0")——值本身逐回合在 user message 里
投递,键上取值会每条消息重渲零字节变化(23322-23325);(2) Slack/Discord 的工具加载门
(`_slack_tools_loaded()`)进键——MCP 注册翻转要重渲一次而非整个会话陈旧(23328-23337)。
pin 存 `conversation.ephemeral_pin=(key, text)`;`_evict_cached_agent` 时与 `vc_last` 一起
置空(23398-23404:新 agent 必须重渲一次、重见一次 VC 状态)。消费点:gateway/run.py:16437。

**重实现要点**:
1. 组合进 system prompt 的动态组件要 pin 字节,免疫渲染非确定性;失效键覆盖"渲染实际读取的
   全部输入",并写 parity 测试锁住这个不变量。
2. 键字段的取舍准则:漏=陈旧、多=白渲;凡"值逐回合变但渲染只看有无"的输入,键上只取存在性。
3. pin 生命周期绑 agent 缓存:agent 重建 ⇒ pin 作废。

---

## 20. `_evict_cached_agent`(23374-23443)+ `_init_cached_agent_for_turn`(23445-23471)

**`_evict_cached_agent`**:弹缓存条目 + **主动软释放** LLM client 池。为什么不等 GC:

gateway/run.py:23377-23383 @ 863e313
```python
        Pops the entry AND soft-releases the evicted agent's LLM client
        pool so the httpx connection (sockets + held buffers) is freed
        promptly rather than waiting on CPython GC — AIAgent holds
        reference cycles (callbacks, tool state) that delay refcount
        collection, so a manual release is required to keep gateway RSS
        flat across many /new, /model, undo and reset operations (#29298,
        same leak class as #25315).
```

软释放(`release_clients()`)保留终端沙箱/浏览器 daemon/追踪的后台进程(按 task_id 键),
会话可用新 agent 恢复;真边界(/new)的调用方已先做过 `_cleanup_agent_resources` 硬拆,
release_clients 幂等可再跑(23385-23392)。**mid-turn 保护**:被弹 agent 若在
`_running_agents` 中(按 `id()` 比对)则不拆(23420-23428)。清理放 daemon 线程,绝不持
`_agent_cache_lock` 等慢 socket teardown(23394-23396)。

**`_init_cached_agent_for_turn`**(staticmethod,复用缓存 agent 前的回合态重置):
活动三元组(ts/desc/provenance)**仅 depth 0 重置**——它们是语义整体,interrupt 递归回合保留
以便 inactivity watchdog 累计 stuck-turn 空闲时间触发 30min 超时(#15654);depth-0 重置
本身防"闲 29 分钟的会话在新回合首次 API 调用前就被 watchdog 误杀"(#9051)。另外重置
SessionDB flush 游标:

gateway/run.py:23460-23471 @ 863e313
```python
        if interrupt_depth == 0:
            from agent.session_activity import ActivityProvenance

            agent._last_activity_ts = time.time()
            agent._last_activity_desc = "starting new turn (cached)"
            agent._last_activity_provenance = ActivityProvenance.UNKNOWN
            # Reset the SessionDB flush cursor so the new turn's messages are
            # fully persisted - a stale value from the previous turn would
            # cause `_flush_messages_to_session_db` to skip new rows (#44327).
            if hasattr(agent, "_last_flushed_db_idx"):
                agent._last_flushed_db_idx = 0
        agent._api_call_count = 0
```

调用点:gateway/run.py:4753(缓存命中复用前)。

**重实现要点**:
1. 有引用环的重资源对象,驱逐时必须显式释放连接池,不能赌 GC。
2. 驱逐分软/硬两档:软保会话工具态(可恢复),硬走真边界;软释放幂等以便叠加。
3. 驱逐前查 running 集(按 id()),mid-turn 对象只出缓存不拆资源。
4. 复用缓存对象前有明确的"回合态重置"清单(活动戳、flush 游标、API 计数),且区分外层/递归回合。

---

## 21. memory commit before soft evict(23473-23566)

**问题(#11205 LRU-cap 变体)**:on_session_end(记忆抽取钩子)属主是
`_session_expiry_watcher`——它在会话到期时对 `_agent_cache` 里找到的 agent 做 teardown。
若 LRU cap 在**到期前**软驱逐了 finalizable 会话的 agent,watcher 届时找不到 agent,
on_session_end 静默跳过,记忆 provider 永远看不到该 transcript。

**实现**:cap 驱逐路径在手里还握着"活的、作用域完整的 agent"时就地补偿——调
`commit_memory_session`(**抽取但不拆 provider**),驱逐保持软、恢复回合照常工作。
触发条件三连:有 memory manager;会话 finalizable(finite reset policy——mode="none" 的
watcher 永不运行,没有"错过的边界"要补);**尚未过期**(过期的由 watcher 直接拆):

gateway/run.py:23511-23520 @ 863e313
```python
            # Only compensate when the watcher would otherwise expect to find
            # this agent at expiry (finite policy, not yet expired). Expired
            # sessions are torn down by the watcher directly; mode="none"
            # sessions are never finalized.
            if not _store.is_session_finalizable(entry):
                return
            if _store._is_session_expired(entry):
                return
            messages = getattr(agent, "_session_messages", None)
            agent.commit_memory_session(messages if isinstance(messages, list) else None)
```

`_commit_then_release_soft`(23528-23537):daemon 驱逐线程上的组合子,**顺序敏感**——
commit 用活 agent 的 memory manager,必须在 `release_clients` 丢掉消息缓冲之前。
`_release_evicted_agent_soft`(23539-23566):release_clients(无则回退旧版全拆)+
清 `_session_messages`(重 session 上可达数十 MB;下一回合从持久化 JSON 重建,丢内存副本安全)。

**重实现要点**:
1. 生命周期钩子(on_session_end)有唯一属主时,任何"提前拿走属主依赖的资源"的路径都要补偿。
2. 补偿动作选"抽取不拆除"变体,保持驱逐语义仍是软的。
3. 补偿条件对齐属主的触发条件(finalizable 且未过期),否则重复或多余。
4. 网络型补偿必须在 daemon 线程做,绝不持缓存锁阻塞。
5. 大内存缓冲(消息历史)驱逐时显式置空,前提是它可从持久层重建。

---

## 22. `_enforce_agent_cache_cap`(23568-23648)——LRU 上限执行

`_AGENT_CACHE_MAX_SIZE = 128`(gateway/run.py:74);`_agent_cache` 是 OrderedDict
(命中 move_to_end,插入后调本方法,调用点 gateway/run.py:4842;须持 `_agent_cache_lock` 调用)。

**关键决策:mid-turn agent 跳过且不找替罪羊**——只把 LRU 前 `size-cap` 个位置视为候选,
候选中活跃的跳过,**不**转而驱逐更新的条目:

gateway/run.py:23600-23608 @ 863e313
```python
        # Walk LRU → MRU and evict excess-LRU entries that aren't mid-turn.
        # We only consider entries in the first (size - cap) LRU positions
        # as eviction candidates.  If one of those slots is held by an
        # active agent, we SKIP it without compensating by evicting a
        # newer entry — that would penalise a freshly-inserted session
        # (which has no cache history to retain) while protecting an
        # already-cached long-running one.  The cache may therefore stay
        # temporarily over cap; it will re-check on the next insert,
        # after active turns have finished.
```

running 判定用 `id()` 集合(O(1) 且不依赖 AIAgent.__eq__——tests 里 MagicMock 会覆写 eq,
23591-23593)。先在锁内批量 pop,释放(含第 21 节的 memory commit)全部丢 daemon 线程;
超 cap 未能清完→warning,下次插入重查。测试 fixture 换成普通 dict 时静默跳过(23586-23589,
duck-type `move_to_end` 探测)。

**重实现要点**:
1. 容量执行допуска临时超限:正确性(不拆活对象)> 严格上限。
2. 跳过活跃候选时不得驱逐"更新的"补偿——那会形成对长驻会话的保护偏置。
3. 锁内只做指针操作,一切慢清理下放线程。
4. 对象身份比较用 id(),不用 __eq__(mock 安全 + O(1))。

---

## 23. `_sweep_idle_cached_agents`(23650-23736)——空闲 TTL 清扫【重点】

`_AGENT_CACHE_IDLE_TTL_SECS = 3600.0`(gateway/run.py:75);由 `_session_expiry_watcher`
周期调用(gateway/run.py:12064),内部自取锁。跳过 mid-turn(同 cap 路径)。

**核心分叉:idle 到点 ≠ 一定驱逐**。会话未过期且 finalizable(如 daily-reset,重置点在
用户最后消息数小时后)→**保留** agent,让过期 watcher 届时还能拿到活 transcript 调
on_session_end(#11205 follow-up);mode=="none"(永不 finalize)→必须驱逐,否则 agent
在缓存里钉一辈子——恰是本清扫要解决的泄漏;finite 但被 LRU cap 提前驱逐的情形由第 21 节的
commit 补偿覆盖:

gateway/run.py:23693-23706 @ 863e313
```python
                    # BUT only defer when the watcher will EVER finalize this
                    # session.  For a mode == "none" session the watcher never
                    # fires (is_session_finalizable() is False), so deferring
                    # would pin the agent in cache for the gateway's entire
                    # lifetime — the exact leak this idle sweep exists to
                    # relieve.  Those sessions fall through to soft eviction
                    # WITHOUT on_session_end, and that is correct: a mode=="none"
                    # session never reaches a session-end boundary, so there is
                    # no missed on_session_end to compensate for.  (The finite
                    # case — a session evicted under LRU-cap pressure before it
                    # expires — is instead covered by _commit_memory_before_soft_
                    # evict on the cap path, which fires on_session_end via the
                    # live agent's memory manager before releasing it.)
```

由此三条驱逐路径 × on_session_end 责任成一张闭合矩阵:
- 过期 watcher 拆除:自己调 on_session_end(属主);
- cap 驱逐 finalizable-未过期:`_commit_memory_before_soft_evict` 补偿;
- idle 驱逐:finalizable-未过期→推迟不驱逐;none→驱逐且无需补偿(无边界语义)。

**重实现要点**:
1. TTL 清扫要与"会话终结钩子的属主"协调:钩子还没机会跑的对象不能先清。
2. "永不终结"的会话类别必须显式识别并放行驱逐,否则推迟逻辑自身成为泄漏。
3. 三方(cap/TTL/expiry)驱逐路径对同一钩子的责任要画成完备矩阵,缺一格就是 #11205 类事故。

---

## 24. `_get_proxy_url`(23742-23756)

代理模式配置读取:`GATEWAY_PROXY_URL` env 优先(Docker 便利),否则 config.yaml
`gateway.proxy_url`;均 rstrip("/");无配置返回 None。是 proxy 转发段(23758 起,下一段)
的开关。

---

## 文档-代码冲突候选

1. **README/docs 对后台通知模式的描述**:代码默认 `all` 且接受 `display.
   background_process_notifications: false` 视为 off(gateway/run.py:8368-8372);若 docs
   只写四个字符串枚举,遗漏布尔兼容,属文档不全。待与 website/docs 对照。
2. **"exactly-once" 表述**:`_deliver_completion_notification` docstring 明确
   "No cross-process exactly-once guarantee is claimed"(22104-22105),
   `_inject_watch_notification` 明确 at-least-once 重放窗口(21917-21919);若任何文档把
   后台完成投递描述为"恰好一次",以代码为准(至多一次/生命周期内去重 + durable
   at-least-once)。
3. **`_CONVERSATION_SCOPED_STATE` 的双轨状态**:注释声明状态已迁入
   `SessionState.conversation`、tuple 仅为 legacy dict(`_pending_model_notes`)与测试契约保留
   (gateway/run.py:2467-2476);但 22957-2964 的运行时循环仍会遍历全部名字——依赖
   `isinstance(store, dict)` 守卫跳过 SessionState 视图。若 docs/AGENTS.md 仍把该 tuple
   描述为唯一清单,已过时。
4. **#54878 × #54947 交互**:gateway/run.py:4599-4612 注明"no existing upstream issue
   tracks this combination as of 2026-07-12"——两个已修 issue 的组合缺陷仅在代码注释里
   被记录,任何 issue 索引型文档都不会有它。

## 调用关系汇总(段外)

- 上游:`_handle_message_with_agent` 段(第 8 段)—— 15883(image mode)、15921/19545
  (vision enrich)、16437(pinned prompt)、16584-16593(lease acquire)、17172/17684
  (lease rebind)、17452/17518(sidecar)、17802(watcher spawn)、17824(watch 注入)、
  18111/25763(count 重基线)、4583(签名)、4753(缓存回合重置)、4842(cap 执行)。
- 启动:11464(恢复 watcher)、11531(async delegation watcher spawn)、12064(idle sweep,
  expiry watcher 内)。
- 平台/工具层:gateway/wake.py:45/56(push 判定/唤醒投递);gateway/turn_lease.py:154/215/274
  (acquire/rebind/release);tools/async_delegation.py:383/414/450/472(durable claim 状态机);
  tools/process_registry.py:174(completion_queue)/1217(is_completion_consumed);
  agent/image_routing.py:461(决策表);gateway/session_state.py:52/91/132(三层状态类)。
