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

`cli.py:253 @ 863e313`(docstring 续)

```python
    Covers the variants emitted by reasoning models today: ``<think>``,
    ``<thinking>``, ``<reasoning>``, ``<REASONING_SCRATCHPAD>``, and
    ``<thought>`` (Gemma 4).  Must stay in sync with
    ``run_agent.py::_strip_think_blocks`` and the stream consumer's
    ``_OPEN_THINK_TAGS`` / ``_CLOSE_THINK_TAGS`` tuples.
```

值得注意的**不对称**:工具调用类标签用了 `\b[^>]*>` 允许带属性,推理标签却只匹配裸标签:

`cli.py:264 @ 863e313`(函数体节选)

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

而 `<function name="...">` 那条特意加了行首/句末边界锚,`cli.py:296 @ 863e313`(续):

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

---

### 2.5 退出路径 —— premise 3:到底是什么在挂

#### 2.5.1 模块级退出状态位

`cli.py:989 @ 863e313`

```python
_cleanup_done = False
```

`cli.py:994 @ 863e313`

```python
_single_query_finalize_attempted_session_ids: set[str | None] = set()
```

`cli.py:1002 @ 863e313`

```python
_tui_input_modes_active = False
```

第三个的注释交代了它为什么必须存在(而不是无脑复位终端):

`cli.py:998 @ 863e313`

```python
# Set True once the TUI's prompt_toolkit app starts (which enables focus
# reporting + mouse tracking). Gates the on-exit terminal reset so non-TUI
# one-shot CLI runs — which also register _run_cleanup via atexit — don't emit
# escape codes for modes they never enabled (#36823).
```

#### 2.5.2 `_arm_exit_watchdog`:两类挂点

premise 3 说「正常解释器关闭会挂」。代码给出的答案更精确——**是两类挂点,而且第二类才是主因**:

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

    The shared daemon pool (``tools.daemon_pool``) removes the main cause
    of (2); this watchdog is the backstop for both. It arms a daemon
    timer when ``_run_cleanup`` starts; if the process is still alive
    after ``timeout_s`` it flushes logging/stdio and calls ``os._exit(0)``.
    Daemon threads keep running through ``Py_FinalizeEx``'s thread joins,
    so the timer fires even when the main thread is stuck in teardown.

    Tune with ``HERMES_EXIT_WATCHDOG_S`` (seconds); ``0`` disables.
    """
```

第 2 类的技术细节被独立模块 `tools/daemon_pool.py` 交叉证实,它的模块 docstring 就是同一件事的展开:

`tools/daemon_pool.py:1 @ 863e313`

```python
"""Shared daemon-thread ThreadPoolExecutor.

Stdlib ``ThreadPoolExecutor`` workers are non-daemon AND are registered in
``concurrent.futures.thread._threads_queues``, whose atexit hook
(``_python_exit``) joins every worker unconditionally — even after
``shutdown(wait=False)``.  A single wedged worker (tool blocked on network
I/O, hung provider daemon, stuck subagent) therefore blocks interpreter
exit forever.  This is the root cause of multi-minute CLI exits on long
sessions: every abandoned concurrent-tool batch leaves workers that the
exit hook insists on joining.
```

**这条链条完整读下来是这样的**:agent 并发执行工具 → 用 stdlib `ThreadPoolExecutor` → 某个工具卡在
socket 上 → 用户 Ctrl+C,`shutdown(wait=False)` 看似放手 → 但 `concurrent.futures` 自己注册的
atexit 钩子 `_python_exit` **无条件 join 所有 worker** → 进程永远退不出去。
`DaemonThreadPoolExecutor` 从根上解决(worker 设 daemon + 跳过 `_threads_queues` 注册),
看门狗是**兜底而非主修**。

看门狗自身的实现有三个关键细节:

`cli.py:1091 @ 863e313` —— `0` 或负值即禁用:

```python
    if timeout_s <= 0:
        return
```

`cli.py:1095 @ 863e313` —— **pytest 下绝不武装**。这一条不写就是灾难:测试会直接调 `_run_cleanup()`,
30 秒后一个 `os._exit(0)` 会把 pytest worker 静默杀掉,表现成随机的「测试消失」:

```python
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
```

`cli.py:1119 @ 863e313` —— 最终动作是 `os._exit(0)`,绕过一切 atexit / finally:

```python
        os._exit(0)
```

之前先刷 logging 与 stdio,顺序是「日志 → stdout/stderr → 硬退」,否则最后那条 WARNING 自己就丢了。

#### 2.5.3 信号版看门狗:为什么要独立一个

`cli.py:1132 @ 863e313`

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
```

**事故经过复述**:用户关掉终端标签 → SHELL 发 SIGHUP → hermes 的信号处理器打算走优雅路径
(打断 agent、退出 prompt_toolkit app、走 finally 到 `_run_cleanup`)→ 但主线程停在一个不响应
unwind 的 syscall 里 → `_run_cleanup` **永远没被执行到** → 它内部武装的那个看门狗**也就永远没武装** →
进程带着 4% CPU 活了 47 分钟。修法:把兜底提前到**信号到达的那一刻**。

时限选择也有讲究:`cli.py:1168 @ 863e313`

```python
        _arm_exit_watchdog(timeout_s=base * 2)
```

2 倍是为了让「慢但在推进」的 `_run_cleanup`(它会武装自己更紧的计时器)不被外层兜底提前砍掉——
外层只在「cleanup 从未被抵达」时才赢。

docstring 里还明确否掉了一个看似更简单的方案:

`cli.py:1150 @ 863e313`(续)

```python
    Deliberately NOT armed at chat startup: the watchdog thread calls
    ``os._exit(0)`` unconditionally after its sleep, so arming without
    shutdown intent would hard-kill every session that outlives the timeout.
```

幂等由模块标志保证:`cli.py:1160 @ 863e313`

```python
    _signal_watchdog_armed = True
```

两处调用点:`cli.py:17649 @ 863e313`(交互模式信号处理器)与 `cli.py:18263 @ 863e313`(`-q` 单查询模式)。

```python
            _arm_exit_watchdog_on_shutdown_signal()
```

#### 2.5.4 `_run_cleanup`:清理顺序本身就是设计

`cli.py:1173 @ 863e313`

```python
def _run_cleanup(*, notify_session_finalize: bool = True):
    """Run resource cleanup exactly once."""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
```

紧接着**第一件事就是武装看门狗**(`cli.py:1183 @ 863e313`),因为后面每一步都可能卡:

```python
    _arm_exit_watchdog()
```

**第二件事是复位终端输入模式**(`cli.py:1185 @ 863e313`),理由写在注释里,值得整段抄:

```python
    # Reset terminal input modes first, before the slower resource teardown
    # below (MCP / browser / memory shutdown can take seconds). On Ctrl+C the
    # user's terminal becomes usable immediately, and a later step raising
    # can't skip the reset (#36823). No-op unless the TUI actually ran.
    _reset_terminal_input_modes_on_exit()
```

**这是一条通用的 harness 设计原则**:清理步骤要按「用户可感知度」而非「资源重要性」排序。
用户看得见的是终端还能不能用,MCP 连接有没有优雅关闭他根本不知道。

之后是一串**每步独立 try/except** 的资源释放:唤醒词 → 终端环境 → 异步委派 → 浏览器 → MCP →
辅助 LLM 客户端。其中 MCP 那步用了 `except BaseException`(而非 `Exception`),
`cli.py:1210 @ 863e313`:

```python
    try:
        from tools.mcp_tool import shutdown_mcp_servers
        shutdown_mcp_servers()
    except BaseException:
        pass
```

——`BaseException` 会连 `KeyboardInterrupt` / `SystemExit` 一起吞。在退出路径上这是**故意的**:
用户在关闭 MCP 期间又按了一次 Ctrl+C,不应该让后面的内存 provider 关闭被跳过。

辅助客户端那步的注释解释了一个奇怪的用户可见症状:

`cli.py:1215 @ 863e313`

```python
    # Close cached auxiliary LLM clients (sync + async) so that
    # AsyncHttpxClientWrapper.__del__ doesn't fire on a closed event loop
    # and trigger prompt_toolkit's "Press ENTER to continue..." handler.
```

最后是内存 provider 的会话收尾,这里有一段很细的取舍:

`cli.py:1234 @ 863e313`

```python
        if _active_agent_ref and hasattr(_active_agent_ref, 'shutdown_memory_provider'):
            # A /new shortly before exit leaves its end→switch boundary task
            # (old-session extraction, LLM-bound) queued on the memory
            # manager's serialized worker. shutdown_all()'s drain only waits
            # ~5s and cancels queued tasks, so give pending work a bounded
            # head start via the manager's own barrier — otherwise a
            # "/new then quit" silently drops the old session's extraction.
            # The 30s exit watchdog remains the hard backstop.
```

**事故复述**:用户 `/new` 开新会话,几秒后退出。`/new` 触发的「旧会话记忆抽取」是一个 LLM 调用,
排在记忆管理器的串行队列上。`shutdown_all()` 只 drain 5 秒就取消队列——旧会话的记忆**静默丢失**。
修法:先用 `flush_pending(timeout=10)` 给它一个有界的抢跑窗口。

`cli.py:1248 @ 863e313` 还交代了另一个坑:必须把 agent 自己的 transcript 传进去,否则
provider 的 `on_session_end` 看到空列表:

```python
            # Forward the agent's own transcript so memory providers'
            # ``on_session_end`` hooks see the real conversation instead of
            # an empty list (#15165). ``_session_messages`` is set on
            # ``AIAgent.__init__`` and refreshed every turn via
            # ``_persist_session``. Fall back to no-arg on test stubs /
            # partially-initialised agents where the attribute is missing.
```

#### 2.5.5 session finalize 的去重

单查询模式会在进程清理**之前**做一次一次性 finalize,让插件能在 agent 还挂着的时候看到会话边界。
如果这个窄窗口里来了信号,atexit 清理**不能再发一次**。去重用一个已尝试集合:

`cli.py:1272 @ 863e313`

