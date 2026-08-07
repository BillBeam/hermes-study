# r7 底稿 · run.py 第 6 段:drain / restart / startup-restore(GatewayRunner 第 3 段,9184-10663)

> 对象:/home/user/hermes-agent/gateway/run.py 第 9184-10664 行 @ 863e313。
> 本段是 GatewayRunner 的「停机排水 → 重启 → 下次启动恢复」全链路:排水等待、强中断、
> 停机通知、mid-turn 转录抢救、off-loop 资源清理、stuck-loop 熔断、三种重启落地方式
> (detached watcher / systemd transient unit / 服务退出码 75)、启动期送达补投 + 自动续跑
> + 入站排队门、以及事件循环活性护栏。
> 溯源约定:`gateway/run.py:行号 @ 863e313`;引用其他文件同格式。

---

## 0. 全链路时序(先看骨架)

停机侧(`_stop_impl`,不在本段但为本段所有方法的宿主):

1. `stop()` 先拆活性护栏(run.py:12669-12671)→ `_stop_impl` 置 `_running=False, _draining=True`(12801-12802);
2. `_notify_active_sessions_of_shutdown()`(12812)——适配器还在线,先把「要重启了」发出去;
3. 预标记 resume_pending(12824-12835,#27856:drain 期间被 SIGKILL 也有耐久标记);
4. `_drain_active_agents(timeout)`(12840)等 agent+cron+api 三类工作归零;
5. 超时 → 再标 resume_pending → `_interrupt_running_agents()`(12915)→ 5s 宽限 → `_kill_tool_subprocesses("post-interrupt")`(12931,#8202);
6. detached 重启则 `_launch_detached_restart_command()`(12939);
7. `_finalize_shutdown_agents(active_agents)`(12943)——mid-turn 转录落库 + off-loop 清理;
8. `_increment_restart_failure_counts()`(13100,stuck-loop 计数);
9. via_service 重启 → `_launch_systemd_restart_shortcut()`(13117)+ 退出码 75。

启动侧(`start()`,同样是宿主):

1. 无 `.clean_shutdown` 标记 → `suspend_recently_active()` 标 `restart_interrupted`(11017;gateway/session.py:2850);
2. `_suspend_stuck_loop_sessions()`(11028,#7536);
3. 开入站排队门 `_startup_restore_in_progress=True`(11039);
4. 适配器全部连上后:`_redeliver_pending_obligations()` → `_schedule_resume_pending_sessions()` → `_finish_startup_restore()`(11447-11449,顺序有意:先补投已生成的答案,再重跑没答案的 turn,最后放行排队的入站)。

---

## 1. `_drain_active_agents` —— 三类在飞工作合并排水(9184-9241)

**问题**:停机排水最初只看 `self._running_agents`(聊天会话)。cron 作业跑在调度器自己的
线程池上、API-server 的 desk 会话有独立登记,两者都不在这个字典里 —— drain 报
`active_at_start=0` 直接进入杀子进程阶段,cron 作业的 terminal 命令被零预警击杀
(#60432);api_server 同构缺口是 #63529。

**实现**:把三个计数折进同一个等待/超时:

```python
# gateway/run.py:9210-9222 @ 863e313
        # Cron jobs run on the scheduler's own thread pool, outside
        # ``self._running_agents`` — fold their in-flight count into the
        # same wait/timeout this method already applies to chat sessions,
        # or a cron job's tool work gets killed with zero warning the
        # instant it's the only active thing running (#60432).
        # API-server / desk sessions have the same structural gap (#63529).
        if not self._running_agents and last_cron_count == 0 and last_api_count == 0:
            _maybe_update_status(force=True)
            return snapshot, False

        _maybe_update_status(force=True)
        if timeout <= 0:
            return snapshot, True
```

轮询循环 0.1s 一拍,三者任一非零且未到 deadline 就继续等(9225-9234);返回
`(snapshot, timed_out)`,snapshot 是 drain **开始时**的 agent 快照(9185),后续
`_finalize_shutdown_agents` 用它兜底(见 §4)。`timed_out` 判定同样三合一(9235-9239)。

计数来源(调用关系):
- `_running_agent_count` = `len(self._running_agents)`(run.py:7378-7379);
- `_active_cron_job_count` → `cron.scheduler.get_running_job_ids()`(run.py:7389-7407,导入失败返回 0——测试替身友好);
- `_active_api_run_count` → `adapters[Platform.API_SERVER].active_agent_work_count()`(run.py:7409-7421);
- 三者之和即 `_active_work_count()`(run.py:7381-7387),被 §10 的 after-turn 等待复用。

内部闭包 `_maybe_update_status`(9191-9208)只在计数变化或距上次 ≥1s 时重写
`_update_runtime_status("draining")`(run.py:7793)——runtime-status 文件是给外部监督
进程看的心跳,drain 期间必须持续跳动,但不能每 0.1s 写盘。

**设计理由与取舍**:
- 三类工作分属三个所有权域(runner 字典 / cron 线程池 / api adapter),不强行统一登记,
  而是在「读侧」聚合 —— 侵入最小,但代价是计数是快照式的,存在竞态窗(新工作可在两拍之间启动;
  停机路径已置 `_draining=True` 拒新,窗口可接受)。
- `timeout<=0` 直接返回 `timed_out=True`:默认配置 `restart_drain_timeout: 0`
  (hermes_cli/config_defaults.py:47)—— 即**默认不等待、立刻进入强中断**,把「等 turn 做完」
  的职责移交给 §10 的 after-turn 等待(#77184 的新分工)。

**重实现要点**:
1. 排水必须枚举**所有**执行域,任何绕过主登记表的执行路径(定时任务、HTTP 服务)都要有可查询的在飞计数;
2. 计数读取要 best-effort(导入失败/属性缺失返回 0),排水逻辑不能因可选子系统缺席而崩;
3. 返回「开始时快照 + 是否超时」两件事,快照供后续 finalize 兜底;
4. 排水期间持续刷新对外心跳,但按「变化或 ≥1s」节流;
5. timeout=0 语义要明确(立即超时而非无限等),并与上层「先等 turn 再 stop」的机制分工。

对应测试(行为规格):tests/gateway/test_cron_active_work_drain.py、
test_api_server_active_work_drain.py、test_cron_shutdown_drain.py、test_restart_drain.py。

---

## 2. `_interrupt_running_agents` —— 兼容两代中断 ABI(9243-9251)

```python
# gateway/run.py:9243-9251 @ 863e313
    def _interrupt_running_agents(self, reason: str) -> None:
        for session_key, agent in list(self._running_agents.items()):
            if agent is _AGENT_PENDING_SENTINEL:
                continue
            try:
                request_hard_interrupt(agent, reason)
                logger.debug("Interrupted running agent for session %s during shutdown", session_key)
            except Exception as e:
                logger.debug("Failed interrupting agent during shutdown: %s", e)
```

- `_AGENT_PENDING_SENTINEL`(run.py:2465,`object()` 哨兵)代表「槽位已占、真 agent 未建」——
  没东西可中断,跳过;
- `request_hard_interrupt`(agent/interrupt_compat.py:9-35)优先走新 ABI `hard_interrupt(message)`,
  用 `inspect.getattr_static` 防 MagicMock/`__getattr__` 代理伪装实现,退回旧 `interrupt(message)`;
- 调用点:`_stop_impl` drain 超时后(run.py:12915-12917),reason 取
  `_INTERRUPT_REASON_GATEWAY_RESTART/_SHUTDOWN`,随后 5s 宽限轮询(12918-12921)。

**重实现要点**:1) 中断循环对快照 `list(...)` 迭代,防回调改字典;2) 哨兵占位者必须跳过;
3) 单个失败只 debug 日志,不中断其余会话的中断;4) ABI 兼容层用静态属性探测,别信动态代理。

---

## 3. `_notify_active_sessions_of_shutdown` —— 停机通知:先私聊后广播,三层抑制(9253-9451)

**问题**:重启会掐断进行中的任务。若不提前告知,用户只看到 bot 沉默;而通知本身又有三个反面问题:
重复轰炸(同一 chat 多 session)、云端例行自动更新每次都广播扰民、发送路径自身可能让停机卡死。

**实现**(在 stop() 最开头调用,适配器仍在线,run.py:12812):

(a) 对每个活跃会话解析投递目标:优先 session store 里持久化的 `origin`,退回运行时缓存
`_get_cached_session_source`(run.py:16262),最后解析 session_key(`_parse_session_key`,
run.py:3352)。按 `(platform, chat_id, thread_id)` 三元组去重(9307-9309)——注释明确:
线程化平台同父 chat 仍是不同投递目标,不能只按 chat 去重。

(b) 文案区分重启/停机,重启附「重启后发任意消息即可续跑」提示:

```python
# gateway/run.py:9263-9270 @ 863e313
        action = "restarting" if self._restart_requested else "shutting down"
        hint = (
            "Your current task will be interrupted. "
            "Send any message after restart and I'll try to resume where you left off."
            if self._restart_requested
            else "Your current task will be interrupted."
        )
        msg = f"⚠️ Gateway {action} — {hint}"
```

(c) 逐平台配置开关 `gateway_restart_notification=false` 可整体禁掉(9317-9323 会话侧、
9406-9412 home 侧);in-chat `/restart` 发起者所在 chat 的通知会 reply 到触发消息
(9325-9334,`_restart_command_source` 于 run.py:5971 初始化)。

(d) in-chat 重启时跳过 home-channel 广播(9366-9368)——发起人自己知道,不用再广播。

(e) drain 标记抑制(仅 home 广播,NS-570 纪元校验):

```python
# gateway/run.py:9383-9394 @ 863e313
        try:
            from gateway.drain_control import drain_notification_suppressed
            if drain_notification_suppressed():
                logger.info(
                    "Home-channel shutdown broadcast suppressed by drain marker "
                    "(suppress_notification=true)"
                )
                return
        except Exception as e:
            # Never let the suppression check block the shutdown broadcast —
            # fail toward the louder, more-visible behaviour.
            logger.debug("drain_notification_suppressed check failed: %s", e)
```

9370-9382 的长注释交代设计:Hermes Cloud 全托管机队的例行镜像迁移是「先 drain 后重建机器」,
若不抑制,每次自动更新都对 home channel 广播一次「gateway shutting down」;
但**逐会话中断 ping 故意不受抑制**——排干净的停机里它天然为空集,强中断场景里它承载
「你的任务被掐、发消息可续」的真信息。`drain_notification_suppressed`
(gateway/drain_control.py:229-251)只认**当前实例纪元**的标记:标记体带 `epoch`
(进程实例化纪元,drain_control.py:68),纪元不匹配视为陈旧标记直接忽略
(drain_control.py:189-207 的 `_marker_epoch_is_stale`,宽松判定:算不出当前纪元或标记无纪元
都按「有效」处理)——防止耐久卷上残留的孤儿标记压掉新 gateway 的合法广播。

(f) home 广播迭代 `list(self.adapters.items())`(9401):

```python
# gateway/run.py:9396-9401 @ 863e313
        # Snapshot adapters up front: adapter.send() can hit a fatal error
        # path that pops the adapter from self.adapters (see _handle_fatal
        # elsewhere), which would otherwise trigger
        # ``RuntimeError: dictionary changed size during iteration`` —
        # observed in a user report during gateway shutdown.
        for platform, adapter in list(self.adapters.items()):
```

(g) 发送结果校验:`result.success is False` 视为失败,不进 `notified` 集合(9346-9353、
9429-9436)——失败目标后续如与 home 重合还能再试一次。整个方法所有异常都吞掉只 debug,
绝不阻塞停机序列(docstring 9254-9259)。

**重实现要点**:
1. 通知在 stop() 最前沿、适配器断连之前发,时序是硬约束;
2. 去重键 = 完整投递目标三元组(平台+chat+thread),不是 chat;
3. 三层抑制各有独立理由:平台配置(用户偏好)、in-chat 重启(发起者已知)、drain 标记(机队例行更新),且抑制只作用于广播、不作用于「你的任务被掐」的私聊;
4. 抑制检查失败时 fail-loud(照发)而非 fail-silent;
5. 任何过期标记都要有纪元/新鲜度校验,耐久存储上的标记文件天然会跨实例存活;
6. 迭代可能被回调收缩的容器一律先快照。

对应测试:tests/gateway/test_restart_notification.py、test_external_drain_control.py。

---

## 4. `_finalize_shutdown_agents` —— mid-turn 转录抢救 + 三级降级(9452-9522)

**问题**(#13121):被 drain-timeout 强中断的 agent 可能永远到不了
`turn_finalizer.finalize_turn`(唯一把 turn 落到 state.db 的地方)——比如卡在一个
中断宽限期内没退出的工具调用里。它的在飞 tool 轮次只活在内存 `_session_messages` 里,
重启后 `load_transcript()` 里这个 turn 无声消失。

**实现**:对 drain 快照里的每个 agent:

```python
# gateway/run.py:9469-9486 @ 863e313
            try:
                _flush = getattr(agent, "_flush_messages_to_session_db", None)
                _session_messages = getattr(agent, "_session_messages", None)
                if callable(_flush) and isinstance(_session_messages, list) and _session_messages:
                    # Strip private empty-response retry scaffolding from the
                    # tail first, mirroring the graceful ``_persist_session``
                    # path, so a resumed turn doesn't replay synthetic recovery
                    # nudges.
                    _strip = getattr(
                        agent, "_drop_trailing_empty_response_scaffolding", None
                    )
                    if callable(_strip):
                        try:
                            _strip(_session_messages)
                        except Exception:
                            pass
                    try:
                        _flush(_session_messages)
```

三级降级:
1. 正常:`_flush_messages_to_session_db(_session_messages)` 落 SQLite。flush 前先剥掉尾部的
   空响应重试脚手架(镜像优雅路径 `_persist_session`),避免续跑时重放合成的 recovery nudge。
   flush 幂等(身份跟踪),优雅完成的 agent 重刷等于无操作(注释 9466-9468)——所以直接对
   drain **开始时**的快照全量执行是安全的。
2. flush 抛异常(如 FTS/SQLite 索引损坏,#72680):落到 DB 外的 JSON 抢救快照
   `flush_agent_history_to_file`(gateway/shutdown_flush.py:272-321,原子写 + 序列化容错,
   供操作员修好 state.db 后手工找回),9496-9506;
3. 快照也失败:外层 try 吞掉只 debug(9507-9508)——停机绝不因 best-effort 备份而阻塞。

随后:`hermes_cli.lifecycle.finalize_session(reason="shutdown")` 记生命周期账(9509-9517,
全吞异常);最后 `_cleanup_agent_resources_off_loop(agent, context="shutdown finalize")`
(9520-9522)——off-loop + 有界,因为 #53175:一个卡死的 memory provider 曾把整个停机挂住,
SIGTERM 永远完成不了(见 §6)。

**重实现要点**:
1. 「唯一落库点在 turn 末尾」的架构必须配一个停机侧的强制 flush,否则强中断=静默丢 turn;
2. flush 设计成幂等(身份跟踪),就能无脑对快照全量执行,不用区分谁优雅完成;
3. 持久化失败的降级目标是「换个介质保数据」(DB 坏了写 JSON),而不是「记条日志」;
4. flush 前要镜像优雅路径的尾部清洗,否则续跑会看到合成脚手架;
5. 每一级都 best-effort,停机路径上不允许任何抢救动作抛出。

对应测试:tests/gateway/test_13121_shutdown_inflight_transcript_flush.py、
test_shutdown_flush.py、test_session_messages_shutdown_preserve.py。

---

## 5. `_should_emit_long_running_notification` —— 心跳所有权三重校验(9524-9545)

**问题**(#12029):长任务心跳(「still working…」气泡)是独立 task,若用户中途 `/new`,
session 槽位被新 agent 接管,旧心跳还在替已死的 run 报「running: delegate_task」。

```python
# gateway/run.py:9537-9545 @ 863e313
        if agent is None:
            return False
        if executor_task is not None and executor_task.done():
            return False
        if session_key:
            _hb_state = self._peek_session_state(session_key)
            if (_hb_state.turn.agent if _hb_state else None) is not agent:
                return False
        return True
```

三重校验:agent 还在、executor future 未完成、session 槽位里的 agent **身份**(`is`)仍是自己。
调用点:心跳循环每拍醒来先查(run.py:25003-25006),失败即 break。

**重实现要点**:1) 派生的周期性任务每拍都要验「我服务的 run 还活着且还拥有槽位」;
2) 所有权比对用身份(is)不用键相等——键会被新 run 复用;3) 判定做成纯函数(读三个输入),
方便单测。

---

## 6. off-loop 有界清理三件套(9547-9693)

**问题**(#53175):`_cleanup_agent_resources` 是同步的,`agent.close()` 做子进程回收、
`shutdown_memory_provider()` 可能走网络/SQLite。在事件循环协程里内联调用会把整个 loop 卡死:
bot 沉默、runtime-status 心跳冻结、SIGTERM 无法被服务。/new 重置路径先修过一次(#35994),
这里把同一方案推广成通用工具。

### 6a. `_cleanup_agent_resources_off_loop`(9596-9634)

```python
# gateway/run.py:9607-9628 @ 863e313
        if agent is None:
            return
        if context.startswith("shutdown") or context == "session expiry":
            try:
                agent._end_session_on_close = False
            except Exception:
                pass
        try:
            await asyncio.wait_for(
                self._run_in_executor_with_context(
                    self._cleanup_agent_resources, agent
                ),
                timeout=self._CLEANUP_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Agent resource cleanup%s exceeded %ss; proceeding without "
                "blocking the event loop (the worker thread is left to finish "
                "on its own). (#53175)",
```

- 工作线程执行(`_run_in_executor_with_context`,run.py:21375)+ `_CLEANUP_TIMEOUT_S=30.0`
  上界(9556);超时只取消 await,**工作线程放任自流**(完成或泄漏)——调用方照常前进。
  取舍:接受偶发线程泄漏,换取 loop 永不被清理挂死。
- shutdown/过期场景先置 `_end_session_on_close=False`:会话还要被续跑,close 不许终结会话。

### 6b. `_defer_agent_cleanup_until_future_done`(9558-9594)

**问题**:超时的 executor 调用(如 §压缩 hygiene 的 timed-out worker)线程还在跑;
立刻 close agent 会拆掉它正在用的 client/provider。

```python
# gateway/run.py:9573-9588 @ 863e313
        async def _cleanup_when_done() -> None:
            try:
                await asyncio.shield(future)
            except asyncio.CancelledError:
                # Loop shutdown can cancel this waiter while the executor still
                # runs. Never turn that cancellation into premature cleanup.
                return
            except Exception as exc:
                logger.debug(
                    "Deferred agent worker%s finished with an error: %s",
                    f" ({context})" if context else "",
                    exc,
                )
            await self._cleanup_agent_resources_off_loop(agent, context=context)

        task = asyncio.create_task(_cleanup_when_done())
```

- `asyncio.shield(future)`:等待者被取消不传染给真 future;等待者被取消时**直接 return 不清理**
  ——宁可泄漏也不在 worker 还活着时拆资源;
- task 存进 `self._deferred_agent_cleanup_tasks` 集合持强引用 + done_callback 自摘
  (9588-9594)——裸 create_task 只有弱引用,pending task 可能被 GC。
- 调用点:hygiene 压缩超时(run.py:17033-17037)与非超时 unwind(17105-17109)。

### 6c. `_cleanup_agent_resources`(9636-9693)—— 真正的清理序

顺序即语义:**先排水后拆除**。
1. `_memory_manager.flush_pending(timeout=10)`(9654-9659)——#73297:
   `shutdown_memory_provider()→shutdown_all()` 只给串行后台 worker ~5s 排水、超时取消余队,
   /reset 或会话轮转可能静默丢掉已交接的记忆写入,下个会话读到旧记忆。先过 manager 自己的
   屏障给在队工作 10s 先行量(镜像 CLI 退出路径);
2. `shutdown_memory_provider(session_messages)`(9670-9674)——#15165:把真实转录传给
   provider 的 `on_session_end` 钩子(此前收到的是空默认);`getattr` 容忍
   `object.__new__` 测试替身缺属性,保持与旧签名兼容;
3. `agent.close()`(9680-9684)——终端沙箱、浏览器守护、后台进程、httpx client,防僵尸堆积;
4. `cleanup_stale_async_clients()`(agent/auxiliary_client.py;9689-9693)——辅助异步 client
   缓存在进程级、创建于工作线程,清掉事件循环已死的条目,防 httpx transport 跨 turn 累积。

**重实现要点**:
1. 任何可能做 IO 的同步清理都必须 off-loop + 有界,超时后放弃等待而不是放弃前进;
2. 「等真 future 完成再清理」与「shield 防取消传染」是成对出现的——被取消的等待者绝不能触发提前清理;
3. 后台 task 必须持强引用集合 + done_callback 自摘,这是 asyncio 的固有坑;
4. 清理序:先排水挂起写入(带独立超时),再带着转录关 provider,再关工具资源,最后清进程级缓存;
5. 每步独立 try/except,单步失败不阻断后续步骤。

对应测试:tests/gateway/test_73297_memory_flush_on_reset.py、
test_shutdown_memory_provider_messages.py、test_shutdown_cache_cleanup.py。

---

## 7. stuck-loop 熔断:重启失败计数 + 自动挂起(9695-9793)

**问题**(#7536):某会话的历史让 agent 每次都卡死 → gateway 重启 → 启动恢复又续跑同一历史
→ 再卡死。无人干预就是永动机。

**实现**:三个方法围着一个 JSON 文件 `<HERMES_HOME>/.restart_failure_counts` 转,
阈值 `_STUCK_LOOP_THRESHOLD = 3`(9695-9696)。

- **停机侧计数**:`_increment_restart_failure_counts(active_session_keys)`(9698-9723),
  `_stop_impl` 在有活跃 agent 时调用(run.py:13099-13100)。活跃会话计数 +1,写回原子
  (`atomic_json_write`);
- **启动侧熔断**:`_suspend_stuck_loop_sessions()`(9725-9772),start() 在
  `suspend_recently_active()` **之后**调用(run.py:11028):

```python
# gateway/run.py:9743-9756 @ 863e313
        suspended = 0
        stuck_keys = [k for k, v in counts.items() if v >= self._STUCK_LOOP_THRESHOLD]

        for session_key in stuck_keys:
            try:
                entry = self.session_store._entries.get(session_key)
                if entry and not entry.suspended:
                    entry.suspended = True
                    suspended += 1
                    logger.warning(
                        "Auto-suspended stuck session %s (active across %d "
                        "consecutive restarts — likely a stuck loop)",
                        session_key, counts[session_key],
                    )
```

  `suspended=True` 压过 resume_pending(见 §14 候选过滤 10481),会话下次消息拿到干净新会话;
  随后整个文件删除,计数清零重来(9766-9770)。
- **成功侧清零**:`_clear_restart_failure_count(session_key)`(9774-9793),
  成功 turn 后与 `clear_resume_pending` 一起调用(run.py:17655-17663)——计数只累积
  **连续**「重启时仍在跑」的轮次。

**文档-代码冲突候选(代码内注释自相矛盾)**:`_increment_restart_failure_counts` 里:

```python
# gateway/run.py:9713-9718 @ 863e313
        # Increment active sessions, remove inactive ones (loop broken)
        new_counts = {}
        for key in active_session_keys:
            new_counts[key] = counts.get(key, 0) + 1
        # Keep any entries that are still above 0 even if not active now
        # (they might become active again next restart)
```

第二条注释声称「保留当前不活跃但 >0 的旧条目」,但代码只从 `active_session_keys` 构建
`new_counts`,**不活跃条目实际被丢弃**——与 docstring 9702-9704(「NOT in active_session_keys
are removed」)一致,与这条行内注释矛盾。行为上丢弃是对的(docstring 语义),注释是残留。

**取舍**:计数文件按整机一份、键为 session_key,粗粒度但零依赖;误伤面:一个恰好每次重启时
都在跑长任务的**健康**会话,3 次后也会被挂起——用「成功 turn 即清零」缓解。
与 §14 的 restart_loop_guard(#30719)分工:本机制针对「**某个会话**的历史致卡」,按会话挂起;
restart_loop_guard 针对「**恢复行为本身**驱动 SIGTERM 风暴」,按 boot 全局跳过 auto-resume。

**重实现要点**:1) 熔断计数必须落盘(每次 boot 是新进程);2) 三个触点缺一不可:失败累加
(停机)、阈值执行(启动)、成功清零(turn 完成);3) 挂起要压过恢复标记,否则熔断无效;
4) 触发后清空计数给用户干净重来的机会;5) 全部 best-effort,计数机制故障不能影响主流程。

