# r7c-raw-cron-sched-a · cron/scheduler.py 第 1–2200 行

> 基线 `863e31318553cda8ad61df681d08175364d4164b`。全文 4428 行，本笔记负责 **1–2200 行**（已逐段通读到 2298，
> 为读完 `_run_job_script` 头部）。凡对代码行为的断言均带 `路径:行号 @ 863e313` + 代码原文。
>
> **重要范围说明**：`tick()` 在 **4151** 行、`run_job()` 在 **2779** 行、`run_one_job()` 在 **3930** 行 ——
> 都在切片之外（见 `cron/scheduler.py:4151,2779,3930`）。任务要求回答"触发循环 / 数据模型 / 时间语义"，
> 这些机制的主体不在本切片，因此凡涉及它们我都标注 **【跨切片参照】** 并同样给出精确行号证据，
> 但不声称已逐行精读那些区间。

---

## 0. 本切片一句话

第 1–2200 行不是"调度"，而是 **cron 的投递层 + 进程级并发原语**：一半篇幅（1467–2110）是
`_deliver_result` 这一个函数——把 agent 的一段文本可靠地送进十几个 IM 平台的正确会话/话题里；
另一半是让并发 cron job 不互相踩踏的基础设施（读写锁、两个线程池、in-flight 集合、解释器关停探测）。

---

## 1. 结构总览

| 行区间 | 内容 | 一句话 |
|---|---|---|
| 1–57 | 模块 docstring + import | 声明"网关每 60s 从后台线程调 `tick()`"、文件锁路径；`sys.path.insert` 兜底 |
| 60–96 | `_set_cron_session_title` | cron 会话收尾时保证有唯一非空标题（#50535/50536/50537） |
| 99–149 | `_summarize_cron_failure_for_delivery` | 失败原因压成一行再进聊天，防 provider JSON 刷屏 |
| 152–162 | `CronPromptInjectionBlocked` | 组装后 prompt 触发注入扫描时抛（#3968） |
| 165–251 | 三个 toolset 解析器 | cron 永久禁用 4 个 toolset；per-job 白名单 + MCP 合流；平台级 `hermes tools` 兜底 |
| 253–289 | 平台常量表 | `_KNOWN_DELIVERY_PLATFORMS` / `_HOME_TARGET_ENV_VARS` / legacy 别名 |
| 291–325 | jobs/executions 导入 + 静默判定 | `[SILENT]` 语义**委托** `gateway.response_filters` 共享 |
| 327–430 | 线程池全局态 + 中断标志 | `_running_job_ids` / `_interrupted_job_ids` / `_running_lock` |
| 433–493 | `_ReadWriteLock` + `_terminal_cwd_lock` | 写者优先读写锁，保护 `os.environ["TERMINAL_CWD"]` |
| 496–539 | 两个持久线程池 + atexit | 并行池（可配 max_workers）+ 单线程顺序池 |
| 542–571 | `_interpreter_shutting_down` | 关停竞态探测（#58720/#55924） |
| 574–594 | `_get_hermes_home` / `_get_lock_paths` | 调用时解析，保证 profile 隔离（#4707） |
| 597–751 | origin 解析 + 投递镜像 | `_resolve_origin`（#18722）、`_cron_mirror_delivery_enabled`、`_maybe_mirror_cron_delivery` |
| 754–971 | 可续聊表面（D1/D2/D6） | 开专属 thread / 播种 thread 会话 / 播种扁平频道会话 |
| 974–1097 | 平台注册表查询 | 插件平台的 `cron_deliver_env_var` 贯通 |
| 1100–1325 | 投递目标解析 | `deliver` 串 → 具体 `{platform, chat_id, thread_id}` 列表 |
| 1328–1464 | 媒体与确认 | 扩展名路由、`_confirm_adapter_delivery`（#47056）、Telegram DM-topic 探测（#22773/#52060） |
| **1467–2110** | **`_deliver_result`** | 本切片的重心：live adapter 优先 → standalone 兜底 → 多目标各自容错 |
| 2113–2207 | 脚本超时 + Windows 解释器 | `_SCRIPT_TIMEOUT` 三层链、uv venv 绕过 launcher |
| 2210–2298+ | `_run_job_script` 头部 | 脚本必须落在 `HERMES_HOME/scripts/`，按扩展名选解释器 |

---

## 2. 数据模型与持久化

### 2.1 本切片能看到的：调度器不定义 schema，只消费 dict

切片内没有任何 job 的 schema 定义，只有对 `job: dict` 的**字段读取**。从本切片实际读到的字段可以反推
job 记录必须包含：

`cron/scheduler.py:106`（失败摘要）：
```python
    job_name = job.get("name") or job.get("id") or "cron job"
```

切片内被读到的字段全集：`id`、`name`、`enabled_toolsets`(240)、`origin`(609/984)、
`attach_to_session`(640)、`deliver`(1299)、`workdir`（分区在 4364，跨切片）。

### 2.2 真正的持久化【跨切片参照 cron/jobs.py】

存储是 **JSON 文件，不是 SQLite**：

`cron/jobs.py:84`：
```python
CRON_DIR = HERMES_DIR / "cron"
JOBS_FILE = CRON_DIR / "jobs.json"
```

完整 job 记录由 `create_job` 一次性构造，`cron/jobs.py:1391-1428`：
```python
    job = {
        "id": job_id,
        "name": name or label_source[:50].strip(),
        "prompt": prompt_text,
        "skills": normalized_skills,
        "skill": normalized_skills[0] if normalized_skills else None,
        "model": normalized_model,
        "provider": normalized_provider,
        "provider_snapshot": provider_snapshot,
        "model_snapshot": model_snapshot,
        "base_url": normalized_base_url,
        "script": normalized_script,
        "no_agent": normalized_no_agent,
        "context_from": context_from,
        "schedule": parsed_schedule,
        "schedule_display": parsed_schedule.get("display", schedule),
        "repeat": {
            "times": repeat,  # None = forever
            "completed": 0
        },
        "enabled": True,
        "state": "scheduled",
        "paused_at": None,
        "paused_reason": None,
        "created_at": now,
        "next_run_at": next_run_at,
        "last_run_at": None,
        "last_status": None,
        "last_error": None,
        "last_delivery_error": None,
        # Delivery configuration
        "deliver": deliver,
        "origin": origin,  # Tracks where job was created for "origin" delivery
        "enabled_toolsets": normalized_toolsets,
        "workdir": normalized_workdir,
    }
```

**另有一个 SQLite**，但它不是 job 存储，是"执行流水账"：`cron/executions.py:20`
```python
EXECUTIONS_FILE = get_hermes_home().resolve() / "cron" / "executions.db"
```
schema 在 `cron/executions.py:38-53`，状态枚举 `('claimed','running','completed','failed','unknown')`，
docstring 第 3 行明确写"**it is not a retry queue**"（`cron/executions.py:3`）。

