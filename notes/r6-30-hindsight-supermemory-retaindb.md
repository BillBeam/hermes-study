# R6 底稿 · hindsight + supermemory + retaindb 记忆后端

> 溯源约定:凡断言紧跟 `路径:行号 @ 863e313` + 逐字代码块,行号在基线工作区实测。学习对象只读。
> 上一轮已定前提:MemoryProvider ABC 契约(`agent/memory_provider.py`),MemoryManager 一次一个外部 provider、读 8s 围栏、写单 worker 离线;298s 阻塞事故是写路径离线化的直接动因。

---

## 0. 公共前提(本轮三家共用的 harness 侧事实)

**读围栏 8s 在 harness 侧,不在 provider 侧。**

`agent/memory_manager.py:47 @ 863e313`
```python
_EXTERNAL_PREFETCH_TIMEOUT_S = 8.0
```

`agent/memory_manager.py:580-588 @ 863e313`(`_prefetch_provider`:外部 provider 的 `prefetch()` 在专用线程上跑,主线程只等 8s,超时就放弃这次注入并跳过后续轮,直到卡住的调用返回)
```python
        thread.join(self._external_prefetch_timeout)
        if thread.is_alive():
            logger.warning(
                "Memory provider '%s' prefetch timed out after %.1fs; skipping it until "
                "the stuck call returns",
                provider.name,
                self._external_prefetch_timeout,
            )
            return ""
```

**298s 事故的正典表述在 `sync_all` 的 docstring 里**,`agent/memory_manager.py:648-657 @ 863e313`:
```python
        Runs on a background worker thread, NOT inline on the
        turn-completion path. A provider's ``sync_turn`` may make a
        blocking network/daemon call (a misconfigured Hindsight daemon
        was observed blocking ~298s before failing); doing that inline
        held ``run_conversation`` open long after the user saw their
        response, so every interface (CLI, TUI, gateway) kept the agent
        marked "running" for minutes and any follow-up message triggered
        an aggressive interrupt. Dispatching off-thread means a slow or
        broken provider can never stall the turn — the sync simply
        completes (or fails, logged) in the background.
```

结论先行:harness 已经把"读有界、写离线"做成了对所有 provider 的通用防御;本轮看的是三家 provider 在围栏**内侧**各自又做了什么(自己的超时、自己的队列、自己的失败方向),三种风格差异极大。

---

## 1. Hindsight(`plugins/memory/hindsight/__init__.py`,2232 行)

### 1.1 它是什么

**三种形态合一的 provider:云 API、进程内管理的本地 daemon、外接已有实例。** 默认 cloud。

`plugins/memory/hindsight/__init__.py:56-57 @ 863e313`
```python
_DEFAULT_API_URL = "https://api.hindsight.vectorize.io"
_DEFAULT_LOCAL_URL = "http://localhost:8888"
```

- **cloud**:vectorize.io 的托管 API,走 `hindsight_client.Hindsight` SDK,API key 认证。
- **local_embedded**:插件自己拉起并管理一个本地 Hindsight daemon(`HindsightEmbedded`,内置 PostgreSQL、用 `sentence_transformers` 本地算嵌入),需要一个外部 LLM key 做事实抽取;`"local"` 是 legacy 别名(`__init__.py:1512-1514`:`if self._mode == "local": self._mode = "local_embedded"`)。**就是这个形态的 daemon 配错时造成了 298s 事故。**
- **local_external**:只连 URL,不管 daemon 生命周期。

### 1.2 存储/检索形态

服务端概念:**bank**(记忆库,命名空间)/ **retain**(写入,服务端自动抽取结构化事实、消解实体)/ **recall**(多策略检索:语义+关键词+实体图+重排)/ **reflect**(跨记忆 LLM 综合作答)/ **observation**(整合层:去重、有证据支撑的"信念")。三个工具 schema 原文见 `__init__.py:305-354`。

**recall 默认只取 observation 层**,理由写在代码注释里,`__init__.py:785-793 @ 863e313`:
```python
        # Default to observation-only recall. Observations are Hindsight's
        # consolidated knowledge layer — deduplicated, evidence-grounded
        # beliefs built from many raw facts, with proof counts and
        # freshness signals (see hindsight.vectorize.io/developer/observations).
        # Including raw world/experience facts re-ships the supporting
        # evidence that observations already summarize, burning the
        # `recall_max_tokens` budget. Users can restore the broader
        # recall via the `recall_types` config key.
        self._recall_types: list[str] = ["observation"]
```

**写入以"会话文档"为单位**:每个进程生命周期铸造唯一 `document_id`,`__init__.py:1461-1464 @ 863e313`:
```python
        # Each process lifecycle gets its own document_id. Reusing session_id
        # alone caused overwrites on /resume — the reloaded session starts
        # with an empty _session_turns, so the next retain would replace the
        # previously stored content. session_id stays in tags so processes
        start_ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self._document_id = f"{self._session_id}-{start_ts}"
```

**服务端能力探测决定增量还是全量重发**:对 API URL 探一次 `/version`(缓存于进程级 dict,`__init__.py:173`),≥0.5.0 支持 `update_mode='append'`,则复用稳定的 session 级 document_id、每次只发新增轮;老 API 退回"每进程唯一 doc id + 每次重发全量",`__init__.py:1433-1452 @ 863e313`:
```python
    def _resolve_retain_target(self, fallback_document_id: str) -> tuple[str, str | None]:
        """Pick (document_id, update_mode) based on live API capability.
        ...
        if not self._session_id:
            return fallback_document_id, None
        if _check_api_supports_update_mode_append(self._probe_url(), self._api_key):
            return self._session_id, "append"
        return fallback_document_id, None
```
探测失败取安全默认 False(`__init__.py:217-224`:"Returns False on any probe failure — that's the safe default")。append 路径只发 delta,`__init__.py:1896-1900`:`turns_to_retain = self._session_turns[self._last_retained_turn_count:]`,水位线在**入队之后**才推进(`__init__.py:1957-1960`)。

### 1.3 ABC 各方法映射

