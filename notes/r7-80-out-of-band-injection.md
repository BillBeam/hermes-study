# r7-80 · 带外注入:后台唤醒(wake)与忙时转向(steer)(主线亲读)

> 基线 @ 863e313。覆盖:gateway/wake.py(184 行,全文)、
> run.py 忙时总入口的 steer/redirect/降级决策块(8867-9003)与 internal 事件护栏。
> "带外" = 不经用户正常发消息路径,把文本塞进一个已存在(可能正在跑)的会话。

## 机制 1:后台完成唤醒 deliver_wake(wake.py)

### 场景/问题
后台工作(delegate_task background=True、terminal notify_on_complete、cron)完成时,
原会话的回合早已结束。要把完成结果作为**新回合**回注会话。难点:不同平台的"回注"
能力天差地别——Telegram 能主动 push,API server 是无状态请求/响应,连"往哪推"都不存在。

### 实现
- 按适配器能力位 `supports_async_delivery` 二分策略(gateway/wake.py:3-24):
  - **push 型**(telegram/discord/插件平台…):构造合成事件
    `MessageEvent(text, TEXT, source, internal=True)` 走 `adapter.handle_message`
    ——与真实消息同管道(73-87);`internal=True` 是后续所有护栏的标记。
  - **无状态型**(API server,`supports_async_delivery=False`):不能走 handle_message,
    因为那会用 `build_session_key()` 派生键(`agent:main:api_server:group:<sid>`),
    与真实网关回合用的裸 `X-Hermes-Session-Id` 键**永不相同**,唤醒会落进一个平行的、
    没人看的会话。改为**自 POST** 到进程内 API server 的 `/v1/chat/completions`,
    带裸 session id 头——与真实回合完全同一入口,续的是真会话(10-20、97-134)。

`gateway/wake.py:10-20 @ 863e313`
```python
* Stateless request/response adapters (the API server,
  ``supports_async_delivery = False``): ``handle_message`` would run the wake
  turn under a ``build_session_key()``-derived key
  (``agent:main:api_server:group:<sid>``) that NEVER matches the raw
  ``X-Hermes-Session-Id`` key real gateway/HQ turns run under
  (``_bind_api_server_session``), so the wake lands in a parallel, invisible
  session. Instead we self-POST ``/v1/chat/completions`` on the in-pod API
  server with the raw session id in the ``X-Hermes-Session-Id`` header — the
  exact entry point real turns use — so the wake turn resumes the REAL
  session, with full history, and its result is visible the next time the
  client polls/reopens the conversation.
```
- `adapter_supports_push`(45-53):能力位读**适配器类**而非 request-scoped contextvar
  (`session_context.async_delivery_supported` 的镜像)——后台 watcher 运行在任何已绑定
  会话上下文之外;未声明该位 = push 型。
