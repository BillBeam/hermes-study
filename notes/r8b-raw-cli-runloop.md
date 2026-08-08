# r8b-raw-cli-runloop —— cli.py 14800-18555(REPL 主循环与入口)

> 溯源约定:所有断言后紧跟 `路径:行号 @ 863e313` 与代码原文块。
> 基线 commit `863e31318553cda8ad61df681d08175364d4164b`。`cli.py` 全长 18555 行,本段 14800–18555 共 3756 行。
> 本文件是**证据层底稿**,不追求好读;结论请配合行号自行复核。

---

## 0. 自验记录

### 0.1 三条前提的检验结论(先说结论,因为三条都不成立)

| # | 交办的前提 | 检验结果 | 真相一句话 |
|---|---|---|---|
| 1 | 「`run()` 是简单的 `while True: 读输入; 跑一轮` 循环」 | **假** | `run()` 自身**一个循环都没有**;它是 2950 行的**装配函数**,末尾进 `app.run()`(prompt_toolkit 事件循环)。真正的 `while` 在两个 daemon 线程里。Ctrl-C 有**三条**互不相同的路径,不是两条。 |
| 2 | 「`cli.py` 的 `main()` 是进程入口」 | **假(但不是"没人调用")** | 打包入口是 `hermes_cli.main:main`;它经 `cmd_chat` **以关键字参数调用** `cli.main()`。`cli.py:main()` 是一个**被当作库函数调用的 Fire 兼容签名**,`fire.Fire(main)` 只在 `python cli.py` 直跑时生效。它有一个**从未被使用的形参** `ignore_user_config`。 |
| 3 | 「退出时清理恰好跑一次」 | **假(双向都假)** | `_run_cleanup` 有全局幂等锁,所以**至多一次**;但 (a) 锁在干活**之前**置位,中途抛异常就永久停在"半次";(b) 有三条 `os._exit(0)` 路径完全绕过它(**零次**);(c) `/update` 走 `os.execvp` 会跳过尚未触发的 atexit(worktree 清理漏掉)。 |

### 0.2 锚点自验(机器复核,含发现并修正的漂移)

写完初稿后做了**两轮机器复核**,不是抽样,是全量。

**第一轮:定点抽验 58 个锚点**(逐条比对 `路径:行号` 处的单行原文是否与引用一致)。
覆盖 `cli.py` 的 989 / 1173 / 1178 / 1183 / 4778 / 4785 / 10720 / 14257 / 14980 / 15164 / 15170 / 15453 / 15506 / 15915 / 15984 / 16094 / 16368 / 17083 / 17357 / 17377 / 17384 / 17506 / 17516 / 17549 / 17589 / 17607 / 17688 / 17692 / 17714 / 17735 / 17794 / 17804 / 17805 / 17828 / 17863 / 17918 / 17927 / 17936 / 18014 / 18026 / 18049 / 18129 / 18241 / 18309 / 18312 / 18484 / 18506 / 18552,外加
`pyproject.toml:359`、`hermes_cli/main.py:2709 / 2735 / 10854`、`agent/turn_context.py:514`、
`agent/interrupt_compat.py:22`、`hermes_cli/kanban_db.py:9141`、`hermes_cli/goals.py:2019`、
`hermes_cli/tips.py:305`、`tests/hermes_cli/test_suppress_eio_on_interrupt.py:29`。
**结果:58 查 1 错** —— 测试文件那条引到了 29 行,实际那句在 28 行(29 行是它的下一句)。

**第二轮:全量复核 97 对「锚点 + 紧跟的代码块」**,逐字节比对代码块内容与 `起始行..结束行` 区间,
并校验行数与区间长度一致(`prompt_toolkit` 的引用比对 venv 内 3.0.52 的实际源码)。
**首轮结果:97 对中 10 对不合格。** 全部是**区间结束行漂移**(引用范围比代码块多算或少算 1–3 行),
起始行与代码块内容全部正确:

| 引用 | 原写 | 更正为 |
|---|---|---|
| `prompt_toolkit/application/application.py` | 807-823 | **807-818** |
| `prompt_toolkit/application/application.py` | 1620-1631 | **1620-1630** |
| `prompt_toolkit/application/application.py` | 1018-1029 | **1018-1026** |
| `prompt_toolkit/key_binding/key_processor.py` | 271-278 | **272-279**(起止都错 1 行) |
| `cli.py` | 430-435 | **430-436** |
| `cli.py` | 1064-1084 | **1064-1085** |
| `cli.py` | 1132-1155 | **1132-1156** |
| `cli.py` | 17505-17517 | **17505-17516** |
| `tests/hermes_cli/test_suppress_eio_on_interrupt.py` | 26-31 | **25-31** |
| `tests/hermes_cli/test_suppress_eio_on_interrupt.py` | 29 | **28-29** |

**修正后重跑:97 对全部通过(0 problems)。**

**第三轮:全文 148 个不重复的 `路径:行号` 引用**(含正文里没有代码块的那些)做了越界/文件存在性检查,
**0 处越界、0 处文件不存在**。

**教训**:起始行几乎不会错(直接来自 `Read` 输出),**结束行是靠人数的,系统性偏差**。
后续底稿应当机器生成区间,或统一只写起始行。

### 0.3 运行环境与实际跑过的测试

按 CLAUDE.md 重建的 venv 可用;`prompt_toolkit` 实际版本 **3.0.52**(与 `pyproject.toml:57` 的 `prompt_toolkit==3.0.52` 一致)。跑通:

```
HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
  tests/hermes_cli/test_suppress_eio_on_interrupt.py \
  tests/cli/test_cli_interrupt_drain_regression.py \
  tests/cli/test_exit_watchdog_signal_arm.py \
  tests/hermes_cli/test_signal_handler_kanban_worker.py
=== Summary: 4 files, 18 tests passed, 0 failed (100% complete) in 7.1s ===
```

另外两处**在容器里实测**(见 §2.9.3、§3-缺陷2):

```
$ /home/user/hermes-venv/bin/python -c "..."   # 见 §2.9.3 原文
cli.py:17789-17796 equivalent -> SKIPPED (RuntimeError: no running event loop)
```

---

## 1. 段内地图

### 1.1 顶层切分

| 行段 | 内容 | 性质 |
|---|---|---|
| 14800–14806 | `_audio_level_bar` 尾巴(函数从 14796 开始,跨了段界) | 渲染 |
| 14808–14850 | `_get_tui_prompt_fragments` / `_get_tui_prompt_text` —— 提示符按状态优先级出图标 | 渲染 |
| 14852–14903 | `_build_tui_style_dict` / `_apply_tui_skin_style` —— 皮肤色 + 浅色终端重映射 | 渲染 |
| 14905–14978 | **wrapper CLI 扩展点**:`_get_extra_tui_widgets` / `_register_extra_tui_keybindings` / `_build_tui_layout_children` | 扩展契约 |
| **14980–17929** | **`HermesCLI.run()`** —— 类的最后一个方法,2950 行 | 本段主体 |
| 17932–17934 | `# Main Entry Point` 分隔注释 | —— |
| 17936–18023 | `_run_kanban_goal_loop_q`(模块级) | kanban 目标循环 |
| 18026–18549 | `main()`(模块级) | 参数装配 + 单次查询 |
| 18552–18555 | `if __name__ == "__main__": fire.Fire(main)` | 直跑入口 |

`run()` 是类里最后一个方法,`_run_kanban_goal_loop_q` 起是模块级:

`cli.py:14980 @ 863e313`

```python
    def run(self):
        """Run the interactive CLI loop with persistent input at bottom."""
        if not self._claim_active_session("cli"):
            return
```

`cli.py:17936 @ 863e313`

```python
def _run_kanban_goal_loop_q(cli: "HermesCLI", first_response: str) -> None:
```

### 1.2 `run()` 的结构统计(前提 1 的量化反证)

对 `run()` 函数体(14980–17929)做机械统计:

```
try:        57
except      57
finally:     3
while         2      ← 两个都在嵌套函数里,run() 自身 0 个循环
nested def   80
kb.add(     39
threading.Thread  9
```

两个 `while` 分别是:

`cli.py:17357 @ 863e313`

```python
            while not self._should_exit:
```

`cli.py:17377 @ 863e313`

```python
            while not self._should_exit:
```

前者在 `spinner_loop` 里,后者在 `process_loop` 里 —— 都是 `run()` 内部定义的嵌套函数,各自跑在 daemon 线程上。**`run()` 的直线代码里没有任何循环**;它执行完装配后,把控制权交给 prompt_toolkit:

`cli.py:17804 @ 863e313`

```python
                app.run()
```

57 个 `except` 的分布(说明这段代码的"防御姿态"):

```
     39  except Exception:
      4  except Exception as e:
      3  except (Exception, KeyboardInterrupt) as e:
      1  except queue.Empty:
      1  except RuntimeError:
      1  except OSError:
      1  except KeyboardInterrupt:
      1  except Exception as exc:
      1  except Exception as _goal_exc:
      1  except Exception as _exc:
      1  except (TypeError, ValueError):
      1  except (OSError, ValueError, KeyError):
      1  except (KeyError, OSError) as _stdin_err:
      1  except (EOFError, KeyboardInterrupt, BrokenPipeError):
```

**39 个裸 `except Exception: pass`** 是这段代码的主基调:每一个横幅、每一个预热、每一个皮肤查询都被单独包起来,原则是"启动期的任何附属功能都不许拖垮启动"。代价是:任何一处逻辑写错都不会有人知道(§3 缺陷 2 就是这么埋进去的)。

---

## 2. 逐机制精读

### 2.1 真实骨架:一个 UI 线程 + 一个工作线程 + 两个队列

这是理解整段代码的唯一关键。`run()` 装配完之后,进程里同时活着:

- **主线程**:被 `app.run()`(asyncio + prompt_toolkit)占住,负责读键、渲染、跑所有 `@kb.add` 处理器。
- **`process_loop` daemon 线程**:唯一有权调用 `self.chat()` 的线程,即唯一跑模型轮次的线程。
- **`spinner_loop` daemon 线程**:只在 slash 命令执行期间以 0.1s 节奏重绘。
- **另外 7 处 `threading.Thread`**:agent 运行时预导入、wake word 启动、语音录制/转写、语音重启、Ctrl-C 取消录音等。

两者之间用两个 `queue.Queue` 连接:

`cli.py:15163-15171 @ 863e313`

```python
        # State for async operation
        self._agent_running = False
        self._pending_input = queue.Queue()     # For normal input (commands + new queries)
        self._interrupt_queue = queue.Queue()   # For messages typed while agent is running
        # See constructor note. Mirrored here for the run() path that skips
        # the earlier __init__ branch.
        self._last_turn_interrupted = False
        self._should_exit = False
        self._last_ctrl_c_time = 0  # Track double Ctrl+C for force exit
```

线程启动点:

`cli.py:17372-17373 @ 863e313`

```python
        spinner_thread = threading.Thread(target=spinner_loop, daemon=True)
        spinner_thread.start()
```

`cli.py:17593-17594 @ 863e313`

```python
        process_thread = threading.Thread(target=process_loop, daemon=True)
        process_thread.start()
```

**两个线程都没有 `join()`**(全仓 `grep` `process_thread|spinner_thread` 只有 17372/17373/17593/17594 四行)。它们靠 daemon 属性被解释器直接回收。这解释了为什么 §2.9 的 `finally` 块要在 teardown 里主动 `request_hard_interrupt` —— 没人会等这两个线程收尾。

**为什么要这么设计(而不是在主线程里直接跑 turn)**:prompt_toolkit 的输入解析、渲染、按键回调全在 asyncio 事件循环的回调里跑。一旦模型轮次(几十秒到几分钟)占住主线程,Ctrl-C 键位就不会被解析,UI 冻死,用户连"中断"这个动作都发不出去。把 turn 推到工作线程,是**中断能力**本身的前提。代价就是下面所有的跨线程状态同步。

### 2.2 启动序幕(14980–15161):十件事,每件都单独 try

`run()` 开头是一串"能失败但不能崩"的启动动作。挑几个有设计含量的:

**(a) 先占坑,占不到就直接返回。** 全局活动会话租约:

`cli.py:14982-14983 @ 863e313`

```python
        if not self._claim_active_session("cli"):
            return
```

注意这个 `return` **在任何 atexit 注册之前**,所以租约没拿到时不会留下任何需要清理的东西。

**(b) 把 TUI 顶到终端底部。** 靠打印 N-1 个空行把光标滚到最后一行:

`cli.py:14996-15001 @ 863e313`

```python
        try:
            _term_lines = shutil.get_terminal_size().lines
            if _term_lines > 2:
                print("\n" * (_term_lines - 1), end="", flush=True)
        except Exception:
            pass
```

这是"非全屏 prompt_toolkit"的固定套路:pt 在非全屏模式下只管理底部若干行,上面的历史输出走普通 scrollback。要让首屏看起来"输入框在底部",只能先把 scrollback 撑开。

**(c) 首跑无凭据直接转到 onboarding。** 注释里写清了旧行为的病症:

`cli.py:15008-15017 @ 863e313`

```python
        # First-run: a completely unconfigured install must route into
        # provider onboarding, not a chat that cannot work. Previously a
        # keyless `hermes` accepted a message, spun for ~30s, then failed
        # with a provider-specific error the user never chose. Only fires
        # on a real TTY; quiet/single-query paths keep their own handling.
        try:
            if sys.stdin.isatty() and not self._runtime_credentials_ready():
                self._offer_first_run_setup()
        except Exception:
            logger.debug("first-run setup offer failed", exc_info=True)
```

**(d) 用"用户正在看横幅"的空档预热 agent 运行时。** 这是本段最值得抄的一个技巧:

`cli.py:15045-15066 @ 863e313`

