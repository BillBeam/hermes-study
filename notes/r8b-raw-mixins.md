# r8b-raw-mixins —— 三个 CLI mixin(5,976 行)

> 底稿(证据层)。研究对象 `NousResearch/hermes-agent @ 863e31318`,只读。
> 覆盖文件:
> - `hermes_cli/cli_commands_mixin.py`(3,556 行,`CLICommandsMixin`,59 个方法)
> - `hermes_cli/cli_billing_mixin.py`(1,566 行,`CLIBillingMixin`,31 个方法)
> - `hermes_cli/cli_agent_setup_mixin.py`(854 行,`CLIAgentSetupMixin`,8 个方法)
>
> 溯源约定:凡断言紧跟 `路径:行号 @ 863e313` + 代码原文块。行号相对基线提交,已复核。

---

## 0. 自验记录

### 0.1 三条前提的裁决(先讲结论:三条全部不成立或需重大限定)

#### 前提 1 —— "纯机械拆分,行为中性" ✗ **不成立(有实证的反例,且作者自己在注释里承认)**

`cli_commands_mixin.py` 的模块 docstring 直接写了 "behavior-neutral":

`hermes_cli/cli_commands_mixin.py:1-13 @ 863e313`

```python
"""Slash-command handlers for the interactive CLI (god-file decomposition Phase 4).

This module hosts the ``_handle_*_command`` slash-command handlers lifted out of
``cli.py``'s ``HermesCLI`` class. ``HermesCLI`` inherits ``CLICommandsMixin`` so
every ``self.<handler>`` call resolves unchanged via the MRO — behavior-neutral.

Import discipline (mirrors gateway/slash_commands.py, PR #41886):
  * Neutral, non-cyclic deps are imported at module top-level below.
  * cli.py-internal symbols (the ``_cprint``/``_ACCENT``/``save_config_value``…
    module-level helpers and constants) are imported LAZILY inside each handler
    via ``from cli import ...`` — that resolves at call time when ``cli`` is fully
    loaded, so the mixin module never imports ``cli`` at top level (no cycle).
"""
```

`cli_agent_setup_mixin.py` 说得更绝对——"every method is lifted verbatim":

`hermes_cli/cli_agent_setup_mixin.py:8-12 @ 863e313`

```
Behavior-neutral: every method is lifted verbatim from ``HermesCLI``. ``self.*``
calls resolve unchanged via the MRO. Neutral dependencies are imported at module
top level; ``cli.py``-internal helpers/constants are imported lazily inside each
method (``from cli import ...`` resolves at call time, when ``cli`` is fully
loaded) so this module never imports ``cli`` at import time -> no import cycle.
```

**反例 A(决定性):同一个文件里,作者自己记录了这次搬迁造成的线上缺陷 #49287。**

`hermes_cli/cli_agent_setup_mixin.py:520-533 @ 863e313`

```python
            # Store reference for atexit memory provider shutdown.
            # NOTE: this MUST write to the ``cli`` module's global, not a
            # local module global. ``_run_cleanup`` (in cli.py) reads
            # ``cli._active_agent_ref`` to decide whether to fire the memory
            # provider's ``on_session_end`` hook. When this code lived in
            # cli.py a bare ``global _active_agent_ref`` worked; after the
            # god-file extraction into this mixin a ``global`` here would bind
            # *this module's* namespace, leaving ``cli._active_agent_ref`` None
            # forever — so memory shutdown never ran on /exit (#49287).
            import cli as _cli
            _cli._active_agent_ref = self.agent
            # Route agent status output through prompt_toolkit so ANSI escape
            # sequences aren't garbled by patch_stdout's StdoutProxy (#2262).
            self.agent._print_fn = _cprint
```

一行 `global _active_agent_ref` 在原文件里绑定 `cli` 的模块命名空间,搬到 mixin 后绑定的是
`hermes_cli.cli_agent_setup_mixin` 的命名空间。语法完全不变、"verbatim lift" 完全成立,行为却变了:
`/exit` 时 memory provider 的 `on_session_end` 再也不触发。**"逐字搬迁" 恰恰是它出错的原因**,因为
Python 的 `global` 是词法作用域绑定到 *定义所在模块*,不是运行时的 `type(self)` 所在模块。

这个反例有配套的回归测试锁住:`tests/cli/test_cli_active_agent_ref_wiring.py:3` 明确写
"(094aa85c37) moved agent construction into ``CLIAgentSetupMixin``"。

**反例 B:billing mixin 的 docstring 自己就撤回了这句话。**

`hermes_cli/cli_billing_mixin.py:1-14 @ 863e313`

```python
"""Billing and subscription handlers for the interactive CLI (god-file decomposition).

This module hosts the Nous billing/subscription methods lifted out of
``cli.py``'s ``HermesCLI`` class. ``HermesCLI`` inherits
``CLIBillingMixin`` so every ``self.<handler>`` call resolves unchanged
via the MRO — behavior-neutral apart from focused billing fixes.

Import discipline mirrors ``hermes_cli.cli_commands_mixin``:
  * Neutral, non-cyclic dependencies are imported at module top level below.
  * cli.py-internal symbols (the ``_cprint``/``_b``/``_d`` helpers and
    display constants) are imported LAZILY inside each method via
    ``from cli import ...``. The mixin never imports ``cli`` at module load
    time, avoiding the cycle created when ``cli.py`` imports this mixin.
"""
```

"behavior-neutral **apart from focused billing fixes**" —— 即拆分那一轮同时改了行为。

**反例 C:commands mixin 里已经有为 "standalone(无 HermesCLI)" 场景新写的防御代码。**
如果真是逐字搬迁,原文件里不会有这种分支,因为 `cli.py` 里 `self.console` 必然存在。

`hermes_cli/cli_commands_mixin.py:263-277 @ 863e313`

```python
    def _print_diff_text(self, text: str) -> None:
        """Render diff/stat text with color when a rich console is present.

        Falls back to plain print when the console isn't available (e.g. unit
        tests instantiating the mixin standalone).
        """
        console = getattr(self, "console", None)
        if console is not None:
            try:
                from cli import _rich_text_from_ansi
                console.print(_rich_text_from_ansi(text))
                return
            except Exception:
                pass
        print(text)
```

#### 关于 "lazy `from cli import ...` 在 `cli` 未完全导入 / 从未导入时会怎样"

分三种情形,结论不同:

**(a) 循环 —— 确实没有循环,但只是因为顺序刚好。** `cli.py` 在第 54–56 行导入三个 mixin:

`cli.py:54-56 @ 863e313`

```python
from hermes_cli.cli_agent_setup_mixin import CLIAgentSetupMixin
from hermes_cli.cli_commands_mixin import CLICommandsMixin
from hermes_cli.cli_billing_mixin import CLIBillingMixin
```

而 mixin 需要的所有 `cli` 符号都定义在第 54 行 **之后**(`CLI_CONFIG` 在 `cli.py:792`,
`_ACCENT` 在 `cli.py:2830`,`_cprint` 在 `cli.py:3070`,`ChatConsole` 在 `cli.py:3874`,
`save_config_value` 在 `cli.py:4100`)。也就是说:**只要有任何一条 `cli.py` 模块级语句在第 54 行到
第 4100 行之间调用了 mixin 的方法,`from cli import save_config_value` 就会在
`sys.modules['cli']` 里拿到半成品模块并抛 `ImportError`。** 目前没有这样的调用点(mixin 方法只从
`HermesCLI` 实例上调,而 `HermesCLI` 在 4205 行才定义),所以安全边界是 "没人在模块级用它",
不是结构上的保证。这是一个隐式不变量,没有测试锁住。

实证(在 `hermes-venv` 里,`HERMES_HOME` 指向临时目录):

```
A) import mixin alone: 0.463s
A) 'cli' in sys.modules after importing mixin: False
A) modules loaded: 438
B) import cli: 0.176s
B) modules loaded: 651
```

导入 mixin 本身**不会**拉入 `cli`(所以确实无循环),但也说明 mixin 是可以在没有 `cli` 的世界里被
导入并调用的 —— 这正是 (b)。

**(b) `cli` 从未导入过时调用 handler —— 不会失败,但会在 handler 内部触发一次 18,555 行模块的完整导入,
带一堆全局副作用。** `cli.py` 的模块级副作用包括:

| 行号 | 副作用 |
|---|---|
| `cli.py:231` | `load_hermes_dotenv(...)` —— 改写 `os.environ` |
| `cli.py:792` | `CLI_CONFIG = load_cli_config()` |
| `cli.py:799` | `setup_logging(mode="cli")` —— **重配根 logger** |
| `cli.py:806` | `print_config_warnings()` —— **向 stdout 打印**(会插在 handler 输出中间) |
| `cli.py:813` | `init_skin_from_config(CLI_CONFIG)` |
| `cli.py:847-` | 猴补 httpx 的 `_AsyncHttpxDelNeuter`(try 块起点) |
| `cli.py:2780` | `_install_skin_light_mode_hook()` —— 猴补 `SkinConfig.get_color` |
| `cli.py:2788` | tty 下 `_detect_light_mode()` —— **向终端写 OSC/DSR 查询序列并读回** |

`cli.py:2783-2790 @ 863e313`

```python
# Prime the light-mode detection cache early (at module load) when
# we're running interactively so OSC 11 happens before pt grabs the
# tty.  Skip for non-tty contexts (subagents, gateway, tests).
try:
    if sys.stdin.isatty() and sys.stdout.isatty():
        _detect_light_mode()
except Exception:
    pass
```

拆分之前,handler 就住在 `cli.py` 里,这些副作用必然已经发生过;拆分之后,**副作用的发生时机被推迟到
"第一次调用某个 handler"**。这本身就是行为变化(参见 §3 缺陷 3)。

**(c) TUI gateway 是否直接 import mixin?—— 不是。** `tui_gateway/slash_worker.py` 走的是完整
`HermesCLI`:

`tui_gateway/slash_worker.py:29-30 @ 863e313`

```python
import cli as cli_mod
from cli import HermesCLI
```

`tui_gateway/slash_worker.py:144 @ 863e313`

```python
        cli = HermesCLI(model=args.model or None, compact=True, resume=args.session_key, verbose=False)
```

真正 "直接 import mixin、不经 `HermesCLI.__init__`" 的是**测试**:
`tests/tools/test_write_approval.py:98 @ 863e313`

```python
    handler = CLICommandsMixin.__new__(CLICommandsMixin)
```

`tests/hermes_cli/test_diff_command.py:49-51 @ 863e313`

```python
class _Stub(CLICommandsMixin):
    def __init__(self, agent=None):
        self.agent = agent
```

所以 mixin 事实上有**两个宿主契约**:完整 `HermesCLI`,和只塞了两三个属性的测试 stub。前者靠
`__init__` 兜底,后者靠 handler 内部的 `getattr`/`hasattr` 兜底,而这两套兜底在 59 个方法里**并不一致**
(见 §3 缺陷 4)。

#### 前提 2 —— "因为是 mixin,`self.<attr>` 必然解析到 `HermesCLI.__init__` 设过的属性" ✗ **不成立(两个层面)**

**层面一:数据属性。** 用 AST 把 `HermesCLI.__init__`(`cli.py:4213-4753`)里所有 `self.X = ` 收齐
(161 个),再和三个 mixin 里所有 `self.X` 读点做差集,只有一个属性完全不在 `__init__` 里:

- `self._resume_display_history` —— `__init__` 从不设置;由
  `hermes_cli/cli_agent_setup_mixin.py:623` 和 `hermes_cli/cli_commands_mixin.py:1071` 在运行时首次赋值。

它的三个读点里,两个是"先写后读"(同一函数内),一个用了 `getattr` 兜底:

`hermes_cli/cli_agent_setup_mixin.py:674-677 @ 863e313`

```python
        from cli import CLI_CONFIG, _record_output_history_entry, _strip_reasoning_tags, _suspend_output_history
        from tools.ansi_strip import sanitize_display_text as _sanitize_display_text
        display_history = getattr(self, "_resume_display_history", self.conversation_history)
        if not display_history:
```

而 `hermes_cli/cli_commands_mixin.py:1113` 是裸读:

`hermes_cli/cli_commands_mixin.py:1112-1114 @ 863e313`

