# r8b-01 · 范围、主干入口链(主线精读)

> 溯源约定:`路径:行号 @ 863e313` + 代码原文块。
> 本篇是**主线亲读**的部分:入口链(`hermes_bootstrap.py` → `hermes_cli/main.py` →
> `_parser.py` → `cli.py`)与 profile 前置解析。`cli.py` 类体内部由 6 段子代理底稿覆盖
> (`notes/r8b-raw-*`)。

## 1. 范围调整(相对台账 `round=R8B`)

开轮台账 `round=R8B` 为 **48 文件 / 40,804 行**。本轮**增补 2 个文件、未删任何文件**,
调整后 **50 文件 / 43,539 行**。两条增补都以规则形式写进 `scripts/assign_layers.py`
(非手改台账),重生成后 `path/kind/lines/status` 四列与切前**逐字节相同**,
仅 `layer`/`round` 两列变化。

| 增补 | 行数 | 理由 |
|---|---|---|
| `hermes_cli/_parser.py` | 473 | R8B 的范围描述原文就是"进程入口、**argparse 子命令树**、命令分发 mixin",而顶层 parser 与 `chat` 子 parser 的本体全在这个文件里。它当初落进 R8D 只是因为规则表没点名它、被 `hermes_cli/**` 兜底规则吃掉——**是规则表的漏,不是判断的改** |
| `hermes_cli/profiles.py` | 2,262 | R8A 报告 §1 明确写了"没纳入 `profiles.py`……**留 R8B**"。规则表同样漏了点名。且 `--profile/-p` 在 argparse **之前**就被消费(见 §4),与主干耦合到无法分开读 |

`_parser.py` 的自我定位原文:

`hermes_cli/_parser.py:1 @ 863e313`

```python
"""
Top-level argparse construction for the hermes CLI.

Lives in its own module so other modules (e.g. ``relaunch.py``) can
introspect the parser to discover which flags exist without running the
``main`` fn.

Only the top-level parser and the ``chat`` subparser live here. Every other
subparser (model, gateway, sessions, …) is built inline in ``main.py``
because its dispatch is tightly coupled to module-level ``cmd_*`` functions.
"""
```

**最后一句是本轮理解 CLI 主干的关键**:子命令树**不在一个地方**——
顶层与 `chat` 在 `_parser.py`,其余 30 多个子命令**在 `main()` 函数体里内联构建**,
理由是"dispatch 与模块级 `cmd_*` 函数耦合太紧"。这是一个明确写下来的取舍,
后果见 §5。

**没有增补的相邻文件**(读到但不认领,沿用 R8A "只读那几处、不认领该文件"的先例):
`hermes_cli/config.py` / `config_defaults.py` / `status.py` / `commands.py`(均 R8A 已精读)、
`tui_gateway/server.py`(R9/R10)、`gateway/display_config.py`(R7C 面)。

---

## 2. 入口链全貌

打包入口只有三个:

`pyproject.toml:358 @ 863e313`

```toml
[project.scripts]
hermes = "hermes_cli.main:main"
hermes-agent = "run_agent:main"
hermes-acp = "acp_adapter.entry:main"
```

**`hermes` 走的是 `hermes_cli/main.py` 的 `main()`,不是 `cli.py` 的 `main()`。**
这一点必须先说清楚,否则读 `cli.py:18026` 的 `main()` 会以为它是进程入口——
它其实是 `cmd_chat` 调下来的**交互式 REPL 的入口**,是第二层。

链条:

```
hermes(console script)
  └─ hermes_cli/main.py : main()            ← 进程入口
       ├─ 模块导入期:bootstrap / 早期 TUI 判定 / 配置桥 / 日志
       ├─ _apply_profile_override()          ← argparse 之前(§4)
       ├─ _try_termux_fast_tui_launch() / _try_termux_fast_cli_launch()
       ├─ build_top_level_parser()           ← _parser.py
       ├─ 30+ subparsers 内联注册
       ├─ parse_args(两次尝试,§5)
       └─ args.func(args)  →  cmd_chat(args)
            └─ cli.py : main()               ← 交互式 REPL 入口
                 └─ HermesCLI(...).run()
```

---

## 3. 模块导入期就干活:三件必须在 import 阶段完成的事

