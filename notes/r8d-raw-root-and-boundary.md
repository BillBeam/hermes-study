# r8d 底稿 · 簇 E —— 根模块与进程边界

> 定位:**底稿**(求全求证),不求好读。凡对 hermes-agent 行为的断言,紧跟
> `路径:行号 @ 863e313` 与代码原文块。基线只读,本轮未写入基线。
>
> 覆盖 13 个文件 / 4,266 行:
> `mcp_serve.py`(1037)、`hermes_logging.py`(800)、`utils.py`(666)、
> `hermes_cli/active_sessions.py`(426)、`hermes_cli/mem_trim.py`(255)、
> `hermes_time.py`(135)、`hermes_cli/proxy/server.py`(298)、
> `hermes_cli/proxy/adapters/nous_portal.py`(199)、`hermes_cli/proxy/adapters/xai.py`(145)、
> `hermes_cli/proxy/cli.py`(140)、`hermes_cli/proxy/adapters/base.py`(108)、
> `hermes_cli/proxy/adapters/__init__.py`(37)、`hermes_cli/proxy/__init__.py`(20)。

---

## 0. 一页纸结论

这一簇是两件不同的东西被放在了一起,值得先分开看:

**(1) 根模块**(`hermes_time` / `hermes_logging` / `utils`)—— 它们的共同性质是
**被别人 import,而自己几乎不 import 别人**(或只做惰性 import 打破循环依赖)。
它们的设计压力全部来自"我不能崩、不能慢、不能循环依赖":
`hermes_time` 三条 `except Exception: pass`、`hermes_logging` 把 `agent.redact` 做成函数内惰性 import、
`utils` 只依赖标准库 + `yaml`。地基上的一个决定确实会波及全仓,
但**本簇最大的发现恰恰是"波及"没有发生**:`hermes_time` 只被 8 个生产文件 import,
而全仓有 100 处裸 `datetime.now()`(§1.3);`hermes_logging` 的时间戳压根不走 `hermes_time`(§1.4,▲-1)。

**(2) 进程边界**(proxy / active_sessions / mem_trim / mcp_serve)—— 四个"把 Hermes 的一部分
递给另一个进程"的口子,四种完全不同的信任模型:

| 边界 | 谁在对面 | 鉴权 | 结论 |
|---|---|---|---|
| `hermes_cli/proxy/` | 任意 OpenAI 兼容客户端(HTTP) | **无**,默认只绑 `127.0.0.1`,可 `--host 0.0.0.0` | §6,文档诚实警告,非 ▲ |
| `active_sessions.py` | 同机其它 Hermes 进程 | 文件锁 + pid 存活校验 | §4,与 R7 的 gateway 租约**不是同一套** |
| `mem_trim.py` | glibc 分配器(不是进程) | n/a | §5,GC 之外的第二步 |
| `mcp_serve.py` | 任意 MCP 客户端(stdio) | **无**,靠"谁能 spawn 进程" | §7,两个工具在生产里是死的(■-1) |

记号统计:**▲ 4 条、◇ 3 条、■ 4 条、◎ 0 条**(§8 汇总)。

proxy 监听地址与鉴权:**已查清**。默认 `127.0.0.1:8645`(硬编码 IPv4 字面量,
不走 webhook 那套 dual-stack 解析,因此与本容器"无 IPv6"限制无关);
**入站零鉴权**,客户端的 `Authorization` 头被当作 hop-by-hop 丢弃;
`--host` 无任何校验,`0.0.0.0` 是被文档明确推荐的用法(§6.3)。

---

## 1. `hermes_time.py` —— 135 行的自建时钟

### 1.1 它是什么

三级解析 + 一次性缓存 + 永不抛异常。解析顺序:环境变量 → `config.yaml` 的 `timezone` 键 → 服务器本地时区。

`hermes_time.py:37-46 @ 863e313`

```python
def _resolve_timezone_name() -> str:
    """Read the configured IANA timezone string (or empty string).

    This does file I/O when falling through to config.yaml, so callers
    should cache the result rather than calling on every ``now()``.
    """
    # 1. Environment variable (highest priority — set by Supervisor, etc.)
    tz_env = os.getenv("HERMES_TIMEZONE", "").strip()
    if tz_env:
        return tz_env
```

`hermes_time.py:122-133 @ 863e313`

```python
def now() -> datetime:
    """
    Return the current time as a timezone-aware datetime.

    If a valid timezone is configured, returns wall-clock time in that zone.
    Otherwise returns the server's local time (via ``astimezone()``).
    """
    tz = get_timezone()
    if tz is not None:
        return datetime.now(tz)
    # No timezone configured — use server-local (still tz-aware)
    return datetime.now().astimezone()
```

注意 fallback 分支 `datetime.now().astimezone()` 而不是裸 `datetime.now()`:
**返回值永远 tz-aware**,这是 `now()` 的类型契约。下游(cron)靠这个契约做
`dt.replace(tzinfo=_hermes_now().tzinfo)`,如果这里可能返回 naive,那行代码会静默把
naive 赋成 naive。

### 1.2 它解决的**具体 bug**:cron #51021

问题不是"显示时间不好看",是**一次性任务永远不到期**。用户写 `hermes cron add ... 20:07`,
存储侧把 naive 的 `20:07` 按服务器本地时区(容器里常是 UTC)锚定,而到期检查侧用
`hermes_time.now()`(配置时区,如 Asia/Kolkata)。两者差 5:30,存下来的瞬间落在
用户意图之外几个小时。

`cron/jobs.py:620-634 @ 863e313`

```python
            # Make naive timestamps timezone-aware at parse time so the stored
            # value doesn't depend on the system timezone matching at check time.
            #
            # Anchor to the CONFIGURED Hermes timezone, not the server's local
            # timezone. The due-check (`get_due_jobs`) compares `next_run_at`
            # against `hermes_time.now()`, which uses the configured zone. If a
            # naive "20:07" were interpreted as server-local (e.g. UTC) while
            # now() runs in Asia/Kolkata, the stored instant would land hours
            # off from the user's wall-clock intent — far enough that one-shots
            # never become due and recurring jobs fire at the wrong time. Using
            # the configured zone makes "20:07" mean 20:07 on the same clock the
            # scheduler checks against (#51021).
            if dt.tzinfo is None:
                hermes_tz = _hermes_now().tzinfo
                dt = dt.replace(tzinfo=hermes_tz)
```

第二个用途是 **system prompt 的日期注入**,而这里有一个和 prompt cache 相关的设计取舍
——只注入**日期**不注入分钟:

`agent/system_prompt.py:535-543 @ 863e313`

```python
    from hermes_time import now as _hermes_now
    now = _hermes_now()
    # Date-only (not minute-precision) so the system prompt is byte-stable
    # for the full day.  Minute-precision changes invalidate prefix-cache KV
    # on every rebuild path (compression boundary, fresh-agent gateway turns,
    # session resume without a stored prompt).  The model can still query the
    # exact wall-clock time via tools when it actually needs it.
    # Credit: @iamfoz (PR #20451).
    timestamp_line = f"Conversation started: {now.strftime('%A, %B %d, %Y')}"
```

*(prompt cache = provider 侧对相同前缀 token 的 KV 缓存复用;prompt 每分钟变一个字节,
整段缓存作废,首 token 延迟和费用都会涨。)*

### 1.3 ◇-1:"全仓统一时钟"不成立 —— 8 个 import vs 100 处裸 `datetime.now()`

**这是一条负结论,先写搜索面。**

- 搜索面:基线仓库根,`grep -rn --include=*.py .`(即全部 `.py`,含 `website/`、`plugins/` 等),
  用 `grep -v "^./tests/"` 排除 `tests/` 目录。
- 模式 A:`(from|import) hermes_time` —— 找 import 方。
- 模式 B:`datetime\.now\(\s*\)` —— **只匹配零参数调用**(即 naive、不 tz-aware 的那种);
  带参数的 `datetime.now(tz)` / `datetime.now(timezone.utc)` 本身就是 tz-aware,不在指控范围内。
  (刻意不用 `datetime.now` 这种宽模式:它会把 `datetime.now(tz)` 也算进来,得出相反的结论。)

```verify
cd /home/user/hermes-agent
grep -rnE "(from|import) hermes_time" --include=*.py . | grep -v "^./tests/" | wc -l
grep -rnE "datetime\.now\(\s*\)" --include=*.py . | grep -v "^./tests/" | wc -l
```

实测:**9 行 import(分布在 8 个文件)** vs **100 处裸 `datetime.now()`**。
8 个 import 方全在两块业务里:`cron/*`(4)+ `agent/monitoring/cron_health.py`、
`agent/system_prompt.py`、`agent/context_compressor.py`、`gateway/run.py`(2 处,取 `get_timezone`)。

裸调用的分布(上面第二条命令的输出节选,非源码):

```console
./cli.py:4561:        self.session_start = datetime.now()
./gateway/mirror.py:74:            "timestamp": datetime.now().isoformat(),
./gateway/run.py:10510:        now = datetime.now()
./gateway/session.py:28:    return datetime.now()
./gateway/delivery.py:401:        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
./gateway/channel_directory.py:204:        "updated_at": datetime.now().isoformat(),
```

换句话说:**`timezone:` 配置只覆盖 cron 调度 + system prompt 日期 + gateway 消息时间戳渲染这三块**,
其余时间戳一律服务器本地时区。这个事实文档没有讲(◇-1),而文档还讲了更强的话(见 ▲-1)。

### 1.4 ▲-1:`timezone:` 不影响日志时间戳(文档说影响)

`website/docs/user-guide/configuration.md:2117-2119 @ 863e313`

> ## Timezone
>
> Override the server-local timezone with an IANA timezone string. Affects timestamps in logs, cron scheduling, and system prompt time injection.

按"整句/整段一并判定"的规则,这句话在 `## Timezone` 标题下讲了**三件事**,逐条判:

- "cron scheduling" —— **成立**(§1.2)。
- "system prompt time injection" —— **成立**(§1.2 已引证)。
- "timestamps in logs" —— **不成立**。

机制:日志格式串用 `%(asctime)s`,由 stdlib `logging.Formatter.formatTime` 渲染,
其 `converter` 默认是 `time.localtime`(服务器本地)。

`hermes_logging.py:82-86 @ 863e313`

```python
# Default log format — includes timestamp, level, optional session tag,
# logger name, and message.  The ``%(session_tag)s`` field is guaranteed to
# exist on every LogRecord via _install_session_record_factory() below.
_LOG_FORMAT = "%(asctime)s %(levelname)s%(session_tag)s %(name)s: %(message)s"
_LOG_FORMAT_VERBOSE = "%(asctime)s - %(name)s - %(levelname)s%(session_tag)s - %(message)s"
```

`RedactingFormatter` 只覆盖 `format()`,没有碰 `converter` 或 `formatTime`:

`agent/redact.py:1000-1008 @ 863e313`

```python
class RedactingFormatter(logging.Formatter):
    """Log formatter that redacts secrets from all log messages."""

    def __init__(self, fmt=None, datefmt=None, style='%', **kwargs):
        super().__init__(fmt, datefmt, style, **kwargs)

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact_sensitive_text(original)
```

