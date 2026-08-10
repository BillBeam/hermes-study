# r7 底稿 · gateway/run.py 第 4 段(10664–12659):start() 启动序列与 watcher 集群

> 精读范围:`gateway/run.py:10664-12659 @ 863e313`(GatewayRunner 第 4 段)。
> 溯源约定:`路径:行号 @ 863e313` + 逐字代码摘录(≤25 行/处)。
> 本段主角:`start()`(913 行启动序列)、`_spawn_supervised`(任务级监督)、
> `_handoff_watcher/_process_handoff`(CLI→gateway 会话交接)、`_session_expiry_watcher`
> (会话过期 finalize 与缓存治理)、stall 看门狗五件套(配合 `gateway/session_stall.py`)、
> `_platform_reconnect_watcher`(平台重连)、systemd watchdog 启停对。

---

## 0. 全段鸟瞰

`start()` 是 gateway 的"总装车间":从进程级自保(faulthandler)开始,经安全闸门
(allowlist / open-policy 拒启)、崩溃恢复(进程登记簿、会话悬挂、stuck-loop 检测)、
平台适配器逐个装配连接(带超时、失败分类、独占声明),最后拉起 10+ 个常驻 watcher。
所有 watcher 统一经 `_spawn_supervised` 拉起 —— 这是本段的核心机制:裸
`asyncio.create_task` 会把 watcher 外层循环逃逸的异常无声吞掉(#71758:平台断线
17.5 小时无人知晓),监督层补上"记日志 + 带退避重启 + 健康期重置计数"。

调用关系总表(本段 → 他处):

| 被调方 | 位置 | 用途 |
|---|---|---|
| `start_loop_liveness_watchdog` / `loop_heartbeat_forever` / `DEFAULT_HEARTBEAT_INTERVAL_S=30.0` | gateway/shutdown_watchdog.py:110/431/47 | 事件循环活性守卫与心跳文件 |
| `check_systemd_timing_alignment` | gateway/shutdown_forensics.py:322 | TimeoutStopSec ≥ drain_timeout 对齐自检 |
| stall 四纯函数 | gateway/session_stall.py:27/46/63/72 | 通知策略(emit/clear/format/idle 解析) |
| `resolve_delivery_transport` / `looks_like_telegram_private_chat_id` | gateway/delivery.py:92/134 | relay 别名感知的投递解析;TG 私聊判定 |
| handoff DB 四方法 | hermes_state.py:9627/9645/9656/9666(经 AsyncSessionDB hermes_state.py:9677) | pending 列表 / 原子认领 / 完成 / 失败 |
| `set_expiry_finalized` / `prune_old_entries` / `suspend_recently_active` / `switch_session` | gateway/session.py:2035/2800/2850/2993 | 会话存储治理 |
| `create_handoff_thread` | gateway/platforms/base.py:3525(relay 版 gateway/relay/adapter.py:2045) | handoff 目的地开新线程 |
| `SystemdWatchdog` | gateway/systemd_notify.py:60 | sd_notify READY/WATCHDOG/STOPPING |
| kanban 双 watcher | gateway/kanban_watchers.py:125/953 | mixin 提供,本段仅拉起 |
| run.py 内部 | :3606 `_dispose_unused_adapter`、:3665 `_reconnect_backoff`、:2009 `_platform_has_bot_credential`、:2428 `_own_policy_open_startup_violation`、:6609/6647 连接超时、:10598 中途停机检测、:9725 stuck-loop、:10271 `_finish_startup_restore`、:13632/13642 credential/listener claim | 见各节 |

---

## 1. start() 启动序列(10664–11564,按阶段逐节)

### 1.0 签名与返回值语义(文档-代码冲突候选 ▲1)

gateway/run.py:10664-10669 @ 863e313
```python
    async def start(self) -> bool:
        """
        Start the gateway and all configured platform adapters.
        
        Returns True if at least one adapter connected successfully.
        """
        logger.info("Starting Hermes Gateway...")
```

**▲1 docstring 与实现冲突**:实测本函数**所有**路径都 `return True`——包括 0 个平台连上
(降级为 cron-only,11341-11343)、open-policy 拒启(10913)、multiplex 配置错误(11242)、
中途收到停机请求(10822 等多处 `return True`)。"至少一个适配器连接成功才 True" 是陈旧
描述;真实语义是"启动流程已走完(含拒启型走完),调用方接着 `wait_for_shutdown()`"。
拒启的信号通道不是返回值,而是 `self._exit_code` + `_request_clean_exit(reason)`。

### 1.1 阶段 0:faulthandler 与事件循环活性守卫(10670–10719)

**问题**(#70344 冻结无栈可查;#71671 Windows 无 stderr 场景下 `faulthandler.enable()`
直接抛错杀死 gateway):进程冻结/崩溃时需要栈转储,但启用动作本身不能成为新的启动死因。

gateway/run.py:10671-10688 @ 863e313
```python
        # Enable faulthandler for stack dumps on freezes/crashes (#70344).
        # Falls back to a log file when sys.stderr is None (Windows VBS /
        # pythonw / detached service) — otherwise the gateway would die
        # here and take every adapter offline. See #71671.
        try:
            faulthandler.enable()
        except (RuntimeError, ValueError, OSError):
            try:
                _fh_log_dir = getattr(self.config, "log_dir", None) or os.path.join(
                    str(get_hermes_home()),
                    "logs",
                )
                os.makedirs(_fh_log_dir, exist_ok=True)
                _fh_enable_path = os.path.join(_fh_log_dir, "gateway_faulthandler.log")
                _fh_enable_file = open(_fh_enable_path, "a", encoding="utf-8")
                faulthandler.enable(file=_fh_enable_file, all_threads=True)
            except Exception:
                logger.debug("faulthandler.enable() unavailable", exc_info=True)
```

