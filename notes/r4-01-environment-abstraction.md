# R4-01 环境抽象:spawn-per-call + 会话快照重放

> 底稿(求全求证)。基线 `863e31318`。范围:`tools/environments/base.py`(1370)——所有 8 个执行后端
> 的共同契约。R2 的 execute_code 底稿引用过它,本篇给全实现。

## 0. 统一模型:spawn-per-call

`tools/environments/base.py:1-7 @ 863e313` 一句话定位整簇:
```python
"""Base class for all Hermes execution environment backends.

Unified spawn-per-call model: every command spawns a fresh ``bash -c`` process.
A session snapshot (env vars, functions, aliases) is captured once at init and
re-sourced before each command. CWD persists via in-band stdout markers (remote)
or a temp file (local).
"""
```

**问题**:7-8 种执行后端(local/docker/ssh/singularity/modal/daytona/vercel_sandbox,+managed_modal)底层
能力差异极大——有的有真 subprocess(local/docker),有的只有一次性阻塞 SDK exec(Modal/Daytona)。但 agent
需要一个"有状态 shell"的统一假象:cwd、export 的环境变量、函数、alias 都跨命令持久。而每条命令都是全新
`bash -c` 进程,进程一退所有状态就没了。

**解法**:会话快照重放。init 时一次登录 shell 把全部状态 dump 到快照文件,每条命令前 source 它、命令后
重新 dump。cwd 靠 stdout 内嵌标记回传。

## 1. 契约:子类只需实现两个方法

`BaseEnvironment(ABC)`(base.py:527)的抽象方法只有两个:
- `_run_bash(command, login, timeout)` → 返回一个 `ProcessHandle`(base.py:576);
- `cleanup()`(base.py:592)。

`ProcessHandle` 是一个 Protocol(鸭子类型接口,base.py:356-371):`poll()`/`kill()`/`wait()`/`stdout`/
`returncode`。真 subprocess 后端直接返回 `subprocess.Popen`;**只有阻塞 SDK exec 的后端**(Modal/Daytona)
用 `_ThreadedProcessHandle`(base.py:374-445)把"阻塞的 `exec_fn`"适配成这个接口——在一个 worker 线程里
跑阻塞调用,stdout 经 `os.pipe` 暴露成可 select 的流。

`tools/environments/base.py:374-381 @ 863e313`:
```python
class _ThreadedProcessHandle:
    """Adapter for SDK backends (Modal, Daytona) that have no real subprocess.

    Wraps a blocking ``exec_fn() -> (output_str, exit_code)`` in a background
    thread and exposes a ProcessHandle-compatible interface.  An optional
    ``cancel_fn`` is invoked on ``kill()`` for backend-specific cancellation
    (e.g. Modal sandbox.terminate, Daytona sandbox.stop).
    """
```

> **R11B 引用更正(片 D)**:原文此处贴的 docstring 是
> "Adapt a blocking ``exec_fn() -> (stdout_text, returncode)`` into the ``ProcessHandle``
> protocol so ``_wait_for_process`` can poll it uniformly. / SDK backends (Modal, Daytona)
> expose a single blocking exec call, not a real OS process. Running it on a worker thread
> and surfacing its output through an ``os.pipe`` lets the shared poll/drain/interrupt loop
> treat it exactly like a ``subprocess.Popen``."
> ——**这段文字在基线 863e313 全仓不存在**(`grep -rn "Adapt a blocking" --include=*.py`
> 零命中,搜索面为基线全部 `.py` 文件)。它是转述被当成逐字摘录贴了出来。
> 依据:`tools/environments/base.py:375` 起的真实 docstring 见上,已按基线原文回抄。
> **结论实质不变**——真实 docstring 说的是同一件事(把阻塞 `exec_fn` 包进后台线程、
> 暴露成 ProcessHandle 兼容接口、`cancel_fn` 挂到 `kill()`),正文第 34-36 行的叙述仍然成立。

**取舍**:所有后端共享 `_wait_for_process` / `_wrap_command` / `execute` 这些"不被覆盖"的方法,后端只填
"怎么起一个 bash"。代价是 SDK 型后端要多一层线程 + 管道适配。

## 2. 快照捕获:init_session 的原子写(base.py:634-717)

init 跑一段 bootstrap 脚本,把登录 shell 的状态 dump 到快照文件。四类状态:环境变量(`export -p` 排除
会话变量)、函数定义、alias、shell 选项。三处防绕过/防撕裂设计,每处都是一次真实事故:

- **原子写防半截读**(#38249):快照先写进 `mktemp` 的临时文件,再 `mv -f` 原子替换。因为并发的
  `source()` 调用可能读到另一条命令正在重写的快照。`tools/environments/base.py:706 @ 863e313`:
  ```python
  f"mv -f {_snap_tmp} {_quoted_snap} || rm -f {_snap_tmp}\n"
  ```
- **临时名必须每写者唯一**:为什么用 `mktemp` 而不是 `$$` 或 `$BASHPID`?`$$` 在 `&` 启动的子壳里是父壳
  PID(并发写者会撞同一个临时名);`$BASHPID` 在 macOS 的 bash 3.2 上不存在(展开成空,又撞名)。只有
  `mktemp` 跨 bash 版本可移植地给每个写者唯一路径(base.py:666-677 长注释)。
- **函数按名过滤不按行**:dump 函数时要滤掉 `_` 前缀的私有 helper(bash-completion 内部函数)。但
  `declare -f | grep -vE '^_'` 是**按行**的——它删了函数头那一行、却留下孤儿的 `{ … }` 函数体,污染
  快照让每条命令 exit 127。正确做法是先 `declare -F` 选出要保留的名字,再整体 dump(base.py:697-699)。

`_snapshot_ready = True` 后,后续命令 source 快照;失败则回退到每条命令跑 `bash -l`(base.py:717-733)。

## 3. 命令包装:_wrap_command 的六段脚本(base.py:781-875)

每条用户命令被包装成一段脚本,顺序固定:
1. **保存 passthrough 变量**(808-816):共享快照可能带上一个 profile 的值,先把当前进程环境里的
   passthrough 变量存进 shell 变量(**不进命令字符串**,防秘密从进程参数/日志泄露)。
2. **source 快照**(823-826):重放上条命令留下的 env/函数/alias;stdout 重定向到 /dev/null——因为 macOS
   bash 3.2 source 含 `declare -x` 的文件会把声明打到 stdout,泄 ~60 行环境变量进每个工具响应(#15459)。
3. **恢复 passthrough**(828-833):把第 1 步保存的当前 profile 值写回(或 unset)。
4. **cd + 执行**(837-842):`builtin cd -- <cwd> || exit 126`,然后 `eval '<escaped command>'`。
5. **重新 dump 快照**(846-862):`umask 077`(快照可能含秘密)后原子重写快照。
6. **发 CWD 标记**(870-872):`printf '\n<marker>%s<marker>\n' "$(pwd -P)"`——所有后端(含 local,#63255 起)
   都从 stdout 解析这个标记拿到新 cwd,不再需要临时文件。

`tools/environments/base.py:870-872 @ 863e313`:
```python
        parts.append(
            f"printf '\\n{self._cwd_marker}%s{self._cwd_marker}\\n' \"$(pwd -P)\""
        )
```
标记是每会话唯一的随机串(`_cwd_marker`,base.py:448),`_extract_cwd_from_output`(base.py:1238)从输出里
剥掉它并更新 `self.cwd`。

## 4. 统一等待循环:_wait_for_process(base.py:891-1230+)

所有后端共享,不被覆盖。要点:
- **非阻塞 drain(select 而非 readline)**:老写法 `for line in proc.stdout` 会阻塞到管道 EOF。用户命令
  背景化一个进程(`cmd &`、`setsid ... & disown`)时,那个孙进程继承了 stdout 管道写端,即使 bash 退了
  管道也不 EOF——drain 线程永不返回、工具挂死整个孙进程生命周期(#8340:用户 `setsid uvicorn & disown`
  重启报无限挂起)。修法:`select()` 短轮询,bash 一退就停止 drain,孙进程之后写的进孤儿管道(内核回收,
  无害)(base.py:950-965)。
- **增量 UTF-8 解码**:`os.read()` 读 4096 字节裸块,一个多字节 UTF-8 字符可能跨块;增量解码器缓冲跨块的
  半个序列,`errors="replace"` 用 U+FFFD 替换坏字节而不是砸掉整个缓冲(base.py:967-974)。
- **有界捕获 + spill**(#64435):前台终端路径 `bounded_capture=True` 只保留 `tool_output.max_bytes` 的
  头/尾窗口防 OOM,溢出 tee 到 spill 文件可恢复;内部消费者(cat 喂补丁引擎、code-execution RPC 读)用
  全保真捕获(截断会损坏数据,base.py:898-904)。
- **活动心跳**:运行中每 10s 触发 activity_callback,让 gateway 的不活动超时不杀长命令(base.py:906-908)。
- **中断兜底**:poll 循环包在 try/finally 里,`KeyboardInterrupt`/`SystemExit` 时保证 `_kill_process`——
  否则 local 后端(用 `os.setsid` 把子进程放进自己进程组)会在 python 中途关闭时留下 PPID=1 的孤儿,
  就是"`sleep 300` 活过 30 分钟"的 bug(base.py:910-915)。

## 5. stdin 两种模式(base.py:535-536, 878-889, 1290-1333)

`_stdin_mode` 默认 `"pipe"`(真 subprocess 走管道);SDK 后端(Modal/Daytona)设 `"heredoc"`,把 stdin
数据作为 shell heredoc 嵌进命令字符串(`_embed_stdin_heredoc`,base.py:882)——因为它们没有真管道。这解释了
R3 execute_code 的文件 RPC 为什么在远端要用 base64+heredoc。

## 6. 重实现要点

1. 多后端统一成"每命令一个 bash + 会话快照重放",子类只填"怎么起 bash";SDK 型后端用线程+管道适配成
   统一的 ProcessHandle。
2. 快照必须原子写(mktemp+mv)、临时名每写者唯一(不用 `$$`/`$BASHPID`)、函数按名过滤(不按行)。
3. cwd 靠 stdout 内嵌唯一标记回传,免临时文件。
4. 等待循环用 select 非阻塞 drain(防背景孙进程挂死)、增量 UTF-8 解码、中断兜底杀进程组。
5. 秘密类值(passthrough)存 shell 变量、不进命令字符串;快照文件 umask 077。

## 7. 边界与延伸

- local/docker 后端细节、terminal_tool 的 shell 语义修补、process_registry 后台进程管理见 r4-02。
- 远端后端(ssh/modal/daytona/vercel/singularity)与 serverless 持久化、file_sync 见 r4-20。
- 浏览器栈见 r4-30,computer_use 见 r4-40。