**负结论(全仓没有别处改 converter),搜索面**:基线根,`--include=*.py`,排除 `./tests/`,
模式 `\.converter\s*=|def formatTime|converter\s*=\s*time\.` —— 三个模式并集,覆盖
"赋值 converter"、"重写 formatTime"、"converter = time.xxx" 三种写法。零命中。

```verify
cd /home/user/hermes-agent
grep -rnE "\.converter\s*=|def formatTime|converter\s*=\s*time\." --include=*.py . | grep -v "^./tests/"; echo "exit=$? (1 = 零命中)"
```

**并且做了实测**(比 grep 更硬):在 `TZ=UTC` 下设 `HERMES_TIMEZONE=Asia/Kolkata`,
对比 `hermes_time.now()` 与一条真实日志记录的 `asctime`:

```verify
cd /tmp && cat > tzprobe.py <<'EOF'
import os, sys
os.environ["HERMES_TIMEZONE"] = "Asia/Kolkata"
sys.path.insert(0, "/home/user/hermes-agent")
import hermes_time, logging
from agent.redact import RedactingFormatter
from hermes_logging import _LOG_FORMAT
print("hermes_time.now() ->", hermes_time.now().strftime("%H:%M %Z"))
rec = logging.LogRecord("t", logging.INFO, "f", 1, "msg", None, None)
rec.session_tag = ""
print("log asctime      ->", RedactingFormatter(_LOG_FORMAT).format(rec))
print("Formatter.converter is time.localtime:", logging.Formatter.converter.__name__)
EOF
TZ=UTC /home/user/hermes-venv/bin/python tzprobe.py
```

输出(非源码,作者声明):

```console
hermes_time.now() -> 07:01 IST
log asctime      -> 2026-08-09 01:31:44,182 INFO t: msg
Formatter.converter is time.localtime: localtime
```

两者差正好 5:30。**▲-1 成立**:`timezone:` 配置对日志时间戳零影响。

### 1.5 ▲-2:cron 排障文档教用户查错了地方

`website/docs/guides/cron-troubleshooting.md:43-45 @ 863e313`

> ### Check 4: Check the system clock and timezone
>
> Jobs use the local timezone. If your machine's clock is wrong or in a different timezone than expected, jobs will fire at the wrong times. Verify:

后面给的验证命令是 `date`。整段一并判:在**默认配置**(`timezone: ""`)下这句字面为真
(`now()` 落到 `datetime.now().astimezone()`);但一旦用户设了 `timezone:`
——也就是这个排障页最该覆盖的场景 —— "Jobs use the local timezone" **字面为假**,
`date` 也查不出问题,真正该看的是 `config.yaml` 的 `timezone` 与 `HERMES_TIMEZONE`。
判 **▲(条件性)**,不判 ◇:它不是"漏讲",是在有配置时给出错误断言 + 错误补救动作。

### 1.6 ◇-2 + ■-1:`reset_cache()` 零调用方,改配置不重启不生效

`hermes_time.py:109-119 @ 863e313`

```python
def reset_cache() -> None:
    """Clear the cached timezone so the next call re-resolves it.

    Call this after the configured timezone may have changed (e.g. after a
    config edit or ``HERMES_TIMEZONE`` update) to force ``get_timezone()`` /
    ``now()`` to read the new value instead of the value cached at first use.
    """
    global _cached_tz, _cached_tz_name, _cache_resolved
    _cached_tz = None
    _cached_tz_name = None
    _cache_resolved = False
```

**负结论(没有任何调用方),搜索面**:基线根,`--include=*.py --include=*.md`,
**不排除 `tests/`**(这次要证明连测试都不用它),两个模式:
`hermes_time[ .a-z_]*reset_cache`(覆盖 `hermes_time.reset_cache` / `import hermes_time` 后点调用)
与 `from hermes_time import[^\n]*reset_cache`(覆盖 from-import)。零命中。

```verify
cd /home/user/hermes-agent
grep -rnE "hermes_time[ .a-z_]*reset_cache|from hermes_time import[^\n]*reset_cache" --include=*.py --include=*.md . ; echo "exit=$? (1 = 零命中)"
```

后果:`get_timezone()` 用 `_cache_resolved` 一次性缓存,长驻进程(gateway、dashboard)
在启动后第一次取时区时定死,**此后改 `config.yaml` 的 `timezone` 或 `HERMES_TIMEZONE`
在该进程内永不生效**,只能重启。文档从没说要重启(◇-2);
而"提供了正确的失效 API 却全仓无人调用"本身是缺陷(■-1,轻度)。

旁证:测试自己绕过了这个 API,直接改私有全局,并且注释把它说成"已被移除":

`tests/test_timezone.py:23-27 @ 863e313`

```python
def _reset_hermes_time_cache():
    """Reset the hermes_time module cache (replacement for removed reset_cache)."""
    hermes_time._cached_tz = None
    hermes_time._cached_tz_name = None
    hermes_time._cache_resolved = False
```

`reset_cache` 并没有被移除(§1.6 开头那段代码块就是它的现役定义)。这是"测试注释和代码
各说各话"的典型形状:公共 API 存在、被文档、零调用,连测试都改走私有字段。

### 1.7 小观察(不计入记号)

`hermes_time.py:86-93 @ 863e313`

```python
    try:
        return ZoneInfo(name)
    except (KeyError, Exception) as exc:
        logger.warning(
            "Invalid timezone '%s': %s. Falling back to server local time.",
            name, exc,
        )
        return None
```

`except (KeyError, Exception)` 里 `Exception` 已经覆盖 `KeyError`
(`ZoneInfoNotFoundError` 是 `KeyError` 子类),元组第一项是冗余的。行为无误,只是噪音。
真正有意义的是**捕获面之宽**:任何异常都被降级成一条 warning + 服务器本地时区,
这与模块 docstring 的承诺("Hermes never crashes due to a bad timezone string")一致——
根模块选择了"永不上抛"。

---

## 2. `hermes_logging.py` —— 800 行做四件事

### 2.1 四条产物线 + 组件过滤

`setup_logging()` 按 `mode` 建 2~3 个文件 handler:`agent.log`(INFO+,catch-all)、
`errors.log`(WARNING+)、`gateway.log`(mode="gateway",只收 `gateway`/`hermes_plugins`/`plugins.platforms` 前缀)、
`gui.log`(mode="gui")。全部套 `RedactingFormatter`。

`hermes_logging.py:320-338 @ 863e313`

```python
    # --- agent.log (INFO+) — the main activity log -------------------------
    _add_rotating_handler(
        root,
        log_dir / "agent.log",
        level=level,
        max_bytes=max_bytes,
        backup_count=backups,
        formatter=RedactingFormatter(_LOG_FORMAT),
    )

    # --- errors.log (WARNING+) — quick triage log --------------------------
    _add_rotating_handler(
        root,
        log_dir / "errors.log",
        level=logging.WARNING,
        max_bytes=2 * 1024 * 1024,
        backup_count=2,
        formatter=RedactingFormatter(_LOG_FORMAT),
    )
```

**幂等的层次很讲究**:handler 注册在前,`_logging_initialized` 早退在后。

`hermes_logging.py:364-376 @ 863e313`

```python
    if _logging_initialized and not force:
        return log_dir

    # Ensure root logger level is low enough for the handlers to fire.
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)

    # Suppress noisy third-party loggers.
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    _logging_initialized = True
    return log_dir
```

这意味着:先 `setup_logging(mode="cli")`、后 `setup_logging(mode="gateway")`,
**第二次仍会补建 `gateway.log`**(handler 注册在早退之前),但不会重复设 root level /
重复压噪。去重靠 `_add_rotating_handler` 里按 `resolve()` 后的路径比对已注册 handler。

### 2.2 敏感值怎么处理 —— 三层,答案是"格式化时正则脱敏",不是"调用点自觉"

这是本簇要害问题之一,答案分三层:

**第一层:脱敏点在 formatter,不在调用点。** `RedactingFormatter.format()`
先让 stdlib 把整条记录(含 message、args、exc_info 回溯)渲染成字符串,
**再对整串跑 `redact_sensitive_text`**(§1.4 已引)。这是关键设计选择:
不要求任何调用方记得脱敏,连第三方库(`openai`、`httpx`)打出来的记录也被覆盖,
连异常回溯里的变量值也被覆盖。代价是每条记录一次正则扫描,作者用**廉价子串预检**把它压下来:

`agent/redact.py:695-700 @ 863e313`

```python
    Performance: each regex pattern is gated behind a cheap substring
    pre-check (e.g. ``"=" in text`` for ENV assignments, ``"://" in text``
    for URLs, ``"eyJ" in text`` for JWTs). On a typical hermes log line
    (no secrets) this drops the 13-pattern scan from ~5.6us to ~1.8us per
    record (-68%). The pre-checks are conservative — false positives
    still run the full regex, which then doesn't match. False negatives
```

**第二层:模式表。** `agent/redact.py` 的模式覆盖(按定义处):
`_PREFIX_PATTERNS`(`sk-`/`ghp_`/`github_pat_`/`gho_` 等已知 key 前缀,`:72`)、
ENV 赋值(`_ENV_ASSIGN_RE`,`:137`)、配置键值(`:159-185`)、YAML 赋值(`:201`)、
JSON 字段(`_JSON_FIELD_RE`,`:287`)、`Authorization` 头(`:304`)、
其它敏感头(`:316`)、Telegram bot token(`:323`)、私钥 PEM(`:328`)、
DB 连接串(`:340`)、URL 里的裸 token(`:360`)、JWT(`:369`)、
Signal 手机号(`:376`)、URL query / userinfo(`:381-424`)、表单体(`:432`)。

**第三层:可被关掉,且是 import 时快照。**

`agent/redact.py:64-69 @ 863e313`

```python
# itself) can opt out via `security.redact_secrets: false` in config.yaml
# (bridged to this env var in hermes_cli/main.py, gateway/run.py, and
# cli.py) or `HERMES_REDACT_SECRETS=false` in ~/.hermes/.env. An opt-out
# warning is logged at gateway and CLI startup so operators see the
# downgrade — see `_log_redaction_status()` in gateway/run.py and cli.py.
_REDACT_ENABLED = os.getenv("HERMES_REDACT_SECRETS", "true").lower() in {"1", "true", "yes", "on"}
```

`_REDACT_ENABLED` 在**模块 import 时**求值一次,全仓唯一的读取点在这里:

`agent/redact.py:708-711 @ 863e313`

```python
    if not text:
        return text
    if not (force or _REDACT_ENABLED):
        return text
```

于是产生一个真实的顺序约束——
`config.yaml` 的开关必须在 `hermes_logging` import `agent.redact` **之前**桥接到环境变量:

`hermes_cli/main.py:699-703 @ 863e313`

```python
# Bridge security.redact_secrets from config.yaml → HERMES_REDACT_SECRETS env
# var BEFORE hermes_logging imports agent.redact (which snapshots the flag at
# module-import time). Without this, config.yaml's toggle is ignored because
# the setup_logging() call below imports agent.redact, which reads the env var
# exactly once. Env var in .env still wins — this is config.yaml fallback only.
```

**逃生门**:`redact_sensitive_text(..., force=True)` 绕过总开关,用于"无论用户怎么设都不能吐原文"的边界。

**模块 docstring 的措辞值得警惕:**

`hermes_logging.py:14-15 @ 863e313`

```python
All files use ``RotatingFileHandler`` with ``RedactingFormatter`` so
secrets are never written to disk.
```