对应测试:tests/gateway/test_stuck_loop.py。

---

## 8. `_launch_detached_restart_command` —— 无监督进程下的自重启 watcher(9795-9980)

**问题**:没有 systemd/launchd/容器兜底时(裸 `hermes gateway` 前台跑),`/restart` 要求
进程自己死后有人拉起自己。方案:先派生一个**脱离会话**的 watcher,轮询本进程 PID,
死亡(或超时 `restart_drain_timeout+5s`,9808)后执行 `hermes gateway restart`。

**共性关键:环境标记洗刷**(POSIX 侧 9956-9963,Windows 侧 9871-9876):

```python
# gateway/run.py:9956-9963 @ 863e313
        # Same marker scrub as the Windows watcher above: this watcher runs
        # `hermes gateway restart` from outside the gateway, but it inherits
        # _HERMES_GATEWAY=1 from us, and the CLI's self-restart loop guard
        # refuses to run when that marker is set — silently (DEVNULL), so the
        # gateway stops and never comes back.
        from tools.environments.local import build_subprocess_env
        watcher_env = build_subprocess_env(scrub_secrets=False, inherit_profile_home=True)
        watcher_env.pop("_HERMES_GATEWAY", None)
```

`_HERMES_GATEWAY=1` 是防 agent 自杀重启的循环护栏(#30719 defense-1);watcher 逻辑上在
gateway 之外,但环境继承会让护栏误伤——不洗掉则 watcher 静默(DEVNULL)拒跑,gateway 停了
永远起不来。

**POSIX 路径**(9950-9980):shell 单行 `while kill -0 <pid> …; do sleep 0.2; done; hermes gateway restart`,
优先 `setsid bash -lc`,无 setsid 退回 `start_new_session=True`。

**Windows 路径**(9815-9948),坑最密:
- `os.kill(pid, 0)` 在 Windows **不是** no-op 探活——映射到 `GenerateConsoleCtrlEvent(0,pid)`
  (bpo-14484),会向目标控制台组发 CTRL_C。改用 Win32 `OpenProcess+WaitForSingleObject(h,0)==WAIT_TIMEOUT`
  判活(9832-9857 内嵌 watcher 源码);
- watcher 用 `sys.executable`(console python)而非 pythonw.exe:GUI 子系统的 watcher 没有
  控制台,每个 console 子孙都会弹出可见 conhost 闪窗(#54220/#56747,9878-9884);
- 双重 spawn 退避:先带 `CREATE_BREAKAWAY_FROM_JOB`(逃出 Electron/Windows Terminal 的
  job object,否则 CLI 退出时 watcher 被连坐回收),job 不允许 breakaway 时 `ERROR_ACCESS_DENIED`
  → 重试去掉 breakaway 位(9901-9927);两次都失败只 warning,且日志**只含解释器 basename +
  错误码**,绝不打 argv/env/watcher 源码(可能带密钥或全路径,9928-9947);
- venv 注入:手工拼 `VIRTUAL_ENV`/`PYTHONPATH` 指向 project venv(9885-9892)。

幂等门:`_detached_restart_helper_started`(9803-9805)——本方法有**两个**调用点
(request_restart 内 10167-10171、_stop_impl 内 12937-12941,前者只在 detached 分支走,
后者兜底),标志保证 watcher 只派生一次。

**重实现要点**:1) 自重启 watcher 必须逃出父进程的进程组/会话/job object,三个平台机制各不同;
2) 护栏环境标记对「逻辑上在外部」的子进程要显式洗刷;3) Windows 探活不能用 `os.kill(pid,0)`;
4) watcher 有硬 deadline(drain+5s),父进程卡死也照样重启;5) 失败日志脱敏(basename+errno);
6) 幂等标志防多触发点重复派生。

