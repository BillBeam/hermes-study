# r7b-20 · 第一层守卫 —— 适配器进程内的会话串行化

> 底稿。基线 `863e31318553cda8ad61df681d08175364d4164b`。R7 已定案第二层(网关侧回合租约);
> 本篇定案第一层,并落实 R7 移交的「base.py 第一层守卫文档描述」一项(定案见 `r7b-10` §6 ▲B-1)。

## 0. 一句话

第一层守卫用**三个字典**把"同一会话同时只跑一个回合"钉在适配器进程内;它的全部复杂度
来自一个事实:**释放守卫的时机比获取守卫难得多**。

## 1. 从一次具体故障说起

用户在 Telegram 里问了个长问题,agent 开始跑。跑到一半用户又发一句补充。此时:

- 如果适配器**不管**:两条消息各自起一个 agent,同一会话两个回合并行 → 重复回复、
  重复工具调用、历史交错。
- 如果适配器**简单地加锁**:第二条消息被丢弃 → 用户的补充石沉大海。
- 如果适配器**加锁但释放时机错**:第一个回合结束时把锁删了,而排水任务还在跑 →
  回到第一种情况。
- 如果适配器**加锁但没释放**(任务崩溃/被取消):会话永久卡死,用户看到无限
  "Interrupting current task…",只能重启网关 —— 这就是 issue #11016 的现场。

第一层守卫是对这四种失败的**同时**回应。

## 2. 三元组状态

```python
        # Track active message handlers per session for interrupt support.
        # _active_sessions stores the per-session interrupt Event; _session_tasks
        # maps session → the specific Task currently processing it so that
        # session-terminating commands (/stop, /new, /reset) can cancel the
        # right task and release the adapter-level guard deterministically.
        # Without the owner-task map, an old task's finally block could delete
        # a newer task's guard, leaving stale busy state.
        self._active_sessions: Dict[str, asyncio.Event] = {}
        self._pending_messages: Dict[str, MessageEvent] = {}
        self._session_tasks: Dict[str, asyncio.Task] = {}
```

(`gateway/platforms/base.py:2775-2785 @ 863e313`)

| 字典 | 职责 | 为什么不能省 |
|---|---|---|
| `_active_sessions[key] -> asyncio.Event` | **忙标志**兼**中断信号** | 键存在 = 忙;Event 被 set = 请停 |
| `_pending_messages[key] -> MessageEvent` | **单槽**待处理消息 | 忙时不丢消息,又不无限堆积 |
| `_session_tasks[key] -> asyncio.Task` | **属主任务** | 精确取消 + 判定守卫是否"陈旧" |

**一个 Event 兼两职**是核心巧思:`key in _active_sessions` 表示"忙",
`_active_sessions[key].is_set()` 表示"已被要求中断"。于是"清空 Event 但保留键"
= "上一回合结束了,但会话仍归我管" —— 这个中间态在 §5 的回合链里是决定性的。

## 3. 释放必须校验身份

```python
        current_guard = self._active_sessions.get(session_key)
        if current_guard is None:
            return
        if guard is not None and current_guard is not guard:
            return
        del self._active_sessions[session_key]
```

(`gateway/platforms/base.py:5325-5330 @ 863e313`;函数体 docstring 在 `:5318-5323`)

> When ``guard`` is provided, only release the entry if it still points
> at that exact Event.  This lets reset-like commands swap in a temporary
> guard while the old processing task unwinds, without having the old
> task's cleanup accidentally clear the replacement guard.

**场景**:用户发 `/reset`。命令路径换入一个 `command_guard` 并取消旧任务;旧任务的
`finally` 这时才醒来收尾。若释放不校验身份,旧任务会删掉 `/reset` 刚装上的守卫,
`/reset` 处理到一半就"看起来不忙了",下一条消息挤进来。**用身份比较把"我释放的必须是
我装的那一个"变成不变量。**

## 4. 入口自愈(#11016)

