# r7 底稿 · gateway/run.py 第 5 段(12659–14328)——停机序列 / multiplex 多 profile 适配器 / 异步委托会话绑定 / 忙时命令面

> 对象:`/home/user/hermes-agent/gateway/run.py` 12659–14328 行 @ 863e313(GatewayRunner 第 5 段)。
> 溯源格式:`路径:行号 @ 863e313` + 逐字摘录。所有行号已用 Read 逐段核实。
> 段内结构:`stop()`(12659–13175)→ `wait_for_shutdown`(13176–13178)→ multiplex 启动三件套(13180–13419)→ secondary 重连(13420–13541)→ profile fatal error(13543–13585)→ message handler 工厂(13587–13629)→ 凭据独占声明(13631–13710)→ `_create_adapter`(13712–13841)→ `_make_adapter_auth_check`(13843–13879)→(13880–13885 空行)→ `_deliver_platform_notice`(13886–13926)→ `_resolve_async_delegation_session`(13928–14076)→ 忙时命令面(14078–14327)→ 14328 起为 `_handle_message`(下一段)。

---

## 一、stop() —— 517 行停机序列(gateway/run.py:12659–13175)

### 1.1 问题

一个长驻 gateway 停机时要同时对付:正在跑的 agent 轮(可能几分钟)、cron 任务、异步委托、bash/browser 子进程、多平台 adapter 连接、SQLite WAL 写锁、systemd 的 TimeoutStopSec 升级 SIGKILL、以及"停机路径本身卡死"这一元问题。涉及 issue:#8202(子进程被 systemd 而非我们杀掉)、#60432(cron 把被截断的输出当成功)、#66892(停机路径冻结,asyncio 超时救不了)、#27856(drain 中途被 kill 丢会话)、#53175(idle agent 的 memory provider 卡死导致 SIGTERM 杀不死进程)、#12875(取消 restart task 导致退出码丢失)、#72680(FTS5 损坏时清 pending 造成永久数据丢失)、#14210(httpx 客户端泄漏 EMFILE)、#42675(docker restart 后误存 stopped 状态导致不自启)、#7536(会话卡死循环)。

### 1.2 入口:幂等 + restart 标志(12659–12678)

`gateway/run.py:12669-12678 @ 863e313`:
```python
        _stop_guards = getattr(self, "_stop_loop_liveness_guards", None)
        if callable(_stop_guards):
            _stop_guards()
        if restart:
            self._restart_requested = True
            self._restart_detached = detached_restart
            self._restart_via_service = service_restart
        if self._stop_task is not None:
            await self._stop_task
            return
```
- 幂等:第二个并发 `stop()` 调用只 await 已有 `_stop_task`(创建于 13173:`self._stop_task = asyncio.create_task(_stop_impl())`),不会跑两遍。
- restart 三个布尔在真正停机前先记下,后续阶段(detached 重启、exit code 75、状态持久化)据此分叉。
- `getattr` 守卫是测试友好:shutdown 测试用 `object.__new__` 造裸 runner,没有 liveness guard 机制(见 12667–12668 注释)。`_stop_loop_liveness_guards` 定义在 run.py:10646。

### 1.3 内嵌 `_kill_tool_subprocesses(phase)` —— 四路清扫 + cron 防"假成功"(12681–12744)

清扫顺序:① `tools/process_registry.process_registry.kill_all()` 杀全部工具子进程;② `cron/scheduler.mark_running_jobs_interrupted()`(cron/scheduler.py:366)把在飞 cron 任务标为 interrupted;③ `tools/async_delegation.interrupt_all()` 中断后台委托;④ `tools/terminal_tool.cleanup_all_environments()` + `tools/browser_tool.cleanup_all_browsers()`。每步独立 try/except,单一子系统失败不阻塞其余(12691–12692 注释)。

② 的动机是 #60432 的精确因果:`gateway/run.py:12704-12717 @ 863e313`:
```python
                try:
                    # Any cron job still dispatched at this instant just had
                    # its tool subprocess killed above (kill_all() has no
                    # per-job-ID targeting — it's a global sweep). Its agent
                    # thread is still alive in this process and may go on to
                    # produce a plausible-looking final response from the
                    # now-truncated tool output; mark the run interrupted so
                    # the scheduler can never report that as success (#60432).
                    # No-op when no cron job is in flight.
                    from cron.scheduler import mark_running_jobs_interrupted
                    _interrupted = mark_running_jobs_interrupted(
                        f"Gateway shutdown ({phase}) killed the job's tool "
                        "subprocess before the run finished."
                    )
```
即:kill_all 是全局扫射,无法按 job 定向;被杀掉的是 cron 任务的工具子进程,但其 agent 线程还活着,可能拿着被截断的工具输出编出一个"看起来合理"的最终回复——必须先在调度器侧打 interrupted 标记,让它永远不能被上报为成功。