**设计取舍**：job 用 JSON 文件（可手改、易看、原子 rename 写入），执行历史用 SQLite（要索引、要 1000 条上限
裁剪、要 WAL）。代价是 jobs.json 极易被手工/迁移脚本写坏 —— 这也是 `_get_due_jobs_locked` 里堆了 4 段
"修复畸形记录"防御代码的直接原因（`cron/jobs.py:2189-2268`）。

---

## 3. 时间语义（时区 / DST / 错过的触发）

### 3.1 cron 表达式：用 croniter，惰性 import

`cron/jobs.py:52-66`（惰性理由是省 15ms 正则编译）：
```python
def _ensure_croniter() -> bool:
    """Import croniter on first use; honor a pre-set HAS_CRONITER override."""
```
依赖钉死版本：`pyproject.toml:59`
```
  "croniter==6.0.0",
```

四种 schedule 由 `parse_schedule` 解析（`cron/jobs.py:564`）：`every X` → interval、5/6 段 cron 表达式 →
cron、含 `T` 或 `YYYY-MM-DD` → once(ISO)、`30m/2h/1d` → once(相对)。

### 3.2 时区：全局单一配置时区，不支持 per-job 时区

`hermes_time.py:122-134`：
```python
def now() -> datetime:
    tz = get_timezone()
    if tz is not None:
        return datetime.now(tz)
    # No timezone configured — use server-local (still tz-aware)
    return datetime.now().astimezone()
```
job 记录里**没有 timezone 字段**（见 §2.2 的完整 dict）。所有 job 共用 `HERMES_TIMEZONE`。

朴素（naive）时间戳的锚定规则有两套，注意区别：
- **新建时**锚到配置时区（`cron/jobs.py:632-634`，#51021）；
- **读旧值时**锚到系统本地时区再换算（`cron/jobs.py:676-680` `_ensure_aware`）。

### 3.3 DST：无显式处理，行为完全由 croniter 决定 —— 我实测了

代码里全仓 cron 目录只有 **两处** 提到 DST，且都在同一段注释里（`cron/jobs.py:2370,2374`），没有任何
`fold=` 处理。因此答案必须实测。用基线 venv 跑 `compute_next_run` 链式推进（America/New_York）：

```
# expr "30 2 * * *"（每天 2:30），秋季回拨 2026-11-01
last 2026-10-31T02:30:00-04:00 -> next 2026-11-01T03:30:00-05:00   ← 只跑 1 次，但落在 03:30
last 2026-11-01T03:30:00-05:00 -> next 2026-11-02T02:30:00-05:00   ← 次日自动归位

# expr "30 1 * * *"（每天 1:30，回拨当天本地出现两次 1:30）
last 2026-10-31T01:30:00-04:00 -> next 2026-11-01T01:30:00-04:00   ← 只命中第一次 1:30（EDT）
last 2026-11-01T01:30:00-04:00 -> next 2026-11-02T02:30:00-05:00   ← 次日漂到 02:30（晚 1 小时）
last 2026-11-02T02:30:00-05:00 -> next 2026-11-03T01:30:00-05:00   ← 第三天才归位

# 春季跳变 2026-03-08（本地 02:00→03:00 不存在）
last 2026-03-07T02:30:00-05:00 -> next 2026-03-08T02:30:00-05:00   ← 不存在的墙钟时间，绝对时刻 = 03:30 EDT
```

**结论（直接回答任务问题）**：
1. **"每天 2:30" 在时钟回拨那天跑 1 次，不是 2 次，也不是 0 次** —— 但实际落在本地 **03:30**（晚一小时）。
2. 不会重复触发的根因不在 cron 代码，而在 `next_run_at` 存的是**绝对时刻**，且 croniter 从 `last_run_at`
   严格向前推进（`cron/jobs.py:817-828`）：
   ```python
        # Use last_run_at as the croniter base when available, consistent
        # with interval jobs.  This ensures that after a crash/restart,
        # the next run is anchored to the actual last execution time
        # rather than to an arbitrary restart time.
        base_time = now
        if last_run_at:
            try:
                base_time = _ensure_aware(datetime.fromisoformat(last_run_at))
   ```
3. 跳变次日会有**一次一小时的漂移**再自愈（croniter 6.0.0 的行为，代码未纠正）。
4. 春季跳变时 croniter 返回一个**本地不存在的墙钟时间**，被当作绝对时刻使用 → 实际晚 1 小时执行。

### 3.4 时区变更修复分支：作者自己承认会与 DST 撞车

`cron/jobs.py:2369-2388`：
```python
            # TRADE-OFF: this cannot distinguish a config/host TZ migration from a
            # legitimate DST offset change. A DST boundary that satisfies all four
            # conditions will recompute (and thus SKIP the pending occurrence, no
            # catch-up) rather than fire it. Accepted: ...
            # rare relative to the double-fire bug this prevents (#28934).
            if (
                kind == "cron"
                and next_run_dt <= now
                and _timezone_offset_mismatch(raw_next_run_dt, now)
                and _stored_wall_clock_is_future(raw_next_run_dt, now)
            ):
```
即：改了 `HERMES_TIMEZONE` 之后，一个"看起来已经到点、但墙钟时间还没到"的 cron job 会被**重算并跳过**
本次触发。这是明写的取舍。

### 3.5 错过的触发：collapse 成一次，不 catch-up 队列

`cron/jobs.py:2158-2169`（`get_due_jobs` docstring）：
```
    For recurring jobs (cron/interval), if the scheduled time is stale (more
    than one period in the past, e.g. because the gateway was down OR because a
    long-running previous execution overran the interval), the accumulated
    missed runs are collapsed — ``next_run_at`` is fast-forwarded to the next
    future occurrence so a backlog does NOT burst-fire on restart — but the job
    still fires ONCE now. This prevents the perpetual-defer loop (#33315) ...
```
宽限窗口 = 周期的一半，钳在 120s–7200s（`cron/jobs.py:745-760`）：
```python
    MIN_GRACE = 120
    MAX_GRACE = 7200  # 2 hours
```
一次性 job 单独走 120s 固定宽限（`cron/jobs.py:116` `ONESHOT_GRACE_SECONDS = 120`）。

**策略总结**：不是 catch-up、不是 skip，而是 **"合并成恰好一次 + 快进 next_run_at"**。
docstring 还提醒：这一次 catch-up 会消耗 `repeat.times` 的一个名额（`cron/jobs.py:2166-2167`）。

---

## 4. 触发循环

