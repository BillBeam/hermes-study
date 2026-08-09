# r9c 底稿 · 可观测性与外发 —— agent 把自己往外说的全部通道

> 本片精读 13 个文件(3,164 行),主题是 **egress(外发)**:指标/事件、OTLP 导出、
> 健康判据、trace 上传、出站 webhook,外加 TLS 校验那两个小文件。
> 一切断言紧跟 `路径:行号 @ 863e313` 与代码原文块;锚点单独成行、置于块之前。
> 非源码块(我自己的运行输出、命令)一律用 ```text / ```console / ```verify 标注。

## 0. 这一簇是什么:两条互不相干的外发线

读完 13 个文件最先要建立的认知是:**它们不是一个系统,是两条设计哲学相反的外发线,
恰好都往外发东西。**

| 线 | 文件 | 载荷 | 脱敏 | 谁开 |
|---|---|---|---|---|
| **监控面**(content-free plane) | `agent/monitoring/*`(9 个) | 只有**枚举值、计数、哈希** | 无条件、且导出侧还有白名单 | 运维在 config 里显式开 |
| **内容面**(content-bearing) | `agent/trace_upload.py`、`agent/outbound_webhooks.py` | **完整会话 / 完整工具入参与结果** | 一个强制脱敏、一个**完全不脱敏** | 用户显式命令 / 用户写 config |

`agent/ssl_guard.py` 与 `agent/ssl_verify.py` 是两条线共同踩的地板(其实只有 LLM provider
那条 httpx 线踩得到,见 §7)。

监控面自己把这条界线写死在模块文档里。

`agent/monitoring/__init__.py:12`

```
Deliberately out of scope here: run/model/tool trajectory capture, usage
analytics, and any content-bearing signal. Those planes are served by the
NeMo Relay integration and its Hermes-owned subscribers.
```

这句话是本片所有设计取舍的总纲:**监控面是「出口」不是「存储」,而且刻意不碰内容面。**
内容面另有其人(trace 上传、出站 webhook、NeMo Relay),它们**不共用**监控面的脱敏管道
——这是本片最重要的一条发现(§6)。

---

## 1. 事件模型:`events.py` + `emitter.py`

### 1.1 先看一次具体的走法

gateway 里某个平台(比如 Slack 连接器)挂了。发生了什么:

1. `gateway/status.py` 写运行时状态文件,写完调 `emit_runtime_status_transition(previous, current)`;
2. 该函数把 `slack: {state: "fatal", error_message: "auth failed for alice@corp.com token sk-live-..."}`
   这条**原始状态**压成一个 `GatewayDiagnosticEvent`,其中 `error_message` 已经被
   `classify_gateway_error()` 折成枚举串 `"auth_failed"`,**原文根本没进事件体**;
3. 事件 `put_nowait` 进一个深 10,000 的环形队列,**调用方立刻返回**;
4. 一个 daemon 线程把队列排空,按批扇出给订阅者(OTLP 的 span / log 流);
5. 每个订阅者被 try/except 包死,谁抛异常都影响不到 gateway,也影响不到别的订阅者。

### 1.2 事件长什么样:三种,全部是 dataclass

`agent/monitoring/events.py:1`

```
"""Typed gateway monitoring events.

Content-free service-health and redacted diagnostic events for the gateway
daemon. These are the only event shapes the monitoring plane emits: no
prompts, messages, tool args/results, session history, or usage analytics.
"""
```

三种事件:

**① 健康 / 生命周期。**

`agent/monitoring/events.py:19`

```
@dataclass(slots=True)
class GatewayHealthEvent:
    """Content-free gateway health snapshot or lifecycle event."""
```

**② 诊断。**

`agent/monitoring/events.py:45`

```
@dataclass(slots=True)
class GatewayDiagnosticEvent:
    """Redacted gateway diagnostic event for operator-owned observability."""
```

**③ cron 执行投影。**

`agent/monitoring/events.py:66`

```
@dataclass(slots=True)
class CronExecutionEvent:
    """Content-free durable cron execution lifecycle projection."""
```

统一的序列化契约:每个都有 `to_dict()`,并在字典里塞一个 `event` 判别键。

`agent/monitoring/events.py:41`

```
    def to_dict(self) -> Dict[str, Any]:
        return {"event": "gateway_health", **asdict(self)}
```

**设计点(值得抄):判别键不是类名,是一个显式字符串常量。**下游(`_span_attrs`、
`_diagnostic_log_attributes`、`event_filter`)全部按这个字符串分派,于是订阅者不需要
import 事件类,批次就是纯 `list[dict]`。代价是加一种事件/属性要在多张白名单上分别登记,而这些白名单散落在两个模块里(见 ▲-3)。

`GatewayHealthEvent` 的字段全是**有界值**——状态串来自闭集、平台数是 int、
`install_id`/`profile` 是标识符。注意 `ts_ns` 用 `field(default_factory=_now_ns)`,
即**事件构造时刻**打时间戳,不是出队时刻。

### 1.3 emitter:热路径不变式

`agent/monitoring/emitter.py:5`

```
the hot-path invariant:

    ``emit()`` MUST return in O(microseconds), MUST NOT block on disk/network,
    and MUST NEVER raise into the caller. A monitoring failure is logged
    locally and dropped — it can never affect the gateway or a session.
```

实现只有一个函数值得逐行看。

`agent/monitoring/emitter.py:53`

```
    def emit(self, event: Any) -> None:
        """Enqueue an event. Never blocks, never raises.

        ``event`` may be a dataclass with ``to_dict()`` or a plain dict.
        """
        if not self._enabled:
            return
        try:
            payload = event.to_dict() if hasattr(event, "to_dict") else dict(event)
            payload.setdefault("ts_ns", time.time_ns())
            self._ensure_started()
            try:
                self._q.put_nowait(payload)
            except queue.Full:
                # Drop oldest to make room — bounded memory, newest-wins.
                try:
                    self._q.get_nowait()
                    self._q.task_done()
                    self._dropped += 1
                    self._q.put_nowait(payload)
                except Exception:
                    self._dropped += 1
        except Exception:  # the hot-path invariant: never propagate
            logger.debug("monitoring emit failed", exc_info=True)
```

四层保护,逐层解释它防什么:

1. `if not self._enabled: return` —— **没人订阅时零成本**。单例默认 `enabled=False`,
   第一个订阅者 `subscribe()` 才打开它。于是 `gateway/status.py`、`cron/executions.py`
   这些生产者可以无条件调 `emit()`,不必自己判断监控开没开。

   `agent/monitoring/emitter.py:178`

   ```
        if _EMITTER is None:
            # Collection is opt-in. A plane exporter enables the singleton by
            # attaching its first subscriber; until then producers are no-ops.
            _EMITTER = MonitoringEmitter(enabled=False)
    return _EMITTER
   ```

2. `put_nowait` —— 绝不阻塞。
3. `queue.Full` 分支 —— **丢最旧、留最新**(newest-wins)。理由:监控事件里最新的那条
   最可能是"刚刚出事了",丢它最亏。
4. 最外层裸 `except Exception` —— 热路径不变式的兜底,连 `to_dict()` 抛异常都吞掉。

丢弃策略实测(把环深从 10,000 改成 4,连发 7 条):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'EOF'
import sys, queue
sys.path.insert(0, "/home/user/hermes-agent")
import agent.monitoring.emitter as E
em = E.MonitoringEmitter(enabled=True)
em._q = queue.Queue(maxsize=4)
em._started = True          # 假装 dispatcher 已起,这样没人排空队列
for i in range(7):
    em.emit({"event": "gateway_health", "name": f"e{i}"})
kept = []
while not em._q.empty():
    kept.append(em._q.get_nowait()["name"])
print("kept:", kept, "stats:", em.stats())
EOF
```

```console
kept: ['e3', 'e4', 'e5', 'e6'] stats: {'queued': 0, 'dispatched': 0, 'dropped': 3, 'subscribers': 0}
```

### 1.4 扇出与失败隔离

`agent/monitoring/emitter.py:109`

```
    def _dispatch(self, batch) -> None:
        # Fan-out to subscribers (OTLP streamers) — fully fail-isolated.
        for sub in list(self._subscribers):
            try:
                sub(batch)
            except Exception:
                logger.debug("monitoring subscriber failed", exc_info=True)
        self._dispatched += len(batch)
```

`list(self._subscribers)` 做了一次快照,于是订阅者在回调里 `unsubscribe` 自己
(`OTLPStreamer.shutdown` 正是这么干的,`agent/monitoring/otlp_exporter.py:207`)不会
炸掉遍历。每个订阅者独立 try,一个慢/抛异常的订阅者影响不到同伴。

### 1.5 `flush()` 是什么级别的屏障

`agent/monitoring/emitter.py:133`

```
    def flush(self, timeout: float = 2.0) -> None:
        """Wait boundedly for queued and in-flight batches to finish dispatch."""
        if timeout <= 0:
            return

        finished = threading.Event()

        def _wait_for_completion() -> None:
            self._q.join()
            finished.set()

        waiter = threading.Thread(
            target=_wait_for_completion,
            name="hermes-monitoring-flush",
            daemon=True,
        )
        waiter.start()
        finished.wait(timeout=timeout)
```

dispatcher 的 `task_done()` 在 `finally` 里、**在 `_dispatch(batch)` 之后**调。

`agent/monitoring/emitter.py:103`

```
            try:
                self._dispatch(batch)
            finally:
                for _ in batch:
                    self._q.task_done()
```

所以 `_q.join()` 返回意味着**所有订阅者的 `__call__` 都已执行完**。但订阅者本身(`OTLPStreamer`)只是把 span 交给
`BatchSpanProcessor`,那又是一层异步。所以:

> `emitter.flush()` = "事件已交到 exporter 手里",**不等于**"已经上网"。

真正的网络刷新要靠 `processor.force_flush()`。`gateway_health_export` 的关停顺序把这两层
分开处理,是本片写得最漂亮的一段(§4.4)。

代价:`flush()` **每次调用起一个新线程**,并且不 join 它。若队列因故永远排不空,
这个 waiter 线程就永远挂着(daemon,进程退出无碍)。`cron_health.emit_execution_state`
在每个终态 cron 执行后都调一次 `flush(timeout=1.0)`,即**每个 cron 任务收尾起一个线程**。

---

## 2. 策略与脱敏 —— 本片挖得最深的一节

### 2.1 `policy.py`:install id 不是账号,是"这台实例"

`agent/monitoring/policy.py:1`

```
"""Install identity for gateway monitoring.

The install id is a stable, resettable pseudonymous identifier attached to
exported health signals so an operator can tell instances apart in their
collector. It carries no account identity and can be rotated by clearing
``monitoring.install_id`` in config.
"""
```

`agent/monitoring/policy.py:35`

```
    minted = str(uuid.uuid4())
    try:
        from hermes_cli.config import load_config, save_config

        fresh = load_config()
        if isinstance(fresh, dict):
            slot = fresh.setdefault("monitoring", {})
            if isinstance(slot, dict) and not str(slot.get("install_id") or "").strip():
                slot["install_id"] = minted
                save_config(fresh)
    except Exception:
        logger.debug("install_id persist failed; using ephemeral id", exc_info=True)
    # Keep the in-memory config consistent for this process either way.
    if isinstance(config, dict):
        config.setdefault("monitoring", {})
        if isinstance(config["monitoring"], dict):
            config["monitoring"]["install_id"] = minted
    return minted
```

设计意图清楚:id 必须跨重启稳定(它会变成 `service.instance.id`),所以新铸的 UUID
**立刻回写 config.yaml**;写失败 fail-open,用临时 id 继续跑。

#### ■-1 `ensure_install_id` 会丢弃磁盘上已存在的 id,破坏实例身份连续性

第 42 行的条件是 "**磁盘上没有** id 才写盘",但第 48-51 行**无条件**把 `minted` 写回内存
并 `return minted`。于是当传入的 `config` 里没有 install_id、而磁盘上有时,
进程导出的 `service.instance.id` 与磁盘上那个**对不上**。实测:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'EOF'
import os, sys, pathlib, tempfile
home = pathlib.Path(tempfile.mkdtemp())
(home / "config.yaml").write_text("monitoring:\n  install_id: PERSISTED-ON-DISK\n")
os.environ["HERMES_HOME"] = str(home)
sys.path.insert(0, "/home/user/hermes-agent")
from agent.monitoring.policy import ensure_install_id
from agent.monitoring.gateway_health import _safe_instance_id
stale = {"monitoring": {}}                     # 调用方内存里的 config 是旧的/合成的
got = ensure_install_id(stale)
print("returned :", got)
print("on disk  :", (home / "config.yaml").read_text().split("install_id:")[1].strip())
print("MATCH?   :", _safe_instance_id(got) == _safe_instance_id("PERSISTED-ON-DISK"))
EOF
```

```console
returned : 29ee56a1-82fa-490a-bb37-aa61c5e9cead
on disk  : PERSISTED-ON-DISK
MATCH?   : False
```

触发面:(a) 两个进程并发首启(gateway + `scripts/observability/gateway_health_export_probe.py`),
后写的那个会看到 slot 已满 → 跳过写盘 → 返回自己铸的;(b) 任何拿合成 config 调用的路径。
影响正对着文档自己的验收项 `docs/observability/monitoring.md:172`:

`docs/observability/monitoring.md:171`

> 5. **Killed gateway:** terminate one canary, verify missing-series detection,
>    restart it, and confirm the same opaque instance identity returns.

一行可修:第 42 行的 `if` 不成立时 `return slot["install_id"]`。

### 2.2 `redaction.py`:一条无条件的洗手管道

`agent/monitoring/redaction.py:1`

```
"""Redaction applied to monitoring data before egress.

One unconditional scrub, no modes, no knobs. Every string that leaves the
process passes through ``redact_for_export``:

  * Secrets first — wraps ``agent/redact.py::redact_sensitive_text(force=True)``
    plus bearer/token-shape patterns, and fails CLOSED: if the redactor cannot
    run, the raw string is never emitted.
  * PII second — e-mail addresses, phone numbers, and UUID-shaped identifiers
    are rewritten to ``[email]`` / ``[phone]`` / ``[id]``.

There is deliberately no setting to weaken this. The monitoring plane is
content-free by design: rendered log messages are not exported, and bounded
structured strings are still scrubbed as defense-in-depth. This redactor also
remains available for a future, explicitly gated redacted-message detail mode.
"""
```

`agent/monitoring/redaction.py:43`

```
def _secret_redact(text: str) -> str:
    """Always-on secret redaction. force=True so user config can't disable it."""
    try:
        from agent.redact import redact_sensitive_text
        out = redact_sensitive_text(text, force=True)
    except Exception:
        # Fail CLOSED: if the redactor can't run, do not emit the raw string.
        return "[redaction-unavailable]"
    out = _BEARER_RE.sub("[redacted]", out)
    out = _TOKEN_RE.sub("[redacted]", out)
    out = _SECRET_LITERAL_RE.sub("[redacted]", out)
    out = _BEARER_RESIDUE_RE.sub("[redacted]", out)
    return out


def redact_for_export(text: Optional[str]) -> Optional[str]:
    """Scrub a string for egress: secrets, then PII. Unconditional."""
    if text is None:
        return None
    out = _secret_redact(str(text))
    out = _EMAIL_RE.sub("[email]", out)
    out = _UUID_RE.sub("[id]", out)
    out = _PHONE_RE.sub("[phone]", out)
    return out
```

结构上有三个决定值得单独拎出来:

1. **fail CLOSED**。第 48-50 行:底层 `agent/redact.py::redact_sensitive_text` 抛异常时
   返回 `"[redaction-unavailable]"`,**绝不返回原文**。这是脱敏器唯一正确的失败方向,
   而热路径不变式(§1.3)恰恰是相反方向的 fail-open——**同一个模块里两种失败方向并存,
   各自对着自己该保的东西**,是很值得抄的一课:可用性 fail-open,机密性 fail-closed。
2. **`force=True`**。用户把全局日志脱敏关掉,不影响这条出口。
3. **顺序:secrets → email → uuid → phone**。UUID 必须排在 phone 前面,否则电话正则会
   啃掉 UUID 的一部分,留下半截。

### 2.3 逐条对照:脱敏名单 vs 真正会进入事件体的字段

这是本片被点名要深挖的地方。先说结论:

> **`redact_for_export` 的正则名单并不是这条外发线的主要防线;主要防线是"事件体里根本
> 就没有自由文本"。** 脱敏是第二层,而且它只在**导出侧**跑,不在事件构造侧跑。

逐字段核对(下表的"进入事件体的形态"全部有代码依据,见其后的锚点):

| 事件字段 | 值的来源 | 进入事件体时已经是什么 | 还需要脱敏吗 |
|---|---|---|---|
| `GatewayDiagnosticEvent.error_class` / `error_code` | 平台原始 error_message | `classify_gateway_error()` 的 **9 个枚举串之一** | 不需要 |
| `GatewayHealthEvent.exit_reason` | 关停原文 | `classify_exit_reason()` 的有界串 | 不需要 |
| `gateway_state` / `old_state` / `new_state` | 状态文件 | `_bounded_state()` 卡进闭集,不在集内一律 `unknown` | 不需要 |
| `subsystem` / `platform` | 平台名(config 里的键) | **原样 `str()`**,唯一的自由文本入口 | **需要** |
| `CronExecutionEvent.job_key` | job_id(可能含人名、收件人) | `sha256(...)[:24]` | 不需要 |
| `CronExecutionEvent.status` / `source` / `delivery_outcome` | 执行记录 | 闭集,不在集内 → `unknown` / `None` | 不需要 |
| `install_id` | config | **原始 UUID 原样进事件体** | 导出侧靠白名单挡(见下) |
| `profile` | 活动 profile 名 | **原样进事件体** | 导出侧靠白名单挡 |
| `version` / `supervision_mode` / `pid` / 各计数 | 进程自身 | 版本串 / 闭集 / int | 版本串走 `_safe_metric_value` |

自由文本的收敛靠这三个分类器:

`agent/monitoring/gateway_health.py:70`

```
def classify_gateway_error(raw: Any) -> str:
    s = str(raw or "").lower()
    if any(k in s for k in ("auth", "token", "unauthorized", "forbidden", "401", "403")):
        return "auth_failed"
    if "rate" in s and "limit" in s:
        return "rate_limited"
    if "timeout" in s or "timed out" in s:
        return "timeout"
    if any(
        k in s
        for k in (
            "network",
            "connection",
            "dns",
            "socket",
            "connect call failed",
            "failed to connect",
            "cannot connect",
            "unreachable",
            "name resolution",
        )
    ):
        return "network_error"
    if any(k in s for k in ("config", "missing", "invalid")):
        return "invalid_config"
    if "startup" in s:
        return "startup_failed"
    if "fatal" in s:
        return "platform_fatal"
    return "unknown"
```

`agent/monitoring/gateway_health.py:122`

```
def _bounded_state(raw: Any, *, allowed: set[str]) -> str:
    state = str(raw or "unknown").lower()
    return state if state in allowed else "unknown"
```

`agent/monitoring/cron_health.py:40`

```
def _job_key(raw: Any) -> str:
    value = str(raw or "unknown").encode("utf-8", errors="replace")
    return f"sha256:{hashlib.sha256(value).hexdigest()[:24]}"
```

**注意 `classify_gateway_error` 的一个隐性收益**:它把任意长的异常原文压成一个短枚举串,
既是脱敏也是**基数控制**(cardinality control)——时序数据库最怕的就是标签取值无限多。
一个"顺手做对两件事"的设计。

### 2.4 那 `install_id` 和 `profile` 到底会不会出去?

**不会,但拦它们的不是脱敏器,是导出侧的两张白名单。** 实测端到端:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'EOF'
import sys, json
sys.path.insert(0, "/home/user/hermes-agent")
from agent.monitoring.gateway_health import build_gateway_health_snapshot
from agent.monitoring.otlp_exporter import _span_attrs
snap = build_gateway_health_snapshot(
    {"gateway_state": "running", "active_agents": 3, "pid": 4242,
     "platforms": {"slack": {"state": "fatal",
                             "error_message": "auth failed for alice@corp.com token sk-live-AAAABBBBCCCC"}}},
    gateway_running=True, profile="work-profile-alice",
    install_id="9d4f2b10-1111-2222-3333-444455556666",
    version="0.1.7", supervision_mode="systemd")
for e in snap.events:
    d = e.to_dict()
    print("EVENT:", json.dumps({k: d[k] for k in ("event", "profile", "install_id") if k in d}))
    print("SPAN :", json.dumps(_span_attrs(d)))
EOF
```

```console
EVENT: {"event": "gateway_health", "profile": "work-profile-alice", "install_id": "9d4f2b10-1111-2222-3333-444455556666"}
SPAN : {"hermes.event": "gateway_health", "hermes.name": "gateway.health_snapshot", "hermes.gateway_state": "running", "hermes.active_agents": 3, "hermes.gateway_busy": true, "hermes.gateway_drainable": true, "hermes.platform_count": 1, "hermes.fatal_platform_count": 1, "hermes.version": "0.1.7", "hermes.supervision_mode": "systemd", "hermes.pid": 4242}
EVENT: {"event": "gateway_diagnostic", "profile": "work-profile-alice"}
SPAN : {"hermes.event": "gateway_diagnostic", "hermes.name": "platform.fatal", "hermes.subsystem": "platform.slack", "hermes.error_class": "auth_failed", "hermes.error_code": "auth_failed", "hermes.platform": "slack", "hermes.version": "0.1.7", "hermes.severity": "error"}
```

两件事同时成立:

- **好消息**:带密钥的平台错误原文(`sk-live-AAAABBBBCCCC`)一路上都没出现,连事件体里都没有
  ——被 `classify_gateway_error` 在**构造时**就折成了 `auth_failed`。
- **需要知道的**:`profile` 与原始 `install_id` **确实躺在事件字典里**,只是 span/log 的
  白名单没收它们。而 `MonitoringEmitter.subscribe()` 把**整个原始 dict** 交给**每一个**
  订阅者(`agent/monitoring/emitter.py:118`)。

#### ◇-1 "content-free by construction" 的实际执行点在导出侧,不在事件侧

`agent/monitoring/emitter.py:118`

```
    def subscribe(self, callback) -> None:
        """Register a live batch subscriber (callable(batch: list[dict]))."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)
        self._enabled = True
```

订阅是开放 API,拿到的是 `list[dict]` 原文。今天只有两个自家订阅者(`OTLPStreamer`、
`GatewayDiagnosticLogStreamer`),它们各带一张白名单;**第三个订阅者只要不带白名单,
`profile` 与原始 `install_id` 就直接出去了**。文档把这层不变式写成"by construction"
——见下句——而代码里它其实是"by two allowlists"。

`docs/observability/monitoring.md:7`

> This plane is content-free by construction. It exports gateway and cron
> lifecycle state, platform connector health, and content-free warning/error
> diagnostics. It never exports prompts, messages, tool arguments or results,


设计教训(可迁移):**如果一个不变式的名字叫 "by construction",那它就该在构造函数里成立。**
更稳的做法是让 `to_dict()` 只吐可导出字段,把 `install_id`/`profile` 挪进一个不参与
序列化的旁路。

### 2.5 脱敏正则的实际能力边界(实测)

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'EOF'
import sys
sys.path.insert(0, "/home/user/hermes-agent")
from agent.monitoring.redaction import redact_for_export as R
for s in ["connect failed for alice@example.com",
          "session 3f2c1a4e-9b8d-4c7a-8e1f-2a3b4c5d6e7f died",
          "token 0123456789abcdef0123456789abcdef expired",
          "AKIAIOSFODNN7EXAMPLE rejected",
          "connect to 192.168.10.42:8080 refused",
          "/home/alice/.hermes/config.yaml not found",
          "prod-12345678"]:
    print(f"{s!r}\n  -> {R(s)!r}")
EOF
```

```console
'connect failed for alice@example.com'
  -> 'connect failed for [email]'
'session 3f2c1a4e-9b8d-4c7a-8e1f-2a3b4c5d6e7f died'
  -> 'session [id] died'
'token 0123456789abcdef0123456789abcdef expired'
  -> 'token 0123456789abcdef0123456789abcdef expired'
'AKIAIOSFODNN7EXAMPLE rejected'
  -> 'AKIAIO...MPLE rejected'
'connect to 192.168.10.42:8080 refused'
  -> 'connect to [phone].42:8080 refused'
'/home/alice/.hermes/config.yaml not found'
  -> '/home/alice/.hermes/config.yaml not found'
'prod-12345678'
  -> 'prod-[phone]'
```

三条结论:

- **漏**:32 位裸 hex(常见的 API key 形态)整条穿过。`_UUID_RE` 要求 8-4-4-4-12 带连字符
  (`agent/monitoring/redaction.py:38`),裸 hex 不在名单里,底层 `redact_sensitive_text`
  也没接住。**在当前的监控面这不构成泄漏**(自由文本根本进不到事件体),但
  `redact_for_export` 的模块文档说自己"remains available for a future ... redacted-message
  detail mode"(`agent/monitoring/redaction.py:14`)——**那个未来模式一旦打开,这就是个真洞**。
- **误伤**:IPv4 被电话正则啃成 `[phone].42`。运维排查网络故障最想看的就是地址,而且
  留了半截比整条抹掉更糟(读者会以为自己看到的是个真地址)。
- **误伤的连锁**:`prod-12345678` → `prod-[phone]`,这条会引出 ■-2(下一节)。

路径类 PII(`/home/alice/...`)不在名单里——但模块文档只承诺 "e-mail addresses, phone
numbers, and UUID-shaped identifiers"(`agent/monitoring/redaction.py:9`),**字面为真**,
不算 ▲。

---

## 3. OTLP 导出:`otlp_exporter.py`

### 3.1 协议与依赖

OTLP/HTTP(protobuf over HTTP),SDK 是可选 extra。

`agent/monitoring/otlp_exporter.py:8`

```
Notes:
  * The destination is operator-configured; this module only sends to that
    endpoint. No default destination ships.
  * ``opentelemetry-sdk`` + ``opentelemetry-exporter-otlp-proto-http`` are an
    optional extra (``pip install hermes-agent[otlp]``), imported lazily so the
    dependency is only required when OTLP export is actually used.
  * ``headers_env`` maps a header name to an environment variable name; values
    are read from the environment at export time and never logged or stored.
  * The continuous subscriber runs in the emitter's dispatcher thread and is
    fail-isolated, so an export error cannot affect the gateway.
```

`pyproject.toml:266`

```
otlp = ["opentelemetry-sdk==1.39.1", "opentelemetry-exporter-otlp-proto-http==1.39.1"]
```

SDK 用**惰性导入 + 惰性安装**,走全仓统一的 `tools.lazy_deps`(feature 名 `export.otlp`)。
非交互场景(gateway 启动)传 `prompt=False`,装不上就 warning + no-op,**绝不阻塞启动**
(`agent/monitoring/otlp_exporter.py:250`)。

### 3.2 端点从哪来:纯 config,无任何校验

`agent/monitoring/otlp_exporter.py:101`

```
def _otlp_config(config: Dict[str, Any]) -> Dict[str, Any]:
    mon = (config or {}).get("monitoring") or {}
    export = mon.get("export") or {}
    return export.get("otlp") or {}


def build_exporter(config: Dict[str, Any]):
    """Construct an OTLP span exporter from config. Raises OTLPUnavailable if no SDK."""
    sdk = _require_sdk()
    otlp = _otlp_config(config)
    endpoint = otlp.get("endpoint")
    if not endpoint:
        raise ValueError("monitoring.export.otlp.endpoint is not set")
    headers = _resolve_headers(otlp.get("headers_env"))
    return sdk["OTLPSpanExporter"](endpoint=endpoint, headers=headers or None)
```

三件事同时为真:

1. 端点来源是 **`monitoring.export.otlp.endpoint`,只来自 config.yaml**
   (默认空串,`hermes_cli/config_defaults.py:2447`),不来自任何远端响应;
2. 校验只有 `if not endpoint`——**没有 scheme 校验,没有主机校验**;
3. `headers` 由 `headers_env` 解析成**真凭据**挂在请求上:

`agent/monitoring/otlp_exporter.py:83`

```
def _resolve_headers(headers_env: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Resolve {header_name: ENV_VAR_NAME} -> {header_name: value} from env.

    The config stores environment variable names, not secret values; values are
    read from the environment here. Missing variables are skipped (and noted at
    debug level without the value).
    """
    resolved: Dict[str, str] = {}
    for header_name, env_name in (headers_env or {}).items():
        val = os.environ.get(str(env_name))
        if val:
            resolved[str(header_name)] = val
        else:
            logger.debug("OTLP header %s: env var %s not set; skipping",
                         header_name, env_name)
    return resolved
```

"config 存变量名不存密文"是个好设计(config.yaml 可以进 git,密文留在环境里),
但要看清后果:**任意环境变量的值,会被挂到一个未经任何校验的 URL 上**。这与 R9B 定案的
两条 ■ 是**同一形状的后半段**,区别只在**前半段**:R9B 那两条的 URL 来自**远端响应**,
这里的 URL 来自**用户自己的 config.yaml**。所以我不把它记成同型 ■,而是记成设计边界
(详见 §8 的三列表)。

**默认值配置**:

`hermes_cli/config_defaults.py:2441`

```
        # OTLP destination. headers_env maps header names to ENVIRONMENT
        # VARIABLE NAMES (never secret values); values are read from the
        # environment at export time.
        "export": {
            "otlp": {
                "enabled": False,
                "endpoint": "",
                "headers_env": {},
            },
        },
```

### 3.3 事件 → span 的映射:第一张白名单

`agent/monitoring/otlp_exporter.py:139`

```
def _span_attrs(ev: Dict[str, Any]) -> Dict[str, Any]:
    """Span attributes for a monitoring event (content-free by construction)."""
    kind = ev.get("event")
    attrs: Dict[str, Any] = {"hermes.event": kind or "unknown"}
    keep_by_kind = {
        "gateway_health": ("name", "gateway_state", "old_state", "new_state",
                           "exit_reason", "restart_requested", "active_agents",
                           "gateway_busy", "gateway_drainable", "platform_count",
                           "fatal_platform_count", "version",
                           "supervision_mode", "pid"),
        "gateway_diagnostic": ("name", "subsystem", "error_class", "error_code",
                               "platform", "old_state", "new_state",
                               "version", "severity"),
        "cron_execution": ("status", "job_key", "source", "duration_ms",
                           "delivery_outcome", "error_class"),
    }
    for col in keep_by_kind.get(kind, ()):  # type: ignore[arg-type]
        v = ev.get(col)
        if v is not None:
            if isinstance(v, str):
                try:
                    from agent.monitoring.redaction import redact_for_export
                    v = (redact_for_export(v) or "[redacted]")[:500]
                except Exception:
                    v = "[redaction-unavailable]"
            attrs[f"hermes.{col}"] = v
    return attrs
```

要点:

- `keep_by_kind` 是**按事件种类分的属性白名单**,未登记的键直接丢(这就是 `profile` /
  `install_id` / `source_logger` 出不去的原因);
- 只有 `isinstance(v, str)` 才过脱敏 + 截 500 字;int/bool 原样(所以 `pid` 原样出去);
- 脱敏本身也 fail-closed(第 162-163 行)。

### 3.4 失败怎么办

三层,全部 fail-open:

- **建不出 provider**:`start_streaming` 捕 `OTLPUnavailable` → warning → 返回 None
  (`agent/monitoring/otlp_exporter.py:252`);
- **单条 span 映射失败**:`export_batch` 逐条 try(`agent/monitoring/otlp_exporter.py:178`);
- **网络失败**:交给 `BatchSpanProcessor`,再往上由 emitter 的订阅者隔离兜住。

### 3.5 `event_filter`:防止"开一个面就顺带把别的面发出去"

`agent/monitoring/otlp_exporter.py:19`

```
Only monitoring events (gateway_health / gateway_diagnostic) exist on this
plane; the ``event_filter`` seam is kept so future planes sharing the emitter
cannot silently ride along on this exporter.
```

`gateway_health_export` 传进来的过滤器是:

`agent/monitoring/gateway_health_export.py:583`

```
def _gateway_health_event(ev: Dict[str, Any]) -> bool:
    return ev.get("event") in {"gateway_health", "cron_execution"}
```

**这是个很值得抄的接缝**:共享事件总线的风险是"我订阅健康面,结果把别人的面也发到我的
collector 去了"。这里的做法是让**订阅方**声明自己要什么,而不是让发送方猜。

---

## 4. 健康:判据、导出、给谁看

### 4.1 gateway 健康判据(`gateway_health.py`)

`agent/monitoring/gateway_health.py:33`

```
_RUNNING_PLATFORM_STATES = {"running", "connected", "ok", "ready"}
_FATAL_PLATFORM_STATES = {"fatal", "degraded", "error", "failed"}
_KNOWN_GATEWAY_STATES = {
    "starting", "draining", "stopping", "stopped", "startup_failed", "unknown"
} | _RUNNING_PLATFORM_STATES | _FATAL_PLATFORM_STATES
_KNOWN_PLATFORM_STATES = _RUNNING_PLATFORM_STATES | _FATAL_PLATFORM_STATES | {
    "connecting", "disconnected", "disabled", "paused", "retrying", "unknown"
}
_SUPERVISION_MODES = {"systemd", "s6", "container", "launchd", "manual", "unknown"}
_SOURCE_LOGGER_RE = re.compile(r"^gateway(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
```

判据本身很朴素:**平台状态落在 `_RUNNING_PLATFORM_STATES` 就算 up,落在
`_FATAL_PLATFORM_STATES` 就算 degraded,其余(connecting / retrying / disabled …)两个都不算。**
注意 `up == 0` 并不等于 `degraded == 1`——一个正在重连的平台两个指标都是 0。文档推荐的
告警是 `hermes_platform_up == 0`(`docs/observability/monitoring.md:116`),这会把"正在重连"
也算成故障;要区分就得同时看 `degraded`。

`busy` / `drainable` 不自己定义,而是**委托给 gateway 自己的判据**并留本地兜底:

`agent/monitoring/gateway_health.py:173`

```
def _derive_busy(gateway_running: bool, gateway_state: Any, active_agents: Any) -> bool:
    try:
        from gateway.status import derive_gateway_busy
        return derive_gateway_busy(
            gateway_running=gateway_running,
            gateway_state=gateway_state,
            active_agents=active_agents,
        )
    except Exception:
        return bool(gateway_running and gateway_state == "running" and _parse_active_agents(active_agents) > 0)


def _derive_drainable(gateway_running: bool, gateway_state: Any) -> bool:
    try:
        from gateway.status import derive_gateway_drainable
        return derive_gateway_drainable(gateway_running=gateway_running, gateway_state=gateway_state)
    except Exception:
        return bool(gateway_running and gateway_state == "running")
```

**设计点**:监控面**不重新发明业务判据**。`derive_gateway_busy` 是 gateway 关停逻辑用的
同一个函数,于是"监控说 busy"和"关停时认为 busy"永远一致。兜底分支存在只是为了让
监控模块能在 gateway 包不可导入时也别炸。

指标标签的基座:

`agent/monitoring/gateway_health.py:193`

```
def _base_attrs(*, profile: str, install_id: str, version: str, supervision_mode: str) -> Dict[str, str]:
    mode = str(supervision_mode or "unknown").lower()
    return {
        "service.instance.id": _safe_instance_id(install_id),
        "service.version": _safe_metric_value(version, limit=64),
        "hermes.supervision_mode": mode if mode in _SUPERVISION_MODES else "unknown",
    }
```

注意 **`profile` 是形参却完全没被使用**——签名收了它,函数体里一个字都没提。
结合文档的这条禁令看,这是**有意不导出**,但留一个从不使用的形参会让读者以为它进了标签。

`docs/observability/monitoring.md:153`

> Keep alert thresholds and routing in deployment-owned configuration. Do not add
> job names, prompts, outputs, schedules, destinations, raw errors, profile names,
> or account identity merely to make a dashboard easier to read.


### 4.2 诊断日志桥:允许清单 + 只取分类,不取原文

`agent/monitoring/gateway_health.py:427`

```
class GatewayDiagnosticLogHandler(logging.Handler):
    """Allowlisted warning/error bridge for gateway-owned diagnostics."""

    def __init__(self, *, profile: str = "default", version: str = "unknown") -> None:
        super().__init__(level=logging.WARNING)
        self.profile = profile
        self.version = version

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.levelno < logging.WARNING:
                return
            if not _allowed_logger(record.name):
                return
            subsystem = subsystem_for_logger(record.name)
            message = record.getMessage()
            error_class = classify_gateway_error(message)
            event = GatewayDiagnosticEvent(
                name=f"gateway.log.{record.levelname.lower()}",
                subsystem=subsystem,
                source_logger=source_logger_for_export(record.name),
                platform=platform_for_subsystem(subsystem),
                error_class=error_class,
                error_code=error_class,
                profile=self.profile,
                version=self.version,
                severity=record.levelname.lower(),
            )
            from agent.monitoring import emitter
            emitter.get_emitter().emit(event)
        except Exception:
            logging.getLogger(__name__).debug("gateway diagnostic emit failed", exc_info=True)
```

三道闸:

1. `level >= WARNING`;
2. `_allowed_logger(record.name)` —— **只有 `gateway` 与 `gateway.*` 的 logger 能进**,
   第三方库的 warning 一律不进监控面;

   `agent/monitoring/gateway_health.py:45`

   ```
def _allowed_logger(name: str) -> bool:
    return name == "gateway" or name.startswith("gateway.")
   ```

3. `message = record.getMessage()` 拿到渲染后的原文,但**只用来分类**
   (`classify_gateway_error(message)`),**原文不进事件**。

第 3 条是本片"content-free"最硬的一处证据:原文在栈上活了一行就被丢弃。

`source_logger` 字段没进 span 白名单,而是在日志路由里当 **OTel instrumentation scope**
用(§4.3),并且先过一道正则:

`agent/monitoring/gateway_health.py:42`

```
_SOURCE_LOGGER_RE = re.compile(r"^gateway(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _allowed_logger(name: str) -> bool:
    return name == "gateway" or name.startswith("gateway.")


def source_logger_for_export(name: Any) -> Optional[str]:
    """Return a bounded source-controlled gateway logger name for OTLP scope."""
    value = str(name or "")
    return value if len(value) <= 128 and _SOURCE_LOGGER_RE.fullmatch(value) else None
```

#### ◇-2 `redact_gateway_message` 是全仓零调用方的挂起 API

`agent/monitoring/gateway_health.py:55`

```
def redact_gateway_message(message: Any) -> str:
    """Redact gateway diagnostic free text for operator-owned export.

    Single scrub path: everything goes through
    ``agent.monitoring.redaction.redact_for_export`` (unconditional
    secrets + PII), then is length-bounded.
    """
    try:
        from agent.monitoring.redaction import redact_for_export
        redacted = redact_for_export(str(message or "")) or ""
    except Exception:
        redacted = "[redaction-unavailable]"
    return redacted[:500]
```

它在 `__all__` 里,但**全仓(含 tests、plugins、scripts、website)找不到第二处出现**。
搜索面:仓库根 `grep -rn "redact_gateway_message" .`,不加任何 include/exclude,
结果只有 `agent/monitoring/gateway_health.py:55`(定义)与 `:468`(`__all__`)两行。

```verify
cd /home/user/hermes-agent && grep -rn "redact_gateway_message" . | wc -l && grep -rn "redact_gateway_message" .
```

```console
2
./agent/monitoring/gateway_health.py:55:def redact_gateway_message(message: Any) -> str:
./agent/monitoring/gateway_health.py:468:    "redact_gateway_message",
```

这与 `agent/monitoring/redaction.py:14`("remains available for a future, explicitly gated
redacted-message detail mode")呼应:**它是为一个还没实现的模式预留的**。记 ◇ 而不是 ■
——但要记住 §2.5 的裸-hex 漏洞正是在这个模式打开时才会变成真问题。

### 4.3 导出运行时(`gateway_health_export.py`):三条 OTLP 路由

一个 endpoint,靠**字符串后缀改写**派生出三条路由:

`agent/monitoring/gateway_health_export.py:231`

```
def _metric_endpoint(endpoint: str) -> str:
    if endpoint.endswith("/v1/traces"):
        return endpoint[: -len("/v1/traces")] + "/v1/metrics"
    return endpoint


def _logs_endpoint(endpoint: str) -> str:
    if endpoint.endswith("/v1/traces"):
        return endpoint[: -len("/v1/traces")] + "/v1/logs"
    if endpoint.endswith("/v1/metrics"):
        return endpoint[: -len("/v1/metrics")] + "/v1/logs"
    return endpoint
```

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "
import sys; sys.path.insert(0,'/home/user/hermes-agent')
from agent.monitoring.gateway_health_export import _metric_endpoint, _logs_endpoint
for ep in ['http://c:4318/v1/traces','http://c:4318','https://c/otlp/v1/traces']:
    print(f'{ep:28} metrics->{_metric_endpoint(ep):28} logs->{_logs_endpoint(ep)}')"
```

```console
http://c:4318/v1/traces      metrics->http://c:4318/v1/metrics      logs->http://c:4318/v1/logs
http://c:4318                metrics->http://c:4318                 logs->http://c:4318
https://c/otlp/v1/traces     metrics->https://c/otlp/v1/metrics     logs->https://c/otlp/v1/logs
```

**取舍**:只有当运维照文档写 `.../v1/traces` 时派生才成立;写成裸 host 的话三条信号全 POST
到同一个 URL。文档的示例是对的(`docs/observability/monitoring.md:53`),但没有任何校验
提醒写错的人。

三条路由各自的资源属性、白名单、载荷:

| 路由 | 资源属性构造 | 属性白名单 | body |
|---|---|---|---|
| `/v1/traces` | `otlp_exporter._resource_attributes` | `_span_attrs` 的 `keep_by_kind` | span 名 = `hermes.<event>` |
| `/v1/metrics` | `gateway_health_export._runtime_resource_attributes` | `GatewayMetric.attributes` | observable gauge |
| `/v1/logs` | 同上(scope 不同) | `_DIAGNOSTIC_ATTRIBUTE_KEYS` | 常量串 `"gateway diagnostic"` |

日志路由的白名单(第二张,与 span 那张**不是同一份**):

`agent/monitoring/gateway_health_export.py:33`

```
_DIAGNOSTIC_ATTRIBUTE_KEYS = frozenset({
    "name",
    "subsystem",
    "error_class",
    "error_code",
    "platform",
    "old_state",
    "new_state",
    "version",
    "severity",
})
```

日志 body 是个常量,连"消息"这个位置都不给内容留余地:

`agent/monitoring/gateway_health_export.py:505`

```
    def __call__(self, batch: list[Dict[str, Any]]) -> None:
        from agent.monitoring.gateway_health import source_logger_for_export

        for ev in batch:
            if ev.get("event") != "gateway_diagnostic":
                continue
            attrs = _diagnostic_log_attributes(ev)
            # Preserve the source-controlled Python logger as the OTel
            # instrumentation scope. This adds precise code attribution without
            # turning a fluid module layout into a maintained subsystem enum.
            # Rendered messages stay out because they may contain arbitrary IDs,
            # names, paths, or configured strings. A future, separately gated
            # ``diagnostic_detail: redacted_message`` mode may add best-effort
            # free text when an observability plane defines that privacy policy.
            source_logger = source_logger_for_export(ev.get("source_logger"))
            otel_logger = (
                self._provider.get_logger(source_logger)
                if source_logger is not None
                else self._logger
            )
            body = "gateway diagnostic"
            record = self._LogRecord(
                timestamp=ev.get("ts_ns"),
                trace_id=self._sdk["INVALID_TRACE_ID"],
                span_id=self._sdk["INVALID_SPAN_ID"],
                trace_flags=self._sdk["TraceFlags"].DEFAULT,
                severity_text=str(ev.get("severity") or "warning").upper(),
                severity_number=_severity_number(self._sdk, ev.get("severity")),
                body=_redact_string(body),
                attributes=attrs,
            )
            otel_logger.emit(record)
            self.exported += 1
```

运维可配的资源属性走第三张白名单,并且**多加了一道"脱敏改动过的值一律丢弃"**:

`agent/monitoring/gateway_health_export.py:55`

```
def _safe_resource_attributes(raw: Any) -> Dict[str, str]:
    """Allowlist bounded resource labels and reject values changed by redaction."""
    attrs: Dict[str, str] = {}
    if not isinstance(raw, dict):
        return attrs
    for key, value in raw.items():
        key = str(key)
        if key not in _RESOURCE_ATTRIBUTE_KEYS or value is None:
            continue
        if key == "service.instance.id":
            from agent.monitoring.gateway_health import _safe_instance_id
            attrs[key] = _safe_instance_id(value)
            continue
        text = str(value)
        if not _SAFE_RESOURCE_VALUE.fullmatch(text):
            continue
        if _redact_string(text, limit=128) != text:
            continue
        attrs[key] = text
    return attrs
```

`agent/monitoring/gateway_health_export.py:77`

```
def _runtime_resource_attributes(
    config: Dict[str, Any], *, telemetry_scope: str
) -> Dict[str, str]:
    """Build the safe OTLP resource shared by metrics and diagnostic logs."""
    gh = _gateway_health_config(config)
    attrs = _safe_resource_attributes(gh.get("resource_attributes"))
    from agent.monitoring.gateway_health import _safe_instance_id

    attrs["service.name"] = "hermes-gateway"
    attrs["service.instance.id"] = _safe_instance_id(_install_id(config))
    attrs["telemetry.scope"] = telemetry_scope
    return attrs
```

#### ■-2 三个被白名单放行的资源属性键,随后被无条件覆盖;运维改了不生效也无提示

`_safe_resource_attributes` 认真校验并放行 `service.name` / `service.instance.id` /
`telemetry.scope`,紧接着第 85-87 行把这三个**全部覆盖**。默认配置里恰好就有 `resource_attributes.service.name`,值与硬编码相同,所以默认无感;
运维一改就静默失效。

`hermes_cli/config_defaults.py:2436`

```
            "resource_attributes": {
                "service.name": "hermes-gateway",
                "deployment.environment.name": "production",
            },
```


#### ■-3 运维配置的资源属性只到 metrics/logs,**traces 路由收不到**

`agent/monitoring/otlp_exporter.py:118`

```
def _resource_attributes(config: Dict[str, Any]) -> Dict[str, str]:
    from agent.monitoring.gateway_health import _safe_instance_id
    from agent.monitoring.policy import ensure_install_id

    return {
        "service.name": "hermes-gateway",
        "service.instance.id": _safe_instance_id(ensure_install_id(config)),
        "telemetry.scope": "gateway_monitoring",
    }
```

这是 traces 路由的资源构造:**只有 3 个键,完全不读
`monitoring.gateway_health_export.resource_attributes`**。实测两条路由并排:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, "/home/user/hermes-agent")
from agent.monitoring.gateway_health_export import _runtime_resource_attributes
from agent.monitoring.otlp_exporter import _resource_attributes as span_resource
cfg = {"monitoring": {"install_id": "abc-install", "gateway_health_export": {"resource_attributes": {
    "service.name": "my-own-gateway-name", "deployment.environment.name": "staging",
    "cloud.region": "eu-west-1"}}}}
print("metrics/logs:", _runtime_resource_attributes(cfg, telemetry_scope="gateway_health"))
print("traces      :", span_resource(cfg))
EOF
```

```console
metrics/logs: {'service.name': 'hermes-gateway', 'deployment.environment.name': 'staging', 'cloud.region': 'eu-west-1', 'service.instance.id': 'sha256:2cba24dcb652f6e57767bbf1', 'telemetry.scope': 'gateway_health'}
traces      : {'service.name': 'hermes-gateway', 'service.instance.id': 'sha256:2cba24dcb652f6e57767bbf1', 'telemetry.scope': 'gateway_monitoring'}
```

后果很具体:运维按 `deployment.environment.name: staging` 分环境做看板,
**metrics 和 logs 分得开,traces 分不开**——而生命周期事件与 cron 执行事件全在 traces 上。
`my-own-gateway-name` 两条路由都被吃掉(那是 ■-2)。

### 4.4 关停:本片写得最好的一段

`agent/monitoring/gateway_health_export.py:112`

```
    def shutdown(self) -> None:
        if self.stop_event is not None:
            self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=0.25)
        if self.log_handler is not None:
            try:
                logging.getLogger().removeHandler(self.log_handler)
            except Exception:
                pass

        # All producers above are now stopped. Drain queued and in-flight
        # events before detaching subscribers so the terminal lifecycle event
        # cannot race exporter shutdown. The barrier is bounded and fail-open.
        try:
            from agent.monitoring.emitter import get_emitter
            emitter = get_emitter()
            emitter.flush(timeout=1.0)
            if self.streamer is not None:
                emitter.unsubscribe(self.streamer)
            if self.log_streamer is not None:
                emitter.unsubscribe(self.log_streamer)
        except Exception:
            pass

        # Network flush/close runs under one bounded daemon-thread deadline and
        # can never delay gateway teardown indefinitely.
        closeables = [
            item for item in (self.streamer, self.log_streamer, self.metric_provider)
            if item is not None
        ]

        def _close() -> None:
            for item in closeables:
                try:
                    item.shutdown()
                except Exception:
                    pass

        if closeables:
            worker = threading.Thread(
                target=_close,
                name="hermes-gateway-health-export-shutdown",
                daemon=True,
            )
            worker.start()
            worker.join(timeout=2.0)
```

顺序是有意的,每一步都对着一个具体故障:

1. 先停**生产者**(快照线程、日志 handler)——不然边排空边有新事件进来,永远排不完;
2. `emitter.flush(timeout=1.0)` 跨越**队列屏障**,再 `unsubscribe`——注释第 123-125 行
   说得很清楚:终态生命周期事件不能和 exporter 关停赛跑;
3. 网络 flush/close 丢进一个**带 deadline 的 daemon 线程**——一个挂死的 collector
   最多拖 2 秒,永远拖不死 gateway 关停。

**可迁移的原则**:异步导出管道的关停必须是 `停生产 → 排队列 → 摘订阅 → 限时刷网络`
四步,且每一步都要有独立的超时。少任何一步都会在"进程正在退出"这个最需要遥测的时刻丢数据。

### 4.5 cron 健康(`cron_health.py`)

指标是"新鲜度"而不是"成功率":

`agent/monitoring/cron_health.py:148`

```
def build_cron_health_snapshot() -> CronHealthSnapshot:
    metrics: list[GatewayMetric] = []
    for name, reader in (
        ("hermes.cron.scheduler.heartbeat_age_seconds", get_ticker_heartbeat_age),
        ("hermes.cron.scheduler.last_success_age_seconds", get_ticker_success_age),
    ):
        try:
            value = reader()
            if value is not None:
                metrics.append(GatewayMetric(name, max(0.0, float(value)), {}))
        except Exception:
            logger.debug("cron freshness metric unavailable", exc_info=True)

```

`agent/monitoring/cron_health.py:132`

```
def _is_overdue(job: dict[str, Any], now: datetime) -> bool:
    if not job.get("enabled", True):
        return False
    next_run = _parse_time(job.get("next_run_at"))
    schedule = job.get("schedule")
    if next_run is None or not isinstance(schedule, dict):
        return False
    try:
        if next_run.tzinfo is None and now.tzinfo is not None:
            next_run = next_run.replace(tzinfo=now.tzinfo)
        lateness = (now - next_run).total_seconds()
        return lateness > _compute_grace_seconds(schedule)
    except (TypeError, ValueError):
        return False
```

"逾期"判据复用 cron 自己的宽限规则 `_compute_grace_seconds(schedule)`,与 §4.1 委托
`derive_gateway_busy` 是同一手法。

执行事件的投影是**唯一一处对热路径做同步等待的地方**:

`agent/monitoring/cron_health.py:114`

```
def emit_execution_state(
    record: Optional[dict[str, Any]], *, delivery_outcome: Optional[str] = None
) -> None:
    """Best-effort lifecycle emit; terminal states synchronously cross the queue barrier."""
    if not record:
        return
    try:
        from agent.monitoring import emitter

        event = project_execution_event(record, delivery_outcome=delivery_outcome)
        target = emitter.get_emitter()
        target.emit(event)
        if event.status in {"completed", "failed", "unknown"}:
            target.flush(timeout=1.0)
    except Exception:
        logger.debug("cron execution telemetry emit failed", exc_info=True)
```

终态(`completed`/`failed`/`unknown`)会**同步 flush 最多 1 秒**。理由:cron 任务跑完
进程可能马上就没了,不跨屏障就丢最重要的那条。这是对 §1.3 热路径不变式的**有意破例**,
而且**文档明写了这个破例**(`docs/observability/monitoring.md:23`:"terminal states make a
fail-open flush attempt that can delay completion by up to one second")。

#### ■-4(轻)cron 指标的 attributes 是空字典

`agent/monitoring/cron_health.py:157`

```
                metrics.append(GatewayMetric(name, max(0.0, float(value)), {}))
```

第三个实参恒为 `{}`,其余五个 gauge 同样(`agent/monitoring/cron_health.py:166`、
`:175`、`:180`、`:188`)—— cron 的六个 gauge **没有任何指标级标签**,不像 gateway 那些带
`_base_attrs`(service.instance.id / service.version / supervision_mode)。资源级的 `service.instance.id` 还在,所以按实例分组仍可行,
但 `service.version` 与 `hermes.supervision_mode` 在 cron 指标上确实没有。这直接构成 ▲-1。

---

## 5. trace 上传:`trace_upload.py`

### 5.1 一次具体的走法

用户敲 `/upload-trace`(或 `hermes trace upload`)。发生什么:

1. 从 SQLite 会话库读出整段对话(`load_session_messages`,`agent/trace_upload.py:329`);
2. 转成 **Claude Code JSONL** 形状——HF Agent Trace Viewer 能自动识别的三种格式之一;
3. **每一段文本都过 `redact_sensitive_text(force=True)`**;
4. 用环境里的 HF token 建/复用一个**私有** dataset,把 `sessions/<id>.jsonl` 推上去。

`agent/trace_upload.py:12`

```
------------
* **Zero LLM turn.** This is a deterministic export — it never spends a
  model call. The ``hermes trace upload`` subcommand calls
  :func:`upload_session_trace` directly.
* **Private by default.** Traces can contain prompts, tool output, local
  paths, and secrets. The dataset is created private and every text body
  is passed through Hermes' secret redactor (``force=True``) unless the
  caller explicitly opts out with ``redact=False``.
* **Never raises.** Returns a user-facing status string so command
  handlers can echo it straight back to the user. Programmatic callers
  that need the URL can use :func:`build_trace_jsonl` + :func:`_do_upload`
  directly.
```

### 5.2 脱敏:强制、且 fail-CLOSED 到"拒绝上传"

`agent/trace_upload.py:58`

```
def _redact(text: Any, enabled: bool) -> Any:
    """Redact secrets from a string body when redaction is enabled.

    Non-strings pass through untouched. Uses Hermes' shared redactor with
    ``force=True`` so an upload always scrubs known secret shapes even if
    the user disabled log redaction globally.
    """
    if not enabled or not isinstance(text, str) or not text:
        return text
    try:
        from agent.redact import redact_sensitive_text
        return redact_sensitive_text(text, force=True)
    except Exception as exc:
        logger.warning("Trace upload redaction failed; refusing upload", exc_info=True)
        raise TraceRedactionError(_REDACTION_BLOCKED_MESSAGE) from exc
```

与监控面的 fail-closed 又不同一档:监控面失败是**发一个占位串**,这里失败是
**抛异常 → 整个上传中止**。因为载荷性质不同——监控面丢一条事件无所谓,
trace 里漏一个密钥就是永久公开(即使 dataset 私有,也已经离开了本机)。

还有一处更细的 fail-closed,值得单独看:

`agent/trace_upload.py:120`

```
        if redact:
            try:
                parsed = json.loads(_redact(json.dumps(parsed), redact))
            except (json.JSONDecodeError, ValueError):
                logger.warning("Trace upload redacted tool arguments are not valid JSON; refusing upload")
                raise TraceRedactionError(_REDACTION_BLOCKED_MESSAGE)
```

工具入参是先 `json.dumps` → 脱敏 → 再 `json.loads`。**如果脱敏把 JSON 结构改坏了
(比如替换串里带了引号),宁可拒绝上传,也不上传一个"我不确定脱成什么样了"的载荷。**
这个判断很到位:脱敏器对结构化文本本来就不安全,与其猜不如停。

### 5.3 端点与凭据

`agent/trace_upload.py:247`

```
def _resolve_hf_token() -> Optional[str]:
    """Return the user's Hugging Face token from the usual env vars."""
    for var in ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
        val = os.getenv(var)
        if val and val.strip():
            return val.strip()
    return None
```

`agent/trace_upload.py:292`

```
    api = HfApi(token=token)
```

- **凭据**:四个环境变量按序取第一个非空。
- **端点**:`HfApi(token=token)` **没有传 `endpoint=`**,即完全采用 `huggingface_hub`
  的库默认值。hermes 侧**既不设置也不校验**这个端点。
  搜索面:`grep -rn "HF_ENDPOINT\|HUGGINGFACE_ENDPOINT" --include=*.py --include=*.md
  --include=*.ts --include=*.yaml .`,全仓唯一命中在
  `optional-skills/mlops/stable-diffusion/references/troubleshooting.md:384`
  (一份技能文档教用户 `export HF_ENDPOINT=https://hf-mirror.com`),**hermes 代码零处理**。
- 因此:上传目标由 `huggingface_hub` 自行解析,hermes 不参与。**"库会不会读
  `HF_ENDPOINT`" 是关于第三方库的事实,不在基线内,我不把它写成结论**(见 §11 未取证项)。

#### ■-5(轻)成功回执里的 URL 是硬编码的 huggingface.co,与真实上传目标无关

`agent/trace_upload.py:325`

```
    return (f"Uploaded -> https://huggingface.co/datasets/{repo_id}/blob/main/{path_in_repo}\n"
            f"View in the trace viewer: https://huggingface.co/datasets/{repo_id}")
```

无论 `HfApi` 实际把文件推到了哪儿,回给用户的两条链接都是拼死的 `huggingface.co`。
只要端点被库层重定向过,用户拿到的就是一个**指向错误位置的确认信息**——而这条信息
正是用户用来核对"我的会话到底传到哪了"的唯一凭据。

### 5.4 一处轻微的契约不符

`agent/trace_upload.py:356`

```
    """Top-level entry point used by the CLI/gateway/subcommand.

    Loads the session, converts it to Claude Code JSONL, and uploads it to
    the user's private ``{user}/hermes-traces`` dataset. Returns a
    user-facing status string and never raises.
    """
```

`upload_session_trace` 自称 "never raises",但 `build_trace_jsonl` 里只有
`TraceRedactionError` 被接住:

`agent/trace_upload.py:387`

```
    except TraceRedactionError:
        return _REDACTION_BLOCKED_MESSAGE
```

`_content_to_blocks` 中的
`json.dumps(part)` 遇到不可序列化对象会抛 `TypeError`,那条路径没人接。实际会话消息来自
SQLite JSON,大概率恒可序列化,所以我**只把它记为契约与实现的边界不严,不记 ■**。

---

## 6. 出站 webhook:`outbound_webhooks.py` —— 本片最值得主线复核的一处

### 6.1 一次具体的走法

用户在 config.yaml 里写:

```yaml
hooks:
  outbound:
    - url: https://metrics.example.com/hooks/hermes
      events: [post_tool_call]
```

之后 agent 每跑完一个工具:

1. `model_tools.py` 调 `invoke_hook("post_tool_call", tool_name=..., args=..., result=..., ...)`;
2. 本模块注册的闭包被调用,**在 agent 循环里**同步执行——所以它只做序列化 + 入队;
3. 单个 daemon worker 出队,`urllib` POST 出去,带 HMAC-SHA256 签名(配了 secret 的话)。

### 6.2 载荷:完整工具入参 **和完整工具结果**,零脱敏

`agent/outbound_webhooks.py:404`

```
def _serialize_payload(
    event: str, kwargs: Dict[str, Any], delivery_id: str,
) -> bytes:
    """Render the POST body.  Same top-level shape as shell hooks' stdin
    (documented in :mod:`agent.shell_hooks`), plus delivery metadata.

    ``delivery_id`` is shared with the ``X-Hermes-Delivery`` header so
    receivers can dedupe on either — and since it (plus ``timestamp``)
    lives inside the HMAC-signed body, it doubles as replay protection.
    """
    extras = {k: v for k, v in kwargs.items() if k not in _TOP_LEVEL_PAYLOAD_KEYS}
    try:
        cwd = str(Path.cwd())
    except OSError:
        cwd = ""
    payload = {
        "hook_event_name": event,
        "tool_name": kwargs.get("tool_name"),
        "tool_input": kwargs.get("args") if isinstance(kwargs.get("args"), dict) else None,
        "session_id": kwargs.get("session_id") or kwargs.get("parent_session_id") or "",
        "cwd": cwd,
        "extra": extras,
        "delivery_id": delivery_id,
        "timestamp": datetime.now(tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
```

关键在第 414 行:`_TOP_LEVEL_PAYLOAD_KEYS` 之外的**所有 kwargs 原样进 `extra`**。
而 `post_tool_call` 的调用方传的是:

`model_tools.py:1103`

```
        invoke_hook(
            "post_tool_call",
            tool_name=function_name,
            args=function_args,
            result=result,
            task_id=task_id or "",
            session_id=session_id or "",
            tool_call_id=tool_call_id or "",
            turn_id=turn_id or "",
            api_request_id=api_request_id or "",
            duration_ms=duration_ms,
            status=status,
            error_type=error_type,
            error_message=error_message,
            middleware_trace=list(middleware_trace or []),
        )
```

而 `result` 不在这份名单里:

`agent/outbound_webhooks.py:98`

```
# kwargs promoted to top-level payload keys (mirrors shell hooks wire).
_TOP_LEVEL_PAYLOAD_KEYS = {"tool_name", "args", "session_id", "parent_session_id"}
```

于是**整个工具输出落进 `extra.result`**。实测:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'EOF'
import sys, json
sys.path.insert(0, "/home/user/hermes-agent")
from agent.outbound_webhooks import _serialize_payload
body = json.loads(_serialize_payload("post_tool_call", {
    "tool_name": "terminal", "args": {"command": "cat ~/.hermes/.env"},
    "result": "OPENAI_API_KEY=sk-live-SUPERSECRET\nHF_TOKEN=hf_abcdefgh",
    "session_id": "sess_abc", "status": "ok", "duration_ms": 12}, "deadbeef"))
body["timestamp"] = "<run time>"; body["cwd"] = "<cwd>"   # 每次运行都不同,置换掉便于比对
print(json.dumps(body, ensure_ascii=False, indent=2))
EOF
```

```console
{
  "hook_event_name": "post_tool_call",
  "tool_name": "terminal",
  "tool_input": {
    "command": "cat ~/.hermes/.env"
  },
  "session_id": "sess_abc",
  "cwd": "<cwd>",
  "extra": {
    "result": "OPENAI_API_KEY=sk-live-SUPERSECRET\nHF_TOKEN=hf_abcdefgh",
    "status": "ok",
    "duration_ms": 12
  },
  "delivery_id": "deadbeef",
  "timestamp": "<run time>"
}
```

(`status` / `duration_ms` 是探针一并传入的其余 kwargs,用来演示 `extra` 的收纳规则;
`timestamp` 与 `cwd` 每次运行都不同,已在脚本里置换成占位串,所以这段输出可逐字复现。)

**全模块零脱敏。** 搜索面:对本片四个外发模块跑
`grep -nE "redact|is_private|ipaddress|localhost|127\.0\.0\.1|169\.254|allowlist|allow_list|_validate_(base_)?url|resolve_host|socket\." agent/outbound_webhooks.py agent/trace_upload.py agent/monitoring/otlp_exporter.py agent/monitoring/gateway_health_export.py`
——命中**全部落在 `agent/trace_upload.py`**(它的 `_redact`),
`outbound_webhooks.py` / `otlp_exporter.py` / `gateway_health_export.py` **零命中**。

```verify
cd /home/user/hermes-agent && grep -cE "redact|is_private|ipaddress|localhost|127\.0\.0\.1|169\.254|allowlist|allow_list|_validate_(base_)?url|resolve_host|socket\." agent/outbound_webhooks.py agent/monitoring/otlp_exporter.py agent/monitoring/gateway_health_export.py
```

```console
agent/outbound_webhooks.py:0
agent/monitoring/otlp_exporter.py:0
agent/monitoring/gateway_health_export.py:0
```

### 6.3 ▲-2 文档说载荷含"tool inputs and event metadata",实际还含**工具结果**

`website/docs/user-guide/features/hooks.md:1594`

> - **No consent prompt.** Outbound targets execute no code on your machine — they receive data at a URL you configured. `HERMES_SAFE_MODE=1` still skips registration, same as plugins and shell hooks. Note that payloads include tool inputs and event metadata, so only point targets at endpoints you trust, and prefer `https://`.

这条 bullet 归 `### Delivery semantics` 管(`website/docs/user-guide/features/hooks.md:1587`),
是全文**唯一**一处交代载荷敏感性的句子。整句判定:

- "execute no code on your machine" —— **成立**(本模块只 POST,不执行任何东西);
- "`HERMES_SAFE_MODE=1` still skips registration" —— **成立**:

  `agent/outbound_webhooks.py:171`

  ```
    if env_var_enabled("HERMES_SAFE_MODE"):
        logger.info("HERMES_SAFE_MODE=1 — outbound webhook registration skipped")
        return []
  ```

- "payloads include tool inputs and event metadata" —— **不完整**:工具**结果**既不是
  input 也不是通常意义上的 "event metadata",而它整条在里面。而"结果"恰恰是三者中
  最可能装着密钥、文件内容、他人隐私的那一个。

同页的 wire-format 示例(`website/docs/user-guide/features/hooks.md:1557`)给的 `extra`
是 `{"completed": true, "interrupted": false, "model": "...", "platform": "cli"}` 这种无害元数据,
进一步把读者引向"`extra` 是元数据"的理解。判 ▲。

### 6.4 URL 校验:scheme 前缀检查,**无主机校验**

`agent/outbound_webhooks.py:278`

```
    url = raw.get("url")
    if not isinstance(url, str) or not url.strip():
        logger.warning("hooks.outbound[%d] is missing a non-empty 'url'", index)
        return None
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        logger.warning(
            "hooks.outbound[%d].url must be http(s); got %r — skipped",
            index, url,
        )
        return None
    if url.lower().startswith("http://"):
        logger.warning(
            "hooks.outbound[%d].url uses plain http:// — payloads (including "
            "tool inputs) travel unencrypted. Prefer https.", index,
        )

```

实测:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'EOF'
import sys, logging
logging.disable(logging.CRITICAL)     # 被拒 URL 会打 warning,这里只看返回值
sys.path.insert(0, "/home/user/hermes-agent")
from agent.outbound_webhooks import _parse_single_target
for u in ["https://ci.example.com/x", "http://169.254.169.254/latest/meta-data/",
          "HTTPS://Evil.example.com/x", " https://x.example.com/y ",
          "https:/ci.example.com/x", "file:///etc/passwd", "javascript:alert(1)"]:
    t = _parse_single_target(0, {"url": u, "events": ["on_session_end"]})
    print(f"{u!r:45} -> {'ACCEPT ' + t.url if t else 'reject'}")
EOF
```

```console
'https://ci.example.com/x'                    -> ACCEPT https://ci.example.com/x
'http://169.254.169.254/latest/meta-data/'    -> ACCEPT http://169.254.169.254/latest/meta-data/
'HTTPS://Evil.example.com/x'                  -> ACCEPT HTTPS://Evil.example.com/x
' https://x.example.com/y '                   -> ACCEPT https://x.example.com/y
'https:/ci.example.com/x'                     -> reject
'file:///etc/passwd'                          -> reject
'javascript:alert(1)'                         -> reject
```

**与 R9B 红线的关系,要说清楚**:

- scheme 检查的**形状是对的**——`startswith(("http://", "https://"))` 是前缀判断,
  不是 R9B 那种子串包含或 `strip()`,`file://` / `javascript:` 都挡住了;
- 但**没有主机校验**:云元数据地址 `169.254.169.254`、`localhost`、内网地址全部放行;
- **关键区别**:这条通道上**没有凭据被发往那个 URL**。HMAC secret 只用来算摘要
  (`agent/outbound_webhooks.py:443`),摘要不泄露密钥本身。所以它**不是**
  "凭据发往未校验主机"那一型,它是**外泄(exfiltration)通道**:
  发出去的是**会话与工具数据**。
- 明文 `http://` 只 warn 不拒(第 289-293 行),于是上面那个 `extra.result` 可以明文过网。

### 6.5 注册时机 —— 这限制了攻击面,值得写清楚

`register_from_config` 全仓只有三个非测试调用方,**全部在进程启动路径上**:

```verify
cd /home/user/hermes-agent && grep -rn "register_outbound_webhooks(" --include=*.py . | grep -v "^./tests/"
```

```console
./cli.py:1057:        register_outbound_webhooks(_hooks_cfg)
./gateway/run.py:10979:            register_outbound_webhooks(_hooks_cfg)
./hermes_cli/main.py:10842:        register_outbound_webhooks(_hooks_cfg)
```

搜索面:仓库根 `grep -rn "register_outbound_webhooks(" --include=*.py .` 去掉 `tests/`;
另外 `iter_configured_targets` 只被 `hermes_cli/hooks.py:57` 的 `hermes hooks list` 用,
不注册任何回调。结论:**会话中途改 config.yaml 不会即时生效**,要等下一次 CLI 会话 /
gateway 重启——这与文档 `website/docs/user-guide/features/hooks.md:1542`
("Changes take effect on the next CLI session / gateway restart")一致,
也**实质性地收窄了"被诱导写 config 就立即开始外泄"这条路径**。

### 6.6 签名、重试、幂等

`agent/outbound_webhooks.py:434`

```
def _build_delivery(
    event: str, target: WebhookTarget, body: bytes, delivery_id: str,
) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Hermes-Agent-Outbound-Webhook",
        "X-Hermes-Event": event,
        "X-Hermes-Delivery": delivery_id,
    }
    if target.secret:
        digest = hmac.new(
            target.secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        headers["X-Hermes-Signature-256"] = f"sha256={digest}"
    return {
        "url": target.url,
        "label": target.label,
        "event": event,
        "body": body,
        "headers": headers,
        "timeout": target.timeout,
    }
```

- **签名**:HMAC-SHA256 over raw body,GitHub 风格头。`delivery_id` 与 `timestamp` 都在
  **被签名的 body 内部**,所以接收端顺带拿到重放保护——这个设计很划算,零额外机制。
- **幂等**:`delivery_id` 在回调触发时生成一次(`agent/outbound_webhooks.py:387`),
  delivery 字典构造一次,**重试复用同一个 id 和同一个 body**,签名依然有效。
  接收端按 `X-Hermes-Delivery` 去重即可。
- **重试**:最多 2 次,退避 `1.0 * attempt`;4xx 不重试,3xx 不跟随。

`agent/outbound_webhooks.py:504`

```
class _NoRedirectHandler(urlrequest.HTTPRedirectHandler):
    """Refuse to follow redirects.

    urllib's default handler converts a redirected POST into a body-less
    GET — the signed payload would be silently dropped and the headers
    re-sent to a location the user never configured.  Treat any 3xx as a
    delivery failure instead (surfaced as HTTPError by returning None).
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


_opener = urlrequest.build_opener(_NoRedirectHandler)
```

**这段的理由写得非常好,值得抄进自己的 harness**:urllib 默认会把被重定向的 POST 转成
无 body 的 GET——签名载荷被静默丢弃,而请求头(含签名头)被重发到用户从没配过的地址。
所以宁可把 3xx 当投递失败。

#### ◇-3 secret_env 指向的环境变量不存在时,降级为**无签名投递**而非拒发

`agent/outbound_webhooks.py:358`

```
def _resolve_secret(index: int, raw: Dict[str, Any]) -> Optional[str]:
    """``secret_env`` (env var name, preferred) wins over inline ``secret``."""
    secret_env = raw.get("secret_env")
    if isinstance(secret_env, str) and secret_env.strip():
        value = os.environ.get(secret_env.strip(), "")
        if value:
            return value
        logger.warning(
            "hooks.outbound[%d].secret_env=%r is not set in the environment "
            "— deliveries will be UNSIGNED", index, secret_env.strip(),
        )
        return None
    secret = raw.get("secret")
    if isinstance(secret, str) and secret:
        return secret
    return None
```

运维意图是"这条通道必须签名",环境变量漏配时得到的是"照发,只是没签名"。
接收端如果没有强制校验签名,就在毫不知情的情况下接受了未认证载荷。
文档明说了这个行为(`website/docs/user-guide/features/hooks.md:1544`:"Entries without a
secret are delivered unsigned"),所以不是 ▲;但"显式配了 `secret_env` 却因变量缺失而降级"
与"压根没配 secret"是两种意图,代码把它们等同处理了。

#### ◇-4 幂等键是 `(event, url)`,secret / matcher / timeout 的变化不参与

`agent/outbound_webhooks.py:187`

```
    with _registered_lock:
        for target in targets:
            wired_any = False
            for event in target.events:
                key = (event, target.url)
                if key in _registered:
                    continue
                manager._hooks.setdefault(event, []).append(
                    _make_callback(event, target)
                )
                _registered.add(key)
                wired_any = True
```

同一进程内对同一 `(event, url)` 二次注册直接跳过。两个 URL 相同、secret 不同的 target,
第二个静默失效。同时注意第 194 行 **直接写 `manager._hooks` 这个私有属性**——
绕过了 plugin manager 的公开注册 API。

### 6.7 单 worker 的队头阻塞

`agent/outbound_webhooks.py:520`

```
def _deliver(delivery: Dict[str, Any]) -> None:
    """POST with bounded retries.  Retries on connection errors and 5xx;
    4xx is the receiver telling us the request itself is wrong — no retry.
    3xx redirects are never followed (misconfiguration — fix the URL)."""
    last_error = ""
    for attempt in range(1, MAX_DELIVERY_ATTEMPTS + 1):
        req = urlrequest.Request(
            delivery["url"],
            data=delivery["body"],
            headers=delivery["headers"],
            method="POST",
        )
        try:
            with _opener.open(req, timeout=delivery["timeout"]) as resp:
```

`_worker_loop` 只有一个线程:

`agent/outbound_webhooks.py:476`

```
        _worker = threading.Thread(
            target=_worker_loop, name="outbound-webhooks", daemon=True,
        )
        _worker.start()
```

`_deliver` 里的 `time.sleep(RETRY_BACKOFF_SECONDS * attempt)` 也在这个线程上。最坏情况:
`timeout=60` × 2 次 + 1 秒退避 = **单条投递占用 worker 约 121 秒**,期间**所有 target
的所有事件**都排在后面。队列满 256 后开始丢:

`agent/outbound_webhooks.py:458`

```
def _enqueue(delivery: Dict[str, Any]) -> None:
    _ensure_worker()
    try:
        _delivery_queue.put_nowait(delivery)
    except queue.Full:
        logger.warning(
            "outbound webhook queue full (%d pending) — dropping %s event "
            "for %s", QUEUE_MAX_SIZE, delivery["event"], delivery["label"],
        )
```

一个死掉的 target 会把健康 target 的投递一起拖垮。

`atexit` 兜底是个好设计——短命的 `-q` CLI 进程 enqueue 完 `on_session_end` 就退出的话,
daemon worker 会被直接杀掉:

`agent/outbound_webhooks.py:480`

```
        # The worker is a daemon thread, so a short-lived process (a `-q`
        # CLI run, a cron session) can exit right after enqueuing the
        # final events — silently dropping on_session_end, the headline
        # use case.  Drain the queue at interpreter shutdown, bounded so
        # a dead endpoint can only delay exit, never hang it.
        atexit.register(flush, timeout=5.0)
```

---

## 7. TLS:`ssl_guard.py` + `ssl_verify.py`

两个文件回答两个不同的问题:`ssl_guard` 问"CA 包本身是不是好的"(启动期,fail-closed),
`ssl_verify` 问"这个 client 该怎么 verify"(每次建 client,fail-open)。

### 7.1 `ssl_verify.py`:什么情况下放松,放松到什么程度

`agent/ssl_verify.py:22`

```
def resolve_httpx_verify(
    *,
    ca_bundle: Optional[str] = None,
    ssl_verify: Any = None,
    base_url: str = "",
) -> bool | ssl.SSLContext:
    """Resolve httpx ``verify`` for provider HTTP clients.

    Priority:
    1. ``ssl_verify: false`` — disable verification (local dev only)
    2. explicit ``ca_bundle`` (per-provider ``ssl_ca_cert`` config field)
    3. ``HERMES_CA_BUNDLE``, ``SSL_CERT_FILE``, ``REQUESTS_CA_BUNDLE``,
       ``CURL_CA_BUNDLE`` env vars
    4. ``True`` (httpx/certifi default)

    ``base_url`` is used only for the insecure-mode warning message.
    """
    if _coerce_insecure(ssl_verify):
        logger.warning(
            "TLS certificate verification DISABLED (ssl_verify: false) for %s — "
            "this is intended for local development only and is unsafe on any "
            "network you do not fully control.",
            base_url or "a custom provider endpoint",
        )
        return False
```

`agent/ssl_verify.py:14`

```
def _coerce_insecure(ssl_verify: Any) -> bool:
    if ssl_verify is False:
        return True
    if isinstance(ssl_verify, str) and ssl_verify.strip().lower() in {"false", "0", "no", "off"}:
        return True
    return False
```

**放松只有一个开关:`ssl_verify: false`(或 `"false"/"0"/"no"/"off"`),放松到彻底关闭
证书校验**(`verify=False`)。没有中间档(没有"只跳过主机名校验"之类)。

**谁能触发?** 这个开关是**每 provider 一条**,而且匹配是**规范化后的精确相等**:

`hermes_cli/config.py:1610`

```
    target_url = normalize_route_base_url(base_url)
    for entry in custom_providers:
        if not isinstance(entry, dict):
            continue
        entry_url = normalize_route_base_url(entry.get("base_url"))
        if not entry_url or entry_url != target_url:
            continue
```

这一点很重要,正好是 R9B 红线的**反面教材**:同样是"拿一个 URL 去查配置",这里用的是
`entry_url != target_url` 精确比较,**不是子串包含**。所以在某个 custom provider 上关掉
校验,**不会**外溢到别的主机。两个调用方:

主 client 从 `client_kwargs` 取(由 `apply_custom_provider_tls_to_client_kwargs`
按同一套精确匹配放进去):

`agent/agent_runtime_helpers.py:2253`

```
    ssl_ca_cert = client_kwargs.pop("ssl_ca_cert", None)
    ssl_verify_cfg = client_kwargs.pop("ssl_verify", None)
    httpx_verify = resolve_httpx_verify(ca_bundle=ssl_ca_cert, ssl_verify=ssl_verify_cfg)
```

辅助 client 整段包在一个兜底里——**出错就回到"校验开启"**,失败方向是安全的那一边:

`agent/auxiliary_client.py:160`

```
        return resolve_httpx_verify(
            ca_bundle=tls.get("ssl_ca_cert"),
            ssl_verify=tls.get("ssl_verify"),
            base_url=str(base_url or ""),
        )
    except Exception:
        return True
```


**注意 `base_url` 形参只用于警告文案**(`agent/ssl_verify.py:37`),不参与决策——
主机作用域完全由调用方负责。这是个容易被误读的签名。

#### ■-6 CA bundle 路径不存在时**静默回落到公共根证书**,而不是拒绝连接

`agent/ssl_verify.py:48`

```
    effective_ca = (
        (ca_bundle or "").strip()
        or os.getenv("HERMES_CA_BUNDLE", "").strip()
        or os.getenv("SSL_CERT_FILE", "").strip()
        or os.getenv("REQUESTS_CA_BUNDLE", "").strip()
        or os.getenv("CURL_CA_BUNDLE", "").strip()
    )
    if effective_ca:
        ca_path = str(Path(effective_ca).expanduser())
        if os.path.isfile(ca_path):
            return ssl.create_default_context(cafile=ca_path)
        logger.warning(
            "CA bundle path does not exist: %s — falling back to default certificates",
            effective_ca,
        )
    return True
```

四个环境变量任一指向一个**不存在**的文件时,只 warning 一句,然后 `return True`
——即用 certifi 的公共根。对"我只信我们公司 CA"这种部署意图,这是**方向错误的
fail-open**:意图从"只信内网 CA"变成了"信全世界的公共 CA",而且只留一行 warning。

同一输入下 `ssl_guard` 的判断**恰好相反**:

`agent/ssl_guard.py:46`

```
def _validate_bundle_path(label: str, value: str, *, require_substantial: bool = False) -> None:
    path = Path(value).expanduser()
    if not path.exists():
        raise _ssl_err(f"{label} points to a missing CA bundle: {value}")
    if not path.is_file():
        raise _ssl_err(f"{label} does not point to a CA bundle file: {value}")
    if require_substantial and path.stat().st_size < 1024:
        raise _ssl_err(f"{label} at {value} appears corrupted (too small)")
```

`agent/ssl_guard.py:62`

```
def verify_ca_bundle() -> None:
    """Verify configured and bundled CA certificates are present and loadable.

    Raises:
        SSLConfigurationError: If an explicit CA-bundle environment variable
            points at a bad path, or if certifi's bundled ``cacert.pem`` is
            missing/corrupt.
    """
    if _skip_ssl_guard_enabled():
        logger.debug("SSL CA bundle guard skipped via HERMES_SKIP_SSL_GUARD")
        return

    for env_var in _CA_BUNDLE_ENV_VARS:
        value = os.getenv(env_var)
        if value:
            _validate_bundle_path(env_var, value)

    try:
        import certifi
    except Exception as exc:
        raise _ssl_err(f"certifi is not importable: {exc}") from exc

    ca_bundle = str(certifi.where())
    _validate_bundle_path("certifi", ca_bundle, require_substantial=True)
```

`verify_ca_bundle` 对同样的四个环境变量做 fail-closed 校验(路径缺失直接抛
`SSLConfigurationError`),而且还额外验证 certifi 自带包能加载出证书。
所以在 `ssl_guard` 跑过的进程里,■-6 摸不到——但它有一个逃生门:

`agent/ssl_guard.py:25`

```
_SKIP_VALUES = {"1", "true", "yes", "on"}


def _skip_ssl_guard_enabled() -> bool:
    return os.getenv("HERMES_SKIP_SSL_GUARD", "").strip().lower() in _SKIP_VALUES
```

`HERMES_SKIP_SSL_GUARD=1` 关掉启动期检查后,一个坏掉的 `HERMES_CA_BUNDLE`
就会走到 `resolve_httpx_verify` 的静默回落分支。**两个文件对同一个输入给出相反判断,
中间隔着一个环境变量开关**——这正是我记 ■ 的理由:它不是"两处实现不一致"这种洁癖问题,
而是"安全属性依赖一个无关开关"。

### 7.2 谁**摸不到**这两个文件 —— 对本片主题很重要

`resolve_httpx_verify` 只服务 **httpx / OpenAI provider client**。本片的三条外发通道
**全部绕开它**:

| 通道 | HTTP 栈 | 是否经 `resolve_httpx_verify` | hermes 侧有没有传 TLS 参数 |
|---|---|---|---|
| OTLP 导出 | OTel SDK(requests) | 否 | 否(`agent/monitoring/otlp_exporter.py:115`、`agent/monitoring/gateway_health_export.py:424`、`:497` 三处构造 exporter,只传 endpoint + headers) |
| 出站 webhook | `urllib.request` | 否 | 否(`agent/outbound_webhooks.py:526` 只传 url/data/headers/method) |
| trace 上传 | `huggingface_hub` | 否 | 否(`agent/trace_upload.py:292` 只传 token) |

好的一面:**`ssl_verify: false` 不可能削弱这三条通道**。
另一面:`HERMES_CA_BUNDLE` 这个 hermes 自己的 CA 约定对它们**也不生效**
(`SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` 这类通用变量是否生效取决于各自的 HTTP 栈,
不在基线内,见 §11)。

---

## 8. 三个外发端点:端点来源 × 主机校验 × 携带凭据

| 通道 | 端点来源 | 主机/scheme 校验 | 请求上挂了什么凭据 |
|---|---|---|---|
| **OTLP 导出** | 仅 config `monitoring.export.otlp.endpoint`,默认空串(`hermes_cli/config_defaults.py:2447`);metrics/logs 由后缀改写派生(`agent/monitoring/gateway_health_export.py:231`) | **无**——只判非空(`agent/monitoring/otlp_exporter.py:112`) | **有**:`headers_env` 把任意环境变量的值挂成请求头(`agent/monitoring/otlp_exporter.py:91`) |
| **出站 webhook** | 仅 config `hooks.outbound[].url`(`agent/outbound_webhooks.py:278`) | **scheme 有**(前缀判断,`agent/outbound_webhooks.py:283`);**主机无**;3xx 不跟随(`agent/outbound_webhooks.py:513`) | **无**——只挂 HMAC 摘要(`agent/outbound_webhooks.py:444`),secret 本身不上网;但**载荷是会话/工具数据** |
| **trace 上传** | **hermes 完全不指定**:`HfApi(token=token)` 不传 `endpoint=`(`agent/trace_upload.py:292`),用库默认 | **无**——hermes 侧不做任何校验 | **有**:HF write token,取自四个环境变量之一(`agent/trace_upload.py:249`) |

**读法**:三条都**没有主机校验**,但风险等级不同。

1. 三条的端点**都来自本地 config / 环境**,没有一条来自远端响应——这与 R9B 定案的
   `gateway/relay/media.py` / `tools/skills_sync_client.py` 有本质区别,那两条是
   **远端说了算**。所以我**不把这三条记成 R9B 同型 ■**。
2. 真正"凭据 + 无校验 URL"两件事同时成立的是 **OTLP 导出**(任意 env 值挂到任意 URL)与
   **trace 上传**(HF token 交给库默认端点)。前者的 URL 是运维自己写的,
   后者的 URL hermes 根本没参与决定——**hermes 对 trace 上传目标的可见度是零**,
   而它却把回执写成了硬编码的 huggingface.co(■-5)。
3. **出站 webhook** 反过来:没有凭据外送,但**载荷本身就是最敏感的东西**(§6.2),
   而且没有主机限制、明文 http 只 warn。它是三条里唯一一条**外泄面**。

---

## 9. 测试作行为规格

### 9.1 读数

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/monitoring/
```

```console
Discovered 5 test files (~22 tests) under ['tests/monitoring']; running with -j 8
=== Summary: 5 files, 19 tests passed, 0 failed (100% complete) in 1.3s (8 workers) ===
```

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/agent/test_outbound_webhooks.py tests/agent/test_trace_upload.py tests/agent/test_ssl_verify.py tests/agent/test_ssl_ca_guard.py tests/agent/test_auxiliary_client_ssl_verify.py tests/run_agent/test_create_openai_client_ssl_verify.py
```

```console
=== Summary: 6 files, 49 tests passed, 0 failed (100% complete) in 7.9s (8 workers) ===
```

合计 **11 文件 / 68 passed / 0 failed**。环境:`/home/user/hermes-venv`,**87 个包**
(`pip list` 去表头计数,与 CLAUDE.md 记录的 R8B 基线一致),`opentelemetry` 与
`huggingface_hub` **均未安装**。

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/pip list 2>/dev/null | tail -n +3 | wc -l && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "import importlib.util as u; print('otel:', bool(u.find_spec('opentelemetry')), 'hf:', bool(u.find_spec('huggingface_hub')))"
```

```console
87
otel: False hf: False
```

### 9.2 零失败,但有一个必须交代的静默跳过

`tests/monitoring/test_otlp_exporter.py:12`

```
otel = pytest.importorskip("opentelemetry.sdk.trace", reason="otlp extra not installed")
```

整个文件被 `importorskip` 门控。本容器**没装 otlp extra**,于是它**一条也没跑**
——运行器的输出行 `✓ tests/monitoring/test_otlp_exporter.py (1s, 0.5s)` 没有 `N✓` 前缀,
正是"收集到 0 个可跑用例"的形态。所以 `19 passed` 这个数**不覆盖 span 映射与
`_resolve_headers`**。这属于**容器环境限制**(离线、不许 pip install),不是代码缺陷,
但报数时必须说明,否则下一轮拿到不同的数会误判。

### 9.3 用例作规格:它们钉住了什么,又漏了什么

`tests/monitoring/test_gateway_health_export.py:30`

```
def test_otlp_attrs_redact_strings_and_never_export_profile():
    from agent.monitoring.otlp_exporter import _span_attrs

    attrs = _span_attrs({
        "event": "gateway_health",
        "name": "gateway.lifecycle",
        "profile": "user@example.com",
        "exit_reason": "Bearer top-secret-token for user@example.com",
    })

    assert "hermes.profile" not in attrs
    assert "top-secret-token" not in str(attrs)
    assert "user@example.com" not in str(attrs)
```

这三条(`test_otlp_attrs_redact_strings_and_never_export_profile`、
`test_diagnostic_log_attributes_are_allowlisted_redacted_and_profile_free`、
`test_resource_attributes_are_allowlisted_and_sanitized`)把"白名单 + 脱敏 + profile 不外发"
钉成了规格,写得很到位。

但有两个**规格覆盖的空洞**,都能从用例本身看出来:

**(1) 资源属性用例看不见 ■-2。** 它断言 `service.name` 原样通过——而传入值恰好就是
硬编码覆盖值 `"hermes-gateway"`。

`tests/monitoring/test_gateway_health_export.py:45`

```
def test_resource_attributes_are_allowlisted_and_sanitized():
    from agent.monitoring.gateway_health_export import _safe_resource_attributes

    attrs = _safe_resource_attributes({
        "service.name": "hermes-gateway",
        "service.instance.id": "install-1",
        "deployment.environment.name": "staging",
        "user.email": "user@example.com",
        "authorization": "Bearer top-secret-token",
        "custom.request.id": "unbounded",
    })

    assert attrs == {
        "service.name": "hermes-gateway",
        "service.instance.id": attrs["service.instance.id"],
        "deployment.environment.name": "staging",
    }
    assert attrs["service.instance.id"].startswith("sha256:")
    assert "install-1" not in attrs["service.instance.id"]
```

把它换成别的名字,断言依然会过(`_safe_resource_attributes` 确实原样返回),
而**真正的覆盖发生在它的调用方 `_runtime_resource_attributes` 里**,用例没测那一层。

**(2) PII 那半条脱敏管道完全没有用例。**
`tests/monitoring/test_export_redaction.py` 的模块文档自称
"free-text PII does not [survive]"(`tests/monitoring/test_export_redaction.py:6`),
但 4 条用例里**一条 email / phone / uuid 都没有**——3 条测 secret,1 条测 fail-closed。
§2.5 那几个误伤与遗漏,没有任何用例会发现。

`tests/monitoring/test_emitter.py` 同样漏了**丢最旧**这条环形缓冲核心语义
(4 条用例:disabled、singleton 休眠、unsubscribe、热路径耗时),这也是我在 §1.3
自己写探针复现的原因。

### 9.4 基线清洁

```verify
cd /home/user/hermes-agent && git status --porcelain | wc -l && git rev-parse HEAD
```

```console
0
863e31318553cda8ad61df681d08175364d4164b
```

---

## 10. 发现清单

### ■ 代码缺陷

| # | 锚点 | 现象 |
|---|---|---|
| ■-1 | `agent/monitoring/policy.py:41` 的 `slot["install_id"] = minted` | `ensure_install_id` 发现磁盘已有 install_id 时跳过写盘,却仍返回自己新铸的 id,导出的 `service.instance.id` 与磁盘不符,破坏文档承诺的实例身份连续性(§2.1 有实测) |
| ■-2 | `agent/monitoring/gateway_health_export.py:85` 的 `attrs["service.name"] = "hermes-gateway"` | `service.name` / `service.instance.id` / `telemetry.scope` 先被资源属性白名单放行、随后被无条件覆盖;运维改 `resource_attributes.service.name` 静默不生效 |
| ■-3 | `agent/monitoring/otlp_exporter.py:122` 的 `"telemetry.scope": "gateway_monitoring",` | traces 路由的资源属性只有 3 个硬编码键,**不读** `monitoring.gateway_health_export.resource_attributes`;metrics/logs 能按 `deployment.environment.name` 分环境,traces 不能 |
| ■-4 | `agent/monitoring/cron_health.py:157` 的 `GatewayMetric(name, max(0.0, float(value)), {})` | cron 的六个 gauge 一律用空 attributes 构造,指标级标签为空,没有 `service.version` / `hermes.supervision_mode` |
| ■-5 | `agent/trace_upload.py:325` 的 `https://huggingface.co/datasets/{repo_id}` | 上传成功回执里的两条链接是硬编码 `huggingface.co`,与 `HfApi` 实际使用的端点无任何关联 |
| ■-6 | `agent/ssl_verify.py:59` 的 `"CA bundle path does not exist: %s` | `HERMES_CA_BUNDLE` 等四个变量指向不存在的文件时只 warning 并 `return True`(回落公共根),与 `agent/ssl_guard.py:49` 对同一输入的 fail-closed 判断相反,中间只隔一个 `HERMES_SKIP_SSL_GUARD` |
| ■-7(轻) | `hermes_cli/main.py:11127` 的 `Warning/error logs:` | `hermes monitoring status` 把 `logs_export_interval_seconds` 印在 "Warning/error logs" 那一行,但该间隔实际控制的是 `_start_snapshot_thread`(受 `diagnostic_events_enabled` 管,`agent/monitoring/gateway_health_export.py:560`),不是日志 handler |

### ▲ 文档与代码矛盾

| # | 锚点 | 现象 |
|---|---|---|
| ▲-1 | `docs/observability/monitoring.md:25` 的 `Signals carry` | "Signals carry `service.name`, version, supervision mode, and a stable one-way hash of the install id" 是对上方五行表格的总括,但 cron 指标(`agent/monitoring/cron_health.py:157`)无 version/supervision mode,cron span 与诊断日志白名单也都没有 supervision mode(`agent/monitoring/otlp_exporter.py:152`、`agent/monitoring/gateway_health_export.py:33`);同句后半"without exporting account/profile identity or the raw install identifier"**成立**(§2.4 实测) |
| ▲-2 | `website/docs/user-guide/features/hooks.md:1594` 的 `**No consent prompt.**` | "payloads include tool inputs and event metadata" —— 实际 `post_tool_call` 的**完整工具结果**也在 `extra.result` 里逐字外发(§6.2 实测) |
| ▲-3(较弱) | `docs/observability/monitoring.md:269` 的 `Add the key to the emitter's per-kind` | "Adding a content-free attribute" 检查表只点名 `_span_attrs` 的 `keep_by_kind` 一张白名单,并延伸到仓外 collector 的 `keep_keys`,却**漏掉仓内第二张** `_DIAGNOSTIC_ATTRIBUTE_KEYS`(`agent/monitoring/gateway_health_export.py:33`);照它做,新属性在 `/v1/logs` 上仍被静默丢弃——正是该文自己第 203-205 行"golden rule"警告的形态。判较弱是因为小节标题写的是 "event/**span**",可辩称日志不在其辖 |

### ◇ 代码有、文档无

| # | 锚点 | 现象 |
|---|---|---|
| ◇-1 | `agent/monitoring/emitter.py:118` 的 `def subscribe(self, callback) -> None:` | "content-free by construction" 实际由**导出侧两张白名单**执行,不由事件构造执行;`subscribe()` 把含原始 `install_id` / `profile` 的完整 dict 交给每个订阅者 |
| ◇-2 | `agent/monitoring/gateway_health.py:55` 的 `def redact_gateway_message(message: Any) -> str:` | `redact_gateway_message` 在 `__all__` 里但**全仓零调用方**(含 tests),是为未实现的 redacted-message 模式预留的挂起 API |
| ◇-3 | `agent/outbound_webhooks.py:365` 的 `deliveries will be UNSIGNED` | `secret_env` 指向的环境变量缺失时降级为**无签名投递**而非拒发;"配了但缺变量"与"根本没配"被等同处理 |
| ◇-4 | `agent/outbound_webhooks.py:190` 的 `key = (event, target.url)` | 注册幂等键是 `(event, url)`,secret/matcher/timeout 不参与;同 URL 不同 secret 的第二个 target 静默失效。同处第 194 行直接写 `manager._hooks` 私有属性 |
| ◇-5 | `agent/outbound_webhooks.py:488` 的 `def _worker_loop() -> None:` | 单 worker + `_deliver` 内 `time.sleep` 退避:`timeout=60` 的死 target 单条最长占用 ~121 秒,期间所有 target 队头阻塞,超 256 条开始丢 |
| ◇-6 | `agent/monitoring/emitter.py:144` 的 `waiter = threading.Thread(` | `flush()` 每次调用起一个新的、不被 join 的 waiter 线程;`emit_execution_state` 在每个终态 cron 执行后都调一次 |

### ◎ 文档成立但显著保守

| # | 锚点 | 现象 |
|---|---|---|
| ◎-1 | `docs/observability/monitoring.md:21` 的 `Warning/error gateway events` | "rendered log messages are never exported" ——**比字面更强**:原文连事件体都进不去,只在 `GatewayDiagnosticLogHandler.emit` 的栈上活一行就被 `classify_gateway_error` 折成枚举(`agent/monitoring/gateway_health.py:442`)。文档说的是"不导出",代码做到的是"不采集" |

### 内部注释与实现的小出入(不计入上面四类)

- `agent/monitoring/emitter.py:19` 说无订阅者时事件 "simply age out of the ring buffer";
  实际上 dispatcher 线程照常起(`_ensure_started` 在 `emit` 里无条件调用),
  批次被取出、扇给空订阅者列表、立即丢弃——是**被排空**,不是"老化出局"。
  只在 `enabled=True` 且零订阅者时可达(单例默认 `enabled=False`,所以生产路径碰不到)。
- `agent/monitoring/gateway_health.py:193` 的 `_base_attrs` 收 `profile` 形参却完全不使用。

---

## 11. 未取证 / 推定,如实列出

1. **`huggingface_hub` 是否读 `HF_ENDPOINT`**:未取证。该库未安装(§9.1),且它不在基线内。
   我只断言基线侧的事实:`agent/trace_upload.py:292` 不传 `endpoint=`,全仓代码零处理该变量。
   "端点可被环境重定向"是**关于第三方库的推定**,主线若要用需另行取证。
2. **OTel SDK 拿到非 http scheme 的 endpoint 会怎样**:未取证(SDK 未安装)。
   我只断言 hermes 侧不做 scheme/主机校验。
3. **`SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` 对 OTLP(requests)与 HF 上传的实际作用**:
   未取证。我只断言 hermes 侧不向这三条通道传任何 TLS 参数(§7.2 表格,三处构造点均已核)。
4. **config.yaml 能否被 agent 自身或被诱导写入**(即 `hooks.outbound` 是否可被非人类写进去):
   **未查**,超出本片文件范围。我只取证了"注册仅发生在进程启动路径"(§6.5),
   这已足以说明中途改配置不即时生效。若主线要评估这条外泄路径的完整可达性,
   需要另查 config 写入的审批门。
5. **■-1 的并发触发**:我用"内存 config 陈旧"这一路径实测复现;
   "两进程并发首启"是**同一代码路径的推论**,未实跑双进程。
6. **`agent/redact.py` 的完整覆盖面**:未通读(1,008 行,属他片)。§2.5 只是对
   `redact_for_export` 的**黑盒抽样**,不是对 `redact_sensitive_text` 覆盖面的全称结论。

### 建议主线实跑复核的两条

- **首选:▲-2 / §6.2 出站 webhook 的 `extra.result`**。一条命令即可复现,
  且直接影响"外泄面"的定性。复核脚本见 §6.2 的 ```verify 块。
- **次选:■-3 / §4.3 traces 路由丢失运维资源属性**。同样零依赖可复现(两个纯函数并排调),
  且它决定"分环境看板到底能不能用"这个很实际的结论。

---

## 12. 自校验读数

```verify
python3 scripts/verify_citations.py /home/user/hermes-agent notes/r9c-raw-monitoring-egress.md; echo "exit=$?"
```

```console
citations=114  OK=84  UNCHECKED=30
可校验比例 OK/114 = 73.7%
table_anchors=33  OK=17  UNCHECKED=16   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
OK: every code-block-backed citation matches the baseline
exit=0
```

| 项 | 读数 |
|---|---|
| citations | 114 |
| OK | 84 |
| UNCHECKED | 30 |
| 可校验比例 | **73.7%**(下限 70%,达标) |
| MISMATCH | **0** |
| BLOCK-DRIFT | **0** |
| TABLE-DRIFT | **0** |
| TABLE-OUT-OF-RANGE | **0** |
| MISSING-FILE | **0** |
| 退出码 | **0** |

表格锚点单独计:`table_anchors=33`,其中 `TABLE-OK=17`、`TABLE-UNCHECKED=16`
(后者是没在同一单元格里声明内联摘录的那些,非阻断)。

**未使用 `--fix`**,全部行号手写核对。