```python
def _should_emit_cleanup_session_finalize(session_id: str | None) -> bool:
    if not _single_query_finalize_attempted_session_ids:
        return True
    if session_id is None:
        return False
    return session_id not in _single_query_finalize_attempted_session_ids
```

`cli.py:1333 @ 863e313` 用 `try/finally` 保证「无论发没发成功,都记为已尝试」:

```python
def _notify_single_query_session_finalize(cli, *, reason: str = "shutdown") -> None:
    agent = getattr(cli, "agent", None)
    session_id = getattr(agent, "session_id", None) or getattr(cli, "session_id", None)
    if session_id in _single_query_finalize_attempted_session_ids:
        return

    try:
        _notify_session_finalize(
            session_id=session_id,
            platform=getattr(agent, "platform", None) or "cli",
            reason=reason,
        )
    finally:
        _single_query_finalize_attempted_session_ids.add(session_id)
```

`cli.py:1349 @ 863e313` 的三段式很清楚:finalize → 清理(不再发 finalize)→ 释放会话租约:

```python
def _finalize_single_query(cli) -> None:
    """Close one-shot CLI resources before releasing the active session lease."""
    try:
        _notify_single_query_session_finalize(cli)
        _run_cleanup(notify_session_finalize=False)
    finally:
        cli._release_active_session()
```

#### 2.5.6 终端输入模式复位:一串「关掉一切」的转义序列

`cli.py:1358 @ 863e313`

```python
def _reset_terminal_input_modes_on_exit() -> None:
    """Best-effort: disable focus reporting + mouse tracking on TUI exit so they
    don't leak into the next shell session sharing the tab.

    prompt_toolkit restores these on a clean teardown, but Ctrl+C, SIGTERM /
    SIGHUP and crashes can bypass its unwind, leaving the modes enabled. The
    terminal then emits raw ``ESC[I`` / ``ESC[O`` focus events and fragmented
    SGR mouse reports as visible text in whatever runs next in the same tab
    (#36823).
```

**事故复述**:用户在 hermes TUI 里按 Ctrl+C,prompt_toolkit 的 unwind 被跳过 → 焦点上报和鼠标追踪
两个终端模式**还开着** → 用户在同一个标签里 `vim` 或跑别的命令,每次鼠标移动/切窗口,终端就往
stdin 里塞 `ESC[I` / SGR 鼠标报告 → 表现为**屏幕上莫名出现乱码字符**。

复位序列的构成:`cli.py:3590 @ 863e313`

```python
_TERMINAL_INPUT_MODE_RESET_SEQ = (
    "\x1b[?1006l"  # disable SGR mouse
    "\x1b[?1003l"  # disable any-motion tracking
    "\x1b[?1002l"  # disable button-motion tracking
    "\x1b[?1000l"  # disable click tracking
    "\x1b[?1004l"  # disable focus events
    "\x1b[?2004l"  # disable bracketed paste
    "\x1b[?1049l"  # leave alt screen (if stuck there)
    "\x1b[<u"      # pop kitty keyboard mode
    "\x1b[>4m"     # reset modifyOtherKeys
    "\x1b[0m"      # reset text attributes
    "\x1b[?25h"    # ensure cursor visible
)
```

复位目标的选择也很讲究——退出时 prompt_toolkit 自己的 output 已经拆了,所以走 `sys.stdout`;
但如果 stdout 被重定向走了,就退到 `/dev/tty`:

`cli.py:1386 @ 863e313`

```python
    try:
        stream = sys.stdout
        if stream is not None and stream.isatty():
            stream.write(_TERMINAL_INPUT_MODE_RESET_SEQ)
            stream.flush()
            return
    except Exception:
        pass
    try:
        with open("/dev/tty", "w", encoding="ascii") as tty:
            tty.write(_TERMINAL_INPUT_MODE_RESET_SEQ)
            tty.flush()
    except Exception:
        pass
```

写之前先清标志,防重入:`cli.py:1383 @ 863e313`

```python
    _tui_input_modes_active = False
```

docstring 还诚实地列出了覆盖不到的两条路径:

`cli.py:1368 @ 863e313`(续)

```python
    SIGTERM/SIGHUP. ``kill -9`` is uncatchable, and the kanban worker's
    ``os._exit(0)`` path bypasses ``atexit``; neither runs this — but both are
    non-TTY / non-TUI, so there is nothing to reset there.
```

#### 2.5.7 Termux 延迟启动

`cli.py:1011 @ 863e313`

```python
def _prepare_deferred_agent_startup() -> None:
    """Run Termux-deferred agent discovery before the first real agent turn."""
    global _deferred_agent_startup_done
    if _deferred_agent_startup_done:
        return
    if os.environ.get("HERMES_DEFER_AGENT_STARTUP") != "1":
        return
    _deferred_agent_startup_done = True
```

**这是「惰性导入」思路的极端版**:在 Termux(Android)上,插件发现、MCP 发现、shell hook 注册
这三件事全部从启动期推迟到**第一次真实 agent turn 之前**。手机 CPU 上这几步能占掉好几秒,
而用户可能只是想看一眼提示符。三步各自独立 try/except,失败只降级不阻断
(插件失败记 `warning`,MCP 与 hook 失败记 `debug`——严重度分级)。

注意第 1018 行**先置标志后干活**:并发第二个调用者会立刻返回,而不是等第一个做完。
对「best-effort 预热」这是对的(不会重复扫),但意味着**第二个调用者可能在发现还没完成时就开始 turn**。


---

### 2.6 git worktree 隔离 —— premise 2 的三处修正

#### 2.6.1 真实目的:代码注释说的是「并发不互撞」

premise 说这是「让 agent 改代码而不碰用户 checkout」。调用点的注释给的首要理由不是这个:

`cli.py:18111 @ 863e313`

```python
        # ── Git worktree isolation (#652) ──
        # Create an isolated worktree so this agent instance doesn't collide
        # with other agents working on the same repo.
```

**「不与同一个 repo 上的其他 agent 实例互撞」**——这是多 agent 并发场景的诉求(同一台机器上跑几个
hermes,或 kanban dispatcher 派发多个任务),而不是「保护用户的未提交改动」。这个区别很实在:
如果目的是保护用户 checkout,那么「用户自己的未提交改动」应该是首要保全对象;而实际的保全逻辑
(§2.6.4)保全的是**worktree 内的提交**,对**用户主 checkout 的状态一概不管**。

段落标题也是同一措辞,`cli.py:1403 @ 863e313`:

```python
# Git Worktree Isolation (#652)
```

#### 2.6.2 它确实碰用户 checkout:两处写入

**第一处**:worktree 就建在用户仓库里。

`cli.py:1631 @ 863e313`

```python
    worktrees_dir = Path(repo_root) / ".worktrees"
    worktrees_dir.mkdir(parents=True, exist_ok=True)
```

**第二处**:自动改写用户的 `.gitignore`。

`cli.py:1637 @ 863e313`

```python
    gitignore = Path(repo_root) / ".gitignore"
    _ignore_entry = ".worktrees/"
    try:
        # utf-8-sig: git files are UTF-8 and Notepad prepends a BOM, which
        # would glue to the first line and defeat the membership check below
        # (duplicating the entry); the locale default also breaks non-ASCII
        # patterns on Windows. The append below already writes UTF-8.
        existing = (
            gitignore.read_text(encoding="utf-8-sig", errors="replace")
            if gitignore.exists()
            else ""
        )
        if _ignore_entry not in existing.splitlines():
            with open(gitignore, "a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write(f"{_ignore_entry}\n")
```

**没有它会坏什么**:不加这行,`.worktrees/` 会出现在 `git status` 里,agent(和用户)会把整个
worktree 目录当成待提交的新文件。所以这个写入是必要的——但它意味着 `hermes -w` **会在用户的
版本控制文件里留下一行永久痕迹**,与 premise 里「不碰用户 checkout」的说法直接冲突。

`utf-8-sig` 的选择也值得记:Notepad 存的 `.gitignore` 带 BOM,BOM 会粘在第一行上,让
`_ignore_entry not in existing.splitlines()` 这条成员检查失效 → **每次启动都追加一行重复条目**。

#### 2.6.3 隔离靠 `TERMINAL_CWD`,不是 `os.chdir`

`cli.py:18125 @ 863e313`

```python
            wt_info = _setup_worktree(sync_base=_sync_base)
            if wt_info:
                _active_worktree = wt_info
                os.environ["TERMINAL_CWD"] = wt_info["path"]
                atexit.register(_cleanup_worktree, wt_info)
            else:
                # Worktree was explicitly requested but setup failed —
                # don't silently run without isolation.
                return
```

**关键点**:这里只设了一个环境变量,**没有 `os.chdir`**。进程 cwd 仍然是用户的 checkout。
隔离的传导路径是 `TERMINAL_CWD` → 各个工具各自读取:

- `tools/file_tools.py:152 @ 863e313`

```python
    """Resolve a path relative to TERMINAL_CWD (the worktree base directory)
```

- `tools/terminal_tool.py:1514 @ 863e313`

```python
    cwd = os.getenv("TERMINAL_CWD", default_cwd)
```

- `tools/code_execution_tool.py:1939 @ 863e313`

```python
    raw = os.environ.get("TERMINAL_CWD", "").strip()
```

也就是说:**隔离是约定式的,不是强制的**。任何直接用 `os.getcwd()` 或绝对路径的代码路径都会
落回用户 checkout。这也解释了 §3-2 那个缺陷为什么危险——只要 `TERMINAL_CWD` 被谁改回去,
隔离就无声地消失了,进程 cwd 甚至不需要变。

顺带记 `else` 那一支的态度:**显式要求了 worktree 但建失败,就直接 return,绝不降级运行**。
这是对的——静默地在用户主 checkout 上跑一个被授权「随便改代码」的 agent 是最坏结果。

TUI 路径(`hermes --tui -w`)走的是另一个调用点,同时设了两个变量:

`hermes_cli/main.py:2335 @ 863e313`

```python
        env["HERMES_CWD"] = wt_info["path"]
        env["TERMINAL_CWD"] = wt_info["path"]
```

#### 2.6.4 base ref 解析:一次 `hermes -w` 启动为什么要联网

