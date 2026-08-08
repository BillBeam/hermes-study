# r8b-raw-cli-init-render —— cli.py 4205-7300(构造与渲染)

> 底稿定位：证据层。求全求证，不求好读。
> 溯源约定：凡对 hermes-agent 行为的断言，紧跟 `路径:行号 @ 863e313` 与代码原文块。
> 基线：`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`，**只读**；
> 开工前与收工后 `git -C /home/user/hermes-agent status --porcelain` 均为空。
> 本段范围：`cli.py` 第 4205–7300 行（`HermesCLI` 类开头到 `_restore_session_cwd` 前半）。
> 全文 18555 行，本段占 ~16.7%。

---

## 0. 自验记录

### 0.1 三条前提的检验结论（**两条为假，一条一半为假**）

任务书给了三条"前提"，要求先验证。结论先行：

| # | 前提原文 | 判定 | 一句话 |
|---|---------|------|--------|
| 1 | "`HermesCLI.__init__` 是个普通构造函数，主要是赋默认值" | **假** | 541 行；开 SQLite 库并建表、跑两套磁盘维护、读 JSON 文件、**可能发一次 HTTP 请求**、改模块全局、往 stderr 打印告警 |
| 2 | "`_recover_after_resize` 存在是因为 prompt_toolkit 在 SIGWINCH 时把自己的渲染搞坏了" | **假（因果搞反）** | 真正的触发者是**终端自己的 reflow**：列数变窄时终端把已画出的整宽状态栏重排成两行，而 prompt_toolkit 用**旧宽度下缓存的 `_cursor_pos.y`** 去 `cursor_up`，够不着那些多出来的行 |
| 3 | "状态栏在每次按键时重建" | **一半为假** | 每次重绘确实重建一次，但**重建的不是 `_build_status_bar_text`**——那个函数在 TUI 热路径上根本不被调用，只在 `_get_status_bar_fragments` 的 except 兜底里出现一次 |

三条的完整证据分别见 §2.1、§2.2、§2.4。

### 0.2 锚点复核

本稿写完后，用脚本把正文里出现的每一个 `路径:行号 @ 863e313` 抽出来，逐条回读源文件，
把该行原文打出来与稿中代码块首行比对。

- 锚点出现次数 **195**，去重后 `(文件, 行号)` 对 **180** 条；
- 首轮复核发现 **9 条漂移**（全部是"引用块从注释/docstring 中段开始，但锚点写了该结构的起始行"
  这一类偏移 1–7 行），已逐条修正；
- 修正后重跑，**180 条全部命中，0 条漂移**。

漂移清单（原 → 正）：`cli.py:4952→4953`、`cli.py:4777→4776`、`cli.py:5386→5387`、
`cli.py:6862→6863`、`cli.py:4794→4797`（第二处引用）、`cli.py:7091→7092`、
`run_agent.py:3938→3939`（两处）、`agent/credits_tracker.py:203→210`；
另删掉一条写错的 `cli.py:6276`（本应是 `cli.py:4277`）。

复核脚本与最终输出见 §5.3。

### 0.3 未能实测的部分

本容器**没有安装 prompt_toolkit**（`python3 -c "import prompt_toolkit"` → `ModuleNotFoundError`，
且 `/home/user/hermes-venv` 不存在）。因此凡涉及 prompt_toolkit 内部行为的说法，本稿一律
**只引 hermes-agent 仓库自己的注释/代码作为证据**，并在文中标注"（依据仓库自述，未跑通验证）"。
不臆造 prompt_toolkit 的实现细节。

---

## 1. 段内地图

### 1.1 类声明与继承

`cli.py:4205 @ 863e313`

```python
class HermesCLI(CLIAgentSetupMixin, CLICommandsMixin, CLIBillingMixin):
```

`HermesCLI` 本身不是"一个类"，是三个 mixin 的挂载点。本段只覆盖 `cli.py` 内定义的方法体，
mixin 里的方法（如 `_init_agent`、`_handle_background_command`）在别的文件，属别的段。

### 1.2 本段方法清单（按行号）

| 行 | 方法 | 归属簇 |
|----|------|--------|
| 4213 | `__init__` | 构造（541 行） |
| 4755 / 4783 | `_claim_active_session` / `_release_active_session` | 全局会话租约 |
| 4794 / 4818 | `_invalidate` / `_paint_now` | **重绘节流**（本段核心分歧点） |
| 4836 / 4861 / 4887 | `_force_full_redraw` / `_recover_terminal_after_interrupt` / `_clear_prompt_toolkit_screen` | 终端状态恢复 |
| 4908 / 4991 / 5033 | `_recover_after_resize` / `_schedule_status_bar_unsuppress` / `_schedule_resize_recovery` | **resize 恢复三件套** |
| 5078–5168 | `_status_bar_context_style`…`_build_context_bar` | 状态栏样式与色阶 |
| 5099 | `_handle_battery_command` | `/battery` 斜杠命令（唯一一个"命令"跑进渲染簇里的） |
| 5171 / 5209 | `_format_prompt_elapsed` / `_format_idle_since` | **计时格式化**（纯函数，可直接单测） |
| 5221 | `_get_status_bar_snapshot` | **状态栏唯一数据源**（162 行） |
| 5386 / 5401 / 5429 / 5442 / 5449 | 宽度测量与裁剪 | 显示宽度（`get_cwidth`）体系 |
| 5472 / 5482 / 5488 | `_tui_input_rule_height` / `_agent_spacer_height` / `_spinner_widget_height` | **窗口高度回调**（prompt_toolkit `Window(height=…)`） |
| 5502 / 5534 | `_render_spinner_text` / `_spinner_token_flow` | 转圈行 |
| 5553–5611 | `_turn_summary_*`（4 个） | 每轮工具账单 |
| 5625–5829 | `_pet_*`（11 个） | Petdex 吉祥物（半块字符精灵） |
| 5831–5883 | `_voice_*`（3 个） | 语音状态条 |
| 5886 / 5900 / 5988 | `_status_bar_goal_segment` / `_build_status_bar_text` / `_get_status_bar_fragments` | **状态栏成品**（两套并行实现） |
| 6164 / 6178 | `_fmt_stash_age` / `_render_stash_panel` | Ctrl+S 草稿暂存面板 |
| 6243 | `_normalize_model_for_provider` | 模型 ID 归一化（与渲染无关，夹在中间） |
| 6346–6398 | `_on_thinking` / `_on_notice` / `_flush_credit_notices` / `_on_notice_clear` | **通知系统** |
| 6402–6604 | 推理（reasoning）流式显示 6 个方法 | **推理框** |
| 6612–6946 | `_stream_delta` / `_emit_stream_text` / `_flush_stream` / `_reset_stream_state` | **正文流式显示** |
| 6948–6995 | `_slow_command_status` / `_command_spinner_frame` / `_busy_command` | 慢命令忙态 |
| 6997–7134 | `_open_external_editor` / `_submit_editor_buffer` / `_inline_pastes` / `_reset_input_buffer` | **外部编辑器** |
| 7138–7197 | `_install_tool_callbacks` / `_ensure_tirith_security` / `_show_security_advisories` | 启动期一次性挂钩 |
| 7199 | `show_banner` | 欢迎横幅 |
| 7284 | `_restore_session_cwd` | 恢复会话工作目录（跨段，本稿只到 7300） |

### 1.3 这一段在整体里的位置

一句话：**这一段是"CLI 进程的全部可变状态定义 + 终端上所有会动的像素"**。

- 状态定义在 `__init__`（4213–4753）：161 个不同的 `self.<attr>`；
- 像素分两条完全不同的通路：
  1. **prompt_toolkit 托管的"活动底盘"**（status bar / 输入框 / 分隔线 / spinner / pet）——由
     `Window(content=FormattedTextControl(callable), height=callable)` 驱动，每次重绘回调一次；
  2. **普通 scrollback**（响应框、推理框、工具行、turn summary）——由 `_cprint` 直接打印，
     一旦打印就归终端历史所有，CLI 再也管不着。

本段所有的"诡异修复"（resize 抑制、CSI 2J、输出历史回放、宽度测量）都源于这两条通路的
**边界冲突**：底盘要在原地重画，scrollback 要往上滚，而终端 reflow 会把底盘变成 scrollback。

---

## 2. 逐机制精读

### 2.1 `__init__`：一个 541 行的启动过程（前提 1 检验）

#### 2.1.1 它有多长

方法体从 4213 到 4753（下一个 `def` 在 4755）。

`cli.py:4213 @ 863e313`

```python
    def __init__(
        self,
        model: str = None,
        toolsets: List[str] = None,
        provider: str = None,
        reasoning: str = None,
        api_key: str = None,
        base_url: str = None,
        max_turns: int = None,
        verbose: Optional[bool] = None,
        compact: bool = False,
        resume: str = None,
        checkpoints: bool = False,
        pass_session_id: bool = False,
        ignore_rules: bool = False,
    ):
```

`cli.py:4752 @ 863e313`（方法体最后两行）

```python
        self._background_tasks: Dict[str, threading.Thread] = {}
        self._background_task_counter = 0
```

`cli.py:4755 @ 863e313`（下一个方法，确认边界）

```python
    def _claim_active_session(self, surface: str = "cli", *, stderr: bool = False) -> bool:
```

机械统计（脚本见 §5.3）：**541 行**，触及 **161 个不同的 `self.<attr>`**，
体内 **5 条 import 语句**，**11 处环境变量读取**，**7 个 try 块**。

#### 2.1.2 它做的不是"赋默认值"，而是六类真实副作用

**(a) 打开 SQLite 库并建表。**

`cli.py:4569 @ 863e313`

```python
        self._session_db = None
        self._session_db_unavailable = False
        try:
            from hermes_state import SessionDB
            self._session_db = SessionDB()
```

`SessionDB()` 不是懒的。可写路径会 `mkdir` 父目录、跑一次只读预检、开连接、建 schema、探测 FTS5：

`hermes_state.py:2104 @ 863e313`

```python
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
```

而它构造时还挂了一堆并发设施（锁、线程本地读连接集合、token 写队列）：

`hermes_state.py:2009 @ 863e313`

```python
        self._lock = threading.Lock()
        # Read-path split (WAL only): recall/browse queries run on per-thread
        # read-only connections so they never queue behind writer flushes on
        # self._lock. See _read_ctx().
        self._read_local = threading.local()
```

**(b) 失败时往 stderr 打印一整段告警。** 这是 I/O，而且是**用户可见**的 I/O：

`cli.py:4587 @ 863e313`

```python
                Console(stderr=True).print(
                    "[bold yellow]⚠ Session store unavailable[/bold yellow] — "
                    "this conversation will [bold]NOT be saved[/bold] to disk and "
                    "cannot be resumed later. Searching past sessions is also disabled.\n"
                    f"  Reason: {e}\n"
                    "  Fix the state.db store (e.g. `hermes update` to rebuild the venv) to restore persistence."
                )
```

值得单独记一笔的是紧贴其上的注释——它解释了一个 Python 作用域陷阱：

`cli.py:4583 @ 863e313`

```python
                # Console is imported at module scope; do NOT re-import it here.
                # A function-local `import` would make `Console` a local name for
                # the whole __init__ body and break the earlier `self.console =
                # Console()` with UnboundLocalError.
```

这是真的：函数体内任何位置出现 `from rich.console import Console`，`Console` 就是整个
`__init__` 的局部名，4246 行的 `self.console = Console()` 会在赋值前引用而抛 `UnboundLocalError`。
541 行的函数把这种坑放大成了必须写注释防守的程度。

**(c) 跑两套磁盘维护任务。**

`cli.py:4605 @ 863e313`

```python
        _run_state_db_auto_maintenance(self._session_db)
```

这个函数会 `load_config()`（读磁盘 YAML）、可能做一次性的 ghost session 清理、
可能跑 auto-archive / auto-prune / **VACUUM**：

`cli.py:2173 @ 863e313`

```python
        session_db.maybe_auto_prune_and_vacuum(
            retention_days=int(cfg.get("retention_days", 90)),
            min_interval_hours=int(cfg.get("min_interval_hours", 24)),
            min_vacuum_interval_days=int(cfg.get("min_vacuum_interval_days", 30)),
            vacuum=bool(cfg.get("vacuum_after_prune", True)),
            sessions_dir=_hermes_home_maint / "sessions",
        )
```

紧接着还有第二套：

`cli.py:4610 @ 863e313`

```python
        _run_checkpoint_auto_maintenance()
```

`cli.py:2203 @ 863e313`

```python
        maybe_auto_prune_checkpoints(
            retention_days=int(cfg.get("retention_days", 7)),
            min_interval_hours=int(cfg.get("min_interval_hours", 24)),
            delete_orphans=False,
            max_total_size_mb=int(cfg.get("max_total_size_mb", 500)),
        )
```

两者都默认 opt-in（`auto_prune` 默认 False），但**只有跑到配置读取之后才知道**——
也就是说，无论如何都至少多一次 `load_config()`。

**(d) 可能发一次网络请求。** 这是最反直觉的一条：

`cli.py:4390 @ 863e313`

```python
        # Auto-detect model from local server if still on default
        if self.model == _DEFAULT_CONFIG_MODEL:
            _base_url = (_model_config.get("base_url") or "") if isinstance(_model_config, dict) else ""
            if "localhost" in _base_url or "127.0.0.1" in _base_url:
                from hermes_cli.runtime_provider import _auto_detect_local_model
                _detected = _auto_detect_local_model(_base_url)
                if _detected:
                    self.model = _detected
```

`hermes_cli/runtime_provider.py:303 @ 863e313`

```python
        resp = requests.get(url + "/models", timeout=(2, 3))
```

即：当用户没配 model 且 base_url 指向本机推理服务器时，**构造函数会阻塞最多 5 秒发一次 HTTP GET**。
触发条件窄（本地 llama.cpp / LM Studio / Ollama 用户），但一旦命中，"new HermesCLI()"就是一次网络调用。

**(e) 改模块级全局。**

`cli.py:4281 @ 863e313`

```python
        _configure_output_history(
            enabled=CLI_CONFIG["display"].get("persistent_output", True),
            max_lines=CLI_CONFIG["display"].get("persistent_output_max_lines", 200),
        )
```

`cli.py:2998 @ 863e313`

```python
def _configure_output_history(enabled: bool, max_lines=200) -> None:
    """Configure recent CLI output replayed after terminal redraws."""
    global _OUTPUT_HISTORY_ENABLED, _OUTPUT_HISTORY_MAX_LINES, _OUTPUT_HISTORY
    _OUTPUT_HISTORY_ENABLED = bool(enabled)
    _OUTPUT_HISTORY_MAX_LINES = _coerce_output_history_limit(max_lines)
    _OUTPUT_HISTORY = deque(maxlen=_OUTPUT_HISTORY_MAX_LINES)
