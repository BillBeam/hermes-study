# R6 底稿 · mem0 + holographic 记忆后端

> L1 机制精读底稿。对象:`plugins/memory/mem0/`(4 个 py + README,共 2219 行)与 `plugins/memory/holographic/`(4 个 py + README,共 2100 行)。基线 commit `863e313`(全称 863e31318553cda8ad61df681d08175364d4164b),hermes-agent 只读。所有行号在基线源码上实测。
>
> 承接上一轮定案:MemoryProvider ABC 契约(`agent/memory_provider.py:81-357 @ 863e313`,abstract:name/is_available/initialize/get_tool_schemas;带默认实现:system_prompt_block/prefetch/queue_prefetch/sync_turn/handle_tool_call/shutdown;可选钩子:on_turn_start/on_session_end/on_session_switch/on_pre_compress/on_delegation/on_memory_write/get_config_schema/save_config/backup_paths);MemoryManager 一次只挂一个外部 provider。本底稿把两个后端逐机制对上这份契约。

---

## 0. 文件清单与定位

| 文件 | 行数 | 定位 |
|---|---|---|
| `plugins/memory/mem0/__init__.py` | 628 | Provider 主体:配置/路由/熔断/prefetch/sync/四工具 |
| `plugins/memory/mem0/_backend.py` | 315 | 三后端(云 SDK / 自建服务器 HTTP / OSS 进程内)统一接口 |
| `plugins/memory/mem0/_oss_providers.py` | 88 | OSS 形态的 LLM/嵌入/向量库供应商注册表 + 校验 |
| `plugins/memory/mem0/_setup.py` | 1001 | `hermes memory setup` 的 post_setup 向导:交互/flag 双模式、依赖安装、Docker/Ollama 自动拉起、连通性检查 |
| `plugins/memory/mem0/README.md` | 187 | 作者地图(见 §1.8 对照) |
| `plugins/memory/holographic/__init__.py` | 462 | Provider 主体:两工具 9 动作、auto_extract、镜像写 |
| `plugins/memory/holographic/holographic.py` | 290 | HRR 相位向量数学:atom/bind/unbind/bundle/similarity/序列化/SNR |
| `plugins/memory/holographic/store.py` | 644 | SQLite 事实库:schema、进程级共享连接、实体抽取、trust、HRR 向量落盘 |
| `plugins/memory/holographic/retrieval.py` | 668 | 五种召回:search/probe/related/reason/contradict |
| `plugins/memory/holographic/README.md` | 36 | 作者地图(见 §2.6 对照) |

两个插件的 plugin.yaml:

`plugins/memory/mem0/plugin.yaml @ 863e313`(实测 cat 输出):
```yaml
name: mem0
version: 1.3.0
description: "Mem0 — server-side LLM fact extraction with semantic search, automatic deduplication, and opt-in reranking (platform mode)."
pip_dependencies:
  - mem0ai>=2.0.10,<3
```

`plugins/memory/holographic/plugin.yaml @ 863e313`:
```yaml
name: holographic
version: 0.1.0
description: "Holographic memory — local SQLite fact store with FTS5 search, trust scoring, and HRR-based compositional retrieval."
hooks:
  - on_session_end
```

---

## 1. mem0:把记忆外包给 Mem0(云 / 自建服务器 / 进程内 OSS)

### 1.1 三形态与路由:一个 `mode` + 一个 `host`,优先级 oss > host > platform

mem0 插件不是"云 vs OSS"两形态,而是**三形态**:

1. **platform**:Mem0 官方云(api.mem0.ai),走 `mem0.MemoryClient` SDK;
2. **selfhosted(host 模式)**:你自己 Docker 跑的 Mem0 FastAPI 服务器,插件直接发 HTTP;
3. **oss**:`mem0.Memory` SDK 在 hermes 进程内运行,LLM/嵌入/向量库全部自备。

路由决策在 `_create_backend`,`plugins/memory/mem0/__init__.py:280-288 @ 863e313`:

```python
        try:
            if self._mode == "oss":
                from ._backend import OSSBackend
                return OSSBackend(self._config.get("oss", {}))
            if self._host:
                from ._backend import SelfHostedBackend
                return SelfHostedBackend(self._api_key, self._host)
            from ._backend import PlatformBackend
            return PlatformBackend(self._api_key)
```

即:`mode=="oss"` 绝对优先;否则只要 `host` 非空(来自 mem0.json 的 `host` 键或 `MEM0_HOST` 环境变量)就走自建服务器;都没有才落到云。系统提示里的模式标签刻意镜像同一优先级,`plugins/memory/mem0/__init__.py:385-395 @ 863e313`:

```python
    def system_prompt_block(self) -> str:
        # Mirror the precedence in _create_backend (oss > host > platform) so
        # the label always names the backend that actually runs. Checking
        # ``host`` first here would mislabel an ``oss``+``host`` config as
        # self-hosted HTTP even though OSS wins the routing.
        if self._mode == "oss":
            mode_label = "OSS (self-hosted)"
        elif self._host:
            mode_label = "self-hosted (HTTP API)"
        else:
            mode_label = "platform (cloud API)"
```

配置的来源与分层:环境变量给默认值,`$HERMES_HOME/mem0.json` 逐键覆盖(避免"json 存在但缺 api_key 导致 .env 里的 key 被吞"的静默失败),`plugins/memory/mem0/__init__.py:78-110 @ 863e313`:

```python
def _load_config() -> dict:
    """Load config from env vars, with $HERMES_HOME/mem0.json overrides.

    Environment variables provide defaults; mem0.json (if present) overrides
    individual keys.  This avoids a silent failure when the JSON file exists
    but is missing fields like ``api_key`` that the user set in ``.env``.
    """
```
其中 secret(MEM0_API_KEY)走 `get_secret`(`__init__.py:89`),非 secret 走 `os.environ`;json 覆盖时过滤 `None`/空串(`__init__.py:105-106`)。

**切换形态 = 改 mem0.json 的 mode/host 两个键**(setup 向导替你改)。切换有一个被显式处理过的坑:selfhosted 存的是 `mode: "platform"` + `host` 非空(`plugins/memory/mem0/_setup.py:415 @ 863e313`:`provider_config["mode"] = "platform"  # routing: oss > host > platform; host wins`),所以从 selfhosted 切回真 platform 时必须清 host——而且必须写空串而不是删键,因为 save_config 是 merge 写,`plugins/memory/mem0/_setup.py:306-313 @ 863e313`:

```python
    provider_config["mode"] = "platform"
    # Clear any stale self-hosted host: routing checks ``host`` before platform
    # (see _create_backend), so leaving it would silently keep routing to the
    # self-hosted server even though the user just chose platform mode. Set it
    # to "" rather than pop() — save_config merges into the existing mem0.json
    # (existing.update), so a popped key would survive; an empty value overwrites
    # it and reads as falsy at routing time.
    provider_config["host"] = ""
```
json 清不掉环境变量,所以紧接着对 `MEM0_HOST` 只能打印警告(`_setup.py:318-324`)。

`is_available` 按形态分叉,`plugins/memory/mem0/__init__.py:227-234 @ 863e313`:

```python
    def is_available(self) -> bool:
        cfg = _load_config()
        mode = cfg.get("mode", "platform")
        if mode == "oss":
            return bool(cfg.get("oss", {}).get("vector_store"))
        # Platform needs an api_key; self-hosted needs a host (api_key optional
        # when the server runs with AUTH_DISABLED).
        return bool(cfg.get("api_key") or cfg.get("host"))
```

**重实现要点(1.1)**
- 多形态后端用"单一优先级链 + 单一配置文件"路由,并让**所有对用户可见的标签走同一条优先级链**(否则提示词撒谎);
- merge 型配置写回时,"删除一个键"必须写空值而非 pop;
- 环境变量能越过文件配置时,切换路径上要主动检测并警告;
- is_available 按形态检查各自的最小必要配置。

### 1.2 __init__.py 主体:身份解析、熔断器、prefetch 双入口、离线 sync、四工具

**user_id 三级解析**。目标:操作员配置的 canonical id > 网关原生 id(Telegram 数字 id、Discord snowflake)> 硬编码兜底;且历史向导写下的占位符 `"hermes-user"` 视为未配置,`plugins/memory/mem0/__init__.py:57-63、342-356 @ 863e313`:

```python
# Sentinel returned when neither MEM0_USER_ID nor a gateway-native id is
# available. Treated as "no operator-configured user_id" by initialize() so
# that legacy mem0.json files written by the setup wizard (which historically
# wrote this exact placeholder) still allow gateway-native ids to flow
# through instead of silently overriding them with the placeholder.
_DEFAULT_USER_ID = "hermes-user"
```
```python
        configured = self._config.get("user_id")
        if configured == _DEFAULT_USER_ID:
            configured = None
        self._user_id = configured or kwargs.get("user_id") or _DEFAULT_USER_ID
```
读写不对称:**读只按 user_id 过滤**(跨网关、跨 agent 召回),**写附带 agent_id 和 channel 元数据**(供 dashboard 按渠道筛选),`plugins/memory/mem0/__init__.py:372-383 @ 863e313`:

```python
    def _read_filters(self) -> Dict[str, Any]:
        # Scoped to user_id only — by design — so recall surfaces memories
        # written from any gateway/agent under this principal. Writes attach
...
        return {"user_id": self._user_id}

    def _write_metadata(self) -> Dict[str, Any]:
        # Tag every write with the gateway channel so the dashboard can offer
        # per-channel filtered views without coupling identity to the channel.
        return {"channel": self._channel} if self._channel else {}
```

**熔断器(circuit breaker)**。5 连败后停 API 调用 120 秒,`plugins/memory/mem0/__init__.py:51-54 @ 863e313`:

```python
_BREAKER_THRESHOLD = 5
_BREAKER_COOLDOWN_SECS = 120
_PREFETCH_WAIT_SECS = 3
```
开合逻辑 `_is_breaker_open`(`plugins/memory/mem0/__init__.py:294-302`):连败数达阈值且未过冷却期即"开";过期后归零自动闭合。关键细节:**客户端错误不计入熔断**——404/not found/bad UUID 是用户传错 ID,不代表服务不可用,`plugins/memory/mem0/__init__.py:65-71 @ 863e313`:

```python
def _is_client_error(exc: Exception) -> bool:
    """True for user-caused errors (bad ID, not found) that should NOT trip circuit breaker."""
    etype = type(exc).__name__
    if etype in _CLIENT_ERROR_TYPES:
        return True
    err_str = str(exc).lower()
    return "404" in err_str or "not found" in err_str or "valid uuid" in err_str
```
在 mem0_search 的 except 里体现为 `if not _is_client_error(e): self._record_failure()`(`__init__.py:552-554`)。

**prefetch 双入口 + 3 秒热路径等待**。`on_turn_start` 在 turn 开始就后台起线程搜(`plugins/memory/mem0/__init__.py:414-415`);harness 稍后调 `prefetch(query)` 时,先消费缓存,没有就现起线程并**只等 3 秒**,等不到返回空串——注入放弃,mem0_search 工具兜底,`plugins/memory/mem0/__init__.py:463-477 @ 863e313`:

```python
    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Recall memories for the CURRENT question with a short hot-path wait."""
        cached = self._consume_prefetch_result(query)
        if cached is not None:
            return cached
        self._start_prefetch(query)
        with self._prefetch_lock:
            thread = self._prefetch_thread if self._prefetch_query == query else None
        if thread:
            thread.join(timeout=_PREFETCH_WAIT_SECS)
        cached = self._consume_prefetch_result(query)
        if cached is not None:
            return cached
        # Slow backend: skip injection; mem0_search tool remains the backstop.
        return ""
```
`_start_prefetch` 用 `_prefetch_query == query` 去重(同一问题不重复搜,`__init__.py:430-435`),结果格式化为 `"## Mem0 Memory\n- fact1\n- fact2"`(`__init__.py:446-448`)。注意:harness 侧 MemoryManager 的 8 秒围栏是外层保险,mem0 自带的 3 秒是更紧的内层预算。

**sync_turn:每 turn 整段对话交给服务端做事实抽取,单线程离线**。`plugins/memory/mem0/__init__.py:493-526 @ 863e313`:

```python
                backend.add(
                    messages,
                    user_id=self._user_id,
                    agent_id=self._agent_id,
                    infer=True,
                    metadata=self._write_metadata(),
                )
```
`infer=True` 是关键:让 Mem0 服务端 LLM 从 user/assistant 两条消息里抽事实、去重、合并。写并发控制:新 sync 前 join 旧线程最多 5 秒,还活着就**跳过本轮**以免重复摄入(`plugins/memory/mem0/__init__.py:505-510`):

```python
        with self._sync_lock:
            if self._sync_thread and self._sync_thread.is_alive():
                self._sync_thread.join(timeout=5.0)
            # If still alive after timeout, skip to avoid duplicate ingestion.
            if self._sync_thread and self._sync_thread.is_alive():
                return
```

**四个工具**:`mem0_search / mem0_add / mem0_update / mem0_delete`(schema 于 `plugins/memory/mem0/__init__.py:117-187`,`get_tool_schemas` 于 514-515)。与 sync_turn 相对,`mem0_add` 走 `infer=False` **逐字存**,不做抽取(`plugins/memory/mem0/__init__.py:562-568`);回执文案区分同步/异步语义,`plugins/memory/mem0/__init__.py:571-573 @ 863e313`:

```python
                # Cloud add is async (server-side extraction); OSS and self-hosted store synchronously.
                msg = "Fact stored." if (self._mode == "oss" or self._host) else "Fact queued for storage."
```
`mem0_search` 参数钳制 `top_k` 到 [1,50](`__init__.py:539`),`rerank` 默认取 mem0.json 里持久化的偏好、per-call 参数覆盖(`__init__.py:540-544`,默认值解析在 initialize 的 362-364)。

**懒安装**:`_create_backend` 先 `tools.lazy_deps.ensure("memory.mem0", prompt=False)`(`__init__.py:274-275`)按需装 mem0ai SDK,失败则放行让后端 import 报出规范错误。

**shutdown 双通道**:`initialize` 里注册 atexit(`__init__.py:368-370`,只注册一次);`shutdown()` join 两个工作线程各 5 秒再关后端(`__init__.py:619-623`)。

