# r9d-91 · 移交项定案(主线独立取证)

> 主线产出。溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于块前。
> **本篇的取证全部由主线自己跑**,不转述子代理;子代理的取证书在
> `notes/r9d-90-handover-*.md`,与本篇对读的结果记在各节的「与子代理取证的对读」。
> 本轮需定案 7 条:R9A 移交归 R9D 的 5 条(H-R9A-b / c / e / f / g)+ R9C 的 2 条(H-R9C-a / b)。
> **每条都给处置结论,不写「续转」了事。**

---

## 1. H-R9A-b · 看板收尸的 `waitpid(-1)` 会替别人收尸

### 1.1 原移交项(R9A 报告 §11)

> **H-R9A-b** | R9D | `hermes_cli/kanban_db.py:6941` 的 `os.waitpid(-1, os.WNOHANG)` |
> 全仓唯一一处 `waitpid(-1)`,跑在网关工作线程上,会替别处的后台 `Popen` 收尸使属主拿到错误退出码;
> asyncio 侧三次实测未复现,不主张

### 1.2 锚点核对:准

`hermes_cli/kanban_db.py:6937-6947 @ 863e313`

```python
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
```

`:6941` 正是那一行 `pid, status = os.waitpid(-1, os.WNOHANG)`,外层函数是 `reap_worker_zombies`。

「全仓唯一一处」复核(搜索面 = 基线全部 `.py`,含测试;`--include=*.py` 递归全仓):

```verify
cd /home/user/hermes-agent && grep -rn "waitpid" --include=*.py . | grep -v "^./tests/"
```

```text
./scripts/profile-tui.py:458:                pid_done, _ = os.waitpid(pid, os.WNOHANG)
./scripts/profile-tui.py:464:                os.waitpid(pid, 0)
./hermes_cli/kanban_db.py:6941:                    pid, status = os.waitpid(-1, os.WNOHANG)
```

另两处都是 `waitpid(pid, ...)`(**指名收自己的**),故「唯一一处 `waitpid(-1)`」成立。

### 1.3 R9A 为什么没复现:它测的那一侧结构上收不到

R9A 记的是「asyncio 侧三次实测未复现,不主张」。**本轮判定 R9A 测错了地方**,理由是
CPython 两条路径的收尸时机根本不同:

- **asyncio 子进程**:`ThreadedChildWatcher` 为**每个**子进程起一条线程,**已经阻塞在**
  `waitpid(pid, 0)` 上。子进程一退出,这条线程立刻被唤醒收走——抢收者几乎不可能赢。
- **普通 `subprocess.Popen`**:**没有**任何线程在等它。子进程退出后一直是僵尸,
  **直到属主自己调 `.poll()` / `.wait()`**。这中间的窗口对抢收者完全敞开。

三组对照实测(**用的是基线里那个真函数**,不是等价重写):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python \
    data/r9d/probes/h_r9a_b_repro.py
