# r11f 片 F 底稿 —— 长尾插件 + 插件系统公共面

> 范围:`plugins/{web, teams_pipeline, memory, disk-cleanup, security-guidance, cron_providers, context_engine}`
> \+ `plugins/plugin_utils.py` + `plugins/__init__.py`,共 **69 文件 / 9,753 行**。
> 深度 L2(结构级):读接口面而不读实现体 —— **可以不读实现,但不能抽样接口**。
> 基线 `/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`,只读。
> 一切断言写作 `路径:行号 @ 863e313`;锚点单独成行、置于块之前;
> 表格里的锚点后紧跟一个反引号摘录,以便被 `verify_citations.py` 机械校验。

本片有两个重心:**(一)插件系统的公共面**(全轮地基,只有本片覆盖);
**(二)片内 7 个插件目录的接缝穷举**。

---

## 0. 点名表(69/69)

术语先锚一次(给不熟本仓库的读者):
**manifest / 清单** = 每个插件目录里的 `plugin.yaml`,声明插件叫什么、属于哪一类、要注册什么;
**宿主 / host** = 加载插件的那一侧代码(主要在 `hermes_cli/plugins.py`);
**注册键** = 清单里那些"我要往宿主注册某种能力"的顶层键(`hooks`、`provides_tools`、
`provides_web_providers` …);
**backend 插件** = 给某个已有内核工具(如 `web_search`)换后端的插件,与"自带工具的独立插件"相对。

### 0.1 公共面(2 文件)

| 路径 | 行 | 角色 |
|---|---:|---|
| `plugins/__init__.py` | 1 | **整个 `plugins/` 树是不是一个 Python 包**,全靠这一行注释文件。它让 `from plugins.web.xai.provider import …` 这种绝对导入成立(见 §1.5),打包声明见 `pyproject.toml:399`:`"plugins", "plugins.*"` |
| `plugins/plugin_utils.py` | 135 | 给插件作者的**并发工具箱**,与发现/加载无关:`lazy_singleton` 装饰器 + `SingletonSlot` 类,两个都是双检锁(double-checked locking)实现。仅依赖 stdlib `threading` |

**注意一个容易踩的预期错位**:名字叫 `plugin_utils.py`,但它**不含任何插件系统机制**
—— 发现、加载、清单解析全在 `hermes_cli/plugins.py`(2000+ 行)。见 §1。

### 0.2 web 搜索后端(26 文件)

| 路径 | 行 | 角色 |
|---|---:|---|
| `plugins/web/__init__.py` | 7 | 纯注释文件,声明本目录的布局约定与注册路径(`ctx.register_web_search_provider()`) |
| `plugins/web/brave_free/__init__.py` | 14 | `register(ctx)` 入口,实例化并注册 `BraveFreeWebSearchProvider` |
| `plugins/web/brave_free/plugin.yaml` | 7 | 清单:`kind: backend` + `provides_web_providers: [brave-free]` |
| `plugins/web/brave_free/provider.py` | 141 | Brave Data-for-Search API 的 `WebSearchProvider` 子类,search-only |
| `plugins/web/ddgs/__init__.py` | 15 | `register(ctx)` 入口 → `DDGSWebSearchProvider` |
| `plugins/web/ddgs/_search_worker.py` | 113 | **子进程入口**:stdin 收一个 JSON 请求、stdout 回一个 JSON 信封。存在的理由是 `ddgs` 包会持 GIL,把它隔进子进程才能超时中断(见 §3.1) |
| `plugins/web/ddgs/plugin.yaml` | 7 | 清单:`kind: backend` + `provides_web_providers: [ddgs]` |
| `plugins/web/ddgs/provider.py` | 362 | DuckDuckGo provider:派生 `_search_worker.py` 子进程、超时杀进程、结果归一化 |
| `plugins/web/exa/__init__.py` | 15 | `register(ctx)` 入口 → `ExaWebSearchProvider` |
| `plugins/web/exa/plugin.yaml` | 7 | 清单:`kind: backend` + `provides_web_providers: [exa]` |
| `plugins/web/exa/provider.py` | 216 | Exa SDK provider,**同步** search + extract |
| `plugins/web/firecrawl/__init__.py` | 28 | `register(ctx)` 入口 → `FirecrawlWebSearchProvider`,docstring 交代它承接了原先内联在 `tools/web_tools.py` 的实现 |
| `plugins/web/firecrawl/plugin.yaml` | 7 | 清单:`kind: backend` + `provides_web_providers: [firecrawl]` |
| `plugins/web/firecrawl/provider.py` | 617 | 片内最大的 provider:SDK 懒加载代理 `_FirecrawlProxy`、直连/Nous 网关双路径、逐 URL 抓取带 SSRF 复检,`extract` 是 **async** |
| `plugins/web/parallel/__init__.py` | 16 | `register(ctx)` 入口 → `ParallelWebSearchProvider` |
| `plugins/web/parallel/plugin.yaml` | 7 | 清单:`kind: backend` + `provides_web_providers: [parallel]` |
| `plugins/web/parallel/provider.py` | 297 | Parallel.ai provider,`extract` 是 **async**(SDK 原生异步) |
| `plugins/web/searxng/__init__.py` | 15 | `register(ctx)` 入口 → `SearXNGWebSearchProvider` |
| `plugins/web/searxng/plugin.yaml` | 7 | 清单:`kind: backend` + `provides_web_providers: [searxng]` |
| `plugins/web/searxng/provider.py` | 153 | 自建 SearXNG 实例 provider,search-only |
| `plugins/web/tavily/__init__.py` | 10 | `register(ctx)` 入口,见 `plugins/web/tavily/__init__.py:10`:`ctx.register_web_search_provider(TavilyWebSearchProvider())` |
| `plugins/web/tavily/plugin.yaml` | 7 | 清单:`kind: backend` + `provides_web_providers: [tavily]` |
| `plugins/web/tavily/provider.py` | 224 | Tavily provider,同步 search + extract |
| `plugins/web/xai/__init__.py` | 14 | `register(ctx)` 入口,用**绝对导入**取 provider:`plugins/web/xai/__init__.py:9`:`from plugins.web.xai.provider import XAIWebSearchProvider` |
| `plugins/web/xai/plugin.yaml` | 7 | 清单:`kind: backend` + `provides_web_providers: [xai]` |
| `plugins/web/xai/provider.py` | 560 | 唯一的 **LLM 背书式**搜索:调 Grok 的服务端 `web_search` 工具,再从模型输出/annotations 里反解结构化结果(4 个私有解析器) |

### 0.3 memory 清单面(16 文件)

**这 16 个文件全是文档 + 清单**,每家的实现 `.py` 在 R6 已按 L1 精读,不在本片。

| 路径 | 行 | 角色 |
|---|---:|---|
| `plugins/memory/byterover/README.md` | 41 | ByteRover 用户文档:装 `brv` CLI、`BRV_API_KEY` 可选、工具表 |
| `plugins/memory/byterover/plugin.yaml` | 9 | **全仓唯一**声明 `external_dependencies` 的清单;它还写了一个不存在的 hook 名,见 `plugins/memory/byterover/plugin.yaml:9`:`- on_pre_compress` |
| `plugins/memory/hindsight/README.md` | 147 | Hindsight 文档:cloud / local-embedded / local-external 三种模式 |
| `plugins/memory/hindsight/plugin.yaml` | 8 | `pip_dependencies: [hindsight-client>=0.6.1]`、`requires_env: []`、`hooks: [on_session_end]` |
| `plugins/memory/holographic/README.md` | 36 | 本地 SQLite + FTS5 事实库文档,唯一一份不提任何环境变量的 |
| `plugins/memory/holographic/plugin.yaml` | 5 | 片内最短清单:name/version/description + `hooks` |
| `plugins/memory/honcho/README.md` | 414 | 片内最长文档:OAuth / device-code / API key 三条接入路径 + 配置解析顺序 |
| `plugins/memory/honcho/plugin.yaml` | 7 | `pip_dependencies: [honcho-ai]` + `hooks: [on_session_end]` |
| `plugins/memory/mem0/README.md` | 187 | Mem0 文档:platform / oss / 自托管三态 |
| `plugins/memory/mem0/plugin.yaml` | 5 | `pip_dependencies: [mem0ai>=2.0.10,<3]`,**无 hooks** |
| `plugins/memory/openviking/README.md` | 122 | OpenViking 文档,含版本兼容矩阵(0.2.10+ 推荐、0.2.6- 弃用) |
| `plugins/memory/openviking/plugin.yaml` | 8 | `pip_dependencies: [httpx]`、`requires_env: []`、`hooks` |
| `plugins/memory/retaindb/README.md` | 40 | RetainDB 文档,全配置走环境变量 |
| `plugins/memory/retaindb/plugin.yaml` | 7 | **片内唯一非空 `requires_env`**:`[RETAINDB_API_KEY]` |
| `plugins/memory/supermemory/README.md` | 138 | Supermemory 文档:托管 + 自托管 |
| `plugins/memory/supermemory/plugin.yaml` | 5 | `pip_dependencies: [supermemory]`,**无 hooks、无 requires_env** |

### 0.4 其余 5 个插件目录(25 文件)