严格讲这是"按已知模式脱敏",不是"证明性地永不落盘";一个不匹配任何模式的自定义 token
(比如某平台的 `xoxb-` 之外的私有格式)照样落盘。这是模式匹配脱敏的固有上限,
不算 ▲(因为整句在其语境下是描述意图),但底稿要记一笔。

### 2.3 异步落盘:QueueHandler + 单 listener 线程

动机是**跨进程轮转锁**:多个 Hermes 进程写同一个 `agent.log`,
`concurrent-log-handler`(Windows)/ 外部 logrotate 会让一次 `emit` 阻塞;
若发起线程是 asyncio 事件循环,阻塞会掉 WebSocket 客户端。

`hermes_logging.py:615-632 @ 863e313`

```python
def _register_queued_handler(handler: logging.Handler) -> None:
    """Route *handler* through the shared async queue instead of attaching it to
    *root* directly, so emitting threads never block on file I/O or the
    cross-process rotation lock.  The ``QueueListener`` applies each handler's
    own level and filters on its worker thread."""
    global _log_queue, _queue_listener, _queue_atexit_registered
    with _queue_state_lock:
        if _log_queue is None:
            _log_queue = queue.SimpleQueue()
            qh = _NonFormattingQueueHandler(_log_queue)
            qh._hermes_queue = True  # type: ignore[attr-defined]
            # Always funnel through the root logger so records from any logger
            # (production passes root here; callers may pass a child) reach the
            # queue via propagation.
            logging.getLogger().addHandler(qh)
        _queued_file_handlers.append(handler)
        # Rebuild the listener with the full target set.  This only happens
        # while init_logging() adds handlers (2-3 times, queue empty), so
```

配套三个细节,每个都对应一次踩坑:

**(1) `_NonFormattingQueueHandler.prepare` 返回 `copy.copy(record)`** —— stdlib
`QueueHandler.prepare` 会格式化并丢掉 `args`/`exc_info`(为跨进程 pickle),
我们的队列是进程内的,不需要;但**必须浅拷贝**,否则发起线程上的同步 handler
会和 listener 线程争同一个 record 对象。

`hermes_logging.py:591-592 @ 863e313`

```python
    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        return copy.copy(record)
```

**(2) `flush_log_queue()` vs `drain_log_queue(timeout)`** —— 前者 stop+start
(无界等待,给测试用);后者只在硬退出路径用,把 `stop()` 丢到一次性线程并只等 `timeout` 秒:

`hermes_logging.py:666-678 @ 863e313`

```python
def drain_log_queue(timeout: float = 1.0) -> None:
    """Best-effort, time-bounded drain for hard-exit paths (no restart).

    Unlike ``flush_log_queue()``, this stops the listener WITHOUT restarting it
    (the process is about to exit) and bounds the drain: if the listener's
    worker thread is wedged on the cross-process rotation lock — the very
    failure this async-logging change exists to survive — an unbounded
    ``stop()``/join would re-freeze the shutdown path. We run ``stop()`` on a
    throwaway thread and only wait ``timeout`` seconds for it; if it hasn't
    drained by then we abandon the last few records and let ``os._exit``
    proceed. Availability beats the last log line when the disk is already
    wedged.
    """
```

**可用性优先于最后一行日志**——这句话直接写在了代码里。

**(3) 副作用:文件 handler 不在 root 上。** 它们挂在 listener 上,所以必须另开一个
访问器,否则扫 `logging.getLogger().handlers` 的代码/测试全会落空:

`hermes_logging.py:694-700 @ 863e313`

```python
def rotating_file_handlers() -> list:
    """Return the live rotating file handlers.

    They are attached to the async ``QueueListener`` rather than the root
    logger, so callers/tests must use this instead of scanning
    ``logging.getLogger().handlers``."""
    return list(_queued_file_handlers)
```

### 2.4 `_ManagedRotatingFileHandler`:每次 emit 前 stat 一次

两个职责:managed 模式(NixOS)下 chmod 0660;以及**外部轮转自愈**。后者是本簇里
最典型的"静默失败"防御:

`hermes_logging.py:428-437 @ 863e313`

```python
    2.  ``RotatingFileHandler`` keeps an open file descriptor.  If anything
        rotates the file *externally* (``logrotate``, manual ``mv``,
        another process rotating under us, a transient unlink), our fd
        keeps pointing at the renamed/unlinked inode and every subsequent
        write goes to ``gateway.log.1`` instead of ``gateway.log`` — silent
        log loss for the file every operator expects to read.  Before each
        emit we ``stat`` ``baseFilename`` and compare it against the open
        stream's inode; on mismatch we reopen.  This is the same pattern
        as stdlib ``WatchedFileHandler.reopenIfNeeded()``, adapted for
        rotating handlers.
```

代价是每条记录一次 `stat`;作者的理由是内核缓存 inode 元数据,热文件上是亚微秒级:

`hermes_logging.py:514-519 @ 863e313`

```python
    def emit(self, record: logging.LogRecord) -> None:
        # Cheap-ish stat-per-record check; the kernel caches inode metadata
        # so the syscall is sub-microsecond on a hot file.
        if self.stream is not None or os.path.exists(self.baseFilename):
            self._reopen_if_externally_rotated()
        super().emit(record)
```

---

## 3. `utils.py` —— 666 行,只依赖标准库 + yaml

分五组,每组都能对应一个真实事故:

**(a) 原子写(`atomic_replace` / `atomic_write_text` / `atomic_json_write` / `atomic_yaml_write` / `atomic_roundtrip_yaml_update`)。**
核心是 `atomic_replace` 的一个反直觉修正:`os.replace` 会**把符号链接本身替换成普通文件**。

`utils.py:91-110 @ 863e313`

```python
def atomic_replace(tmp_path: Union[str, Path], target: Union[str, Path]) -> str:
    """Atomically move *tmp_path* onto *target*, preserving symlinks.

    ``os.replace(tmp, target)`` atomically swaps ``tmp`` into place at
    ``target``.  When ``target`` is a symlink, the symlink itself is
    replaced with a regular file — silently detaching managed deployments
    that symlink ``config.yaml`` / ``SOUL.md`` / ``auth.json`` etc. from
    ``~/.hermes/`` to a git-tracked profile package or dotfiles repo
    (GitHub #16743).

    This helper resolves the symlink first so ``os.replace`` writes to
    the real file in-place while the symlink survives.  For non-symlink
    and non-existent paths the behavior is identical to a plain
    ``os.replace`` call unless the rename fails with ``EXDEV`` or ``EBUSY``;
    those cases fall back to copy/fsync/unlink for cross-device, bind-mount,
    and busy-file deployments.

    Returns the resolved real path used for the replace, so callers that
    need to re-apply permissions can target it instead of the symlink.
    """
```

配套三条:`_preserve_file_mode` / `_restore_file_mode`(`tempfile.mkstemp` 建的是 0600,
replace 后目标会继承这个紧权限,打断 Docker/NAS 挂载);
`_preserve_file_owner` / `_restore_file_owner`(root 跑的命令写用户卷,replace 会把 owner 换成 root);
以及 `IndentDumper` —— 两条写路径(PyYAML 与 ruamel)必须产出**字节一致的排版**:

`utils.py:319-332 @ 863e313`

```python
class IndentDumper(yaml.SafeDumper):
    """PyYAML dumper that indents list items under mapping keys (2-space).

    Default PyYAML emits "indentless" sequences — list items start at the
    same column as their parent mapping key.  ``ruamel.yaml`` (used by
    :func:`atomic_roundtrip_yaml_update`) emits 2-space-indented sequences.
    Mixing both styles in the same ``config.yaml`` produces a file that
    stricter parsers like ``js-yaml`` reject with ``bad indentation of a
    mapping entry``.  Forcing ``indentless=False`` aligns the two
    serializers so all write paths emit byte-identical layouts (#31999).
    """

    def increase_indent(self, flow=False, indentless=False):  # noqa: ARG002
        return super().increase_indent(flow, False)
```

这是一条**很容易被忽略的跨模块契约**:同一个文件有两个 writer,任何一个改了排版风格,
用户配置就会在另一个生态(这里是 `js-yaml`)里解析失败。

**(b) 凭据文件权限告警。** 这是"读时检查"而不是"写时收紧",定位很明确:
用户手写的 / 老版本写出的 0644 凭据文件。

`utils.py:284-294 @ 863e313`

```python
    """Warn (once per call) when a credential file is group/world-readable.

    Secret-bearing files that users create by hand (or that older Hermes
    versions wrote without an explicit mode) commonly end up 0o644 under the
    default umask. This helper is the shared read-time check for that class:
    call it before loading any token/credential file so the owner gets a
    remediation hint in the logs.

    Returns True when a warning was emitted. No-ops (returns False) on
    platforms without POSIX permission bits semantics (best effort), when the
    file is missing, or when permissions are already tight.
    """
```

`utils.py:302-305 @ 863e313`

```python
    if os.name != "posix":
        # Windows ACLs don't map onto POSIX group/other bits; st_mode there
        # is synthesized and would false-positive.
        return False
```

**(c) 启动性能:`fast_safe_load`。** 一条能被复用的经验——PyYAML 纯 Python `SafeLoader`
比 libyaml 的 `CSafeLoader` 慢约 8 倍,而 Hermes 启动要解析 `config.yaml` + 每个插件 manifest。

`utils.py:499-513 @ 863e313`

```python
# ── Fast YAML loading ────────────────────────────────────────────────────
#
# PyYAML's pure-Python SafeLoader is ~8x slower than the libyaml-backed
# ``CSafeLoader`` C extension. Startup parses config.yaml and every plugin
# manifest with the slow path, costing ~0.9s of cold-start time. The C loader
# is a true drop-in for ``safe_load`` (same restricted tag set), so prefer it
# and fall back to the pure-Python loader only when libyaml isn't compiled in.
_fast_yaml_loader = None


def _get_fast_yaml_loader():
    global _fast_yaml_loader
    if _fast_yaml_loader is None:
        _fast_yaml_loader = getattr(yaml, "CSafeLoader", None) or yaml.SafeLoader
    return _fast_yaml_loader
```

注意作者特意说明 `CSafeLoader` 是 `safe_load` 的**真 drop-in**(同样受限的 tag 集),
即换 loader 不放宽反序列化面 —— 这句是安全论证,不是性能论证。

**(d) URL 主机名比较(安全)。** 这一对函数是整簇里最值得抄走的:

`utils.py:593-601 @ 863e313`

```python
def base_url_hostname(base_url: str) -> str:
    """Return the lowercased hostname for a base URL, or ``""`` if absent.

    Use exact-hostname comparisons against known provider hosts
    (``api.openai.com``, ``api.x.ai``, ``api.anthropic.com``) instead of
    substring matches on the raw URL. Substring checks treat attacker- or
    proxy-controlled paths/hosts like ``https://api.openai.com.example/v1``
    or ``https://proxy.test/api.openai.com/v1`` as native endpoints, which
    leads to wrong api_mode / auth routing.
    """
```

`utils.py:648-658 @ 863e313`

