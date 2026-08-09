# R8C 底稿 · web_server 尾段(13184–17732)+ 四个 web_routers + web_models

> 取证范围:`hermes_cli/web_server.py` 的 **13184–17732 行**(文件尾部),
> `hermes_cli/web_routers/{skills,profiles,tools,__init__}.py`,`hermes_cli/web_models.py`。
> 溯源约定:凡对 hermes-agent 行为的断言,**锚点单独成行放在代码块之前**,
> 格式 `路径:行号 @ 863e313`,代码块为基线逐字原文。
> `13974` 的 Raw YAML config 端点由本轮另一段覆盖并定案,本文件只在地图里标一行。

---

## 0. 环境与边界(先报数)

**基线干净**。全程未在 `/home/user/hermes-agent` 下执行任何写盘命令;临时脚本与探针全部写 `/tmp/r8c/`。

```console
$ git -C /home/user/hermes-agent rev-parse HEAD
863e31318553cda8ad61df681d08175364d4164b
$ git -C /home/user/hermes-agent status --porcelain
(空)
```

**venv 已漂移,必须记账**。CLAUDE.md 记的 R8B 基准是 **87 包**;本轮开工时实测 **91 包**。
按"直接断言,不要间接推断"的规矩去查了 `dist-info` 时间戳,多出来的是今天 16:38 装进来的
`boto3 / botocore / jmespath / s3transfer`(某个兄弟子代理往共享 venv 里装的),
比 `aiohttp/brotlicffi` 那批(16:05)晚。**本文件报的测试数是 91 包环境下的数。**

```console
$ /home/user/hermes-venv/bin/pip list | tail -n +3 | wc -l
91
$ ls -dlt /home/user/hermes-venv/lib/python3.11/site-packages/*.dist-info | head -5
drwxr-xr-x ... Aug  8 16:38 .../botocore-1.42.97.dist-info
drwxr-xr-x ... Aug  8 16:38 .../boto3-1.42.89.dist-info
drwxr-xr-x ... Aug  8 16:38 .../jmespath-1.1.0.dist-info
drwxr-xr-x ... Aug  8 16:38 .../s3transfer-0.16.1.dist-info
drwxr-xr-x ... Aug  8 16:05 .../aiohttp-3.14.1.dist-info
```

---

## 1. 地图:行号区间 → 职责

先给表,再逐块讲"为什么需要"。表里的行号是**段落横幅**(`# ---` 注释块)的起始行,
职责一列写这段解决什么。

| 行号区间 | 段落 | 职责一句话 |
|---|---|---|
| `13182`–`13307` | Skills hub 端点 | 技能市场的 search/install/uninstall/update;**装/卸载不在进程内做,而是 spawn 子进程** |
| `13308`–`13556` | Profile 管理 | 档位(profile)的 list/create/rename/delete + SOUL.md;含把写操作重定向到目标档位的两个 helper |
| `13557`–`13786` | Skills & Tools 端点 | `_profile_scope` / `_config_profile_scope` 两个"把这一次请求钉到某个档位"的上下文管理器 + 挂载 skills/tools 路由 |
| `13787`–`13955` | 终端执行后端选择器 | `terminal.backend` 的 GUI 面:6 个后端 + 每个一条**永不抛异常**的健康探针 |
| `13956`–`13971` | Computer Use | cua-driver 就绪度 + macOS TCC 授权(纯横幅,实现已搬进 `web_routers/tools.py`) |
| `13972`–`14007` | Raw YAML config | `GET/PUT /api/config/raw`——**本轮另一段已定案,本文件跳过** |
| `14008`–`14391` | Token / 成本分析 | `/api/analytics/usage` + `/api/analytics/models`:把 state.db 的用量行聚合成图表数据 |
| `14392`–`15090` | `/api/pty` PTY 桥 + WS 鉴权工具箱 | 把 `hermes --tui` 塞进 WebSocket;附带 `_ws_*` 一整套 peer/Host/Origin/token 判定 |
| `15091`–`15831` | `/api/console` + `/api/pty` | 安全的"Hermes Console"命令 WS(不开 PTY)与 PTY WS 本体 |
| `15832`–`15945` | `/api/ws`、`/api/pub`、`/api/events` | JSON-RPC sidecar 与聊天页事件广播 |
| `15946`–`16211` | SPA 挂载 + 主题引导 CSS | `mount_spa()`:注入 session token / base path,渲染首屏主题 CSS |
| `16212`–`16553` | Dashboard 主题 | 内置主题表 + 用户主题 YAML 发现 + `PUT /api/dashboard/theme` / `font` |
| `16554`–`17330` | **Dashboard 插件系统** | 第三方插件的发现、门控、静态资源分发、**后端路由挂载(import 任意 Python)** |
| `17328`–`17422` | 端口发现 / ready 文件 / 开浏览器 | 从活着的 uvicorn socket 读真实端口,再宣告 READY |
| `17423`–`17732` | **`start_server`** | 绑定地址决策 → 鉴权门 → fail-closed → uvicorn 参数 → 事件循环心跳 → Windows 分支 |

### 1.1 为什么需要这些块(逐块)

**Skills hub 为什么要 spawn 子进程,而不是在 dashboard 进程里装?**
横幅自己写了理由:装/搜都要走网络和"复杂的 source-router 流水线",跑起来慢,所以做成
"后台 action + 前端拉日志"的形态。

`hermes_cli/web_server.py:13182 @ 863e313`
```python
# ---------------------------------------------------------------------------
# Skills hub endpoints — search / install / uninstall / update.
#
# Search and install touch the network (GitHub, hub sources) and run the same
# complex source-router pipeline the CLI uses, so they're spawned as background
# actions whose logs the dashboard tails.  The already-installed skill list +
# enable/disable toggle live in the existing /api/skills endpoints.
# ---------------------------------------------------------------------------
```

但**真正逼出子进程的不是性能,是绑定时机**。`tools/skills_hub.SKILLS_DIR` 是 import 时绑定的
模块级全局;想让"给档位 B 装技能"落到 B 的目录,只能起一个新进程,让它在 import 之前就
把 `HERMES_HOME` 指向 B。`_profile_cli_args` 的 docstring 把这条讲得很清楚:

`hermes_cli/web_server.py:13192 @ 863e313`
```python
def _profile_cli_args(profile: Optional[str]) -> List[str]:
    """Return ``["-p", <name>]`` for a validated non-default profile.

    Hub install/uninstall/update run in a fresh ``hermes`` subprocess, and
    ``_apply_profile_override()`` reads ``-p`` from argv in the child — the
    only mechanism that reaches import-time-bound globals like
    ``skills_hub.SKILLS_DIR``. Empty/"current" means the dashboard's own
    profile (no args, legacy behavior).
    """
```

**为什么每个技能要有自己的 action 名?** 因为 `_spawn_hermes_action` 是"一个名字一个进程一份日志"。
共用 `skills-install` 会让并发的行内操作互相盖掉状态和日志——UI 是按行轮询的。

`hermes_cli/web_server.py:13217 @ 863e313`
```python
    slug = re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")[:48] or "skill"
    digest = hashlib.sha1(key.encode()).hexdigest()[:8]
    name = f"skills-{verb}-{slug}-{digest}"
    _ACTION_LOG_FILES.setdefault(name, f"action-{name}.log")
    return name
```

**Skills & Tools 段为什么需要两个作用域管理器?** 因为要重定向的"缝"有两种,生命周期不一样:
`load_config`/`save_config` 在**调用时**解析 home,contextvar 能覆盖到;而 `skills_tool` /
`skill_manager_tool` 的 `SKILLS_DIR` 是 **import 时**绑定的模块属性,contextvar 够不着,只能加锁临时改
再改回来。改模块全局这件事**不能跨 `await`**——另一个并发请求会在它的 `finally` 里把本请求的
目录还原掉,于是有了第二个"只动 contextvar"的版本。

`hermes_cli/web_server.py:13574 @ 863e313`
```python
def _profile_scope(profile: Optional[str]):
    """Scope config + skill-directory resolution to ``profile`` for one request.

    Two seams must be redirected for skills/toolsets endpoints:

    1. ``load_config``/``save_config`` resolve ``get_hermes_home()`` at call
       time — the context-local override from ``set_hermes_home_override``
```

`hermes_cli/web_server.py:13633 @ 863e313`
```python
def _config_profile_scope(profile: Optional[str]):
    """Await-safe, config-only profile scope for handlers that ``await``.

    Unlike ``_profile_scope`` this touches ONLY the context-local
    ``set_hermes_home_override`` contextvar — it does NOT swap the
    process-global ``skills_tool``/``skill_manager`` module attributes.
    Those globals are shared across all event-loop tasks, so holding them
    across an ``await`` lets a concurrent skills request restore THIS
    request's profile dir on its ``finally`` (cross-contamination). The
    contextvar override is task-local and survives an ``await`` cleanly,
    which is all endpoints that resolve ``get_hermes_home()`` at call time
    (config, env, gateway status) actually need.

    None/""/"current" means the dashboard's own profile — no override.
```