| 路径 | 行 | 角色 |
|---|---:|---|
| `plugins/context_engine/__init__.py` | 285 | context engine 的**独立发现系统**:`discover_context_engines` / `load_context_engine` / `_EngineCollector` 假 ctx。本目录**没有任何引擎子目录**(见 §3.5) |
| `plugins/cron_providers/__init__.py` | 356 | cron 调度器 provider 的**独立发现系统**,自称是 `plugins/memory/__init__.py` 的近乎逐字克隆;假 ctx 见 `plugins/cron_providers/__init__.py:342`:`def register_cron_scheduler(self, provider):` |
| `plugins/cron_providers/chronos/__init__.py` | 245 | Chronos provider:把"到点叫我"外包给 NAS,实现 scale-to-zero。`register(ctx)` 调 `ctx.register_cron_scheduler(...)` |
| `plugins/cron_providers/chronos/_nas_client.py` | 123 | NAS `agent-cron` 三个端点的瘦 HTTP 客户端,首个见 `plugins/cron_providers/chronos/_nas_client.py:21`:`_PROVISION_PATH = "/api/agent-cron/provision"` |
| `plugins/cron_providers/chronos/plugin.yaml` | 9 | 清单:只有 name/description/version/author,**没有 `kind:`** —— 这一点有后果,见 §4 的 ■-2 |
| `plugins/cron_providers/chronos/verify.py` | 154 | NAS 回调 JWT 的验证器,入口 `plugins/cron_providers/chronos/verify.py:79`:`def verify_nas_fire_token(` —— 远程触发任务执行的安全边界,crypto 委托 PyJWT |
| `plugins/disk-cleanup/README.md` | 51 | disk-cleanup 用户文档:hook 行为表 + 删除规则表 + 安全边界 |
| `plugins/disk-cleanup/__init__.py` | 316 | 插件装配层:两个 hook + 一个斜杠命令,注册点 `plugins/disk-cleanup/__init__.py:309`:`def register(ctx) -> None:` |
| `plugins/disk-cleanup/disk_cleanup.py` | 611 | 清理规则库:`plugins/disk-cleanup/disk_cleanup.py:66`:`def is_safe_path(path: Path) -> bool:` 起,含 track / forget / dry_run / quick / deep / status / guess_category |
| `plugins/disk-cleanup/plugin.yaml` | 7 | 清单:`hooks: [post_tool_call, on_session_end]` |
| `plugins/security-guidance/LICENSE` | 202 | Apache-2.0 全文(`patterns.py` 的上游许可证) |
| `plugins/security-guidance/NOTICE` | 30 | Apache-2.0 要求的归属声明 |
| `plugins/security-guidance/README.md` | 88 | 用户文档:25 条规则的分类表 + 三种模式 + "还没做什么" |
| `plugins/security-guidance/__init__.py` | 259 | 装配层:预编译规则、扫描、两个 hook,注册点 `plugins/security-guidance/__init__.py:257`:`def register(ctx) -> None:` |
| `plugins/security-guidance/patterns.py` | 368 | 纯数据:25 条规则 + `RuleId` 枚举 + `rule_names_to_mask()`,自称逐字 fork 自上游 |
| `plugins/security-guidance/plugin.yaml` | 7 | 清单:`hooks: [transform_tool_result, pre_tool_call]` |
| `plugins/teams_pipeline/__init__.py` | 23 | 只注册**一个 CLI 命令**:`plugins/teams_pipeline/__init__.py:12`:`def register(ctx) -> None:`;明写不给模型加任何工具 |
| `plugins/teams_pipeline/cli.py` | 461 | 运营者 CLI:11 个子命令(见 §3.3) |
| `plugins/teams_pipeline/meetings.py` | 333 | Graph 会议助手:解析会议引用、列/下载 transcript 与录像、call-record 富化 |
| `plugins/teams_pipeline/models.py` | 350 | 5 个规范化 dataclass:`GraphSubscription` / `TeamsMeetingRef` / `MeetingArtifact` / `TeamsMeetingSummaryPayload` / `TeamsMeetingPipelineJob` |
| `plugins/teams_pipeline/pipeline.py` | 701 | 编排核心 `TeamsMeetingPipeline` + 两个外部 sink:`plugins/teams_pipeline/pipeline.py:109`:`class NotionWriter:` 与 `:206` 的 `LinearWriter` |
| `plugins/teams_pipeline/plugin.yaml` | 9 | 清单:`kind: standalone` + `platforms: [linux, macos, windows]`(`platforms` 无人消费,见 §1.4) |
| `plugins/teams_pipeline/runtime.py` | 135 | **第二个入口**:`bind_gateway_runtime(gateway)`,由 `gateway/run.py` 直接 import,不走 PluginContext(见 §3.3) |
| `plugins/teams_pipeline/store.py` | 193 | durable 本地状态,落盘名见 `plugins/teams_pipeline/store.py:18`:`DEFAULT_TEAMS_PIPELINE_STORE_FILENAME = "teams_pipeline_store.json"` |
| `plugins/teams_pipeline/subscriptions.py` | 249 | Graph 订阅生命周期:创建/续期/判定托管/`clientState` 校验 |

---

## 1. 插件系统的公共面(重心一)

### 1.1 宿主怎么发现插件 —— 四个来源、两种布局、深度上限 2

模块 docstring 就是这套体系的说明书。

`hermes_cli/plugins.py:5 @ 863e313`

> Discovers, loads, and manages plugins from four sources:
>
> 1. **Bundled plugins** – ``<repo>/plugins/<name>/`` (shipped with hermes-agent;
>    ``memory/`` and ``context_engine/`` subdirs are excluded — they have their
>    own discovery paths)

四个来源按顺序扫,**后来者覆盖先来者**(同 key 冲突时 project > user > bundled)。
第一步扫仓库自带的 `plugins/`,并显式跳过四个"有自己发现系统"的目录:

`hermes_cli/plugins.py:1358 @ 863e313`

```
        bundled = self._scan_directory(
            repo_plugins,
            source="bundled",
            skip_names={"memory", "context_engine", "platforms", "model-providers"},
        )
```

**跳过表里没有 `cron_providers`** —— 而 `plugins/cron_providers/` 恰恰也是一个
"有自己发现系统"的目录。这个不对称是 §4 ■-2 的根。

扫描本身是两层递归:

| 布局 | 形状 | key | 锚点 + 摘录 |
|---|---|---|---|
| 递归入口 | 两层,`depth` 逐层加一 | —— | `hermes_cli/plugins.py:1529`:`def _scan_directory_level(` |
| flat | `<root>/<name>/plugin.yaml` | `<name>`(如 `disk-cleanup`) | `hermes_cli/plugins.py:1553`:`manifest_file = child / "plugin.yaml"` |
| category | `<root>/<cat>/<name>/plugin.yaml`,`<cat>` 自己没有清单 | `<cat>/<name>`(如 `web/tavily`) | `hermes_cli/plugins.py:1572`:`sub_prefix = f"{prefix}/{child.name}" if prefix else child.name` |
| 三层及以上 | —— | **永远发现不到**(`depth >= 1` 且无清单即放弃) | `hermes_cli/plugins.py:1568`:`if depth >= 1:` |

清单文件名接受两种:先找 `plugin.yaml`,找不到再找 `plugin.yml`。

用宿主自己的扫描器跑一遍(不 import 任何插件模块),得到顶层的全部发现结果:

```verify
cd /home/user/hermes-agent && PYTHONDONTWRITEBYTECODE=1 HERMES_DISABLE_LAZY_INSTALLS=1 \
  /home/user/hermes-venv/bin/python \
  /home/user/hermes-study/data/r11f/probes/f_scanner_kinds.py /home/user/hermes-agent
```

```text
VALID_KINDS=backend,exclusive,model-provider,platform,standalone
top-level manifests found: 33
  key=browser/browser_use          kind=backend       name=browser-browser-use
  key=browser/browserbase          kind=backend       name=browser-browserbase
  key=browser/firecrawl            kind=backend       name=browser-firecrawl
  key=cron_providers/chronos       kind=standalone    name=chronos
  key=dashboard_auth/basic         kind=backend       name=basic
  key=dashboard_auth/drain         kind=backend       name=drain
  key=dashboard_auth/nous          kind=backend       name=nous
  key=dashboard_auth/self_hosted   kind=backend       name=self-hosted
  key=disk-cleanup                 kind=standalone    name=disk-cleanup
  key=google_meet                  kind=standalone    name=google_meet
  key=image_gen/deepinfra          kind=backend       name=deepinfra
  key=image_gen/fal                kind=backend       name=fal
  key=image_gen/krea               kind=backend       name=krea
  key=image_gen/openai             kind=backend       name=openai
  key=image_gen/openai-codex       kind=backend       name=openai-codex
  key=image_gen/openrouter         kind=backend       name=openrouter
  key=image_gen/xai                kind=backend       name=xai
  key=observability/langfuse       kind=standalone    name=langfuse
  key=observability/nemo_relay     kind=standalone    name=nemo_relay
  key=security-guidance            kind=standalone    name=security-guidance
  key=spotify                      kind=backend       name=spotify
  key=teams_pipeline               kind=standalone    name=teams_pipeline
  key=video_gen/deepinfra          kind=backend       name=deepinfra
  key=video_gen/fal                kind=backend       name=fal
  key=video_gen/xai                kind=backend       name=xai
  key=web/brave_free               kind=backend       name=web-brave-free
  key=web/ddgs                     kind=backend       name=web-ddgs
  key=web/exa                      kind=backend       name=web-exa
  key=web/firecrawl                kind=backend       name=web-firecrawl
  key=web/parallel                 kind=backend       name=web-parallel
  key=web/searxng                  kind=backend       name=web-searxng
  key=web/tavily                   kind=backend       name=web-tavily
  key=web/xai                      kind=backend       name=web-xai
```

### 1.2 kind 决定"发现之后干什么" —— 六条互斥分支

`kind` 是**唯一**的路由字段,合法值五个。不认识的 kind **不报错、只 warning,然后当 standalone**。

| 事项 | 锚点 + 摘录 |
|---|---|
| 合法值 | `hermes_cli/plugins.py:280`:`_VALID_PLUGIN_KINDS: Set[str] = {"standalone", "backend", "exclusive", "platform", "model-provider"}` |
| 越界不阻断 | `hermes_cli/plugins.py:1609`:`if kind not in _VALID_PLUGIN_KINDS:` |
| 路由循环 | `hermes_cli/plugins.py:1407`:`for manifest in winners.values():` |

循环里的分支顺序即优先级:

| 顺序 | 条件 | 处置 | 锚点 + 摘录 |
|---:|---|---|---|
| 1 | key 或 name 在 `plugins.disabled` | 记录但不加载 | `hermes_cli/plugins.py:1412`:`if lookup_key in disabled or manifest.name in disabled:` |
| 2 | `kind == "exclusive"` | 只登记清单,由 `<category>.provider` 配置激活 | `hermes_cli/plugins.py:1422`:`if manifest.kind == "exclusive":` |
| 3 | `kind == "model-provider"` | 只登记,交给 `providers/` 自己的懒发现 | `hermes_cli/plugins.py:1440`:`if manifest.kind == "model-provider":` |
| 4 | bundled 且 backend | **无条件自动加载** | `hermes_cli/plugins.py:1453`:`if manifest.source == "bundled" and manifest.kind == "backend":` |
| 5 | bundled 且 platform | 注册**延迟加载器**,首次真用到才 import | `hermes_cli/plugins.py:1468`:`if manifest.source == "bundled" and manifest.kind == "platform":` |
| 6 | 其余(standalone / 用户装的 backend / entry-point) | **opt-in**,要出现在 `plugins.enabled` 里 | `hermes_cli/plugins.py:1476`:`is_enabled = (` |

片内 8 个 web 插件全部命中第 4 条 —— 这就是"bundled web 后端总是可用、无需 enable"的机制来源。
`disk-cleanup` / `security-guidance` / `teams_pipeline` / `cron_providers/chronos` 命中第 6 条。

### 1.3 怎么加载 —— 合成模块名 + 失败即记录不抛

目录型插件不走 `import`,而是用 `importlib.util.spec_from_file_location` 把
`__init__.py` 装进一个**合成的模块名** `hermes_plugins.<slug>`:

`hermes_cli/plugins.py:1874 @ 863e313`

```
        key = manifest.key or manifest.name
        slug = key.replace("/", "__").replace("-", "_")
        module_name = f"{_NS_PARENT}.{slug}"
        spec = importlib.util.spec_from_file_location(
            module_name,
            init_file,
            submodule_search_locations=[str(plugin_dir)],
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {init_file}")

        module = importlib.util.module_from_spec(spec)
        module.__package__ = module_name
        module.__path__ = [str(plugin_dir)]  # type: ignore[attr-defined]
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
```

三个设计点:

| # | 设计点 | 为什么 | 锚点 + 摘录 |
|---:|---|---|---|
| 1 | slug 由 **key** 派生而非 name | `image_gen/openai` 与将来的 `tts/openai` 不会撞槽位 —— 两份清单的 `name` 都可以是 `openai` | `hermes_cli/plugins.py:1876`:`module_name = f"{_NS_PARENT}.{slug}"` |
| 2 | 设 `submodule_search_locations` + `__path__` | 让插件内部的相对导入成立 | `plugins/disk-cleanup/__init__.py:30`:`from . import disk_cleanup as dg` |
| 3 | 失败不抛给调用方 | 一个插件炸了不拖垮 agent 启动;代价是错误只在 `hermes plugins list` 里可见 | `hermes_cli/plugins.py:1846`:`except Exception as exc:` |
| 4 | 再入守卫先置位后回滚 | 不把"扫描失败"缓存成"已发现且注册表为空" | `hermes_cli/plugins.py:1332`:`self._discovered = True` |

发现-加载全流程还有一个**再入守卫**:`_discovered` 标志**先置位再干活**,失败时回滚(表中第 4 行),
注释明写这是为了不把"扫描失败"缓存成"已发现且注册表为空"。

### 1.4 `plugin.yaml` 的键面契约 —— 谁定义、谁消费、有没有 schema 校验

**没有 schema 校验。** 契约就是 `_parse_manifest` 里那一串 `data.get()`:

`hermes_cli/plugins.py:1657 @ 863e313`

```
            return PluginManifest(
                name=name,
                version=str(data.get("version", "")),
                description=data.get("description", ""),
                author=data.get("author", ""),
                requires_env=data.get("requires_env", []),
                provides_tools=data.get("provides_tools", []),
                provides_hooks=data.get("provides_hooks", []),
                source=source,
                path=str(plugin_dir),
                kind=kind,
                key=key,
            )
```

加上上方单独处理的 `kind`(`:1605`)与 `name`(`:1602`),**通用加载器一共只读 8 个键**。
清单里其它任何键都被**静默丢弃**:不校验、不告警、不进任何数据结构。

片内 20 份清单的键集逐份列全(判据 2):

```verify
cd /home/user/hermes-agent && PYTHONDONTWRITEBYTECODE=1 HERMES_DISABLE_LAZY_INSTALLS=1 \
  /home/user/hermes-venv/bin/python \
  /home/user/hermes-study/data/r11f/probes/f_manifest_keys.py /home/user/hermes-agent
```

```text
manifest dir                 top-level keys (* = 加载器不读)
cron_providers/chronos       name description version author
disk-cleanup                 name version description author hooks*
security-guidance            name version description author hooks*
teams_pipeline               name version description author kind platforms*
memory/byterover             name version description external_dependencies* hooks*
memory/hindsight             name version description pip_dependencies* requires_env hooks*
memory/holographic           name version description hooks*
memory/honcho                name version description pip_dependencies* hooks*
memory/mem0                  name version description pip_dependencies*
memory/openviking            name version description pip_dependencies* requires_env hooks*
memory/retaindb              name version description pip_dependencies* requires_env
memory/supermemory           name version description pip_dependencies*
web/brave_free               name version description author kind provides_web_providers*
web/ddgs                     name version description author kind provides_web_providers*
web/exa                      name version description author kind provides_web_providers*
web/firecrawl                name version description author kind provides_web_providers*
web/parallel                 name version description author kind provides_web_providers*
web/searxng                  name version description author kind provides_web_providers*
web/tavily                   name version description author kind provides_web_providers*
web/xai                      name version description author kind provides_web_providers*

片内不同顶层键 11 个,按出现次数:
  description              20  读
  name                     20  读
  version                  20  读
  author                   12  读
  kind                      9  读
  provides_web_providers    8  不读
  hooks                     7  不读
  pip_dependencies          6  不读
  requires_env              3  读
  external_dependencies     1  不读
  platforms                 1  不读
```

**「不读」不等于「没用」** —— 它只是不被**通用加载器**读。全部注册键的真实消费方:

| 注册键 | 通用加载器 | 真正的消费方(锚点 + 摘录) | 结论 |
|---|---|---|---|
| `name`/`version`/`description`/`author`/`kind` | 读 | `hermes_cli/plugins.py:1657`:`return PluginManifest(` | 核心元数据 |
| `requires_env` | 读 | 另有三处直接读 YAML:`hermes_cli/plugins_cmd.py:302`:`requires_env = manifest.get("requires_env") or []` | 设置向导输入面 |
| `requires_env`(配置向导) | — | `hermes_cli/config.py:5397`:`entries = list(manifest.get("requires_env") or [])` | 同上 |
| `requires_env`(dashboard) | — | `hermes_cli/web_server.py:5271`:`"required_env": _string_list(manifest.get("requires_env")),` | 同上 |
| `optional_env` | **不读** | 仅一处:`hermes_cli/config.py:5398`:`entries.extend(manifest.get("optional_env") or [])` | 只进配置向导,不进 `PluginManifest` |
| `provides_tools` | 读 | `hermes_cli/plugins_cmd.py:1855`:`for tool_name in manifest.get("provides_tools") or []:` | 加载前先公示工具名 |
| `provides_tools`(dashboard) | — | `hermes_cli/web_server.py:16895`:`provides_tools = manifest_data.get("provides_tools") or []` | 同上 |
| **`provides_hooks`** | 读 | **全仓 0 份清单声明它**(见下) | **死字段** |
| **`hooks`** | **不读** | **无任何消费方** | **纯装饰**(§4 ■-3) |
| `pip_dependencies` | 不读 | `hermes_cli/memory_setup.py:134`:`pip_deps = _provider_pip_dependencies(provider_name, meta.get("pip_dependencies", []))` | **只对 memory 生效** |
| `pip_dependencies`(dashboard) | — | `hermes_cli/web_server.py:5269`:`"pip_dependencies": _string_list(manifest.get("pip_dependencies")),` | 同上 |
| `external_dependencies` | 不读 | `hermes_cli/memory_setup.py:189`:`ext_deps = meta.get("external_dependencies", [])` | **只对 memory 生效** |
| `external_dependencies`(dashboard) | — | `hermes_cli/web_server.py:5257`:`for raw in manifest.get("external_dependencies") or []:` | **且是可执行面**(§4 ■-1) |
| **`provides_web_providers`** | 不读 | **全仓无任何代码读它**(§4 ▲-1) | 纯文档 |
| **`provides_browser_providers`** | 不读 | **同上** | 纯文档 |
| **`platforms`** | 不读 | **无消费方**(仅 `plugins/google_meet/` 与 `plugins/teams_pipeline/` 两份声明) | 纯装饰 |
| `label` | 不读 | 不在本片语料内,未查 | — |

`provides_web_providers` / `provides_browser_providers` 的负结论,搜索面写清楚:
`git grep` 全仓所有被追踪文件(不限扩展名、不排除任何目录),再单独限 `*.py`:

```verify
echo "files mentioning provides_web_providers (any file type):"
git -C /home/user/hermes-agent grep -l "provides_web_providers" | wc -l
echo "python readers of either key:"
git -C /home/user/hermes-agent grep -n "provides_web_providers\|provides_browser_providers" -- '*.py' | wc -l
```

```text
files mentioning provides_web_providers (any file type):
10
python readers of either key:
0
```

那 10 个文件是:8 份 `plugins/web/*/plugin.yaml` + `website/docs/developer-guide/web-search-provider-plugin.md`
+ 它的中文译本。**声明方与文档各一半,消费方零。**

`provides_hooks` 与 `hooks` 的对照普查:

```verify
cd /home/user/hermes-agent && PYTHONDONTWRITEBYTECODE=1 HERMES_DISABLE_LAZY_INSTALLS=1 \
  /home/user/hermes-venv/bin/python \
  /home/user/hermes-study/data/r11f/probes/f_hooks_key_census.py /home/user/hermes-agent
```

```text
manifests declaring `hooks:`        = 10
manifests declaring `provides_hooks:` = 0   <- the key the parser reads

  plugins/disk-cleanup/plugin.yaml               post_tool_call, on_session_end
  plugins/google_meet/plugin.yaml                on_session_end
  plugins/memory/byterover/plugin.yaml           on_pre_compress [NOT IN VALID_HOOKS]
  plugins/memory/hindsight/plugin.yaml           on_session_end
  plugins/memory/holographic/plugin.yaml         on_session_end
  plugins/memory/honcho/plugin.yaml              on_session_end
  plugins/memory/openviking/plugin.yaml          on_session_end
  plugins/observability/langfuse/plugin.yaml     pre_api_request, post_api_request, pre_llm_call, post_llm_call, pre_tool_call, post_tool_call
  plugins/observability/nemo_relay/plugin.yaml   on_session_start, on_session_end, on_session_finalize, on_session_reset, pre_llm_call, post_llm_call, pre_approval_request, post_approval_response, subagent_start, subagent_stop
  plugins/security-guidance/plugin.yaml          transform_tool_result, pre_tool_call

hook names not in VALID_HOOKS: 1
  plugins/memory/byterover/plugin.yaml -> on_pre_compress
```

### 1.5 注册面 —— 真正把能力交给宿主的是 `ctx`,不是清单

清单里的 `provides_*` 都是**公示**;真正的注册动作发生在 `register(ctx)` 里。
`PluginContext` 上实测有 **18 个** `register_*` 方法(用宿主自己的对象枚举,不靠读源码数):

```verify
cd /home/user/hermes-agent && PYTHONDONTWRITEBYTECODE=1 HERMES_DISABLE_LAZY_INSTALLS=1 \
  /home/user/hermes-venv/bin/python \
  /home/user/hermes-study/data/r11f/probes/f_chronos_ctx_gap.py /home/user/hermes-agent 2>/dev/null
```

```text
PluginContext register_* methods: 18
  register_auxiliary_task
  register_browser_provider
  register_cli_command
  register_command
  register_context_engine
  register_dashboard_auth_provider
  register_hook
  register_image_gen_provider
  register_middleware
  register_platform
  register_secret_source
  register_skill
  register_slack_action_handler
  register_tool
  register_transcription_provider
  register_tts_provider
  register_video_gen_provider
  register_web_search_provider
hasattr(ctx, 'register_cron_scheduler') = False
after _load_plugin: enabled=False error="'PluginContext' object has no attribute 'register_cron_scheduler'"
```

| 事项 | 锚点 + 摘录 |
|---|---|
| hook 名的运行时闸(**24** 个 `VALID_HOOKS`,越界即拒) | `hermes_cli/plugins.py:1186`:`if hook_name not in VALID_HOOKS:` |
| 归属统计用 register 前后快照做差,不拿名字跟已加载插件比 | `hermes_cli/plugins.py:1800`:`# Snapshot registry state BEFORE register() so each registry` |
| 差集落地 | `hermes_cli/plugins.py:1815`:`loaded.tools_registered = [` |

注意 `VALID_HOOKS` 是**运行时**校验;清单里写的 hook 名从不经过它(§1.4)。
注释里给出的理由是:拿名字跟已加载插件比,会把两个插件共用的 hook 名只算给第一个。