`hermes_cli/main.py` 有大量**模块级**语句(不在任何函数里),因为它们必须早于某些 import。

### 3.1 `hermes_bootstrap` 必须是第一个 import,而且必须能失败

`hermes_cli/main.py:46 @ 863e313`

```python
# IMPORTANT: hermes_bootstrap must be the very first import — it sets up
# UTF-8 stdio on Windows so print()/subprocess children don't hit
# UnicodeEncodeError with non-ASCII characters.  No-op on POSIX.
```

真正值得学的是**为什么它被 try 包起来**:

`hermes_cli/main.py:50 @ 863e313`

```python
# Guarded against ModuleNotFoundError because ``hermes_bootstrap`` is a
# top-level module registered via pyproject.toml's ``py-modules`` list.
# When the user upgrades code via ``git pull`` (or ``hermes update``
# crashes between ``git reset --hard`` and ``uv pip install -e .``), the
# new code references ``hermes_bootstrap`` but the editable install's
# ``.pth`` file still points at the old set of top-level modules.  Without
# this guard, hermes crashes on import and the user can't run
# ``hermes update`` to recover.  Missing the bootstrap means UTF-8 stdio
# setup is skipped on Windows — degraded, not broken.  POSIX is unaffected.
```

**这是一条一般性设计原则,值得单独记**:
**升级命令自身必须在"升级失败后的半坏状态"下仍可运行。**
`hermes update` 在 `git reset --hard` 与 `pip install -e .` 之间崩溃,会留下
"新源码 + 旧 `.pth`"的组合;若入口 import 硬失败,用户**连修复命令都敲不进去**,
只能手工重装。这个 try 的全部价值就是把"砖化"降级成"少一个 Windows 优化"。

同样的思路在 `main()` 里还有两处兜底:清理上次 update 留下的隔离文件、
以及自愈被打断的 venv 安装。后者的判据写得很坦白:

`hermes_cli/main.py:11215 @ 863e313`

```python
    # The substring match is deliberately loose: argv isn't parsed yet at this
    # point, and the failure modes are asymmetric. Over-matching (e.g.
    # ``hermes skills install update``) merely defers recovery one launch;
    # under-matching (missing ``hermes -p work update``) would race a recovery
    # install against the real one. Loose wins.
```

**"两种误判的代价不对称,所以选择往代价小的一侧犯错"**——
这条比"写个精确的 argv 解析"更适合放在这个位置,因为此处**根本还没解析 argv**。

### 3.2 第六个 config.yaml 读取函数(补 R8A 的账)

R8A 数出 `config.yaml` 有**五个读取函数**。**CLI 主干带来第六个**:

`hermes_cli/main.py:280 @ 863e313`

```python
def _config_default_interface_early() -> str:
    """Return the configured default interface ("cli"/"tui") via a minimal
    YAML read. Best-effort: any error falls back to "cli" (legacy behavior)."""
```

它**自己开文件、自己 `yaml.load`、自己缓存**(`_EARLY_INTERFACE_CACHE`),
不走 `read_raw_config()`:

`hermes_cli/main.py:294 @ 863e313`

```python
            import yaml as _yaml_iface

            with open(cfg_path, encoding="utf-8") as _f:
                raw = _yaml_iface.load(
                    _f, Loader=getattr(_yaml_iface, "CSafeLoader", None) or _yaml_iface.SafeLoader
                ) or {}
```

**这一次的重复是有正当理由的,而且理由可验证**:它的调用点是**模块级**语句,
位置在文件第 371 行:

`hermes_cli/main.py:371 @ 863e313`

```python
_suppress_mouse_residue_early()
```

而复用共享缓存的那个桥在**第 709 行之后**才 import `hermes_cli.config`:

`hermes_cli/main.py:710 @ 863e313`

```python
    # Reuse read_raw_config()'s (mtime, size)-keyed cache instead of a bespoke
    # yaml.load — the SAME parse then serves hermes_logging's
    # _read_logging_config and any later raw reads in this process, collapsing
    # 3-4 config.yaml parses per invocation into one.
```

**371 < 709**,所以第 371 行那次读**真的没有共享缓存可用**——
此时若 import `hermes_cli.config`,就等于把它想避开的重量级 import 提前到最热的启动路径上。

