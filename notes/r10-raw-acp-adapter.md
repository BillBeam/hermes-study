# r10-C · acp_adapter 编辑器接驳 —— 一个 ACP 服务端,与它带出来的第四个审批面

> 底稿(L2 结构级理解)。片名 **C · acp_adapter 编辑器接驳**;片内 11 个文件 / 5,831 行。
> 一切对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` 单独成行、置于代码块之前。
> 围栏块是逐字源码摘录;```text / ```verify / ```console 是作者声明的非源码块。

---

## §1 这一片是什么

**ACP = Agent Client Protocol**,一个「编辑器(客户端)↔ agent(服务端)」之间的 JSON-RPC 2.0 协议,
走**子进程的 stdin/stdout**。编辑器(Zed、Buzz Desktop 等)启动 agent 进程、在 stdout 上收发 JSON 帧,
于是同一个编辑器可以接任何实现了这套协议的 agent。本片是 **hermes 作为 ACP 服务端**的那一半实现。

要先记住三个方向,后面全靠它区分:

- **agent 侧方法**(编辑器 → hermes 的请求):`initialize`、`session/new`、`session/prompt`……
  hermes 实现它们,共 12 个(§3.1)。
- **client 侧调用**(hermes → 编辑器):只有两个 —— `session/update`(通知,单向)与
  `session/request_permission`(请求,要等答复)。§3.2。
- **反方向不存在**:hermes 从不调用编辑器的 `fs/read_text_file`、`fs/write_text_file`、`terminal/create`。
  它用自己的 `read_file` / `write_file` / `terminal` 工具直接操作宿主文件系统。取证见 §5.4「未使用的客户端能力」。

工程上要解决的核心矛盾是:**hermes 的 `AIAgent` 是同步的、跑在工作线程里;ACP 的 I/O 是 asyncio 的、
跑在主线程的事件循环上。** 于是本片一半的代码量是「线程 ↔ 事件循环」的搬运与隔离
(`asyncio.run_coroutine_threadsafe` 的封装、ContextVar 而不是环境变量、线程本地回调),
另一半是「hermes 的内部事件形状 → ACP 的通知形状」的翻译(`tools.py` 1,347 行几乎全是这个)。

术语一句话锚定(首次出现):

| 术语 | 一句话中文 |
|---|---|
| stdio transport | 用子进程的标准输入/输出当传输管道,不开网络端口 |
| JSON-RPC `-32601` | 标准错误码「method not found」 |
| ContextVar | Python 的「上下文局部变量」,每个线程/asyncio 任务各有一份,不像 `os.environ` 全进程共享 |
| ToolKind | ACP 给工具调用分的类别(read / edit / execute / search / fetch / think / other),编辑器据此选图标 |
| ToolCallStart / ToolCallUpdate | 「工具开始了」/「工具进展或结束了」两种通知负载 |
| prompt cache | provider 侧对相同请求前缀的缓存;前缀一变就失效,所以中途换工具表是有代价的 |
| SessionDB | hermes 的 SQLite 会话库,默认 `~/.hermes/state.db` |
| compression / compaction | 上下文压缩:把长历史摘要成一条,内部会换一个新的 DB 会话 id |
| MCP | Model Context Protocol,外挂工具服务器的协议;hermes 可以把 MCP 服务器的工具并进自己的工具表 |
| WSL | Windows Subsystem for Linux;Windows 侧路径 `E:\x` 与 Linux 侧 `/mnt/e/x` 要互译 |

---

## §2 文件清单(逐个全路径 + 角色)

| 全路径 | 行数 | 角色一句话 |
|---|---|---|
| `acp_adapter/__init__.py` | 1 | 包标记,只有一行 docstring;**它把 ACP 写成 "Agent Communication Protocol"**(见 §6 记号 ◇7) |
| `acp_adapter/__main__.py` | 5 | 让 `python -m acp_adapter` 可用:`from .entry import main` 后直接 `main()` |
| `acp_adapter/auth.py` | 79 | 认证面:探测当前可用 provider、拼出 ACP 握手要的 auth methods 列表(2 类) |
| `acp_adapter/edit_approval.py` | 338 | **ACP 独有的「文件编辑审批」面**:造 diff 提案、按策略自动放行、绑 ContextVar |
| `acp_adapter/entry.py` | 280 | CLI 入口(`hermes acp` / `hermes-acp` / `python -m acp_adapter`):早期 bootstrap、日志转 stderr、探针噪声过滤、5 个开关、拉起 `acp.run_agent` |
| `acp_adapter/events.py` | 279 | 回调桥:把 `AIAgent` 的 4 个同步回调翻成 ACP `session/update`,含 todo → ACP 原生 plan 的翻译 |
| `acp_adapter/permissions.py` | 182 | **危险命令审批**的 ACP 桥:造 5 个权限选项、把 ACP 的答复映射回 hermes 的 `once/session/always/deny/timeout` |
| `acp_adapter/provenance.py` | 127 | 会话溯源:从 `sessions` 表的 `parent_session_id` / `end_reason` 现推出压缩血统,挂在 ACP `_meta.hermes` 下 |
| `acp_adapter/server.py` | 2510 | `HermesACPAgent`:12 个协议方法、`prompt()` 全生命周期、9 个斜杠命令、模型/模式/配置项切换、历史回放 |
| `acp_adapter/session.py` | 683 | `SessionManager`:ACP 会话 ↔ `AIAgent` 实例的映射、SessionDB 持久化与恢复、WSL cwd 互译、建 agent 的全部 kwargs |
| `acp_adapter/tools.py` | 1347 | 工具渲染层:hermes 工具名 → ToolKind / 标题 / 起止通知内容;21 个逐工具的结果美化器;unified diff 解析 |

11 个文件全部点名。行数校验:

```verify
cd /home/user/hermes-agent && wc -l acp_adapter/*.py | tail -1
# 期望: 5831 total
```

**片外但本片强依赖**(不在清单里,只在需要时下钻):
`toolsets.py`(`hermes-acp` toolset 定义,行 407)、`model_tools.py`(共享工具派发器 `handle_function_call`)、
`tools/approval.py`(危险命令判据核心)、`tools/terminal_tool.py`(线程本地审批回调槽)、
`tools/write_approval.py`(memory/skills 写审批)、`tools/file_tools.py`(敏感路径硬拒)、
`agent/tool_executor.py`(发 `tool.started` 的地方)、`hermes_cli/main.py`(`hermes acp` 子命令)。

---

## §3 接缝穷举

### §3.1 ACP agent 侧方法:12 个,逐项列全

`HermesACPAgent` 覆写的、非下划线开头的 `async def` 就是它实现的协议方法面。**12 个,无遗漏**:

| # | Python 方法 | 行 | 返回类型 | 一句话 |
|---|---|---|---|---|
| 1 | `initialize` | 1139 | `InitializeResponse` | 回协议版本、agent 名/版本、能力位、auth methods |
| 2 | `authenticate` | 1173 | `AuthenticateResponse \| None` | 只接受与 `initialize` 里 advertise 过的 method_id 一致的那一个 |
| 3 | `new_session` | 1435 | `NewSessionResponse` | 建 `SessionState` + `AIAgent`,注册本会话 MCP 服务器 |
| 4 | `load_session` | 1456 | `LoadSessionResponse \| None` | 找不到返回 `None`;**在响应前 `await` 完整历史回放** |
| 5 | `resume_session` | 1504 | `ResumeSessionResponse` | 同上,但找不到就**新建**(不返回 None) |
| 6 | `cancel` | 1540 | `None` | 置 cancel_event + `request_hard_interrupt` |
| 7 | `fork_session` | 1561 | `ForkSessionResponse` | 深拷贝历史到新会话 |
| 8 | `list_sessions` | 1581 | `ListSessionsResponse` | cwd 过滤 + cursor 分页,页大小固定 50 |
| 9 | `prompt` | 1628 | `PromptResponse` | 核心:斜杠命令拦截 → 重定向/排队 → 线程池跑 agent → 回流通知 |
| 10 | `set_session_model` | 2440 | `SetSessionModelResponse \| None` | 解析 `provider:model`,**重建 agent** |
| 11 | `set_session_mode` | 2474 | `SetSessionModeResponse \| None` | 三档模式,落到 `state.mode` |
| 12 | `set_config_option` | 2490 | `SetSessionConfigOptionResponse \| None` | 只特判 `edit_approval_policy`,其余原样存进 `state.config_options` |

```verify
cd /home/user/hermes-agent && grep -nE '^    async def [a-z]' acp_adapter/server.py | grep -v 'async def _'
cd /home/user/hermes-agent && grep -cE '^    async def [a-z][a-z_]*\(' acp_adapter/server.py   # 期望 12
cd /home/user/hermes-agent && grep -cE '^    async def _' acp_adapter/server.py                # 期望 5(私有辅助,不是协议面)
```

**线上方法名**只有 2 个在基线里被测试逐字钉死:

`tests/acp/test_server.py:377 @ 863e313`

```python
        mode_result = await router(
            "session/set_mode",
            {"modeId": "accept_edits", "sessionId": new_resp.session_id},
            False,
        )
        config_result = await router(
            "session/set_config_option",
            {
                "configId": "approval_mode",
                "sessionId": new_resp.session_id,
                "value": "auto",
            },
            False,
        )
```

另有 4 个线上名字以字面量出现在**同仓库的 ACP 客户端**一侧(hermes 作为 Copilot 的 ACP 客户端,不在本片):
`agent/copilot_acp_client.py:639` 的 `"session/new"`、`:652` 的 `"session/prompt"`、
`:682` 的 `"session/update"`、`:702` 的 `"session/request_permission"`。
其余方法的线上名(`initialize`、`authenticate`、`session/load`、`session/resume`、`session/fork`、
`session/list`、`session/cancel`、`session/set_model`)由 SDK `agent-client-protocol==0.9.0` 的路由器决定,
**该 SDK 在本容器未安装**(见 §7),因此本底稿不对这 8 个线上名下断言。

### §3.2 ACP client 侧调用:2 种,共 10 + 2 处

hermes 只反向调用编辑器两个东西:

| 调用 | 语义 | 调用点 |
|---|---|---|
| `conn.session_update(session_id, update)` | 单向通知,不等答复 | 10 处 |
| `conn.request_permission(session_id=, tool_call=, options=)` | 请求,阻塞等答复 | 2 处传入(命令审批 1、编辑审批 1) |

```verify
cd /home/user/hermes-agent && grep -nE '(conn|_conn)\.session_update\(' acp_adapter/*.py | grep -v '``'
cd /home/user/hermes-agent && grep -nE '(conn|_conn)\.session_update\(' acp_adapter/*.py | grep -v '``' | wc -l   # 期望 10
cd /home/user/hermes-agent && grep -nE 'conn\.request_permission,?$|conn\.request_permission,' acp_adapter/server.py   # 期望 2 行(1804 / 1809)
```

10 处 `session_update` 的分布:`acp_adapter/events.py:97`(唯一的工作线程侧出口,所有 agent 事件都从这里出去)、
`acp_adapter/server.py:884`(usage)、`:956`(session_info)、`:1357`(历史回放)、`:1717`(斜杠命令回执)、
`:1760`(重定向回执)、`:1767`(排队回执)、`:2052`(最终答复)、`:2067`(排队 prompt 的回显)、
`:2115`(命令表 advertise)。

### §3.3 `session/update` 通知类型:9 种

6 种由代码里的**显式字面量**确定:

```verify
cd /home/user/hermes-agent && grep -rnoE 'session_update="[a-z_]+"' acp_adapter/*.py | sort -u
# plan(acp_adapter/events.py:60,84) / user_message_chunk(acp_adapter/server.py:1294) / agent_message_chunk(acp_adapter/server.py:1300)
# / usage_update(acp_adapter/server.py:871) / session_info_update(acp_adapter/server.py:950)
# / available_commands_update(acp_adapter/server.py:2118)  → 去重后 6 种
```

另 3 种经 SDK 帮助函数产生,负载类型在本仓库有类型标注、**变体字符串在 SDK 里**(未取证):

| 帮助函数 | 本仓库的类型标注 | 推定变体 |
|---|---|---|
| `acp.start_tool_call` | `acp_adapter/tools.py:1049`:`) -> ToolCallStart:` | `tool_call` |
| `acp.update_tool_call` | `acp_adapter/tools.py:1311`:`) -> ToolCallProgress:` | `tool_call_update` |
| `acp.update_agent_thought_text` | `acp_adapter/server.py:1307`:`    def _history_thought_update(text: str) -> AgentThoughtChunk:` | `agent_thought_chunk` |

合计 **9 种**。`acp.update_agent_message_text` / `acp.update_user_message_text` 分别对应上面已计入的
`agent_message_chunk` / `user_message_chunk`(acp_adapter/server.py:1293-1303 用显式构造器造了同样两种,带 `field_meta`)。

### §3.4 斜杠命令:9 个,三张表一致

`_SLASH_COMMANDS`(帮助文本)、`_ADVERTISED_COMMANDS`(advertise 给客户端)、`_handle_slash_command` 的
dispatch 表 —— 三处**各 9 条,名字一致**。