### 4.1 是网关内的一个后台**线程**，不是独立进程，也不是 asyncio task

`gateway/run.py:26914-26921`：
```python
    cron_thread = threading.Thread(
        target=cron_provider.start,
        args=(cron_stop,),
        kwargs=cron_start_kwargs,
        daemon=True,
        name="cron-scheduler",
    )
    cron_thread.start()
```
选哪个 provider 走插件解析（`gateway/run.py:26875-26877`）：
```python
    from cron.scheduler_provider import InProcessCronScheduler, resolve_cron_scheduler
    cron_stop = threading.Event()
    cron_provider = resolve_cron_scheduler()
```

### 4.2 tick 周期：绝对间隔轮询，不是 sleep-to-next

`cron/scheduler_provider.py:225-238`（内置 provider 的循环体）：
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
```
末尾：`cron/scheduler_provider.py:261`
```python
            stop_event.wait(interval)
```
`interval` 默认 60（`cron/scheduler_provider.py:182`）。**是 `wait(60)` 的固定轮询**，不计算"到下一次触发
还有多久"。代价：最坏迟到 60s；收益：实现极简、崩溃/改表都不用重排定时器。

`BaseException` 而非 `Exception` 兜底（`cron/scheduler_provider.py:239`），理由写明是 provider SDK 抛
`SystemExit` 会静默杀死 ticker 线程（#32612）。多 profile 时另有一份并行的多路复用循环
（`cron/scheduler_provider.py:315-357`，#69377）。

### 4.3 "到点了"怎么变成一次 agent 回合

`tick()` → `_submit_with_guard` → 线程池 → `_process_job` → `run_one_job(job, adapters, loop)`
（`cron/scheduler.py:4253-4258`）：
```python
        def _process_job(job: dict) -> bool:
            """Run one due job end-to-end. Thin wrapper around the shared
            module-level ``run_one_job`` so ``tick`` and external providers
            (Chronos ``fire_due``) use the identical execute→save→deliver→mark
            body."""
            return run_one_job(job, adapters=adapters, loop=loop, verbose=verbose)
```
**关键顺序**：`next_run_at` 是在**任何执行开始之前**、还持着文件锁时就批量推进的
（`cron/scheduler.py:4218-4223`）：
```python
        # Advance next_run_at for all recurring jobs FIRST, under the file lock,
        # before any execution begins.  This preserves at-most-once semantics.
        # ...
        advance_next_runs([job["id"] for job in due_jobs])
```

### 4.4 文件锁：跨进程，抢不到就直接返回 0

`cron/scheduler.py:4179-4190`：
```python
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
路径在本切片解析（`cron/scheduler.py:590-594`）：
```python
def _get_lock_paths() -> tuple[Path, Path]:
    """Resolve cron lock paths at call time so profile/env changes are honored."""
    hermes_home = _get_hermes_home()
    lock_dir = hermes_home / "cron"
    return lock_dir, lock_dir / ".tick.lock"
```
**锁的持有时长取决于 `sync`**：`sync=False`（网关 ticker）时 tick 派发完就返回、`finally` 立刻放锁
（`cron/scheduler.py:4413-4423`），job 在池里继续跑；`sync=True`（测试/`python cron/scheduler.py`）时
`as_completed` 会一直等（`cron/scheduler.py:4377-4387`），锁被握到所有 job 跑完。
——**这意味着"文件锁保证不重复执行"只在同步模式下成立**；网关模式下真正防重入的是
`_running_job_ids`（§5.2）和 one-shot 的 `run_claim`（§5.3），文件锁只防"同时扫同一批 due job"。

模块自带独立入口（`cron/scheduler.py:4427-4429`）：
```python
if __name__ == "__main__":
    tick(verbose=True)
```

---

## 5. 并发与互斥

本切片是这一节的主场。四层互斥，各管一件事：

### 5.1 跨进程：文件锁 `.tick.lock`
见 §4.4。管的是"两个 tick 不要同时扫同一批 due job"。

### 5.2 同进程同 job：`_running_job_ids` in-flight 集合
`cron/scheduler.py:334-335`：
```python
_running_job_ids: set = set()
_running_lock = threading.Lock()
```
派发处（跨切片 `cron/scheduler.py:4291-4295`）：
```python
            with _running_lock:
                if job_id in _running_job_ids:
                    logger.info("Job '%s' already running — skipping", job.get("name", job_id))
                    return None
                _running_job_ids.add(job_id)
```
**直接回答"上一次没跑完、下一次到点了怎么办"：跳过本次，不排队、不并发。** 释放在 worker 的 finally
（`cron/scheduler.py:4302-4307`）。成员期覆盖整个 job 生命周期，不只是派发瞬间 ——
本切片 `get_running_job_ids` 的 docstring 明说（`cron/scheduler.py:350-353`）：
```
    A job ID is a member from the moment ``_submit_with_guard`` dispatches
    it onto the parallel/sequential pool until ``_process_job`` returns —
    i.e. for the job's *entire* run, tool calls included, not just the
    ticker's dispatch instant.
```

### 5.3 跨进程同 job（仅一次性 job）：`run_claim` 声明【跨切片】
`cron/jobs.py:2303-2312` 用 `run_claim` + TTL 拦截；future-dated claim 视为过期（#60703）。
心跳续期常量在本切片：`cron/scheduler.py:2116`
```python
_RUN_CLAIM_HEARTBEAT_SECONDS = 60.0
```

### 5.4 环境变量互斥：写者优先读写锁

这是本切片最值得抄的设计。问题：workdir job 会改 **进程全局** 的 `os.environ["TERMINAL_CWD"]`，
而同时跑的无 workdir job 会读到它，命令就跑错目录。

`cron/scheduler.py:440-455`：
```python
class _ReadWriteLock:
    """Writer-preferring readers-writer lock.

    Guards the process-global ``os.environ["TERMINAL_CWD"]`` override that a
    workdir cron job applies for the whole of its agent run.  Workdir jobs are
    writers: they mutate the shared env and need exclusive access.  Workdir-less
    jobs are readers: they only observe ``TERMINAL_CWD`` (indirectly, via the
    terminal / file / code-exec tools), so any number of them may run
    concurrently with each other, but none may run alongside a writer — that is
    exactly what stops a workdir-less job from picking up another job's workdir
    override and running its commands in the wrong directory.

    Writer preference bounds the wait for a workdir job (dispatched on the
    single-thread sequential pool) so a stream of workdir-less readers cannot
    starve it.
    """
```
写者优先靠 `_writers_waiting` 计数实现（`cron/scheduler.py:463-467`）：
```python
    def acquire_read(self) -> None:
        with self._cond:
            while self._writer_active or self._writers_waiting > 0:
                self._cond.wait()
            self._readers += 1
```
实例：`cron/scheduler.py:493` `_terminal_cwd_lock = _ReadWriteLock()`。