**重实现要点(1.2)**
- 外部记忆服务必须配熔断器,且**区分服务故障与用户输入错误**,后者不计连败;
- prefetch 要"后台预热 + 热路径限时等待 + 超时放弃注入、工具兜底"三件套,内层预算(3s)应紧于 harness 围栏(8s);
- 自动摄入(infer=True 的 sync_turn)与显式存储(infer=False 的 add 工具)是两条语义不同的写路径,应分开;
- 写线程串行化 + 超时跳过,宁可丢一轮摄入也不重复摄入;
- user_id 解析要处理"历史向导写死的占位默认值"这类兼容包袱——把占位符当 None。

### 1.3 _backend.py:一个 4 方法 ABC,三个实现

内部 ABC `Mem0Backend`:`search/add/update/delete` 四个抽象方法 + 可选 `close`(`_backend.py:9-37 @ 863e313`)。`_unwrap_results` 统一"dict 带 results 键 / 裸 list"两种响应形状(`_backend.py:40-46`)。

**PlatformBackend**(`_backend.py:49-80`):`mem0.MemoryClient(api_key=...)` 的薄封装,search 直传 `filters/top_k/rerank`。

**SelfHostedBackend**(`plugins/memory/mem0/_backend.py:83-153`):为什么不能复用官方 SDK,docstring 说得很清楚,`plugins/memory/mem0/_backend.py:84-92 @ 863e313`:

```python
    """Direct HTTP backend for a self-hosted Mem0 server (the FastAPI ``server/``).

    mem0.MemoryClient can't be reused for self-hosted: it is hardwired to the
    cloud API — ``Authorization: Token`` auth and a ``GET /v1/ping/`` validation
    call in ``__init__`` that the self-hosted server does not expose (it would
    404 before any real request). This client talks to that server directly,
    using its actual contract: ``X-API-Key`` auth and the ``/memories`` /
    ``/search`` routes.
    """
```
实现细节:`X-API-Key` 头(AUTH_DISABLED 的服务器可不带,`_backend.py:98-99`);httpx.Client,`timeout=30.0`,**连接层重试 2 次**——单个丢包不该计入 provider 熔断,transport 可注入供测试 mock(`_backend.py:100-108`);rerank 被自建服务器忽略、user_id 放 filters(顶层已废弃)(`_backend.py:115-119`)。

**OSSBackend**(`_backend.py:156-315`):把 mem0.json 的 `oss` 块翻译成 `mem0.Memory.from_config` 的配置。三个值得记的机制:

1. **legacy `api_base` 键归一化**:老配置里的 `api_base` 被 pop 出来映射到各 provider 的规范键(`openai_base_url`/`ollama_base_url`),`_backend.py:163-178`;
2. **嵌入维度自动推断**:embedder 配置没写 `embedding_dims` 时按模型名查 `KNOWN_DIMS`,并塞进向量库配置的 `embedding_model_dims`(`_backend.py:186-193`);
3. **维度变更时自动重建集合**:`_recreate_collection_if_dims_changed`(`_backend.py:208-270`)——换嵌入模型导致维度变化时,qdrant 分支读 collection 的向量 size(区分 named/unnamed 两种返回形状,`_backend.py:228-233`)不等则 `delete_collection`;pgvector 分支查 `pg_attribute.atttypmod` 不等则 `DROP TABLE`(`_backend.py:255-264`)。整段 best-effort,全部裹 `except Exception: pass`。

OSS 的 `close()` 逐层礼貌关闭:posthog 遥测、Memory 自身、vector_store、底层 client(`_backend.py:298-315`)。

**重实现要点(1.3)**
- 同一服务的"云 SDK"经常硬编码云契约(auth 头、ping 端点),自建形态宁可手写一个 100 行 HTTP client 也别硬掰 SDK;
- 传输层瞬断重试要放在**熔断计数之下**(连接 retries=2),否则网络抖动会误开熔断;
- 嵌入模型可换的系统必须处理"维度漂移":存维度、比对、不等即重建,否则向量库报错或静默错配;
- 老配置键做入口处归一化,而不是散落在各处兼容。

### 1.4 _oss_providers.py:声明式供应商注册表

三张表 + 一张维度表 + 一个校验函数。LLM/Embedder 各支持 openai、ollama;向量库支持 qdrant(默认本地路径 `~/.hermes/mem0_qdrant`)、pgvector。每条记录声明 `needs_key/env_var/default_model/default_url/base_url_key/pip_dep/dims`,`plugins/memory/mem0/_oss_providers.py:46-64 @ 863e313`:

```python
VECTOR_PROVIDERS: dict[str, dict[str, Any]] = {
    "qdrant": {
        "label": "Qdrant",
        "default_config": {"path": os.path.expanduser("~/.hermes/mem0_qdrant")},
        "pip_dep": "qdrant-client",
    },
    "pgvector": {
        "label": "PGVector",
        "default_config": {"host": "localhost", "port": 5432, "user": os.getenv("USER", "postgres"), "dbname": "postgres"},
        "pip_dep": "psycopg2-binary",
    },
}

KNOWN_DIMS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "nomic-embed-text": 768,
}
```
`validate_oss_config`(67-88)检查三节齐全、provider 在注册表内、pgvector 必须有 user。setup 向导、OSSBackend、懒安装三处都吃这一张表——单一事实源。

**重实现要点(1.4)**:可插拔供应商用"数据表 + 泛型代码"而非 if/else 分支;pip 依赖、密钥环境变量名、默认模型、维度全部进表,UI 与后端共享。

### 1.5 _setup.py 的 1001 行装什么:一个会自己动手的安装向导

回答任务问题:**既是交互式配置,也做依赖安装,还负责把外部服务(Docker pgvector、Ollama)拉起来**。入口是 ABC 可选钩子 `post_setup`(`__init__.py:263-265` 转发到这里),由 `hermes memory setup` 框架调用(`hermes_cli/memory_setup.py:325-329 @ 863e313`:"If the provider has a post_setup hook, delegate entirely to it.")。结构分六块:

1. **flag 解析(64-125)**:手写 while 循环解析 20 个 `--oss-*` / `--mode` / `--api-key` / `--dry-run` 等 flag,不用 argparse——因为它接的是 `hermes memory setup mem0 ...` 之后的残余 argv。这让**agent 自己也能非交互地配置记忆**(README 称 "Agent-Driven Setup")。
2. **三模式路由(964-1001)**:`--mode oss` → `_setup_oss`;`--mode selfhosted|self-hosted` → `_setup_selfhosted`;`--mode platform` → `_setup_platform`;无 flag → curses 单选(三项,`_setup.py:989-993`)。入口先 `_check_min_dep_version()`(945-961)提示 mem0ai 过旧。
3. **platform 流(234-342)**:按 schema 逐字段问(choices 走 curses、secret 走 getpass 掩码显示尾 4 位),secret 写 `.env`、行为配置写 mem0.json、`config["memory"]["provider"]="mem0"` 写 config.yaml,并做 §1.1 说的 host 清空 + MEM0_HOST 警告。
4. **selfhosted 流(361-438)**:问 URL / 可选 API key / user_id / agent_id,存 `mode: "platform"` + host(见 §1.1),`_check_selfhosted_server`(345-358)GET `/docs` 做 best-effort 可达性检查——**任何 HTTP 状态码(含 401/404)都算"有东西在听"**。
5. **OSS 流(441-852)**:flag 版(451-494)直接 build+validate+落盘;交互版(734-852)三个 curses 选择器(LLM/Embedder/向量库)加上两台"自动装机器":
   - `_ensure_ollama`(614-661):找 ollama 二进制→没跑就 `ollama serve` 后台拉起→逐个 `ollama pull` 缺失模型(超时 600s);
   - `_ensure_pgvector`(523-564)+`_start_pgvector_docker`(567-611):TCP 探测不通→发现停掉的容器 `hermes-pgvector` 就 docker start→否则征求同意后 `docker pull pgvector/pgvector:pg17` + `docker run -d -p 5432:5432`,再 `_ensure_pgvector_extension`(677-700)`CREATE EXTENSION IF NOT EXISTS vector`;
   - 依赖安装 `_install_provider_deps`(855-881):从注册表收集 pip_dep,走 `tools.lazy_deps.install_specs`(环境感知,sealed Docker venv 重定向到持久卷,NS-605),完了 `importlib.invalidate_caches()`;
   - `_run_connectivity_checks`(915-942):qdrant 路径可写/URL healthz、pgvector TCP、Ollama /api/tags,全部只警告不阻断。
