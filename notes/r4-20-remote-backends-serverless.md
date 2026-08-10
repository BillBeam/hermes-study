# R4-20 远端执行后端 + serverless 持久化(子代理底稿)

> 由子代理精读产出,主线抽查关键行号与定案(a serverless 持久化、b seven backends)。基线 863e31318。
> 范围:ssh(375)、modal(478)、managed_modal(282)、modal_utils(210)、daytona(270)、
> vercel_sandbox(662)、singularity(268)、file_sync(484)。

All evidence gathered. Here is the complete L1 deep-read draft.

---

# R4 底稿 · 远端执行后端 + serverless 持久化机制簇

> 学习对象:NousResearch/hermes-agent @ `863e31318553cda8ad61df681d08175364d4164b`
> 溯源约定:凡对行为的断言,紧跟 `路径:行号 @ 863e313` + 逐字代码摘录。行号以基线 commit 为准。
> 本底稿求全求证,面向"要凭它重实现同等机制"的读者;可读性成品章另出。

## 0. 覆盖清单与实测行数

`wc -l` 实测(与任务给定行数一致):

| 文件 | 实测行数 | 角色 |
|---|---|---|
| `tools/environments/ssh.py` | 375 | 真 subprocess 型远端后端 + tar-over-SSH 批量传输 |
| `tools/environments/modal.py` | 478 | SDK exec 型;文件系统快照持久化(direct) |
| `tools/environments/managed_modal.py` | 282 | 网关代管 Modal,完全另起 execute() |
| `tools/environments/modal_utils.py` | 210 | 代管 Modal 的共享执行流基类 |
| `tools/environments/daytona.py` | 270 | SDK exec 型;stop-resume 持久化 |
| `tools/environments/vercel_sandbox.py` | 662 | SDK exec 型;snapshot 持久化 + 健康自愈 |
| `tools/environments/singularity.py` | 268 | 真 subprocess 型;overlay 目录持久化(本地) |
| `tools/environments/file_sync.py` | 484 | 事务性双向文件同步 |

契约来源(主线,本底稿只引用不精读):`tools/environments/base.py`(1371 行)。

**契约三条**(重实现时必须复刻):
1. 子类实现 `_run_bash(cmd_string, *, login, timeout, stdin_data) -> ProcessHandle` 与 `cleanup()`(`base.py:576-594`)。
2. `init_session()` 用 login bash 跑一段 bootstrap,把 `export -p` / `declare -f` / `alias -p` 的会话状态 dump 到远端一个快照文件,后续每条命令 `source` 它来重放会话(`base.py:634-709`)。
3. CWD 不落地文件,靠 stdout 里内嵌的 `__HERMES_CWD_{session}__<path>__HERMES_CWD_{session}__` 标记回传,`_extract_cwd_from_output` 解析后从输出里剥掉(`base.py:1238-1270`)。

关键:base 的 `_run_bash` 只要求返回一个满足 `ProcessHandle` **协议**(鸭子类型)的对象,不要求是真进程——这正是远端后端能分成两派的支点。

```356:365:/home/user/hermes-agent/tools/environments/base.py
class ProcessHandle(Protocol):
    """Duck type that every backend's _run_bash() must return.

    subprocess.Popen satisfies this natively.  SDK backends (Modal, Daytona)
    return _ThreadedProcessHandle which adapts their blocking calls.
    """
```

---

## 1. 机制一:两种 `_run_bash` 实现范式(真进程 vs SDK exec)

### 1.1 场景:一条 `ls` 命令在两类后端里的不同走法

同样是 `terminal("ls")`,base 的 `execute()` 最终都会调 `_run_bash(wrapped_script)` 再交给 `_wait_for_process(proc)`。`_wait_for_process` 的核心是一个 `select()` 轮询 + 后台 drain 线程,它**假定** `proc.stdout` 是一个真 OS 文件描述符,并用 `proc.poll()` 判断进程是否结束(`base.py:1002-1073, 1104`)。

- **SSH / Singularity**:`_run_bash` 真的 `subprocess.Popen(["ssh", ..., "bash", "-c", ...])`,`proc.stdout` 是真管道 fd,一切天然满足。
- **Modal(direct)/Daytona/Vercel**:它们没有本地子进程——命令是通过各自云 SDK 的**阻塞式 exec 调用**跑在远端的,返回的是 `(输出字符串, 退出码)`,不是流。要塞进 `_wait_for_process` 的轮询模型,就得把"一次阻塞调用"伪装成"一个正在跑、可 poll、可 kill、stdout 可读的进程"。这就是 `_ThreadedProcessHandle` 的职责。

### 1.2 机制:`_ThreadedProcessHandle` 把阻塞 exec 适配成 `ProcessHandle`

数据结构(`tools/environments/base.py:383-449`):内部持有一个 `threading.Event _done`、一个 `os.pipe()`、以及后台 worker 线程。

```383:417:/home/user/hermes-agent/tools/environments/base.py
    def __init__(
        self,
        exec_fn: Callable[[], tuple[str, int]],
        cancel_fn: Callable[[], None] | None = None,
    ):
        self._cancel_fn = cancel_fn
        self._done = threading.Event()
        self._returncode: int | None = None
        self._error: Exception | None = None

        # Pipe for stdout — drain thread in _wait_for_process reads the read end.
        read_fd, write_fd = os.pipe()
        self._stdout = os.fdopen(read_fd, "r", encoding="utf-8", errors="replace")
        self._write_fd = write_fd

        def _worker():
            try:
                output, exit_code = exec_fn()
                self._returncode = exit_code
                # Write output into the pipe so drain thread picks it up.
                try:
                    os.write(self._write_fd, output.encode("utf-8", errors="replace"))
                except OSError:
                    pass
            except Exception as exc:
                self._error = exc
                self._returncode = 1
            finally:
                try:
                    os.close(self._write_fd)
                except OSError:
                    pass
                self._done.set()
```

