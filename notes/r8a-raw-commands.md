# r8a-raw-commands · commands.py 全文

底稿。基线 `863e313`,精读对象 `hermes_cli/commands.py` 全文 2260 行。
本轮读的是**定义侧**(R7C 从网关消费侧读过它,这里补齐欠账)。

约定:凡断言紧跟 `路径:行号 @ 863e313` + 原文代码块。路径相对基线仓库根。

---

## 0. 这个文件是什么

模块自述:它是所有斜杠命令的**中央注册表**,CLI help / 网关 dispatch / Telegram
BotCommands / Slack 子命令映射 / 自动补全全部从 `COMMAND_REGISTRY` 派生。`hermes_cli/commands.py:1-9 @ 863e313`

```python
"""Slash command definitions and autocomplete for the Hermes CLI.

Central registry for all slash commands. Every consumer -- CLI help, gateway
dispatch, Telegram BotCommands, Slack subcommand mapping, autocomplete --
derives its data from ``COMMAND_REGISTRY``.

To add a command: add a ``CommandDef`` entry to ``COMMAND_REGISTRY``.
To add an alias: set ``aliases=("short",)`` on the existing ``CommandDef``.
"""
```

**解决什么问题**:一个 harness 有 6+ 个"命令表面"(CLI REPL、TUI、Telegram 菜单、
Discord 原生斜杠、Slack manifest、网关文本 dispatch)。如果每个表面各自维护一份命令
清单,加一条命令要改 6 处,漏一处就出现"CLI 有 /context 但 Slack 没有"这类静默不一致。
这里的答案是:**声明一次,所有表面从同一个 list 派生**;各表面差异用 `CommandDef`
上的字段(`cli_only` / `gateway_only` / `gateway_config_gate` / `busy_policy`)表达。

**模块级重依赖只有两个**,都是轻量的:`hermes_cli/commands.py:23-24 @ 863e313`

```python
from utils import is_truthy_value
from hermes_constants import INDICATOR_STYLES
```

这个"导入轻量"是刻意的设计约束,下面 §5(prompt_toolkit 垫片)和 `execute` 字段
(§2.10)都是为它服务。

---

## 1. 必答一:`COMMAND_REGISTRY` 到底几条?——**94 条**

### 1.1 数法(三种,互相印证)

**数法 A(AST,权威)**:把文件 parse 成 AST,找到 `COMMAND_REGISTRY` 这个
`AnnAssign` 的 value(一个 list literal),数它的 `elts` 长度,并断言每个元素都是
`CommandDef(...)` 调用。结果 **94**。脚本我放在 scratchpad,核心逻辑是:

```
tree = ast.parse(open('hermes_cli/commands.py').read())
reg = <the AnnAssign whose target.id == 'COMMAND_REGISTRY'>.value
assert all(isinstance(e, ast.Call) and e.func.id == 'CommandDef' for e in reg.elts)
len(reg.elts) == 94
```

**数法 B(文本,交叉验证)**:`grep -c "^    CommandDef(" hermes_cli/commands.py` = 94,
且 `sed -n '102,342p' | grep -c "CommandDef("` = 94(两者相等 ⇒ 文件里没有别处出现
`CommandDef(` 构造,也没有一行写两个)。

**数法 C(运行时,最终确认)**:`PYTHONPATH=/home/user/hermes-agent python3 -c
"from hermes_cli import commands as C; print(len(C.COMMAND_REGISTRY))"` → **94**。

三法一致 ⇒ **94 条 `CommandDef`**。上一轮报告称的 94 条**核实无误**。

列表的起止:`hermes_cli/commands.py:102 @ 863e313`

```python
COMMAND_REGISTRY: list[CommandDef] = [
```

`hermes_cli/commands.py:342 @ 863e313`

```python
]
```

### 1.2 别名算不算另一条?——**不算**

别名是 `CommandDef` 上的一个字段,不是独立条目。`hermes_cli/commands.py:53 @ 863e313`

```python
    aliases: tuple[str, ...] = ()      # alternative names: ("bg",)
```

数据(AST 统计):**24 条**命令带别名,别名共 **26 个**,全部唯一,且**没有任何别名与
任何 canonical name 撞名**。canonical 94 + alias 26 = **120 个可解析 token**。

24 条带别名的命令(canonical → aliases):

```
new→reset          prompt→compose      branch→fork         compress→compact
snapshot→snap      background→bg,btw   agents→tasks        journey→learning,memory-graph
queue→q            heartbeat→hb        context→ctx         sethome→set-home
codex-runtime→codex_runtime            statusbar→sb        timestamps→ts
hatch→generate-pet suggestions→suggest blueprint→bp        reload-mcp→reload_mcp
reload-skills→reload_skills            subscription→upgrade
platforms→gateway  version→v           quit→exit
```

注意别名有两类语义混在一起:(a) **真短名**(bg / q / ctx / hb / v),(b) **拼写变体**
(`reload_mcp` vs `reload-mcp`、`set-home` vs `sethome`、`codex_runtime` vs
`codex-runtime`)。后者是为了让 Telegram(命令名不能有连字符)回传的下划线形式也能解析。
这两类在 `gateway_help_lines()` 里被区别对待(§4.1)。

### 1.3 94 条的横切分布(AST 统计,可复算)

| 维度 | 数值 |
|---|---|
| 总条目 | 94 |
| category | Session 36 / Configuration 21 / Tools & Skills 19 / Info 17 / Exit 1 |
| `cli_only=True` | 35 |
| `gateway_only=True` | 8(start, topic, approve, deny, sethome, commands, restart, platform) |
| 既 cli_only 又 gateway_only | 0(互斥,但**无代码强制**,见 §7) |
| `gateway_config_gate` 非空 | 2(verbose→`display.tool_progress_command`,skills→`skills.write_approval`) |
| `busy_policy="reject"`(默认) | 69 |
| `busy_policy="dispatch"` | 23 |
| `busy_policy="interrupt_then_dispatch"` | 2(new, stop) |
| `busy_handler` 非空 | 10 |
| `execute` 非空 | 6(egress, profile, bundles, commands→gateway_commands, help→gateway_help, version) |
| 网关可见(`not cli_only`) | **59** |

派生字典的实际规模(运行时实测,HERMES_HOME 指向空目录,两个 gate 都关):

```
len(COMMANDS)               = 111   # 94-8(gateway_only) + 26-1(set-home 属 gateway_only) = 86+25
len(COMMANDS_BY_CATEGORY)   = 5 个 category
len(SUBCOMMANDS)            = 31    # 24 显式 + 7 从 args_hint 正则提取
len(GATEWAY_KNOWN_COMMANDS) = 77    # (59+2gated) canonical + 16 非 cli_only 的别名
len(gateway_help_lines())   = 59
len(telegram_bot_commands())= 59
len(slack_native_slashes()) = 50    # 恰好顶到 Slack 上限
len(slack_subcommand_map()) = 75    # 59 canonical + 16 alias
```

---

## 2. 必答二:`CommandDef` 每个字段的语义

数据类是 frozen 的(不可变、可 hash)。`hermes_cli/commands.py:46-48 @ 863e313`

```python
@dataclass(frozen=True)
class CommandDef:
    """Definition of a single slash command."""
```

### 2.1 `name` / `description` / `category`(三个位置参数)

`hermes_cli/commands.py:50-52 @ 863e313`

```python
    name: str                          # canonical name without slash: "background"
    description: str                   # human-readable description
    category: str                      # "Session", "Configuration", etc.
```

- `name`:**不带斜杠**的 canonical 名。所有查表、hook 名、busy 分发都用它。
- `description`:一句话人读说明。会被直接塞进 Telegram BotCommand / Slack manifest,
  所以受下游长度限制约束(Telegram 描述被截到 40 字符,Discord 100,Slack 140,见 §4.4)。
- `category`:纯展示分组,仅 `COMMANDS_BY_CATEGORY` 和 TUI catalog 用。注册表里有个小
  瑕疵:`export` / `import` 两条写在 "# Session" 注释块里但 category 填的是
  "Configuration",而 `sessions` 上面顶着两行 "# Configuration" 注释却是 "Session" 类
  —— 注释与字段不一致,只影响读代码的人。`hermes_cli/commands.py:136-137 @ 863e313`

```python
    CommandDef("export", "Export a profile (config, skills, theme) to a shareable archive", "Configuration",
               cli_only=True, args_hint="[profile] [-o output.tar.gz]"),
```

`hermes_cli/commands.py:189-190 @ 863e313`

```python
    # Configuration
    CommandDef("sessions", "Browse and resume previous sessions", "Session"),
```

### 2.2 `aliases`

见 §1.2。写法 `aliases=("short",)`。

### 2.3 `args_hint`

`hermes_cli/commands.py:54 @ 863e313`

```python
    args_hint: str = ""                # argument placeholder: "<prompt>", "[name]"
```

三个用途:
1. 拼进 CLI 描述:`_build_description()`。`hermes_cli/commands.py:370-374 @ 863e313`

```python
def _build_description(cmd: CommandDef) -> str:
    """Build a CLI-facing description string including usage hint."""
    if cmd.args_hint:
        return f"{cmd.description} (usage: /{cmd.name} {cmd.args_hint})"
    return cmd.description
```

2. 判定"必填参数":以 `<` 开头 ⇒ 必填。`hermes_cli/commands.py:544-546 @ 863e313`

```python
def _requires_argument(args_hint: str) -> bool:
    """Return True when selecting a command without text would be incomplete."""
    return args_hint.strip().startswith("<")
```

3. **兜底推导 subcommands**(见 §2.4,有坑)。

`args_hint` 有一条是运行期算出来的,不是字面量:`hermes_cli/commands.py:239-241 @ 863e313`

```python
    CommandDef("indicator", "Pick the TUI busy-indicator style", "Configuration",
               cli_only=True, args_hint=f"[{'|'.join(INDICATOR_STYLES)}]",
               subcommands=INDICATOR_STYLES),
```

`INDICATOR_STYLES = ("ascii","emoji","kaomoji","unicode")`。`hermes_constants.py:26 @ 863e313`

```python
INDICATOR_STYLES: tuple[str, ...] = ("ascii", "emoji", "kaomoji", "unicode")
```

### 2.4 `subcommands` —— 以及 args_hint 正则兜底的三个笔误级坑

字段本身:`hermes_cli/commands.py:55 @ 863e313`

```python
    subcommands: tuple[str, ...] = ()  # tab-completable subcommands
```

显式 subcommands 先进 `SUBCOMMANDS`。`hermes_cli/commands.py:396-399 @ 863e313`

```python
SUBCOMMANDS: dict[str, list[str]] = {}
for _cmd in COMMAND_REGISTRY:
    if _cmd.subcommands:
        SUBCOMMANDS[f"/{_cmd.name}"] = list(_cmd.subcommands)
```

没有显式 subcommands 的,用正则从 `args_hint` 里抠管道分隔的 token。`hermes_cli/commands.py:405-412 @ 863e313`

```python
_PIPE_SUBS_RE = re.compile(r"[a-z]+(?:\|[a-z]+)+")
for _cmd in COMMAND_REGISTRY:
    key = f"/{_cmd.name}"
    if key in SUBCOMMANDS or not _cmd.args_hint:
        continue
    m = _PIPE_SUBS_RE.search(_cmd.args_hint)
    if m:
        SUBCOMMANDS[key] = m.group(0).split("|")
```

正则字符类只有 `[a-z]`,**连字符、下划线、数字、`--` 前缀都不认**,而且只取
`search()` 的第一个匹配。实测(运行时打印)这 7 条是正则推导出来的:

```
/topic          -> ['off', 'help', 'session']        # args_hint "[off|help|session-id]"
/snapshot       -> ['create', 'restore']             # args_hint "[create|restore <id>|prune]"
/approve        -> ['session', 'always']
/codex-runtime  -> ['auto', 'codex']                 # args_hint "[auto|codex_app_server]"
/tools          -> ['list', 'disable', 'enable']
/platform       -> ['pause', 'resume', 'list']
/debug          -> ['nous', 'local']
```

三个可疑缺陷(只记录不修):

- **`/topic` 补出 `session`**。真实 args_hint 是 `[off|help|session-id]`,`session-id` 是
  "填一个 session id" 的占位符,正则在 `-` 处断掉,于是 TUI 会把 `session` 当成一个
  真实子命令提示给用户。`hermes_cli/commands.py:109-110 @ 863e313`

```python
    CommandDef("topic", "Enable or inspect Telegram DM topic sessions", "Session",
               gateway_only=True, args_hint="[off|help|session-id]"),
```

- **`/codex-runtime` 补出 `codex`**,真实值是 `codex_app_server`。用户按提示敲
  `/codex-runtime codex` 大概率不是合法值。`hermes_cli/commands.py:198-201 @ 863e313`

```python
    CommandDef("codex-runtime", "Toggle codex app-server runtime for OpenAI/Codex models",
               "Configuration", aliases=("codex_runtime",),
               args_hint="[auto|codex_app_server]",
               busy_policy="reject", busy_handler="codex-runtime"),
```