**最后回到那 1 行的 `plugins/__init__.py`。** 插件模块被装进 `hermes_plugins.<slug>`,
但片内 8 个 web 插件的 `__init__.py` 用的却是**绝对导入**(见 §0.2 表里 `plugins/web/xai/__init__.py` 那一行)。
这条导入成立的前提,是 `plugins` 本身是一个可导入的包 —— 靠的正是那一行文件,
以及打包声明把它算进发行物:

`pyproject.toml:399 @ 863e313`

```
include = ["agent", "agent.*", "tools", "tools.*", "hermes_cli", "hermes_cli.*", "gateway", "gateway.*", "tui_gateway", "tui_gateway.*", "cron", "cron.*", "acp_adapter", "plugins", "plugins.*", "providers", "providers.*"]
```

于是同一份 `provider.py` 会以 `plugins.web.xai.provider` 这个名字进 `sys.modules`,
而 `__init__.py` 以 `hermes_plugins.web__xai` 进 —— **两个名字,各进各的槽位**。
两个类别发现器都为此手工注册过父包,注释写的就是"让相对导入解析得了":

| 事项 | 锚点 + 摘录 |
|---|---|
| context_engine 手工注册父包 | `plugins/context_engine/__init__.py:120`:`for parent in ("plugins", "plugins.context_engine"):` |
| cron_providers 同样手工注册 | `plugins/cron_providers/__init__.py:239`:`for parent in ("plugins", "plugins.cron_providers"):` |

### 1.6 `plugin_utils.py` —— 唯一给插件作者的公共库

它解决的是一个具体的形态:插件里常见的懒加载单例在多线程下会被建两次。

`plugins/plugin_utils.py:3 @ 863e313`

> The most common plugin footgun is the lazy process-wide singleton:

实现是教科书式的双检锁,用一个**单元素 list 作 box**(避免 `None` 与"没建过"混淆):

`plugins/plugin_utils.py:65 @ 863e313`

```
    @functools.wraps(factory)
    def accessor() -> T:
        if box:
            return box[0]
        with lock:
            if box:  # re-check inside the lock
                return box[0]
            instance = factory()
            box.append(instance)
            return instance
```

`SingletonSlot` 是同一套语义的"带参版",取的是 **first config wins**;
两者都挂 `.reset()` 供测试拆卸,且**工厂抛异常时不缓存**,下次重试。

| 事项 | 锚点 + 摘录 |
|---|---|
| first config wins 的自述 | `plugins/plugin_utils.py:88`:`caches the first successfully-built instance and ignores the argument on` |
| 只导出两个名字 | `plugins/plugin_utils.py:38`:`__all__ = ["lazy_singleton", "SingletonSlot"]` |

---

## 2. 端到端链:一次 `web_search` 调用,从"宿主发现插件"到"结果回到用户"

这是全轮的地基链 —— 逐跳带锚点。设定:用户在 CLI 里让 agent 搜一句话,
`web.search_backend` 配成 `tavily`。

| # | 跳 | 发生了什么 | 锚点 + 摘录 |
|---:|---|---|---|
| 1 | 用户 → agent | agent 决定调 `web_search` 工具 | —— |
| 2 | 内核 → 插件系统 | 首次触发 `discover_plugins()`;`_discovered` 先置位作再入守卫 | `hermes_cli/plugins.py:1332`:`self._discovered = True` |
| 3 | 扫描 bundled | `plugins/web/` 自己没有 `plugin.yaml`,于是被当**类别**递归进去 | `hermes_cli/plugins.py:1572`:`sub_prefix = f"{prefix}/{child.name}" if prefix else child.name` |
| 4 | 解析清单 | key=`web/tavily`、kind=`backend`;`provides_web_providers` **在这一步被丢弃** | `hermes_cli/plugins.py:1657`:`return PluginManifest(` |
| 5 | 路由 | bundled + backend → **无条件加载**,不查 `plugins.enabled` | `hermes_cli/plugins.py:1453`:`if manifest.source == "bundled" and manifest.kind == "backend":` |
| 6 | 导入 | `__init__.py` 装进 `hermes_plugins.web__tavily` | `hermes_cli/plugins.py:1876`:`module_name = f"{_NS_PARENT}.{slug}"` |
| 7 | 插件注册 | `register(ctx)` 交出一个 provider 实例 | `plugins/web/tavily/__init__.py:10`:`ctx.register_web_search_provider(TavilyWebSearchProvider())` |
| 8 | 进注册表 | ctx 转手写进 `agent/web_search_registry.py` | `plugins/web/__init__.py:7`:`ctx.register_web_search_provider() into agent.web_search_registry.` |
| 9 | 归属统计 | register 前后快照做差,记下这个插件注册了什么 | `hermes_cli/plugins.py:1815`:`loaded.tools_registered = [` |
| 10 | 选后端 | 按 `web.search_backend` → `web.backend` 的顺序挑 provider,认的是 ABC 的稳定 id | `agent/web_search_provider.py:89`:`class WebSearchProvider(abc.ABC):` |
| 11 | 可用性闸 | 先问 `is_available()`(便宜、离线);Tavily 查 `TAVILY_API_KEY` | `plugins/web/tavily/provider.py:141`:`def is_available(self) -> bool:` |
| 12 | 能力闸 | `supports_search()` 为真才走 `search` | `plugins/web/tavily/provider.py:147`:`def supports_search(self) -> bool:` |
| 13 | 执行 | 返回归一化 dict | `plugins/web/tavily/provider.py:153`:`def search(self, query: str, limit: int = 5) -> Dict[str, Any]:` |
| 14 | 回到用户 | 结果作为工具结果进下一轮模型消息 | —— |

链上两个值得记住的性质:

- **第 4 跳的丢弃是无声的**。清单里公示的 `provides_web_providers: [tavily]` 在这里
  蒸发,第 7 跳注册的名字来自 `provider.name` 属性。两者不一致也没人会知道。
- **第 5 跳跳过了 `plugins.enabled`**。这就是"bundled backend 必须开箱可用"的兑现方式,
  也是**用户装的**同名 web 插件反而要 opt-in 的原因(§1.2 第 6 条分支)。

---

## 3. 片内 7 个目录的接缝穷举(重心二)

### 3.1 `plugins/web/` —— provider 面(8 家 × 8 个 ABC 成员)

ABC 契约在 `agent/web_search_provider.py`,成员共 **8 个**(其中 `name` / `display_name` 是 property;
类头锚点见 §2 链第 10 跳)。下表把 8 家实现逐项列全(✔=本类实现,·=用 ABC 默认):

| 成员 | brave_free | ddgs | exa | firecrawl | parallel | searxng | tavily | xai |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `name` | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `display_name` | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `is_available()` | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `supports_search()` | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `supports_extract()` | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `search()` | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `extract()` | · | · | ✔ 同步 | ✔ **async** | ✔ **async** | · | ✔ 同步 | · |
| `get_setup_schema()` | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |

枚举命令与条数:

```verify
cd /home/user/hermes-agent
echo "ABC members (2 of them are properties):"; grep -c "^    def " agent/web_search_provider.py
echo "providers implementing extract():"
grep -l "def extract(\|async def extract(" plugins/web/*/provider.py | wc -l
echo "providers implementing get_setup_schema():"
grep -l "def get_setup_schema(" plugins/web/*/provider.py | wc -l
echo "provider dirs:"; ls -d plugins/web/*/ | grep -v __pycache__ | wc -l
```

```text
ABC members (2 of them are properties):
8
providers implementing extract():
4
providers implementing get_setup_schema():
8
provider dirs:
8
```

**`ddgs` 的子进程接缝**(片内唯一一个跨进程的插件内部接缝)。`_search_worker.py`
是被 provider 以脚本路径派生的独立进程,契约写在它自己的 docstring 里:

`plugins/web/ddgs/_search_worker.py:1 @ 863e313`

```
"""DDGS search child-process entrypoint (#68096).

Invoked as ``python plugins/web/ddgs/_search_worker.py`` (script path from the
parent provider). Reads one JSON request from stdin, writes one JSON envelope
to stdout, then exits.
```

另有一组**只在 `HERMES_DDGS_ALLOW_TEST_HOOKS=1` 时生效**的测试钩子
(`sleep` / `gil` / `success` / `error` / `empty`),用来在测试里复现"子进程持 GIL 不响应超时"。
这是本片最值得学的一个取舍:**第三方同步库不肯让出 GIL 时,进程隔离是唯一能真正超时的办法。**

### 3.2 `plugins/memory/` —— 清单面 + 文档面(8 家)

8 家 bundled provider(目录数机械枚举):

```verify
git -C /home/user/hermes-agent ls-files 'plugins/memory/*/plugin.yaml' | cut -d/ -f3 | sort | tr '\n' ' '
echo
git -C /home/user/hermes-agent ls-files 'plugins/memory/*/plugin.yaml' | wc -l
```

```text
byterover hindsight holographic honcho mem0 openviking retaindb supermemory 
8
```

**`requires_env` / `optional_env` 逐条列全**(判据 2 明确要求):

| provider | `requires_env` | `optional_env` | README 里实际记载的环境变量 |
|---|---|---|---|
| byterover | (无此键) | (无) | `BRV_API_KEY`(可选) |
| hindsight | `[]`(空列表) | (无) | `HINDSIGHT_API_KEY`、`HINDSIGHT_LLM_API_KEY`、`HINDSIGHT_API_LLM_BASE_URL`、`HINDSIGHT_API_URL` |
| holographic | (无此键) | (无) | 无(全走 config.yaml) |
| honcho | (无此键) | (无) | `HONCHO_API_KEY`、`HONCHO_BASE_URL`、`HONCHO_ENVIRONMENT`、`HONCHO_OAUTH_*`(3 个) |
| mem0 | (无此键) | (无) | `MEM0_API_KEY` |
| openviking | `[]`(空列表) | (无) | `OPENVIKING_API_KEY` |
| retaindb | `[RETAINDB_API_KEY]` | (无) | `RETAINDB_API_KEY`、`RETAINDB_BASE_URL`、`RETAINDB_PROJECT` |
| supermemory | (无此键) | (无) | `SUPERMEMORY_API_KEY`、`SUPERMEMORY_BASE_URL` |

**结论:8 家里只有 1 家(retaindb)在清单里声明了非空 `requires_env`,`optional_env` 一家都没有。**
而 8 家 README 里有 7 家记载了至少一个环境变量。这不是遗漏 —— memory 子系统的配置面走的是
provider 代码里的 `get_config_schema()`,由 `hermes_cli/web_server.py` 渲染;
清单的 `requires_env` 只是**另一条、被通用向导用的**输入面。
两条面并存、且清单这条几乎全空,是 memory 与其它插件类别最大的形态差异。

`pip_dependencies` 逐条:hindsight `hindsight-client>=0.6.1`、honcho `honcho-ai`、
mem0 `mem0ai>=2.0.10,<3`、openviking `httpx`、retaindb `requests`、supermemory `supermemory`;
byterover 与 holographic 无。共 6 家。

