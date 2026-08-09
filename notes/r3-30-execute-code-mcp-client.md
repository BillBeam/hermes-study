# R3-30 execute_code 编程式工具调用 + MCP 客户端侧(子代理底稿)

> 由子代理精读产出,主线抽查关键行号与定案(C1 execute_code 证实、C2 MCP 修正)。基线 863e31318。
> 范围:code_execution_tool(2087)、env_passthrough(223)、env_probe(370)、secret_scope(293)、
> redact(1008)、mcp_tool(7230)、mcp_oauth(1369)、mcp_oauth_manager(785)、mcp_stdio_watchdog(157)、
> mcp_dashboard_oauth(145)、mcp_schema_cache(121)。

I have all the evidence I need. Here is the complete L1 底稿.

---

# r3-底稿 · execute_code 编程式工具调用 + MCP 客户端侧
> 求全求证底稿。面向"要凭它重实现同等机制"的工程师。所有断言紧跟 `路径:行号 @ 863e313` + 逐字代码摘录。
> 基线 commit `863e31318553cda8ad61df681d08175364d4164b`。hermes-agent 只读。
> 实测行数(`wc -l`):`code_execution_tool.py` 2087 / `env_passthrough.py` 223 / `env_probe.py` 370 / `secret_scope.py` 293 / `redact.py` 1008 / `mcp_tool.py` 7230 / `mcp_oauth.py` 1369 / `mcp_oauth_manager.py` 785 / `mcp_stdio_watchdog.py` 157 / `mcp_dashboard_oauth.py` 145 / `mcp_schema_cache.py` 121。全部与任务清单一致。

---

## 导航

- **A 块 execute_code(PTC)**:A1 三态 RPC 传输选择 → A2 token 鉴权 → A3 环境洗净(三层)→ A4 secret_scope 与 profile 多路复用 → A5 审批上下文跨线程/跨进程传播 → A6 stub 模块生成 → A7 为什么只回 stdout(截断+脱敏) → A8 解释器/CWD 模式 → A9 env_probe。
- **B 块 MCP 客户端**:B1 命名规范与撞车 fail-closed → B2 描述注入扫描 → B3 OSV 恶意包预检 → B4 可疑 server 配置过滤(exfil/persistence/IOC) → B5 stdio watchdog 孤儿清理 → B6 schema 缓存与懒注册 → B7 动态注册(list_changed) → B8 OAuth 流(结构级) → B9 远端 URL 校验 / 跨源鉴权剥离 / 错误脱敏。
- **定案**:C1 execute_code(◇);C2 MCP 客户端侧安全与动态注册(◇/▲)。
- **测试行为规格**:D1–D4。

---

# A 块 · execute_code —— 编程式工具调用(PTC)

## A0 一句话与全链条

execute_code 让 LLM 写一段 Python 脚本,脚本里 `from hermes_tools import web_search, terminal, ...` 直接调工具;工具调用经 RPC 回到父进程派发,**只有脚本 stdout 回给 LLM**,中间工具结果不进上下文窗口。模块 docstring 把两条传输链说得很清楚:

`tools/code_execution_tool.py:8-25 @ 863e313`
```
Architecture (two transports):

  **Local backend (UDS):**
  1. Parent generates a `hermes_tools.py` stub module with UDS RPC functions
  2. Parent opens a Unix domain socket and starts an RPC listener thread
  3. Parent spawns a child process that runs the LLM's script
  4. Tool calls travel over the UDS back to the parent for dispatch

  **Remote backends (file-based RPC):**
  1. Parent generates `hermes_tools.py` with file-based RPC stubs
  2. Parent ships both files to the remote environment
  3. Script runs inside the terminal backend (Docker/SSH/Modal/Daytona/etc.)
  4. Tool calls are written as request files; a polling thread on the parent
     reads them via env.execute(), dispatches, and writes response files
  5. The script polls for response files and continues

In both cases, only the script's stdout is returned to the LLM; intermediate
tool results never enter the context window.
```

入口 `execute_code()` 的顶层链条(`code_execution_tool.py:1266-1332`):
1. 可用性/空码检查 → 2. 读 `env_type`(terminal 后端类型) → 3. **审批守卫** `check_execute_code_guard`(A5) → 4. 清中断位 → 5. 若 `env_type != "local"` 走 `_execute_remote`(文件 RPC),否则走本地 UDS/TCP 路径。

工具白名单只有 7 个,是**沙箱可调工具的全集**,与会话已启用工具取交集:

`tools/code_execution_tool.py:63-71 @ 863e313`
```python
SANDBOX_ALLOWED_TOOLS = frozenset([
    "web_search",
    "web_extract",
    "read_file",
    "write_file",
    "search_files",
    "patch",
    "terminal",
])
```

资源上限(`code_execution_tool.py:74-77`):`DEFAULT_TIMEOUT=300`s、`DEFAULT_MAX_TOOL_CALLS=50`、`MAX_STDOUT_BYTES=50_000`、`MAX_STDERR_BYTES=10_000`。

---

## A1 三态 RPC 传输:怎么选、怎么建

**问题(一次具体调用走法)**:LLM 提交 `terminal("ls")` 的脚本。父进程要在**不把凭证塞进子进程、又能让子进程调工具**的前提下,把这一个 `terminal` 调用路由回父进程派发。父进程运行环境有三种形态:本地 POSIX、本地 Windows、远端容器(Docker/SSH/Modal/…),AF_UNIX 不是处处可用,于是有三态传输。

**机制**:传输由平台 + 后端类型三分:

- **本地 POSIX → AF_UNIX(UDS)**。父进程在 `/tmp`(macOS 因 104 字节 AF_UNIX 路径限制强制用 `/tmp`)建一个 `.sock`,`listen(1)`,并 `chmod 0600` 用文件权限当访问门:

  `code_execution_tool.py:1413-1416 @ 863e313`
  ```python
  server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  server_sock.bind(sock_path)
  os.chmod(sock_path, 0o600)
  server_sock.listen(1)
  ```

- **本地 Windows → 环回 TCP**。`AF_UNIX` 在 Windows Python 上不可靠,退回 `127.0.0.1` 临时端口,端点写成 `tcp://host:port`:

  `code_execution_tool.py:1407-1411 @ 863e313`
  ```python
  if _use_tcp_rpc:
      server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      server_sock.bind(("127.0.0.1", 0))  # ephemeral port
      _host, _port = server_sock.getsockname()[:2]
      rpc_endpoint = f"tcp://{_host}:{_port}"
  ```
  `_use_tcp_rpc = _IS_WINDOWS`(`:1364`)。生成的 client 从 `HERMES_RPC_SOCKET` 前缀 `tcp://` 判断走 AF_INET 还是 AF_UNIX(见 A6 的 `_connect` stub,`:532-541`)。

- **远端后端 → 文件 RPC**。容器/SSH/Modal 里没法共享父进程的 UDS,改用请求/响应文件:子进程把调用写成 `req_NNNNNN` 文件,父进程一个轮询线程用 `env.execute("ls .../req_*")` + `cat` 读出、派发、把结果 base64 写回 `res_NNNNNN`。核心轮询体 `_rpc_poll_loop`(`:925-1071`),投递用 `echo '<b64>' | base64 -d`(因为 Modal 对链式命令的 stdin 不可靠,`:1050-1061`)。