**注意这是两层**：单线程顺序池只保证 workdir job 之间不重叠；读写锁才额外挡住并行池里的无 workdir job。
tick 的分区注释说得很清楚（`cron/scheduler.py:4263-4269`）：
```python
        # That alone only keeps workdir jobs from overlapping EACH OTHER;
        # run_job's _terminal_cwd_lock is what additionally stops a concurrently
        # firing workdir-less parallel-pool job from observing the override.
        sequential_jobs = [j for j in due_jobs if (j.get("workdir") or "").strip()]
        parallel_jobs = [j for j in due_jobs if not (j.get("workdir") or "").strip()]
```

### 5.5 两个持久线程池

`cron/scheduler.py:496-507` 并行池（max_workers 变了就重建）、`cron/scheduler.py:510-524` 顺序池
（`max_workers=1`，docstring 明说是为了跨 tick 保序）。两者 `atexit` 统一关（`cron/scheduler.py:539`）。

并发度解析在 tick 里：env `HERMES_CRON_MAX_PARALLEL` > `cron.max_parallel_jobs` > **无上限**
（`cron/scheduler.py:4226-4243`）。默认无上限是个明显的取舍：省了排队，但 20 个 job 同时到点就是 20 个
并发 LLM 会话。

### 5.6 关停期的三段防护（#60432 / #58720）

- `mark_running_jobs_interrupted(reason)`（`cron/scheduler.py:366-400`）：网关杀完工具子进程后，把当时
  所有 in-flight job 标记为中断。**先写标志再写 `last_status`**，注释说明了这个顺序是为了防竞态
  （`cron/scheduler.py:376-380`）：
  ```
      Records the job IDs in ``_interrupted_job_ids`` BEFORE writing
      ``last_status`` so ``run_one_job``'s own eventual completion for the
      same job (racing in its own thread) sees the flag and skips its normal
      write instead of clobbering this one
  ```
  它坦承不做 PID→job_id 关联（`cron/scheduler.py:381-386`），是粗粒度的。
- `_is_interrupted` 只窥视不清（`cron/scheduler.py:403-415`），`_consume_interrupted_flag` 读并清
  （`cron/scheduler.py:418-430`）—— 清除的理由是"周期性 job 每次触发复用同一个 ID"。
- `_interpreter_shutting_down`（`cron/scheduler.py:542-571`）：`sys.is_finalizing()` 或异常文本匹配。
  匹配的是**短前缀**，注释说明 CPython 会吐两种变体（`cron/scheduler.py:563-570`）：
  ```python
        # Match the SHORT prefix deliberately: CPython emits two shutdown
        # variants — "cannot schedule new futures after interpreter shutdown"
        # ... and "cannot schedule new futures after shutdown" (a plain
        # ThreadPoolExecutor). Both are documented in #58720.
        return "cannot schedule new futures" in str(exc).lower()
  ```

---

## 6. ▲/◇ 候选（含 cron-internals.md 逐段对表）

`cron-internals.md` 全文 303 行，我逐段对了。结论：**这份文档整体准确度尚可，但"Job Storage"和
"Tick Cycle"两节是明显的旧版快照**。

### ▲-1 `state: "running"` 是文档里的幽灵状态，代码从不写

- 文档：`website/docs/developer-guide/cron-internals.md:73`
  ```
  | `running` | Currently executing (transient state) |
  ```
  以及伪码 `website/docs/developer-guide/cron-internals.md:91`
  ```
     a. Set state to "running"
  ```
- 代码：全仓 `grep '"state"'` 在 cron/tools/hermes_cli 下的所有写入点是
  `cron/jobs.py:1415`(`"scheduled"`)、`1617`(`"paused"`)、`1641`/`1658`(`"scheduled"`)、
  `1752`/`1785`/`1878`(`"completed"`)、`1769`(`"error"`)、`1787`(`"scheduled"`)。
  **没有任何一处写 `"running"`**；反而有文档没提的 `"error"` 状态（`cron/jobs.py:1769`）。
  "正在跑"这件事记录在别处：进程内 `_running_job_ids`（`cron/scheduler.py:334`）+
  executions.db 的 `status='running'`（`cron/executions.py:47-48`）。

### ▲-2 tick 伪码把 `next_run` 的推进放在执行之后，代码放在执行之前

- 文档：`website/docs/developer-guide/cron-internals.md:96-99`
  ```
     f. Update run_count, compute next_run
     g. If repeat count exhausted → state = "completed"
  ...
    5. Write updated jobs back to jobs.json
  ```
- 代码：`cron/scheduler.py:4213-4218` 在**任何执行开始前**、持锁状态下批量 `advance_next_runs`，
  注释写明理由是 at-most-once。文档的"最后统一写回"也不成立：完成时是 `mark_job_run` 逐 job 写。

### ▲-3 文档的 job 记录示例缺 15 个字段

- 文档：`website/docs/developer-guide/cron-internals.md:38-63` 列了 13 个字段。
- 代码：`cron/jobs.py:1391-1428` 实际 25 个字段（见 §2.2）。文档缺：`skill`、`provider_snapshot`、
  `model_snapshot`、`base_url`、`no_agent`、`context_from`、`schedule_display`、`paused_at`、
  `paused_reason`、`last_error`、`last_delivery_error`、`origin`、`enabled_toolsets`、`workdir`，
  以及运行期才出现的 `attach_to_session`（`cron/jobs.py:1430-1433`）和 `run_claim`。
  其中 `origin`/`workdir`/`enabled_toolsets` 是本切片重度依赖的字段。

### ▲-4 "Cron deliveries are NOT mirrored" 已经不成立（cron-internals 落后于 user-guide）

- 文档 A（开发者卷，绝对口吻）：`website/docs/developer-guide/cron-internals.md:270-272`
  ```
  ### Session Isolation
  Cron deliveries are NOT mirrored into gateway session conversation history.
  ```
- 文档 B（根 AGENTS.md，同样绝对）：`AGENTS.md:1082-1083`
  ```
  Cron deliveries are **not** mirrored into the target gateway session —
  they land in their own cron session with a header/footer frame
  ```
- 代码：`cron/scheduler.py:640-667` 提供 per-job `attach_to_session` + 全局 `cron.mirror_delivery` 开关：
  ```python
    per_job = job.get("attach_to_session")
    if isinstance(per_job, bool):
        return per_job
    try:
        if cfg is None:
            cfg = load_config() or {}
        return bool((cfg.get("cron", {}) or {}).get("mirror_delivery", False))
  ```
  默认关，所以"默认行为"描述没错，但两处文档都写成了不可变的架构不变量。
