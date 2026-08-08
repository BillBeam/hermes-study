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

`hermes_cli/main.py:45 @ 863e313`

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
# ``hermes update`` to recover.
```

**这是一条一般性设计原则,值得单独记**:
**升级命令自身必须在"升级失败后的半坏状态"下仍可运行。**
`hermes update` 在 `git reset --hard` 与 `pip install -e .` 之间崩溃,会留下
"新源码 + 旧 `.pth`"的组合;若入口 import 硬失败,用户**连修复命令都敲不进去**,
只能手工重装。这个 try 的全部价值就是把"砖化"降级成"少一个 Windows 优化"。

同样的思路在 `main()` 里还有两处兜底:清理上次 update 留下的隔离文件、
以及自愈被打断的 venv 安装。后者的判据写得很坦白:

`hermes_cli/main.py:11216 @ 863e313`

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

`hermes_cli/main.py:709 @ 863e313`

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

`hermes_cli/main.py:364 @ 863e313`

```python
# Mouse-tracking residue suppression — runs BEFORE every other import on the
# TUI hot path so the terminal stops emitting SGR/X10 mouse reports while the
# Python launcher is still doing imports (≈100–300ms in cooked + echo mode,
# before the Node TUI takes stdin into raw mode). During that window any
# incoming bytes are echoed straight back to the user's shell scrollback as
# ``^[[<…M`` text.
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

`hermes_cli/main.py:571 @ 863e313`

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

`hermes_cli/main.py:524 @ 863e313`

```python
        """True once argv reaches `hermes mcp add ... --args <command argv>`.

        ``mcp add --args`` is command-argv passthrough. Flags after that point
        belong to the child MCP command (for example Docker MCP Toolkit's
        ``--profile``), not to Hermes' own profile selector.
        """
```

**(b) 非法 profile 名直接放弃**,理由举了一个真实场景(pytest 的 `-p no:xdist`):

`hermes_cli/main.py:613 @ 863e313`

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

`hermes_cli/main.py:12501 @ 863e313`

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

`hermes_cli/main.py:12509 @ 863e313`

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

`hermes_cli/main.py:12591 @ 863e313`

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

`hermes_cli/main.py:311 @ 863e313`

```python
    Precedence: explicit ``--cli`` wins (forces classic REPL), then
    explicit ``--tui``/``HERMES_TUI=1``, then a real-TTY gate (a
```

代码里环境变量确实**排在 TTY 闸门之前**:

`hermes_cli/main.py:339 @ 863e313`

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

`hermes_cli/main.py:2498 @ 863e313`

```python
    The TTY gate (3) is load-bearing: ambient TUI preferences (env var or
    config default) must never hijack a NON-interactive invocation. Kanban
    workers, cron jobs, and pipelines run ``hermes … chat -q`` with stdout
    on a pipe; booting the Ink TUI there hits its no-TTY bail-out, which
    prints a resume hint and exits 0 — a kanban worker then dies with
    "exited cleanly without calling kanban_complete — protocol violation"
    on every attempt (found dogfooding the desktop kanban board).
```

**同一个环境变量,一个函数叫它 explicit、另一个叫它 ambient**,
而那段 docstring 描述的正是一次真实事故。

**但本轮把三个消费点逐个核完,结论是当前无后果**:

| 消费点 | 锚点 | 为什么安全 |
|---|---|---|
| 鼠标残留抑制 | `main.py:352` | 自带独立 TTY 判断 `if not os.isatty(1): return`(`main.py:357`),非 TTY 直接不写 |
| Termux 快速 CLI 路径 | `main.py:10886` | 返回 True 只是**放弃快速路径**、回落完整分发,分发里再判 |
| Termux 快速 TUI 路径 | `main.py:10958` | 紧接着在 `main.py:10977` 用 `_resolve_use_tui(args)` **重判一次**,不通过就返回 |

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