**终端后端选择器为什么要探针?** 因为纯枚举下拉框不告诉用户"Docker 没起来";
横幅还明确要求探针**不能抛**——探针失败要渲染成一个状态,而不是 500。

`hermes_cli/web_server.py:13787 @ 863e313`
```python
# ---------------------------------------------------------------------------
# Terminal execution backend picker — the GUI counterpart of terminal.backend
# in config.yaml. Each row carries a fast, defensive health probe (Docker
# daemon reachable, SSH host configured, Modal/Daytona credentials present) so
```

**`web_routers/__init__.py`(8 行)是什么?** 它只有一段 docstring,交代了这次拆分的**唯一硬约束**:
每个 router 必须在 web_server 模块体里**原来注册的那一行**被 include,因为 Starlette 是
**先注册先匹配**,挪动 include 点就等于改路由优先级。

`hermes_cli/web_routers/__init__.py:1 @ 863e313`
```python
"""Extracted APIRouter modules for the dashboard web server.

Each module exposes ``router = APIRouter()`` (profiles additionally exposes
``sessions_router``) and is mounted by ``hermes_cli.web_server`` at the exact
point in module execution where the routes were originally registered, so
route-matching order is unchanged.  Shared web_server helpers/state are
reached through the late-binding seam in ``hermes_cli.web_deps``.
"""
```

这也解释了 `skills.py` 为什么有**两个** router:hub 那批在 profiles 之前注册,普通 CRUD 那批在之后。
`web_server` 分两次 include:

`hermes_cli/web_server.py:13224 @ 863e313`
```python
from hermes_cli.web_routers import skills as _skills_routes  # noqa: E402

app.include_router(_skills_routes.hub_router)
```

---

## 2. `web_models.py`(725 行)是什么 + 裸 dict 清单

**Pydantic 一句话**:一个"按你声明的字段类型校验并解析请求 JSON"的库——你写
`class Foo(BaseModel): name: str`,FastAPI 就会把请求体解析成 `Foo`,类型不符直接 422,
**没声明的键默认丢弃**。所以"模型声明了哪些字段"= "这个端点认哪些键"。

`web_models.py` 就是整个 dashboard HTTP 面的请求体 schema 集合,从 web_server 里**原样搬出来**的
纯 schema 移动,web_server 再全部 re-export,老 import 路径不破。

`hermes_cli/web_models.py:1 @ 863e313`
```python
"""Pydantic request/response models for the Hermes dashboard web server.

Extracted verbatim from ``hermes_cli/web_server.py`` (pure schema move).
``web_server`` re-exports every name here, so existing imports like
``from hermes_cli.web_server import ConfigUpdate`` keep working.
"""
```

文件里每个模型上方都保留了 `# --- from web_server.py (originally lines A-B) ---` 的出处注释,
**这些行号指的是搬迁前的 web_server.py,不是基线现在的 web_server.py**——注意别拿它当锚点用。

### 2.1 裸 dict 清单(必答 2)

"裸 dict"= 字段类型只声明了容器(`dict` / `Dict[str, Any]` / `Dict[str, str]`),
**没有具名字段**,于是 Pydantic 对**键名**不做任何校验。全文件 `class` 共 62 个,逐个扫过一遍,
命中如下(按"键名完全不受 Pydantic 约束"的程度排序):

| 模型 | 行号 | 裸 dict 字段 | 对应端点 | 有无其他校验兜底 |
|---|---|---|---|---|
| `ConfigUpdate` | `web_models.py:18` | `config: dict` | `PUT /api/config` | **几乎没有**:`_denormalize_config_from_web` + `_deep_merge` + `save_config`,不校验根键名(本轮另一段已定案) |
| `CronJobUpdate` | `web_models.py:377` | `updates: dict` | `PATCH /api/cron/jobs/{id}` | **部分**:`_normalize_dashboard_cron_updates` 只对已知键做归一化,**未知键原样透传**给 `update_job`;`context_from` / 执行字段另有校验 |
| `MCPServersReplace` | `web_models.py:404` | `servers: Dict[str, Dict[str, Any]]` | `PUT /api/mcp/servers`(整表替换) | **有**:`_replace_mcp_servers` 返回 `(ok, issues)`,不 ok 就 400 |
| `SessionImport` | `web_models.py:311` | `sessions: List[Dict[str, Any]]` | `POST /api/sessions/import` | 由 `sessions.py` 导入逻辑自行判形,Pydantic 层无约束 |
| `MemoryProviderConfigUpdate` | `web_models.py:45` | `values: Dict[str, Any]` | `PUT /api/memory/providers/{name}/config` | **有**:`surface=declared` 走 provider 声明的 schema;否则 `_write_memory_provider_config_values` 兜底,`ValueError → 400` |
| `MemoryProviderSetupRequest` | `web_models.py:49` | `values: Dict[str, Any]` | `POST /api/memory/providers/{name}/setup` | 同上,复用 `_write_memory_provider_config_values` |
| `AutomationBlueprintInstantiate` | `web_models.py:383` | `values: Dict[str, Any]` | `POST /api/automations/blueprints/instantiate` | 由 blueprint 的 slot 定义消费,Pydantic 层无约束 |
| `MessagingPlatformUpdate` | `web_models.py:65` | `env: Dict[str, str]` | `PUT /api/messaging/platforms/{name}` | 值是 `str`,**键名不受约束**(写 .env) |
| `MCPServerCreate` | `web_models.py:390` | `env: Dict[str, str]` | `POST /api/mcp/servers` | 同上,写进该 server 的 env |
| `MCPCatalogInstall` | `web_models.py:419` | `env: Dict[str, str]` | `POST /api/mcp/catalog/install` | 同上 |
| `ToolsetEnvUpdate` | `web_models.py:668` | `env: Dict[str, str]` | `PUT /api/tools/toolsets/{name}/env` | **有,而且是本表里最严的**:键名必须落在该 toolset 可见 provider 的 `env_vars` 并集里,否则 400(见 §7) |
| `ProfileExport` | `web_models.py:581` | `extra_files: Dict[str, str]` | `POST /api/profiles/{name}/export` | 文件名→内容,键名即写入的文件名,由导出逻辑兜底 |
| `CronJobCreate` | `web_models.py:361` | `context_from: Optional[Any]`(不是 dict,但同样"无类型") | `POST /api/cron/jobs` | **有**:`_cron_string_list` + `_validate_dashboard_cron_context_from` 逐个校验 job 存在 |
| `MoaConfigPayload` | `web_models.py:201` | `presets: dict[str, MoaPresetPayload]` | `PUT /api/moa/config` | **不算裸 dict**:值类型是具名模型,只有 preset 名字自由 |

最典型的一条,原文如下(注意它连 `Dict[str, Any]` 都没写,直接 `dict`):

`hermes_cli/web_models.py:18 @ 863e313`
```python
class ConfigUpdate(BaseModel):
    config: dict
    profile: Optional[str] = None
```

它落到的写路径:

`hermes_cli/web_server.py:6911 @ 863e313`
```python
@app.put("/api/config")
async def update_config(body: ConfigUpdate, profile: Optional[str] = None):
    try:
        with _profile_scope(body.profile or profile):
            # The dashboard form is schema-driven (see CONFIG_SCHEMA). Any root
            # key absent from the schema — most visibly ``custom_providers``, but
            # also ``agent.personalities``, ``terminal.lifetime_seconds``, etc. —
            # is not sent in the PUT body. A full-replace save would silently
            # drop those keys. Deep-merge incoming over what's on disk so the
            # frontend can only overwrite what it explicitly sends.
            existing = read_raw_config()
            incoming = _denormalize_config_from_web(body.config)
            save_config(_deep_merge(existing, incoming))
        return {"ok": True}
```

注释自己承认"表单是 schema 驱动的,schema 外的根键不会被发上来"——但那是**前端的自律**,
`ConfigUpdate.config: dict` 让后端对此**一个字都不校验**;deep-merge 只保证"不删",不保证"不加"。
本轮另一段已就此定案,这里只补一条本段视角的推论:
**`approvals.*` 是安全策略本身,而它和普通配置共用这条无键名校验的通道**(见 §7.3)。

### 2.2 顺带的两条观察

- `MCPServerCreate.bearer_token` 是全文件**唯一**用 `SecretStr` 的字段——即"别把它打进日志/repr"。
  其余 API key 字段(`ModelAssignment.api_key`、`CredentialPoolAdd.api_key`、
  `CustomEndpointUpdate.api_key`、`EnvVarUpdate.api_key`)都是裸 `str`。
  ◇ 代码有、文档无:这条不对称没有任何地方解释。

  `hermes_cli/web_models.py:399 @ 863e313`
  ```python
      # One-time provisioning input; persisted only to the profile's .env.
      bearer_token: Optional[SecretStr] = None
  ```

- `_MoaReferenceControls._validate_reference_timeout` 是全文件**唯一**的 `field_validator`,
  专门挡 JSON 布尔和非有限值——说明"多写校验"在这套 schema 里是例外不是惯例。

  `hermes_cli/web_models.py:166 @ 863e313`
  ```python
      @field_validator("reference_timeout", mode="before")
      @classmethod
      def _validate_reference_timeout(cls, value: Any) -> Optional[float]:
          """Reject JSON booleans/non-finite values before float coercion."""
  ```