控制流关键点:
- **stdout 造一个真 fd**:worker 把阻塞 exec 的全部输出一次性 `os.write` 进管道写端,`_wait_for_process` 的 drain 线程照常 `select()`+`os.read` 读端。因为 `_stdout` 是真 `os.fdopen(read_fd)`,`_wait_for_process` 里的 `fileno()` 分支(`base.py:1012-1019`)会认它作真 fd,无需走 iterator 回退路径。worker 完成时 `os.close(write_fd)` → 读端 EOF,drain 线程自然收尾。
- **poll/wait 用 Event 桥接**:`poll()` 返回 `self._returncode if self._done.is_set() else None`(`base.py:428-429`);`wait(timeout)` 就是 `self._done.wait(timeout)`(`base.py:438-440`)。于是 base 的 `while proc.poll() is None` 轮询循环对 SDK 后端也成立。
- **kill 走 cancel_fn**:`kill()` 调用构造时传入的 `cancel_fn`(`base.py:431-436`)。每个 SDK 后端把 cancel_fn 接到自己的"终止沙箱"上——这是中断(Ctrl-C / 超时)能真正停住远端的唯一途径,因为没有本地进程可以 `SIGKILL`。

三个 SDK 后端的 `_run_bash` 都是同一模板,差别只在 exec_fn/cancel_fn:

- **Modal direct**(`tools/environments/modal.py:408-440`):exec_fn = `sandbox.exec.aio("bash","-c",cmd)` 后 `read`/`wait`;cancel = `sandbox.terminate.aio()`。注意它把 async 调用丢进独立事件循环线程 `_AsyncWorker` 跑(`tools/environments/modal.py:127-161`),`run_coroutine` 用 `future.result(timeout)` 同步等。

`tools/environments/modal.py:415-440 @ 863e313`

```python
        def cancel():
            worker.run_coroutine(sandbox.terminate.aio(), timeout=15)

        def exec_fn() -> tuple[str, int]:
            async def _do():
                args = ["bash"]
                if login:
                    args.extend(["-l", "-c", cmd_string])
                else:
                    args.extend(["-c", cmd_string])
                process = await sandbox.exec.aio(*args, timeout=timeout)
                stdout = await process.stdout.read.aio()
                stderr = await process.stderr.read.aio()
                exit_code = await process.wait.aio()
```

- **Daytona**(`tools/environments/daytona.py:226-249`):exec_fn = `sandbox.process.exec(shell_cmd, timeout=timeout)`(同步 SDK,直接返回 `.result`/`.exit_code`);cancel = `sandbox.stop()`(在 `self._lock` 内)。注意 cancel 用的是 `stop()`——中断时把整个沙箱停掉,下一条命令靠 `_ensure_sandbox_ready` 再 `start()` 回来(见 §2.3)。

```226:240:/home/user/hermes-agent/tools/environments/daytona.py
        def cancel():
            with lock:
                try:
                    sandbox.stop()
                except Exception:
                    pass

        if login:
            shell_cmd = f"bash -l -c {shlex.quote(cmd_string)}"
        else:
            shell_cmd = f"bash -c {shlex.quote(cmd_string)}"

        def exec_fn() -> tuple[str, int]:
            response = sandbox.process.exec(shell_cmd, timeout=timeout)
            return (response.result or "", response.exit_code)
```

- **Vercel**(`tools/environments/vercel_sandbox.py:597-637`):exec_fn = `sandbox.run_command("bash", ["-lc"|"-c", cmd])`;cancel = `self._stop_sandbox(sandbox)`。此处 `timeout`/`stdin_data` 显式 `del` 丢弃——SDK 无 per-exec 超时,超时靠 base 的 `_wait_for_process` 触发 cancel_fn 停沙箱(注释 `tools/environments/vercel_sandbox.py:616-626`)。

```616:635:/home/user/hermes-agent/tools/environments/vercel_sandbox.py
        del timeout
        del stdin_data
        ...
        def cancel() -> None:
            with lock:
                self._stop_sandbox(sandbox)

        def exec_fn() -> tuple[str, int]:
            result = sandbox.run_command(
                "bash",
                ["-lc" if login else "-c", cmd_string],
                cwd=workspace_root,
            )
            return _extract_result_output(result), _extract_result_returncode(result)
```

### 1.3 例外:Managed Modal 不用 `_ThreadedProcessHandle`,而是整体接管 `execute()`

代管 Modal 的沙箱由 Nous tool-gateway 拥有,命令通过 HTTP REST 起 exec、轮询状态。它的 `_wrap_command`/`_wait_for_process`/快照那一整套 base 机制**都不适用**(网关侧负责 CWD 追踪和 env 快照),所以 `BaseModalExecutionEnvironment` 直接 override `execute()`,自己写轮询循环:

```58:67:/home/user/hermes-agent/tools/environments/modal_utils.py
class BaseModalExecutionEnvironment(BaseEnvironment):
    """Execution flow for the *managed* Modal transport (gateway-owned sandbox).

    This deliberately overrides :meth:`BaseEnvironment.execute` because the
    tool-gateway handles command preparation, CWD tracking, and env-snapshot
    management on the server side.  The base class's ``_wrap_command`` /
    ``_wait_for_process`` / snapshot machinery does not apply here — the
    gateway owns that responsibility.
```

