# r7c-raw-cron-jobs · cron/jobs.py + cron/executions.py + cron/\_\_init\_\_.py

> 基线:`863e31318553cda8ad61df681d08175364d4164b`(2026-08-06)。
> 本文所有断言格式为 `路径:行号 @ 863e313` + 代码原文块。行号已逐条复核。
> hermes-agent 仓库只读。

切片规模:`cron/jobs.py` 2746 行(完整精读)、`cron/executions.py` 280 行(完整精读)、
`cron/__init__.py` 42 行(完整读)。

---

## 0. 本切片一句话

**`jobs.py` 是 cron 的"状态机 + 单文件数据库"——一个 JSON 文件 + 两层锁 + 三套 claim 协议,
把"到点该不该跑"这个判断做成可崩溃恢复的;`executions.py` 是旁挂的 SQLite 审计账本,
只记录"发生过什么",从不驱动重试。**

两个文件的分工是本切片最重要的设计决定:**调度决策(去重、抢占、推进)全在 `jobs.json` 里,
执行历史(审计)全在 `executions.db` 里,后者对前者没有任何反向控制。**

---

## 1. 结构总览

### 1.1 `cron/jobs.py`(2746 行)

| 行区间 | 内容 | 一句话 |
|---|---|---|
| 1–62 | 模块 docstring / import / croniter 懒加载 | `croniter` 导入要 ~15ms 正则编译,推迟到首次用 |
| 64–116 | 配置常量 | `HERMES_DIR`/`CRON_DIR`/`JOBS_FILE`/ticker 标记文件/两把锁/超时 |
| 119–189 | `_CronStorePaths` + ContextVar 覆盖 + `_current_cron_store()` + `use_cron_store()` | **存储路径的动态解析**(profile 隔离核心) |
| 192–236 | one-shot run-claim TTL 推导 | 从 `HERMES_CRON_TIMEOUT` 派生失效窗口 |
| 239–262 | `_job_running_in_this_process()` | 向 scheduler 反查"这个 job 此刻还在本进程跑吗" |
| 265–365 | `_jobs_lock_file()` / `_jobs_lock()` | 进程内 RLock + 跨进程 flock(带 30s 超时降级) |
| 367–387 | `_IMMUTABLE_JOB_FIELDS` / `_job_output_dir()` | id 不可改 + 路径逃逸防御 |
| 390–472 | skill 归一化 / `_coerce_job_text` / `_normalize_job_record` | 读侧容错:老记录/手改记录不许让消费者崩 |
| 475–536 | `_secure_dir` / `_secure_file` / `_preserve_file_ownership` / `ensure_dirs` | 0700/0600 + root 写回属主 |
| 539–661 | `parse_duration` / `parse_schedule` | 四种调度语法 → 结构化 dict |
| 664–705 | `_ensure_aware` / `_timezone_offset_mismatch` / `_stored_wall_clock_is_future` | 时区迁移判定三件套 |
| 708–831 | `_recoverable_oneshot_run_at` / `_compute_grace_seconds` / `compute_next_run` | 下次运行时间计算 |
| 834–1006 | ticker 心跳 / 成功标记 / catch-up 计数 / 最后一次 tick 错误 | 跨进程可观测性(`hermes cron status` 用) |
| 1013–1102 | `load_jobs` / `_save_jobs_unlocked` / `save_jobs` | JSON 读写 + 自愈 + 原子替换 |
| 1105–1243 | `_normalize_workdir` / provider·model 快照 | 创建期校验与快照 |
| 1246–1441 | **`create_job`** | 唯一的 job 构造点 |
| 1444–1504 | `get_job` / `AmbiguousJobReference` / `resolve_job_ref` / `list_jobs` | 读 API |
| 1507–1686 | `update_job` / `pause_job` / `resume_job` / `trigger_job` / `remove_job` | 写 API |
| 1689–1792 | **`mark_job_run`** | 运行后状态推进(含终态判定) |
| 1795–1918 | `_write_wedged_oneshot_diagnostic` / **`claim_dispatch`** | one-shot 预扣次数 |
| 1921–1950 | `heartbeat_run_claim` | 长跑 one-shot 的 claim 续租 |
| 1953–2004 | `advance_next_runs` / `advance_next_run` | 周期 job 的预推进(批量) |
| 2007–2076 | `_machine_id` / **`claim_job_for_fire`** | 多副本 CAS 抢占 |
| 2079–2152 | `COMPLETED_ONESHOT_RETENTION_DAYS` / `_sweep_completed_oneshots` | 完成态记录保留 7 天 |
| 2155–2521 | **`get_due_jobs` / `_get_due_jobs_locked`** | 到期扫描 + 全部自愈逻辑(全文件最复杂的一段) |
| 2524–2600 | 输出保留 + `save_job_output` | 每 job 保留 50 个输出文件 |
| 2603–2746 | `referenced_skill_names` / `rewrite_skill_refs` | curator 整合 skill 后回写 job 引用 |

### 1.2 `cron/executions.py`(280 行)

| 行区间 | 内容 |
|---|---|
| 1–24 | docstring + `EXECUTIONS_FILE` / `MAX_TERMINAL_EXECUTIONS=1000` / 进程 UUID |
| 27–83 | `_connect` / `_initialize_schema`(建表 + 索引) / `_transaction` |
| 86–120 | `_record` / `_emit_execution_state`(投影到监控) / `_process_start_time` / `_owner_is_live` |
| 123–132 | `_prune_unlocked`(终态行裁剪) |
| 135–196 | `create_execution` / `mark_execution_running` / `finish_execution`(三段状态迁移) |
| 199–233 | `recover_interrupted_executions`(重启后把"证明已死"的置 `unknown`) |
| 236–280 | `list_executions` / `latest_execution` / `latest_executions` |

### 1.3 `cron/__init__.py`(42 行)

纯 re-export 门面:`create_job / get_job / list_jobs / remove_job / update_job / pause_job /
resume_job / trigger_job / JOBS_FILE`(来自 `cron.jobs`)+ `tick`(来自 `cron.scheduler`)。

`cron/__init__.py:9-15 @ 863e313`

```python
Cron jobs are executed automatically by the gateway daemon:
    hermes gateway install    # Install as a user service
    sudo hermes gateway install --system  # Linux servers: boot-time system service
    hermes gateway            # Or run in foreground

The gateway ticks the scheduler every 60 seconds. A file lock prevents
duplicate execution if multiple processes overlap.
```

注意门面**没有**导出 `claim_dispatch` / `claim_job_for_fire` / `mark_job_run` /
`get_due_jobs` / `save_job_output` / `advance_next_run(s)` / `use_cron_store` /
`heartbeat_run_claim`——这些是 scheduler 与工具层直接 `from cron.jobs import ...` 拿的。
门面事实上只覆盖"用户级 CRUD",不覆盖"调度内核"。

---

## 2. job 数据模型与存储

### 2.1 存储位置:为什么是"动态解析"而不是模块常量

存储锚点是**当前 profile 的 home**,不是共享 root。这条注释是全文件最长的一段设计说明:

`cron/jobs.py:68-85 @ 863e313`

```python
# Cron is per-profile by design (issue #4707). Each profile owns its own cron
# store under its own HERMES_HOME, and a profile-scoped gateway runs that
# profile's jobs under that same HERMES_HOME — so a job authored in profile
# `coder` lives in `~/.hermes/profiles/coder/cron/jobs.json` and executes with
# `coder`'s `.env`, `config.yaml`, and skills. We deliberately anchor on
# `get_hermes_home()` (the active profile home), NOT `get_default_hermes_root()`
# (the shared root). Anchoring at the root would funnel every profile's jobs
# into one shared `jobs.json` and run them under whatever HERMES_HOME the
# ticker process happens to have — leaking config/credentials/skills across
# profiles (the security boundary #4707 was filed for). Do NOT change this to
# the default root: that re-breaks per-profile isolation. See also the dynamic
# `_get_hermes_home()` / `_get_lock_paths()` resolution in cron/scheduler.py.
HERMES_DIR = get_hermes_home().resolve()
# These constants remain the default-profile fallback and a compatibility
# surface for existing callers/tests. Cross-profile callers must scope paths
# with use_cron_store() instead of mutating them process-wide.
CRON_DIR = HERMES_DIR / "cron"
JOBS_FILE = CRON_DIR / "jobs.json"
```

**解决什么问题**:模块级常量在 import 时就冻结了路径。任何在 import 之后才改
`HERMES_HOME` 的调用方(测试 fixture、dashboard 多 profile、multiplex gateway)都会读写
**错误的 jobs.json**——注释里说这真的发生过:"fixtures that patched the env too late
silently rewrote the user's real jobs file"。

**怎么实现**:四级优先级的 `_current_cron_store()`。

`cron/jobs.py:139-167 @ 863e313`

```python
def _current_cron_store() -> _CronStorePaths:
    """Return paths pinned to this execution context's profile.

    Precedence, most explicit first:

    1. an active use_cron_store() override (ContextVar);
    2. deliberately re-pointed module constants — if CRON_DIR/JOBS_FILE/
       OUTPUT_DIR no longer match their import-time values, someone chose
       the documented process-wide compatibility surface; honor it;
    3. the ACTIVE profile home, resolved fresh via get_hermes_home()
       (context-local override, then the HERMES_HOME env var) — so a test
       or embedder that re-points HERMES_HOME after this module was
       imported reads/writes ITS OWN store, not whatever jobs.json the
       import happened to freeze (the filed incident: fixtures that patched
       the env too late silently rewrote the user's real jobs file);
    4. the import-time constants (home unchanged since import — the common
       path, returned unchanged).
    """
    override = _cron_store_override.get()
    if override is not None:
        return override
    live_constants = _CronStorePaths(CRON_DIR, JOBS_FILE, OUTPUT_DIR)
    if live_constants != _IMPORT_STORE:
        return live_constants
    home = get_hermes_home().resolve()
    if home == HERMES_DIR:
        return live_constants
    cron_dir = home / "cron"
    return _CronStorePaths(cron_dir, cron_dir / "jobs.json", cron_dir / "output")
```

**取舍**:优先级 2(monkeypatch 模块常量)是**部分可分离的三元组**,这是个坑——
如果只 monkeypatch `CRON_DIR` 而不改 `JOBS_FILE`,`live_constants != _IMPORT_STORE` 成立,
于是返回一个"cron_dir 是新的、jobs_file 还是老的"的**混合 store**。
`tests/cron/test_scheduler_provider.py:289-292 @ 863e313` 就是这种写法(只 patch 了
`CRON_DIR`/`OUTPUT_DIR`),因为那个用例不碰 jobs.json 所以没暴露。

ContextVar 覆盖(优先级 1)是推荐姿势:

`cron/jobs.py:170-184 @ 863e313`

```python
@contextlib.contextmanager
def use_cron_store(home: Union[str, Path]):
    """Route cron storage to ``home`` without mutating process globals."""
    cron_dir = Path(home).expanduser().resolve() / "cron"
    token = _cron_store_override.set(
        _CronStorePaths(
            cron_dir=cron_dir,
            jobs_file=cron_dir / "jobs.json",
            output_dir=cron_dir / "output",
        )
    )
    try:
        yield
    finally:
        _cron_store_override.reset(token)
```

用它的两处:web dashboard(`hermes_cli/web_server.py:11687 @ 863e313`)和 multiplex ticker
(`cron/scheduler_provider.py:303,325,346 @ 863e313`)。

### 2.2 job 的完整字段表

唯一构造点是 `create_job`,字段全表如下(`cron/jobs.py:1391-1434 @ 863e313`):

```python
    job = {
        "id": job_id,
        "name": name or label_source[:50].strip(),
        "prompt": prompt_text,
        "skills": normalized_skills,
        "skill": normalized_skills[0] if normalized_skills else None,
        "model": normalized_model,
        "provider": normalized_provider,
        # Provider/model resolution captured at creation for unpinned jobs
        # (#44585). None for pinned axes, no_agent jobs, resolution failures, and
        # any pre-existing job written before these fields existed (back-compat).
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
    # Only persist attach_to_session when explicitly set, so existing jobs and
    # the common case stay byte-identical (absent key => fall back to the
    # global cron.mirror_delivery config, default off).
    if normalized_attach is not None:
        job["attach_to_session"] = normalized_attach
```

**用户可写 vs 系统维护**,按写入方分类:

| 类别 | 字段 | 说明 |
|---|---|---|
| 用户可写(创建时给) | `name` `prompt` `skills`/`skill` `model` `provider` `base_url` `script` `no_agent` `context_from` `schedule` `repeat.times` `deliver` `origin` `enabled_toolsets` `workdir` `attach_to_session` | 全部经 `create_job` 参数进入 |
| 用户可改(`update_job`) | 上面全部 **除 `id`** | `_IMMUTABLE_JOB_FIELDS = frozenset({"id"})`,`cron/jobs.py:371 @ 863e313` |
| 系统维护(只有引擎写) | `id` `created_at` `schedule_display` `repeat.completed` `enabled` `state` `paused_at` `paused_reason` `next_run_at` `last_run_at` `last_status` `last_error` `last_delivery_error` `provider_snapshot` `model_snapshot` | — |
| 系统维护、**不在初始字典里、运行期才出现** | `run_claim` `fire_claim` `execution_id` | 分别见 §6.2 / §6.3;`execution_id` 不落盘,只在内存 job dict 上传给 `run_one_job` |

`id` 不可变的理由是安全而非洁癖:

`cron/jobs.py:367-371 @ 863e313`

```python
# Fields on a cron job that must never change after creation. ``id`` is used
# as a filesystem path component under ``OUTPUT_DIR``; allowing it to be
# updated lets an unsafe value (``../escape``, absolute path, nested) leak
# into output writes/deletes.
_IMMUTABLE_JOB_FIELDS = frozenset({"id"})
```

配套的运行期防御:

`cron/jobs.py:374-387 @ 863e313`

```python
def _job_output_dir(job_id: str) -> Path:
    """Resolve a job's output directory, rejecting any path-escape attempt.
    ...
    """
    text = str(job_id or "").strip()
    if not text or text in {".", ".."} or "/" in text or "\\" in text:
        raise ValueError(f"Invalid cron job id for output path: {job_id!r}")
    if Path(text).is_absolute() or Path(text).drive:
        raise ValueError(f"Invalid cron job id for output path: {job_id!r}")
    return _current_cron_store().output_dir / text
```

`remove_job` 特意**先解析目录再保存**,避免半执行:

`cron/jobs.py:1676-1685 @ 863e313`

