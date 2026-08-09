# r7c-raw-cron-sched-b · scheduler.py 后半 + scheduler_provider.py + lifecycle_guard.py

> 基线 `863e31318553cda8ad61df681d08175364d4164b`。凡断言均给 `路径:行号 @ 863e313` + 代码原文。
> 切片:`cron/scheduler.py:2200-4428`(到文件尾)、`cron/scheduler_provider.py`(全 357 行)、
> `cron/lifecycle_guard.py`(全 565 行)。
> 为回答"结果投递"问题,额外精读了 `cron/scheduler.py:1100-2110`(投递目标解析 + `_deliver_result`),
> 该区间归属 r7b 切片,本底稿只在投递语义必需处引用,不做逐行复述。

---

## 0. 本切片一句话

**scheduler.py 后半是"一次 cron 触发"的全部实体:`tick` 只做"选中 + 抢占 + 派发",
`run_one_job` 做"执行→存盘→投递→记账"的定序,`run_job` 做"造一个一次性 agent 并跑一个回合";
`scheduler_provider.py` 把"何时触发"抽象成可换的 Axis-B provider(进程内 60s ticker vs. Chronos 托管);
`lifecycle_guard.py` 只守一件事——不让 cron 作业在网关进程里执行"重启/停止网关"这类命令,
避免 launchd/systemd KeepAlive 下的 SIGTERM-重生死循环。**

---

## 1. 结构总览

### 1.1 三个文件的调用关系

```
gateway/run.py::start_gateway
   └─ resolve_cron_scheduler()                       [scheduler_provider.py:122]
        ├─ (默认) InProcessCronScheduler              [scheduler_provider.py:162]
        │     └─ .start()  60s 循环                   [scheduler_provider.py:176 / 263 多 profile]
        │           └─ cron.scheduler.tick(sync=False)          [scheduler.py:4151]
        │                 └─ _submit_with_guard → 线程池        [scheduler.py:4272]
        │                       └─ run_one_job                  [scheduler.py:3930]
        │                             ├─ run_job                [scheduler.py:2779]
        │                             │     ├─ _run_job_script_with_claim_heartbeat [2367]
        │                             │     │     └─ _run_job_script                [2210]
        │                             │     ├─ _parse_wake_gate                     [2432]
        │                             │     ├─ _build_job_prompt                    [2458]
        │                             │     │     └─ _scan_assembled_cron_prompt    [2663]
        │                             │     ├─ _guard_job_credential_exfil          [2733]
        │                             │     └─ AIAgent.run_conversation             [3618]
        │                             ├─ save_job_output                     [4020]
        │                             ├─ _deliver_result                     [1467]
        │                             ├─ _teardown_cron_agent                [3905]
        │                             ├─ mark_job_run / finish_execution     [4082/4092]
        │                             └─ (完)
        └─ (cron.provider=chronos) ChronosCronScheduler          [plugins/cron_providers/chronos/__init__.py:47]
              ├─ .start() 只 arm 一次然后 return(不轮询)        [chronos:103]
              └─ NAS → POST /api/cron/fire → provider.fire_due   [api_server.py:5642 / scheduler_provider.py:91]
                    └─ claim_job_for_fire + run_one_job          [scheduler_provider.py:107-113]

cron/jobs.py::create_job
   └─ check_gateway_lifecycle(prompt, script)          [cron/jobs.py:1365-1366 → lifecycle_guard.py:516]

tools/terminal_tool.py(_HERMES_GATEWAY=1 时)
   └─ contains_launchctl_submit_command                [terminal_tool.py:2510 → lifecycle_guard.py:155]
   └─ contains_gateway_lifecycle_command_or_referenced_script
                                                       [terminal_tool.py:2586 → lifecycle_guard.py:424]
```

要点:**`lifecycle_guard.py` 与 `scheduler.py` 之间没有直接调用**。guard 只在
`cron/jobs.py::create_job` 这一个 cron 侧入口被调,以及在 `tools/terminal_tool.py` 被复用。
`scheduler.py` 唯一提到它的地方是一句注释(说明二者的"路径摄取契约"一致):

`cron/scheduler.py:2256-2263 @ 863e313`
```python
    except (ValueError, RuntimeError, OSError):
        # Same ingestion contract as cron.lifecycle_guard: a NUL-bearing
        # value (ValueError) or an unexpandable ``~`` (RuntimeError with no
        # resolvable HOME) can never name a real script. The creation-time
        # guard tolerates such values as "nothing to scan", so they can
        # reach fire time — fail the run with a report instead of crashing
        # the scheduler with an unhandled exception.
        return False, f"Blocked: script path is not a valid filesystem path: {script_path!r}"
```

### 1.2 scheduler.py 后半的函数清单(含行号)

| 行 | 符号 | 职责 |
|---|---|---|
| 2113-2116 | `_DEFAULT_SCRIPT_TIMEOUT` / `_SCRIPT_TIMEOUT` / `_RUN_CLAIM_HEARTBEAT_SECONDS` | 3600s / 可 monkeypatch 覆盖 / 60.0s |
| 2119 | `_get_script_timeout` | 模块覆盖 → env → config → 默认 |
| 2152/2168 | `_read_windows_pyvenv_cfg` / `_windows_cron_python_invocation` | Windows/uv venv 解释器修正 |
| 2210 | `_run_job_script` | 脚本沙箱执行(路径监牢 + 解释器选择 + 环境净化 + 脱敏) |
| 2367 | `_run_job_script_with_claim_heartbeat` | 长脚本期间续租 one-shot 抢占 |
| 2432 | `_parse_wake_gate` | 解析 `{"wakeAgent": false}` 唤醒闸门 |
| 2458 | `_build_job_prompt` | 组装最终 prompt(脚本输出/上游作业输出/cron 提示/skill) |
| 2663 | `_scan_assembled_cron_prompt` | 组装后 prompt 的注入扫描(双档) |
| 2733 | `_guard_job_credential_exfil` | 运行期 provider/base_url 凭据外泄兜底 |
| 2779 | `run_job` | 跑一个作业的 agent 回合,返回 `(success, doc, final_response, error)` |
| 3905 | `_teardown_cron_agent` | 拆一次性 agent 的异步资源 |
| 3930 | `run_one_job` | 执行→存盘→投递→记账的共享定序体 |
| 4133 | `_notify_provider_jobs_changed` | 作业集变更后通知 provider |
| 4151 | `tick` | 文件锁 + 选中 + 前推 next_run + 分池派发 |
| 4427 | `__main__` | `tick(verbose=True)` |

---

## 2. 一次触发的完整走法(端到端)

下面按"到点 → agent 回合结束 → 结果投递"逐段追。

### 2.1 到点:`tick()` 选中并派发

**① 抢单一 tick 的跨进程文件锁。**

`cron/scheduler.py:4175-4190 @ 863e313`
```python
    lock_dir, lock_file = _get_lock_paths()
    lock_dir.mkdir(parents=True, exist_ok=True)

    # Cross-platform file locking: fcntl on Unix, msvcrt on Windows
    lock_fd = None
    try:
        lock_fd = open(lock_file, "w", encoding="utf-8")
        if fcntl:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif msvcrt:
            msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
    except (OSError, IOError):
        logger.debug("Tick skipped — another instance holds the lock")
        if lock_fd is not None:
            lock_fd.close()
        return 0
```
非阻塞独占锁,抢不到直接 `return 0`。锁在 `finally`(4413-4424)释放。

**② 排水闸门。** 网关正在 drain 时不派发,due 作业留给下一个允许的 tick:

`cron/scheduler.py:4193-4195 @ 863e313`
```python
        if can_dispatch is not None and not can_dispatch():
            logger.debug("Cron dispatch paused while gateway drains existing work")
            return 0
```
`can_dispatch` 由 `gateway/run.py:26910-26913` 注入,**仅对内置 provider 注入**:
```python
    if isinstance(cron_provider, InProcessCronScheduler):
        cron_start_kwargs["can_dispatch"] = lambda: not (
            runner._draining or runner._external_drain_active
        )
```

**③ 空转 tick 的短路。** 没有 due 作业时不加载 config、不做分池,但仍扫 MCP 孤儿进程:

`cron/scheduler.py:4199-4213 @ 863e313`
```python
        if not due_jobs:
            # Idle tick: skip config load + pool partitioning entirely
            # (#33612 — the gateway ticker calls tick(verbose=False) every
            # 60s, so idle ticks previously fell through to load_config()).
            # Still run the post-tick MCP orphan sweep: main intentionally
            # sweeps on idle ticks so orphaned stdio children from crashed
            # jobs are reaped even when nothing is due.
            if verbose:
                logger.info("%s - No jobs due", _hermes_now().strftime('%H:%M:%S'))
            try:
                from tools.mcp_tool import _kill_orphaned_mcp_children
                _kill_orphaned_mcp_children()
            except Exception as _e:
                logger.debug("Post-tick MCP orphan cleanup failed: %s", _e)
            return 0
```

**④ 执行前先把 `next_run_at` 推到下一次。** 这是 at-most-once 的关键:

`cron/scheduler.py:4218-4224 @ 863e313`
```python
        # Advance next_run_at for all recurring jobs FIRST, under the file lock,
        # before any execution begins.  This preserves at-most-once semantics.
        # For parallel jobs that are already running, the advance keeps
        # bumping next_run_at forward so the grace window never expires.
        # mark_job_run() overwrites next_run_at on completion.
        # Batched: one load + one save for the whole due set, not one per job.
        advance_next_runs([job["id"] for job in due_jobs])
```

**⑤ 并发上限。** `HERMES_CRON_MAX_PARALLEL` > `config.yaml cron.max_parallel_jobs` > 无上限
(`scheduler.py:4228-4244`)。

**⑥ 分池。** 带 `workdir` 的作业进单线程顺序池,其余进并行池:

`cron/scheduler.py:4260-4267 @ 863e313`
```python
        # Partition due jobs: those with a per-job workdir mutate
        # os.environ["TERMINAL_CWD"] inside run_job, which is process-global, so
        # they queue on the single-thread sequential pool to run one at a time.
        # That alone only keeps workdir jobs from overlapping EACH OTHER;
        # run_job's _terminal_cwd_lock is what additionally stops a concurrently
        # firing workdir-less parallel-pool job from observing the override.
        sequential_jobs = [j for j in due_jobs if (j.get("workdir") or "").strip()]
        parallel_jobs = [j for j in due_jobs if not (j.get("workdir") or "").strip()]
```
这是**双层互斥**:顺序池管 workdir 作业之间,`_terminal_cwd_lock`(读写锁,
`scheduler.py:440`,在 `run_job:3128-3132` 取)管 workdir 作业 vs. 无 workdir 作业。

**⑦ 派发守卫 `_submit_with_guard`(4272-4332)。** 三道:

- 解释器已在收尾 → 跳过不报错(`4285-4290`),作业留在 due,下一个健康 tick 再来:
  `# (#58720, #55924)`
- 同 job_id 上一次还在飞 → 跳过(`4291-4295`):
  ```python
            with _running_lock:
                if job_id in _running_job_ids:
                    logger.info("Job '%s' already running — skipping", job.get("name", job_id))
                    return None
                _running_job_ids.add(job_id)
  ```
- 派发前先落一条 execution 记录(`4296-4299`):
  ```python
            # Record the attempt before executor dispatch. Recovery classifies
            # abandoned records as unknown; it never automatically retries them.
            execution = create_execution(job_id, source="builtin")
            dispatched_job = dict(job, execution_id=execution["id"])
  ```
  并用 `contextvars.copy_context()`(4300)把调度器上下文带进工作线程,
  `finally` 里把 job_id 从 `_running_job_ids` 摘掉(4305-4307)。

**⑧ 同步 vs 异步。** `sync=True`(测试/手工 tick)会 `as_completed` 等全部结束
(`4380-4387`),**此时文件锁仍握着**;`sync=False`(网关 ticker,见
`scheduler_provider.py:231-237`)立即返回,靠最后一个 future 的 done-callback 扫 MCP 孤儿
(`4392-4407`)。

### 2.2 `run_one_job`:执行→存盘→投递→记账(3930-4130)

这是**内置 ticker 与外部 provider 共用的唯一定序体**:

`cron/scheduler.py:3931-3944 @ 863e313`
```python
    """Run ONE due job end-to-end: execute → save output → deliver → mark.

    This is the shared firing body extracted from ``tick``'s per-job closure so
    that BOTH the built-in ticker and an external provider's ``fire_due`` (e.g.
    Chronos) run the identical sequence — no duplicated correctness.

    It does NOT decide whether the job is due, claim it, or compute the next
    run — those are the caller's concern (``tick`` advances ``next_run_at``
    under the file lock before dispatch; an external provider claims via the
    store CAS). This function only fires the given job once.
```

**a) 一次性作业的派发抢占(#38758)。** 在副作用发生前把"这次派发"落盘,
防止执行中途进程被杀后重启无限重放:

`cron/scheduler.py:3949-3970 @ 863e313`
```python
        # Pre-run dispatch claim (issue #38758): atomically commit a finite
        # one-shot's dispatch BEFORE its side effect runs, so a tick that dies
        # mid-execution (gateway kill, OOM, segfault, hard-timeout) cannot
        # re-fire the job forever on restart. No-op for recurring jobs (they
        # use advance_next_run) and infinite/no-repeat jobs. This lives here in
        # the shared body so BOTH the built-in ticker and the external provider
        # (Chronos fire_due) get at-most-times semantics.
        if not claim_dispatch(job["id"]):
            ...
            return True  # not an error — already handled/removed

        # The attempt is claimed durably before executor/provider dispatch and
        # becomes running only immediately before the actual run.
        mark_execution_running(execution_id)
```

**b) profile 秘密作用域。** ticker 线程没有 per-turn scope,不装就 `UnscopedSecretError`:

`cron/scheduler.py:3972-3987 @ 863e313`
```python
        # Run the job under the profile's secret scope. get_secret() fails
        # closed outside a scope once profile isolation is in play (multiple
        # gateway profiles / room→profile multiplexing), and cron fires from
        # the ticker thread where no per-turn scope is installed — so
        # resolve_runtime_provider() raised UnscopedSecretError before model
        # selection, breaking every cron job. Mirrors the per-turn pattern in
        # gateway/run.py (_profile_runtime_scope).
        from agent.secret_scope import (
            build_profile_secret_scope,
            reset_secret_scope,
            set_secret_scope,
        )

        _scope_token = set_secret_scope(
            build_profile_secret_scope(_get_hermes_home())
        )
```

**c) 延迟 agent 拆解(#58720)。** `run_job` 平时在 `finally` 里 `agent.close()`,
但投递必须在**活的**异步客户端上跑,于是把 agent 交回给调用方,投递完再拆:

`cron/scheduler.py:3988-3999 @ 863e313`
```python
        # Defer the cron agent's async-resource teardown until AFTER delivery.
        # run_job normally closes the agent (and reaps stale async clients) in
        # its finally block; doing that before _deliver_result runs means the
        # live send races a torn-down async client (#58720). Passing a holder
        # list makes run_job hand the agent back instead, and we tear it down
        # below once delivery is done. Defense-in-depth alongside the
        # interpreter-shutdown guard in _deliver_result.
        _deferred_agents: list = []
        try:
            success, output, final_response, error = run_job(
                job, defer_agent_teardown=_deferred_agents
            )
```
`except BaseException:`(4000-4008)保证抛异常时也拆(含 `KeyboardInterrupt`/`SystemExit`)。

**d) 存盘先于投递。** `save_job_output(job["id"], output)`(4020)——**注意:与
`deliver` 取值无关,所有作业都会存盘**。

**e) 关机中断校正(#60432)。**
`cron/scheduler.py:4024-4036 @ 863e313`
```python
            # If the gateway shutdown killed this job's tool subprocess
            # mid-flight (#60432), the agent may still have produced a
            # plausible-looking final_response from the truncated output --
            # force the failure path so the delivered message is an honest
            # "this run was interrupted" summary instead of that response.
            # Peek-only: the flag stays set for the authoritative check
            # right before mark_job_run below.
            if success and _is_interrupted(job["id"]):
                success = False
                error = (
                    "Interrupted by gateway shutdown before the run finished "
                    "(tool subprocess was killed mid-flight)."
                )
```

**f) 记账。** `mark_job_run`(4082,若中断标志已被 `_consume_interrupted_flag` 消费则跳过)
+ `finish_execution`(4092-4097,带 `delivery_outcome`)。软失败规则:

`cron/scheduler.py:4074-4079 @ 863e313`
```python
        # Treat empty final_response as a soft failure so last_status
        # is not "ok" — the agent ran but produced nothing useful.
        # (issue #8585)
        if success and not final_response.strip():
            success = False
            error = "Agent completed but produced empty response (model error, timeout, or misconfiguration)"
```