```python
        title_part = f" \"{session_meta['title']}\"" if session_meta.get("title") else ""
        msg_count = len([m for m in self._resume_display_history if m.get("role") == "user" and not m.get("display_kind")])
        if self.conversation_history:
```

只因为同一函数第 1071 行刚赋过值才不炸。**结论:数据属性层面前提"几乎"成立,但不是因为 `__init__`,
而是因为写点恰好支配读点** —— 这是一个没有类型/结构保证的巧合。

**层面二(真正的破口):`self.<attr>` 大量解析到的不是属性,而是仍然留在 `cli.py` 里的兄弟方法。**
三个 mixin 里 `self.X()` 形式的调用,有 **35 个** 的定义体不在这三个文件里,而在 `cli.py` 的
`HermesCLI` 类体内:

```
_apply_tui_skin_style      _console_print            _current_reasoning_callback
_disable_voice_mode        _enable_voice_mode        _ensure_tirith_security
_fast_command_available    _get_goal_manager         _get_heartbeat_manager
_install_tool_callbacks    _invalidate               _list_recent_sessions
_normalize_model_for_provider   _normalize_slash_confirm_choice
_prompt_text_input         _prompt_text_input_modal  _render_resume_history_panel_lines
_resolve_checkpoint_ref    _resolve_personality_prompt   _restore_session_cwd
_restore_session_yolo      _scrollback_box_width     _show_recent_sessions
_show_voice_status         _show_wake_word_status    _start_heartbeat_watchdog
_start_wake_word_listener  _stop_wake_word_listener  _toggle_voice_tts
_transfer_session_yolo     _try_attach_clipboard_image   _write_osc52_clipboard
new_session                show_tools                undo_last
```

(全部 35 个都能在 `cli.py` 的 `HermesCLI` 里找到定义,没有解析不到的;这一点我验证过。)

所以准确的描述是:**这不是一次"切出一个自洽模块"的拆分,而是把方法体挪走、把耦合从"同文件调用"降级成
"跨文件隐式接口"**。加上 33 个 lazy 导入的 `cli` 模块级符号,三个 mixin 对 `cli.py` 的依赖面是
**35 个方法 + 33 个模块级符号 = 68 个名字**,且这个接口没有任何一处显式声明(没有 ABC、没有 Protocol、
没有 `if TYPE_CHECKING` 的 stub)。

#### 前提 3 —— "billing mixin 只显示费用信息,不能改变 agent 行为" ✗ **严重不成立**

`CLIBillingMixin` 是三个文件里唯一一个**会真的花钱**的。它是 `/topup`、`/subscription`、`/usage`
背后的实现(`cli.py:10148-10150`、`cli.py:11377-11378`)。

**(1) 直接扣款。** `_billing_confirm_and_charge` 调 `post_charge`:

`hermes_cli/cli_billing_mixin.py:1143-1160 @ 863e313`

```python
        key = new_idempotency_key()
        try:
            result = post_charge(amount_usd=amount, idempotency_key=key)
        except BillingScopeRequired:
            # In-flight reauth: allow remote spending, then resume THIS charge
            # (press-Enter beat) — no command re-run. Reuses the same idem key.
            self._billing_handle_scope_required(state, amount=amount, idempotency_key=key)
            return
        except BillingError as exc:
            self._billing_render_charge_error(state, exc)
            return

        charge_id = result.get("chargeId")
        if not charge_id:
            print("  🔴 No charge id returned; please check the portal.")
            return
        _cprint(f"  {_d('Charge submitted — confirming settlement…')}")
        self._billing_poll_charge(state, charge_id, amount)
```

**(2) 设置**未来**的自动扣款。** `_billing_auto_reload_flow`:

`hermes_cli/cli_billing_mixin.py:1500-1517 @ 863e313`

```python
        from hermes_cli.nous_billing import (
            BillingError,
            BillingScopeRequired,
            patch_auto_top_up,
        )

        try:
            patch_auto_top_up(
                enabled=True, threshold=float(threshold_amt), top_up_amount=float(reload_amt)
            )
        except BillingScopeRequired:
            self._billing_handle_scope_required(state)
            return
        except BillingError as exc:
            self._billing_render_charge_error(state, exc)
            return
        print(f"  ✅ Auto-reload on: below {format_money(threshold_amt)} → "
              f"reload to {format_money(reload_amt)}.")
```

**(3) 变更订阅档位(升档立即按比例扣款)。** `_subscription_apply` 的 `kind == "upgrade"` 分支调
`post_subscription_upgrade`,并且为此专门维护幂等键(`hermes_cli/cli_billing_mixin.py:589-596`)。

**(4) 打开浏览器,给这台终端**永久**授予新的 OAuth scope,并改写进程内的 token 缓存。**

`hermes_cli/cli_billing_mixin.py:684-704 @ 863e313`

```python
        try:
            from hermes_cli.auth import step_up_nous_billing_scope

            granted = step_up_nous_billing_scope(open_browser=True)
        except Exception as exc:
            print(f"  Couldn't allow Remote Spending: {exc}")
            return
        if not granted:
            print("  Couldn't allow Remote Spending — an org admin or owner has to approve it for this org.")
            return
        _cprint(f"  {_DIM}✓ Remote Spending allowed.{_RST}")
        # Bust the 30s token cache so the replay uses the freshly-scoped token. The
        # cache still holds the pre-grant unscoped token, and _request only busts it
        # on a 401 (not a 403 scope denial) — without this, the replay would 403
        # again and (before the allow_stepup guard) re-prompt in a loop.
        try:
            from hermes_cli import nous_billing as _nb

            _nb.invalidate_cached_token()
        except Exception:
            pass
```

**(5) 间接改变 agent 行为。** 计划档位决定了哪些模型可达 —— 这是 mixin 自己的文案说的:
`hermes_cli/cli_billing_mixin.py:66`(`'> Free · free models only. Run /subscription to reach paid models.'`)、
`hermes_cli/cli_billing_mixin.py:224`(`'> Paid models need a subscription. Start one to reach them.'`)、
`hermes_cli/cli_billing_mixin.py:227`(`Top up or upgrade before a mid-run cutoff.`)。余额耗尽会造成
**turn 中途被切断**。所以 "/topup 只是显示" 在功能上等价于说 "充值不影响能不能跑" —— 显然不成立。

**唯一成立的一半**:billing mixin 对 `self` 是**完全只读**的 —— AST 扫描全文件 `self.X = ` 写点为
**0 个**。它不改 CLI 进程内状态,但它改远端账务状态、改 OAuth 授权、改 `hermes_cli.nous_billing` 的
模块级 token 缓存。准确的说法是:**"不改 CLI 内存状态" ≠ "只显示"**。

### 0.2 锚点复核记录

- 引用的代码块全部先用脚本按行号从源码原样 dump,再逐段复制进本文,**未手打、未重排缩进**。
- 对最终文稿做了两轮机器复核:抽取本文每一处 `路径:行号 @ 863e313` 后紧跟的代码块,
  按行号回读源文件逐行逐字比对(脚本见 §5.1)。
- **共复核带代码块的锚点 73 个,累计发现 15 个错误,全部已修正:**
  - 9 个是"少抄了区间末尾的空行"导致的区间末号 +1;
  - 5 个是整体行号偏移(`hermes_cli/cli_commands_mixin.py:1261→1262`、`:541→542`、`:2197→2196`、
    `hermes_cli/cli_billing_mixin.py:111→109`、`cli.py:2784→2783`);
  - 1 个是单行锚点偏 2 行(`cli.py:8880→8878`)。
- **最终一轮:73 个全部逐字通过,不一致 0。**
- 另抽查了 27 个**不带代码块的行内锚点**的实际内容,其中 6 个指向的是 `try:` 块首行而非我描述的
  调用行,已收紧到精确调用行(`cli.py:797→799`、`804→806`、`811→813`、`2786→2788`、
  `17475-17479→17473-17480`,以及 `cli.py:847` 标注为块起点)。
- 另有 3 处在写作过程中被我**主动推翻并改写**的结论,记录在 §0.3,以免留下假阳性。

### 0.3 三处我自己推翻的初判(负面结果也是产出)

1. **`BillingError` 同时看 `.error` 和 `.code` 不是笔误。** 我一度怀疑
   `hermes_cli/cli_billing_mixin.py:1241-1242` 的 `getattr(exc, "code", None)` 是把 `.error` 写错了。查
   `hermes_cli/nous_billing.py:61-79` 后确认 `BillingError.__init__` 同时接受并保存 `error=` 和
   `code=` 两个字段(注释写 "`code` (the new machine code dual-emitted alongside `error`)"),
   双查是**正确的向后兼容**。撤回。
2. **"确认框输入数字会选错行" 大部分不成立。** 我一度认为 `_normalize_slash_confirm_choice`
   (`cli.py:8812-8827`)的硬编码别名表(`"1"→once`、`"2"→always`、`"3"→cancel`)会让 billing 弹窗
   的数字选择全部错位。后来发现 `cli.py:15854-15866` 另外注册了 0–9 的**按键绑定**,它是按
   `choices[idx][0]` 正确索引的,并且按下即提交,所以在活的 TUI 里数字是对的。只剩一个窄口子
   (弹窗降级到裸 stdin 时),降级为 §3 缺陷 12。
3. **`_usage_bar_lines` 里 `pb.total_usd > 0` 不会 `TypeError`。** 查
   `agent/billing_usage.py:98-99`,`UsageBar.remaining_usd/total_usd` 都是非 Optional 的 `float`,
   不会是 `None`。撤回。

---

## 1. 段内地图

### 1.1 三个文件的定位

```
                          cli.py  (18,555 行)
                          ├── 模块级:CLI_CONFIG / _cprint / _ACCENT / ChatConsole /
                          │            save_config_value / AIAgent 转发 …(33 个被 mixin 懒引用)
                          └── class HermesCLI(CLIAgentSetupMixin, CLICommandsMixin, CLIBillingMixin)
                                 ├── __init__            161 个 self.X = 
                                 ├── run() / process_loop / process_command  ← 调度层
                                 └── 35 个被 mixin 反向调用的兄弟方法

   ┌──────────────────────────┬──────────────────────────┬──────────────────────────┐
   │ CLIAgentSetupMixin       │ CLICommandsMixin         │ CLIBillingMixin          │
   │ 854 行 / 8 方法           │ 3,556 行 / 59 方法        │ 1,566 行 / 31 方法        │
   │ agent 生命周期            │ 斜杠命令处理器            │ Nous 账务 5 屏 + 订阅     │
   │ 凭据解析 / 构造 / 恢复显示 │ /rollback … /wake         │ /usage /subscription /topup│
   └──────────────────────────┴──────────────────────────┴──────────────────────────┘
```

`cli.py:4205 @ 863e313`

```python
class HermesCLI(CLIAgentSetupMixin, CLICommandsMixin, CLIBillingMixin):
```

MRO 顺序 = `HermesCLI → CLIAgentSetupMixin → CLICommandsMixin → CLIBillingMixin → object`。
三个 mixin 之间**没有任何方法名重叠**,所以 MRO 顺序在这里是无意义的(换顺序也一样)——
这是"按主题切,不是按覆写切"的证据。

### 1.2 `CLIAgentSetupMixin`(8 个方法,agent 生命周期)

| 方法 | 行号 | 作用 |
|---|---|---|
| `_ensure_runtime_credentials` | 25 | 重解析 provider 凭据(支持轮换),失败时走 fallback 链;必要时置 `self.agent = None` |
| `_runtime_credentials_ready` | 187 | **静默**探测(不打印、不改状态),给首次运行引导用 |
| `_offer_first_run_setup` | 221 | 完全未配置时提供 provider 选择器 |
| `_resolve_turn_agent_config` | 285 | 单轮的 model/runtime 路由 + `/fast` 覆盖 |
| `_init_agent` | 333 | **唯一的主 agent 构造点**(50 个 kwarg);resume 时装载历史 |
| `_preload_resumed_session` | 576 | run() 早期先把历史读出来供显示 |
| `_display_resumed_history` | 666 | 渲染 "Previous Conversation" 面板 |

模块顶层只导入 `sys` 和 `rich.markup.escape` —— 是三者里最干净的。

### 1.3 `CLICommandsMixin`(59 个方法)

模块顶层导入:

`hermes_cli/cli_commands_mixin.py:15-40 @ 863e313`

```python
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from urllib.parse import urlparse

from rich import box as rich_box
from rich.markup import escape as _escape
from rich.panel import Panel

from hermes_constants import display_hermes_home, is_termux as _is_termux_environment
from agent.turn_context import extract_api_content_sidecar
from hermes_cli.browser_connect import (
    DEFAULT_BROWSER_CDP_URL,
    discover_local_cdp_url,
    find_free_debug_port,
    is_browser_debug_ready,
    launch_chrome_debug,
    local_port_in_use,
    manual_chrome_debug_command,
)
```

按主题分簇(行号为方法起点):

| 簇 | 方法 |
|---|---|
| 文件状态 | `_handle_rollback_command`51 · `_handle_diff_command`145 · `_print_session_diff`223 · `_print_diff_text`263 · `_handle_snapshot_command`279 |
| 配置迁移 | `_handle_export_command`366 · `_handle_import_command`397 · `_handle_profile_command`768 |
| 进程/后台 | `_handle_stop_command`440 · `_handle_agents_command`473 · `_handle_background_command`1947 |
| **会话** | `_handle_handoff_command`781 · `_handle_resume_command`950 · `_handle_sessions_command`1138 · `_handle_branch_command`1171 |
| 输入辅助 | `_handle_paste_command`576 · `_handle_copy_command`602 · `_handle_image_command`663 · `_compose_in_editor`2835 · `_handle_prompt_compose_command`2879 |
| 工具/技能 | `_handle_tools_command`688 · `_handle_skills_command`1841 · `_handle_learn_command`1862 · `_handle_init_command`1888 · `_handle_memory_command`1914 · `_save_write_approval`1942 · `_handle_bundles_command`2102 |
| 自动化 | `_handle_cron_command`1501 · `_handle_suggestions_command`1747 · `_handle_blueprint_command`1768 · `_handle_curator_command`1798 · `_handle_kanban_command`1820 · `_handle_heartbeat_command`2371 |
| **目标循环** | `_handle_refine_command`2456 · `_handle_goal_command`2497 · `_handle_goal_draft`2670 · `_handle_subgoal_command`2716 |
| 浏览器 | `_handle_browser_command`2142 |
| 显示开关 | `_handle_personality_command`1329 · `_handle_pet_command`1375 · `_handle_hatch_command`1433 · `_handle_skin_command`2792 · `_handle_focus_command`2908 · `_set_tool_progress_mode`3005 · `_note_focus_hidden_line`3023 · `_emit_focus_recovery_line`3041 · `_handle_footer_command`3070 · `_handle_timestamps_command`3123 · `_handle_indicator_command`3315 |
| 模型行为 | `_handle_reasoning_command`3173 · `_handle_busy_command`3272 · `_handle_fast_command`3355 · `_handle_approvals_command`3060 |
| 运维 | `_handle_journey_command`539 · `_handle_debug_command`3410 · `_handle_update_command`3436 |
| 语音 | `_handle_voice_command`3488 · `_handle_wake_command`3512 · `_persist_wake_word_enabled`3543 |

**统计事实(AST 统计,可复算)**:59 个方法里 **36 个**含 `from cli import ...`,**23 个**完全不碰 `cli`。
这直接反驳了 docstring 的 "imported LAZILY inside each handler" 的普适口吻(见 §4)。

### 1.4 `CLIBillingMixin`(31 个方法)

模块顶层**零导入**(只有 `from __future__ import annotations`)—— 所有依赖都是方法内懒导入。

三条入口 → 五屏状态机:

```
/usage        → _print_nous_credits_block (23) → _usage_bar_lines (926)
                → _print_usage_cta (88)
/subscription → _show_subscription (103)
                → _subscription_overview (147)
                    ├─ 免费+admin → _subscription_free_catalog (292) → 门户 deep-link
                    └─ 付费+admin → _subscription_change_menu (387)
                          ├─ change → _subscription_pick_tier (421)
                          │             → _subscription_preview_and_confirm (449)
                          │                 → _subscription_apply (565)  ← 扣款
                          ├─ keep   → _subscription_apply(("resume", None))
                          ├─ cancel_sub → _subscription_confirm_cancel (543)
                          └─ portal → _subscription_open_portal (357)
/topup        → _show_billing (754) → _billing_overview (795)
                    ├─ buy   → _billing_buy_flow (1019)
                    │            [无卡] → _billing_add_card_flow (975)
                    │            → _billing_confirm_and_charge (1092)  ← 扣款
                    │                → _billing_poll_charge (1162)  2s 轮询 / 5 分钟上限
                    ├─ auto  → _billing_auto_reload_flow (1374) / _billing_auto_reload_disable (1519)
                    ├─ limit → _billing_limit_screen (1544)   只读
                    └─ portal→ _billing_open_portal (947)

横切:_subscription_handle_scope_required (656) / _billing_handle_scope_required (1267)
      —— 403 insufficient_scope 的"就地补授权 + 重放"
错误渲染:_subscription_render_error (719) / _subscription_render_upgrade_ambiguous (736)
          / _billing_render_charge_failed (1206) / _billing_render_charge_error (1220)
```

---

## 2. 逐机制精读

### 2.1 lazy `from cli import ...` 到底解决了什么、代价是什么

**它解决的问题是真实的**:`cli.py` 在第 54 行 import 三个 mixin;若 mixin 在模块顶层写
`from cli import _cprint`,则 `import cli` → `import mixin` → `import cli`(半成品)→
`ImportError: cannot import name '_cprint' from partially initialized module 'cli'`。把导入下沉到
函数体,导入时刻推迟到调用时刻,循环消失。

**它没解决的问题**:

1. **接口没有被声明。** 33 个符号散落在 36 个方法体里,任何一次 `cli.py` 重命名都只能在运行时炸,
   而且是在用户敲下某个斜杠命令那一刻炸。静态检查器看不到(名字在字符串式的 import 语句里,但
   `cli` 模块在 mixin 的静态视图里根本不存在)。
2. **失败点被搬进了用户路径。** 拆分前,`_cprint` 是同文件的一个名字,查找失败在导入期就暴露;
   拆分后变成 handler 内的一次 import,失败发生在 `/reasoning` 执行到一半时。
3. **顺序不变量是隐式的**(见 §0.1(a)):所有被引用的符号都必须定义在 `cli.py:54` 之后,
   且不能有任何模块级代码在那之前调用 mixin 方法。没有测试锁这个。

**同一个仓库里另一种做法的对照**:`_print_diff_text`(`hermes_cli/cli_commands_mixin.py:269-277`,已引于 §0.1)
把 `from cli import` 包在 `try/except Exception` 里并给出降级路径 —— 只有 1 处这样写。其余 35 处是
裸 import,一旦 `cli` 不可导入,handler 直接抛。

### 2.2 `self.*` 契约:35 个跨文件方法与"两个宿主"

见 §0.1 前提 2 的清单。这里补充两个观察:

**(1) 兜底方式在同一文件内自相矛盾。** 同一个属性 `_agent_running`:

- `hermes_cli/cli_commands_mixin.py:536` 用 `getattr(self, "_agent_running", False)`
- `hermes_cli/cli_commands_mixin.py:860` 用 `getattr(self, "_agent_running", False)`
- 但 `hermes_cli/cli_commands_mixin.py:2019` 和 `2093` 是**裸读**:

`hermes_cli/cli_commands_mixin.py:2017-2022 @ 863e313`

```python
                def _bg_thinking(text: str) -> None:
                    # Concurrent bg tasks may race on _spinner_text; acceptable for best-effort UI.
                    if not self._agent_running:
                        self._spinner_text = text
                        if self._app:
                            self._app.invalidate()
```

`hermes_cli/cli_commands_mixin.py:2091-2100 @ 863e313`

```python
                self._background_tasks.pop(task_id, None)
                # Clear spinner only if no foreground agent owns it
                if not self._agent_running:
                    self._spinner_text = ""
                if self._app:
                    self._invalidate(min_interval=0)

        thread = threading.Thread(target=run_background, daemon=True, name=f"bg-task-{task_id}")
        self._background_tasks[task_id] = thread
        thread.start()
```

**(2) `_pending_input` 的 `hasattr` 守卫是死代码(对 `HermesCLI` 而言),但对 stub 宿主是活的,
而同一文件里另一处又不守卫。**

`cli.py:4633 @ 863e313`

```python
        self._pending_input = queue.Queue()
```

守卫版(`/learn`、`/init`、`/browser connect`):

`hermes_cli/cli_commands_mixin.py:1883-1886 @ 863e313`

```python
        if hasattr(self, "_pending_input"):
            self._pending_input.put(msg)
        else:  # pragma: no cover - defensive (no live input loop)
            print("  /learn needs an active chat session to run.")
```

不守卫版(`/goal`):用 `except Exception: pass` **静默吞掉**:

`hermes_cli/cli_commands_mixin.py:2664-2668 @ 863e313`

```python
        # separate message after setting the goal.
        try:
            self._pending_input.put(state.goal)
        except Exception:
            pass
```

后果:`/goal <text>` 的"立刻踢一脚循环"如果失败,用户只会看到 "Goal set" 却什么也不发生,没有任何提示。

### 2.3 会话切换簇:`/resume`、`/branch`、`/sessions`、`/handoff`

这一簇是 commands mixin 里最"有状态"的部分,四个 handler 共享一套固定的切换协议:

```
1. flush 未落盘消息   agent._flush_messages_to_session_db(...)        #47202
2. 结束旧 session     _session_db.end_session(old, <reason>)
3. 切 self.session_id + _sync_process_session_id(new)                 (让 tool 的进程注册表跟上)
4. 载入/复制历史      get_resume_conversations / append_messages_batch
5. 同步 agent         agent.session_id / reset_session_state /
                      _last_flushed_db_idx / _todo_store / _invalidate_system_prompt
6. 通知 memory        _memory_manager.on_session_switch(..., reset=False)  #6672
7. 恢复 cwd + YOLO    _restore_session_cwd / _restore_session_yolo(_transfer_session_yolo)
```

`/resume` 和 `/branch` 各自把这 7 步**手抄了一遍**(`hermes_cli/cli_commands_mixin.py:1033-1136` vs
`1208-1327`),没有抽公共函数。这是本段最大的一处结构性重复:两处的 agent 同步块几乎逐行相同,
只有 `session_start` 和 `reason` 不同。任何一处加字段(例如将来 agent 多一个 per-session 缓存)
都要记得改两处。

值得记的两个设计点:

**(a) 双投影历史。** `/resume` 从**一次** lineage SELECT 拿两份投影:

`hermes_cli/cli_commands_mixin.py:1066-1073 @ 863e313`

```python
        model_history, display_history = self._session_db.get_resume_conversations(
            target_id
        )
        restored = [m for m in (model_history or []) if m.get("role") != "session_meta"]
        self.conversation_history = restored
        self._resume_display_history = [
            m for m in (display_history or []) if m.get("role") != "session_meta"
        ]
```

`model_history` 做过 alternation 修复(供模型重放),`display_history` 是原样 lineage(供 UI)。
理由写在 `1055-1065` 的注释里:一次性把持久的 `user;user` 违例治好,而不是每个请求都跑一遍前置修复。

**(b) `/branch` 保留 api_content sidecar 以保住 prompt cache:**

`hermes_cli/cli_commands_mixin.py:1262-1266 @ 863e313`

```python
                        # Keep the api_content sidecar so the branch's first turn
                        # replays the parent's exact wire bytes (warm provider
                        # prompt cache) instead of a full cold prefill.
                        "api_content": extract_api_content_sidecar(msg),
                        "timestamp": msg.get("timestamp"),
```

**(c) `/handoff` 是唯一一个返回值有语义的 handler**:返回 `False` 表示"退出 CLI"(和 `/quit` 同义),
并且用 `state.db` 的 `handoff_state` 列做**跨进程握手**:写 `pending` → 阻塞轮询 0.5s/次 → 60s 超时
→ `fail_handoff`。它显式拒绝 mid-turn(`hermes_cli/cli_commands_mixin.py:860-862`),理由是在飞的 turn 会和
gateway 的 `switch_session` 抢。

### 2.4 `/background`:仓库里的第二条 agent 构造路径

