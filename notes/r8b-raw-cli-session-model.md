# r8b-raw-cli-session-model —— cli.py 7300-9835(会话恢复/配置展示/模型运行时)

> 底稿。所有断言紧跟 `路径:行号 @ 863e313` 与代码原文块。研究对象 `/home/user/hermes-agent`
> 固定在 `863e31318553cda8ad61df681d08175364d4164b`,只读。
> 本段负责 `cli.py` 第 7300–9835 行,必要时向外追证据(`tools/registry.py`、
> `agent/agent_runtime_helpers.py`、`hermes_cli/cli_commands_mixin.py`、`run_agent.py` 等)。

---

## 0. 自验记录

### 0.1 行号自验

分两轮验证,全部用脚本对着源文件跑,不靠记忆。

**第一轮(写作前,预定锚点)**:预挑 **65 条**逐条比对「该行实际文本是否包含我要引用的内容」。
**错 3 条**,均已修正:

| 我原以为 | 实际 | 内容 |
|---|---|---|
| `agent/agent_runtime_helpers.py:2762` | **2764** | `old_norm = (old_provider or "")...` |
| `run_agent.py:656` | **657** | `cwd=_launch_cwd_for_session(source),` |
| `hermes_cli/cli_commands_mixin.py:992` | **993** | `if target.isdigit():` |

三条都是「相邻注释行占位」造成的 +1~+2 偏移。

**第二轮(写完后,全量回扫)**:用正则从成稿里抽出**全部** `路径:行号 @ 863e313` 锚点
—— 共 **173 处引用 / 144 个唯一锚点** —— 逐个验证文件存在、行号在范围内,并打印实际内容人工核对。
**行号越界 0 处**;但**内容比对又发现 5 条语义错位**(行号合法但指错了地方),已全部修正:

| 我原写 | 实际 | 内容 |
|---|---|---|
| `agent/agent_runtime_helpers.py:1720-1722` | **1709-1712** | `agent._fallback_activated = False` 等三行重置 |
| `agent/agent_runtime_helpers.py:2716-2717` | **2714-2715** | `agent._cached_system_prompt = None` |
| `agent/agent_runtime_helpers.py:2738` | **2737** | `"reasoning_config": dict(...)` |
| `cli.py:16582-16583` | **16583-16588** | slash-confirm 倒计时渲染 |
| `hermes_state.py:5812-5814` | **5830-5831** | `order_by_last_active` 排序语义 |

**第三轮(代码块逐字回比)**:对成稿里**每一个「代码围栏 + 紧跟锚点」对**(共 **48 个**),
按锚点行号从源文件切片,与围栏内容**逐行比对**。发现 **4 处引文截断**(锚点标了 N 行、
围栏里只抄了不到 N 行),已全部补全:

| 锚点 | 问题 |
|---|---|
| `cli.py:9455-9466` → 改为 **9458-9466** | 锚点比引文多算了 3 行 |
| `cli.py:3213-3215` → 改为 **3213-3216** | 引文在句中截断 |
| `cli.py:3073-3074` → 改为 **3073-3075** | 引文在句中截断 |
| `cli.py:7287` | 只抄了半行,已补全 |

**总计:验证 144 个唯一锚点 + 48 个代码块。发现并修正 12 处问题
(3 条行号偏移 + 5 条语义错位 + 4 处引文截断)。最终重跑:行号越界 0、代码块不匹配 0。**

正文中所有代码原文块由脚本从源文件按行号切片导出后原样粘贴,未手工重排缩进。

### 0.2 实机自验(在 `/home/user/hermes-venv` 下真实执行)