`external_dependencies` **全仓仅 byterover 一家**,清单原文:

`plugins/memory/byterover/plugin.yaml:4 @ 863e313`

```
external_dependencies:
  - name: brv
    install: "curl -fsSL https://byterover.dev/install.sh | sh"
    check: "brv --version"
```

它是一个**可执行面** —— 见 §4 ■-1。

### 3.3 `plugins/teams_pipeline/` —— 两个入口面

**入口面 A(插件协议)**:`register(ctx)` 只做一件事 —— 注册 CLI 命令(锚点见 §0.4 表)。
`teams-pipeline` 下的子命令逐项列全,**11 个**(别名不另计):

```verify
cd /home/user/hermes-agent && grep -o 'subs.add_parser("[a-z-]*"' plugins/teams_pipeline/cli.py \
  | sed 's/.*("//;s/"//' | sort | tr '\n' ' '; echo
grep -c 'subs.add_parser(' plugins/teams_pipeline/cli.py
```

```text
delete-subscription fetch list maintain-subscriptions renew-subscription run show subscribe subscriptions token-health validate 
11
```

**入口面 B(宿主直连)**:gateway 绕过 PluginContext,**按名字**判断插件是否启用,
然后直接 import 插件模块:

`gateway/run.py:6265 @ 863e313`

```
        if Platform.MSGRAPH_WEBHOOK not in self.adapters:
            return
        if not _teams_pipeline_plugin_enabled():
            logger.debug("Teams pipeline plugin is disabled; skipping runtime wiring")
            return
        try:
            from plugins.teams_pipeline.runtime import bind_gateway_runtime
        except Exception as exc:
            logger.warning("Teams pipeline runtime import failed: %s", exc)
            return
        try:
            bound = bind_gateway_runtime(self)
```

判定"启用"用的是字符串匹配而非 PluginManager(下表第 1 行)。
两种写法都接受,而扫描器给出的 key 恰是 `teams_pipeline`(§1.1 探针输出),所以**当前不会错**;
但这是一条**与插件系统平行的、按名字硬连线的接缝**,记作 ◇-1(§4)。

其余接缝:

| 接缝 | 锚点 + 摘录 |
|---|---|
| 启用判定按名字匹配 | `gateway/run.py:3134`:`return "teams_pipeline" in enabled or "teams-pipeline" in enabled` |
| 宿主直接 import 插件模块 | `gateway/run.py:6271`:`from plugins.teams_pipeline.runtime import bind_gateway_runtime` |
| 落盘文件名 | `plugins/teams_pipeline/store.py:18`:`DEFAULT_TEAMS_PIPELINE_STORE_FILENAME = "teams_pipeline_store.json"` |
| 外部 sink 之一 | `plugins/teams_pipeline/pipeline.py:109`:`class NotionWriter:` |
| 外部 sink 之二 | `plugins/teams_pipeline/pipeline.py:206`:`class LinearWriter:` |
| 作业状态机终态集 | `plugins/teams_pipeline/pipeline.py:40`:`TERMINAL_PIPELINE_STATES = {"completed", "failed", "retry_scheduled"}` |

### 3.4 `plugins/cron_providers/` —— 一个 provider、三个 NAS 端点、一条 JWT 边界

发现系统自述是 memory 的克隆:

`plugins/cron_providers/__init__.py:12 @ 863e313`

> This is a near-verbatim clone of ``plugins/memory/__init__.py`` — the same
> discovery/loader machinery, retargeted at ``CronScheduler``.

**接缝逐项**:

| 接缝 | 条数 | 锚点 + 摘录 |
|---|---:|---|
| NAS 端点 | 3 | `plugins/cron_providers/chronos/_nas_client.py:21`:`_PROVISION_PATH = "/api/agent-cron/provision"` |
| NAS 端点(取消) | — | `plugins/cron_providers/chronos/_nas_client.py:22`:`_CANCEL_PATH = "/api/agent-cron/cancel"` |
| NAS 端点(列举) | — | `plugins/cron_providers/chronos/_nas_client.py:23`:`_LIST_PATH = "/api/agent-cron/list"` |
| 配置键 | 2 | `plugins/cron_providers/chronos/__init__.py:72`:`_cfg("cron", "chronos", "portal_url")` |
| 入站 JWT 边界 | 1 | `plugins/cron_providers/chronos/verify.py:79`:`def verify_nas_fire_token(` |
| 验证器可换 | 1 | `plugins/cron_providers/chronos/verify.py:147`:`def get_fire_verifier() -> Callable[..., Optional[Dict[str, Any]]]:` |
| 假 ctx 面 | 1 | `plugins/cron_providers/__init__.py:342`:`def register_cron_scheduler(self, provider):` |

```verify
cd /home/user/hermes-agent
echo "NAS endpoints:"; grep -c '^_[A-Z]*_PATH = ' plugins/cron_providers/chronos/_nas_client.py
echo "cron.chronos config keys:"
grep -oh '_cfg("cron", "chronos", "[a-z_]*"' plugins/cron_providers/chronos/*.py | sed 's/.*"chronos", "//;s/"//' | sort -u | tr '\n' ' '; echo
echo "provider dirs under cron_providers:"; ls -d plugins/cron_providers/*/ 2>/dev/null | grep -v __pycache__ | wc -l
```

```text
NAS endpoints:
3
cron.chronos config keys:
callback_url portal_url 
provider dirs under cron_providers:
1
```

### 3.5 `plugins/context_engine/` —— 一个只有发现系统、没有被发现物的目录

```verify
git -C /home/user/hermes-agent ls-files plugins/context_engine/
```

```text
plugins/context_engine/__init__.py
```

**目录里只有发现器本身,零个引擎子目录。** 默认引擎 `compressor` 是内核里的
`ContextCompressor`,不是插件(见该文件 docstring 第 10 行)。
所以这是一个**为第三方预留、自己不占位**的扩展点 —— 与 `cron_providers`
(自己占一个 chronos)恰成对照。

接缝面:公开 API 2 个(`discover_context_engines` / `load_context_engine`),
假 ctx `_EngineCollector` 的方法 5 个,其中只有 `register_context_engine` 与
`register_command` 是真实现,后者还带**两道防撞**:

| 防撞 | 锚点 + 摘录 |
|---|---|
| 拒绝与内建斜杠命令同名 | `plugins/context_engine/__init__.py:235`:`if resolve_command(clean) is not None:` |
| 拒绝覆盖已注册的插件命令 | `plugins/context_engine/__init__.py:248`:`if clean in manager._plugin_commands:` |

### 3.6 `plugins/disk-cleanup/` —— 注册面 3 项、类别面 7 项

注册面:`post_tool_call`、`on_session_end` 两个 hook + `/disk-cleanup` 一个斜杠命令(锚点见 §0.4 表)。

```verify
cd /home/user/hermes-agent
echo "hooks+command registered:"; grep -c 'ctx.register_' plugins/disk-cleanup/__init__.py
echo "categories:"; sed -n '/^ALLOWED_CATEGORIES = {/,/^}/p' plugins/disk-cleanup/disk_cleanup.py | grep -o '"[a-z-]*"' | wc -l
echo "tool names watched by post_tool_call:"
grep -o 'tool_name == "[a-z_]*"' plugins/disk-cleanup/__init__.py | sed 's/.*== "//;s/"//' | tr '\n' ' '; echo
```

```text
hooks+command registered:
3
categories:
7
tool names watched by post_tool_call:
write_file patch terminal 
```

安全边界面三层:

| 层 | 锚点 + 摘录 |
|---|---|
| 路径白名单(只认 `HERMES_HOME` 与 `/tmp/hermes-*`) | `plugins/disk-cleanup/disk_cleanup.py:66`:`def is_safe_path(path: Path) -> bool:` |
| 顶层目录黑名单(21 项,含 `patches`/`projects`/`skins`/`themes` 等用户资产) | `plugins/disk-cleanup/disk_cleanup.py:567`:`def guess_category(path: Path) -> Optional[str]:` |
| cron 专用规则:只有 `cron/output/**` 可清 | `plugins/disk-cleanup/disk_cleanup.py:168`:`def _is_protected_cron_path(p: Path) -> bool:` |

### 3.7 `plugins/security-guidance/` —— 规则面 25 条、模式面 3 种

| 面 | 锚点 + 摘录 |
|---|---|
| 注册 2 个 hook | `plugins/security-guidance/__init__.py:257`:`def register(ctx) -> None:` |
| 被扫描的工具表(3 个) | `plugins/security-guidance/__init__.py:53`:`_TARGET_TOOLS: Dict[str, Tuple[str, Tuple[str, ...]]] = {` |
| 扫描上限 256 KiB | `plugins/security-guidance/__init__.py:63`:`_MAX_SCAN_BYTES = 256 * 1024` |
| 全关开关 | `plugins/security-guidance/__init__.py:70`:`def _plugin_disabled() -> bool:` |

三个被扫工具的字段映射:`write_file`(`path`/`content`)、`patch`(`path`/`new_string`,`patch`)、
`skill_manage`(`file_path`/`file_content`,`new_string`)。
三种模式:默认告警;`SECURITY_GUIDANCE_BLOCK=1` 改为在 `pre_tool_call` 直接拒写;
`SECURITY_GUIDANCE_DISABLE=1` 全关。

规则面 25 条,其中带路径过滤的只有 5 条:

```verify
cd /home/user/hermes-agent && python3 - <<'PYEOF'
src = open('plugins/security-guidance/patterns.py', encoding='utf-8').read()
body = src[src.index('SECURITY_PATTERNS = ['):src.index('\nclass RuleId')]
print("rules=%d path_filter=%d path_check=%d" % (
    body.count('"ruleName":'), body.count('"path_filter":'), body.count('"path_check":')))
PYEOF
```

```text
rules=25 path_filter=4 path_check=1
```

---

## 4. 记号

### 4.0 先定一条口径:插件自己的 `README.md` 算不算「地图」?

**本片判定:算,计入地图级 ▲。** 理由三条:

1. **CLAUDE.md 的原文限定词只挂在 AGENTS.md 上** —— 「README / 仓库根 AGENTS.md /
   website/docs 是作者自绘地图」。`仓库根` 修饰的是 `AGENTS.md`,`README` 没有被限定。
2. **判据应当是"它是什么东西",不是"它在哪个目录"。** 地图之所以会烂,是因为它
   **与代码分开维护、没有任何机械校验、却被读者当成代码行为的陈述**。
   插件 README 三条全中:实测**插件系统这一侧没有任何代码读插件的 `README.md`**。
   搜索面与读数见下(负结论的成本:第一版我私自把 `tests/` 与 `skills/` 排除在外
   报了个小得多的数,那是"我没看见"的另一种说法,故改为报全量再分类)。
3. **与 ▲(码内)的分界正好落在这里**。R11B 把「模块 docstring 与代码注释」拆出去,
   理由是它们与地图的**腐烂方式不同**(改代码时就在眼前)。插件 README 是独立文件,
   改 `patterns.py` 时它不在眼前 —— 腐烂方式与 website/docs 完全同型。