```

```text
收尸者 = 真实 reap_worker_zombies()
[组1 对照] 无人抢,     Popen.wait() = 42   (真实退出码应为 42)
[组2 实验] 抢走 1 个,Popen.wait() = 0   (被抢后属主看到的退出码)
[组3 asyncio] 抢到 0 个,proc.wait() = 42   (ThreadedChildWatcher 在场)
```

**组 3 正是 R9A 测的那一侧。** 但这里要比初稿说得更准确——**初稿写"asyncio 侧结构上安全",
过强了,现予收紧**(依据是移交取证组 A 的独立实验,主线复跑后采信其结论):

| 测量 | 次数 | 被抢到几次 | `proc.wait()` 读数 |
|---|---|---|---|
| 主线本轮 | 8 | **0** | 全部 42 |
| 移交取证组 A | 5 | **1** | `[42, 255, 42, 42, 42]`,伴随 `Unknown child process pid ..., will report returncode 255` 日志 |

**这是两次不同的测量,读数不同,不得合并表述。** 合起来的正确结论是:
asyncio 侧的 watcher 线程**通常抢先**(主线 8 次全赢),但**并非结构上不可能被抢**;
而关键在于**被抢之后的表现**——CPython 在 asyncio 侧记 `returncode=255` **并打 warning**,
是一次**响亮的失败**;阻塞 `subprocess` 侧则静默记 **0**,是一次**被报成成功的失败**。

**所以 R9A 的方法错位不在于"asyncio 侧不可能出事",而在于:
它选的那一侧即使出事也会大声喊,因此最不可能在三次试跑里表现成一个需要主张的问题。
组 2 才是暴露面,退出码 42 变成 0,没有任何日志。**

失败方向是**最坏的那一种**:不是"报错",是**把失败报成成功**。机制在 CPython 的
`subprocess.Popen._try_wait` 里:`waitpid` 抛 `ChildProcessError` 时它把 `sts` 当 0 处理。

### 1.4 可达性:同进程、每 60 秒一次、且 `subprocess.run` 同样中招

收尸跑在**网关进程**的看板派发循环里,每 tick 一次:

`gateway/kanban_watchers.py:1423-1429 @ 863e313`

```python
        while self._running:
            try:
                # Reap zombie children before per-board work so a board DB
                # failure cannot block cleanup of unrelated workers.
                pids = await asyncio.to_thread(_kb.reap_worker_zombies)
                if pids:
                    logger.info(
```

`gateway/run.py:11490` 把它作为受监督任务起在网关进程里(`_spawn_supervised(self._kanban_dispatcher_watcher, ...)`),
默认 tick 间隔 60 秒(`kanban_watchers.py:1029` 的 `dispatch_interval_seconds`,下限 1.0 秒)。

**`subprocess.run()` 也中招**——这一条必须单独证,因为受害现场用的是 `run()` 而非裸 `Popen`:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python \
    data/r9d/probes/h_r9a_b_run_variant.py
```

```text
[组A 对照] 正常 subprocess.run().returncode      = 42
[组B 实验] 抢走 1 个后 run().returncode = 0

webhook_filters.py:279 的判据 'result.returncode != 0'(非零=拒绝该 webhook):
  对照组该判据 = True  -> 拒绝
  实验组该判据 = False  -> 放行(fail-open)
```

受害现场之一,同在网关进程内:

`gateway/platforms/webhook_filters.py:279-280 @ 863e313`

```python
        if result.returncode != 0:
            logger.info(
```

这行的语义是「过滤脚本返回非零 = 忽略这个 webhook」。退出码被抹成 0,**"拒绝"就变成"放行"**——
方向是 fail-open。

### 1.5 处置结论

**立 ■,推翻 R9A 的「不主张」。**

- **机制已实证**(用基线真函数):`Popen.wait()` 与 `subprocess.run().returncode` 都从 42 降级为 0,**且无任何日志**。
  (对照:asyncio 侧被抢到时记 255 并打 warning —— 同一个收尸动作,两条路径的失败**可见度**完全不同。)
- **可达性已实证**:收尸者与受害者同在网关进程,收尸每 60 秒一次。
- **后果方向已实证**:`webhook_filters.py:279` 的安全判据从"拒绝"翻成"放行"。
- **修法**:`reap_worker_zombies` 不该用 `waitpid(-1)`。它已经维护着 `_recent_worker_exits`
  这张 pid 表,应当**只收自己派发出去的 worker pid**(`waitpid(pid, WNOHANG)` 逐个收),
  而不是见僵尸就收。

**必须如实说清的限定(两条)**:

1. **组 2 / 组 B 的窗口是我主动制造的**,不是在真实时序下等到的。组 B 用 monkeypatch 在
   `run()` 内部 `wait()` 之前插入抢收,证明的是**降级机制**,不是"这个竞态在生产里多久触发一次"。
   真实触发概率取决于「子进程退出」与「60 秒一次的收尸 tick」的重合,**每次很低,但长期不封顶**。
2. **需要嵌入式看板派发器在跑**(网关且启用看板)。不跑看板的部署不受影响。

*R9A 写「asyncio 侧三次实测未复现,不主张」是一次**负结论关闭了调查**的标本——
恰好是 CLAUDE.md「负结论的成本」那条规矩要防的形状。它的搜索面(asyncio 子进程)
恰好是全部暴露面里**最不容易复现、且即使复现也会大声报错**的那个子集。*

*另一条移交取证组 A 提供、主线未独立取证的线索(照实标注强度)*:
`hermes_cli/web_server.py:4786` 的 `exit_code = proc.poll()` **形状完全吻合**
(被偷即得 0 并缓存进 `_ACTION_RESULTS`),但**它是否与看板收尸器同进程运行未取证**。
该残留可在本仓库内消解(查网关是否在进程内起 dashboard),本轮未做。

---

## 2. H-R9A-c · 改文件工具白名单只有两个名字

### 2.1 原移交项(R9A 报告 §11)

> **H-R9A-c** | R9D | `agent/tool_result_classification.py:9` 的 `FILE_MUTATING_TOOL_NAMES` |
> 验证门按工具名白名单,`sed -i` / `execute_code` / MCP 文件工具改代码后门直接放行,
> 台账连「工作区脏了」都不知道

### 2.2 锚点核对:准

`agent/tool_result_classification.py:9 @ 863e313`

```python
FILE_MUTATING_TOOL_NAMES = frozenset({"write_file", "patch"})
```

### 2.3 「验证门」到底是什么门:**不是审批门,是收尾验证门**

R9A 的措辞「直接放行」容易读成权限旁路。**本轮改述:它与权限无关。**
这个集合喂的是**回合收尾时的"你改了代码,先去验证再停"** 那一关。

写入侧只认这两个名字:

`run_agent.py:3408-3409 @ 863e313`

```python
        if tool_name not in _FILE_MUTATING_TOOLS:
            return
```

消费侧(整个机制以 `changed_paths` 为空即短路):

`agent/verification_stop.py:216-218 @ 863e313`

```python
    paths = sorted({str(p) for p in _filter_verifiable_paths(changed_paths)})
    if not paths or attempts >= max_attempts:
        return None
```

`changed_paths` 来自 `agent/conversation_loop.py:7046` 的
`changed_paths=getattr(agent, "_turn_file_mutation_paths", set())`;同一个集合还在
`conversation_loop.py:7102` 门控 `pre_verify` 钩子的续跑。

于是链条是:**只有 `write_file` / `patch` 会把路径写进 `_turn_file_mutation_paths`
→ 用 `terminal`(`sed -i`)/ `execute_code` / MCP 文件工具改的文件不进这个集合
→ `paths` 为空 → 收尾验证提示永不触发 → 回合正常结束。**

而这条提示的正文自称:

`agent/verification_stop.py:263 @ 863e313`

```python
        "[System: You edited code in this turn, but the workspace does not have "
```

**"You edited code in this turn" 这个判断,实际只覆盖两条改文件路径中的一部分。**

### 2.4 仓库里本来有一个不靠工具名的探测器,没接上

`tools/working_diff.py:70-71 @ 863e313`

```python
def collect_working_diff(cwd: str, mode: str = "working",
                         paths: List[str] | None = None) -> Dict:
```

它用 git 直接看工作区脏没脏,与工具名无关。**调用方只有两个,都是给人看的命令**
(搜索面 = 全仓非测试 `.py`):

```verify
cd /home/user/hermes-agent && grep -rn "collect_working_diff" --include=*.py . | grep -v "^./tests/"
```

```text
./gateway/slash_commands.py:3224:        from tools.working_diff import collect_working_diff
./gateway/slash_commands.py:3226:        result = await asyncio.to_thread(collect_working_diff, cwd, mode)
./hermes_cli/cli_commands_mixin.py:185:        from tools.working_diff import collect_working_diff
./hermes_cli/cli_commands_mixin.py:187:        result = collect_working_diff(cwd, mode=mode, paths=paths or None)
./tools/working_diff.py:70:def collect_working_diff(cwd: str, mode: str = "working",
```

**没有一个接到收尾验证门上。** 这正是 R9C §6.3 归纳的那个形态的又一例:
能力写好了、只装了一处(而且装的是"给人看"那一处,不是"给机器判"那一处)。

### 2.5 处置结论

**立 ■,但改述 R9A 的定性。**

- **成立的部分**:白名单只有 `write_file` / `patch` 两个名字,经 `terminal` / `execute_code` /
  MCP 文件工具做出的改动**确实**不会触发收尾验证门。
- **推翻的部分**:R9A 的「直接放行」读起来像审批旁路,**不是**。这里没有任何权限判定,
  放行的是"去验证一下"的提示。**严重度应下调到"质量门静默变窄",不是安全缺陷。**
- **推翻的第二处**:R9A 说「台账连『工作区脏了』都不知道」。准确说法是
  **回合级的 `_turn_file_mutation_paths` 集合**不知道;仓库另有一个 git 级探测器
  (`tools/working_diff.py:70`)知道,只是没接到这条链上。
- **修法**:收尾验证门不该以工具名为唯一信源。`_turn_file_mutation_paths` 为空但本回合
  跑过 `terminal` / `execute_code` 时,应回落到 `collect_working_diff` 判一次工作区。

### 2.6 主线独立复判移交取证组 A 提出的那条 ▲(它自己请求复判)

取证组 A 新判了一条 ▲ 并在残留里写明:「若主线/评审位认为该句属『意图性描述』而非
『条件断言』,可降为 ◎」。**主线独立复判:▲ 成立,不降级。**

`website/docs/user-guide/features/hooks.md:670 @ 863e313`

> Fires **once per turn when the agent edited code**, just before it finishes (after the built-in verify-on-stop guard). This is a user/plugin policy gate: a callback can keep the agent going — run a check, defer it, tidy the diff — instead of letting it stop.

归属标题是 `### pre_verify`(`hooks.md:668`)。代码侧的触发条件:

`agent/conversation_loop.py:7109 @ 863e313`

```python
                    if _edited and has_hook("pre_verify") and _attempt < max_verify_nudges():
```

而 `_edited` 只来自 `_turn_file_mutation_paths`(`conversation_loop.py:7102`),
该集合只被 `write_file` / `patch` 填。

**判 ▲ 的理由,以及它为什么与本轮另一条"不判 ▲"的裁定不矛盾**——这两条值得并排看:

| | `hooks.md:670`(本条) | `security.md:47`(§4.5 cron,判**不**是 ▲) |
|---|---|---|
| 文档给的条件 | "when the agent edited code" | "when they trigger a dangerous-command prompt" |
| 该条件在缺陷场景下 | **成立**(用 `sed -i` 改代码,agent 确实 edited code) | **不成立**(脚本路径根本不触发提示) |
| 文档承诺的结果 | 不发生(钩子不触发) | —— |
| 判定 | **▲**:前件成立而后件不发生,字面为假 | **不是 ▲**:句子的前件从未被满足,字面为真 |

**区别就在"文档那句话的前件在缺陷场景里成立与否"。** `security.md:47` 把自己的适用范围
限定在"触发危险命令提示时",而脚本路径不触发,所以它没说错话(缺陷在别处);
`hooks.md:670` 说的是"当 agent 改了代码时",而 `sed -i` 改代码时它不触发,**它说错了话**。

*把这两条并排写出来,是因为 CLAUDE.md 只给了「字面为真就不是 ▲」这一句判准,
而判准的难点从来不在"真假",在**"这句话到底断言了什么范围"**。*

**未取证**:未实跑一次 `terminal` + `sed -i` 的完整回合去观察提示不触发——那需要模型凭据
(项目边界明写不配置)。上面的判定是**静态全链对读**:写入侧的早退(`run_agent.py:3408`)
与消费侧的短路(`verification_stop.py:217`)两处都读到了,链条闭合,但**证据等级是静态,不是实跑**。

---

## 3. H-R9A-e · 子代理提交点未包上下文传播

### 3.1 锚点核对:准

`agent/subagent_lifecycle.py:259 @ 863e313`

```python
        record.future = _EXECUTOR.submit(self._run, record, request.goal, parent)
```

### 3.2 方向已定:是 **fail-open(变松)**,不是变严 —— 主线独立复现

移交时悬着的关键问题是"丢了审批 session key 之后,是全被拒(变严)还是全放行(变松)"。
**这个方向决定它是不是 ■。** 取证组 B 给出实验,主线独立重跑,读数完全一致:

`agent/subagent_lifecycle.py:165 @ 863e313`

```python
_EXECUTOR = _DaemonExecutor(max_workers=8, thread_name_prefix="hermes-lifecycle")
```

同一个判定函数 `_run_approval_gate`,在三种提交方式下:

```text
PARENT   {'tag': 'parent-thread',        'session_key': 'telegram:42', 'is_gateway': True,  'profile': 'work',   'approved': False}
BARE     {'tag': 'bare-submit',          'session_key': 'default',     'is_gateway': False, 'profile': '<none>', 'approved': True}
COPYCTX  {'tag': 'copy_context-submit',  'session_key': 'telegram:42', 'is_gateway': True,  'profile': 'work',   'approved': False}
```

**读法**:父线程判 `approved=False`(要求审批)→ 裸 `submit` 判 `approved=True`(**自动放行**)
→ 把同一个函数包进 `copy_context()` 再提交,又变回 `approved=False`。

**方向是变松。** 一个在父线程上需要人点头的危险动作,到了子代理的 worker 线程里**被自动批准**。
机制:`tools/approval.py` 的两个前置谓词(`_is_interactive_cli`、`_is_gateway_approval_context`)
都只读 contextvar,contextvar 没传过去 → 两个谓词都判"不在交互/网关上下文" → 走自动放行分支。

**为什么下游的 `copy_context` 救不回来**:`self._run` 下游确实有一次 `copy_context()`,
但它是在**已经身处 worker 线程时**取快照——源头断了,下游全是空转。
*这是一个很值得记住的形态:**上下文传播只要断一处,后面每一处 `copy_context` 都在忠实地复制"空"**。*

### 3.3 处置结论

**维持 ■,并把方向定死为 fail-open。** 覆盖率数字按取证组 B 的重数改述
(R9A 的"全仓 8 处同类提交点"口径未写明,取证组 B 重数并写了搜索面:
`copy_context` 在非测试代码里 **18 处**)。

**残留(本仓库内不可完全消解)**:未在真实 gateway 回合里端到端跑
"插件起子代理 → 子代理执行危险命令 → 未提示审批"全链路——那需要真实 provider 凭据,
项目边界明写不配置。上面的实验覆盖了**从 contextvars 到 `approved` 布尔值的全部判定逻辑**,
但"子代理确实会调 `check_dangerous_command`"这一段仍是静态对读。

---

## 4. H-R9A-f · Skills Hub 的裸 `httpx.get`

### 4.1 锚点核对:两个都准

`tools/skills_hub.py:3205 @ 863e313`

```python
            resp = httpx.get(md_url, timeout=20, follow_redirects=True)
```

同文件的守卫:

`tools/skills_hub.py:302 @ 863e313`

```python
def _guarded_http_get(url: str, *, timeout: int = 20) -> Optional[httpx.Response]:
```

守卫做两件事:用 `create_ssrf_safe_client(..., follow_redirects=False)` 建客户端,
并对**每一跳**重定向目标跑 `is_safe_url` 再决定跟不跟。

### 4.2 主线的一处改判:**这不是「凭据跟着重定向走」那个形态**

`httpx.get(md_url, timeout=20, follow_redirects=True)` **没有 headers 参数、不挂任何凭据**。
R9C 的 H-R9A-a 是"bearer 被带到任意主机";**本条不是**。本条的两个风险是:

1. **SSRF**:`md_url` 未经 `is_safe_url`,可指向内网/元数据地址;
2. **内容投毒**:取回的正文是 **skill 的 markdown**,而 skill 正文是**喂给模型的指令**。

**第 2 条比第 1 条重**:一个能左右 skill 正文的人,能左右 agent 之后的行为。

### 4.3 处置结论

**维持 ■,改述两处**:

1. **风险类型改述**(主线与取证组 B 同判):从"凭据泄漏"改为 **SSRF + skill 内容投毒**。
   `httpx.get(md_url, timeout=20, follow_redirects=True)` 不挂任何凭据,
   所以它不是 R9C 的 H-R9A-a 那个形态。守卫 `_guarded_http_get` 守三件事:
   `is_safe_url`(SSRF 地址闸)、`check_website_access`(站点策略黑名单)、
   **以及自己做重定向**(用 `follow_redirects=False` + 手动逐跳重过闸,
   并把校验挪到 TCP connect 前一刻以对付 DNS rebinding)。
   **`:3205` 的 `follow_redirects=True` 恰是这个设计的反面。**
2. **"8 处里唯一一处"这个覆盖率口径不成立**(取证组 B 重数,主线采信):
   实为**同类 3 处、2 处走守卫、1 处没走**。R9A 的"8 处"把不同型的调用混进了分母。

**严重度的决定因素,以及它为什么不可在本仓库内消解**:`md_url` 来自
**browse.sh(第三方目录,不是 Nous 官方 hub)**的 `/api/skills/{slug}` 详情端点,
校验只有 `isinstance(str)` + 前缀检查。**该目录的条目能否由任意第三方提交**,
决定这条是"需要第三方站点作恶"还是"任何人都能投毒"——**容器离线够不到 browse.sh,
推定未取证,且本仓库内不可消解**(需外网)。这不影响 ■ 成立(守卫该走没走是代码事实),
只影响严重度分级。

---

## 5. H-R9A-g · `AGENTS.md` toolset 清单

### 5.1 原移交项与它的一处算错

R9A 记:「文档列 30 个键、代码有 58 个,**文档还漏 28 个**;本轮只判定了『文档有而代码无』的 3 个」。

**30 与 58 都对,28 错。** 正确是 **31**:文档那 30 个里有 3 个代码根本没有,
故重合只有 27,代码独有 = 58 − 27 = **31**。R9A 应是直接算了 58 − 30。

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python -c "
import ast, pathlib
tree = ast.parse(pathlib.Path('toolsets.py').read_text())
for n in ast.walk(tree):
    if isinstance(n, ast.Assign) and any(getattr(t,'id',None)=='TOOLSETS' for t in n.targets):
        code = {k.value for k in n.value.keys if isinstance(k, ast.Constant)}
doc = set('''browser clarify code_execution cronjob debugging delegation discord discord_admin
feishu_doc feishu_drive file homeassistant image_gen kanban memory messaging moa rl safe search
session_search skills spotify terminal todo tts video vision web yuanbao'''.split())
print(f'代码 {len(code)} / 文档 {len(doc)} / 重合 {len(code&doc)}')
print(f'文档有代码无 {len(doc-code)}: {sorted(doc-code)}')
print(f'代码有文档漏 {len(code-doc)}')"
```

```text
代码 58 / 文档 30 / 重合 27
文档有代码无 3: ['messaging', 'moa', 'rl']
代码有文档漏 31
```

### 5.2 归哪个标题管:`## Toolsets`(AGENTS.md:964)

CLAUDE.md 要求「判定一条文档断言时必须把整段一并判定,并确认它归哪个标题管」。
该节共四句断言,**逐句判**:

`AGENTS.md:966-969 @ 863e313`

> All toolsets are defined in `toolsets.py` as a single `TOOLSETS` dict.
> Each platform's adapter picks a base toolset (e.g. Telegram uses
> `"messaging"`); `_HERMES_CORE_TOOLS` is the default bundle most
> platforms inherit from.

