# r8b-raw-cli-module —— cli.py 1-4204(模块层)

> 底稿(证据层)。研究对象:`NousResearch/hermes-agent` @ `863e313`。
> 覆盖范围:`cli.py` 第 1–4204 行的**模块层**(类 `HermesCLI` 之前的一切),
> 其中 **409–901 行 `load_cli_config()` 已由前轮精读,本稿跳过**,仅在本段代码依赖它时引用。
> 溯源约定:每条断言后紧跟 `路径:行号 @ 863e313` 与代码原文块。

---

## 0. 自验记录

- **锚点总数**:本稿共 **97** 个 `路径:行号 @ 863e313` 锚点。
- **重新核验数量**:**全部 97 个**逐行 `sed -n 'Np'` 复核(分 6 批 dump 比对),超出要求的 15 个下限。
- **核验中发现并修正的漂移**:**2 处**。
  1. 起初把 `_prune_stale_worktrees` 的 "aggressive tier" 文档句记为 `cli.py:2220`,实际空行;
     复核后修正为 `cli.py:2222`。
  2. 起初把 rich 系列导入记为「`load_cli_config` 之后紧邻」,复核发现 `load_cli_config` 与
     rich 导入之间还夹着 830–891 的 `_AsyncHttpxDelNeuter` 元路径钩子,已在 §2.1 补正。
- **额外实证**:worktree 数据丢失路径(§3-1)不是静态推断,而是在容器里用真实 git 复现过
  (无 remote 仓库 → `git for-each-ref refs/remotes` 返回 rc=0 且空输出 → 判定「无未推送提交」→
  `git worktree remove --force` + `git branch -D` 把 agent 的提交从工作区与分支上一并抹掉)。
- **未能验证项**:prompt_toolkit 未安装于本容器(`ModuleNotFoundError: No module named 'prompt_toolkit'`),
  §2.11 中「补丁与上游 `Vt100Parser.feed` 的差异」是基于补丁自身注释与其配套测试的推断,已在 §5 移交。

---

## 1. 段内地图

| 行段 | 内容 | 性质 |
|---|---|---|
| 1–24 | shebang / 模块 docstring / `hermes_bootstrap` 首位导入 | 启动顺序契约 |
| 26–51 | 标准库导入 + `logger` + `HERMES_QUIET=1` 副作用 | 导入期副作用 |
| 53–92 | hermes_cli mixin / prompt_toolkit 导入 + 键位别名安装 | 重型导入 |
| 93–208 | **惰性导入 shim 家族(第一批)** + 两个「伪 shim」+ 别名反查缓存 | premise 1 战场 |
| 209–231 | banner 导入、`get_hermes_home()` 快照、`.env` 加载 | 导入期副作用 |
| 234–331 | 推理标签剥离 `_strip_reasoning_tags` + 助手内容取文本 | 纯函数 |
| 338–407 | prefill / reasoning_effort / service_tier 三个小解析器 | 纯函数 |
| **409–901** | **`load_cli_config()`(跳过)** + 792 行 `CLI_CONFIG` 求值 + 830–891 httpx `__del__` 元路径钩子 + 893–897 rich 导入 | 前轮已读 |
| 901–986 | **惰性导入 shim 家族(第二批)**:AIAgent / 工具定义 / toolset / cron / 清理回调 | premise 1 战场 |
| 989–1002 | 退出期模块级状态位(`_cleanup_done` / `_active_agent_ref` / `_tui_input_modes_active` 等) | 全局状态 |
| 1005–1062 | `_mark_tui_input_modes_active` / `_prepare_deferred_agent_startup`(Termux 延迟启动) | 生命周期 |
| 1064–1170 | **退出看门狗**:`_arm_exit_watchdog` + 信号版 | premise 3 战场 |
| 1173–1399 | `_run_cleanup` 主清理 + session finalize 去重 + 终端输入模式复位 | 退出路径 |
| 1402–2115 | **git worktree 隔离**:路径归一化 / base 解析 / 建树 / 脏与未推送判定 / 锁活性 / 清理 | premise 2 战场 |
| 2118–2210 | 启动期自动维护:state.db 剪枝归档、checkpoint 剪枝 | 启动路径 |
| 2213–2497 | worktree 陈旧剪枝(三相:年龄过滤 / 并行分类 / 串行变更)+ 孤儿分支剪枝 | 启动路径 |
| 2499–2560 | ANSI 基元、`_hex_to_ansi`、明暗模式检测常量 | 呈现层 |
| 2562–2790 | 亮色模式检测(6 级优先级,含 OSC 11 探测)+ 皮肤取色钩子 + 导入期预热 | 呈现层 |
| 2794–2902 | `_SkinAwareAnsi` 惰性 ANSI、`_b`/`_d`、rich 文本与 markdown 剥离 | 呈现层 |
| 2905–2981 | Windows 路径保护、流式宽度、最终助手内容渲染三模式 | 呈现层 |
| 2984–3227 | **输出历史**(重绘重放)+ `_cprint` 跨线程打印 + `_prepend_note_to_message` | 呈现层核心 |
| 3230–3489 | **附件/文件拖放**:路径切分、解析、拖放检测、徽章、剪贴板粘贴判定 | 输入层 |
| 3492–3835 | **prompt_toolkit 补丁族**:括号粘贴超时、CPR 抑制、终端响应清洗、Ctrl+Enter、输入高度估算 | 输入层核心 |
| 3838–3865 | `_collect_query_images` 单查询模式图片收集 | 输入层 |
| 3868–3918 | `ChatConsole`(rich → prompt_toolkit 适配器) | 呈现层 |
| 3920–3993 | ASCII logo / caduceus / 紧凑 banner | 呈现层 |
| 3997–4016 | `_looks_like_slash_command` | 分发 |
| 4019–4097 | skill 斜杠命令与 bundle 的记忆化取用 + 插件命令名 + `--skills` 解析 | 分发 |
| 4100–4157 | **`save_config_value`** 运行时配置持久化 | 配置写路径 |
| 4167–4203 | `_normalize_moa_model`、`_VoiceInputMessage` 哨兵 | 小工具 |
| 4205– | `class HermesCLI`(超出本段) | — |