```python
        # Pre-import the agent runtime off-thread during the same idle window.
        # The first turn otherwise pays ~1.5s of module imports on the
        # time-to-first-token critical path: `import run_agent` (~0.9s,
        # deferred by the lazy AIAgent wrapper above) plus the OpenAI SDK
        # (~0.6s, deferred until client construction). Python's import lock
        # makes this safe: if the user submits before the warm finishes, the
        # main thread simply blocks on the remaining import work instead of
        # redoing it. Skipped when agent startup is explicitly deferred
        # (Termux) — that path defers heavy work on purpose.
        if os.environ.get("HERMES_DEFER_AGENT_STARTUP") != "1":
            def _prewarm_agent_runtime() -> None:
                try:
                    import run_agent  # noqa: F401  (imports model_tools + tool registry)
                    import openai  # noqa: F401
                except Exception:
                    logger.debug("agent runtime pre-import failed", exc_info=True)

            threading.Thread(
                target=_prewarm_agent_runtime,
                name="agent-runtime-prewarm",
                daemon=True,
            ).start()
```

设计要点:**利用 CPython 的 import lock 作为天然的幂等/去重机制** —— 预热线程和主线程抢同一个模块,后到者阻塞在锁上而不是重复做功。不需要任何自建的 `Event`/`Future`。

**(e) 安全网关掉时必须吵。** 脱敏开关的"反向告警":

`cli.py:15068-15084 @ 863e313`

```python
        # Redaction opt-out warning (#17691): ON by default, loud when off.
        # The redactor snapshots its state at import time so any toggle now
        # won't affect the running process — we just want the operator to
        # see that they're running without the safety net.
        try:
            _redact_raw = os.getenv("HERMES_REDACT_SECRETS", "true")
            if _redact_raw.lower() not in {"1", "true", "yes", "on"}:
                self._console_print(
                    "[bold red]⚠  Secret redaction is DISABLED[/] "
                    f"(HERMES_REDACT_SECRETS={_redact_raw}). "
                    "API keys and tokens may appear verbatim in chat output, "
                    "session JSONs, and logs. Set "
                    "[cyan]security.redact_secrets: true[/] in config.yaml "
                    "to re-enable."
                )
        except Exception:
            pass
```

### 2.3 运行时状态块(15163–15238):一次性把所有 modal 状态摊平

15163–15238 是一整片状态初始化。设计模式统一:**每个"需要用户在输入框里回答的东西"都是一个 `dict` + 一个 `deadline` + 一个 `response_queue`**。

- `_clarify_state` / `_clarify_deadline`(15187–15189)
- `_sudo_state` / `_sudo_deadline`(15192–15193)
- `_approval_state` / `_approval_deadline` / `_approval_lock`(15197–15199)
- `_slash_confirm_state` / `_slash_confirm_deadline`(15205–15206)
- `_secret_state` / `_secret_deadline`(15214–15215)

`cli.py:15196-15199 @ 863e313`

```python
        # Dangerous command approval state (similar mechanism to clarify)
        self._approval_state = None     # dict with command, description, choices, selected, response_queue
        self._approval_deadline = 0
        self._approval_lock = threading.Lock()  # serialize concurrent approval prompts (delegation race fix)
```

**为什么是队列而不是回调**:提问方是工具线程(在 `process_loop` 之下更深的调用栈里),回答方是 UI 线程。工具线程 `response_queue.get(timeout=...)` 阻塞等待,UI 线程按键处理器 `put()` 一个值就放行。这是唯一能让"工具执行到一半停下来问人"而不把 UI 冻住的结构。

代价是:**状态字典被置位后,如果那个工具线程死了,状态字典还在**,输入框就被 modal 过滤器卡住,用户以为终端挂了。这正是 `_clear_active_overlays_for_interrupt` 存在的原因:

`cli.py:13642-13657 @ 863e313`

```python
    def _clear_active_overlays_for_interrupt(self) -> None:
        """Drain and clear every input-blocking overlay left by an interrupted agent.

        approval/clarify/sudo/secret prompts each block a worker thread on a
        ``response_queue.get()``.  When the agent is interrupted the worker
        thread is torn down, but the overlay's state dict stays set — leaving
        the CLI input gated (``read_only`` condition + keypress filter) with no
        thread servicing the prompt.  The result is a frozen terminal until the
        prompt's own timeout expires.  Push a terminal value onto each queue so
        any still-blocked thread unblocks cleanly, then nil the state out and
        restore the user's pre-modal draft (#14026).

        Safe default per prompt: approval -> "deny", clarify/sudo/secret ->
        cancel (None / empty).  Each step is wrapped so a dead queue can't
        prevent clearing the others.
        """
```

**设计原则(可迁移)**:凡是"阻塞在队列上的跨线程问答",清理路径必须**同时**做两件事 —— 往队列里推一个终止值(放行阻塞方)**和**清空状态(放行 UI 方)。只做一件就是死锁或幽灵面板。

### 2.4 `handle_enter`:输入路由的六岔口(15257–15538)

这是整段最"业务"的函数。一次 Enter 按下,按以下**顺序**判断,先命中先返回:

`cli.py:15257-15269 @ 863e313`

```python
        def handle_enter(event):
            """Handle Enter key - submit input.
            
            Routes to the correct queue based on active UI state:
            - Sudo password prompt: password goes to sudo response queue
            - Approval selection: selected choice goes to approval response queue
            - Clarify freetext mode: answer goes to the clarify response queue
            - Clarify choice mode: selected choice goes to the clarify response queue
            - Agent running: goes to _interrupt_queue (chat() monitors this)
            - Agent idle: goes to _pending_input (process_loop monitors this)
            Commands (starting with /) always go to _pending_input so they're
            handled as commands, not sent as interrupt text to the agent.
            """
```

顺序(实际代码顺序,与 docstring 略有出入,docstring 漏了 slash-confirm 和 model picker):

1. `_sudo_state`(15271)→ 密码进 sudo 队列
2. `_secret_state`(15279)→ 密钥进 secret 队列
3. `_approval_state`(15287)→ 确认高亮选项
4. `_slash_confirm_state`(15293)→ 破坏性命令二次确认
5. `_model_picker_state`(15307)→ `/model` 选择器
6. `_clarify_freetext` + `_clarify_state`(15324)→ 自由文本答案
7. `_clarify_state` 非 freetext(15340)→ 选项/多选
8. **正常输入路由**(15383 起)

第 8 步内部还有三个**必须在 UI 线程就地执行**的 slash 命令旁路,理由完全相同:`process_loop` 此刻正阻塞在 `self.chat()` 里,把命令排队进 `_pending_input` 等于把它推迟到本轮结束 —— 而这三个命令的全部意义就是"在本轮进行中生效"。

`cli.py:15404-15420 @ 863e313`

```python
                # Handle /steer while the agent is running immediately on the
                # UI thread.  Queuing through _pending_input would deadlock the
                # steer until after the agent loop finishes (process_loop is
                # blocked inside self.chat()), which turns /steer into a
                # post-run next-turn message — defeating mid-run injection.
                # agent.steer() is thread-safe (holds _pending_steer_lock).
                if self._should_handle_steer_command_inline(text, has_images=has_images):
                    self.process_command(text)
                    event.app.current_buffer.reset(append_to_history=True)
                    # Force a repaint after clearing the buffer.  /steer is
                    # dispatched mid-run while the agent streams output through
                    # patch_stdout; process_command() never invalidates the
                    # app, so without this the submitted "/steer <text>" can
                    # linger in the input area (looking unsent) and invite an
                    # accidental re-submit. See issue #34569.
                    event.app.invalidate()
                    return
```

`/background` 同理,注释还点破了一个"两套实现只改了一套"的历史债:

`cli.py:9675-9679 @ 863e313`

```python
        The command's own ``CommandDef`` already declares
        ``busy_policy="dispatch"``; the gateway honours that, the classic CLI
        never consulted it. Dispatching inline on the UI thread starts the
        background session immediately and leaves the foreground turn running
        untouched: no interrupt, no steer.
```

**忙时输入的三种模式。** 走到 15453 时,如果 agent 在跑且不是本地派发(slash / `!`),按 `busy_input_mode` 分流:

`cli.py:15446-15456 @ 863e313`

```python
                # A bang command is treated like a slash command while the
                # agent is busy: it must never be routed into steer/redirect
                # (which would inject `!git status` into the model's context as
                # a prompt). It queues and runs locally once the loop drains.
                _is_local_dispatch = bool(text) and (
                    _looks_like_slash_command(text) or text.strip().startswith("!")
                )
                if self._agent_running and not _is_local_dispatch:
                    _effective_mode = self.busy_input_mode
                    redirected = False
                    if _effective_mode == "steer":
```

- `steer`:调 `agent.steer(text)`,中途注入。带图片或空文本时**降级为 queue**(15462-15463),`steer()` 拒绝也降级(15476)。
- `queue`:进 `_pending_input`,下一轮跑(15477-15481)。
- `interrupt`:先试 `agent.redirect(text)`(需要 `_supports_active_turn_redirect` 为 True),失败则进 `_interrupt_queue`(15504)。

`cli.py:15482-15511 @ 863e313`

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
                        if redirected:
                            preview = text[:80] + ("..." if len(text) > 80 else "")
                            _cprint(f"  {_ACCENT}↪ Redirected current turn: '{preview}'{_RST}")
                        else:
                            # Compatibility path for older agents, multimodal
                            # follow-ups, or a turn that finished in the race.
                            self._interrupt_queue.put(payload)
                            try:
                                _dbg = _hermes_home / "interrupt_debug.log"
                                with open(_dbg, "a", encoding="utf-8") as _f:
                                    _f.write(f"{time.strftime('%H:%M:%S')} ENTER: queued interrupt msg={str(payload)[:60]!r}, "
                                             f"agent_running={self._agent_running}\n")
                            except Exception:
                                pass
```

注意 `getattr(..., "_supports_active_turn_redirect", False) is True` 用 `is True` 而非 `bool()` —— 这是在防 `MagicMock`/动态代理:任何 `__getattr__` 代理返回的对象都是 truthy,但不会 `is True`。同一防御思路在 `request_hard_interrupt` 里用 `inspect.getattr_static` 实现:

`agent/interrupt_compat.py:17-30 @ 863e313`

```python
    # Avoid treating a dynamic ``__getattr__`` proxy (notably an unspecced
    # ``MagicMock`` or a third-party RPC facade) as if it genuinely implements
    # the new ABI. Static lookup proves the attribute exists on the instance or
    # its type before normal descriptor binding retrieves the callable.
    try:
        inspect.getattr_static(agent, "hard_interrupt")
    except AttributeError:
        interrupt = None
    else:
        interrupt = getattr(agent, "hard_interrupt", None)
    if not callable(interrupt):
        interrupt = getattr(agent, "interrupt", None)
    if not callable(interrupt):
        return False
```

### 2.5 Ctrl-C 的**三条**路径(交办要求重点看的部分)

前提 1 说"prompt 处 vs turn 中是两条不同路径"。实测是**三条**,而且第三条几乎肯定不是作者预期的行为。

#### 路径 A:终端里敲 Ctrl-C(raw mode,不产生 SIGINT)

`app.run()` 期间 pt 把 tty 置于 raw mode(`with self.input.raw_mode()`,`prompt_toolkit/application/application.py:734 @ 863e313` 附近),raw mode 关掉 `ISIG`,所以 **Ctrl-C 不会变成 SIGINT**,只是字节 `0x03`,被 pt 解析为 `Keys.ControlC`,进入本文件绑定的处理器:

`cli.py:15915-15925 @ 863e313`

```python
        @kb.add('c-c')
        def handle_ctrl_c(event):
            """Handle Ctrl+C - cancel interactive prompts, interrupt agent, or exit.
            
            Priority:
            0. Cancel active voice recording
            1. Cancel active sudo/approval/clarify prompt
            2. Interrupt the running agent (first press)
            3. Force exit (second press within 2s, or when idle)
            """
            now = time.time()
```

**在 turn 进行中**(`_agent_running` 为 True 且 `self.agent` 存在):

`cli.py:15984-15993 @ 863e313`

```python
            if self._agent_running and self.agent:
                if now - self._last_ctrl_c_time < 2.0:
                    print("\n⚡ Force exiting...")
                    self._should_exit = True
                    event.app.exit()
                    return
                
                self._last_ctrl_c_time = now
                print("\n⚡ Interrupting agent... (press Ctrl+C again to force exit)")
                request_hard_interrupt(self.agent)
```

**在 prompt 处空闲**:

`cli.py:15994-16002 @ 863e313`

```python
            # If there's text or images, clear them (like bash).
            # If everything is already empty, exit.
            elif event.app.current_buffer.text or self._attached_images:
                event.app.current_buffer.reset()
                self._attached_images.clear()
                event.app.invalidate()
            else:
                self._should_exit = True
                event.app.exit()
```

即:**有草稿 → 清草稿(bash 语义);空 → 退出。** 与 turn 中的"中断 → 再按强退"完全不同。

在这两者之前还插了一段"先清 overlay,但**不 return**"的逻辑,这是 #14026 的修复:

`cli.py:15961-15982 @ 863e313`

```python
            # Clear all agent-blocking overlays (approval/clarify/sudo/secret)
            # in one shot.  We do NOT return after clearing — we fall through so
            # that if the agent is also running we fire the interrupt on the same
            # Ctrl+C press.  This fixes the case where a stale/orphaned overlay
            # (left behind by a previous interrupt) consumes the press without
            # ever reaching the agent-interrupt branch, leaving the chat frozen
            # (#14026).
            _overlay_cleared = bool(
                self._sudo_state
                or self._secret_state
                or self._approval_state
                or self._clarify_state
            )
            if _overlay_cleared:
                self._clear_active_overlays_for_interrupt()
                event.app.current_buffer.reset()
                event.app.invalidate()

            # If we only cleared overlays and the agent is NOT running, stop here
            # (don't fall through to the interrupt/exit path).
            if _overlay_cleared and not (self._agent_running and self.agent):
                return
```

**为什么这个"不 return"很重要**:上一轮 Ctrl-C 中断 agent 后,可能留下一个没人服务的 approval 面板。此时用户再按 Ctrl-C,旧代码在第 1 优先级就被这个幽灵面板吃掉,永远走不到"中断 agent"分支 —— 聊天看起来彻底冻住。改成"清完继续往下走"后,一次按键同时完成两件事。

`_slash_confirm_state` 和 `_model_picker_state` 是**例外**,它们是纯前台 UI(没有工作线程阻塞在队列上),所以清完就 `return`:

`cli.py:15946-15959 @ 863e313`

```python
            # Cancel slash confirmation prompt (foreground UI, not an
            # agent-blocking overlay — cancel and stop here).
            if self._slash_confirm_state:
                self._submit_slash_confirm_response("cancel")
                event.app.current_buffer.reset()
                event.app.invalidate()
                return

            # Cancel /model picker (foreground UI — cancel and stop here).
            if self._model_picker_state:
                self._close_model_picker()
                event.app.current_buffer.reset()
                event.app.invalidate()
                return