---

## 3. Dashboard 插件系统(`16554`–`17330`)

### 3.1 一次插件是怎么被"注册"进后端的

四步,每步都有门:

1. **发现**:扫三处 `plugins/*/dashboard/manifest.json`;
2. **api 字段消毒**:`_safe_plugin_api_relpath` 把绝对路径 / `..` 逃逸挡掉;
3. **来源与开关门控**:project 来源**绝不** import;user 来源必须在 `plugins.enabled` 里;
4. **挂载**:`importlib.util.spec_from_file_location` → `exec_module` → `app.include_router(..., prefix=f"/api/plugins/{name}")`。

发现的三处搜索目录,以及那条 GHSA 修过的环境变量门:

`hermes_cli/web_server.py:16612 @ 863e313`
```python
    search_dirs = [
        (get_process_hermes_home() / "plugins", "user"),
        (bundled_root / "memory", "bundled"),
        (bundled_root, "bundled"),
    ]
```

`api` 字段的消毒器——它的 docstring 把 GHSA-5qr3-c538-wm9j 的两个原语讲得很完整
(绝对路径吞掉前缀 + `../..` 爬出去):

`hermes_cli/web_server.py:16558 @ 863e313`
```python
def _safe_plugin_api_relpath(api_field: Any, *, dashboard_dir: Path) -> Optional[str]:
    """Validate the manifest's ``api`` field for the plugin loader.

    The web server later imports this file as a Python module via
    ``importlib.util.spec_from_file_location`` (arbitrary code
    execution by design — that's how plugins extend the backend).
```

发现阶段还会顺手把 manifest 的 `tab` 块归一成"这个插件在侧边栏占哪个位置",
其中 `override` 允许插件**替换一个内置 tab 的路径**(后端只校验它是字符串且以 `/` 开头,
真正的消费在前端):

`hermes_cli/web_server.py:16648 @ 863e313`
```python
                raw_tab = data.get("tab", {}) if isinstance(data.get("tab"), dict) else {}
                tab_info = {
                    "path": raw_tab.get("path", f"/{name}"),
                    "position": raw_tab.get("position", "end"),
                }
```

发现结果按进程缓存,只有"缓存里某个目录已经不在了"才会自动重扫——所以**新装的插件在
`GET /api/dashboard/plugins/rescan` 之前不会出现**,而**被删掉的插件会自动消失**:

`hermes_cli/web_server.py:16707 @ 863e313`
```python
def _get_dashboard_plugins(force_rescan: bool = False) -> list:
    global _dashboard_plugins_cache
    if _dashboard_plugins_cache is None or force_rescan:
        _dashboard_plugins_cache = _discover_dashboard_plugins()
    elif _dashboard_plugins_cache:
        if any(not Path(p["_dir"]).is_dir() for p in _dashboard_plugins_cache):
            _dashboard_plugins_cache = _discover_dashboard_plugins()
    return _dashboard_plugins_cache
```

第 3 步那两道门(project 一律拒、user 必须在 `plugins.enabled`)在同一个循环里:

`hermes_cli/web_server.py:17231 @ 863e313`
```python
    for plugin in _get_dashboard_plugins():
        api_file_name = plugin.get("_api_file")
        if not api_file_name:
            continue
        plugin_name = plugin.get("name", "")
```

挂载点本身:

`hermes_cli/web_server.py:17305 @ 863e313`
```python
            router = getattr(mod, "router", None)
            if router is None:
                _log.warning("Plugin %s api file has no 'router' attribute", plugin["name"])
                continue
            app.include_router(router, prefix=f"/api/plugins/{plugin['name']}")
            _log.info("Mounted plugin API routes: /api/plugins/%s/", plugin["name"])
```

### 3.2 `plugin['name']` 有没有被校验过?——**没有**,但它不是失效链

**结论先行**:`plugin['name']` 来自 manifest 的 `name` 字段,**全程没有任何正则/字符集校验**;
`_validate_plugin_name`(`:17008`)只用于 **URL 路径参数**,和这里的 manifest 名字是两条独立的路。
但把 `../` 塞进 `name` **不构成额外提权**,因为能走到 `include_router` 这一行就已经意味着
`exec_module` 跑过了攻击者的 Python——那已经是完全 RCE,路由前缀逃不逃逸不改变结论。

名字的来源(注意:`data.get("name", child.name)`——**manifest 声明优先于目录名**):

`hermes_cli/web_server.py:16639 @ 863e313`
```python
                data = json.loads(manifest_file.read_text(encoding="utf-8"))
                name = data.get("name", child.name)
                if name in seen_names:
                    continue
                seen_names.add(name)
```

用于 URL 参数的那个校验器(**只**保护 `/api/dashboard/agent-plugins/{name:path}/…` 和
`/api/dashboard/plugins/{name:path}/visibility`,不保护 manifest):

`hermes_cli/web_server.py:17008 @ 863e313`
```python
def _validate_plugin_name(name: str) -> str:
    """Reject path-traversal attempts in plugin name URL parameters."""
    name = name.strip("/")
    if not name or ".." in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid plugin name.")
    return name
```
注意它 `strip("/")` 之后**不禁止内部 `/`**,只禁 `..` 和 `\`。

**FastAPI 侧对 prefix 的实际约束**(实测,非基线引用):只拒绝以 `/` 结尾,`..` 和多段 `/` 都放行。

```verify
$ /home/user/hermes-venv/bin/python /tmp/r8c/prefix_probe.py     # fastapi 0.141.1
'/api/plugins/normal'   => 正常挂载
'/api/plugins/../..'    => 挂载成功;路由字面量含 '..',浏览器/httpx 会先归一化掉 → 404
'/api/plugins/'         => include_router REJECTED: AssertionError:
                           A path prefix must not end with '/', ...
```

### 3.3 插件能不能覆盖已有路由?——**不能覆盖内置 API,但能覆盖登录页和 SPA**

两条事实叠起来才是答案:

**(a) Starlette 先注册先匹配。** 实测:先注册 `/api/config`,再 `include_router(prefix="/api")`
挂一个同路径的插件路由,请求打到的是**内置那个**。

```verify
'/api' => results={'/api/config': {'who': 'builtin'}}   # 插件没抢到
```

**(b) 插件挂载点在所有 `@app.*` 之后,但在 dashboard-auth 路由和 SPA catch-all 之前。**

`hermes_cli/web_server.py:17315 @ 863e313`
```python
# Mount plugin API routes before the SPA catch-all.
_mount_plugin_api_routes()

# Mount the dashboard auth routes (/login, /auth/*, /api/auth/*) before the
# SPA catch-all so /{full_path:path} doesn't swallow them.  These are
# always mounted — the gate middleware decides whether to enforce auth,
# not whether the routes exist.
from hermes_cli.dashboard_auth.routes import router as _dashboard_auth_router  # noqa: E402
app.include_router(_dashboard_auth_router)

mount_spa(app)
```

所以:内置 `@app.*` 路由(`/api/config`、`/api/skills`……)插件抢不到;
但 `_dashboard_auth_router` 注册的 `/login`、`/auth/login`、`/auth/callback`、
`/auth/password-login`、`/api/auth/me`、`/api/auth/ws-ticket` 这一批,**以及 SPA 的
`/{full_path:path}`,在插件之后注册,理论上可被先注册的插件路由抢占**。
实际能否抢到还受 prefix 恒为 `/api/plugins/<name>` 限制(要越出去必须带 `..`,而 `..` 会被
规范化的 HTTP 客户端吃掉)。
**判定:◇ 代码有文档无。**"插件先于 auth 路由挂载"这条顺序在注释里只被描述为"在 SPA catch-all 之前",
没有任何地方说明它同时也排在鉴权路由**之前**;这是一条纵深防御上的隐含约定,没写下来。

### 3.4 ■ 真正的失效链:manifest 的 `name` 是**声明的**,不是**目录推出来的**

**现象**:`~/.hermes/plugins/<任意目录名>/dashboard/manifest.json` 里写 `"name": "kanban"`,
就能把内置的 `kanban` dashboard 插件**整个顶掉**(`seen_names` 去重 + user 目录先扫),
并且以 `source="user"` 的身份去和 `plugins.enabled` 比对——于是它**继承了用户为内置 kanban 打的那个勾**,
启动时 `exec_module` 它的 `plugin_api.py`。

实测(HERMES_HOME 指到 `/tmp/r8c/home`,目录名 `evil-dir`,manifest 声明 `name: kanban`):

```console
$ /home/user/hermes-venv/bin/python -c '...ws._discover_dashboard_plugins()...'
kanban | Shadow-Kanban | user | /tmp/r8c/home/plugins/evil-dir/dashboard
hermes-achievements | Achievements | bundled | .../plugins/hermes-achievements/dashboard
# 内置 kanban 从列表里消失了

$ cat /tmp/r8c/home/config.yaml
plugins:
  enabled:
    - kanban