```python
def base_url_host_matches(base_url: str, domain: str) -> bool:
    """Return True when the base URL's hostname is ``domain`` or a subdomain.

    Safer counterpart to ``domain in base_url``, which is the substring
    false-positive class documented on ``base_url_hostname``. Accepts bare
    hosts, full URLs, and URLs with paths.

        base_url_host_matches("https://api.moonshot.ai/v1", "moonshot.ai") == True
        base_url_host_matches("https://moonshot.ai", "moonshot.ai")        == True
        base_url_host_matches("https://evil.com/moonshot.ai/v1", "moonshot.ai") == False
        base_url_host_matches("https://moonshot.ai.evil/v1", "moonshot.ai")     == False
    """
```

`base_url_hostname` 的 `urlparse(raw if "://" in raw else f"//{raw}")`(`:606`)
是为了让裸主机名(`api.openai.com/v1`)也能解析出 hostname 而不是被当成 path;
`.rstrip(".")` 去掉 FQDN 尾点(`api.openai.com.` 与 `api.openai.com` 在 DNS 里等价)。

**(e) 杂项。** 全仓统一的真值集(`is_truthy_value`/`env_var_enabled`/`env_int`/
`env_float`/`env_bool` 都由它派生):

`utils.py:19 @ 863e313`

```python
TRUTHY_STRINGS = frozenset({"1", "true", "yes", "on"})
```

代理 URL 归一化 —— WSL/Clash 环境导出的 `socks://` 别名 httpx 不认:

`utils.py:566-578 @ 863e313`

```python
def normalize_proxy_url(proxy_url: str | None) -> str | None:
    """Normalize proxy URLs for httpx/aiohttp compatibility.

    WSL/Clash-style environments often export SOCKS proxies as
    ``socks://127.0.0.1:PORT``. httpx rejects that alias and expects the
    explicit ``socks5://`` scheme instead.
    """
    candidate = str(proxy_url or "").strip()
    if not candidate:
        return None
    if candidate.lower().startswith("socks://"):
        return f"socks5://{candidate[len('socks://'):]}"
    return candidate
```

以及模型能力探测 —— 注意它**故意**做名字判定而不是只看 host:

`utils.py:613-621 @ 863e313`

```python
def model_forces_max_completion_tokens(model: str) -> bool:
    """Return True for model families that require ``max_completion_tokens``.

    OpenAI's newer families reject ``max_tokens`` on /v1/chat/completions with
    HTTP 400 ``unsupported_parameter`` — the caller must send
    ``max_completion_tokens`` instead. This covers:

    - ``gpt-4o`` / ``gpt-4o-mini`` / ``gpt-4o-*``
    - ``gpt-4.1`` / ``gpt-4.1-*``
```

`utils.py:628-632 @ 863e313`

```python
    The URL-based check (``base_url_hostname == "api.openai.com"``) misses
    third-party OpenAI-compatible endpoints (custom OpenAI gateways,
    OpenRouter) that front these models and enforce the same parameter
    constraint, so name-based detection is required as a fallback.
    """
```

—— 这与 (d) 的"别用子串比 host"并不矛盾:host 判定用于**认身份**(必须严),
名字判定用于**认能力约束**(必须宽,因为同一个模型会被很多网关转发)。

---

## 4. `hermes_cli/active_sessions.py` —— 跨进程会话租约

### 4.1 要害问题:与 R7 的 gateway 租约是不是同一套?

**答案:不是同一套,是两层不同的东西;但 gateway 会同时用到这一套。** 分三点:

**(1) `gateway/turn_lease.py` 是另一套**,它是**进程内**、**按 resolved session_id** 串行化
`[load history → run → flush]` 区间的锁,解决的是"两个 routing key 映射到同一个 session_id
导致两次 turn 交错刷同一份 transcript"。

`gateway/turn_lease.py:1-9 @ 863e313`

```python
"""Per-session turn lease — serializes the [load history → run → flush] region.

Why this exists (#64934): the gateway's busy guards are keyed by ROUTING KEY
(``_active_sessions`` in the adapter, ``_running_agents`` in the runner), but
the durable transcript is owned by SESSION_ID — and ``switch_session()`` makes
the key→id mapping many-to-one (``/resume`` of a named session from a second
chat/topic, CLI-continuity rebinding, async-delegation completion pinning,
Telegram topic-binding tip-walks). Two routing keys mapped to one session_id
run concurrent turns on two different agent objects, so no per-key guard ever
```

它自己在"Known limits"里点名了本模块解决不了的那半边:

`gateway/turn_lease.py:40-43 @ 863e313`

```python
Known limits (deliberate, flagged on #64934):

- A CLI process sharing the session via CLI-continuity is outside any
  in-process lock — that pair needs a DB-level lease (separate design).
```

**(2) `hermes_cli/active_sessions.py` 是跨进程的并发**配额**,不是互斥。**
它回答的是"整机同时允许几个活跃会话",而不是"这个会话谁在跑"。

**(3) gateway 会调用这一套。** 也就是说 gateway 侧其实叠了三层:
adapter 的 `_active_sessions`(routing key → asyncio.Event,进程内)、
`turn_lease`(session_id 串行化,进程内)、以及这里的跨进程槽位:

`gateway/run.py:8528-8546 @ 863e313`

```python
    def _claim_active_session_slot(
        self,
        session_key: str,
        source: SessionSource,
    ) -> tuple[Any, Optional[str]]:
        """Claim a cross-process active-session slot for a new gateway turn."""
        if self._is_session_running(session_key):
            return None, None
        local_limit_message = self._active_session_limit_message(session_key)
        if local_limit_message is not None:
            return None, local_limit_message
        try:
            from hermes_cli.active_sessions import try_acquire_active_session

            platform = source.platform.value if source and source.platform else "gateway"
            return try_acquire_active_session(
                session_id=session_key,
                surface=f"gateway:{platform}",
                config=getattr(self, "config", None),
                metadata={
                    "platform": platform,
```

注意"先本地后跨进程"的顺序:本地计数(`_running_agent_count()`)命中上限就直接拒,
省掉一次文件锁;只有本地没满才去抢跨进程槽。

### 4.2 实现:文件锁 + 原子替换 + pid×创建时间

状态与锁都在 `~/.hermes/runtime/` 下:

`hermes_cli/active_sessions.py:117-126 @ 863e313`

```python
def _state_dir() -> Path:
    return Path(get_hermes_home()) / "runtime"


def _state_path() -> Path:
    return _state_dir() / "active_sessions.json"


def _lock_path() -> Path:
    return _state_dir() / "active_sessions.lock"
```

锁是 `fcntl.flock` / Windows `msvcrt.locking`,**拿不到锁就抛**,不静默降级:

`hermes_cli/active_sessions.py:147-155 @ 863e313`

```python
        else:
            try:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
            except Exception as exc:
                self._fh.close()
                self._fh = None
                raise RuntimeError("active session file lock unavailable") from exc
```

写盘走 tmp + `os.replace`,tmp 名里带 pid 和 uuid,避免两个进程撞同一个临时文件:

`hermes_cli/active_sessions.py:197-202 @ 863e313`

```python
def _write_entries(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"entries": entries}, fh, sort_keys=True)
    os.replace(tmp, path)
```

僵尸租约回收有两级:

**一级 `_prune_dead`:pid 存活 + 创建时间比对。** 只查 pid 会被 pid 复用骗过:

`hermes_cli/active_sessions.py:205:213 @ 863e313`

```python
def _process_start_time(pid: int) -> Optional[float]:
    # Pair pid with process create_time when psutil can read it, so a recycled
    # pid does not keep a stale lease alive indefinitely.
    try:
        import psutil  # type: ignore

        return float(psutil.Process(pid).create_time())
    except Exception:
        return None
```

`hermes_cli/active_sessions.py:240-246 @ 863e313`

```python
    expected_start = _optional_float(process_start_time)
    if expected_start is None:
        return True
    current_start = _process_start_time(pid_int)
    if current_start is None:
        return True
    return abs(current_start - expected_start) < 0.001
```

两处"取不到就返回 True"是**故意 fail-open**:psutil 缺失/无权限时宁可把租约当活的
(顶多少一个槽),也不误杀活会话。

**二级 `release_orphaned_leases`:自己清自己。** 这一级专门治"进程活了好几天但会话漏了 teardown":

`hermes_cli/active_sessions.py:390-399 @ 863e313`

```python
def release_orphaned_leases(live_lease_ids: set[str]) -> int:
    """Drop this process's registry entries that no live session owns.

    ``_prune_dead`` only reclaims leases whose owning process died. A server
    that runs for days (``hermes dashboard`` / ``serve``) never trips that
    check, so a lease whose session skipped teardown is held until restart.
    The owning process is the only authority on which of its own leases are
    real, so it drops the rest itself — exact, with no heartbeat write on the
    turn path and no staleness threshold to tune.
    """
```

这是一个很干净的设计选择,值得抄:**不做心跳、不设过期阈值**,而是让
"唯一知道真相的人"(拥有该 pid 的进程)自己在空闲 reaper tick 上对账。
心跳要在 turn 路径上写盘,阈值要调参,两个都躲开了。

还有一处省事:

`hermes_cli/active_sessions.py:400-405 @ 863e313`

```python
    pid = os.getpid()
    state_path = _state_path()
    # With the cap disabled the registry is never written, so don't take a lock
    # (or create its file) on the idle-reaper tick for the majority of installs.
    if not state_path.exists():
        return 0
```

### 4.3 fail-open 在调用点,不在模块里

模块本身会抛(锁不可用)。文档承诺 fail-open:

`website/docs/user-guide/configuration.md:1956-1957 @ 863e313`

> The cap is enforced with a local runtime lease file and is best-effort: Hermes
> fails open if the registry cannot be read or locked so users are not stranded.

承诺成立,但**兑现点在两个调用方,不在模块里**:

`cli.py:4767-4769 @ 863e313`

```python
        except Exception as exc:
            logger.warning("Failed to claim active session slot: %s", exc)
            return True
```

`gateway/run.py:8553-8555 @ 863e313`

```python
        except Exception as exc:
            logger.warning("Failed to claim active session slot: %s", exc)
            return None, None
```

### 4.4 拒绝消息为什么要点名持有者

`hermes_cli/active_sessions.py:104-113 @ 863e313`

```python
    # Name the holders: the slots are shared across CLI, desktop/TUI and the
    # messaging gateway, so the surface that gets rejected is usually NOT the
    # one squatting on them (idle desktop chats starving a Discord bot, say).
    # Without this the message is unactionable and the only way to find out is
    # reading runtime/active_sessions.json by hand.
    held = summarize_holders(entries or [])
    detail = f" Held by: {held}." if held else ""
    return (
        f"Hermes is at the active session limit ({active_count}/{max_sessions})."
        f"{detail} Try again when another session finishes."
    )
```

可迁移原则:**跨 surface 共享的配额,拒绝消息必须说明是谁占着**,
否则被拒的那一方(通常不是占用方)完全无从下手。

---

## 5. `hermes_cli/mem_trim.py` —— Python 有 GC,为什么还要手动放堆

### 5.1 要害问题:GC 不够在哪

**因为 GC 和"把内存还给操作系统"是两件事。** CPython 的 `gc.collect()` 只是把对象归还给
**Python 自己的分配器**;分配器再把小块归还给 **glibc 的 free list / arena**;
但 glibc 默认**不会**把这些空闲页 `munmap` 还给内核 —— 它留着复用。
结果是长驻 gateway 进程的 RSS 只涨不落:一次大压缩 / 一批 subagent 关闭之后,
Python 侧对象已经没了,`/proc/self/status` 的 `VmRSS` 却纹丝不动。
`malloc_trim(0)` 是显式请求 glibc 归还。