`AGENTS.md:971-975 @ 863e313`

> Current toolset keys: `browser`, `clarify`, `code_execution`, `cronjob`,
> `debugging`, `delegation`, `discord`, `discord_admin`, `feishu_doc`,
> `feishu_drive`, `file`, `homeassistant`, `image_gen`, `kanban`, `memory`,
> `messaging`, `moa`, `rl`, `safe`, `search`, `session_search`, `skills`,
> `spotify`, `terminal`, `todo`, `tts`, `video`, `vision`, `web`, `yuanbao`.

| # | 断言 | 判定 | 依据 |
|---|---|---|---|
| 1 | "All toolsets are defined in `toolsets.py` as a single `TOOLSETS` dict" | **成立**,但有未述之处 → **◇** | 静态字面确在该文件该 dict;另有运行时注入路径 `toolsets.py:915` 的 `def create_custom_toolset(` 会 `TOOLSETS[name] = {`,文档未提 |
| 2 | "Telegram uses `\"messaging\"`" | **▲** | `hermes_cli/platforms.py:23`:`default_toolset="hermes-telegram"`;且 `messaging` 压根不是 `TOOLSETS` 键 |
| 3 | "`_HERMES_CORE_TOOLS` is the default bundle most platforms inherit from" | **成立,不记号** | `toolsets.py:31` 的 `_HERMES_CORE_TOOLS = [` 定义,22 个 `hermes-*` 平台 toolset 拿它当 `tools` |
| 4 | "Current toolset keys: …"(30 个) | **▲** | 实为 58;漏 31、多列 3 |

