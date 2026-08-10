# r8d · 结构级底稿:gateway 子命令、服务安装与可观测

> 层级:**L2 结构级理解**(不是逐行精读)。目标是让一个没读过本仓库的人知道
> **什么时候该来翻这些文件**、**从哪个函数进去**、**它跟谁耦合**。
> 溯源约定:凡对代码行为的断言,锚点 `路径:行号 @ 863e313` 单独成行、置于代码块之前,
> 代码块逐字摘自基线。非源码块用 ```text / ```verify 标注。
> 覆盖 30 个文件 / 22,412 行(逐文件角色表见第 7 节)。

---

## 0. 本簇在系统里的位置(速览)

这一簇是 **hermes 进程之外的一切**:怎么把 gateway 装成一个开机自启的服务、怎么找到
它、怎么停它、它出问题时怎么把现场打包寄出去、以及它安静地往本地 SQLite 里记了些什么计数。
**gateway 进程内部怎么收发消息、怎么跑 agent,全都不在这里**——那是 `gateway/` 包,
R7/R7C 已精读。

```text
             ┌──────────────────────── 用户敲的命令 ────────────────────────┐
             │  hermes gateway {run|start|stop|restart|status|install|      │
             │                  uninstall|list|setup|migrate-legacy|enroll} │
             └───────────────────────────┬─────────────────────────────────┘
                                         │  hermes_cli/subcommands/gateway.py(建 parser)
                                         ▼
                       hermes_cli/gateway.py  ← 本簇主体(7,461 行)
                       gateway_command → _gateway_command_inner 一个大分派
                                         │
        ┌────────────────┬───────────────┼───────────────┬────────────────────┐
        │                │               │               │                    │
    「装服务」       「找/停进程」    「渲染状态」    「配置平台」         「run」
   systemd/launchd   PID 扫描 +      systemctl/       gateway setup      唯一一次
   schtasks/s6       ancestor 排除   launchctl 探针     向导               交接给运行时
        │                │               │               │                    │
        ▼                ▼               ▼               ▼                    ▼
 service_manager.py  gateway.status   gateway.status  gateway.platform_  gateway/run.py
 gateway_windows.py  (读 pid 文件)    (读 runtime      registry           start_gateway()
 container_boot.py                     status)                            ← 边界在这里
        │
        └──► s6 容器:/run/service/gateway-<profile>/(tmpfs,每次重启重建)

  旁路设施(同一个 CLI 进程里的杂役):
    debug.py + diagnostics_upload.py  出事时把日志打包上传(paste.rs 公开 / Nous 私有 S3)
    logs.py                            看日志
    observability/*                    本地 SQLite 计数器 + 每日 JSON 增量包(默认关)
    pty_bridge / win_pty_bridge / pty_session   dashboard 的浏览器终端
    _subprocess_compat.py / stdio.py   Windows 兼容垫片
    uninstall.py / gui_uninstall.py / linux_desktop_entry.py   反向操作
```

---

## 1. 边界:`hermes_cli/gateway.py`(子命令)vs `gateway/`(运行时)

**一句话:`hermes_cli/gateway.py` 管的是"这个进程存不存在、该不该存在、以什么身份存在";
`gateway/` 管的是"这个进程活着的时候在干什么"。整个 7,461 行子命令代码里,真正把控制权
交出去的只有一行 `asyncio.run(...)`。**

### 1.1 交接点只有一处

`hermes_cli/gateway.py:5124-5127`

```
    success = False
    try:
        success = asyncio.run(start_gateway(replace=replace, verbosity=verbosity))
        _exit_diag("asyncio.run.returned", success=success)
```

这行之前的 5,000 多行全是**前置条件**:守卫(不能在 multiplexer 下起命名 profile、不能和
已被 systemd 监管的实例打架、不能以 root 在官方 Docker 里跑)、Windows 控制台信号吸收、
日志 verbosity 计算、以及一次"顺手把 systemd unit 刷新到最新"的自愈。

`hermes_cli/gateway.py:4984-4988`

```
    if supports_systemd_services():
        try:
            refresh_systemd_unit_if_needed(system=False)
        except Exception:
            pass  # best-effort; don't block gateway startup
```

**这个自愈是理解边界的关键**:unit 文件是子命令一侧的产物,但**只有运行时启动的时候才有
把握知道"当前这份代码期望的 unit 长什么样"**。所以作者把"重写 unit"塞进了 `run` 路径,
而不是只放在 `install`——否则一次带新 `RestartSec` 的代码升级要等到用户下次手动
`gateway start` 才生效。

### 1.2 边界的形状:一个几乎单向的依赖,且窄到只有一个模块

```verify
cd /home/user/hermes-agent
# 子命令 → 运行时:38 条 import,按模块分布
grep -cE "^[[:space:]]*from gateway\." hermes_cli/gateway.py
grep -oE "^[[:space:]]*from gateway\.[a-z_]+" hermes_cli/gateway.py | tr -d ' ' | sort | uniq -c | sort -rn
# 运行时 → 子命令:反向依赖
grep -rnE "from hermes_cli\.gateway import" --include='*.py' gateway/
```

实测(本轮):

| 方向 | 条数 | 分布 |
|---|---|---|
| `hermes_cli/gateway.py` → `gateway.*` | **38** | `gateway.status` **29**、`gateway.config` 3、`gateway.run` 2、`gateway.platforms` 2、`gateway.restart` 1、`gateway.platform_registry` 1 |
| `gateway/**` → `hermes_cli.gateway` | **1** | 仅 `gateway/run.py:10005` |

**29/38 集中在 `gateway/status.py`**,这说明边界的真实契约不是"函数调用",而是
**磁盘上的 PID 文件与 runtime status 文件**——`gateway/status.py` 是这份契约的读写库,
子命令一侧几乎只通过它认识运行时(`get_running_pid`、`read_runtime_status`、
`write_planned_stop_marker`、`looks_like_gateway_command_line`)。子命令**从不 import
gateway 的 session / delivery / platforms 主体**。

唯一的反向依赖也只是借一个命名函数:

`gateway/run.py:10005-10009`

```
                from hermes_cli.gateway import get_service_name

                service_name = get_service_name()
            except Exception:
                service_name = "hermes-gateway"
```

注意它**自带 fallback**(`except` 里硬编码 `"hermes-gateway"`),即运行时并不真的依赖
CLI 存在。**这是一条设计上刻意保持可断的边**。

### 1.3 子命令这一侧到底做了什么(按行号分区)

按 `grep -n "^def \|^class "` 的函数序划分,`hermes_cli/gateway.py` 大致是七块:

| 行区间 | 大致规模 | 干什么 |
|---|---|---|
| 1–76 | ~76 | import + **给 PATH 补 `/bin` `/usr/bin`**(UV 自带 Python 的 PATH 太瘦,找不到 `systemctl`/`launchctl`,#3849) |
| 77–1652 | ~1,580 | **进程发现与终止**:扫 PID、排除祖先进程(免得杀了自己的 shell)、排除 venv launcher stub、按 profile 归组、优雅重启(SIGUSR1)、`GatewayRuntimeSnapshot` |
| 1653–1749 | ~100 | 平台判定:`is_linux/is_macos/is_windows`、`supports_systemd_services`、WSL/容器里 systemd 是否真能用 |
| 1750–3693 | ~1,950 | **systemd 全套**:服务名/unit 路径按 profile 派生、unit 文本生成、linger、user-bus 预检、install/uninstall/start/stop/restart/status、**遗留 `hermes.service` 迁移** |
| 3694–4693 | ~1,000 | **launchd 全套**:label/plist 路径、domain 探测(`gui/<uid>` vs `user/<uid>`)、bootstrap 重试、不可用时降级为"detached 直接 spawn" |
| 4694–5365 | ~670 | **run 的守卫 + run_gateway**(交接点在此) |
| 5366–6623 | ~1,260 | **`gateway setup` 平台配置向导**:枚举平台、渲染每个平台的配置状态、逐平台交互配置(weixin 扫码、qqbot 扫码、signal 等特例) |
| 6624–7461 | ~840 | s6 分派 + `gateway_command` 总分派 + `status`/`list`/`migrate-legacy` 的输出渲染 |

**读者导航结论**:
- 想知道"为什么我的 gateway 没起来/起了两个"→ 77–1652(进程发现)+ 4694–5365(守卫)。
- 想知道"unit 文件里那行为什么长这样"→ 2837 `generate_systemd_unit` / 4053 `generate_launchd_plist`。
- 想知道"某个 IM 平台怎么配的"→ 5366–6623,并注意它调 `gateway.platform_registry`
  而不是自己维护列表(插件平台也能出现在向导里)。

---

## 2. 服务安装:一个 Protocol,四个后端,但只有一个后端真的用了这个 Protocol

### 2.1 抽象接口的形状

`hermes_cli/service_manager.py:65-83`

```
    kind: ServiceManagerKind

    # Lifecycle of a pre-declared service.
    def start(self, name: str) -> None: ...
    def stop(self, name: str) -> None: ...
    def restart(self, name: str) -> None: ...
    def is_running(self, name: str) -> bool: ...

    # Runtime registration (s6 only).
    def supports_runtime_registration(self) -> bool: ...
    def register_profile_gateway(
        self,
        profile: str,
        *,
        extra_env: dict[str, str] | None = None,
        start_now: bool = True,
    ) -> None: ...
    def unregister_profile_gateway(self, profile: str) -> None: ...
    def list_profile_gateways(self) -> list[str]: ...
```

**接口分两段,这个切分本身就是全部设计**:
- **生命周期段**(start/stop/restart/is_running)——四个后端都实现;
- **运行时注册段**(register/unregister/list)——**只有 s6 实现**,主机后端一律抛
  `NotImplementedError`,调用方必须先问 `supports_runtime_registration()`。

`hermes_cli/service_manager.py:178-191`

```
    def supports_runtime_registration(self) -> bool:
        return False

    def register_profile_gateway(
        self,
        profile: str,
        *,
        extra_env: dict[str, str] | None = None,
        start_now: bool = True,
    ) -> None:
        raise NotImplementedError(
            f"{type(self).__name__} does not support runtime profile "
            "gateway registration (container-only feature)"
        )
```

**为什么这么切**:主机上"多开一个 profile 的 gateway"意味着**写一个新的 unit / plist /
计划任务文件**,那是 `hermes gateway install` 的活儿,是**有交互、要 sudo、要问用户**的;
而容器里一切都是 tmpfs 上的目录,新建一个服务槽只是 `mkdir` + 让 s6-svscan 重扫,
**可以在 `hermes profile create` 里顺手做掉**。把两种成本完全不同的操作硬塞进同一个方法,
才会逼出"主机上悄悄写 systemd unit"这种意外。

### 2.2 后端选择

`hermes_cli/service_manager.py:86-95`

```
def detect_service_manager() -> ServiceManagerKind:
    """Detect which service manager is available in this environment.

    Returns:
        "s6" — s6-svscan is PID 1 (s6-overlay image; Docker, Podman, or a
               Fly Firecracker microVM)
        "windows" — native Windows host
        "launchd" — macOS host
        "systemd" — Linux host with a working user/system bus
        "none" — anything else (Termux, sandbox shells, etc.)
```

判定顺序是 **s6 → windows → launchd → systemd → none**。注释里记了一次真实教训:
s6 的判定**只看 `_s6_running()`(PID 1 的 comm 是 `s6-svscan` 且 `/run/s6/basedir` 存在),
不看 `is_container()`**——因为后者在 Fly 的 Firecracker microVM 上是 False,
一度让整条 s6 分派路径在 Fly 上彻底失效,`gateway start` 掉回主机路径,起了一个**和被监管
实例抢同一个 HERMES_HOME 的前台 gateway**。

### 2.3 三个主机后端是薄壳,复杂度都在别处

`hermes_cli/service_manager.py:213-216`

```
    def start(self, name: str) -> None:
        from hermes_cli.gateway import systemd_start
        systemd_start()
```

**注意 `name` 参数被丢弃了**——主机后端操作的永远是"当前 `HERMES_HOME` 对应的那个服务",
profile 是通过外层 `hermes -p <profile>` 设进环境变量的,不是通过参数传进来的。
这个签名形状是为 s6 设计的(那里每个 profile 是一个独立目录),主机侧只是"形式上对齐"。

三个后端的**服务标识符**都由同一个 `_profile_suffix()` 派生,这是"多 profile 互不冲突"的
唯一来源。systemd 侧:

`hermes_cli/gateway.py:1832-1835`

```
    suffix = _profile_suffix()
    if not suffix:
        return _SERVICE_BASE
    return f"{_SERVICE_BASE}-{suffix}"
```

launchd 侧同构:

`hermes_cli/gateway.py:3696-3697`

```
    suffix = _profile_suffix()
    return f"ai.hermes.gateway-{suffix}" if suffix else "ai.hermes.gateway"
```

于是三个主机后端的真实实现分别在:

| 后端 | 真身 | 关键产物 | 关键坑 |
|---|---|---|---|
| systemd | `hermes_cli/gateway.py` 1750–3693 | `~/.config/systemd/user/hermes-gateway[-<profile>].service` 或 `/etc/systemd/system/…` | user bus 不可达(新 SSH、无 linger)要给可执行的补救而不是 traceback;`hermes.service` 遗留单元会和新单元抢 Telegram token |
| launchd | `hermes_cli/gateway.py` 3694–4693 | `~/Library/LaunchAgents/ai.hermes.gateway[-<profile>].plist` | domain 到底是 `gui/<uid>` 还是 `user/<uid>` 只能探测;探测/bootstrap 全失败时**写一个 unsupported marker 并降级为 detached spawn** |
| Windows | `hermes_cli/gateway_windows.py`(1,696 行) | 计划任务 `Hermes_Gateway` + `.cmd`/`.vbs` 启动脚本 | schtasks 被 ACL 挡住时降级到**启动文件夹**;需要 UAC 时**先问完所有交互问题再提权**,免得提权后再弹问题 |

Windows 的降级链值得单独记(这是本簇里"取舍"最明显的一处):

`hermes_cli/gateway_windows.py:1011-1015`

```
def _install_startup_fallback(script_path: Path, start_now: bool, detail: str) -> None:
    """Install the Startup-folder fallback and optionally start once."""
    print(f"↻ Scheduled Task install blocked ({detail.splitlines()[0]}) — using Startup folder fallback")
    entry = _install_startup_entry(script_path)
    print(f"✓ Installed Windows login item: {entry}")
```

即 **计划任务(能设 30 秒登录延迟、999 次重启)→ 启动文件夹(只有"登录时跑一次",无重启
保障)→ 直接 detached spawn(连开机自启都没有)**,每退一档就少一层保障,但**永远不会
以"装不上"收场**。

### 2.4 s6 后端:唯一支持运行时注册的那个

服务槽写在 tmpfs 上:

`hermes_cli/service_manager.py:331-335`

```
# s6-overlay's dynamic scandir for runtime-registered services. Lives on
# tmpfs and is the directory s6-svscan watches. Writes here trigger
# automatic supervision on the next rescan.
S6_DYNAMIC_SCANDIR = Path("/run/service")
S6_SERVICE_PREFIX = "gateway-"
```

**"tmpfs" 这三个字决定了 `container_boot.py` 必须存在**:每次 `docker restart`,
`/run/service/` 被清空,而 `$HERMES_HOME/profiles/<name>/` 在持久卷上还在。
`container_boot.py` 挂在镜像的 `/etc/cont-init.d/02-reconcile-profiles`,开机时遍历持久
profile、重建服务槽,并且**只把"上次确实在跑"的那些拉起来**:

`hermes_cli/container_boot.py:31-39`

```
# Only this desired state triggers automatic restart. Everything else
# (startup_failed, starting, stopped, missing) registers the slot in
# the down state and waits for explicit user action — this avoids the
# crash-loop where a broken gateway keeps being restarted across
# `docker restart` cycles. Older installs only have gateway_state;
# newer lifecycle commands persist desired_state separately so a transient
# runtime state (draining/startup_failed) does not erase the operator's
# durable start/stop intent across pod/container recreation.
_AUTOSTART_STATES = frozenset({"running"})
```

这里有一个**双状态字段**的设计,值得记住:`gateway_state` 是 gateway 进程自己写的
**易变运行时状态**(可能是 `draining`、`startup_failed`);`desired_state` 是
`hermes gateway start/stop` 写的 **操作者意图**。只有后者能决定重启后要不要拉起——
否则一次"正在排空时被 docker restart"就会让服务再也起不来。写入点刻意是
**best-effort**(写失败不阻塞 s6 生命周期控制):

`hermes_cli/service_manager.py:359-360`

```
def _write_gateway_desired_state(name: str, desired_state: str) -> None:
    """Persist durable s6 gateway intent next to runtime status.
```

s6 后端还藏着一个 **权限**上的关键细节:

`hermes_cli/service_manager.py:416-418`

```
def _seed_supervise_skeleton(svc_dir: Path) -> None:
    """Pre-create the ``supervise/`` and top-level ``event/`` skeleton
    inside a service directory, owned by the hermes user.
```

它在触发 s6 重扫**之前**,先以 hermes 用户
(UID/GID 10000)把 `supervise/`、`event/`、`supervise/control` FIFO 建好。原因是
s6-supervise 以 root 建这些目录会得到 `0700 root:root`,而 Hermes 的一切运行时操作都通过
`s6-setuidgid` 以 hermes 用户执行,于是 `s6-svc`/`s6-svstat`/`s6-svwait` 全部 EACCES——
**整个 S6ServiceManager 生命周期在生产里是静默失效的**。之所以"抢先建"有效,是因为
s6-supervise 的 `mkdir`/`mkfifo` 都把 `EEXIST` 当成功,并**跳过**本来会把属主改回 root 的
chown/chmod。

### 2.5 s6 下的两条特殊分派

容器里 `hermes gateway start/stop/restart` 不能走主机路径,`_dispatch_via_service_manager_if_s6`
把它转成 s6 的 `want up`/`want down`:

`hermes_cli/gateway.py:6650-6656`

```
        # _profile_suffix() returns the bare profile name for
        # HERMES_HOME=<root>/profiles/<name>, "" for the default root,
        # or a hash for unrelated paths. Map "" → "default" so the
        # default-profile gateway is reachable as gateway-default.
        profile = _profile_suffix() or "default"
    mgr = get_service_manager()
    service_name = f"gateway-{profile}"
```

`--all` 走 `_dispatch_all_via_service_manager_if_s6`,它的存在理由写在 docstring 里,
是一个漂亮的"抽象泄漏"案例:主机路径的 `--all` 实现是 `pkill` 掉所有 gateway 进程,
而 s6 会在约 1 秒后把它们全部重启——**于是 `gateway stop --all` 在容器里实际是
"踢一脚所有 gateway",语义完全反了**。

另一条是 `_maybe_redirect_run_to_s6_supervision`:老用法 `docker run <image> gateway run`
在 s6 镜像里被**透明升级**成"注册+启动一个被监管的槽,然后当前进程退化成心跳"。心跳的实现
本身也踩过坑:

`hermes_cli/gateway.py:6824-6829`

```
    try:
        os.execvp("sleep", ["sleep", "infinity"])
    except OSError:
        # execvp only returns by raising; on success it replaces this
        # process. ENOENT (no `sleep` on PATH) and any other exec error
        # land here.
```

`os.execvp` 会做 PATH 查找,PATH 被用户改坏时曾**整个容器 FileNotFoundError 崩在启动阶段**
(#36208),所以补了一个纯进程内的 `_block_until_terminated()` 兜底。

---

## 3. 可观测:shared metrics 到底共享给谁

### 3.1 数据通路(6 个模块 + 2 份 schema 的分工)

```text
Hermes 生命周期钩子(on_session_start / pre_llm_call / pre_tool_call / …)
        │  observability/__init__.py   —— 只有 31 行,一个 try/except 包装器
        ▼
  relay_shared_metrics.py (1,294)  —— 唯一的钩子实现方;维护 per-profile 的 _Runtime,
        │                             把 Hermes 钩子翻译成 NeMo Relay 的 scope/mark 生命周期
        ▼
  (NeMo Relay 原生运行时,进程内)
        │
        ▼
  shared_metrics_subscriber.py (101) —— Relay 事件 → 允许清单投影;不认识的事件直接 return
        │        依赖 shared_metrics_contract.py (976) 做全部 **有界化**:
        │        枚举收敛、字符串正则+长度上限、桶化(时长/次数/重试)
        ▼
  shared_metrics.py (718)  —— SQLite 聚合(按 UTC 日 × 维度组合累加)
        │                     + 每日一次生成不可变 JSON 增量包
        ▼
  $HERMES_HOME/telemetry/shared_metrics/{metrics.sqlite3, outbox/*.json}
                                              ▲
                     schemas/hermes.shared_metrics.v{1,2}.schema.json 是这些包的封闭 schema
```

`relay_runtime.py`(14 行)不是模块,是一个 **`sys.modules` 别名**,把
`hermes_cli.observability.relay_runtime` 指向 `agent.relay_runtime`,让迁移期的插件和测试
共享同一份 profile registry。

存储位置与权限:

`hermes_cli/observability/shared_metrics.py:55-61`

```
        root = get_hermes_home() / "telemetry" / "shared_metrics"
        self.database_path = database_path or root / "metrics.sqlite3"
        self.outbox_directory = outbox_directory or root / "outbox"
        self._ensure_private_directory(self.database_path.parent)
        self._ensure_private_directory(self.outbox_directory)
        self._ensure_private_file(self.database_path)
        self._ensure_schema()
```

`hermes_cli/observability/shared_metrics.py:285-290`

```
    def _ensure_private_directory(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            path.chmod(0o700)
        except OSError:
            pass
```

目录 `0700`、DB 文件 `0600`,而且是**每次构造 store 都重新 chmod**(不只建的时候)。

### 3.2 共享给谁?——**当前没有任何远程接收方**

**负结论 + 搜索面**:

```verify
cd /home/user/hermes-agent
# 搜索面:hermes_cli/observability/ 下全部 *.py(8 个文件),
# 模式覆盖 stdlib/三方 HTTP 客户端与裸 URL;不排除任何子目录。
# 预期:无输出,退出码 1。
grep -rnE "urllib|httpx|requests|aiohttp|socket|https?://[a-z]" --include='*.py' hermes_cli/observability/
echo "退出码=$?"
```

实测**零命中,退出码 1**。补充说明两点,免得读者复现时困惑:
(a) 若去掉 `--include='*.py'`,两份 JSON schema 会命中 `"$schema": "https://json-schema.org/…"`
——那是 JSON Schema 规范标识符,不是端点;
(b) `__pycache__/*.pyc` 会命中 `post_patch_state` 这类含子串的标识符,`--include='*.py'` 已排除。

因此 **"shared metrics" 里的 "shared" 指的是"跨 Hermes 进程共享的本地 SQLite 计数器",
不是"上报给 Nous"**。同一台机器上并发的多个 Hermes 进程通过 SQLite 事务共享同一份聚合
(比如 `client_active` 的 24 小时窗口用事务化 compare-and-set 保证不重复计数),
`outbox/*.json` 是**等着未来某个 exporter 来取的本地文件**。

文档对这一点的表述与代码一致。

`docs/observability/relay-shared-metrics.md:158`

> This slice has no remote-delivery path. A future remote exporter must not reuse

### 3.3 隐私边界:三道闸

**第一道:默认关,且 managed 覆盖层改不动。**

`hermes_cli/config_defaults.py:2737-2743`

```
    # Privacy-safe aggregate metrics written only to this profile's local
    # telemetry directory. Collection is opt-in and no remote sink exists.
    "telemetry": {
        "shared_metrics": {
            "enabled": False,
        },
    },
```

`hermes_cli/observability/relay_shared_metrics.py:1087-1089`

```
        value = (
            isinstance(shared_metrics, dict) and shared_metrics.get("enabled") is True
        )
```

注意是 `is True`——字符串 `"true"`、`1` 都不算开。而且这个 `enabled()` 读的是
`read_raw_config_readonly()`(profile 自己的 `config.yaml`),**不是合并后的配置**,
注释明说这是为了让"机器管理的配置覆盖层不能替 profile 决定要不要采集"。
关掉时它还会顺手 `deactivate()` 掉已建的 runtime,不是只挡新事件。

**第二道:允许清单式投影。** 订阅器不是"过滤掉敏感字段",而是**只认识几种事件形状,
其余一律 return**;每个维度值都要过 `counter_dimensions_are_valid` 才能进 SQLite,
打包时再校验一次(`_package_metric` 不合法直接 `raise ValueError`)。工具名、调用 ID、
参数、结果、命令、错误文本、prompt、response、session/task/request ID 全都进不来——
工具只保留**类别**(不认识的 toolset 塌缩成 `other`)。

**第三道:install_id 的作用域与本地留存上限。** 每个 `$HERMES_HOME` 一个随机 UUID,
不派生自硬件/账号/路径/凭据;删掉 `telemetry/shared_metrics` 目录即重置(同时丢掉聚合与
待导出包)。已导出的本地历史 30 天后裁剪,未导出的永不裁剪:

`hermes_cli/observability/shared_metrics.py:28-33`

```
_PACKAGE_SCHEMA_VERSION = "hermes.shared_metrics.v2"
_STORE_SCHEMA_VERSION = "2"
_BUSY_TIMEOUT_MS = 250
_SCHEMA_BUSY_TIMEOUT_MS = 5_000
_LOCAL_HISTORY_RETENTION_DAYS = 30
_ACTIVE_INSTALL_STATE_KEY = "client_active_recorded_at"
```

### 3.4 v1 → v2 的 schema 演进

| | v1(338 行) | v2(702 行) |
|---|---|---|
| `$id` | `urn:hermes-agent:schema:shared-metrics:v1` | `…:v2` |
| 顶层字段 | 完全相同(schema_version / package_id / install_id / period_start / period_end / generated_at / resource / metrics),required 也相同 | 同左 |
| `$defs` | 8 个 | 17 个 |
| 计数器种类 | 3 种:`hermes.model_call.count`、`hermes.task_run.started`、`hermes.task_run.finished` | 8 种:上述 3 种 + `hermes.client.active`、`hermes.model_route.count`、`hermes.tool_call.count`、`hermes.tool_approval.count`、`hermes.skill.lifecycle.count`、`hermes.skill.load.count` |

**v2 是纯加法,顶层信封一字未改**——老的 `model_call_counter` 定义被**原样保留**在 v2 里,
文档说明理由是"让升级后仍能把旧版本攒下的待导出计数安全排空"。

真正有含义的一处改动是 **model 维度从"封闭枚举"换成了"结构受限的自由字符串"**:

`hermes_cli/observability/schemas/hermes.shared_metrics.v1.schema.json:114-118`

```
            "model_family": {
              "enum": [
                "claude",
                "deepseek",
                "gemini",
```

`hermes_cli/observability/schemas/hermes.shared_metrics.v2.schema.json:246-257`

```
            "model": {
              "type": "string",
              "minLength": 1,
              "maxLength": 256,
              "pattern": "^[a-z0-9][a-z0-9._:/@+\\-]*$"
            },
            "provider": {
              "type": "string",
              "minLength": 1,
              "maxLength": 64,
              "pattern": "^[a-z0-9][a-z0-9._:/@+\\-]*$"
            }
```

v1 把模型收敛成 20 个 family 之一(`claude`/`gpt`/`qwen`/…/`unknown`),再加
`locality`、`provider_family`、`call_role`、`outcome` 四个枚举;v2 的 `model_route`
**只留 `model` + `provider` 两个字段,值是小写化后的原始标识符**,最长 256/64 字节。
产生逻辑在:

`hermes_cli/observability/shared_metrics_contract.py:941-942`

```
def model_call_fields(kwargs: dict[str, Any]) -> dict[str, str]:
    """Return the terminal model identity and provider route known to Hermes."""
```

优先取 `response_model`,
取不到退回 `model`,都不合法则写 `"unknown"`;唯一的净化是 `_metric_identifier`
(小写、去空白、首字符与字符集白名单、长度上限)。

**取舍很清楚**:v1 那份枚举是一张要不断维护的模型目录,新模型一律落进 `unknown`,
数据越用越糊;v2 把归类责任推给后端("Pricing and model-family classification belong to
the metrics backend"),代价是**自建/私有模型名会原样落进本地包**——比如一个内部模型
`acme-internal-v3` 会逐字出现在 `outbox/*.json` 里。在"无远程 sink"的前提下这不构成外泄,
但它把"未来加 exporter"这件事的隐私评审门槛抬高了,而文档自己也把这件事挂了起来
(`docs/observability/relay-shared-metrics.md:159` 那句"A future remote exporter must not reuse the persistent
local identifier by default")。

v2 新增的 `client_active` 计数器则是相反方向的克制——**维度必须为空、值必须恰为 1**:

`hermes_cli/observability/schemas/hermes.shared_metrics.v2.schema.json:116-129`

```
        "name": {
          "const": "hermes.client.active"
        },
        "type": {
          "const": "counter"
        },
        "dimensions": {
          "type": "object",
          "additionalProperties": false,
          "maxProperties": 0
        },
        "value": {
          "const": 1
        }
```

`maxProperties: 0` + `value: const 1` 让"活跃安装"这条指标在 schema 层面就**不可能**
携带任何维度或被夸大。这是本簇里最值得抄的一个小设计:**把隐私约束写进 schema,
而不是写进 code review 备忘**。

---

## 4. PTY 三件套的分工

三个文件是**两层**,不是三个平行实现:

```text
        ┌─────────────────────────────────────────────────────┐
        │  hermes_cli/web_server.py  /api/pty WebSocket 端点   │
        └───────────────┬─────────────────────┬───────────────┘
                        │ 会话层              │ 传输层
                        ▼                     ▼
          pty_session.py (195)          PtyBridge(平台二选一)
          RingBuffer + PtySession       ├─ pty_bridge.py (293)     POSIX / ptyprocess
          + PtySessionRegistry          └─ win_pty_bridge.py (184) Windows / pywinpty
          「进程比 WebSocket 活得久」      「把一个子进程塞进伪终端」
```

**下层(两份桥)** 是同一个接口的两个平台实现,选择在 import 期完成:

`hermes_cli/web_server.py:14406-14412`

```
# PTY bridge: POSIX uses pty_bridge (fcntl/termios/ptyprocess); native Windows
# uses win_pty_bridge (pywinpty/ConPTY, already a declared dependency).  Both
# expose the same public surface — spawn/read/write/resize/close/is_available —
# so the /api/pty WebSocket handler needs no platform guards.
if sys.platform.startswith("win"):
    try:
        from hermes_cli.win_pty_bridge import WinPtyBridge as PtyBridge, PtyUnavailableError
```

`pty_bridge.py` 依赖 `fcntl`/`termios`/`ptyprocess`(原生 Windows 上没有),
`win_pty_bridge.py` 依赖 `pywinpty`(ConPTY)。两边都刻意走**字节**而不是 unicode
——`pty_bridge` 的 docstring 明说不用 `PtyProcessUnicode`,因为流式 ANSI 天生面向字节、
UTF-8 边界可能落在一次 read 中间。

**上层(会话)** 完全不关心是哪个桥,它拿到的只是一个叫 `bridge` 的鸭子类型对象:

`hermes_cli/pty_session.py:42-47`

```
class PtySession:
    def __init__(self, key: str, bridge, *, buffer_cap: int, read_timeout: float) -> None:
        self.key = key
        self.bridge = bridge
        self.buffer = RingBuffer(buffer_cap)
        self.alive = True
```

它解决的是另一个问题:**浏览器刷新一下,终端里跑的东西不能死**。做法是一个常驻 drain 任务
把 PTY 读进有界 RingBuffer,WebSocket 在就转发、不在就只入 buffer;带同一个不透明 token
重连时先回放 buffer 再续上实时流。两个专用关闭码 `WS_CLOSE_PROCESS_EXITED = 4410` /
`WS_CLOSE_SUPERSEDED = 4409` 把"进程真的退了"和"被新连接顶掉了"区分开——
否则前端无法判断该重连还是该报错。注册表 `PtySessionRegistry` 带 TTL 与 `max_sessions`,
满了先回收空闲的,回收不出来就 `RegistryFull`;这两个上限由**调用方**给定,不是会话层自带的常量。

`hermes_cli/web_server.py:14440-14442`

```
PTY_REGISTRY = PtySessionRegistry(
    ttl=30 * 60,
    max_sessions=16,
```

**导航结论**:改终端渲染/编码 → 两份桥;改"刷新后还在不在"、"最多开几个" → `pty_session.py`。

---

## 5. `hermes debug share` 打包了什么、脱敏到什么程度

### 5.1 打包内容与两个目的地

一次 `hermes debug share` 产出的是同一份 bundle,只是投递方式不同:

| 目的地 | 触发 | 通道 | 可见性 | 留存 |
|---|---|---|---|---|
| 公开 paste | 默认 | POST `https://paste.rs/`,失败退 `https://dpaste.com/api/` | **任何拿到链接的人** | 客户端尽力在 6 小时后删(见 5.3) |
| Nous 私有 S3 | `--nous` | `POST {NAS}/api/diagnostics/upload-url` 拿签名 URL → `PUT` gzip 包 | Nous 员工 + 允许清单内 Discord mod,经 Google 登录网关 | 14 天自动过期 |

`hermes_cli/diagnostics_upload.py:30-32`

```
NAS_BASE = os.environ.get(
    "HERMES_DIAGNOSTICS_BASE_URL", "https://portal.nousresearch.com"
)
```

bundle 的内容由 `collect_share_bundle` 统一生成,**两条路径共用同一个采集器**,
docstring 明确说这是为了"Nous 路径永远不会看到未脱敏的原始日志"。它的头两行就是全部输入:

`hermes_cli/debug.py:667-668`

```
    dump_text = _capture_dump()
    log_snapshots = _capture_default_log_snapshots(log_lines, redact=redact)
```

**注意 `redact=` 只传给了后者**——这正是 ■-1 的根。内容是:
1. `report` —— `hermes dump` 输出 + 五个日志的尾部(agent / errors / gateway / gui / desktop);
2. 四份**完整日志**(agent.log / gateway.log / gui.log / desktop.log),每份上限 512 KB,
   每份都前置一遍 dump 头部使其自包含。

**注意 `errors.log` 只以尾部形式出现在 report 里,不作为独立完整日志上传**。
report 里有它:

`hermes_cli/debug.py:616-618`

```
    errors_lines = min(log_lines, 100)
    buf.write(f"--- errors.log (last {errors_lines} lines) ---\n")
    buf.write(log_snapshots["errors"].tail_text)
```

但完整日志上传的循环只列了四个:

`hermes_cli/debug.py:792-798`

```
    # 2-5. Full logs (optional — failures are collected, not raised)
    for label in ("agent.log", "gateway.log", "gui.log", "desktop.log"):
        content = bundle.get(label)
        if not content:
            continue
        try:
            urls[label] = upload_to_pastebin(content, expiry_days=expiry)
```

### 5.2 脱敏做到什么程度

日志侧是**强制脱敏**,不受用户配置影响:

`hermes_cli/debug.py:436-439`

```
    from agent.redact import redact_sensitive_text

    text = redact_sensitive_text(text, force=True)
    return _EMAIL_ADDRESS_RE.sub("[REDACTED_EMAIL]", text)
```

`force=True` 的含义是**绕过运营者的 `security.redact_secrets` 开关**——本地日志文件本身不改,
只有内存里那份要上传的副本被洗。此外额外加了一层邮箱正则。脱敏后正文前置一条可见 banner,
让看 paste 的人知道内容被处理过。

dump 侧走的是**另一条路**:不过 `_redact_log_text`,而是靠调用参数把密钥整个关掉。

`hermes_cli/debug.py:566-569`

```
    from hermes_cli.dump import run_dump

    class _FakeArgs:
        show_keys = False
```

`hermes_cli/dump.py:397-402`

```
    for env_var, label in api_keys:
        val = os.getenv(env_var, "")
        if show_keys and val:
            display = _redact(val)
        else:
            display = "set" if val else "not set"
```

读起来像反的,其实不是:`show_keys=True` 才显示**掩码后的**密钥片段(`mask_secret`),
`show_keys=False` 只显示 `set` / `not set`。`debug share` 用后者,所以密钥连掩码形式都不出现。
dump 里的配置项也是**封闭允许清单**(`_interesting_overrides` 只挑 15 个键,如
`agent.max_turns`、`display.skin`),不是把 config.yaml 倒出来。清单之外只有两处
"整个列表 `str()` 直印",其中一处是 ■-1 关心的:

`hermes_cli/dump.py:271-274`

```
    # Fallback providers
    fallbacks = config.get("fallback_providers", [])
    if fallbacks:
        overrides["fallback_providers"] = str(fallbacks)
```

用户在上传前会看到明确的隐私告知,并且**没有默认同意**——`_confirm_upload` 要求显式确认;
公开 paste 的告知逐条列出了"不会被脱敏"的东西:

`hermes_cli/debug.py:199-206`

> ⚠️  This will upload system info + logs to a PUBLIC paste service.
>
> Cryptographic secrets (API keys, tokens, passwords) are redacted before
> upload, but the following personal data is NOT redacted and will be public:
>   • Your display name and persistent platform user ID
>   • Verbatim content of your recent messages (prompts, responses, tool output)
>   • Local filesystem paths
>   • Any other PII present in the logs

**总评:密钥侧的边界是清楚且被两条独立机制守住的;对话内容侧则是"如实告知,不做处理"。**
这是个诚实的取舍——真要脱掉对话内容,这份 bundle 也就没有调试价值了。

### 5.3 ■ 两处安全含义

**■-1(中):`hermes dump` 的输出是整个上传包里唯一不过强制脱敏的一段。**
`collect_share_bundle` 对四份日志逐一 `_redact_log_text`,但 `dump_text` 直接拼进 report
并前置到每份日志。它的安全性**完全依赖** `show_keys=False` 与那张 15 键允许清单;
一旦以后有人往 dump 里加一个打印用户提供值的字段(例如自定义 `base_url`——
`hermes_cli/dump.py:272-274` 已经在 `str(fallbacks)` 逐字打印 `fallback_providers` 列表),
它会**绕过**这一层安全网直接进公开 paste。
本轮**未发现**已被这条路径泄漏的具体凭据(检查面:`hermes_cli/dump.py` 内全部 `print`
语句,以及 `_interesting_overrides` 的 15 个键与 `fallback_providers`/`toolsets` 两处
`str()` 直印);这里记的是**结构性不对称**,不是已发生的泄漏。
**修法很轻**:把 `dump_text` 也过一遍 `_redact_log_text`,代价只是几毫秒正则。

**■-2(低-中):公开 paste 的"6 小时自动删除"是尽力而为,但告知语写得像承诺。**
`_AUTO_DELETE_SECONDS = 21600`(`hermes_cli/debug.py:65`)只是往
`~/.hermes/pastes/pending.json` 里记一条待删记录:

`hermes_cli/debug.py:264-268`

```
    The replacement is stateless: we append to ``~/.hermes/pastes/pending.json``
    and the gateway's cron ticker sweeps expired entries once per hour.
    ``hermes debug share`` also runs an opportunistic sweep as a fallback
    for CLI-only users.  If neither runs again, paste.rs's own retention
    policy handles cleanup.
```

清扫方只有两个。一是 gateway 的 cron ticker:

`gateway/run.py:26203-26206`

```
        if tick_count % PASTE_SWEEP_EVERY == 0:
            try:
                deleted, remaining = _sweep_expired_pastes()
                if deleted:
```

二是下一次
`hermes debug` 调用(`hermes_cli/debug.py:771/858/949/1020`)。**一个只用 CLI、分享一次
之后再没跑过 hermes 的用户,那份含完整对话内容的公开 paste 不会在 6 小时后消失**,
只能等 paste.rs 自己的保留策略。而用户看到的告知是无条件句
"Pastes auto-delete after 6 hours"(`hermes_cli/debug.py:208-209`)。
代码自己的 docstring 是诚实的,面向用户的那句不是。
(注:这句话在**代码字符串**里,不在 website/docs 里,所以按本项目记号规则**不计入 ▲**。)

---

## 6. ▲ ◇ ■ ◎ 汇总

本簇取证到的条目如下。**每条都附锚点文件与一句话现象**,便于后续轮直接接手。

### ■ 代码缺陷 / 风险(2 条)

| 编号 | 锚点 | 一句话现象 |
|---|---|---|
| ■-1 | `hermes_cli/debug.py:667`(`collect_share_bundle` 第一行 `dump_text = _capture_dump()`) | 上传包里四份日志逐一过 `_redact_log_text`,唯独 `dump_text` 不过,其安全性只靠 `show_keys=False` 与 dump 里的 15 键允许清单;dump 已在 `hermes_cli/dump.py:272-274` 逐字打印 `fallback_providers`(含 `base_url`)。 |
| ■-2 | `hermes_cli/debug.py:208-209`(`_PRIVACY_NOTICE` 中 "Pastes auto-delete after 6 hours") | 删除是客户端尽力而为,靠 gateway cron 或下一次 `hermes debug` 调用清扫;纯 CLI 用户分享一次后不再运行 hermes,公开 paste 不会被删。同文件 `:264-268` 的 docstring 自己承认了这一点。 |

### ◇ 代码有、文档无(3 条)

| 编号 | 锚点 | 一句话现象 |
|---|---|---|
| ◇-1 | `hermes_cli/gateway.py:1778-1779`(`_profile_suffix` 的 hash 兜底,原文见下) | `website/docs/user-guide/multi-profile-gateways.md:345-351` 的服务文件表只列了"默认 profile"和"`profiles/<name>`"两种命名,漏了第三种:任意其它 `HERMES_HOME` 会得到 `hermes-gateway-<sha256前8位>`。 |
| ◇-2 | `hermes_cli/debug.py:617-618`(report 里写入 errors.log 尾部) | `website/docs/reference/cli-commands.md:871` 描述 debug share 内容为 "recent agent, gateway, GUI/dashboard, and desktop logs",未提 `errors.log`;实际 report 含其尾部(最多 100 行),但它**不**作为独立完整日志上传。 |
| ◇-3 | `hermes_cli/gateway.py:6675`(`_dispatch_all_via_service_manager_if_s6`) | `cli-commands.md:257` 只说 `--all` 是"act on every profile's gateway",没有交代 s6 容器下走的是完全不同的实现——主机路径的 pkill 语义在 s6 下会被监管器抵消成"踢一脚"。 |

◇-1 的代码侧原文:

`hermes_cli/gateway.py:1778-1779`

```
    # Fallback: short hash for arbitrary HERMES_HOME paths
    return hashlib.sha256(str(home).encode()).hexdigest()[:8]
```

### ◎ 文档为真但显著保守(1 条)

| 编号 | 锚点 | 一句话现象 |
|---|---|---|
| ◎-1 | `hermes_cli/service_manager.py:86-100`(`detect_service_manager` 的 docstring 与实现) | `website/docs/user-guide/multi-profile-gateways.md` 通篇只讲 launchd/systemd 两种后端("launchd/systemd quirks"),字面为真但实际有四种(另有 Windows 计划任务与容器 s6),后两者的行为差异远大于文档里讨论的 quirks。 |

### ▲ 文档与代码矛盾:**本簇 0 条**

搜索面已写明:通读了 `website/docs/user-guide/multi-profile-gateways.md`(服务文件命名、
plist/unit 路径、linger、launchd 重载)、`website/docs/reference/cli-commands.md` 的
`hermes gateway` / `hermes debug` / `hermes logs` 三节、
`docs/observability/relay-shared-metrics.md` 全文、
`website/docs/user-guide/skills/optional/devops/devops-hermes-s6-container-supervision.md`。
逐条比对的断言包括:launchd label 与 plist 路径(`ai.hermes.gateway[-<profile>].plist`,
对 `hermes_cli/gateway.py:3697` 与 `:2514-2516`)、systemd 单元名
(`hermes-gateway[-<profile>].service`,对 `:1832-1835`)、shared metrics 的
opt-in 位置 / 无远程通道 / install_id 语义 / v1 保持不变 / 30 天本地留存
(对 `hermes_cli/observability/shared_metrics.py:28-33` 与 3.2 节的 grep)、s6 服务目录布局与 `s6-svc` 操作
(对 `hermes_cli/service_manager.py:334-335`)。**未发现矛盾**;发现的偏差都是"漏说"或"保守",
已分别记为 ◇ / ◎。

---

## 7. 逐文件角色表(30 个文件 / 21,608 行)

### gateway 子命令与服务安装

| 文件 | 行数 | 一句话角色 |
|---|---|---|
| `hermes_cli/gateway.py` | 7,461 | `hermes gateway` 全部子命令的实现;**进程发现 + 四种服务后端 + 平台配置向导 + 状态渲染**,唯一一次 `asyncio.run(start_gateway(...))` 把控制权交给 `gateway/` 运行时 |
| `hermes_cli/gateway_windows.py` | 1,696 | Windows 侧服务安装的全部实现:计划任务 XML 生成、`.cmd`/`.vbs` 启动脚本、UAC 提权交接、schtasks 失败时降级到启动文件夹、detached spawn、deep 状态探针 |
| `hermes_cli/service_manager.py` | 1,125 | 四后端统一 `ServiceManager` Protocol + `detect_service_manager()`;三个主机后端是薄壳,**`S6ServiceManager` 是唯一有真实现的**(服务目录渲染、supervise 骨架预置、desired_state 落盘) |
| `hermes_cli/container_boot.py` | 615 | 容器 `cont-init.d/02-reconcile-profiles` 入口:tmpfs 上的 s6 服务槽每次重启都没了,据持久 profile 重建,只自动拉起 `desired_state == running` 的;dashboard 容器直接跳过 |
| `hermes_cli/gateway_enroll.py` | 277 | `hermes gateway enroll`:拿 Nous Portal token 向 connector 换取 per-gateway secret + delivery key,写进 `.env`;是 relay connector 侧鉴权的 gateway 半边 |
| `hermes_cli/windows_ssh_runtime.py` | 508 | 原生 Windows 上 Desktop **SSH 后端**生命周期的信任边界:用 Win32 安全描述符把 token/lock/log 文件限死在"当前 SID + SYSTEM",按 (pid, 创建时间, hermes 路径, spawn nonce) 四元组确认进程身份后才 spawn/terminate;是一个被 Electron 端以 JSON-over-stdin 调用的独立小进程(`dispatch`/`main`) |

### 卸载与桌面集成

| 文件 | 行数 | 一句话角色 |
|---|---|---|
| `hermes_cli/uninstall.py` | 979 | `hermes uninstall`:清 shell rc 里的 PATH、wrapper 脚本、node 符号链接、gateway 服务、Windows 注册表 PATH 与环境变量、逐 profile 卸载;分"全删"与"保留 `~/.hermes`"两档 |
| `hermes_cli/gui_uninstall.py` | 306 | `hermes uninstall --gui`:只删 Electron 桌面端的两种形态(源码构建产物 + 系统安装的 DMG/NSIS/AppImage/deb/rpm)与其 userdata,**不碰 Python agent 与用户配置** |
| `hermes_cli/linux_desktop_entry.py` | 173 | 写/删 XDG `hermes.desktop`;`Exec` 与 `Icon` 都必须写绝对路径(启动器没有 shell PATH),缓存刷新工具存在才调 |

### dashboard 侧的进程与注册

| 文件 | 行数 | 一句话角色 |
|---|---|---|
| `hermes_cli/dashboard_procs.py` | 458 | 从 `main.py` 机械拆出的三个 dashboard 进程卫生助手(扫描/杀陈旧进程/检测并发实例);通过惰性 `_m()` 回指 main,保住既有的 monkeypatch 路径 |
| `hermes_cli/dashboard_register.py` | 427 | `hermes dashboard register`:用 `~/.hermes/auth.json` 的 Portal token 去 NAS 建一个自托管 OAuth client,把 `agent:{id}` 写进 `.env`,替代手工在门户页面点按钮 |

### PTY / 子进程 / stdio

| 文件 | 行数 | 一句话角色 |
|---|---|---|
| `hermes_cli/pty_bridge.py` | 293 | POSIX 伪终端桥(`ptyprocess` + `fcntl`/`termios`),给 dashboard 的 xterm.js 提供字节级 read/write/resize;原生 Windows 上 import 即 `ImportError`,由调用方降级 |
| `hermes_cli/win_pty_bridge.py` | 184 | 上面那个的 Windows ConPTY 对应物(`pywinpty`),**公开接口逐个对齐**,使 `/api/pty` 端点无需平台分支 |
| `hermes_cli/pty_session.py` | 195 | 桥之上的会话层:RingBuffer + 常驻 drain 任务 + token 重连回放 + 带 TTL/上限的注册表,让终端进程活得比 WebSocket 久 |
| `hermes_cli/_subprocess_compat.py` | 464 | Windows subprocess 垫片:`npm` → `npm.cmd` 的 PATHEXT 解析、`start_new_session` → `CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW`、消除控制台闪窗 |
| `hermes_cli/stdio.py` | 251 | Windows stdio 强制 UTF-8(Python 侧 reconfigure + 控制台代码页翻到 65001),否则 banner 里的框线字符会在 cp1252 控制台上直接 `UnicodeEncodeError` 打死 CLI |

### 独立子命令

| 文件 | 行数 | 一句话角色 |
|---|---|---|
| `hermes_cli/cron.py` | 504 | `hermes cron` 的 CLI 壳:list/create/edit/pause/resume/run/remove/status/tick;自身不实现调度,调 cron API,并在 gateway 没跑时给出警告 |
| `hermes_cli/webhook.py` | 307 | `hermes webhook` 订阅管理,持久化到 `~/.hermes/webhook_subscriptions.json`,由 webhook adapter 热加载,**不需要重启 gateway** |
| `hermes_cli/hooks.py` | 434 | `hermes hooks` list/test/revoke/doctor 的薄壳;同意记录在 `~/.hermes/shell-hooks-allowlist.json`,实际逻辑全在 `agent.shell_hooks` |
| `hermes_cli/logs.py` | 397 | `hermes logs`:尾读/跟随 `~/.hermes/logs/*.log`,支持按 level / session / component / 相对时间过滤 |

### 诊断上传

| 文件 | 行数 | 一句话角色 |
|---|---|---|
| `hermes_cli/debug.py` | 1,046 | `hermes debug share|delete`:采集 dump + 五份日志 → **强制脱敏** → 上传公开 paste 或(`--nous`)私有 S3;含 paste 待删清单与清扫逻辑 |
| `hermes_cli/diagnostics_upload.py` | 138 | `--nous` 目的地的纯 stdlib 客户端:向 NAS 要一个带 `ContentLength` 的预签名 PUT URL,再把 gzip 包 PUT 上去;无回调、无状态 |

### 可观测

| 文件 | 行数 | 一句话角色 |
|---|---|---|
| `hermes_cli/observability/relay_shared_metrics.py` | 1,294 | 唯一实现 Hermes 生命周期钩子的模块:维护 per-profile `_Runtime`,把 13 个钩子翻译成 Relay 的 scope/mark;`enabled()` 是采集总闸(读 profile 自有 config,`is True` 才开) |
| `hermes_cli/observability/shared_metrics_contract.py` | 976 | **有界化契约**:所有枚举集合、标识符正则与长度上限、时长/次数/重试的桶化、各指标的 dimensions 校验函数;整套隐私边界的规则都在这里 |
| `hermes_cli/observability/shared_metrics.py` | 718 | SQLite 聚合存储(0700 目录 / 0600 文件)+ 每日增量包生成 + outbox 原子导出 + 30 天本地留存裁剪;含 v1→v2 的表迁移 |
| `hermes_cli/observability/shared_metrics_subscriber.py` | 101 | Relay 事件 → 允许清单投影的订阅器;认不出的事件直接 return,带 runtime_id 过滤与 `deactivate()` |
| `hermes_cli/observability/relay_runtime.py` | 14 | **不是模块,是 `sys.modules` 别名**,指向 `agent.relay_runtime`,让迁移期插件/测试共享同一份 profile registry |
| `hermes_cli/observability/__init__.py` | 31 | 31 行的门面:`observe_lifecycle` / `handles_hook`,把异常吞成 warning,保证观测失败不影响 agent |
| `…/schemas/hermes.shared_metrics.v2.schema.json` | 702 | 当前增量包的封闭 schema:8 种计数器;`client.active` 用 `maxProperties: 0` + `value: const 1` 把隐私约束写进 schema |
| `…/schemas/hermes.shared_metrics.v1.schema.json` | 338 | 旧包 schema,**冻结不改**;3 种计数器,模型维度是 20 项封闭 family 枚举 |

---

## 8. 可迁移的设计原则(给 R12 用)

1. **把"进程管理"和"进程内部"划成两个包,并让边界落在文件系统契约上。**
   本簇 38 条跨界 import 里 29 条是 `gateway.status`——那不是 API 依赖,是"谁来读写
   PID 文件与 runtime status"。这让 CLI 可以在 gateway 根本没装的机器上正常工作。
2. **服务安装的抽象要按"操作成本"切,不要按"名词"切。** `ServiceManager` 把生命周期与
   运行时注册分成两段、并强制调用方先问 `supports_runtime_registration()`,正是因为
   主机上"新增一个服务"是有交互、要提权的重操作,容器里只是 mkdir。
3. **安装路径必须有降级链,且每一档都告诉用户失去了什么。** Windows 的
   计划任务 → 启动文件夹 → 直接 spawn 是本簇最好的样板:永不以"装不上"收场,
   但每次降级都打印损失。
4. **易变的运行时状态与持久的操作者意图必须是两个字段。** `gateway_state` vs
   `desired_state` —— 没有这个区分,一次"正在排空时重启容器"就会让服务再也起不来。
5. **隐私约束尽量写进 schema,而不是写进评审备忘。** `maxProperties: 0` /
   `value: const 1` 是机器可校验的,code review 的记忆不是。
6. **默认关 + 只读 profile 自有配置 + 允许清单式投影,三者缺一不可。** 只有默认关会被
   管理覆盖层绕过;只有允许清单会在开关误开时全量泄漏。
7. **诊断包的脱敏要有单一采集器。** `collect_share_bundle` 让两个目的地共用同一份
   已脱敏产物,是防止"新加一个上传通道就绕过脱敏"的结构性做法——本簇的 ■-1 恰好是这个
   原则的一个未贯彻处(dump 段没进这条管道)。

## 9. 延伸

- 运行时侧(`gateway/run.py`、`gateway/status.py`、`gateway/restart.py`)见 R7 / R7C 产出。
- 本簇未展开、留给后续轮的:`gateway setup` 向导内各平台的具体配置流程
  (`hermes_cli/gateway.py:5366-6623`,约 1,260 行);
  `gateway_windows.py` 的 deep 状态探针(`:1298-1430`);
  `windows_ssh_runtime.py` 的 Win32 安全描述符校验(`_verify_security`,`:107`)。