`hermes_cli/mem_trim.py:1-6 @ 863e313`

```python
"""Rate-limited heap release for long-lived Hermes gateway processes.

On Linux/glibc, ``malloc_trim(0)`` can return pages from freed Python/C
allocations to the OS.  Other platforms and allocators are safe no-ops.
Behavior is configured under ``context.memory_trim`` in ``config.yaml``.
"""
```

因此 `trim_memory` 里是 **`gc.collect()` 然后 `trim(0)`** 的两步,顺序不能反
(先让对象死掉,块才可能空,trim 才有东西可还):

`hermes_cli/mem_trim.py:218-224 @ 863e313`

```python
        try:
            before = collect_memory_snapshot()
            started = time.perf_counter()
            gc.collect()
            trim_result = trim(0)
            released = bool(trim_result)
            after = collect_memory_snapshot()
```

### 5.2 平台探测:只在 Linux+glibc 生效,探一次

`hermes_cli/mem_trim.py:148-166 @ 863e313`

```python
def _probe_glibc_malloc_trim() -> Callable[[int], int] | None:
    """Resolve glibc's malloc_trim once; return None on unsupported systems."""
    global _malloc_trim, _probe_done
    if _probe_done:
        return _malloc_trim
    _probe_done = True
    if sys.platform != "linux":
        return None
    try:
        if platform.libc_ver()[0].lower() != "glibc":
            return None
        libc = ctypes.CDLL(None)
        trim = libc.malloc_trim
        trim.argtypes = [ctypes.c_size_t]
        trim.restype = ctypes.c_int
        _malloc_trim = trim
    except Exception as exc:
        logger.debug("malloc_trim unavailable: %s", exc)
    return _malloc_trim
```

musl(Alpine)会在 `libc_ver()` 那一步被挡掉 —— musl 没有 `malloc_trim`,
硬 `CDLL` 取符号会抛。`_probe_done` 保证不支持的平台只付一次探测代价。

### 5.3 触发条件:6 个调用点 + 两级节流

**调用点(搜索面:基线根 `--include=*.py`,模式 `trim_memory|mem_trim`,
排除 `./tests/` 与 `mem_trim.py` 自身):**

```verify
cd /home/user/hermes-agent
grep -rn "trim_memory\|mem_trim" --include=*.py . | grep -v "^./tests/" | grep -v "mem_trim.py:"
```

输出(非源码,作者声明)——六处,全是**清理边界**而不是定时器:

```console
./gateway/run.py:26275:                trim_memory(reason="messaging gateway housekeeping")
./agent/context_compressor.py:6836:            trim_memory(reason="post-compression")
./tui_gateway/slash_worker.py:184:                trim_memory(reason="slash worker command completion")
./tui_gateway/server.py:1176:        trim_memory(reason="idle reaper periodic trim")
./tui_gateway/server.py:10059:                trim_memory(reason="tui turn completion")
./run_agent.py:4316:            trim_memory(force=True, reason="agent close")
```

最后一行是**全仓唯一的 `force=True`**(agent close);其余五处都靠冷却节流。

**两级节流。** 第一级是普通冷却(默认 60s,可配);第二级是**连 `force=True` 也要守的 5 秒地板**:

`hermes_cli/mem_trim.py:201-217 @ 863e313`

```python
        if not force and _last_trim_monotonic and now - _last_trim_monotonic < cooldown:
            return False
        # Even forced trims honor a short floor: AIAgent.close() forces a trim,
        # and delegate batches close N child subagents back-to-back in the SAME
        # process — without a floor that stacks N+1 uncooled full gc.collect()
        # passes (50-500ms each in a large gateway process). 5s coalesces the
        # burst while keeping the parent's final close-trim effective.
        _FORCE_FLOOR_SECONDS = 5.0
        if (
            force
            and _last_trim_monotonic
            and now - _last_trim_monotonic < _FORCE_FLOOR_SECONDS
        ):
            return False
        # Record the attempt before calling into libc so repeated failures do not
        # turn every turn boundary into an expensive full collection.
        _last_trim_monotonic = now
```

这段有三个可迁移的点:
(a) **`force` 不等于"无条件"** —— 因为触发它的 `AIAgent.close()` 会在一次 delegate 批里
被连续调 N 次,每次一个 50–500ms 的全量 `gc.collect()`,不设地板就是 N+1 次串行卡顿;
(b) **先记时间再调 libc** —— 失败也算一次尝试,否则每个 turn 边界都会重试一次昂贵的全量收集;
(c) **`_config_settings()` 每次都读配置,但用的是 `load_config_readonly()`**,理由写在原地:

`hermes_cli/mem_trim.py:40-47 @ 863e313`

```python
        # Read-only access: settings are only .get()ed and coerced, never
        # mutated — use the no-deepcopy variant. This runs on EVERY trim
        # attempt (before the cooldown check), and generating a full-config
        # deepcopy per attempt is exactly the allocator garbage this module
        # exists to release.
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly() or {}
```

"节省内存的模块自己不许制造垃圾"——这个自指的约束很漂亮。

### 5.4 ◇-3:`_FORCE_FLOOR_SECONDS` 不可配、不在文档

默认配置里有 4 个键(`enabled` / `cooldown_seconds` / `log_every_n` / `info_log_min_delta_mb`):

`hermes_cli/config_defaults.py:1625-1636 @ 863e313`

```python
        # Return freed glibc allocator pages after long-running agent/TUI
        # cleanup boundaries. Unsupported platforms are safe no-ops.
        "memory_trim": {
            "enabled": True,
            "cooldown_seconds": 60.0,
            # Successful trim calls are INFO logged every Nth periodic call;
            # force paths always log so process-close behavior is visible.
            "log_every_n": 1,
            # Suppress INFO logs only when a readable RSS change is smaller.
            # 0 reports every successful configured trim.
            "info_log_min_delta_mb": 0.0,
        },
```

而 `_FORCE_FLOOR_SECONDS = 5.0` 是函数体内的局部字面量,不可配、不在默认配置、不在文档;
把 `cooldown_seconds` 调成 0 也去不掉它。这在"我强制要一次 trim"的场景下会让调用方困惑
(`force=True` 却返回 `False`)。计 ◇-3(代码有、文档无)。

---

## 6. `hermes_cli/proxy/` —— 本地 OAuth→OpenAI 兼容代理

### 6.1 先厘清:仓库里有**两个** proxy,方向相反

`hermes_cli/proxy_cli.py:12-14 @ 863e313`

```python
The top-level command is ``hermes egress``.  Note that the inbound OAuth
reverse-proxy command (``hermes proxy``) lives elsewhere in
``hermes_cli/main.py`` — different direction, different purpose.
```

- `hermes egress`(`hermes_cli/proxy_cli.py`,903 行,**不在本簇**)—— 出站,管 iron-proxy 二进制。
- `hermes proxy`(**本簇**)—— 入站,把本机的 OAuth 订阅包装成 OpenAI 兼容端点给外部 app 用。

两棵 argparse 子树用不同的 dest 隔开,理由写得很有意思——**不是为了修今天的 bug,
是为了防明天的重构**:

`hermes_cli/proxy_cli.py:43-48 @ 863e313`

```python
    # dest='egress_command' — keeps this subparser tree disjoint from the
    # inbound OAuth ``hermes proxy`` subparser (which uses dest='proxy_command').
    # No runtime collision today since they live in separate parser trees,
    # but a future grep-and-refactor on ``proxy_command`` would otherwise
    # hit both handlers.
    sub = parent_parser.add_subparsers(dest="egress_command")
```

### 6.2 它做什么(以及刻意不做什么)

`hermes_cli/proxy/server.py:1-10 @ 863e313`

```python
"""HTTP server that forwards OpenAI-compatible requests to a configured upstream.

Listens on ``http://<host>:<port>/v1/<path>`` and forwards each request to
``<upstream-base-url>/<path>`` with the client's ``Authorization`` header
replaced by a freshly-resolved bearer from the configured adapter. The
response is streamed back unmodified, preserving SSE.

The server is intentionally minimal: it does NOT mediate, log, transform,
or rewrite request/response bodies. It's a credential-attaching forwarder.
"""
```

### 6.3 **监听地址与鉴权(要害问题,已查清)**

**默认绑定:`127.0.0.1:8645`,IPv4 字面量。**

`hermes_cli/proxy/server.py:51-56 @ 863e313`

```python
DEFAULT_PORT = 8645
DEFAULT_HOST = "127.0.0.1"
# Body cap for forwarded requests. Chat-completion payloads with long agent
# conversations can be large; mirror api_server's MAX_REQUEST_BYTES (10 MB).
# client_max_size bounds every read path, including chunked bodies.
MAX_REQUEST_BYTES = 10_000_000
```

`hermes_cli/proxy/server.py:262-265 @ 863e313`

```python
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
```

**与本容器"无 IPv6"限制的关系:无关。** `DEFAULT_HOST` 是硬编码字符串 `"127.0.0.1"`,
`TCPSite` 直接拿去绑。作为对照,同仓 webhook 平台走的是完全另一套(哨兵 `None` + 按族逐个绑):

`gateway/platforms/webhook.py:129-131 @ 863e313`

```python
DEFAULT_HOST = None
DEFAULT_PORT = 8644
_INSECURE_NO_AUTH = "INSECURE_NO_AUTH"
```

proxy **没有**这套 dual-stack 逻辑,所以它不会因为容器没有 IPv6 而失败
(CLAUDE.md 记录的 `test_default_bind_serves_both_families` 必然失败属于 webhook 那一侧,
与本簇无关);测试里唯一真绑端口的辅助函数也显式写死 IPv4:

`tests/hermes_cli/test_proxy.py:282-290 @ 863e313`

```python
async def _start_runner(app: "web.Application"):
    """Spin up an aiohttp app on an ephemeral localhost port. Returns (runner, base_url)."""
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=0)
    await site.start()
    sockets = list(site._server.sockets)  # type: ignore[union-attr]
    port = sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"
```

**入站鉴权:没有,而且是设计如此。** 客户端的 `Authorization` 头被列进 hop-by-hop 集合直接丢弃:

`hermes_cli/proxy/server.py:32-49 @ 863e313`

```python
# Headers we strip when forwarding to the upstream. ``host``/``content-length``
# are recomputed by aiohttp; ``authorization`` is replaced with our bearer.
# Everything else (content-type, accept, user-agent, x-* headers) passes through.
_HOP_BY_HOP_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "authorization",  # we replace this one
    }
)
```

**`--host` 无任何校验**,而且 help 文本主动教你开到 LAN:

`hermes_cli/subcommands/gateway.py:336-340 @ 863e313`

```python
    proxy_start.add_argument(
        "--host",
        default=None,
        help="Bind address (default: 127.0.0.1). Use 0.0.0.0 to expose on LAN.",
    )
```

`hermes_cli/proxy/cli.py:53-64 @ 863e313`