---

## 9. `_launch_systemd_restart_shortcut` —— 绕开 RestartSteps 退避的临时单元(9982-10075)

**问题**:计划内重启走干净退出,但带 `RestartSteps` 的 unit 连自动重启也计数退避,连续
`/restart` 测试会被越拖越慢。方案:`systemd-run --collect` 派生一个 transient unit,
它在本 gateway 的 cgroup 之外存活,等 PID 消失后立刻 `reset-failed + restart`;
真崩溃循环仍由 unit 自身退避管辖。

关键是 **system/user 域探测**(10021-10044):对两个域各查 `systemctl show <svc> --property=MainPID`,
与自身 PID 相等者胜;都不等则直接放弃(「宁可不重启也不重启错 unit」):

```python
# gateway/run.py:10032-10044 @ 863e313
            system_pid = _query_pid([])
            user_pid = _query_pid(["--user"])
            if str(current_pid) == system_pid:
                scope_flags = []
                systemctl_scope = "systemctl"
            elif str(current_pid) == user_pid:
                scope_flags = ["--user"]
                systemctl_scope = "systemctl --user"
            else:
                # MainPID does not match in either scope — likely invoked
                # outside of systemd or the unit was renamed.  Bail out
                # rather than restart the wrong unit.
                return
```

前置条件:linux + `INVOCATION_ID` 存在(systemd 注入的调用标记,9992-9993)。此前硬编码
`--user` 曾害死 system-unit 部署(MainPID 查空 → helper 不派生 → gateway 死到手工重启,
注释 10013-10020)。整体 best-effort:调用方 `_stop_impl` 在其后**无条件**以退出码 75
(TEMPFAIL)退出,配合 `RestartForceExitStatus=75` 让 systemd 把计划重启当受控失败拉起
(run.py:13116-13129 的注释交代:非 root 单元 `systemd-run --system` 常被 Polkit 拒、
headless 无 user bus、operator 可能用 `Restart=on-failure`)——helper 只是锦上添花的
「立即」通道,75 才是兜底通道。