| ABC 方法 | 实现位置(行号) | 行为要点 |
|---|---|---|
| `name` | 802-804 | `"hindsight"` |
| `is_available` | 806-823 | 按 mode:local→探 import;local_external→恒 True;cloud→有 key 或有 URL |
| `initialize` | 1454-1692 | 读配置、铸 doc_id、客户端版本自动升级、local_embedded 的 root 检查与 daemon 后台启动 |
| `system_prompt_block` | 1694-1714 | 按 memory_mode(context/tools/hybrid)三种文案 |
| `queue_prefetch`(重写) | 1734-1786 | 起后台线程做 recall/reflect,结果写入缓存 |
| `prefetch` | 1716-1732 | 只 join 3s + 消费缓存,**本身不打网络** |
| `sync_turn` | 1862-1960 | 只入内存队列,单写者线程消化 |
| `get_tool_schemas` | 1962-1965 | context 模式返回 `[]`,否则三工具 |
| `handle_tool_call` | 1967-2038 | retain/recall/reflect,同步调用(在工具执行线程上) |
| `on_session_switch` | 2040-2167 | flush 老会话缓冲、清 prefetch 缓存、旋转 doc_id |
| `shutdown` | 2169-2227 | sentinel 停写者(join 10s)、join prefetch(5s)、关客户端、**不停共享 loop** |
| `on_memory_write` | 未实现 | — |
| `on_session_end` | 未实现 | — (见 1.10 第 7 条) |
| `get_config_schema` / `save_config` / `post_setup` / `backup_paths` | 1057-1099 / 825-840 / 842-1055 / 684-692 | 完整 setup 向导;备份路径 `~/.hindsight` |

### 1.4 认证与配置

**配置解析三级**,`__init__.py:361-368 @ 863e313`:
```python
def _load_config() -> dict:
    """Load config from profile-scoped path, legacy path, or env vars.

    Resolution order:
      1. $HERMES_HOME/hindsight/config.json  (profile-scoped)
      2. ~/.hindsight/config.json             (legacy, shared)
      3. Environment variables
    """
```
API key 走 `get_secret("HINDSIGHT_API_KEY", "")`(`__init__.py:389`,即 profile 域秘密解析,不是裸 `os.environ`)。

**local_embedded 的 LLM key 落地为 `~/.hindsight/profiles/<profile>.env`,强制 0600**,`__init__.py:565-580 @ 863e313`:
```python
def _secure_write_profile_env(profile_env, content: str) -> None:
    """Create/overwrite *profile_env* with owner-only (0600) permissions.

    The file carries the embedded daemon's plaintext LLM API key
    (``HINDSIGHT_API_LLM_API_KEY``), so it must never be created with the
    default umask-derived mode. A pre-existing file is tightened *before*
    the new secret bytes are written.
    """
    if profile_env.exists():
        try:
            os.chmod(profile_env, 0o600)
        except OSError:
            pass
    fd = os.open(str(profile_env), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
```
写后校验不过就把文件删掉(`__init__.py:612-619`:"Never leave a plaintext API key behind")。

**桌面面板的声明式 schema 是另一份**(`plugins/memory/hindsight/config_schema.py:22-33`),只暴露 `cloud` / `local_external` 两个 mode 选项——local_embedded 被有意排除在桌面配置面板之外(CLI 向导才有三选)。

### 1.5 并发模型:一 loop、一写者、一预取线程

**进程级共享事件循环**(避免每次调用建临时 loop 泄漏 aiohttp session),`__init__.py:269-283`;同步侧通过 `future.result(timeout)` 桥接,`__init__.py:286-293 @ 863e313`:
```python
def _run_sync(coro, timeout: float = _DEFAULT_TIMEOUT):
    """Schedule *coro* on the shared loop and block until done."""
    from agent.async_utils import safe_schedule_threadsafe
    loop = _get_loop()
    future = safe_schedule_threadsafe(coro, loop)
    if future is None:
        raise RuntimeError("Hindsight loop unavailable")
    return future.result(timeout=timeout)
```

**单写者线程 + 内存队列**,动机注释即事故教训,`__init__.py:724-728 @ 863e313`:
```python
        # Single-writer model for retain. sync_turn() enqueues; the writer
        # thread drains sequentially. Avoids spawning ad-hoc threads that
        # can race the interpreter shutdown and emit "cannot schedule new
        # futures after interpreter shutdown" / "Unclosed client session".
        self._retain_queue: queue.Queue = queue.Queue()
```
写者循环单条失败不死,`__init__.py:1372-1380 @ 863e313`:
```python
            try:
                if job is _WRITER_SENTINEL:
                    return
                try:
                    job()
                except Exception as exc:
                    logger.warning("Hindsight retain failed: %s", exc, exc_info=True)
            finally:
                self._retain_queue.task_done()
```
写者惰性启动(tools-only 模式不付空转线程,`__init__.py:1173-1178`),并注册幂等 atexit 钩子兜底 CLI 直接退出的场景(`__init__.py:1382-1393`)。

### 1.6 超时/重试/失败方向

**Hindsight 自己有超时,且是三家里最长的:默认 120s,可配。** `__init__.py:60 @ 863e313`:
```python
_DEFAULT_TIMEOUT = 120  # seconds — cloud API can take 30-40s per request
```
生效点有二:cloud 客户端构造参数(`__init__.py:1145-1146`:`kwargs = {"base_url": self._api_url, "timeout": float(timeout)}`)与 `self._run_sync`(`__init__.py:1154-1156`:`return _run_sync(coro, timeout=self._timeout)`)。注意 `future.result(timeout)` 到期只抛 TimeoutError、**不取消协程**(`agent/async_utils.py:63`:底层是 `asyncio.run_coroutine_threadsafe`),协程仍在共享 loop 上跑完——超时是"放弃等待",不是"中止请求"。