```

后果：**构造第二个 `HermesCLI` 会把第一个的输出历史整个丢掉**（`deque` 被换新的）。
单进程单实例的假设被硬编码进了构造函数。

**(f) 读一个 JSON 文件。**

`cli.py:4493 @ 863e313`

```python
        self.prefill_messages = _load_prefill_messages(
            _resolve_prefill_messages_file(CLI_CONFIG)
        )
```

`cli.py:356 @ 863e313`

```python
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
```

#### 2.1.3 它**没有**做的事（同样重要）

- **不读 config.yaml 主体**：`CLI_CONFIG` 是模块导入期就算好的全局：

  `cli.py:792 @ 863e313`

  ```python
  CLI_CONFIG = load_cli_config()
  ```

  所以 `__init__` 里的 `CLI_CONFIG["display"].get(...)` 是纯内存读。这也是为什么
  `/battery` 之类的开关要单独 `save_config_value()` 写盘 + 同时改 `self.` 属性——
  改盘上的值对当前进程不生效。

- **不起线程**：`__init__` 只 **new** 了同步原语（`threading.Lock` ×4、`threading.Event` ×2、
  `queue.Queue` ×2），没有一处 `.start()`。pet 动画线程由 `_pet_start_anim()` 起（§2.5），
  spinner / process 线程在 `run()` 里起。

  `cli.py:4694 @ 863e313`

  ```python
          self._pet_lock = threading.Lock()
  ```

  `cli.py:4715 @ 863e313`

  ```python
          self._voice_lock = threading.Lock()
  ```

- **不解析 provider**：明确推迟到用时。

  `cli.py:4411 @ 863e313`

  ```python
          # Provider selection is resolved lazily at use-time via _ensure_runtime_credentials().
  ```

#### 2.1.4 配置优先级：三种不同的写法混在一个函数里

`__init__` 里至少并存四套"取值优先级"写法，值得单独列出来，因为它们**语义不一致**：

1. **CLI 参数 > 配置 > 环境变量 > 常量**（`max_turns`）：

   `cli.py:4436 @ 863e313`

   ```python
           # Max turns priority: CLI arg > config file > env var > default
           if max_turns is not None:  # CLI arg was explicitly set
               self.max_turns = max_turns
           elif CLI_CONFIG["agent"].get("max_turns"):
               self.max_turns = CLI_CONFIG["agent"]["max_turns"]
   ```

2. **环境变量 > 配置**（`max_tokens`、`system_prompt`）：

   `cli.py:4486 @ 863e313`

   ```python
           self.system_prompt = (
               os.getenv("HERMES_EPHEMERAL_SYSTEM_PROMPT", "")
               or CLI_CONFIG["agent"].get("system_prompt", "")
           )
   ```

3. **配置是唯一真源，env 明确不读**（`model`）：

   `cli.py:4363 @ 863e313`

   ```python
           # Configuration - priority: CLI args > env vars > config file
           # Model comes from: CLI arg or config.yaml (single source of truth).
           # LLM_MODEL/OPENAI_MODEL env vars are NOT checked — config.yaml is
           # authoritative.  This avoids conflicts in multi-agent setups where
           # env vars would stomp each other.
   ```

   注意第一行注释 `priority: CLI args > env vars > config file` 与紧随其后的三行
   自相矛盾（后三行说 env **不读**）。这是段内第一处注释-代码冲突，详见 §4.1。

4. **CLI 参数直接压过配置（配置项因此变成死键）**——`compact`，见 §3 缺陷 #1。

---

### 2.2 resize 恢复三件套（前提 2 检验）

#### 2.2.1 前提 2 错在哪

前提说"prompt_toolkit 在 SIGWINCH 时把自己的渲染搞坏了"。代码里的因果链**不是这样**。
真正的链条，源码注释交代得非常完整：

`cli.py:4932 @ 863e313`

```python
        Suppression alone is not enough on a WIDTH change.  prompt_toolkit's
        ``renderer.erase()`` does ``cursor_up(_cursor_pos.y)`` + ``erase_down()``
        using the ``_cursor_pos.y`` cached from the LAST render at the OLD
        width (renderer.py).  When the column count shrinks, the terminal
        reflows each already-painted full-width chrome row into 2+ physical
        rows, so the cached ``y`` undershoots: ``cursor_up`` does not climb
        past the reflowed rows and ``erase_down`` leaves the stale bar stranded
        ABOVE the live origin.  The next paint then stacks a fresh bar below it
        — the duplicated-status-bar report (two bars, two elapsed readings).
        Suppression hides the *new* bar but never erases the already-reflowed
        *old* one, so the ghost survives the whole suppression window.
```

拆开：

- **谁先动手**：**终端模拟器**。列数变窄时它对已经画出的整宽行做 soft-wrap reflow，
  一行变两行。这一步 prompt_toolkit 完全不知情。
- **prompt_toolkit 做错了什么**：它按**旧宽度**下缓存的 `_cursor_pos.y` 往上跳。
  reflow 之后真实行数变多了，所以它跳得不够高，`erase_down()` 擦不到那条被顶上去的旧状态栏。
- **结果**：旧栏留在 live origin 之上，新栏画在下面 → 用户看到两条状态栏、两个计时读数。

所以：**prompt_toolkit 不是"把自己搞坏了"，而是它的增量渲染假设（缓存光标位置仍然有效）
被终端的 reflow 在背后打破了。** 这是一个"外部世界在你不知情时改变了你缓存的状态"的经典问题，
不是渲染器 bug。

#### 2.2.2 真实补救：两段式 + 一个宽度判据

补救不是"重画一遍"，而是三条独立措施：

**措施一：抑制新栏（不解决幽灵，只解决"看起来像两条"里的一半）。**

`cli.py:4962 @ 863e313`

```python
        self._status_bar_suppressed_after_resize = True
```

这个标志被**两处**消费。一处是状态栏窗口的 filter：

`cli.py:17125 @ 863e313`

```python
            filter=Condition(
                lambda: cli_ref._status_bar_visible
                and not getattr(cli_ref, "_status_bar_suppressed_after_resize", False)
            ),
```

另一处是输入分隔线的高度回调（本段内）：

`cli.py:5472 @ 863e313`

```python
    def _tui_input_rule_height(self, position: str, width: Optional[int] = None) -> int:
        """Return the visible height for the top/bottom input separator rules."""
        if position not in {"top", "bottom"}:
            raise ValueError(f"Unknown input rule position: {position}")
        if getattr(self, "_status_bar_suppressed_after_resize", False):
            return 0
        if position == "top":
            return 1
        return 0 if self._use_minimal_tui_chrome(width=width) else 1
```

**措施二：宽度变了才擦视口（CSI 2J），行数变了不擦。**

`cli.py:4972 @ 863e313`

```python
        try:
            new_width = self._get_tui_terminal_width()
        except Exception:
            new_width = None
        prev_width = getattr(self, "_last_resize_width", None)
        # First resize of the session has no prior width to compare against;
        # treat it as a change so an initial maximize/restore is covered too.
        width_changed = new_width is not None and new_width != prev_width
        if width_changed:
            try:
                self._clear_prompt_toolkit_screen(app, rebuild_scrollback=False)
                _replay_output_history()
            except Exception:
                pass
        if new_width is not None:
            self._last_resize_width = new_width
        original_on_resize()
        self._schedule_status_bar_unsuppress(app)
```

关键设计点是 `rebuild_scrollback=False`。`_clear_prompt_toolkit_screen` 里，
`CSI 3J`（清 scrollback 历史）被单独一个开关挡住：

`cli.py:4887 @ 863e313`

```python
    def _clear_prompt_toolkit_screen(self, app, *, rebuild_scrollback: bool = False) -> None:
        """Clear the terminal and reset prompt_toolkit renderer state."""
        try:
            renderer = app.renderer
            out = renderer.output
            out.reset_attributes()
            out.erase_screen()
            if rebuild_scrollback:
                try:
                    out.write_raw("\x1b[3J")
                except Exception:
                    pass
            out.cursor_goto(0, 0)
            out.flush()
            # Drop prompt_toolkit's cached screen + cursor state so the
            # next _redraw() starts from a known (0, 0) origin and
            # re-renders every cell rather than diffing against stale.
            renderer.reset(leave_alternate_screen=False)
        except Exception:
            pass
