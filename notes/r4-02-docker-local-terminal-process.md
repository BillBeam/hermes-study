# R4-02 本地/Docker 后端 + 终端工具 shell 语义 + 后台进程注册表

> 底稿。基线 `863e31318`。范围:`tools/environments/docker.py`(2029)、`environments/local.py`(1687,概述)、
> `tools/terminal_tool.py`(3432)、`tools/process_registry.py`(2529)、`tools/daemon_pool.py`(64)、
> `agent/shell_hooks.py`(930,概述)、`agent/runtime_cwd.py`(100)。

## 1. Docker 后端:跨进程容器复用 + 孤儿回收(docker.py)

**问题**:agent 在 Docker 沙箱里跑命令。Hermes 进程重启(或崩溃)后,该不该保留容器?每次重建容器要
几秒 + 丢失容器内后台进程;但留着又可能堆积孤儿。

**设计**:默认 `persist_across_processes=True`(docker.py:871),三态 cleanup:
- `force_remove=True` → stop + rm(显式拆除);
- **persist 模式(默认)→ 对容器 no-op**,只丢进程内句柄让下次 __init__ 经标签重探到运行中的容器
  (docker.py:1958-1966);
- persist=False → stop + rm(每进程隔离)。

`docker.py:1953-1957 @ 863e313`:
```python
        # The persist-mode no-op is the issue-#20561 contract: the container
        # outlives Hermes processes, processes inside it stay alive, and
        # reuse on next startup is instant.
```

复用靠 **Docker 标签**:容器带 `label=hermes-agent=1` + `hermes-profile=<profile>` + task 标签,
下次启动按 `(task, profile)` 标签查到运行中的容器直接接管。标签值要清洗成 `[a-zA-Z0-9_.-]` ≤63 字符
才能过 `docker ps --filter`(`_sanitize_label_value`,docker.py:115)。

**孤儿回收**(`reap_orphan_containers`,docker.py:144):cleanup 是 atexit 钩子,但 SIGKILL/OOM/崩溃会绕过它,
留下容器永久孤儿。回收器扫 `label=hermes-agent=1` + `status=exited` + `FinishedAt` 早于 600s 的容器删除。
三条安全约束:**运行中的容器永不回收**(可能属于正在用它的兄弟 Hermes 进程,killing 会让兄弟命令崩)、
默认只扫本 profile(A profile 不拆 B 的)、只删够老的(刚退出正要被替换的不yank)(docker.py:154-164)。

**iron-proxy egress 强制**:容器按 egress 姿态打 `_egress_reuse_fingerprint` 指纹(docker.py:559, 1077),
不同 egress 策略的容器不复用。R3 提过 MITM CA 注入 + per-provider 代理 token,这里是复用键的一部分。

**★ tools.md:88 定案(R1 挂起条目)**:文档说"容器 stopped and removed on shutdown",实际默认
`persist_across_processes=True` 时 cleanup **对容器 no-op**,容器跨进程存活(容器内后台进程也活),
只在下次启动被同 (task,profile) 复用或被孤儿回收器(退出且够老)清理。**证实 R1**,以代码为准。

## 2. 本地后端 + runtime_cwd(local.py / runtime_cwd.py,概述)