1. **复现 `_show_tool_availability_warnings` 的 `KeyError`**(见 §2.2 / 缺陷 #1):

```
unavailable count: 12
keys of first entry: ['env_vars', 'name', 'tools']
sample: {'name': 'browser-cdp', 'env_vars': [], 'tools': ['browser_cdp', 'browser_dialog']}
KeyError reproduced: 'missing_vars'
```

2. **复现 `_prompt_text_input_modal` 在主线程上的自锁**(见 §2.5 / 缺陷 #2)。用桩对象绑定
   `HermesCLI._prompt_text_input_modal`,`timeout=3`:

```
MAIN-THREAD  result=None elapsed=3.0s state_after=None restored=True
WORKER-THREAD(带活 event loop, 外部应答) result='once' restored=True state=None
```

即:主线程调用 = 阻塞满 timeout 后返回 `None`;工作线程调用 = 正常应答。

3. 确认仓库根**不存在** `cli-config.yaml`(`ls: cannot access 'cli-config.yaml': No such file or directory`),
   这是 §2.3 判定 `show_config` 的 `Config File` 行失真的前提之一。

### 0.3 三条前提的结论(先给结论,细节见 §2)

| 前提(任务书给出) | 判定 | 一句话 |
|---|---|---|
| 1. `show_config` 只是漂亮地打印合并后的配置 | **假** | 它**一个 loader 都不读**:全部来自 `self.*` 活属性 + `os.getenv`,只打印一个它从不读取内容的**配置文件路径**;并且该路径的选择逻辑是 `load_cli_config()` 的**残缺副本**(漏掉 `HERMES_IGNORE_USER_CONFIG` 分支),`Timeout` 行的兜底值 `60` 与 terminal tool 真实默认值 `180` 不符 |
| 2. `_snapshot_model_runtime` 快照模型状态以便 `/model` 切换后复原 | **半真** | 它快照 CLI 侧 8 个字段 + `agent._primary_runtime` 的深拷贝;**漏掉** `agent._fallback_chain` / `_fallback_model`(会被 `switch_model` 永久裁剪)、`reasoning_config`(首次切换时 `_primary_runtime` 里根本没这个 key),并且复原时**强行清零** `agent._rate_limited_until` |
| 3. `_restore_session_cwd` 恢复目录 | **真,但失败姿态有洞** | 目录消失时降级为一行 dim 提示,不崩溃 —— 这条成立;但「已在该目录」的早退路径**不会**同步 `TERMINAL_CWD`,且 `/new` 创建的会话行**根本不写 `cwd`**,导致这些会话恢复时永远无目录可恢复 |

---

## 1. 段内地图

7300–9835 是 `HermesCLI` 类体的一段连续方法区。按定义行列出(行号已程序化核对):

| 行号 | 方法 | 没有它会坏掉什么 |
|---|---|---|
| 7284 | `_restore_session_cwd` | resume 后 terminal / code-exec / 相对路径落在错误仓库 |
| 7337 | `_restore_session_yolo` | 新进程里 `tools.approval._session_yolo` 为空集,用户的 bypass 静默失效 |
| 7377 | `_render_resume_history_panel_lines` | 终端 resize 时 resume 面板无法按新宽度重放 |
| 7394 | `_try_attach_clipboard_image` | Alt+V 粘贴图片 |
| 7414 | `_resolve_checkpoint_ref` | `/checkpoint` 的编号↔hash 解析 |
| 7431 | `_write_osc52_clipboard` | tmux/screen 下复制被多路复用器吞掉 |
| 7458 | `_recover_terminal_input_modes` | 鼠标上报泄漏后终端输入模式漂移无法自愈 |
| 7491 | `_preprocess_images_with_vision` | 非视觉模型无法处理附图 |
| **7557** | **`_show_tool_availability_warnings`** | 启动时提示「哪些工具因缺 key 被禁用」——**实测已死**,见 §2.2 |
| 7579 | `_show_status` | 启动状态行(模型/工具数/provider) |
| 7623 | `_show_session_status` | `/status` 的会话摘要 |
| 7676 / 7685 | `_fast_command_available` / `_command_available` | `/help` 里隐藏当前模型不支持的 `/fast` |
| 7690 | `show_help` | `/help` |
| 7750 | `show_tools` | `/tools`(刻意 `skip_tool_search_assembly=True` 列全量目录) |
| 7797 | `show_toolsets` | `/toolsets` |
| **7829** | **`show_config`** | `/config`,见 §2.3 |
| 7887 | `_list_recent_sessions` | `/resume`/`/sessions` 的候选列表来源(唯一口径) |
| 7906 | `_show_recent_sessions` | 渲染候选表 + 提示如何选 |
| 7936 | `show_history` | `/history` |
| 8019 | `_notify_session_boundary` | 插件 `on_session_finalize` / `on_session_reset` 钩子 |
| 8044 | `_discard_session_if_empty` | 空会话行堆积污染 `/resume` |
| 8073 | `_launch_session_boundary_memory_flush` | `/new` 时 context engine 的同步边界 + provider 抽取的异步交接 |
| 8118 | `new_session` | `/new` 全量轮转,见 §2.7 的 `CLI_CONFIG` 陈旧问题 |
| **8324** | **`_consume_pending_resume_selection`** | 裸 `/resume` 后直接敲数字,见 §2.4 |
| 8363 | `save_conversation` | `/save` 快照导出 |
| 8398 | `retry_last` | `/retry` |
| 8430 | `undo_last` | `/undo N`(内存截断 + DB 软删 + memory provider `rewound=True`) |
| 8556 | `_undo_content_to_text` | content-part 列表拍平成文本 |
| 8570 | `_prefill_input_buffer` | undo 后把消息回填到 composer |
| 8584 | `_run_curses_picker` | curses 选择器的线程/终端所有权保护 |
| 8614 | `_prompt_text_input` | 裸 `input()` 的线程保护版 |
| **8669** | **`_prompt_text_input_modal`** | 走 prompt_toolkit composer 的模态确认,见 §2.5 |
| 8793 | `_submit_slash_confirm_response` | 按键侧提交答案 |
| 8802 | `_normalize_slash_confirm_choice` | `1/y/ok/…` → `once/always/cancel` |
| 8836 | `_get_slash_confirm_display_fragments` | 模态面板渲染(自适应宽度 + detail 截断) |
| 8916 | `_open_model_picker` | `/model` 无参时的两级选择器 |
| 8931 | `_confirm_expensive_model_switch` | 贵模型二次确认 |
| 8963 | `_confirm_and_apply_model_switch_result` | picker 路径的「确认 + 应用」组合 |
| 8976 | `_close_model_picker` | 关闭并回填 composer 草稿 |
| **8981** | **`_snapshot_model_runtime`** | `--once` 的一回合快照,见 §2.6 |
| 8998 | `_restore_model_runtime_snapshot` | 一回合复原 |
| 9042 | `_compute_model_picker_viewport` | 选择器滚动视窗(纯函数,可单测) |
| 9070 | `_clear_persisted_context_for_model_switch` | 换 owner 时清掉全局 `model.context_length` 钉子 |
| 9092 | `_apply_model_switch_result` | picker 路径的落地(与 9462–9584 高度重复,见缺陷 #8) |
| 9235 | `_handle_model_picker_selection` | picker 两级 stage 机 |
| 9309 | `_handle_model_switch` | `/model` 主入口 |
| 9586 | `_handle_codex_runtime` | `/codex-runtime` |
| **9626** | **`_should_handle_model_command_inline`** | `/model` 走 UI 线程,见 §2.7 |
| 9638 / 9662 | `_should_handle_steer_command_inline` / `_should_handle_background_command_inline` | 让 `/steer`、`/background` 在 agent 跑着时不被队列饿死 |
| 9693 / 9699 | `_output_console` / `_console_print` | TUI 活着时改走 `ChatConsole` |
| 9703 | `handle_bang_shell` | `!cmd` 零 token 旁路 |
| 9761 | `_resolve_personality_prompt` | personality 值 str/dict 兼容 |
| 9778 | `_show_gateway_status` | `/gateway-status` |
| 9835 | `process_command` | 斜杠命令总分派(本段末尾开始) |

**这一段的共同主题**:它是「**会话身份 / 显示 / 模型运行时**」三件事的 CLI 侧胶水层 ——
把持久化在 SQLite 会话行里的东西(cwd、yolo)搬回进程状态,把进程状态渲染给人看,
把 `/model` 的一次切换正确地施加到「CLI 属性 + 活 agent + config.yaml」三处。
下面发现的绝大多数问题,都出在**同一份状态被两处独立地重新推导**。

---

## 2. 逐机制精读

### 2.1 `_restore_session_cwd`(7284)—— 前提 3

#### 它解决什么

一个 CLI 会话在 `~/proj-a` 启动。用户退出、`cd ~/proj-b`、再 `hermes --resume <id>`。
如果不做任何事,进程 cwd 是 `proj-b`,而 terminal 工具的 `TERMINAL_CWD` 也是 `proj-b`
(见 §2.3 的 config bridge:local backend 在 import 期就把 `TERMINAL_CWD` 强制设为 `os.getcwd()`)。
于是「恢复了会话,但每条命令跑在另一个仓库里」。这就是 `#38562`。

#### 实现与失败姿态

```
        recorded = (session_meta or {}).get("cwd")
        if not recorded:
            return
        recorded = os.path.expanduser(str(recorded))
        try:
            current = os.getcwd()
        except OSError:
            current = None
        if current and os.path.realpath(recorded) == os.path.realpath(current):
            return  # Already where the session lived — nothing to announce.

        if not os.path.isdir(recorded):
            msg = f"⚠ Session's working directory is gone: {recorded} — staying in {current or '.'}"
            if quiet:
                print(msg, file=sys.stderr)
            else:
                self._console_print(f"[dim]{_escape(msg)}[/dim]")
            return
```
`cli.py:7299-7316 @ 863e313`

```
        try:
            os.chdir(recorded)
        except OSError as e:
            msg = f"⚠ Could not enter session's working directory {recorded}: {e}"
            if quiet:
                print(msg, file=sys.stderr)
            else:
                self._console_print(f"[dim]{_escape(msg)}[/dim]")
            return

        # Retarget the terminal/code-exec tools to match the process cwd.
        os.environ["TERMINAL_CWD"] = recorded

        msg = f"↻ Working directory: {recorded}"
        if quiet:
            print(msg, file=sys.stderr)
        else:
            self._console_print(f"[dim]{_escape(msg)}[/dim]")
```
`cli.py:7318-7335 @ 863e313`

**失败姿态结论(回答前提 3)**:记录的目录不存在 → 打印一行 dim 提示、**留在当前目录**、
**不抛异常**。`os.chdir` 本身失败(权限、竞态删除)同样降级为提示。这两条都符合注释承诺
(`cli.py:7294-7298 @ 863e313` 的 docstring:"A missing directory degrades to a single dim warning rather than a crash — repos get moved and deleted")。**前提 3 的这一半是真的。**

但**降级路径没有回填 `TERMINAL_CWD`**:目录消失时函数直接 `return`,`TERMINAL_CWD` 保持
import 期由 config bridge 写入的值。对 local backend 这恰好等于 `os.getcwd()`,无害;
对**非 local backend** 就不一定(见缺陷 #6)。

#### 三条调用路径

```
        self._restore_session_cwd(session_meta)
```
`hermes_cli/cli_commands_mixin.py:1130 @ 863e313`(会话中 `/resume`,`#38562` 补的就是这条)

另外两条是启动期 resume:`hermes_cli/cli_agent_setup_mixin.py:431 @ 863e313`
(`quiet=_quiet_mode`)与 `hermes_cli/cli_agent_setup_mixin.py:643 @ 863e313`。
`quiet` 分支走 `print(..., file=sys.stderr)`,是为了非交互/管道场景不污染 stdout。

#### 写入端:谁往会话行里写 `cwd`

```
    if source != "cli":
        return None
    backend = (os.environ.get("TERMINAL_ENV") or "local").strip().lower()
    if backend and backend != "local":
        return None
    try:
        return os.getcwd()
    except OSError:
        # cwd was unlinked out from under us — nothing meaningful to record.
        return None
```
`run_agent.py:81-90 @ 863e313`

```
            self._session_db.create_session(
                session_id=self.session_id,
                source=source,
                model=self.model,
                model_config=_init_model_config,
                system_prompt=self._cached_system_prompt,
                user_id=None,
                parent_session_id=self._parent_session_id,
                cwd=_launch_cwd_for_session(source),
                profile_name=_profile_for_session,
            )
            self._session_db_created = True
```
`run_agent.py:649-660 @ 863e313`

写入端**已经**做了 backend 守卫:非 local 后端不记录 cwd。读取端 `_restore_session_cwd`
**没有**对称守卫 —— 这是缺陷 #6 的根。

#### `/new` 创建的会话没有 cwd

```
            if self._session_db:
                try:
                    self.agent._session_db_created = False
                    self._session_db.create_session(
                        session_id=self.session_id,
                        source=os.environ.get("HERMES_SESSION_SOURCE", "cli"),
                        model=self.model,
                        model_config={
                            "max_iterations": self.max_turns,
                            "reasoning_config": self.reasoning_config,
                        },
                    )
                    self.agent._session_db_created = True
                except Exception:
                    pass
```
`cli.py:8248-8262 @ 863e313`

这里 `create_session(...)` **不传 `cwd`**,并且紧接着把 `_session_db_created` 置 `True`。
而 agent 侧唯一会补 `cwd` 的入口 `run_agent.py:_ensure_db_session` 的第一件事是:

> `if self._session_db_created or not self._session_db: return`
> `run_agent.py:625 @ 863e313`

所以 `/new` 之后的会话行 `cwd` 列**永远为 NULL**,后续 `--resume` 时
`_restore_session_cwd` 在第一行就 `return`。同样问题在 `/branch`:
`hermes_cli/cli_commands_mixin.py:1233 @ 863e313` 的 `create_session(...)` 也不传 `cwd`
(但它不置 `_session_db_created`,所以理论上下一轮 `_ensure_db_session` 有机会补 —— 前提是
`SessionDB.create_session` 的 ON CONFLICT 用 `COALESCE` 回填,`hermes_state.py:3010 @ 863e313`
确实是 `cwd = COALESCE(sessions.cwd, excluded.cwd)`)。

→ **缺陷 #5**。

---

### 2.2 `_show_tool_availability_warnings`(7557)—— 整块是死代码

#### 场景

用户第一次装 Hermes,没配 `EXA_API_KEY`。期望:启动横幅下面出现一段
「⚠️ Some tools disabled (missing API keys): • web (EXA_API_KEY)」。实际:**什么都不出现**。

#### 代码

```
        try:
            from model_tools import check_tool_availability
            
            available, unavailable = check_tool_availability()
            
            # Filter to only those missing API keys (not system deps)
            api_key_missing = [u for u in unavailable if u["missing_vars"]]
            
            if api_key_missing:
                self._console_print()
                self._console_print("[yellow]⚠️  Some tools disabled (missing API keys):[/]")
                for item in api_key_missing:
                    tools_str = ", ".join(item["tools"][:2])  # Show first 2 tools
                    if len(item["tools"]) > 2:
                        tools_str += f", +{len(item['tools'])-2} more"
                    self._console_print(f"   [dim]• {item['name']}[/] [dim italic]({', '.join(item['missing_vars'])})[/]")
                self._console_print("[dim]   Run 'hermes setup' to configure[/]")
        except Exception:
            pass  # Don't crash on import errors
```
`cli.py:7559-7577 @ 863e313`

数据源返回的 dict 里根本没有 `missing_vars` 这个 key:

```
                available.append(ts)
            else:
                unavailable.append({
                    "name": ts,
                    "env_vars": ts_entries[0].requires_env if ts_entries else [],
                    "tools": [entry.name for entry in ts_entries],
                })
        return available, unavailable
```
`tools/registry.py:900-907 @ 863e313`

`model_tools.check_tool_availability` 只是转发:

> `    return registry.check_tool_availability(quiet=quiet)`
> `model_tools.py:1569 @ 863e313`

于是 `u["missing_vars"]` 在**第一个元素**上就抛 `KeyError`,被 7576 行的裸
`except Exception: pass` 吞掉。实测(§0.2)确认:`unavailable` 长度 12,keys 为
`['env_vars', 'name', 'tools']`,`KeyError reproduced: 'missing_vars'`。

**关键点:失败恰好只在「本该显示」时发生。** 若 `unavailable` 为空,列表推导不会取 key,
不报错也不显示 —— 视觉上与「一切正常」无法区分。这让这个 bug 极难被人肉发现。

对照组:doctor 走的是同一个 API,但**防御性地兼容两种 key**:

```
        
        for item in unavailable:
            env_vars = item.get("missing_vars") or item.get("env_vars") or []
            if env_vars:
                vars_str = ", ".join(env_vars)
                check_warn(item["name"], f"(missing {vars_str})")
            else:
                check_warn(item["name"], "(system dependency not met)")
```
`hermes_cli/doctor.py:2546-2553 @ 863e313`

说明 `missing_vars` 是某个历史版本的 key,`registry` 重构后改成了 `env_vars`,
doctor 跟上了,`cli.py` 没跟上。

另外 `tools_str`(7570-7573)**计算完从未被使用** —— 7574 行的 `_console_print` 打的是
`item['name']` 和 `item['missing_vars']`,和 `tools_str` 无关。即使 KeyError 被修好,
这三行仍是死代码。

→ **缺陷 #1**(整块不生效)与 **#1b**(`tools_str` 未使用)。

---

### 2.3 `show_config`(7829)—— 前提 1

#### 前提是假的:它不读任何 loader

```
        # Get terminal config from environment (which was set from cli-config.yaml)
        terminal_env = os.getenv("TERMINAL_ENV", "local")
        terminal_cwd = os.getenv("TERMINAL_CWD", os.getcwd())
        terminal_timeout = os.getenv("TERMINAL_TIMEOUT", "60")
        
        user_config_path = _hermes_home / 'config.yaml'
        project_config_path = Path(__file__).parent / 'cli-config.yaml'
        if user_config_path.exists():
            config_path = user_config_path
        else:
            config_path = project_config_path
        config_status = "(loaded)" if config_path.exists() else "(not found)"
```
`cli.py:7831-7842 @ 863e313`

```
        print("  -- Terminal --")
        print(f"  Environment:  {terminal_env}")
        if terminal_env == "ssh":
            ssh_host = os.getenv("TERMINAL_SSH_HOST", "not set")
            ssh_user = os.getenv("TERMINAL_SSH_USER", "not set")
            ssh_port = os.getenv("TERMINAL_SSH_PORT", "22")
            print(f"  SSH Target:   {ssh_user}@{ssh_host}:{ssh_port}")
        print(f"  Working Dir:  {terminal_cwd}")
        print(f"  Timeout:      {terminal_timeout}s")
        print()
        print("  -- Agent --")
        print(f"  Max Turns:  {self.max_turns}")
        print(f"  Toolsets:   {', '.join(self.enabled_toolsets) if self.enabled_toolsets else 'all'}")
        print(f"  Verbose:    {self.verbose}")
        print()
        print("  -- Session --")
        print(f"  Started:     {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Config File: {config_path} {config_status}")
        print()
```
`cli.py:7867-7885 @ 863e313`

**没有 `CLI_CONFIG`,没有 `load_config()`,没有读任何 YAML。** 数据只有两个来源:

- **活属性**:`self.model` / `self.base_url` / `self.api_key` / `self.max_turns` /
  `self.enabled_toolsets` / `self.verbose` / `self.session_start`;
- **环境变量**:`TERMINAL_*`(由 `load_cli_config()` 在 import 期从 config.yaml 桥接过去)。

`Config File:` 这一行**只是一个路径字符串**,函数从未打开它。所以「pretty-print 合并配置」
这个前提是假的:它更像「运行时快照 + 一条关于配置文件在哪的猜测」。

好的一面:**活属性正是 agent 实际用的东西**,所以 Model / Base URL / Toolsets / Max Turns
这几行是可信的。`api_key` 的展示还专门处理了 Azure Entra 的 callable 形态:

> ```
>         from agent.azure_identity_adapter import is_token_provider
>         if is_token_provider(self.api_key):
>             api_key_display = "Microsoft Entra ID"
> ```
> `cli.py:7846-7848 @ 863e313`

坏的一面有三处,全部集中在**它自己重新推导、而不是复用**的那部分。

#### (a) `Config File` 行漏掉 `--ignore-user-config`

真 loader:

```
    # Check user config first ({HERMES_HOME}/config.yaml)
    user_config_path = _hermes_home / 'config.yaml'
    project_config_path = Path(__file__).parent / 'cli-config.yaml'

    # --ignore-user-config: force-skip the user config.yaml (still honor project
    # config as a fallback so defaults stay sensible).
    ignore_user_config = os.environ.get("HERMES_IGNORE_USER_CONFIG") == "1"

    # Use user config if it exists, otherwise project config
    if user_config_path.exists() and not ignore_user_config:
        config_path = user_config_path
    else:
        config_path = project_config_path
```
`cli.py:426-438 @ 863e313`

`show_config`(7836-7841)是这段的**逐字副本减去 `ignore_user_config` 这一项**。
`hermes chat --ignore-user-config` 会设 `HERMES_IGNORE_USER_CONFIG=1`
(`hermes_cli/main.py:2675 @ 863e313`),此时进程**实际上完全没读**用户 config.yaml,
而 `/config` 仍然报告 `~/.hermes/config.yaml (loaded)`。→ **缺陷 #3**。

#### (b) `_hermes_home` 是 import 期常量,与写入端不同源

```
_hermes_home = get_hermes_home()
```
`cli.py:229 @ 863e313`

而同一进程里持久化模型选择的 `save_config_value` 用的是**实时** `get_hermes_home()`:

```
    # setting silently vanished every restart on any install whose
    # HERMES_HOME/config.yaml didn't exist yet.
    config_path = get_hermes_home() / 'config.yaml'
    
```
`cli.py:4126-4129 @ 863e313`

`get_hermes_home()` 会读一个 ContextVar 覆写(`hermes_constants.py:45-50 @ 863e313`
的 `get_hermes_home_override`),`save_config_value` 的注释明说这样做是
「so profile switches and test isolation land right」(`cli.py:4117 @ 863e313`)。
因此 profile 切换后:`/model x --global` 写进**新 home**,`/config` 报告**旧 home**。
→ **缺陷 #3b**。

#### (c) `Timeout` 行的兜底值与真实默认值不符

`TERMINAL_TIMEOUT` 只有在 config.yaml 显式写了 `terminal.timeout` 时才会被桥接
(`cli.py:662 @ 863e313` 的 `"timeout": "TERMINAL_TIMEOUT"` 映射,配合
`cli.py:701-714 @ 863e313` 的 `if config_key in terminal_config` 守卫);
而 `load_cli_config()` 的 `defaults["terminal"]`(`cli.py:447-459 @ 863e313`)
**根本没有 `timeout` 这个 key**。所以默认安装下 `TERMINAL_TIMEOUT` 是未设的,
`show_config` 显示 `Timeout: 60s`。terminal tool 的真实默认是 **180**:

```
        "host_cwd": host_cwd,
        "docker_mount_cwd_to_workspace": mount_docker_cwd,
        "timeout": _parse_env_var("TERMINAL_TIMEOUT", "180"),
        "lifetime_seconds": _parse_env_var("TERMINAL_LIFETIME_SECONDS", "300"),
```
`tools/terminal_tool.py:1545-1548 @ 863e313`

→ **缺陷 #4**。(同一份 60 的陈旧副本还出现在
`tools/terminal_tool.py:3356 @ 863e313` 的调试打印里。)

#### (d) 项目级 fallback 指向一个不存在的文件

`project_config_path = Path(__file__).parent / 'cli-config.yaml'`(7837 / 428)。
实测仓库根**没有** `cli-config.yaml`(§0.2 第 3 条)。因此在**没有**用户 config.yaml 的
全新安装上,`/config` 永远打印
`Config File: /path/to/hermes-agent/cli-config.yaml (not found)` —— 技术上诚实,
但对用户毫无指导意义(它不会告诉你「其实我在用内置 defaults」)。
7831 行注释「which was set from cli-config.yaml」也因此过时。→ **文档出入 D1**。

#### (e) 用裸 `print()`,不进入输出重放缓冲

`show_config` / `show_tools` / `show_toolsets` / `_show_gateway_status` 全部用裸 `print()`。
只有 `_cprint` 会记录输出历史:

```
    the line above it, and redraws the prompt cleanly.
    """
    _record_output_history(text)
```
`cli.py:3084-3087 @ 863e313`

而输出历史正是 Ctrl+L / `/redraw`(`cli.py:4855 @ 863e313`)和终端宽度变化
(`cli.py:4983 @ 863e313`)时用来重绘屏幕的:两处都调用 `_replay_output_history()`。
后果:按一次 Ctrl+L 或调整窗口宽度,`/config`、`/tools`、`/toolsets` 的输出**消失**,
而 `/help`、`/history`(走 `_cprint` / `_cli_visible_print`)的输出会被重放回来。
→ **缺陷 #7**。

---

### 2.4 `_consume_pending_resume_selection`(8324)

#### 场景

用户敲裸 `/resume`,看到一张 1–10 的会话表,然后**只敲一个 `3`**。若没有这个机制,
`3` 会被当成聊天内容发给模型(这就是 `#34584`)。

#### 代码

```
        pending = self._pending_resume_sessions
        if not pending:
            return False
        # One-shot: disarm now so a non-matching input can't leave the prompt
        # armed and hijack a later number the user meant as chat.
        self._pending_resume_sessions = None

        if not isinstance(text, str):
            return False
        stripped = text.strip()
        # Only a pure number selects; let "/resume 3", titles, or any other
        # text fall through to normal handling.
        if not stripped.isdigit():
            return False

        index = int(stripped)
        if index < 1 or index > len(pending):
            _cprint(f"  Resume index {index} is out of range.")
            _cprint("  Use /resume with no arguments to see available sessions.")
            return True

        self._handle_resume_command(f"/resume {index}")
        return True
```
`cli.py:8338-8360 @ 863e313`

设计上有三个值得学的点:

1. **一次性(one-shot)且提前解除武装**:8343 行在做任何判断**之前**就把状态清空。
   这样即使后面走了任何 `return False` 分支,状态也不会残留 —— 避免用户十分钟后
   敲一个 `2` 被当成陈旧选择。
2. **只接受纯数字**:`/resume 3`、标题、任何别的文本都 `return False` 交回正常路径。
3. **返回值区分「已消费」与「未消费」**:调用点据此决定是否 `continue`,
   见 `cli.py:17446-17452 @ 863e313`。

#### 一个真实的 TOCTOU:索引在两个不同的列表上解析

armed 时保存的是一份**快照**:

```
            if self._show_recent_sessions(reason="resume"):
                # Arm a one-shot pending-resume selection so the user can type
                # just the number (`3`) on the next line instead of having to
                # retype `/resume 3`. The list here must match the one shown by
                # _show_recent_sessions and used for index resolution below —
                # all three go through _list_recent_sessions(limit=10). See
                # #34584.
                self._pending_resume_sessions = self._list_recent_sessions(limit=10)
                return
```
`hermes_cli/cli_commands_mixin.py:971-979 @ 863e313`

但 8359 行把控制权交给 `_handle_resume_command(f"/resume {index}")` 之后,
后者**重新查询**一次:

```
        # Resolve numbered selection, title, or ID
        if target.isdigit():
            sessions = self._list_recent_sessions(limit=10)
            index = int(target)
            if index < 1 or index > len(sessions):
                _cprint(f"  Resume index {index} is out of range.")
                _cprint("  Use /resume with no arguments to see available sessions.")
                return
            selected = sessions[index - 1]
            target_id = selected["id"]
```
`hermes_cli/cli_commands_mixin.py:992-1001 @ 863e313`

即:**范围检查做了两次,分别对着两份可能不同的列表**;真正决定恢复哪个会话的是
**第二份**。缓解因素是默认排序不是「最近活跃」:

> `        order_by_last_active=bool(search),`
> `hermes_cli/session_listing.py:77 @ 863e313`

无搜索词时 `order_by_last_active=False`,`list_sessions_rich` 按
「original conversation start time」排 —— 见其 docstring:

```
        Pass ``order_by_last_active=True`` to sort by most-recent activity
        instead of original conversation start time. For compression chains,
```
`hermes_state.py:5830-5831 @ 863e313`

`started_at` 不变,所以**已有行的相对顺序稳定**;只有在 arm→选 之间**新建**一个 cli 会话
(并发的 gateway / kanban worker / 另一个终端)才会整体前移一格,让 `3` 指向另一个会话。
→ **缺陷 #9(置信度中低,但确实存在)**。

---

### 2.5 `_prompt_text_input` / `_prompt_text_input_modal`(8614 / 8669)

#### 为什么要有模态,而不是 `input()`

prompt_toolkit 的 `Application` 跑起来后**独占 stdin**。在这种状态下调用裸 `input()`:
终端里出现的提示行会跑到 TUI 上方、选项被后续重绘覆盖、回车可能被解释成 EOF 把整个 app 退掉。
docstring 把这段历史写得很清楚(`cli.py:8677-8684 @ 863e313`)。
Windows 上更糟:早期代码在 `win32` 直接跳过模态退回 `input()`,而斜杠命令是在
`process_loop` 守护线程上分派的,那个 `input()` 与 prompt_toolkit 的 stdin 所有权互锁 ——
`/reset` 直接冻住、Ctrl-C 被吞(`#33961`,`cli.py:8686-8699 @ 863e313`)。

**所以现在的设计契约是:模态的建立/拆除必须回到 app 的 event loop 上,答案通过队列跨线程回传。**

#### 线程判定与三条退路

```
        if not getattr(self, "_app", None):
            return self._prompt_text_input("Choice [1/2/3]: ")

        try:
            app_loop = self._app.loop
        except Exception:
            app_loop = None

        in_main_thread = threading.current_thread() is threading.main_thread()

        def _stdin_fallback() -> str | None:
            # On native Windows a raw input() from a non-main thread deadlocks
            # against prompt_toolkit's stdin ownership (#33961).  With an app
            # running we cannot safely prompt off the main thread, so cancel
            # cleanly (None) rather than hang the terminal.
            if sys.platform == "win32" and not in_main_thread:
                self._invalidate()
                return None
            return self._prompt_text_input("Choice [1/2/3]: ")

        if not in_main_thread and app_loop is None:
            return _stdin_fallback()
```
`cli.py:8709-8731 @ 863e313`

#### 核心:`_run_on_app_loop` 与轮询循环

```
        def _run_on_app_loop(fn) -> bool:
            if in_main_thread or app_loop is None:
                fn()
                return True
            ready = threading.Event()

            def _wrapped() -> None:
                try:
                    fn()
                finally:
                    ready.set()

            try:
                app_loop.call_soon_threadsafe(_wrapped)
            except Exception:
                return False
            return ready.wait(timeout=5)

        if not _run_on_app_loop(_setup_modal):
            return _stdin_fallback()

        _last_countdown_refresh = _time.monotonic()
        try:
            while True:
                try:
                    result = response_queue.get(timeout=1)
                    _run_on_app_loop(_teardown_modal)
                    return result
                except queue.Empty:
                    remaining = self._slash_confirm_deadline - _time.monotonic()
                    if remaining <= 0:
                        break
                    now = _time.monotonic()
                    if now - _last_countdown_refresh >= 5.0:
                        _last_countdown_refresh = now
                        self._invalidate()
        finally:
            if self._slash_confirm_state is not None:
                _run_on_app_loop(_teardown_modal)
        return None
```
`cli.py:8752-8791 @ 863e313`

**这里有一个致命的隐含前提:调用者不在主线程上。**
当 `in_main_thread is True` 时,`_run_on_app_loop` 退化成同步 `fn()`,然后
`while True: response_queue.get(timeout=1)` 就在**主线程**上阻塞。而主线程正是
prompt_toolkit 事件循环所在的线程(`app.run()` 在 `cli.py:17804 @ 863e313`,
外面包着 `with patch_stdout():`,`cli.py:17787 @ 863e313`)。
事件循环被占住 → 按键无法分派 → `_submit_slash_confirm_response` 永远没机会被调用 →
队列永远空 → 死等到 `timeout`(默认 120 s),返回 `None`。

§0.2 的实测复现了这一点:主线程调用、`timeout=3`,`elapsed=3.0s`、`result=None`;
同一函数在工作线程 + 活 event loop 下正常返回 `'once'`。

每 5 秒的 `self._invalidate()` 不是无用代码 —— 状态栏确实渲染倒计时:

```
            if cli_ref._slash_confirm_state:
                remaining = max(0, int(cli_ref._slash_confirm_deadline - time.monotonic()))
                return [
                    ('class:hint', '  type 1/2/3, or ↑/↓ to select, Enter to confirm'),
                    ('class:clarify-countdown', f'  ({remaining}s)'),
                ]
```
`cli.py:16583-16588 @ 863e313`

但在主线程自锁的情况下这个 invalidate 也无法生效(循环没让出)。

哪条路径会以主线程调用它?见 §2.7。→ **缺陷 #2**。

#### 次要:提交与超时之间的窄竞态

```
    def _submit_slash_confirm_response(self, value: str | None) -> None:
        state = self._slash_confirm_state
        if not state:
            return
        state["response_queue"].put(value)
        self._slash_confirm_state = None
        self._slash_confirm_deadline = 0
        self._invalidate()
```
`cli.py:8793-8800 @ 863e313`

提交端先 `put`、再把 `_slash_confirm_deadline` 清零。消费端在 `except queue.Empty:` 之后
才去读 `self._slash_confirm_deadline`。若 `get(timeout=1)` 刚好超时、提交在这两句之间发生,
消费端读到 `deadline == 0` → `remaining <= 0` → `break`。此时 `finally` 里
`self._slash_confirm_state` 已被提交端置 `None`,**`_teardown_modal` 被跳过**,
于是 `_restore_modal_input_snapshot()`(`cli.py:13629 @ 863e313`)不会执行 ——
用户在模态弹出前敲了一半的草稿**不会被还原**,同时函数返回 `None`(表现为「取消」)。
窗口只有两条字节码宽,概率极低,但它同时丢答案和丢草稿。→ **缺陷 #10(置信度低)**。

---

### 2.6 `_snapshot_model_runtime` / `_restore_model_runtime_snapshot`(8981 / 8998)—— 前提 2

#### 场景

`/model opus --once`:这一回合用贵模型,下一回合自动切回来。

#### 快照内容

```
    def _snapshot_model_runtime(self) -> dict:
        """Capture current CLI and agent model runtime for one-turn restore."""
        agent = getattr(self, "agent", None)
        return {
            "model": self.model,
            "provider": self.provider,
            "requested_provider": self.requested_provider,
            "_explicit_api_key": getattr(self, "_explicit_api_key", None),
            "_explicit_base_url": getattr(self, "_explicit_base_url", None),
            "api_key": self.api_key,
            "base_url": self.base_url,
            "api_mode": self.api_mode,
            "agent_primary_runtime": copy.deepcopy(
                getattr(agent, "_primary_runtime", None)
            ) if agent is not None else None,
        }
```
`cli.py:8981-8996 @ 863e313`

拍摄时机在**变更之前**,正确:

```
        if not self._confirm_expensive_model_switch(result):
            _cprint("  Model switch cancelled.")
            return

        # Apply to CLI state.
        # Update requested_provider so _ensure_runtime_credentials() doesn't
        # overwrite the switch on the next turn (it re-resolves from this).
        old_model = self.model
        _one_turn_restore_snapshot = self._snapshot_model_runtime() if one_turn else None
```
`cli.py:9458-9466 @ 863e313`

暂存与消费:

```
        if one_turn:
            self._pending_one_turn_model_restore = _one_turn_restore_snapshot
        else:
            self._pending_one_turn_model_restore = None
```
`cli.py:9528-9531 @ 863e313`

`cli.py:14040-14043 @ 863e313` 在发起 `run_conversation` 前把它取出并清空,
`cli.py:14072-14074 @ 863e313` 在 `finally:` 里 `self._restore_model_runtime_snapshot(...)` ——
放 `finally` 是对的:turn 抛异常也要还原,否则用户永久留在贵模型上。

#### 复原实现

```
    def _restore_model_runtime_snapshot(self, snapshot: dict | None) -> None:
        """Restore a model runtime captured before a one-turn override."""
        if not snapshot:
            return
        for key in (
            "model",
            "provider",
            "requested_provider",
            "_explicit_api_key",
            "_explicit_base_url",
            "api_key",
            "base_url",
            "api_mode",
        ):
            if key in snapshot:
                setattr(self, key, snapshot.get(key))

        agent = getattr(self, "agent", None)
        if agent is None:
            return

        primary = snapshot.get("agent_primary_runtime")
        if primary and hasattr(agent, "_restore_primary_runtime"):
            try:
                agent._primary_runtime = copy.deepcopy(primary)
                agent._fallback_activated = True
                agent._rate_limited_until = 0
                if agent._restore_primary_runtime():
                    return
            except Exception:
                logger.debug("CLI one-turn model restore via primary runtime failed", exc_info=True)

        if hasattr(agent, "switch_model"):
            try:
                agent.switch_model(
                    new_model=snapshot.get("model", ""),
                    new_provider=snapshot.get("provider", ""),
                    api_key=snapshot.get("api_key", ""),
                    base_url=snapshot.get("base_url", ""),
                    api_mode=snapshot.get("api_mode", ""),
                )
            except Exception as exc:
                logger.warning("CLI one-turn model restore failed: %s", exc)
```
`cli.py:8998-9041 @ 863e313`

**手法值得记录**:它复用了 fallback 机制的「回到主 runtime」通道 —— 把旧
`_primary_runtime` 塞回去,然后**伪造** `_fallback_activated = True`
(否则 `restore_primary_runtime` 第一句就 `if not agent._fallback_activated: ... return False`,
`agent/agent_runtime_helpers.py:1459-1469 @ 863e313`),再调 `_restore_primary_runtime()`。
好处是 client 重建、prompt cache 布局、compressor 参数等一整套都由现成代码处理。

#### 漏了什么(回答前提 2)

**(i) `agent._fallback_chain` / `_fallback_model` —— 会被 `switch_model` 永久裁剪,快照里没有。**

```
    old_norm = (old_provider or "").strip().lower()
    new_norm = (new_provider or "").strip().lower()
    fallback_chain = list(getattr(agent, "_fallback_chain", []) or [])
    if old_norm and new_norm and old_norm != new_norm:
        fallback_chain = [
            entry for entry in fallback_chain
            if (entry.get("provider") or "").strip().lower() not in {old_norm, new_norm}
        ]
    agent._fallback_chain = fallback_chain
    agent._fallback_model = fallback_chain[0] if fallback_chain else None
```
`agent/agent_runtime_helpers.py:2764-2773 @ 863e313`

`restore_primary_runtime` 只重置 `_fallback_activated` / `_fallback_index` / 退避计数:

```
        # ── Reset fallback chain for the new turn ──
        agent._fallback_activated = False
        agent._fallback_index = 0
        agent._rate_limit_backoff_count = 0  # reset exponential backoff counter
```
`agent/agent_runtime_helpers.py:1709-1712 @ 863e313`

注意注释写的是「Reset fallback **chain**」,但代码只动了三个标量,**没有重建 `_fallback_chain` 列表**。
所以 `/model <另一个 provider> --once` 之后:模型切回来了,但本会话的 fallback 链
被永久剥掉了旧、新两个 provider 的条目 —— 后续任何一次真实故障,可回退的目标变少甚至归零。
→ **缺陷 #11**。

**(ii) `reasoning_config` —— 首次 `--once` 切换时快照里根本没有这个 key。**

`switch_model` 会按新模型重解析:

```
    # ── Re-resolve reasoning_config from per-model override ──
    # The new model may have a different reasoning_effort override. Re-read
    # config so the override takes effect immediately on /model switch —
    # resolved through the shared chokepoint (per-model > global; YAML
    # boolean False = disabled).
    try:
        from hermes_constants import resolve_reasoning_config
        from hermes_cli.config import load_config as _sm_load_config

        _reasoning_cfg = _sm_load_config() or {}
        agent.reasoning_config = resolve_reasoning_config(_reasoning_cfg, agent.model)
        logger.info(
            "switch_model: reasoning_config resolved for %s: %s",
            agent.model, agent.reasoning_config,
        )
    except Exception as _reasoning_err:
        logger.debug("switch_model: could not re-resolve reasoning_config: %s", _reasoning_err)
```
`agent/agent_runtime_helpers.py:2696-2712 @ 863e313`

而复原端只在快照里**有**该 key 时才还原:

```
        # ── Restore reasoning_config if it was saved ──
        # switch_model saves reasoning_config in _primary_runtime. If the
        # snapshot predates that (older sessions), keep the current value.
        saved_reasoning = rt.get("reasoning_config")
        if saved_reasoning is not None:
            agent.reasoning_config = dict(saved_reasoning)
```
`agent/agent_runtime_helpers.py:1702-1707 @ 863e313`

关键:**`_primary_runtime` 有两个构造点,只有其中一个带 `reasoning_config`。**
agent 初始化那份不带:

```
    agent._primary_runtime = {
        "model": agent.model,
        "provider": agent.provider,
        "requested_provider": agent.requested_provider,
        "base_url": agent.base_url,
        "api_mode": agent.api_mode,
        "api_key": getattr(agent, "api_key", ""),
        "client_kwargs": dict(agent._client_kwargs),
        "use_prompt_caching": agent._use_prompt_caching,
        "use_native_cache_layout": agent._use_native_cache_layout,
        # Context engine state that _try_activate_fallback() overwrites.
        # Use getattr for model/base_url/api_key/provider since plugin
        # engines may not have these (they're ContextCompressor-specific).
        "compressor_model": getattr(_cc, "model", agent.model),
        "compressor_base_url": getattr(_cc, "base_url", agent.base_url),
        "compressor_api_key": getattr(_cc, "api_key", ""),
        "compressor_provider": getattr(_cc, "provider", agent.provider),
        "compressor_context_length": _cc.context_length,
        "compressor_threshold_tokens": _cc.threshold_tokens,
    }
```
`agent/agent_init.py:2777-2796 @ 863e313`

`switch_model` 那份带:

```
        "reasoning_config": dict(agent.reasoning_config) if getattr(agent, "reasoning_config", None) else None,
```
`agent/agent_runtime_helpers.py:2737 @ 863e313`

于是:**进程启动后第一条 `/model B --once`**,快照来自 agent_init 版本(无 key),
`switch_model` 把 `agent.reasoning_config` 改成 B 的配置,复原时 `rt.get("reasoning_config")`
返回 `None` → 保留当前值 → **模型 A 之后一直用着 B 的 reasoning 配置**。
且 CLI 侧的 `self.reasoning_config` 也不在 8981 的快照键列表里。→ **缺陷 #12**。

**(iii) 强行清零 `_rate_limited_until`。** 9024 行 `agent._rate_limited_until = 0` 是为了
绕过 `restore_primary_runtime` 的冷却门(`agent/agent_runtime_helpers.py:1471-1472 @ 863e313`:
`if getattr(agent, "_rate_limited_until", 0) > time.monotonic(): return False`)。
但如果这一回合里主 provider 真的被限流并设置了冷却,这次清零会把真实冷却抹掉,
下一回合立刻再撞一次限流。→ **缺陷 #13(置信度中)**。

**(iv) 部分失败留下不一致状态。** 若 `_restore_primary_runtime()` 返回 `False`
(例如凭据池的 reset-aware 门 `agent/agent_runtime_helpers.py:1512-1524 @ 863e313` 认为
主 provider 还在长时限流窗口内),代码**已经**改过 `_primary_runtime`、`_fallback_activated`、
`_rate_limited_until`,然后又落到 `switch_model(...)` 再改一遍。两条路径都执行过,
`_fallback_activated` 最终被 `switch_model` 重置为 `False`,基本自洽 —— 但这依赖
`switch_model` 成功;若它也抛异常,只 `logger.warning`,agent 停留在中间态。
→ 归入 #13。

**(v) 深拷贝的隐性依赖。** `copy.deepcopy(agent._primary_runtime)` 会拷到 `api_key`。
`api_key` 允许是 callable(Azure Entra bearer provider,`show_config` 7846-7848 就在判它)。
当前之所以安全,是因为 `azure.identity.get_bearer_token_provider` 返回的是普通函数,
而 `copy` 模块把 `FunctionType` 当原子对象原样返回。若将来某 provider 提供的是**可调用实例**,
deepcopy 会去克隆整个 credential 对象图(可能含锁/socket → `TypeError`),
而 `_snapshot_model_runtime` **没有 try/except**,异常会一路冒到 `_handle_model_switch`
之外。→ **缺陷 #14(置信度低,属于「设计脆弱点」而非现存 bug)**。

---

### 2.7 `_should_handle_model_command_inline`(9626)与它引爆的两个问题

#### 它做什么

```
    def _should_handle_model_command_inline(self, text: str, has_images: bool = False) -> bool:
        """Return True when /model should be handled immediately on the UI thread."""
        if not text or has_images or not _looks_like_slash_command(text):
            return False
        try:
            from hermes_cli.commands import resolve_command
            base = text.split(None, 1)[0].lower().lstrip('/')
            cmd = resolve_command(base)
            return bool(cmd and cmd.name == "model")
        except Exception:
            return False
```
`cli.py:9626-9636 @ 863e313`

调用点在 prompt_toolkit 的**按键绑定**里:

```
            if text or has_images:
                # Handle /model directly on the UI thread so interactive pickers
                # can safely use prompt_toolkit terminal handoff helpers.
                if self._should_handle_model_command_inline(text, has_images=has_images):
                    if not self.process_command(text):
                        self._should_exit = True
                        if event.app.is_running:
                            event.app.exit()
```
`cli.py:15386-15393 @ 863e313`

`process_command` 在 `cli.py:10039-10040 @ 863e313` 把 `model` 分派到 `_handle_model_switch`。

#### 与两个兄弟判定的关键差异

`_should_handle_steer_command_inline`(9638)和 `_should_handle_background_command_inline`(9662)
都额外要求 `if not getattr(self, "_agent_running", False): return False`
(`cli.py:9652 @ 863e313` / `cli.py:9683 @ 863e313`)—— 它们只在 agent 忙时才抢 UI 线程,
因为那正是队列会饿死它们的时刻。**`/model` 没有这个守卫:任何时候都走 UI 线程。**

#### 后果一:`/model <贵模型>` 会冻住 TUI 120 秒然后「取消」

`_handle_model_switch` 在直连路径上**同步**调用确认:

```
        if not self._confirm_expensive_model_switch(result):
            _cprint("  Model switch cancelled.")
            return
```
`cli.py:9458-9460 @ 863e313`

```
    def _confirm_expensive_model_switch(self, result) -> bool:
        """Ask for explicit confirmation before applying costly model switches."""
        if not getattr(result, "success", False):
            return True
        try:
            from hermes_cli.model_cost_guard import expensive_model_warning

            warning = expensive_model_warning(
                result.new_model,
                provider=result.target_provider,
                base_url=result.base_url or self.base_url or "",
                api_key=result.api_key or self.api_key or "",
                model_info=result.model_info,
            )
        except Exception:
            warning = None
        if warning is None:
            return True

        choices = [
            ("once", "Switch anyway", "Use this model for the current Hermes session."),
            ("cancel", "Cancel", "Keep the current model."),
        ]
        raw = self._prompt_text_input_modal(
            title="!!! Expensive Model Warning !!!",
            detail=warning.message,
            choices=choices,
            timeout=120,
        )
        choice = self._normalize_slash_confirm_choice(raw, choices)
        return choice == "once"
```
`cli.py:8931-8961 @ 863e313`

链路:按键绑定(主线程)→ `process_command` → `_handle_model_switch` →
`_confirm_expensive_model_switch` → `_prompt_text_input_modal`(§2.5 证明主线程会自锁)。
触发条件是 `expensive_model_warning` 返回非 `None`,即已知定价超过
`INPUT_COST_WARNING_THRESHOLD = Decimal("20")` 或 `OUTPUT_COST_WARNING_THRESHOLD = Decimal("100")`
(`hermes_cli/model_cost_guard.py:12-13 @ 863e313`,判定在
`hermes_cli/model_cost_guard.py:101-108 @ 863e313`)。

**反证:同一个确认函数在 picker 路径上被显式丢到后台线程。**

```
                # Capture before close — picker state is cleared on close.
                _picker_custom_provs = state.get("custom_provs")
                self._close_model_picker()
                if getattr(self, "_app", None):
                    threading.Thread(
                        target=self._confirm_and_apply_model_switch_result,
                        args=(result, persist_global, _picker_custom_provs),
                        daemon=True,
                    ).start()
                else:
                    self._confirm_and_apply_model_switch_result(
                        result, persist_global, custom_providers=_picker_custom_provs
                    )
                return
```
`cli.py:9293-9306 @ 863e313`

`if getattr(self, "_app", None): threading.Thread(...)` 就是「app 活着时**不能**在这条线程上确认」
的自证。直连路径(9458)缺同样的处理。→ **缺陷 #2**。

#### 后果二:`/model` 在 agent 跑着时也抢 UI 线程

`/model` 没有 `_agent_running` 守卫,意味着 agent 正在流式输出时敲 `/model x`,
切换会**立刻**打在 `self.agent` 上(`cli.py:9497-9503 @ 863e313` 的 `agent.switch_model`),
而 `run_conversation` 正在另一线程里用这个 agent。`switch_model` 会重建 client、清
`_transport_cache`、改 `agent.model` / `api_mode` / caching 标志、失效 system prompt:

```
    # ── Invalidate cached system prompt so it rebuilds next turn ──
    agent._cached_system_prompt = None
```
`agent/agent_runtime_helpers.py:2714-2715 @ 863e313`
本段代码没有任何针对「turn 进行中」的锁或延后。→ **缺陷 #15(置信度中,需跨段确认
`run_conversation` 是否另有保护)**。

#### 顺带:`new_session` 的「重置到 config 默认」读的是陈旧快照

```
        # /new is a full conversation boundary: session-scoped runtime
        # overrides (/model --session, /fast, one-turn restores) do not carry
        # forward.  Re-derive model/provider and service tier from config.yaml
        # so a session-only switch never leaks into the next session (#48055,
        # #23131).
        self._pending_one_turn_model_restore = None
        self.service_tier = _parse_service_tier_config(
            CLI_CONFIG["agent"].get("service_tier", "")
        )
        _model_config = CLI_CONFIG.get("model", {})
        _config_model = (
            (_model_config.get("default") or _model_config.get("model") or "")
            if isinstance(_model_config, dict)
            else (_model_config or "")
        )
        if _config_model and _config_model != getattr(self, "model", None):
```
`cli.py:8168-8183 @ 863e313`

注释说「Re-derive … **from config.yaml**」,代码读的是 `CLI_CONFIG` —— 一个在
`cli.py:792 @ 863e313`(`CLI_CONFIG = load_cli_config()`)于 import 期计算、
**全文件再无任何重新赋值**的模块级快照(全仓 `CLI_CONFIG` 引用见 §0 检索,只有一处赋值)。
而 `/model x --global` 通过 `save_config_value` 只写磁盘(`cli.py:4128 @ 863e313`),
不回写 `CLI_CONFIG`。

后果:同一进程内 `/model gpt5 --global` → `/new`,`/new` 会把模型「重置」回
**进程启动时**的 config 默认值,而不是刚刚持久化的 `gpt5`。
→ **缺陷 #16 + 文档出入 D2**。

好的一面:这段用 `try/except` + `logger.debug` 兜底(`cli.py:8226-8229 @ 863e313`),
注释写明「an unreachable config default must never block /new」—— 失败姿态是对的。

---

## 3. 可疑缺陷清单

> 每条:现象 / 锚点 / 为什么可疑 / 触发条件 / 置信度

---

**#1 — 启动时的「工具因缺 API key 被禁用」提示整块从不显示**

- **现象**:无论缺多少 key,`_show_tool_availability_warnings` 什么都不打印。
- **锚点**:`cli.py:7565 @ 863e313`(`u["missing_vars"]`);数据源
  `tools/registry.py:902-906 @ 863e313` 返回的 key 是 `env_vars`;
  吞异常在 `cli.py:7576-7577 @ 863e313`。
- **为什么可疑**:下标访问不存在的 key → `KeyError` → 被裸 `except Exception: pass` 吞掉。
  且**只在 `unavailable` 非空时**才抛,即恰好只在「本该提示」时失败,静默且无日志。
  同一 API 的另一个消费者 `hermes_cli/doctor.py:2548 @ 863e313` 写的是
  `item.get("missing_vars") or item.get("env_vars") or []`,说明 key 曾经改过名而 cli.py 未跟进。
- **触发条件**:任意存在不可用 toolset 的安装(实测默认环境下 `unavailable` 有 12 项)。
- **置信度**:**高**(§0.2 已实机复现 `KeyError`)。

**#1b — `tools_str` 计算后从未使用**

- **现象**:即使 #1 被修好,警告行也只会显示 toolset 名 + 环境变量名,**不会**显示
  「哪些工具受影响」——尽管代码算好了这个字符串。
- **锚点**:`cli.py:7570-7573 @ 863e313` 构造 `tools_str`,`cli.py:7574 @ 863e313`
  的输出串里没有它。
- **为什么可疑**:三行计算 + 一个 f-string 分支,结果被丢弃。要么是重构时漏改的输出串,
  要么是有意删除时留下的残骸;无论哪种,都说明这段代码从未被真正运行观察过(与 #1 互为佐证)。
- **触发条件**:恒定成立(静态)。
- **置信度**:高(纯静态可判)。

---

**#2 — `/model <贵模型>` 在 TUI 里冻结 120 秒后误报「Model switch cancelled」**

- **现象**:输入 `/model <定价超阈值的模型>`,界面卡住不响应任何按键约 2 分钟,
  然后打印 `  Model switch cancelled.`,模型没换。
- **锚点**:`cli.py:15389 @ 863e313`(按键绑定里直接 `process_command`)→
  `cli.py:10040 @ 863e313` → `cli.py:9458 @ 863e313` → `cli.py:8954 @ 863e313` →
  `cli.py:8753 @ 863e313`(`if in_main_thread or app_loop is None: fn()`)+
  `cli.py:8775-8787 @ 863e313`(主线程上阻塞轮询)。
- **为什么可疑**:模态的整套设计(`call_soon_threadsafe` + 队列 + `ready.wait`)只有在
  **调用者不在事件循环线程**时成立;主线程调用时轮询循环占住事件循环,按键无法分派,
  应答队列永远不会被填。**反证**:picker 路径 `cli.py:9296-9301 @ 863e313` 在
  `self._app` 存在时显式 `threading.Thread(...)` 起后台线程做同一件事,直连路径没有。
- **触发条件**:TUI 交互模式 + `/model <name>` 直连(非无参 picker)+
  `expensive_model_warning` 返回非 None(input > $20/M 或 output > $100/M,
  `hermes_cli/model_cost_guard.py:12-13 @ 863e313`)。
- **置信度**:**高**(§0.2 用桩对象实测:主线程调用阻塞满 timeout 并返回 `None`)。

---

**#3 — `/config` 在 `--ignore-user-config` 下谎报配置文件**

- **现象**:`hermes chat --ignore-user-config` 启动后 `/config` 显示
  `Config File: ~/.hermes/config.yaml (loaded)`,而该文件实际被完全跳过。
- **锚点**:`cli.py:7836-7841 @ 863e313` vs 真 loader `cli.py:426-438 @ 863e313`
  (多出 `ignore_user_config = os.environ.get("HERMES_IGNORE_USER_CONFIG") == "1"`);
  设置者 `hermes_cli/main.py:2675 @ 863e313`。
- **为什么可疑**:show_config 是 loader 路径选择逻辑的**残缺副本**,少了一个条件。
  这是「同一决策被两处独立推导」的典型后果。
- **触发条件**:`--ignore-user-config`(或直接设 `HERMES_IGNORE_USER_CONFIG=1`)+ `/config`。
- **置信度**:**高**。

**#3b — profile 切换后 `/config` 报旧 HERMES_HOME**

- **现象**:切到另一个 profile 后,`/model x --global` 写进新 profile 的 config.yaml,
  而 `/config` 的 `Config File:` 仍指向启动时那个 home。用户按 `/config` 给的路径去编辑,
  改的是一个不再生效的文件。
- **锚点**:`cli.py:229 @ 863e313`(import 期 `_hermes_home`)与
  `cli.py:4128 @ 863e313`(`save_config_value` 用实时 `get_hermes_home()`);
  覆写机制 `hermes_constants.py:45-50 @ 863e313`。
- **为什么可疑**:读写两端对「home 在哪」用了**不同解析时机** —— 一个 import 期冻结、
  一个每次调用实时解析。`save_config_value` 的注释(`cli.py:4117 @ 863e313`)明确说选实时是
  为了 profile 切换,这等于承认 import 期常量在这个场景下是错的;而 `show_config` 用的正是它。
- **触发条件**:运行期存在 HERMES_HOME 覆写(profile 切换)。
- **置信度**:中高(机制确凿;是否有 CLI 路径在同进程内切 profile 需跨段确认)。

---

**#4 — `/config` 的 `Timeout` 显示 60s,实际是 180s**

- **现象**:默认安装下 `/config` 打印 `Timeout: 60s`,但 terminal 工具用 180 秒。
- **锚点**:`cli.py:7834 @ 863e313`(`os.getenv("TERMINAL_TIMEOUT", "60")`)vs
  `tools/terminal_tool.py:1547 @ 863e313`(`_parse_env_var("TERMINAL_TIMEOUT", "180")`);
  `terminal` 默认字典无 `timeout` 键:`cli.py:447-459 @ 863e313`。
- **为什么可疑**:兜底默认值在两处各写一份,已经漂移。用户据此判断「命令为什么被杀」
  会得出错误结论(以为 60 秒超时,实际 180)。
- **触发条件**:config.yaml 未显式设置 `terminal.timeout`(默认情况)。
- **置信度**:**高**。

---

**#5 — `/new` 创建的会话不记录 `cwd`,导致这些会话恢复时永不回到原目录**

- **现象**:`hermes` → `/new` → 干活 → 退出 → `cd ~` → `hermes --resume <id>`:
  没有 `↻ Working directory:` 提示,terminal 工具留在 `~`。
- **锚点**:`cli.py:8251-8259 @ 863e313`(`create_session` 不传 `cwd`)+
  `cli.py:8260 @ 863e313`(`_session_db_created = True`)封死了 agent 侧补写入口
  `run_agent.py:625 @ 863e313`;正确写法见 `run_agent.py:657 @ 863e313`。
- **为什么可疑**:两个 `create_session` 调用点参数不一致,而只有其中一个带 `cwd`。
  `/branch`(`hermes_cli/cli_commands_mixin.py:1233 @ 863e313`)同样不传,但它不置
  `_session_db_created`,所以还有 `COALESCE` 回填机会(`hermes_state.py:3010 @ 863e313`)。
- **触发条件**:会话由 `/new`(以及委托给它的 `/clear`、`/reset`)创建。
- **置信度**:**高**(静态链路完整)。

---

**#6 — `_restore_session_cwd` 不检查 terminal backend,可能把宿主路径写进 SSH 后端的 `TERMINAL_CWD`**

- **现象**:把 `terminal.env_type` 从 `local` 改成 `ssh` 之后,恢复一个旧(local 时期录的)会话,
  之后每条远程命令都在一个远端不存在的目录里执行。
- **锚点**:`cli.py:7329 @ 863e313`(无条件 `os.environ["TERMINAL_CWD"] = recorded`);
  写入端有守卫 `run_agent.py:83-85 @ 863e313`;
  terminal 工具只对容器后端做兜底净化
  `tools/terminal_tool.py:1527-1533 @ 863e313`,而 `ssh` 不在
  `_CONTAINER_BACKENDS`(`tools/terminal_tool.py:1367 @ 863e313`)。
- **为什么可疑**:写入端做了 backend 守卫、读取端没有 —— 不对称。docker 等容器后端下游会
  兜住(`_is_unusable_container_cwd` 丢弃宿主路径),`ssh` 不会。
- **触发条件**:会话录制时 `TERMINAL_ENV=local`,恢复时 `TERMINAL_ENV=ssh`。
- **置信度**:**中**(需要用户中途改后端;但改后端正是长期用户的常见操作)。

**#6b — 「已在该目录」早退不同步 `TERMINAL_CWD`**

- **现象**:若进程 cwd 恰好等于会话记录的 cwd,而 `TERMINAL_CWD` 指向别处,
  恢复后终端工具仍在别处 —— 且不会有任何提示(该分支连日志都不打)。
- **锚点**:`cli.py:7307-7308 @ 863e313`。
- **为什么可疑**:该分支只比对**进程 cwd**,不检查 `TERMINAL_CWD`。local 后端下
  config bridge 已把两者对齐(`cli.py:653-655 @ 863e313` + `cli.py:707 @ 863e313`),
  所以当前无害;但这是一条依赖外部不变量的隐式契约,任何让二者脱钩的改动都会打破它。
- **触发条件**:进程 cwd == 会话记录的 cwd,且 `TERMINAL_CWD` 指向第三个位置
  (需要 config bridge 的 local 分支被绕过 —— 例如 `_HERMES_GATEWAY=1`
  导致 `cli.py:704-705 @ 863e313` 跳过导出,或后端非 local)。
- **置信度**:低(当前无害的设计脆弱点)。

---

**#7 — `/config`、`/tools`、`/toolsets`、`/gateway-status` 的输出在 Ctrl+L / 窗口变宽后消失**

- **现象**:执行 `/config` 后按 Ctrl+L(或拖动窗口改变宽度),输出不再出现;
  而 `/help`、`/history` 的输出会被重绘回来。
- **锚点**:`cli.py:7854-7885 @ 863e313`(裸 `print`)、
  `cli.py:7759-7794 @ 863e313`、`cli.py:7802-7826 @ 863e313`、
  `cli.py:9782-9833 @ 863e313`;只有 `_cprint` 记录历史
  `cli.py:3086 @ 863e313`;重放触发点 `cli.py:4855 @ 863e313`(`/redraw`)与
  `cli.py:4983 @ 863e313`(resize)。
- **为什么可疑**:同一文件里存在 `_cli_visible_print`(`cli.py:3210 @ 863e313`)
  专门解决这类问题,而这四个函数没用它 —— 不一致本身就是信号。
- **触发条件**:TUI 交互模式 + 上述命令 + 一次 Ctrl+L 或宽度变化。
- **置信度**:中高(重放缓冲不含这些行是确定的;是否「完全看不到」还取决于
  `patch_stdout` 的行为,`_cli_visible_print` 的 docstring 声称「would render nothing」,
  见文档出入 D3)。

---

**#8 — `_apply_model_switch_result` 与 `_handle_model_switch` 尾部是两份约 90 行的近似复制,且异常保护不对称**

- **现象**:同一套「提交切换 + 打印元信息 + 持久化」逻辑写了两遍。
- **锚点**:`cli.py:9092-9233 @ 863e313`(picker 路径)与
  `cli.py:9462-9584 @ 863e313`(直连路径)。差异点:
  - 只有直连路径支持 `--once`(`cli.py:9528-9531 @ 863e313`);
  - picker 路径把 `resolve_display_context_length` 包在 `try/except` 里
    (`cli.py:9191-9205 @ 863e313`),直连路径**没有**
    (`cli.py:9542-9553 @ 863e313`)。
- **为什么可疑**:直连路径若在 9543 抛异常,切换**已经**施加到 CLI 与 agent
  (`cli.py:9479-9503 @ 863e313`)、`_pending_model_switch_note` 已设
  (`cli.py:9522 @ 863e313`),但 9572-9580 的 `--global` 持久化被跳过 ——
  「切了但没存」的半成品状态。
- **触发条件**:`resolve_display_context_length` 抛异常。该函数内部对解析器有
  `try/except`(`hermes_cli/model_switch.py:1066-1079 @ 863e313`),
  仅剩 `int(model_info.context_window)`(`hermes_cli/model_switch.py:1081-1082 @ 863e313`)
  等极窄路径可能抛。
- **置信度**:重复本身=高;实际触发=**低**。

---

**#9 — 裸 `/resume` 的编号在两份独立查询的列表上解析(TOCTOU)**

- **现象**:裸 `/resume` 列表里第 3 行是会话 A;敲 `3` 之后恢复的却是会话 B。
- **锚点**:arm 时 `hermes_cli/cli_commands_mixin.py:978 @ 863e313`;
  校验 `cli.py:8354 @ 863e313`(对 armed 快照);
  真正解析 `hermes_cli/cli_commands_mixin.py:993-1001 @ 863e313`(重新查询)。
- **为什么可疑**:注释(`hermes_cli/cli_commands_mixin.py:973-977 @ 863e313`)
  声称三处「all three go through `_list_recent_sessions(limit=10)`」以保证一致 ——
  但一致的是**函数**,不是**结果**。
- **触发条件**:arm 与选择之间有新的 cli 源会话被创建(并发 gateway / kanban worker /
  另一终端)。默认排序按 `started_at`(`hermes_state.py:5830-5831 @ 863e313` docstring +
  `hermes_cli/session_listing.py:77 @ 863e313` 的 `order_by_last_active=bool(search)`),
  已有行相对顺序稳定,所以只有「新增」会整体移位。
- **置信度**:**中低**。

---

**#10 — 模态提交与超时之间的窄竞态会同时吞掉答案和用户草稿**

- **现象**:在贵模型确认框上按下选择,却看到「Model switch cancelled」,
  同时模态弹出前正在输入的草稿也没了。
- **为什么可疑**:提交端与消费端对**两个**共享变量(`response_queue` 与
  `_slash_confirm_deadline`)的读写没有任何同步;消费端还把
  「`_slash_confirm_state is not None`」当作「需要 teardown」的判据 ——
  而提交端恰恰会先把它置 `None`,于是 teardown(含草稿还原)被条件性跳过。
- **锚点**:`cli.py:8797-8799 @ 863e313`(先 `put` 后清 deadline)与
  `cli.py:8780-8783 @ 863e313`(超时后才读 deadline);
  `cli.py:8788-8790 @ 863e313` 的 `finally` 因 `state is None` 跳过 teardown,
  于是 `cli.py:8749 @ 863e313` 的 `_restore_modal_input_snapshot()` 不执行。
- **触发条件**:`queue.get(timeout=1)` 恰好在用户按键提交的同一瞬间超时。
- **置信度**:**低**(窗口极窄),但后果是「答案丢失 + 草稿丢失」双重。

---

**#11 — `--once` 一回合切换会永久裁剪本会话的 fallback 链**

- **现象**:`/model <另一 provider> --once` 一回合后模型切回来了,但后续真实故障时
  可回退的 provider 变少甚至为空。
- **锚点**:裁剪 `agent/agent_runtime_helpers.py:2764-2773 @ 863e313`;
  快照不含 `_fallback_chain`:`cli.py:8984-8995 @ 863e313`;
  `restore_primary_runtime` 只重置 index/flag:`agent/agent_runtime_helpers.py:1709-1712 @ 863e313`。
- **为什么可疑**:`--once` 的语义是「这一回合之后一切照旧」,但它借用的恢复通道
  (`restore_primary_runtime`)原本只为 fallback 服务 —— fallback 从不裁剪 chain,
  所以那条通道**没有理由**去重建它。复用通道时没人核对「`switch_model` 到底写了哪些字段」,
  裁剪就成了 `--once` 的永久副作用。而且这个损坏**完全不可见**:只有下一次真实故障才暴露。
- **触发条件**:`--once` 且新旧 provider 不同(`old_norm != new_norm`)且配置了 fallback 链。
- **置信度**:**高**(静态链路完整)。

---

**#12 — 首次 `--once` 切换后,`reasoning_config` 不会被还原**

- **现象**:`/model B --once` 之后回到模型 A,但 A 一直用着 B 的 reasoning 配置。
- **锚点**:重解析 `agent/agent_runtime_helpers.py:2696-2712 @ 863e313`;
  还原条件 `agent/agent_runtime_helpers.py:1705-1707 @ 863e313`(`is not None` 才还原);
  两份 `_primary_runtime` 构造:agent_init 版**无** `reasoning_config`
  (`agent/agent_init.py:2777-2796 @ 863e313`),switch_model 版**有**
  (`agent/agent_runtime_helpers.py:2737 @ 863e313`)。
  CLI 侧 `self.reasoning_config` 也不在 `cli.py:8984-8992 @ 863e313` 的键列表里。
- **为什么可疑**:还原逻辑用 `is not None` 做「快照里有没有这个字段」的判据,并注释成
  「older sessions」的兼容分支 —— 但缺这个字段的不是老会话,而是**同一版本里另一个构造点**
  (agent_init)。两处构造同一个 dict、字段集不同,是典型的「结构体没有单一定义」问题。
- **触发条件**:进程启动后**第一条** `--once` 切换(此时 `_primary_runtime` 还是 agent_init
  那份);且新旧模型的 `reasoning_effort` 覆写不同。
- **置信度**:**中高**。

---

**#13 — 一回合还原时强行 `_rate_limited_until = 0`,抹掉真实限流冷却**

- **现象**:`--once` 那一回合撞上限流后,下一回合不但没有等冷却,反而立刻再次打向同一个
  被限流的 provider。
- **锚点**:`cli.py:9022-9024 @ 863e313`;被绕过的门
  `agent/agent_runtime_helpers.py:1471-1472 @ 863e313`。
- **为什么可疑**:该赋值的目的只是绕过冷却门以完成一次**用户显式请求**的还原,
  但它无差别清零,包括本回合刚记录的真实限流冷却。
- **触发条件**:`--once` 的那一回合里主 provider 被限流并设置了 `_rate_limited_until`。
- **置信度**:**中**。

---

**#14 — `copy.deepcopy(_primary_runtime)` 隐式依赖「callable api_key 一定是普通函数」**

- **现象(潜在)**:若 api_key 是可调用**实例**,`/model x --once` 会在快照阶段抛异常,
  且该异常没有任何本地保护 —— 在 inline 路径上会直接冒到 prompt_toolkit 的按键处理器里。
- **触发条件**:某 provider 的 token provider 由闭包函数改为可调用对象(当前不存在)。
- **锚点**:`cli.py:8993-8995 @ 863e313`;`_primary_runtime["api_key"]` 来源
  `agent/agent_init.py:2783 @ 863e313`;callable api_key 是受支持形态
  (`agent/azure_identity_adapter.py:440-446 @ 863e313`,`cli.py:7846-7848 @ 863e313`)。
- **为什么可疑**:`_snapshot_model_runtime` 无任何异常保护;若 api_key 是可调用**实例**,
  deepcopy 会克隆 credential 对象图。
- **置信度**:**低**(当前 `get_bearer_token_provider` 返回闭包函数,deepcopy 视为原子)。

---

**#15 — `/model` 在 agent 运行中也走 UI 线程,直接对活 agent 做 in-place swap**

- **现象(潜在)**:agent 正在流式输出时敲 `/model x`,当前这一轮可能中途换 client /
  换 model 名 / 丢 system prompt 缓存,产生半新半旧的一轮对话。
- **锚点**:`cli.py:9626-9636 @ 863e313`(无 `_agent_running` 守卫)对比
  `cli.py:9652 @ 863e313` / `cli.py:9683 @ 863e313`(steer / background 都有);
  施加点 `cli.py:9495-9503 @ 863e313`。
- **为什么可疑**:`switch_model` 会重建 client、清 transport cache、失效 system prompt
  (`agent/agent_runtime_helpers.py:2714-2715 @ 863e313`),而 `run_conversation`
  可能正在另一线程持有同一 agent。本段无锁、无延后。
- **触发条件**:agent 流式输出期间敲 `/model x`。
- **置信度**:**中**(需跨段确认 `run_conversation` 侧是否另有保护;本段确实没有)。

---

**#16 — `/new` 的「重置到 config 默认」读 import 期快照,看不见同进程内 `--global` 的写入**

- **现象**:`/model gpt5 --global` → `/new`,模型回到**启动时**的默认值而非 `gpt5`。
- **锚点**:`cli.py:8177-8182 @ 863e313`(读 `CLI_CONFIG`);
  `CLI_CONFIG = load_cli_config()` 仅在 `cli.py:792 @ 863e313` 赋值一次、全文件无重新赋值;
  写入端 `cli.py:9574-9575 @ 863e313` → `save_config_value` → `cli.py:4128 @ 863e313` 只写磁盘。
- **为什么可疑**:`CLI_CONFIG` 是 import 期快照且全文件只赋值一次,而同一文件里的
  `save_config_value` 只写磁盘、不回写内存 —— 「持久化」与「重新读取」用了两条不相交的路径。
  注释还明说要「from config.yaml」重新推导(见 D2),说明作者的意图正是读磁盘。
- **触发条件**:同一进程内先 `--global` 切换、再 `/new`。
- **置信度**:**高**。

---

## 4. 与文档/注释的出入

> 规则:README / AGENTS.md / website/docs 与代码冲突以代码为准。本段冲突主要出在**注释与
> docstring** 与代码本身之间 —— 同样按「以代码为准」记录。

**D1 — `show_config` 的注释说 terminal 配置来自 `cli-config.yaml`**

```
        # Get terminal config from environment (which was set from cli-config.yaml)
```
`cli.py:7831 @ 863e313`

实际:实测仓库根**不存在** `cli-config.yaml`;`load_cli_config()` 的实际来源是
`{HERMES_HOME}/config.yaml`(`cli.py:427/435-436 @ 863e313`),且当用户 config 不存在时
使用的是内置 defaults(`cli.py:441+ @ 863e313`),而不是任何文件。
**定案:注释过时,以代码为准。**

**D2 — `new_session` 的注释说「Re-derive … from config.yaml」**

```
        # forward.  Re-derive model/provider and service tier from config.yaml
```
`cli.py:8170 @ 863e313`

实际读的是 import 期快照 `CLI_CONFIG`(`cli.py:8174/8177 @ 863e313`),不是 config.yaml。
**定案:注释与代码不符,行为按 §3 #16 描述。**

**D3 — `_cli_visible_print` 的 docstring 说裸 `print()` 会「render nothing」**

```
    Bare ``print()`` output is swallowed by ``patch_stdout`` while an
    interactive ``Application`` is running, so ``/sessions`` and ``/history``
    would render nothing. Route through ``_cprint`` (prompt_toolkit-native)
    in that case, and fall back to ``print`` otherwise.
```
`cli.py:3213-3216 @ 863e313`

同文件另一处的说法更精确 —— 被吞的是 **ANSI 转义**,不是纯文本:

```
    Raw ANSI escapes written via print() are swallowed by patch_stdout's
    StdoutProxy.  Routing through print_formatted_text(ANSI(...)) lets
    prompt_toolkit parse the escapes and render real colors.
```
`cli.py:3073-3075 @ 863e313`

两条注释互相冲突。**定案:未在本轮实测中判定,标记为待验证**;
但无论哪条为真,#7(不进重放缓冲)都成立。

**D4 — `save_config_value` 的 docstring 与函数体自相矛盾**

```
def save_config_value(key_path: str, value: any) -> bool:
    """
    Save a value to the active config file at the specified key path.
    
    Respects the same lookup order as load_cli_config():
    1. ~/.hermes/config.yaml (user config - preferred, used if it exists)
    2. ./cli-config.yaml (project config - fallback)
```
`cli.py:4100-4106 @ 863e313`

函数体明确**拒绝**第 2 条:

```
    config_path = get_hermes_home() / 'config.yaml'
```
`cli.py:4128 @ 863e313`

而且 4116-4127 的注释详细解释了为什么**不能**退回 `cli-config.yaml`
(wake-word 设置每次重启消失的历史 bug)。**定案:docstring 是修复前的残留,以代码为准。**
这也是 `/model --global` 与 `/config` 走不同 home 解析(#3b)的根源。

**D5 — `_restore_session_cwd` docstring 声称「Idempotent and safe to call from every resume path」**

```
        Idempotent and safe to call from every resume path. When the stored
```
`cli.py:7287 @ 863e313`

幂等性成立(第二次调用会命中 7307 的早退)。但「every resume path」这个前提在 `/new` 创建
的会话上不成立 —— 那些会话根本没有 `cwd` 可恢复(#5)。**定案:docstring 描述的是本函数的
契约,问题在写入端;记录为需要一并修的对偶缺口。**

---

## 5. 移交

### 5.1 本段确认的高置信度缺陷(建议后续轮次优先复核 / 汇入成品章)

| # | 一句话 | 置信度 |
|---|---|---|
| 1 | 启动的「工具缺 key」提示因 `KeyError('missing_vars')` 被裸 except 吞掉,整块从不显示 | 高(已实机复现) |
| 2 | `/model <贵模型>` 走 UI 线程 → 模态自锁 → 冻 120 秒后误报取消 | 高(已实机复现自锁) |
| 3 | `/config` 忽略 `--ignore-user-config`,谎报配置文件已加载 | 高 |
| 4 | `/config` 的 `Timeout` 兜底 60 vs 真实 180 | 高 |
| 5 | `/new` 创建的会话不写 `cwd`,恢复时永不回原目录 | 高 |
| 11 | `--once` 永久裁剪 fallback 链 | 高 |
| 16 | `/new` 的模型重置读 import 期 `CLI_CONFIG` 快照 | 高 |

### 5.2 三条前提的最终裁定

1. **假**。`show_config` 不读任何 loader;它打印活属性 + 环境变量,外加一个它从不读取内容
   的文件路径,而该路径的推导是 `load_cli_config()` 的残缺副本(#3、#3b、#4、D1)。
   **注意这与上一轮「cli.py 用了一套更浅的 config merge」的结论方向一致但性质不同**:
   这里连 merge 都没有,是**第三套**独立的推导。
2. **半真**。快照覆盖 CLI 8 字段 + `agent._primary_runtime` 深拷贝;
   漏 `_fallback_chain`/`_fallback_model`(#11)、`reasoning_config`(#12);
   复原时清零 `_rate_limited_until`(#13);deepcopy 依赖 callable api_key 是函数(#14)。
3. **真(失败姿态正确),但对偶端有洞**。目录消失 → 一行 dim 提示、不 chdir、不崩溃;
   但 `/new` 会话根本不记录 cwd(#5),且读取端缺 backend 守卫(#6)。

### 5.3 留给后续轮次的未决问题

- **U1**:`patch_stdout` 下裸 `print()` 究竟是「完全不显示」还是「显示但丢 ANSI」?
  这决定 #7 的严重度是「输出丢失」还是「重绘后丢失」。需要一次真实 TUI 会话验证
  (本轮环境无法起交互终端)。文档冲突见 D3。
- **U2**:#15 需要跨段确认 —— `run_conversation` / turn loop 侧是否对
  「turn 进行中被 `switch_model`」有保护(锁、代际号、快照)。本段(CLI 侧)确定没有。
- **U3**:`_restore_primary_runtime` 返回 `False` 时 CLI 已改过 3 个 agent 字段再落到
  `switch_model`,两条路径叠加后的最终状态是否总是自洽,需要一次针对
  `agent/agent_runtime_helpers.py:1449-1560 @ 863e313` 的专门精读。
- **U4**:`_show_tool_availability_warnings`(#1)修好之后**会显示什么**?
  实测 `unavailable` 12 项中第一项 `browser-cdp` 的 `env_vars` 是空列表,
  说明修复不能简单把 `missing_vars` 换成 `env_vars` —— 过滤条件
  「missing API keys(not system deps)」的语义需要重新定义。这本身是一条设计教训。

### 5.4 可迁移的设计观察(给成品章备料)

1. **「同一决策被两处独立推导」是本段所有配置类缺陷的唯一根因**:
   `show_config` 复制 loader 的路径选择(#3)、复制 timeout 默认值(#4)、
   `_apply_model_switch_result` 复制 `_handle_model_switch` 的提交序列(#8)、
   `_consume_pending_resume_selection` 与 `_handle_resume_command` 各查一次列表(#9)。
   自造 harness 时的规则:**展示层永远从执行层取值,不得自己再算一遍**;
   默认值必须只有一个定义点。
2. **裸 `except Exception: pass` 会把「契约变更」伪装成「功能正常」**(#1)。
   数据源换了字段名,消费者静默变成 no-op,且**只在有内容要显示时**才失败。
   规则:兜底 except 至少要 `logger.debug(..., exc_info=True)`。
3. **线程亲和性必须写进函数签名或断言,而不是靠调用者自觉**(#2)。
   `_prompt_text_input_modal` 的正确性依赖「不在事件循环线程」,但它对主线程调用
   不是拒绝而是**退化成同步执行**,把一个契约违规变成一次 120 秒挂起。
   规则:这类函数应在 `in_main_thread and self._app` 时**直接 fail-fast 或走真正的异步路径**。
4. **写入端做了守卫,读取端就必须做对称守卫**(#6)。
   `_launch_cwd_for_session` 拒绝为非 local 后端记录 cwd,而 `_restore_session_cwd`
   无条件写 `TERMINAL_CWD`。守卫的对称性应当是可测试的不变量。
5. **「快照-恢复」型状态管理必须列举被 mutate 的**全部**字段**(#11、#12、#13)。
   本段的快照复用了 fallback 机制的恢复通道,这是聪明的(省掉重建 client 的逻辑),
   但它继承了那条通道的**作用域**:fallback 恢复只需还原「主 runtime」,
   而 `/model --once` 还需要还原「切换的副作用」(chain 裁剪、reasoning 重解析)。
   规则:复用恢复通道前,先枚举变更端 `switch_model` 写了哪些字段,逐一对账。