```python
    host = getattr(args, "host", None) or DEFAULT_HOST
    port = getattr(args, "port", None) or DEFAULT_PORT

    print(
        f"Starting Hermes proxy for {adapter.display_name}\n"
        f"  Listening on:  http://{host}:{port}/v1\n"
        f"  Forwarding to: (resolved per-request from your subscription)\n"
        f"  Use any bearer token in the client — the proxy attaches your real credential.\n"
        f"\n"
        f"Press Ctrl+C to stop.",
        file=sys.stderr,
    )
```

**判定:这不是 ▲,也不算硬 ■。** 文档极其诚实地写了后果:

`website/docs/user-guide/features/subscription-proxy.md:171-174 @ 863e313`

> ⚠ **Be aware:** anyone on your network can now use your Portal
> subscription. The proxy has no auth of its own — it accepts any bearer.
> Use a firewall, VPN, or reverse proxy with proper auth if you expose
> this beyond your trusted network.

需要精确说清**风险边界**:泄露的是**订阅额度的使用权**,不是凭据本身
—— bearer 只加在**出站**请求上,客户端拿不到它;而且路径被 adapter 的
`allowed_paths` 白名单挡住(Nous 4 条、xAI 5 条):

`hermes_cli/proxy/server.py:110-122 @ 863e313`

```python
    async def handle_proxy(request: "web.Request") -> "web.StreamResponse":
        # Extract the path *after* /v1
        rel_path = request.match_info.get("tail", "")
        rel_path = "/" + rel_path.lstrip("/")

        if rel_path not in adapter.allowed_paths:
            allowed = ", ".join(sorted(adapter.allowed_paths))
            return _json_error(
                404,
                f"Path /v1{rel_path} is not forwarded by this proxy. "
                f"Allowed: {allowed}",
                code="path_not_allowed",
            )
```

### 6.4 ■-2(轻度):非 loopback 绑定时运行时零警告,且与同仓 api_server 的姿态相反

同一个仓库里,`gateway/platforms/api_server.py` 对同类问题采取了**完全相反**的姿态
——**没有 `API_SERVER_KEY` 就拒绝启动,连只绑 loopback 也拒**:

`gateway/platforms/api_server.py:6944-6952 @ 863e313`

```python
    def _api_key_passes_startup_guard(self) -> bool:
        """Return True when API_SERVER_KEY is present and strong enough to start."""
        if not self._api_key:
            logger.error(
                "[%s] Refusing to start: API_SERVER_KEY is required for the API server, "
                "including loopback-only binds on %s.",
                self.name, self._host,
            )
            return False
```

差异是**可辩护的**(api_server 会派发 terminal-capable 的 agent 工作,proxy 只转发推理),
仓库文档自己也把这个差别明确摆在对照表里:

`website/docs/user-guide/features/subscription-proxy.md:21 @ 863e313`

> | Auth | Your `API_SERVER_KEY` | Any bearer (proxy attaches the real one) |

仍记 ■-2 的理由只有一条,且限定得很窄:**`cmd_proxy_start` 在 `host` 非 loopback 时
不打印任何警告**——上面那段 banner 对 `127.0.0.1` 和 `0.0.0.0` 一字不差。
唯一的警告在网页文档里,而选择 `--host 0.0.0.0` 的人未必读过那一页;
同仓 api_server 证明了"在启动路径上直接 `logger.error` 说清后果"是本项目认可的做法。
这是**缺一句 warn**,不是设计错误。

### 6.5 适配器:两种"续命"策略

`UpstreamAdapter` 抽象四个必需成员(`name` / `display_name` / `allowed_paths` /
`is_authenticated` / `get_credential`)加一个可选的 `get_retry_credential`,默认不重试:

`hermes_cli/proxy/adapters/base.py:84-96 @ 863e313`

```python
    def get_retry_credential(
        self,
        *,
        failed_credential: UpstreamCredential,
        status_code: int,
    ) -> Optional[UpstreamCredential]:
        """Return an alternate credential after an upstream auth failure.

        The default is no retry. Providers can override this for one-shot
        fallback paths after the upstream rejects the first request.
        """
        _ = failed_credential, status_code
        return None
```

服务器只在 401/429 时问一次,拿到新凭据就**关掉旧 session、重开一次**;
拿不到就把原始响应流回客户端(注意 `except Exception` 把"取重试凭据本身失败"也降级成"不重试"):

`hermes_cli/proxy/server.py:200-216 @ 863e313`

```python
        if upstream_resp.status in {401, 429}:
            try:
                retry_cred = adapter.get_retry_credential(
                    failed_credential=cred,
                    status_code=upstream_resp.status,
                )
            except Exception as exc:
                logger.warning("proxy: retry credential resolution failed: %s", exc)
                retry_cred = None

            if retry_cred is not None:
                upstream_resp.release()
                await session.close()
                session_or_response, upstream_resp = await _open_upstream(retry_cred)
                if upstream_resp is None:
                    return session_or_response
                session = session_or_response
```

**只重试一次**:第二次请求的响应直接进流式回传,不再检查 401/429。这是刻意的
——凭据轮换若第二次还失败,多半是账号侧问题,继续重试只会放大上游压力。

- **Nous(`nous_portal.py`)**:401 → 强制刷新 inference JWT。它对 base_url 做了三层防御:
  env 覆盖优先 → 网络侧校验 → 生产默认。理由写在原地(为了不误杀合法的 staging 覆盖):

  `hermes_cli/proxy/adapters/nous_portal.py:136-149 @ 863e313`

  ```python
              # base_url returned by resolve_nous_runtime_credentials() already
              # honors the NOUS_INFERENCE_BASE_URL env override (the documented
              # dev/staging escape hatch). Re-validating it here against the prod
              # host allowlist would wrongly reject a legitimate staging override,
              # so layer the same env-first overlay on top of the network-validated
              # value: env override wins, else validate the returned URL, else
              # fall back to the production default (defense-in-depth for a future
              # source-layer bypass).
              base_url = (
                  _nous_inference_env_override()
                  or _validate_nous_inference_url_from_network(refreshed.get("base_url"))
                  or DEFAULT_NOUS_INFERENCE_URL
              )
              base_url = base_url.rstrip("/")
  ```

  刷新失败且判定为**终态**错误时,把 OAuth 状态隔离(quarantine)并落盘(`:109-123`),
  避免用一个已死的 refresh token 反复打上游。

- **xAI(`xai.py`)**:走 `CredentialPool`,401 与 429 处理不同 —— 429 直接标记冷却并轮换,
  401 先试刷新、失败再轮换;并且**新旧 bearer 相同就不重试**(防止无意义的二次请求):

  `hermes_cli/proxy/adapters/xai.py:90-106 @ 863e313`

  ```python
              if status_code == 429:
                  # Mark the rate-limited key with its 1-hour cooldown and rotate
                  # to the next available credential. Returns None when the pool
                  # has no other key to offer — the 429 will flow back to the client.
                  refreshed = pool.mark_exhausted_and_rotate(status_code=status_code)
              else:
                  refreshed = pool.try_refresh_current()
                  if refreshed is None:
                      refreshed = pool.mark_exhausted_and_rotate(status_code=status_code)
              if refreshed is None:
                  return None

              retry_cred = self._credential_from_entry(refreshed)
              if retry_cred.bearer == failed_credential.bearer:
                  return None
              logger.info(
                  "proxy: xAI upstream returned %s; retrying with rotated pool credential",
                  status_code,
              )
  ```

### 6.6 流式回传的资源纪律

`hermes_cli/proxy/server.py:225-236 @ 863e313`

```python
        try:
            async for chunk in upstream_resp.content.iter_any():
                if chunk:
                    await resp.write(chunk)
        except (aiohttp.ClientError, asyncio.CancelledError) as exc:
            logger.warning("proxy: streaming interrupted: %s", exc)
        finally:
            upstream_resp.release()
            await session.close()

        await resp.write_eof()
        return resp
```

`iter_any()`(而非 `iter_chunked(n)`)保证 SSE 事件不被重新分块;
`finally` 里 `release()` + `close()` 保证客户端中途断开时上游连接不泄漏。
每个请求新建一个 `ClientSession` —— 简单但没有连接池复用,对本地单用户代理是合理取舍。

---

## 7. `mcp_serve.py` —— 把会话暴露成 MCP 工具

*(MCP = Model Context Protocol,一套让外部 LLM 客户端调用本地工具的协议;
stdio 传输意味着客户端**直接 spawn 这个进程**并用标准输入输出通信。)*

### 7.1 暴露了什么:10 个工具,零权限边界

`mcp_serve.py:1-13 @ 863e313`

```python
"""
Hermes MCP Server — expose messaging conversations as MCP tools.

Starts a stdio MCP server that lets any MCP client (Claude Code, Cursor, Codex,
etc.) list conversations, read message history, send messages, poll for live
events, and manage approval requests across all connected platforms.

Matches OpenClaw's 9-tool MCP channel bridge surface:
  conversations_list, conversation_get, messages_read, attachments_fetch,
  events_poll, events_wait, messages_send, permissions_list_open,
  permissions_respond

Plus: channels_list (Hermes-specific extra)
```

| 工具 | 定义处 | 读/写 | 边界 |
|---|---|---|---|
| `conversations_list` | `mcp_serve.py:612` | 读全部会话索引 | 只有 `platform`/`search`/`limit` **过滤**,不是权限 |
| `conversation_get` | `:669` | 读单会话元数据 | 无 |
| `messages_read` | `:702` | 读 transcript | 只留 `user`/`assistant` 角色,内容截断 2000 字符 |
| `attachments_fetch` | `:759` | 读附件块 | 无 |
| `events_poll` | `:811` | 读事件队列 | 无 |
| `events_wait` | `:840` | 长轮询 | `timeout_ms` 上限 5 分钟 |
| `messages_send` | `:874` | **写:向任意平台任意目标发消息** | **无** |
| `channels_list` | `:910` | 读可发目标 | 无 |
| `permissions_list_open` | `:964` | 读待审批 | 见 §7.2 |
| `permissions_respond` | `:980` | 写:批准/拒绝 | 见 §7.2 |

**权限边界的实际答案:唯一的边界是"谁能 spawn 这个进程"。**
没有 allowlist、没有只读模式、没有 per-tool 开关、没有 session/平台白名单。
`messages_send` 直接调内部发送引擎:

`mcp_serve.py:896-905 @ 863e313`

```python
        try:
            from tools.send_message_tool import send_message_tool
            result_str = send_message_tool(
                {"action": "send", "target": target, "message": message}
            )
            return result_str
        except ImportError:
            return json.dumps({"error": "Send message tool not available"})
        except Exception as e:
            return json.dumps({"error": f"Send failed: {e}"})
```

由于是 stdio,这个信任模型是自洽的(能 spawn 进程的人本来就能直接跑 `hermes send`)。
文档也明确说了只有 stdio(`mcp.md:860`)。所以**不判 ■**;但值得记的是:
接入一个 MCP 客户端 = 把"以你的身份向任意已连平台发消息"的能力交给该客户端背后的模型,
这一点在文档的工具表里读不出来。

### 7.2 ■-1(本簇最重):两个审批工具在生产里**永远是空的**

`_pending_approvals` 初始化为空 dict,只被读和 pop,**从来没有被写过**:

`mcp_serve.py:331-336 @ 863e313`

```python
        self._last_poll_timestamps: Dict[str, float] = {}  # session_key -> unix timestamp
        # In-memory approval tracking (populated from events)
        self._pending_approvals: Dict[str, dict] = {}
        # mtime cache — skip expensive work when state.db hasn't changed
        self._state_db_mtime: float = 0.0
        self._cached_sessions_index: dict = {}
```