6. **.env 写入的编码防御(191-218)**:读取用 `utf-8-sig`(BOM 容忍),写回 UTF-8,注释指明 Windows 落地 bug:`plugins/memory/mem0/_setup.py:196-203 @ 863e313`:

```python
        # Read as UTF-8 (BOM-tolerant), matching the canonical .env readers in
        # hermes_cli/config.py. read_text() with no encoding falls back to the
        # system locale (cp1252/GBK on Windows): it mangles or crashes on
        # non-ASCII values while copying existing lines through, and a BOM'd
        # first line would fail the key match and get duplicated.
```

另一处细节:embedder 与 LLM 同为 openai 时**自动复用 LLM 的 key**(`build_oss_config`,`_setup.py:183-186`;交互版 763-765)。`--dry-run` 全程只打印、跑连通性检查、不写文件(299-304、407-413、464-473)。

**内部矛盾(定案 ▲)**:`_check_min_dep_version` 注释称"minimum version from plugin.yaml"但硬编码 `(2, 0, 7)`,而 plugin.yaml 声明 `mem0ai>=2.0.10,<3`,`plugins/memory/mem0/_setup.py:952-953 @ 863e313`:

```python
        installed_parts = tuple(int(x) for x in installed_ver.split(".")[:3])
        required_parts = (2, 0, 7)
```
以 plugin.yaml 为准(安装约束),_setup 的检查只是提示,阈值滞后了,属无害漂移但要记录。

**重实现要点(1.5)**
- setup 向导做成"交互 + flag 全等价"双通道,agent 可以自己配置自己;
- 一切外部依赖检查 best-effort:警告不阻断,配置照存(服务可以晚点起来);
- 会主动"装机"(docker run、ollama pull、pip install)的向导每一步都要有超时和征求同意;
- `.env` 读写显式 UTF-8(-sig),不信任平台默认编码;
- `--dry-run` 是 agent 驱动配置的安全阀。

### 1.6 ABC 映射表(mem0)

| ABC 成员 | mem0 实现 | 位置(@ 863e313) |
|---|---|---|
| name | `"mem0"` | `__init__.py:223-225` |
| is_available | 按形态查 api_key/host/oss.vector_store | 227-234 |
| initialize | 加载配置、三级 user_id、rerank 默认、建后端、注册 atexit | 337-370 |
| system_prompt_block | 模式标签 + 强搜索指令(多跳多搜) | 385-412 |
| prefetch | 缓存消费 + 3s 限时等待,超时返 "" | 463-477 |
| queue_prefetch | 未覆写(ABC 默认 no-op;测试断言不发搜索,test_mem0_v3.py:234-240) | — |
| sync_turn | 后台线程 add(infer=True),串行防重 | 479-512 |
| get_tool_schemas | 4 工具 | 514-515 |
| handle_tool_call | search/add/update/delete + 熔断/未初始化护栏 | 517-609 |
| shutdown | join 线程 + close 后端;另有 atexit 兜底 | 619-623 / 368-370 |
| on_turn_start(钩子) | 提前起 prefetch 线程 | 414-415 |
| get_config_schema / save_config(钩子) | schema 5 字段 / merge 写 mem0.json(0o600) | 251-261 / 236-249 |
| post_setup(钩子) | 转发 `_setup.post_setup` | 263-265 |

### 1.7 失败方向:一切读写 fail-open,只有工具调用把错误说给模型听

- **prefetch 失败/超时** → 返回 `""`,不注入,不阻塞 turn(`__init__.py:476-477`);
- **sync_turn 失败** → 记入熔断、log warning,事实丢失但对话不受影响(`__init__.py:501-503`);
- **后端建不起来** → `_backend=None`,记 `_init_error`,工具调用时把错误 + OSS 排障提示(查向量库是否在跑)返回给模型(`__init__.py:517-525`);
- **熔断开** → 工具直接返回 "Mem0 temporarily unavailable ... Will retry automatically."(`__init__.py:527-532`);
- **OSS 错误信息增强**:`_format_error` 识别 connection/refused/timeout 字样,附上"check that qdrant is running"类提示(`__init__.py:304-311`)。

即:**记忆是增益不是依赖**——记忆系统整体故障时 agent 退化为无记忆但完全可用,且模型会在工具结果里得到可转述的原因。

### 1.8 README vs 代码 逐条对照(mem0)

| # | README 断言 | 代码事实 | 判定 |
|---|---|---|---|
| 1 | `README.md:28`:`mode` 默认 `platform` | `__init__.py:88` `os.environ.get("MEM0_MODE", "platform")` | 一致 |
| 2 | `README.md:30`:`user_id` 默认 `hermes-user` | `__init__.py:56-62、353-356`:该值是**哨兵**,被视为未配置,实际回落网关原生 id | ▲ 有误导:写着"默认值"的字符串在代码里等于"没配",按 README 填 hermes-user 会得到与预期不同(其实是更合理)的 per-gateway 隔离 |
| 3 | `README.md:65`:"authenticates with X-API-Key ... /search and /memories routes. api_key is optional — omit it only for AUTH_DISABLED" | `_backend.py:97-99、115-147` 完全一致 | 一致 |
| 4 | `README.md:67`:"Don't set mode: oss — OSS takes precedence and ignores host" | `_create_backend` 280-288 优先级 oss>host;测试 test_mem0_v3.py:384-391 锁死 | 一致 |
| 5 | `README.md:101` Flags 表:`--mode` 取值 "platform or oss" | `_setup.py:980` 还接受 `selfhosted`/`self-hosted`(README 自己 49 行也用了) | ▲ 表格漏了第三个取值,README 内部自相矛盾 |
| 6 | `README.md:7`:Requirements "pip install mem0ai"(无版本) | plugin.yaml 要求 `mem0ai>=2.0.10,<3`;且 `__init__.py:274` 会懒安装,手动装并非必须 | ◇ 不完整:无版本约束,也未提及懒安装 |
| 7 | `README.md:32`:rerank "platform mode only" | `__init__.py:396-397` 提示词只在 platform 提 rerank;`_backend.py:115-117` selfhosted 忽略;OSS `search` 直接不传 | 一致 |
| 8 | `README.md:146`:mem0_add "Store a fact verbatim (no LLM extraction)" | `__init__.py:566` `infer=False` | 一致 |
| 9 | `README.md:154`:"Circuit breaker tripped after 5 consecutive failures. Resets after 2 minutes." | `__init__.py:51-52` 阈值 5、冷却 120s | 一致 |
| 10 | `README.md:185`:"Use sync_turn for LLM extraction" | `__init__.py:497` sync_turn `infer=True` | 一致 |
| 11 | `README.md:3`:"hybrid multi-signal retrieval via the Mem0 Platform v3 API" | 代码只见 MemoryClient.search 透传;"v3 API"是 SDK/服务端行为,本仓库内不可证 | ◇ 本仓不可验证的宣传句,存疑不判 |
| 12 | `_setup.py:954` 最低版本 (2,0,7) vs plugin.yaml `>=2.0.10` | 见 §1.5 | ▲ 代码内部漂移(非 README,但属文档-代码类冲突,记录) |

