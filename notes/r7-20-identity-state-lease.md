# r7-20 · 会话身份、状态容器与回合租约(主线亲读)

> 基线 @ 863e313。本篇覆盖:gateway/session_context.py(495 行)、session_state.py(476 行)、
> turn_lease.py(302 行)、run.py 中 run generation 机制(23014-23063)与租约挂接点。
> 全部由主线逐行亲读,证据即读到的原文。

## 机制 1:contextvars 会话上下文(session_context.py)——并发下"我是谁"的正确答案

### 场景/问题
网关用 asyncio 并发处理多条消息。旧实现把会话身份写进 `os.environ`
(`HERMES_SESSION_PLATFORM` 等)——进程全局,消息 A 的值被消息 B 覆盖,后台通知与工具调用
路由错线程。

`gateway/session_context.py:10-18 @ 863e313`
```python
The gateway processes messages concurrently via ``asyncio``.  When two
messages arrive at the same time the old code did:

    os.environ["HERMES_SESSION_THREAD_ID"] = str(context.source.thread_id)

Because ``os.environ`` is *process-global*, Message A's value was
silently overwritten by Message B before Message A's agent finished
running.  Background-task notifications and tool calls therefore routed
to the wrong thread.
```

### 实现
- 17 个 `ContextVar`,默认值是哨兵 `_UNSET`(区分"从未设过"与"显式清空"):
  `session_context.py:46,74-128`。`get_session_env(name)` 的解析顺序:ContextVar 已设(哪怕
  空串)→ 直接返回、**不回落**;`_UNSET` → 回落 `os.environ`(CLI/cron/测试兼容)→ default
  (`session_context.py:363-386`)。
- **三态生命周期**是精髓:
  - `set_session_vars(...)`(206-271)绑定全部变量,返回 tokens;
  - `clear_session_vars(tokens)`(274-312)处理器**退出**时调用:一律 `var.set("")`
    ——"显式清空",抑制 os.environ 回落;docstring 明说 tokens 仅为 API 兼容,
    实际不用 `reset(token)`,即**不可嵌套**;
  - `reset_session_vars()`(315-360)处理器**入口**时调用:一律 `var.set(_UNSET)`,
    恢复"从未绑定"。
- 为什么入口要 reset:**跨会话 ContextVar 继承泄漏**。`create_task` 会 `copy_context`,
  消息 B 的任务从"消息 A 已 set 过"的上下文里 spawn 出来,B 绑定自己之前的窗口内,
  B 起的子进程会以 A 的身份运行:

`gateway/session_context.py:324-336 @ 863e313`
```python
    🔴 Why this exists — the cross-session ContextVar inheritance leak.
    Each gateway message is processed in its own ``asyncio`` task, created via
    ``create_task`` (which snapshots the *current* context with
    ``copy_context``).  When message B's task is spawned from a context where a
    concurrent message A had already called :func:`set_session_vars`, B inherits
    A's **set** ContextVars.  Until B calls its own ``set_session_vars`` there is
    a window where any subprocess B spawns (e.g. a tool shelling out) reads
    *A's* ``HERMES_SESSION_*`` identity via the subprocess-env bridge.  The
    bridge's ``_UNSET``-strip guard cannot help: the vars are not ``_UNSET``,
    they are set-to-A.
```
  行为规格:tests/gateway/test_session_context_inheritance.py(本轮跑通)。
- **进程级 engaged 闩锁**:`_session_context_engaged`(60)首个 `set_session_vars` 置 True、
  永不回落("Monotonic latch",52-59)。子进程 env 桥(tools/environments/local.py)据此
  切换策略:engaged 后 ContextVar 为权威、`_UNSET` 表示"本任务无会话"→ **剥离**
  os.environ 镜像,防止最后写者的身份泄进子进程;never-engaged(纯 CLI)保留旧回落。
  一次性 runner 声明"无异步投递能力"要用 `declare_stateless_channel()`(441-463)而不是
  `set_session_vars(async_delivery=False)`,就是为了不误触这个闩锁。
- `set_current_session_id`(151-186):CLI `/new`/`/resume`/压缩换代时同步 ContextVar 与
  os.environ 两条存储;**委派子代理例外**——子代理在父进程内构造,写 os.environ 会把子
  会话 id 泄给父进程后续工具,故只写 task-local 的 ContextVar。