**定案 ◇-R8B-b(信息类,不记缺陷)**:`config.yaml` 的读取函数应从 R8A 的**五个**更正为**六个**,
第六个是 `_config_default_interface_early`。它是**唯一一个有明确正当理由的重复**
——前五个是历史分叉,这一个是**为了不在启动最早期拉起配置子系统而付的已知代价**,
并且同文件第 709 行的注释显示作者对"这个文件解析了几次"是有意识、并主动收敛过的
(把 3-4 次并成 1 次)。

### 3.3 启动期的"最早决策"与它的代价

`_suppress_mouse_residue_early` 要在**任何其它 import 之前**关掉终端的鼠标上报:

`hermes_cli/main.py:341 @ 863e313`

```python
# Mouse-tracking residue suppression — runs BEFORE every other import on the
# TUI hot path so the terminal stops emitting SGR/X10 mouse reports while the
# Python launcher is still doing imports (≈100–300ms in cooked + echo mode,
# before the Node TUI takes stdin into raw mode). During that window any
# incoming bytes are echoed straight back to the user's shell scrollback as
# ``^[[<…M`` text. The TUI itself runs `resetTerminalModes()` again in
# `entry.tsx`; this is just the earlier cousin. ``HERMES_TUI_NO_EARLY_DISABLE``
# escapes the behaviour for diagnostics.
```

**这是一个很典型的"启动延迟本身就是 bug 来源"的例子**:
Python 启动器要 100-300ms 才把 stdin 切进 raw 模式,这段窗口里用户动一下鼠标,
终端就把 `^[[<…M` 回显进 scrollback。修法不是"启动更快",而是**在窗口开始处先关掉源头**。

---

## 4. `--profile` 在 argparse 之前被手工扫描

`--profile/-p` 决定 `HERMES_HOME`,而 `HERMES_HOME` 决定**读哪一份配置**,
所以它必须在任何配置读取之前生效——**也就必须在 argparse 之前**:

`hermes_cli/main.py:517 @ 863e313`

```python
def _apply_profile_override() -> None:
    """Pre-parse --profile/-p and set HERMES_HOME before imports."""
```

代价是要**手工重写一小段 argparse**,而这段手工扫描必须知道所有"带值的 flag",
否则会把 flag 的值误当成 profile 名:

`hermes_cli/main.py:572 @ 863e313`

```python
    value_flags = {
        "-z", "--oneshot",
        "-m", "--model",
        "--provider",
        "-t", "--toolsets",
        "-r", "--resume",
        "-s", "--skills",
        "--usage-file",
    }
```

**这是一份必须与真 parser 保持同步的手抄名单**——`_parser.py` 里新增一个带值的短 flag 而
忘了同步这里,`hermes -X foo -p work` 就会解析错。本轮**未发现现存不同步**,
但这是一个结构性的同步点,记为观察项。

三处防御做得很细,值得记:

**(a) 命令 argv 透传区不扫描**:

`hermes_cli/main.py:525 @ 863e313`

```python
        """True once argv reaches `hermes mcp add ... --args <command argv>`.

        ``mcp add --args`` is command-argv passthrough. Flags after that point
        belong to the child MCP command (for example Docker MCP Toolkit's
        ``--profile``), not to Hermes' own profile selector.
        """
```

**(b) 非法 profile 名直接放弃**,理由举了一个真实场景(pytest 的 `-p no:xdist`):

`hermes_cli/main.py:611 @ 863e313`

```python
    # 1b. Reject values that can't be valid profile names (e.g. pytest's
    # "-p no:xdist" would be misread as profile "no:xdist" otherwise).
    # Mirrors hermes_cli.profiles._PROFILE_ID_RE so we never call
    # resolve_profile_env() with a value it must reject + sys.exit on.
```

注释自己说了这是 **mirror**(手抄)。全仓这条 profile 名正则共 **6 份**:

```
./hermes_cli/profiles.py:37       _PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
./hermes_cli/main.py:618          re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", profile_name)
./hermes_cli/gateway.py:1774      re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", parts[0])
./hermes_cli/gateway.py:1808      re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", parts[0])
./gateway/platforms/base.py:1274  re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", path.name)
./optional-skills/creative/kanban-video-orchestrator/scripts/bootstrap_pipeline.py:74
```

