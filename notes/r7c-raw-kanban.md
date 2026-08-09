# r7c-raw-kanban · kanban_watchers.py + hooks.py + platform_registry.py + cwd_placeholder.py

> 基线 `863e31318553cda8ad61df681d08175364d4164b`。凡断言均带 `路径:行号 @ 863e313` + 代码原文。
> 本切片文件:`gateway/kanban_watchers.py`(1493)、`gateway/hooks.py`(227)、
> `gateway/builtin_hooks/__init__.py`(1)、`gateway/platform_registry.py`(332)、
> `gateway/cwd_placeholder.py`(49)。全部逐行读完。

---

## 0. 本切片一句话

网关侧的 kanban 只干两件事——**派单**(把 ready 卡片变成 OS 进程)和**回话**(把卡片的终态事件
变成聊天消息 + 唤醒创建者会话);**R7 移交的"评论 → steer 注入"根本不在本文件里**,它在
worker 进程自己的心跳里(`tools/kanban_tools.py` + `run_agent.py`),这是本轮最重要的更正。

---

## 1. kanban 是什么(全仓定位)

### 1.1 定义:自建的、SQLite 落盘的多 agent 工作队列

不是外部集成(不是 Jira/Trello/GitHub Projects),是 hermes 自己实现的一张表。

`AGENTS.md:1088-1094 @ 863e313`:

```
## Kanban (multi-agent work queue)

Durable SQLite-backed board that lets multiple profiles / workers
collaborate on shared tasks. Users drive it via `hermes kanban <verb>`;
workers spawned by the dispatcher drive it via a dedicated `kanban_*`
toolset so their schema footprint is zero when they're not inside a
kanban task.
```

`website/docs/user-guide/features/kanban.md:11 @ 863e313`:

```
Hermes Kanban is a durable task board, shared across all your Hermes profiles, that lets multiple named agents collaborate on work without fragile in-process subagent swarms. Every task is a row in `~/.hermes/kanban.db`; every handoff is a row anyone can read and write; every worker is a full OS process with its own identity.
```

### 1.2 它在架构里的位置:与 `delegate_task` 是两种不同原语

文档给出的对照(`website/docs/user-guide/features/kanban.md:33-45 @ 863e313`)可概括为:
`delegate_task` = 函数调用(fork→join,父进程阻塞,子 agent 匿名,失败即失败);
kanban = 持久消息队列 + 状态机(fire-and-forget,worker 是有名字有记忆的 profile,
block→unblock→重跑、crash→reclaim,审计行永久留在 SQLite)。

### 1.3 涉及的模块分工(全仓)

| 层 | 文件 | 职责 |
|---|---|---|
| 内核 | `hermes_cli/kanban_db.py` | schema、`dispatch_once`、事件表、订阅表、原子 claim、worker spawn 环境 |
| CLI | `hermes_cli/kanban.py` | `hermes kanban <verb>` |
| 模型工具面 | `tools/kanban_tools.py` | `kanban_show/complete/block/comment/...`,**外加评论 steer 注入** |
| 网关派单+通知 | **`gateway/kanban_watchers.py`(本切片)** | 两个后台 loop |
| 分解器 | `hermes_cli/kanban_decompose.py` / `kanban_specify.py` | triage 卡片 → 子任务图 |
| 仪表盘 | `plugins/kanban/dashboard/` | Web UI 插件 |
| TUI | `tui_gateway/server.py:8834+` | 复刻了一份 notifier 语义 |

### 1.4 本切片的两个 loop 是什么关系

`gateway/kanban_watchers.py:1-9 @ 863e313`(模块 docstring):

```python
"""Kanban board watcher methods for GatewayRunner.

Extracted verbatim from ``gateway/run.py`` (god-file decomposition Phase 3).
These are the background-loop methods that subscribe to kanban boards, deliver
notifications/artifacts, and drive the multi-agent dispatcher. They use only
``self`` state, so they live on a mixin that ``GatewayRunner`` inherits — the
``self._kanban_*`` call sites resolve identically via the MRO, making this a
behavior-neutral move that lifts ~1,000 LOC out of run.py.
"""
```

即:这是 run.py 的 god-file 拆分产物,`class GatewayKanbanWatchersMixin`
(`gateway/kanban_watchers.py:112-113 @ 863e313`),被 `GatewayRunner` 多继承
(`gateway/run.py:5759 @ 863e313`):

```python
class GatewayRunner(GatewayAuthorizationMixin, GatewayKanbanWatchersMixin, GatewaySlashCommandsMixin):
```

Mixin 里没有 `__init__`,所有状态字段都靠 `getattr(self, ..., default)` 兜底
(如 `_kanban_sub_fail_counts`、`_kanban_notifier_profile`、`_kanban_dispatcher_lock_handle`),
这是"verbatim 搬家不改行为"的代价:契约是隐式的。

---

## 2. watcher 启停与变更检测

### 2.1 谁启动、什么时候启动

两个 loop 都在 `GatewayRunner.start()` 里被 `_spawn_supervised` 拉起
(`gateway/run.py:11481` 与 `11490 @ 863e313`):

```python
        # Start background kanban notifier — each gateway delivers events for
        # subscriptions owned by the profiles whose adapters it hosts, even
        # when another gateway owns the single dispatcher.
        self._spawn_supervised(self._kanban_notifier_watcher, "kanban_notifier_watcher")

        # Start background kanban dispatcher — spawns workers for ready
        # tasks. Gated by `kanban.dispatch_in_gateway` (default True).
        # When false, users run `hermes kanban daemon` externally or
        # simply don't use kanban; this loop becomes a no-op.
        self._spawn_supervised(self._kanban_dispatcher_watcher, "kanban_dispatcher_watcher")
```

`_spawn_supervised` 的关键语义(`gateway/run.py:11625-11630 @ 863e313`):

```python
            exc = t.exception()
            if exc is None:
                # Clean return == deliberate shutdown or a self-disabling watcher
                # (e.g. a gated no-op that returns synchronously). Respawning here
                # would busy-spin such a watcher — so NEVER restart on clean exit.
                return
```

**为什么这么设计**:dispatcher 有多条"我不该跑"的早退路径(配置关、env 关、
锁被别人拿着)。如果监督器对 clean return 也重启,这些早退会变成忙等。所以
"干净返回 = 自我禁用",只有抛异常才带指数退避重启。

### 2.2 notifier:5 秒一跳,顺序与竞态

- 默认周期:`async def _kanban_notifier_watcher(self, interval: float = 5.0)`
  (`gateway/kanban_watchers.py:125 @ 863e313`);spawn 时不传参,所以就是 5s。
- 启动前先睡 5s 等适配器接线完:`gateway/kanban_watchers.py:191-192 @ 863e313`

```python
        # Initial delay so the gateway can finish wiring adapters.
        await asyncio.sleep(5)
```

- 主循环条件 `while self._running:`(`gateway/kanban_watchers.py:194 @ 863e313`);
  停机走 1 秒切片以便"停得快"(`gateway/kanban_watchers.py:779-783 @ 863e313`):

```python
            # Sleep with cancellation checks.
            for _ in range(int(max(1, interval))):
                if not self._running:
                    return
                await asyncio.sleep(1)
```

**启动顺序上有一个不显眼但必要的编排**:notifier 先被 spawn(11484),dispatcher 后
(11490);但 notifier 一进函数就 `await asyncio.sleep(5)`(192),而 dispatcher 在
`await asyncio.sleep(5)`(1144)**之前**已经同步完成了配置读取与单例锁获取(1012)。
所以 notifier 第一跳读 `self._owns_kanban_dispatcher_lock()`(198)时,锁状态已经确定。
如果把 dispatcher 的锁获取挪到 sleep 之后,notifier 首跳就会误判自己"不是 dispatch owner",
从而漏掉 legacy 无 profile 戳的订阅一整跳。

### 2.3 dispatcher:60s 一跳 + 三重闸门

三重闸门按顺序:

1. **env 逃生门**(`gateway/kanban_watchers.py:980-983 @ 863e313`):

```python
        env_override = os.environ.get("HERMES_KANBAN_DISPATCH_IN_GATEWAY", "").strip().lower()
        if env_override in {"0", "false", "no", "off"}:
            logger.info("kanban dispatcher: disabled via HERMES_KANBAN_DISPATCH_IN_GATEWAY env")
            return
```

2. **配置门**(`gateway/kanban_watchers.py:990-995 @ 863e313`),默认 True:

```python
        kanban_cfg = cfg.get("kanban", {}) if isinstance(cfg, dict) else {}
        if not kanban_cfg.get("dispatch_in_gateway", True):
            logger.info(
                "kanban dispatcher: disabled via config kanban.dispatch_in_gateway=false"
            )
            return
```

3. **机器全局单例锁**(`gateway/kanban_watchers.py:1010-1026 @ 863e313`):

```python
        self._kanban_dispatcher_lock_handle = None
        _lock_path = _kb.kanban_home() / "kanban" / ".dispatcher.lock"
        _lock_handle, _lock_state = _acquire_singleton_lock(_lock_path)
        if _lock_state == "contended":
            logger.info(
                "kanban dispatcher: another gateway already holds the dispatcher "
                "lock (%s); this gateway will NOT dispatch.", _lock_path,
            )
            return
        if _lock_state == "held":
            self._kanban_dispatcher_lock_handle = _lock_handle  # hold for process lifetime
            logger.info("kanban dispatcher: holding singleton dispatcher lock (%s)", _lock_path)
        else:
            logger.warning(
                "kanban dispatcher: advisory lock unavailable at %s; proceeding "
                "on config control alone.", _lock_path,
            )
```

锁本身在模块级函数 `_acquire_singleton_lock`(`gateway/kanban_watchers.py:60-94 @ 863e313`),
其 docstring 把"为什么需要第三道闸"写得很清楚:

```python
    """Take an exclusive, non-blocking advisory lock for the sole dispatcher.

    Only one gateway process machine-wide may run the embedded kanban
    dispatcher: concurrent dispatchers double the reclaim frequency (each
    runs its own ``release_stale_claims`` → promote → dispatch loop), double
    claim-attempt events in the event log, and — with ``wal_autocheckpoint=0`` —
    concurrent manual WAL checkpoints can corrupt index pages. The
    ``dispatch_in_gateway`` config flag is the primary control; this lock is the
    backstop that survives config drift and same-profile restart races.
```

三态返回:`held` / `contended` / `unavailable`,`unavailable` 表示锁机制本身不可用
(非 POSIX 文件系统、status.py 不可导入),此时**降级为仅配置控制**而不是拒绝派单。
这是一个明确的可用性 > 严格性取舍。

释放:`gateway/kanban_watchers.py:1479-1482`(CancelledError)与 `1493`(正常退出):

```python
            except asyncio.CancelledError:
                logger.debug("kanban dispatcher: cancelled")
                self._release_kanban_dispatcher_lock()
                raise
```