**重实现要点**:1) 计划重启与崩溃重启要走不同的 supervisor 通道(transient unit vs 退避);
2) system/user 域必须探测,用 MainPID==自身 PID 做所有权证明;3) helper 必须 best-effort,
真正的保证靠退出码协议;4) `--collect` 让 transient unit 完成即回收,不留垃圾。

---

## 10. `_await_active_work_before_restart` —— 先等 turn 做完,再进 stop()(10077-10147)

**问题**(#77184):in-band `/restart` 过去立刻调 stop(),把**发起重启的那个 turn 本身**
折进 drain 等待集,`restart_drain_timeout`(默认 0!)一到就被强中断——用户下达 /restart,
自己正在收的回答被拦腰砍断。

**实现**:重启序列在 stop() 之前插入一个独立等待段:拒收新 turn(`_draining=True`,由
request_restart 置),然后等 `_active_work_count()`(agent+cron+api 三合一,run.py:7381)
归零,上限 `_restart_after_turn_timeout`:

```python
# gateway/run.py:10090-10101 @ 863e313
        active = self._active_work_count()
        if active <= 0:
            return True

        timeout = float(getattr(self, "_restart_after_turn_timeout", 0.0) or 0.0)
        if timeout <= 0:
            logger.info(
                "Restart requested with %d active work unit(s); "
                "restart_after_turn_timeout=0 — entering stop()/drain immediately",
                active,
            )
            return False
```

等待期间每 30s 打点并刷 "draining" 状态(10129-10140),0.1s 轮询;超时返回 False,
调用方照进 stop()(那里再由 restart_drain_timeout 决定强中断)。默认值 21600s(6h),
配置注释明说这是「防 agent 卡死的安全阀,不是目标延迟」(hermes_cli/config_defaults.py:48-55);
与 `restart_drain_timeout=0` 组成新分工:**耐心等在 stop() 之前,stop() 之内速战速决**
(必须短于 systemd TimeoutStopSec,否则请 SIGKILL 吃 mid-cleanup)。

**重实现要点**:1) 「拒新 + 等旧」要发生在进入强中断域**之前**,两个超时职责分离;
2) 等待对象必须是全量在飞工作计数(复用 §1 的三合一);3) 0 值语义 = 保留旧行为的逃生门;
4) 长等待要有周期性可观测输出(日志+状态文件)。