第 2 句的证据:

`hermes_cli/platforms.py:23 @ 863e313`

```python
    ("telegram",       PlatformInfo(label="📱 Telegram",        default_toolset="hermes-telegram")),
```

**为什么第 4 句判 ▲ 而不是 ◇/◎**:CLAUDE.md 定「字面为真就不是 ▲」。这里的措辞是
**"Current toolset keys:"** 后接一个**完整枚举并以句号收尾**——它把这 30 个呈现为"当前的键",
而不是"例如""部分"。列 30 个而实有 58 个,**且其中 3 个根本不存在**,字面即不为真。
(对照:CLAUDE.md 举的 ◎ 例子是"20+ 平台"而实为 24 —— 那是字面为真的保守表述,与此不同。)

### 5.3 漏掉的 31 个:两个性质完全不同的家族

```verify
cd /home/user/hermes-agent && grep -c '^    "hermes-' toolsets.py
```

```text
24
```

| 家族 | 个数 | 在 `toolsets.py` 的位置 | 性质 |
|---|---|---|---|
| `hermes-<平台>` | **24** | 407–610 行,**连续一整块** | 每个平台的默认捆绑包,由 `hermes_cli/platforms.py` 的 `default_toolset=` 指定;文档在第 2 句里**概念上提到了**这个机制,只是举错了例子 |
| 普通功能 toolset | **7** | 115–374 行,**与已列出的那些交错** | `x_search`(115)、`video_gen`(146)、`bfl`(158)、`computer_use`(177)、`context_engine`(242)、`project`(254)、`coding`(374) |