**设计理由**:注释明确 Windows 环回退化是"same ephemeral port, same 1-connection listen queue, same serialized request/response framing"(`:1359-1362`),即三态共享同一套单连接、串行帧协议,只是承载不同。文件 RPC 用**原子 rename**(写 `.tmp` 再 `os.rename`)避免读到半个请求(`:602-610`)。

**取舍**:UDS 靠文件权限(0600)做隔离,最强;TCP 只有"环回=本机同用户进程可连",注释承认"No filesystem permission story"(`:1403-1405`),所以补了 token(A2);文件 RPC 走 `env.execute` 每次起独立进程,注释说"run safely concurrent with the script-execution thread"(`:938-941`),但每次工具调用要 ls+cat+写文件多趟 shell,延迟高,自适应轮询 50ms→250ms(`:613-619`)。

**重实现要点**:传输选择器放进一个环境变量(`HERMES_RPC_SOCKET`,path vs `tcp://`),让 client 自解析,父进程按平台/后端决定;三态共用一份 line-delimited JSON 帧协议;远端一律原子 rename + base64,不要依赖 stdin 管道。

---

## A2 token 鉴权:环回 TCP 与文件 RPC 的第二道门

**问题(攻击走法)**:Windows 环回 TCP 端口对**本机任意进程**可连;文件 RPC 的 `req_*` 文件躺在临时目录,同机另一个进程也能写一个伪造请求文件。仅靠"本机同用户"不够。

**机制**:每次 execute_code 生成一次性 token `secrets.token_urlsafe(32)`,注入子进程 env,子进程每条 RPC 请求都带 token,服务端用 `secrets.compare_digest` 常数时间比对,失败即 `Unauthorized` 且**不派发**:

`code_execution_tool.py:703-711 @ 863e313`
```python
if not rpc_token or not secrets.compare_digest(
    # Compare as bytes: compare_digest raises TypeError on a
    # str with non-ASCII characters, and the token comes from
    # sandbox-script-supplied JSON.
    str(request.get("token") or "").encode(), rpc_token.encode()
):
    resp = tool_error("Unauthorized RPC request")
    conn.sendall((resp + "\n").encode())
    continue
```

本地路径 token 生成 `:1398 rpc_token = secrets.token_urlsafe(32)`;远端路径同样 `:1133`。文件 RPC 侧的等价校验在 `_rpc_poll_loop`(`:988-996`),失败时删掉坏请求文件避免死循环重试。注意 `not rpc_token` 短路:空 token 也直接拒(fail-closed)。

**设计理由**:注释点出 token 来自"sandbox-script-supplied JSON",所以必须按 bytes 比对(`compare_digest` 对含非 ASCII 的 str 会抛 `TypeError`)且常数时间防时序侧信道。

**取舍**:token 每次调用一换,不持久;派发前先查白名单(`:717`)再查调用上限(`:727`)再剥离危险 terminal 参数(A6)——鉴权是第一关。

**重实现要点**:环回 TCP / 共享临时目录这类"本机可连"传输,必须叠一层每会话随机 token,bytes 常数时间比对,空 token fail-closed。

---

## A3 环境洗净:三层规则 + delegate 上下文桥接

**问题(攻击走法)**:LLM 脚本里写 `import os; print(os.environ)` 想偷 `OPENAI_API_KEY`。子进程若继承父进程完整 env,凭证就泄了。

**机制**:`_scrub_child_env`(`:208-299`)按**顺序**产出洗净 env(顺序即优先级):

`code_execution_tool.py:253-273 @ 863e313`
```python
for k, v in source_env.items():
    if is_passthrough(k):
        resolved = resolve_passthrough_value(k, v)
        if resolved is not None:
            scrubbed[k] = resolved
        continue
    if any(s in k.upper() for s in _SECRET_SUBSTRINGS):
        continue
    if any(k.startswith(p) for p in _SAFE_ENV_PREFIXES):
        scrubbed[k] = v
        continue
    if k in _HERMES_CHILD_ALLOWED:
        scrubbed[k] = v
        continue
    if is_windows and k.upper() in _WINDOWS_ESSENTIAL_ENV_VARS:
        scrubbed[k] = v
        continue
    if k.startswith("HERMES_"):
        _dropped_hermes.append(k)
```

规则栈:① passthrough(技能/config 显式声明,A4 解析);② **secret 子串黑名单先行**(`_SECRET_SUBSTRINGS`,`:152-162`:`KEY/TOKEN/SECRET/PASSWORD/PASSWD/AUTH/DSN/WEBHOOK/CREDS/BEARER/APIKEY`——注释特意说明 `PASS` 故意不加,因误伤 `BYPASS_CACHE/COMPASS_DIR`);③ 安全前缀白名单(`_SAFE_ENV_PREFIXES`,`:149-151`:`PATH/HOME/USER/LANG/LC_/TERM/TMPDIR/...`);④ 运营性 `HERMES_*` 精确名单(`_HERMES_CHILD_ALLOWED`,`:168-174`:仅 `HERMES_HOME/PROFILE/CONFIG/ENV/DELEGATED_CHILD_CONTEXT`);⑤ Windows 必需 OS 变量精确名单(`:182-205`,没它连 `socket.socket()` 都会 WinError 10106)。

洗净后父进程再**显式**注入运行所需:`HERMES_RPC_SOCKET / HERMES_RPC_TOKEN / PYTHONDONTWRITEBYTECODE`(`:1442-1444`),`PYTHONIOENCODING=utf-8 / PYTHONUTF8=1`(`:1462-1463`),`PYTHONPATH`(把 staging tmpdir + hermes root 前置,`:1468-1473`),以及仅 `TZ`(不泄 `HERMES_TIMEZONE`,`:1478-1481`)。

**delegate 上下文桥接(易漏点)**:delegate_task 子进程用 ContextVar 标记,而 execute_code 跨进程边界会丢,所以洗净后再补一层——若当前是委派子上下文,`scrub_kanban_env` 剥掉 Kanban 变量,防止 passthrough 反向给委派子进程重新授予看板变更能力:

`code_execution_tool.py:289-298 @ 863e313`
```python
from agent.delegation_context import (
    is_delegated_child_process_context, scrub_kanban_env,
)
if is_delegated_child_process_context():
    scrubbed = scrub_kanban_env(scrubbed)
```

**设计理由(issue 号)**:`#27303` 明确移除了原来宽泛的 `HERMES_` 前缀放行,因为它会泄漏 `HERMES_BASE_URL/HERMES_KANBAN_DB/HERMES_*_WEBHOOK` 等含非 secret 子串的配置(`:144-148`)。被丢弃的 `HERMES_*` 变量会 `logger.debug` 一次,指向 env_passthrough 逃生口(`:274-282`)。

**取舍**:黑名单在白名单之前 → 即使某个 secret 名字碰巧撞上安全前缀也先被黑名单拦掉(`_SECRET_SUBSTRINGS` 是子串匹配、`_SAFE_ENV_PREFIXES` 是前缀匹配,顺序保证 secret 优先);代价是像 `HERMES_KANBAN_DB` 这种非 secret 也被丢,要靠 passthrough 显式恢复。

**重实现要点**:洗净顺序 = passthrough → secret 子串黑名单 → 安全前缀白名单 → 运营精确名单 → OS 必需名单;洗完再显式注入运行变量;跨进程边界要手动桥接 ContextVar 标记的能力上下文,且 passthrough 不能反授委派能力。

---

## A4 env_passthrough 与 secret_scope:逃生口本身要 fail-closed