对应测试:tests/gateway/test_restart_after_turn.py。

---

## 11. `request_restart` —— 重启编排入口与 task 生命周期陷阱(10149-10188)

```python
# gateway/run.py:10149-10159 @ 863e313
    def request_restart(self, *, detached: bool = False, via_service: bool = False) -> bool:
        if self._restart_task_started:
            return False
        self._restart_requested = True
        self._restart_detached = detached
        self._restart_via_service = via_service
        self._restart_task_started = True
        # Refuse new turns immediately while in-flight work finishes.
        # Keep ``_running`` True so adapters stay connected and the active
        # turn can still deliver its final response (#77184).
        self._draining = True
```

- 幂等(`_restart_task_started` 单向门);`_draining=True` 拒新但 `_running` 保持 True——
  适配器不断连,当前 turn 的最终回复还能送达(#77184);
- `_run_restart` 协程:after-turn 等待 → (detached 时)派 watcher(**此时才派**:watcher
  deadline 是 drain+5,早派会在请求 turn 还在跑时就触发 `hermes gateway restart`,
  10163-10166 注释)→ `stop(restart=True, …)`;
- **task 引用双坑**(10175-10187 注释,#12875):不能放进 `_background_tasks`
  (`_stop_impl` 会取消该集合全部成员,而 `_run_restart` 正 await `_stop_task`,取消会把
  CancelledError 传进 `_stop_impl`,`_shutdown_event.set()`/退出码 75 都到不了);
  又必须存 `self._restart_task` 持强引用(裸 create_task 弱引用可被 GC);
  `_stop_impl` 的取消循环显式跳过它(run.py:12987)。

**调用者**(三个入口,统一汇到此):
- in-chat `/restart`:gateway/slash_commands.py:1624-1629——supervisor/容器环境
  `via_service=True`,裸进程 `detached=True`(setsid 链在 systemd KillMode=mixed / Docker tini
  下都活不下来,注释 1610-1618);
- SIGUSR1:run.py:26699-26700(`request_restart(detached=False, via_service=True)`;
  hermes_cli/gateway.py:258 文档化此约定);
- `hermes update` 自更新流程(hermes_cli/update_cmd.py:4960 注释链)。

**重实现要点**:1) 重启入口做成幂等状态机(requested/detached/via_service 三标志 + 单向门);
2) 「拒新」与「断连」是两个独立开关,重启要前者不要后者;3) 编排 task 既要防 GC 又要防
被自家停机取消——强引用 + 显式豁免,二者缺一即死锁或静默;4) 辅助 watcher 的派生时机必须在
等待段之后。