**本轮实测六份当前完全一致**(`base.py` 用 `fullmatch` 无锚点,与其余的 `^...$` 等价),
**不记缺陷**,但登记进 R8A §3.6 那张"同一语义几份实现"的表:**profile 名校验 = 6 份**。

**(c) `sudo` 下按 `SUDO_USER` 找 profile 库**,理由写得很清楚——
`--run-as-user` 是 argparse 的参数,此时还不存在:

`hermes_cli/main.py:539 @ 863e313`

```python
        """Resolve `sudo hermes -p <name>` against the invoking user's home.

        `_apply_profile_override()` runs before argparse, so `--run-as-user`
        is not available yet. For sudo invocations, the best available signal
        is SUDO_USER: root is only doing the privileged install/start action,
        while the profile store normally belongs to the user who invoked sudo.
        """
```

---

## 5. argparse 的两次解析:一个为老 Python 打的补丁

`main()` 的解析不是一次 `parse_args`,而是**条件性地解析两次**:

`hermes_cli/main.py:12480 @ 863e313`

```python
    # On some Python versions (notably <3.11), argparse fails to route
    # subcommand tokens when the parent parser has nargs='?' optional
    # arguments (--continue).  The symptom: "unrecognized arguments: model"
    # even though 'model' is a registered subcommand.
```

做法是:argv 里出现任何已注册子命令名 ⇒ 先把 `subparsers.required = True` 强制路由,
**并把 stderr 换成一个 StringIO 吞掉**,失败再退回默认行为:

`hermes_cli/main.py:12498 @ 863e313`

```python
    if _has_cmd_token:
        subparsers.required = True
        _saved_stderr = sys.stderr
        try:
            sys.stderr = _io.StringIO()
            args = parser.parse_args(_processed_argv)
            sys.stderr = _saved_stderr
        except SystemExit as exc:
            sys.stderr = _saved_stderr
```

**里面有一处补丁的补丁,溯源到具体 issue**:

`hermes_cli/main.py:12507 @ 863e313`

```python
            # Help/version flags (exit code 0) already printed output —
            # re-raise immediately to avoid a second parse_args printing
            # the same help text again (#10230).
            if exc.code == 0:
                raise
```

**故事**:第一版补丁吞掉 stderr 重试,于是 `hermes model --help` 变成
**帮助文本打两遍**——第一次解析已经把帮助打到了真 stdout,异常被当成"路由失败"又解析一次。
修法是按**退出码**区分"这是用户要的输出"(0)与"这是路由失败"(非 0)。
**教训:把"打印了东西然后退出"和"解析失败然后退出"都表示成 `SystemExit` 时,
退出码是唯一能把二者分开的信息。**

### 5.1 退出码沿着 handler 往上传

`hermes_cli/main.py:12590 @ 863e313`

```python
    if hasattr(args, "func"):
        rc = args.func(args)
        if isinstance(rc, int) and rc != 0:
            sys.exit(rc)
```

注释点名了动机:`hermes egress start` 在配置不对时要**真的退出非零**,
否则脚本判不出失败。**返回 `None` 一律当成功**——这是一条对 30 多个 `cmd_*` 都生效的约定,
而它没有任何强制手段(没有类型标注、没有测试守卫),属"靠约定维持"的一类。

---

## 6. TUI 判定有两份实现,且优先级不同(核完:当前无后果)

`_wants_tui_early`(:311)与 `_resolve_use_tui`(:2485)都在回答同一个问题
"这次要不要开 TUI",相距 2,100 行。**两者对 `HERMES_TUI=1` 的分类相反。**

`hermes_cli/main.py:314 @ 863e313`

```python
    Precedence: explicit ``--cli`` wins (forces classic REPL), then
    explicit ``--tui``/``HERMES_TUI=1``, then a real-TTY gate (a
```

代码里环境变量确实**排在 TTY 闸门之前**:

`hermes_cli/main.py:329 @ 863e313`

```python
    if "--cli" in argv:
        return False
    if os.environ.get("HERMES_TUI") == "1" or "--tui" in argv:
        return True
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
```

而 `_resolve_use_tui` 把同一个环境变量归为 **ambient(环境残留)**,排在 TTY 闸门**之后**:

`hermes_cli/main.py:2499 @ 863e313`