**重试:仅 embedded 断连场景重试一次**(daemon 空闲自杀后重连),`__init__.py:1403-1418 @ 863e313`:
```python
    def _run_hindsight_operation(self, operation):
        """Run an async Hindsight client operation, retrying once after idle shutdown."""
        client = self._get_client()
        try:
            return self._run_sync(operation(client))
        except Exception as exc:
            if not self._is_retriable_embedded_connection_error(exc):
                raise
            logger.info(
                "Hindsight embedded daemon appears unreachable; recreating client and retrying once: %s",
                exc,
            )
            self._client = None
            client = self._get_client()
            self._client = client
            return self._run_sync(operation(client))
```
可重试判定只认连接类错误文本(`__init__.py:1158-1171`:"cannot connect to host" / "connection refused" / "connect call failed" / "clientconnectorerror"),且仅 local_embedded 模式。

**失败方向:自动路径全部 fail-open。** retain 失败→写者 log warning 丢弃(上引 1377-1378);prefetch 失败→log debug、缓存留空(`__init__.py:1782-1783`:`logger.debug("Hindsight prefetch failed: %s", e, ...)`);/version 探测失败→当 legacy API(`__init__.py:208-210`)。**工具路径 fail-visible**:异常包成 `tool_error(...)` 回给模型(`__init__.py:1990-1991` 等)。

### 1.7 对 298s 事故的代码防御(问题:hindsight 侧现在有没有自己的超时?)

**有,而且是多层的;但真正保证回复路径零阻塞的是结构,不是超时数值。**

1. **回复路径读:`prefetch()` 从不打网络**,只等后台线程最多 3s、然后消费(并清空)缓存,`__init__.py:1716-1725 @ 863e313`:
```python
    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            logger.debug("Prefetch: waiting for background thread to complete")
            self._prefetch_thread.join(timeout=3.0)
        with self._prefetch_lock:
            result = self._prefetch_result
            self._prefetch_result = ""
```
   3s(provider 侧)< 8s(harness 围栏),双保险且 provider 先触发。