### 1.9 配套测试与行为规格(mem0)

测试文件:`tests/plugins/memory/test_mem0_v3.py`(411 行,provider 主体+路由+user_id 解析)、`test_mem0_backend.py`(215 行,三后端:Platform 参数透传/OSS legacy api_base 归一化/SelfHosted X-API-Key 与 HTTP 错误)、`test_mem0_setup.py`(233 行,flag 解析/OSS 配置构建/.env BOM 行为)、`test_mem0_providers.py`(78 行,注册表校验)、`test_memory_lazy_install.py`;另有 `tests/agent/test_memory_user_id.py`(281 行,跨 provider 的 user_id 契约)。

**行为规格 1:prefetch 永不阻塞在慢后端上**。`tests/plugins/memory/test_mem0_v3.py:189-231 @ 863e313`——把后端 search 用 Event 停住,断言 `provider.prefetch(...) == ""` 且此时后端 search **仍停着**(`assert not search_returned.is_set()`);释放后 join 线程,再次 prefetch 拿到 "lives in Berlin"。注释明确说这是把老的 `assert elapsed < 0.1` 壁钟断言改成确定性见证,消除调度器抖动导致的假失败。这就是"超时放弃注入、结果不丢、下次消费"的完整规格。

**行为规格 2:路由优先级与提示词一致性**。`test_mem0_v3.py:384-401`——`mode=oss` 且 `host` 同时设置时,`_create_backend()` 必须返回 OSSBackend,且 `system_prompt_block()` 必须含 "OSS"、不含 "HTTP API"("Guards the prompt-vs-routing lie")。

---

## 2. holographic:零外部依赖的本地"全息"记忆

### 2.1 "全息"指什么:HRR 相位向量代数(holographic.py)

**HRR = Holographic Reduced Representations(Plate 1995)**,一类 Vector Symbolic Architecture:把符号结构编码进定宽分布式向量,靠代数运算(绑定/解绑/叠加)做组合式查询。本实现不用经典的实数循环卷积,而是**相位编码**变体:每个概念是一个 dim 维**角度向量**(每个分量 ∈ [0, 2π)),于是:

- **bind(绑定)= 逐元素相位相加**(等价于复数单位向量逐元素相乘,即频域的循环卷积),`plugins/memory/holographic/holographic.py:77-84 @ 863e313`:

```python
def bind(a: "np.ndarray", b: "np.ndarray") -> "np.ndarray":
    """Circular convolution = element-wise phase addition.

    Binding associates two concepts into a single composite vector.
    The result is dissimilar to both inputs (quasi-orthogonal).
    """
    _require_numpy()
    return (a + b) % _TWO_PI
```
- **unbind(解绑)= 相位相减**(循环相关),`unbind(bind(a,b), a) ≈ b` 至叠加噪声(`holographic.py:87-94`);
- **bundle(叠加)= 复指数求和取辐角**(圆均值),结果与每个输入相似,容量 O(√dim),`plugins/memory/holographic/holographic.py:97-105 @ 863e313`:

```python
def bundle(*vectors: "np.ndarray") -> "np.ndarray":
    """Superposition via circular mean of complex exponentials.

    Bundling merges multiple vectors into one that is similar to each input.
    The result can hold O(sqrt(dim)) items before similarity degrades.
    """
    _require_numpy()
    complex_sum = np.sum([np.exp(1j * v) for v in vectors], axis=0)
    return np.angle(complex_sum) % _TWO_PI
```
- **similarity = 相位差余弦均值**,`float(np.mean(np.cos(a - b)))`,范围 [-1,1],随机向量≈0(`holographic.py:108-115`)。

选相位编码的理由写在模块头(`holographic.py:12-14`):数值稳定、避免传统复数 HRR 的模长坍缩、天然映射到余弦相似度。

**atom(原子向量)是确定性的**:SHA-256 计数器块生成——`f"{word}:{i}"` 逐块哈希,digest 按 uint16 小端解包,缩放到 [0,2π),`plugins/memory/holographic/holographic.py:68-73 @ 863e313`:

```python
    uint16_values: list[int] = []
    for i in range(blocks_needed):
        digest = hashlib.sha256(f"{word}:{i}".encode()).digest()
        uint16_values.extend(struct.unpack("<16H", digest))

    phases = np.array(uint16_values[:dim], dtype=np.float64) * (_TWO_PI / 65536.0)
    return phases
```
不用 numpy RNG 是为了**跨进程/跨机器/跨版本可复现**——同一个词永远是同一个向量,数据库因此可以只存事实向量、随时按需重新编码查询向量。

**文本与事实的编码**:`encode_text` = 小写分词去标点后所有 token atom 的 bundle(词袋,无词序,`plugins/memory/holographic/holographic.py:118-139`);`encode_fact` 引入两个保留角色原子做**槽-填充结构**,`plugins/memory/holographic/holographic.py:147-172 @ 863e313`:

```python
    Components:
    1. bind(encode_text(content, dim), encode_atom("__hrr_role_content__", dim))
    2. For each entity: bind(encode_atom(entity.lower(), dim), encode_atom("__hrr_role_entity__", dim))
    3. bundle all components together

    This enables algebraic extraction:
        unbind(fact, bind(entity, ROLE_ENTITY)) ≈ content_vector
```
即一条事实 = bundle( content⊗ROLE_CONTENT, entity₁⊗ROLE_ENTITY, entity₂⊗ROLE_ENTITY, … )。检索时用 `bind(entity, ROLE_ENTITY)` 当钥匙解绑,残差与内容信号比相似度——这就是 probe/reason 的数学基础。

**序列化**:float32 blob 带 `b"HRR1"` 前缀(dim=1024 时 4KB+4B,比 legacy float64 的 8KB 省一半),读侧兼容无前缀 float64 老格式;dim=1 时两种格式同为 8 字节会歧义,写侧退回 float64、读侧优先按 legacy 解释(`holographic.py:170-263`,详尽的碰撞窗口注释在 196-211)。

**容量守卫**:`snr_estimate(dim, n_items) = sqrt(dim/n_items)`,SNR<2(即 n_items > dim/4,默认 1024 维 ≈ 256 条/类别)时 log warning "HRR storage near capacity"(`holographic.py:266-290`)。