---

## 2. 逐机制精读

### 2.0 三条前提的校验结论(先说结论,后给证据)

| # | 前提原文 | 判定 | 摘要 |
|---|---|---|---|
| 1 | `def X(*args, **kwargs)` 一行式都是惰性导入 shim | **部分为真,存在反例** | 大多数确实是;但 `format_duration_compact:108` / `format_token_count_compact:169` **不是 shim,是本地重复实现**;`get_tool_definitions:907` **不是纯 shim**,它额外插了一道 MCP 发现同步屏障;`CanonicalUsage:96` / `estimate_usage_cost:102` 是**全仓无人引用的死代码** |
| 2 | worktree 是「让 agent 改代码而不碰用户 checkout」的会话级隔离 | **主旨为真,但目的与边界被说窄了,且并非「不碰 checkout」** | 代码注释给的首要动机是**多 agent 并发不互撞**;worktree 建在 `<repo>/.worktrees/` **就在用户 checkout 里**,还会**改写用户的 `.gitignore`**;隔离靠 `TERMINAL_CWD` 环境变量而**非 `os.chdir`**,进程 cwd 始终是用户 checkout |
| 3 | `_arm_exit_watchdog` 是因为解释器正常关闭会挂 | **为真,且原因被代码与配套模块交叉证实** | 具体挂点有二:清理步骤卡网络 I/O;以及 `concurrent.futures` 的 atexit 钩子**无条件 join** 非守护线程池工人 |

---

### 2.1 导入序:为什么第一行必须是 `hermes_bootstrap`

模块开头显式声明了一个**导入顺序契约**:`hermes_bootstrap` 必须是最早的 import,因为它在 Windows 上把
stdio 切成 UTF-8;而这里同时写了一个**极不寻常的兜底**——允许它 import 失败。

`cli.py:17 @ 863e313`

```python
try:
    import hermes_bootstrap  # noqa: F401
except ModuleNotFoundError:
    # Graceful fallback when hermes_bootstrap isn't registered in the venv
    # yet — happens during partial ``hermes update`` where git-reset landed
    # new code but ``uv pip install -e .`` didn't finish.  Missing bootstrap
    # means UTF-8 stdio setup is skipped on Windows; POSIX is unaffected.
    pass
```

**没有它会坏什么**:不是「Windows 打不出中文」这么轻。banner 里是 Unicode 制表符,cp1252 编码下
`print()` 直接 `UnicodeEncodeError`,CLI 在打印欢迎语时就崩。而 `except ModuleNotFoundError` 这一支
是给**半完成的 `hermes update`** 留的:git 已经把新代码 reset 进工作区、但 `uv pip install -e .` 还没跑完,
此时 `hermes_bootstrap` 尚未注册进 venv。作者宁可在 Windows 上退化成「无 UTF-8 stdio」,也不愿让
升级中途的用户拿到一个**连启动都不启动**的 CLI。

