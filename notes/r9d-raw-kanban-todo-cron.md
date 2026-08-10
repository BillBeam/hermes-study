# r9d-C · 看板、待办与定时任务 —— agent 的自我任务管理三层

> 溯源约定:凡对 hermes-agent 行为的断言,紧跟 `路径:行号 @ 863e313` 与代码原文块;
> 锚点一律单独成行、置于块之前。基线 = `/home/user/hermes-agent` @ `863e313`。
> 命令输出与实验结果用 ```console / ```verify 围栏声明(非源码摘录)。
>
> 本片文件清单(5 文件 / 4073 行):
>
> | 路径 | 行数 | 一句话定位 |
> |---|---|---|
> | `tools/kanban_tools.py` | 2250 | 看板(kanban)工具面:worker / orchestrator 两套 schema + 心跳、评论注入桥 |
> | `agent/kanban_stop.py` | 108 | 回合循环里的「看板 worker 不许裸退」守卫(纯策略,无 I/O) |
> | `tools/todo_tool.py` | 335 | 单会话内存待办清单,压缩后重注入 |
> | `tools/project_tools.py` | 189 | 桌面「项目」(命名工作区)的显式切换工具 |
> | `tools/cronjob_tools.py` | 1191 | 让模型排定时任务的单一压缩工具 `cronjob` |
>
> **术语锚定**(首次出现):
> - **kanban(看板)**:一张跨进程共享的 SQLite 任务表,多个 agent 进程通过它领任务、交接、汇报。
> - **dispatcher(调度器)**:嵌在网关里的 tick 循环,把「ready」任务分配给 profile 并 spawn 一个 worker 进程。
> - **worker(工人)**:dispatcher 派生的一次性 agent 进程,环境里带 `HERMES_KANBAN_TASK=<任务id>`。
> - **orchestrator(编排者)**:配置里显式打开 `kanban` toolset、但**不**绑定单个任务的 profile,负责派活。
> - **toolset(工具集)**:一组工具的命名分组,决定哪些工具进模型的 schema(函数调用清单)。
> - **check_fn**:注册表为每个工具挂的「此刻可用吗」探针,结果被 TTL 缓存。
> - **CAS(compare-and-swap)**:「只有当前值等于我预期的那个,才写」的原子更新,用来做无锁抢占。
> - **approval(审批)**:执行危险 shell 命令前向人类要许可的闸门。
> - **steer / OUT-OF-BAND 注入**:在一次回合**运行中**往对话里塞一条消息,不等回合结束。

---

## 1. 这一片解决什么问题(先场景)

**场景一:一次长任务的交接。** 用户在 Telegram 里说「把这个仓库的 CI 修好并写份报告」。
orchestrator profile 调 `kanban_create` 拆成三张卡(修 CI / 跑测试 / 写报告),第三张卡的
`parents` 填前两张卡的 id。dispatcher 每个 tick 扫一遍板子,看到前两张 `ready` 就各 spawn
一个 worker 进程,环境里塞 `HERMES_KANBAN_TASK`。worker 干完调 `kanban_complete(summary=...)`;
两张都 `done` 之后第三张自动从 `todo` 升到 `ready`,再被 spawn。人类全程只看板子。

**场景二:模型narrate完就走。** worker 干完活,最后一句说「Let me write the report now」,
然后 `finish_reason=stop`、没有工具调用。进程 rc=0 干净退出 —— 而任务还是 `running`。
dispatcher 把这记成 `protocol_violation`。`agent/kanban_stop.py` 就是为这一种失败单独存在的
108 行:在回合循环判定「这一轮要结束了」的那一刻插一脚,合成一条 user 消息把模型顶回去。

**场景三:待办 ≠ 看板。** 同一个 agent 在一次会话里做 5 步事情,不需要跨进程、不需要落盘、
不需要别人看见 —— 那是 `todo`。它活在 `AIAgent` 实例上(每会话一个),唯一的持久化诉求是
「上下文压缩后别忘了我还有 3 步没做」。**两套的分界线是「有没有第二个进程要读它」。**

**场景四:让模型排班。** 用户说「每天早上 9 点给我发昨天的 PR 汇总」。模型调
`cronjob(action="create", schedule="0 9 * * *", prompt="...")`。到点由网关的 ticker 起一个
**全新的、无当前聊天上下文的** agent 跑那段 prompt,把最终回复投递回原聊天。
这里最要命的问题是:**这个未来的、无人看管的 agent,权限跟现在一样大吗?**

---

## 2. 逐文件 / 逐机制精读

### 2.1 `agent/kanban_stop.py` —— 108 行为什么值得单独一个文件

#### 2.1.1 它是纯策略,没有任何 I/O

文件头自己声明了定位。整个模块只有三个函数,不 import 数据库、不 import registry、
不 import agent。它只吃两样东西:进程环境变量 + 消息列表,吐一个字符串或 `None`。

`agent/kanban_stop.py:20 @ 863e313`

```python
_TERMINAL_KANBAN_TOOLS = frozenset({"kanban_complete", "kanban_block"})

_DEFAULT_MAX_ATTEMPTS = 2
```

这就是「停」的语义:**只有 `kanban_complete` 与 `kanban_block` 算终态**。
一句自然语言回复不是终态 —— 这正是它要教给模型的那条规则。

#### 2.1.2 「谁叫停谁」:是 harness 叫停模型的**退出**,不是叫停模型的**工作**

名字容易误读成「停止看板任务」。实际方向相反:模型想停(`finish_reason=stop`),
harness 不让它停。守卫位于回合循环里「文本回复即将成为最终答案」的分支。

`agent/conversation_loop.py:7164 @ 863e313`

```python
                try:
                    from agent.kanban_stop import build_kanban_stop_nudge

                    _kanban_nudge = build_kanban_stop_nudge(
                        messages=messages,
                        attempts=getattr(agent, "_kanban_stop_nudges", 0),
                    )
                except Exception:
                    logger.debug("kanban stop-loop check failed", exc_info=True)
                    _kanban_nudge = None
```

紧接着的处置:把这轮的 assistant 消息与合成 user 消息都打上 `_kanban_stop_synthetic` 标记,
`final_response = None` 后 `continue` 回循环顶端。

`agent/conversation_loop.py:7175 @ 863e313`

```python
                if _kanban_nudge:
                    agent._kanban_stop_nudges = (
                        getattr(agent, "_kanban_stop_nudges", 0) + 1
                    )
                    final_msg["finish_reason"] = "kanban_terminal_required"
                    final_msg["_kanban_stop_synthetic"] = True
                    messages.append(final_msg)
                    messages.append({
                        "role": "user",
                        "content": _kanban_nudge,
                        "_kanban_stop_synthetic": True,
                    })
```

`_kanban_stop_synthetic` 这个标记在 `run_agent.py:247` 的名单里,用于把合成回合从
持久化 transcript 里剥掉 —— **合成的顶回去不该污染历史**。这和同一段代码上方
`_pre_verify_synthetic` 的处理法完全同构:**「顶回去」是这个 harness 的一类通用手法,
kanban 只是其中一个 policy 插件。** 这解释了为什么它值得单独成文件:
回合循环需要的是一个「给我一句 nudge 或 None」的纯函数,而不是又一坨内联条件。

#### 2.1.3 开关语义:env 存在即开,显式关字才关

`agent/kanban_stop.py:31 @ 863e313`

```python
    env = os.environ.get("HERMES_KANBAN_STOP_NUDGE")
    if env is not None and env.strip().lower() in {"0", "false", "no", "off"}:
        return False
    task = (os.environ.get("HERMES_KANBAN_TASK") or "").strip()
    return bool(task)
```

注意这里读的是 `os.environ`,**不是** `gateway.session_context` 的 ContextVar。
下面 §4 的 ■3 会说明这一点造成的后果。

#### 2.1.4 「已经调过终态工具」的判定 —— 把失败的调用也算了进去

`agent/kanban_stop.py:56 @ 863e313`

```python
            continue
        role = msg.get("role")
        if role == "assistant":
            for tc in msg.get("tool_calls") or []:
                if _tool_call_name(tc) in _TERMINAL_KANBAN_TOOLS:
                    return True
        elif role == "tool":
            name = str(msg.get("name") or "")
            if name in _TERMINAL_KANBAN_TOOLS:
```

判定只看**调用发生过没有**,不看**调用成功没有**。这是 §4 ■1 的根。

---

### 2.2 `tools/kanban_tools.py` —— 两套 schema、三层守卫

#### 2.2.1 为什么是工具而不是 shell 出去调 CLI

模块头自己列了三条理由(后端可移植 / 无 shell 引号地雷 / 结构化错误),其中第一条是真正的
设计约束:worker 的终端工具可能指向 Docker / Modal / SSH,`hermes` 命令和 `~/.hermes/kanban.db`
都不在那个容器里;而工具跑在 agent 自己的 Python 进程里,永远够得着板子。
**可迁移原则:凡是「协调层」的动作,不要走被测环境的 shell,要走 harness 自己的进程。**

#### 2.2.2 三层守卫:schema 层、handler 层、DB 层

**第一层(schema 层,决定模型看不看得见)** 是 `check_fn`。两个 check_fn 把工具面切成两半:

`tools/kanban_tools.py:115 @ 863e313`

```python
    if _is_delegated_child_context():
        return False
    if os.environ.get("HERMES_KANBAN_TASK") and _is_dispatcher_owned_worker():
        return True
    return _profile_has_kanban_toolset()
```

`_check_kanban_orchestrator_mode` 是它的镜像:worker 上下文返回 `False`。
于是 `kanban_list` / `kanban_unblock` 只给 orchestrator,
`kanban_show/complete/block/heartbeat/comment/attach*/create/link` 两边都给。

**第二层(handler 层,防止 schema 层被绕过)** 有三个独立的守卫函数:

- `_reject_delegated_child_mutation(tool_name)` —— 拒绝 `delegate_task` 子 agent 的写操作。
- `_require_orchestrator_tool(tool_name)` —— 只要 `HERMES_KANBAN_TASK` 存在就拒(注释自称 belt-and-suspenders)。
- `_enforce_worker_task_ownership(tid)` —— worker 只能动自己那张卡。

`tools/kanban_tools.py:202 @ 863e313`

```python
    env_tid = os.environ.get("HERMES_KANBAN_TASK")
    if not env_tid:
        # Orchestrator or CLI context — no task-scope restriction.
        return None
    if tid != env_tid:
        return tool_error(
            f"worker is scoped to task {env_tid}; refusing to mutate "
            f"{tid}. Use kanban_comment to hand off information to other "
            f"tasks, or kanban_create to spawn follow-up work."
        )
    return None
```

这条错误消息本身就是一份**「允许的跨任务通道」清单**:`kanban_comment` 与 `kanban_create`。
它**没有列 `kanban_link`** —— 而 `kanban_link` 恰恰也是跨任务写。见 §4 ■2。

