# r9d-90 · 移交项取证组 A —— H-R9A-b(waitpid 收尸)+ H-R9A-c(改文件工具白名单)

> 本文是**底稿**(证据层),求全求证不求好读。所有对 hermes-agent 的断言紧跟
> `路径:行号 @ 863e313` 与代码原文块。
> 术语锚定:**收尸(reap)** = 父进程调用 `waitpid` 取走已退出子进程的退出状态,
> 使其从"僵尸(zombie)"变为彻底消失;**退出状态被"偷走"** = 别人先 `waitpid` 到了,
> 真正的属主再问内核时子进程已不存在。

## 0. 基线与环境自检

```verify
cd /home/user/hermes-agent && git rev-parse HEAD && git status --porcelain
```

```text
863e31318553cda8ad61df681d08175364d4164b
(git status --porcelain 输出为空)
```

基线工作区干净,未做任何写操作。

- venv:`/home/user/hermes-venv`,`pip list` 去表头后 **87 个包**(与 CLAUDE.md 记录的 R8B 环境一致)。
- Python **3.11.15**(下文对 CPython `subprocess` 内部行为的引用以此版本为准)。
- 本轮跑测试 **3 个文件,34 passed,0 failed**(见 §2.6)。

---

# 1. H-R9A-b —— `waitpid(-1)` 替别人收尸

## 1.1 原移交项复述

R9A 移交原文:锚点 `hermes_cli/kanban_db.py:6941` 的 `os.waitpid(-1, os.WNOHANG)`。
现象:全仓唯一一处 `waitpid(-1)`,跑在网关工作线程上,会替别处的后台 `Popen` 收尸,
使属主拿到错误退出码;**R9A 自己说"asyncio 侧三次实测未复现,不主张"**。

## 1.2 锚点核对 —— 准确,未漂移

`hermes_cli/kanban_db.py:6930 @ 863e313`

```
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
```

`os.waitpid(-1, os.WNOHANG)` 确实在 **:6941**,移交锚点**准确**。
注意 `while True` —— 它不是收一个就走,而是**一次性把当前所有已退出的子进程全部排干**。

**全称否定的搜索面(“全仓唯一一处 `waitpid(-1)`”)。**
命令如下,搜索面 = 基线仓库根下全部 `*.py`(含 `tests/`、`scripts/`),模式为字面量 `waitpid`,
不排除任何目录:

```verify
cd /home/user/hermes-agent && grep -rn "waitpid" --include=*.py .
```

```text
./scripts/profile-tui.py:458:                pid_done, _ = os.waitpid(pid, os.WNOHANG)
./scripts/profile-tui.py:464:                os.waitpid(pid, 0)
./hermes_cli/kanban_db.py:6941:                    pid, status = os.waitpid(-1, os.WNOHANG)
（其余 8 处命中均在 tests/ 的 .pyc 与用例文本中）
```

`scripts/profile-tui.py` 的两处都是 `waitpid(pid, ...)`(指定 pid,不抢别人)。
**R9A 这条负结论成立**:全仓非测试代码里 `waitpid(-1)` 只此一处。

## 1.3 取证:调用链 —— 谁、在什么线程、多久一次

**两个调用点,都落在非主线程上。**

调用点 1(网关内嵌 kanban 调度器,每 tick 一次):

`gateway/kanban_watchers.py:1423 @ 863e313`

```
        while self._running:
            try:
                # Reap zombie children before per-board work so a board DB
                # failure cannot block cleanup of unrelated workers.
                pids = await asyncio.to_thread(_kb.reap_worker_zombies)
                if pids:
                    logger.info(
                        "kanban dispatcher: reaped %d zombie worker(s), pids=%s",
                        len(pids),
                        pids,
                    )
            except Exception:
```

`asyncio.to_thread` 把它丢进**默认线程池的工作线程**执行 —— 这正是移交项说的"跑在网关工作线程上"。

调用点 2(`dispatch_once` 内部,该函数本身也由 `asyncio.to_thread` 调起):

`hermes_cli/kanban_db.py:8316 @ 863e313`

```
    # Reap zombie children from previously spawned workers. See
    # reap_worker_zombies() for the full rationale.
    reap_worker_zombies()
```

**频率与默认开关。** 调度器**默认在网关进程内启动**,tick 间隔默认 **60 秒**:

`gateway/kanban_watchers.py:1029 @ 863e313`

