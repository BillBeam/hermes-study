# r10-tui-gateway-methods —— tui_gateway 的方法实现面与宿主进程监管(L2 结构级)

> 基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`,引用后缀 `@ 863e313`。
> 本片 11 个文件、9,742 行。凡对代码行为的断言,锚点单独成行置于块前;非源码块用
> ```` ```text ```` / ```` ```verify ```` 声明。

---

## §1 这一片是什么

`tui_gateway/` 是 hermes 的**终端 UI / 桌面 App 与 Python agent 内核之间的 JSON-RPC 桥**。
JSON-RPC(JSON Remote Procedure Call,一种"客户端发一条 `{method, params}`、服务端回
一条 `{result}` 或 `{error}`"的极简远程调用约定)在这里跑在**换行分隔的 stdio**
(Ink 终端 UI)或 **WebSocket**(Electron 桌面 App / web 仪表盘)上。
Node 侧只负责画屏,Python 侧持有会话、工具、模型调用与斜杠命令逻辑。

这一片是这座桥的**方法实现面 + 宿主进程监管**,可以分成四组:

1. **五个 `methods_*` 模块** —— 123 个 JSON-RPC 方法的**处理函数体**。它们是 2026 年
   从 19,000 行的 `tui_gateway/server.py` 里**逐字搬出来**的,用一个很不寻常的
   "把函数的 `__globals__` 重绑回 server.py 命名空间"的手法保持函数体一字不改(见 §5.1)。
2. **宿主监管两件套** —— `compute_host.py`(被监管的子进程本体)与
   `host_supervisor.py`(父进程里的监工)。解决的是 CPython 单 GIL
   (Global Interpreter Lock,全局解释器锁:同一时刻只有一个线程能执行 Python 字节码)
   下"agent 计算线程把 WebSocket 事件循环饿死"的问题。
3. **两个信息暴露器** —— `project_tree.py`(把会话按 项目→仓库→车道 分组,喂桌面侧边栏)
   与 `git_probe.py`(在 gateway 侧跑 `git`,解析仓库根,带单飞缓存)。
4. **两个进程外执行体** —— `slash_worker.py`(每个会话一个常驻 `HermesCLI` 子进程,
   跑斜杠命令)与 `synthetic_turn.py`(一个**测试接缝**:假 agent,专门烧 CPU 占住 GIL)。

---

## §2 文件清单(逐个全路径 + 角色)

| 全路径 | 行数 | 角色 |
|---|---|---|
| `tui_gateway/methods_session.py` | 3138 | 会话生命周期 / 委派 / spawn-tree / 计费 / 宠物(petdex)共 **62** 个方法;唯一使用 `@_profile_scoped` 的模块(12 处) |
| `tui_gateway/methods_tools.py` | 1914 | 工具与系统 / 斜杠执行 / 回滚 / 浏览器 / 插件 / cron / skills 共 **32** 个方法;`slash.exec` 与 `command.dispatch` 两大路由器都在这里 |
| `tui_gateway/methods_prompt.py` | 949 | 提交与附件共 **16** 个方法(`prompt.submit` 一家独大 267 行);另外 `register()` 会额外发布一个非 `@method` 的辅助函数 `_pending_reaction_notes` |
| `tui_gateway/methods_config.py` | 422 | 配置读取 / 项目树 / 安装自检共 **7** 个方法;`config.get` 一个方法内分派 **18** 个 key |
| `tui_gateway/methods_complete.py` | 484 | 补全与模型密钥共 **6** 个方法(`complete.path` / `complete.slash` / `model.save_key` …) |
| `tui_gateway/compute_host.py` | 880 | 被监管的子进程本体:`python -m tui_gateway.compute_host`。持有真实 `AIAgent`、按帧执行回合、心跳、孤儿自杀 |
| `tui_gateway/host_supervisor.py` | 577 | 父进程里的监工:拉起/判死/重启 compute host,转发帧,维护 PID 登记文件 |
| `tui_gateway/project_tree.py` | 768 | **纯函数**的 项目→仓库→车道→会话 树构建器(所有 git 解析由外部注入),桌面侧边栏分组的唯一权威 |
| `tui_gateway/git_probe.py` | 183 | gateway 侧 `git` 探测:仓库根解析 + 线程安全单飞缓存(正结果永久、负结果 30s TTL) |
| `tui_gateway/slash_worker.py` | 196 | 常驻 `HermesCLI` 子进程,stdin/stdout 上跑 `{id, command}` → `{id, ok, output}` |
| `tui_gateway/synthetic_turn.py` | 231 | **测试接缝**:`SyntheticHeavyAgent`,一个持有 GIL 狂烧 CPU 的假 agent,仅在 `HERMES_ISO_CERTIFY_SYNTH_TURN=1` 时生效 |

行数复核:

```verify
cd /home/user/hermes-agent && wc -l $(cat /home/user/hermes-study/data/r10/slices/B.txt)
```

---

## §3 接缝穷举

### §3.1 五个 `methods_*` 模块注册的 JSON-RPC 方法(共 123 条,逐个列全)

注册机制是 `@method("名字")` 装饰器(见 §5.1),**每个装饰器都在行首**,所以可机械枚举:

```verify
cd /home/user/hermes-agent && for f in methods_session methods_prompt methods_config methods_complete methods_tools; do
  printf '%-18s %s\n' "$f" "$(grep -c '^@method(\"' tui_gateway/$f.py)"