---

## 12. 启动恢复(一):同步屏障 `_run_startup_resume_event` + 入站排队门(10199-10342)

**问题**:boot 自动续跑与真实用户消息赛跑。`BasePlatformAdapter.handle_message()` 装好
守卫、spawn 后台任务就返回——返回≠turn 结束,用户消息可在续跑 turn 刚起步时插进来撞车。

### 12a. `_run_startup_resume_event`(10199-10227)

```python
# gateway/run.py:10214-10227 @ 863e313
        try:
            await adapter.handle_message(event)
            session_tasks = getattr(adapter, "_session_tasks", {})
            task = session_tasks.get(session_key) if isinstance(session_tasks, dict) else None
            if task is not None:
                await asyncio.shield(task)
        finally:
            # _schedule_resume_pending_sessions pre-claims the runner slot
            # before spawning this task.  If adapter.handle_message raises
            # before _handle_message takes ownership, release that pre-claim;
            # otherwise the real run's normal cleanup owns the slot.
            _pre_state = self._peek_session_state(session_key)
            if (_pre_state.turn.agent if _pre_state else None) is _AGENT_PENDING_SENTINEL:
                self._release_running_agent_state(session_key)
```

- 穿透 adapter 拿到 `_session_tasks[session_key]` 再 `shield`-await 真正的 turn task——
  边界从「已受理」推进到「已完成」;
- finally 里检查槽位是否仍是哨兵:是 ⇒ handle_message 在真 run 接管前就抛了,释放预占;
  否则真 run 的正常清理拥有槽位(预占-移交协议见 §14)。

### 12b. 排队门:`_queue_startup_restore_event`(10229-10243)+ `_drain_startup_restore_queue`(10245-10269)

`_handle_message` 在门开着时把**非 internal、非重放**的入站消息全部入队直接返回
(run.py:14383-14389);排空时给事件打 `_hermes_startup_restore_replay=True` 标记重放
(10263-10266),防止门还没关时重放消息又被入队成死循环。

### 12c. `_finish_startup_restore`(10271-10327)—— 有界门闩

**问题**:门在续跑 turn 全部完成前不开,一个病态长的 boot-resume turn 会把**所有渠道**的
入站压住不回。

```python
# gateway/run.py:10286-10301 @ 863e313
            timeout = _startup_restore_drain_timeout_secs()
            if timeout > 0:
                # asyncio.wait (unlike wait_for / gather+timeout) does NOT
                # cancel the pending tasks on timeout — the slow resume turn
                # keeps running in the background instead of being killed.
                done, pending = await asyncio.wait(tasks, timeout=timeout)
                if pending:
                    logger.warning(
                        "Startup-restore gate released after %.0fs with %d boot "
                        "auto-resume turn(s) still running; draining inbound "
                        "queue now (resume slots already claimed, so no "
                        "duplicate agents). Slow turn(s) continue in the "
                        "background.",
```

- 上界 `HERMES_STARTUP_RESTORE_DRAIN_TIMEOUT`(默认 30s,run.py:912;桥接自 config
  `agent.gateway_startup_restore_drain_timeout`,run.py:967-993);非正值 = 旧「无限等」;
- 选 `asyncio.wait` 而非 `wait_for/gather`:超时**不取消** pending——慢 turn 继续跑;
- 提前放行安全的根据:§14 在 spawn 前**同步**预占了 `_running_agents` 槽位,排空的消息会
  排在槽位后面而不是再起一个 agent(docstring 10277-10283);
- 放行后仍在跑的 task 挂 `_log_background_resume_result` done-callback(10307-10308;
  10329-10342)——否则晚到的失败被 `_background_tasks.discard` 静默吞掉;
- 已完成 task 逐个取 `exception()` 记 debug(10314-10322)。

**重实现要点**:1) 「启动恢复优先于入站」用显式队列 + 门闩实现,别指望时序巧合;
2) 门必须有界,且超时用不取消语义(asyncio.wait),慢恢复降级为后台而非被杀;
3) 提前放行的前提是互斥已由「同步预占槽位」保证,门只管顺序不管互斥;
4) 重放消息要打标记免二次入队;5) 出门后的孤儿 task 必须补挂结果日志回调。

对应测试:tests/gateway/test_startup_restart_race.py、test_restart_resume_pending.py。

---

## 13. `_redeliver_pending_obligations` —— 送达账本补投:答案比重跑便宜(10344-10449)