注释写着 "(populated from events)",但 `_poll_once` 里**唯一**的 `_enqueue` 调用只产 `type="message"`:

`mcp_serve.py:562-576 @ 863e313`

```python
            for msg in new_messages:
                content = _extract_message_content(msg)
                if not content:
                    continue
                self._enqueue(QueueEvent(
                    cursor=0,
                    type="message",
                    session_key=session_key,
                    data={
                        "role": msg.get("role", ""),
                        "content": content[:500],
                        "timestamp": str(msg.get("timestamp", "")),
                        "message_id": str(msg.get("id", "")),
                    },
                ))
```

从不产 `approval_requested`,也从不写 `_pending_approvals`。

**负结论(全仓无写入点),搜索面**:基线根,`--include=*.py`,**不排除 tests**,
模式 `_pending_approvals`(整个标识符,不是子串猜测)。命中分三类:
(a) `gateway/run.py` / `gateway/slash_commands.py` / `gateway/session_state.py` 里的
**同名但无关**属性 —— 那是 gateway runner 的字段,与 EventBridge 无任何引用关系:

`gateway/run.py:5817-5820 @ 863e313`

```python
    _session_ephemeral_pin = legacy_dict_property("_session_ephemeral_pin")
    _session_vc_last = legacy_dict_property("_session_vc_last")
    _pending_approvals = legacy_dict_property("_pending_approvals")
    _update_prompt_pending = legacy_dict_property("_update_prompt_pending")
```

(同名不同物这件事本身就是排查陷阱:一条 `grep _pending_approvals` 会给出 70 多个命中,
其中绝大多数属于 gateway,很容易让人以为"这个字段当然有人写";)
(b) `mcp_serve.py` 自身的 4 处(1 处初始化 + 2 处读 + 1 处 pop);
(c) `tests/test_mcp_serve.py` 的 5 处**直接注入**。生产写入点:**零**。

```verify
cd /home/user/hermes-agent
grep -rn "_pending_approvals" --include=*.py . | grep -v "^./tests/" | grep -v "^./gateway/"
grep -rn "approval_requested" --include=*.py .
```

第二条命令只回两行,**都在注释/docstring 里**,没有一处 `_enqueue`:

`mcp_serve.py:292-298 @ 863e313`

```python
@dataclass
class QueueEvent:
    """An event in the bridge's in-memory queue."""
    cursor: int
    type: str  # "message", "approval_requested", "approval_resolved"
    session_key: str = ""
    data: dict = field(default_factory=dict)
```

**后果(生产行为):**
- `permissions_list_open` 恒返回 `{"count": 0, "approvals": []}`;
- `permissions_respond(id, decision)` 恒返回 `{"error": "Approval not found: <id>"}`;
- `events_poll` / `events_wait` 永不产出 `approval_requested` 事件。

即 **10 个广告出来的工具里有 2 个是死的**。

**并且:即使 `_pending_approvals` 被填上,`respond_to_approval` 也不会真的批准任何东西。**
它只是从进程内 dict pop 掉,再往自己的队列塞一条事件——没有任何 IPC 到 gateway:

`mcp_serve.py:422-437 @ 863e313`

```python
    def respond_to_approval(self, approval_id: str, decision: str) -> dict:
        """Resolve a pending approval (best-effort without gateway IPC)."""
        with self._lock:
            approval = self._pending_approvals.pop(approval_id, None)

        if not approval:
            return {"error": f"Approval not found: {approval_id}"}

        self._enqueue(QueueEvent(
            cursor=0,  # Will be set by _enqueue
            type="approval_resolved",
            session_key=approval.get("session_key", ""),
            data={"approval_id": approval_id, "decision": decision},
        ))

        return {"resolved": True, "approval_id": approval_id, "decision": decision}
```

docstring 老实承认 "best-effort without gateway IPC",但**返回值写的是 `"resolved": True`**
——对 MCP 客户端(以及它背后的模型)来说,这是一个"我已经批准了"的肯定答复。
这属于 ■-1 的第二半:**返回值与实际效果不符**。

**测试为什么没抓到:** 5 个审批用例全部**直接往私有 dict 里塞数据**,
从没走过任何能填充它的生产路径:

`tests/test_mcp_serve.py:890-899 @ 863e313`

```python
    def test_respond_allow(self, mcp_server_e2e, _event_loop):
        server, bridge = mcp_server_e2e
        bridge._pending_approvals["a1"] = {"id": "a1", "kind": "exec"}
        result = _run_tool(server, "permissions_respond",
                          {"id": "a1", "decision": "allow-once"})
        assert result["resolved"] is True
        assert result["decision"] == "allow-once"
        # Should be gone now
        check = _run_tool(server, "permissions_list_open")
        assert check["count"] == 0
```

这是"测试给了假信心"的教科书样本:5 个用例全绿,而被测功能在生产里一次都跑不起来。
唯一如实反映生产的是 `test_list_empty`(`:872-876`),它断言 `count == 0` ——
恰好是生产的**唯一**可能结果。

### 7.3 ▲-3:文档把这两个死工具当成活的

`website/docs/user-guide/features/mcp.md:826-827 @ 863e313`

> | `permissions_list_open` | List pending approval requests observed during this bridge session. |
> | `permissions_respond` | Allow or deny a pending approval request. |

`website/docs/user-guide/features/mcp.md:841 @ 863e313`

> Event types: `message`, `approval_requested`, `approval_resolved`

整段判定:这张表在 `### Available tools` 标题下,开头一句是
"The MCP server exposes 10 tools";同页还有一节专门讲已知限制,列了 4 条:

`website/docs/user-guide/features/mcp.md:858-863 @ 863e313`