```

#### 路径 B:真正的 OS SIGINT(`kill -INT`、进程组信号)—— **被静默吞掉**

`app.run()` 默认 `handle_sigint=True`(`prompt_toolkit/application/application.py:624 @ 863e313` 的 `run_async` 默认值),于是 pt 在事件循环上注册了 SIGINT 处理器:

`prompt_toolkit/application/application.py:807-818 @ 863e313`

```python
        @contextmanager
        def set_handle_sigint(loop: AbstractEventLoop) -> Iterator[None]:
            if handle_sigint:
                with _restore_sigint_from_ctypes():
                    # save sigint handlers (python and os level)
                    # See: https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1576
                    loop.add_signal_handler(
                        signal.SIGINT,
                        lambda *_: loop.call_soon_threadsafe(
                            self.key_processor.send_sigint
                        ),
                    )
```

`send_sigint` 把 `Keys.SIGINT`(即 `"<sigint>"`)喂进按键处理器。而 `cli.py` **从未绑定 `Keys.SIGINT`**(39 处 `kb.add` 里没有它),于是落到 pt 的默认绑定 —— 一个空函数:

`prompt_toolkit/key_binding/bindings/basic.py:135-146 @ 863e313`

```python
    @handle("<sigint>")
    @handle(Keys.Ignore)
    def _ignore(event: E) -> None:
        """
        First, for any of these keys, Don't do anything by default. Also don't
        catch them in the 'Any' handler which will insert them as data.

        If people want to insert these characters as a literal, they can always
        do by doing a quoted insert. (ControlQ in emacs mode, ControlV in Vi
        mode.)
        """
        pass
```

**结论:POSIX 下 `kill -INT <hermes-pid>` 对交互式 CLI 完全无效** —— 既不中断 agent,也不退出,连日志都没有。而 SIGTERM / SIGHUP 有完整处理(见 §2.10)。这与本文件自己的注释直接冲突,见 §4 冲突 1。

顺带说明这条路径为什么"不是没人管":`main()` 在调 `cli.run()` 之前**给 SIGINT 装过处理器**:

`cli.py:18310-18317 @ 863e313`

```python
    try:
        import signal as _signal
        _signal.signal(_signal.SIGINT, _signal_handler_q)
        _signal.signal(_signal.SIGTERM, _signal_handler_q)
        if hasattr(_signal, "SIGHUP"):
            _signal.signal(_signal.SIGHUP, _signal_handler_q)
    except Exception:
        pass  # signal handler may fail in restricted environments
```

注意这段**在 `if query or image:` 之前**(18320),所以**交互模式也会装**。但 `app.run()` 期间被 pt 的 `add_signal_handler` 顶掉了 —— asyncio 的 `add_signal_handler` 会把 Python 层处理器换成自己的 no-op C 函数。pt 用 `_restore_sigint_from_ctypes` 在退出时把它还回来:

`prompt_toolkit/application/application.py:1620-1630 @ 863e313`

```python
    sigint = signal.getsignal(signal.SIGINT)
    if have_ctypes_signal:
        sigint_os = pythonapi.PyOS_getsig(signal.SIGINT)

    try:
        yield
    finally:
        if sigint is not None:
            signal.signal(signal.SIGINT, sigint)
        if have_ctypes_signal:
            pythonapi.PyOS_setsig(signal.SIGINT, sigint_os)
```

(必须这么绕,是因为 asyncio 的 `remove_signal_handler(SIGINT)` 恢复的是 `signal.default_int_handler`,而不是之前那个 —— 这正是 pt issue #1576。)

#### 路径 C:`app.run()` 返回之后、清理跑完之前的 Ctrl-C —— **打断清理**

`app.run()` 一返回,pt 的 `raw_mode` 上下文退出,`ISIG` 恢复,Ctrl-C 重新变成真 SIGINT;同时 `_restore_sigint_from_ctypes` 已经把 `_signal_handler_q` 装回去了。而此时进程正走在 `finally` 的 teardown 里(会话 flush、SQLite `end_session`、MCP/浏览器/内存 provider 关停,注释自己说这个窗口"可能几秒"):

`cli.py:17831-17839 @ 863e313`

```python
            # Immediate feedback: prompt_toolkit has just torn down the input
            # box + status bar, so without a line here the terminal sits
            # silent for the whole cleanup window (session flush, memory
            # shutdown, MCP/browser/terminal teardown) and the exit looks
            # hung. Print before any potentially-slow step.
            try:
                print(f"{_DIM}Shutting down… (finalizing session){_RST}", flush=True)
            except Exception:
                pass
```

此时按 Ctrl-C → `_signal_handler_q` → `request_hard_interrupt` + `time.sleep(1.5)` → `raise KeyboardInterrupt()`:

`cli.py:18264-18275 @ 863e313`

```python
        try:
            _agent = getattr(cli, "agent", None)
            if _agent is not None:
                request_hard_interrupt(_agent, f"received signal {signum}")
                try:
                    _grace = float(os.getenv("HERMES_SIGTERM_GRACE", "1.5"))
                except (TypeError, ValueError):
                    _grace = 1.5
                if _grace > 0:
                    time.sleep(_grace)
        except Exception:
            pass  # never block signal handling
```

`cli.py:18309 @ 863e313`

```python
        raise KeyboardInterrupt()
```

这个 `KeyboardInterrupt` 从 `finally` 块中间抛出,剩余步骤(会话持久化、`end_session`、`on_session_end`、`_run_cleanup()`、退出摘要、租约释放)全部跳过,然后一路穿透 `run()` → `cli.main()` → `cmd_chat` → `hermes_cli.main:main`,而顶层**没有 `except KeyboardInterrupt`**:

`hermes_cli/main.py:12590-12595 @ 863e313`

```python
    if hasattr(args, "func"):
        rc = args.func(args)
        if isinstance(rc, int) and rc != 0:
            sys.exit(rc)
    else:
        parser.print_help()
```

用户看到的是一段 traceback。`atexit` 还会补跑 `_run_cleanup` 和 `_release_active_session`,但**本轮未落盘的对话丢了**。详见 §3 缺陷 1。

#### Ctrl-Q:Ctrl-C 的删减版

`cli.py:16013-16020 @ 863e313`

```python
        @kb.add('c-q')  # Ctrl+Q
        def handle_ctrl_q(event):
            """Alternative interrupt/exit shortcut (Ctrl+Q).

            Behaves like Ctrl+C: cancels active prompts, interrupts the
            running agent, or clears the input buffer. Does not support
            the double-press 'force exit' feature of Ctrl+C.
            """
```

16013–16078 是 15915–16002 的近乎逐行复制,只少了双击强退。**两份高度重复的中断路径,任何一边改了另一边不会跟着改** —— 已经能看到差异:Ctrl-C 分支打印 `"\n⚡ Interrupting agent... (press Ctrl+C again to force exit)"`(15992),Ctrl-Q 打印 `"\n⚡ Interrupting agent..."`(16070),其余完全一样。

### 2.6 Ctrl-D / 双 ESC:EOF 与草稿丢弃

`cli.py:16080-16095 @ 863e313`

```python
        @kb.add('c-d')
        def handle_ctrl_d(event):
            """Ctrl+D: delete char under cursor (standard readline behaviour).
            Only exit when the input is empty — same as bash/zsh. Pending
            attached images count as input and block the EOF-exit so the
            user doesn't lose them silently.
            """
            buf = event.app.current_buffer
            if buf.text:
                buf.delete()
            elif self._attached_images:
                # Empty text but pending attachments — no-op, don't exit.
                return
            else:
                self._should_exit = True
                event.app.exit()
```

注意 EOF 退出走的是 `app.exit()` 而**不是**抛 `EOFError`。真正会抛 `EOFError` 的是 pt 内部(`f.set_exception(EOFError)`,输入流关闭时),由 17805 的 `except (EOFError, ...)` 接住。

双 ESC 丢草稿,设计上刻意把草稿先塞进 history 作为撤销手段:

`cli.py:16120-16144 @ 863e313`

```python
        @kb.add('escape', 'escape', filter=~_modal_prompt_active)
        def handle_double_escape(event):
            """Double ESC: discard the current draft and any attached images.

            Matches Claude Code / Gemini CLI, where double-Esc is the
            clear-the-composer gesture. It works while the agent is
            streaming, which is the gap Ctrl+C leaves: Ctrl+C interrupts a
            running turn and only clears the draft when idle, so mid-stream
            there was no way to discard a half-typed prompt.

            The draft is appended to history first, so Up recalls it — the
            same undo affordance Claude Code provides, and the reason this
            is safe to bind to a key pressed by reflex.

            Single ESC is the prefix for Alt sequences (escape+enter,
            escape+g, escape+v), so prompt_toolkit's escape-timeout keeps
            those distinct from the double press. Modal prompts bind ESC
            eagerly and are excluded here so cancel still wins.
            """
            buf = event.app.current_buffer
            if not (buf.text or cli_ref._attached_images):
                return
            buf.reset(append_to_history=bool(buf.text))
            cli_ref._attached_images.clear()
            event.app.invalidate()
```

这条 docstring 把"为什么需要它"讲得很干净:Ctrl-C 在流式输出中被 agent-interrupt 分支占用,留下了"流式中无法丢草稿"的空档。

### 2.7 `process_loop`:唯一的消费端(17376–17590)

`cli.py:17375-17392 @ 863e313`

```python
        # Background thread to process inputs and run agent
        def process_loop():
            while not self._should_exit:
                try:
                    # Check for pending input with timeout
                    try:
                        user_input = self._pending_input.get(timeout=0.1)
                    except queue.Empty:
                        # Periodic config watcher — auto-reload MCP on mcp_servers change
                        if not self._agent_running:
                            self._check_config_mcp_changes()
                            # Check for background process notifications (completions
                            # and watch pattern matches) while agent is idle.
                            try:
                                self._drain_process_notifications("cli-idle")
                            except Exception:
                                pass
                        continue
```

**0.1s 超时轮询而非阻塞 get 的原因**:空闲期要做两件周期性的事 —— config.yaml 的 mtime 监视(内部再节流到 5s,`cli.py:11536` 的 `CONFIG_WATCH_INTERVAL = 5.0`)和后台进程通知排水。同时 0.1s 也是 `_should_exit` 的最大响应延迟。

拿到输入后的处理顺序(每一步都是"先命中先短路"):

1. **拆语音哨兵**(17396-17398)。用一个 `_VoiceInputMessage` 包装类区分 STT 输出和手打文本:

`cli.py:4188-4194 @ 863e313`

```python
class _VoiceInputMessage:
    """Sentinel wrapper for voice-transcribed messages in ``_pending_input``.

    Distinguishes STT output from manually typed text while voice mode is
    active, so the concise-voice-response prefix is applied only to messages
    that actually came from the microphone (#65827).
    """
```

2. **拆图片元组**(17408-17410):payload 可能是 `str` 或 `(text, [Path,...])`。
3. **洗终端泄漏序列**(17412-17416):括号粘贴包装、鼠标上报。
4. **打字版 "stop" 结束语音会话**(17423-17424)。
5. **文件拖放识别**(17428-17441)。
6. **`/resume` 后的裸数字选择**(17446-17452)。
7. **`!<cmd>` shell 模式**(17458-17463)—— 明确不进对话历史、不耗模型轮次。
8. **slash 命令**(17465-17490)。
9. **展开粘贴引用**、打印预览(17492-17498)。
10. **跑 turn**(17506-17587)。

slash 分支里有一个专门的 `KeyboardInterrupt` 保护:

`cli.py:17465-17480 @ 863e313`

```python
                    if not _file_drop and isinstance(user_input, str) and _looks_like_slash_command(user_input):
                        _cprint(f"\n⚙️  {user_input}")
                        try:
                            if not self.process_command(user_input):
                                self._should_exit = True
                                # Schedule app exit
                                if app.is_running:
                                    app.exit()
                        except KeyboardInterrupt:
                            # Ctrl+C during a slow slash command (e.g. /skills browse,
                            # /sessions list with a large DB) should interrupt the
                            # command and return to the prompt, NOT exit the entire
                            # session. Without this guard a KeyboardInterrupt unwinds
                            # to the outer prompt_toolkit loop and the session dies.
                            _cprint("\n[dim]Command interrupted.[/dim]")
                            continue
```

以及 slash handler 可以留下"一次性种子",让本次 slash 之后直接接一个 agent turn:

`cli.py:17481-17490 @ 863e313`

```python
                        # A slash handler may set a one-shot pending seed (e.g.
                        # /blueprint <name>) to be run as the next agent turn.
                        # If present, fall through to the chat path with the seed
                        # as the user message instead of looping back to idle.
                        _seed = getattr(self, "_pending_agent_seed", None)
                        if _seed:
                            self._pending_agent_seed = None
                            user_input = _seed
                        else:
                            continue
```

外层唯一的兜底:

`cli.py:17589-17590 @ 863e313`

```python
                except Exception as e:
                    logger.warning("process_loop unhandled error (msg may be lost): %s", e)
```

**只接 `Exception`,不接 `BaseException`。** 任何 `SystemExit` / `KeyboardInterrupt` 从 `self.chat()` 或某个 slash handler 逃出来,这个线程就静默死亡,而 UI 线程毫不知情:输入框照常收字,`_pending_input.put()` 照常成功,只是**再也没有人取**。用户看到的是"回车没反应"。见 §3 缺陷 6。

### 2.8 turn 的 `try/finally`:一轮结束要做的七件事(17505–17587)

`cli.py:17505-17516 @ 863e313`

```python
                    # Regular chat - run agent
                    self._agent_running = True
                    self._interactive_turn = True
                    self._pet_turn_error = False
                    self._pet_reasoning = False
                    self._turn_summary_begin()
                    app.invalidate()  # Refresh status line

                    try:
                        self.chat(user_input, images=submit_images or None, voice_input=is_voice_input)
                    finally:
                        self._agent_running = False