2. **回复路径写:`sync_turn()` 只入队**(docstring 明说 Non-blocking,`__init__.py:1862-1868`),网络调用全在写者线程,单次调用被 `_run_sync(timeout=120)` 封顶,不会像事故里那样无限阻塞。
3. **daemon 起不来不再无声空转**:root 检测直接禁用并打印(注释点名 issue #13125),`__init__.py:1628-1650 @ 863e313`:
```python
            # PostgreSQL's initdb refuses to run as root by design, so the
            # embedded daemon can never initialize its data directory under
            # root. Without this guard the daemon-start thread would fail,
            # retry, and loop forever — each cycle reloading embedding models
            # (~958MB RAM, ~33% CPU) with no user-visible error. Detect root
            # up front and skip daemon startup with a clear message instead.
            if hasattr(os, "geteuid") and os.geteuid() == 0:
```
   daemon 启动本身也在后台线程(`__init__.py:1691-1692`:`t = threading.Thread(target=_start_daemon, daemon=True, ...)`),日志重定向到 `hindsight-embed.log` 而非终端。
4. **local runtime 坏了直接降级**:import 探针(含 `sentence_transformers`)失败→`self._mode = "disabled"` 并 return(`__init__.py:1519-1526`),不再反复试起坏后端。
5. **shutdown 有界**:写者 join 10s,超时弃单并 warning(`__init__.py:2183-2189`:"abandoning %d pending retain(s)");prefetch join 5s。
6. **daemon 侧节流配置**:空闲 300s 自杀(`__init__.py:61`),`/health` 宽限期可调且必须在 import daemon 管理器之前用 `os.environ.setdefault` 导出(`__init__.py:103-127`,显式 env 覆盖优先)。

### 1.8 读后写可见性:两道栅栏 + drop 语义(hindsight 独有)

问题:写离线之后,下一轮的预取可能**跑在刚写完的 retain 之前**,recall 就会缺最后一轮。且 `retain_async=True` 时服务端"受理即返回",本地队列排空≠可见。方案注释,`__init__.py:762-772 @ 863e313`:
```python
        # Async retain never blocks the reply (writes drain on the single
        # writer thread). But the next turn's warm prefetch runs on its own
        # thread and could read BEFORE the just-completed retain is
        # recall-visible on the server, dropping the latest turn from recall.
        # When True, the background prefetch first waits (bounded) for the
        # local writer queue to drain AND for the server-side async retain
        # operation(s) to report completion, an explicit read-after-write
        # signal — closing that race without putting any write on the reply
        # path.
        self._prefetch_waits_for_retain = True
        self._prefetch_retain_drain_timeout = 10.0
```
栅栏一:轮询 `unfinished_tasks`(而非 `queue.join()`,避免 wedged 写把预取吊死)每 0.05s(`__init__.py:1271-1281`);栅栏二:轮询服务端 `get_operation_status` 每 0.5s(每次都是网络往返,故意比本地粗,`__init__.py:742-746`),404 视为完成(`__init__.py:1220-1242`),瞬时错误继续等。**到期未决的 op 被丢弃而非保留**——否则一个永远失败的 status 端点会让 pending 集合无限增长、每轮预取都烧满预算,`__init__.py:1293-1302 @ 863e313`:
```python
        Ops still pending when the deadline expires are DROPPED, not retained:
        keeping them would make a permanently failing status endpoint (auth
        error, endless 500s, server that loses ops without a 404) grow the
        pending set forever and burn the full timeout on EVERY subsequent
        prefetch — turning "bounded wait per prefetch" into unbounded
        session-wide degradation (and, via prefetch()'s bounded join on the
        reply path, a per-turn reply-latency penalty). Dropping trades a
```

### 1.9 会话切换与关闭的细节

`on_session_switch`(`__init__.py:2040-2167`):先把老会话缓冲的轮次以**老 doc_id、老 update_mode、老 metadata**(全部先快照)flush 一笔——且这笔 flush **走同一条写者队列**以保证 FIFO(`__init__.py:2136-2145`:"That serializes it behind any still-queued retains from the old session");再 join 老预取线程并清缓存(防新会话读到旧 recall);最后旋转 `_session_id`/`_document_id`/清计数器。动机注释点名 hermes-agent#6672 与 vectorize-io/hindsight#1303。

`shutdown`(`__init__.py:2169-2227`):先 `_shutting_down.set()`(此后 `sync_turn` 直接丢弃,`__init__.py:1873-1875`),再 sentinel+join;**刻意不停共享事件循环**——它被同进程所有 provider 实例共享,停了会把兄弟实例的 aiohttp session 撂死在 loop 上(注释点名 #11923,`__init__.py:2217-2227`)。

### 1.10 README vs 代码对照(hindsight)

| # | README 断言 | 代码事实 | 判定 |
|---|---|---|---|
| 1 | `README.md:49`"Config file: `~/.hermes/hindsight/config.json`" | `__init__.py:364-367` 还有第 2 级 legacy 回退 `~/.hindsight/config.json` 与第 3 级 env,README 未提 | ▲ README 少讲两级 |
| 2 | `README.md:133-143` 环境变量表只列 7 个 | 模块 docstring `__init__.py:12-25` 另有 `HINDSIGHT_TIMEOUT` / `HINDSIGHT_IDLE_TIMEOUT` / `HINDSIGHT_EMBED_PORT_HEALTH_GRACE_TIMEOUT` / 4 个 `HINDSIGHT_RETAIN_*`,均真实生效(如 `__init__.py:390-396`) | ▲ README 环境变量表不全 |
| 3 | `README.md:31`"stops after 5 minutes of inactivity" | `__init__.py:61` `_DEFAULT_IDLE_TIMEOUT = 300` | ✓ |
| 4 | `README.md:147`"auto-upgrades on session start" | `__init__.py:1466-1487` initialize 里检版本、`install_specs` 升级 | ✓ |
| 5 | `README.md:67-100` 配置表 | 缺 `timeout`/`idle_timeout`/`port_health_grace_timeout`/`observation_scopes`/`prefetch_waits_for_retain`/`prefetch_retain_drain_timeout`/`retain_every_n_turns`,这些都在 `get_config_schema`(`__init__.py:1079-1098`) | ▲ README 配置表不全 |
| 6 | `README.md:78-87` recall_types 默认 observation-only、工具与自动召回共用同一设置 | `__init__.py:793`、`1771-1772`(prefetch)与 `2005-2006`(工具)同读 `self._recall_types`;RECALL_SCHEMA(326-339)确无 per-call types 参数 | ✓ 完全一致 |
| 7 | `plugin.yaml:7-8` 声明 `hooks: - on_session_end` | `HindsightMemoryProvider` **没有**实现 `on_session_end`(grep 全类无此方法);且全仓无代码消费 plugin.yaml 的 `hooks` 键(消费 `pip_dependencies` 的是 `hermes_cli/memory_setup.py:123-134`) | ▲ 惰性元数据,与实现不符 |
| 8 | `config_schema.py:22-33` 桌面面板 mode 只有 cloud/local_external | `get_config_schema`(`__init__.py:1059`)与 README 有三 mode | ◇ 两个配置面之间的口径差,桌面有意不提供 local_embedded |

### 1.11 配套测试(行为规格)

文件:`tests/plugins/memory/test_hindsight_provider.py`(1375 行)、`test_hindsight_env_perms.py`(80)、`test_hindsight_config_schema.py`(51);harness 侧 `tests/agent/test_memory_async_sync.py`(文件头逐字复述 298s 事故与修法)。

精选规格两条:
- **`test_prefetch_waits_for_pending_retain_before_recall`**(`test_hindsight_provider.py:505-538`):慢 retain 卡住时,queue_prefetch 起的线程必须停在栅栏前(0.2s 后 `order == []`),放行后顺序必须是 `["retain", ..., "recall"]`——这是"读后写栅栏"的可执行定义。
- **`test_timed_out_ops_are_dropped_not_repolled`**(`test_hindsight_provider.py:652-682`):永远 pending 的 op 在第一次预取烧完 0.3s 预算后必须被清空(`p._pending_retain_ops == set()`),第二次预取必须 <0.25s——这是"drop 换 liveness"的可执行定义。

### 1.12 重实现要点(hindsight 簇)

1. 桥接 async SDK 用**一个进程级常驻 loop + `run_coroutine_threadsafe`**,绝不在调用点建临时 loop;记住 `future.result(timeout)` 不取消协程,超时语义是"放弃等待"。
2. 写路径 = 内存队列 + 惰启单写者 + sentinel 退出 + atexit 兜底;单条失败 log 后继续,`task_done()` 放 finally。
3. 异步受理型服务端要做**显式读后写栅栏**(本地排空 + 服务端 op 完成),且到期必须**丢弃**未决 op,防止一次故障变全会话退化。
4. 会话文档策略:doc_id = session + 进程时间戳防 /resume 覆盖;探测服务端能力(缓存/URL)决定 append 增量 vs 全量重发;水位线在入队后推进。
5. 会话切换先 flush 老状态(全字段快照)且走同一队列保序;shutdown 一切 join 有界;共享资源(loop)的生命周期归进程不归实例。
6. 明文密钥文件 `os.open(..., 0o600)` 创建、写后验证、验证失败即删除。
7. 本地后端要有"起不来"三连防:import 探针降级、root/环境前置检查、启动线程化 + 日志重定向。

---

## 2. Supermemory(`plugins/memory/supermemory/__init__.py`,1053 行)

### 2.1 它是什么

**纯云 API(可自托管改 base_url),官方 Python SDK + 一处手写 HTTP。** 默认端点与自托管解析:

`plugins/memory/supermemory/__init__.py:35 @ 863e313`
```python
_DEFAULT_BASE_URL = "https://api.supermemory.ai"
```
`__init__.py:82-91`:base_url 优先级 config(`supermemory.json`)> `SUPERMEMORY_BASE_URL` env > 默认。SDK 客户端构造(注意 **max_retries=0** 与来源头),`__init__.py:302-308 @ 863e313`:
```python
        self._client = Supermemory(
            api_key=api_key,
            base_url=self._base_url,
            timeout=timeout,
            max_retries=0,
            default_headers={"x-sm-source": "hermes"},
        )
```
唯一绕开 SDK 的调用是整会话 ingest,直接 `urllib` POST `/v4/conversations`(`__init__.py:407-418`),超时 = `self._timeout + 3`(`__init__.py:417`:`urllib.request.urlopen(req, timeout=self._timeout + 3)`)。

### 2.2 存储/检索形态

命名空间是 **container_tag**(支持 `{identity}` 模板做 profile 隔离,`__init__.py:663-666`);写入两类:`documents.add` 单条记忆(带 `entity_context` 抽取指导,内置默认指导语强调"When in doubt, store less",`__init__.py:47-55`)与**整会话一次性 ingest**;检索两类:`search.memories`(hybrid/memories/documents 三模式)与 **profile**(static 持久事实 + dynamic 近期上下文 + 附带搜索结果,`__init__.py:357-380`)。注入文本包在 `<supermemory-context>` 标签里(`__init__.py:262-267`),写回前用正则剥掉自己注入过的标签防回流(`__init__.py:41-46` + `270-273`)。

### 2.3 ABC 映射(与 hindsight 的关键差异加粗)

| ABC 方法 | 行号 | 行为要点 |
|---|---|---|
| `is_available` | 568-576 | **只查 key 不查 SDK**(注释:惰装 SDK,查 import 是先有鸡还是先有蛋) |
| `initialize` | 653-702 | 读 `supermemory.json`、解析 tag/base_url、`agent_context in {"cron","flush","subagent"}` 时禁写(687)、建 SDK 客户端 |
| `on_turn_start` | 704-705 | 记 turn 号(供 profile 注入频率用) |
| `system_prompt_block` | 707-721 | 工具用法 + 多容器说明 |
| `prefetch` | 723-738 | **同步打网络**(`get_profile(query=...)`),无 `queue_prefetch` 重写 → 完全依赖 harness 8s 围栏 + 自身 5s SDK 超时 |
| `sync_turn` | 740-750 | **纯缓冲,零网络**:清洗后 append 进 `_session_turns` |
| `on_session_end` | 752-783 | 整会话一次 ingest(单条且 <20 字符的会话跳过,765-766),成功后清缓冲 |
| `on_session_switch` | 785-828 | 老会话缓冲 flush 成 `partial: not reset` 的 full_session ingest,再重置 |
| `on_memory_write` | 830-850 | 内建记忆写镜像,**每次一个后台线程**(先 join 上一个 2s) |
| `shutdown` | 852-882 | **只兜底崩溃路径**:缓冲非空才 flush(标 `partial: True`),join 三个线程各 5s |
| `get_tool_schemas` | 904-935 | 四工具,**同时注册 snake_case 与 kebab-case 两套名字**;多容器开启时注入 `container_tag` 参数 |
| `handle_tool_call` | 1031-1049 | 别名归一后分发 store/search/forget/profile |

`prefetch` 的注入频率控制:profile 部分只在首轮和每 N 轮(默认 50)出现,搜索结果每轮都有,`__init__.py:727-734 @ 863e313`:
```python
            profile = self._client.get_profile(query=query[:200])
            include_profile = self._turn_count <= 1 or (self._turn_count % self._profile_frequency == 0)
            context = _format_prefetch_context(
                static_facts=profile["static"] if include_profile else [],
                dynamic_facts=profile["dynamic"] if include_profile else [],
                search_results=profile["search_results"],
                max_results=self._max_recall_results,
            )
```

### 2.4 认证与配置

`SUPERMEMORY_API_KEY` 走 `get_secret`(`__init__.py:659`);配置文件 `$HERMES_HOME/supermemory.json`,所有值经 clamp/normalize(`__init__.py:113-157`)。setup 时有一个多路复用防泄漏细节——**multiplex 网关下绝不把 key 写进进程全局 environ**,`__init__.py:634-643 @ 863e313`:
```python
        # Single-profile convenience only: never write a profile's key into
        # the process-global environ under a multiplexed gateway — sibling
        # profiles' turns (and any subprocess spawned with env=os.environ)
        # would inherit it.
        if (
            api_key
            and not is_multiplex_active()
            and os.environ.get("SUPERMEMORY_API_KEY") != api_key
        ):
            os.environ["SUPERMEMORY_API_KEY"] = api_key
```

### 2.5 超时/重试/失败方向

超时默认 5s、硬 clamp 到 [0.5, 15],`__init__.py:142-145 @ 863e313`:
```python
    try:
        config["api_timeout"] = max(0.5, min(15.0, float(config.get("api_timeout", _DEFAULT_API_TIMEOUT))))
    except Exception:
        config["api_timeout"] = _DEFAULT_API_TIMEOUT
```
**重试:零**(SDK `max_retries=0`,见 2.1)。失败方向:自动路径全 fail-open——prefetch 异常 `logger.debug` 后返回 `""`(`__init__.py:736-738`),session ingest 异常 `logger.warning` 后继续(`__init__.py:777-780`),initialize 建客户端失败→`self._active = False` 整体静默停用(`__init__.py:699-702`);工具路径 `tool_error` 回模型(`__init__.py:957-958` 等)。

### 2.6 与 298s 事故的关系

Supermemory 的答案是**把写路径压缩到几乎不存在**:`sync_turn` 零网络(纯 append),全部网络写集中到会话边界的一次 ingest——而那次 ingest 发生在 `on_session_end` / `on_session_switch` / `shutdown`,都不在回复路径上。测试注释留下了演化痕迹,`tests/plugins/memory/test_supermemory_provider.py:115-120 @ 863e313`:
```python
def test_sync_turn_buffers_short_messages(provider):
    # Trivial filtering is no longer applied at sync time — every non-empty turn
    # is buffered and only the full session is written at session boundaries.
    provider.sync_turn("ok", "sure", session_id="session-1")
    assert provider._session_turns == [{"user": "ok", "assistant": "sure"}]
    assert provider._client.add_calls == []
```
(老版本曾在 sync 时逐轮过滤并写网络;现在连过滤都不做了,统一到边界。)读路径同步,但受 harness 8s 围栏 + 自身 5s(clamp 上限 15s < 围栏死区不成立,15>8,极端配置下 harness 围栏兜底)双保险。

### 2.7 README vs 代码对照(supermemory)

| # | README 断言 | 代码事实 | 判定 |
|---|---|---|---|
| 1 | `README.md:55` `capture_mode` 默认 `all`,"Skip tiny or trivial turns by default" | `_capture_mode` 被加载(`__init__.py:672`)但**全文件无任何使用点**;`_is_trivial_message`(276)与 `_MIN_CAPTURE_LENGTH = 10`(33)同为死代码;sync_turn(740-750)缓冲一切非空轮 | ▲ 死配置,README 描述的行为不存在 |
| 2 | `README.md:58` `api_timeout`"Timeout for SDK and ingest requests" | SDK 用原值(305),ingest 用 `timeout + 3`(417) | ▲ 细节不符(ingest 实为 +3s) |
| 3 | `README.md:49` base_url 优先级 config > env > 默认 | `_resolve_base_url`(82-91)完全一致 | ✓ |
| 4 | `README.md:74`"Kebab-case names are registered for the agent; snake_case aliases remain supported" | `with_kebab_aliases`(905-920)把两套名字**都**作为完整 schema 注册(kebab 是追加的 copy),`handle_tool_call` 把 kebab 归一回 snake(1034-1040) | ◇ 方向说反了(snake 是本体、kebab 是别名 copy),行为等价 |
| 5 | `README.md:85-89` `x-sm-source: hermes` + `metadata.sm_source` 是功能性路由非遥测 | `default_headers`(307)、`_merge_metadata`(310-318)注释同文 | ✓ |
| 6 | `README.md:129-132` 多容器:工具收 `container_tag`、必须在白名单、自动操作只用主容器 | `_resolve_tool_container_tag`(884-902)白名单校验;自动路径(prefetch/sync/ingest/on_memory_write)全部不传 tag→主容器 | ✓ |
| 7 | `README.md:96`"(or on /reset, branch, compression, or shutdown)" | on_session_switch(785)+ shutdown(852)均 flush;shutdown 注释自称 "Emergency fallback (crashes only)"(853) | ✓(README 把兜底路径也列为常规,轻微口径差) |

### 2.8 配套测试(行为规格)

文件:`tests/plugins/memory/test_supermemory_provider.py`(458 行)。精选:
- **`test_shutdown_joins_threads_and_flushes_buffer`**(161-206):sync_turn 后断言 `_sync_thread is None`(不再起线程),`on_memory_write` 起后台线程,shutdown 后三线程全清、缓冲以 `partial: True` 的 full_session 落一笔——完整刻画"缓冲 + 边界一次写"生命周期。
- **`test_on_session_end_ingests_clean_messages`**(123-141):system 角色被滤掉、metadata 结构、ingest 后缓冲清空(防 shutdown 重复写)。

### 2.9 重实现要点(supermemory 簇)

1. "缓冲 + 会话边界一次 ingest"是最简的写离线方案:回复路径零网络、零线程;代价是崩溃丢整段(仅 shutdown 兜底)、云端逐轮不可见。
2. 同步 `prefetch` 是合法选项——前提是 harness 有围栏且自身超时短(5s)、零重试;把重试留给上层是避免超时叠加的正确做法。
3. 注入内容打标签(`<supermemory-context>`),写回前剥掉自己的标签,防"记忆污染记忆"回流。
4. 云端记忆按来源打路由键(header + metadata 双写),用户侧可按 agent 过滤/清理。
5. `is_available` 只查配置不查依赖;SDK 惰装挪进客户端构造。
6. 多租户密钥永不进程全局 environ;工具入参的命名空间必须白名单校验。
7. 死配置(capture_mode)提醒:配置面每加一项都要有使用点测试,否则文档必然漂移。

---

## 3. RetainDB(`plugins/memory/retaindb/__init__.py`,804 行)

### 3.1 它是什么

**纯云 API(README:$20/月),无官方 SDK,`requests` 手写 REST 客户端。**

`plugins/memory/retaindb/__init__.py:43 @ 863e313`
```python
_DEFAULT_BASE_URL = "https://api.retaindb.com"
```
认证是**双头**:`Authorization: Bearer` 恒有,memory/context 路径额外带 `X-API-Key`,`__init__.py:211-220 @ 863e313`:
```python
    def _headers(self, path: str) -> dict:
        token = self.api_key.replace("Bearer ", "").strip()
        h = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-sdk-runtime": "hermes-plugin",
        }
        if path.startswith(("/v1/memory", "/v1/context")):
            h["X-API-Key"] = token
        return h
```

### 3.2 存储/检索形态

命名空间是 **project**(解析:`RETAINDB_PROJECT` env > config.yaml > `hermes-<profile目录名>` > `"default"`,`__init__.py:527-535`)。检索面最宽:`/v1/context/query`(综合上下文)、`/v1/memory/search`(语义搜索,`include_pending: True`,`__init__.py:262`)、profile、**dialectic**(`/v1/memory/profile/<uid>/ask`,LLM 合成的用户理解)、**agent self-model**(`/v1/memory/agent/<aid>/model`,人格+持久指令);还有一整套**共享文件库**(upload/list/read/ingest/delete,rdb:// URI)。写入:`/v1/memory`(单条)与 `/v1/memory/ingest/session`(逐轮 ingest)。API 兼容层:get_profile/add_memory/delete_memory 都是 try 新路由、except 落老路由(`__init__.py:265-287`)。

**initialize 还会把 `$HERMES_HOME/SOUL.md` 后台种子进 agent 身份**(`__init__.py:548-557`,`/seed` 端点,daemon 线程)。

### 3.3 ABC 映射

| ABC 方法 | 行号 | 行为要点 |
|---|---|---|
| `is_available` | 503-504 | 只查 `RETAINDB_API_KEY` |
| `initialize` | 515-557 | env→config.yaml→默认三级解析;建 `_WriteQueue`(SQLite);SOUL.md 种子线程 |
| `system_prompt_block` | 565-572 | 工具用法 |
| `queue_prefetch`(重写) | 576-591 | **三个并行后台线程**:context / dialectic / agent-model,先 join 旧线程 2s 防堆积 |
| `prefetch` | 631-657 | 纯消费三份缓存(锁内取出即清),零网络 |
| `sync_turn` | 661-673 | `_queue.enqueue(...)`,**先落 SQLite 再入内存队列** |
| `get_tool_schemas` | 677-683 | **10 个工具**(5 记忆 + 5 文件) |
| `handle_tool_call` | 685-691 | 统一 try/except 包 `_dispatch`,异常→`tool_error` |
| `on_memory_write` | 785-793 | 内建记忆镜像,**同步调用**(在 harness 的写 worker 上跑,失败 log debug) |
| `shutdown` | 795-799 | join 预取线程 3s、队列 sentinel + join 10s |
| `on_session_end` / `on_session_switch` | 未实现 | 无会话边界动作(逐轮已 ingest,无需 flush) |

`queue_prefetch` 的防堆积,`__init__.py:576-591 @ 863e313`:
```python
    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """Fire context + dialectic + agent model prefetches in background."""
        if not self._client:
            return
        # Wait for any still-running prefetch threads before spawning new ones.
        # Prevents thread accumulation if turns fire faster than prefetches complete.
        for t in self._prefetch_threads:
            t.join(timeout=2.0)
```
dialectic 的推理档位按 query 长度自适应(`__init__.py:622-629`:<120 low、<400 medium、否则 high)。

### 3.4 持久写队列(三家中唯一 crash-safe 的写路径)

`__init__.py:356-371 @ 863e313`:
```python
class _WriteQueue:
    """SQLite-backed async write queue. Survives crashes — pending rows replay on startup."""

    def __init__(self, client: _Client, db_path: Path):
        ...
        self._init_db()
        self._thread.start()
        # Replay any rows left from a previous crash
        for row_id, user_id, session_id, msgs_json in self._pending_rows():
            self._q.put((row_id, user_id, session_id, json.loads(msgs_json)))
```
enqueue 先 INSERT 提交再入内存队列(`__init__.py:395-404`);发送成功才 DELETE 行,失败 UPDATE `last_error` 并留行等下次进程重放,`__init__.py:406-417 @ 863e313`:
```python
    def _flush_row(self, row_id: int, user_id: str, session_id: str, messages: list) -> None:
        try:
            self._client.ingest_session(user_id, session_id, messages)
            conn = self._get_conn()
            conn.execute("DELETE FROM pending WHERE id = ?", (row_id,))
            conn.commit()
        except Exception as exc:
            logger.warning("RetainDB ingest failed (will retry): %s", exc)
            conn = self._get_conn()
            conn.execute("UPDATE pending SET last_error = ? WHERE id = ?", (str(exc), row_id))
            conn.commit()
            time.sleep(2)
```
语义:**at-least-once**(失败行本进程不重试、下次启动重放;重放上限 200 行,`__init__.py:393`)。SQLite 连接按线程缓存(`__init__.py:373-380`)。

### 3.5 超时/重试/失败方向

统一入口默认 8s(恰好等于 harness 围栏值),逐端点覆盖,`__init__.py:222 @ 863e313`:
```python
    def request(self, method: str, path: str, *, params=None, json_body=None, timeout: float = 8.0) -> Any:
```
覆盖表(实测):add_memory 5.0(276/281)、delete 5.0(285/287)、ingest_session 15.0(289)、ask_user 8.0(298)、get_agent_model 4.0(301)、seed 20.0(306)、文件 upload/read 30(319/336)、ingest_file 60.0(346)、delete_file 5.0(349)。**无 HTTP 层重试**(单发);"重试"只存在于持久队列的跨进程重放。失败方向:预取三线程各自 `logger.debug` 吞掉(`__init__.py:600-620`)、镜像写 debug 吞掉(792-793)、队列写 warning 留行;工具路径 `tool_error`(690-691)。fail-open。

文件上传有一道 harness 安全闸:`raise_if_read_blocked` 拒读凭据库等敏感路径(`__init__.py:739-742`)。

### 3.6 与 298s 事故的关系

三家中最强的写路径答案:**write-behind + 落盘**。`sync_turn` 的成本 = 一次本地 SQLite INSERT(毫秒级),网络在 `retaindb-writer` 线程;进程崩了数据还在,下次进程重放。读路径与 hindsight 同构(重写 `queue_prefetch`,`prefetch` 零网络),且预取线程 join 上限 2s 自我防堆积。

### 3.7 README vs 代码对照(retaindb)

| # | README 断言 | 代码事实 | 判定 |
|---|---|---|---|
| 1 | `README.md:24`"All config via environment variables in `.env`" | `_load_retaindb_config`(47-63)还读 config.yaml 的 `memory.retaindb` 块(Dashboard 写入),测试 `test_retaindb_provider.py:111-125` 点名 #68209 | ▲ README 落后于代码 |
| 2 | `README.md:33-40` 工具表 5 个 | `get_tool_schemas`(677-683)注册 **10 个**(另有 upload/list/read/ingest/delete 文件工具,schema 136-198) | ▲ README 漏掉整个文件工具族 |
| 3 | `README.md:3`"7 memory types" | REMEMBER_SCHEMA enum 只有 6 个:`["factual", "preference", "goal", "instruction", "event", "opinion"]`(113-117) | ▲ 数字对不上(7 vs 6) |
| 4 | `README.md:3`"hybrid search (Vector + BM25 + Reranking)" | 纯服务端断言,插件只 POST `/v1/memory/search`(255-263),仓内不可验证 | ◇ 存疑不证伪 |
| 5 | `README.md:30` `RETAINDB_PROJECT` 默认"auto (profile-scoped)" | 529-535:显式值 > `hermes-<profile>`(hermes_home 目录名非 `.hermes` 时)> `"default"` | ✓(README 简化但方向对) |
| 6 | 模块 docstring(1-19)列 durable SQLite queue、dialectic、SOUL.md 种子、文件库 | README 一概未提 | ▲ README 极薄,docstring 才是真地图 |

### 3.8 配套测试(行为规格)

文件:`tests/plugins/memory/test_retaindb_provider.py`(188 行)。精选:
- **`test_upload_file_rejects_hermes_credential_store`**(10-24):把 `$HERMES_HOME/auth.json` 传给 upload 工具必须返回含 "credential store" 的 error 且 `upload_file` 未被调用——文件外传前必须过 harness 读闸的可执行定义。
- **`test_initialize_combines_scoped_secret_with_dashboard_config`**(144-176):multiplex 下 scoped secret(`RETAINDB_API_KEY=scoped-key`)必须压过 env 里别的 profile 的 key,同时 config.yaml 的非密配置照常生效——密钥走 secret_scope、非密走 config 的双通道规格。

### 3.9 重实现要点(retaindb 簇)

1. 写路径要 crash-safe 就用 **SQLite write-behind**:INSERT-commit-入队;成功 DELETE、失败留行 + 记 last_error;启动重放(带上限)。语义定为 at-least-once 并让服务端按 session_id 幂等。
2. 手写 REST 客户端时:超时逐端点定(交互式短、批处理长),错误统一抛带 status+message 的异常,由每个消费面自己决定吞或报。
3. 多路由兼容(新老 API try/except)让插件跨服务端版本存活,代价是真错误也会被二次请求掩盖一拍——只适合幂等 GET/POST。
4. 预取可以多路并行(context/synthesis/self-model 三线程),但要 join 旧线程防堆积;缓存取出即清,防陈旧注入。
5. 把 agent 的自我文件(SOUL.md)种子进记忆服务是低成本高杠杆的初始化动作,放后台线程、失败无声。
6. 任何"把本地文件传出去"的工具必须复用 harness 的文件安全闸,不能自己另写一套。

---

## 4. 横向对比:同一 ABC 下的三种集成风格

| 维度 | hindsight | supermemory | retaindb |
|---|---|---|---|
| 形态 | 云 / 本地 daemon / 外接三合一 | 云(可自托管 URL) | 云 |
| 客户端 | 官方 async SDK + 共享事件循环 | 官方 sync SDK + 一处 urllib | requests 手写 REST |
| 写路径 | 内存队列 + 单写者线程(逐轮,增量 append) | 内存缓冲 + 会话边界一次 ingest | SQLite 持久队列 + 写者线程(逐轮) |
| 写崩溃丢失窗口 | 队列内未发轮次 | 整个未 flush 会话 | ≈0(落盘重放) |
| 读路径 | 重写 queue_prefetch(后台)+ prefetch 消费缓存(join 3s) | 同步 prefetch 直连网络 | 重写 queue_prefetch(3 并行线程)+ prefetch 消费缓存 |
| 自身超时 | 120s/调用(可配),/version 5s | 5s(clamp 0.5–15) | 8s 默认,4–60s 按端点 |
| 重试 | embedded 断连重连一次 | 0(max_retries=0) | HTTP 0;队列跨进程重放 |
| read-after-write | 显式双栅栏 + drop 语义 | 不需要(会话末才写) | `include_pending: True` 交给服务端 |
| 失败方向 | 自动路径 fail-open;工具 fail-visible | 同左 | 同左 |
| 命名空间 | bank_id(+模板 {profile}/{user}/…) | container_tag(+{identity},多容器白名单) | project(+profile 自动派生) |
| 会话边界钩子 | on_session_switch(flush 老 doc) | on_session_end + switch + shutdown 三点 flush | 无(逐轮已写) |

**取舍读法(为自造 harness 提炼):**

1. **写离线有三档,按"每轮写的价值 × 崩溃容忍度"选。** 逐轮价值高(服务端逐轮抽取、跨进程可见)→ 队列;能接受边界才可见 → 缓冲一次写(最简,supermemory);写不能丢 → 落盘 write-behind(retaindb)。hindsight 选队列还叠了 append 增量与读后写栅栏,是因为它逐轮写 + 异步受理 + 下一轮就要读——三个条件同时成立才需要那套复杂度。
2. **读路径的分界是"谁负责后台化"。** provider 重写 `queue_prefetch` 自己后台化(hindsight/retaindb),`prefetch` 退化为零网络的缓存消费,harness 8s 围栏形同保险丝;不重写(supermemory)则 `prefetch` 直连网络,harness 围栏是唯一防线,此时自身超时必须短且零重试,否则叠加超过围栏就每轮白等 8s。
3. **超时数值应属地化**:围栏(8s)管"回复等多久",provider 超时管"后台线程最多陪服务端耗多久"——两者量级可以不同(hindsight 120s 合法,因为它只烧写者/预取线程)。
4. **失败方向全行业一致**:记忆是增强不是依赖,自动路径永远 fail-open(log 后继续),工具路径 fail-visible(让模型知道并可复述失败)。三家无一例外。
5. **README 是作者自绘地图,漂移方向一致**:三家 README 都**落后**于代码(少配置项、少工具、死配置、惰性元数据),没有一处代码落后于 README——印证"以代码为准"的项目纪律,也说明配置面/工具面每次扩张都应带 README diff。

---

## 附:本轮覆盖与测试清单

- 精读(L1):`plugins/memory/hindsight/__init__.py`(2232)、`plugins/memory/hindsight/config_schema.py`(76)、`plugins/memory/hindsight/README.md`(147)、`plugins/memory/supermemory/__init__.py`(1053)、`plugins/memory/supermemory/README.md`(138)、`plugins/memory/retaindb/__init__.py`(804)、`plugins/memory/retaindb/README.md`(40);顺带核对 `plugin.yaml` 三份与 `agent/memory_manager.py:47,548-596,638-662`、`agent/async_utils.py:34-63`(佐证,不计层)。
- 行为规格参照(LT):`tests/plugins/memory/test_hindsight_provider.py`(1375)、`test_hindsight_env_perms.py`(80)、`test_hindsight_config_schema.py`(51)、`test_supermemory_provider.py`(458)、`test_retaindb_provider.py`(188);harness 侧 298s 规格 `tests/agent/test_memory_async_sync.py`。
- 遗留待后续轮:同目录 byterover / holographic / honcho / mem0 / openviking 五家与 `plugins/memory/__init__.py`、`config_schema.py`、`query_rewrite.py`(按台账计划轮次推进)。