**问题**(#58818/#41696/#63695):最终回复生成后、平台 ACK 前崩溃,文本只活在 Python 局部
变量里——token 已烧,内容无迹可寻。早先的 delivery-outbox 尝试因**静默重发歧义消息**被
合同评审毙掉(#61790),本机制的核心改进是「歧义必须可见」。

**实现**:gateway/delivery_ledger.py 在 state.db 里按发送三检查点记账
(pending→attempting→delivered/failed,delivery_ledger.py:12-17);启动时本方法
(调用点 run.py:11447,**先于** `_schedule_resume_pending_sessions`,注释 11442-11446:
补投已有答案严格便宜且更正确于重跑整个 turn):

1. `ledger_enabled()`(delivery_ledger.py:339,默认开,`gateway.delivery_ledger: false` 关)
   与 `sweep_recoverable(deliverable_platforms=…)` 都套 `asyncio.to_thread`(10369-10379)
   ——SQLite IO 不上事件循环;
2. **只认领本 boot 能发的平台**:`self.adapters` 只含 connect() 成功者;每次认领消耗该行
   3 次重投预算之一,连不上的平台若也认领,就会「每 boot 烧一次预算、一次没真发过就到顶」
   (delivery_ledger.py:250-255;sweep 内 10379 与 delivery_ledger.py:279-285);
   认领本身是 owner-stamp 守卫的原子 UPDATE,双 gateway 竞扫不会双认领(delivery_ledger.py:286-292);
3. 歧义标记:

```python
# gateway/run.py:10401-10403 @ 863e313
            content = row["content"]
            if row.get("needs_marker"):
                content = RECOVERED_MARKER + content
```

   `needs_marker = state != "pending"`(delivery_ledger.py:301-303):send 从未开始的行
   原样补投;mid-send(attempting)与曾被拒(failed)的行前缀
   「♻️ Recovered reply — … may be a duplicate」(delivery_ledger.py:68-71)——诚实的
   at-least-once,可能重复但绝不静默重复;
4. 成功 `mark_delivered`、失败 `mark_failed`(10419-10434);无论成败,**只要行被认领**就
   `clear_resume_pending(session_key)`(10440-10448)——答案已到(或已欠付),不能再让
   恢复路径重跑重付一遍;
5. 毒行界:3 次尝试上限 + 24h 陈旧线 → abandoned,7 天保留后剪除(delivery_ledger.py:61-64)。

**文档-代码冲突候选**:docstring 说 "Returns the number of redeliveries **attempted**"
(run.py:10358),但 `redelivered` 只在 `mark_delivered` 成功分支自增(10420-10422)——
实际返回的是**成功数**。仅返回值语义注释失准,调用方(11447)不消费返回值,无行为影响。

**重实现要点**:1) 「产出但未确认送达」是独立于转录的资产,要单独记账,检查点必须夹住 await;
2) 崩溃语义按状态分流:未发过→原样投,歧义/被拒→带可见标记投,禁止静默重发;
3) 认领 = 原子换 owner + 扣预算,预算只许花在真能发送的目标上;
4) 补投优先于重跑,且两机制间用 clear_resume_pending 互斥;5) 毒行三重界(次数/陈旧/保留)。

对应测试:tests/gateway/test_delivery_ledger.py、test_delivery_ledger_producer.py、
test_restart_redelivery_dedup.py。

---

## 14. `_schedule_resume_pending_sessions` —— 自动续跑:五重闸门 + 槽位预占(10451-10589)

**机制**:枚举 session store 中 `resume_pending` 且 `resume_reason ∈ _AUTO_RESUME_REASONS`
的会话,为每个合成一个**空文本 internal 事件**,交 §12a 跑一遍完整消息管线。空文本是关键:
`_handle_message_with_agent` 的 `_is_resume_pending` 分支(run.py:5307-5335)负责注入
reason-aware 恢复系统提示(交互平台报告恢复并询问,webhook/API 等无人平台直接续做任务,
#57056),本方法不写文案,单一来源不重复。

`_AUTO_RESUME_REASONS`(10195-10197):`restart_timeout`/`shutdown_timeout`
(drain 超时强中断,由 `_stop_impl` 12831、12902-12903 写)+ `restart_interrupted`
(崩溃恢复:无 `.clean_shutdown` 标记时 `suspend_recently_active()` 写,
gateway/session.py:2877-2881)。三者共义「mid-turn 被杀」。

候选过滤(10478-10485):`resume_pending and not suspended and origin is not None and
reason ∈ AUTO_RESUME and (platform is None or 匹配)`——`suspended` 在此压过恢复标记
(§7 熔断的执行点);`platform` 参数供重连路径定向重试(run.py:12512:启动时适配器离线的
平台重连后,只补自己平台的会话,不碰别家在飞恢复)。

五重闸门(逐条):
1. **restart-loop 熔断**(#30719 defense-3,10500-10508):有候选才
   `restart_loop_guard.check_and_record()`(gateway/restart_loop_guard.py:122-150,
   状态在 `<HERMES_HOME>/gateway/restart_loop.json`,默认 60s 窗内 ≥3 次
   「带恢复候选的 boot」即跳过本 boot 的全部 auto-resume;干净 boot 不计数;失败 fail-OPEN)。
   会话保持 resume_pending,真人消息仍可续——「把人放回环里」;
2. **新鲜度窗**(10513-10515):`last_resume_marked_at`(退回 `updated_at`)超过
   `_auto_continue_freshness_window()`(run.py:949-964,委托 gateway/session.py 的
   单一真源,配置 `agent.gateway_auto_continue_freshness`)即跳过——太久前的中断不该突然诈尸;
3. **已在跑**(10517-10519):`_is_session_running` 防启动 pass 与重连 pass 重复续;
4. **适配器就绪**(10522-10530):不就绪静默跳过,留给重连 pass 或下条真消息;
5. **授权复查**(#23778,10538-10551):owner 已被移出 allowlist 的会话不许因一个恢复标记
   在重启后静默收到完整回复;校验抛异常也跳过(fail-closed)。

**槽位预占**(#45456,与 §12 的门闩配对):

```python
# gateway/run.py:10553-10561 @ 863e313
            # Claim the session slot *before* spawning the task so that an
            # inbound message arriving between task creation and the task's
            # first await (where _process_message_background sets the real
            # sentinel) sees the slot as occupied and queues behind it
            # instead of spinning up a duplicate AIAgent (#45456).
            _resume_state = self._session_state(entry.session_key)
            _resume_state.turn.agent = _AGENT_PENDING_SENTINEL
            _resume_state.turn.started_ts = time.time()
            self._persist_active_agents()
```

同步(spawn 前)置哨兵,消灭「task 已建但首个 await 未至」的窗口;task 进 `_background_tasks`
(强引用)且在门开着时同时进 `_startup_restore_tasks`(10572-10582,供 §12c 等待)。

**重实现要点**:1) 恢复提示文案只在消息管线一处生成,调度器只投「空事件+标记」;
2) reason 白名单显式列举,新增中断来源必须显式 opt-in;3) 每重闸门单独可解释
(熔断/新鲜度/互斥/就绪/授权),顺序从便宜到贵;4) 互斥靠 spawn 前同步预占哨兵 + 失败路径
释放(§12a finally);5) 熔断必须 fail-open 且只对「有候选的 boot」计数;
6) 授权是随时间漂移的,恢复路径必须以**当下**的 allowlist 复查历史会话。

对应测试:tests/gateway/test_restart_resume_pending.py、test_resume_command.py、
tests/gateway/test_stuck_loop.py(loop guard 部分)。

---