轮询循环(`tools/environments/modal_utils.py:125-155`):`_start_modal_exec` 起一个 exec 拿 handle → 循环里 `is_interrupted()` 就 `_cancel_modal_exec`、`_poll_modal_exec` 返回非 None 就结束、过 deadline 就 cancel+超时。三个抽象方法由 `ManagedModalEnvironment` 实现成 REST 调用:
- start = `POST /v1/sandboxes/{id}/execs`(`tools/environments/managed_modal.py:72-119`),同步完成的直接返回结果;
- poll = `GET .../execs/{execId}`(`tools/environments/managed_modal.py:121-146`),状态在 `{completed,failed,cancelled,timeout}` 里就返回结果;
- cancel = `POST .../execs/{execId}/cancel`(`tools/environments/managed_modal.py:248-256`)。

### 1.4 设计理由 / 取舍 / 重实现要点

- **理由**:统一的 `_wait_for_process`(带中断检查、活性心跳 `touch_activity_if_due`、超时、bounded capture、grandchild 管道防挂死)是所有后端共享的宝贵逻辑(`base.py:891-1210`)。用 `_ThreadedProcessHandle` 把 SDK 调用"降维"成进程,就能白嫖这套逻辑而不必每后端重写。
- **取舍 1(无真流式)**:SDK 后端是"跑完再一次性写管道",所以 `bounded_capture`(边流边截断防 OOM)对它们**无效**——输出已在内存里成型。Managed Modal 的注释明确承认这点(`tools/environments/modal_utils.py:89-93`)。长命令的实时输出/超大输出对 SDK 后端是隐患。
- **取舍 2(kill 粒度粗)**:本地进程能精确杀进程组;SDK 后端的 cancel 往往是"停整个沙箱"(Daytona/Vercel)或 terminate(Modal)。中断一条命令 = 掀翻沙箱,代价是下一条命令要付重启成本。
- **重实现要点**:(a) 适配器必须给 stdout 造**真 fd**(`os.pipe`),否则 select 型 drain 循环无法工作;(b) worker 线程务必在 finally 里 `close(write_fd)` + `set(done)`,否则 drain 线程/poll 循环永远不结束;(c) cancel_fn 必须幂等且吞异常(`kill()` 里 `try/except`),因为它会在超时/中断/GC 多路径被触发。

---

## 2. 机制二:Serverless 持久化(逐后端拆解"空闲休眠、按需唤醒")

README 宣称 *"Daytona and Modal offer serverless persistence — your agent's environment hibernates when idle and wakes on demand"*(`README.md:29`)。下面逐后端查实现,共有**四种不同的物理机制**。

### 2.1 Modal(direct):文件系统快照 = snapshot-on-cleanup + restore-on-launch

**场景**:agent 跑 task `alpha`,`pip install numpy` 后会话结束;明天同一 task 再开,希望 numpy 还在。

**机制**:持久化不是"空闲自动休眠",而是**cleanup 时对文件系统拍快照,下次创建时从快照 id 复活**。

- cleanup 路径(`tools/environments/modal.py:451-487`):先 `sync_manager.sync_back()`(拉回 skills/cache/credentials),再 `sandbox.snapshot_filesystem.aio()` 拿到一个 image 的 `object_id`,存进 JSON 台账,最后 `terminate` 沙箱。

```451:469:/home/user/hermes-agent/tools/environments/modal.py
        if self._persistent:
            try:
                async def _snapshot():
                    img = await self._sandbox.snapshot_filesystem.aio()
                    return img.object_id
...
                try:
                    snapshot_id = self._worker.run_coroutine(_snapshot(), timeout=60)
                except Exception:
                    snapshot_id = None
...
                if snapshot_id:
                    _store_direct_snapshot(self._task_id, snapshot_id)
                    logger.info(
                        "Modal: saved filesystem snapshot %s for task %s",
                        snapshot_id[:20], self._task_id,
                    )
```

- restore 路径(`tools/environments/modal.py:194-278`):构造时按 `task_id` 查台账拿 `snapshot_id`,`_resolve_modal_image` 把 `im-` 前缀的 id 转成 `Image.from_id`(`tools/environments/modal.py:105-106`),用它当创建沙箱的 image;若复活失败则删台账、退回 base image 重建(`tools/environments/modal.py:264-275`)。

**台账的关键设计——命名空间隔离 + legacy 迁移**(`tools/environments/modal.py:34-80`):快照 id 存在 `{HERMES_HOME}/modal_snapshots.json`,键是 `direct:<task_id>`(`_direct_snapshot_key`)。为什么要 `direct:` 前缀?因为同一 `task_id` 在 direct 与其它 Modal 传输路径下可能各自有快照,裸 `task_id` 键会串味。`_get_snapshot_restore_candidate` 先查命名空间键,回落到 legacy 裸键并标记 `restored_from_legacy_key`;复活成功后 `_store_direct_snapshot` 把它迁移到命名空间键并 `pop` 掉裸键(`tools/environments/modal.py:50-80, 277-278`)。这条迁移路径正是 `test_modal_snapshot_isolation.py` 的核心断言(见 §6)。

**取舍**:所谓 "hibernate when idle" 在 direct 模式下**并不精确**——沙箱创建时 `timeout` 默认 3600s(`tools/environments/modal.py:252`),那是**最大存活**不是空闲计时;真正的"省钱"来自 cleanup 时 terminate(不再计费)+ 下次从快照冷启。也就是说:是**会话结束即快照+销毁**,不是后台空闲探测。这是"地图"与"代码"的第一处出入(§5)。