紧接着是一个**导入即副作用**:

`cli.py:51 @ 863e313`

```python
os.environ["HERMES_QUIET"] = "1"  # Our own modules
```

也就是说,**任何 `import cli` 的进程都会被强制静音**,包括 gateway 在函数内部懒加载 cli 时
(`gateway/run.py:20529` 的 `from cli import save_config_value`)。这是本文件多处「导入期副作用」中
最容易被忽略的一处。

模块层还有另外三处导入期副作用需要一并记住,它们决定了「`import cli` 不是免费的」:

- `cli.py:229 @ 863e313` —— HERMES_HOME 在**导入时被快照**:

```python
_hermes_home = get_hermes_home()
```

- `cli.py:792 @ 863e313` —— 整份 CLI 配置在**导入时求值**(并因此把 `TERMINAL_CWD` 等环境变量写死):

```python
CLI_CONFIG = load_cli_config()
```

- `cli.py:2780 @ 863e313` 与 `cli.py:2786 @ 863e313` —— 皮肤取色钩子安装 + 明暗模式探测预热(后者会向 TTY 发 OSC 11 查询):

```python
_install_skin_light_mode_hook()
```

```python
try:
    if sys.stdin.isatty() and sys.stdout.isatty():
        _detect_light_mode()
except Exception:
    pass
```

`cli.py:86 @ 863e313` 展示了一个值得抄的小手法:键位别名装完立刻把符号 `del` 掉,防止后续代码误用
一个「只应在导入期调用一次」的安装函数。

```python
    install_shift_enter_alias()
    install_ctrl_enter_alias()
    install_cmd_backspace_alias()
    install_ignored_terminal_sequences()
    del install_shift_enter_alias, install_ctrl_enter_alias, install_cmd_backspace_alias, install_ignored_terminal_sequences
```

**跳过段的依赖点(仅记依赖,不展开)**:`load_cli_config()`(`cli.py:409`)在 local 后端下会
**无条件把 `TERMINAL_CWD` 覆写成 `os.getcwd()`**——这条在 §3-2 会变成一个真实缺陷。

`cli.py:653 @ 863e313`

```python
    if effective_backend == "local":
        terminal_config["cwd"] = os.getcwd()
```

`cli.py:707 @ 863e313`

```python
                os.environ[env_var] = str(terminal_config[config_key])
```

模块层还夹了一个惰性 monkeypatch:把 openai SDK 的 `AsyncHttpxClientWrapper.__del__` 变成 no-op,
但**不立刻 import openai**,而是插一个 `sys.meta_path` finder 等到真正 import 时再打补丁。

`cli.py:889 @ 863e313`

```python
    _httpx_neuter_sys.meta_path.insert(0, _AsyncHttpxDelNeuter())
```

`cli.py:833 @ 863e313` 的注释交代了收益量级与**为什么必须在任何 AsyncOpenAI 实例构造之前完成**:

```python
# Neuter AsyncHttpxClientWrapper.__del__ before any AsyncOpenAI clients are
# created.  The SDK's __del__ schedules aclose() on asyncio.get_running_loop()
# which, during CLI idle time, finds prompt_toolkit's event loop and tries to
# close TCP transports bound to dead worker loops — producing
# "Event loop is closed" / "Press ENTER to continue..." errors.
```

这是全仓「用 import hook 换冷启动时间」的范式:eager import 要付 ~166ms/~30MB,finder 方案在
openai 从未被用到的路径上(如 `hermes --help`)一分钱不花,同时由 Python 导入系统本身保证
「先 import 后实例化」的时序,补丁不可能被绕过。

---

### 2.2 惰性导入 shim 家族 —— premise 1 的三个反例

**典型形态**长这样(`cli.py:901 @ 863e313`,前置注释在 899 行):

```python
def AIAgent(*args, **kwargs):
    from run_agent import AIAgent as _AIAgent

    return _AIAgent(*args, **kwargs)
```

`cli.py:915 @ 863e313`、`cli.py:925 @ 863e313`、`cli.py:950 @ 863e313`、`cli.py:959 @ 863e313` 等
十余个函数是同一模板。设计意图写在紧挨着的注释里:

`cli.py:209 @ 863e313`

```python
# NOTE: `from agent.account_usage import ...` is deliberately NOT at module
# top — it transitively pulls the OpenAI SDK chain (~230 ms cold) and is only
# needed when the user runs `/limits`. Lazy-imported inside the handler below.
```

**没有它会坏什么**:不是功能坏,是**交互体感坏**。`cli.py` 是 CLI 的入口模块,任何写在模块顶层的
`import` 都会计入「敲下 `hermes` 到看见提示符」的时间。把 `run_agent`(整个 agent + provider 栈)、
`model_tools`、`toolsets`、`cron`、`tools.terminal_tool`、`tools.browser_tool` 全部推迟到**第一次真正调用**,
裸交互启动只需要提示符所需的那点依赖。

#### 反例 A:`format_duration_compact` / `format_token_count_compact` 根本不是 shim

签名长得一模一样(`(*args, **kwargs)`),但函数体里**没有 import,是完整的本地实现**:

`cli.py:108 @ 863e313`

```python
def format_duration_compact(*args, **kwargs):
    seconds = float(args[0] if args else kwargs.get("seconds", 0.0))
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}m"
    hours = minutes / 60
    if hours < 24:
        remaining_min = int(minutes % 60)
        return f"{int(hours)}h {remaining_min}m" if remaining_min else f"{int(hours)}h"
    days = hours / 24
    return f"{days:.1f}d"
```

而 `agent/usage_pricing.py` 里有一份**逐行等价**的权威实现:

`agent/usage_pricing.py:1398 @ 863e313`

```python
def format_duration_compact(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}m"
    hours = minutes / 60
    if hours < 24:
        remaining_min = int(minutes % 60)
        return f"{int(hours)}h {remaining_min}m" if remaining_min else f"{int(hours)}h"
    days = hours / 24
    return f"{days:.1f}d"
```

`format_token_count_compact` 同理(`cli.py:169 @ 863e313` vs `agent/usage_pricing.py:1412 @ 863e313`)。

**为什么这是有意义的发现**:这两个函数在**状态栏热路径**上被调用——每次状态栏快照都会调一次
(`cli.py:5248 @ 863e313`):

```python
            "duration": format_duration_compact(elapsed_seconds),
```

也就是说,作者不是「忘了写 shim」,而是**故意把实现内联进 cli.py,以免状态栏刷新触发
`agent.usage_pricing` 的导入**(那条链会拖进定价表)。代价是**两份实现必须手工保持同步**,
而且它们保留了 `(*args, **kwargs)` 的伪装签名,读代码的人会误以为改一处就够。

#### 反例 B:`get_tool_definitions` 不是纯 shim,它是一道同步屏障

`cli.py:907 @ 863e313`

```python
def get_tool_definitions(*args, **kwargs):
    from hermes_cli.mcp_startup import wait_for_mcp_discovery
    from model_tools import get_tool_definitions as _get_tool_definitions

    wait_for_mcp_discovery()
    return _get_tool_definitions(*args, **kwargs)
```

第 911 行的 `wait_for_mcp_discovery()` 是**行为增量**,不是导入延迟。它解决的问题是:MCP 工具在
后台线程里异步发现,如果第一轮请求在发现完成前就把工具清单快照给了模型,那些 MCP 工具**这一轮
不存在**。屏障的成本被上游设计得很低——

`hermes_cli/mcp_startup.py:170 @ 863e313`

```python
def wait_for_mcp_discovery(
    timeout: "float | None" = None, *, single_query: bool = False
) -> None:
    """Wait for background MCP discovery before the first tool snapshot.

    ``thread.join(timeout)`` returns the INSTANT discovery completes, so this
    only ever blocks for the real connect time of a still-pending server —
    users with no MCP servers or fast servers pay ~0s.  The bound (from
    ``mcp_discovery_timeout`` in config) just caps the wait so a dead server
    can't freeze startup; servers that miss it are picked up by the automatic
    late-binding refresh.
```

**这是个值得抄的模式**:把「等后台任务」藏在**唯一消费点**的门面函数里,而不是在启动流程中间加一个
显式 `join`。调用方(`cli.py:7216`、`7585`、`7755`、`9922`)完全不需要知道 MCP 的存在。

#### 反例 C:两个 shim 是死代码

`cli.py:96 @ 863e313`