**重实现要点(2.1)**
- 相位 HRR 三件套:bind=模 2π 加、unbind=模 2π 减、bundle=复指数和取角;相似度 = mean(cos(Δ));
- atom 必须内容寻址、确定性生成(哈希计数器块),这换来"查询向量永不落盘、随处重算"的自由;
- 结构化编码用保留角色原子(role-filler binding),检索=解绑+残差比对;
- 叠加容量 O(√dim),要有 SNR 告警;序列化格式变更要处理新老共存与尺寸碰撞。

### 2.2 store.py:SQLite 里存什么、怎么存

**Schema**(`store.py:16-76 @ 863e313`):五张表/虚表——
- `facts`:content(UNIQUE,内容即去重键)、category(默认 general)、tags、trust_score(默认 0.5)、retrieval_count、helpful_count、created/updated_at、`hrr_vector BLOB`(相位向量,§2.1 格式);
- `entities`(name/entity_type/aliases 逗号分隔)与 `fact_entities` 多对多连接表;
- `facts_fts`:FTS5 外部内容表(`content=facts, content_rowid=fact_id`),三只触发器(insert/delete/update)维持同步(51-66);
- `memory_banks`:每类别一条,`bank_name = "cat:<category>"`,存该类别**全部事实向量的 bundle**(叠加"全息图")+ dim + fact_count。

**进程级共享连接注册表**(本文件最重的工程机制),动机注释 `plugins/memory/holographic/store.py:102-113 @ 863e313`:

```python
    # SQLite permits only one writer at a time. Each MemoryStore instance used
    # to open its own connection guarded by its own RLock, so the several
    # providers that coexist in one process (the main agent plus every
    # delegate_task subagent) raced as independent WAL writers. Combined with
    # writes that were not rolled back on error, one connection could leave an
    # open write transaction that pinned the write lock and made every other
    # connection's write fail with "database is locked" for the full busy
    # timeout. All instances for the same database now share ONE connection and
    # ONE re-entrant lock, so access is fully serialized and cross-connection
    # contention is impossible. The shared connection is refcounted, so closing
    # one instance never tears the connection out from under a live sibling.
```
实现三根支柱:(a) 键是 `Path.resolve()` 后的真实路径,符号链接/相对路径归并到同一连接(`store.py:132-138`);(b) 连接以 `isolation_level=None`(autocommit)打开——每条语句自成事务,**中途抛异常不可能留下悬挂写事务钉死写锁**,显式 commit 全部变成无害 no-op(`store.py:142-151`);(c) 引用计数 close:最后一个引用才真正关连接(`store.py:619-638`)。WAL 开启走共享的 `apply_wal_with_fallback`,NFS/SMB/FUSE 上优雅降级(`store.py:170-177`)。

**add_fact 写路径**(`store.py:188-231`):strip→INSERT(UNIQUE 冲突则返回既有 id,不改行)→正则实体抽取(四条规则:连续大写词组 / 双引号 / 单引号 / "X aka Y",去重保序,`store.py:85-91、447-480`)→实体解析(名字 LIKE 大小写不敏感精确匹配→别名逗号边界 LIKE→新建,`store.py:482-510`)→连接表→`_compute_hrr_vector`(拉实体列表,encode_fact 落 blob,`store.py:523-545`)→`_rebuild_bank(category)`——**每次写都全量重建该类别的叠加向量**并跑 SNR 告警(`store.py:547-583`)。

**trust 机制**:`record_feedback` 不对称调整——helpful +0.05、unhelpful −0.10,钳制 [0,1](`store.py:79-82、402-441`)。坏事实沉底比好事实上浮快一倍。

**死代码(定案 ◇)**:`search_facts`(233-289)与 `rebuild_all_vectors`(585-609)全仓无调用点(实测 grep 仅定义处)。前者与 retriever.search 功能重叠(甚至反向 import retriever 的 sanitizer,`store.py:250-260`);后者 docstring 自称"For recovery/migration"。属预留 API,记录不判错。

**重实现要点(2.2)**
- 同进程多实例写同一 SQLite:进程级 {resolve 路径 → 单连接+单 RLock+引用计数} 注册表,一劳永逸消灭 "database is locked";
- autocommit(isolation_level=None)是"异常不悬挂事务"的结构性保证,比到处 try/rollback 可靠;
- 外部内容 FTS5 + 触发器同步是零成本全文索引的标准做法;
- 派生数据(HRR 向量、类别 bank)在写路径同步维护,读路径零重算;
- 反馈调 trust 用不对称步长,负反馈权重更大。

### 2.3 retrieval.py:五种召回

**search:三信号混合 + trust 加权**。管线(`plugins/memory/holographic/retrieval.py:48-122`):FTS5 取 limit×3 候选 → 对每个候选算 Jaccard(查询 token ∩ content+tags token)与 HRR 相似度(查询 encode_text vs 事实向量,平移到 [0,1];无向量的老行给中性 0.5)→ 加权合成再乘 trust,`plugins/memory/holographic/retrieval.py:101-107 @ 863e313`:

```python
            # Combine FTS5 + Jaccard + HRR
            relevance = (self.fts_weight * fts_score
                        + self.jaccard_weight * jaccard
                        + self.hrr_weight * hrr_sim)

            # Trust weighting
            score = relevance * fact["trust_score"]
```
默认权重 0.4/0.3/0.3;numpy 缺席时自动重分配为 0.6/0.4/0(`retrieval.py:29-46`)。可选时间衰减 `0.5^(age_days/half_life)`(`retrieval.py:110-111、644-668`),默认关闭(half_life=0)。查询向量惰性 hoist:只在第一个真带向量的候选出现时才编码一次(`retrieval.py:81-96`,注释说明迁移库可能整批候选无向量,不该白付编码)。

**FTS5 查询消毒**(召回正确性的命门):FTS5 对多词 MATCH 默认 AND 连接,自然语言查询召回归零。`_sanitize_fts_query`(`retrieval.py:599-633`)分词→去停用词(120 词表,581-597)与 <2 字符 token→逐 token 剥 FTS5 算子字符 `"()*^:-+`→**短语字面量化后 OR 连接**;全被过滤则回退原始查询(宁可 0 结果不可 SQL 错)。`_fts_candidates` 把 FTS5 的负 rank 归一化到 [0,1],MATCH 异常吞掉返回空(`retrieval.py:538-560`)。

**probe(实体探针)**:构造钥匙 `bind(entity, ROLE_ENTITY)`;指定 category 且有 bank 时,**先从类别叠加向量整体解绑**得到"这个实体在该类别中关联的内容信号",再拿它给逐条事实打分(`retrieval.py:145-162`);否则逐事实解绑:`residual = unbind(fact_vec, probe_key)`,与 `bind(encode_text(content), ROLE_CONTENT)` 比相似度——实体真在事实里扮演结构角色时,解绑会"抵消"实体分量、残差与内容信号对齐(`retrieval.py:188-202`)。无 numpy / 无向量行时回退 FTS 搜索。

**related(结构邻接)**:用**裸实体原子**(不绑角色)解绑,看残差与两个角色原子哪个更像取 max——实体无论以实体角色还是内容词身份出现都能命中(`retrieval.py:222-272`)。