> ### Current limits
>
> - The embedded `hermes mcp serve` exposes a **stdio-only** MCP server today. If you need an HTTP MCP server, run a separate adapter — or, much more commonly, use the MCP **client** side of Hermes, which already speaks both stdio and HTTP (`url` + `headers` in `mcp_servers.yaml` / `config.yaml`; see [HTTP servers](#http-servers) above).
> - Event polling at ~200ms intervals via mtime-optimized DB polling (skips work when files are unchanged)
> - No `claude/channel` push notification protocol yet
> - Text-only sends (no media/attachment sending through `messages_send`)

四条里**没有一条**提到审批工具不可用。也就是说文档不仅在工具表里正面承诺了这个能力,
还在"我们知道自己缺什么"的清单里把它排除在外。`approval_requested` 事件类型同理:
文档列了,代码不产。**▲-3。**

(注:中文站的同名页面是同一断言的翻译,同一处 ▲,不重复计数。)

### 7.4 ■-3:`hermes mcp serve --verbose` 不会开启 DEBUG

`mcp_serve.py:1016-1019 @ 863e313`

```python
    if verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
```

调用链是这样接上的:

`hermes_cli/mcp_config.py:1074-1079 @ 863e313`

```python
    """Main dispatcher for ``hermes mcp`` subcommands."""
    action = getattr(args, "mcp_action", None)

    if action == "serve":
        from mcp_serve import run_mcp_server
        run_mcp_server(verbose=getattr(args, "verbose", False))
```

而在此之前,`hermes_cli/main.py` 在**模块 import 期**就已经建好了 root handler:

`hermes_cli/main.py:747-757 @ 863e313`

```python
try:
    from hermes_logging import setup_logging as _setup_logging

    _setup_logging(
        mode=(
            "gui"
            if next((arg for arg in sys.argv[1:] if not arg.startswith("-")), "")
            in {"dashboard", "serve", "gui", "desktop"}
            else "cli"
        )
    )
except Exception:
    pass  # best-effort — don't crash the CLI if logging setup fails
```

`setup_logging` 会给 root 挂一个 `_NonFormattingQueueHandler`(§2.3)。
stdlib `logging.basicConfig` 的 `level=` 参数是在 `if len(root.handlers) == 0:`
分支**内部**才被应用的 —— root 已有 handler 时,整个 `level=` 被静默丢弃。

**实测(比读 CPython 源码更硬):**

```verify
cd /tmp && cat > mcpverbose.py <<'EOF'
import os, sys, logging, tempfile
os.environ["HERMES_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, "/home/user/hermes-agent")
from hermes_logging import setup_logging
setup_logging(mode="cli")                       # what hermes_cli/main.py:750 does
print("root level after setup_logging:", logging.getLevelName(logging.getLogger().level))
print("root handlers:", [type(h).__name__ for h in logging.getLogger().handlers])
logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)   # mcp_serve.py:1017
print("root level after basicConfig(DEBUG):", logging.getLevelName(logging.getLogger().level))
print("hermes.mcp_serve DEBUG enabled?:",
      logging.getLogger("hermes.mcp_serve").isEnabledFor(logging.DEBUG))
EOF
/home/user/hermes-venv/bin/python mcpverbose.py
```

输出(非源码,作者声明):

```console
root level after setup_logging: INFO
root handlers: ['_NonFormattingQueueHandler']
root level after basicConfig(DEBUG): INFO
hermes.mcp_serve DEBUG enabled?: False
```

**■-3 成立**:`--verbose` 是空操作。`mcp_serve.py` 里所有 `logger.debug(...)`
(如 `:501` 的 "EventBridge poll error")在这条路径上永远不会输出,
而这些恰恰是排障最需要的。修法很小:`basicConfig(..., force=True)`,
或直接调 `hermes_logging.setup_verbose_logging()`。

顺带一条 ▲(并入 ▲-4 计数):`mcp.md:848-849` 写

> hermes mcp serve              # Normal mode
> hermes mcp serve --verbose    # Debug logging on stderr

"Debug logging on stderr" 与实测不符。这与 ■-3 是同一现象的文档面,单独计为 **▲-4**。

### 7.5 EventBridge:200ms 轮询靠一次 mtime 检查变成"几乎免费"

`mcp_serve.py:504-514 @ 863e313`

```python
    def _poll_once(self, db):
        """Check for new messages across all sessions.

        Uses a single mtime check on state.db to skip work when nothing
        has changed — makes 200ms polling essentially free.  Since #9006
        the routing index itself lives in state.db (session rows carry
        session_key/origin metadata), so a new conversation and its first
        message land in the SAME file and one mtime check covers both —
        eliminating the old dual-file (sessions.json + state.db) race that
        could drop brand-new conversations (#8925).
        """
```

两个真实教训固化在这里:
- **#8925(双文件竞态)**:路由索引原本在 `sessions.json`、消息在 `state.db`,
  两个文件两次 mtime 检查,新会话的第一条消息可能在"索引还没刷新"的窗口里被丢掉。
  修法是把路由元数据搬进 `state.db`(#9006),于是**一次 mtime 检查同时覆盖两者**。
- **#13414(启动重放)**:`start()` 里先 `_establish_baseline()` 记下每个会话的最新时间戳
  **且不发事件**,否则 MCP 客户端一连上来就被历史消息灌一遍:

`mcp_serve.py:342-348 @ 863e313`

```python
        # Snapshot existing history BEFORE the poll loop starts so pre-existing
        # messages are not replayed as new events on startup (#13414). Sessions
        # that first appear afterwards are absent from the baseline and default
        # to last_seen=0.0 in _poll_once, so new-conversation delivery is
        # preserved. Unit tests that drive _poll_once directly bypass start()
        # and still observe first-poll delivery.
        self._establish_baseline()
        self._running = True
```

最后一句尤其值得学:作者明确交代了"单元测试直接驱动 `_poll_once` 会绕开 `start()`,
因此仍能观察到首轮投递"——把**测试与生产在这一点上行为不同**这件事写进了注释。

### 7.6 ■-4(轻度):`events_poll` 的 `limit` 在过滤之后才截断,`next_cursor` 可能倒退

`mcp_serve.py:369-384 @ 863e313`

```python
        with self._lock:
            events = [
                e for e in self._queue
                if e.cursor > after_cursor
                and (not session_key or e.session_key == session_key)
            ][:limit]

        next_cursor = events[-1].cursor if events else after_cursor
        return {
            "events": [
                {"cursor": e.cursor, "type": e.type,
                 "session_key": e.session_key, **e.data}
                for e in events
            ],
            "next_cursor": next_cursor,
        }
```

`next_cursor` 取的是**返回的最后一条**的 cursor,这本身没问题。
真正的问题在 `_enqueue` 的队列裁剪:

`mcp_serve.py:439-448 @ 863e313`

```python
    def _enqueue(self, event: QueueEvent) -> None:
        """Add an event to the queue and wake any waiters."""
        with self._lock:
            self._cursor += 1
            event.cursor = self._cursor
            self._queue.append(event)
            # Trim queue to limit
            while len(self._queue) > QUEUE_LIMIT:
                self._queue.pop(0)
        self._new_event.set()
```

上限是硬编码的:

`mcp_serve.py:288-289 @ 863e313`

```python
QUEUE_LIMIT = 1000
POLL_INTERVAL = 0.2  # seconds between DB polls (200ms)
```

客户端如果轮询间隔内产生了 >1000 条事件,
早的事件被从队头丢弃,**客户端无法察觉**:它拿到的下一批 cursor 会直接跳号,
但返回体里没有任何"你漏了 N 条"的信号(没有 `dropped` / `oldest_cursor` 字段)。
对一个以 `after_cursor` 做断点续传的协议来说,**静默丢事件**是缺陷。记 ■-4(轻度)。
另外 `{... , **e.data}` 把事件负载平铺进顶层,`data` 里若出现 `cursor`/`type`/`session_key`
同名键会覆盖协议字段——目前 `data` 的产出点只有两处、键名可控,所以是隐患不是现症,不单独计数。

---

## 8. 记号汇总

### ▲ 文档与代码矛盾(4 条)

| # | 位置 | 文档说 | 代码实际 | 证据 |
|---|---|---|---|---|
| ▲-1 | `website/docs/user-guide/configuration.md:2119` | `timezone:` "Affects timestamps in logs" | 日志走 stdlib `time.localtime`,与 `timezone:` 无关;实测差 5:30 | §1.4 |
| ▲-2 | `website/docs/guides/cron-troubleshooting.md:45` | "Jobs use the local timezone",教用户查 `date` | 配了 `timezone:` 时用配置时区,`date` 查不出问题 | §1.5 |
| ▲-3 | `website/docs/user-guide/features/mcp.md:826-827, 841` | 两个审批工具可用;有 `approval_requested` 事件 | 生产里恒空/恒报错;该事件从不产出 | §7.2–7.3 |
| ▲-4 | `website/docs/user-guide/features/mcp.md:849` | `--verbose` = "Debug logging on stderr" | `basicConfig` 是 no-op,DEBUG 未开启(实测) | §7.4 |

### ◇ 代码有、文档无(3 条)

| # | 内容 | 证据 |
|---|---|---|
| ◇-1 | `timezone:` 的**实际覆盖面只有三块**(cron 调度 / system prompt 日期 / gateway 消息时间戳);全仓另有 100 处裸 `datetime.now()` 走服务器本地时区 | §1.3 |
| ◇-2 | 时区一经解析即进程内缓存且**无人调用 `reset_cache()`**,改配置必须重启进程;文档从未提及 | §1.6 |
| ◇-3 | `mem_trim._FORCE_FLOOR_SECONDS = 5.0` 连 `force=True` 也挡,不可配、不在 `DEFAULT_CONFIG`、不在文档 | §5.4 |

### ■ 代码缺陷(4 条)

| # | 严重度 | 内容 | 证据 |
|---|---|---|---|
| ■-1 | **高** | `mcp_serve` 的 `permissions_list_open` / `permissions_respond` 在生产里结构性失效(`_pending_approvals` 无写入点);且 `respond_to_approval` 返回 `"resolved": True` 而实际未做任何事 | §7.2 |
| ■-2 | 低 | proxy 绑定非 loopback 时运行时零警告,与同仓 `api_server` 的启动守卫姿态相反 | §6.4 |
| ■-3 | 中 | `hermes mcp serve --verbose` 不开启 DEBUG(`basicConfig` 在 root 已有 handler 时丢弃 `level=`) | §7.4 |
| ■-4 | 低 | `EventBridge` 队列满 1000 后静默丢弃队头事件,协议无溢出信号,断点续传客户端察觉不到 | §7.6 |

### ◎ 文档成立但显著保守:**0 条**

(`mcp.md:814` "exposes 10 tools" —— 实际正好 10 个,字面精确,不是 ◎。)

---

## 9. 测试作行为规格

**环境记录(按 CLAUDE.md 要求,且本轮必须多说一句)**:`/home/user/hermes-venv`,
**本簇未安装任何包、未改动 venv**。但共享 venv 在本轮**被别人改了**,必须交代:

```verify
ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l
ls -la --time-style=+%H:%M:%S -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | awk '{print $6, $7}' | sort | tail -8
```

首次跑测试时是 **87 个包**(与 R8B 记录一致),收尾复核时变成 **93**。
按 CLAUDE.md "直接断言、不要间接推断"的要求去看 `dist-info` 时间戳,而不是猜:
87 个的时间戳集中在 `01:19:41`–`01:20:14`(venv 初建),
另外 6 个是 `01:33:43`–`01:33:45` 装进来的 ——
`boto3` / `botocore` / `jmespath` / `s3transfer`(AWS)、`edge_tts`(TTS)、`tabulate`。
即本轮有**同伴子代理往共享 venv 装了平台 extra**,与本簇无关。

**处置**:不做推断,直接在 93 包状态下把 7 个文件**整体重跑一遍**,
结果与 87 包时**逐文件相同**(见下表)。本簇 7 个文件都不受这 6 个包门控
(它们是 AWS/TTS/表格渲染,与 `hermes_time` / `hermes_logging` / `utils` /
`active_sessions` / `mem_trim` / proxy / `mcp_serve` 无依赖关系),所以两次读数一致是预期内的。
**下表的数是 93 包状态下的复核值。**

运行方式:

```verify
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/hermes_cli/test_proxy.py tests/hermes_cli/test_mem_trim.py \
  tests/hermes_cli/test_active_sessions.py tests/test_mcp_serve.py tests/test_hermes_logging.py \
  tests/test_timezone.py tests/agent/test_context_compressor_temporal_anchoring.py
```

| 文件 | 用例数 | 结果 |
|---|---|---|
| `tests/hermes_cli/test_proxy.py` | 4 | 全通过 |
| `tests/hermes_cli/test_mem_trim.py` | 12 | 全通过 |
| `tests/hermes_cli/test_active_sessions.py` | 3 | 全通过 |
| `tests/test_mcp_serve.py` | 88 | 全通过 |
| `tests/test_hermes_logging.py` | 28 | 全通过 |
| `tests/test_timezone.py` | 11 | 全通过 |
| `tests/agent/test_context_compressor_temporal_anchoring.py` | 2 | 全通过 |

**合计 7 个文件 / 148 个用例 / 0 失败。** 本簇**没有**遇到 CLAUDE.md 里记录的三类
环境性必然失败(无 IPv6 / root / 离线 models.dev)——原因见 §6.3:
proxy 的测试显式绑 `127.0.0.1`,不依赖 dual-stack。

几个用例值得作为规格记住:

- `test_server_strips_client_auth_header`(`tests/hermes_cli/test_proxy.py:344`)——
  唯一一个真起两个 aiohttp server(假上游 + proxy)的端到端用例,
  断言客户端的 `Bearer SHOULD_NOT_LEAK` 到不了上游,上游看到的是 `Bearer ours`。
  **这就是 proxy 鉴权模型的可执行规格:客户端 bearer 被丢弃,不是被校验。**
- `test_force_floor_coalesces_burst_closes`(`tests/hermes_cli/test_mem_trim.py:186`)—— §5.3 那个 5 秒地板的规格。
- `test_cross_process_acquire_claims_only_one_last_slot`(`tests/hermes_cli/test_active_sessions.py:49`)——
  真正起多进程抢最后一个槽,验证文件锁。
- `test_release_orphaned_leases_reclaims_only_unowned_own_pid_entries`(`:142`)——
  规格化了 §4.2 二级回收的**边界**:只清自己 pid 的、且不在 `live_lease_ids` 里的。
- `TestE2EPermissions` 5 个用例(`tests/test_mcp_serve.py:871-919`)—— §7.2 的反面教材。

---

## 10. 移交项(附锚点文件 + 一句话现象)

1. **`mcp_serve` 审批链路是否曾经存在过 / 是否有别处的桥接。**
   锚点:`mcp_serve.py:333`(`self._pending_approvals: Dict[str, dict] = {}`,注释写
   "(populated from events)" 但全仓无写入点)。现象:注释描述的填充路径不存在,
   需要确认是"从未实现"还是"被摘除后遗留",这决定 ■-1 该报成缺陷还是死代码。

2. **`hermes_time` 缓存与 `hermes config set timezone` 的交互。**
   锚点:`hermes_time.py:102`(`if not _cache_resolved:`,一次性缓存)。
   现象:`reset_cache()` 零调用方,长驻进程改时区不生效;
   未查证 `hermes config set` 路径是否会重启相关进程或有别的失效手段。

3. **`utils.atomic_*` 与 R8B 的 H-7(坏 YAML 静默抹掉 `approvals.deny`)是否同源。**
   锚点:`utils.py:335`(`atomic_yaml_write`,先 `yaml.dump` 再原子替换,
   写入前不校验待写数据是否完整)。现象:该函数忠实写出调用方给的 dict,
   若调用方读到的是被降级的空/残缺配置,原子性只保证"完整地写坏"。
   本簇未追调用方,仅标注这是那类缺陷的落盘端。

4. **`EventBridge` 队列溢出信号。** 锚点:`mcp_serve.py:446-447`
   (`while len(self._queue) > QUEUE_LIMIT: self._queue.pop(0)`)。
   现象:队头被静默丢弃,`poll_events` 返回体无 `dropped`/`oldest_cursor` 字段,
   客户端只能看到 cursor 跳号。若后续轮做 MCP 章,这是"断点续传协议怎么设计"的正例反面。

5. **`_filter_response_headers` 不过滤 `Set-Cookie`。** 锚点:`hermes_cli/proxy/server.py:75-85`
   (只剔 hop-by-hop + `content-encoding`/`content-length`)。现象:上游若下发 cookie,
   会原样透给客户端。当前两个 adapter 的上游都是纯 JSON API,未见实际影响,
   但这是新增 adapter 时的踩坑位。