`_handle_background_command` 自己构造一个 `AIAgent`,不走 `_init_agent`。两条路径的 kwarg 差异是
本段最有价值的发现之一(AST 精确对比):`_init_agent` 传 **50 个** kwarg,`/background` 传 **26 个**,
差 **24 个**,且是单向的(`/background` 没有任何 `_init_agent` 不传的)。

`hermes_cli/cli_commands_mixin.py:1986-2013 @ 863e313`

```python
                bg_agent = AIAgent(
                    model=turn_route["model"],
                    api_key=turn_route["runtime"].get("api_key"),
                    base_url=turn_route["runtime"].get("base_url"),
                    provider=turn_route["runtime"].get("provider"),
                    api_mode=turn_route["runtime"].get("api_mode"),
                    acp_command=turn_route["runtime"].get("command"),
                    acp_args=turn_route["runtime"].get("args"),
                    max_tokens=turn_route["runtime"].get("max_tokens"),
                    max_iterations=self.max_turns,
                    enabled_toolsets=self.enabled_toolsets,
                    quiet_mode=True,
                    verbose_logging=False,
                    session_id=task_id,
                    platform="cli",
                    session_db=self._session_db,
                    reasoning_config=self.reasoning_config,
                    service_tier=self.service_tier,
                    request_overrides=turn_route.get("request_overrides"),
                    providers_allowed=self._providers_only,
                    providers_ignored=self._providers_ignore,
                    providers_order=self._providers_order,
                    provider_sort=self._provider_sort,
                    provider_require_parameters=self._provider_require_params,
                    provider_data_collection=self._provider_data_collection,
                    openrouter_min_coding_score=self._openrouter_min_coding_score,
                    fallback_model=self._fallback_model,
                )
```

对照前台:

`hermes_cli/cli_agent_setup_mixin.py:467-519 @ 863e313`

```python
            self.agent = AIAgent(
                model=effective_model,
                api_key=runtime.get("api_key"),
                base_url=runtime.get("base_url"),
                provider=runtime.get("provider"),
                requested_provider=runtime.get("requested_provider"),
                api_mode=runtime.get("api_mode"),
                acp_command=runtime.get("command"),
                acp_args=runtime.get("args"),
                credential_pool=runtime.get("credential_pool"),
                max_tokens=self.max_tokens,
                max_iterations=self.max_turns,
                enabled_toolsets=self.enabled_toolsets,
                disabled_toolsets=self.disabled_toolsets,
                verbose_logging=self.verbose,
                quiet_mode=not self.verbose,
                tool_progress_mode=getattr(self, "tool_progress_mode", "all"),
                ephemeral_system_prompt=self.system_prompt if self.system_prompt else None,
                prefill_messages=self.prefill_messages or None,
                reasoning_config=self.reasoning_config,
                service_tier=self.service_tier,
                request_overrides=request_overrides,
                providers_allowed=self._providers_only,
                providers_ignored=self._providers_ignore,
                providers_order=self._providers_order,
                provider_sort=self._provider_sort,
                provider_require_parameters=self._provider_require_params,
                provider_data_collection=self._provider_data_collection,
                openrouter_min_coding_score=self._openrouter_min_coding_score,
                session_id=self.session_id,
                platform="cli",
                session_db=self._session_db,
                clarify_callback=self._clarify_callback,
                reasoning_callback=self._current_reasoning_callback(),

                fallback_model=self._fallback_model,
                thinking_callback=self._on_thinking,
                checkpoints_enabled=self.checkpoints_enabled,
                checkpoint_max_snapshots=self.checkpoint_max_snapshots,
                checkpoint_max_total_size_mb=self.checkpoint_max_total_size_mb,
                checkpoint_max_file_size_mb=self.checkpoint_max_file_size_mb,
                pass_session_id=self.pass_session_id,
                skip_context_files=self.ignore_rules,
                skip_memory=self.ignore_rules,
                tool_progress_callback=self._on_tool_progress,
                tool_start_callback=self._on_tool_start if self._inline_diffs_enabled else None,
                tool_complete_callback=self._on_tool_complete if self._inline_diffs_enabled else None,
                stream_delta_callback=self._stream_delta if self.streaming_enabled else None,
                tool_gen_callback=self._on_tool_gen_start if self.streaming_enabled else None,
                notice_callback=self._on_notice,
                notice_clear_callback=self._on_notice_clear,
                reaction_callback=self._on_reaction,
            )
```

24 个缺失项里,大部分是回调(后台任务不需要 UI 回调,合理),但有 **6 个是用户显式表达的约束**:

| 缺失 kwarg | 语义 | 缺失后果 |
|---|---|---|
| `disabled_toolsets` | 用户在 `agent.disabled_toolsets` 里禁用的工具集 | 后台 agent **能用被禁工具**(见 §3 缺陷 1) |
| `ephemeral_system_prompt` | `/personality` 与 `agent.system_prompt` | 后台任务丢失人格/系统提示 |
| `skip_context_files` / `skip_memory` | `--ignore-rules` | 后台任务照读 AGENTS.md 与 memory |
| `checkpoints_enabled` 及三个上限 | 文件快照 | 后台任务改文件**无 checkpoint 覆盖**,`/rollback` 回不去 |
| `credential_pool` | 密钥轮换池 | 后台任务不轮换密钥 |
| `pass_session_id` | 系统提示里是否带 session id | 行为不一致 |

### 2.5 `_ensure_runtime_credentials`:凭据再解析、fallback 降级、agent 重建

这是三个 mixin 里唯一一个**能改写会话核心路由**的函数。它做四件事:

**(1) 重解析。** 每次调用都重新跑 `resolve_runtime_provider`,目的是"密钥轮换和 token 刷新不用重启 CLI"。

**(2) 主 provider 认证失败时,沿 `--fallback-model` 链降级,并把降级结果写死进会话:**

`hermes_cli/cli_agent_setup_mixin.py:49-79 @ 863e313`

```python
        # Primary provider auth failed — try fallback providers before giving up.
        if runtime is None and _primary_exc is not None:
            from hermes_cli.auth import AuthError
            if isinstance(_primary_exc, AuthError):
                _fb_chain = self._fallback_model if isinstance(self._fallback_model, list) else []
                for _fb in _fb_chain:
                    _fb_provider = (_fb.get("provider") or "").strip().lower()
                    _fb_model = (_fb.get("model") or "").strip()
                    if not _fb_provider or not _fb_model:
                        continue
                    try:
                        from hermes_cli.fallback_config import resolve_entry_api_key

                        _fb_kwargs = {"requested": _fb_provider}
                        if _fb.get("base_url"):
                            _fb_kwargs["explicit_base_url"] = _fb["base_url"]
                        _fb_api_key = resolve_entry_api_key(_fb)
                        if _fb_api_key:
                            _fb_kwargs["explicit_api_key"] = _fb_api_key
                        runtime = resolve_runtime_provider(**_fb_kwargs)
                        logger.warning(
                            "Primary provider auth failed (%s). Falling through to fallback: %s/%s",
                            _primary_exc, _fb_provider, _fb_model,
                        )
                        _cprint(f"⚠️  Primary auth failed — switching to fallback: {_fb_provider} / {_fb_model}")
                        self.requested_provider = _fb_provider
                        self.model = _fb_model
                        _primary_exc = None
                        break
                    except Exception:
                        continue
```

注意 `self.requested_provider` / `self.model` 是**永久改写**:一次瞬时的认证抖动会把整个会话
降级到 fallback 模型,并且没有任何自动回升路径(下次调用时 `requested` 已经是 fallback 了)。

**(3) callable api_key(Azure Entra ID bearer provider)的特判。** 这是有专门测试锁住的
(`tests/run_agent/test_callable_api_key.py:263-268` 断言源码里必须出现
`_is_callable_provider = callable(api_key)`):

`hermes_cli/cli_agent_setup_mixin.py:93-99 @ 863e313`

```python
        # A callable api_key is a bearer-token provider (Azure Foundry
        # Entra ID — ``azure_identity_adapter.build_token_provider``).
        # The OpenAI SDK accepts ``Callable[[], str]`` for ``api_key`` and
        # invokes it before every request. Skip the string-only validation
        # and placeholder substitution for callables.
        _is_callable_provider = callable(api_key) and not isinstance(api_key, str)
        if not _is_callable_provider and (not isinstance(api_key, str) or not api_key):
```

**(4) 变更检测 → 销毁 agent。**

`hermes_cli/cli_agent_setup_mixin.py:127-137 @ 863e313`

```python
        credentials_changed = api_key != self.api_key or base_url != self.base_url
        routing_changed = (
            resolved_provider != self.provider
            or resolved_api_mode != self.api_mode
            or resolved_acp_command != self.acp_command
            or resolved_acp_args != self.acp_args
        )
        self.provider = resolved_provider
        self.api_mode = resolved_api_mode
        self.acp_command = resolved_acp_command
        self.acp_args = resolved_acp_args
```

`hermes_cli/cli_agent_setup_mixin.py:177-185 @ 863e313`

```python
        model_changed = self._normalize_model_for_provider(resolved_provider)

        # AIAgent/OpenAI client holds auth at init time, so rebuild if key,
        # routing, or the effective model changed.
        if (credentials_changed or routing_changed or model_changed) and self.agent is not None:
            self.agent = None
            self._active_agent_route_signature = None

        return True
```

第 127 行的 `api_key != self.api_key` 对 callable provider 是**对象身份比较**。
`hermes_cli/runtime_provider.py:1437` 每次都新建一个 provider(`build_token_provider(config=entra_config)`),
而 `agent/azure_identity_adapter.py:252-253` 返回的是
`ai.get_bearer_token_provider(credential, config.scope)` —— 每次都是新对象。所以对 Entra ID 用户,
`credentials_changed` **恒为 True**。这在 `_init_agent` 里无害(它在 `self.agent is not None` 时
提前返回,根本不会走到这儿),但在 `/background` 路径里是每次必炸(见 §3 缺陷 2)。

### 2.6 显示通道:`print()` vs `_cprint()`,以及 patch_stdout

仓库自己在三处文档化了这条规则:

**规则出处 1**(`_handle_journey_command` docstring):

`hermes_cli/cli_commands_mixin.py:542-545 @ 863e313`

```
        The read-only views (default + ``list``) render Rich color, which
        patch_stdout would swallow as raw escapes; capture with forced ANSI and
        re-emit through ``_cprint``. ``delete``/``edit`` are interactive
        (confirm prompt / ``$EDITOR``) so they keep the real stdio.
```

**规则出处 2**(`_handle_tools_command` 内的 `_run_capture`):

`hermes_cli/cli_commands_mixin.py:705-712 @ 863e313`

```python
            """Run tools_disable_enable_command, routing its ANSI-colored
            print() output through _cprint when inside the interactive TUI
            so escapes aren't mangled by patch_stdout's StdoutProxy into
            garbled '?[32m...?[0m' text.

            Outside the TUI (standalone mode, tests), call straight through
            so real stdout / pytest capture works as expected.
            """
```

**规则出处 3**(billing mixin,把"顺序"也纳入):

`hermes_cli/cli_billing_mixin.py:45-86 @ 863e313`

```python
        if usage is not None and usage.available and format_renews is not None:
            printed_any = False
            plan = usage.plan_name or ("Free" if usage.status == "free" else None)
            renews_display = getattr(usage, "renews_display", None) or format_renews(usage.renews_at)
            renews = f" · renews {renews_display}" if renews_display else ""
            if plan:
                print()
                _cprint(f"  {_b(f'Plan: {plan}{renews}')}")
                printed_any = True

            # All lines below go through _cprint (same renderer as the Plan line) so
            # ordering is deterministic: raw print() and _cprint() flush to different
            # buffers under patch_stdout and interleave nondeterministically (the bar
            # would race above/below the Plan line across states). Keep one path.
            for _bar_ln in self._usage_bar_lines(usage, usage.plan_name):
                _cprint(_bar_ln)
                printed_any = True
            if usage.has_topup and usage.total_spendable_usd is not None:
                _cprint(f"  Total spendable: ${usage.total_spendable_usd:,.2f}")

            if usage.status == "free":
                _cprint(f"  {_d('> Free · free models only. Run /subscription to reach paid models.')}")
                printed_any = True
            elif usage.status == "low":
                _amt = f"${usage.total_spendable_usd:,.2f}" if usage.total_spendable_usd is not None else "under $5"
                _low = f"! Low balance · {_amt} left. Run /topup or /subscription."
                _cprint(f"  {_low}")
                printed_any = True

            if printed_any:
                return True

        # Fallback: legacy text lines (only when the model is unavailable).
        from agent.account_usage import nous_credits_lines

        lines = nous_credits_lines()
        if not lines:
            return False
        print()
        for line in lines:
            print(f"  {line}")
        return True
```