```python
    The TTY gate (3) is load-bearing: ambient TUI preferences (env var or
    config default) must never hijack a NON-interactive invocation. Kanban
    workers, cron jobs, and pipelines run ``hermes … chat -q`` with stdout
    on a pipe; booting the Ink TUI there hits its no-TTY bail-out, which
    prints a resume hint and exits 0 — a kanban worker then dies with
    "exited cleanly without calling kanban_complete — protocol violation"
    on every attempt (found dogfooding the desktop kanban board). A user
    who *explicitly* passes ``--tui`` still gets the informative bail-out.
```

**同一个环境变量,一个函数叫它 explicit、另一个叫它 ambient**,
而那段 docstring 描述的正是一次真实事故。

**但本轮把三个消费点逐个核完,结论是当前无后果**:

| 消费点 | 锚点 | 为什么安全 |
|---|---|---|
| 鼠标残留抑制 | `hermes_cli/main.py:352` | 自带独立 TTY 判断 `if not os.isatty(1): return`(`hermes_cli/main.py:357`),非 TTY 直接不写 |
| Termux 快速 CLI 路径 | `hermes_cli/main.py:10886` | 返回 True 只是**放弃快速路径**、回落完整分发,分发里再判 |
| Termux 快速 TUI 路径 | `hermes_cli/main.py:10958` | 紧接着在 `hermes_cli/main.py:10977` 用 `_resolve_use_tui(args)` **重判一次**,不通过就返回 |

且两条 Termux 路径都被 `_is_termux_startup_environment()` 门控,非 Termux 根本进不去。

**定案 ▲-R8B-01(文档/语义冲突,不记 ■;中置信)**:两份 TUI 判定对
`HERMES_TUI=1` 的语义分类相反,**当前被三个消费点各自的独立防护完全补偿**。
**记录它的理由不是它现在会出事,而是它现在不出事的原因是"三处各自又防了一次",
而不是"优先级本身正确"**——任何一处防护被当成冗余删掉,那段 docstring 里
描述过的 kanban 事故就会以 `HERMES_TUI=1` 的形态回来。

> **可迁移的一条**:同一个决策有两份实现时,**让它们不一致的成本由谁承担**很关键。
> 这里是"每个消费点自己再判一次"承担的——这叫纵深防御,有效但昂贵,
> 而且它把"两份实现不一致"这件事**藏了起来**(因为没有症状)。

---

## 7. 本篇移交

- `_apply_profile_override` 的 `value_flags` 手抄名单(§4)与真 parser 的同步,
  **本轮未发现不同步**,但无任何自动守卫。记为观察项,不记缺陷。
- `cmd_*` 返回码约定(§5.1)无强制手段,同上。

---

## 8. `cli.py` 1-4204(模块层)—— 主线补位

**说明**:本段原派给子代理(`notes/r8b-raw-cli-module.md`),该段**未在本轮收尾前落盘**
(见 `reports/round-8b-*.md` §8)。为不留黑洞,主线在此补上结构级说明与两个关键机制的精读。
其中最重的一块 `load_cli_config`(409-901)已由 `notes/r8b-02` 全文覆盖,不重复。

### 8.1 段内地图

| 行段 | 内容 |
|---|---|
| 1-95 | 模块 docstring、import、`_hermes_home` 解析 |
| 96-408 | **惰性导入垫片**(`CanonicalUsage`/`estimate_usage_cost`/… 形如 `def X(*args, **kwargs)`)+ 文本处理(reasoning 标签剥离、markdown 表格重排) |
| **409-901** | **`load_cli_config`** —— 第二份配置装载器(**已由 `notes/r8b-02` 覆盖**) |
| 901-1005 | 更多惰性垫片(`AIAgent` / 工具集查询 / 清理回调注册) |
| 1005-1410 | **退出路径**:延迟启动、退出看门狗、`_run_cleanup`、会话终结通知、终端输入模式还原 |
| 1410-2120 | **git worktree 生命周期**:仓库根解析、基点解析、建/清/剪枝、合并缓存、锁活性判定 |
| 2118-2520 | 状态库与检查点的自动维护、陈旧 worktree 与孤儿分支清理 |
| 2521-3070 | ANSI / 皮肤 / 终端背景色探测(OSC11)、`_SkinAwareAnsi` |
| 3027-3250 | **输出历史重放**(`_record_output_history` / `_replay_output_history`)与 `_cprint` |
| 3259-3500 | 附件路径解析、文件拖放识别、图片角标渲染、剪贴板图片 |
| 3486-3840 | **prompt_toolkit 补丁群**:bracketed paste 超时、Ctrl-Enter 换行、CPR 告警抑制、终端响应泄漏清洗 |
| 3874-4204 | `ChatConsole`、紧凑横幅、斜杠命令识别、技能命令/bundle 缓存、`save_config_value` |