随后(10695-10712)在 POSIX 上把 `SIGUSR2` 注册为"按需转储所有线程栈到
`logs/gateway_faulthandler.log`"(`faulthandler.register(_sigusr2, file=_fh,
all_threads=True, chain=True)`),Windows 无 SIGUSR2 则跳过。设计理由:服务管理器
(launchd/NSSM)常不捕获 stderr,固定文件是唯一可靠取证通道;`chain=True` 保留用户
自装的 SIGUSR2 处理器。

10714-10719:记录 `self._gateway_loop = asyncio.get_running_loop()` 并调用
`_start_loop_liveness_guards`(gateway/run.py:10624,armed 两件套:loop floor timer +
线程外 watchdog;`gateway.loop_watchdog: false` 可整体关闭,#69089)。取舍:守卫在
**适配器之前**armed,使适配器 connect 阶段的循环冻结也可被侦测。

**重实现要点**:① 崩溃取证设施必须 fail-open,启用失败降级为文件而不是让进程死在取证
代码上;② 给运维留一个"活体取栈"信号(SIGUSR2);③ 活性守卫要先于业务装配 armed。

### 1.2 阶段 1:启动自检广播(10720–10821)

六项"把隐性配置读出来喊一遍"的自检,全部 best-effort(try/except 包裹,绝不阻断启动):

1. **systemd 停机窗对齐**(10727-10742):调 `check_systemd_timing_alignment(self._restart_drain_timeout)`
   (gateway/shutdown_forensics.py:322)。问题:用户升级后没重跑 `hermes setup`,unit 文件
   里旧 `TimeoutStopSec` < 新 drain_timeout,SIGTERM 后 systemd 在 drain 中途 SIGKILL,
   journal 只见 `code=killed status=9`("phantom kill")。实现:读 `/proc/self/cgroup`
   找 unit 名 → `systemctl show --property=TimeoutStopUSec` → 不齐则 WARN 提示
   `hermes gateway install --force`。
2. **max_iterations 预算回显**(10746-10754):`int(os.getenv("HERMES_MAX_ITERATIONS", "500"))`,
   目的是让运维一眼核对 config.yaml→env 桥接结果,防"陈旧 .env 值静默跑数周"。
3. **脱敏状态**(10755-10777,#17691 默认开启):关掉时打 WARN。注释点明关键:
   "the redactor snapshots its state at import time, so this log line is the source of
   truth for this process's lifetime"——运行中改 env 无效,日志行即本进程终身状态。
4. **active profile 回显**(10778-10784)。
5. **runtime status 写 `starting`**(10785-10789,gateway/status.py `write_runtime_status`)。
6. **健康 OTLP 导出 + 供应链公告**(10790-10821):`start_gateway_health_export(load_config())`;
   `hermes_cli.security_advisories.detect_compromised()` 命中则 WARN(不拦启动、不进用户
   消息——注释:能处置的是运维,不是聊天对端)。

10822-10823:第一处 `_abort_startup_if_shutdown_requested()`(gateway/run.py:10598)——启动全程
反复插入该检查点,收到 /restart 或 SIGTERM 时就地收尾(等 `_stop_task` 或自己调 `stop()`)
后 `return True`,避免"启动与停机赛跑"。

**重实现要点**:① 启动期把所有影响行为的隐性开关(预算、脱敏、profile)显式打进日志,
作为"进程终身契约"的书面记录;② 与服务管理器的定时参数做启动期对齐校验;③ 长启动序列
里高频插入停机检查点。

### 1.3 阶段 2:安全闸门(10825–10913)

**警告闸**(10825-10891):内置 24 个 `*_ALLOWED_USERS` 与 19 个 `*_ALLOW_ALL_USERS`
env 名单(10826-10859),再从 `gateway.platform_registry.platform_registry.plugin_entries()`
合并插件平台各自声明的 `allowed_users_env / allow_all_env`(10863-10876)——设计理由:
警告文案的准确性随插件生态自动扩展。两者皆空时 WARN"默认 pairing/allowlist 策略会拒绝
陌生人"。

**拒启闸**(10893-10913):`_own_policy_open_startup_violation(self.config)`
(gateway/run.py:2428)检查五个"自有协议"平台(WECOM/WEIXIN/YUANBAO/QQBOT/WHATSAPP,
`_OWN_POLICY_OPEN_ENV` gateway/run.py:2419):`dm_policy/group_policy: open` 却没有
`GATEWAY_ALLOW_ALL_USERS` 或平台级 allow-all 双确认 → 返回违规原因。

gateway/run.py:10901-10913 @ 863e313
```python
            logger.error(
                "Refusing to start: %s has dm_policy/group_policy set to 'open' "
                "but neither GATEWAY_ALLOW_ALL_USERS nor %s is enabled.",
                platform_value,
                allow_all_env or "a platform allow-all flag",
            )
            try:
                from gateway.status import write_runtime_status
                write_runtime_status(gateway_state="startup_failed", exit_reason=reason)
            except Exception:
                pass
            self._request_clean_exit(reason)
            return True
```

取舍:为什么只有这五个平台是硬拒启、其余平台仅 WARN?这五个走自建回调/网页协议,
"open" 意味着任何扫到入口的人都能驱动 agent(带宿主机工具),风险级别不同;而
Telegram/Discord 等 open 至少还要先找到 bot。双开关(全局 + 平台)是"故意打开"证明。

**重实现要点**:① 危险配置组合要在启动期拒绝而非运行期出事;② 拒启也要写 runtime
status(`startup_failed` + reason),让 `hermes status` 可诊断;③ 安全警告清单让插件
自带元数据,避免中心清单腐化。

### 1.4 阶段 3:插件 / relay / hooks 装配(10915–10987)

- **插件发现**(10921-10927):`hermes_cli.plugins.discover_plugins()`。注释交代顺序
  理由:gateway 是懒 import `run_agent` 的,`model_tools.py` 里的发现副作用此刻未必
  跑过;且"插件先于 shell hooks 发现,tie 时插件 block 决策优先"。
- **relay 适配器注册**(10929-10959):`gateway.relay` 的三连:`self_provision_relay()`
  (启动期自供给:NAS token → POST /relay/provision → 写 `GATEWAY_RELAY_*` 进
  os.environ,**必须在** `register_relay_adapter()` 读取之前)、`register_relay_adapter()`
  (无 URL 即 no-op,单租户零影响)、`send_relay_policy()`(把 mention-gating 等相关性
  策略推给 connector,使 relay 侧投递遵守同一行为)。
- **shell hooks / outbound webhooks**(10961-10984):`agent.shell_hooks.register_from_config(_hooks_cfg, accept_hooks=False)`。
  注释交代:gateway 无 TTY,同意只能来自三个显式渠道(--accept-hooks / env / config),
  这里传 False 让 register_from_config 自己解析 env+config,避免重复查找逻辑。
- **event hooks**(10987):`self.hooks.discover_and_load()`。

### 1.5 阶段 4:崩溃恢复四连(10990–11032)

1. **进程登记簿恢复**(10991-10997):`tools.process_registry.process_registry.recover_from_checkpoint()`
   ——上个进程留下的后台子进程(浏览器、长命令)从 checkpoint 找回。
2. **会话悬挂**(10999-11021,#7536):

gateway/run.py:11008-11021 @ 863e313
```python
        _clean_marker = _hermes_home / ".clean_shutdown"
        if _clean_marker.exists():
            logger.info("Previous gateway exited cleanly — skipping session suspension")
            try:
                _clean_marker.unlink()
            except Exception:
                pass
        else:
            try:
                suspended = await self.async_session_store.suspend_recently_active()
                if suspended:
                    logger.info("Marked %d in-flight session(s) as resumable from previous run", suspended)
            except Exception as e:
                logger.warning("Session suspension on startup failed: %s", e)
```

   问题(#7536):卡死会话被盲目续跑 → 同样历史再次卡死 → 重启 → 死循环。实现:非
   干净退出时把"最近活跃"(默认 120s 内,gateway/session.py:2850)的会话标记 suspended,
   下一条用户消息触发干净重置。`.clean_shutdown` 标记文件由优雅停机路径写入并在此消费
   (读后即删,一次性),使 `hermes update`/`/restart` 后不会误伤正常会话。
3. **stuck-loop 检测**(11023-11032 调 gateway/run.py:9725):`.restart_failure_counts` 里
   计数 ≥ `_STUCK_LOOP_THRESHOLD = 3`(gateway/run.py:9695)的会话直接 `entry.suspended = True`
   ——"连续 3 次重启时都在活跃"判定为同一历史反复弄死 agent,自动给用户清白开局;
   随后删计数文件重新起算。
4. **startup-restore 闸门声明**(11034-11041):

gateway/run.py:11034-11041 @ 863e313
```python
        # Serialize startup restore against inbound dispatch.  Platform
        # adapters can begin receiving messages as soon as they connect, but
        # restart-interrupted sessions are not auto-resumed until all startup
        # wiring below completes.  Queue inbound messages until the resume
        # pass runs and every synthetic resume turn has finished.
        self._startup_restore_in_progress = True
        self._startup_restore_queue = []
        self._startup_restore_tasks = []