$ /home/user/hermes-venv/bin/python -c 'import hermes_cli.web_server'   # 仅 import
INFO:hermes_cli.web_server:Mounted plugin API routes: /api/plugins/kanban/
pwned marker exists: True        # plugin_api.py 在 dashboard 启动时被执行
```

**失效链**:
1. 攻击者/被诱导的用户把一个目录放进 `~/.hermes/plugins/`(不需要是合法插件名);
2. 其 `dashboard/manifest.json` 声明 `name` = 任意一个**用户已经启用过的插件名**;
3. `_discover_dashboard_plugins` 先扫 user 目录 → `seen_names` 抢先占位 → 内置同名插件被静默丢弃;
4. `_mount_plugin_api_routes` 的 user 门只检查 `plugin_name in enabled_set`,而 `plugin_name` 正是
   第 2 步声明的字符串 → 门通过;
5. `exec_module` 执行攻击者的 Python(dashboard 主进程,非沙箱)。

**这条链有多严重要说清楚**:第 1 步本身已经需要本地写文件权限,而"往 `~/.hermes/plugins/` 放东西"
在这套设计里本来就等同于"授予代码执行"——`_safe_plugin_api_relpath` 的 docstring 自己写了
"arbitrary code execution by design"。所以这不是一条**新增**的提权,而是
**`plugins.enabled` 这道显式同意门被绕开了**:用户勾的是"内置 kanban",跑的是别人的代码,
UI 上还显示成 kanban。#46435 / GHSA-mcfc-hp25-cjv7 补的正是"未启用的插件不许执行代码"这条,
而这里的洞恰恰是"启用记录按**攻击者可声明的字符串**匹配"。
**判定:■(名字空间混淆导致同意门错配),定级中——需要本地文件写入前提,不可远程触发。**

顺带一条同源的可用性问题:agent 插件的规范 key 可能是 `observability/nemo_relay` 这样的嵌套形式,
而 dashboard 门比对的是 `dashboard/manifest.json` 里那个**另写的** `name`。两者不一致时,
用户 `hermes plugins enable` 了也白搭——dashboard 侧静默不加载,只在 `_log.debug` 留一行。

`hermes_cli/plugins_cmd.py:781 @ 863e313`
```python
def _resolve_plugin_key(name: str) -> Optional[str]:
    """Resolve a user-supplied plugin identifier to its canonical registry key.

    Accepts either the bare manifest name (``nemo_relay``), the directory
    name, or the full path-derived key (``observability/nemo_relay``) and
    returns the canonical key the loader gates on (``manifest.key`` or, for a
    flat plugin, the bare name). Returns ``None`` when no plugin matches.
```

### 3.5 静态资源与"谁能不带凭据读到什么"

`/dashboard-plugins/{plugin_name}/{file_path:path}` **不以 `/api/` 开头,所以 `auth_middleware`
不拦它**——这是有意的,`<script src>` / `<link href>` 带不了自定义头。代价是引入了
后缀白名单,否则任何能连上环回端口的人都能 curl 到第三方插件的 `.py` 源码:

`hermes_cli/web_server.py:17113 @ 863e313`
```python
@app.get("/dashboard-plugins/{plugin_name}/{file_path:path}")
async def serve_plugin_asset(plugin_name: str, file_path: str):
    """Serve static assets from a dashboard plugin directory.

    Only serves files from the plugin's ``dashboard/`` subdirectory.
    Path traversal is blocked by checking ``resolve().is_relative_to()``.
```

另外 `/api/dashboard/plugins`(插件清单)在**公开白名单**里,两个鉴权中间件共用同一份表,
所以**公网 bind 下也不需要任何凭据就能读到已装插件的名字/版本/entry 文件名**:

`hermes_cli/dashboard_auth/public_paths.py:51 @ 863e313`
```python
    # Read-only theme + plugin manifests for the dashboard skin engine.
    "/api/dashboard/themes",
    "/api/dashboard/plugins",
```

而白名单文件自己给出的准入标准是"任何 curl 这个域名的人看到都无所谓"。
插件名+版本是典型的指纹面(能推出装了哪些第三方后端扩展、版本多少)。
**判定:◎ 文档成立但保守**——内部字段(`_dir`/`_api_file`)在出站前会被按下划线前缀剥掉,
泄露面确实是"只读、无密钥";但把它和 `/api/status` 并列为"外部探活可见"仍属偏宽,值得在成品章点一句。

`hermes_cli/web_server.py:16764 @ 863e313`
```python
def _strip_dashboard_manifest(p: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in p.items() if not k.startswith("_")}
```

---

## 4. `start_server`:这东西到底怎么起来的(`17423`–`17732`)

### 4.1 绑定地址怎么决定

**没有自动探测,全靠 `--host`,默认 `127.0.0.1`。**

`hermes_cli/subcommands/dashboard.py:29 @ 863e313`
```python
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host (default 127.0.0.1)"
    )