**这 7 个才是真正的漏列**:它们与文档已列出的 `browser` / `file` / `todo` 等**同处一段、同一性质**,
文档挑着列了一部分。24 个 `hermes-*` 是另一件事——它们是平台捆绑包,
一份面向贡献者的地图不逐个列出是合理的编辑取舍。

**与本轮的直接关联**:这 7 个里 **`project` 与 `x_search` 的实现文件正在 R9D 的 49 个里**
(`tools/project_tools.py`、`tools/x_search_tool.py`),`computer_use` 归 R4。
换句话说,**文档漏列的功能 toolset,恰恰是历轮最晚才被读到的那些** —— 地图腐烂的方向不是随机的,
是"越边缘越不更新"。

### 5.4 主线初判被推翻:那 24 个平台束不是 ▲,是 ◇

**本节撤回主线初稿的一处判定,依据是取证组 C 提供、主线独立复核过的历史证据。**

初稿把第 4 句(键清单)整条判 ▲,即把"漏掉的 31 个"不加区分地算作文档与代码矛盾。
**这是错的**,而且错在一个我没去查的地方:**文档定稿那一刻,这份清单是不是完整的?**

清单所在小节由 `b7bd17710`(2026-05-05,"docs(AGENTS.md): add curator/cron/delegation/toolsets…")写入。
取那一刻的快照对读(用 `git show`,**不切换基线工作区**):