- **`/snapshot` 丢了 `prune`**,因为 `restore <id>` 里的空格把管道链切断。`hermes_cli/commands.py:134-135 @ 863e313`

```python
    CommandDef("snapshot", "Create or restore state snapshots of Hermes config/state", "Session",
               cli_only=True, aliases=("snap",), args_hint="[create|restore <id>|prune]"),
```

怎么会踩到:纯补全层面的误导,不会让命令跑错(handler 自己会校验),但用户按 Tab 得到
一个不存在的子命令。代码里的注释其实已经给出了正确做法("Use the `subcommands` field
… for intentional tab-completable args"),这三条只是没照做。`hermes_cli/commands.py:403-404 @ 863e313`

```python
# NOTE: If a command already has explicit subcommands, this fallback is skipped.
# Use the `subcommands` field on CommandDef for intentional tab-completable args.
```

### 2.5 `cli_only`

`hermes_cli/commands.py:56 @ 863e313`

```python
    cli_only: bool = False             # only available in CLI
```

**这是网关侧的真门**:`GATEWAY_KNOWN_COMMANDS` 和 `_is_gateway_available()` 都读它。
在网关上敲一条 cli_only 命令,会走到"未知命令"分支(除非它带 config gate 且 gate 开)。

### 2.6 `gateway_only`

`hermes_cli/commands.py:57 @ 863e313`

```python
    gateway_only: bool = False         # only available in gateway/messaging
```

**这是 CLI 侧的软门,而且只影响展示**:它只在构造 `COMMANDS` / `COMMANDS_BY_CATEGORY`
时被过滤掉。`hermes_cli/commands.py:379-383 @ 863e313`

```python
for _cmd in COMMAND_REGISTRY:
    if not _cmd.gateway_only:
        COMMANDS[f"/{_cmd.name}"] = _build_description(_cmd)
        for _alias in _cmd.aliases:
            COMMANDS[f"/{_alias}"] = f"{_cmd.description} (alias for /{_cmd.name})"
```

`hermes_cli/commands.py:387-392 @ 863e313`

```python
for _cmd in COMMAND_REGISTRY:
    if not _cmd.gateway_only:
        _cat = COMMANDS_BY_CATEGORY.setdefault(_cmd.category, {})
        _cat[f"/{_cmd.name}"] = COMMANDS[f"/{_cmd.name}"]
        for _alias in _cmd.aliases:
            _cat[f"/{_alias}"] = COMMANDS[f"/{_alias}"]
```

全仓范围内 `gateway_only` 只有一个外部读者,是 TUI 的命令目录:`tui_gateway/methods_tools.py:272 @ 863e313`

```python
            if cmd.name in _TUI_HIDDEN or cmd.gateway_only:
```

而 `cli_only` 在 commands.py 与 tests 之外**没有任何读者**(grep 全仓确认)。含义:
两个 flag 都是"该不该出现在这个表面的清单里"的声明,**不是执行期拒绝**;真正的拒绝
来自"不在清单里 ⇒ 解析不到 ⇒ 走未知命令分支"。

### 2.7 `gateway_config_gate`

`hermes_cli/commands.py:58 @ 863e313`

```python
    gateway_config_gate: str | None = None  # config dotpath; when truthy, overrides cli_only for gateway
```

详见 §3(必答三)。

### 2.8 `busy_policy`

`hermes_cli/commands.py:59-75 @ 863e313`

```python
    # Mid-run (agent busy) gateway behavior.  Drives the Guard-2 dispatcher
    # in gateway/run.py (_dispatch_busy_slash_command) instead of a
    # hand-written per-command if-chain.  Values:
    #   "dispatch"                — run the command while the agent is busy
    #                               (via its normal handler, or the mid-run
    #                               variant named by ``busy_handler``).
    #   "reject"                  — refuse mid-run.  Without ``busy_handler``
    #                               the generic "Agent is running — `/<cmd>`
    #                               can't run mid-turn" catch-all is returned;
    #                               with ``busy_handler`` a command-specific
    #                               reject message is used.
    #   "interrupt_then_dispatch" — interrupt/kill the running agent first,
    #                               then dispatch (the /stop, /new, /reset
    #                               class).  Guard 1 (platforms/base.py)
    #                               routes these through the cancel-handoff
    #                               path via is_interrupt_then_dispatch().
    busy_policy: str = "reject"
```

合法值集合定义在这里:`hermes_cli/commands.py:93-95 @ 863e313`

```python
VALID_BUSY_POLICIES: frozenset[str] = frozenset(
    {"dispatch", "reject", "interrupt_then_dispatch"}
)
```

**可疑缺陷:`VALID_BUSY_POLICIES` 从未被使用来校验任何东西。** 全仓 grep 只有两处出现:
定义处,以及 `tests/hermes_cli/test_busy_policy_invariants.py:13` 的 import —— 而那个测
试文件 import 了它却没有任何断言引用它(文件里只有两个 test 函数,都不碰它)。`tests/hermes_cli/test_busy_policy_invariants.py:10-16 @ 863e313`

```python
from hermes_cli.commands import (
    ACTIVE_SESSION_BYPASS_COMMANDS,
    COMMAND_REGISTRY,
    VALID_BUSY_POLICIES,
    is_interrupt_then_dispatch,
    should_bypass_active_session,
)
```

怎么会踩到:给新命令写 `busy_policy="dispatchh"`(拼错)不会有任何报错。派生集合
`ACTIVE_SESSION_BYPASS_COMMANDS`(`!= "reject"`)会把它算成 bypass,而网关的
`policy in ("dispatch","interrupt_then_dispatch")` 判定为假,直接掉到 catch-all
拒绝文案 —— 表现是"这条命令永远说 agent 忙",且没有 warning。

### 2.9 `busy_handler`

`hermes_cli/commands.py:76-80 @ 863e313`

```python
    # Optional key of a special mid-run handler in the Guard-2 handler table
    # (gateway/run.py) for commands whose busy behavior differs from their
    # normal handler (e.g. /goal's control-verb whitelist, /queue's FIFO
    # enqueue, /model's custom busy-reject text).
    busy_handler: str | None = None
```

10 条命令用了它:`start, new, stop, queue, steer, goal, moa, egress, model, codex-runtime`
(handler key 与 name 同名)。消费端在网关,分两张表:特殊 handler 表和"自定义拒绝文案"
表。`gateway/run.py:14120-14131 @ 863e313`

```python
        if handler_key:
            special = {
                "start": self._busy_start_command,
                "stop": self._busy_stop_command,
                "new": self._busy_new_command,
                "queue": self._busy_queue_command,
                "steer": self._busy_steer_command,
                "egress": self._busy_egress_command,
                "goal": self._busy_goal_command,
            }.get(handler_key)
            if special is not None:
                return await special(event, quick_key, source)
```

`gateway/run.py:14091-14096 @ 863e313`

```python
    _BUSY_REJECT_TEXT: Dict[str, str] = {
        "model": "Agent is running — wait or /stop first, then switch models.",
        "codex-runtime": ("Agent is running — wait or /stop first, then "
                          "change runtime."),
        "moa": "Agent is running — wait or /stop first, then run /moa.",
    }
```

我核对过:10 个 `busy_handler` 值全部命中这两张表之一(7 special + 3 reject text),
23 条 `dispatch` 命令全部在 special 表或普通表里有 handler,`interrupt_then_dispatch`
的 new/stop 也都有 —— **当前没有孤儿声明**。网关对孤儿的兜底是打 warning 然后拒绝。`gateway/run.py:14159-14162 @ 863e313`

```python
            logger.warning(
                "busy_policy=%s for /%s has no mid-run handler — "
                "falling back to busy-reject", policy, name,
            )
```

### 2.10 `execute` —— 用字符串键换取"导入轻量"

`hermes_cli/commands.py:81-89 @ 863e313`

```python
    # Registry-owned shared execution (thin slice, informational commands).
    # Names a key in ``hermes_cli.slash_exec.EXECUTORS`` — a pure formatter
    # producing the canonical, surface-independent core text.  Surfaces
    # resolve it via ``hermes_cli.slash_exec.run_execute`` and apply only
    # their own decoration (Rich markup, emoji/markdown, telegramize).  A
    # string key (not a callable) keeps this module import-light: the
    # gateway can import commands.py without prompt_toolkit and without
    # pulling in executor dependencies.
    execute: str | None = None
```

6 条命令已迁移到共享执行器。`hermes_cli/slash_exec.py:234-241 @ 863e313`

```python
EXECUTORS: dict[str, Callable[[CommandContext], CommandReply]] = {
    "version": _exec_version,
    "egress": _exec_egress,
    "profile": _exec_profile,
    "bundles": _exec_bundles,
    "gateway_help": _exec_help,
    "gateway_commands": _exec_commands,
}
```

**为什么用字符串不用 callable**:如果字段直接存函数对象,`commands.py` 就必须 import
`slash_exec`,而 `slash_exec` 的 executor 又要 import 各自的实现模块 —— 网关只想拿命令
元数据,却被拖进一条完整依赖链。字符串键把"注册"和"实现"解耦成一次延迟查表。
`slash_exec` 自己的模块头把这条纪律写死了。`hermes_cli/slash_exec.py:14-17 @ 863e313`

```python
Import discipline: this module imports nothing heavy at module level and
``hermes_cli.commands`` does NOT import this module (the ``execute`` field is
a plain string), so the gateway can keep importing ``commands.py`` without
prompt_toolkit and without cycles.
```

**取舍**:字符串键没有类型检查,写错 key 就是 `EXECUTORS.get(key)` 返回 None、表面
静默回落到自己的老实现(`resolve_executor` 返回 None 即"未迁移")。`hermes_cli/slash_exec.py:244-249 @ 863e313`

```python
def resolve_executor(cmd_def: Any) -> Callable[[CommandContext], CommandReply] | None:
    """Return the shared executor for ``cmd_def`` (or None when not migrated)."""
    key = getattr(cmd_def, "execute", None)
    if not key:
        return None
    return EXECUTORS.get(key)
```

---

## 3. 必答三:配置门控 —— `_resolve_config_gates()` 与 `_is_gateway_available()`

### 3.1 场景

`/verbose`(切换工具进度显示档位)默认只在 CLI 有。但有人在 Telegram 上也想开。做法
不是加一条新命令,而是给它挂一个**配置门**:`gateway_config_gate="display.tool_progress_command"`。`hermes_cli/commands.py:216-219 @ 863e313`

```python
    CommandDef("verbose", "Cycle tool progress display: off -> new -> all -> verbose -> log",
               "Configuration", cli_only=True,
               gateway_config_gate="display.tool_progress_command",
               busy_policy="dispatch"),
```

另一条是 `/skills`,门是 `skills.write_approval`。`hermes_cli/commands.py:256-260 @ 863e313`

```python
    CommandDef("skills", "Search, install, inspect, or manage skills",
               "Tools & Skills", cli_only=True,
               gateway_config_gate="skills.write_approval",
               subcommands=("search", "browse", "inspect", "install", "audit",
                            "pending", "approve", "reject", "diff", "approval")),
```

全仓只有这两条带 gate(AST 统计确认)。

### 3.2 `_resolve_config_gates()` —— 一次读配置,算出"哪些门开了"

`hermes_cli/commands.py:499-505 @ 863e313`

```python
def _resolve_config_gates() -> set[str]:
    """Return canonical names of commands whose ``gateway_config_gate`` is truthy.

    Reads ``config.yaml`` and walks the dot-separated key path for each
    config-gated command.  Returns an empty set on any error so callers
    degrade gracefully.
    """
```

实现分四步:

**① 空转短路**:注册表里没有带 gate 的命令就直接返回,连配置都不读。`hermes_cli/commands.py:506-508 @ 863e313`

```python
    gated = [c for c in COMMAND_REGISTRY if c.gateway_config_gate]
    if not gated:
        return set()
```

**② 读原始配置(不合并默认值,不迁移)**,任何异常都吞成空集。`hermes_cli/commands.py:509-513 @ 863e313`

```python
    try:
        from hermes_cli.config import read_raw_config
        cfg = read_raw_config()
    except Exception:
        return set()
```

`read_raw_config()` 的语义要点:只读 `~/.hermes/config.yaml` 原文,**不 deep-merge
默认值、不跑迁移**,文件不存在或解析失败返回 `{}`,按 `(mtime_ns, size)` 缓存。`hermes_cli/config.py:2933-2939 @ 863e313`

```python
def read_raw_config() -> Dict[str, Any]:
    """Read ~/.hermes/config.yaml as-is, without merging defaults or migrating.

    Returns the raw YAML dict, or ``{}`` if the file doesn't exist or can't
    be parsed.  Use this for lightweight config reads where you just need a
    single value and don't want the overhead of ``load_config()``'s deep-merge
    + migration pipeline.
```

**③ 逐条走点分路径**,中途遇到非 dict 就判定为 None。`hermes_cli/commands.py:514-522 @ 863e313`

```python
    result: set[str] = set()
    for cmd in gated:
        val: Any = cfg
        for key in cmd.gateway_config_gate.split("."):
            if isinstance(val, dict):
                val = val.get(key)
            else:
                val = None
                break
```

**④ 用项目共享的 truthy 语义判真**,默认 False。`hermes_cli/commands.py:523-525 @ 863e313`

```python
        if is_truthy_value(val, default=False):
            result.add(cmd.name)
    return result
```

`is_truthy_value` 的语义(为什么 `"true"` / `"yes"` 这种字符串也算开):`utils.py:22-30 @ 863e313`

```python
def is_truthy_value(value: Any, default: bool = False) -> bool:
    """Coerce bool-ish values using the project's shared truthy string set."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_STRINGS
    return bool(value)
```

我实测过:写 `skills: {write_approval: "yes"}` 的 YAML(字符串而非布尔),
`_resolve_config_gates()` 返回 `{'skills', 'verbose'}` —— 字符串确实被认。

### 3.3 `_is_gateway_available()` —— 门与 cli_only 的合成

`hermes_cli/commands.py:528-541 @ 863e313`

```python
def _is_gateway_available(cmd: CommandDef, config_overrides: set[str] | None = None) -> bool:
    """Check if *cmd* should appear in gateway surfaces (help, menus, mappings).

    Unconditionally available when ``cli_only`` is False.  When ``cli_only``
    is True but ``gateway_config_gate`` is set, the command is available only
    when the config value is truthy.  Pass *config_overrides* (from
    ``_resolve_config_gates()``) to avoid re-reading config for every command.
    """
    if not cmd.cli_only:
        return True
    if cmd.gateway_config_gate:
        overrides = config_overrides if config_overrides is not None else _resolve_config_gates()
        return cmd.name in overrides
    return False
```

真值表(三行讲完):

| cli_only | gate | 结果 |
|---|---|---|
| False | 任意 | **可见**(注意:`gateway_only=True` 也走这条,因为 gateway_only 命令的 cli_only 是 False) |
| True | 无 | **不可见** |
| True | 有 | gate 开则可见,关则不可见 |

`config_overrides` 参数是**性能接缝**:每个表面构建函数在循环外算一次
`_resolve_config_gates()`,循环里传进来,避免 94 次配置读取。所有调用点都遵守了这个约定
(`gateway_help_lines` :551、`telegram_bot_commands` :614、`slack_native_slashes` :1311、
`slack_subcommand_map` :1407,以及 Discord adapter),`None` 分支是给零散调用者的兜底。

### 3.4 门控命令仍然可 dispatch —— 关键的不对称

`GATEWAY_KNOWN_COMMANDS`(网关"这是不是一条命令"的判定集)**故意包含**带 gate 的
cli_only 命令,把 gate 的具体判定推迟到 handler。`hermes_cli/commands.py:419-427 @ 863e313`

```python
# Set of all command names + aliases recognized by the gateway.
# Includes config-gated commands so the gateway can dispatch them
# (the handler checks the config gate at runtime).
GATEWAY_KNOWN_COMMANDS: frozenset[str] = frozenset(
    name
    for cmd in COMMAND_REGISTRY
    if not cmd.cli_only or cmd.gateway_config_gate
    for name in (cmd.name, *cmd.aliases)
)
```

**为什么这么设计**:如果 gate 关时网关连"这是命令"都不认,用户在 Telegram 敲 `/verbose`
只会得到 "Unknown command"。现在它被认作命令,handler 里再返回"没开,请在 config.yaml
里打开"的可操作提示。这条提示文案在 locale 里(每种语言一份)。`locales/en.yaml:419 @ 863e313`

```yaml
    not_enabled:           "The `/verbose` command is not enabled for messaging platforms.\n\nEnable it in `config.yaml`:\n```yaml\ndisplay:\n  tool_progress_command: true\n```"
```

handler 侧的二次判定(与 `_resolve_config_gates` 用同一个 `is_truthy_value` 语义,但走
的是网关自己的 config 读取):`gateway/slash_commands.py:3801 @ 863e313`

```python
        Gated by ``display.tool_progress_command`` in config.yaml (default off).
```

所以门控是**两层**:第一层 `_is_gateway_available`(决定"出不出现在 help/菜单/manifest"),
第二层 handler 运行时(决定"跑不跑")。两层读同一个键。

### 3.5 门控机制的三个取舍与陷阱

**取舍 1:读 raw config 而不是 merged config。** 好处是快(不跑 deep-merge + migration
管线),坏处是**它看不见 `config_defaults.py` 里的默认值**。今天两个 gate 的默认值都是
`False`,所以"key 缺失 ⇒ 判 False"恰好等于"默认值 False",没有 bug。但如果将来某个
gate 的默认值是 `True`,用户没写这个 key 时 `_resolve_config_gates()` 会判成关 —— 与
`load_config()` 的结果不一致。**这是一个待踩的坑,不是当前 bug。** 默认值位置:
`hermes_cli/config_defaults.py:1200 @ 863e313`

```python
        "tool_progress_command": False,  # Enable /verbose command in messaging gateway
```

`hermes_cli/config_defaults.py:1829 @ 863e313`

```python
        "write_approval": False,
```

**取舍 2:全异常吞成空集 = 门静默关闭。** `config.yaml` 写坏(YAML 语法错)时
`read_raw_config` 返回 `{}`,gate 判 False,`/verbose` 与 `/skills` **从 Telegram 菜单、
Slack manifest、Discord 注册里静默消失**,用户只会觉得"命令没了",没有任何指向配置损坏
的信号。怎么会踩到:手改 config.yaml 缩进出错 → 重启网关 → 菜单少两条。

**取舍 3:gate 值被复用成"两件事"。** `skills.write_approval` 的本职是"技能写入是否需要
审批",顺带被借用为"`/skills` 在网关上可不可见"。语义耦合:一个只想在网关用
`/skills search` 的用户,必须打开写入审批门。反过来,关掉审批门就会顺手把网关上的
`/skills` 全部功能藏掉。这是把"功能开关"当"可见性开关"用的典型代价。

---

## 4. 必答四:Telegram 菜单那一套

### 4.1 上游:`telegram_bot_commands()` —— 只出 canonical,连字符转下划线

`hermes_cli/commands.py:600-612 @ 863e313`

```python
def telegram_bot_commands() -> list[tuple[str, str]]:
    """Return (command_name, description) pairs for Telegram setMyCommands.

    Telegram command names cannot contain hyphens, so they are replaced with
    underscores.  Aliases are skipped -- Telegram shows one menu entry per
    canonical command.

    Built-in commands that require arguments (e.g. /queue, /steer, /background)
    are **included** because their handlers return usage text when selected
    without a payload, making them discoverable via autocomplete.

    Plugin-registered slash commands that require arguments are **excluded**
    because plugins may not provide a no-arg usage fallback.
    """
```

内置命令的循环:只过 `_is_gateway_available`,不过 `_requires_argument`。`hermes_cli/commands.py:616-624 @ 863e313`

```python
    for cmd in COMMAND_REGISTRY:
        if not _is_gateway_available(cmd, overrides):
            continue
        # Built-in arg-taking commands are included — their handlers show
        # usage text when invoked without arguments, and hiding them from
        # the menu hurts discoverability (issue #24312).
        tg_name = _sanitize_telegram_name(cmd.name)
        if tg_name:
            result.append((tg_name, cmd.description))
```

插件命令的循环:**要参数的被排除**(插件不保证有 no-arg usage 兜底)。`hermes_cli/commands.py:625-630 @ 863e313`

```python
    for name, description, args_hint in _iter_plugin_command_entries():
        if _requires_argument(args_hint):
            continue
        tg_name = _sanitize_telegram_name(name)
        if tg_name:
            result.append((tg_name, description))
```

名字消毒规则(Telegram 只认 `a-z0-9_`,1-32 字符):`hermes_cli/commands.py:797-808 @ 863e313`

```python
def _sanitize_telegram_name(raw: str) -> str:
    """Convert a command/skill/plugin name to a valid Telegram command name.

    Telegram requires: 1-32 chars, lowercase a-z, digits 0-9, underscores only.
    Steps: lowercase → replace hyphens with underscores → strip all other
    invalid characters → collapse consecutive underscores → strip leading/
    trailing underscores.
    """
    name = raw.lower().replace("-", "_")
    name = _TG_INVALID_CHARS.sub("", name)
    name = _TG_MULTI_UNDERSCORE.sub("_", name)
    return name.strip("_")
```

注意"消毒后为空串就跳过"(`if tg_name:`)—— 名字全是非法字符的技能会被静默丢弃,
测试 `test_empty_sanitized_names_excluded` 盯这条。

**别名被跳过**这件事在 `gateway_help_lines()` 里有个对应的、更细的规则:help 行会列别名,
但**下划线/连字符同形别名不列**(避免 "/reload-mcp (alias: /reload_mcp)" 这种噪音)。`hermes_cli/commands.py:558-563 @ 863e313`

```python
        for a in cmd.aliases:
            # Skip internal aliases like reload_mcp (underscore variant)
            if a.replace("-", "_") == cmd.name.replace("-", "_") and a != cmd.name:
                continue
            alias_parts.append(f"`/{a}`")
        alias_note = f" (alias: {', '.join(alias_parts)})" if alias_parts else ""
```

### 4.2 为什么要有这一套?—— 60 与 100 分别是什么约束

`hermes_cli/commands.py:634-639 @ 863e313`

```python
# Telegram allows up to 100 BotCommands. Hermes ships ~50 built-in commands;
# a 60-slot default keeps every built-in plus common skill commands visible in
# the `/` menu while staying comfortably under Telegram's ~4KB payload limit.
# Users can tune this via platforms.telegram.extra.command_menu.max_commands.
_DEFAULT_TELEGRAM_MENU_MAX_COMMANDS = 60
_TELEGRAM_BOT_API_MAX_COMMANDS = 100
```

两个常量分别是:

- **`_TELEGRAM_BOT_API_MAX_COMMANDS = 100`** —— **Telegram Bot API 的硬上限**
  (`setMyCommands` 最多 100 个 BotCommand)。它只用于**钳制用户配置值的上界**,
  用户写 999 会被压到 100。
- **`_DEFAULT_TELEGRAM_MENU_MAX_COMMANDS = 60`** —— **Hermes 自己选的软上限默认值**。
  理由写在注释里:Telegram 还有一个**未公开的 payload 体积限制(约 4KB)**,100 条
  带描述的命令可能撑爆它,导致 `setMyCommands` 整体失败(不是截断,是失败)。60 是
  "留余量"的经验值。

**存在的根本原因**:Hermes 的命令空间(94 条注册表 + 插件命令 + 用户技能命令,技能可能
上百条)远超 Telegram 菜单能承载的量,而 Telegram 菜单是**唯一的发现入口**(手机上没
Tab 补全)。所以必须有一个"谁上榜"的策略,而不是随便截断。

**注释里的 "~50 built-in commands" 与实测不符**:实测 `len(telegram_bot_commands()) == 59`
(两个 gate 都关时)。因此 60 的余量只剩 **1 个槽**给插件+技能,而不是注释和文档声称的
"every built-in plus common skill commands"。见 §9 文档冲突。

### 4.3 `_TELEGRAM_MENU_PRIORITY` —— 截断策略的核心

`hermes_cli/commands.py:642-671 @ 863e313`

```python
_TELEGRAM_MENU_PRIORITY = (
    # Most-typed everyday commands first.
    "help",
    "new",
    "stop",
    "status",
    "egress",
    "resume",
    "sessions",
    "model",
    # Maintenance / diagnostics — the ones that prompted this priority list.
    "debug",
    "restart",
    "update",
    "verbose",
    "commands",
    # Mid-turn session control.
    "approve",
    "deny",
    "queue",
    "steer",
    "background",
    # Lower-priority but still useful operational built-ins.
    "reasoning",
    "usage",
    "platforms",
    "platform",
    "profile",
    "whoami",
)
```

24 条。它的存在理由写在紧随的 docstring 里。`hermes_cli/commands.py:672-677 @ 863e313`

```python
"""Built-in commands that should stay visible in Telegram's capped menu.

Telegram only displays a small BotCommand menu in practice.  The full Hermes
registry is still dispatchable when typed manually, but operational commands
need to survive the visible menu cap ahead of lower-priority built-ins.
"""
```

用户可以叠加自己的优先列表,三种合并模式:`hermes_cli/commands.py:745-757 @ 863e313`

```python
def _telegram_effective_priority() -> tuple[str, ...]:
    menu_cfg = _telegram_command_menu_config()
    configured = list(_dedupe_sanitized_names(menu_cfg["priority"]))
    defaults = list(_dedupe_sanitized_names(_TELEGRAM_MENU_PRIORITY))

    if menu_cfg["priority_mode"] == "replace":
        raw_priority = configured
    elif menu_cfg["priority_mode"] == "append":
        raw_priority = defaults + configured
    else:
        raw_priority = configured + defaults

    return _dedupe_sanitized_names(raw_priority)
```

排序是**稳定的两段式**:在优先表里的按优先表次序排前面,不在的按注册表原序排后面。`hermes_cli/commands.py:760-782 @ 863e313`

```python
def _prioritize_telegram_menu_commands(
    commands: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    priority = {
        name: index
        for index, name in enumerate(_telegram_effective_priority())
    }
    return [
        command
        for _index, command in sorted(
            enumerate(commands),
            key=lambda item: (
                0,
                priority[item[1][0]],
                item[0],
            )
            if item[1][0] in priority
            else (
                1,
                item[0],
            ),
        )
    ]
```

排序键是**变长元组**(`(0,p,i)` vs `(1,i)`),Python 先比首元素 0<1,所以不会因为长度
不同抛 TypeError。写法有点绕但正确。

### 4.4 截断在哪里发生

`hermes_cli/commands.py:1000-1015 @ 863e313`

```python
    core_commands = _prioritize_telegram_menu_commands(list(telegram_bot_commands()))
    reserved_names = {n for n, _ in core_commands}
    all_commands = list(core_commands)
    hidden_core_count = max(0, len(all_commands) - max_commands)

    remaining_slots = max(0, max_commands - len(all_commands))
    entries, hidden_count = _collect_gateway_skill_entries(
        platform="telegram",
        max_slots=remaining_slots,
        reserved_names=reserved_names,
        desc_limit=40,
        sanitize_name=_sanitize_telegram_name,
    )
    # Drop the cmd_key — Telegram only needs (name, desc) pairs.
    all_commands.extend((n, d) for n, d, _k in entries)
    return all_commands[:max_commands], hidden_count + hidden_core_count
```

三层优先级(docstring 明说):`hermes_cli/commands.py:986-991 @ 863e313`

```python
    Priority order (higher priority = never bumped by overflow):
      1. Core CommandDef commands (always included)
      2. Plugin slash commands (take precedence over skills)
      3. Built-in skill commands (fill remaining slots, alphabetical)
```

技能/插件那一层在 `_collect_gateway_skill_entries` 里,插件永不裁、技能填剩余槽。`hermes_cli/commands.py:970-976 @ 863e313`

```python
    # Skills fill remaining slots — only tier that gets trimmed
    remaining = max(0, max_slots - len(all_entries))
    hidden_count = max(0, len(skill_triples) - remaining)
    for n, d, k in skill_triples[:remaining]:
        all_entries.append((n, d, k))

    return all_entries[:max_slots], hidden_count
```

### 4.5 会不会截掉重要命令?—— 会,但被优先表挡住了大部分

我做了两组实测:

**实测 A(两个 gate 关,cap=60)**:core=59,菜单 59 条,hidden=0,技能只剩 1 槽。
菜单尾部是 `reload_mcp, reload_skills, topup, insights, version` —— 都是低频命令,
被优先表挤到后面,符合设计意图。

**实测 B(两个 gate 都开,cap=60)**:core=**61 > 60**,菜单 60 条,`hidden=1`,
被丢掉的是 **`version`**;`remaining_slots = max(0, 60-61) = 0` ⇒ **技能一条也进不去**。

结论(这是本节最实质的发现):

1. **优先表 24 条 + cap 60 ⇒ 24 条运营命令永远安全**;被截掉的一定是优先表外的低频
   命令(当前是 `version`)。所以"会不会截掉重要命令"的答案是:**按现有优先表不会**,
   但代价是**技能几乎拿不到槽位**。
2. **默认配置下技能只剩 1 个槽**,与注释/文档说的"keeps every built-in plus common
   skill commands visible" **不符**。用户要在 Telegram 菜单里看到自己的技能,必须手动
   把 `max_commands` 调到 80-100,或者用 `priority` + `replace` 模式重排。
3. **打开任何一个 config gate,技能槽直接归零**,而且这是完全不可见的连锁反应
   (开 `/skills` 的网关可见性 → 挤掉一条命令 → 技能菜单全没)。

被隐藏的数量确实会报给用户,但只在 adapter 的 INFO 日志里,不是聊天里的提示。`plugins/platforms/telegram/adapter.py:3627-3631 @ 863e313`

```python
                if hidden_count:
                    logger.info(
                        "[%s] Telegram menu: %d commands registered, %d hidden (over %d limit). Use /commands for full list.",
                        self.name, len(menu_commands), hidden_count, max_commands,
                    )
```

**可疑缺陷(hidden_count 少报)**:`_collect_gateway_skill_entries` 的
`hidden_count` 只统计被裁的**技能**;当插件命令数 ≥ `max_slots` 时,末尾的
`return all_entries[:max_slots]` 会**静默裁掉插件条目而不计入 hidden_count**。而
docstring 明说 "Only skills are trimmed when the cap is reached"。`hermes_cli/commands.py:871 @ 863e313`

```python
    Only skills are trimmed when the cap is reached.
```

怎么会踩到:装了 40+ 个插件命令 + cap 收紧,日志会报 "N hidden" 但 N 少算了被丢的插件数。

### 4.6 `telegram_menu_max_commands()` 与配置读取

`hermes_cli/commands.py:729-731 @ 863e313`

```python
def telegram_menu_max_commands() -> int:
    """Return configured Telegram BotCommand menu cap with safe bounds."""
    return int(_telegram_command_menu_config()["max_commands"])
```

规范化配置的全过程(默认值 + 类型容错 + 钳制):`hermes_cli/commands.py:705-710 @ 863e313`

```python
    max_commands = menu_cfg.get("max_commands", _DEFAULT_TELEGRAM_MENU_MAX_COMMANDS)
    try:
        max_commands = int(max_commands)
    except (TypeError, ValueError):
        max_commands = _DEFAULT_TELEGRAM_MENU_MAX_COMMANDS
    max_commands = max(1, min(_TELEGRAM_BOT_API_MAX_COMMANDS, max_commands))
```

`priority_mode` 非法值回落 `prepend`:`hermes_cli/commands.py:712-714 @ 863e313`

```python
    priority_mode = str(menu_cfg.get("priority_mode") or "prepend").strip().lower()
    if priority_mode not in _TELEGRAM_PRIORITY_MODES:
        priority_mode = "prepend"
```

`priority` 非 list 回落空表:`hermes_cli/commands.py:716-720 @ 863e313`

```python
    raw_priority = menu_cfg.get("priority")
    if isinstance(raw_priority, list):
        priority = [str(item) for item in raw_priority if str(item).strip()]
    else:
        priority = []
```

路径遍历用一个防御性小工具,中途遇到非 Mapping 就返回空 dict:`hermes_cli/commands.py:680-686 @ 863e313`

```python
def _nested_mapping(root: Mapping[str, Any], *path: str) -> Mapping[str, Any]:
    node: Any = root
    for key in path:
        if not isinstance(node, Mapping):
            return {}
        node = node.get(key)
    return node if isinstance(node, Mapping) else {}
```

我实测过:`max_commands: 999` + `priority_mode: bogus` 的配置,归一化结果是
`{'max_commands': 100, 'priority_mode': 'prepend', 'priority': []}` —— 钳制与回落都生效。

**注意 `telegram_menu_commands` 的默认参数是 100 而不是 60**。`hermes_cli/commands.py:983 @ 863e313`

```python
def telegram_menu_commands(max_commands: int = 100) -> tuple[list[tuple[str, str]], int]:
```

只有走 adapter 才会拿到 60(adapter 显式调 `telegram_menu_max_commands()`)。直接调用
这个函数的其它代码(或测试)拿到的是 100 —— 默认值不一致是个小陷阱。`plugins/platforms/telegram/adapter.py:3610-3611 @ 863e313`

```python
                max_commands = telegram_menu_max_commands()
                menu_commands, hidden_count = telegram_menu_commands(max_commands=max_commands)
```

---

## 5. 必答五:`prompt_toolkit` 的 try/except ImportError 垫片

`hermes_cli/commands.py:28-39 @ 863e313`

```python
# prompt_toolkit is an optional CLI dependency — only needed for
# SlashCommandCompleter and SlashCommandAutoSuggest.  Gateway and test
# environments that lack it must still be able to import this module
# for resolve_command, gateway_help_lines, and COMMAND_REGISTRY.
try:
    from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
    from prompt_toolkit.completion import Completer, Completion
except ImportError:  # pragma: no cover
    AutoSuggest = object  # type: ignore[assignment,misc]
    Completer = object    # type: ignore[assignment,misc]
    Suggestion = None     # type: ignore[assignment]
    Completion = None     # type: ignore[assignment]
```

### 5.1 为什么必须让缺库环境也能 import

因为这个文件同时承担了**两个完全不同的职责**:

- **数据职责**(注册表、解析、各表面派生)—— 网关、Telegram/Discord/Slack adapter、
  TUI、Slack CLI 都需要,它们**不跑终端 UI**;
- **UI 职责**(`SlashCommandCompleter` / `SlashCommandAutoSuggest`)—— 只有交互式 CLI 需要。

如果没有垫片,`class SlashCommandCompleter(Completer)` 这一行会在**模块级**抛
`ImportError`,于是**整个网关起不来**。网关对本模块的依赖是硬依赖,例如:`gateway/run.py:14962-14966 @ 863e313`

```python
        from hermes_cli.commands import (
            GATEWAY_KNOWN_COMMANDS,
            is_gateway_known_command,
            resolve_command as _resolve_cmd,
        )
```

`gateway/platforms/base.py:5605-5608 @ 863e313`

```python
            from hermes_cli.commands import (
                is_interrupt_then_dispatch,
                should_bypass_active_session,
            )
```

其它硬依赖点:`gateway/run.py:877`(`_sanitize_telegram_name`)、
`plugins/platforms/telegram/adapter.py:3602`、`plugins/platforms/discord/adapter.py:5641`、
`hermes_cli/slack_cli.py:53`、`tui_gateway/methods_tools.py:260`。

### 5.2 垫片为什么"能工作"

- `Completer = object` / `AutoSuggest = object` ⇒ 两个类退化成 `object` 的子类,
  **类定义能成功执行**,模块导入成功。`hermes_cli/commands.py:1426 @ 863e313`

```python
class SlashCommandCompleter(Completer):
```

`hermes_cli/commands.py:2172 @ 863e313`

```python
class SlashCommandAutoSuggest(AutoSuggest):
```

- `Suggestion = None` / `Completion = None` ⇒ 只有**调用**这两个补全类的生成器方法时才会
  炸(`TypeError: 'NoneType' object is not callable`)。网关从不调用它们,所以永远不炸。
- `from __future__ import annotations` 让 `history_suggest: AutoSuggest | None = None`
  这样的注解变成字符串、不在运行期求值,否则 `object | None` 在旧 Python 上也会有麻烦。`hermes_cli/commands.py:11 @ 863e313`

```python
from __future__ import annotations
```

我实测确认:在没有 prompt_toolkit 的解释器里
`from hermes_cli import commands` 成功,`C.Completion is None` 为真,
`len(C.COMMAND_REGISTRY) == 94`、`telegram_bot_commands()`、`slack_native_slashes()`
全部正常返回。

### 5.3 取舍 + 与 pyproject 的出入

**取舍**:垫片把"缺库"从 import 期错误推迟成调用期错误,代价是错误信息变差
(`'NoneType' object is not callable` 而不是 `No module named prompt_toolkit`)。
对本项目是划算的,因为唯一会调用它的进程(交互式 CLI)必然装了库。

**文档-代码出入**:注释说 "prompt_toolkit is an **optional** CLI dependency",但
`pyproject.toml` 把它列在**核心 dependencies**(不是 optional-dependencies)里。`pyproject.toml:56-57 @ 863e313`

```toml
  # Interactive CLI (prompt_toolkit is used directly by cli.py)
  "prompt_toolkit==3.0.52",
```

即按官方安装方式一定装得到,"optional" 说法不准确。垫片的**实际**价值是给
(a) 裁剪过的 slim Docker 镜像 (b) 只装子集的测试环境 兜底。判定:以代码为准 —— 它是
核心依赖,注释里的 "optional" 应读作 "optional **for this module's data path**"。

---

## 6. 必答六:这一段里的每一个配置键与环境变量

### 6.1 直接读的配置键

| 键 | 默认值 | 读取点(commands.py) | 读取函数 | 备注 |
|---|---|---|---|---|
| `display.tool_progress_command` | `False`(`hermes_cli/config_defaults.py:1200`) | 声明 `:218`,遍历 `:517`,判真 `:523` | `_resolve_config_gates()` | `/verbose` 的网关可见性门;handler 侧二次判定在 `gateway/slash_commands.py:3816` / `gateway/run.py:3746` |
| `skills.write_approval` | `False`(`hermes_cli/config_defaults.py:1829`) | 声明 `:258`,遍历 `:517`,判真 `:523` | `_resolve_config_gates()` | `/skills` 的网关可见性门;本职是技能写入审批开关,被借用 |
| `platforms.telegram.extra.command_menu.max_commands` | `60`(`_DEFAULT_TELEGRAM_MENU_MAX_COMMANDS`,`:638`) | `:705` | `_telegram_command_menu_config()` | 非 int 回落 60;钳制到 `1..100`(`:710`) |
| `platforms.telegram.extra.command_menu.priority_mode` | `"prepend"` | `:712` | 同上 | 合法值 `{prepend, append, replace}`(`:640`);非法回落 prepend |
| `platforms.telegram.extra.command_menu.priority` | `[]` | `:716` | 同上 | 非 list 回落 `[]`;元素经 `_sanitize_telegram_name` 去重 |
| `mcp_servers` | `-`(缺失当 `{}`) | `:1965` | `SlashCommandCompleter._tools_completions()` | 走 `load_config()`(合并默认值),不是 raw |
| `agent.personalities` | `{}` | `:2028` | `SlashCommandCompleter._personality_completions()` | 走 `cli.load_cli_config()`,**不是** `hermes_cli.config.load_config()` |

`mcp_servers` 读取点:`hermes_cli/commands.py:1965 @ 863e313`

```python
            mcp_servers = config.get("mcp_servers") or {}
```

`agent.personalities` 读取点,注释里写明了为什么不能用 `load_config()`:`hermes_cli/commands.py:2022-2028 @ 863e313`

```python
            # Resolve from the same source the runtime applies personalities —
            # agent.personalities via the CLI config (which ships the built-ins).
            # load_config()'s schema has no agent.personalities, so the completer
            # used to come back empty even with personalities available.
            from cli import load_cli_config

            personalities = (load_cli_config().get("agent") or {}).get("personalities", {}) or {}
```

### 6.2 间接读的配置键(commands.py 调别人,别人读配置)

| 键 | 默认值 | commands.py 调用点 | 实际读取处 |
|---|---|---|---|
| `skills.external_dirs` | `[]`(`config_defaults.py`,"skills" 块) | `:940`、`:1119` | `agent/skill_utils.py:499` `get_external_skills_dirs()` |
| `skills.disabled` | `-` | `:921`、`:1092` | `agent/skill_utils.py:464` `get_disabled_skill_names()` |
| `skills.platform_disabled.<platform>` | `-` | 同上 | `agent/skill_utils.py:465-469` |
| 网关平台配置(connected platforms / home channel) | `-` | `:1996-1999` | `gateway/config.py` `load_gateway_config()` |
| CLI 工具集启用状态 | `-` | `:1933` | `hermes_cli/tools_config.py` `_get_platform_tools()` |

`skills.external_dirs` 的调用点与它解决的问题(#8110):`hermes_cli/commands.py:938-941 @ 863e313`

```python
        _allowed_prefixes = [_skills_dir.rstrip("/") + "/"]
        _allowed_prefixes.extend(
            str(d).rstrip("/") + "/" for d in get_external_skills_dirs()
        )
```

`skills.disabled` / `platform_disabled` 的调用点(**显式传 platform**):`hermes_cli/commands.py:920-921 @ 863e313`

```python
        from agent.skill_utils import get_disabled_skill_names
        _platform_disabled = get_disabled_skill_names(platform=platform)
```

对应实现:`agent/skill_utils.py:464-470 @ 863e313`

```python
    global_disabled = _normalize_string_set(skills_cfg.get("disabled"))
    if resolved_platform:
        platform_disabled = (skills_cfg.get("platform_disabled") or {}).get(
            resolved_platform
        )
        if platform_disabled is not None:
            return global_disabled | _normalize_string_set(platform_disabled)
    return global_disabled
```

### 6.3 环境变量

**commands.py 自身不读任何环境变量。** 我 grep 过 `getenv` / `environ`:文件里只有两处
"environment" 是英文注释,**零个 `os.getenv` / `os.environ`**。它用的 `os` 全是路径/
文件操作(`os.path.expanduser`、`os.listdir`、`os.getcwd`、`os.path.getsize`)。

间接生效的环境变量:

| 环境变量 | 默认 | 生效路径 | 语义 |
|---|---|---|---|
| `HERMES_HOME` | 平台默认(POSIX `~/.hermes`;Win `%LOCALAPPDATA%/hermes`) | `_resolve_config_gates()`/`_telegram_command_menu_config()` → `read_raw_config()` → `get_config_path()` → `get_hermes_home()` | 决定读哪个 `config.yaml`,即门控与菜单配置来自哪个 profile |
| `LOCALAPPDATA` | `~/AppData/Local` | 同上(仅 win32) | Windows 默认 home 的基址 |
| `HERMES_PLATFORM` / `HERMES_SESSION_PLATFORM` | 无 | `get_disabled_skill_names()` 的 platform 回落 | **本文件不触发**:commands.py 两处都显式传 `platform=`,所以这条 fallback 链在这里是死的 |

`HERMES_HOME` 的 fallback 链(context-local override → 环境变量 → 平台默认):`hermes_constants.py:132-139 @ 863e313`

```python
    override = get_hermes_home_override()
    if override:
        return Path(override)

    if not os.environ.get("HERMES_HOME", "").strip():
        _warn_profile_fallback_once()

    return _hermes_home_from_env()
```

`hermes_constants.py:71-74 @ 863e313`

```python
    val = os.environ.get("HERMES_HOME", "").strip()
    if val:
        return Path(val)
    return _get_platform_default_hermes_home()
```

测试里正是通过 `monkeypatch.setenv("HERMES_HOME", ...)` 来切换 gate 状态的,印证这条链:`tests/hermes_cli/test_commands.py:283-289 @ 863e313`

```python
        config_file = tmp_path / "config.yaml"
        config_file.write_text("display:\n  tool_progress_command: false\n")
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        lines = gateway_help_lines()
        joined = "\n".join(lines)
        assert "`/verbose" not in joined
```

另有两个"文本里提到但本文件不读"的环境变量,记录以免误判:`/prompt` 的描述里写了
`$EDITOR`(实际读取在别处的 handler),`SKILL.md` 模板变量 `${HERMES_SKILL_DIR}` /
`${HERMES_SESSION_ID}` 在 `config_defaults.py` 的注释里。

---

## 7. 其余机制(逐个:解决什么 / 怎么实现 / 为什么 / 取舍)

### 7.1 名字→定义 的解析:`_COMMAND_LOOKUP` + `resolve_command`

**解决**:用户可能敲 `/BG`、`/bg`、`bg`,都要落到同一个 `CommandDef`。

`hermes_cli/commands.py:349-356 @ 863e313`

```python
def _build_command_lookup() -> dict[str, CommandDef]:
    """Map every name and alias to its CommandDef."""
    lookup: dict[str, CommandDef] = {}
    for cmd in COMMAND_REGISTRY:
        lookup[cmd.name] = cmd
        for alias in cmd.aliases:
            lookup[alias] = cmd
    return lookup
```

`hermes_cli/commands.py:359 @ 863e313`

```python
_COMMAND_LOOKUP: dict[str, CommandDef] = _build_command_lookup()
```

`hermes_cli/commands.py:362-367 @ 863e313`

```python
def resolve_command(name: str) -> CommandDef | None:
    """Resolve a command name or alias to its CommandDef.

    Accepts names with or without the leading slash.
    """
    return _COMMAND_LOOKUP.get(name.lower().lstrip("/"))
```

**取舍**:`lstrip("/")` 会剥掉**多个**前导斜杠(`//help` 也能解析),且不做下划线↔连字符
归一(网关在 `gateway/run.py:15615` 处**另外**手动做了 `replace("_","-")`,说明这里
的不归一确实带来了下游补丁)。别名撞名靠**测试**约束,不靠代码。`tests/hermes_cli/test_commands.py:54-56 @ 863e313`

```python
    def test_no_alias_collides_with_canonical_name(self):
        """An alias must not shadow another command's canonical name."""
        canonical_names = {cmd.name for cmd in COMMAND_REGISTRY}
```

**注意导入期构建**:`_COMMAND_LOOKUP` / `COMMANDS` / `COMMANDS_BY_CATEGORY` /
`SUBCOMMANDS` / `GATEWAY_KNOWN_COMMANDS` / `ACTIVE_SESSION_BYPASS_COMMANDS` 全部在
**模块导入时**一次算好。这是"注册表是静态的"这一前提的直接体现 —— 插件命令**不进**
这些结构,而是每次现查(§7.3)。

**文档-代码出入**:分节注释说这些派生结构"refreshed by `rebuild_lookups()`",但
**全仓不存在名为 `rebuild_lookups` 的函数**(grep 全仓只命中这一行注释本身)。`hermes_cli/commands.py:345-347 @ 863e313`

```python
# ---------------------------------------------------------------------------
# Derived lookups -- rebuilt once at import time, refreshed by rebuild_lookups()
# ---------------------------------------------------------------------------
```

### 7.2 三个"网关行为集合"

**`ACTIVE_SESSION_BYPASS_COMMANDS`** —— 历史名字,现在是派生量。`hermes_cli/commands.py:450-458 @ 863e313`

```python
# Commands with explicit mid-run (running-agent) behavior in gateway/run.py.
# DERIVED from the registry: every command whose ``busy_policy`` is not
# "reject" either dispatches while the agent is busy or interrupts it first.
# Kept under its historical public name for introspection / tests;
# semantically a subset of "all resolvable commands" — which is the real
# bypass set (see should_bypass_active_session below).
ACTIVE_SESSION_BYPASS_COMMANDS: frozenset[str] = frozenset(
    cmd.name for cmd in COMMAND_REGISTRY if cmd.busy_policy != "reject"
)
```

**`is_interrupt_then_dispatch()`** —— Guard 1 用它决定要不要走"取消交接"路径。`hermes_cli/commands.py:461-473 @ 863e313`

```python
def is_interrupt_then_dispatch(command_name: str | None) -> bool:
    """Return True when *command_name* must interrupt a running agent first.

    Derived from the registry: commands whose ``busy_policy`` is
    "interrupt_then_dispatch" (the /stop, /new, /reset class).  Guard 1
    (gateway/platforms/base.py) routes these through the cancel-handoff
    path that serializes cancellation + runner response + pending drain.
    Accepts aliases (e.g. "reset" resolves to "new").
    """
    if not command_name:
        return False
    cmd = resolve_command(command_name)
    return cmd is not None and cmd.busy_policy == "interrupt_then_dispatch"
```

**`should_bypass_active_session()`** —— **任何能解析的斜杠命令都 bypass**,理由是一段
事故史。`hermes_cli/commands.py:476-496 @ 863e313`

```python
def should_bypass_active_session(command_name: str | None) -> bool:
    """Return True for any resolvable slash command.

    Rationale: every gateway-registered slash command either has a
    specific Level-2 handler in gateway/run.py (/stop, /new, /model,
    /approve, etc.) or reaches the running-agent catch-all that returns
    a "busy — wait or /stop first" response. In both paths the command
    is dispatched, not queued.

    Queueing is always wrong for a recognized slash command because the
    safety net in gateway.run discards any command text that reaches
    the pending queue — which meant a mid-run /model (or /reasoning,
    /voice, /insights, /title, /resume, /retry, /undo, /compress,
    /usage, /reload-mcp, /sethome, /reset) would silently
    interrupt the agent AND get discarded, producing a zero-char
    response. See issue #5057 / PRs #6252, #10370, #4665.

    ACTIVE_SESSION_BYPASS_COMMANDS remains the subset of commands with
    explicit Level-2 handlers; the rest fall through to the catch-all.
    """
    return resolve_command(command_name) is not None if command_name else False
```

**事故因果链(可复述版)**:agent 正在跑 → 用户敲 `/model xxx` → 老逻辑认为它不在
bypass 集里,于是把它当普通消息塞进 pending 队列 → 但塞队列这个动作本身打断了 agent →
队列的安全网又发现队里是一条命令文本、直接丢弃 → 用户看到一个 **0 字符的回复**,agent
也被白白打断。修法:把 bypass 集从"手写清单"改成"能解析就 bypass",让每条命令要么有
专用 mid-run handler、要么拿到明确的"忙,请等或 /stop"文案。

**取舍**:`ACTIVE_SESSION_BYPASS_COMMANDS` 现在是个**只给测试和 introspection 用的
历史名**,真正的判据是 `should_bypass_active_session`。两个名字并存容易读错,但测试
把它钉成派生量:`tests/hermes_cli/test_busy_policy_invariants.py:47-51 @ 863e313`

```python
def test_bypass_set_is_derived_from_registry():
    expected = frozenset(
        cmd.name for cmd in COMMAND_REGISTRY if cmd.busy_policy != "reject"
    )
    assert ACTIVE_SESSION_BYPASS_COMMANDS == expected
```

### 7.3 插件命令:懒查,永不进静态表

`hermes_cli/commands.py:430-447 @ 863e313`

```python
def is_gateway_known_command(name: str | None) -> bool:
    """Return True if ``name`` resolves to a gateway-dispatchable slash command.

    This covers both built-in commands (``GATEWAY_KNOWN_COMMANDS`` derived
    from ``COMMAND_REGISTRY``) and plugin-registered commands, which are
    looked up lazily so importing this module never forces plugin
    discovery. Gateway code uses this to decide whether to emit
    ``command:<name>`` hooks — plugin commands get the same lifecycle
    events as built-ins.
    """
    if not name:
        return False
    if name in GATEWAY_KNOWN_COMMANDS:
        return True
    for plugin_name, _description, _args_hint in _iter_plugin_command_entries():
        if plugin_name == name:
            return True
    return False
```

`hermes_cli/commands.py:568-581 @ 863e313`

```python
def _iter_plugin_command_entries() -> list[tuple[str, str, str]]:
    """Yield (name, description, args_hint) tuples for all plugin slash commands.

    Plugin commands are registered via
    :func:`hermes_cli.plugins.PluginContext.register_command`. They behave
    like ``CommandDef`` entries for gateway surfacing: they appear in the
    Telegram command menu, in Slack's ``/hermes`` subcommand mapping, and
    (via :func:`plugins.platforms.discord.adapter._register_slash_commands`) in
    Discord's native slash command picker.

    Lookup is lazy so importing this module never forces plugin discovery
    (which can trigger filesystem scans and environment-dependent
    behavior).
    """
```

**双层异常吞噬** + 类型校验:`hermes_cli/commands.py:582-596 @ 863e313`

```python
    try:
        from hermes_cli.plugins import get_plugin_commands
    except Exception:
        return []
    try:
        commands = get_plugin_commands() or {}
    except Exception:
        return []
    entries: list[tuple[str, str, str]] = []
    for name, meta in commands.items():
        if not isinstance(name, str) or not isinstance(meta, dict):
            continue
        description = str(meta.get("description") or f"Run /{name}")
        args_hint = str(meta.get("args_hint") or "").strip()
        entries.append((name, description, args_hint))
```

**为什么懒查**:插件发现会扫文件系统、跑第三方 `register()`(我在实测时就看到一堆
"Failed to load plugin … No module named 'httpx'"),如果在 import 期做,任何一个坏插件
都能拖垮整个 CLI/网关的启动。

**取舍/缺陷**:(a) `is_gateway_known_command` 每次调用都可能触发一次插件枚举,是 O(n)
线性扫描而不是 set 查找;(b) 它**不做**下划线↔连字符归一(与 `gateway/run.py:15615`
的 `command.replace("_","-")` 不一致),所以 Telegram 回传的 `/my_plugin_cmd`
在插件注册名是 `my-plugin-cmd` 时匹配不上;(c) 异常全吞 ⇒ 插件系统整体故障时,插件
命令静默变成"未知命令"。

### 7.4 Slack:50 条硬帽 + 保留名 + 手工降级清单

**约束**:Slack app 每个最多 50 条 slash command,且有一批**内建 slash 不能被 app 抢占**。`hermes_cli/commands.py:1216-1228 @ 863e313`

```python
# Slack slash command name constraints: lowercase a-z, 0-9, hyphens,
# underscores. Max 32 chars. Slack app manifest accepts up to 50 slash
# commands per app.
_SLACK_MAX_SLASH_COMMANDS = 50
_SLACK_NAME_LIMIT = 32
_SLACK_INVALID_CHARS = re.compile(r"[^a-z0-9_\-]")
_SLACK_RESERVED_COMMANDS = frozenset({
    # Built-in Slack slash commands that cannot be registered by apps.
    # https://slack.com/help/articles/201259356-Use-built-in-slash-commands
    "me", "status", "away", "dnd", "shrug", "remind", "msg", "feed",
    "who", "collapse", "expand", "leave", "join", "open", "search",
    "topic", "mute", "pro", "shortcuts",
})
```

Hermes 有两条命令正好撞 Slack 保留名:**`/status` 和 `/topic`**(实测确认它们不在
native 列表里)。

**问题**:注册表 59 条网关可见命令 + 26 个别名 ≫ 50。老行为是"排到哪算哪,超了就静默丢
最后几个",于是"加一条新命令 ⇒ 某个老命令的 Slack 原生斜杠悄悄消失"。

**两个手工清单是对策**:

① 高价值别名钉死在最前(仅次于 `/hermes`)。`hermes_cli/commands.py:1230-1241 @ 863e313`

```python
# High-value aliases that must survive Slack's 50-slash cap even when the
# registry fills up. Without this, adding a new canonical command silently
# clamps off low-priority aliases (they're added in the second pass), so a
# long-standing native slash like /btw could disappear just because an
# unrelated command landed. These claim their slots right after /hermes,
# ahead of both canonical names and the rest of the aliases. Anything not
# listed here still degrades gracefully (reachable via /hermes <command>).
# Keep this list TIGHT: every pinned alias takes a slot a canonical command
# would otherwise get, and the Telegram-parity test fails when a canonical
# gets clamped ("reset" was unpinned for exactly that — /new keeps its
# native slot, the alias spelling stays reachable via /hermes reset).
_SLACK_PRIORITY_ALIASES = ("btw", "bg")
```

② 明确降级到 `/hermes <cmd>` 的 canonical 清单(注释逐条写了降级理由,是一份很好的
"容量预算决策记录"):`hermes_cli/commands.py:1275 @ 863e313`

```python
_SLACK_VIA_HERMES_ONLY = frozenset({"topup", "moa", "debug", "egress", "init", "version", "diff", "update", "heartbeat", "refine"})
```

**三趟填充**(canonical 先于 alias,alias 先于 plugin,`/hermes` 永远第一):`hermes_cli/commands.py:1315-1332 @ 863e313`

```python
    # Reserve /hermes as the catch-all top-level command.
    entries.append(("hermes", "Talk to Hermes or run a subcommand", "[subcommand] [args]"))
    seen.add("hermes")

    def _add(name: str, desc: str, hint: str) -> None:
        slack_name = _sanitize_slack_name(name)
        if not slack_name or slack_name in seen:
            return
        if slack_name in _SLACK_RESERVED_COMMANDS:
            return
        if slack_name in _SLACK_VIA_HERMES_ONLY:
            # Intentionally Slack-via-/hermes only (see _SLACK_VIA_HERMES_ONLY).
            return
        if len(entries) >= _SLACK_MAX_SLASH_COMMANDS:
            return
        # Slack description cap is 2000 chars; keep it short.
        entries.append((slack_name, desc[:140], hint[:100]))
        seen.add(slack_name)
```

**实测(重要)**:`len(slack_native_slashes()) == 50` —— **正好顶满**。分解:

- `hermes` + `btw` + `bg` = 3
- canonical 第一趟填到 50 就停;
- **第二趟(别名)与第三趟(插件)实际一条都进不去**:`reset, fork, compact, tasks, q,
  hb, ctx, set-home, codex_runtime, suggest, bp, reload_mcp, reload_skills, v` 全部落榜。
- 未上榜的 canonical 共 12 条 = 2 条 Slack 保留名(`status`,`topic`)+ 10 条
  `_SLACK_VIA_HERMES_ONLY`,**静默被 clamp 的为 0**。

也就是说,这两份手工清单**当前恰好把系统调到容量边缘的临界点**。再加**任何**一条网关
可见的新命令,就会有一条 canonical 被静默丢弃 —— 唯一的报警是 Telegram-parity 测试。`tests/hermes_cli/test_commands.py:240-243 @ 863e313`

```python
        missing = (tg_norm - slack_norm) - reserved_norm - via_hermes_norm
        assert not missing, (
            f"commands on Telegram but missing from Slack native slashes: {sorted(missing)}"
        )
```

**取舍**:用"测试当护栏 + 人工维护降级清单"替代"自动优先级算法"。好处是每次降级都是
一个有记录的人类决策(注释里逐条写了为什么);坏处是维护成本高,而且降级理由散落在
注释里、用户看不到("为什么 Slack 上没有 /version?")。

`slack_app_manifest()` 只产出 manifest 的 `features.slash_commands` 片段,刻意不耦合
其余 schema。`hermes_cli/commands.py:1371-1382 @ 863e313`

```python
def slack_app_manifest(request_url: str = "https://hermes-agent.local/slack/commands") -> dict[str, Any]:
    """Generate a Slack app manifest with all gateway commands as slashes.

    ``request_url`` is required by Slack's manifest schema for every slash
    command, but in Socket Mode (which we use) Slack ignores it and routes
    the command event through the WebSocket. A placeholder URL is fine.

    The returned dict is the ``features.slash_commands`` portion only —
    callers compose it into a full manifest (or merge into an existing
    one). Keeping it narrow avoids coupling us to the rest of the manifest
    schema (display_information, oauth_config, settings, etc.) which users
    set up once in the Slack UI and rarely change.
    """
```

`slack_subcommand_map()` 是 `/hermes <verb>` 的兜底路由,canonical 和 alias 都进(实测 75 条),
所以被 clamp 掉的命令仍然可达。`hermes_cli/commands.py:1409-1414 @ 863e313`

```python
    for cmd in COMMAND_REGISTRY:
        if not _is_gateway_available(cmd, overrides):
            continue
        mapping[cmd.name] = f"/{cmd.name}"
        for alias in cmd.aliases:
            mapping[alias] = f"/{alias}"
```

### 7.5 32 字符钳制:`_clamp_command_names`

Telegram 和 Discord 都限命令名 32 字符。`hermes_cli/commands.py:785-789 @ 863e313`

```python
_CMD_NAME_LIMIT = 32
"""Max command name length shared by Telegram and Discord."""

# Backward-compat alias — tests and external code may reference the old name.
_TG_NAME_LIMIT = _CMD_NAME_LIMIT
```

`hermes_cli/commands.py:811-826 @ 863e313`

```python
def _clamp_command_names(
    entries: list[tuple[str, ...]],
    reserved: set[str],
) -> list[tuple[str, ...]]:
    """Enforce 32-char command name limit with collision avoidance.

    Both Telegram and Discord cap slash command names at 32 characters.
    Names exceeding the limit are truncated.  If truncation creates a duplicate
    (against *reserved* names or earlier entries in the same batch), the name is
    shortened to 31 chars and a digit ``0``-``9`` is appended to differentiate.
    If all 10 digit slots are taken the entry is silently dropped.

    Accepts tuples of any length >= 2.  Extra elements beyond ``(name, desc)``
    (e.g. ``cmd_key``) are passed through unchanged, so callers can attach
    metadata that survives the rename.
    """
```

`hermes_cli/commands.py:829-847 @ 863e313`

```python
    for entry in entries:
        name, desc, *extra = entry
        if len(name) > _CMD_NAME_LIMIT:
            candidate = name[:_CMD_NAME_LIMIT]
            if candidate in used:
                prefix = name[:_CMD_NAME_LIMIT - 1]
                for digit in range(10):
                    candidate = f"{prefix}{digit}"
                    if candidate not in used:
                        break
                else:
                    # All 10 digit slots exhausted — skip entry
                    continue
            name = candidate
        if name in used:
            continue
        used.add(name)
        result.append((name, desc, *extra))
```

`for...else + continue` 的用法正确(`else` 只在没 break 时执行,`continue` 跳过外层这一条)。

**文档-代码小出入**:docstring 只说了"10 个数字位用光才静默丢弃",没说
**长度合法但重名的条目也会被静默丢弃**(`:843-844` 的 `if name in used: continue`,
不补数字)。

`*extra` 透传设计是为了让 `cmd_key`(`/skill-name` 原键)在改名后仍然跟着走,否则
Discord 的 handler 回调找不到对应技能。测试 `TestClampCommandNamesTriples` /
`TestDiscordSkillCmdKeyDispatch` 盯这条。

### 7.6 Discord `/skill` 分类:把静默丢弃改成可诊断的 WARNING

`discord_skill_commands_by_category()` 里,两个技能的前 32 字符相同时不再静默丢,而是
打一条指名道姓的 warning。`hermes_cli/commands.py:1158-1170 @ 863e313`

```python
            if discord_name in _names_used:
                # Two skills whose first 32 chars are identical. One wins
                # (the first one seen, which is alphabetical because the
                # caller iterates ``sorted(skill_cmds)``); the other is
                # dropped from Discord's /skill autocomplete.
                #
                # Silently counting this as ``hidden`` (the old behavior)
                # meant skill authors had no way to discover the drop —
                # their skill just didn't appear in the picker. Emit a
                # WARNING naming both sides so the author can rename the
                # losing skill's frontmatter name to something with a
                # distinct 32-char prefix.
                prior = _names_used[discord_name]
```

用哨兵值区分"撞保留命令名"和"两个技能互撞":`hermes_cli/commands.py:1104 @ 863e313`

```python
    _names_used: dict[str, str] = dict.fromkeys(reserved_names, "<reserved>")
```

**这是本文件里"静默失败 → 可诊断"的最佳实践样板**:同一个丢弃动作,给出"谁赢了、谁输了、
改哪个字段"三条可操作信息。对比之下,同文件里 `_clamp_command_names`、
`telegram_bot_commands` 的空名跳过、`_collect_gateway_skill_entries` 的插件裁剪都还是静默的。

**注释里记录的一次架构简化**:老的 25 组 × 25 子命令上限已经不适用,因为
Discord adapter 改成"单个 autocomplete 回调"了。`hermes_cli/commands.py:1070-1077 @ 863e313`

```python
    The legacy 25-group × 25-subcommand caps (from the old nested
    ``/skill <cat> <name>`` layout) are **not** applied — the live caller
    (``_register_skill_group`` in ``gateway/platforms/discord.py``, refactored
    in PR #11580) flattens these results and feeds them into a single
    autocomplete callback, which scales to thousands of entries without any
    per-command payload concerns. ``hidden_count`` is retained in the return
    tuple for backward compatibility and still reports skills dropped for
    other reasons (32-char clamp collision vs a reserved name).
```

**文档-代码出入(轻)**:这段说 caller 在 `gateway/platforms/discord.py`,但实际的
Discord adapter 在 `plugins/platforms/discord/adapter.py`(`_register_slash_commands` /
`_register_skill_group` 都在那里)。同文件 `:575` 处倒是写对了
(`plugins.platforms.discord.adapter._register_slash_commands`)。

### 7.7 补全器 `SlashCommandCompleter`(prompt_toolkit 侧)

顶层分派逻辑:非 `/` 开头 → 试 `@` 上下文引用 → 试路径补全;`/` 开头 → 分"还在打命令名"
和"已在打参数"两态。`hermes_cli/commands.py:2051-2063 @ 863e313`

```python
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            # Try @ context completion (Claude Code-style)
            ctx_word = self._extract_context_word(text)
            if ctx_word is not None:
                yield from self._context_completions(ctx_word)
                return
            # Try file path completion for non-slash input
            path_word = self._extract_path_word(text)
            if path_word is not None:
                yield from self._path_completions(path_word)
            return
```

参数态的优先级链:**堆叠技能链 > /skin,/personality 动态列表 > /tools > /handoff >
静态 SUBCOMMANDS**。`hermes_cli/commands.py:2077-2099 @ 863e313`

```python
            if self._is_skill_command(base_cmd):
                yield from self._stacked_skill_completions(text)
                return

            # Dynamic completions for commands with runtime lists
            if " " not in sub_text:
                if base_cmd == "/skin":
                    yield from self._skin_completions(sub_text, sub_lower)
                    return
                if base_cmd == "/personality":
                    yield from self._personality_completions(sub_text, sub_lower)
                    return

            # /tools needs multi-word completion (subcommand + toolset name)
            # so it handles both stages itself, bypassing the single-word
            # SUBCOMMANDS branch below.
            if base_cmd == "/tools":
                yield from self._tools_completions(sub_text, sub_lower)
                return

            if base_cmd == "/handoff":
                yield from self._handoff_completions(sub_text, sub_lower)
                return
```

命令名态的四段来源:内置 `COMMANDS` → 技能 bundle → 技能命令 → 插件命令,各有
不同的 display_meta 图标(`▣` bundle / `⚡` skill / `🔌` plugin)。`hermes_cli/commands.py:2114-2118 @ 863e313`

```python
        for cmd, desc in COMMANDS.items():
            if not self._command_allowed(cmd):
                continue
            cmd_name = cmd[1:]
            if cmd_name.startswith(word):
```

几个值得记的小机制:

**① 尾随空格与 picker 命令的冲突**。`hermes_cli/commands.py:1538-1542 @ 863e313`

```python
    # Commands that open pickers when run without arguments.
    # These should NOT receive a trailing space in completions because:
    # - The TUI's submit handler applies completions on Enter if input differs
    # - Adding space makes "/model" → "/model " which blocks picker execution
    _PICKER_COMMANDS = frozenset({"model", "skin", "personality"})
```

`hermes_cli/commands.py:1557-1562 @ 863e313`

```python
        if cmd_name != word:
            return cmd_name
        # Don't add space for picker commands — allows Enter to execute them
        if cmd_name in SlashCommandCompleter._PICKER_COMMANDS:
            return cmd_name
        return f"{cmd_name} "
```

因果:精确打完 `/help` 时补全返回同样的字符串是 no-op,prompt_toolkit 会把菜单收起来;
补一个尾随空格能让菜单留着。但 `/model` 这类"无参就开选择器"的命令,多出来的空格
会让 TUI 的 Enter 处理器把它当"已有参数",选择器就打不开了。

**② URL 不当路径补全**(每敲一个字符 `os.listdir("https:")` 是纯延迟)。`hermes_cli/commands.py:1587-1592 @ 863e313`

```python
        # URLs contain "/" but are not local paths. Treating them as paths fires
        # os.listdir on every keystroke while typing/pasting a link (e.g. an
        # https:// URL becomes a listdir of "https:") — pure latency, never a
        # useful completion. Skip any token with a scheme separator.
        if "://" in word:
            return None
```

**③ `@folder:` 只列目录、`@file:` 只列文件**。`hermes_cli/commands.py:1723-1729 @ 863e313`

```python
                    # `@folder:` must only surface directories; `@file:` only
                    # regular files.  Without this filter `@folder:` listed
                    # every .env / .gitignore in the cwd, defeating the
                    # explicit prefix and confusing users expecting a
                    # directory picker.
                    if want_dir != is_dir:
                        continue
```

**④ 项目文件列表:rg → fd 降级链,2 秒超时,5 秒缓存,最多 5000 条。**`hermes_cli/commands.py:1760-1774 @ 863e313`

```python
        files: list[str] = []
        # Try rg first (fast, respects .gitignore), then fd, then find.
        for cmd in [
            ["rg", "--files", "--sortr=modified", cwd],
            ["rg", "--files", cwd],
            ["fd", "--type", "f", "--base-directory", cwd],
        ]:
            tool = cmd[0]
            if not shutil.which(tool):
                continue
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=2,
                    cwd=cwd, encoding="utf-8", errors="replace",
                )
```

**可疑缺陷(注释与代码不符)**:注释说 "then fd, **then find**",但候选列表里**没有
`find`**,只有两个 rg 变体和一个 fd。既没 rg 也没 fd 的机器上 `@` 模糊补全直接空表
(而且空表会被缓存 5 秒,每 5 秒重试一次 `shutil.which`)。

**⑤ 模糊评分是手写的分档打分,不是编辑距离。** `hermes_cli/commands.py:1801-1812 @ 863e313`

```python
        # Exact filename match
        if lower_file == lower_q:
            return 100
        # Filename starts with query
        if lower_file.startswith(lower_q):
            return 80
        # Filename contains query as substring
        if lower_q in lower_file:
            return 60
        # Full path contains query
        if lower_q in lower_path:
            return 40
```

首字母缩写匹配额外给 35/25 分,判据是"匹配点落在 `_-./` 边界后的比例 ≥ 0.5"。`hermes_cli/commands.py:1830-1832 @ 863e313`

```python
            if boundary_hits >= len(lower_q) * 0.5:
                return 35
            return 25
```

**⑥ `/tools` 的补全按当前启用状态过滤**(enable 只提示没开的,disable 只提示开着的),
并把 MCP server 以 `server:` 前缀形式提供。`hermes_cli/commands.py:1936-1942 @ 863e313`

```python
                if ts_key in already or not ts_key.startswith(partial_lower):
                    continue
                is_on = ts_key in enabled
                if subcommand == "enable" and is_on:
                    continue
                if subcommand == "disable" and not is_on:
                    continue
                yield Completion(
```

**⑦ 堆叠技能补全**:`/skill-a /skill-b 指令文本` —— 只要"每个已完成 token 都是不重复的
技能命令"且"当前词以 `/` 开头"就继续提示,链一断就不提示(避免污染指令正文)。`hermes_cli/commands.py:1505-1519 @ 863e313`

```python
        # The chain must be unbroken: every completed token is a distinct
        # skill command, and there's room left under the cap.
        seen: set[str] = set()
        for token in completed:
            key = self._normalize_skill_token(token)
            if key not in self._iter_skill_commands() or key in seen:
                return
            seen.add(key)
        if len(seen) >= _cap:
            return

        # Only suggest while the user is typing another /token — a bare
        # space after the chain means they may be starting the instruction.
        if not current_word.startswith("/"):
            return
```

上限从 `agent/skill_commands` 导入,失败回落 5(与那边的真实值一致)。`hermes_cli/commands.py:1494-1498 @ 863e313`

```python
        try:
            from agent.skill_commands import _MAX_STACKED_SKILLS as _cap
        except Exception:
            _cap = 5
```

`agent/skill_commands.py:630 @ 863e313`

```python
_MAX_STACKED_SKILLS = 5
```

**⑧ 下划线↔连字符归一**在技能 token 这里做了(与 §7.1 的 `resolve_command` 不做形成对比):`hermes_cli/commands.py:1469-1477 @ 863e313`

```python
    @staticmethod
    def _normalize_skill_token(token: str) -> str:
        """Canonicalize a typed skill token to its hyphenated /slug form.

        Mirrors resolve_skill_command_key() in agent/skill_commands.py:
        underscores (Telegram bot-command form) are interchangeable with
        hyphens.
        """
        return "/" + token.lstrip("/").replace("_", "-").lower()
```

**⑨ 所有 provider 回调都吞异常**(`_command_allowed` 异常时**放行**,即 fail-open):`hermes_cli/commands.py:1443-1449 @ 863e313`

```python
    def _command_allowed(self, slash_command: str) -> bool:
        if self._command_filter is None:
            return True
        try:
            return bool(self._command_filter(slash_command))
        except Exception:
            return True
```

**可疑缺陷(安全相关,低危)**:`_command_filter` 是权限过滤器(非 admin 用户看不到某些
命令),异常时 fail-open 会把本该隐藏的命令显示出来。这只是**补全展示**层,不是执行
授权层,所以影响是信息泄露级别(暴露命令名)而非提权。

### 7.8 幽灵文本 `SlashCommandAutoSuggest`

`hermes_cli/commands.py:2200-2213 @ 863e313`

```python
        if len(parts) == 1 and not text.endswith(" "):
            # Still typing the command name: /upd → suggest "ate"
            # Prefer the SHORTEST matching command so a short, high-frequency
            # command keeps its ghost text when a longer command shares its
            # prefix (e.g. /he → "lp" for /help, not "artbeat" for
            # /heartbeat; type one more letter to steer).
            word = text[1:].lower()
            for cmd in sorted(COMMANDS, key=len):
                if self._completer is not None and not self._completer._command_allowed(cmd):
                    continue
                cmd_name = cmd[1:]  # strip leading /
                if cmd_name.startswith(word) and cmd_name != word:
                    return Suggestion(cmd_name[len(word):])
            return None
```

**为什么按长度排序**:前缀相同时短命令更常用(`/he` → `/help` 而不是 `/heartbeat`)。
`sorted(COMMANDS, key=len)` 对等长的按字典序(Python sort 稳定 + dict 保序),
所以结果确定。

**可疑缺陷(轻)**:`sorted(COMMANDS, key=len)` 比较的是**带斜杠的键**长度,与
`cmd_name` 长度差一个常数,不影响相对次序;但它会把**别名**也纳入候选,于是
`/b` 的最短匹配是 `/bg`(别名)而不是 `/background` —— 这大概是想要的,只是没写在注释里。

### 7.9 `_file_size_label`

`hermes_cli/commands.py:2248-2253 @ 863e313`

```python
def _file_size_label(path: str) -> str:
    """Return a compact human-readable file size, or '' on error."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return ""
```

小工具,补全 meta 列用。放在文件最末尾但被上面的方法引用(Python 运行期解析名字,没问题)。

---

## 8. 消费侧地图(定义侧 → 谁在用)

| 消费者 | 用了什么 | 位置 |
|---|---|---|
| 网关文本 dispatch | `resolve_command`、`GATEWAY_KNOWN_COMMANDS`、`is_gateway_known_command` | `gateway/run.py:14962`、`:15001`、`:15013`、`:15615` |
| 网关 Guard 1(取消交接) | `should_bypass_active_session`、`is_interrupt_then_dispatch` | `gateway/platforms/base.py:5605` |
| 网关 Guard 2(mid-run) | `cmd_def.busy_policy` / `busy_handler` | `gateway/run.py:14098` |
| Telegram adapter | `telegram_menu_commands`、`telegram_menu_max_commands` | `plugins/platforms/telegram/adapter.py:3602`、`:8764` |
| Discord adapter | `COMMAND_REGISTRY`、`_is_gateway_available`、`_resolve_config_gates`、`discord_skill_commands*` | `plugins/platforms/discord/adapter.py:5641` |
| Slack adapter | `is_gateway_known_command` | `plugins/platforms/slack/adapter.py:377` |
| Matrix adapter | `is_gateway_known_command` | `plugins/platforms/matrix/adapter.py:310` |
| `hermes slack manifest` CLI | `slack_app_manifest` | `hermes_cli/slack_cli.py:53`、`:242` |
| TUI 命令目录 | `COMMAND_REGISTRY`、`SUBCOMMANDS`、`_build_description`、`gateway_only` | `tui_gateway/methods_tools.py:260-272` |
| 共享执行器 | `CommandDef.execute` | `hermes_cli/slash_exec.py:244` |

Discord 是唯一一个**直接遍历 `COMMAND_REGISTRY` + `_is_gateway_available`** 的 adapter
(其它走封装函数),并有自己的 100 条上限。`plugins/platforms/discord/adapter.py:5650-5658 @ 863e313`

```python
            for cmd_def in COMMAND_REGISTRY:
                if not _is_gateway_available(cmd_def, config_overrides):
                    continue
                # Discord command names: lowercase, hyphens OK, max 32 chars.
                discord_name = cmd_def.name.lower()[:32]
                if discord_name in already_registered:
                    continue
                if len(already_registered) >= slot_cap:
                    dropped_over_cap += 1
                    continue
```

---

## 9. 文档与代码的出入(本段汇总)

| # | 说法出处 | 说的 | 代码实际 |
|---|---|---|---|
| D1 | `hermes_cli/commands.py:346` | 派生表 "refreshed by `rebuild_lookups()`" | 全仓不存在 `rebuild_lookups`;派生表只在 import 期构建一次,无刷新入口 |
| D2 | `hermes_cli/commands.py:28` | "prompt_toolkit is an **optional** CLI dependency" | `pyproject.toml:57` 把它列在核心 dependencies,不是 optional-dependencies |
| D3 | `hermes_cli/commands.py:634-636` | "Hermes ships **~50** built-in commands;60-slot default keeps **every built-in plus common skill commands** visible" | 实测网关可见内置 **59** 条;默认 cap 60 下技能只剩 **1** 个槽;两个 config gate 全开时 core=61>60,技能槽为 **0** 且 `/version` 被丢 |
| D4 | `website/docs/user-guide/messaging/telegram.md:84` | "The default cap is 60 commands — enough to keep all built-in commands plus common skill commands visible." | 同 D3。文档同一段里"clamps configured values to 1..100"是对的(`:710`) |
| D5 | `hermes_cli/commands.py:871` | "Only skills are trimmed when the cap is reached." | 末尾 `return all_entries[:max_slots]`(`:976`)也会裁插件条目,且不计入 `hidden_count` |
| D6 | `hermes_cli/commands.py:820-822` | 只提"10 个数字位用光才静默丢弃" | `:843-844` 还有一条静默丢弃路径:名字长度合法但已被占用,直接 `continue`,不补数字 |
| D7 | `hermes_cli/commands.py:1073` | caller 在 `gateway/platforms/discord.py` | 实际在 `plugins/platforms/discord/adapter.py`;同文件 `:575` 写的是对的 |
| D8 | `hermes_cli/commands.py:1761` | "Try rg first …, then fd, **then find**" | 候选表(`:1762-1766`)只有 2×rg + 1×fd,**没有 find** |
| D9 | 注册表分节注释 `:189-190` / `:103,:136` | `# Configuration` 注释下是 `sessions`(category="Session");`# Session` 注释下是 `export`/`import`(category="Configuration") | 注释分组与 `category` 字段不一致(仅影响读代码) |

---

## 10. 可疑缺陷汇总(只记录,不修)

| # | 位置 | 现象 | 怎么会踩到 |
|---|---|---|---|
| B1 | `:93-95` | `VALID_BUSY_POLICIES` 定义了但**从未用于校验**;测试 import 了它却没有断言 | 新命令写 `busy_policy="dispatchh"` 无任何报错;派生集把它算进 bypass,网关判定为假 → 永远回"agent 忙",无 warning |
| B2 | `:405-412` | args_hint 正则 `[a-z]+(\|[a-z]+)+` 不认 `-`/`_`/空格 | `/topic` 补出不存在的 `session`;`/codex-runtime` 补出 `codex`(真值 `codex_app_server`);`/snapshot` 丢掉 `prune` |
| B3 | `:509-513` | `_resolve_config_gates` 全异常吞成空集 | `config.yaml` 语法错 → `/verbose`+`/skills` 从所有网关表面静默消失,无任何信号 |
| B4 | `:509-513` | 读 raw config(不合并默认值) | 今天两个 gate 默认都是 False,恰好等价;将来若有 gate 默认 True,用户不写该键时会被判成关,与 `load_config()` 不一致 |
| B5 | `:971-976` | `hidden_count` 只算技能;`[:max_slots]` 静默裁插件 | 插件命令 ≥ max_slots 时,日志 "N hidden" 少报被丢的插件数 |
| B6 | `:843-844` | 名字重复时静默丢弃(不补数字) | 两个技能名恰好相同(或撞保留名)时,后者从 Telegram/Discord 菜单消失,只有 Discord 分类路径会 warning |
| B7 | `:444-446` | `is_gateway_known_command` 对插件是 O(n) 线性扫描,且不做 `_`↔`-` 归一 | 插件注册名 `my-cmd`,用户/Telegram 回传 `my_cmd` → 判为未知命令(网关 `:15615` 处另有归一,两处不一致) |
| B8 | `:582-589` | 插件枚举双层吞异常返回 `[]` | 插件系统整体故障时,所有插件命令静默变"未知命令",无诊断 |
| B9 | `:1447-1449` | `_command_allowed` 异常时 **fail-open**(返回 True) | 权限过滤器抛异常 → 本该对非 admin 隐藏的命令名出现在补全里(展示层信息泄露,不是提权) |
| B10 | `:1762-1766` | 无 rg/fd 时项目文件列表为空,且空结果被缓存 5 秒 | 精简容器里 `@` 模糊补全永远空;每 5 秒重跑一次 `shutil.which`,纯浪费 |
| B11 | `:1275` + `:1328` | Slack 已**正好**顶满 50 条(实测 `len(slack_native_slashes()) == 50`) | 再加一条网关可见命令就会静默 clamp 掉一条 canonical;唯一护栏是 `test_telegram_parity` |
| B12 | `:983` vs adapter | `telegram_menu_commands` 默认参数 100,adapter 传 60 | 直接调该函数(或测试)拿到 100,与线上行为不同 |
| B13 | `:2207` | 幽灵文本按键长排序时**别名参与竞争** | `/b` 的幽灵文本来自别名 `/bg` 而非 `/background`;行为可能是想要的,但没写进注释 |

---

## 11. 配套测试(行为规格)

直接针对本文件:

- `tests/hermes_cli/test_commands.py` —— **主规格**。52 个用例,覆盖:注册表唯一性、
  别名不撞 canonical、派生字典、`GATEWAY_KNOWN_COMMANDS` 含 gated 命令、
  `gateway_help_lines` 排除 cli_only、Telegram 名不含连字符 / 含带参内置命令、
  Slack 限制 + **telegram parity**、manifest 字段、**config gate 开关两态**、
  补全器(技能 / 堆叠 / `/tools` / `/handoff` / 幽灵文本)、`_sanitize_telegram_name`、
  `_clamp_*` 三组、Telegram 菜单(external dirs / 特殊字符 / 空名)、
  Discord(允许连字符 / cap / 分类 / external dirs)、插件枚举。
- `tests/hermes_cli/test_busy_policy_invariants.py` —— busy_policy 不变量:
  bypass 集必须是注册表派生;`interrupt_then_dispatch` 类恰好是 `/stop` `/new`(含别名 `reset`)。
- `tests/hermes_cli/test_discord_skill_clamp_warning.py` —— 32 字符撞名 warning。
- `tests/hermes_cli/test_commands_execute.py` —— `execute` 字段 / `EXECUTORS` 的
  "输出与 surface 无关" 不变量。
- `tests/hermes_cli/test_path_completion.py`、`tests/hermes_cli/test_at_context_completion_filter.py`
  —— 路径与 `@` 补全。
- `tests/hermes_cli/test_subcommands_batch.py` / `test_subcommands_followup.py` /
  `test_subcommands_profile_gateway.py` —— 子命令相关。

间接引用注册表的:

- `tests/gateway/test_command_bypass_active_session.py`
- `tests/gateway/test_verbose_command.py`(gate 的 handler 侧,含 `"false"` 字符串两态)
- `tests/gateway/test_discord_slash_commands.py`、`test_discord_slash_auth.py`、
  `test_telegram_forum_commands.py`、`test_reload_skills_discord_resync.py`
- `tests/run_agent/test_steer.py:539`(`ACTIVE_SESSION_BYPASS_COMMANDS` 含 steer)

**实际跑过(本轮)**:

```
HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
  tests/hermes_cli/test_commands.py tests/hermes_cli/test_busy_policy_invariants.py
=== Summary: 2 files, 54 tests passed, 0 failed (100% complete) in 3.2s (8 workers) ===
```

(`run_tests.sh` 会写 `test_durations.json`,该文件在 `.gitignore:35`,不污染基线工作树。)

---

## 12. 重实现要点(从零重写这套东西,必须知道的 8 条)

1. **一张表,多个表面,差异用字段表达,不用分支。** 命令的"身份"(name/desc/args)
   只写一遍;"在哪些表面出现"(cli_only / gateway_only / config gate)、"忙时怎么办"
   (busy_policy / busy_handler)、"怎么执行"(execute key)都做成 `CommandDef` 上的
   声明字段。每加一个表面 = 加一个 `for cmd in REGISTRY: if <该表面的可见性判定>` 的
   派生函数,而不是复制一份清单。

2. **每个 IM 平台都有硬上限,且上限的"单位"不同,必须先把它们建模成常量。**
   Telegram:100 条 + 未公开的 ~4KB payload(所以取保守默认 60);Slack:50 条
   + 一批不可抢占的保留名;Discord:100 条 + 名字 32 字符。**把"平台硬上限"和"我们的
   保守默认"分成两个常量**(`_TELEGRAM_BOT_API_MAX_COMMANDS` vs
   `_DEFAULT_TELEGRAM_MENU_MAX_COMMANDS`),前者用于钳制用户配置,后者用于默认值。

3. **超限时必须有显式优先级,并且分层"谁先被裁"。** Hermes 的答案是
   核心命令 > 插件命令 > 技能命令,只裁最后一层;核心命令内部再用一张手写的
   `_TELEGRAM_MENU_PRIORITY` 保证运维命令(help/new/stop/status/restart/debug)永远上榜。
   **不要靠字典序或注册顺序兜底** —— 那等于"加一条新命令随机踢掉一条老命令"。
   同时**要给用户一个 override 接口**(max_commands / priority / priority_mode 三件套,
   带 prepend|append|replace 语义)。

4. **静默丢弃是这类系统最大的可运维性债。** 名字被截断、撞名、超帽 —— 每一处丢弃都
   应该 (a) 计入一个返回给调用方的 `hidden_count`,并且 (b) 在能指名道姓时打
   WARNING 说清"谁赢了、谁输了、改哪个字段"(本文件 `:1170-1188` 是范本)。Hermes 自己
   也只在 Discord 分类那一条路径做到了,其余仍是静默的(B5/B6)。

5. **"忙时行为"要声明化,并且默认必须是拒绝而不是排队。** 事故教训写在
   `should_bypass_active_session` 的 docstring 里:把命令排进 pending 队列会同时触发
   "打断 agent" 和 "队列安全网丢弃命令文本",产出 0 字符回复。正确姿势:**任何能解析的
   斜杠命令都不进队列**,要么有 mid-run handler,要么给一句明确的"忙,请等或 /stop"。
   声明值集合要有**运行期或测试期校验**(Hermes 定义了 `VALID_BUSY_POLICIES` 却没用,
   见 B1 —— 这是要避开的坑)。

6. **注册表模块必须导入轻量,可选 UI 依赖用 try/except 垫成 `object`/`None`。**
   网关、adapter、TUI 都要 import 它拿元数据,却不该被交互式终端库、插件发现、
   执行器依赖链拖累。三个手法:(a) UI 基类 ImportError 垫片;(b) `execute` 存**字符串
   键**而非 callable;(c) 插件命令**懒查**,永不进模块级派生表。

7. **配置门控要分两层,并想清楚"读 raw 还是读 merged"。** 第一层决定"出不出现在
   help/菜单/manifest"(`_is_gateway_available`),第二层在 handler 里决定"跑不跑"并
   给出可操作的开启提示;**门关时命令仍要被识别为命令**,否则用户只会看到 "Unknown
   command"。读 raw config 快但看不见 schema 默认值 —— 只有当所有 gate 的默认值都是
   falsy 时这才安全(B4)。另外**不要拿功能开关(如写入审批)兼职做可见性开关**,
   会把两个语义焊死。

8. **别名要区分"短名"和"平台拼写变体",并在派生时区别对待。** Telegram 命令名不能有
   连字符,所以必须有 `reload_mcp` 这类下划线变体;但它们不该出现在 help 的
   "(alias: …)" 里(`:558-563` 的过滤),也不该占 Slack 的 50 条名额(只钉
   `btw`/`bg` 这类真短名)。同时:**解析函数要不要做 `_`↔`-` 归一,必须全局统一决定** ——
   Hermes 在 `resolve_command` 不归一、在技能 token 归一、在网关未知命令判定处又手动
   归一,这种不一致直接产出 B7。