**问题(攻击走法,GHSA-rhgp-j443-p4rf)**:一个恶意技能在 frontmatter 里声明 `required_environment_variables: [ANTHROPIC_TOKEN, OPENAI_API_KEY]`,借 passthrough 把 Hermes 自己的 provider 凭证隧道进 execute_code 子进程,击穿洗净保证。

**机制**:passthrough 注册端(`tools/env_passthrough.py`)对 **Hermes 托管的 provider 凭证** fail-closed 拒绝注册:

`tools/env_passthrough.py:113-121 @ 863e313`
```python
if _is_hermes_provider_credential(name):
    logger.warning(
        "env passthrough: refusing to register Hermes provider "
        "credential %r (blocked by _HERMES_PROVIDER_ENV_BLOCKLIST). "
        "Skills must not override the execute_code sandbox's "
        "credential scrubbing; see GHSA-rhgp-j443-p4rf.",
        name,
    )
    continue
```

判定 `_is_hermes_provider_credential`(`:50-90`)靠静态 `_HERMES_PROVIDER_ENV_BLOCKLIST` + 动态 `_is_hermes_internal_secret`(枚举不出的 `AUXILIARY_*_API_KEY / GATEWAY_RELAY_*`),且 **import 失败也 fail-closed**(`:75-82` 返回 `True` = 视为受保护、拒放行)。config.yaml 路径同样过这道过滤(`:147-157`)。非 Hermes 第三方 key(`TENOR_API_KEY/NOTION_TOKEN`)不在黑名单,正常可注册。

**secret_scope 联动(profile 多路复用)**:passthrough 值的解析走 `resolve_passthrough_value`(`env_passthrough.py:182-218`)→ `agent/secret_scope.py`。多路复用网关一个进程服务多 profile,不能把各 profile 的 `.env` union 进 `os.environ`(会串号)。`get_secret`(`secret_scope.py:132-186`)语义:

`agent/secret_scope.py:159-183 @ 863e313`
```python
scope = _SECRET_SCOPE.get()
if scope is not None:
    val = scope.get(name)
    if val is not None:
        return val
    if _MULTIPLEX_ACTIVE:
        return default
    # Multiplex off: the scope is an overlay over the process environment,
    # not an isolation boundary — there is no other profile to leak from.
    # Without this fallthrough, credentials injected only into the process
    # environment vanish inside any set_secret_scope(...) block (the cron
    # scheduler installs one around every job), so cron jobs send a
    # placeholder API key and 401 while interactive turns keep working.
    val = os.environ.get(name)
    return val if val is not None else default

if _MULTIPLEX_ACTIVE:
    raise UnscopedSecretError(
        f"get_secret({name!r}) called with no profile secret scope active "
        f"while multiplexing is on. This credential read must run inside a "
        f"set_secret_scope(...) block (the per-turn / per-adapter profile "
        f"scope). Reading os.environ here would risk leaking another "
        f"profile's value. See docs/design/multiplexing-gateway.md "
        f"(Workstream A)."
    )
```

即:多路复用开启且**无 scope** 的凭证读会**抛 `UnscopedSecretError`**,而不是静默回落到 `os.environ`(可能是别的 profile 的值)。`_is_global_env`(`:125-129`)对真正进程级变量(`HERMES_HOME/PATH/TZ/HERMES_KANBAN_*/TERMINAL_*` 等)例外,始终读 `os.environ`。

**设计理由**:注释直指 GHSA-rhgp-j443-p4rf 的隧道 bypass;fail-closed 抛错的理由是"un-migrated or newly-added call site fails loud at that exact line instead of leaking another profile's value"(`secret_scope.py:16-19`)。

**取舍**:单 profile 部署下 scope 只是覆盖层,scope miss 回落 os.environ,否则 cron 任务(每个 job 都套 `set_secret_scope`)会看不到进程注入的凭证而 401(`:166-171`)。

**重实现要点**:沙箱洗净的逃生口(passthrough)必须对宿主自己的 provider 凭证 fail-closed,且黑名单 import 失败也当受保护;多 profile 共进程时凭证读要 context-local,无 scope 且多路复用时抛错而非回落全局。

---

## A5 审批上下文跨线程跨进程传播