- `async_delivery_supported()`(466-495):`_UNSET`→True(CLI 与未感知路径不受影响);
  API server 等无状态适配器在 bind 时传 False;`HERMES_KANBAN_TASK` 存在即 False
  (kanban worker 是一次性 `chat -q` 子进程,489-490)。工具(terminal notify_on_complete、
  delegate_task background=True)以此拒绝"渠道兑现不了的承诺"(#53027、#63142,461)。
- `session_is_messaging_surface()`(418-438):平台/来源二元身份判定是否人类聊天渠道;
  `NON_MESSAGING_SESSION_SURFACES`(400-415)默认拒绝式设计——**不认识的身份按 messaging 算**,
  新平台接入不会先被当成本地面。与 apps/desktop 的 LOCAL_SESSION_SOURCE_IDS 保持镜像(注释 397-399)。

### 设计理由与取舍
- ContextVar 而非锁:身份是任务局部读多写一,天然契合;锁保护 os.environ 会串行化整个网关。
- 三态(_UNSET / "" / 值)成本是心智负担,收益是**兼容三代调用方**:未迁移的 os.getenv 代码、
  已迁移的 gateway 代码、根本不用会话系统的 CLI。
- 不可嵌套的 clear 是承认现实:处理器边界只有一层,tokens-restore 语义留着只会造成假安全感。

### 重实现要点
1. 并发宿主里任何"当前会话"信息都必须 task-local;os.environ 只能做单进程兼容回落。
2. 用哨兵区分"从未设"与"清空",否则回落逻辑会在错误时机启动。
3. 消息处理器**入口先重置**继承来的上下文,再绑定自己——create_task 的上下文快照会泄漏。
4. 把"渠道能否异步回投"做成显式能力位,让工具能拒绝空头支票。
5. 进程级 engaged 闩锁解决"混合宿主"(gateway+CLI 同进程)下子进程该继承什么的判定。

## 机制 2:SessionState 三层状态容器(session_state.py)——19 个裸 dict 的结构化葬礼

### 场景/问题
GatewayRunner 曾有 ~19 个按 session_key 键控的独立 dict,三类事故:
边界漂移(清理清单手抄漏项,#48031/#58403/#10702/#35809)、回合释放漂移
(各处 `del self._running_agents[key]` 弹的子集不一)、整体重置竞态
(懒初始化 `self._x = {}` 覆盖并发会话条目)。

`gateway/session_state.py:3-19 @ 863e313`
```python
GatewayRunner historically carried ~19 separate ``Dict[str, ...]`` attributes
keyed by session_key, each with its own ad-hoc lifecycle.  Three failure
classes grew out of that shape:

1. Boundary drift — every conversation boundary carried a hand-copied
   pop-list that went stale when a new dict was added (#48031, #58403,
   #10702, #35809).  Mitigated by the ``_CONVERSATION_SCOPED_STATE`` registry,
   now structurally fixed: the fields live in one ``ConversationState``
   dataclass with a single ``clear()``.
```

### 实现
- 按**清理时机**分三层(21-28):`TurnState`(每回合末清)、`ConversationState`
  (会话边界清:/new、/resume、auto-reset、expiry、压缩耗尽重置)、`PersistentState`
  (各自生命周期)。`SessionState` 聚合三者(172-178);`GatewayRunner._sessions`
  是 `Dict[session_key, SessionState]`,条目**不逐出**(30-33,与旧 dict 同,留了后续工作)。
- `TurnState`(51-88):agent 实例/started_ts/跨进程并发槽 lease/busy_ack_ts;
  `lease_token`/`lease_generation` **不在 clear() 里清**——由 `_release_turn_lease` 独占管理,
  保证注册表租约"每获取回合恰好释放一次"(55-59)。
- `ConversationState`(90-128):/model 覆盖、--once 快照、/reasoning、/fast tier
  (`_UNSET_TIER` 哨兵:**键存在性**而非值真假决定覆盖是否生效,44-48)、last_resolved_model
  (#35314 恢复)、/queue 溢出 FIFO、sidecar notes、ephemeral pin、vc_last。
  单一 `clear()` = 结构性的边界清单:加字段自动进清理集。
- `PersistentState`(131-169):审批、update 提示、native 图片路径、pending_command_text
  (关机才落盘,#72680;注意与 base.py 适配器级 `_pending_messages` **同名不同物**,144-147)、
  `run_generation`(单调,**永不重置**,#28686)、`hygiene_failure_streak`(#79624:
  hygiene 每次跑新建 AIAgent,agent 内的压缩失败梯度计数结构性够不着,故在 agent 外按
  session_key 记连败以升级冷却;**进程局部故意为之**——键在 session_key 而非 sid,
  这是它比落库列多买到的"跨压缩轮换正确性",158-168)。
- **遗留视图层**(181-477):大量测试直接 `runner._running_agents = {}` 式读写旧属性。
  `SessionFieldView`(225-297)把每个旧 dict 做成一个跨会话的**活 MutableMapping 视图**
  (`_FieldSpec` 描述 scope/字段/存在性判定);`legacy_dict_property`(419-451)生成
  getter/setter/deleter property;`TurnLeaseTokenView`(299-366)保 `(session_key, generation)`
  二元组键的旧形状。生产代码走 `self._session_state(key).<scope>.<field>`。

### 设计理由与取舍
- 分层依据是"**谁在什么时机清它**"而不是语义相近——清理时机才是事故来源。
- run_generation 放 persistent 且永不重置:重置会让"旧回合迟到结果"重新变成当前代。
- 视图层是迁移成本的显式化:几十个测试是行为规格,宁可写 300 行适配器也不改规格。

### 重实现要点
1. 按清理时机给会话状态分层,每层一个 `clear()`;"加字段忘清理"从 review 项变成不可能。
2. 单调代数计数器决不重置;它的意义就是"永远向前"。
3. 需要跨压缩轮换存活的计数,键要选路由键(chat 不变)而不是会话 id(轮换会变)。
4. 大规模状态迁移时,用活视图保住既有测试面,让规格无损迁移。

## 机制 3:回合租约 SessionTurnLeaseRegistry(turn_lease.py)——按最终 session_id 串行化

### 场景/问题(#64934)
busy 守卫都按**路由键**(routing key)加锁(适配器 `_active_sessions`、runner
`_running_agents`),但持久转写按 **session_id** 归属,而 `switch_session()` 让键→id
多对一(第二个 chat `/resume` 同名会话、CLI-continuity 重绑、异步委托 pinning、
Telegram topic tip-walk)。两个路由键各自过守卫、各建 agent、并发跑同一转写:
flush 按完成序而非到达序落盘、身份标记去重可能整行吞掉、第二回合的历史基线看不到
第一回合——留下永久的 `user;user` 交替楔子,`repair_message_sequence` 每次请求都在修。

`gateway/turn_lease.py:3-15 @ 863e313`
```python
Why this exists (#64934): the gateway's busy guards are keyed by ROUTING KEY
(``_active_sessions`` in the adapter, ``_running_agents`` in the runner), but
the durable transcript is owned by SESSION_ID — and ``switch_session()`` makes
the key→id mapping many-to-one (``/resume`` of a named session from a second
chat/topic, CLI-continuity rebinding, async-delegation completion pinning,
Telegram topic-binding tip-walks). Two routing keys mapped to one session_id
run concurrent turns on two different agent objects, so no per-key guard ever
sees the collision. The two turns then interleave their flushes on one
transcript: rows persist in completion order instead of arrival order, the
identity-marker dedup over shared history dicts can swallow a row outright,
and the second turn runs on a history base that never saw the first turn's
exchange — leaving a permanent ``user;user`` alternation wedge
```

### 实现
- 每 resolved session_id 一个 `asyncio.Lock` + holder 记录(`_SessionLease`,100-112);
  获取点在会话解析**定案之后、载入历史之前**(run.py:16568-16593:get_or_create →
  异步委托 pinning → tip-walk switch 都在其上;wait 超时取 `HERMES_AGENT_TIMEOUT` 默认
  1800s,与回合不活跃看门狗同钟,turn_lease.py:63-66 注释点明)。
- **三条安全性质**(27-38):
  1. 代数域身份检查释放:token 记 (owner_key, generation),`release()` 只在"这个 token
     正是当前 holder"时才放锁(288-296);过期回退永远放不掉新回合的租约(#28686 教训)。
     幂等(`released` 位,282-284)。
  2. 超时 fail-open:等锁超时返回 `degraded=True` 的 token,回合**不串行化继续跑**并
     ERROR 一条(192-208)——宁可回到旧行为也不楔死会话;degraded token 不持有也不释放。
  3. 有界注册表:上限 512(61),只逐出 idle(无 holder、无 waiter)条目、最老优先
     (139-152);活租约永不逐出,突发可暂超上限——"correctness beats the cap"。
- `rebind(token, new_sid)`(215-272):压缩**回合中**轮换 session_id 时,把**同一个**
  `_SessionLease` 对象再登记到新 id 下(旧映射留着等 idle 逐出),两个 id 的获取者
  串行化在同一把锁上;只有当前 holder 能 rebind;若新 id 已有活租约(目标会话正有回合),
  **不合并串行化域**、留在旧 id 上、响亮记日志——fail-open 不死锁(250-267)。
- 已知边界(40-47,docstring 自认):CLI-continuity 的跨进程共享在任何进程内锁之外
  (需要 DB 级租约,另案);mid-turn 压缩轮换有小的别名窗口,rebind 是补(#64934 flagged)。
- 挂接:acquire 在 run.py:16584-16589;token 存 `TurnState.lease_token/lease_generation`
  (run.py:16590-16593);释放在 dispatch 层 finally(`_release_turn_lease` run.py:22859)。
  争用时 WARNING 点名 session 与两个路由键(174-188),与
  `agent/agent_runtime_helpers.note_turn_start` 的跨 agent 绊线成对(24-25)。
  行为规格:tests/gateway/test_turn_lease.py(本轮跑通)。

### 设计理由与取舍
- 不把守卫改键(routing key→session_id):守卫在解析前就要挡人,而 id 解析要查库;
  租约补在"解析已定案"这一点,两层各管各的。
- fail-open 而非 fail-closed:楔死会话比转写交错更糟——交错可修(repair),楔死要人来救。
- 进程内 asyncio 锁的可见域 = 它要扩展的守卫的可见域,明说不解决跨进程(43-44)。

### 重实现要点
1. 锁的键必须与被保护资源的**归属键**一致;路由键 ≠ 存储键时,在解析定案点补第二层锁。
2. 租约 token 带 (owner, generation) 双身份,释放走身份检查——异常回退路径永远存在。
3. 等锁要有超时且超时后**降级继续**并大声记日志,不要把用户会话变成死等。
4. 有界注册表逐出只碰 idle 条目;正确性优先于上限。
5. 资源身份会中途轮换(压缩换 id)时,提供"同锁多键"的 rebind,而不是搬锁状态。

## 机制 4:run generation(run.py:23014-23063)——迟到结果的代数闸门

### 场景/问题(#28686)
/stop、/new 打断旧回合后,旧 worker 还在异步收尾;它迟到的结果/清理若被当成"当前回合"
处理,会渗进新会话(污染历史、误释放新回合的资源)。

### 实现
`gateway/run.py:23014-23027 @ 863e313`
```python
    def _begin_session_run_generation(self, session_key: str) -> int:
        """Claim a fresh run generation token for ``session_key``.

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
- `_invalidate_session_run_generation`(23029-23039)= 再 +1(使在飞代作废),带 reason 日志;
  `_is_session_run_current(key, gen)`(23041-23047)= 相等判定;
  `_bind_adapter_run_generation`(23049-23063)把代数塞给适配器的 interrupt 事件对象
  (`_hermes_run_generation` 属性),适配器层的取消也能识别代。
- 消费侧例证:进程收割 `_reap_gateway_turn_processes` 的 `is_still_current` 闭包
  (run.py:2851-2857)——超时收割前检查"是否已有新回合认领本会话",避免误杀新回合的进程;
  租约 release/rebind 只匹配当前代(turn_lease 上文)。

### 重实现要点
1. 每个可被打断的异步工作单元领一个单调代数;所有迟到副作用先验代再执行。
2. "作废"就是"翻代",不需要额外状态位。
3. 代数要传给所有可能代表本回合行动的层(适配器事件、清理线程、租约)。
