# r7-60 · 看护面:stall 通知、回合不活跃看门狗、会话过期、内存监控(主线亲读)

> 基线 @ 863e313。覆盖:gateway/session_stall.py(121 行,全文)、
> run.py `_watch_gateway_turn_inactivity` 族(2841-2985)、`_session_stall_*` 族(12104-12353)、
> `_session_expiry_watcher`(11926-12102)、memory_monitor.py(230 行,全文)。
> 四条看护线各管一类"没人看着就会烂掉"的问题,边界刻意分开。

## 机制 1:session_stall 通知策略(session_stall.py + gateway/run.py:12104-12353)

### 场景/问题(#72016 item 2)
用户发消息进来排队(pending inbound),而占着会话的回合卡住不动。用户看到的是"已读不回"。
需要在"卡住"时**通知一次**,恢复后能再次武装,但不能拿回合开始时间或消息到达时间当进度钟
(那会把"长工具正常跑"误判为卡死)。

### 实现
- **策略与观测分离**:session_stall.py 只有 4 个纯函数,进度来源是共享活动契约
  `agent.session_activity` / `AIAgent.get_activity_summary()`(#72039)——"single progress
  source",模块自己不发明时钟:

`gateway/session_stall.py:3-14 @ 863e313`
```python
Consumes the shared activity observation contract from
``agent.session_activity`` / ``AIAgent.get_activity_summary()``
(#72039) as the **single progress source**. This module owns only the
notify-once policy for "pending inbound + stale progress"; it does not
invent a parallel progress clock from turn-start or inbound event
timestamps.

Boundaries (keep separate):
- ``gateway/shutdown_watchdog.py`` — process / event-loop liveness
- ``gateway/delivery_ledger.py`` — outbound delivery obligations
- Pending inbound here is a stall *policy gate* (queued follow-up exists),
  not an outbound obligation and not a progress timestamp.
```
- 触发条件(27-43):`timeout>0` ∧ 有 pending inbound ∧ 未通知过 ∧ `idle_seconds ≥ timeout`;
  `idle_seconds is None`(观测缺失)**不触发**。
- 解除条件(46-60):无 pending → 解除;timeout 关掉 → 解除;`idle < timeout` → 解除;
  **观测缺失(None)→ 保持闩锁**——"Do not treat observation gaps as recovery"(57)。
- `resolve_session_idle_seconds_from_activity`(72-121):优先 `seconds_since_activity`
  (有限值;负数归零),否则由 `last_activity_at`/`last_activity_ts` 推;都没有 → None。
- run.py 侧消费:超时阈 `HERMES_SESSION_STALL_TIMEOUT` 默认 300s、0 关(12104-12106);
  `_check_session_stalls`(12146-12329)每轮从**两处**收集候选:各适配器 `_pending_messages`
  槽 + runner `_queued_events` 溢出 FIFO 队头(12167-12185,含 profile 适配器,
  `_iter_gateway_adapters` 12108-12127 按 id 去重);进度快照只取运行中 agent
  (`_session_activity_for_stall` 12129-12144,sentinel 跳过);notify-once 闩锁在
  `_session_stall_notified` map,先判解除再判触发(12197-12211)。
  watcher `_session_stall_watcher` 每 30s 一轮(12330)。
- 行为规格:tests/gateway/test_session_stall_watchdog.py(本轮跑通,含"观测缺失不算恢复"用例)。

### 设计理由与取舍
- 通知(告诉用户)与处置(杀/重试)分权:本模块**只通知**,杀回合是回合看门狗的事(机制 2)。
- pending inbound 作为策略闸门:没有排队消息就没有"已读不回"体验问题,不打扰。
- None 保持闩锁是保守选择:观测断了 ≠ 恢复了;代价是极端情况下少发一次"已恢复后再卡"的提醒。

### 重实现要点
1. 卡死判定的进度钟必须来自"工作本体的活动观测",不能用回合开始/消息到达时间。
2. 通知一次 + 恢复解除闩锁;观测缺失不算恢复。
3. 策略写成纯函数、观测与执行留在宿主——测试与复用都容易。
4. "通知""超时杀""投递义务""进程活性"四件事分四个组件,别揉在一起。

## 机制 2:回合级不活跃看门狗(gateway/run.py:2841-2985)

### 场景/问题
回合可能因 provider 挂死、工具死循环等停止进展;gateway 的 asyncio 循环本身也可能被饿死。
需要一个**独立于事件循环**的守护,在回合长时间无活动时打断它,并只收割**该回合**遗留的后台进程。

### 实现
- 看门狗是**线程**,明说原因:"Thread watchdog that remains runnable when gateway asyncio
  is starved"(gateway/run.py:2963)。每 5s 轮询 `agent.get_activity_summary()['seconds_since_activity']`
  (2964-2971,同一进度契约),`idle ≥ timeout` 触发 `_abandon_timed_out_gateway_turn`(2976)。
- `_abandon_timed_out_gateway_turn`(2912-2948):cleanup_lock 下检查 worker_done/timeout_fired
  双事件,先到先得(2923-2926);对 agent `request_hard_interrupt(..., TIMEOUT)`;再收割进程。
- 收割的精确性(`_reap_gateway_turn_processes` 2841-2909)是亮点:

`gateway/run.py:2848-2857 @ 863e313`
```python
    """Reap only background processes created by one abandoned turn.

    ``task_id`` is session-scoped (task_id == session_id), not turn-scoped,
    so a *replacement* turn on the same session can start and spawn its own
    legitimate process while this reap is still in flight. ``is_still_current``
    — a closure over the run_generation captured when the reaping turn began
    or was interrupted — lets the caller detect that a newer turn has since
    claimed the session and bail out instead of killing that newer turn's
    process. The newer turn snapshots its own baseline independently, so
    skipping here does not leave anything permanently unreaped.
    """
```
  - 空 task_id 直接不收(2859-2863):ProcessSession.task_id 对无会话调用方默认 "",
    空串会匹配并杀掉**所有**无关空任务进程。
  - 基线差分:`kill_started_since(task_id, process_baseline)`——只杀"本回合开始后新出现"的。
  - run generation 闸门:`is_still_current` 闭包发现新回合已认领会话就放弃收割(新回合有
    自己的基线,不会漏收)。
  - 收割跑在 detached daemon 线程上,异常吞掉走正常日志通道(2890-2901)。

### 设计理由与取舍
- 线程而非 asyncio 任务:看门狗的假设敌之一就是事件循环卡死,守护不能与被守护者同生死。
- "只收自己孩子"三重保险(空 id 拒绝 / 基线差分 / 代数闸门)换来的是可以放心自动杀,
  不然误杀新回合进程比不杀更糟。

### 重实现要点
1. 看护"事件循环可能卡死"的场景,守护必须在独立线程/进程。
2. 自动清理的匹配谓词要做成"归属 + 时间基线 + 代数"三元组,宁可漏收不可误杀。
3. 超时打断与正常完成之间用双事件 + 锁裁决,恰好一方胜出。

## 机制 3:会话过期与缓存治理(gateway/run.py:11926-12102)

### 场景/问题
网关长驻,会话按重置策略过期(idle/daily)后,缓存的 AIAgent(LLM 客户端、工具 schema、
memory provider 引用)若不清,内存随会话数单调增长;过期还要触发 finalize 钩子
(记忆固化等),且只能触发一次。

### 实现
- watcher 每 300s 一轮,启动延迟 60s(11926-11935);逐条:`finalize_session`(lifecycle 钩子,
  reason="session_expired",11969-11976)→ 清缓存 agent 的工具/记忆资源(off-loop,
  11979-11996;先查 `_agent_cache`,mid-turn 则回落 `_running_agents`)→ `_evict_cached_agent`
  (11997-12001)→ `_clear_conversation_scope(reason="expiry_finalized")`——注释明确区分:
  **真 finalize 才能清会话域覆盖**,idle 逐出不能清(会话还活着,恢复回合要靠这些覆盖重建
  agent)(12002-12014)→ `set_expiry_finalized` 持久化(sessions.json + state.db 单写路径
  #9006,顺带丢 /model 覆盖,12015-12019)。
- 失败重试有界:连续 3 次失败后**标记已 finalize 防止无限重试**,但 `clear_model_override=False`
  少清一点(12025-12037)——可用性优先,泄一个覆盖好过每 5 分钟报错一次。
- 同一轮顺带:`_sweep_idle_cached_agents`(TTL 逐出,专治 reset policy = never 的会话,
  12059-12071)+ SessionStore 每小时 prune старых条目(`session_store_max_age_days`,
  12073-12095;"resumed session just gets a fresh session_id" 对用户不可见)。

### 重实现要点
1. 过期 finalize 要幂等(persisted 标志)且失败有界重试,兜底是"标记完成少清一点"。
2. 区分"会话结束"与"缓存逐出"两种清理深度:前者清覆盖,后者必须保留。
3. 长驻进程的每个 per-key 容器都要有对应的收敛机制(过期/TTL/prune 三线)。

## 机制 4:内存监控(memory_monitor.py,全文)

### 场景/问题
网关缓存 agent 实例、转写、工具 schema、MCP 连接……任何子系统慢泄漏在单行日志里不可见,
只能看 RSS 随小时爬升。要一条 grep 友好的时间序列。

### 实现
- 自 cline/cline#10343 移植(1-3)。每 N 分钟(默认 300s)一条
  `[MEMORY] rss=…MB gc=(g0,g1,g2) threads=… uptime=…s`(83-126);启动即打 baseline、
  关机打 shutdown 快照(178-179、207-211)——"last RSS before exit is always in the log"。
- RSS 读取:`resource.getrusage` 优先(Linux ru_maxrss 单位 KB、macOS 是**字节**,
  代码注释"yes, really",58-69;注意 ru_maxrss 是高水位,注释直言这正是泄漏排查想要的),
  回落 psutil(Windows);都不可用 → WARNING 一次并**禁用**而不是空转(164-172)。
- daemon 线程,`stop` 时先打快照再 set 事件,join 放锁外防死锁(213-222);
  幂等 start(161-162)。
- 配置:`logging.memory_monitor`(config.yaml,27-28)。
- 行为规格:tests/gateway/test_memory_monitor.py(本轮跑通)。

### 重实现要点
1. 长驻进程标配:周期性单行结构化资源快照(RSS+GC+线程数+uptime),grep 即时间序列。
2. baseline 与 shutdown 快照让"从多少涨到多少"永远可答。
3. 观测线程 daemon 化 + 不可用即禁用,监控永远不能反噬宿主。