- **用户卷已经更新**：`website/docs/user-guide/features/cron.md:357-362` 明确文档化了
  `mirror_delivery` 与 `attach_to_session`。所以这是**同仓库内两份文档互相矛盾**，
  开发者卷 + AGENTS.md 落后。

### ▲-5 AGENTS.md 声称支持 `"every monday 9am"`，实际解析失败

- 文档：`AGENTS.md:1061`
  ```
  - "every" phrase: `"every 2h"`, `"every monday 9am"`
  ```
- 代码：`cron/jobs.py:587-589` 把 `every ` 后面整段交给 `parse_duration`，而后者的正则
  （`cron/jobs.py:553`）只认 `^(\d+)\s*(m|h|d…)$`。
- **实测**（基线 venv，`/home/user/hermes-venv/bin/python`）：
  ```
  'every monday 9am' -> ERROR ValueError Invalid duration: 'monday 9am'. Use format like '30m', '2h', or '1d'
  'every 2h'         -> {'kind': 'interval', 'minutes': 120, 'display': 'every 120m'}
  ```
  且没有自然语言预处理层：`tools/cronjob_tools.py:1008` 是唯一调用点，直接调 `parse_schedule`。
  （weekday 名字→数字的映射只存在于 `cron/blueprint_catalog.py:598`，那是蓝图模板，不是 schedule 解析。）

### ▲-6 AGENTS.md 的"3 分钟硬中断"与代码的 600s 不活动超时冲突

- 文档：`AGENTS.md:1073-1074`
  ```
  - **3-minute hard interrupt** on cron sessions — runaway agent loops
    cannot monopolize the scheduler.
  ```
- 代码【跨切片】：`cron/scheduler.py:3562-3578`
  ```python
        # duration is caught and killed.  Default 600s (10 min inactivity);
        # override via HERMES_CRON_TIMEOUT env var.  0 = unlimited.
  ```
  且语义不是"总时长硬上限"而是"**不活动**超时"——只要还在调工具/收流式 token 就可以跑数小时
  （同段注释 `cron/scheduler.py:3560-3561`）。`website/docs/developer-guide/cron-internals.md:216` 对此描述**是对的**
  （"600s of idle time, `0` = unlimited"），所以 AGENTS.md 单方面过时。

### ▲-7 `homeassistant` 被列为"裸名投递到 HA 会话"，实际解析不出目标

- 文档：`website/docs/developer-guide/cron-internals.md:250`
  ```
  | Home Assistant | `homeassistant` or `homeassistant:<conversation>` | Bare name delivers to HA conversation |
  ```
- 代码：`homeassistant` 在 `_KNOWN_DELIVERY_PLATFORMS`（`cron/scheduler.py:258`），
  但 **不在** `_HOME_TARGET_ENV_VARS`（`cron/scheduler.py:264-281` 全表无此键），
  且它的 PlatformEntry 也没注册 `cron_deliver_env_var`
  （`plugins/platforms/homeassistant/adapter.py:585` 处的注册项，全仓
  `grep cron_deliver_env_var` 无 homeassistant 命中）。
  于是 `_resolve_home_env_var("homeassistant")` 返回 `""`（`cron/scheduler.py:1036-1040`），
  `_get_home_target_chat_id` 返回 `""`（`cron/scheduler.py:1045-1047`），
  裸名分支落到 `cron/scheduler.py:1233-1235`：
  ```python
    chat_id = _get_home_target_chat_id(platform_name)
    if not chat_id:
        return None
  ```
  → 无目标。同类问题还有 `webhook`、`wecom_callback`、`yuanbao`（都在 KNOWN 表但无 home env var），
  只是文档没为它们承诺裸名投递。

### ▲-8 `_get_script_timeout` 文档说"三层链"却列了四条

- `website/docs/developer-guide/cron-internals.md:209-214`：`"resolves the limit through a three-layer chain:"` 后面列了 1/2/3/4。
- 代码 `cron/scheduler.py:2119-2149` 确实是四层（module override → env → config → default），
  文档的措辞错在数量词。小，但属于同一段落自相矛盾。

### ◇-1 `whatsapp_cloud` 的 home 映射基本是死配置

`cron/scheduler.py:280`：
```python
    "whatsapp_cloud": "WHATSAPP_CLOUD_HOME_CHANNEL",
```
但 `whatsapp_cloud` **不在** `_KNOWN_DELIVERY_PLATFORMS`（`cron/scheduler.py:255-260`），
`plugins/platforms/` 下也没有 `whatsapp_cloud` 目录（只有 `whatsapp`）。
后果链：
- `cron_delivery_targets()` 会用 `_is_known_delivery_platform` 过滤掉它（`cron/scheduler.py:1127-1128`）；
- `all` 展开会产出它，但随后 `_resolve_single_delivery_target` 的裸名分支在
  `cron/scheduler.py:1231-1232` 判 `_is_known_delivery_platform` 为假 → 丢弃；
- **唯一能命中它的路径**是 `deliver=origin` 且 job 没有 origin 时的 home 兜底循环
  （`cron/scheduler.py:1158-1170`），该循环**没有**调 `_is_known_delivery_platform`。
所以这是个半接线的条目 —— 要么补进 KNOWN 表，要么删。文档两侧都没提 whatsapp_cloud。

### ◇-2 `_KNOWN_DELIVERY_PLATFORMS` 的安全注释与实际校验路径不符

注释（`cron/scheduler.py:253-254`）：
```python
# Valid delivery platforms — used to validate user-supplied platform names
# in cron delivery targets, preventing env var enumeration via crafted names.
```
但 `platform:target` 冒号形式在 `cron/scheduler.py:1173-1214` 全程**不查**这张表，直接构造目标返回。
真正的兜底在 `_deliver_result` 的 `Platform(platform_name.lower())`（`cron/scheduler.py:1587`），
而 `Platform._missing_` 只为已发现的插件平台建动态成员、拒绝任意字符串
（`gateway/config.py:305-322`）。**结论：枚举风险实际被 Platform 枚举挡住了，但注释归因错了地方**，
读注释的人会以为冒号形式也过了这张白名单。

### ◇-3 文档 Key Files 表漏掉 4 个 cron 模块

`website/docs/developer-guide/cron-internals.md:13-19` 只列 5 个文件。实际 `cron/` 下还有
`executions.py`（SQLite 审计账本，本切片在 `cron/scheduler.py:292` 直接导入）、
`lifecycle_guard.py`（拦截"cron 里重启网关"，`cron/jobs.py:1365-1366` 调用，#30719）、
`scheduler_provider.py`（文档正文 108 行提到了，但没进 Key Files 表）、
`blueprint_catalog.py` / `suggestion_catalog.py` / `suggestions.py`。