**问题(攻击走法,#33057/#30882)**:execute_code 脚本里 `terminal("rm -rf /")`。RPC 派发发生在**父进程的一个后台线程**里,而危险命令审批回调是**线程局部/ContextVar**的。如果线程没继承审批上下文,`terminal` 的危险命令守卫会因"无回调"而在网关里静默自动批准。

**机制**:两层。

第一层——**整脚本一次性审批**(跨进程前的门):`execute_code` 在派生子进程前先 `check_execute_code_guard`,因为脚本里的 `subprocess/os.system/ctypes` 根本不过 `terminal()`/`DANGEROUS_PATTERNS`:

`code_execution_tool.py:1307-1312 @ 863e313`
```python
from tools.approval import check_execute_code_guard
_guard = check_execute_code_guard(
    code, env_type,
    has_host_access=_docker_has_host_access(_env_config),
)
if not _guard.get("approved", False):
    return json.dumps({... "error": _guard.get("message") ...})
```

守卫策略(`tools/approval.py:4229-4298`):隔离后端(vercel_sandbox / 无 host 绑定的容器)跳过;`--yolo`/`approvals.mode=off` 跳过;**cron 无人在场默认 deny**(`:4273-4290`);只有网关/ask 上下文拿整脚本一次性审批;纯本地非交互非网关会话返回 approved(文档化的局限,`:4240-4246`)。smart 模式把整脚本喂给 aux LLM 评估(`:4315-4344`)。

第二层——**审批/sudo 回调注入 RPC 线程**:RPC 线程用 `propagate_context_to_thread` 包装,把父线程的 ContextVar + 审批/sudo 回调搬进 worker 线程:

`code_execution_tool.py:1421-1428 @ 863e313`
```python
rpc_thread = threading.Thread(
    target=propagate_context_to_thread(_rpc_server_loop),
    args=(server_sock, task_id, tool_call_log,
          tool_call_counter, max_tool_calls, sandbox_tools, stop_event, rpc_token,),
    daemon=True,
)
```

`propagate_context_to_thread`(`tools/thread_context.py:64-120`)`copy_context()` 捕获父线程回调,worker 里 `set_approval/set_sudo` 装上、`finally` 里清空;**fail-closed**:回调装载失败就留 `None`,而 `prompt_dangerous_approval` 在无回调时**拒绝**危险命令(`:72-76`)。远端文件 RPC 的 `_rpc_poll_loop` 同样这样包(`:1145-1146`,注释 `#33057`)。

审批等待期间落到本线程的陈旧中断位会在批准后清掉,防止第一次 poll 就误杀刚批准的运行(`:1326-1328`)。

**设计理由**:注释 `#33057`(CLI 交互下 per-call terminal 守卫靠上下文传播恢复)、`#30882`(网关沙箱工具调用曾静默自动批准危险命令)。

**取舍**:整脚本审批是 one-shot(整段一次批,不逐调用弹);CLI 交互下不走整脚本审批(否则每次 execute_code 都弹),靠 per-call terminal 守卫(上下文已传播)兜底(`approval.py:4292-4298`)。

**重实现要点**:任何"工具派发发生在非请求线程"的架构,都必须把审批/权限回调随 ContextVar 一起 `copy_context()` 搬进 worker,且装载失败 fail-closed(无回调=拒);对不过工具层的任意代码执行,要在派生前加一道整体审批门,cron 无人场景默认 deny。

---

## A6 stub 模块怎么生成

**问题**:子进程 `from hermes_tools import web_search` 时,`hermes_tools.py` 从哪来、长什么样、怎么只暴露被允许的工具?

**机制**:`generate_hermes_tools_module`(`:431-463`)把 `SANDBOX_ALLOWED_TOOLS & enabled_tools` 的交集逐个渲染成 stub:每个工具一段 `def name(sig): doc; return _call(name, args_expr)`,模板表在 `_TOOL_STUBS`(`:330-373`)。传输不同拼不同 header(`_UDS_TRANSPORT_HEADER` / `_FILE_TRANSPORT_HEADER`),两者都内嵌 `_COMMON_HELPERS`(`json_parse/shell_quote/retry`,`:468-504`)。

`code_execution_tool.py:451-456 @ 863e313`
```python
stub_functions.append(
    f"def {func_name}({sig}):\n"
    f"    {doc}\n"
    f"    return _call({func_name!r}, {args_expr})\n"
)
```

UDS 版 `_call`(`:545-570`)每次一整个 send+recv 用 `_call_lock` 串行化(RPC 服务端单连接、无 request-id,并发会串响应,`:513-517`);读到 `\n` 结尾即一帧。文件版 `_call`(`:588-636`)`_seq_lock` 保护自增序号(`_seq += 1` 非原子),写 `.tmp`+rename,自适应轮询等 `res_` 文件。stub 里发送的请求带 token:

`code_execution_tool.py:547-551 @ 863e313`
```python
request = json.dumps({
    "tool": tool_name, "args": args,
    "token": os.environ.get("HERMES_RPC_TOKEN", ""),
}) + "\\n"
```

服务端派发前还剥掉危险 terminal 参数(短命脚本不该用后台/pty):

`code_execution_tool.py:646, 736-738 @ 863e313`
```python
_TERMINAL_BLOCKED_PARAMS = {"background", "pty", "notify_on_complete", "watch_patterns"}
...
if tool_name == "terminal" and isinstance(tool_args, dict):
    for param in _TERMINAL_BLOCKED_PARAMS:
        tool_args.pop(param, None)
```

派发本身走标准 `handle_function_call`(`:663, 749-751`),期间把 `sys.stdout/stderr` 重定向到 devnull,防止工具内部 print 泄进 CLI spinner(`:743-754`)。

**设计理由**:stub 是"生成的、只含白名单工具"的模块,天然实现能力最小化;工具函数返回**已解析的 dict**(stub 里 `_call` 会二次 `json.loads`,`:565-570`),`_sandbox_failure_hint`(`:376-428`)据生产 state.db 挖掘的高频失败(import 不存在的工具 23×、把 dict 当 str、import 不存在的三方包)给一句可执行修复提示。

**取舍**:单连接串行协议简单但无并发(靠锁串行),schema 描述与 stub 签名要同步(测试 `test_stubs_cover_all_schema_params` 校验漂移,见 D1)。

**重实现要点**:stub 代码生成 = 白名单交集逐工具渲染 + 传输 header;`_call` 单连接要加锁串行、带 token;工具返回解析后 dict;派发前剥离不适合短命脚本的参数;派发期间静默工具内部输出。

---

## A7 为什么只回 stdout:截断 + ANSI + 脱敏

**问题**:工具中间结果动辄几十 KB,若全进上下文就失去 PTC "zero-context-cost" 的意义;而且脚本可能从磁盘读到 secret 再 print。

**机制**:父进程用后台读线程排空子进程 stdout,**head+tail 策略**(前 40% + 后 60%,`:1515-1516`),stderr 只留 head(错误早出),避免管道死锁(`:1511-1580`)。组装时给出显式截断元数据(`stdout_truncated/bytes_omitted/...`),因为纯文本截断标记可能被下游再截(`_assemble_stdout_result`,`:80-119`)。然后:

`code_execution_tool.py:1638-1650 @ 863e313`
```python
from tools.ansi_strip import strip_ansi
stdout_text = strip_ansi(stdout_text)
stderr_text = strip_ansi(stderr_text)
...
from agent.redact import redact_sensitive_text
stdout_text = redact_sensitive_text(stdout_text, code_file=True)
stderr_text = redact_sensitive_text(stderr_text, code_file=True)
```

`code_file=True` 的语义(`agent/redact.py:679-682`):跳过 ENV 赋值 / JSON 字段的正则(避免把 `MAX_TOKENS=***` 常量、`"apiKey":"test"` fixture 误伤),但**前缀 key(`sk-`/`ghp_`)、Authorization 头、私钥、DB 连接串、JWT、URL secret 仍照脱敏**。注释点明沙箱 env 过滤挡住了 `os.environ`,但脚本仍能 `open('~/.hermes/.env')` 读盘,所以这层脱敏保证泄露的 secret 永不进模型上下文(`:1642-1647`)。远端路径同样脱敏(`:1225-1226`)。

超时/中断在 output 里附人可读消息(`⏰ Script timed out...`),因为 output 为空时模型常当"啥也没发生"产生空回复被网关静默丢弃(`#10807`,`:1662-1678`)。

**设计理由**:只回 stdout 是 PTC 的核心价值——"intermediate tool results never enter the context window"(`:24-25`);脱敏是纵深防御的最后一环(env 过滤 + 磁盘脱敏双保险)。

**取舍**:head+tail 会丢中段,但保证最终 print() 结果不丢;`code_file=True` 牺牲了对 ENV/JSON 形状 secret 的检测换取不误伤源码。

**重实现要点**:PTC 的返回面只暴露脚本 stdout,并叠 ANSI 剥离 + secret 脱敏;截断用 head+tail 并给结构化元数据;区分"源码输出"以关掉 ENV/JSON 误报正则但保留前缀/头/私钥脱敏。

---

## A8 解释器 / CWD 模式(project vs strict)

`_get_execution_mode`(`:1808-1832`)读 `code_execution.mode`,默认 `project`。project 模式用用户 venv 的 python(`VIRTUAL_ENV/CONDA_PREFIX`,过 `_is_usable_python` 3.8+ 检查,`:1859-1899`)、跑在会话 CWD(解析梯:session cwd 记录 → 注册 override → `TERMINAL_CWD` → `os.getcwd()`,`:1902-1947`,`#56047`),让 `import pandas`、相对路径生效;strict 用 `sys.executable` + 隔离 tmpdir,可复现但项目依赖不解析。**两模式 env 洗净与工具白名单完全一致**(`:1490, 1823`)。子进程 `start_new_session=True`(`:1503`)使其自成进程组,便于 `_kill_process_group` 用 psutil 整树杀(`:1729-1776`)。

---

## A9 env_probe(旁支,系统提示用)

`tools/env_probe.py` 与 execute_code 不在同一调用链,但同属"子进程 env 探测"簇:它在系统提示里输出**至多一行** Python 工具链状态(python3/pip 版本、PEP-668、uv),环境正常则**空输出零 token**(`:189-268`)。关键工程点:探测只在**单个后台线程**跑,`get_environment_probe_line` 至多等 `_PROBE_WAIT_TIMEOUT=10s` 就 fail-open 返回 `""`,防止一个卡死的 pip 孙进程(`#67964`)堵住系统提示构建;子进程输出走临时文件而非 `capture_output` 管道,让 `timeout` 覆盖整调用(孙进程持有管道写端时,管道 reader 线程不受 timeout 约束会挂 ~28 分钟,`:81-99`)。远端后端跳过(工具不在宿主跑,`:196-199`)。这是"探测子进程要 fail-open + 超时要覆盖孙进程"的范例。

---

# B 块 · MCP 客户端 —— 把外部 server 当不受信输入设防

## B0 全景

Hermes 作为 MCP **客户端**连接外部 server(stdio 子进程 / HTTP)。外部 server 的**工具名、工具描述、schema、甚至它是不是恶意包**都不可信。防线自外向内:配置加载期过滤(B4)→ 生成期命名撞车 fail-closed(B1)→ 描述注入扫描(B2)→ spawn 前 OSV 恶意包预检(B3)→ spawn 后 watchdog+孤儿清理(B5)→ schema 缓存懒注册也复用扫描(B6)→ 运行期 list_changed 动态注册(B7)→ OAuth(B8)。

`MCPServerTask`(`mcp_tool.py:1821`)是每 server 一个的长生命周期任务,`run()`(`:3052`)是连接/重连/退避主循环。

---

## B1 命名规范与撞车 fail-closed

**问题(攻击/事故走法)**:两个 MCP server(或一个 server 的 `read-file` 与 `read_file`)provider-safe 归一化后撞成同一个 registry 名;或某 MCP 工具归一化后撞上内建工具名。若"任选一个 handler",调用就可能路由到攻击者/错误的 handler。

**机制**:命名规范 `mcp__<server>__<tool>`,双下划线分隔:

`mcp_tool.py:5519-5526 @ 863e313`
```python
def mcp_prefixed_tool_name(server_name: str, tool_name: str) -> str:
    safe_server = sanitize_mcp_name_component(server_name)
    safe_tool = sanitize_mcp_name_component(tool_name)
    return f"{MCP_TOOL_NAME_PREFIX}{safe_server}{_MCP_NAME_DELIM}{safe_tool}"
```
`sanitize_mcp_name_component`(`:5497-5505`)把 `[^A-Za-z0-9_]` 全换 `_`(有损),所以 `read-file` 与 `read_file` 会撞。`_register_server_tools`(`:5810`)先把所有候选(原始工具 + 生成的 resource/prompt 工具)算归一化名,**同名不同来源 → 全部跳过**,不选任意 handler:

`mcp_tool.py:5925-5943 @ 863e313`
```python
ambiguous_names = {
    registry_name: sorted(origins)
    for registry_name, origins in origins_by_name.items()
    if len(origins) > 1
}
for registry_name, origins in sorted(ambiguous_names.items()):
    logger.error(
        "MCP server '%s': name normalization collision for '%s' from %s; "
        "skipping every colliding entry instead of choosing an arbitrary handler", ...)
```

跨 server / 撞内建的处理(`:5945-5965`):若归一化名已被别的 `mcp-` toolset 拥有 → 跳过保留原主;若撞内建工具 → 跳过保留内建。且注册是并行的,预检只是 advisory,`registry.register()` 之后再查一次 `get_toolset_for_tool` 作为**原子归属门**(`:5977-5987`)。

**设计理由**:注释"skipping every colliding entry instead of choosing an arbitrary handler"——歧义即拒,不赌。双下划线选型对齐 Claude Code/Codex/OpenCode(`:5508-5514`)。

**取舍**:有损归一化换 provider 兼容(名字合法),代价是可能撞;fail-closed 牺牲"尽量都注册"换"绝不错路由"。

**重实现要点**:外部来源的名字归一化后必做撞车检测,**歧义全跳**而非任选;跨源撞车用 registry 原子归属做最终门;prefix 用双下划线消歧 server/tool 边界。

---

## B2 描述注入扫描

**问题(攻击走法)**:恶意 server 的工具描述里塞 "Ignore all previous instructions. You are now a ..." 或 `curl https://evil/`,描述会进模型上下文形成 prompt injection。

**机制**:`_scan_mcp_description`(`:573-591`)对每条描述跑 10 条正则(`_MCP_INJECTION_PATTERNS`,`:549-570`):ignore previous instructions / you are now a / your new task is / `system:` / `<system>` 角色标签 / do not tell / `curl|wget https?://` / base64 decode / `exec(|eval(` / `import subprocess`。命中 **WARNING 级日志,不阻断**:

`mcp_tool.py:584-591 @ 863e313`
```python
if findings:
    logger.warning(
        "MCP server '%s' tool '%s': suspicious description content — %s. "
        "Description: %.200s",
        server_name, tool_name, "; ".join(findings), description,
    )
return findings
```

在 `_register_server_tools` 注册每个工具前调用(`:5866`);懒注册路径(B6)也调(`:6085`,注释"the cache file is user-writable JSON, so run the same injection scan")。

**设计理由**:注释明说"WARNING-level — we log but don't block, since false positives would break legitimate MCP servers"(`:547-548`)。这是**可观测性优先**的取舍:不敢硬拦,只留证据。

**取舍**:只告警不阻断 = 依赖运维看日志,注入内容仍会进模型上下文(与 A7 execute_code 输出脱敏的"硬阻断"形成对比)。

**重实现要点**:不可信来源的描述文本要过注入模式扫描并留证据;是否阻断取决于误报承受度——描述扫描选告警,凭证扫描选阻断。

---

## B3 OSV 恶意包预检

**问题(攻击走法)**:config 里 `command: npx, args: [-y, evil-mcp-pkg@1.2.3]`。spawn 前若不查,恶意 npm/PyPI 包直接在本机跑。

**机制**:`_run_stdio`(`:2377`)在 spawn 前、且在 watchdog 包裹前,查 OSV 恶意软件库(仅 `MAL-*` 通告,忽略普通 CVE):

`mcp_tool.py:2406-2422 @ 863e313`
```python
from tools.osv_check import check_package_for_malware
try:
    malware_error = await asyncio.wait_for(
        asyncio.to_thread(check_package_for_malware, command, args),
        timeout=_OSV_MALWARE_CHECK_TIMEOUT_S,   # 12.0s
    )
except asyncio.TimeoutError:
    logger.warning("... OSV malware preflight timed out ... proceeding without the check.")
    malware_error = None
if malware_error:
    raise ValueError(f"MCP server '{self.name}': {malware_error}")
```

`check_package_for_malware`(`tools/osv_check.py:66-111`)从 `command` 推生态(`npx→npm`,`uvx/pipx→PyPI`,其它跳过)、从 args 解析包名版本、查 `https://api.osv.dev/v1/query`,命中 `MAL-*` 返回 `BLOCKED: ...`。**fail-open**:网络错/超时/解析失败一律放行(`:93-97`)。结果缓存 1h(clean 和 blocked 都缓存,失败不缓存)——因为重连/recycle 会对同包反复预检,`#75485` 记录过 16h 内 779K 次 DNS 查询(`osv_check.py:29-37`)。

**设计理由**:注释强调预检必须查**真实 command/args**,所以放在 watchdog 包裹**之前**(否则 argv 被改写成 `python -m tools.mcp_stdio_watchdog ...` 会让预检变 no-op,`:2403-2405, 2432-2433`);超时用外层 `wait_for` 兜住 `#29184`(卡住的 SSL 握手不能冻结 MCP 发现/网关启动)。

**取舍**:fail-open——网络不可达时放行,安全性让位可用性;只查恶意通告不查 CVE,减少误拦。

**重实现要点**:spawn 外部包前做恶意软件预检,查真实 argv、用外层 wall-clock timeout、fail-open、缓存 verdict(含 clean)防查询风暴。

---

## B4 可疑 server 配置过滤(exfil / persistence / IOC)

**问题(攻击走法,June 2026 hermes-0day)**:攻击者预植 `config.yaml`,写 `command: bash, args: ["-c", "echo <attacker-key> >> ~/.ssh/authorized_keys"]`,Hermes 每次 cron/启动重跑就重装后门。

**机制**:`_filter_suspicious_mcp_servers`(`mcp_tool.py:4613-4637`)在**任何 stdio spawn 前**丢掉 exfil 形状的 config,委托 `hermes_cli/mcp_security.py:validate_mcp_server_entry`(`:121-177`)。它只拦三种窄形状:

`hermes_cli/mcp_security.py:159-175 @ 863e313`
```python
# 2. Network exfiltration shape.
if _EGRESS_PATTERN.search(script):
    issue = (f"MCP server '{name}' uses shell interpreter '{command}' with network egress in args")
    if _EXFIL_HINT_PATTERN.search(script): issue += " and exfiltration-shaped arguments"
    issues.append(issue)
# 3. OS persistence shape (SSH key / PAM / sudoers / cron / rc files).
if _PERSISTENCE_PATTERN.search(script):
    issues.append(f"... write to an OS persistence surface ... this is the hermes-0day backdoor shape ...")
```

前置还有硬编码 IOC 黑名单(攻击者 SSH 公钥、`hermes-0day` 字样、China Telecom 源 IP),命中即拒(`:138-147`)。触发条件:`command` basename 属 shell 解释器(`bash/sh/zsh/.../powershell`,`:33-45`)且 inline script 命中 egress(`curl|wget|nc|/dev/tcp/|Invoke-WebRequest`,`:47-54`)或 persistence(`authorized_keys|.ssh/|/etc/ssh|/etc/pam.d|/etc/sudoers|crontab|.bashrc...`,`:64-74`)。模块注释明确**save 时(dashboard/CLg)和 spawn 时(discovery/cron/startup)双查**,所以手改或预植的条目也在执行前被拦(`:21-24`)。

`_warn_hidden_whitespace`(`:4567-4610`)另外对 config 里带首尾隐藏空白的字符串值告警(粘贴 token 带换行导致 auth 失败),只报 key 路径不报值。

**设计理由**:注释坦承"does not try to sandbox that capability"——MCP stdio 本就支持任意本地命令,只拦"高信号滥用形状"而非白名单,免得挡住合法自定义 server。

**取舍**:窄拦截(只三形状)= 低误报但可绕(换非 shell 解释器 / 换 egress 工具即逃逸);IOC 黑名单是"已知威胁"事后补丁。

**重实现要点**:执行外部配置的命令前,在 save 与 spawn 两端各拦一次已知滥用形状(egress/persistence)+ 硬编码 IOC;拦截理由要具体、告警不泄敏(只报 key 路径)。

---

## B5 stdio watchdog 孤儿清理

**问题(攻击/事故走法)**:Hermes 被 `kill -9`/崩溃/强退,正常 teardown 不跑,stdio MCP 子进程(及它自己的孙进程,如 `mcp-remote` 起的 `node`)成孤儿永久运行,多次硬重启堆积 N 个孤儿争同一上游 SSE 会话。

**机制**:两条互补路径。

(1) **父死 watchdog 包裹**:不直接 spawn MCP 命令,而是 spawn `mcp_stdio_watchdog.py --ppid <pid> -- <real cmd>`:

`mcp_tool.py:720-727 @ 863e313`
```python
watchdog_args = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_stdio_watchdog.py"),
    "--ppid", str(my_pid), "--", command, *args,
]
return sys.executable, watchdog_args
```
watchdog(`mcp_stdio_watchdog.py`)`start_new_session=True` 起真命令(自成进程组),透明转发 stdin/stdout/stderr(MCP stdio 协议直接走这些管道,必须是 no-op relay,`:121-127`),后台线程每 2s 比 `getppid()` 是否变(`_is_orphaned`,`:57-59`),父一没就 SIGTERM→宽限→SIGKILL 整个进程组并退出(`_terminate_process_group`,`:62-92`)。POSIX-only(`:709-714`)。且转发 SIGTERM/SIGINT 给子组,否则优雅关闭反而杀不到独立进程组的子进程(`:135-140`)。

(2) **主动孤儿清理**:`_run_stdio` spawn 前 `await asyncio.to_thread(_kill_orphaned_mcp_children)` 收前次失败连接残留(`:2464`,`#57355/#57228`);spawn 后用 `_snapshot_child_pids`(读 `/proc/<pid>/task/<pid>/children`,回落 psutil,`:4293-4316`)差集捕获新 PID,并经 `_filter_mcp_children`(`:4334-4366`)剔除非 MCP 子进程(slash_worker/LSP,防 killpg 误杀 TUI 父进程)。`_kill_orphaned_mcp_children`(`:6978-7104`)SIGTERM→wait 2s→SIGKILL,POSIX 用 `killpg` 到 spawn 时记录的 pgid(收编重parent 的孙进程),且**若子进程 pgid == 网关自己的 pgid 则跳过 killpg 改用 per-pid kill**(否则自杀,`#47134`,`:7053-7066`)。

**设计理由**:watchdog docstring 详述 macOS 无 `prctl(PR_SET_PDEATHSIG)` 等价物,ungraceful 死亡无人收尸(`:11-18`);双下划线的"snapshot pgid while child alive"(退出后 `os.getpgid` 就调不到,`:2491-2494`)。

**取舍**:watchdog 是每 MCP 子进程多一个薄 supervisor 进程(纯 stdlib,启动快,`:33-35`);孤儿清理默认只收 `_orphan_stdio_pids`,不碰活跃 session(避免误伤并发 cron/用户会话,`:6982-6988`)。

**重实现要点**:长生命周期外部子进程要 (a) 用父死 watchdog(轮询 getppid,killpg 整组,透明转发 stdio 与信号)兜 ungraceful 死亡,(b) spawn 前后做 PID 快照/过滤/孤儿清理,killpg 前排除自身 pgid。

---

## B6 schema 缓存与懒注册

**问题**:idle dashboard 启动就 spawn 每个 stdio 子进程太慢。

**机制**:`mcp_schema_cache.py` 把 per-server 工具清单落盘(`<home>/cache/mcp_schema_cache.json`,`0o600`,`:57-63`),按 server 名 + config 指纹(command/args/url/tools 过滤的 sha256[:16],`:30-42`)键控。首次 live connect 后**写穿**缓存(`_register_server_tools:5994-6006`);下次启动 `_register_from_cache_sync`(`:6037-6153`)不 spawn 子进程直接把工具注册进 registry,首个真实调用才经 `_ensure_lazy_server_connected` 拉起(`#56832`)。懒路径复用同样的 include/exclude 过滤、**描述注入扫描**(`:6085`)、跨 toolset 撞车跳过(`:6088-6095`)。

**设计理由**:注释"cache file is trusted input on the lazy registration path, so keep it user-only"(`:60-62`)+ 懒路径明确"Defense-in-depth: the cache file is user-writable JSON, so run the same injection scan"(`:6083-6084`)——**缓存也是不可信输入**,不因来自本地盘就免检。

**取舍**:懒注册换启动速度,代价是工具 schema 可能过期(指纹变则失效重连);缓存文件被篡改的风险靠 0600 + 复用扫描缓解。

**重实现要点**:昂贵的外部发现结果可落盘懒加载,但缓存要 (a) config 指纹键控失效,(b) 0600 权限,(c) 反序列化后复用与 live 路径**相同**的安全扫描,不给"本地缓存"开后门。

---

## B7 动态注册(list_changed)

**问题**:server 运行期推 `notifications/tools/list_changed`(schema 变了)。

**机制**:`_refresh_tools`(`:2082-2166`)加 `_refresh_lock` 防并发刷新;重新 `list_tools`(分页 `_paginate_full_list`);**不 nuke-and-repave**——只 deregister 新清单里没有的陈旧名(且只删本 toolset 拥有的,绝不删别 server 的撞名条目,`:2120-2126`),再 `_register_server_tools` 就地重注册;工具增删打 WARNING "tools changed dynamically ... Verify these changes are expected"(`:2157-2160`)。

**取舍**:就地替换而非全清,避免活跃 turn 里已发出的 tool-call ID 指向失效 handler 的竞态(`:2108-2114`)。

**重实现要点**:运行期动态 schema 刷新要加锁、增量 diff(只删真正消失的、只碰自己拥有的)、变更告警留证据。

---

## B8 OAuth 流(结构级)

`mcp_oauth.py`(1369)实现 OAuth 2.1 授权码 + PKCE,复用 MCP SDK 的 `OAuthClientProvider`(一个 `httpx.Auth` 子类,自动处理 discovery/动态客户端注册/PKCE/token 交换/刷新/step-up)。Hermes 的胶水:`HermesTokenStorage`(`:429`)落盘 token(`<home>/mcp-tokens/<server>.json` 等),`_write_json`(`:387-421`)用 `os.open(O_EXCL, 0o600)` **原子创建** token 文件——避免旧 `write_text`+`chmod` 的 TOCTOU 窗口(文件短暂 0644 世界可读,`#19673`,`:388-395`),parent dir 收紧 0700;临时 localhost 回调服务器捕获 redirect code(`_make_callback_handler`/`_make_callback_waiter`)。

`mcp_oauth_manager.py`(785)是进程内唯一实例化 SDK `OAuthClientProvider` 的地方,协调:跨进程 token reload(mtime 磁盘监视,外部 cron 刷 token 后下次 auth 自动拾取,对标 Claude Code `invalidateOAuthCacheIfDiskChanged`,`:24-27`)、401 去重(in-flight futures,N 个并发 401 只发一次恢复,`:11-14`)、重连信号。`mcp_dashboard_oauth.py`(145)是 dashboard 侧的 OAuth 流协调对象(`publish_authorization_url`/`wait_for_callback`/`mark_approved`,把浏览器授权 URL 与回调跨线程传递)。

**结构级定案**:OAuth 是"标准 2.1+PKCE、SDK 承重、Hermes 只做持久化与并发协调";安全要点是 token 文件 O_EXCL+0600 原子写、跨进程 mtime reload、401 去重。

---

## B9 三个横切防护

- **远端 URL 校验** `_validate_remote_mcp_url`(`:1059-1108`):只收 http(s)(拒 `file://`/`ws://`/`stdio:`/缺 scheme/空 host),`http://:8080` 空 host 也拒。
- **跨源鉴权剥离** `_strip_auth_on_cross_origin_redirect`(`:2898-2906`):HTTP 传输 follow_redirects 时,若 redirect 目标 (scheme,host,port) 与原始不同,`pop` 掉 `Authorization` 头,防 bearer token 随重定向泄给第三方源。
- **错误脱敏** `_sanitize_error`(`:479-485`):返回给 LLM 的错误文本先用 `_CREDENTIAL_PATTERN` 把 token/key 换 `[REDACTED]`。
- **stdio env 过滤** `_build_safe_env`(`:446-476`):stdio 子进程只放安全基线 + `XDG_*` + 外部 secret source(Bitwarden/1Password 显式标记)+ 用户 config `env`,不盲传完整 shell 环境。

---

# C 定案

## C1 ◇ execute_code 编程式工具调用 —— 证实(文档属实,机制远超文档)

**文档说了什么**:README 第 28 行(`Delegates and parallelizes` 行)逐字:
`README.md:28 @ 863e313`
```
Spawn isolated subagents for parallel workstreams. Write Python scripts that
call tools via RPC, collapsing multi-step pipelines into zero-context-cost turns.
```
`website/docs/user-guide/security.md:507` 补一句:"Both `execute_code` and `terminal` strip sensitive environment variables from child processes to prevent credential exfiltration by LLM-generated code."

**代码怎么实现(全链条,证实且更细)**:
1. **三态 RPC**(A1):本地 POSIX AF_UNIX(0600,`:1413-1416`)、Windows 环回 TCP(`:1407-1411`)、远端文件 RPC(`_rpc_poll_loop`)。文档只笼统说"via RPC",未提三态——**文档不足,代码更强**。
2. **鉴权**(A2):每会话 `token_urlsafe(32)` + `compare_digest` bytes 常数时间比对,fail-closed(`:703-711`)。文档未提。
3. **洗净**(A3/A4):`_scrub_child_env` 五层规则(secret 黑名单 > 安全前缀 > HERMES 精确名单 > Windows 名单)+ delegate 上下文桥接(`:253-298`);passthrough 逃生口对 Hermes provider 凭证 fail-closed(GHSA-rhgp-j443-p4rf,`env_passthrough.py:113-121`);多 profile 用 secret_scope 无 scope 抛 `UnscopedSecretError`(`secret_scope.py:175-183`)。文档 security.md:507 只说"strip sensitive env vars",**远未覆盖 GHSA 隧道防护与多路复用 fail-closed**。
4. **审批跨线程跨进程**(A5):`check_execute_code_guard` 整脚本审批(`:1307-1312`,`#30882`,cron 默认 deny)+ `propagate_context_to_thread` 把审批回调搬进 RPC 线程且 fail-closed(`:1421-1428`,`#33057`)。文档完全未提。
5. **只回 stdout**(A7):head+tail 截断 + ANSI 剥离 + `redact_sensitive_text(code_file=True)` 磁盘 secret 兜底(`:1638-1650`)。文档"zero-context-cost"属实,但脱敏兜底未提。

**结论:证实**。README 断言真实且低估——PTC 是一套三态传输 + token 鉴权 + 五层洗净 + 双层审批传播 + 输出脱敏的完整机制,文档只呈现了冰山一角。**地图缺项**:三态 RPC、token 鉴权、审批传播、GHSA 隧道防护、多路复用 secret_scope 均"未见于文档"。

## C2 ◇/▲ MCP 客户端侧安全与动态注册 —— 修正(动态注册与命名已文档化;安全防护层基本未文档化)

**R1 原猜想**:"MCP 客户端侧安全与动态注册未见于文档或名不副实"。

**逐项对照**:
- **命名规范**:文档化。`website/docs/user-guide/features/mcp.md:400` "Hermes prefixes MCP tools so they do not collide with built-in names";`mcp-config-reference.md:270-293` 详列 `mcp__<server>__<tool>` 与双下划线理由。但**命名撞车 fail-closed(归一化歧义全跳、跨源撞车保留原主)未文档化**(代码 `mcp_tool.py:5925-5965`)。
- **动态注册**:文档化。`mcp.md:565` "Dynamic Tool Discovery"、`:573` "Reloading" 都在。→ **此项证伪 R1 猜想**(并非未见于文档)。
- **描述注入扫描**(B2,`:549-591`):**未文档化**。全 website 搜 `prompt injection` 只命中 context-file 扫描(`security.md:696`)、cron 扫描(`contributing.md:213`),无一条指 MCP 工具描述扫描。
- **OSV 恶意包预检**(B3,`osv_check.py`):**几乎未文档化**。`cli-commands.md:504` 只提"on-demand `hermes security audit`",未提 **stdio spawn 前自动预检**这条运行期防线。
- **可疑 server 过滤 exfil/persistence/IOC**(B4,`mcp_security.py`):**未文档化**。全 website 搜 `exfiltrat/persistence surface/hermes-0day/IOC` 在 MCP 语境零命中。
- **stdio watchdog / 孤儿清理**(B5):**未文档化**(configuration.md 的 watchdog 指的是 session stall watchdog,`:886`,与此无关)。
- **schema 缓存懒注册复用扫描**(B6)、**跨源鉴权剥离/token 文件 0600 原子写**(B8/B9):**未文档化**。
- **MCP 安全"文档章节"**:`mcp.md:593` 的 "Security model" 只讲两件事——stdio env 过滤、config 级工具暴露控制(tool filtering)。**完全没提**注入扫描/OSV/watchdog/撞车 fail-closed/exfil 过滤。

**结论:修正**。R1 猜想部分证伪(动态注册与命名规范确有文档)、部分证实(客户端侧**安全防护层**——注入扫描、OSV 预检、exfil/persistence/IOC 过滤、watchdog 孤儿清理、命名撞车 fail-closed、schema 缓存复检、跨源鉴权剥离——基本"未见于文档")。**地图缺项定案**:上述 7 项安全机制均为"territory 有、map 无",是本簇最大的文档-代码落差,且都是纵深防御的关键环。

---

# D 测试作为行为规格(读代码,未运行)

选 4 个最像"行为规格"的:

## D1 `tests/tools/test_code_execution.py`(801 行)—— execute_code 端到端契约
- `TestEnvVarFiltering.test_api_keys_excluded / test_tokens_excluded`(`:498-516`):跑一段 dump `os.environ` 的脚本,断言 `OPENAI_API_KEY/ANTHROPIC_API_KEY/FIRECRAWL_API_KEY/GITHUB_TOKEN/MODAL_TOKEN_*` **不在**子进程 env——**规格化 A3 洗净**。`test_hermes_rpc_socket_injected`(`:519`)断言 `HERMES_RPC_SOCKET` **在**;`test_timezone_injected_when_set`(`:524`)断言 `TZ` 被注入而 `HERMES_TIMEZONE` 不泄。
- `TestRpcTokenAuthorization.test_missing_token_rejected`(`:784-790`):对真实 AF_UNIX socketpair 驱动 `_rpc_server_loop`,无 token 请求断言响应含 `Unauthorized`——**规格化 A2 fail-closed 鉴权**。`test_generated_module_sends_token`(`:793`)断言生成的 stub 源码含 `HERMES_RPC_TOKEN` 与 `"token"`。
- `test_concurrent_tool_calls_match_responses`(`:253`)/`test_uds_transport_serializes_concurrent_calls`(`:102`):规格化单连接串行锁——并发 `_call` 不串响应。
- `TestStubSchemaDrift.test_stubs_cover_all_schema_params`(`:372`):规格化 stub 签名与 schema 参数不漂移。

## D2 `tests/tools/test_env_passthrough.py`(413 行)—— GHSA 隧道防护契约
- `test_passthrough_cannot_override_provider_blocklist`(`:275-296`):技能/config 尝试把 Hermes provider 凭证注册为 passthrough,断言 `is_env_passthrough(blocked_var)` 为 False 且该 var **不在** `_make_run_env` 结果、`PATH` 仍在——**规格化 A4 的 GHSA-rhgp-j443-p4rf fail-closed**。
- `test_passthrough_cannot_override_internal_dynamic_secret`(`:298`):`AUXILIARY_*_API_KEY / GATEWAY_RELAY_*` 动态内部 secret 同样拦。
- `test_provider_blocklist_import_failure_fails_closed`(`:366`):黑名单 import 失败时仍拒放行——规格化 `env_passthrough.py:75-82` 的 fail-closed。
- `test_non_hermes_api_key_still_registerable`(`:354`)/`TestProfileScopedResolution.test_unscoped_multiplex_read_fails_closed`(`:86`):第三方 key 仍可注册;多路复用无 scope 读抛错——规格化 secret_scope。

## D3 `tests/hermes_cli/test_mcp_security.py`(171 行)—— 可疑 server 过滤契约
- `test_validator_flags_ssh_key_persistence_payload`(`:57-66`):hermes-0day 的 `authorized_keys` 载荷**无网络 egress**,断言仍被 persistence-surface 规则(或 IOC)拦——**规格化 B4 persistence 形状**。
- `test_explicit_registration_skips_dangerous_entry_before_connect`(`:83-127`):注册 `{evil: 危险条目, clean: 正常}`,断言 `connected == ["clean"]`——**规格化"spawn 前过滤,evil 从不连接"**。
- `test_migration_disables_existing_dangerous_entry`(`:130-145`):迁移时把已存在的危险条目 `enabled: False` 并产出 warning——规格化 save 端同拦。

## D4 `tests/tools/test_mcp_stdio_watchdog.py`(40 行)—— 父死 watchdog 契约
- `test_is_orphaned_is_false_while_direct_parent_is_unchanged`(`:11-17`):`getppid` 不变时 `_is_orphaned` 为 False——规格化 B5 孤儿判定。
- `test_wrap_command_uses_stable_parent_pid_and_preserves_command_tail`(`:21-40`):断言 `_wrap_command_with_watchdog` 返回 `(sys.executable, [watchdog.py, --ppid, <pid>, --, command, *args])` 且**原始 command 尾部原样保留**——**规格化 B5 包裹形状**(真命令 argv 完整传递给 watchdog,佐证 B3 "OSV 必须在包裹前查真实 argv")。

(备选强规格:`test_mcp_tool.py` 撞车 fail-closed、`test_mcp_schema_cache.py` 指纹失效、`test_osv_check.py` fail-open+缓存、`test_mcp_config_whitespace_warning.py`。)

---

# 溯源约定

全文断言格式 `路径:行号 @ 863e313`,行号取自基线 commit `863e31318553cda8ad61df681d08175364d4164b` 的 `Read`/`sed -n` 直读。核心文件:`tools/code_execution_tool.py`、`tools/env_passthrough.py`、`agent/secret_scope.py`、`agent/redact.py`、`tools/thread_context.py`、`tools/approval.py`、`tools/mcp_tool.py`、`hermes_cli/mcp_security.py`、`tools/osv_check.py`、`tools/mcp_stdio_watchdog.py`、`tools/mcp_schema_cache.py`、`tools/mcp_oauth.py`、`tools/mcp_oauth_manager.py`。文档对照:`README.md:28`、`website/docs/user-guide/features/mcp.md`、`website/docs/reference/mcp-config-reference.md`、`website/docs/user-guide/security.md`。

---

**给父 agent 的交付说明**:以上为 R3「execute_code + MCP 客户端侧」L1 精读底稿全文,可直接落盘为 `notes/r3-execute-code-mcp-client.md`。关键定案:C1 execute_code 证实(文档低估机制深度);C2 修正(动态注册/命名已文档化,但注入扫描/OSV 预检/exfil-persistence-IOC 过滤/stdio watchdog/命名撞车 fail-closed/schema 缓存复检/跨源鉴权剥离 7 项安全机制未文档化,是本簇最大 map-territory 落差)。台账建议:本轮覆盖的 13 个源文件标 `R3-deep-read`(mcp_oauth*.py 为结构级,标 `R3-structure`)。