done
echo "----"; grep -ch '^@method("' tui_gateway/methods_*.py | paste -sd+ | bc
```

实测输出:

```text
methods_session    62
methods_prompt     16
methods_config     7
methods_complete   6
methods_tools      32
----
123
```

同时确认**没有**写在行内的漏网装饰器(总数 123 与行首数一致):

```verify
cd /home/user/hermes-agent && grep -rn '@method(' tui_gateway/methods_*.py | grep -vc ':@method("'
```

→ 输出 `0`(即 123 处 `@method(` 全部在行首)。

完整清单(带行号,`grep -n '^@method("'` 的输出重排为表):

**A. `tui_gateway/methods_session.py` —— 62 条**

| # | 方法 | 行 | # | 方法 | 行 |
|---|---|---|---|---|---|
| 1 | `session.create` | 14 | 32 | `pet.cancel` | 1755 |
| 2 | `session.list` | 162 | 33 | `pet.generate.status` | 1769 |
| 3 | `session.most_recent` | 214 | 34 | `pet.generate` | 1800 |
| 4 | `project.facts` | 263 | 35 | `pet.hatch` | 1913 |
| 5 | `verification.status` | 281 | 36 | `billing.state` | 2012 |
| 6 | `session.resume` | 306 | 37 | `usage.bars` | 2028 |
| 7 | `session.cwd.set` | 725 | 38 | `subscription.state` | 2043 |
| 8 | `session.workspace.move` | 750 | 39 | `subscription.preview` | 2059 |
| 9 | `session.active_list` | 824 | 40 | `subscription.change` | 2084 |
| 10 | `session.activate` | 862 | 41 | `subscription.resume` | 2107 |
| 11 | `session.delete` | 887 | 42 | `subscription.upgrade` | 2125 |
| 12 | `session.title` | 937 | 43 | `billing.charge` | 2163 |
| 13 | `message.react` | 1021 | 44 | `billing.charge_status` | 2189 |
| 14 | `llm.oneshot` | 1074 | 45 | `billing.auto_reload` | 2218 |
| 15 | `handoff.request` | 1133 | 46 | `billing.step_up` | 2240 |
| 16 | `handoff.state` | 1221 | 47 | `session.status` | 2281 |
| 17 | `handoff.fail` | 1248 | 48 | `session.history` | 2357 |
| 18 | `session.usage` | 1272 | 49 | `session.undo` | 2381 |
| 19 | `session.context_breakdown` | 1296 | 50 | `session.compress` | 2416 |
| 20 | `pet.info` | 1326 | 51 | `session.save` | 2588 |
| 21 | `pet.info.meta` | 1352 | 52 | `session.close` | 2660 |
| 22 | `pet.cells` | 1375 | 53 | `session.branch` | 2672 |
| 23 | `pet.gallery` | 1480 | 54 | `session.interrupt` | 2824 |
| 24 | `pet.select` | 1563 | 55 | `delegation.status` | 2898 |
| 25 | `pet.remove` | 1590 | 56 | `delegation.pause` | 2918 |
| 26 | `pet.export` | 1620 | 57 | `subagent.interrupt` | 2926 |
| 27 | `pet.rename` | 1647 | 58 | `spawn_tree.save` | 2937 |
| 28 | `pet.thumb` | 1685 | 59 | `spawn_tree.list` | 2980 |
| 29 | `pet.disable` | 1720 | 60 | `spawn_tree.load` | 3031 |
| 30 | `pet.scale` | 1734 | 61 | `session.steer` | 3055 |
| 31 | — | — | 62 | `session.redirect` / `terminal.resize` | 3088 / 3127 |

（第 31/62 格合并是为了塞满两列;上表 62 个方法名与下面的机械枚举命令输出逐条一致。）

```verify
cd /home/user/hermes-agent && grep -n '^@method("' tui_gateway/methods_session.py | sed 's/@method("/ /; s/")$//'
```

**B. `tui_gateway/methods_prompt.py` —— 16 条**

`prompt.submit`(67)、`clipboard.paste`(336)、`image.attach`(376)、
`image.attach_bytes`(419)、`pdf.attach`(480)、`file.attach`(606)、
`image.detach`(653)、`input.detect_drop`(673)、`prompt.background`(720)、
`preview.restart`(766)、`clarify.respond`(879)、`terminal.read.respond`(888)、
`preview.read.respond`(897)、`sudo.respond`(905)、`secret.respond`(910)、
`approval.respond`(915)。

**C. `tui_gateway/methods_config.py` —— 7 条**

`projects.discover_repos`(19)、`projects.record_repos`(44)、`projects.tree`(108)、
`projects.project_sessions`(135)、`config.get`(161)、`setup.status`(340)、
`setup.runtime_check`(350)。

`config.get` 是一个方法里的二级分派表,**20 个分支 / 21 个 key**:

```verify
cd /home/user/hermes-agent && awk 'NR>=161 && NR<=337' tui_gateway/methods_config.py \
  | grep -oE 'if key (==|in) [^:]*' | sed 's/^/  /'
```

实测 **20** 行输出(其中 `{approval_mode, approvals.mode}` 一个分支管两个 key,故 key 数为 21):
`provider` / `profile` / `project` / `full` / `prompt` / `skin` / `indicator` /
`personality` / `reasoning` / `fast` / `busy` / `{approval_mode, approvals.mode}` /
`details_mode` / `thinking_mode` / `density` / `theme` / `statusbar` / `focus` /
`mouse` / `mtime`,其余落到 `4002 unknown config key`。
*(自我更正:本节初稿写"18 个 key、17 行输出",是我目视点数漏了 `mouse` 并少算了一行;
按上面那条命令重跑得 20 行 / 21 key —— 这正是"shell 命令即证据"要抓的形态。)*

> **注意(◇,§6-4)**:模块顶部注释声明 `config.set` **没有**搬过来。
> `tui_gateway/methods_config.py:3` 的 `NOTE: ``config.set`` stays in server.py for now`。
> 所以"读配置在 methods_config、写配置在 server.py"是本片一条真实的接缝断裂。

**D. `tui_gateway/methods_complete.py` —— 6 条**

`paste.collapse`(14)、`complete.path`(41)、`complete.slash`(218)、
`model.options`(327)、`model.save_key`(350)、`model.disconnect`(430)。

**E. `tui_gateway/methods_tools.py` —— 32 条**

`system.battery`(14)、`process.stop`(39)、`process.list`(49)、`process.kill`(61)、
`reload.mcp`(84)、`reload.env`(234)、`commands.catalog`(255)、`cli.exec`(371)、
`command.resolve`(412)、`command.dispatch`(432)、`slash.exec`(1073)、
`insights.get`(1213)、`rollback.list`(1238)、`rollback.restore`(1268)、
`rollback.diff`(1320)、`browser.manage`(1343)、`plugins.list`(1360)、
`config.show`(1382)、`tools.list`(1423)、`tools.show`(1454)、`tools.configure`(1497)、
`toolsets.list`(1566)、`agents.list`(1596)、`cron.manage`(1620)、
`learning.frames`(1647)、`learning.detail`(1671)、`learning.delete`(1682)、
`learning.edit`(1693)、`skills.manage`(1704)、`skills.reload`(1763)、
`plugins.manage`(1788)、`shell.exec`(1867)。

**规模坐标(◇,§6-3)**:拆分后 `tui_gateway/server.py` 自己只剩 **10** 个 `@method`,
本片 5 个模块占 **123** 个 —— 即 92.5% 的 JSON-RPC 处理函数体已不在 server.py 里。

```verify
cd /home/user/hermes-agent && printf 'server.py: %s\nmethods_*: %s\n' \
  "$(grep -c '^@method(\"' tui_gateway/server.py)" \
  "$(grep -ch '^@method(\"' tui_gateway/methods_*.py | paste -sd+ | bc)"
```

### §3.2 `@_profile_scoped` 装饰面(12 条,逐个列全)

`@_profile_scoped` 把 `params["profile"]` 对应的 `HERMES_HOME` 绑到处理函数执行期间。

```verify
cd /home/user/hermes-agent && grep -n -B1 '^@_profile_scoped' tui_gateway/methods_*.py \
  | grep '@method(' | sed 's/-@method("/ /; s/")$//'
```

实测 12 条:`verification.status`(281)、`pet.info`(1326)、`pet.info.meta`(1352)、
`pet.cells`(1375)、`pet.gallery`(1480)、`pet.select`(1563)、`pet.remove`(1590)、
`pet.export`(1620)、`pet.rename`(1647)、`pet.thumb`(1685)、`pet.disable`(1720)、
`pet.scale`(1734)。

**没有**这个装饰器的 pet 方法有 4 个:`pet.cancel`(1755)、`pet.generate.status`(1769)、
`pet.generate`(1800)、`pet.hatch`(1913) —— 后两个是**写盘**方法,构成 §6-1 的 ■。

### §3.3 宿主监管的帧词汇表(三张表,逐项列全)

**(a) `MUTATOR_ROUTE_TABLE` —— 13 条**,是"哪些会改状态的操作允许穿过进程边界、
以及按什么并发策略穿"的**白名单**。不在表里的 `route_name` 直接抛异常。

`tui_gateway/host_supervisor.py:290 @ 863e313`

```python
        if route_name not in MUTATOR_ROUTE_TABLE:
            raise ValueError(f"unclassified host mutator route: {route_name}")
```

`tui_gateway/host_supervisor.py:31 @ 863e313`

```python
MUTATOR_ROUTE_TABLE: dict[str, str] = {
    "prompt.submit": "turn-path",
    "session.interrupt": "turn-path",
    "reload.mcp": "run-concurrent",
    "session.save": "run-concurrent",
    "session.compress": "idle-gated",
    "prompt.submit.truncate": "idle-gated",
    "slash.model": "idle-gated",
    "slash.personality": "idle-gated",
    "slash.prompt": "idle-gated",
    "slash.compress": "idle-gated",
    "session.reset": "idle-gated",
    "session.history.reload": "idle-gated",
    "slash.retry": "idle-gated",
}
```

三种策略的含义:`turn-path` = 走正常回合通道;`run-concurrent` = 可与在跑的回合并发;
`idle-gated` = 子进程侧会先查这个会话是否有回合在跑,忙则回 `control.error`。

`tui_gateway/compute_host.py:654 @ 863e313`

```python
            if route == "idle-gated" and session.get("running"):
                self.emit({"type": "control.error", "sid": sid, "request_id": request_id, "message": "session busy"})
                return
```

条数复核:

```verify
cd /home/user/hermes-agent && sed -n '31,45p' tui_gateway/host_supervisor.py | grep -c '": "'
```
→ `13`。

**(b) 父 → 子:compute host 认识的帧类型 —— 6 种 + 兜底**

```verify
cd /home/user/hermes-agent && sed -n '266,292p' tui_gateway/compute_host.py | grep -o 'kind == "[a-z_.]*"'
```

实测:`session.seed` / `turn.start` / `interrupt` / `reload_mcp` / `control` / `shutdown`,
其余落到 `{"type": "error", "message": f"unknown frame type: {kind}"}`。

**(c) 子 → 父:compute host 发出的帧类型 —— 14 种;监工只处理 11 种**

```verify
cd /home/user/hermes-agent && echo "--- emitted ---" && grep -o '"type": "[a-z_.]*"' tui_gateway/compute_host.py | sort -u
echo "--- handled by supervisor ---" && sed -n '415,452p' tui_gateway/host_supervisor.py \
  | grep -o 'ftype ==\? "[a-z_.]*"\|"[a-z_.]*\.ack"\|"control\.error"'
```

| 帧 | 子进程发出 | 监工处理 | 说明 |
|---|---|---|---|
| `hello` | ✓ | ✓ | 启动握手,携带 `boot_id` / `build_sha` / `hermes_home` / `cwd` |
| `hb` | ✓ | ✓(仅记录) | 心跳,带 `active_turns` / `progress_counter` / `rss_mb` |
| `rpc` | ✓ | ✓ | 把子进程里 agent 产生的 JSON-RPC 事件原样中继给客户端 |
| `turn.end` / `turn.error` | ✓ | ✓ | 结束回合,触发 `_complete_turn` 回调 |
| `control.ack` / `control.error` | ✓ | ✓ | 控制帧应答,喂回 `_pending_controls` 的 `queue` |
| `interrupt.ack` / `reload_mcp.ack` / `shutdown.ack` | ✓ | ✓ | 同上 |
| `error` | ✓ | ✓(仅当带 `request_id`) | 不带 `request_id` 的 `error` 帧被静默丢弃 |
| `turn.started` | ✓ | **✗** | 监工无分支,静默丢弃 |
| `delta` | ✓ | **✗** | 只在"spike"假回合路径产生,生产路径不用 |
| `session.seeded` | ✓ | **✗** | 只回应 `session.seed`,同样只有测试/spike 会发 |
| `orphan` | ✓ | **✗** | 子进程发现父进程换人时的**遗言**,监工不处理也不记日志 |
| `reload_mcp` | (内部重派发) | — | `tui_gateway/compute_host.py:658` 自己转手给 `_handle_reload_mcp`,不出管道 |

最后一列的 4 个"✗"构成 §6-5 的 ◇。

### §3.4 `project_tree.py` 的公开 API 与它铸造的 id 形状

模块层名字共 36 个:公开(无下划线)**8** 个,私有 **28** 个。
8 个公开名里 2 个是类型别名(`Resolve` / `Exists`,给注入的两个回调标注签名),
其余 6 个是下表这 6 个真正被外部用到的名字:

```verify
cd /home/user/hermes-agent && python3 - <<'EOF'
import ast
t = ast.parse(open('tui_gateway/project_tree.py', encoding='utf-8').read())
pub, priv = [], []
for n in t.body:
    names = []
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names = [n.name]
    elif isinstance(n, ast.Assign):
        names = [x.id for x in n.targets if isinstance(x, ast.Name)]
    elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
        names = [n.target.id]
    for nm in names:
        (priv if nm.startswith('_') else pub).append(nm)
print("public", len(pub), pub)
print("private", len(priv), priv)
EOF
```

实测 `public 8 [...]` / `private 28 [...]`。

| 名字 | 锚点 + 摘录 | 作用 |
|---|---|---|
| `build_tree` | `tui_gateway/project_tree.py:537`:`def build_tree(` | 唯一入口,返回 `{"projects": [...], "scoped_session_ids": [...]}` |
| `base_name` | `tui_gateway/project_tree.py:120`:`def base_name(path: str) -> str:` | 路径末段(不用 `os.path`,自己按 `[/\\]` 切) |
| `kanban_worktree_dir` | `tui_gateway/project_tree.py:125`:`def kanban_worktree_dir(path: str) -> Optional[str]:` | 认出 `<repo>/.worktrees/t_<hex>` 形状 |
| `DEFAULT_BRANCH_LABEL` | `tui_gateway/project_tree.py:50`:`DEFAULT_BRANCH_LABEL = "main"` | 无分支记录时的车道标签 |
| `NO_PROJECT_ID` | `tui_gateway/project_tree.py:57`:`NO_PROJECT_ID = "__no_project__"` | "无项目"合成桶的 id |
| `NO_PROJECT_LABEL` | `tui_gateway/project_tree.py:58`:`NO_PROJECT_LABEL = "Home"` | 该桶的显示名 |

它铸造的 **6 种 id 形状**在模块 docstring 里被声明为"与渲染器持久化状态字节兼容"
(改一个字就会让用户的置顶/排序/忽略状态失配):

`tui_gateway/project_tree.py:13 @ 863e313`

```python
  - explicit project id .......... ``p_<hex>`` (from projects.db)
  - auto/discovered project id ... the repo root path
  - home (no-project) bucket ..... ``__no_project__``
  - repo node id ................. the repo root path
  - main branch lane id .......... ``<repoRoot>::branch::<branch>`` (or ``::branch::``)
  - kanban bucket lane id ........ ``<repoRoot>::kanban``
  - linked worktree lane id ...... the worktree path
```

### §3.5 `git_probe.py` 的公开 API —— 7 个函数 + 1 个私有缓存类

```verify
cd /home/user/hermes-agent && grep -nE '^def ' tui_gateway/git_probe.py
```

`run_git`(45)、`branch`(58)、`invalidate`(125)、`repo_root`(130)、
`common_repo_root`(137)、`resolve`(159)、`warm_roots`(172) —— 7 个模块层 `def`,
其中 `run_git` 是底座,`_RootCache`(62)是唯一的私有类。
`tui_gateway/server.py` 侧把其中 5 个起了别名:

`tui_gateway/server.py:2371 @ 863e313`

```python
_git = git_probe.run_git
_git_branch_for_cwd = git_probe.branch
_git_repo_root_for_cwd = git_probe.repo_root
_git_common_repo_root_for_cwd = git_probe.common_repo_root
_resolve_cwd_git = git_probe.resolve
```

### §3.6 `slash_worker.py` 的进程协议 —— 2 个命令行参数 + 2 种报文 + 2 个环境旋钮

| 面 | 内容 |
|---|---|
| argv | `--session-key`(必填)、`--model`(可选);`tui_gateway/slash_worker.py:130`:`p.add_argument("--session-key", required=True)` |
| stdin | 每行一个 `{"id": <任意>, "command": "<斜杠命令>"}` |
| stdout | 成功 `{"id", "ok": true, "output"}`,失败 `{"id", "ok": false, "error"}`(输出前统一 `strip_ansi`) |
| env 旋钮 | `HERMES_SLASH_WATCHDOG_POLL_S`(默认 2.0)、`HERMES_SLASH_WATCHDOG_GRACE_S`(默认 5.0);`tui_gateway/slash_worker.py:49`:`_WATCHDOG_POLL_S = max(0.05, _env_float("HERMES_SLASH_WATCHDOG_POLL_S", 2.0))` |
| 进程内 env | 自己设两个变量:`tui_gateway/slash_worker.py:134`:`os.environ["HERMES_SESSION_KEY"] = args.session_key` |

`tui_gateway/slash_worker.py:166 @ 863e313`

```python
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            out = _run(cli, req.get("command", ""))
            sys.stdout.write(json.dumps({"id": rid, "ok": True, "output": out}) + "\n")
            sys.stdout.flush()
```

### §3.7 `synthetic_turn.py` 的接缝面 —— 3 个导出 + 5 个 env 旋钮

导出共 3 个。

`tui_gateway/synthetic_turn.py:227 @ 863e313`

```python
__all__ = [
    "SyntheticHeavyAgent",
    "maybe_build_synthetic_agent",
    "synth_turn_armed",
]
```

env 旋钮(全部可被 prompt 里的 JSON spec 覆盖):

| 变量 | 默认 | 含义 |
|---|---|---|
| `HERMES_ISO_CERTIFY_SYNTH_TURN` | 未设 | `=="1"` 才武装这个接缝;`tui_gateway/synthetic_turn.py:42`:`return os.environ.get("HERMES_ISO_CERTIFY_SYNTH_TURN") == "1"` |
| `HERMES_ISO_CERTIFY_DURATION_S` | 8.0 | 持有 GIL 的墙钟秒数 |
| `HERMES_ISO_CERTIFY_CHUNK` | 20000 | 每次中断检查之间的纯 Python 整数运算次数 |
| `HERMES_ISO_CERTIFY_DELTA_S` | 0.05 | 流式增量的发帧节奏 |
| `HERMES_ISO_CERTIFY_TPD` | 512 | 每个增量记账的名义输出 token 数 |

### §3.8 斜杠命令的**路由表面**(7 张集合,逐项列全)

这是回答问题 (c) 的骨架,7 张集合决定一条 `/xxx` 走哪条路:

```verify
cd /home/user/hermes-agent && python3 - <<'PYEOF'
import ast
tree = ast.parse(open('tui_gateway/server.py', encoding='utf-8').read())
want = {"_LIVE_SESSION_DIRECT_COMMANDS","_ISOLATED_SESSION_READ_COMMANDS",
        "_PENDING_INPUT_COMMANDS","_WORKER_BLOCKED_COMMANDS","_TUI_HIDDEN","_TUI_EXTRA"}
for node in tree.body:
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        tgts = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
        for t in tgts:
            if isinstance(t, ast.Name) and t.id in want:
                v = (ast.literal_eval(node.value.args[0])
                     if isinstance(node.value, ast.Call) else ast.literal_eval(node.value))
                print(f"{t.id}  n={len(v)}")
PYEOF
```

| 集合 | 条数 | 内容 | 效果 |
|---|---|---|---|
| `_LIVE_SESSION_DIRECT_COMMANDS` | 9 | clear, compress, effort, history, models, prompt, rename, status, usage | gateway **自己答**,不进 worker |
| `_ISOLATED_SESSION_READ_COMMANDS` | 3 | context, help, tools | 仅当会话跑在 compute host 上时 gateway 自己答 |
| `_PENDING_INPUT_COMMANDS` | 12 | compact, compress, goal, init, learn, moa, plan, q, queue, retry, steer, undo | 直接改派给 `command.dispatch`,**绕过 worker** |
| `_WORKER_BLOCKED_COMMANDS` | 2 | snap, snapshot | 其 `restore`/`rewind` 子命令在 `slash.exec` 里被拒 |
| `_TUI_HIDDEN` | 5 | approve, commands, deny, set-home, sethome | 从 `commands.catalog` 目录里**隐藏** |
| `_TUI_EXTRA` | 4 | /density, /logs, /mouse, /sessions | 目录里**额外补上**的 TUI-only 命令 |
| `_MUTATES_WHILE_RUNNING` | 4 | model, personality, prompt, compress | 在 `_mirror_slash_side_effects` 里"回合进行中拒绝执行" |

`command.dispatch` **自己实现**的命令分支(在 4 个动态查找之后)共 12 个 `if`:

```verify
cd /home/user/hermes-agent && awk 'NR>=432 && NR<=1071' tui_gateway/methods_tools.py \
  | grep -nE '^\s+if name (==|in) '
```

实测:`qcmds`(用户 quick_commands)、`{queue,q}`、`learn`、`init`、`moa`、`focus`、
`retry`、`steer`、`goal`、`undo`、`{snapshot,snap}`、`{compress,compact}`,
兜底 `4018 not a quick/plugin/bundle/skill command: <name>`。

---

## §4 端到端链:桌面里点"发送",在开了回合隔离时怎么走(逐跳带锚点)

场景:用户在 Electron 桌面 App 的输入框里敲 "帮我改一下这个函数" 回车。
这个会话是"懒会话"(打开聊天时只画了输入框,还没建 `AIAgent`),
且 `config.yaml` 里 `dashboard.turn_isolation: true`。

**跳 1 —— 客户端发 RPC。** 桌面渲染进程通过 `requestGateway("prompt.submit", {...})`
把 `{session_id, text}` 发到 WebSocket。落到 `tui_gateway/server.py` 的
`handle_request`(该函数在第 1891 行),查 `_methods["prompt.submit"]`。

**跳 2 —— `prompt.submit` 决定走不走隔离。**

`tui_gateway/methods_prompt.py:67 @ 863e313`

```python
@method("prompt.submit")
def _(rid, params: dict) -> dict:
    from hermes_cli.input_sanitize import sanitize_user_prompt_text
```

先做输入净化与"打字版语音停止短语"检查,再取会话、抢活跃会话名额,然后:

`tui_gateway/methods_prompt.py:124 @ 863e313`

```python
    isolation_cfg = _load_dashboard_process_isolation_config()
    turn_isolation = _session_uses_compute_host(session, isolation_cfg)
```

判据是:开关打开、且(这个会话之前已被宿主接管 `_compute_host_active`,
或者它还没建 agent 但注册了 `agent_ready` 事件)。

`tui_gateway/server.py:1604 @ 863e313`

```python
def _session_uses_compute_host(session: dict, cfg: dict | None = None) -> bool:
    if not _turn_isolation_enabled(cfg):
        return False
```

换句话说:**懒会话/桌面会话走隔离,已经在进程内建好 agent 的老会话不动。**

**跳 3 —— 抢下"我在跑"标记并派给宿主。** 抢标记与派发是分开的两步:

`tui_gateway/methods_prompt.py:241 @ 863e313`

```python
        session["running"] = True
        session["_turn_cancel_requested"] = False
        session["last_active"] = time.time()
        _start_inflight_turn(session, text)

    if turn_isolation:
        isolated_response = _submit_prompt_to_compute_host(rid, sid, session, text)
        if not isolated_response.get("error"):
            return isolated_response
```

`tui_gateway/server.py` 的 `_submit_prompt_to_compute_host`(第 1733 行)组装
`type: "turn.start"` 帧(带 `history` / `history_version` / `cwd` / `cols` /
`profile_home` / `model_override` …,由同文件第 1629 行的 `_compute_host_turn_frame` 生成),
然后 `_get_compute_host_supervisor(cfg).submit_turn(frame, on_complete=_complete)`。
**注意 `rpc_sink=write_json`** —— 监工把子进程转发上来的事件直接写回客户端:

`tui_gateway/server.py:1620 @ 863e313`

```python
            from tui_gateway.host_supervisor import HostSupervisor

            _compute_host_supervisor = HostSupervisor(
                rpc_sink=write_json,
                heartbeat_secs=int(isolation_cfg.get("compute_host_heartbeat_secs") or 15),
                respawn_max=int(isolation_cfg.get("compute_host_respawn_max") or 3),
            )
```

**跳 4 —— 监工登记 + 写管道。**

`tui_gateway/host_supervisor.py:238 @ 863e313`

```python
    def submit_turn(
        self,
        frame: dict[str, Any],
        *,
        on_complete: Callable[[dict], None] | None = None,
    ) -> str:
```

它先 `self.start()`(必要时拉起子进程,见 §5.2),把 `request_id → (sid, on_complete)`
记进 `_pending_turns`,再 `_send_frame`:

`tui_gateway/host_supervisor.py:388 @ 863e313`

```python
    def _send_frame(self, frame: dict[str, Any]) -> None:
        with self._lock:
            proc = self._proc
            if proc is None or proc.poll() is not None or proc.stdin is None:
                raise RuntimeError("compute host is not running")
            proc.stdin.write(json.dumps(frame, separators=(",", ":"), ensure_ascii=False) + "\n")
            proc.stdin.flush()
```

**跳 5 —— 子进程读帧、丢进线程池。** 子进程的 `run_host` 起一个
`compute-host-control-reader` 线程逐行读 stdin(`tui_gateway/compute_host.py` 第 844 行),
交给同文件第 266 行的 `handle_frame` → `_handle_turn_start`:

`tui_gateway/compute_host.py:321 @ 863e313`

```python
    def _handle_turn_start(self, frame: dict[str, Any]) -> None:
        sid = str(frame.get("sid") or "")
        if sid in self._sessions:
            self._handle_spike_turn_start(frame)
            return
        future = self._executor.submit(self._run_real_turn, dict(frame))
        self._track_turn_future(future, sid)
```

`self._sessions` 只被 `session.seed` 填充(测试/spike 用),生产路径为空,
所以真实回合走 `_run_real_turn`。

**跳 6 —— 子进程里 `import tui_gateway.server`,在自己的进程里建 agent、跑回合。**
这是整个设计最反直觉的一跳:**子进程导入的是同一个 `server` 模块**,于是所有
`server._sessions` / `_make_agent` / `_run_prompt_submit` 逻辑一字不改地在子进程里复用。
`_ensure_server_session`(`tui_gateway/compute_host.py` 第 524 行)负责在子进程侧建会话:如果
`profile_home` 非空,先 `set_hermes_home_override` + `set_secret_scope` + 另开一个
`SessionDB`,再 `server._make_agent(...)`,最后把会话的 `transport` 换成 `_HostTransport`。
然后:

`tui_gateway/compute_host.py:485 @ 863e313`

```python
            text = frame.get("text") if "text" in frame else frame.get("prompt", "")
            server._run_prompt_submit(request_id, sid, session, text)
            run_thread = session.get("_run_thread")
            if run_thread is not None and hasattr(run_thread, "join"):
                run_thread.join()
```

**跳 7 —— 流式事件回程:`_HostTransport` 把每个 RPC 事件包成 `rpc` 帧。**
子进程里的 agent 照常调 `transport.write({jsonrpc, method:"event", params:{...}})`,
但这个 transport 是:

`tui_gateway/compute_host.py:90 @ 863e313`

```python
class _HostTransport:
    def __init__(self, emit: Callable[[dict[str, Any]], None]) -> None:
        self._emit = emit

    def write(self, obj: dict) -> bool:
        sid = ""
        try:
            if obj.get("method") == "event":
                sid = str(((obj.get("params") or {}).get("session_id")) or "")
        except Exception:
            sid = ""
        self._emit({"type": "rpc", "sid": sid, "message": obj})
        return True
```

`emit` 加上 `host_ns` 时间戳,`json.dumps` 后在 `_write_lock` 保护下写 stdout。

`tui_gateway/compute_host.py:170 @ 863e313`

```python
    def emit(self, frame: dict[str, Any]) -> None:
        frame.setdefault("host_ns", now_ns())
        data = json.dumps(frame, separators=(",", ":"), ensure_ascii=False)
        with self._write_lock:
            print(data, file=self._stdout, flush=True)
```

**跳 8 —— 监工拆包、原样喂回客户端。** 父进程的 `compute-host-stdout` 线程逐行
`json.loads`,交 `_handle_host_frame`。

`tui_gateway/host_supervisor.py:396 @ 863e313`

```python
    def _drain_stdout(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        for raw in proc.stdout:
            try:
                frame = json.loads(raw)
```

`tui_gateway/host_supervisor.py:425 @ 863e313`

```python
        if ftype == "rpc":
            message = frame.get("message")
            if isinstance(message, dict):
                self.rpc_sink(message)
            return
```

`rpc_sink` 就是跳 3 传进来的 `server.write_json`(`tui_gateway/server.py` 第 1511 行),
它把这条 JSON-RPC 事件写到当前客户端 transport —— **桌面收到的 `message.delta`
与不开隔离时一模一样**。这是这套设计的核心取舍:进程边界对客户端**完全透明**,
代价是所有会话状态在子进程里有第二份。

**跳 9 —— 收尾。** 子进程发 `turn.end`(带 `history_version` / `message_count` /
`session_info`),监工 `_complete_turn`(`tui_gateway/host_supervisor.py` 第 453 行)
从 `_pending_turns` 弹出回调,调用 `_on_compute_host_turn_done`
(`tui_gateway/server.py` 第 1704 行)把版本号与 `session_info`
镜像回父进程的会话字典,并清掉 `running`。

**降级路径(重要)**:如果跳 3 返回带 `error` 的响应,`prompt.submit` **不报错**,
而是打一条 warning 后继续走进程内老路:

`tui_gateway/methods_prompt.py:250 @ 863e313`

```python
        logger.warning(
            "compute-host dispatch failed for session %s; falling back inline: %s",
            sid,
            isolated_response["error"].get("message", "unknown error"),
        )
```

这条降级把 §5.2 的"重启上限用尽后永久熄火"从"功能中断"降为"性能退化"。

---

## §5 逐机制结构笔记

### §5.1 五个 `methods_*` 是怎么在不改一个字节的前提下从 server.py 搬出来的

问题:server.py 的 ~130 个处理函数都**闭包在模块全局上**(`_sessions`、`_ok`、`_err`、
一堆配置助手),很多还写 `global X` 去改 server.py 的模块状态。
要把它们从 19,000 行的文件里搬走,常规做法是逐个改成显式传参 —— 那等于重写 130 个函数体。

hermes 的做法是 `tui_gateway/method_ctx.py`(54 行,不在本片但是本片的契约方):
每个 `methods_*` 模块用一个本地 `HandlerRegistry` 收集 `(名字, 函数)`,
server.py 在**自己 import 的最后一行**(等所有全局都存在了)调用 `install`,
用 `types.FunctionType` 把每个函数的 `__globals__` **重绑到 server.py 的命名空间**:

`tui_gateway/method_ctx.py:43 @ 863e313`

```python
        g = vars(server)
        for name, fn in self._pending:
            real = types.FunctionType(
                fn.__code__, g, fn.__name__, fn.__defaults__, fn.__closure__
            )
            real.__kwdefaults__ = fn.__kwdefaults__
            real.__doc__ = fn.__doc__
            real.__dict__.update(fn.__dict__)
            if getattr(fn, "_hermes_profile_scoped", False):
                real = server._profile_scoped(real)
            server._methods[name] = real
```

于是函数体里的 `_sessions`、`_ok`、`global _paste_counter` 全部照旧命中 server.py 的模块状态。
反向 import 环的规避方式是:`methods_*` **在模块层从不 import server**,
是 server 在自己文件末尾 import 它们并把自己传进 `register()`:

`tui_gateway/server.py:13990 @ 863e313`

```python
from . import (  # noqa: E402
    methods_complete as _methods_complete,
    methods_config as _methods_config,
    methods_prompt as _methods_prompt,
    methods_session as _methods_session,
    methods_tools as _methods_tools,
)

for _m in (
    _methods_session,
    _methods_prompt,
    _methods_config,
    _methods_complete,
    _methods_tools,
):
    _m.register(sys.modules[__name__])
del _m
```

**可迁移的教训**:这是一次纯机械拆分,代价明确写在 docstring 里 —— 换来的是
"函数体逐字未变、review diff 只有搬动",付出的是"这五个文件**单独读不懂**"
(每个 `_(rid, params)` 里的自由变量都得回 server.py 查)。`methods_prompt.py`
的 `register()` 甚至要为一个**非 `@method`** 的辅助函数手工重复一遍同样的重绑:

`tui_gateway/methods_prompt.py:943 @ 863e313`

```python
    server._pending_reaction_notes = types.FunctionType(
        _pending_reaction_notes.__code__,
        vars(server),
        _pending_reaction_notes.__name__,
        _pending_reaction_notes.__defaults__,
        _pending_reaction_notes.__closure__,
    )
```

也就是说这套机制**只自动处理带装饰器的处理函数**,任何被搬出来的普通函数都要手工补一行。
这是拆分方案里最容易在下一次搬迁时漏掉的地方。

### §5.2 问题 (a):宿主监管在管什么、怎么判死、怎么重启、上限多少

**管什么进程。** 恰好一个持久子进程:

`tui_gateway/host_supervisor.py:148 @ 863e313`

```python
        self.registry_path = Path(registry_path) if registry_path is not None else _default_registry_path()
        self.argv = argv or [sys.executable, "-m", "tui_gateway.compute_host"]
        self.cwd = Path(cwd) if cwd is not None else _repo_root()
```

它只在 `dashboard.turn_isolation` 打开时才被创建(默认 `False`,
`tui_gateway/server.py:2882`:`_DASHBOARD_TURN_ISOLATION_DEFAULT = False`),
**懒创建、进程内单例**(`tui_gateway/server.py:1615` 的 `_get_compute_host_supervisor` + 一把锁)。

**为什么要有它。** 不是为了隔离崩溃,是为了 **GIL**。`synthetic_turn.py` 的 docstring
把病理写得最清楚:并发的重回合在**服务进程的线程里**跑纯 Python 计算,
CPython 的单 GIL 让这些线程把负责冲刷 WebSocket 帧的事件循环线程**饿死好几分钟**
—— 2026-07-04 的一次 `sample` 抓到循环线程停在 `take_gil` 上,
**不是**阻塞在 I/O。把回合搬进另一个进程 = 换一个解释器 = 换一把 GIL。

**子进程怎么被启动。** `_spawn_locked`(`:313`)组装环境:
`hermes_subprocess_env(inherit_credentials=True)` 打底、叠 `os.environ`、叠构造参数、
写入 `HERMES_COMPUTE_HOST_HEARTBEAT_SECS`、把仓库根塞进 `PYTHONPATH` 头部,
然后 `subprocess.Popen(..., text=True, encoding="utf-8", errors="replace", bufsize=1,
start_new_session=True)`。`errors="replace"` 有事故背书(#52649:locale 不匹配的字节
会在 drain 线程里抛异常并把监工带走)。启动后开三个守护线程:
`compute-host-stdout` / `compute-host-stderr` / `compute-host-wait`。

**怎么判死 —— 四条独立机制。**

| 机制 | 锚点 + 摘录 | 判据 |
|---|---|---|
| 启动握手超时 | `tui_gateway/host_supervisor.py:349`:`if not self._hello_event.wait(timeout=10.0):` | 10 秒内没收到 `hello` → 杀掉并抛 `RuntimeError`,错误里带最后 5 行 stderr |
| 身份校验 | `tui_gateway/host_supervisor.py:356`:`def _validate_hello(self) -> None:` | `hermes_home` 不一致、或 `build_sha` 与父进程的 `git rev-parse HEAD` 不一致 → 拒收(防"旧代码的僵尸子进程接管新会话") |
| 存活轮询 | `tui_gateway/host_supervisor.py:185`:`def is_running(self) -> bool:` | `proc.poll() is None` **且** 没被崩溃循环熄火 |
| 退出监听线程 | `tui_gateway/host_supervisor.py:466`:`def _wait_for_exit(self, proc: subprocess.Popen[str]) -> None:` | `proc.wait()` 返回即认定死亡;非主动关闭时清 `_proc`、删登记文件、把所有在飞回合以 `reason="crash"` 失败掉、再决定是否重生 |

**判死里最讲究的一处是"孤儿收养 + PID 复用防护"。** 上一次 dashboard 崩了、留下一个
还在跑的 compute host,新 dashboard 启动时要杀掉它 —— 但登记文件里的 PID 可能已经被
操作系统分配给了**别的无关进程**,直接 `SIGTERM` 就是杀错人:

`tui_gateway/host_supervisor.py:226 @ 863e313`

```python
        if pid <= 0 or not _pid_alive(pid):
            self._remove_registry()
            return "not-running"
        if not self._pid_matches_compute_host(pid):
            # PID was reused by another process. Never signal it.
            self._remove_registry()
            return "pid-reuse-ignored"

        self._terminate_pid(pid, timeout=_SHUTDOWN_TIMEOUT_SECS)
        self._remove_registry()
        return "terminated"
```

身份验证不靠猜,靠**直接读 `/proc/<pid>/cmdline`**(Linux 快路径),
不行再退回 `ps -p <pid> -o command=`:

`tui_gateway/host_supervisor.py:126 @ 863e313`

```python
def is_compute_host_identity(pid: int) -> bool:
    cmd = _pid_command(pid)
    return "tui_gateway.compute_host" in cmd
```

有测试钉住这条。

`tests/tui_gateway/test_compute_host_phase1.py:96 @ 863e313`

```python
    result = supervisor.reconcile_startup_orphan()

    assert result == "pid-reuse-ignored"
```

**怎么重启 + 失败上限。** 上限是 **5 分钟窗口内最多 `respawn_max` 次(默认 3)**:

`tui_gateway/host_supervisor.py:507 @ 863e313`

```python
    def _maybe_respawn_after_crash(self) -> None:
        now = time.monotonic()
        self._restart_times = [t for t in self._restart_times if now - t <= _RESPAWN_WINDOW_SECS]
        if len(self._restart_times) >= self.respawn_max:
            self._stopped_respawning = True
            logger.error("compute host crash loop: max %s restarts per 5min reached; not respawning", self.respawn_max)
            return
        self._restart_times.append(now)
        # Small bounded backoff; tests and first recovery stay quick.
        delay = min(5.0, 0.25 * (2 ** max(0, len(self._restart_times) - 1)))
```

| 参数 | 值 | 锚点 + 摘录 |
|---|---|---|
| 窗口 | 300 秒 | `tui_gateway/host_supervisor.py:48`:`_RESPAWN_WINDOW_SECS = 300.0` |
| 上限 | 3(可配,下限 0) | `tui_gateway/server.py:2884`:`_DASHBOARD_COMPUTE_HOST_RESPAWN_MAX_DEFAULT = 3` |
| 退避 | 0.25s → 0.5s → 1.0s,上限 5s | 上面 `delay = min(5.0, 0.25 * (2 ** ...))` |
| 关停超时 | 10 秒后 SIGKILL | `tui_gateway/host_supervisor.py:49`:`_SHUTDOWN_TIMEOUT_SECS = 10.0` |
| 心跳 | 15 秒(可配,下限 1) | `tui_gateway/server.py:2883`:`_DASHBOARD_COMPUTE_HOST_HEARTBEAT_SECS_DEFAULT = 15` |

**熄火是永久的**:`_stopped_respawning` 全仓只在 `:511` 被置 `True`,构造时置 `False`
之后再无任何复位点(搜索面:全仓 `*.py`,模式 `_stopped_respawning`,共 5 处命中,
见 §6-2 的 verify 块)。此后 `is_running()` 恒 `False`、`_spawn_locked` 抛
`RuntimeError("compute host respawn disabled after crash loop")`(`:314`),
每次 `prompt.submit` 都走跳 3 的降级路径回到进程内执行 —— **不中断服务,但隔离特性
在这个进程的余生里彻底失效,且用户端只看到一条日志**。

**反向监管:子进程也在盯父进程。** compute host 每秒查一次 `getppid()`,
父进程换人(被 init 收养,或 ppid 变了)就发遗言、冲刷会话、`os._exit(0)`:

`tui_gateway/compute_host.py:790 @ 863e313`

```python
    def _parent_guard_loop(self) -> None:
        while not self._closed.wait(1.0):
            ppid = os.getppid()
            if ppid in {0, 1} or (self._parent_pid and ppid != self._parent_pid):
                self.emit({"type": "orphan", "old_ppid": self._parent_pid, "ppid": ppid})
                self.shutdown(reason="orphan")
                os._exit(0)
```

`shutdown` 的顺序被 40 行 docstring 反复强调(`tui_gateway/compute_host.py:180-221`):
**先排空在飞回合、再 finalize**,因为 `_finalize_session` 是**一次性闩锁**,
在回合还在产出时用掉这唯一机会,尾巴就永久无法持久化。
`_FLUSH_RESERVE_SECS = 1.0`(`:132`)从预算里扣一秒留给 finalize,
且"不超过预算的一半",这样短 `wait` 仍能真排空一会儿。

**同样的持久化,`slash_worker` 有一套更简单的孤儿看门狗**:轮询 `getppid()` 变化,
变了就给在飞命令一个 `_ORPHAN_GRACE_S`(默认 5 秒)的宽限,然后 `os._exit(0)`
(`tui_gateway/slash_worker.py:81-90`)。它在 `HermesCLI` 构建**之前**就启动,
因为那几百毫秒本身就是孤儿风险窗口。

### §5.3 问题 (b):`synthetic_turn.py` 的"合成回合"到底是什么

**先纠正一个可能的预设**:这个文件**不是**"界面需要一个并非用户发起的回合"那种合成回合。
它是**一个测试接缝**,造的是一个**假的 `AIAgent`**,唯一职责是**持有 GIL 狂烧 CPU**。

它解决的问题是"怎么证明进程隔离真的修好了 GIL 饿死"。要复现那个病理,需要
6 个并发的 100K+ 上下文真实模型调用 —— 烧真金白银,而且不确定。
但**不能用睡眠或网络桩代替**:

`tui_gateway/synthetic_turn.py:13 @ 863e313`

```python
A network/sleep stub is WRONG here — it would release the GIL during I/O and
never reproduce ``take_gil`` contention, so a dry-run green off it is a fake
green (the spec says so explicitly).
```

所以它的回合是一段**紧凑整数循环**,一条字节码一步,永不释放 GIL:

`tui_gateway/synthetic_turn.py:165 @ 863e313`

```python
        while True:
            if self._interrupt.is_set():
                interrupted = True
                break
            now = time.monotonic()
            if now - start >= duration:
                break
            # GIL-holding pure-Python work. A tight integer loop runs one
            # bytecode step per iteration and NEVER releases the GIL — this is
            # the exact interpreter contention that starves the serving loop.
            for _ in range(chunk):
                acc = (acc * 1_000_003 + 12_345) & 0xFFFFFFFFFFFFFFFF
```

**这个假 agent 只实现"服务端真正会读的那些属性"**:`run_conversation` /
`interrupt` / `clear_interrupt` / `close`,加一把 `model` / `provider` / `api_mode` /
`session_*_tokens` 计数器(供状态栏的 `_get_usage` 与 `_session_info` 读),
`tokens_per_delta` 每次增量给计数器加数,冒充一个"重回合"。

**接缝点选得很讲究**:它挂在 `_make_agent` 上 ——

`tui_gateway/server.py:6304 @ 863e313`

```python
    # AC-4 test seam: dead unless explicitly armed by the isolated certify
    # harness. Both inline and compute-host paths construct through _make_agent,
    # leaving the process boundary as the only experimental variable.
    from tui_gateway.synthetic_turn import maybe_build_synthetic_agent

    synthetic = maybe_build_synthetic_agent(session_id or key, model_override)
    if synthetic is not None:
        return synthetic
```

因为**进程内路径与 compute-host 路径都经过 `_make_agent`**,同一个合成回合能同时
驱动两条派发路径,于是"开隔离 / 关隔离"两次跑之间**唯一变量就是进程边界**。
这是一条可复用的实验设计原则:**要度量一个边界的效果,把桩打在边界两侧共用的那个构造点上。**

强度参数不写死在服务端,而是**藏在 prompt 文本里当 JSON spec 传**
(`_parse_spec`,`:110`),服务端的接缝保持"傻":任何不是 JSON 对象的 prompt
就回落到 env / 内置默认值。

被谁用:认证脚本在起子进程前武装它。

`scripts/iso-certify.py:174 @ 863e313`

```python
        env["HERMES_ISO_CERTIFY_SYNTH_TURN"] = "1"
```

被谁钉:`tests/tui_gateway/test_iso_certify_seam.py`(未武装时 `synth_turn_armed()`
为 `False` 且 `maybe_build_synthetic_agent("sid")` 返回 `None`)。实测通过:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
  /home/user/hermes-venv/bin/python -m pytest \
  tests/tui_gateway/test_project_tree.py tests/tui_gateway/test_iso_certify_seam.py -q 2>&1 | tail -3
```
→ `28 passed`。

### §5.4 问题 (c):`slash_worker` 与 CLI 的斜杠命令是同一套还是两套

**答案:一套半。** 主干是**同一套**(worker 里跑的就是真正的 `HermesCLI`),
但外面套了**三层 gateway 自己的第二实现**,而且**守卫的分布不对称**。

**同一套的证据。** `slash_worker` 的整个"执行"就是构造一个真 `HermesCLI`
并调它的 `process_command`:

`tui_gateway/slash_worker.py:143 @ 863e313`

```python
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        cli = HermesCLI(model=args.model or None, compact=True, resume=args.session_key, verbose=False)
```

`tui_gateway/slash_worker.py:111 @ 863e313`

```python
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            cli.process_command(cmd)
    finally:
        if old is not None:
            cli_mod._cprint = old
```

它连 Rich(Python 的终端富文本库)的 `Console` 都换成写进 buffer 的版本 ——
因为 `Console` 在构造时就捕获了文件句柄,`redirect_stdout` 对它无效。

`tui_gateway/slash_worker.py:102 @ 863e313`

```python
    # Rich Console captures its file handle at construction time, so
    # contextlib.redirect_stdout won't affect it. Swap the console's
    # underlying file to our buffer so self.console.print() is captured.
    cli.console = Console(file=buf, force_terminal=True, width=120)
```

最后统一 `strip_ansi` —— 桌面聊天气泡渲染纯文本,不是 ANSI。

**第二实现之一:`_live_slash_command_output`。**

`tui_gateway/server.py:12427 @ 863e313`

```python
def _live_slash_command_output(sid: str, session: Optional[dict], name: str, arg: str) -> Optional[str]:
    name = (name or "").lstrip("/").lower()
    arg = arg or ""
```

9 + 3 个命令名由 gateway **直接答**,根本不进 worker。理由是**状态归属**:
worker 是**另一个进程**,它的 `HermesCLI` 有自己的 agent 快照,
问它 `/usage`、`/history`、`/context`、`/status` 得到的是**它自己的**数字,
不是这个会话的活 agent 的数字。

**第二实现之二:`command.dispatch`。**

`tui_gateway/methods_tools.py:432 @ 863e313`

```python
@method("command.dispatch")
def _(rid, params: dict) -> dict:
    name, arg = params.get("name", "").lstrip("/"), params.get("arg", "")
```

12 个 `if name` 分支(§3.8 末尾)在 gateway 进程里**重新实现**了 CLI 的
`/queue` `/learn` `/init` `/moa` `/focus` `/retry` `/steer` `/goal` `/undo`
`/snapshot` `/compress`。触发理由写在代码里:

`tui_gateway/methods_tools.py:571 @ 863e313`

```python
    # ── Commands that queue messages onto _pending_input in the CLI ───
    # In the TUI the slash worker subprocess has no reader for that queue,
    # so we handle them here and return a structured payload.
```

即 CLI 版这些命令是"把文本塞进 `self._pending_input` 队列,由主循环取出当成一次用户输入",
而 worker 子进程**没有那个主循环**,塞进去就没了。所以必须在 gateway 侧重写成
"返回一个 `{"type": "send", "message": ...}` 结构,让客户端再发一次 `prompt.submit`"。

**第二实现之三:`_mirror_slash_side_effects`。**

`tui_gateway/server.py:12487 @ 863e313`

```python
def _mirror_slash_side_effects(sid: str, session: dict, command: str) -> str:
    """Apply side effects that must also hit the gateway's live agent."""
    parts = command.lstrip("/").split(None, 1)
```

worker 在自己进程里执行完 `/model` `/personality` `/prompt` `/compress` 之后,
gateway 还得把**同样的副作用重新打到自己那份活 agent 上** —— 因为 worker 改的是
worker 进程的对象。这 4 个名字就是 `_MUTATES_WHILE_RUNNING`。

**`slash.exec` 的完整决策顺序**(`tui_gateway/methods_tools.py` 第 1073 行起,共 7 级):

```text
slash.exec(command)
  0. _sess_nowait  —— 只查会话存在,不等 agent、不看回合是否在跑
  1. _live_slash_command_output  → 命中就直接返回 gateway 自己算的输出
  2. _cmd_base ∈ _PENDING_INPUT_COMMANDS (12) → 改派 command.dispatch,不进 worker
  3. _cmd_base ∈ _WORKER_BLOCKED_COMMANDS (2) 且子命令是 restore/rewind → 4018 拒绝
  4. 是 skill bundle → 改派 command.dispatch
  5. 是 skill 命令 → 4018 "use command.dispatch"
  6. 是插件命令 → gateway 进程内直接调插件 handler
  7. 以上都不是 → 首次使用时按会话加锁 spawn _SlashWorker,worker.run(cmd),
     然后 _mirror_slash_side_effects 把副作用镜像到活 agent
```

第 7 级的"按会话加锁"本身是一个并发教训:on-demand spawn 是**唯一**的 spawn 路径
(预热已被移除),而 `slash.exec` 跑在 RPC 线程池上,两条并发的斜杠命令会双双看到
`slash_worker=None` 各 fork 一个"完整 MCP 舰队"的 worker,输掉 `_attach_worker`
竞争的那个会泄漏。

`tui_gateway/methods_tools.py:1180 @ 863e313`

```python
        # MCP-fleet worker (the loser of the _attach_worker race would leak
        # unclosed). Serialize first-use spawn per session.
        with _sessions_lock:
            spawn_lock = session.setdefault("_slash_spawn_lock", threading.Lock())
        with spawn_lock:
```

**顺序带来的一个反直觉但正确的结果**(我一开始判错、复查后撤回):
`plan` 在 `_PENDING_INPUT_COMMANDS` 里,但 `command.dispatch` **没有** `if name == "plan"`
分支。看着像"路由到了一个不实现它的地方"。实际上 `/plan` 是**捆绑技能**
`skills/software-development/plan/SKILL.md`(`name: plan`),
`command.dispatch` 在 12 个硬编码分支**之前**先查了技能表,所以它在那里被解析成
`{"type": "skill", ...}`。

`tui_gateway/methods_tools.py:550 @ 863e313`

```python
        cmds = scan_skill_commands()
        key = f"/{name}"
        if key in cmds:
```
反过来说:如果 `plan` 不在 `_PENDING_INPUT_COMMANDS` 里,`slash.exec` 第 5 级会返回
`4018 skill command: use command.dispatch for /plan`,逼客户端再发一次 —— 那条表项
正是为了省掉这次往返(注释里点名 #48848)。

**守卫只装在其中一处 —— 这就是本片最重的一条 ■(详见 §6-1)。**
"回合进行中不许原地换模型"这条不变式,项目自己的测试写得斩钉截铁:

`tests/test_tui_gateway_server.py:10160 @ 863e313`

```python
# /model switch and other agent-mutating commands must reject while the
# session is running.  agent.switch_model() mutates self.model, self.provider,
# self.base_url, self.client etc. in place — the worker thread running
# agent.run_conversation is reading those on every iteration.  So a mid-turn
# config.set model must NOT switch in place; instead it queues the pick
# (session["pending_model_switch"]) and _apply_pending_model_switch applies it
# on the turn thread at the next turn start, where nothing is in flight.
```

三个调用 `_apply_model_switch` 的**面向用户**入口里,两个守住了,一个没有:

| 入口 | 守卫 | 锚点 + 摘录 |
|---|---|---|
| `config.set key=model` | ✓ 延后到下个回合开头 | `tests/test_tui_gateway_server.py:10170`:`def test_config_set_model_defers_while_running(monkeypatch):` |
| `/model <x>` → worker → 镜像 | ✓ 直接拒绝 | `tui_gateway/server.py:12526`:`if name in _MUTATES_WHILE_RUNNING and session.get("running"):` |
| `/moa <prompt>` → `command.dispatch` | **✗ 无任何检查** | `tui_gateway/methods_tools.py:623`:`_apply_model_switch(` |

### §5.5 问题 (d):`project_tree` 与 `git_probe` 把什么暴露给界面、有没有路径边界

**`project_tree.build_tree` 暴露什么。** 它的返回值就是桌面侧边栏的全部数据:
`{"projects": [...], "scoped_session_ids": [...]}`。每个 project 节点携带
`id / label / path / color / icon / isAuto / isNoProject / sessionCount / lastActive /
repos / previewSessions`(`tui_gateway/project_tree.py:522-534`),`repos` 里每个仓库带
`id / label / path / groups / sessionCount`,每个 group(车道)带
`id / label / path / isMain / isKanban / sessions`。

也就是说 **gateway 主机上的绝对文件系统路径**(仓库根、链接 worktree 路径、
`.worktrees` 目录、每个会话的 cwd)会作为 id 与 `path` 字段**原样**发给客户端。
这在"gateway 与客户端同机"的模型下无所谓;在跨机的桌面/仪表盘场景下,
它就是一张"这台机器上有哪些项目目录"的清单。

**它的三层归属判定**(纯函数,git 解析全靠注入的 `resolve`):

```text
Tier 1  显式项目(projects.db 里用户建的) —— _FolderIndex 按 cwd 的最长祖先目录匹配
Tier 2  自动项目 —— 剩下的会话按"公共 git 根"、否则按 cwd 归堆
Tier 3  发现的仓库 —— 全历史/磁盘扫描出的零会话仓库
Tier 0  Home 桶 —— 上面都放不下的会话("__no_project__"),插在列表最前
```

**有没有路径边界检查?—— 三个层次的答案。**

**(1) `project_tree.py` 自己:没有,而且它唯一的包含性判定是死代码。**
模块里有一个专门写来判断"target 是不是在 folder 底下"的函数:

`tui_gateway/project_tree.py:131 @ 863e313`

```python
def _is_path_under(folder: str, target: str) -> bool:
    """True when ``target`` equals ``folder`` or is nested under it (segment-wise)."""
    f = _comparison_segments(folder)
    t = _comparison_segments(target)
    if not f or len(f) > len(t):
        return False
    return all(f[i] == t[i] for i in range(len(f)))
```

它在**全仓一次也没被调用过**(搜索面:全仓 `*.py`,模式 `_is_path_under`,
唯一命中就是它自己的定义行;见 §6-6 的 verify 块)。
真正在做归属匹配的是 `_FolderIndex.match`(`:471`),用"最长祖先前缀查 dict"实现,
路径拼接与比较全部自己用正则做(`_segments` 按 `[/\\]` 切、
Windows 路径 `casefold`),**不碰 `os.path`、不 `realpath`、不解 symlink**:

```verify
cd /home/user/hermes-agent && grep -nE 'commonpath|commonprefix|realpath|relative_to|expanduser|os\.path' tui_gateway/project_tree.py; echo "exit=$?"
```
→ 无输出,`exit=1`。整个 768 行里**一次 `os.path` 都没有**,连 `import os` 都没有
(它是纯字符串/正则处理,这也是它能被纯单元测试覆盖的原因)。

反过来,它还**主动向上走**:`_probe_sibling_worktree`(`:176`)为了把一个**已删除**的
`<repo>-<suffix>` worktree 认领回它的父仓库,会沿 `_parent_dir` 逐级上溯、
对每级祖先按名字裁掉 `-<段>` 去 `resolve()` 探测,上限 4 次 git 探测
(`_MAX_SIBLING_PROBES = 4`,`:63`)。也就是说它会对**会话 cwd 之外的兄弟路径**发起 git 探测。

**(2) `git_probe.py`:没有边界,`cwd` 给什么就在什么目录跑 git。**

`tui_gateway/git_probe.py:45 @ 863e313`

```python
def run_git(cwd: str, *args: str) -> str:
    """``git -C <cwd> <args>`` → stripped stdout, or ``""`` on any failure.

    Uses the shared :func:`bounded_git_probe` so the post-kill cleanup is bounded
    on Windows — a plain ``subprocess.run(timeout=...)`` here deadlocked Desktop
    session readiness when a killed git left a suspended descendant holding the
    pipe handles (issue #68609).
    """
    if not cwd:
        return ""
    return bounded_git_probe(["git", "-C", cwd, *args], timeout=_GIT_TIMEOUT)
```

唯一的校验是"非空",超时 1.5 秒。它读到的东西也就是 git 愿意说的:
`rev-parse --show-toplevel`、`--git-common-dir`、`branch --show-current`。
缓存设计值得学:正结果永久缓存、负结果只缓存 `_NEG_TTL = 30.0` 秒
—— 因为新项目的第一个 worktree 是被 `git init` 出来的,冻结的 `""`
会让主车道被目录名误标;而 30 秒足以把"一次侧边栏构建里成百次重复探测"塌掉
(`tui_gateway/git_probe.py:12-22` 记录了这就是"Projects 加载要好几秒"的病根)。
`_RootCache.resolve`(`:80`)是**单飞**的:后到的线程等领头线程的探测结果,
而不是各跑一个 `git`。

**(3) gateway 侧的过滤器:只有"垃圾根"黑名单,不是"工作区"白名单。**
`build_tree` 接受三个注入的谓词,server.py 传的是:

`tui_gateway/server.py:11646 @ 863e313`

```python
        preview_limit=preview_limit,
        hydrate=hydrate,
        is_junk_root=_is_repo_junk,
        is_junk_cwd=_is_session_cwd_junk,
        exists=_dir_exists_cached,
```

`_is_repo_junk`(`tui_gateway/server.py:11334`)只挡三样:空、裸 `$HOME`、`$HERMES_HOME` 及其子树;
`_is_session_cwd_junk`(`:11350`)更窄,只挡裸 `$HOME` 与 `$HERMES_HOME` **本身**
(有意的:`HERMES_HOME` 下面用户显式选的子目录可能真是个散文/数据工作区)。
`exists=_dir_exists_cached` 是防"删掉的目录变成幽灵项目",不是边界。
**没有任何"必须位于某个允许的根之下"的检查。**

**(4) 真正能列目录的是本片另一个方法:`complete.path`,它没有包含性检查。**
`complete.path`(`tui_gateway/methods_complete.py:41`)的 `root = _completion_cwd(params)`
本意是"会话工作区",但显式路径分支直接接受绝对路径:

`tui_gateway/methods_complete.py:166 @ 863e313`

```python
        search_dir = (
            search_dir if os.path.isabs(search_dir) else os.path.join(root, search_dir)
        )
        if not os.path.isdir(search_dir):
            return _ok(rid, {"items": []})
```

之后 `rel = os.path.relpath(full, root)`(`:188`)会算出 `../../etc/...` 这种越界相对路径,
**没有任何 `..` / `commonpath` 拦截**:

```verify
cd /home/user/hermes-agent && grep -nE 'commonpath|commonprefix|startswith\(root|relative_to' tui_gateway/methods_complete.py; echo "exit=$?"
```
→ 无输出,`exit=1`(搜索面:`tui_gateway/methods_complete.py` 全文,
四种常见包含性判定写法)。

有意思的是**同一个处理函数的另一个分支是有边界的**:模糊 basename 搜索走
`_list_repo_files(root)`,而那个函数的 docstring 明确写"root 之外的文件被排除,
让选择器保持在从 gateway cwd 可达的范围内"(`tui_gateway/server.py:11932-11943`)。
所以边界意识存在,只是**只装在两个分支中的一个**上 —— 与 §5.4 的 `/moa` 是同一形态。

`config.get {key: "project", cwd: <任意路径>}` 也构成一个更弱的探测面:
`tui_gateway/methods_config.py:186-190` 把 `cwd` 交给 `_completion_cwd`,后者只在
`os.path.isdir(resolved)` 成立时返回该路径、否则回落 `os.getcwd()`
—— 于是响应里的 `cwd` 字段**区分了"这个目录存在"与"不存在"**。

---

## §6 发现清单

### ■1 `pet.generate` / `pet.hatch` 漏掉了 `@_profile_scoped`,在"一后端服务多 profile"下会把宠物装进错误的 profile

12 个 pet 方法带 `@_profile_scoped`,4 个不带,其中两个是**写盘**方法。
装饰器自己的 docstring 就点名了它要解决的场景:

`tui_gateway/server.py:1406 @ 863e313`

```python
def _profile_scoped(handler):
    """Bind ``params['profile']``'s HERMES_HOME around a pet RPC handler.

    Pets are per-profile: ``display.pet.*`` lives in the profile's config.yaml and
    sprites install under its ``pets/`` dir (both resolve via ``get_hermes_home``).
    The desktop sends ``profile`` on pet calls so config + pets dir resolve to the
    focused profile even in app-global remote mode, where one backend serves every
    profile. No-op for the launch profile (own-profile backends already resolve it).
    """
```

对照两个装饰器的实际位置:

`tui_gateway/methods_session.py:1326 @ 863e313`

```python
@method("pet.info")
@_profile_scoped
def _(rid, params: dict) -> dict:
```

`tui_gateway/methods_session.py:1800 @ 863e313`

```python
@method("pet.generate")
def _(rid, params: dict) -> dict:
```

而 `pet.generate` 的落盘目录与 `pet.hatch` 的安装目录都走 `get_hermes_home()`:

`tui_gateway/server.py:8182 @ 863e313`

```python
def _pet_gen_root():
    """Profile-scoped staging dir for in-progress generation drafts."""
    from hermes_constants import get_hermes_home

    root = get_hermes_home() / "cache" / "pet-gen"
    root.mkdir(parents=True, exist_ok=True)
    return root
```

`agent/pet/store.py:56 @ 863e313`

```python
def pets_dir() -> Path:
    """Return the profile-scoped pets directory (created on demand)."""
    path = get_hermes_home() / "pets"
    path.mkdir(parents=True, exist_ok=True)
    return path
```

**后果**:在 app-global remote 模式下,桌面聚焦 profile B、点"生成宠物"→"孵化",
`pet.hatch` 会把新宠物写进**启动 profile A** 的 `pets/`,并按 A 的
`display.pet.scale` 生成预览;随后 profile-scoped 的 `pet.gallery` / `pet.select`
读的是 **B** 的 `pets/`,新宠物**看不见也无法采纳**。
(`pet.generate` 与 `pet.hatch` 之间的草稿交接不受影响 —— 两者都用未加范围的
`_pet_gen_root()`,错得一致。)

`pet.generate.status` 缺装饰器影响较小(只读 provider 配置),
`pet.cancel` 有意留在装饰器外(docstring 说要"不占 worker 池")。

**测试也没兜**:全仓 `tests/` 下搜 `_profile_scoped` / `profile.*pet` / `pet.*profile`
共 17 处命中,**无一条**是钉 pet RPC 的 profile 范围的
(搜索面:`grep -rn "_profile_scoped\|profile.*pet\|pet.*profile" tests/ --include=*.py`)。

### ■2 `_stopped_respawning` 永不复位:崩溃循环触发后,回合隔离在该进程余生里静默失效

```verify
cd /home/user/hermes-agent && grep -rn "_stopped_respawning" --include=*.py .
```

实测 5 处命中:`:166` 构造置 `False`、`:187` 读、`:314` 读、`:511` 置 `True`、`:521` 读。
**没有任何一处把它复位。**(搜索面:全仓所有 `*.py`,含 `tests/`;
未搜 `.ts`/`.md` —— 这是个 Python 进程内状态,跨语言不可能复位它。)

`tui_gateway/host_supervisor.py:313 @ 863e313`

```python
    def _spawn_locked(self, *, reason: str) -> None:
        if self._stopped_respawning:
            raise RuntimeError("compute host respawn disabled after crash loop")
```

严重度受两点缓解:(a) `prompt.submit` 有降级路径(§4 末),服务不中断;
(b) 熄火只发生在 5 分钟内崩 3 次。但**用户端零反馈** ——
`logger.error` 之后,每个后续回合都静默地退回到"GIL 会被饿死"的老架构,
而这正是打开这个开关想避免的。可迁移的教训:
**"降级成功"与"降级已成为常态"是两件事,后者必须可观测。**

### ■3(低)心跳与孤儿看门狗共用一个开关;心跳的进度计数收了却没人读

两个不相关的安全设施挂在同一个 `if` 上:

`tui_gateway/compute_host.py:161 @ 863e313`

```python
        self._heartbeat_secs = (
            float(heartbeat_secs)
            if heartbeat_secs is not None
            else float(os.environ.get("HERMES_COMPUTE_HOST_HEARTBEAT_SECS") or "15")
        )
        if self._heartbeat_secs > 0:
            threading.Thread(target=self._heartbeat_loop, name="compute-host-heartbeat", daemon=True).start()
            threading.Thread(target=self._parent_guard_loop, name="compute-host-ppid-guard", daemon=True).start()
```

把心跳关掉(`heartbeat_secs=0` 或 env 设为 `0`)**同时**关掉"父进程没了就自杀"。
经监工创建时够不到这条路径(`self.heartbeat_secs = max(1, int(heartbeat_secs))`,
`tui_gateway/host_supervisor.py:154`;server 侧配置也有 `min_value=1`),
所以这是**潜在耦合**而非当前可触发的缺陷 —— 直接 `python -m tui_gateway.compute_host`
并设 `HERMES_COMPUTE_HOST_HEARTBEAT_SECS=0` 才会命中。

同一处的第二个问题:心跳里最有用的字段是 `progress_counter`(回合有没有在推进),
监工把它存进 `_last_progress_counter` 后**再没读过**:

```verify
cd /home/user/hermes-agent && grep -rn "_last_progress_counter" --include=*.py .
```
→ 3 处:`:171` 初始化、`:422` 赋值、无读取点。
**因此监工没有"卡死看门狗"**:一个活着但死锁/停摆的子进程永远不会被判死,
只有进程真的退出才会。判死的四条机制(§5.2)全部基于**进程存活**,不基于**进度**。

### ■4(低)`project_tree._is_path_under` 是死代码,而且它正是这个模块唯一的路径包含性判定

见 §5.5(1)。它不是"缺守卫",是"写了守卫、换了实现、忘了删"。
危险在于**下一个读者会以为这个模块做了包含性检查**。

```verify
cd /home/user/hermes-agent && grep -rn "_is_path_under" --include=*.py .
```
→ 只有 `tui_gateway/project_tree.py:131` 这一行定义。
(搜索面:全仓所有 `*.py` 含测试;该名字是私有下划线名,不会被跨语言引用。)

### ▲5 `AGENTS.md` 的"Slash Command Flow" 把 `command.dispatch` 说成 worker 之后的 fallback,代码里它是 worker **之前**的抢先路由

`AGENTS.md:463 @ 863e313` 标题 `### Slash Command Flow` 下的第 2 条:

> 2. Everything else → `slash.exec` (runs in persistent `_SlashWorker` subprocess) → `command.dispatch` fallback

整句判定:"Everything else" 与 "→ command.dispatch fallback" 两处都与代码不符。
`slash.exec` 里有 **12 个命令名**在碰到 worker **之前**就被改派给 `command.dispatch`:

`tui_gateway/methods_tools.py:1099 @ 863e313`

```python
    if _cmd_base in _PENDING_INPUT_COMMANDS:
        # Route directly to command.dispatch instead of returning an error
        # that requires the frontend to retry.  Some TUI clients fail the
        # fallback, leaving the command empty and showing "empty command".
        return _methods["command.dispatch"](
```

另有 9 + 3 个命令名由 `_live_slash_command_output` 在 gateway 进程内直接答掉、
skill bundle 也改派 `command.dispatch`、插件命令在 gateway 进程内直接执行 —— 全部
**不进** worker。代码注释里 `instead of returning an error that requires the frontend
to retry` 正好说明:文档描述的那个"worker 先跑、再 fallback"的旧形态已被有意替换掉。
同一表格里 `AGENTS.md:461` 的 `slash.exec` → `_SlashWorker`, `command.dispatch`
只并列两者、不排序,**字面为真,不计 ▲**。

### ▲6 `SECURITY.md` 把 tui_gateway 描述成 "reached over local IPC",而本片代码显式为跨机客户端设计

`SECURITY.md:192 @ 863e313` 在 "surfaces that cross a trust boundary" 列表下:

> - **The TUI gateway (`tui_gateway/`).** JSON-RPC backend for the
>   Ink terminal UI, reached over local IPC.

同一段的 Uniform rule 1 把 TUI gateway 归入 "editor and local-IPC surfaces",
授权 = 依赖 OS 级访问控制。但本片代码有两处第一方声明与之矛盾:

`tui_gateway/methods_prompt.py:421 @ 863e313`

```python
    """Attach an image to the session from base64 bytes (remote-client path).

    A desktop app or web dashboard running on a DIFFERENT machine than the
    gateway can't hand us a local path — that file only exists on the client's
    disk. So it uploads the raw image bytes (base64) and we write them into the
    gateway's own images dir. The response shape mirrors ``image.attach`` so the
    client treats both identically.
```

`tui_gateway/methods_prompt.py:613 @ 863e313`

```python
    remote-gateway case where the desktop passes a path that only exists on the
    CLIENT's disk: the client uploads ``data_url`` bytes and we materialize the
    file on the gateway.
```

即 `image.attach_bytes` 与 `file.attach` **整个存在理由**就是"客户端在另一台机器上"。
把它描述为 "local IPC" 且"服务于 Ink terminal UI"是两处都偏窄
(它同时是 Electron 桌面 App 与 web 仪表盘的后端,见 `AGENTS.md:494`)。
**限定**:Uniform rule 1 的**政策**部分(不得在没有网络鉴权层的情况下暴露)是否被违反,
取决于 `tui_gateway/ws.py` 与 web_server 的 token 校验 —— 那两个文件不在本片,
我没查,所以本条只判**面的描述**与代码矛盾,不判政策被违反(见 §7)。
这条 ▲ 与 §5.5 的目录枚举面直接相关:在"local IPC"模型下 `complete.path`
列任意目录无所谓,在"另一台机器上的客户端"模型下它就是一个文件系统枚举面。

### ◇7 compute host 发出 14 种帧,监工只处理 11 种;被丢掉的包括子进程唯一的"我要退出了"遗言

见 §3.3(c) 的表。`_handle_host_frame` 的最后一个分支之后**没有 else、没有兜底日志**:

`tui_gateway/host_supervisor.py:443 @ 863e313`

```python
        if ftype == "error" and frame.get("request_id"):
            request_id = str(frame.get("request_id") or "")
            with self._lock:
                q = self._pending_controls.get(request_id)
            if q is not None:
                try:
                    q.put_nowait(frame)
                except queue.Full:
                    pass
```

`turn.started` / `delta` / `session.seeded` 被丢掉无实害(前者信息已在 rpc 事件里,
后两者只在 spike 路径产生)。`orphan` 被丢掉有实害:那是子进程在
`os._exit(0)` **之前**说的唯一一句话,说明它是因为父进程换人而自杀,
而不是崩了。监工那边只会看到 `proc.wait()` 返回、把这次退出记为 `reason="crash"`
并计入 5 分钟重启配额(`tui_gateway/host_supervisor.py:475`)。

### ◇8 `config.set` 没有随 `config.get` 一起搬出来,读写配置分居两个文件

`tui_gateway/methods_config.py:1 @ 863e313`

```python
"""Config / projects / setup JSON-RPC handlers (moved verbatim from server.py).

NOTE: ``config.set`` stays in server.py for now — the in-flight
opt/model-resolution-core PR touches it; move it in a follow-up once merged.
```

这是一条**代码里有、任何文档都没有**的接缝断裂:`config.get` 的 21 个 key
在 `methods_config.py`,与之配对的 `config.set` 在 server.py
(`tui_gateway/server.py:10482` 的 `@method`)。§5.4 的 `/focus` 分支正好跨这条缝调用:
`tui_gateway/methods_tools.py:681` 的 `_res = _methods["config.set"](`。

### ◎9 `AGENTS.md` 说 server.py 是 "the full method/event catalog",这在运行期为真、在阅读期已严重偏窄

`AGENTS.md:445 @ 863e313`:

> Newline-delimited JSON-RPC over stdio. Requests from Ink, events from Python. See `tui_gateway/server.py` for the full method/event catalog.

**字面为真**(所以是 ◎ 不是 ▲):`_methods` 这个注册表确实住在 server.py,
`methods_*` 是把处理函数**装进**它(§5.1),运行期 `server._methods` 就是全表。
但作为"去哪读"的指路,它已经指向了只剩 10/133 = 7.5% 处理函数体的文件。

```verify
cd /home/user/hermes-agent && printf 'server.py=%s methods_*=%s\n' \
  "$(grep -c '^@method(\"' tui_gateway/server.py)" \
  "$(grep -ch '^@method(\"' tui_gateway/methods_*.py | paste -sd+ | bc)"
```
→ `server.py=10 methods_*=123`。

### ◇10 `dashboard.turn_isolation` 默认关闭,整套 compute host 机制在默认安装下是死的

`tui_gateway/server.py:2882 @ 863e313`

```python
_DASHBOARD_TURN_ISOLATION_DEFAULT = False
_DASHBOARD_COMPUTE_HOST_HEARTBEAT_SECS_DEFAULT = 15
_DASHBOARD_COMPUTE_HOST_RESPAWN_MAX_DEFAULT = 3
```

搜索面:全仓 `*.md`,模式 `turn_isolation|compute_host|compute-host` —— **零命中**
(命令见下)。即 1,457 行的宿主监管机制、13 条 mutator 路由表、
以及 `synthetic_turn.py` 整套认证接缝,**在任何面向用户或开发者的 Markdown 文档里
都不存在**;`tui_gateway/synthetic_turn.py:3` 与 `scripts/iso-certify.py:5` 引用的那份 PRD
(`docs/desktop/2026-07-04-dashboard-process-isolation-PRD.md`)**也不在基线里**。

```verify
cd /home/user/hermes-agent && grep -rln "turn_isolation\|compute_host\|compute-host" --include=*.md . ; echo "md-hits-exit=$?"
git -C /home/user/hermes-agent grep -n "dashboard-process-isolation-PRD"
ls -d /home/user/hermes-agent/docs/desktop 2>&1 | tail -1
```
实测:第一条无输出(`md-hits-exit=1`);第二条只有 `scripts/iso-certify.py:5` 与
`tui_gateway/synthetic_turn.py:3` 两处引用;第三条 `No such file or directory`。

---

## §7 未取证与推定(明确列出我没验的东西)

1. **没有真跑起 compute host 做端到端验证。** §4 的 9 跳是**读代码**推出来的调用链,
   逐跳有锚点,但我没有把 `dashboard.turn_isolation` 打开、拉一个真 dashboard 走一遍。
   `tests/tui_gateway/test_compute_host.py` + `test_compute_host_phase1.py` 12 个用例
   实测通过(命令见下),它们覆盖了 spike 帧、`pid-reuse-ignored`、shutdown 排空,
   但**没有**覆盖"崩溃 3 次后永久熄火"这条路径 —— 我搜过
   `respawn|crash loop|_stopped_respawning` 在这两个测试文件里的命中,只有
   `reconcile_startup_orphan` 相关的 2 处。所以 ■2 是**读代码得出的结论**,不是实测。

   ```verify
   cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
     /home/user/hermes-venv/bin/python -m pytest \
     tests/tui_gateway/test_compute_host.py tests/tui_gateway/test_compute_host_phase1.py -q 2>&1 | tail -3
   ```
   → `12 passed`。

2. **`complete.path` 的越界目录枚举没有实跑复现。** §5.5(4) 是代码路径推演
   (`isabs` 直通 + 无 `..` 拦截 + `relpath` 会产出 `../..`)。要实跑得起一个带
   `_sessions` 全局的 gateway 进程,超出 L2 该做的下钻量。**我没有构造过一次真实请求。**

3. **▲6 的政策面没查。** `tui_gateway/ws.py`、`hermes_cli/web_server.py` 的
   token/bind 策略不在本片,所以我只判"面的描述"矛盾,不判"暴露给了未鉴权的网络"。

4. **`methods_session.py` 的 62 个方法我只读了接口面。** 逐个方法的**实现体**里,
   我完整读过的是 `session.create`(14-161)、`session.resume` 的前 120 行、
   4 个 pet 方法、以及 §6-1 涉及的部分。`handoff.*` / `billing.*` / `subscription.*` /
   `spawn_tree.*` / `delegation.*` 共 18 个方法我**只看了方法名与行号**,
   没读实现。按派工书 §4 这是 L2 的正当做法,但要如实说清界线在哪。

5. **`methods_prompt.py` 的 `prompt.submit` 我读全了,`pdf.attach` / `file.attach` /
   `preview.restart` 只读了 docstring 与关键分支。**

6. **compute host 的 `shutdown` 帧路径是否丢数据,我没定论。** `handle_frame` 处理
   `"shutdown"` 时**不调** `flush_all_sessions`(只有 SIGTERM / orphan / stdin-closed 调),
   随后 reader 直接 `os._exit(0)` 绕过 atexit(`tui_gateway/compute_host.py:857-858`)。
   docstring 声明这是 "a clean child-process close"(`:280-282`)。
   到底干净不干净取决于 `server._finalize_session`(`tui_gateway/server.py:655`)做了什么,
   那不在本片,**我没读**。

7. **`git_probe` 依赖的 `bounded_git_probe`(`hermes_cli/_subprocess_compat`)没读。**
   我把它当黑盒:"跑 git、超时可控、失败返回空串"。

8. **没跑 `ui-tui` 的 TypeScript 测试,也没读客户端侧。** 派工书禁止 `npm`/`vitest`。
   §4 的跳 1 和跳 8 的客户端一端我只能写"接到谁",不能验。

9. **`_TUI_HIDDEN` 隐藏的 5 个命令是否仍可执行,没验。** 它只作用于
   `commands.catalog` 的目录输出(`tui_gateway/methods_tools.py:272`:
   `if cmd.name in _TUI_HIDDEN or cmd.gateway_only:`),我**推定**它们仍能通过
   `slash.exec` → worker 执行(worker 里是完整 `HermesCLI`),但没实跑确认。

---

## §8 L2 判据自评

| 判据 | 达成 | 说明 |
|---|---|---|
| **1. 点名到位**(片内每个文件至少一次全路径 + 一句话角色) | ✓ | §2 表格 11 行,11 个全路径逐个列出并各给角色;正文里每个文件都被再次全路径引用过 |
| **2. 接缝穷举**(逐项列全 + 机械枚举命令 + 条数) | ✓(有一处如实打折) | 穷举了 8 张接缝:123 个 JSON-RPC 方法(逐个列名,5 条枚举命令)、12 个 `@_profile_scoped`、13 条 `MUTATOR_ROUTE_TABLE`、6 种父→子帧、14 种子→父帧(含监工处理/丢弃标注)、`project_tree` 8 个模块层公开名(其中 6 个真被外部用)+ 6 种 id 形状、`git_probe` 7 个 `def`、`slash_worker` 协议 4 面、`synthetic_turn` 3 导出 + 5 env、7 张斜杠路由集合。**打折处**:`config.get` 的 21 个 key 我用一条 `grep -oE` 枚举并给了名字,但没逐个说明每个 key 的返回体形状 |
| **3. 一条端到端链走通** | ✓ | §4 共 9 跳 + 1 条降级路径,每跳带锚点;两端写清了接到谁(跳 1 接 `requestGateway`/`handle_request`,跳 8 接 `write_json` → 客户端 transport)。跨出本片的部分(server.py / cli.py)也逐一给了锚点 |
| **4. 两处以上逐字取证** | ✓ | 逐字源码围栏块共 **61** 个(全部 ```` ```python ````,逐行受 BLOCK-DRIFT 校验):`tui_gateway/host_supervisor.py` 12、`tui_gateway/server.py` 11、`tui_gateway/compute_host.py` 7、`tui_gateway/methods_prompt.py` 7、`tui_gateway/methods_tools.py` 5、`tui_gateway/slash_worker.py` 4、`tui_gateway/synthetic_turn.py` 3、`tui_gateway/project_tree.py` 2、`tui_gateway/methods_session.py` 2、其余 9 个文件各 1(`method_ctx.py` / `git_probe.py` / `methods_complete.py` / `methods_config.py` / `agent/pet/store.py` / `scripts/iso-certify.py` / 两个测试文件)。另有 3 个 `>` 文档引用块(`AGENTS.md` × 2、`SECURITY.md` × 1)、23 个 ```` ```verify ````、3 个 ```` ```text ````。全部源码块用 `sed -n 'A,Bp'` 取出后粘贴,未手抄 |
| **5. 至少一条记号** | ✓ | 10 条:■4(1 中高 + 3 低)、▲2、◇3(编号 7/8/10)、◎1,逐条带锚点与代码块 |

**我没做到的**:见 §7,尤其是 (1) ■2 未实测、(2) `complete.path` 越界未实跑复现、
(4) `methods_session.py` 18 个方法只到方法名。

---

## §9 移交

| 编号 | 锚点 + 摘录 | 一句话现象 | 建议下一轮 |
|---|---|---|---|
| H-R10B-a | `tui_gateway/methods_session.py:1800`:`@method("pet.generate")` | 该行下一行直接是 `def _(rid, params: dict) -> dict:`,**没有** `@_profile_scoped`;而 `pet.info`(`:1326`)、`pet.gallery`(`:1480`)等 12 个方法都有 —— 于是 `pet.hatch` 把宠物装进启动 profile,`pet.gallery` 从聚焦 profile 读,新宠物看不见 | 读 `agent/pet/generate/__init__.py` 的 `hatch_pet` 确认落盘点;若确认,这是一条可直接提 issue 的缺陷 |
| H-R10B-b | `tui_gateway/host_supervisor.py:511`:`self._stopped_respawning = True` | 全仓仅此一处置 `True`,无任何复位点;触发后 `is_running()` 恒 False,回合隔离在该进程余生静默失效,只留一条 `logger.error` | 查 dashboard 侧有没有把这个状态暴露到 `/api/health` 之类的面;没有就是"降级不可观测" |
| H-R10B-c | `tui_gateway/host_supervisor.py:422`:`self._last_progress_counter = int(frame.get("progress_counter") or self._last_progress_counter)` | 心跳里的进度计数只写不读(全仓 3 处命中,无读取点),所以监工**没有卡死看门狗** —— 判死四机制全基于进程存活,不基于进度 | 与 gateway 其它看门狗(`slash_worker` 的 `_start_parent_death_watchdog`、`tools/mcp_tool` 的孤儿清扫)对照,看这是不是全项目一致的取舍 |
| H-R10B-d | `tui_gateway/methods_tools.py:623`:`_apply_model_switch(` | 这条调用在 `command.dispatch` 的 `/moa` 分支里,**上游没有任何** `session.get("running")` 检查;而同一操作的另外两个入口(`config.set model`、`_mirror_slash_side_effects`)都有守卫,项目自己的测试注释把该不变式写成 `tests/test_tui_gateway_server.py:10160`:`# /model switch and other agent-mutating commands must reject while the` | 顺着 `session["moa_one_shot_restore"]` 查回合结束后的还原路径,确认中途换模型会留下什么残留状态 |
| H-R10B-e | `tui_gateway/project_tree.py:131`:`def _is_path_under(folder: str, target: str) -> bool:` | 该模块唯一的路径包含性判定,全仓零调用(`grep -rn "_is_path_under" --include=*.py .` 只命中定义行);真正做归属的是 `_FolderIndex.match`(`:471`) | 顺手确认桌面 TS 侧(`apps/desktop/src/lib/`)有没有自己那份 `isPathUnder` —— 若有,这是"同一判定两处实现"的又一例 |
| H-R10B-f | `tui_gateway/methods_complete.py:167`:`search_dir if os.path.isabs(search_dir) else os.path.join(root, search_dir)` | 显式路径分支直通绝对路径、无 `..`/`commonpath` 拦截,而同一处理函数的模糊搜索分支走 `_list_repo_files(root)` 且其 docstring 明确"root 之外的文件被排除" —— 边界只装在两个分支中的一个 | 结合 `tui_gateway/ws.py` 的 bind/token 策略判定这是"本地便利"还是"远程枚举面";这是 ▲6 落地与否的关键 |
| H-R10B-g | `tui_gateway/methods_config.py:3`:`NOTE: ``config.set`` stays in server.py for now — the in-flight` | 读配置(`config.get`,21 key)已搬进 `methods_config.py`,写配置(`config.set`)仍在 `tui_gateway/server.py` 第 10482 行;`/focus` 分支跨这条缝调用 —— `tui_gateway/methods_tools.py:681`:`_res = _methods["config.set"](` | 若后续轮次要讲"大文件拆分怎么收尾",这是现成的"拆了一半"标本 |
| H-R10B-h | `tui_gateway/synthetic_turn.py:3`:`Mechanism B (the class ``docs/desktop/2026-07-04-dashboard-process-isolation-PRD.md``` | 这份 PRD 被 2 个文件引用(另一处 `scripts/iso-certify.py:5`),但 `docs/desktop/` 目录在基线里**不存在** | 整套回合隔离机制(1,457 行)在全仓 `*.md` 里零提及,是"◇ 代码有、文档无"的最大一块;R12 蓝图里值得单开一节 |

---

## 附:交付前自检

引用校验读数(交付时):`citations=87  OK=64  UNCHECKED=23`,
`可校验比例 OK/87 = 73.6%`(≥ 70% 下限),`table_anchors=33  OK=33`,
`MISMATCH=0  BLOCK-DRIFT=0  TABLE-DRIFT=0`,退出码 0,输出
`OK: every code-block-backed citation matches the baseline`。

```verify
cd /home/user/hermes-agent && git status --porcelain; echo "porcelain-exit=$?"
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent \
  notes/r10-raw-tui-gateway-methods.md
```

基线只读约束:本片全程只 `sed`/`grep`/`git status`/`pytest`(读),
未在基线里写入任何文件、未跑 `npm`/`pip`,未安装任何 Python 包。
