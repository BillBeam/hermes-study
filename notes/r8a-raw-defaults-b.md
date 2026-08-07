# r8a-raw-defaults-b · config_defaults.py:2200-4313

底稿。基线 `NousResearch/hermes-agent @ 863e31318553cda8ad61df681d08175364d4164b`(下简写 `863e313`)。
本段覆盖 `hermes_cli/config_defaults.py` 第 **2200 行到文件末尾 4313 行**,即:

- `DEFAULT_CONFIG` 的后半段(从 `cron.chronos` 收尾一直到 `_config_version`,结束于 3127 行);
- `OPTIONAL_ENV_VARS` 全表(3130-4313 行)。

同轮的 defaults-a 覆盖 1-2199 行。两段在 `cron` 块内部交接(`cron` 块起于 2161 行),
本底稿为叙述完整会把 `cron.chronos` 四个键一起交代,并标出哪几个落在 2200 之前。

---

## 0. 模块性质:一个"纯数据叶子模块"

文件开头的 docstring 把这个模块的契约写死了:它只装数据,并且**不许**反向 import 配置层。
`hermes_cli/config_defaults.py:1 @ 863e313`

```python
"""Default configuration data for Hermes Agent.

Pure-data leaf module: DEFAULT_CONFIG and OPTIONAL_ENV_VARS, extracted
verbatim from hermes_cli/config.py. Must not import from hermes_cli.config.
"""
```

这条契约在基线上是**成立**的:全文件 4313 行,没有任何 `import` 语句(我用
`grep -c '^import \|^from ' hermes_cli/config_defaults.py` 得到 0;文中出现 "import" 的四处都在注释里)。
它解决的问题是**循环依赖**:`hermes_cli/config.py` 自身很重(5000+ 行,含 setup/migration/dashboard 支撑),
而 `tools/environments/local.py`、`hermes_cli/env_loader.py`、`hermes_cli/provider_catalog.py` 这些
早启动路径需要在 `config.py` 完全初始化之前就拿到键表。把纯数据劈出来后,这些模块可以直接
`from hermes_cli.config_defaults import OPTIONAL_ENV_VARS`,不用 lazy-import 兜圈子。

`config.py` 用一行 re-export 把两个名字接回自己的命名空间,保持历史 import 路径不破。
`hermes_cli/config.py:943 @ 863e313`

```python
from hermes_cli.config_defaults import DEFAULT_CONFIG, OPTIONAL_ENV_VARS  # noqa: F401
```

**取舍**:re-export 意味着**存在两条 import 路径**指向同一个 dict 对象
(`hermes_cli.config.OPTIONAL_ENV_VARS` 与 `hermes_cli.config_defaults.OPTIONAL_ENV_VARS`)。
这在这里是**故意**的——见第 3 节:`config.py` 在 import 时会**原地 mutate** 这个 dict,
所以两条路径必须指向同一个对象,否则注入的 provider/plugin 键就只有一半的消费者能看见。
代价是:谁从 `config_defaults` 直接导入且在 `config.py` import 之前读表,就会看到**未注入**的短表。
`env_loader.py` 正是这样直接导入的(它同时 lazy-import `config._EXTRA_ENV_KEYS`,顺带触发了注入,
所以实际不出问题——但这是巧合而非设计保证)。`hermes_cli/env_loader.py:63 @ 863e313`

```python
    from hermes_cli.config import _EXTRA_ENV_KEYS
    from hermes_cli.config_defaults import OPTIONAL_ENV_VARS

    return set(OPTIONAL_ENV_VARS.keys()) | set(_EXTRA_ENV_KEYS)
```

---

## 1. `DEFAULT_CONFIG` 后半段的四重身份

在逐块列键之前,先说清这张表**被谁用**——因为"往 DEFAULT_CONFIG 里加一个键"这个动作
同时触发四件事,这是本文件最重要的机制。

### 1.1 身份一:read-time 深合并的默认值来源

`load_config()` 从 `DEFAULT_CONFIG` 出发深合并用户 YAML,所以**缺键即生效默认值**,
不需要把默认写进磁盘。`hermes_cli/config.py:1817 @ 863e313`

```python
    ``load_config()`` deliberately starts from ``DEFAULT_CONFIG`` and deep-merges
```

### 1.2 身份二:root 键白名单

配置校验的"允许的顶层键"集合是从 `DEFAULT_CONFIG.keys()` 派生的,加一个新 section
自动被接受,不用改校验表。`hermes_cli/config.py:1881 @ 863e313`

```python
_KNOWN_ROOT_KEYS = frozenset(DEFAULT_CONFIG.keys()) | _EXTRA_KNOWN_ROOT_KEYS
```

补集 `_EXTRA_KNOWN_ROOT_KEYS` 列了 20 个"磁盘上合法但故意不进 DEFAULT_CONFIG"的 root
(`mcp_servers`、`plugins`、`image_gen`、`platforms`、各种 gateway 顶层便捷形式……)。
`hermes_cli/config.py:1854 @ 863e313`

```python
_EXTRA_KNOWN_ROOT_KEYS = {
```

### 1.3 身份三:`hermes config check` 的"新选项"扫描

递归遍历 `DEFAULT_CONFIG` 树,报告用户配置里缺的每一条路径。
`hermes_cli/config.py:1213 @ 863e313`

```python
    _check(DEFAULT_CONFIG, config)
```

关键:migration **不会**把这些键落盘,只做信息展示——因为 1.1 的深合并已经让缺键生效。
`hermes_cli/config.py:2356 @ 863e313`

```python
    # New default keys are NOT materialised to disk: load_config() deep-merges
```

### 1.4 身份四:dashboard 配置编辑器的 schema

`DEFAULT_CONFIG` 被走一遍,产出"点分路径 → UI 字段"的扁平 schema;字段类型**由默认值的
Python 类型推断**。`hermes_cli/web_server.py:1117 @ 863e313`

```python
CONFIG_SCHEMA = _build_schema_from_config(DEFAULT_CONFIG)
```

`hermes_cli/web_server.py:1062 @ 863e313`

```python
def _infer_type(value: Any) -> str:
    """Infer a UI field type from a Python value."""
    if isinstance(value, bool):
        return "boolean"
```

这条身份带来两个**在本段大量踩到**的后果,详见 §6 缺陷 D1/D2:

- **空 dict `{}` 的默认值会递归进"没有叶子",于是完全不产生 schema 条目**,即
  该键在 dashboard 配置页**不可见**。`hermes_cli/web_server.py:1099 @ 863e313`

  ```python
        if isinstance(value, dict):
            # Recurse into nested dicts
            schema.update(_build_schema_from_config(value, full_key))
  ```

  本段中因此隐形的键:`model_catalog.providers`、`monitoring.export.otlp.headers_env`、
  `onboarding.seen`、`lsp.servers`、`secrets.onepassword.env`。

- **`None` 默认值被推断成 `"string"`**(`_infer_type` 走到最后一行 fallthrough),
  哪怕它语义上是 int / bool / list。本段中受影响:`cron.max_parallel_jobs`(int)、
  `kanban.max_in_progress_per_profile`(int)、`x_search.reasoning_effort`(枚举串,还行)、
  `computer_use.no_overlay`(三态 bool)、`proxy.upstream_deny_cidrs`(list)。

`_config_version` 被显式跳过,不进 schema。`hermes_cli/web_server.py:1087 @ 863e313`

```python
        if full_key in {"_config_version"}:
```

---

## 2. `DEFAULT_CONFIG` 逐块穷举(2200-3127)

下面每块给:块起始行的可核验引用 + 该块**全部叶子键**(点分路径 / 默认值 / 语义要点 / 读取点)。
表格里的引用脚本记为 UNCHECKED(它们是"指向某行"的溯源,不是断言正文)。

### 2.1 `cron.chronos.*` —— NAS 托管定时器的四件套(2190-2203,跨段边界)

Chronos 是 Nous 侧的托管 cron:agent 把一次性任务"武装"到 NAS(Nous 的门户/调度服务),
到点由 NAS 反向 POST `{callback_url}/api/cron/fire`,请求带一个 JWT。四个键正好覆盖
"往哪注册 / 我的公网地址 / 我期望的 audience / 用谁的公钥验签"。

本段(≥2200)只含最后一个键;前三个在 2193/2197/2199,属 defaults-a 段,列出以便理解整块。

| 点分路径 | 默认值 | 语义 | 定义行 |
|---|---|---|---|
| `cron.chronos.portal_url` | `"https://portal.nousresearch.com"` | NAS/门户基址,同时是签发者(issuer) | `hermes_cli/config_defaults.py:2193` |
| `cron.chronos.callback_url` | `""` | agent **自己**的公网基址;空 → Chronos 不可用,回落内置 ticker | `hermes_cli/config_defaults.py:2197` |
| `cron.chronos.expected_audience` | `""` | 期望的 JWT `aud`,形如 `agent:{instance_id}` | `hermes_cli/config_defaults.py:2199` |
| `cron.chronos.nas_jwks_url` | `""` | NAS JWKS(公钥集)URL;**空 → fire 端点拒绝一切 token,不做无签名解码** | `hermes_cli/config_defaults.py:2202` |

`hermes_cli/config_defaults.py:2200 @ 863e313`

```python
            # NAS JWKS URL for verifying the inbound fire JWT's signature.
            # Empty → the fire endpoint refuses all tokens (no unsigned decode).
            "nas_jwks_url": "",
```

**为什么这么设计**:默认全空 = fail-closed。可用性判定在 provider 插件里,只要 `portal_url`
与 `callback_url` 任一为空就宣告不可用。`plugins/cron_providers/chronos/__init__.py:72 @ 863e313`

```python
        if not (_cfg("cron", "chronos", "portal_url") and _cfg("cron", "chronos", "callback_url")):
```

验签侧同一组键被两个入口共用(gateway 内嵌的 API server 与 dashboard 的 cron 路由),
两处读法一致。`gateway/platforms/api_server.py:5665 @ 863e313`

```python
            expected_audience=cfg_get(cfg, "cron", "chronos", "expected_audience", default=""),
            jwks_or_key=cfg_get(cfg, "cron", "chronos", "nas_jwks_url", default="") or None,
```

`hermes_cli/web_routers/cron.py:151 @ 863e313`

```python
        expected_audience=cfg_get(cfg, "cron", "chronos", "expected_audience", default=""),
```

**取舍**:`nas_jwks_url` 为空时"拒绝一切"而不是"跳过验签",意味着**配了 callback_url 却忘了
JWKS 的实例,Chronos 会静默地一次都不触发**——因为可用性检查(§上)不看 `nas_jwks_url`。
这是一个"半配好"的坑,见 §6 D8。

### 2.2 `cron.*` 其余键(2204-2243)

| 点分路径 | 默认值 | 语义 | 定义行 / 读取点 |
|---|---|---|---|
| `cron.wrap_response` | `True` | 投递的 cron 结果加头(任务名)加尾("The agent cannot see this message") | 定义 `:2206` / 读 `cron/scheduler.py:1510` |
| `cron.mirror_delivery` | `False` | cron 简报**可续聊**:线程优先,DM 平台退化为镜进原 DM 会话 | 定义 `:2227` / 读 `cron/scheduler.py:646` |
| `cron.max_parallel_jobs` | `None` | 每 tick 并行跑的到期任务上限;`null/0`=无限,`1`=串行 | 定义 `:2232` / 读 `cron/scheduler.py:4240` |
| `cron.output_retention` | `50` | `save_job_output` 保留最近 N 个 `.md`;≤0 关闭清理 | 定义 `:2236` / 读 `cron/jobs.py:2538` |
| `cron.session_db_timeout_seconds` | `10` | cron 任务内 `SessionDB()` 初始化的超时;`0`=不限 | 定义 `:2242` / 读 `cron/scheduler.py:2947` |

`hermes_cli/config_defaults.py:2206 @ 863e313`

```python
        "wrap_response": True,
```

`mirror_delivery` 的注释是本文件里信息量最大的一段之一:它把"续聊"的**平台分叉**写清楚了——
线程能力平台开专用 thread 并 seed 该 thread 的会话;DM-only 平台(WhatsApp / Signal / SMS)
没有 thread,就把简报镜进来源 DM 会话。并强调只碰 origin chat,fan-out/broadcast 目标永不镜像。
`hermes_cli/config_defaults.py:2227 @ 863e313`

```python
        "mirror_delivery": False,
```

`cron/scheduler.py:646 @ 863e313`

```python
        return bool((cfg.get("cron", {}) or {}).get("mirror_delivery", False))
```

`max_parallel_jobs` 的解析顺序是 **env > config.yaml > 无限**,且 `int(x) or None` 让 `0` 也变无限。
`cron/scheduler.py:4226 @ 863e313`

```python
        # Resolve max parallel workers: env var > config.yaml > unbounded.
        # Set HERMES_CRON_MAX_PARALLEL=1 to restore old serial behaviour.
        _max_workers: Optional[int] = None
        try:
            _env_par = os.getenv("HERMES_CRON_MAX_PARALLEL", "").strip()
```

`session_db_timeout_seconds` 的存在理由(注释里说得很直白)是:`SessionDB` 自己**没有**
针对卡死的 `sqlite3.connect` 的超时,一旦无限挂起就把该任务的 dispatch guard 永久占死。
`hermes_cli/config_defaults.py:2237 @ 863e313`

```python
        # Timeout (seconds) for SessionDB() init inside cron jobs.
```

`cron/scheduler.py:2933 @ 863e313`

```python
        _raw_env_timeout = os.getenv("HERMES_CRON_SESSION_DB_TIMEOUT", "").strip()
```

### 2.3 `kanban.*` —— 多 agent 协作调度器(2245-2312)

块头注释交代了整个 dispatcher 循环的形状:每 N 秒 tick 一次,回收过期 claim,把依赖满足的
todo 提升为 ready,然后对每个可认领的 ready 任务 fork 一个 `hermes -p <assignee> chat -q ...`。
并明确"一个 profile 一个 dispatcher 就够;同一 kanban.db 上跑多个会抢 claim"。
`hermes_cli/config_defaults.py:2245 @ 863e313`

```python
    # Kanban multi-agent coordination — controls the dispatcher loop that
    # spawns workers for ready tasks. The dispatcher ticks every N seconds
```