```python
def CanonicalUsage(*args, **kwargs):
    from agent.usage_pricing import CanonicalUsage as _CanonicalUsage

    return _CanonicalUsage(*args, **kwargs)
```

`cli.py:102 @ 863e313`

```python
def estimate_usage_cost(*args, **kwargs):
    from agent.usage_pricing import estimate_usage_cost as _estimate_usage_cost

    return _estimate_usage_cost(*args, **kwargs)
```

全仓 grep:`CanonicalUsage` 与 `estimate_usage_cost` 的所有引用都直接指向 `agent.usage_pricing`,
**没有任何地方 `from cli import` 这两个名字,cli.py 自身也从不调用它们**。

#### 这一族 shim 的共同结构性风险:它们是**函数,不是类**

`AIAgent` 在 cli.py 里是一个函数。这意味着:

- `isinstance(x, AIAgent)` 会抛 `TypeError`;
- `AIAgent.some_classmethod` / `AIAgent.__init__` 之类的类级访问全部失效。

当前唯一的外部消费点只把它当构造器用,所以没炸:

`hermes_cli/cli_commands_mixin.py:1954 @ 863e313`

```python
        from cli import AIAgent, ChatConsole, _accent_hex, _cprint, _maybe_remap_for_light_mode, _render_final_assistant_content, set_approval_callback, set_secret_capture_callback, set_sudo_password_callback
```

`CanonicalUsage` 同理更危险——它在 `agent/moa_loop.py:1613` 那类地方是被 `isinstance()` 用的:
如果哪天有人图省事写 `from cli import CanonicalUsage`,`isinstance` 会立刻 `TypeError`。
死代码在这里不是「无害的冗余」,而是**一个装了引信的陷阱**。

#### 另一种变体:记忆化 shim

`cli.py:4027 @ 863e313`

```python
def _ensure_skill_commands() -> dict:
    global _skill_commands
    if _skill_commands is None:
        from agent.skill_commands import scan_skill_commands

        _skill_commands = scan_skill_commands()
    return _skill_commands
```

`cli.py:4052 @ 863e313` 的 `get_skill_bundles()` 是同一形状。这两个既延迟导入、又缓存结果——
`scan_skill_commands()` 要扫磁盘上的 skill 目录,不缓存的话每次补全都要走一遍文件系统。
代价是**会话中途安装的新 skill 不会出现在斜杠命令里**(见 §3-9)。

---

### 2.3 `_strip_reasoning_tags`:为什么要处理三种残缺形态

`cli.py:234 @ 863e313`

```python
_REASONING_TAGS = (
    "REASONING_SCRATCHPAD",
    "think",
    "thinking",
    "reasoning",
    "thought",
)
```

`cli.py:243 @ 863e313` 的 docstring 把它要覆盖的三类输入讲得很清楚:

```python
def _strip_reasoning_tags(text: str) -> str:
    """Remove reasoning/thinking blocks from displayed text.

    Handles every case:
      * Closed pairs ``<tag>…</tag>`` (case-insensitive, multi-line).
      * Unterminated open tags that run to end-of-text (e.g. truncated
        generations on NIM/MiniMax where the close tag is dropped).
      * Stray orphan close tags (``stuff</think>answer``) left behind by
        partial-content dumps.
```

**没有它会坏什么**:开源推理模型把思维链塞在 `<think>…</think>` 里,provider 侧不一定会剥。
若模型被截断(NIM / MiniMax 上常见),闭合标签根本不存在——只处理闭合对的实现会把**整段思维链
原样打印给用户**。所以三条正则依次是:闭合对、开标签吃到结尾、孤儿闭标签。

同一个 docstring 里还写了一条**跨文件的同步义务**,这是本仓库里少见的显式耦合声明:

`cli.py:243 @ 863e313`(docstring 续)

```python
    Covers the variants emitted by reasoning models today: ``<think>``,
    ``<thinking>``, ``<reasoning>``, ``<REASONING_SCRATCHPAD>``, and
    ``<thought>`` (Gemma 4).  Must stay in sync with
    ``run_agent.py::_strip_think_blocks`` and the stream consumer's
    ``_OPEN_THINK_TAGS`` / ``_CLOSE_THINK_TAGS`` tuples.
```

值得注意的**不对称**:工具调用类标签用了 `\b[^>]*>` 允许带属性,推理标签却只匹配裸标签:

`cli.py:243 @ 863e313`(函数体节选)