### 2.2 Managed Modal:更接近真"空闲休眠"

代管模式把 idle 计时交给网关。创建沙箱时显式传 `idleTimeoutMs`(至少 5 分钟,或 `timeout` 秒)与 `persistentFilesystem`(`tools/environments/managed_modal.py:183-192`);cleanup 时 `POST /terminate` 带 `snapshotBeforeTerminate: persistent`(`tools/environments/managed_modal.py:188-196`)。

```186:192:/home/user/hermes-agent/tools/environments/managed_modal.py
            "timeoutMs": 3_600_000,
            "idleTimeoutMs": max(300_000, int(self.timeout * 1000)),
            "persistentFilesystem": self._persistent,
            "logicalKey": self._task_id,
```

所以 managed 才真有"服务端 idle 到点休眠"的语义,`logicalKey=task_id` 让网关按 task 复用/复活。direct 没有这层。

### 2.3 Daytona:stop-resume(整机停/启,不是快照)

**机制**:持久化靠"停/启同一个 sandbox 实体",文件系统天然随实体保留。

- resume 路径(`tools/environments/daytona.py:89-131`):persistent 时先按 `hermes-<task_id>` 名 `daytona.get(name)` 找到旧沙箱并 `start()`;找不到再按 label `list()` 找 legacy;都没有才 `create()`。
- 创建时 `auto_stop_interval=0`(`tools/environments/daytona.py:125`)——**显式关掉 Daytona 自己的空闲自动停机**。
- cleanup 路径(`tools/environments/daytona.py:261-287`):persistent 时 `sandbox.stop()`(保留文件系统),非 persistent 才 `daytona.delete()`。

```260:267:/home/user/hermes-agent/tools/environments/daytona.py
                if self._persistent:
                    self._sandbox.stop()
                    logger.info("Daytona: stopped sandbox %s (filesystem preserved)",
                                self._sandbox.id)
                else:
                    self._daytona.delete(self._sandbox)
```

- 中断自愈(`tools/environments/daytona.py:206-217`):因为中断的 cancel_fn 会 `stop()` 沙箱,所以每条命令前 `_before_execute` → `_ensure_sandbox_ready`:`refresh_data()` 后若状态是 STOPPED/ARCHIVED 就 `start()`。

**取舍**:`auto_stop_interval=0` 意味着"空闲休眠"并非 Daytona 平台自动做的,而是 **Hermes 在 cleanup 里主动 stop**。README 的"hibernates when idle"在 Daytona 上同样是"会话结束即停",不是后台 idle 计时(§5 第二处出入)。好处是 stop-resume 比快照更保真(连 `/root` 下非同步文件也在),坏处是停机前那一刻的活进程/PID 不保留。

### 2.4 Vercel:snapshot 持久化 + 沙箱健康自愈

**机制**:与 Modal direct 同构——cleanup 拍 `sandbox.snapshot()` 存 id,创建时 `source={"type":"snapshot","snapshot_id":...}` 复活(`tools/environments/vercel_sandbox.py:306-342, 448-475`)。台账 `{HERMES_HOME}/vercel_sandbox_snapshots.json`,键是裸 `task_id`(`tools/environments/vercel_sandbox.py:76, 175-200`)。复活失败则 `_delete_snapshot` 剪枝 + 退回全新沙箱(`tools/environments/vercel_sandbox.py:323-331`)。

`tools/environments/vercel_sandbox.py:448-469 @ 863e313`

```python
    def _snapshot_sandbox(self, sandbox: Sandbox) -> str | None:
        if not self._persistent or not self._task_id:
            return None
        try:
            snapshot = sandbox.snapshot()
        except Exception as exc:
            logger.warning(
                "Vercel: filesystem snapshot failed for task %s: %s",
                self._task_id,
                exc,
            )
            return None
...
        snapshot_id = _extract_snapshot_id(snapshot)
...
        _store_snapshot(self._task_id, snapshot_id)
```

Vercel 独有两块工程化:
- **瞬时错误重试**:`_retry_vercel_call` 对创建/写文件包了 3 次指数退避,`_is_transient_vercel_error` 顺着异常链认 `{408,425,429,500,502,503,504}` 与 httpx 网络错(`tools/environments/vercel_sandbox.py:66-135, 306-342`)。
- **每命令前健康检查 + 重建**:`_ensure_sandbox_ready`(`tools/environments/vercel_sandbox.py:477-511`)`refresh()`,若进入 terminal 态(ABORTED/FAILED/STOPPED)就关旧客户端、`_create_sandbox` 重建、重新 `_configure_attached_sandbox`,再 `_wait_for_running`。这让"沙箱被平台回收"对 agent 透明。

**注意**:README 只点名 Daytona 和 Modal,但 Vercel **同样**提供 snapshot 持久化(`features/tools.md:68, 148` 也这么写)。README 漏了 Vercel(§5)。

### 2.5 Singularity:writable overlay 目录(本地持久化,非 serverless)

**机制**:持久化靠给 Apptainer 实例挂一个**可写 overlay 目录**,该目录在宿主 scratch 下按 task_id 命名,实例停了目录还在。

- 启动(`tools/environments/singularity.py:204-227`):persistent 且有 overlay 时 `--overlay <dir>`,否则 `--writable-tmpfs`(临时、不留)。

```204:207:/home/user/hermes-agent/tools/environments/singularity.py
        if self._persistent and self._overlay_dir:
            cmd.extend(["--overlay", str(self._overlay_dir)])
        else:
            cmd.append("--writable-tmpfs")
```