| 点分路径 | 默认值 | 语义 | 定义行 / 读取点 |
|---|---|---|---|
| `kanban.auto_subscribe_on_create` | `True` | `kanban_create` 时自动把发起会话订阅到完成/阻塞事件,免轮询 | `:2259` / `tools/kanban_tools.py:1393` |
| `kanban.dispatch_in_gateway` | `True` | 在 gateway 进程内跑 dispatcher(空闲时约 300µs/tick) | `:2265` / `gateway/kanban_watchers.py:991` |
| `kanban.dispatch_interval_seconds` | `60` | tick 间隔 | `:2268` / `gateway/kanban_watchers.py:1029` |
| `kanban.failure_limit` | `2` | 同 task/profile 连续非成功次数达标即自动 block;换 assignee 重置 | `:2272` / `gateway/kanban_watchers.py:1068` |
| `kanban.worker_log_rotate_bytes` | `2 * 1024 * 1024` | worker stdout/stderr 日志 spawn 时轮转阈值 | `:2276` / `hermes_cli/kanban_db.py:8699` |
| `kanban.worker_log_backup_count` | `1` | 保留几个轮转备份 | `:2277` / `hermes_cli/kanban_db.py:8704` |
| `kanban.orchestrator_profile` | `""` | Triage 分解后根任务给谁;空 → 默认 profile | `:2283` / `hermes_cli/kanban_decompose.py:187` |
| `kanban.default_assignee` | `""` | 匹配不到 profile 的子任务落到谁;空 → 默认 profile("assignee 永不为 None") | `:2287` / `gateway/kanban_watchers.py:1104` |
| `kanban.max_in_progress_per_profile` | `None` | 单 profile 并发 worker 上限(#21582);None=不限 | `:2296` / `gateway/kanban_watchers.py:1117` |
| `kanban.auto_decompose` | `True` | 每 tick 自动对落入 Triage 的任务跑分解器 | `:2301` / `gateway/kanban_watchers.py:50` |
| `kanban.auto_decompose_per_tick` | `3` | 每 tick 最多分解几个,防止批量导入烧一波辅助 LLM 调用 | `:2305` / `gateway/kanban_watchers.py:52` |
| `kanban.dispatch_stale_timeout_seconds` | `14400` | 超过这么久没心跳的 running 任务被回收为 ready(先杀本机 worker);0=关闭 | `:2311` / `gateway/kanban_watchers.py:1087` |

`hermes_cli/config_defaults.py:2259 @ 863e313`

```python
        "auto_subscribe_on_create": True,
```

`hermes_cli/config_defaults.py:2276 @ 863e313`

```python
        "worker_log_rotate_bytes": 2 * 1024 * 1024,
        "worker_log_backup_count": 1,
```

注意 `2 * 1024 * 1024` 是**表达式**而非字面量——这让 `ast.literal_eval` 整表解析直接抛
`ValueError: malformed node`(我实测过),想静态读这张表必须 `exec`。这是一个对**工具链**
的隐性约束(schema 导出脚本、文档生成器都得能 exec 这个模块)。

`gateway/kanban_watchers.py:50 @ 863e313`

```python
    enabled = bool(kcfg.get("auto_decompose", True))
```

`gateway/kanban_watchers.py:52 @ 863e313`

```python
        per_tick = int(kcfg.get("auto_decompose_per_tick", 3) or 3)
```

**读取点的默认值与本表不一致的一处**:stale 超时在 watcher 里的兜底是 `0`(=关闭),
而 `DEFAULT_CONFIG` 给 `14400`。因为 `load_config()` 会深合并,正常路径永远拿到 14400;
但任何**不走 `load_config()`** 的读法(raw config)会得到"关闭"。
`gateway/kanban_watchers.py:1087 @ 863e313`

```python
        raw_stale = kanban_cfg.get("dispatch_stale_timeout_seconds", 0)
```

### 2.4 `code_execution.mode`(2314-2326)

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `code_execution.mode` | `"project"` | `project`=在会话工作目录用当前 venv/conda 的 python 跑(项目依赖与相对路径可用);`strict`=隔离临时目录 + `sys.executable` |

注释明确:**env 擦洗(剥离 `*_API_KEY`/`*_TOKEN`/`*_SECRET`…)和工具白名单在两种模式下完全一样**,
两者只差"在哪跑、用谁的解释器"。`hermes_cli/config_defaults.py:2325 @ 863e313`

```python
        "mode": "project",
```

读取点用的是 `read_raw_config()`(不是 `load_config()`),理由写在 docstring 里:
在工具发现阶段构建 schema 时 import `cli` 会把 prompt_toolkit/Rich 拖进每条启动路径。
`tools/code_execution_tool.py:1789 @ 863e313`

```python
    try:
        from hermes_cli.config import read_raw_config

        cfg = read_raw_config().get("code_execution", {})
```

代价:**默认值出现了第二个真相源**——模块常量 `DEFAULT_EXECUTION_MODE`。
`tools/code_execution_tool.py:1804 @ 863e313`

```python
EXECUTION_MODES = ("project", "strict")
DEFAULT_EXECUTION_MODE = "project"
```

`tools/code_execution_tool.py:1825 @ 863e313`

```python
    cfg_value = str(_load_config().get("mode", DEFAULT_EXECUTION_MODE)).strip().lower()
```

目前两处都是 `"project"`,一致;但这是靠人肉同步维持的。

### 2.5 `tools.tool_search.*` —— 大工具面的渐进披露(2328-2376)

**解决什么问题**:接了很多 MCP server / 插件工具后,它们的 JSON schema 每一轮都要塞进 context,
可能吃掉相当比例的窗口。开启后这些工具从"模型可见 tools 数组"里撤下,换成三个桥接工具
`tool_search` / `tool_describe` / `tool_call`,按需揭示。**核心 Hermes 工具永不延迟**。
`hermes_cli/config_defaults.py:2335 @ 863e313`

```python
    # Core Hermes tools (terminal, read_file, write_file, patch,
    # search_files, todo, memory, browser_*, etc.) are NEVER deferred.
```

分层策略(注释里定义了三档):
- Tier 0 —— 没有可延迟工具:全部保持 eager;
- Tier 1 —— 目录清单塞得进预算:桥接 + skills 风格的 name+description 清单(放不下降级为纯 name);
- Tier 2 —— 连纯 name 都超预算(注释举例 Cloudflare 约 3300 个工具的扁平 API 面):
  裸桥接 + 每个 server 一行摘要(名字 + 工具数),具体工具只能靠 `tool_search` 发现。

| 点分路径 | 默认值 | 语义 / 取值域 | 定义行 |
|---|---|---|---|
| `tools.tool_search.enabled` | `"auto"` | `auto`/`on` = 只要存在可延迟工具就激活;`off` = 完全关闭(tools 数组组装成为直通) | `:2353` |
| `tools.tool_search.threshold_pct` | `5` | 清单预算 = min(模型 context 的这个百分比, `listing_max_tokens`);范围 0..100 | `:2357` |
| `tools.tool_search.search_default_limit` | `5` | 模型不带 `limit` 调用时返回几条;范围 1..`max_search_limit` | `:2360` |
| `tools.tool_search.max_search_limit` | `20` | 模型能请求的硬上限;范围 1..50 | `:2362` |
| `tools.tool_search.listing` | `"auto"` | 是否在桥接工具描述里内嵌 skills 风格目录:`auto`/`on`/`off` | `:2371` |
| `tools.tool_search.listing_max_tokens` | `4000` | 内嵌清单的绝对上限(按 chars/4 估算);范围 200..60000 | `:2374` |

`hermes_cli/config_defaults.py:2353 @ 863e313`

```python
            "enabled": "auto",
```

解析器把注释里的"范围"真正**钳位**了,而且 `search_default_limit` 被钳到 `max_search_limit`,
所以两键写反也不会产生非法组合。`tools/tool_search.py:130 @ 863e313`

```python
        threshold_pct = _safe_float(raw.get("threshold_pct"), 5.0)
        threshold_pct = max(0.0, min(100.0, threshold_pct))

        max_search_limit = max(1, min(50, _safe_int(raw.get("max_search_limit"), 20)))
        search_default_limit = max(1, min(max_search_limit,
                                          _safe_int(raw.get("search_default_limit"), 5)))
```

`tools/tool_search.py:146 @ 863e313`

```python
        listing_max_tokens = max(200, min(60000, _safe_int(raw.get("listing_max_tokens"), 4000)))
```

还有一层**向后兼容**:整块写成裸 `true`/`false` 也被接受,分别映射到 `auto`/`off`。
`tools/tool_search.py:110 @ 863e313`

```python
        if raw is True:
            return cls(enabled="auto", threshold_pct=5.0,
                       search_default_limit=5, max_search_limit=20)
```

注释里指路 "the openclaw-tool-search-report PDF in this PR" —— 这是**指向 PR 附件的死链**,
基线仓库里没有这个 PDF(§7 文档-代码出入 C1)。

### 2.6 `logging.*`(2378-2384)

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `logging.level` | `"INFO"` | `~/.hermes/logs/agent.log` 的最低级别 |
| `logging.max_size_mb` | `5` | 单文件轮转阈值 |
| `logging.backup_count` | `3` | 保留几个轮转备份 |

`hermes_cli/config_defaults.py:2380 @ 863e313`

```python
    "logging": {
        "level": "INFO",       # Minimum level for agent.log: DEBUG, INFO, WARNING
        "max_size_mb": 5,      # Max size per log file before rotation
        "backup_count": 3,     # Number of rotated backup files to keep
    },
```

读取走 raw config(同样为了避免早启动的重 import),返回三元组,任一可为 `None`。
`hermes_logging.py:791 @ 863e313`

```python
            log_cfg = cfg.get("logging", {})
```

**兜底用的是 `or` 链**,于是 `0` 被当成"没设":`hermes_logging.py:312 @ 863e313`

```python
    max_bytes = (max_size_mb or cfg_max_size or 5) * 1024 * 1024
    backups = backup_count or cfg_backup or 3
```

后果见 §6 D3:`logging.backup_count: 0`(想"轮转但不留备份")静默变成 3。

### 2.7 `model_catalog.*`(2386-2405)

**解决什么问题**:模型选择器的 curated 列表(OpenRouter / Nous Portal)要能**不发版**地更新。
于是 CLI 去一个远端 manifest 拉,失败回落仓内快照。

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `model_catalog.enabled` | `True` | 总开关 |
| `model_catalog.url` | `"https://hermes-agent.nousresearch.com/docs/api/model-catalog.json"` | manifest 地址(由 docs 站 GitHub Pages 部署提供) |
| `model_catalog.ttl_hours` | `1` | 磁盘缓存 TTL;超时后下次 `/model` 或 `hermes model` 重取,网络失败静默用旧缓存 |
| `model_catalog.providers` | `{}` | 每 provider 的覆盖 URL,给想自托管同 schema 的第三方 |

`hermes_cli/config_defaults.py:2391 @ 863e313`

```python
    "model_catalog": {
        "enabled": True,
        "url": "https://hermes-agent.nousresearch.com/docs/api/model-catalog.json",
```

读取器把四个键都填了兜底:`hermes_cli/model_catalog.py:107 @ 863e313`

```python
    return {
        "enabled": bool(raw.get("enabled", True)),
        "url": str(raw.get("url") or DEFAULT_CATALOG_URL),
        "ttl_hours": float(raw.get("ttl_hours") or DEFAULT_TTL_HOURS),
        "providers": raw.get("providers") if isinstance(raw.get("providers"), dict) else {},
    }
```

同样是 `or` 兜底 → `ttl_hours: 0`("每次都重取")静默变回默认(§6 D3 同类)。

`ttl_hours` 的默认值有一条**迁移史**:v24→25 把 24 降到 1,且只改"恰好等于旧默认 24"的值,
不碰用户自定义值。这是"改默认值"的正确做法样板。`hermes_cli/config_migrations.py:486 @ 863e313`

```python
    if isinstance(raw_mc, dict) and raw_mc.get("ttl_hours") == 24:
```

**未在 DEFAULT_CONFIG 里声明但被读的键**:`model_catalog.excluded_providers`。
`hermes_cli/inventory.py:100 @ 863e313`

```python
    excluded = cfg.get("model_catalog", {}).get("excluded_providers") or []
```

`hermes_cli/main.py:3307 @ 863e313`

```python
        for p in (config.get("model_catalog", {}) or {}).get("excluded_providers") or []
```

后果:它在 dashboard schema 里不存在、`hermes config check` 不会提示、文档里也没有——
一个纯口传键(§6 D4)。

### 2.8 `network.force_ipv4`(2407-2413)

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `network.force_ipv4` | `False` | 强制 IPv4。注释解释了症状:IPv6 不可达的机器上 Python 先试 AAAA,会挂满整个 TCP 超时再回落 |

`hermes_cli/config_defaults.py:2412 @ 863e313`

```python
        "force_ipv4": False,
```

三个入口各自读一遍(gateway、cron、CLI 早启动),因为这必须在任何 socket 建立**之前**打补丁。
`gateway/run.py:2293 @ 863e313`

```python
    if isinstance(_network_cfg, dict) and _network_cfg.get("force_ipv4"):
```

`cron/scheduler.py:3278 @ 863e313`

```python
            if isinstance(_net_cfg, dict) and _net_cfg.get("force_ipv4"):
```

`hermes_cli/main.py:736 @ 863e313`

```python
        if isinstance(_early_net_cfg, dict) and _early_net_cfg.get("force_ipv4"):
```

### 2.9 `monitoring.*` —— gateway 健康导出(2415-2451)

块头把**隐私边界**写成了设计声明:content-free by construction——不含 prompt、消息、
工具参数/结果、会话历史、用量分析、审计日志、轨迹。默认关闭,operator 不开且不填 endpoint
就什么都不采集不发送。`hermes_cli/config_defaults.py:2415 @ 863e313`

```python
    # Gateway monitoring — Service Health Monitoring plus redacted Operational
```

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `monitoring.install_id` | `""` | 稳定安装标识;空 = 首次使用时铸一个 UUID;清空即轮换;不携带账号身份 |
| `monitoring.gateway_health_export.enabled` | `False` | 健康/诊断导出总开关 |
| `monitoring.gateway_health_export.metrics_enabled` | `True` | 指标 |
| `monitoring.gateway_health_export.diagnostic_events_enabled` | `True` | 诊断事件 |
| `monitoring.gateway_health_export.warning_error_events_enabled` | `True` | WARNING/ERROR 事件 |
| `monitoring.gateway_health_export.export_interval_seconds` | `60` | 指标导出周期 |
| `monitoring.gateway_health_export.logs_export_interval_seconds` | `5` | 日志导出周期 |
| `monitoring.gateway_health_export.resource_attributes["service.name"]` | `"hermes-gateway"` | **死配置**,运行时被硬覆盖(§6 D5) |
| `monitoring.gateway_health_export.resource_attributes["deployment.environment.name"]` | `"production"` | 生效(在允许名单内且不被覆盖) |
| `monitoring.export.otlp.enabled` | `False` | OTLP 目的地开关 |
| `monitoring.export.otlp.endpoint` | `""` | OTLP endpoint |
| `monitoring.export.otlp.headers_env` | `{}` | header 名 → **环境变量名**(绝不是密文值),导出时才从环境读 |

`hermes_cli/config_defaults.py:2427 @ 863e313`

```python
        "install_id": "",
```

`hermes_cli/config_defaults.py:2436 @ 863e313`

```python
            "resource_attributes": {
                "service.name": "hermes-gateway",
                "deployment.environment.name": "production",
            },
```

`hermes_cli/config_defaults.py:2441 @ 863e313`

```python
        # OTLP destination. headers_env maps header names to ENVIRONMENT
        # VARIABLE NAMES (never secret values); values are read from the
        # environment at export time.
```

**"三个都为真才导出"的与门**:`agent/monitoring/gateway_health_export.py:181 @ 863e313`

```python
    return bool(gh.get("enabled") and otlp.get("enabled") and otlp.get("endpoint"))
```

**`headers_env` 的间接层**是这个子系统最值得抄的一招:config.yaml 里只放变量名,
密文永远在环境里,于是配置文件可以随意提交/分享。
`agent/monitoring/otlp_exporter.py:114 @ 863e313`

```python
    headers = _resolve_headers(otlp.get("headers_env"))
```

**`install_id` 的铸造-落盘**:空则铸一个 UUID 并**立刻写回 config.yaml**(因为它会变成
`service.instance.id`,必须跨重启稳定);写失败 fail-open,用临时 id,下次再铸。
`agent/monitoring/policy.py:18 @ 863e313`

```python
def ensure_install_id(config: Dict[str, Any]) -> str:
```

`agent/monitoring/policy.py:35 @ 863e313`

```python
    minted = str(uuid.uuid4())
```

这里的写回是安全的,因为 `save_config` 默认 `strip_defaults=True`,不会把整棵
`DEFAULT_CONFIG` 灌进用户 YAML。`hermes_cli/config.py:3505 @ 863e313`

```python
def save_config(
    config: Dict[str, Any],
    *,
    strip_defaults: bool = True,
```

**resource_attributes 的允许名单**只放 9 个 OTel 语义约定键,值还要过正则与脱敏一致性检查
(脱敏后不等于原值就丢弃)。`agent/monitoring/gateway_health_export.py:22 @ 863e313`

```python
_RESOURCE_ATTRIBUTE_KEYS = frozenset({
    "service.name",
    "service.namespace",
```

`agent/monitoring/gateway_health_export.py:69 @ 863e313`

```python
        if not _SAFE_RESOURCE_VALUE.fullmatch(text):
            continue
        if _redact_string(text, limit=128) != text:
            continue
```

### 2.10 `gateway.*`(2453-2602)

这一块是本段最杂的:既有 gateway 守护进程的自保机制,也有媒体投递的安全姿态。

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `gateway.delivery_ledger` | `True` | 持久投递义务账本:最终回复在平台发送前后写 state.db;finalize 与平台 ACK 之间死掉的 gateway 下次开机重投(可疑重复会带 "recovered reply" 标记,诚实的 at-least-once) |
| `gateway.platform_connect_timeout` | `30` | 单个消息平台启动/重连的等待秒数;`0` 或负 = 无限等 |
| `gateway.loop_watchdog` | `True` | 进程内 asyncio loop 存活看门狗(#69089):连续漏探测后 dump 全线程栈并按 service-restart 退出码硬退,让 systemd/launchd 复活 |
| `gateway.write_sessions_json` | `True` | 是否继续写 legacy `sessions.json` 路由索引镜像(主副本在 state.db 的 `gateway_routing` 表) |
| `gateway.scale_to_zero.idle_timeout_minutes` | `5` | 空闲多久后驱动 relay 传输休眠,让平台(如 Fly autostop:"suspend")挂起机器 |
| `gateway.restart_loop_guard.max_restarts` | `3` | 滚动窗口内 restart-interrupted 开机次数达标即**跳过本次 auto-resume**;`0` 关闭 |
| `gateway.restart_loop_guard.window_seconds` | `60` | 上者的窗口 |
| `gateway.respawn_storm.max_starts` | `5` | 滑窗内 gateway (重)启动次数达标即先睡指数退避再开机;`<=0` 关闭 |
| `gateway.respawn_storm.window_seconds` | `120` | 上者的窗口 |
| `gateway.message_timestamps.enabled` | `False` | 给**模型上下文里**的用户消息加人类可读时间前缀;持久化 transcript 永远保持干净 |
| `gateway.max_inbound_media_bytes` | `134217728` (128 MiB) | 入站图/音/视频缓冲上限;`0` 关闭 |
| `gateway.strict` | `False` | 出站文件投递姿态:默认=只要不在凭据/系统路径黑名单就当附件发;`true`=回到旧的白名单+新鲜度窗口 |
| `gateway.media_delivery_allow_dirs` | `[]` | 额外可上传目录(list 或 `os.pathsep` 分隔串);**两种模式都生效** |
| `gateway.trust_recent_files` | `True` | mtime 在窗口内的文件也可投递;**仅 `strict` 为真时才被查阅** |
| `gateway.trust_recent_files_seconds` | `600` | 上者窗口;**仅 `strict` 为真时才被查阅** |
| `gateway.api_server.max_concurrent_runs` | `10` | OpenAI 兼容 API server 的并发 run 上限,超出返回 429 + Retry-After;`0` 关闭 |

`hermes_cli/config_defaults.py:2463 @ 863e313`

```python
        "delivery_ledger": True,
```

`gateway/delivery_ledger.py:347 @ 863e313`

```python
        value = gw.get("delivery_ledger", True)
```

`hermes_cli/config_defaults.py:2481 @ 863e313`

```python
        "loop_watchdog": True,
```

`gateway/config.py:1200 @ 863e313`

```python
            write_sessions_json=_coerce_bool(data.get("write_sessions_json"), True),
```

**scale_to_zero 的一句关键设计声明**:功能开不开**不是 config 键**,而是 NAS "Labs" 开关
(以 `HERMES_SCALE_TO_ZERO` env 戳传进来);config 里只有空闲超时。
`hermes_cli/config_defaults.py:2492 @ 863e313`

```python
        # the HERMES_SCALE_TO_ZERO env stamp) AND messaging is relay-only/absent
```

`gateway/run.py:7464 @ 863e313`

```python
            stz = gw.get("scale_to_zero") if isinstance(gw, dict) else None
```

**两层重启保护**是本块最值得学的设计,它们**互补**而非重复:

- `restart_loop_guard`(#30719 defense-3)针对"被 SIGTERM 打断 → 下次开机 auto-resume →
  那一轮又触发一次 kill"的紧循环。它**不阻止 gateway 启动**,只是跳过 auto-resume:
  gateway 照常服务真实入站消息,只是不再重播那个把自己弄死的会话。
  `hermes_cli/config_defaults.py:2514 @ 863e313`

  ```python
        "restart_loop_guard": {
            "max_restarts": 3,
            "window_seconds": 60,
        },
  ```

  `gateway/run.py:7484 @ 863e313`

  ```python
            rlg = gw.get("restart_loop_guard") if isinstance(gw, dict) else None
  ```

- `respawn_storm` 是**便携的**进程级熔断:滑窗计数 (re)start,过多就先睡指数退避再开机,
  防止 launchd `KeepAlive` / systemd `Restart=always` 把进程锤成 respawn storm。
  `hermes_cli/config_defaults.py:2527 @ 863e313`

  ```python
        "respawn_storm": {
            "max_starts": 5,
            "window_seconds": 120,
        },
  ```

  `hermes_cli/gateway.py:5076 @ 863e313`

  ```python
            _rs = _gw.get("respawn_storm") if isinstance(_gw, dict) else None
  ```

**媒体投递的四个键有一条明确的"谁在什么模式下被读"的规则**,这是本文件里少见的把
"条件依赖"写进注释的地方:`allow_dirs` 两模式都读,`trust_recent_files*` 只在 strict 读。
`hermes_cli/config_defaults.py:2585 @ 863e313`

```python
        "trust_recent_files": True,
```

`hermes_cli/config_defaults.py:2589 @ 863e313`

```python
        "trust_recent_files_seconds": 600,
```

四个键在 gateway 启动时**桥接成环境变量**,因为真正执行判定的是
`gateway/platforms/base.py` 的共享缓存助手(跨所有平台适配器)。
`gateway/run.py:2235 @ 863e313`

```python
            _strict = _gateway_cfg.get("strict")
            if _strict is not None:
                os.environ["HERMES_MEDIA_DELIVERY_STRICT"] = (
                    "1" if _strict else "0"
                )
```

`gateway/run.py:2255 @ 863e313`

```python
            _trust_recent_seconds = _gateway_cfg.get("trust_recent_files_seconds")
```

`platform_connect_timeout` 的桥接方向**与上面几个相反**:那几个是 config 权威,
这个 env 是**手动逃生口且优先**——已显式设置时 config 不覆盖。注释把这个不对称说明白了。
`gateway/run.py:2258 @ 863e313`

```python
            # Bridge gateway.platform_connect_timeout → the internal env var the
            # connect path + Discord adapter ready-wait both read (#19776).
            # Unlike the agent.*/display.* bridges above (config-authoritative),
            # this env var is the manual-override escape hatch, so it WINS if
            # already set explicitly; otherwise config.yaml supplies the value.
```

这条桥接整体包在一个 `try` 里,而且注释记了一次**真实事故**:以前是 `except Exception: pass`,
静默吞掉部分桥接失败,导致用户看到 config 写 `max_turns=500` 实际却是 60 次上限。
现在改成打到 stderr。`gateway/run.py:2270 @ 863e313`

```python
    except Exception as _bridge_err:
```

`max_inbound_media_bytes` 的读取是"键不存在就用模块常量"而不是 `.get(k, default)`,
所以显式写 `0` 能真的关闭上限。`gateway/platforms/base.py:742 @ 863e313`

```python
    if not isinstance(gw, dict) or "max_inbound_media_bytes" not in gw:
        return DEFAULT_INBOUND_MEDIA_MAX_BYTES
```

`gateway.api_server.max_concurrent_runs` 用 `cfg_get` 走点分路径读,并 `max(0, value)`。
`gateway/platforms/api_server.py:1570 @ 863e313`

```python
            raw = cfg_get(
                load_config(),
                "gateway",
                "api_server",
                "max_concurrent_runs",
                default=default,
            )
```

**注意 `gateway` 块里缺一个被实际读取的键**:`gateway.proxy_url`(代理模式)。
`gateway/run.py:23752 @ 863e313`

```python
        url = (cfg.get("gateway") or {}).get("proxy_url")
```

它只在 `OPTIONAL_ENV_VARS["GATEWAY_PROXY_URL"]` 的描述里被提到,却没进 `DEFAULT_CONFIG`(§6 D4)。

### 2.11 `streaming.*`(2604-2641)

块头注释说了一件很有意思的事:**这一块加进 DEFAULT_CONFIG 不改变任何行为**——
gateway 本来就在缺这块时用同样的默认值;加进来只是让它在 config.yaml 里**可被发现**。
`hermes_cli/config_defaults.py:2604 @ 863e313`

```python
    # Real-time token streaming to messaging platforms (Telegram, Discord,
    # Slack, etc.). Read at the top level by the gateway; absent this block the
    # gateway falls back to these same defaults, so adding it here only makes
    # the feature discoverable in config.yaml — it does not change behavior.
```

这是"默认表 = 文档"这一身份的**纯文档用法**,值得单独记一笔。

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `streaming.enabled` | `False` | 总开关;关 = 每次回复一条最终消息 |
| `streaming.transport` | `"auto"` | `auto`(能原生 draft 就 draft,否则 edit)/`draft`/`edit`/`off` |
| `streaming.edit_interval` | `0.8` | 渐进编辑最小间隔秒(对着 Telegram 约 1 edit/s 的洪水阈值调的) |
| `streaming.buffer_threshold` | `24` | 累积多少字符就 flush,让短回复接近即时 |
| `streaming.cursor` | `" ▉"` | 进行中消息尾部的光标字形 |
| `streaming.fresh_final_after_seconds` | `0.0` | >0 时,长流式回复的最终 edit 改发新消息,让平台时间戳反映完成时刻;**仅 Telegram** |

`hermes_cli/config_defaults.py:2611 @ 863e313`

```python
    "streaming": {
```

`hermes_cli/config_defaults.py:2635 @ 863e313`

```python
        "cursor": " \u2589",
```

`gateway/config.py:803 @ 863e313`

```python
                data.get("edit_interval"), DEFAULT_STREAMING_EDIT_INTERVAL,
```

`gateway/stream_consumer.py:1848 @ 863e313`

```python
        threshold = getattr(self.cfg, "fresh_final_after_seconds", 0.0) or 0.0
```

### 2.12 `sessions.*` —— state.db 生命周期(2643-2722)

块头给了**具体的痛点数字**:state.db 无限累积,重度用户(gateway + cron)报告 384MB+ /
68K+ 消息,拖慢 FTS5 插入、`/resume` 列表与 insights 查询。

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `sessions.auto_prune` | `False` | 启动时按 `retention_days` 清理已结束且不活跃的会话;默认关(历史对搜索召回有价值,静默删会吓到人) |
| `sessions.retention_days` | `90` | 保留多少天不活跃的已结束会话 |
| `sessions.auto_archive` | `False` | 软隐藏(永不删)长期未触碰的会话;pinned 永远豁免 |
| `sessions.auto_archive_days` | `3` | 归档的空闲阈值(天),仅 `auto_archive` 为真时生效 |
| `sessions.vacuum_after_prune` | `True` | 真删了行才 VACUUM(SQLite DELETE 不还盘) |
| `sessions.min_vacuum_interval_days` | `30` | 两次成功 VACUUM 的最小间隔 |
| `sessions.min_interval_hours` | `24` | 两次自动维护的最小间隔;经 state.db 的 `state_meta` 记录,**跨进程共享** |
| `sessions.write_json_snapshots` | `False` | legacy 每会话 JSON 快照写入器;state.db 是权威且字段更全,默认关 |
| `sessions.fts_optimize_notice` | `"advise"` | v23 紧凑索引布局的提示强度:`advise`/`require`/`off`,**opt-in,不自动重建** |
| `sessions.cjk_fts` | `True` | CJK bigram 索引(`cjk_unicode61` 可加载分词器);扩展不在时该设置惰性 |
| `sessions.search_slow_ms` | `1000` | 慢搜索日志阈值(ms),日志里带路由路径 `fts_cjk`/`fts5`/`trigram`/`like_scan`;`0` 记录每一次 |

`hermes_cli/config_defaults.py:2648 @ 863e313`

```python
    "sessions": {
```

`hermes_cli/config_defaults.py:2655 @ 863e313`

```python
        "auto_prune": False,
```

`fts_optimize_notice` 的注释顺手写了**未来的发布计划**:等准备好把 v23 布局变成强制时
就把默认翻到 `require`,因为命令、进度条、可恢复性都已就位,"enforcement is a copy/gating
change, not new migration code"。`hermes_cli/config_defaults.py:2701 @ 863e313`

```python
        #   "require": the notice is shown as a REQUIRED upgrade (firmer copy),
```

`hermes_cli/config_defaults.py:2707 @ 863e313`

```python
        "fts_optimize_notice": "advise",
```

`hermes_cli/update_cmd.py:389 @ 863e313`

```python
                "fts_optimize_notice", "advise"
```

`cjk_fts` / `search_slow_ms` 是**config → env 内部载体**的又一例(`hermes_state` 读 env):
`cli.py:779 @ 863e313`

```python
    # Session-search index knobs (hermes_state reads the env carriers).
    sessions_config = defaults.get("sessions", {})
    if isinstance(sessions_config, dict):
        if "cjk_fts" in sessions_config:
            os.environ["HERMES_CJK_FTS"] = str(sessions_config["cjk_fts"])
```

gateway 侧有一份**平行实现**(同样两键、同样 env 名):`gateway/run.py:1894 @ 863e313`

```python
            os.environ["HERMES_CJK_FTS"] = str(sessions_cfg["cjk_fts"])
```

清理/归档的实际调用点也是 CLI 与 gateway 各一份:`cli.py:2171 @ 863e313`

```python
        if not cfg.get("auto_prune", False):
```

`gateway/run.py:6174 @ 863e313`

```python
                        idle_days=float(_sess_cfg.get("auto_archive_days", 3)),
```

`agent/agent_init.py:1534 @ 863e313`

```python
        agent._session_json_enabled = bool(_sess_cfg.get("write_json_snapshots", False))
```

### 2.13 `onboarding.*`(2724-2735)

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `onboarding.seen` | `{}` | 提示"已看过"的闩锁字典;每条提示每装机只出一次,latch 在这里。用户清空整节即可重看全部 |
| `onboarding.profile_build` | `"ask"` | 有史以来第一条 gateway 消息上是否提议构建用户画像:`ask`(opt-in、consent-gated,先问再查,绝不静默读已连账号)/`off` |

`hermes_cli/config_defaults.py:2727 @ 863e313`

```python
    "onboarding": {
        "seen": {},
```

`agent/onboarding.py:164 @ 863e313`

```python
    mode = onboarding.get("profile_build")
```

这里体现了一个模式:**把"已展示过"的运行时状态写进 config.yaml**,而不是单开一个 state 文件。
好处是用户可以手删重看、可以 `hermes config` 检视;代价是 config.yaml 承担了状态职责,
并且 `onboarding.seen` 是空 dict → dashboard schema 里不可见(§1.4)。
web_server 的分类合并注释明确承认了这点:"`onboarding.seen` is an internal latch dict,
not a user setting"。`hermes_cli/web_server.py:1032 @ 863e313`

```python
    # `onboarding.profile_build` is the only schema-surfaced onboarding field
```

### 2.14 `telemetry.shared_metrics.enabled`(2737-2743)

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `telemetry.shared_metrics.enabled` | `False` | 只写本 profile 本地 telemetry 目录的聚合指标;**采集 opt-in 且不存在远端 sink** |

`hermes_cli/config_defaults.py:2739 @ 863e313`

```python
    "telemetry": {
        "shared_metrics": {
            "enabled": False,
        },
    },
```

`hermes_cli/observability/relay_shared_metrics.py:1085 @ 863e313`

```python
            telemetry.get("shared_metrics") if isinstance(telemetry, dict) else None
```

### 2.15 `updates.*`(2745-2792)

`pre_update_backup` 的注释是本文件最好的一段"为什么"文档:它把**三种模式各自防哪个事故**
写上了 issue 号。

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `updates.pre_update_backup` | `"quick"` | `quick`=快照关键小状态(配对 JSON、cron 任务、config.yaml、.env、auth.json、per-profile DB)到 `<HERMES_HOME>/state-snapshots/`,>1 GiB 的文件(如臃肿的 state.db)跳过并告警 —— 防 #15733(配对数据丢失)/ #34600(cron 任务被清空);`full`=再加一个 `hermes backup` 式 zip —— 防 #48200(错路径抹除);`off`=不备份。**legacy 布尔值被兼容:`true`→`full`,`false`→`off`** |
| `updates.backup_keep` | `5` | 保留几个 full zip;小于 1 被抬到 1(刚做的那个永远保住);quick 快照恒定保留 1 个 |
| `updates.non_interactive_local_changes` | `"stash"` | **非交互**更新(桌面/聊天 app/gateway,没有 TTY 回答提示)遇到源码树未提交改动怎么办:`stash`=自动 stash→pull→自动恢复(冲突留在 git stash 里,什么都不丢);`discard`=stash 后丢弃 stash(**不是** `reset --hard` + `clean -fd`,所以 node_modules/venv/构建产物这些被忽略路径不受影响)。交互式更新不受影响 |
| `updates.refresh_cua_driver` | `True` | `hermes update` 时刷新已装的 cua-driver;best-effort 且仅 macOS |

`hermes_cli/config_defaults.py:2765 @ 863e313`

```python
        "pre_update_backup": "quick",
```

`hermes_cli/update_cmd.py:2532 @ 863e313`

```python
    raw = updates_cfg.get("pre_update_backup", "quick")
```

`hermes_cli/update_cmd.py:2668 @ 863e313`

```python
        _keep = (load_config() or {}).get("updates", {}).get("backup_keep", 5)
```

`hermes_cli/update_cmd.py:3592 @ 863e313`

```python
                _mode = str(_update_cfg.get("non_interactive_local_changes", "stash")).lower()
```

`hermes_cli/update_cmd.py:4666 @ 863e313`

```python
                        _update_cfg.get("refresh_cua_driver", True)
```

`updates.non_interactive_local_changes` 与 `updates.refresh_cua_driver` 是本段里**少数
拿到了手写 schema 描述**的键(dashboard 会显示人话而不是自动 Title Case)。
`hermes_cli/web_server.py:1003 @ 863e313`

```python
    "updates.refresh_cua_driver": {
```

### 2.16 `lsp.*`(2794-2847)

**解决什么问题**:`write_file` / `patch` 之后的 lint 检查需要真语言服务器的语义诊断
(pyright、gopls、rust-analyzer…)。关键设计是**门控在 git 工作区探测上**:agent 的 cwd
(或被编辑文件)在 git worktree 里才起 LSP;都不在就休眠,只留进程内语法检查——
"handy for Telegram/Discord chats where the cwd is the user's home directory"。
`hermes_cli/config_defaults.py:2799 @ 863e313`

```python
    # LSP is gated on git-workspace detection: when the agent's
```

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `lsp.enabled` | `True` | 总开关;false = 不 spawn server、不起后台事件循环、零成本 |
| `lsp.wait_mode` | `"document"` | `document`=只等当前文件的诊断;`full`=另外请求 workspace 级(更慢) |
| `lsp.wait_timeout` | `5.0` | 等诊断的秒数 |
| `lsp.install_strategy` | `"auto"` | `auto`=首次用时经 npm/go/pip 装到 `<HERMES_HOME>/lsp/bin/`;`manual`=只用 PATH 上的;`off`=`manual` 的别名 |
| `lsp.idle_timeout` | `600.0` | 空闲这么多秒后关掉 language server,按需重启。防止长跑的 gateway/CLI 随 agent 在 worktree 间移动而堆积 pyright/gopls/tsserver 子进程(每个几百 MB + 管道 FD);`0` 关闭回收 |
| `lsp.servers` | `{}` | 每 server 覆盖;key 是注册表里的 `server_id`,支持 `disabled` / `command`(钉死二进制路径,绕过自动安装)/ `env` / `initialization_options` |

`hermes_cli/config_defaults.py:2805 @ 863e313`

```python
    "lsp": {
```

`hermes_cli/config_defaults.py:2846 @ 863e313`

```python
        "servers": {},
```

`agent/lsp/manager.py:210 @ 863e313`

```python
        wait_mode = lsp_cfg.get("wait_mode", "document")
```

`agent/lsp/manager.py:212 @ 863e313`

```python
        install_strategy = lsp_cfg.get("install_strategy", "auto")
```

`agent/lsp/manager.py:214 @ 863e313`

```python
            idle_timeout = float(lsp_cfg.get("idle_timeout", DEFAULT_IDLE_TIMEOUT))
```

### 2.17 `x_search.*`(2849-2868)

**注册条件是三重与**:有 xAI 凭据(SuperGrok OAuth 或 `XAI_API_KEY`)**且** `x_search`
toolset 在 `hermes tools` 里开启。这几个键只调后端 Responses 调用。

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `x_search.model` | `"grok-4.5"` | 走 Responses 的 xAI 模型 |
| `x_search.reasoning_effort` | `None` | 可选 reasoning effort;null = 保留所选模型自身默认 |
| `x_search.timeout_seconds` | `180` | 请求超时,**最小 30**(复杂查询可能 60-120s) |
| `x_search.retries` | `2` | 5xx / ReadTimeout / ConnectionError 的自动重试次数,退避 1.5×attempt 秒、上限 5s |

`hermes_cli/config_defaults.py:2854 @ 863e313`

```python
    "x_search": {
```

`tools/x_search_tool.py:74 @ 863e313`

```python
        return load_config().get("x_search", {}) or {}
```

"最小 30"是**代码里真的钳位**的:`tools/x_search_tool.py:104 @ 863e313`

```python
        return max(30, int(raw_value))
```

`reasoning_effort` 是本段里少见的**非法值抛异常**而不是静默回落的键(其余大多是 warn+fallback)。
`tools/x_search_tool.py:91 @ 863e313`

```python
    if effort not in X_SEARCH_REASONING_EFFORTS:
```

### 2.18 `secrets.*` —— 外部密钥源(2870-2954)

**解决什么问题**:不把凭据落在 `~/.hermes/.env`,而是进程启动时从外部 secret manager 拉。

块头还定义了**优先级规则**:显式 `sources` 列表可选;无论列表如何,"mapped" 源
(显式 VAR→ref 绑定)总是优先于 "bulk" 源(项目整包 dump,如 Bitwarden BSM);
且**第一个认领某变量的源获胜**,后来的被跳过并告警。`hermes_cli/config_defaults.py:2876 @ 863e313`

```python
        # Optional explicit ordering of enabled secret sources.  When
```

注意 `sources` 键**被注释掉了**,只作为文档存在:`hermes_cli/config_defaults.py:2884 @ 863e313`

```python
        # "sources": [],
```

#### `secrets.bitwarden.*`

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `secrets.bitwarden.enabled` | `False` | 总开关;false = 永不联系 BSM、永不自动装 bws |
| `secrets.bitwarden.access_token_env` | `"BWS_ACCESS_TOKEN"` | 装机器账号 token 的**环境变量名**(唯一的引导密钥,住 `.env`/shell,永不进 config.yaml) |
| `secrets.bitwarden.project_id` | `""` | 要同步的 BSM 项目 UUID |
| `secrets.bitwarden.cache_ttl_seconds` | `300` | 复用新鲜缓存的秒数;`0` 关闭正常新鲜缓存复用 |
| `secrets.bitwarden.encrypted_cache.enabled` | `False` | 加密的 last-good 回退(AES-GCM 写 `~/.hermes/cache/`) |
| `secrets.bitwarden.encrypted_cache.max_stale_seconds` | `0` | 网络/超时故障时可用多旧的加密缓存;**认证失败不回退** |
| `secrets.bitwarden.override_existing` | `True` | BSM 值覆盖已有 env。理由写得很好:用 BSM 的意义就是集中轮换,若 `.env` 说了算,轮换要等你也清掉 `.env` 那行才生效 |
| `secrets.bitwarden.auto_install` | `True` | 首次用时把 bws 下到 `~/.hermes/bin/` |
| `secrets.bitwarden.server_url` | `""` | region / 自托管端点;空 = bws CLI 默认(US Cloud)。EU 用 `https://vault.bitwarden.eu`。经子进程 `BWS_SERVER_URL` 传入 |

`hermes_cli/config_defaults.py:2885 @ 863e313`

```python
        "bitwarden": {
```

`hermes_cli/config_defaults.py:2893 @ 863e313`

```python
            "access_token_env": "BWS_ACCESS_TOKEN",
```

`hermes_cli/config_defaults.py:2912 @ 863e313`

```python
            "override_existing": True,
```

**基类默认与本表相反**,子类各自覆写。这是一处"默认值散落三处"的真相源分裂:
`agent/secret_sources/base.py:184 @ 863e313`

```python
        return bool(isinstance(cfg, dict) and cfg.get("override_existing", False))
```

`agent/secret_sources/bitwarden.py:871 @ 863e313`

```python
        return bool(isinstance(cfg, dict) and cfg.get("override_existing", True))
```

`agent/secret_sources/onepassword.py:521 @ 863e313`

```python
        return bool(isinstance(cfg, dict) and cfg.get("override_existing", True))
```

好在 bitwarden 那处有注释显式说"Default True (matches DEFAULT_CONFIG)"。
`agent/secret_sources/bitwarden.py:867 @ 863e313`

```python
        # Default True (matches DEFAULT_CONFIG): the point of BSM is
```

`access_token_env` 还被 iron-proxy 复用(见 §2.21):`agent/proxy_sources/iron_proxy.py:2159 @ 863e313`

```python
                "access_token_env", "BWS_ACCESS_TOKEN"
```

#### `secrets.onepassword.*`

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `secrets.onepassword.enabled` | `False` | 总开关;false = 永不调用 op CLI |
| `secrets.onepassword.env` | `{}` | env 变量名 → 1Password 引用(`op://vault/item/field`);每条启动时一次 `op read` |
| `secrets.onepassword.account` | `""` | 传给 `op read --account` 的账号简写;空 = op 默认账号 |
| `secrets.onepassword.service_account_token_env` | `"OP_SERVICE_ACCOUNT_TOKEN"` | 无头认证 token 的**变量名**,导出给 op 子进程 |
| `secrets.onepassword.binary_path` | `""` | op 二进制绝对路径;设了就**逐字使用,不查 PATH**(避免信任 PATH 上第一个 `op`) |
| `secrets.onepassword.cache_ttl_seconds` | `300` | 内存 + 磁盘缓存秒数;`0` **两层全关**(不往磁盘写任何值) |
| `secrets.onepassword.override_existing` | `True` | 同 bitwarden |

`hermes_cli/config_defaults.py:2926 @ 863e313`

```python
        "onepassword": {
```

`hermes_cli/config_defaults.py:2941 @ 863e313`

```python
            "service_account_token_env": "OP_SERVICE_ACCOUNT_TOKEN",
```

`agent/secret_sources/onepassword.py:577 @ 863e313`

```python
        binary_path = str(cfg.get("binary_path") or "")
```

**"存变量名而不是存值"这个模式在本文件出现了四次**(`monitoring.export.otlp.headers_env`、
`secrets.bitwarden.access_token_env`、`secrets.onepassword.service_account_token_env`、
以及 §3 整个 `OPTIONAL_ENV_VARS`)。这是本仓库最一致的安全姿态:**config.yaml 里只有指针,
密文只在 `.env` / 环境 / 外部 manager 里**。

### 2.19 `paste_collapse_*`(2956-2975,三个顶层标量)

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `paste_collapse_threshold` | `5` | 括号粘贴(bracketed paste)处理:换行数 ≥ 此值即折叠成文件引用;`0` 关闭 |
| `paste_collapse_threshold_fallback` | `5` | 不支持括号粘贴的终端的启发式回退:同样的行数判据,但用"新增字符数/新增换行数"启发式门控,避免正常打字误判;`0` 关闭 |
| `paste_collapse_char_threshold` | `2000` | 长单行粘贴护栏:总字符数达标就折叠,即使行数没到。抓的是"一行 8000 字符的压缩 JSON / 日志"这种;`0` 关闭 |

`hermes_cli/config_defaults.py:2973 @ 863e313`

```python
    "paste_collapse_threshold": 5,
    "paste_collapse_threshold_fallback": 5,
    "paste_collapse_char_threshold": 2000,
```

注意这三个是**顶层标量**,所以在 dashboard schema 里落进 `general` 分类(§1.4 的
"top-level scalar → general" 规则)。`cli.py:16306 @ 863e313`

```python
                char_threshold = self.config.get("paste_collapse_char_threshold", 2000)
```

### 2.20 `computer_use.*`(2977-3001)

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `computer_use.cua_telemetry` | `False` | cua-driver 上游默认**开启**匿名 PostHog 遥测;Hermes 默认替用户关掉(每次调用都在子进程 env 设 `CUA_DRIVER_RS_TELEMETRY_ENABLED=0`)。设 true 才让它用自己的默认 |
| `computer_use.max_image_dimension` | `1456` | 会话开始时经 `set_config` 限制截图最长边(px),压小 SOM 多模态负载;`0` 关闭 |
| `computer_use.capture_after_mode` | `"som"` | `capture_after` 跟进模式:`som`(截图+叠加标注)/`ax`(只要元素,无 PNG,更快)/`vision`(只要像素) |
| `computer_use.no_overlay` | `None` | 关掉 cua-driver 的光标叠加层。`None`=自动探测(macOS 与 headless/WSL2 Linux 上关,其他开);`True`=总关;`False`=总开 |

`hermes_cli/config_defaults.py:2985 @ 863e313`

```python
        "cua_telemetry": False,
```

`no_overlay` 的注释附了两个真实 issue:macOS vImage 重绘循环 #47032、Linux/WSL2 空闲自旋 #28152
——叠加层在空闲时能把一个核跑满。`hermes_cli/config_defaults.py:2992 @ 863e313`

```python
        # Disable the cursor overlay rendered by cua-driver. The overlay
        # shows where agent actions land but can peg a core when idle
        # (macOS vImage redraw loop #47032; Linux/WSL2 idle spin #28152).
```

`tools/computer_use/cua_backend.py:240 @ 863e313`

```python
    return not bool(_computer_use_cfg().get("cua_telemetry", False))
```

`tools/computer_use/cua_backend.py:250 @ 863e313`

```python
        dim = int(_computer_use_cfg().get("max_image_dimension", 1456))
```

`tools/computer_use/cua_backend.py:212 @ 863e313`

```python
    val = _computer_use_cfg().get("no_overlay")
```

`tools/computer_use/tool.py:1140 @ 863e313`

```python
            "capture_after_mode", "som"
```

### 2.21 `proxy.*` —— 出口凭据注入代理 iron-proxy(3003-3061)

**解决什么问题**:远程终端沙箱(今天是 Docker)的出站流量走一个受管的 iron-proxy 子进程;
沙箱里只看得到**不透明的 proxy token**,真凭据在出口边界被换上。攻破沙箱只泄漏"只在配置好的
可信代理边界后面才有效"的 token(CA 私钥 + proxy endpoint 完整性属于该边界的一部分)。
`hermes_cli/config_defaults.py:3006 @ 863e313`

```python
    # When enabled, outbound traffic from remote terminal sandboxes (Docker
```

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `proxy.enabled` | `False` | 总开关;false = 完全 no-op(不启进程、不加 docker mount、不自动装二进制) |
| `proxy.tunnel_port` | `9090` | 隧道监听端口,沙箱拿到 `HTTPS_PROXY=http://<host>:<port>` |
| `proxy.auto_install` | `True` | 首次用时把钉版的 iron-proxy 下到 `~/.hermes/bin/` |
| `proxy.credential_source` | `"env"` | 出口时去哪查真凭据:`env`(进程环境)/`bitwarden`(每次 proxy 重启 `bws secret list` 重取,Web 上轮换即生效,需 `secrets.bitwarden.enabled`) |
| `proxy.enforce_on_docker` | `True` | proxy 启用但没跑起来时 Docker 后端**拒绝**启沙箱;false = 回落到"带真凭据直连"的 legacy 姿态 |
| `proxy.allow_env_fallback` | `False` | `credential_source: bitwarden` 但 token/project_id 缺失或取回为空时,默认**抛异常**;设 true 才退回读宿主 env(迁移期用) |
| `proxy.upstream_deny_cidrs` | `None` | SSRF 拒绝名单。省略/留空 = 安全默认(loopback、link-local 含云元数据 169.254.169.254、RFC1918);显式 `[]` 才是完全退出(只在需要打 loopback 上游的封闭测试里合理) |
| `proxy.extra_allowed_hosts` | `[]` | 除内置默认(OpenRouter/OpenAI/Anthropic/Google/xAI/Mistral/Groq/Together/DeepSeek/Nous)外的额外允许上游,支持 `*.foo.com` 通配 |

`hermes_cli/config_defaults.py:3019 @ 863e313`

```python
        "enabled": False,
```

`hermes_cli/config_defaults.py:3056 @ 863e313`

```python
        "upstream_deny_cidrs": None,
```

`None` vs `[]` 的区分是**故意**的三态语义(None=用安全默认;[]=真的不拦),而不是常见的
"None 和空列表等价"。读取点保留了这个区分:`hermes_cli/proxy_cli.py:410 @ 863e313`

```python
    deny_cidrs = proxy_cfg.get("upstream_deny_cidrs")
```

`hermes_cli/proxy_cli.py:383 @ 863e313`

```python
        tunnel_port = int(proxy_cfg.get("tunnel_port", ip._DEFAULT_TUNNEL_PORT))
```

`agent/proxy_sources/iron_proxy.py:2187 @ 863e313`

```python
                    if not (bitwarden_config or {}).get("allow_env_fallback"):
```

**块里还留了一段"墓碑注释"**,记一个**已删除**的键 `fail_on_uncovered_providers`:
它曾在 Anthropic/Azure OpenAI/Gemini env 变量存在时拒绝启动,现在这些 provider 已通过
per-provider `match_headers` 规则(`x-api-key`、`api-key`、`x-goog-api-key`)成为一等
被换凭据的 provider,fail-closed 那一档变空了。**旧配置里残留该键会被无害忽略**。
`hermes_cli/config_defaults.py:3037 @ 863e313`

```python
        # NOTE: ``fail_on_uncovered_providers`` was removed.  It gated a
```

这段墓碑注释的**位置**是个坑:它紧接着 `enforce_on_docker`,而其后半段(3043-3049)
描述的其实是**下一个键** `allow_env_fallback`,中间没有空行分隔,读起来像是一条注释。见 §7 C2。

### 2.22 `desktop.*`(3063-3104)

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `desktop.repo_scan_enabled` | `True` | Desktop Projects 侧栏的 git 仓库发现 |
| `desktop.repo_scan_roots` | `[]` | 空 roots 保留历史的"有界扫描用户 home"行为 |
| `desktop.repo_scan_exclude_paths` | `[]` | 排除路径 |
| `desktop.electron_flags` | `[]` | 追加到每次 desktop 启动的 Electron 命令行 flag(如 `--ozone-platform=x11`);接受字符串列表,单个字符串也接受并做 shell 分词 |
| `desktop.disable_gpu` | `"auto"` | `auto`=探测远程显示(SSH/VNC/RDP)时才关 GPU;`true`=总关(软件渲染,给无 GPU 的 VM/Proxmox);`false`=总开。桥到 `HERMES_DESKTOP_DISABLE_GPU` |
| `desktop.macos_signing_identity` | `""` | 仅 macOS:持久代码签名身份(登录钥匙串里的自签 "Code Signing" 证书即可,不需要 Apple 开发者账号)。证书锚定的 Designated Requirement 跨重建稳定,于是 TCC 授权(全盘访问、桌面/下载/文稿、辅助功能、自动化、麦克风)能熬过每次更新。空 = 默认稳定 ad-hoc 签名(标识符钉定) |
| `desktop.auto_continue.enabled` | `True` | 被 app/后端/机器崩溃打断的 turn,恢复会话时自动重投那条 prompt(显示为 "resumed interrupted turn") |
| `desktop.auto_continue.freshness_minutes` | `15` | 打断多新才自动续;过期的只展示恢复出来的部分 transcript |
| `desktop.auto_continue.max_attempts` | `2` | 崩溃循环熔断:一个被打断 turn 的最大自动重跑次数 |

`hermes_cli/config_defaults.py:3065 @ 863e313`

```python
    "desktop": {
```

`hermes_cli/config_defaults.py:3097 @ 863e313`

```python
        "auto_continue": {
            "enabled": True,
```

`hermes_cli/main.py:6963 @ 863e313`

```python
    raw_flags = desktop_cfg.get("electron_flags")
```

`hermes_cli/main.py:6969 @ 863e313`

```python
    raw_gpu = desktop_cfg.get("disable_gpu", "auto")
```

`hermes_cli/main.py:6628 @ 863e313`

```python
        identity = desktop.get("macos_signing_identity")
```

`tui_gateway/server.py:7193 @ 863e313`

```python
        minutes = float(cfg.get("freshness_minutes", _AUTO_CONTINUE_FRESHNESS_MINUTES_DEFAULT))
```

`tui_gateway/server.py:11379 @ 863e313`

```python
    roots = source.get("roots", source.get("repo_scan_roots", defaults["repo_scan_roots"]))
```

### 2.23 `vertex.*`(3106-3123)

块头写了一条**"什么算 secret"的判定规则**:Vertex 走 OAuth2(从服务账号 JSON 或 ADC 铸短期
token),不是静态 API key;凭据**路径**是"secret-adjacent 指针",住 `.env`
(`VERTEX_CREDENTIALS_PATH` / `GOOGLE_APPLICATION_CREDENTIALS`);而 project/region 是
**非密的路由配置**,住 config.yaml。

| 点分路径 | 默认值 | 语义 |
|---|---|---|
| `vertex.project_id` | `""` | GCP 项目 ID;空 → 用服务账号 JSON 里内嵌的(或 ADC 解析出的) |
| `vertex.region` | `"global"` | Gemini 3.x preview 模型**必须**用 `"global"`(区域端点会静默 404 它们);模型钉在某区域时才改 |

`hermes_cli/config_defaults.py:3115 @ 863e313`

```python
    "vertex": {
```

`hermes_cli/config_defaults.py:3122 @ 863e313`

```python
        "region": "global",
```

`agent/vertex_adapter.py:66 @ 863e313`

```python
def _resolve_region(explicit: Optional[str] = None) -> str:
    """Region precedence: explicit arg > VERTEX_REGION env > config.yaml > default."""
```

`agent/vertex_adapter.py:86 @ 863e313`

```python
    cfg_project = str(_vertex_config().get("project_id") or "").strip()
```

注释里"Both are bridged to the VERTEX_PROJECT_ID / VERTEX_REGION env vars"与代码不符,见 §7 C3。

### 2.24 `_config_version`(3125-3126)

`hermes_cli/config_defaults.py:3126 @ 863e313`

```python
    "_config_version": 33,
```

它是**迁移阶梯的"最新版本"真相源**:`hermes_cli/config.py:1825 @ 863e313`

```python
    latest = _coerce_config_version(DEFAULT_CONFIG.get("_config_version", 1)) or 1
```

与迁移注册表的最高目标版本一致(33),这条一致性在基线上成立:
`hermes_cli/config_migrations.py:667 @ 863e313`

```python
    (33, _migrate_to_33),
```

阶梯的语义有个细节:`current_ver` **在整个阶梯里不前进**,每一步都用同一个初始值判定,
复刻了原来那串 `if current_ver < N:` 的行为。`hermes_cli/config_migrations.py:683 @ 863e313`

```python
    for target_ver, migration_fn in MIGRATIONS:
        if current_ver < target_ver:
            migration_fn(results, quiet)
```

以 `_` 开头的键在 `get_missing_config_fields` 里被跳过,所以 `_config_version` 不会被
当成"新配置项"提示。`hermes_cli/config.py:1201 @ 863e313`

```python
            if key.startswith('_'):
```

---

## 3. `OPTIONAL_ENV_VARS`(3130-4313)—— 它到底是什么

### 3.1 数据形状

一个 `{ENV_VAR_NAME: metadata_dict}` 的**平表**,静态字面量里有 **151** 条
(我 exec 该模块后 `len(OPTIONAL_ENV_VARS)` 实测 151;运行时还会被注入更多,见 §3.4)。
`hermes_cli/config_defaults.py:3130 @ 863e313`

```python
OPTIONAL_ENV_VARS = {
```

字段出现次数(151 条里):`description` 151、`prompt` 151、`category` 151、`url` 136、
`password` 139、`advanced` 77、`tools` 25、`help` 3。字段语义:

| 字段 | 类型 | 语义 | 谁消费 |
|---|---|---|---|
| `description` | str | 一句话说明,展示在 setup checklist / dashboard 卡片 | `config.py:2325`、`web_server.py:7054` |
| `prompt` | str | 交互式输入时的提示语 | `setup.py:3535`、`web_server.py:8243` |
| `url` | str \| None | 去哪申请这个 key(注册页) | `config.py:2337`、`provider_catalog.py:161` |
| `password` | bool | 是否密文字段(dashboard 打码 + reveal 门控;也参与沙箱 blocklist 判定) | `web_server.py:7057`、`tools/environments/local.py:246` |
| `category` | str | `provider` / `tool` / `skill` / `messaging` / `setting` 五选一 | 分流的主键,见 §3.3 |
| `advanced` | bool | 高级项:setup 向导**跳过**它们("those are for power users") | `config.py:2308` |
| `tools` | list[str] | 这个 key 解锁哪些工具,用于 checklist 上的 `→ web_search, web_extract` 尾注 | `config.py:5270`、`setup.py:3558` |
| `help` | str | 更长的操作指引(只有三条 Slack 键有) | `web_server.py:8244` |

category 分布(静态表):`provider` 53、`messaging` 52、`tool` 39、`skill` 4、`setting` 3。

### 3.2 它**不是**什么

它**不是**"Hermes 认识的全部环境变量"。另有一个 `_EXTRA_ENV_KEYS` 冻结集,装
"由 setup/provider 流程直接管理、会被写进 `.env` 但不进 `OPTIONAL_ENV_VARS`"的键。
`hermes_cli/config.py:261 @ 863e313`

```python
# Env var names written to .env that aren't in OPTIONAL_ENV_VARS
# (managed by setup/provider flows directly).
_EXTRA_ENV_KEYS = frozenset({
```

两者的**并集**才是"Hermes 已知 env 键"。`hermes_cli/env_loader.py:66 @ 863e313`

```python
    return set(OPTIONAL_ENV_VARS.keys()) | set(_EXTRA_ENV_KEYS)
```

`hermes_cli/config.py:4095 @ 863e313`

```python
    known_keys = set(OPTIONAL_ENV_VARS.keys()) | _EXTRA_ENV_KEYS
```

**分工的判据**在文件末尾被写死了一条:`HERMES_TOOL_PROGRESS_MODE` 已废弃但**仍在运行时被
gateway 作为向后兼容回退读取**,所以它必须留在 `_EXTRA_ENV_KEYS`(reload/兼容路径要知道它),
但**故意不进** `OPTIONAL_ENV_VARS`——因为后者喂的是**面向用户的界面**(dashboard keys 页、
setup checklist),废弃旋钮不该在那里被推荐。`hermes_cli/config_defaults.py:4290 @ 863e313`

```python
    # HERMES_TOOL_PROGRESS_MODE is deprecated — tool progress is configured via
    # display.tool_progress in config.yaml (off|new|all|verbose|log). The
    # gateway still falls back to HERMES_TOOL_PROGRESS_MODE for backward
    # compatibility, so it lives in _EXTRA_ENV_KEYS (known to reload and
    # compatibility paths) but is intentionally NOT listed here:
    # OPTIONAL_ENV_VARS feeds user-facing surfaces (dashboard keys page, setup
    # checklists) and deprecated knobs shouldn't be offered there.
```

对照 `_EXTRA_ENV_KEYS` 里那条同款注释:`hermes_cli/config.py:295 @ 863e313`

```python
    # HERMES_TOOL_PROGRESS_MODE is deprecated (replaced by display.tool_progress
```

**这是本段最重要的一条设计原则,值得单独抄走**:
> "运行时认识的 env 键集合" 与 "向用户推荐的 env 键集合" 是**两张表**。
> 废弃键从后者摘除、在前者保留,才能既不误导用户又不破坏老配置。

### 3.3 六个消费者(`category` 是分流主键)

1. **`.env` 的 reload 与删除语义**:`reload_env()` 会删掉"`.env` 里已不存在但仍在
   `os.environ` 里"的**已知**键——只删已知键,避免误伤无关环境。
   `hermes_cli/config.py:4102 @ 863e313`

   ```python
    for key in known_keys:
        if key not in env_vars and key in os.environ:
   ```

2. **setup 向导 / migration 的"缺什么"清单**:`hermes_cli/config.py:985 @ 863e313`

   ```python
        for var_name, info in OPTIONAL_ENV_VARS.items():
            if not get_env_value(var_name):
   ```

   `advanced` 的键在这里被过滤掉:`hermes_cli/config.py:2306 @ 863e313`

   ```python
    missing_optional = [
        v for v in missing_optional
        if v["name"] not in required_names and not v.get("advanced")
    ]
   ```

   `category == "tool"` 与 `category == "messaging" and not advanced` 各成一张 checklist。
   `hermes_cli/setup.py:3544 @ 863e313`

   ```python
    missing_tools = [v for v in missing_optional if v.get("category") == "tool"]
   ```

3. **`hermes config check` 的 Optional 列表**:`hermes_cli/config.py:5266 @ 863e313`

   ```python
        for var_name, info in OPTIONAL_ENV_VARS.items():
            if get_env_value(var_name):
   ```

4. **dashboard / desktop 的 Keys 页**:每条键渲染成一行,`password` 决定是否打码,
   `provider`/`provider_label` 由 provider catalog 补齐,未在任何 catalog 里的 `.env` 键
   作为 `custom` 行兜底(默认当密文)。`hermes_cli/web_server.py:7078 @ 863e313`

   ```python
    for var_name, info in OPTIONAL_ENV_VARS.items():
        result[var_name] = _row(var_name, info)
   ```

5. **消息平台卡片的 env 发现**:按 `category == "messaging"` + 平台前缀匹配,
   排除三个跨切面的 gateway 键与 setup-hidden 键。`hermes_cli/web_server.py:8162 @ 863e313`

   ```python
    for name, info in OPTIONAL_ENV_VARS.items():
        if info.get("category") != "messaging":
   ```

   `hermes_cli/web_server.py:8128 @ 863e313`

   ```python
_MESSAGING_KEYS_PAGE_KEYS = frozenset({
    "GATEWAY_ALLOW_ALL_USERS",
    "GATEWAY_PROXY_KEY",
    "GATEWAY_PROXY_URL",
})
   ```

6. **【最重要】沙箱 env blocklist**:agent 终端 / `execute_code` 子进程的环境擦洗名单
   **直接由 category 派生**。`tools/environments/local.py:241 @ 863e313`

   ```python
        from hermes_cli.config import OPTIONAL_ENV_VARS
        for name, metadata in OPTIONAL_ENV_VARS.items():
            category = metadata.get("category")
            if category in {"tool", "messaging"}:
                blocked.add(name)
            elif category == "setting" and metadata.get("password"):
                blocked.add(name)
   ```

   **规则**:`tool` 与 `messaging` 无条件屏蔽;`setting` 只有 `password` 为真才屏蔽;
   `provider` **不由这个循环屏蔽**(它们由 `PROVIDER_REGISTRY` 循环 + 一份硬编码名单覆盖);
   `skill` **故意不屏蔽**。

   `skill` 这一档的存在理由,`OPTIONAL_ENV_VARS` 自己的注释写清楚了:skill 合法地需要这些值
   透传给 curl,所以给它们一个**不同于 `tool` 的 category**,好让 blocklist 循环跳过。
   `hermes_cli/config_defaults.py:3754 @ 863e313`

   ```python
    # ── Bundled skills (opt-in: only needed if the user uses that skill) ──
    # These use category="skill" (distinct from "tool") so the sandbox
    # env blocklist in tools/environments/local.py does NOT rewrite them —
    # skills legitimately need these passed through to curl via
    # tools/env_passthrough.py when the user's skill calls out.
   ```

   **这条我实地核对过,注释与代码一致**。这是"一个纯数据字段(category)同时是 UI 分类、
   setup 分流键、和安全边界"的典型——**改一条 category 会同时改安全语义**。

   顺带:`VERTEX_CREDENTIALS_PATH` 因为 `password=False` 会被上面的循环漏掉,
   所以在硬编码名单里补了一次,并写了注释说明原因。`tools/environments/local.py:263 @ 863e313`

   ```python
        # Path to a GCP service-account JSON, not a bare key, so
        # OPTIONAL_ENV_VARS marks it password=False and the loop above skips it.
        "VERTEX_CREDENTIALS_PATH",
   ```

另有一个只读消费者:provider catalog 在 provider profile 没给 `signup_url` 时,
回落到该 provider 首个 API-key 变量的 `url`。`hermes_cli/provider_catalog.py:159 @ 863e313`

```python
        if not signup_url and api_key_vars:
            info = OPTIONAL_ENV_VARS.get(api_key_vars[0]) or {}
```

### 3.4 运行时注入:这张表在 import 时会被**原地扩表**两次

**注入一:provider profile**。`providers/` 下任何 `auth_type="api_key"` 的 provider,
它声明的 `env_vars` 会自动被合成一条 `OPTIONAL_ENV_VARS` 条目(硬编码条目优先,已存在就跳过),
于是"加一个 provider"不需要改本文件。`hermes_cli/config.py:5306 @ 863e313`

```python
def _inject_profile_env_vars() -> None:
```

`hermes_cli/config.py:5320 @ 863e313`

```python
            for _var in _pp.env_vars:
                if _var in OPTIONAL_ENV_VARS:
                    continue
                _is_key = not _var.endswith("_BASE_URL") and not _var.endswith("_URL")
                OPTIONAL_ENV_VARS[_var] = {
```

`password` 由**命名启发式**决定:不以 `_BASE_URL` / `_URL` 结尾的就当 key(密文)。
注入是 import 时**急切执行**的:`hermes_cli/config.py:5337 @ 863e313`

```python
_inject_profile_env_vars()
```

**注入二:平台插件 manifest**。`plugins/platforms/*/plugin.yaml` 的 `requires_env` +
`optional_env` 被读进来,同样"硬编码条目优先"。`hermes_cli/config.py:5363 @ 863e313`

```python
def _inject_platform_plugin_env_vars() -> None:
```

`hermes_cli/config.py:5408 @ 863e313`

```python
                if name in OPTIONAL_ENV_VARS:
                    continue  # hardcoded entry wins (back-compat)
```

密文判定同样是启发式(`_TOKEN`/`_SECRET`/`_KEY`/`_PASSWORD`/`_JSON` 后缀),
除非 manifest 显式 `password: false`。这行的写法值得看一眼——`not X is False` 在 Python 里
解析为 `not (X is False)`(比较运算符优先级高于 `not`),所以语义是对的,但**极易被误读**:
`hermes_cli/config.py:5414 @ 863e313`

```python
                if not is_secret and not meta.get("password") is False:
```

默认 `category` 是 `"messaging"`(因为这是平台插件),所以**插件声明的 env 变量默认会进
沙箱 blocklist**——安全默认是对的。`hermes_cli/config.py:5427 @ 863e313`

```python
                    "category": meta.get("category") or "messaging",
```

两个注入都是 `try/except: pass` **全吞异常**:一个坏掉的 `plugin.yaml` 不能炸掉 CLI import。
代价是**静默降级**——键不出现,用户不知道为什么。`hermes_cli/config.py:5429 @ 863e313`

```python
    except Exception:
        pass
```

`hermes_cli/config.py:5434 @ 863e313`

```python
_inject_platform_plugin_env_vars()
```

### 3.5 表内分区与条目穷举

文件用五条 `# ── ... ──` 注释横线把表分区。分区不影响代码(分类靠 `category` 字段),
但是**阅读时的唯一导航**。

`hermes_cli/config_defaults.py:3131 @ 863e313`

```python
    # ── Provider (handled in provider selection, not shown in checklists) ──
```

`hermes_cli/config_defaults.py:3554 @ 863e313`

```python
    # ── Tool API keys ──
```

`hermes_cli/config_defaults.py:3908 @ 863e313`

```python
    # ── Messaging platforms ──
```

`hermes_cli/config_defaults.py:4280 @ 863e313`

```python
    # ── Agent settings ──
```

#### (a) `category: "provider"` —— 53 条(3132-3553)

模式极其规整:每个 provider 一对 `X_API_KEY` + `X_BASE_URL`,`advanced: True`
(所以 setup 向导跳过它们——provider 在"选 provider"那步单独处理)。

```
NOUS_BASE_URL, OPENROUTER_API_KEY, GOOGLE_API_KEY, GEMINI_API_KEY, GEMINI_BASE_URL,
VERTEX_CREDENTIALS_PATH, XAI_API_KEY, XAI_BASE_URL, NVIDIA_API_KEY, NVIDIA_BASE_URL,
LM_API_KEY, LM_BASE_URL, GLM_API_KEY, ZAI_API_KEY, Z_AI_API_KEY, GLM_BASE_URL,
KIMI_API_KEY, KIMI_BASE_URL, KIMI_CN_API_KEY, STEPFUN_API_KEY, STEPFUN_BASE_URL,
ARCEEAI_API_KEY, ARCEE_BASE_URL, GMI_API_KEY, GMI_BASE_URL, ACTUAL_API_KEY,
ACTUAL_BASE_URL, FIREWORKS_API_KEY, MINIMAX_API_KEY, MINIMAX_BASE_URL,
MINIMAX_CN_API_KEY, MINIMAX_CN_BASE_URL, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL,
DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, HERMES_QWEN_BASE_URL, OPENCODE_ZEN_API_KEY,
OPENCODE_ZEN_BASE_URL, OPENCODE_GO_API_KEY, OPENCODE_GO_BASE_URL, HF_TOKEN,
HF_BASE_URL, OLLAMA_API_KEY, OLLAMA_BASE_URL, XIAOMI_API_KEY, XIAOMI_BASE_URL,
UPSTAGE_API_KEY, UPSTAGE_BASE_URL, AWS_REGION, AWS_PROFILE,
AZURE_FOUNDRY_API_KEY, AZURE_FOUNDRY_BASE_URL
```

值得注意的几条:

- **别名族**:`GOOGLE_API_KEY` ↔ `GEMINI_API_KEY`;`GLM_API_KEY` ↔ `ZAI_API_KEY` ↔
  `Z_AI_API_KEY`。三个 Z.AI 别名各占一条,描述里互相指认。
  `hermes_cli/config_defaults.py:3233 @ 863e313`

  ```python
    "GLM_API_KEY": {
        "description": "Z.AI / GLM API key (also recognized as ZAI_API_KEY / Z_AI_API_KEY)",
  ```

- **`VERTEX_CREDENTIALS_PATH` 是全表最长的 description**,它把整条 fallback 链写进了文案:
  显式路径 → `GOOGLE_APPLICATION_CREDENTIALS` → ADC(`gcloud auth application-default login`),
  并指引 project/region 去 config.yaml 的 `vertex:`。
  `hermes_cli/config_defaults.py:3173 @ 863e313`

  ```python
    "VERTEX_CREDENTIALS_PATH": {
        "description": "Path to a Google Cloud service account JSON for Vertex AI (Gemini). "
  ```

- **AWS Bedrock 没有 API key**,只有 `AWS_REGION` / `AWS_PROFILE` 两个非密项;
  dashboard 靠 `auth_type == "aws_sdk"` 把它们挂到 Bedrock 卡片上。
  `hermes_cli/web_server.py:7005 @ 863e313`

  ```python
        if d.auth_type == "aws_sdk":
            for aws_var in ("AWS_REGION", "AWS_PROFILE"):
  ```

- **`url` 字段的两种"空"**:多数写 `None`,但 `DEEPSEEK_BASE_URL` / `DASHSCOPE_BASE_URL`
  写的是 `""`。消费者用 `info.get("url") if info.get("url") is not None else cat_meta.get("url")`,
  所以 `""` 与 `None` 走的是**不同分支**(`""` 会阻断 catalog 回填)。
  `hermes_cli/config_defaults.py:3403 @ 863e313`

  ```python
        "url": "",
  ```

  `hermes_cli/web_server.py:7055 @ 863e313`

  ```python
            "url": info.get("url") if info.get("url") is not None else cat_meta.get("url"),
  ```

#### (b) `category: "tool"` —— 39 条(3555-3752 + 3792-3906)

搜索/抓取:`EXA_API_KEY`、`PARALLEL_API_KEY`、`FIRECRAWL_API_KEY`、`FIRECRAWL_API_URL`、
`FIRECRAWL_GATEWAY_URL`、`TOOL_GATEWAY_DOMAIN`、`TOOL_GATEWAY_SCHEME`、
`TOOL_GATEWAY_USER_TOKEN`、`TAVILY_API_KEY`、`SEARXNG_URL`、`BRAVE_SEARCH_API_KEY`。

浏览器:`BROWSERBASE_API_KEY`、`BROWSERBASE_PROJECT_ID`、`BROWSER_USE_API_KEY`、
`FIRECRAWL_BROWSER_TTL`、`AGENT_BROWSER_ENGINE`、`CAMOFOX_URL`、`CAMOFOX_API_KEY`。

生成/语音:`FAL_KEY`、`KREA_API_KEY`、`VOICE_TOOLS_OPENAI_KEY`、`ELEVENLABS_API_KEY`、
`MISTRAL_API_KEY`、`PORCUPINE_ACCESS_KEY`。

其他:`GITHUB_TOKEN`(Skills Hub)。

记忆后端(每家一到两条,分区注释各自成段):`HONCHO_API_KEY` / `HONCHO_BASE_URL`、
`HINDSIGHT_API_KEY` / `HINDSIGHT_API_URL`、`SUPERMEMORY_API_KEY`、`MEM0_API_KEY`、
`RETAINDB_API_KEY` / `RETAINDB_BASE_URL`、`BRV_API_KEY`、`OPENVIKING_API_KEY` /
`OPENVIKING_ENDPOINT`。

可观测:`HERMES_LANGFUSE_PUBLIC_KEY`(**`password: False`**——它是公钥)、
`HERMES_LANGFUSE_SECRET_KEY`、`HERMES_LANGFUSE_BASE_URL`。

25 条带 `tools` 字段的键全在这一档(加一条 provider 档的 `OPENROUTER_API_KEY`,
它的 `tools` 是 `["vision_analyze"]`)。`hermes_cli/config_defaults.py:3555 @ 863e313`

```python
    "EXA_API_KEY": {
        "description": "Exa API key for AI-native web search and contents",
        "prompt": "Exa API key",
        "url": "https://exa.ai/",
        "tools": ["web_search", "web_extract"],
```

`TOOL_GATEWAY_*` 四条是 **Nous 订阅者专属**的共享工具网关:给一个域名后缀就能派生出
各 vendor 主机(`nousresearch.com` → `firecrawl-gateway.nousresearch.com`),
scheme 可切 `http` 供本地测试,token 不显式给就从 Hermes auth store 读。
`hermes_cli/config_defaults.py:3595 @ 863e313`

```python
    "TOOL_GATEWAY_DOMAIN": {
        "description": "Shared tool-gateway domain suffix for Nous Subscribers only, used to derive vendor hosts, e.g. nousresearch.com -> firecrawl-gateway.nousresearch.com",
```

`hermes_cli/config_defaults.py:3611 @ 863e313`

```python
    "TOOL_GATEWAY_USER_TOKEN": {
```

#### (c) `category: "skill"` —— 4 条(3759-3790)

`NOTION_API_KEY`、`LINEAR_API_KEY`、`AIRTABLE_API_KEY`、`TENOR_API_KEY`。
全部 `advanced: True` + `password: True`。它们的**唯一**区别就是 category(见 §3.3 第 6 条)。
`hermes_cli/config_defaults.py:3759 @ 863e313`

```python
    "NOTION_API_KEY": {
```

#### (d) `category: "messaging"` —— 52 条(3909-4278)

Telegram(3):`TELEGRAM_BOT_TOKEN`、`TELEGRAM_ALLOWED_USERS`、`TELEGRAM_PROXY`。
`TELEGRAM_PROXY` 的语义是"覆盖 `HTTPS_PROXY`",支持 `http://`/`https://`/`socks5://`。
`hermes_cli/config_defaults.py:3923 @ 863e313`

```python
    "TELEGRAM_PROXY": {
```

Discord(3):`DISCORD_BOT_TOKEN`、`DISCORD_ALLOWED_USERS`、`DISCORD_REPLY_TO_MODE`
(`off`/`first`(默认)/`all`)。

Slack(3):`SLACK_BOT_TOKEN`、`SLACK_APP_TOKEN`、`SLACK_ALLOWED_USERS` ——
**全表仅有的三条带 `help` 字段**,并且 description 里直接列了需要的 OAuth scope
与 Event Subscription。这三条是"文档写进数据表"的极端案例。
`hermes_cli/config_defaults.py:3950 @ 863e313`

```python
    "SLACK_BOT_TOKEN": {
        "description": "Slack bot token (xoxb-). Get from OAuth & Permissions after installing your app. "
                       "Required scopes: chat:write, app_mentions:read, channels:history, groups:history, "
                       "im:history, im:read, im:write, mpim:history, mpim:read, users:read, files:read, files:write",
```

`SLACK_ALLOWED_USERS` 的 description 里还埋了一条**运维坑**:不设它 Slack 可能连上但
默认拒绝消息。`hermes_cli/config_defaults.py:3971 @ 863e313`

```python
        "description": "Comma-separated Slack member IDs allowed to use Hermes, e.g. U01ABC2DEF3. Without this, Slack may connect but deny messages by default.",
```

Mattermost(5):`MATTERMOST_URL`、`MATTERMOST_TOKEN`、`MATTERMOST_ALLOWED_USERS`、
`MATTERMOST_REQUIRE_MENTION`(默认 true)、`MATTERMOST_FREE_RESPONSE_CHANNELS`。

Matrix(9):`MATRIX_HOMESERVER`、`MATRIX_ACCESS_TOKEN`、`MATRIX_USER_ID`、
`MATRIX_ALLOWED_USERS`、`MATRIX_REQUIRE_MENTION`、`MATRIX_FREE_RESPONSE_ROOMS`、
`MATRIX_AUTO_THREAD`(房间默认 true)、`MATRIX_DM_AUTO_THREAD`(DM 默认 false)、
`MATRIX_DEVICE_ID`(稳定 device ID 让 E2EE 跨重启持久)、`MATRIX_RECOVERY_KEY`
(device key 轮换后的交叉签名验证)。共 10 条。
`hermes_cli/config_defaults.py:4073 @ 863e313`

```python
    "MATRIX_DEVICE_ID": {
        "description": "Stable Matrix device ID for E2EE persistence across restarts (e.g. HERMES_BOT)",
```

BlueBubbles / iMessage(4):`BLUEBUBBLES_SERVER_URL`、`BLUEBUBBLES_PASSWORD`、
`BLUEBUBBLES_ALLOWED_USERS`、`BLUEBUBBLES_ALLOW_ALL_USERS`。

QQ(8):`QQ_APP_ID`、`QQ_CLIENT_SECRET`、`QQ_ALLOWED_USERS`、`QQ_GROUP_ALLOWED_USERS`、
`QQ_ALLOW_ALL_USERS`、`QQBOT_HOME_CHANNEL`、`QQBOT_HOME_CHANNEL_NAME`、`QQ_SANDBOX`。
这一族**普遍省略 `url` 与 `password`**(见 §6 D6)。
`hermes_cli/config_defaults.py:4115 @ 863e313`

```python
    "QQ_APP_ID": {
```

IRC(5):`IRC_SERVER`、`IRC_CHANNEL`、`IRC_NICKNAME`、`IRC_SERVER_PASSWORD`、
`IRC_NICKSERV_PASSWORD`。

跨切面 gateway / API server(9):
`GATEWAY_ALLOW_ALL_USERS`、`API_SERVER_ENABLED`、`API_SERVER_KEY`、`API_SERVER_PORT`
(默认 8642)、`API_SERVER_HOST`(默认 127.0.0.1)、`API_SERVER_MODEL_NAME`、
`GATEWAY_PROXY_URL`、`GATEWAY_PROXY_KEY`、以及 webhook 三条 `WEBHOOK_ENABLED` /
`WEBHOOK_PORT`(默认 8644)/ `WEBHOOK_SECRET`。

`API_SERVER_KEY` 的 description 记了一条**硬安全规则**:API server 启用时**必须**有它,
没有就拒绝启动;而 `API_SERVER_HOST` 补了一句"即使绑 loopback 也仍然需要 key"。
`hermes_cli/config_defaults.py:4210 @ 863e313`

```python
    "API_SERVER_KEY": {
        "description": "Bearer token for API server authentication. Required whenever the API server is enabled; server refuses to start without it.",
```

`hermes_cli/config_defaults.py:4227 @ 863e313`

```python
        "description": "Host/bind address for the API server (default: 127.0.0.1). API_SERVER_KEY is still required even on loopback binds.",
```

`GATEWAY_PROXY_URL` 描述了 **proxy mode**:gateway 只做平台 I/O,agent 工作全部委托给
远端 Hermes API server(给"Docker E2EE 容器中继到宿主 agent"这种拓扑用),
并说"Also configurable via gateway.proxy_url in config.yaml"。
`hermes_cli/config_defaults.py:4242 @ 863e313`

```python
    "GATEWAY_PROXY_URL": {
```

它有一条**专门的测试**在盯着这条元数据存在:`tests/gateway/test_proxy_mode.py:293 @ 863e313`

```python
        assert "GATEWAY_PROXY_URL" in OPTIONAL_ENV_VARS
```

#### (e) `category: "setting"` —— 3 条(4280-4312)

| 键 | password | 语义 |
|---|---|---|
| `SUDO_PASSWORD` | `True` | 终端命令需要 root 时的 sudo 密码;**显式设成空串 = 尝试空密码且不提示** |
| `HERMES_PREFILL_MESSAGES_FILE` | `False` | 指向一个 JSON 文件,装 few-shot 预热用的**临时** prefill 消息 |
| `HERMES_EPHEMERAL_SYSTEM_PROMPT` | `False` | API 调用时注入的临时系统提示,**永不持久化进会话** |

`hermes_cli/config_defaults.py:4283 @ 863e313`

```python
    "SUDO_PASSWORD": {
        "description": "Sudo password for terminal commands requiring root access; set to an explicit empty string to try empty without prompting",
```

只有 `SUDO_PASSWORD` 因 `password: True` 进沙箱 blocklist;另两条 `password: False`
所以**会透传进 agent 终端子进程**(见 §3.3 第 6 条规则)。

分区里还留了一条**墓碑注释**:`MESSAGING_CWD` 已删除,改用 config.yaml 的 `terminal.cwd`,
gateway 读的是从它桥来的 `TERMINAL_CWD`。`hermes_cli/config_defaults.py:4281 @ 863e313`

```python
    # NOTE: MESSAGING_CWD was removed here — use terminal.cwd in config.yaml
    # instead.  The gateway reads TERMINAL_CWD (bridged from terminal.cwd).
```

---

## 4. 环境变量索引(本段涉及的 env,含"非 OPTIONAL_ENV_VARS 的内部载体")

除了 `OPTIONAL_ENV_VARS` 里那 151 条,本段的 config 键还**桥接/派生**出一批内部 env:

| env 变量 | 来源 config 键 | 桥接点 | 方向/优先级 |
|---|---|---|---|
| `HERMES_MEDIA_DELIVERY_STRICT` | `gateway.strict` | `gateway/run.py:2237` | config 权威 |
| `HERMES_MEDIA_ALLOW_DIRS` | `gateway.media_delivery_allow_dirs` | `gateway/run.py:2249` | config 权威(list → `os.pathsep` join) |
| `HERMES_MEDIA_TRUST_RECENT_FILES` | `gateway.trust_recent_files` | `gateway/run.py:2252` | config 权威 |
| `HERMES_MEDIA_TRUST_RECENT_SECONDS` | `gateway.trust_recent_files_seconds` | `gateway/run.py:2257` | config 权威 |
| `HERMES_GATEWAY_PLATFORM_CONNECT_TIMEOUT` | `gateway.platform_connect_timeout` | `gateway/run.py:2267` | **env 优先**(逃生口) |
| `HERMES_CJK_FTS` | `sessions.cjk_fts` | `cli.py:783`、`gateway/run.py:1894` | config 权威 |
| `HERMES_SEARCH_SLOW_MS` | `sessions.search_slow_ms` | `cli.py:785`、`gateway/run.py:1896` | config 权威 |
| `HERMES_CRON_MAX_PARALLEL` | `cron.max_parallel_jobs` | `cron/scheduler.py:4230` | **env 优先** |
| `HERMES_CRON_SESSION_DB_TIMEOUT` | `cron.session_db_timeout_seconds` | `cron/scheduler.py:2933` | **env 优先** |
| `HERMES_GATEWAY_MAX_STARTS` / `HERMES_GATEWAY_START_WINDOW_S` | `gateway.respawn_storm.*` | `hermes_cli/gateway.py:5059` | **env 优先**(逃生口) |
| `HERMES_DESKTOP_DISABLE_GPU` | `desktop.disable_gpu` | `hermes_cli/main.py:6969` 附近 | env 形式仍可用 |
| `HERMES_SCALE_TO_ZERO` | **不是 config 键**(NAS Labs 开关的 env 戳) | `gateway/scale_to_zero.py:36` | 只有 env |
| `CUA_DRIVER_RS_TELEMETRY_ENABLED` | `computer_use.cua_telemetry`(取反) | `tools/computer_use/cua_backend.py:190` | config → 子进程 env |
| `BWS_SERVER_URL` | `secrets.bitwarden.server_url` | `agent/secret_sources/bitwarden.py:516` | config → 子进程 env |
| `OP_SERVICE_ACCOUNT_TOKEN` | `secrets.onepassword.service_account_token_env` **指向的变量的值** | `agent/secret_sources/onepassword.py:72` | env 名的间接层 |
| `VERTEX_PROJECT_ID` / `VERTEX_REGION` | `vertex.project_id` / `vertex.region` | **无桥接**,adapter 直接分别读 env 与 config | env 优先(见 §7 C3) |
| `HERMES_TOOL_PROGRESS_MODE` | (废弃,`display.tool_progress` 取代) | `hermes_cli/config.py:301` | 仅兼容回退 |

`hermes_cli/gateway.py:5059 @ 863e313`

```python
    # the env vars ``HERMES_GATEWAY_MAX_STARTS`` /
```

`gateway/scale_to_zero.py:36 @ 863e313`

```python
SCALE_TO_ZERO_ENV = "HERMES_SCALE_TO_ZERO"
```

`tools/computer_use/cua_backend.py:190 @ 863e313`

```python
_CUA_TELEMETRY_ENV_VAR = "CUA_DRIVER_RS_TELEMETRY_ENABLED"
```

**模式总结**:本仓库的桥接有**两个方向**,而且注释里被明确对比过(见 §2.10 那段):
- **config 权威型**:桥接时无条件覆盖 env,config.yaml 说了算;
- **逃生口型**:env 已显式设置就不覆盖,env 说了算。
  用在"运维要在不改配置文件的前提下临时救火"的旋钮上(平台连接超时、respawn 熔断、cron 并行度)。

---

## 5. 配套测试(行为规格)

我用键名反查 `tests/`,与本段直接相关的:

- `tests/plugins/test_chronos_cron.py`、`tests/plugins/test_chronos_verify.py`、
  `tests/gateway/test_cron_fire_webhook.py` —— `cron.chronos.*` 与 fire JWT 验签
- `tests/hermes_cli/test_cron.py`、`tests/cron/test_execution_ledger.py` —— cron 其余键
- `tests/gateway/test_kanban_auto_decompose_live.py` —— `kanban.auto_decompose*`
- `tests/tools/test_tool_search.py` —— `tools.tool_search.*` 的钳位与分层
- `tests/gateway/test_platform_base.py` —— `gateway.max_inbound_media_bytes`
- `tests/gateway/test_scale_to_zero.py`、`tests/gateway/test_scale_to_zero_watcher.py`
- `tests/hermes_cli/test_gateway_restart_loop.py` —— `gateway.restart_loop_guard.*`
- `tests/gateway/test_proxy_mode.py` —— `gateway.proxy_url` + `GATEWAY_PROXY_URL` 元数据
- `tests/monitoring/test_gateway_health_export.py`、`tests/monitoring/test_otlp_exporter.py`
  —— `monitoring.*`(含 resource_attributes 允许名单)
- `tests/hermes_cli/test_backup.py`、`test_cmd_update.py`、`test_update_autostash.py`、
  `test_update_yes_flag.py` —— `updates.*`
- `tests/hermes_cli/test_state_db_guard.py` —— `sessions.*` 维护
- `tests/tools/test_x_search_tool.py`、`tests/skills/test_xurl_x_search_routing.py` —— `x_search.*`
- `tests/computer_use/test_cua_no_overlay.py`、`tests/tools/test_computer_use.py` —— `computer_use.*`
- `tests/test_iron_proxy_e2e.py` —— `proxy.*`
- `tests/hermes_cli/test_desktop_repo_discovery_config.py` —— `desktop.repo_scan_*`
  **并直接断言 `CONFIG_SCHEMA` 里的类型**,是 §1.4 那条身份的行为规格
- `tests/tools/test_local_env_blocklist.py` —— §3.3 第 6 条(category → 沙箱 blocklist)
- `tests/hermes_cli/test_env_custom_keys.py` —— "不在任何 catalog 里的 `.env` 键"的处理
- `tests/hermes_cli/test_upstage_provider.py`、`test_gmi_provider.py`、
  `test_fireworks_provider.py`、`test_api_key_providers.py` —— OPTIONAL_ENV_VARS 条目的
  逐字段断言(`category` / `password` / `url` 都被断言过)
- `tests/hermes_cli/test_web_server.py` —— `OPTIONAL_ENV_VARS` → `/api/env` 的渲染
- `tests/hermes_cli/test_config.py`、`test_config_validation.py`、`test_set_config_value.py`

`tests/hermes_cli/test_desktop_repo_discovery_config.py:8 @ 863e313`

```python
    assert desktop["repo_scan_enabled"] is True
```

`tests/hermes_cli/test_upstage_provider.py:67 @ 863e313`

```python
        assert OPTIONAL_ENV_VARS["UPSTAGE_API_KEY"]["category"] == "provider"
```

---

## 6. 可疑缺陷(只记录,不修)

**D1 —— 空 dict 默认值在 dashboard 配置页彻底隐形。**
`_build_schema_from_config` 对 dict 递归,空 dict 递归出零条目。受影响:
`model_catalog.providers`、`monitoring.export.otlp.headers_env`、`onboarding.seen`、
`lsp.servers`、`secrets.onepassword.env`。怎么踩到:用户想在 dashboard 里配
1Password 的 `env:` 映射或 OTLP header,找不到入口,只能编辑 YAML。
`hermes_cli/web_server.py:1099 @ 863e313`

```python
        if isinstance(value, dict):
```

**D2 —— `None` 默认值在 dashboard 里一律被推断成字符串输入框。**
`_infer_type` 没有 `None` 分支,fallthrough 到 `"string"`。受影响的语义类型:
int(`cron.max_parallel_jobs`、`kanban.max_in_progress_per_profile`)、
三态 bool(`computer_use.no_overlay`)、list(`proxy.upstream_deny_cidrs`)。
怎么踩到:在 dashboard 给 `max_parallel_jobs` 填 `4`,存进去是字符串 `"4"`;
`cron/scheduler.py:4242` 的 `int(_cfg_par)` 恰好能吃字符串所以不炸,但
`proxy.upstream_deny_cidrs` 填任何东西都会变成一个字符串,而消费方期待 list/None。
`hermes_cli/web_server.py:1074 @ 863e313`

```python
    return "string"
```

**D3 —— `or` 兜底链让"显式 0"无法表达。**
`logging.max_size_mb: 0` / `logging.backup_count: 0` 静默变 5 / 3;
`model_catalog.ttl_hours: 0`(想"每次重取")静默变默认 TTL。
`hermes_logging.py:313 @ 863e313`

```python
    backups = backup_count or cfg_backup or 3
```

`hermes_cli/model_catalog.py:110 @ 863e313`

```python
        "ttl_hours": float(raw.get("ttl_hours") or DEFAULT_TTL_HOURS),
```

对照写法:`gateway.max_inbound_media_bytes` 用 `"key" not in gw` 判定,`0` 能真的生效
(`gateway/platforms/base.py:742`)。同一仓库里两种写法并存。

**D4 —— 被代码读取却不在 `DEFAULT_CONFIG` 里的键(纯口传)。**
`model_catalog.excluded_providers`(两处读)、`gateway.proxy_url`(proxy mode 的主开关)。
后果:`hermes config check` 不提示、dashboard 无字段、`_KNOWN_ROOT_KEYS` 派生逻辑也覆盖不到
(它们是二级键,不影响 root 校验,但仍然是"文档黑洞")。
`hermes_cli/main.py:3300 @ 863e313`

```python
    # Honor ``model_catalog.excluded_providers`` so the CLI ``hermes model``
```

**D5 —— `monitoring.gateway_health_export.resource_attributes["service.name"]` 是死配置。**
它在允许名单里、会被 `_safe_resource_attributes` 收下,但紧接着被无条件硬覆盖成
`"hermes-gateway"`。用户改它没有任何效果,而默认值恰好等于硬编码值所以没人发现。
`agent/monitoring/gateway_health_export.py:82 @ 863e313`

```python
    attrs = _safe_resource_attributes(gh.get("resource_attributes"))
    from agent.monitoring.gateway_health import _safe_instance_id

    attrs["service.name"] = "hermes-gateway"
```

怎么踩到:多实例部署时想用不同 `service.name` 区分,改了没用;真正的区分维度是
`service.instance.id`(由 `install_id` 派生,也是被硬覆盖的)。

**D6 —— 带点号的配置键与点分路径 API 冲突。**
`resource_attributes` 的两个 key 本身含点号(`service.name`、`deployment.environment.name`)。
`hermes config set monitoring.gateway_health_export.resource_attributes.service.name X`
会被 `_set_nested` 按点号切开,写成嵌套 `{"service": {"name": "X"}}`,而读取端
`_safe_resource_attributes` 期待的是**平的、key 含点号的** dict,于是该值被
`key not in _RESOURCE_ATTRIBUTE_KEYS` 静默丢弃。
`hermes_cli/config.py:1014 @ 863e313`

```python
    parts = dotted_key.split(".")
```

`agent/monitoring/gateway_health_export.py:62 @ 863e313`

```python
        if key not in _RESOURCE_ATTRIBUTE_KEYS or value is None:
            continue
```

怎么踩到:照着 dashboard 显示的路径去 `hermes config set`,静默无效果、无报错。

**D7 —— 12 条 `OPTIONAL_ENV_VARS` 条目缺 `password` 字段。**
`HONCHO_BASE_URL`、`HINDSIGHT_API_URL`、`RETAINDB_BASE_URL`、`OPENVIKING_ENDPOINT`、
`BLUEBUBBLES_ALLOW_ALL_USERS`、`QQ_APP_ID`、`QQ_ALLOWED_USERS`、`QQ_GROUP_ALLOWED_USERS`、
`QQ_ALLOW_ALL_USERS`、`QQBOT_HOME_CHANNEL`、`QQBOT_HOME_CHANNEL_NAME`、`QQ_SANDBOX`
(我 exec 该模块后逐条扫描得到)。消费者一律 `info.get("password", False)`,
所以它们在 dashboard 上**不打码**。这 12 条恰好都不是密文,**当下无害**;
但风险在于"缺字段 = 非密"这个隐式契约没有任何校验兜着——将来往 QQ 那一族里加一条
`QQ_*_SECRET` 而忘了写 `password`,就会明文显示。
`hermes_cli/web_server.py:7057 @ 863e313`

```python
            "is_password": info.get("password", cat_meta.get("is_password", False)),
```

同族还有 15 条缺 `url`(含 `QQ_CLIENT_SECRET`),那个只影响"去哪申请"的链接,无安全影响。

**D8 —— Chronos "半配好"会静默失效。**
可用性判定只看 `portal_url` 与 `callback_url`,而 fire 端点在 `nas_jwks_url` 为空时
拒绝一切 token。于是"配了 callback_url、没配 JWKS"的实例会认为 Chronos 可用、
把任务武装过去,然后每一次 fire 都被自己的验签拒绝,一次都不执行。
`plugins/cron_providers/chronos/__init__.py:99 @ 863e313`

```python
        return str(_cfg("cron", "chronos", "callback_url") or "")
```

**D9 —— `override_existing` 的默认值分散在三个类里且基类与其余相反。**
基类 `False`、bitwarden `True`、onepassword `True`、`DEFAULT_CONFIG` 里两处都是 `True`。
怎么踩到:新写一个 secret source 子类若不覆写 `override_existing`,会继承 `False`,
与本仓库其他源的行为相反,而 `DEFAULT_CONFIG` 里若也忘了给它写默认,用户体验就分叉了。
(引用见 §2.18。)

**D10 —— 两个 env 注入器全吞异常。**
`_inject_profile_env_vars` / `_inject_platform_plugin_env_vars` 都是
`except Exception: pass`,一个坏 `plugin.yaml`、一个 import 失败的 provider 模块,
表现是"某个 key 就是不出现在 setup/dashboard 里",没有任何日志。
(引用见 §3.4。)

---

## 7. 文档 / 注释与代码的出入

**C1 —— `tools.tool_search` 注释指向一个不存在的文件。**
注释说 "See tools/tool_search.py for full design notes and the
openclaw-tool-search-report PDF in this PR for the rationale"。
基线仓库里没有这个 PDF(它是 PR 附件,不随代码入库)。
`hermes_cli/config_defaults.py:2337 @ 863e313`

```python
    # See tools/tool_search.py for full design notes and the
    # openclaw-tool-search-report PDF in this PR for the rationale.
```

**C2 —— `proxy` 块里 `fail_on_uncovered_providers` 的墓碑注释与
`allow_env_fallback` 的说明连成一片,读起来像同一条注释。**
3037-3042 是墓碑,3043-3049 描述的是紧随其后的 `allow_env_fallback`,中间没有空行。
不影响运行,但会让读者以为 `allow_env_fallback` 与被删的键有关。
`hermes_cli/config_defaults.py:3043 @ 863e313`

```python
        # When credential_source is bitwarden but the BWS access token /
```

**C3 —— `vertex` 块注释说两个键"bridged to the VERTEX_PROJECT_ID / VERTEX_REGION
env vars",但代码里没有任何桥接。**
adapter 是**分别读**:先读 env(`_get_secret`),再回落 config.yaml。
我全仓 grep `VERTEX_PROJECT_ID|VERTEX_REGION`,只有 `agent/vertex_adapter.py` 和
这条注释自身命中,没有 `os.environ[...] =` 的写入点。
最终**效果**(env 赢)与注释一致,但**机制**描述是错的——读代码的人会去找不存在的桥接代码。
`hermes_cli/config_defaults.py:3112 @ 863e313`

```python
    # settings are non-secret routing config and live here. Both are bridged to
```

`agent/vertex_adapter.py:70 @ 863e313`

```python
    env_region = (_get_secret("VERTEX_REGION") or "").strip()
```

**C4 —— `hermes_cli/tips.py` 说 `HERMES_CRON_MAX_PARALLEL` 默认 4,实际默认无限。**
`DEFAULT_CONFIG` 里 `cron.max_parallel_jobs = None`,scheduler 的兜底也是 unbounded。
`hermes_cli/tips.py:359 @ 863e313`

```python
    "HERMES_CRON_MAX_PARALLEL (default 4) caps how many cron jobs run per tick so bursts don't saturate your keys.",
```

`cron/scheduler.py:4250 @ 863e313`

```python
                _max_workers if _max_workers else "unbounded",
```

**C5 —— 两份"作者自绘地图"把 `OPTIONAL_ENV_VARS` 的位置写成了旧路径。**
它们说这张表在 `hermes_cli/config.py`,实际已经搬到 `hermes_cli/config_defaults.py`
(`config.py` 只是 re-export)。对新增平台/provider 的作者来说是错误的施工指引。
`gateway/platforms/ADDING_A_PLATFORM.md:41 @ 863e313`

```markdown
  auto-populate `OPTIONAL_ENV_VARS` in `hermes_cli/config.py` so the setup
```

`providers/README.md:42 @ 863e313`

```markdown
  `OPTIONAL_ENV_VARS` so the setup wizard knows about it.
```

(第二条只是没写路径,主要问题在第一条。)

**C6 —— `kanban.dispatch_stale_timeout_seconds` 的 watcher 兜底(0=关闭)与
`DEFAULT_CONFIG`(14400)相反。**
走 `load_config()` 时不会出问题,但注释/默认表读起来是"默认 4 小时",
而单看 watcher 代码读起来是"默认关闭"。(引用见 §2.3。)

---

## 8. 重实现要点(如果我从零写一个同级 harness)

1. **默认表必须是纯数据叶子模块,零 import。** 它会被早启动路径、沙箱擦洗、
   dashboard schema 生成器同时消费;任何 import 都会把重依赖拖进这些路径,
   或者制造循环依赖。Hermes 把这条写进了 docstring 并在基线上真的做到了。

2. **默认表不是"一张表",是"一个键的四重身份"。** 加一个键会同时:
   (a) 成为 read-time 深合并的默认值;(b) 进 root 白名单;(c) 进 `config check` 的新选项;
   (d) 生成一个 dashboard 字段。**设计时就要问"这四件事我都想要吗"**——
   `onboarding.seen` 这种内部闩锁其实只想要 (a),于是它靠"空 dict 不产生 schema"
   意外地达成了目的,但这是巧合不是机制。真要做,应该有显式的 `internal: true` 标记。

3. **"缺键即默认"比"迁移时把默认写进磁盘"好。** Hermes 明确不 materialize 新默认键
   (`config.py:2356`),于是**改默认值对没显式设过的用户立刻生效**。
   代价是无法区分"用户显式设成了默认值"与"用户没设",所以 `save_config` 需要
   `strip_defaults` + "raw config 里存在该路径"的判据来还原这个区分。这一对必须成套设计。

4. **默认值的类型要能被 schema 推断器区分,别用 `None` 表达"未设"。**
   `None` 会退化成字符串输入框(D2),而且和"三态 bool""可选 list"混在一起无法区分。
   要么给每个键显式的类型元数据,要么用 sentinel 而不是 `None`。
   同理:**别用 `or` 做兜底**,用 `key in cfg` 或 `is None` 判定,否则 `0` / `""` / `[]`
   这些合法值永远无法表达(D3)。

5. **"运行时认识的 env 键"与"向用户推荐的 env 键"必须是两张表。**
   这是本段最干净的一条设计。废弃的键从推荐表摘除、在认识表保留:
   老配置继续工作,新用户不会被引导去设一个废弃旋钮。
   同时,`reload_env` 只删"认识的"键,才不会误伤用户 shell 里的无关环境。

6. **env 元数据表里的一个字段(category)同时是 UI 分类和安全边界,要写进契约。**
   Hermes 用 `category ∈ {tool, messaging}` 直接派生沙箱擦洗名单,并专门造了
   `skill` 这一档来表达"这条要透传"。这个耦合很省事,但意味着**改一条 category
   就是改一次安全策略**。重实现时要么把这两件事拆成两个字段,要么在测试里
   钉死"每条 secret 都必须被 blocklist 覆盖"这个不变式(Hermes 有
   `tests/tools/test_local_env_blocklist.py`,方向是对的)。

7. **config 里存"变量名"而不是"值",让配置文件永远可分享。**
   `headers_env`、`access_token_env`、`service_account_token_env` 三处一致地用了这招。
   这条应该上升为 harness 的硬规则:**config.yaml 里只能有指针,密文只在 .env / 环境 /
   外部 manager**;并且 `.env` 里的键必须来自一张已知表,才能做 reload 的删除语义。

8. **config→env 的桥接要显式声明方向,并把方向写进注释。**
   Hermes 有两类:config 权威(媒体投递、CJK 索引)与 env 逃生口(平台连接超时、
   respawn 熔断、cron 并行度)。混淆过一次就会出"config 写 500 实际 60"那种事故
   (`gateway/run.py:2270` 的注释就是那次事故的墓志铭)。桥接整体不能静默吞异常。

9. **带点号的 key 不要放进点分路径可达的位置。**
   OTel 语义约定的属性名天然带点(`service.name`),塞进一个用 `.` 做路径分隔的
   配置树里,`config set` 就再也写不进去(D6)。要么把它们放进一个明确的
   "opaque map" 节点并禁止点分路径下钻,要么在 key 里做转义。