**g) 顶层 `except BaseException`(#73973)。**
`cron/scheduler.py:4100-4109 @ 863e313`
```python
    except BaseException as e:  # noqa: BLE001 — deliberate: see below
        # BaseException, not Exception (#73973): the inner run_job handler
        # re-raises CancelledError / KeyboardInterrupt / SystemExit after agent
        # teardown, and none of those are Exception subclasses. If they escape
        # without mark_job_run(False), a finite one-shot is left wedged —
        # claim_dispatch() already consumed repeat.completed, but last_run_at
        # is never written, so the job sits in state "scheduled" until the
        # run-claim TTL expires and the dispatch-limit guard removes it with
        # no output and no error. Record the failure first, then re-raise
        # anything that isn't a plain Exception.
```

### 2.3 `run_job`:一个 cron 作业的 agent 回合(2779-3902)

#### 2.3.1 `no_agent` 短路(2819-2903)——脚本即作业

`cron/scheduler.py:2801-2818 @ 863e313`
```python
    # ---------------------------------------------------------------
    # no_agent short-circuit — the script IS the job, no LLM involvement.
    # ---------------------------------------------------------------
    # This mirrors the classic "run a bash script on a timer, send its
    # stdout to telegram" watchdog pattern. The agent path is skipped
    # entirely: no AIAgent, no prompt, no tool loop, no token spend.
    #
    # We check this BEFORE importing run_agent / constructing SessionDB so
    # a pure-script tick never pays for the agent machinery it isn't going
    # to use. Keep this block self-contained.
    #
    # Semantics:
    #   - script stdout (trimmed) → delivered verbatim as the final message
    #   - empty stdout            → silent run (no delivery, success=True)
    #   - non-zero exit / timeout → delivered as an error alert, success=False
    #   - wakeAgent=false gate    → treated like empty stdout (silent), since
    #                               the whole point of no_agent is that there
    #                               is no agent to wake
```
四条语义分别落在 2850-2867(失败告警)、2871-2882(wakeAgent=false 静默)、
2884-2893(空输出静默)、2895-2903(正常投递)。静默是靠返回
`SILENT_MARKER`(`scheduler.py:297 = "[SILENT]"`)实现的,由 `run_one_job:4053` 拦截。

`no_agent` 是**唯一把 `workdir` 传给脚本 cwd 的路径**(2830-2841)。

#### 2.3.2 SessionDB 带超时初始化(2926-2978)

这段注释把"为什么要给一个 SQLite 连接单独加超时"讲得很完整:

`cron/scheduler.py:2916-2925 @ 863e313`
```python
    # Bounded with its own timeout (separate from HERMES_CRON_TIMEOUT, which
    # only watches the agent's run_conversation below): SessionDB.__init__
    # opens/migrates state.db synchronously and has no timeout of its own
    # against a wedged sqlite3.connect (e.g. a stale flock left by a crashed
    # sibling process). An unbounded hang here is invisible to every other
    # cron safeguard, because it happens BEFORE _submit_with_guard's future
    # exists — the finally block that releases the job from
    # _running_job_ids never runs, so the job stays wedged "running" until
    # the whole gateway process is restarted, silently skipping every
    # scheduled fire in between with "already running — skipping".
```
解析链:`HERMES_CRON_SESSION_DB_TIMEOUT`(2933)→ `cron.session_db_timeout_seconds`(2947)
→ 默认 `10.0`(2956);`0` = 无限(2967-2969)。超时后**不等**卡死的线程,
`_session_db_pool.shutdown(wait=False)`(2966),这次 run 无 session store 继续跑(2970-2976)。

#### 2.3.3 唤醒闸门(2984-3000)

脚本在**建 prompt 之前**跑一次,`{"wakeAgent": false}` 直接静默返回,不进 LLM:

`cron/scheduler.py:2984-2989 @ 863e313`
```python
    prerun_script = None
    script_path = job.get("script")
    if script_path:
        prerun_script = _run_job_script_with_claim_heartbeat(job, script_path)
        _ran_ok, _script_output = prerun_script
        if _ran_ok and not _parse_wake_gate(_script_output):
```
`_parse_wake_gate`(2432-2455)只看 **stdout 最后一个非空行**是否是
`{"wakeAgent": false}`,其它一切(非 JSON / 缺字段 / true)都唤醒。来源标注为
`nanoclaw #1232`(2436)。

#### 2.3.4 ContextVar 隔离(3039-3100)——本切片设计密度最高的一段

`cron/scheduler.py:3041-3061 @ 863e313`
```python
    # Cron execution is an internal scheduler context, not a live inbound
    # gateway message. Do not seed HERMES_SESSION_* contextvars from the
    # stored ``origin`` (which is delivery routing metadata, not a sender
    # identity). Several tool consumers branch on these vars during job
    # execution and would otherwise behave as if a real user from the
    # origin chat was driving the agent:
    #   - tools/terminal_tool.py: background-process notification routing
    #     (notify_on_complete / watch_patterns) reads HERMES_SESSION_PLATFORM
    #     and HERMES_SESSION_CHAT_ID to populate watcher_platform / chat_id,
    #     which would route completion notifications to the origin chat
    #     instead of via HERMES_CRON_AUTO_DELIVER_* below.
    #   - tools/tts_tool.py: picks Opus vs MP3 based on
    #     HERMES_SESSION_PLATFORM == "telegram".
    #   - tools/skills_tool.py + agent/prompt_builder.py: per-platform
    #     skill-disable lists and the system-prompt cache key both consume
    #     HERMES_SESSION_PLATFORM.
    #   - tools/send_message_tool.py: mirror source labelling and the
    #     send_message gate read HERMES_SESSION_PLATFORM.
    # Cron output delivery itself reads job["origin"] directly via
    # _resolve_origin(job) and the HERMES_CRON_AUTO_DELIVER_* vars set
    # below, so clearing HERMES_SESSION_* here does not affect delivery.
```

`async_delivery=False`(3091)的理由:

`cron/scheduler.py:3078-3090 @ 863e313`
```python
        # A cron job cannot receive a completion after its turn ends. We clear the
        # HERMES_SESSION_* routing keys just below, so an async delegation's
        # completion event carries session_key="" — _enrich_async_delegation_routing
        # cannot resolve it and _inject_watch_notification drops it ("no routing
        # metadata"). And by the time a child finishes, run_job has already shipped
        # the job's final response via _deliver_result; there is no turn left to
        # re-enter. (Worse, get_current_session_key() can fall back to the ambient
        # os.environ HERMES_SESSION_KEY, which risks routing a cron subagent's output
        # into an unrelated user chat.)
        #
        # Declaring the channel stateless routes delegate_task to its existing
        # inline/synchronous path, so results return within the job's own turn.
        # See declare_stateless_channel(). Upstream: #53027, #63142.
```

另外三个隔离动作:
- `HERMES_CRON_SESSION = "1"`(3147),把 cron 审批策略作用域限制到本次 run;
- `enter_non_dispatcher_owned_context()`(3167),防止 cron agent 被误认成 kanban worker
  (注释 3149-3166 详述:否则 `kanban_complete` 会默认拿 `$HERMES_KANBAN_TASK`,
  让一个无关 cron 作业关掉 worker 的任务并覆盖真实结果);
- `TERMINAL_CWD` 进程级 env 的读写锁(3126-3132 取,3799-3809 释放)。

#### 2.3.5 每次 run 都重读 .env / config(3172-3189)

`cron/scheduler.py:3172-3189 @ 863e313`
```python
        # Re-read .env and config.yaml fresh every run so provider/key
        # changes take effect without a gateway restart. Route through
        # load_hermes_dotenv (not a bare load_dotenv) and reset the secret-
        # source cache first: startup already applied external secrets and
        # recorded this HERMES_HOME in _APPLIED_HOMES, so a naive reload would
        # re-apply only the .env placeholder and never re-resolve a Bitwarden/
        # BSM-backed secret — leaving cron jobs 401'ing on the placeholder
        # (#33465). Clearing the cache forces the re-pull; the resolved secret
        # overrides the placeholder only when secrets.bitwarden.override_existing
        # is set (mirrors startup), and the Bitwarden value-cache keeps the
        # forced re-pull off the network. load_hermes_dotenv also handles the
        # utf-8/latin-1 encoding fallback internally.
        from hermes_cli.env_loader import (
            load_hermes_dotenv,
            reset_secret_source_cache,
        )
        reset_secret_source_cache()
        load_hermes_dotenv(hermes_home=_get_hermes_home())
```

#### 2.3.6 模型/provider 解析与两道钱包保险

**模型优先级**(3201-3257):per-job `model` > `HERMES_MODEL` > `cron.model`(cron 舰队默认)
> `config.yaml model.default`。注意 3245-3249 的实际次序是:job 没 pin 时 `cron.model` **压过**
`config.yaml model`,但不压过 env `HERMES_MODEL`(3207 先赋值,3245 的 `if not job.get("model")`
分支会覆盖它)。**这与 3201-3204 的注释描述次序不完全一致**(见 §6 ◇-7)。

无模型直接抛(3263-3272,#23979)。

**保险一:凭据外泄兜底(F8,`_guard_job_credential_exfil`,2733-2776,调用点 3329)。**
`fail closed` 的边界很讲究:

`cron/scheduler.py:2752-2769 @ 863e313`
```python
        # Fail CLOSED: this is the last guard before provider resolution, so an
        # unexpected validator/import error must not silently allow an unvetted
        # pair through. A job that carries no base_url override cannot exfiltrate
        # a stored credential via this path (there is nothing to validate, and
        # the validator would return None), so it still runs — that keeps the
        # overwhelmingly-common no-override jobs from wedging on an unrelated
        # error. But any job that DID set a base_url is refused until the
        # validator can actually vet the pair. Operator fallback providers come
        # from config, not the job, so they are unaffected.
        if job.get("base_url"):
            err = (
                f"could not validate provider/base_url pair "
                f"({exc.__class__.__name__}: {exc}); refusing to run a job with "
                "an unverified base_url override"
            )
        else:
            err = None
    if err:
```

**保险二:模型/provider 漂移守卫(#44585,3417-3484)。**

`cron/scheduler.py:3417-3431 @ 863e313`
```python
        # Provider/model-drift fail-closed guard (#44585).
        #
        # An UNPINNED job (no explicit job["provider"]/["model"]) follows the
        # global default, which can change after the job was created — a switch
        # to a paid PROVIDER (e.g. nous) OR a paid MODEL on the same provider
        # (e.g. claude-fable-5 on openrouter). Without a guard the job would
        # silently inherit that change and spend real money on every tick — the
        # $7.73 incident named BOTH a provider and a model.
        #
        # create_job() snapshots whatever resolution would have picked at
        # creation for each unpinned axis (job["provider_snapshot"] /
        # job["model_snapshot"]). Here, for each axis that (a) has a snapshot and
        # (b) is unpinned and (c) currently resolves to a DIFFERENT value, we
        # fail closed: skip this run, make NO paid call, and deliver a loud,
        # actionable alert telling the user to pin the axis explicitly.
```
显式设了 `cron.model` / `cron.model_provider` 的轴不算漂移(3437-3439 + 3446/3459 的条件)。

**auth 失败的 fallback 是"provider+model 成对换"**,不是只换 provider:

`cron/scheduler.py:3366-3369 @ 863e313`
```python
        except AuthError as auth_exc:
            # Primary provider auth failed — try each configured provider/model
            # pair atomically. Keeping the primary model while changing only the
            # provider can silently route a paid GPT model through OpenRouter.
```

#### 2.3.7 AIAgent 构造(3525-3557)

关键参数:
```python
            quiet_mode=True,                                    # 3546
            skip_context_files=not bool(_job_workdir),          # 3551
            load_soul_identity=True,                            # 3552
            skip_memory=True,  # Cron system prompts would corrupt user representations   # 3553
            platform="cron",                                    # 3554
            session_id=_cron_session_id,                        # 3555
            enabled_toolsets=_resolve_cron_enabled_toolsets(job, _cfg),   # 3544
            disabled_toolsets=_resolve_cron_disabled_toolsets(_cfg),      # 3545
```
`_resolve_cron_disabled_toolsets`(165-187)固定禁四个 toolset:

`cron/scheduler.py:180 @ 863e313`
```python
    disabled = ["cronjob", "messaging", "clarify", "memory"]
```

#### 2.3.8 非活动超时(3559-3689)

不是墙钟超时,是**空闲超时**:

`cron/scheduler.py:3559-3566 @ 863e313`
```python
        # Run the agent with an *inactivity*-based timeout: the job can run
        # for hours if it's actively calling tools / receiving stream tokens,
        # but a hung API call or stuck tool with no activity for the configured
        # duration is caught and killed.  Default 600s (10 min inactivity);
        # override via HERMES_CRON_TIMEOUT env var.  0 = unlimited.
        #
        # Uses the agent's built-in activity tracker (updated by
        # _touch_activity() on every tool call, API call, and stream delta).
```
监控循环每 `_POLL_INTERVAL = 5.0`s(3580)醒一次(3638-3656),顺带做 one-shot 抢占续租
(`_heartbeat_run_claim_if_due`,3598-3611)。超时后 `request_hard_interrupt` 并抛
`TimeoutError`(3684-3689)。

**even 无限超时也要 poll**——因为 one-shot 需要续租:
`cron/scheduler.py:3621-3635 @ 863e313`
```python
            if _cron_inactivity_limit is None:
                # Unlimited — no inactivity watchdog, but a one-shot still
                # needs its run_claim heartbeat, so poll instead of blocking.
                if _is_oneshot:
                    ...
                else:
                    result = _cron_future.result()
```

#### 2.3.9 回合结果的判读(3691-3771)

三层判读:

1. **非 dict 返回**直接抛(3692-3695)。
2. **agent 自报失败**要抛,不能当成功投递(#17855):
   `cron/scheduler.py:3697-3703 @ 863e313`
   ```python
        # If the agent itself reported failure (e.g. all retries exhausted on
        # API errors, model abort, mid-run interrupt), do not silently mark the
        # job as successful. run_agent populates `failed=True`/`completed=False`
        # on these paths and may put the error into `final_response`, which
        # would otherwise be delivered as if it were the agent's reply and the
        # job's `last_status` set to "ok". Raise so the except handler below
        # builds the proper failure tuple. (issue #17855)
   ```
   例外:`max_iterations_reached(...)` 且有内容 → 当成功投递(3706-3724)。
3. **异常空回合的解释文案抑制(#34452)**:
   `cron/scheduler.py:3730-3738 @ 863e313`
   ```python
        # Cron silence on abnormal empty turns.  The turn-completion explainer
        # (#34452) replaces a blank/empty model turn with a "⚠️ No reply: …"
        # string so interactive surfaces (CLI/gateway) explain why the box is
        # empty.  In a cron context that turns a previously-silent empty turn
        # into a delivered warning (Manfredi's Telegram symptom).  Detect the
        # explainer text deterministically (via the same formatter that
        # produced it) and treat it as empty so the empty-response suppression
        # and soft-failure marking below apply — restoring pre-#34452 silence
        # for scheduled jobs without disabling the explainer everywhere.
   ```
   判定方式是**再调一次同一个格式化器做逐字比对**(3741-3744),不是正则匹配文案。

#### 2.3.10 `finally`(3795-3902)——恢复顺序有讲究

顺序:恢复 `TERMINAL_CWD` → 释放 cwd 锁 → 清 ContextVar → 清投递 var →
SessionDB 收尾 → 拆 agent(或交回)。

SessionDB 收尾里有三件事和三个 issue:
- **先解析压缩延续 id**(3820-3844):压缩会把 agent 轮换到 continuation session,
  要 finalize 那个而不是最初的 cron id;
- **标题必须在 `end_session`/`close` 之前写**(#50536),去重(#50537),
  永不留空标题(#50535)——3845-3879;
- **拆 agent**(3890-3902):

`cron/scheduler.py:3890-3902 @ 863e313`
```python
        # Release subprocesses, terminal sandboxes, browser daemons, and the
        # main OpenAI/httpx client held by this ephemeral cron agent. Without
        # this, a gateway that ticks cron every N minutes leaks fds per job
        # until it hits EMFILE (#10200 / "too many open files").
        #
        # When the caller opted to defer teardown (passed a list), hand the live
        # agent back instead of closing it here — delivery must run against a
        # live async client, and the caller tears down afterwards (#58720).
        if defer_agent_teardown is not None:
            if agent is not None:
                defer_agent_teardown.append(agent)
        else:
            _teardown_cron_agent(agent, job_id)
```

### 2.4 脚本执行子系统(2210-2429)

**路径监牢。** 相对路径落在 `HERMES_HOME/scripts/`,绝对路径也必须 resolve 后仍在里面:

`cron/scheduler.py:2264-2277 @ 863e313`
```python
    if raw.is_absolute():
        path = raw.resolve()
    else:
        path = (scripts_dir / raw).resolve()

    # Guard against path traversal, absolute path injection, and symlink
    # escape — scripts MUST reside within HERMES_HOME/scripts/.
    try:
        path.relative_to(scripts_dir_resolved)
    except ValueError:
        return False, (
            f"Blocked: script path resolves outside the scripts directory "
            f"({scripts_dir_resolved}): {script_path!r}"
        )
```

**解释器按扩展名选,故意不认 shebang:**

`cron/scheduler.py:2286-2291 @ 863e313`
```python
    # Pick an interpreter by extension.  Bash for .sh/.bash, Python for
    # everything else.  We deliberately do NOT honour the file's own
    # shebang: the scripts dir is trusted, but keeping the interpreter
    # choice explicit here keeps the allowed surface small and auditable.
    suffix = path.suffix.lower()
    if suffix in {".sh", ".bash"}:
```

**环境净化 + 不改进程 cwd:**

`cron/scheduler.py:2322-2337 @ 863e313`
```python
        env = build_subprocess_env()
        env.update(env_overlay)
        # Use the job's workdir as the subprocess cwd when configured,
        # otherwise default to the scripts-dir parent (back-compat).
        # NEVER mutate the Python process cwd — that would leak into
        # concurrent gateway sessions (#69396).
        _script_cwd = workdir or str(path.parent)
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=script_timeout,
            cwd=_script_cwd,
            env=env,
            **popen_kwargs,
        )
```

**脱敏在所有返回路径之前,且失败即整体打码:**

`cron/scheduler.py:2341-2349 @ 863e313`
```python
        # Redact secrets from both stdout and stderr before any return path.
        try:
            from agent.redact import redact_sensitive_text
            stdout = redact_sensitive_text(stdout)
            stderr = redact_sensitive_text(stderr)
        except Exception as e:
            logger.warning("Failed to redact sensitive text from output: %s", e)
            stdout = "[REDACTED - redaction failed]"
            stderr = "[REDACTED - redaction failed]"
```

**长脚本续租(2367-2429)。** 只对"`schedule.kind == "once"` 且有 claim owner"的作业起线程:

`cron/scheduler.py:2370-2381 @ 863e313`
```python
    """Run a cron script while keeping its owned one-shot claim fresh.

    Script execution is synchronous and may legitimately outlive the stale
    claim TTL.  Without a concurrent heartbeat, another scheduler process can
    mistake the live run for a dead owner and dispatch the same one-shot again.
    Recurring jobs and unclaimed/manual runs have no durable one-shot claim and
    therefore use the ordinary script path without starting a thread.

    The claim owner is captured from the dispatched job and never re-read from
    storage.  ``heartbeat_run_claim`` compares that stable owner before every
    refresh, so a stale runner cannot extend a replacement owner's claim.
    """
```
收尾时 `heartbeat_thread.join(timeout=1.0)`(2429),避免被别的进程的锁拖住。

### 2.5 prompt 组装与注入扫描(2458-2730)

**组装顺序(自底向上前置)**:
1. 用户 prompt(2469);
2. 脚本输出 `## Script Output` 前置(2488-2494),**脚本成功但输出为空 → 整体返回 `None`,
   跳过 AI 调用**(2496-2498);脚本失败 → `## Script Error` 前置并要求 agent 报告(2500-2506);
3. `context_from` 上游作业最新 `.md` 输出前置(2508-2555),job_id 必须是纯十六进制
   (2517,防路径穿越),单条截断到 8000 字符(2539-2541),读不到就**静默跳过**;
4. cron 执行指引前置(2559-2570)——这是 `[SILENT]` 契约的唯一出处:

`cron/scheduler.py:2559-2570 @ 863e313`
```python
    cron_hint = (
        "[IMPORTANT: You are running as a scheduled cron job. "
        "DELIVERY: Your final response will be automatically delivered "
        "to the user — do NOT use send_message or try to deliver "
        "the output yourself. Just produce your report/output as your "
        "final response and the system handles the rest. "
        "SILENT: If there is genuinely nothing new to report, respond "
        "with exactly \"[SILENT]\" (nothing else) to suppress delivery. "
        "Never combine [SILENT] with content — either report your "
        "findings normally, or say [SILENT] and nothing more.]\n\n"
    )
    prompt = cron_hint + prompt
```
5. skill / bundle 展开(2587-2647),bundle 可以 shadow 同名 skill(2594-2618);
   加载失败的 skill 会生成一段"请在回答开头告知用户"的通知插到最前(2649-2656)。

**注入扫描分两档(2663-2730)**,选档依据是"组装后的 prompt 里有什么",不是"有没有挂 skill":

`cron/scheduler.py:2681-2704 @ 863e313`
```python
    Two pattern tiers, selected by what the assembled prompt CONTAINS,
    not just whether skills are attached:

    - When the assembled prompt is essentially the user prompt + the cron
      hint (no skills, no injected data), the STRICT ``_scan_cron_prompt``
      patterns apply: a bare ``rm -rf /`` in a small directive prompt is a
      smoking gun, not prose.
    - When the assembled prompt includes runtime-loaded content — skill
      markdown (``has_skills=True``) or DATA injected from a job script's
      stdout / an upstream job's output (``has_injected_data=True``) — the
      LOOSER ``_scan_cron_skill_assembled`` pattern set is used: only
      unambiguous prompt-injection directives block; command-shape
      patterns are dropped and invisible unicode is sanitized (stripped +
      logged) rather than blocked, to avoid false-positives that
      permanently kill a job. Skill bodies are vetted at install time by
      ``skills_guard.py``; script output is produced by operator-authored
      code, the same trust class — and data feeds (e.g. a triage bot
      ingesting bug reports) legitimately quote dangerous commands.

    When the looser tier is selected because of injected data only,
    ``user_prompt`` (the raw, pre-assembly prompt) is additionally scanned
    with the STRICT set so the user-authored surface keeps the full
    create/update-time guarantee at runtime (defense-in-depth for legacy
    jobs that predate the create-time scanner).
```
这补的是 #3968:创建期只扫用户 prompt,runtime 从磁盘加载的 skill 内容从来没被扫过,
而 cron 是**非交互自动批准**的。

---

## 3. 结果投递

> 三个问题的直接答案:
> **发到哪**:由 job 的 `deliver` 字段在**开火时**解析成 0..N 个 `{platform, chat_id, thread_id}`;
> **怎么知道**:`_resolve_delivery_targets`(1289)展开逗号列表和 `all` token,
> 逐项过 `_resolve_single_delivery_target`(1141);
> **静默**:agent 回 `[SILENT]`(或裸 `SILENT`/`NO_REPLY`)→ 不投递,但输出照存;
> **只在有内容时才发**:是,`should_deliver = bool(deliver_content.strip())`(4045)。

### 3.1 目标解析(1141-1325)

`deliver` 是字符串,支持:`local` / `origin` / `<platform>` / `<platform>:<target>[:<thread>]`,
逗号可组合,`all` 是路由 token。

- `local` → 返回 None,不投递(1146-1147);
- `origin` → 用 job 存的 `origin`;origin 缺失时**逐个平台回退到 home channel**(1156-1171);
- `platform:rest` → 走 `_parse_target_ref` + `resolve_channel_name`(把 `slack:#eng`、
  `Alice (dm)` 这类友好名解析成真 id)(1173-1214);
- 裸平台名 → 优先 home channel,没有则退回 origin 的 chat_id(1216-1241)。

**`all` 在开火时展开,不是创建时**:

`cron/scheduler.py:1264-1268 @ 863e313`
```python
# Routing intent tokens — resolved at fire time, not create time, so a
# job created before Telegram was wired up will pick up Telegram once it
# comes online.  ``all`` expands into the set of connected platforms
# (those with a configured home chat_id) in _expand_routing_tokens.
_ROUTING_TOKENS = frozenset({"all"})
```

去重键是 `(platform.lower(), chat_id, thread_id)` 三元组(1315)。

`_normalize_deliver_value`(1244-1261)专门处理"MCP 客户端传了数组"这种历史脏数据——
否则 `str(["telegram"])` 会变成字面量 `"['telegram']"` 而静默解析失败。

### 3.2 `_deliver_result`(1467-2110)

**无目标时的三分支**(1478-1498):`local` 返回 None(不算失败);
`origin` 但无 origin 也无 home channel 也返回 None(#43014,否则 CLI 创建的作业每次都报假错);
其它情况返回错误串。

**包装**(1506-1523):默认 `cron.wrap_response: true`,加头 `Cronjob Response: <name>\n(job_id: ...)` 和尾。

**媒体**:`MEDIA:` 标签抽出来走原生附件(1529-1530)。

**镜像开关**(1536-1543 + `_cron_mirror_delivery_enabled`:619-648):
per-job `attach_to_session` > 全局 `cron.mirror_delivery` > **默认 False**。
镜像只对 origin 会话生效(`_target_matches_origin`,1577-1579),扇出/广播/home 回退目标不镜像。

**每个 target 的两条投递路径:**

- **live adapter 路径**,条件是 adapter 在 + loop 在 + loop 正在跑:
  `cron/scheduler.py:1622-1626 @ 863e313`
  ```python
        live_adapter_ready = (
            runtime_adapter is not None
            and loop is not None
            and getattr(loop, "is_running", lambda: False)()
        )
  ```
  走 `DeliveryRouter._deliver_to_platform`(1818-1825),`future.result(timeout=60)`。
  **超时语义靠 `future.cancel()` 的返回值区分**:
  `cron/scheduler.py:1835-1852 @ 863e313`
  ```python
                            # #38922: a slow confirmation does NOT necessarily
                            # mean the send failed — but we must distinguish two
                            # cases via future.cancel()'s return value:
                            #
                            #   cancel() == False -> the coroutine was already
                            #     running on the gateway loop when the timeout
                            #     fired; the request is in flight on the wire and
                            #     cannot be un-sent.  Re-sending via standalone
                            #     would be a guaranteed DUPLICATE, so treat it as
                            #     delivered (assume-delivered).
                            #
                            #   cancel() == True -> the scheduled callback never
                            #     started executing (loop wedged/backlogged for
                            #     the full 60s), so nothing was sent.  We MUST
                            #     fall through to the standalone path or the
                            #     message is silently dropped (worse than a
                            #     duplicate).
  ```
- **standalone 路径**(2039-2092):`asyncio.run(_send_to_platform(...))`,
  失败再退到一次性线程池。relay 平台**不回退**(2016-2026,重发会重复且认证不对);
  解释器收尾中也不回退(2033-2038,#58720/#55924)。

**可续聊表面(D1/D2/D6)。** 默认 `thread`,平台配置 `cron_continuable_surface: in_channel`
且 adapter 有 `supports_inchannel_continuable` 才走扁平投递(1641-1658),否则 fail-safe 回 thread。
thread 模式会先开一个专属 thread 再投(1720-1737),**但 session 种子推迟到投递成功之后**才播:

`cron/scheduler.py:1731-1735 @ 863e313`
```python
                # Route THIS delivery into the new thread now (the send needs the
                # thread_id), but defer seeding the thread session until the
                # delivery actually succeeds — otherwise an open-succeeds /
                # deliver-fails case leaves a seeded brief the user never saw,
                # and (worse) suppresses the DM-fallback mirror via thread_seeded.
```

**Telegram 三态话题路由**(1739-1790,#22773 / #52060):
`telegram:<正数 chat_id>:<数字 thread_id>` 形状歧义——可能是私聊里的论坛话题,
也可能是 Bot API 频道 Direct-Messages 话题,两者路由**相反**,靠
`_is_channel_dm_topic` 在投递时区分,并把 `thread_id` 放进 `route_metadata` 绕开
DeliveryRouter 对"私聊话题必须有回复锚点"的要求(cron 投递没有入站锚点)。

### 3.3 静默与"只在有内容时才发"(run_one_job:4038-4066)

`cron/scheduler.py:4038-4055 @ 863e313`
```python
            # Deliver the final response to the origin/target chat.
            # If the agent responded with [SILENT], skip delivery (but
            # output is already saved above).  Failed jobs always deliver.
            deliver_content = final_response if success else _summarize_cron_failure_for_delivery(job, error)
            # Treat whitespace-only final responses the same as empty
            # responses: do not deliver a blank message, and let the
            # empty-response guard below mark the run as a soft failure.
            should_deliver = bool(deliver_content.strip())
            unresolved_origin = False
            # Cron silence suppression — see _is_cron_silence_response.  Replaces the
            # old `SILENT_MARKER in ...upper()` substring check, which both leaked
            # bracketless near-markers ("SILENT" / "NO_REPLY") and wrongly swallowed
            # a real report that merely quoted "[SILENT]" mid-sentence (#51438,
            # #46917).  Keeps the intentional bracketed-prefix / trailing-line
            # tolerance the cron contract relies on.
            if should_deliver and success and _is_cron_silence_response(deliver_content):
                logger.info("Job '%s': agent returned %s — skipping delivery", job["id"], SILENT_MARKER)
                should_deliver = False
```
`_is_cron_silence_response`(311-325)委托给
`gateway.response_filters.is_autonomous_silence_response`,识别整段/首行/末行的
`[SILENT]`,以及裸 `SILENT` / `NO_REPLY` / `NO REPLY`;**句中出现视为真内容照发**。

失败作业的投递内容是压缩成一行的摘要(`_summarize_cron_failure_for_delivery`,99-149),
把 429/超时/401-403 归成短句,其余截到 180 字符,详情留在 cron output 和日志里。

**投递结局四态**(4083-4097),写进 execution 账本:
```python
        if delivery_error:
            delivery_outcome = "failed"
        elif should_deliver and unresolved_origin:
            delivery_outcome = "not_configured"
        elif should_deliver and normalized_deliver != "local":
            delivery_outcome = "delivered"
        else:
            delivery_outcome = "suppressed"
```

---

## 4. `scheduler_provider.py`(全 357 行)

### 4.1 抽象是什么

模块自我定位为 **Axis B = 触发器**,明确排除"触发意味着什么":

`cron/scheduler_provider.py:10-18 @ 863e313`
```python
A CronScheduler decides *when* a due job fires. It does NOT decide what firing
means: execution + delivery stay in cron.scheduler.run_job / _deliver_result,
shared by all providers. Providers must never reimplement agent construction or
delivery.

The built-in InProcessCronScheduler runs the historical 60s daemon-thread
ticker. Alternative providers (e.g. Chronos, a NAS-mediated managed-cron
provider for scale-to-zero deployments) live under plugins/cron_providers/<name>/ and are
selected via the `cron.provider` config key (empty = built-in).
```

**并且显式标 EXPERIMENTAL,给出了演进纪律:**

`cron/scheduler_provider.py:3-8 @ 863e313`
```python
⚠️ EXPERIMENTAL — this interface is validated by exactly ONE consumer (the
built-in) until an external provider (Chronos, Phase 4) shakes it out. Until
then the module path, method signatures, and start() kwargs MAY change without
a deprecation cycle. Once a second provider validates the shape it becomes
stable. Any growth MUST be additive (new optional method with a default), never
a changed signature on start() or a new abstractmethod.
```

### 4.2 接口面(27-119)

| 成员 | 抽象? | 默认行为 |
|---|---|---|
| `name`(37-40) | **abstract property** | — |
| `is_available`(42-49) | 否 | `True`;**契约:不得发网络请求** |
| `start`(51-66) | **abstract** | — |
| `stop`(68-72) | 否 | no-op |
| `on_jobs_changed`(78-83) | 否 | no-op(内置每 tick 重读 jobs.json) |
| `recover_interrupted`(85-89) | 否 | 调 `cron.executions.recover_interrupted_executions()` |
| `fire_due`(91-113) | 否 | store CAS 抢占 + `run_one_job` |
| `reconcile`(115-119) | 否 | no-op |

后四个是 Phase-4 追加的**非抽象**钩子,注释明说是为了让内置不改一行仍满足 ABC:

`cron/scheduler_provider.py:74-76 @ 863e313`
```python
    # --- Optional hooks for external providers (added Phase 4). --------------
    # All default-safe so the built-in inherits working behavior without
    # overriding. Keep these NON-abstract — see test_abc_growth_stays_additive.
```

`fire_due` 的默认实现就是"多机 at-most-once"的落点:

`cron/scheduler_provider.py:103-113 @ 863e313`
```python
        from cron.jobs import claim_job_for_fire, get_job
        from cron.executions import create_execution
        from cron.scheduler import run_one_job

        if not claim_job_for_fire(job_id):
            return False  # another machine already claimed this fire
        job = get_job(job_id)
        if job is None:
            return False  # job removed (e.g. repeat-N exhausted) between arm and fire
        job["execution_id"] = create_execution(job_id, source=self.name)["id"]
        return run_one_job(job, adapters=adapters, loop=loop)
```

### 4.3 有几种实现 / 选择逻辑在哪

**两种**:
1. `InProcessCronScheduler`(本文件 162-357,核心内置,**故意不放 plugins/**);
2. `ChronosCronScheduler`(`plugins/cron_providers/chronos/__init__.py:47`)。

选择逻辑在 `resolve_cron_scheduler()`(122-159),读 `cron.provider`:

`cron/scheduler_provider.py:141-159 @ 863e313`
```python
    if not name or name in ("builtin", "in-process", "inprocess"):
        return InProcessCronScheduler()

    try:
        from plugins.cron_providers import load_cron_scheduler
        provider = load_cron_scheduler(name)
        if provider is None:
            logger.warning("cron.provider '%s' not found; using built-in ticker", name)
            return InProcessCronScheduler()
        if not provider.is_available():
            logger.warning("cron.provider '%s' not available; using built-in ticker", name)
            return InProcessCronScheduler()
        logger.info("Using cron scheduler provider: %s", provider.name)
        return provider
    except Exception as e:
        logger.warning(
            "Failed to load cron.provider '%s' (%s); using built-in ticker", name, e
        )
        return InProcessCronScheduler()
```
**四条回退路径全部落到内置**——"cron 永不失去触发器"。

调用点:`gateway/run.py:26877`、`gateway/platforms/api_server.py:5705`(fire webhook)、
`hermes_cli/web_server.py:11965`、`hermes_cli/cron.py:59`(只取名字做 status 展示)、
`cron/scheduler.py:4146`(`_notify_provider_jobs_changed`)。

### 4.4 内置 ticker(162-261)

`cron/scheduler_provider.py:225-261 @ 863e313`
```python
        while not stop_event.is_set():
            ok = False
            try:
                if can_dispatch is not None and not can_dispatch():
                    logger.debug("Cron dispatch paused while gateway drains existing work")
                else:
                    cron_tick(
                        verbose=False,
                        adapters=adapters,
                        loop=loop,
                        sync=False,
                        can_dispatch=can_dispatch,
                    )
                ok = True
            except BaseException as e:
                # Catch BaseException (not just Exception) so a SystemExit from
                # a misbehaving provider SDK / agent retry path does not kill
                # the ticker thread silently (#32612). KeyboardInterrupt is
                # intentionally caught here too — gateway shutdown is driven by
                # stop_event (set by the main thread's signal handler), not by
                # an exception in this daemon thread, so swallowing it and
                # re-checking stop_event keeps shutdown clean.
                logger.error("Cron tick error: %s", e, exc_info=True)
                # Persist the failure reason next to the heartbeat markers so
                # `hermes cron status`/`list` (separate processes) can show
                # WHY ticks fail, not just that the success marker is stale —
                # e.g. a root-rewritten jobs.json locking out the ticker's
                # uid went unnoticed for ~14h with the reason buried in the
                # gateway log (#68483).
                record_ticker_error(f"{type(e).__name__}: {e}")
            # Record liveness every iteration; bump the success marker only on a
            # clean tick, so status can tell "alive but failing every tick" from
            # "actually firing jobs" (#32612, #32895).
            record_ticker_heartbeat(success=ok)
            if ok:
                clear_ticker_error()
            stop_event.wait(interval)
```
两个心跳标记(liveness vs. success)是为了区分"线程还活着但每 tick 都炸"和"真在开火"。

注意 `can_dispatch` 在这里和 `tick` 内部**各判一次**(225-230 与 `scheduler.py:4193`),
外层这次能省掉整个文件锁 + `get_due_jobs` 的 IO。

**多 profile 复用(263-357,#69377)。** 每个 profile 用
`set_hermes_home_override()` + `use_cron_store()` 包一层,分别做 recovery(299-313)、
tick(321-334)、心跳(342-356)。

### 4.5 Chronos 与 scale-to-zero 说法的核对

**结论:文档 `cron-internals.md:132-142` 的 scale-to-zero 说法与代码一致,不构成 ▲。**
证据链三处:

1. 代码自己的模块 docstring 就这么写:`cron/scheduler_provider.py:16-17`
   `"Alternative providers (e.g. Chronos, a NAS-mediated managed-cron provider for
   scale-to-zero deployments)"`。
2. Chronos 插件 docstring:`plugins/cron_providers/chronos/__init__.py:1-19`
   ```python
   """Chronos — NAS-mediated managed cron provider (scale-to-zero).
   ...
   Design constraints (see the plan's DQ-1):
     - start() arms all enabled jobs and RETURNS; it never blocks and never spawns
       a periodic wake. Between fires the machine is truly at zero.
     - reconcile runs only on a warm process (start / on_jobs_changed / piggybacked
       on a fire), never as a periodic wake of a sleeping machine.
   ```
3. `start()` 实现确实不循环:`plugins/cron_providers/chronos/__init__.py:103-117`
   ```python
       def start(self, stop_event, *, adapters=None, loop=None, interval=60):
           """Arm all enabled jobs via NAS, then RETURN immediately.

           Does NOT block and does NOT spawn a 60s wake (DQ-1) — that is the whole
           point of scale-to-zero. The machine wakes only on a NAS→agent fire.
           """
           # A new provider lifecycle cannot prove what an interrupted prior
           # process did. Classify those attempts unknown for audit only; do not
           # requeue them here.
           self.recover_interrupted()
           try:
               self.reconcile()
           except Exception as e:
               logger.warning("Chronos start() reconcile failed: %s", e)
           # Intentionally return — no loop, no periodic wake.
   ```
   入站开火 webhook 真实存在:`gateway/platforms/api_server.py:5643`(handler 定义在 `:5642`)
   `"""POST /api/cron/fire — Chronos managed-cron fire webhook (NAS → agent)."""`。

**但有两条重要限定,文档没写(记 ◇,见 §6):**
- **cron 不再是唯一定时唤醒源。** 网关无条件另起一条 housekeeping 线程,
  它自己有 60s 循环,与 provider 无关:
  `gateway/run.py:26134-26137 @ 863e313`
  ```python
      Split out of the historical ``_start_cron_ticker`` so the cron *trigger*
      can live behind the ``CronScheduler`` provider (built-in or external) while
      these gateway-specific chores keep running independently of which provider
      fires cron. An external scale-to-zero provider has no 60s loop at all, but
      this housekeeping still wants its hourly cadence — so it owns its own loop.
  ```
  所以"进程可以完全停掉"是**部署层面**的说法,单靠切 provider 并不能让 hermes 进程自己不醒。
- **Chronos 开火路径拿不到 live adapter**(见 §6 ▲-3)。

---

## 5. `lifecycle_guard.py`(全 565 行)

### 5.1 守的是什么生命周期 / 防的是什么故障

守的是 **hermes gateway 进程自身的生命周期**;防的是 **agent 自己给自己排了一个"重启网关"
的定时任务,然后在 KeepAlive 监管下变成每 ~10 秒一次的 SIGTERM-重生死循环**:

`cron/lifecycle_guard.py:1-15 @ 863e313`
```python
"""Gateway lifecycle guard for cron job creation (#30719).

An agent running inside a gateway can schedule a cron job that calls
``hermes gateway restart`` (or ``launchctl kickstart ai.hermes.gateway``
or ``systemctl restart hermes-gateway``).  When the cron fires, the
gateway dies, the supervisor (launchd KeepAlive / systemd Restart=)
revives it, auto-resume picks up the offending session, and the resumed
turn re-runs the same logic — a SIGTERM-respawn loop every ~10 seconds
until manually broken.

This module rejects cron job specs whose prompt or script contains a
direct shell-level gateway-lifecycle command.  It is enforced at
``cron.jobs.create_job`` so it fires on every job-creation path: the
``hermes cron create`` CLI subcommand AND the agent's ``cronjob`` model
tool (which calls ``create_job`` directly, bypassing the CLI layer).
```

**为什么用"命令形状"而不是关键词:**

`cron/lifecycle_guard.py:17-24 @ 863e313`
```python
The pattern is intentionally command-shaped: it anchors on a concrete
command identifier (``hermes gateway``, ``launchctl ... hermes-gateway``,
``systemctl ... hermes-gateway``, ``pkill`` against the gateway) so it
cannot fire on prose.  A cron ``prompt`` is fed to a future LLM, not a
shell, so an over-broad substring match on English ("Kong API gateway
autoscaling and restart behavior") would produce a high false-positive
rate without preventing the actual foot-gun, which requires a real
command shape.
```

### 5.2 检测分层

**层 1:正则四分支(56-82)。**
- A(62):`hermes gateway restart|stop`——**故意不含 `start`**
  (61-62 注释:"starting a gateway from inside a gateway is benign");
- B(75):`launchctl (kickstart|unload|load|stop|restart|submit|bootstrap) ... hermes[.-]?gateway`;
- C(77):`systemctl ... (restart|stop|start) ... hermes[.-]?gateway`;
- D(80-81):`p?kill ... hermes ... gateway` 与反序两条。

**层 1.5:shell 续行折叠(85-95)。** 因为每个分支用 `[^\n]*`,多行续写的真命令会漏:

`cron/lifecycle_guard.py:85-95 @ 863e313`
```python
# A backslash immediately followed by a newline is a POSIX shell line
# continuation — the shell joins the two lines before parsing. Every branch
# above uses `[^\n]*` between its verb and the gateway identifier so the
# match can't span unrelated lines of a longer cron prompt/script, but that
# also means a real multi-line shell invocation split across continuation
# lines (e.g. `launchctl submit \` / `  -l ai.hermes.gateway-... \` / `  -- ...`,
# the exact reported shape in #62891) would otherwise slip past. Collapse
# continuations to a single space before matching, mirroring what the shell
# itself does, rather than loosening `[^\n]*` and risking false positives
# across genuinely separate lines.
_SHELL_LINE_CONTINUATION = re.compile(r"\\\r?\n[ \t]*")
```

**层 2:label 无关的 `launchctl submit|bootstrap` 检测(155-173)。**
这是对 #62891 第二次复现的应答——标签是攻击者自选的,任何锚 label 的正则都能被中性名绕开:

`cron/lifecycle_guard.py:156-163 @ 863e313`
```python
    """Detect an executed ``launchctl submit``/``bootstrap``, not quoted text.

    Label-independent by design: the label of a submitted/bootstrapped job is
    chosen by whoever writes it, so a neutral name (``ai.hermes.svc-reload-tmp``)
    defeats any label-anchored regex (#62891, second reproduction). Both verbs
    register a NEW persistent launchd job (``submit`` jobs get KeepAlive
    semantics; ``bootstrap`` loads an arbitrary plist), which is never safe to
    do from inside the gateway process.
    """
```
实现是**执行感知的**:先 shlex 切段(`_iter_command_segments`,118-143,处理引号、注释、
`;&|()` 分隔),跳过前缀 env 赋值(`_command_token_index`,146-152),再看首 token 的
basename 是不是 `launchctl`——所以被引号包起来的文本不会误报。

**层 3:递归展开被引用的脚本(214-421)。**
- `_iter_referenced_shell_scripts`(214-269):识别 `. script` / `source script`、
  `sh|bash|dash|ksh|zsh [opts] script`、含 `/` 或以 `.sh/.bash/.zsh` 结尾的裸命令;
- `_iter_shell_command_payloads`(272-282):抽出 `-c '...'` 的内联代码继续递归;
- `_contains_unsafe_gateway_action`(359-421):深度上限 8,**超限直接判 unsafe**:
  `cron/lifecycle_guard.py:371-372 @ 863e313`
  ```python
      if depth >= _MAX_REFERENCED_SCRIPT_DEPTH:
          return True
  ```
  用 `visited` 集防环(392-394),脚本内的相对引用按**该脚本自己的目录**解析(410-412)。

### 5.3 "守卫本身绝不能崩"这条契约

这是本文件反复出现的主题,四个 issue 都在这条线上:

`cron/lifecycle_guard.py:176-198 @ 863e313`
```python
def _expand_candidate_path(candidate: str) -> Optional[Path]:
    """Sanitize a tokenized path candidate at the ingestion boundary.

    Candidate tokens come from shlex-splitting arbitrary command text —
    including text recursively decoded from binaries or remote reads — so
    they can carry NUL bytes or other junk no real filesystem path can
    contain. Every OS-facing ``Path`` operation downstream (``expanduser``,
    ``os.open``, ``resolve``) raises a *different* exception for the same
    junk (``ValueError: embedded null byte``, ``RuntimeError: Could not
    determine home directory`` when HOME is unset under launchd, OSError
    for over-long paths). Rejecting here — once, before any OS call — is
    the whole-class fix; catching per-syscall was the whack-a-mole that
    produced #76762, #77703, #77780, and #78256.
    ...
```

顶层封装把契约写死在函数边界上:

`cron/lifecycle_guard.py:430-463 @ 863e313`
```python
    """Detect lifecycle/submit commands, including bounded nested scripts.

    Total by construction: this function returns a verdict for *every*
    input and never raises. The direct scans below are pure string
    operations; the referenced-script walk touches the filesystem, remote
    backends, and shlex on arbitrary decoded bytes, so it is best-effort
    defense-in-depth — any unexpected failure inside it is logged and
    treated as "walk found nothing" rather than crashing the caller.

    This is the contract #76762 established ("a guarded path must never
    crash the guard") enforced at the boundary instead of per-syscall: a
    guard crash propagates out of ``tools/terminal_tool.py`` and breaks
    every terminal command until the gateway restarts (#77780, #78256),
    which is strictly worse than either verdict.
    """
    try:
        # Includes the direct regex/submit scans at depth 0.
        return _contains_unsafe_gateway_action(
            command,
            cwd=cwd,
            depth=0,
            visited=set(),
            read_remote_script=read_remote_script,
        )
    except Exception:
        logger.warning(
            "lifecycle guard referenced-script walk failed; "
            "falling back to direct-scan verdict",
            exc_info=True,
        )
        # Pure string scans of the top-level command — cannot raise.
        return contains_gateway_lifecycle_command(
            command
        ) or contains_launchctl_submit_command(command)
```

读文件的三态语义(`_read_referenced_script`,296-330):
- 非常规文件(非 `S_ISREG`)→ `(None, True)` = **unsafe,fail closed**(310-311);
- 首块含 NUL(二进制 ELF/Mach-O/PE)→ `(None, False)` = **"没东西可扫",不算 unsafe**(326-327,#76762);
- 超 1 MiB → `(None, True)` = **unsafe**(328-329)。

远程回调的输出走同一套语义(`_sanitize_remote_script_text`,333-356),
且**用字节数而非字符数比大小**——多字节文件按字节截断后字符数更少,按字符判会误放行(345-348)。

### 5.4 `.py` 脚本的特例(541-551)

`cron/lifecycle_guard.py:541-551 @ 863e313`
```python
    if python_script:
        # Python is executed by the interpreter, never through a POSIX
        # shell: the shell-script reference walk is a false-positive
        # generator on Python sources (pathlib's "/" operator resolves to
        # the filesystem root and trips the regular-file check, blocking
        # every innocent .py cron script, #77131). The direct command
        # regex below still scans the full text, so a literal
        # `hermes gateway restart` embedded in a .py script is still
        # blocked. Non-regular/oversized script files still fail closed
        # via the lifecycle-shaped sentinel in _read_script_for_scanning.
        unsafe = contains_gateway_lifecycle_command(combined)
```
配套的 `_iter_referenced_shell_scripts:260-269` 也专门跳过纯 `/` token(同一个 #77131)。

### 5.5 与 gateway shutdown / drain 的配合(交叉引用)

**关键结论:`lifecycle_guard.py` 与 gateway 的 shutdown/drain **没有直接协作**,
它是把"agent 触发的关机"从源头掐掉,而 gateway 的 drain/shutdown 处理的是"外部触发的关机"。
两者在 cron 上的接缝在 `cron/scheduler.py` 那侧,不在 guard 里。**

三条互补防线:
1. **创建期**:`cron/jobs.py:1365-1366` → `check_gateway_lifecycle(prompt, script)`;
2. **执行期(终端工具)**:`tools/terminal_tool.py:2504-2510` 与 `:2586-2601`,
   仅当 `os.environ.get("_HERMES_GATEWAY") == "1"` 时,`force=True` 也压不住;
3. **CLI 自指**:guard docstring:`cron/lifecycle_guard.py:29-30`
   `"``hermes gateway stop|restart`` separately refuse to self-target from inside the gateway."`

gateway 侧的 cron 关机协作(在 scheduler.py,不在 guard):
- **drain 可见性**:`gateway/run.py:7404-7405` 调 `cron.scheduler.get_running_job_ids()`
  把在飞 cron 计入 active work,否则 drain 对 cron 是"结构性失明"(#60432);
- **强杀后打断标记**:`gateway/run.py:12713-12714` 调 `mark_running_jobs_interrupted(...)`;
- **排水期停派发**:`gateway/run.py:26910-26913` 注入 `can_dispatch`(**仅内置 provider**);
- **停机**:`gateway/run.py:26966-26971`,先 `cron_stop.set()`,再 `cron_provider.stop()`,
  再等线程退出(`_CRON_SHUTDOWN_DRAIN_TIMEOUT`,注释在 `gateway/run.py:26307-26310`
  说明这个上限来自 `_deliver_result` 的 `future.result(timeout=60)`)。

---

## 6. ▲/◇ 候选

> ▲ = 文档与代码矛盾;◇ = 代码有而文档无。双侧证据。
> 对表对象:`website/docs/developer-guide/cron-internals.md`(303 行)。

### ▲-1 `running` 不是真实的作业状态

- 文档:`website/docs/developer-guide/cron-internals.md:73`
  `| running | Currently executing (transient state) |`
  以及 `:92` tick 伪码 `a. Set state to "running"`。
- 代码:`cron/jobs.py` 全文没有任何 `state = "running"` 的写入。实际写入的三个值是
  `"scheduled"`(`cron/jobs.py:469`、`:1787`)、`"completed"`(`:1752`、`:1785`、`:1878`)、
  `"error"`(`:1769`)。在飞状态只存在于**进程内内存集合**:
  `cron/scheduler.py:334 @ 863e313`
  ```python
  _running_job_ids: set = set()
  ```
  由 `_submit_with_guard:4295` 加入、`_run_and_release:4305-4307` 移除。
- 影响:另一个进程(如 `hermes cron list`)永远看不到 `running`。

### ▲-2 tick 伪码把并发/顺序完全画反

- 文档:`cron-internals.md:85-101` 的 tick 伪码是**严格串行**的
  "for each due job: … e. Deliver … f. compute next_run … 5. Write updated jobs back …
  6. Release scheduler lock"。
- 代码:
  - `next_run_at` 是在**任何执行开始前**、锁内一次性批量前推的:`cron/scheduler.py:4224`
    `advance_next_runs([job["id"] for job in due_jobs])`;
  - 执行是**分两个持久线程池并发**的:`:4266-4267` 分池 + `:4340-4363` 派发;
  - 网关 ticker 用 `sync=False`(`cron/scheduler_provider.py:235`),
    tick **不等**作业结束就返回并释放锁(`:4392-4412` 只挂 done-callback);
  - 投递发生在 `run_one_job`(`:4063`),在锁外的工作线程里。
- 影响:读者按文档会得出"cron 作业彼此串行、锁覆盖整个执行"的错误模型。

### ▲-3 "firing 的含义对所有 provider 完全一致"——投递能力实际不一致

- 文档:`cron-internals.md:126-128`
  `"What "firing" *means* (job execution + delivery) is unchanged and shared by all
  providers … A provider only controls the trigger, never execution."`
- 代码:内置路径把网关的 live adapters 和 event loop 一路传下去
  (`gateway/run.py:26878` → `scheduler_provider.py:231-237` → `scheduler.py:4258`
  → `run_one_job(..., adapters=adapters, loop=loop)`);
  而 Chronos 的入站开火路径**硬传 `adapters=None`**:
  `gateway/platforms/api_server.py:5710-5712 @ 863e313`
  ```python
              task = asyncio.create_task(
                  asyncio.to_thread(provider.fire_due, job_id, adapters=None, loop=loop)
              )
  ```
  `hermes_cli/web_server.py:11966` 更彻底:`provider.fire_due(job_id, adapters=None, loop=None)`。
- 后果(对照 `_deliver_result`):`runtime_adapter` 为 None → `live_adapter_ready` 为 False
  (`scheduler.py:1622-1626`)→ 走 standalone HTTP 发送。于是 **E2EE 房间(Matrix)、
  可续聊 thread 开启(`:1720-1737`)、in_channel 扁平续聊种子(`:1992-1998`)在 Chronos 下全部不生效**。
  文档 `:1471-1474`(`_deliver_result` docstring)自己就说 live adapter 路径是给 E2EE 用的。

### ▲-4 "cron 投递不会镜像进网关会话历史"已不成立

- 文档:`cron-internals.md:270-272`
  `"### Session Isolation — Cron deliveries are NOT mirrored into gateway session
  conversation history."`
- 代码:存在完整的镜像通路,只是**默认关**:
  `cron/scheduler.py:627-632 @ 863e313`
  ```python
      Precedence (first decisive value wins):
        1. Per-job ``attach_to_session`` (bool) — set via the ``cronjob`` tool,
           lets one briefing job opt in without flipping global behaviour.
        2. Global ``cron.mirror_delivery`` (bool) in config.yaml.
        3. False.
  ```
  实际调用点 `scheduler.py:1999-2003` / `:2102-2106`(`_maybe_mirror_cron_delivery`)。
- 定性:文档把"默认行为"写成了"绝对保证",且完全没提 `attach_to_session` /
  `cron.mirror_delivery` 两个开关。

### ▲-5 "脚本是 Python 脚本"——bash 是一等公民

- 文档:`cron-internals.md:200` `"Jobs can also attach a Python script via the ``script`` field."`
  例子(`:202-207`)也只给 `.py`。
- 代码:`.sh` / `.bash` 走 bash,其余走 Python;而且这是为 `no_agent` watchdog 专门做的:
  `cron/scheduler.py:2228-2229 @ 863e313`
  ```python
      Shell support lets ``no_agent=True`` jobs ship classic bash watchdogs
      (the `memory-watchdog.sh` pattern) without wrapping them in Python.
  ```
  选择点 `:2290-2306`。
- 另:文档 `:209` 说 `_get_script_timeout()` 是 "three-layer chain",紧接着列了 **4 条**
  (`:210-214`)——文档内部自相矛盾;代码 `:2119-2149` 确实是 4 层(模块覆盖/env/config/默认)。

### ▲-6 `deliver: local` 的描述会让人以为只有 local 才存盘

- 文档:`cron-internals.md:238` `| Local file | ``local`` | Save to ``~/.hermes/cron/output/`` |`
- 代码:`save_job_output` 对**每一个**作业无条件调用,与 `deliver` 无关:
  `cron/scheduler.py:4020` `output_file = save_job_output(job["id"], output)`。
  `local` 的真实含义是"解析不出投递目标,不投递"(`:1146-1147`、`:1300-1301`)。

### ◇-1 文档完全没提 `cron/lifecycle_guard.py`

`cron-internals.md` 的 Key Files 表(`:13-19`)只列 5 个文件,`lifecycle_guard.py`(565 行)、
`scheduler_provider.py`(357 行)、`executions.py`、`suggestions.py`、`blueprint_catalog.py`、
`suggestion_catalog.py` 全部缺席;正文也没有任何"cron 不能重启网关"的说明。
代码侧:`cron/jobs.py:1365-1366` 是强制拦截点,被拦的用户会拿到
`GatewayLifecycleBlocked`(`lifecycle_guard.py:559-565`)却在文档里找不到解释。

### ◇-2 `check_gateway_lifecycle` 只在 create 生效,update 完全绕过(已实证)

代码侧:全仓只有一个调用点:
```
$ grep -rn "check_gateway_lifecycle" cron/ tools/
cron/jobs.py:1365:    from cron.lifecycle_guard import check_gateway_lifecycle
cron/jobs.py:1366:    check_gateway_lifecycle(prompt_text, normalized_script)
```
`cron/jobs.py:1507 update_job` 不调;`tools/cronjob_tools.py:914-964` 的 `update` 分支只跑
`_scan_cron_prompt`(`:917`),而 `_CRON_THREAT_PATTERNS`(`tools/cronjob_tools.py:97-106`)
八条模式没有一条能匹配 `hermes gateway restart`。

**实证**(隔离 HERMES_HOME,不动仓库):
```
CREATE: blocked OK
UPDATE via cron.jobs.update_job: succeeded, stored prompt = 'hermes gateway restart'
UPDATE via cronjob tool: True -> 'hermes gateway restart'
```
即 `cronjob(action="update", job_id=..., prompt="hermes gateway restart")` 成功落库。
`script` 字段同理可改(`tools/cronjob_tools.py:955-960` 只做路径校验,不做内容扫描)。

**残余防线**:该作业开火时若 agent 真去调终端,`tools/terminal_tool.py:2586` 会拦
(前提 `_HERMES_GATEWAY=1`)。但**脚本路径不受这层保护**——
`cron/scheduler.py:2329 subprocess.run(argv, ...)` 直接起进程,不经过 terminal_tool。
另存在 TOCTOU:创建时扫过的脚本文件,之后被磁盘上替换,开火时不会重扫。

### ◇-3 网关 dashboard 的 cron 变更不通知 provider

- 代码侧:`cron/scheduler.py:4136-4138` 的 docstring 说
  `"Called by the consumer surfaces (model tool / CLI / REST) AFTER a successful
  store mutation"`。实际接线:
  - model tool ✅ `tools/cronjob_tools.py:805/865/881/886/901/1017`;
  - CLI ✅(经 model tool:`hermes_cli/cron.py:45-48` `_cron_api` 直接调 `cronjob` 工具);
  - gateway REST ✅ `gateway/platforms/api_server.py:1306-1311`;
  - **dashboard / web_server REST ❌**:`hermes_cli/web_server.py:11816 _create_cron_job_sync`、
    `:11894 _pause_cron_job_sync`、`:11930 _delete_cron_job_sync` 等直接
    `_call_cron_for_profile(profile, "create_job"|"pause_job"|"remove_job", ...)`,
    整个 `hermes_cli/` 目录 grep 不到 `_notify_provider_jobs_changed`。
- 后果:Chronos 下从 dashboard 建/删/停一个作业,NAS 侧的 one-shot 不会立刻 arm/cancel,
  要等下一次 `reconcile()`(只在 start / on_jobs_changed / fire 后跑,
  `plugins/cron_providers/chronos/__init__.py:112-114`、`:122-128`、`:227-235`)。

### ◇-4 ABC 的 `start()` 签名与内置实现已经分叉,靠 isinstance 兜

- ABC:`cron/scheduler_provider.py:52-59` 只有 `(stop_event, *, adapters, loop, interval)`;
- 内置:`:176-185` 多了 `can_dispatch=None, profile_homes=None`;
- 调用方只能类型判断:`gateway/run.py:26910-26913`、`:26910`
  ```python
      if isinstance(cron_provider, InProcessCronScheduler):
          cron_start_kwargs["can_dispatch"] = lambda: not (
              runner._draining or runner._external_drain_active
          )
  ```
- 与模块自己立的规矩(`:7-8` "never a changed signature on start()")构成张力:
  内置没改 ABC 签名,但**加了 ABC 不知道的必需能力**,导致外部 provider 结构性拿不到
  drain 闸门(Chronos 的 drain 保护改由 `api_server._draining_response()` 在 HTTP 层做,
  `gateway/platforms/api_server.py:5691-5693`)。

### ◇-5 `workdir` 只对 `no_agent` 作业影响脚本 cwd

- `no_agent` 路径显式传:`cron/scheduler.py:2839-2841`
  ```python
              ok, output = _run_job_script_with_claim_heartbeat(
                  job, script_path, workdir=_job_workdir,
              )
  ```
- LLM 路径的预跑**不传**:`cron/scheduler.py:2987`
  ```python
          prerun_script = _run_job_script_with_claim_heartbeat(job, script_path)
  ```
  `_build_job_prompt` 的兜底路径也不传:`:2485` `success, script_output = _run_job_script(script_path)`。
- 于是同一个作业配了 `workdir` + `script`:`no_agent=True` 时脚本 cwd = workdir,
  `no_agent=False` 时脚本 cwd = 脚本父目录(`:2328` `_script_cwd = workdir or str(path.parent)` 的
  `workdir` 为 None)。文档对 `workdir` 只字未提。

### ◇-6 文档没有 `no_agent` / `wakeAgent` / `context_from` / 漂移守卫 / 注入扫描

`cron-internals.md` 全文搜不到 `no_agent`、`wakeAgent`、`context_from`、`provider_snapshot`、
`attach_to_session`、`enabled_toolsets`、`max_parallel_jobs`。这些都是本切片里成体量的机制:
`scheduler.py:2819`(no_agent)、`:2432`(wake gate)、`:2509`(context_from)、
`:3440`(#44585 漂移守卫)、`:2663`(组装期注入扫描)、`:4228-4244`(并发上限)。

### ◇-7 模型解析注释与实现的次序有出入(代码内部)

- 注释:`cron/scheduler.py:3201-3203`
  ```python
          # Model resolution precedence: per-job override > cron.model (the
          # cron-fleet default) > HERMES_MODEL env > config.yaml ``model:``
  ```
- 实现:`:3207` 先 `model = job.get("model") or os.getenv("HERMES_MODEL") or ""`,
  然后 `:3245-3249` 在 `not job.get("model")` 时用 `_cron_default_model` **覆盖**。
  所以 `cron.model` 实际上也压过 `HERMES_MODEL`,与注释里"cron.model > HERMES_MODEL"一致;
  但 3207 那行单独看会让人以为 env 已经定案。属于**注释可读性/实现顺序**的小坑,
  不是行为 bug——记下以免重实现时照抄 3207 的形状而漏掉 3245 的覆盖。

---

## 7. issue 溯源(切片内出现的编号 + 因果)

### scheduler.py:2200-4428

| issue | 行 | 因果经过 |
|---|---|---|
| nanoclaw #1232 | 2436 | 唤醒闸门约定的来源:pre-check 脚本 stdout 最后一行是 `{"wakeAgent": false}` 就整轮跳过 agent。 |
| #3968 | 2675 | 创建期只扫用户 prompt;skill 内容运行时从磁盘加载从没被扫过 → 恶意 skill 的注入载荷在"非交互自动批准"的 cron 里畅通。修:组装后再扫,双档模式。 |
| #4219 | 3510 | cron 作业从来看不到 MCP 工具(只有 gateway/CLI 启动时调 `discover_mcp_tools()`)。修:`run_job` 里也调一次,幂等,失败非致命。 |
| #8585 | 4076 | agent 跑完但 `final_response` 为空,`last_status` 却记 "ok"。修:空回答记软失败。 |
| #10200 | 3893/4003/4017/4070 | 每次 cron run 造一个一次性 agent,不 close 就漏 fd,网关每 N 分钟 tick 一次直到 EMFILE("too many open files")。修:`finally` 里 `agent.close()` + 收割失效异步 client,并保证异常路径也拆。 |
| #17855 | 3703 | `run_agent` 在重试耗尽/模型中止时置 `failed=True` 并把错误塞进 `final_response`;cron 会把它当正常回复投出去且记 "ok"。修:显式抛。 |
| #23979 | 3262 | 模型解析全空时以空串打到 provider,得到一个不可读的 400。修:提前抛带诊断的 RuntimeError。 |
| #33465 | 3179 | 启动时已应用外部 secret 并把 HERMES_HOME 记进 `_APPLIED_HOMES`;cron 每轮朴素 reload 只会重新套上 .env 里的占位符,不会重解 Bitwarden/BSM 的真值 → cron 作业一直 401。修:先 `reset_secret_source_cache()` 再 `load_hermes_dotenv()`。 |
| #33612 | 4201 | 网关 ticker 每 60s 调 `tick(verbose=False)`,空转 tick 也会掉进 `load_config()`。修:无 due 作业时直接短路(但保留 MCP 孤儿清扫)。 |
| #34452 | 3731/3737 | 轮次完成解释器把空回合替换成 "⚠️ No reply: …" 字符串给交互界面看;在 cron 里这把"本来静默"的空轮变成了一条投递出去的警告(Manfredi 的 Telegram 症状)。修:用同一个格式化器重算文本做逐字比对,命中就当空。 |
| #38758 | 3949 | tick 执行中途被杀(kill/OOM/segfault/硬超时),重启后有限次 one-shot 会被无限重放。修:副作用发生前先 `claim_dispatch` 落盘。 |
| #44585 | 3211/3417/3483 | 未 pin provider/model 的作业跟随全局默认;默认切到付费 provider 或付费模型后,作业每 tick 都在真花钱——"$7.73 事故"同时涉及 provider 和 model 两个轴。修:创建时对每个未 pin 轴快照,开火时对比,漂移就跳过本轮、零付费调用、投一条要求显式 pin 的告警。 |
| #46917 / #51438 | 4050-4051 | 旧的 `SILENT_MARKER in text.upper()` 子串判定:一边漏掉模型丢了方括号的裸 `SILENT`/`NO_REPLY`,一边把句中引用了 "[SILENT]" 的真实报告整段吞掉。修:换成 `_is_cron_silence_response` → `gateway.response_filters` 的共享匹配器。 |
| #50535 / #50536 / #50537 | 3847-3865 | cron 会话标题三连:必须在 `end_session()`/`close()` 之前写(否则 close 撞上在飞的标题写入,#50536);要去重(#50537);任何异常路径都不能留空标题(#50535,兜底到 `cron <job_id> <后6位>`)。 |
| #53027 / #63142 | 3090 | cron 回合结束后收不到异步委派的完成事件;更糟的是 `get_current_session_key()` 会退回环境里的 `HERMES_SESSION_KEY`,把 cron 子 agent 的输出路由进一个无关用户聊天。修:声明 channel 为 stateless(`async_delivery=False`),让 `delegate_task` 走同步内联路径,结果在本回合内返回。 |
| #55924 / #58720 | 4284/2790/3991/3897 | 两件事:(a) tick 与网关拆卸赛跑,解释器收尾时 `pool.submit` 抛 "cannot schedule new futures after interpreter shutdown" 把整个 tick 打崩 → 改为干净跳过;(b) `run_job` 的 `finally` 在投递之前就把 agent 的异步 client 拆了,投递跑在死客户端上 → 改为把 agent 交回调用方,投递完再拆。 |
| #60432 | 4025 | 网关关机时 `process_registry.kill_all()` 把 cron 作业的工具子进程杀掉,但 agent 线程还活着,会用被截断的工具输出编出一段"看起来很像样"的 final_response。修:关机路径打 `_interrupted_job_ids` 标记,`run_one_job` 投递前 peek(4031)、记账前 consume(4081)。 |
| #62002 | 3581 | one-shot 的 run_claim TTL 本意是"死主检测";没有心跳时,一次合法地跑超时的运行(流卡住、笔记本睡眠)和一个死 tick 无法区分,别的进程会重派发,`get_due_jobs` 还会把 job 记录从活运行下面陈旧移除。修:监控循环里定期续租。 |
| #69396 | 2244/2327/2829/3065/3120 | cron 作业里的 `os.chdir()` 是进程级副作用,会泄进并发的 gateway 会话。修:脚本用 `subprocess(cwd=...)`,agent 侧用 `_SESSION_CWD` ContextVar(经 `set_session_vars(cwd=...)`),`TERMINAL_CWD` env 用读写锁串行化。 |
| #73973 | 4101 | `run_job` 的内部处理器在拆完 agent 后重抛 `CancelledError`/`KeyboardInterrupt`/`SystemExit`,这些都不是 `Exception` 子类;逃出去就没人写 `mark_job_run(False)`,而 `claim_dispatch()` 已经消耗了 `repeat.completed` → 有限 one-shot 卡在 "scheduled",直到 run-claim TTL 过期被派发上限守卫无声无息地删掉。修:改捕 `BaseException`,先记账再决定是否重抛。 |

### scheduler_provider.py

| issue | 行 | 因果 |
|---|---|---|
| #32612 | 240/257 | ticker 线程被 provider SDK / agent 重试路径抛出的 `SystemExit` 静默杀死。修:捕 `BaseException`;并加"活着 vs. 成功"两个心跳标记。 |
| #32895 | 257 | 与上同组:区分"活着但每 tick 都失败"和"真在开火"。 |
| #68483 | 252-253 | 一个被 root 改写过的 `jobs.json` 把 ticker 的 uid 锁在外面,~14 小时没人发现,原因埋在 gateway 日志里。修:把失败原因和心跳标记一起持久化,让另一个进程里的 `hermes cron status/list` 能直接显示。 |
| #69377 | 200-202 | 开了 `multiplex_profiles` 时只有进程级 HERMES_HOME(默认 profile)被 tick,次级 profile 的 cron store 没有 ticker 认领——作业显示 "scheduled" 且 `next_run_at` 合法却永不执行。修:`_start_multiplex` 逐 profile 套 home override + cron store。 |

### lifecycle_guard.py

| issue | 行 | 因果 |
|---|---|---|
| #30719 | 1/563 | 本模块存在的理由:agent 排一个 `hermes gateway restart` 的 cron → 开火杀网关 → launchd KeepAlive / systemd Restart= 复活 → auto-resume 捡回那个会话 → 重跑同一段逻辑 → 每 ~10 秒一次的 SIGTERM-重生死循环,只能手工打断。 |
| #62891 | 71-74 / 90 / 160-163 | 两次复现:(1) 直接 restart/kill 被拦后,改用 `launchctl submit -l ai.hermes.gateway-<后缀> -- <helper>` 把重启洗成一个新的 KeepAlive 作业;(2) 换成中性 label(`ai.hermes.svc-reload-tmp`)绕开任何锚 label 的正则。修:分别加 label 锚定分支 + label 无关的执行感知 `submit|bootstrap` 检测;顺带折叠 shell 续行(报告里的命令就是多行 `\` 写法)。 |
| #76762 | 187 / 313-327 / 390 | 递归扫描把一个二进制(ELF/Mach-O/PE)的解码内容当 shell 脚本 tokenize,机器码被切成含 NUL 的伪路径,`Path.resolve` 抛 `ValueError: embedded null byte` 把守卫本身打崩。确立契约:"a guarded path must never crash the guard"。修:首块含 NUL 一律当"没东西可扫";超 1 MiB fail closed。 |
| #77131 | 262-264 / 545-548 | Python 源码里的 `Path.home() / ".hermes"`——pathlib 的 `/` 运算符——被当成可执行 token,解析到文件系统根目录,过不了常规文件检查,于是**每一个无辜的 .py cron 脚本都被硬拦**。修:跳过纯分隔符 token;并且 `.py` 脚本整体跳过引用脚本遍历(只跑直接正则)。 |
| #77703 | 187 / 302-306 / 320-325 / 341 | 远程/本地读回的二进制字节进入递归,产生 NUL 路径。修:本地与远程读取统一"NUL 优先判定为二进制、跳过"。 |
| #77780 / #78256 | 188 / 441-443 | 守卫崩溃会从 `tools/terminal_tool.py` 冒出去,**直到网关重启为止,每一条终端命令都用不了**——比给出任何一个错误结论都糟。修:在边界(而非逐 syscall)兜底,walk 失败就退回纯字符串直扫的结论。 |

---

## 8. 测试(行为规格参照)

本轮实际运行(`HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh ...`),全绿:

```
tests/cron/test_scheduler_provider.py     20 passed
tests/cron/test_run_one_job.py             3 passed
tests/cron/test_cron_no_agent.py           6 passed
tests/hermes_cli/test_gateway_restart_loop.py   92 passed
tests/cron/test_cron_script.py            22 passed
tests/cron/test_shutdown_interrupt.py     14 passed
tests/cron/test_scheduler_shutdown_guard.py      7 passed
```

### 与本切片对应的测试文件

| 文件 | 覆盖的机制 |
|---|---|
| `tests/cron/test_scheduler_provider.py` | ABC 抽象性(`test_cronscheduler_is_abstract`:107)、**增长必须是加法**(`test_abc_growth_stays_additive`:116)、内置 tick+stop(:132)、默认 `cron.provider` 为空(:163)、未知 provider 回退(:182/:207)、`fire_due` 默认先 claim 再跑(:240)、失败 tick 记 liveness 不记 success(:259)、心跳往返(:283)、多 profile 每轮各 tick 一次(:366) |
| `tests/cron/test_run_one_job.py` | tick 与 `run_one_job` 的调用序(:44/:57)、多 profile 下装 secret scope(:69) |
| `tests/cron/test_cron_no_agent.py` | `no_agent` 四条语义 |
| `tests/cron/test_cron_script.py` | 脚本路径监牢、超时、bash/python 选择、脱敏 |
| `tests/cron/test_script_claim_heartbeat.py` | `_run_job_script_with_claim_heartbeat`(#62002) |
| `tests/cron/test_cron_inactivity_timeout.py` | `HERMES_CRON_TIMEOUT` 空闲超时 |
| `tests/cron/test_sessiondb_init_hang.py` | SessionDB 初始化超时(2926-2978) |
| `tests/cron/test_cron_workdir.py` / `test_terminal_cwd_lock.py` | workdir 与 `_terminal_cwd_lock`(#69396) |
| `tests/cron/test_cron_prompt_injection_skill.py` | `_scan_assembled_cron_prompt` 双档(#3968) |
| `tests/cron/test_cron_provider_pin.py` | provider/model pin 与漂移守卫(#44585) |
| `tests/cron/test_cron_context_from.py` | `context_from` 注入 |
| `tests/cron/test_shutdown_interrupt.py` / `test_scheduler_shutdown_guard.py` | `mark_running_jobs_interrupted`、解释器收尾跳过(#60432/#58720) |
| `tests/cron/test_parallel_pool.py` | 并行/顺序双池 |
| `tests/cron/test_execution_ledger.py` | execution 账本 + Chronos provider 的 recovery(:249-251) |
| `tests/cron/test_jobs_changed_notify.py` | `_notify_provider_jobs_changed` |
| `tests/cron/test_idle_tick_config_skip.py` | 空转 tick 短路(#33612) |
| `tests/cron/test_ticker_stall_60703.py` | ticker 停摆检测 |
| `tests/cron/test_scheduler_cron_session_isolation.py` | ContextVar 隔离(3039-3100) |
| `tests/cron/test_cron_kanban_env_isolation.py` | `enter_non_dispatcher_owned_context`(3167) |
| `tests/cron/test_scheduler_mcp_init.py` | MCP 初始化(#4219) |
| `tests/hermes_cli/test_gateway_restart_loop.py` | **lifecycle_guard 的主规格**,92 条:正则四分支正/反例(:22-107)、`check_gateway_lifecycle` 直测(:565-680)、引用脚本递归(:690-762) |
| `tests/gateway/test_cron_fire_webhook.py` | `/api/cron/fire` + `resolve_cron_scheduler().fire_due` |
| `tests/gateway/test_cron_shutdown_drain.py` | drain 对在飞 cron 的可见性(#60432) |
| `tests/tools/test_cronjob_run_immediate.py` | `cronjob action=run` → `run_one_job` |

---

## 9. 重实现要点(造自己的 harness 时抄什么)

1. **把"何时触发"和"触发意味着什么"切成两个轴。** 触发器可换(进程内轮询 / 外部托管 webhook),
   执行+投递必须是**唯一一份共享代码**。hermes 的做法是把整个
   "execute → save → deliver → mark"抽成 `run_one_job`(`scheduler.py:3930`),
   provider 的 `fire_due` 默认实现直接调它(`scheduler_provider.py:113`)。
   否则每加一个 provider 就复制一遍正确性。

2. **回退必须落在核心里,不能落在插件里。** `InProcessCronScheduler` 定义在
   `cron/scheduler_provider.py` 而不是 `plugins/`,四条失败路径全部回退到它——
   "cron 永不失去触发器"。

3. **at-most-once 要分三层做,每层解决不同的死法:**
   - 进程内:`_running_job_ids` 内存集合(同进程重复派发);
   - 单机跨进程:tick 的 flock + **执行前**批量前推 `next_run_at`;
   - 多机:store 层 CAS(`claim_job_for_fire`)+ 副作用前的 `claim_dispatch`。
   再加**长运行续租**(`heartbeat_run_claim`),否则"claim 过期"既可能是死主也可能是慢活。

4. **超时要按"空闲"而不是"墙钟"算。** agent 回合可以合法跑几小时,只要还在调工具/收 token。
   `run_job` 的 5s 轮询 + `get_activity_summary()` 是可复用的骨架(`:3580`/`:3638-3656`)。
   顺便:轮询循环还是心跳续租的自然挂载点。

5. **"agent 说它失败了"必须比"函数没抛异常"权重高。** `:3712` 这一行是 cron 与交互式
   surface 语义分岔的关键:交互式可以把错误文本显示给人看,自动化不能把它当成结果投出去。

6. **静默要有显式协议,而且要能容错。** prompt 里写死 `[SILENT]` 契约(`:2559-2570`),
   匹配侧宽容到裸 token 和首/末行,但**句中出现算真内容**。
   把匹配器抽成共享函数(`gateway.response_filters`)让 cron 和 webhook 两条自动化链路同规格。

7. **投递失败不等于运行失败,要分开记账。** `mark_job_run(..., delivery_error=...)`
   与 `finish_execution(..., delivery_outcome=...)` 四态(delivered / suppressed /
   not_configured / failed)是很实用的划分(`:4083-4097`)。

8. **live 通道超时时,必须能区分"已上线"和"还没发出"。** `future.cancel()` 的返回值就是这个信号
   (`:1852`)。区分不出来只能二选一:要么重复,要么静默丢消息。

9. **注入扫描要按"内容来源"选强度,不是按"配置形状"。** 强档给用户直写的小指令 prompt,
   弱档给运行时加载的 skill / 脚本输出;弱档触发时仍对**原始用户 prompt** 跑强档
   (`:2716-2719`)。并且弱档对不可见 unicode 是**清洗而非拦截**——一个零宽空格不该永久废掉作业。

10. **钱包保险要 fail-closed 且带"逃生门"。** 漂移守卫(#44585)不是禁止变更,
    是要求**显式 pin**;凭据外泄兜底(F8)只在 job 真的设了 base_url 时才因验证器故障而拒跑,
    没设 override 的绝大多数作业不会被无关错误卡死(`:2751-2768`)。这两处的边界划法值得抄。

11. **守卫的可用性 > 守卫的精确性。** lifecycle_guard 的核心教训:一个会崩的守卫比一个偶尔判错的
    守卫糟得多——它会把上游的整条工具链一起拖下水(#77780/#78256)。
    正确做法是在**摄取边界**做一次总的输入净化(`_expand_candidate_path`),
    在**函数边界**做一次 total 封装(`contains_gateway_lifecycle_command_or_referenced_script`),
    而不是逐 syscall 打补丁。

12. **命令检测要"执行感知",不要纯正则。** `contains_launchctl_submit_command`
    先 shlex 切段、跳过 env 赋值、再取首 token 的 basename——引号里的文本不误报,
    中性 label 也绕不开。纯正则只能锚定字面量,而字面量是攻击者可选的。

13. **递归展开要有三个上限。** 深度(8,超限判 unsafe)、单文件字节数(1 MiB,超限判 unsafe)、
    访问集合(防环)。而"二进制"要单独判成"没东西可扫"而不是 unsafe,否则用户跑任何
    编译产物都会被拦。

14. **别忘了写路径(update)。** hermes 的 create-time 守卫是完整的,但 update 路径漏了
    (◇-2,已实证)。安全检查应该挂在**数据落库的那一层**(`update_job` / `create_job` 共同的
    normalize 之后),而不是挂在某一个入口函数上。

15. **给自动化留一条"从进程外能看见"的健康信号。** ticker 心跳(liveness)+ 成功标记 + 失败原因
    三件套(`scheduler_provider.py:248-260`)让另一个进程里的 `hermes cron status`
    能区分"线程死了""每 tick 都炸""真在开火"——#68483 那 14 小时的教训。