- overlay 目录预建(`tools/environments/singularity.py:191-195`):`{scratch}/hermes-overlays/overlay-<task_id>`。
- cleanup(`tools/environments/singularity.py:251-268`):`instance stop`;persistent 时把 overlay 路径记进 `singularity_snapshots.json`(纯记账,目录本身就地保留)。

**定位**:Singularity 是"绑定挂载/本地文件系统直接可见"类后端,`file_sync` 用不上(`base.py:1276-1284` 注释、`tools/environments/file_sync.py:5-7`),持久化完全靠本地 overlay。它不是 serverless,但 overlay 机制回答了任务问的"Singularity overlay 目录怎么实现空闲休眠、按需唤醒":停实例=休眠、`--overlay` 同目录再起=唤醒,状态在 overlay 的 upper 层。

### 2.6 五后端持久化对照表

| 后端 | 物理机制 | 台账文件 | 键 | "唤醒"触发点 | 真 idle 计时? |
|---|---|---|---|---|---|
| Modal direct | filesystem snapshot | `modal_snapshots.json` | `direct:<task>` | 下次 create 用 `Image.from_id` | 否(cleanup 拍照) |
| Modal managed | gateway 快照 | 网关侧 | `logicalKey=task` | 网关按 key 复活 | **是**(`idleTimeoutMs`) |
| Daytona | stop / start 同实体 | 无(靠 name/label) | `hermes-<task>` | 下次 `get()+start()` | 否(`auto_stop_interval=0`,cleanup stop) |
| Vercel | snapshot | `vercel_sandbox_snapshots.json` | `<task>` | create 用 `source=snapshot` | 否(cleanup 拍照) |
| Singularity | writable overlay 目录 | `singularity_snapshots.json`(仅记账) | `<task>` | 同 overlay 再 `instance start` | 否(本地) |

---

## 3. 机制三:FileSyncManager 事务性双向文件同步

### 3.1 场景:credentials/skills/cache 如何进出远端沙箱

远端后端里,宿主机上的 `~/.hermes/{credentials,skills,cache}` 与沙箱内不是同一个文件系统。agent 在沙箱里可能新增/改写 skill,退出前得把改动拉回宿主;开工时又得把宿主的凭据推上去。`FileSyncManager` 就是这套双向同步的**后端无关引擎**——各后端只注入传输回调(`tools/environments/file_sync.py:134-164`)。

### 3.2 正向 sync:mtime/size 变更检测 + 事务回滚 + 限速

`iter_sync_files(container_base)` 把 credentials/skills/cache 拍平成 `[(host_path, remote_path)]`,并把硬编码的 `/root/.hermes` 重映射到各后端真实 home(`tools/environments/file_sync.py:53-79`)——这是 Daytona 用 `/home/daytona`、Vercel 用 `$HOME` 时路径能对上的关键。

`_sync_transaction`(`tools/environments/file_sync.py:178-250`)一个周期:
1. **限速**:非 force 且距上次 < `sync_interval`(5s)直接返回(`tools/environments/file_sync.py:180-183`)。SSH/Modal/Daytona/Vercel 的 `_before_execute` 每条命令都调 `sync()`,靠这层限速避免每命令都传全量。
2. **算 diff**:对每个文件用 `_file_mtime_key = (mtime, size)` 比对 `_synced_files`,变了才进 `to_upload`;`_synced_files` 里有、当前集合没有的进 `to_delete`(`tools/environments/file_sync.py:190-202`)。
3. **事务性**:先快照 `prev_files/prev_hashes`,执行 bulk_upload(有则用批量,否则逐个)+ delete;**全部成功**才提交(算 sha256 写 `_pushed_hashes`、更新 `_synced_files`、推进限速时钟);任一步抛异常就回滚 state 且**故意不推进时钟**,好让下一周期立刻重试(`tools/environments/file_sync.py:241-274`)。

```241:250:/home/user/hermes-agent/tools/environments/file_sync.py
        except Exception as exc:
            self._synced_files = prev_files
            self._pushed_hashes = prev_hashes
            # Do NOT advance _last_sync_time here: a failed cycle rolls state
            # back so the next cycle can retry. Bumping the rate-limit clock on
            # failure would make the next non-forced sync() return early (the
            # guard above), suppressing that retry for up to _sync_interval and
            # leaving the remote with stale files — contradicting this method's
...
            logger.warning("file_sync: sync failed, rolled back state: %s", exc)
```

### 3.3 反向 sync_back:tar 下载 → sha256 diff → last-write-wins,外加四层护栏

cleanup 时各后端调 `sync_back()`(`tools/environments/file_sync.py:256-267` → `_sync_back_transaction`)。核心 `_sync_back_impl`(`tools/environments/file_sync.py:353-443`):
1. bulk_download 把远端 `.hermes/` 打成 tar 下载,`extractall(staging, filter="data")`(防路径穿越,`tools/environments/file_sync.py:380-382`)。
2. 遍历解出的每个文件,用 `_pushed_hashes` 判断:与推上去时的 hash 相同则跳过(未改);不同或本来就没推过(远端新建)才考虑落地。
3. host 路径解析:已知映射走 `_resolve_host_path`,远端新建文件走 `_infer_host_path`——用"某个已知 remote 目录前缀 → host 目录前缀"的替换推断落点(`tools/environments/file_sync.py:454-476`)。
4. **冲突处理 last-write-wins**:若 host 侧 push 后也被改过(host_hash≠pushed_hash)且远端也变了,记 WARNING 后仍用远端版覆盖(`tools/environments/file_sync.py:426-437`)。