```python
        # On-entry self-heal: if the adapter still has an _active_sessions
        # entry for this key but the owner task has already exited (done or
        # cancelled), the lock is stale.  Clear it and fall through to
        # normal dispatch so the user isn't trapped behind a dead guard —
        # this is the split-brain tail described in issue #11016.
        if session_key in self._active_sessions:
            self._heal_stale_session_lock(session_key)
```

(`gateway/platforms/base.py:5584-5590 @ 863e313`)

"陈旧"的判定刻意保守(`gateway/platforms/base.py:5332-5346 @ 863e313`):

```python
    def _session_task_is_stale(self, session_key: str) -> bool:
        """Return True if the owner task for ``session_key`` is done/cancelled.

        A lock is "stale" when the adapter still has ``_active_sessions[key]``
        AND a known owner task in ``_session_tasks`` that has already exited.
        When there is no owner task at all, that usually means the guard was
        installed by some path other than handle_message() (tests sometimes
        install guards directly) — don't treat that as stale.
        """
```

**无属主任务 ≠ 陈旧**。理由是"守卫可能由 handle_message 以外的路径装上"。取舍很清楚:
**宁可漏治一个,不可误杀一个** —— 误判陈旧会把正在跑的回合的守卫清掉,后果(双 agent)
比卡死更糟。故事化:#11016 的症状是"无限 Interrupting",修法不是"超时强解",
而是"下一条消息进来时,如果属主任务确已死亡,就地清理并正常派发"。
**自愈发生在入口而非定时器**,所以不需要额外的看门狗线程。

`tests/gateway/test_session_split_brain_11016.py` 是这条的行为规格(本轮已跑通)。

## 5. `handle_message` 的完整决策树

```
handle_message(event)
├─ 无 _message_handler → return                              base.py:5562-5563
├─ coerce_plaintext_gateway_command(event)                   base.py:5565
├─ [Telegram & DM & 装了钩子] → to_thread(_apply_topic_recovery)  base.py:5566-5576
├─ session_key = build_session_key(...)                      base.py:5578-5582
├─ [键在 _active_sessions] → _heal_stale_session_lock         base.py:5584-5590
└─ 忙?
   ├─ 是(键仍在 _active_sessions)                            base.py:5592
   │  ├─ cmd = event.get_command()
   │  ├─ should_bypass_active_session(cmd)?                  base.py:5608
   │  │  ├─ is_interrupt_then_dispatch(cmd)  → _dispatch_active_session_command
   │  │  │     (/stop /new /reset:取消在飞任务 + 保序排水)     base.py:5611-5625
   │  │  └─ 其余(/approve /deny /status /background /restart)
   │  │        → inline:直接 await _message_handler + 发回复    base.py:5627-5654
   │  ├─ [非命令] 有待决 clarify? → inline 路由到 clarify 解析器  base.py:5656-5706
   │  ├─ _busy_session_handler(event, key) 返回 True → return   base.py:5708-5713
   │  ├─ [PHOTO] → merge_pending_message_event,不打断           base.py:5715-5719
   │  ├─ [queue 模式的普通文本] → _queue_text_debounce           base.py:5721-5730
   │  └─ 其余 → merge_pending_message_event(merge_text=TEXT)    base.py:5731-5744
   └─ 否 → _start_session_processing(event, session_key)        base.py:5746-5754
```

### 5.1 关键结论:第一层默认**不打断**

上表里**没有任何一处** `interrupt_event.set()`。全文件唯一的 `.set()` 在
`interrupt_session_activity`(`gateway/platforms/base.py:4808-4813 @ 863e313`),
调用者全在第二层(`gateway/run.py:23127`/`:23131`)与 relay 适配器
(`gateway/relay/adapter.py:626 @ 863e313`)。

**第一层只做三件事**:命令绕过、把消息塞进单槽、把决策权交给
`_busy_session_handler`。真正的 interrupt/steer/redirect 策略机在第二层(R7 已精读)。
文档把两层混叙的定案见 `r7b-10` §6 ▲B-1。