**第三层(DB 层,唯一的真信任边界)** 在 `hermes_cli/kanban_db.py` 的 `write_txn` 里。

`hermes_cli/kanban_db.py:165 @ 863e313`

```python
def _assert_not_delegated_child_mutation() -> None:
    """Reject Kanban state mutations from ``delegate_task`` child contexts.

    The structured kanban tools and CLI dispatch layer both have fast-fail
    guards for better UX, but neither is a trust boundary: a delegated child can
    still shell out to the CLI or import this module directly. The actual
    invariant belongs at the DB/filesystem mutation layer so every public
    mutator that uses ``write_txn`` (tasks, runs, comments, attachments,
    dispatcher claims, repair events, subscriptions, GC, etc.) and every board
    metadata mutator fails closed before touching durable state.
    """
```

**这段注释是本片最值得抄走的设计原则:工具层的守卫是 UX(给模型一句能读懂的拒绝),
真正的不变量必须钉在「碰持久状态的那一层」,因为模型总能绕过工具层(shell 出去、直接 import)。**

#### 2.2.3 check_fn 有 30 秒 TTL 缓存,缓存键里没有委派上下文

`tools/kanban_tools.py:54` 的注释声称「check_fn 结果被注册表 TTL 缓存(~30s)」,属实:

`tools/registry.py:216 @ 863e313`

```python
_CHECK_FN_TTL_SECONDS = 30.0
```

但缓存键是 `(fn, scope)`,`scope` 只按 profile 维度(多路复用网关下才非 `None`),
**不含 delegation ContextVar**。实测:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "
import os,sys,tempfile
os.environ['HERMES_HOME']=tempfile.mkdtemp(); os.environ['HERMES_KANBAN_TASK']='t_parent'
sys.path.insert(0,'/home/user/hermes-agent')
import tools.kanban_tools as kt
from tools.registry import _check_fn_cached
from agent.delegation_context import delegated_child_context
print('parent, uncached:', _check_fn_cached(kt._check_kanban_mode))
with delegated_child_context():
    print('child, direct call:', kt._check_kanban_mode())
    print('child, via registry cache:', _check_fn_cached(kt._check_kanban_mode))
"
```

```console
parent, uncached: True
child, direct call: False
child, via registry cache: True
```

结论:30 秒窗口内,同进程的 `delegate_task` 子 agent 的 **schema 里会出现 kanban 工具**。
写操作会被第二/第三层挡住(所以不是漏洞),但**只读的 `kanban_show` 两层都没挂守卫**
(见下 §4 ◇2)。这正是「belt-and-suspenders 注释里说的那种情况真会发生」的实证。

#### 2.2.4 `kanban_complete` 的四道闸

按代码顺序:

1. **委派子 agent 拒绝** → 2. **任务归属**(`_enforce_worker_task_ownership`)
→ 3. **敏感信息脱敏**(`summary` / `result` / `metadata` 全部过 `redact_sensitive_text(..., force=True)`)
→ 4. **goal_mode 判官闸**。

第四道最有设计含量。`goal_mode` 卡片(开放式目标、跑到判官说完成为止)如果只在回合末尾判,
模型可以抢先调 `kanban_complete` 自己宣布完成。于是在真正写库前先过一次判官:

`tools/kanban_tools.py:732 @ 863e313`

```python
            task = kb.get_task(conn, tid)
            if task and task.goal_mode and _goal_judge_available():
                verdict = "done"
```

关键在 `_goal_judge_available()` 这个前置探测。`judge_goal` 在没有辅助模型可用时是
**fail-open** 的:它返回一个和「还没做完」**无法区分**的 `"continue"`。如果不先探测,
一个没配辅助模型的部署会让每个 `goal_mode` worker **永远关不掉自己的卡**。

`tools/kanban_tools.py:233 @ 863e313`

```python
def _goal_judge_available() -> bool:
    """True when an auxiliary client is configured for the goal judge.

    ``judge_goal`` is fail-open at the source: when no auxiliary model can
    be reached it returns a ``"continue"`` verdict that is indistinguishable
    from a real "not done yet" judgment. The completion gate must not treat
    that as a rejection, or an unconfigured/degraded auxiliary model would
    wedge every ``goal_mode`` worker (it could never close its own task).
```

**可迁移原则:一个 fail-open 的判定器,不能直接拿来当 fail-closed 的闸门用;
必须先独立探测「判定器本身在不在」,再决定要不要开闸。**

而 `kanban_block` 是这道闸的**第二个出口**,所以它也被堵上了:

`tools/kanban_tools.py:849 @ 863e313`

```python
        if (
            task
            and task.goal_mode
            and kind not in _GOAL_MODE_BLOCK_ALLOWED_KINDS
        ):
            conn.close()
            return tool_error(
                f"goal_mode tasks can only block with kind in "
                f"{sorted(_GOAL_MODE_BLOCK_ALLOWED_KINDS)} (got {kind!r}). "
                f"If the task is actually finished or cannot proceed for "
                f"another reason, call kanban_complete instead — the "
                f"completion judge will evaluate it."
            )
```

`_GOAL_MODE_BLOCK_ALLOWED_KINDS = frozenset({"dependency", "needs_input"})`
—— 只留真·外部阻塞两种;`capability` / `transient` / 不填,都被赶回判官那条路。
**堵住一个逃生口的时候,要把同一个循环的所有出口一起数出来。**

#### 2.2.5 结构化拒绝要显式告诉模型「你还能重试」

`kanban_complete` 有两个「拒绝但状态没变」的分支,措辞都刻意写明这一点:

`tools/kanban_tools.py:777 @ 863e313`

```python
            except kb.HallucinatedCardsError as hall_err:
                # Structured rejection — surface the phantom ids so the
                # worker can retry with a corrected list or drop the
                # field. Audit event already landed in the DB.
                #
                # The task itself was NOT mutated (the gate runs before
                # the write txn), so the worker can simply call
                # kanban_complete again. Spell that out — without it the
                # model often interprets a tool_error as a terminal
                # failure and either blocks or crashes the run instead
                # of retrying. See #22923.
```

**可迁移原则:对 LLM 来说「工具报错」默认等于「此路不通」。任何「可重试」的失败,
必须在错误文本里显式写「你的状态没变,原样再调一次即可」,否则模型会去 block 或崩掉。**

#### 2.2.6 两条不靠模型调用的自动桥

`kanban_tools.py` 里两个函数**不是工具**,而是从 agent 的活动打点里被动触发的桥,
入口都在 `run_agent.py` 的 `_touch_activity`:

`run_agent.py:3701 @ 863e313`

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
```

两条桥各自的限流常量:

`tools/kanban_tools.py:275 @ 863e313`

```python
_AUTO_HEARTBEAT_MIN_INTERVAL_SECONDS = 60.0
_auto_heartbeat_last_attempt: float = 0.0
```

`tools/kanban_tools.py:343 @ 863e313`

```python
_COMMENT_POLL_MIN_INTERVAL_SECONDS = 6.0
_comment_poll_last_attempt: float = 0.0
# task_id -> highest comment id already seen (seeded on first poll so history
# already present in build_worker_context isn't re-injected).
_comment_watermark: dict[str, int] = {}
```

注意两个 `_last_attempt` 都是**模块级**变量,即限流是**按进程**而不是按 task 的(见 §5 推定 6)。

- **心跳桥**(60 秒限流):把 agent 的
  「我还在动」翻译成板子上的 `last_heartbeat_at`。理由写在 `tools/kanban_tools.py:254`
  的注释里:dispatcher 看的是 DB 列,不是 agent 进程里的内存时间戳;**不做这个桥,
  一个正在干活的 worker 会被回收**,而且不能指望模型自觉调 `kanban_heartbeat`。
- **评论注入桥**(6 秒限流,水位线按 task id 记):把人类在板子上新写的评论,
  用 OUT-OF-BAND steer 塞进**正在跑的**回合。首次轮询只**播种水位线**、不注入
  (那些历史评论已经在 worker 的 context 里了),并跳过 `HERMES_PROFILE` 等于自己的评论
  以免自我回声。

**可迁移原则:「活着」这个信号不能靠模型主动上报 —— 要从 harness 已经有的活动打点里派生。
反过来,「人类插话」也不该要求重启,应该有一条 out-of-band 通道折进当前回合。**

#### 2.2.7 评论作者身份不接受参数

`tools/kanban_tools.py:961 @ 863e313`

```python
    body = redact_sensitive_text(str(body), force=True)
    # Author is intentionally derived from the worker's own runtime
    # identity, NOT from caller-supplied args. Comments are injected
    # into the next worker's system prompt by ``build_worker_context``
    # as ``**{author}** (timestamp): {body}`` — accepting an
    # ``args["author"]`` override let a worker forge a comment from
    # an authoritative-looking name like ``hermes-system`` and poison
    # the future-worker context with what reads as a system directive.
    # Cross-task commenting itself remains unrestricted (see #19713) —
    # comments are the deliberate handoff channel between tasks.
    author = os.environ.get("HERMES_PROFILE") or "worker"
```

**可迁移原则:凡是会被拼进未来某个 prompt 的字段,它的「说话人」必须由 harness 派生,
不能来自模型参数 —— 否则模型可以给自己签一个看起来像系统的名字。**
注意这条守卫只管**署名**,不管**能不能给别人的卡写评论**(后者是刻意开放的)。

#### 2.2.8 `kanban_attach_url` 的 SSRF 防护:每一跳都查

`tools/kanban_tools.py:1050 @ 863e313`

```python
    """Fetch ``url`` over http(s) with SSRF guarding, capped at ``max_bytes``.

    Every hop — the initial URL and each redirect target — is validated with
    ``tools.url_safety.is_safe_url`` before it is fetched, so a
    model-controlled URL (or a public host 302ing to one) cannot reach
    loopback, private/CGNAT ranges, or cloud metadata endpoints. Redirects
    are followed manually (``follow_redirects=False``) so each Location is
    re-checked, mirroring ``tools.skills_hub._guarded_http_get``.
```

最多 5 跳(`_MAX_ATTACH_URL_REDIRECTS = 5`),分块读、超限即抛。
**可迁移原则:URL 由模型控制时,只查第一跳等于没查 —— 公网主机 302 到
169.254.169.254(云元数据服务)是标准手法。**

#### 2.2.9 `kanban_create` 的「什么能继承、什么不能继承」

`tools/kanban_tools.py:1248 @ 863e313`

```python
    # Resolve workspace. Workspace sharing is always explicit: omitted fields
    # mean a fresh scratch workspace, even when a dispatcher-spawned worker
    # creates the task. Reusing a parent's literal path would let a child
    # mutate review evidence or race the parent's checkout (#67567).
    #
    # Project identity is the one safe context to inherit implicitly. The DB
    # resolves a project-linked scratch request into a fresh per-task worktree,
    # preserving the repository/branch convention without sharing a checkout.