`_resolve_worktree_base` 是这一簇里最有信息量的函数,它的 docstring 把问题演得很完整:

`cli.py:1469 @ 863e313`

```python
def _resolve_worktree_base(
    repo_root: str,
    fetch_timeout: float = 5,
    freshness_window: float = 300,
) -> tuple:
    """Resolve the freshest base ref to branch a new worktree from.

    The standalone clone's ``HEAD`` can lag the remote by hundreds of commits
    (the ``~/.hermes/hermes-agent`` clone is updated only by ``hermes update``,
    not on every session). Branching a worktree from that stale ``HEAD`` roots
    every new branch on an old base — so the PR diff GitHub computes against
    current ``main`` balloons with unrelated changes, and the agent has to
    discover the staleness via the pre-push gate and rebase. Branching from the
    freshly-fetched remote tip instead means the worktree starts current.
```

**事故复述**:hermes 自己的独立 clone(`~/.hermes/hermes-agent`)只在 `hermes update` 时更新。
用户一周没升级 → 本地 HEAD 落后 remote 几百个 commit → `hermes -w` 从这个 HEAD 开分支 →
agent 干完活开 PR → GitHub 拿 PR 分支和**当前 main** 算 diff → 差异里混进几百个**别人的、无关的**
提交 → PR 无法审阅。agent 只能靠 pre-push 门禁发现「base 陈旧」然后 rebase,白干一轮。

三级降级策略写得很清楚:

`cli.py:1484 @ 863e313`(docstring 续)

```python
    Strategy (each step falls back to the next on failure):
      1. If the current branch tracks an upstream, refresh and use that
         upstream ref — so a deliberate feature-branch worktree tracks its own
         remote, not the default branch.
      2. Else refresh the remote's default branch (``origin/HEAD`` → e.g.
         ``origin/main``) and use it.
      3. Else fall back to ``HEAD`` (offline, no remote, or detached) — the
         old behavior, never worse than before.
```

但这个修法**引入了新的启动延迟**,于是又加了两道成本控制,docstring 里连原始症状都留了:

`cli.py:1493 @ 863e313`(docstring 续)

```python
    "Refresh" is deliberately cheap on the startup path (the fetch here used
    to stall ``hermes -w`` launches for 30-60s on flaky smart-HTTP
    connections):

    - The fetch is SKIPPED entirely when the repo's ``FETCH_HEAD`` is younger
      than *freshness_window* seconds — a base fetched moments ago cannot have
      meaningfully moved, so repeated launches don't re-pay a network round
      trip.
    - The fetch is capped at *fetch_timeout* seconds. On timeout or failure we
      fall back to the locally-known remote-tracking ref (labelled "cached")
      instead of cascading into a second fetch attempt. Genuine staleness is
      backstopped by the pre-push stale-base gate.
```

**「一次修复引入的延迟,用两道成本控制+一道下游门禁兜底」——这是很成熟的工程节奏**:
不追求 base 绝对新鲜(那要付网络代价),只追求「便宜地大概率新鲜」,真正的正确性由
pre-push 门禁保证。

新鲜度判定读的是 `FETCH_HEAD` 的 mtime:

`cli.py:1528 @ 863e313`

```python
    def _fetch_head_age() -> Optional[float]:
        """Seconds since the last fetch in this repo, or None if unknown."""
```

`cli.py:1544 @ 863e313` 是核心:

```python
    def _refresh(remote: str, branch: str, ref: str) -> tuple:
        """Return (ref, label) after a cheap best-effort refresh of *ref*.

        Never raises, never fetches twice, never blocks longer than
        *fetch_timeout*.
        """
        age = _fetch_head_age()
        if age is not None and age < freshness_window and _ref_exists(ref):
            return ref, f"{ref} (fetched {int(age)}s ago)"
        try:
            fetched = _git(["fetch", remote, branch], timeout=fetch_timeout)
            if fetched.returncode == 0:
                return ref, f"{ref} (fetched)"
            reason = "fetch failed"
        except subprocess.TimeoutExpired:
            reason = f"fetch timed out after {fetch_timeout:g}s"
        except Exception as e:
            reason = f"fetch error: {e}"
        if _ref_exists(ref):
            logger.debug("worktree base: %s — using cached %s", reason, ref)
            return ref, f"{ref} (cached — {reason})"
        return "HEAD", f"HEAD (local — {reason}, no cached {ref})"
```

注意它**返回的是 `(ref, label)` 二元组**,label 是给用户看的人话理由。这个小设计让 banner 能打出
`Base: origin/main (cached — fetch timed out after 5s)` 这种**自解释**的行,用户不需要猜为什么慢。

`_git` 子进程封装里有两个细节是本簇其他 git 调用**都没做**的(见 §3-7):

`cli.py:1514 @ 863e313`

```python
    def _git(args, timeout: float = 20):
        return subprocess.run(
            ["git", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, cwd=repo_root,
            stdin=subprocess.DEVNULL,
            env=noninteractive_git_env(),
        )
```

`stdin=subprocess.DEVNULL` + `noninteractive_git_env()` —— 前者防止 git 从 CLI 的 TTY 抢键盘输入,
后者关掉凭据交互提示。缺了这两样,一次需要认证的 fetch 会**在 prompt_toolkit 正在管着终端时弹出
密码提示**,结果是两个程序抢同一个 tty。

远端默认分支的解析有个防呆:

`cli.py:1588 @ 863e313`

```python
            show = _git(["remote", "show", "origin"], timeout=max(fetch_timeout, 5))
            for line in show.stdout.splitlines():
                line = line.strip()
                if line.startswith("HEAD branch:"):
                    _branch = line.split(":", 1)[1].strip()
                    # A remote with no default branch reports "(unknown)";
                    # don't construct a bogus "origin/(unknown)" ref from it.
                    if _branch and _branch != "(unknown)":
                        default_ref = "origin/" + _branch
                    break
```

#### 2.6.5 `_setup_worktree`:创建、include 拷贝、加锁

`cli.py:1608 @ 863e313`

```python
def _setup_worktree(repo_root: str = None, sync_base: bool = True) -> Optional[Dict[str, str]]:
    """Create an isolated git worktree for this CLI session.

    Returns a dict with worktree metadata on success, None on failure.
    The dict contains: path, branch, repo_root.
```

命名:`hermes-<8位hex>` 目录 + `hermes/hermes-<8位hex>` 分支。

`cli.py:1627 @ 863e313`

```python
    short_id = uuid.uuid4().hex[:8]
    wt_name = f"hermes-{short_id}"
    branch_name = f"hermes/{wt_name}"
```

这个命名不是随意的——`hermes-` 前缀是**剪枝器分档的依据**(§2.7.2),`hermes/` 分支前缀是
**孤儿分支剪枝的匹配模式**(§2.7.3)。

建树失败时有一次降级重试:

`cli.py:1671 @ 863e313`

```python
        if result.returncode != 0:
            # If branching from the resolved remote ref failed for any reason
            # (e.g. a partial fetch left the ref unusable), retry from local
            # HEAD so worktree creation never hard-fails on a sync hiccup.
            if base_ref != "HEAD":
```

**`.worktreeinclude`**:worktree 是干净的 checkout,`.env`、`node_modules` 之类被 gitignore 的
东西不会在里面,agent 会当场缺依赖。这个机制把它们带过去:

`cli.py:1692 @ 863e313`

```python
    # Copy files listed in .worktreeinclude (gitignored files the agent needs)
    include_file = Path(repo_root) / ".worktreeinclude"
```

安全检查是**双向**的,源和目标都要在各自根内:

`cli.py:1720 @ 863e313`

```python
                if not _path_is_within_root(src_resolved, repo_root_resolved):
                    logger.warning("Skipping .worktreeinclude entry outside repo root: %s", entry)
                    continue
                if not _path_is_within_root(dst_resolved, wt_path_resolved):
                    logger.warning("Skipping .worktreeinclude entry that escapes worktree: %s", entry)
                    continue
```

判定函数本身极简(`cli.py:1460 @ 863e313`):

```python
def _path_is_within_root(path: Path, root: Path) -> bool:
    """Return True when a resolved path stays within the expected root."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
```

**没有它会坏什么**:`.worktreeinclude` 是仓库里的文件,内容可被 PR 修改。一行 `../../../.ssh/id_rsa`
就能让 hermes 把用户私钥拷进一个 agent 可读可提交的目录。这是**把不可信仓库内容当路径用**的经典面。

目录用 symlink(省盘、快),但 Windows 上 symlink 需要开发者模式或提权,于是有 copytree 兜底:

`cli.py:1729 @ 863e313`

```python
                elif src.is_dir():
                    # Symlink directories (faster, saves disk).  On Windows,
                    # symlink creation requires Developer Mode or elevation,
                    # and fails with OSError otherwise — fall back to a
                    # recursive copy so the worktree is still usable.  The
                    # copy is slower and uses disk, but it doesn't require
                    # admin and matches the Linux/macOS symlink outcome
                    # functionally.
```

注意非 Windows 分支是 `raise` 而不是吞掉——POSIX 上 symlink 失败是真异常,应该冒泡到外层的
debug 日志,而不是静默降级成拷贝。

`cli.py:1761 @ 863e313`

```python
                            else:
                                raise
```

**加锁**:用 git 原生的 worktree lock,reason 里带 pid:

`cli.py:1768 @ 863e313`

```python
    try:
        subprocess.run(
            ["git", "worktree", "lock", "--reason", f"hermes pid={os.getpid()}", str(wt_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, cwd=repo_root,
        )
        logger.debug("Worktree locked: %s (pid=%s)", wt_path, os.getpid())
    except Exception as e:
        logger.debug("git worktree lock failed (non-fatal): %s", e)
```

**这是个漂亮的设计**:锁不是 hermes 自己发明的文件锁,而是 **git 自己认识的锁**——所以
`git worktree remove` 会尊重它,别的 hermes 进程也能通过 `git worktree list --porcelain` 读到,
而 reason 字段被当成一个**廉价的所有权元数据槽**塞了 pid 进去。锁失败只记 debug,不阻断会话。