| 命令 | 处理器行 | 提示(input_hint) | 一句话 |
|---|---|---|---|
| `/help` | 2187 | — | 列 9 条 + 「不认识的 / 命令交给模型」 |
| `/model` | 2195 | model name to switch to | 无参显示当前;有参**重建 agent** |
| `/tools` | 2216 | — | 用 `hermes-acp` toolset 重算一遍工具表(不读当前 agent 的 `tools`) |
| `/context` | 2252 | — | 按角色计数 + 估算 token 压力 + 压缩阈值 |
| `/reset` | 2336 | — | 清历史 + `agent.reset_session_state()` |
| `/compress` | 2352 | — | 手动压缩;**临时把 `agent._session_db` 置 None** 以避免会话 id 分裂 |
| `/steer` | 2407 | guidance for the active turn | 有活跃回合就注入,否则排队 |
| `/queue` | 2426 | prompt to run next | 排到下一回合 |
| `/version` | 2435 | — | 版本号 |

```verify
cd /home/user/hermes-agent && sed -n '569,579p' acp_adapter/server.py | grep -cE '^\s+"[a-z]+"'      # _SLASH_COMMANDS 键数 → 9
cd /home/user/hermes-agent && sed -n '581,621p' acp_adapter/server.py | grep -cE '"name":'          # _ADVERTISED_COMMANDS → 9
cd /home/user/hermes-agent && grep -cE '^\s+"[a-z]+": self\._cmd_' acp_adapter/server.py            # dispatch 表 → 9
```

### §3.5 `entry.py` CLI 开关:5 个

```verify
cd /home/user/hermes-agent && grep -cE '^\s+parser\.add_argument\(' acp_adapter/entry.py   # 期望 5
cd /home/user/hermes-agent && grep -oE '"--[a-z-]+"|"-[a-z]"' acp_adapter/entry.py | tr '\n' ' '
# 期望: "--version" "--check" "--setup" "--setup-browser" "--yes" "-y"
```

`--version` / `--check` / `--setup` / `--setup-browser` **在 `_setup_logging()` 与 `_load_env()` 之前就 return**
(server 根本不起),`--yes` 只是 `--setup-browser` 的确认跳过。

### §3.6 会话模式(3)与编辑审批策略(3)的双射

`acp_adapter/server.py:626 @ 863e313`

```python
    _MODE_ACCEPT_EDITS = "accept_edits"
    _MODE_DONT_ASK = "dont_ask"
    _MODE_TO_EDIT_APPROVAL_POLICY = {
        _MODE_DEFAULT: "ask",
        _MODE_ACCEPT_EDITS: "workspace_session",
        _MODE_DONT_ASK: "session",
    }
    _EDIT_APPROVAL_POLICY_TO_MODE = {
        value: key for key, value in _MODE_TO_EDIT_APPROVAL_POLICY.items()
    }
```

| 模式 id | 编辑器上的名字 | 描述(server.py 里的原文位置) | 映射到的策略 | 效果 |
|---|---|---|---|---|
| `default` | Default | 668 | `ask` | 每次编辑都问 |
| `accept_edits` | Accept Edits | 673 | `workspace_session` | cwd 子树 + 系统临时目录内自动放行 |
| `dont_ask` | Don't Ask | 678 | `session` | 本会话内一律自动放行 |

三档策略的字面常量:

`acp_adapter/edit_approval.py:45 @ 863e313`

```python
SENSITIVE_AUTO_APPROVE_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}
AUTO_APPROVE_ASK = "ask"
AUTO_APPROVE_WORKSPACE = "workspace_session"
AUTO_APPROVE_SESSION = "session"
```

**两档自动放行都不覆盖敏感路径**:`should_auto_approve_edit`(acp_adapter/edit_approval.py:200)先查
`_is_sensitive_auto_approve_path`(:192),路径里含 `.git` / `.ssh` 目录段、或文件名在上面那 5 个里,
一律返回 False(照旧问)。

```verify
cd /home/user/hermes-agent && grep -cE '^\s+id=self\._MODE_' acp_adapter/server.py   # 期望 3
```

### §3.7 权限选项 id:命令面 5 个、编辑面 2 个

`acp_adapter/permissions.py:18 @ 863e313`

```python
# Maps ACP permission option ids to Hermes approval result strings.
# Option ids are stable across both the ``allow_permanent=True`` and
# ``allow_permanent=False`` paths even though the option list differs.
_OPTION_ID_TO_HERMES = {
    "allow_once": "once",
    "allow_session": "session",
    "allow_always": "always",
    "deny": "deny",
    "deny_always": "deny",
}
```

| option_id | ACP `kind` | 编辑器标签 | 何时出现 | 映射到 hermes |
|---|---|---|---|---|
| `allow_once` | `allow_once` | Allow once | 恒有 | `once` |
| `allow_session` | `allow_always`(**故意错配**,见下) | Allow for session | `smart_denied=False` 时 | `session` |
| `allow_always` | `allow_always` | Allow always | `allow_permanent and not smart_denied` | `always` |
| `deny` | `reject_once` | Deny | 恒有 | `deny` |
| `deny_always` | `reject_always` | Deny always | `not smart_denied` 且 SDK 支持该 kind | **`deny`**(见 ■1) |

