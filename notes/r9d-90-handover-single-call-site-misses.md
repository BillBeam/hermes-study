# r9d-90 · 移交项取证组 B —— 「N 处同类调用点里唯独一处漏了守卫」两个标本

> 底稿(证据层)。研究对象:hermes-agent，基线 commit `863e313`
> (`863e31318553cda8ad61df681d08175364d4164b`)。
> 所有 `路径:行号 @ 863e313` 均相对基线仓库根 `/home/user/hermes-agent`。
> 术语一次性锚定:
> **contextvar**(上下文变量,Python `contextvars.ContextVar`)= 一个"每线程/每异步任务各自一份"的全局变量;
> 新起的线程拿到的是**空**的一份,不继承父线程的值,除非父线程显式 `copy_context()` 快照后交给它跑。
> **SSRF**(Server-Side Request Forgery,服务端请求伪造)= 让服务端替攻击者去访问它自己能访问、
> 而攻击者访问不到的地址(内网、云元数据端点等)。
> **fail-open / fail-closed**(失效放行 / 失效阻断)= 判定所需信息缺失时,默认放行还是默认拒绝。

**本轮基线只读自检**(交付前实跑,输出为空即基线未被改动):

```verify
git -C /home/user/hermes-agent status --porcelain; echo "[exit=$?] [clean-if-nothing-above]"
git -C /home/user/hermes-agent rev-parse HEAD
```

实测输出:`git status --porcelain` 无任何行;HEAD = `863e31318553cda8ad61df681d08175364d4164b`。
测试 venv:`/home/user/hermes-venv`,`pip list` 去两行表头后 **87** 个包(与 CLAUDE.md 记录的 R8B 环境一致)。

---

## 1. H-R9A-e —— 子代理生命周期服务的裸 `submit`

### 1.1 原移交项复述

> 锚点 `agent/subagent_lifecycle.py:259` 的裸 `submit`。现象:未包上下文传播,
> worker 线程丢审批 session key 与 profile 覆盖;R9A 称"全仓 8 处同类提交点它是唯一漏的"。

要交代四件事:锚点核对、8 这个数重数并写搜索面、"丢审批 session key" 的方向(变严还是变松)、配套测试有没有钉住。

### 1.2 锚点核对:**准确,未漂移**

`agent/subagent_lifecycle.py:255 @ 863e313`

```python
        with _REGISTRY.lock:
            _REGISTRY.records[subagent_id] = record
            if request.correlation_id:
                _REGISTRY.correlations[correlation_key] = subagent_id
        record.future = _EXECUTOR.submit(self._run, record, request.goal, parent)
        return handle
```

`:259` 正是那一行 `record.future = _EXECUTOR.submit(...)`,一字不差,
**没有任何 `copy_context()` / `propagate_context_to_thread()` 包裹**。被提交的可调用是 `self._run`:

`agent/subagent_lifecycle.py:408 @ 863e313`

```python
    def _run(self, record: _Record, goal: str, parent: Any) -> None:
        with _REGISTRY.lock:
            if record.state is not SubagentState.CANCEL_REQUESTED:
```

线程池本身:

`agent/subagent_lifecycle.py:163 @ 863e313`

```python
from tools.daemon_pool import DaemonThreadPoolExecutor as _DaemonExecutor

_EXECUTOR = _DaemonExecutor(max_workers=8, thread_name_prefix="hermes-lifecycle")
```

这是**模块级**的长驻线程池:worker 线程被复用,每个 worker 第一次启动时拿到的是空的 contextvars 映射。

### 1.3 丢的到底是什么:仓库自己写了答案

仓库把"裸线程会丢什么"写成了一个专门的模块文档:

`tools/thread_context.py:4 @ 863e313`

```python
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

即:方向由仓库自己声明为 **auto-approve(自动放行)**,不是"全被拒"。下面用实跑把它坐实。

### 1.4 方向取证(**实跑复现**):是**变松**,不是变严

判定分支在 `_run_approval_gate` 里。两个前置谓词都靠 contextvars:

`tools/approval.py:3219 @ 863e313`

```python
    is_cli = _is_interactive_cli()
    is_gateway = _is_gateway_approval_context()

    if not is_cli and not is_gateway:
```

两个谓词各自读一个 contextvar。第一个 `_is_gateway_approval_context`(定义在 `tools/approval.py:244`)的判定尾部:

`tools/approval.py:258 @ 863e313`

```python
    if _is_cron_approval_context():
        return False
    if env_var_enabled("HERMES_GATEWAY_SESSION"):
        return True
    return bool(_get_session_platform())
```

`_get_session_platform()` 读的是 `gateway.session_context` 里那一排 contextvar:

`gateway/session_context.py:74 @ 863e313`

```python
_SESSION_PLATFORM: ContextVar = ContextVar("HERMES_SESSION_PLATFORM", default=_UNSET)
_SESSION_SOURCE: ContextVar = ContextVar("HERMES_SESSION_SOURCE", default=_UNSET)
```

第二个 `_is_interactive_cli`(定义在 `tools/approval.py:85`)的判定体:

`tools/approval.py:91 @ 863e313`

```python
    ctx_val = _hermes_interactive_ctx.get()
    if ctx_val is not None:
        return is_truthy_value(ctx_val)
    return env_var_enabled("HERMES_INTERACTIVE")
```

**两者在空上下文里都退回环境变量,而 gateway 只写 contextvar、不写 `os.environ`,于是双双为假**,
于是走进 `if not is_cli and not is_gateway:`。
该分支里非 cron、且危险命令路径的 `fail_closed_when_no_human` 默认为 `False`,直落到:

`tools/approval.py:3253 @ 863e313`

```python
        logger.warning(
            "%s (pattern: %s): %s — set HERMES_INTERACTIVE or "
            "HERMES_GATEWAY_SESSION to require approval.",
            autoapprove_log_prefix, pattern_key, description,
        )
        return {"approved": True, "message": None}