### ◇-4 文档完全没写"可续聊 cron"（本切片 754–971 + 1630–1998 的一大块）

`_open_continuable_cron_thread`（`cron/scheduler.py:754`）、`_seed_cron_thread_session`（791）、
`_seed_cron_channel_session`（878）、以及 `cron_continuable_surface` 配置键
（`cron/scheduler.py:1643`）在 `cron-internals.md` 中零提及。
用户卷只提了一句"mirror 到 DM session"（`cron.md:373`），没提"开专属 thread"和 `in_channel` 表面。
这是本切片代码量最大的新增机制之一（D1/D2/D6 三个决策点在注释里都有编号）。

### ◇-5 文档没提"组装后 prompt 二次扫描"

`cron.md:804` 只说"scanned … at creation and update time"。
代码有 `CronPromptInjectionBlocked`（`cron/scheduler.py:152-162`）+
`_scan_assembled_cron_prompt`（`cron/scheduler.py:2663`，跨切片），docstring 明说创建期扫描盖不住
运行期加载的 skill 内容（#3968）。这是安全语义上的实质差异，文档缺。

### ◇-6 文档没提 cron 强制禁用的 4 个 toolset 里的 3 个

`website/docs/developer-guide/cron-internals.md:181` 与 `:276` 只说禁用 `cronjob`。代码禁用 4 个（`cron/scheduler.py:180`）：
```python
    disabled = ["cronjob", "messaging", "clarify", "memory"]
```
且会叠加用户 `agent.disabled_toolsets`，理由写明是防 LLM 用 `enabled_toolsets` 绕开策略（#25752，
`cron/scheduler.py:176-178`）。

### ◇-7 `[SILENT]` 的匹配规则比文档宽

- 文档：`website/docs/developer-guide/cron-internals.md:268` 说 "The `[SILENT]` **prefix**"；`cron.md:440` 说 "contains `[SILENT]`"
  —— 两处说法本身就不一致，一个是前缀一个是包含。
- 代码：`cron/scheduler.py:311-325` 委托 `gateway.response_filters.is_autonomous_silence_response`，
  规则是"整条 / 首行 / 末行"，另接受无括号的 `SILENT` / `NO_REPLY` / `NO REPLY`（#51438、#46917），
  且**句中出现不算**：
  ```python
      Recognizes the bracketed ``[SILENT]`` sentinel (whole-response, first line,
      or last line) plus the bracketless ``SILENT`` / ``NO_REPLY`` / ``NO REPLY``
      variants the model emits when it drops the brackets (#51438, #46917).
  ```
  `cron.md:440` 的"contains"是**错的**（会让人以为 mid-sentence 也会静默），
  而 `cron/scheduler.py:304-305` 的注释专门举了反例。

### 与文档一致、无需记账的部分（对表已核）

- 四种 schedule 格式表（`website/docs/developer-guide/cron-internals.md:23-30`）与 `parse_schedule` 一致。
- `skill` → `skills` 的向后兼容提升（`website/docs/developer-guide/cron-internals.md:77`）：`cron/jobs.py:390-414` 属实。
- provider 插件与 fallback 到内置 ticker（`website/docs/developer-guide/cron-internals.md:104-128`）：与
  `cron/scheduler_provider.py` + `gateway/run.py:26875` 一致。
- 文件锁 fcntl/msvcrt、抢不到返回 0（`website/docs/developer-guide/cron-internals.md:283`）：`cron/scheduler.py:4181-4190` 一致。
- 脚本只是 pre-run、超时只管脚本不管 agent（`website/docs/developer-guide/cron-internals.md:216`）：与
  `cron/scheduler.py:2119-2149` + `2210-2298` 一致。
- 递归守卫（`website/docs/developer-guide/cron-internals.md:274-279`）方向正确，只是漏了另 3 个 toolset（见 ◇-6）。

---

## 7. issue 溯源（切片内 1–2200 行出现的编号）