```

`finally` 的第一条语句就是 `_agent_running = False`(17516),这是**故意的**:后面还有一长串收尾动作,任何一个抛异常都不能让"agent 还在跑"的假状态卡住 UI(输入路由、Ctrl-C 语义、占位符文案全看这个标志)。

`finally` 里的七件事:

**(1) 清渲染状态 + 发出 turn 会计行**(17517-17529)。

**(2) 中断后的终端恢复**:

`cli.py:17531-17540 @ 863e313`

```python
                        # Post-turn terminal recovery (#33271): after an
                        # interrupt the prompt_toolkit renderer may have
                        # drifted from the physical terminal state — CSI 6n
                        # cursor position reports can leak as literal text
                        # (^[[19;1R), and the VT100 input parser can stall in
                        # a partial-escape state, accepting no further
                        # keystrokes.  Drain stray escape bytes from the OS
                        # input buffer and force a clean renderer redraw.
                        if self._last_turn_interrupted:
                            self._recover_terminal_after_interrupt()
```

**(3) 把 `_interrupt_queue` 的残留倒回 `_pending_input`** —— 这是本段最有教学价值的一个 bug 修复:

`cli.py:17542-17549 @ 863e313`

```python
                        # Re-queue any messages that arrived in _interrupt_queue
                        # while the agent was running and were never claimed by
                        # the explicit interrupt path. See
                        # _drain_interrupt_queue_to_pending_input for the full
                        # rationale. Regression of #17666 / #18760 — the drain
                        # block from the original PR #17939 was deferred as
                        # "worth its own review" and never re-landed (#20271).
                        self._drain_interrupt_queue_to_pending_input()
```

`cli.py:10702-10718 @ 863e313`

```python
    def _drain_interrupt_queue_to_pending_input(self) -> None:
        """Move stray messages from ``_interrupt_queue`` into ``_pending_input``.

        While the agent is running, user input is routed into
        ``_interrupt_queue`` (see the architecture comment near
        ``_route_user_input_when_busy``). The explicit-interrupt path at the
        top of ``process_loop`` only drains that queue when
        ``busy_input_mode == "interrupt"`` AND a ``pending_message`` was
        acknowledged. If the agent's turn finishes naturally (no interrupt),
        any messages typed during the turn stay stuck in ``_interrupt_queue``
        forever. Subsequent ``Enter`` presses re-route to the same blocked
        queue and the CLI appears to hang.

        Called once at the end of every turn from ``process_loop``'s ``finally``
        block. Catches and swallows ``Exception`` because the drain must never
        break the main loop. (#20271)
        """
```

**故事**:v0.12.0 用户在 agent 跑的时候打了字。那轮**自然结束了**(没有被中断),于是"中断路径"从来没被触发,那条消息就永远躺在 `_interrupt_queue` 里。用户再敲回车 —— 因为 agent 其实已经停了?不,更糟:只要还在同一轮判定窗口里,新输入继续路由到同一个没人取的队列。CLI 看起来彻底冻住。根因是一个 PR 拆分事故:#17939 原本把"粘贴文件 TOCTOU 修复"和"turn 末排水"打包在一起,评审时把后者拆出去说"值得单独评审",然后**再也没人 land 它**(#17666 / #18760),直到 #20271 重新发现。

**可迁移原则**:任何"忙时改路由"的设计,必须在"忙"结束时**无条件**把备用通道排空 —— 不能依赖某条特定的成功路径去排。

**(4) 目标续跑判定**(17551-17560)。**(5) 连续语音自动重启录音**(17562-17580)。**(6) 后台进程通知排水**(17582-17587)。

其中目标续跑对 Ctrl-C 有特殊语义 —— 被打断的一轮不判定、直接暂停目标:

`cli.py:10786-10800 @ 863e313`

```python
        # If the turn was user-interrupted (Ctrl+C), auto-pause the goal
        # and bail. The judge call would almost always return "continue"
        # on the partial output and immediately re-queue another turn,
        # which is exactly what the user cancelled. Pausing (rather than
        # silently skipping) is the observable, recoverable behavior.
        if getattr(self, "_last_turn_interrupted", False):
            try:
                mgr.pause(reason="user-interrupted (Ctrl+C)")
            except Exception as exc:
                logging.debug("goal pause-on-interrupt failed: %s", exc)
            _cprint(
                f"  {_DIM}⏸ Goal paused — turn was interrupted. "
                f"Use /goal resume to continue, or /goal clear to stop.{_RST}"
            )
            return
```

**这是"自动化循环 + 人工中断"必须处理的经典冲突**:自动判定器只看输出,看不到"用户按了 Ctrl-C"这个意图。不显式建模这个意图,Ctrl-C 就等于没按。

### 2.9 `app.run()` 外面的三层保护(17690–17929)

#### 2.9.1 前置健康检查

在起 pt 之前先验 stdin:

`cli.py:17746-17759 @ 863e313`

```python
        # Validate stdin before launching prompt_toolkit — on macOS with
        # uv-managed Python, fd 0 can be invalid or unregisterable with the
        # asyncio selector, causing "KeyError: '0 is not registered'" (#6393).
        try:
            os.fstat(0)
        except OSError:
            print(
                "Error: stdin (fd 0) is not available.\n"
                "This can happen with certain Python installations (e.g. uv-managed cPython on macOS).\n"
                "Try reinstalling Python via pyenv or Homebrew, then re-run: hermes setup"
            )
            _run_cleanup()
            self._print_exit_summary()
            return
```

以及 macOS 上探测 kqueue 能否注册 fd 0,不能就换 `SelectSelector` 事件循环策略:

`cli.py:17761-17783 @ 863e313`

```python
        # On macOS with uv-managed Python, kqueue's selector cannot register
        # fd 0, raising OSError(EINVAL) from kqueue.control() when prompt_toolkit
        # calls loop.add_reader (#6393). Probe kqueue and, if it can't watch
        # stdin, switch to a SelectSelector-backed event loop policy.
        if sys.platform == "darwin":
            try:
                import selectors as _selectors
                if hasattr(_selectors, "KqueueSelector"):
                    _kq = _selectors.KqueueSelector()
                    try:
                        _kq.register(0, _selectors.EVENT_READ)
                        _kq.unregister(0)
                    finally:
                        _kq.close()
            except (OSError, ValueError, KeyError):
                import asyncio as _aio_probe
                import selectors as _selectors

                class _SelectEventLoopPolicy(_aio_probe.DefaultEventLoopPolicy):
                    def new_event_loop(self):
                        return _aio_probe.SelectorEventLoop(_selectors.SelectSelector())

                _aio_probe.set_event_loop_policy(_SelectEventLoopPolicy())
```

**这是"用探针替代版本嗅探"的好例子**:不去判断"是不是 uv 装的 Python",而是直接试一次 `kq.register(0)`。探针便宜、准确、不会随环境演化而失效。

#### 2.9.2 三层 try 的实际形状

`cli.py:17785-17787 @ 863e313`

```python
        # Run the application with patch_stdout for proper output handling
        try:
            with patch_stdout():
```

`cli.py:17799-17806 @ 863e313`

```python
                # The app enables focus reporting + mouse tracking; record that
                # so _run_cleanup resets them on exit (#36823).
                _mark_tui_input_modes_active()
                # Drive the petdex mascot animation (no-op when no pet enabled).
                self._pet_start_anim()
                app.run()
        except (EOFError, KeyboardInterrupt, BrokenPipeError):
            pass
```

`cli.py:17807-17827 @ 863e313`

```python
        except (KeyError, OSError) as _stdin_err:
            # Catch selector registration failures from broken stdin (#6393)
            # and I/O errors from broken stdout during interrupt (#13710).
            _errno = getattr(_stdin_err, "errno", None) if isinstance(_stdin_err, OSError) else None
            _msg = str(_stdin_err)
            if _errno == errno.EIO:
                pass  # suppress broken-stdout I/O errors on interrupt (#13710)
            elif (
                _errno in {errno.EINVAL, errno.EBADF}
                or "is not registered" in _msg
                or "Bad file descriptor" in _msg
                or "Invalid argument" in _msg
            ):
                print(
                    f"\nError: stdin is not usable ({_stdin_err}).\n"
                    "This can happen with certain Python installations (e.g. uv-managed cPython on macOS)\n"
                    "where kqueue cannot register fd 0.\n"
                    "Try reinstalling Python via pyenv or Homebrew, then re-run: hermes setup"
                )
            else:
                raise
```

`cli.py:17828-17830 @ 863e313`

```python
        finally:
            self._should_exit = True
            self._pet_stop_anim()
```

即:`EOFError`/`KeyboardInterrupt`/`BrokenPipeError` 静默吞;`KeyError`/`OSError` 按 errno 分类,只有已知的 stdin/stdout 病症被吞,其余**重抛**;其他任何异常直接穿透(`finally` 会先跑完)。

`erase_when_done=True` 是另一个值得记的细节,解释了为什么退出后终端是干净的:

`cli.py:17264-17274 @ 863e313`

```python
            # Erase the live bottom chrome (status bar, input box, separator
            # rules) on exit instead of freezing a final copy into scrollback.
            # Without this, prompt_toolkit's render_as_done teardown repaints
            # the chrome one last time and leaves it stranded above the exit
            # summary — so a dead status bar + empty prompt sit between the
            # conversation transcript and the "Resume this session" block, and
            # stack with the next session's UI on resume (#38252). The actual
            # conversation transcript is printed through patch_stdout into
            # normal scrollback and is unaffected; only the managed chrome is
            # erased. Applies to every exit path (/exit, /quit, EOF, Ctrl+C).
            erase_when_done=True,
```

#### 2.9.3 `_suppress_closed_loop_errors`:一段**永远不会生效**的代码

先看它想做什么:

`cli.py:17728-17744 @ 863e313`

```python
        # Install a custom asyncio exception handler that suppresses the
        # "Event loop is closed" RuntimeError from httpx transport cleanup
        # and the "0 is not registered" KeyError from broken stdin (#6393).
        # The RuntimeError fix is defense-in-depth — the primary fix is
        # neuter_async_httpx_del which disables __del__ entirely.  The
        # KeyError fix handles macOS + uv-managed Python environments where
        # fd 0 is not reliably available to the asyncio selector.
        def _suppress_closed_loop_errors(loop, context):
            exc = context.get("exception")
            if isinstance(exc, RuntimeError) and "Event loop is closed" in str(exc):
                return  # silently suppress
            if isinstance(exc, KeyError) and "is not registered" in str(exc):
                return  # suppress selector registration failures (#6393)
            if isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.EIO:
                return  # suppress I/O errors from broken stdout on interrupt (#13710)
            # Fall back to default handler for everything else
            loop.default_exception_handler(context)
```

再看它怎么被安装的:

`cli.py:17788-17798 @ 863e313`

```python
                # Set the custom handler on prompt_toolkit's event loop
                try:
                    import asyncio as _aio
                    # Use get_running_loop() to avoid DeprecationWarning on
                    # Python 3.10+ when called outside an async context.
                    _loop = _aio.get_running_loop()
                    _loop.set_exception_handler(_suppress_closed_loop_errors)
                except RuntimeError:
                    pass  # No running loop -- nothing to patch
                except Exception:
                    pass
```

`run()` 是同步方法(`main()` 在 18549 直接调它,调用链上没有任何 `async`),所以 `asyncio.get_running_loop()` **必然**抛 `RuntimeError`。容器内实测:

```
cli.py:17789-17796 equivalent -> SKIPPED (RuntimeError: no running event loop)
```

而且即使装上了也没用:`app.run()` 内部 `set_exception_handler=True` 默认开启,pt 会把自己的处理器覆盖上去,退出时再还原:

`prompt_toolkit/application/application.py:826-834 @ 863e313`

```python
        @contextmanager
        def set_exception_handler_ctx(loop: AbstractEventLoop) -> Iterator[None]:
            if set_exception_handler:
                previous_exc_handler = loop.get_exception_handler()
                loop.set_exception_handler(self._handle_exception)
                try:
                    yield
                finally:
                    loop.set_exception_handler(previous_exc_handler)
```

pt 的处理器长这样 —— 正好就是所有相关注释想避免的那个"Press ENTER to continue":

`prompt_toolkit/application/application.py:1018-1026 @ 863e313`

```python
        async def in_term() -> None:
            async with in_terminal():
                # Print output. Similar to 'loop.default_exception_handler',
                # but don't use logger. (This works better on Python 2.)
                print("\nUnhandled exception in event loop:")
                print(formatted_tb)
                print("Exception {}".format(context.get("exception")))

                await _do_wait_for_enter("Press ENTER to continue...")
```

**两条独立的理由,该抑制器一次都没生效过。** 详见 §3 缺陷 2、§4 冲突 2。

### 2.10 信号处理与退出看门狗

#### `_signal_handler`(SIGTERM / SIGHUP,交互模式)

`cli.py:17610-17638 @ 863e313`

```python
        def _signal_handler(signum, frame):
            """Handle SIGHUP/SIGTERM by triggering graceful cleanup.

            Calls ``self.agent.interrupt()`` first so the agent daemon
            thread's poll loop sees the per-thread interrupt and kills the
            tool's subprocess group via ``_kill_process`` (os.killpg).
            Without this, the main thread dies from KeyboardInterrupt and
            the daemon thread is killed with it — before it can run one
            more poll iteration to clean up the subprocess, which was
            spawned with ``os.setsid`` and therefore survives as an orphan
            with PPID=1.

            Grace window (``HERMES_SIGTERM_GRACE``, default 1.5 s) gives
            the daemon time to: detect the interrupt (next 200 ms poll) →
            call _kill_process (SIGTERM + 1 s wait + SIGKILL if needed) →
            return from _wait_for_process.  ``time.sleep`` releases the
            GIL so the daemon actually runs during the window.

            Guarded ``logger.debug``: CPython's ``logging`` module is not
            reentrant-safe.  ``Logger.isEnabledFor`` caches level results
            in ``Logger._cache``; under shutdown races the cache can be
            cleared (``_clear_cache``) or mid-mutation when the signal
            fires, raising ``KeyError: <level_int>`` (e.g. ``KeyError: 10``
            for DEBUG) inside the handler.  That KeyError then escapes
            before ``raise KeyboardInterrupt()`` can fire, which bypasses
            prompt_toolkit's normal interrupt unwind and surfaces as the
            EIO cascade from issue #13710.  Wrap the log in a bare
            ``try/except`` so the handler can never raise through it.
            """