```

**实跑复现**(可零成本重跑,不联网、不写基线):

```verify
mkdir -p /tmp/r9d && cat > /tmp/r9d/probe_ctx.py <<'PY'
import os, sys, tempfile, contextvars, concurrent.futures
os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="hermes-probe-")
for v in ("HERMES_GATEWAY_SESSION","HERMES_INTERACTIVE","HERMES_SESSION_KEY","HERMES_SESSION_PLATFORM"):
    os.environ.pop(v, None)
sys.path.insert(0, "/home/user/hermes-agent")
from gateway import session_context as sc
import tools.approval as ap

def probe(tag):
    return {
        "tag": tag,
        "session_key": ap.get_current_session_key(),
        "is_gateway": ap._is_gateway_approval_context(),
        "profile": sc.get_session_env("HERMES_SESSION_PROFILE", "<none>"),
        "approved": ap._run_approval_gate(
            pattern_key="probe_pattern",
            description="probe dangerous action",
            display_target="rm -rf /home/user/probe",
            cron_deny_message="cron-deny",
            autoapprove_log_prefix="PROBE",
        )["approved"],
    }

sc.set_session_vars(platform="telegram", chat_id="42", session_key="telegram:42", profile="work")
ap.set_current_session_key("telegram:42")
print("PARENT  ", probe("parent-thread"))
ex = concurrent.futures.ThreadPoolExecutor(max_workers=2)
print("BARE    ", ex.submit(probe, "bare-submit").result())
ctx = contextvars.copy_context()
print("COPYCTX ", ex.submit(ctx.run, probe, "copy_context-submit").result())
ex.shutdown()
PY
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
  /home/user/hermes-venv/bin/python /tmp/r9d/probe_ctx.py
