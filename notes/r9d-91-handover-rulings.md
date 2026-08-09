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
    /tmp/claude-0/-home-user-hermes-study/11b9bcbd-a8fd-518c-931a-498c7a1d5f37/scratchpad/h_r9a_b_repro.py
```

```text
收尸者 = 真实 reap_worker_zombies()
[组1 对照] 无人抢,     Popen.wait() = 42   (真实退出码应为 42)
[组2 实验] 抢走 1 个,Popen.wait() = 0   (被抢后属主看到的退出码)
[组3 asyncio] 抢到 0 个,proc.wait() = 42   (ThreadedChildWatcher 在场)
```

**组 3 正是 R9A 测的那一侧,它确实复现不了——因为那一侧有 watcher 线程护着。
组 2 才是暴露面,退出码 42 变成 0。**

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
    /tmp/claude-0/-home-user-hermes-study/11b9bcbd-a8fd-518c-931a-498c7a1d5f37/scratchpad/h_r9a_b_run_variant.py
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

- **机制已实证**(用基线真函数):`Popen.wait()` 与 `subprocess.run().returncode` 都从 42 降级为 0。
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
是全部暴露面里**唯一一个结构上安全**的子集。*

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

### 3.2 处置见子代理取证书,主线复核结论

本条的关键不在锚点(已核准),而在两个数:**同类提交点到底几处、漏的方向是变严还是变松**。
主线的独立普查见 `notes/r9d-90-handover-single-call-site-misses.md` 的对读节;
**处置结论与理由一并写在那里,本节不重复。**

> **本节的定案见 §7 汇总表。**

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

**维持 ■,但改述风险类型**(从"凭据泄漏"改为"SSRF + skill 内容投毒"),
严重度取决于 `md_url` 的来源可信度——该链路的取证见
`notes/r9d-90-handover-single-call-site-misses.md`,定案见 §7 汇总表。

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

### 5.4 处置结论

- **▲ 两条**(第 2 句的 Telegram 例子、第 4 句的键清单),**◇ 一条**(运行时 `create_custom_toolset` 未述),
  第 3 句成立不记号。
- **R9A 的 28 改正为 31**,并给出 24 / 7 的家族拆分。
- **判定完成,H-R9A-g 关闭**:R9A 留下的"漏列那一半未判"至此判完。
- 建议修法(给上游):第 2 句的例子改成 `hermes-telegram`;第 4 句要么补上 7 个功能 toolset
  并声明 `hermes-*` 另有一族,要么把措辞从 "Current toolset keys" 改成明确的部分枚举。

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

*(§3 / §4 两条的最终定案在子代理取证到货并经主线复核后填入,见本表下方状态栏。)*

| 移交项 | 锚点(声明式) | 处置结论 |
|---|---|---|
| **H-R9A-b** | `hermes_cli/kanban_db.py:6941`:`pid, status = os.waitpid(-1, os.WNOHANG)` | **立 ■**,推翻 R9A「不主张」;实证 42→0 降级 + fail-open 后果;R9A 测的 asyncio 侧是唯一结构安全的子集 |
| **H-R9A-c** | `agent/tool_result_classification.py:9`:`FILE_MUTATING_TOOL_NAMES = frozenset({"write_file", "patch"})` | **立 ■ 但改述定性**:是收尾验证门变窄,**非**审批旁路;仓库内已有 git 级探测器未接上 |
| **H-R9A-e** | `agent/subagent_lifecycle.py:259`:`record.future = _EXECUTOR.submit(self._run, record, request.goal, parent)` | 见 §3,定案待主线复核子代理普查后填 |
| **H-R9A-f** | `tools/skills_hub.py:3205`:`resp = httpx.get(md_url, timeout=20, follow_redirects=True)` | **维持 ■,改述风险类型**:无凭据,是 SSRF + skill 内容投毒 |
| **H-R9A-g** | `AGENTS.md:966`:`All toolsets are defined in ` | **关闭**:▲×2 + ◇×1;R9A 的「漏 28」改正为 **31**,拆为 24 平台族 + 7 功能 toolset |
| **H-R9C-a** | `hermes_cli/nous_billing.py:182`:`stored = state.get("portal_base_url")` | **立 ■,范围扩到 2 处**;env 分支判为**合乎设计、非缺陷**(作者自述威胁模型) |
| **H-R9C-b** | `hermes_cli/secrets_cli.py` | 见子代理取证书,定案待主线复核后填 |
