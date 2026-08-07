# r7c-raw-restart-readiness · 重启 / 就绪 / 缩容 7 文件

> 基线 `863e31318553cda8ad61df681d08175364d4164b`(下简称 `@ 863e313`)。
> 本篇覆盖 `gateway/` 下 7 个「进程生命周期外围」小文件,共 837 行(实测 `wc -l`,
> 任务书写的 886 为估值):
> restart.py 120 / restart_loop_guard.py 150 / readiness.py 122 / systemd_notify.py 176 /
> cgroup_cleanup.py 81 / scale_to_zero.py 124 / code_skew.py 64。
> 全部逐行读完;凡断言均附 `路径:行号 @ 863e313` + 代码原文。

---

## 0. 一句话

这 7 个文件是 hermes 网关**与"外部监督者"(systemd / launchd / s6 / Fly)对话的全部词汇表**:
用退出码说"请重启我"(restart.py)、用磁盘计数说"别再重启我了"(restart_loop_guard.py)、
用 sd_notify 说"我活着 / 我要停了"(systemd_notify.py)、用 HTTP 200+JSON 说"我就绪到什么程度"
(readiness.py)、用 ExecStopPost 收拾自己没带走的孩子(cgroup_cleanup.py)、
用纯谓词判断"可以睡了"(scale_to_zero.py)、用 git 指纹说"我脑子里的代码过期了"(code_skew.py)。
**7 个都真接线;其中 scale_to_zero 的纯函数正确且有测试,但 run.py 侧的绑定
`_scale_to_zero_has_live_background_work` 把网关自己的常驻 watcher 也算成"活工作",
导致生产环境永远判不出 idle —— 本轮最重的发现(见 §2.5)。**

---

## 1. 逐文件

### 1.1 `gateway/restart.py`(120 行)—— 重启的「词汇表 + 解析器」

#### 问题

一个长活网关要重启自己,有两条互斥的路:
(a) **退出让 supervisor 拉起**;(b) **自己 fork 一个脱离进程,等自己死后再把自己拉起来**。
选错就是"网关死了再也不回来"。判断依据(有没有 supervisor、是不是容器)和两个超时值的解析,
被三个调用方(gateway/run.py、gateway/slash_commands.py、hermes_cli/gateway.py)共享,
所以抽成一个**无状态常量+纯函数模块**。

**注意:restart.py 本身不 exec、不 fork、不发信号。** 它只提供 5 个常量 + 5 个纯函数。
真正的动作在 run.py / slash_commands.py。

#### 实现

**(1) 两个退出码就是与 supervisor 的全部协议。**

`gateway/restart.py:8-16 @ 863e313`:
```python
# EX_TEMPFAIL from sysexits.h — used to ask the service manager to restart
# the gateway after a graceful drain/reload path completes.
GATEWAY_SERVICE_RESTART_EXIT_CODE = 75

# EX_CONFIG from sysexits.h — fatal configuration error (e.g. token
# collision, no messaging platforms).  The s6 finish script translates
# this into exit 125 (permanent failure) so the supervisor stops
# restarting the gateway.  See #51228.
GATEWAY_FATAL_CONFIG_EXIT_CODE = 78
```

75 与 78 分别被写进生成的 systemd unit 的两个指令,`hermes_cli/gateway.py:2917-2918 @ 863e313`
(system unit)与 `2955-2956`(user unit)完全同文:
```
RestartForceExitStatus={GATEWAY_SERVICE_RESTART_EXIT_CODE}
RestartPreventExitStatus={GATEWAY_FATAL_CONFIG_EXIT_CODE}
```
即:**75 = 强制当作失败去重启(即使 `Restart=on-failure`);78 = 永不重启。**

78 在 s6(Docker)侧的翻译不是签进仓库的脚本,而是**运行时生成**的
`hermes_cli/service_manager.py:711-733 @ 863e313`:
```python
    @staticmethod
    def _render_finish_script() -> str:
        """Generate the finish script for a profile-gateway s6 service.

        When the gateway exits with EX_CONFIG (78) — a fatal
        configuration error such as a token collision or no messaging
        platforms — we tell s6-supervise to stop restarting by exiting
        125 (permanent failure).  Any other exit code lets s6 restart
        normally.  See #51228.
        """
        from gateway.restart import GATEWAY_FATAL_CONFIG_EXIT_CODE

        code = GATEWAY_FATAL_CONFIG_EXIT_CODE
        return (
            "#!/command/with-contenv sh\n"
            ...
            f'if [ "$1" = "{code}" ]; then\n'
            "  exit 125\n"
            "fi\n"
            "exit 0\n"
        )
```
(签进仓库的 `docker/s6-rc.d/` 里只有 `dashboard/finish`,网关的 finish 是注册期生成的 —— 我一开始
按 `find . -name "finish*"` 只找到 dashboard,差点误判 restart.py 的 docstring 说谎;它没说谎。)

**(2) 「有没有 supervisor」的四路探测。**

`gateway/restart.py:37-54 @ 863e313`:
```python
def is_gateway_supervisor_process(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return whether this gateway process is owned by a supervisor."""
    env = os.environ if environ is None else environ
    if env.get("INVOCATION_ID"):
        return True
    if env.get("HERMES_S6_SUPERVISED_CHILD"):
        return True
    xpc_service = env.get("XPC_SERVICE_NAME", "")
    if xpc_service and xpc_service != "0":
        return True
    return str(env.get(EXTERNAL_GATEWAY_SUPERVISOR_ENV, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
```
- `INVOCATION_ID` —— systemd 给每个 unit 进程注入。
- `HERMES_S6_SUPERVISED_CHILD` —— s6 longrun 的 run 脚本自己导出的
  (`hermes_cli/service_manager.py:686 @ 863e313`:`lines.append("export HERMES_S6_SUPERVISED_CHILD=1")`)。
- `XPC_SERVICE_NAME` —— launchd 注入 job label;**交互 shell 继承的是字符串 `"0"`**,
  所以第 47 行必须显式排除 `"0"`,否则一个人在 macOS 终端里手跑的网关会被误判成有人管,
  退 75 之后没人拉它。
- `HERMES_GATEWAY_EXTERNAL_SUPERVISOR` —— 逃生舱,由 `hermes gateway run --external-supervisor`
  设置(`hermes_cli/gateway.py:6870-6871 @ 863e313`)。为什么需要它,注释写得很清楚,
  `gateway/restart.py:18-21 @ 863e313`:
```python
# Set by ``hermes gateway run --external-supervisor``. Unlike systemd's
# INVOCATION_ID and launchd's XPC_SERVICE_NAME, this survives wrappers that
# intentionally replace the child environment (for example ``sudo env -i``).
EXTERNAL_GATEWAY_SUPERVISOR_ENV = "HERMES_GATEWAY_EXTERNAL_SUPERVISOR"
```

**(3) 容器探测被单独抽出来,理由是"可测性",且注释直接点名了自测污染。**

`gateway/restart.py:57-66 @ 863e313`:
```python
def is_container_restart_context() -> bool:
    """Return whether the gateway is running inside a container for restart
    routing purposes (Docker/Podman ⇒ the detached setsid path dies with the
    cgroup; exit-75 service restart is the only viable path).

    Extracted from the inline probe in the /restart handler so tests can mock
    container detection hermetically — a real ``/.dockerenv`` on a
    containerized CI runner otherwise flips the routing under the test.
    """
    return os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")
```
对应的 mock 在 `tests/gateway/test_restart_service_detection.py:46-48 @ 863e313`。

**(4) 路由在哪:`/restart` 处理器。**

`gateway/slash_commands.py:1609-1628 @ 863e313`:
```python
        # When running under a service manager (systemd/launchd) or inside a
        # Docker/Podman container, use the service restart path: exit with
        # code 75 so the service manager / container restart policy restarts
        # us.  The detached subprocess approach (setsid + bash) doesn't work
        # under systemd (KillMode=mixed kills the cgroup) or Docker (tini
        # exits when the gateway dies, taking the detached helper with it).
        # Native supervisor markers cover direct systemd/launchd starts. The
        # explicit marker covers wrappers such as ``sudo env -i`` that strip
        # those markers before execing the foreground gateway.
        from gateway.restart import (
            is_container_restart_context,
            is_gateway_supervisor_process,
        )

        _under_service = is_gateway_supervisor_process()
        _in_container = is_container_restart_context()
        if _under_service or _in_container:
            self.request_restart(detached=False, via_service=True)
        else:
            self.request_restart(detached=True, via_service=False)
```

**回答任务书的"自重启怎么做?exec 自己?退出让 supervisor 拉起?" —— 两条都有,二选一,
且都不是 `os.execv`:**

- **有 supervisor / 在容器里** → `_restart_via_service=True` → 走 `stop()` 全流程后设退出码 75,
  `gateway/run.py:13116-13137 @ 863e313`:
```python
            if self._restart_requested and self._restart_via_service:
                self._launch_systemd_restart_shortcut()
                # Always exit with TEMPFAIL (75) on service-managed
                # restarts.  The shortcut helper above is best-effort and
                # commonly fails on real deployments: non-root gateway
                # units hit Polkit denials when invoking ``systemd-run
                # --system``, headless boxes have no user bus for
                # ``--user``, and operator-managed unit files may use
                # ``Restart=on-failure`` rather than ``Restart=always``.
                # Exit 75 paired with ``RestartForceExitStatus=75`` makes
                # systemd treat the planned restart as a controlled
                # failure and revive the unit via ``Restart=on-failure``,
                # regardless of whether the helper survived.  Without
                # this, a clean exit (0) on Linux left the gateway dead
                # until someone rebooted the host.  Only the planned code
                # (75) is whitelisted via ``RestartForceExitStatus``; a
                # genuine crash exits non-zero-but-not-75, so real crash
                # loops are still governed by the unit's normal
                # ``Restart=``/``RestartSec`` (and any StartLimit the
                # operator sets) rather than force-restarted here.
                self._exit_code = GATEWAY_SERVICE_RESTART_EXIT_CODE
```
  另有一条"加速通道":`_launch_systemd_restart_shortcut`
  (`gateway/run.py:9982-10060 @ 863e313`)用 `systemd-run --collect --unit <name>-planned-restart-<pid>`
  起一个瞬时 unit,轮询 `kill -0 <pid>` 等本进程死掉,然后 `systemctl reset-failed && systemctl restart`。
  它先用 `systemctl show <svc> --property=MainPID --value` 在 system / user 两个 scope 里比对自己的 PID
  来决定加不加 `--user`(`gateway/run.py:10024-10040`),比对不上就 bail —— 注释说硬编码 `--user`
  曾经导致 system-unit 部署重启不了。

- **没有 supervisor(纯前台)** → `_restart_detached=True` → 在 `stop()` 里 fork 一个
  **脱离会话的 watcher**,`gateway/run.py:12937-12941 @ 863e313` 调用
  `_launch_detached_restart_command`(`gateway/run.py:9795`)。POSIX 分支的实质是一行 shell,
  `gateway/run.py:9950-9955 @ 863e313`:
```python
        cmd = " ".join(shlex.quote(part) for part in hermes_cmd)
        shell_cmd = (
            f"deadline=$(( $(date +%s) + {int(restart_after_s)} )); "
            f"while kill -0 {current_pid} 2>/dev/null && [ $(date +%s) -lt $deadline ]; do sleep 0.2; done; "
            f"{cmd} gateway restart"
        )
```
  再用 `setsid bash -lc` + `start_new_session=True` 拉起(`gateway/run.py:9964-9977`)。
  **关键细节:必须把 `_HERMES_GATEWAY` 标记从子环境里抠掉**,`gateway/run.py:9956-9963 @ 863e313`:
```python
        # Same marker scrub as the Windows watcher above: this watcher runs
        # `hermes gateway restart` from outside the gateway, but it inherits
        # _HERMES_GATEWAY=1 from us, and the CLI's self-restart loop guard
        # refuses to run when that marker is set — silently (DEVNULL), so the
        # gateway stops and never comes back.
        from tools.environments.local import build_subprocess_env
        watcher_env = build_subprocess_env(scrub_secrets=False, inherit_profile_home=True)
        watcher_env.pop("_HERMES_GATEWAY", None)
```
  Windows 没有 setsid/bash,改成用 `sys.executable -c <内联 watcher 源码>`
  (`gateway/run.py:9818-9947`),里面还要绕开 `os.kill(pid,0)` 在 Windows 上会变成
  `GenerateConsoleCtrlEvent` 的坑(bpo-14484,`gateway/run.py:9832-9834`)。

**(5) 状态怎么传到新进程 —— 不靠内存,全靠 HERMES_HOME 下的 JSON marker。**
`/restart` 处理器在发起前先写去重 marker,`gateway/slash_commands.py:1575-1606 @ 863e313`
写 `.restart_last_processed.json`;`stop()` 里写 planned-restart 通知 marker,
`gateway/run.py:13102-13114 @ 863e313`:
```python
            if self._restart_requested and self._restart_command_source is None:
                try:
                    atomic_json_write(
                        _planned_restart_notification_path(),
                        {
                            "requested_at": time.time(),
                            "via_service": bool(self._restart_via_service),
                            "detached": bool(self._restart_detached),
                        },
                        indent=None,
                    )
```
新进程启动后读这些 marker 发"gateway restarted"通知。**这是本簇的统一模式:进程间状态一律落盘,
因为每次重启都是全新进程,内存必然清零。**(restart_loop_guard 用同一模式,见 §1.2。)

**(6) 两个超时的解析,以及为什么它们不对称。**

`gateway/restart.py:23-34 @ 863e313`:
```python
DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT = float(
    DEFAULT_CONFIG["agent"]["restart_drain_timeout"]
)

# In-band restart (``/restart``, SIGUSR1, self-restart from a child CLI)
# waits for active turns to finish *before* ``stop()`` begins. Distinct
# from ``restart_drain_timeout``, which is the force-interrupt budget
# once ``stop()`` is running (and must stay short under systemd
# TimeoutStopSec). See #77184.
DEFAULT_GATEWAY_RESTART_AFTER_TURN_TIMEOUT = float(
    DEFAULT_CONFIG["agent"]["restart_after_turn_timeout"]
)
```
实测值(`/home/user/hermes-venv/bin/python -c "from gateway.restart import *; ..."`):
`DRAIN=0.0`、`AFTER_TURN=21600.0`(6 小时)。来源
`hermes_cli/config_defaults.py:47 @ 863e313` `"restart_drain_timeout": 0,` 与
`:54` `"restart_after_turn_timeout": 21600,`。

`0` 的语义在两个解析器里**故意不同**。`gateway/restart.py:78-92 @ 863e313`:
```python
def parse_restart_after_turn_timeout(raw: object) -> float:
    """Parse the after-turn wait cap for in-band restart, falling back to default.

    ``0`` is a deliberate disable (legacy immediate drain) and must not fall
    through to the default — unlike empty/missing input.
    """
    if raw is None:
        return DEFAULT_GATEWAY_RESTART_AFTER_TURN_TIMEOUT
    if isinstance(raw, str) and not raw.strip():
        return DEFAULT_GATEWAY_RESTART_AFTER_TURN_TIMEOUT
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_GATEWAY_RESTART_AFTER_TURN_TIMEOUT
    return max(0.0, value)
```
而 drain 版没有这个区分,`gateway/restart.py:69-75 @ 863e313`:
```python
def parse_restart_drain_timeout(raw: object) -> float:
    """Parse a configured drain timeout, falling back to the shared default."""
    try:
        value = float(raw) if str(raw or "").strip() else DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
    except (TypeError, ValueError):
        return DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
    return max(0.0, value)
```
`str(raw or "")` 让 **int `0` 落进 default 分支、str `"0"` 落进 float 分支**。
今天两条路都得 0.0(实测 `parse_drain(0)=0.0`、`parse_drain("0")=0.0`),因为 default 本身就是 0;
**但只要有人把 `restart_drain_timeout` 的 default 改成非 0,`0` 这个显式配置就会被静默吞掉。**
潜在坑,记一笔(见 §4 的 ▲3)。

**(7) 预算函数:CLI 等网关退出要等多久。**