四层护栏:
- **凭据 upload-only**:`_credential_host_paths()` 收集的凭据文件在 sync_back 里被跳过(`tools/environments/file_sync.py:82-102, 385-424`)——凭据只上不下,防止沙箱侧污染宿主凭据。
- **SIGINT 延迟**:主线程上跑时把 SIGINT handler 换成"记下待办",同步完再恢复并用 `signal.raise_signal` 补投(`tools/environments/file_sync.py:301-334`);worker 线程上跳过(signal 只能主线程设)。目的:别让 Ctrl-C 打断到一半留下半同步状态。
- **flock 串行化**:`fcntl.flock(LOCK_EX)` 序列化并发网关沙箱的 sync_back;Windows 无 fcntl 则跳过(`tools/environments/file_sync.py:336-351`)。
- **尺寸上限**:tar 超 2GiB 拒绝解压(`tools/environments/file_sync.py:131, 369-378`),防恶意/失控沙箱撑爆磁盘。
- **重试**:3 次 `(2,4,8)s` 退避,全失败只记 WARNING 不抛(`tools/environments/file_sync.py:129-130, 284-299`)——cleanup 不该因同步失败而崩。
- **空推送短路**:从未成功推过(`_pushed_hashes` 和 `_synced_files` 皆空)就跳过 sync_back,避免对未初始化远端发起重试风暴(`tools/environments/file_sync.py:277-279`)。

### 3.4 各后端注入的传输回调(同一引擎、五种传输)

| 后端 | bulk_upload | bulk_download | 传输要点 |
|---|---|---|---|
| SSH | `tar c` 本地 → SSH 管道 → 远端 `tar x`(`tools/environments/ssh.py:188-301`) | `ssh ... tar cf -`(`tools/environments/ssh.py:303-319`) | 单 TCP 流;symlink staging 规避 `--transform`;`--no-overwrite-dir` 防坏 sshd StrictModes |
| Modal direct | 内存 `tar.gz` → base64 → stdin 分块喂 `base64 -d | tar xzf -`(`tools/environments/modal.py:325-367`) | `tar cf - -C / root/.hermes`(`tools/environments/modal.py:369-388`) | 绕开 SDK 64KB exec-arg 限;1MB 分块喂 stdin |
| Daytona | `sandbox.fs.upload_files()` 一次 multipart(`tools/environments/daytona.py:160-180`) | 远端打 tar + `fs.download_file`(`tools/environments/daytona.py:182-196`) | 580 文件从 ~5min → <2s;PID 后缀防并发撞名 |
| Vercel | `sandbox.write_files()`(`tools/environments/vercel_sandbox.py:516-535`) | 远端 tar + `download_file`(`tools/environments/vercel_sandbox.py:554-589`) | 包 3 次瞬时重试 |
| SSH/Modal/Daytona/Vercel 共用 | `iter_sync_files` / `quoted_mkdir_command` / `quoted_rm_command` / `unique_parent_dirs`(`tools/environments/file_sync.py:53-118`) | | 路径全 `shlex.quote`,批量 mkdir/rm 减往返 |

**重实现要点**:同步引擎与传输解耦(回调注入),diff 用 (mtime,size) 快判、sha256 精判,事务性 = 全成才提交 + 失败不推进限速钟;sync_back 必须处理凭据单向、并发串行、信号延迟、尺寸/重试护栏——这些都是被真事故打磨出来的(见测试 §6)。

---

## 4. 机制四:iron-proxy egress 强制 —— 负面发现(本簇不涉及)

任务问"iron-proxy egress 强制(如相关)"。**实测:与本簇远端后端无关**。

- egress 凭据注入防火墙(iron-proxy)只在 **Docker** 后端被接线:`_egress_proxy_args_for_docker()` 构造 `HTTPS_PROXY`/CA-bundle/token 三元组注入容器(`tools/environments/docker.py:393-531`,`DockerEnvironment.__init__` 处 1070-1215 合并)。
- egress 内部文档也只列 `tools/environments/docker.py` 作为后端接入点,SSH/Modal/Daytona/Vercel/Singularity **均未出现**(`website/docs/developer-guide/egress-internals.md:12` 起的模块清单)。
- 对本簇 7 文件 grep `iron|egress|HTTPS_PROXY|proxy` **零命中**(仅 Vercel 关掉自身遥测 `VERCEL_TELEMETRY_DISABLED`,`tools/environments/vercel_sandbox.py:47-56`,与 egress 无关)。

**结论(记入学习产出)**:iron-proxy 的出口凭据隔离目前**仅 Docker 后端**享有;远端后端(SSH/Modal/Daytona/Vercel)与 Singularity 的出口流量**不经 iron-proxy 强制**。若安全模型依赖 egress 隔离,选远端后端时这是一个覆盖缺口。重实现同级 harness 时应意识到:egress 强制与执行后端是正交维度,需各后端单独接线,不能假设"选了远端就有出口管控"。

---

## 5. 定案任务:结论(证实 / 证伪 / 修正)

### 定案 a) ◇ Serverless 持久化 —— docs 讲了多少 vs 代码实现

**结论:证实其存在,修正其表述。** 四种机制代码都真实存在(§2),但 docs 的覆盖与措辞与代码有出入:

| 断言(地图) | 代码(领土) | 判定 |
|---|---|---|
| README:"Daytona and Modal … hibernates when idle"(`README.md:29`) | Modal direct 是 **cleanup 拍快照 + 销毁**,沙箱 `timeout=3600` 是最大存活非空闲计时(`tools/environments/modal.py:252,451-469`);Daytona `auto_stop_interval=0` 显式关掉平台 idle 自动停,靠 cleanup `stop()`(`tools/environments/daytona.py:125,262`) | **修正**:direct/Daytona 无"后台空闲探测",是"会话结束即休眠"。只有 **managed Modal** 有真 `idleTimeoutMs`(`tools/environments/managed_modal.py:189`) |
| `features/tools.md:148`:Vercel "snapshot preserve filesystem … not preserve live processes/PID" | 完全吻合:`snapshot()`+`source=snapshot`,重建换沙箱身份(`tools/environments/vercel_sandbox.py:448-511`) | **证实**,且此处 docs 比 README 精确 |
| docs 是否讲 Modal 文件系统快照细节 / Daytona stop-resume / Singularity overlay | `features/tools.md` 仅一句带过 Modal "Serverless, scale"、Daytona "Persistent remote dev environments";**未**解释快照 id 台账、namespace 迁移、overlay `--overlay` 等实现;Singularity overlay 持久化 docs 基本无文 | **修正/补白**:实现细节远比文档丰富,本底稿 §2 即补文档空白 |

### 定案 b) README "seven terminal backends" 与 "Daytona and Modal offer serverless persistence" 是否名副其实

**"seven terminal backends" —— 证实。** 工厂 `_create_environment` 的 `env_type` 分支恰好 7 个:`local, docker, singularity, modal, daytona, vercel_sandbox, ssh`(`tools/terminal_tool.py:1633-1760`)。managed Modal **不是**第 8 个后端,而是 `modal` 这一 env_type 下的传输子模式(`_get_modal_backend_state` 在 direct/managed 间选,`tools/terminal_tool.py:1668-1723`),故不改变"7 个"的数目。README 列的七个与代码分支一一对应。

**"Daytona and Modal offer serverless persistence" —— 证实但不完整。**
- Daytona、Modal 确有持久化(§2.1-2.3),**证实**。
- 但 **Vercel 同样提供 snapshot 持久化**(`tools/environments/vercel_sandbox.py:448-475`,`features/tools.md:68,148` 亦承认),README 只字未提 → **不完整/低估**。
- Singularity 提供 overlay 持久化(本地非 serverless),不在 README 该句范围内,不算冲突,但说明"能持久化的后端 > README 点名的两个"。
- "serverless" 一词对 Daytona 略勉强:Daytona 是长驻可停/启的 dev sandbox(stop-resume),不是 FaaS 式 serverless;但从计费角度(停机不计费)可接受该营销措辞。

**净结论**:数字准确;"serverless persistence" 名单应为 **Modal + Daytona + Vercel**(managed Modal 才是最贴合"idle 休眠"的一个),README 漏了 Vercel、且把"cleanup 触发"讲成了"idle 触发"。

---

## 6. 对应测试清单 + 三个行为规格详述

`find tests -path '*environments*' -o -name '*modal*' …` 命中本簇相关测试(实测行数):

| 测试文件 | 行数 | 覆盖 |
|---|---|---|
| `tests/tools/test_file_sync_back.py` | 459 | sync_back 全语义 |
| `tests/tools/test_file_sync.py` | 412 | 正向 sync 事务/限速/删除 |
| `tests/tools/test_file_sync_perf.py` | — | 批量传输性能路径 |
| `tests/tools/test_file_sync_sigint.py` | — | SIGINT 延迟 |
| `tests/tools/test_modal_snapshot_isolation.py` | 228 | 快照命名空间隔离 + legacy 迁移 |
| `tests/tools/test_modal_sandbox_fixes.py` | 439 | Modal 沙箱创建/exec 回归 |
| `tests/tools/test_modal_bulk_upload.py` | 161 | tar.gz/base64/stdin 分块上传 |
| `tests/tools/test_managed_modal_environment.py` | 195 | 代管 Modal REST 流程 |
| `tests/tools/test_daytona_environment.py` | 325 | Daytona stop-resume/中断/资源换算 |
| `tests/tools/test_vercel_sandbox_environment.py` | 621 | Vercel 快照/自愈/同步 |
| `tests/tools/test_ssh_environment.py` | 233 | SSH ControlMaster/命令构造 |
| `tests/tools/test_ssh_bulk_upload.py` | 267 | tar-over-SSH 批量 |
| `tests/tools/test_singularity_preflight.py` | 55 | apptainer/singularity 探测 |
| `tests/tools/test_base_environment.py` | 407 | 契约与 `_wait_for_process` |
| `tests/integration/test_modal_terminal.py` / `test_daytona_terminal.py` | — | 真云集成(需凭据) |

挑 3 个最像"行为规格"的,概述其断言(只读不跑):

#### 规格 1 — `tests/tools/test_file_sync_back.py`(反向同步的完整行为契约,459 行)

这是本簇最像规格的测试,把 sync_back 的每条语义钉成断言:
- **未改则不动**:远端 tar 内容与 pushed hash 相同 → host 文件字节不变(`test_sync_back_no_changes`, 110-130)。
- **改了则覆盖**:远端 hash 不同 → host 被远端版覆盖(`test_sync_back_applies_changed_file`, 136-154)。
- **远端新建走推断**:不在 `_pushed_hashes` 的远端新文件,靠同目录已知映射的前缀替换推断出 host 落点并写入(`test_sync_back_detects_new_remote_file`, 160-180;`_infer_host_path` 前缀匹配的正反例 335-364)。
- **冲突 last-write-wins**:host 与远端 push 后都改了 → 记 "conflict" WARNING 且远端版胜出(`test_sync_back_conflict_warns`, 186-213)。
- **护栏**:3 次退避重试(第 3 次成功,sleep 恰 2 次且实参 = `_SYNC_BACK_BACKOFF[0],[1]`,219-238)、全失败不抛只 WARNING(240-255)、`flock` 至少 LOCK_EX+LOCK_UN(310-323)、Windows fcntl=None 跳锁不崩(325-332)、主线程换 SIGINT handler / worker 线程不换(370-415)、超 `_SYNC_BACK_MAX_BYTES` 拒解压且 host 不动(421-443)。
- **hash 台账**:`sync()` 后 `_pushed_hashes` 被填,删文件后被清(258-304)。