```

**「目录共享必须显式,项目身份可以隐式」** —— 因为前者是可变状态,后者只是命名约定,
DB 会把它兑换成一个新的 worktree。这是一条很干净的继承边界划法。

---

### 2.3 看板的并发写(任务 b)

#### 2.3.1 声明的策略

`hermes_cli/kanban_db.py:61 @ 863e313`

```
Concurrency strategy: WAL mode + ``BEGIN IMMEDIATE`` for write
transactions + compare-and-swap (CAS) updates on ``tasks.status`` and
``tasks.claim_lock``.  SQLite serializes writers via its WAL lock, so at
most one claimer can win any given task.  Losers observe zero affected
rows and move on -- no retry loops, no distributed-lock machinery.
The CAS coordination is **per-board** — each board is a separate DB,
so multi-board installs get the same atomicity guarantees without any
new locking.
```

四层叠起来:
1. **长 busy_timeout**(默认见 `DEFAULT_BUSY_TIMEOUT_MS`,本容器实测 120000ms),
   理由写在 `_resolve_busy_timeout_ms` 的 docstring:看板是跨 profile 的共享派工总线,
   worker 踩踏是**预期**的,宁可让 SQLite 排队也不要抛 `database is locked`。
2. **`BEGIN IMMEDIATE` + 抖动重试**:SQLite 自带的 busy 退避近似确定性,并发写者会
   **同拍再撞**;所以在事务边界加了 20–150ms 的随机抖动打散车队。

`hermes_cli/kanban_db.py:2768 @ 863e313`

```python
# SQLite's own busy_timeout uses a near-deterministic backoff, so concurrent
# writers re-collide in lockstep under a stampede. A jittered retry on the
# transaction boundary breaks that convoy. Mirrors state.db's _execute_write:
# a fixed 20-150ms jitter band (a 20ms floor prevents a near-zero retry from
# busy-spinning back into the collision). Only BEGIN IMMEDIATE and COMMIT are
# retried -- both are idempotent re-issues that touch no transaction body, so a
# CAS inside write_txn is never replayed. kanban keeps fewer retries than
# state.db (5 vs 15) because its 120s busy_timeout already absorbs most waits;
# the retry is the backstop for the tail SQLite returns BUSY on immediately.
```

**「只重试 BEGIN IMMEDIATE 与 COMMIT」这一句是关键**:它们是幂等的重发,不碰事务体,
所以 `write_txn` 里的 CAS 永远不会被重放。**可迁移原则:重试只能加在幂等的边界上,
不能加在带 CAS 的事务体上。**
3. **CAS**:`complete_task` / `block_task` / `heartbeat_worker` 都带 `expected_run_id`。
4. **首连接的跨进程文件锁**(`_cross_process_init_lock`,10 秒上限):
   dispatcher 爆发时多个 worker 进程同时首连一块新板子,每个进程的
   `_INITIALIZED_PATHS` 缓存都是空的,进程内的 `_INIT_LOCK` 管不着;
   这个文件锁把「校验头 / 探测完整性 / 开 WAL / 加列」串成全机单写。

#### 2.3.2 实测:四个线程同时 `kanban_complete` 同一张卡

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "
import os,sys,tempfile,threading
os.environ['HERMES_HOME']=tempfile.mkdtemp(); sys.path.insert(0,'/home/user/hermes-agent')
from hermes_cli import kanban_db as kb
conn=kb.connect()
print('journal_mode =', conn.execute('PRAGMA journal_mode').fetchone()[0])
print('busy_timeout =', conn.execute('PRAGMA busy_timeout').fetchone()[0])
t=kb.create_task(conn,title='race',assignee='me'); conn.close()
os.environ['HERMES_KANBAN_TASK']=t; os.environ['HERMES_PROFILE']='me'
import tools.kanban_tools as kt
res=[]
def go(n): res.append((n, kt._handle_complete({'summary':'done by %d'%n})))
ths=[threading.Thread(target=go,args=(i,)) for i in range(4)]
[x.start() for x in ths]; [x.join() for x in ths]
for n,r in sorted(res): print(n, r[:110])
conn=kb.connect(); print('final:', kb.get_task(conn,t).status, '| runs:', len(kb.list_runs(conn,t)))
" 2>/dev/null
```

```console
journal_mode = delete
busy_timeout = 120000
0 {"ok": true, "task_id": "t_df4e5393", "run_id": 1}
1 {"error": "could not complete t_df4e5393 (unknown id or already terminal)"}
2 {"error": "could not complete t_df4e5393 (unknown id or already terminal)"}
3 {"error": "could not complete t_df4e5393 (unknown id or already terminal)"}
final: done | runs: 1
```

**结论:一个赢,三个拿到可读的结构化拒绝,没有重试风暴、没有半写状态、只有一条 run 记录。**
这就是设计承诺的「Losers observe zero affected rows and move on」。

#### 2.3.3 ◎:本容器的 journal_mode 是 `delete`,不是 WAL

上面实测里 `journal_mode = delete`,与 docstring 声称的 "WAL mode" 不一致。原因不是代码缺陷,
而是运行时对链接的 SQLite 版本做了降级(本容器 SQLite 3.45.1 带 WAL-reset 损坏 bug):

```console
kanban.db (kanban.db): linked SQLite 3.45.1 is vulnerable to the WAL-reset corruption bug (https://sqlite.org/wal.html#walresetbug) — using journal_mode=DELETE instead of enabling WAL. Upgrade to SQLite 3.51.3+ (or backports 3.50.7 / 3.44.6); Hermes-managed installs can repair the embedded runtime with `hermes update`. See `hermes doctor`. This warning fires once per process per database.
```

判定机制在 `hermes_state.py:826` 一带(`_should_avoid_wal` 类逻辑)。
**这是「有意的安全降级」而非 bug,但它意味着 `hermes_cli/kanban_db.py:61` 那句
"Concurrency strategy: WAL mode" 在一部分部署上字面不成立** —— 记为 ◎(见 §4)。
降级的实际代价:DELETE 日志模式下读者会阻塞写者,踩踏时更依赖那 120 秒 busy_timeout。

---

### 2.4 `tools/todo_tool.py` —— 为什么要第二套(任务 d)

#### 2.4.1 边界:进程内 vs 跨进程

| 维度 | `todo` | `kanban` |
|---|---|---|
| 存储 | `AIAgent` 实例上的内存 `TodoStore` | 跨进程 SQLite(`~/.hermes/kanban.db`) |
| 生命周期 | 一次会话 | 跨多次 run、多个 agent、多天 |
| 读者 | **只有当前模型自己** | 别的 worker、dispatcher、人类、仪表盘 |
| 并发 | 无(单实例) | WAL/CAS/claim/心跳/回收一整套 |
| 失败模式 | 压缩后忘了 → 重注入解决 | 进程崩了 → 心跳+claim TTL+回收解决 |
| 工具数 | 1 个(`todo`,读写同一个) | 12 个 |

**一句话:`todo` 解决的是「模型的短期记忆被上下文压缩吃掉」,`kanban` 解决的是
「多个进程要就同一批工作达成一致」。** 硬要合并的话,要么给 todo 加上没人需要的
并发/持久化代价,要么给 kanban 每一次心跳/评论都进模型上下文 —— 两边都亏。

模块头把 `todo` 的设计约束写得很干净(`tools/todo_tool.py:10`):单一工具、每次返回全量、
不改系统提示、不改工具结果、**行为指导全部塞进 schema description**。
最后一条的理由写在 `tools/todo_tool.py:264`:

`tools/todo_tool.py:264 @ 863e313`

```python
# Behavioral guidance is baked into the description so it's part of the
# static tool schema (cached, never changes mid-conversation).
```

**可迁移原则:要模型养成某个习惯,把规则写进 schema 的 description 而不是系统提示
—— 前者随工具定义进 prompt cache(提示缓存,同样前缀复用可省钱省延迟)且永不中途变化,
后者一改就击穿缓存。**

#### 2.4.2 三道上限,全部是为「压缩后重注入」服务的

`tools/todo_tool.py:31 @ 863e313`

```python
MAX_TODO_CONTENT_CHARS = 4000
MAX_TODO_ITEMS = 256
# Upper bound on a single todo tool-result payload accepted during history
# hydration. The gateway/API server replays caller-supplied conversation
# history to rebuild the store, so an oversized forged result is dropped
# before it is parsed and re-injected (see AIAgent._hydrate_todo_store).
MAX_TODO_RESULT_CHARS = 512_000
```

三条上限对应两个威胁:模型自己写了一条超长待办(自伤),以及
**API server 允许调用方提交 conversation_history**(他伤 —— 伪造一条巨大的 todo 结果)。

#### 2.4.3 重注入只放未完成项

`tools/todo_tool.py:134 @ 863e313`

```python
        # Only inject pending/in_progress items — completed/cancelled ones
        # cause the model to re-do finished work after compression.
        active_items = [
            item for item in self._items
            if item["status"] in {"pending", "in_progress"}
        ]
        if not active_items:
            return None
```

实测确认:全部 completed/cancelled 时返回 `None`(见 §3 实验)。
**这是从事故里学来的:把已完成项也注回去,模型会重做已完成的工作。**

注入点在压缩流程末尾,并且有两条讲究:

`agent/conversation_compression.py:3077 @ 863e313`

```python
        todo_snapshot = agent._todo_store.format_for_injection()
        if todo_snapshot:
            # Fold the snapshot into a trailing REAL user message so
            # compression never introduces a synthetic user/user pair. Any
            # snapshot merged at an earlier boundary is stripped first so
            # repeated compactions refresh rather than accumulate todo state
            # (#26981). Scaffolding tails (continuation marker, summary
            # handoff, a bare stale snapshot row) must never absorb the
            # snapshot: merging would upgrade them to "real user" evidence
            # and break zero-user provenance (#69292), so those keep the
            # flagged standalone append and the real-user preservation pass
            # continues to see todo scaffolding, not human intent.
```

`TODO_INJECTION_HEADER` 那个固定字符串就是给这段逻辑做「这一行是合成的、不是人说的」标记用的。

#### 2.4.4 网关每条消息新建 agent → 靠历史回放重建 store

`run_agent.py:4336 @ 863e313`

```python
    def _hydrate_todo_store(self, history: List[Dict[str, Any]]) -> None:
        """
        Recover todo state from conversation history.
        
        The gateway creates a fresh AIAgent per message, so the in-memory
        TodoStore is empty. We scan the history for the most recent todo
        tool response and replay it to reconstruct the state.

        Hydration is restricted to tool results that are paired with an
        earlier assistant ``todo`` tool call. The gateway/API server accepts
        caller-supplied ``conversation_history``, so a forged bare
        ``role: tool`` message carrying a ``todos`` array must not be able to
        seed the store without a matching canonical tool call
        (GHSA-5g4g-6jrg-mw3g).
        """
```