`gateway/restart.py:95-120 @ 863e313`:
```python
def resolve_restart_exit_wait_budget(
    drain_timeout: float,
    after_turn_timeout: float,
    *,
    headroom: float = 15.0,
) -> float:
    """Seconds a CLI should wait for the gateway PID to exit after SIGUSR1.

    In-band restart may defer ``stop()`` until active turns finish
    (``after_turn_timeout``) and then spend up to ``drain_timeout`` inside
    ``stop()``. Callers that fall back to a hard kill on wait expiry must
    cover both phases or they reintroduce #77184.
    """
```
按默认值实测 = `0 + 21600 + 15 = 21615` 秒。**取舍:CLI 的 `hermes gateway restart` 在极端情况下
会安静等 6 小时也不硬杀。** 这是 #77184 的直接后果 —— 宁可等,也不要把用户那一回合腰斩。

#### 设计理由

- **常量共享而非各处写死**:75/78 出现在 unit 模板、s6 finish 生成器、run.py 退出路径、
  CLI 的 systemd 状态诊断(`hermes_cli/gateway.py:1231`、`:3652-3654`)四处;
  抽成一个 import 就不会漂。
- **探测/解析全是纯函数**:唯一副作用是读 `os.environ` 与 `os.path.exists`,且 env 可注入
  (`environ` 形参,`gateway/restart.py:38`),容器探测可 monkeypatch。这让 `/restart` 的路由
  能在无容器无 systemd 的 CI 上被完整覆盖。

#### 取舍

- 探测靠 env 标记,**任何剥离环境的 wrapper 都会误判**;逃生舱是 `--external-supervisor`,
  但要用户自己知道要加。
- 75 这条路依赖 unit 里有 `RestartForceExitStatus=75`。用户手改过 unit(或从旧版继承)就会
  "退 75 → systemd 认为失败 → `Restart=on-failure` 也许没配 → 网关不回来"。
  CLI 侧因此有 `hermes gateway status` 的专门提示,`hermes_cli/gateway.py:3652-3658 @ 863e313`:
```python
    elif active_state == "failed" and exec_main_status == str(
        GATEWAY_SERVICE_RESTART_EXIT_CODE
    ):
        print("  ⚠ Planned restart is stuck in systemd failed state (exit 75)")
```

---

### 1.2 `gateway/restart_loop_guard.py`(150 行)—— 自动续跑的熔断器

#### 问题(模块 docstring 讲得比我好,原文引用)

`gateway/restart_loop_guard.py:1-27 @ 863e313`:
```python
"""Auto-resume restart-loop breaker (#30719, defense-3).

Defenses 1 and 2 (the ``_HERMES_GATEWAY`` guard on ``hermes gateway
stop|restart`` + ``terminal_tool``, and the cron-creation lifecycle
filter) stop the agent from scheduling its own restart via the cron and
CLI paths.  They do NOT cover every SIGTERM source: an agent running a
raw ``terminal("launchctl kickstart -k gui/<uid>/ai.hermes.gateway")``,
an external monitor with a bad trigger, or any other repeated crash can
still drive the supervisor (launchd ``KeepAlive`` / systemd ``Restart=``)
into a tight respawn loop.  On each boot the gateway auto-resumes the
restart-interrupted session, whose next turn re-runs the offending
logic — SIGTERM every ~10 seconds until manually broken.

This module is the last-resort circuit breaker: it records a timestamp
each time the gateway boots with restart-interrupted sessions pending,
keeps a rolling window of recent boots persisted across processes (each
boot is a fresh process, so in-memory state is useless), and reports the
loop as "tripped" once too many such boots happen inside a short window.
When tripped, the caller SKIPS auto-resume for that boot — the gateway
still starts and serves real inbound messages, it just stops replaying
the session that keeps killing it, which breaks the cycle and puts a
human back in the loop.

State lives in ``<HERMES_HOME>/gateway/restart_loop.json`` so it is
profile-scoped and survives process death.  It is intentionally tiny and
best-effort: any read/write failure fails OPEN (no false trip) because a
broken breaker must never wedge a healthy gateway.
"""
```