```verify
cd /home/user/hermes-agent
echo "README.md mentions in tracked *.py:"
git grep -n 'README\.md' -- '*.py' | wc -l
echo "README reads inside the plugin loader / plugins CLI:"
git grep -n 'README' -- hermes_cli/plugins.py hermes_cli/plugins_cmd.py | wc -l
```

```text
README.md mentions in tracked *.py:
71
README reads inside the plugin loader / plugins CLI:
0
```

全仓 `.py` 提到 `README.md` 的 71 处里,**插件系统那三个文件(`plugins.py` / `plugins_cmd.py`)一处都没有**;
其余 71 处是散文注释、测试夹具里自己造的 `README.md`、以及若干与插件无关的路径断言。
插件 README 因此是**纯散文**,与 website/docs 同类。

**为保跨轮可比,本片把地图级 ▲ 再分两行报**:`website/docs` 来源 1 条、
`plugins/*/README.md` 来源 2 条。若后续轮次要把插件 README 排除在 ▲ 外,
减掉后一行即可,不必重算。

### 4.1 ■ 代码缺陷(4 条)

**■-1(安全,结清 H-R10G-b 并加强定性):memory 的 `plugin.yaml` 是一个可执行面,
而且触发它的是「读」不是「装」。**

原移交项记的是「除 pip 外还会 `shlex.split()` 执行 manifest 里的命令」。
实测三点,一点比原述更弱、两点更强:

*(a) `check` 命令确实经 `shlex.split()` 成 argv 后执行(无 shell)*:

`hermes_cli/web_server.py:5393 @ 863e313`

```
        try:
            completed = _run_setup_command(
                shlex.split(check_cmd),
                display=check_cmd,
                timeout=20,
            )
```

*(b) 但 `install` 命令**不走 `shlex.split()`** —— 它是 `shell=True` 的整串 bash*:

`hermes_cli/web_server.py:5519 @ 863e313`

```
        if install_cmd:
            try:
                install = _run_setup_command(
                    install_cmd,
                    display=install_cmd,
                    shell=True,
                    timeout=300,
                )
```

| 佐证 | 锚点 + 摘录 |
|---|---|
| `shell=True` 时显式指定 bash | `hermes_cli/web_server.py:5365`:`executable="/bin/bash" if shell else None,` |
| 子进程环境**不做 secret 擦洗** | `hermes_cli/web_server.py:5320`:`env = build_subprocess_env(scrub_secrets=False, inherit_profile_home=False)` |

全仓唯一声明它的清单,内容正是一条 curl-pipe-sh(§3.2 的逐字块)。

*(c) 最要紧的一点:`check` 的执行**不需要用户点"安装"**。* 它被
`_memory_provider_dependencies_installed` 调用,而后者挂在**读状态**的路径上:

`hermes_cli/web_server.py:5254 @ 863e313`

```
def _memory_provider_setup_manifest(name: str) -> Dict[str, Any]:
    manifest = _memory_provider_manifest(name)
    external_dependencies: List[Dict[str, str]] = []
    for raw in manifest.get("external_dependencies") or []:
        if not isinstance(raw, dict):
            continue
        dep = {
            "name": str(raw.get("name") or "").strip(),
            "install": str(raw.get("install") or "").strip(),
            "check": str(raw.get("check") or "").strip(),
        }
        if dep["name"] or dep["install"] or dep["check"]:
            external_dependencies.append(dep)

    return {
        "pip_dependencies": _string_list(manifest.get("pip_dependencies")),
        "external_dependencies": external_dependencies,
        "required_env": _string_list(manifest.get("requires_env")),
    }
```

调用链逐跳:

| 跳 | 锚点 + 摘录 |
|---|---|
| 只读端点 | `hermes_cli/web_server.py:12739`:`@app.get("/api/memory")` |
| 对**每一个**被发现的 provider 取 setup 信息 | `hermes_cli/web_server.py:5941`:`setup = _memory_provider_setup_info(name)` |
| setup 信息里含一次真实执行 | `hermes_cli/web_server.py:5277`:`setup["dependencies_installed"] = _memory_provider_dependencies_installed(setup)` |

`GET /api/dashboard/plugins`(`:16717`)走同一条。
**而它对每一个被发现的 provider 都跑一遍,不看谁是 active、也不看 `plugins.enabled`。**

实测(临时 HERMES_HOME 里造一个假 provider,`check` 命令写一个标记文件,
然后只调 `_memory_provider_setup_info`,不碰安装端点):

```verify
cd /home/user/hermes-agent && PYTHONDONTWRITEBYTECODE=1 HERMES_DISABLE_LAZY_INSTALLS=1 \
  /home/user/hermes-venv/bin/python \
  /home/user/hermes-study/data/r11f/probes/f_memory_manifest_exec.py /home/user/hermes-agent
```

```text
discovered memory providers = 9
probeprov discovered without any plugins.enabled entry = True
marker file created by manifest `check` command = True
setup_info dep name=probe check=/bin/sh -c 'touch <TMP>/MARKER' install=echo never-run-by-this-probe
required_env=[] pip_dependencies=[]
```

**边界侧的正面认定要一并说清**(免得这条被读成"随便谁都能 RCE"):

| 信任边界面 | 强/弱 | 锚点 + 摘录 |
|---|---|---|
| provider 名严格字符白名单,路径穿越走不通 | 强 | `hermes_cli/web_server.py:6021`:`_MEMORY_PROVIDER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")` |
| 清单只能来自真实插件目录 | 强 | `hermes_cli/web_server.py:5230`:`def _memory_provider_manifest(name: str) -> Dict[str, Any]:` |
| 「是不是 memory provider」靠**文本嗅探**,不是签名也不是 opt-in | **弱** | `plugins/memory/__init__.py:85`:`return "register_memory_provider" in source or "MemoryProvider" in source` |

所以真正的门槛是**「把一个目录放进 `~/.hermes/plugins/`」**。
可门槛的另一半低得意外:被认作 memory provider 的**唯一条件**,
是 `__init__.py` 前 8 KiB 里出现两个字符串之一(上表第 3 行)。于是"放进去"与"被执行"之间,
少了插件系统对其它所有类别都设了的那道 `plugins.enabled` 闸。

**可迁移的教训**:清单文件天然被读作**数据**,一旦某个字段的语义是"一条命令",
它就变成了代码分发通道 —— 而阅读它的那条路径(状态展示)通常没人当作执行路径来审。

**■-2:`cron_providers/chronos` 会被通用加载器发现成 `standalone`,而它一旦被 enable 必定失败。**

跳过表里有 `memory` / `context_engine` / `platforms` / `model-providers`,**没有 `cron_providers`**
(§1.1 的逐字块)。chronos 的清单又没写 `kind:`,而 `_parse_manifest` 的启发式只认两类
(memory 与 model-provider),chronos 一类都不沾。结果就是 §1.1 探针输出的那一行
`key=cron_providers/chronos  kind=standalone`。

它的 `register()` 调的是一个真 `PluginContext` 上不存在的方法:

`plugins/cron_providers/chronos/__init__.py:239 @ 863e313`

```
def register(ctx) -> None:
    """Plugin entrypoint — register the Chronos provider with the loader.

    Mirrors the memory-plugin shape; plugins/cron_providers discovery calls this and
    collects the provider via register_cron_scheduler.
    """
    ctx.register_cron_scheduler(ChronosCronScheduler())
```

§1.5 的探针实跑 `_load_plugin(chronos)`,得到
`error="'PluginContext' object has no attribute 'register_cron_scheduler'"`。
`register_cron_scheduler` 在全仓只存在于 `plugins/cron_providers/` 内部
(搜索面:`git grep register_cron_scheduler -- '*.py'`,排除 `tests/` 后 6 处命中全在该目录)。

**这正是 memory 当年踩过、并在代码里留了注释的同一个坑**:

| 对照 | 锚点 + 摘录 |
|---|---|
| memory 有自动矫正,注释写明理由 | `hermes_cli/plugins.py:1618`:`loaded by the general PluginManager (which has no` |
| 矫正条件只认两类,cron 一类都不沾 | `hermes_cli/plugins.py:1622`:`if kind == "standalone" and "kind" not in data:` |

cron_providers 是**同型问题,没做矫正**。
影响有限(chronos 的正路是 `cron.provider: chronos`,不经通用加载器),
但它会以可 enable 的姿态出现在插件列表里,而 enable 它只会得到一行错误。

**■-3:`hooks` 这个清单键,写它的有 10 份,读它的一份都没有。**

`_parse_manifest` 读的是 `provides_hooks`(§1.4 逐字块),而**全仓 0 份清单写 `provides_hooks`**;
10 份清单写的都是 `hooks:`,而**没有任何生产代码读 `hooks:`**。搜索面与分类:

```verify
cd /home/user/hermes-agent
echo "hooks-key hits in tracked *.py:"
git grep -n 'get("hooks")\|get('"'"'hooks'"'"')\|\["hooks"\]' -- '*.py' | wc -l
echo "  of which under tests/:"
git grep -n 'get("hooks")\|get('"'"'hooks'"'"')\|\["hooks"\]' -- 'tests/*.py' | wc -l
echo "  tests that read a plugin.yaml hooks key:"
git grep -ln 'set(data\["hooks"\])' -- 'tests/*.py'
```

```text
hooks-key hits in tracked *.py:
22
  of which under tests/:
12
  tests that read a plugin.yaml hooks key:
tests/plugins/test_langfuse_plugin.py
tests/plugins/test_nemo_relay_plugin.py
```

22 命中里非测试的 10 处逐处核过,**没有一处的入参是 manifest dict**:

| 类别 | 处数 | 代表锚点 + 摘录 |
|---|---:|---|
| 读**用户 config.yaml** 的 `hooks` 配置块 | 8 | `agent/shell_hooks.py:239`:`specs = _parse_hooks_block(cfg.get("hooks"))` |
| 读 `LoadedPlugin` 的**运行时**统计 | 1 | `cli.py:10235`:`if info.get("hooks"):` |
| 与插件无关的迁移脚本 | 1 | `optional-skills/migration/openclaw-migration/scripts/openclaw_to_hermes.py:2401`:`hooks = config.get("hooks") or {}` |

**但要更正一句"完全没人读"的说法**:测试侧有 **2 份**在读,把清单的 `hooks` 当规格断言:

| 读它的测试 | 覆盖的清单 | 锚点 + 摘录 |
|---|---|---|
| langfuse | `plugins/observability/langfuse/plugin.yaml` | `tests/plugins/test_langfuse_plugin.py:29`:`assert set(data["hooks"]) == {` |
| nemo_relay | `plugins/observability/nemo_relay/plugin.yaml` | `tests/plugins/test_nemo_relay_plugin.py:270`:`assert set(data["hooks"]) == {` |

**这恰恰让问题更清楚**:10 份清单里只有这 2 份有测试盯着,另外 8 份(含 byterover)
一个校验都没有 —— 所以坏值能一直躺着。

后果不是"少了个功能",而是**这块面完全没有反馈**:

| 现象 | 锚点 + 摘录 |
|---|---|
| 一个不存在的 hook 名躺在 bundled 清单里 | `plugins/memory/byterover/plugin.yaml:9`:`- on_pre_compress` |
| 它其实是 `MemoryProvider` ABC 的生命周期方法,不是插件 hook | `agent/memory_provider.py:258`:`def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:` |

也就是说,**两套不同的词汇表在同一个键名底下并存了,而没有任何东西会发现**。
§1.4 的普查输出把这一条标成 `[NOT IN VALID_HOOKS]`。

**■-4:`hermes memory` 的帮助文本硬编码 7 个 provider,实际是 8 个(独立复核 H-R11B-B2-b,成立)。**

`hermes_cli/subcommands/memory.py:16 @ 863e313`

```
        help="Configure external memory provider",
        description=(
            "Set up and manage external memory provider plugins.\n\n"
            "Available providers: honcho, openviking, mem0, hindsight,\n"
            "holographic, retaindb, byterover.\n\n"
```

漏的是 `supermemory`(§3.2 的目录枚举给出 8 家)。选择器本身走的是动态发现
(`discover_memory_providers()`),所以**能选到**,只是 `--help` 少列一个。
形态是「硬编码枚举与它所描述的目录漂开了」。

*记号归类说明*:这条既不是地图(不是 README/AGENTS/website),也不是 docstring 或注释
—— 它是**代码产生的用户可见字符串**。现行记号表没有这一格,本片按 ■ 记,
并把口径缺口作为移交项 H-R11F-F-e 提出。

### 4.2 ▲ 地图与代码矛盾(3 条)

**▲-1(website/docs):`provides_web_providers` 被说成由加载器消费,实际无人读。**

`website/docs/developer-guide/web-search-provider-plugin.md:143 @ 863e313`

> | `provides_web_providers` | List of provider `name`s this plugin registers — used by the loader to advertise the plugin in `hermes tools` even before `register()` runs |

整句判定(CLAUDE.md 要求把整句连同它归哪个标题管一起判):这一行在
`## ABC reference` 之前的 **manifest 键表**里,表头是 `| Key | Purpose |`,
所以它是一条**关于这个键有什么用**的断言,不是范例说明。
断言的两半都不成立:(a) 加载器不读它 —— `_parse_manifest` 的 8 个键里没有它,
`PluginManifest` 也没有对应字段;(b) 不存在"在 `register()` 之前公示"的状态,
因为 bundled backend 走的是无条件加载(§1.2 第 4 条),发现即 register。
真正能在 register 之前公示的键是 `provides_tools`,它确实有三个消费方(§1.4 表)。
负结论搜索面见 §1.4 的 `git grep` verify 块(全文件类型 10 命中、`*.py` 0 命中)。

`provides_browser_providers` 在姊妹文档的验收清单里同样出现,消费方同样为零 ——
但那句是 checklist 措辞(「`plugin.yaml` declares …」),**字面为真**(清单里确实声明了),
按 CLAUDE.md「字面为真就不是 ▲」**不计**:

| 出处 | 判定 | 锚点 + 摘录 |
|---|---|---|
| 姊妹文档验收清单 | 字面为真,不计 ▲ | `website/docs/developer-guide/browser-provider-plugin.md:153`:`provides_browser_providers` |

**▲-2(插件 README):`security-guidance` 说每条规则都带路径过滤,实际 25 条里只有 4 条。**

`plugins/security-guidance/README.md:33 @ 863e313`

> The pattern data uses Python regex + literal-substring matching. Each rule
> carries a per-extension `path_filter` lambda — Python-only rules skip `.js`,
> JS rules skip `.py`, all rules skip `.md/.txt/.rst/.json/.yaml`.

整段三个子断言,逐个判:

| 子断言 | 判定 | 依据(锚点 + 摘录) |
|---|---|---|
| 「Each rule carries a per-extension `path_filter` lambda」 | **假** | §3.7 verify 块:`rules=25 path_filter=4 path_check=1` |
| 「Python-only rules skip `.js`」 | **真但覆盖面极小**(仅 2 条) | `plugins/security-guidance/patterns.py:151`:`"path_filter": lambda p: p.endswith(_PY_EXTS),` |
| 「all rules skip `.md/.txt/.rst/.json/.yaml`」 | **假**(仅 1 条) | `plugins/security-guidance/patterns.py:127`:`"path_filter": lambda p: not p.endswith(_DOC_EXTS),` |

后果是实打实的:`os_system_injection` 只扫 `.py`,而 `pickle_variants_load`、
`aes_ecb_mode`、`tls_verification_disabled` 等 20 条**没有任何路径门**,
会照样扫进 `.md` 文档里的示例代码 —— 恰恰是 README 承诺不会发生的那件事。

**▲-3(插件 README):`disk-cleanup` 说自动追踪 `*.test.*`,实际只认 4 个固定后缀。**

`plugins/disk-cleanup/README.md:16 @ 863e313`

> | `post_tool_call` | When `write_file` / `terminal` / `patch` creates a file matching `test_*`, `tmp_*`, or `*.test.*` inside `HERMES_HOME`, track it silently as `test` / `temp` / `cron-output`. |

代码里的后缀是一张**闭表**,不是通配:

`plugins/disk-cleanup/disk_cleanup.py:563 @ 863e313`

```
_TEST_PATTERNS = ("test_", "tmp_")
_TEST_SUFFIXES = (".test.py", ".test.js", ".test.ts", ".test.md")
```

于是 `foo.test.tsx` / `foo.test.go` / `foo.test.sh` 都不会被追踪。
同一行还有第二个偏差:名字规则只可能产出 `test` 这一个类别;
`temp` 只来自 `$HERMES_HOME/cache/**`、`cron-output` 只来自 `cron/output/**`,
与名字模式无关(`guess_category` 函数体,锚点见 §3.6 表)。
**这是本轮"整句判定"规矩的一个正面样本**:
半句(`test_*`/`tmp_*` → `test`)是真的,另半句(`*.test.*`、三个类别都由名字决定)是假的。

### 4.3 ▲(码内)文档字符串/注释与代码矛盾(2 条,与地图级分开计数)

**▲(码内)-1:`discover_context_engines` 自称"不 import 引擎",而它 import 并执行引擎模块。**

`plugins/context_engine/__init__.py:33 @ 863e313`

```
def discover_context_engines() -> List[Tuple[str, str, bool]]:
    """Scan plugins/context_engine/ for available engines.

    Returns list of (name, description, is_available) tuples.
    Does NOT import the engines — just reads plugin.yaml for metadata
    and does a lightweight availability check.
    """
```

同一函数体里的"轻量可用性检查"就是完整加载:

`plugins/context_engine/__init__.py:63 @ 863e313`

```
        # Quick availability check — try loading and calling is_available()
        available = True
        try:
            engine = _load_engine_from_dir(child)
            if engine is None:
                available = False
            elif hasattr(engine, "is_available"):
                available = engine.is_available()
        except Exception:
            available = False
```

`_load_engine_from_dir` 会把目录里**每一个 `.py`** 都 exec 一遍,再 exec `__init__.py`:

| 步骤 | 锚点 + 摘录 |
|---|---|
| 先 exec 每个子模块 | `plugins/context_engine/__init__.py:164`:`sub_spec.loader.exec_module(sub_mod)` |
| 再 exec `__init__.py` | `plugins/context_engine/__init__.py:169`:`spec.loader.exec_module(mod)` |
| 对照组(同族模块,docstring 与行为一致) | `plugins/memory/__init__.py:146`:`def list_memory_provider_names() -> List[str]:` |

对照组那份的 docstring 明写「does NOT import provider modules」,而它确实只做目录扫描
—— 说明作者知道这个区别,只是 context_engine 这一份没跟上。
当前无实害(目录为空,§3.5),但这正是"扩展点空着所以没人发现"的形态。

**▲(码内)-2:`security-guidance` 模块 docstring 说"接一个行为",实际注册两个 hook。**

`plugins/security-guidance/__init__.py:3 @ 863e313`

> Wires one behaviour:
>
> * ``transform_tool_result`` hook — scans the *content being written* by

而 `register()` 注册的是两个:

| 实际注册 | 锚点 + 摘录 |
|---|---|
| 第一个 hook(docstring 没提) | `plugins/security-guidance/__init__.py:258`:`ctx.register_hook("pre_tool_call", _on_pre_tool_call)` |
| 第二个 hook(docstring 提了) | `plugins/security-guidance/__init__.py:259`:`ctx.register_hook("transform_tool_result", _on_transform_tool_result)` |
| 同一作者的姊妹插件,同套写法且数对得上 | `plugins/disk-cleanup/__init__.py:3`:`Wires three behaviours:` |

所以这不是措辞习惯问题,是这一份漏了 `pre_tool_call`。

### 4.4 ◇ 代码有、文档无(2 条)

**◇-1:teams_pipeline 有第二条、绕过插件协议的宿主直连入口。**
gateway 直接 import 插件模块、并按名字判定启用(两个锚点见 §3.3 的接缝表),
插件系统文档里的插件生命周期(发现 → 加载 → `register(ctx)`)完全描述不了这条路径。

**◇-2:web-search ABC 有 `get_setup_schema()`,该篇开发者文档的方法表没有它。**
8 家 bundled provider **全部实现**(§3.1 verify 块 `providers implementing get_setup_schema(): 8`),
而 `website/docs/developer-guide/web-search-provider-plugin.md` 的
「Methods you may override」表列了 7 个成员、不含它。

| 事项 | 锚点 + 摘录 |
|---|---|
| ABC 里确实有 | `agent/web_search_provider.py:186`:`def get_setup_schema(self) -> Dict[str, Any]:` |
| 兄弟文档给了整整一节 | `website/docs/developer-guide/browser-provider-plugin.md:114`:`get_setup_schema()` |

**记 ◇ 不记 ▲**:该表上一句是「Full contract in `agent/web_search_provider.py`」,
把完备性显式外包给了源码,所以表本身不构成"仅此七个"的断言;
兄弟文档写了而这一篇没写,说明是漏了,不是有意省略。

### 4.5 ◎ 文档成立但显著保守(1 条)

**◎-1:`disk-cleanup` README 的安全清单比代码保守。**

`plugins/disk-cleanup/README.md:47 @ 863e313`

> - `$HERMES_HOME/logs/`, `memories/`, `sessions/`, `skills/`, `plugins/`,
>   and config files are never tracked

代码里的顶层黑名单**共 21 项**,除 README 列的以外还护住了
`patches` / `projects` / `skins` / `themes` / `contributors` / `profiles` / `backups` /
`optional-skills`,且 cron 面另有专门规则只放行 `cron/output/**`(均在 `guess_category` 函数体内,锚点见 §3.6 表)。
字面为真、范围偏小,按 ◎ 不按 ▲。

---

## 5. 判据五条自报