该函数被调用**两次**(12684–12689 注释 + 12931、13029 两个调用点):一次在 drain 超时强制中断 agent 之后立刻调("post-interrupt",赶在 systemd TimeoutStopSec 对 cgroup 升级 SIGKILL 之前抢回 bash/sleep 子进程,#8202);一次在 `_stop_impl` 末尾兜底("final-cleanup",覆盖优雅路径 + 中途重生的进程)。

### 1.4 线程级停机看门狗(12746–12788,#66892)

`gateway/run.py:12746-12752 @ 863e313`:
```python
            # Thread-based shutdown watchdog (#66892): asyncio timeouts cannot
            # recover a frozen loop. Arm a plain OS thread at the start of
            # stop(); if teardown never finishes within drain+grace it dumps
            # faulthandler stacks and os._exit so KeepAlive/systemd can revive.
            # Skip under pytest so stop()-driving unit tests don't get a
            # delayed hard-exit in the worker.
            _watchdog_done = threading.Event()
```
- 设计理由:停机卡死时事件循环本身可能被冻结,任何 asyncio 级超时(`wait_for` 等)都依赖循环还活着,因此救不了;必须用纯 OS 线程。`arm_shutdown_watchdog`(gateway/shutdown_watchdog.py:337)是 daemon 线程,以 1s 步进等 `done_event`,超时后写 faulthandler 全线程栈转储(文件 + stderr 双写,"wedged disk" 是 #66892 假设之一,见 shutdown_watchdog.py:324–325)再 `os._exit(exit_code)`;退出前先释放 PID 文件与运行锁再 drain 日志队列(shutdown_watchdog.py:400–403)。
- 时限 = drain_timeout + grace(`resolve_shutdown_watchdog_delay`,shutdown_watchdog.py:274–288)。
- `snapshot_fn`(12756–12772)在触发时采集 restart/draining/active agents/cron/api 计数与阶段耗时,进转储头部,便于事后归因。
- pytest 下跳过布防(12774),否则驱动 stop() 的单测会在 worker 里收到延迟硬退出。
- `try/finally` 保证 `_watchdog_done.set()`(12782–12788)——正常完成即解除。

### 1.5 停机主体 `_stop_impl_body` 逐阶段(12790–13171)

每阶段都打 `Shutdown phase: ... at +%.2fs` 日志(`_phase_elapsed`,12798–12799),是排障时的时间轴。

**P1 翻标志 + 停外围(12801–12808)**:`self._running = False; self._draining = True`;停 systemd sd_notify 心跳(`_stop_systemd_watchdog`,run.py:12651–12657,注释"Stop heartbeats before any potentially long shutdown drain"——否则长 drain 期间心跳停了会被 systemd 当 hang 杀掉,索性先主动停);取消 secondary profile 重连任务(`_cancel_secondary_profile_reconnect_tasks`,run.py:12603–12633,见 §4)。

**P2 通知活跃会话(12810–12816)**:`_notify_active_sessions_of_shutdown()`(run.py:9253)。注释点明顺序约束:"Adapters are still connected here, so messages can be sent"——必须在 drain/断连**之前**发。

**P3 预标 resume_pending(12820–12835,#27856)**:`gateway/run.py:12820-12833 @ 863e313`:
```python
            # Pre-mark sessions as resume_pending BEFORE the drain wait.
            # If the process is killed by the service manager during the
            # drain, the durable marker is already written so the next
            # gateway boot can recover in-flight sessions (#27856).
            _pre_drain_keys: list[str] = []
            for _sk, _agent in list(self._running_agents.items()):
                if _agent is _AGENT_PENDING_SENTINEL:
                    continue
                try:
                    await self.async_session_store.mark_resume_pending(
                        _sk,
                        "restart_timeout" if self._restart_requested else "shutdown_timeout",
                    )
                    _pre_drain_keys.append(_sk)
```
`mark_resume_pending`(gateway/session.py:2751–2778)保留 session_id + transcript,下一条消息自动续上同一会话;且**从不覆盖显式 suspended**(session.py:2769–2772,suspended 是 /stop 或卡死升级的硬信号)。`_AGENT_PENDING_SENTINEL`(run.py:2465)代表"已占坑未启动"的 agent,无需标记。

**P4 drain + 优雅清标(12837–12869)**:`_drain_active_agents(timeout)`(run.py:9184)等 agent 自然跑完,超时上限 `self._restart_drain_timeout`。若未超时,把 P3 预标的、且已不在 `_running_agents` 里的会话逐个 `clear_resume_pending`(session.py:2780)——否则跑完的会话下轮还会带上一条"被重启打断"的陈旧系统注记。

**P5 超时路径(12871–12935)**:再次对**当前** `_running_agents` 标 resume_pending。为什么不用 drain 开始时的快照?`gateway/run.py:12892-12901 @ 863e313`:
```python
                # Iterate self._running_agents (current) rather than the
                # drain-start ``active_agents`` snapshot — the snapshot
                # may include sessions that finished gracefully during
                # the drain window, and marking those falsely would give
                # them a stray restart-interruption system note on their
                # next turn even though their previous turn completed
                # cleanly.  Skip pending sentinels for the same reason
                # _interrupt_running_agents() does: their agent hasn't
                # started yet, there's nothing to interrupt, and the
                # session shouldn't carry a misleading resume flag.
```
随后 `_interrupt_running_agents(reason)`(run.py:9243;reason 取 `_INTERRUPT_REASON_GATEWAY_RESTART`/`_SHUTDOWN`,定义于 run.py:2837–2838),给 5 秒宽限循环(12918–12921,期间持续 `_update_runtime_status("draining")`),然后**立即** `_kill_tool_subprocesses("post-interrupt")`(12931,#8202:不能拖到 stop() 尾部,systemd 可能先升级 SIGKILL,子进程就变成"被 systemd 杀"而非"被我们杀",丢掉清理语义)。注释同时交代分层:resume_pending 管"下条消息续会话";真正卡死的会话由 `.restart_failure_counts` 卡死计数(阈值 3)升级成 `suspended=True` 并覆盖 resume_pending(12886–12891)。

**P6 detached restart(12937–12941)**:`_restart_detached` 时调 `_launch_detached_restart_command()`(run.py:9795),失败只记 error 不中断停机。

**P7 收尾 agent + idle 缓存(12943–12965)**:`_finalize_shutdown_agents(active_agents)`(run.py:9452)处理 drain 时刻还在轮中的 agent;随后单独处理 `_agent_cache` 里的 idle agent——它们的 MemoryProvider 从没收到 on_session_end。逐个走 `_cleanup_agent_resources_off_loop`(run.py:9596),注释:"Bounded + off-loop so a wedged memory provider on one idle agent can't hang shutdown indefinitely — that path is why SIGTERM failed to kill the process (#53175)"(12960–12962)。即 #53175 的根因就是 idle agent 清理挂在事件循环里。

**P8 adapter 断连(12967–12982)**:先 primary(`self.adapters`)后 secondary(`self._profile_adapters` 两层字典),都走 `_bounded_adapter_teardown`(run.py:6525,带超时预算),profile 版多传 `profile=_prof` 便于日志。

**P9 后台任务取消(12984–12994,#12875)**:`gateway/run.py:12984-12992 @ 863e313`:
```python
            for _task in list(self._background_tasks):
                if _task is self._stop_task:
                    continue
                if _task is self._restart_task:
                    # The restart orchestration task is awaiting _stop_task
                    # right now; cancelling it would propagate CancelledError
                    # into this _stop_impl and skip _shutdown_event.set() /
                    # _exit_code = 75 (#12875).  It self-terminates anyway.
                    continue
                _task.cancel()
```
#12875 的坑:`_restart_task` 此刻正 await `_stop_task`,取消它会把 CancelledError 传播进当前 `_stop_impl` 自身,跳过 `_shutdown_event.set()` 和 exit code 75——重启编排任务反正会自行终止,必须放过。

**P10 pending 落盘 + 状态清空(12999–13020,#72680)**:`gateway/run.py:12999-13007 @ 863e313`:
```python
            # Flush pending messages to disk before clearing (#72680).
            # When FTS5 corruption prevents message persistence, the
            # in-memory pending text is the only surviving copy.  Clearing
            # without flushing causes permanent data loss.
            try:
                from gateway.shutdown_flush import flush_pending_to_file
                flush_pending_to_file(dict(self._pending_messages), reason="shutdown")
            except Exception:
                pass
```
`flush_pending_to_file`(gateway/shutdown_flush.py:82)为每个非空 slot 原子写一个 0o600 的 `pending-<uuid>.json` 恢复文件并 fsync 目录。随后清空 `_running_agents/_running_agents_ts/_active_session_leases/_pending_messages/_pending_approvals/_busy_ack_ts`,注释强调真实 runner 上这些是 SessionState 视图,`clear()` 逐会话复位单字段而非整字典换新,并发写方不丢条目(13008–13011);最后 `_shutdown_event.set()`(13020)唤醒 `wait_for_shutdown`。

**P11 final kill + 辅助客户端回收(13029–13046,#14210)**:第二次 `_kill_tool_subprocesses("final-cleanup")`;`agent.auxiliary_client.shutdown_cached_clients()` 回收进程级缓存的 httpx 客户端——绑定在已死 worker 线程循环上的客户端(典型是 cron tick)只能在这里扫,否则长期运行累积 async httpx transport,在 macOS 默认 RLIMIT_NOFILE=256 下打爆 EMFILE(13035–13041 注释)。

**P12 关 SQLite(13048–13068)**:显式 close `self._session_db`(AsyncSessionDB 门面,`getattr(_self_db, "_db", _self_db)` 解包到同步句柄)与 `session_store._db`,释放 WAL 写锁——否则 `--replace` 类重启流程里旧进程握锁到 Python 真正退出,新 gateway 打开同一文件报 "database is locked"(13048–13052 注释)。再 `GatewayRunner._shutdown_executor(self)` 关线程池。

**P13 PID 文件与运行锁(13070–13072)**:`gateway.status.remove_pid_file()` + `release_gateway_runtime_lock()`。

**P14 clean-shutdown 标记条件写(13074–13092)**:`gateway/run.py:13082-13086 @ 863e313`:
```python
            if not timed_out:
                try:
                    (_hermes_home / ".clean_shutdown").touch()
                except Exception:
                    pass
```
超时被强制中断的会话可能处于"尾随 tool response、没有最终 assistant 消息"的残破状态(13077–13079),**故意不写标记**,让下次启动走 `suspend_recently_active()` 给用户干净的新会话,而不是恢复半截 tool loop。

**P15 卡死循环计数(13094–13100,#7536)**:停机时仍活跃的会话逐个 `_increment_restart_failure_counts`(run.py:9698);连续 3 次重启都在跑 → 下次启动自动 suspend,打破"会话让 gateway 崩→重启→会话又让它崩"的循环。

**P16 restart 标记 + exit 75(13102–13137)**:无外部命令来源的重启先原子写 planned-restart 通知标记(`_planned_restart_notification_path`,run.py:1797)。service 路线先试 `_launch_systemd_restart_shortcut()`(run.py:9982),但**无论 helper 成败都**置 `self._exit_code = GATEWAY_SERVICE_RESTART_EXIT_CODE`(= 75,gateway/restart.py:10)。理由(13118–13135 注释):helper 在真实部署常失败(非 root 单元调 `systemd-run --system` 被 Polkit 拒、headless 无 user bus、运维单元用 `Restart=on-failure` 而非 always);EX_TEMPFAIL(75)配合 unit 的 `RestartForceExitStatus=75` 让 systemd 把计划内重启当"受控失败"复活;干净退出 0 在 Linux 上曾让 gateway 死到有人重启主机为止。且只白名单 75:真崩溃退非 75 的非零码,仍受正常 `Restart=`/`RestartSec`/StartLimit 治理,不会被强制复活掩盖崩溃循环。

**P17 终态持久化(13139–13171,#42675)**:`gateway/run.py:13161-13169 @ 863e313`:
```python
            if getattr(self, "_signal_initiated_shutdown", False) and not self._restart_requested:
                logger.info(
                    "Gateway stopped by an unexpected signal — persisting "
                    "gateway_state=running so container_boot auto-starts on "
                    "the next boot (issue #42675)"
                )
                self._update_runtime_status("running", self._exit_reason)
            else:
                self._update_runtime_status("stopped", self._exit_reason)
```
#42675 因果:Docker(s6-overlay)的 `container_boot.py` 下次开机只自启上次状态为 "running" 的 gateway;例行 `docker compose up --force-recreate` 发的 SIGTERM 若被持久化成 "stopped"(或留下中途的 "draining"),消息通道就永久静默直到人工重启。区分手段:操作员主动停(`hermes gateway stop`、ExecStop、Ctrl+C)会在发信号**前**写 planned-stop 标记,归类为计划停机,如实存 "stopped";没有标记的信号(docker restart、OOM、裸 kill)视为意外,保留运行意图存 "running"。restart 也存 "stopped"(重启进程自己会拉起来)。最后 `_shutdown_gateway_health_export(self)`(run.py:26348)导出健康快照并打总耗时。

### 1.6 wait_for_shutdown(13176–13178)

```python
    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()
```
主循环挂在此处,P10 的 `_shutdown_event.set()` 是唯一唤醒点(这也是 #12875 保护 `_restart_task` 的原因链末端)。

### 1.7 重实现要点(停机序列)

1. **两层看门狗**:asyncio 内的 drain 超时管"业务收不完",纯 OS 线程的 watchdog 管"事件循环本身死了";后者必须 faulthandler 转储 + `os._exit`,且退出前先还锁再刷日志。
2. **持久标记先行**:resume 标记在 drain **前**先写一遍(进程可能在 drain 中被外力杀),优雅完成再清;超时路径按"当前活跃集合"而非快照重标,避免误伤已完成会话。
3. **子进程回收要抢时序**:强制中断 agent 后立即杀子进程,不能拖到序列尾部——外层监督者(systemd/s6)的 SIGKILL 升级在和你赛跑;同时把关联的调度任务(cron)标 interrupted,防"截断输出被上报为成功"。
4. **退出码即协议**:计划内 service 重启固定用一个白名单退出码(75 + RestartForceExitStatus),与真崩溃的非零码严格区分,既保证复活又不掩盖崩溃循环。
5. **终态 = 意图而非事实**:意外信号停机持久化 "running"(保留运行意图供下次自启),计划停机持久化 "stopped";区分靠"发信号前写 planned-stop 标记"。
6. **清理皆有界、皆兜底**:每个清理步骤独立 try/except + 超时预算 + off-loop,任何一个子系统卡死都不许拖垮整条序列;易失数据(pending 消息)清空前先落盘。

---

## 二、multiplex 多 profile 适配器启动(13180–13419)

### 2.1 问题

`gateway.multiplex_profiles` 开启后,一个 gateway 进程要同时服务多个 profile(各自独立的 HERMES_HOME、config.yaml、`.env` 凭据、skills、memory)。难点:① 每个 profile 的 adapter 必须在**它自己的**配置与密钥作用域下创建/连接/处理消息;② 两个 profile 配了同一个 bot token 会造成"同一 token 被两个客户端轮询"的逐消息竞速;③ HTTP 端口类平台只能由 default profile 独占监听;④ 单个坏 profile 不能拖垮整个 multiplexer。

### 2.2 作用域机制 `_profile_runtime_scope`(run.py:1938–1971,段外支撑)

`gateway/run.py:1939-1954 @ 863e313`:
```python
    """Scope config/skills/memory AND credentials to a profile for one turn.

    Combines the two seams the multiplexer needs:
      1. ``set_hermes_home_override`` — redirects ``get_hermes_home()`` (config,
         skills, memory, SOUL, sessions) to the profile's home. Contextvar, so
         it propagates into the agent worker thread via ``copy_context()``.
      2. ``set_secret_scope`` — installs the profile's ``.env`` secrets as the
         authoritative credential source, so ``get_secret`` reads this profile's
         keys and never the process-global ``os.environ`` (which in a
         multiplexer may hold another profile's values).

    Only used on the multiplexed inbound path. Single-profile gateways never
    enter this scope, so their behavior is unchanged. Loading the profile's
    ``.env`` here does NOT mutate ``os.environ`` — ``build_profile_secret_scope``
    returns an isolated dict — which is what keeps subprocesses (MCP, kanban)
    from inheriting cross-profile secrets.
    """
```
两条 seam:contextvar 的 home 重定向(能随 `copy_context()` 传进 agent worker 线程)+ 隔离字典的 secret scope(不污染 `os.environ`,子进程拿不到跨 profile 密钥)。本段所有"以某 profile 身份做事"的代码都以 `with _profile_runtime_scope(profile_home):` 包住。

### 2.3 `_start_secondary_profile_adapters`(13180–13266)

- 非 multiplex 直接返回 0(13195–13196);`profiles_to_serve(multiplex=True)`(hermes_cli/profiles.py:957,纯目录扫描,启动路径必须便宜)给出 `(name, home)` 对,active profile 跳过(由 primary 启动循环负责,13226–13227)。
- **claims 预占表**(13204–13223):`claimed: Dict[tuple, str]` 资源→属主 profile。先把 primary 已连 adapter 的凭据指纹与 listener 声明记到 active 名下;再把 `_failed_platforms`(primary 重连队列)里存的 `credential_claim`/`listener_claim` 也预占——`gateway/run.py:13217-13223 @ 863e313`:
```python
        # A retryable primary still owns its configured credential and listener.
        # Reserve both while it is queued so a secondary cannot take the endpoint
        # before the reconnect watcher retries the primary adapter.
        for retry_info in getattr(self, "_failed_platforms", {}).values():
            for claim_name in ("credential_claim", "listener_claim"):
                retry_claim = retry_info.get(claim_name)
                if isinstance(retry_claim, tuple):
                    claimed[retry_claim] = active
```
  即"排队重试中的 primary 仍拥有其资源",防 secondary 在重连窗口抢走端点。
- 逐 profile 调 `_start_one_profile_adapters`;异常分层(13232–13244):`SecondaryPortBindingConfigError` → 只 warning 跳过该 profile(单个坏 profile 不拖垮全局);`MultiplexConfigError` → **上抛**到启动守卫(安全类配置错必须 fatal,见 run.py:1924–1930 类注释:"config error means the operator must fix config.yaml…propagate to the startup guard instead of being treated as retryable adapter noise");其它异常 → error 日志继续。
- 收尾(13246–13264):为每个 served profile 建 `PairingStore`(active 用现成的,其余按 profile home 解析),供 authz_mixin 把配对校验路由到正确白名单;`write_runtime_status(served_profiles=...)` 供 `hermes status` 展示。

### 2.4 `_start_one_profile_adapters`(13268–13396)

顺序:
1. **scope 内加载该 profile 的 gateway config**(13274–13276)。
2. **open-policy 校验**(13276–13283):`_own_policy_open_startup_violation`(run.py:2428)发现某 profile 开了 `dm_policy/group_policy: open` 又没配 allow-all → 抛 `MultiplexConfigError`(fatal,安全问题不许降级为跳过)。
3. **端口绑定平台校验**(13285–13300):任何 enabled 且 `_platform_binds_port`(从 gateway/config.py 导入,run.py:1918–1921)判定绑端口的平台 → 抛 `SecondaryPortBindingConfigError`。设计:default profile 独占共享 HTTP listener,secondary 走 `/p/<profile>/` URL 前缀(报错文案 13294–13299 直接给修复指引)。
4. **逐平台创建**:RELAY 跳过(13307–13314 注释:relay 是进程级共享 ingress,active profile 拥有唯一连接,connector 打的 `source.profile` 负责把入站轮路由到 secondary);scope 内 `_create_adapter`(见 §6),失败/返 None 各自记日志继续。
5. **凭据冲突拒启**(13335–13351):`gateway/run.py:13336-13351 @ 863e313`:
```python
            credential_claim = self._adapter_credential_claim(platform, adapter)
            if credential_claim is not None:
                owner = claimed.get(credential_claim)
                if owner is not None:
                    logger.error(
                        "Profile '%s' and '%s' both configure %s with the same "
                        "credential — refusing to start the duplicate (one "
                        "credential cannot be consumed twice). Give each profile "
                        "its own %s credential.",
                        owner, profile_name, platform.value, platform.value,
                    )
                    # This adapter has not connected and therefore owns no
                    # resources to clean up. Calling disconnect here can mutate
                    # the shared platform state and, for a same-credential Photon
                    # adapter, shut down the primary profile's live sidecar.
                    continue
```
   关键取舍:冲突的 adapter **从未 connect,因此不调 disconnect**——同凭据的 Photon adapter 若 disconnect 会误关 primary 的活 sidecar(共享平台状态被污染)。listener 冲突(13353–13373)同理拒启不断连,报错文案直接指出该改 `platforms.<p>.extra.sidecar_port`。
6. **配置 + 连接**(13375–13395):`_configure_profile_adapter`;scope 内 `_connect_initial_adapter_with_timeout`(run.py:6647);成功才把 claim 登记到本 profile 名下(13384–13387,"先到先得,后来者看得见");失败/异常走 `_safe_adapter_disconnect`(run.py:6496)。

### 2.5 `_configure_profile_adapter`(13398–13418)

给 secondary adapter 装满一套 profile 化的钩子:profile message handler(§5)、profile fatal error handler(§4)、共享 session_store、busy session handler(`_handle_active_session_busy_message`,run.py:8742——忙时路径与冷路径同源)、reaction handler(可选)、Telegram topic 恢复函数、profile 绑定的 authz 回调(§7),最后同步 `_busy_text_mode`(run.py:5770 默认 "interrupt",8291 从配置载入;与 11102/12474 primary 路径同款赋值)。

### 2.6 重实现要点(multiplex 启动)

1. **作用域是上下文而非全局**:profile 的 home/密钥用 contextvar + 隔离字典注入,绝不写 `os.environ`;凡"以该 profile 身份"的创建/连接/消息处理全部包 scope。
2. **资源声明表集中裁决**:凭据与监听端点抽象为可哈希 claim 元组,在唯一能同时看到所有 profile 已解析凭据的地方(secondary 启动器)统一查重;排队重试者视同持有者。
3. **冲突处理三分级**:安全配置错 fatal 上抛;共享 listener 冲突跳过单 profile;运行时连接失败仅记日志重试。
4. **拒启的 adapter 不 disconnect**:未连接就没有可清理资源,disconnect 反而可能动到共享平台状态(误杀他人 sidecar)。
5. **共享 ingress 平台(relay)单连接 + 打标路由**,不为每个 profile 重复连。

---

## 三、secondary profile 重连(13420–13541)

### 3.1 `_run_secondary_profile_reconnect`(13420–13516)

`while self._running` 循环,每次尝试**从该 profile 当前配置整体重建 adapter**(不复用旧实例):scope 内重读 `load_gateway_config().platforms.get(platform)`,平台被禁用/配置消失即安静退出(13435–13437)——重连循环同时充当"配置变更收敛点"。连接后三重竞态裁决:

`gateway/run.py:13453-13474 @ 863e313`:
```python
                    if success and self._running:
                        profile_map = self._profile_adapters.setdefault(profile_name, {})
                        if platform not in profile_map:
                            profile_map[platform] = adapter
                            self._sync_voice_mode_state_to_adapter(adapter)
                            logger.info(
                                "✓ %s reconnected (profile: %s)",
                                platform.value,
                                profile_name,
                            )
                            return
                        # A newer reconnect already won the slot while this
                        # attempt was awaiting connect; do not replace it.
                        await self._safe_adapter_disconnect(adapter, platform)
                        return

                    # Shutdown can begin while connect() is in flight. Do not
                    # republish a newly connected adapter after the registry has
                    # been drained; release its partial resources instead.
                    if success:
                        await self._safe_adapter_disconnect(adapter, platform)
                        return
```
① 槽位已被更新的重连占了 → 弃own;② connect 期间开始 shutdown(`_running` 已 False)→ 不得向已 drain 的注册表"复活"adapter,释放部分资源;③ 失败且 `has_fatal_error and not fatal_error_retryable` → 永久退出(13477–13481)。CancelledError/普通异常都先断连再处理(13482–13494)。退避 `_reconnect_backoff(attempts)`(run.py:3665)。

`finally` 自清(13507–13516):只有当 `_profile_failed_platforms[profile][platform]` 记录的 task 就是当前 task(或不是 Task)才 pop——防止把**后继重连任务**的登记误删;空 dict 级联清理。

### 3.2 `_schedule_secondary_profile_reconnect`(13518–13541)

守卫:`not self._running or not adapter.fatal_error_retryable` 直接放弃;`(profile, platform)` 已有在飞任务则去重(13529–13530);新任务命名 `secondary-reconnect:<profile>:<platform>` 并纳入 `_background_tasks`(带 `add_done_callback(discard)`),从而受 stop() P9 统一取消、受 §1.5 P1 的 `_cancel_secondary_profile_reconnect_tasks` 有界等待(run.py:12603–12633:先 cancel 再以 adapter 断连预算 `asyncio.wait`,等不完也没关系——"the stopped runner state still prevents it from installing an adapter when it eventually resumes",12609–12610)。

### 3.3 重实现要点(重连)

1. **重连 = 重建**:每次尝试从头读配置、造新 adapter,天然吸收配置变更且不背旧实例的脏状态。
2. **发布点单一且带条件**:只有"仍在运行 + 槽位空"才发布;竞态输家与 shutdown 竞态一律断连弃own。
3. **登记表自清要验身份**:finally 中先确认登记的 task 是自己再删,防误删后继。
4. **可重试性由 adapter 声明**(`fatal_error_retryable`),调度器不猜。

---

## 四、profile fatal error 路由(13543–13585)

`_make_profile_fatal_error_handler`(13543–13550)是闭包工厂,把 `(profile_name, platform)` 绑进 handler。`_handle_profile_adapter_fatal_error`(13552–13585)的问题陈述在 docstring:

`gateway/run.py:13558-13564 @ 863e313`:
```python
        """Remove a failed multiplexed adapter without touching the primary slot.

        Secondary adapters are owned by ``_profile_adapters`` rather than
        ``self.adapters``. The primary-only fatal handler intentionally ignores
        them; without this route, a fatal secondary Discord client stayed live
        forever after its liveness sampler stopped.
        """
```
即:primary 的 fatal handler 只认 `self.adapters`,secondary 出 fatal 曾经无人处理——liveness 采样停了、僵尸客户端永远挂着。处理:**身份校验**(`profile_map.get(platform) is adapter`,is 比较防 stale 实例的迟到错误,13565–13572)→ pop → 断连 → 若仍在运行则 `_schedule_secondary_profile_reconnect`。尾注(13584–13585):"Reconnect is scoped to the profile's own config and secret mapping; never rebuild a secondary adapter with the default profile's credentials." —— 重连绝不许借默认 profile 凭据。

重实现要点:① 每类 adapter 归属唯一注册表,fatal 路由按归属分发;② 错误回调必须 `is` 验身份,stale 实例的回调直接忽略;③ 恢复动作继承出错实体的作用域(profile 凭据),不回落全局。

---

## 五、profile message handler 工厂(13587–13629)

`_make_profile_message_handler`(13587–13613):handler 先给 `event.source.profile` 打标(仅当为空,不覆盖 connector 已打的标),再**整个 handler 包进 profile scope** 后委托共享 `_handle_message`。为什么要包整个 handler 而不是只包 agent 轮?docstring 13589–13593:"Auth runs inside `_handle_message` *before* the agent-turn scope is installed. For secondary profiles under multiplex, wrap the whole handler in `_profile_runtime_scope` so allowlists/tokens from that profile's `.env` are visible to `get_secret` / authz." —— 鉴权发生在 agent 轮作用域安装之前,若不提前包住,secondary profile 的白名单/token 对 authz 不可见。`get_profile_dir` 失败则退化为不包 scope 直接委托(13597–13600、13611)。

`_make_default_profile_message_handler`(13615–13623)与 `_primary_message_handler`(13625–13629):multiplex 开启时 default profile 的 primary adapter 也要从 ingress 起就包 scope(否则进程 env 里可能残留别的 profile 的值);未开启则直接返回裸 `_handle_message`,单 profile 路径零变化。

重实现要点:① 作用域必须覆盖"鉴权→会话→agent"全链路,从 ingress 就包;② 打标只补空不覆盖,让上游 connector 的路由标记优先;③ 单租户路径保持字节级不变(不进 scope)。

---

## 六、凭据独占声明三函数(13631–13710)

- `_adapter_credential_claim`(13631–13639):`(platform, fingerprint)` 元组,fingerprint 为 None 则不参与查重。
- `_adapter_listener_claim`(13641–13661):仅 photon 平台;`("listener", "photon", bind.lower(), port)`。docstring 13645–13649:即便两个 profile 凭据不同,sidecar 也不能共享 bind+port,把端点表示成 claim,让 multiplex 启动在 connect()/disconnect() 有机会扰动第一个 profile 之前就拒掉后来者。
- `_adapter_credential_fingerprint`(13663–13710):按属性名探测链 `token/bot_token/_token/api_token/_bot_token/_project_secret`(`_project_secret` 是 Photon/Spectrum 的项目凭据,注释 13678–13681:纳入它才能防多 profile 为同一账号+端口起竞争 sidecar);找不到再退到 `adapter.config` 子对象的 `token/bot_token`。这个回退有实战教训:

`gateway/run.py:13688-13693 @ 863e313`:
```python
        # Many adapters (e.g. Discord) store the token on their `config`
        # sub-object rather than directly on the adapter. Without this lookup
        # those adapters all return None here, the same-token conflict check
        # is silently skipped, and every profile's adapter for that platform
        # starts polling the same bot token — producing a per-message race
        # for which adapter answers. See test_reads_config_token.
```
最终 `sha256("hermes-mux:" + token)` 取 16 hex(13709–13710):**盐化哈希、永不落原文**,日志安全;None 即放弃该 adapter 的冲突检测(宁漏检不误报,13669–13671)。

重实现要点:① 独占资源统一建模为可哈希元组(凭据、监听端点同一张表);② 指纹必须哈希加盐,专用盐前缀防跨用途碰撞比对;③ 探测链要覆盖"属性在子对象上"的适配器形态,否则静默漏检=逐消息竞速;④ 无凭据可发现时明确放弃检测而非猜测。

---

## 七、`_create_adapter`(13712–13841)

- 先把 runner 级配置注入 `config.extra` 默认值:`group_sessions_per_user`、`thread_sessions_per_user`(13722–13730,`setdefault` 不覆盖平台级显式配置)。
- **插件注册表优先**(13732–13757):`gateway.platform_registry.platform_registry.is_registered` → `create_adapter`。成功则无条件注入反向引用 `adapter.gateway_runner = self`(13738–13745 注释:BasePlatformAdapter 声明了该属性,故对所有平台生效,用于跨平台 admin 告警投递与 `runner._profile_name_for_source` 入站 profile 路由,后者定义在 run.py:24161)。**注册了但创建失败 → 返回 None 不回落内建链**(13747–13754:插件平台没有内建实现,静默回落只会掩盖错误)。注册表查询异常仅 debug,继续走内建。
- 内建 if/elif 链(13759–13841):whatsapp_cloud、signal、weixin、api_server、webhook、msgraph_webhook、bluebubbles、qqbot、yuanbao。模式统一:惰性导入 + `check_*_requirements()` 依赖预检(缺依赖 warning + None,不抛)+ 个别平台配置校验(signal 的 `validate_signal_config`);api_server 与 webhook 两个内建平台也注入 `gateway_runner`(13798、13807)。链尾返回 None(13841)。
- 注:telegram/discord/slack 等主流平台不在内建链——它们在 863e313 已迁到 plugin 注册表(plugins/platforms/…),内建链只剩未迁移平台。

重实现要点:① 注册表优先 + "注册即负责"(创建失败不回落);② 依赖检查在创建期做且只降级不抛,单平台缺依赖不影响其余;③ runner 反向引用统一注入,平台无关能力(告警投递、profile 路由)靠它;④ runner 级默认经 `setdefault` 下发,平台配置可覆盖。

---

## 八、`_make_adapter_auth_check`(13843–13879)

为 adapter 构造平台绑定的鉴权回调。用途(docstring 13849–13855):adapter 拉外部上下文时(如 Slack `conversations.replies`)经 `BasePlatformAdapter._is_sender_authorized` 调它,把**非白名单发言者在 LLM 上下文中标记为 unverified**——这是对共享 thread/频道里第三方间接 prompt 注入的缓解。实现:构造 `SessionSource(platform, chat_id, chat_type 默认 "group", user_id, profile=profile_name)` 委托 `self._is_user_authorized`(gateway/authz_mixin.py:386),保持"平台白名单、群白名单、pairing store、allow-all"整条鉴权链单一事实源(13856–13859);`profile_name` 参数让 secondary adapter 的校验解析到自己 profile 的密钥作用域而非 active profile(13860–13863)。空 user_id 直接 False(13869–13870,fail-closed)。

重实现要点:① 鉴权只有一个入口函数,所有旁路(adapter 内部取数)都构造 Source 走同一入口;② 回调工厂把平台与租户(profile)绑死在闭包里,调用方无法传错;③ 未知发言者标记进模型上下文,是注入缓解而非访问控制的替代。

---

## 九、`_deliver_platform_notice`(13886–13926)

运维/配置类通知的统一投递轨:按 source 找 adapter;Slack 的 ignored channel 直接跳过(13893–13902);读 `config.get_notice_delivery(platform)` 决定 "private"/"public"——private 时先试 `adapter.send_private_notice(chat_id, user_id, content)`(平台私密回执,如 Slack ephemeral),失败或不成功**回落公开 send**(13909–13926)。调用点如 run.py:4896(setup 提示)与 17440。

重实现要点:① 通知投递策略按平台配置化(私密优先、公开兜底);② 忽略名单在投递层再查一次(生产者不必知道);③ 回落必须显式而非异常驱动上抛。

---

## 十、`_resolve_async_delegation_session`(13928–14076)——重点

### 10.1 问题(#55578 / #57498)

异步委托(delegate 工具的后台模式)完成后,完成通知以合成 MessageEvent 注回 gateway,metadata 里带发起时钉住的 `gateway_session_id`(打标处 run.py:22001:`metadata["gateway_session_id"] = parent_session_id`)。消费点在 `_handle_message_with_agent`(run.py:16276)——`gateway/run.py:16307-16317 @ 863e313`:
```python
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
风险:委托可能跑很久,期间路由键(session_key → session_id 的映射)可能因 /new、/resume、压缩轮换(compression rotation:压缩事务结束物理父行、在子行延续同一逻辑对话)而移动。把完成结果注错会话 = 把 A 对话的产物灌进 B 对话(#55578);注不进又丢结果。定调(docstring 13935–13939):跟随压缩谱系,但**绝不让迟到的完成覆盖无关的 /new 或恢复路由;所有权不明一律 fail-closed 丢弃注入**(结果仍留在 delegation 记录里可查,不算数据丢失)。

### 10.2 fail-closed 分支矩阵

1. 无 session DB → 丢(13942–13947,日志明写 "#55578 fail-closed")。
2. 钉住的会话行查不到 → 丢(13959–13965)。
3. 钉住的会话已结束且 `end_reason != "compression"`(如 /new 的显式用户边界)→ 丢,"instead of resurrecting it"(13969–13978)。
4. 压缩谱系:`get_compression_tip(pinned)`(hermes_state.py:5719)找延续尖端;无尖端/尖端=自身 → 丢(13993–13999);尖端行不存在或也已结束 → 丢(14001–14012)。
5. **路由所有权校验**(14014–14043):`gateway/run.py:14014-14033 @ 863e313`:
```python
            route_owns_lineage = session_entry.session_id in {
                pinned_session_id,
                target_session_id,
            }
            if not route_owns_lineage:
                # A long-running delegation may survive multiple compression
                # rotations.  Accept an intermediate stale route only when its
                # own verified compression tip is the same live target.
                try:
                    route_row = await session_db.get_session(session_entry.session_id)
                    route_tip = (
                        await session_db.get_compression_tip(session_entry.session_id)
                        if route_row is not None
                        and route_row.get("ended_at")
                        and route_row.get("end_reason") == "compression"
                        else None
                    )
                except Exception:
                    route_tip = None
                route_owns_lineage = route_tip == target_session_id
```
   三种放行:路由当前指向钉住会话本身、指向尖端、或路由自己也是一段压缩中间态且**它自己验证过的尖端就是同一个活目标**(长委托跨多轮压缩的情形);否则 → 丢(14035–14043)。

### 10.3 绑定:两种原语,CAS 语义

路由与目标一致直接返回(14045–14046)。不一致时(14048–14059):
- 压缩谱系 → `advance_compression_session(session_key, prior, target)`(gateway/session.py:2957–2991):**CAS**——条目当前 session_id 必须仍等于 `expected_session_id` 才推进,期间被 /new 抢先则返 None,调用方 fail-closed;且**不动 SQLite 行生命周期**(压缩事务已拥有该生命周期,这里只修 gateway 的 key→session 持久映射,session.py:2965–2969)。
- 非压缩(钉住会话还活着但路由已指向别处,如用户 /resume 去了别的会话)→ `switch_session(session_key, target)`(session.py:2993 起):像 /resume 一样结束当前行、复用目标 session_id,把路由拉回完成结果的属主会话。
- `switched is None` → 丢(14060–14067);成功打 `#57498` 日志(14069–14075)并返回新 entry,后续整轮 agent 在属主会话上跑。

### 10.4 重实现要点

1. **完成通知必须携带发起时的"钉"**(spawning session id),消费端以钉为准做归属验证,绝不信当前路由。
2. **默认 fail-closed**:归属不能证明就丢注入,同时保证结果在委托记录里可再取——"丢投递"≠"丢数据"。
3. **区分逻辑对话与物理会话行**:压缩轮换是"同一逻辑对话换物理行",用显式 end_reason("compression")+ 尖端指针建谱系,归属验证沿谱系走。
4. **多轮轮换要传递验证**:中间态路由只有当"它自己的尖端 == 已验证目标"才算同谱系,防两个不相干谱系恰好交叉。
5. **绑定用 CAS**:带 expected 值推进,和 /new、并发切换的竞态在存储层裁决,输了就放弃。
6. **压缩绑定不复制会话生命周期副作用**(不 end/reopen 行),与 /resume 型 switch 分成两个原语。

---

## 十一、忙时命令面 Guard 2(14078–14327)——重点

### 11.1 问题与架构(#5057 / #6252 / #10370 / #2170)

agent 正在跑时用户又发了斜杠命令,历史实现是手写的逐命令 if 链,散落两处(adapter 层 + runner 层),漏一个命令就出事故。现在是声明式:每个命令的忙时行为写在 `CommandDef.busy_policy / busy_handler` 上(hermes_cli/commands.py:55–95),两道 Guard 读同一注册表:
- **Guard 1**(gateway/platforms/base.py:5604–5640):adapter 层。`should_bypass_active_session(cmd)` 的命令直接内联分发(不进 pending 队列);其中 `is_interrupt_then_dispatch(cmd)`(busy_policy == "interrupt_then_dispatch",即 /new(别名 /reset)与 /stop,commands.py:106–108、140–141)走专门的 cancel-handoff 路径,串行化"取消在飞任务 + runner 应答 + pending 排水"。base.py:5595–5598 注释交代不这么做的两种事故:命令文本泄漏进对话成为用户消息(/stop、/new),或死锁(/approve、/deny——agent 正阻塞在 Event.wait 等审批)。
- **Guard 2**(run.py:14757–14792,`_handle_message` 内):runner 层兜底。会话运行中时 resolve 命令 → /status、/context 先于门禁直通(用户永远能看状态)→ `_check_slash_access` 门禁(镜像冷路径,防"agent 恰好在忙"绕过权限)→ 任何可识别命令交 `_dispatch_busy_slash_command`;未识别命令与普通文本落到 interrupt/queue 逻辑。

`busy_policy` 三值(commands.py:62–74):`dispatch`(忙时照常跑,或跑 `busy_handler` 命名的忙时变体)、`reject`(拒绝;无 busy_handler 用通用文案,有则用定制文案)、`interrupt_then_dispatch`(先杀当前轮再跑)。默认 **reject**(commands.py:75)——新命令不声明就安全拒绝。不变量测试 tests/hermes_cli/test_busy_policy_invariants.py 用重构前的手写 frozenset 对照注册表,保证迁移无语义漂移。

### 11.2 `_dispatch_busy_slash_command`(14098–14170)

解析顺序(docstring 14103–14114):① `busy_handler` 特表(start/stop/new/queue/steer/egress/goal 七个方法);② handler 名在 `_BUSY_REJECT_TEXT`(14091–14096:model / codex-runtime / moa 三条定制拒绝文案,"wait or /stop first");③ `busy_policy in ("dispatch", "interrupt_then_dispatch")` 查普通 handler 表(status/context/restart/approve/deny/agents/background/kanban/subgoal/heartbeat/yolo/verbose/footer/help/commands/profile/update/version,14137–14156)调常规 handler;④ 表中无 → warning + 落到兜底拒绝。兜底拒绝的动机是三个事故:

`gateway/run.py:14108-14114 @ 863e313`:
```python
          3. Catch-all busy-reject text. Rejecting is required rather than
             falling through to interrupt + discard: commands like /model,
             /reasoning, /voice, /insights, /title, /resume, /retry,
             /undo, /compress, /usage, /reload-mcp, /sethome, /reset (all
             registered as Discord slash commands) would interrupt the
             agent AND get silently discarded by the slash-command safety
             net, producing a zero-char response. See #5057, #6252, #10370.
```
因果:这些命令注册成了 Discord 原生斜杠命令,若落进"interrupt + 当普通文本排队"的老路径,会先打断 agent,再被斜杠命令安全网静默吞掉——用户得到零字符响应,agent 还被白白杀了一轮。

### 11.3 逐命令

- **/start**(14172–14177):Telegram 在 bot 启动/深链时自动发 /start,是平台 ping 不是用户命令——返回 `""`(无帮助转储、无打断、无排队)。commands.py:104–105 的描述就叫 "Acknowledge platform start pings without a reply"。
- **/egress**(14179–14182):纯信息命令,直接返回 `hermes_cli.proxy_cli.format_status_text()`。
- **/stop**(14184–14197):`gateway/run.py:14184-14197 @ 863e313`:
```python
    async def _busy_stop_command(self, event: MessageEvent, quick_key: str, source):
        # /stop must hard-kill the session when an agent is running.
        # A soft interrupt (agent.interrupt()) doesn't help when the agent
        # is truly hung — the executor thread is blocked and never checks
        # _interrupt_requested.  Force-clean _running_agents so the session
        # is unlocked and subsequent messages are processed normally.
        await self._interrupt_and_clear_session(
            quick_key,
            source,
            interrupt_reason=_INTERRUPT_REASON_STOP,
            invalidation_reason="stop_command",
        )
        logger.info("STOP for session %s — agent interrupted, session lock released", quick_key)
        return EphemeralReply(t("gateway.stop.stopped"))
```
  软中断的失效模式:真挂死的 agent 的 executor 线程阻塞着,永远轮询不到 `_interrupt_requested` 标志——必须硬杀 + 强制清 `_running_agents` 解锁会话。`_interrupt_and_clear_session`(run.py:23065)做 `request_hard_interrupt` + run generation 失效(先 bump 再调度收割线程,防误杀替换轮的进程,23089–23098)+ 起线程收割该轮 spawn 的 OS 进程。返回 `EphemeralReply`(gateway/platforms/base.py:2375,str 子类,支持平台按 TTL 自动删除系统回执,不支持 delete_message 的平台静默忽略)。
- **/new(/reset)**(14199–14216,#2170):事故因果:/reset 曾被当普通文本排队,中断完成后 "/reset" 字符串作为用户消息**连同坏掉的历史一起**喂回 agent。修法:先 `_interrupt_and_clear_session`(invalidation_reason="new_command",同时清 adapter pending 队列防旧文本重放),再调 `_handle_reset_command(event)` 正常走重置。
- **/queue**(14218–14256):不打断,FIFO 入队,**每条 /queue 是独立完整的一轮,不合并**(14221–14224 注释,与普通 followup 文本的 merge 行为相对)。媒体保真:带图/文档/回复上下文的 "/queue"(如作为图片 caption)即使无文本也有效,重建 MessageEvent 时完整复制 media_urls/media_types/reply_to_* 五件套/auto_skill/channel_prompt 等字段(14228–14251,"Dropping these fields silently lost the attachment")。入队原语 `_enqueue_fifo`(run.py:7691–7703):adapter `_pending_messages` 单 slot 为主位,占用时溢出到 SessionState 的 `queued_events` 列表;`_queue_depth`(run.py:7736)= slot + overflow,回执报深度。
- **/steer**(14258–14305):与 /queue 的分工在注释里:"Unlike /queue (turn boundary), /steer lands BETWEEN tool-call iterations inside the same agent run, by appending to the last tool result's content. No interrupt, no new user turn, no role-alternation violation."(14260–14263)。底层 `AIAgent.steer(text)`(run_agent.py:3229–3263):线程安全地把文本暂存 `_pending_steer`,agent 循环在当前工具批次结束后**把它拼进最后一个 tool result 的内容**,模型下一次迭代把 steer 当工具输出的一部分读到——绕开了"user 消息必须与 assistant 交替"的角色约束。多次 steer 换行拼接。两个退化路径都落回 /queue 语义:agent 还是 `_AGENT_PENDING_SENTINEL`(占坑未启动,没有可 steer 的对象)→ 入队 + "Agent still starting";agent 缺 steer 方法 → 入队 + "No active agent"。接受后回执带 60 字预览。
- **/goal**(14307–14326):控制动词白名单。`gateway/run.py:14313-14326 @ 863e313`:
```python
        _goal_arg = (event.get_command_args() or "").strip().lower()
        _goal_verb = _goal_arg.split(None, 1)[0] if _goal_arg else ""
        # Exact-match control verbs (unchanged semantics), plus the
        # wait/unwait barrier verbs which take a pid argument and the
        # gate management verb (inspection/mutation of the gate list only —
        # gates run at turn boundary, so editing them mid-run is safe).
        _is_control = (
            not _goal_arg
            or _goal_arg in {"status", "pause", "resume", "clear", "stop", "done", "unwait"}
            or _goal_verb in {"wait", "gate"}
        )
        if _is_control:
            return await self._handle_goal_command(event)
        return "Agent is running — use /goal status / pause / clear / wait mid-run, or /stop before setting a new goal."
```
  设计:检查/暂停/清除/屏障(wait 带 pid 参数所以按首词匹配)/gate 编辑(gate 在轮边界才执行,运行中改列表安全)都放行;**设置新 goal 文本被拒**——否则会让第二条 continuation prompt 和当前轮竞速(14310–14312 注释,与 /model 同款拒绝话术)。

### 11.4 重实现要点(忙时命令面)

1. **忙时行为是命令的声明属性**,不是分发器的 if 链;默认值取最安全的 reject,新命令零声明零风险。
2. **拒绝优于"打断+吞掉"**:识别出的命令绝不允许落进普通文本路径,零字符响应 + 白杀一轮是最差用户体验。
3. **两道 Guard 共享一个注册表**:adapter 层管"必须绕过排队/取消在飞任务"的强命令(防泄漏进对话、防审批死锁),runner 层管其余全部并镜像权限门禁。
4. **三级注入时机**:/stop(立即硬杀)> /steer(工具批次间,寄生在 tool result 里,不破坏角色交替)> /queue(轮边界,独立成轮不合并);steer 不可用时显式降级为 queue 并告知。
5. **硬杀要配套**:中断标志 + run generation 失效 + OS 进程收割 + 强制清运行表,四件缺一会留僵尸或锁死会话。
6. **状态查询永远可用**(/status /context 先于门禁与忙判定)。

---

## 十二、调用关系汇总

| 本段成员 | 调用/被调 | 对方位置 |
|---|---|---|
| `stop()` | 被 restart 编排、信号处理、CLI stop 调;内调 `_drain_active_agents`/`_interrupt_running_agents`/`_notify_active_sessions_of_shutdown`/`_finalize_shutdown_agents`/`_cleanup_agent_resources_off_loop`/`_increment_restart_failure_counts`/`_launch_detached_restart_command`/`_launch_systemd_restart_shortcut` | run.py:9184/9243/9253/9452/9596/9698/9795/9982 |
| `stop()` 外部依赖 | `process_registry.kill_all`;`mark_running_jobs_interrupted`;`async_delegation.interrupt_all`;`flush_pending_to_file`;`shutdown_cached_clients`;`arm_shutdown_watchdog`/`resolve_shutdown_watchdog_delay`;`remove_pid_file`/`release_gateway_runtime_lock`;`GATEWAY_SERVICE_RESTART_EXIT_CODE` | tools/process_registry.py;cron/scheduler.py:366;tools/async_delegation.py;gateway/shutdown_flush.py:82;agent/auxiliary_client.py;gateway/shutdown_watchdog.py:337/274;gateway/status.py;gateway/restart.py:10 |
| `mark_resume_pending`/`clear_resume_pending` | AsyncSessionStore → SessionStore | gateway/session.py:2751/2780 |
| `_start_secondary_profile_adapters` | 由启动序列调(run.py:11227);内调 `profiles_to_serve`/`get_active_profile_name`、`PairingStore`、`write_runtime_status` | hermes_cli/profiles.py:957;gateway/pairing.py;gateway/status.py |
| `_start_one_profile_adapters` | `_profile_runtime_scope`(run.py:1938)、`load_gateway_config`、`_own_policy_open_startup_violation`(run.py:2428)、`_platform_binds_port`(gateway/config.py,经 run.py:1918–1921 导入)、`_create_adapter`、`_connect_initial_adapter_with_timeout`(run.py:6647)、`_safe_adapter_disconnect`(run.py:6496) | 见左 |
| `_configure_profile_adapter` | `set_message_handler/set_fatal_error_handler/set_busy_session_handler/...` | gateway/platforms/base.py(set_busy_session_handler:3345) |
| `_run_secondary_profile_reconnect` | `get_profile_dir`(hermes_cli/profiles.py:370)、`_connect_adapter_with_timeout`(run.py:6609)、`_reconnect_backoff`(run.py:3665)、`_sync_voice_mode_state_to_adapter`(run.py:6423) | 见左 |
| `_handle_profile_adapter_fatal_error` | 由 adapter fatal 回调触发(base.py 的 fatal_error_handler 机制) | gateway/platforms/base.py |
| `_make_adapter_auth_check` | 被 11101/12473(primary)与 13415(secondary)安装;回调进 `BasePlatformAdapter._is_sender_authorized`;委托 `_is_user_authorized` | gateway/authz_mixin.py:386 |
| `_create_adapter` | `platform_registry.create_adapter`;各内建 adapter 模块 | gateway/platform_registry.py;gateway/platforms/*.py |
| `_resolve_async_delegation_session` | 唯一调用点 `_handle_message_with_agent`(run.py:16311);钉打标于 run.py:22001;前置分类 `_classify_completion_target`(run.py:22043);内调 `get_session`/`get_compression_tip`(hermes_state.py:5719)、`advance_compression_session`/`switch_session`(gateway/session.py:2957/2993) | 见左 |
| `_dispatch_busy_slash_command` | 唯一调用点 run.py:14790(`_handle_message` 忙路径);Guard 1 对照 base.py:5604–5640;命令声明 hermes_cli/commands.py:102 起 | 见左 |
| `_busy_stop/_busy_new` | `_interrupt_and_clear_session`(run.py:23065)、`_handle_reset_command` | run.py |
| `_busy_queue/_busy_steer` | `_enqueue_fifo`(run.py:7691)、`_queue_depth`(run.py:7736)、`AIAgent.steer` | run_agent.py:3229 |

---

## 十三、文档-代码冲突候选

1. **▲ multiplex 文档"startup fails fast"vs 代码"跳过重复者继续"**。website/docs/user-guide/multi-profile-gateways.md:188–190:"If two profiles configure the same `(platform, token)`, startup fails fast naming both profiles";同文 474–476 称 "the second gateway refuses to start with an error"。而 multiplexer 内的同凭据冲突(run.py:13336–13351)是 **log error + continue**:只拒绝重复的那个 adapter,该 profile 的其余平台与其余 profile 照常启动,gateway 整体不退。文档的 "fails fast/refuses to start" 更贴近**两个独立 gateway 进程**的旧式 token 冲突检查;对 multiplex 内冲突,代码语义是"拒重复、不失败"。以代码为准。
2. **◇ `busy_policy="interrupt_then_dispatch"` 在 Guard 2 普通表分支不打断**。commands.py:70–74 说该策略"interrupt/kill the running agent first, then dispatch";run.py:14136 的 `if policy in ("dispatch", "interrupt_then_dispatch")` 若命中普通 handler 表会**直接 dispatch 而不打断**。当前注册表中该策略仅 /new 与 /stop,两者都有 busy_handler,总在 ① 特表被截获(特表内自行打断),普通表分支实际不可达;真正到达 14159 的只会打 warning 落兜底拒绝。属"防御分支与文档措辞不一致",非现网行为错误(不变量测试守着注册表)。
3. **◇ 14111 注释把 `/reset` 列进"会被打断+吞掉"的例子**。/reset 是 /new 的别名(commands.py:107),busy_policy=interrupt_then_dispatch + busy_handler="new",如今在 Guard 1/特表正确处理;注释列举的是**历史事故清单**(#5057 等修复前的状态),读代码时不应据此推断现行为。
4. **◇ `stop()` docstring(12666)"Stop the gateway and disconnect all adapters"** 严重轻描淡写:实际还承担 restart 编排、退出码协议、状态持久化、数据落盘等十余职责。仅记为文档不充分,不算冲突。

---

## 十四、覆盖自查

12659–13175 stop()(§1);13176–13178 wait_for_shutdown(§1.6);13180–13266 / 13268–13396 / 13398–13418 multiplex 三件套(§2);13420–13516 / 13518–13541 重连(§3);13543–13585 fatal 路由(§4);13587–13629 handler 工厂(§5);13631–13710 凭据声明(§6);13712–13841 _create_adapter(§7);13843–13879 auth check(§8);13880–13885 空行;13886–13926 平台通知(§9);13928–14076 异步委托绑定(§10);14078–14327 忙时命令面(§11);14328 起属下一段。无遗漏。