### 8.2 退出看门狗:为什么"清理"需要一个兜底的自杀定时器

`cli.py:1064 @ 863e313`

```python
def _arm_exit_watchdog(timeout_s: float | None = None) -> None:
    """Guarantee the process actually exits once shutdown has begun.

    Two hang classes have kept "dead" CLI processes alive for minutes:

      1. A cleanup step wedged on network I/O (memory provider
         ``on_session_end``, MCP teardown, remote terminal cleanup).
      2. Interpreter teardown blocked joining non-daemon threads —
         stdlib ``ThreadPoolExecutor`` workers are joined unconditionally
         by ``concurrent.futures``' atexit hook even after
         ``shutdown(wait=False)``, so one tool thread wedged on a socket
         held the process open forever (#27563 class).
```

**第 2 类值得单独记,因为它是 Python 标准库的一个反直觉行为**:
`concurrent.futures` 注册了 atexit 钩子**无条件 join 工作线程**,
所以即使调用方 `shutdown(wait=False)`,只要有一个工作线程卡在 socket 上,
**解释器退出就会被无限期挡住**。
兜底手段是**守护线程定时器 + `os._exit(0)`**,理由写在同一段注释里:
守护线程能穿过 `Py_FinalizeEx` 的线程 join 阶段继续跑,所以主线程卡死时它仍会触发。

> **可迁移的一条**:凡"清理里会做网络 I/O"的程序,都需要一个**不依赖被清理对象**的退出兜底。
> 判据是:**兜底路径本身不能用到任何可能挂住的东西**——
> 这里用的是守护线程 + `os._exit`,两者都不参与正常的关停协议。

### 8.3 worktree:把"隔离"做成可回收的,而不是可创建的

`cli.py:1608 @ 863e313`

```python
def _setup_worktree(repo_root: str = None, sync_base: bool = True) -> Optional[Dict[str, str]]:
    """Create an isolated git worktree for this CLI session.

    Returns a dict with worktree metadata on success, None on failure.
    The dict contains: path, branch, repo_root.

    When *sync_base* is True (default), the worktree branches from the
    freshly-fetched remote tip rather than the (possibly stale) local ``HEAD``
    — see ``_resolve_worktree_base``. Set ``worktree_sync: false`` in config to
    branch from local ``HEAD`` (the pre-#10760-followup behavior).
    """
```

真正的设计重量不在创建,而在**回收的判据**:段内为此写了一整组辅助函数
——`_worktree_has_unpushed_commits`(:1791)、`_worktree_is_dirty`(:1822)、
`_worktree_commits_all_merged_upstream`(:1900)、`_worktree_lock_is_live`(:1993),
外加一份**合并判定缓存**(`_load_worktree_merge_cache` :1854 / `_save_worktree_merge_cache` :1872)。

> **可迁移的一条**:**自动创建的隔离环境,难点从来不是创建,是"什么时候可以安全删掉"。**
> 这里的判据是三个独立否决项(有未推送提交 / 工作区脏 / 锁还活着)任一成立就不删,
> 且把最贵的那项(是否已全部并入上游)**缓存起来**——
> 因为它要跑 git 命令,而清理路径会对每个陈旧 worktree 都问一遍。

### 8.4 ■-R8B-09 · 无 remote 的仓库里,`hermes -w` 清理会强删分支(数据丢失,高置信)

**补记说明**:本条线索来自 `notes/r8b-raw-cli-module.md` 的正文尾部
——该段子代理**被截断在写 §3 可疑缺陷清单之前**,正文里留下一句
"在无 remote 的情况下,这两句合起来就是 §3-1 的数据丢失",而 §3-1 从未写出来。
**主线据此线索独立回源查证,结论:成立。**

**判定"有没有未推送提交"的函数,在没有 remote 时返回"没有"**:

`cli.py:1791 @ 863e313`