```python
        self._release_kanban_dispatcher_lock()
```

`_release_kanban_dispatcher_lock`(`gateway/kanban_watchers.py:119-123 @ 863e313`)
先清 `self` 上的可见性字段再释放 OS 锁——注释点名了原因:

```python
    def _release_kanban_dispatcher_lock(self) -> None:
        """Clear notifier-visible ownership before releasing the OS lock."""
        handle = getattr(self, "_kanban_dispatcher_lock_handle", None)
        self._kanban_dispatcher_lock_handle = None
        _release_singleton_lock(handle)
```

因为 notifier(198 行)是靠这个字段判断"我能不能收 legacy 订阅"的;如果先放 OS 锁
再清字段,中间窗口里另一个网关拿到锁,两个进程会同时认为自己拥有 legacy 订阅。

派单周期(`gateway/kanban_watchers.py:1028-1036 @ 863e313`),下限 1 秒:

```python
        try:
            interval = float(kanban_cfg.get("dispatch_interval_seconds", 60) or 60)
        except (ValueError, TypeError):
            ...
            interval = 60.0
        interval = max(interval, 1.0)  # sanity floor — tighter than this is a footgun
```

### 2.4 变更检测:不是文件监听,是"轮询 + 每订阅游标 + 原子 claim"

三层机制:

**(a) 每跳枚举全部 board(不缓存)**——`gateway/kanban_watchers.py:1272-1287 @ 863e313`:

```python
        def _tick_once() -> "list[tuple[str, Optional[object]]]":
            """Run one dispatch_once per board. Returns (slug, result) pairs.

            Enumerating boards on every tick keeps the dispatcher honest
            when users create a new board mid-run: no restart required,
            the next tick picks it up automatically.
            """
```

**(b) 同一 DB 路径去重**——多个 slug 可能指向同一个 DB(`HERMES_KANBAN_DB` 钉死时),
`gateway/kanban_watchers.py:231-254 @ 863e313`:

```python
                    # Enumerate every board on disk, but poll each resolved DB
                    # path once. Multiple slugs can point at the same DB when
                    # HERMES_KANBAN_DB pins the board path; without this guard
                    # one gateway could collect the same subscription/event
                    # more than once before advancing the cursor.
```

**(c) 真正的"新事件"判据 = 每订阅一个单调游标 + `BEGIN IMMEDIATE` 原子推进**
——`gateway/kanban_watchers.py:322-329 @ 863e313`:

```python
                                    old_cursor, cursor, events = _kb.claim_unseen_events_for_sub(
                                        conn,
                                        task_id=sub["task_id"],
                                        platform=sub["platform"],
                                        chat_id=sub["chat_id"],
                                        thread_id=sub.get("thread_id") or "",
                                        kinds=TERMINAL_KINDS,
                                    )
```

内核侧(`hermes_cli/kanban_db.py:9911-9924 @ 863e313`)讲清了去重语义:

```python
    """Atomically claim unseen notification events for one subscription.

    Returns ``(old_cursor, new_cursor, events)``. When events are returned,
    ``kanban_notify_subs.last_event_id`` has already been advanced to
    ``new_cursor`` inside a ``BEGIN IMMEDIATE`` transaction. That makes the
    notifier's read/claim step single-owner across multiple gateway watcher
    processes pointed at the same board DB: concurrent watchers serialize on
    SQLite's writer lock, and only the first process sees and claims a given
    event range.
```

即:**去重靠 SQLite 的写锁 + 游标,不靠内存去重表**。这样多网关部署天然安全。
代价是"claim 先于送达",所以每条失败路径都必须显式 rewind(见 §3.4)。

**(d) 零订阅早退**(每跳成本优化)——`gateway/kanban_watchers.py:255-278 @ 863e313`:

```python
                        # Zero-subscription early exit: probe the board with a
                        # cheap read-only connection BEFORE the writable
                        # `connect()`. A board with no subscriptions has
                        # nothing to notify, and the writable open (schema
                        # init/migration on first open, WAL/-shm sidecars,
                        # checkpoint traffic) is exactly the per-tick cost
                        # this skip avoids.
                        try:
                            if _kb.count_notify_subs(
                                board=slug,
                                notifier_profiles=notifier_profiles,
                                include_unowned=include_unowned,
                            ) == 0:
```

### 2.5 坏 DB 隔离:指纹 + 5 分钟隔离期

`gateway/kanban_watchers.py:1152-1170 @ 863e313`:

```python
        # Avoid hot-looping corrupt-looking board DBs, but do not suppress
        # same-fingerprint retries forever: transient WAL/open races can
        # surface as "database disk image is malformed" for one tick.
        CORRUPT_BOARD_RETRY_AFTER_SECONDS = 300
        disabled_corrupt_boards: dict[
            str, tuple[tuple[str, int | None, int | None], float]
        ] = {}

        def _board_db_fingerprint(slug: str) -> tuple[str, int | None, int | None]:
            path = _kb.kanban_db_path(slug)
            try:
                resolved = str(path.expanduser().resolve())
            except Exception:
                resolved = str(path)
            try:
                stat = path.stat()
            except OSError:
                return (resolved, None, None)
            return (resolved, stat.st_mtime_ns, stat.st_size)
```

指纹 = (解析后路径, mtime_ns, size)。文件一变(用户恢复了备份)立刻重试;不变则等 300s
再试一次。这是"隔离但不永久放弃"的标准写法。判据在
`gateway/kanban_watchers.py:1172-1182 @ 863e313`(既认自定义 `KanbanDbCorruptError`,
也认 sqlite 的两条文案)。

---

## 3. R7 移交项:评论 → steer 注入的完整证据链(重点)

### 3.0 结论先行:**A6 的移交定位错了**

R7 `notes/r7-90-doc-conflict-rulings.md` A6 写:"kanban 评论 steer 注入侧
(kanban_watchers.py)移交 R7C"。

**代码事实**:`gateway/kanban_watchers.py` 全文 1493 行**没有任何 `steer` 字样**,
也不读 `task_comments` 表。全仓 grep 证据:

```
$ grep -rn "steer" --include="*.py" . | grep -i kanban
./tests/tools/test_kanban_comment_injection.py:5,9,29,31,65,83,93,94,99,124
./tools/kanban_tools.py:339,354,355,363,411,413
```

评论 → steer 的实现在 **`tools/kanban_tools.py`(agent 侧,worker 进程内)**,
调用点在 **`run_agent.py:3710`**。网关的 kanban_watchers 走的是**另一条**注入路径
(wake → 合成 MessageEvent → **排队**,明确 **不 steer**)。

下面把两条链都钉死。

### 3.1 链 A(真正的 steer):worker 自轮询自己的评论

**场景**:你在 Telegram 里敲 `/kanban comment t_abcd "用 2026 schema,不是 2025"`。
此刻 `t_abcd` 的 worker 进程正跑到第 7 轮工具调用中间。你希望这句话**现在**就影响它,
而不是等它跑完、失败、你再 block→comment→unblock 重跑一遍。

**第 1 跳 · 触发时机 = agent 的活动心跳,而不是一个独立 loop。**
`run_agent.py:3666-3672 @ 863e313`(函数签名与 docstring 开头):

```python
    def _touch_activity(
        self,
        desc: str,
        *,
        provenance: Optional[ActivityProvenance] = None,
        force_persist: bool = False,
    ) -> None:
```

`run_agent.py:3701-3716 @ 863e313`:

```python
        if os.environ.get("HERMES_KANBAN_TASK"):
            try:
                from tools.kanban_tools import (
                    heartbeat_current_worker_from_env,
                    inject_new_comments_from_env,
                )
                heartbeat_current_worker_from_env()
                # Fold any new operator notes into the running turn (OUT-OF-BAND
                # steer) so the user can talk to a live task without a restart.
                inject_new_comments_from_env(self)
            except Exception:
                # Never let the bridge break the agent loop.  The function
                # already swallows exceptions internally; this outer guard
                # covers import-time failures (kanban_tools unavailable,
                # etc.) on niche deployment surfaces.
                pass
```

**为什么挂在 `_touch_activity` 上**:这是 R7 A6 里那口"单一进度钟"。`_touch_activity`
在整个 agent 侧有约 28 个调用点(`run_agent.py` 3 + `agent/chat_completion_helpers.py` 11
+ `agent/conversation_loop.py` 7 + `agent/tool_executor.py` 5 + `agent/codex_runtime.py` 1
+ `agent/stream_diag.py` 1),密度足够高、又天然只在"agent 还活着"时触发。
复用它 = 零新线程、零新 loop、和看门狗共用一钟。这是 A6 那条"三个消费者共用一钟"的
**第四个消费者**,R7 没数进去。

**第 2 跳 · 自门控 + 节流**(`tools/kanban_tools.py:362-370 @ 863e313`):

```python
    tid = os.environ.get("HERMES_KANBAN_TASK")
    if not tid or agent is None or not hasattr(agent, "steer"):
        return False
    global _comment_poll_last_attempt
    import time as _time
    now = _time.monotonic()
    if (now - _comment_poll_last_attempt) < _COMMENT_POLL_MIN_INTERVAL_SECONDS:
        return False
    _comment_poll_last_attempt = now
```

节流常量 6 秒(`tools/kanban_tools.py:338 @ 863e313`),注释解释了为什么比心跳的 60s 紧:

```python
# Live operator-note injection: poll the worker's task for new comments and
# fold them into the running agent via the OUT-OF-BAND steer channel, so a user
# can "talk to" a running kanban task without the block → comment → unblock
# dance (or a restart). Rate-limited on its own (tighter than the 60s heartbeat
# so notes land within a few seconds), watermarked per task id.
_COMMENT_POLL_MIN_INTERVAL_SECONDS = 6.0
```

`HERMES_KANBAN_TASK` 由 dispatcher spawn worker 时打进环境
(`hermes_cli/kanban_db.py:9019 @ 863e313`):

```python
    env["HERMES_KANBAN_TASK"] = task.id
```

所以这个函数在 CLI/网关主进程里永远是 no-op —— **只有 dispatcher 亲手拉起的 worker 会走这条路**。

**第 3 跳 · 水位线(watermark)= rowid,不是时间戳。**
`tools/kanban_tools.py:372-395 @ 863e313`:

```python
    seen = _comment_watermark.get(tid)
    try:
        kb, conn = _connect()
        try:
            rows = kb.list_comments_after(conn, tid, after_id=seen or 0)
        finally:
            ...
    except Exception:
        logger.debug("comment-inject: bridge failed", exc_info=True)
        return False

    if seen is None:
        # First poll for this task: seed past the existing thread, inject nothing.
        _comment_watermark[tid] = max((c.id for c in rows), default=0)
        return False
    if not rows:
        return False

    # Advance the watermark past everything we just read (including our own
    # notes) so nothing is re-injected next poll.
    _comment_watermark[tid] = max(c.id for c in rows)
```