读它即可复述 sync_back 完整规格,是重实现的验收基线。

#### 规格 2 — `tests/tools/test_modal_snapshot_isolation.py`(serverless 快照持久化的隔离/迁移契约,228 行)

用纯 stub 把 modal SDK、base、credential 全替身掉(`_install_modal_test_modules`, 54-197),不碰真云,专测**快照 id 台账**语义:
- **legacy 键迁移 + 用快照复活**(`test_modal_environment_migrates_legacy_snapshot_key_and_uses_snapshot_id`, 200-214):台账初值 `{"task-legacy":"im-legacy123"}`;构造 `ModalEnvironment(task_id="task-legacy")` 后断言:①用 `Image.from_id("im-legacy123")` 复活(`from_id_calls==["im-legacy123"]`)、②创建沙箱的 image 是该快照对象、③cleanup 后台账被迁移成命名空间键 `{"direct:task-legacy":"im-legacy123"}`(裸键被 pop)。这正是 `tools/environments/modal.py:50-80,277-278` 的迁移逻辑。
- **image 解析双路**(`test_resolve_modal_image_uses_snapshot_ids_and_registry_images`, 217-228):`im-` 前缀 → `Image.from_id`;普通 tag → `Image.from_registry` 且 setup 命令含 `ensurepip`(对应 `tools/environments/modal.py:105-124`)。

读它即懂"快照 id 如何被 key、如何隔离 direct 命名空间、如何从旧格式迁移、复活失败如何回退"。

#### 规格 3 — `tests/tools/test_daytona_environment.py`(stop-resume 生命周期契约,325 行)

用 mock Daytona SDK(含 `SandboxState` 枚举,29-45)钉死 stop-resume 语义:
- **persistent 复用**(`test_persistent_resumes_via_get`, 132-139):按 `hermes-<task>` `get()` 到旧沙箱并 `start()`,**不** `create()`——即"按需唤醒"。
- **非 persistent 不查复用**(`test_non_persistent_skips_lookup`, 142-149):不 `get`/`list`,直接 `create`。
- **cleanup 停机保盘**(`test_persistent_cleanup_stops_sandbox`, 154-159):persistent cleanup 调 `stop()` 而非 delete——即"空闲休眠"由 Hermes 主动触发(佐证 §2.3、§5 的修正)。
- **中断掀沙箱返回 130**(`test_interrupt_stops_sandbox_and_returns_130`, 231-265):中断时 cancel_fn `stop()` 沙箱、退出码 130,呼应 `_ThreadedProcessHandle.kill → cancel_fn`。
- **停机后自愈**(`test_restarts_stopped_sandbox`, 288-293):下一命令前 `_ensure_sandbox_ready` 对 STOPPED 态 `start()` 回来。
- **home/cwd 解析**、**资源换算**(memory→GiB 上取整、disk 封顶 10GB)、**创建重试**等旁证(117-130, 189-231)。

读它即懂 Daytona 的"停/启同一实体"如何等价于 serverless 持久化,以及中断→停机→自愈的闭环。

---

## 7. 给重实现者的机制清单(可迁移原则)

1. **契约窄、协议松**:让后端只需返回一个 poll/kill/wait/stdout 鸭子类型,统一的等待/中断/超时/心跳逻辑只写一次;阻塞式 SDK 用"线程 worker + os.pipe 造真 fd + Event 桥接"降维成进程。
2. **中断即 cancel_fn**:无本地进程的后端,中断/超时唯一手段是掀沙箱;cancel_fn 必幂等吞异常。
3. **持久化 = 会话边界拍照/停机 + 下次按 key 复活**,别指望"idle 后台探测"除非平台(如网关)提供;台账要按传输命名空间隔离并带 legacy 迁移与"复活失败剪枝回退"。
4. **同步引擎与传输解耦**:diff 用 (mtime,size) 快判 + sha256 精判;正向全成才提交、失败不推进限速钟;反向要有凭据单向、并发 flock、信号延迟、尺寸/重试四护栏 + last-write-wins 冲突策略。
5. **egress 与后端正交**:出口管控要各后端单独接线,选远端后端不等于有出口隔离。

## 8. 延伸

- 主线契约细节(snapshot bootstrap 的 bash 3.2 兼容、`mktemp` 防并发撕裂、CWD marker 剥离、bounded capture/spill)见 `base.py:634-709, 891-1210`,属主线另精读范围。
- 工厂选择/资源换算/modal direct-vs-managed 决策见 `tools/terminal_tool.py:1460-1760`(下钻可另开一节)。
- 文档对照原文:`README.md:29`、`website/docs/user-guide/features/tools.md:58-172`、`website/docs/developer-guide/egress-internals.md`。

---

**底稿完成说明**:8 个目标文件逐一覆盖,机制组织为"两种执行范式 / 五后端持久化 / 事务同步 / egress 负面发现"四簇;定案 a、b 各给证实-修正结论;测试挑 3 个行为规格详述。所有行为断言均带 `路径:行号 @ 863e313` + 代码摘录,行号以基线 commit 实读为准。可作为对应成品章与 R12 蓝图的证据层。