#### 2.6.6 保全判据:脏、未推送、已合入

三个判据函数的**失败方向**是这一簇最重要的设计决策:

`cli.py:1822 @ 863e313` —— 脏判定,**失败偏保守(返回 True = 保留)**:

```python
def _worktree_is_dirty(worktree_path: str, timeout: int = 10) -> bool:
    """Return whether a worktree has uncommitted changes (staged, unstaged, or
    untracked).

    Fails SAFE: on any error returns True so callers do not delete a worktree
    whose state they cannot determine.
    """
```

`cli.py:1791 @ 863e313` —— 未推送判定,注意它的「无 remote 即视为无未推送」:

```python
def _worktree_has_unpushed_commits(worktree_path: str, timeout: int = 10) -> bool:
    """Return whether a worktree has commits not reachable from any remote branch.

    ``git log HEAD --not --remotes`` compares against remote-tracking refs under
    ``refs/remotes/*``. If a repo has no remote-tracking refs yet, there is no
    usable remote baseline to compare against, so treat it as having no
    "unpushed" commits.
    """
```

`cli.py:1808 @ 863e313`

```python
        if not remote_refs.stdout.strip():
            return False
```

这一行就是 §3-1 那个数据丢失缺陷的源头。

`cli.py:1900 @ 863e313` —— patch 等价判定,解决「squash merge 之后本地提交永远够不着 remote」的漏洞:

```python
def _worktree_commits_all_merged_upstream(
    worktree_path: str,
    timeout: int = 30,
    max_ahead: int = 20,
    cache: Optional[Dict[str, bool]] = None,
) -> bool:
    """Return whether every local-only commit is patch-equivalent to a commit
    already on the default upstream branch.

    The dominant ``.worktrees/`` leak: a branch is pushed, its PR is
    squash-merged (or cherry-picked), and the remote branch is deleted. The
    local commits are then unreachable from ``refs/remotes/*`` forever, so the
    unpushed-commits guard preserves the worktree indefinitely even though its
    content is fully merged. ``git cherry`` detects patch-equivalence, letting
    the pruner reap these.
```

**事故复述**:agent 建 worktree、提交、推分支、开 PR。维护者 **squash merge** 并删掉远端分支。
本地那几个原始提交现在**永远**不可能从 `refs/remotes/*` 到达 → 「有未推送提交」判定恒为真 →
worktree 永远不被回收 → `.worktrees/` 里堆几十个已合入的死树,占几十 GB。
`git cherry` 用 patch-id(而非 sha)比较,识别出「内容已在上游」。

它的缓存设计是本簇最讲究的一段:

`cli.py:1920 @ 863e313`(docstring 续)

```python
    ``git cherry`` diff-hashes every commit in the range, which on a large repo
    costs ~0.2-1.0s per worktree — and a tree preserved for unpushed work is
    re-tested on *every* startup, forever, always reaching the same answer. When
    *cache* is provided, the verdict is memoized against
    ``(base_sha, head_sha, max_ahead)``: the exact inputs ``git cherry``
    consumes. A cache hit is therefore identical to recomputation by
    construction — if either ref moves the key changes and the real git call
    runs again.
```

**「cache key = 被缓存计算的完整输入集」——这是缓存正确性的最强论证形式**:不需要失效策略,
因为输入变了 key 就变了。实现:

`cli.py:1950 @ 863e313`

```python
        cache_key = None
        if cache is not None:
            revs = subprocess.run(
                ["git", "rev-parse", f"{base}^{{commit}}", "HEAD^{commit}"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, cwd=worktree_path,
            )
            if revs.returncode == 0:
                shas = revs.stdout.split()
                if len(shas) == 2:
                    cache_key = f"{shas[0]}..{shas[1]}:{max_ahead}"
                    if cache_key in cache:
                        return cache[cache_key]
```

`git cherry` 输出的读法:

`cli.py:1986 @ 863e313`

```python
        lines = [ln for ln in cherry.stdout.splitlines() if ln.strip()]
        # "-" = patch-equivalent commit exists upstream; "+" = unique local work
        return _memo(bool(lines) and all(ln.startswith("-") for ln in lines))
```

缓存的落盘是原子的、有界的:

`cli.py:1843 @ 863e313`

```python
# Upper bound on retained `git cherry` verdict entries (see
# _save_worktree_merge_cache). Each entry is ~90 bytes, so this caps the cache
# near 90 KB even on a repo that churns thousands of worktree branches.
_WORKTREE_MERGE_CACHE_MAX = 1000
```

`cli.py:1854 @ 863e313` —— 载入时**只接受布尔值**,防止手改/半写的文件把非布尔注进判定:

```python
def _load_worktree_merge_cache() -> Dict[str, bool]:
    """Load the ``git cherry`` verdict cache. Missing/corrupt cache = empty."""
```

`cli.py:1867 @ 863e313`

```python
    # Only keep well-formed bool verdicts — a hand-edited or partially written
    # cache must never inject a non-bool into the prune decision.
    return {k: v for k, v in entries.items() if isinstance(v, bool)}
```

`cli.py:1885 @ 863e313` —— 临时文件名带 pid,避免两个 hermes 同时写互踩:

```python
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
```

缓存路径用的是**运行时** `get_hermes_home()`(与 §3-4 的 `_hermes_home` 快照形成对比):

`cli.py:1849 @ 863e313`

```python
def _worktree_merge_cache_path() -> Path:
    """Path of the patch-equivalence verdict cache (profile-aware)."""
    return get_hermes_home() / "cache" / "worktree_merge_verdicts.json"
```

#### 2.6.7 锁活性三态

`cli.py:1993 @ 863e313`

```python
def _worktree_lock_is_live(repo_root: str, worktree_path: str, timeout: int = 10):
    """Classify a worktree's git lock as live, dead, or absent.

    ``hermes -w`` locks each worktree with reason ``hermes pid=<pid>`` so a
    concurrent hermes process' startup prune leaves an in-use worktree alone.
    But a *crashed* session leaves the lock behind forever, and
    ``git worktree remove --force`` (single ``-f``) refuses to remove a locked
    worktree — so dead-locked worktrees accumulate indefinitely. This lets the
    pruner tell the two apart:

    - ``"live"``  — locked and the owning pid is still running (skip it).
    - ``"dead"``  — locked but the owning pid is gone, or the reason isn't a
                    parseable hermes lock (safe to unlock + reap).
    - ``None``    — not locked at all.

    Fails SAFE toward ``"live"``: if git can't be queried at all we cannot
    prove the worktree is safe to touch, so we report it as live.
    """
```

**这是「锁 + 心跳」的最省事替代方案**:不需要心跳文件、不需要租约续期,直接把 pid 写进锁 reason,
清理时问一句 `_pid_exists(pid)`。代价是 pid 会被复用(§5 移交)。

解析用正则从 reason 里抠 pid:

`cli.py:2032 @ 863e313`

```python
        elif line == "locked" or line.startswith("locked "):
            if current != target:
                continue
            reason = line[len("locked"):].strip()
            m = re.search(r"hermes pid=(\d+)", reason)
            if not m:
                # Locked by something we don't recognize as a hermes session
                # (or lock reason unavailable). Treat as dead — a foreign lock
                # on a hermes -w worktree is almost certainly a leftover, and
                # the age/dirty/unpushed gates already ran before we got here.
                return "dead"
```

自己的 pid 直接判 live(`cli.py:2044 @ 863e313`):

```python
            if pid == os.getpid():
                return "live"
```

存活探测复用了 gateway 的实现,而不是自己写一份:

`cli.py:2047 @ 863e313`

```python
                from gateway.status import _pid_exists
                return "live" if _pid_exists(pid) else "dead"
```

#### 2.6.8 `_cleanup_worktree`:保全条件只有一条

`cli.py:2055 @ 863e313`

```python
def _cleanup_worktree(info: Dict[str, str] = None) -> None:
    """Remove a worktree and its branch on exit.

    Preserves the worktree only if it has unpushed commits (real work
    that hasn't been pushed to any remote).  Uncommitted changes alone
    (untracked files, test artifacts) are not enough to keep it — agent
    work lives in commits/PRs, not the working tree.
    """
```

**这是一条明确的产品判断**:「agent 的成果在 commit / PR 里,不在工作区里」。所以未提交的改动
(未跟踪文件、测试产物)不构成保留理由。

`cli.py:2077 @ 863e313`

```python
    has_unpushed = _worktree_has_unpushed_commits(wt_path, timeout=10)

    if has_unpushed:
        print(f"\n\033[33m⚠ Worktree has unpushed commits, keeping: {wt_path}\033[0m")
        print(f"  To clean up manually: git worktree remove --force {wt_path}")
        _active_worktree = None
        return
```

注意保留时**打印了手工清理命令**——这是对的,不然用户面对一个 hermes 留下的目录不知道怎么处理。

删除顺序是「先解锁、再删树、最后删分支」,每步独立 try:

`cli.py:2085 @ 863e313`

```python
    # Remove worktree (even if working tree is dirty — uncommitted
    # changes without unpushed commits are just artifacts)
    # Unlock first so `git worktree remove` isn't blocked by the lock we
    # placed at creation time.  Fail-soft — never block cleanup.
```

`cli.py:2098 @ 863e313`

```python
        subprocess.run(
            ["git", "worktree", "remove", wt_path, "--force"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, cwd=repo_root,
        )
```

`cli.py:2107 @ 863e313`

```python
        subprocess.run(
            ["git", "branch", "-D", branch],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, cwd=repo_root,
        )
```

**注意 `-D` 是强制删除**(而不是 `-d` 的「只删已合入的」)。在有 remote 的正常情况下,前面的
`has_unpushed` 已经确认过内容都在 remote 上,`-D` 是安全的;在无 remote 的情况下,
这两句合起来就是 §3-1 的数据丢失。


---

### 2.7 启动期自动维护与陈旧剪枝

#### 2.7.1 state.db / checkpoint 的自动维护

两个函数形状一样:读配置 → 默认关闭 → 委托给真正的实现 → **绝不抛异常**。

`cli.py:2118 @ 863e313`