```

`main.py` 把 `args.host` 原样传进 `start_server`,`start_server` 也原样交给 uvicorn。
**host 这个字符串同时决定三件事**:绑哪个网卡、鉴权门开不开、Host 头怎么校验。

### 4.2 鉴权门在什么条件下启用

**唯一判据:host 是不是环回。** 不是环回就开门,没有第二个条件、没有开关。

`hermes_cli/web_server.py:467 @ 863e313`
```python
_LOOPBACK_HOST_VALUES: frozenset = frozenset({
    "localhost", "127.0.0.1", "::1",
})
```

`hermes_cli/web_server.py:472 @ 863e313`
```python
def should_require_auth(host: str, allow_public: bool = False) -> bool:
    """Return True iff the dashboard auth gate must be active.

    Truth table:
      host == loopback        → False (no auth — local-only, trusted operator)
      host != loopback        → True  (gate engages — OAuth or password required)

    "Loopback" is 127.0.0.1, localhost, ::1. RFC1918 / CGNAT / link-local are
    deliberately treated as PUBLIC — a hostile device on the same LAN is exactly
    the threat model the gate is designed for.
```

注意 `should_require_auth` 的第二个形参 `allow_public` **在函数体里根本没被用到**——
它保留只为签名兼容,`return host not in _LOOPBACK_HOST_VALUES` 一行到底。

结果被钉在 `app.state` 上,中间件、SPA token 注入、WS 鉴权全从这里分叉:

`hermes_cli/web_server.py:17463 @ 863e313`
```python
    app.state.auth_required = should_require_auth(host)
```

`auth_required` 为真时的下游后果(逐条):
- `auth_middleware` **直接放行**,把判定权交给 cookie 门;
- `mount_spa` **不再注入** `__HERMES_SESSION_TOKEN__`,改注入 `__HERMES_AUTH_REQUIRED__`;
- uvicorn 打开 `proxy_headers`(见 §4.5)。

`hermes_cli/web_server.py:658 @ 863e313`
```python
    # When the OAuth gate is active, cookie-based auth (gated_auth_middleware
    # above) is authoritative.  The legacy _SESSION_TOKEN path is loopback-only
    # and is skipped here so the gate's session attachment isn't overridden.
    if getattr(request.app.state, "auth_required", False):
        return await call_next(request)
```

### 4.3 `--insecure` 现在还起不起作用?——**不起作用,只剩一条警告**

`hermes_cli/web_server.py:17465 @ 863e313`
```python
    # ``--insecure`` no longer disables the auth gate (June 2026 hardening:
    # the hermes-0day MCP-persistence campaign abused unauthenticated public
    # dashboards). If a caller still passes it, warn that it is now a no-op
    # rather than silently changing their expectation of an open bind.
    if allow_public and host not in _LOOPBACK_HOST_VALUES:
        _log.warning(
            "--insecure no longer bypasses dashboard authentication. A "
            "non-loopback bind (%s) now ALWAYS requires an auth provider "
            "(OAuth or the bundled password provider). Configure one — see "
            "below — or bind to 127.0.0.1 and reach it over an SSH tunnel / "
            "Tailscale.", host,
        )
```

CLI 的 help 文本也已同步改口(这一点是一致的,不算冲突):

`hermes_cli/subcommands/dashboard.py:32 @ 863e313`
```python
    parser.add_argument(
        "--insecure",
        action="store_true",
        help=(
            "DEPRECATED / NO-OP. Formerly bypassed auth on a non-loopback "
            "bind. As of the June 2026 hardening it no longer disables "
            "authentication — a public bind always requires an auth provider "
            "(password or OAuth). Bind 127.0.0.1 + tunnel to keep it local."
        ),
    )
```

**▲ 文档与代码矛盾(仓库自带部署清单没跟上)**:Windows 版 compose 仍然按老语义写着
`--host 0.0.0.0 … --insecure`。按现在的代码,这个容器在没有配 auth provider 时会
**直接 SystemExit,起不来**。

`docker-compose.windows.yml:38 @ 863e313`
```yaml
    command: ["dashboard", "--host", "0.0.0.0", "--port", "9119", "--no-open", "--insecure"]
```

同仓的 Linux 版 compose 反而是对的(环回 + 提示走 ssh 隧道),说明这是漏改一处:

`docker-compose.yml:75 @ 863e313`
```yaml
    # Localhost-only. For remote access, tunnel via `ssh -L 9119:localhost:9119`.
    command: ["dashboard", "--host", "127.0.0.1", "--no-open"]
```

另有一处**代码内部的注释**没跟上同一次改动:`_is_accepted_host` 还写着
"0.0.0.0 bind ... (requires --insecure per web_server.start_server)"——现在 `--insecure` 已是 no-op,
`0.0.0.0` 需要的是 auth provider,不是这个 flag。

`hermes_cli/web_server.py:523 @ 863e313`
```python
    # 0.0.0.0 bind means operator explicitly opted into all-interfaces
    # (requires --insecure per web_server.start_server). No Host-layer
    # defence can protect that mode; rely on operator network controls.
    if bound_host in {"0.0.0.0", "::"}:
        return True
```
**▲**(注释 vs 代码,同一文件内)。这条同时说明另一件重要的事:**bind 到 `0.0.0.0` 时
Host 头校验形同虚设**——DNS rebinding 的应用层防线只在"绑了具体地址"时有效。

### 4.4 没有 provider 时为什么直接拒绝启动

因为**没有别的出口了**。以前的出口就是 `--insecure`;去掉它之后,"非环回 + 无 provider"
是一个没有安全落点的状态,只能 fail-closed。

`hermes_cli/web_server.py:17478 @ 863e313`
```python
    if app.state.auth_required:
        # The gate engages on every non-loopback bind. Require at least one
        # provider to be registered, else fail closed — there is no longer an
        # escape hatch that serves the dashboard without authentication.
        from hermes_cli.dashboard_auth import list_providers
        if not list_providers():
```

拒绝时**分两条消息**,区别在于"有没有 provider 装了但没配好"。有 `LAST_SKIP_REASON` 时:

`hermes_cli/web_server.py:17540 @ 863e313`
```python
                raise SystemExit(
                    f"Refusing to bind dashboard to {host} — the auth gate "
                    f"engages on non-loopback binds, but no auth providers "
                    f"are registered.\n\n"
                    f"Bundled providers reported these issues:\n"
                    + "\n".join(skip_reasons)
                    + "\n\n"
                    + _fix_hint
                )
```

否则走裸版:

`hermes_cli/web_server.py:17549 @ 863e313`
```python
            raise SystemExit(
                f"Refusing to bind dashboard to {host} — the auth gate "
                f"engages on non-loopback binds, but no auth providers are "
                f"registered.\n\n" + _fix_hint
            )
```

**这段的设计精髓不在"拒绝",在"拒绝时把话说全"**:它专门去读 provider plugin 的
`LAST_SKIP_REASON`,还专门处理了"`dashboard.basic_auth` 配好了但 `basic` 插件被列进
`plugins.disabled`"这个把人坑惨的组合(#54489)。**"no providers" 这句话在 provider 装了但没配的时候
是误导性的**——这是我在整段里最想搬走的一条工程判断。

配套注意:`main.py` 在调 `start_server` **之前**显式跑了一次 `discover_plugins()`,否则
provider 插件根本没机会注册,fail-closed 会误伤:

`hermes_cli/main.py:10464 @ 863e313`
```python
    try:
        from hermes_cli.plugins import discover_plugins
        discover_plugins()
    except Exception as exc:
```

### 4.5 起来之后:host 记账、uvicorn 参数、端口发现

绑定的 host 记回 `app.state`,供 Host 头中间件用(反 DNS rebinding):

`hermes_cli/web_server.py:17562 @ 863e313`
```python
    app.state.bound_host = host
```

uvicorn 的三个参数都由"是不是环回 / 门开没开"驱动:

`hermes_cli/web_server.py:17596 @ 863e313`
```python
    _is_loopback = host in ("127.0.0.1", "localhost", "::1")
    config = uvicorn.Config(
        app, host=host, port=port, log_level="warning",
        # proxy_headers defaults to False so _ws_client_is_allowed sees
        # the real connection peer rather than X-Forwarded-For's rewritten
        # value (which would defeat the loopback gate when behind a reverse
        # proxy).  When the OAuth gate is active we are explicitly running
        # behind a TLS terminator (Fly.io) and need X-Forwarded-Proto to
        # decide cookie Secure flags, so we flip proxy_headers on for that
        # mode.
        proxy_headers=bool(app.state.auth_required),
```
三条取舍值得原样搬走:
1. **`proxy_headers` 默认关**——开了 `X-Forwarded-For` 就能伪造 peer,环回门直接失效;
   只有在"我确知自己在 TLS 终结器后面"(门开着)时才打开,而且是为了 `X-Forwarded-Proto` 定 cookie 的 Secure 位。
2. **环回上把 WS keepalive ping 完全关掉**(`ws_ping_interval=None`)。理由不是省流量:
   agent 一次长回合会拿着 GIL 卡住事件循环几分钟,循环处理不了 pong,uvicorn 就判定连接死了
   把健康的本地连接掐掉(#53773 记录了 226.3s 的 stall)。**环回上没有半开连接这种失败模式**
   (没有网络、没有代理,本地客户端死了会有真的 FIN/RST),所以 ping 是净负值。
3. `_is_loopback` 这里是**另一份**环回判定(元组字面量),和 `_LOOPBACK_HOST_VALUES` 内容相同但
   各写各的。◇ 两处硬编码同一个集合,没有共享常量,改一处漏一处。

端口发现刻意做成"先 startup 再读 socket",消除了老做法的 TOCTOU:

`hermes_cli/web_server.py:17564 @ 863e313`
```python
    # ── Start uvicorn with direct Server API ─────────────────────────
    # We use uvicorn.Server directly (not uvicorn.run) so we can split
    # startup from the main loop.  After startup() the socket is actually
    # bound — we read the OS-assigned port from the live socket, print
    # HERMES_DASHBOARD_READY, open the browser, *then* serve.
```

Windows 只在**这一处**分叉:`asyncio.run` 在 win32 默认给 Proactor loop,而 uvicorn 的 socket 栈
假定 Selector loop,结果是"端口 LISTENING 但握手永远不完成"(#50641)。

`hermes_cli/web_server.py:17706 @ 863e313`
```python
    if sys.platform != "win32":
        asyncio.run(_serve())
        return
```

---

## 5. Skills hub 的 install:从哪装、装到哪、装之前校验什么(供应链面)

### 5.1 端点做的事:几乎什么都没做,直接转给 CLI

`hermes_cli/web_routers/skills.py:56 @ 863e313`
```python
    identifier = (body.identifier or "").strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="identifier is required")
    name = _hub_action_name("install", identifier)
    try:
        proc = _spawn_hermes_action(
            _profile_cli_args(body.profile or profile)
            + ["skills", "install", identifier, "--yes"],
            name,
        )
```

- `identifier` **只做非空校验**,没有格式、来源、前缀白名单;
- 是 argv 元素(list 形式的 `subprocess.Popen`,**没有 shell**),所以不存在命令注入;
- 参数注入(identifier 以 `-` 开头)只能"设一个 flag 但同时缺掉 positional",argparse 会直接报错,
  **拿不到 `--force`**——因为 `--force` 和 `identifier` 是两个 argv 元素,一个字符串给不出两个。

### 5.2 从哪装:**没有来源白名单**,URL 直装是被明写支持的

`hermes_cli/subcommands/skills.py:88 @ 863e313`
```python
    skills_install = skills_subparsers.add_parser("install", help="Install a skill")
    skills_install.add_argument(
        "identifier",
        help="Skill identifier (e.g. openai/skills/skill-creator) or a direct HTTP(S) URL to a SKILL.md file",
    )
```

有的只是**信任分级表**:只有 `official`(内置可选技能)算 `builtin`,四个硬编码仓库算 `trusted`,
**其余一律 `community`**——包括任意 URL、任意 GitHub 仓库、skills.sh / ClawHub / LobeHub 上的一切。

`tools/skills_guard.py:44 @ 863e313`
```python
TRUSTED_REPOS = {
    "openai/skills",
    "anthropics/skills",
    "huggingface/skills",
    # NVIDIA-verified skills: each entry ships a signed `skill.oms.sig`
    # and a governance `skill-card.md` (sync pipeline drops anything
    # missing the signature or card). Catalog details:
    # https://github.com/NVIDIA/skills
    "NVIDIA/skills",
}
```

**签名:本地不验。** 上面注释提到的 `skill.oms.sig` 是 **NVIDIA 上游同步流水线**的性质描述,
不是本地校验步骤。搜索面:`tools/skills_hub.py`、`tools/skills_guard.py`、`hermes_cli/skills_hub.py`
三个文件里 grep `signature|\.sig\b|verify_sig|gpg|minisign|cosign`,命中的全部是**注释**
和一条**扫描规则名** `gpg_dir_access`——它是"检测技能是否读 GPG 钥匙串"的规则,
和"校验技能自己的签名"完全无关。**没有任何一处执行签名校验**。◎ 记为负结论,搜索面如上。

`tools/skills_guard.py:129 @ 863e313`
```python
    (r'\$HOME/\.gnupg|\~/\.gnupg',
     "gpg_dir_access", "high", "exfiltration",
     "references user GPG keyring"),
```

### 5.3 装之前校验什么:一次静态扫描 + 一张策略表

`tools/skills_guard.py:55 @ 863e313`
```python
INSTALL_POLICY = {
    #                  safe      caution    dangerous
    "builtin":       ("allow",  "allow",   "allow"),
    "trusted":       ("allow",  "allow",   "block"),
    "community":     ("allow",  "block",   "block"),
```

CLI 的 install 流程里,策略判定**在确认提示之前**,而且 `allowed` 为 `None`("ask")时
`not allowed` 也为真 → 一样拦下:

`hermes_cli/skills_hub.py:679 @ 863e313`
```python
    # Check install policy
    allowed, reason = should_allow_install(result, force=force)
    if not allowed:
        c.print(f"\n[bold red]Installation blocked:[/] {reason}")
```

`--yes` 跳过的只是那个**人类免责声明确认框**,不是扫描门:

`hermes_cli/skills_hub.py:696 @ 863e313`
```python
    # Confirm with user — show appropriate warning based on source
    # skip_confirm bypasses the prompt (needed in TUI mode where input() hangs)
    if not force and not skip_confirm:
```

**所以从 dashboard 装技能的真实安全模型是**:
> 任意来源(含任意 URL)→ 落 quarantine → 一次**启发式静态扫描** → 若判为 `safe` 则
> **无人工确认直接装进 `$HERMES_HOME/skills/`**;判为 `caution`/`dangerous` 才拦。
> 没有来源白名单,没有签名,`--force` 从 dashboard 走不通(端点不传)。

也就是说,**扫描器的假阴性 = 直接落盘**。而技能的内容会进系统提示词——这是提示注入面,
不是"多一个工具"那么简单。dashboard 侧确实补了 `GET /api/skills/hub/scan`
("装之前先扫一遍"按钮)和 `/preview`("装之前先读 SKILL.md"),但它们是**用户可选的动作**,
不是 install 路径上的强制关卡。

`hermes_cli/web_routers/skills.py:299 @ 863e313`
```python
@hub_router.get("/api/skills/hub/scan")
async def scan_skill_hub(identifier: str = "", profile: Optional[str] = None):
    """Run the install-time security scan on a hub skill WITHOUT installing it.