```
            interval = float(kanban_cfg.get("dispatch_interval_seconds", 60) or 60)
```

`hermes_cli/config_defaults.py:2268 @ 863e313`

```
        "dispatch_interval_seconds": 60,
```

`kanban.dispatch_in_gateway` 的默认值是 `True` —— docstring 与实现两处都写明:

`gateway/kanban_watchers.py:956 @ 863e313`

```
        Gated by `kanban.dispatch_in_gateway` in config.yaml (default True).
```

`gateway/kanban_watchers.py:991 @ 863e313`

```
        if not kanban_cfg.get("dispatch_in_gateway", True):
```

即:**默认配置下,每个网关进程每 60 秒执行一次"排干全部已退出子进程"。**

## 1.4 取证:R9A 为什么没复现 —— 它找错了地方(已实证)

这是本项的关键。**风险真实存在,R9A 的复现方法探的是错误的那一侧。**

### 机制:两条路径对"退出状态被偷走"的反应完全不同

**(a) asyncio 侧(R9A 探的那一侧)。** Python 3.11 默认 `ThreadedChildWatcher`:
每 spawn 一个子进程就起一条**专用线程**,立刻阻塞在 `os.waitpid(pid, 0)` 上。
它几乎总是抢在 60 秒一次的收尸器前面;即便偶尔被抢到,CPython 的处理是
**记 returncode = 255 并打一条 warning 日志**——响亮、且 255 显然不是"成功"。

**(b) 阻塞 `subprocess` 侧(R9A 没探的那一侧)。** CPython `Popen._wait(timeout)`
在**带 timeout 时进入忙轮询**:`_try_wait(os.WNOHANG)` + `time.sleep(delay)`,
`delay` 最大 50 ms。**在这些 sleep 期间子进程没有任何线程守着**。
而 `_try_wait` 撞到 `ChildProcessError` 时:

```text
（CPython 3.11.15 Lib/subprocess.py，Popen._try_wait，非 hermes-agent 源码）
        def _try_wait(self, wait_flags):
            """All callers to this function MUST hold self._waitpid_lock."""
            try:
                (pid, sts) = os.waitpid(self.pid, wait_flags)
            except ChildProcessError:
                # This happens if SIGCLD is set to be ignored or waiting
                # for child processes has otherwise been disabled for our
                # process.  This child is dead, we can't get the status.
                pid = self.pid
                sts = 0
            return (pid, sts)
```