```verify
cd /home/user/hermes-agent && git show b7bd17710:toolsets.py > /tmp/toolsets_old.py &&   /home/user/hermes-venv/bin/python -c "
import ast, pathlib
tree = ast.parse(pathlib.Path('/tmp/toolsets_old.py').read_text())
for n in ast.walk(tree):
    if isinstance(n, ast.Assign) and any(getattr(t,'id',None)=='TOOLSETS' for t in n.targets):
        keys = {k.value for k in n.value.keys if isinstance(k, ast.Constant)}
doc = set('''browser clarify code_execution cronjob debugging delegation discord discord_admin
feishu_doc feishu_drive file homeassistant image_gen kanban memory messaging moa rl safe search
session_search skills spotify terminal todo tts video vision web yuanbao'''.split())
nonplat = {k for k in keys if not k.startswith('hermes-')}
print(f'当时 TOOLSETS {len(keys)} 键 = 非 hermes-* {len(nonplat)} + hermes-* {len(keys)-len(nonplat)}')
print('文档集合 == 当时的非 hermes-* 集合 ?', doc == nonplat)"
```

```text
当时 TOOLSETS 54 键 = 非 hermes-* 30 + hermes-* 24
文档集合 == 当时的非 hermes-* 集合 ? True
```

**集合严格相等。** 也就是说:作者当时做的是**「能力 toolset」这一子类的完整枚举**,
**24 个 `hermes-<平台>` 捆绑包是有意排除的**,不是漏写。文档从未就平台族说过与代码矛盾的话——
它只是**没把"本清单不含平台族"这条命名规则写出来**。

**所以正确的拆判是:**