**然后代码大面积违反自己的规则。** AST 统计:

- `CLICommandsMixin`:17 个方法只用 `print()` 从不用 `_cprint()`,其中 `_handle_browser_command`
  有 59 处 `print()`;`_handle_tools_command`(3 print / 3 _cprint)与
  `_handle_background_command`(2 print / 11 _cprint,且在**后台线程**里打印)混用。
- `CLIBillingMixin`:31 个方法里 **18 个**同时用 `print()` 和 `_cprint()`。
  包括**写下那条规则的 `_print_nous_credits_block` 自己**(第 51 行是裸 `print()`)。

而同文件的 `_subscription_overview` 明确知道并修掉了空行问题:

`hermes_cli/cli_billing_mixin.py:196-220 @ 863e313`

```python
        # "nothing happened" — mirrors the TUI banner. All-`_cprint` (blanks
        # included) so the block orders deterministically even when piped.
        _trans = None
        if c and c.cancel_at_period_end:
            _when = format_renews(c.cancellation_effective_at) or "the end of the billing period"
            _trans = ((c.tier_name or "your plan"), "cancels", _when)
        elif c and c.pending_downgrade_tier_name:
            _when = format_renews(c.pending_downgrade_at) or "the end of the cycle"
            _trans = ((c.tier_name or "your plan"), c.pending_downgrade_tier_name, _when)
        _cprint("")
        if _trans:
            _from, _to, _when = _trans
            _cprint(f"  ⏳ {_b('Scheduled change')}")
            _cprint(f"  {_from} ──▶ {_to}  {_d('· ' + _when)}")
            _cprint(f"  {_d(f'You keep {_from} (and its credits) until then.')}")
            _cprint("")

        _cprint(f"  ⚕ {_b(status)}")
        print(f"  {'─' * 41}")

        # Two-bar dollar usage view — plan name labels the plan bar.
        for _bar_ln in self._usage_bar_lines(usage, plan_name):
            print(_bar_ln)
        if usage and getattr(usage, "has_topup", False) and getattr(usage, "total_spendable_usd", None) is not None:
            print(f"  Total spendable: ${usage.total_spendable_usd:,.2f}")
```

注意第 197 行说 "All-`_cprint` (blanks included)",而第 214/218/220 行就是裸 `print()`,
和第 205/213 行的 `_cprint` 交替 —— 这正是第 55-58 行警告的模式。

**为什么这个设计会走到这一步**:`_usage_bar_lines` 被刻意做成"返回字符串列表、由调用方自己选打印函数",
docstring 明说理由:

`hermes_cli/cli_billing_mixin.py:926-945 @ 863e313`

```python
    def _usage_bar_lines(self, usage, plan_name) -> list:
        """The plan + top-up dollar bars as ready-to-print lines (filled = remaining).

        Returns [] when there's nothing to draw. The caller resolves ``plan_name``
        (the plan-bar label) and picks its own print fn — block ordering differs
        per surface (``_cprint`` vs ``print`` under patch_stdout). One source of
        truth for the bar format across /usage, /subscription, and /topup.
        """
        lines: list = []
        pb = getattr(usage, "plan_bar", None) if usage else None
        if pb is not None and pb.total_usd > 0:
            filled = max(0, min(10, round(pb.fill_fraction * 10)))
            bar = ("█" * filled) + ("░" * (10 - filled))
            pct_s = f" · {pb.pct_used}% used" if pb.pct_used is not None else ""
            label = (plan_name or "plan").ljust(8)[:8]
            lines.append(f"  {label}[{bar}]  ${pb.remaining_usd:,.2f} left of ${pb.total_usd:,.2f}{pct_s}")
        tb = getattr(usage, "topup_bar", None) if usage else None
        if tb is not None and tb.remaining_usd > 0:
            lines.append(f"  {'top-up'.ljust(8)}[{'█' * 10}]  ${tb.remaining_usd:,.2f} · never expires")
        return lines
```

把"用哪个打印通道"做成调用方的自由度,等于把一条全局不变量降级成 31 处独立决策 —— 于是 18 处混用。
**可迁移的教训:输出通道应该是一个进程级不变量(单一 sink),不该是每个函数的参数。**

### 2.7 billing 的钱路:失败语义分得非常细,是本段最值得抄的设计

尽管有 §2.6 的显示问题,`_subscription_apply` 的错误分类是我在整个 harness 里见过最讲究的一处:

`hermes_cli/cli_billing_mixin.py:593-618 @ 863e313`

```python
        try:
            if kind == "upgrade":
                try:
                    res = post_subscription_upgrade(subscription_type_id=arg, idempotency_key=key) or {}
                except BillingScopeRequired:
                    raise  # a scope denial rejects BEFORE charging → route to the step-up
                except (BillingTransient, BillingSessionRevoked, BillingRemoteSpendingRevoked) as exc:
                    # Deterministic PRE-charge typed rejections (429 / 401 / 403) never
                    # reached Stripe → surface the CORRECT recovery (retry_after / re-login /
                    # reconnect), NOT the "maybe charged" ambiguity copy.
                    self._subscription_render_error(state, exc)
                    return
                except BillingError as exc:
                    _status = getattr(exc, "status", None)
                    _code = getattr(exc, "error", None)
                    if _code in ("network_error", "endpoint_unavailable") or _status is None or _status >= 500:
                        # Genuinely INDETERMINATE — transport / unparseable 2xx / a 5xx the
                        # server hit mid-request: NAS may have already prorated + charged.
                        # Steer to a re-check, never a blind retry (a fresh key can't dedup →
                        # a real second charge).
                        self._subscription_render_upgrade_ambiguous(exc)
                    else:
                        # A deterministic 4xx (role_required / no_payment_method / …) → the
                        # normal error copy, not "maybe charged".
                        self._subscription_render_error(state, exc)
                    return
```

三分法:**确定性拒绝(未到 Stripe)/ 不确定(可能已扣)/ scope 缺失(可就地补)**。第三类的
"不确定" 分支拒绝提示重试,理由写得很清楚:CLI 无法跨命令保留幂等键,重试等于换新 key,
新 key 无法去重 → 真的会扣两次。这是一条**只有把幂等键的生命周期想清楚才写得出来的结论**。

同理,`_billing_confirm_and_charge` 的确认框刻意把"花钱那一行"放在非默认位置:

`hermes_cli/cli_billing_mixin.py:519-524 @ 863e313`

```python
            # The money-moving row is NOT the default — a bare Enter hits "Go back",
            # so a single stray keystroke can't charge the card.
            confirm_choices = [
                ("cancel", "Go back", "do not charge"),
                ("yes", pay_label, "charge + upgrade now"),
            ]
```

而 "scheduled"(不立即扣款)分支就把 `yes` 放回第一位(`531-534`)。**默认值的位置随"这一步会不会
花钱"而变** —— 这是一个可以直接抄进任何 harness 的模式。

另一条:**不做 preflight,让服务端的 403 顺序决定用户看到哪个流程**:

`hermes_cli/cli_billing_mixin.py:1028-1032 @ 863e313`

```python
        # No card / scope preflight here — that's the rejected anti-pattern. We let
        # the charge fly and react to whatever 403 the server returns: scope first
        # (insufficient_scope → in-flight reauth), then card (no_payment_method →
        # portal handoff via _billing_render_charge_error). Mirrors the server's gate
        # order; the user only hits the flow they actually need.
```

理由是 preflight 会把服务端的门禁顺序在客户端复制一遍,两边一定会漂移。

### 2.8 `/goal`、`/heartbeat`、`/focus`:三个纯 `self` 状态的小机制

这三个是 commands mixin 里少数**不依赖 `cli.py` 兄弟方法之外还有清晰内聚**的。

- `/focus` 明确是**显示层**、并且刻意**复用**已有的 `tool_progress_mode` 抑制路径而不是新开一套:

`hermes_cli/cli_commands_mixin.py:2916-2927 @ 863e313`

```
        Focus view is a DISPLAY-ONLY mode.  It composes with the existing
        ``/verbose`` tool-progress machinery rather than adding a second
        suppression mechanism: turning it on snaps ``tool_progress_mode`` to
        ``"off"`` (the same value ``/verbose off`` uses, honoured by
        ``agent/tool_executor.py`` and ``_on_tool_progress``) after stashing
        whatever mode the user had, and turning it off restores that mode
        verbatim.  On top of that it adds the two things ``/verbose off``
        lacks: a per-turn hidden-line count with a recovery hint, and a
        persistent ``focus`` segment in the status bar.

        Nothing here touches conversation history, the system prompt, or any
        request payload — the model sees an identical turn either way.
```

而写路径被抽成 `_set_tool_progress_mode`,理由是"两个地方要写,漏掉 agent 那份就要等重建才生效":

`hermes_cli/cli_commands_mixin.py:3005-3021 @ 863e313`

```python
    def _set_tool_progress_mode(self, mode: str) -> None:
        """Set the live tool-progress mode on both the CLI and the agent.

        Extracted so ``/focus`` and ``/verbose`` share one write path — the
        agent copy is what ``agent/tool_executor.py`` gates on, and forgetting
        it means the new mode only takes effect after an agent rebuild.
        """
        from hermes_cli.focus_view import normalize_tool_progress_mode

        normalized = normalize_tool_progress_mode(mode)
        self.tool_progress_mode = normalized
        agent = getattr(self, "agent", None)
        if agent is not None:
            try:
                agent.tool_progress_mode = normalized
            except Exception:
                pass
```

- `/goal` 的 gate 概念值得记:一个 gate 是**必须通过的 shell 命令**,失败输出直接成为下一轮的
  continuation prompt(`hermes_cli/cli_commands_mixin.py:2595-2597`)。这把 "done" 从 judge 模型的主观判断
  变成了可执行的确定性检查。`/goal wait <pid>` 则是"停在一个后台进程上,直到它退出"——把
  "等 CI" 从 agent 的忙轮询变成 OS 级事件。
- `/heartbeat` 明确是**进程内、会话作用域**,并把持久化需求转介给 `hermes cron`
  (`hermes_cli/cli_commands_mixin.py:2449-2454`),避免两套调度器语义重叠。

---

## 3. 可疑缺陷清单

> 每条:现象 / 锚点 / 为什么可疑 / 触发条件 / 置信度。

### 缺陷 1 —— `/background` 绕过 `disabled_toolsets`,后台 agent 能用被用户禁用的工具

**现象**:配置里 `agent.disabled_toolsets: [...]`(或 `hermes-*` 平台包的减法)对 `/background`
派生的 agent 完全不生效。

**锚点**:`hermes_cli/cli_commands_mixin.py:1996 @ 863e313`

```python
                    enabled_toolsets=self.enabled_toolsets,
```

对照 `hermes_cli/cli_agent_setup_mixin.py:479-480 @ 863e313`

```python
                enabled_toolsets=self.enabled_toolsets,
                disabled_toolsets=self.disabled_toolsets,
```

**为什么可疑**:`disabled_toolsets` 在 `model_tools.py` 里是**最后一步无条件减法**,即使
`enabled_toolsets` 已给出白名单也照减 —— 注释写得很明确:

`model_tools.py:434-438 @ 863e313`

```python
    # Always apply disabled toolsets as a subtraction step at the end.
    # This ensures that even if a composite toolset (like hermes-cli)
    # is enabled, any tools belonging to a disabled toolset are strictly
    # stripped out. See issue #17309.
    if disabled_toolsets:
```

不传它 = 不做这一步减法。这是**安全语义的静默放宽**:用户禁用某个工具集的动机通常正是"别让它碰这个"。

**触发条件**:配置里有非空 `agent.disabled_toolsets`,且用户跑了 `/background <prompt>`。

**置信度**:**高**(两处构造点的 kwarg 差异是 AST 精确对比得到的;减法语义有源码注释背书)。

---