内核侧点名了为什么用 rowid(`hermes_cli/kanban_db.py:3677-3686 @ 863e313`):

```python
def list_comments_after(
    conn: sqlite3.Connection, task_id: str, *, after_id: int = 0
) -> list[Comment]:
    """Return comments on ``task_id`` with ``id > after_id`` (ascending).

    Keyed on the monotonic rowid rather than ``created_at`` so a same-second
    burst can't be skipped. Used by the live worker bridge to fold new
    operator notes into a running task without a restart (see
    ``tools.kanban_tools.inject_new_comments_from_env``).
    """
```

**首次轮询只播种、不注入**——这一条是为了不和 `build_worker_context` 重复:worker 启动时
已经把全部历史评论读进 prompt 了,再 steer 一遍就是自己跟自己说话。

**第 4 跳 · 过滤自述 + 组装 steer 文本**(`tools/kanban_tools.py:397-409 @ 863e313`):

```python
    own = (os.environ.get("HERMES_PROFILE") or "").strip()
    fresh = [c for c in rows if (c.author or "").strip() != own and (c.body or "").strip()]
    if not fresh:
        return False

    lines = [f"- {c.author or 'operator'}: {c.body.strip()}" for c in fresh]
    note = (
        "New note"
        + ("s" if len(fresh) > 1 else "")
        + " on your kanban task from the operator (delivered mid-run). "
        + "Take it into account for the work you're doing right now:\n"
        + "\n".join(lines)
    )
```

注意水位线在**过滤之前**就已推进(395 行),所以 worker 自己写的评论也被吃掉水位,
不会下一跳再读一次。

**第 5 跳 · 落到 out-of-band steer 通道**(`tools/kanban_tools.py:410-414 @ 863e313`):

```python
    try:
        return bool(agent.steer(note))
    except Exception:
        logger.debug("comment-inject: steer failed", exc_info=True)
        return False
```

`AIAgent.steer` 的语义(`run_agent.py:3229-3240 @ 863e313`):

```python
    def steer(self, text: str) -> bool:
        """
        Inject a user message into the next tool result without interrupting.

        Unlike interrupt(), this does NOT stop the current tool call. The
        text is stashed and the agent loop appends it to the LAST tool
        result's content once the current tool batch finishes. The model
        sees the steer as part of the tool output on its next iteration.

        Thread-safe: callable from gateway/CLI/TUI threads. Multiple calls
        before the drain point concatenate with newlines.
```

**这就是"out-of-band"的确切含义**:不打断当前工具调用,不新开一轮,而是把文本追加到
**最后一条 tool result 的 content 里**。模型下一次 iteration 自然读到。这样做:
- 不破 prompt cache(不改历史消息,只在末尾追加);
- 不产生"用户消息"角色错位(它伪装成工具输出的一部分);
- 不与工具执行竞态(drain point 在 tool batch 结束后)。

**完整链条(链 A)**:

```
用户 /kanban comment t_abcd "…"
  → hermes_cli/kanban.py 写 task_comments 行(SQLite)
  → [worker 进程内] agent 干活 → _touch_activity(run_agent.py:3698)
  → HERMES_KANBAN_TASK 存在 → inject_new_comments_from_env(self)  (run_agent.py:3710)
  → 6s 节流通过 → list_comments_after(rowid > watermark)
  → 过滤掉 HERMES_PROFILE 自述 → 组装 note
  → agent.steer(note)  (run_agent.py:3229)
  → _pending_steer 暂存 → 当前 tool batch 结束 → 追加进最后一条 tool result
  → 模型下一轮 iteration 看到操作员的话
```

### 3.2 链 B(网关侧真正做的事):终态事件 → 通知 + wake,**明确不 steer**

**场景**:你在 Telegram 里 `/kanban create "抓一下竞品定价"`,该聊天自动订阅了这张卡。
40 分钟后 worker 完成。

**第 1 跳 · 事件筛选集**(`gateway/kanban_watchers.py:156-158 @ 863e313`):

```python
        # "status" covers dashboard drag-drop and `_set_status_direct()`
        # writes — surface those transitions to subscribers too.
        TERMINAL_KINDS = ("completed", "blocked", "gave_up", "crashed", "timed_out", "status", "archived", "unblocked", "block_loop_detected")
```

9 种。其中 `archived` / `unblocked` 被 claim 但**故意静默**
(`gateway/kanban_watchers.py:485-493 @ 863e313`):

```python
                        else:
                            # archived / unblocked are claimed by TERMINAL_KINDS
                            # (so the cursor advances past them and they can't
                            # wedge a later completed/blocked event behind an
                            # unclaimed row) but are intentionally SILENT: an
                            # archive needs no user ping, and unblocked is an
                            # internal transition. They are also excluded from
                            # _WAKE_KINDS below, so they never wake the creator.
                            continue
```

**为什么要 claim 一个不发的事件**:因为游标是单调的。如果 `unblocked` 不在 kinds 里,
它会一直卡在游标后面,后面真正需要发的 `completed` 就永远被挡住。这是"游标式去重"
必然带来的设计约束——**静默 ≠ 不消费**。

**第 2 跳 · 谁负责投递(多网关归属)**。这一段是全文最密的逻辑,
`gateway/kanban_watchers.py:144-148 @ 863e313`:

```python
        # Dispatch and delivery have separate ownership. A deployment may run
        # one dispatcher while each profile has its own gateway credentials;
        # those adapter-owning gateways must still poll and deliver their own
        # subscriptions. Legacy rows without a notifier_profile are visible
        # only while this process holds the actual singleton dispatcher lock.
```

`include_unowned = self._owns_kanban_dispatcher_lock()`(`gateway/kanban_watchers.py:198`)
—— 无 profile 戳的老订阅只归"真正拿着派单锁的那个网关"投递,所以两个网关不会抢。

平台粗筛(`gateway/kanban_watchers.py:209-226 @ 863e313`)的注释记了一个真实 bug:

```python
                    # Widen to every platform any secondary profile has live,
                    # not just the default profile's. This is only a coarse
                    # pre-filter to skip claiming events for subs nobody can
                    # possibly deliver — the precise per-profile check (via
                    # gateway/authz_mixin.py::_authorization_adapter, which
                    # forbids default-profile fallback) still runs at delivery
                    # time below, rewinding the claim if it resolves to None.
                    # Without this, a subscription owned by a secondary
                    # profile on a platform the DEFAULT profile never
                    # connected (e.g. beta owns discord, default doesn't) was
                    # dropped here before ever being claimed — no rewind
                    # applies to an unclaimed event, so it silently never
                    # retries.
```

**因果**:beta profile 独占 discord,default 没连 discord → 粗筛用 default 的平台集 →
beta 的 discord 订阅在 claim 之前就被 `continue` 掉 → 因为**没 claim 就没得 rewind**,
事件永远不会重试 → 用户永远收不到通知。修法是粗筛放宽到全 profile 并集,精确判定
下沉到投递点(382 行)并配 rewind。

投递用的适配器解析(`gateway/kanban_watchers.py:373-382 @ 863e313`):

```python
                    # Route via the SAME chokepoint the authorization path uses
                    # (gateway/authz_mixin.py::_authorization_adapter): a stamped
                    # profile with its own adapter-registry entry must be served
                    # by THAT profile's same-platform adapter and must NOT silently
                    # fall back to the default profile's adapter — otherwise a
                    # secondary profile's task notification is delivered by the
                    # wrong bot (the cross-profile mis-delivery this whole change
                    # exists to fix). The helper returns None only when the profile
                    # (or default) genuinely has no adapter for the platform.
                    adapter = self._authorization_adapter(plat, sub_profile or None)
```

**第 3 跳 · 文本渲染**(`gateway/kanban_watchers.py:406-493`),按 kind 分支,每条带
`board_tag` + `@assignee` 身份前缀(`gateway/kanban_watchers.py:408-412 @ 863e313`):

```python
                        # Identity prefix: attribute terminal pings to the
                        # worker that did the work. Makes fleets (where one
                        # chat subscribes to many tasks) legible at a glance.
                        who = (task.assignee if task and task.assignee else None)
                        tag = f"@{who} " if who else ""
```

`completed` 优先用事件 payload 里的 summary(worker 有意写的交接语),回落到
`task.result`(`gateway/kanban_watchers.py:413-434`);`block_loop_detected` 有专门的
"这条必须吵醒人"分支(`gateway/kanban_watchers.py:466-484 @ 863e313`):

```python
                        elif kind == "block_loop_detected":
                            # A task re-blocked for the same cause past the
                            # recurrence limit and was routed to `triage` for a
                            # human decision. This is the ONE transition that
                            # exists to force human attention, yet it emits no
                            # `blocked`/`status` event — so before adding it to
                            # TERMINAL_KINDS it produced zero notification and
                            # the task stalled in triage silently. Ping loudly.
```

**第 4 跳 · wake:把终态变成对创建者会话的一次输入**。这是链 B 与"注入"最接近的部分。

wake 文案由 i18n 组装(`gateway/kanban_watchers.py:620-647 @ 863e313`):

```python
                        task_terminal = task and task.status in {"done", "archived"}
                        _WAKE_KINDS = ("completed", "gave_up", "crashed", "timed_out", "blocked")
                        _wake_kinds = {ev.kind for ev in d["events"] if ev.kind in _WAKE_KINDS}
                        from gateway.wake import adapter_supports_push as _adapter_push_ok

                        _is_push_adapter = _adapter_push_ok(adapter)
                        _session_key = ""
                        _synth = ""
                        if _wake_kinds:
                            _session_key = getattr(task, "session_id", None) or ""
                        if _wake_kinds and _session_key:
                            ...
                            _synth = t(
                                "gateway.kanban.wake.message",
                                task_id=sub["task_id"],
                                status=_status,
                                title=_title,
                                assignee=_assignee,
                                board=board_slug,
                            )
```

模板(`locales/en.yaml:186 @ 863e313`):

```yaml
      message:             "[kanban] Task {task_id} {status}.\nTitle: {title}\nAssignee: @{assignee}\nBoard: {board}\n\nCheck the result or decide the next step."
```

`_WAKE_KINDS` 只有 5 种(比 `TERMINAL_KINDS` 少 `status` / `archived` / `unblocked` /
`block_loop_detected`)—— 只有"这一轮工作有结果了"才值得唤醒 agent。

推送型适配器的 wake 走合成事件(`gateway/wake.py:73-87 @ 863e313`):

```python
    if adapter_supports_push(adapter):
        if source is None:
            raise ValueError(
                "deliver_wake: push-capable adapter requires a SessionSource"
            )
        from gateway.platforms.base import MessageEvent, MessageType

        synth_event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            internal=True,
        )
        await adapter.handle_message(synth_event)
        return
```

**第 5 跳(关键) · `internal=True` 决定了它绝不 steer、绝不打断。**
`gateway/run.py:8867-8879 @ 863e313`:

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