| 家族 | 个数 | 记号 | 理由 |
|---|---|---|---|
| `hermes-<平台>` 捆绑包(代表 `toolsets.py:480`:`"hermes-telegram": {`) | 24 | **◇** | 定稿时即被有意排除,文档没说错话,只是没写出这条规则 |
| 能力 toolset(代表 `toolsets.py:242`:`"context_engine": {`) | **7** | **▲** | 与已列出的那 30 个**同类**;清单自称是该类的完整枚举,而它现在不完整了 |
| 文档列了但代码已无(`messaging` / `moa` / `rl`) | 3 | **▲** | 定稿时存在,后被删,文档未跟 |

*为什么这个更正重要,而不只是"分类更细":**判 ▲ 是在说"作者画错了地图"**,
判 ◇ 是在说"地图没画这一块"。对那 24 个平台束,作者**画对了**——他画的是另一张图,
只是没写图例。把它算成 ▲,既冤枉了作者,也让 ▲ 这个跨轮"地图腐烂程度"指标失真。
CLAUDE.md 立 ▲/◇/◎ 之分时说的就是这件事,我初判时没有去查"定稿那一刻"这个时间维度。*

### 5.5 处置结论

- **▲ 两类**:第 2 句的 Telegram 例子(`messaging` 根本不是键)、
  以及键清单里 **7 个能力 toolset 漏列 + 3 个已删仍列**;
  **◇ 两类**:24 个平台族未述、运行时 `create_custom_toolset` 未述;第 3 句成立不记号。
- **R9A 的"漏 28"改正为 31**,并按定稿快照拆成 24(◇)+ 7(▲)。
- **R9A 的锚点 `AGENTS.md:971-974` 也要改正为 `971-975`**:原范围**漏掉整整一行 8 个键**,
  照它去截取只数得出 22 个而非 30 个。*(移交项锚点漂一行就让下一轮找错地方——
  这正是 CLAUDE.md 要求移交锚点用声明式写法的理由。)*
- **判定完成,H-R9A-g 关闭。**
- 建议修法(给上游):第 2 句的例子改成 `hermes-telegram`;清单补上 7 个能力 toolset、
  删掉 3 个已不存在的,并**写明"本清单不含 `hermes-<平台>` 捆绑包"**这条规则。

---

## 6. H-R9C-a · Portal 基址不查白名单(**本轮扩大为两处**)

### 6.1 锚点核对:准

`hermes_cli/nous_billing.py:179-185 @ 863e313`

```python
    env = os.getenv("HERMES_PORTAL_BASE_URL") or os.getenv("NOUS_PORTAL_BASE_URL")
    if env and env.strip():
        return env.strip().rstrip("/")
    if state:
        stored = state.get("portal_base_url")
        if isinstance(stored, str) and stored.strip():
            return stored.strip().rstrip("/")
```

对照:同一字段在 `auth.py` 是查清单的。

`hermes_cli/auth.py:5900 @ 863e313`

```python
            if parsed_portal_url.hostname and parsed_portal_url.hostname not in _NOUS_PORTAL_ALLOWED_HOSTS:
```

### 6.2 决定性证据:作者自己写下了这条清单的威胁模型

`hermes_cli/auth.py:2339-2342 @ 863e313`

```python
    set it themselves), so — like the inference override — it must NOT be
    gated by ``_NOUS_PORTAL_ALLOWED_HOSTS``: that allowlist exists to reject
    an untrusted NETWORK-provided value (a poisoned portal_base_url
    persisted to auth.json), not a value the operator explicitly configured.
```

**这段话把本条一分为二,而且是作者自己分的:**

- **env 分支**(`nous_billing.py:179-181`)不查清单 —— **正确,合乎设计**。
  作者明写 env 是运营者自己设的、可信,**"must NOT be gated"**。
- **stored 分支**(`nous_billing.py:182-185`)不查清单 —— **正是这条清单被写出来要挡的那一种**
  ("a poisoned portal_base_url persisted to auth.json")。

### 6.3 后果:bearer 发往该地址,且走的是 `urlopen`

`hermes_cli/nous_billing.py:413 @ 863e313`

```python
        with urllib.request.urlopen(req, timeout=timeout) as resp:
```

请求头在 `nous_billing.py:399-402` 组装,首项是 `"Authorization": f"Bearer {token}"`。
**这与 R9C 定案的 H-R9A-a 是同一形态**(`urllib` + `Authorization`),
故 R9C 的结论在此原样适用:**只补主机校验不够,还须换成 `open_credentialed_url`**,
否则重定向仍会把 bearer 带到新主机。

### 6.4 主线的扩大:清单装了 2 处,**漏的也是 2 处**

清单的全部查询点(搜索面 = 全仓非测试 `.py`):

```verify
cd /home/user/hermes-agent && grep -rn "_NOUS_PORTAL_ALLOWED_HOSTS" --include=*.py . | grep -v "^./tests/"
```

```text
./hermes_cli/auth.py:2235:_NOUS_PORTAL_ALLOWED_HOSTS: FrozenSet[str] = frozenset({
./hermes_cli/auth.py:2340:    gated by ``_NOUS_PORTAL_ALLOWED_HOSTS``: that allowlist exists to reject
./hermes_cli/auth.py:5900:            if parsed_portal_url.hostname and parsed_portal_url.hostname not in _NOUS_PORTAL_ALLOWED_HOSTS:
./hermes_cli/auth.py:6257:                    or portal_host not in _NOUS_PORTAL_ALLOWED_HOSTS
```