### 5.2 两类绕过为什么必须分开

`/approve`、`/deny` 走 inline:agent 线程正阻塞在 `Event.wait` 上等审批,消息若入槽
就是**死锁**——审批永远到不了,回合永远不结束,槽永远不排水。注释直陈
(`gateway/platforms/base.py:5594-5604 @ 863e313`):

```python
            # Certain commands must bypass the active-session guard and be
            # dispatched directly to the gateway runner.  Without this, they
            # are queued as pending messages and either:
            #   - leak into the conversation as user text (/stop, /new), or
            #   - deadlock (/approve, /deny — agent is blocked on Event.wait)
            #
            # Dispatch inline: call the message handler directly and send the
            # response.  Do NOT use _process_message_background — it manages
            # session lifecycle and its cleanup races with the running task
            # (see PR #4926).
```

`/stop`、`/new`、`/reset` 则要**先取消再分发**,且要保住排队跟进的顺序 —— 所以有独立的
`_dispatch_active_session_command`。这两类都"绕过守卫",但一类是"读",一类是"写会话生命周期",
合并处理会让取消与清理互相竞争(PR #4926 的教训)。

### 5.3 clarify 文本拦截:与 `/approve` 同形的第三类死锁

```python
            # Clarify reply bypass: if the agent is blocked on a
            # clarify_tool call, the next non-command message in this
            # session MUST reach the runner so typed numeric choices,
            # exact choices, and free-form "Other" answers can resolve the
            # clarify-intercept and unblock the agent.
            #
            # Without this bypass: the message gets queued in
            # _pending_messages as a follow-up turn instead of reaching the
            # clarify resolver, leaving the agent blocked and discarding the
            # user's answer.
            # Same shape as the /approve deadlock fix (PR #4926) — both
            # cases are "agent thread blocked on Event.wait, message must
            # reach the resolver before being treated as a new turn."
```

(`gateway/platforms/base.py:5656-5669 @ 863e313`)

**这是一条可迁移的规律**:凡是"agent 阻塞等用户输入"的机制(审批、澄清、确认),
其应答**不是新回合**,必须在守卫之前旁路到解析器。设计新 harness 时,应把这类
"阻塞等待"注册成一张表,守卫统一查表,而不是每加一个就打一个补丁。

### 5.4 单槽的合并语义

`merge_pending_message_event`(`gateway/platforms/base.py:2438-2499 @ 863e313`)不是简单覆盖:

- 双方都是 PHOTO → 媒体列表**拼接**,文案合并(相册/连拍是多条事件);
- 任一方带媒体 → 拼接媒体、合并文案、类型向 PHOTO/非 TEXT 收敛;
- `merge_text=True` 且双方都是 TEXT → 文本按行**追加**(多段思路不被截断);
- 其余 → 覆盖(`pending_messages[session_key] = event`)。

**取舍**:单槽 + 合并,而不是无界队列。收益是"忙时无限堆积"不可能发生;代价是
普通文本在不开 `merge_text` 时会丢中间条目。上层用 `/queue` 的溢出缓冲
(`_queued_events`,R7C 范围)补上"每条都要独立成回合"的需求。

## 6. 回合链:守卫的"活着但空转"中间态

回合结束后若槽里有消息,不能直接释放守卫再重新获取 —— 那之间的空窗会放进第二个 agent。

```python
                # Keep the _active_sessions entry live across the turn chain
                # and only CLEAR the interrupt Event — do NOT delete the entry.
                # If we deleted here, a concurrent inbound message arriving
                # during the awaits below would pass the Level-1 guard, spawn
                # its own _process_message_background, and run simultaneously
                # with the recursive drain below.  Two agents on one
                # session_key = duplicate responses, duplicate tool calls.
                # Clearing the Event keeps the guard live so follow-ups take
                # the busy-handler path as intended.
                _active = self._active_sessions.get(session_key)
                if _active is not None:
                    _active.clear()
```

(`gateway/platforms/base.py:6309-6321 @ 863e313`)

这正是 §2 说的"一个 Event 兼两职"的兑现:**清空 = 重置中断意图;保留键 = 会话仍归我管**。

### 6.1 #17758:递归排水会把进程 SIGSEGV

```python
                # Spawn a fresh task for the pending message instead of
                # recursing.  Issue #17758: `await
                # self._process_message_background(...)` here grew the
                # call stack one frame per chained follow-up, and under
                # sustained pending-queue activity the C stack would
                # exhaust at ~2000 frames and SIGSEGV the process.
                # Mirror the late-arrival drain pattern below: hand off
                # to a new task and return so this frame can unwind.
                drain_task = asyncio.create_task(
                    self._process_message_background(pending_event, session_key)
                )
                # Hand ownership of the session to the drain task so
                # stale-lock detection keeps working while it runs.
                self._session_tasks[session_key] = drain_task
```

(`gateway/platforms/base.py:6324-6338 @ 863e313`)

**故事**:一个活跃群聊里用户连续发言,每条都在上一回合跑动时入槽。旧实现用
`await self._process_message_background(...)` 递归排水,每链一次栈深 +1;
约 2000 条之后 C 栈耗尽,整个网关进程 **SIGSEGV** —— 不是异常,是段错误,没有 traceback。
修法是**交棒**:起新任务、转移属主、当前帧立刻 unwind。

注意 `self._session_tasks[session_key] = drain_task` 这一行:**属主必须跟着交**,
否则自愈逻辑(§4)会看到"属主已 done"而误判整条链陈旧。

### 6.2 迟到排水与"别起两个"

清理阶段的 `await` 之间仍可能有消息落槽,所以 `finally` 里再排一次
(`gateway/platforms/base.py:6423-6432 @ 863e313`):

```python
            # Late-arrival drain: a message may have arrived during the
            # cleanup awaits above (typing_task cancel, stop_typing).  Such
            # messages passed the Level-1 guard (entry still live, Event
            # possibly set) and landed in _pending_messages via the
            # busy-handler path.  Without this block, we would delete the
            # active-session entry and the queued message would be silently
            # dropped (user never gets a reply).
```

但**排水任务可能已经被 §6.1 起过了**,于是要判属主(`base.py:6434-6449 @ 863e313`):

```python
                if (
                    existing_task is not None
                    and existing_task is not current_task
                ):
                    # The in-band drain (or an earlier late-arrival drain)
                    # already spawned a follow-up task that owns this
                    # session.  Re-queue the late-arrival event so that
                    # task picks it up — avoids spawning two concurrent
                    # _process_message_background tasks for the same key
                    # (#17758 follow-up: prevents the create_task path
                    # from racing with itself across the in-band/finally
                    # boundary).
                    self._pending_messages[session_key] = late_pending
```

**放回槽而不是起任务** —— 让已经拥有会话的那个任务去消费。

### 6.3 #48300:先释放,再**有条件**删属主

```python
        """Release the session guard for a finished owner task, then drop its
        ``_session_tasks`` entry ONLY if the guard was actually released.

        Release-then-conditional-delete is the #48300 fix: when a concurrent
        path (reset/new command, drain handoff) swapped ``_active_sessions[key]``
        to a different guard, ``_release_session_guard`` skips on the guard
        mismatch and the lock stays installed. If we deleted ``_session_tasks``
        unconditionally (the old order), ``_session_task_is_stale`` would later
        see no owner task and report "not stale", so the orphaned guard would
        never be healed — a permanent session deadlock. Keeping the done-task
        entry when the guard survives lets the on-entry self-heal detect the
        stale lock and clear it on the next inbound message.
        """
        self._release_session_guard(session_key, guard=interrupt_event)
        if session_key not in self._active_sessions:
            self._session_tasks.pop(session_key, None)
```

(`gateway/platforms/base.py:6492-6510 @ 863e313`)

**这是全簇最精妙的一处**,而且它是**两个保守设计互相咬合的产物**:
§3 的"释放校验身份"会在冲突时**跳过释放**;§4 的"无属主任务不算陈旧"要求
**有属主任务才能自愈**。如果释放失败却仍删属主,就同时踩中两条:守卫留着、属主没了、
自愈永远判"不陈旧" → **永久死锁**。修法是把删属主变成"只有守卫真的释放了才删",
让"守卫还在"这个事实带着它的属主一起留下,等下一条消息进来时被自愈收走。

**可迁移原则**:当两个机制各自为了安全而"保守跳过"时,要检查它们的**跳过路径是否
互相依赖**。两个独立正确的保守策略,组合起来可能构成一个不可恢复态。

## 7. 关停:落盘而非丢弃

```python
            flush_pending_to_file(self._pending_messages, reason="adapter_shutdown")
        ...
        self._pending_messages.clear()
        self._active_sessions.clear()
```

(`gateway/platforms/base.py:6563-6567 @ 863e313`)

槽里的消息在关停时写盘,重启后由恢复路径重投。这与 R7 定案的
"pending 落盘 #72680" 是同一条线在适配器侧的落点。

## 8. 【文档-代码冲突候选】

**▲ B-1 / ▲ B-2**:见 `r7b-10` §6(第一层"设置中断事件"证伪;`/stop` 与
`/approve` 不同路)。

**▲ B-7**:`docs/session-lifecycle.md:455-457 @ 863e313`:

> ```
> adapter._pending_messages: Dict[session_key, MessageEvent]
>     └── Single "next-up" slot per session. Overwritten on repeat sends
>         (burst collapse). Shared with photo-burst follow-ups.
> ```

"Overwritten" 只对**无媒体且未开 `merge_text` 的普通文本**成立。PHOTO 连拍是
**拼接**(`gateway/platforms/base.py:2464-2470 @ 863e313`),带媒体混合是**合并**
(`:2472-2489`),`merge_text=True` 的 TEXT 是**逐行追加**(`:2491-2497`)。
文档把四条分支压成一句 "overwritten",读者会以为连拍只留最后一张。

**◇ B-8**:#17758(递归排水 → C 栈耗尽 SIGSEGV)与 #48300(释放-删除顺序 →
永久死锁)两条修复的因果链只存在于代码注释;`docs/session-lifecycle.md` 讲了单槽/溢出
的数据结构,但没有任何关于**回合链交棒**与**属主转移**的描述 —— 而这恰恰是重实现时
最容易做错的部分。

**◇ B-9**:clarify 文本拦截(§5.3)在 `docs/session-lifecycle.md` 与
`website/docs/developer-guide/gateway-internals.md` 中均无描述,尽管它与
`/approve` 死锁属同一类问题、同一条修法。

## 9. 【bug 候选】

无。本段的所有"看起来奇怪"的写法(保留守卫、放回槽、条件删属主)都有注释给出的
明确理由,且各自有 issue 号支撑。

## 10. 【重实现要点】

1. **忙标志与中断信号合用一个 Event**:键存在=忙,Event set=请停,清空但保留键=
   "回合链中,仍归我管"。这个中间态是回合链正确性的关键。
2. **释放守卫必须校验身份**(释放的是不是我装的那一个)。
3. **属主任务要单独记**,并在交棒时同步转移;否则自愈会误判。
4. **自愈放在入口**,判定保守(无属主 ≠ 陈旧),宁漏勿误杀。
5. **排水用 create_task 交棒,不要递归 await** —— 递归会按链长增长 C 栈,最终段错误。
6. **迟到排水要先判属主**,已有属主就放回槽,不要再起任务。
7. **"释放失败"与"删属主"必须绑定**:只有真的释放了才删属主,否则自愈路径被永久掐断。
8. **阻塞等待类机制(审批/澄清/确认)的应答不是新回合**,必须在守卫前旁路;
   建议做成注册表而非逐个打补丁。
9. **关停时把待处理槽落盘**,不要丢。