这就是**与 R7 已读的 run.py 忙时策略机的衔接点**:`_handle_active_session_busy_message`
(`gateway/run.py:8742 @ 863e313`)对 internal 事件**第一件事就是 return False**,
在读 `_busy_input_mode` / `_busy_text_mode`(8884-8885)**之前**。

返回 False 后回到基座适配器(`gateway/platforms/base.py:5711-5716 @ 863e313`):

```python
            if self._busy_session_handler is not None:
                try:
                    if await self._busy_session_handler(event, session_key):
                        return
                except Exception as e:
                    logger.error("[%s] Busy-session handler failed: %s", self.name, e, exc_info=True)
```

继续下落,internal 事件不满足 debounce 候选条件
(`gateway/platforms/base.py:5156-5164 @ 863e313`,`not getattr(event, "internal", False)`),
于是走 else 分支入队(`gateway/platforms/base.py:5735-5748 @ 863e313`):

```python
            else:
                logger.debug(
                    "[%s] New message while session %s is active — queuing follow-up "
                    "(no interrupt, will cascade after current turn)",
                    self.name,
                    session_key,
                )
                merge_pending_message_event(
                    self._pending_messages,
                    session_key,
                    event,
                    merge_text=event.message_type == MessageType.TEXT,
                )
            return  # Don't process now - will be handled after current task finishes
```

**链 B 完整链条**:

```
worker 调 kanban_complete → task_events 写 completed 行
  → [网关] notifier tick(5s)→ count_notify_subs 非零 → connect(board)
  → claim_unseen_events_for_sub(BEGIN IMMEDIATE,推游标)
  → _authorization_adapter(plat, sub_profile) 解析出正确 profile 的 bot
  → adapter.send(chat_id, "✔ [board] @worker Kanban t_abcd done — …")
  → 有 artifacts → send_multiple_images / send_video / send_document
  → advance cursor
  → deliver_wake(合成 MessageEvent(internal=True), SessionSource)
  → adapter.handle_message → _handle_active_session_busy_message → internal → return False
  → base adapter: merge_pending_message_event(排队)
  → 当前回合结束后作为新一轮 cascade 执行
```

### 3.3 两条链的对照表(这是本轮最该记住的一张表)

| | 链 A:评论 steer | 链 B:终态 wake |
|---|---|---|
| 代码位置 | `tools/kanban_tools.py:350-414` + `run_agent.py:3710` | `gateway/kanban_watchers.py:620-772` + `gateway/wake.py` |
| 运行进程 | **worker 进程自己** | **网关进程** |
| 触发源 | agent 活动心跳 `_touch_activity`(无独立 loop) | notifier 后台 loop(5s) |
| 频率闸 | 6s 节流 | 5s tick |
| 去重 | 内存 watermark(comment rowid) | SQLite 游标 + 原子 claim |
| 目标 | **正在跑的那一轮**(mid-turn) | **创建者的会话**(下一轮) |
| 注入方式 | `agent.steer()` → 追加进最后一条 tool result | 合成 `MessageEvent(internal=True)` → 排队 |
| 会不会打断 | 不打断(定义上就是 out-of-band) | 不打断(internal 显式短路忙时策略机) |
| 跨进程? | 否(同进程内存 watermark) | 是(跨网关靠 SQLite 写锁串行) |

**设计取舍**:两条链都刻意选择了"绝不打断正在跑的回合"。区别在于**能不能等**:
操作员的纠偏必须**现在**生效(等下一轮就白跑 40 分钟),所以链 A 用 steer 挤进当前回合;
任务完成通知**可以等**(它本来就是新一件事),所以链 B 排队。这条判据("是纠偏还是新事件")
比"用什么技术手段"更值得迁移。

### 3.4 链 B 的送达保证:claim 先行带来的四种回滚

因为 claim 在发送之前(游标已推进),每条失败路径都必须显式处理,否则事件永久丢失。

**(a) 未知平台字符串 → 直接 advance 防止永久重放**
(`gateway/kanban_watchers.py:363-371 @ 863e313`):

```python
                    try:
                        plat = _Platform(platform_str)
                    except ValueError:
                        # Unknown platform string; skip and advance cursor so
                        # we don't replay forever.
                        await asyncio.to_thread(
                            self._kanban_advance, sub, d["cursor"], board_slug,
                        )
                        continue
```

**(b) 适配器在投递前断连 → rewind**(`gateway/kanban_watchers.py:383-395 @ 863e313`)。

**(c) `SendResult(success=False)` 也算失败**(`gateway/kanban_watchers.py:533-544 @ 863e313`):

```python
                            # A SendResult(success=False) without an exception
                            # (returned by push-capable adapters on a genuine
                            # transient failure) must count as a FAILED
                            # delivery — otherwise the cursor advances and the
                            # event is permanently lost. Adapters returning
                            # None (or anything non-SendResult shaped) keep
                            # the legacy "no exception == delivered" contract.
                            if getattr(_send_res, "success", True) is False:
                                raise RuntimeError(
                                    "adapter send() reported failure: "
                                    f"{getattr(_send_res, 'error', None) or 'unknown error'}"
                                )
```

**(d) 连续失败 12 次退订**(`gateway/kanban_watchers.py:171-180 @ 863e313`):

```python
        # Per-subscription send-failure counter. Adapter.send raising
        # means the chat is dead (deleted, bot kicked, etc.) — after N
        # consecutive send failures the sub is dropped so we don't spin
        # against a dead chat every 5 seconds forever.
        # Raised from 3 to 12 (~60s at the 5s tick cadence): now that a
        # reported SendResult(success=False) also lands here (see the
        # delivery loop below), a transient Telegram/API outage of a few
        # ticks must NOT permanently unsubscribe a live review-gate channel.
        # A genuinely dead chat still drops, just ~60s later — a fine trade
        # for an unattended gate where a false drop means silent work pileup.
        MAX_SEND_FAILURES = 12
```

**3→12 的因果**:引入 (c) 之后,一次几跳的 Telegram 抖动就能凑满 3 次失败,
把一个还活着的"人工评审门"频道永久退订 → 工作静默堆积。改成 12(~60s)后,
真死的聊天照样掉,只是晚 60 秒。

### 3.5 非推送适配器(api_server)的特例:wake 就是投递本身

`gateway/kanban_watchers.py:502-528 @ 863e313` 先跳过注定失败的 send:

```python
                        # Adapters with no push channel (the API server —
                        # ``supports_async_delivery = False``) can NEVER
                        # satisfy a text-send: ``send()`` always reports
                        # SendResult(success=False) by design (see
                        # ApiServerAdapter.send()). Treating that as a
                        # delivery failure would rewind/drop the subscription
                        # forever and — because the wake dispatch below lives
                        # in this loop's ``else`` clause — would also make the
                        # wake-on-completion path (the actual fix for the
                        # api_server wrong-session bug) unreachable. So for
                        # non-push adapters, skip the doomed send attempt
                        # entirely: there is nothing to text-notify, the
                        # creator is woken via the self-post below instead.
```

然后把 wake 提到 advance **之前**(`gateway/kanban_watchers.py:603-619 @ 863e313`):

```python
                    else:
                        # All text pings delivered (or intentionally skipped
                        # for non-push adapters, whose delivery is the wake
                        # self-post below). Whether the cursor may advance now
                        # depends on the adapter class:
                        #
                        # * push-capable: the text send WAS the delivery, so
                        #   advance immediately (pre-existing behavior); the
                        #   wake injection below stays best-effort.
                        # * non-push (api_server): the wake self-post IS the
                        #   delivery. Advancing first would let a failed /
                        #   retry-exhausted self-post (swallowed by the
                        #   best-effort except) permanently lose the event.
                        #   So the self-post runs FIRST and the cursor only
                        #   advances after it succeeds — a failure rewinds the
                        #   claim exactly like a failed send() above, so the
                        #   next tick retries.
```

self-post 的原因(`gateway/wake.py:10-20 @ 863e313`):

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

**事故经过复述**:api_server 上创建的 kanban 任务完成后,网关照老路 wake
→ `handle_message` 用 `build_session_key()` 造出 `agent:main:api_server:group:<sid>`
→ 而真实客户端的会话键是原始 `X-Hermes-Session-Id` → wake 落进一个平行的、
没人看的会话 → 用户永远看不到"任务完成了"。修法是走 HTTP 自 POST 回自己的
`/v1/chat/completions`,带原始 session id 头,即"用真实入口叫醒真实会话"。

### 3.6 推送型适配器的 wake:chat_type 必须从订阅行还原(#56580)

`gateway/kanban_watchers.py:717-738 @ 863e313`:

```python
                                # Rebuild the creator's real session scope from
                                # the chat_type persisted on the subscription
                                # row (#56580). build_session_key() keys DMs
                                # (":dm:<chat_id>") on a wholly different shape
                                # from group/thread, so the old hardcoded
                                # "group" mis-routed DM/thread creators into a
                                # fresh session. Legacy rows written before the
                                # column existed may still carry chat_type in
                                # delivery_metadata (#60600 rows) — fall back
                                # to that, then to "group" (the historical
                                # default that suits the dashboard/group flows).
                                # handle_message() get_or_create_session's the
                                # target, so a mismatch only ever degrades to a
                                # fresh session, never an exception.
```

三级回落:`sub["chat_type"]` → `delivery_metadata["chat_type"]` → `"group"`。
对应测试:`tests/gateway/test_kanban_notifier.py:356
test_notifier_wakeup_uses_subscription_chat_type`。

---

## 4. hooks.py 钩子系统 + builtin_hooks 的空壳之谜

### 4.1 全仓有**两套**互不相干的钩子系统(读代码时最容易混淆的一点)

| | 网关事件钩子(**本切片**) | 插件生命周期钩子 |
|---|---|---|
| 实现 | `gateway/hooks.py` `HookRegistry` | `hermes_cli/lifecycle.py` `invoke_hook` |
| 注册方式 | 扫描 `~/.hermes/hooks/*/`(HOOK.yaml + handler.py) | 插件 `register()` 里 `ctx.register_hook(...)` |
| 生效范围 | **只在网关进程**(CLI 不加载) | CLI + 网关都生效 |
| 事件名 | `agent:start` / `command:*` 这类冒号命名 | `pre_tool_call` / `post_llm_call` 这类下划线命名 |
| 返回值 | `emit` 丢弃;`emit_collect` 收集 | 各 hook 各自约定 |

文档明确区分(`website/docs/user-guide/features/hooks.md:358 @ 863e313`):

```
Gateway hooks only fire in the **gateway** (Telegram, Discord, Slack, WhatsApp, Teams). The CLI does not load gateway hooks. For hooks that work everywhere, use [plugin hooks](#plugin-hooks).
```

两者在同一次请求里都会出现:`handle_message` 里既调 `_invoke_hook("pre_gateway_dispatch", ...)`
(插件钩子,`gateway/run.py:14406-14412 @ 863e313`),又调 `self.hooks.emit("agent:start", ...)`
(网关钩子,`gateway/run.py:17540`)。