**故事版(#30719):** 用户让 agent 干点事,agent 在 terminal 工具里跑了
`launchctl kickstart -k gui/501/ai.hermes.gateway` —— 这条命令的字面意思是"踢一下网关服务"。
launchd 照办,给网关发 SIGTERM。网关优雅关闭时把这个"被打断的会话"标记成 `resume_pending`。
launchd 的 `KeepAlive=true` 立刻把网关拉起来。新网关一启动就自动续跑那个 pending 会话 ——
于是 agent 又跑了一遍 `launchctl kickstart`。**约每 10 秒一轮,直到人工介入。**
防线 1(CLI/terminal 上的 `_HERMES_GATEWAY` 标记)和防线 2(cron 创建时的生命周期过滤)
拦得住 `hermes gateway restart`,拦不住 `launchctl` 这种任意 shell。
所以有了防线 3:**不拦命令,拦"自动续跑"这个放大器。**

#### 实现

**计数存哪 —— 任务书让我核实"必然在磁盘",核实结论:是,`<HERMES_HOME>/gateway/restart_loop.json`。**

`gateway/restart_loop_guard.py:47-67 @ 863e313`:
```python
def _state_path():
    return get_hermes_home() / "gateway" / "restart_loop.json"


def _load_boots() -> List[float]:
    try:
        raw = _state_path().read_text(encoding="utf-8")
        data = json.loads(raw)
        boots = data.get("boots", [])
        return [float(t) for t in boots if isinstance(t, (int, float))]
    except (OSError, ValueError, TypeError):
        return []


def _save_boots(boots: List[float]) -> None:
    try:
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"boots": boots}), encoding="utf-8")
    except OSError:
        pass
```
文件内容就是 `{"boots": [<epoch float>, ...]}`。**注意 `_save_boots` 是裸 `write_text`,
不是本仓库别处用的 `atomic_json_write`** —— 断电/kill 恰好落在写中间会留半截 JSON,
但 `_load_boots` 的 `except (OSError, ValueError, TypeError): return []` 会把它当空处理,
即"fail OPEN"。这是刻意的(见下),不是疏漏。

**窗口 / 阈值 / 熔断后做什么。**

`gateway/restart_loop_guard.py:41-44 @ 863e313`:
```python
# Defaults chosen so a legitimate operator restart (or two) never trips the
# breaker, but the documented ~10s respawn loop does within a few cycles.
DEFAULT_MAX_RESTARTS = 3
DEFAULT_WINDOW_SECONDS = 60
```
即 **60 秒内 ≥3 次"带 restart-interrupted 会话的启动"即熔断**。10 秒一轮的循环 3 轮内触发。

窗口是**滑动窗口 + 每次记录时顺手剪枝**,`gateway/restart_loop_guard.py:70-86 @ 863e313`:
```python
def record_restart_interrupted_boot(
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
    *,
    now: Optional[float] = None,
) -> List[float]:
    """Record that the gateway just booted with restart-interrupted sessions.

    Prunes boots older than ``window_seconds`` and appends the current time.
    Returns the pruned+appended list (most recent last).  Best-effort — a
    persistence failure returns the in-memory list without raising.
    """
    ts = time.time() if now is None else now
    cutoff = ts - max(1, window_seconds)
    boots = [t for t in _load_boots() if t >= cutoff]
    boots.append(ts)
    _save_boots(boots)
    return boots
```
`max(1, window_seconds)` 保证窗口至少 1 秒,防止配置 0 导致 cutoff == now 把刚写的也剪掉。

**唯一的生产入口是 `check_and_record`(记录 + 判定合一)**,
`gateway/restart_loop_guard.py:122-150 @ 863e313`:
```python
def check_and_record(
    max_restarts: int = DEFAULT_MAX_RESTARTS,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
    *,
    now: Optional[float] = None,
) -> bool:
    """Record this restart-interrupted boot and report whether the loop is now
    tripped.

    This is the single entry point the gateway calls: it appends the current
    boot, then checks whether the (now-updated) window has reached the
    threshold.  Returns True when auto-resume should be SKIPPED to break the
    loop.
    """
    boots = record_restart_interrupted_boot(window_seconds, now=now)
    tripped = len(boots) >= max_restarts if max_restarts > 0 else False
    if tripped:
        logger.warning(
            "Restart-loop breaker TRIPPED: %d restart-interrupted gateway "
            "boots within %ds (threshold %d). Skipping auto-resume to break "
            "a suspected SIGTERM-respawn loop (#30719). Restart-interrupted "
            "sessions stay resume-pending and will continue on the next real "
            "user message. If this is a false positive, delete %s.",
            len(boots),
            window_seconds,
            max_restarts,
            _state_path(),
        )
    return tripped
```
**熔断后做什么 —— 什么都不停,只跳过这一轮 auto-resume。** 且告警里直接给出自救路径
(删那个 json)。

**接线点。** 只有一处,在枚举完 `resume_pending` 会话之后、真正调度续跑之前,
`gateway/run.py:10491-10509 @ 863e313`:
```python
        # Defense-3 (#30719): break the SIGTERM-respawn loop. Only count this
        # boot when there are restart-interrupted sessions to resume — a clean
        # boot must not accrue toward the breaker. If too many such boots have
        # happened in the configured window, skip auto-resume for THIS boot:
        # the gateway still comes up and serves real inbound messages, it just
        # stops replaying the session that keeps killing it. The session stays
        # resume_pending, so a real user message can still continue it (a human
        # is now in the loop). Defenses 1-2 cover the cron/CLI/terminal paths;
        # this catches every other SIGTERM source (e.g. a raw `terminal(
        # "launchctl kickstart ai.hermes.gateway")`).
        if candidates:
            try:
                from gateway import restart_loop_guard as _rlg

                _max_restarts, _window = self._restart_loop_guard_config()
                if _rlg.check_and_record(_max_restarts, _window):
                    return 0
            except Exception as exc:  # noqa: BLE001 — breaker must fail OPEN
                logger.debug("Restart-loop guard check skipped: %s", exc)
```
`if candidates:` 这一行是核心语义:**干净启动不计数**,只有"这次启动确实有要续跑的被打断会话"
才往窗口里投一票。

阈值可配,`gateway/run.py:7471-7492 @ 863e313`(`gateway.restart_loop_guard.max_restarts` /
`.window_seconds`,`max_restarts <= 0` 关闭);默认值同步写在
`hermes_cli/config_defaults.py:2514-2517 @ 863e313`。

**不要和 respawn_storm 混淆。** 同仓另有一个熔断器,
`gateway/status.py:64-68 @ 863e313` 明确划界:
```python
def _get_starts_log_path() -> Path:
    """Path to the append-only gateway-start ledger used by the respawn-storm
    breaker. Distinct from ``restart_loop.json`` (the auto-resume guard) — no
    collision."""
    return get_hermes_home() / "gateway-starts.log"
```
区别:**respawn_storm 数的是"所有启动",熔断后动作是 `sleep` 一段指数退避再启动
(`gateway/status.py:71-104`);restart_loop_guard 数的是"带待续跑会话的启动",熔断后动作是
跳过 auto-resume,不睡不停。** 一个治"启动太频",一个治"续跑自杀"。
所以"退避"在本模块里**没有** —— 退避是 respawn_storm 的职责。

#### 设计理由

- **fail OPEN 是硬约束**,两处 docstring 都写死了(`:26-27`、`:100-101`):
  "a broken breaker must never wedge a healthy gateway"。所以整个模块没有一处会抛异常,
  调用侧还额外包了一层 `except`(run.py:10508)。
- **`now` 参数可注入**(`:73`、`:93`、`:126`),让测试不依赖真实时钟,
  见 `tests/hermes_cli/test_gateway_restart_loop.py:955-969`。

#### 取舍 / 死代码

- **`is_restart_loop_tripped`(`:89-111`)在生产侧无调用者** —— 全仓 grep(排除 tests)零命中。
  只有测试用它验证"读不写"的语义(`tests/hermes_cli/test_gateway_restart_loop.py:955-962`)。
  属于"为对称性保留的只读变体"。
- **`clear()`(`:114-119`)的 docstring 说 "used on clean shutdown / by tests",
  但生产侧无任何调用者** —— 全仓 grep(排除 tests)零命中。**"clean shutdown 会清计数"是假的。**
  实际后果:一次干净重启后的 60 秒内,旧的 boots 记录仍在;不过因为只有 `candidates` 非空才记录,
  影响有限。记为 ▲6(见 §4)。
- 阈值 3/60s 对**慢启动**的机器不友好:如果网关启动本身要 30 秒,窗口 60 秒里最多也就 2 次启动,
  熔断永远不会触发 —— 熔断器隐含假设了"崩溃循环比启动快"。

---

### 1.3 `gateway/readiness.py`(122 行)—— 就绪探针

#### 问题

控制面(dashboard / 监控 / 另一个容器)需要知道网关"能不能干活",而不只是"进程在不在"。
但这个信息里天然带着**配置值、路径、凭据、异常文本**,一不留神就变成信息泄露面;
而且探针会被**高频轮询**,不能与正常写入争锁、不能泄漏 fd。

#### 「就绪」的定义 —— 六项检查全 ok 才 ok

`gateway/readiness.py:89-119 @ 863e313`:
```python
def collect_runtime_readiness(
    *,
    configured_model: str,
    runtime_status: dict[str, Any] | None,
    active_api_runs: int = 0,
    process_completion_queue_depth: int = 0,
    active_delegations: int = 0,
) -> dict[str, Any]:
    """Return bounded readiness diagnostics without mutating runtime state.

    The detailed health endpoint is authenticated. Even there, probes expose
    status and counts only: never config values, credentials, paths, commands,
    queue payloads, or exception messages.
    """
    home = get_hermes_home()
    runtime = runtime_status if isinstance(runtime_status, dict) else {}
    checks = {
        "state_db": _probe_state_db(home),
        "config": _probe_config(home),
        "model": _check("ok" if str(configured_model or "").strip() else "degraded"),
        "disk": _probe_disk(home),
        "gateway": _probe_gateway(runtime),
        "background_queues": _check(
            "ok",
            active_api_runs=max(0, int(active_api_runs)),
            process_completions=max(0, int(process_completion_queue_depth)),
            active_delegations=max(0, int(active_delegations)),
        ),
    }
    overall = "ok" if all(item.get("status") == "ok" for item in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
```
六项:**state_db 可读 / config 可解析且顶层是 mapping / model 非空 / 磁盘 <90% / 网关状态 ∈
{running, draining} / 后台队列(永远 ok,只报数)**。

只有两种取值:`ok` / `degraded` —— **没有 `fail`,也没有非 200 状态码**。

#### 「与存活区分了吗」—— 分,而且分在两个 endpoint 上

`gateway/platforms/api_server.py:2862-2866 @ 863e313`(liveness):
```python
    async def _handle_health(self, request: "web.Request") -> "web.Response":
        """GET /health — simple health check."""
        return web.json_response(
            {"status": "ok", "platform": "hermes-agent", "version": _hermes_version()}
        )
```
`gateway/platforms/api_server.py:2868-2882 @ 863e313`(readiness,需鉴权):
```python
    async def _handle_health_detailed(self, request: "web.Request") -> "web.Response":
        """GET /health/detailed — rich status for cross-container dashboard probing.

        Returns gateway state, connected platforms, PID, and uptime so the
        dashboard can display full status without needing a shared PID file or
        /proc access.  Requires the same Bearer auth as other API routes.
        """
        auth_err = self._check_auth(request)
        if auth_err:
            return auth_err
```
消费点 `gateway/platforms/api_server.py:2893-2905 @ 863e313`。返回体里
`"status": readiness["status"]`,但 `web.json_response(...)` 没传 `status=` 参数 ——
**degraded 也返 HTTP 200**。这一点官方文档说清楚了(见 §4 的"文档准确"部分)。

#### 「给谁用」

1. **API server 的 `/health/detailed`** —— dashboard 跨容器探测(上面)。
2. **桌面/dashboard 的 `/api/status`** —— 复用其中一个私有探针,
   `hermes_cli/web_server.py:3245-3266 @ 863e313`:
```python
        # Component-level health rollup. Counts and status enums only — this
        # payload is public (PUBLIC_API_PATHS), so no messages, paths, or
        # other detail that could carry secrets. The storage probe reuses the
        # gateway readiness state_db check (read-only, 1s-bounded) in an
        # executor so a wedged DB can't stall the event loop.
        ...
        try:
            from gateway.readiness import _probe_state_db

            storage_check = await asyncio.get_running_loop().run_in_executor(
                None, functools.partial(_probe_state_db, get_hermes_home())
            )
            components["storage"] = {"status": storage_check.get("status", "degraded")}
        except Exception:
            components["storage"] = {"status": "degraded"}
```
**没有任何 k8s probe / systemd 消费者。** systemd 侧的健康完全走 sd_notify(§1.4),
与 readiness.py 无交集。

#### 实现里最值得抄的一段:只读连接 + `closing()`

`gateway/readiness.py:27-45 @ 863e313`:
```python
def _probe_state_db(home: Path) -> dict[str, Any]:
    path = home / "state.db"
    if not path.exists():
        return _check("ok", "not initialized")
    try:
        # A readiness probe must never compete with normal state writers. A
        # read-only schema query still catches unreadable/corrupt databases
        # without taking a write reservation on every health poll.
        # ``closing(...)`` is required: sqlite3's connection context manager
        # only commits/rolls back — it never closes, so a bare ``with
        # sqlite3.connect(...)`` leaks one connection (and its fds) per
        # health poll in the long-running gateway (#69678/#69567 bug class).
        uri = f"file:{path.as_posix()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=1.0)) as conn:
            conn.execute("PRAGMA query_only = ON")
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        return _check("ok")
    except Exception as exc:
        return _check("degraded", type(exc).__name__)
```
三重防护:`mode=ro` URI + `PRAGMA query_only=ON` + `timeout=1.0`。
`#69678/#69567` 那一类 bug = "`with sqlite3.connect(...)` 只提交不关闭",在按秒轮询的
长活进程里就是 fd 泄漏。

**"不泄漏"的纪律在每个 except 分支上都能看到:只回 `type(exc).__name__`,不回 `str(exc)`。**
`:45`、`:58`、`:68` 三处一致。`:58` 稍微多给一点:`f"invalid config ({type(exc).__name__})"`。

`_probe_config` 还检查了顶层类型,`gateway/readiness.py:48-58 @ 863e313`:
```python
def _probe_config(home: Path) -> dict[str, Any]:
    path = home / "config.yaml"
    if not path.exists():
        return _check("ok", "using defaults")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw is not None and not isinstance(raw, dict):
            return _check("degraded", "top level is not a mapping")
        return _check("ok")
```
"文件不存在 = ok(用默认值)"是个刻意的宽松判定 —— 全新安装不该报 degraded。

`_probe_disk` 阈值写死 90%,`gateway/readiness.py:16 @ 863e313` `_DISK_DEGRADED_PERCENT = 90.0`,
`:61-68` 计算并**同时回百分比与剩余字节**(计数,不是路径)。

#### 取舍

- **`_probe_gateway` 的 status 只看 `gateway_state`,不看连上了几个平台**,
  `gateway/readiness.py:71-86 @ 863e313`:
```python
def _probe_gateway(runtime_status: dict[str, Any]) -> dict[str, Any]:
    state = str(runtime_status.get("gateway_state") or "unknown")
    platforms = runtime_status.get("platforms")
    connected = 0
    configured = 0
    if isinstance(platforms, dict):
        configured = len(platforms)
        connected = sum(
            1
            for value in platforms.values()
            if isinstance(value, dict)
            and str(value.get("state") or value.get("status") or "").lower()
            in {"connected", "running", "ok"}
        )
    status = "ok" if state in {"running", "draining"} else "degraded"
    return _check(status, state=state, connected_platforms=connected, platforms=configured)
```
  **一个所有平台都掉线的网关,只要 `gateway_state == "running"`,readiness 仍报 ok。**
  连接数只作为附带计数暴露,判定权留给调用方。web_server 那边就自己另算了一遍
  (`hermes_cli/web_server.py:3267-3280`),把 `platforms` 单列成一个 component。
  → 两个面对同一事实给出的 overall 可能不同。这是刻意的分层还是漂移,代码里没写。
- **`draining` 算 ok**(`:85`)。合理(排水中仍在服务已接的活),但对负载均衡语义有影响:
  正在排水的实例不该再收新流量,而 readiness 说它 ok。目前没人拿它做 LB 摘除,所以不咬人。
- **私有 API 跨模块使用**:`__all__` 只导出一个名字,`gateway/readiness.py:122 @ 863e313`:
```python
__all__ = ["collect_runtime_readiness"]
```
  而 `hermes_cli/web_server.py:3259` 直接 `from gateway.readiness import _probe_state_db`。
  下划线前缀在这里已经不是"私有"了,是事实上的公开契约。记为轻度设计漂移。

---

### 1.4 `gateway/systemd_notify.py`(176 行)—— sd_notify 协议实现

#### 问题

普通的 `Restart=always` 只能救"进程死了"。救不了**"进程还在,但 asyncio 事件循环被卡死"**
—— 这时所有平台适配器、所有 watchdog 线程一起哑掉,但 PID 还在,systemd 觉得一切正常。
sd_notify 的 watchdog 机制就是为这个:进程必须周期性地主动喊"我还在跑",
超过 `WatchdogSec` 不喊,systemd 杀了重启。

#### sd_notify 是什么(锚一次)

systemd 的进程→init 单向通知协议。init 在环境变量 `NOTIFY_SOCKET` 里给出一个 Unix
**数据报**套接字地址,进程往里发形如 `READY=1`、`WATCHDOG=1`、`STOPPING=1`、`STATUS=<文本>`
的换行分隔键值文本。无响应、无握手、发完就走。

#### 实现

**(1) 发送:一次一个 datagram,失败一律吞。**

`gateway/systemd_notify.py:12-39 @ 863e313`:
```python
def _notify_address(raw: str) -> str:
    """Translate systemd's ``@abstract`` notation to Python's address form."""
    return "\0" + raw[1:] if raw.startswith("@") else raw


def notify(message: str) -> bool:
    """Send one nonblocking sd_notify datagram when systemd configured it.

    Notification failures are deliberately non-fatal: a missing socket or an
    older platform must never prevent the gateway from starting.
    """
    address = os.environ.get("NOTIFY_SOCKET", "").strip()
    if not address:
        return False
    if not isinstance(message, str) or not message:
        return False
    if not hasattr(socket, "AF_UNIX"):
        return False
    try:
        payload = message.encode("utf-8")
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sender:
            # A full receiver buffer must not stall the gateway event loop.
            sender.setblocking(False)
            sender.connect(_notify_address(address))
            sender.send(payload)
        return True
    except (OSError, UnicodeError, ValueError):
        return False
```
三个细节:
- `@abstract` → `\0abstract`(第 14 行)。systemd 用 `@` 前缀表示 Linux 抽象命名空间套接字,
  Python 用前导空字节。
- `setblocking(False)` 在 `connect` 之前(第 34 行)。**接收端缓冲区满时不能把网关事件循环拖住** ——
  宁可丢一次心跳。
- **没有 systemd 时怎么降级 —— 三重早退,`return False`,零副作用:**
  `NOTIFY_SOCKET` 未设(第 23-25 行)、消息为空(26-27)、平台无 `AF_UNIX`(Windows,28-29)。
  调用方拿到 `False` 什么都不做。这就是全部降级逻辑。

**(2) 间隔:从 `WATCHDOG_USEC` 读,不自己拍脑袋。**

`gateway/systemd_notify.py:42-57 @ 863e313`:
```python
def watchdog_interval_seconds() -> Optional[float]:
    """Return systemd's configured watchdog interval in seconds."""
    if not os.environ.get("NOTIFY_SOCKET", "").strip():
        return None
    if not hasattr(socket, "AF_UNIX"):
        return None
    raw = os.environ.get("WATCHDOG_USEC", "").strip()
    if not raw:
        return None
    try:
        interval = float(raw) / 1_000_000.0
    except (TypeError, ValueError):
        return None
    if not math.isfinite(interval) or interval <= 0:
        return None
    return interval
```
`enabled` 由「配置开关 AND 拿到了间隔」共同决定,`gateway/systemd_notify.py:77-79 @ 863e313`:
```python
    @property
    def enabled(self) -> bool:
        return self._config_enabled and self.interval_seconds is not None
```

**(3) 三个信号各在何时发。**

| 信号 | 发送点 | 触发时机 |
|---|---|---|
| `READY=1\nSTATUS=<text>` | `SystemdWatchdog.ready()`,`gateway/systemd_notify.py:118-123` | 适配器 + cron + housekeeping 全部就位之后,`gateway/run.py:26935-26940` |
| `WATCHDOG=1` | `record_tick()`,`gateway/systemd_notify.py:137` | 采样循环每 `interval/2` 一次,且**只在事件循环按时醒来时** |
| `STATUS=watchdog unhealthy: …` | `record_tick()`,`gateway/systemd_notify.py:135` | 首次检测到唤醒迟到 |
| `STOPPING=1` | `stop()`,`gateway/systemd_notify.py:174-176` | `_stop_impl` 的**最开头**,排水之前 |

READY 的时序有明确注释,`gateway/run.py:26935-26940 @ 863e313`:
```python
    # READY is emitted only after adapters, cron, and housekeeping have all
    # reached their running boundary. Missing config/systemd runtime state
    # leaves the watchdog disabled without changing gateway behavior.
    start_watchdog = getattr(runner, "_start_systemd_watchdog", None)
    if callable(start_watchdog):
        start_watchdog()
```
`gateway/run.py:12635-12649 @ 863e313`:
```python
    def _start_systemd_watchdog(self) -> bool:
        """Start sd_notify only after a configured gateway is truly running."""
        if not self._running or self.config.systemd_watchdog_seconds <= 0:
            return False
        if self._systemd_watchdog is not None:
            return True

        from gateway.systemd_notify import SystemdWatchdog

        watchdog = SystemdWatchdog(config_enabled=True)
        if not watchdog.start():
            return False
        self._systemd_watchdog = watchdog
        watchdog.ready("Hermes Gateway running")
        return True
```

STOPPING 的时序理由,`gateway/run.py:12651-12652 @ 863e313`:
```python
    async def _stop_systemd_watchdog(self) -> None:
        """Stop heartbeats before any potentially long shutdown drain."""
```
调用位置在 `_stop_impl` 里紧跟 `self._running=False; self._draining=True` 之后,
`gateway/run.py:12804-12806 @ 863e313`:
```python
            stop_watchdog = getattr(self, "_stop_systemd_watchdog", None)
            if callable(stop_watchdog):
                await stop_watchdog()
```
**为什么必须最先发:** 排水可能很久(after-turn 默认 6 小时)。若还在按 `WatchdogSec`
喂心跳,systemd 会以为服务正常运行;若停了心跳却不发 `STOPPING=1`,systemd 会在
`WatchdogSec` 到点时**把正在优雅排水的网关 SIGABRT 掉**。`STOPPING=1` 让 systemd 进入
deactivating 态、关掉 watchdog 计时器,排水才安全。

**(4) 核心巧思:心跳不是"定时发",是"事件循环按时醒来才发"。**

`gateway/systemd_notify.py:125-138 @ 863e313`:
```python
    def record_tick(self, *, scheduled_at: float, now: float) -> bool:
        """Feed systemd only when the event loop woke within its lag budget."""
        if not self.enabled or self._stopping or self._unhealthy:
            return False
        try:
            lag = float(now) - float(scheduled_at)
        except (TypeError, ValueError):
            lag = float("inf")
        if not math.isfinite(lag) or lag > self._lag_tolerance():
            self._unhealthy = True
            notify("STATUS=watchdog unhealthy: event loop progress is late")
            return False
        notify("WATCHDOG=1")
        return True
```
`gateway/systemd_notify.py:140-157 @ 863e313`:
```python
    async def _run(self) -> None:
        interval = self.interval_seconds
        if interval is None:
            return
        cadence = max(0.01, interval / 2.0)
        loop = asyncio.get_running_loop()
        scheduled_at = loop.time() + cadence
        try:
            while not self._stopping and not self._unhealthy:
                await asyncio.sleep(max(0.0, scheduled_at - loop.time()))
                now = loop.time()
                if not self.record_tick(scheduled_at=scheduled_at, now=now):
                    return
                scheduled_at += cadence
                if scheduled_at < now:
                    scheduled_at = now + cadence
        except asyncio.CancelledError:
            return
```
- `cadence = interval/2`(第 144 行)是 sd_notify 的标准做法:按 `WatchdogSec` 的一半喂。
- `scheduled_at` 是**绝对时刻推进**,不是 `sleep(cadence)` —— 所以 `now - scheduled_at`
  正好等于"事件循环晚醒了多少"。
- 容差默认是 interval 的 25%,`gateway/systemd_notify.py:89-100 @ 863e313`:
```python
    def _lag_tolerance(self) -> float:
        interval = self.interval_seconds or 0.0
        configured = self._lag_tolerance_seconds
        if configured is None:
            return max(0.1, interval * 0.25)
```
- **`_unhealthy` 是一个闩锁(latch),一旦置位就不再复位**:`_run` 的循环条件带
  `not self._unhealthy`(第 148 行),`record_tick` 返回 False 后 `_run` 直接 `return`
  (第 151-152 行)。

**这个设计的精髓:检测到"迟到"时,它不去杀自己,而是"停止喂食"并发一条 STATUS 说明原因。**
真正执行处决的是 systemd(`WatchdogSec` 到点)。好处:(a) 处决动作由外部执行,即使
Python 侧已经半死也一定会发生;(b) journal 里留下一句人类可读的原因,而不是一条干巴巴的
"watchdog timeout"。

**(5) `stop()` 的幂等 + 自取消保护。**

`gateway/systemd_notify.py:159-176 @ 863e313`:
```python
    async def stop(self) -> None:
        """Stop feeding systemd and emit ``STOPPING=1`` at most once."""
        self._stopping = True
        task = self._task
        current = asyncio.current_task()
        if task is not None and task is not current:
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self._task = None
        if self.enabled and not self._stopping_notified:
            notify("STOPPING=1")
            self._stopping_notified = True
```
`task is not current`(第 164 行)防的是"采样任务自己调 stop() 把自己 cancel 掉";
`_stopping_notified` 保证 `STOPPING=1` 至多一次。

#### 服务单元侧的联动

开关是 `gateway.systemd_watchdog_seconds`(默认 0 = 关),
`gateway/config.py:931 @ 863e313` `systemd_watchdog_seconds: int = 0`,
归一化函数 `gateway/config.py:153-158 @ 863e313`:
```python
def coerce_systemd_watchdog_seconds(
    value: Any, key: str = "gateway.systemd_watchdog_seconds"
) -> int:
    """Return a bounded positive watchdog interval or zero when disabled.

    Runtime and service generation share this normalization so a value can
    never enable ``Type=notify`` while disabling application heartbeats.
    """
```
**"同一个归一化函数被运行时和 unit 生成器共用"是这里最重要的一致性保证** ——
否则会出现 unit 写了 `Type=notify` 而进程从不发 READY 的死锁(systemd 永远等不到就绪,
`TimeoutStartSec` 到点后杀掉重启,无限循环)。

unit 字段生成:`hermes_cli/gateway.py:2777-2785 @ 863e313`:
```python
def _systemd_watchdog_service_fields(
    hermes_home: str | Path | None = None,
) -> tuple[str, str]:
    """Return systemd service fields for the effective gateway config."""
    seconds = _systemd_watchdog_seconds(hermes_home)
    if seconds <= 0:
        return "simple", ""
    return "notify", f"NotifyAccess=main\nWatchdogSec={seconds}s\n"
```

#### 取舍

- **每发一个 datagram 就新建一个 socket**(`:32`)。默认 `WatchdogSec=120` → 每 60 秒一次,
  开销可忽略;好处是无状态、无需在长活进程里维护 fd。
- **`_unhealthy` 不可恢复**:一次瞬时卡顿(比如一次大 GC、一次同步磁盘 IO 超过 30 秒)
  就会永久停止心跳,必然被 systemd 杀掉。默认容差 = 120 × 0.25 = 30 秒,余量不小,
  但这是"宁杀错不放过"的取向。
- **构造器有 `lag_tolerance_seconds` 参数(`:67`),但生产侧调用点不传**
  (`gateway/run.py:12645`:`SystemdWatchdog(config_enabled=True)`)—— 容差目前**不可配**,
  只有测试用得上(`tests/gateway/test_systemd_notify.py:71`)。

---

### 1.5 `gateway/cgroup_cleanup.py`(81 行)—— 遗留子进程收割

#### 问题(docstring 原文)

`gateway/cgroup_cleanup.py:1-13 @ 863e313`:
```python
"""SIGKILL any process left in this systemd unit's cgroup.

Runs as ``ExecStopPost=`` so it only fires after the gateway's main process
has exited. The gateway already reaps its own tool subprocesses on a clean
shutdown; this is the safety net for long-lived helpers it doesn't track
(``adb``, platform bridges, etc.) that would otherwise be orphaned in the
cgroup and block ``Restart=always`` — issue #37454.

We deliberately iterate ``cgroup.procs`` and send per-PID SIGKILLs instead
of writing ``1`` to ``cgroup.kill``: the original failure mode in #37454
was the kernel returning ``EINVAL`` on the cgroup-wide kill, while per-PID
signal delivery uses a separate code path that still works.
"""
```

**清理什么:** 网关自己不追踪的长活辅助进程 —— `adb`、平台 bridge 之类。
网关的工具子进程在正常关闭时由 `process_registry.kill_all()` 收掉
(`gateway/run.py` 的 `_kill_tool_subprocesses`);这里是**兜底网**。

**为什么需要:** systemd 的 `KillMode=mixed` 只对主进程发 SIGTERM,cgroup 里剩下的进程
要等 `TimeoutStopSec` 到点才被 SIGKILL;更糟的是,只要 cgroup 非空,unit 就停不干净,
`Restart=always` 拉不起新实例 —— 这就是 #37454 的现象。

**cgroup v1 还是 v2:只支持 v2。** `gateway/cgroup_cleanup.py:24-33 @ 863e313`:
```python
def _own_cgroup_path() -> str | None:
    """Return the cgroup v2 path for the calling process, or None."""
    try:
        text = Path("/proc/self/cgroup").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^0::(.+)$", text, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()
```
`^0::` 是 cgroup v2 统一层级在 `/proc/self/cgroup` 里的固定前缀。**纯 v1 的机器匹配不上 →
`None` → `reap_cgroup` 直接 `return 0`**(`:58-59`),静默 no-op。

#### 实现

`gateway/cgroup_cleanup.py:36-72 @ 863e313`:
```python
def _read_cgroup_pids(cgroup_path: str) -> list[int]:
    procs_file = Path(f"/sys/fs/cgroup{cgroup_path}/cgroup.procs")
    try:
        raw = procs_file.read_text(encoding="utf-8")
    except OSError:
        return []
    pids: list[int] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


def reap_cgroup(cgroup_path: str | None = None) -> int:
    """SIGKILL every PID in the cgroup other than the caller. Returns the count killed."""
    if cgroup_path is None:
        cgroup_path = _own_cgroup_path()
    if not cgroup_path:
        return 0
    own = os.getpid()
    killed = 0
    for pid in _read_cgroup_pids(cgroup_path):
        if pid == own:
            continue
        try:
            os.kill(pid, signal.SIGKILL)  # windows-footgun: ok — Linux-only (reads /proc, /sys/fs/cgroup; runs from a systemd unit)
            killed += 1
        except ProcessLookupError:
            continue
        except PermissionError:
            continue
    return killed
```
- 每一步 IO 都有 `except` 兜底,一路降级到 0。
- `pid == own` 是唯一的自保:**ExecStopPost 进程自己也在这个 cgroup 里**。
- `os.kill` 行尾那条 `# windows-footgun: ok` 是仓库自建的静态检查抑制标记
  (全仓有一套 windows-footgun lint),顺带说明了"Linux only"的理由。

**接线:不是 Python import,是 unit 里的一行命令。**
`hermes_cli/gateway.py:2922 @ 863e313`(system unit)与 `:2960`(user unit):
```
ExecStopPost=-{python_path} -m gateway.cgroup_cleanup
```
`-` 前缀 = 失败不影响 stop job。入口 `gateway/cgroup_cleanup.py:75-81 @ 863e313`:
```python
def main() -> int:
    reap_cgroup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```
**`main()` 永远返回 0**,连 `-` 前缀都用不上 —— 双保险。
`reap_cgroup` 的返回值(杀了几个)被丢弃,也不打日志。

#### 取舍

- **只在 systemd 路径生效**。launchd(macOS)与 s6(Docker)的 unit/服务定义里都没有它
  —— 全仓 grep `cgroup_cleanup` 只有那两行 `ExecStopPost`。macOS 侧靠 launchd 自己的
  job 进程组管理;Docker 侧靠容器边界。
- **SIGKILL,不给 SIGTERM 机会**。理由是它只在主进程已经退出之后跑 —— 优雅期已经过了。
- **无日志、无返回值消费**。想知道它杀了什么,只能靠外部观察。
  调试友好度换来了"绝不干扰 stop job"。

---

### 1.6 `gateway/scale_to_zero.py`(124 行)—— 见 §2 专章

见下方 §2(R7 移交项 A5 落地)。

---

### 1.7 `gateway/code_skew.py`(64 行)—— 代码偏斜检测

#### 「代码偏斜」是什么

**运行中进程的 `sys.modules` 与磁盘上的源码不一致。** 具体到 hermes:网关是一个长活单进程,
启动时把模块全部导入并缓存;有人在它底下跑了 `git pull`(手动,或者 `hermes update`
到"已 pull 但还没优雅重启"的那个窗口),磁盘变了,内存没变。

#### 问题(真实事故,讲成故事)

`tests/test_stale_utils_module_import.py:1-21 @ 863e313` 记录了完整因果:
```python
"""Regression for the stale-``utils``-module ImportError after a hot ``git pull``.

Real incident (gateway session 1518671026962174144)::

    Sorry, I encountered an error (ImportError).
    cannot import name 'env_float' from 'utils' (~/.hermes/hermes-agent/utils.py)

Mechanism:

1. A long-running gateway/agent process imported ``utils`` BEFORE ``env_float``
   existed (added in 06ca1e99, 2026-06-20 14:00). The cached module object in
   ``sys.modules`` therefore has no ``env_float`` attribute.
2. ``hermes update`` ran ``git pull``, updating ``utils.py`` (now defining
   ``env_float``) and ~22 consumer modules (now doing ``from utils import
   env_float``) on disk -- WITHOUT restarting the process.
3. Switching the live session's model (anthropic/opus -> opencode/glm) forced the
   FIRST import of a consumer module on the new provider's code path. Its
   top-level ``from utils import env_float`` resolved against the STALE cached
   ``utils`` -> ImportError. The path in parentheses is the consumer-reported
   ``utils.__file__`` on disk (which *does* define ``env_float``), which is why
   the error is so confusing: the file on disk is fine, the in-memory module is not.
```
**一句话复述:** 老进程缓存了旧的 `utils`;`git pull` 之后新的 consumer 模块要
`from utils import env_float`;这个 consumer 只有切模型时才第一次被 import;
于是切模型 → ImportError,而报错里给出的那个文件路径打开一看**明明有** `env_float`。
排查者被彻底误导。

#### 检测什么 / 检测到做什么

`gateway/code_skew.py:1-16 @ 863e313`(模块 docstring):
```python
"""Detect when the gateway is running stale code after a hot ``git pull``.

The gateway is a single long-lived process; its ``sys.modules`` is frozen at
boot. If the checkout is updated underneath it (a manual ``git pull``, or the
window before ``hermes update``'s graceful restart fires), a first-time lazy
import on a new code path can resolve a freshly-pulled consumer module against a
stale cached dependency -> ImportError (see
``tests/test_stale_utils_module_import.py`` for the exact failure).

We snapshot the checkout revision at gateway startup and compare on demand, so
risky callers (e.g. ``/model`` switching) can refuse with a clear "restart the
gateway" message instead of crashing on a cryptic import error.

If the revision can't be read (non-git install, IO error), the boot snapshot
stays ``None`` and skew detection no-ops — it never produces a false positive.
"""
```

**检测的是 git checkout 指纹(不是文件 mtime、不是模块哈希)。**
`gateway/code_skew.py:22-45 @ 863e313`:
```python
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_boot_fingerprint: str | None = None


def _fingerprint() -> str | None:
    """Current checkout fingerprint, reusing the CLI's git-rev reader.

    ``hermes_cli.main`` is always already imported in a gateway process (it's
    the entry point), so this import is free and avoids duplicating the
    worktree-aware ref resolution.
    """
    try:
        from hermes_cli.main import _read_git_revision_fingerprint

        return _read_git_revision_fingerprint(_PROJECT_ROOT)
    except Exception:
        return None


def record_boot_fingerprint() -> None:
    """Snapshot the checkout revision at gateway startup (idempotent)."""
    global _boot_fingerprint
    if _boot_fingerprint is None:
        _boot_fingerprint = _fingerprint()
```
指纹格式是 `git:<ref>:<sha>`,由 `hermes_cli/main.py:838-879 @ 863e313`
的 `_read_git_revision_fingerprint` 生成 —— **不 spawn git**,直接读
`.git/HEAD` → 解析 `ref:` → 读松散 ref 或 `packed-refs`,还处理了
worktree 的 `commondir` 间接(`hermes_cli/main.py:848-857`)。读不到时返回
`git:<ref>:unresolved` 或 `None`。

**快照点在 `start_gateway` 的第一行代码**,`gateway/run.py:26374-26379 @ 863e313`:
```python
    # Snapshot the checkout revision now, while sys.modules still matches disk,
    # so a later `git pull` under this long-lived process can be detected (and
    # risky work like model switching refused) instead of crashing on a stale
    # in-memory module.
    from gateway.code_skew import record_boot_fingerprint
    record_boot_fingerprint()
```
"趁 `sys.modules` 还与磁盘一致时快照"—— 这个时序理由是整个机制的地基。

**比较:** `gateway/code_skew.py:56-64 @ 863e313`:
```python
def detect_code_skew() -> tuple[str, str] | None:
    """Return ``(boot_rev, disk_rev)`` short labels if the checkout drifted
    since boot, else ``None``."""
    if _boot_fingerprint is None:
        return None
    current = _fingerprint()
    if current is None or current == _boot_fingerprint:
        return None
    return _short(_boot_fingerprint), _short(current)
```
三处 `return None` 就是"绝不误报"的三重闸门:没快照 / 读不到当前 / 一致。

**检测到做什么:拒绝一次 `/model` 切换,给出人话。**
`gateway/slash_commands.py:72-98 @ 863e313`:
```python
def _model_switch_skew_guard() -> Optional[str]:
    """Refuse a model switch when the gateway is running stale code.

    A long-lived gateway holds its modules in memory from boot. If the checkout
    changed underneath it (e.g. a manual ``git pull``), switching models can hit
    a first-time lazy import on a new code path and crash on a stale cached
    dependency — the cryptic ``cannot import name 'env_float' from 'utils'``.
    Detect the drift and tell the user to restart instead.

    Intentionally scoped to model switching — the known, highest-risk trigger.
    Any first-time lazy import on a stale process is technically exposed; we
    don't guard every import site, only this one.
    """
    from gateway.code_skew import detect_code_skew

    skew = detect_code_skew()
    if not skew:
        return None
    boot_rev, disk_rev = skew
    return t(
        "gateway.model.error_prefix",
        error=(
            f"This gateway is running code from {boot_rev} but the checkout on "
            f"disk is now {disk_rev}. Switching models would risk a stale-module "
            f"crash — restart the gateway to load the new code: hermes gateway restart"
        ),
    )
```
两个调用点:`gateway/slash_commands.py:1816`(picker 回调路径)与 `:2124`(直接
`/model <name>` 路径)。

#### 设计理由

- **"守一个点,不守所有点"是明写的取舍**(docstring 第 82-84 行:"Intentionally scoped to
  model switching — the known, highest-risk trigger… we don't guard every import site")。
  切模型是唯一被观测到会踩雷的高危动作,守它性价比最高。
- **复用 CLI 已有的 git 读取器**而不是新写一个(`:29-31` 的理由:入口进程里 `hermes_cli.main`
  一定已导入,所以 import 是免费的,还白拿了 worktree 支持)。
- **模块级全局 + 幂等**(`:41-45`)。整个模块没有磁盘状态 —— 因为它要检测的就是"本进程的
  内存 vs 磁盘",跨进程状态在这里毫无意义。这与 restart_loop_guard 恰好相反(那个必须落盘),
  两者对照很能说明"状态放哪"该由问题决定。

#### 取舍 / 边界

- **只认 git 提交,不认未提交的编辑。** `vim` 改一个文件保存(不 commit),指纹不变,
  skew 检测不出来 —— 而这种改动同样会造成 stale-module 崩溃。
- **`_short` 只取 sha 后段**,`gateway/code_skew.py:48-53 @ 863e313`:
```python
def _short(fingerprint: str) -> str:
    """Render a ``git:<ref>:<sha>`` fingerprint as a compact label."""
    sha = fingerprint.rsplit(":", 1)[-1]
    if sha and sha != "unresolved" and len(sha) > 10:
        return sha[:10]
    return sha or fingerprint
```
  比较用的是**完整指纹**(含 ref),展示用的是 **sha 前 10 位**。
  边角:如果只换了分支名而 sha 不变(`git checkout -b same-sha`),
  `detect_code_skew` 会判定漂移,但给用户的消息里两个标签**完全一样**
  ("running code from abc1234567 but the checkout on disk is now abc1234567"),读起来像 bug。
- **非 git 安装完全无保护**(pip wheel 安装、Docker 镜像内),`_fingerprint()` 返回 `None`,
  快照为 `None`,永远不报。这是刻意的 fail-open。

---

## 2. R7 移交项 A5 落地:`gateway/scale_to_zero.py` 本体证据链

### 2.0 场景先行:一台一直在烧钱的空闲机器

一个托管在 Fly.io 上的 hermes 实例,用户只通过 relay(Nous 的中继连接器)跟它说话。
它一天里可能只有 20 分钟在干活,剩下 23 小时 40 分钟在等消息 —— 但机器一直开着,一直计费。
理想状态:**空闲 5 分钟就把机器挂起(suspend),有消息进来时被唤醒。**

难点在于:网关和中继之间是一条长连 WebSocket。机器一挂起,socket 就断了,期间发来的消息
去哪?谁来叫醒它?怎么保证"叫醒时没丢消息"?

答案是把职责切成两半:
- **PRIMITIVES(原语,relay 侧,已存在)** —— 缓冲翻转、按实例的持久缓冲、wakeUrl 戳、
  重连监督者。写在 `docs/relay-connector-contract.md` 的 §3.2/§3.3。
- **BEHAVIOUR(行为,网关侧,就是本文件)** —— **决定**什么时候睡。

`gateway/scale_to_zero.py:1-27 @ 863e313`(模块 docstring 全文,它自己把这层关系讲得最清楚):
```python
"""Scale-to-zero idle detection + dormant-quiesce for the gateway (Phase 0).

This is the gateway-side BEHAVIOUR layer that consumes the relay scale-to-zero
PRIMITIVES (gateway-gateway Phase 5: the buffered-flip, the durable per-instance
buffer, the wakeUrl poke, the reconnect supervisor). It owns the *decision* to go
idle and drives the relay transport's ``go_dormant()`` (D12) — it does NOT itself
suspend the machine. On Fly, the now-traffic-idle machine is suspended by
``autostop:"suspend"`` and woken by autostart-on-wakeUrl (decisions.md Q3=C′).

Design constraints (decisions.md):
  - Per-instance enable is gated SOLELY by the NAS "Labs" toggle, carried to the
    gateway as the ``HERMES_SCALE_TO_ZERO`` env stamp (D11/Q8=A). NOT a user
    config key; ``scale_to_zero.idle_timeout_minutes`` IS config.yaml (D2).
  - Arm only when messaging is relay-only or absent (D1/F6) AND a wakeUrl is
    registered (§3.4(1)) AND the flag is set.
  - Idle = no in-flight agent turn AND no inbound for N min AND no live
    background work (D2/D3/F7).
  - The quiesce uses ``go_dormant()`` (socket closed + supervisor preserved),
    NEVER the stop/restart drain or ``disconnect()`` (F12/F14). The process stays
    alive; Fly freezes+resumes it.
  - ``mark_resume_pending`` is deliberately NOT called here (D13 — suspend
    preserves RAM; revive only if we move to autostop:"stop" or see kills).

The pure helpers (``parse_idle_timeout_seconds``, ``scale_to_zero_enabled``,
``messaging_is_relay_only_or_absent``, ``is_idle``, ``should_arm``) take plain
inputs so they unit-test without a live gateway.
"""
```

**注意 docstring 里满地的 `D11/Q8=A`、`F6`、`§3.4(1)` —— 这些指向的是
`~/nous/specs/scale-to-zero/decisions.md`,一份不在本仓库里的外部设计文档
(`find . -name decisions.md` 零命中)。只有 `§3.4(x)` 能在仓内溯源到
`docs/relay-connector-contract.md:333-382`。** 这是本簇最大的可追溯性缺口,记为 ◇7(见 §4)。

### 2.1 逐函数

#### (a) `scale_to_zero_enabled` —— 唯一的开关来源是 env 挂牌

`gateway/scale_to_zero.py:34-51 @ 863e313`:
```python
# Env flag stamped by NAS when the scaleToZero Labs toggle is on (D11/Q8=A),
# mirroring how the `relay` feature stamps GATEWAY_RELAY_URL. Truthy values only.
SCALE_TO_ZERO_ENV = "HERMES_SCALE_TO_ZERO"

# config.yaml default (D2). Behavioural setting -> config, not env.
DEFAULT_IDLE_TIMEOUT_MINUTES = 5

_TRUTHY = {"1", "true", "yes", "on"}


def scale_to_zero_enabled(environ: Optional[dict] = None) -> bool:
    """Whether the per-instance Labs toggle is on (the HERMES_SCALE_TO_ZERO stamp).

    D11/Q8=A: this env flag is the SOLE per-instance enable signal reaching the
    gateway. Absent/blank/falsey -> disabled (fail-safe default off).
    """
    env = environ if environ is not None else os.environ
    return str(env.get(SCALE_TO_ZERO_ENV, "")).strip().lower() in _TRUTHY
```
**为什么开关是 env 而不是 config key:** 这是"托管方(NAS)控制的实例级能力",
不是"用户偏好"。用户改 config.yaml 不该能给自己开一个会挂起机器的功能。
`environ` 形参可注入(第 44 行)—— 又一个"为可测性开口"的例子。

#### (b) `parse_idle_timeout_seconds` —— 行为参数才进 config

`gateway/scale_to_zero.py:54-69 @ 863e313`:
```python
def parse_idle_timeout_seconds(
    cfg_value: Any, default_minutes: int = DEFAULT_IDLE_TIMEOUT_MINUTES
) -> float:
    """Coerce ``scale_to_zero.idle_timeout_minutes`` (config.yaml, D2) to seconds.

    Degrades to the default on any non-numeric / non-positive value (never raises,
    never returns <= 0 — a zero/negative timeout would make the gateway go dormant
    instantly, which is never the intent).
    """
    try:
        minutes = float(cfg_value)
    except (TypeError, ValueError):
        minutes = float(default_minutes)
    if minutes <= 0:
        minutes = float(default_minutes)
    return minutes * 60.0
```
**关键差异:这里 `0` 明确不是"禁用",而是"回落到默认"**(第 67-68 行)。
理由写在 docstring:0 会让网关"立刻休眠",这绝不可能是任何人的本意。
对比 §1.1 里 `parse_restart_after_turn_timeout` 把 `0` 当作显式禁用 ——
**同一仓库里 `0` 的语义按机制而定,各自在 docstring 里交代。** 这个自觉值得学。

#### (c) `messaging_is_relay_only_or_absent` —— 结构性前置条件

`gateway/scale_to_zero.py:72-88 @ 863e313`:
```python
def messaging_is_relay_only_or_absent(platforms: Iterable[Any]) -> bool:
    """True iff the only connected messaging platform is RELAY, or there is none
    (a Chronos-only / no-platform agent) — the F6/D1 structural precondition.

    A directly-connected platform (Discord/Telegram/Slack/...) holds a live
    socket and cannot scale to zero, so its presence disarms the feature. We
    compare by the platform's ``.value``/name to avoid importing the enum here
    (keeps this module import-light and unit-testable).
    """
    names = {_platform_name(p) for p in platforms}
    names.discard("relay")
    return len(names) == 0


def _platform_name(platform: Any) -> str:
    value = getattr(platform, "value", platform)
    return str(value).strip().lower()
```
**为什么必须 relay-only:** Discord/Telegram 各自持一条到自家服务器的长连。机器一挂起,
那条连接就断,平台侧会认为 bot 掉线;而且没有任何"缓冲 + 唤醒"原语给它们。
只有 relay 通道做了缓冲翻转 + wakeUrl 戳,才能安全地睡。

`_platform_name` 用 duck typing 读 `.value`(第 87 行)而不 import `Platform` 枚举 ——
docstring 直说理由是"keeps this module import-light and unit-testable"。
测试里的 stand-in 就是个三行的类(`tests/gateway/test_scale_to_zero.py:44-48`)。

#### (d) `should_arm` —— relay-only 特判解决的真实故障

`gateway/scale_to_zero.py:91-104 @ 863e313`:
```python
def should_arm(
    *,
    enabled: bool,
    relay_only_or_absent: bool,
    wake_url: Optional[str],
) -> bool:
    """Whether to start the idle watcher at all (D1/D11/§3.4(1)).

    ALL must hold: the Labs flag is on, messaging is relay-only/absent, and a
    wakeUrl is registered (a suspended instance with no reachable wake target is
    a black hole — §3.4(1)). Any unmet -> the watcher never starts (no idle
    timer, no dormancy), so a non-opted instance behaves exactly as today.
    """
    return bool(enabled) and bool(relay_only_or_absent) and bool(wake_url)
```
三个 `and`,`wake_url` 用真值判断(`""` 和 `None` 都不算)。

**"relay-only 特判解决了什么真实故障" —— 任务书问的这个,答案不在 `should_arm` 里,
而在它的调用点。故事如下:**

`gateway/run.py:7494-7528 @ 863e313`:
```python
    def _scale_to_zero_should_arm(self) -> bool:
        """Whether to start the idle watcher (D1/D11/§3.4(1))."""
        from gateway.relay import relay_wake_url
        from gateway.scale_to_zero import (
            messaging_is_relay_only_or_absent,
            scale_to_zero_enabled,
            should_arm,
        )

        try:
            # Only ENABLED platforms count. `config.platforms` is pre-seeded with a
            # disabled placeholder PlatformConfig for every KNOWN platform (telegram,
            # discord, slack, …), so `.keys()` is the full ~20-entry catalog regardless
            # of what this instance actually runs. Passing the bare keys made
            # `messaging_is_relay_only_or_absent` see those placeholders as live
            # direct-socket platforms and return False, so scale-to-zero NEVER armed on
            # a real relay-only instance. Mirror the connect loop, which already gates on
            # `platform_config.enabled` (see the `if not platform_config.enabled: continue`
            # in the adapter-connect loop) — arm off the same notion of "active platform."
            platforms = (
                [p for p, pc in self.config.platforms.items() if getattr(pc, "enabled", False)]
                if self.config
                else []
            )
        except Exception:  # noqa: BLE001
            platforms = []
        try:
            wake_url = relay_wake_url()
        except Exception:  # noqa: BLE001
            wake_url = None
        return should_arm(
            enabled=scale_to_zero_enabled(),
            relay_only_or_absent=messaging_is_relay_only_or_absent(platforms),
            wake_url=wake_url,
        )
```

**故事:什么输入 → 什么现象 → 为什么 → 怎么修。**
- **输入:** 一台真真正正只跑 relay 的实例,Labs 开关已打开,wakeUrl 已注册。
- **现象:** scale-to-zero **从来不 arm**。机器 24 小时不睡,一分钱没省,而且日志里什么都没有。
- **为什么:** `GatewayConfig.platforms` 是一个**预填字典** —— 它给每个**已知**平台
  (telegram、discord、slack…约 20 个)都预置了一个 `enabled=False` 的占位
  `PlatformConfig`。所以 `self.config.platforms.keys()` 永远是那 20 个名字的全集,
  跟这台机器实际跑什么毫无关系。把裸 keys 传进 `messaging_is_relay_only_or_absent`,
  它看到 `{telegram, discord, slack, ...}`,discard 掉 "relay" 之后还剩 19 个,
  `len(names) == 0` 为假 → 返回 False → `should_arm` 永远 False。
- **怎么修:** 在**调用点**过滤 `pc.enabled`,与适配器连接循环用同一套"什么算活跃平台"的定义。
  纯函数 `messaging_is_relay_only_or_absent` 本身没改 —— 它的契约一直是"传给我实际在跑的平台"。

**这个 bug 的教训值得单独记:纯函数把"输入正确"的责任推给了调用方,而调用方手边最顺手的
那个数据结构(`config.platforms`)恰好不是它以为的东西。可测性换来了一个契约缝隙。**

修复的第二半是**可观测性**:加了一条"opted-in 但没 arm"的 INFO 日志,
`gateway/run.py:7530-7573 @ 863e313`(节选 docstring 与日志):
```python
    def _log_scale_to_zero_not_armed_reason(self) -> None:
        """Log why the idle watcher did NOT arm — but only for an OPTED-IN instance.

        A non-opted instance (no HERMES_SCALE_TO_ZERO stamp) not arming is the normal
        case and must stay silent. When the Labs stamp IS set but the watcher still
        didn't arm, that's the surprising case worth one INFO line so "why won't it
        suspend/wake?" is a log grep, not a box-dive.
        """
```
```python
            logger.info(
                "scale-to-zero: NOT armed despite opt-in — "
                "relay_only_or_absent=%s (enabled platforms=%s), wake_url=%s. "
                "Need relay-only messaging + a registered wake URL.",
                relay_only,
                active or "none",
                "set" if wake_url else "MISSING",
            )
```
(`gateway/run.py:7564-7571 @ 863e313`)
**"沉默的 False 是最贵的 bug"** —— 这条日志就是为了让下一次同类问题变成一次 grep。
注意它同样只在 opted-in 时才出声(`:7546-7547` 的 `if not enabled: return`),
否则 99% 的实例每次启动都会打一条无意义的 INFO。

#### (e) `is_idle` —— 三个合取项

`gateway/scale_to_zero.py:107-124 @ 863e313`:
```python
def is_idle(
    *,
    running_agent_count: int,
    seconds_since_last_inbound: float,
    idle_timeout_seconds: float,
    has_live_background_work: bool,
) -> bool:
    """The idle predicate (D2/D3/F7). Pure — composes the three conjuncts.

    Idle iff: no in-flight agent turn, no inbound within the timeout window, and
    no live background work (backgrounded delegate_task / kanban / bg terminal).
    Any active work keeps the gateway awake — suspending mid-flight would lose it.
    """
    if running_agent_count > 0:
        return False
    if has_live_background_work:
        return False
    return seconds_since_last_inbound >= idle_timeout_seconds
```
`>=` 是边界内的(测试明确覆盖:`tests/gateway/test_scale_to_zero.py:87-89`
`test_idle_exactly_at_threshold`)。

### 2.2 为什么抽成无副作用纯函数 —— 三条证据,不是猜的

1. **模块 docstring 自己说了**,`gateway/scale_to_zero.py:24-26 @ 863e313`:
```python
The pure helpers (``parse_idle_timeout_seconds``, ``scale_to_zero_enabled``,
``messaging_is_relay_only_or_absent``, ``is_idle``, ``should_arm``) take plain
inputs so they unit-test without a live gateway.
```
2. **run.py 侧的分区注释也说了**,`gateway/run.py:7423-7428 @ 863e313`:
```python
    # ── scale-to-zero idle detection / dormant-quiesce (Phase 0) ──────────────
    # The gateway-side BEHAVIOUR that consumes the relay scale-to-zero primitives
    # (gateway-gateway Phase 5). Pure logic lives in gateway/scale_to_zero.py; the
    # methods here bind it to the live runner/transport. See ~/nous/specs/
    # scale-to-zero (decisions.md) for the design + the F12/F14 distinctions.
```
3. **测试文件的开头把这条设计当作前提写进了 docstring**,
   `tests/gateway/test_scale_to_zero.py:1-7 @ 863e313`:
```python
"""Unit tests for the scale-to-zero idle-detection pure logic (Phase 0).

Behaviour-contract tests (AGENTS.md): each conjunct of the idle predicate and
each clause of the arm-gate is exercised independently, not frozen against a
snapshot. The pure helpers in gateway/scale_to_zero.py take plain inputs so they
test without a live gateway.
"""
```

**所以答案是明确的"是,为了可测性"** —— 而且是"每个合取项独立可翻转"这种粒度的可测性。
`gateway/run.py` 是 27000 行的单文件;把 5 个判定挪出来意味着这 5 个判定可以在 3 秒内
跑 12 个用例(实测 `tests/gateway/test_scale_to_zero.py` 12 passed / 3.37s),
而不需要 boot 一个网关。

**但这个切分也是本轮最大 bug 的温床 —— 见 §2.5。**

### 2.3 纯函数与 run.py 调用点的配合(完整接线图)

| scale_to_zero.py 纯函数 | run.py 绑定方法 | 绑定做了什么 |
|---|---|---|
| `scale_to_zero_enabled()` | `_scale_to_zero_should_arm` `run.py:7525` / `_log_..._reason` `run.py:7545` | 直接调用,读真实 `os.environ` |
| `messaging_is_relay_only_or_absent()` | 同上 `run.py:7527` / `run.py:7559` | **过滤 `pc.enabled`** 后再传(见 §2.1(d)) |
| `should_arm()` | `_scale_to_zero_should_arm` `run.py:7524-7528` | 补上 `relay_wake_url()`(`gateway/relay/__init__.py:228`) |
| `parse_idle_timeout_seconds()` | `_scale_to_zero_idle_timeout_seconds` `run.py:7457-7469` | 从 `config.yaml` 的 `gateway.scale_to_zero.idle_timeout_minutes` 取原值 |
| `is_idle()` | `_scale_to_zero_is_idle` `run.py:7576-7584` | 补上四个实时量 |

`gateway/run.py:7576-7584 @ 863e313`:
```python
    def _scale_to_zero_is_idle(self) -> bool:
        from gateway.scale_to_zero import is_idle

        return is_idle(
            running_agent_count=self._running_agent_count(),
            seconds_since_last_inbound=time.time() - self._last_inbound_at,
            idle_timeout_seconds=self._scale_to_zero_idle_timeout_seconds(),
            has_live_background_work=self._scale_to_zero_has_live_background_work(),
        )
```

**时钟从哪来:** `_last_inbound_at` 在构造时初始化为 `time.time()`
(`gateway/run.py:6252 @ 863e313`),只被"真实用户 inbound"更新,
`gateway/run.py:14391-14398 @ 863e313`:
```python
        # scale-to-zero (Phase 0, 0.B/F13): stamp the gateway-scoped last-inbound
        # clock for real (user-originated) inbound only. Internal/system events
        # (background-process completions, startup-restore replays) are NOT
        # traffic — counting them would keep a genuinely idle gateway awake. This
        # clock is what the idle predicate (gateway/scale_to_zero.is_idle) reads.
        if not is_internal:
            self._scale_to_zero_note_real_inbound()
```

**"活工作"三查:** `gateway/run.py:7429-7455 @ 863e313`:
```python
    def _scale_to_zero_has_live_background_work(self) -> bool:
        """Live background work that must block a suspend (D3/F7).

        Backgrounded delegate_task / kanban / terminal(background=true) are NOT
        counted by _running_agent_count(), but suspending mid-flight loses them.
        Checks the runner's own tracked tasks + the process registry's running
        processes + any pending process-completion watchers.
        """
        if any(not t.done() for t in self._background_tasks):
            return True
        try:
            from tools.async_delegation import active_count

            if active_count() > 0:
                return True
        except Exception:  # noqa: BLE001 - never let the idle check raise
            logger.debug("scale-to-zero async-delegation check failed", exc_info=True)
        try:
            from tools.process_registry import process_registry

            if process_registry.has_any_active():
                return True
            if process_registry.pending_watchers:
                return True
        except Exception:  # noqa: BLE001 - never let the idle check raise
            logger.debug("scale-to-zero bg-work check failed", exc_info=True)
        return False
```

**arm 点:** `gateway/run.py:11539-11552 @ 863e313`(前面已全文引用)。

**watcher:** `gateway/run.py:7611-7667 @ 863e313`,docstring 把 D12/F12/F14 三条讲全:
```python
    async def _scale_to_zero_watcher(self, interval: float = 30.0) -> None:
        """Watch for idle and drive the relay dormant so the platform can suspend.

        Started ONLY when _scale_to_zero_should_arm() (opted in via the Labs
        HERMES_SCALE_TO_ZERO stamp + relay-only/absent messaging + a wakeUrl).
        On a sustained idle window it runs the DORMANT sequence (D12/F12/F14):
          - mark runtime status `draining` (composes with the existing state
            machine, §3.4(6); does NOT set _running=False),
          - relay adapter.go_dormant() — going_idle->ack + supervisor-preserving
            socket close (NOT disconnect(), NOT the run.py stop path),
          - deliberately NO mark_resume_pending (D13 — suspend preserves RAM).
        The process stays alive; the platform (Fly autostop:"suspend") suspends
        the now-traffic-idle machine and autostart wakes it on the wakeUrl poke,
        at which point the preserved reconnect supervisor re-dials and the
        connector drains the buffered backlog. After driving dormant we set a
        re-arm cooldown so a wake's drained backlog isn't immediately re-quiesced.
        """
        await asyncio.sleep(min(interval, 30.0))  # let startup settle
        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    return
                if time.time() < self._scale_to_zero_cooldown_until:
                    continue
                if not self._scale_to_zero_is_idle():
                    continue
                adapter = self._relay_adapter_for_dormancy()
                if adapter is None:
                    continue
                go_dormant = getattr(adapter, "go_dormant", None)
                if not callable(go_dormant):
                    continue
```
落地动作 `gateway/run.py:7645-7662 @ 863e313`:
```python
                logger.info(
                    "scale-to-zero: gateway idle for >= %.0fs — going dormant "
                    "(relay buffered, socket closed, awaiting platform suspend)",
                    self._scale_to_zero_idle_timeout_seconds(),
                )
                try:
                    self._update_runtime_status("draining")
                except Exception:  # noqa: BLE001 - status is best-effort
                    logger.debug("scale-to-zero: status mark failed", exc_info=True)
                try:
                    result = go_dormant()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:  # noqa: BLE001 - dormancy is best-effort
                    logger.debug("scale-to-zero: go_dormant failed", exc_info=True)
                # 0.F: after a wake the drained inbound updates _last_inbound_at,
                # but give it a window so we don't immediately re-go-dormant on the
                # same idle reading before traffic lands.
                self._scale_to_zero_cooldown_until = time.time() + max(interval, 60.0)
```

**唤醒后的状态复原:** `gateway/run.py:7586-7601 @ 863e313`:
```python
    def _scale_to_zero_note_real_inbound(self) -> None:
        """Stamp real inbound and restore lifecycle after a dormant wake.

        The watcher marks runtime status `draining` as it quiesces the relay, but
        dormancy is not the stop/restart drain path: the process remains alive and
        should present as running once real traffic wakes it and re-enters the
        gateway. Internal completion/replay events intentionally do not call this
        helper, so they do not keep an otherwise idle gateway awake.
        """
        self._last_inbound_at = time.time()
        if getattr(self, "_scale_to_zero_cooldown_until", 0.0) > 0:
            try:
                self._update_runtime_status("running")
            except Exception:  # noqa: BLE001 - status restoration is best-effort
                logger.debug("scale-to-zero: status restore failed", exc_info=True)
            self._scale_to_zero_cooldown_until = 0.0
```

**下游 `go_dormant` 与 `disconnect` 的区别(F12/F14 的落点)**,
`gateway/relay/adapter.py:872-884 @ 863e313`:
```python
    async def go_dormant(self) -> bool:
        """Quiesce the relay for a scale-to-zero suspend (D12 / Phase 0).

        Unlike ``disconnect()`` (terminal teardown for shutdown/restart), this
        keeps the adapter's reconnect path armed so the gateway re-dials and
        drains its buffered backlog when the machine wakes. Delegates to the
        transport's ``go_dormant()`` when available; a transport without it (the
        stub) is a no-op that returns False, so callers degrade safely.

        NOTE: deliberately does NOT stop the revocation monitor — going dormant
        is not a teardown; the monitor stays live so a real opt-out/revocation
        during dormancy is still surfaced on wake.
        """
```

### 2.4 契约对照:relay 合同的 6 条义务 vs 代码

`docs/relay-connector-contract.md:333-382 @ 863e313` 列了行为层必须遵守的 6 条。逐条核对:

| 义务(合同原文要点) | 代码落点 | 状态 |
|---|---|---|
| §3.4(1) 挂起前必须已注册 wakeUrl,否则是黑洞 | `should_arm` 第三个合取项 `scale_to_zero.py:104`;取值 `gateway/relay/__init__.py:228` | ✅ |
| §3.4(2) 必须 `going_idle` → 等 ack 再关 socket | 委托给 transport,`gateway/relay/ws_transport.py:634` `go_dormant` | ✅(在原语侧) |
| §3.4(3) 重连循环必须保持存活 | `adapter.go_dormant` docstring 明写 "keeps the adapter's reconnect path armed"(`adapter.py:875-877`) | ✅ |
| §3.4(4) 健康模型必须区分"挂起"与"宕机" | **代码里找不到落点。** watcher 只把 runtime status 标成 `draining`(`run.py:7651`);readiness 把 `draining` 判为 ok(`readiness.py:85`),算是被动满足 | ⚠️ 无显式实现 |
| §3.4(5) 唤醒戳是尽力而为,不可假定即时 | watcher 的 cooldown(`run.py:7662`)与"重连时必然 drain"的兜底 | ✅ |
| §3.4(6) 必须与既有 drain 状态机组合,不另起并行路径 | `run.py:7614-7619` docstring 明确引用 §3.4(6),用 `_update_runtime_status("draining")` 而不是 `_running=False` | ✅ |

**合同本身仍把行为层称为 "future"**(`docs/relay-connector-contract.md:302-303`:
"a future scale-to-zero behaviour layer";`:333` 标题 "Obligations on a **future** scale-to-zero
behaviour layer"),而代码已经实现了。记为 ▲7(见 §4)。

### 2.5 ★ 本轮最重发现:`_scale_to_zero_has_live_background_work` 在生产环境恒为 True

**纯函数没问题,绑定有问题。**

`gateway/run.py:7437 @ 863e313` 的第一查:
```python
        if any(not t.done() for t in self._background_tasks):
            return True
```

但 `self._background_tasks` **不是"工作任务集合",而是"受监督的常驻守护任务注册表"**。
`gateway/run.py:11601-11611 @ 863e313`:
```python
        if getattr(self, "_background_tasks", None) is None:
            self._background_tasks = set()

        # Monotonic spawn timestamp captured per spawn: the ``_done`` callback
        # uses it to distinguish a rapid crash-loop from a healthy-run-then-crash.
        _started = time.monotonic()

        # Deliberately do NOT pass name= to create_task — some test doubles mock
        # create_task with a signature that rejects the name kwarg.
        task = asyncio.create_task(coro_factory())
        self._background_tasks.add(task)
```

网关启动时通过 `_spawn_supervised` 往里塞了至少 8 个**永不结束**的 watcher:
`gateway/run.py:11475`(session_expiry)、`:11479`(session_stall)、`:11484`(kanban_notifier)、
`:11490`(kanban_dispatcher)、`:11515`(reconnect)、`:11525`(handoff)、
`:11531`(async_delegation)、`:11560`(drain_control)。

**而 scale-to-zero watcher 自己也是用 `_spawn_supervised` 起的**,
`gateway/run.py:11545 @ 863e313`:
```python
                self._spawn_supervised(self._scale_to_zero_watcher, "scale_to_zero_watcher")
```

**结论:一旦 arm 成功,watcher 自身就是 `_background_tasks` 里一个永远 `not done()` 的成员,
`_scale_to_zero_has_live_background_work()` 恒返回 True,`is_idle()` 恒返回 False
(`scale_to_zero.py:121-122`),网关永远不会 go dormant。** 就算把 watcher 自己排除掉,
另外 8 个常驻 watcher 也会把它钉死在 True。

**实证(在基线仓库上跑真实代码,未修改任何文件):**
```
$ /home/user/hermes-venv/bin/python <脚本:GatewayRunner.__new__ + _spawn_supervised 一个长活协程>
before spawn: False
after  spawn: True
bg tasks: 1
```
脚本逻辑:构造裸 `GatewayRunner`,`_background_tasks = set()`,先调
`_scale_to_zero_has_live_background_work()` 得 `False`;用真实的 `r._spawn_supervised(...)`
起一个 `while r._running: await asyncio.sleep(0.01)` 的协程(即 watcher 的形状),
再调同一方法得 `True`。

**为什么测试没抓到:** `tests/gateway/test_scale_to_zero_watcher.py:38` 把
`r._background_tasks = set()` 设为空集,并且在 watcher 测试里直接
monkeypatch 掉了 `_scale_to_zero_is_idle`(`:42`),绕开了这条路径:
```python
    r._background_tasks = set()
    adapter = _FakeRelayAdapter() if armed_adapter else None

    monkeypatch.setattr(r, "_scale_to_zero_is_idle", lambda: idle, raising=False)
```
而单独验证这一查的用例 `test_bg_work_blocks_idle_via_background_tasks`
(`tests/gateway/test_scale_to_zero_watcher.py:65-83`)只往集合里放**一个**任务,
证明的正是"有任务 ⇒ True"这个**当前实现的**语义 —— 它把 bug 固化成了规格。

**证据强度说明:** 我没有 boot 一个真实的、armed 的网关来端到端确认它不休眠
(需要 relay 凭据 + Fly 环境,按 CLAUDE.md 边界不得配置)。上述结论建立在
三条可独立复核的静态事实 + 一次真实代码的行为实证之上:
(a) `run.py:11545` 用 `_spawn_supervised` 起 watcher;
(b) `run.py:11611` 把任务加入 `_background_tasks`;
(c) `run.py:7437` 对该集合做 `any(not t.done())`。
另有 8 个同样常驻的 watcher(`run.py:11475-11560`)独立地锁死同一条件。

**这个 bug 的形态值得记进"重实现要点":纯函数把语义外包给调用方,
而调用方拿了一个名字听起来对、含义完全不同的字段(`_background_tasks` 听起来是
"后台工作",实际是"守护进程注册表")。** 这不是纯函数化的错,是缺少一个
"什么算 live background work"的单一权威定义 —— 对照 R7 已定案的
"三个看门狗共用一钟"(#72039 单一进度源契约),这里恰恰缺了那个契约。

**顺带的第二个口子:** `_scale_to_zero_is_idle` 用的是 `_running_agent_count()`
(`run.py:7378-7379`,只数 `self._running_agents`),不是 `_active_work_count()`
(`run.py:7381-7388`,= agents + cron jobs + api runs)。所以**一个在跑的 cron 作业
或 API run 不会通过 `running_agent_count` 挡住休眠**。今天被上面那个恒 True 掩盖了,
一旦修掉恒 True,这个口子就会暴露。

---

## 3. 接线核查表

全仓 grep(`--include=*.py --include=*.sh --include=*.toml --include=*.yaml --include=*.md`,
排除 `tests/` 与自身),结论如下。

| 文件 | 生产调用点(`@ 863e313`) | 结论 |
|---|---|---|
| `gateway/restart.py` | `gateway/run.py:2399-2406`(import 6 个符号)、`gateway/slash_commands.py:1619-1625`、`gateway/shutdown_watchdog.py:38,116`、`hermes_cli/gateway.py:34-43`(import 8 个)+ `:1231,:2917-2918,:2955-2956,:3281,:3288-3293,:3298,:3653,:4720,:6871`、`hermes_cli/service_manager.py:722-724`、`hermes_cli/web_server.py:213-214` | ✅ 全仓最热的一个,5 个模块 20+ 处 |
| `gateway/restart_loop_guard.py` | `gateway/run.py:7477`(读配置)、`gateway/run.py:10502-10505`(唯一判定点) | ✅ 已接线。但 `is_restart_loop_tripped` 与 `clear()` **生产侧零调用** |
| `gateway/readiness.py` | `gateway/platforms/api_server.py:96`(import)+ `:2896`(调用);`hermes_cli/web_server.py:3259-3262`(import 私有 `_probe_state_db`) | ✅ 两处,一处用公开 API 一处用私有 |
| `gateway/systemd_notify.py` | `gateway/run.py:12642`(唯一 import)→ `:12645-12648` 起 + `:12658` 停;`_start_systemd_watchdog` 被 `gateway/run.py:26938-26940` 调用,`_stop_systemd_watchdog` 被 `:12804-12806` 调用 | ✅ 单一消费者(GatewayRunner) |
| `gateway/cgroup_cleanup.py` | **不经 import** —— `hermes_cli/gateway.py:2922`(system unit)与 `:2960`(user unit)的 `ExecStopPost=-{python_path} -m gateway.cgroup_cleanup` | ✅ 已接线,但仅 systemd 路径(launchd/s6 无) |
| `gateway/scale_to_zero.py` | `gateway/run.py:7458`、`:7497-7501`、`:7539-7542`、`:7577`(4 处延迟 import);arm 点 `:11540-11545`;时钟 `:14397` | ✅ 已接线,**但见 §2.5:生产语义被 run.py:7437 破坏** |
| `gateway/code_skew.py` | `gateway/run.py:26378-26379`(启动快照)、`gateway/slash_commands.py:85-87`(检测)→ 被 `:1816` 与 `:2124` 调用 | ✅ 已接线 |

**死代码 / 命名漂移小结:**
- `restart_loop_guard.is_restart_loop_tripped`(`:89-111`)—— 生产零调用,仅测试。
- `restart_loop_guard.clear`(`:114-119`)—— 生产零调用,**docstring 声称的 "clean shutdown"
  用法不存在**(▲6)。
- `readiness._probe_state_db` —— 私有名但被 `hermes_cli/web_server.py` 跨模块使用,
  `__all__`(`readiness.py:122`)未包含。
- `systemd_notify.SystemdWatchdog.__init__` 的 `lag_tolerance_seconds`(`:67`)——
  生产调用点(`run.py:12645`)不传,仅测试用。
- `cgroup_cleanup.reap_cgroup` 的返回值(杀了几个)—— `main()`(`:75-77`)丢弃,无处消费。

---

## 4. ▲ / ◇ 候选(含全仓文档检索证据)

### 4.0 检索方法与命中数(可复现)

检索路径:`website/`(389 个文件)、`README.md`、根 `AGENTS.md`、仓库根 `docs/`。
命令形状:`grep -rniE "<pattern>" website/ README.md AGENTS.md docs/ | wc -l`。

| 检索式 | 命中 |
|---|---|
| `HERMES_SCALE_TO_ZERO` | **0** |
| `idle_timeout_minutes` | **0** |
| `go_dormant` | **0** |
| `restart_loop_guard` | **0** |
| `code[-_ ]?skew` | **0** |
| `cgroup` | **0** |
| `cgroup_cleanup` | **0** |
| `gateway/readiness|collect_runtime_readiness` | **0** |
| `sd_notify|NOTIFY_SOCKET|WATCHDOG_USEC` | **0** |
| `exit(-| )?(code )?75|EX_TEMPFAIL` | **0** |
| `EX_CONFIG|exit(-| )?(code )?78` | **0** |
| `restart_after_turn_timeout` | **0** |
| `systemd_watchdog_seconds` | 1(`website/docs/user-guide/messaging/index.md:173`) |
| `RestartForceExitStatus` | 1(`website/docs/user-guide/messaging/index.md:574`) |
| `restart_drain_timeout` | 2(`.../environment-variables.md:760` + zh-Hans 译本 `:521`) |
| `external[-_]supervisor` | 2(`website/docs/reference/cli-commands.md:259,261`) |
| `health/detailed` | 4(其中 `website/docs/user-guide/features/api-server.md:327` 是正文) |

另:`scale-to-zero` 在 website 内只有 6 处,全部与网关无关(Chronos 托管语境
`website/docs/developer-guide/cron-internals.md:132,135`、CLI 参考 `cli-commands.md:577`、
以及 HuggingFace/Modal 技能文档)。`AGENTS.md` 全文只有 2 处弱相关命中
(`:1013` "survive process restart"、`:1113` kanban 的 systemd 目录),`README.md` **零命中**。

### 4.1 ◇(代码有、地图无)

**◇1 —— `gateway/scale_to_zero.py` 网关侧行为层无用户/开发者文档。R7 A5 的最终证实。**
- 文档:上表 `HERMES_SCALE_TO_ZERO` / `idle_timeout_minutes` / `go_dormant` 三项在
  website + README + AGENTS.md 全为 0。**唯一的仓内记载是
  `docs/relay-connector-contract.md`(§3.2/§3.3 讲原语,§3.4 讲行为层义务),
  而它不在 website/ 发布树内**(`docs/` 是仓库根的内部设计目录)。
- 代码:`gateway/scale_to_zero.py` 全文 124 行 + `gateway/run.py:7423-7667` 共约 245 行绑定。
- 裁决:**◇ 证实,且比 R7 判断更严格 ——** 用户完全无从得知这个功能存在、如何开启、
  `gateway.scale_to_zero.idle_timeout_minutes` 这个 config key 存在。
  `hermes_cli/config_defaults.py:2490-2500` 里有详尽注释,但那是代码不是文档。

**◇2 —— `gateway.restart_loop_guard` 配置项无文档。**
- 文档:0 命中。对照:**同类的 `respawn_storm` 有文档**
  (`website/docs/reference/environment-variables.md:808`:
  "`HERMES_GATEWAY_MAX_STARTS` | Respawn-storm circuit breaker… Also configurable via
  `gateway.respawn_storm.max_starts` in `config.yaml`.")。
- 代码:`gateway/run.py:7471-7492` 读 `gateway.restart_loop_guard.{max_restarts,window_seconds}`;
  默认值 `hermes_cli/config_defaults.py:2514-2517`。
- 裁决:◇ 证实。两个熔断器一个有文档一个没有,不是刻意区分,是遗漏。
  用户遇到"重启后会话不自动续跑了"时,唯一线索是那条 WARNING 日志
  (`restart_loop_guard.py:139-149`,它确实给了自救路径)。

**◇3 —— `gateway/cgroup_cleanup.py` 与 cgroup 收割整体无文档。**
- 文档:`cgroup` 在全部检索路径 **0 命中**。
- 代码:模块 81 行 + unit 模板两行 `ExecStopPost`(`hermes_cli/gateway.py:2922,2960`)。
- 裁决:◇ 证实。见 ▲1 —— 这个遗漏还与一条 `:::danger` 提示产生了危险的交互。

**◇4 —— `gateway/code_skew.py` 与 stale-module 风险无文档。**
- 文档:`code[-_ ]?skew` **0 命中**;`stale code|stale module` 亦 0。
- 代码:模块 64 行 + `gateway/slash_commands.py:72-98` 的守卫 + 两处调用。
- 裁决:◇ 证实。用户会在 `/model` 时看到一句"This gateway is running code from X but the
  checkout on disk is now Y"—— 消息本身自解释,所以缺文档的实际伤害低。
  但"热 `git pull` 会让长活网关踩 stale-module"这个**运维风险**完全没有文档提示。

**◇5 —— sd_notify 协议细节(READY/WATCHDOG/STOPPING 的时序)无文档。**
- 文档:`sd_notify|NOTIFY_SOCKET|WATCHDOG_USEC` **0 命中**。
  `website/docs/user-guide/messaging/index.md:165-187` 讲了如何开启
  `systemd_watchdog_seconds` 及其效果("Hermes sends heartbeats only while its event loop
  is making timely progress; systemd restarts the process when they stop"),**功能层面准确**。
- 代码:`gateway/systemd_notify.py:176 行`。
- 裁决:◇(轻微)。用户文档够用,协议细节属实现内部,不算真缺口。**列出但不主张修。**

**◇6 —— 退出码 75 / 78 的语义无文档。**
- 文档:`exit 75|EX_TEMPFAIL|EX_CONFIG|exit 78` **0 命中**;
  `RestartForceExitStatus` 只在 `messaging/index.md:574` 出现一次,且只是提了名字没解释。
- 代码:`gateway/restart.py:8-16`,以及 unit 模板、s6 finish 生成器、CLI 诊断四处消费。
- 裁决:◇ 证实。运维会在 `systemctl status` 里看到 "status=75",无从查证含义。
  代码侧倒是给了兜底:`hermes gateway status` 会翻译它
  (`hermes_cli/gateway.py:3652-3658`)。

**◇7 —— `decisions.md`(scale-to-zero 设计文档)不在仓库内。**
- 证据:`gateway/scale_to_zero.py:10`("Design constraints (decisions.md):")、
  `gateway/run.py:7426-7427`("See ~/nous/specs/scale-to-zero (decisions.md)")。
  `find . -name "decisions.md"` 在基线仓库内**零命中**。
- 影响:全模块的 `D1/D2/D3/D11/D12/D13/F6/F7/F12/F14/Q3=C′/Q8=A` 十几个编号**无法溯源**。
  只有 `§3.4(x)` 能对应到 `docs/relay-connector-contract.md:333-382`。
- 裁决:◇(可追溯性缺口)。这是"注释引用外部私有文档"的典型代价 ——
  对本学习项目而言,这些编号只能当作"作者知道自己在遵守某条约束"的信号来读,
  不能当作可验证的证据。

### 4.2 ▲(文档与代码不符)

**▲1 —— `:::danger` 提示叫用户"删掉 ExecStopPost 那行",但 Hermes 自己的 unit 就有一行
ExecStopPost,且删了会重新引入 #37454。**
- 文档 `website/docs/user-guide/messaging/index.md:573-575 @ 863e313`:
```
:::danger Don't add a custom `ExecStopPost` kill drop-in
The unit Hermes installs already shuts the gateway down cleanly with `KillMode=mixed` + `KillSignal=SIGTERM`, and uses `Restart=always` with `RestartForceExitStatus` so updates and `/restart` respawn correctly. Do **not** add a systemd drop-in such as `ExecStopPost=/bin/kill -9 $MAINPID` — `ExecStopPost` fires on *every* stop, including clean restarts, so it `SIGKILL`s the freshly spawned instance before it stabilizes and `Restart=always` immediately respawns it. The result is an infinite restart loop (and, on Telegram, a flood of restart messages). If you've added such a drop-in, remove it: `systemctl --user edit hermes-gateway` (or `sudo systemctl edit hermes-gateway` for a system service) and delete the `ExecStopPost` line, then `systemctl --user daemon-reload`.
:::
```
- 代码 `hermes_cli/gateway.py:2922 @ 863e313`(以及 `:2960`):
```
ExecStopPost=-{python_path} -m gateway.cgroup_cleanup
```
- 分析:文档的技术判断本身正确(`/bin/kill -9 $MAINPID` 确实是灾难),但
  (a) 它把 Hermes 自己的 unit 描述成"只有 KillMode/KillSignal/Restart",**只字不提自带的
  ExecStopPost**;(b) 结尾"delete the `ExecStopPost` line"这句指令在 drop-in 语境下没问题,
  但一个照着做却打开了主 unit 文件的用户会删掉 cgroup 收割器,**直接回退到 #37454**
  (残留 `adb`/bridge 卡住 cgroup → `Restart=always` 拉不起来)。
- 两者不冲突的技术原因(文档没写):Hermes 那行是 `-` 前缀(失败即忽略)、
  目标是 cgroup 内**除自己以外**的 PID(`cgroup_cleanup.py:63-64` 的 `if pid == own: continue`)、
  且只在主进程已退出后才跑(`cgroup_cleanup.py:3-4` docstring);
  systemd 的 stop job 完成后才启动 start job,所以不存在"杀掉刚起来的新实例"。
- 裁决:**▲ 成立(中度)** —— 文档不完整 + 一条可能误导的操作指令。

**▲2 —— `HERMES_RESTART_DRAIN_TIMEOUT` 的文档默认值 900,代码默认值 0。**
- 文档 `website/docs/reference/environment-variables.md:760 @ 863e313`:
```
| `HERMES_RESTART_DRAIN_TIMEOUT` | Gateway: seconds to wait for active runs to drain on `/restart` before forcing the restart (default: `900`). |
```
  (中文译本 `website/i18n/zh-Hans/.../environment-variables.md:521` 同样写 900。)
- 代码 `hermes_cli/config_defaults.py:38-47 @ 863e313`:
```python
        # Force-interrupt budget once gateway stop()/drain has begun
        # (seconds). Applies to SIGTERM/external stop and to the final
        # phase of in-band restart after any after-turn wait. 0 = interrupt
        # immediately (the default).
        #
        # Keep this short and under systemd TimeoutStopSec — a long value
        # here invites SIGKILL-mid-cleanup. For in-band restart
        # (/restart, SIGUSR1), prefer restart_after_turn_timeout below so
        # active turns finish *before* stop() begins (#77184).
        "restart_drain_timeout": 0,
```
  实测 `DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT = 0.0`。
- 语义也变了:文档说它是"`/restart` 时等活跃 run 排空的时间";代码说它是
  "**stop()/drain 已经开始之后**的强制打断预算",而"等活跃回合结束"现在是
  `restart_after_turn_timeout`(默认 21600,**文档 0 命中**)的职责。
- 裁决:**▲ 成立(中度)** —— #77184 拆分了两个超时,文档只留在旧世界。数值与语义双错。

**▲3 —— `parse_restart_drain_timeout` 对 int `0` 与 str `"0"` 语义不一致(代码内部不一致,非文档)。**
- 代码 `gateway/restart.py:71-72 @ 863e313`:
```python
    try:
        value = float(raw) if str(raw or "").strip() else DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
```
  `str(0 or "")` → `""` → 走 default 分支;`str("0" or "")` → `"0"` → 走 `float()` 分支。
  实测两者今天都得 `0.0`(因 default 就是 0),但**逻辑路径不同**。
- 对照 `parse_restart_after_turn_timeout`(`:78-92`)明确处理了这个区分并写进 docstring。
- 裁决:▲(轻微,潜伏)。今天不咬人,改 default 就咬。

**▲4 —— `tests/gateway/test_restart_service_detection.py` 的 docstring 说 launchd plist 用
`KeepAlive.SuccessfulExit=false`,实际是无条件 `KeepAlive=true`。**
- 测试 docstring `tests/gateway/test_restart_service_detection.py:5-9 @ 863e313`:
```
The /restart handler routes through ``request_restart(via_service=True)``
when a service manager supervises the gateway, so the process exits with
the service-restart code and the manager relaunches it.  Under macOS
launchd the plist uses ``KeepAlive.SuccessfulExit=false`` — a clean exit 0
is treated as a deliberate stop and the gateway stays dead (#43475) — so
```
- 代码 `hermes_cli/gateway.py:4132-4133 @ 863e313`:
```
    <key>KeepAlive</key>
    <true/>
```
  且 `hermes_cli/gateway.py:262 @ 863e313` 明写 "launchd (unconditional KeepAlive)"。
- 裁决:▲(轻微)。测试 docstring 记录的是 #43475 当时的 plist 形态,后来 plist 改成了
  无条件 KeepAlive,docstring 没跟。测试本身仍然正确(它测的是 `XPC_SERVICE_NAME`/
  外部标记的探测,不是 plist)。

**▲5 —— `restart.py:12-15` 说"The s6 finish script"像是指一个签进仓库的文件,实际是运行时生成的。**
- 代码 `gateway/restart.py:12-16 @ 863e313` 的措辞:"The s6 finish script translates
  this into exit 125"。
- 事实:签进仓库的只有 `docker/s6-rc.d/dashboard/finish`(**dashboard 的,不是网关的**);
  网关的 finish 由 `hermes_cli/service_manager.py:712-733` 在服务注册时生成。
  `docker/s6-rc.d/main-hermes/run` 更是明确写着 "For now this service is a no-op: it
  sleeps forever"(`docker/s6-rc.d/main-hermes/run:23-25`),网关是"per-profile gateways
  register dynamically via /run/service/ at runtime (Phase 4)"。
- 裁决:▲(极轻微,措辞)。断言正确,只是定冠词让人以为能 `find` 到。**我为此绕了一圈,
  记下来给后来者省时间。**

**▲6 —— `restart_loop_guard.clear()` docstring 声称"used on clean shutdown",生产无此调用。**
- 代码 `gateway/restart_loop_guard.py:114-115 @ 863e313`:
```python
def clear() -> None:
    """Remove the persisted boot log (used on clean shutdown / by tests)."""
```
- 事实:全仓 grep(排除 tests)对 `restart_loop_guard.clear` / `rlg.clear` 零命中。
- 裁决:▲(轻微)。docstring 描述了一个不存在的用法。

**▲7 —— `docs/relay-connector-contract.md` 仍把 scale-to-zero 行为层称为 "future",而它已经实现。**
- 文档 `docs/relay-connector-contract.md:302-303 @ 863e313`:
  "it wires the wake SIGNAL so **a future scale-to-zero behaviour layer** can rely on…";
  `:333` 小节标题:"### 3.4 Obligations on **a future** scale-to-zero behaviour layer";
  `:335-336`:"this section is the **contract a separate scale-to-zero behaviour workstream
  must honour**"。
- 代码:`gateway/scale_to_zero.py` + `gateway/run.py:7423-7667` 已实现,且 docstring 逐条
  引用 §3.4 条款(`scale_to_zero.py:100-101` 引 §3.4(1);`run.py:7616` 引 §3.4(6))。
- 裁决:▲(轻微,时态滞后)。合同文档本身内容仍然有效(6 条义务都是活的),
  只是"future"这个词已经过期。

### 4.3 文档准确的部分(也要记,避免只报坏消息)

- **`/health/detailed` 的文档与 readiness.py 逐项吻合。**
  `website/docs/user-guide/features/api-server.md:327-337 @ 863e313`:
```
### GET /health/detailed

Authenticated readiness check for monitoring and control planes. It reports
bounded status for the active profile's config, state database, configured
model, disk space, gateway/platform state, active API runs, pending process
completions, and active delegations. The response exposes status and counts,
not config values, credentials, paths, commands, queue payloads, or raw errors.

The public `/health` route remains a cheap liveness probe and does not run
readiness checks. A degraded readiness result still uses HTTP 200; inspect the
top-level `status` and `readiness.checks` fields.
```
  逐项核对 `gateway/readiness.py:105-117` 的六个 check —— 全中,连"不暴露什么"的清单都
  与 `readiness.py:99-102` 的 docstring 一字不差。"degraded 仍返 200"也与
  `api_server.py:2903`(无 `status=` 参数)一致。**这是本簇文档质量的高点。**
- **`systemd_watchdog_seconds` 的用户文档正确。**
  `website/docs/user-guide/messaging/index.md:182-187` 说 "A positive value makes the
  generated unit use `Type=notify`, `NotifyAccess=main`, and the matching `WatchdogSec`" ——
  与 `hermes_cli/gateway.py:2783-2785` 完全一致;"Hermes sends heartbeats only while its
  event loop is making timely progress" 与 `systemd_notify.py:126,133-137` 一致;
  "The default `0` keeps the existing `Type=simple` behavior" 与
  `gateway/config.py:931` + `hermes_cli/gateway.py:2783-2784` 一致。
- **`--external-supervisor` 的 CLI 文档正确。**
  `website/docs/reference/cli-commands.md:259` 描述("declare that a wrapper-provided
  process manager owns the foreground gateway… when `sudo`, `env -i`, or another wrapper
  strips launchd/systemd's native environment marker")与 `gateway/restart.py:18-21`
  的注释同义。

---

## 5. issue 溯源

本簇文件内注释里出现的 issue 编号(编号 + 行号 + 因果):

| 编号 | 出处 | 因果经过 |
|---|---|---|
| **#51228** | `gateway/restart.py:15`;`hermes_cli/service_manager.py:720` | 致命配置错误(token 冲突、一个消息平台都没配)导致网关启动即失败;supervisor 无脑重启 → 无限循环。修法:退 78(EX_CONFIG),systemd 侧 `RestartPreventExitStatus=78` 永不重启,s6 侧生成的 finish 脚本把 78 翻译成 125(s6 的"永久失败")。 |
| **#77184** | `gateway/restart.py:31`、`:106` | 原来 `/restart`/SIGUSR1 一来就进 `stop()` 排水,**发起 `/restart` 的那一回合自己被腰斩**。修法:引入 `restart_after_turn_timeout`(默认 6h),先等活跃回合自然结束再进 `stop()`;并新增 `resolve_restart_exit_wait_budget` 让 CLI 的等待预算覆盖"等回合 + 排水"两段,否则 CLI 提前硬杀就等于没修。 |
| **#30719** | `gateway/restart_loop_guard.py:1`、`:142`;`gateway/run.py:10491`;`hermes_cli/config_defaults.py:2500` | agent 在 terminal 里跑 `launchctl kickstart -k gui/<uid>/ai.hermes.gateway` → launchd SIGTERM 网关 → 会话标记 restart-interrupted → KeepAlive 拉起 → 自动续跑同一会话 → agent 又跑同一条命令。约 10 秒一轮。防线 1/2(CLI 与 cron 上的生命周期过滤)拦不住任意 shell,防线 3 改为拦"自动续跑":60 秒内 3 次带待续跑会话的启动 ⇒ 本轮跳过续跑。 |
| **#69678 / #69567** | `gateway/readiness.py:38`(表述为 "bug class") | `with sqlite3.connect(...)` 的上下文管理器**只 commit/rollback,不 close**。健康检查按秒轮询 ⇒ 每次泄漏一个连接和它的 fd ⇒ 长活网关最终 fd 耗尽。修法:`closing(sqlite3.connect(...))`。 |
| **#37454** | `gateway/cgroup_cleanup.py:7`、`:10`;`tests/gateway/test_cgroup_cleanup.py:1` | 网关停止后,它不追踪的长活辅助进程(`adb`、平台 bridge)留在 systemd unit 的 cgroup 里 ⇒ cgroup 非空 ⇒ unit 停不干净 ⇒ `Restart=always` 拉不起新实例。第一版修法(往 `cgroup.kill` 写 1)被内核以 `EINVAL` 拒绝;第二版改为遍历 `cgroup.procs` 逐 PID `SIGKILL`,走另一条内核代码路径,可用。 |
| **#43475** | `tests/gateway/test_restart_service_detection.py:8`(测试 docstring,非本簇源码) | macOS 上 `/restart` 后网关不回来:当时的 plist 用 `KeepAlive.SuccessfulExit=false`,干净退出 0 被 launchd 当作"故意停止"。修法:在 `/restart` 处理器里就检测 launchd(`XPC_SERVICE_NAME`),走 via_service 路径。**注意 plist 现已改为无条件 `KeepAlive=true`(▲4)。** |

**本簇里 `gateway/systemd_notify.py`、`gateway/scale_to_zero.py`、`gateway/code_skew.py`
三个文件的注释中不含任何 issue 编号。** scale_to_zero 用的是外部 `decisions.md` 的
D/F/Q 编号(◇7);code_skew 用的是一个测试文件路径 + 一个 gateway session id
(`tests/test_stale_utils_module_import.py:4`:"Real incident (gateway session
1518671026962174144)")。

**跨簇引用到的编号(在调用点注释里,归属其他轮次但与本簇路径相关):**
`#8202`(排水超时后 systemd SIGKILL cgroup 抢走 bash/sleep 子进程,`gateway/run.py:12929`)、
`#42675`(`docker compose up --force-recreate` 后 gateway_state 被写成 stopped,
下次开机不自启,`gateway/run.py:13154`)、
`#53107`(卡死的非守护线程阻塞解释器退出,os._exit 兜底,`gateway/run.py:26988` 附近)、
`#53175`(memory provider 卡死导致 SIGTERM 杀不掉,`gateway/run.py:12950`)、
`#54220/#56747`(Windows 上用 pythonw 会让每个控制台子进程弹出 conhost,`gateway/run.py:9891`)、
`#23778`(自动续跑没校验 allowlist,`gateway/run.py:10530` 附近)。

---

## 6. 测试

### 6.1 直接对应的测试文件

| 被测模块 | 测试文件 | 行数 | 用例数(实测) |
|---|---|---|---|
| `gateway/readiness.py` | `tests/gateway/test_readiness.py` | 61 | 2 |
| `gateway/systemd_notify.py` | `tests/gateway/test_systemd_notify.py` | 81 | 3 |
| `gateway/systemd_notify.py`(生命周期契约) | `tests/gateway/test_systemd_watchdog_lifecycle.py` | 54 | 1 |
| `gateway/cgroup_cleanup.py` | `tests/gateway/test_cgroup_cleanup.py` | 42 | 2 |
| `gateway/scale_to_zero.py`(纯函数) | `tests/gateway/test_scale_to_zero.py` | 91 | 12 |
| `gateway/scale_to_zero.py`(watcher 绑定) | `tests/gateway/test_scale_to_zero_watcher.py` | 164 | 5 |
| `gateway/code_skew.py` | `tests/test_code_skew.py` | 63 | 7 |
| `gateway/restart_loop_guard.py` | `tests/hermes_cli/test_gateway_restart_loop.py::TestRestartLoopGuard`(`:940-968`) | 1045(整文件,本类约 29 行) | 2 |
| `gateway/restart.py` | `tests/gateway/test_restart_service_detection.py`(78)、`tests/gateway/test_restart_after_turn.py`(39)、`tests/gateway/test_restart_drain.py` | — | — |

### 6.2 运行验证(基线仓库,只读,未修改)

```
$ cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
    bash scripts/run_tests.sh tests/gateway/test_readiness.py \
    tests/gateway/test_systemd_notify.py tests/gateway/test_systemd_watchdog_lifecycle.py \
    tests/gateway/test_cgroup_cleanup.py tests/gateway/test_scale_to_zero.py \
    tests/gateway/test_scale_to_zero_watcher.py tests/test_code_skew.py

=== Summary: 7 files, 32 tests passed, 0 failed (100% complete) in 3.9s (8 workers) ===
```

### 6.3 测试作为行为规格 —— 几条值得引用的

**(a) readiness 的"非破坏性"被写成断言。**
`tests/gateway/test_readiness.py:58-59 @ 863e313`:
```python
    # Readiness is diagnostic data, not an exception or a destructive repair.
    assert (home / "config.yaml").read_text(encoding="utf-8") == "model: [unterminated"
```
探针读到一个坏 YAML,必须报 degraded 并且**原样留着不修**。

**(b) sd_notify 的抽象套接字翻译被真实套接字验证。**
`tests/gateway/test_systemd_notify.py:14-28 @ 863e313` 真的 `bind("\0hermes-test-notify")`,
设 `NOTIFY_SOCKET="@hermes-test-notify"`,断言 `receiver.recv(4096) == b"WATCHDOG=1"`。
不是 mock,是端到端。

**(c) 三个信号的顺序被断言。**
`tests/gateway/test_systemd_notify.py:75-79 @ 863e313`:
```python
    assert any(message.startswith("READY=1") for message in calls)
    assert "WATCHDOG=1" in calls
    assert calls[-1] == "STOPPING=1"
    assert watchdog.unhealthy is False
```
`calls[-1] == "STOPPING=1"` 就是"STOPPING 必须是最后一条"的规格。

**(d) cgroup 收割在探针文件不可读时必须**不**发信号。**
`tests/gateway/test_cgroup_cleanup.py:36-42 @ 863e313`:
```python
        def _explode(*_a, **_kw):
            pytest.fail("os.kill must not be called when cgroup.procs is unreadable")

        monkeypatch.setattr(cgroup_cleanup.os, "kill", _explode)
        assert cgroup_cleanup.reap_cgroup(cgroup_path) == 0
```
"读不到就什么都别杀"被写成硬失败。

**(e) scale-to-zero 的边界值。**
`tests/gateway/test_scale_to_zero.py:87-89 @ 863e313`:
```python
def test_idle_exactly_at_threshold():
    # >= timeout is idle (boundary).
    assert is_idle(**_idle_kwargs(seconds_since_last_inbound=300.0)) is True
```
以及"没有 wakeUrl 绝不 arm"`:63-66`(注释直接引 §3.4(1) 的"black hole")。

**(f) code_skew 的"绝不误报"。**
`tests/test_code_skew.py:20-24 @ 863e313`:
```python
    def test_no_boot_fingerprint_means_no_skew(self, monkeypatch):
        # Nothing recorded (e.g. non-git install) -> never a false positive.
        monkeypatch.setattr(code_skew, "_fingerprint", lambda: "git:refs/heads/main:def456")
        assert code_skew.detect_code_skew() is None
```

**(g) restart_loop_guard 的"读不写"语义。**
`tests/hermes_cli/test_gateway_restart_loop.py:955-962 @ 863e313`:
```python
    def test_is_tripped_reads_without_recording(self):
        import gateway.restart_loop_guard as rlg
        rlg.record_restart_interrupted_boot(60, now=1000.0)
        rlg.record_restart_interrupted_boot(60, now=1001.0)
        assert rlg.is_restart_loop_tripped(3, 60, now=1002.0) is False
        rlg.record_restart_interrupted_boot(60, now=1002.0)
        assert rlg.is_restart_loop_tripped(3, 60, now=1003.0) is True
```

### 6.4 测试覆盖的缺口

- **§2.5 的恒 True bug 无测试能抓到** —— 反而被
  `tests/gateway/test_scale_to_zero_watcher.py:65-83` 固化成了规格。
  缺的是"一个 armed 的 runner 在真实 startup 之后仍然能判出 idle"这一级的集成测试。
- **`is_restart_loop_tripped` 与 `clear()` 只有测试用**,测试覆盖了不存在的生产路径 ——
  覆盖率不等于接线正确。
- **`cgroup_cleanup` 无 happy-path 测试**:`TestReapCgroup` 类里只有
  `test_noop_when_procs_file_missing` 一个用例(`tests/gateway/test_cgroup_cleanup.py:26-42`),
  "真的读到 PID 列表并逐个 kill"这条主路径没有用例。
- **`readiness._probe_disk` 的 90% 阈值无用例**(现有两个用例都只断言
  `in {"ok","degraded"}`,`tests/gateway/test_readiness.py:38`)。

---

## 7. 重实现要点(造自己的 harness 时抄什么、避什么)

**抄:**

1. **把"与 supervisor 的协议"收敛成一个 20 行的常量模块。** 退出码、env 标记名、
   超时默认值,只有一个定义处;unit 模板、finish 脚本生成器、运行时退出路径、
   CLI 诊断都从那里 import。hermes 的 75/78 出现在 4 个消费点,靠 import 保持同步。
2. **两个退出码就够表达全部意图**:一个"请重启我"(systemd `RestartForceExitStatus`),
   一个"别再重启我了"(`RestartPreventExitStatus` / s6 的 125)。剩下的交给 supervisor
   自己的 `Restart=`/`RestartSec`/`StartLimit`。
3. **跨重启的状态一律落盘,且 fail OPEN。** 每次重启都是新进程,内存状态毫无意义。
   落盘的熔断器坏了要"放行"而不是"拦截"——
   `restart_loop_guard.py:26-27`:"a broken breaker must never wedge a healthy gateway"。
4. **熔断的动作要选最小的那个。** hermes 熔断后不停网关、不停平台、不退避,
   只跳过"自动续跑"这一个放大器;网关继续服务真实用户消息,人自动回到环路里。
   **熔断日志里给出自救路径(删哪个文件)。**
5. **watchdog 心跳的判据是"事件循环按时醒来",不是"定时器到点"。**
   用绝对时刻推进 `scheduled_at`,`now - scheduled_at` 就是循环延迟。
   检测到超容差时**不自杀,而是停止喂食 + 发一条人类可读的 STATUS**,让外部执行处决。
6. **`STOPPING=1` 必须在长排水开始之前发。** 否则 watchdog 计时器会在优雅排水中途把你打死。
7. **就绪探针的三条纪律**:只读(`mode=ro` + `PRAGMA query_only` + 短 timeout)、
   显式关闭(`closing()`,别信 sqlite3 的 `with`)、异常只回类名不回消息。
8. **区分 liveness 与 readiness**:一个便宜的公开 `/health`(进程在不在)+ 一个鉴权的
   `/health/detailed`(能不能干活),degraded 仍返 200,把判定权留给调用方。
9. **收割自己没带走的孩子。** 长活进程 + 会 spawn 长活辅助进程 = 必然有孤儿。
   在 supervisor 的 post-stop 钩子里收割一遍;逐 PID 发信号比"整组 kill"的内核路径更可靠。
10. **长活进程要能检测"自己的代码过期了"。** 启动时快照一个便宜的版本指纹
    (读 `.git/HEAD` 而不是 spawn git),在高危动作(切模型、加载新代码路径)前比对,
    宁可拒绝并给一句"重启我",也不要让用户面对一条自相矛盾的 ImportError。
11. **判定逻辑抽成纯函数确实值得**:5 个纯函数换来 12 个 3 秒跑完的独立用例,
    每个合取项都能单独翻转。**但要配一条契约(见下)。**

**避:**

12. **★ 纯函数化必须配一个"输入契约的单一权威定义",否则调用点会喂错料。**
    hermes 的 `messaging_is_relay_only_or_absent` 被喂了预填的平台目录(20 个占位)
    而不是"实际启用的平台",导致功能整整一段时间从不生效且无声无息
    (`gateway/run.py:7502-7511` 的注释就是这场事故的墓志铭)。
    `_scale_to_zero_has_live_background_work` 又被喂了 `_background_tasks` ——
    一个听起来像"后台工作"、实际是"守护进程注册表"的字段,**导致 idle 判定在生产上恒为 False**
    (§2.5)。**修法:给"什么算活跃平台""什么算 live work"各建一个方法,
    所有消费者共用**(对照 hermes 自己在 #72039 里做对的"三个看门狗共用一钟")。
13. **"沉默的 False"是最贵的 bug。** 任何"本该启用却没启用"的分支,都要在
    **用户已明确 opt-in** 的前提下打一条说明原因的日志(hermes 的
    `_log_scale_to_zero_not_armed_reason`,`run.py:7530-7573`),
    且在未 opt-in 时保持安静。
14. **同一个字面量在不同机制里的语义要各自写清。** hermes 里 `0` 在
    `restart_after_turn_timeout` 是"显式禁用",在 `scale_to_zero.idle_timeout_minutes`
    是"回落默认"。两处 docstring 都交代了 —— 这是对的;但
    `parse_restart_drain_timeout` 里 int `0` 和 str `"0"` 走不同分支(▲3),这是没交代的,
    早晚咬人。
15. **代码里引用的设计文档要在仓库内。** hermes 的 `decisions.md` 不在仓库里(◇7),
    十几个 `D11/Q8=A` 编号成了无法验证的符号。
16. **文档里给出的"修复操作"要检查会不会误伤自家配置。** ▲1 那条
    "delete the `ExecStopPost` line" 会让照做的用户删掉 cgroup 收割器,
    重新引入它自己在别处修好的 #37454。
17. **别让下划线私有名成为事实公开 API。** `readiness._probe_state_db` 被跨模块 import
    而 `__all__` 不含它 —— 要么改名公开,要么在 `__all__` 里承认。
18. **测试可以把 bug 固化成规格。** `test_bg_work_blocks_idle_via_background_tasks`
    精确验证了当前实现的语义,而当前实现的语义是错的。
    **对"判定谓词"这类东西,除了单元测试还要有一条"在真实启动之后仍然能判出 True"的集成断言。**

---

## 附:本篇未展开、留给成品章的素材

- `/restart` 的完整时序(marker 写入 → 排水 → 通知 → 退出 → 新进程读 marker 发通知)
  跨 run.py 与 slash_commands.py,R7 的 `r7-raw-run-06-drain-restart-restore.md` 已覆盖排水侧,
  本篇只覆盖了 restart.py 提供的"路由词汇"。
- `_launch_detached_restart_command` 的 Windows 分支(`gateway/run.py:9818-9947`,约 130 行)
  含大量 Win32 细节(job object breakaway、conhost、bpo-14484),本篇只点到。
- relay 侧的 `going_idle`/`going_idle_ack`/`inbound_ack` 三帧与 `ws_transport.go_dormant`
  (`gateway/relay/ws_transport.py:634`)属 R7B relay 簇。