```

这段 docstring 是全仓最好的"信号处理器写作教材",三条硬约束:

1. **孤儿进程组问题**:工具用 `os.setsid` 起子进程。主线程死掉时 daemon 线程跟着死,来不及 `killpg`,子进程被 init 收养。所以必须先 `interrupt()` 再给一个宽限窗口。
2. **`time.sleep` 释放 GIL**,所以宽限窗口是真的能让 daemon 线程跑起来的(不是空转)。
3. **`logging` 在信号处理器里不可重入**:`Logger._cache` 可能正在被清空,`isEnabledFor` 抛 `KeyError: 10`。这个 KeyError 会在 `raise KeyboardInterrupt()` 之前逃逸,绕过 pt 的正常 unwind,变成 #13710 的 EIO 级联。所以**信号处理器里的日志必须裸 try 包住**。

处理器体内先做的事是**立刻武装退出兜底**:

`cli.py:17643-17649 @ 863e313`

```python
            # Shutdown intent is now unambiguous — arm the exit backstop
            # IMMEDIATELY, before the graceful unwind below.  If any step of
            # that unwind wedges (main thread parked in a syscall, prompt_toolkit
            # teardown never returning), _run_cleanup never runs and would
            # never arm its own watchdog — leaving a "dead" CLI alive for
            # minutes (#65998 class).  Never raises.
            _arm_exit_watchdog_on_shutdown_signal()
```

然后**优先走 `app.exit()` 而不是抛 KeyboardInterrupt**:

`cli.py:17664-17688 @ 863e313`

```python
            # Prefer a clean prompt_toolkit exit over `raise KeyboardInterrupt()`.
            # Raising KBI from a signal handler unwinds into whatever Python
            # frame the interpreter happens to be running — typically an
            # `await asyncio.sleep()` inside prompt_toolkit's
            # `_poll_output_size` coroutine.  The KBI becomes a Task
            # exception, prompt_toolkit's `_handle_exception` prints
            # "Unhandled exception in event loop" + the full traceback, and
            # parks the terminal on "Press ENTER to continue..." (#13710
            # variant — same root cause, different surface).
            #
            # `app.exit()` scheduled via `call_soon_threadsafe` lets the
            # event loop unwind normally; `app.run()` returns and our
            # existing `except (EOFError, KeyboardInterrupt, BrokenPipeError)`
            # block at the bottom of the input loop handles the rest.
            try:
                from prompt_toolkit.application.current import get_app_or_none
                _app = get_app_or_none()
                if _app is not None:
                    _loop = getattr(_app, "loop", None)
                    if _loop is not None:
                        _loop.call_soon_threadsafe(_app.exit)
                        return  # clean unwind — no traceback, no ENTER pause
            except Exception:
                pass
            raise KeyboardInterrupt()  # fallback for non-prompt_toolkit contexts
```

**核心洞察**:从信号处理器里抛异常,异常会在解释器**恰好正在执行的那一帧**里冒出来 —— 在 asyncio 程序里,那大概率是某个 coroutine 内部,于是变成 Task 异常而不是主流程的中断。正确做法是**把"退出"作为一条消息投递给事件循环**(`call_soon_threadsafe`),让循环自己走正常的收尾。

注册只覆盖 SIGTERM/SIGHUP(POSIX 的 SIGINT 明确不管):

`cli.py:17690-17694 @ 863e313`

```python
        try:
            import signal as _signal
            _signal.signal(_signal.SIGTERM, _signal_handler)
            if hasattr(_signal, 'SIGHUP'):
                _signal.signal(_signal.SIGHUP, _signal_handler)
```

Windows 单独装一个吞掉 SIGINT 的空处理器:

`cli.py:17696-17724 @ 863e313`

```python
            # Windows: install a SIGINT handler that absorbs the signal
            # instead of letting Python's default handler raise
            # KeyboardInterrupt in MainThread. Windows Terminal / Win32
            # delivers spurious CTRL_C_EVENT to the hermes process when
            # child processes are spawned from background threads (agent
            # subprocess Popen path). The default Python SIGINT handler
            # would then unwind prompt_toolkit's app.run(), trigger
            # _run_cleanup mid-turn, and close browser sessions mid-open
            # — causing "Daemon process exited during startup" errors.
            #
            # The handler is a silent no-op. Real user Ctrl+C still works
            # because prompt_toolkit binds c-c at the TUI layer and never
            # reaches this OS-signal path. This matches how Claude Code
            # handles the same Windows quirk (cancellation is driven by
            # the TUI key handler, not by OS signals).
            #
            # POSIX: leave the default SIGINT handler alone. prompt_toolkit
            # installs its own handler there and it works as expected.
            if sys.platform == "win32":
                def _sigint_absorb(signum, frame):
                    # Absorb silently. Do NOT call agent.interrupt() here:
                    # Windows fires spurious CTRL_C_EVENT whenever a
                    # background thread spawns a .cmd subprocess, and
                    # interrupt() would inject a fake user message each
                    # time. Real user Ctrl+C routes through prompt_toolkit's
                    # own c-c key binding at the TUI layer (same pattern as
                    # Claude Code's Windows handling).
                    return
                _signal.signal(_signal.SIGINT, _sigint_absorb)
```

Windows 需要这个补丁的直接原因在 pt 里:pt 在 Windows 上根本不注册 SIGINT 处理器(`prompt_toolkit/application/application.py:653-658 @ 863e313` 强制 `handle_sigint = False`),所以 Python 默认处理器会真的抛 KeyboardInterrupt。POSIX 上被 pt 接管,变成路径 B 的静默吞。

#### 退出看门狗:三层

**第一层**:`_run_cleanup` 一开始就武装 30s 定时器。

`cli.py:1064-1085 @ 863e313`

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

    The shared daemon pool (``tools.daemon_pool``) removes the main cause
    of (2); this watchdog is the backstop for both. It arms a daemon
    timer when ``_run_cleanup`` starts; if the process is still alive
    after ``timeout_s`` it flushes logging/stdio and calls ``os._exit(0)``.
    Daemon threads keep running through ``Py_FinalizeEx``'s thread joins,
    so the timer fires even when the main thread is stuck in teardown.

    Tune with ``HERMES_EXIT_WATCHDOG_S`` (seconds); ``0`` disables.
    """
```

其中最精妙的一句是"**daemon 线程在 `Py_FinalizeEx` 的线程 join 阶段仍然在跑**",所以这个定时器即使在解释器已经开始 teardown、主线程卡死时也能开火。

测试环境豁免也写得对:

`cli.py:1093-1096 @ 863e313`

```python
    # Never arm under pytest: tests invoke _run_cleanup() directly and a
    # 30s-delayed os._exit(0) would silently kill the test worker.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
```

**第二层**:信号到达时就武装(2× 时长),因为从信号到 `_run_cleanup` 之间还有好几个可能卡死的点:

`cli.py:1132-1156 @ 863e313`

```python
def _arm_exit_watchdog_on_shutdown_signal() -> None:
    """Arm the exit backstop the moment a termination signal arrives.

    SIGTERM/SIGHUP establish unambiguous shutdown intent, but the graceful
    path from signal → ``agent.interrupt()`` → ``app.exit()`` /
    ``KeyboardInterrupt`` → ``finally`` → ``_run_cleanup`` has several wedge
    points BEFORE ``_run_cleanup`` arms the normal watchdog: a main thread
    parked in a syscall that never observes the unwind, a prompt_toolkit
    teardown that never returns, or an agent worker blocking the ``finally``.
    When that happens the process has NO backstop and a "dead" CLI lingers
    (observed: ``hermes --tui`` alive ~47 min at 4% CPU after terminal close —
    the #65998 class).

    Arming at signal time closes that window. The leash is 2× the normal
    cleanup timeout so a slow-but-progressing ``_run_cleanup`` (which arms
    its own tighter timer when it starts) is never cut short by this outer
    backstop — this timer only wins when cleanup was never reached at all.

    Deliberately NOT armed at chat startup: the watchdog thread calls
    ``os._exit(0)`` unconditionally after its sleep, so arming without
    shutdown intent would hard-kill every session that outlives the timeout.

    Idempotent (module flag) so repeated signals don't stack timer threads.
    Never raises — safe to call from a signal handler.
    """
```

"**2× 而不是同一时长**"这个细节值得记:外层兜底必须比内层松,否则会把"慢但在推进"的正常清理砍掉。

**第三层**:kanban worker 的 `os._exit(0)` —— 见 §2.13。

### 2.11 清理路径全景(前提 3 的完整答案)

一次交互式退出可能触及的清理入口共 **6 个**:

| 入口 | 位置 | 触发条件 | 幂等? |
|---|---|---|---|
| `run()` 的 `finally` 块 | `cli.py:17828-17920` | `app.run()` 任何方式返回 | 单次执行(try/finally) |
| `_run_cleanup()` 显式调用 | `cli.py:17918`(还有 17757) | `finally` 走到底 | 全局锁,至多一次 |
| `atexit.register(_run_cleanup)` | `cli.py:17607` **和** `cli.py:18241` | 解释器正常退出 | 同上,第 2 次 no-op |
| `atexit.register(self._release_active_session)` | `cli.py:4778` | 同上 | `lease is None` 检查 |
| 退出看门狗 `os._exit(0)` | `cli.py:1119` | 30s / 60s 超时 | 绕过一切 |
| kanban worker `os._exit(0)` | `cli.py:18308` | SIGTERM + `HERMES_KANBAN_TASK` | 绕过一切 |

核心幂等锁:

`cli.py:989 @ 863e313`

```python
_cleanup_done = False
```

`cli.py:1173-1183 @ 863e313`

```python
def _run_cleanup(*, notify_session_finalize: bool = True):
    """Run resource cleanup exactly once."""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True

    # Bound total shutdown time: if cleanup (or the interpreter's
    # thread-join teardown after it) wedges, force-exit instead of
    # leaving a zombie CLI holding the terminal for minutes.
    _arm_exit_watchdog()
```

**注意标志位在干活之前置位。** 这是刻意的(避免重入/递归),但代价是:**任何一步抛出未捕获异常,后续步骤永久跳过,且没有任何重试机会。** `_run_cleanup` 内部 12 个步骤里 11 个有 try 包裹,唯一裸露的是:

`cli.py:1225-1232 @ 863e313`

```python
    if notify_session_finalize:
        cleanup_session_id = _active_agent_ref.session_id if _active_agent_ref else None
        if _should_emit_cleanup_session_finalize(cleanup_session_id):
            _notify_session_finalize(
                session_id=cleanup_session_id,
                platform="cli",
                reason="shutdown",
            )
```

`_active_agent_ref.session_id` 无保护;若 `_active_agent_ref` 是一个没有 `session_id` 的替身,`AttributeError` 会跳过后面的 memory provider 关停(1233-1269),而 memory provider 的 `shutdown_memory_provider` 正是最需要跑的一步(会话记忆提取)。触发条件苛刻,列为低置信。

**终端输入模式的复位**被刻意放在最前面,理由写得很清楚:

`cli.py:1185-1189 @ 863e313`

```python
    # Reset terminal input modes first, before the slower resource teardown
    # below (MCP / browser / memory shutdown can take seconds). On Ctrl+C the
    # user's terminal becomes usable immediately, and a later step raising
    # can't skip the reset (#36823). No-op unless the TUI actually ran.
    _reset_terminal_input_modes_on_exit()
```

**可迁移原则**:清理步骤要按"**用户可感知程度**"排序,不是按依赖关系排序。终端复位对用户是立刻可见的,MCP 关停是不可见的 —— 所以前者必须先跑,且必须排在任何可能抛异常/超时的步骤之前。

`finally` 块本身的顺序(17828–17920):

1. `_should_exit = True`、停宠物动画(17829-17830)
2. 打印 "Shutting down…"(17836-17839)
3. 中断 agent(17844-17848)
4. 关语音录音器 + 清临时录音(17850-17861)
5. **反注册三个回调**(17862-17865)—— **无 try 包裹**
6. `_persist_active_session_before_close()`(17870)
7. SQLite `end_session` / 空会话剪枝 / `--delete` 删除(17872-17899)
8. `on_session_end` 插件钩子(17900-17917)
9. `_run_cleanup()` / `_print_exit_summary()` / `_release_active_session()`(17918-17920)

第 5 步是唯一裸露的调用:

`cli.py:17862-17865 @ 863e313`

```python
            # Unregister callbacks to avoid dangling references
            set_sudo_password_callback(None)
            set_approval_callback(None)
            set_secret_capture_callback(None)
```

这三个是懒导入包装:

`cli.py:965-968 @ 863e313`

```python
def set_sudo_password_callback(*args, **kwargs):
    from tools.terminal_tool import set_sudo_password_callback as _set_sudo_password_callback

    return _set_sudo_password_callback(*args, **kwargs)
```

`ImportError` 在这里会跳过第 6–9 步的**全部**内容 —— 包括会话落盘。实践中 `tools.terminal_tool` 早已导入,概率很低,但结构上它是这条链上唯一没保险的一环。

**`/update` 的延迟重启**放在 `finally` 之后,注释解释了为什么:

`cli.py:17922-17929 @ 863e313`

```python
        # Deferred relaunch: /update sets _pending_relaunch so the exec
        # happens here — after prompt_toolkit has exited and fully restored
        # terminal modes — rather than from the background process_loop
        # thread (which would skip terminal cleanup on POSIX and only exit
        # the worker thread on Windows).
        if getattr(self, '_pending_relaunch', None):
            from hermes_cli.relaunch import relaunch
            relaunch(self._pending_relaunch, preserve_inherited=False)
```