### 缺陷 2 —— `/background` 会在前台 turn 运行中把 `self.agent` 置 None(Entra ID 下必然触发)

**现象**:前台 agent 正在跑,用户敲 `/background ...`,前台的 `self.agent` 被清空。

**锚点**:`hermes_cli/cli_commands_mixin.py:1967-1970 @ 863e313`

```python
        # Make sure we have valid credentials
        if not self._ensure_runtime_credentials():
            _cprint("  (>_<) Cannot start background task: no valid credentials.")
            return
```

`hermes_cli/cli_agent_setup_mixin.py:181-183 @ 863e313`

```python
        if (credentials_changed or routing_changed or model_changed) and self.agent is not None:
            self.agent = None
            self._active_agent_route_signature = None
```

**为什么可疑**:`/background` 是**故意**在 agent 运行时从 prompt_toolkit UI 线程直接派发的,
而 `process_loop` 线程此刻正阻塞在 `self.chat()` 里:

`cli.py:9681-9684 @ 863e313`

```python
        if not text or has_images or not _looks_like_slash_command(text):
            return False
        if not getattr(self, "_agent_running", False):
            return False
```

且该函数的 docstring 明确承诺 "leaves the foreground turn running untouched: no interrupt, no steer"
(`cli.py:9677-9679`)。但 `_ensure_runtime_credentials` 会改写 `self.provider / api_mode /
acp_command / acp_args / _credential_pool / _provider_source / api_key / base_url`,可能改写
`self.model / requested_provider`,并可能把 `self.agent` 置 None —— 全部发生在另一个线程正在用
`self.agent` 的时候。**"untouched" 的承诺与实现不符。**

对 Azure Entra ID 用户是**必然**触发:`credentials_changed = api_key != self.api_key`
(`hermes_cli/cli_agent_setup_mixin.py:127`)对 callable 是对象身份比较,而
`hermes_cli/runtime_provider.py:1437` 每次都新建 provider:

`hermes_cli/runtime_provider.py:1437 @ 863e313`

```python
                token_provider = build_token_provider(config=entra_config)
```

`agent/azure_identity_adapter.py:252-253 @ 863e313`

```python
    credential = build_credential(config)
    return ai.get_bearer_token_provider(credential, config.scope)
```

每次返回新对象 → `credentials_changed` 恒 True。

**触发条件**:(a) Entra ID provider + 运行中敲 `/background`(必然);(b) 任意 provider + 密钥
在两次解析之间真的轮换过 + 运行中敲 `/background`。

**置信度**:**高**(代码路径确定;实际崩溃形态取决于 `chat()` 里对 `self.agent` 的读取时序,
这部分我没有精读,故对"具体表现为什么异常"保持中)。

---

### 缺陷 3 —— 三个 handler 的 `shlex.split` 没有 `ValueError` 兜底,引号不配对时**静默无动作**

**现象**:`/cron add "check server`(引号没闭)—— 没有报错、没有用法提示,什么都不发生。

**锚点(缺兜底)**:`hermes_cli/cli_commands_mixin.py:1574-1576 @ 863e313`

```python
        tokens = shlex.split(cmd)

        if len(tokens) == 1:
```

`hermes_cli/cli_commands_mixin.py:1804-1808 @ 863e313`

```python
        import shlex

        tokens = shlex.split(cmd)[1:] if cmd else []
        if not tokens:
            tokens = ["status"]
```

`hermes_cli/cli_commands_mixin.py:556-562 @ 863e313`

```python
        register_cli(parser)
        rest = cmd_original.split(None, 1)
        try:
            args = parser.parse_args(shlex.split(rest[1]) if len(rest) > 1 else [])
        except SystemExit:
            return

```

(第三处的 `try` 只捕 `SystemExit`,`shlex.split` 抛的是 `ValueError`,不在捕获范围。)

**对照(有兜底,同一文件)**:`hermes_cli/cli_commands_mixin.py:156-162 @ 863e313`

```python
        import shlex

        try:
            parts = shlex.split(command)[1:]  # preserves quoted paths
        except ValueError:
            parts = command.split()[1:]

```

`hermes_cli/cli_commands_mixin.py:731-735 @ 863e313`

```python
        try:
            parts = shlex.split(cmd)
        except ValueError:
            parts = cmd.split()

```

**为什么可疑**:异常一路冒到 `process_loop` 的兜底 handler,只写日志、不打屏:

`cli.py:17589-17590 @ 863e313`

```python
                except Exception as e:
                    logger.warning("process_loop unhandled error (msg may be lost): %s", e)
```

主交互路径的 `process_command` 调用只捕 `KeyboardInterrupt`(`cli.py:17473-17480`),
不捕 `Exception`。所以用户看到的就是"命令石沉大海"。同一文件里 4 个 handler 做了兜底、3 个没做,
是典型的复制粘贴漂移。

**触发条件**:`/cron`、`/curator`、`/journey` 的参数里出现不配对的引号或反斜杠。

**置信度**:**高**。

---

### 缺陷 4 —— `/browser status` 硬编码探测 `127.0.0.1` + `AF_INET`,与 `connect` 的双栈发现自相矛盾

**现象**:`/browser connect ws://10.0.0.5:9222` 成功后,`/browser status` 报
"⚠ not reachable"。或者浏览器只监听 `[::1]` 时(**正是 connect 路径专门加固过的场景**),
status 同样误报不可达。

**锚点**:`hermes_cli/cli_commands_mixin.py:2313-2333 @ 863e313`

```python
        elif sub == "status":
            print()
            if current:
                print("🌐 Browser: connected to live Chromium-family browser via CDP")
                print(f"   Endpoint: {current}")

                _port = 9222
                try:
                    _port = int(current.rsplit(":", 1)[-1].split("/")[0])
                except (ValueError, IndexError):
                    pass
                try:
                    import socket
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(1)
                    s.connect(("127.0.0.1", _port))
                    s.close()
                    print("   Status: ✓ reachable")
                except (OSError, Exception):
                    print("   Status: ⚠ not reachable (browser may not be running)")
            else:
```

**对照**:同一 handler 的 connect 分支为了 IPv6 专门用了 `discover_local_cdp_url`:

`hermes_cli/cli_commands_mixin.py:2197-2211 @ 863e313`

```python

            # Check if a Chromium-family browser is already serving CDP on the debug port.
            # For the default-local URL, probe both loopbacks (IPv4 + IPv6): a
            # squatter on 127.0.0.1:<port> (e.g. an IDE's JS debugger) can push
            # the debug browser to bind [::1] only.
            _is_default = cdp_url == _DEFAULT_CDP
            if _is_default:
                _found = discover_local_cdp_url(_port, timeout=1.0)
                _already_open = _found is not None
                if _found:
                    cdp_url = _found
            else:
                _already_open = is_browser_debug_ready(cdp_url, timeout=1.0)

            if _already_open:
```

**为什么可疑**:connect 明确支持远程主机(解析 `parsed_cdp.hostname`,`2172-2177`)且专门处理
IPv6-only 情形;status 却丢掉主机名、只连 `127.0.0.1`,且只建 `AF_INET` 套接字。两条路径对
"什么算连上了" 的定义不一致。附带小问题:`except (OSError, Exception)` 里 `OSError` 是
`Exception` 子类,写法冗余,说明这段是随手加的。

**触发条件**:CDP 端点不是 IPv4 loopback(远程主机、容器、或 IPv6-only 的调试实例)。

**置信度**:**高**(纯静态可判)。

---

### 缺陷 5 —— `_print_nous_credits_block` 的 "Total spendable" 行不计入 `printed_any`,可导致重复渲染

**现象**:`/usage` 先打印 "Total spendable: $X",紧接着又打印一整块 legacy 文本。

**锚点**:`hermes_cli/cli_billing_mixin.py:62-63 @ 863e313`

```python
            if usage.has_topup and usage.total_spendable_usd is not None:
                _cprint(f"  Total spendable: ${usage.total_spendable_usd:,.2f}")
```

(上下文与 fallback 见 §2.6 引用的 45-86 全段:`74-75` 是 `if printed_any: return True`,
`77-86` 是 legacy 回退。)

**为什么可疑**:该分支**打印了**却不置 `printed_any = True`。若同一次调用里 `plan` 为空、
`_usage_bar_lines` 返回 `[]`、`status` 既不是 `free` 也不是 `low`,则 `printed_any` 仍为 `False`,
函数继续往下走进 legacy 回退并再打一遍。注释第 77 行写 "only when the model is unavailable",
但控制流实际是 "model 可用但这一次没打印出足够东西" 也会走进来 —— 注释与代码不一致。

**触发条件**:`usage.available == True`、`plan_name` 为空、`status` 为 `ok`(非 free/low)、
`plan_bar` 为空或 `total_usd <= 0`、`topup_bar` 为空或 `remaining_usd <= 0`,但 `has_topup` 为真
且 `total_spendable_usd` 非空。窄,但不是不可达(`has_topup` 由 `topup_remaining_usd > 0` 决定,
而 `topup_bar` 的构造在 `agent/billing_usage.py:200-205` 另有条件)。

**置信度**:**中**(控制流缺陷确定;能否真实构造出该状态取决于 `build_usage_model` 的字段组合,
我没有穷举)。

---

### 缺陷 6 —— `_subscription_overview` 的 `format_renews` 导入在 try 之外,破坏了 `/subscription` 的 fail-open 承诺

**现象**:`agent.billing_usage` 模块不可导入时,`/subscription` 抛异常(静默无输出,见缺陷 3 的
兜底路径),而不是降级成一条清晰提示。

**锚点**:`hermes_cli/cli_billing_mixin.py:155-165 @ 863e313`

```python
        from cli import _cprint, _b, _d

        # Shared dollar usage model (the only source with top-up dollars).
        from agent.billing_usage import format_renews
        try:
            from agent.billing_usage import build_usage_model

            usage = build_usage_model()
        except Exception:
            usage = None

```

**为什么可疑**:两个符号来自**同一个模块**,一个在 `try` 外一个在 `try` 内。若模块本身导入失败
(依赖缺失、语法错误),第 158 行先炸,`try` 形同虚设。而 `_show_subscription` 的 docstring 明确承诺:

`hermes_cli/cli_billing_mixin.py:109-111 @ 863e313`

```
        page (NOT the Stripe portal; that page routes upgrade→Checkout /
        downgrade→scheduled internally). The terminal NEVER charges for a
        subscription. Fail-open: logged-out / portal hiccup degrades to a clear
```

对照 `_print_nous_credits_block:37-43` 把两个符号**一起**包进 `try`(并在 `except` 里把
`format_renews` 设为 `None`),说明作者在另一处是想到了的。

**触发条件**:`agent.billing_usage` 导入失败(部分安装、可选依赖缺失、平台裁剪构建)。

**置信度**:**高**(结构性;触发前提较窄)。

---

### 缺陷 7 —— 自动充值(auto-reload)遇到 scope 缺失后,用户输入的两个金额被静默丢弃

**现象**:`/topup → Auto-reload → 输入阈值和补足额 → 同意` → 弹出 "Allow Remote Spending" →
授权成功 → 打印 "✓ Remote Spending allowed. Run /topup to continue." → **auto-reload 仍然是关的**,
刚才输入的两个金额没了,必须从头再走一遍。

**锚点**:`hermes_cli/cli_billing_mixin.py:1506-1512 @ 863e313`

```python
        try:
            patch_auto_top_up(
                enabled=True, threshold=float(threshold_amt), top_up_amount=float(reload_amt)
            )
        except BillingScopeRequired:
            self._billing_handle_scope_required(state)
            return
```

`hermes_cli/cli_billing_mixin.py:1333-1337 @ 863e313`

```python
        # Nothing to resume (scope-required hit outside a charge, e.g. auto-reload
        # config) → just tell the user it's ready.
        if amount is None:
            print("  ✓ Remote Spending allowed. Run /topup to continue.")
            return
```

**为什么可疑**:同一个 step-up 机制对**一次性充值**做了完整的"持有金额 + 复用幂等键 + 按 Enter 续做"
(`_billing_handle_scope_required` 的 `amount` / `idempotency_key` 参数,`1339-1372`),
对 auto-reload 却什么都不持有。注释承认了这是已知缺口,但用户视角就是白填一遍表单。
`_subscription_handle_scope_required` 则用 `retry=(kind, arg)` 元组解决了同类问题
(`656-717`)—— 三处同源需求,三种做法。