- 自 POST 细节(97-184):通配绑定地址(0.0.0.0/::/*)改连 loopback(111-113);裸 IPv6
  加方括号(123-124);`API_SERVER_KEY` 缺失是**硬错误**——未认证的 API server 会 403 掉
  X-Hermes-Session-Id 续会话,与其让唤醒跑进一个没人看的指纹派生新会话,不如响亮失败
  (104-107、116-121);同步整回合超时 600s(34-36);429(全局 max_concurrent_runs 并发帽)
  按 (2,5,10)s 退避重试,≥400 其余立即失败(138-162);**失败一律 raise**,让调用方回卷
  游标/重试,不许静默丢事件(21-23、69-71)。
- 注:API server 无每会话锁,同会话并发回合 last-writer-wins(39-41 注释自认)。
- 行为规格:tests/gateway/test_wake_delivery.py(本轮跑通;含"裸 session id 头 + bearer +
  stream=false"与"429 退避后成功"两用例)。

### 设计理由与取舍
- "回注必须走真实入口"是两分支共同原则:push 型走 handle_message(享受全部守卫),
  无状态型走 HTTP 入口(享受同一会话绑定)。**不造第三条特权通道**。
- 失败上抛而非吞:唤醒事件的调用方(watcher)持有游标,只有它能决定重投;静默丢 = 用户
  永远等不到完成通知。

### 重实现要点
1. 平台"能否主动推"做成适配器类能力位;后台路径读类属性,不读请求上下文。
2. 无状态渠道的回注要走它的**真实请求入口**,伪造内部事件会造出平行会话。
3. 唤醒失败必须让持游标者感知;重试只对可恢复错误(429/连接类)。
4. 认证缺失时宁可硬失败,不要让事件落进没人能看到的会话。

## 机制 2:internal 事件护栏(gateway/run.py:8867-8879)

### 场景/问题
唤醒/完成类合成事件如果被当成用户文本,在 busy 会话上会按 busy_text_mode 默认打断正在跑的
回合并回一句"⚡ Interrupting current task"——与"完成结果只在空闲时作为新回合浮出"的
设计不变量正相反。

### 实现
`gateway/run.py:8867-8879 @ 863e313`
```python
        # --- Internal synthetic events must never interrupt/steer ---
        # Async-delegation completions (delegate_task(background=true)) and
        # background-process completions (terminal notify_on_complete) re-enter
        # the originating session as internal MessageEvents. When the session
        # is busy, treating them like a user TEXT message means interrupt-mode
        # (the default busy_text_mode) aborts the active turn AND sends a "⚡
        # Interrupting current task" ack — exactly the opposite of the design
        # invariant that a completion surfaces as a NEW turn only when idle and
        # never splices into a running turn. Fall through to the base adapter,
        # which queues internal events silently (no interrupt, no ack) so they
        # cascade after the current turn finishes.
        if getattr(event, "internal", False):
            return False
```
返回 False = 交回 base 适配器静默排队,当前回合结束后级联处理。
行为规格:tests/gateway/test_internal_event_never_interrupts_busy_session.py(本轮跑通)。

### 重实现要点
1. 合成事件必须带可判别标记,并在**每个**会打断用户工作的分支前挡下。
2. "完成通知只在空闲时浮出"要写成不变量并配测试,否则每加一种带外事件就回归一次。

## 机制 3:忙时输入策略与 steer 注入(gateway/run.py:8884-9003)

### 场景/问题
agent 正跑长任务,用户又发来消息。四种合理处置:打断(interrupt)、排队(queue)、
中途转向(steer:把话塞进正在跑的回合)、重定向(redirect:支持该能力的 agent 原地换目标)。
错误处置的代价不对称:一句闲聊打断几分钟的子代理任务是灾难;把 /stop 排队等于失去刹车。

### 实现
- 模式装载:`_load_busy_input_mode`(8278-8288)——env `HERMES_GATEWAY_BUSY_INPUT_MODE` >
  config `display.busy_input_mode`;合法值 queue/steer,**其余一律回落 "interrupt"(默认)**。
  `_load_busy_text_mode`(8291-8312)是 TEXT 消息的窄化旋钮:legacy 显式设置优先,
  否则跟随 busy_input_mode("queue" if input_mode=="queue" else "interrupt")。
- 决策序(`_handle_active_session_busy_message` 尾段,主线亲读 8859-9003):
  1. internal 事件 → 静默排队(机制 2)。
  2. TEXT ∧ busy_text_mode=queue ∧ 非 steer 模式 → return False 交 base 排队(8886-8891)。
  3. **两个自动降级**(interrupt → queue):运行中 agent 有活跃子代理(#30170,
     `_agent_has_active_subagents`,8905-8915)、或该会话压缩飞行中(#56391,8916-8926)。
     注释点明:显式 /stop、/new 走 `_interrupt_and_clear_session`,**不受降级影响**——
     操作员永远有强制刹车。
  4. steer 模式(8929-8961):`_prepare_busy_steer_text` 先行(含语音转写折叠——纯语音
     跟进消息把转写并进 steer 文本,否则语音在 steer 模式静默退化为 queue,#58780,
     8931-8938);可 steer 条件 = 有文本 ∧(纯文本无媒体 ∨ 全部媒体都是已折叠语音)∧
     agent 已真实存在(非 pending 哨兵)∧ 有 `steer()` 方法(8939-8952);
     `running_agent.steer(steer_text)` 成功 → steered;**任何失败回落 queue**,消息不丢
     (8953-8961)。
  5. interrupt 模式的 redirect 特例(8962-8976):纯文本 ∧ agent 声明
     `_supports_active_turn_redirect` ∧ 有 `redirect()` → 原地转向,不打断。
  6. 收尾(8978-8994):**steer/redirect 成功的消息不再入队**(已进回合,再排队会重放);
     其余走 `_queue_or_replace_pending_event` FIFO——不用 merge_text 的原始合并,因为
     newline 合并会把两条独立消息糊成一个回合,毁掉消息边界(#43066 sub-bug 2);
     FIFO 保证每条文本各占一回合、到达序,媒体连拍(相册)仍保留合并语义。
- steer 的 agent 侧(邻簇,R2 已学):`AIAgent.steer()` 把文本放入回合内 steer 队列,
  循环在迭代间隙消费——网关只负责判定与投递。

### 设计理由与取舍
- 默认 interrupt 而非 queue:单人对话里"新消息优先"符合直觉;但用两个自动降级保护
  高价值在飞工作(子代理、压缩),把"什么时候不该打断"编码成机制而不是文档。
- steer 一切失败都落 queue:带外注入是尽力而为,丢消息不可接受。
- 消息边界神圣:排队用 FIFO 而不是文本拼接;这是从事故(#43066)学来的。

### 重实现要点
1. busy 处置做成显式模式机(interrupt/queue/steer/redirect),配**基于在飞工作价值**的
   自动降级,而不是一刀切。
2. steer 的先决条件要检查到"agent 真实存在且有该方法",失败静默降级为排队。
3. 语音等富媒体要在 steer 前折叠成文本,否则该模式对它们静默失效。
4. 成功注入的消息绝不能再入队(双投);失败注入的消息绝不能丢(必入队)。
5. 排队保消息边界:每条消息一回合,合并只对天然连拍媒体。