```

   设计理由:适配器连上即可能收消息,而重启中断会话的自动续跑要等全部布线完成;不设闸
   会出现"用户新消息与合成 resume 轮抢同一会话"的竞态。闸门由阶段 11 的
   `_finish_startup_restore()`(gateway/run.py:10271)释放——**有界等待**(超时释放闸门、慢
   resume 轮继续后台跑不取消;防重复 agent 的真正机制是 resume 预先同步占
   `_running_agents` 槽,见其 docstring)。

**重实现要点**:① 用一次性标记文件区分"干净退出"与"崩溃",崩溃才触发保守恢复;
② 跨重启计数器识别"毒历史"会话并自动隔离;③ 恢复期入站消息排队而非丢弃,且闸门必须
有界,靠槽位占用而非闸门本身防止重复执行。

### 1.6 阶段 5:平台适配器逐个装配与连接(11043–11220)

主循环 `for platform, platform_config in self.config.platforms.items()`(11051),
每个平台走六步:

1. **multiplex 空凭据跳过**(11049-11071,#64674):`multiplex_profiles` 开启时,
   default profile 的 config.yaml 启用了平台但 token 在别的 profile 的 .env 里——
   空 token 起主适配器必失败且进入"永不能好"的重连死循环。故
   `_platform_has_bot_credential(platform, platform_config)`(gateway/run.py:2009,只对
   `PLATFORM_TOKEN_ENV_NAMES` 内平台检查 token/api_key 非空)不过即 skip,记入
   `_multiplex_skipped_platforms` 供阶段 7 复核。
2. **建 adapter**(11074-11087):`self._create_adapter` 返回 None 时区分两种告警
   ——非内置平台名提示"插件装了吗",内置平台提示"依赖/凭据"。
3. **handler 装配清单**(11093-11102,与重连路径 12465-12474 完全同构):

gateway/run.py:11093-11102 @ 863e313
```python
            adapter.set_message_handler(self._primary_message_handler())
            adapter.set_fatal_error_handler(self._handle_adapter_fatal_error)
            adapter.set_session_store(self.session_store)
            adapter.set_busy_session_handler(self._handle_active_session_busy_message)
            _set_reaction = getattr(adapter, "set_reaction_handler", None)
            if callable(_set_reaction):
                _set_reaction(self._handle_reaction_event)
            adapter.set_topic_recovery_fn(self._recover_telegram_topic_thread_id)
            adapter.set_authorization_check(self._make_adapter_auth_check(adapter.platform))
            adapter._busy_text_mode = self._busy_text_mode
```

   注释(11089-11092)强调 multiplex 下 default profile 也要拿到"整 handler 级"运行时
   scope:授权与 prompt 渲染都发生在更窄的 agent-turn scope 安装之前。
4. **带超时连接 + takeover 窗口**(11112-11115):`_connect_initial_adapter_with_timeout`
   (gateway/run.py:6647)在 await 期间临时置 `adapter._platform_lock_takeover_allowed =
   bool(self._platform_lock_takeover_on_start)`,finally 归 False。该 flag 由 CLI
   `--replace` 设置(gateway/run.py:26595)。设计理由(6648-6654 docstring):"驱逐同 token
   旧持有者"的能力只在**冷启动初连**窗口可见;重连路径直接走
   `_connect_adapter_with_timeout`(gateway/run.py:6609)且默认 deny——网络恢复后的重连永远
   不能驱逐健康的 token 持有者。底层超时用 detach-on-timeout 模式(6623-6645):
   `asyncio.wait` 而非 `wait_for`,超时后 cancel 但**不等**其退出——吞掉 CancelledError
   的 connect() 不能永远堵死 watcher(#70344)。
5. **成功路**(11118-11132):挂进 `self.adapters`、同步 voice 状态与
   `_voice_input_callback`、runtime status 记 `connected`。
6. **失败三分类**(11133-11218):
   - connect 返回 False 且 `adapter.has_fatal_error`:按 `fatal_error_retryable` 分流
     ——retryable 入 `_failed_platforms` 重试队列(`attempts:1, next_retry:+30s`),
     non-retryable 只进 `startup_nonretryable_errors` 列表(不入队);
   - 返回 False 无 fatal 信息:视为瞬态,入队;
   - 抛异常:同瞬态,入队。
   三条失败路都先 `await self._safe_adapter_disconnect(adapter, platform)`(11143 注释:
   失败的 connect() 可能已分配 aiohttp session / poll task / bridge 子进程,不清理就是
   "Unclosed client session";disconnect 实现被要求幂等且容忍半初始化)。

**凭据/监听独占声明**:每个入队条目都带
`credential_claim` / `listener_claim`(11165-11170 等三处):

gateway/run.py:13632-13639 @ 863e313
```python
    def _adapter_credential_claim(
        platform: Platform, adapter: Any
    ) -> Optional[tuple]:
        """Return the exclusive credential resource claimed by an adapter."""
        fingerprint = GatewayRunner._adapter_credential_fingerprint(adapter)
        if fingerprint is None:
            return None
        return (platform, fingerprint)
```

credential claim = (platform, 盐化哈希指纹)(指纹提取见 gateway/run.py:13664,遍历
token/bot_token/_token 等属性,**绝不落原文**);listener claim 目前仅 photon 平台
(gateway/run.py:13642-13661:sidecar 是 per-profile 进程,即便两 profile 凭据不同也不能共享
bind+port,表达为 `("listener","photon",bind,port)` 四元组)。用途:multiplex 启动时
secondary profile 的适配器与已入队/已连接者比对 claim,冲突即拒——**在 connect()/
disconnect() 能碰到第一个 profile 之前**就拦下(13647-13649 docstring)。

**重实现要点**:① 初连与重连的"抢锁"权限必须不对称(初连可 --replace 驱逐,重连永远
不可),否则网络分区恢复时两实例互相驱逐;② connect 超时要 detach 而不是等取消完成;
③ 失败分类三路(non-retryable 不入队 / retryable 入队 / 未知按瞬态入队),每路都强制
资源清理;④ 独占资源(凭据、端口)在入队时就登记 claim,冲突检测前移到装配期。

### 1.7 阶段 6:secondary profiles 与 takeover 窗口关闭(11222–11267)

`_secondary_connected = await self._start_secondary_profile_adapters()`(11227,实现
在 gateway/run.py:13180,不在本段)。两个失败面:`MultiplexConfigError` → 写 `startup_failed`
+ `self._exit_code = GATEWAY_FATAL_CONFIG_EXIT_CODE` + 干净退出(11229-11242,理由:
宁可让运维改 config.yaml,不跑"半布线 gateway");普通异常仅记 error 继续。

gateway/run.py:11245-11248 @ 863e313
```python
        finally:
            # Startup authority is one phase, not a persistent runner mode.
            # From this point onward every adapter retry is non-evicting.
            self._platform_lock_takeover_on_start = False