**reason(多实体合取,向量空间 JOIN)**:对每个实体各造钥匙,逐事实分别解绑打分,**取 min**——AND 语义,所有实体都结构性在场才高分,`plugins/memory/holographic/retrieval.py:329-346 @ 863e313`:

```python
        # Score each fact by how much EACH entity is structurally present.
        # A fact scores high only if ALL entities have structural presence
        # (AND semantics via min, vs OR which would use mean/max).
```
```python
            entity_scores = []
            for probe_key in entity_residuals:
                residual = hrr.unbind(fact_vec, probe_key)
                sim = hrr.similarity(residual, role_content)
                entity_scores.append(sim)

            min_sim = min(entity_scores)
            fact["score"] = (min_sim + 1.0) / 2.0 * fact["trust_score"]
```

**contradict(矛盾检测)**:定义"同主体不同说法"= 实体集 Jaccard 重叠 ≥0.3 **且** 内容向量相似度低;分数 = `entity_overlap * (1 - (content_sim+1)/2)`,≥0.3 报出成对结果附共享实体(`retrieval.py:414-453`)。O(n²) 护栏:超过 500 条只比对最近更新的 500 条(~125K 次比较,`retrieval.py:392-398`)。工具层未暴露 threshold 参数(provider `__init__.py:321-326` 只传 category/limit)。

**重实现要点(2.3)**
- 词法(FTS5)+ 集合(Jaccard)+ 结构(HRR)三信号互补,乘 trust 做最终排序;任一信号缺席可降级重分配权重;
- 把自然语言塞进 FTS5 前必须消毒:去停用词、OR 连接、短语字面量化、异常兜底——这是"召回为零"级别的正确性问题,不是优化;
- 合取查询用 min 聚合是向量记忆里最便宜的 AND;
- 矛盾检测 = 高实体重叠 × 低内容相似,配 O(n²) 上限护栏;
- 循环不变的确定性向量(角色原子、查询向量)hoist 到循环外,且用"逐位相同"测试锁住等价性。

### 2.4 __init__.py(holographic):装配、auto_extract、镜像写

**工具面**:`fact_store`(9 动作:add/search/probe/related/reason/contradict/update/remove/list,schema `__init__.py:39-75`)+ `fact_feedback`(helpful/unhelpful,77-91)。handler 是纯分发(271-367),KeyError 统一报"Missing required argument"。

**配置**:住 config.yaml 的 `plugins.hermes-memory-store` 下(`_load_plugin_config`,98-105,走 managed-scope overlay + ${VAR} 展开的规范读取)。initialize(156-179)展开 db_path 里的 `$HERMES_HOME`/`${HERMES_HOME}`,建 MemoryStore + FactRetriever。`is_available` 恒 True(126-127):SQLite 永远在,numpy 只是可选增强。

**prefetch**:retriever.search 取 top5、min_trust 过滤,格式 `- [0.8] fact内容`(204-218)。**sync_turn 是显式 pass**(220-223):自动摄入不走每 turn,而走 on_session_end。