```python
def _worktree_has_unpushed_commits(worktree_path: str, timeout: int = 10) -> bool:
    """Return whether a worktree has commits not reachable from any remote branch.

    ``git log HEAD --not --remotes`` compares against remote-tracking refs under
    ``refs/remotes/*``. If a repo has no remote-tracking refs yet, there is no
    usable remote baseline to compare against, so treat it as having no
    "unpushed" commits.
    """
```

实现里对应的那一句:

`cli.py:1808 @ 863e313`

```python
        if not remote_refs.stdout.strip():
            return False
```

**清理路径把这个 `False` 当成"提交都安全,可以删"**:

`cli.py:2077 @ 863e313`

```python
    has_unpushed = _worktree_has_unpushed_commits(wt_path, timeout=10)

    if has_unpushed:
        print(f"\n\033[33m⚠ Worktree has unpushed commits, keeping: {wt_path}\033[0m")
        print(f"  To clean up manually: git worktree remove --force {wt_path}")
        _active_worktree = None
        return
```

走不到这条"保留并警告"的分支,就一路走到**强制删分支**:

`cli.py:2107 @ 863e313`

```python
        subprocess.run(
            ["git", "branch", "-D", branch],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, cwd=repo_root,
        )
```

**因果链**:仓库没有 remote(纯本地仓库——个人项目、实验仓、`git init` 之后还没加 remote 的仓库,
都是极常见的形态)→ `_worktree_has_unpushed_commits` 返回 `False`
→ 清理认为"内容都在 remote 上" → `git branch -D`(**`-D` 是强制删,不是 `-d` 的"只删已合入的"**)
→ **这次会话在 worktree 分支上的全部提交被丢弃**,界面上不提示、不确认、不保留。

**为什么这条特别值得记:它是整个函数里唯一一处 fail-open。**
同一个函数的**每一条错误路径都返回 `True`**(即"当作有未推送提交、别删"):

- `for-each-ref` 返回非零 → `return True`(`cli.py:1805`)
- `git log` 返回非零 → `return True`(`cli.py:1816`)
- 任何异常 → `return True`(`cli.py:1818`)

**作者的意图明显是 fail-safe:拿不准就别删。** 唯独"没有 remote"这一种情况被当成了
**确定性的"安全"**,而不是"拿不准"。**它不是疏忽某个错误分支,而是把一个
"无法判断"的状态错误地归类成了"已判断为安全"。**

> **可迁移的判据**:凡"删除前的安全检查",都要把**判据不适用**与**判据通过**严格分开。
> 这里的判据是"与 remote 比对",而没有 remote 时**判据根本不适用**——
> 不适用必须归到"不安全"一侧。
> 一个好用的自检问法:**把这个检查函数的返回值改名为
> `is_safe_to_destroy()`,再读一遍每个 `return` —— 哪些是真的"我验证过安全",
> 哪些其实是"我没法验证"?** 后者返回 `True` 就是数据丢失的种子。

**已实跑复现(主线,端到端,用的是生产函数本体)。** 构造真实 git 仓库 + worktree,
在 worktree 里做 2 个提交,然后:

```
_worktree_has_unpushed_commits(worktree) = False
  ^ False 意味着清理路径认定「提交都已推送,可以强删」
=== 执行清理路径的两条命令(与 cli.py:2098/2107 相同)===
Deleted branch hermes-sess (was b2c833d).
=== 事后 ===
IMPORTANT.txt 还在吗: NO — 内容已消失
分支还在吗: NO — 分支已删
提交还可达吗(reflog 之外): 0
```

判据本身的实测(在 worktree 内):

```
for-each-ref refs/remotes -> rc=0 (输出为空即命中 return False)
git log HEAD --not --remotes 提交数: 3
```

**函数报「没有未推送的提交」,而 `git log` 同时数出 3 个。**

**触发面比"纯本地仓库"更宽(此条由子代理 `notes/r8b-raw-cli-module.md` §3-1 指出,主线采纳)**:
判据看的是 `refs/remotes` 是否为空,所以**"有 remote 但从未 fetch 过"同样命中**
——`git clone` 之后的仓库有 remote-tracking ref,但 `git init` + `git remote add`
而尚未 fetch 的仓库没有。**离线环境、刚建的原型仓、CI 里浅克隆的某些形态都可能落进来。**