### 4.2 契约:发现 → 加载 → 注册 → 触发

**发现根目录在模块导入时固化**(`gateway/hooks.py:46-49 @ 863e313`):

```python
from hermes_cli.config import get_hermes_home


HOOKS_DIR = get_hermes_home() / "hooks"
```

这是模块级常量,`get_hermes_home()` 本身支持 contextvar override
(`hermes_constants.py:132-134 @ 863e313`),但因为在 import 时就求过值了,
**运行时切 profile 不会改变 HOOKS_DIR**。见 §8 ◇3。

**加载**(`gateway/hooks.py:81-160`),每个钩子目录必须同时有 `HOOK.yaml` 和 `handler.py`
(103-104),yaml 必须声明非空 `events`(113-116),handler 必须有顶层 `handle`(141-144)。

动态加载有一处非显然的必要步骤(`gateway/hooks.py:118-134 @ 863e313`):

```python
                # Dynamically load the handler module.
                # Register in sys.modules BEFORE exec_module so Pydantic /
                # dataclasses / typing introspection can resolve forward
                # references (triggered by `from __future__ import annotations`
                # in the handler). Without this, a handler that declares a
                # Pydantic BaseModel for webhook/event payloads fails at first
                # dispatch with "TypeAdapter ... is not fully defined".
                module_name = f"hermes_hook_{hook_name}"
                spec = importlib.util.spec_from_file_location(
                    module_name, handler_path
                )
                ...
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                try:
                    spec.loader.exec_module(module)
                except Exception:
                    sys.modules.pop(module_name, None)
                    raise
```

**事故复述**:钩子作者在 handler.py 顶上写 `from __future__ import annotations`
(现在几乎是习惯写法),再定义一个 Pydantic BaseModel 描述 webhook 载荷。
`exec_module` 之后 Pydantic 要解析前向引用,得从 `sys.modules[module.__name__]`
取模块全局名字空间——但那时模块还没进 `sys.modules` → 第一次 dispatch 时炸
"TypeAdapter … is not fully defined"。修法是**先注册后执行**,并在执行失败时回滚注册。

**通配匹配**(`gateway/hooks.py:162-173 @ 863e313`):

```python
    def _resolve_handlers(self, event_type: str) -> List[Callable]:
        """Return all handlers that should fire for ``event_type``.

        Exact matches fire first, followed by wildcard matches (e.g.
        ``command:*`` matches ``command:reset``).
        """
        handlers = list(self._handlers.get(event_type, []))
        if ":" in event_type:
            base = event_type.split(":")[0]
            wildcard_key = f"{base}:*"
            handlers.extend(self._handlers.get(wildcard_key, []))
        return handlers
```

只支持 `<base>:*` 一层通配。注意:同时订阅 `command:reset` 和 `command:*` 的同一个
handler 会被触发两次(无去重)。

**两种触发语义**:
- `emit`(`gateway/hooks.py:175-198`):丢弃返回值,纯观察者;
- `emit_collect`(`gateway/hooks.py:200-227`):收集非 None 返回值,用于决策式钩子。
  唯一生产消费者是 slash 命令策略(`gateway/run.py:15024-15057 @ 863e313`),
  支持 `allow` / `deny` / `handled` / `rewrite` 四种 decision。

两者都用同一条容错原则(`gateway/hooks.py:197-198 @ 863e313`):

```python
            except Exception as e:
                print(f"[hooks] Error in handler for '{event_type}': {e}", flush=True)
```

注意:用的是 `print` 而不是 `logger`。模块整体不 import logging——这是本切片里
唯一一个不走 logger 的模块,风格上与 kanban_watchers.py / platform_registry.py 不一致。

### 4.3 实际触发点(全仓 grep,`emit` 的生产调用点)

| 事件 | 触发点 | 备注 |
|---|---|---|
| `gateway:startup` | `gateway/run.py:11378` | `discover_and_load()` 在 `gateway/run.py:10987` |
| `session:start` | `gateway/run.py:16408` | |
| `session:end` | `gateway/slash_commands.py:238` | `/new`、`/reset` |
| `session:reset` | `gateway/slash_commands.py:245` | |
| `agent:start` | `gateway/run.py:17540` | |
| `agent:step` | `TurnRunner._step_callback_sync`(`gateway/run.py:4323-4348`) | 线程 → loop 桥 |
| `agent:end` | `gateway/run.py:17788` | |
| `command:<name>` | `gateway/run.py:15024`(`emit_collect`) | 唯一的决策式钩子 |
| `reaction:added` / `reaction:removed` | `gateway/run.py:7196-7210` | 适配器经 `set_reaction_handler` 转发 |
| `session:compress` | `agent/conversation_compression.py:3479`、`agent/codex_runtime.py:253` | 经 `_event_callback_sync`(`gateway/run.py:4350-4358`)桥回 |

一处性能细节(`gateway/run.py:4869 @ 863e313`):

```python
        agent.step_callback = ctx._step_callback_sync if ctx._hooks_ref.loaded_hooks else None
```

**没装任何钩子时,`step_callback` 直接置 None**——每轮 tool loop 都要跑的回调,
不该为一个空列表付出跨线程调度成本。

### 4.4 builtin_hooks 的空壳:不是遗留垃圾,是被**故意拆掉**的功能

事实一:`gateway/builtin_hooks/` 目录下只有 `__init__.py`,内容仅一行 docstring
(`gateway/builtin_hooks/__init__.py:1 @ 863e313`):

```python
"""Built-in gateway hooks that are always registered."""
```

事实二:该包在**全仓 Python 代码中零 import**。grep `builtin_hooks` 只命中三处:
自己(`gateway/builtin_hooks/__init__.py:1`)、方法名(`gateway/hooks.py:72`、`91`)、
测试的 patch 目标(`tests/gateway/test_hooks.py:32`)。**没有任何 `import ... builtin_hooks`**。

事实三:注册函数是空的(`gateway/hooks.py:72-79 @ 863e313`):

```python
    def _register_builtin_hooks(self) -> None:
        """Register built-in hooks that are always active.

        Currently empty — no shipped built-in hooks. Kept as the extension
        point for future always-on gateway hooks so they drop in without
        re-plumbing discover_and_load().
        """
        return
```

事实四:**为什么空**——文档里有完整的因果
(`website/docs/user-guide/features/hooks.md:345-347 @ 863e313`):

```
#### Why this isn't a built-in

An earlier version of Hermes shipped this as a built-in hook and silently spawned an agent with bare defaults on every gateway boot. That surprised users with custom endpoints and made the feature invisible to users who didn't know it was running. Keeping it as a documented pattern — built by you, in your hooks directory — means you see exactly what it does and opt in by writing the files.
```

**事故复述**:早期 hermes 内置了一个 `gateway:startup` 钩子,每次网关启动就用**裸默认配置**
拉起一个 agent 跑 BOOT.md 清单。对自定义 endpoint 的用户,它拿错凭据/错模型静默开跑;
对不知情的用户,它是一笔看不见的开销。作者的处理不是"改好它",而是**整个删掉,降级成文档教程**
(`website/docs/user-guide/features/hooks.md:193-343` 是完整的 BOOT.md 自建教程)。
留下的 `builtin_hooks/` 空包 + 空方法,是"扩展点还在,货已下架"。

事实五:**AGENTS.md 是诚实的**(`AGENTS.md:249 @ 863e313`):

```
│   └── builtin_hooks/    # Extension point for always-registered gateway hooks (none shipped)
```

**结论:不是 ▲,不是死代码事故,而是一次"删功能保留插槽"的有意留白。**
与 R7 的 `memory_monitor.py`(零调用点休眠模块)**性质不同**:那个是有实现没接线;
这个是有插槽没实现,且文档、代码注释、目录结构三方一致。

---

## 5. platform_registry.py

### 5.1 解决什么问题

`gateway/platform_registry.py:1-10 @ 863e313`:

```python
"""
Platform Adapter Registry

Allows platform adapters (built-in and plugin) to self-register so the gateway
can discover and instantiate them without hardcoded if/elif chains.

Built-in adapters continue to use the existing if/elif in _create_adapter()
for now.  Plugin adapters register here via PluginContext.register_platform()
and are looked up first -- if nothing is found the gateway falls through to
the legacy code path.
...
```

### 5.2 与 R7B 读过的 `_create_adapter` 的确切关系:注册表优先,内建兜底

`gateway/run.py:13712-13758 @ 863e313`:

```python
    def _create_adapter(
        self, 
        platform: Platform, 
        config: Any
    ) -> Optional[BasePlatformAdapter]:
        """Create the appropriate adapter for a platform.

        Checks the platform_registry first (plugin adapters), then falls
        through to the built-in if/elif chain for core platforms.
        """
        ...
        # ── Plugin-registered platforms (checked first) ───────────────────
        try:
            from gateway.platform_registry import platform_registry
            if platform_registry.is_registered(platform.value):
                adapter = platform_registry.create_adapter(platform.value, config)
                if adapter is not None:
                    ...
                    adapter.gateway_runner = self
                    return adapter
                # Registered but failed to instantiate — don't silently fall
                # through to built-ins (there are none for plugin platforms).
                logger.error(
                    "Platform '%s' is registered but adapter creation failed "
                    "(check dependencies and config)",
                    platform.value,
                )
                return None
        except Exception as e:
            logger.debug("Platform registry lookup for '%s' failed: %s", platform.value, e)
        # Fall through to built-in adapters below
```

关键取舍:**"注册了但造不出来" ≠ "没注册"**。前者显式 `return None` 而不落回内建链,
因为插件平台在内建链里根本没有对应分支,继续走下去只会得到一个更迷惑的 "unknown platform"。

### 5.3 注册表存什么:`PlatformEntry` 的 20 个字段

`PlatformEntry`(`gateway/platform_registry.py:38-159`)不是"一个工厂",而是一张
**平台能力与集成点清单**。按用途归组:

| 组 | 字段 | 消费者 |
|---|---|---|
| 身份 | `name` `label` `emoji` `source` `plugin_name` | UI、日志、`plugin_entries()` 过滤 |
| 构造 | `adapter_factory` `check_fn` `validate_config` | `create_adapter`(278-328) |
| 状态 | `is_connected` | `GatewayConfig.get_connected_platforms()` |
| 安装/引导 | `required_env` `install_hint` `setup_fn` | `hermes setup` |
| 鉴权 | `allowed_users_env` `allow_all_env` | `gateway/authz_mixin.py:558-559` |
| 消息约束 | `max_message_length` `pii_safe` `allow_update_command` | 分片、会话描述脱敏、`/update` 白名单 |
| 模型引导 | `platform_hint` | `agent/system_prompt.py:440-441` |
| 配置桥 | `env_enablement_fn` `apply_yaml_config_fn` | `gateway/config.py:1004-1010`、`1493` |
| 带外投递 | `cron_deliver_env_var` `standalone_sender_fn` | `cron/scheduler.py:1008-1009`、`tools/send_message_tool.py:742` |

