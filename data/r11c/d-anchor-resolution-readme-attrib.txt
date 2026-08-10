
########## notes/r6-20-openviking-byterover.md
   32 [## 一、OpenViking:它是什么、存储在哪、什么形态]
      笔记: 数据模型是**文件系统层级 + 三级摘要**:一切内容是 `viking://` URI 下的"文件/目录",每个节点有 L0 abstract(约 100 token)、L1 overview(约 2k token)、L2 全文三个读取档位(`README_SCHEMA` 描述,`__init__
      openviking   - `ov.conf` configures OpenViking storage, embedding/VLM models, auth, and
      byterover    <越界 共41行>
  285 [## 十一、openviking README vs 代码对照(逐条)]
      笔记: | 1 | `README.md:10-11`:"OpenViking server running and reachable from Hermes"(前置要求) | 本地端点不可达时运行期自动 `Popen` 拉起 server 并后台等待 attach(`__init__.py:1482-1
      openviking   - OpenViking server running and reachable from Hermes
      byterover    # or
  286 [## 十一、openviking README vs 代码对照(逐条)]
      笔记: | 2 | `README.md:12-16`:0.2.10+ 推荐;legacy 仅在匿名 OpenAPI 也验明时接受 | `_probe_openviking_identity`(947-964)与 `_LEGACY_OPENVIKING_IDENTITY_DETAIL`(155-159)完全
      openviking   OpenViking 0.2.10 or newer is recommended. For backward compatibility,
      byterover    ```
  287 [## 十一、openviking README vs 代码对照(逐条)]
      笔记: | 3 | `README.md:34-36`:setup 可"link 现有 ovcli.conf、**copy 其连接值进 Hermes**、或新建" | 现有 profile 只有 link 路径(`_run_existing_profile_setup` 2003-2064 只调 `_lin
      openviking   The setup can link to an existing `~/.openviking/ovcli.conf`, copy its current
      byterover    
  288 [## 十一、openviking README vs 代码对照(逐条)]
      笔记: | 4 | `README.md:70-80`:5 个 env 变量表 + API-key 模式省略租户头 | `_headers`(305-320)+ `_resolve_connection_settings`(1089-1127)一致 | ✓;但表**不含** `get_config_sche
      openviking   | Env Var | Default | Description |
      byterover    <越界 共41行>
  289 [## 十一、openviking README vs 代码对照(逐条)]
      笔记: | 5 | `README.md:86`:`viking_search` "fast/deep/auto modes" | 代码只有两种行为:`endpoint = "/api/v1/search/search" if mode == "deep" else "/api/v1/search/find
      openviking   | `viking_search` | Semantic search with fast/deep/auto modes |
      byterover    <越界 共41行>
  290 [## 十一、openviking README vs 代码对照(逐条)]
      笔记: | 6 | `README.md:95-100`:remember 用 `content/write mode=create`,peer 域 URI,API-key 模式可能返回 user-scoped 规范形 | `_tool_remember`(5102-5106)、`_build_memory
      openviking   `viking_remember` writes directly to OpenViking with `POST /api/v1/content/write`
      byterover    <越界 共41行>
  291 [## 十一、openviking README vs 代码对照(逐条)]
      笔记: | 7 | `README.md:105-112`:仅 `add` 镜像;replace/remove 不镜像(无稳定 URI) | `on_memory_write`:`if action != "add" or not content ...: return`(4736) | ✓ |
      openviking   | Hermes action | OpenViking operation |
      byterover    <越界 共41行>
  292 [## 十一、openviking README vs 代码对照(逐条)]
      笔记: | 8 | `README.md:114-122`:forget 只收具体 .md 用户记忆 URI,`memories/` 直下文件亦可,拒目录/资源/生成摘要/query | `_validate_forget_memory_uri`(704-729):`user/<acct>/memories
      openviking   `viking_forget` is intentionally narrow. It only accepts concrete user memory
      byterover    <越界 共41行>
  347 [## 十三、byterover README vs 代码对照(逐条)]
      笔记: | 1 | `README.md:3`:"hierarchical knowledge tree with tiered retrieval (fuzzy text → LLM-driven search)" | 插件仅调 `brv query/curate/status`,树与分级检索是 brv 
      openviking   Context database by Volcengine (ByteDance) with filesystem-style knowledge hierarchy, tiered retrieval, and automatic memory extra
      byterover    Persistent memory via the `brv` CLI — hierarchical knowledge tree with tiered retrieval (fuzzy text → LLM-driven search).
  348 [## 十三、byterover README vs 代码对照(逐条)]
      笔记: | 2 | `README.md:7-12`:两种安装方式 | 与 `plugin.yaml` `external_dependencies`(install/check 命令)及模块 docstring(9-10)一致;`hermes memory setup` 会跑 `brv --version
      openviking   - OpenViking installed with the `openviking-server` command available
      byterover    Install the ByteRover CLI:
  349 [## 十三、byterover README vs 代码对照(逐条)]
      笔记: | 3 | `README.md:29-31`:配置表仅 `BRV_API_KEY`(可选) | 代码还有 `auto_extract`(config.yaml `memory.byterover.auto_extract`,默认 true,224-225;schema 249-254;另接受 le
      openviking   
      byterover    | Env Var | Required | Description |
  350 [## 十三、byterover README vs 代码对照(逐条)]
      笔记: | 4 | `README.md:24`:`BRV_API_KEY` 写入 `~/.hermes/.env` 即生效 | 插件不读该变量,靠 `os.environ.copy()` 透传(137);生效前提是 env 已加载进进程 | ✓(机制是透传而非插件消费) |
      openviking   openviking-server doctor
      byterover    echo "BRV_API_KEY=your-key" >> ~/.hermes/.env
  351 [## 十三、byterover README vs 代码对照(逐条)]
      笔记: | 5 | `README.md:33`:工作目录 `$HERMES_HOME/byterover/` | `_get_brv_cwd`(165-168)一致,`_run_brv` 每次 mkdir(135) | ✓ |
      openviking   
      byterover    Working directory: `$HERMES_HOME/byterover/` (profile-scoped).
  352 [## 十三、byterover README vs 代码对照(逐条)]
      笔记: | 6 | `README.md:37-41`:三工具表 | `get_tool_schemas`(380-381)一致 | ✓ |
      openviking   
      byterover    | Tool | Description |

########## notes/r6-30-hindsight-supermemory-retaindb.md
  295 [### 1.10 README vs 代码对照(hindsight)]
      笔记: | 1 | `README.md:49`"Config file: `~/.hermes/hindsight/config.json`" | `__init__.py:364-367` 还有第 2 级 legacy 回退 `~/.hindsight/config.json` 与第 3 级 env,R
      hindsight    Config file: `~/.hermes/hindsight/config.json`
      supermemory  | `base_url` | `https://api.supermemory.ai` | API endpoint for hosted or self-hosted Supermemory. Takes priority over `SUPERMEMORY
      retaindb     <越界 共40行>
  296 [### 1.10 README vs 代码对照(hindsight)]
      笔记: | 2 | `README.md:133-143` 环境变量表只列 7 个 | 模块 docstring `__init__.py:12-25` 另有 `HINDSIGHT_TIMEOUT` / `HINDSIGHT_IDLE_TIMEOUT` / `HINDSIGHT_EMBED_PORT_HEA
      hindsight    ## Environment Variables
      supermemory  
      retaindb     <越界 共40行>
  297 [### 1.10 README vs 代码对照(hindsight)]
      笔记: | 3 | `README.md:31`"stops after 5 minutes of inactivity" | `__init__.py:61` `_DEFAULT_IDLE_TIMEOUT = 300` | ✓ |
      hindsight    Hermes spins up a local Hindsight daemon with built-in PostgreSQL. Requires an LLM API key for memory extraction and synthesis. Th
      supermemory  Before running `hermes memory setup`, add the local endpoint to
      retaindb     
  298 [### 1.10 README vs 代码对照(hindsight)]
      笔记: | 4 | `README.md:147`"auto-upgrades on session start" | `__init__.py:1466-1487` initialize 里检版本、`install_specs` 升级 | ✓ |
      hindsight    Requires `hindsight-client >= 0.6.1`. The plugin auto-upgrades on session start if an older version is detected.
      supermemory  <越界 共138行>
      retaindb     <越界 共40行>
  299 [### 1.10 README vs 代码对照(hindsight)]
      笔记: | 5 | `README.md:67-100` 配置表 | 缺 `timeout`/`idle_timeout`/`port_health_grace_timeout`/`observation_scopes`/`prefetch_waits_for_retain`/`prefetch_retai
      hindsight    ### Recall
      supermemory  
      retaindb     <越界 共40行>
  300 [### 1.10 README vs 代码对照(hindsight)]
      笔记: | 6 | `README.md:78-87` recall_types 默认 observation-only、工具与自动召回共用同一设置 | `__init__.py:793`、`1771-1772`(prefetch)与 `2005-2006`(工具)同读 `self._recall_type
      hindsight    | `recall_types` | `observation` | Fact types surfaced by recall (both auto-recall and the `hindsight_recall` tool). Comma-separat
      supermemory  | `supermemory-save` | `supermemory_store` | Store an explicit memory |
      retaindb     <越界 共40行>
  423 [### 2.7 README vs 代码对照(supermemory)]
      笔记: | 1 | `README.md:55` `capture_mode` 默认 `all`,"Skip tiny or trivial turns by default" | `_capture_mode` 被加载(`__init__.py:672`)但**全文件无任何使用点**;`_is_trivi
      hindsight    | `mode` | `cloud` | `cloud`, `local_embedded`, or `local_external` |
      supermemory  | `capture_mode` | `all` | Skip tiny or trivial turns by default |
      retaindb     <越界 共40行>
  424 [### 2.7 README vs 代码对照(supermemory)]
      笔记: | 2 | `README.md:58` `api_timeout`"Timeout for SDK and ingest requests" | SDK 用原值(305),ingest 用 `timeout + 3`(417) | ▲ 细节不符(ingest 实为 +3s) |
      hindsight    ### Memory Bank
      supermemory  | `api_timeout` | `5.0` | Timeout for SDK and ingest requests |
      retaindb     <越界 共40行>
  425 [### 2.7 README vs 代码对照(supermemory)]
      笔记: | 3 | `README.md:49` base_url 优先级 config > env > 默认 | `_resolve_base_url`(82-91)完全一致 | ✓ |
      hindsight    Config file: `~/.hermes/hindsight/config.json`
      supermemory  | `base_url` | `https://api.supermemory.ai` | API endpoint for hosted or self-hosted Supermemory. Takes priority over `SUPERMEMORY
      retaindb     <越界 共40行>
  426 [### 2.7 README vs 代码对照(supermemory)]
      笔记: | 4 | `README.md:74`"Kebab-case names are registered for the agent; snake_case aliases remain supported" | `with_kebab_aliases`(905-920)把两套名字**都**作为完整
      hindsight    | `recall_max_input_chars` | `800` | Maximum input query length for auto-recall |
      supermemory  Kebab-case names are registered for the agent; snake_case aliases remain supported.
      retaindb     <越界 共40行>
  427 [### 2.7 README vs 代码对照(supermemory)]
      笔记: | 5 | `README.md:85-89` `x-sm-source: hermes` + `metadata.sm_source` 是功能性路由非遥测 | `default_headers`(307)、`_merge_metadata`(310-318)注释同文 | ✓ |
      hindsight    > Per [Hindsight's docs](https://hindsight.vectorize.io/developer/observations), observations are the **consolidated** knowledge l
      supermemory  All Supermemory API calls send `x-sm-source: hermes`, and document writes stamp
      retaindb     <越界 共40行>
  428 [### 2.7 README vs 代码对照(supermemory)]
      笔记: | 6 | `README.md:129-132` 多容器:工具收 `container_tag`、必须在白名单、自动操作只用主容器 | `_resolve_tool_container_tag`(884-902)白名单校验;自动路径(prefetch/sync/ingest/on_memory_w
      hindsight    | `hindsight_retain` | Store information with auto entity extraction; supports optional per-call `tags` |
      supermemory  - `supermemory-search`, `supermemory-save`, `supermemory-forget`, and `supermemory-profile` accept an optional `container_tag` par
      retaindb     <越界 共40行>
  429 [### 2.7 README vs 代码对照(supermemory)]
      笔记: | 7 | `README.md:96`"(or on /reset, branch, compression, or shutdown)" | on_session_switch(785)+ shutdown(852)均 flush;shutdown 注释自称 "Emergency fallbac
      hindsight    | `retain_context` | `conversation between Hermes Agent and the User` | Context label for retained memories |
      supermemory  - buffer the full conversation and ingest it as **one session** at session end (or on `/reset`, branch, compression, or shutdown)
      retaindb     <越界 共40行>
  558 [### 3.7 README vs 代码对照(retaindb)]
      笔记: | 1 | `README.md:24`"All config via environment variables in `.env`" | `_load_retaindb_config`(47-63)还读 config.yaml 的 `memory.retaindb` 块(Dashboard 写入
      hindsight    
      supermemory  For a fully self-hosted setup, start Supermemory local and note the API key it
      retaindb     All config via environment variables in `.env`:
  559 [### 3.7 README vs 代码对照(retaindb)]
      笔记: | 2 | `README.md:33-40` 工具表 5 个 | `get_tool_schemas`(677-683)注册 **10 个**(另有 upload/list/read/ingest/delete 文件工具,schema 136-198) | ▲ README 漏掉整个文件工具族 |
      hindsight    Supports any OpenAI-compatible LLM endpoint (llama.cpp, vLLM, LM Studio, etc.) — pick `openai_compatible` as the provider and ente
      supermemory  
      retaindb     
  560 [### 3.7 README vs 代码对照(retaindb)]
      笔记: | 3 | `README.md:3`"7 memory types" | REMEMBER_SCHEMA enum 只有 6 个:`["factual", "preference", "goal", "instruction", "event", "opinion"]`(113-117) | ▲ 
      hindsight    Long-term memory with knowledge graph, entity resolution, and multi-strategy retrieval. Supports cloud, local embedded, and local 
      supermemory  Semantic long-term memory with profile recall, semantic search, explicit memory tools, and full-session conversation ingest (one i
      retaindb     Cloud memory API with hybrid search (Vector + BM25 + Reranking) and 7 memory types.
  561 [### 3.7 README vs 代码对照(retaindb)]
      笔记: | 4 | `README.md:3`"hybrid search (Vector + BM25 + Reranking)" | 纯服务端断言,插件只 POST `/v1/memory/search`(255-263),仓内不可验证 | ◇ 存疑不证伪 |
      hindsight    Long-term memory with knowledge graph, entity resolution, and multi-strategy retrieval. Supports cloud, local embedded, and local 
      supermemory  Semantic long-term memory with profile recall, semantic search, explicit memory tools, and full-session conversation ingest (one i
      retaindb     Cloud memory API with hybrid search (Vector + BM25 + Reranking) and 7 memory types.
  562 [### 3.7 README vs 代码对照(retaindb)]
      笔记: | 5 | `README.md:30` `RETAINDB_PROJECT` 默认"auto (profile-scoped)" | 529-535:显式值 > `hermes-<profile>`(hermes_home 目录名非 `.hermes` 时)> `"default"` | ✓(RE
      hindsight    
      supermemory  
      retaindb     | `RETAINDB_PROJECT` | auto (profile-scoped) | Project identifier |

########## notes/r6-40-mem0-holographic.md
  383 [### 1.8 README vs 代码 逐条对照(mem0)]
      笔记: | 1 | `README.md:28`:`mode` 默认 `platform` | `__init__.py:88` `os.environ.get("MEM0_MODE", "platform")` | 一致 |
      mem0         | `mode` | `platform` | `platform` (Mem0 Cloud) or `oss` (self-managed, in-process) |
      holographic  | `default_trust` | `0.5` | Default trust score for new facts |
  384 [### 1.8 README vs 代码 逐条对照(mem0)]
      笔记: | 2 | `README.md:30`:`user_id` 默认 `hermes-user` | `__init__.py:56-62、353-356`:该值是**哨兵**,被视为未配置,实际回落网关原生 id | ▲ 有误导:写着"默认值"的字符串在代码里等于"没配",按 README 填 he
      mem0         | `user_id` | `hermes-user` | User identifier on Mem0 |
      holographic  
  385 [### 1.8 README vs 代码 逐条对照(mem0)]
      笔记: | 3 | `README.md:65`:"authenticates with X-API-Key ... /search and /memories routes. api_key is optional — omit it only for AUTH_DISABLED" | `plugins/
      mem0         The plugin authenticates with `X-API-Key` and uses the server's `/search` and `/memories` routes. `api_key` is optional — omit it 
      holographic  <越界 共36行>
  386 [### 1.8 README vs 代码 逐条对照(mem0)]
      笔记: | 4 | `README.md:67`:"Don't set mode: oss — OSS takes precedence and ignores host" | `_create_backend` 280-288 优先级 oss>host;测试 tests/plugins/memory/te
      mem0         > Setting `host` routes to the self-hosted server automatically. Don't set `mode: oss` — OSS takes precedence and ignores `host`.
      holographic  <越界 共36行>
  387 [### 1.8 README vs 代码 逐条对照(mem0)]
      笔记: | 5 | `README.md:101` Flags 表:`--mode` 取值 "platform or oss" | `plugins/memory/mem0/_setup.py:980` 还接受 `selfhosted`/`self-hosted`(README 自己 49 行也用了) | 
      mem0         | `--mode` | `platform` or `oss` |
      holographic  <越界 共36行>
  388 [### 1.8 README vs 代码 逐条对照(mem0)]
      笔记: | 6 | `README.md:7`:Requirements "pip install mem0ai"(无版本) | plugin.yaml 要求 `mem0ai>=2.0.10,<3`;且 `__init__.py:274` 会懒安装,手动装并非必须 | ◇ 不完整:无版本约束,也未提及懒安装
      mem0         - `pip install mem0ai`
      holographic  None — uses SQLite (always available). NumPy optional for HRR algebra.
  389 [### 1.8 README vs 代码 逐条对照(mem0)]
      笔记: | 7 | `README.md:32`:rerank "platform mode only" | `__init__.py:396-397` 提示词只在 platform 提 rerank;`plugins/memory/mem0/_backend.py:115-117` selfhosted 
      mem0         | `rerank` | `false` | Rerank search results for relevance (platform mode only) |
      holographic  
  390 [### 1.8 README vs 代码 逐条对照(mem0)]
      笔记: | 8 | `README.md:146`:mem0_add "Store a fact verbatim (no LLM extraction)" | `__init__.py:566` `infer=False` | 一致 |
      mem0         | `mem0_add` | Store a fact verbatim (no LLM extraction) |
      holographic  <越界 共36行>
  391 [### 1.8 README vs 代码 逐条对照(mem0)]
      笔记: | 9 | `README.md:154`:"Circuit breaker tripped after 5 consecutive failures. Resets after 2 minutes." | `__init__.py:51-52` 阈值 5、冷却 120s | 一致 |
      mem0         Circuit breaker tripped after 5 consecutive failures. Resets after 2 minutes.
      holographic  <越界 共36行>
  392 [### 1.8 README vs 代码 逐条对照(mem0)]
      笔记: | 10 | `README.md:185`:"Use sync_turn for LLM extraction" | `__init__.py:497` sync_turn `infer=True` | 一致 |
      mem0         - `mem0_add` stores verbatim (no extraction). Use `sync_turn` for LLM extraction.
      holographic  <越界 共36行>
  393 [### 1.8 README vs 代码 逐条对照(mem0)]
      笔记: | 11 | `README.md:3`:"hybrid multi-signal retrieval via the Mem0 Platform v3 API" | 代码只见 MemoryClient.search 透传;"v3 API"是 SDK/服务端行为,本仓库内不可证 | ◇ 本仓不可验证
      mem0         Server-side LLM fact extraction with semantic search and hybrid multi-signal retrieval via the Mem0 Platform v3 API.
      holographic  Local SQLite fact store with FTS5 search, trust scoring, entity resolution, and HRR-based compositional retrieval.
  616 [### 2.6 README vs 代码 逐条对照(holographic)]
      笔记: | 1 | `README.md:3`:"Local SQLite fact store with FTS5 search, trust scoring, entity resolution, and HRR-based compositional retrieval" | store.py sch
      mem0         Server-side LLM fact extraction with semantic search and hybrid multi-signal retrieval via the Mem0 Platform v3 API.
      holographic  Local SQLite fact store with FTS5 search, trust scoring, entity resolution, and HRR-based compositional retrieval.
  617 [### 2.6 README vs 代码 逐条对照(holographic)]
      笔记: | 2 | `README.md:7`:"Requirements: None — uses SQLite (always available). NumPy optional" | `__init__.py:126-127` is_available 恒 True;`plugins/memory/
      mem0         - `pip install mem0ai`
      holographic  None — uses SQLite (always available). NumPy optional for HRR algebra.
  618 [### 2.6 README vs 代码 逐条对照(holographic)]
      笔记: | 3 | `README.md:24-29` 配置表:db_path/auto_extract/default_trust/hrr_dim 四键 | initialize 还读 `min_trust_threshold`(`__init__.py:120`)、`hrr_weight`(169)、`
      mem0         Behavioral settings live in `$HERMES_HOME/mem0.json` (set them via `hermes memory setup`). Only the secret `MEM0_API_KEY` belongs 
      holographic  | Key | Default | Description |
  619 [### 2.6 README vs 代码 逐条对照(holographic)]
      笔记: | 4 | `README.md:35`:"fact_store | 9 actions: add, search, probe, related, reason, contradict, update, remove, list" | schema enum(`__init__.py:58-61`
      mem0         
      holographic  | `fact_store` | 9 actions: add, search, probe, related, reason, contradict, update, remove, list |
  620 [### 2.6 README vs 代码 逐条对照(holographic)]
      笔记: | 5 | `README.md:22`:"Config in config.yaml under plugins.hermes-memory-store" | `_load_plugin_config`(104)一致;但 plugin.yaml `name: holographic`、provid
      mem0         ## Config
      holographic  Config in `config.yaml` under `plugins.hermes-memory-store`:
  621 [### 2.6 README vs 代码 逐条对照(holographic)]
      笔记: | 6 | `README.md:36`:fact_feedback "trains trust scores" | `store.py:402-441` +0.05/−0.10 不对称调整 | 一致("trains"是修辞,实为固定步长) |
      mem0         - **Platform** — Mem0's hosted cloud (`api.mem0.ai`). Set `MEM0_API_KEY`. (default)
      holographic  | `fact_feedback` | Rate facts as helpful/unhelpful (trains trust scores) |

########## notes/r6-90-doc-conflict-rulings.md
   23 [## 定案 3 ▲ honcho README 会话名优先级表——证伪]
      笔记: `README.md:230-242` 表:manual map(1)→ /title(2)→ gateway key(3)→ per-session(4)…
      honcho       The Honcho session name determines which conversation bucket memory lands in. Resolution follows a priority chain — first match wi
   34 [## 定案 4 ▲ openviking:两处 README 证伪 + 一处保守]
      笔记: - `README.md:86` "viking_search fast/deep/auto modes":代码只有二态
      openviking   | `viking_search` | Semantic search with fast/deep/auto modes |
   36 [## 定案 4 ▲ openviking:两处 README 证伪 + 一处保守]
      笔记: - `README.md:34-36` "copy 现有 profile 连接值进 Hermes":该路径在基线不存在(现有 profile 只有
      openviking   The setup can link to an existing `~/.openviking/ovcli.conf`, copy its current
   38 [## 定案 4 ▲ openviking:两处 README 证伪 + 一处保守]
      笔记: - `README.md:10-11` 要求先跑 server:实际本地端点不可达时运行期**自动拉起**(保守而非错)。
      openviking   - OpenViking server running and reachable from Hermes
   52 [## 定案 6 ▲ supermemory:死配置]
      笔记: `README.md:55` `capture_mode` "Skip tiny or trivial turns by default":`_capture_mode` 被加载
      supermemory  | `capture_mode` | `all` | Skip tiny or trivial turns by default |
   59 [## 定案 7 ▲ retaindb:三处 README 证伪]
      笔记: - `README.md:3` "7 memory types":schema enum 只有 6 个(factual/preference/goal/instruction/
      retaindb     Cloud memory API with hybrid search (Vector + BM25 + Reranking) and 7 memory types.
   61 [## 定案 7 ▲ retaindb:三处 README 证伪]
      笔记: - `README.md:33-40` 工具表 5 个:实注册 **10 个**(漏整个文件工具族 upload/list/read/ingest/delete)。
      retaindb     
   62 [## 定案 7 ▲ retaindb:三处 README 证伪]
      笔记: - `README.md:24` "All config via env":还读 config.yaml 的 `memory.retaindb` 块(#68209)。
      retaindb     All config via environment variables in `.env`:
   67 [## 定案 8 ▲ mem0:README 误导 + 代码内漂移]
      笔记: - `README.md:30` `user_id` 默认 `hermes-user`:该值实为**哨兵**,等于"未配置"、回落网关原生 id
      mem0         | `user_id` | `hermes-user` | User identifier on Mem0 |
   69 [## 定案 8 ▲ mem0:README 误导 + 代码内漂移]
      笔记: - `README.md:101` `--mode` 取值表漏 `selfhosted`(README 自己 49 行用了,内部矛盾)。
      mem0         | `--mode` | `platform` or `oss` |

########## notes/r6-10-honcho.md
  706 [## 9. README 宣称 vs 代码(逐条)]
      笔记: **◇ 定案(R1 遗留):根 README.md:26 "Honcho dialectic user modeling"** —— `README.md:26 @ 863e313`:
      honcho       
  706 [## 9. README 宣称 vs 代码(逐条)]
      笔记: **◇ 定案(R1 遗留):根 README.md:26 "Honcho dialectic user modeling"** —— `README.md:26 @ 863e313`:
      honcho       