`relaunch` 在 POSIX 上是 `os.execvp`(`hermes_cli/relaunch.py:205 @ 863e313`),**替换进程映像 → atexit 不跑**。已显式跑过的 `_run_cleanup` / `_release_active_session` 不受影响,但 §3 缺陷 5 里的 worktree 清理会被漏掉。

### 2.12 `_run_kanban_goal_loop_q`(17936–18023)

只有一个调用点,在 `-Q` 静默单查询路径里:

`cli.py:18477-18488 @ 863e313`

```python
                        # Kanban goal-loop mode: a worker spawned for a
                        # goal_mode card keeps working in THIS session until an
                        # auxiliary judge agrees the card is done, the worker
                        # terminates the task itself, or the turn budget runs
                        # out (→ sticky block). Gated on the env vars the
                        # dispatcher sets in `_default_spawn`; a no-op for every
                        # normal worker and every non-kanban `-q` run.
                        if os.environ.get("HERMES_KANBAN_GOAL_MODE") == "1":
                            try:
                                _run_kanban_goal_loop_q(cli, response)
                            except Exception as _goal_exc:
                                logger.debug("kanban goal loop failed: %s", _goal_exc)
```

"只在 quiet 分支里"这个约束是 dispatcher 侧强制的,而且有事故编号:

`hermes_cli/kanban_db.py:9135-9141 @ 863e313`

```python
    if task.goal_mode:
        # Goal-mode workers must take the fully-quiet single-query path:
        # the kanban goal-loop hook (_run_kanban_goal_loop_q) only runs in
        # cli.py's quiet branch. Without -Q the worker gets exactly one
        # turn, prints text, exits rc=0, and the dispatcher records a
        # protocol violation (incident 2026-06-09 t_d9cbe312).
        cmd.append("-Q")
```

函数本身把 kanban DB 和 goals 模块用四个注入点缝起来:

`cli.py:17977-17991 @ 863e313`

```python
    def _run_turn(prompt: str) -> str:
        result = cli.agent.run_conversation(
            user_message=prompt,
            conversation_history=cli.conversation_history,
        )
        # Keep session_id in sync if mid-run compression rotated it.
        if (
            getattr(cli.agent, "session_id", None)
            and cli.agent.session_id != cli.session_id
        ):
            cli.session_id = cli.agent.session_id
        resp = result.get("final_response", "") if isinstance(result, dict) else str(result)
        if resp:
            print(resp)
        return resp or ""
```

`cli.py:18014-18023 @ 863e313`

```python
    _run_loop(
        task_id=task_id,
        goal_text=goal_text,
        run_turn=_run_turn,
        task_status_fn=_task_status,
        block_fn=_block,
        max_turns=max_turns,
        first_response=first_response or "",
        log=lambda m: logger.info("%s", m),
    )
```

依赖注入做得很干净(`hermes_cli/goals.py:2014-2017 @ 863e313` 的 docstring 明说 "fully decoupled from the CLI for testability"),但**返回值被丢弃**(`run_kanban_goal_loop` 声明 `-> Dict[str, Any]`,`_run_kanban_goal_loop_q` 声明 `-> None`)。见 §3 缺陷 3、缺陷 4。

DB 连接管理是"每次操作开一条、finally 关掉"的保守写法,三处一模一样(17957-17964、17994-18002、18005-18012):

`cli.py:17957-17964 @ 863e313`

```python
    conn = _kb.connect()
    try:
        task = _kb.get_task(conn, task_id)
    finally:
        try:
            conn.close()
        except Exception:
            pass
```

### 2.13 `main()`(18026–18549):不是进程入口

#### 真正的入口链

`pyproject.toml:358-359 @ 863e313`

```toml
[project.scripts]
hermes = "hermes_cli.main:main"
```

`hermes_cli.main:main` 用 argparse 分发到 `cmd_chat`,`cmd_chat` **导入并以 kwargs 调用** `cli.main`:

`hermes_cli/main.py:2708-2738 @ 863e313`

```python
    # Import and run the CLI
    from cli import main as cli_main

    # Build kwargs from args
    kwargs = {
        "model": args.model,
        "provider": getattr(args, "provider", None),
        "reasoning": getattr(args, "reasoning", None),
        "toolsets": args.toolsets,
        "skills": getattr(args, "skills", None),
        "verbose": getattr(args, "verbose", None),
        "quiet": getattr(args, "quiet", False),
        "query": args.query,
        "image": getattr(args, "image", None),
        "resume": getattr(args, "resume", None),
        "worktree": getattr(args, "worktree", False),
        "checkpoints": getattr(args, "checkpoints", False),
        "pass_session_id": getattr(args, "pass_session_id", False),
        "max_turns": getattr(args, "max_turns", None),
        "ignore_rules": getattr(args, "ignore_rules", False) or getattr(args, "safe_mode", False),
        "ignore_user_config": getattr(args, "ignore_user_config", False) or getattr(args, "safe_mode", False),
        "compact": getattr(args, "compact", False),
    }
    # Filter out None values
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    try:
        cli_main(**kwargs)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
```

而 `fire.Fire` 只服务 `python cli.py` 直跑:

`cli.py:18552-18555 @ 863e313`

```python
if __name__ == "__main__":
    import fire

    fire.Fire(main)
```

**所以 `cli.main()` 的定位是:一个用 Fire 风格签名写、但实际主要被当作库函数用 kwargs 调用的装配入口。** 它的形参分成三类:

- **两条路都走的**:`model` / `provider` / `toolsets` / `skills` / `query` / `image` / `quiet` / `resume` / `worktree` / `checkpoints` / `max_turns` / `compact` / `verbose` / `reasoning` / `pass_session_id` / `ignore_rules`
- **只有 `python cli.py` 能到的**:`list_tools` / `list_toolsets` / `gateway` / `q` / `w` / `api_key` / `base_url`(`cmd_chat` 的 kwargs 里没有它们)
- **完全没用的**:`ignore_user_config`(见 §3 缺陷 8)

#### `main()` 的执行顺序

1. Windows UTF-8 stdio(18091-18095)
2. `HERMES_INTERACTIVE=1`(18097-18099)
3. `gateway=True` → 起 gateway 并 return(18102-18107)
4. **git worktree 隔离**(18110-18135)
5. toolsets 解析 / coding 姿态推断(18140-18169)
6. 构造 `HermesCLI`(18174-18188)
7. skills 预载(18190-18216),**全部缺失才硬失败**:

`cli.py:18195-18211 @ 863e313`

```python
        if missing_skills:
            missing_display = ", ".join(missing_skills)
            # If at least one skill loaded, degrade gracefully: skip the
            # unknown ones and continue. A typo'd skill name should not crash
            # the worker (which auto-blocks the Kanban task after retries).
            # Only when EVERY requested skill is missing do we hard-fail, so a
            # fully-misconfigured worker fails loudly instead of running blind.
            if loaded_skills:
                logger.warning(
                    "Unknown skill(s) requested, skipping: %s. "
                    "Continuing with: %s. "
                    "List available skills with `hermes skills list`.",
                    missing_display,
                    ", ".join(loaded_skills),
                )
            else:
                raise ValueError(f"Unknown skill(s): {missing_display}")
```

("**部分坏 → 降级,全坏 → 响亮失败**"是个好默认;`cmd_chat` 恰好把 `ValueError` 接住转成 exit 1。)

8. `--list-tools` / `--list-toolsets` → `sys.exit(0)`(18230-18238)
9. `atexit.register(_run_cleanup)`(18241)
10. `_signal_handler_q` 注册(18258-18317)—— **无条件**,交互模式也装
11. `if query or image:` 单次查询(18320-18546)
12. `cli.run()`(18549)

#### kanban worker 的 `os._exit(0)`

`cli.py:18276-18308 @ 863e313`

```python
        # Kanban worker exit path (#28181): SIGTERM hits a dispatcher-spawned
        # worker that's likely in a non-daemon thread waiting on a child
        # subprocess in _wait_for_process. Raising KeyboardInterrupt only
        # unwinds the main thread; the worker thread keeps running, the
        # process gets reparented to init, and the dispatcher's _pid_alive
        # check returns True forever — task stuck in 'running' indefinitely.
        # Skip the controlled-unwind dance and call os._exit(0) so the kernel
        # reclaims the PID immediately and detect_crashed_workers can reclaim
        # the stale claim on the next tick. Flush logging + stdout/stderr
        # first so the final debug trace isn't lost; SIGALRM deadman guards
        # the flush against any rare blocking-I/O case (the reporter measured
        # flush in <1ms; the alarm is a failsafe, not the common path).
        if os.environ.get("HERMES_KANBAN_TASK"):
            try:
                import signal as _sig_mod
                if hasattr(_sig_mod, "SIGALRM"):
                    # Cancel any pre-existing alarm to avoid colliding with
                    # caller-installed timers.
                    _sig_mod.signal(_sig_mod.SIGALRM, lambda *_: os._exit(0))
                    _sig_mod.alarm(2)
            except Exception:
                pass
            try:
                import logging as _lg
                _lg.shutdown()
            except Exception:
                pass
            for _stream in (sys.stdout, sys.stderr):
                try:
                    _stream.flush()
                except Exception:
                    pass
            os._exit(0)
```

**"用 SIGALRM 给 flush 上死人开关"**是个值得抄的模式:要在 `os._exit` 前 flush 日志,但 flush 本身理论上可能阻塞;先装 2s 的 SIGALRM → `os._exit(0)`,再 flush。正常 <1ms 走完,异常时闹钟兜底。

#### 单次查询的退出码契约

`cli.py:18493-18518 @ 863e313`

```python
                        # Ensure proper exit code for automation wrappers.
                        #
                        # Kanban workers get a special case: when the run failed
                        # purely because the provider rate-limited / exhausted
                        # quota (not because the task itself is broken), exit with
                        # the EX_TEMPFAIL sentinel instead of the generic 1. The
                        # dispatcher's reap classifier maps that code to a
                        # ``rate_limited`` exit and releases the task back to
                        # ``ready`` WITHOUT incrementing the failure counter, so a
                        # 5-hour quota window can't trip the circuit breaker and
                        # permanently block the card. Non-kanban runs keep the
                        # plain 0/1 contract automation wrappers expect.
                        _exit_code = 0
                        if isinstance(result, dict) and result.get("failed"):
                            _exit_code = 1
                            if os.environ.get("HERMES_KANBAN_TASK") and result.get(
                                "failure_reason"
                            ) in ("rate_limit", "billing"):
                                try:
                                    from hermes_cli.kanban_db import (
                                        KANBAN_RATE_LIMIT_EXIT_CODE as _RL_CODE,
                                    )
                                    _exit_code = _RL_CODE
                                except Exception:
                                    _exit_code = 1
                        sys.exit(_exit_code)
```

**"限流不是失败"**这个区分很重要:失败计数器 + 熔断会把卡片永久 block,而配额窗口只是暂时的。用一个专门的退出码把两者分开,是自动化调度里必须做的建模。

---

## 3. 可疑缺陷清单

### 缺陷 1:清理窗口内的 Ctrl-C 会打断 teardown 并抛出 traceback(置信度:**中高**)

**现象** `app.run()` 返回后进入 "Shutting down… (finalizing session)" 阶段(会话 flush + SQLite + MCP/浏览器/内存关停,可达数秒)。此时用户不耐烦按 Ctrl-C:进程先卡 1.5s,然后打印一段 `KeyboardInterrupt` traceback 退出;本轮未落盘的对话丢失,SQLite 会话没有 `end_session`,`on_session_end` 钩子不触发。

**锚点** `cli.py:18310-18317`(SIGINT 装的是 `_signal_handler_q`)、`cli.py:17690-17694`(交互模式只覆盖 SIGTERM/SIGHUP)、`cli.py:18264-18275`(1.5s sleep)、`cli.py:18309`(`raise KeyboardInterrupt()`)、`cli.py:17828-17920`(被打断的 `finally`)、`hermes_cli/main.py:12590-12595`(顶层无 KBI 捕获)。

```python
    try:
        import signal as _signal
        _signal.signal(_signal.SIGINT, _signal_handler_q)
        _signal.signal(_signal.SIGTERM, _signal_handler_q)
        if hasattr(_signal, "SIGHUP"):
            _signal.signal(_signal.SIGHUP, _signal_handler_q)
    except Exception:
        pass  # signal handler may fail in restricted environments
```

**为什么可疑** `_signal_handler_q` 是给 `-q` 单次查询写的,它的语义(interrupt agent → 睡 1.5s → 抛 KBI)对"已经在清理中的交互式会话"是错的:agent 早就被 17844-17848 中断过了,1.5s 纯粹是白等,抛 KBI 只会把清理拦腰截断。而交互路径的 `_signal_handler`(17610,会走 `app.exit()` 优雅路线)**只覆盖了 SIGTERM/SIGHUP,没接管 SIGINT**。

**触发条件** POSIX;交互模式;`app.run()` 已返回但 `finally` 未跑完(pt 已退出 raw mode,ISIG 恢复,Ctrl-C 变真 SIGINT);此窗口内按 Ctrl-C。会话越长、MCP server 越多,窗口越大。

**旁证** `atexit` 仍会补 `_run_cleanup` 和 `_release_active_session`,所以不会漏租约、不会漏终端复位;丢的是**会话持久化**(17870)和 **DB 收尾**(17872-17899)。

---

### 缺陷 2:`_suppress_closed_loop_errors` 是死代码,它想防的 "Press ENTER to continue" 一直裸露着(置信度:**高**)

**现象** 交互式 CLI 里,任何进入 asyncio 异常处理器的错误(httpx `__del__` 的 "Event loop is closed"、broken stdin 的 "0 is not registered"、中断时 broken stdout 的 `EIO`)都会被 prompt_toolkit 的 `_handle_exception` 接住,打印 `Unhandled exception in event loop` + 完整 traceback,然后把终端停在 `Press ENTER to continue...`。

**锚点** `cli.py:17735-17744`(处理器定义)、`cli.py:17789-17798`(安装点)、`prompt_toolkit/application/application.py:826-834`(pt 覆盖)、`prompt_toolkit/application/application.py:1018-1026`(pt 的行为)。