`standalone_sender_fn` 的存在理由值得单独记(`gateway/platform_registry.py:144-159 @ 863e313`):

```python
    # ── Standalone (out-of-process) sending ──
    # Optional: async coroutine that delivers a message without a live
    # gateway adapter.  Called by ``tools/send_message_tool._send_via_adapter``
    # when ``cron`` runs in a separate process from the gateway and the
    # in-process adapter weakref is therefore ``None``.
    ...
    # Without this hook, plugin platforms cannot serve as cron ``deliver=``
    # targets when the gateway is not co-resident with the cron process.
```

即:注册表不仅服务"网关进程内建适配器",还服务"cron 独立进程要给这个平台发消息"。

### 5.4 插件怎么进来:两阶段(延迟加载)

**为什么要延迟**(`gateway/platform_registry.py:171-183 @ 863e313`):

```python
        # Deferred platform loaders: name -> zero-arg callable that imports the
        # owning plugin module (which calls register() and populates _entries).
        #
        # Why this exists: platform adapter modules import heavy, platform-
        # specific SDKs at module level (lark_oapi, microsoft_teams, discord.py,
        # slack_bolt, ...). Eagerly loading all ~20 bundled platform plugins at
        # plugin-discovery time added several seconds to *every* `hermes`
        # invocation -- including plain `hermes chat`, which never touches any
        # gateway platform. Discovery now registers a cheap deferred loader per
        # platform; the real module is imported only when a registry lookup
        # actually asks for that platform (gateway start, cron delivery,
        # `hermes setup`/`gateway status`, send_message).
        self._deferred: dict[str, Callable[[], None]] = {}
```

**事故复述**:20 个内建平台插件各自在模块顶层 import 自己的重 SDK。插件发现阶段
一股脑全 import → 连 `hermes chat`(完全不碰网关)也要多等好几秒。修法是发现阶段
只登记一个零参 loader,真正 import 推迟到有人 `get(name)` / `create_adapter(name)`。

登记侧(`hermes_cli/plugins.py:1751-1754 @ 863e313`):

```python
        try:
            from gateway.platform_registry import platform_registry

            platform_registry.register_deferred(platform_name, _loader)
```

**关键设计点 · `is_registered` 不触发加载**(`gateway/platform_registry.py:271-276 @ 863e313`):

```python
    def is_registered(self, name: str) -> bool:
        # A deferred (not-yet-imported) platform still counts as registered --
        # the loader will materialize it on first real use.  This keeps cheap
        # membership checks (toolset resolution, webhook deliver-target checks)
        # from triggering a heavy import.
        return name in self._entries or name in self._deferred
```

这条是整个延迟机制能省下时间的前提:全仓有多处只想问"这平台存在吗"
(`toolsets.py:772-773`、`gateway/platforms/webhook.py:390-391`、`gateway/config.py:336-337`),
它们绝不能因为"问一句"就把 SDK 拉进来。

**解析(`_resolve`)只跑一次**(`gateway/platform_registry.py:202-215`),
pop 掉 loader 再执行,失败只 warning 不抛。
**迭代型访问器强制全解析**(`gateway/platform_registry.py:217-229 @ 863e313`):

```python
    def _resolve_all(self) -> None:
        """Run every pending deferred loader.

        Used by the iterate-all accessors (``all_entries``/``plugin_entries``),
        which are only called by paths that genuinely need every adapter:
        gateway startup, ``hermes setup``/``gateway status``, channel
        directory.  CLI chat never iterates the full set.
        """
        if not self._deferred:
            return
        # Snapshot keys -- loaders mutate _deferred as they resolve.
        for name in list(self._deferred):
            self._resolve(name)
```

`list(self._deferred)` 快照是必需的:loader 执行时会调 `register()`,而
`register()` 第一件事就是 `self._deferred.pop(entry.name, None)`
(`gateway/platform_registry.py:238`)——迭代中改字典会炸。

**覆盖语义**(`gateway/platform_registry.py:231-248 @ 863e313`):

```python
    def register(self, entry: PlatformEntry) -> None:
        """Register a platform adapter entry.

        If an entry with the same name exists, it is replaced (last writer
        wins -- this lets plugins override built-in adapters if desired).
        """
```

后写覆盖 + INFO 日志。允许插件覆盖内建适配器是有意为之。

**线程安全声明**(`gateway/platform_registry.py:162-167 @ 863e313`):

```python
class PlatformRegistry:
    """Central registry of platform adapters.

    Thread-safe for reads (dict lookups are atomic under GIL).
    Writes happen at startup during sequential discovery.
    """
```

注意这条声明与延迟加载**有张力**:`_resolve` 是**读路径触发的写**(pop + loader 里的
register)。如果两个线程同时 `get()` 同一个未解析平台,`self._deferred.pop(name, None)`
是原子的,所以只有一个线程拿到 loader、另一个拿到 None 直接返回 `_entries.get(name)` ——
可能返回 None(loader 还没跑完)。属于良性竞态但与 docstring 的"写只在启动时"不完全相符。
生产路径都是单线程启动顺序调用,未见实际影响。见 §8 ◇4。

单例(`gateway/platform_registry.py:331-332 @ 863e313`):

```python
# Module-level singleton
platform_registry = PlatformRegistry()
```

---

## 6. cwd_placeholder.py

### 6.1 解决什么问题:一个占位符在三种 backend 下有三种正确答案

`gateway/cwd_placeholder.py:1-8 @ 863e313`:

```python
"""Resolve gateway ``terminal.cwd`` placeholder values to ``TERMINAL_CWD``.

When ``terminal.cwd`` is unset or a placeholder (``.``, ``auto``, ``cwd``),
the gateway must not blindly map host ``Path.home()`` into container backends.
Docker with workspace mounting still needs an explicit host path signal
(``MESSAGING_CWD`` or an absolute config path) for ``terminal_tool`` to map
``/host/project`` → ``/workspace``.
"""
```

**场景**:用户在 config.yaml 里写 `terminal: {cwd: "."}`,意思是"用当前目录"。
- backend=local:"." 应该解析成宿主机的一个真路径(`MESSAGING_CWD` 或 `~`);
- backend=docker + 不挂载:"." 应该**什么都不设**,让容器用它自己的默认工作目录——
  把宿主机 `~` 塞进容器是纯粹的错误映射;
- backend=docker + 挂载 workspace:需要宿主机的**真实路径**才能做
  `/host/project → /workspace` 的映射,所以只接受显式的 `MESSAGING_CWD`,
  不接受 `Path.home()` 兜底。

### 6.2 实现:一个纯函数,三分支

`gateway/cwd_placeholder.py:12`、`19-49 @ 863e313`:

```python
CWD_PLACEHOLDERS = frozenset({".", "auto", "cwd"})
```

```python
def resolve_placeholder_terminal_cwd(
    *,
    configured_cwd: str,
    terminal_backend: str,
    messaging_cwd: str | None,
    docker_mount_cwd_to_workspace: bool,
    home_fallback: str,
) -> str | None:
    """Return the ``TERMINAL_CWD`` value to set, or ``None`` to leave it unset.

    Cases:
      - **local** + placeholder → ``MESSAGING_CWD`` or ``home_fallback``
      - **docker** + placeholder + mount on + host ``MESSAGING_CWD`` → host path
        (for ``terminal_tool`` ``/workspace`` mapping)
      - **docker** + placeholder + mount off → ``None`` (sandbox default)
      - other non-local backends + placeholder → ``None``
    """
    if configured_cwd and configured_cwd not in CWD_PLACEHOLDERS:
        return configured_cwd

    backend = (terminal_backend or "local").strip().lower()
    if backend == "local":
        messaging = (messaging_cwd or "").strip()
        return messaging or home_fallback

    if backend == "docker" and docker_mount_cwd_to_workspace:
        messaging = (messaging_cwd or "").strip()
        if messaging and messaging not in CWD_PLACEHOLDERS:
            return messaging

    return None
```

设计要点:
- **纯函数,零副作用,零 import**(除 `__future__`)。所有环境变量读取都在调用方。
  这就是它能被单测 26 行覆盖完的原因。
- **返回 `Optional[str]`,`None` 语义是"删掉这个环境变量"而不是"用默认值"**。
  调用方必须区分。
- 有一个"占位符防复发"的二次检查:`messaging not in CWD_PLACEHOLDERS`(46 行)——
  `MESSAGING_CWD` 本身也可能被用户填成 `.`。
- `_truthy_env`(`gateway/cwd_placeholder.py:15-16`)定义了但**在本模块内未被调用**
  (布尔判断在调用方 `gateway/run.py:2333-2336` 就地做了)。这是一个小的模块内死代码。

### 6.3 在哪被替换:网关模块导入期(不是运行期)

`gateway/run.py:2318-2340 @ 863e313`(模块级,不在任何函数内):

```python
# Set terminal working directory for messaging platforms.
# config.yaml terminal.cwd is the canonical source (bridged to TERMINAL_CWD
# by the config bridge above).  Placeholder values are resolved per-backend —
# see gateway/cwd_placeholder.py for the three-case contract (local vs docker
# mount-off vs docker mount-on).  MESSAGING_CWD is a backward-compat fallback.
from gateway.cwd_placeholder import CWD_PLACEHOLDERS, resolve_placeholder_terminal_cwd

_configured_cwd = os.environ.get("TERMINAL_CWD", "")
if not _configured_cwd or _configured_cwd in CWD_PLACEHOLDERS:
    _resolved_cwd = resolve_placeholder_terminal_cwd(
        configured_cwd=_configured_cwd,
        terminal_backend=os.environ.get("TERMINAL_ENV", ""),
        messaging_cwd=os.getenv("MESSAGING_CWD"),
        docker_mount_cwd_to_workspace=os.getenv(
            "TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE", "false"
        ).lower()
        in {"true", "1", "yes"},
        home_fallback=str(Path.home()),
    )
    if _resolved_cwd is None:
        os.environ.pop("TERMINAL_CWD", None)
    else:
        os.environ["TERMINAL_CWD"] = _resolved_cwd
```

**唯一生产调用点**。放在 `import gateway.run` 的副作用里,是因为后续的
`from gateway.config import ...`(2342)以及所有工具模块在导入时就会读 `TERMINAL_CWD`。

### 6.4 未收编的同款逻辑(三处独立复刻)

同一套占位符判断在全仓另有三份**各自独立**的实现:

- `cli.py:650-656 @ 863e313`:`_CWD_PLACEHOLDERS = (".", "auto", "cwd")`(tuple)
- `tui_gateway/server.py:1432 @ 863e313`:`_CWD_PLACEHOLDERS = {".", "auto", "cwd"}`(set)
- `tests/cli/test_cwd_env_respect.py:10`:测试里又抄了一遍