```python
    cleaned = text
    for tag in _REASONING_TAGS:
        # Closed pair — case-insensitive so <THINK>…</THINK> is handled too.
        cleaned = re.sub(
            rf"<{tag}>.*?</{tag}>\s*",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
```

对比工具标签这一支:

```python
    # Tool-call XML blocks (openclaw/openclaw#67318).
    for tc_tag in ("tool_call", "tool_calls", "tool_result",
                   "function_call", "function_calls"):
        cleaned = re.sub(
            rf"<{tc_tag}\b[^>]*>.*?</{tc_tag}>\s*",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
```

所以 `<thinking budget="high">…</thinking>` 这种带属性的推理块**不会被剥**(见 §3-10)。

而 `<function name="...">` 那条特意加了行首/句末边界锚,`cli.py:243 @ 863e313`(续):

```python
    # <function name="..."> — boundary + attribute gated to avoid prose FPs.
    cleaned = re.sub(
        r'(?:(?<=^)|(?<=[\n\r.!?:]))[ \t]*'
        r'<function\b[^>]*\bname\s*=[^>]*>'
        r'(?:(?:(?!</function>).)*)</function>\s*',
        '',
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
```

这条边界门控就是在换「误伤散文」的风险:如果不加锚,一段讨论 XML 的正文里出现 `<function name=...>`
会被整段吞掉。

配套的两个取文本函数很短但有意义 —— `cli.py:315 @ 863e313` 处理 OpenAI 风格的多模态 content 列表:

```python
def _assistant_content_as_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return str(content)
```

`cli.py:330 @ 863e313` 把两者组合成「复制到剪贴板时该给用户的文本」:

```python
def _assistant_copy_text(content: Any) -> str:
    return _strip_reasoning_tags(_assistant_content_as_text(content))
```

**设计要点**:剥离只作用在**展示/复制**路径,不动 `messages` 里的原文——否则下一轮上下文就丢了模型的思维链。

---

### 2.4 三个小解析器:prefill / reasoning / service_tier

`cli.py:338 @ 863e313` —— prefill 消息(会话开始前预置的假对话,用来给模型定调):

```python
def _load_prefill_messages(file_path: str) -> List[Dict[str, Any]]:
    """Load ephemeral prefill messages from a JSON file.
```

它的相对路径基准用的是**导入期快照**:

`cli.py:351 @ 863e313`

```python
        path = _hermes_home / path
```

这一点与 `save_config_value` 明确采取的相反策略构成了文件内的自相矛盾(§3-4)。

`cli.py:367 @ 863e313` 的键位优先级值得记:环境变量 > 顶层 `prefill_messages_file` > `agent.prefill_messages_file`(legacy):

```python
def _resolve_prefill_messages_file(config: Dict[str, Any]) -> str:
    """Resolve the prefill file path from env/config.

    ``prefill_messages_file`` at the top level is the canonical config key.
    ``agent.prefill_messages_file`` remains a legacy fallback for older CLI and
    godmode-generated configs.
    """
```

`cli.py:399 @ 863e313` —— service tier 归一化,把一堆同义词折成 Responses API 的两态:

```python
def _parse_service_tier_config(raw: str) -> str | None:
    """Parse a persisted service-tier preference into a Responses API value."""
    value = str(raw or "").strip().lower()
    if not value or value in {"normal", "default", "standard", "off", "none"}:
        return None
    if value in {"fast", "priority", "on"}:
        return "priority"
    logger.warning("Unknown service_tier '%s', ignoring", raw)
    return None
```

`cli.py:386 @ 863e313` 的 reasoning 解析把「解析」下放给 `hermes_constants`,自己只负责**在
用户明明写了值却解析不出来时告警**——这是个容易被略过但很关键的区分:

```python
def _parse_reasoning_config(effort) -> dict | None:
    """Parse a reasoning effort level into an OpenRouter reasoning config dict.

    Accepts the raw config value (string or YAML boolean — ``false``/``off``
    parse as thinking disabled, see parse_reasoning_effort).
    """
    from hermes_constants import parse_reasoning_effort
    result = parse_reasoning_effort(effort)
    if effort and str(effort).strip() and result is None:
        logger.warning("Unknown reasoning_effort '%s', using default (medium)", effort)
    return result
```

`result is None` 有两种来源:「用户没配」和「用户配错了」。`if effort and str(effort).strip()` 这一层
就是把二者分开,只对后者告警。

---

*(下接 §2.5 退出路径与看门狗)*