```python
                try:
                    import asyncio as _aio
                    # Use get_running_loop() to avoid DeprecationWarning on
                    # Python 3.10+ when called outside an async context.
                    _loop = _aio.get_running_loop()
                    _loop.set_exception_handler(_suppress_closed_loop_errors)
                except RuntimeError:
                    pass  # No running loop -- nothing to patch
```

**为什么可疑** 两条独立的失效原因:
1. `run()` 是同步方法,调用链(`hermes_cli.main:main` → `cmd_chat` → `cli.main` → `cli.run`)上没有任何 `async`,`asyncio.get_running_loop()` **必然** `RuntimeError`。容器内实测输出 `SKIPPED (RuntimeError: no running event loop)`。真正的循环是 `app.run()` 内部 `asyncio.run(coro)` 现建的,这段代码根本碰不到它。
2. 即使碰到了,`run_async(set_exception_handler=True)` 默认会在 `app.run()` 期间把处理器换成 pt 自己的,退出时再还原 —— 想抑制的窗口正好完全被覆盖。

注释里那句 "Use get_running_loop() to avoid DeprecationWarning ... when called outside an async context" 本身就承认了"在非 async 上下文里调用",却没意识到这等于把功能关掉了。

**触发条件** 每一次交互式启动都命中(这段代码 100% 走 `except RuntimeError: pass`)。用户可感知的后果需要同时发生一个 asyncio 层异常。

**测试为什么没发现** `tests/hermes_cli/test_suppress_eio_on_interrupt.py` **重建了一份等价副本**来测,从不触碰安装路径:

`tests/hermes_cli/test_suppress_eio_on_interrupt.py:25-31 @ 863e313`

```python
def _make_suppress_fn():
    """Build a standalone copy of ``_suppress_closed_loop_errors``.

    The real function is defined as a closure inside
    ``CLI._run_interactive``; we reconstruct an equivalent here so the
    unit tests don't need a full CLI instance.
    """
```

7 个测试全绿,证明的是"这个函数的分支逻辑对",而不是"这个函数会跑"。(顺带:`CLI._run_interactive` 这个方法名在 `cli.py` 里不存在,`grep -c "_run_interactive" cli.py` = 0。)

---

### 缺陷 3:kanban 目标循环的最终结局不影响 worker 退出码(置信度:**高**)

**现象** goal_mode worker 跑了 20 轮、最后因预算耗尽被 `block_fn` 打成 blocked,进程仍以第 1 轮的退出码退出(通常 0)。dispatcher 的 reap 分类器看到 rc=0,判定为正常完成。

**锚点** `cli.py:18484-18488`(调用点)、`cli.py:18505-18518`(退出码只读 `result`)、`cli.py:18014`(返回值被丢)、`hermes_cli/goals.py:2019-2022`(返回决策字典)。

```python
                        if os.environ.get("HERMES_KANBAN_GOAL_MODE") == "1":
                            try:
                                _run_kanban_goal_loop_q(cli, response)
                            except Exception as _goal_exc:
                                logger.debug("kanban goal loop failed: %s", _goal_exc)
```

```python
                        _exit_code = 0
                        if isinstance(result, dict) and result.get("failed"):
```

**为什么可疑** `result` 是**第一轮**的结果(18445 赋值),`_run_kanban_goal_loop_q` 在 18486 之后才跑了 N-1 轮,而它的返回值 —— 明确声明为 `Dict[str, Any]`,含 `{"outcome", "turns_used", "reason"}` —— 被 `_run_kanban_goal_loop_q` 整个吞掉(该函数签名是 `-> None`,18014 是裸调用)。特别地,缺陷所在的 rate-limit 特判(18508-18517)只看第一轮的 `failure_reason`:如果第 1 轮成功、第 12 轮被限流,worker 退出码是 0,卡片被判成"完成",限流退避机制完全不生效。

`hermes_cli/goals.py:2019-2022 @ 863e313`

```python
    Returns a decision dict: ``{"outcome", "turns_used", "reason"}`` where
    outcome is one of ``"completed_by_worker"``, ``"blocked_budget"``,
    ``"blocked_by_worker"``, or ``"stopped"``.
    """
```

**触发条件** `HERMES_KANBAN_GOAL_MODE=1` 的 worker,且首轮之后的任意一轮出现失败/限流,或循环以 `blocked_budget` 结束。

**缓解** `block_fn`(18004-18012)会把卡片写成 blocked,所以看板状态是对的;错的是**进程退出码**和依赖它的 dispatcher 分类。

---

### 缺陷 4:kanban 目标循环的续跑轮不携带对话历史(置信度:**中高**)

**现象** goal_mode worker 的第 2..N 轮看不到第 1..N-1 轮做了什么 —— 每轮都是一次"从零开始"的对话,只有 prompt 里带的续跑指令。

**锚点** `cli.py:17977-17981`、`cli.py:18445-18448`(quiet 路径也不回写)、`agent/turn_context.py:514`。

```python
    def _run_turn(prompt: str) -> str:
        result = cli.agent.run_conversation(
            user_message=prompt,
            conversation_history=cli.conversation_history,
        )
```

**为什么可疑** `run_conversation` 完全从传入的 `conversation_history` 构造本轮 messages,**没有**回退到 agent 自己的 `_session_messages`:

`agent/turn_context.py:514 @ 863e313`

```python
    messages = list(conversation_history) if conversation_history else []
```

而交互路径的 `chat()` **每轮都回写**:

`cli.py:14257 @ 863e313`

```python
            self.conversation_history = result.get("messages", self.conversation_history) if result else self.conversation_history
```

`_run_turn`(17977)和 quiet 单查询路径(18445-18461,只同步了 `session_id`)**都不回写**。且 `run_conversation` 不会原地修改调用方的列表(`list(...)` 复制;全仓 `grep "conversation_history\.\(append\|extend\|insert\|clear\|pop\)"` 在 `agent/` 与 `run_agent.py` 下**零命中**)。所以每次 `_run_turn` 拿到的都是同一份起始历史。

这与 18478-18479 的注释直接冲突:

```python
                        # Kanban goal-loop mode: a worker spawned for a
                        # goal_mode card keeps working in THIS session until an
```

session_id 确实是同一个(持久化行归属正确),但**模型的上下文不连续**。

**触发条件** 任何 goal_mode 卡片的第 2 轮及以后。

**未完全确认的部分** 没有实跑一个真 kanban worker(需要模型凭据,按项目边界不配置)。若 `run_conversation` 内部另有从 SessionDB 重载历史的路径(如 resume 语义),结论会变弱。判定所需的下一步:读 `agent/turn_context.py:341-380` 的 `recover_rotated_compression_session` 分支是否在此场景下命中。

---

### 缺陷 5:`/update` 走 `os.execvp`,跳过 worktree 的 atexit 清理(置信度:**中**)

**现象** `hermes chat -w`(worktree 隔离)会话里执行 `/update`,重启后旧的 git worktree 目录和分支残留。

**锚点** `cli.py:18129`(注册)、`cli.py:17927-17929`(exec 点)、`hermes_cli/relaunch.py:205`。

```python
                atexit.register(_cleanup_worktree, wt_info)
```

```python
        if getattr(self, '_pending_relaunch', None):
            from hermes_cli.relaunch import relaunch
            relaunch(self._pending_relaunch, preserve_inherited=False)
```

**为什么可疑** `os.execvp` 替换进程映像,`atexit` 注册的回调**不会执行**。`_run_cleanup` 和 `_release_active_session` 因为在 17918-17920 被显式调用过所以没事,但 `_cleanup_worktree` 只有 atexit 一条路。

**触发条件** `--worktree` / `-w` / `config.worktree: true` + `/update`。

**自愈** 下一次 `-w` 启动会 `_prune_stale_worktrees`(`cli.py:18118-18120`),所以只是暂时残留。因此严重度低。

---

### 缺陷 6:`process_loop` 只捕 `Exception`,`BaseException` 会让消费端线程静默死亡(置信度:**中**)

**现象** 输入框照常接受输入、回车照常清空草稿,但**永远没有响应** —— 消息进了 `_pending_input` 再也没人取。UI 无任何提示。

**锚点** `cli.py:17589-17590`。

```python
                except Exception as e:
                    logger.warning("process_loop unhandled error (msg may be lost): %s", e)
```

**为什么可疑** `self.chat()`(17514)或任何 slash handler 抛出 `SystemExit` / `KeyboardInterrupt` / 其他 `BaseException`,`while` 循环就地终止,线程退出,而 UI 线程和 `spinner_loop` 都不知情。`_should_exit` 仍是 False,`app.run()` 继续跑。这是**最难诊断的一类故障**:没有崩溃、没有日志、没有 UI 变化。

`slash` 分支已经单独护住了 `KeyboardInterrupt`(17473-17480),说明作者知道这个风险,但只补了一处。

**触发条件** 需要一个从 `chat()` 或某个 slash handler 逃逸的 `BaseException`。`cli.py` 内部的 `sys.exit` 都在 `main()` 里(18233/18238/18326/18452/18518/18521),不在交互路径上;`hermes_cli/` 下的命令处理器是否有 `SystemExit` 未逐一验证。

**判定所需的下一步** `grep -rn "sys.exit\|SystemExit" hermes_cli/commands*.py hermes_cli/slash*` 逐个命令核对。

---

### 缺陷 7:`handle_enter` 的三条内联 slash 旁路没有异常保护,会把 traceback 打进 UI 并停在 "Press ENTER"(置信度:**中高**)

**现象** `/model`、`/steer`、`/background` 的处理器一旦抛异常,终端上出现 `Unhandled exception in event loop:` + traceback,然后停在 `Press ENTER to continue...`;同时输入框里的命令文本**没被清空**(reset 在 return 之前的语句之后),诱发重复提交。

**锚点** `cli.py:15389-15402`(`/model`)、`cli.py:15410-15420`(`/steer`)、`cli.py:15428-15438`(`/background`)。对照 `cli.py:15307-15321`(model picker 分支**有** try)。

```python
                if self._should_handle_model_command_inline(text, has_images=has_images):
                    if not self.process_command(text):
                        self._should_exit = True
                        if event.app.is_running:
                            event.app.exit()
                    event.app.current_buffer.reset(append_to_history=True)
```

```python
            if self._model_picker_state:
                try:
                    # Picker selections follow the same session-scoped default
                    # as /model <name>; honour model.persist_switch_by_default.
                    from hermes_cli.model_switch import resolve_persist_behavior

                    self._handle_model_picker_selection(
                        persist_global=resolve_persist_behavior(False, False)
                    )
                except Exception as _exc:
                    _cprint(f"  ✗ Model selection failed: {_exc}")
                    self._close_model_picker()
```

**为什么可疑** 按键处理器里的异常会一路冒到 pt 的 `process_keys`,后者**重置解析器、清空输入队列、然后重抛**:

`prompt_toolkit/key_binding/key_processor.py:272-279 @ 863e313`

```python
            try:
                self._process_coroutine.send(key_press)
            except Exception:
                # If for some reason something goes wrong in the parser, (maybe
                # an exception was raised) restart the processor for next time.
                self.reset()
                self.empty_queue()
                raise
```

再往上是 asyncio 的 `add_reader` 回调,异常落到 loop 的 exception handler —— 由缺陷 2,那就是 pt 的 `_handle_exception`(打 traceback + Press ENTER)。**同一条命令走 `process_loop` 路径时只会被 17589 记一条 warning**,走内联路径就是一次 UI 事故。这个不对称本身就是问题。

**触发条件** `/model`、`/steer`、`/background` 的处理器抛异常(如 provider `/v1/models` 拉取失败、`agent.steer` 内部错误、后台会话创建失败)。

---

### 缺陷 8:`main()` 的 `ignore_user_config` 形参从未被使用(置信度:**高**,严重度低)

**锚点** `cli.py:18049`(声明)、`cli.py:432`(真正的机制是环境变量)、`hermes_cli/main.py:2674` 与 `10854`(两处设置该环境变量)。

```python
    ignore_user_config: bool = False,
```

`awk 'NR>=18026 && NR<=18556' cli.py | grep -n ignore_user_config` 只匹配到形参声明本身(相对第 24 行),函数体内零引用。真正生效的是:

`cli.py:430-436 @ 863e313`

```python
    # --ignore-user-config: force-skip the user config.yaml (still honor project
    # config as a fallback so defaults stay sensible).
    ignore_user_config = os.environ.get("HERMES_IGNORE_USER_CONFIG") == "1"

    # Use user config if it exists, otherwise project config
    if user_config_path.exists() and not ignore_user_config:
        config_path = user_config_path
```

**为什么可疑** `cmd_chat` 在 kwargs 里认真地传了它(`hermes_cli/main.py:2728`),读者会以为它生效。功能实际由环境变量在 **cli 模块导入时**读取,而 `hermes_cli/main.py:2674` 和 `_apply_safe_mode`(10854)都在 `from cli import ...`(2709)之前设置,所以行为是对的。但 `python cli.py --ignore-user-config` 这条直跑路径**完全无效** —— Fire 会接受这个参数,然后什么都不做。

`hermes_cli/main.py:10850-10855 @ 863e313`

```python
def _apply_safe_mode(args) -> None:
    if not getattr(args, "safe_mode", False):
        return
    os.environ["HERMES_SAFE_MODE"] = "1"
    os.environ["HERMES_IGNORE_USER_CONFIG"] = "1"
    os.environ["HERMES_IGNORE_RULES"] = "1"
```

---

### 缺陷 9:`interrupt_debug.log` 在 UI 线程上同步写、无上限、无开关(置信度:**高**,严重度低)

**锚点** `cli.py:15505-15511`(UI 线程)、`cli.py:14166`(另一处)。

```python
                            self._interrupt_queue.put(payload)
                            try:
                                _dbg = _hermes_home / "interrupt_debug.log"
                                with open(_dbg, "a", encoding="utf-8") as _f:
                                    _f.write(f"{time.strftime('%H:%M:%S')} ENTER: queued interrupt msg={str(payload)[:60]!r}, "
                                             f"agent_running={self._agent_running}\n")
                            except Exception:
                                pass
```