**on_session_end 的 auto_extract**(需 plugin.yaml 声明 `hooks: [on_session_end]`):默认关;开关判断用 `is_truthy_value` 而非裸 truthiness——因为 schema 里 auto_extract 是字符串枚举,`"false"` 按裸真值判断是 True(#57682),`plugins/memory/holographic/__init__.py:235-240 @ 863e313`:

```python
    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        # is_truthy_value: the config schema declares auto_extract as a string
        # enum ("false"/"true"), and a plain truthiness check treats the string
        # "false" as enabled (#57682).
        if not is_truthy_value(self._config.get("auto_extract", False)):
            return
```
抽取本体(371-451)是**纯正则**:偏好三式(`I prefer/like/love/use/want/need`、`my favorite ... is`、`I always/never/usually`)入 user_pref,决策两式(`we decided/agreed/chose`、`the project uses/needs/requires`)入 project,截断 400 字符。两个真实事故防御:压缩器(context compressor)的 handoff 摘要以 role=user 插入,其行文**稳定命中决策正则**,不挡住就每次 rollover 都把压缩器自述存成"事实"(#57682);而 merge-into-tail 型摘要同一行里前半段是真实用户内容,整行丢弃会连真话一起丢,所以按 `_MERGED_SUMMARY_DELIMITER` 切开只收前段(#57690 review)(`__init__.py:380-428`)。

**on_memory_write 镜像**(245-252):内置 memory 工具每次 add 都同步镜像成一条 fact(target=="user" → user_pref),两套记忆间做单向同步。

**shutdown**(254-267):显式 `store.close()` 而非弃引用等 GC——注释点明长驻网关上 GC 迟迟不回收会把连接和写锁一直吊着,恰好复活共享连接机制要消灭的 "database is locked"。

**ABC 映射表(holographic)**

| ABC 成员 | 实现 | 位置(@ 863e313) |
|---|---|---|
| name | `"holographic"` | 122-124 |
| is_available | 恒 True | 126-127 |
| initialize | 路径展开 + Store/Retriever 装配 | 156-179 |
| system_prompt_block | 按 fact 总数分"空库劝存"/"报数劝查"两版 | 181-202 |
| prefetch | retriever.search top5,异常返 "" | 204-218 |
| sync_turn | pass(设计决定:只显式/会末摄入) | 220-223 |
| get_tool_schemas / handle_tool_call | 2 工具 9+2 动作 | 225-233、271-367 |
| shutdown | 显式 close(refcount 安全) | 254-267 |
| on_session_end(钩子) | auto_extract 正则收割(带压缩摘要防御) | 235-243、371-451 |
| on_memory_write(钩子) | 镜像内置 memory 写 | 245-252 |
| get_config_schema / save_config(钩子) | 4 字段 / 写 config.yaml(raw 读回写) | 146-154、129-144 |

### 2.5 无外部服务下的性能/精度取舍

- **精度上限**:encode_text 是词袋——无词序、无语义。"cat chases dog" 与 "dog chases cat" 同向量;同义词零相似(SHA-256 原子间准正交)。HRR 信号擅长的是**结构**(哪个实体跟哪条内容绑在一起),语义泛化整体靠 FTS5+Jaccard 的词面匹配打底,这是不调用嵌入模型的根本代价。
- **容量**:bundle 容量 O(√dim);SNR=√(dim/n) < 2 即告警,默认 1024 维时每类别 ~256 条以上 bank 探针开始不可靠(`holographic.py:266-290`)。逐事实打分路径不受 bank 容量限制,但是全表扫描。
- **计算复杂度**:probe/related/reason/`_score_facts_by_vector` 全部 `SELECT ... WHERE hrr_vector IS NOT NULL` 全表拉取逐行解码打分(如 `retrieval.py:171-180`)——没有 ANN 索引。dim=1024 的逐元素 cos 均值极便宜,千条级毫秒档,但 O(N) 天花板明确;contradict 另有 500 条硬顶。
- **存储**:每事实 4KB(float32)向量;bank 每类别一条 4KB。全库单文件 SQLite,`backup_paths` 天然友好。
- **换来的东西**:零网络、零凭据、零服务进程、隐私完全本地、毫秒级延迟、跨机器确定性可复现(SHA-256 原子)、以及嵌入库给不了的两个查询原语——reason 的代数 AND 与 contradict 的矛盾对(代价见上)。

### 2.6 README vs 代码 逐条对照(holographic)

| # | README 断言 | 代码事实 | 判定 |
|---|---|---|---|
| 1 | `README.md:3`:"Local SQLite fact store with FTS5 search, trust scoring, entity resolution, and HRR-based compositional retrieval" | store.py schema + retrieval.py 五算法俱全 | 一致 |
| 2 | `README.md:7`:"Requirements: None — uses SQLite (always available). NumPy optional" | `__init__.py:126-127` is_available 恒 True;`holographic.py:27-31` numpy try/except;`retrieval.py:39-42` 无 numpy 重分配权重 | 一致 |
| 3 | `README.md:24-29` 配置表:db_path/auto_extract/default_trust/hrr_dim 四键 | initialize 还读 `min_trust_threshold`(`__init__.py:120`)、`hrr_weight`(169)、`temporal_decay_half_life`(170);模块 docstring(8-16)列了 min_trust_threshold/temporal_decay 却没列 hrr_dim/hrr_weight | ▲ README 与 docstring 各漏一半:实际可配 7 键,任一处文档都不全 |
| 4 | `README.md:35`:"fact_store | 9 actions: add, search, probe, related, reason, contradict, update, remove, list" | schema enum(`__init__.py:58-61`)正是这 9 个 | 一致 |
| 5 | `README.md:22`:"Config in config.yaml under plugins.hermes-memory-store" | `_load_plugin_config`(104)一致;但 plugin.yaml `name: holographic`、provider name "holographic" | ◇ 一致但暗坑:插件名与配置键不同名(历史名 hermes-memory-store 残留),README 未解释 |
| 6 | `README.md:36`:fact_feedback "trains trust scores" | `store.py:402-441` +0.05/−0.10 不对称调整 | 一致("trains"是修辞,实为固定步长) |

### 2.7 配套测试与行为规格(holographic)

测试文件:`tests/plugins/memory/test_holographic_store.py`(227 行,共享连接/关闭语义/并发)、`test_holographic_retrieval.py`(240 行,FTS 消毒 + hoist 等价性)、`test_holographic_auto_extract.py`(139 行,压缩摘要防御)、`test_holographic_shutdown_closes_db.py`(48 行)、`tests/plugins/test_holographic_vector_storage.py`(205 行,float32/float64 blob 全矩阵:round-trip、dim=1 碰撞、malformed 拒收、legacy 读取、bank 落盘 float32)。

**行为规格 1:失败写不钉写锁**。`tests/plugins/memory/test_holographic_store.py:186-207 @ 863e313`——monkeypatch 让 `_rebuild_bank` 在 INSERT 之后必抛;断言抛完 `broken._conn.in_transaction is False`(autocommit 无悬挂事务),且 sibling 实例**立即**能写。这是 `isolation_level=None` 决策的直接规格。同类 `test_concurrent_multi_instance_writers`(157-184):8 线程 × 15 事实并发写,零 "database is locked",总数精确 120,收尾 `MemoryStore._shared == {}`(引用计数归零)。

**行为规格 2:自然语言查询必须能召回**。`tests/plugins/memory/test_holographic_retrieval.py:84-95 @ 863e313`——种入"Thursday deployment rollback failed..."后,查询 "what happened with the deployment rollback" 必须命中且排第一;文件头注明修复前该查询因 FTS5 默认 AND 连接返回 0 条。参数化用例(22-55)同时钉死:全停用词查询回退原文、算子字符被剥(`"context: length-probe"` → `{"context","lengthprobe"}`)。

---

## 3. 对比:云 SaaS(mem0 托管)vs 纯本地数学(holographic)

同一份 ABC 契约下的两个极端,几乎每条轴上都是镜像:

| 轴 | mem0(platform 形态) | holographic |
|---|---|---|
| 智能所在 | 服务端:LLM 抽取、语义嵌入、去重、rerank 全在 Mem0 云上 | 本地:SHA-256 原子 + 相位代数 + FTS5,全程无一次模型调用 |
| 依赖面 | API key、网络、mem0ai SDK(还要懒安装);OSS 形态更要 LLM+嵌入+向量库三件套 | 标准库 sqlite3;numpy 可选(缺了自动降为 FTS+Jaccard,`retrieval.py:39-42`) |
| 摄入 | sync_turn 每 turn 推给服务端 `infer=True` 自动抽取 | sync_turn 刻意 pass;靠工具显式 add、会末正则收割、内置 memory 镜像 |
| 语义泛化 | 有(嵌入 + 可选 rerank):换措辞也能召回 | 无:同义词准正交,靠 OR 化 FTS 和词面重叠兜底 |
| 结构查询 | 无原语:多跳靠提示词逼模型多次搜索(`__init__.py:406-409`) | 有原语:probe/related/reason(代数 AND)/contradict 直接一次调用 |
| 失败模型 | 网络/服务故障 → 熔断器 + fail-open,记忆退化不拖垮对话 | 几乎无网络故障面;风险换成本地锁与容量(共享连接注册表、SNR 告警) |
| 身份/多租户 | user_id/agent_id/channel 三维,跨网关合并是一等公民 | 单用户单库(docstring "Single-user Hermes memory store plugin",`store.py:3`),身份问题不存在 |
| 隐私/成本 | 对话内容出境到第三方云;按 SaaS 计费 | 数据不出盘;边际成本≈0 |
| 复杂度分布 | 代码复杂度堆在**运维接线**上(三形态路由、1001 行 setup、维度漂移重建) | 复杂度堆在**算法与本地工程**上(HRR 数学、FTS 消毒、SQLite 并发) |

**可迁移结论**:ABC 这层抽象的价值恰好被这两家证明——契约只规定"注入、召回、摄入、工具、关闭"五件事的时机与形状,不规定智能在哪。云后端把钱花在服务端模型上,换语义;本地后端把 CPU 花在确定性代数上,换隐私与结构原语。harness 侧的护栏(prefetch 围栏、单 provider、fail-open)对两者一视同仁,这是"记忆是增益不是依赖"原则的接口化表达。做自己的 harness 时,记忆后端接口至少要预留:同步/异步两条写路径语义位(verbatim vs infer)、prefetch 的超时放弃语义、以及 setup 钩子(能力差异巨大的后端各自需要完全不同的 onboarding,mem0 用 1001 行证明了这点)。

---

## 4. 台账与状态

本轮覆盖 10 个文件(mem0 5 + holographic 5,共 4319 行)建议置 `L1 / R6-deep-read`;引用过的测试文件(test_mem0_v3.py、test_mem0_backend.py、test_mem0_setup.py、test_mem0_providers.py、test_holographic_store.py、test_holographic_retrieval.py、test_holographic_auto_extract.py、test_holographic_shutdown_closes_db.py、tests/plugins/test_holographic_vector_storage.py)作 LT 行为规格参照。定案汇总:▲ 3 条(mem0 README user_id 默认值误导;mem0 README --mode 取值表不全;holographic 配置键文档两处各缺一半)、◇ 4 条(mem0 依赖版本未入 README 且 _setup 检查阈值 2.0.7 落后 plugin.yaml 2.0.10;"v3 API"宣传句仓内不可验;store.py `search_facts`/`rebuild_all_vectors` 死代码;插件名 holographic vs 配置键 hermes-memory-store 不同名)。