```

### 5.4 装到哪

`install_from_quarantine` 把 quarantine 目录移进 skills 根,路径经过三层校验:
技能名校验、category 校验(`_validate_install_parent_path`)、以及"quarantine 路径必须在 quarantine 根下":

`tools/skills_hub.py:3720 @ 863e313`
```python
    safe_skill_name = _validate_skill_name(skill_name)
    safe_category = _validate_install_parent_path(category) if category else ""
    quarantine_resolved = quarantine_path.resolve()
    quarantine_root = _quarantine_dir().resolve()
    if not quarantine_resolved.is_relative_to(quarantine_root):
        raise ValueError(f"Unsafe quarantine path: {quarantine_path}")
```

还额外拒绝"把技能装进另一个技能目录里"(否则外层技能被卸载时会连内层一起 rmtree,#75983 的兄弟场景)。

### 5.5 ■(低)action 日志登记表无界增长

`_hub_action_name` 对**每一个不同的 identifier** 都 `setdefault` 一条进模块级字典,并在
`_spawn_hermes_action` 里**先 open 日志文件再 spawn**。字典和目录都没有任何裁剪路径
(全文件只有 `_ACTION_PROCS.pop`,没有 `_ACTION_LOG_FILES.pop`)。

`hermes_cli/web_server.py:3722 @ 863e313`
```python
_ACTION_LOG_FILES: Dict[str, str] = {
    "gateway-restart": "gateway-restart.log",
```

**失效链**:已鉴权会话 → 循环 POST `/api/skills/hub/install`,每次换一个 identifier →
每次新增一条 dict 条目 + 一个磁盘日志文件 + 一个子进程 → 进程内存与磁盘 inode 单调增长,
无上限、无 TTL。**需要已鉴权前提,定级低**;但它是"名字即资源键"这类设计的典型代价,
成品章里值得当反例讲一句。

---

## 6. Profile 管理:create / rename / delete 各动了磁盘上的什么

### 6.1 create

端点 `POST /api/profiles` 是个"先做主干,再尽力做支线"的形状:

- **主干**(失败就 400/500):`profiles_mod.create_profile(...)` 建目录;非 clone 时
  `seed_profile_skills` 播种内置技能;`create_wrapper_script` 在 `~/.local/bin/<name>` 建别名脚本
  (先 `check_alias_collision`)。

  `hermes_cli/web_routers/profiles.py:389 @ 863e313`
  ```python
          if not clone:
              profiles_mod.seed_profile_skills(path, quiet=True)

          # Match the CLI's profile-create flow: named profiles should get a
          # wrapper in ~/.local/bin when the alias is safe to create.
          collision = profiles_mod.check_alias_collision(body.name)
          if not collision:
              profiles_mod.create_wrapper_script(body.name)
  ```

- **支线**(全部 best-effort,失败只记日志):写主模型、写 MCP servers、按 keep 列表禁用未选技能、
  为每个 `hub_skills` spawn 一个 `hermes -p <name> skills install <id> --yes`。

`hermes_cli/web_routers/profiles.py:403 @ 863e313`
```python
    # Optional explicit model assignment for the new profile. Best-effort:
    # the profile already exists, so a model-write hiccup must not 500 the
    # whole create — the user can set the model later from the Models page
    # or `<profile> setup`.
```

**为什么支线要 best-effort**:目录已经建出来了,回滚成本高于"让用户去对应页面补一下"。
这条取舍写得很直白,值得搬。

**profile 名字的校验在哪**:`create_profile` 内部 `normalize_profile_name` → `validate_profile_name`;
dashboard 侧另有 `_resolve_profile_dir` 做同样的事(用于 `-p` 参数与目录解析):

`hermes_cli/web_server.py:13393 @ 863e313`
```python
def _resolve_profile_dir(name: str) -> Path:
    """Validate ``name`` and resolve to its directory or raise an HTTPException."""
    from hermes_cli import profiles as profiles_mod
    try:
        profiles_mod.validate_profile_name(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

`hermes_cli/profiles.py:341 @ 863e313`
```python
    if not _PROFILE_ID_RE.match(name):
        raise ValueError(
            f"Invalid profile name {name!r}. Must match "
            f"[a-z0-9][a-z0-9_-]{{0,63}}"
        )
    if name in _RESERVED_NAMES:
```

### 6.2 rename

`PATCH /api/profiles/{name}` → `rename_profile`,动了**五样东西**,顺序有讲究:

`hermes_cli/profiles.py:2210 @ 863e313`
```python
    # 1. Stop gateway if running
    if _check_gateway_running(old_dir):
        _cleanup_gateway_service(old_canon, old_dir)
        _stop_gateway_process(old_dir)

    # 2. Rename directory
    old_dir.rename(new_dir)
```

后续依次是:3) 迁移 Honcho 的 profile-scoped host 块(保住 aiPeer 身份);
4) 删旧 wrapper、按需建新 wrapper;5) 若 `active_profile` 指向旧名则改指新名。
护栏只有两条:`default` 既不能被改名,也不能被改成 `default`。

### 6.3 delete:动了什么、凭据删不删、有没有"正在用"的保护

`hermes_cli/web_routers/profiles.py:583 @ 863e313`
```python
@router.delete("/api/profiles/{name}")
async def delete_profile_endpoint(name: str):
    """Delete a profile. The dashboard collects the user's confirmation in
    its own dialog before this request, so we always pass ``yes=True`` to
    skip the CLI's interactive prompt."""
```

**注意 `yes=True`**:CLI 版要求用户手打 profile 名字才肯删,dashboard 版把这一步交给前端弹窗,
API 层是**无条件删**。

`delete_profile` 的完整动作序列(1 → 5):

`hermes_cli/profiles.py:1537 @ 863e313`
```python
    # 1. Disable service (prevents auto-restart)
    _cleanup_gateway_service(canon, profile_dir)
```
然后 1b) s6 槽位注销(容器路径);2) 停 gateway;2b) `_stop_profile_backends` 停掉
Desktop 起的、`gateway.pid` 记不到的 serve/dashboard 后端;3) 删 wrapper 脚本;
4) `_rmtree_with_retry` 整棵删档位目录;5) 若 `active_profile` 指向它则重置为 `default`。

**凭据一并删掉吗?——会,而且它自己就是这么宣告的。**

`hermes_cli/profiles.py:1509 @ 863e313`
```python
    items = [
        "All config, API keys, memories, sessions, skills, cron jobs",
    ]
```
档位目录是整棵 rmtree,`.env`(0600 的那个)、`config.yaml`、`state.db` 全在里面。
**负结论 + 搜索面**:在 `hermes_cli/profiles.py`(2262 行)里 grep `keyring|keychain` **零命中**;
在 `hermes_cli/` 与 `tools/` 两棵树里 grep `import keyring` 也**零命中**——
即这套实现**根本不用 OS 钥匙串**,所以不存在"目录删了但系统钥匙串里还留着凭据"的残留面。