```python
def _run_state_db_auto_maintenance(session_db) -> None:
    """Call ``SessionDB.maybe_auto_prune_and_vacuum`` using current config.

    Reads the ``sessions:`` section from config.yaml via
    :func:`hermes_cli.config.load_config` (the authoritative loader that
    deep-merges DEFAULT_CONFIG, so unmigrated configs still get default
    values). Honours ``auto_prune`` / ``retention_days`` /
    ``vacuum_after_prune`` / ``min_vacuum_interval_days`` /
    ``min_interval_hours``, and delegates to the DB. Never raises —
    maintenance must never block interactive startup.
    """
```

注意它**不用模块级 `CLI_CONFIG`,而是重新调 `hermes_cli.config.load_config()`**,理由写在括号里:
那才是会 deep-merge `DEFAULT_CONFIG` 的权威加载器,老配置文件里缺的键才能拿到默认值。

里面挂了两个**一次性迁移**,用 DB 里的 meta 键做幂等标记:

`cli.py:2136 @ 863e313`

```python
        # One-time prune of empty TUI ghost sessions.
        try:
            if not session_db.get_meta("ghost_session_prune_v1"):
                pruned = session_db.prune_empty_ghost_sessions(
                    sessions_dir=_hermes_home_maint / "sessions"
                )
                session_db.set_meta("ghost_session_prune_v1", "1")
```

`cli.py:2148 @ 863e313`

```python
        # One-time finalize of orphaned compression continuations (#20001).
        try:
            if not session_db.get_meta("orphaned_compression_finalize_v1"):
                finalized = session_db.finalize_orphaned_compression_sessions()
                session_db.set_meta("orphaned_compression_finalize_v1", "1")
```

**`<名字>_v<N>` 这个 meta 键命名是可迁移的模式**:一次性数据修复挂在启动路径上,用带版本号的
标记键做幂等;将来需要重跑就 bump 到 `_v2`。

归档与剪枝的**顺序**是刻意的:

`cli.py:2162 @ 863e313`

```python
        # Auto-archive (soft-hide stale sessions) is independent of the
        # destructive auto_prune sweep — run it first, before prune's early
        # return, so enabling one doesn't require the other.
        if cfg.get("auto_archive", False):
```

——归档(软隐藏)必须放在 `if not cfg.get("auto_prune"): return` 之前,否则用户想开归档就被迫
也开破坏性剪枝。

checkpoint 那边有一条**明确拒绝执行配置项**的决定,理由值得整段抄:

`cli.py:2198 @ 863e313`

```python
        # delete_orphans is intentionally never honoured here: a missing
        # workdir at startup is ambiguous (deleted project vs. an unmounted
        # external volume / network share / VPN not yet up) and this sweep
        # runs unattended. Orphan cleanup is only ever done via the explicit
        # `hermes checkpoints prune` command, which the user has to invoke.
        maybe_auto_prune_checkpoints(
            retention_days=int(cfg.get("retention_days", 7)),
            min_interval_hours=int(cfg.get("min_interval_hours", 24)),
            delete_orphans=False,
            max_total_size_mb=int(cfg.get("max_total_size_mb", 500)),
        )
```

**「无人值守的清扫不能对歧义信号做破坏性动作」**——workdir 不见了,可能是项目删了,也可能是
外挂盘没挂、VPN 没连。破坏性判断留给用户手动触发的命令。这是本仓库里少见的
「配置项存在,但在这个上下文里被硬编码为 False」的写法,而且写清了理由。

#### 2.7.2 `_prune_stale_worktrees`:三相流水线

这是本段最长、最讲究的一个函数。它的问题背景是**性能**:

`cli.py:2250 @ 863e313`

```python
    Performance: this runs on the startup path of every ``hermes -w`` session,
    and each candidate tree costs several git subprocesses (the ``git cherry``
    patch-equivalence probe dominates at ~0.2-1.0s on a large repo). With
    dozens of accumulated worktrees the serial version added ~11-18s of latency
    before the banner. Two changes keep the decisions byte-identical while
    removing nearly all of that:

    1. The read-only classification of each tree (dirty / unpushed / merged /
       lock state) is independent per tree, so it runs on a thread pool. Only
       the mutating phase (unlock, remove, branch -D) stays serial and ordered.
    2. ``git cherry`` verdicts are memoized on disk keyed by the exact
       ``(base_sha, head_sha)`` range they were computed from, so a tree
       preserved for unpushed work is not re-diff-hashed on every subsequent
       startup.
```

**「11-18 秒的启动前延迟」是用户直接能感知的**,而修法的自我约束是 "keep the decisions
byte-identical" —— 并行化不改变任何判定,只改变执行方式。这是重构并发化时应有的承诺。

**相 1:纯 stat 的年龄过滤**(不起子进程):

`cli.py:2281 @ 863e313`

```python
    # ── Phase 1: age filter (no subprocesses) ───────────────────────────────
    # Cheap stat-only pass so the thread pool below is sized to the trees that
    # actually need git work, not to everything on disk.
```

kanban 任务树被显式排除(它有自己的 gc):

`cli.py:2277 @ 863e313`

```python
    # Kanban task worktrees (<repo>/.worktrees/t_<hex>) have their own
    # dispatcher-driven lifecycle (hermes kanban gc) — never touch them here.
    kanban_re = re.compile(r"^t_[0-9a-f]+$")
```

分档:`hermes-` 前缀 = 临时刮擦树,走默认时间线;其它名字 = 人工建的救援/评审通道,给 3 倍宽限:

`cli.py:2289 @ 863e313`

```python
        # Scratch trees (hermes-*) age out on the default schedule; named
        # trees (salvage/review lanes someone created deliberately) get 3x.
        scratch = entry.name.startswith("hermes-")
        tier_hours = max_age_hours if scratch else max_age_hours * 3
        soft_cutoff = now - (tier_hours * 3600)
        hard_cutoff = now - (tier_hours * 3 * 3600)
```

**相 2:并行只读分类**。安全性论证写在注释里:

`cli.py:2309 @ 863e313`

```python
    # ── Phase 2: classify in parallel (read-only git queries) ───────────────
    # Every check here is a read-only git query against a distinct worktree, so
    # they are safe to run concurrently (git takes no repo-wide lock for these,
    # and each has its own index). Verdicts are collected and applied serially
    # below so removal order and log output stay deterministic.
```

判定顺序是**先脏、再未推送(带 squash-merge 逃生口)、最后锁活性**:

`cli.py:2318 @ 863e313`

```python
    def _classify(item):
        entry, mtime, force = item
        # Never delete real work, regardless of age or tier. Uncommitted
        # changes and unpushed commits may be a crashed session's in-flight
        # work; only clean, fully-merged/pushed trees (the scratch trees that
        # actually cause .worktrees/ bloat) are ever reaped.
        if _worktree_is_dirty(str(entry), timeout=5):
            return (entry, mtime, force, "dirty", None)
```

共享缓存的并发处理用了「快照 → 无锁计算 → 回写合并」:

`cli.py:2330 @ 863e313`

```python
            with cache_lock:
                snapshot = dict(merge_cache)
            merged = _worktree_commits_all_merged_upstream(
                str(entry), timeout=30, cache=snapshot
            )
            with cache_lock:
                merge_cache.update(snapshot)
```

**这是「把锁的持有时间压到最短」的标准写法**:锁只在拷贝/合并时持有,那个 0.2–1.0 秒的
`git cherry` 在锁外跑。因为 key 是内容寻址的(sha 对),两个线程算出同一 key 的结果必然相同,
合并冲突无害。

线程池上界的选择带了理由:

`cli.py:2350 @ 863e313`

```python
    # Bounded pool: enough to hide git's per-process startup latency without
    # spawning dozens of concurrent git processes on a small machine.
    workers = max(1, min(8, (os.cpu_count() or 4), len(candidates)))
```

池本身失败还有串行兜底:

`cli.py:2361 @ 863e313`

```python
    except Exception as e:
        # Never let a pool failure block startup — fall back to serial.
        logger.debug("Parallel worktree classification failed (%s); serial", e)
        verdicts = [_classify(c) for c in candidates]
```

只在缓存**确实变大**时才落盘,避免每次启动都写一次文件:

`cli.py:2366 @ 863e313`

```python
    if len(merge_cache) != cache_size_before:
        _save_worktree_merge_cache(merge_cache)
```

**相 3:串行变更**。分支删除被门控在「树删成功」之后:

`cli.py:2404 @ 863e313`

```python
            if remove_result.returncode != 0:
                # Removal failed — keep the branch so any commits stay
                # reachable rather than orphaning it.
                logger.debug(
                    "Failed to remove worktree %s: %s",
                    entry.name, remove_result.stderr.strip(),
                )
                continue
```

**这条门控很关键**:如果树删失败而分支照删,那些提交就只剩 reflog 可达,等于半个数据丢失。

最后是保全可见性——被保留且超过 7 天的树汇总成**一条** WARNING:

`cli.py:2421 @ 863e313`

```python
    if preserved_stale:
        logger.warning(
            "Preserving %d worktree(s) older than 7 days with unmerged work "
            "(push or remove them to reclaim disk): %s",
            len(preserved_stale), ", ".join(sorted(preserved_stale)),
        )
```

**「保守策略必须配可见性」**:一个永远只保留、从不删除的规则,如果不告诉用户「我在替你留着这些」,
最终结果就是磁盘被悄悄吃满。合并成一条日志而非每树一条,是为了不刷屏。

#### 2.7.3 孤儿分支剪枝

`cli.py:2431 @ 863e313`

```python
def _prune_orphaned_branches(repo_root: str) -> None:
    """Delete local ``hermes/hermes-*`` and ``pr-*`` branches with no worktree.

    These are auto-generated by ``hermes -w`` sessions and PR review
    workflows respectively.  Once their worktree is gone they serve no
    purpose and just accumulate.
    """
```

保护集合是「所有被 worktree 占用的分支 + 当前分支 + `main`」:

`cli.py:2475 @ 863e313`

```python
    active_branches.add("main")
```

匹配用**严格前缀**,不是通配:

`cli.py:2477 @ 863e313`