`LocalEnvironment`(local.py)是真 subprocess 后端:`_run_bash` 直接 `subprocess.Popen`,用 `os.setsid`
把子进程放进自己进程组(便于整组杀)。Windows 子类覆盖 `_quote_cwd_for_cd`/`_quote_shell_path` 把
`C:\Users\x` 转成 Git-Bash 的 `/c/Users/x`(base.py 多处注释)。`agent/runtime_cwd.py`(100)是 cwd 解析
的单一入口:session cwd 记录 → 注册 override → `TERMINAL_CWD` → `os.getcwd()`(与 R3 execute_code 的 CWD
解析梯共享,#56047)。

## 3. 终端工具的 shell 语义修补(terminal_tool.py)

`terminal_tool` 在把命令交给环境前做几处 shell 语义修补,每处对应一类真实故障:

- **`A && B &` 重写**(terminal_tool.py:805-884):bash 把 `A && B &` 解析成"`&&` 紧于 `&`"——它 fork 一个
  子壳把整个 `A && B` 背景化。于是 A 也在后台跑,终端拿不到 A 的退出码。重写成 `A && { B & }` 保住 `&&` 的
  错误语义(A 前台跑、失败则不跑 B),只背景化 B。深度 0 才重写,幂等。
- **`sudo -S` 密码管道**(terminal_tool.py:1040-1053):配了 `SUDO_PASSWORD` 或有回调时,把 `sudo` 改写成
  `sudo -S`(从 stdin 读密码),密码行按 `sudo` 出现次数重复(复合命令 `sudo a && sudo b` 每个 sudo 读一行)。
  密码经 stdin 传、不进命令字符串;按 secret scope 缓存(多 profile 隔离)。
- **前台/后台引导**:工具描述(terminal_tool.py:TERMINAL_TOOL_DESCRIPTION)明确"永不用 nohup/setsid/尾部 &
  ——用 background=true 让 Hermes 跟踪进程",把后台进程管理收拢到 process_registry。

工具描述里那句"Filesystem, current working directory, and exported environment variables persist between
calls"——就是 r4-01 快照重放机制对用户/模型的呈现;但描述**没提**快照文件、原子写、函数/alias 也持久
(R3 曾记为定案,归 r4-90)。

## 4. 后台进程注册表(process_registry.py)

`background=true` 的进程交给 `ProcessRegistry` 管理。核心机制:

- **崩溃恢复靠 JSON 检查点**(process_registry.py:9):进程会话写进检查点文件,Hermes 重启后能恢复对
  在跑进程的跟踪。
- **PID-reuse 防误杀**(process_registry.py:103):`ProcessSession` 存 `host_start_time`(内核 start ticks,
  `/proc/<pid>/stat` 第 22 字段)。杀进程前比对 start time——PID 被系统回收给别的进程时 start time 不同,
  避免杀错无辜进程。
- **完成通知 notify_on_complete**(process_registry.py:120):进程退出时给 agent 排一条通知,触发新回合
  (这是 R2 讲的"后台进程通知"的实现侧)。
- **watch_patterns + strike 熔断**(process_registry.py:67-71, 236-333):监视输出匹配模式(如"Server
  started")触发通知。但一个刷屏的进程会让匹配狂发——连续 `WATCH_STRIKE_LIMIT=3` 个 strike 窗口后
  **永久禁用该会话的 watch**,降级为 notify_on_complete,并发一条"watch disabled"说明(只发一次)。
  `process_registry.py:287-289 @ 863e313`:
  ```python
                        # Promote to notify_on_complete so the agent still gets
                        # the completion signal even after watch is disabled.
                        session.notify_on_complete = True
  ```
- **本地 PTY/pipe 与沙箱内 nohup 双路径**(process_registry.py:9 附近):本地进程直接管;远端沙箱内的后台
  进程用 nohup + log/pid/exit 三文件轮询(因为远端没有真管道)。

`daemon_pool.py`(64)是一个小的 DaemonThreadPoolExecutor——R2 工具执行器用它跑并发工具(daemon 线程,
`shutdown(wait=False)` 不阻塞进程退出)。

## 5. shell_hooks(agent/shell_hooks.py,概述)

pre/post shell 命令钩子系统,让 config/插件在命令执行前后注入行为(如自动激活 venv、记录命令)。930 行,
本轮结构级理解:它是 terminal 命令的扩展点,与审批(R3)分工——审批管"能不能跑",shell_hooks 管"跑前后
做什么"。

## 6. 重实现要点

1. 容器复用用"标签 + (task,profile) 键",persist 模式 cleanup 对容器 no-op;配一个"退出且够老才删"的
   孤儿回收器兜住 SIGKILL/OOM 绕过 atexit 的情况,且永不碰运行中的容器。
2. shell 语义修补要对准具体故障:`A && B &` 的 `&&`/`&` 优先级、sudo -S 的每命令一行密码、密码走 stdin。
3. 后台进程注册表要:检查点崩溃恢复、PID-reuse 用 start_time 防误杀、watch 模式配 strike 熔断降级。

## 7. 边界与延伸

- 环境抽象基类见 r4-01;远端后端与 serverless 见 r4-20;浏览器见 r4-30;computer_use 见 r4-40。
- patch_parser 见 r4-50。