**触发条件**:首次在终端配置 auto-reload 且尚未授予 Remote Spending scope(即**第一次配置的人
必然遇到**)。

**置信度**:**高**。

---

### 缺陷 8 —— `/background` 里 `_ensure_runtime_credentials` 的 fallback 降级会永久改写**前台**会话的 model

**现象**:前台正在用 `model-A`;`/background` 时主 provider 恰好认证失败,fallback 生效 →
此后**前台**也变成 fallback 模型,且不会回升。

**锚点**:`hermes_cli/cli_agent_setup_mixin.py:73-77 @ 863e313`

```python
                        _cprint(f"⚠️  Primary auth failed — switching to fallback: {_fb_provider} / {_fb_model}")
                        self.requested_provider = _fb_provider
                        self.model = _fb_model
                        _primary_exc = None
                        break
```

**为什么可疑**:`self.model` / `self.requested_provider` 是**会话级**状态,却被一次**后台任务的**
凭据解析改写。而且改写 `requested_provider` 之后,下一次 `resolve_runtime_provider(requested=...)`
拿到的就是 fallback,主 provider 恢复后也不会自动切回 —— 没有任何"回升"路径。用户只看到一行
`⚠️ Primary auth failed`(而且这行走 `_cprint`,在后台线程输出,很可能被前台流式输出淹没)。

**触发条件**:配置了 `fallback_model` 链 + 主 provider 抛 `AuthError`(令牌过期、429 被包装成
AuthError 等)+ 触发了任一 `_ensure_runtime_credentials` 调用点。

**置信度**:**中高**(改写是确定的;"不会回升" 依赖 `resolve_runtime_provider` 对 `requested` 的
处理,我按参数名推断,未逐行读该函数)。

---

### 缺陷 9 —— `_compose_in_editor` 的兜底分支把 `$EDITOR` 交给 shell 执行

**现象**:`/prompt` 在 `subprocess.call([...])` 抛异常时,改用 `shell=True` 重跑。

**锚点**:`hermes_cli/cli_commands_mixin.py:2835-2870 @ 863e313`

```python
    def _compose_in_editor(self, initial_text: str = "") -> str:
        """Open ``$VISUAL``/``$EDITOR`` on a temp markdown file and return the
        saved buffer (comment lines starting with ``#!`` stripped).

        Returns the composed prompt text, or an empty string if the editor
        could not be launched or the buffer was left empty. Factored out so
        the read-back/strip logic is unit-testable without spawning an editor.
        """
        import os
        import shlex
        import subprocess
        import tempfile

        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if not editor:
            editor = "notepad" if os.name == "nt" else "nano"

        header = (
            "#! Compose your prompt below. Lines starting with '#!' are ignored.\n"
            "#! Save and quit to send; leave empty to cancel.\n\n"
        )
        fd, path = tempfile.mkstemp(suffix=".md", prefix="hermes_prompt_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(header)
                if initial_text:
                    fh.write(initial_text)
            try:
                subprocess.call([*shlex.split(editor), path])
            except Exception:
                # Fall back to a bare invocation (editor value may not be a
                # simple argv-splittable string on some platforms).
                subprocess.call(f"{editor} {shlex.quote(path)}", shell=True)
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read()
        finally:
```

**为什么可疑**:`path` 被 `shlex.quote` 保护了,但 `editor` 本身**原样拼进 shell 命令**。
`$EDITOR` 通常由用户自己设置(信任边界内),但在 agent harness 语境里,环境变量并不总是"用户手打"的
—— agent 自己能改环境、能写 shell rc、能通过 `execute_code` 设置变量。这条路径把
"环境变量" 提升成了 "任意 shell 执行"。而且第一次 `subprocess.call` 用列表形式**不会**因为
"命令不存在" 之外的原因抛异常(退出码非 0 是返回值不是异常),所以兜底几乎只在
`FileNotFoundError` / `shlex.split` 抛 `ValueError` 时触发 —— 后者恰好是 `$EDITOR` 里有不配对引号,
也就是最可能被构造的输入。

**触发条件**:`$VISUAL`/`$EDITOR` 含不配对引号或指向不存在的可执行文件,且用户跑 `/prompt`。

**置信度**:**中**(是设计气味 + 边界模糊,不是可直接利用的漏洞)。

---

### 缺陷 10 —— `/resume` 与 `/branch` 的 7 步切换协议手抄两份

**现象**:两个 handler 各有一份几乎逐行相同的 agent 同步块。

**锚点**:`hermes_cli/cli_commands_mixin.py:1082-1110 @ 863e313`(`/resume`)

```python
        if self.agent:
            self.agent.session_id = target_id
            self.agent.reset_session_state()
            if hasattr(self.agent, "_last_flushed_db_idx"):
                self.agent._last_flushed_db_idx = len(self.conversation_history)
            if hasattr(self.agent, "_todo_store"):
                try:
                    from tools.todo_tool import TodoStore
                    self.agent._todo_store = TodoStore()
                except Exception:
                    pass
            if hasattr(self.agent, "_invalidate_system_prompt"):
                self.agent._invalidate_system_prompt()

            # Notify memory providers that session_id rotated to a resumed
            # session. reset=False — the provider's accumulated state is
            # still valid; it just needs to target the new session_id for
            # subsequent writes. See #6672.
            try:
                _mm = getattr(self.agent, "_memory_manager", None)
                if _mm is not None:
                    _mm.on_session_switch(
                        target_id,
                        parent_session_id=old_session_id or "",
                        reset=False,
                        reason="resume",
                    )
            except Exception:
                pass
```

`hermes_cli/cli_commands_mixin.py:1290-1319 @ 863e313`(`/branch`)

```python
        if self.agent:
            self.agent.session_id = new_session_id
            self.agent.session_start = now
            self.agent.reset_session_state()
            if hasattr(self.agent, "_last_flushed_db_idx"):
                self.agent._last_flushed_db_idx = len(self.conversation_history)
            if hasattr(self.agent, "_todo_store"):
                try:
                    from tools.todo_tool import TodoStore
                    self.agent._todo_store = TodoStore()
                except Exception:
                    pass
            if hasattr(self.agent, "_invalidate_system_prompt"):
                self.agent._invalidate_system_prompt()

            # Notify memory providers that session_id forked to a new branch.
            # reset=False — the branched session carries the transcript
            # forward, so provider state tracks the lineage. parent_session_id
            # links the branch back to the original. See #6672.
            try:
                _mm = getattr(self.agent, "_memory_manager", None)
                if _mm is not None:
                    _mm.on_session_switch(
                        new_session_id,
                        parent_session_id=parent_session_id or "",
                        reset=False,
                        reason="branch",
                    )
            except Exception:
                pass
```