`gateway/cwd_placeholder.py` 只统一了网关一路。见 §8 ◇5。

---

## 7. 接线核查(每文件的全仓生产调用点)

| 文件 | 生产调用点 | 结论 |
|---|---|---|
| `gateway/kanban_watchers.py` | `gateway/run.py:2377`(import)、`5759`(继承)、`11484`/`11490`(spawn);模块级函数 `_resolve_auto_decompose_settings` 经 `1341` 内部调用;`_acquire_singleton_lock` 经 `1012` | **已接线**,双 loop 均在 `start()` 中拉起 |
| `gateway/hooks.py` | `gateway/run.py:6225-6226`(实例化)、`10987`(discover)、9 处 emit(见 §4.3) | **已接线** |
| `gateway/builtin_hooks/__init__.py` | **零 import**(仅自身 + `gateway/hooks.py:72`/`91` 的同名方法 + `tests/gateway/test_hooks.py:32` 的 patch 目标) | **未接线的空壳包**;但为**有意保留的插槽**,`AGENTS.md:249` 已如实标注 |
| `gateway/platform_registry.py` | 30+ 处,覆盖 `gateway/`(run/config/session/pairing/authz/slash/relay/webhook/channel_directory)、`hermes_cli/`(main/plugins/gateway/status/platforms/web_server)、`cron/scheduler.py`、`tools/send_message_tool.py`、`agent/system_prompt.py`、`toolsets.py`、3 个平台插件 | **重度接线**,是全仓引用最广的注册表之一 |
| `gateway/cwd_placeholder.py` | `gateway/run.py:2323`(import)、`2327`(调用)—— **仅一处** | **已接线**,但仅覆盖网关路径;CLI/TUI 各有独立复刻 |

模块内死代码:`gateway/cwd_placeholder.py:15-16` 的 `_truthy_env` 定义后未被本模块调用。

---

## 8. ▲/◇ 候选

### ▲1. kanban.md 的终态事件清单缺 4 种(轻微,面向用户会误导)

- **文档**:`website/docs/user-guide/features/kanban.md:897 @ 863e313`:

```
When you run `/kanban create …` from the gateway (Telegram, Discord, Slack, etc.), the originating chat is automatically subscribed to the new task. The gateway's background notifier polls `task_events` every few seconds and delivers one message per terminal event (`completed`, `blocked`, `gave_up`, `crashed`, `timed_out`) to that chat. Completed tasks also send the first line of the worker's `--result` so you see the outcome without having to `/kanban show`.
```

- **代码**:`gateway/kanban_watchers.py:158 @ 863e313` 有 9 种:

```python
        TERMINAL_KINDS = ("completed", "blocked", "gave_up", "crashed", "timed_out", "status", "archived", "unblocked", "block_loop_detected")
```

其中 `status`(`gateway/kanban_watchers.py:461-465`)与 `block_loop_detected`
(`466-484`)**会真的发消息**;`archived` / `unblocked` 静默(485-493)。
- **裁决 ▲**:文档漏列 2 种会发消息的事件。用户看不到"仪表盘拖卡 → 收到 🔄 状态通知"
  和 "🛑 routed to TRIAGE" 的来源说明。以代码为准。

### ◇1. kanban 完成会**唤醒创建者的 agent 会话**——文档全无

- **代码**:`gateway/kanban_watchers.py:620-772 @ 863e313` 的 wake 分支;
  `gateway/wake.py:56-94`;推送型走合成 `MessageEvent(internal=True)`,
  非推送型走 `/v1/chat/completions` 自 POST。
- **文档**:`website/docs/user-guide/features/kanban.md` 的 "Gateway notifications"
  一节(895-935)只讲"发一条消息到聊天",全篇无 wake / 唤醒 / 新回合的说法;
  `docs/kanban/multi-gateway.md` 同样只讲投递归属。
- **为什么这是重要遗漏**:wake 会让创建者的 agent **真的跑一轮**(消耗 token、可能调工具)。
  这是有成本、有副作用的行为,而不是一条通知。
- **裁决 ◇**:代码有、文档无,且是用户可感知的成本行为。

### ◇2. "评论 mid-run steer" 是完整实现的功能,但用户文档只描述了旧的 block→comment→unblock 流程

- **代码**:`tools/kanban_tools.py:338-414 @ 863e313`,配套测试 3 条。
- **文档**:`website/docs/user-guide/features/kanban.md:836 @ 863e313`:

```
- You spot a card that needs human context → `/kanban comment t_xyz "use the 2026 schema, not 2025"` lands on the task thread and the *next* run of that task will read it in `kanban_show()`.
```

  文档明确说"**下一次运行**才会读到"。而代码里 worker 每 6 秒轮询一次,**当前运行中**就会
  以 steer 形式吃进去(前提是该 worker 由 dispatcher 拉起、`HERMES_KANBAN_TASK` 已设)。
  `website/docs/user-guide/features/kanban.md:64` 也只写 "when a worker is (re-)spawned it reads the full comment thread"。
- **裁决 ◇ 偏 ▲**:代码能力强于文档承诺。严格说 836 行的断言在"worker 正在跑"这个情形下
  **是失实的**(不是"next run",是"this run")。但它没有说错方向,只是漏说了更强的行为。
  记为 ◇(代码有而文档无),并在此标注该句的适用边界。

### ◇3. `HOOKS_DIR` 在模块导入期固化,profile 级 override 对它无效

- **代码**:`gateway/hooks.py:49 @ 863e313`:

```python
HOOKS_DIR = get_hermes_home() / "hooks"
```

  而 `get_hermes_home()`(`hermes_constants.py:132-139`)支持 contextvar override:

```python
    override = get_hermes_home_override()
    if override:
        return Path(override)
```

- **影响**:网关进程一旦 import 了 `gateway.hooks`,钩子目录就钉死。任务级 HERMES_HOME
  override 不会让它去读另一个 profile 的钩子。对网关(单 profile 单进程)无实际问题,
  但这是一条隐式约束,而 docstring(`gateway/hooks.py:5`)只说
  "Hooks are discovered from ~/.hermes/hooks/ directories",没有点明"导入期定死"。
- **裁决 ◇**:未文档化的隐式约束。

### ◇4. `PlatformRegistry` 的线程安全 docstring 与延迟加载有张力

- **docstring**(`gateway/platform_registry.py:165-166 @ 863e313`):

```python
    Thread-safe for reads (dict lookups are atomic under GIL).
    Writes happen at startup during sequential discovery.
```

- **代码**:`get()`(255-259)、`create_adapter()`(287-289)、`is_registered` 之外的每条
  读路径都可能触发 `_resolve()`,而 `_resolve` 会 `self._deferred.pop(...)` 并执行 loader,
  loader 里调 `register()` 写 `self._entries`。**读路径会写**。
- **影响**:两线程并发首次 `get("discord")` 时,一个跑 loader,另一个可能在 loader 完成前
  返回 None。属良性(调用方对 None 都有处理),但 docstring 的"写只发生在启动期顺序发现"
  在延迟加载引入后已不准确。
- **裁决 ◇**(轻微,docstring 滞后于机制)。

### ◇5. cwd 占位符逻辑三处独立复刻,只有网关一路被收编

- `gateway/cwd_placeholder.py:12`(frozenset,含三分支 backend 逻辑)
- `cli.py:650`(tuple,无 backend 分支)
- `tui_gateway/server.py:1432`(set,无 backend 分支)
- **影响**:CLI / TUI 走的是"占位符 → 直接兜底"的旧两分支逻辑,没有 docker
  mount-off → `None` 的处理。三者行为在 docker backend 下不一致。
- **裁决 ◇**:代码事实,无文档提及。

### 非冲突(核对后确认地图诚实,记录以免下轮重复排查)

- `AGENTS.md:249` 对 `builtin_hooks/` 的描述 "(none shipped)" **准确**。
- `docs/kanban/multi-gateway.md:8-18` 的"单派单 + profile 归属投递"与
  `gateway/kanban_watchers.py:144-148`/`198` 完全一致。
- `gateway/platform_registry.py:7-8` 的 "Built-in adapters continue to use the existing if/elif
  ... for now" 基本准确,但有**一个例外**:`relay` 是以 `source="builtin"` 注册进注册表的
  (`gateway/relay/__init__.py:879-888 @ 863e313`):

```python
    platform_registry.register(
        PlatformEntry(
            name="relay",
            label="Relay",
            adapter_factory=_factory,
            check_fn=lambda: True,
            source="builtin",
            emoji="\U0001f50c",
        )
    )
```

  它因此被 `plugin_entries()`(`gateway/platform_registry.py:266-269`,过滤 `source == "plugin"`)
  排除在插件列表外,但走 `_create_adapter` 的注册表分支。属"docstring 略滞后",
  影响极小,记为 ▲-轻微/边缘,不单列。

---

## 9. issue 溯源

本切片文件内出现的 issue 编号(`grep -on "#[0-9]\{3,6\}"` 全量):

| 编号 | 行号 | 因果经过 |
|---|---|---|
| **#49638** | `gateway/kanban_watchers.py:33`、`:38`、`:1331`、`:1440` | auto-decompose 的开关在网关启动时被捕获一次。用户还在**输入任务描述**的过程中,自动分解器就把它拆成子任务并派单跑了破坏性操作;用户把 `kanban.auto_decompose` 改成 false 想紧急停车,却"关不掉"——网关用的仍是启动时的旧值,必须重启网关才生效。修法:每跳重读配置(`_resolve_auto_decompose_settings`,28-57),且**读失败时 fail-safe 返回 `(False, 3)`**,绝不因一次读错把用户关掉的功能又打开。 |
| **#22941** | `gateway/kanban_watchers.py:166` | (被引用为同形 bug 的先例)`blocked` 事件发出后就退订,导致 unblock 再 block 的循环里用户只收到第一次。当前代码把这个教训推广到全部非终态事件:只有 `done`/`archived` 才退订。 |
| **#21378** | `gateway/kanban_watchers.py:293`、`:1224` | `connect()` 首次打开已跑过 schema + 幂等迁移;旧代码又显式调 `init_db()`,后者会**故意清掉进程内缓存**并在**第二条连接**上重跑迁移,与第一条竞争 → 每次网关对着 legacy DB 启动都刷一条 `duplicate column name` traceback,还间歇报 "database is locked"。修法:`_add_column_if_missing` 容忍该竞态,同时**删掉这次多余调用**。 |
| **#56580** | `gateway/kanban_watchers.py:719` | wake 时 `chat_type` 曾被硬编码成 `"group"`。`build_session_key()` 对 DM 用完全不同的形状(`:dm:<chat_id>`),于是 DM/thread 里创建任务的用户被 wake 到一个**全新的空会话**里,看不到上下文。修法:从订阅行持久化的 `chat_type` 列还原。 |
| **#60600** | `gateway/kanban_watchers.py:725` | 上一条的兼容尾巴:`chat_type` 列存在之前写入的老订阅行,`chat_type` 可能藏在 `delivery_metadata` 里。三级回落 `sub.chat_type → delivery_metadata.chat_type → "group"`。 |
| **#27145** | `gateway/kanban_watchers.py:1101` | 从仪表盘创建的卡片没有 assignee,dispatcher 永远跳过它们(无限滞留 ready)。引入 `kanban.default_assignee` 作为兜底路由 profile;空串(schema 默认)= 保持旧的"继续跳过"行为,向后兼容。 |
| **#21582** | `gateway/kanban_watchers.py:1113` | 全局 `max_in_progress` 挡不住"某一个 profile 被扇出打爆":该 profile 的本地模型 / API 配额 / 浏览器池是它自己的瓶颈。引入 `kanban.max_in_progress_per_profile` 做每 profile 并发帽。 |

