# R5 底稿 · R4-structure 四文件清账

溯源约定:所有断言紧跟 `路径:行号 @ 863e313` 与逐字代码块(行号已实测)。基线 commit `863e31318553cda8ad61df681d08175364d4164b` 已核对(`git -C /home/user/hermes-agent rev-parse HEAD`)。四文件行数实测:local.py 1687、browser_tool.py 5098、shell_hooks.py 930、desktop_ui.py 40。本稿不复述 base.py 已定契约(spawn-per-call + 会话快照重放),只讲各文件特有机制与分工边界。

---

## 1. tools/environments/local.py(1687 行)—— 本地 subprocess 后端

### 1.1 与 base.py 的分工总账

base 拥有:`execute()` 统一流程、`_wrap_command`(source 快照→cd→eval→re-dump→cwd marker)、`init_session` bootstrap 脚本、`_extract_cwd_from_output` 的 marker 解析、超时/中断等待。local 只 override 七个点:`get_temp_dir`、`_quote_cwd_for_cd`、`_quote_shell_path`、`_run_bash`、`_kill_process`、`_update_cwd`/`_extract_cwd_from_output`、`cleanup`,外加类属性 `_profile_scoped_passthrough = True`。

`tools/environments/local.py:1414-1427 @ 863e313`:
```python
class LocalEnvironment(BaseEnvironment):
    """Run commands directly on the host machine.

    Spawn-per-call: every execute() spawns a fresh bash process.
    Session snapshot preserves env vars across calls.
    CWD persists via file-based read after each command.
    """

    _profile_scoped_passthrough = True

    def __init__(self, cwd: str = "", timeout: int = 60, env: dict = None):
        cwd = _resolve_local_initial_cwd(cwd)
        super().__init__(cwd=cwd, timeout=timeout, env=env)
        self.init_session()
```

注意 `_update_cwd` 的注释澄清了历史:local 曾经用 temp 文件读回 cwd,现在与远程后端共享 stdout marker 解析,docstring "CWD persists via file-based read" 已是旧说法(见 1.4)。

### 1.2 没有 PTY;进程组隔离 = `start_new_session=True`

**回答任务的 "PTY?":这一层没有 PTY。** 前台终端命令是纯 pipe:stdout=PIPE、stderr 合并进 stdout、stdin 要么 DEVNULL 要么 pipe(`_pipe_stdin` 线程异步写,从 base 导入,tools/environments/local.py:17)。PTY 存在于别处(`hermes_cli/pty_bridge.py` 的交互 `!` shell、`tools/process_registry.spawn_local` 的后台进程),不属于环境后端。

`tools/environments/local.py:1532-1553 @ 863e313`:
```python
        proc = subprocess.Popen(
            args,
            text=True,
            env=run_env,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
            start_new_session=True,
            cwd=_popen_cwd,
            **_popen_kwargs,
        )
        if not _IS_WINDOWS:
            try:
                proc._hermes_pgid = os.getpgid(proc.pid)
            except ProcessLookupError:
                pass

        if stdin_data is not None:
            _pipe_stdin(proc, stdin_data)
```

`start_new_session=True` 即在子进程里 `setsid()`——不是 `os.setsid` 直调,而是 Popen 参数形式,让 bash 及其全部子孙独占一个进程组。PGID 提前存到 `proc._hermes_pgid`,防止 kill 时 wrapper 已死查不到组。

**杀进程 = 杀组,两段式,且等的是"组灭"不是"wrapper 灭"。** base 的默认 `_kill_process` 只 `proc.kill()`(base.py:1223-1228);local 重写为 killpg SIGTERM → 等 1s → SIGKILL → 等 2s:

`tools/environments/local.py:1608-1624 @ 863e313`:
```python
                try:
                    os.killpg(pgid, signal.SIGTERM)  # windows-footgun: ok — POSIX process-group SIGTERM (guarded by _IS_WINDOWS above)
                except ProcessLookupError:
                    return

                # Wait on the process group, not just the shell wrapper. Under
                # load the wrapper can exit before grandchildren do; returning
                # at that point leaves orphaned process-group members behind.
                if _wait_for_group_exit(pgid, 1.0):
                    return

                try:
                    # POSIX-only: _IS_WINDOWS is handled by the outer branch.
                    os.killpg(pgid, signal.SIGKILL)  # windows-footgun: ok — POSIX process-group SIGKILL
                except ProcessLookupError:
                    return
                _wait_for_group_exit(pgid, 2.0)
```

组存活探测用 `killpg(pgid, 0)`,`PermissionError` 也算活(组存在只是无权发信号,tools/environments/local.py:1559-1568);等待循环里穿插 `proc.poll()` 收尸,否则死而未收的组长会让 killpg(pgid,0) 一直报组还活着(tools/environments/local.py:1570-1586)。Windows 分支走 `gateway.status.terminate_pid(force=True)`(tools/environments/local.py:1589-1599)。