```

为什么必须挡住 3J？因为启动横幅是在 prompt_toolkit 接管之前用普通 print 打的，
它只存在于 scrollback，**且不在 `_OUTPUT_HISTORY` 里**，擦掉就再也回不来：

`cli.py:4909 @ 863e313`

```python
        """Recover a resized classic CLI without desynchronizing cursor state.

        Unlike _force_full_redraw, we do NOT clear the physical screen or
        scrollback here.  The startup banner and tool summary are printed
        before prompt_toolkit owns the live chrome, so they live in normal
        terminal scrollback.  Erasing the screen on SIGWINCH removes that
        startup UI and ``_replay_output_history`` cannot reconstruct it
        (the banner was never added to ``_OUTPUT_HISTORY``).
```

**措施三：去抖 + 自动解除抑制。**

去抖在 `_schedule_resize_recovery`（0.12s）：

`cli.py:5033 @ 863e313`

```python
    def _schedule_resize_recovery(self, app, original_on_resize, delay: float = 0.12) -> None:
        """Debounce resize redraws so footer chrome is not stamped into scrollback."""
```

它用"timer 身份比对"做去抖（比取消更可靠——已经 fire 的 timer 取消不掉）：

`cli.py:5042 @ 863e313`

```python
            def _timer_fired(timer_ref):
                def _run_recovery():
                    with lock:
                        if getattr(self, "_resize_recovery_timer", None) is not timer_ref:
                            return
                        self._resize_recovery_timer = None
                        self._resize_recovery_pending = False
                    self._recover_after_resize(app, original_on_resize)
```

自动解除抑制在 `_schedule_status_bar_unsuppress`（0.35s，同样去抖）：

`cli.py:4991 @ 863e313`

```python
    def _schedule_status_bar_unsuppress(self, app, delay: float = 0.35) -> None:
        """Clear the post-resize status-bar suppression after the reflow settles.

        Debounced: a fresh resize cancels the pending unsuppress and restarts
        the timer, so a resize storm only repaints the bar once it stops.
        """
```

这条自动解除是**后补的**，注释里明说以前只有"下次提交输入才解除"，导致 idle 时状态栏永久消失：

`cli.py:4953 @ 863e313`

```python
        The suppression is transient: a short follow-up timer clears it and
        repaints once the reflow has settled, so the bar returns on its own
        during idle.  Previously the flag was only cleared on the next
        *submitted* user input, so a resize/reflow (tmux pane change, SSH
        window restore, font zoom) followed by idle left the status bar hidden
        indefinitely even while the refresh clock kept ticking (the dynamic
        chrome rendered at height 0 on every repaint).  The next-submit clear
        at the input loop remains as a fast path.
```

"fast path"指的是这一行（不在本段，为完整性列出）：

`cli.py:17405 @ 863e313`

```python
                    self._status_bar_suppressed_after_resize = False
```

#### 2.2.3 挂载点

整套东西通过**猴补丁**接到 prompt_toolkit 的 SIGWINCH 处理上：

`cli.py:17349 @ 863e313`

```python
        _original_on_resize = app._on_resize

        def _resize_clear_ghosts():
            self._schedule_resize_recovery(app, _original_on_resize)

        app._on_resize = _resize_clear_ghosts
```

注意 `original_on_resize` 是**被保留并最终调用**的（4988 行），不是被替换掉。
所以整套逻辑是"在 prompt_toolkit 自己的 resize 前后各加一段"，不是重写。

#### 2.2.4 `_resize_recovery_pending` 与重绘节流的耦合

resize 在飞的时候，一切后台重绘要停：

`cli.py:4794 @ 863e313`

```python
    def _invalidate(self, min_interval: float = 0.25) -> None:
        """Throttled UI repaint for high-frequency background updates.

        Use this for spinner frames, streaming token flushes, and other
        repaints that can fire many times per second — the throttle prevents
        terminal blinking on slow/SSH connections, and the resize-recovery
        guard avoids stamping footer/status-bar chrome into scrollback while a
        SIGWINCH reflow is in flight.

        Do NOT use this for user-blocking modal prompts (approval / clarify /
        sudo). Those are rare, one-shot, user-blocking events that must paint
        immediately; route them through ``self._app.invalidate()`` directly, the
        same way the modal key-binding handlers already do. Sending a modal's
        entry paint through this throttle lets an unrelated background repaint
        within the 250ms window — or an in-flight resize — silently drop it, so
        the prompt never renders and times out unseen (#41098).
        """
        if getattr(self, "_resize_recovery_pending", False):
            return
        now = time.monotonic()
        if hasattr(self, "_app") and self._app and (now - getattr(self, "_last_invalidate", 0.0)) >= min_interval:
            self._last_invalidate = now
            self._app.invalidate()
```

这是本段最重要的一段设计文档。它同时定义了两件事：
1. **节流值 0.25s 是给"高频背景更新"的**（spinner/流式），SSH 上防闪；
2. **模态框绝不能走这条路**——因为 250ms 窗口里任何一次别的重绘都会把模态的"入场绘制"吞掉，
   模态就永远画不出来，然后静默超时（#41098）。

对应的逃生舱：

`cli.py:4818 @ 863e313`

```python
    def _paint_now(self) -> None:
        """Immediate, unthrottled repaint for user-blocking modal prompts.

        Background-thread callbacks (approval / clarify / sudo) set their modal
        state then call this to make the panel visible at once. It deliberately
        bypasses the ``_invalidate`` throttle and resize-recovery guard — a
        modal the user is actively waiting on must never be dropped — mirroring
        the direct ``event.app.invalidate()`` the modal key-binding handlers
        already use. See ``_invalidate`` for why the throttle must not gate
        these paints (#41098).
        """
```

**这条约定在段内被 pet 动画线程违反了**，见 §3 缺陷 #5。

#### 2.2.5 另外两条"终端状态恢复"路径（同簇，不同触发）

对比清单——三条恢复路径的差别是**擦不擦、擦多少、回放不回放**：

| 方法 | 触发 | erase_screen (2J) | CSI 3J | renderer.reset | 回放历史 |
|------|------|:---:|:---:|:---:|:---:|
| `_force_full_redraw` (4836) | Ctrl+L / `/redraw` | ✔ | ✘ | ✔ | ✔ |
| `_recover_terminal_after_interrupt` (4861) | 打断后 | ✔（经前者） | ✘ | ✔ | ✔ |
| `_recover_after_resize` (4908) | SIGWINCH | **仅宽度变化时** | ✘ | 同上 | 同上 |

`_force_full_redraw` 的存在理由是"外部重画我们探测不到"：

`cli.py:4836 @ 863e313`

```python
    def _force_full_redraw(self) -> None:
        """Force a clean full-screen repaint of the prompt_toolkit UI.

        Used to recover from terminal buffer drift caused by external
        redraws we can't detect — e.g. macOS cmux / tmux tab switches,
        ``clear`` issued from a subshell, or SSH window restores. These
        wipe or repaint the terminal without firing SIGWINCH, so
        prompt_toolkit's tracked ``_cursor_pos`` no longer matches reality
        and the next incremental redraw stacks on top of stale content
        (ghost status bars, duplicated prompts).
```

`_recover_terminal_after_interrupt` 是另一类：**CPR 应答泄漏**。

`cli.py:4861 @ 863e313`

```python
    def _recover_terminal_after_interrupt(self) -> None:
        """Recover the terminal after an interrupted agent turn (#33271).

        When the user interrupts a running turn by typing a new message,
        prompt_toolkit may have an in-flight ``CSI 6n`` cursor-position query
        whose reply (``ESC[<row>;<col>R``) arrives on stdin after the input
        parser has torn down. The reply then leaks as literal text
        (``^[[19;1R``) and the VT100 parser can stall in a partial-escape
        state, accepting no further keystrokes — the terminal appears frozen.
```

这三条合起来说明一件事：**prompt_toolkit 的增量渲染依赖"我知道光标在哪"这个不变量，
而终端世界有至少三种方式在它背后破坏这个不变量**（reflow、外部清屏、CPR 应答错位）。
harness 作者的应对是统一的：丢掉缓存、从 (0,0) 重画、把自己记的输出历史重放一遍。

---

### 2.3 计时与格式化：`_format_prompt_elapsed` / `_format_idle_since`

两个纯静态函数，是本段里最容易单测的部分。

`cli.py:5171 @ 863e313`

```python
    def _format_prompt_elapsed(prompt_start_time: Optional[float], prompt_duration: float, live: bool = False) -> str:
        """Format per-prompt elapsed time for the status bar.

        Always returns a string — shows 0s on fresh start before first turn.
        Keeps seconds visible at all scales so it increments smoothly:
            59s → 1m → 1m 1s → ... → 1m 59s → 2m → 2m 1s → ...
            59m 59s → 1h → 1h 0m 1s → ...
            23h 59m 59s → 1d → 1d 0h 1m → ...

        Emoji prefix: ⏱ when turn is live, ⏲ when frozen or fresh start.
        Uses width-1 (no variation selector) glyphs so the status bar stays
        aligned in monospace terminals.
        """
```

**设计意图**很清楚：状态栏里的数字**不能跳宽度**，否则整条栏会左右抖。所以

1. 秒始终可见（不做"超过 1 分钟就只显示分钟"），
2. emoji 特意挑**不带变体选择符**的 ⏱ (U+23F1) / ⏲ (U+23F2)。

实际字符已核对：

`cli.py:5205 @ 863e313`

```python
        emoji = "⏱" if live else "⏲"
```

（脚本核对码点：U+23F1 / U+23F2，无 U+FE0F。）

计算主体：

`cli.py:5184 @ 863e313`

```python
        if prompt_start_time is None and prompt_duration == 0.0:
            return "⏲ 0s"
        elapsed = time.time() - prompt_start_time if prompt_start_time is not None else prompt_duration
        elapsed = max(0.0, elapsed)
```

`live` 与"是否在跑"的耦合在快照里：

`cli.py:5249 @ 863e313`

```python
            "prompt_elapsed": self._format_prompt_elapsed(
                getattr(self, "_prompt_start_time", None),
                getattr(self, "_prompt_duration", 0.0),
                live=getattr(self, "_prompt_start_time", None) is not None,
            ),
```

即：`_prompt_start_time is not None` 就是"这轮在跑"的唯一判据。轮结束时它被置 None 并冻结时长：

`cli.py:14218 @ 863e313`

```python
                self._prompt_duration = max(0.0, time.time() - self._prompt_start_time)
                self._prompt_start_time = None
```

**这里用的是 `time.time()`（墙钟），不是 `time.monotonic()`。** 而同一段内的工具计时器用的是 monotonic：

`cli.py:5510 @ 863e313`

```python
            elapsed = time.monotonic() - t0
```

turn summary 也是 monotonic：

`cli.py:5581 @ 863e313`

```python
            self._turn_summary_start = time.monotonic()
```

不一致。后果见 §3 缺陷 #6。

`_format_idle_since` 是它的镜像，只在"没在跑"时出现：

`cli.py:5209 @ 863e313`

```python
    def _format_idle_since(last_finished_at: Optional[float], turn_live: bool) -> str:
        """Format time since the last final agent response for the status bar.

        Returns an empty string while a turn is live (the per-prompt elapsed
        timer covers that case) or before the first turn has completed.
        Compact read-out: ``✓ 42s`` / ``✓ 3m`` / ``✓ 1h 12m``.
        """
        if turn_live or last_finished_at is None:
            return ""
        idle = max(0.0, time.time() - last_finished_at)
        return f"✓ {format_duration_compact(idle)}"
```

设计上"两个计时器互斥"是对的：跑的时候看 ⏱，停的时候看 ✓，状态栏永远只多一个字段。

---

### 2.4 状态栏：两套实现、一个数据源（前提 3 检验）

#### 2.4.1 前提 3 的第一半：`_build_status_bar_text` 不在热路径上

全仓 `_build_status_bar_text` 的**非测试**引用只有两处——定义和一处 except 兜底：

```
$ grep -rn "_build_status_bar_text" --include=*.py .   # 已剔除 tests/
./cli.py:5900:    def _build_status_bar_text(self, width: Optional[int] = None) -> str:
./cli.py:6162:            return [("class:status-bar", f" {self._build_status_bar_text()} ")]
```

`cli.py:6161 @ 863e313`

```python
        except Exception:
            return [("class:status-bar", f" {self._build_status_bar_text()} ")]
```

真正挂到 TUI 上的是 fragments 版：

`cli.py:17111 @ 863e313`

```python
        status_bar = ConditionalContainer(
            Window(
                content=FormattedTextControl(lambda: cli_ref._get_status_bar_fragments()),
                height=1,
```

所以：**`_build_status_bar_text` 是一条"纯文本降级通道"**，只有在 fragments 版整个抛异常时才跑。
它另外还被 6 个测试文件直接调用（`tests/cli/test_cli_status_bar.py` 等），
所以它事实上是"被测试固定住的第二实现"。两套实现共用 `_get_status_bar_snapshot`，
但**分段逻辑、分隔符、字段顺序各写一遍**：

- 文本版分隔符：`< 52` 用 `·`，`< 76` 用 `·`，宽用 `│`（5947 / 5984 行）
- fragments 版：同样三档，但每档手写 `("class:status-bar-dim", " · ")` 片段

`cli.py:5947 @ 863e313`

```python
                return self._trim_status_bar_text(" · ".join(parts), width)
```

`cli.py:5984 @ 863e313`

```python
            return self._trim_status_bar_text(" │ ".join(parts), width)
```

两套实现的漂移风险是真实的（fragments 版有 focus badge 的注释说明位置、
文本版没有对应注释；两版的 stash 指示器处理也不同——文本版**根本没有** stash 指示器）。
对照：fragments 版的 stash 段落在 6130–6144，文本版全段无 `_prompt_stash` 字样。

`cli.py:6130 @ 863e313`

```python
            try:
                stash_indicator = self._prompt_stash.indicator()
            except Exception:
                stash_indicator = ""
```

#### 2.4.2 前提 3 的第二半：确实每次重绘都重建，且代价被刻意压过

`_get_status_bar_fragments` 每次被调用都会重跑 `_get_status_bar_snapshot()`：

`cli.py:5988 @ 863e313`

```python
    def _get_status_bar_fragments(self):
        if not self._status_bar_visible or getattr(self, '_model_picker_state', None):
            return []
        try:
            snapshot = self._get_status_bar_snapshot()
```

作者自己在快照里三处写明"这是每次重绘都跑的"，可以当作仓库自述的证据：

`cli.py:5289 @ 863e313`

```python
        # Battery read-out (first status-bar element when enabled). Reads are
        # memoised for a few seconds inside agent.battery, so polling it on
        # every status-bar repaint is cheap.
```

`cli.py:5306 @ 863e313`

```python
        # Count live /background tasks. The dict entry is removed in the
        # task thread's finally block, so len() reflects truly-running tasks.
        # len() on a CPython dict is atomic; safe to read without a lock.
```

`cli.py:5334 @ 863e313`

```python
        # Standing /goal state (Ralph loop). GoalManager is cached on self and
        # keeps its state in memory, so this is a cheap attribute read — no DB
        # hit per repaint. Only an *active* goal earns a segment; paused/done
        # goals stay out of the bar (matching the desktop's active-first row).
```

**逐项核实这些"便宜"的说法**（这一步是本节的价值所在）：

| 快照字段 | 实现 | 真实代价 | 核实 |
|---|---|---|---|
| `model_short` | `_reverse_alias_for_display` | 首次 `load_config()`，之后走 `_REVERSE_ALIAS_CACHE` | `cli.py:138` |
| `battery_*` | `agent.battery.read_battery()` | TTL 缓存命中即返回 | `agent/battery.py:89` |
| `active_background_processes` | `process_registry.count_running()` | `len(dict)` | `tools/process_registry.py:1832` |
| `active_background_subagents` | `async_delegation.active_count()` | 持锁遍历 records dict | `tools/async_delegation.py:544` |
| `goal_*` | `GoalManager.is_active()` | 纯内存属性读 | `hermes_cli/goals.py:1257` |
| `context_*` | `agent.context_compressor` 属性 | 属性读 | `cli.py:5364` |

逐条证据：

`cli.py:138 @ 863e313`

```python
    global _REVERSE_ALIAS_CACHE
    if not model_name:
        return model_name
    if _REVERSE_ALIAS_CACHE is None:
```

`agent/battery.py:89 @ 863e313`

```python
    if use_cache and _cache is not None:
        ts, cached = _cache
        if time.monotonic() - ts < _CACHE_TTL_SECONDS:
            return cached
```

`tools/process_registry.py:1831 @ 863e313`

```python
        try:
            return len(self._running)
        except Exception:
            return 0
```

`tools/async_delegation.py:544 @ 863e313`

```python
    with _records_lock:
        return sum(
            1 for r in _records.values()
            if r.get("status") in {"running", "stalling", "finalizing"}
        )
```

`hermes_cli/goals.py:1257 @ 863e313`

```python
    def is_active(self) -> bool:
        return self._state is not None and self._state.status == "active"
```

**结论：这些说法都成立。** 每次重绘的真实代价里，最贵的不是数据采集，而是：

1. **多次 `ioctl` 量宽度**。`_get_tui_terminal_width` 每次都问一遍 prompt_toolkit：

   `cli.py:5428 @ 863e313`

   ```python
       @staticmethod
       def _get_tui_terminal_width(default: tuple[int, int] = (80, 24)) -> int:
           """Return the live prompt_toolkit width, falling back to ``shutil``.

           The TUI layout can be narrower than ``shutil.get_terminal_size()`` reports,
           especially on Termux/mobile shells, so prefer prompt_toolkit's width whenever
           an app is active.
           """
           try:
               from prompt_toolkit.application import get_app
               return get_app().output.get_size().columns
           except Exception:
               return shutil.get_terminal_size(default).columns
   ```

   一次重绘里至少四条独立路径会调它：`_get_status_bar_fragments`(5998)、
   `_tui_input_rule_height`→`_use_minimal_tui_chrome`(5445) ×2（top/bottom）、
   `_spinner_widget_height`(5495)、`_get_voice_status_fragments`(5868)、
   `_render_stash_panel` 的调用点(17139)。

2. **逐 fragment 调 `get_cwidth` 做总宽复核**：

   `cli.py:6155 @ 863e313`

   ```python
               total_width = sum(self._status_bar_display_width(text) for _, text in frags)
               if total_width > width:
                   plain_text = "".join(text for _, text in frags)
                   trimmed = self._trim_status_bar_text(plain_text, width)
                   return [("class:status-bar", trimmed)]
               return frags
   ```

   而 `_status_bar_display_width` **每次调用都做一次函数内 import**：

   `cli.py:5385 @ 863e313`

   ```python
       @staticmethod
       def _status_bar_display_width(text: str) -> int:
           """Return terminal cell width for status-bar text.

           len() is not enough for prompt_toolkit layout decisions because some
           glyphs can render wider than one Python codepoint. Keeping the status
           bar within the real display width prevents it from wrapping onto a
           second line and leaving behind duplicate rows.
           """
           try:
               from prompt_toolkit.utils import get_cwidth
               return get_cwidth(text or "")
           except Exception:
               return len(text or "")
   ```

   函数内 import 命中 `sys.modules` 是便宜的，但在"每 fragment 一次"的循环里仍然是可省的开销。

#### 2.4.3 谁触发重绘

- **不是定时器**（默认关闭）：

  `cli.py:17257 @ 863e313`

  ```python
              # Read from display.cli_refresh_interval (default 0 = disabled).
              # When non-zero, prompt_toolkit redraws the UI on this cadence
              # during idle, keeping wall-clock status-bar read-outs ticking.
              # Set to 0 to suppress background redraws entirely — avoids
              # fighting terminal auto-scroll in non-fullscreen mode (Xshell,
              # iTerm2, Windows Terminal). See #48309.
              refresh_interval=float(CLI_CONFIG.get("display", {}).get("cli_refresh_interval", 0)),
  ```

- **也不是 spinner 线程**（空闲时它什么都不做）：

  `cli.py:17364 @ 863e313`

  ```python
                  else:
                      # Do not repaint the idle prompt every second. In non-full-screen
                      # prompt_toolkit mode, background redraws can fight tmux/Ghostty/cmux
                      # viewport restoration after focus changes and visually move the
                      # command input area. Keep idle stable; input/agent events still
                      # invalidate explicitly when the UI actually changes.
                      time.sleep(0.2)
  ```

- **是**：输入事件（prompt_toolkit 自身在按键后重绘，见上面注释末句"input/agent events still
  invalidate explicitly"）、`_invalidate()` 的各个调用点（流式 token、spinner、tool 事件）、
  以及 pet 动画线程每 0.16s 一次的 `app.invalidate()`（§2.5）。

**所以"每次按键重建状态栏"是成立的**，而且一旦启用 pet，就变成"每 0.16s 也重建一次"。
这是本段最大的隐藏成本，见 §3 缺陷 #5。

#### 2.4.4 三档宽度与四个阈值不一致

状态栏用 52 / 76 两档：

`cli.py:5915 @ 863e313`

```python
            if width < 52:
```

`cli.py:5924 @ 863e313`

```python
            if width < 76:
```

而"窄终端精简 chrome"用 64：

`cli.py:5446 @ 863e313`

```python
        return width < 64
```

`_scrollback_box_width` 用 32 做地板：

`cli.py:5470 @ 863e313`

```python
        return max(32, int(width or 80))
```

四个魔数分散在三个方法里，没有共同常量。这是一处可维护性缺口（不是缺陷，记在此处备查）。

`_scrollback_box_width` 的注释里藏着一段有价值的设计史：

`cli.py:5449 @ 863e313`

```python
    def _scrollback_box_width(width: Optional[int] = None) -> int:
        """Return the full viewport width for printed scrollback box rules.

        Previously this clamped to ``max(32, min(width, 56))`` as a defense
        against terminal-emulator reflow on column-shrink (#25975, salvaging
        #24403).  That clamp made response/reasoning borders look stubby on
        any modern wide terminal.  We now trust the prompt_toolkit
        ``_output_screen_diff`` monkey-patch landed in #26137 (salvaging
        #25981) to keep chrome out of scrollback in the first place, and
        accept that an aggressive column-shrink may visually reflow already
        printed Panel borders — that's a cosmetic artifact of stamped
        scrollback history, not a live-render bug.
```

**这是同一个 reflow 问题的第二个战场**：§2.2 解决的是"活动底盘"被 reflow，
这里解决的是"已打印到 scrollback 的框线"被 reflow。作者的取舍是：
底盘必须修（会看到两条状态栏），scrollback 框线不修（只是难看），
因为为了防它把所有框限到 56 列，代价是宽终端上永远的丑。

---

### 2.5 Pet 部件：一个默认对所有人生效的后台线程

#### 2.5.1 定位与设计

`cli.py:5613 @ 863e313`

```python
    # ── Petdex mascot (base-CLI pet pane) ───────────────────────────────
    #
    # Parity with the TUI: a half-block sprite rendered as a prompt_toolkit
    # window above the prompt, reacting to agent state and animated by a timer
    # that calls ``app.invalidate()``. Half-blocks only — the crisp Kitty image
    # protocol can't coexist with prompt_toolkit's patch_stdout output layer
    # (raw image escapes get swallowed/mangled), so we use truecolor styled
    # text, which prompt_toolkit renders natively in any 24-bit terminal.
```

这条注释解释了一个真实的技术取舍：**Kitty 图形协议与 `patch_stdout` 不兼容**，
所以只能用 `▀`/`▄` 半块 + 24 位真彩前景/背景色来"画图"。渲染核心：

`cli.py:5766 @ 863e313`

```python
        frags = []
        for y, row in enumerate(grid):
            if y:
                frags.append(("", "\n"))
            for top, bottom in row:
                tr, tg, tb, ta = top
                br, bg, bb, ba = bottom
                top_op = ta >= 32
                bot_op = ba >= 32
                if not top_op and not bot_op:
                    frags.append(("", " "))
                elif top_op and bot_op:
                    frags.append((f"fg:#{tr:02x}{tg:02x}{tb:02x} bg:#{br:02x}{bg:02x}{bb:02x}", "▀"))
                elif top_op:
                    # Upper half only — leave the lower half the terminal's bg
                    # instead of painting it black (cleaner on light themes).
                    frags.append((f"fg:#{tr:02x}{tg:02x}{tb:02x}", "▀"))
                else:
                    frags.append((f"fg:#{br:02x}{bg:02x}{bb:02x}", "▄"))
        return frags
```

一个终端字符 = 两个垂直像素（上半用前景色、下半用背景色）。alpha < 32 视为透明，
半透明时**只画有色的那一半**，让另一半保持终端背景色——这一条是给浅色主题准备的。

#### 2.5.2 状态机

三层优先级：**瞬时反应 > 等待用户 > 稳态**。

`cli.py:5709 @ 863e313`

```python
    def _derive_pet_state(self) -> str:
        """Map current CLI activity to a pet animation state.

        A transient reaction beat (wave/jump/failed) wins while it's live;
        otherwise the steady state comes from the shared
        :func:`agent.pet.state.derive_pet_state` so the CLI can't drift from the
        TUI/desktop priority order.
        """
        if self._pet_event and time.monotonic() < self._pet_event_until:
            return self._pet_event
        self._pet_event = ""
        from agent.pet.state import derive_pet_state

        # A live blocking modal (approval / clarify / sudo / secret / slash
        # confirm) means the agent is paused on the user → the `waiting` pose,
        # which outranks the in-flight signals in derive_pet_state.
        awaiting_input = bool(
            self._approval_state
            or self._clarify_state
            or self._sudo_state
            or self._secret_state
            or getattr(self, "_slash_confirm_state", None)
        )
```

稳态判定被**抽到共享模块** `agent.pet.state.derive_pet_state`，注释明说是为了
"CLI 不会和 TUI/desktop 的优先级顺序漂移"。这是个好设计：三个前端各画各的像素，
但"现在该是什么姿势"只有一份定义。

#### 2.5.3 动画驱动与它的代价

`cli.py:5622 @ 863e313`

```python
    _PET_FRAME_INTERVAL = 0.16
    _PET_CFG_INTERVAL = 2.5
```

`cli.py:5797 @ 863e313`

```python
    def _pet_anim_loop(self) -> None:
        """Advance the frame + invalidate on a timer while a pet is enabled."""
        while self._pet_anim_running:
            time.sleep(self._PET_FRAME_INTERVAL)
            now = time.monotonic()
            if now - self._pet_cfg_checked >= self._PET_CFG_INTERVAL:
                self._pet_cfg_checked = now
                self._pet_resolve_config()
            if not self._pet_enabled:
                continue
            with self._pet_lock:
                self._pet_frame_idx += 1
            app = getattr(self, "_app", None)
            if app is not None:
                try:
                    app.invalidate()
                except Exception:
                    pass
```

**关键顺序问题**：`_pet_resolve_config()` 在 `if not self._pet_enabled: continue` **之前**。
也就是说，**即使用户从来没开过 pet，这个线程也会每 2.5 秒读一次配置文件**。

`_pet_resolve_config` 里的读法：

`cli.py:5631 @ 863e313`

```python
        try:
            from agent.pet import constants, store
            from agent.pet.render import PetRenderer
            from hermes_cli.config import load_config

            cfg = load_config()
```

`load_config()` 有 mtime+size 缓存，但**命中缓存也要 stat 一次并做一次 deepcopy**，
仓库自己给这条路径写过一个只读快速版：

`hermes_cli/config.py:3142 @ 863e313`

```python
    Why this exists: ``load_config()`` cache-hit cost is ~265us per call,
    half of which (~135us) is the defensive deepcopy. The agent loop calls
    into config reads (timeouts, thresholds, feature flags) ~20-50x per
    conversation; skipping deepcopy here removes a measurable allocation
    source and the GC pressure that comes with it.
```

`_pet_resolve_config` 只读不写，本可以用 `load_config_readonly()`。

而线程是**无条件启动**的：

`cli.py:17802 @ 863e313`

```python
                # Drive the petdex mascot animation (no-op when no pet enabled).
                self._pet_start_anim()
```

`cli.py:5816 @ 863e313`

```python
    def _pet_start_anim(self) -> None:
        if self._pet_anim_running:
            return
        self._pet_resolve_config()
        self._pet_anim_running = True
        self._pet_anim_thread = threading.Thread(target=self._pet_anim_loop, daemon=True)
        self._pet_anim_thread.start()
```

注释说"no-op when no pet enabled"——**这句话不准确**。线程照起，每 0.16s 醒一次，
每 2.5s 读一次配置。详见 §3 缺陷 #4 与 §4.3。

#### 2.5.4 高度回调与内容回调的两次独立求值

`cli.py:5787 @ 863e313`

```python
    def _pet_widget_height(self) -> int:
        """Visible rows for the pet window — 0 collapses it when no pet shows."""
        with self._pet_lock:
            if not self._pet_enabled or self._pet_renderer is None:
                return 0
            grids = self._pet_frames_for(self._derive_pet_state())
            if not grids or not grids[0]:
                return 0
            return len(grids[0])
```

`cli.py:16642 @ 863e313`

```python
        self._pet_widget = Window(
            content=FormattedTextControl(self._pet_fragments),
            height=self._pet_widget_height,
            align=WindowAlign.RIGHT,
        )
```

高度和内容是**两个独立回调**，各自 `with self._pet_lock` 并各自调 `_derive_pet_state()`。
这两次求值之间状态可以变（反应 beat 到期、`_agent_running` 翻转），
两次拿到的 grid 行数就可能不同。见 §3 缺陷 #7。

---

### 2.6 通知系统：一个明确写成 no-op 的回调

#### 2.6.1 为什么要排队而不是直接打印

`cli.py:6354 @ 863e313`

```python
    def _on_notice(self, notice) -> None:
        """Queue an out-of-band AgentNotice for rendering at the next clean boundary.

        Notices fire from inside the agent turn (cold-start seed during _init_agent,
        per-turn _capture_credits after the API call) — printing immediately races the
        streaming response and the line gets buried behind the prompt (see _cprint's
        bg-thread caveat). So we QUEUE here and flush in _flush_credit_notices(), called
        right after run_conversation returns. Fail-soft: never break the turn.
        """
```

这是本段里"scrollback vs 活动底盘"冲突的第三个实例：从 agent 线程直接 `_cprint`
会和输入区的重绘赛跑，行会被埋在提示符后面。解法是**排队 + 在干净边界统一 flush**。

队列结构是 `(level, text)` 二元组，**不带 key**：

`cli.py:6363 @ 863e313`

```python
        try:
            text = getattr(notice, "text", "") or ""
            if not text:
                return
            level = getattr(notice, "level", "info") or "info"
            if not hasattr(self, "_pending_credit_notices"):
                self._pending_credit_notices = []
            self._pending_credit_notices.append((level, text))
        except Exception:
            pass
```

（注意 `_pending_credit_notices` **不在 `__init__` 里声明**，靠 `hasattr` 懒建。
段内还有若干这种"懒属性"，如 `_stream_prefilt`、`_reasoning_buf`、`_deferred_content`、
`_voice_record_key_display_cache`——全部靠 `getattr(self, x, default)` 兜底读。）

flush 端：

`cli.py:6374 @ 863e313`

```python
    def _flush_credit_notices(self) -> None:
        """Print any queued credit notices as level-colored lines. Called at turn end
        (after run_conversation) where _cprint paints cleanly above the prompt."""
```

#### 2.6.2 `_on_notice_clear` 是显式 no-op，而上游确实会 clear

`cli.py:6393 @ 863e313`

```python
    def _on_notice_clear(self, key: str) -> None:
        """Notice cleared. The REPL prints lines (no persistent slot to wipe), so
        this drops any still-queued notice with that key is not tracked by key here;
        it's a no-op for rendering — kept so the agent's clear callback is bound
        symmetrically with the show callback (and so future REPL UIs can hook it)."""
        return
```

（这段 docstring 本身语法破碎——"this drops any still-queued notice with that key **is not
tracked by key here**"——像是两句话被合并时漏删了半句。记在 §4.4。）

绑定处：

`hermes_cli/cli_agent_setup_mixin.py:516 @ 863e313`

```python
                notice_callback=self._on_notice,
                notice_clear_callback=self._on_notice_clear,
```

上游确实会先 clear 再 show：

`run_agent.py:3939 @ 863e313`

```python
            for key in to_clear:        # clears FIRST …
                self._emit_notice_clear(key)
            for notice in to_show:      # … then shows (depleted lands last in a latest-wins slot)
                self._emit_notice(notice)
```

而 clear 的语义是"同一个 key 的旧行要被新行替换"：

`agent/credits_tracker.py:347 @ 863e313`

```python
    if target_band != shown_band:
        if CREDITS_USAGE_KEY in active:
            to_clear.append(CREDITS_USAGE_KEY)
            active.discard(CREDITS_USAGE_KEY)
```

TUI 那边是真的实现了 clear：

`tui_gateway/server.py:5652 @ 863e313`

```python
        "notice_clear_callback": lambda key: _emit(
```

CLI 这边不实现的后果见 §3 缺陷 #3。

---

### 2.7 推理框与响应框：两个流的排他关系

#### 2.7.1 三种推理显示模式

`cli.py:6402 @ 863e313`

```python
    def _current_reasoning_callback(self):
        """Return the active reasoning display callback for the current mode."""
        if self.show_reasoning and self.streaming_enabled:
            return self._stream_reasoning_delta
        if self.verbose and not self.show_reasoning:
            return self._on_reasoning
        return None
```

三条分支对应三种体验：**流式推理框** / **verbose 逐行** / **不显示**。
注意 `show_reasoning` 默认 True：

`cli.py:4277 @ 863e313`

```python
        self.show_reasoning = CLI_CONFIG["display"].get("show_reasoning", True)
```

但 `streaming_enabled` 默认 False：

`cli.py:4304 @ 863e313`

```python
        self.streaming_enabled = CLI_CONFIG["display"].get("streaming", False)
```

所以**默认配置下 `_current_reasoning_callback()` 返回 None**（第一条要求两个都真，
第二条要求 `verbose and not show_reasoning`）。推理框是 opt-in 的。

#### 2.7.2 排他：推理框开着时正文要憋住

`cli.py:6758 @ 863e313`

```python
    def _emit_stream_text(self, text: str) -> None:
        """Emit filtered text to the streaming display."""
        if not text:
            return

        # When show_reasoning is on and reasoning is still rendering,
        # defer content until the reasoning box closes.  This ensures the
        # reasoning block always appears BEFORE the response in the terminal.
        if self.show_reasoning and getattr(self, "_reasoning_box_opened", False):
            self._deferred_content = getattr(self, "_deferred_content", "") + text
            return

        # Close the live reasoning box before opening the response box
        self._close_reasoning_box()
```

反向也有防守——响应框一开，后续推理全丢：

`cli.py:6558 @ 863e313`

```python
    def _stream_reasoning_delta(self, text: str) -> None:
        """Stream reasoning/thinking tokens into a dim box above the response.

        Opens a dim reasoning box on first token, streams line-by-line.
        The box is closed automatically when content tokens start arriving
        (via _stream_delta → _emit_stream_text).

        Once the response box is open, suppress any further reasoning
        rendering — a late thinking block (e.g. after an interrupt) would
        otherwise draw a reasoning box inside the response box.
        """
        if not text:
            return
        self._reasoning_shown_this_turn = True
        if getattr(self, "_stream_box_opened", False):
            return
```

**这是一个"两个盒子不能嵌套"的不变量**，靠两端各加一个守卫维持：
正文憋在 `_deferred_content`、迟到推理直接丢。

`_close_reasoning_box` 是这个不变量的交接点：

`cli.py:6594 @ 863e313`

```python
    def _close_reasoning_box(self) -> None:
        """Close the live reasoning box if it's open."""
        if getattr(self, "_reasoning_box_opened", False):
            # Flush remaining reasoning buffer
            buf = getattr(self, "_reasoning_buf", "")
            if buf:
                _cprint(f"{_DIM}{buf}{_RST}")
                self._reasoning_buf = ""
            w = self._scrollback_box_width()
            _cprint(f"{_DIM}└{'─' * (w - 2)}┘{_RST}")
            self._reasoning_box_opened = False

            # Flush any content that was deferred while reasoning was rendering.
            deferred = getattr(self, "_deferred_content", "")
            if deferred:
                self._deferred_content = ""
                self._emit_stream_text(deferred)
```

最后四行是**互递归**：`_close_reasoning_box` → `_emit_stream_text` → （开头就检查
`_reasoning_box_opened`，此时已是 False）→ 不会再回来。递归深度 1，安全，但依赖
"先置 False 再 flush"这个顺序。**如果把 6604 行的 `self._reasoning_box_opened = False`
挪到 flush 之后，就是无限递归。** 这是一处脆弱但正确的写法。

#### 2.7.3 开框与关框的宽度是分别测的

开框（推理）：

`cli.py:6576 @ 863e313`

```python
        if not getattr(self, "_reasoning_box_opened", False):
            self._reasoning_box_opened = True
            w = self._scrollback_box_width()
            r_label = " Reasoning "
            r_fill = w - 2 - len(r_label)
            _cprint(f"\n{_DIM}┌─{r_label}{'─' * max(r_fill - 1, 0)}┐{_RST}")
```

开框（响应）：

`cli.py:6799 @ 863e313`

```python
            w = self._scrollback_box_width()
            fill = w - 2 - HermesCLI._status_bar_display_width(label)
            _cprint(f"\n{_ACCENT}╭─{label}{'─' * max(fill - 1, 0)}╮{_RST}")
```

关框（响应）：

`cli.py:6927 @ 863e313`

```python
        # Close the response box
        if self._stream_box_opened:
            w = self._scrollback_box_width()
            _cprint(f"{_ACCENT}╰{'─' * (w - 2)}╯{_RST}")
```

两个细节：

1. **推理框用 `len(r_label)`，响应框用 `_status_bar_display_width(label)`。**
   `r_label = " Reasoning "` 是纯 ASCII，两者相等；但 `label` 来自 skin 配置
   （`_skin.get_branding("response_label", "⚕ Hermes")`，6783 行），可能含宽字符，
   所以响应框必须用显示宽度。**推理框如果哪天标签可配置，就会踩这个坑。**
2. **开框和关框各自调一次 `_scrollback_box_width()`**，中间隔着整个流式过程。
   期间 resize 会让上下边框宽度不一致。见 §3 缺陷 #8。

#### 2.7.4 `_stream_delta` 的推理标签过滤（本段最复杂的一段）

`cli.py:6643 @ 863e313`

```python
        _OPEN_TAGS = ("<REASONING_SCRATCHPAD>", "<think>", "<reasoning>", "<THINKING>", "<thinking>", "<thought>")
        _CLOSE_TAGS = ("</REASONING_SCRATCHPAD>", "</think>", "</reasoning>", "</THINKING>", "</thinking>", "</thought>")
```

难点在于**模型会在正文里提到这些标签**。作者的解法是"块边界"判定：

`cli.py:6649 @ 863e313`

```python
        # Check if we're entering a reasoning block.
        # Only match tags that appear at a "block boundary": start of the
        # stream, after a newline (with optional whitespace), or when nothing
        # but whitespace has been emitted on the current line.
        # This prevents false positives when models *mention* tags in prose
        # like "(/think not producing <think> tags)".
```

判定逻辑：

`cli.py:6675 @ 863e313`

```python
                    if idx == 0:
                        # At buffer start — only a boundary if we're at
                        # a line start (stream start or last emit ended
                        # with newline)
                        is_block_boundary = getattr(self, "_stream_last_was_newline", True)
                    else:
                        # Find last newline in the buffer before the tag
                        last_nl = preceding.rfind("\n")
                        if last_nl == -1:
                            # No newline in buffer — boundary only if
                            # last emit was a newline AND only whitespace
                            # has accumulated before the tag
                            is_block_boundary = (
                                getattr(self, "_stream_last_was_newline", True)
                                and preceding.strip() == ""
                            )
                        else:
                            # Text between last newline and tag must be
                            # whitespace-only
                            is_block_boundary = preceding[last_nl + 1:].strip() == ""
```

第二个难点：**标签会被切成多个 token**。开标签的处理是"末尾疑似前缀就先扣住"：

`cli.py:6708 @ 863e313`

```python
            # Could also be a partial open tag at the end — hold it back
            if not getattr(self, "_in_reasoning_block", False):
                # Check for partial tag match at the end (case-insensitive)
                safe = self._stream_prefilt
                for tag in _OPEN_TAGS:
                    tag_lower = tag.lower()
                    for i in range(1, len(tag)):
                        if prefilt_lower.endswith(tag_lower[:i]):
                            safe = self._stream_prefilt[:-i]
                            break
```

闭标签的处理是"永远留最长闭标签长度的尾巴"：

`cli.py:6749 @ 863e313`

```python
            max_tag_len = max(len(t) for t in _CLOSE_TAGS)
            if len(self._stream_prefilt) > max_tag_len:
                if self.show_reasoning:
                    # Route the safe prefix to reasoning display
                    safe_reasoning = self._stream_prefilt[:-max_tag_len]
                    self._stream_reasoning_delta(safe_reasoning)
                self._stream_prefilt = self._stream_prefilt[-max_tag_len:]
```

第三个难点：**模型提了开标签但从不闭合**。兜底在 flush：

`cli.py:6882 @ 863e313`

```python
    def _flush_stream(self) -> None:
        """Emit any remaining partial line from the stream buffer and close the box."""
        # If we're still inside a "reasoning block" at end-of-stream, it was
        # a false positive — the model mentioned a tag like <think> in prose
        # but never closed it.  Recover the buffered content as regular text.
        if getattr(self, "_in_reasoning_block", False) and getattr(self, "_stream_prefilt", ""):
            self._in_reasoning_block = False
            self._emit_stream_text(self._stream_prefilt)
            self._stream_prefilt = ""
```

**可迁移的教训**：流式过滤器必须同时处理"跨 token 的标签"、"prose 里提到标签"、
"标签不闭合"三种情况，且第三种只能在流结束时补救。

#### 2.7.5 表格重排：流式里唯一的"整块缓冲"

`cli.py:6832 @ 863e313`

```python
            # Hold table-shaped lines in a side-buffer so we can re-pad
            # the whole block once it ends.  Streaming line-by-line, we
            # cannot re-align mid-table without reflowing already-printed
            # rows; the cost is that the user sees the table appear in a
            # single batch when the block closes instead of row-by-row.
```

取舍讲得很干脆：**表格必须整块出，否则对不齐**。代价是 TTFT 观感变差。

而针对"长段落还没换行导致响应框空着"的观感问题，另有一招：

`cli.py:6863 @ 863e313`

```python
        # TTFT perception: while a long opening paragraph accumulates
        # without a newline, mirror its tail into the status-bar spinner
        # line so the user sees tokens arriving instead of a blank box.
        if (
            self._stream_buf
            and not self._in_stream_table
            and not self._stream_buf.lstrip().startswith("|")
            and len(self._stream_buf) >= 80
        ):
```

**把正文的尾巴镜像到 spinner 行**——用活动底盘补 scrollback 的观感。这是本段最漂亮的一处设计。

#### 2.7.6 为什么不再自己硬换行

`cli.py:6853 @ 863e313`

```python
        # Long partial lines are emitted ONLY at real newlines — we no
        # longer hard-wrap paragraphs at terminal width ourselves.  Each
        # logical line lands in scrollback as one line; the TERMINAL
        # soft-wraps it visually, and emulators (iTerm2/kitty/VTE/
        # xterm.js/Windows Terminal) rejoin soft-wrapped rows on copy,
        # so highlight-copy yields the original unwrapped text — same
        # outcome as the TUI's selection copy.  (The pre-July-2026 chunk
        # emitter baked real '\n's into every long paragraph, which is
        # exactly what polluted copy/paste.)
```

**这条值得单独记住**：终端 UI 里"自己换行"会污染用户的复制粘贴。
把换行交给终端的 soft-wrap，复制出来才是原文。

---

### 2.8 外部编辑器：一条绕过 accept_handler 的提交路径

#### 2.8.1 为什么要自己接管提交

`cli.py:6997 @ 863e313`

```python
    def _open_external_editor(self, buffer=None) -> bool:
        """Open the active input buffer in an external editor."""
```

前置守卫三连（TUI 未启动 / 命令在跑 / 模态在等）：

`cli.py:6999 @ 863e313`

```python
        app = getattr(self, "_app", None)
        if not app:
            _cprint(f"{_DIM}External editor is only available inside the interactive CLI.{_RST}")
            return False
        if self._command_running:
            _cprint(f"{_DIM}Wait for the current command to finish before opening the editor.{_RST}")
            return False
        if self._sudo_state or self._secret_state or self._approval_state or getattr(self, "_slash_confirm_state", None) or self._clarify_state:
            _cprint(f"{_DIM}Finish the active prompt before opening the editor.{_RST}")
            return False
```

核心：

`cli.py:7013 @ 863e313`

```python
        try:
            # Inline pastes so the editor (and the draft it submits) sees real
            # content; skip flag unconditionally so the editor-close text-change
            # doesn't re-collapse it, even when there was nothing to inline.
            self._inline_pastes(target_buffer)
            self._skip_paste_collapse = True
            # Open the editor, then submit the saved draft on a clean exit —
            # matching the TUI's Ctrl+G (openEditor), which sends the buffer
            # instead of requiring a second Enter. Submission in this CLI is
            # driven by the custom `enter` keybinding, NOT the buffer's
            # accept_handler, so validate_and_handle can't route through it;
            # chain a done-callback on the returned Task that re-uses the
            # real submit pipeline via _submit_editor_buffer().
            task = target_buffer.open_in_editor(validate_and_handle=False)
            if task is not None and hasattr(task, "add_done_callback"):
                task.add_done_callback(
                    lambda _t, b=target_buffer: self._submit_editor_buffer(b)
                )
            return True
```

**设计要点**：这个 CLI 的提交不走 prompt_toolkit 的 `accept_handler`，而走自定义的
`enter` 键绑定。所以 `open_in_editor(validate_and_handle=True)` 那条现成路子用不了，
只能 `validate_and_handle=False` + 手动挂 done-callback。

`_submit_editor_buffer` 因此必须**手工复刻 enter 处理器的所有分支**：

`cli.py:7036 @ 863e313`

```python
    def _submit_editor_buffer(self, buffer) -> None:
        """Submit the draft an external editor left in ``buffer``.

        Invoked from the Ctrl+G done-callback so saving the editor sends the
        prompt (TUI parity) instead of leaving it sitting in the input area.
        Mirrors the idle/queue branches of the `enter` keybinding handler:
        an empty save is ignored (never submits a blank turn), a slash command
        is dispatched, otherwise the text is routed through the same input
        queues the normal Enter path uses. Runs on the prompt_toolkit event
        loop via the Task callback, so it must be cheap and non-blocking.
        """
```

复刻了：空提交丢弃(7051)、`!` shell(7062)、斜杠命令(7076)、忙态分流(7091)。
**没复刻**：图片附件、`agent.redirect()` 快路径、`/steer`、首次忙态 onboarding 提示。
其中忙态分流的偏差是真 bug，见 §3 缺陷 #2。

#### 2.8.2 `_inline_pastes` 与一次性标志

`cli.py:7105 @ 863e313`

```python
    def _inline_pastes(self, buffer) -> None:
        """Replace collapsed-paste placeholders in ``buffer`` with real content.

        A big paste shows as a compact ``[Pasted text #N -> file]`` placeholder,
        but history recall and the external editor need the actual text — a bare
        reference is useless once the file is gone or on another machine. Inlining
        before ``reset(append_to_history=True)`` also lets prompt_toolkit persist
        the content through its normal path. Sets ``_skip_paste_collapse`` so the
        ensuing text-change doesn't re-collapse it.
        """
```

`_skip_paste_collapse` 是一次性的，由文本变更处理器消费：

`cli.py:16467 @ 863e313`

```python
            if _paste_just_collapsed[0] or self._skip_paste_collapse:
                _paste_just_collapsed[0] = False
                self._skip_paste_collapse = False
                _prev_newline_count[0] = text.count('\n')
                return
```

这解释了 7018 行为什么要**再设一次**：`_inline_pastes` 里设的那次会被它自己触发的
文本变更消费掉，7018 行这次是留给"编辑器关闭时的文本变更"的。注释说得很准。

粘贴引用展开本身用 try/except 而非 `exists()`，理由写得很好：

`cli.py:6536 @ 863e313`

```python
        def _expand_ref(match):
            path = Path(match.group(1))
            # Use try/except instead of path.exists() to avoid TOCTOU race:
            # the paste file may be deleted between check and read, causing
            # the input to be silently dropped (#17666).
            try:
                return path.read_text(encoding="utf-8")
            except (OSError, IOError):
                logger.warning("Paste file gone or unreadable, returning placeholder: %s", path)
                return match.group(0)
```

---

### 2.9 每轮工具账单（turn summary）

四个方法构成一条从"工具进度回调"到"轮末一行"的旁路：

`cli.py:5526 @ 863e313`

```python
    # ── Per-turn accounting (display.turn_summary / spinner_token_flow) ──
    #
    # Both features are CLI-only chrome. The tally is observed from the
    # tool-progress callback this class already receives on every tool call,
    # so nothing is threaded through the agent loop. Token flow reads the
    # agent's cumulative session counters (bumped per API call in
    # agent/conversation_loop.py) and subtracts a per-turn baseline.
```

**设计要点：零侵入。** 不改 agent loop，只在已有的 tool-progress 回调上挂个计数器。
token 数用"会话累计 − 本轮起点基线"算差值：

`cli.py:5583 @ 863e313`

```python
            self._turn_token_baseline = (
                getattr(agent, "session_output_tokens", 0) or 0
            ) if agent is not None else 0
```

`cli.py:5546 @ 863e313`

```python
            produced = (getattr(agent, "session_output_tokens", 0) or 0) - (
                getattr(self, "_turn_token_baseline", 0) or 0
            )
```

四道 gate 决定"这个表面要不要打这一行"：

`cli.py:5553 @ 863e313`

```python
    def _turn_summary_is_active(self) -> bool:
        """Whether the per-turn summary line should render for this surface.

        Gated off for: the config key, quiet/tool-progress-off mode, and any
        non-interactive path (single query, ``-Q``, gateway/messaging) — those
        surfaces either want machine-readable output or carry their own footer.
        """
        if not getattr(self, "_turn_summary_enabled", False):
            return False
        if getattr(self, "tool_progress_mode", "all") == "off":
            return False
        agent = getattr(self, "agent", None)
        if agent is not None and getattr(agent, "quiet_mode", False):
            return False
        if not getattr(self, "_interactive_turn", False):
            return False
        return True
```

`_interactive_turn` 只在 `run()` 的交互轮里为真：

`cli.py:4328 @ 863e313`

```python
        # True only while an interactive (run()-loop) turn is in flight. Single
        # query, -Q, and gateway paths never set it, which is what keeps the
        # summary line out of non-interactive surfaces.
        self._interactive_turn = False
```

生命周期挂在 `run()` 的 try/finally 上：

`cli.py:17506 @ 863e313`

```python
                    self._agent_running = True
                    self._interactive_turn = True
                    self._pet_turn_error = False
                    self._pet_reasoning = False
                    self._turn_summary_begin()
```

`cli.py:17523 @ 863e313`

```python
                        # Post-turn accounting line (display.turn_summary).
                        # Emitted after the response box, before the prompt
                        # returns, so it reads as a footer for the turn.
                        self._turn_summary_emit()
                        self._interactive_turn = False
```

**注意第二条 gate 的副作用**：`tool_progress_mode == "off"` 就不打账单。
而 `/focus` 会把模式强推到 "off"：

`hermes_cli/focus_view.py:36 @ 863e313`

```python
FOCUS_TOOL_PROGRESS_MODE = "off"
```

`cli.py:4262 @ 863e313`

```python
        if self._focus_view_enabled:
            from hermes_cli.focus_view import (
                FOCUS_TOOL_PROGRESS_MODE,
                normalize_tool_progress_mode,
            )

            self._focus_saved_tool_progress = normalize_tool_progress_mode(
                self.tool_progress_mode
            )
            self.tool_progress_mode = FOCUS_TOOL_PROGRESS_MODE
```

即：**开 focus view 会连带关掉每轮账单行**。但 `__init__` 里的注释明确说 focus 是
"purely cosmetic"、只走"EXISTING suppression path"：

`cli.py:4253 @ 863e313`

```python
        # focus_view: display-only reduced-output mode (/focus). When on, the
        # tool-progress mode is snapped to "off" so the EXISTING suppression
        # path hides per-tool lines, and the pre-focus mode is stashed so
        # /focus off restores it. Purely cosmetic — never changes what is sent
        # to the model. See hermes_cli/focus_view.py.
```

"复用现有抑制路径"的代价就是**顺带触发了那条路径上所有别的 gate**。这是"复用状态位来表达意图"
的经典副作用，值得作为设计教训记下（见 §5.2）。

---

### 2.10 忙态与慢命令

`cli.py:6974 @ 863e313`

```python
    @contextmanager
    def _busy_command(self, status: str, *, blocks_input: bool = True):
        """Expose a temporary busy state in the TUI while a slash command runs.

        Most synchronous slash commands must reserve the composer because their
        completion changes the active session state. Manual compression is safe
        to draft through: the queued input is processed against the compacted
        history after the command completes.
        """
        previous_blocks_input = getattr(self, "_command_blocks_input", False)
        self._command_running = True
        self._command_blocks_input = blocks_input
        self._command_status = status
        self._invalidate(min_interval=0.0)
        try:
            print(f"⏳ {status}")
            yield
        finally:
            self._command_running = False
            self._command_blocks_input = previous_blocks_input
            self._command_status = ""
            self._invalidate(min_interval=0.0)
```

两个细节：
1. `_invalidate(min_interval=0.0)` —— 用节流函数但把节流关掉，**仍然保留 resize guard**。
   这与 `_paint_now()`（完全绕过）是不同的选择，说明作者认为忙态入场没有模态那么急。
2. `_command_blocks_input` 是**保存/恢复**而非置回 False，支持嵌套。

---

## 3. 可疑缺陷清单

### #1 `display.compact` 配置项永远不生效（死配置）

**现象**：在 `config.yaml` 里写 `display.compact: true` 对交互式 CLI 没有任何效果。

**锚点** `cli.py:4248 @ 863e313`

```python
        self.compact = compact if compact is not None else CLI_CONFIG["display"].get("compact", False)
```

**为什么可疑**：`compact` 形参的默认值是 `False`，不是 `None`：

`cli.py:4223 @ 863e313`

```python
        compact: bool = False,
```

而唯一的生产调用链每一环都保证传的是 bool：

`hermes_cli/main.py:2729 @ 863e313`

```python
        "compact": getattr(args, "compact", False),
```

`cli.py:18040 @ 863e313`

```python
    compact: bool = False,
```

`cli.py:18183 @ 863e313`

```python
        compact=compact,
```

所以 `compact is not None` 恒为真，右分支（读配置）永远不执行。
而配置里确实定义了这个键：

`hermes_cli/config_defaults.py:1073 @ 863e313`

```python
        "compact": False,
```

文档也在教用户用它：

`website/docs/user-guide/configuration.md:1646 @ 863e313`

```
  compact: false          # Compact output mode (less whitespace)
```

`self.compact` 的实际消费点：

`cli.py:7209 @ 863e313`

```python
        use_compact = self.compact or term_width < 80
```

**触发条件**：用户在 config.yaml 设 `display.compact: true` 且终端 ≥ 80 列 → 仍然是完整横幅。

**置信度**：**高**。整条链路已逐环核实，且 `tui_gateway/slash_worker.py:144` 显式传
`compact=True` 说明形参就是给调用方用的。

---

### #2 编辑器提交在 `busy_input_mode="interrupt"` 下会打断当前轮，却告诉用户"已排队"

**现象**：agent 正在跑，用户按 Ctrl+G 打开编辑器写完保存，屏幕上显示
`Queued for the next turn: …`，但当前这一轮实际上被打断了。

**锚点** `cli.py:7090 @ 863e313`

```python
        # Regular prompt: route through the same queues the Enter handler uses.
        if self._agent_running:
            # Agent busy → honour the configured busy-input behaviour by
            # queueing for the next turn (the safe default; interrupt/steer
            # remain reachable via the normal Enter path).
            self._interrupt_queue.put(text) if self.busy_input_mode == "interrupt" else self._pending_input.put(text)
            preview = text[:80] + ("..." if len(text) > 80 else "")
            _cprint(f"  Queued for the next turn: {preview}")
```

**为什么可疑**：三重不一致。

1. **注释与代码相反**。注释说"queueing for the next turn"、"interrupt/steer remain
   reachable via the normal Enter path"（言下之意这里不做 interrupt），
   而代码在 `interrupt` 模式下恰恰投进 `_interrupt_queue`。
2. **消息与行为相反**。无论走哪条分支都打印 `Queued for the next turn`。
   投进 `_interrupt_queue` 的语义不是排队，是打断——对照正常 Enter 路径，
   两条分支的用户提示是分开的：

   `cli.py:15477 @ 863e313`

   ```python
                       if _effective_mode == "queue":
                           # Queue for the next turn instead of interrupting
                           self._pending_input.put(payload)
                           preview = text if text else f"[{len(images)} image{'s' if len(images) != 1 else ''} attached]"
                           _cprint(f"  Queued for the next turn: {preview[:80]}{'...' if len(preview) > 80 else ''}")
   ```

   `cli.py:15498 @ 863e313`

   ```python
                           if redirected:
                               preview = text[:80] + ("..." if len(text) > 80 else "")
                               _cprint(f"  {_ACCENT}↪ Redirected current turn: '{preview}'{_RST}")
   ```

3. **少了 redirect 快路径**。正常 Enter 在 interrupt 模式下会**先试** `agent.redirect(text)`
   （软重定向，不杀轮），失败才落到 `_interrupt_queue`：

   `cli.py:15482 @ 863e313`

   ```python
                       elif _effective_mode == "interrupt":
                           if not images and text:
                               try:
                                   if (
                                       self.agent is not None
                                       and getattr(
                                           self.agent,
                                           "_supports_active_turn_redirect",
                                           False,
                                       )
                                       is True
                                       and hasattr(self.agent, "redirect")
                                   ):
                                       redirected = bool(self.agent.redirect(text))
                               except Exception:
                                   redirected = False
   ```

   编辑器路径直接跳过了这一步，等于把"软重定向"降级成"硬打断"。

另外 `steer` 模式在编辑器路径下静默降级为 `queue`（走 else 分支进 `_pending_input`）——
这一条**与注释相符**，不算 bug，但和 interrupt 分支放在同一个三元表达式里，
使得整行的意图无法从代码读出。

**触发条件**：`display.busy_input_mode` 为默认的 `"interrupt"`（`cli.py:4288-4294`），
agent 正在跑，用户用外部编辑器提交。

**置信度**：**高**（消息错误是确定的；"应不应该 redirect"属于设计意图判断，但注释已明确表态）。

---

### #3 `_on_notice_clear` 是 no-op，导致同一 key 的过期通知在轮末被一起打出来

**现象**：一轮里发生了多次 API 调用且用量跨了档（如 50% → 75%），
轮末会同时打印"50% 已用"和"75% 已用"两行，其中第一行是已被 agent 撤销的。

**锚点** `cli.py:6393 @ 863e313`

```python
    def _on_notice_clear(self, key: str) -> None:
        """Notice cleared. The REPL prints lines (no persistent slot to wipe), so
        this drops any still-queued notice with that key is not tracked by key here;
        it's a no-op for rendering — kept so the agent's clear callback is bound
        symmetrically with the show callback (and so future REPL UIs can hook it)."""
        return
```

**为什么可疑**：docstring 的辩护是"REPL 打的是行，没有持久槽位可擦"。
对**已经打印出去**的行，这是对的。但 CLI 恰恰**不是立刻打印**的——它排队到轮末：

`cli.py:6368 @ 863e313`

```python
            if not hasattr(self, "_pending_credit_notices"):
                self._pending_credit_notices = []
            self._pending_credit_notices.append((level, text))
```

所以在 `_on_notice` 与 `_flush_credit_notices` 之间存在一个**真实的、可擦的队列**，
只是队列元素 `(level, text)` 没存 `key`，擦不了。而 `AgentNotice` 是带 key 的：

`agent/credits_tracker.py:210 @ 863e313`（`AgentNotice` dataclass 字段）

```python
    text: str
    level: str = "info"            # info | warn | error | success
    kind: str = "sticky"           # sticky | ttl
    ttl_ms: Optional[int] = None   # honored only when kind == "ttl"
    key: Optional[str] = None      # dedupe / fired-once-latch / clear key
```

上游确实按"先 clear 再 show"的替换语义发：

`run_agent.py:3939 @ 863e313`

```python
            for key in to_clear:        # clears FIRST …
                self._emit_notice_clear(key)
            for notice in to_show:      # … then shows (depleted lands last in a latest-wins slot)
                self._emit_notice(notice)
```

档位变化时同一 key 先撤后发：

`agent/credits_tracker.py:347 @ 863e313`

```python
    if target_band != shown_band:
        if CREDITS_USAGE_KEY in active:
            to_clear.append(CREDITS_USAGE_KEY)
            active.discard(CREDITS_USAGE_KEY)
```

**触发条件**：一轮内多次 API 调用（多工具轮次），期间 credits 用量跨越 50/75/90 档，
或 `paid_access` 状态翻转。

**修法（备记）**：把队列元素改成 `(level, text, key)`，`_on_notice_clear` 里
`self._pending_credit_notices = [t for t in pending if t[2] != key]`。三行。

**置信度**：**中高**。逻辑链完整；未实测（需要真实 credits 头部，本环境无凭据）。

---

### #4 pet 动画线程对所有用户无条件常驻，且每 2.5s 读一次配置文件

**现象**：任何交互式 `hermes chat` 会话都多一个后台线程，每 0.16s 醒一次，
每 2.5s 做一次 `stat` + config deepcopy——即使用户从未开启过 pet。

**锚点** `cli.py:5797 @ 863e313`

```python
    def _pet_anim_loop(self) -> None:
        """Advance the frame + invalidate on a timer while a pet is enabled."""
        while self._pet_anim_running:
            time.sleep(self._PET_FRAME_INTERVAL)
            now = time.monotonic()
            if now - self._pet_cfg_checked >= self._PET_CFG_INTERVAL:
                self._pet_cfg_checked = now
                self._pet_resolve_config()
            if not self._pet_enabled:
                continue
```

**为什么可疑**：`_pet_resolve_config()` 在 `if not self._pet_enabled: continue` **之前**，
所以短路不掉。而启动是无条件的，注释还写着"no-op when no pet enabled"：

`cli.py:17802 @ 863e313`

```python
                # Drive the petdex mascot animation (no-op when no pet enabled).
                self._pet_start_anim()
```

配置读取用的是带 deepcopy 的版本：

`cli.py:5636 @ 863e313`

```python
            cfg = load_config()
```

仓库自己给只读调用方准备了免 deepcopy 的版本，并量化过成本：

`hermes_cli/config.py:3142 @ 863e313`

```python
    Why this exists: ``load_config()`` cache-hit cost is ~265us per call,
    half of which (~135us) is the defensive deepcopy. The agent loop calls
    into config reads (timeouts, thresholds, feature flags) ~20-50x per
    conversation; skipping deepcopy here removes a measurable allocation
    source and the GC pressure that comes with it.
```

**触发条件**：任何交互式会话，无条件。

**置信度**：**高**（代码路径确定）。对"这算不算缺陷"可以争论——2.5s 一次 265us
是可忽略的 CPU，但"注释宣称 no-op 而实际不是"以及"6.25 次/秒的空转唤醒"
在移动端/低功耗场景（Termux）是真实成本。

---

### #5 pet 动画绕过 `_invalidate` 的 resize guard 直接 `app.invalidate()`

**现象**：SIGWINCH 之后的 0.12s 去抖窗口内，pet 线程仍会强制重绘，
而这正是 `_invalidate` 的 guard 要阻止的事。

**锚点** `cli.py:5809 @ 863e313`

```python
            app = getattr(self, "_app", None)
            if app is not None:
                try:
                    app.invalidate()
                except Exception:
                    pass
```

**为什么可疑**：`_invalidate` 的 docstring 把使用边界写得非常明确——
**只有用户阻塞型模态**才可以绕过 guard：

`cli.py:4797 @ 863e313`

```python
        Use this for spinner frames, streaming token flushes, and other
        repaints that can fire many times per second — the throttle prevents
        terminal blinking on slow/SSH connections, and the resize-recovery
        guard avoids stamping footer/status-bar chrome into scrollback while a
        SIGWINCH reflow is in flight.

        Do NOT use this for user-blocking modal prompts (approval / clarify /
        sudo). Those are rare, one-shot, user-blocking events that must paint
        immediately; route them through ``self._app.invalidate()`` directly, the
        same way the modal key-binding handlers already use.
```

pet 帧推进是教科书式的"high-frequency background update"，属于**应该**走 `_invalidate` 的一类，
却直接调了 `app.invalidate()`。对照同一段里 `_paint_now` 的写法——它绕过 guard 是**写了理由的**：

`cli.py:4818 @ 863e313`

```python
    def _paint_now(self) -> None:
        """Immediate, unthrottled repaint for user-blocking modal prompts.
```

pet 循环没有任何说明。

**触发条件**：启用 pet + 调整终端窗口大小。窗口 0.12s（去抖）+ 0.35s（解除抑制），
期间最多 ~3 次越权重绘。

**置信度**：**中高**。违反约定是确定的；"是否真的会造成幽灵栏"取决于 prompt_toolkit
在 `_status_bar_suppressed_after_resize=True` 时渲染的内容（状态栏 filter 为 False、
分隔线高度为 0，所以画出来的底盘很薄），实际危害可能小于设计意图。

---

### #6 逐轮计时器用墙钟 `time.time()`，与同段其它计时器不一致

**现象**：会话中系统时钟被 NTP 校正或时区/DST 变更时，状态栏的 ⏱ 计时会跳变
或被钳到 `0s`。

**锚点** `cli.py:5186 @ 863e313`

```python
        elapsed = time.time() - prompt_start_time if prompt_start_time is not None else prompt_duration
        elapsed = max(0.0, elapsed)
```

起点同样是墙钟：

`cli.py:14103 @ 863e313`

```python
            self._prompt_start_time = time.time()
```

`cli.py:5218 @ 863e313`

```python
        idle = max(0.0, time.time() - last_finished_at)
```

**为什么可疑**：同一段里其它三个计时器都用 monotonic：

`cli.py:5510 @ 863e313`

```python
            elapsed = time.monotonic() - t0
```

`cli.py:5581 @ 863e313`

```python
            self._turn_summary_start = time.monotonic()
```

`cli.py:6168 @ 863e313`

```python
        secs = int(_t.monotonic() - stashed_at)
```

`_invalidate` 的节流也是 monotonic（`cli.py:4813`）。**唯独状态栏的两个"用户直接读的数字"
用墙钟**——正好是最不该跳的那两个。`max(0.0, …)` 会把时钟回拨的负值钳成 0，
表现为"计时器突然归零"，比显示负数更迷惑。

**触发条件**：长会话 + NTP 步进 / 手动改系统时间 / 容器时钟同步。

**置信度**：**高**（代码事实确定），影响**低**（罕见且只是显示）。

---

### #7 pet 窗口的高度与内容在同一次渲染里两次独立求值，可能不一致

**现象**：某一帧 pet 精灵被截掉一行或多出一条空行。

**锚点** `cli.py:5787 @ 863e313`

```python
    def _pet_widget_height(self) -> int:
        """Visible rows for the pet window — 0 collapses it when no pet shows."""
        with self._pet_lock:
            if not self._pet_enabled or self._pet_renderer is None:
                return 0
            grids = self._pet_frames_for(self._derive_pet_state())
```

`cli.py:5755 @ 863e313`

```python
    def _pet_fragments(self):
        """Return prompt_toolkit FormattedText for the current pet frame, or []."""
        with self._pet_lock:
            if not self._pet_enabled or self._pet_renderer is None:
                return []
            state = self._derive_pet_state()
            grids = self._pet_frames_for(state)
```

**为什么可疑**：两个回调各自取锁、各自调 `_derive_pet_state()`，锁在两次调用之间是**放开的**。
`_derive_pet_state` 的返回值依赖三个会在别的线程变化的量：反应 beat 的到期时间（`time.monotonic()`
比较，见 5717）、`_agent_running`（agent 线程写）、`_pet_reasoning`（工具进度回调写）。
不同 state 的 sprite 行数不必相同（`len(grids[0])`），所以 prompt_toolkit 拿到的
height 与 content 行数可能对不上。

同一模式在 spinner 上也存在——`_spinner_widget_height` 内部先跑一遍 `_render_spinner_text()`：

`cli.py:5488 @ 863e313`

```python
    def _spinner_widget_height(self, width: Optional[int] = None) -> int:
        """Return the visible height for the spinner/status text line above the status bar."""
        spinner_line = self._render_spinner_text()
```

而内容回调再跑一遍（`cli.py:16623-16627`）。spinner 文本含实时秒数，两次求值必然不同，
只是宽度差通常不足以改变 `ceil(width/cols)`。

**触发条件**：pet 启用 + 状态在两次回调之间翻转（agent 起停、反应 beat 到期）。

**置信度**：**中**。竞态是代码事实；能否被肉眼看到取决于 prompt_toolkit 的
height/content 求值间隔与是否同帧，未实测。

---

### #8 scrollback 框的上下边框宽度分别测量，resize 后会不对齐

**现象**：流式输出中途调整终端宽度，响应框/推理框的上边框和下边框长度不同。

**锚点**（开框）`cli.py:6799 @ 863e313`

```python
            w = self._scrollback_box_width()
            fill = w - 2 - HermesCLI._status_bar_display_width(label)
            _cprint(f"\n{_ACCENT}╭─{label}{'─' * max(fill - 1, 0)}╮{_RST}")
```

（关框）`cli.py:6928 @ 863e313`

```python
        if self._stream_box_opened:
            w = self._scrollback_box_width()
            _cprint(f"{_ACCENT}╰{'─' * (w - 2)}╯{_RST}")
```

推理框同理（开 6578、关 6602）。

**为什么可疑**：`w` 不被记住。`_scrollback_box_width` 每次现问终端：

`cli.py:5465 @ 863e313`

```python
        if width is None:
            try:
                width = shutil.get_terminal_size((80, 24)).columns
            except Exception:
                width = 80
        return max(32, int(width or 80))
```

一次流式响应可能持续几十秒，期间 resize 完全可能。作者在 `_scrollback_box_width` 的
docstring 里承认"已打印内容的 reflow 是可接受的观感瑕疵"，但那说的是**终端重排已有内容**，
不是**新画的下边框用了新宽度**——后者是本进程自己造成的不一致。

**触发条件**：流式响应进行中调整终端列宽。

**置信度**：**中高**。代码事实确定；观感影响小，作者可能有意接受。

---

### #9 `_pet_frames_for` 会把异常结果永久缓存

**现象**：渲染器一次瞬时失败后，该动画状态在整个会话里永久变成空（pet 该状态不再显示）。

**锚点** `cli.py:5739 @ 863e313`

```python
    def _pet_frames_for(self, state: str) -> list:
        """Return (and cache) the half-block grids for one state."""
        cached = self._pet_frames_cache.get(state)
        if cached is not None:
            return cached
        renderer = self._pet_renderer
        if renderer is None:
            return []
        try:
            count = renderer.frame_count(state) or 1
            grids = [renderer.cells(state, i, cols=self._pet_cols) for i in range(count)]
        except Exception:
            grids = []
        self._pet_frames_cache[state] = grids
        return grids
```

**为什么可疑**：`except` 分支把 `grids = []` **写进了缓存**，之后 `cached is not None`
永远为真（空 list 不是 None），再也不会重试。缓存只在 `_pet_resolve_config` 检测到
pet/几何变化时才清：

`cli.py:5674 @ 863e313`

```python
                    self._pet_frames_cache.clear()
```

而 `renderer is None` 那条路**不写缓存**（5745-5746 直接 return []），
两条失败路径的处理不一致，说明缓存写入位置是无意的。

**触发条件**：sprite 表读取瞬时失败（文件被替换、磁盘抖动、`hermes pets` 正在改文件）。

**置信度**：**中高**。代码事实确定；触发条件罕见。

---

### #10 `_recover_after_resize` 的 docstring 第二段与它自己的代码相反

**现象**：文档说"不要在 prompt_toolkit 的 erase 之前 reset renderer"，代码在宽度变化时正是这么做的。

**锚点**（docstring）`cli.py:4918 @ 863e313`

```python
        Let prompt_toolkit's own resize path run with its renderer cursor
        cache intact. Its Application._on_resize() starts with
        renderer.erase(leave_alternate_screen=False), which needs the cached
        cursor position to move back to the live prompt origin before
        erase_down(). Resetting the renderer before that erase loses the
        origin and can leave stale prompt glyphs after a narrow resize.
```

（代码）`cli.py:4980 @ 863e313`

```python
        if width_changed:
            try:
                self._clear_prompt_toolkit_screen(app, rebuild_scrollback=False)
                _replay_output_history()
            except Exception:
                pass
```

而 `_clear_prompt_toolkit_screen` 的最后一步就是 reset：

`cli.py:4904 @ 863e313`

```python
            renderer.reset(leave_alternate_screen=False)
```

**为什么可疑**：docstring 第二段是**旧版本的设计说明**，第四段（4932 起）才是当前实现的说明，
两段共存且直接冲突。测试固定的是**当前实现**：

`tests/cli/test_cli_force_redraw.py:57 @ 863e313`

```python
        bare_cli._recover_after_resize(app, original_on_resize)

        # Viewport cleared and transcript replayed BEFORE prompt_toolkit's resize.
        assert "erase" in events
        assert "replay" in events
        assert events.index("erase") < events.index("original_resize")
```

**触发条件**：读文档的人（人或 AI）按第二段行事。

**置信度**：**高**（纯文档层面，已逐行比对）。

---

### #11 `original_on_resize()` 抛异常时状态栏会永久隐藏到下次提交

**现象**：SIGWINCH 处理中 prompt_toolkit 自己的 resize 抛异常，之后状态栏和输入分隔线
一直不见，直到用户提交一次输入。

**锚点** `cli.py:4986 @ 863e313`

```python
        if new_width is not None:
            self._last_resize_width = new_width
        original_on_resize()
        self._schedule_status_bar_unsuppress(app)
```

**为什么可疑**：4962 行已经把 `_status_bar_suppressed_after_resize` 置 True，
而解除它的调度在 `original_on_resize()` **之后**且没有 try/finally。
`_schedule_status_bar_unsuppress` 自己是 fail-open 的：

`cli.py:5029 @ 863e313`

```python
        except Exception:
            # Fail open: never leave the bar stuck hidden.
            self._status_bar_suppressed_after_resize = False
```

但它压根没被调用。docstring 明确说这个 timer 的存在就是为了"bar returns on its own during idle"
（4952 行），而异常路径正好绕过了它。

对照 `_schedule_resize_recovery` 的整体 try/except（5074-5076）——那一层能兜住
`_recover_after_resize` 抛出的异常并**再调一次** `_recover_after_resize`（可能又抛），
但兜不住"抑制标志已置位"这个副作用。

**触发条件**：prompt_toolkit 的 `_on_resize` 抛异常（输出已关闭、终端断开、
resize 与 app 退出竞争）。

**置信度**：**中**。异常本身罕见，但一旦发生，用户看到的是"状态栏消失了"这种难以归因的现象。

---

### #12 `model_short` 用 `len()` 截断，与本段自建的显示宽度体系相悖

**锚点** `cli.py:5241 @ 863e313`

```python
        if len(model_short) > 26:
            model_short = f"{model_short[:23]}..."
```

**为什么可疑**：同一个类里专门写了一个方法解释"`len()` 不够用"：

`cli.py:5387 @ 863e313`

```python
        """Return terminal cell width for status-bar text.

        len() is not enough for prompt_toolkit layout decisions because some
        glyphs can render wider than one Python codepoint. Keeping the status
        bar within the real display width prevents it from wrapping onto a
        second line and leaving behind duplicate rows.
        """
```

模型名可以来自用户配置的别名（`_reverse_alias_for_display`，见 5232），完全可能是中文/日文。
26 个 CJK 字符 = 52 单元格，直接把窄档状态栏撑爆。最终的整体宽度复核（6155）会兜住，
但兜法是**把整条栏降级成一段纯文本**（丢掉所有样式），而不是只截模型名。

**触发条件**：`model_aliases` 里配了 CJK 别名。

**置信度**：**中**。代码事实确定；触发需要特定配置。

---

### #13 `🗜️` 带变体选择符，违反本段自己定的"不用变体选择符"约定

**锚点**（约定）`cli.py:5180 @ 863e313`

```python
        Emoji prefix: ⏱ when turn is live, ⏲ when frozen or fresh start.
        Uses width-1 (no variation selector) glyphs so the status bar stays
        aligned in monospace terminals.
```

（违反）`cli.py:5930 @ 863e313`

```python
                    parts.append(f"🗜️ {compressions}")
```

同样的字面量还出现在 5961、6039、6088。已用脚本核对码点：
`🗜️` = U+1F5DC + **U+FE0F**（变体选择符），而 ⏱/⏲ = U+23F1/U+23F2（无 VS）。

**为什么可疑**：不同终端对"基础字符 + VS16"的宽度处理不一致（有的按 1 格、有的按 2 格），
正是 5180 行那条注释想避免的情况。另外 `⚕`(U+2695)、`⊙`(U+2299)、`▶`、`⚙`、`⛓`、`📌`
在状态栏里混用，宽度类别不统一。

**触发条件**：发生过上下文压缩（`compressions > 0`）时状态栏多出这个段。

**置信度**：**中**。约定冲突确定；实际错位取决于终端与 `get_cwidth` 的实现，未实测。

---

### #14 `_tui_input_rule_height` 在渲染回调里 `raise`

**锚点** `cli.py:5474 @ 863e313`

```python
        if position not in {"top", "bottom"}:
            raise ValueError(f"Unknown input rule position: {position}")
```

**为什么可疑**：这个方法是 prompt_toolkit `Window(height=…)` 的回调：

`cli.py:17071 @ 863e313`

```python
        input_rule_top = Window(
            char='─',
            height=lambda: cli_ref._tui_input_rule_height("top"),
            style='class:input-rule',
        )
```

渲染回调里抛异常会把整个重绘打断。当前只有两个字面量调用点，所以不会触发；
但同段所有别的渲染回调都是 fail-soft 的（`_pet_fragments` 返回 []、
`_get_status_bar_fragments` 整体 try/except、`_render_stash_panel` 的调用点 17141 有 except），
唯独这里选择 raise。**风格不一致，且这一处的"防御"防的是开发者错误，代价却由用户承担。**

**置信度**：**低**（当前不可触发），仅记为设计一致性问题。

---

### #15 `_open_external_editor` 失败时留下未消费的 `_skip_paste_collapse=True`

**锚点** `cli.py:7017 @ 863e313`

```python
            self._inline_pastes(target_buffer)
            self._skip_paste_collapse = True
```

`cli.py:7032 @ 863e313`

```python
        except Exception as exc:
            _cprint(f"{_DIM}Failed to open external editor: {exc}{_RST}")
            return False
```

**为什么可疑**：标志在 `open_in_editor()` 之前置位，异常路径不复位。
它会被**下一次任意文本变更**吞掉（16467-16469），也就是用户接下来输入的第一个字符，
使得那一次的大粘贴折叠被跳过。

**触发条件**：`$EDITOR` 未设置 / 编辑器无法启动，紧接着用户粘贴大段文本。

**置信度**：**低**（影响极小，且自愈）。

---

### #16 `_claim_active_session` 每次成功都注册一个新的 atexit 回调

**锚点** `cli.py:4776 @ 863e313`

```python
        self._active_session_lease = lease
        try:
            atexit.register(self._release_active_session)
        except Exception:
            pass
        return True
```

**为什么可疑**：开头的早退只挡住"当前已持有租约"的情况：

`cli.py:4757 @ 863e313`

```python
        if self._active_session_lease is not None:
            return True
```

`_release_active_session` 会把它置回 None（`cli.py:4792`），
之后再 claim 就会注册第二个 atexit 回调。回调本身幂等（`lease is None` 时直接 return），
所以不会出错，只是 atexit 表里堆积。

**置信度**：**低**（无功能影响）。

---

## 4. 与文档/注释的出入

### 4.1 `__init__` 里"CLI args > env vars > config file"与紧随三行自相矛盾

`cli.py:4363 @ 863e313`

```python
        # Configuration - priority: CLI args > env vars > config file
        # Model comes from: CLI arg or config.yaml (single source of truth).
        # LLM_MODEL/OPENAI_MODEL env vars are NOT checked — config.yaml is
        # authoritative.  This avoids conflicts in multi-agent setups where
        # env vars would stomp each other.
```

第一行说 env 排在 config 前面，后三行说 model 根本不读 env。实际代码：

`cli.py:4371 @ 863e313`

```python
        self.model = model or _config_model or _DEFAULT_CONFIG_MODEL
```

**以代码为准**：model 只看 CLI 参数和 config，不看 env。第一行注释是遗留的通用说明，
放错了位置。

（同一函数里 `max_tokens` 确实是 env 优先，见 4379-4384；`max_turns` 是
CLI > config > env，见 4436-4455。所以"优先级"在这个函数里根本不是统一的，
一行总纲注释注定不准。）

### 4.2 `display.compact` 被文档教学、被 defaults 定义，但代码路径不可达

见 §3 缺陷 #1。文档侧锚点：

`website/docs/user-guide/configuration.md:1646 @ 863e313`

```
  compact: false          # Compact output mode (less whitespace)
```

**以代码为准**：交互式 CLI 里这个键无效；要 compact 只能靠 `--compact` 或终端 < 80 列
（`cli.py:7209`）。

### 4.3 `_pet_start_anim` 的"no-op when no pet enabled"不成立

`cli.py:17802 @ 863e313`

```python
                # Drive the petdex mascot animation (no-op when no pet enabled).
                self._pet_start_anim()
```

见 §3 缺陷 #4。**以代码为准**：线程无条件起，且配置轮询不受 `_pet_enabled` 短路。

### 4.4 `_on_notice_clear` 的 docstring 语法破碎且结论不成立

`cli.py:6394 @ 863e313`

```python
        """Notice cleared. The REPL prints lines (no persistent slot to wipe), so
        this drops any still-queued notice with that key is not tracked by key here;
```

两个问题：(a) 语法不通，像两句话被合并时漏删了半句；
(b) "no persistent slot to wipe"不成立——`_pending_credit_notices` 就是一个可擦的槽位。
见 §3 缺陷 #3。

### 4.5 `_submit_editor_buffer` 的注释与其 interrupt 分支相反

`cli.py:7092 @ 863e313`

```python
            # Agent busy → honour the configured busy-input behaviour by
            # queueing for the next turn (the safe default; interrupt/steer
            # remain reachable via the normal Enter path).
```

见 §3 缺陷 #2。**以代码为准**：interrupt 模式下这里就是打断，不是排队。

### 4.6 `_recover_after_resize` docstring 第二段 vs 第四段 + 代码

见 §3 缺陷 #10。**以代码 + 测试为准**：宽度变化时**要**在 prompt_toolkit resize 前
erase + reset。

### 4.7 `_format_prompt_elapsed` docstring 的示例与代码输出不一致

`cli.py:5175 @ 863e313`

```python
        Keeps seconds visible at all scales so it increments smoothly:
            59s → 1m → 1m 1s → ... → 1m 59s → 2m → 2m 1s → ...
            59m 59s → 1h → 1h 0m 1s → ...
            23h 59m 59s → 1d → 1d 0h 1m → ...
```

代码：

`cli.py:5196 @ 863e313`

```python
        if days > 0:
            time_str = f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            time_str = f"{hours}h {minutes}m {seconds}s" if seconds else f"{hours}h {minutes}m"
```

整点 1 小时（h=1,m=0,s=0）代码输出 `1h 0m`，文档写 `1h`；
整 1 天代码输出 `1d 0h 0m`，文档写 `1d`。**以代码为准**。
（分钟档倒是对的：m>0 且 s=0 → `f"{minutes}m"`。）

### 4.8 `_status_bar_snapshot` 注释"no DB hit per repaint"成立，但只因为构造时已经打过

`cli.py:5334 @ 863e313`

```python
        # Standing /goal state (Ralph loop). GoalManager is cached on self and
        # keeps its state in memory, so this is a cheap attribute read — no DB
        # hit per repaint.
```

这句话对**稳态**成立，但 `_get_goal_manager` 在 `session_id` 变化时会重建，
重建时会 `load_config()` 并 `load_goal(session_id)`（读盘）：

`hermes_cli/goals.py:1249 @ 863e313`

```python
        self._state: Optional[GoalState] = load_goal(session_id)
```

`cli.py:10574 @ 863e313`

```python
        try:
            cfg = load_config() or {}
            goals_cfg = cfg.get("goals") or {}
            max_turns = int(goals_cfg.get("max_turns", 20) or 20)
```

即 `/new` 或压缩导致会话切分之后的**第一次重绘**会读盘。注释没写这个例外。
（不算缺陷，注释加个"after a session switch"就准确了。）

---

## 5. 移交

### 5.1 本段与其它段的接口

- **`__init__` → 所有段**：161 个属性是全类的状态字典。凡别的段读 `self._xxx`，
  定义大概率在 4213–4753 之间。特别注意**懒属性**（`__init__` 里没有、靠 `hasattr`/`getattr`
  建的）：`_pending_credit_notices`(6368)、`_stream_prefilt`(6647)、`_reasoning_buf`(6583)、
  `_deferred_content`(6767)、`_reasoning_box_opened`(6577)、`_stream_last_was_newline`(6660)、
  `_stream_text_ansi`(6794)、`_voice_record_key_display_cache`(5862)、`_reasoning_shown_this_turn`(6571)、
  `_goal_manager`(10570)。这些属性在 `object.__new__(HermesCLI)` 构造的测试夹具里也能工作，
  测试因此大量使用 `bare_cli` 夹具（见 `tests/cli/test_cli_force_redraw.py:21`）。
- **渲染回调 → `run()` 里的布局定义（16600–17400）**：本段只定义"画什么"，
  "挂在哪"全在 `run()` 里。两段必须一起读才能理解一个部件。已建立的对应表见 §1.2 + §2.4.1。
- **`_stream_delta` ← agent**：由 `cli_agent_setup_mixin.py:514` 绑定，且只在
  `streaming_enabled` 为真时绑定。
- **`_turn_summary_record` ← `_on_tool_progress`(12080)**：跨段。

### 5.2 可迁移的设计原则（写给"自己造 harness"的自己）

1. **"活动底盘"与"滚动历史"是两种不同的像素，边界处必然出事**。
   终端 UI 的绝大多数诡异 bug（幽灵状态栏、复制粘贴被污染、横幅消失）都在这条边界上。
   设计时就要明确：哪些内容归 UI 框架管（可以原地重画），哪些一旦打印就归终端管（不可撤回）。
2. **不要相信"我知道光标在哪"**。至少三种外力会在你不知情时破坏这个缓存：终端 reflow、
   外部清屏、CPR 应答错位。恢复手段应该统一（丢缓存 + 从 (0,0) 重画 + 回放自己记的历史），
   并且要区分"擦视口(2J)"和"擦历史(3J)"——后者会毁掉框架接管前打的东西。
3. **重绘节流要有明确的"谁可以绕过"约定，并且写进 docstring**。
   `_invalidate` / `_paint_now` 的分工是个好范式（高频背景更新 vs 用户阻塞模态），
   但要靠代码审查维持——本段里 pet 线程就绕过去了（缺陷 #5）。
4. **宽度必须按显示单元格量，不能按 `len()`**，且**只量一次、传下去**。
   本段既有正例（`_status_bar_display_width` 体系）也有反例（`model_short` 用 len，
   框上下边框各量一次）。
5. **构造函数里别做 I/O**。541 行的 `__init__` 里藏着 SQLite 建表、VACUUM、
   一次 5 秒超时的 HTTP 请求和模块全局改写。正确做法是构造只赋值，
   把这些挪进显式的 `start()` / `prepare()`。判据很简单：
   **单测想构造这个对象需要 mock 几个东西？** 本段的答案是"prompt_toolkit 全家 + config + 工具定义"
   （见 `tests/cli/test_cli_init.py` 的 `_make_cli`）。
6. **别用"复用现有状态位"来表达新意图**。`/focus` 把 `tool_progress_mode` 推成 `"off"`
   来复用抑制路径，顺带关掉了 turn summary（§2.9）。新意图该有新旗标。
7. **流式文本过滤器必须处理三件事**：跨 token 的标签、prose 里提到的标签、永不闭合的标签。
   第三件只能在流末补救。
8. **一个可读性技巧**：长时间没有换行的正文，把尾巴镜像到状态行（`cli.py:6862`）。
   用"底盘"补"历史"的 TTFT 观感，成本极低。

### 5.3 复核脚本与结果

复核脚本 `verify_anchors.py`（写在 scratchpad，**不入基线仓库、也不写进 hermes-agent**）：
用正则从本稿抽出每一个 `` `路径:行号 @ 863e313` ``，回读 `/home/user/hermes-agent` 下对应文件的
该行原文并打印，供逐条与稿中代码块首行比对。

```python
pat = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|md)):(\d+) @ 863e313`")
```

最终一轮输出（首轮的 9 条漂移已按 §0.2 清单修正）：

```
$ python3 verify_anchors.py /home/user/hermes-study/notes/r8b-raw-cli-init-render.md
anchor occurrences: 195
unique (file,line):  180
...
---
all anchors resolve to an existing line
```

180 条唯一锚点按文件分布：

- `cli.py`（154 条）：138, 356, 792, 2173, 2203, 2998, 4205, 4213, 4223, 4248, 4253, 4262,
  4277, 4281, 4304, 4328, 4363, 4371, 4390, 4411, 4436, 4486, 4493, 4569, 4583, 4587,
  4605, 4610, 4694, 4715, 4752, 4755, 4757, 4776, 4794, 4797, 4818, 4836, 4861, 4887,
  4904, 4909, 4918, 4932, 4953, 4962, 4972, 4980, 4986, 4991, 5029, 5033, 5042, 5171,
  5175, 5180, 5184, 5186, 5196, 5205, 5209, 5218, 5241, 5249, 5289, 5306, 5334, 5385,
  5387, 5428, 5446, 5449, 5465, 5470, 5472, 5474, 5488, 5510, 5526, 5546, 5553, 5581,
  5583, 5613, 5622, 5631, 5636, 5674, 5709, 5739, 5755, 5766, 5787, 5797, 5809, 5816,
  5915, 5924, 5930, 5947, 5984, 5988, 6130, 6155, 6161, 6168, 6354, 6363, 6368, 6374,
  6393, 6394, 6402, 6536, 6558, 6576, 6594, 6643, 6649, 6675, 6708, 6749, 6758, 6799,
  6832, 6853, 6863, 6882, 6927, 6928, 6974, 6997, 6999, 7013, 7017, 7032, 7036, 7090,
  7092, 7105, 7209, 10574, 14103, 14218, 15477, 15482, 15498, 16467, 16642, 17071,
  17111, 17125, 17257, 17349, 17364, 17405, 17506, 17523, 17802, 18040, 18183
- `hermes_state.py`：2009, 2104
- `hermes_cli/config.py`：3142
- `hermes_cli/config_defaults.py`：1073
- `hermes_cli/focus_view.py`：36
- `hermes_cli/goals.py`：1249, 1257
- `hermes_cli/main.py`：2729
- `hermes_cli/cli_agent_setup_mixin.py`：516
- `hermes_cli/runtime_provider.py`：303
- `agent/battery.py`：89
- `agent/credits_tracker.py`：210, 347
- `run_agent.py`：3939
- `tools/process_registry.py`：1831
- `tools/async_delegation.py`：544
- `tui_gateway/server.py`：5652
- `tests/cli/test_cli_force_redraw.py`：57
- `website/docs/user-guide/configuration.md`：1646

另有约 30 处以正文散引形式出现的行号（如"同样的字面量还出现在 5961、6039、6088"、
"`cli.py:16623-16627`"、"`cli.py:5745-5746`"），不带 `` @ 863e313 `` 后缀因而不入脚本统计；
这些均在写稿时由 `Read`/`grep` 直接核对过，未再单独脚本复核。

基线仓库全程只读，收工复核：

```
$ git -C /home/user/hermes-agent status --porcelain
(空)
```

### 5.4 建议下一段接手时先看的三处

1. **`run()` 里 16600–17400 的布局定义**——本段所有渲染回调的挂载点，不看这段就不知道
   哪个回调多久跑一次。
2. **`_on_tool_progress`(12022)**——本段的 `_turn_summary_record`、`_pet_turn_error`、
   `_pet_reasoning`、`_tool_start_time` 全由它驱动。
3. **`chat()`(14100 附近)**——`_prompt_start_time` / `_prompt_duration` /
   `_last_turn_finished_at` 三个计时状态的唯一写点，本段只读不写。