| issue | 行号 | 因果经过（输入 → 现象 → 为什么 → 怎么修） |
|---|---|---|
| **#50535/#50536/#50537** | 60–96 | 输入：cron job 跑完要给会话起名。现象：会话空标题 / 标题写入与 close 竞态 / 重名时 `set_session_title` 抛 `ValueError`（唯一索引）后被吞成无标题。为什么：三处分别是"无名 job 无 fallback"、"异步写撞上 close"、"重名未处理"。修：集中到一个同步函数，在 finally 里、close 之前写；`ValueError` 时用 `get_next_title_in_lineage` 加 `#N` 后缀重试，不支持则重新抛。 |
| **#3968** | 158–161 | 输入：一个带恶意 payload 的 skill 被 cron job 引用。现象：创建时的注入扫描通过了（它只扫用户填的 prompt 字段），运行期加载的 skill 内容没扫，payload 直达 auto-approve 的 cron agent。修：改扫**组装后**的完整 prompt，命中抛 `CronPromptInjectionBlocked`，`run_job` 捕获后投递一条干净的 "job blocked"。 |
| **#25752** | 176–178 | 输入：LLM 通过 `cronjob` 工具给 job 设 `enabled_toolsets`。现象：这个 per-job 白名单**加宽**了 config.yaml 里 `agent.disabled_toolsets` 的禁令。修：把用户级 denylist 叠加进 cron 的强制禁用表，per-job 白名单无法绕过。 |
| **#6130** | 226 | per-job `enabled_toolsets` 曾被平台级配置覆盖掉；改为 per-job 优先级最高。 |
| （无编号，"Norbert 的 $4.63") | 236–238 | 输入：全新安装、未配置 cron 平台 toolset。现象：cron job 默认带上了 `moa`（mixture-of-agents），一次跑出 $4.63。修：走 `_get_platform_tools`，未配置平台会剔除 `_DEFAULT_OFF_TOOLSETS = {moa, homeassistant, rl}`。 |
| **#51438 / #46917** | 316 | 模型输出 `SILENT` / `NO_REPLY`（丢了方括号）。现象：不认这些变体，静默 job 照样投递。修：共享 `gateway.response_filters` 的匹配器，接受无括号变体。 |
| **#60432** | 343、360 | 输入：网关 SIGTERM，`process_registry.kill_all()` 杀掉工具子进程。现象：cron 的 agent 线程还活着，用被截断的工具输出编出一个"看起来正常"的最终回复，把 `last_status` 写成 `ok`；同时网关 drain 完全看不到 cron 在跑（cron 用自己的线程池，不在 `_running_agents` 里）。修：`get_running_job_ids()` 暴露 in-flight 集合给 drain；`_interrupted_job_ids` 让 job 自己的完成路径不敢覆盖中断状态。 |
| **#58720 / #55924** | 552–553、567、2032 | 输入：`hermes update` / systemd restart / OOM 期间恰好一次 tick。现象：`concurrent.futures` 抛 `cannot schedule new futures after interpreter shutdown`，`errors.log` 每次重启都吐一条 traceback。为什么：解释器 finalize 后 asyncio 默认 executor 已拆。修：`_interpreter_shutting_down()` 探测（含异常文本兜底，因为 futures 的模块全局标志会比 `sys.is_finalizing()` 早翻一拍），命中就 warning 跳过。 |
| **#4707** | 581 | cron 存储被冻结在 import 期 / 锚在共享默认根，导致多 profile 的 job 混在一起。修：`_get_hermes_home()` 调用时解析。 |
| **#18722** | 607 | 输入：某 job 的 `origin` 被迁移脚本写成字符串 `"combined-digest-replaces-x-and-y"`。现象：每次触发都 `'str' object has no attribute 'get'` 崩，`mark_job_run` 记下失败，下一 tick 重新加载同一条毒记录再崩，**永远卡死**直到手工改 jobs.json。修：`_resolve_origin` 把非 dict 的 origin 当"没有 origin"。 |
| **#2221 / #2313** | 722 | 输入：cron 结果被镜像进目标会话。现象：以 assistant 角色追加，落在 agent 上一条 assistant 之后 → assistant→assistant，破坏严格交替。修：改成 user 角色 + `[Cron delivery: …]` 前缀，靠 `repair_message_sequence` 的连续 user 合并安全落地。（#2313 是删掉旧实现的那次。） |
| **#24409** | 1063 | 输入：Telegram 开了 topic 模式，cron 投到根 DM。现象：消息落进"系统专用大厅"，用户没法回复，网关还会丢掉 `reply_to_message_id`。修：加 `TELEGRAM_CRON_THREAD_ID`，让 cron 定向到一个专用 topic。 |
| **#43014** | 1487 | 输入：CLI 创建的 job（永远不带 `{platform, chat_id}` origin）设了 `deliver=origin`。现象：每次运行都报 "no delivery target resolved" 假错误。修：`deliver=origin` 且既无 origin 又无任何 home channel 时，按 local 处理（输出仍存 `last_output`）。 |
| **#47056** | 1397、1896 | 输入：live adapter 返回 `None`（吞掉的异常 / 提前 return）。现象：调度器打日志 "delivered via live adapter"，网关其实从没见过这条消息。修：`_confirm_adapter_delivery` 要求对象**有** `success` 属性且为真；dict 形状单独归一化。 |
| **#22773** | 1430、1740、1775、1799、1942 | 输入：`telegram:<正数chat_id>:<数字thread_id>`。现象：真正的 Bot API channel Direct-Messages topic 需要 `direct_messages_topic_id` 路由，走 `message_thread_id` 会落到 General 或被 Bot API 10.0 拒绝；媒体附件也各走各的落错。修：投递时探测 `get_chat_info`，是 channel 才用 DM-topic 路由，文本与媒体共用同一份 `route_metadata`。 |
| **#52060** | 1424、1779 | #22773 的回归：仅凭"形状"判断，把私聊里的 forum topic 误判成 channel DM topic（两者形状完全相同）。修：`_is_channel_dm_topic` 用 chat **type** 判定，失败/超时一律 fail-safe 回 `message_thread_id`。 |
| **#38922** | 1835、1946 | 输入：网关事件循环拥塞，live 发送 60s 没确认。现象：旧逻辑当失败 → standalone 重发 → 用户收到重复消息。修：用 `future.cancel()` 的**返回值**区分两种情况：`False`=协程已在跑、消息在路上 → 当作已投递（跳过 standalone）；`True`=根本没派发 → 必须走 standalone（漏发比重发更糟）。同时"假定已投递"分支跳过媒体发送并把丢掉的附件数记进 `delivery_errors`。 |
| **#47163** | 2063 | 输入：`asyncio.run` 抛 RuntimeError 后进线程池兜底，兜底自己又抛（SMTP ConnectionError / future 超时）。现象：这个异常不被同级的 `except Exception` 捕获，直接逃出 `_deliver_result`，**后面所有投递目标被静默跳过**。修：把兜底再包一层 try/except，单目标失败只记账并 continue。 |
| **#69396** | 2242–2244 | 输入：带 workdir 的 cron 脚本。现象：用 `os.chdir()` 改进程 cwd 会泄漏到并发的网关会话。修：只给 subprocess 传 `cwd=`，**永不**改 Python 进程自身的 cwd。 |
| **#59229 / #60703 / #33315 / #28934 / #51021** | 跨切片 | 见 §3、§5.3 的 `cron/jobs.py` 引用。 |
| **#32612 / #32895 / #68483 / #69377** | 跨切片 | 见 §4.2 的 `cron/scheduler_provider.py` 引用。 |

---

## 8. 测试（本切片对应的行为规格）

已在基线跑通（`HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh …`）：

```
tests/cron/test_terminal_cwd_lock.py  4✓
tests/cron/test_scheduler_shutdown_guard.py  7✓
tests/cron/test_parallel_pool.py  7✓
tests/cron/test_scheduler.py  65✓
tests/cron/test_shutdown_interrupt.py  14✓
=> 97 passed, 0 failed
```