**`sts = 0` → `returncode = 0` → "成功"。** 这条路径是**静默的,而且方向最坏**:
失败被读成成功。上面这段是 CPython 标准库源码,不是基线源码,故按声明式豁免用 ```text 标注;
复核命令见下。

```verify
/home/user/hermes-venv/bin/python -c "import inspect,subprocess;print(inspect.getsource(subprocess.Popen._try_wait))"
```

### 实验 1:阻塞 `subprocess` 侧 —— **复现成功**

脚本 `/tmp/.../scratchpad/exp_b.py`,直接 import 基线的 `hermes_cli.kanban_db`,
victim 侧照抄 `tools/code_execution_tool.py` 的 `poll()`/`wait(timeout=)` 轮询形状,
reaper 侧照抄 `gateway/kanban_watchers.py:1427`(为把 60 s 间隔压进测试时长,tick 加速到 5 ms):

```text
no reaper (control)          -> returncodes=[42, 42, 42, 42, 42]  (true exit code is 42)
with reap_worker_zombies     -> returncodes=[0, 42, 42, 0, 42]    (true exit code is 42)
```

**5 次里 2 次把真实退出码 42 读成了 0。** 对照组 5/5 正确。

### 实验 2:确定性版本 —— 收尸只要落进窗口就 **100% 偷走**

只发**一次**收尸(严格等价于一次 dispatcher tick),时间点落在子进程已退出、属主还在 sleep 的窗口内:

```text
trial 0: reaped=[32450] owner_sees_returncode=0 (true=42) stolen=YES
trial 1: reaped=[32451] owner_sees_returncode=0 (true=42) stolen=YES
trial 2: reaped=[32453] owner_sees_returncode=0 (true=42) stolen=YES
```

这条很重要:**竞态不在"偷得成不成功",而只在"收尸有没有落进窗口"。**
落进去就是确定性地偷走。

### 实验 3:asyncio 侧 —— 复现困难,且**失败形态完全不同**

同一个收尸线程(同样 5 ms 加速),victim 换成 `asyncio.create_subprocess_exec`:

```text
child watcher: ThreadedChildWatcher
Unknown child process pid 28470, will report returncode 255
asyncio returncodes with reaper running: [42, 255, 42, 42, 42]  (true exit code is 42)
```

**结论(实跑复现):R9A 的"三次实测未复现"是方法问题,不是风险不存在。**
asyncio 侧(a)命中率低,(b)命中了也是 **255 + 一行 warning 日志**,
一个只看"有没有拿到 42"的探针跑三次很容易全绿。真正危险的形态在阻塞 `subprocess` 侧,
它给出的是 **0(成功)且完全静默**,而 R9A 从未探过这一侧。

## 1.5 取证:会被误收的属主(搜索面写明)

**搜索面**:基线仓库根下全部 `*.py`,模式为 `\.poll() is None|\.poll() is not None|= *proc\.poll()|\.wait(timeout=`,
**排除** `./tests/` 目录,并**排除** `threading.Event` / `stop_event` / `probe_event` / `done.wait` / `evt.wait`
这类同名但与进程无关的等待(它们是事件对象不是 `Popen`)。命令:

```verify
cd /home/user/hermes-agent && grep -rn "\.poll() is None\|\.poll() is not None\|= *proc\.poll()\|\.wait(timeout=" --include=*.py . | grep -v "^./tests/" | grep -v "_event\.wait\|stop_event\|probe_event\|done\.wait\|evt\.wait\|threading"
```

在命中里,**真会读退出码、且与收尸器同进程**的属主:

| 属主 | 锚点 + 摘录 | 是否读退出码 | 与收尸器同进程 |
|---|---|---|---|
| `execute_code` 工具轮询 | `tools/code_execution_tool.py:1592`:`while proc.poll() is None:` | 是 | 是(网关内嵌 AIAgent) |
| `execute_code` 取码 | `tools/code_execution_tool.py:1627`:`exit_code = proc.returncode if proc.returncode is not None else -1` | 是 | 是 |
| `execute_code` 判失败 | `tools/code_execution_tool.py:1679`:`elif exit_code != 0:` | 是 | 是 |
| 仪表盘 action 状态 | `hermes_cli/web_server.py:4786`:`exit_code = proc.poll()` | 是(并缓存进 `_ACTION_RESULTS`) | 推定(未取证) |

**最强的一条受害链(静态对读 + 实跑机制复现,已闭环)。**
`execute_code` 用的正是实验 1/2 复现的那个形状,而它把退出码直接翻译成给模型看的成败:

`tools/code_execution_tool.py:1679 @ 863e313`

```
        elif exit_code != 0:
            result["status"] = "error"
            result["error"] = stderr_text or f"Script exited with code {exit_code}"
```

退出码被偷 → `exit_code == 0` → **这一支不进入** → `status` 保持它在轮询开始前设的初值:

`tools/code_execution_tool.py:1582 @ 863e313`

```
        status = "success"
```

即:**一段真的失败了的脚本,会被当作成功汇报给模型。**

**同进程性(co-tenancy)取证。** 收尸器默认跑在网关进程(§1.3);网关进程在进程内构造 AIAgent:

`gateway/run.py:4794 @ 863e313`

```
            agent = ctx.AIAgent(
```

而 `execute_code` 注册进的是同一进程的工具注册表:

`tools/code_execution_tool.py:2077 @ 863e313`

```
    name="execute_code",
```

故两者同进程。

**一处需要澄清的非受害者(避免误传)。** `gateway/slash_commands.py:5644` 的
`rc = proc.wait(timeout=3600)` 看起来像受害者,但它位于一段被
`subprocess.Popen([sys.executable, "-c", helper, ...])` 送去**另一个进程**执行的 helper 源码字符串里,
不在网关进程内,**不受影响**。

## 1.6 附带发现:收尸器的测试小节是空的

`tests/hermes_cli/test_kanban_db.py:1547 @ 863e313`

```
# ---------------------------------------------------------------------------
# reap_worker_zombies() tests
# ---------------------------------------------------------------------------
```

标题下方 **1550–1559 行全为空行**,下一个非空内容是另一小节的横幅注释。
即**这个小节挂着"reap_worker_zombies() tests"的名字,里面一个用例都没有**。

```verify
cd /home/user/hermes-agent && awk 'NR>=1547&&NR<=1560{printf "%d:[%s]\n", NR, $0}' tests/hermes_cli/test_kanban_db.py
```

搜索面:`grep -rn "reap" tests/` 全量扫过,`tests/` 下没有任何用例调用 `reap_worker_zombies`
(唯一另一处提及是 `tests/hermes_cli/test_kanban_core_functionality.py:1078` 的一句**注释**)。
**这处 `waitpid(-1)` 没有任何行为规格覆盖** —— 与 §1.4 的结论互相印证:
无人测过它对同进程其他子进程的影响。

## 1.7 处置结论:**立 ■(代码缺陷),但严重度按低概率如实标注**

**■ H-R9A-b 成立。** `hermes_cli/kanban_db.py:6941` 的 `os.waitpid(-1, os.WNOHANG)`
是进程级全局操作,却被一个**子系统级**(kanban 调度器)的后台循环无条件调用。
它会排干**整个进程**所有已退出子进程,包括它并不拥有的那些。
被偷走退出状态的 `Popen` 属主在 CPython 下得到 **`returncode = 0`**,
即**失败静默变成成功**。已在基线代码上实跑复现(§1.4 实验 1、2)。

**推翻了原移交项的哪一部分:** R9A 说"asyncio 侧三次实测未复现,不主张"。
本轮实证 R9A 的探针方向错误 —— asyncio 侧因 `ThreadedChildWatcher` 抢先且失败形态为
"255 + warning",本就难复现且不静默;真正的受害形态在阻塞 `subprocess` 的轮询等待侧,
R9A 从未探过。**"未复现"不等于"无风险",这一判断被推翻。**

**维持/收紧了哪一部分:** 移交项说的"跑在网关工作线程上""会替别处的后台 Popen 收尸""属主拿到错误退出码"
三点全部取证成立,并补上了它没说的关键一环:**错误退出码的具体值是 0(成功),不是随机值**。

**严重度如实标注(不夸大)。** 生产默认 tick 间隔是 **60 秒**(§1.3),而 `execute_code` 的轮询退避上限是 0.2 s:

`tools/code_execution_tool.py:1613 @ 863e313`

```
            poll_interval = min(0.2, poll_interval * 1.5)
```

故单次 tick 命中某个特定属主窗口的概率很低,
**这是一个低频、但静默且方向最坏(失败→成功)的缺陷**,不是高频故障。
上面实验用 5 ms 加速 tick 是为了在测试时长内把窗口撞出来,**不代表生产命中率**。

**修法方向(设计层面,供 R12 蓝图引用):** 子系统级的收尸必须按 pid 定向 ——
调度器已经知道自己 spawn 了哪些 worker pid,应改为对**自己的 pid 集合**逐个
`waitpid(pid, WNOHANG)`,而不是 `waitpid(-1)`。`waitpid(-1)` 只属于进程里**唯一的 init 角色**;
一个库级模块调用它,就是在替整个进程做决定。

---

# 2. H-R9A-c —— 验证门按工具名白名单判断"改没改文件"

## 2.1 原移交项复述

R9A 移交原文:锚点 `agent/tool_result_classification.py:9` 的 `FILE_MUTATING_TOOL_NAMES`。
现象:验证门按**工具名白名单**判断"这一步改没改文件",于是 `sed -i` / `execute_code` /
MCP 文件工具改了代码之后**直接放行**,台账连"工作区脏了"都不知道。

## 2.2 锚点核对 —— 准确;常量当前完整内容(逐字)

`agent/tool_result_classification.py:9 @ 863e313`

```
FILE_MUTATING_TOOL_NAMES = frozenset({"write_file", "patch"})
```

锚点**准确**,常量**只有两个名字**。判定这个集合是否"落地"的函数紧随其后:

`agent/tool_result_classification.py:26 @ 863e313`

```
def file_mutation_result_landed(tool_name: str, result: Any) -> bool:
    """Return True when a file mutation result proves the write landed."""
    if tool_name not in FILE_MUTATING_TOOL_NAMES or not isinstance(result, str):
        return False
    try:
        data = json.loads(result.strip())
    except Exception:
        return False
    if not isinstance(data, dict) or data.get("error"):
        return False
    if tool_name == "write_file":
        return "bytes_written" in data
    if tool_name == "patch":
```

## 2.3 取证:所有读这个集合的地方,以及"验证门"到底做什么

**搜索面**:基线仓库根下全部 `*.py`,模式 `FILE_MUTATING_TOOL_NAMES|file_mutation_result_landed|tool_may_have_side_effect`,
不排除任何目录。

```verify
cd /home/user/hermes-agent && grep -rn "FILE_MUTATING_TOOL_NAMES\|file_mutation_result_landed" --include=*.py . | grep -v "^./tests/"
```

非测试读取点共 4 处 + 定义处:

| 读取点 | 锚点 + 摘录 | 作用 |
|---|---|---|
| 记录本轮改动路径 | `run_agent.py:3408`:`if tool_name not in _FILE_MUTATING_TOOLS:` | 不在白名单直接 `return`,该次调用**不进入**任何本轮改动台账 |
| 解析改动目标路径 | `agent/tool_dispatch_helpers.py:416`:`if tool_name not in _FILE_MUTATING_TOOLS:` | 不在白名单返回 `[]` |
| 失败分类兜底 | `agent/tool_guardrails.py:249`:`if file_mutation_result_landed(tool_name, result):` | 判"这次写盘算不算失败" |
| CLI 内联 diff | `agent/display.py:1316`:`if file_mutation_result_landed(tool_name, result):` | 决定要不要渲染 diff |

**"验证门"的准确所指。** 它不是安全门,而是 **verify-on-stop(停机前验证)门**:
在 agent 准备交出最终答案时,若判定"本轮改过代码",就**不让它停**,而是塞一条合成的
system 提示要求先跑验证。门的输入正是上面那张台账:

`agent/conversation_loop.py:7043 @ 863e313`

```
                    if verify_on_stop_enabled():
                        _verify_nudge = build_verify_on_stop_nudge(
                            session_id=getattr(agent, "session_id", None),
                            changed_paths=getattr(agent, "_turn_file_mutation_paths", set()),
                            attempts=getattr(agent, "_verification_stop_nudges", 0),
```

而门的第一件事就是:**路径集为空 → 直接放行**:

`agent/verification_stop.py:213 @ 863e313`

```
    # Drop documentation/prose paths (markdown, skills, README, LICENSE, ...) —
    # they carry no verifiable behavior, so a turn that touched only those has
    # nothing to verify and must not nudge.
    paths = sorted({str(p) for p in _filter_verifiable_paths(changed_paths)})
    if not paths or attempts >= max_attempts:
        return None
```

早退那两行单独取证(下文多处引用它):

`agent/verification_stop.py:217 @ 863e313`

```
    if not paths or attempts >= max_attempts:
        return None
```

**"放行"的后果**:`build_verify_on_stop_nudge` 返回 `None` → `conversation_loop` 不设
`finish_reason = "verification_required"` → 本轮**正常结束**,模型那句"我改好了"被直接采纳,
**没有任何人要求它跑一次测试**。注意这个早退发生在读验证证据库**之前**,
所以即便别处已知道工作区脏了也无济于事。

## 2.4 取证:三类绕过的实证(实跑)

脚本直接 import 基线模块,把四种"真的改了 `/work/app.py`"的调用喂给分类器:

```text
whitelist = ['patch', 'write_file']
terminal                         in_whitelist=False landed=False targets=[] landed_paths=[]
execute_code                     in_whitelist=False landed=False targets=[] landed_paths=[]
mcp_filesystem_write_file        in_whitelist=False landed=False targets=[] landed_paths=[]
skill_manage                     in_whitelist=False landed=False targets=[] landed_paths=[]
write_file                       in_whitelist=True  landed=True  targets=['/work/app.py'] landed_paths=['/work/app.py']
```

`terminal`(`sed -i`)、`execute_code`、MCP 文件工具**三类全部** `targets=[]` ——
即本轮改动台账**收不到任何路径**,与移交项描述一致。

**端到端 A/B 对照(同一个真实改动,只换归因工具)。** 在一个真实 git 工作区里直接调
`build_verify_on_stop_nudge`:

```text
A: sed -i / execute_code (whitelist miss)
   nudge_is_None=True
B: same edit via write_file
   nudge_is_None=False
   -> [System: You edited code in this turn, but the workspace does not have fresh passing verification evidence yet. |  | Verification status: unverified |  | Changed paths: | - `/tmp/hermes-veri
```

**同一处真实代码改动,经 `write_file` 会被拦下要求验证,经 `sed -i` 则直接放行。**
移交项描述的绕过**实证成立**。

## 2.5 取证:这是不是有意保守的设计选择?

**没有找到任何声称保守的注释、测试或文档。** 搜索面:
`agent/tool_result_classification.py` 与 `agent/verification_stop.py` 全文(找 `whitelist` /
`allowlist` / `conservative` / `sed -i`,**零命中**);
`--include=*.md` 全仓找 `FILE_MUTATING` / `file_mutation_verifier` / `verify_on_stop`。

文档侧对**页脚验证器**(另一个消费者)的描述是**字面准确**的,明确写了只管 `write_file`/`patch`:

`website/docs/user-guide/configuration.md:1694 @ 863e313`

> When `display.file_mutation_verifier` is `true` (default), Hermes appends a one-line advisory to the assistant's final response whenever a `write_file` or `patch` call failed during the turn and was never superseded by a successful write to the same path.

但对 **verify-on-stop / `pre_verify` 门**,文档给出的触发条件是"**改了代码**",不是"调了 write_file/patch":

`website/docs/user-guide/features/hooks.md:670 @ 863e313`

> Fires **once per turn when the agent edited code**, just before it finishes (after the built-in verify-on-stop guard). This is a user/plugin policy gate: a callback can keep the agent going — run a check, defer it, tidy the diff — instead of letting it stop.

`website/docs/user-guide/features/hooks.md:693 @ 863e313`

> **Fires:** In `agent/conversation_loop.py`, at the point the agent would accept a final answer, immediately after the verify-on-stop check — but only when the agent edited code this turn and at least one `pre_verify` hook is registered.

`website/docs/user-guide/features/hooks.md:689 @ 863e313`

> | `changed_paths` | `list` | Files the agent edited this turn (sorted, always non-empty here) |

**▲(文档与代码矛盾)。** 按整段判定:这三处同属 `### pre_verify` 标题下,
共同给出的触发条件是"the agent edited code this turn",且 `changed_paths` 被描述为
"Files the agent edited this turn"。而 §2.4 已实证:一次 `sed -i` 改了代码的轮次,
`changed_paths` 为空、门不触发。**文档陈述的触发条件在实现中不成立**,
`changed_paths` 也不是"agent 本轮改的文件",而是"agent 本轮**通过 write_file/patch** 改的文件"。
这不是"保守但字面为真"(那样才是 ◎)—— 文档给的是一个**精确的触发条件**,而它是假的,故记 ▲。

**结论:没有证据表明白名单是有意保守的设计选择。** 更像是把一个为**页脚验证器**
(其文档口径确实只承诺 write_file/patch)设计的窄集合,**复用**到了一个语义更宽的
verify-on-stop 门上,而没有随之放宽。

## 2.6 取证:白名单里的名字与实际注册的工具名对得上吗?

**对得上。** 白名单的两个名字与 `tools/file_tools.py` 的实际注册名逐字一致:

`tools/file_tools.py:2317 @ 863e313`

```
registry.register(name="write_file", toolset="file", schema=WRITE_FILE_SCHEMA, handler=_handle_write_file, check_fn=_check_file_reqs, emoji="✍️", max_result_size_chars=100_000)
registry.register(name="patch", toolset="file", schema=PATCH_SCHEMA, handler=_handle_patch, check_fn=_check_file_reqs, emoji="🔧", max_result_size_chars=100_000)
```

**本轮 R9D 范围三个文件的核对结果:**

| 文件 | 是否注册工具 | 与白名单的关系 |
|---|---|---|
| `tools/file_tools.py` | 注册 4 个:`read_file` / `write_file` / `patch` / `search_files` | `write_file`、`patch` **名字对得上** |
| `tools/file_operations.py` | **不注册任何工具**,是 `file_tools` 背后的引擎(`tools/file_operations.py:1412` 的 `def write_file`) | 无名字漂移风险 |
| `tools/working_diff.py` | **不注册任何工具**,只导出 `tools/working_diff.py:70` 的 `collect_working_diff` | 见下 |

**搜索面**:`grep -rhn 'registry.register(name="' tools/*.py` 全量,`tools/` 下经此形式注册的工具名
只有 `patch` / `read_file` / `search_files` / `write_file` 四个。

```verify
cd /home/user/hermes-agent && grep -rhn 'registry.register(name="' tools/*.py | sed 's/.*name="\([^"]*\)".*/\1/' | sort -u
```

**◇(代码有、文档无)—— 仓库里已有一个 git 级"工作区脏了"探针,验证门却不用它。**

`tools/working_diff.py:70 @ 863e313`

```
def collect_working_diff(cwd: str, mode: str = "working",
                         paths: List[str] | None = None) -> Dict:
```

它能从 git 直接算出工作区改动,但**搜索面**(`grep -rn "working_diff" --include=*.py .`,排除 `tests/`)
显示调用方只有两处 —— `/diff` 斜杠命令与 CLI:

`gateway/slash_commands.py:3224 @ 863e313`

```
        from tools.working_diff import collect_working_diff

        result = await asyncio.to_thread(collect_working_diff, cwd, mode)
```

`hermes_cli/cli_commands_mixin.py:185 @ 863e313`

```
        from tools.working_diff import collect_working_diff

        result = collect_working_diff(cwd, mode=mode, paths=paths or None)
```

**验证门从不调用它**。
即:"台账连工作区脏了都不知道"这个说法,准确的形态是
**"仓库有能力知道,但验证门没接这条线"**。

**■(附带发现)白名单在自己项目内部就不自洽。** 同一个"改文件工具"概念,
`agent/display.py` 用的是**三元**集合:

`agent/display.py:909 @ 863e313`

```
    if tool_name not in {"write_file", "patch", "skill_manage"}:
```

`skill_manage` 被 display 当作会改文件的工具(要为它渲染 diff),却**不在**
`FILE_MUTATING_TOOL_NAMES` 里。同一概念两处硬编码、内容不同,是典型的会漂的形态。

**测试(行为规格)实跑:**

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/agent/test_tool_result_classification.py tests/run_agent/test_file_mutation_verifier.py tests/run_agent/test_verification_continuation_budget.py
```

```text
=== Summary: 3 files, 34 tests passed, 0 failed (100% complete) in 3.3s (8 workers) ===
```

**3 个文件 / 34 passed / 0 failed。** 逐条诊断:无失败项。
但需指出:`tests/agent/test_tool_result_classification.py` 只断言白名单**内**的行为,
**没有任何用例断言"terminal / execute_code 改了文件时应当发生什么"** ——
即绕过路径无行为规格覆盖。

## 2.7 处置结论:**■ 成立(定性为设计缺口 + 一处 ▲ + 一处 ◇)**

**■ H-R9A-c 成立,维持原移交项判断,并收紧其表述。**
verify-on-stop 门以 `FILE_MUTATING_TOOL_NAMES`(仅 `write_file`、`patch`)为唯一事实来源
判定"本轮是否改过代码"。经 `terminal`(`sed -i`)、`execute_code`、MCP 文件工具改动代码的轮次,
`changed_paths` 为空,门在 `agent/verification_stop.py:217` 早退放行 —— **实证成立**(§2.4 A/B 对照)。

**推翻/修正了原移交项的哪一部分:**
1. 原文"台账连工作区脏了都不知道"**表述过宽**。准确说法是:**本轮改动台账**确实不知道,
   但仓库另有 `tools/working_diff.py:70` 的 `collect_working_diff` 能从 git 得知,
   只是验证门没接它(记 ◇)。这是"没接线",不是"没能力"。
2. 原文暗示这可能只是实现疏漏。本轮补上了**文档侧的定案**:文档给 `pre_verify` 门写的触发条件是
   "the agent edited code this turn"(`hooks.md:670`/`:693`/`:689`),与实现矛盾,记 **▲**。

**维持的部分:** 白名单绕过三类(shell / 代码执行 / MCP)全部实证成立;
"按工具名判断改没改文件"这一设计取向本身是缺口。

**是不是有意的设计选择:判断为"否"(无证据支持)。** §2.5 已给出搜索面,
注释、测试、文档三侧均无"有意保守"的说法;文档反而承诺了更宽的语义。

**名字漂移:未发生。** 白名单两个名字与 `tools/file_tools.py:2317`/`:2318` 的注册名逐字一致。
但同概念在 `agent/display.py:909` 有第二份不同的硬编码集合(多一个 `skill_manage`),
是尚未发生、但结构上已具备的漂移点。

---

# 3. 未取证 / 推定

按断言强度如实分列。

| 项 | 锚点 + 摘录 | 强度 | 说明 |
|---|---|---|---|
| 仪表盘 action 状态也会被偷 | `hermes_cli/web_server.py:4786`:`exit_code = proc.poll()` | **推定,未取证** | 形状完全吻合(纯 `poll()`,被偷即得 0 并缓存进 `_ACTION_RESULTS`),但**未取证 `hermes_cli/web_server.py` 是否与 kanban 收尸器同进程运行**。若不同进程则不受影响 |
| 生产环境实际命中率 | `gateway/kanban_watchers.py:1029`:`interval = float(kanban_cfg.get("dispatch_interval_seconds", 60) or 60)` | **静态推算,未实测** | 60 s tick × 0.2 s 轮询窗口,推算命中率很低;**本轮所有复现都用了加速 tick(5 ms),不能外推为生产频率** |
| `terminal` 工具主执行路径是否为受害形状 | `tools/terminal_tool.py:791`:`probe = subprocess.run(` | **部分取证** | 只确认了几处 `subprocess.run(..., timeout=)` 短探针(带 timeout 即走轮询,理论上是受害形状);**terminal 的持久 shell 会话主路径未逐行读完**,未判定 |
| `_record_worker_exit` 是否构成"补偿机制" | `hermes_cli/kanban_db.py:6864` 的 `_record_worker_exit` | **未取证** | 收尸器把偷到的状态记进了模块级字典。**未查清是否有任何消费者能借此把状态还给真正的属主**(直觉上不能,因为属主是 `Popen` 对象、不查这个字典),但未做搜索 |
| ▲ 的判定边界 | `website/docs/user-guide/features/hooks.md:670` 的 `Fires` | **静态对读** | 判为 ▲ 的依据是文档给出了精确触发条件且实现不满足。若评审位认为该句属"意图性描述"而非"条件断言",可降为 ◎;本轮取 ▲,理由见 §2.5 |
| MCP 文件工具的真实工具名 | `agent/tool_result_classification.py:9`:`FILE_MUTATING_TOOL_NAMES = frozenset({"write_file", "patch"})` | **构造实证,非真实调用** | §2.4 用 `mcp_filesystem_write_file` 作为代表名喂分类器。**未取证真实 MCP 服务器注册进来的文件工具叫什么** —— 但因白名单是**闭集**,任何非 `write_file`/`patch` 的名字结果都相同,不影响结论 |

---

# 4. 给主线的移交表(声明式锚点)

| 编号 | 处置 | 锚点 + 摘录 | 一句话现象 |
|---|---|---|---|
| H-R9A-b | **改判:立 ■**(R9A 原为"不主张") | `hermes_cli/kanban_db.py:6941`:`pid, status = os.waitpid(-1, os.WNOHANG)` | 子系统级后台循环用进程级 `waitpid(-1)` 排干**全进程**已退出子进程;被偷走状态的 `Popen` 属主在 CPython 下得 `returncode = 0`,**失败静默变成功**,已实跑复现 |
| H-R9A-b 附 | 新增 ■(覆盖缺口) | `tests/hermes_cli/test_kanban_db.py:1548`:`# reap_worker_zombies() tests` | 该测试小节标题下 1550–1559 行全空,**一个用例都没有** |
| H-R9A-c | **维持 ■** | `agent/tool_result_classification.py:9`:`FILE_MUTATING_TOOL_NAMES = frozenset({"write_file", "patch"})` | verify-on-stop 门只认这两个名字;`sed -i` / `execute_code` / MCP 改代码后 `changed_paths` 为空,门在 `agent/verification_stop.py:217`:`if not paths or attempts >= max_attempts:` 早退放行 |
| H-R9A-c ▲ | 新增 ▲ | `website/docs/user-guide/features/hooks.md:670` 的 `Fires` | 文档写门"when the agent edited code"触发,实为"when write_file/patch succeeded";`website/docs/user-guide/features/hooks.md:689` 更把 `changed_paths` 描述为"Files the agent edited this turn" |
| H-R9A-c ◇ | 新增 ◇ | `tools/working_diff.py:70` 的 `collect_working_diff` | 仓库已有 git 级工作区改动探针,但只被 `/diff` 与 CLI 调用,**验证门从不调它** |
| H-R9A-c ■附 | 新增 ■(内部不自洽) | `agent/display.py:909`:`if tool_name not in {"write_file", "patch", "skill_manage"}:` | 同一"改文件工具"概念在 display 是三元集合(多 `skill_manage`),与白名单不一致 |