`allow_session` 的 kind 错配是代码里自己声明的取舍(acp_adapter/permissions.py:51-52 注释:
"ACP has no session-scoped kind, so use the closest persistent hint while keeping Hermes semantics
in the option id"),不是缺陷。

**SDK 能力探测**:`_permission_option_supports_kind`(acp_adapter/permissions.py:32)用一次
`PermissionOption(option_id="__probe__", kind=kind, name="probe")` 构造试探当前 SDK 是否接受
`reject_always`,失败就不发 `deny_always`。这是「探针式向下兼容」的一个干净样本。

编辑面只有 2 个选项(acp_adapter/edit_approval.py:308-311):`allow_once` / `deny`,**没有 session 档、没有 always 档**。

```verify
cd /home/user/hermes-agent && grep -oE 'option_id="[a-z_]+"' acp_adapter/permissions.py | sort -u   # 含 __probe__ 共 6 行
cd /home/user/hermes-agent && grep -oE 'option_id="[a-z_]+"' acp_adapter/edit_approval.py | sort -u # 期望 2 行
```

### §3.8 `TOOL_KIND_MAP`:27 条,7 种 kind

`acp_adapter/tools.py:24 @ 863e313`

```python
TOOL_KIND_MAP: Dict[str, ToolKind] = {
    # File operations
    "read_file": "read",
    "write_file": "edit",
    "patch": "edit",
    "search_files": "search",
    # Terminal / execution
    "terminal": "execute",
    "process": "execute",
    "execute_code": "execute",
```

```verify
cd /home/user/hermes-agent && python3 - <<'PY'
import ast, pathlib
tree = ast.parse(pathlib.Path('acp_adapter/tools.py').read_text())
for n in ast.walk(tree):
    if isinstance(n, ast.AnnAssign) and getattr(n.target,'id',None)=='TOOL_KIND_MAP':
        d = ast.literal_eval(n.value)
from collections import Counter
print("entries:", len(d))            # 期望 27
print("kinds:", dict(Counter(d.values())))
# 期望 {'read': 7, 'edit': 3, 'search': 1, 'execute': 11, 'other': 1, 'fetch': 3, 'think': 1}
PY
```

`get_tool_kind`(acp_adapter/tools.py:84)对表外的一切返回 `"other"` —— **没有报错、没有日志**。

### §3.9 三张工具表的四向差集(本片最有信息量的一张)

三张表:
① `toolsets.py:407` 的 `hermes-acp` toolset(**决定模型能看见什么**),29 个;
② `acp_adapter/tools.py:24` 的 `TOOL_KIND_MAP`(**决定编辑器画什么图标**),27 个;
③ `acp_adapter/tools.py:62` 的 `_POLISHED_TOOLS`(**决定用不用美化过的渲染路径**),55 个。

```verify
cd /home/user/hermes-agent && python3 - <<'PY'
import ast, pathlib
t = ast.parse(pathlib.Path('acp_adapter/tools.py').read_text())
kind = polished = None
for n in ast.walk(t):
    if isinstance(n, ast.AnnAssign) and getattr(n.target,'id',None)=='TOOL_KIND_MAP':
        kind = ast.literal_eval(n.value)
    if isinstance(n, ast.Assign) and any(getattr(x,'id',None)=='_POLISHED_TOOLS' for x in n.targets):
        polished = ast.literal_eval(n.value)
acp = None
for n in ast.walk(ast.parse(pathlib.Path('toolsets.py').read_text())):
    if isinstance(n, ast.Dict):
        for k, v in zip(n.keys, n.values):
            if isinstance(k, ast.Constant) and k.value == 'hermes-acp':
                acp = set(ast.literal_eval(v)['tools'])
print("hermes-acp:", len(acp), "| TOOL_KIND_MAP:", len(kind), "| _POLISHED_TOOLS:", len(polished))
print("A) ACP 可见但无 kind:", sorted(acp - set(kind)))
print("B) 有 kind 但 ACP 不可见:", sorted(set(kind) - acp))
print("C) ACP 可见但未美化:", sorted(acp - polished))
print("D) 美化表里 ACP 不可见:", len(polished - acp), sorted(polished - acp))
PY
```

实测输出(29 / 27 / 55):

```text
A) ACP 可见但无 kind(5):  browser_cdp browser_console browser_dialog memory session_search
B) 有 kind 但 ACP 不可见(3): _thinking image_generate text_to_speech
C) ACP 可见但未美化(2):    browser_cdp browser_dialog
D) 美化表里 ACP 不可见(28): clarify cronjob discord discord_admin
   feishu_doc_read feishu_drive_add_comment feishu_drive_list_comment_replies
   feishu_drive_list_comments feishu_drive_reply_comment
   ha_call_service ha_get_state ha_list_entities ha_list_services
   image_generate kanban_block kanban_comment kanban_complete kanban_create
   kanban_heartbeat kanban_link kanban_show send_message text_to_speech
   yb_query_group_info yb_query_group_members yb_search_sticker yb_send_dm yb_send_sticker
```

**这直接回答了派工书的第三问「ACP 工具名与内核工具名怎么对上」:**

1. **没有改名。一个都没有。** ACP 侧不存在「ACP 工具名」这个概念 —— hermes 不向编辑器暴露工具
   *清单*(那是 MCP 干的事),它只在工具**跑起来的时候**发一条 `ToolCallStart` 通知。
   这条通知里根本没有「工具名」字段:只有 `tool_call_id`、`title`(人读的字符串)、`kind`、
   `content`、`locations`、`raw_input`(`acp.start_tool_call(...)` 的实参,acp_adapter/tools.py:1067-1070 / 1098-1100 等 16 处)。
   内核工具名只被用来**选** kind 和**拼** title;对不认识的工具名,title 就是名字本身
   (`build_tool_title` 的最后一行 `return tool_name`,acp_adapter/tools.py:188)。
   **相关性靠 id,不靠名字。** 因此「名字对不上」这种错在本片结构上不可能发生。

2. **但三张表之间的错位是真实的、可枚举的**,而且各有后果:
   - **A 组(5 个,ACP 可见但无 kind)** → 编辑器给它们统一画 `other` 图标。
     其中 `memory` 与 `session_search` 是「操作员循环」里的高频工具(它们在 `_POLISHED_TOOLS` 里、
     有专门的 title 分支和结果美化器),**唯独漏在 kind 表外** —— 这不是设计,是漏登记。
   - **B 组(3 个)** 说明 kind 表是照「全仓工具」写的,不是照 ACP 面写的;
     `_thinking` 更是个伪工具名(kind `think`)。
   - **C 组(2 个)**:`browser_cdp` / `browser_dialog` 是三张表都漏掉的两个 —— 它们走
     `_build_tool_start` 的**通用兜底**分支(acp_adapter/tools.py:1289-1298),把整个 arguments dump 成 JSON 文本,
     并且是唯一会带 `raw_input=arguments` 的路径(见 ■3:那个三元表达式其实是死分支)。
   - **D 组(28 个)** 说明 `_POLISHED_TOOLS` 是「全仓所有值得美化的工具」的集合,
     被 ACP 面**复用**而非**为 ACP 面裁剪**:它包含 28 个 ACP 面根本看不见的工具
     (Home Assistant、kanban、飞书、Discord、yb……),其中 `cronjob` 甚至有专门的
     title 分支(acp_adapter/tools.py:184-187)和结果美化器(acp_adapter/tools.py:923)——**这些代码在 ACP 通道上不可达**。

3. **有没有内核工具在 ACP 面上不可见?有,而且是绝大多数。** ACP 面固定就是
   `hermes-acp` 这一个 composite toolset(+ 每个已配置 MCP 服务器一个 `mcp-<name>` toolset),
   写死在建 agent 的 kwargs 里:

`acp_adapter/session.py:623 @ 863e313`

```python
        kwargs = {
            "platform": "acp",
            "enabled_toolsets": _expand_acp_enabled_toolsets(
                ["hermes-acp"],
                mcp_server_names=configured_mcp_servers,
            ),
            "quiet_mode": True,
            "session_id": session_id,
            "session_db": self._get_db(),
            "model": model or default_model,
        }
```

   注意 `["hermes-acp"]` 是**字面量**,不读配置。所以 `website/docs/user-guide/features/acp.md:275-276`
   那句「`platform_toolsets.acp` does not narrow the ACP toolset, so it cannot be used to drop `terminal`」
   **是成立的**(搜索面见 §7 负结论-1)。

### §3.10 渲染层的三张分支表

| 表 | 条数 | 位置 | 兜底 |
|---|---|---|---|
| `build_tool_title` 的逐工具分支 | 23 | acp_adapter/tools.py:94-188 | `return tool_name` |
| `_build_tool_start` 的逐工具分支 | 16(15 个 `==` + 1 个 `in _POLISHED_TOOLS`) | acp_adapter/tools.py:1073-1298 | 通用 JSON dump |
| `_build_polished_completion_content` 的美化器 | 21 | acp_adapter/tools.py:902-924 | `_format_generic_structured_result` |

```verify
cd /home/user/hermes-agent && sed -n '94,188p'   acp_adapter/tools.py | grep -cE '^\s+if tool_name == '        # 23
cd /home/user/hermes-agent && sed -n '1073,1298p' acp_adapter/tools.py | grep -cE '^\s+if tool_name (==|in) '  # 16
cd /home/user/hermes-agent && sed -n '902,924p'  acp_adapter/tools.py | grep -cE '^\s+"[a-z_]+": lambda'       # 21
cd /home/user/hermes-agent && sed -n '902,924p'  acp_adapter/tools.py | grep -oE '^\s+"[a-z_]+"' | tr -d ' "' | tr '\n' ' '
# todo read_file write_file patch search_files execute_code process delegate_task session_search memory
# skill_view skill_manage web_search web_extract browser_navigate browser_snapshot browser_vision
# browser_get_images vision_analyze image_generate cronjob
```

### §3.11 ACP 输入内容块 → OpenAI 内容部件:5 种块,3 条转换路径

`_content_blocks_to_openai_user_content`(acp_adapter/server.py:515)处理的块类型与产物:

| ACP 块类型 | 处理分支 | 产物 |
|---|---|---|
| `TextContentBlock` | acp_adapter/server.py:529 | `{"type":"text",...}` |
| `ImageContentBlock` | acp_adapter/server.py:534 | `{"type":"image_url",...}`,data 或 uri,data 无 `data:` 前缀时补 `data:<mime>;base64,` |
| `ResourceContentBlock`(resource_link) | acp_adapter/server.py:539 | 读本地文件:图片 → 文本头 + `image_url` data URL;文本 → 内联正文;二进制 → 「omitted」说明 |
| `EmbeddedResourceContentBlock` | acp_adapter/server.py:546 | `TextResourceContents` → 直接内联;`BlobResourceContents` → base64 解码后同上 |
| `AudioContentBlock` | **无分支** | 静默丢弃(只出现在类型标注里,acp_adapter/server.py:483/518) |

三条不变量,都是「为了不破坏旧路径」:
- 上限 `_MAX_ACP_RESOURCE_BYTES = 512 * 1024`(acp_adapter/server.py:212),超了截断并在正文里注明;
- **全是文本部件时退回成一个字符串**(acp_adapter/server.py:560-561),这样斜杠命令解析与纯文本 provider 走原路径;
- 一个非文本块都没有时,退回 `_extract_text(prompt)`(acp_adapter/server.py:554-555)。

Windows/WSL 路径互译是 `_path_from_file_uri`(acp_adapter/server.py:270):`file:///C:/x` 与 `C:\x` 都译成 `/mnt/c/x`。

---

## §4 端到端链:编辑器里点「同意」到文件真的被改

场景:Zed 里用户说「把 README 里的版本号改成 2.0」,模型决定调 `write_file`,当前模式是 `Default`。
**逐跳,每跳带锚点。** 两端接谁在跳 0 和跳 13 写明。

**跳 0(片外,上游)** 编辑器起子进程 `hermes-acp` → `hermes_cli/main.py:11050` 的
`from acp_adapter.entry import main as acp_main`;或直接 `python -m acp_adapter` →
`acp_adapter/__main__.py:3`。`entry.main()` 在 `acp_adapter/entry.py:271` 交给
`asyncio.run(acp.run_agent(agent, use_unstable_protocol=True))`,SDK 从此开始读 stdin 的 JSON-RPC 帧。

**跳 1** `session/prompt` 帧到达 → SDK 路由到 `HermesACPAgent.prompt`(`acp_adapter/server.py:1628`)。
取会话(`:1641`)、抽文本(`:1646`)、转多模态内容(`:1647`)。

**跳 2** 不是斜杠命令、会话空闲 → `state.is_running = True`(`:1752`),记下当前 prompt 文本供 cancel 用。

**跳 3** 在事件循环线程上造 4 个回调 + 2 个审批桥(`:1786`-`:1813`)。
其中编辑审批桥:

`acp_adapter/server.py:1806 @ 863e313`

```python
                from acp_adapter.edit_approval import make_acp_edit_approval_requester

                edit_approval_requester = make_acp_edit_approval_requester(
                    conn.request_permission,
                    loop,
                    session_id,
                    auto_approve_getter=lambda: self._edit_approval_policy_for_state(state),
                )
```

**跳 4** `_run_agent`(`:1851`)被 `contextvars.copy_context().run` 包着丢进
`_executor`(4 线程的 ThreadPoolExecutor,`:199`)—— `:1956`-`:1957`。
在**执行线程内**才绑三件事(注释 `:1833`-`:1845` 解释了为什么必须在线程内):
线程本地的命令审批回调(`:1885`)、ContextVar 的编辑审批 requester(`:1892`)、
ContextVar 的 interactive 标志(`:1899`)。

**跳 5** `agent.run_conversation(...)`(`:1908`)。模型回一个 `write_file` 的 tool_call。

**跳 6(片外,内核)** `agent/tool_executor.py:701` 先发进度事件:

`agent/tool_executor.py:701 @ 863e313`

```python
    if agent.tool_progress_callback:
        try:
            display_args = (
                _redact_tool_args_for_display(function_name, function_args)
                or function_args
            )
            preview = _build_tool_preview(function_name, display_args)
            agent.tool_progress_callback(
                "tool.started", function_name, preview, display_args
            )
```

**跳 7** 回到本片:`acp_adapter/events.py:134` 的 `_tool_progress` 只认 `"tool.started"`(`:136`),
铸一个 `tc-<uuid12>` id(`:146`,来自 `acp_adapter/tools.py:89`),按**工具名**压进 FIFO 队列(`:148`-`:154`),
存 args + 编辑快照(`:156`-`:164`),按当前策略试算「会不会被自动放行」以决定要不要提前把 diff 塞进
start 通知(`:166`-`:177`),然后 `build_tool_start` → `_send_update`(`:179`-`:180`)。

**跳 8** `_send_update`(`acp_adapter/events.py:87`)是**唯一的跨线程出口**:
`safe_schedule_threadsafe(conn.session_update(...), loop, ...)`(`:96`)+ `future.result(timeout=5)`(`:105`)。
编辑器此刻画出一个 `edit` 类型的工具卡片。

**跳 9(片外,共享派发器)** 工具真正派发前,`model_tools.handle_function_call`(`model_tools.py:1123`)
里插着 ACP 的编辑审批闸:

`model_tools.py:1350 @ 863e313`

```python
        # ACP/Zed edit approval runs before any file mutation.  The requester
        # is bound via ContextVar only for ACP sessions, so CLI/gateway paths
        # are unaffected when it is unset.
        try:
            from acp_adapter.edit_approval import maybe_require_edit_approval

            edit_block_message = maybe_require_edit_approval(function_name, function_args)
```

**注意这一跳的位置**:闸不在 ACP adapter 里,在**全仓共享的工具派发器**里,靠 ContextVar 是否绑定来开关。
这是本片最重要的一个结构选择,§5.9 单独展开。

**跳 10** `maybe_require_edit_approval`(`acp_adapter/edit_approval.py:233`)取出 requester(非 None),
`build_edit_proposal("write_file", args)`(`:245` → `:181`)读现有文件内容当 `old_text`(`:92` → `:73`),
造 `EditProposal`。`_requester`(`:295`)先问自动放行策略(`:299`-`:306`),`ask` 档不放行,
于是 `build_acp_edit_tool_call`(`:312` → `:264`)造一个 `kind="edit"`、内容是
`acp.tool_diff_content(path, old_text, new_text)` 的 `ToolCallUpdate`,
经 `safe_schedule_threadsafe`(`:318`)发出 `session/request_permission`,
`future.result(timeout=60)`(`:327`)**阻塞执行线程**等答复。

**跳 11** 用户点 Allow edit → 判定极窄:

`acp_adapter/edit_approval.py:332 @ 863e313`

```python
        outcome = getattr(response, "outcome", None)
        return (
            getattr(outcome, "outcome", None) == "selected"
            and getattr(outcome, "option_id", None) == "allow_once"
        )
```

返回 True → `maybe_require_edit_approval` 返回 `None` → 派发继续。
(任何异常、超时、别的 option_id、`outcome != "selected"` 一律 False,即**拒绝**。)

**跳 12(片外)** `write_file_tool`(`tools/file_tools.py:1757`)先过内核自己的敏感路径闸
(`:1768` `sensitive_err = _check_sensitive_path(path, task_id)`),再落盘。

**跳 13** 结果回流:`agent` 在下一步调用 `step_callback` →
`acp_adapter/events.py:223` 的 `_step` 从 FIFO 队列 popleft 拿回 `tc_id`(`:242`),
`build_tool_complete`(`:244` → `acp_adapter/tools.py:1305`)算出 `status="completed"`(或 `"failed"`,
判据 `_tool_result_failed`,`acp_adapter/tools.py:213`)与美化内容,再走 `_send_update`。
回合结束后 `prompt()` 回到事件循环线程:落历史(`acp_adapter/server.py:1965`-`:1968`)、
检测压缩换 id 并补发 provenance(`:1974`-`:1992`)、必要时补发最终答复(`:2041`-`:2052`)、
排空队列(`:2061`-`:2074`)、发 usage(`:2086`)、最后 `return PromptResponse(...)`(`:2089`)
—— SDK 把它序列化成 `session/prompt` 的响应帧写回 stdout,**编辑器的转圈停下**。

---

## §5 逐机制结构笔记

### §5.1 `entry.py`:启动顺序本身是机制

三件事的顺序不能换:

1. **`import hermes_bootstrap` 必须是第一个 import**(acp_adapter/entry.py:18),为的是 Windows 上的 UTF-8 stdio;
   随后 `hermes_bootstrap.harden_import_path()`(:30)防止**启动目录**里的 `utils/` / `proxy/` / `ui/`
   包遮蔽 hermes 自己的模块 —— `hermes acp` 可以从任意项目目录被编辑器拉起,这是真实风险。
   `ModuleNotFoundError` 时**静默降级**(:20-25),理由写在注释里:`hermes update` 半途而废时
   git 已 reset 到新代码但 `uv pip install -e .` 没跑完。
2. **日志全部改道 stderr**(`_setup_logging`,:81),因为 stdout 是协议通道。
3. **`.env` 从 `HERMES_HOME` 加载**(`_load_env`,:102)。

**探针噪声抑制**(:41-78)是一个很好的「协议正确但体验糟糕」的样本:客户端(如 acp-bridge)
周期性发 `ping` 当心跳;ACP 路由器**正确地**回 `-32601 method not found`;但 SDK 的调度任务随后
用 `logging.exception("Background task failed")` 把 traceback 打到 stderr,每个探针周期一次。
`_BenignProbeMethodFilter` 的判据窄到不能再窄:消息**恰好**是 `"Background task failed"`、
异常是 `RequestError`、code **恰好** `-32601`、且 `data["method"]` 在
`frozenset({"ping", "health", "healthcheck"})` 里 —— 四条全中才吞。协议响应一字不改。

**MCP 冷启动**(:258-267):默认在后台守护线程里跑 `start_background_mcp_discovery`,
免得 `asyncio.run()` 被 2-5 秒的 MCP 连接阻塞;`HERMES_ACP_SKIP_CONFIGURED_MCP=1` 可以整个跳过
(供自己管 MCP 的宿主用)。判据是**严格等于 `"1"`**,别的真值串都不算。

### §5.2 `auth.py`:79 行的认证面

ACP 官方注册表要求 agent 在握手时至少 advertise 一个可用的认证方式。hermes 的做法:

- `detect_provider()`(:11)委托给 `hermes_cli.runtime_provider.resolve_runtime_provider()`;
  **关键判据是 `api_key` 可以是 `Callable`**(:28 `is_callable_provider = callable(api_key) and not isinstance(api_key, str)`)
  —— Azure Foundry 的 Entra ID 是「bearer token 提供函数」而不是字符串密钥;
  没有这一条,Entra 配置的部署会静默回落成 `"openrouter"` 而握手拒掉合法 provider。
  这是一个「鸭子类型的凭据」在类型判定上留下的坑,值得记住。
- `build_auth_methods()`(:41)**恒发**一个 `TerminalAuthMethod(id="hermes-setup", args=["--setup"])`,
  有凭据时**追加**一个 `AuthMethodAgent(id=<provider>)`。所以列表长度是 1 或 2,不会是 0。
- `authenticate`(acp_adapter/server.py:1173)反过来收窄:`method_id` 必须**等于**当前探到的 provider
  (小写比较),或者等于 `hermes-setup` 且此刻**已经**有 provider(终端设置流走完了)。
  注释(acp_adapter/server.py:1174-1179)自陈这是 API 卫生而非安全边界:「ACP is stdio-only, local-trust」。

### §5.3 `session.py`:会话管理与三层身份

**三个 id 要分清**,这是本片最容易读混的地方:

| 名字 | 谁给的 | 会变吗 | 用途 |
|---|---|---|---|
| ACP `session_id` | `SessionManager.create_session` 的 `uuid4()`(acp_adapter/session.py:204) | **不变**,是对编辑器的稳定句柄 | 协议里的会话标识、`task_id`、`HERMES_SESSION_ID` |
| 内部 hermes `agent.session_id` | 建 agent 时传入,但**压缩会换** | 会变 | SessionDB 的行主键 |
| `tool_call_id` | `tc-<uuid12>`(acp_adapter/tools.py:89);历史回放时改用 provider 的原 id(acp_adapter/server.py:1328) | 每次调用一个 | 关联 start / complete 通知 |

**持久化**:落 SessionDB(`source="acp"`),`_restore`(:497)在内存里找不到时**透明地**从 DB 重建
——包括重建 `AIAgent`。所以 ACP 会话**跨进程重启存活**,并出现在 `session_search` 里。
`get_session`(:220)先查内存再回落 `_restore`,这意味着一次「查一下在不在」可能有**建一个新 agent**
的副作用 —— `_schedule_mcp_late_refresh` 里专门为此只查内存字典(acp_adapter/server.py:1087-1093 的注释点名了这件事)。

**`_persist` 里最精细的一段**(:453-493)值得完整理解,它是三次事故的沉积:
agent 自己往同一个 DB 增量 flush 时,再调 `replace_messages()` 就是二次写,而且会 DELETE 掉
`archive_and_compact()` 留下的 `active=0/compacted=1` 归档行 —— 长到发生过压缩的 ACP 对话会**静默丢历史**。
判据是「agent 是否自己拥有持久化」(`agent._session_db is db and agent._session_db_created`);
即使不拥有(换模型 / `/restore` 会铸一个 `_session_db_created=False` 的新 agent),
也要先问 `db.has_archived_messages()`,有归档就只替换 `active=1` 那一份。

**WSL cwd 互译**贯穿全文件:`_translate_acp_cwd`(:29,写入/执行用)与
`_normalize_cwd_for_compare`(:43,过滤/比较用)是**两套**,后者还额外把 `/mnt/E/` 折成 `/mnt/e/`(:56-57)。
理由:Windows 的 Zed 可以把 `hermes acp` 起在 WSL 里,却把工作区当作 `E:\Projects` 发过来。

**`_make_agent`(:590)是本片唯一造 agent 的地方**,四个调用点(create / fork / restore / 换模型)全走它。
它做的事:读 config 取默认模型与 provider、收集**启用的** MCP 服务器名(:617-621,`enabled: false` 被剔除)、
拼 kwargs(§3.9 引过)、试 `resolve_runtime_provider`(:636,失败只 debug 不抛)、
**有界等待 MCP 发现**(:665-673,`ensure_mcp_discovery_before_agent_build`,默认约 1.5s)、
最后两笔收尾:`agent.session_cwd = cwd`(:679,给 Codex runtime 用)与
`agent._print_fn = _acp_stderr_print`(:682,把 agent 顺手 print 的东西赶到 stderr)。

### §5.4 `server.py`:生命周期、并发模型、并发不变量

**并发模型**(要一句话讲清):事件循环独占主线程;每个 `prompt()` 把同步的 agent 丢进一个
**全模块共享的 4 线程池**(`_executor`,:199);跨向用 `run_coroutine_threadsafe`,
跨回用 `loop.run_in_executor` 的 future。所以:

- **最多 4 个 ACP 会话能同时跑回合**,第 5 个排在 executor 队列里(编辑器看不出区别,只是慢)。
- 线程池会**复用线程**,于是每一样「线程可见的状态」都必须存取对称。代码里三处显式对称:
  线程本地审批回调(存旧的 :1884、还回去 :1930)、`HERMES_SESSION_ID` 环境变量(:1905 存、:1923-1926 还)、
  编辑审批 ContextVar token(:1892 设、:1937 reset)。
- **为什么用 ContextVar 而不是环境变量**:注释 :1836-1842 直接点了 GHSA-96vc-wcxf-jjff ——
  `os.environ["HERMES_INTERACTIVE"]` 是进程全局的,一个会话的 `/restore` 能把另一个会话
  掉到「非交互自动放行」路径上。改成 contextvar + `copy_context()` 包住 executor 调用后,
  每个 worker 只看见自己的值。

**每会话的并发不变量**由 `SessionState.runtime_lock` 守着(acp_adapter/session.py:170)。
`is_running` 的翻转、`queued_prompts` 的进出、`interrupted_prompt_text` 的交接,全在锁内。
两个非平凡场景:

- **cancel 与新 prompt 的竞态**(:1543-1558):`cancel` 在**同一把锁内**先把
  `current_prompt_text` 挪到 `interrupted_prompt_text`、再置 cancel_event、再 hard interrupt,
  免得另一个 prompt 抢到锁后把这个回合误判成「可重定向的活干」。
- **MCP 迟到刷新与首个回合的竞态**(:1105-1116):后台守护线程要重建工具表,
  但重建会破坏 prompt cache 前缀;于是它**持 `runtime_lock`** 检查 `is_running` 与
  `_user_turn_count`/`_api_call_count` 都为 0 才动手,把「守卫过了但首个 prompt 已经起跑」那个窗口关掉。

**`prompt()` 的输入分流**(:1646-1768),按判定顺序:

```text
1. 空内容                        → PromptResponse(end_turn),什么都不做
2. 纯文本 且 以 "/steer" 开头 且 会话空闲
     ├─ 有 interrupted_prompt_text → 重写成「原 prompt + 用户中断后的更正」
     └─ 否则                        → 重写成普通 prompt(否则会伪装成 /queue 的回执)
3. 纯文本 且 不以 "/" 开头 且 会话空闲 且 有 interrupted_prompt_text
                                  → 把被取消的 prompt 拼在前面(支持「停下,不是那个文件」)
4. 纯文本 且 以 "/" 开头          → 斜杠命令拦截(认识就本地答,不认识返回 None 落给模型)
5. 会话正在跑
     ├─ 纯文本 且 agent 支持 _supports_active_turn_redirect → agent.redirect()
     └─ 否则                     → 排队(**图片在这里被丢掉**,见 ■2)
6. 其余                          → 正式起跑
```

**历史回放**(`_replay_session_history`,:1337)是 `session/load` / `session/resume` 必须在**响应之前**
`await` 完的动作 —— 注释 :1470-:1479 说明了为什么不能 `loop.call_soon` 延后:
Zed 在 await loadSession 之前就注册好了 session-update 路由,正是为了让「请求生命周期内」的回放能找到线程;
2026 年 5 月延后过一次,把所有守规矩的客户端都弄坏了(#12285 后续)。
回放会重建 4 类东西:user/assistant 文本块、reasoning 思考块、tool_call 的 start、tool 结果的 complete,
外加 `todo` 结果重建的原生 plan 更新。**压缩摘要**被打上 `_meta.hermes.compactionSummary` 或
`containsCompactionSummary`(:1246-1281),两个键分开的理由写得很清楚:整块都是摘要的可以整体折叠,
而「真内容 + 尾部追加摘要」的合并型如果整体折叠就把真内容藏了。

**usage 面**(`_build_usage_update`,:843):Zed 的环形上下文指示器由 `usage_update` 驱动,
`size` 取 `compressor.context_length`,`used` 用 `estimate_request_tokens_rough(history, system_prompt, tools)`
—— **和真正发给 provider 的三个桶一致**,不是只数 transcript。估算失败回落
`compressor.last_prompt_tokens`。`size <= 0` 时干脆不发。

**模型选择器**(`_build_model_state`,:699)复用全仓共享的 model inventory
(`hermes_cli.inventory.build_models_payload`),再补上「命名自定义端点」这一类
(`_named_custom_provider_catalogs`,:90)—— 后者不出现在规范 provider 枚举里,所以 TUI 的 `/model`
能看见而 ACP 选择器看不见(#47039 只做了 TUI)。选择 id 编码成 `provider:model`
或 `custom:<name>:<model>`(`_encode_model_choice`,:689),能原样被 `parse_model_input` 解回来。
每 provider 上限 `ACP_MAX_MODELS_PER_PROVIDER = 200`(:211),理由是客户端把整个
`availableModels` 数组塞进一个下拉框。

**未使用的客户端能力**:`initialize` 收下 `client_capabilities`(:1142)后**既不存也不用**;
本片不出现任何 `fs/read_text_file`、`fs/write_text_file`、`create_terminal` 的调用。

```verify
cd /home/user/hermes-agent && grep -rn 'read_text_file\|write_text_file\|create_terminal' acp_adapter/
# 期望: 无输出(hermes 作为 ACP 服务端从不调用客户端的文件/终端能力)
```

设计后果:编辑器里的未保存缓冲区、编辑器自己的终端面板,hermes 都用不上;
它直接读写磁盘、自己起子进程。好处是 CLI / gateway / ACP 三条通道**共用同一套工具语义**;
代价是「编辑器里改了没存」的内容 hermes 看不见。

### §5.5 `events.py`:回调桥的三个设计点

1. **FIFO 队列按工具名**(:148-154):`Dict[str, Deque[str]]`。并行的同名调用(两个 `read_file`)
   如果只存一个 id,完成事件就会挂到错的那一次上。代码还兼容「历史上这里存的是 str」的形状
   (:151-153 把 str 升级成单元素 deque)—— 一处向下兼容的痕迹。
2. **`todo` → ACP 原生 plan**(`_build_plan_update_from_todo_result`,:39):Zed 把
   `sessionUpdate: plan` 渲染成一等公民的任务面板。翻译里有一个必须记住的取舍:
   ACP 的 plan 只有 `pending/in_progress/completed` 三态,hermes 有 `cancelled`;
   映射成 `completed` 并在正文前加 `[cancelled] `(:80-81),理由是客户端做的是**整表替换**,
   直接丢掉会让用户看着任务凭空消失。
3. **`_json_loads_maybe_prefix`**(:28):hermes 的工具有时在 JSON 后面追加人读的提示
   (`{...}\n\n[Hint: ...]`),所以用 `JSONDecoder().raw_decode` 解第一个 JSON 值。

`thinking_callback` 被显式设成 `None`(acp_adapter/server.py:1828),`reasoning_callback` 才接
`make_thinking_cb` 的产物(:1829)。理由在注释 :1825-1827:ACP 的思考面板不该收 hermes 本地的
「kawaii 等待/状态」文案;provider 不出 reasoning 时,Zed 不该看到一个假的 thinking 折叠块。

### §5.6 `tools.py`:1,347 行几乎全是渲染

结构是三段:名字→kind/title(§3.8、§3.10)、结果美化器(21 个)、start/complete 组装。
两个跨全文件的不变量:

- **渲染永不中断回合**:`build_tool_start`(:1043)整体 try/except,
  任何异常都回落成一个「最小但合法」的 start 事件(:1067-1070)。注释说明这与
  `agent/display.py` 的 `get_cute_tool_message` 是同一个理由 —— 模型可能给出不符 schema 的参数
  (非字符串的 `command`/`path`),而 start 事件在实时回调**和历史回放**两条路上都会走。
- **失败判定刻意保守**(`_tool_result_failed`,:213):只认三类信号 ——
  `"Error executing tool '"` 前缀(内核工具执行器唯一产出的包装,普通输出造不出来)、
  结构化 `success/ok is False`、非零 `exit_code/returncode`;
  再加一条窄口子:**只有** `_POLISHED_TOOLS` 里的工具,`{"error": ...}` 且无 `content` 才算失败。
  理由:纯文本里出现 "error" 太常见(测试失败、命令打诊断),不该在 Zed 里标红。

`_parse_unified_diff_content`(:943)自己手写了 unified diff 解析,把 `--- / +++ / @@` 拆成
ACP 的 diff 内容块;只在 `skill_manage` 上用(:1014-1027),因为 `skill_manage` 的结果里带 diff 文本。
`_fenced_text`(:257)算出比正文里最长反引号串更长的围栏,防止工具输出里的反引号破坏 Markdown ——
小,但是渲染层该有的严谨。

### §5.7 `provenance.py`:它在标记什么的来源、为什么需要

**标记的是「ACP 会话句柄」与「内部 hermes 会话 id」之间的血统关系。**

问题的形状:ACP 的 `session_id` 必须对编辑器保持稳定(编辑器用它路由所有通知),
但 hermes 的**上下文压缩会在内部换一个新的 DB 会话 id**(把旧的以 `end_reason='compression'` 结束、
新建一个 `parent_session_id` 指向它的子会话)。于是编辑器面前是一条连续的对话,
而 `state.db` 里是一条链。客户端如果想知道「刚才发生了压缩」,不借助本模块只能:
解析状态文案、从 token 数骤降猜、或者直接读 `state.db` —— 三条都不该是客户端干的事(模块 docstring :9-11)。

**设计上的三条自我约束**,都值得抄:

1. **零新增持久状态**:全部从 `sessions` 表已有的 `parent_session_id` / `end_reason` **现推**(:2-7)。
2. **挂在 `_meta.hermes` 下**(:1-3):ACP 的扩展通道,不认识的客户端直接忽略,不破坏兼容。
3. **走链有界**:`_MAX_WALK = 100`(:19)+ `seen` 集合防环(:60、:62)。

判据的精细处:`parent_session_id` 这一列被压缩子会话、delegate 子会话、branch 子会话**共用**,
所以 `compressionDepth` 只数 `parent.end_reason == 'compression'` 的那些跳(:72-73);
`sessionKind` 看**直接父**的 `end_reason`(:78-85);`rotated` 只在 `prompt()` 传了
`previous_hermes_session_id` 且与当前不同时为真(:87-90),这时才补
`reason="compression"` / `creatorKind="compression"`(:104-106)。
产出的 6~8 个字段列全:`acpSessionId`、`currentHermesSessionId`、`rootHermesSessionId`、
`parentHermesSessionId`、`sessionKind`、`compressionDepth`,可选 `previousHermesSessionId`、
`reason`、`creatorKind`。

发出时机三处:`new_session` / `load_session` / `resume_session` 的响应 `field_meta`
(acp_adapter/server.py:1451、:1499、:1535),以及回合内检测到换 id 后补一条 `session_info_update`
(acp_adapter/server.py:1974-1992)。

### §5.8 权限模型:`permissions.py` 与 `edit_approval.py` 各自的判据面

**这两个文件是两个不同的面,不是一个面的两半。** 表格是本节的主要产出:

| | `acp_adapter/permissions.py` | `acp_adapter/edit_approval.py` |
|---|---|---|
| 拦什么 | 危险**命令**(terminal 家族) | 文件**编辑**(`write_file` / `patch`) |
| 判据在哪 | **不在本文件**。判据是 `tools/approval.py` 的命令文本模式匹配;本文件只做选项映射 | **在本文件**:`build_edit_proposal` 按**工具名**决定「这算不算一次编辑」 |
| 装配方式 | `tools/terminal_tool.set_approval_callback`,**线程本地**(acp_adapter/server.py:1885) | `set_edit_approval_requester`,**ContextVar**(acp_adapter/server.py:1892) |
| 触发点 | 内核 `check_all_command_guards` 内部,只有走 `terminal_tool` 的调用会到 | 共享派发器 `model_tools.py:1356`,**每个工具调用都会到** |
| 选项数 | 5(§3.7) | 2:`allow_once` / `deny` |
| 自动放行 | 有,但在内核:session/permanent allowlist 按 `pattern_key` 缓存 | 有,在本文件:`should_auto_approve_edit` 按**模式 + 路径** |
| 敏感例外 | 内核的 hardline / user deny rules | `SENSITIVE_AUTO_APPROVE_NAMES` + 路径含 `.git`/`.ssh` 段 |
| 超时 | 60s → 返回 **`"timeout"`**(与 deny 区分,:167) | 60s → 返回 **False**(与 deny 不区分,:327-331) |
| 展示前脱敏 | **有**:`tools/approval.py:2764-2766` 过 `redact_sensitive_text` | **无**:文件原文直接进 `tool_diff_content`(:276-280) |
| 生效范围 | 只在当前 executor 线程 | 当前上下文及其 `copy_context()` 副本(含 delegate 子 agent,见 §7 推定-2) |

`edit_approval.py` 的模块 docstring 把它的隔离性说得非常直白:

`acp_adapter/edit_approval.py:1 @ 863e313`

```python
"""Pre-execution ACP edit approval helpers.

This module is intentionally isolated from the generic tool registry.  ACP binds
an edit approval requester in a ContextVar for the duration of one ACP agent run;
CLI, gateway, and other sessions leave it unset and therefore bypass this guard.
"""
```

**编辑提案的构造是三条独立路径**(每条都可能抛,抛了就 fail-closed 拒绝,`maybe_require_edit_approval` :244-248):
- `write_file` → `_proposal_for_write_file`(:82):`old_text` 读现有文件(不存在则 None,即新建)。
- `patch` + `mode="replace"` → `_proposal_for_patch_replace`(:98):**真的跑一遍**
  `tools.fuzzy_match.fuzzy_find_and_replace`(:111-118)算出 `new_text`,匹配不到就抛 ——
  所以「拒绝的 patch 不可能改到文件」这条保证是靠**先算后审**实现的,不是靠事后回滚。
- `patch` + `mode="patch"`(V4A 格式)→ `_proposal_for_patch_v4a`(:155):
  正则抽 `*** Update/Add/Delete File:` 与 `*** Move File: a -> b`(:133-151);
  **多文件时 `old_text=None`、`new_text` 直接是整段 patch 原文**(:164-174),
  注释说明 ACP 这里只支持一个 diff 负载,所以选择「把原文摆出来」而不是「不审」。

### §5.9 核心比较题:ACP 的审批面、tui_gateway 的审批面、内核自己的审批闸,是同一套还是三套?

**结论:是「一个判据核心 + 三条投递通道」,外加两个内核里独立的效果级闸,再外加 ACP 独有的第四个面。
既不是同一套,也不是三套。**

先把面数清。全仓一共 **5 个** 会拦住一次工具调用的闸:

| # | 闸 | 判据是什么 | 谁来答 | 只覆盖哪些工具 |
|---|---|---|---|---|
| 1 | 危险命令闸 `tools/approval.py:3738` 的 `check_all_command_guards` | **命令文本**的模式匹配 → `pattern_key` | 三条通道(下表) | 走 `terminal_tool` 的调用 |
| 2 | execute_code 整段脚本闸 `tools/approval.py:4229` 的 `check_execute_code_guard` | 整段脚本,一次 | **只有** gateway 队列 / `HERMES_EXEC_ASK` | `execute_code` |
| 3 | 敏感路径闸 `tools/file_tools.py:675` 的 `_check_sensitive_path` | **路径**前缀/精确匹配 + hermes config 路径 | 没人答,硬拒 | `write_file` / `patch` 内部 |
| 4 | 写审批闸 `tools/write_approval.py:253` 的 `evaluate_gate` | **子系统**(memory / skills),**默认关** | inline 提示 或 落盘暂存(`/memory pending`) | `memory` / `skill_manage` |
| 5 | **ACP 编辑审批** `acp_adapter/edit_approval.py:233` 的 `maybe_require_edit_approval` | **工具名 ∈ {write_file, patch}** | ACP `request_permission`(**编辑器/宿主程序**) | `write_file` / `patch` |

闸 1 的**三条投递通道**由 `check_all_command_guards` 内部同一段代码分派:

| 通道 | 判据 | 装配 | 谁用 |
|---|---|---|---|
| ① 交互回调 | `_is_interactive_cli()`(tools/approval.py:85,先看 ContextVar,回落 `HERMES_INTERACTIVE`) | `tools/terminal_tool.set_approval_callback`,线程本地 | **CLI 与 ACP** |
| ② gateway 队列 | `_is_gateway_approval_context()`(tools/approval.py:244)或 `HERMES_EXEC_ASK` | `register_gateway_notify(session_key, cb)`,按会话键 | **tui_gateway** 与各聊天平台 |
| ③ 无人兜底 | 都不成立 | 无 | cron 按 `approvals.cron_mode`;其余**自动放行**(命令路径的历史 fail-open 默认) |

tui_gateway 走的确实是通道 ②:`tui_gateway/server.py:3098` 设
`os.environ["HERMES_GATEWAY_SESSION"] = "1"`,`:2193` / `:4818` / `:6570` 三处
`register_gateway_notify`,答复入口是 `tui_gateway/methods_prompt.py:915` 的
`@method("approval.respond")` → `resolve_gateway_approval`。
ACP 走通道 ①:`acp_adapter/server.py:1885` 装线程本地回调、`:1899` 置 interactive ContextVar。
`tools/terminal_tool.py:257` 的注释把这个分工写死了:「Gateway mode resolves approvals via the
per-session queue in tools.approval, not through these callbacks」。

所以:**闸 1 是同一套判据 + 同一段分派代码,ACP 与 tui_gateway 只是落在不同分支上。
闸 5 是 ACP 独有的、别人根本不存在的第四个面。**

#### 用 ACP 通道检验既有结论「守卫认的是工具名,不是效果;要紧的不是装了几处,是装在了哪一层」

**判定:两句都成立,但都需要改述。ACP 通道给出三条独立的取证。**

**改述一:「认工具名」发生在两级,不是一级。**

- **第一级(挂闸)恒按工具名 / 调用入口。** 一个工具要么被挂在某个闸上,要么根本不过任何闸。
  这一级没有例外:闸 1 只覆盖走 `terminal_tool` 的调用,闸 3 只在 `write_file_tool` / patch 内部,
  闸 4 只被 `memory_tool` 与 `skill_manager_tool` 主动调用,闸 5 只认两个名字。
- **第二级(闸内判定)有的按效果、有的按名字。** 闸 1 判**命令文本**、闸 3 判**路径**
  —— 这两个是效果级的,同一个效果换写法(`sed -i` vs `tee` vs `>`)照样被抓。
  闸 5 判的还是**名字**:进了闸门之后,它做的第一件事仍然是 `if tool_name == ...`:

`acp_adapter/edit_approval.py:178 @ 863e313`

```python
def build_edit_proposal(tool_name: str, arguments: dict[str, Any]) -> EditProposal | None:
    """Return an edit proposal for supported file mutation calls."""

    if tool_name == "write_file":
        return _proposal_for_write_file(arguments)
    if tool_name == "patch":
        mode = arguments.get("mode", "replace")
        if mode == "replace":
            return _proposal_for_patch_replace(arguments)
        if mode == "patch":
            return _proposal_for_patch_v4a(arguments)
    return None
```

  返回 `None` → `maybe_require_edit_approval` 返回 `None` → 派发继续,**不问、不拦、不记**。

  所以漏洞的形状不是「判据太粗」,而是 **「一个新工具达到了同样的效果,但没被挂到任何闸上」**。

**取证 A —— `skill_manage`:同一对文件里,渲染层和守卫层对「什么是一次编辑」意见不一致。**

渲染层认它是编辑:

`acp_adapter/events.py:156 @ 863e313`

```python
        snapshot = None
        if name in {"write_file", "patch", "skill_manage"}:
            try:
                from agent.display import capture_local_edit_snapshot

                snapshot = capture_local_edit_snapshot(name, args)
            except Exception:
                logger.debug("Failed to capture ACP edit snapshot for %s", name, exc_info=True)
        tool_call_meta[tc_id] = {"args": args, "snapshot": snapshot}
```

`acp_adapter/tools.py:1167`(`_build_tool_start` 的 `skill_manage` 分支)更是直接为它造
`acp.tool_diff_content(...)`,`acp_adapter/tools.py:1014` 还专门为它解 unified diff。
守卫层不认它(上面 `build_edit_proposal` 只有两个名字)。它自己那个闸(闸 4)**默认是关的**:
`tools/write_approval.py:274` 的 `if not write_approval_enabled(subsystem): return GateDecision(allow=True)`,
而 `write_approval_enabled` 的默认值是 `False`(:74-90)。
于是:**ACP 的 `Default` 模式描述是 "Ask before edits."(acp_adapter/server.py:668),但在默认配置下,
`skill_manage` 改 `~/.hermes/skills/` 下的文件,一个提示都不会有** —— 同时编辑器会把它画成一个带 diff 的
`edit` 卡片。见 ■4。

**取证 B —— `execute_code`:ACP 面可见,但两个可能拦它的闸都不生效。**

`execute_code` 在 `hermes-acp` toolset 里(`toolsets.py:421`)。它的专属闸是闸 2,而闸 2 的判据是:

`tools/approval.py:4292 @ 863e313`

```python
    # Only gateway/ask contexts get the one-shot whole-script approval.
    #   * CLI interactive: the script's terminal() calls are guarded per-call
    #     (context now propagates into the RPC thread, #33057); a whole-script
    #     prompt would fire on every execute_code call.
    #   * Local non-interactive non-gateway: documented limitation above.
    if not is_gateway and not is_ask:
        return {"approved": True, "message": None}
```

ACP 会话既不是 gateway(它设的是 interactive ContextVar,不是 `HERMES_GATEWAY_SESSION`),
也不设 `HERMES_EXEC_ASK` —— 基线自己的测试 docstring 把这一点写死了:
`tests/acp/test_approval_isolation.py:152-154`「HERMES_EXEC_ASK takes the gateway-queue path
which requires a notify_cb registered in `_gateway_notify_cbs` — not applicable to ACP,
which uses a direct callback shape」。所以闸 2 在 ACP 上**直接放行**。
剩下的兜底是注释里那句「the script's `terminal()` calls are guarded per-call」——
可是同一个函数的 docstring(`tools/approval.py:4233-4236`)自己声明脚本可以
「call `subprocess`, `os.system`, `ctypes`, or other process/file APIs directly,
none of which pass through `terminal()` / `DANGEROUS_PATTERNS`」。
而闸 5 不认 `execute_code` 这个名字,闸 3 只在 `write_file_tool` 内部。
**净结果:ACP `Default` 模式下,`execute_code` 里一句 `open(p,'w')` 三个闸全不过。** 见 ◇4。

**取证 C —— 内核自己已经知道这个形状,而且是用「人工配对」在补。** 这是本轮最有力的一条:

`tools/approval.py:279 @ 863e313`

```python
# ~/.hermes/config.yaml IS the security policy: approvals.mode, yolo, and the
# permanent-approval allowlist live here, and the config cache is mtime-keyed
# so a write takes effect mid-session (the agent could flip approvals.mode=off
# and immediately bypass the gate). Pair the write_file/patch deny (file_tools
# _check_sensitive_path) with terminal-side coverage so `sed -i`, `tee`, `>`,
# `cp`, etc. targeting it are gated too — otherwise the deny is unpaired
# theater. Mirrors _HERMES_ENV_PATH; matches the HERMES_HOME override form as
# well as ~/.hermes/.
```

「otherwise the deny is unpaired theater」—— 内核在承认:**按工具名挂闸的必然失效模式是
「同一效果换个工具名」,而它的对策是在每个新闸上手工把配对做齐。** 手工配对不可枚举、不可校验,
所以取证 A / B 那两个洞正是这套方法的必然产物,不是疏忽。

**改述二:「装在哪一层」买到的是「哪些调用路径会经过闸」,不是「哪些效果会被拦」。**

ACP 把层次做**对**了,这一点要给足信用。闸 5 **不在 ACP adapter 里**,而在全仓共享的
工具派发器 `model_tools.handle_function_call` 里(§4 跳 9 的逐字块),靠 ContextVar 开关。
后果都是好的:

- **凡是走 `handle_function_call` 的调用都会经过它** —— 包括 delegate 子 agent(`tools/delegate_tool.py:2207`
  与 `:3024` 的 `contextvars.copy_context()`)、`agent/tool_executor.py` 的并发批(经
  `tools/thread_context.py:78` 的 `propagate_context_to_thread` 复制上下文),
  甚至 hermes 把自己工具当 MCP 服务器暴露那条路(`agent/transports/hermes_tools_mcp_server.py:214`)。
  换句话说:**它覆盖的是调用点,而不是 ACP 这个界面。**
- **它对别人零影响**:CLI / gateway 不绑那个 ContextVar,`requester is None` 直接返回
  (acp_adapter/edit_approval.py:240-242)。这是「装深一层但不影响其他通道」的标准做法:
  把钩子装在最深的公共点,把**开关**放在最外层的会话上下文里。
- 失败模式也被想过:`model_tools.py:1372-1389` 里,闸本身抛异常时,
  **只有** `write_file` / `patch` 会被 fail-closed 拦掉,其余工具继续 —— 又一次按名字。

**但层次深度对「效果覆盖」一点帮助都没有。** 闸装在派发器上,意味着 `execute_code` 这个调用
**确实经过了**闸 5 —— 它只是在 `build_edit_proposal` 里拿到 `None` 然后被放走。
**判据决定拦不拦,层次只决定问不问。**

**改述三(ACP 独有,前几轮通道给不出的一条):ACP 是唯一把「谁来答」交给外部程序的通道。**

闸 1 通道 ① 的答复来自本机人类(prompt_toolkit 面板或 `input()`);通道 ② 的答复来自 hermes 自己的
会话队列 + 平台按钮。ACP 的答复来自 **stdio 另一端的宿主程序**,而宿主可以自己答。
仓库文档自己把后果写下来了:

> `website/docs/user-guide/features/acp.md:262 @ 863e313`
> Two behaviors combine on this path. The `hermes-acp` toolset includes `terminal`
> and `execute_code`, and Buzz's ACP bridge answers Hermes' permission requests
> itself with `allow_once` rather than surfacing them. A Hermes agent in Buzz
> therefore runs shell commands on the host without prompting. I asked one to run
> `rm -rf` against a scratch directory and it deleted it, no prompt anywhere.

同页 `:273-274` 还明说 `approvals.mode: manual` 只能让 hermes **发出**请求,拦不住宿主自动同意。
**所以对 ACP 这条通道,「装在哪一层」还要再加一维:闸的判据在 hermes 里,闸的裁决权在客户端里。**
这是 hermes 无法用任何内部层次弥补的 —— 除非它自己再加一道不问客户端的硬闸(闸 3 就是这种,
所以 `~/.hermes/config.yaml` 在 Buzz 上依然写不进去)。

**一句话总括(可直接进成品章):**
> 判据分两级:第一级「挂闸」恒按工具名/调用入口,第二级「闸内判定」才可能按效果。
> 把闸装深(到共享派发器)买到的是调用路径的完备覆盖;把判据写成效果级(命令文本、路径)
> 买到的是同效果换写法照样拦。ACP 通道把前者做对了、后者留在了名字上,
> 并且额外交出了裁决权 —— 于是它同时是这条结论最好的正例和最好的反例。

---

## §6 发现清单

### ■ 代码缺陷(4 条)

**■1 「Deny always」按钮的行为和「Deny」完全一样。**
`acp_adapter/permissions.py:26` 把 `deny_always` 映射成 `"deny"`(§3.7 的逐字块),
而 hermes 的审批语义里根本没有「永久拒绝」这一档:`tools/approval.py:3379-3384` 只对
`choice == "session"` / `"always"` 做持久化(`approve_session` / `approve_permanent` /
`save_permanent_allowlist`),`"deny"` 只返回一条「Do NOT retry」的阻断消息,不写任何规则。
配置里确实有持久拒绝(`approvals.deny`,`tools/approval.py:542` 的 `_match_user_deny_rule`),
但这个按钮不写它。**用户点了 "Deny always",下一次同样的命令还会再问。**
标签比效果宽,这正是审批 UI 最不该有的偏差。

**■2 回合进行中发来的图片被静默丢弃,并被替换成字面串。**

`acp_adapter/server.py:1745 @ 863e313`

```python
                            exc_info=True,
                        )
                if not redirected:
                    queued_text = user_text or "[Image attachment]"
                    state.queued_prompts.append(queued_text)
                    queued_depth = len(state.queued_prompts)
            else:
                state.is_running = True
                state.current_prompt_text = user_text or "[Image attachment]"
```

`queued_prompts` 是 `List[str]`(acp_adapter/session.py:169),排队时只留文本。排空时:

`acp_adapter/server.py:2071 @ 863e313`

```python
            await self.prompt(
                prompt=[TextContentBlock(type="text", text=next_prompt)],
                session_id=session_id,
            )
```

于是:回合进行中用户拖进来一张截图 → 若无附带文字,模型收到的字面内容是 `"[Image attachment]"`;
若有附带文字,图片被丢掉、只有文字被重放。两种情况都**没有任何提示**,
回执反而是 `"Queued for the next turn. (N queued)"`(:1765),读起来像「收到了,排上了」。
`initialize` 又 advertise 了 `PromptCapabilities(image=True)`(:1163),所以客户端有充分理由这么发。

**■3 `acp_adapter/tools.py:1297` 的三元表达式是死分支。**

`acp_adapter/tools.py:1274 @ 863e313`

```python
    if tool_name in _POLISHED_TOOLS:
        try:
            args_text = json.dumps(arguments, indent=2, default=str)
        except (TypeError, ValueError):
            args_text = str(arguments)
        content = [_text(_truncate_text(args_text, limit=1200))]
        return acp.start_tool_call(
            tool_call_id, title, kind=kind, content=content, locations=locations,
        )
```

`acp_adapter/tools.py:1289 @ 863e313`

```python
    # Generic fallback
    try:
        args_text = json.dumps(arguments, indent=2, default=str)
    except (TypeError, ValueError):
        args_text = str(arguments)
    content = [acp.tool_content(acp.text_block(args_text))]
    return acp.start_tool_call(
        tool_call_id, title, kind=kind, content=content, locations=locations,
        raw_input=None if tool_name in _POLISHED_TOOLS else arguments,
    )
```

第二块只有在第一块的条件为假时才可达,所以 `:1297` 的 `tool_name in _POLISHED_TOOLS` **恒为 False**,
`raw_input` 恒等于 `arguments`。危害是零(行为等价于直接写 `raw_input=arguments`),
但它把「这里可能不带 raw_input」这个假象写进了代码 —— 而 §3.9 的 C 组说明落到这里的正是
`browser_cdp` / `browser_dialog` 这两个漏登记的工具,读者会以为它们受同一条保护。
对照:`build_tool_complete`(:1329)里同形状的 `raw_output=None if tool_name in _POLISHED_TOOLS or ...`
**是活的**(该函数没有提前 return),所以这不是「作者的一贯写法」,是这一处的疏漏。

**■4 `Default` 模式承诺 "Ask before edits.",但 `skill_manage` 的文件写入不问。**
取证见 §5.9 取证 A。三个锚点:渲染层认它是编辑
(`acp_adapter/events.py:157`:`        if name in {"write_file", "patch", "skill_manage"}:`);
守卫层不认它(`acp_adapter/edit_approval.py:181`:`    if tool_name == "write_file":`);
它自己的闸默认关(`tools/write_approval.py:274`:`    if not write_approval_enabled(subsystem):`)。
模式描述在 `acp_adapter/server.py:668`:`                    description="Ask before edits.",`。
`skill_manage` 在 `hermes-acp` toolset 里(`toolsets.py:414`:`            "skills_list", "skill_view", "skill_manage",`)。

### ▲ 文档与代码矛盾(6 条)

**▲1 reasoning 不是经 `step_callback` 转发的。** 文档侧整句:

`website/docs/developer-guide/acp-internals.md:79 @ 863e313`

> - `thinking_callback` (currently set to `None` in the ACP bridge — reasoning is forwarded through `step_callback` instead)

前半为真、**后半为假**,代码侧:

`acp_adapter/server.py:1825 @ 863e313`

```python
        # ACP thought panes should not receive Hermes' local kawaii waiting/status
        # updates. Route provider/model reasoning deltas instead; if the provider
        # emits no reasoning, Zed should not get a fake "thinking" accordion.
        agent.thinking_callback = None
        agent.reasoning_callback = reasoning_cb
        agent.step_callback = step_cb
        agent.stream_delta_callback = stream_delta_cb
```

reasoning 走 `agent.reasoning_callback`(值是 `make_thinking_cb` 的产物,`acp_adapter/server.py:1794`);
`step_callback` 干的是完全另一件事 —— 用 FIFO 队列补发工具完成通知(`acp_adapter/events.py:209`)。
按「整句一并判定」的规矩,这一句判 ▲。

**▲2 「非文本块被忽略」被列为当前限制,而代码已经实现了它们。** 文档侧,在
`## Current limitations` 标题下:

`website/docs/developer-guide/acp-internals.md:173 @ 863e313`

> - non-text prompt blocks are currently ignored for request text extraction

代码里非文本块**不被忽略**:`ImageContentBlock` → `image_url` 部件(`acp_adapter/server.py:534-538`)、
`ResourceContentBlock` → 读盘内联(`:539-545`)、`EmbeddedResourceContentBlock` → 解码内联(`:546-552`),
而 `initialize` 还 advertise 了图片能力:

`acp_adapter/server.py:1161 @ 863e313`

```python
            agent_capabilities=AgentCapabilities(
                load_session=True,
                prompt_capabilities=PromptCapabilities(image=True),
                session_capabilities=SessionCapabilities(
                    fork=SessionForkCapabilities(),
                    list=SessionListCapabilities(),
                    resume=SessionResumeCapabilities(),
                ),
            ),
```

基线测试 `tests/acp_adapter/test_acp_images.py:16` / `:39` / `:65` 三个用例正是钉这三件事。
标题「Current limitations」是断言的一部分:把已实现的能力列为当前限制,判 ▲。
(唯一为真的读法是「`_extract_text` 这一个函数不取非文本块的文本」——
但发给模型的是 `_content_blocks_to_openai_user_content` 的产物,`acp_adapter/server.py:1647`。)

**▲3 cancel 调的不是 `agent.interrupt()`。** 文档侧(注意真实行号是 `:133` 而非 `:132`,
`:132` 是同一列表的上一项「sets the session cancel event」):

`website/docs/developer-guide/acp-internals.md:133 @ 863e313`

> - calls `agent.interrupt()` when available

代码调的是 `request_hard_interrupt(state.agent)`(`acp_adapter/server.py:1552`),而它优先用
**静态查找**确认 `hard_interrupt` 存在并调它:

`agent/interrupt_compat.py:21 @ 863e313`

```python
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

`interrupt()` 只是给第三方 agent / 老测试替身的回落。真正的 `AIAgent` 两个都有
(`run_agent.py:3028` `interrupt`、`:3163` `hard_interrupt`),所以生产路径调的是 `hard_interrupt`。

**▲4 「ACP 会话只活在进程里」与代码相反,而且与同仓库另一份文档互相矛盾。** 文档侧两句:

`website/docs/user-guide/features/acp.md:316 @ 863e313`

> ACP sessions are tracked by the ACP adapter's in-memory session manager while the server is running.

`website/docs/user-guide/features/acp.md:326 @ 863e313`

> The underlying `AIAgent` still uses Hermes' normal persistence/logging paths, but ACP `list/load/resume/fork` are scoped to the currently running ACP server process.

代码相反,而且是模块 docstring 的第一段就写着:

`acp_adapter/session.py:1 @ 863e313`

```python
"""ACP session manager — maps ACP sessions to Hermes AIAgent instances.

Sessions are persisted to the shared SessionDB (``~/.hermes/state.db``) so they
survive process restarts and appear in ``session_search``.  When the editor
reconnects after idle/restart, the ``load_session`` / ``resume_session`` calls
find the persisted session in the database and restore the full conversation
history.
"""
```

配套实现:`_restore`(`acp_adapter/session.py:497`)在内存里找不到时从 DB 重建整个 agent;
`list_sessions`(`acp_adapter/session.py:280`)把 `db.list_sessions_rich(source="acp", limit=1000)`
的行并进结果;`get_session`(`acp_adapter/session.py:220`)的 docstring 明确写「If the session is not
in memory but exists in the database (e.g. after a process restart), it is transparently restored」。
**同仓库的另一份文档站在代码这边:**

`website/docs/developer-guide/acp-internals.md:172 @ 863e313`

> - ACP sessions are persisted to the shared `~/.hermes/state.db` (SessionDB) and transparently restored across process restarts; they appear in `session_search`

两份文档互相矛盾,代码为准。**这个形态(文档 A ▲、文档 B 正确)在本片首次出现**,
比单纯的「文档过时」更值得记:读者随机翻到哪一份决定他信什么。

**▲5 审批选项数说 3,代码最多发 5。** 文档侧整段的第一句:

`website/docs/user-guide/features/acp.md:334 @ 863e313`

> Dangerous terminal commands can be routed back to the editor as approval prompts. ACP approval options are simpler than the CLI flow:

后接三项 `allow once` / `allow always` / `deny`。代码最多发 **5** 个选项(§3.7 的逐字块),
`allow_session` 与 `deny_always` 都不在这三项里。同一页 `:351-357` 的表格自己列到了 4 项
(补了 `allow_session`),所以这是**页内自相矛盾 + 与代码矛盾**。

**▲6 一个叫「编辑自动放行」的小节里一个字都没讲编辑审批。** 文档侧的小标题:

`website/docs/user-guide/features/acp.md:347 @ 863e313`

> ### Session-scoped edit auto-approval

该节的表格(`website/docs/user-guide/features/acp.md:351-357`)四行全是
`acp_adapter/permissions.py` 的**命令**审批 option id,`:354` 还把 `allow_session` 的作用域写成
「All matching calls in this ACP session」。而**编辑**审批面只发两个选项、没有 session 档:

`acp_adapter/edit_approval.py:308 @ 863e313`

```python
        options = [
            PermissionOption(option_id="allow_once", kind="allow_once", name="Allow edit"),
            PermissionOption(option_id="deny", kind="reject_once", name="Deny"),
        ]
```

编辑的会话级自动放行走的是完全另一套东西 —— ACP 会话模式
(`_MODE_TO_EDIT_APPROVAL_POLICY`,`acp_adapter/server.py:628`,§3.6)。
标题层级本身就是断言,判 ▲。

### ◇ 代码有、文档无(7 条)

**◇1 `acp_adapter/edit_approval.py`(338 行)与 `acp_adapter/provenance.py`(127 行)在
`acp-internals.md` 全文不出现。** 那份清单的引导句与它覆盖的 7 个文件:

`website/docs/developer-guide/acp-internals.md:11 @ 863e313`

> Key implementation files:

清单是 `:13-19`,列 `entry.py` / `server.py` / `session.py` / `events.py` / `permissions.py` /
`tools.py` / `auth.py` —— 恰好是本片 11 个文件里的 7 个,漏掉的是
`edit_approval.py`、`provenance.py`、`__init__.py`、`__main__.py`。前两个不是薄文件。
而该页 frontmatter 自称覆盖 approvals:

`website/docs/developer-guide/acp-internals.md:4 @ 863e313`

> description: "How the ACP adapter works: lifecycle, sessions, event bridge, approvals, and tool rendering"

正文里只有一个 `### Permission bridge` 小节(`website/docs/developer-guide/acp-internals.md:88-98`),
讲的全是命令审批。**ACP 的两个审批面里有一个在开发者文档里不存在。**

**◇2 三档会话模式与三个协议方法无文档。** 文档侧的方法清单:

`website/docs/developer-guide/acp-internals.md:44 @ 863e313`

> - new/load/resume/fork/list/cancel session methods

`set_session_mode`(`acp_adapter/server.py:2474`)、`set_config_option`(`acp_adapter/server.py:2490`)、
以及 Default / Accept Edits / Don't Ask 三档(`acp_adapter/server.py:665-680`)在这份清单与
`website/docs/user-guide/features/acp.md` 全文都不出现。**这是 ACP 用户唯一能调节编辑审批强度的旋钮。**
`acp_adapter/server.py:650-657` 的注释还记录了一个非平凡的产品判断:Zed 把 `config_options` 渲染在
「模型选择器原来的位置」,所以 hermes 故意把编辑策略映射到 **modes** 而不是 config options。

**◇3 两个审批面的脱敏不对称,且同走一条 stdio 通道。** 命令面在渲染前脱敏:

`tools/approval.py:2760 @ 863e313`

```python
    # Redact secrets before any user-visible rendering. The original
    # `command` is still what executes after approval; only the displayed
    # copy is scrubbed. Reuses the same redaction module used for memory
    # and log sanitization so tokens mask consistently across surfaces.
    from agent.redact import redact_sensitive_text
    display_command = redact_sensitive_text(command)
    display_description = redact_sensitive_text(description)
```

编辑面把文件当前内容原样放进 diff:

`acp_adapter/edit_approval.py:274 @ 863e313`

```python
        status="pending",
        content=[
            acp.tool_diff_content(
                path=proposal.path,
                old_text=proposal.old_text,
                new_text=proposal.new_text,
            )
        ],
        raw_input={"tool": proposal.tool_name, "arguments": proposal.arguments},
```

后果具体:模式为 `ask`(Default)时,模型对 `~/.ssh/config` 或某个 `.env` 发起 `patch` ——
`_is_sensitive_auto_approve_path`(`acp_adapter/edit_approval.py:192`)正确地不自动放行,于是**弹审批框**,
而框里的 diff 就是那个文件的**完整明文**,`raw_input` 里还带一份完整 arguments。
这在本地可信的 stdio 模型下是可辩护的(看不见 diff 就没法审批),
但它是一个未记录的不对称:同一条通道上两个面,一个脱敏一个不脱。

顺带核实一条**负结论:编辑参数在到达 ACP 之前没有被任何一层动过。** 内核给工具进度事件用的
`redact_tool_args_for_display` 只处理 `browser_type` 的 `text`:

`agent/display.py:408 @ 863e313`

```python
    if not isinstance(args, dict):
        return args
    if tool_name == "browser_type" and isinstance(args.get("text"), str):
        safe_args = dict(args)
        safe_args["text"] = redact_sensitive_text(args["text"], force=True)
        return safe_args
    return args
```

搜索面:全仓 `--include=*.py`、排除 `tests/` grep `_redact_tool_args_for_display` 得 9 处命中,
全在 `agent/tool_executor.py`,都调的是这同一个 `agent/display.py:400` 的实现;
`acp_adapter/` 内零处脱敏调用。

**◇4 `execute_code` 在 ACP 会话里不过整段脚本闸。** 取证见 §5.9 取证 B。
`website/docs/user-guide/features/acp.md` 的 `## Approvals` 一节(`:332-345`)只讲
「Dangerous terminal commands」;`execute_code` 唯一被提到的地方是 Buzz 那段警告(`:262`)。
代码侧这是**声明过的取舍**(§5.9 取证 B 的逐字块),不是遗漏,所以记 ◇ 而非 ■;
但那句取舍的理由(「the script's `terminal()` calls are guarded per-call」)与同函数 docstring
的自陈在覆盖面上并不相等:

`tools/approval.py:4233 @ 863e313`

```python
    execute_code runs arbitrary local Python — the script can call
    ``subprocess``, ``os.system``, ``ctypes``, or other process/file APIs
    directly, none of which pass through ``terminal()`` /
    ``DANGEROUS_PATTERNS``. In gateway/ask contexts we fail closed by approving
```

**◇5 代码处理 resource_link 与 embedded resource,但能力位只 advertise 了 image。**
`initialize` 里只有 `prompt_capabilities=PromptCapabilities(image=True)`(▲2 的逐字块,
`acp_adapter/server.py:1163`),而这两个转换器加起来近 150 行:

`acp_adapter/server.py:332 @ 863e313`

```python
def _resource_link_to_parts(block: ResourceContentBlock) -> list[dict[str, Any]]:
    """Convert an ACP resource_link block to OpenAI content parts.

    Returns a list of {"type": "text", ...} and/or {"type": "image_url", ...}
    parts. Image resources produce an image_url part with a small text header
    so the model knows which attachment it is. Non-image resources return a
    single text part with the inlined file body (or a binary-omit note).
    """
```

加上 `_embedded_resource_to_parts`(`acp_adapter/server.py:431`)。
守规矩的客户端不会发它没被告知服务端能收的块类型,所以这段代码在标准客户端上可能长期不可达。
(ACP 规范里是否存在对应的 `embeddedContext` 能力位 —— 未取证,SDK 未安装,见 §7。)

**◇6 `browser_cdp` / `browser_dialog` 三张工具表全漏。** 见 §3.9 的 A/C 组:
它们在 `hermes-acp` toolset 里(`toolsets.py:418`:`            "browser_vision", "browser_console", "browser_cdp", "browser_dialog",`),
却既不在 `TOOL_KIND_MAP`(→ 图标 `other`)也不在 `_POLISHED_TOOLS`(→ 走通用 JSON dump 兜底)。
`browser_console` 半漏:在 `_POLISHED_TOOLS` 里、不在 kind 表里。
`memory` 与 `session_search` 同样漏在 kind 表外,而它们有专属 title 分支
(`acp_adapter/tools.py:135-141`)和专属结果美化器(`acp_adapter/tools.py:911-912`)—— 说明是登记遗漏,不是有意归到 `other`。

**◇7 `acp_adapter/__init__.py` 把 ACP 展开成错的全称。**

`acp_adapter/__init__.py:1 @ 863e313`

```python
"""ACP (Agent Communication Protocol) adapter for hermes-agent."""
```

正式名称是 **Agent Client Protocol**:`pyproject.toml:252` 的依赖是
`agent-client-protocol==0.9.0`,`acp_adapter/auth.py:42-44` 说的是
「registry-compatible ACP auth methods」并提到「The official ACP registry」,
`acp.md`(`:9-22`)整页也不用 "Communication" 这个词。这是包的**第一行**,
也是任何人读这个包时看到的第一句话。归 ◇(代码里有一个文档层面没有的错误说法)而不是 ▲
—— 冲突方是代码注释而非文档。

### ◎ 文档成立但显著保守(1 条)

**◎1 `website/docs/user-guide/features/acp.md:36`** ——
「It intentionally excludes things that do not fit typical editor UX, such as messaging delivery and
cronjob management.」字面为真(`send_message` 与 `cronjob` 确实不在 `hermes-acp` 里),
但排除面远大于这两个例子。同仓库的 `website/docs/reference/toolsets-reference.md:96` 自己列得更全:
「Drops `clarify`, `cronjob`, `image_generate`, `text_to_speech`, `computer_use`, all four Home
Assistant tools, the kanban tools, and the desktop-GUI pane tools.」
§3.9 的 D 组给出机械数字:`_POLISHED_TOOLS` 里有 **28 个**工具在 ACP 面不可见,
其中飞书 5 个、kanban 7 个、yb 5 个、Home Assistant 4 个都没被 `acp.md` 提到。
(注:`toolsets-reference.md` 的中英两版这份清单本身不一致 —— 中文版
`website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/reference/toolsets-reference.md:94`
含 `send_message` 而无 `computer_use` / kanban / desktop-GUI。这是文档-文档冲突,不计入本表。)

---

## §7 未取证与推定

**未取证-1:`agent-client-protocol==0.9.0` SDK 在本容器未安装,故 ACP 线上方法名、
`sessionUpdate` 变体字符串、`PermissionOption.kind` 的合法取值、`PromptCapabilities` 的字段全集,
本底稿都没有第一手取证。**

```verify
cd /home/user/hermes-agent && grep -n 'acp = \[' pyproject.toml    # acp = ["agent-client-protocol==0.9.0"]
HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "import acp" 2>&1 | tail -1
# 期望: ModuleNotFoundError: No module named 'acp'
```

按派工书铁律**没有安装任何包**。凡涉及 SDK 内部的判断,本文都标为推定并给出替代取证
(仓库内字面量、测试断言、类型标注)。

**未取证-2:tests/acp 与 tests/acp_adapter 共 20 个文件 / 3,831 行,其中 11 个文件因模块级
`import acp` 连收集都过不去。** 剩下 7 个测试文件实测:

```console
$ cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_HOME=<临时目录> \
    /home/user/hermes-venv/bin/python -m pytest tests/acp tests/acp_adapter -q -p no:cacheprovider \
    --ignore=tests/acp/test_entry.py --ignore=tests/acp/test_events.py \
    --ignore=tests/acp/test_mcp_e2e.py --ignore=tests/acp/test_named_provider_catalogs.py \
    --ignore=tests/acp/test_permissions.py --ignore=tests/acp/test_ping_suppression.py \
    --ignore=tests/acp/test_server.py --ignore=tests/acp/test_tools.py \
    --ignore=tests/acp_adapter/test_acp_commands.py --ignore=tests/acp_adapter/test_acp_images.py \
    --ignore=tests/acp_adapter/test_acp_mcp_discovery.py
2 failed, 40 passed in 4.64s
```

两个 failed **都**是函数体里的 `import acp`(`tests/acp/test_auth.py::TestBuildAuthMethods::...`
命中 `acp_adapter/auth.py:51`;`tests/acp/test_edit_approval.py::test_acp_permission_tool_call_uses_edit_kind_and_diff_content`
命中 `acp_adapter/edit_approval.py:267`),不是断言失败。
环境:共享 venv **87 个包**(`pip list` 去表头计数 = `site-packages/*.dist-info` 计数 = 87),
未安装任何东西。

**因此本底稿引用测试时,只把用例名与用例正文当「行为规格」读,不宣称跑绿。**
被当规格引用的关键用例:
`tests/acp/test_approval_isolation.py:146` 的 `TestAcpExecAskGate`(其 docstring 是 ACP 审批路由的权威说明)、
`:44` 的 `TestThreadLocalApprovalCallback`(4 个用例钉死回调不跨线程泄漏,GHSA-qg5c-hvr5-hjgr)、
`tests/acp/test_edit_approval.py:50` `test_requester_exception_denies_and_does_not_mutate` 与
`:72` `test_patch_replace_rejection_does_not_mutate`(「拒绝不得改文件」)、
`:102` `test_workspace_auto_approval_allows_workspace_and_tmp_but_not_sensitive`(三档策略的边界)、
`tests/acp/test_permissions.py:122` `test_timeout_returns_timeout_and_cancels_future`(timeout ≠ deny)、
`tests/acp/test_server.py:61` `test_new_session_exposes_edit_approvals_as_modes_not_config_options`
与 `:75` `test_set_config_option_persists_edit_approval_policy_without_advertising_config`
(◇2 里那个产品判断的规格)、
`tests/acp/test_session.py:167` `test_save_session_preserves_existing_messages_on_encode_failure`
与 `tests/acp/test_session_db_private_access.py:83` `TestNoPrviateDBAccess`(§5.3 那段持久化的规格)。

**未取证-3:测试自己的覆盖面有一处名不副实,值得记下但我没深挖。**
`tests/acp/test_tools.py:32` 的 `test_all_hermes_tools_have_kind` 断言「Every common hermes tool
should appear in TOOL_KIND_MAP」,但它遍历的 `COMMON_HERMES_TOOLS`(`:28`)只有 6 个名字
(`read_file` `search_files` `terminal` `patch` `write_file` `process`)。
§3.9 的 A 组那 5 个漏登记的工具正好都不在这 6 个里,所以这个用例结构上抓不到它们。

**推定-1(未验):ACP 编辑审批的 ContextVar 会传播进 delegate 子 agent,于是子 agent 的每次
`write_file` 也会向编辑器弹框。** 依据是 `tools/delegate_tool.py:2207` 与 `:3024` 的
`contextvars.copy_context()`、以及 `tools/thread_context.py:78` 的 `propagate_context_to_thread`
(其 docstring `:1-32` 明确说要复制 ContextVar 与线程本地回调)。
我**没有**实跑一次 delegate 下的 ACP 编辑,也没有逐跳确认 `delegate_task` 的执行路径一定经过这两处。

**推定-2(未验):`_executor` 是模块级的 4 线程池,故并发 ACP 会话上限 4。**
`acp_adapter/server.py:199` 的 `ThreadPoolExecutor(max_workers=4, thread_name_prefix="acp-agent")` 是字面量,
但我没验证是否存在别的执行路径(例如 `/compress` 之类同步斜杠命令直接在事件循环线程上跑,
确实如此 —— `_handle_slash_command` 在事件循环线程执行,`:2163-2171` 的注释就是为此写的)。
所以「上限 4」只对**回合**成立,不对全部工作成立。

**推定-3(未验):`prompt()` 排空队列用的是递归(`acp_adapter/server.py:2071` 里 `await self.prompt(...)`),
N 个排队 prompt 会产生 N 层协程栈,且第一个 `session/prompt` 的响应要等到全部排空才返回。**
我读出了这个形状,但没构造 N 大的场景验证栈深或客户端超时行为。

**未做-1:`server.py` 与 `tools.py` 的**实现体**大部分没读**(L2 的定义就是读接口面不读实现体)。
具体没下钻的:21 个结果美化器里除 `_format_edit_result` / `_format_generic_structured_result` 外的
逐个格式细节;`_build_model_state` 里 `build_models_payload` 的 10 个参数各自的含义;
`session.py` 的 `list_sessions` 里内存/DB 两路合并的排序细节。

**未做-2:没跑任何 npm / vitest**(铁律 3)。本片无 TS 代码。

**负结论-1:ACP 建 agent 的路径不读 `platform_toolsets`,所以 `platform_toolsets.acp` 收窄不了 ACP 工具面。**
搜索面:对全仓 `--include=*.py`、排除 `tests/`,grep `platform_toolsets` 得 11 个文件命中,
其中运行时读取只在 `hermes_cli/tools_config.py:2232`(`_get_platform_tools`,配置界面/向导用)
与 `hermes_cli/config.py:2262`(迁移期校验)、`hermes_cli/nous_subscription.py:125`、
`hermes_cli/plugins_cmd.py:1877`;**`acp_adapter/`、`model_tools.py`、`agent/agent_init.py`、
`toolsets.py` 四处零命中**(`agent/agent_init.py:2583` 只在注释里提到)。
ACP 的实际链路是 `acp_adapter/session.py:625` 字面量 `["hermes-acp"]` → `AIAgent(enabled_toolsets=...)` →
`model_tools.get_tool_definitions(enabled_toolsets=...)`。

```verify
cd /home/user/hermes-agent && grep -rn 'platform_toolsets' --include=*.py . | grep -v '^./tests/' | wc -l   # 11
cd /home/user/hermes-agent && grep -rn 'platform_toolsets' acp_adapter/ model_tools.py toolsets.py          # 期望无输出
```

**负结论-2:hermes 作为 ACP 服务端从不调用客户端的文件/终端能力。**
搜索面:在 `acp_adapter/` 全部 11 个文件里 grep `read_text_file|write_text_file|create_terminal`,
零命中(命令见 §5.4)。对照:`agent/copilot_acp_client.py:704` 有 `"fs/read_text_file"`,
但那是 hermes 作为 **ACP 客户端**去接 Copilot,属于另一片。
未排除的可能:SDK 内部是否在某些路径上代表 agent 主动调客户端 —— SDK 未安装,无法检查。

---

## §8 L2 判据自评

| 判据 | 自评 | 说明 |
|---|---|---|
| **1. 点名到位** | ✅ 做到 | §2 表格逐行给出 11 个全路径 + 一句话角色,与 `slices/C.txt` 逐条对齐;行数合计 5,831 有 ```verify 命令 |
| **2. 接缝穷举** | ✅ 做到(11 个接缝) | §3.1 方法 12 / §3.2 客户端调用 10+2 / §3.3 通知 9 / §3.4 斜杠命令 9 / §3.5 CLI 开关 5 / §3.6 模式 3 + 策略 3 / §3.7 选项 5+2 / §3.8 kind 表 27×7 / §3.9 toolset 29 与四向差集 5+3+2+28 / §3.10 分支表 23+16+21 / §3.11 内容块 5。**每一项都给了 ```verify 机械枚举命令与条数,无抽样。** 唯一不完备处已声明:§3.1 的 12 个**线上**方法名里只有 2 个有仓库内取证、4 个有间接取证,余 8 个因 SDK 未安装不下断言(§7 未取证-1) |
| **3. 一条端到端链** | ✅ 做到 | §4:编辑器 `session/prompt` → 12 跳 → `PromptResponse` 写回 stdout,**每跳带锚点**;跳 0 与跳 6/9/12 明确标注「片外」并写清接到谁(`hermes_cli/main.py:11050`、`agent/tool_executor.py:701`、`model_tools.py:1350`、`tools/file_tools.py:1768`) |
| **4. 两处以上逐字取证** | ✅ 做到(15 个围栏块) | 逐字源码块 15 个:`acp_adapter/edit_approval.py:1/45/178/332`、`acp_adapter/permissions.py:18`、`acp_adapter/events.py:156`、`acp_adapter/server.py:626/1745/1806/2071`、`acp_adapter/session.py:623`、`acp_adapter/tools.py:24/1274/1289`、`model_tools.py:1350`、`tools/approval.py:279/4292`、`agent/tool_executor.py:701`、`acp_adapter/__init__.py:1`、`tests/acp/test_server.py:377` |
| **5. 至少一条记号** | ✅ 做到(18 条) | ■4 / ▲6 / ◇7 / ◎1,逐条带锚点 |

**核心比较题**:§5.9 给出结论 + 三条改述 + 三条取证(A `skill_manage`、B `execute_code`、
C 内核自陈「unpaired theater」),并明确判定原结论「被支持但需改述」,附一句话总括可直接进成品章。

**没做到 / 不确定的**(与 §7 重复但集中列出):
1. SDK 未安装 → 8 个线上方法名、9 个通知变体里 3 个的字符串、`PromptCapabilities` 字段全集无第一手取证;
2. 20 个 ACP 测试文件里 11 个无法收集,只能当规格读名字与正文,不能宣称跑绿;
3. 推定-1(delegate 子 agent 继承编辑审批)、推定-3(排队递归的栈深/超时)未实跑;
4. `server.py` / `tools.py` 的多数实现体按 L2 定义未读(§7 未做-1 列了具体项)。

---

## §9 移交

| 编号 | 锚点 + 摘录 | 一句话现象 | 建议 |
|---|---|---|---|
| H-R10C-a | `acp_adapter/permissions.py:26`:`    "deny_always": "deny",` | ACP 发出的「Deny always」选项被映射成一次性 `deny`;`tools/approval.py` 里没有持久拒绝这一档,`approvals.deny` 配置规则不会被写入 | 若要修:或者摘掉这个选项,或者让它写 `approvals.deny`。附带查一遍 `tools/approval.py:542` 的 `_match_user_deny_rule` 有没有写入入口 |
| H-R10C-b | `acp_adapter/server.py:1748`:`                    queued_text = user_text or "[Image attachment]"` | 回合进行中收到的图片被丢弃,只把字面串 `"[Image attachment]"` 排进 `List[str]` 队列,排空时当纯文本重放(`:2072`);回执却是「Queued for the next turn」 | 需要把 `queued_prompts` 的元素类型从 `str` 升级成内容块列表(`acp_adapter/session.py:169`),或至少在回执里说明图片未入队 |
| H-R10C-c | `acp_adapter/edit_approval.py:181`:`    if tool_name == "write_file":` | ACP 编辑审批只认 `write_file` / `patch` 两个名字;`skill_manage`(同一对文件里被渲染成带 diff 的 `edit`,见 `acp_adapter/events.py:157`:`        if name in {"write_file", "patch", "skill_manage"}:`)不进这个闸,而它自己的闸默认关 | 这是「守卫认工具名」结论的最强单点取证,建议进成品章。若要修,方向是把 `build_edit_proposal` 扩到 `skill_manage` 的 create/edit/patch/write_file 动作 |
| H-R10C-d | `tools/approval.py:4297`:`    if not is_gateway and not is_ask:` | `check_execute_code_guard` 只在 gateway / `HERMES_EXEC_ASK` 上下文生效;ACP 走的是 interactive 分支,于是 `execute_code`(在 `hermes-acp` toolset 里)在 ACP 会话中直接放行 | 需要判定这是否可接受:同函数 docstring `tools/approval.py:4233`:`    execute_code runs arbitrary local Python — the script can call` 自陈脚本可绕过 `terminal()` 的全部模式匹配 |
| H-R10C-e | `acp_adapter/tools.py:1297`:`        raw_input=None if tool_name in _POLISHED_TOOLS else arguments,` | 该三元表达式恒取 `arguments` 分支(`:1274` 的 `if tool_name in _POLISHED_TOOLS:` 已提前 return),是死逻辑;落到这条路径的正是 `browser_cdp` / `browser_dialog` 两个三表全漏的工具 | 低优先级清理。同时建议把 `memory` / `session_search` / `browser_console` / `browser_cdp` / `browser_dialog` 补进 `TOOL_KIND_MAP` |
| H-R10C-f | `website/docs/developer-guide/acp-internals.md:79`:`- \`thinking_callback\` (currently set to \`None\` in the ACP bridge — reasoning is forwarded through \`step_callback\` instead)` | 该句后半为假:reasoning 走 `reasoning_callback`(`acp_adapter/server.py:1829`:`        agent.reasoning_callback = reasoning_cb`),`step_callback` 补发的是工具完成通知 | ▲1,已定案,供跨轮 ▲ 计数 |
| H-R10C-g | `website/docs/user-guide/features/acp.md:326`:`The underlying \`AIAgent\` still uses Hermes' normal persistence/logging paths, but ACP \`list/load/resume/fork\` are scoped to the currently running ACP server process.` | 与代码相反(`acp_adapter/session.py:497` 的 `_restore` 从 SessionDB 重建会话与 agent),且与同仓库 `website/docs/developer-guide/acp-internals.md:172` 互相矛盾 | ▲4,已定案。**两份文档互相矛盾**这个形态在本片首次出现,值得在成品章里作为「地图腐烂」的一个类型单列 |
| H-R10C-h | `acp_adapter/server.py:1163`:`                prompt_capabilities=PromptCapabilities(image=True),` | `initialize` 只 advertise `image`,但代码有近 150 行的 resource_link / embedded-resource 处理(`:332`、`:431`);守规矩的客户端可能永远不发这两类块 | 需要 SDK 或 ACP 规范才能判定「是否存在对应能力位」。下一轮若装得上 `agent-client-protocol==0.9.0`(在**基线之外**的副本里),这是第一个该查的问题 |