| 测试文件 | 钉住的行为（对应本切片） |
|---|---|
| `tests/cron/test_scheduler.py`（1954 行，65 例） | per-job toolset + MCP 合流的三种语义（17–63）；非 dict origin 不崩（95）；origin 投递保 thread_id、裸平台名走 home root 而非 origin thread（110/127）；`TELEGRAM_CRON_THREAD_ID` 优先级（146/159）；`deliver` 传 list 被归一（202）；`all` 展开（226）；header/footer 包裹（261）；relay-fronted home（289）；媒体走原生附件（361）；平台 disabled 时返回错误（425）；`[SILENT]` 抑制 + **句中出现仍投递**（955/968）；失败 job 无视 SILENT 必投（982）；60s 超时假定已投递不重复（1351）；`None` 结果落回 standalone（1473）；`deliver=origin` 无 home 时按 local（1498）；媒体超时取消 future 后继续（1509）；`cron_delivery_targets` 标记 home 未配置（1592）；镜像写 **user** 角色带标签（1625）；镜像的是未包裹的干净内容（1647）；开 thread + 播种（1685/1709）；`in_channel` 跳过开 thread、播种 key 与入站回复 key 一致（1815/1827）；多目标第一个失败不中断循环、全失败返回合并错误（1883/1914）；标题重名去重（1944） |
| `tests/cron/test_terminal_cwd_lock.py` | 多读者并发；写者等待活跃读者；**读者绝不观察到写者的 override**；`run_job` 体内抛异常也释放锁 |
| `tests/cron/test_parallel_pool.py` | 池复用 / shutdown 清空；**`_running_job_ids` 阻止重复派发**；`sync=True` 阻塞并返回正确计数；顺序 job 不阻塞 ticker；顺序池持久；`advance_next_runs` 每 tick 只调一次且带全部 due id |
| `tests/cron/test_shutdown_interrupt.py` | `get_running_job_ids` 快照不可变且独立；`mark_running_jobs_interrupted` 标记全部并设标志；单个 job 标记失败不影响其余；`_is_interrupted` 不清标志 / `_consume_interrupted_flag` 清；被中断的 job 走失败摘要而非原始回复；异常路径同样尊重中断标志 |
| `tests/cron/test_scheduler_shutdown_guard.py` | `_interpreter_shutting_down` 四种输入；standalone 路径在 finalize 时不调度；正常时投递照旧 |
| `tests/cron/test_cron_script.py`（431 行） | 脚本路径安全：绝对路径越界 / `~` / `~` 穿越 / 相对穿越 / **symlink 逃逸** 全 blocked；scripts 子目录允许；subprocess env 被 sanitize；Windows uv venv 绕过 launcher；非 Windows 保留默认文本解码；早期错误时清理 env |
| `tests/gateway/test_slack_cron_continuable_surface.py` | `supports_inchannel_continuable` 能力声明；未识别的 surface 值降级为 `thread`；`in_channel` 未配 flat reply 时告警 |
| `tests/cron/test_cron_profile_isolation.py` | cron 存储锚定在 profile home（#4707） |
| `tests/cron/test_execution_ledger.py` / `test_claim_job_for_fire.py` / `test_jobs_crossprocess_lock.py` / `test_ticker_stall_60703.py` | 【跨切片】执行账本、跨进程 claim、jobs 文件锁、one-shot 卡死恢复 |

未被按名字直接测到的切片函数：`_resolve_cron_disabled_toolsets`、`_get_script_timeout`、
`_confirm_adapter_delivery`、`_is_channel_dm_topic`、`_normalize_deliver_value`
（前两个有间接覆盖，后三个只在集成场景里被间接走到）。

---

## 9. 重实现要点（造自己的 harness 时抄什么、避什么）

**值得抄的**

1. **"到点了"和"跑一次"必须分离。** 本仓把 trigger（Axis B）做成可插拔 provider，
   把 execution 固定在 `run_one_job`（`cron/scheduler.py:4253-4258` 的注释直说是为了让内置 ticker 和
   Chronos webhook 走**同一段** execute→save→deliver→mark）。这样换调度后端不会带来行为漂移。
2. **at-most-once 靠"执行前先推进 next_run_at"**（`cron/scheduler.py:4213-4218`），
   而不是靠执行后收尾。收尾一定会有崩溃/超时的路径，推进放在前面 + 持锁，才是真的幂等。
3. **同一个 job 的重入用进程内集合直接 skip，不排队**（`cron/scheduler.py:4291-4295`）。
   排队会让慢 job 攒出雪崩；skip 的代价只是少跑一次，而 `mark_job_run` 完成后下一 tick 自然又到点
   （注释在 `cron/scheduler.py:4350-4354` 明说 "No catch-up queue needed"）。
4. **区分"共享进程状态的 job"和"只读的 job"，用写者优先读写锁**（`cron/scheduler.py:440-493`）。
   只做"写者之间串行"是不够的 —— 这是很多人会漏的一半。
5. **错过的触发要 collapse 成一次**（`cron/jobs.py:2156-2167`），宽限窗口按周期比例算并钳位
   （`cron/jobs.py:738-753`）。既不 burst-fire 也不永久跳过。
6. **关停期要有一等公民的探测函数**（`cron/scheduler.py:542-571`），并且匹配异常文本作兜底 ——
   `sys.is_finalizing()` 和 executor 的内部标志有先后差。
7. **"投递成功"要显式确认，不能靠 `None` 当真**（`cron/scheduler.py:1390-1408`）。
8. **超时不等于失败**：用 `future.cancel()` 的返回值区分"已在飞"和"没派发"
   （`cron/scheduler.py:1852-1874`）。这个二分法适用于任何"重试可能造成重复副作用"的场景。

**值得避的**

1. **别把 job 存 JSON 文件。** `_get_due_jobs_locked` 里为畸形记录写了 4 段修复代码
   （`cron/jobs.py:2189-2268`，缺 id / schedule 非 dict / next_run_at 非法 / last_run_at 非法），
   每一段的注释都在讲"一条坏记录让整个 profile 的调度器冻住"。这是文件存储 + 鼓励手改的直接代价。
2. **DST 别外包给库然后不看。** 实测 croniter 6.0.0 在回拨当天会让"每天 2:30"落到 03:30，
   次日还会再漂一小时（§3.3）。要么显式按墙钟推进（存 `(local_time, tz)` 而不是绝对时刻），
   要么至少写测试钉住跳变日的行为 —— 本仓两者都没有。
3. **默认并发无上限**（`cron/scheduler.py:4234-4243`，env/config 都不设时 `_max_workers = None`）。
   同一分钟到点的 job 数就是并发 LLM 会话数。
4. **平台白名单要有单一入口。** `_KNOWN_DELIVERY_PLATFORMS` 只被裸名分支用，
   冒号分支绕过（◇-2）；`whatsapp_cloud` 只出现在半边表里（◇-1）；`homeassistant` 只出现在另半边（▲-7）。
   两张并列的常量表 + 一个插件注册表，必然漂移。
5. **别让"这个不变量成立"进架构文档。** `AGENTS.md:1082` 的"cron 投递永不镜像"在
   `cron/scheduler.py:619` 落地了开关之后就成了错的（▲-4）。默认值和不变量是两回事。

---

## 10. 延伸 / 未覆盖

- 本切片**不含**：`run_job`（2779–3904，agent 构造、模型解析、fallback、workdir、inactivity 超时）、
  `run_one_job`（3930–4132）、`tick`（4151–4428）。这些是同轮另一个切片的范围。
- 本笔记为回答任务问题而引用的 `cron/jobs.py`、`cron/executions.py`、`cron/scheduler_provider.py`、
  `gateway/run.py`、`hermes_time.py` 均为**定点核对**，非逐行精读，不应据此为它们标记 L1。
- 待后续轮次确认：`Platform._missing_` 的 bundled-plugin 发现路径（`gateway/config.py:320-322`）
  对 cron 投递平台校验的实际边界；`cron_continuable_surface` 除 Slack 外是否还有消费者。