```

实测输出(逐字照抄,含中间那行 warning 日志):

```text
PARENT   {'tag': 'parent-thread', 'session_key': 'telegram:42', 'is_gateway': True, 'profile': 'work', 'approved': False}
PROBE (pattern: probe_pattern): probe dangerous action — set HERMES_INTERACTIVE or HERMES_GATEWAY_SESSION to require approval.
BARE     {'tag': 'bare-submit', 'session_key': 'default', 'is_gateway': False, 'profile': '<none>', 'approved': True}
COPYCTX  {'tag': 'copy_context-submit', 'session_key': 'telegram:42', 'is_gateway': True, 'profile': 'work', 'approved': False}
```

读法:**父线程 `approved=False`(要求审批)→ 裸 submit `approved=True`(自动放行)→
把同一个函数放进 `copy_context()` 再提交,`approved=False`(恢复为要求审批)**。
第二行那句 warning 正是上面 `tools/approval.py:3253` 那个 `logger.warning` 打出来的,
它本身即"走进了自动放行分支"的证据。

**结论:方向是「变松 / 全放行」。** 丢了 session key 不会让子代理的危险命令全被拒,而是让它们
**绕过审批直接执行**;同时 `HERMES_SESSION_PROFILE` 也从 `work` 变成未设置(profile 覆盖丢失,
子代理会按默认 profile 解析 `get_hermes_home()`)。这是 **■(代码缺陷)**,且是安全方向的缺陷。

**为什么内层的 `copy_context` 救不回来。** `self._run` 会调 `_run_child_lifecycle`
→ `_run_single_child`,后者内部确实有一次 `copy_context()`:

`tools/delegate_tool.py:2207 @ 863e313`

```python
        _child_context = contextvars.copy_context()
        _child_future = _timeout_executor.submit(
            _child_context.run,
            _run_with_thread_capture,
```

但 `copy_context()` 是在**调用它的那个线程**上取快照 —— 此时已经在 `hermes-lifecycle` worker 线程里,
快照到的就是那份空上下文。**它忠实地把"空"传了下去。** 这正是本形态最阴的地方:
下游看起来处处有 `copy_context`,但源头断了,下游全是空转。

### 1.5 重数「同类提交点」:R9A 的 8 复现不出来,我数到 12 处有守卫 + 1 处裸

**搜索面(负结论的成本条款要求):**

```verify
cd /home/user/hermes-agent
# 面 1:全部 .submit( 调用点(含测试与随仓 skills)
grep -rn "\.submit(" --include=*.py . | wc -l                      # 117
# 面 2:排除 tests/ 、skills/ 、optional-skills/ 后的一等代码
grep -rn "\.submit(" --include=*.py . | grep -v "^\./tests/" \
  | grep -v "^\./skills/" | grep -v "^\./optional-skills/" | wc -l # 48
# 面 3:两种传播写法的全部出现处
grep -rn "propagate_context_to_thread" --include=*.py .
grep -rn "copy_context" --include=*.py .
```

实测:面 1 = **117**,面 2 = **48**,`propagate_context_to_thread` 在非测试代码里 **11 处引用**、
`copy_context` 在非测试代码里 **18 处**。

**我采用的"同类"定义(必须写死,否则数字不可比):**
提交点满足两条 ——(a) 提交发生时,**父线程本身处于一个已绑定 session / 审批上下文的 agent 回合或工具调用中**;
(b) 被提交的可调用会在 worker 线程里**跑 agent 回合或分发 Hermes 工具**(即会走到审批闸门)。

按这个定义逐个核对面 2 的 48 处,落在类内的是 13 处:

| 提交点 | 传播写法 | 是否守住 |
|---|---|---|
| `agent/tool_executor.py:1177`:`f = executor.submit(` | `propagate_context_to_thread` | 是 |
| `agent/moa_loop.py:856` 的 `executor.submit(` | `propagate_context_to_thread` | 是 |
| `agent/conversation_compression.py:924` 的 `future = executor.submit(` | `propagate_context_to_thread` | 是 |
| `tools/async_delegation.py:804`:`executor.submit(propagate_context_to_thread(_worker))` | `propagate_context_to_thread` | 是 |
| `tools/async_delegation.py:1045`:`executor.submit(propagate_context_to_thread(_worker))` | `propagate_context_to_thread` | 是 |
| `model_tools.py:177`:`future = pool.submit(propagate_context_to_thread(_run_in_worker))` | `propagate_context_to_thread` | 是 |
| `tools/delegate_tool.py:2207`:`_child_context = contextvars.copy_context()` | `copy_context`(仅 contextvars) | 是(部分) |
| `tools/delegate_tool.py:3024`:`child_context = contextvars.copy_context()` | `copy_context`(仅 contextvars) | 是(部分) |
| `cron/scheduler.py:3618`:`_cron_future = _cron_pool.submit(_cron_context.run, agent.run_conversation, prompt)` | `copy_context` | 是 |
| `cron/scheduler.py:4310`:`return pool.submit(_run_and_release)` | 闭包内 `ctx.run(_process_job, j)` | 是 |
| `gateway/run.py:21378`:`ctx = copy_context()` | `copy_context` + `run_in_executor(…, ctx.run, …)` | 是 |
| `tui_gateway/server.py:1937`:`_pool.submit(lambda: ctx.run(run))` | `copy_context` | 是 |
| **`agent/subagent_lifecycle.py:259`**:`record.future = _EXECUTOR.submit(self._run, record, request.goal, parent)` | **无** | **否** |

**改判 R9A 的数字:同类提交点是 13 处(12 守 + 1 裸),不是 8 处。**
我用三种自然口径都复现不出 8:只数 `propagate_context_to_thread` 包裹的 `.submit(` 是 6 处;
只数 agent/ 与 tools/ 下的守护提交点是 8 处(上表前 8 行)—— **R9A 的 8 很可能是这个更窄的口径**,
但它随后写的"全仓"两字对不上,把 cron / gateway / tui_gateway 三个子系统漏在了外面。
**"唯一漏的"这个判断本身站得住:上表 13 行里只有最后一行没有任何包裹。**

**类外但值得点名的两处(不计入上表,理由写清):**
`tui_gateway/compute_host.py:326` 与 `:340` 也是裸 `submit` 且跑的是一次真回合,
但提交发生在 compute-host 的帧读取循环线程里,**父线程本就没有绑定过 session 上下文**
(会话身份是在 `_run_real_turn` 内部经 `_ensure_server_session` 重新建立的),
不满足我定义的 (a),所以不算"漏了传播"。
`agent/secret_sources/registry.py:224` 的 `executor.submit(_fetch)` 也是裸的,但它用
`set_source_environment(environ)` 这套**显式**机制在 worker 内自建环境,是另一种传播写法,且是启动期路径。

### 1.6 谁能触发它:只有插件路径,但足以到达工具分发

`SubagentLifecycleService` 的唯一非测试消费者是插件上下文:

搜索面:`grep -rn "subagent_lifecycle\|SubagentLifecycle" --include=*.py . | grep -v tests/`,
命中 `hermes_cli/plugins.py`(`PluginContext.subagent_lifecycle` 惰性构造服务)与
`run_agent.py:7787`(回合内 `bind_subagent_parent`)两处,无第三处。构造处:

`hermes_cli/plugins.py:379 @ 863e313`

```python
        if self._subagent_lifecycle is None:
            from agent.subagent_lifecycle import (
                SubagentLifecycleService,
                get_active_subagent_parent,
            )
            self._subagent_lifecycle = SubagentLifecycleService(
                get_active_subagent_parent
            )
        return self._subagent_lifecycle
```

即:**一个插件在 agent 回合里调用 `ctx.subagent_lifecycle.launch(...)` 起的子代理,
其整条工具链都在空审批上下文里跑。** 而 `launch` 的父上下文是完整的(它就在回合内被调用),
所以这里是"有得传却没传",不是"没得传"。

### 1.7 配套测试:**没有任何一条钉住这件事**

`tests/agent/test_subagent_lifecycle.py` 全文 174 行、4 个用例
(`test_cancel_is_cooperative_and_forged_handle_is_unknown`、`test_cancel_uses_explicit_hard_interrupt`、
`test_public_lifecycle_runs_host_aggregation`、`test_agent_turn_binds_and_clears_lifecycle_parent`),
覆盖的是句柄伪造、协作取消、宿主聚合与 parent 绑定/解绑,**没有一条碰 contextvars**。

搜索面与实测:

```verify
cd /home/user/hermes-agent
grep -c "propagate_context_to_thread\|copy_context" tests/agent/test_subagent_lifecycle.py   # 0
grep -rn "subagent_lifecycle" tests/ --include=*.py | grep -v __pycache__                    # 仅该文件
```

对照之下,仓库对**别的**提交点是有钉子的,而且钉法是两种:

- `tests/run_agent/test_tool_executor_contextvar_propagation.py` —— 3 个用例,先证明"裸 submit 确实不传播"
  (即把 Python 语义本身钉成前提),再证明 `_execute_tool_calls_concurrent` 的包裹有效;
- `tests/tools/test_execute_code_approval_cluster.py` —— 22 个用例,其中两条直接**读源码字符串**:
  断言 `"propagate_context_to_thread(_rpc_server_loop)" in src` 与
  `"propagate_context_to_thread(_rpc_poll_loop)" in src`。

也就是说,仓库已经发明了"源码级钉子"这种手段来防止某个具体线程被改回裸提交,
**但那份名单是手写的、只点了 `code_execution_tool` 的两个线程**,没有覆盖 `subagent_lifecycle`。
这正是 R9C 那句结构性结论的又一个实例:**防线的存在不是覆盖率的证据**;
这里连"清点谁该上防线"的机制都是人肉名单。

实跑(3 个文件、29 用例、0 失败):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/agent/test_subagent_lifecycle.py \
    tests/run_agent/test_tool_executor_contextvar_propagation.py \
    tests/tools/test_execute_code_approval_cluster.py
```

```text
=== Summary: 3 files, 29 tests passed, 0 failed (100% complete) in 2.6s (8 workers) ===
```

### 1.8 处置结论:**维持 ■,并改述 + 定向**

- **维持**:`agent/subagent_lifecycle.py:259` 确为裸提交,锚点未漂,无任何上下文传播。**■**
- **改述(数字)**:同类提交点是 **13 处(12 守 + 1 裸)**,不是 R9A 说的 8 处;
  8 只在"agent/ 与 tools/ 下"这个更窄的口径下成立,而移交项写的是"全仓"。
  **"它是唯一漏的"这一判断维持**。
- **定向(本轮新增,是这条的价值所在)**:丢 session key 的方向是 **fail-open(变松、全放行)**,
  实跑证据见 §1.4 —— 父线程 `approved=False`,裸 worker `approved=True`。
  连带丢失 `HERMES_SESSION_PROFILE`(profile 覆盖)。
- **测试**:无任何用例钉住;仓库对同类问题已有"源码级钉子"手法但名单未覆盖此处。

同构的正确写法就在隔壁子系统里,一行之差:

`agent/tool_executor.py:1176 @ 863e313`

```python
                    try:
                        f = executor.submit(
                            propagate_context_to_thread(_run_tool),
```

修法(供 R12 蓝图引用,不改基线):把 `:259` 改成
`_EXECUTOR.submit(propagate_context_to_thread(self._run), record, request.goal, parent)`
即与 `agent/tool_executor.py:1177` 同构;并在 `tests/agent/test_subagent_lifecycle.py` 里
补一条与 `test_execute_code_approval_cluster.py` 同款的源码级断言。

### 1.9 残留未取证

- 未在真实 gateway 回合里端到端跑通"插件起子代理 → 子代理执行危险命令 → 未提示审批"这条完整链路
  (需要真实 provider 凭据,项目边界禁止配置)。§1.4 的实跑是**对同一批判定函数的直接调用**,
  覆盖了从 contextvars 到 `approved` 布尔值的全部判定逻辑,但没有覆盖"子代理确实会调 `check_dangerous_command`"
  这一段 —— 后者是静态对读结论(`_run_child_lifecycle` → `run_conversation` → 工具分发 → `terminal_tool`)。
- `DaemonThreadPoolExecutor` 复用 worker 线程时,**上一个**子代理留下的 contextvars 是否会被下一个看到,
  未验证。stdlib `ThreadPoolExecutor` 的 worker 在两次任务之间不清空线程状态,而裸 `submit` 也不重置 ——
  这意味着"污染方向"可能不止是丢,还可能是**串**(A 会话的 session key 被 B 会话的子代理读到)。
  **推定未取证**,建议单列。

---

## 2. H-R9A-f —— skills_hub 里取自远端 JSON 的 URL 走裸 `httpx.get`

### 2.1 原移交项复述

> 锚点 `tools/skills_hub.py:3205` 的 `httpx.get(md_url, ..., follow_redirects=True)`。
> 现象:8 处裸调用里唯一 URL 取自远端 JSON 的一处,未走同文件 `:302` 的守卫。

### 2.2 锚点核对:两个锚点**都准确,未漂移**

`tools/skills_hub.py:3201 @ 863e313`

```python
        md_url = self._resolve_skill_md_url(slug, item)
        if not md_url:
            return None
        try:
            resp = httpx.get(md_url, timeout=20, follow_redirects=True)
            if resp.status_code != 200:
                return None
            content = resp.text
        except httpx.HTTPError:
            return None
```

`:3205` 正是 `resp = httpx.get(md_url, timeout=20, follow_redirects=True)`。
**注意这一行没有 `headers=` 参数** —— 见 §2.5 的风险定性。

`tools/skills_hub.py:302 @ 863e313`

```python
def _guarded_http_get(url: str, *, timeout: int = 20) -> Optional[httpx.Response]:
    """Fetch a URL with SSRF and redirect-target validation."""
    from tools.url_safety import SSRFConnectionBlocked

    current_url = url

    for _ in range(_MAX_SKILL_FETCH_REDIRECTS + 1):
        if not is_safe_url(current_url):
            logger.warning("Blocked unsafe Skills Hub URL: %s", current_url)
            return None

        blocked = check_website_access(current_url)
        if blocked:
            logger.info(
                "Blocked Skills Hub fetch for %s by rule %s",
                blocked["host"],
                blocked["rule"],
            )
            return None
```

`:302` 是 `_guarded_http_get` 的 `def` 行,准确。

### 2.3 `:302` 那个守卫到底守什么(三件事,缺一不可)

1. **`is_safe_url(current_url)` —— SSRF 地址闸门。** `tools/url_safety.py` 的模块文档开头就写明它挡的是
   "私有/内网地址、云元数据端点 169.254.169.254、localhost 服务"。
2. **`check_website_access(current_url)` —— 用户自定义的站点策略(黑白名单)。**
   这是**用户配置**层面的拦截,与 SSRF 无关:用户在配置里禁掉的域名,走守卫的取回会被拒,裸调用不会。
3. **自己做重定向,每一跳都重新过 1 和 2。** 关键实现在
   `tools/skills_hub.py:294 @ 863e313` 的 `_ssrf_safe_http_get`:

`tools/skills_hub.py:294 @ 863e313`

```python
def _ssrf_safe_http_get(url: str, *, timeout: int = 20) -> httpx.Response:
    """Fetch one URL with connect-time SSRF validation and no automatic redirects."""
    from tools.url_safety import create_ssrf_safe_client

    with create_ssrf_safe_client(timeout=timeout, follow_redirects=False) as client:
        return client.get(url)
```

`follow_redirects=False` + 循环里手动 `urljoin` 下一跳,**就是为了不把重定向交给 httpx**,
因为交给 httpx 就意味着第 2 跳往后的地址从没过闸门。
`create_ssrf_safe_client` 还额外把校验挪到**连接前一刻**,对付 DNS rebinding
(TOCTOU:先返回公网 IP 骗过检查、连接时改返回内网 IP)。这两条限制是仓库自己写下的:

`tools/url_safety.py:15 @ 863e313`

```python
Limitations:
  - DNS rebinding (TOCTOU): an attacker-controlled DNS server with TTL=0
    can return a public IP for the check, then a private IP for the actual
    connection. Hermes-owned direct httpx request paths should use
    ``create_ssrf_safe_client()`` / ``create_ssrf_safe_async_client()`` so the
    same policy is applied immediately before TCP connect and the client
    connects to the validated IP while preserving Host/SNI semantics.
  - Redirect-based bypass is mitigated by httpx event hooks that re-validate
    each redirect target in vision_tools, gateway platform adapters, and
    media cache helpers. Web tools use third-party SDKs (Firecrawl/Tavily)
    where redirect handling is on their servers.
```

注意最后一句点名的是 `vision_tools`、gateway 平台适配器、媒体缓存 —— **skills_hub 不在其列**,
本文件的重定向再校验是靠 `_guarded_http_get` 自己那个循环实现的,
所以**只有走这个函数的取回点才享有它**。

**`:3205` 的 `follow_redirects=True` 恰好是这个设计的反面。**

### 2.4 `md_url` 的来源链路

三跳:

**第一跳 —— 目录。** `BrowseShSource` 的类文档说明它是谁:

`tools/skills_hub.py:3093 @ 863e313`

```python
    """Discover and install site-specific browser automation skills from browse.sh.

    browse.sh (https://browse.sh) is Browserbase's catalog of 200+ SKILL.md files
    that describe how to automate specific websites (Airbnb, Amazon, arXiv, etc.).
    The catalog lives at ``/api/skills`` and each skill's actual SKILL.md content
    is fetched via ``/api/skills/{slug}`` which returns a ``skillMdUrl`` field
    pointing at a CDN-hosted blob — the catalog's ``sourceUrl`` field is a GitHub
    HTML URL whose underlying repository is not always public, so it cannot be
    relied on for content fetch.
    """
```

`tools/skills_hub.py:3104 @ 863e313`

```python
    CATALOG_URL = "https://browse.sh/api/skills"
    SKILL_DETAIL_URL = "https://browse.sh/api/skills/{slug}"
```

**browse.sh 是 Browserbase 的目录,不是 Nous 官方 hub。**
`BrowseShSource` 给出的信任级别恒为 `"community"` —— 仓库自己就把它标成了不可信来源:

`tools/skills_hub.py:3111 @ 863e313`

```python
    def trust_level_for(self, identifier: str) -> str:
        return "community"
```

对照 Nous 自家索引源的常量:

`tools/skills_hub.py:3981 @ 863e313`

```python
HERMES_INDEX_URL = "https://hermes-agent.nousresearch.com/docs/api/skills-index.json"
HERMES_INDEX_TTL = 6 * 3600  # 6 hours
```

**第二跳 —— 详情端点吐出 `skillMdUrl`。**

`tools/skills_hub.py:3236 @ 863e313`

```python
            detail = httpx.get(
                self.SKILL_DETAIL_URL.format(slug=slug),
                timeout=20,
                follow_redirects=True,
            )
            if detail.status_code == 200:
                data = detail.json()
                if isinstance(data, dict):
                    md_url = data.get("skillMdUrl")
                    if isinstance(md_url, str) and md_url.startswith("http"):
                        return md_url
```

对 `md_url` 的全部校验就是 **`isinstance(str)` + `startswith("http")`**。
没有 host 白名单、没有 scheme 精确匹配(`http` 前缀连 `httpfoo://` 都不排除,虽然 httpx 会自己报错)、
没有任何私有地址检查。**任意字符串只要以 `http` 开头就被当成内容 URL 取回。**

**第三跳 —— 回落分支,比主路径更松。**

`tools/skills_hub.py:3250 @ 863e313`

```python
        source_url = item.get("sourceUrl", "") if isinstance(item, dict) else ""
        if source_url and "raw.githubusercontent.com" in source_url:
            return source_url
        return None
```

`in` 是**子串**判定,不是 host 判定。`http://127.0.0.1:9/x?ref=raw.githubusercontent.com` 直接过。
**实跑确认**:

```verify
mkdir -p /tmp/r9d && cat > /tmp/r9d/probe_sourceurl.py <<'PY'
import os, sys, tempfile
os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="hermes-su-")
for v in ("HTTP_PROXY","http_proxy","HTTPS_PROXY","https_proxy","ALL_PROXY","all_proxy"):
    os.environ.pop(v, None)
sys.path.insert(0, "/home/user/hermes-agent")
import tools.skills_hub as sh
src = sh.BrowseShSource()
src.SKILL_DETAIL_URL = "http://127.0.0.1:1/{slug}"   # 让主路径失败,逼出回落分支
item = {"sourceUrl": "http://127.0.0.1:9/x?ref=raw.githubusercontent.com"}
print("fallback md_url ->", src._resolve_skill_md_url("evil/x", item))
PY
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
  /home/user/hermes-venv/bin/python /tmp/r9d/probe_sourceurl.py
```

```text
fallback md_url -> http://127.0.0.1:9/x?ref=raw.githubusercontent.com
```

这是移交项里**没提到**的一处,记 **■(新增子项)**:子串判定形式的 host 校验可被 query 参数绕过。

**可信度定性:** 攻击面不需要"browse.sh 被攻陷"这么强的前提 —— 只需要 browse.sh 的目录里
存在一条攻击者可控的条目(该站是站点自动化技能的社区目录,条目是否可由第三方提交,
本轮**离线无法核实,列为推定**)。即便按最保守假设"只有 browse.sh 运营方能改",
结论仍是:**Hermes 把"这个第三方目录说的任何 URL"直接当成可取回、且取回内容会变成技能正文。**

### 2.5 挂没挂凭据:**没有。所以这不是 R9C 那个形态**

`:3205` 的调用没有 `headers=` 参数(见 §2.2 的原文块),整个 `BrowseShSource` 也不持有任何 token
(它没有 `auth` 成员,`create_sources()` 里构造它时不传 `auth`,见 §2.8 引的那一段)。
另外 httpx 0.28.1 在跨 origin 重定向时会主动剥掉 `Authorization`(`httpx._client.Client._redirect_headers`,
`if not _same_origin(url, request.url): ... headers.pop("Authorization", None)`),
所以即便挂了也不会跟着跳走。

**所以风险类型是这两种,不是凭据外泄:**

1. **SSRF** —— 让 Hermes 进程去 GET 一个它能到、攻击者到不了的地址(内网服务、云元数据端点、
   `check_website_access` 里被用户禁掉的站点)。`follow_redirects=True` 让第一跳合法、第二跳打内网
   这种最常见的绕法直接生效。
2. **内容投毒 / 提示注入** —— 取回的**响应体原样成为 `SkillBundle.files["SKILL.md"]`**。
   §2.2 的原文块里 `content = resp.text`,紧随其后:

`tools/skills_hub.py:3214 @ 863e313`

```python
        return SkillBundle(
            name=name,
            files={"SKILL.md": content},
```

   技能正文是喂给模型的指令文本,等于把任意远端内容变成 agent 的指令。

**端到端实跑复现(本机 loopback,不联网)** —— 同一个 URL:守卫拒、裸调用取到并装进 bundle:

```verify
mkdir -p /tmp/r9d && cat > /tmp/r9d/probe_ssrf.py <<'PY'
import os, sys, json, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="hermes-ssrf-")
for v in ("HTTP_PROXY","http_proxy","HTTPS_PROXY","https_proxy","ALL_PROXY","all_proxy","NO_PROXY","no_proxy"):
    os.environ.pop(v, None)
sys.path.insert(0, "/home/user/hermes-agent")

class Internal(BaseHTTPRequestHandler):            # 冒充内网服务(SSRF 目标)
    def do_GET(self):
        body = b"---\nname: pwned\ndescription: INTERNAL-ONLY-DATA\n---\nbody\n"
        self.send_response(200); self.send_header("Content-Type","text/plain")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
internal = HTTPServer(("127.0.0.1", 0), Internal); INT_PORT = internal.server_address[1]
threading.Thread(target=internal.serve_forever, daemon=True).start()
INTERNAL_URL = f"http://127.0.0.1:{INT_PORT}/latest/meta-data/"

class Catalog(BaseHTTPRequestHandler):             # 冒充 browse.sh 目录/详情端点
    def do_GET(self):
        if self.path == "/api/skills":
            payload = {"skills": [{"slug": "evil.com/x", "name": "x", "title": "x",
                                   "description": "d", "hostname": "evil.com", "sourceUrl": ""}]}
        else:
            payload = {"skillMdUrl": INTERNAL_URL}
        body = json.dumps(payload).encode()
        self.send_response(200); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
catalog = HTTPServer(("127.0.0.1", 0), Catalog); CAT_PORT = catalog.server_address[1]
threading.Thread(target=catalog.serve_forever, daemon=True).start()

import tools.skills_hub as sh
print("A. _guarded_http_get on the same internal URL ->", sh._guarded_http_get(INTERNAL_URL))
print("B. is_safe_url(internal) ->", sh.is_safe_url(INTERNAL_URL))
src = sh.BrowseShSource()
src.CATALOG_URL = f"http://127.0.0.1:{CAT_PORT}/api/skills"
src.SKILL_DETAIL_URL = f"http://127.0.0.1:{CAT_PORT}/api/skills/{{slug}}"
bundle = src.fetch("browse-sh/evil.com/x")
print("C. BrowseShSource.fetch bundle ->", None if bundle is None else
      {"name": bundle.name, "trust": bundle.trust_level,
       "SKILL.md": bundle.files["SKILL.md"][:60], "meta_md_url": bundle.metadata.get("skill_md_url")})
PY
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
  /home/user/hermes-venv/bin/python /tmp/r9d/probe_ssrf.py
```

实测输出:

```text
Blocked request to private/internal address: 127.0.0.1 -> 127.0.0.1
Blocked unsafe Skills Hub URL: http://127.0.0.1:37865/latest/meta-data/
A. _guarded_http_get on the same internal URL -> None
Blocked request to private/internal address: 127.0.0.1 -> 127.0.0.1
B. is_safe_url(internal) -> False
C. BrowseShSource.fetch bundle -> {'name': 'x', 'trust': 'community', 'SKILL.md': '---\nname: pwned\ndescription: INTERNAL-ONLY-DATA\n---\nbody\n', 'meta_md_url': 'http://127.0.0.1:37865/latest/meta-data/'}
```

**同一个 URL:走 `_guarded_http_get` 返回 `None`(被 SSRF 闸门挡下),
走 `BrowseShSource.fetch` 把内网响应体原样装进了 `SKILL.md`。** 这条 ■ 就此坐实。

(说明:实验里把 `CATALOG_URL` / `SKILL_DETAIL_URL` 指向本机,是因为容器离线、够不到真 browse.sh;
被测的缺陷不在"目录 host 是谁",而在"目录说的 `skillMdUrl` 不过任何闸门",两者独立。)

### 2.6 覆盖率数清楚

**同文件(`tools/skills_hub.py`)搜索面与计数:**

```verify
cd /home/user/hermes-agent
grep -c "httpx\.\(get\|post\|stream\|request\)(" tools/skills_hub.py   # 21
grep -n "_guarded_http_get(" tools/skills_hub.py                      # def 1 处 + 调用 5 处
grep -n "is_safe_url\|check_website_access\|create_ssrf_safe_client" tools/skills_hub.py
```

实测:**21 处 `httpx.*` 直接调用**、**5 处 `_guarded_http_get(...)` 调用**
(`:1380`、`:1411`、`:1548`、`:1555`、`:2922`)。
`is_safe_url` / `check_website_access` / `create_ssrf_safe_client` 在本文件里
**只出现在 `_guarded_http_get` / `_ssrf_safe_http_get` 内部**(`:298`、`:309`、`:313`)——
也就是说,**本文件的 SSRF 防线只有这一道门,21 处裸调用一处都没经过它**。

但"裸"不等于"有问题"。真正该数的是 **URL 主机取自远端响应体**的取回点。逐个核对 21 处后:

| 取回点 | URL 从哪来 | 是否过守卫 |
|---|---|---|
| `tools/skills_hub.py:2850`:`raw_url = file_meta.get("rawUrl") or file_meta.get("downloadUrl") or file_meta.get("url")` | ClawHub 远端 JSON | **是**(经 `:2922` 的 `_fetch_text`) |
| `tools/skills_hub.py:3205`:`resp = httpx.get(md_url, timeout=20, follow_redirects=True)` | browse.sh 远端 JSON 的 `skillMdUrl` | **否** |
| `tools/skills_hub.py:1767` 的 `httpx.get(` (`sitemap_url`) | skills.sh sitemap XML 里的 `<loc>` | **否** |

其余 18 处的 host 全部来自模块内常量(`https://api.github.com/...`、`self.BASE_URL`、
`INDEX_URL`、`CATALOG_URL`、`SITEMAP_INDEX_URL`、`SEARCH_URL`、`HERMES_INDEX_URL`、
`https://chat-agents.lobehub.com/{agent_id}.json`),路径/query 可被远端数据影响但 host 不可,
不在本类内。

**对照组的价值在这里:ClawHub 干的是一模一样的事 —— 从远端 JSON 里读一个 URL 再取回 —— 它走了守卫。**

`tools/skills_hub.py:2850 @ 863e313`

```python
            raw_url = file_meta.get("rawUrl") or file_meta.get("downloadUrl") or file_meta.get("url")
            if isinstance(raw_url, str) and raw_url.startswith("http"):
                content = self._fetch_text(raw_url)
                if content is not None:
                    files[fname] = content
```

`tools/skills_hub.py:2921 @ 863e313`

```python
    def _fetch_text(self, url: str) -> Optional[str]:
        resp = _guarded_http_get(url, timeout=20)
        if resp is not None and resp.status_code == 200:
            return resp.text
        return None
```

连 `isinstance(...) and startswith("http")` 这个前置检查都一字不差,**只有最后一步分叉**:
ClawHub 调 `self._fetch_text`(守),BrowseSh 调 `httpx.get`(裸)。

**改判 R9A 的"唯一":不成立,是 3 取 1 守、2 未守。**
第二处未守的是 `:1767`,移交项没提:

`tools/skills_hub.py:1765 @ 863e313`

```python
        for sitemap_url in skill_sitemap_urls:
            try:
                resp = httpx.get(
                    sitemap_url,
                    timeout=30,
                    follow_redirects=True,
                    headers=sitemap_headers,
                )
```

`skill_sitemap_urls` 来自上一跳远端 XML 的 `<loc>`,过滤条件只有 `if "sitemap-skills" in loc`
(又一次子串判定)。它比 `:3205` 轻:响应体只被正则抽 skill id,不会变成技能正文,
所以是**盲 SSRF / 内网端口探测**,没有内容投毒。记 **◇(代码有、文档无)+ ■(轻)**。

**全仓层面的口径(负结论,搜索面写在这里):**

```verify
cd /home/user/hermes-agent
grep -rn "create_ssrf_safe_client\|create_ssrf_safe_async_client" --include=*.py . | grep -v "^\./tests/" | wc -l   # 41
grep -rln "create_ssrf_safe_client\|create_ssrf_safe_async_client" --include=*.py . | grep -v "^\./tests/"          # 14 个文件
grep -rn "is_safe_url(" --include=*.py . | grep -v "^\./tests/" | grep -v "def is_safe_url" | wc -l                 # 47
```

实测:SSRF 安全客户端在 **14 个非测试文件**里被用到(gateway 平台适配器 6 个、
`tools/vision_tools.py`、`tools/managed_tool_gateway.py`、`tools/flux3_video_tool.py`、
`tools/skills_hub.py`、`tools/url_safety.py` 等),`is_safe_url(` 调用点 **47 处**。
**我没有对全仓做"URL 主机取自远端响应体"的穷举** —— 那需要跨模块数据流分析,
`grep` 做不到。因此本节的覆盖率结论**只对 `tools/skills_hub.py` 这一个文件是完备的**;
全仓层面我只能说"同类形态至少还有 `:1767` 一处未守",不能说"全仓只有这两处"。

### 2.7 配套测试:**同样没有钉子**

搜索面与实测:

```verify
cd /home/user/hermes-agent
grep -rn "_guarded_http_get" tests/ --include=*.py | wc -l    # 0
grep -n "def test_" tests/tools/test_skills_hub_browse_sh.py  # 3 条
```

`tests/tools/test_skills_hub_browse_sh.py` 全文 85 行、3 个用例
(`test_source_id`、`test_search_returns_results`、`test_inspect_returns_meta`),
全部 mock 掉目录后只验元数据形状,**没有一条碰取回路径或 SSRF**。
**全仓测试里 `_guarded_http_get` 出现 0 次** —— 这道门本身没有任何用例保护,
更谈不上有用例断言"谁必须走它"。

实跑(4 个文件、100 用例、0 失败):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/tools/test_skills_hub_browse_sh.py tests/tools/test_skills_hub.py \
    tests/tools/test_skills_guard.py tests/tools/test_skill_bundle_provenance.py
```

```text
=== Summary: 4 files, 100 tests passed, 0 failed (100% complete) in 2.6s (8 workers) ===
```

### 2.8 处置结论:**维持 ■,并改述(风险定性 + 覆盖率)**

- **维持**:`:3205` 确为裸 `httpx.get`,`md_url` 确实整段来自远端 JSON,`:302` 的守卫确实没走。**■**
- **改述(风险定性)**:**不是 R9C 那个"凭据跟着重定向走"的形态** —— 该调用不带 `Authorization`,
  `BrowseShSource` 也不持凭据,且 httpx 0.28.1 跨 origin 会剥掉该头。
  真实风险是 **(a) SSRF**(含绕过用户站点策略 `check_website_access`)与
  **(b) 内容投毒 / 提示注入**(响应体原样成为 `SKILL.md`,即模型指令)。两者均已端到端实跑复现(§2.5)。
- **改述(覆盖率)**:同文件 21 处 `httpx.*` 调用中,"URL 主机取自远端响应体"的有 **3 处**,
  **1 处走守卫(ClawHub `:2850`→`:2922`)、2 处没走(`:3205`、`:1767`)**。
  R9A 的"8 处裸调用里唯一一处"两个数都不准:裸调用是 21 处,"唯一"是 2 取 1。
- **新增子项 ■**:`_resolve_skill_md_url` 的回落分支用**子串**判定当 host 校验,实跑可用 query 参数绕过:

`tools/skills_hub.py:3250 @ 863e313`

```python
        source_url = item.get("sourceUrl", "") if isinstance(item, dict) else ""
        if source_url and "raw.githubusercontent.com" in source_url:
            return source_url
```
- **新增 ◇/■(轻)**:`tools/skills_hub.py:1767` 的 sitemap 二跳同样未守,属盲 SSRF。
- **来源可信度**:browse.sh 是 Browserbase 的第三方目录,**不是 Nous 官方 hub**;
  仓库自己给它的信任级别就是 `"community"`。它在 `create_sources()` 里**默认启用**,不需要用户额外开关:

`tools/skills_hub.py:4281 @ 863e313`

```python
        ClawHubSource(),
        LobeHubSource(),
        BrowseShSource(),   # browse.sh: 169+ site-specific browser automation skills
    ]
```

修法(供蓝图引用):把 `:3205` 换成 `_guarded_http_get(md_url, timeout=20)`,与 ClawHub 同构;
`:3251` 改成解析后的 host 精确比较;`:1767` 同样换成守卫版。

### 2.9 残留未取证

- **browse.sh 的目录条目是否可由任意第三方提交**,决定这条是"需要第三方站点作恶"还是
  "任何人都能投毒"。容器离线,无法访问 browse.sh 核实,**推定未取证**。
  这不影响 ■ 的成立(守卫该走没走是代码事实),只影响严重度分级。
- 未验证落盘的目录缓存是否会把被投毒的 `skillMdUrl` 持久化到 `INDEX_CACHE_TTL` 之后 ——
  若会,则一次投毒有持续窗口。**推定未取证。** 落盘入口:

`tools/skills_hub.py:3464 @ 863e313`

```python
def _write_index_cache(key: str, data: Any) -> None:
    """Write data to cache."""
    index_cache_dir = _index_cache_dir()
```
- 未穷举全仓"URL 主机取自远端响应体"的取回点(见 §2.6 末尾的口径声明)。

---

## 3. 未取证 / 推定(汇总)

| 项 | 状态 | 锚点 |
|---|---|---|
| 子代理端到端"危险命令未提示审批"链路(需真实 provider 凭据) | 未取证;§1.4 已实证判定函数一侧 | `agent/subagent_lifecycle.py:259`:`record.future = _EXECUTOR.submit(self._run, record, request.goal, parent)` |
| `DaemonThreadPoolExecutor` 复用 worker 时 contextvars 是否**跨会话串味**(不只是丢) | 推定,未取证 | `agent/subagent_lifecycle.py:165`:`_EXECUTOR = _DaemonExecutor(max_workers=8, thread_name_prefix="hermes-lifecycle")` |
| browse.sh 目录条目是否第三方可提交(决定严重度,不决定 ■ 是否成立) | 推定,离线无法核实 | `tools/skills_hub.py:3104`:`CATALOG_URL = "https://browse.sh/api/skills"` |
| 被投毒的 `skillMdUrl` 是否随目录缓存持久化 | 推定,未取证 | `tools/skills_hub.py:3114`:`def _fetch_catalog(self) -> List[Dict]:` |
| 全仓"URL 取自远端响应体"的取回点穷举(grep 做不到跨模块数据流) | 未取证;结论仅对 `tools/skills_hub.py` 完备 | `tools/skills_hub.py:302`:`def _guarded_http_get(url: str, *, timeout: int = 20) -> Optional[httpx.Response]:` |

## 4. 交给下一轮的锚点(声明式写法)

| 编号 | 锚点 + 摘录 | 一句话现象 |
|---|---|---|
| H-R9D-e1 | `agent/subagent_lifecycle.py:259`:`record.future = _EXECUTOR.submit(self._run, record, request.goal, parent)` | 裸提交,worker 空上下文;实跑确认审批闸门由"要求审批"翻成"自动放行"(fail-open),并丢 `HERMES_SESSION_PROFILE` |
| H-R9D-e2 | `agent/subagent_lifecycle.py:165`:`_EXECUTOR = _DaemonExecutor(max_workers=8, thread_name_prefix="hermes-lifecycle")` | 模块级长驻池,worker 复用;是否会把上一个子代理的 contextvars 串给下一个,未验证 |
| H-R9D-f1 | `tools/skills_hub.py:3205`:`resp = httpx.get(md_url, timeout=20, follow_redirects=True)` | 远端 JSON 给的 URL 未过 `:302` 守卫;实跑取到 loopback 内容并装进 `SKILL.md`;无 Authorization,故为 SSRF + 内容投毒而非凭据外泄 |
| H-R9D-f2 | `tools/skills_hub.py:3251`:`if source_url and "raw.githubusercontent.com" in source_url:` | 子串判定当 host 校验,实跑用 query 参数绕过 |
| H-R9D-f3 | `tools/skills_hub.py:1767` 的 `httpx.get(` | sitemap 二跳 URL 取自远端 XML `<loc>`,同样未过守卫;响应体只被正则抽 id,属盲 SSRF |