```python
        if len(jobs) < original_len:
            # Resolve the output dir BEFORE saving so a legacy unsafe ID (e.g.
            # left over from before the create-time guard) fails closed without
            # half-applying the removal.
            job_output_dir = _job_output_dir(canonical_id)
            save_jobs(jobs)
            # Clean up output directory to prevent orphaned dirs accumulating
            if job_output_dir.exists():
                shutil.rmtree(job_output_dir)
            return True
```

### 2.3 状态机(`state` 字段)

代码里实际会被写入的 `state` 取值共 **4 个**:`scheduled` / `paused` / `completed` / `error`。
全部写入点:

| 行 | 值 | 触发 |
|---|---|---|
| `cron/jobs.py:1415` | `scheduled` | `create_job` 初值 |
| `cron/jobs.py:1617` | `paused` | `pause_job` |
| `cron/jobs.py:1641` | `scheduled` | `resume_job` |
| `cron/jobs.py:1658` | `scheduled` | `trigger_job` |
| `cron/jobs.py:1752` | `completed` | `mark_job_run` 触到 repeat 上限 |
| `cron/jobs.py:1769` | `error` | `mark_job_run` 周期 job 算不出 next_run |
| `cron/jobs.py:1785` | `completed` | `mark_job_run` one-shot 无下次 |
| `cron/jobs.py:1787` | `scheduled` | `mark_job_run` 正常回到待跑 |
| `cron/jobs.py:1878` | `completed` | `claim_dispatch` 发现已完成 |
| `cron/jobs.py:470` | 读侧兜底 | `_normalize_job_record` 给无 state 老记录补 `scheduled`/`paused` |

**全仓没有任何一处把 cron job 的 `state` 写成 `"running"`**(用 `grep -rn 'state.*=.*"running"'`
核过,命中的全是 gateway/LSP 的无关字段;`cron/` 内 `'running'` 只出现在 `executions.py` 的
SQL 状态枚举里)。这是一条 ▲,见 §7。

`enabled` 与 `state` 是**两个独立维度**且会不一致:`mark_job_run` 在 `error` 分支里**故意保持
`enabled=True`**(见 §6.5),而 `pause_job` 同时写 `enabled=False` + `state="paused"`
(`cron/jobs.py:1613-1621 @ 863e313`)。`list_jobs` 默认只按 `enabled` 过滤:

`cron/jobs.py:1491-1504 @ 863e313`

```python
def list_jobs(include_disabled: bool = False) -> List[Dict[str, Any]]:
    """List all jobs, optionally including disabled ones."""
    jobs = [_normalize_job_record(j) for j in load_jobs()]
    if not include_disabled:
        jobs = [j for j in jobs if j.get("enabled", True)]
    try:
        from cron.executions import latest_executions

        latest = latest_executions([job.get("id", "") for job in jobs])
    except Exception:
        latest = {}
    for job in jobs:
        job["latest_execution"] = latest.get(job.get("id", ""))
    return jobs
```

→ 结果:**暂停的 job 默认在 `cronjob list` 里看不见**(需要 `include_disabled=True`);
完成的 one-shot 同理(`enabled=False`),但它在保留期内仍可用 `--all` 查到最终状态。
这也是 `list_jobs` 唯一一处把 `jobs.json` 与 `executions.db` 缝合起来的地方
(`latest_execution` 字段)。

### 2.4 读侧容错:`_normalize_job_record`

**解决什么问题**:老版本 / 手改 / 外部写入的记录可能 `prompt` 为 null、`name` 缺失、
`schedule_display` 为空,UI 与 scheduler 在格式化时会崩。

`cron/jobs.py:440-472 @ 863e313`

```python
def _normalize_job_record(job: Dict[str, Any]) -> Dict[str, Any]:
    """Return a read-safe cron job shape for UI/API/tool/scheduler consumers.

    Older or hand-edited jobs can have nullable fields like ``prompt``,
    ``name``, or ``schedule_display``.  Keep storage untouched on read, but
    ensure consumers never crash while formatting or running those records.
    """
    normalized = _apply_skill_fields(job)
    job_id = _coerce_job_text(normalized.get("id"), "unknown")
    prompt = _coerce_job_text(normalized.get("prompt"))
    normalized["id"] = job_id
    normalized["prompt"] = prompt

    name = _coerce_job_text(normalized.get("name")).strip()
    if not name:
        script = _coerce_job_text(normalized.get("script")).strip()
        label_source = (
            prompt
            or (normalized["skills"][0] if normalized.get("skills") else "")
            or script
            or job_id
            or "cron job"
        )
        name = label_source[:50].strip() or "cron job"
    normalized["name"] = name
    normalized["schedule_display"] = _schedule_display_for_job(normalized)

    state = _coerce_job_text(normalized.get("state")).strip()
    if not state:
        state = "scheduled" if normalized.get("enabled", True) else "paused"
    normalized["state"] = state

    return normalized
```

关键取舍:**"Keep storage untouched on read"**——归一化只在返回值上做,不回写文件。
`get_job` / `resolve_job_ref` / `list_jobs` 走这条;**但 `get_due_jobs` 不走**,
它只做 `_apply_skill_fields`(`cron/jobs.py:2194 @ 863e313`):

```python
    jobs = [_apply_skill_fields(j) for j in copy.deepcopy(raw_jobs)]
```

→ scheduler 拿到的 due job 字典**没有经过 `_normalize_job_record`**,`prompt` 可能是 `None`。
这是一处一致性缝隙(scheduler 侧自己做防护,不在本切片)。

`skill`(单数,legacy)与 `skills`(复数,正典)双写对齐:

`cron/jobs.py:407-413 @ 863e313`

```python
def _apply_skill_fields(job: Dict[str, Any]) -> Dict[str, Any]:
    """Return a job dict with canonical `skills` and legacy `skill` fields aligned."""
    normalized = dict(job)
    skills = _normalize_skill_list(normalized.get("skill"), normalized.get("skills"))
    normalized["skills"] = skills
    normalized["skill"] = skills[0] if skills else None
    return normalized
```

### 2.5 存储层:两把锁

**为什么需要两把**:进程内 tick 是多线程并行跑 job 的,进程间还有 CLI 与 gateway 同时改文件。

`cron/jobs.py:101-114 @ 863e313`

```python
# In-process lock protecting load_jobs→modify→save_jobs cycles.
# Required when tick() runs jobs in parallel threads — without this,
# concurrent mark_job_run / advance_next_run calls can clobber each other.
_jobs_file_lock = threading.RLock()
_jobs_lock_state = threading.local()

# Upper bound on waiting for the cross-process .jobs.lock flock (#60703).
# Every cron function in the process funnels through _jobs_lock(), and the
# flock is taken while holding the process-wide RLock — so an unbounded wait
# on a lock held by a wedged sibling process silently freezes the ticker
# heartbeat and every job forever.  30s is orders of magnitude above any
# legitimate critical section (field updates only) while keeping the ticker's
# worst-case stall well under one status-alarm threshold.
_JOBS_LOCK_TIMEOUT_SECONDS = 30.0
```

`_jobs_lock()` 的三个设计点:

1. **可重入**(用 `threading.local().depth` 计数),这样 `load_jobs()` 内部自愈调用
   `save_jobs()` 不会死锁:

`cron/jobs.py:290-297 @ 863e313`

```python
    depth = getattr(_jobs_lock_state, "depth", 0)
    if depth:
        _jobs_lock_state.depth = depth + 1
        try:
            yield
        finally:
            _jobs_lock_state.depth -= 1
        return
```

