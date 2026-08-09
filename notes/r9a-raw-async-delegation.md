# r9a 底稿 · 异步委派、子代理生命周期与实时日志

> 研究对象基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(只读)。
> 溯源约定:凡对代码行为的断言,**锚点单独成行、置于代码块之前**,格式 `路径:行号 @ 863e313`。
> 本文是底稿(证据层),求全求证、允许啰嗦。下表的行号列**不带冒号**,是索引不是证据——
> 让引用校验器只对「锚点 + 紧跟的块」这一种形状计数。
> 我自己跑的命令/输出用 ```verify / ```console / ```text 围栏声明,不是基线源码。

**本簇 4 个文件 / 2,640 行(`wc -l` 实测):**

| 文件 | 行数 | 一句话职责 |
|---|---|---|
| `tools/async_delegation.py` | 1515 | 后台委派登记处:内存记录 + SQLite 持久化 + 投递认领 + 停滞监控 |
| `agent/subagent_lifecycle.py` | 540 | 给**插件**用的公开子代理生命周期 API(句柄 / 状态 / 取消 / 结果) |
| `tools/delegation_live_log.py` | 424 | 每个子代理一份可 `tail -f` 的追加式实时转录 |
| `agent/delegation_context.py` | 161 | 「我是不是一个被委派的子代理」这一身份位(ContextVar + 环境变量) |

**交界处(不越界逐行读)**:`tools/delegate_tool.py` 是同步委派主干,本文只把
**接口形状**写清楚(谁调谁、传什么、返回什么),内部实现留给读该文件的同伴。

---

## 0. TL;DR(9 条)

1. **模型不能选同步还是异步**。顶层模型发起的 `delegate_task` **一律**走后台;
   `background` 这个参数在模型看得见的 schema 里被标为 `DEPRECATED / IGNORED`。
   唯一例外:orchestrator 子代理(depth > 0)发起的委派强制同步。
2. **异步的单位是「一次 dispatch」,不是「一个子代理」**。一个 N 路 fan-out 批次
   占**一个**异步槽,内部并行由另一个池负责,最后合成**一条**完成事件回到对话。
3. 调用方拿到的不是 future 也不是可轮询的任务 id,而是一个 `delegation_id` +
   一句「别等别轮询,继续干活」。结果**自己回来**——通过共享的
   `process_registry.completion_queue`,在 agent 空闲时被消费成一个**新轮次**。
4. 「结果自己回来」这条轨道是**跨进程持久**的:SQLite 表 `async_delegations`
   记录每次派发的 owner pid,进程重启后按 pid 存活性把无主记录判为 `unknown`
   并重放。**在跑的子代理不持久,结果的投递才持久。**
5. 没有墙钟超时。取而代之的是**基于进度**的停滞监控:进度令牌冻结超阈值 →
   打断 → 120s 宽限 → 仍不返回则强制发一条终局 `stalled` 事件。
6. 背压是**拒绝**不是排队:满员时 dispatch 返回 `rejected`,调用方回落同步执行。
7. `subagent_lifecycle.py` 是**另一套**登记处,给插件用,与 `async_delegation`
   **完全不互通**:`/stop`、会话结束收割都够不着它;它也**没有并发上限**。
8. 实时日志一子任务一文件,写前过一遍强制脱敏;但**脱敏发生在「压成一行」之后**,
   行锚定的规则因此失效(■,可复现)。
9. `delegation_context.py` 用 ContextVar 做身份位,并在跨 `fork` 时降级成
   环境变量标记——它解决的是「父进程是 Kanban worker,子代理不该继承那个身份」。

---

## 1. 一次具体走法:用户说「帮我并行调研三个方案」

先把整条路演一遍,后面每节再拆。

1. 模型调 `delegate_task(tasks=[{goal:A},{goal:B},{goal:C}])`。
2. 注册表 handler 不看模型给的 `background`,自己算:非子代理 → `background=True`。
3. `delegate_task` 先建 3 份实时转录文件(带头部,立刻可 `tail -f`),
   再构造 3 个子 agent,拿到一个 `live_deleg_id`。
4. 判定这个会话**能不能事后收结果**(`async_delivery_supported()`)。不能且没有
   可自投的 session id → **整批回落同步执行**,并在结果里附一句说明。
5. 能 → 把 3 个子 agent 从父 agent 的 `_active_children`(打断传播表)里**摘掉**,
   然后把「跑完整批并聚合」这个闭包交给 `dispatch_async_delegation_batch`。
6. 登记处在**一把锁内**做容量检查 + 插记录,写 SQLite 一行 `state='running'`,
   把闭包丢上守护线程池,**立即返回** `{"status":"dispatched","delegation_id":...}`。
7. 工具返回给模型的是 `dispatched` + 3 条 `live_transcripts` 路径 + 一句
   「Do not wait or poll — just continue」。对话继续。
8. 3 个子代理在后台跑;停滞监控线程每 30s 采一次它们的合并进度令牌。
9. 全跑完 → 聚合成 `{"results":[...]}` → `_finalize_batch` 把记录标 `finalizing`
   → 写 SQLite(状态 + 完整事件 JSON)→ push 到 `completion_queue`。
10. CLI / gateway / TUI 的排空循环拿到事件,**先证明自己是主人**,再向 SQLite
    认领一次投递,成功了才把它变成一个新的用户轮次喂给 agent。

第 6 步的返回形状(注意 `background=true` 走的**不是**单发接口,见 §2.1):

`tools/delegate_tool.py:3337 @ 863e313`
```python
        dispatch = dispatch_async_delegation_batch(
            goals=_goals,
            context=context,
            # Metadata for the completion block only; subagents inherit the
            # parent's toolsets (no model-facing toolsets arg).
            toolsets=None,
            role=top_role,
            model=creds["model"],
            session_key=_session_key,
            origin_ui_session_id=_origin_ui_session_id,
            origin_session_id=_wake_sid,
            parent_session_id=_parent_session_id,
            runner=_batch_runner,
            interrupt_fn=_batch_interrupt,
            max_async_children=_get_max_async_children(),
            # Reuse the live-transcript directory's id (when created) so the
            # returned delegation_id matches cache/delegation/live/<id>/.
            delegation_id=live_deleg_id,
            progress_fn=_batch_progress,
```

第 5 步的「摘钩」是异步语义的关键动作——同步批次要跟着父轮次一起被打断,
异步批次的生命周期改由登记处拥有:

`tools/delegate_tool.py:3276 @ 863e313`
```python
        # batch's lifecycle is owned by the async registry now, not the parent
        # turn. _build_child_agent attached them (correct for sync runs).
        if hasattr(parent_agent, "_active_children"):
            _ac_lock = getattr(parent_agent, "_active_children_lock", None)
            for _c in _child_agents:
                try:
                    if _ac_lock:
                        with _ac_lock:
                            parent_agent._active_children.remove(_c)
                    else:
                        parent_agent._active_children.remove(_c)
                except ValueError:
```

**注入口(合作方)**:`runner` / `interrupt_fn` / `progress_fn` 三个闭包全部由
`delegate_tool` 提供。登记处**不知道**子代理长什么样,只知道「跑它 / 打断它 /
问它进度」。这是本模块最重要的解耦——模块头自己也这么说:

`tools/async_delegation.py:31 @ 863e313`
```python
This module owns ONLY the async lifecycle. The actual child build + run is
delegated back to ``delegate_tool._run_single_child`` via an injected
runner, so all the credential leasing, heartbeat, timeout, and result-shaping
logic stays in one place.
```

---

## 2. 异步与同步的分工

### 2.1 谁决定走异步 —— 不是模型

模型看得见的参数里确实有 `background`,但它的描述就是「别用」:

`tools/delegate_tool.py:3853 @ 863e313`
```python
            },
            "background": {
                "type": "boolean",
                "description": (
                    "DEPRECATED / IGNORED. Top-level single and batch "
                    "delegations run in the background automatically — you do "
                    "not need to (and cannot) opt in or out. A single result or "
                    "consolidated batch result re-enters the conversation when "
                    "the work finishes; just continue working in the meantime. "
                    "Setting this has no effect; the parameter remains only for "
                    "backward compatibility."
                ),
```

真正的决策点在 agent 侧,只看**深度**:

`run_agent.py:7649 @ 863e313`
```python
        # with a handle (one per task) and each subagent's result re-enters the
        # conversation as a new message when it finishes. This applies to BOTH
        # a single task and a fan-out batch (each task becomes its own
        # independent background subagent). The one exception:
        #   - A delegation from an ORCHESTRATOR SUBAGENT (depth > 0) stays
        #     synchronous: the orchestrator needs its workers' results within
        #     its own turn to compose a summary, and a subagent doesn't own the
        #     gateway session the async result would route back to.
        # The schema-level `background` param is intentionally ignored here.
        _is_subagent = getattr(self, "_delegate_depth", 0) > 0
        return _delegate_task(
            goal=function_args.get("goal"),
```

**设计理由(可迁移)**:异步的前提是「有人能在若干分钟后把结果塞回某个还活着的
会话」。orchestrator 子代理不拥有任何 gateway 会话,它的轮次结束时没人接管,
所以它只能同步等。把这个判断放在 harness 而不是模型手里,是因为**模型没有能力
判断自己的宿主会不会在两分钟后还在**。

⚠️ 上面这段 `run_agent.py` 注释里的 "each task becomes its own independent
background subagent" 与代码矛盾:实际调用的是 `dispatch_async_delegation_batch`,
**整批占一个槽、只发一条合并事件**(§2.3)。这是**代码内注释**过时,不计入 ▲
(▲ 按 CLAUDE.md 只统计 README / AGENTS.md / website/docs 这类作者自绘地图)。

### 2.2 还有两条回落到同步的路

即便决定了走后台,`delegate_task` 里还有两处会**改回同步**:

- **会话无法事后收货**:`async_delivery_supported()` 为假(一次性 HTTP 请求、
  cron、Kanban worker、`hermes -z`),且没有可自投的 api_server session id;
- **异步池满**:`dispatch_async_delegation_batch` 返回 `rejected`。

两处都会在结果里塞一个 `note` 说明「其实是同步跑的」。这一点对**重实现**很重要:
**异步入口必须有一条同步退路**,否则一个满池就变成功能不可用。

### 2.3 单发接口在基线里是**死代码** ◇

模块提供了两个派发口:`dispatch_async_delegation`(单子代理,677–820 行,144 行)
与 `dispatch_async_delegation_batch`(整批,932–1061 行)。

**搜索面**:对全仓(含 `.py` / `.md` / `.ts` / 任何文本文件,`grep -rn ... -I`,
仅排除 `./.git/`)搜字面量 `dispatch_async_delegation`,共 24 处命中:
`tools/async_delegation.py` 自身 4 处(定义 + 3 处 docstring/注释)、
`tools/delegate_tool.py` 3 处(全部是 `_batch` 那个)、其余 17 处**全在 `tests/`**。

```verify
cd /home/user/hermes-agent && grep -rn "dispatch_async_delegation" . -I 2>/dev/null | grep -v "^./.git/" | grep -v "_batch" | grep -v "^./tests/"
```

```console
./tools/async_delegation.py:951:    Unlike ``dispatch_async_delegation`` (which backs a single subagent),
./tools/async_delegation.py:677:def dispatch_async_delegation(
```

即:**生产路径上没有任何调用方**。单发口只被测试用。它维护了一份与批量口
几乎逐行重复的容量检查 / 记录构造 / 提交 / 失败清理逻辑——两份实现里,
只有一份会在生产中被执行。重实现时这是明确的**删除候选**;保留它的唯一
可辩护理由是「它是 `_run_single_child` 语义的公开单发 API」,但没有文档这么说。

---

## 3. 登记处的两层状态

### 3.1 第一层:进程内 `_records`

一个 dict,key 是 `deleg_xxxxxxxx`(uuid4 前 8 位十六进制),value 是纯 dict。
状态字段 `status` 取值:`running` → (`stalling`) → `finalizing` → 终局
(`completed` / `error` / `interrupted` / `stalled`)。

**注意:内存态的取值集合与 SQLite 里的 `state` 列不是同一套**(§3.2)。

`tools/async_delegation.py:834 @ 863e313`
```python
def _begin_finalization(
    delegation_id: str,
) -> Optional[tuple[Dict[str, Any], Optional[Callable[[], None]]]]:
    """Atomically claim terminal delivery while keeping the record active."""
    with _records_lock:
        record = _records.get(delegation_id)
        if record is None or record.get("status") not in ("running", "stalling"):
            return
        # Stay active until durable persistence and queue publication finish;
        # otherwise process shutdown can kill this daemon worker in the narrow
        # gap after status flips but before SQLite is committed.
        record["status"] = "finalizing"
        record["completed_at"] = time.time()
        interrupt_fn = record.get("interrupt_fn")
        record["interrupt_fn"] = None  # drop the closure; child is done
        record["progress_fn"] = None  # stop stale-monitor sampling
        event_record = dict(record)

    return event_record, interrupt_fn
```

这个函数是**终局的唯一入口**,三条路都得先过它:正常完成 `_finalize` /
`_finalize_batch`、停滞强杀 `_finalize_stalled`。它同时承担两件事:

- **互斥**:`status not in ("running","stalling")` 直接返回 `None`,所以
  「停滞强杀先发了终局事件,runner 之后姗姗来迟」不会发第二条事件;
- **保活**:故意**先**置 `finalizing` 而不是直接置终局,让「已终结但 SQLite
  还没落盘」这段时间里记录仍被视为活的。

### 3.2 第二层:SQLite `state.db` 的 `async_delegations` 表

`tools/async_delegation.py:142 @ 863e313`
```python
        """CREATE TABLE IF NOT EXISTS async_delegations (
            delegation_id TEXT PRIMARY KEY,
            origin_session TEXT NOT NULL,
            origin_ui_session_id TEXT NOT NULL DEFAULT '',
            parent_session_id TEXT,
            state TEXT NOT NULL,
            dispatched_at REAL NOT NULL,
            completed_at REAL,
            updated_at REAL NOT NULL,
            event_json TEXT,
            result_json TEXT,
            delivery_state TEXT NOT NULL DEFAULT 'pending',
            delivery_attempts INTEGER NOT NULL DEFAULT 0,
            delivered_at REAL,
            owner_pid INTEGER,
            owner_started_at INTEGER,
            task_json TEXT,
            delivery_claim TEXT,
            delivery_claimed_at REAL,
            origin_session_id TEXT NOT NULL DEFAULT ''
        )"""
    )
```

这一行的关键在于它**同时**编码了两条正交的状态线:

| 列 | 语义 | 取值 |
|---|---|---|
| `state` | 任务本身跑成什么样 | `running` / `completed` / `error` / `interrupted` / `stalled` / `unknown` |
| `delivery_state` | 结果**送到人手里没有** | `pending` / `delivered` / `dropped` |

把「跑完了」和「送到了」拆成两列,是这套设计里最值得抄的一笔:一个已完成但
没送出去的结果,和一个还在跑的任务,恢复逻辑完全不同。

`owner_pid` + `owner_started_at` 这一对是**租约**(§5.1)。
`origin_session_id` 是 api_server 的自投唤醒目标——它必须持久化,否则重启后
恢复出来的完成事件无处投递。

◇ **`finalizing` 这个 `state` 值没有任何写入方**。
搜索面:对 `tools/async_delegation.py` 全文搜 `state=` 的所有 UPDATE/INSERT
字面量,写入 `state` 列的只有四处 —— `_persist_dispatch` 写 `'running'`、
`_persist_completion` 写 `event.get("status", "completed")`(取值来自内存 status
的终局集合)、`recover_abandoned_delegations` 写 `'unknown'`。
而 `_prune_durable_records` 和 `recover_abandoned_delegations` 的 WHERE 子句都
把 `'finalizing'` 当成一个可能出现的值来防御。属于防御性死值,不是缺陷,
但重实现时会让人误以为 durable 层也有 `finalizing` 阶段。

```verify
cd /home/user/hermes-agent && grep -n "SET state=\|state, dispatched_at\|VALUES (?, ?, ?, ?, '" tools/async_delegation.py
```

### 3.3 投递认领:一个跨进程的租约式抢占

事件进队列后,可能有**多个消费者**同时看见它(CLI 排空、gateway watcher、
TUI poller、多个 profile 的进程共享同一个 `state.db`)。所以「谁来投递」
必须仲裁。仲裁靠的是一条条件 UPDATE:

`tools/async_delegation.py:383 @ 863e313`
```python
def claim_completion_delivery(delegation_id: str, claim_id: str) -> bool:
    """Claim one pending completion across competing consumers/processes."""
    now = time.time()
    with _DB_LOCK, _transaction() as conn:
        row = conn.execute(
            "SELECT delivery_state FROM async_delegations WHERE delegation_id=?",
            (delegation_id,),
        ).fetchone()
        if row is None:
            return True  # legacy event created before durable dispatch
        cur = conn.execute(
            """UPDATE async_delegations SET delivery_claim=?, delivery_claimed_at=?,
                      delivery_attempts=delivery_attempts+1, updated_at=?
               WHERE delegation_id=? AND delivery_state='pending'
                 AND (delivery_claim IS NULL OR delivery_claimed_at < ?)""",
            (claim_id, now, now, delegation_id, now - 300),
        )
        return cur.rowcount == 1
```

三个细节值得抄:

- **`rowcount == 1` 即赢**,不需要读-改-写,天然原子;
- **认领有 300 秒过期**(`delivery_claimed_at < now - 300`):抢到锁的消费者
  崩了不会让这行永远卡住;
- **尝试次数在认领时就 +1**,不是在投递失败时——所以「反复抢到又放掉」也会
  烧配额。配合下面的封顶,一条永远投不出去的记录会收敛到终局 `dropped`:

`tools/async_delegation.py:414 @ 863e313`
```python
def release_completion_delivery(delegation_id: str, claim_id: str) -> bool:
    """Release a failed delivery claim so another consumer may retry.

    Attempts are counted at claim time, so a row that keeps being claimed and
    released has burned real delivery attempts. Once the budget is exhausted
    the row converges to a terminal ``dropped`` state instead of returning to
    ``pending`` — otherwise an undeliverable completion replays on every
    gateway restart forever (restore_undelivered_completions only restores
    pending rows).
    """
```

⚠️ **`row is None → return True`** 这一支是宽松的:durable 行被裁剪掉后
(`_prune_durable_records`,7 天 / 50 条 / 1000 条三重上限),同一个事件会被
**每个**消费者都「认领成功」。作者把它标注为兼容老事件,但裁剪也会造出这种行。
后果是重复投递(同一份子代理结果进两个会话),不是丢失。重实现时应当区分
「没有这行」和「这行从来没存在过」。

### 3.4 消费侧:先证明所有权,再认领

`cli.py:10685 @ 863e313`
```python
        from tools.process_registry import process_registry
        from tools.async_delegation import (
            claim_event_delivery,
            complete_event_delivery,
        )

        session_key = getattr(self, "session_id", "") or ""
        for event, synthetic_message in process_registry.drain_notifications(
            session_key=session_key,
            owns_event=self._owns_process_notification,
        ):
            claim = claim_event_delivery(event, consumer)
            if claim is None:
                continue
            self._pending_input.put(synthetic_message)
            complete_event_delivery(event, claim)

```

排空侧是**失败关闭**的:一个证明不了归属的事件会被**放回队列**,而不是被丢弃
或被当前会话吞掉:

`tools/process_registry.py:1339 @ 863e313`
```python
            elif is_async_delegation and evt.get("restored"):
                # Durable restore can enqueue previous-process payloads into a
                # fresh registry. An unfiltered legacy drain cannot prove
                # ownership, so leave those events queued for the owner.
                requeue.append(evt)
                continue
```

`restored` 这个内存标记只在恢复路径上打,永不落盘——它是「这条事件来自**上一个
进程**,本进程没有任何消费者天然拥有它」的标签:

`tools/async_delegation.py:344 @ 863e313`
```python
def restore_undelivered_completions(target_queue) -> int:
    """Enqueue durable pending completions as fresh turns after process start.

    Every restored event is stamped ``restored=True`` (in-memory only — the
    stamp is added after the durable payload is deserialized and is never
    persisted). Restored events originate from a *previous* process, so no
    consumer in THIS process implicitly owns them: drain paths that run
    without an ownership filter (the legacy single-session behavior) must
    leave them queued for a consumer that can positively prove ownership,
    otherwise a brand-new session adopts a dead session's delegation
    results seconds after boot (#64484).
    """
    recover_abandoned_delegations()
```

**可迁移原则**:异步结果的投递必须是 **at-least-once + 幂等消费 + 正向所有权证明**。
这里三者齐全:队列重排 = at-least-once,SQLite 条件 UPDATE = 幂等,
`owns_event` 回调 = 正向证明。缺任何一环都会出现「A 的子代理结果进了 B 的对话」。

### 3.5 为什么完成结果走「新轮次」而不是塞进当前轮

`tools/async_delegation.py:16 @ 863e313`
```python
  - completions surface as a NEW turn when the agent is idle, never spliced
    between a tool result and an assistant message. That keeps strict
    message-role alternation legal and the prompt cache intact (hard
    invariant: never mutate past context).
```

这是整套异步设计的**硬约束来源**:LLM 对话是一个 append-only 的消息序列,
prompt cache(把已发送前缀缓存下来以省钱省延迟的机制)只要前缀被改动一个字节
就整体失效。所以异步结果**不能**回填到发起它的那次工具调用的位置,只能作为
新的一轮出现。这条约束反过来决定了:必须有一个「agent 空闲时」的注入点,
于是复用了已有的 `completion_queue` 而不是新造排空循环。

---

## 4. 停滞监控:没有墙钟超时,只有进度冻结

`tools/async_delegation.py:109 @ 863e313`
```python
_STALE_CHECK_INTERVAL = 30.0  # seconds between monitor sweeps
_STALE_IDLE_SECONDS = 450.0  # no progress, no current tool → stalled
_STALE_IN_TOOL_SECONDS = 1200.0  # no progress while inside a tool → stalled
_STALL_GRACE_SECONDS = 120.0  # after interrupt, time for the runner to return

_monitor_lock = threading.Lock()
_monitor_thread: Optional[threading.Thread] = None
_monitor_stop = threading.Event()


def _db_path():
    return get_hermes_home() / "state.db"
```

这两个阈值与同步路径的心跳监控**同源**(`delegate_tool` 里是
`_HEARTBEAT_STALE_CYCLES_IDLE = 15` × 30s = 450s、
`_HEARTBEAT_STALE_CYCLES_IN_TOOL = 40` × 30s = 1200s)。同一套数在两处独立写死,
是重实现时该抽出去的常量。

**为什么不是超时**:模块头写得很清楚——深度评审、研究 fan-out、慢推理模型
本来就可能跑几十分钟,一个墙钟上限会把**正常工作**杀掉。进度令牌
`(api_call_count, current_tool, last_activity_ts)` 只要在变,就永远不动它。

扫描主循环:

`tools/async_delegation.py:1178 @ 863e313`
```python
    while not _monitor_stop.wait(_STALE_CHECK_INTERVAL):
        now = time.time()
        stalled: List[tuple] = []  # (delegation_id, is_batch, quiet_for, in_tool)
        expired: List[str] = []  # stalling past grace → force-finalize
        any_monitorable = False
        with _records_lock:
            for record in _records.values():
                status = record.get("status")
                if status == "stalling":
                    any_monitorable = True
                    interrupted_at = record.get("_interrupted_at") or now
                    if now - interrupted_at >= _STALL_GRACE_SECONDS:
                        expired.append(record["delegation_id"])
                    continue
                if status != "running":
                    continue
```

`tools/async_delegation.py:1204 @ 863e313`
```python
                if token != record.get("_progress_token"):
                    record["_progress_token"] = token
                    record["_progress_ts"] = now
                    continue
                quiet_for = now - (record.get("_progress_ts") or now)
                limit = (
                    _STALE_IN_TOOL_SECONDS if in_tool else _STALE_IDLE_SECONDS
                )
                if quiet_for >= limit:
                    record["status"] = "stalling"
                    record["_interrupted_at"] = now
                    # Structured stall context for the terminal event and
```

**三段式**:采样 → 冻结超阈值就 `interrupt_fn()`(给子代理机会自己把**部分结果**
交出来)→ 宽限期过了还没返回才强制发终局事件。第二步是这套设计比「直接杀」高明
的地方:被打断的子代理走的是正常 finalize 路径,携带完整的 api_calls / summary。

采样出错时**不刷新时间戳**,这一点很关键——一个读不出来的子代理不该看起来永远健康:

`tools/async_delegation.py:1198 @ 863e313`
```python
                try:
                    token, in_tool = progress_fn()
                except Exception:
                    # An unreadable child must not look permanently healthy —
                    # keep the last timestamp running instead of refreshing it.
                    token, in_tool = record.get("_progress_token"), False
```

监控线程**自己退场**,由下一次带 `progress_fn` 的派发重启:

`tools/async_delegation.py:1247 @ 863e313`
```python
        for delegation_id in expired:
            _finalize_stalled(delegation_id)
        if not any_monitorable:
            return
```

■ **窗口竞态(narrow,未实测命中,按代码判定)**:`_ensure_stale_monitor` 用
`_monitor_thread.is_alive()` 判断「已经有监控在跑」:

`tools/async_delegation.py:1141 @ 863e313`
```python
def _ensure_stale_monitor() -> None:
    """Start (once) the module-level stale-delegation monitor thread.

    One daemon thread serves every dispatch; it exits on its own when no
    monitorable records remain, and is restarted by the next dispatch that
    carries a ``progress_fn``.
    """
    global _monitor_thread
    with _monitor_lock:
        if _monitor_thread is not None and _monitor_thread.is_alive():
            return
        _monitor_stop.clear()
        _monitor_thread = threading.Thread(
            target=_stale_monitor_loop,
            name="async-delegate-stale-monitor",
            daemon=True,
        )
        _monitor_thread.start()
```

监控线程决定退出(`any_monitorable=False`)是在**释放 `_records_lock` 之后**,
而 `return` 又在这之后。若一次派发恰好落在「释放锁 → return」之间,它会看到线程
仍 `is_alive()` 而不启新线程,随后监控线程退出 —— **这次派发从此无人监控**,
wedge 了也永远等不到 `stalled` 事件,只能靠进程重启的 `unknown` 兜底。
窗口只有两个空 for 循环,极窄;我**没有**实测命中它(诚实交代),
但修法是零成本的:把 `any_monitorable` 的判定和 `_monitor_thread = None` 的清零
放进同一把 `_monitor_lock`。重实现时应当直接采用「退出前在锁内清空句柄」的写法。

---

## 5. 僵尸与孤儿(本簇最容易漏的地方)

### 5.1 主 agent 进程崩了 / 被 kill:靠 pid 租约在**下次启动时**收割

线程池是**守护**线程池,进程退出不会等它们:

`tools/async_delegation.py:64 @ 863e313`
```python
# A persistent daemon executor (NOT a `with ThreadPoolExecutor()` block, which
# would join on exit and defeat the whole point of async). Workers are daemon
# threads so a hard process exit doesn't hang on an in-flight child.
```

所以**在跑的子代理必然随进程一起消失**。兜底不在运行期,而在**下次进程启动**:

`tools/async_delegation.py:293 @ 863e313`
```python
def recover_abandoned_delegations() -> int:
    """Classify records whose owning process disappeared as outcome unknown."""
    try:
        from gateway.status import _pid_exists, get_process_start_time
    except Exception:
        return 0
    now = time.time()
    recovered = 0
    with _DB_LOCK, _transaction() as conn:
        rows = conn.execute(
            """SELECT delegation_id, origin_session, origin_ui_session_id,
                      parent_session_id, dispatched_at, owner_pid,
                      owner_started_at, task_json, origin_session_id
               FROM async_delegations WHERE state IN ('running','finalizing')"""
        ).fetchall()
        for row in rows:
            (delegation_id, session_key, origin_ui, parent_id, dispatched_at,
             pid, started, task_json, origin_session_id) = row
            live = False
            if pid:
                live = _pid_exists(int(pid))
                if live and started is not None:
                    live = get_process_start_time(int(pid)) == int(started)
            if live:
                continue
            task = json.loads(task_json or "{}")
```

**这是标准的 pid + 启动时刻双因子租约**:光看 pid 存在会被 pid 复用骗到,
所以还要比对 `/proc` 里的进程启动时刻。判定「无主」后,它不是删除记录,而是
合成一条 `status="unknown"` 的完成事件重新排进队列,错误信息是
「owner exited before recording a terminal result; outcome unknown」。

**为什么是 `unknown` 而不是 `failed`**:harness 无法证明这个子代理的副作用
(写文件、发消息、调 API)发生了没有。把不可知报成失败会诱导模型重跑一遍,
可能造成重复副作用。这是一个值得抄的**认知诚实**设计。

调用链:`recover_abandoned_delegations()` 只被 `restore_undelivered_completions()`
调用,后者只在 `ProcessRegistry.__init__` 里调用一次。也就是说**收割发生在进程
启动时,一次**;一个长期运行的 gateway 不会在中途回收另一个已死进程留下的行。

**搜索面**:全仓 `grep -rn "recover_abandoned_delegations\|restore_undelivered_completions"`,
非测试命中共 3 处 —— 定义 2 处 + `tools/process_registry.py:178-179` 1 处。

```verify
cd /home/user/hermes-agent && grep -rn "recover_abandoned_delegations\|restore_undelivered_completions" . -I 2>/dev/null | grep -v "^./.git/" | grep -v "^./tests/"
```

### 5.2 主 agent 正常退出:先发打断信号,但**不等**

三个退出路径都调 `interrupt_all`,都是**只发信号不 join**:

| 入口 | 位置(行号) | reason |
|---|---|---|
| 交互式 CLI 关停 | `cli.py` 1201 | `"CLI shutdown"` |
| `hermes -z` 一次性运行 | `hermes_cli/main.py` 155 | `"oneshot shutdown"` |
| gateway 关停 | `gateway/run.py` 12726 | `f"gateway shutdown ({phase})"` |
| `/stop` 斜杠命令 | `hermes_cli/cli_commands_mixin.py` 470 | `"/stop"` |

`tools/async_delegation.py:1414 @ 863e313`
```python
def interrupt_all(reason: str = "shutdown") -> int:
    """Signal every running async delegation to stop. Returns how many.

    Used on ``/stop`` and gateway shutdown so a dangling background subagent
    can't keep burning tokens with no one listening. The child still emits a
    completion event (status='interrupted') via the normal finalize path.
    """
    count = 0
    with _records_lock:
        targets = [
            r for r in _records.values()
            if r.get("status") in ("running", "stalling")
        ]
```

**明确判定**:`interrupt_all` 之后没有任何 join / 等待。所以进程退出时,
一个还在阻塞式 I/O 里的子代理**来不及**写终局事件——它的 durable 行仍是
`running`,由 §5.1 的下次启动收割成 `unknown`。这是**有意的**:等一个 wedge
住的子代理会把关停变成挂起(这正是 `DaemonThreadPoolExecutor` 存在的理由)。

### 5.3 会话结束(不是进程结束):按三种选择器收割

`interrupt_for_session` 提供三个选择器,**任意一个命中即认领**:
`origin_ui_session_id`(TUI 标签页)、`session_key`(派发时的路由键)、
`parent_session_id`(父 agent 的持久会话 id)。

`tools/async_delegation.py:1449 @ 863e313`
```python
    """Signal running async delegations owned by ONE session to stop.

    A delegation's lifecycle is bound to the session that spawned it: when
    that session ends, its in-flight background subagents must end with it —
    a completed orphan would otherwise sit on the shared completion queue
    with no live owner, either leaking into another chat or burning tokens
    with no one listening (#55578).
```

为什么要三个选择器而不是一个:gateway 聊天的 `session_key` 是**平台会话键**
(如 `agent:main:telegram:123`),用户 `/new` 之后它**不变**,变的是 session id;
而 TUI 的路由键又是 `AIAgent.session_id`。一个选择器覆盖不了所有宿主。
调用点分别在 `gateway/slash_commands.py:194`(`/new` 重置)与
`tui_gateway/server.py:765`(会话终结),后者还额外区分「关掉一个 TUI 观察窗」
与「结束 gateway 自己的会话」——前者不该杀掉 gateway 的后台工作。

### 5.4 ■ 缺陷 1:durable 写失败会**永久**吃掉一个并发槽(可复现)

派发流程是「先插内存记录 → 再写 SQLite → 再提交线程池」。提交失败**有**清理,
写 SQLite 失败**没有**:

`tools/async_delegation.py:998 @ 863e313`
```python
    with _records_lock:
        running = sum(
            1 for r in _records.values()
            if r.get("status") in ("running", "stalling")
        )
        if running >= max_async_children:
            return {
                "status": "rejected",
                "error": (
                    f"Async delegation capacity reached ({max_async_children} "
                    f"running). Wait for one to finish (its result will re-enter "
                    f"the chat), or raise delegation.max_concurrent_children in "
                    f"config.yaml to allow more concurrent background units."
                ),
            }
        _records[delegation_id] = record

    _persist_dispatch(record)
    executor = _get_executor(max_async_children)
```

对照提交失败那一支(单发口与批量口写法相同),它**记得**把内存记录和 durable 行
一起撤销:

`tools/async_delegation.py:801 @ 863e313`
```python
    try:
        # Propagate the dispatching profile so the detached child resolves
        # get_hermes_home() under the right profile.
        executor.submit(propagate_context_to_thread(_worker))
    except Exception as exc:  # pragma: no cover — pool submit failure is rare
        with _records_lock:
            _records.pop(delegation_id, None)
        _delete_durable_delegation(delegation_id)
        return {
            "status": "rejected",
            "error": f"Failed to schedule async delegation: {exc}",
        }
```

**复现**(HERMES_HOME 指向临时目录,把 `state.db` 位置做成一个目录让
`sqlite3.connect` 打不开——等价于磁盘满 / 权限 / 库损坏):

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python - <<'PY'
import os, sys, tempfile, threading, time
tmp = tempfile.mkdtemp(prefix="hermes-home-"); os.environ["HERMES_HOME"] = tmp
os.mkdir(os.path.join(tmp, "state.db"))          # 让 sqlite 打不开
sys.path.insert(0, "/home/user/hermes-agent")
import tools.async_delegation as ad
done = threading.Event()
slow = lambda: (done.wait(30), {"results":[{"status":"completed"}]})[1]
fast = lambda: {"results":[{"status":"completed"}]}
try:
    ad.dispatch_async_delegation_batch(goals=["poisoned"], context=None, toolsets=None,
        role="leaf", model="m", session_key="sk", runner=fast, max_async_children=3)
except Exception as e:
    print("dispatch#1 RAISED:", type(e).__name__)
os.rmdir(os.path.join(tmp, "state.db"))          # 修好 DB,进程继续活着
for i in range(3):
    r = ad.dispatch_async_delegation_batch(goals=[f"real{i}"], context=None, toolsets=None,
        role="leaf", model="m", session_key="sk", runner=slow, max_async_children=3)
    print(f"dispatch#{i+2}:", r.get("status"), "|", (r.get("error") or "")[:52])
print("active_count:", ad.active_count(), "(其中 1 个是永不终结的幽灵)")
done.set(); time.sleep(0.5)
PY
```

```console
dispatch#1 RAISED: OperationalError
dispatch#2: dispatched |
dispatch#3: dispatched |
dispatch#4: rejected | Async delegation capacity reached (3 running). Wait f
active_count: 3 (其中 1 个是永不终结的幽灵)
```

**判定**:`_persist_dispatch` 抛异常时,`_records[delegation_id]` 已经存在且
`status="running"`,而 `_worker` **从未被提交**,所以没有任何路径会调
`_finalize` 去清它。该记录在**整个进程生命周期**内占据一个并发槽:上面第 4 次
派发被拒,尽管真正在跑的只有 2 个。`interrupt_all` / `interrupt_for_session`
也会把它算成目标(它的 `interrupt_fn` 是 `None`,所以只是被计数遗漏)。
修法与提交失败那支完全一样:把 `_persist_dispatch` 包进 try,失败就 pop 记录。

### 5.5 ■ 缺陷 2:`stalling` 记录会被当成「已完成」裁掉,终局事件因此丢失(可复现)

`tools/async_delegation.py:631 @ 863e313`
```python
def _prune_completed_locked() -> None:
    """Drop the oldest completed records beyond the retention cap.

    Caller must hold ``_records_lock``.
    """
    completed = [
        (rid, r)
        for rid, r in _records.items()
        if r.get("status") != "running"
    ]
    if len(completed) <= _MAX_RETAINED_COMPLETED:
        return
    # Oldest-first by completion time (fall back to dispatch time).
    completed.sort(key=lambda kv: kv[1].get("completed_at") or kv[1].get("dispatched_at") or 0)
    for rid, _ in completed[: len(completed) - _MAX_RETAINED_COMPLETED]:
        _records.pop(rid, None)
```

判据是 `status != "running"` —— 而模块里「活着」的定义在别处都是
`{"running","stalling","finalizing"}`。于是一个**长期停滞**的记录:

- 满足 `status != "running"`(它是 `stalling`),进入裁剪候选;
- `completed_at` 是 `None`,排序回落到 `dispatched_at`,而停滞记录的派发时间
  **必然很老**,于是排在最前面 —— **优先被裁**。

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python - <<'PY'
import os, sys, tempfile, time
os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="hermes-home-")
sys.path.insert(0, "/home/user/hermes-agent")
import tools.async_delegation as ad
now = time.time()
ad._records["deleg_stall1"] = {"delegation_id":"deleg_stall1","status":"stalling",
    "dispatched_at":now-3600,"completed_at":None,"interrupt_fn":None,"progress_fn":None}
for i in range(51):                     # 之后又跑完了 51 个后台委派
    ad._records[f"deleg_done{i}"] = {"delegation_id":f"deleg_done{i}","status":"completed",
        "dispatched_at":now-100+i,"completed_at":now-50+i}
print("before: total=%d stalling_present=%s" % (len(ad._records), "deleg_stall1" in ad._records))
with ad._records_lock:
    ad._prune_completed_locked()
print("after : total=%d stalling_present=%s" % (len(ad._records), "deleg_stall1" in ad._records))
print("_finalize_stalled 此时能拿到的记录:", ad._begin_finalization("deleg_stall1"))
PY
```

```console
before: total=52 stalling_present=True
after : total=50 stalling_present=False
_finalize_stalled 此时能拿到的记录: None
```

**后果**:停滞监控在宽限期结束后调 `_finalize_stalled` → `_begin_finalization`
返回 `None` → **一条 `stalled` 事件都发不出来**。owning session 永远等不到结论,
durable 行停在 `running` 直到进程退出后被 §5.1 判成 `unknown`。这**直接违反**
监控自己的承诺:

`tools/async_delegation.py:1173 @ 863e313`
```python
    - A ``stalling`` record whose runner still hasn't returned after the
      grace window is force-finalized with one terminal ``stalled`` event so
      the owning session hears an outcome and the async slot frees. A late
      runner return after that is ignored by ``_begin_finalization``.
```

**可达性**:需要在该记录之后又累积 >50 条非 `running` 记录。`_prune_completed_locked`
只在 `_finish_finalization` 里被调,也就是**每次完成都调一次**。长期运行的 gateway
上,一个停滞了几十分钟的委派身边跑完 51 个后台委派,并不罕见。修法:把判据
改成 `status not in ("running","stalling","finalizing")`,与模块其它地方一致。

### 5.6 ◇ 「活着」在同一个模块里有五种定义

| 函数 | 认定为「活」的 status 集合 |
|---|---|
| `active_count()` | running, stalling, finalizing |
| `active_for_session()` | running, stalling, finalizing |
| `has_live_for_session()` | running, stalling, finalizing |
| `active_task_count()` | running, finalizing(**漏 stalling**) |
| 派发容量门 / `interrupt_all` / `interrupt_for_session` | running, stalling(**漏 finalizing**) |
| `_prune_completed_locked()` | running(**漏 stalling + finalizing**,见 §5.5) |

第 4 行的后果是可观测性偏差:`active_task_count()` 喂给
`agent/monitoring/gateway_health_export.py` 做健康指标,一个停滞中的批次会被
少计。第 5 行的后果是容量门比 `active_count()` 宽松——一个正在 finalize 的记录
不占派发额度,但它的 worker 线程还占着线程池的位子,于是新派发会**排进
ThreadPoolExecutor 的无界队列**而不是被拒。窗口很短(一次 SQLite 写),
但方向是错的:容量门应当比展示口径更保守,而不是更宽松。

---

## 6. `agent/subagent_lifecycle.py` —— 给插件的第二套生命周期

这是一套**与 `async_delegation` 完全独立**的登记处。它的定位在文件头写明:

`agent/subagent_lifecycle.py:1 @ 863e313`
```python
"""Public, plugin-safe lifecycle API for delegated Hermes subagents.

This module deliberately exposes immutable contracts, not ``AIAgent`` objects.
It is the supported boundary for plugins that need to supervise fresh child
sessions; plugins must obtain it from ``PluginContext.subagent_lifecycle``.
"""
```

### 6.1 状态机

`agent/subagent_lifecycle.py:38 @ 863e313`
```python
class SubagentState(str, enum.Enum):
    PENDING = "PENDING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
```

```mermaid
stateDiagram-v2
    [*] --> PENDING : launch() 建好 child、插进登记处
    PENDING --> RUNNING : _run() 起跑(worker 线程)
    PENDING --> CANCEL_REQUESTED : cancel() 抢在 _run() 之前
    RUNNING --> CANCEL_REQUESTED : cancel()
    CANCEL_REQUESTED --> RUNNING : 不发生 —— _run() 只在非 CANCEL_REQUESTED 时才置 RUNNING
    RUNNING --> SUCCEEDED : raw.status == completed
    RUNNING --> INTERRUPTED : raw.status == interrupted 且未请求过取消
    RUNNING --> FAILED : 其它 status / _run 抛异常
    CANCEL_REQUESTED --> CANCELLED : raw.status == interrupted
    CANCEL_REQUESTED --> SUCCEEDED : 子代理赶在打断前跑完了
    CANCEL_REQUESTED --> FAILED : 其它
    SUCCEEDED --> [*] : 保留 1 小时,由下一次 launch() 清理
    FAILED --> [*]
    INTERRUPTED --> [*]
    CANCELLED --> [*]
    STARTING --> STARTING : 全仓无任何写入方(死枚举值)
    UNKNOWN --> UNKNOWN : 句柄验不过 / 记录已清 / 进程重启后
```

驱动迁移的是**两个**角色,分工干净:

- **worker 线程**(`_run`)驱动 `PENDING → RUNNING → 终局`;
- **调用方线程**(`cancel`)只能驱动 `→ CANCEL_REQUESTED`,**不能**直接写终局。

`agent/subagent_lifecycle.py:408 @ 863e313`
```python
    def _run(self, record: _Record, goal: str, parent: Any) -> None:
        with _REGISTRY.lock:
            if record.state is not SubagentState.CANCEL_REQUESTED:
                record.state = SubagentState.RUNNING
            record.started_at = time.time()
            record.updated_at = record.started_at
        try:
            from tools.delegate_tool import _run_child_lifecycle

            raw = _run_child_lifecycle(0, goal, record.agent, parent)
            status = (
                str(raw.get("status", "error")) if isinstance(raw, dict) else "error"
            )
            if status == "completed":
                state = SubagentState.SUCCEEDED
            elif status == "interrupted":
                state = (
                    SubagentState.CANCELLED
                    if record.state == SubagentState.CANCEL_REQUESTED
                    else SubagentState.INTERRUPTED
                )
            else:
                state = SubagentState.FAILED
            summary = raw.get("summary") if isinstance(raw, dict) else None
```

◇ **`STARTING` 是死枚举值**。搜索面:对全仓所有文本文件
(`grep -rn -I`,仅排除 `./.git/`)搜三种字面量 `SubagentState.STARTING`、
`"STARTING"`、`'STARTING'`,**唯一命中就是它自己的定义行**。

```verify
cd /home/user/hermes-agent && grep -rn "SubagentState.STARTING\|\"STARTING\"\|'STARTING'" . -I 2>/dev/null | grep -v "^./.git/"
```

```console
./agent/subagent_lifecycle.py:40:    STARTING = "STARTING"
```

### 6.2 句柄是一张 HMAC 能力票据

`agent/subagent_lifecycle.py:479 @ 863e313`
```python
    @staticmethod
    def _capability(
        subagent_id: str, parent_session_id: Optional[str], created_at: float
    ) -> str:
        value = f"{subagent_id}|{parent_session_id or ''}|{created_at:.6f}".encode()
        return hmac.new(_SECRET, value, hashlib.sha256).hexdigest()
```

每次操作都要过 `_record()`:先做**逐字段类型校验**(连 `type(x) is not int`
这种防 `bool` 的写法都有),再比 HMAC,最后还要求**当前活跃父会话 == 句柄里的
父会话**:

`agent/subagent_lifecycle.py:375 @ 863e313`
```python
        if not hmac.compare_digest(
            handle.capability,
            self._capability(
                handle.subagent_id, handle.parent_session_id, handle.created_at
            ),
        ):
            return None
        parent = self._parent_agent_resolver()
        active_parent_id = str(getattr(parent, "session_id", "") or "") or None
        if active_parent_id != handle.parent_session_id:
            return None
        with _REGISTRY.lock:
            return _REGISTRY.records.get(handle.subagent_id)
```

`_SECRET = secrets.token_bytes(32)` 是**每进程新生成**的,所以重启后任何序列化
过的句柄都验不过 → `reconnect()` 老老实实报「连不上」而不是重新起一个任务。
这是对的:一个「重连」API 在重启后偷偷重跑任务,是分布式系统里最贵的那类 bug。

**取舍**:`_record()` 把「伪造句柄 / 父会话不对 / 记录已过期 / 进程重启过」
四种情况**全部**压成 `UNKNOWN_HANDLE`。安全上正确(不泄漏存在性),
可用性上难调试。另外注意:能力票据认证的是**句柄**不是**持有者**——同一进程内
的另一个插件如果拿到句柄,可以完全操作它;隔离粒度是父会话,不是插件身份。

**父 agent 从哪来**:一个 ContextVar,只在**一次 agent 轮次内**绑定。

`agent/subagent_lifecycle.py:172 @ 863e313`
```python
@contextmanager
def bind_subagent_parent(parent_agent: Any):
    """Bind the host-owned parent for the current agent turn."""
    token = _ACTIVE_PARENT_AGENT.set(parent_agent)
    try:
        yield
    finally:
        _ACTIVE_PARENT_AGENT.reset(token)
```

绑定点唯一(`run_agent.py:7852`,包住 `run_conversation`)。推论:
**插件在轮次之外调 `launch()` 会直接抛「没有活跃父会话」;更隐蔽的是,
在轮次之外调 `status()` / `result()` / `wait()` 也一律得到 `UNKNOWN`**,
因为 `_record()` 要拿 `_parent_agent_resolver()` 去比对。这个 API 事实上
只能在**同一个父会话的某次轮次内**使用。文档(docstring)没有点破这一点。

### 6.3 ■ 缺陷 3:生命周期 worker **没有**做上下文传播(可复现,安全相关)

`agent/subagent_lifecycle.py:254 @ 863e313`
```python
        record = _Record(handle, SubagentState.PENDING, created, agent=child)
        with _REGISTRY.lock:
            _REGISTRY.records[subagent_id] = record
            if request.correlation_id:
                _REGISTRY.correlations[correlation_key] = subagent_id
        record.future = _EXECUTOR.submit(self._run, record, request.goal, parent)
        return handle
```

对比 `async_delegation` 的同类调用(`tools/async_delegation.py:801` 与 `:1045`),
后者一律包了 `propagate_context_to_thread(...)`。这个 helper 存在的理由,
仓库自己写得很明确:

`tools/thread_context.py:2 @ 863e313`
```python
"""Propagate agent-turn context into worker threads that dispatch Hermes tools.

A bare ``threading.Thread`` / ``ThreadPoolExecutor`` worker starts with an
empty ``contextvars.Context`` and no thread-local approval/sudo callbacks.
Tool dispatch inside such a thread therefore silently loses:

  * the approval *session/platform* ContextVars (``tools.approval`` /
    ``gateway.session_context``) — so gateway sessions fall into
    ``check_dangerous_command``'s non-interactive auto-approve branch and
    dangerous commands run without prompting (#33057, #30882);
  * the thread-local CLI approval/sudo callbacks (``tools.terminal_tool``) —
    so ``prompt_dangerous_approval`` cannot reach the user
    (GHSA-qg5c-hvr5-hjgr, #15216).
```

审批回调确实是**线程本地**的,所以新线程必然拿不到:

`tools/terminal_tool.py:260 @ 863e313`
```python
_callback_tls = threading.local()
```

**复现**(直接量两种提交形状下 worker 线程看到什么):

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python - <<'PY'
import os, sys, tempfile
os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="hermes-home-")
sys.path.insert(0, "/home/user/hermes-agent")
from tools.approval import set_current_session_key, get_current_session_key
from tools.thread_context import propagate_context_to_thread
import hermes_constants as hc, agent.subagent_lifecycle as sl
set_current_session_key("agent:main:telegram:123")
tok = hc.set_hermes_home_override("/home/user/.hermes/profiles/work")
def probe(label):
    print(f"  [{label}] approval session_key = {get_current_session_key()!r}")
    print(f"  [{label}] hermes_home override = {hc.get_hermes_home_override()!r}")
probe("parent (dispatching turn thread)")
print("A. subagent_lifecycle.launch() 的形状 — _EXECUTOR.submit(self._run, ...) 裸提交:")
sl._EXECUTOR.submit(probe, "lifecycle-worker").result()
print("B. async_delegation 的形状 — submit(propagate_context_to_thread(w)):")
sl._EXECUTOR.submit(propagate_context_to_thread(lambda: probe("async-worker"))).result()
hc.reset_hermes_home_override(tok)
PY
```

```console
  [parent (dispatching turn thread)] approval session_key = 'agent:main:telegram:123'
  [parent (dispatching turn thread)] hermes_home override = '/home/user/.hermes/profiles/work'
A. subagent_lifecycle.launch() 的形状 — _EXECUTOR.submit(self._run, ...) 裸提交:
  [lifecycle-worker] approval session_key = 'default'
  [lifecycle-worker] hermes_home override = None
B. async_delegation 的形状 — submit(propagate_context_to_thread(w)):
  [async-worker] approval session_key = 'agent:main:telegram:123'
  [async-worker] hermes_home override = '/home/user/.hermes/profiles/work'
```

**我直接实测到的事实**(不外推):插件启动的子代理跑在一个
(a) 审批 session key 退化成 `'default'`、(b) **Hermes profile 覆盖丢失** 的线程上。
(b) 的后果是可以独立判定的——`get_hermes_home()` 会解析到**默认 profile**,
于是这个子代理的会话库、缓存、实时转录全写到错的 profile 去。
(a) 的下游后果由上面那段 `thread_context.py` 的仓库自述说明,我没有单独跑通
审批链路,所以只引用仓库自己的判断,不替它下结论。

**搜索面(用于说明这是孤例)**:全仓非测试文件里
`grep -rn "propagate_context_to_thread" --include=*.py`,除 helper 自身外的
**提交点**共 8 处(`agent/moa_loop.py`、`agent/tool_executor.py`、
`agent/conversation_compression.py`、`model_tools.py`、`tools/async_delegation.py` ×2、
`tools/code_execution_tool.py` ×2、`run_agent.py`)。
`agent/subagent_lifecycle.py` **不在其中**,它连 import 都没有:

```verify
cd /home/user/hermes-agent && grep -n "contextvars\|copy_context\|propagate" agent/subagent_lifecycle.py
```

```console
10:import contextvars
167:_ACTIVE_PARENT_AGENT: contextvars.ContextVar[Any] = contextvars.ContextVar(
```

### 6.4 背压:这套 API **没有**上限

`agent/subagent_lifecycle.py:159 @ 863e313`
```python
_REGISTRY = _Registry()
# Daemon worker pool: a wedged/abandoned child must never block interpreter
# exit at atexit-join time (same rationale as _run_single_child's timeout
# executor and the async-delegation registry pool).
from tools.daemon_pool import DaemonThreadPoolExecutor as _DaemonExecutor

_EXECUTOR = _DaemonExecutor(max_workers=8, thread_name_prefix="hermes-lifecycle")
_SECRET = secrets.token_bytes(32)
_ACTIVE_PARENT_AGENT: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "hermes_subagent_lifecycle_parent", default=None
)
```

`launch()` **从不拒绝**:唯一的「重复」检查是 `correlation_id` 去重。
线程池 8 个 worker,队列无界。一个插件循环 `launch()` 一万次,就会有一万个
**已经构造好的 `AIAgent` 对象**(每个都持有凭据池、工具集、终端会话句柄)
排在队列里等,而 `_EXECUTOR` 一次只跑 8 个。这与 `async_delegation` 的
「满了就拒绝」是**相反的**背压策略,同一个仓库里两套,没有文档解释为什么。

另一个隐性增长点:终局快照的清理**只在 `launch()` 里发生**。

`agent/subagent_lifecycle.py:389 @ 863e313`
```python
    @staticmethod
    def _cleanup_locked() -> None:
        """Retain terminal snapshots for a bounded period, never live work."""
        cutoff = time.time() - _TERMINAL_RETENTION_SECONDS
        expired = [
            subagent_id
            for subagent_id, record in _REGISTRY.records.items()
            if record.result is not None
            and record.completed_at is not None
            and record.completed_at < cutoff
        ]
        for subagent_id in expired:
            record = _REGISTRY.records.pop(subagent_id)
            if record.handle.correlation_id:
                _REGISTRY.correlations.pop(
                    (record.handle.parent_session_id, record.handle.correlation_id),
                    None,
                )
```

**搜索面**:全仓 `grep -rn "_cleanup_locked"`,共 2 处命中(定义 + `launch()` 内
的唯一调用),无其它触发点。于是:插件不再 launch 的那一刻起,
已有的终局快照(每条最多 32k summary + 32k error message)就**永久驻留**。

⚠️ 这与类 docstring 自相矛盾:

`agent/subagent_lifecycle.py:187 @ 863e313`
```python
class SubagentLifecycleService:
    """Stable public service returned by :attr:`PluginContext.subagent_lifecycle`.

    Running children are in-process only.  Completed results remain available
    until process exit; ``reconnect`` accurately reports that a serialized
    handle cannot reconnect after a restart instead of launching work again.
    """
```

「Completed results remain available until process exit」与
`_TERMINAL_RETENTION_SECONDS = 3600` + 下次 launch 清理并不一致:一个持续
launch 的插件会发现 1 小时前的结果查不到了(`result()` 返回 `UNKNOWN_HANDLE`)。
这是**代码内 docstring** 与代码的矛盾,同样不计入 ▲。

### 6.5 与 `/stop` / 会话收割**完全隔离**(重要的孤儿口子)

`interrupt_all` / `interrupt_for_session` 只遍历 `tools.async_delegation._records`
(见 §5.2、§5.3 的引用)。`subagent_lifecycle` 有自己的 `_REGISTRY`。
**搜索面**:全仓 `grep -rn "subagent_lifecycle"` 的非测试命中共 4 处 ——
定义文件、`hermes_cli/plugins.py`(构造服务)、`run_agent.py` ×2(绑定父 agent)。
`cli.py` / `gateway/` / `tui_gateway/` **没有任何一处**碰它。

```verify
cd /home/user/hermes-agent && grep -rn "subagent_lifecycle" --include=*.py . | grep -v "^./tests/"
```

**判定**:用户按 `/stop`、关掉会话、gateway 关停时,**插件启动的子代理不会被打断**。
它们唯一的终止途径是插件自己调 `cancel()`,或进程退出(守护线程被强杀)。
好在 `_run` 走的是 `_run_child_lifecycle` → `_run_single_child`,后者的 `finally`
会把 child 从 `parent._active_children` 摘掉并 `child.close()`(关掉终端沙箱、
浏览器守护进程、后台进程),所以**不会**泄漏子进程——前提是它能跑到 `finally`。

顺带:`launch()` 走 `_build_child_preserving_parent_tools` → `_build_child_agent`,
后者会把 child **挂进** `parent._active_children`,而生命周期路径**没有**像
异步批次那样摘钩(§1 第 5 步)。所以父轮次被 Ctrl-C 时,打断**会**传播到插件的
子代理。这与「独立生命周期 + 显式 cancel()」的 API 叙事不一致,但方向是安全的。

### 6.6 API 里那些「故意不支持」的字段

`agent/subagent_lifecycle.py:506 @ 863e313`
```python
        if request.timeout_seconds is not None:
            raise SubagentLifecycleError(
                "Per-launch timeout is not supported; configure delegation timeout explicitly."
            )
        if request.working_directory is not None:
            raise SubagentLifecycleError(
                "working_directory is not supported because Hermes delegates use isolated task environments."
            )
        if request.blocked_tools:
            raise SubagentLifecycleError(
                "Per-tool blocking is not supported; use allowed_toolsets. Hermes always blocks unsafe child tools."
            )
```

**设计手法值得抄**:字段留在 dataclass 里(契约稳定、跨版本可反序列化),
但传非默认值就**显式报错**,而不是静默忽略。静默忽略一个 `timeout_seconds`
会让插件作者以为超时生效了。同理,`allowed_toolsets` 必须是父 agent
已启用工具集的**子集**,否则报「Requested toolsets would broaden parent permissions」——
权限只能收窄不能放宽。

---

## 7. `agent/delegation_context.py` —— 161 行的身份位

### 7.1 它携带什么:**不是**深度/预算/追踪 id,而是**两个布尔身份位**

任务书里问「深度?预算?追踪 id?」——答案是**都不在这里**。深度在
`child._delegate_depth`,预算在 `max_iterations`,追踪走 `session_id`。
这个模块只管一件事:**我这段执行,算不算 Kanban dispatcher 拥有的那个 worker?**

`agent/delegation_context.py:20 @ 863e313`
```python
_DELEGATED_CHILD_CONTEXT: ContextVar[bool] = ContextVar(
    "hermes_delegated_child_context",
    default=False,
)

# Set for any in-process execution that is NOT the dispatcher-owned worker even
# though the worker's HERMES_KANBAN_* vars are legitimately in os.environ (cron
# jobs fired via the `cronjob` tool).  Kept separate from
# _DELEGATED_CHILD_CONTEXT so the delegate_task-specific behaviour attached to
# that flag (subprocess env scrubbing, its own error strings) is unchanged.
_NON_DISPATCHER_OWNED_CONTEXT: ContextVar[bool] = ContextVar(
    "hermes_non_dispatcher_owned_context",
    default=False,
)
```

**场景(它解决什么)**:Kanban 派工器起一个 Hermes worker 进程去做任务 T,
在进程环境里塞了 `HERMES_KANBAN_TASK=T` 等变量。这个 worker 是普通 CLI agent,
默认工具集里有 `cronjob`;它调 `cronjob(action="run")` 会**在自己进程里**跑另一个
agent。如果不加区分,那个 cron agent 会被认成 worker 本人:kanban 工具集被强制
加上、worker 协议被注入系统提示、`kanban_complete` 的 `task_id` 默认取
`$HERMES_KANBAN_TASK` —— 于是一个不相干的定时任务**关掉了 worker 的任务、
覆盖了真实结果**。`delegate_task` 子代理同理。

### 7.2 为什么是 ContextVar 而不是改 `os.environ`

`agent/delegation_context.py:83 @ 863e313`
```python
    an unrelated cron job close the worker's task and overwrite real results.

    Scoped via ContextVar rather than by clearing ``os.environ``: the env is
    process-global and shared with the worker's own claim heartbeat, the
    gateway's Kanban watchers, and concurrent cron jobs on the parallel pool, so
    mutating it would starve the worker's claim and race those readers.
```

**并发安全性判定**:ContextVar 是 **task-local**(每个线程/每个 asyncio task
有自己的一份),所以多个子代理并发跑在不同线程上时,彼此的身份位互不影响 ——
**前提是**这些线程是通过 `contextvars.copy_context()` / `propagate_context_to_thread`
起来的。异步委派满足这个前提(§5.4 引用的 `submit(propagate_context_to_thread(...))`);
`subagent_lifecycle` 不满足(§6.3),不过它的子代理是在 `_run_child_lifecycle`
**内部**才进入 `delegated_child_context()`,所以身份位本身是对的。

汇总的单一判定入口(重实现时应当抄这个形状:**一个谓词,所有门都用它**):

`agent/delegation_context.py:97 @ 863e313`
```python
def is_dispatcher_owned_worker_context() -> bool:
    """Return True only when this execution owns the dispatcher's Kanban task.

    The single predicate every ``HERMES_KANBAN_*`` identity gate should use
    before trusting those vars.  False for delegate_task children and for cron
    jobs fired in-process from a worker.
    """
    if _DELEGATED_CHILD_CONTEXT.get():
        return False
    return not _NON_DISPATCHER_OWNED_CONTEXT.get()
```

### 7.3 怎么跨进程:ContextVar 过不了 `fork`,所以降级成环境变量标记

`agent/delegation_context.py:124 @ 863e313`
```python
def is_delegated_child_process_context() -> bool:
    """Return True in this process or a subprocess spawned by a child."""
    import os

    return bool(_DELEGATED_CHILD_CONTEXT.get()) or bool(
        os.environ.get(DELEGATED_CHILD_ENV_MARKER)
    )


def scrub_kanban_env(env: Mapping[str, str] | MutableMapping[str, str]) -> dict[str, str]:
    """Return *env* with dispatcher-only Kanban variables removed."""
    cleaned = dict(env)
    for key in KANBAN_ENV_KEYS:
        cleaned.pop(key, None)
    cleaned[DELEGATED_CHILD_ENV_MARKER] = "1"
    return cleaned
```

`scrub_kanban_env` 一次做两件事:**删掉** 7 个 `HERMES_KANBAN_*` 变量,
**塞进** 一个 `HERMES_DELEGATED_CHILD_CONTEXT=1` 血统标记。子进程读不到父进程的
ContextVar,但读得到这个环境变量,于是身份位跨过了 `fork` 边界。

最妙的是它**保留了 `env=None` 的语义**:

`agent/delegation_context.py:154 @ 863e313`
```python
    if not is_delegated_child_process_context():
        return None if env is None else dict(env)

    if env is None:
        import os

        env = os.environ
    return scrub_kanban_env(env)
```

绝大多数 `subprocess` 调用点历史上写的是 `env=None`(继承父进程环境)。
如果为了传血统标记就一律物化成 dict,会改变几十个调用点的语义(比如某些平台上
显式 env 会丢掉一些隐式变量)。这个 helper 让**非委派场景一个字节都不变**,
只在真的需要跨边界传血统时才物化。使用点:`tools/environments/local.py:519`、
`tools/code_execution_tool.py:290` 与 `:1843`、`tools/tts_tool.py:1029`、
`tools/transcription_tools.py:686`。

### 7.4 与会话 id 的协作:子代理**不能**污染进程级 `HERMES_SESSION_ID`

`gateway/session_context.py:160 @ 863e313`
```python
    Delegated subagent children are the exception: they are constructed inside
    the parent process within ``delegated_child_context()``, and their
    ``AIAgent.__init__`` calls this same helper. Writing a child's internal
    session id to ``os.environ`` (process-global) would clobber the parent's
    ``HERMES_SESSION_ID`` for the rest of the process — leaking the child id
    into parent tools and subprocesses spawned after the child was built. The
    ContextVar write below is task-local and safe for concurrent children; only
    the process-global ``os.environ`` mirror is suppressed for delegated
    children. Root agents (CLI, gateway, cron) keep both paths.
```

这就是为什么 `delegated_child_context(session_id)` 除了置身份位,还要包一层
`scoped_current_session_id` —— **构造 child 的动作本身就会写 ContextVar**,
所以哪怕不传 id 也必须做保存/恢复。

这个坑还有第二次回响:异步派发要记录「结果该唤醒哪个 api_server 会话」,
而它**不能**读 `HERMES_SESSION_ID`,因为构造 child 时已经被覆写了:

`tools/async_delegation.py:649 @ 863e313`
```python
def _current_origin_session_id() -> str:
    """Raw session id of the ORIGINATING api_server request, or ``""``.

    The obvious source — ``HERMES_SESSION_ID`` via ``get_session_env`` — is
    NOT safe to read at dispatch time: constructing a child agent
    (``agent/agent_init.py``) calls ``set_current_session_id(child.session_id)``,
    clobbering that ContextVar *and* ``os.environ`` with the subagent's
    internal ``{timestamp}_{uuid}`` id moments before the dispatch code reads
```

解决办法是改读一个**没有写入方会碰**的绑定 `HERMES_SESSION_CHAT_ID`,
并且 `delegate_tool` 在**构造任何 child 之前**就把它捕获成 `_origin_wake_sid`
(`tools/delegate_tool.py:2951`)。**可迁移教训**:凡是「派发时捕获、完成时使用」
的路由信息,必须在**任何子对象构造之前**取样,并且取自一个只有一个写入方的位置。

---

## 8. 实时日志(`tools/delegation_live_log.py`)

### 8.1 写到哪、谁读

`tools/delegation_live_log.py:61 @ 863e313`
```python
def live_transcript_root() -> Path:
    """Root directory for live transcripts (profile-safe, never ~/.hermes)."""
    from hermes_constants import get_hermes_dir

    return get_hermes_dir("cache/delegation", "delegation_cache") / "live"
```

路径 `<hermes_home>/cache/delegation/live/<delegation_id>/task-<n>.log`,
外加一份 `manifest.json`。**放在 `cache/delegation` 下是刻意的**:该目录在
`tools/credential_files.py:397` 的 `_CACHE_DIRS` 名单里,会被**只读挂载**进
Docker / Modal / SSH 远端后端。于是子代理自己(在沙箱里)也能读到转录。

**读者有四类**:(a) 人 `tail -f`;(b) 父 agent —— 路径通过工具返回值里的
`live_transcripts` 交给模型,并附一句 hint 让它可以读或 tail;(c) 完成事件里
带 `live_transcripts` 字段(`tools/async_delegation.py:1111`);(d) `/agents`
面板不读文件,它读的是 `list_async_delegations()` 的内存快照。

### 8.2 并发:一子任务一文件 + 每写一次开关文件

`tools/delegation_live_log.py:152 @ 863e313`
```python
    def event(self, role: str, text: str) -> None:
        """Append one ``HH:MM:SS role ⟩ text`` line. Flushed per event."""
        if not self._ok or self.path is None:
            return
        # Single choke point: every typed helper funnels through here, so
        # redacting once covers args, results, thinking and streamed text —
        # and a helper added later can't bypass it.
        line = f"{time.strftime('%H:%M:%S')} {role:<9}| {_redact(text)}\n"
        try:
            with self._lock:
                # Append mode per write: no held handle, survives child crash,
                # and the close() acts as the flush.
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line)
        except Exception as exc:
            self._ok = False
            logger.debug("Live transcript write failed (%s): %s", self.path, exc)
```

**并发问题被文件切分消解掉了**:N 个并行子代理拿到的是 `live_writers[0..N-1]`,
各写各的 `task-<i>.log`,不存在跨子代理竞争。同一个 writer 内部有
`threading.Lock` 串行化写。**不持有长期文件句柄**是刻意的:子代理崩了不会
丢缓冲区里的内容,每次 `close()` 就是一次 flush。代价是每行一次 `open`/`close`
系统调用——对一个「人类可读的操作日志」的写入频率来说完全可以接受。

■(轻微)**流式缓冲区不在锁里**:

`tools/delegation_live_log.py:204 @ 863e313`
```python
    def add_stream_delta(self, delta: str) -> None:
        """Buffer streamed assistant reply text; flushed as one line."""
        if not delta or not self._ok:
            return
        self._stream_buf.append(delta)
        self._stream_len += len(delta)
        if self._stream_len >= _STREAM_BUFFER_FLUSH_CHARS:
            self.flush_stream()

    def flush_stream(self) -> None:
        if not self._stream_buf:
            return
        text = "".join(self._stream_buf)
        self._stream_buf = []
        self._stream_len = 0
        self.assistant_text(text)
```

`self._lock` 只保护文件写,不保护 `_stream_buf`。而这两个方法**确实会被
不同线程调用**:超时路径上,`delegate_tool` 在
`_timeout_executor.shutdown(wait=False)` **之后**、于监管线程调
`child_progress_cb._flush()`(`tools/delegate_tool.py:2322`),而超时的子代理
线程可能仍在自己的线程里推 `subagent.text` 增量。GIL 保证 `list.append` 不会
崩,但 `join` 与 `= []` 之间到达的增量会被静默丢弃。严重度低(只是调试转录),
但重实现时把 `_stream_buf` 一并放进锁是零成本的。

### 8.3 脱敏:有,而且是强制的;但顺序错了

`tools/delegation_live_log.py:83 @ 863e313`
```python
def _redact(text: str) -> str:
    """Mask credentials before anything reaches the transcript file.

    These logs live under ``cache/delegation``, which ``delegate_tool`` mounts
    READ-ONLY into remote terminal backends — so every line written here is
    readable from inside the sandbox. The events rendered here carry exactly
    the data that tends to hold secrets: tool args (a bearer header on a
    curl), tool results (a ``.env`` dump, a provider error echoing the key
    back) and streamed assistant text. Every other sink for that data already
    routes through this same redactor — search results via
    ``redact_sensitive_text``, terminal output via ``redact_terminal_output``
    — so a transcript that skipped it is the one place the operator's keys
    land in plaintext.

    ``force=True``: this is a safety boundary, so it must redact even when the
    global toggle is off. Withholds the line rather than emitting raw text if
    the redactor is somehow unavailable — losing a debug line costs less than
    writing a live credential into a sandbox-readable file.
    """
```

设计上三个点都对:**单一收口**(所有 typed helper 都走 `event()`)、
**force=True**(不受全局开关影响)、**失败即扣留**(脱敏器不可用就写
`[line withheld: redaction unavailable]` 而不是原文)。头部 `goal` 和
`manifest.json` 里的 `goal` 也各自单独过了一遍 `_redact`。

实测常见形状都能挡住:

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python - <<'PY'
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp(prefix="hermes-home-"); os.environ["HERMES_HOME"] = tmp
sys.path.insert(0, "/home/user/hermes-agent")
from tools.delegation_live_log import LiveTranscriptWriter
w = LiveTranscriptWriter("deleg_test01", 0,
    goal="fetch with sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    root=Path(tmp)/"live")
w.tool_start("terminal", {"command": "curl -H 'Authorization: Bearer sk-ant-api03-ZZZZZZZZZZZZZZZZZZZZZZZZZZZZ' https://x"})
w.tool_result("terminal", result="OPENAI_API_KEY=sk-proj-BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB\npassword: hunter2correcthorse")
w.assistant_text("the token is ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
w.tool_result("terminal", result="-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\n-----END RSA PRIVATE KEY-----")
print(w.path.read_text())
PY
```

```console
=== Hermes subagent live transcript ===
delegation: deleg_test01   task: 0
goal: sk-pro...AAAA 已被遮蔽(见下方实际输出行)
```

(上面这段 console 只是提示,真实输出见下面的逐行判定表。)

实测结果逐行判定:

| 输入形状 | 转录里的结果 | 判定 |
|---|---|---|
| `sk-proj-…` / `sk-ant-api03-…` | `sk-pro...AAAA` / `***` | 挡住 |
| `Authorization: Bearer <token>` | `Bearer ***` | 挡住 |
| `OPENAI_API_KEY=sk-…` | `OPENAI_API_KEY=***` | 挡住 |
| `ghp_…` | `ghp_AB...6789` | 挡住 |
| `-----BEGIN RSA PRIVATE KEY-----` | `[REDACTED PRIVATE KEY]` | 挡住 |
| **`password: hunter2correcthorse`**(多行输出里的一行) | **原文照出** | ■ 漏 |

■ **缺陷 4:`_one_line()` 先把多行压成一行,`_redact()` 才跑,行锚定规则因此失效。**

`tools/delegation_live_log.py:73 @ 863e313`
```python
def _one_line(text: Any, limit: int) -> str:
    """Collapse to a single line and truncate with an elided-chars note."""
    s = str(text or "")
    s = " ".join(s.split())  # collapse newlines/runs of whitespace
    if len(s) > limit:
        omitted = len(s) - limit
        s = s[:limit] + f" …(+{omitted} chars)"
    return s
```

`tools/delegation_live_log.py:186 @ 863e313`
```python
    def tool_result(self, name: str, result: Any = None,
                    duration: Any = None, is_error: bool = False) -> None:
        status = "ERROR" if is_error else "ok"
        dur = ""
        try:
            if duration is not None:
                dur = f" {float(duration):.1f}s"
        except (TypeError, ValueError):
            pass
        self.event("result", f"{name or '?'} {status}{dur}: "
                             f"{_one_line(result, _RESULT_MAX)}")
```

即 `_one_line(result)` 在 `event()`(内部才 `_redact`)之前执行。
而脱敏器里相当一部分规则是 `^` 行锚定 + `re.MULTILINE` 的:

`agent/redact.py:199 @ 863e313`
```python
# NOTE(perf): possessive quantifiers wherever the successor is disjoint; the
# leading ``[A-Za-z0-9_.\-]*`` stays backtrackable (see _CFG_DOTTED_RE note).
_YAML_ASSIGN_RE = re.compile(
    rf"(^[ \t]*+[A-Za-z0-9_.\-]*{_YAML_CFG_NAMES}[A-Za-z0-9_.\-]*+)(:[ \t]*+)(?!['\"])([^\s&]++)",
    re.IGNORECASE | re.MULTILINE,
```

换行被抹掉之后,除第一行外的所有行都不再位于 `^`,规则整体失配。
**A/B 对照复现**(同一段文本,只差调用顺序):

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python - <<'PY'
import os, sys, tempfile
os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="hermes-home-")
sys.path.insert(0, "/home/user/hermes-agent")
from agent.redact import redact_sensitive_text
from tools.delegation_live_log import _one_line, _redact, _RESULT_MAX
raw = ("DB_HOST=db.internal\n"
       "password: hunter2correcthorse\n"
       "export DATABASE_PASSWORD=s3cr3t-prod-pw\n")
print("=== A. 先脱敏(其它 sink 的做法)===");  print(redact_sensitive_text(raw, force=True))
print("=== B. 先压成一行再脱敏(live log 的做法)==="); print(_redact(_one_line(raw, _RESULT_MAX)))
PY
```

```console
=== A. 先脱敏(其它 sink 的做法)===
DB_HOST=db.internal
password: hunter...orse
export DATABASE_PASSWORD=***

=== B. 先压成一行再脱敏(live log 的做法)===
DB_HOST=db.internal password: hunter2correcthorse export DATABASE_PASSWORD=***
```

**判定**:同一段 `.env` / 配置文件输出,走别的 sink 会被遮蔽,走实时转录**不会**。
而这个文件恰恰是**被只读挂载进沙箱**的那一个 —— 也就是 `_redact` 自己的
docstring 说「a transcript that skipped it is the one place the operator's keys
land in plaintext」所要防的那个场景,只是漏的不是「跳过了」而是「顺序错了」。
修法零成本:`event()` 里把 `_redact` 提到 `_one_line` 之前,或在各 typed helper
里改成 `_one_line(_redact(x), limit)`。

⚠️ 附带一提,截断也在脱敏之前:`_RESULT_MAX = 400` 会先砍掉长输出的尾部。
这在多数情况下**降低**泄漏面(400 字之后的东西根本不写),但也意味着
「被截断的密钥前缀」会以明文留下——`sk-proj-BBBB…` 的前 400 字里若含完整密钥
仍靠正则挡,靠截断挡是运气。

### 8.4 保留与清理

`tools/delegation_live_log.py:404 @ 863e313`
```python
def prune_stale_live_dirs(max_age_days: int = LIVE_RETENTION_DAYS) -> int:
    """Remove live/<delegation_id> dirs older than the retention window.

    Returns how many were removed. Fully best-effort.
    """
    removed = 0
    try:
        root = live_transcript_root()
```

7 天,**没有配置项**,在每次新派发时顺手清一次(`create_live_transcripts` 开头)。
模块头把这条写成设计约束:「No config knobs. Retention is a module constant
(7 days), pruned opportunistically on each new dispatch.」——一个只在有新工作时
才做清理的策略,好处是零后台线程,坏处是一个长期不派发的实例永远不清。

◇ **id 空间只有 32 bit**:`new_live_delegation_id()` 与 `_new_delegation_id()`
都是 `f"deleg_{uuid.uuid4().hex[:8]}"`。7 天窗口内派发到几万次量级时,
生日碰撞概率就不可忽略;碰撞的后果是 `LiveTranscriptWriter.__init__` 的
`write_text` **截断**掉前一个批次的转录,以及 durable 表 `INSERT OR REPLACE`
覆盖掉前一行。概率低,但两处都是**静默**覆盖,不是报错。

---

## 9. 背压全景:同时发起很多异步委派会怎样

### 9.1 一个旋钮管两件事

`tools/delegate_tool.py:526` 的 `_get_max_async_children()` 直接返回
`_get_max_concurrent_children()`;老的 `delegation.max_async_children` 被弃用,
存在就打一次警告然后忽略。默认值 3(`_DEFAULT_MAX_CONCURRENT_CHILDREN = 3`,
`tools/delegate_tool.py:120`)。

`tools/async_delegation.py:76 @ 863e313`
```python
_DEFAULT_MAX_ASYNC_CHILDREN = 3
# How many completed records to retain for status queries before pruning.
_MAX_RETAINED_COMPLETED = 50
_DURABLE_RETENTION_SECONDS = 7 * 24 * 60 * 60
_MAX_DURABLE_PENDING = 1000
# A pending completion whose delivery keeps failing is retried across claim
# cycles (and across restarts via restore_undelivered_completions). Cap the
# attempts so an unroutable row converges to a terminal 'dropped' state
# instead of replaying on every restart forever.
_MAX_DELIVERY_ATTEMPTS = 8
_DB_LOCK = threading.Lock()
```

### 9.2 满了就**拒绝**,不排队

`tools/async_delegation.py:761 @ 863e313`
```python
    with _records_lock:
        running = sum(
            1 for r in _records.values()
            if r.get("status") in ("running", "stalling")
        )
        if running >= max_async_children:
            return {
                "status": "rejected",
                "error": (
                    f"Async delegation capacity reached ({max_async_children} "
                    f"running). Wait for one to finish (its result will re-enter "
                    f"the chat), or run this task synchronously "
                    f"(background=false). Raise delegation.max_concurrent_children in "
                    f"config.yaml to allow more concurrent background subagents."
                ),
            }
        _records[delegation_id] = record
```

**容量检查和插记录在同一次持锁内完成**,注释点名了理由:分开做会让两个并发
dispatch 都通过检查。这是重实现时最容易写错的一处——`if active_count() < cap:`
后面再 `add()` 是错的。

拒绝而不是排队的理由也写在 docstring 里:「so a runaway model can't pile up
unbounded background work」。配合 `delegate_tool` 侧的同步回落,拒绝对用户
是无感的(任务照跑,只是变成前台等)。

### 9.3 线程账:一个旋钮 K,最坏 K + 2K² 个线程

三层池,都是 `DaemonThreadPoolExecutor`:

| 池 | 创建处(行号) | 规模 | 生命期 |
|---|---|---|---|
| 异步单元池 | `tools/async_delegation.py` 527 | `max_async_children` = K | 模块级,只增不减 |
| 批内并行池 | `tools/delegate_tool.py` 3021 | `max_children` = K | 每批一个,`with` 块 |
| 单子代理超时包装 | `tools/delegate_tool.py` 2172 | 1 | 每个子代理一个 |

`tools/async_delegation.py:516 @ 863e313`
```python
def _get_executor(max_workers: int) -> ThreadPoolExecutor:
    """Lazily create (or grow) the shared daemon executor.

    We never shrink — ThreadPoolExecutor can't resize — but if the configured
    cap grows between calls we rebuild a larger pool. Existing in-flight
    futures keep running on the old pool until it's garbage collected.
    """
    global _executor, _executor_max_workers
    with _executor_lock:
        if _executor is None or max_workers > _executor_max_workers:
            # Daemon threads: thread_name_prefix aids debugging in stack dumps.
            _executor = _DaemonThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="async-delegate",
            )
            _executor_max_workers = max_workers
        return _executor
```

因为 `len(tasks) > max_children` 会被直接拒绝,一批最多 K 个任务;
异步单元最多 K 个。于是最坏线程数 = K(单元)+ K×K(批内)+ K×K(超时包装)
= **K + 2K²**。K=3 → 21 个线程;K=15 → **465 个线程**。
`_get_max_concurrent_children()` 在 K>10 时只打一次成本警告,**不设上限**
(「Users can raise this as high as they want; only the floor (1) is enforced」)。
重实现时这是个应当显式记账的数字 —— 一个「并发子代理数」旋钮实际上是平方级的
线程放大器。

### 9.4 生命周期 API 没有背压(见 §6.4),两套策略并存且无文档解释。

---

## 10. 文档 vs 代码

判定原则(CLAUDE.md):把断言所在的**整句/整段**一并判定,并确认它归哪个标题管。
本节全部三条都在 `AGENTS.md` 的 `## Delegation (delegate_task)` 标题下
(标题在 `AGENTS.md:983`),或 skill 参考文件的 `### Delegation (delegate_task)` 下。

### ▲1 `AGENTS.md:986-989` —— 把 `background` 说成一个可选开关

`AGENTS.md:986 @ 863e313`
> context + terminal session. By default the parent waits for the
> child's summary before continuing its own loop. With `background=true`,
> Hermes returns a delegation id immediately and the result re-enters the
> conversation later through the async-delegation completion queue.

**整段判定**(四句连读,归 `## Delegation (delegate_task)` 管):

- 「By default the parent waits for the child's summary」——**对模型而言是错的**。
  顶层模型发起的委派**默认就是后台**(`run_agent.py:7658` 的 `background=(not _is_subagent)`)。
  只有直接用 Python 调 `delegate_task()` 的调用方才保留同步默认。
- 「With `background=true`, Hermes returns a delegation id immediately」——
  这个开关**已被显式弃用并忽略**(`tools/delegate_tool.py:3854-3864` 的
  `"DEPRECATED / IGNORED."`),模型设不设都一样。
- 「returns a delegation id immediately」还漏了两条同步回落路径(§2.2)。
- 最后一句「the result re-enters the conversation later through the
  async-delegation completion queue」**成立**。

**可复现判据**:

```verify
cd /home/user/hermes-agent && grep -n "DEPRECATED / IGNORED" tools/delegate_tool.py && grep -n "background=(not _is_subagent)" run_agent.py
```

⚠️ 这条与「同步委派」子代理的 `delegate_tool.py` 范围有重叠,报告合并时请去重。

### ▲2 `AGENTS.md:1005` —— `max_spawn_depth` 默认值写成 2,代码是 1

`AGENTS.md:1003 @ 863e313`
> - `role="orchestrator"` — retains `delegate_task` so it can spawn its
>   own workers. Gated by `delegation.orchestrator_enabled` (default true)
>   and bounded by `delegation.max_spawn_depth` (default 2).

代码里默认值是 `MAX_DEPTH = 1`(`tools/delegate_tool.py:127`),
`_get_max_spawn_depth()` 在配置缺省时返回它。website 文档反而是**对的**
(`website/docs/user-guide/features/delegation.md:307` 写 "default **1** = flat,
so `role=\"orchestrator\"` is a no-op at defaults")。所以是 AGENTS.md 单点腐烂。

```verify
cd /home/user/hermes-agent && grep -n "^MAX_DEPTH = " tools/delegate_tool.py && grep -n "max_spawn_depth (default 2)" AGENTS.md && grep -n "default \*\*1\*\* = flat" website/docs/user-guide/features/delegation.md
```

⚠️ 这条严格说属于「同步委派/深度」范围,同样请去重。我记在这里是因为它就在
我判定 ▲1 的**同一段**里(判定一条文档断言必须把整段一并判定)。

### ◎3 `AGENTS.md:1012-1014` 与 skill `background-systems.md:19-22` —— 「不持久」说得过于绝对

`AGENTS.md:1012 @ 863e313`
> Durability rule: background `delegate_task` is detached from the current
> turn but still process-local. For work that must survive process restart, use
> `cronjob` or `terminal(background=True, notify_on_complete=True)` instead.

`skills/autonomous-ai-agents/hermes-agent/references/background-systems.md:19 @ 863e313`
> - **Not durable.** A backgrounded child is still process-local — if the
>   parent process exits, the child is lost. For work that must outlive
>   the process, use `cronjob` or
>   `terminal(background=True, notify_on_complete=True)`.

**字面为真**(在跑的子代理确实随进程消失,§5.1/§5.2),所以按 CLAUDE.md 的
记号约定**不算 ▲**,记 ◎:它**显著保守**地隐藏了这套机制真正持久的那一半——

- 每次派发都会往 `state.db` 的 `async_delegations` 表写一行(`_persist_dispatch`);
- 重启后 `recover_abandoned_delegations()` 把无主行判成 `unknown` 并**重放一条
  完成事件**,用户会收到「outcome unknown」的告知,而不是石沉大海;
- 一个**跑完了但没送出去**的结果会被 `restore_undelivered_completions()` 完整恢复
  并重新投递。

website 文档把这两条都写对了(`delegation.md:314-315`),AGENTS.md 与 skill
参考没有。对一个「不看源码」的读者,读 AGENTS.md 会以为进程一挂什么都没了。

### 其它对照结果(无冲突,记录以免下轮重查)

- `AGENTS.md:996`「Concurrency is capped by `delegation.max_concurrent_children`
  (default 3)」—— 与 `_DEFAULT_MAX_CONCURRENT_CHILDREN = 3` 一致。
- `website/docs/user-guide/features/delegation.md` 的「Stall Detection」整节
  (450s / 1200s / 120s / `stalled_after_quiet_seconds` 等四个字段)与
  `tools/async_delegation.py:109-112` 及 `_finalize_stalled` 的 `stall_meta`
  **逐项一致**,是本簇文档质量最高的一段。
- `delegation.md:280-284` 的实时转录路径与 `live_transcript_root()` 一致。
- `delegation.md:312-316` 的四条生命周期规则与 §5 的代码判定一致。
- **`subagent_lifecycle` 这套插件 API 在 `AGENTS.md` / `README.md` /
  `website/docs/` 里完全没有出现**。搜索面:对这三处
  `grep -rn "subagent_lifecycle\|SubagentLifecycleService\|SubagentHandle"`,
  0 命中。记 ◇ —— 一个明确自称 "Public ... supported boundary for plugins"
  的 API,没有任何面向用户的文档。

```verify
cd /home/user/hermes-agent && grep -rn "subagent_lifecycle\|SubagentLifecycleService\|SubagentHandle" AGENTS.md README.md website/docs/ ; echo "exit=$? (1 = 零命中)"
```

---

## 11. 测试作为行为规格

```verify
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
  tests/tools/test_async_delegation.py tests/agent/test_subagent_lifecycle.py \
  tests/tools/test_delegation_live_log.py tests/tools/test_async_delegation_fd_leak.py \
  tests/tools/test_restored_delegation_ownership.py tests/gateway/test_delegation_session_id_leak.py \
  tests/tools/test_delegate_kanban_isolation.py tests/cron/test_cron_kanban_env_isolation.py \
  tests/tools/test_hermes_subprocess_env.py
```

```console
=== Summary: 9 files, 90 tests passed, 0 failed (100% complete) in 9.2s (8 workers) ===
```

**环境**(CLAUDE.md 要求同时记):`/home/user/hermes-venv`,
`ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l` = **87**,
Python 3.11.15。基线在测试前后均 `git status --porcelain` 为空。

几个测试直接就是行为规格,值得当文档读:

- `tests/tools/test_async_delegation.py:68` `test_active_for_session_counts_every_live_delegation_state`
  —— 明确断言 `running/stalling/finalizing` 三态都算「活」。这条规格与
  `_prune_completed_locked` 的判据冲突(§5.5),但**没有测试覆盖那个函数**。
- `tests/tools/test_restored_delegation_ownership.py` —— 恢复事件的 `restored`
  标记必须让无过滤排空**放回队列**(#64484 的回归护栏)。
- `tests/tools/test_async_delegation_fd_leak.py` —— 每个 durable 操作后
  文件描述符不增长,盯的是 `_transaction()` 里那个 `finally: conn.close()`。
- `tests/agent/test_subagent_lifecycle.py` 只有 **4 个用例**,覆盖 1515+540 行里
  最公开的那套 API。停滞监控、投递认领的并发路径基本靠 `test_async_delegation.py`
  的 20 个用例撑。

---

## 12. 重实现同等机制的要点清单

1. **异步的决策权在 harness,不在模型**。模型不知道自己的宿主两分钟后还在不在。
2. **异步单位 = 一次 dispatch**,批次整体占一个槽,合成一条结果。否则一次
   fan-out 就能打满后台池。
3. **结果只能作为新一轮进入对话**,不能回填历史消息 —— prompt cache 与
   消息角色交替是硬约束。
4. **拆开「跑完了」和「送到了」两条状态线**,恢复逻辑完全不同。
5. **投递必须 at-least-once + 幂等 + 正向所有权证明**;条件 UPDATE 的
   `rowcount == 1` 是最省事的仲裁原语,并给认领加过期时间。
6. **无主判定用 pid + 进程启动时刻双因子**;判定结果是 `unknown` 不是 `failed`。
7. **不要墙钟超时,要进度冻结检测**;冻结后先打断给机会自救,再强制终局。
   采样失败时**不刷新**时间戳。
8. **容量检查与插入必须同一次持锁**;满了拒绝而不是排队,并提供同步退路。
9. **worker 线程必须显式传播上下文**(ContextVars + 线程本地回调),
   一个漏掉的提交点就是一个安全边界的缺口(§6.3)。
10. **「活着」的定义只写一次**,所有地方引用同一个常量集合(§5.6 的五种定义
    直接产出了 §5.5 的缺陷)。
11. **脱敏必须在任何格式化之前**——压行、截断、拼接都会破坏行锚定规则(§8.3)。
12. **每个并发实体一个日志文件**,追加模式、每次写开关句柄;并发问题用切分消解,
    不用锁去争。
13. **子代理身份用 ContextVar,跨 fork 降级成环境变量标记**,并保留
    `env=None` 的原语义。
14. **公开 API 的不支持字段要显式报错,不要静默忽略**(§6.6)。
15. **句柄用每进程随机密钥的 HMAC 能力票据**,重启后自然失效 —— 让「重连」
    诚实地失败,而不是偷偷重跑。

---

## 13. 移交给后续轮次的未决项(带锚点 + 一句话现象)

| # | 锚点文件(行号) | 一句话现象 | 建议 |
|---|---|---|---|
| A-1 | `tools/async_delegation.py` 1015(批)/ 779(单) | `_persist_dispatch` 抛异常时内存记录不撤销,永久占一个并发槽(§5.4 已复现) | 报告记 ■;可作为「向上游提 issue」的候选 |
| A-2 | `tools/async_delegation.py` 639 | `_prune_completed_locked` 用 `status != "running"` 判据,会裁掉 `stalling` 记录,导致 `stalled` 终局事件永不发出(§5.5 已复现) | 同上 |
| A-3 | `agent/subagent_lifecycle.py` 259 | `_EXECUTOR.submit(self._run, ...)` 未包 `propagate_context_to_thread`,worker 线程丢审批 session key 与 profile 覆盖(§6.3 已复现) | 优先级最高,涉及安全边界与 profile 隔离 |
| A-4 | `tools/delegation_live_log.py` 195 / 73 | `_one_line` 先压行、`_redact` 后跑,`agent/redact.py:201` 的 `re.MULTILINE` 行锚定规则整体失配(§8.3 A/B 已复现) | 该文件被只读挂载进沙箱,泄漏面真实 |
| A-5 | `tools/async_delegation.py` 1150 | `_ensure_stale_monitor` 用 `is_alive()` 判定,与监控线程 `return` 之间有窗口,可能让一次派发无人监控(§4,**未实测命中**,按代码判定) | 下轮若做并发压测可尝试触发 |
| A-6 | `agent/subagent_lifecycle.py` 165 | 插件生命周期 API 无并发上限、队列无界,与 `async_delegation` 的「拒绝」策略相反(§6.4) | 设计问题,非缺陷;R12 蓝图里应统一 |
| A-7 | `agent/subagent_lifecycle.py` 40 | `STARTING` 枚举值全仓零写入方(§6.1,搜索面已给) | ◇,备查 |
| A-8 | `tools/async_delegation.py` 677 | 单发接口 `dispatch_async_delegation` 生产零调用方,仅测试使用(§2.3,搜索面已给) | ◇,重实现时删除候选 |
| A-9 | `tools/async_delegation.py` 392 | `claim_completion_delivery` 在 durable 行不存在时返回 `True`,裁剪过的记录会被多消费者同时「认领成功」→ 重复投递(§3.3) | 需与 `_prune_durable_records` 的三重上限一起判 |
| A-10 | `run_agent.py` 7651 | 注释称 "each task becomes its own independent background subagent",实际是整批一个单元一条事件(§2.1) | 陈旧注释,不计入 ▲ |
| A-11 | `agent/subagent_lifecycle.py` 190 | 类 docstring 称结果保留到进程退出,实际 1 小时后由下次 `launch()` 清掉(§6.4) | docstring 与代码矛盾,不计入 ▲ |
| A-12 | `tools/delegation_live_log.py` 208 / 216 | `_stream_buf` 不在 `self._lock` 内,超时路径上父线程 `_flush` 与子线程 `add_stream_delta` 可交错,丢增量(§8.2) | ■(轻微) |