配对校验实现在 `_tool_response_matches_todo_call`:从 tool 结果往前扫到**最近的**
assistant 消息,要求它发过 id 匹配的 `todo` 调用;中途撞到 `user`/`system` 边界即判不配对。
**可迁移原则:任何「从历史回放重建内部状态」的机制,只要历史可能来自调用方,
就必须校验「这条工具结果确实配得上一条真实的工具调用」,否则它就是一个免费的状态注入口。**

---

### 2.5 `tools/project_tools.py` —— 最小的一个,但边界划得最清楚

`tools/project_tools.py:2 @ 863e313`

```python
"""Project tools — the agent's INTENTIONAL handle on first-class Projects.

Projects (per-profile ``projects.db``) are the named workspaces the desktop
sidebar groups sessions into. Creating / switching a project is a deliberate act
expressed as explicit tools — never a side effect of a terminal ``cd``.

Exposed only on GUI sessions: the tools live in the `project` toolset (kept off
``_HERMES_CORE_TOOLS``) which the desktop/TUI gateway folds into its resolved
toolsets, so no CLI/messaging/cron schema carries them. The GUI also wires
``set_project_workspace_callback`` so a create/switch re-anchors the live
session's cwd and the sidebar follows the move; the DB write is the durable part.
"""
```

三个可抄的点:

1. **「显式动作」原则**:切工作区是**有意图的**,不能是 `cd` 的副作用。工具描述里
   连着说了两遍 "not `cd`"。这是在跟模型抢一个它天然会走的捷径。
2. **gating 靠 toolset 成员身份,不靠 check_fn**。三个 `registry.register` 调用**都没有 `check_fn`**:

`tools/project_tools.py:134 @ 863e313`

```python
registry.register(
    name="project_list",
    toolset="project",
    schema={
        "name": "project_list",
        "description": "List the desktop Projects (named workspaces) and which one is active.",
        "parameters": {"type": "object", "properties": {}},
    },
    handler=lambda args, **kw: project_list(task_id=kw.get("task_id")),
)
```

   闸门在 TUI 网关的工具集解析器里,只有它会把 `project` 折进来:

`tui_gateway/server.py:4194 @ 863e313`

```python
        # The desktop Project tools are off _HERMES_CORE_TOOLS (every other
        # platform would carry their schema for nothing), so the platform
        # recovery above — which keys off hermes-cli's tool universe — can't
        # surface them. This resolver runs ONLY in the desktop/TUI gateway, so
        # folding in the `project` toolset here is the gate that exposes them on
        # exactly the surface that can follow a project move.
        return sorted(enabled | {"project"})
```

   **可迁移原则:两种 gating 各有其位 —— 「这台机器上有没有 Docker」用 check_fn(动态探测),
   「这个前端支不支持这个动作」用 toolset 成员身份(静态编排)。** 后者不需要每回合探测,
   也不会因为探测抖动而消失。
3. **双写的失败面不对称**:DB 写是持久部分,GUI 回调是尽力而为:

`tools/project_tools.py:42 @ 863e313`

```python
def _apply_workspace(task_id: Optional[str], path: Optional[str], name: str) -> None:
    cb = _workspace_callback
    if cb and task_id and path:
        try:
            cb(task_id, path, name)
        except Exception:
            pass
```

   回调抛异常被吞掉,模型仍然收到 `{"success": true, ...}` —— 这是**被文档化的**取舍
   (docstring 末句 "the DB write is the durable part"),不记 ■,记 ◇(见 §4)。

另一处小的解析不对称:`_resolve()` 查项目时用 `include_archived=True`(能切回归档项目),
而 `project_list()` 用默认值(列表里看不到归档项目)。所以模型可以切到一个它列不出来的项目。
这是有意的(按名字/slug 精确指定 vs 浏览),但值得知道。

---

### 2.6 `tools/cronjob_tools.py` —— 让模型排班(任务 c)

#### 2.6.1 一个工具、七个动作