2. **有界获取**,超时后降级为"只有进程内锁"而不是永远卡死(#60703):

`cron/jobs.py:322-343 @ 863e313`

```python
                    _deadline = time.monotonic() + _JOBS_LOCK_TIMEOUT_SECONDS
                    while True:
                        try:
                            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except (OSError, IOError):
                            if time.monotonic() >= _deadline:
                                logger.error(
                                    "Timed out after %.0fs waiting for the cron "
                                    "jobs lock (%s) — another process is holding "
                                    "it. Proceeding with in-process locking only "
                                    "so the scheduler stays alive (#60703).",
                                    _JOBS_LOCK_TIMEOUT_SECONDS,
                                    _jobs_lock_file(),
                                )
                                try:
                                    lock_fd.close()
                                except OSError:
                                    pass
                                lock_fd = None
                                break
                            time.sleep(0.1)
```

注释里那句取舍写得很直白:**"A briefly-torn cross-process write is strictly better than a
permanently dead scheduler."**(`cron/jobs.py:321 @ 863e313`)

3. **锁不可用不算错误**:没有 `fcntl` 也没有 `msvcrt`(非 Unix 非 Windows),或者
   `open()` 失败,都只 warning 后退化为进程内锁(`cron/jobs.py:346-350 @ 863e313`)。

### 2.6 `load_jobs`:三档自愈

`cron/jobs.py:1022-1062 @ 863e313`(自 `load_jobs` 的 try 起,节选关键分支)

```python
    try:
        # utf-8-sig: Windows Notepad / PowerShell 5.1 Set-Content -Encoding UTF8
        # write a leading BOM; json.load under plain utf-8 raises
        # JSONDecodeError("Unexpected UTF-8 BOM") and takes down cron.
        with open(jobs_file, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        # Retry with strict=False to handle bare control chars in string values
        _strict_retry = True
        try:
            with open(jobs_file, 'r', encoding='utf-8-sig') as f:
                data = json.loads(f.read(), strict=False)
        except Exception as e:
            logger.error("Failed to auto-repair jobs.json: %s", e)
            raise RuntimeError(f"Cron database corrupted and unrepairable: {e}") from e
```

三档:① BOM(`utf-8-sig`)② 裸控制字符(`strict=False` 重试后**回写修复**)
③ 顶层是裸 list(包回 `{"jobs": [...]}` 并回写)。都失败才抛
`RuntimeError("Cron database corrupted and unrepairable")`。

回写点:`cron/jobs.py:1049`(控制字符)与 `cron/jobs.py:1056`(裸 list)。

### 2.7 `save_jobs`:原子写 + 属主保护

`cron/jobs.py:1065-1096 @ 863e313`

```python
def _save_jobs_unlocked(jobs: List[Dict[str, Any]]):
    """Save all jobs to storage. Caller must hold _jobs_lock()."""
    jobs_file = _current_cron_store().jobs_file
    ensure_dirs()
    # Snapshot the current owner BEFORE the atomic replace so a privileged
    # writer (root CLI in Docker) can hand ownership back to the gateway user
    # afterwards instead of locking its ticker out (#68483). When the file is
    # being created for the first time, inherit the cron dir's owner — in the
    # Docker image that is the PUID/PGID gateway user who must be able to
    # read the store on the next tick.
    try:
        _stat_before = os.stat(jobs_file)
    except OSError:
        try:
            _stat_before = os.stat(jobs_file.parent)
        except OSError:
            _stat_before = None
    fd, tmp_path = tempfile.mkstemp(dir=str(jobs_file.parent), suffix='.tmp', prefix='.jobs_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({"jobs": jobs, "updated_at": _hermes_now().isoformat()}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        atomic_replace(tmp_path, jobs_file)
        _secure_file(jobs_file)
        _preserve_file_ownership(jobs_file, _stat_before)
```

落盘格式是 `{"jobs": [...], "updated_at": "<iso>"}`,`indent=2`;写入是
mkstemp + fsync + `atomic_replace`。

### 2.8 调度语法解析

`parse_schedule` 支持四种,按判定顺序:

`cron/jobs.py:582-661 @ 863e313`(结构骨架)

1. `every <duration>` → `{"kind":"interval","minutes":N,"display":"every Nm"}`(587–594)
2. 5/6 段 cron 表达式 → `{"kind":"cron","expr":...}`(596–613),字段正则
   `^[\d\*\-,/]+$` 只看前 5 段;需要 `croniter`,缺库直接 `ValueError`
3. ISO 时间戳 → `{"kind":"once","run_at":...}`(615–641)
4. 裸 duration(`30m`)→ `{"kind":"once","run_at": now+N}`(643–651)

`parse_duration` 的正则是唯一权威(`cron/jobs.py:553 @ 863e313`):

```python
    match = re.match(r'^(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)$', s)
```

**只接受"数字 + 单位"**。这直接推翻了根 AGENTS.md 的一条声明,见 §7 ▲-1。

时间戳这段有个重要的时区决定(#51021):

`cron/jobs.py:620-634 @ 863e313`

```python
            # Make naive timestamps timezone-aware at parse time so the stored
            # value doesn't depend on the system timezone matching at check time.
            #
            # Anchor to the CONFIGURED Hermes timezone, not the server's local
            # timezone. The due-check (`get_due_jobs`) compares `next_run_at`
            # against `hermes_time.now()`, which uses the configured zone. If a
            # naive "20:07" were interpreted as server-local (e.g. UTC) while
            # now() runs in Asia/Kolkata, the stored instant would land hours
            # off from the user's wall-clock intent — far enough that one-shots
            # never become due and recurring jobs fire at the wrong time. Using
            # the configured zone makes "20:07" mean 20:07 on the same clock the
            # scheduler checks against (#51021).
            if dt.tzinfo is None:
                hermes_tz = _hermes_now().tzinfo
                dt = dt.replace(tzinfo=hermes_tz)
```

对照:**读取**老的 naive 时间戳走的是另一套语义——按**系统本地时区**解释后转配置时区
(`cron/jobs.py:664-680 @ 863e313` `_ensure_aware`)。写时用配置时区、读时用系统时区,
这个不对称是刻意的(新写入的都带 tz,只有历史遗留才走 `_ensure_aware` 的 naive 分支)。

---

## 3. job 类型学与执行路径

`jobs.py` 里没有 `type` 字段;**类型是由 `no_agent` + `script` + `skills` + `prompt` 四个字段的
组合"涌现"出来的**。这是本切片一个明显的设计选择:不建类型枚举,只建正交开关。

`create_job` 的 docstring 把语义讲全了(`cron/jobs.py:1281-1307 @ 863e313`):

```python
        script: Optional path to a script whose stdout feeds the job. With
                ``no_agent=True`` the script IS the job — its stdout is
                delivered verbatim. Without ``no_agent``, its stdout is
                injected into the agent's prompt as context (data-collection /
                change-detection pattern). Paths resolve under
                ~/.hermes/scripts/; ``.sh`` / ``.bash`` files run via bash,
                anything else via Python.
        ...
        no_agent: When True, skip the agent entirely — run ``script`` on schedule
                and deliver its stdout directly. Empty stdout = silent (no
                delivery). Requires ``script`` to be set. Ideal for classic
                watchdogs and periodic alerts that don't need LLM reasoning.
```

由此推出的**四种事实类型**:

| # | 组合 | 名字 | 执行路径 |
|---|---|---|---|
| A | `prompt` only | 提示词类 | fresh agent session,跑 prompt |
| B | `prompt` + `skills[]` | 技能类 | 先注入 skill 内容,prompt 作为任务指令 |
| C | `script` + `no_agent=False` | 脚本喂料类 | 先跑脚本,stdout 注入 prompt 作上下文,再跑 agent |
| D | `script` + `no_agent=True` | 纯脚本类(无 LLM) | 只跑脚本,stdout 原样投递;空 stdout = 静默 |

`create_job` 里**唯一的类型级校验**是 D 的完整性:

`cron/jobs.py:1341-1348 @ 863e313`

```python
    # no_agent jobs are meaningless without a script — the script IS the job.
    # Surface this as a clear ValueError at create time so bad configs never
    # reach the scheduler.
    if normalized_no_agent and not normalized_script:
        raise ValueError(
            "no_agent=True requires a script — with no agent and no script "
            "there is nothing for the job to run."
        )
```

**反过来没有校验**:`create_job(prompt="", schedule="every 1h")`(既无 prompt、无 skill、
无 script)是**合法的**,会创建一个每小时跑一次空提示词的 job。这个"有效性"校验被推到了
上层——`hermes_cli/cli_commands_mixin.py:1650-1651 @ 863e313` 有
`if not prompt and not skills: print("(._.) Please provide a prompt or at least one skill")`,
`hermes_cli/web_server.py:11824 @ 863e313` 有 `_validate_dashboard_cron_effective_job(...)`
(定义在 `hermes_cli/web_server.py:11546`)。
即:**同一条不变量在 3 个入口各实现一次,内核不守**。这是 §4 要展开的入口分散问题。

第五类"内建 job"?**没有**。全仓没有 `builtin` / `system` 类型的 cron job;所有 job 都从
`create_job` 来,都由用户或 agent 显式创建。`suggestions` / `blueprints` 只是**预填的
`create_job` kwargs 模板**,不是新类型:

`cron/suggestion_catalog.py:39 @ 863e313`

```python
    job_spec: Dict[str, Any]  # kwargs for cron.jobs.create_job
```

`cron/blueprint_catalog.py:667-673 @ 863e313`

```python
    """Validate ``values`` and return ``cron.jobs.create_job`` kwargs.
    ...
    options. The result is passed straight to ``create_job`` — no second schema.
```

### 3.1 provider / model 快照:类型学的一个副产品

Agent 类 job(A/B/C)若没有 pin provider/model,就跟随全局配置。为了让"全局默认被换掉"
这件事在触发时**失败关闭**而不是悄悄改花销,创建时快照当时的解析结果:

`cron/jobs.py:1191-1233 @ 863e313`

```python
def _compute_provider_model_snapshots(
    *,
    provider: Any,
    model: Any,
    base_url: Any,
    no_agent: Any,
) -> Tuple[Optional[str], Optional[str]]:
    """Snapshot unpinned inference axes for the provider/model drift guard.

    Agent cron jobs with unpinned provider/model follow global config at fire
    time. Capture the current resolution for each unpinned axis so a later
    global switch fails closed instead of silently changing spend. Pinned axes
    and no-agent script jobs intentionally carry no snapshot.
    """
```

`no_agent=True`(D 类)直接 `return None, None`(`cron/jobs.py:1211-1212`)——纯脚本 job
不涉及推理,无需快照。快照的默认 model 解析里,`cron.model` 优先于全局 `model.default`:

`cron/jobs.py:1163-1176 @ 863e313`

```python
        # Mirror run_job's precedence: the explicit cron-fleet default
        # (cron.model) beats the global chat model for unpinned cron jobs.
        cron_cfg = cfg.get("cron") or {}
        if isinstance(cron_cfg, dict):
            cron_model = cron_cfg.get("model")
            if isinstance(cron_model, str) and cron_model.strip():
                return cron_model.strip()
        model_cfg = cfg.get("model") or {}
```

`update_job` 只在四个推理轴**真的变了**时重算快照:

`cron/jobs.py:1536-1538 @ 863e313`

```python
            inference_fields_changed = bool(
                {"provider", "model", "base_url", "no_agent"}.intersection(updates)
            ) and _normalized_inference_axes(updated) != previous_inference_axes
```

### 3.2 `workdir`:创建期校验、运行期不复检

`cron/jobs.py:1105-1135 @ 863e313`

```python
def _normalize_workdir(workdir: Optional[str]) -> Optional[str]:
    """Normalize and validate a cron job workdir.

    Rules:
      - Empty / None → None (feature off, preserves old behaviour).
      - ``~`` is expanded.  Relative paths are rejected — cron jobs run detached
        from any shell cwd, so relative paths have no stable meaning.
      - The path must exist and be a directory at create/update time.  We do
        NOT re-check at run time (a user might briefly unmount the dir; the
        scheduler will just fall back to old behaviour with a logged warning).
    """
```

取舍很清楚:**创建期严格、运行期宽松**。理由是 cron 是无人值守的,运行期硬失败等于静默丢一次运行。

---

## 4. 创建入口盘点(全仓 grep)

`grep -rn "create_job"` 后逐个确认,**共 9 个真实创建入口**,全部最终落到
`cron.jobs.create_job`(唯一构造点):

| # | 入口 | 调用点 | 路径特征 |
|---|---|---|---|
| 1 | **agent 模型工具 `cronjob(action="create")`** | `tools/cronjob_tools.py:787 @ 863e313` | 直接调 `create_job`;前置了 prompt 注入扫描、script 路径校验、base_url 校验、`context_from` 存在性校验 |
| 2 | **CLI `hermes cron create` / `add`** | `hermes_cli/cron.py:341 @ 863e313` → `_cron_api(action="create")` | 经由 #1 的工具函数,不是直连 |
| 3 | **CLI 会话内 `/cron add`** | `hermes_cli/cli_commands_mixin.py:1653 @ 863e313` → `_cron_api(action="create")` | 同样经由 #1 |
| 4 | **gateway HTTP `POST /api/jobs`** | `gateway/platforms/api_server.py:5498 @ 863e313` `job = _cron_create(**kwargs)` | **直连 `create_job`**,绕过 #1 的工具层校验(仅自带 name/schedule/prompt 长度 + `_scan_cron_prompt`) |
| 5 | **dashboard `POST /api/cron/jobs`** | `hermes_cli/web_server.py:11830-11845 @ 863e313` `_call_cron_for_profile(profile_name, "create_job", ...)` | 直连 + `use_cron_store` 作 profile 定向 |
| 6 | **dashboard 蓝图实例化** | `hermes_cli/web_routers/cron.py:237 @ 863e313` | `functools.partial(_call_cron_for_profile, profile, "create_job", **spec)` |
| 7 | **CLI `hermes blueprint`** | `hermes_cli/blueprint_cmd.py:306-308 @ 863e313` | 直连 |
| 8 | **agent `blueprints` 工具** | `tools/blueprints.py:209-214 @ 863e313` | 直连 |
| 9 | **接受一条 cron 建议** | `cron/suggestions.py:235-241 @ 863e313` | 直连,`job_spec` 原样展开 |

`cron/suggestions.py:235-241 @ 863e313`

```python
    from cron.jobs import create_job

    spec = dict(s.get("job_spec") or {})
    if origin is not None and "origin" not in spec:
        spec["origin"] = origin

    job = create_job(**spec)
```

**这个分布带来的最重要结论**:9 个入口中有 6 个(#4–#9)**直连 `create_job`**,
只有 3 个走 `cronjob` 工具。因此**任何必须"每条创建路径都生效"的不变量,都必须放进
`create_job` 本身**——代码里明确这么做了一次:

`cron/jobs.py:1360-1366 @ 863e313`

```python
    # Reject cron jobs that schedule gateway-lifecycle commands. Prevents
    # agent-driven SIGTERM-respawn loops under launchd/systemd KeepAlive
    # (#30719). Enforced here (not only in the CLI layer) so the agent's
    # `cronjob` model tool — which calls create_job directly — is also
    # covered, not just `hermes cron create`.
    from cron.lifecycle_guard import check_gateway_lifecycle
    check_gateway_lifecycle(prompt_text, normalized_script)
```

`cron/lifecycle_guard.py:11-15 @ 863e313` 复述同一逻辑:

```python
This module rejects cron job specs whose prompt or script contains a
direct shell-level gateway-lifecycle command.  It is enforced at
``cron.jobs.create_job`` so it fires on every job-creation path: the
``hermes cron create`` CLI subcommand AND the agent's ``cronjob`` model
tool (which calls ``create_job`` directly, bypassing the CLI layer).
```

**但同一守卫没有装在 `update_job` 上**。`grep -rn "check_gateway_lifecycle"` 全仓只有
`cron/jobs.py:1365-1366` 一处调用点。`tools/cronjob_tools.py:915-919 @ 863e313` 的 update
分支只跑 `_scan_cron_prompt`(提示词注入扫描),不跑生命周期守卫:

```python
        if normalized == "update":
            updates: Dict[str, Any] = {}
            if prompt is not None:
                scan_error = _scan_cron_prompt(prompt)
                if scan_error:
                    return tool_error(scan_error, success=False)
                updates["prompt"] = prompt
```

→ 路径:先创建一个无害 job,再 `cronjob(action="update", prompt="hermes gateway restart")`,
即可绕开创建期守卫。缓解层在别处存在(`tools/terminal_tool.py:2586 @ 863e313` 在
`_HERMES_GATEWAY=1` 时于执行期硬拦),所以这是**纵深防御的一层缺口**而非直接可利用洞。
记作 ◇-6(见 §7)。

对照 §3 提到的"有效 job"校验分散:同一个仓库里,一条不变量放内核(生命周期守卫),
另一条放三个入口各写一遍(prompt/skill 非空),**标准不统一**。

---

## 5. `executions.py` 执行记录

### 5.1 定位:审计账本,不是重试队列

模块 docstring 开门见山(`cron/executions.py:1-6 @ 863e313`):

```python
"""Profile-local durable audit ledger for cron execution attempts.

The ledger records what is known about each attempt; it is not a retry queue.
Interrupted attempts become ``unknown`` only after their exact owner process is
proved gone. Terminal states are immutable.
"""
```

三条不变量:① 只记录不驱动;② `unknown` 需要**证明**属主进程已死;③ 终态不可改写。

### 5.2 记什么(schema)

`cron/executions.py:39-62 @ 863e313`

```python
    conn.execute(
        """CREATE TABLE IF NOT EXISTS executions (
             id TEXT PRIMARY KEY,
             job_id TEXT NOT NULL,
             source TEXT NOT NULL,
             process_id TEXT NOT NULL,
             pid INTEGER NOT NULL,
             process_started_at INTEGER,
             status TEXT NOT NULL CHECK(status IN
               ('claimed','running','completed','failed','unknown')),
             claimed_at TEXT NOT NULL,
             started_at TEXT,
             finished_at TEXT,
             error TEXT
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_executions_job_claimed "
        "ON executions(job_id, claimed_at DESC, id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_executions_status_claimed "
        "ON executions(status, claimed_at DESC, id DESC)"
    )
```

关键字段:
- `process_id` = 进程级 UUID(`cron/executions.py:24` `_PROCESS_ID = uuid.uuid4().hex`),
  区分"同一进程"用的,不受 PID 复用影响;
- `pid` + `process_started_at` = **进程指纹**,专门用来抵抗 PID 复用;
- `source` = `"builtin"` / `"direct"` / provider 名(如 `chronos`),由三个调用点决定:
  `cron/scheduler.py:4298`(builtin)、`cron/scheduler.py:3947`(direct)、
  `cron/scheduler_provider.py:112`(`source=self.name`)。

两条索引都是 `(…, claimed_at DESC, id DESC)`——排序键与所有查询完全一致,
所以列表与"每 job 最新一条"都能走索引。

DB 配置:`PRAGMA busy_timeout=5000`、WAL(带回退)、`PRAGMA synchronous=FULL`
(`cron/executions.py:36-38 @ 863e313`)。`synchronous=FULL` 是审计账本该有的选择:
宁可慢,不可在断电时丢已确认的终态。

### 5.3 状态迁移:三段,每段都是条件 UPDATE

`cron/executions.py:157-172 @ 863e313`

```python
def mark_execution_running(execution_id: str) -> Optional[Dict[str, Any]]:
    """Transition one claimed attempt to running exactly once."""
    now = _hermes_now().isoformat()
    with _transaction() as conn:
        cur = conn.execute(
            """UPDATE executions SET status='running', started_at=?
               WHERE id=? AND status='claimed'""",
            (now, execution_id),
        )
        if cur.rowcount != 1:
            return None
```

`cron/executions.py:175-196 @ 863e313`

```python
def finish_execution(
    execution_id: str, *, success: bool, error: Optional[str] = None,
    delivery_outcome: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Write a terminal result once; terminal attempts cannot be rewritten."""
    now = _hermes_now().isoformat()
    status = "completed" if success else "failed"
    detail = None if success else (str(error) if error else "unknown failure")
    with _transaction() as conn:
        cur = conn.execute(
            """UPDATE executions SET status=?, finished_at=?, error=?
               WHERE id=? AND status IN ('claimed','running')""",
            (status, now, detail, execution_id),
        )
        if cur.rowcount != 1:
            return None
        _prune_unlocked(conn)
```

**手法**:每次迁移都把"前置状态"写进 `WHERE`,再用 `rowcount != 1` 判定是否真的迁移了。
这是 SQL 层的 CAS,不需要额外锁,也天然幂等(重复调用第二次 rowcount=0 → 返回 None)。

### 5.4 留多久:全局 1000 条终态

`cron/executions.py:21 @ 863e313`

```python
MAX_TERMINAL_EXECUTIONS = 1000
```

`cron/executions.py:123-132 @ 863e313`

```python
def _prune_unlocked(conn: sqlite3.Connection) -> None:
    limit = max(0, int(MAX_TERMINAL_EXECUTIONS))
    conn.execute(
        """DELETE FROM executions WHERE id IN (
             SELECT id FROM executions
             WHERE status IN ('completed','failed','unknown')
             ORDER BY claimed_at DESC, id DESC LIMIT -1 OFFSET ?
           )""",
        (limit,),
    )
```

三点值得记:
- **只裁终态**,`claimed` / `running` 永不被裁(在飞的记录不会被自己的兄弟挤掉);
- **全局 1000 条,不是每 job 1000 条**。一个每分钟跑一次的 job 一天就产 1440 条,
  会把别的 job 的历史全部挤出去。这是可用性上的一个真实取舍(简单 vs 公平);
- 裁剪只在 `finish_execution`(196 行前的 191)和 `recover_interrupted_executions`
  (`cron/executions.py:229-230`)里触发——**没有独立的定时清理**,不写就不裁。

### 5.5 怎么查询

三个读 API,全部走索引:

`cron/executions.py:236-257 @ 863e313`(游标分页)

```python
def list_executions(
    *, job_id: Optional[str] = None, limit: int = 50,
    before_claimed_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return indexed, newest-first execution history with cursor pagination."""
    ...
    params.append(max(1, min(int(limit), 500)))
```

`limit` 被夹在 `[1, 500]`(250 行)。分页用 `claimed_at < ?` 游标而非 OFFSET。

`cron/executions.py:265-280 @ 863e313`(批量取每 job 最新一条,给 `list_jobs` 用)

```python
def latest_executions(job_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Load latest execution for many jobs in one indexed query."""
    clean = [str(job_id) for job_id in dict.fromkeys(job_ids) if job_id]
    if not clean:
        return {}
    placeholders = ",".join("?" for _ in clean)
    with _transaction() as conn:
        rows = conn.execute(
            f"""SELECT e.* FROM executions e
                WHERE e.job_id IN ({placeholders})
                  AND e.id=(SELECT e2.id FROM executions e2
                            WHERE e2.job_id=e.job_id
                            ORDER BY e2.claimed_at DESC, e2.id DESC LIMIT 1)""",
            clean,
        ).fetchall()
    return {row["job_id"]: dict(row) for row in rows}
```

用户面:`hermes cron runs [job-id] --limit 20`(别名 `history`),
`hermes_cli/cron.py:199-215 @ 863e313`;CLI 子命令注册在
`hermes_cli/subcommands/cron.py:185-190 @ 863e313`。

### 5.6 连接管理:一个被显式修掉的泄漏

`cron/executions.py:65-83 @ 863e313`

```python
@contextmanager
def _transaction() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit/rollback on exit, always close.

    ``sqlite3.Connection.__enter__``/``__exit__`` only commit or roll back
    the transaction; it does not close the connection. Relying on that alone
    leaks a connection (and its WAL/SHM file descriptors) on every call,
    since closing then depends on the garbage collector. Schema init runs
    inside the ``try`` too, so a PRAGMA/DDL failure after a successful
    ``connect()`` still closes the connection instead of leaking it.
    """
    with _lock:
        conn = _connect()
        try:
            _initialize_schema(conn)
            with conn:
                yield conn
        finally:
            conn.close()
```

这是个通用陷阱的教科书记录:`with sqlite3.connect(...)` **不关连接**,只管事务。
四条测试专门盯这个(见 §9)。

注意这里每次调用都**重新建连接并重跑 `CREATE TABLE IF NOT EXISTS` + PRAGMA**——
用简单换正确(不用维护连接池 / 线程亲和),代价是每次调用一次 open + DDL 解析。
`_lock = threading.RLock()`(`cron/executions.py:23`)把同进程调用串行化。

### 5.7 `_owner_is_live`:如何"证明进程已死"

`cron/executions.py:110-120 @ 863e313`

```python
def _owner_is_live(pid: int, started_at: Optional[int]) -> bool:
    try:
        from gateway.status import _pid_exists
        if not _pid_exists(pid):
            return False
    except Exception:
        return True  # fail safe: inability to prove death must not rewrite state
    if started_at is None:
        return pid == os.getpid()
    current = _process_start_time(pid)
    return current is not None and current == started_at
```

逻辑层次:
1. PID 不存在 → 死。
2. 探测本身抛异常 → **返回 True**(fail-safe:证不了死就当活着,绝不改写状态)。
3. 有指纹 → 比对启动时间,防 PID 复用。
4. **没有指纹**(创建时 `_process_start_time` 就失败了)→ `pid == os.getpid()`。
   这一支是保守但不对称的:一个**真的还活着**的外部进程,若当初没能取到启动时间,
   会被判为"死",其记录被置 `unknown`。取舍是"宁可多标一个 unknown 审计记录,
   也不留一个永远 `running` 的幽灵行"——而且因为 `unknown` **不触发重试**,误判的代价
   仅限于审计噪音。

`cron/executions.py:209-243 @ 863e313` 的恢复循环:

```python
        for row in rows:
            if row["process_id"] == _PROCESS_ID:
                continue
            if _owner_is_live(int(row["pid"]), row["process_started_at"]):
                continue
            cur = conn.execute(
                """UPDATE executions SET status='unknown', finished_at=?, error=?
                   WHERE id=? AND status IN ('claimed','running')""",
                (now,
                 "Scheduler restarted after this execution's owner exited before a durable "
                 "terminal state; whether side effects ran is unknown.",
                 row["id"]),
            )
```

先跳过"本进程自己的记录"(`process_id == _PROCESS_ID`),再要求证明死亡。
写进 `error` 的那句话本身就是设计声明:**"whether side effects ran is unknown"**——
账本承认自己不知道副作用是否发生,所以绝不代替人做重试决定。

### 5.8 监控投影

`cron/executions.py:90-99 @ 863e313`

```python
def _emit_execution_state(
    record: Optional[Dict[str, Any]], *, delivery_outcome: Optional[str] = None
) -> None:
    """Project durable state to monitoring without affecting ledger behavior."""
    try:
        from agent.monitoring.cron_health import emit_execution_state

        emit_execution_state(record, delivery_outcome=delivery_outcome)
    except Exception:
        pass
```

"without affecting ledger behavior" + 裸 `except: pass` = 监控是纯旁路。
下游在 `agent/monitoring/cron_health.py:114-129 @ 863e313`,终态会同步 flush
(`target.flush(timeout=1.0)`)以保证进程退出前事件已出队。

### 5.9 `executions.db` 的 profile 作用域缺口(重要发现)

`cron/executions.py:20 @ 863e313`

```python
EXECUTIONS_FILE = get_hermes_home().resolve() / "cron" / "executions.db"
```

**这是模块级、import 时求值的常量,没有 `_current_cron_store()` 等价物,也不响应
`use_cron_store()`。** 而 `jobs.py` 为此专门建了整套动态解析(§2.1)。

后果在 multiplex 下暴露。`cron/scheduler_provider.py:273-280 @ 863e313` 的 docstring 声称:

```python
        """Tick every served profile's cron store when multiplex_profiles is on.

        Each profile uses ``set_hermes_home_override()`` + ``use_cron_store()``
        to scope its tick, heartbeat, recovery, lock file, config/.env, and
        agent execution to that profile's home — mirroring how
        ``_profile_runtime_scope`` scopes the multiplexed inbound path and
        ``web_server.py`` scopes per-profile cron API calls.
        """
```

但被它包在 scope 里调用的 `self.recover_interrupted()`
(`cron/scheduler_provider.py:301-305 @ 863e313`)最终走到
`recover_interrupted_executions()`,而后者读的是 import 期冻结的 `EXECUTIONS_FILE`:

```python
                with use_cron_store(home):
                    recovered = self.recover_interrupted()
```

→ **所有 profile 的执行记录落在同一个 `executions.db`(进程 import 时的 home),
recovery 也只扫那一个库。** docstring 里 "recovery … scoped to that profile's home" 与
`cron/executions.py:20` 直接矛盾。同理,dashboard 的 `_call_cron_for_profile(..., "list_jobs")`
(`hermes_cli/web_server.py:11687-11688`)在 profile scope 内调 `list_jobs`,
`list_jobs` 内部的 `latest_executions`(`cron/jobs.py:1497-1499`)也读的是同一个库——
显示的 `latest_execution` 可能不属于该 profile。

由于 `job_id` 是 12 位 hex,跨 profile 撞 id 概率极低,所以"串号"不会显性出错,
只会出现"某 profile 的 runs 列表里混着别的 profile 的行"以及"1000 条上限被所有 profile 共享"。
记作 ◇-1(代码内部不一致 + 与自身 docstring 冲突)。

`cron/executions.py` **全文没有一个 issue 编号**——是全新写就的模块,不是被一堆事故打磨出来的
(对比 `jobs.py` 的 39 处 issue 引用)。

---

## 6. 幂等 / 去重 / 失败重试

这是 `jobs.py` 的核心。**四套互不相同的 claim 协议**并存,因为四种"重复"的成因不同。

### 6.1 协议一:`advance_next_run(s)` —— 周期 job 的"预推进"

**问题**:周期 job 在执行中崩溃,重启后 `next_run_at` 还是老值 → 再次到期 → 崩 → 无限重放。

`cron/jobs.py:1990-2004 @ 863e313`

```python
def advance_next_run(job_id: str) -> bool:
    """Preemptively advance next_run_at for a recurring job before execution.

    Call this BEFORE run_job() so that if the process crashes mid-execution,
    the job won't re-fire on the next gateway restart.  This converts the
    scheduler from at-least-once to at-most-once for recurring jobs — missing
    one run is far better than firing dozens of times in a crash loop.

    One-shot jobs are left unchanged so they can still retry on restart.

    Returns True if next_run_at was advanced, False otherwise.
    """
    # >= 1 (not == 1): a corrupted jobs file with duplicate ids advances
    # every matching record; the wrapper still reports the advance.
    return advance_next_runs([job_id]) >= 1
```

**语义定档**:周期 job = **at-most-once**(宁可漏一次);one-shot 保留重试能力。

批量版是性能优化,注释里带实测数据:

`cron/jobs.py:1953-1966 @ 863e313`

```python
def advance_next_runs(job_ids) -> int:
    """Batch form of :func:`advance_next_run` for the due-dispatch loop.

    One ``load_jobs()`` + at most one ``save_jobs()`` for the whole due
    set, instead of one of each per job — the per-job form costs
    O(N loads + N saves) for N due jobs (~110 ms at N=50, measured), the
    batch form O(1 + 1) (~2 ms). ``job_ids`` may contain ids of one-shot
    or unknown jobs; they are skipped exactly as the per-job form skips
    them. Returns the number of jobs whose ``next_run_at`` was advanced.

    Crash semantics: the batch persists once at the end, so a crash
    mid-batch re-fires the whole set on restart (at-least-once burst)
    rather than advancing a prefix — acceptable given the sub-10ms window,
    and identical to the per-job form once the batch completes.
    """
```

批量化把崩溃语义从"前缀已推进"改成"要么全推进要么全不推进",作者显式承认并接受
(窗口 <10ms)。

### 6.2 协议二:`run_claim` —— one-shot 的"运行中占位"(#59229 / #62002)

**问题**:one-shot 的"到期"状态直到 `mark_job_run` 才解除,而一次 agent 运行可能几分钟。
两个 ticker(如 gateway + desktop 都开了 60s 内嵌 ticker,指向同一个 HERMES_HOME)
会在第二个 tick 时再次派发同一个 one-shot。`advance_next_run` 对 one-shot 不生效(§6.1),
所以需要独立机制。

**盖章点**在 `get_due_jobs` 返回之前,与到期判定**同一把锁内**:

`cron/jobs.py:2485-2508 @ 863e313`

```python
                # Durably claim a one-shot for the DURATION of its run before
                # returning it as due, so a second scheduler process (gateway +
                # desktop both run in-process 60s tickers on one HERMES_HOME)
                # cannot re-dispatch it while the first run is still in flight
                # (#59229). A plain one-shot's due-state is not resolved until
                # mark_job_run() completes it minutes later, so advancing
                # next_run_at by a fixed window is not enough — a job that outlives
                # one tick (e.g. a 2.5-min research prompt) would simply re-fire on
                # the next tick after the window. Instead we stamp a run_claim under
                # the same lock get_due_jobs already holds; the other process reads
                # a fresh claim on its next tick and skips (handled at the top of
                # this loop). mark_job_run() clears the claim on completion. The TTL
                # is only a safety valve: a claiming tick that DIES mid-run leaves a
                # stale claim that expires after the resolved run-claim TTL
                # (_oneshot_run_claim_ttl_seconds, derived from HERMES_CRON_TIMEOUT),
                # so the job is re-dispatched rather than wedged forever.
                if kind == "once":
                    claim = {"at": now.isoformat(), "by": _machine_id()}
                    job["run_claim"] = claim
                    for rj in raw_jobs:
                        if rj["id"] == job["id"]:
                            rj["run_claim"] = claim
                            needs_save = True
                            break
```

**读取点**在同一循环开头:

`cron/jobs.py:2294-2314 @ 863e313`

```python
            # Cross-process running-claim guard (#59229): if another scheduler
            # process already claimed this one-shot and its run is still in flight
            # (claim younger than the TTL), skip it — do NOT re-dispatch. ...
            existing_claim = job.get("run_claim")
            if existing_claim and job.get("schedule", {}).get("kind") == "once":
                try:
                    claimed_at = _ensure_aware(
                        datetime.fromisoformat(existing_claim["at"])
                    )
                    # 0 <= age: a future-dated claim (clock/TZ skew across a
                    # restart) must be treated as stale, not eternally fresh,
                    # or the one-shot is skipped forever (#60703).
                    _age = (now - claimed_at).total_seconds()
                    if 0 <= _age < _run_claim_ttl:
                        continue  # a fresh claim is held by an in-flight run
                except (KeyError, ValueError, TypeError):
                    pass  # malformed claim → fall through and (re)claim
```

**TTL 不是魔数,是从运行超时派生的**:

`cron/jobs.py:210-236 @ 863e313`

```python
def _oneshot_run_claim_ttl_seconds() -> float:
    """Resolve the one-shot running-claim stale-recovery TTL.

    Derived from ``HERMES_CRON_TIMEOUT`` (the cron inactivity timeout the
    scheduler enforces on each run) so the safety valve tracks how long a run
    is actually allowed to go quiet, instead of a magic constant:

    - unset / invalid → default 600s inactivity limit → TTL = 1800s
    - ``0`` (unlimited runs) → no finite bound to derive from → fall back to
      ``ONESHOT_RUN_CLAIM_TTL_SECONDS``
    - positive N → ``max(N * headroom, ONESHOT_RUN_CLAIM_TTL_SECONDS)`` so a
      tiny configured timeout can never expire a claim mid-run.
    """
```

常量:`ONESHOT_RUN_CLAIM_TTL_SECONDS = 1800`(`cron/jobs.py:197`)、
`_ONESHOT_RUN_CLAIM_TTL_HEADROOM = 3`(`cron/jobs.py:205`)、
`_DEFAULT_CRON_INACTIVITY_TIMEOUT = 600.0`(`cron/jobs.py:207`)。

**TTL 还不够**——真正长的运行(网络卡顿、笔记本睡眠)会越过 TTL。于是加了两层:

(a) **续租**(#62002):

`cron/jobs.py:1921-1936 @ 863e313`

```python
def heartbeat_run_claim(job_id: str, *, expected_owner: str) -> bool:
    """Refresh a one-shot's ``run_claim`` timestamp while its run is alive.

    Called periodically from the scheduler's run monitor (#62002) so a
    legitimately long run keeps its claim fresh: an expired claim then really
    does mean "the claiming process died", and neither another process's tick
    nor this process's own next tick will re-dispatch or stale-remove the job
    while the run is in flight. mark_job_run() clears the claim on completion.

    ``expected_owner`` is the stable owner copied from the dispatched job. The
    compare-and-refresh prevents a stale runner that resumes after a long sleep
    from extending a claim another scheduler process has since taken over.
    """
```

比对 owner 再续租——防止睡醒的旧 runner 抢回别人已接管的 claim。

(b) **进程内活性直查**:

`cron/jobs.py:239-262 @ 863e313`

```python
def _job_running_in_this_process(job_id: str) -> bool:
    """Return True when the scheduler in THIS process is still running ``job_id``.

    Direct liveness signal for stale-entry recovery (#62002): the run_claim
    TTL alone cannot distinguish "the claiming tick died" from "the run is
    alive but slow" — a run stalled on network I/O (or a laptop that slept
    mid-run) legitimately outlives the TTL. The in-process ticker and the run
    share this process, so the scheduler's running set settles the common
    single-gateway case without any claim-age guesswork.

    Imported lazily: the scheduler imports this module at load, so a
    module-level import here would be circular.
    """
    try:
        from cron.scheduler import get_running_job_ids
        return job_id in get_running_job_ids()
    except Exception:
        logger.warning(
            "Cron running-set liveness check failed for job %r; keeping the "
            "entry to avoid deleting a possibly live one-shot run",
            job_id,
            exc_info=True,
        )
        return True
```

异常时返回 `True`——同样是 fail-safe(证不了就当在跑,不删记录)。

### 6.3 协议三:`fire_claim` —— 多副本外部触发的 CAS

**问题**:外部调度器(Chronos)在 N 个 gateway 副本上同时说"这个 job 到点了",
必须恰好一个执行。

`cron/jobs.py:2024-2076 @ 863e313`(节选)

```python
def claim_job_for_fire(job_id: str, *, claim_ttl_seconds: int = 300) -> bool:
    """Atomically claim a job for a single external 'fire' (multi-machine
    at-most-once). Returns True iff THIS caller won the claim.
    ...
    """
    with _jobs_lock():
        jobs = load_jobs()
        for job in jobs:
            if job["id"] != job_id:
                continue
            if not job.get("enabled", True) or job.get("state") == "paused":
                return False
            now = _hermes_now()
            existing = job.get("fire_claim")
            if existing:
                try:
                    claimed_at = _ensure_aware(datetime.fromisoformat(existing["at"]))
                    # Bounded on BOTH sides (#60703): a claim stamped in the
                    # future (clock/TZ skew across a restart, or a corrupted
                    # timestamp) would otherwise have a negative age and stay
                    # "fresh" forever — the job becomes permanently unfireable
                    # and every manual `cron run` reports "already being
                    # fired". Treat future-dated claims as stale/overwritable.
                    _age = (now - claimed_at).total_seconds()
                    if 0 <= _age < claim_ttl_seconds:
                        return False  # someone holds a fresh claim
                except Exception:
                    pass  # malformed claim → overwrite
            job["fire_claim"] = {"at": now.isoformat(), "by": _machine_id()}
            kind = job.get("schedule", {}).get("kind")
            if kind in {"cron", "interval"}:
                nxt = compute_next_run(job["schedule"], now.isoformat())
                if nxt:
                    job["next_run_at"] = nxt
            save_jobs(jobs)
            return True
        return False
```

注意"CAS"其实是**文件锁 + 新鲜度检查**,不是原子指令:

`cron/jobs.py:2007-2012 @ 863e313`

```python
def _machine_id() -> str:
    """Stable-ish identifier for claim attribution/debugging (NOT correctness).

    Uses ``HERMES_MACHINE_ID`` if set, else hostname + pid. The CAS correctness
    comes from the file lock + the fresh-claim check, not from this value.
    """
```

**这里有个前提条件值得记下**:跨机器的正确性依赖 `.jobs.lock` 的 flock 跨机器有效,
而 flock 在网络文件系统上的语义是不保证的。加上 §2.5 的"超时后降级为进程内锁",
多副本 at-most-once 是**尽力而为**,不是强保证。TTL(默认 300s)是兜底。

同样的 `0 <= _age` 双边界防御在两处出现(`cron/jobs.py:2064` 与 `cron/jobs.py:2311`),
都是 #60703 的产物:**未来时间戳会让年龄为负 → 永远"新鲜" → job 永远不可触发**。

### 6.4 协议四:`claim_dispatch` —— one-shot 的次数预扣(#38758)

**问题**:一个 `repeat.times=1` 的 job,如果在执行中被 kill,`repeat.completed` 还是 0,
重启后再跑,再被 kill……无限次。

`cron/jobs.py:1839-1854 @ 863e313`

```python
def claim_dispatch(job_id: str) -> bool:
    """Atomically claim a finite one-shot job dispatch BEFORE execution.

    Increments ``repeat.completed`` under the cross-process jobs lock and
    persists the claim immediately, so that if the tick dies mid-execution
    (gateway kill, OOM, segfault, hard-timeout) the dispatch is not lost.
    This converts finite one-shot jobs from *at-least-once* to *at-most-times*
    semantics — a job that self-destructs fires at most ``repeat.times`` times
    instead of infinitely (issue #38758).

    Returns ``True`` if the caller may proceed to run the job, ``False`` if the
    dispatch limit is already reached (in which case the stale job is removed).

    Only claims jobs with ``schedule.kind == "once"`` and ``repeat.times > 0``.
    Recurring jobs (they use ``advance_next_run``) and infinite-repeat / no-repeat
    jobs are left unchanged and always allowed to proceed.
    """
```

**"at-most-times"** —— 这是本仓库自造的语义词,值得记住:不是 at-most-once,
而是"总共最多 times 次,不管崩几回"。

预扣带来的必然后果:`mark_job_run` 必须知道"这次已经被预扣过了",否则重复计数:

`cron/jobs.py:1719-1737 @ 863e313`

```python
                # Increment completed count.  Finite one-shot jobs are
                # pre-claimed by claim_dispatch() BEFORE the side effect runs
                # (issue #38758), which already incremented completed — do not
                # double-count them here.  Recurring jobs and direct callers
                # with no pre-run claim still get the legacy increment.
                if job.get("repeat"):
                    repeat = job["repeat"]
                    times = repeat.get("times")
                    completed = repeat.get("completed", 0)
                    kind = job.get("schedule", {}).get("kind")
                    preclaimed_oneshot = (
                        kind == "once"
                        and times is not None
                        and times > 0
                        and completed > 0
                    )
                    if not preclaimed_oneshot:
                        completed += 1
                        repeat["completed"] = completed
```

判据是 `completed > 0`——**这是个启发式而非精确记账**:它假设"one-shot 且 completed 已 >0"
只可能来自预扣。对 `times=1` 的绝大多数场景成立;对 `times=3` 的 one-shot,
第 2 次运行时 `completed` 已是 2(第 1 次预扣 + 第 2 次预扣),仍走 preclaimed 分支,
逻辑仍对。

### 6.5 失败与重试:三层"失败"分别记在哪

`mark_job_run` 是唯一的失败落库点(`cron/jobs.py:1689-1717 @ 863e313`):

```python
def mark_job_run(job_id: str, success: bool, error: Optional[str] = None,
                 delivery_error: Optional[str] = None):
    """
    Mark a job as having been run.
    
    Updates last_run_at, last_status, increments completed count,
    computes next_run_at, and auto-deletes if repeat limit reached.

    ``delivery_error`` is tracked separately from the agent error — a job
    can succeed (agent produced output) but fail delivery (platform down).
    """
    with _jobs_lock():
        jobs = load_jobs()
        for i, job in enumerate(jobs):
            if job["id"] == job_id:
                now = _hermes_now().isoformat()
                job["last_run_at"] = now
                job["last_status"] = "ok" if success else "error"
                job["last_error"] = error if not success else None
                # Track delivery failures separately — cleared on successful delivery
                job["last_delivery_error"] = delivery_error
                # Clear any external-fire claim so a re-armed recurring job can
                # be claimed again on its next fire (Phase 4C CAS).
                job["fire_claim"] = None
                # Clear the one-shot running-claim (#59229): the run is over, so
                # a re-armed recurring job or a re-dispatched one-shot recovery
                # is claimable again. No-op if the job never carried a claim.
                if job.get("run_claim") is not None:
                    job["run_claim"] = None
```

三种失败的分离:
1. **agent 失败** → `last_status="error"` + `last_error`;
2. **投递失败** → `last_delivery_error`(独立字段,因为 agent 可能成功但平台宕机);
3. **算不出下次运行** → `state="error"`,见下。

`docstring` 里 "auto-deletes if repeat limit reached" 是**过期描述**——代码已改为保留记录:

`cron/jobs.py:1739-1755 @ 863e313`

```python
                    # Check if we've hit the repeat limit
                    if times is not None and times > 0 and completed >= times:
                        # Limit reached: retain the record as a terminal
                        # completion instead of popping it. Deleting the job
                        # here discarded the last_status / last_error /
                        # last_delivery_error written above — a finished
                        # one-shot vanished from `cronjob list` with no
                        # inspectable outcome, and a failed delivery was
                        # invisible. Mirror the terminal shape of the
                        # next_run_at-is-None branch below; the retention
                        # sweep prunes these after
                        # COMPLETED_ONESHOT_RETENTION_DAYS.
                        job["enabled"] = False
                        job["state"] = "completed"
                        job["next_run_at"] = None
                        save_jobs(jobs)
                        return
```

**注:docstring(1695 行)说 "auto-deletes",实现(1751-1753 行)是"保留 + 标 completed"。
文件内自相矛盾,记作 ◇-7。**

**最重要的一条失败策略**——绝不因缺依赖而静默停掉周期 job:

`cron/jobs.py:1757-1787 @ 863e313`

```python
                # Compute next run
                job["next_run_at"] = compute_next_run(job["schedule"], now)

                # If no next run, decide whether this is terminal completion
                # (one-shot) or a transient failure (recurring schedule couldn't
                # compute — e.g. 'croniter' missing from the runtime env).
                # Recurring jobs must NEVER be silently disabled: that turns a
                # missing runtime dep into "job completed" and the user's
                # schedule quietly goes off. See issue #16265.
                if job["next_run_at"] is None:
                    kind = job.get("schedule", {}).get("kind")
                    if kind in {"cron", "interval"}:
                        job["state"] = "error"
                        if not job.get("last_error"):
                            job["last_error"] = (
                                "Failed to compute next run for recurring "
                                "schedule (is the 'croniter' package "
                                "installed in the gateway's Python env?)"
                            )
                        logger.error(
                            "Job '%s' (%s) could not compute next_run_at; "
                            "leaving enabled and marking state=error so the "
                            "job is not silently disabled.",
                            job.get("name", job.get("id", "?")),
                            kind,
                        )
                    else:
                        job["enabled"] = False
                        job["state"] = "completed"
                elif job.get("state") != "paused":
                    job["state"] = "scheduled"
```

### 6.6 会不会自动禁用反复失败的 job?——**不会**

全仓 `grep -rn "consecutive\|failure_count\|fail_count\|auto_pause"` 在 `cron/` 与
`tools/cronjob_tools.py` 下**零命中**(唯一命中是 `cron/scheduler.py:724` 一句无关的
"consecutive-user merge")。

结论:**没有熔断、没有退避、没有失败计数**。一个每分钟失败一次的 job 会永远每分钟失败一次,
只在 `last_status="error"` + `last_error` 里留痕。唯一的自动禁用是**终态**
(repeat 耗尽 / one-shot 完成),不是失败驱动的。

这是个明确的设计取舍:cron 的失败是**用户可见的**(投递失败会推消息,
`hermes cron status` 会显示 ticker 错误标记),所以引擎选择"永不替用户做停用决定"。
与 §5.1 "the ledger is not a retry queue" 是同一哲学的两面:
**引擎只记录与执行,不做策略判断。**

### 6.7 重复"记录"呢?

`create_execution` **没有任何去重**——每次派发都插一条新 uuid 行:

`cron/executions.py:135-148 @ 863e313`

```python
def create_execution(job_id: str, *, source: str) -> Dict[str, Any]:
    """Persist a claimed attempt before executor/provider dispatch."""
    now = _hermes_now().isoformat()
    execution_id = uuid.uuid4().hex
    pid = os.getpid()
```

所以**"同一次触发不重复记录"完全由 jobs.json 层的四套 claim 保证**;
账本层只保证"同一条记录的状态迁移幂等"(§5.3)。这个分层很干净:
**去重在决策层,幂等在记录层。**

`cron/scheduler.py:3945-3947 @ 863e313` 还留了一个 idempotency 接缝:

```python
    execution_id = job.get("execution_id")
    if not execution_id:
        execution_id = create_execution(job["id"], source="direct")["id"]
```

——由上游(builtin tick / provider)预先创建的 execution 会通过 job dict 传下来复用,
只有"直接调用"路径才现场创建。

### 6.8 到期扫描的自愈:六道修复 + 一层兜底

`_get_due_jobs_locked`(`cron/jobs.py:2173-2521`)是全文件最长的函数,大半篇幅在修数据。
按出现顺序:

| 序 | 行 | 修什么 | 为什么(注释原意) |
|---|---|---|---|
| 1 | 2189–2192 | 无 `id` 的记录(老写入方用 `job_id`)→ 恢复或新造 | 一条坏记录让 `job["id"]` 抛 KeyError,**整个扫描中止**,健康 job 的 fast-forward 全部回滚,profile 陷入每分钟空转 |
| 2 | 2205–2212 | `schedule` 不是 dict → 置 `{}` | 同上,`schedule.get("kind")` 会抛 |
| 3 | 2221–2244 | `next_run_at` 非法 ISO → 剔除 | 同上,`fromisoformat` 会抛 |
| 4 | 2246–2268 | `last_run_at` 非法 → 剔除 | 同上 |
| 5 | 2279–2281 | 完成态 one-shot 过保留期 → 清除 | 见 §6.9 |
| 6 | 2322–2354 | 有 schedule 但无 `next_run_at` → 重算 | 直接编辑 jobs.json 绕过 create 的场景 |
| 兜底 | 2283–2290 / 2511–2516 | 每 job 一个 try/except | 见下 |

`cron/jobs.py:2179-2188 @ 863e313`(第 1 道的完整因果记录,写得像事故报告):

```python
    # Repair id-less records BEFORE anything keys off ``job["id"]``. A direct
    # jobs.json edit that bypassed add_job() can leave a record without an "id"
    # (older writers used "job_id"). Every downstream site — the logging
    # helpers and the ``for rj in raw_jobs: if rj["id"] == job["id"]``
    # persistence loops — indexes job["id"] eagerly, so a single malformed
    # record raised KeyError mid-tick, aborting the whole scan before
    # save_jobs() ran. That froze the entire profile's scheduler in a
    # per-minute fast-forward loop (healthy jobs recomputed in memory, then
    # discarded when the exception unwound). Recover the id from the drifted
    # "job_id" key when present, else synthesize one, and persist.
```

(顺带:这段注释提到的 `add_job()` 在代码里**不存在**——函数名叫 `create_job`。命名漂移,见 §7 ◇-8。
同样的 `add_job()` 还出现在 `cron/jobs.py:2331`。)

**结构性兜底**——承认"未来还会有新的畸形形态":

`cron/jobs.py:2283-2290 @ 863e313`

```python
    for job in jobs:
        # Per-job containment (structural guard): one malformed or
        # unexpected job record must never abort the whole scan. The id /
        # schedule / timestamp normalizations above repair the known shapes;
        # this guard catches every FUTURE variant, degrading to "skip this
        # job this tick" so healthy siblings still run and their recovered
        # state still reaches save_jobs() below.
        try:
```

`cron/jobs.py:2511-2516 @ 863e313`

```python
        except Exception:
            logger.exception(
                "Skipping malformed cron job %r during due scan",
                job.get("name") or job.get("id") or "?",
            )
            continue
```

**这是本切片最值得抄的设计**:先修已知形态(可诊断、可持久化),再用一层
per-item try/except 兜住未知形态(降级为"跳过这一条",不牵连兄弟)。

### 6.9 迟到与追赶

`cron/jobs.py:2155-2167 @ 863e313`

```python
def get_due_jobs() -> List[Dict[str, Any]]:
    """Get all jobs that are due to run now.

    For recurring jobs (cron/interval), if the scheduled time is stale (more
    than one period in the past, e.g. because the gateway was down OR because a
    long-running previous execution overran the interval), the accumulated
    missed runs are collapsed — ``next_run_at`` is fast-forwarded to the next
    future occurrence so a backlog does NOT burst-fire on restart — but the job
    still fires ONCE now. This prevents the perpetual-defer loop (#33315) where
    a job whose runtime exceeds ``interval + grace`` would be skipped forever.

    Note: firing once on catch-up flows through ``mark_job_run``, so a job with
    a ``repeat.times`` limit consumes one of its runs on that catch-up fire.
    """
```

**"collapse 积压 + 仍跑一次"** 是关键折中:既不 burst-fire 补上所有错过的 slot,
也不因为"太迟了"而永远跳过(#33315 的坑)。

宽限窗口是**周期的一半,夹在 120s–2h**:

`cron/jobs.py:738-753 @ 863e313`

```python
def _compute_grace_seconds(schedule: dict) -> int:
    """Compute how late a job can be and still catch up instead of fast-forwarding.

    Uses half the schedule period, clamped between 120 seconds and 2 hours.
    This ensures daily jobs can catch up if missed by up to 2 hours,
    while frequent jobs (every 5-10 min) still fast-forward quickly.
    """
    MIN_GRACE = 120
    MAX_GRACE = 7200  # 2 hours
```

one-shot 用固定 `ONESHOT_GRACE_SECONDS = 120`(`cron/jobs.py:116`),
且**跑过一次就永不再合格**:

`cron/jobs.py:708-735 @ 863e313`

```python
def _recoverable_oneshot_run_at(
    schedule: Dict[str, Any],
    now: datetime,
    *,
    last_run_at: Optional[str] = None,
) -> Optional[str]:
    """Return a one-shot run time if it is still eligible to fire.

    One-shot jobs get a small grace window so jobs created a few seconds after
    their requested minute still run on the next tick. Once a one-shot has
    already run, it is never eligible again.
    """
    if not isinstance(schedule, dict) or schedule.get("kind") != "once":
        return None
    if last_run_at:
        return None
```

这个 grace 也是创建期的硬校验(#59395 让它在 update 门也生效):

`cron/jobs.py:1377-1389 @ 863e313`

```python
    next_run_at = compute_next_run(parsed_schedule)
    if parsed_schedule.get("kind") == "once" and next_run_at is None:
        run_at = parsed_schedule.get("run_at") or schedule
        logger.warning(
            "Rejecting one-shot cron job '%s': run_at %s is outside the %ss grace window",
            name or label_source[:50].strip(),
            run_at,
            ONESHOT_GRACE_SECONDS,
        )
        raise ValueError(
            f"Requested one-shot time {run_at} is more than "
            f"{ONESHOT_GRACE_SECONDS}s in the past and cannot be scheduled."
        )
```

`cron/jobs.py:1559-1563 @ 863e313`(update 门,#59395)

```python
                    # Same guard as create_job: an UPDATE that sets a one-shot
                    # to a time >ONESHOT_GRACE_SECONDS in the past would store
                    # next_run_at=None with state="scheduled", re-creating the
                    # ghost job that never fires (#59395). Reject it here too so
                    # the bug can't re-enter through the update door.
```

"the bug can't re-enter through the update door" —— 这句话概括了本仓库对
"多入口同一不变量"的处理原则(与 §4 的 lifecycle_guard 缺口形成对照:
这里补上了,那里没补)。

### 6.10 时区迁移的双开双 fire 防御(#28934)

`cron/jobs.py:2361-2397 @ 863e313`

```python
            # Migration repair: a cron job persists next_run_at as an absolute
            # instant, but the cron expr describes local wall-clock intent. If the
            # configured/system timezone changed after persistence, the stored
            # instant's offset no longer matches now's, and its converted time can
            # look due hours early (21:00+10 -> 13:00+02). When the stored *wall
            # clock* is still in the future, recompute from the schedule so we fire
            # at the intended local time instead of early-then-again.
            #
            # TRADE-OFF: this cannot distinguish a config/host TZ migration from a
            # legitimate DST offset change. A DST boundary that satisfies all four
            # conditions will recompute (and thus SKIP the pending occurrence, no
            # catch-up) rather than fire it. Accepted: in the pure-migration case
            # the recompute lands on the same wall-clock time later the same period,
            # and DST-boundary collisions with a still-future stored wall clock are
            # rare relative to the double-fire bug this prevents (#28934).
            if (
                kind == "cron"
                and next_run_dt <= now
                and _timezone_offset_mismatch(raw_next_run_dt, now)
                and _stored_wall_clock_is_future(raw_next_run_dt, now)
            ):
```

四条件合取才触发,并且**在注释里明写了会误伤 DST 边界**并说明为什么接受。
这是本切片文档质量最高的一处取舍记录。

### 6.11 卡死 one-shot 的可观测移除(#73973)

`cron/jobs.py:1795-1807 @ 863e313`

```python
def _write_wedged_oneshot_diagnostic(job: Dict[str, Any]) -> None:
    """Leave an operator-visible trace when a wedged one-shot is removed.

    A finite one-shot whose dispatch was claimed (``repeat.completed`` >=
    ``repeat.times``) but which never reached ``mark_job_run`` (``last_run_at``
    is null) was interrupted mid-run — scheduler restart, gateway kill, or a
    non-Exception escape (#73973). The recovery guards remove such jobs so
    they stop appearing due, but a silent removal leaves the user with no
    output, no error, and no job record. Write a small diagnostic file into
    the job's output directory so the removal is observable and debuggable.

    Best-effort: diagnostics must never break the removal itself.
    """
```

两个调用点:`claim_dispatch`(`cron/jobs.py:1894`)与到期扫描
(`cron/jobs.py:2482`)。诊断文件通过 `save_job_output` 写进该 job 的输出目录,
内容含 claim 时间与 claim 者(`cron/jobs.py:1813-1825`)。

**设计原则:任何"引擎自动删掉用户资产"的动作,必须留下人能读懂的痕迹。**

### 6.12 完成态与输出的两条保留策略

| 对象 | 常量 | 配置键 | 默认 | 清理时机 |
|---|---|---|---|---|
| 完成的 one-shot 记录 | `COMPLETED_ONESHOT_RETENTION_DAYS = 7`(`cron/jobs.py:2082`) | `cron.completed_retention_days` | 7 天 | 每次到期扫描(`cron/jobs.py:2279`) |
| 每 job 的输出 md | `_CRON_OUTPUT_DEFAULT_KEEP = 50`(`cron/jobs.py:2529`) | `cron.output_retention` | 50 个 | 每次 `save_job_output` 之后(`cron/jobs.py:2598`) |
| 执行账本终态行 | `MAX_TERMINAL_EXECUTIONS = 1000`(`cron/executions.py:21`) | 无(硬编码) | 1000 条(全局) | `finish_execution` / `recover_*` |

两者都可通过非正值关闭(`cron/jobs.py:2116-2117`、`cron/jobs.py:2552-2553`);
`MAX_TERMINAL_EXECUTIONS` **不可配置**。

保留清理绝不猜:

`cron/jobs.py:2105-2113 @ 863e313`

```python
def _sweep_completed_oneshots(raw_jobs: List[Dict[str, Any]], now: datetime) -> bool:
    """Prune terminal ``state == "completed"`` one-shot records past retention.

    Mutates *raw_jobs* in place; returns True when anything was removed (the
    caller persists). Only one-shot (``schedule.kind == "once"``) records in
    the terminal completed state are candidates; recurring jobs and non-
    terminal one-shots are never touched. Age is measured from
    ``last_run_at`` — a completed record without a parseable ``last_run_at``
    is kept (never guess a record into deletion).
    """
```

`cron/jobs.py:2543-2551 @ 863e313`(输出裁剪靠文件名字典序)

```python
def _prune_job_output(job_output_dir: Path, keep: int) -> int:
    """Remove the oldest ``*.md`` run-output files beyond *keep*. Returns count deleted.

    Mirrors the quick-snapshot retention in ``hermes_cli.backup._prune_quick_snapshots``:
    output filenames are timestamp-based (``%Y-%m-%d_%H-%M-%S.md``) so a reverse
    lexical sort orders newest-first, and everything past *keep* is the tail to
    drop. A non-positive *keep* disables pruning. Pruning failures are swallowed
    so they can never break output saving.
    """
```

依赖"文件名时间戳字典序 = 时间序"——由 `save_job_output`
(`cron/jobs.py:2579-2580`)保证格式:

```python
    timestamp = _hermes_now().strftime("%Y-%m-%d_%H-%M-%S")
    output_file = job_output_dir / f"{timestamp}.md"
```

**注意:秒级粒度**——同一秒内两次 `save_job_output` 会覆盖(`atomic_replace` 到同名文件)。
`_write_wedged_oneshot_diagnostic` 与真实输出撞秒时理论上会互相覆盖。

---

## 7. ▲/◇ 候选

约定:▲ = 文档与代码**矛盾**;◇ = 代码有而文档无(或文档内部/代码内部自相矛盾)。

### ▲-1 `"every monday 9am"` 根本不被支持(高置信,可复现)

**文档侧** `AGENTS.md:1059-1061 @ 863e313`

```
Supported schedule formats:
- Duration: `"30m"`, `"2h"`, `"1d"`
- "every" phrase: `"every 2h"`, `"every monday 9am"`
```

**代码侧** `cron/jobs.py:552-561 @ 863e313`

```python
    s = s.strip().lower()
    match = re.match(r'^(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)$', s)
    if not match:
        raise ValueError(f"Invalid duration: '{s}'. Use format like '30m', '2h', or '1d'")
```

`parse_schedule` 对 `every ` 前缀的处理直接调用它(`cron/jobs.py:587-594`),异常不捕获。

**实测**(baseline venv,`/home/user/hermes-venv/bin/python`):

```
'every monday 9am' -> ERROR: ValueError Invalid duration: 'monday 9am'. Use format like '30m', '2h', or '1d'
'every 2h'         -> {'kind': 'interval', 'minutes': 120, 'display': 'every 120m'}
```

全仓也无任何自然语言调度预处理层(`tools/cronjob_tools.py` 只在 1008 行直接调
`parse_schedule`)。**AGENTS.md 这条是错的**;`website/docs/developer-guide/cron-internals.md:25-30`
的四格表反而是对的。

### ▲-2 job 生命周期状态表:文档有 `running`,代码没有;代码有 `error`,文档没有

**文档侧** `website/docs/developer-guide/cron-internals.md:68-73 @ 863e313`

```
| State | Meaning |
|-------|---------|
| `scheduled` | Active, will fire at next scheduled time |
| `paused` | Suspended — won't fire until resumed |
| `completed` | Repeat count exhausted or one-shot that has fired |
| `running` | Currently executing (transient state) |
```

同文档 tick 伪码 `website/docs/developer-guide/cron-internals.md:90-91 @ 863e313` 也写着:

```
  4. For each due job:
     a. Set state to "running"
```

**代码侧**:全仓无一处把 cron job 的 `state` 写为 `"running"`(§2.3 列出了全部 10 个
`state` 写入点)。运行中状态是靠 `run_claim`(`cron/jobs.py:2501-2503`)与
scheduler 的内存集合 `_running_job_ids`(`cron/scheduler.py:4292-4295`)表达的,不落在 `state` 上。

反向:`cron/jobs.py:1768 @ 863e313` 写入的 `"error"` 状态在文档表里完全缺席。

```python
                    if kind in {"cron", "interval"}:
                        job["state"] = "error"
```

### ▲-3 到期过滤条件写错

**文档侧** `website/docs/developer-guide/cron-internals.md:89 @ 863e313`

```
  3. Filter to due jobs (next_run <= now AND state == "scheduled")
```

**代码侧** `cron/jobs.py:2291-2292 @ 863e313`

```python
            if not job.get("enabled", True):
                continue
```

过滤的是 **`enabled`**,不是 `state`。差别是可观测的:一个 `state="error"` 的周期 job
(`enabled` 仍为 True,§6.5)按文档说法**不会**再被派发,按代码会**继续每周期派发**——
而这正是 #16265 想要的行为。文档写反了这条修复的要点。

### ▲-4 AGENTS.md 的 "3-minute hard interrupt" 与代码常量不符

**文档侧** `AGENTS.md:1072-1074 @ 863e313`

```
Hardening invariants:
- **3-minute hard interrupt** on cron sessions — runaway agent loops
  cannot monopolize the scheduler.
```

**代码侧** `cron/jobs.py:207 @ 863e313`

```python
_DEFAULT_CRON_INACTIVITY_TIMEOUT = 600.0
```

`cron/jobs.py:201-205 @ 863e313` 更明确地说明它是**不活跃超时**而非墙钟上限:

```python
# TTL only recovers a claim left by a tick that DIED mid-run. HERMES_CRON_TIMEOUT
# is an *inactivity* limit, not a wall-clock cap — a job that keeps producing
# output legitimately runs past it — so the multiplier gives comfortable
# headroom over any healthy run before we treat a claim as stale.
```

另一份文档 `website/docs/developer-guide/cron-internals.md:216 @ 863e313` 写的是
"a separate *inactivity*-based budget (`HERMES_CRON_TIMEOUT`, default 600s of idle time,
`0` = unlimited) — they can run for hours as long as they keep calling tools or streaming
tokens",与代码完全一致。
**即:AGENTS.md 与代码 + website 开发者文档三方中,AGENTS.md 是孤证且与代码矛盾。**

### ▲-5 jobs.json 路径:文档写死默认 home,代码是 per-profile

**文档侧** `website/docs/developer-guide/cron-internals.md:36 @ 863e313`:"Jobs are stored in `~/.hermes/cron/jobs.json`";
`website/docs/user-guide/features/cron.md:780 @ 863e313` 同样表述。

**代码侧** `cron/jobs.py:69-74 @ 863e313`(原文,未省略):

```python
# store under its own HERMES_HOME, and a profile-scoped gateway runs that
# profile's jobs under that same HERMES_HOME — so a job authored in profile
# `coder` lives in `~/.hermes/profiles/coder/cron/jobs.json` and executes with
# `coder`'s `.env`, `config.yaml`, and skills. We deliberately anchor on
# `get_hermes_home()` (the active profile home), NOT `get_default_hermes_root()`
# (the shared root). Anchoring at the root would funnel every profile's jobs
```

非默认 profile 下路径是 `~/.hermes/profiles/<name>/cron/jobs.json`。文档未提 profile 维度,
这对多 profile 用户是会导致"找不到我的 job"的实际误导。

### ◇-1 `executions.db` 不支持 profile 定向,与其调用方 docstring 矛盾

见 §5.9。双侧证据:

- `cron/executions.py:20 @ 863e313` `EXECUTIONS_FILE = get_hermes_home().resolve() / "cron" / "executions.db"`(import 期冻结)
- `cron/scheduler_provider.py:275-277 @ 863e313` 声称 `use_cron_store()` 让 "recovery" 也被 scope 到该 profile 的 home
- `cron/jobs.py:139-167` 为同一问题专门建了 `_current_cron_store()`——**同一子系统内两套标准**

文档侧 `website/docs/user-guide/features/cron.md:263-264 @ 863e313` 说 "profile-local
`~/.hermes/cron/executions.db`",与 `jobs.json` 的 per-profile 语义不一致,亦无 multiplex 说明。

### ◇-2 `.jobs.lock`(存储锁)全无文档

文档只讲了 tick 锁:`website/docs/developer-guide/cron-internals.md:283 @ 863e313`

```
The scheduler uses cross-process file-based locking (`fcntl.flock` on Unix, `msvcrt.locking` on Windows) to prevent overlapping ticks from executing the same due-job batch twice — even between the gateway's in-process ticker and a standalone `hermes cron` / manual `tick()` call. If the lock cannot be acquired, `tick()` returns 0 immediately.
```

`AGENTS.md:1077 @ 863e313` 也只提 `~/.hermes/cron/.tick.lock`。

代码里还有**第二把独立的锁** `<cron dir>/.jobs.lock`(`cron/jobs.py:265-267`),
以及它 30s 超时后降级为进程内锁的行为(`cron/jobs.py:322-343`,#60703)——
这直接影响"多副本 at-most-once 是不是硬保证",文档一字未提。

### ◇-3 job 记录示例缺 15 个字段

`website/docs/developer-guide/cron-internals.md:38-63 @ 863e313` 的 JSON 示例列了 14 个字段。
代码 `cron/jobs.py:1391-1434` 写入 27 个键 + 3 个运行期键。文档缺席的:
`provider_snapshot` `model_snapshot` `base_url` `no_agent` `context_from`
`enabled_toolsets` `workdir` `paused_at` `paused_reason` `last_error`
`last_delivery_error` `origin` `attach_to_session` `run_claim` `fire_claim`。

其中 `run_claim` / `fire_claim` 是理解并发语义的关键字段,文档完全没有。

### ◇-4 完成态保留 7 天 / 输出保留 50 个 / 账本 1000 条,均无文档

- `cron.completed_retention_days`(`cron/jobs.py:2085-2098`)
- `cron.output_retention`(`cron/jobs.py:2532-2540`)
- `MAX_TERMINAL_EXECUTIONS`(`cron/executions.py:21`)

`grep -rn "output_retention\|completed_retention_days" website/` **零命中**。
`website/docs/developer-guide/cron-internals.md:97` 只说 "If repeat count exhausted → state = 'completed'",
未提记录会被保留后清除。用户看不到这些可调项。

### ◇-5 `cron/executions.py` 未列入开发者文档的 Key Files 表

`website/docs/developer-guide/cron-internals.md:13-19 @ 863e313` 的 Key Files 表列了
`cron/jobs.py` / `cron/scheduler.py` / `tools/cronjob_tools.py` / `gateway/run.py` /
`hermes_cli/cron.py`,**没有 `cron/executions.py`**,整篇 303 行也没有 "executions" 一词
(`grep -c` 确认 cron-internals.md 中 "executions" 只在 179 行以 "cron executions" 泛指出现)。
用户指南 `website/docs/user-guide/features/cron.md:262-273` 反而写得很完整。
**开发者文档比用户文档更旧。**

### ◇-6 gateway 生命周期守卫只在 create,不在 update

见 §4 末。双侧证据:

- `cron/lifecycle_guard.py:12-16 @ 863e313` 宣称 "enforced at `cron.jobs.create_job`
  so it fires on **every job-creation path**" —— 措辞只承诺 creation,严格说不算说谎
- `cron/jobs.py:1365-1366` 是全仓唯一调用点
- `cron/jobs.py:1507` `update_job` 无该调用
- 对照 `cron/jobs.py:1559-1563`(#59395)——one-shot grace 守卫**特意补进了 update 门**,
  说明"补 update 门"是本仓库认可的做法,此处未做

### ◇-7 `mark_job_run` docstring 与实现矛盾(文件内部)

- `cron/jobs.py:1695 @ 863e313`:`"computes next_run_at, and auto-deletes if repeat limit reached."`
- `cron/jobs.py:1740-1753 @ 863e313`:实现是"保留记录、置 `state="completed"`",
  并在注释里明写 `"retain the record as a terminal completion instead of popping it"`

### ◇-8 命名漂移:注释里的 `add_job()` 不存在

`cron/jobs.py:2180 @ 863e313`:`"jobs.json edit that bypassed add_job() can leave a record without an \"id\""`
`cron/jobs.py:2331 @ 863e313`:`"direct jobs.json edit that bypassed add_job() — left"`

全仓无 `def add_job`。真实函数名是 `create_job`。CLI 侧 `add` 是 `create` 的别名
(`hermes_cli/subcommands/cron.py:27-29 @ 863e313`),注释大概率是从 CLI 动词漂过来的。

### ◇-9 半死代码:`TICKER_HEARTBEAT_FILE` / `TICKER_SUCCESS_FILE`

`cron/jobs.py:86-94 @ 863e313`(原文,未省略):

```python
# Heartbeat file the in-process ticker touches on every loop iteration. The
# gateway process and the (separate) ``hermes cron status`` process share it
# so status can tell whether the ticker THREAD is alive, not just whether the
# gateway PROCESS exists — a ticker that dies silently inside a live gateway
# would otherwise report healthy (#32612, #32895).
TICKER_HEARTBEAT_FILE = CRON_DIR / "ticker_heartbeat"
# Last tick that completed WITHOUT raising. Distinguishing this from the plain
# heartbeat lets status detect a ticker that is alive but failing every tick.
TICKER_SUCCESS_FILE = CRON_DIR / "ticker_last_success"
```

**生产代码从不读这两个常量**。`record_ticker_heartbeat` 与两个 age getter 都用字面量
经 `_current_cron_store()` 拼路径:

`cron/jobs.py:884-892 @ 863e313`

```python
    store = _current_cron_store()
    try:
        _atomic_write_epoch(store.cron_dir / "ticker_heartbeat")
    except Exception:
        pass
    if success:
        try:
            _atomic_write_epoch(store.cron_dir / "ticker_last_success")
        except Exception:
            pass
```

全仓唯一引用是一处测试的 monkeypatch(`tests/cron/test_scheduler_provider.py:291-292`),
而该测试同时 patch 了 `CRON_DIR`,所以那两行 monkeypatch 是**无效操作**。
两个常量应视为已死的兼容表面(且它们是 import 期冻结的,与动态解析理念相反)。

对比:`TICKER_INTERVAL_SECONDS`(`cron/jobs.py:99`)是**活的**——
`hermes_cli/cron.py:259,265 @ 863e313` 用它算 `STALE_AFTER = TICKER_INTERVAL_SECONDS * 3 + 20`。

### ◇-10 `create_job` 不校验"job 是否有可执行内容"

见 §3。`create_job(prompt="", schedule="every 1h")` 合法。同一不变量在
`hermes_cli/cli_commands_mixin.py:1650-1651`、`hermes_cli/web_server.py:11824`
(→ `hermes_cli/web_server.py:11546` `_validate_dashboard_cron_effective_job`)
各实现一次,内核不守——与 ◇-6 同类问题。

### ◇-11 `cron/__init__.py` 门面不覆盖调度内核

`cron/__init__.py:31-42 @ 863e313` 只导出 9 个符号;
`claim_dispatch` / `claim_job_for_fire` / `get_due_jobs` / `mark_job_run` /
`heartbeat_run_claim` / `save_job_output` / `advance_next_run(s)` / `use_cron_store` 都不在其中,
消费者一律绕过门面直接 `from cron.jobs import ...`。门面事实上是**部分门面**,
不构成模块边界。文档未描述这一分层。

---

## 8. issue 溯源

`jobs.py` 共 **39 行** 带 issue 引用,覆盖 **18 个不同编号**;`executions.py` 与 `__init__.py`
**零引用**。下表 17 行(#32612 与 #32895 同源合并)。按编号列出因果经过
(输入 → 现象 → 原因 → 修法):

| 编号 | 行号 | 因果 |
|---|---|---|
| **#4707** | 68, 77 | **输入**:多 profile 并存,cron 存储锚在共享 root → **现象**:profile `coder` 的 job 在别的 profile 的 HERMES_HOME 下执行,读到别人的 `.env`/`config.yaml`/skills → **原因**:`get_default_hermes_root()` 把所有 profile 的 job 汇入一个 jobs.json → **修法**:改锚 `get_hermes_home()`(活动 profile),并在注释里立"DO NOT change this" |
| **#16265** | 1765 | **输入**:gateway 的 Python 环境里没装 `croniter` → **现象**:周期 job 跑完一次后 `next_run_at=None`,被判为"完成"并 `enabled=False`,用户的日程**悄悄消失** → **原因**:one-shot 与周期共用同一条"算不出下次 = 完成"分支 → **修法**:`mark_job_run` 按 `kind` 分叉,周期改判 `state="error"` 且**保持 enabled**,并把"是不是没装 croniter"写进 `last_error` |
| **#28934** | 2375 | **输入**:配置时区或宿主时区在 job 持久化之后被改(如 +10 → +02)→ **现象**:cron job 提前数小时触发,然后到点又触发一次(double-fire)→ **原因**:`next_run_at` 存的是绝对时刻,但 cron 表达式表达的是**本地墙钟意图**;偏移变了,同一绝对时刻换算出的本地时间就错了 → **修法**:四条件合取(cron 类型 + 已到期 + 偏移不同 + 存储墙钟仍在未来)时从 schedule 重算;注释显式接受"会误伤 DST 边界"的代价 |
| **#30719** | 1362 | **输入**:agent 在 gateway 里创建了一个内容为 `hermes gateway restart` 的 cron job → **现象**:job 触发 → gateway 死 → launchd/systemd KeepAlive 拉起 → auto-resume 接上原会话 → 同一轮再跑一次 → 约每 10 秒一个循环,必须人工介入 → **原因**:守卫原本只在 CLI 层,agent 的 `cronjob` 工具直连 `create_job` 绕过了它 → **修法**:守卫下沉到 `create_job`(`cron/lifecycle_guard.py`) |
| **#32612 / #32895** | 90, 876 | **输入**:gateway 进程还在,但里面的 ticker **线程**静默死了(或每 tick 都抛)→ **现象**:`hermes cron status` 报告健康,job 全不跑 → **原因**:只有"进程在不在"一个信号 → **修法**:两个独立标记文件——`ticker_heartbeat`(每轮都写)与 `ticker_last_success`(只有不抛异常的 tick 才写);另在 provider 侧改捕 `BaseException` 以免 SystemExit 杀线程 |
| **#33315** | 2163 | **输入**:某个 job 的单次运行时长 > `interval + grace` → **现象**:每次扫描都判定"太迟了",fast-forward 后跳过,**永远不执行** → **原因**:迟到处理只有"跳过"一条路 → **修法**:collapse 积压的同时**仍然跑一次**(fall through 到 `due.append`) |
| **#38758** | 1721, 1847, 2436 | **输入**:`repeat.times=1` 的 one-shot,执行中进程被 kill(OOM/segfault/硬超时)→ **现象**:`repeat.completed` 仍是 0,重启后再跑再被 kill,**无限重放** → **原因**:计数在运行**之后**才加 → **修法**:`claim_dispatch()` 在副作用发生**之前**在锁内预扣并落盘,把语义从 at-least-once 改成 **at-most-times**;`mark_job_run` 相应加 `preclaimed_oneshot` 判据避免双计 |
| **#44585** | 1145, 1400 | **输入**:创建了一个未 pin model 的 agent job,之后用户换了全局默认 model → **现象**:job 静默换到新模型上跑,**花销变化无人知晓** → **修法**:创建/更新时对未 pin 的推理轴(provider / model)快照当时的解析结果,触发时对比,不一致则 fail-closed |
| **#51021** | 631 | **输入**:用户输入不带时区的 `2026-02-03T20:07`,而 Hermes 配置时区(如 Asia/Kolkata)与服务器本地时区(如 UTC)不同 → **现象**:one-shot 永不到期,或周期 job 在错误的钟点触发 → **原因**:解析时按服务器本地时区解释,而到期判定用 `hermes_time.now()`(配置时区),两者差数小时 → **修法**:解析时把 naive 时间锚到**配置时区** |
| **#52383** | 2527, 2597 | **输入**:高频 job 跑在长期部署上 → **现象**:`cron/output/<job>/` 每次运行多一个 md 文件,**永不清理,可撑爆磁盘** → **原因**:输出目录从未设保留策略(对比快照存储早就有 20 个上限)→ **修法**:每 job 保留最新 50 个(`cron.output_retention` 可调,非正值关闭) |
| **#59229** | 192, 1713, 2294, 2489 | **输入**:gateway 与 desktop 都开了 60s 内嵌 ticker、指向同一个 HERMES_HOME;一个 one-shot 要跑 2.5 分钟 → **现象**:第二个 tick 再次派发同一个 one-shot,**同一任务跑两遍** → **原因**:one-shot 的"到期"状态直到 `mark_job_run` 才解除,而 `advance_next_run` 对 one-shot 不生效 → **修法**:在 `get_due_jobs` 已持有的同一把锁内盖 `run_claim`(带 TTL),另一进程读到新鲜 claim 就跳过;`mark_job_run` 清 claim |
| **#59395** | 1562 | **输入**:把一个 job 的 schedule **update** 成一个 >120s 之前的 one-shot 时刻 → **现象**:存下 `next_run_at=None` + `state="scheduled"` 的**幽灵 job**,永不触发也永不消失 → **原因**:创建门有 grace 校验,更新门没有 → **修法**:同样的守卫补进 `update_job`,"so the bug can't re-enter through the update door" |
| **#60703** | 107, 308, 333, 2057, 2309 | 三个独立子问题合一个编号:**(a)** 无超时的 `fcntl.flock(LOCK_EX)` 在持有进程级 RLock 时阻塞 → 一个卡死的兄弟进程让本进程**所有** cron 函数(含 ticker 的 `get_due_jobs`)永久冻结,心跳停更、无任何报错 → 改为 `LOCK_NB` 轮询 + 30s 死线,超时后**降级为进程内锁**并 error 日志。**(b)** 时钟/时区跨重启回拨导致 claim 时间戳落在未来 → 年龄为负 → 永远"新鲜" → job 永久不可触发,手动 `cron run` 也报"already being fired" → 改为 `0 <= _age < ttl` 双边界。**(c)** 同样的双边界修进 one-shot 的 `run_claim` 读取路径 |
| **#62002** | 242, 1924, 2448 | **输入**:一次 one-shot 运行因网络 I/O 停滞、或笔记本中途睡眠,活得比 `run_claim` TTL 还久 → **现象**:同一个 tick 循环里,`completed >= times` + claim 过期的组合被判为"卡死",**job 记录被删,而运行还在进行**,`mark_job_run` 落不了 `last_run_at`/`last_status` → **原因**:TTL 无法区分"claim 者死了"与"运行慢" → **修法**:双管齐下——(a) 运行监视器周期性 `heartbeat_run_claim` 续租(带 owner 比对);(b) 删除前先问 `_job_running_in_this_process()`,在跑就跳过 |
| **#68483** | 500, 525, 948, 1071 | **输入**:`docker exec hermes hermes cron create ...`(docker exec 默认 root)对一个属主是非特权 gateway 用户的 store 做写入 → **现象**:原子写(mkstemp+replace)把 `jobs.json` 翻成 `root:root` mode 600,gateway ticker(uid 1000)从此**每次 tick 都失败**,持续约 14 小时无人发现,原因只在 gateway 的 errors.log 里 → **修法**:(a) 替换前快照属主,euid==0 且属主不同则 `chown` 还回去(`_preserve_file_ownership`);(b) 新增 `ticker_last_error` 标记文件,让另一个进程里的 `hermes cron status`/`list` 能显示失败**原因**而不只是"标记过期" |
| **#69377** | 880, 912, 923 | **输入**:开启 `multiplex_profiles`,一个 gateway 进程服务多个 profile → **现象**:只有进程级 HERMES_HOME(默认 profile)被 tick,次级 profile 的 job **躺在无人认领的 store 里不跑**;`hermes cron status` 也无法分 profile 报活性 → **修法**:`_start_multiplex` 对每个 profile 用 `set_hermes_home_override()` + `use_cron_store()` 逐个 tick;心跳/成功/错误标记全改为经 `_current_cron_store()` 解析(**注意:执行账本没跟上,见 ◇-1**) |
| **#73973** | 1801, 1889, 2481 | **输入**:一个已 `claim_dispatch` 预扣的 one-shot,其 tick 在 `mark_job_run` 之前因 scheduler 重启 / gateway kill / 非 Exception 逃逸而中断 → **现象**:`completed >= times` 但 `last_run_at` 为 null,恢复守卫把它**静默删除**,用户既没有输出、没有报错,连 job 记录都没了 → **修法**:删除前调 `_write_wedged_oneshot_diagnostic()`,往该 job 的输出目录写一份含 claim 时间/claim 者/删除时间的诊断 md |

补充:`cron/jobs.py:1711 @ 863e313` 的 `fire_claim` 注释引用的是内部里程碑
`"(Phase 4C CAS)"` 而非 issue 编号——这是全文件唯一一处非 issue 溯源标记。

---

## 9. 测试

### 9.1 直接覆盖本切片的测试文件

| 文件 | 用例数 | 覆盖点 |
|---|---|---|
| `tests/cron/test_jobs.py` | 66 | `jobs.py` 主测:parse / compute_next_run / CRUD / pause-resume / resolve_job_ref / mark_job_run / advance / get_due_jobs / claim_dispatch / 输出保留 / BOM / 晚期 env 重指向 |
| `tests/cron/test_execution_ledger.py` | 18 | `executions.py` 全部:状态迁移、终态不可改写、保留裁剪、损坏库 fail-closed、恢复语义、连接不泄漏(4 个用例)、CLI 打印、快照包含账本、`list_jobs` 暴露 `latest_execution` |
| `tests/cron/test_jobs_crossprocess_lock.py` | — | `.jobs.lock` 跨进程互斥 |
| `tests/cron/test_ticker_stall_60703.py` | — | #60703 的 30s 超时降级 |
| `tests/cron/test_jobs_file_ownership.py` | — | #68483 属主还原 |
| `tests/cron/test_cron_profile_isolation.py` | — | #4707 per-profile 存储 |
| `tests/cron/test_claim_job_for_fire.py` | — | `fire_claim` CAS |
| `tests/cron/test_compute_next_run_last_run_at.py` | — | 以 `last_run_at` 为基准算下次 |
| `tests/cron/test_script_claim_heartbeat.py` | — | #62002 claim 续租 |
| `tests/cron/test_rewrite_skill_refs.py` | — | curator 回写 |
| `tests/cron/test_file_permissions.py` | — | 0700/0600 |
| `tests/cron/test_cronjob_schema.py` | — | 工具 schema 与字段一致性 |
| `tests/test_journal_mode_config.py:139-162` | — | `executions.db` 的 WAL/journal 模式 |

`tests/cron/` 下共 38 个文件(其余多属 scheduler 切片)。

### 9.2 基线跑通结果

```
$ HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/cron/test_jobs.py tests/cron/test_execution_ledger.py
=== Summary: 2 files, 84 tests passed, 0 failed (100% complete) in 3.0s (8 workers) ===
```

**84/84 通过**(`test_jobs.py` 66 ✓ / 2.8s;`test_execution_ledger.py` 18 ✓ / 3.0s)。

### 9.3 值得当"行为规格"读的几个用例

- `tests/cron/test_jobs.py:607` `test_one_shot_not_redispatched_while_running`
  —— #59229 的可执行规格
- `tests/cron/test_jobs.py:639` `test_run_claim_heartbeat_keeps_long_run_claimed_past_ttl`
  —— #62002 续租
- `tests/cron/test_jobs.py:686` `test_heartbeat_run_claim_rejects_replaced_owner`
  —— owner 比对
- `tests/cron/test_jobs.py:384` `test_recurring_cron_not_disabled_when_croniter_missing`
  —— #16265,是"周期 job 绝不静默停用"的规格锚点
- `tests/cron/test_jobs.py:508` `test_idless_job_does_not_crash_or_block_sibling_jobs`
  与 `:777` `test_bad_next_run_at_does_not_crash_or_block_sibling_jobs`
  与 `:833` `test_unforeseen_per_job_exception_does_not_starve_siblings`
  —— §6.8 三层自愈的三条规格,**"兄弟不被牵连"是被显式测出来的不变量**
- `tests/cron/test_jobs.py:978` `test_late_env_repoint_scopes_store` 与
  `:1000` `test_public_io_after_late_env_repoint_leaves_old_file_untouched`
  —— §2.1 那起"fixture 改晚了 env 结果覆写了用户真实 jobs 文件"事故的回归锁
- `tests/cron/test_execution_ledger.py:310/328/340/357` 四个
  `test_*_closes_connection` —— §5.6 连接泄漏的四面围堵
- `tests/cron/test_execution_ledger.py:68` `test_corrupt_store_fails_closed_without_overwrite`
  —— 断言损坏的 db **原字节不变**(`executions.EXECUTIONS_FILE.read_bytes() == b"not a sqlite database"`),
  与 `jobs.json` 的"尽力自愈"策略**相反**:账本宁可不可用也不覆写

最后这一条对比很值得记:**同一子系统里,job 存储选"自愈优先"(可用性),
执行账本选"绝不覆写"(可审计性)——因为前者的价值在"还能跑",后者的价值在"没被改过"。**

---

## 10. 重实现要点

如果要自己造一个同级别的 cron 子系统,从本切片可迁移的十条:

1. **存储路径必须运行期解析,不能 import 期冻结。** 任何"多租户/多 profile/可嵌入"的
   系统,模块级 `PATH = get_home() / "x"` 都是定时炸弹(§2.1)。用 ContextVar 做作用域覆盖,
   不要用全局变量 monkeypatch(后者会产生"部分重指向"的混合状态)。
   **反例就在本仓库内部**:`executions.py` 没跟上,造成 ◇-1。

2. **"重复执行"不是一个问题,是四个。** 分别是:周期 job 的崩溃重放(→ 预推进
   `next_run_at`)、one-shot 的长跑期重复派发(→ 带 TTL 的 `run_claim` + 续租 + 进程内活性查)、
   多副本的同时触发(→ 锁内 CAS `fire_claim`)、one-shot 的崩溃重放(→ 副作用前预扣次数
   `claim_dispatch`)。**不要指望一个机制覆盖四种**——本仓库试过,四个 issue 各修一遍才收敛。

3. **明确写下每类 job 的投递语义并放进 docstring。** 本仓库的三个词值得抄:
   周期 job = **at-most-once**(`cron/jobs.py:1995`);
   有限 one-shot = **at-most-times**(`cron/jobs.py:1846`);
   批量推进窗口内 = **at-least-once burst**(`cron/jobs.py:1963`)。
   语义写在代码旁边,后来人才不会"顺手优化"掉。

4. **所有 claim 的年龄检查都要双边界。** `0 <= age < ttl`,而不是 `age < ttl`。
   时钟回拨 / 时区变更 / 损坏时间戳会产生未来时间戳,单边界会让任务**永久不可触发**
   且报错信息误导("already being fired")。#60703 的教训。

5. **锁的等待必须有界,超时后降级而不是死等。** 一把在持有进程锁时无超时获取的文件锁,
   等于给整个子系统装了一个静默死机开关。降级路径要 error 级日志 + 明确的取舍陈述。

6. **数据自愈分两层:已知形态逐个修 + 未知形态 per-item 兜底。** 关键是**修完要能持久化**——
   本仓库多个 issue 的共同现象是"一条坏记录抛异常 → 整轮扫描回滚 → 健康 job 的恢复成果全丢"。
   `try/except continue` 必须包在**每条记录**外,不能包在整个循环外。

7. **引擎不做策略判断。** 不自动禁用反复失败的 job(§6.6),不自动重试 unknown 的执行
   (§5.1)。引擎只保证"记录准确"与"不重复执行",停用/重试是人的决定。
   这条让系统行为可预测,也让 bug 不会放大成"我的 job 被系统关掉了"。

8. **任何"引擎自动删用户资产"的动作,必须留人类可读的痕迹。** #73973 的
   `_write_wedged_oneshot_diagnostic` 就是这条。删除是对的,静默删除是错的。

9. **审计账本与调度状态分家,且分家要彻底。** 调度状态放可自愈的存储(JSON + 锁),
   审计放不可改写的存储(SQLite + 条件 UPDATE + `synchronous=FULL`)。
   两者的失败策略应该相反:前者尽力自愈,后者 fail-closed 绝不覆写(§9.3 末)。
   **但要做完**——本仓库的账本没做 profile 作用域,是半成品(◇-1)。

10. **同一条不变量若必须在所有入口生效,就放进唯一构造点。**
    本仓库 9 个创建入口里 6 个直连 `create_job`,所以 lifecycle guard 下沉是对的;
    但"job 要有可执行内容"这条却在三个入口各写一遍(◇-10),
    而 update 门的 lifecycle guard 干脆没有(◇-6)。
    **判据很简单:如果一条规则的违反会造成危害,它就属于内核,不属于入口。**

---

## 附:延伸阅读指向

- scheduler 侧(`cron/scheduler.py` 4000+ 行):`run_job` / `_process_job` / `tick` /
  `_running_job_ids` / 脚本执行 / 投递 —— 不在本切片
- `cron/scheduler_provider.py`:内建 ticker 与 Chronos provider 的选择、multiplex 逐 profile tick
- `cron/lifecycle_guard.py`:gateway 生命周期命令识别(#30719)
- `cron/suggestions.py` / `cron/suggestion_catalog.py` / `cron/blueprint_catalog.py`:
  预填的 `create_job` kwargs 模板层
- `tools/cronjob_tools.py`:agent 面工具 + 三个 CLI 入口共用的校验层