四行拆开看:**定义 1 处**(`:2235`)+ **注释 1 处**(`:2340`)+ **真正的判定 2 处**
(`:5900` 与 `:6257`)—— **判定点合计 2 个,全在 `hermes_cli/auth.py`**。

*(留痕:本节初稿把这段输出抄成了 3 行、漏了 `:6257`,并在正文里用散文把它补回来。
重跑该命令得 4 行 —— 与所抄不符。已改为原样粘贴。
这正是 CLAUDE.md「shell 命令即证据:必须是重跑能复现该结论的那一条」要防的形状,
本轮自查时撞见并修掉。)*

而 R9C 只找到 `nous_billing.py` 一个漏点。**本轮找到第二个,同型**:

`hermes_cli/dashboard_register.py:84-87 @ 863e313`

```python
        state = get_provider_auth_state("nous") or {}
        base = state.get("portal_base_url")
        if isinstance(base, str) and base.strip():
            return base.rstrip("/")
```

它同样把结果当凭据目的地:

`hermes_cli/dashboard_register.py:133-141 @ 863e313`

```python
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
```

**读同一个 stored 字段 + 挂 Bearer + 走 `urlopen` 且不查清单 = 2 处
(`nous_billing.py`、`dashboard_register.py`);查清单的 = 2 处,都在 `auth.py`。**

### 6.5 处置结论

**立 ■,并把范围从 1 处扩到 2 处。**

- **stored 分支**:■。作者自述的威胁模型明写这条清单就是为它写的,而两个消费点都没查。
- **env 分支**:**不是缺陷**,合乎作者明述的设计。*(R9C 的移交项把两个分支并作一条写,
  本轮拆开——不拆的话修法会把一个正确的逃生舱一起堵了。)*
- **修法**:`resolve_portal_base_url` 的 **stored 分支**加清单校验(env 分支保持不变),
  且两个消费点一并从 `urlopen` 换成 `open_credentialed_url`。
- **仍是推定的一半**:**未取证"网络侧如何把 poisoned 值写进 `auth.json`"**。
  本轮只证明了"若该字段被污染,则 bearer 发往污染地址",没有证明污染路径本身可达。
  采信"这是真威胁"的依据是**作者自己在 `auth.py:2341` 写下的威胁模型**——
  这是仓库内证据,不是我的推断,但它终究是作者的判断而非我实证的攻击链。

---

## 7. 定案汇总表

*(七条全部到案。§3 / §4 / §5 三条的定案依据取证组 B/C 的证据做过修订,修订理由写在各节。)*

| 移交项 | 锚点(声明式) | 处置结论 |
|---|---|---|
| **H-R9A-b** | `hermes_cli/kanban_db.py:6941`:`pid, status = os.waitpid(-1, os.WNOHANG)` | **立 ■**,推翻 R9A「不主张」;实证 42→0 降级 + fail-open 后果;R9A 测的 asyncio 侧是唯一结构安全的子集 |
| **H-R9A-c** | `agent/tool_result_classification.py:9`:`FILE_MUTATING_TOOL_NAMES = frozenset({"write_file", "patch"})` | **立 ■ 但改述定性**:是收尾验证门变窄,**非**审批旁路;仓库内已有 git 级探测器未接上 |
| **H-R9A-e** | `agent/subagent_lifecycle.py:259`:`record.future = _EXECUTOR.submit(self._run, record, request.goal, parent)` | **维持 ■,方向定死为 fail-open**:父线程 `approved=False` 的危险动作,在裸 submit 的 worker 里变成 `approved=True`(主线独立复现) |
| **H-R9A-f** | `tools/skills_hub.py:3205`:`resp = httpx.get(md_url, timeout=20, follow_redirects=True)` | **维持 ■,改述两处**:风险是 SSRF + skill 内容投毒(不挂凭据);覆盖率由「8 取 1」改述为「同类 3 处、2 守 1 未守」 |
| **H-R9A-g** | `AGENTS.md:966`:`All toolsets are defined in ` | **关闭**。R9A 的「漏 28」改正为 **31**;**主线初判被推翻**——按定稿快照(集合严格相等)拆为 24 平台族 **◇** + 7 能力 toolset **▲**;R9A 锚点 `971-974` 改正为 `971-975`(原范围漏一整行 8 个键) |
| **H-R9C-a** | `hermes_cli/nous_billing.py:182`:`stored = state.get("portal_base_url")` | **立 ■,范围扩到 2 处**;env 分支判为**合乎设计、非缺陷**(作者自述威胁模型) |
| **H-R9C-b** | `hermes_cli/secrets_cli.py:59`:`help="Provide the access token non-interactively (will be stored in .env)",` | 核心问号判**阴性**:落盘的 `.env` 在禁读清单里(profile 级 + 根级 + 7 个项目基名),见 `notes/r9d-92-*.md` §3;取证组 D 的结构级理解到货后另附 |