## 15. `_startup_should_abort` / `_abort_startup_if_shutdown_requested` —— 启动中途弃航(10591-10622)

启动是长流程(逐平台 connect),期间可能收到 SIGTERM/`/restart`。`start()` 在每个平台循环
头部查询(run.py:11052-11053):

```python
# gateway/run.py:10591-10596 @ 863e313
    def _startup_should_abort(self) -> bool:
        return (
            self._restart_requested
            or self._draining
            or self._shutdown_event.is_set()
        )
```

弃航时:先取消刚建 adapter 的后台任务并安全断连(10606-10611),然后**汇入而非另起**停机:
`_stop_task` 已存在且非当前 task 就 await 它;否则(未设 shutdown 事件)自己发起
`stop(restart=…)` 把三个重启标志原样带过去(10612-10621)。返回 True 让 start() 直接 return。

**重实现要点**:1) 长启动流程要在每个昂贵步骤间插弃航检查;2) 弃航必须清理本步骤已创建的
半成品资源;3) 与并发停机的汇合协议:有 stop_task 等它、没有才发起,防双 stop;
4) 弃航传播重启意图(restart/detached/via_service),别把重启降级成裸停机。

---

## 16. loop 活性护栏 `_start/_stop_loop_liveness_guards`(10624-10662)

**问题**(#66892/#69089):asyncio loop 冻死时,一切基于 asyncio 的自愈(drain deadline、
状态重写、取证)结构性失效;launchd/systemd KeepAlive 只救**死进程**,「活着但冻住」的
gateway 是要手工 SIGKILL 的僵尸。

**实现**(实现体在 gateway/shutdown_watchdog.py,本段是装配点):
- `_arm_loop_floor_timer(loop)`(shutdown_watchdog.py:96-107):自续期 5s 定时器,
  保证 selector 永远有一个有限超时——loop 若还能跑 timer,现存 async 恢复任务就有机会复位;
- `start_loop_liveness_watchdog(loop)`(shutdown_watchdog.py:110+):**OS 线程**周期探测
  (30s 一探、10s 应答窗、3 击出局),连续失败即 dump 全线程栈 + `os._exit(75)` 让
  supervisor 拉起——「循环外」是本质:诊断与自杀不能依赖被诊断的循环;
- 开关:`gateway.loop_watchdog: false`,**config-only、无环境变量覆盖**(#69089,
  10627-10632 docstring 明示);两个句柄各自幂等装配(is None / not is_alive 才建,
  10633-10644);
- 拆除(10646-10662):`stop()` 第一步调用(run.py:12669-12671)——停机本身会重载 loop
  (drain 轮询、executor 等待),不先拆护栏会被 watchdog 误判冻死而 `os._exit`,
  docstring:「Disarm lifetime liveness guards before shutdown can load the loop」。
  拆除函数把属性先置 None 再操作旧句柄,幂等且异常全吞。

**重实现要点**:1) 监督「事件循环活性」的机构必须活在循环之外(OS 线程)且出口是 `os._exit`
级别;2) floor timer 与 watchdog 是互补两层:前者给 loop 自愈机会,后者兜底他杀;
3) 停机前必须先解除武装,否则正常停机负载触发误杀;4) 探测参数(间隔/超时/击数)要留配置
开关但默认开启;5) 退出码复用服务重启协议(75),让 supervisor 语义正确地拉起。

对应测试:tests/gateway/test_loop_liveness_watchdog.py、test_shutdown_watchdog.py、
test_shutdown_forensics.py。

---

## 17. 文档-代码冲突候选(汇总)

| # | 位置 | 内容 | 判定 |
|---|------|------|------|
| 1 | run.py:9717-9718 vs 9713-9716 | 行内注释称「保留不活跃但 >0 的旧计数条目」,代码实际只保留活跃键、丢弃其余(与 docstring 9702-9704 一致) | 注释残留,行为以 docstring 为准;候选 ▲ |
| 2 | run.py:10358 | docstring 称返回「redeliveries **attempted**」,实际 `redelivered` 只计 `mark_delivered` 成功分支(10420-10422),是成功数 | 返回值语义注释失准,无调用方受影响;候选 ◇ |
| 3 | website/docs/user-guide/messaging/index.md:235-252 | 送达账本文档(3 次/24h/7 天/标记语义/默认开) | 与 delivery_ledger.py:61-71、339-350 逐条核对**一致**,非冲突,记录为已验证 |

---

## 18. 覆盖对账(9184-10663 全部交代)

| 行段 | 内容 | 节 |
|------|------|----|
| 9184-9241 | `_drain_active_agents` | §1 |
| 9243-9251 | `_interrupt_running_agents` | §2 |
| 9253-9451 | `_notify_active_sessions_of_shutdown` | §3 |
| 9452-9522 | `_finalize_shutdown_agents` | §4 |
| 9524-9545 | `_should_emit_long_running_notification` | §5 |
| 9547-9556 | `_CLEANUP_TIMEOUT_S` 注释与常量 | §6a |
| 9558-9594 | `_defer_agent_cleanup_until_future_done` | §6b |
| 9596-9634 | `_cleanup_agent_resources_off_loop` | §6a |
| 9636-9693 | `_cleanup_agent_resources` | §6c |
| 9695-9793 | stuck-loop 三方法与常量 | §7 |
| 9795-9980 | `_launch_detached_restart_command` | §8 |
| 9982-10075 | `_launch_systemd_restart_shortcut` | §9 |
| 10077-10147 | `_await_active_work_before_restart` | §10 |
| 10149-10188 | `request_restart` | §11 |
| 10190-10197 | `_AUTO_RESUME_REASONS` | §14 |
| 10199-10227 | `_run_startup_resume_event` | §12a |
| 10229-10269 | 排队门两方法 | §12b |
| 10271-10342 | `_finish_startup_restore` + `_log_background_resume_result` | §12c |
| 10344-10449 | `_redeliver_pending_obligations` | §13 |
| 10451-10589 | `_schedule_resume_pending_sessions` | §14 |
| 10591-10622 | 启动弃航两方法 | §15 |
| 10624-10662 | loop 活性护栏装配/拆除 | §16 |

关联外部文件(调用关系索引):agent/interrupt_compat.py:9;gateway/drain_control.py:68,189,229;
gateway/shutdown_flush.py:272;gateway/restart_loop_guard.py:70,89,122;
gateway/delivery_ledger.py:68,236,339;gateway/shutdown_watchdog.py:96,110;
gateway/session.py:2850-2884;gateway/restart.py:23-35;gateway/slash_commands.py:1609-1632;
hermes_cli/config_defaults.py:40-55;hermes_cli/gateway.py:258;
run.py 本文件内:2465、3352、5307-5335、7378-7421、7471-7492、11017-11041、11437-11449、
12512、12659-12943、12987、13094-13129、14383-14389、17033/17105、17647-17663、
25003-25006、26699-26700。