**为什么可疑**:两份唯一实质差异是 `session_start` 与 `reason`。**已经有一处漂移**:
`/branch` 之后调 `self._transfer_session_yolo(old, new)`(`1282`),`/resume` 之后调
`self._restore_session_yolo(session_meta)`(`1136`);`/resume` 还调了
`self._restore_session_cwd(session_meta)`(`1130`),`/branch` **完全没有 cwd 处理**。
是有意还是遗漏,代码里没有任何注释说明 —— 而 `/resume` 那处的注释(`1124-1129`)专门解释了
"没有它,terminal/code-exec 工具会留在错的仓库里"(#38562),同样的道理对 `/branch` 应当成立
(branch 出的会话应该继承父会话 cwd,而不是继承进程当前 cwd)。

**触发条件**:任何时候往这套协议里加字段。cwd 差异则在 `/branch` 于非会话原目录执行时显现。

**置信度**:重复本身**高**;cwd 缺失是不是 bug —— **中**(可能是"branch 不换目录所以不用恢复",
但 `/branch` 之前若发生过 `/resume`,cwd 已经被改过,语义就不清了)。

---

### 缺陷 11 —— `/goal` 踢循环失败被静默吞掉

**现象**:`/goal <text>` 打印 "⊙ Goal set (N-turn budget): ...",然后什么都不发生。

**锚点**:见 §2.2 引用的 `hermes_cli/cli_commands_mixin.py:2664-2669`(以及 `_handle_goal_draft` 的同款
`2711-2714`)。

**为什么可疑**:`except Exception: pass` 覆盖了 `AttributeError`(`_pending_input` 不存在)、
`queue.Full` 等所有情况,并且没有任何提示。同一文件里 `/learn` 和 `/init` 对同一个属性用了
`hasattr` + 明确的用户提示(`1883-1887`)。三个 handler、两种处理、一种给提示一种不给。

**触发条件**:非 `HermesCLI` 宿主(Desktop GUI / 测试 stub / 未来的其它 surface),或队列异常。

**置信度**:**中**(在标准 CLI 里 `_pending_input` 恒存在,所以是潜在缺陷而非现行缺陷)。

---

### 缺陷 12 —— `_subscription_pick_tier` 缺少 `_subscription_free_catalog` 才有的数字选择垫片

**现象**:确认弹窗降级到裸 stdin 时(无 `self._app`、事件循环取不到、或调度失败,见
`cli.py:8698-8699` 与 `cli.py:8709-8710`),在"Start a subscription"里输入 `1` 能选中第一档,
在"Change plan"里输入 `1` 会被判为取消。

**锚点(有垫片)**:`hermes_cli/cli_billing_mixin.py:326-340 @ 863e313`

```python
        raw = self._prompt_text_input_modal(
            title="Start a subscription",
            detail="Pick a plan to open it on the portal.",
            choices=choices,
        )
        # The rows are printed numbered, so accept a bare number as a pick (the
        # shared normalizer only knows the confirm-dialog digit aliases).
        _digit = (raw or "").strip()
        if _digit.isdigit() and 1 <= int(_digit) <= len(tiers):
            choice = tiers[int(_digit) - 1].tier_id
        else:
            choice = self._normalize_slash_confirm_choice(raw, choices)
        if not choice or choice == "cancel":
            print("  🟡 Cancelled. No plan started.")
            return
```

**锚点(无垫片)**:`hermes_cli/cli_billing_mixin.py:438-446 @ 863e313`

```python
        raw = self._prompt_text_input_modal(
            title="Change plan",
            detail=f"Current: {c.tier_name if c else 'Free'}. Pick a plan to preview the effect.",
            choices=choices,
        )
        choice = self._normalize_slash_confirm_choice(raw, choices)
        if not choice or choice == "cancel":
            print("  🟡 Cancelled. No plan change.")
            return
```

**为什么可疑**:`_normalize_slash_confirm_choice` 用的是**硬编码别名表**,不索引 `choices`:

`cli.py:8812-8827 @ 863e313`

```python
        aliases = {
            "1": "once",
            "once": "once",
            "approve": "once",
            "yes": "once",
            "y": "once",
            "ok": "once",
            "2": "always",
            "always": "always",
            "remember": "always",
            "3": "cancel",
            "cancel": "cancel",
            "nevermind": "cancel",
            "no": "cancel",
            "n": "cancel",
        }
```

而弹窗渲染出的行是 `[1] … [2] …`,并明确告诉用户 "Type 1/2/3":

`cli.py:8878 @ 863e313`

```python
        preview_lines.append("Type 1/2/3 or use ↑/↓ then Enter. ESC/Ctrl+C cancels.")
```

活的 TUI 里另有按键绑定按 `choices[idx][0]` 正确索引(`cli.py:15854-15866`),所以主路径没问题
—— **裸 stdin 降级路径没有那套按键绑定**,只剩别名表。垫片那处的注释("the shared normalizer only
knows the confirm-dialog digit aliases")说明作者知道这个问题,但只修了一处。

**触发条件**:确认弹窗走到 `_prompt_text_input` 降级(`cli.py:8709-8710` 或 `8714` 的调度失败分支),
且用户按提示输入数字选档位。

**置信度**:**中**(失败方向是"取消",不会误扣钱;主要是两处不一致 + 提示文案与实现在降级路径下不符)。

---

### 缺陷 13 —— lazy `from cli import` 使 `cli` 的模块级副作用被推迟到 handler 执行中

**现象**:在一个从未 `import cli` 的宿主里调用任一 mixin handler,会在 handler 中途:
重配根 logger、把配置警告打到 stdout、改写 `os.environ`、猴补 `httpx` 与 `SkinConfig`,
并在 tty 下向终端写 OSC/DSR 查询序列。

**锚点**:见 §0.1(b) 的表格与 `cli.py:2784-2790` 引用。相关 handler 侧锚点:
`hermes_cli/cli_commands_mixin.py:3185 @ 863e313`

```python
        from cli import CLI_CONFIG, _ACCENT, _DIM, _RST, _cprint, _parse_reasoning_config, save_config_value
```

**为什么可疑**:拆分前这些副作用必然发生在进程启动期;拆分后,它们的发生时机变成"第一次调用某个
handler"。测试里已经出现了 `CLICommandsMixin.__new__(...)` 这种宿主(`tests/tools/test_write_approval.py:98`),
只要那条用例走到任何一个含 `from cli import` 的分支,就会在测试中途把 pytest 的 logging 配置冲掉。

**触发条件**:任何 "先用 mixin、后 import cli" 的宿主。当前仓库里主要是测试与假想的新 surface。

**置信度**:**中**(机制确定;是否已造成实际故障未证实)。

---

### 缺陷 14 —— `_resume_display_history` 不在 `__init__` 里,靠"写点支配读点"存活

**现象**:见 §0.1 前提 2 层面一。`hermes_cli/cli_commands_mixin.py:1113` 是裸读。

**锚点**:`hermes_cli/cli_commands_mixin.py:1112-1114 @ 863e313`

```python
        title_part = f" \"{session_meta['title']}\"" if session_meta.get("title") else ""
        msg_count = len([m for m in self._resume_display_history if m.get("role") == "user" and not m.get("display_kind")])
        if self.conversation_history:
```

**为什么可疑**:161 个属性都在 `__init__` 里,唯独这一个不是,而且 `_display_resumed_history`
自己用 `getattr(..., self.conversation_history)` 兜底(`hermes_cli/cli_agent_setup_mixin.py:676`),
说明作者知道它可能缺席。裸读点只靠同函数上游第 1071 行的赋值支配。任何一次在 1071 之前 `return`
的重构都会引入 `AttributeError`。

**触发条件**:重构 `_handle_resume_command` 的早退路径。

**置信度**:**中**(当前不可触发,是脆弱性而非缺陷)。

---

## 4. 与文档/注释的出入

| # | 文档/注释断言 | 锚点 | 代码事实 | 裁定 |
|---|---|---|---|---|
| ▲1 | "behavior-neutral" | `hermes_cli/cli_commands_mixin.py:5`、`hermes_cli/cli_agent_setup_mixin.py:8` | 同文件 `hermes_cli/cli_agent_setup_mixin.py:520-528` 记录了拆分导致的线上缺陷 #49287 | **以代码为准**:拆分非行为中性 |
| ▲2 | "cli.py-internal symbols … imported LAZILY inside **each** handler" | `hermes_cli/cli_commands_mixin.py:9-12` | 59 个方法里只有 36 个含 `from cli import`;23 个完全不碰 `cli` | **以代码为准**:是"部分 handler",不是"每个" |
| ▲3 | "All methods use only ``self`` state plus the imports above and per-method lazy ``from cli import ...``" | `hermes_cli/cli_commands_mixin.py:46-48` | 还调用 35 个仍在 `cli.py` 的兄弟方法;并直接 import 了 `tools.*`、`hermes_cli.*`、`agent.*` 等数十个模块 | **以代码为准**:依赖面远大于描述 |
| ▲4 | "All lines below go through _cprint … Keep one path." | `hermes_cli/cli_billing_mixin.py:55-58` | 同函数第 51、83、85 行是裸 `print()`;全文件 31 个方法里 18 个混用 | **以代码为准**:规则未被遵守 |
| ▲5 | "All-`_cprint` (blanks included) so the block orders deterministically even when piped." | `hermes_cli/cli_billing_mixin.py:196-197` | 紧邻的 214、218、220 行就是裸 `print()` | **以代码为准**:注释描述的是它上面那一小段,不是整块;措辞误导 |
| ▲6 | "Fallback: legacy text lines (**only when the model is unavailable**)." | `hermes_cli/cli_billing_mixin.py:77` | model 可用但 `printed_any` 为假时也会进入(缺陷 5) | **以代码为准** |
| ▲7 | "`Fail-open`: logged-out / portal hiccup degrades to a clear message, never a crash." | `hermes_cli/cli_billing_mixin.py:109-111` | `hermes_cli/cli_billing_mixin.py:158` 的 `format_renews` 导入在 try 之外(缺陷 6) | **以代码为准**:存在会 crash 的路径 |
| ▲8 | "leaves the foreground turn running untouched: no interrupt, no steer." | `cli.py:9677-9679` | `/background` 里 `_ensure_runtime_credentials()` 改写 ~10 个 `self` 字段并可能置 `self.agent = None`(缺陷 2) | **以代码为准** |
| ▲9 | "Type 1/2/3 or use ↑/↓ then Enter." | `cli.py:8878` | 降级到裸 stdin 时,数字由硬编码别名表解释,与实际 `choices` 不对应(缺陷 12) | **以代码为准**(仅降级路径) |
| ◇1 | `_billing_render_charge_error` 同时看 `.error` 与 `.code` | `hermes_cli/cli_billing_mixin.py:1241-1242` | `nous_billing.BillingError` 确实同时携带二者(dual-emitted) | **文档/代码一致**,我的初判错误,已撤回 |
| ◇2 | `_usage_bar_lines` 的 `pb.total_usd > 0` 可能 `TypeError` | `hermes_cli/cli_billing_mixin.py:936` | `UsageBar.total_usd: float` 非 Optional | **无问题**,已撤回 |
| ◇3 | 顶层 import 与方法内 import 重复 | `hermes_cli/cli_commands_mixin.py:30` vs `292`;`:18` vs `2843`;`:21` vs `913` | `display_hermes_home`、`os`、`time` 各被顶层与方法内重复导入 | **无害冗余**,但佐证"逐字搬迁 + 事后补顶层 import,没有去重" |

补充说明 ◇3 的证据:

`hermes_cli/cli_commands_mixin.py:288-293 @ 863e313`

```python
        from hermes_cli.backup import (
            create_quick_snapshot, list_quick_snapshots,
            restore_quick_snapshot, prune_quick_snapshots,
        )
        from hermes_constants import display_hermes_home

```

而 `display_hermes_home` 已在 `hermes_cli/cli_commands_mixin.py:30` 顶层导入(见 §1.3 的顶层 import 引用)。
同类:`_compose_in_editor` 第 2843 行 `import os`(顶层第 18 行已有);`_handle_handoff_command`
第 913 行 `import time as _time`(顶层第 21 行已有 `import time`)。

---

## 5. 移交

### 5.1 复核脚本(可复算)

```bash
# 1) 属性差集:__init__ 设过的 vs mixin 读到的
python3 - <<'EOF'
import ast
from collections import defaultdict
FILES = ['hermes_cli/cli_commands_mixin.py','hermes_cli/cli_billing_mixin.py',
         'hermes_cli/cli_agent_setup_mixin.py']
reads=defaultdict(list); mixin_methods=set()
for p in FILES:
    t=ast.parse(open(p).read())
    for cd in t.body:
        if isinstance(cd,ast.ClassDef):
            mixin_methods |= {f.name for f in cd.body if isinstance(f,ast.FunctionDef)}
    for n in ast.walk(t):
        if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) \
           and n.value.id=='self' and isinstance(n.ctx,ast.Load):
            reads[n.attr].append((p,n.lineno))
t=ast.parse(open('cli.py').read())
cls=[n for n in ast.walk(t) if isinstance(n,ast.ClassDef) and n.name=='HermesCLI'][0]
cli_methods={f.name for f in cls.body if isinstance(f,ast.FunctionDef)}
init=[f for f in cls.body if isinstance(f,ast.FunctionDef) and f.name=='__init__'][0]
init_attrs={n.attr for n in ast.walk(init)
            if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name)
            and n.value.id=='self' and isinstance(n.ctx,ast.Store)}
print(sorted(a for a in reads if a not in (init_attrs|cli_methods|mixin_methods)))
EOF
# 期望输出: ['_resume_display_history']

# 2) 两条 AIAgent 构造路径的 kwarg 差集 → 期望 24 个单向缺失
# 3) print()/_cprint() 混用统计 → 期望 billing 18/31 混用
```

### 5.2 锚点复核结果

复核脚本(对本文自身运行,可复算):

```bash
python3 - <<'EOF'
import re, os
lines = open('notes/r8b-raw-mixins.md').read().splitlines()
anchor = re.compile(r'`([A-Za-z0-9_./]+\.py):(\d+)(?:-(\d+))?\s*@ 863e313`')
checked = 0; bad = []
i = 0
while i < len(lines):
    m = anchor.search(lines[i])
    if not m: i += 1; continue
    path, a = m.group(1), int(m.group(2))
    b = int(m.group(3)) if m.group(3) else None
    j = i + 1
    FENCE = chr(96) * 3          # avoid a literal fence inside this fenced block
    while j < len(lines) and j <= i + 4 and not lines[j].startswith(FENCE): j += 1
    if j >= len(lines) or not lines[j].startswith(FENCE): i += 1; continue
    k = j + 1; body = []
    while k < len(lines) and not lines[k].startswith(FENCE): body.append(lines[k]); k += 1
    src = open(os.path.join('/home/user/hermes-agent', path)).read().splitlines()
    end = b if b else a + len(body) - 1
    exp = src[a-1:end]
    checked += 1
    if exp != body: bad.append((path, a, end))
    i = k + 1
print('checked:', checked, 'mismatches:', len(bad), bad)
EOF
```

- **带代码块的锚点:73 个。累计 15 个不一致,已全部修正;最终一轮 0 个不一致。**
- **不带代码块的行内锚点:抽查 27 个,6 个行号收紧(见 §0.2)。**
- 另有 3 处结论在写作中被自我推翻(§0.3),已从缺陷清单移除,避免假阳性。

### 5.3 给下一轮 / 给成品章的提炼

**留给 R8 成品章的四条可迁移原则:**

1. **"逐字搬迁 ≠ 行为中性"。** Python 里至少三类构造会随模块位置改变语义:`global`(绑定定义所在
   模块)、相对/延迟 import 的解析时机、模块级副作用的执行时机。#49287 是第一类的教科书案例
   (`hermes_cli/cli_agent_setup_mixin.py:520-528`)。做 god-file 拆分时,这三类必须逐个 grep,不能靠 diff 为空
   就宣布中性。
2. **输出通道必须是进程级不变量。** `_usage_bar_lines` 把"用 `print` 还是 `_cprint`"下放成调用方
   自由度,直接导致 31 个方法里 18 个混用、且写规则的那个函数自己就违反规则。正确做法是一个
   sink,不给选择。
3. **同一个能力只能有一条构造路径。** `/background` 的第二条 `AIAgent(...)` 少了 24 个 kwarg,
   其中 6 个是用户显式表达的**约束**(禁用工具集、忽略规则、checkpoint)。任何"再来一条快捷路径"
   都应该是对唯一构造函数的**参数覆写**,不是重写参数列表。
4. **"钱路"的失败必须三分:确定性拒绝 / 不确定 / 可就地修复。** `_subscription_apply:593-618`
   是本仓库里最值得抄的一段,尤其是"不确定 → 引导复查而非重试"的推理(幂等键无法跨命令保留)。

**留给后续轮次的未完事项(本段没做的):**

- `cli.py` 里那 35 个被 mixin 反向调用的兄弟方法,本段只列了名字,没有精读。特别是
  `_prompt_text_input_modal` / `_normalize_slash_confirm_choice` / `_restore_session_yolo` /
  `_transfer_session_yolo`,它们承载了审批与安全语义,值得单列。
- `hermes_cli/nous_billing.py`(HTTP 层、token 缓存、异常类型体系)本段只按需查了 `BillingError`
  的字段,未通读。缺陷 6/7 的确切爆炸半径需要它。
- 缺陷 2 的"具体表现为何种异常"需要精读 `HermesCLI.chat()` 对 `self.agent` 的读取时序。
- `agent/billing_usage.py` 的 `build_usage_model` 字段组合空间,用于坐实缺陷 5 是否可达。