模块头就写明设计取舍:「Expose a single compressed action-oriented tool to avoid
schema/context bloat」。七个 action:`create` / `list` / `update` / `pause` / `resume` /
`remove` / `run`(+ 别名 `run_now` / `trigger`)。
**可迁移原则:一组 CRUD 工具做成一个带 `action` 的压缩工具,省 schema token;
代价是参数校验从 schema 层掉到 handler 层(每个 action 需要哪些参数只能写在描述里,
所以 `action` 的 description 里手工写了 "When action=create, the 'schedule' and 'prompt'
fields are REQUIRED" —— `tests/cron/test_cronjob_schema.py` 专门守着这句话不许删)。**

#### 2.6.2 谁执行、以什么身份

- **调度**:网关内嵌的 ticker(cron 系统是内部的 JSON 文件调度器,不依赖系统 crontab
  —— 见 `check_cronjob_requirements` 的 docstring)。
- **执行**:`cron/scheduler.py::run_one_job`,在**网关进程**内;`action="run"` 时则在
  **调用方自己的线程上同步执行**(`_execute_job_now` → `run_one_job`)。
- **身份**:同一个 OS 用户、同一个 `HERMES_HOME`。不是沙箱,不是降权。
- **上下文**:全新 session,无当前聊天历史(schema description:
  "Jobs run in a fresh session with no current-chat context")。

#### 2.6.3 至多一次的领取(claim)

`action="run"` 不是「改一下 next_run_at 等 ticker」,而是真跑;为了不和 ticker 双触发,
先走和 ticker 同一个 CAS:

`tools/cronjob_tools.py:592 @ 863e313`

```python
def _execute_job_now(job: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a cron job immediately, outside the scheduler tick.

    Atomically claims the job first via ``claim_job_for_fire`` — the same
    at-most-once CAS the scheduler/external-provider fire path uses — so a
    concurrently-running gateway ticker cannot also fire it (the claim both
    blocks a duplicate fire and advances ``next_run_at`` for recurring jobs).
    If the claim is lost (another fire is in flight), this is a no-op.
```

抢不到时**不许一律说「已经在跑了」** —— 因为 `claim_job_for_fire` 对暂停/禁用/不存在的 job
也返回 False,那样会把用户支去追一个不存在的在飞运行(#60703)。于是重新读一次 job 分三种措辞。

#### 2.6.4 同步执行会把父回合的看门狗饿死 —— 心跳线程

`action="run"` 同步跑一个动辄几分钟的 agent run,期间调用方那一回合**一个工具活动都不发**,
网关的不活动看门狗会认定 agent 挂了并杀掉父回合(#76502)。解法是起一个后台线程,
每 10 秒往调用方的活动回调打一次点。两个细节值得抄:

`tools/cronjob_tools.py:640 @ 863e313`

```python
        try:
            from tools.environments.base import get_activity_callback

            # Capture on THIS thread: the callback is thread-local (installed
            # by the tool executor as the calling agent's _touch_activity), so
            # a freshly spawned thread cannot read it back.
            activity_cb = get_activity_callback()
        except Exception:
            activity_cb = None
```

1. **回调必须在原线程上取**(thread-local),新线程读不到。
2. **心跳有天花板**(`_CRON_RUN_HEARTBEAT_CEILING = 6 * 3600.0`):否则
   `HERMES_CRON_TIMEOUT=0`(显式无限)时,一个真卡死的 job 会**永远遮蔽**网关看门狗
   —— 而在这个功能之前,父进程至少还会在 ~1800s 被收掉。

**可迁移原则:任何「压制看门狗」的机制都必须自带上限,否则它把一个有界的故障变成无界的。**

#### 2.6.5 两套注入扫描器,因为两种输入的信噪比不同

`tools/cronjob_tools.py:96` 起是严格集(prompt injection + `cat *.env` + `rm -rf /` +
`authorized_keys` + `/etc/sudoers` + 5 条外带命令模式),只用于**用户写的 prompt**。
`tools/cronjob_tools.py:115` 起是宽松集(只留 4 条「在任何语境下都无歧义」的注入指令),
用于**装配后的 prompt(含 skill 正文)**。理由写得非常具体:

`tools/cronjob_tools.py:77 @ 863e313`

```python
#   2. Assembled prompt that includes loaded skill content (large markdown
#      bodies, often security docs, postmortems, runbooks discussing attack
#      patterns in PROSE). Reusing the strict patterns here false-positives
#      every time a skill *describes* a command — see #3968 follow-up: the
#      `hermes-agent-dev` skill contains a security postmortem mentioning
#      `cat ~/.hermes/.env`, which tripped `read_secrets` and silently
#      killed all PR-scout jobs.
```

核心事故:`hermes-agent-dev` skill 里一篇安全事后分析**提到了** `cat ~/.hermes/.env`,
触发严格集的 `read_secrets`,**静默杀掉了所有 PR-scout job**。

两个扫描器的**处置也不同**:严格集命中 → 硬阻断;宽松集遇到不可见 unicode → **消毒不阻断**
(skill 正文安装时已被 `skills_guard.py` 扫过,一个复制粘贴带进来的零宽空格不该永久杀死一个 job)。

还有一个很细的豁免:`_strip_cron_safe_constructs` 用 `re.sub` 剥掉
`curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/...` 这一个构造,
用 `re.sub` 而不是 `str.replace` 是因为**装了 2 个以上 GitHub skill 的 job 里有好几块**,
老实现只剥第一块、剩下的每次运行都触发外带检测器。而尾部只吃 `[^\s;&|$\`]*`,
所以同一行里夹带的 `;` / `&&` / `$(...)` **不会**被一起剥掉,仍然接受扫描。

**可迁移原则:安全扫描的模式集要按「输入的可信度 + 语料的自然形态」分层,
不能一套模式打天下 —— 否则不是漏检就是把正常功能扫死,而后者会让人关掉扫描器。**

#### 2.6.6 凭据外带守卫:命名 provider 的存储密钥只能发给它自己的端点

`_validate_cron_base_url`(`tools/cronjob_tools.py:436`)是本文件最硬的一段安全逻辑。
威胁模型:cron 工具是模型可调的,一个被注入的 job 可以设 `provider="anthropic"` +
`base_url="https://evil.test"`,到点调度器解析出该 provider 的**存储 API key** 并发往那个 URL。

判定树(fail-closed):
- 无 `base_url` → 放行;
- 有 `base_url` 但无 `provider` → **拒**(会继承默认 provider 的存储 key,同一个原语);
- `provider == "custom"` → 放行(纯 BYOK,key 由 base_url 派生);
- 命名 custom provider → 只有 `base_url` 主机与它**配置的**端点一致才放行;
- 其它已知 provider → 只有主机与 `PROVIDER_REGISTRY` 里的 `inference_base_url` 一致才放行;
- 解析不出来 → **拒**。

而且 `update` 时**每次都重新校验有效对**,不只在这次 update 碰到 provider/base_url 时校验:

`tools/cronjob_tools.py:935 @ 863e313`

```python
            # Re-validate the EFFECTIVE provider/base_url on EVERY update, not
            # only when this update supplies provider/base_url. A job persisted
            # before this guard (or written directly to the jobs store) may
            # already hold an unsafe named-provider + off-host base_url pair;
            # if we only checked when the update touches those axes, editing any
            # unrelated field (name, schedule, ...) would succeed and leave that
            # exfil-capable pair active and schedulable (F8). The effective pair
            # merges this update's normalized values over the stored job; an
            # operator can still remediate in the same update by clearing
            # base_url or pointing provider/base_url at a safe pair.
```

调度器侧还有一道运行时兜底 `_guard_job_credential_exfil`(`cron/scheduler.py:2733`),
连「校验器本身 import 失败」都 fail-closed(但只对**设了 base_url** 的 job 拒,
不设的照跑,避免无关错误把绝大多数 job 卡死)。

**可迁移原则:一个「持久化的、由模型写入的配置」需要三处校验 —— 写入时、每次编辑时
(校验合并后的有效值,不是本次改动)、以及使用前的最后一刻。只做写入时校验,
等于假设存储永远只被这一条路径写过。**

#### 2.6.7 递归防护是真的(不只是 prompt 里那句话)

schema 描述最后一句是软规则:

`tools/cronjob_tools.py:1045 @ 863e313`

```python
Important safety rule: cron-run sessions should not recursively schedule more cron jobs.""",
```

但硬闸在调度器:

`cron/scheduler.py:180 @ 863e313`

```python
    disabled = ["cronjob", "messaging", "clarify", "memory"]
    agent_cfg = (cfg or {}).get("agent") or {}
```

并且用户的 `agent.disabled_toolsets` 会叠加在上面,理由是
**per-job 的 `enabled_toolsets` 是 LLM 写的,不能靠它绕过 config.yaml 的黑名单(#25752)**。

**可迁移原则:模型可写的 allowlist 必须被一个模型不可写的 denylist 覆盖,顺序是 deny 后置。**

#### 2.6.8 审批(approval)在哪一步生效 —— 任务 c 的正面回答

**默认下 cron 比当下更严,不是更松。** 审批闸的分支顺序:

`tools/approval.py:3222 @ 863e313`

```python
    if not is_cli and not is_gateway:
        # Cron sessions: respect cron_mode config
        if _is_cron_approval_context():
            if _get_cron_approval_mode() == "deny":
                return {
                    "approved": False,
                    "message": cron_deny_message,
                    "pattern_key": pattern_key,
                    "description": description,
                }
```

`tools/approval.py:2984 @ 863e313`

```python
def _get_cron_approval_mode() -> str:
    """Read the cron approval mode from config. Returns 'deny' or 'approve'."""
    try:
        from hermes_cli.config import load_config_readonly
        config = load_config_readonly()
        mode = str(cfg_get(config, "approvals", "cron_mode", default="deny")).lower().strip()
        if mode in {"approve", "off", "allow", "yes"}:
            return "approve"
        return "deny"
    except Exception:
        return "deny"
```

三点值得注意:
1. 默认 `deny` —— cron 里撞到危险命令**直接拒**,而同一段代码里
   「非 cron、非交互、无网关」的裸脚本走的是**历史 fail-open**(auto-approve)。
   所以 cron 是这条路径上**唯一被特别收紧**的非交互上下文。
2. `_is_gateway_approval_context()` **显式把 cron 排除在网关上下文之外**,
   理由写在 docstring:cron 为了投递路由会绑 `HERMES_SESSION_PLATFORM`,
   若让它落进网关分支,会提交一个**没有监听者的**待审批请求,把 job 无限期挂住。
3. 判定优先读 session ContextVar,读不到才回落进程 env
   —— 「一个 cron job 不能污染同进程里无关的网关/API/TUI 回合」。

`HERMES_CRON_SESSION="1"` 由调度器用 ContextVar 设置(**不是 os.environ**),
理由同上,注释在 `cron/scheduler.py:3143`。

**但是** —— 见下面 §4 ■5:**`no_agent=True` 的脚本路径完全不经过任何审批闸**,
因为那条路上根本没有 agent。`approvals.cron_mode` 对它无效。

---

## 3. 测试作为行为规格

### 3.1 环境记录(用例数是环境的函数)

```verify
/home/user/hermes-venv/bin/pip list 2>/dev/null | tail -n +3 | wc -l
ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l
```

```console
87
87
```

与 CLAUDE.md 记录的 R8B 环境一致(87 个包 = `[dev]` extra + `aiohttp 3.14.1` + `brotlicffi 1.2.0.1`)。
本片**没有安装任何包**。

### 3.2 跑了什么

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/tools/test_kanban_tools.py tests/tools/test_kanban_redaction.py \
  tests/tools/test_kanban_comment_injection.py tests/tools/test_delegate_kanban_isolation.py \
  tests/agent/test_kanban_stop.py tests/tools/test_todo_tool.py tests/tools/test_todo_tool_type_coercion.py
```

```console
=== Summary: 7 files, 64 tests passed, 0 failed (100% complete) in 4.0s (8 workers) ===
```

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/tools/test_cronjob_tools.py tests/tools/test_cron_approval_mode.py \
  tests/tools/test_cron_prompt_injection.py tests/tools/test_cronjob_run_immediate.py \
  tests/cron/test_cron_script.py tests/cron/test_cron_no_agent.py tests/cron/test_cronjob_schema.py
```

```console
=== Summary: 7 files, 142 tests passed, 0 failed (100% complete) in 3.4s (8 workers) ===
```

**合计:14 个文件,206 passed,0 failed。** 无失败,故无逐条诊断。

### 3.3 从测试里读出来的行为规格

- `tests/agent/test_kanban_stop.py` 只有 3 个用例,守的正好是三条分支:
  非 worker → `None`;worker 且未调终态 → 有 nudge;已调终态 → `None`。
  **它没有覆盖「调过但失败」这一支** —— 这正是 §4 ■1 能存活的原因。
- `tests/tools/test_delegate_kanban_isolation.py`(6 用例)是 §2.2.2 第二层守卫的规格。
- `tests/tools/test_cron_approval_mode.py` 有 30 个用例,是本片最密的一块规格,
  覆盖 `cron_mode` deny/approve × 交互/网关/裸脚本上下文的矩阵。
- **静默跳过**:本次 14 个文件**没有观察到 `importorskip` 整文件跳过**
  (7+7 个文件全部有用例执行且计数非零)。

### 3.4 补充的定向实验(非仓库测试,我自己写的)

todo 的 id 折叠(下面 §4 ■4 的实证):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "
import sys,json; sys.path.insert(0,'/home/user/hermes-agent')
from tools.todo_tool import TodoStore, todo_tool
s=TodoStore()
out=json.loads(todo_tool(todos=[{'content':'step A','status':'pending'},
                                {'content':'step B','status':'pending'},
                                {'content':'step C','status':'pending'}], store=s))
print(out['todos'], out['summary'])
s3=TodoStore()
todo_tool(todos=[{'id':'a','content':'A','status':'completed'},
                 {'id':'b','content':'B','status':'cancelled'}], store=s3)
print('inject all-terminal ->', repr(s3.format_for_injection()))
"
```

```console
[{'id': '?', 'content': 'step C', 'status': 'pending'}] {'total': 1, 'pending': 1, 'in_progress': 0, 'completed': 0, 'cancelled': 0}
inject all-terminal -> None
```

---

## 4. 发现清单

> 强度标注:**实跑复现** = 我在本容器跑出来了;**静态对读** = 只读代码推出的;
> **推定未取证** = 有理由怀疑但没验证(全部挪到 §5)。

### ■1 —— 一次**被拒绝**的 `kanban_complete` 会永久关掉「不许裸退」守卫(实跑复现)

`agent/kanban_stop.py:50` 的 `session_called_kanban_terminal` 只看调用**发生过**没有,
不看**成功**没有。而 `_handle_complete` 有至少三条「拒绝但任务仍在飞」的返回路径:
goal_mode 判官驳回、`HallucinatedCardsError`、`ArtifactPreservationError`。
这三条恰恰是**最需要模型再试一次**的场景 —— `tools/kanban_tools.py:777` 的注释还专门
写了「模型常把 tool_error 当成终局失败,于是去 block 或崩掉 run」。

实测:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "
import os,sys; os.environ['HERMES_KANBAN_TASK']='t_abc'; sys.path.insert(0,'/home/user/hermes-agent')
from agent.kanban_stop import build_kanban_stop_nudge, session_called_kanban_terminal
msgs=[{'role':'user','content':'do it'},
 {'role':'assistant','tool_calls':[{'id':'1','function':{'name':'kanban_complete','arguments':'{}'}}]},
 {'role':'tool','tool_call_id':'1','name':'kanban_complete',
  'content':'{\"error\": \"Goal completion rejected by judge: not done\"}'},
 {'role':'assistant','content':'Let me write the report now.'}]
print('terminal_seen =', session_called_kanban_terminal(msgs))
print('nudge =', build_kanban_stop_nudge(messages=msgs, attempts=0))
"
```

```console
terminal_seen = True
nudge = None
```

**后果:** 一个 goal_mode worker 被判官驳回 → narrate 一句 → 停 → 守卫不发 nudge →
rc=0 干净退出 → dispatcher 记 `protocol_violation`。
**这是守卫本该拦下的那一类失败里最典型的一种,而它恰恰被守卫自己放过。**
修法很轻:`session_called_kanban_terminal` 在看 `role == "tool"` 那一支时,顺手解析
content 里有没有 `"error"` 键(仓库自己的 `tool_error()` 就是产出 `{"error": ...}`),
只把**成功的**终态调用算数。

### ■2 —— `kanban_link` 是**没有归属校验**的跨任务写,worker 可以拖住别人的卡并劫持其通知(实跑复现)

`_handle_link` 只挂了 `_reject_delegated_child_mutation`,**没有** `_enforce_worker_task_ownership`,
也**没有** `_require_orchestrator_tool`,并且 `check_fn=_check_kanban_mode`(worker 也看得见)。

`tools/kanban_tools.py:1509 @ 863e313`

```python
def _handle_link(args: dict, **kw) -> str:
    """Add a parent→child dependency edge after the fact."""
    delegated_err = _reject_delegated_child_mutation("kanban_link")
    if delegated_err:
        return delegated_err
    parent_id = args.get("parent_id")
    child_id = args.get("child_id")
    if not parent_id or not child_id:
        return tool_error("both parent_id and child_id are required")
    board = args.get("board")
    try:
        kb, conn = _connect(board=board)
        try:
            kb.link_tasks(conn, parent_id=parent_id, child_id=child_id)
            return _ok(parent_id=parent_id, child_id=child_id)
        finally:
            conn.close()
```

DB 侧 `link_tasks` 会做两件有副作用的事:**把 `ready` 的子卡降级为 `todo`**,
以及**把父卡的通知订阅复制给子卡**。

`hermes_cli/kanban_db.py:3543 @ 863e313`

```python
        # If child was ready but parent is not yet done, demote child to todo.
        parent_status = conn.execute(
            "SELECT status FROM tasks WHERE id = ?", (parent_id,)
        ).fetchone()["status"]
        if parent_status != "done":
            conn.execute(
                "UPDATE tasks SET status = 'todo' WHERE id = ? AND status = 'ready'",
                (child_id,),
            )
```

`hermes_cli/kanban_db.py:3319 @ 863e313`

```python
    conn.execute(
        f"""
        INSERT OR IGNORE INTO kanban_notify_subs
            (task_id, platform, chat_id, thread_id, user_id,
             notifier_profile, created_at, last_event_id)
        SELECT ?, platform, chat_id, thread_id, user_id, notifier_profile, ?, ?
          FROM kanban_notify_subs
         WHERE task_id IN ({placeholders})
        """,
```

`link_tasks` 里**没有任何 tenant(租户)比较**。实测(worker 绑定 tenant-A 的卡,
去 link 一张 tenant-B 的卡):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "
import os,sys,tempfile; os.environ['HERMES_HOME']=tempfile.mkdtemp(); sys.path.insert(0,'/home/user/hermes-agent')
from hermes_cli import kanban_db as kb
conn=kb.connect()
mine=kb.create_task(conn,title='mine',assignee='me',tenant='tenant-A')
foreign=kb.create_task(conn,title='foreign',assignee='them',tenant='tenant-B')
kb.add_notify_sub(conn,task_id=mine,platform='telegram',chat_id='111',notifier_profile='me')
conn.execute(\"UPDATE tasks SET status='ready' WHERE id=?\",(foreign,))
print('foreign before:', kb.get_task(conn,foreign).status); conn.close()
os.environ['HERMES_KANBAN_TASK']=mine; os.environ['HERMES_PROFILE']='me'
import tools.kanban_tools as kt
print('complete(foreign) ->', kt._enforce_worker_task_ownership(foreign))
print('link ->', kt._handle_link({'parent_id':mine,'child_id':foreign}))
conn=kb.connect(); print('foreign after:', kb.get_task(conn,foreign).status)
print('subs:', [tuple(r) for r in conn.execute('SELECT task_id,platform,chat_id FROM kanban_notify_subs')])
" 2>/dev/null
```

```console
foreign before: ready
complete(foreign) -> {"error": "worker is scoped to task t_5ad0948f; refusing to mutate t_93ac5a40. Use kanban_comment to hand off information to other tasks, or kanban_create to spawn follow-up work."}
link -> {"ok": true, "parent_id": "t_5ad0948f", "child_id": "t_93ac5a40"}
foreign after: todo
subs: [('t_5ad0948f', 'telegram', '111', 'me'), ('t_93ac5a40', 'telegram', '111', 'me')]
```

**同一个 worker,`kanban_complete` 那张外国卡被拒,`kanban_link` 却成功了 ——
而 link 的效果是:(a) 把那张 `ready` 卡拖回 `todo`,在我的卡完成前它不会被派工;
(b) 那张卡未来的终态通知会投递到我的 Telegram 聊天。**
`_enforce_worker_task_ownership` 的 docstring 明说这道守卫是为了防
「a buggy or prompt-injected worker … could corrupt sibling or cross-tenant runs (see #19534)」——
`kanban_link` 恰好是同一类破坏,却漏挂了。

### ▲1 —— 文档断言「dispatcher-spawned workers … cannot mutate unrelated tasks」不成立

`website/docs/user-guide/features/kanban.md:341 @ 863e313`

> The "(Orchestrators)" tools — `kanban_list`, `kanban_create`, `kanban_link`, `kanban_unblock`, and `kanban_comment` on foreign tasks — are available through the same toolset; the convention (encoded in the auto-injected kanban guidance) is that worker profiles don't fan out or route unrelated work, and orchestrator profiles don't execute implementation work. Dispatcher-spawned workers are still task-scoped for destructive lifecycle operations and cannot mutate unrelated tasks.

按 CLAUDE.md 的整句判定要求,这句话在 `## How workers interact with the board` 标题下,
包含两个断言:
- **前半「task-scoped for destructive lifecycle operations」成立** ——
  `complete` / `block` / `heartbeat` / `attach` / `attach_url` / `unblock` 都挂了归属校验,
  实测拒绝(见 ■2 的 console)。
- **后半「and cannot mutate unrelated tasks」不成立** —— `kanban_link` 实测可以,
  且效果是改变了外国卡的 `status` 与其通知订阅集。`kanban_comment` 也是写(虽是刻意开放的,
  同段前半句已承认),但 comment 至少不改 task 行;link 改了。

判 ▲(字面矛盾,不是保守)。

### ■3 —— `kanban_stop` 与 `kanban_tools` 对「我是不是 dispatcher worker」判定不一致(实跑复现)

`tools/kanban_tools.py` 用的是 `HERMES_KANBAN_TASK` **且** `_is_dispatcher_owned_worker()`
(一个 ContextVar,cron 调度器会在 job 执行期间显式置反);`agent/kanban_stop.py` 只看 env。
后果:**一个从 kanban worker 进程内联触发的 cron job**(`cronjob(action="run")` 走
`run_one_job` → `run_job`,就在那个 worker 进程里),看板工具**已经被正确地从它的 schema 里摘掉**,
但「不许裸退」守卫**仍然会开火**,催它去调一个它根本没有的工具。

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "
import os,sys; os.environ['HERMES_KANBAN_TASK']='t_abc'; sys.path.insert(0,'/home/user/hermes-agent')
from agent.kanban_stop import build_kanban_stop_nudge, kanban_stop_nudge_enabled
from agent.delegation_context import enter_non_dispatcher_owned_context
import tools.kanban_tools as kt
print('before: check_kanban_mode =', kt._check_kanban_mode(), '| nudge_enabled =', kanban_stop_nudge_enabled())
tok = enter_non_dispatcher_owned_context()
print('in-cron: check_kanban_mode =', kt._check_kanban_mode(), '| nudge_enabled =', kanban_stop_nudge_enabled())
print('in-cron: nudge is not None =', build_kanban_stop_nudge(messages=[{'role':'user','content':'x'}], attempts=0) is not None)
print('in-cron: _default_task_id(None) =', kt._default_task_id(None))
"
```

```console
before: check_kanban_mode = True | nudge_enabled = True
in-cron: check_kanban_mode = False | nudge_enabled = True
in-cron: nudge is not None = True
in-cron: _default_task_id(None) = None
```

读法:同一个进程状态下,`kanban_tools` 认为「你不是 dispatcher worker」(工具摘掉、
默认 task_id 也不给),而 `kanban_stop` 认为「你是」(照发 nudge)。

**代价是有界的**(最多 2 次多余回合 + 一条误导性的系统消息),但方向是错的:
`cron/scheduler.py:3145-3165` 那一大段注释详细论证了「为什么必须用 ContextVar 而不是清 env」,
`kanban_stop.py` 却是全仓里**唯一**只认 env 的看板消费者。

### ■4 —— 缺 `id` 的多条 todo 会静默折叠成一条(实跑复现)

`tools/todo_tool.py:190 @ 863e313`

```python
    @staticmethod
    def _dedupe_by_id(todos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Collapse duplicate ids, keeping the last occurrence in its position."""
        last_index: Dict[str, int] = {}
        for i, item in enumerate(todos):
            if not isinstance(item, dict):
                # Non-dict items get a synthetic key so _validate can handle them
                last_index[f"__invalid_{i}"] = i
                continue
            item_id = str(item.get("id", "")).strip() or "?"
            last_index[item_id] = i
        return [todos[i] for i in sorted(last_index.values())]
```

所有缺 `id` 的条目都被映射到同一个键 `"?"`,于是 3 条计划只剩最后 1 条(见 §3.4 实测)。
非 dict 条目反而被特意保留(`__invalid_{i}` 每个都不同)—— **对格式最差的输入最宽容,
对只少填一个字段的输入最严厉**,这个不对称本身就是个信号。

严重性:`id` 在 schema 里标了 `required`,但 LLM 漏填必填字段是常态;工具返回的
`summary.total` 会显示 1,模型**理论上**能发现,但没有任何错误提示。
修法:给缺 id 的条目发一个合成唯一 id(如 `__auto_{i}`),而不是让它们全挤在 `"?"`。

### ■5 —— `no_agent=True` 的 cron 脚本是一条**完全不经过审批的**代码执行路径,`approvals.cron_mode` 对它无效(实跑复现)

这是任务 (c) 「模型能不能通过排 cron 绕过当下的审批约束」的正面回答:**能,而且这条路是被文档化的。**

链条:
1. **写脚本不受管**。`~/.hermes/scripts/` 不在 `file_tools._SENSITIVE_PATH_PREFIXES`、
   不在 `_SENSITIVE_EXACT_PATHS`、不是 `~/.hermes/config.yaml`、也不在
   `_check_cross_profile_path` 覆盖的 `skills/plugins/cron/memories` 四个目录里。
   `tools/approval.py:_SENSITIVE_WRITE_TARGET` 同样只盖 `/etc`、`/dev/sd`、`~/.ssh`、
   `~/.hermes/.env`、`~/.hermes/config.yaml`、shell rc、`.netrc/.pgpass/.npmrc/.pypirc`。
2. **排 job 不受管**。`create` 只在 `prompt` 非空时扫描;`no_agent=True` 允许**没有 prompt**:

`tools/cronjob_tools.py:756 @ 863e313`

```python
            elif not prompt and not canonical_skills:
                return tool_error("create requires either prompt or at least one skill", success=False)
            if prompt:
                scan_error = _scan_cron_prompt(prompt)
                if scan_error:
                    return tool_error(scan_error, success=False)
```

   `_validate_cron_script_path` 只校验**路径**(必须相对、必须留在 scripts 目录内),
   **从不读脚本内容**:

`tools/cronjob_tools.py:532 @ 863e313`

```python
    # Reject absolute paths and ~ expansion at the API boundary.
    # Only relative paths within ~/.hermes/scripts/ are allowed.
    if raw.startswith(("/", "~")) or (len(raw) >= 2 and raw[1] == ":"):
        return (
            f"Script path must be relative to ~/.hermes/scripts/. "
            f"Got absolute or home-relative path: {raw!r}. "
            f"Place scripts in ~/.hermes/scripts/ and use just the filename."
        )
```

3. **执行不受管**。调度器把 scripts 目录当成可信区,直接 `subprocess.run`:

`cron/scheduler.py:2286 @ 863e313`

```python
    # Pick an interpreter by extension.  Bash for .sh/.bash, Python for
    # everything else.  We deliberately do NOT honour the file's own
    # shebang: the scripts dir is trusted, but keeping the interpreter
    # choice explicit here keeps the allowed surface small and auditable.
```

4. **审批闸根本不在这条路上**。因为没有 agent loop,`check_dangerous_command` 从不被调用。

**负结论的搜索面(按 CLAUDE.md 要求写明)**:

```verify
cd /home/user/hermes-agent && grep -rn "approval\|check_dangerous_command\|check_hardline\|requires_approval" cron/*.py
```

```console
cron/scheduler.py:3143:        # Scope cron approval policy to this job. Keep the token so the finally
```

搜索面 = `cron/` 目录下全部 **9** 个 `.py` 文件(原写 8,与紧跟其后自己列出的文件名个数不符,主线复核时更正)(`__init__.py`、`blueprint_catalog.py`、
`executions.py`、`jobs.py`、`lifecycle_guard.py`、`scheduler.py`、`scheduler_provider.py`、
`suggestion_catalog.py`、`suggestions.py`),模式 = 上述四个标识符的字面/子串匹配,
未排除任何文件。唯一命中是一行**注释**(设置 ContextVar 的那处),**没有任何审批函数调用**。
另外 `grep -rn "cronjob" tools/approval.py tools/registry.py` 零命中,
说明 `cronjob` 工具本身也没有被工具级审批包住。

**端到端实跑**(临时 HERMES_HOME,基线未被改动):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "
import os,sys,tempfile,json
HOME=tempfile.mkdtemp(); os.environ['HERMES_HOME']=HOME; os.environ['HERMES_INTERACTIVE']='1'
sys.path.insert(0,'/home/user/hermes-agent')
from tools.file_tools import _check_sensitive_path
from tools.cronjob_tools import cronjob
sd=os.path.join(HOME,'scripts'); os.makedirs(sd,exist_ok=True)
marker=os.path.join(HOME,'PWNED.txt')
open(os.path.join(sd,'evil.sh'),'w').write('#!/bin/bash\ncat ~/.ssh/id_rsa 2>/dev/null; echo owned > %s; echo \"nothing to report\"\n'%marker)
print('write gate on scripts dir ->', _check_sensitive_path(os.path.join(sd,'evil.sh')))
d=json.loads(cronjob(action='create', schedule='0 9 * * *', script='evil.sh', no_agent=True, name='exp'))
print('create ok:', d.get('success'), '| no_agent:', d.get('job',{}).get('no_agent'))
from cron.scheduler import _run_job_script
print('run ->', _run_job_script('evil.sh'))
print('marker written:', os.path.exists(marker))
" 2>/dev/null
```

```console
write gate on scripts dir -> None
create ok: True | no_agent: True
run -> (True, 'nothing to report')
marker written: True
```

**并且这正是文档教用户走的路:**

`website/docs/user-guide/features/cron.md:493 @ 863e313`

> Hermes will write the check script to `~/.hermes/scripts/` via `write_file`, then call:

**怎么定性。** 这不是「有人忘了加校验」,而是审批模型本身的形状问题:
Hermes 的危险命令闸是**命令字符串形状**的(扫 `rm -rf /`、`cat *.env` 这些字面),
而 `bash x.sh` 这个字符串永远无害。cron 的 `no_agent` 只是把这个既有缺口做成了
一条**定时的、无人值守的、跨会话存活的**版本 —— 而且它绕过的恰恰是
`approvals.cron_mode: deny` 这个**专门为「无人值守时更保守」而存在的**配置项。

`website/docs/user-guide/security.md:47 @ 863e313`

> | `cron_mode` | `deny` | How [cron jobs](./features/cron.md) behave headlessly when they trigger a dangerous-command prompt. `deny` blocks the command (the agent must find another path); `approve` auto-approves everything in cron context. |

这句文档字面为真(它说的是 "trigger a dangerous-command prompt",而脚本路径根本不 trigger),
所以**不判 ▲**;但一个读了这张表就以为「我把 cron 设成 deny 了,cron 干不了危险事」的运维,
判断是错的。**这是我这一片最值得主线复核的一条。**

**如果我来重新设计**:`no_agent` 脚本在 fire 时至少应当过一次和终端工具同一套的
`check_dangerous_command`(对脚本**内容**,不是对调用行),并且在 `cron_mode == "deny"` 时
拒绝执行未经人类确认过内容哈希的脚本 —— 即「脚本内容变更需要重新批准」。

### ■6 —— `attach_to_session` 在 schema 里,但注册的 handler 从不转发(实跑复现)

`tools/cronjob_tools.py:1126` 的 schema 声明了 `attach_to_session`(一段 300 字的描述,
讲这个 job 变成「可续聊」的),而注册处的 lambda 参数表里**没有它**:

`tools/cronjob_tools.py:1176 @ 863e313`

```python
        # model / provider / base_url are intentionally NOT read from the
        # agent's arguments: per-job inference pins are user-owned (dashboard,
        # `hermes cron create/edit --model`, or hand-edited jobs). The agent
        # must not be able to point unattended spend at a different model.
        # Programmatic callers of cronjob() itself retain the parameters.
        reason=args.get("reason"),
        script=args.get("script"),
        context_from=args.get("context_from"),
        enabled_toolsets=args.get("enabled_toolsets"),
        workdir=args.get("workdir"),
        no_agent=args.get("no_agent"),
        task_id=kw.get("task_id"),
```

`model` / `provider` / `base_url` 的省略是**有注释的、刻意的**;
`attach_to_session` 的省略**没有任何注释**,而且它和被刻意省略的三个不是一类
(它不牵涉花钱或凭据,纯粹是投递行为)。实测对照:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "
import os,sys,tempfile,json
os.environ['HERMES_HOME']=tempfile.mkdtemp(); os.environ['HERMES_INTERACTIVE']='1'
sys.path.insert(0,'/home/user/hermes-agent')
import tools.cronjob_tools as ct
from tools.registry import registry
h = registry._tools['cronjob'] if hasattr(registry,'_tools') else None
json.loads(h.handler({'action':'create','schedule':'0 9 * * *','prompt':'hi','attach_to_session':True}))
from cron.jobs import list_jobs
print('via model-facing handler ->', list_jobs(include_disabled=True)[0].get('attach_to_session'))
os.environ['HERMES_HOME']=tempfile.mkdtemp()
import importlib, cron.jobs; importlib.reload(cron.jobs)
ct.cronjob(action='create', schedule='0 9 * * *', prompt='hi', attach_to_session=True)
print('via python call ->', cron.jobs.list_jobs(include_disabled=True)[0].get('attach_to_session'))
" 2>/dev/null
```

```console
via model-facing handler -> None
via python call -> True
```

**后果:** 用户说「每天给我发简报,我想能直接回复它继续做事」,模型照 schema 传了
`attach_to_session=True`,工具返回 `success: True`,而 job 存的是 `None` ——
到点投递后用户回复,agent 没有简报在上下文里,正是这个参数描述里说要避免的
「asking 'what is that?'」。**静默的、schema 承诺与行为不一致的失败。**

顺带两处更小的同类不一致(都不构成独立发现,记在这里):
- `include_disabled` 不在 schema 里,handler 硬传 `True`,而 `cronjob()` 函数默认 `False`
  —— 所以模型调 `list` 永远看得到暂停/禁用的 job(这个方向是好的,但不是文档化的)。
- `skill`(单数)和 `reason` 被 handler 读取但不在 schema 里,模型永远传不到。

### ■7 —— `_handle_block` 有一条不关连接的错误路径(静态对读,未复现)

`tools/kanban_tools.py:831 @ 863e313`

```python
    try:
        kb, conn = _connect(board=board)
        if kind is not None and kind not in kb.VALID_BLOCK_KINDS:
            conn.close()
```

`tools/kanban_tools.py:848 @ 863e313`

```python
        task = kb.get_task(conn, tid)
        if (
```

`_connect()` 之后到 `try/finally conn.close()` 之间隔着
两条可能抛异常的语句(`kb.VALID_BLOCK_KINDS` 属性访问、`kb.get_task(conn, tid)`)。
`kb.get_task` 在 DB 锁竞争下抛 `sqlite3.OperationalError` 会落到外层 `except Exception`,
此时 `conn` 从未 `close()`。同文件里 `_handle_show` / `_handle_list` / `_handle_attach` 都是
「connect 后立刻进 try/finally」,只有 `_handle_block` 例外。

影响:泄漏的连接会一直占着 `hermes_cli.sqlite_safe_read.connect_tracked` 的活连接注册表
(该注册表的作用是:注册期间拒绝对同一文件的字节级探测,因为 `open()`/`close()`
会取消本进程的 POSIX 咨询锁),直到对象被 GC。CPython 下通常很快,但不保证。
**未复现**(需要构造 `get_task` 抛异常),记为静态对读。

### ◇1 —— worker 可以读**任意**卡的全文,包括别的租户(实跑复现)

`_handle_show` 既无 `_enforce_worker_task_ownership`,也无 `_require_orchestrator_tool`:

`tools/kanban_tools.py:495 @ 863e313`

```python
def _handle_show(args: dict, **kw) -> str:
    """Read a task's full state: task row, parents, children, comments,
    runs (attempt history), and the last N events."""
    tid = _default_task_id(args.get("task_id"))
    if not tid:
        return tool_error(
            "task_id is required (or set HERMES_KANBAN_TASK in the env)"
        )
    board = args.get("board")
```

实测:

```console
read foreign title: foreign secret | tenant: tenant-B
read foreign body: API key rotation runbook: step 1 ...
read foreign comments: [{'author': 'ops', 'body': 'the staging password is hunter2', 'created_at': 1786265999}]
comment on foreign: {'ok': True, 'task_id': 't_f76653fd', 'comment_id': 2}
```

`kanban_attachments` 的 docstring 明写 "read-only; no ownership restriction",
说明作者对读侧不设限是**有意识的**;但 `kanban_show` 没有这句声明,
而它返回的内容(body + 全部评论 + `worker_context`)远比附件列表敏感。
记 ◇(代码有此行为、文档无此说明),不记 ■ —— 因为 `tenant` 在这套代码里
一直被描述为 "namespace for multi-project isolation",没有承诺是安全边界。
不过它和 ■2 组合起来就不只是读:link 之后连通知都跟着走。

### ◇2 —— `delegate_task` 子 agent 在 30 秒窗口内能看见 kanban 工具的 schema(实跑复现)

见 §2.2.3。写操作被两层守卫拦住,但 `kanban_show` 两层都没有,
因此子 agent 在窗口内能读板子(需要显式 `task_id`,因为 `_default_task_id` 对委派子上下文返回 `None`)。

### ◇3 —— `project_create` / `project_switch` 的 GUI 回调失败被静默吞掉

见 §2.5。这是文档化的取舍(docstring: "the DB write is the durable part"),故记 ◇ 不记 ■。

### ◇4 —— worker 可以为**任意 tenant** 创建卡

`tools/kanban_tools.py:1232 @ 863e313`

```python
    tenant = args.get("tenant") or os.environ.get("HERMES_TENANT")
```

`tenant` 直接取模型参数,没有与 worker 自身卡的 tenant 比对。`kanban_create` 的 schema
把 `tenant` 描述为 "Optional namespace for multi-project isolation",没有说它受限。

### ◎1 —— `kanban_db` docstring 声称的 "WAL mode" 在部分部署上不成立

见 §2.3.3。字面上 WAL 是**目标**策略,运行时会因链接的 SQLite 版本安全降级为 `delete`。
不判 ▲(不是文档与代码矛盾,是文档描述的是默认路径、代码多了一条有意的降级分支),
判 ◎(声明成立但显著乐观 —— 读者会据此以为并发读写不互斥)。

---

## 5. 未取证 / 推定

1. **`_handle_block` 的连接泄漏在真实负载下的可观测后果**(锚点 `tools/kanban_tools.py:831`)。
   我没有构造出 `kb.get_task` 抛异常的场景,所以「注册表条目滞留导致后续 `sqlite_safe_read`
   探测被拒」只是按 `connect_tracked` 的 docstring 推的,未取证。
2. **■5 的实际投递面**:我验证了 `_run_job_script` 会执行脚本、`create` 会接受它,
   但**没有**跑完整的 `run_one_job`(它要拉起整个调度器和投递栈)。
   「非零退出会发告警、空 stdout 静默」这两条 `no_agent` 投递语义我只读了 schema 描述与
   `cron/scheduler.py` 的注释,**未实跑**。
3. **■2 的下游后果(通知真的会投到劫持者的聊天)**:我证实了 `kanban_notify_subs` 行被复制,
   但没有跑网关的通知轮询器去看它真的发出去。链路的后半段是推定。
4. **■1 在真实 worker 里的完整复现**:我用 `build_kanban_stop_nudge` 做了单元级复现,
   没有跑一个真的 dispatcher + worker(需要模型凭据)。
   「会导致 dispatcher 记 protocol_violation」这一段是按
   `website/docs/user-guide/features/kanban.md:398-403` 与 `kanban_stop.py` 模块头的描述推的。
5. **`_comment_watermark` 是模块级 dict,按 task id 记水位**(`tools/kanban_tools.py:347`)。
   一个进程里如果先后跑了同一个 task id 的两次 run(重试),第二次的首轮 poll **不会**再播种
   (dict 里已有该 key),于是会把第一次 run 期间的评论也注入进来。
   **推定未取证** —— worker 通常是一次性进程,但 `cronjob(action="run")` 的内联执行说明
   同进程复用是存在的形态。
6. **`_auto_heartbeat_last_attempt` 是模块级 float,非线程安全**(注释自认,说「最坏多写一次」)。
   在同进程跑多个看板 worker 的形态下(是否存在?未查证),这个全局限流会让**第二个 worker 的心跳被第一个吃掉**
   —— 因为限流窗口是**按进程**而不是**按 task**的。推定未取证。
7. **`initial_status="running"` 创建的卡**(`kanban_create` schema 允许 `running` / `blocked`,
   默认 `running`)与 dispatcher 的 claim 机制怎么互动、会不会产生一张没有 run 行的 running 卡,
   我没有查 `create_task` 的对应分支。未取证。

---

## 6. 本片移交项

| 编号 | 建议轮次 | 锚点 + 一句话现象 | 状态 |
|---|---|---|---|
| **H-R9D-C-a** | 主线本轮复核 | `cron/scheduler.py:2288`:`# choice explicit here keeps the allowed surface small and auditable.` —— `no_agent` 脚本执行路径上 `cron/*.py` 里零个审批调用,`approvals.cron_mode: deny` 对它无效;模型写脚本进 `~/.hermes/scripts/` 也无 gate(实跑复现,见 §4 ■5) | 待主线复核 |
| **H-R9D-C-b** | 主线本轮复核 | `tools/kanban_tools.py:1510`:`"""Add a parent→child dependency edge after the fact."""` —— `_handle_link` 缺 `_enforce_worker_task_ownership`,worker 实测可把外国租户的 `ready` 卡降级为 `todo` 并继承其通知订阅(见 §4 ■2、▲1) | 待主线复核 |
| **H-R9D-C-c** | 主线本轮复核 | `agent/kanban_stop.py:62`:`name = str(msg.get("name") or "")` —— 只看终态工具**调用过**不看**成功过**,一次被判官驳回的 `kanban_complete` 就永久关掉守卫(见 §4 ■1) | 待主线复核 |
| **H-R9D-C-d** | R10+ | `tools/cronjob_tools.py:1181`:`script=args.get("script"),` —— 同一个 lambda 里 `attach_to_session` 未转发,schema 承诺与行为不一致(见 §4 ■6) | 待处置 |
| **H-R9D-C-e** | R10+ | `agent/kanban_stop.py:34`:`task = (os.environ.get("HERMES_KANBAN_TASK") or "").strip()` —— 全仓唯一只认 env、不认 `is_dispatcher_owned_worker` ContextVar 的看板消费者(见 §4 ■3) | 待处置 |
| **H-R9D-C-f** | R10+ | `tools/todo_tool.py:199`:`item_id = str(item.get("id", "")).strip() or "?"` —— 多条缺 id 的待办折叠成一条,静默丢计划(见 §4 ■4) | 待处置 |

### 给 H-R9A-b 定案位的材料(waitpid 移交项)

我这一片是**看板工具侧**,结论是:**`tools/kanban_tools.py` 与那个 `waitpid(-1)` 站点完全无关。**

**调用关系(搜索面写明)**:

```verify
cd /home/user/hermes-agent && grep -rn "reap_worker_zombies" --include=*.py . ; echo "---" ; grep -rn "waitpid" --include=*.py .
```

搜索面 = 全仓 `*.py`,模式分别为字面 `reap_worker_zombies` 与 `waitpid`,未排除任何目录。结果:

```console
./gateway/kanban_watchers.py:1427:                pids = await asyncio.to_thread(_kb.reap_worker_zombies)
./hermes_cli/kanban_db.py:6930:def reap_worker_zombies() -> "list[int]":
./hermes_cli/kanban_db.py:8317:    # reap_worker_zombies() for the full rationale.
./hermes_cli/kanban_db.py:8318:    reap_worker_zombies()
```

`tools/kanban_tools.py` 零命中。它调用的 `kanban_db` 函数共 28 个符号
(`connect` / `get_task` / `create_task` / `complete_task` / `block_task` / `unblock_task` /
`link_tasks` / `add_comment` / `list_comments` / `list_comments_after` / `list_events` /
`list_runs` / `latest_run` / `parent_ids` / `child_ids` / `list_tasks` / `recompute_ready` /
`heartbeat_claim` / `heartbeat_worker` / `build_worker_context` / `store_attachment_bytes` /
`list_attachments` / `add_notify_sub` / `KANBAN_ATTACHMENT_MAX_BYTES` / `VALID_BLOCK_KINDS` /
`ArtifactPreservationError` / `AttachmentTooLarge` / `HallucinatedCardsError`),
**没有一个进入 dispatch/reap 路径**。工具侧只做「读板子 / 改我这张卡」,
**从不 spawn 进程,也从不收尸**。

**所以 H-R9A-b 的暴露面恰好只有两处,都在 dispatcher 侧**:

`gateway/kanban_watchers.py:1424 @ 863e313`

```python
            try:
                # Reap zombie children before per-board work so a board DB
                # failure cannot block cleanup of unrelated workers.
                pids = await asyncio.to_thread(_kb.reap_worker_zombies)
                if pids:
```

`hermes_cli/kanban_db.py:8316 @ 863e313`

```python
    # Reap zombie children from previously spawned workers. See
    # reap_worker_zombies() for the full rationale.
    reap_worker_zombies()
```

`hermes_cli/kanban_db.py:6930 @ 863e313`

```python
def reap_worker_zombies() -> "list[int]":
    """Reap all zombie children of this process without blocking.

    Returns the list of reaped PIDs. Safe to call when there are no
    children (returns []). No-op on Windows.
    """
    reaped: "list[int]" = []
    if os.name != "nt":
        try:
            while True:
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    break
                if pid == 0:
                    break
                _record_worker_exit(pid, status)
                reaped.append(pid)
        except Exception:
            pass
    return reaped
```

**我能补的一块新证据:R9A 说「asyncio 侧三次实测未复现」,但机制本身在 CPython 里是确定的。**
一个第三方 `waitpid(-1)` 会把子进程的退出状态取走,之后属主的 `Popen.wait()` 拿到的是 **0**,
而不是真实退出码 —— 因为 CPython 的 `Popen._try_wait` 捕获 `ChildProcessError` 后按
「已退出、状态 0」处理。独立最小复现(不涉及基线代码):

```verify
/home/user/hermes-venv/bin/python -c "
import os, subprocess, sys, time
p = subprocess.Popen([sys.executable, '-c', 'import sys; sys.exit(42)'])
time.sleep(0.5)
reaped = []
while True:
    try:
        pid, status = os.waitpid(-1, os.WNOHANG)
    except ChildProcessError:
        break
    if pid == 0:
        break
    reaped.append((pid, os.WEXITSTATUS(status)))
print('third-party reaper saw:', reaped)
print('owner Popen.wait() ->', p.wait(), '(real exit code was 42)')
"
```

```console
third-party reaper saw: [(12737, 42)]
owner Popen.wait() -> 0 (real exit code was 42)
```

**结论(给定案位)**:机制成立且可复现;R9A「未复现」的多半是**竞速条件**而非机制不成立
—— 需要 reaper tick 恰好落在「子进程已退出、属主尚未 `wait()`」的窗口里。
网关进程里同时存在终端工具子进程、MCP stdio 服务器子进程、以及看板 worker,
所以窗口是真实存在的;但复现需要控制 tick 与 `wait()` 的相对时序,
单纯多跑几次 asyncio 循环撞不上。另外 `_record_worker_exit` 会把**所有**被收的 pid
(包括不是看板 worker 的)记进 `_recent_worker_exits`,该 dict 有 `_RECENT_WORKER_EXITS_MAX`
上限与按时间的裁剪,所以不会无界增长 —— 污染的是**语义**(`worker_exit_reason` 会对
一个非 worker 的 pid 给出 `clean_exit` / `signaled` 判定),不是内存。

---

## 7. 交付自检

```verify
git -C /home/user/hermes-agent status --porcelain; echo "exit=$?"
git -C /home/user/hermes-agent rev-parse HEAD
```

```console
exit=0
863e31318553cda8ad61df681d08175364d4164b
```

- **基线工作区干净**:`git status --porcelain` 输出为**空**(上面 `exit=0` 之前无任何行),
  HEAD 仍为 `863e31318553cda8ad61df681d08175364d4164b`。全程未在基线内做任何写操作
  (无 commit / checkout / clean / stash,无 npm / pip)。
- **未安装任何包**:venv 包数在本片开始与结束时均为 87(见 §3.1)。
  所有跑基线代码的命令均带 `HERMES_DISABLE_LAZY_INSTALLS=1`。
- **未改 `scripts/`**:本片只写了 `/home/user/hermes-study/notes/r9d-raw-kanban-todo-cron.md`
  这一个文件;所有实验脚本写在会话 scratchpad 目录下,不在两个仓库里。
- **测试**:14 个文件,206 passed / 0 failed(见 §3.2)。无静默跳过。
