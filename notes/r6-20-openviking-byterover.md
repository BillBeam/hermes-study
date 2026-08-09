# R6 底稿 · openviking + byterover 记忆后端

> L1 精读底稿。对象:`plugins/memory/openviking/__init__.py`(5212 行)+ `README.md`(122 行);`plugins/memory/byterover/__init__.py`(449 行)+ `README.md`(41 行)。全部行号实测于基线 commit 863e313。上轮已定的 ABC 契约与 MemoryManager 围栏(读 8s 超时、写单 worker 离线)作为已知前提,本稿只补一处关键常量佐证:`agent/memory_manager.py:47 @ 863e313` `_EXTERNAL_PREFETCH_TIMEOUT_S = 8.0`。

---

## 一、OpenViking:它是什么、存储在哪、什么形态

**结论:Hermes 侧是一个纯 REST 客户端(httpx),没有本地索引、没有本地 embedding、没有本地数据库。** 真正的存储、向量索引、embedding/VLM 抽取全部在外部的 `openviking-server` 进程(火山引擎/字节的 "context database",可本地跑也可用 VolcEngine 云托管端点)。

`plugins/memory/openviking/__init__.py:1-8 @ 863e313`:

```python
"""OpenViking memory plugin — full bidirectional MemoryProvider interface.

Context database by Volcengine (ByteDance) that organizes agent knowledge
into a filesystem hierarchy (viking:// URIs) with tiered context loading,
automatic memory extraction, and session management.

Original PR #3369 by Mibayy, rewritten to use the full OpenViking session
lifecycle instead of read-only search endpoints.
...
```

`plugins/memory/openviking/__init__.py:65-66 @ 863e313`:

```python
_DEFAULT_ENDPOINT = "http://127.0.0.1:1933"
_OPENVIKING_SERVICE_ENDPOINT = "https://api.vikingdb.cn-beijing.volces.com/openviking"
```

数据模型是**文件系统层级 + 三级摘要**:一切内容是 `viking://` URI 下的"文件/目录",每个节点有 L0 abstract(约 100 token)、L1 overview(约 2k token)、L2 全文三个读取档位(`README_SCHEMA` 描述,`__init__.py:499-509`)。embedding 模型是**服务端的事**,配置在服务端自己的 `ov.conf` 里,插件从不接触(`README.md:60-62 @ 863e313`:"`ov.conf` configures OpenViking storage, embedding/VLM models, auth, and server behavior")。插件唯一 pip 依赖是 httpx(`plugins/memory/openviking/plugin.yaml @ 863e313`:`pip_dependencies: [httpx]`),且是惰性导入(`__init__.py:278-284` `_get_httpx()`)。

Hermes 本地磁盘上属于这个插件的东西只有四类,全是**控制面文件而非数据**:
1. 连接配置:profile 的 `.env`(OPENVIKING_* 五个变量)或 `~/.openviking/ovcli.conf`(与 OpenViking CLI 共享);
2. 崩溃恢复标记:`$HERMES_HOME/openviking/pending_sessions/<sid>.json`;
3. 运行锁:`$HERMES_HOME/openviking/runs/<run_id>.lock`;
4. 自动拉起的 server 日志:`$HERMES_HOME/logs/openviking-server.log`。

`__init__.py:144,160-161 @ 863e313`:

```python
_OPENVIKING_SERVER_LOG_RELATIVE_PATH = Path("logs") / "openviking-server.log"
...
_PENDING_SESSIONS_RELATIVE_DIR = Path("openviking") / "pending_sessions"
_RUN_LOCKS_RELATIVE_DIR = Path("openviking") / "runs"
```

**重实现要点**
- 把"记忆后端"拆成 数据面(远端服务)/ 控制面(本地配置+恢复标记)两层;客户端零数据落盘,崩溃恢复只需持久化"哪些会话还没 commit"这一个事实。
- 摘要分级(L0/L1/L2)由服务端预生成,客户端按需选档,是控制注入 token 成本的核心抓手。

---

## 二、5212 行结构分块(全文件地图)