`hooks.py` / `platform_registry.py` / `cwd_placeholder.py` / `builtin_hooks/__init__.py`
四个文件内**无 issue 编号引用**。

相邻但对本切片理解必要的编号(在其他文件):
- **#72016 / #72039**(`run_agent.py:3683`):单一活动观测源契约——链 A 挂靠的那口钟。
- **#31752**(`run_agent.py:3675-3679`):`_touch_activity` 桥接 kanban 心跳字段,
  防止 dispatcher 看门狗把正在干活的 worker 当 stale 回收。链 A 与它同一处代码。
- **#18594**(`hermes_constants.py:130`):`get_hermes_home` 的 profile 回退告警,
  与 ◇3 相关。

---

## 10. 测试

### 10.1 本切片对应测试文件

| 测试文件 | 行数 | 覆盖 | 用例 |
|---|---|---|---|
| `tests/gateway/test_kanban_watchers_mixin.py` | 28 | mixin 方法齐备性(拆分后防回归) | 1 |
| `tests/gateway/test_kanban_notifier.py` | 518 | 通知主路径 | 8 |
| `tests/gateway/test_kanban_notifier_apiserver_wake.py` | 138 | 非推送适配器 self-post wake | 1 |
| `tests/gateway/test_kanban_notifier_zero_sub_gate.py` | 85 | 零订阅只读探针不做可写打开 | 1 |
| `tests/gateway/test_kanban_notifier_watcher_dispatch_gate.py` | 46 | 非派单网关照样投递自己的订阅 | 1 |
| `tests/gateway/test_kanban_auto_decompose_live.py` | 29 | `_resolve_auto_decompose_settings` 纯函数 | 2 |
| `tests/gateway/test_hooks.py` | 142 | HookRegistry 全部四个能力 | 7 |
| `tests/gateway/test_platform_registry.py` | 496 | 注册表 + 配置桥 + 插件闸门 | 18 |
| `tests/gateway/test_cwd_placeholder.py` | 26 | 纯函数两分支 | 2 |
| `tests/gateway/test_config_cwd_bridge.py` | — | 配置桥到 TERMINAL_CWD 的端到端 | — |
| `tests/tools/test_kanban_comment_injection.py` | 124 | **链 A(评论 steer)** | 3 |

### 10.2 实跑结果(基线 863e313)

```
$ HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
    tests/gateway/test_hooks.py tests/gateway/test_platform_registry.py \
    tests/gateway/test_cwd_placeholder.py tests/gateway/test_kanban_watchers_mixin.py
=== Summary: 4 files, 28 tests passed, 0 failed (100% complete) in 3.3s (8 workers) ===

$ ... tests/gateway/test_kanban_notifier.py tests/gateway/test_kanban_notifier_apiserver_wake.py \
      tests/gateway/test_kanban_notifier_zero_sub_gate.py \
      tests/gateway/test_kanban_notifier_watcher_dispatch_gate.py \
      tests/gateway/test_kanban_auto_decompose_live.py tests/tools/test_kanban_comment_injection.py
=== Summary: 6 files, 16 tests passed, 0 failed (100% complete) in 2.5s (8 workers) ===
```

全绿,共 44 条。

### 10.3 当行为规格读:最有信息量的几条

**链 A 的三条规格**(`tests/tools/test_kanban_comment_injection.py:1-9 @ 863e313`):

```python
"""Live operator-note injection into a running kanban worker.

``tools.kanban_tools.inject_new_comments_from_env`` polls the worker's task
for comments added *after* the run started and folds them into the live turn
via the agent's OUT-OF-BAND steer channel — so a user can talk to a running
task without the block→comment→unblock dance or a restart.

Verifies: no-op off a worker, watermark seeding (history isn't re-injected),
new comments steer, and own-authored comments are skipped.
"""
```

其 `FakeAgent`(`tests/tools/test_kanban_comment_injection.py:27-33 @ 863e313`)
把契约钉成一个方法:

```python
class FakeAgent:
    def __init__(self):
        self.steers: list[str] = []

    def steer(self, text: str) -> bool:
        self.steers.append(text)
        return True
```

**注入侧对 agent 的唯一要求就是 `steer(text) -> bool`**。这也解释了
`tools/kanban_tools.py:363` 的 `not hasattr(agent, "steer")` 自门控。

**wake 的两条规格**(`tests/gateway/test_kanban_notifier_apiserver_wake.py:1-10 @ 863e313`):

```python
"""Kanban notifier behavior on stateless (api_server) subscriptions.

Covers the wrong-session-wake / silent-loss fixes:
* a SendResult(success=False) return (the API server's send() stub) rewinds
  the cursor instead of advancing past a never-delivered event;
* api_server subscriptions wake the creator's REAL session via the
  /v1/chat/completions self-post (raw task.session_id), never via
  handle_message (which would run under a build_session_key()-derived key
  that never matches the raw X-Hermes-Session-Id session real turns use).
"""
```

**mixin 拆分的防回归规格**(`tests/gateway/test_kanban_watchers_mixin.py:1`,
"Tests for the extracted GatewayKanbanWatchersMixin (god-file Phase 3)"):它只断言
6 个方法名在 mixin 上存在(`:14-26`)。这是一条**结构契约测试**——保证 run.py 里的
`self._kanban_*` 调用点不会因为搬家而 AttributeError。

### 10.4 测试里暴露的隐式契约(重实现时必须复现)

`tests/gateway/test_kanban_notifier_apiserver_wake.py:67-73 @ 863e313` 用
`object.__new__` 造 runner,只补 5 个字段:

```python
def _make_runner(adapters):
    runner = GatewayRunner.__new__(GatewayRunner)
    runner._running = True
    runner.adapters = adapters
    runner._kanban_sub_fail_counts = {}
    runner._kanban_dispatcher_lock_handle = object()
    return runner
```

**这 5 个字段(加上 `_profile_adapters`、`_authorization_adapter`、`_active_profile_name`
的 getattr 兜底)就是 notifier 对宿主类的全部依赖面。** mixin 没有 `__init__`,
契约只存在于 getattr 默认值和这个测试 fixture 里。

---

## 11. 重实现要点

写自己的 harness 时,本切片值得原样搬走的设计:

1. **后台 loop 一律走"监督器 + 干净返回不重启"**。
   自禁用型 watcher(配置关、锁被占)必须能干净返回,监督器必须能区分
   "干净返回 = 我不该跑" 与 "异常 = 重启我"。否则每个 gate 都会变成忙等。
   参考 `gateway/run.py:11625-11630`。

2. **多进程共享队列的通知,去重用"每订阅游标 + `BEGIN IMMEDIATE` 原子推进",不用内存表。**
   直接得到跨进程语义,零协调协议。代价是 claim 先于送达,所以**每一条失败路径都必须
   显式 rewind**——包括"适配器返回 success=False 但没抛异常"这种最容易漏的。
   参考 `hermes_cli/kanban_db.py:9902-9950` + `gateway/kanban_watchers.py:363-598`。

3. **"必须消费但不发送"的事件要显式建模。**
   单调游标一旦漏掉某类事件,它就成了后续事件的路障。`archived`/`unblocked`
   进 `TERMINAL_KINDS` 但走 `continue`(`gateway/kanban_watchers.py:485-493`)
   是这个约束的标准解法。

4. **把"打断策略"和"注入通道"分开设计,判据是"这条输入能不能等到下一轮"。**
   - 能等(任务完成通知)→ 合成事件 + 排队,且用一个显式的 `internal` 标志
     在忙时策略机的**最开头**短路掉一切打断/steer 逻辑
     (`gateway/run.py:8867-8879`);
   - 不能等(操作员纠偏)→ out-of-band steer,追加到最后一条 tool result,
     不打断工具、不破 cache、不产生角色错位(`run_agent.py:3229-3263`)。

5. **带外注入不要新开 loop,挂到已有的活动心跳上。**
   `_touch_activity` 已经是"agent 还活着"的高频信号,复用它 = 零新线程、
   与看门狗共用一钟、天然只在 agent 存活时轮询。自带节流常量与心跳分离
   (6s vs 60s),因为两者的时效要求不同(`tools/kanban_tools.py:343`)。

6. **带外注入的水位线用单调 rowid,不用时间戳**,且**首次只播种不注入**
   (历史已在初始 prompt 里)。同秒突发不会漏,重启后自然重新播种。

7. **注册表要区分"存在性查询"与"实体化"。**
   `is_registered` 命中延迟表就返回 True 而不触发 import
   (`gateway/platform_registry.py:271-276`),否则延迟加载省下的时间会被
   "问一句"的调用点全部吐回去。

8. **每个平台条目存的不该只是工厂,而是一张集成点清单**——鉴权 env 名、
   消息长度上限、system prompt 提示、cron 投递 env、脱离网关的独立发送器。
   这样新平台"接入所有子系统"是填字段,而不是改 N 个 if/elif。

9. **"占位符解析"要做成纯函数,返回 `Optional`,`None` 明确表示"不设"**。
   容器化 backend 下"不设"和"设成宿主机 home"是两种完全不同的行为,
   用 `None` 而不是空串来表达,调用方才会被迫处理它
   (`gateway/run.py:2337-2340` 的 `os.environ.pop`)。

10. **删功能时保留插槽是可以的,但要三方一致**:空目录 + 空方法 + docstring 说明
    "currently empty, kept as extension point" + 项目地图标注 "(none shipped)"
    + 用户文档写清"为什么不再内置"。`builtin_hooks` 这一组做到了四项俱全,
    所以它不是黑洞。反例是 R7 的 `memory_monitor.py`(有实现、零调用、无说明)。

11. **钩子系统的两个非显然实现细节**:
    - 动态加载 handler 前**先进 `sys.modules` 再 `exec_module`**,
      否则 `from __future__ import annotations` + Pydantic 会在首次 dispatch 时炸;
    - **没装钩子就把回调置 None**(`gateway/run.py:4869`),不要让空列表的遍历
      进入每轮 tool loop。