```python
    orphaned = [
        b for b in all_branches
        if b not in active_branches
        and (b.startswith("hermes/hermes-") or b.startswith("pr-"))
    ]
```

注意是 `hermes/hermes-`(双段)而不是 `hermes/`,所以用户手工建的 `hermes/my-feature` 不会被删。

批量删除按 50 一批,避免命令行过长:

`cli.py:2487 @ 863e313`

```python
    for i in range(0, len(orphaned), 50):
```

无法确定活跃分支时直接 bail(不猜):

`cli.py:2461 @ 863e313`

```python
    except Exception:
        return  # Can't determine active branches — bail
```

---

### 2.8 明暗终端与皮肤取色

#### 2.8.1 为什么需要明暗检测

Hermes 的配色是按深色终端调的(金色 `#FFD700`、奶油 `#FFF8DC`)。放到浅色 Terminal.app 上,
奶油色文字**在奶油色背景上等于不可见**。

`cli.py:2539 @ 863e313`

```python
# ────────────────────────────────────────────────────────────────────────
# Light/dark terminal mode detection.
#
# Mirrors ui-tui/src/theme.ts detectLightMode().  Used to decide whether
# to remap "near-white" skin colors (e.g. #FFF8DC banner_text, #B8860B
# banner_dim) to darker equivalents that are readable on a light
# Terminal.app / iTerm2 background.
#
# Detection priority:
#   1. HERMES_LIGHT / HERMES_TUI_LIGHT env (true/false) — explicit override
#   2. HERMES_TUI_THEME=light|dark — explicit theme
#   3. HERMES_TUI_BACKGROUND=#RRGGBB — explicit bg hint
#   4. COLORFGBG env (set by xterm/Konsole/urxvt) — bg slot 7/15 = light
#   5. OSC 11 query (\x1b]11;?\x1b\\) — ask the terminal directly
#   6. Default: assume dark (matches the legacy Hermes assumption)
#
# Cached after first call so we don't query the terminal repeatedly.
```

**六级优先级的排布是有原则的**:显式覆盖 > 显式主题 > 显式颜色 > 环境暗示 > **主动探测** > 默认。
主动探测排在倒数第二,因为它是唯一有副作用(往终端写字节、读回复)的手段。

`cli.py:2559 @ 863e313` 的空集合很有意思——第 6 级 TERM_PROGRAM 白名单被清空了:

```python
_LIGHT_DEFAULT_TERM_PROGRAMS = frozenset()  # Apple_Terminal doesn't reliably indicate; require explicit
```

也就是说 `TERM_PROGRAM=Apple_Terminal` **曾经**被当成浅色信号,后来发现不可靠,于是保留代码
路径但清空数据。这比删掉整段更好——将来有可靠信号时只加一个字符串。

#### 2.8.2 OSC 11 探测:一个带 tty 竞态的机制

`cli.py:2576 @ 863e313`

```python
def _query_osc11_background() -> str | None:
    """Ask the terminal for its background color via OSC 11.

    Most modern terminals reply with \x1b]11;rgb:RRRR/GGGG/BBBB\x1b\\
    within a few ms.  We wait up to 100ms total before giving up.
    Returns "#RRGGBB" or None on timeout / non-tty.

    Skipped over SSH: the round-trip routinely exceeds our 100ms budget, so a
    late reply lands after prompt_toolkit has grabbed the tty — its payload
    leaks in as typed text and the BEL terminator reads as Ctrl+G (open
    editor), trapping the user in a stray editor. Remote sessions fall back to
    COLORFGBG / env hints / the dark default instead.
    """
```

**事故复述**:SSH 会话里,hermes 启动时问终端「你背景什么色?」,但 100ms 预算不够跨网往返 →
放弃等待 → prompt_toolkit 接管 tty → **终端的回复这时才到**,变成用户「输入」的乱码;更糟的是
回复的终止符 BEL(`\x07`)在 prompt_toolkit 里就是 **Ctrl+G = 打开外部编辑器** → 用户莫名其妙
被丢进一个编辑器里。修法:SSH 下整个跳过。

`cli.py:2589 @ 863e313`

```python
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return None
    if any(os.environ.get(v) for v in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")):
        return None
```

即便在本地,也有一道兜底:恢复终端属性时用 `TCSAFLUSH` 把没读完的回复冲掉。

`cli.py:2640 @ 863e313`

```python
        # TCSAFLUSH discards any unread input as it restores the original
        # attributes — scrubs a slow/partial OSC 11 reply out of the tty
        # buffer before prompt_toolkit can read it as keystrokes.
        try:
            termios.tcsetattr(fd, termios.TCSAFLUSH, old)
        except Exception:
            pass
```

回复里的每个颜色分量是 1–4 位十六进制,需要归一化到 8 bit:

`cli.py:2632 @ 863e313`

```python
        def norm(h: bytes) -> int:
            v = int(h, 16)
            # Scale to 0-255 based on hex length
            bits = len(h) * 4
            return (v * 255) // ((1 << bits) - 1) if bits else 0
```

亮度判据用 Rec.709 luma,阈值 0.5:

`cli.py:2562 @ 863e313`

```python
def _luminance_from_hex(hex_str: str) -> float | None:
```

`cli.py:2572 @ 863e313`

```python
    # Rec.709 luma
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
```

#### 2.8.3 重映射表:只映射「独立前景色」

`cli.py:2716 @ 863e313`

```python
# IMPORTANT: only remap colors that are used as STANDALONE foregrounds
# on the terminal's background.  Don't remap colors that are paired
# with a dark bg (e.g. status bar text on bg:#1a1a2e) — those would
# become invisible the OTHER direction (dark gray on dark navy).
_LIGHT_MODE_REMAP: dict[str, str] = {
```

`cli.py:2734 @ 863e313` 明确列了被跳过的那几个:

```python
    # NOTE: skipping #C0C0C0/#888888/#555555/#8B8682 — those are
    # status-bar foregrounds paired with dark navy bg, where dark
    # remap values would become invisible.
```

**这是主题重映射的通用陷阱**:「按亮度翻转颜色」只在颜色画在**终端背景**上时成立;
一旦它画在应用自己指定的背景上,翻转就是把可见变成不可见。

大小写不敏感用预大写表实现:

`cli.py:2755 @ 863e313`

```python
_LIGHT_MODE_REMAP_UPPER = {k.upper(): v for k, v in _LIGHT_MODE_REMAP.items()}
```

#### 2.8.4 皮肤取色钩子:在类上打补丁,而不是改所有调用点

`cli.py:2758 @ 863e313`

```python
def _install_skin_light_mode_hook() -> None:
    """Wrap SkinConfig.get_color at import time so EVERY skin color read goes
    through the light-mode remap.  Idempotent."""
```

`cli.py:2765 @ 863e313`

```python
    if getattr(SkinConfig, "_hermes_light_mode_hook_installed", False):
        return
    _orig_get_color = SkinConfig.get_color

    def _wrapped_get_color(self, key, fallback=""):
        value = _orig_get_color(self, key, fallback)
        try:
            return _maybe_remap_for_light_mode(value)
        except Exception:
            return value
```