```

阶段 4 里被 skip 的平台若最终没有任何 secondary profile 接住(11255-11267),打 WARN
"enabled but no profile provided a bot credential — the platform is not being served"
——#64674 follow-up:防"配置里启用了、实际上静默没人服务"的死频道。

### 1.8 阶段 7:connected_count == 0 决策树(11269–11343)

四层判定,核心问题:**启动失败时进程该死还是该活?**

1. **纯 non-retryable**(11270-11281):`exit_code = GATEWAY_FATAL_CONFIG_EXIT_CODE`
   (=78,配置错误)干净退出——配合 systemd `RestartPreventExitStatus=78` / s6
   finish→125(#51228)阻断重启循环,逼运维修配置。
2. **混合失败**(11282-11302,NS-609):

gateway/run.py:11283-11297 @ 863e313
```python
                # Mixed failure mode (NS-609): some platforms are fatally
                # misconfigured (e.g. WhatsApp enabled but never paired) while
                # others hit merely transient errors (e.g. Telegram TimedOut
                # during polling startup).  Exiting with
                # GATEWAY_FATAL_CONFIG_EXIT_CODE here is wrong in both
                # supervision worlds: under supervisors that honor the
                # exit-78 contract (systemd RestartPreventExitStatus, s6
                # finish→125 since #51228) the gateway goes PERMANENTLY down
                # over a network blip; under anything else it crash-loops.
                # Either way the retryable platforms never get their retry.
                # Log the fatal side loudly, then fall through to the
                # degraded/retry path below: the reconnect watcher recovers
                # the retryable platforms; the non-retryable ones remain
                # fatal-parked and visible in runtime status.
                logger.error(
```

   ——一句话:有任何可重试失败在场,就不许用退出码 78,否则"WhatsApp 没配对"会连累
   "Telegram 网络抖动"永远得不到重试。fatal 者停在 runtime status 里示众,gateway 活着。
3. **全 retryable**(11303-11330):写 `degraded` 状态,留活等 reconnect watcher。
   历史教训(11313-11314 注释):"Exiting here used to convert a single misconfigured
   platform into an infinite systemd restart loop."
4. **无任何 adapter 可建 / 无平台启用**(11331-11343,#5196):fleet 部署里同一
   config.yaml 撒到只有部分凭据的节点,降级为 cron-only 继续跑。

**重实现要点**:① 退出码是给 supervisor 的 API:致命配置错误用专用码 + supervisor 端
"此码不重启"约定;② 混合失败禁用致命码,fail-open 到降级态;③ "没有平台"不等于
"没有价值"(cron 仍在),降级要显式声明而非崩溃。

### 1.9 阶段 8:进入 running 与心跳(11345–11392)

`self.delivery_router.adapters = self.adapters`(11348)、`_wire_teams_pipeline_runtime()`、
`self._running = True` + runtime status `running`(11351-11352)。然后拉起 loop 心跳
(#66892):

gateway/run.py:11354-11366 @ 863e313
```python
        # Loop-liveness heartbeat (#66892): an asyncio task so a frozen loop
        # stops refreshing ``state/gateway.heartbeat``. Cancelled with the
        # other background tasks during stop(). Best-effort — a liveness probe
        # must never be able to abort startup.
        try:
            _existing_hb = getattr(self, "_loop_heartbeat_task", None)
            if _existing_hb is None or _existing_hb.done():
                self._loop_heartbeat_task = asyncio.create_task(
                    loop_heartbeat_forever(
                        interval_s=DEFAULT_HEARTBEAT_INTERVAL_S,
                        start_time=getattr(self, "_gateway_started_at", 0.0),
                    )
                )
```

设计巧思:心跳是 **asyncio task**(而非线程),循环冻结 → 心跳文件停更 → 外部探针
(`hermes status`、shutdown_watchdog 侧)据"文件年龄"判死。随后 `hooks.emit
("gateway:startup", {platforms:[...]})`(11378-11380)、构建 channel directory
(11386-11392,gateway/channel_directory.py `build_channel_directory`,供
send_message 名称解析)。

### 1.10 阶段 9:update / restart 通知(11394–11435)

- `_send_update_notification()`(11396):/update 重启回来后通知;若
  `.update_pending.json` / `.update_pending.claimed.json` 仍在(更新还在跑),
  `_schedule_update_notification_watch()` 持续盯到真正完成。
- `await asyncio.sleep(1.0)`(11410):给刚连上的适配器 1 秒沉降——注释点名
  "helps Discord thread deliveries right after reconnect"。
- `/restart` 精确回执(11413-11422):`_restart_notification_pending()` 读
  `.restart_notify.json` 标记;**在 unlink 之前**捕获 `self._booted_from_restart = True`
  ——这是 /restart 重投递防重的 one-shot 信号(缺 dedup 标记时,只有"确知刚从重启周期
  出来"才抑制 /restart,见 `_is_stale_restart_redelivery`)。
- 计划内重启广播(11429-11435):非聊天发起(终端/SIGUSR1/service)的重启才向 home
  channel 广播"回来了";聊天发起的 /restart 已有精确回复目标,**不重复泄漏**到 home
  channel(11424-11428 注释)。

### 1.11 阶段 10:恢复顺序三部曲(11437–11472)

gateway/run.py:11442-11450 @ 863e313
```python
        # Delivery-obligation redelivery runs FIRST: a session whose final
        # response was generated but never confirmed-delivered has its answer
        # in the ledger — redelivering it (and clearing resume_pending for
        # that session) is strictly cheaper and more correct than re-running
        # the whole turn.
        await self._redeliver_pending_obligations()
        self._schedule_resume_pending_sessions()
        await self._finish_startup_restore()
```

顺序即语义:① 投递台账重投(答案已生成只是没送到,重投严格优于重跑整轮);② 调度
resume_pending 会话的合成续跑轮(同步占 `_running_agents` 槽);③ 有界等待后释放入站
闸门并 drain 排队消息(gateway/run.py:10271)。之后(11451-11472)把 crash checkpoint 恢复的
进程 watcher 逐个 `_spawn_supervised(..., restart=False)` 拉起,**每 100 个
`await asyncio.sleep(0)` 让出循环**——注释:防几千个 watcher 时 O(n²) 阻塞;先把
`pending_watchers` 整体换成新 list 再遍历,避免并发 append 被 clear() 吞掉(11454-11459)。

### 1.12 阶段 11:watcher 拉起清单(11474–11564)

按序拉起(全部经 `_spawn_supervised`):

| 顺位 | watcher | 行号 | 职责一句话 |
|---|---|---|---|
| 1 | `_session_expiry_watcher` | 11475 | 过期会话 finalize + 缓存治理(见 §4) |
| 2 | `_session_stall_watcher` | 11479 | 停滞会话提醒 /new(见 §5) |
| 3 | `_kanban_notifier_watcher` | 11484 | kanban 事件投递(gateway/kanban_watchers.py:125) |
| 4 | `_kanban_dispatcher_watcher` | 11490 | kanban 任务派工(:953;`kanban.dispatch_in_gateway` 可关) |
| 5 | `_platform_reconnect_watcher` | 11515 | 失败平台重连(见 §6;唯一带 `on_spawn` 者) |
| 6 | `_handoff_watcher` | 11525 | CLI→gateway 会话交接(见 §3) |
| 7 | `_async_delegation_watcher` | 11531 | 后台子代理完成事件注回原会话(gateway/run.py:22247) |
| 8 | `_scale_to_zero_watcher` | 11545 | 条件 armed:缩容到零(`_scale_to_zero_should_arm` gateway/run.py:7494;未 armed 且已 opt-in 则打原因,11550) |
| 9 | `_drain_control_watcher` | 11560 | 对账外部 `.drain_request.json`(NS-570:靠 instantiation epoch 忽略前世遗留标记) |

reconnect watcher 的拉起注释(11499-11519)是 #70344/#71758 的完整事故记录,见 §6。
最后 `logger.info("Press Ctrl+C to stop")` + `return True`(11562-11564)。

---

## 2. `_spawn_supervised`:任务级监督(11566–11669)

**问题**(#71758):watcher 内层循环有 per-iteration try/except,但**外层**
`while self._running:` 或 setup 区抛的异常,裸 `asyncio.create_task` 直接丢地上——
无日志、无重启、watcher 无声消失。实测事故:平台已入 `_failed_platforms` 队列后
reconnect watcher 死掉,而 `_ensure_reconnect_watcher_running()` 只在**新** fatal
error 到来时被调,若再无其他平台失败,17.5 小时无人发现(上游瞬态故障早已恢复)。

**实现**:两个类常量 + 一个闭包 done-callback:

gateway/run.py:11566-11575 @ 863e313
```python
    _MAX_SUPERVISED_RESTARTS = 5
    # A task that ran at least this long before crashing is treated as having
    # been HEALTHY — its crash is a fresh, isolated failure rather than part of
    # a rapid crash-loop, so the consecutive-restart counter resets to 0. Only
    # crashes that happen within this window of a (re)spawn accumulate toward
    # ``_MAX_SUPERVISED_RESTARTS``. Without this, a long-lived launchd daemon
    # whose watcher crashes a handful of times over days would hit the cap and
    # be permanently abandoned (NS: silent loss of platform-reconnect / kanban /
    # handoff for the rest of the process life).
    _SUPERVISED_HEALTHY_SECS = 300
```

gateway/run.py:11621-11651 @ 863e313
```python
        def _done(t):
            self._background_tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc is None:
                # Clean return == deliberate shutdown or a self-disabling watcher
                # (e.g. a gated no-op that returns synchronously). Respawning here
                # would busy-spin such a watcher — so NEVER restart on clean exit.
                return
            logger.error("Supervised task %s died: %r", name, exc, exc_info=exc)
            if restart and self._running:
                ran_for = time.monotonic() - _started
                if ran_for >= self._SUPERVISED_HEALTHY_SECS:
                    # Ran healthily for a while before crashing — this is a
                    # FRESH failure, not part of a rapid crash-loop. Reset the
                    # consecutive counter so a daemon that crashes a handful of
                    # times over days is never permanently abandoned.
                    effective_attempt = 0
                else:
                    effective_attempt = _attempt
                if effective_attempt >= self._MAX_SUPERVISED_RESTARTS:
                    logger.error(
                        "Supervised task %s died %d times in rapid succession "
                        "(each within %ds of restart) — giving up restarts",
                        name,
                        effective_attempt,
                        self._SUPERVISED_HEALTHY_SECS,
                    )
                    return
                backoff = min(60, 2 ** min(effective_attempt, 6))
```

细节逐条:
- **retry 语义**:crash-loop 判定不是"总崩溃次数",而是"连续、且每次都在重启后
  `_SUPERVISED_HEALTHY_SECS=300s` 内崩"。跑满 300s 再崩视为全新故障,计数归零——
  这是对 systemd `StartLimitIntervalSec` 语义的任务级复刻。
- **退避**:`min(60, 2 ** min(effective_attempt, 6))` → 1/2/4/8/16/32(cap 60)秒;
  respawn 自身也是登记进 `_background_tasks` 的 task,stop() 可一并取消。
- **clean return 绝不重启**(11627-11630):自禁用型 watcher(如 gated no-op 同步
  return)重启即 busy-spin。
- **cancelled 不重启**(11623):停机取消不是故障。
- **`on_spawn` 回调**(11593-11599 docstring + 11612-11619):每次 spawn(**含内部
  退避 respawn**)都回调新 task 句柄。外部另存句柄的调用者(`_reconnect_watcher_task`)
  必须传它,否则监督层自己 respawn 后外部句柄指向旧 task,
  `_ensure_reconnect_watcher_running` 误判"死了"再拉一个 → **双 watcher 并发重连**。
- **不传 `name=` 给 create_task**(11608-11609 注释):测试替身 mock 的 create_task
  签名可能不收 name kwarg——为可测性牺牲 task 命名。
- 每次 spawn 捕获 `_started = time.monotonic()`(11606),健康期判定基于本次 spawn。

**调用关系**:start() 内 9 处拉起(§1.12 表);进程 watcher 恢复(11463,`restart=False`
——单个进程的 watcher 结束即终局);`_ensure_reconnect_watcher_running`(gateway/run.py:12386)。

**重实现要点**:① 长命后台任务必须有 done-callback 层监督,内层 try/except 覆盖不了
外层循环与 setup 段;② crash-loop 计数要带"健康期归零",否则以天计的偶发崩溃迟早耗尽
预算;③ clean return / cancelled 与异常严格分流;④ 外部句柄追踪者必须经 on_spawn 同步,
否则监督重启会造出并发副本;⑤ respawn 任务也要纳入统一取消集合。

---

## 3. handoff:CLI→gateway 会话交接(11671–11925)

### 3.1 `_handoff_watcher`(11671–11719):轮询-认领-执行-落终态

**问题**:用户在 CLI 里干到一半,想把会话搬到手机上的 Telegram/Discord 继续。CLI 进程
与 gateway 进程隔离,交接需要一个跨进程契约。**实现**:state.db 的
`handoff_state` 列做状态机(pending→running→completed/failed),gateway 侧 2 秒轮询:

gateway/run.py:11693-11714 @ 863e313
```python
        while self._running:
            try:
                if self._session_db is None:
                    await asyncio.sleep(interval)
                    continue
                pending = await self._session_db.list_pending_handoffs()
                for row in pending:
                    session_id = row.get("id")
                    if not session_id:
                        continue
                    if not await self._session_db.claim_handoff(session_id):
                        # Another tick or another gateway already claimed it.
                        continue
                    try:
                        await self._process_handoff(row)
                        await self._session_db.complete_handoff(session_id)
                    except Exception as exc:
                        logger.warning(
                            "Handoff for session %s failed: %s",
                            session_id, exc, exc_info=True,
                        )
                        await self._session_db.fail_handoff(session_id, str(exc))
```

- 认领是 SQL 原子操作(hermes_state.py:9645-9654:`UPDATE ... SET handoff_state=
  'running' WHERE id=? AND handoff_state='pending'`,`rowcount>0` 即认领成功)——
  多 gateway / 多 tick 并发安全。
- CLI 侧 poll-block 在终态行上,向用户打印结果(11687-11688 docstring)。
- 初始 `await asyncio.sleep(5)`(11692):等平台全部连好再派发。
- 失败落 `handoff_error`(截 500 字,hermes_state.py:9672),用户在 CLI 看得到原因。

### 3.2 `_process_handoff`(11721–11925):七步交接

1. **解析平台 + 活体传输**(11727-11749):`Platform(platform_name)`;
   `resolve_delivery_transport(platform, self.config, self.adapters)`
   (gateway/delivery.py:92)。注释交代为何不能直接 `adapters.get(discord)`:relay
   前置的 gateway 只注册**一个** `Platform.RELAY` 适配器却前置 N 个逻辑平台,共享解析器
   做别名匹配(native 优先;relay 仅当其认证过的 transport 声明前置该逻辑平台)。
2. **home channel 必须已配置**(11752-11757):没有就抛"run /sethome on the desired
   chat first"。
3. **尝试开新线程**(11760-11784):`adapter.create_handoff_thread(chat_id,
   f"Hermes — {cli_title}")`(gateway/platforms/base.py:3525)。返回 None(平台不支持
   线程:Matrix/WhatsApp/Signal/SMS;或无权限/topics 关闭/父级是 DM)则降级直投 home
   channel——"合成轮仍然落地,只是没有线程隔离"。
4. **目的地 SessionSource 构造**(11786-11836)——两个平台特例是本函数的知识密度所在:
   - **Telegram 私聊 topic**(11789-11809):TG 私聊(正 chat_id)里 handoff 建的
     topic,入站适配器会按 **DM-topic** 形状上报;若合成轮按通用 `thread` 形状绑 key,
     用户下一条真实回复会落在 `dm` 形状的**另一个** session key 上。故
     `looks_like_telegram_private_chat_id`(gateway/delivery.py:134)命中时强制
     `chat_type="dm"` 且 `user_id=chat_id`(与后续真实入站同一身份)。
   - **Discord 线程 key**(11810-11827):Discord 适配器给线程内自然消息的
     `chat_id == 线程自身 id`(session key 形如 `…:thread:{thread}:{thread}`);handoff
     若按父频道 keyed(`…:thread:{parent}:{thread}`),用户在线程里回话会解析到不同
     key、另起新会话。Slack/Telegram 则相反(chat_id==父频道)。故仅 Discord 线程用
     `dest_chat_id = effective_thread_id`。
5. **session key 重绑**(11843-11864):用与适配器完全相同的规则
   `build_session_key(dest_source, group_sessions_per_user=..., thread_sessions_per_user=...)`
   (gateway/session.py;thread 默认不按 user 分 → 线程内下一条真实消息共享本会话);
   `get_or_create_session` 确保条目存在,`switch_session(session_key, cli_session_id)`
   (gateway/session.py:2993)把 gateway key 指向 CLI 的 session_id——完整角色化转写
   在下一轮 agent 里重放。
6. **缓存与运行态清场**(11866-11872):`_evict_cached_agent(session_key)`(与
   /resume、/branch 同路)+ `_release_running_agent_state(session_key)`(合成轮不能
   排在陈旧 running 旗后面)。
7. **合成轮 + 直调派发**(11874-11924):`MessageEvent(text=..., internal=True)`;

gateway/run.py:11894-11898 @ 863e313
```python
        # Dispatch through the runner directly. Going through
        # adapter.handle_message would spawn a background task and we'd
        # lose synchronous error visibility; calling _handle_message inline
        # keeps the success/failure path observable for the watcher.
        response_text = await self._handle_message(synthetic_event)
```

   返回空文本视为成功(流式可能已内联投递);非空则经 `transport.send(platform, ...)`
   补投(**不走** adapter.send 直连——relay 前置时出站帧要盖逻辑平台戳,
   send_for_platform,11904-11908 注释),`SendResult.success=False` 亦抛错 → 上层落
   failed。

**◇ 文档-代码出入候选 2(作者自认)**:11821-11823 注释明说 Slack 的 chat_type 归一化
问题——handoff 用 "thread" 而 Slack 自然消息用 "group"——"is a separate issue",即
Slack 目的地上 handoff 合成轮与后续真实回复可能 key 形状不一致,基线未修。

**重实现要点**:① 跨进程交接用 DB 行状态机 + 原子 UPDATE 认领,天然多消费者安全;
② 交接目的地的 session key 必须按"入站适配器将来会怎么算 key"逆向构造(平台差异是
主要坑源);③ 合成轮同步内联执行以保住错误可见性;④ 每步降级都有落点(无线程→home
channel;空响应→视为已投);⑤ 终态必须写回(completed/failed+error),发起方靠它解除
阻塞。

---

## 4. `_session_expiry_watcher`:过期 finalize 与缓存治理(11926–12102)

**问题**:会话有 reset 策略(N 小时无活动即过期),但过期不只是"下次重开新 id"——
缓存的 AIAgent(LLM 客户端、工具 schema、memory provider 引用)、conversation-scoped
状态字典若不清,gateway 常驻数月后内存无界增长。

**实现**:300s 一轮,先 60s 初始延迟。每轮四件事:

1. **收集过期会话**(11940-11964):遍历 `session_store._entries`,跳过
   `entry.expiry_finalized`,`_is_session_expired(entry)` 判定;先聚合再打一条摘要日志
   (从 key `agent:main:telegram:dm:12345` 取字段 [2] 作平台名统计)。
2. **逐个 finalize**(11966-12042),五步:
   - `hermes_cli.lifecycle.finalize_session(...)` 钩子(reason="session_expired");
   - 找 cached agent:先 `_agent_cache`(带锁),兜底 `_running_agents`(过期时可能
     还在轮中),`_AGENT_PENDING_SENTINEL`(gateway/run.py:2465)排除;
     `_cleanup_agent_resources_off_loop`(关 memory provider、工具资源,**off-loop**
     ——阻塞型清理不占事件循环);
   - `_evict_cached_agent(key)` 释放引用链;
   - `_clear_conversation_scope(key, reason="expiry_finalized")`——注释(12002-12014)
     划出重要边界:**真终局**(finalize、/new、/reset)才清 conversation 状态与边界
     安全态(approvals、update 提示、slash 确认);**闲置缓存驱逐不许清**——会话还活
     着,resumed 轮要靠这些 overrides 重建 agent;
   - `set_expiry_finalized(entry)`(gateway/session.py:2035,#9006 单写路:
     sessions.json 与 state.db 一起落,顺带清持久化的 /model override——finalize 即
     会话边界)。
   - **失败重试上限**(11936-11937, 12025-12042):连续失败 `_MAX_FINALIZE_RETRIES=3`
     次后强行 `set_expiry_finalized(entry, clear_model_override=False)` 止损——
     "Marking as finalized to prevent infinite retry loop",宁可漏清一次资源,不做
     每 5 分钟永动重试。
3. **闲置 agent 扫除**(12059-12071):`_sweep_idle_cached_agents()`(gateway/run.py:23650)
   ——针对 reset 窗口极长 / "never" 的会话,cached AIAgent 按闲置 TTL 驱逐(不做
   finalize,只是掉缓存)。
4. **SessionStore 陈旧条目修剪**(12073-12095):每小时一次,
   `session_store_max_age_days > 0` 时 `prune_old_entries(_max_age)`
   (gateway/session.py:2800)。注释:对用户不可见——"a resumed session just gets a
   fresh session_id, exactly as if the reset policy fired"。

睡眠可中断(12099-12102):`for _ in range(interval): if not self._running: break;
await asyncio.sleep(1)`——300s 大觉拆成 1s 小觉,停机最多迟 1 秒。

**重实现要点**:① "过期"要拆成三层动作:业务 finalize 钩子 → 资源关停(off-loop)→
状态清空 + 持久化落旗;② 清 conversation 状态只允许发生在真会话边界,缓存驱逐≠边界;
③ finalize 失败必须有次数上限并强制落旗,否则失败会话成为永动机;④ 三个不同 TTL 治理
三种增长源(过期策略→finalize;闲置→agent 缓存;年龄→store 条目);⑤ 长周期 watcher
的 sleep 必须可中断。

---

## 5. stall 看门狗五件套(12104–12353)+ gateway/session_stall.py

**问题**(#72016):用户发了消息排在队里,agent 却已停止一切活动(上游 hang、工具死锁)
——用户视角是"已读不回"。需要一个**只提醒、不杀轮**的看门狗(对比 `gateway_timeout` /
`shutdown_watchdog` 是杀伐系)。

**架构分工**:run.py 持状态与 I/O,gateway/session_stall.py 是**纯函数策略层**
(可独立单测):

- `resolve_session_idle_seconds_from_activity`(gateway/session_stall.py:72):只从共享活动
  快照取 idle——优先 `seconds_since_activity`(有限值),否则
  `last_activity_at/last_activity_ts` 推导;都没有则 None。**契约**(#72039):进度的
  唯一来源是 `AIAgent.get_activity_summary()`,"callers must not fall back to
  turn-start or pending-inbound clocks"——待办消息是**策略闸**不是**进度钟**。
- `should_emit_session_stall_notification`(:27):timeout>0 ∧ 有 pending ∧ 未通知过
  ∧ idle 已知 ∧ idle≥timeout。
- `should_clear_session_stall_notification`(:46):无 pending 或 timeout≤0 即清;
  **idle 未知时保持 latch**(:57 "Do not treat observation gaps as recovery")。
- `format_session_stall_notification`(:63):"⚠️ Agent session appears stalled
  (last activity N min ago). Try /new to reset."

run.py 侧:

- `_session_stall_timeout_seconds`(12104-12106):`HERMES_SESSION_STALL_TIMEOUT`
  默认 300s,0 关闭。
- `_iter_gateway_adapters`(12108-12127):default `adapters` + 全部
  `_profile_adapters`,按 `id(adapter)` 去重(同一适配器可能出现在多映射)。
- `_session_activity_for_stall`(12129-12144):从 `_running_agents[key]` 取
  `get_activity_summary()`,sentinel/异常/非 dict 皆 None。
- `_check_session_stalls`(12146-12328)每轮:
  1. **候选收集**:各适配器 `_pending_messages` 槽 + runner 级 `_queued_events`
     溢出队(12167-12185,后者需 `_adapter_for_source` 反解适配器);
  2. **策略判定**:先 clear 后 emit(12197-12211),`notified_map`
     (`_session_stall_notified`)实现"每停滞事件仅一次"latch;
  3. **发送前二次核验**(#76354 review S2,12243-12277):

gateway/run.py:12243-12248 @ 863e313
```python
            # #76354 review S2: re-read pending state + activity timestamp
            # IMMEDIATELY before delivery. The snapshot above ages while
            # earlier candidates in this pass await their sends; an agent
            # that made progress (or drained its queue) in that window must
            # not receive a false stall notice. Abort and leave the latch
            # un-set so the next tick re-evaluates from scratch.
```

     ——同一轮里前序候选的 await send 会让快照变老,发送前重读 pending + fresh idle,
     已恢复者放行且**撤 latch**(12276)。
  4. **有界发送**(12288-12304):`asyncio.wait_for(adapter.send(...),
     timeout=_STALL_NOTIFY_SEND_TIMEOUT_SECONDS=15.0)`(常量 gateway/run.py:85)——Round-2
     审阅点:卡死的传输不能堵死整轮扫描与后续候选;超时/`SendResult.success=False`/
     异常三路都**不落 latch**,下轮重试;仅确认送达才 `notified_map[key]=True`。
     特例:无 chat_id 无法投递时**落 latch**(12236-12242)防每轮刷日志。
  5. **latch 回收**(12323-12326):不在候选集里的 key 全部撤 latch(事件结束)。
- `_session_stall_watcher`(12330-12352):30s 周期;初始延迟
  `min(30, max(1, interval))`——"startup reconnect noise does not false-fire";每轮
  重读 timeout(env 可热改);睡眠同样 1s 分片可中断。

**重实现要点**:① 策略(何时报/何时清)做成纯函数与 I/O 分离,单测覆盖边界;② 进度
判定只认单一观测源,禁止用"消息等了多久"冒充"agent 停了多久";③ 通知按"事件"去重
(latch),恢复即撤 latch 允许下次事件再报;④ 发送前必须用新鲜状态复核,失败/超时不落
latch;⑤ 通知发送必须带超时,监视器自身不可被被监视对象拖死。

---

## 6. reconnect watcher(12368–12602)与 secondary 收尾(12603–12633)

### 6.1 `_ensure_reconnect_watcher_running`(12368–12390)

被调点:`_handle_adapter_fatal_error` 入队 retryable 失败后(gateway/run.py:7345)。tracked
task 已 done(重启预算耗尽 / 终态异常)则 WARN 并重拉;活着则直接返回。与
`_spawn_supervised(on_spawn=...)` 配合闭环:on_spawn 保证句柄永远指向当前活 task,
本函数因此不会把"被监督层换代过的 watcher"误判为死(否则双 watcher 并发重连,见 §2)。

### 6.2 `_platform_reconnect_watcher`(12392–12601)

**策略宣言**(docstring 12393-12405):退避 30→60→120→240→300s 封顶
(`_reconnect_backoff` gateway/run.py:3665:`min(30 * 2**(attempt-1), 300)`);retryable 在
封顶频率**无限重试**(网络恢复即自愈,永不要求人工干预);non-retryable 立即出队;
熔断器(`/platform pause/resume`)保留为**手动**工具——

gateway/run.py:12401-12405 @ 863e313
```python
        remains available for manual operator control via ``/platform list``
        and ``/platform resume <name>``, but is no longer triggered
        automatically — auto-pausing a recovered platform was the cause of
        bots silently staying dead after a transient DNS failure.
```

主循环逐平台(10s 一轮扫描,空队时 30s 检查一次;所有 sleep 1s 分片可中断):

1. **并发消失容忍**(12422-12428):快照 keys 后逐个 `get`,None(被 /platform resume
   或他路成功摘除)直接 continue;
2. **paused 跳过**(12429-12432)、**未到 next_retry 跳过**(12433-12434);
3. **空凭据出队**(12439-12448,#64674):队里的 config 无 bot 凭据永远连不上,直接
   删除防 multiplex 场景空转;
4. **全新 adapter + 同款 handler 装配**(12456-12474,与 §1.6 清单逐行同构);
5. **保留服务端队列的重连**(12477-12481,#46621):`_connect_adapter_with_timeout(
   adapter, platform, is_reconnect=True)`——`is_reconnect` 透传给 `adapter.connect()`,
   区分"冷启动丢弃陈旧队列"与"断线重连保留离线期间的消息"(gateway/run.py:6613-6618
   docstring);
6. **成功路**(12482-12518):挂 `self.adapters`、同步 voice(#60623 重连也要接
   `_voice_input_callback`)、刷 delivery_router、出队、status `connected`、重建
   channel directory;最后补一刀:

gateway/run.py:12505-12512 @ 863e313
```python
                        # A platform that was offline at gateway startup never
                        # got its restart-interrupted sessions auto-resumed —
                        # the startup pass skips sessions whose adapter isn't
                        # connected yet. Now that it's back, retry the
                        # auto-resume scoped to this platform so recovery
                        # doesn't silently wait for a manual user message.
                        try:
                            self._schedule_resume_pending_sessions(platform=platform)
```

   ——启动时离线的平台错过了 resume pass,重连成功即补跑(按平台限定范围)。
7. **失败三路皆强制 dispose**(#37011,fd 泄漏事故):non-retryable(12520-12540,
   dispose 后出队)、retryable(12541-12570,dispose 后按退避重排)、异常
   (12571-12595,dispose 后按退避重排)。事故完整因果在 `_dispose_unused_adapter`
   docstring(gateway/run.py:3606-3634):watcher 每次重试**新建** adapter,失败即弃、无人调
   disconnect;`APIServerAdapter.__init__` 开的 SQLite ResponseStore 持 2 fd(db+WAL),
   asyncio 绑定对象 Python 循环 GC 不及时回收 → 300s 封顶下 ≈12 fd/小时 → 默认 2560
   ulimit 约 12 小时耗尽 → 所有 open() 抛 `[Errno 24]`,gateway 成僵尸。修复:三路
   统一调 `_dispose_unused_adapter`(内部 `await adapter.disconnect()` 吞 Exception
   不吞 CancelledError,半构造对象 disconnect 抛错不许击穿 watcher)。

### 6.3 `_cancel_secondary_profile_reconnect_tasks`(12603–12633)

停机路径专用:secondary profile 的重连是 per-profile 的独立 task
(`_profile_failed_platforms` 里存 Task),停机时先 cancel 再 bounded
`asyncio.wait(tasks, timeout=_adapter_disconnect_timeout_secs())`——一个在 adapter
setup 中等待的重连不许在 secondary registry 已 drain 后**再发布**adapter;等不完也
安全:"the stopped runner state still prevents it from installing an adapter when it
eventually resumes"(12608-12610)。

**重实现要点**:① 重连策略三分:瞬态无限退避重试(自动自愈)、致命立即出队示众、暂停
仅手动——自动熔断曾是"恢复后还死着"的根因;② 每次重试新建的对象若失败必须显式
dispose,不能指望 GC(fd 泄漏以小时计积累);③ 重连成功要补跑该平台错过的启动期恢复
动作;④ 重连与停机的竞态用"先取消 + 有界等 + 状态兜底"三层防;⑤ watcher 自身要有
"看门狗的看门狗"(`_ensure_...` + on_spawn 句柄同步)。

---

## 7. systemd watchdog 启停对(12635–12658)

gateway/run.py:12635-12649 @ 863e313
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

- **调用时机**(gateway/run.py:26935-26940):在 run_gateway 主流程里,适配器 + cron 线程 +
  housekeeping 线程**全部**到达 running 边界后才调——`READY=1` 的含义被严格定义为
  "全系统就绪",Type=notify 下 systemd 依赖此点判定启动完成。
- `SystemdWatchdog`(gateway/systemd_notify.py:60)不是无脑喂狗:`record_tick`
  (:125-138)比较"计划醒来时刻 vs 实际醒来时刻",lag 超过容忍(默认 interval 的
  25%,至少 0.1s)即**停止喂狗**并 `STATUS=watchdog unhealthy: event loop progress is
  late`——事件循环卡顿时**故意**让 systemd 的 WatchdogSec 杀掉进程重启,这正是 armed
  watchdog 的意义(喂狗任务是 asyncio task,循环冻结自然停喂,双保险)。喂狗节奏为
  interval/2(:144)。
- `_stop_systemd_watchdog`(12651-12657):**先**置 `self._systemd_watchdog = None`
  再 `await watchdog.stop()`(发 `STOPPING=1` 至多一次)——docstring 点名顺序动机:
  "Stop heartbeats before any potentially long shutdown drain",drain 可能超过
  WatchdogSec,不先停喂/告知 STOPPING 会被 systemd 误杀于停机途中。

**重实现要点**:① READY 只在全子系统就绪后发,别在 adapter 连上时抢发;② 喂狗要绑定
"事件循环真实进度"(计划 vs 实际醒来),循环卡顿时主动断喂借 supervisor 之手重启;
③ 停机第一步是停喂 + STOPPING,否则长 drain 会触发 watchdog 误杀;④ start/stop 幂等
(已存在返回 True / None 检查)。

---

## 8. 文档-代码冲突/出入候选汇总

| # | 位置 | 内容 |
|---|---|---|
| ▲1 | gateway/run.py:10668 | `start()` docstring "Returns True if at least one adapter connected successfully" 与实现不符:所有路径(含 0 连接降级、拒启、mid-startup 停机)皆 return True;真实信号是 `_exit_code`/`_request_clean_exit`。 |
| ◇2 | gateway/run.py:11821-11823 | 作者自认未修:Slack 目的地 handoff 用 chat_type="thread" 而 Slack 自然线程消息用 "group",key 形状潜在不一致("a separate issue")。 |
| ◇3 | gateway/run.py:12395 vs 3665 | reconnect docstring 写 "30s → 60s → 120s → 240s → 300s (cap)";公式第 5 次实为 480→封顶 300,序列一致但"240 之后直接 300"是封顶所致,非等比——读文档者可能误推 4 次后即封顶(实为第 5 次起)。轻微,不算冲突。 |
| ◇4 | gateway/run.py:11577 段 | `_spawn_supervised` 是**任务级**监督,与 systemd/launchd 的**进程级**监督、以及 shutdown_watchdog 的**循环级**监督构成三层;仓库文档(website/docs)对这三层未见统一叙述,成品章值得画清。 |

---

## 9. 本段引用的 issue 台账

#70344(冻结取证 + connect 超时 detach + reconnect watcher 句柄)、#71671(faulthandler
无 stderr 回退)、#17691(脱敏默认开)、#7536(重启悬挂 + stuck-loop)、#64674(multiplex
空凭据跳过/出队 + 孤儿平台告警)、NS-609(混合失败不退 78)、#51228(s6 finish→125)、
#5196(fleet 降级 cron-only)、#66892(loop 心跳文件)、#46621(重连保留服务端队列)、
#60623(重连接 voice 回调)、#37011(未安装 adapter 的 fd 泄漏)、#71758(watcher 无声
死亡 17.5h)、#72016/#72039(stall 看门狗与单一进度源契约)、#76354(发送前二次核验)、
NS-570(drain 标记 epoch)、#9006(finalize 单写路)、#69089(loop_watchdog config-only
开关)、#48031/#58403/#10702/#35809(conversation-scope 清理清单漂移史,`_clear_conversation_scope` 背景)。