**有没有防止删掉正在用的档位?——只挡 `default`,不挡"当前进程正在用的那个"。**

`hermes_cli/profiles.py:1479 @ 863e313`
```python
    canon = normalize_profile_name(name)
    validate_profile_name(canon)

    if canon == "default":
        raise ValueError(
            "Cannot delete the default profile (~/.hermes).\n"
```

而"停掉绑在这个档位上的后端"这一步**刻意跳过自己和自己的祖先进程**:

`hermes_cli/profiles.py:1316 @ 863e313`
```python
    # Never terminate ourselves or a parent (e.g. `hermes -p <canon> profile
    # delete` runs under the very profile it's deleting).
    skip: set[int] = {os.getpid()}
```

**■ 失效链(自毁)**:
1. 用 `hermes dashboard --isolated` 从某个命名档位启动,dashboard 进程的 `HERMES_HOME` = 该档位目录;
2. 从这个 dashboard 调 `DELETE /api/profiles/<该档位名>`;
3. `delete_profile` 只挡 `default`,该名字不是 `default` → 放行;
4. `_stop_profile_backends` 的 `skip` 含 `os.getpid()`,**不会停掉正在处理这个请求的自己**;
5. `_rmtree_with_retry` 把自己的 `HERMES_HOME` 整棵删掉,进程继续跑,后续任何 config/state 访问
   面对的是一个不存在的目录。
**没有任何一层挡它**——`sticky active_profile` 会被重置为 `default`,但那是**记录**,不是**运行中的进程**。
定级:中(需要 `--isolated` 起法 + 已鉴权),表现为"删完之后 dashboard 行为不可预测",不是提权。

---

## 7. `web_routers/tools.py` 与 `skills.py`:是不是"改 agent 能用哪些工具"的面?会不会绕过审批?

### 7.1 是。两者都是,但改的是**两种不同的东西**

- `tools.py` 改的是 **toolset 开关**(`platform_toolsets.<platform>`)与**每个 toolset 的 provider / 模型 / 密钥**,
  也就是"哪些工具会出现在 agent 的 tool schema 里";
- `skills.py` 改的是 **skill 的启用/内容**,也就是"哪些指令会进系统提示词"。

toolset 开关的写路径:

`hermes_cli/web_routers/tools.py:115 @ 863e313`
```python
@router.put("/api/tools/toolsets/{name}")
async def toggle_toolset(name: str, body: ToolsetToggle, profile: Optional[str] = None):
    """Enable/disable a configurable toolset for its configuration platform.
```
它先用 `_get_effective_configurable_toolsets()` 的 key 集合做白名单,未知 key 直接 400——
**这一面是有枚举校验的**。

### 7.2 会不会绕过 approvals?——**toolset 开关不会;但 skill 写入是"明写的绕过",终端后端切换是"隐含的绕过"**

**(a) toolset 开关不绕。** approvals 是**执行期**的闸门,和"这个工具在不在 schema 里"正交:
`terminal` 被启用,agent 调用它时照样进 `check_all_command_guards`——门在 `env.execute` 之前,
与 toolset 无关。

`tools/terminal_tool.py:2612 @ 863e313`
```python
        if not force:
            approval = _check_all_guards(
                command, env_type,
                has_host_access=_docker_has_host_access(config),
            )
```

**(b) skill 写入是文档化的绕过。** 端点自己写明了:

`hermes_cli/web_routers/skills.py:459 @ 863e313`
```python
@router.post("/api/skills")
async def create_skill(body: SkillCreate):
    """Create a new custom skill (SKILL.md) from the dashboard editor.

    Calls the same validated write path as the agent's ``skill_manage``
    tool (frontmatter validation, name/category validation, size limit,
    optional security scan) — but bypasses the agent write-approval gate:
    a write from the authenticated dashboard IS the user acting directly.
    """
```
理由是自洽的("已鉴权 dashboard 上的写 = 用户本人在操作"),但它意味着
**dashboard 的鉴权强度就是 skill 写入的安全强度**——环回 bind 下那是一个注入进 SPA HTML 的进程内 token。
它复用的 `_create_skill` 仍有 frontmatter/名字/大小/扫描四道校验,且扫描不过会**回滚删目录**:

`tools/skill_manager_tool.py:944 @ 863e313`
```python
    # Security scan — roll back on block
    scan_error = _security_scan_skill(skill_dir)
    if scan_error:
        shutil.rmtree(skill_dir, ignore_errors=True)
        return {"success": False, "error": scan_error}
```

**(c) ◇ 终端后端切换会改变审批层是否运行——这条没有任何文档。**

`PUT /api/tools/terminal/backend` 就是往 `config.yaml` 写一个 `terminal.backend`:

`hermes_cli/web_routers/tools.py:683 @ 863e313`
```python
    with _profile_scope(body.profile or profile):
        config = load_config()
        terminal_cfg = config.setdefault("terminal", {})
        if not isinstance(terminal_cfg, dict):
            terminal_cfg = {}
            config["terminal"] = terminal_cfg
        terminal_cfg["backend"] = backend
        save_config(config)
```

这个键被桥接成 `TERMINAL_ENV`:

`hermes_cli/config.py:3183 @ 863e313`
```python
TERMINAL_CONFIG_ENV_MAP = {
    "backend": "TERMINAL_ENV",
```

而 `TERMINAL_ENV` 决定的 `env_type`,是**危险命令审批层的第一道分叉**:

`tools/approval.py:3406 @ 863e313`
```python
def _should_skip_container_guards(env_type: str, has_host_access: bool = False) -> bool:
    """Return True when the backend is isolated enough to skip dangerous-command prompts.

    Isolated container backends sandbox the agent away from the host, so their
    commands can't damage real files/services and we skip the approval layer.
    Docker is the exception once host paths are bind-mounted into the container:
    at that point a command like ``rm -rf /workspace`` reaches host files, so it
    must go through the normal approval flow.
    """
    if env_type == "docker":
        return not has_host_access
    return env_type in ("singularity", "modal", "daytona", "vercel_sandbox")
```

`tools/approval.py:3752 @ 863e313`
```python
    # Skip isolated container backends for both checks. Docker stops skipping
    # once host paths are bind-mounted into the sandbox.
    if _should_skip_container_guards(env_type, has_host_access=has_host_access):
        return {"approved": True, "message": None}
```

**即:从 dashboard 把后端从 `local` 切到 `singularity`/`modal`/`daytona`(或无 host 挂载的 `docker`),
就等于把 hardline 之外的整层危险命令审批关掉**,而端点自己的 docstring 只说
"选一个还没配好的后端是允许的,选择器会显示指引而不是拦住你",一个字没提审批后果。

**我把这条判为 ◇ 而不是 ■,理由是查实了它 fail-closed**:后端建不起来时 `_create_environment`
的失败路径是**返回错误**,不是静默回落到 local——所以不存在"审批被跳过、命令却在宿主机上跑"的组合:

`tools/terminal_tool.py:2473 @ 863e313`
```python
                    except ImportError as e:
                        return json.dumps({
                            "output": "",
                            "exit_code": -1,
                            "error": f"Terminal tool disabled: environment creation failed ({e})",
                            "status": "disabled"
                        }, ensure_ascii=False)
```

### 7.3 唯一真正"能改 approvals 本身"的面在别处

`tools/approval.py` 自己点名说 `config.yaml` **就是**安全策略,而且配置缓存按 mtime 失效,
写下去当场生效:

`tools/approval.py:279 @ 863e313`
```python
# ~/.hermes/config.yaml IS the security policy: approvals.mode, yolo, and the
# permanent-approval allowlist live here, and the config cache is mtime-keyed
# so a write takes effect mid-session (the agent could flip approvals.mode=off
# and immediately bypass the gate). Pair the write_file/patch deny (file_tools
# _check_sensitive_path) with terminal-side coverage so `sed -i`, `tee`, `>`,
# `cp`, etc. targeting it are gated too — otherwise the deny is unpaired
# theater. Mirrors _HERMES_ENV_PATH; matches the HERMES_HOME override form as
# well as ~/.hermes/.
```
**它防的是 agent**(工具层写 `config.yaml` 被 deny)。**它防不到 dashboard**:
`PUT /api/config`(`ConfigUpdate.config: dict`,§2.1)和 `PUT /api/config/raw` 是两条直写 `config.yaml` 的
HTTP 通道,不经过 `file_tools` 的 deny,也不经过 approvals。这与本轮另一段
"`PUT /api/config` 收任意键名"的定案是**同一条链的两端**,合起来才是完整叙述:
> agent 想关掉自己的审批 → 被工具层 deny 拦住;
> 但只要 agent 能诱导 dashboard 发一个 `PUT /api/config {"config": {"approvals": {"mode": "off"}}}`,
> 这道 deny 就绕过去了。

**注意这是链路描述,不是已复现的攻击**:agent 要触发 dashboard 请求还需要一个额外的
SSRF/前端注入原语,本段没有取到证据。列为存疑项(§10)。

### 7.4 这一面里做得最好的一处:env 写入是白名单制

和 §2.1 那些裸 dict 相比,`ToolsetEnvUpdate.env` 有硬校验——键名必须属于该 toolset
**可见 provider 的 `env_vars` 并集**,否则 400:

`hermes_cli/web_routers/tools.py:559 @ 863e313`
```python
        unknown = [k for k in body.env if k not in allowed]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown env var(s) for toolset {name}: {', '.join(sorted(unknown))}",
            )
```
docstring 把设计意图写得很准:"so the GUI can't write an arbitrary env var through this endpoint"。
**这正好证明"裸 dict 不校验键名"是能被解决的**——同一个文件里就有正确做法,
`ConfigUpdate` 只是没做。

---

## 8. 记号汇总

| 记号 | 条目 | 锚点 |
|---|---|---|
| ▲ | Windows compose 仍按老语义传 `--host 0.0.0.0 --insecure`,现在会 fail-closed 起不来 | `docker-compose.windows.yml:38` |
| ▲ | `_is_accepted_host` 注释仍写 "requires --insecure per web_server.start_server",而 `--insecure` 已是 no-op | `hermes_cli/web_server.py:525` |
| ■ | dashboard 插件 `name` 由 manifest 声明而非目录推出,user 插件可顶掉同名 bundled 插件并继承其 `plugins.enabled` 勾选 → 同意门错配 | `hermes_cli/web_server.py:16639` |
| ■ | `delete_profile` 只挡 `default`,不挡"当前进程正在用的档位";`_stop_profile_backends` 又刻意跳过自己 → `--isolated` dashboard 可删掉自己的 HERMES_HOME | `hermes_cli/profiles.py:1482`、`hermes_cli/profiles.py:1318` |
| ■(低) | `_ACTION_LOG_FILES` 按 identifier 无界增长,无裁剪路径 | `hermes_cli/web_server.py:3722`、`hermes_cli/web_server.py:13220` |
| ◇ | 插件路由挂载点排在 `_dashboard_auth_router` 与 SPA catch-all **之前**,注释只提了后者 | `hermes_cli/web_server.py:17315` |
| ◇ | `PUT /api/tools/terminal/backend` 改的是"整层危险命令审批跑不跑",端点 docstring 只字未提 | `hermes_cli/web_routers/tools.py:665`、`tools/approval.py:3406` |
| ◇ | `_is_loopback` 与 `_LOOPBACK_HOST_VALUES` 两处独立硬编码同一集合 | `hermes_cli/web_server.py:17596`、`hermes_cli/web_server.py:467` |
| ◇ | `web_models.py` 里只有 `bearer_token` 用 `SecretStr`,其余 api_key 皆裸 `str`,不对称无解释 | `hermes_cli/web_models.py:399` |
| ◎ | `/api/dashboard/plugins` 在公开白名单里,公网 bind 下无凭据即可枚举已装插件名/版本;内部路径已剥除,泄露面确为只读 | `hermes_cli/dashboard_auth/public_paths.py:52` |
| ◎ | skills 安装**不做签名校验**(负结论,搜索面见 §5.2);现有防线是静态扫描 + 信任分级表 | `tools/skills_guard.py:55` |

---

## 9. 测试作为行为规格(实跑并报数)

**环境:`/home/user/hermes-venv`,91 包(见 §0,已从 CLAUDE.md 记的 87 漂移)。**
命令一律:
```console
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh <文件...>
```

| 批次 | 文件数 | 通过 | 失败 |
|---|---|---|---|
| 插件 + 鉴权门:`test_project_plugin_rce_bypass.py` / `test_startup_plugin_gating.py` / `test_plugin_runtime_disable_gate.py` / `test_plugins_hub_perf_guard.py` / `test_dashboard_auth_gate.py` | 5 | **49** | 0 |
| skills / profiles / tools:`test_web_server_skills_profiles.py` / `test_web_server_skill_editor.py` / `test_web_profile_soul_writes.py` / `test_web_server_profile_unification.py` / `test_profiles.py` / `test_toolset_validation.py` / `test_tools_disable_enable.py` / `test_skills_install_flags.py` / `test_skills_skip_confirm.py` / `test_skills_hub.py` | 10 | **101** | 0 |
| web_server 主体:`tests/test_web_server.py` / `tests/hermes_cli/test_web_server.py` / `test_dashboard_admin_endpoints.py` / `test_dashboard_lifecycle_flags.py` / `test_plugins_cmd.py` | 5 | **229** | 0 |
| **合计** | **20** | **379** | **0** |

跑完复核基线仍为空(`git status --porcelain` 无输出)。

**几个测试文件本身就是行为规格,值得引用:**

- `tests/hermes_cli/test_project_plugin_rce_bypass.py` 的模块 docstring 是 GHSA-5qr3-c538-wm9j
  两个原语最清楚的一份叙述(truthy 语义 + `Path('safe') / '/abs'` 吞前缀),23 个用例逐层钉住
  "env 语义 / `_safe_plugin_api_relpath` / 挂载时复检 / project 来源一律拒绝"。
- `tests/hermes_cli/test_web_server.py::TestPluginAPIAuth` 钉住"插件 API 路由必须带 session token"
  (issue #19533),并且它的 fixture 注释把**挂载顺序**这件事写成了可执行的规格:
  中途挂载的插件路由会输给已经就位的 SPA catch-all,所以 fixture 必须把新路由挪到列表最前面。
  这正好从反面证明了 §3.3 的结论。
- `tests/hermes_cli/test_dashboard_auth_gate.py`(14 用例)是 §4 那张真值表的机器版。

---

## 10. 本段未覆盖 / 存疑(每条带锚点 + 一句话现象)

1. **`/api/config` → `approvals` 的可达性未取证。**
   锚点:`hermes_cli/web_server.py:6911`(`update_config`)+ `tools/approval.py:279`。
   现象:`ConfigUpdate.config` 是裸 dict、`_deep_merge` 后直接 `save_config`,路径上没有任何键名过滤,
   因此**理论上**可写 `approvals.mode`;但"agent 如何促成这次 HTTP 请求"缺一个原语,未复现。
   下一轮若做 dashboard 攻击面,应先构造一次 `PUT /api/config {"config":{"approvals":{"mode":"off"}}}`
   并确认磁盘落值,再谈链路。

2. **`CronJobUpdate.updates` 的未知键会不会落盘,未追到 `update_job` 内部。**
   锚点:`hermes_cli/web_server.py:11577`(`normalized = dict(updates or {})`)。
   现象:normalizer 只对约 7 个已知键做转换,**其余键原样带进** `_call_cron_for_profile(..., "update_job", ...)`;
   `cron/jobs.py::update_job` 是否有字段白名单没查(超出本段范围)。

3. **`Dashboard 主题`段(`16212`–`16553`)只做了结构级过读。**
   锚点:`hermes_cli/web_server.py:16299`(`_normalise_theme_definition`)。
   现象:用户主题来自 `$HERMES_HOME/themes/*.yaml`,经 `_parse_theme_layer` / `_normalise_theme_definition`
   归一后被渲染进首屏 CSS(`_render_active_theme_bootstrap_css`,`:15958`)——
   即**用户 YAML 的字符串会进 HTML/CSS**,是否有转义未验证。

4. **Token/成本分析段(`14010`–`14391`)只读了函数签名与聚合骨架,未验证数值口径。**
   锚点:`hermes_cli/web_server.py:14046`(`_merge_aux_into_by_model`)。
   现象:辅助模型用量是**单独一张表**再 merge 进 by-model 汇总的,合并规则是否会双计未核。

5. **插件 `tab.override` 能替换内置 tab,只看到 manifest 侧,未追前端。**
   锚点:`hermes_cli/web_server.py:16653`(`override_path = raw_tab.get("override")`,只校验以 `/` 开头)。
   现象:manifest 可以声明覆盖某个内置 tab 路径,后端只检查它是字符串且以 `/` 开头就放行;
   前端 `registerSlot` / 路由表如何消费未查(web/ 目录不在本段)。

6. **`_validate_plugin_name` 允许内部 `/`,其下游 `dashboard_*_user_plugin` 是否拿它拼路径未追。**
   锚点:`hermes_cli/web_server.py:17010`(`name = name.strip("/")`,只禁 `..` 和 `\`)。
   现象:`{name:path}` 可以是 `a/b`;`hermes_cli/plugins_cmd.py` 里的
   `dashboard_set_agent_plugin_enabled` / `dashboard_remove_user_plugin` 是否把它当路径段用,没查。
   嵌套插件 key 本来就长 `observability/nemo_relay` 这样,所以允许 `/` 很可能是**有意**的,
   但"有意"和"安全"要分别取证。

7. **`hub_skills` 在 profile-create 里用的是 `body.name` 原文,不是 canonical 名。**
   锚点:`hermes_cli/web_routers/profiles.py:443`(`["-p", body.name, "skills", "install", ident, "--yes"]`)。
   现象:`create_profile` 内部会 `normalize_profile_name`(小写化),但这里传的是用户原文;
   下游 `resolve_profile_env` 也会归一,所以**大概率无害**,未构造大小写用例验证。