**为什么用 monkeypatch 而不是在每个取色点包一层**:取色点分散在 cli.py、hermes_cli/*、TUI 各处,
逐点改既漏又乱。包在**唯一的读取入口**上,新增的取色点自动获得能力。代价是隐式——读
`get_active_skin().get_color(...)` 的人看不出返回值被改过。幂等靠类属性哨兵。

#### 2.8.5 `_SkinAwareAnsi`:假装成字符串的惰性求值对象

`cli.py:2794 @ 863e313`

```python
class _SkinAwareAnsi:
    """Lazy ANSI escape that resolves from the skin engine on first use.

    Acts as a string in f-strings and concatenation.  Call ``.reset()`` to
    force re-resolution after a ``/skin`` switch.
    """
```

它靠三个魔术方法伪装成 str:

`cli.py:2807 @ 863e313`

```python
    def __str__(self) -> str:
        if self._cached is None:
            try:
                from hermes_cli.skin_engine import get_active_skin
                self._cached = _hex_to_ansi(
                    get_active_skin().get_color(self._skin_key, self._fallback_hex),
                    bold=self._bold,
                )
            except Exception:
                self._cached = _hex_to_ansi(self._fallback_hex, bold=self._bold)
        return self._cached

    def __add__(self, other: str) -> str:
        return str(self) + other

    def __radd__(self, other: str) -> str:
        return other + str(self)
```

**没有它会坏什么**:`_ACCENT` 是模块级常量,在**导入时**求值就意味着导入时就要拉起 skin engine
并读配置。改成惰性后,`f"{_ACCENT}..."` 触发 `__str__`,第一次真正打印彩色输出时才解析。

`cli.py:2830 @ 863e313`

```python
_ACCENT = _SkinAwareAnsi("response_border", "#FFD700", bold=True)
```

对比 `_DIM`,它**故意不用皮肤色**:

`cli.py:2831 @ 863e313`

```python
# Use ANSI dim+italic attributes (\x1b[2;3m) instead of a hardcoded
# hex color so dim/thinking text inherits the terminal's default
# foreground color and stays readable in both light and dark
# Terminal.app modes.  Hardcoded skin colors like #B8860B
# (dark goldenrod) become invisible against light cream backgrounds.
_DIM = "\x1b[2;3m"
```

**这是比重映射表更根本的解法**:用 SGR 属性(dim / italic)而非具体颜色,让终端自己决定
「暗一点的前景色」是什么——两种模式下都对,不需要维护映射表。可惜只用在了 dim 一处。

`_b` / `_d` 是给**非 TTY 场景**(slash worker、日志重定向)准备的降级版:

`cli.py:2839 @ 863e313`

```python
def _b(s: str) -> str:
    """Bold if stdout is a real TTY; plain text otherwise (slash-worker safe)."""
    import sys as _sys
    try:
        return f"\x1b[1m{s}\x1b[0m" if _sys.stdout.isatty() else str(s)
    except Exception:
        return str(s)
```


---

### 2.9 输出历史与 `_cprint` —— 一个「终端不是文件」的完整应对

#### 2.9.1 场景:终端一 resize,上面的输出就没了

prompt_toolkit 的交互 Application 占着终端底部一块固定区域。终端 resize 或需要全屏重绘时,
**滚动区里已经打过的内容 prompt_toolkit 不负责重建**——它只知道自己那块。于是 Hermes 自己记一份
最近输出,重绘后重放。

`cli.py:2984 @ 863e313`

```python
_OUTPUT_HISTORY_ENABLED = True
_OUTPUT_HISTORY_REPLAYING = False
_OUTPUT_HISTORY_SUPPRESSED = False
_OUTPUT_HISTORY_MAX_LINES = 200
_OUTPUT_HISTORY = deque(maxlen=_OUTPUT_HISTORY_MAX_LINES)
```

三个独立的抑制标志各司其职:
- `_ENABLED` —— 用户配置(`cli.py:4281` 处从配置写入);
- `_REPLAYING` —— 重放期间自己不要把重放内容再记一遍(否则历史会指数膨胀);
- `_SUPPRESSED` —— 上下文管理器式的临时抑制。

`cli.py:3021 @ 863e313` 是唯一的写入闸门:

```python
def _record_output_history_entry(entry) -> None:
    if not _OUTPUT_HISTORY_ENABLED or _OUTPUT_HISTORY_REPLAYING or _OUTPUT_HISTORY_SUPPRESSED:
        return
    _OUTPUT_HISTORY.append(entry)
```

`cli.py:3010 @ 863e313` 的抑制上下文保存/恢复旧值(而非无脑置 False),支持嵌套:

```python
@contextmanager
def _suspend_output_history():
    global _OUTPUT_HISTORY_SUPPRESSED
    old_value = _OUTPUT_HISTORY_SUPPRESSED
    _OUTPUT_HISTORY_SUPPRESSED = True
    try:
        yield
    finally:
        _OUTPUT_HISTORY_SUPPRESSED = old_value
```

#### 2.9.2 条目可以是 callable —— 让重放适应新宽度

`cli.py:3037 @ 863e313`

```python
def _replay_output_history() -> None:
    """Repaint recent output above the prompt after a full screen clear."""
    global _OUTPUT_HISTORY_REPLAYING
    if not _OUTPUT_HISTORY_ENABLED or not _OUTPUT_HISTORY:
        return
    _OUTPUT_HISTORY_REPLAYING = True
    try:
        rendered_lines = []
        for entry in tuple(_OUTPUT_HISTORY):
            if callable(entry):
                try:
                    lines = entry()
                except Exception:
                    continue
                if isinstance(lines, str):
                    lines = lines.splitlines()
            else:
                lines = [entry]
            rendered_lines.extend(str(line) for line in lines)
```

**为什么要允许 callable**:一个已渲染成 80 列的 Panel,在窗口拉宽到 160 列后重放出来是错的。
存一个**渲染闭包**而不是渲染结果,重放时按当前宽度重新渲染。真实用例:

`hermes_cli/cli_agent_setup_mixin.py:852 @ 863e313`

```python
        _record_output_history_entry(lambda: self._render_resume_history_panel_lines(panel))
```

重放的输出方式也经过优化:

`cli.py:3056 @ 863e313`

```python
        if rendered_lines:
            # Replay after resize can contain hundreds of history lines. A
            # per-line prompt_toolkit print forces one synchronous terminal I/O
            # and redraw cycle per line, which users perceive as a waterfall of
            # old output. Keep the existing history contents unchanged, but
            # emit the replay as one ANSI payload so resize recovery does a
            # single prompt_toolkit print/redraw.
            _pt_print(_PT_ANSI("\n".join(rendered_lines)))
```

**「用户感知」再次成为设计依据**:逐行打印在功能上完全正确,但在视觉上是「旧输出瀑布」,
所以合并成一次 payload。

#### 2.9.3 `_cprint`:三条路径的打印分发

`cli.py:3070 @ 863e313`

```python
def _cprint(text: str):
    """Print ANSI-colored text through prompt_toolkit's native renderer.

    Raw ANSI escapes written via print() are swallowed by patch_stdout's
    StdoutProxy.  Routing through print_formatted_text(ANSI(...)) lets
    prompt_toolkit parse the escapes and render real colors.

    When called from a background thread while a prompt_toolkit
    ``Application`` is running (the common case for the self-improvement
    background review's ``💾 …`` summary, curator summaries, and other
    bg-thread emissions), a direct ``_pt_print`` races with the input
    area's redraw and the line can end up visually buried behind the
    prompt.  Route those cases through ``run_in_terminal`` via
    ``loop.call_soon_threadsafe``, which pauses the input area, prints
    the line above it, and redraws the prompt cleanly.
    """
```

**问题演出来是这样的**:后台任务(如自我改进的回顾)做完了,想打一行 `💾 …`。它在后台线程里
直接调 prompt_toolkit 打印 → 与输入区的重绘竞态 → 那行字**被提示符盖住**,用户看不到自己的任务完成了。

分发的三条路径:

**路径 A(无 app / app 未跑)**——直接打,失败退化到裸 `print`:

`cli.py:3100 @ 863e313`

```python
    # No active app, or we're already on the app's main thread: the
    # direct prompt_toolkit print is safe and matches existing behavior
    # (spinner frames, streamed tokens, tool activity prefixes, …).
    if app is None or not getattr(app, "_is_running", False):
        try:
            _pt_print(_PT_ANSI(text))
        except Exception:
            # Fallback when stdout is not a real console (e.g. subprocess
            # worker logging to a file). prompt_toolkit raises
            # NoConsoleScreenBufferError (Windows) or OSError (other).
            try:
                print(text)
            except Exception:
                pass
        return
```

**路径 B(同一个事件循环线程)**——直接打:

`cli.py:3135 @ 863e313`

```python
    # Same thread as the app's loop → safe to print directly.
    if current_loop is loop and loop.is_running():
        _pt_print(_PT_ANSI(text))
        return
```

判断「当前是不是 app 的循环线程」时特意用 `get_running_loop()` 而非 `get_event_loop()`:

`cli.py:3126 @ 863e313`

```python
        # Use get_running_loop() instead of get_event_loop() to avoid the
        # DeprecationWarning / RuntimeWarning emitted by Python 3.10+ when
        # get_event_loop() is called from a thread that has no current event
        # loop set (e.g. the process_loop background thread).  Fixes #19285.
        current_loop = _asyncio.get_running_loop()
```

**路径 C(跨线程)**——通过 `call_soon_threadsafe` 把 `run_in_terminal` 排到 app 的循环上:

`cli.py:3140 @ 863e313`

```python
    # Cross-thread emission: ask the app's event loop to schedule a
    # ``run_in_terminal`` that wraps ``_pt_print``.  This hides the
    # prompt, prints, and redraws.  Fire-and-forget — if scheduling
    # fails we fall back to a direct print so the line isn't lost.
```

路径 C 内部还处理了 `run_in_terminal` 返回值的**两种形态**,并且明确禁止了一个看似合理的兜底:

`cli.py:3144 @ 863e313`

```python
    def _schedule():
        # run_in_terminal() may return either:
        #   • a coroutine / Future (prompt_toolkit ≥ 3.0) — must be scheduled
        #     via ensure_future so the coroutine is actually awaited; calling
        #     it bare would leave it unawaited and silently drop the output
        #     (fixes #23185 Bug A).
        #   • None (some mocks / older PT builds) — just call the inner
        #     function directly since PT already executed it synchronously.
        # Do NOT fall back to a bare _pt_print when ensure_future raises,
        # because run_in_terminal already invoked the lambda in that case
        # (the mock path), which would double-print the line.
```

**「不要在这里兜底」是个反直觉但正确的判断**:兜底会把「一次输出」变成「两次输出」,而
丢一行的代价远小于重复一行(重复会让用户以为任务跑了两遍)。

`_cli_visible_print` 是同一问题的简化版,给 `/sessions`、`/history` 这类批量输出用:

`cli.py:3210 @ 863e313`

```python
def _cli_visible_print(text: str = "") -> None:
    """Print normally unless prompt_toolkit owns the live terminal.

    Bare ``print()`` output is swallowed by ``patch_stdout`` while an
    interactive ``Application`` is running, so ``/sessions`` and ``/history``
    would render nothing. Route through ``_cprint`` (prompt_toolkit-native)
    in that case, and fall back to ``print`` otherwise.
    """
```

#### 2.9.4 `_prepend_note_to_message`:多模态内容的类型分叉

`cli.py:3175 @ 863e313`

```python
def _prepend_note_to_message(message, note: str):
    """Prepend a one-shot system-style note to a user message.

    ``message`` is normally a plain string, but when the user attaches an image
    to a vision-capable model it becomes a list of OpenAI-style content parts
    (text + ``image_url`` blocks). Naively doing ``note + "\\n\\n" + message``
    then raises ``TypeError: can only concatenate str (not "list") to str`` —
    e.g. running ``/model ...`` (which queues a model-switch note) and then
    sending a pasted image in the same turn.
```

**事故复述**:用户先 `/model gpt-5`(排队一条「模型已切换」的提示要塞进下一条消息),
然后粘贴一张图。此时 message 已经是 OpenAI 的多模态 content **列表**,
`note + "\n\n" + message` 直接 `TypeError`,用户的这一轮输入丢失。

三分支处理 + fail-open:

`cli.py:3194 @ 863e313`

```python
    if isinstance(message, str):
        return f"{note}\n\n{message}" if message else note
    if isinstance(message, list):
        parts = list(message)
        for i, part in enumerate(parts):
            if isinstance(part, dict) and part.get("type") == "text":
                merged = dict(part)
                text = merged.get("text", "")
                merged["text"] = f"{note}\n\n{text}" if text else note
                parts[i] = merged
                return parts
        # No text part (image-only) — insert the note as a leading text block.
        return [{"type": "text", "text": note}, *parts]
    return message
```

注意 `merged = dict(part)` 是**浅拷贝后再改**,不原地修改传入的 dict——避免污染调用方持有的对象。

---

### 2.10 附件与文件拖放

#### 2.10.1 场景:用户把文件拖进终端

终端里拖一个文件,shell 会把路径贴进来。用户期望 hermes 把它当附件,而不是当聊天文本。
更麻烦的是:路径以 `/` 开头,和斜杠命令**长得一模一样**。

`cli.py:3376 @ 863e313`

```python
def _detect_file_drop(user_input: str) -> "dict | None":
    """Detect if *user_input* starts with a real local file path.

    This catches dragged/pasted paths before they are mistaken for slash
    commands, and also supports Termux-friendly paths like ``~/storage/...``.
```

前置过滤器列了一长串「看起来像路径」的开头形态,包括各种引号包裹与 Windows 盘符:

`cli.py:3399 @ 863e313`

```python
    starts_like_path = (
        stripped.startswith("/")
        or stripped.startswith("~")
        or stripped.startswith("./")
        or stripped.startswith("../")
        or stripped.startswith("file://")
        or (len(stripped) >= 3 and stripped[1] == ":" and stripped[2] in {"\\", "/"} and stripped[0].isalpha())
        or stripped.startswith('"/')
        or stripped.startswith('"~')
        or stripped.startswith("'/")
        or stripped.startswith("'~")
        or stripped.startswith('"./')
        or stripped.startswith('"../')
        or stripped.startswith("'./")
        or stripped.startswith("'../")
        or (len(stripped) >= 4 and stripped[0] in {"'", '"'} and stripped[2] == ":" and stripped[3] in {"\\", "/"} and stripped[1].isalpha())
    )
```

**判定的最终依据是「文件真的存在吗」**——这是唯一可靠的区分手段,`/help` 不是文件,
`/Users/x/a.png` 是。三级尝试:

`cli.py:3419 @ 863e313`(整串就是路径):

```python
    direct_path = _resolve_attachment_path(stripped)
```

`cli.py:3427 @ 863e313`(切出第一个 token,剩下的当说明文字):

```python
    first_token, remainder = _split_path_input(stripped)
```

`cli.py:3429 @ 863e313`(带空格的路径:从**最长前缀**开始逐个空格位回退试):

```python
    if drop_path is None and " " in stripped and stripped[0] not in {"'", '"'}:
        space_positions = [idx for idx, ch in enumerate(stripped) if ch == " "]
        for pos in reversed(space_positions):
            candidate = stripped[:pos].rstrip()
            resolved = _resolve_attachment_path(candidate)
            if resolved is not None:
                drop_path = resolved
                remainder = stripped[pos + 1 :].strip()
                break
```

`reversed(space_positions)` = 从最后一个空格开始,所以先试**最长**的候选路径——
`/tmp/my file.png describe` 会正确切成 `/tmp/my file.png` + `describe`,而不是 `/tmp/my`。

#### 2.10.2 `_split_path_input`:手写的小词法分析器

`cli.py:3259 @ 863e313`

```python
def _split_path_input(raw: str) -> tuple[str, str]:
    r"""Split a leading file path token from trailing free-form text.

    Supports quoted paths and backslash-escaped spaces so callers can accept
    inputs like:
      /tmp/pic.png describe this
      ~/storage/shared/My\ Photos/cat.png what is this?
      "/storage/emulated/0/DCIM/Camera/cat 1.png" summarize
    """
```

引号分支里的转义处理:

`cli.py:3272 @ 863e313`

```python
    if raw[0] in {'"', "'"}:
        quote = raw[0]
        pos = 1
        while pos < len(raw):
            ch = raw[pos]
            if ch == '\\' and pos + 1 < len(raw):
                pos += 2
                continue
            if ch == quote:
                token = raw[1:pos]
                remainder = raw[pos + 1 :].strip()
                return token, remainder
            pos += 1
        return raw[1:], ""
```

**为什么不用 `shlex.split`**:shlex 对未闭合引号会抛异常,而用户拖进来的路径经常是半截的;
这里的策略是「引号没闭合就把剩下全当路径」(第 3285 行的 `return raw[1:], ""`),
永远不失败。这是**面向人类输入的解析器**该有的性格。

#### 2.10.3 `_resolve_attachment_path`:六种路径方言归一

`cli.py:3302 @ 863e313`

```python
def _resolve_attachment_path(raw_path: str) -> Path | None:
    """Resolve a user-supplied local attachment path.

    Accepts quoted or unquoted paths, expands ``~`` and env vars, and resolves
    relative paths from ``TERMINAL_CWD`` when set (matching terminal tool cwd).
    Returns ``None`` when the path does not resolve to an existing file.
    """
```

`file://` URL 的解析里有一条 Windows 专属修正:

`cli.py:3327 @ 863e313`

```python
                elif (
                    os.name == "nt"
                    and len(expanded) >= 3
                    and expanded[0] == "/"
                    and expanded[1].isalpha()
                    and expanded[2] == ":"
                ):
                    # file:///C:/... parses to path "/C:/..." — drop the
                    # leading slash so it resolves as a drive-letter path.
                    expanded = expanded[1:]
```

反向的 WSL 修正——在 POSIX 上收到 Windows 盘符路径,翻译成 `/mnt/<盘符>/`:

`cli.py:3340 @ 863e313`

```python
    if os.name != "nt":
        normalized = expanded.replace("\\", "/")
        if len(normalized) >= 3 and normalized[1] == ":" and normalized[2] == "/" and normalized[0].isalpha():
            expanded = f"/mnt/{normalized[0].lower()}/{normalized[3:]}"
```

相对路径的基准是 `TERMINAL_CWD`(即 worktree),而非进程 cwd——这是 §2.6.3 那条约定的又一个消费点:

`cli.py:3345 @ 863e313`

```python
    if not path.is_absolute():
        base_dir = Path(os.getenv("TERMINAL_CWD", os.getcwd()))
        path = base_dir / path
```

最后是这个函数里最有教学价值的一段注释——**为什么 `exists()` 也要包 try**:

`cli.py:3354 @ 863e313`

```python
    # Path.exists() / is_file() invoke os.stat(), which raises OSError when
    # the candidate string is structurally invalid as a path — most commonly
    # ENAMETOOLONG (errno 63 on macOS, errno 36 on Linux) when the input
    # exceeds NAME_MAX (typically 255 bytes). This bites pasted slash
    # commands like `/goal <long prose>` because `_detect_file_drop()`'s
    # `starts_like_path` prefilter accepts any input starting with `/`,
    # then this resolver tries to stat it before short-circuiting on the
    # slash-command path. Without this guard the OSError propagates up to
    # the process_loop catch-all in _interactive_loop and the user input
    # is silently lost (the warning ends up in agent.log but the user sees
    # nothing — the prompt just hangs).
    try:
        if not resolved.exists() or not resolved.is_file():
            return None
    except OSError:
        return None
```

**事故复述**:用户输入 `/goal <一大段散文>` → 以 `/` 开头,过了 `starts_like_path` 预筛 →
resolver 拿整串去 `os.stat` → 超过 `NAME_MAX`(通常 255 字节)→ `OSError: ENAMETOOLONG` →
一路冒到 `_interactive_loop` 的 catch-all → **用户的输入静默消失,提示符像卡住一样**,
错误只进了 `agent.log`。这是一条从「路径预筛太宽松」到「用户输入丢失」的完整因果链。

#### 2.10.4 徽章与窄终端

`cli.py:3448 @ 863e313`

```python
def _format_image_attachment_badges(attached_images: list[Path], image_counter: int, width: int | None = None) -> str:
    """Format the attached-image badge row for the interactive CLI.

    Narrow terminals such as Termux should get a compact summary that fits on a
    single row, while wider terminals can show the classic per-image badges.
    """
```

三档宽度,`< 52` / `< 80` / 其余,各有独立的截断预算:

`cli.py:3462 @ 863e313`

```python
    if width < 52:
        if len(attached_images) == 1:
            return f"[📎 {_trunc(attached_images[0].name, 20)}]"
        return f"[📎 {len(attached_images)} images attached]"
```

Termux(手机)是这段代码的一等公民,`cli.py:3243 @ 863e313` 的示例路径探测也是为它写的:

```python
def _termux_example_image_path(filename: str = "cat.png") -> str:
    """Return a realistic example media path for the current Termux setup."""
```

`cli.py:3251 @ 863e313` 里的一句注释解释了为什么用字面 `/` 拼接:

```python
    # Termux/Android roots are POSIX paths — join with literal forward
    # slashes so the hint stays correct even when this renders on Windows.
```

#### 2.10.5 剪贴板图片的粘贴判定

`cli.py:3481 @ 863e313`

```python
def _should_auto_attach_clipboard_image_on_paste(pasted_text: str) -> bool:
    """Auto-attach clipboard images only for image-only paste gestures."""
    return not pasted_text.strip()
```

一行代码,但语义很重要:粘贴事件带回来的文本**是空的**,才说明用户剪贴板里是纯图片。
如果剪贴板里既有文字又有图,以文字为准,不自作主张附图。

#### 2.10.6 `_collect_query_images`:单查询模式的图片收集

`cli.py:3838 @ 863e313`

```python
def _collect_query_images(query: str | None, image_arg: str | None = None) -> tuple[str, list[Path]]:
    """Collect local image attachments for single-query CLI flows."""
```

当整串就是一个图片路径(没有说明文字)时,给模型合成一句占位文本:

`cli.py:3843 @ 863e313`

```python
    if isinstance(message, str):
        dropped = _detect_file_drop(message)
        if dropped and dropped.get("is_image"):
            images.append(dropped["path"])
            message = dropped["remainder"] or f"[User attached image: {dropped['path'].name}]"
```

`--image` 显式参数走**严格校验**(找不到就抛,不是静默忽略):

`cli.py:3849 @ 863e313`

```python
    if image_arg:
        explicit_path = _resolve_attachment_path(image_arg)
        if explicit_path is None:
            raise ValueError(f"Image file not found: {image_arg}")
        if explicit_path.suffix.lower() not in _IMAGE_EXTENSIONS:
            raise ValueError(f"Not a supported image file: {explicit_path}")
```

**两种输入两种严格度**:拖放是「猜测式」的,猜错就当普通文本;`--image` 是「声明式」的,
错了必须报错。这个区分很对。