**后台 spawn 面用的是"用户登录 shell",不是 bash。** `_find_shell` 只在 `$SHELL` 属于 POSIX-sh 家族时尊重它,否则回退 `_find_bash`——因为 spawn_local 的调用形态是 `[shell, "-lic", "set +m; …"]`,fish/csh/nushell 会直接语法报错;而 macOS 上强选 bash 3.2 又会被 `~/.bash_profile` 里的 `exec /bin/zsh -l` 吞掉 `-c` 参数(#42203):

`tools/environments/local.py:1008-1012 @ 863e313`:
```python
# POSIX-sh-family shells that understand the ``[shell, "-lic", "set +m; …"]``
# invocation spawn_local uses. $SHELL values outside this set (fish, csh/tcsh,
# nushell, elvish, xonsh, …) would error on that syntax, so _find_shell falls
# back to bash for them rather than honouring $SHELL. (#42203)
_SPAWN_COMPATIBLE_SHELLS = frozenset({"bash", "zsh", "sh", "dash", "ksh", "mksh"})
```

对应调用点 `tools/process_registry.py:738 @ 863e313`:`[user_shell, "-lic", f"set +m; {safe_command}"]`。

### 1.3 cwd 三道防线(local 特有)

**第一道:构造期锚定相对 cwd。** config 里的 `TERMINAL_CWD` 若是相对路径且恰好等于进程当前目录的尾段(如 `hermes-agent` 而进程已在 `~/.hermes/hermes-agent`),`abspath` 会指向不存在的嵌套目录;`_resolve_local_initial_cwd` 检测尾段匹配后直接用当前目录(tools/environments/local.py:53-90,尾段比较在 83-88)。

**第二道:每次 spawn 前的安全 cwd 恢复。** `os.path.isdir` 不够——`/root` 对非 root 用户 stat 成功但 Popen(cwd=…) 抛 PermissionError(#65583,root 启动的 CLI 把 `/root` 泄进共享状态,非 root gateway 的 cron 永久全挂);目录也可能被上一条命令 `rm -rf` 自己删掉(#17558)。所以先 `X_OK` 检查,再逐级向上找可进入的祖先,兜底 tempdir:

`tools/environments/local.py:140-152 @ 863e313`:
```python
def _cwd_usable(path: str) -> bool:
    """True when *path* is a directory this process can actually chdir into.

    ``os.path.isdir`` alone is not enough: stat() on ``/root`` succeeds for a
    non-root user (only ``/`` needs search permission), but
    ``subprocess.Popen(cwd='/root')`` then dies with ``PermissionError:
    [Errno 13] Permission denied: '/root'``. Seen in the wild when a
    root-launched CLI session leaks ``/root`` into shared state that a
    non-root gateway/cron process later reads (#65583) — every cron job's
    terminal/file tool then fails on every command, forever. Checking
    X_OK up front lets the caller fall back instead.
    """
    return os.path.isdir(path) and os.access(path, os.X_OK)
```

`_run_bash` 集成处只在"目录真不存在"时告警,MSYS→Windows 纯归一不告警(tools/environments/local.py:1513-1526)。

**第三道:命令后 cwd 回写校验。** 共享 base 的 marker 解析,但 override 加了 Windows 归一 + isdir 验证 + 回滚:

`tools/environments/local.py:1659-1668 @ 863e313`:
```python
        prev_cwd = self.cwd
        super()._extract_cwd_from_output(result)
        if self.cwd != prev_cwd:
            normalized = _msys_to_windows_path(self.cwd) if _IS_WINDOWS else self.cwd
            if normalized and os.path.isdir(normalized):
                self.cwd = normalized
            else:
                # Stale / non-existent path — keep previous cwd; _run_bash
                # will resolve a safe fallback on the next call if needed.
                self.cwd = prev_cwd
```

### 1.4 环境净化 —— 本文件其实是全仓 subprocess env 政策的"单一权威"

local.py 有约 700 行(200-719、1268-1328)不是 LocalEnvironment 的方法,而是全仓各 spawn 面共用的 env 工厂。四个入口、一套底层谓词:

| 入口 | 面向 | 特点 |
|---|---|---|
| `_make_run_env`(1268-1328)| 前台终端 `_run_bash` | `os.environ | self.env` 合并 + blocklist + PATH 手术 |
| `_sanitize_subprocess_env`(456-513)| 后台/PTY spawn(process_registry.spawn_local)| skill 感知(env_passthrough)|
| `hermes_subprocess_env`(574-656)| 非终端 spawn(浏览器、ACP/CLI executor、TUI Node host…)| 两层剥离,`inherit_credentials` 可 grep 审计 |
| `build_subprocess_env`(659-719)| 统一工厂 | "~11 个 commit 各修一个漏网 spawn 点"之后的类级修复 |

**Blocklist 三层结构:**

(a) 静态名单 `_HERMES_PROVIDER_ENV_BLOCKLIST`:从 provider 注册表 + `OPTIONAL_ENV_VARS`(tool/messaging 类别、password 型 setting)派生,再并上硬编码大名单(tools/environments/local.py:225-337)。两个刻意的反向决定值得记:AWS 通用凭据链**故意可继承**(SECURITY.md §3.2:本地终端是用户的可信操作 shell,只剥 Bedrock 专属 `AWS_BEARER_TOKEN_BEDROCK`,tools/environments/local.py:206-222);`CLAUDE_CODE_OAUTH_TOKEN` **故意 discard 出名单**——剥掉它曾导致 agent 起的 `claude` CLI 认证失败后清空共享凭据库,把用户交互会话登出(#55878):

`tools/environments/local.py:324-333 @ 863e313`:
```python
    # CLAUDE_CODE_OAUTH_TOKEN is deliberately NOT stripped.  It is set and
    # owned by the user's Claude Code install (subscription OAuth), not a
    # Hermes-managed inference credential — Claude subscription auth is not a
    # working Hermes provider path.  Stripping it broke agent-spawned
    # ``claude`` CLIs: the child fell through to the shared macOS Keychain /
    # ``~/.claude/.credentials.json`` store and, on auth failure, cleared it,
    # logging the user out of their interactive Claude sessions (#55878).
    # It arrives via the registry loop above (anthropic api_key_env_vars),
    # so remove it explicitly.
    blocked.discard("CLAUDE_CODE_OAUTH_TOKEN")
```

(b) 动态模式谓词 `_is_hermes_internal_secret`:`AUXILIARY_<TASK>_API_KEY/_BASE_URL`(运行期注入的副 LLM 凭据)与 `GATEWAY_RELAY_*_SECRET/_KEY/_TOKEN`,静态注册表不可能列举,故用模式匹配,且**无条件剥离**、passthrough 也救不回(tools/environments/local.py:352-394)。

(c) Tier-1 `_ALWAYS_STRIP_KEYS`:gateway bot token、GitHub auth、远程算力密钥等,连 `inherit_credentials=True`(用户授权的 claude/codex/gemini CLI)也照剥(tools/environments/local.py:539-571);Tier-2(provider key)才受 `inherit_credentials` 控制(tools/environments/local.py:608-625)。

另有 `_HERMES_FORCE_` 前缀:extra_env 里带此前缀的 key 去前缀后**强行注入**、绕过 blocklist(但仍过动态谓词),用于 Hermes 自己要给子进程递的值(tools/environments/local.py:470-486、1282-1286)。

**跨会话身份泄漏防线 `_inject_session_context_env`。** `HERMES_SESSION_*` 有 ContextVar 与 os.environ 双写,后者 last-writer-wins 永不清除;并发多会话宿主(gateway/ACP/API/TUI)下,一个未绑定 ContextVar 的任务 spawn 出的子进程会继承**别的会话**的身份。规则:一旦本进程 engaged 过 session-context 机制,ContextVar 即权威——UNSET 就从子环境剥掉,而非继承全局:

`tools/environments/local.py:444-453 @ 863e313`:
```python
    _engaged = session_context_engaged()
    for var_name, var in _VAR_MAP.items():
        value = var.get()
        if value is not _UNSET:
            # Explicitly bound (including "") — authoritative for this task.
            env[var_name] = "" if value is None else str(value)
        elif _engaged:
            # Unset for THIS task while a concurrent host is engaged: drop any
            # inherited global so a sibling session's value can't leak in.
            env.pop(var_name, None)
```

**venv 标记剥离。** gateway 自己跑在 venv 里,`VIRTUAL_ENV`/`CONDA_PREFIX` 泄给 agent 对**其他** Python 项目跑 `uv`/`poetry` 时,会把那个项目的依赖 sync 进 Hermes 的 venv 路径,静默毁掉 gateway 环境(#23473,tools/environments/local.py:339-349)。

**PATH 手术(_make_run_env 尾部,1296-1309):** 三步:`_append_missing_sane_path_entries`(POSIX 去空项/去重 + 追加 `_SANE_PATH` + Hermes 管理的 node/uv 目录,追加不前置——用户自己 PATH 上的工具优先,tools/environments/local.py:1171-1224)→ `_prepend_git_bash_dirs`(Windows,见 1.5)→ `_prepend_hermes_bin_dir`(systemd/cron 启动的 gateway 缺 `~/.local/bin` 等,导致插件 shell out 裸 `hermes` 报 127,tools/environments/local.py:1069-1140)。

### 1.5 Windows:没有子类,是"同一个类 + 模块级路径代数"

**先纠正一个说法:仓库里不存在 `WindowsEnvironment` 子类**(全仓 grep 仅 local.py 定义 `LocalEnvironment`)。base.py:646 注释里说的 "the Windows subclass override" 实指 LocalEnvironment 对 `_quote_cwd_for_cd`/`_quote_shell_path` 的 override——这两个 override 本身跨平台,Windows 行为由模块级函数的 `_IS_WINDOWS` 早退实现。这是注释措辞与结构的一处小出入(见 §5)。

**路径代数四件套(全部幂等、非 Windows no-op):**
- `_msys_to_windows_path`(25-50):`/c/Users/x`、`/cygdrive/c/…`、`/mnt/c/…` → `C:\Users\x`;多段 POSIX 路径(`/home/x`)不动。用于 Python 侧(isdir、Popen cwd)。
- `_windows_to_msys_path`(93-108):反向,`C:\Users\x` → `/c/Users/x`。用于 bash 侧 `builtin cd`。
- `_bash_safe_path`(111-130):native/混合路径(`/c/Users\Alexander\…`)归一为纯正斜杠 MSYS 形,防 bash 吃 `\U`、防 MSYS 参数转换把 `C:/...` 当 Windows 路径搅出 `Directory \drivers\etc` 失败类。
- `_quote_bash_path`(133-137):`shlex.quote(_bash_safe_path(path))`。

**两个 override 的接线**(base 在 bootstrap 与 wrap 时统一走它们,所以远程后端零感知):

`tools/environments/local.py:1477-1484 @ 863e313`:
```python
    @staticmethod
    def _quote_cwd_for_cd(cwd: str) -> str:
        """Use native paths for Python, but Git Bash-friendly paths for cd."""
        return BaseEnvironment._quote_cwd_for_cd(_windows_to_msys_path(cwd))

    def _quote_shell_path(self, path: str) -> str:
        """Rewrite native/mixed Windows paths before quoting for Git Bash."""
        return _quote_bash_path(path)
```

即:**cd 目标 native→MSYS 再走 base 的 `~` 保留 quote;快照/临时文件路径先 MSYS 化再 shlex.quote。** 快照路径若保持 `C:/...` 形态,bootstrap 脚本会触发 MSYS 参数转换的 drivers\etc 失败(base.py:651-656 注释)。

**`_find_bash` 候选与探活(722-929):** 顺序 = `HERMES_GIT_BASH_PATH` → 自带 PortableGit(`%LOCALAPPDATA%\hermes\git\bin` 与 MinGit 的 `usr\bin`)→ 已知 Git-for-Windows 安装点(避开 `shutil.which` 命中 WSL bash)→ PATH。每个候选用 `_bash_starts` 探活:`--noprofile --norc` 防坏 login 误杀,且**故意跑外部程序**(`/usr/bin/true; /usr/bin/cat --version`)——builtin-only 探针测不出 Mandatory ASLR 下的 MSYS fork/spawn 失败(tools/environments/local.py:897-905、814)。全部失败时查询系统 `ForceRelocateImages` 状态,命中则抛出带逐程序 `Set-ProcessMitigation` 修复命令的定向报错(831-894)。

**非登录 fallback 的 coreutils 救援:** `bash -l` 坏掉(经典 `Directory \drivers\etc does not exist`)时 base 会转非登录 `bash -c`(base.py:567-570、726-741),但非登录 shell 不 source `/etc/profile`,`usr\bin` 里的 cat/mktemp/mv 全部失踪 → write_file 空错误、终端全 127。`_git_bash_bin_dirs` 从 bash.exe 反推 Git 根目录,按 `/etc/profile` 的顺序(mingw64 → usr/bin → bin)前置到 PATH(tools/environments/local.py:935-1005)。

**MSYS 参数转换默认关闭:** `MSYS_NO_PATHCONV=1` + `MSYS2_ARG_CONV_EXCL=*` 双设(Git-for-Windows 只认前者,MSYS2/Cygwin 只认后者),防 `/FO`、`/Create` 之类被改写成 `C:/.../git/FO` 打坏 tasklist/schtasks(#56700、#56147;tools/environments/local.py:1244-1247)。

**`get_temp_dir`(1429-1475):** Windows 用 `HERMES_HOME/cache/terminal` 且强制正斜杠——同一字符串同时喂 bash 插值与 Python `open()`,并保证无空格(`%TEMP%` 常含空格,打断未加引号的 bash 插值);Termux 无 `/tmp`,优先 POSIX 形 `TMPDIR/TMP/TEMP`,再 `/tmp`(带 W_OK|X_OK 检查),再 `tempfile.gettempdir()`。

### 1.6 快照前的 shell init 注入(login 路径专属)

`_run_bash(login=True)` 仅被 `init_session` bootstrap 使用;此时把 `terminal.shell_init_files`(或默认 `~/.profile → ~/.bash_profile → ~/.bashrc`,顺序有讲究:Debian bashrc 的交互 guard 会让非交互 source 早退,而 n/nvm 装在 profile 里)拼到脚本前面,每个文件 `[ -r f ] && . f 2>/dev/null || true` 守护,坏 rc 不毁快照(tools/environments/local.py:1351-1411、1496-1499)。非 login 调用不需要——它们 source 的就是快照。

### 1.7 cleanup

删快照 + cwd 文件,再 glob 清 `snap.tmp.*`——被打断的 mv 留下的原子写残骸(#38249;tools/environments/local.py:1670-1687)。

### 重实现要点(local 后端)

1. 进程隔离用"每命令一个新会话/进程组",杀时杀组并**等组灭**(wrapper 先死不算完);PGID 在 spawn 后立刻缓存。
2. cwd 要三道防线:构造期锚定相对路径、spawn 前 X_OK 级可用性检查 + 向上回退、命令后回写先验证再提交(验证失败回滚,下次 spawn 再救)。`isdir` 不等于"能进"。
3. 子进程 env 必须走单一工厂;blocklist 分"静态注册表派生 + 动态模式谓词 + 无条件 Tier-1",并留强制注入前缀与 passthrough 白名单两个受控逃生口。反向决定(哪些**不**剥)与正向名单同等重要,要写明理由。
4. 多会话宿主里,任何"进程全局镜像 + ContextVar"双写的身份变量,子进程 env 必须以 ContextVar 为权威,UNSET 时主动剥离而非继承。
5. Windows 支持不必子类化:模块级幂等路径转换函数 + 两个 quote hook 足够;关键是把"Python 视角路径"与"bash 视角路径"在每个交接点显式换算,并用**跑外部程序**的探针给 shell 探活。
6. PATH 修补分方向:系统兜底与自管运行时**追加**(不抢用户优先级),自身 CLI 与 shell 自带 coreutils **前置**(否则功能性缺失)。

### 配套测试清单(local.py)

`tests/tools/` 下:`test_local_env_blocklist.py`、`test_local_env_session_leak.py`(源码 433 行自引)、`test_local_env_cwd_recovery.py`、`test_local_cwd_permission_fallback.py`、`test_local_env_relative_cwd.py`、`test_local_env_windows_msys.py`、`test_local_shell_init.py`、`test_local_tempdir.py`、`test_local_interrupt_cleanup.py`、`test_local_background_child_hang.py`、`test_hermes_subprocess_env.py`、`test_build_subprocess_env.py`、`test_env_passthrough.py`、`test_skill_env_passthrough.py`、`test_base_environment.py`(共享契约)。

---

## 2. tools/browser_tool.py(5098 行)—— 浏览器主工具面

### 2.1 工具注册面:10 个 browser_* 工具

`BROWSER_TOOL_SCHEMAS`(tools/browser_tool.py:1981-2128)定义、文件尾 `registry.register` 接线(tools/browser_tool.py:5017-5098):`browser_navigate`、`browser_snapshot`、`browser_click`、`browser_type`、`browser_scroll`、`browser_back`、`browser_press`、`browser_get_images`、`browser_vision`、`browser_console`,toolset 统一为 `"browser"`。前 9 个 `check_fn=check_browser_requirements`;vision 单独用 `check_browser_vision_requirements`——浏览器可用**且**视觉后端可解析才向模型广告,否则调用期报 provider 侧密文错误(#31179):

`tools/browser_tool.py:4936-4951 @ 863e313`:
```python
def check_browser_vision_requirements() -> bool:
    """Whether ``browser_vision`` should be advertised to the model.

    Requires BOTH a working browser (``check_browser_requirements``) AND a
    resolvable vision backend. Without the vision check, the tool stays in
    the model's tool list even when no vision provider is configured, then
    fails at call time with a cryptic provider-side error like
    ``unknown variant `image_url`, expected `text``` (issue #31179).
    """
```

没有独立的 `browser_eval` 工具:JS 求值折叠在 `browser_console(expression=...)` 里(schema 2110-2127,分发 3536-3541)。

### 2.2 执行底座:spawn-per-command 驱动 agent-browser CLI

与终端后端同构:每个动作 spawn 一次 `agent-browser` CLI,常驻状态在 CLI 背后的 daemon(及 2.6 的 supervisor)。`_run_browser_command`(2440-2764)是唯一通道,关键机制:

- **后端参数二选一**:云会话 `--cdp <ws_url>`(注释警告 `--session` 与 `--cdp` 同用时后者被静默忽略,2518-2522);本地 `--session <name>`(+ `--headed` 可选,2523-2527)。engine 仅本地非 camofox 注入 `--engine`(2529-2535)。
- **每会话独立 socket 目录 + owner_pid**:`/tmp/agent-browser-<session>`,0700,并写入本进程 PID 供 orphan reaper 跨进程判属(2552-2562;`_write_owner_pid` 1687-1702)。macOS 绕过 `TMPDIR` 用 `/tmp`,因 AF_UNIX 104 字节路径上限(`_socket_safe_tmpdir` 1494-1508)。
- **凭据剥离的子环境**:`_build_browser_env` 走 local.py 的 `hermes_subprocess_env(inherit_credentials=False)` 再只回填 6 个浏览器后端 key——agent-browser 是 Node 进程,给它全量密钥环等于把每个 Hermes 秘密交给任一被攻陷的 npm 传递依赖(#29157 / GHSA-m4m8-xjp4-5rmm):

`tools/browser_tool.py:109-122 @ 863e313`:
```python
# Browser-specific tool keys passed through to the agent-browser subprocess
# AFTER credential stripping.  agent-browser is a Node process loading npm
# deps; handing it the full operator keyring (#29157 / GHSA-m4m8-xjp4-5rmm)
# means a compromised transitive dependency could read every Hermes secret
# straight out of process.env.  Strip by default, then re-add only the
# browser-backend keys the worker legitimately needs.
_BROWSER_PASSTHROUGH_KEYS: tuple[str, ...] = (
    "BROWSERBASE_API_KEY",
    "BROWSERBASE_PROJECT_ID",
    "BROWSER_USE_API_KEY",
    "FIRECRAWL_API_KEY",
    "FIRECRAWL_API_URL",
    "FIRECRAWL_BROWSER_TTL",
)
```

- **stdout/stderr 用临时文件不用 pipe**:daemon 继承 fd 后 pipe 永远不 EOF,`communicate()` 会挂满超时(2603-2611)。Windows 上额外 `STARTF_USESTDHANDLES` + `close_fds=True`,并且**不加** `CREATE_NEW_PROCESS_GROUP`——Python 3.11 Windows 上它会连锁取消 asyncio ProactorEventLoop 任务,在 CLI 主线程炸出 KeyboardInterrupt(2619-2628、2204-2217 两处成对注释)。
- **空输出即失败**:rc=0 且无输出对多数命令是坏状态(除 `close`/`record`,`_EMPTY_OK_COMMANDS` 280),2685-2687。非 JSON 输出对 screenshot 有路径抢救正则(2704-2727、`_extract_screenshot_path_from_text` 2419-2437)。
- **`_find_agent_browser`**(2294-2416):PATH → 扩展 PATH(Hermes 管理 node、Homebrew 版本化 node、Termux)→ 仓内 node_modules/.bin(Windows 必须解析到 `.cmd` shim,否则 WinError 193)→ `npx agent-browser` 兜底 → 懒安装 `ensure_dependency("browser")`。每个候选都用 `agent_browser_runnable` 验证,不信任裸 which——npm postinstall 的悬空符号链接曾把所有浏览器工具静默打死(#48521)。
- **命令超时分级**:通用 30s 可配(floor 5s,`_get_command_timeout` 298-323,写缓存先值后旗标防并发读到 `resolved=True/None`,#14331);`open` 有 60s/120s(首开)下限(264-265、338-342)。

### 2.3 后端选择:camofox / CDP override / cloud / local / lightpanda

**会话创建优先级**在 `_get_session_info`(2162-2282):CDP override > 强制本地 sidecar(`::local` key)> 云 provider > 本地。

`tools/browser_tool.py:2222-2230 @ 863e313`:
```python
    cdp_override = _get_cdp_override()
    if cdp_override and not force_local:
        session_info = _create_cdp_session(task_id, cdp_override)
    elif force_local:
        session_info = _create_local_session(task_id)
    else:
        provider = _get_cloud_provider()
        if provider is None:
            session_info = _create_local_session(task_id)
```

**Camofox 在更外层分流**:每个 `browser_*` 函数在安全检查通过后整体委托 `camofox_*`(navigate 3037-3040,snapshot 3187-3189 等)。`is_camofox_mode` = 设了 `CAMOFOX_URL` 且**无 CDP override**(env 或 config 均可压制它)——`tools/browser_camofox.py:127-131 @ 863e313`:
```python
    if os.getenv("BROWSER_CDP_URL", "").strip():
        return False
    if _config_cdp_url():
        return False
    return bool(get_camofox_url())
```

**Cloud provider 解析与 fallback**(`_get_cloud_provider` 735-837):config `browser.cloud_provider` 显式指定走插件注册表(`agent.browser_registry`,第三方 vendor 只能显式启用);显式 `local` 关闭云;未配置走历史自动探测顺序 BrowserUse → Browserbase;凭据未就绪返回 None 但**不缓存**(可自愈)。云 `create_session` 抛错时降级本地 Chromium 并打上 `fallback_from_cloud/fallback_reason/fallback_provider` 可观测标记(2242-2262);本地也失败才 RuntimeError。

**CDP override 双形态**:`_get_cdp_override_raw`(纯配置读取,无网络)供 check_fn/路由判定;`_get_cdp_override`(可能发 `/json/version` 发现请求)只许连接路径调用——否则一个指向死端点的陈旧 `browser.cdp_url` 会让每次启动的 schema 组装期阻塞 10s+(497-533 长注释)。

**Lightpanda**:`browser.engine`/`AGENT_BROWSER_ENGINE` 配置(910-955),导航快但无渲染器。`_run_browser_command` 在**所有**出口路径(超时/空/非 JSON/rc≠0/解析成功但内容可疑)判定 `_lightpanda_fallback_reason`(1010-1059:显式失败、快照 <20 字符、截图 <20KB 的 panda 占位图),命中则 `_run_chrome_fallback_command`——因为 daemon 引擎启动即锁死,同 session 传 `--engine chrome` 无效,只能开一个临时 Chrome 会话:eval 拿当前 URL(用 `_engine_override="auto"` 防递归)→ 开临时 session 导航 → 执行命令 → close + 删 socket 目录(1103-1265);结果贴 `fallback_warning` 用户可见标记(1067-1091)。`browser_vision` 对截图**预路由**到 Chrome(4240-4269)。

### 2.4 Hybrid routing:云配置下私网 URL 的本地 sidecar

`_navigation_session_key`(1369-1396)五条件全真才返回 `f"{task_id}::local"`:有云 provider、`browser.auto_local_for_private_urls`(默认 True,1277-1303)、URL 解析为私网、无 CDP override、非 camofox。判私 `_url_is_private`(1306-1366):字面 IP 直判(显式补 `172.16/12`——Python 3.10 的 `is_private` 不覆盖,bpo-40791;含 CGNAT `100.64/10`)、`localhost/.local/.lan/.internal` 短路、其余 DNS 解析后判,DNS 失败视为非私(让正常路径自然报错)。

**非导航工具靠 `_last_active_session_key` 跟班**:navigate 成功后记录 task→session_key(3114),click/snapshot 等通过 `_last_session_key`(1428-1453)复用;所有权元数据(`owner_task_id`/`session_key`,2270-2272)不匹配就丢弃绑定 fail-closed,防止点错浏览器。cleanup 对裸 task_id 会连带收割 sidecar(4540-4551),并按"谁是记录属主"精细清除绑定(4556-4564)。

### 2.5 SSRF / 安全检查接线点(url_safety 本体 R3 已学,这里只列接线)

判定开关 `_eval_ssrf_guard_active`(3598-3611)= 非本地后端 ∧ 非 sidecar key ∧ 未 `allow_private_urls`。而 `_is_local_backend`(867-903)有三个要点:CDP override **一票否决本地**(必须在 camofox 短路之前判,因 CDP 主机网络位形与终端无保证);camofox 视为本地;`TERMINAL_ENV` 是容器后端时浏览器在宿主 → 视为非本地(终端摸不到的内网浏览器摸得到)。

接线点清单(逐字块仅摘最关键两处):

1. **导入期 fail-closed**(147-158):`url_safety` 导入失败时 `_is_safe_url = lambda url: False`、`_is_always_blocked_url = lambda url: True`;对照 `website_policy` 导入失败是 fail-open(142-145)。
2. **navigate 前置四连**:URL(含 %2D 解码形)命中密钥前缀正则即拒(2956-2976,normalize 前后各查一遍);敏感 query 参数 + 云后端拒(2990-3000);**IMDS 无条件地板**;`is_safe_url` 常规闸(受三开关豁免);website policy(3029-3035)。

`tools/browser_tool.py:3011-3026 @ 863e313`:
```python
    if _is_always_blocked_url(url):
        return json.dumps({
            "success": False,
            "error": "Blocked: URL targets a cloud metadata endpoint",
        })

    if (
        not _is_local_backend()
        and not auto_local_this_nav
        and not _allow_private_urls()
        and not _is_safe_url(url)
    ):
        return json.dumps({
            "success": False,
            "error": "Blocked: URL targets a private or internal address",
        })
```
   地板(#16234)对**一切**后端生效——本地 Chromium 跑在 EC2 上照样能打宿主 IMDS 偷 IAM 凭据;常规闸则被本地后端/sidecar/显式 opt-out 豁免。
3. **navigate 后置 redirect 复查**(3082-3104):最终 URL 变了且落私网/IMDS → 先 `open about:blank` 清场再报 Blocked,防后续 snapshot 读内网内容。
4. **snapshot 前 eval 复查当前 URL**(3205-3234):堵 `browser_console` 里 `location.href=...` 导航后偷读。
5. **click/type/press 统一走 `_blocked_private_page_action`**(3504-3518;调用点 3287、3328、3485):私网页面拒收输入。探测失败 fail-open(与 snapshot/vision 一致,`_current_page_private_url` 3638-3663 docstring 言明)。
6. **console 读取前复查**(3550-3560);**back 后复查**(3435-3454,历史可能落在 preflight 没见过的地址);**get_images 后复查**(4125-4136);**vision 截图前复查**(4204-4233)。
7. **eval 双子路径**:字面 URL 预扫 `_expression_targets_private_url`(3614-3635,直接 `fetch('http://127.0.0.1/…')` 不改 location.href,后置复查看不见)+ 后置页面 URL 复查(supervisor 快路径内 3872-3883,子进程路径同构)。
8. **可选 eval 词表 denylist**(默认关):`browser.restrict_evaluate` 开启后按敏感原语**名称**拦(cookie/storage/fetch/clipboard/表单取值…),含字符串字面量解码 + 拼接反混淆(`document["coo"+"kie"]`,3758-3780);因误伤合法 DOM 提取故 opt-in,`allow_unsafe_evaluate` 可再关(3714-3736 docstring 讲清取舍)。
9. **输出层**:`_redact_browser_output` 对 snapshot/console/eval/图片列表做 force 密钥脱敏(2920-2938,"Tool output is a model boundary");type 回显走 display 脱敏(3344-3357);存盘全文快照先 force 脱敏(2790)。

### 2.6 与 browser_supervisor 的分工

browser_tool 是**无状态的 spawn-per-command 驱动层**;supervisor(R4 已读:常驻 CDP WebSocket、对话桥 recent_dialogs/pending_dialogs、frame_tree)是**可选的常驻观察/加速层**。四个接线点,全部 swallow error、non-fatal:

1. **启动**:`_get_session_info` 建好会话后 `_ensure_cdp_supervisor`(2275-2280 调用;594-639 实现)——CDP URL 来源二选一(override 或云会话的 `cdp_url`),经 `SUPERVISOR_REGISTRY.get_or_start` 幂等挂接,带 `browser.dialog_policy`/`dialog_timeout_s` 配置(558-591);失败仅意味着 snapshot 里看不到 `pending_dialogs`/`frame_tree` 字段(609-611 docstring)。本地 sidecar 无 CDP URL 跳过。
2. **snapshot 合并**(3249-3260):supervisor 存活且 active 时把其状态字典 update 进响应(同样过脱敏)。
3. **eval 快路径**(3849-3859):`supervisor.evaluate_runtime(expression)` 直接走已连的 WS 做 `Runtime.evaluate`,零子进程开销;任何失败落回 CLI 子进程路径,行为不变。
4. **停止**:`_cleanup_single_browser_session` 第一步就 `_stop_cdp_supervisor`(4569-4571)——先关自己的 WS 再拆后端端点;`cleanup_all_browsers` 收尾 `stop_all()`(4666-4671)。

### 2.7 会话生命周期:过期、闲置、孤儿收割

**Provider 权威过期**:`expires_at`(epoch 或 ISO,`Z` 归一,1572-1595)→ `_session_has_expired`(1598-1605)。`_get_session_info` 发现过期先清后建,且有并发替换 guard(别的线程可能已建好新会话,2206-2213);cleanup 对过期会话**跳过发 close**——过期 CDP URL 收不了命令,且经 `_get_session_info` 会递归续建(4600-4607)。

**闲置回收双保险**:Python 侧后台线程每 30s 扫 `_session_last_activity`,超 `BROWSER_SESSION_INACTIVITY_TIMEOUT`(默认 120s,config floor 30s,1541-1559)调 `cleanup_browser`(1659-1684、1916-1956);daemon 侧下发 `AGENT_BROWSER_IDLE_TIMEOUT_MS` 让 agent-browser 自杀(2573-2580)——即使 Python 进程被 SIGKILL,daemon 也会到点自灭。

**孤儿收割器**(atexit + 清理线程首轮 + 每次干净退出都会跑,1608-1652、1924-1928):扫 `/tmp` 下 `agent-browser-h_*`/`cdp_*`/`hermes_*` 三类 socket 目录(1816-1822),判属优先级:`<session>.owner_pid` 里的 hermes 进程还活着 → 不动(跨进程安全,两个并发 hermes 不互杀);无 owner_pid(旧版 daemon)→ 查本进程 `_active_sessions`;确认孤儿后**还要过身份验证**才 tree-kill:

`tools/browser_tool.py:1758-1786 @ 863e313`(节选):
```python
    looks_like_browser = "agent-browser" in name or "agent-browser" in cmdline
    if not looks_like_browser:
        logger.warning(
            "Refusing to reap PID %d (session %s): not an agent-browser "
            "process (name=%r)", daemon_pid, session_name, name)
        return False

    # Binding check: the live process must reference *this* socket dir.
    socket_dir_l = socket_dir.lower()
    socket_base_l = os.path.basename(socket_dir).lower()
    bound = socket_dir_l in cmdline or (
        socket_base_l and socket_base_l in cmdline)
```

理由:`.pid` 文件在世界可写、名字可预测的 /tmp 里且非我方所写——同用户攻击者可栽赃指向任意受害 PID,或 PID 复用命中无关进程;杀的又是**进程树**(`ProcessRegistry._terminate_host_pid`,1897-1907),等于任意进程 DoS(#14073)。双重验证(进程像 agent-browser + cmdline/environ 绑定本 socket 目录)fail-closed,存疑不杀。PID 存在性检查用 `gateway.status._pid_exists`——`os.kill(pid, 0)` 在 Windows 不是 no-op(bpo-14484,1849-1852)。

### 2.8 快照瘦身、vision 走法

**snapshot**:>15000 字符(与 web_tools 同预算对齐,266-271)时,带 `user_task` 走辅助 LLM 摘要 `_extract_relevant_content`(先存全文、prompt 先脱敏、回displaystyle结果再脱敏,失败退截断,2808-2872),否则 `_truncate_snapshot` 按行边界截断(2875-2917);两者都先 `_store_full_snapshot` 把 force-脱敏后的全文按内容 hash 存 `cache/web/browser-snapshot-<digest>.txt`(去重、2MB 上限、挂进远端只读 mount),截断提示直接给出 `read_file path=… offset=… limit=200` 续读命令(2909-2914)。navigate 成功后自动附带一次紧凑快照,省一轮工具调用(3146-3161)。

**vision**(4170-4472):截图存持久目录(24h 清理);主模型有原生视觉时走 fast path——截图直接以多模态 tool-result 附进上下文,模型下一轮亲看像素(4347-4373);否则送辅助 vision 模型,尺寸被拒时自动降采样重试(4424-4444);分析文本回程脱敏;**LLM 分析失败不删截图**(证据保留,4461-4470)。Lightpanda 时截图预路由 Chrome(见 2.3)。

### 重实现要点(浏览器工具面)

1. 浏览器动作层做成"无状态 CLI 驱动 + 常驻 daemon + 可选常驻观察器"三层;观察器(supervisor)必须全程 non-fatal,它只增益(对话/帧树/快速 eval),不承载正确性。
2. SSRF 防线不能只放在 navigate:redirect、history back、JS 导航、JS 直连 fetch、截图、读控制台,每个**内容出口**都要复查当前 URL;并区分"可豁免的常规闸"与"无条件的 IMDS 地板"。安全模块导入失败 fail-closed,策略模块 fail-open,方向要想清楚。
3. 会话键设计成不透明字符串(`task_id` / `task_id::local`),路由决策只在 navigate 做一次并记录"最后活跃键",非导航工具跟班 + 所有权校验 fail-closed。
4. 收割别人留下的进程前,必须证明"它是我这类进程 **且** 绑定我这个会话资源";owner-pid 活着一律不碰;杀树不杀点。
5. 子进程 I/O:daemon 会继承 pipe fd,凡是"CLI 退出但 daemon 常驻"的架构必须用临时文件收集输出;Windows 上显式控制句柄继承。
6. 一切降级(cloud→local、lightpanda→chrome)都要在结果里留可见标记(fallback_warning/元数据),静默降级 = 不可诊断。
7. 缓存写入遵守"先值后旗标"(或反向清空),防并发读到半初始化状态。

### 地图与代码出入(浏览器簇)

核对 `website/docs/user-guide/features/browser.md` 的 hybrid-routing 段(92-114 行:auto_local 默认开、关掉后需 `allow_private_urls` 才放行)与 `restrict_evaluate` 段(521 行:默认不限制、SSRF 独立于该开关)——与代码 1277-1303、3017-3026、3714-3736 一致,**无冲突**。`developer-guide/browser-supervisor.md` 被 snapshot 合并处代码直接引用(3251)。

### 配套测试清单(browser_tool.py)

`tests/tools/`:`test_browser_snapshot_ssrf.py`、`test_browser_eval_ssrf.py`、`test_browser_console_ssrf.py`、`test_browser_get_images_ssrf.py`、`test_browser_private_page_action_guard.py`、`test_browser_ssrf_local.py`、`test_browser_secret_exfil.py`、`test_browser_hybrid_routing.py`、`test_browser_cloud_fallback.py`、`test_browser_cloud_provider_cache.py`、`test_browser_use_session_expiry.py`、`test_browser_orphan_reaper.py`、`test_browser_cleanup.py`、`test_browser_cdp_override.py`、`test_browser_cdp_tool.py`、`test_browser_eval_supervisor_path.py`、`test_browser_supervisor.py`、`test_browser_supervisor_healthcheck.py`、`test_browser_lightpanda.py`、`test_browser_console.py`、`test_browser_type_redaction.py`、`test_browser_open_timeout.py`、`test_browser_command_timeout_race.py`、`test_browser_chromium_autoinstall.py`、`test_browser_chromium_check.py`、`test_browser_headed_mode.py`、`test_browser_homebrew_paths.py`、`test_browser_hardening.py`、`test_browser_content_none_guard.py`、camofox 系列 7 个(`test_browser_camofox*.py`)、`test_managed_browserbase_and_modal.py`。

---

## 3. agent/shell_hooks.py(930 行)—— 声明式 shell 钩子桥

### 3.1 定位:把 config.yaml 的 `hooks:` 块桥进既有插件 hook 管理器

不是新事件系统:解析 `hooks:` → 生成闭包 → **直接 append 进 plugin manager 的 `_hooks` 字典**,所以所有既有 `invoke_hook()` 调用点零改动即可分发到 shell 脚本。

`agent/shell_hooks.py:274-283 @ 863e313`:
```python
        with _registered_lock:
            if key in _registered:
                continue
            manager._hooks.setdefault(spec.event, []).append(_make_callback(spec))
            _registered.add(key)
            registered.append(spec)
```

**注册/发现**:两个入口都调 `register_from_config`——CLI(`hermes_cli/main.py:10833-10836 @ 863e313`,传 `accept_hooks=_accept_hooks` 即 `--accept-hooks`)与 gateway(`gateway/run.py:10972-10974 @ 863e313`,传 False,由函数内部自行解析 env/config 通道);进程内幂等靠 `(event, matcher, command)` 三元组集合(agent/shell_hooks.py:142-158),matcher 参与 key 因为同一脚本可合法地按工具分多条注册。事件名必须属于 `VALID_HOOKS`(定义在 `hermes_cli/plugins.py:135-175 @ 863e313`,含 pre/post_tool_call、pre/post_llm_call、pre_verify、on_session_*、subagent_*、transform_* 等约 20 个),拼错给 difflib "did you mean" 提示后跳过(326-340);`hooks:` 下的 `output_spill`/`outbound` 是保留子节不当事件(319-324)。matcher 仅对 pre/post_tool_call 生效,其他事件配了会警告并置 None(386-393);timeout 夹在 1..300,默认 60(138-139、395-417)。`HERMES_SAFE_MODE=1` 整体跳过注册(229-235)。

### 3.2 执行:`shell=False`,JSON over stdin/stdout

单一 spawn 点 `_spawn`(434-491):`shlex.split(os.path.expanduser(command))` + `subprocess.run(..., shell=False)`——无 shell 注入面,要管道自己写脚本(模块 docstring 16-18);stdin 喂 `_serialize_payload` 的 JSON(538-554:`hook_event_name`/`tool_name`/`tool_input`/`session_id`/`cwd`/`extra`,不可序列化值 `default=str` 字符串化而非丢弃)。每个事件的 `extra` 键表在模块 docstring 53-105 逐一列出(post_tool_call 的 result/status/duration_ms/middleware_trace,subagent_stop 的 child_summary/tool_call_history 等)。

### 3.3 执行顺序与胜负规则

Python 插件先经 `discover_and_load()` 注册,shell hook 后 append → 同一事件回调按注册序执行,**平局时插件的 block 先赢**;聚合层 first-block-wins。

`agent/shell_hooks.py:12-15 @ 863e313`:
```python
* Python plugins and shell hooks compose naturally: both flow through
  :func:`hermes_cli.plugins.invoke_hook` and its aggregators.  Python
  plugins are registered first (via ``discover_and_load()``) so their
  block decisions win ties over shell-hook blocks.
```

### 3.4 失败语义:对钩子自身 fail-open,唯一例外是"非零退出仍解析 stdout"

`_make_callback`(494-535):`error`(找不到/不可执行/解析失败)→ 记 warning 返回 None;**timeout → None**(即超时的 pre_tool_call 拦截器拦不住任何东西——想 fail-closed 的门禁不该用 shell hook 做,见 3.6);非零 exit **仍解析 stdout**,让"报错 + 同时 block"的脚本成立:

`agent/shell_hooks.py:524-531 @ 863e313`:
```python
        # Non-zero exits: log but still parse stdout so scripts that
        # signal failure via exit code can also return a block directive.
        if r["returncode"] != 0:
            logger.warning(
                "shell hook exited %d (event=%s command=%s); stderr=%s",
                r["returncode"], spec.event, spec.command, stderr[:400],
            )
        return _parse_response(spec.event, r["stdout"])
```

`_parse_response`(568-622)是双 wire-format 归一点:pre_tool_call 接受 Claude-Code 形 `{"decision":"block","reason":…}` 与 Hermes 形 `{"action":"block","message":…}`,统一翻译成后者(docstring 自称"本模块最重要的正确性不变量",573-577);pre_verify 里 `continue`(Hermes)与 `block`(Claude-Code Stop 语义:block the stop = 继续跑)同义,无 message 即 no-op(607-616);pre_llm_call 透传 `{"context": …}`;其余一律 None。非 JSON stdout → warning + None。

### 3.5 Consent(同意)机制

首次遇到未允列的 `(event, command)` 对才询问;allowlist 持久在 `~/.hermes/shell-hooks-allowlist.json`。三个免提示通道任一即自动记录批准(优先级:显式参数/`--accept-hooks` > `HERMES_ACCEPT_HOOKS` env > config `hooks_auto_accept`,836-856);否则**必须有 TTY**,非 TTY 直接拒注册(fail-closed 到"不装",不是"装了再说"):

`agent/shell_hooks.py:730-748 @ 863e313`(节选):
```python
    if accept_hooks:
        _record_approval(event, command)
        ...
        return True

    if not sys.stdin.isatty():
        return False

    print(
        f"\n⚠ Hermes is about to register a shell hook that will run a\n"
        f"  command on your behalf.\n\n"
        f"    Event:   {event}\n"
        f"    Command: {command}\n\n"
        f"  Commands run with your full user credentials.  Only approve\n"
        f"  commands you trust."
    )
```

写侧并发:进程内 mkstemp+`atomic_replace` 原子写(648-677),跨进程 `.lock` 侧文件 `fcntl.flock` 串行化读改写(690-721,注释点名 Codex 用 20-50 并发写者复现过丢更新;非 POSIX 退化为进程内锁)。批准记录带 `approved_at` 与**批准时刻的脚本 mtime**(762-777),供 `hermes hooks doctor` 做漂移检测(脚本批准后被改过);`revoke` 只清 allowlist,进程内已注册回调要重启才掉(784-798)。配套自省面:`iter_configured_hooks`(288-293)、`run_once`(913-930,刻意复用 `_serialize_payload`,保证 `hermes hooks test` 的合成 stdin 与生产逐字节一致)、`script_is_executable`(890-910,裸调用查 X_OK,解释器前缀只查 R_OK,镜像 `_spawn` 真实行为)。

TTY prompt 放在锁外执行(阻塞 input 不 park 其他线程),突破 prompt 后重取锁再做幂等复查(250-279 注释 + 结构)。

### 3.6 与审批层(approval)的分工

shell hook 是**审批之前的纯自动策略闸**:它只能产出 block/context/continue,进 plugins 聚合;它自身 fail-open。真正 fail-closed 的人审升级(`approve` 指令 → `tools.approval.request_tool_approval`,gate 出错/拒绝/超时一律 block)集中在 `hermes_cli/plugins.py` 的 `resolve_pre_tool_block`:

`hermes_cli/plugins.py:2270-2274 @ 863e313`:
```python
    Centralizing this keeps the security-critical fail-closed logic in ONE
    place instead of copy-pasted across the concurrent/sequential/helper
    dispatch paths: an ``approve`` directive whose gate errors, denies, or
    times out is fail-closed to a block; ``block`` blocks with its message;
    anything else proceeds.
```

反向:审批系统的观察 hook 是 observer-only,不能 veto 审批(hooks.md:1103 与代码一致)。分层结论:**shell hook = 用户自动化策略(fail-open,损失的是策略不是安全底线);plugins 聚合层 = 指令裁决(first block wins);approval 层 = 人/智能审的安全闸(fail-closed)。**

### 重实现要点(shell 钩子)

1. 外挂钩子桥进既有内部 hook 总线,而不是另起事件系统——调用点零改动,插件与脚本天然可比较、可组合,平局规则由注册顺序显式决定。
2. 执行外部命令一律 `shell=False` + shlex;协议走 stdin/stdout JSON;兼容外来 wire 格式(Claude-Code)时在**单一入口**做归一翻译,并把这条翻译当成不变量测试。
3. 失败语义要按层分配:用户自动化 fail-open(坏脚本不许拖垮 agent),安全升级 fail-closed 且**集中一处**;"非零退出仍解析 stdout"这种细节让脚本可同时报错与表态。
4. 任意命令执行必须过首用同意:allowlist 持久化 + 原子写 + 跨进程文件锁;记录批准时刻的脚本 mtime 供漂移审计;非 TTY 无显式 opt-in 就拒装。
5. 测试助手(`run_once`)必须复用生产序列化路径,否则测试与生产静默分叉。

### 配套测试清单(shell_hooks.py)

`tests/agent/test_shell_hooks.py`、`tests/agent/test_shell_hooks_consent.py`、`tests/agent/test_verify_hooks.py`(pre_verify 语义)、`tests/agent/test_subagent_stop_hook.py`、`tests/hermes_cli/test_hooks_cli.py`(hooks list/test/doctor 面)。

---

## 4. tools/desktop_ui.py(40 行)—— 桌面渲染器事件桥

全部机制一句话:**一个可选安装的 `(sid, event, payload)` 回调槽**。桌面版 `tui_gateway` 会话启动时 `set_emitter` 装入(`tui_gateway/server.py:9330-9334 @ 863e313`:`desktop_ui.set_emitter(lambda sid, event, payload: _emit(event, sid, payload))`);其他运行形态槽位保持 None,`available()` 为 False,桌面专属工具(`tools/open_preview_tool.py:46`、`tools/focus_pane_tool.py:26`、`tools/react_to_message_tool.py:80` 均为调用方)据此回答 "desktop only"。事件路由键取会话环境的 `HERMES_UI_SESSION_ID`,保证事件落到**拥有当前回合的那扇窗口**;线程安全靠底层 `write_json` 的 `_stdout_lock`(docstring 声明,本文件自身无锁):

`tools/desktop_ui.py:32-40 @ 863e313`:
```python
def emit(event: str, payload: dict) -> bool:
    """Route ``event`` to the window that owns the current turn.

    Returns ``False`` when no emitter is wired (i.e. not the desktop app)."""
    fn = _emit
    if fn is None:
        return False
    fn(get_session_env("HERMES_UI_SESSION_ID", ""), event, payload)
    return True
```

`fn = _emit` 先取局部再判空,避免 set_emitter(None) 并发竞态。重实现要点:桌面/无头能力分叉用"进程级可空 emitter + 布尔探询"最小化耦合,工具层不 import 任何渲染器代码,路由身份从会话上下文取而非参数传递。测试:`tests/tools/test_desktop_ui.py`(另 `test_open_preview_tool.py`、`test_focus_pane_tool.py` 覆盖调用方)。

---

## 5. 与文档/既有认知的出入

1. **▲ "Windows 子类"不存在**。base.py:645-647 注释写 "the Windows subclass override converts a native ``C:\Users\x`` cwd"(`tools/environments/base.py:645-647 @ 863e313`),但全仓没有 Windows 专用 Environment 子类;所指实为 `LocalEnvironment._quote_cwd_for_cd`/`_quote_shell_path` 这两个跨平台 override(tools/environments/local.py:1477-1484)+ 模块级 `_IS_WINDOWS` 守卫函数。代码注释措辞与实际结构不符(功能无碍),本轮任务描述沿用了该措辞,一并修正认知。
2. **◇ local.py 类 docstring 的 "CWD persists via file-based read" 已过时**(tools/environments/local.py:1419)。现行实现与远程后端共享 stdout marker 解析,`_update_cwd` 自己的 docstring 说明了这一点并保留 `_cwd_file` 仅作 cleanup 遗产(tools/environments/local.py:1635-1644、1670-1676)。
3. **website/docs 本簇核对无冲突**:`user-guide/features/hooks.md`(consent 三通道、timeout 1..300 clamp、双 wire shape、"errors never crash the agent"、approval 观察 hook observer-only)与 `agent/shell_hooks.py` 逐条一致;`user-guide/features/browser.md`(auto_local_for_private_urls 默认开、关闭后需 allow_private_urls、restrict_evaluate 默认关且独立于 SSRF)与 `tools/browser_tool.py` 一致。R1/R3 已录的"文档为作者自绘地图"原则本轮未新增冲突条目。

---

## 台账处置建议(供合并本轮时执行)

`tools/environments/local.py`、`tools/browser_tool.py`、`agent/shell_hooks.py`、`tools/desktop_ui.py` 四行:layer 保持 L1,status 由 `R4-structure` 更新为 `R5-deep-read`;上列各测试文件维持 LT 不变。