**为什么可疑** 三点:
1. 这是**同步文件 I/O,跑在 prompt_toolkit 事件循环线程上**。同一文件在 16206-16208 明确写着 "This handler runs in prompt_toolkit's event-loop thread. Any blocking call here (locks, sd.wait, disk I/O) freezes the entire UI." —— 自己定的规矩自己破了。
2. **无轮转、无大小上限、无配置开关**。全仓只有 `cli.py:14166` 和 `cli.py:15506` 两处写入,没有任何清理。
3. 它**不是**调试遗留:`hermes_cli/tips.py:305` 把它当功能宣传。

**触发条件** `busy_input_mode == "interrupt"` 且 `agent.redirect` 未接受时的每一次回车。

---

### 缺陷 10:`_agent_running` 在 `try` 之外置位,17506–17512 窗口内的异常会让状态永久卡住(置信度:**低**)

**锚点** `cli.py:17506-17513`。

```python
                    self._agent_running = True
                    self._interactive_turn = True
                    self._pet_turn_error = False
                    self._pet_reasoning = False
                    self._turn_summary_begin()
                    app.invalidate()  # Refresh status line

                    try:
```

**为什么可疑** 复位 `_agent_running = False` 在 17516 的 `finally` 里,而置位在 17506 —— 两者之间有 5 条语句不在保护范围内。若其中任何一条抛异常,会被 17589 的外层 `except Exception` 接住并 `continue`,而 `_agent_running` **永远停在 True**:UI 一直显示"agent 在跑",回车路由到 `_interrupt_queue`/steer,Ctrl-C 走 interrupt 分支 —— 全都是假的。

**触发条件** 窗口内唯一可能抛的是 `app.invalidate()`(17511),`_turn_summary_begin` 自身有 try(`cli.py:5573-5587`)。概率很低,故置信度低。修法很便宜:把 17506-17511 挪进 `try` 或改成 `try/finally` 包住整块。

---

### 缺陷 11:`finally` 里三个无保护的回调反注册挡在会话落盘之前(置信度:**低**)

**锚点** `cli.py:17862-17865`、`cli.py:965-968`(懒导入包装)。

```python
            # Unregister callbacks to avoid dangling references
            set_sudo_password_callback(None)
            set_approval_callback(None)
            set_secret_capture_callback(None)
```

**为什么可疑** 这三个是 `from tools.terminal_tool import ...` 的懒导入包装(965-968)。若导入失败,`finally` 在此中断,**后面的 `_persist_active_session_before_close()`(17870)、`end_session`(17875)、`on_session_end`(17904-17917)、`_run_cleanup()`(17918)、`_print_exit_summary()`(17919)、`_release_active_session()`(17920) 全部跳过**。atexit 能补前两者,补不了会话落盘。

**触发条件** `tools.terminal_tool` 在退出时不可导入。实践中它早已加载,故低置信。结构上它是这条链上唯一没保险的一环 —— 而且位置最差(挡在最重要的持久化前面)。

---

### 缺陷 12:退出中途丢消息与顺序反转(置信度:**低-中**,严重度低)

**(a) 丢消息** `_drain_interrupt_queue_to_pending_input()`(17549)把打断队列倒回 `_pending_input`,但如果同一时刻 `_should_exit` 已置位,`while not self._should_exit` 下一轮就退出,这些消息**从未被处理也从未被告知用户**。

**(b) 顺序反转** 同一轮里如果先有一条消息进了 `_interrupt_queue`(`interrupt` 模式 + redirect 失败),后有一条 slash 命令进了 `_pending_input`(15531-15532 的 `else` 分支),轮末排水会把前者**追加到后者之后**:

`cli.py:10719-10725 @ 863e313`

```python
        try:
            while not self._interrupt_queue.empty():
                stray = self._interrupt_queue.get_nowait()
                if stray:
                    self._pending_input.put(stray)
        except Exception:
            pass  # Non-fatal — never break the main loop
```

时间上 A 先于 B,重放顺序变成 B、A。

---

### 观察(非缺陷,但会误导读者)

- **`if not self._agent_running:`(`cli.py:17384`)在出厂代码里恒为真。** `_agent_running` 只在 `cli.py:4632 / 15164 / 17506 / 17516` 被赋值,后两处与 17384 同线程且互斥(`queue.Empty` 分支不可能在 `chat()` 内部执行)。这个卫语句给读者的暗示("这段可能在 agent 忙时跑")与事实相反。只有 wrapper CLI 从别的线程改这个标志时它才有意义。
- **`cli_ref = self` 出现两次**,`cli.py:16368` 和 `cli.py:17083`,第二次是完全冗余的重复赋值。更要紧的是:大量 `@kb.add` 处理器在 `cli.py:15579` / `15585-15595` / `15932` 等处引用 `cli_ref`,而这些**行号都在 16368 之前** —— 靠闭包延迟求值才没炸。任何人把 `cli_ref = self` 往下挪或把某个处理器改成立即执行,就会 `NameError`。

---

## 4. 与文档/注释的出入

### 冲突 1(▲ 代码为准):"POSIX 上 prompt_toolkit 的 SIGINT 处理器 works as expected"

**注释** `cli.py:17712-17713 @ 863e313`

```python
            # POSIX: leave the default SIGINT handler alone. prompt_toolkit
            # installs its own handler there and it works as expected.
```

**代码** pt 确实装了处理器,但它把 SIGINT 转成 `Keys.SIGINT` 按键,而 `cli.py` 的 39 处 `kb.add` **从不绑定 `Keys.SIGINT`**,落到 pt 的默认空实现(`prompt_toolkit/key_binding/bindings/basic.py:135-146`)。

**定案** 注释成立的**只有键盘 Ctrl-C** —— 而键盘 Ctrl-C 在 raw mode 下压根不产生 SIGINT,走的是 `c-c` 绑定,与 pt 的 SIGINT 处理器无关。对**真正的 OS SIGINT**(`kill -INT`、进程组信号),行为是**静默丢弃**。注释把"Ctrl-C 能用"错误归因给了 SIGINT 处理器。

### 冲突 2(▲ 代码为准):`_suppress_closed_loop_errors` 的注释描述了一个从未发生的安装

**注释** `cli.py:17728-17730 @ 863e313`

```python
        # Install a custom asyncio exception handler that suppresses the
        # "Event loop is closed" RuntimeError from httpx transport cleanup
        # and the "0 is not registered" KeyError from broken stdin (#6393).
```

**代码** 见缺陷 2:`get_running_loop()` 必抛 `RuntimeError`,且 pt 会覆盖。注释描述的是意图,不是行为。`cli.py:17788` 的 "Set the custom handler on prompt_toolkit's event loop" 尤其误导 —— 这个时刻 pt 的事件循环还不存在。

### 冲突 3(▲ 代码为准):`atexit.register(_run_cleanup)` 的注释说"只给单查询用"

**注释** `cli.py:18240 @ 863e313`

```python
    # Register cleanup for single-query mode (interactive mode registers in run())
```

**代码** 这行 `atexit.register` 是**无条件**的(18241),交互模式同样注册。所以 `_run_cleanup` 在交互模式下被 atexit 注册**两次**(18241 + 17607)。功能上无害(`_cleanup_done` 幂等),但注释描述的分工不成立。

### 冲突 4(▲ 代码为准):`handle_enter` 的 docstring 漏了两个 modal 分支

**注释** `cli.py:15260-15268 @ 863e313` 列了 sudo / approval / clarify-freetext / clarify-choice / agent-running / agent-idle 六种路由。

**代码** 实际有八个分支:多出 `_secret_state`(15279)和 `_slash_confirm_state`(15293)、`_model_picker_state`(15307)。且 docstring 里的 "Commands (starting with /) always go to _pending_input" 有三个例外(`/model` / `/steer` / `/background` 内联执行,15389/15410/15428)。

### 冲突 5(▲ 代码为准):测试 docstring 引用了不存在的方法名

**注释** `tests/hermes_cli/test_suppress_eio_on_interrupt.py:28-29 @ 863e313`

```python
    The real function is defined as a closure inside
    ``CLI._run_interactive``; we reconstruct an equivalent here so the
```

**代码** `grep -c "_run_interactive" cli.py` = 0。真实位置是 `HermesCLI.run`(`cli.py:14980`)里的闭包(`cli.py:17735`)。

### 冲突 6(◇ 表述过宽):tips 说"每一次中断都会记日志"

**文档** `hermes_cli/tips.py:305 @ 863e313`

```python
    "Every interrupt during an agent run is logged to ~/.hermes/interrupt_debug.log with timestamps.",
```

**代码** `cli.py:15506` 的写入只发生在 `busy_input_mode == "interrupt"` **且** `agent.redirect` 未接受时。`steer` / `queue` 模式、Ctrl-C 触发的 `request_hard_interrupt`(15993)都不写这个文件。

### 冲突 7(◇ 表述过宽):"keeps working in THIS session"

见缺陷 4。`cli.py:18477-18479` 的注释在 session_id 层面成立,在**模型上下文**层面不成立。

---

## 5. 移交

### 5.1 本段的净结论

1. **`run()` 不是循环,是装配器。** 2950 行里 0 个循环、57 个 try、39 个按键绑定、9 个线程。真正的循环在 `spinner_loop`(17357)和 `process_loop`(17377)两个 daemon 线程里,主线程被 `app.run()`(17804)占住。这个"UI 线程 / 工作线程 + 双队列"的形状是**中断能力本身的前提**,不是可选的架构风格。
2. **Ctrl-C 有三条路径**:键盘 `c-c` 绑定(raw mode,不产 SIGINT)、OS SIGINT(被 pt 转成无绑定的 `Keys.SIGINT`,**静默丢弃**)、清理窗口内的 Ctrl-C(ISIG 已恢复 → 打到 `_signal_handler_q` → 打断 teardown)。前提里说的"两条"少数了一条,而漏掉的那条正是坏掉的那条。
3. **`cli.py:main()` 不是进程入口,是被 kwargs 调用的库函数。** 入口是 `hermes_cli.main:main`(`pyproject.toml:359`)→ `cmd_chat` → `cli_main(**kwargs)`(`hermes_cli/main.py:2735`)。`fire.Fire` 只服务 `python cli.py`。
4. **"清理恰好一次"双向都假**:全局锁保证**至多**一次;锁先置位所以中途异常会永久停在半次;三条 `os._exit` 路径 + 一条 `execvp` 路径完全绕过。

### 5.2 值得写进 R12 蓝图的设计原则(与本仓解耦)

- **turn 必须跑在非 UI 线程。** 否则用户无法在 turn 进行中发出任何指令(包括"停")。这条决定了后面所有跨线程状态同步的复杂度,但它不可协商。
- **"忙时改路由"必须配"闲时无条件排水"。** `_drain_interrupt_queue_to_pending_input` 的教训:排水不能挂在某条成功路径上,必须挂在 `finally`。
- **状态标志的置位与复位必须同处一个 try/finally。** `_agent_running` 差一点就做到了(复位是 `finally` 第一句,很好),但置位在 try 外面(缺陷 10)。
- **跨线程问答的取消必须双向放行**:往队列推终止值(放行阻塞方)+ 清状态(放行 UI 方)。只做一边就是死锁或幽灵面板。
- **信号处理器里不要抛异常,要投递消息。** `call_soon_threadsafe(app.exit)` 优于 `raise KeyboardInterrupt()`(17664-17688 的完整论证)。
- **信号处理器里的日志必须裸 try 包住**(CPython `logging` 非重入,`Logger._cache` 会抛 `KeyError`)。
- **清理步骤按"用户可感知度"排序**,不按依赖排序。终端复位第一。
- **退出兜底要分层**:清理开始时武装(紧),shutdown 信号到达时武装(松,2×),两者不冲突。用 daemon 线程 + `os._exit(0)`,因为 daemon 线程在 `Py_FinalizeEx` 期间仍然在跑。
- **用探针代替版本嗅探**(macOS kqueue 探测,17765-17783)。
- **"限流不是失败"**:自动化调度必须把"暂时不可用"和"任务本身坏了"用不同退出码区分(18493-18518)。
- **裸 `except Exception: pass` 是启动期的合理默认,但它会藏 bug。** 本段 39 处这样的写法,藏住了缺陷 2 这种"整块功能从未生效"。配套要求:凡是这样写的地方,功能本身必须有一个**独立于该代码路径**的验证手段。

### 5.3 覆盖度与测试空洞(给后续轮次)

- **`HermesCLI.run()` 的 2950 行没有任何测试真正执行过。** `grep -rn "cli\.run()"` 在 `tests/` 下零命中;100 个测试文件提到 `HermesCLI`,全部走的是"stub 掉 prompt_toolkit + 单独调某个方法"的路子。相关测试自己也承认:`tests/cli/test_cli_interrupt_drain_regression.py:24-27` 写着 "The integration into `process_loop` itself is not threaded here (it requires a real prompt_toolkit app)"。
- **`cli.main()` 同样零集成测试**(`grep "from cli import main"` 在 `tests/` 下零命中)。
- 因此本段的所有结论都建立在**静态阅读 + pt/asyncio 源码交叉验证 + 4 个单元测试文件(18 项全绿)**之上,而不是端到端行为观测。要把缺陷 1/6/7 从"中"提到"高",需要一个能在无头环境里驱动真实 pt Application 的测试夹具(pt 提供 `create_pipe_input()` + `DummyOutput()`,技术上可行)——**这是给下一轮的具体建议**。

### 5.4 留给相邻段的接口点

- `chat()`(13708–14400 区间)与本段的契约:`_last_turn_interrupted` 由 `chat()` 在 14333 写、由本段在 17539 和 `_maybe_continue_goal_after_turn`(10791)读;`_interrupt_queue` 由本段生产、由 `chat()` 消费、由本段兜底排水。
- `process_command()` 与本段的契约:返回 `False` 表示"退出会话"(17468、15390);可通过 `_pending_agent_seed` 让一次 slash 之后直接接一个 agent turn(17485-17488)。
- `_run_cleanup` / `_arm_exit_watchdog` / `_reset_terminal_input_modes_on_exit`(989–1400 区间)是本段 teardown 的被调方,归属另一段精读。
- `hermes_cli/main.py` 的 `cmd_chat`(2528–2738)是本段 `main()` 的唯一实际调用方,归属 r8a 配置面的邻接内容。