| # | 判据 | 自报 | 依据 |
|---|---|---|---|
| 1 | 点名到位 | **达成** | §0 四张表,69/69 全路径 + 一句话角色;同型薄文件(8 份 `web/*/__init__.py`、20 份 `plugin.yaml`、9 份 README)归组叙述但**组内逐个列了全路径** |
| 2 | 接缝穷举 | **达成** | §1.4(清单键面,20 份逐份列全 + 11 个键的消费方全表)、§1.5(注册面 18 + hook 面 24)、§3.1(8 家 × 8 成员的 ABC 矩阵)、§3.2(8 家 requires_env/optional_env/pip_dependencies 逐条)、§3.3(11 个 CLI 子命令)、§3.4(3 端点 + 2 配置键 + 1 JWT 边界)、§3.5(0 引擎)、§3.6(3 注册项 + 7 类别 + 3 工具)、§3.7(25 规则 + 3 工具 + 3 模式)。每处都给了机械枚举命令与条数 |
| 3 | 端到端链 | **达成** | §2,14 跳,取的正是派工书点名的「宿主发现并加载一个插件」那条 |
| 4 | 逐字取证 | **达成** | 逐字源码围栏 **16 个**(另有 `>` 文档引用块若干);关卡实测 `citations=24 OK=24`,可校验比例 **100%**、`table_anchors=117 OK=117` |
| 5 | 记号 | **达成** | ■ 4、▲(地图) 3、▲(码内) 2、◇ 2、◎ 1,全部带锚点 |

**判据本身是否需要修订**(派工书列为验收项):**需要补一格,不需要降要求。**
■-4 那种「**代码产生的用户可见字符串**与它所描述的目录漂开」既非地图、
也非 docstring/注释,现行 ▲ / ▲(码内) / ◇ / ■ 四格都不贴切。
本片按 ■ 记并在移交里提出,而不是自行新造记号 —— 新记号会让跨轮计数不可比,
这正是 R11B 把 ◎ 从 ▲ 里拆出来时给的理由。

---

## 6. 移交项(锚点 + 一句话现象)

| 案号 | 锚点 + 现象 | 建议去向 |
|---|---|---|
| **H-R11F-F-a** | `hermes_cli/web_server.py:5519`:`if install_cmd:` —— memory 清单的 `install` 字段以 `shell=True` + `/bin/bash` 执行,`check` 字段在**只读**端点上就会执行;而 memory 的发现只靠文本嗅探,不经 `plugins.enabled`。**已实测**(§4.1 ■-1) | 归入安全面章节;R12 蓝图的「扩展点信任边界」一节应引用 |
| **H-R11F-F-b** | `hermes_cli/plugins.py:1361`:`skip_names={"memory", "context_engine", "platforms", "model-providers"},` —— 跳过表漏了 `cron_providers`,于是 `cron_providers/chronos` 被发现成 `standalone`,enable 后必然抛 `AttributeError`。**已实测** | 与 memory 的 kind 自动矫正并列写进"类别发现系统"一节 |
| **H-R11F-F-c** | `hermes_cli/plugins.py:1664`:`provides_hooks=data.get("provides_hooks", []),` —— 解析器读 `provides_hooks`(全仓 0 份清单声明),10 份清单写的是 `hooks`(无人读);因此那个不存在的 hook 名 `on_pre_compress` 从未被任何东西发现 | 「清单无 schema 校验」的最佳单例,写进公共面章节 |
| **H-R11F-F-d** | `website/docs/developer-guide/web-search-provider-plugin.md:143`:`List of provider` —— 该行说加载器用 `provides_web_providers` 在 `register()` 前公示插件,实测全仓 `*.py` 零消费方 | 计入本轮地图级 ▲;`provides_browser_providers` 同状况但文档措辞字面为真,不计 |
| **H-R11F-F-e** | `hermes_cli/subcommands/memory.py:18`:`"holographic, retaindb, byterover.\n\n"` —— **记号口径缺口**:这是「代码产生的用户可见字符串」与目录漂开,既非地图 ▲、也非 ▲(码内)。本片暂按 ■ 记 | 请主线裁定是否需要第五个记号(或明确并入 ■),裁定前各片按 ■ 记以免计数不可比 |
| **H-R11F-F-f** | `plugins/context_engine/__init__.py:37`:`Does NOT import the engines — just reads plugin.yaml for metadata` —— docstring 与 `:66` 的 `_load_engine_from_dir(child)` 直接矛盾;当前无实害只因该目录**零个引擎子目录** | ▲(码内);另可作为"空扩展点"设计取舍的例子 |
| **H-R11F-F-g** | `plugins/security-guidance/README.md:34`:`carries a per-extension` —— 25 条规则里只有 4 条有 `path_filter`,承诺的"所有规则跳过 `.md/.txt/...`"实际只有 1 条做到 | 地图级 ▲;同时是"安全插件的误报面比文档说的大"的实例 |

---

## 7. 环境与边界自查

- 基线只读:开工与收工各断言一次 `git -C /home/user/hermes-agent status --porcelain` 为空;
  全部探针加 `PYTHONDONTWRITEBYTECODE=1`,不落 `.pyc`。
- 惰性安装:所有执行基线代码的命令均带 `HERMES_DISABLE_LAZY_INSTALLS=1`。
- venv:用共享 venv(**87 包**),**未安装任何东西**、未改任何共享环境。
- 未改 `scripts/`、`chapters/`、台账、`CLAUDE.md`;未碰 `data/inflight/*.claim`。
- 网络:本片全部结论均由本地静态读取与本地执行得出,**未发起任何外部网络请求**;
  无被拦域名要报。

---

## 完成信号

- **片号**:R11F 片 F —— 长尾插件 + 插件系统公共面
  (`plugins/{web, teams_pipeline, memory, disk-cleanup, security-guidance, cron_providers, context_engine}`
  \+ `plugins/plugin_utils.py` + `plugins/__init__.py`,69 文件 / 9,753 行)。

- **产出文件**:
  - 底稿 `notes/r11f-raw-f-longtail-and-plugin-core.md`(本文件)
  - 探针 `data/r11f/probes/f_scanner_kinds.py` —— 用宿主自己的 `_scan_directory` 枚举顶层清单发现结果(key/kind/source)
  - 探针 `data/r11f/probes/f_chronos_ctx_gap.py` —— 枚举 `PluginContext` 的 18 个 `register_*`,并实跑 `_load_plugin(chronos)` 取错误
  - 探针 `data/r11f/probes/f_manifest_keys.py` —— 片内 20 份清单键集逐份列全,标注加载器读/不读
  - 探针 `data/r11f/probes/f_hooks_key_census.py` —— 全仓 `hooks` vs `provides_hooks` 键普查,并对 `VALID_HOOKS` 校验取值
  - 探针 `data/r11f/probes/f_memory_manifest_exec.py` —— 实证 memory 清单是可执行面(临时 HERMES_HOME,自清理)

- **五条判据**(逐条):
  1. **点名到位 —— 达成**。69/69 全路径 + 一句话角色(§0)。
  2. **接缝穷举 —— 达成**。9 处接缝面逐项列全,每处附机械枚举命令与条数(§1.4、§1.5、§3.1–§3.7)。
  3. **端到端链 —— 达成**。§2 一条 14 跳链,逐跳带锚点,取的是「宿主发现并加载一个插件 → 用户拿到搜索结果」。
  4. **逐字取证 —— 达成**。逐字源码围栏 **16 个**,另有 `>` 文档引用块若干。
  5. **记号 —— 达成**。■ 4 / ▲(地图) 3 / ▲(码内) 2 / ◇ 2 / ◎ 1,全部带锚点。
  - **判据修订建议(验收项)**:不降要求,补一格 —— 「代码产生的用户可见字符串与代码事实矛盾」
    现无记号可归,本片暂按 ■ 记,提为 H-R11F-F-e 请主线裁定。

- **两道阻断关卡(本文件)**:
  - `verify_citations.py` 退出码 **0** —— `citations=24  OK=24`,
    **可校验比例 100%**(下限 70%);`table_anchors=117  OK=117`,无 DRIFT / OUT-OF-RANGE。
  - `verify_evidence_commands.py` 退出码 **0** —— `paired=15  unpaired=0  differing=0`。
  - 合并跑强制范围(`chapters/*.md` + 本文件)两者亦为退出码 0。
  - *过程中关卡实拦两次,如实记下*:(a) 有两个 ```verify 块我先写了预期输出、
    没真跑,关卡以 `EVIDENCE-DIFF` 当场判错(`ABC members` 与 `categories` 两个数);
    (b) 两条负结论的搜索面被我私自排除了 `tests/`,读数偏小,已改为报全量再分类
    (`README.md` 6→**71**、`hooks` 键 11→**22**),结论不变但成本写清楚了。

- **点名文件数**:**69 / 69**。

- **接缝枚举命令与条数**(每条都在正文里配了 ```verify + ```text):

  | 接缝面 | 条数 | 所在节 |
  |---|---:|---|
  | 顶层清单发现结果(key/kind) | 33 | §1.1 |
  | 片内 `plugin.yaml` 顶层键(不同键) | 11(20 份清单) | §1.4 |
  | `provides_web_providers` 的 Python 消费方 | **0**(提及它的文件 10) | §1.4 |
  | 全仓声明 `hooks:` / 声明 `provides_hooks:` 的清单 | 10 / **0** | §1.4 |
  | `PluginContext` 的 `register_*` 方法 | 18 | §1.5 |
  | `VALID_HOOKS` | 24 | §1.5 |
  | web ABC 成员 / 实现 `extract()` / 实现 `get_setup_schema()` / provider 目录 | 8 / 4 / 8 / 8 | §3.1 |
  | bundled memory provider 目录 | 8 | §3.2 |
  | `teams-pipeline` CLI 子命令 | 11 | §3.3 |
  | NAS 端点 / `cron.chronos.*` 配置键 / cron provider 目录 | 3 / 2 / 1 | §3.4 |
  | `plugins/context_engine/` 被追踪文件 | 1(引擎子目录 **0**) | §3.5 |
  | disk-cleanup 注册项 / 类别 / 被监视工具 | 3 / 7 / 3 | §3.6 |
  | security-guidance 规则 / 带 `path_filter` / 带 `path_check` | 25 / 4 / 1 | §3.7 |
  | `hooks` 键在 `*.py` 的全部命中 / 其中在 `tests/` / 读清单 `hooks` 的测试 | 22 / 12 / **2** | §4.1 ■-3 |
  | `README.md` 在 `*.py` 的全部命中 / 插件加载器与 CLI 里的 | 71 / **0** | §4.0 |

- **新铸记号编号**:`H-R11F-F-a`、`H-R11F-F-b`、`H-R11F-F-c`、`H-R11F-F-d`、
  `H-R11F-F-e`、`H-R11F-F-f`、`H-R11F-F-g`(七条,一号一实体,均带锚点 + 一句话现象,见 §6)。

- **口径裁定(对全轮 ▲ 计数有影响,请主线知悉)**:本片判定
  **插件自己的 `README.md` 计入地图级 ▲**(理由三条见 §4.0),
  并把地图级 ▲ 分两行报以保跨轮可比 —— `website/docs` 来源 **1** 条、
  `plugins/*/README.md` 来源 **2** 条。