| 块 | 行号 | 内容 |
|---|---|---|
| A | 1-167 | 模块头、常量(超时、召回默认值、URI 常量、身份态枚举、分类→子目录映射) |
| B | 169-243 | 错误类型、错误消息脱敏(`_sanitize_openviking_error_message` 189-207:HTML 错误页提取 `<title>`、截 300 字)、skill 脚手架剥离(220-230)、sync trace 开关 |
| C | 245-271 | **atexit 安全网**:进程退出时对最后活跃 provider 补一次 `on_session_end` |
| D | 274-466 | `_VikingClient`:薄 HTTP 客户端(headers/认证/trusted-mode 重试/响应解析/上传/健康与身份探测) |
| E | 469-651 | 6 个工具 schema + 召回类工具名集合 + tool_status 规范化别名表 |
| F | 654-750 | 资源上传辅助(目录打 zip、file:// 解析、本地路径判定)、`viking_forget` URI 白名单校验 |
| G | 753-849, 971-1049, 1130-1243 | ovcli.conf 配置族:读取/发现 profile/写 .env(注入防护)/写 ovcli(原子+0600) |
| H | 850-916 | 端点归一化 + SSRF 安全底线(cloud-metadata 地址拒绝) |
| I | 919-968 | 服务身份探测:modern/legacy/unhealthy/invalid 状态机 |
| J | 1052-1127 | 连接设置解析链:env → ovcli → config.yaml → 默认值 |
| K | 1246-2152 | `hermes memory setup` 交互流:可达性/认证/root-vs-user key 验证、profile 选择与镜像 |
| L | 1398-1657 | 本地 server 自动拉起:端口探测、进程识别(psutil)、spawn、健康等待、运行期健康分类 |
| M | 2159-5203 | `OpenVikingMemoryProvider` 本体(下面逐机制) |
| N | 5206-5212 | `register(ctx)` 插件入口 |

**重实现要点**
- 一个 5000 行的后端插件,约 40% 行数花在"连接的取得与守护"(G/H/I/J/K/L),不在记忆逻辑本身——外部服务型后端的复杂度大头是配置解析、健康判定与降级,不是业务调用。

---

## 三、_VikingClient:认证、trusted-mode 重试、响应契约

**认证有两套互斥模式**:有 API key 时靠 key(服务端从 key 推导租户),没 key 时(本地/信任模式)发 `X-OpenViking-Account` / `X-OpenViking-User` 断言租户身份。`__init__.py:305-320 @ 863e313`:

```python
    def _headers(self, *, include_tenant: bool | None = None) -> dict:
        if include_tenant is None:
            include_tenant = not bool(self._api_key)

        h = {"Content-Type": "application/json"}
        if self._agent:
            h["X-OpenViking-Actor-Peer"] = self._agent
        if include_tenant:
            if self._account:
                h["X-OpenViking-Account"] = self._account
            if self._user:
                h["X-OpenViking-User"] = self._user
        if self._api_key:
            h["X-API-Key"] = self._api_key
            h["Authorization"] = "Bearer " + self._api_key
```

**trusted-mode 重试**:带 key 的请求默认不发租户头;若服务端明确报"Trusted mode requests must include X-OpenViking-Account/User"(且 status 是 400),自动带租户头重发一次;故意的权限拒绝不重试(`_needs_trusted_identity_retry`,330-348;`_send_with_trusted_identity_retry`,350-361)。

**响应契约**:HTTP ≥400 或 body `{"status":"error"}` 都转异常;错误结构 `{"error":{"code","message"}}` 被展平(363-394)。**身份探测是匿名的**:`_anonymous_json` 不带任何凭据探 `/health` 与 `/openapi.json`(447-458),避免向未验明身份的端点泄露 key(有专门测试 `test_openviking_identity_probes_are_anonymous_before_authenticated_requests`)。

**身份状态机**(947-964):`/health` 返回 `{"status":"ok","healthy":true,"version":"x"}` → modern;仅 `{"status":"ok"}`(0.2.6 及以前的旧契约)→ 还要匿名读 `/openapi.json` 验证 `info.title == "OpenViking API"` 才算 legacy,验不上是 legacy-unverified(拒用);`healthy:false` → unhealthy;其他 → invalid。

**端点安全底线**(865-916):归一化 URL(localhost 简写补全 `:1933`、拒绝 userinfo/query/fragment),然后过 `is_always_blocked_url` 拒绝 cloud-metadata 类地址——注释明说这是防"被投毒的 endpoint 借 memory sync 做 SSRF",且**绝不静默替换成 localhost**(898-900)。`_openviking_endpoint_is_always_blocked` 用 `lru_cache(128)` 按完整 endpoint 缓存 DNS 检查(850-862)。

**重实现要点**
- 对外部服务:先匿名验明"你是谁",再发凭据;两种认证模式的差异用"错误驱动的一次性重试"兜住版本差异,而非枚举版本。
- 用户可配的 URL 必须过 SSRF 底线,且失败时 fail-closed,不自动改写目的地。

---

## 四、ABC 方法映射(openviking)

| ABC 方法 | 实现位置 @ 863e313 | 行为 |
|---|---|---|
| `name` | 2234-2236 | `"openviking"` |
| `is_available` | 2238-2253 | 纯配置检查(env/config.yaml/ovcli 有 endpoint 即可),零网络 |
| `initialize` | 2659-2750 | 解析连接→建 client→健康分类→(本地)后台拉起 server→拿 run lock→恢复 pending 会话→登记 atexit |
| `system_prompt_block` | 2867-2913 | 根目录 `fs/ls` 非空才注入工具使用守则;失败降级为短版守则 |
| `prefetch` | 2915-2935 | 会话首帧 profile 注入 + 语义召回(详见第五节) |
| `queue_prefetch` | 2986-2988 | 显式 no-op(召回只针对当前 query,不做 post-turn 预热) |
| `sync_turn` | 4445-4597 | 转写本轮 transcript 为 batch,后台 writer 线程 POST(详见第七节) |
| `on_session_end` | 4599-4631 | drain writers(10s)→ commit(触发服务端 6 类记忆抽取) |
| `on_session_switch` | 4633-4721 | 旧会话异步 finalize + 会话状态轮换 + 压缩场景的 commit 守卫重臂 |
| `on_memory_write` | 4728-4765 | 内置 memory 工具 `add` 镜像为 `content/write`(仅 add) |
| `get_tool_schemas` | 4767-4775 | 6 个工具 |
| `handle_tool_call` | 4777-4796 | 分发 + `_ensure_client` 前置 + 异常转 `tool_error` |
| `shutdown` | 4798-4832 | 置 `_shutting_down`,join 四类线程各 5s,释放 run lock |
| `backup_paths` | 2162-2173 | 报出 ovcli.conf 路径供 `hermes backup` 捕获 |
| `get_config_schema`/`save_config`/`get_status_config`/`post_setup` | 2255-2493 | Dashboard/CLI 配置面(schema 含 8 个 recall_* 行为项;save_config 剥离 api_key 不落 config.yaml) |

未实现(用 ABC 默认 no-op):`on_turn_start`、`on_pre_compress`、`on_delegation`。注意 `plugin.yaml` 的 `hooks: [on_session_end]` 只是描述性元数据——加载器只读 `description`(`plugins/memory/__init__.py:166-176 @ 863e313`),hook 分发实际走 ABC 默认实现,与 yaml 无关。

---

## 五、prefetch 召回:纯语义检索 + 客户端重排 + 双预算

**召回不是向量/关键词混合——检索本身是服务端语义检索,客户端再做词面重排。** 整条管线:

**(1)会话首帧注入**(`_session_start_memory_context`,4001-4024):每个 session 只做一次(`_profile_prefetched_sessions` 集合去重),读三样东西:
- `viking://user/memories/profile.md` 全文(3818-3836,404/410 视为空、其他错误视为 None 即"整块跳过");
- `preferences/`、`entities/` 两个目录的**递归清单**(仅 `.md` 文件名 + 200 字 abstract,3838-3855、3731-3747);
- 用 token 预算(默认 6000)组装成 `<user-profile>` + `<available-memories>` 块。token 估算是"共享 OpenViking 契约"的字符启发式(CJK 每字 6 单位、其余 1 单位,4 单位=1 token;3749-3757),profile 超预算时头 8 行 + 尾部、中间打 `[profile middle elided]` 省略标记(3784-3816)。

**(2)语义检索**(`_search_prefetch_context`,3505-3573):query 短于 5 字符不搜(`_RECALL_QUERY_MIN_CHARS = 5`,92)。候选量 = `max(limit*4, 20)`(默认 limit=6 → 24);优先 POST `/api/v1/search/search`(带 `session_id` 的会话感知检索),失败降级 `/api/v1/search/find`(2944-2984)。注意发给服务端的是 `score_threshold: 0`——**阈值过滤全在客户端做**(2955-2960):

```python
        base_payload = {
            "query": query,
            "limit": limit,
            "score_threshold": 0,
            "context_type": context_type,
        }
```

`context_type` 默认只有 `"memory"`,开 `recall_resources` 才加 `"resource"`(3534-3536)。

**(3)客户端选择与重排**(`_select_recall_candidates`,4076-4103):URI 去重 + 语义键去重(`_dedupe_key`,4048-4057:非 events/cases 的条目按 `category+归一化 abstract` 去重——同义记忆合并;events/cases 按 URI,保留重复事件)+ 阈值过滤(默认 0.15)。排序分 = 服务端 score(截到 [0,1])+ 叶子加成 + 词面重叠加成(4068-4074):

```python
    @classmethod
    def _recall_rank(cls, item: Dict[str, Any], query_tokens: List[str]) -> float:
        text = f"{item.get('uri', '')} {cls._recall_abstract(item)}".lower()
        overlap = sum(1 for token in query_tokens if token in text)
        overlap_boost = min(0.2, overlap * 0.05)
        leaf_boost = 0.12 if item.get("level") == 2 else 0.0
        return cls._clamp_score(item.get("score")) + leaf_boost + overlap_boost
```

query 词取小写字母数字化后前 8 个、长度≥2(4060-4066)。取 top `limit`(默认 6)。

**(4)内容取材**(`_resolve_recall_content`,4117-4153):默认(`prefer_abstract=False`)对 level==2 的叶子或无摘要项做 L2 全文读(`/content/read`),但**全文读全局限额默认 2 次**(`recall_full_read_limit`),超限退回 abstract。

**(5)注入预算**(`_build_prefetch_entries`,4155-4192):逐条格式化为 `- [category] / <uri> / 内容缩进`,累计字符超 `recall_max_injected_chars`(默认 4000)则**跳过该条继续尝试后面更短的**(4188-4189 是 `continue` 不是 `break`)。

**(6)时间预算双层**:总 deadline(默认 4s)+ 单请求超时(默认 3s),每次请求前取 `min(单请求, 剩余)`,剩余 <0.05s 直接抛 `TimeoutError`(2937-2942)。这层在 provider 内部,外面还套着 MemoryManager 的 8s 围栏。

所有 8 个 recall 参数走 `config.yaml: memory.openviking.*` 为主、`OPENVIKING_RECALL_*` env 覆盖,非法值告警一次并回默认、再夹到 [min,max](3584-3710)。

**重实现要点**
- "服务端召回 + 客户端重排"分层:服务端只管召回率(阈值发 0),精度(阈值、去重、词面 boost、叶子偏好)全留在客户端,可调可测且不依赖服务端版本。
- 三种预算独立:条数(limit)、字符(max_injected_chars)、时间(deadline+per-request);昂贵操作(L2 全读)单独限额。
- 会话首帧的"profile 全文 + 目录索引"与逐轮的"query 相关召回"是两种注入,前者每会话一次、压缩后重新武装(见第八节)。

---

## 六、依赖处理与降级路径

- **embedding**:完全在服务端(ov.conf),插件无 auxiliary 路由、无本地模型。缺什么都不影响插件代码路径。
- **httpx 缺失**:`_VikingClient.__init__` 抛 ImportError(301-303),`initialize`/`_ensure_client` 捕获后 `self._client = None` 并 warning "httpx not installed — OpenViking plugin disabled"(2738-2740、2844-2847)——**插件静默降级为不可用,不炸 harness**。
- **server 不可达**:所有入口先过 `_ensure_client()`(2752-2771),不可用时 `system_prompt_block`/`prefetch`/`sync_turn` 返回空或直接 return,工具返回 `tool_error("OpenViking server not connected")`(4778-4779)。
- **本地端点自动拉起**:运行期发现本地端点(http + localhost/127.0.0.1/::1)不可达时,先 TCP 探测端口(2s 预算,1415-1427)——**端口被占只作为"不要 spawn"的信号,绝不当作"那就是 OpenViking"**(1487-1498 注释),否则才 `subprocess.Popen(["openviking-server","--host",host,"--port",port], start_new_session=True)` 后台拉起(1499-1521),再由 daemon waiter 线程轮询健康最长 60s 后 attach(2495-2591)。
- **失败冷却**:同一配置探测失败后 30s 内不再探测(`_FAILED_CONFIG_RETRY_COOLDOWN_SECONDS = 30.0`,143;2821-2832),防止 server 宕机期间每次 provider 访问都在 refresh 锁下付 3s 探测。
- **配置热更**:`/reload` 只刷 env 不重建 provider,所以 `_ensure_client` 每次访问重解析配置链(env → ovcli → config.yaml → 默认),只有值变了才重建+健康检查,热路径是一次 dict 比较(2752-2764 注释,溯源 #21130)。

**重实现要点**
- 外部后端的每个入口都要有"不可用 → 空产出"的统一降级门;把"重连"做成按访问惰性触发 + 失败冷却,而不是后台心跳。
- 自动拉起本地进程时,"端口开着"与"服务健康"必须是两个独立判定。

---

## 七、并发模型:锁、writer 池、commit 守卫

provider 自己维护 **7 把锁 + 4 类线程**(`__init__`,2175-2232):

- `_session_state_lock`:守 `(_session_id, _turn_count)` 对。`sync_turn` 在锁内"快照 sid + 自增计数"(4499-4503),`on_session_end`/`on_session_switch` 在锁内"快照+重置",保证一轮要么整体记在旧会话、要么整体记在新会话(溯源 #28296 review)。
- `_inflight_writers: Dict[sid, Set[Thread]]` + `_inflight_lock`:**按 sid 跟踪全部在途 writer**,而非只留最后一个(2990-3014 `_spawn_writer`);commit 前 `_drain_writers(sid, timeout)` 把该 sid 的 writer 全部 join(3040-3061)。为什么按 sid 集合:一个被丢跟踪的旧 writer 仍在向旧 sid POST,若 commit 不等它,写入会落在 commit 边界之后、永远不被抽取(测试文件 1066-1071 注释)。
- `_client_refresh_lock`:连接设置与 client 是"一个发布状态",refresh 串行化;另有 `_conn_snapshot` 元组——**健康检查通过后一次性原子发布**(CPython 引用赋值原子),后台 writer 无锁 `_new_client()` 时整元组读取,不会看到"新 endpoint + 旧 api_key"的撕裂组合(2214-2218、3063-3082)。
- `_deferred_commit_sids/_threads + lock`:switch 路径的 finalize(drain+GET+commit,可能数秒)全部下放 daemon 线程,按 sid 去重防止快速二连 switch 叠两个 finalizer(3456-3503)。
- `_committed_session_lock` + `_committed_session_ids`:**commit 守卫**。已 commit 的 sid 永不二次 commit——且这个判定必须先于 turn_count 检查,因为竞态的 sync_turn 可能在 commit+reset 后又把计数加回去(3421-3429):

```python
    def _session_needs_commit(self, sid: str, turn_count: int) -> bool:
        # Already-committed sessions never need a second commit, regardless of
        # the turn counter — a racing sync_turn can re-increment _turn_count
        # after a commit+reset, so the committed-guard must win over turn_count.
        if self._has_committed_session(sid):
            return False
        if turn_count > 0:
            return True
        return self._session_has_pending_tokens(sid)
```

  turn_count==0 时还会问服务端 `pending_tokens`(3114-3125)兜住"本进程没记到但服务端有存量"的情况。
- 压缩特例(#74695):**原地压缩保持同一 sid**,压缩时的 commit 会把守卫锁死,导致这个还活着的会话后续所有 commit 都被拒——所以 `on_session_switch(reason="compression")` 且未轮换时调 `_clear_session_committed` 重新武装守卫(3135-3145、4691-4703),同时清 `_profile_prefetched_sessions` 让 profile 重新注入(4683-4689)。轮换式压缩则保持旧 sid 锁死(正好用来去重它的异步 finalizer)。
- `shutdown`(4798-4832):置 `_shutting_down` 停新写,依次 join 在途 writer / deferred finalizer / memory-write 镜像线程 / runtime-start waiter 各 5s——注释点名不 join waiter 会在解释器退出时 SIGABRT(Py_FinalizeEx)。

**重实现要点**
- "commit 是屏障"是全部并发设计的根:先 drain 该会话全部在途写、再 commit;守卫防重复;守卫必须能对"同 id 继续活着"的会话重臂。
- 无锁读端用"单元组原子发布"代替细粒度字段读,是 CPython 下最便宜的一致性快照手段。

---

## 八、持久化与崩溃恢复:run lock + pending markers + atexit

**问题**:commit 才触发服务端记忆抽取;进程崩溃/被杀时未 commit 的会话就永远不被抽取。三层防线:

1. **atexit 安全网**(250-271):模块级 `_last_active_provider`,进程退出时补一次 `on_session_end([])` 并释放 run lock;`shutdown` 正常走完会把引用清掉防止双 commit(4829-4831)。
2. **pending marker**(3310-3340):第一次 `sync_turn` 时向 `pending_sessions/<urlencoded-sid>.json` 原子写 `{"session_id", "owner_run_id"}`(0600);commit 成功即删。**没拿到 run lock 就不写 marker**(3318-3320)——防止无主 marker 被别的进程误恢复。
3. **启动恢复**(3362-3419):`initialize` attach 成功后扫描 marker,按 owner_run_id 分组;对每组先 `flock` 抢占**死主人的 run lock 文件**(非阻塞,抢不到说明主人还活着,跳过;3230-3279),抢到才起 daemon 线程逐个 `_commit_session(..., clear_missing=True)`——404 视为会话已不存在、只删 marker(3448-3452)。run lock 本体:`runs/<run_id>.lock` 上的 `fcntl.flock(LOCK_EX|LOCK_NB)`(3180-3207);无 fcntl 平台(Windows)禁用锁,只允许恢复"legacy 无主 marker"(3237-3243)。

配套的两处文件写入防护也值得记:`.env` 写入时 `_env_line_safe` 剥掉 CR/LF/NUL,防止带换行的"api_key"注入额外 KEY=VALUE 行(1169-1183);secret 文件先 0600 预创建再写,消除 umask 窗口(1146-1166);ovcli.conf 用 `atomic_json_write(..., mode=0o600)`(1238-1243)。

**重实现要点**
- 崩溃恢复 = "持久化意图(marker)+ 所有权(per-run flock)+ 幂等重放(commit 守卫 + 404 清理)"三件套;marker 必须绑定 owner,恢复必须先夺取死者的锁,否则共享 HOME 的多进程会互相抢救活人。

---

## 九、sync_turn:transcript 转写与三级降级

`sync_turn`(4445-4597)不是简单存两段文本:
1. 剥 skill 脚手架(4457,双保险——manager 已剥过,注释 220-230 说明这是防"钩子被绕过 manager 调用");user 文本为空直接不记。
2. `_extract_current_turn_messages`(4207-4258):从完整 canonical transcript 里**从尾部锚定**本轮——先找文本匹配 assistant_content 的最后一条 assistant,再向前找匹配 user_content 的 user;匹配不到就退化为"最后一条 assistant/user"。
3. `_messages_to_openviking_batch`(4326-4443):转成 OpenViking 消息格式。要点:system/developer 丢弃;tool 结果聚合成 assistant 消息里的 `type:"tool"` parts(带 tool_id/name/input/output/status,status 经别名表归一化,4299-4324 还会解析 JSON body 里的 `success:false`/`exit_code!=0` 判 error);**召回类工具(viking_search/read/browse)整体剔除**——注释点名"把召回结果回灌进会话再存储会造成记忆自我复制"(635-643);assistant 上未完成的 tool_calls 记为 `pending`。
4. 发送三级降级(4507-4596):batch 端点按 100 条分片 POST → 首片失败降级为"文本双消息"(user/assistant 各截 4000 字)→ 整体失败重建 client 重试一次 → 重试仍失败且有部分已发,**逐条补发未发消息**(避免重发已收下的分片造成重复)。
5. 全程在 `_spawn_writer` 的 daemon 线程上,主线程只做锁内计数与 marker。

**重实现要点**
- 存储转写要做"防回声"过滤:凡是从记忆系统读出来的内容,不得再写回记忆系统。
- 分片上传的失败恢复要记录"已发到哪",降级路径按"最保真 → 最保底"排列且互不重复发送。

---

## 十、工具面(6 个)与安全边界

- `viking_search`(4876-4918):`mode=="deep"` 走 `/search/search`(带 session_id),否则 `/search/find`;结果跨 memories/resources/skills 三桶按原始 score 统一排序,附 relations 前 3 条。
- `viking_read`(4995-5055):单 URI 或 ≤3 个批量(`_READ_BATCH_LIMIT=3`);abstract/overview 是**目录级端点**,伪摘要文件名(`.abstract.md` 等)映射回父目录(4843-4851),真文件先 `fs/stat` 探测、file 直接走 `/content/read` 免一次注定失败的往返(4920-4961);批量 full 每条截 2500 字;按档位截断(full 8000 / overview 4000 / abstract 1200)。
- `viking_browse`(5057-5087):tree/ls/stat 映射到 `fs/*`,列表规范化并截 50 条。
- `viking_remember`(5089-5114):`content/write mode=create` 直写 `viking://user/peers/<agent>/memories/<subdir>/mem_<12hex>.md`,category→子目录映射(108-115),**不依赖 commit 抽取**。
- `viking_forget`(5116-5139):删除前过 `_validate_forget_memory_uri`(704-729)白名单:必须 viking:// 且 `.md` 结尾、无 query/fragment、路径落在四种 user memories 形态之一(692-701,兼容 API-key 模式的 `user/<acct>/...` 规范形)、拒绝 `.abstract.md/.overview.md` 生成物;删除带 `recursive: False`。
- `viking_add_resource`(5141-5203):远程 URL 直接提交;本地文件先过 `raise_if_read_blocked`(凭据文件防护),目录打 zip 时逐文件跳 symlink、跳逃出根的 resolve、跳被 read-block 的文件(654-676),经 `temp_upload` 换 temp_file_id 再 POST `/resources`。

**重实现要点**
- 删除类工具做成"精确 URI 白名单 + 显式拒绝所有宽泛形态";上传类工具复用 harness 的文件读黑名单,记忆后端不能成为凭据外传旁路。

---

## 十一、openviking README vs 代码对照(逐条)

| # | README 断言 | 代码事实 | 定案 |
|---|---|---|---|
| 1 | `README.md:10-11`:"OpenViking server running and reachable from Hermes"(前置要求) | 本地端点不可达时运行期自动 `Popen` 拉起 server 并后台等待 attach(`__init__.py:1482-1521, 2593-2657`) | ◇ README 偏保守:本地场景无需手动先跑 server |
| 2 | `README.md:12-16`:0.2.10+ 推荐;legacy 仅在匿名 OpenAPI 也验明时接受 | `_probe_openviking_identity`(947-964)与 `_LEGACY_OPENVIKING_IDENTITY_DETAIL`(155-159)完全一致 | ✓ |
| 3 | `README.md:34-36`:setup 可"link 现有 ovcli.conf、**copy 其连接值进 Hermes**、或新建" | 现有 profile 只有 link 路径(`_run_existing_profile_setup` 2003-2064 只调 `_link_ovcli_profile`);"copy into Hermes"仅存在于**新建**流程的 "Keep in Hermes only"(2115-2152);新建的 ovcli 是 `ovcli.conf.<name>` 存档而非激活的 `ovcli.conf` | ▲ "copy 现有 profile 值"路径在 863e313 不存在 |
| 4 | `README.md:70-80`:5 个 env 变量表 + API-key 模式省略租户头 | `_headers`(305-320)+ `_resolve_connection_settings`(1089-1127)一致 | ✓;但表**不含** `get_config_schema` 另暴露的 8 个 `OPENVIKING_RECALL_*`/`OPENVIKING_PROFILE_TOKEN_BUDGET`(2293-2371) → ◇ README 配置表不完整 |
| 5 | `README.md:86`:`viking_search` "fast/deep/auto modes" | 代码只有两种行为:`endpoint = "/api/v1/search/search" if mode == "deep" else "/api/v1/search/find"`(4888)——auto ≡ fast | ▲ "auto" 无独立行为,仅是 schema 枚举默认值 |
| 6 | `README.md:95-100`:remember 用 `content/write mode=create`,peer 域 URI,API-key 模式可能返回 user-scoped 规范形 | `_tool_remember`(5102-5106)、`_build_memory_uri`(4723-4726)一致;forget 校验兼容规范形(697-700) | ✓ |
| 7 | `README.md:105-112`:仅 `add` 镜像;replace/remove 不镜像(无稳定 URI) | `on_memory_write`:`if action != "add" or not content ...: return`(4736) | ✓ |
| 8 | `README.md:114-122`:forget 只收具体 .md 用户记忆 URI,`memories/` 直下文件亦可,拒目录/资源/生成摘要/query | `_validate_forget_memory_uri`(704-729):`user/<acct>/memories/profile.md` → parts 长度 4 ≥ idx(2)+2 通过;`.abstract.md/.overview.md` 拒绝 | ✓ |
| 9 | 模块 docstring `__init__.py:19-20`:"Automatic memory extraction on session commit (6 categories)" | commit 调用(3439-3443)+ `on_session_end` docstring(4600-4604)列 profile/preferences/entities/events/cases/patterns;抽取本体在服务端,插件侧不可验证类别数 | ◇ 服务端承诺,插件仅触发 |

---

## 十二、byterover:CLI 包装型后端

**它是什么**:ByteRover 是商业记忆服务(byterover.dev),形态是本地 CLI `brv`(npm/curl 安装),本地维护"层级上下文树"、可选云同步。插件是**子进程包装器**:所有操作都是 `subprocess.run([brv, ...])`,Hermes 不接触其存储格式。`plugins/memory/byterover/__init__.py:1-20 @ 863e313`:

```python
"""ByteRover memory plugin — MemoryProvider interface.

Persistent memory via the ByteRover CLI (``brv``). Organizes knowledge into
a hierarchical context tree with tiered retrieval (fuzzy text → LLM-driven
search). Local-first with optional cloud sync.
...
Working directory: $HERMES_HOME/byterover/ (profile-scoped context tree)
"""
```

**二进制解析**(99-123):`shutil.which("brv")` → 失败探 `~/.brv-cli/bin/brv`、`/usr/local/bin/brv`、`~/.npm-global/bin/brv` 三个已知位置;结果双检锁缓存;运行时 FileNotFoundError 会重置缓存(157-160)。**执行**(126-162):`cwd=$HERMES_HOME/byterover/`(profile 域上下文树,165-168),brv 所在目录注入子进程 PATH 头部(138-139),`--` 分隔防参数注入,超时 query 10s / curate 120s / status 15s(40-41、437)。

**认证方式**:插件从不读取 `BRV_API_KEY`——仅经 `env = os.environ.copy()`(137)透传给 brv 子进程,云同步认证完全由 CLI 自理;`get_config_schema` 声明该 env var 供 setup 写入 `.env`(241-247)。

**ABC 映射**:

| 方法 | 位置 | 行为 |
|---|---|---|
| `is_available` | 235-237 | brv 在不在,零网络 |
| `initialize` | 256-260 | 记 cwd/sid/计数,mkdir 工作目录 |
| `system_prompt_block` | 262-270 | 固定三句话(brv 在才注入) |
| `prefetch` | 272-288 | **同步阻塞** `brv query`(query <10 字符跳过,输出 ≤20 字符丢弃,截 5000 入参);注意其 10s 内部超时 > manager 的 8s 围栏(`agent/memory_manager.py:47`),实际由围栏先掐 |
| `queue_prefetch` | 290-292 | no-op |
| `sync_turn` | 294-322 | `auto_extract`(默认 true,224-225)才执行;user 内容 <10 字符跳过;拼 `User:.../Assistant:...` 各截 2000 字后台 `brv curate`;新线程启动前 join 旧线程最多 5s(316-317)——**join 超时也照样覆盖引用继续**,旧线程失去跟踪 |
| `on_memory_write` | 324-343 | add/replace 镜像为 `brv curate "[User profile|Agent memory] ..."`;线程 fire-and-forget 不跟踪;签名无 `metadata` → manager 签名嗅探后按 3 参调用(`agent/memory_manager.py:997-1010`) |
| `on_pre_compress` | 345-378 | 压缩前取将被丢弃消息的**最后 10 条**、每条截 500 字,后台 curate 一条 `[Pre-compression context]`;返回 ""(不注入摘要);fire-and-forget |
| `get_tool_schemas` | 380-381 | brv_query / brv_curate / brv_status |
| `handle_tool_call` | 383-390 | 三工具分发;query 结果截 8000 字 |
| `shutdown` | 392-394 | 仅 join 当前 `_sync_thread` 10s;memwrite/flush 线程不等 |

未实现:`on_session_end`、`on_session_switch`(会话轮换对它无意义——没有会话概念,curate 即时入库);`sync_turn` 无 `messages` 参数 → manager 嗅探后只传两段文本(`agent/memory_manager.py:628-636`)。

**失败方向**:一切失败都收敛成 `{"success": False, "error": ...}`(126-162)——CLI 缺失、超时、非零退出码;prefetch/sync 静默降级,工具面转 `tool_error`。没有重试、没有健康检查、没有崩溃恢复:curate 丢了就丢了(与 openviking 的 commit-屏障哲学形成两极)。

**重实现要点**
- CLI 包装型后端的最小闭环:二进制发现(缓存+失效重置)、`--` 参数隔离、固定 cwd 作数据域、超时分级、错误归一。
- 它示范了 ABC 的"最小实现面":不实现的钩子交给基类 no-op,manager 靠签名嗅探兼容旧签名——provider 接口演进不破坏旧插件。
- 反面教材两处:join 超时后仍覆盖线程引用(丢跟踪,openviking 用按 sid 集合解决的正是这个问题);shutdown 不等 memwrite/flush 线程(退出时可能丢写)。

---

## 十三、byterover README vs 代码对照(逐条)

| # | README 断言 | 代码事实 | 定案 |
|---|---|---|---|
| 1 | `README.md:3`:"hierarchical knowledge tree with tiered retrieval (fuzzy text → LLM-driven search)" | 插件仅调 `brv query/curate/status`,树与分级检索是 brv 内部实现,本仓不可验证 | ◇ 外部承诺,插件侧无对应代码 |
| 2 | `README.md:7-12`:两种安装方式 | 与 `plugin.yaml` `external_dependencies`(install/check 命令)及模块 docstring(9-10)一致;`hermes memory setup` 会跑 `brv --version` check 失败时提示安装命令(`hermes_cli/memory_setup.py:189-202`) | ✓ |
| 3 | `README.md:29-31`:配置表仅 `BRV_API_KEY`(可选) | 代码还有 `auto_extract`(config.yaml `memory.byterover.auto_extract`,默认 true,224-225;schema 249-254;另接受 legacy `memory.provider_config`,83-85) | ◇ README 配置表缺 `auto_extract`;模块 docstring(15-18)有 |
| 4 | `README.md:24`:`BRV_API_KEY` 写入 `~/.hermes/.env` 即生效 | 插件不读该变量,靠 `os.environ.copy()` 透传(137);生效前提是 env 已加载进进程 | ✓(机制是透传而非插件消费) |
| 5 | `README.md:33`:工作目录 `$HERMES_HOME/byterover/` | `_get_brv_cwd`(165-168)一致,`_run_brv` 每次 mkdir(135) | ✓ |
| 6 | `README.md:37-41`:三工具表 | `get_tool_schemas`(380-381)一致 | ✓ |
| 7 | `plugin.yaml` `hooks: [on_pre_compress]` | 代码实际还实现 `on_memory_write`;该字段本就不参与分发(加载器只读 description) | ◇ 元数据不完整且无害 |

---

## 十四、配套测试与行为规格

**测试文件清单**:
- `/home/user/hermes-agent/tests/openviking_plugin/test_openviking.py`(1289 行):URI 归一化、skill 脚手架安全、recall 配置解析(config.yaml/env 覆盖/坏值回退)、transcript 转写、read/browse 形态、召回 e2e、`_ensure_client` 重建/并发/冷却、不可用告警文案。
- `/home/user/hermes-agent/tests/plugins/memory/test_openviking_provider.py`(1611 行):配置链、ovcli profile 发现与 link、setup 交互流、本地 server 拉起守卫、身份探测匿名性、会话轮换/commit 守卫/压缩重臂、并发恢复抢锁、shutdown 等待。
- `/home/user/hermes-agent/tests/plugins/memory/test_openviking_endpoint_always_blocked.py`(68 行):SSRF 底线(metadata 端点拒绝、loopback 保留、缓存)。
- `/home/user/hermes-agent/tests/plugins/memory/test_openviking_shutdown.py`(72 行):health 等待的 should_stop 短路、shutdown join runtime-start 线程。
- `/home/user/hermes-agent/tests/plugins/memory/test_byterover_provider.py`(18 行):仅 1 个测试。

**行为规格 1(openviking 召回全链路)**:`tests/openviking_plugin/test_openviking.py:637-783 @ 863e313` `test_prefetch_e2e_sends_limit_and_reads_l2_content`。起一个真 HTTPServer 假扮 OpenViking(modern health、profile.md、preferences/entities 目录、search 返回一条 level=2 score=0.9 的记忆),对 `prefetch("What should we recall?")` 断言:注入块以 `## OpenViking Context` 开头且同时含 profile 全文、两个目录清单行(`owner/answers.md — Prefers source-backed answers.`)、**L2 全文而非 abstract**(758:`"E2E abstract should not be injected." not in block`);线上契约逐字段锁死——search 只发一次、`limit==24`(6×4)、`score_threshold==0`、`session_id` 透传、**无** `top_k`/`mode` 字段(773-774,契约防漂移),目录列表带 `output=agent&recursive=true&abs_limit=512&node_limit=512`,且无 key 模式下每个请求都带三张身份头。这份测试就是第五节整条管线的可执行规格。

**行为规格 2(commit 守卫次序)**:`tests/plugins/memory/test_openviking_provider.py:1032-1045 @ 863e313` `test_session_needs_commit_guard_wins_over_stale_turn_count`。规格:对已 `_mark_session_committed` 的 sid,即使 turn_count 仍为 5,`_session_needs_commit` 必须为 False(committed 判定先于 turn_count>0 捷径)——否则竞态 sync_turn 在 commit+reset 后重新加计数会引发同会话双 commit(#28296 M3 回归)。

**行为规格(byterover)**:`tests/plugins/memory/test_byterover_provider.py:6-16 @ 863e313` `test_auto_extract_false_skips_sync_turn`——`auto_extract: False` 时 `sync_turn` 不得调 `_run_brv` 且不得创建 `_sync_thread`(配置闸门在计数自增之后、线程创建之前生效)。byterover 测试面仅此一处,并发缺陷(join 超时覆盖引用、shutdown 不等镜像线程)无规格覆盖。

---

## 十五、两家对照总结(可迁移结论)

| 维度 | openviking | byterover |
|---|---|---|
| 形态 | REST 客户端 → 常驻服务(本地/云) | 子进程包装 → 本地 CLI(可云同步) |
| 记忆写入 | 会话流式上传 + commit 触发服务端抽取;工具直写旁路 | 每轮直接 `curate`(即时抽取),无会话概念 |
| 召回 | 服务端语义检索 + 客户端重排/预算/分档读 | CLI 原样输出 + 长度闸门 |
| 一致性 | commit 屏障 + drain + 守卫 + marker 恢复 | 尽力而为,丢了就丢 |
| 会话生命周期 | end/switch/压缩全接 | 全不接(仅 pre_compress 抢救) |
| 降级 | 健康状态机 + 冷却 + 本地自动拉起 | error dict 静默吞 |
| 代码量 | 5212 行(≈40% 是连接治理) | 449 行 |

设计上二者是同一 ABC 的两个极端:byterover 展示"最小可用 provider"(约 200 行核心即可挂进 harness),openviking 展示"生产级 provider"必须补齐的全部暗面——连接热更、身份验明、SSRF 底线、写后 commit 一致性、崩溃恢复、进程生命周期。harness 侧的围栏(8s prefetch fence、逐 provider 异常吞掉、签名嗅探)使两个极端都能安全共存。