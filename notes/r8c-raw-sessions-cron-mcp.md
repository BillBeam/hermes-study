# R8C 底稿 · `hermes_cli/web_server.py` 11049–13310 + `web_routers/{sessions,cron,mcp}.py`

> **溯源约定**:凡对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` **单独成行、放在代码块之前**,
> 代码块为基线逐字原文。路径一律自基线仓库根解析。
> 非源码块用 ```text / ```console / ```verify 声明。
> 本段的**鉴权层**由本轮另一段负责(结论:pairing 路由本体零鉴权,全部保护来自中间件链),本底稿不重查,
> 只在必要处引用其结论。

---

## 0. 六问一句话结论

```text
Q1 地图     11049 会话详情/11440 日志/11498 Cron/11975 蓝图/11984 MCP/12282 Pairing/
            12380 Webhook/12532 网关生命周期/12566 凭据池/12732 Memory/12801 Ops/13182 Skills Hub。
            主线是"把 CLI 已有的数据层原样搬到 HTTP 上",几乎每块都在包一个 hermes_cli.* / cron.* / gateway.* 模块。
Q2 分工     抽出去的是"整条 URL 家族 + handler 已经很薄"的路由(7 个模块 / 99 条),
            重活(*_sync worker、模块状态、profile 解析)全部留在 web_server;
            不是纯搬运 —— 有一套强制约定:late() 晚绑定、原地挂载保序、回灌旧名、共用同一个 logger。
Q3 Pairing  _pairing_store 不需要 _profile_scope,因为 PairingStore 自己按 profile 名算目录,
            不动任何进程级全局,故可安全跨 await;approve 兼容 request_id/code 双入口;
            「不填 profile」与「填 default」在命名 profile 的进程上确实指向不同库(已实测,◇)。
Q4 凭据池   读不回:list 只出 mask_secret 后的 token_preview,POST/DELETE 都不回显原值,
            auth.json 也被 Files API 拉黑 —— 但同一段的 backup + backup/download 组合会把
            .env 与 auth.json 明文打包下发(已实测,◇)。
Q5 Ops      backup 打包整个 HERMES_HOME(含 .env / auth.json / state.db,排除 repo/缓存/backups 自身);
            import 会覆盖凭据与配置;来源校验只有"zip 里出现过 config.yaml/.env/state.db 任一 basename",
            无签名无出处;/api/ops/import 接受任意本地绝对路径,不限制在备份目录(◇)。
Q6 Cron     dashboard 建的任务落到 <profile home>/cron/jobs.json(use_cron_store 上下文改写);
            /api/cron/fire 免鉴权是因为它的调用方是 NAS 而不是浏览器,拿的是 NAS 签发的短期 JWT,
            cookie 门会在 verifier 之前把它 401 掉,所以必须绕过 —— JWT 才是真门,且默认 fail-closed。
```

---

## 1. 地图:行号区间 → 职责

### 1.1 区间表

```text
区间            主题                         形态              落到哪个数据层
11049–11166   会话详情 helper              纯函数            hermes_state.SessionDB
11167–11181   挂载 _sessions_routes.manage_router + 回灌旧名
11182–11346   SessionDB 打开策略 / 自动归档  纯函数 + 后台 tick  SessionDB / config.yaml sessions.*
11347–11436   _prune_sessions              纯函数            SessionDB.prune_sessions
11438–11494   日志查看器 GET /api/logs      1 条路由          hermes_cli.logs._read_tail
11496–11736   Cron dashboard 适配层         纯函数            cron.jobs(经 use_cron_store)
11737–11754   挂载 _cron_routes.router + 回灌旧名
11757–11970   Cron *_sync worker + fire     纯函数            cron.jobs / cron.scheduler_provider
11973–11981   Automation Blueprints 横幅(实现全在 cron.py 路由 + cron/blueprint_catalog.py)
11982–12095   MCP 创建规范化 / env 脱敏      纯函数            hermes_cli.mcp_config + mcp_security
12096–12111   挂载 _mcp_routes.router + 回灌旧名
12122–12274   MCP dashboard OAuth 飞行登记表 + worker         tools.mcp_dashboard_oauth / mcp_oauth
12280–12376   Pairing(list/approve/revoke/clear-pending)  4 条路由  gateway.pairing.PairingStore
12378–12528   Webhook 订阅(list/enable/create/delete/toggle) 5 条路由 hermes_cli.webhook JSON 库
12530–12562   网关生命周期(start/stop)     2 条路由          spawn `hermes gateway <verb>`
12564–12728   凭据池(list/add/remove)      3 条路由          agent.credential_pool → auth.json
12730–12797   Memory provider(status/select/reset)  3 条路由  config.yaml memory.* + memories/*.md
12799–13180   Ops(doctor/audit/backup/download/import/upload/hooks/checkpoints)  11 条路由
13182–13306   Skills Hub helper(动作名/来源标签/已装清单)
13308–        Profile 管理(下一段)
```

### 1.2 逐块「为什么需要」

**会话详情簇(11049–11436):为什么 helper 留在 web_server、路由却在别的文件里。**
这一段的函数全是"给别人用的",本身不带 `@app`。`_open_session_db_for_profile` 是全簇的地基——
它要解决的问题很具体:dashboard 是**一个进程要读很多 profile 的 state.db**,而只读打开会跳过
`_reconcile_columns()`,老库会在每次轮询上 500。

`hermes_cli/web_server.py:11210`
```python
def _open_session_db_for_profile(profile: Optional[str], *, read_only: bool):
    """Open a SessionDB with an explicit access mode for a profile.

    ``profile`` None/empty selects this process's own ``state.db``. A named
    profile opens that profile's on-disk store directly.

    Writable opens keep the full init and repair path. Read-only opens
    bootstrap a missing or zero-byte store once, and heal an older or
    malformed schema through one writable open before reopening read-only.
    The healthy read path never takes a write lock or requests a checkpoint.
    """
```

紧跟它的两段注释解释了两个真实事故:并发首屏轮询争抢 sqlite 文件创建(输家 `no such table: sessions`),
以及只读打开撞上旧 schema。两者都用"先用可写连接补一次,再退回只读"解决。

`hermes_cli/web_server.py:11192`
```python
# Serialises the one-time writable schema bootstrap for read-only opens.
# Concurrent first-load polls otherwise race sqlite file creation: the losers
# open mode=ro against a store whose schema is still being written and every
# query raises "no such table: sessions".
_session_db_bootstrap_lock = threading.Lock()
```

**路由顺序是这一簇最贵的隐性契约**,而且作者知道:抽路由的时候必须整块搬。

`hermes_cli/web_server.py:11134`
```python
# CRITICAL — every literal-path route below MUST be declared BEFORE the
# templated ``/api/sessions/{session_id}`` family that follows. FastAPI/
# Starlette match routes in registration order, and the ``{session_id}``
# pattern is unconstrained — it would otherwise swallow e.g.
# ``DELETE /api/sessions/empty``, ``POST /api/sessions/bulk-delete``, or
# ``GET /api/sessions/stats`` as "operate on the session with id
# 'empty'" / "'bulk-delete'" / "'stats'", which would 404 (or worse,
# succeed and delete the wrong row). Same story as the older
# ``/api/sessions/search`` endpoint up at line ~1191. If you split or
# reorder this block, move every route in it together.
```

**会话导入(11144–11156):为什么不用 FastAPI 的 body 解析。** 因为 FastAPI 会先把整个 JSON 读进内存再交给
handler,SessionDB 自己的 per-session / per-transaction 限额根本来不及生效;所以这里手工流式读并在
25 MB 处 413。

**日志查看器(11438–11494):为什么是 1 条路由却单独占一节。** 它是本段里唯一不包 CLI 数据层、
而是直接读 `<home>/logs/*.log` 的端点。关键设计是"过滤器为空必须传 `None` 而不是 `()`":

`hermes_cli/web_server.py:11465`
```python
    # Normalize "ALL" / "all" / empty → no filter. _matches_filters treats an
    # empty tuple as "must match a prefix" (startswith(()) is always False),
    # so passing () instead of None silently drops every line.
```
`search` 不被 `_read_tail` 支持,所以先拉 2000 行再在 Python 侧过滤——这是"能力落在下层就下推、
落不下去就上提"的一个小样本。

**Cron 适配层(11496–11736):为什么需要一层适配而不是直接暴露 `cron.jobs`。**
dashboard 是一个进程要写 N 个 profile 的 `jobs.json`,而 `cron/jobs.py` 的路径是 import 期常量。

`cron/jobs.py:84`
```python
CRON_DIR = HERMES_DIR / "cron"
JOBS_FILE = CRON_DIR / "jobs.json"
```

所以每次调用都要**同时**换两样东西:cron 存储上下文 + 运行时 HERMES_HOME。

`hermes_cli/web_server.py:11671`
```python
def _call_cron_for_profile(target_profile: Optional[str], func_name: str, *args, **kwargs):
    """Run cron.jobs helpers against the selected profile's cron directory.

    The dashboard is a single process that can inspect many profiles. Route
    storage through cron.jobs' execution-context override so dashboard calls
    cannot retarget a concurrent desktop ticker's load/save transaction.
    """
    profile_name, home = _cron_profile_home(target_profile)
    from cron import jobs as cron_jobs
    from hermes_constants import (
        reset_hermes_home_override,
        set_hermes_home_override,
    )

    token = set_hermes_home_override(str(home))
    try:
        with cron_jobs.use_cron_store(home):
            result = getattr(cron_jobs, func_name)(*args, **kwargs)
    finally:
        reset_hermes_home_override(token)

    if isinstance(result, list):
        return [_annotate_cron_job(j, profile_name, home) for j in result]
    if isinstance(result, dict):
        return _annotate_cron_job(result, profile_name, home)
    return result
```

`use_cron_store` 是 contextvar 覆盖,不动模块全局——这样并发的桌面 ticker 不会被 dashboard 的一次请求带偏:

`cron/jobs.py:171`
```python
def use_cron_store(home: Union[str, Path]):
    """Route cron storage to ``home`` without mutating process globals."""
    cron_dir = Path(home).expanduser().resolve() / "cron"
    token = _cron_store_override.set(
        _CronStorePaths(
            cron_dir=cron_dir,
            jobs_file=cron_dir / "jobs.json",
            output_dir=cron_dir / "output",
        )
    )
```

适配层还负责 dashboard 独有的**输入收窄**:表单来的 `script` 必须落在该 profile 的 `scripts/` 沙箱内。

`hermes_cli/web_server.py:11523`
```python
def _normalize_dashboard_cron_script(value: Any, profile_home: Path) -> Optional[str]:
    """Validate a dashboard-selected cron script against the profile sandbox."""
    text = _cron_optional_text(value)
    if not text:
        return None

    scripts_root = (profile_home / "scripts").resolve()
    raw_path = Path(text).expanduser()
    candidate = raw_path.resolve() if raw_path.is_absolute() else (scripts_root / raw_path).resolve()
    try:
        relative = candidate.relative_to(scripts_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"script must be inside {scripts_root}",
        ) from exc
    if not candidate.exists():
        raise HTTPException(status_code=400, detail=f"script does not exist: {candidate}")
    if not candidate.is_file():
        raise HTTPException(status_code=400, detail=f"script is not a file: {candidate}")
    return str(relative)
```
注意它 `resolve()` 之后再 `relative_to`,所以符号链接和 `../` 都逃不出去;返回的是**相对路径**,
存进 jobs.json 的也是相对路径——换机器仍然有效。

**MCP 簇(11982–12274):为什么创建请求要先过一个"规范化"函数再落盘。**
因为 Bearer token 绝不能进 config.yaml。

`hermes_cli/web_server.py:11992`
```python
def _normalize_mcp_server_create(
    body: MCPServerCreate,
) -> tuple[str, Dict[str, Any], Optional[str]]:
    """Validate a Dashboard MCP create request and build its safe config.

    The returned config never contains the submitted Bearer token. Callers
    persist the token with the shared Bearer helper only after they enter the
    intended profile scope. Keeping this conversion shared makes the
    standalone MCP page and the Profile Builder enforce the same
    transport/auth contract.
    """
```
它返回三元组 `(name, server_config, bearer_token)`:config 里只留 `Authorization: Bearer ${MCP_<NAME>_API_KEY}`
模板,真值由调用方在 profile scope 里写 `.env`。读回时 stdio 的 `env` 块统一脱敏:

`hermes_cli/web_server.py:12063`
```python
def _redact_mcp_env(env: Dict[str, Any]) -> Dict[str, str]:
    """Mask secret-shaped MCP env values for read responses."""
    out: Dict[str, str] = {}
    for k, v in (env or {}).items():
        try:
            out[str(k)] = redact_key(str(v)) if v else ""
        except Exception:
            out[str(k)] = "***"
    return out
```
(测试 `tests/hermes_cli/test_dashboard_admin_endpoints.py::TestMcpEndpoints::test_stdio_env_is_redacted_on_read`
与 `test_http_bearer_auth_separates_secret_from_config` 就是这两条的行为规格,本轮实跑通过。)

**Webhook / 网关生命周期 / Memory / Ops / Skills Hub** 的共同动机写在各自横幅里,一句话概括:
**让没有 shell 的远程管理员能干原本只有 CLI 能干的事**。凡是"跑得久 + 输出是文本"的就 spawn 成后台 action
(`doctor` / `security audit` / `backup` / `import` / `skills install` / `gateway start|stop`),
dashboard 用 `/api/actions/{name}/status` 拖日志;凡是"便宜 + 结构化"的就直接返回 JSON(hooks list、checkpoints list)。

---

## 2. `web_routers/*.py` 与 `web_server.py` 的分工原则

### 2.1 事实规模

```console
$ wc -l hermes_cli/web_routers/*.py hermes_cli/web_deps.py hermes_cli/web_models.py
     8 hermes_cli/web_routers/__init__.py
   243 hermes_cli/web_routers/cron.py
   138 hermes_cli/web_routers/git.py
   478 hermes_cli/web_routers/mcp.py
   811 hermes_cli/web_routers/profiles.py
   720 hermes_cli/web_routers/sessions.py
   490 hermes_cli/web_routers/skills.py
   736 hermes_cli/web_routers/tools.py
   153 hermes_cli/web_deps.py
   725 hermes_cli/web_models.py

$ 各 router 模块里 @*router.<verb> 装饰器计数
cron 13 | git 19 | mcp 11 | profiles 18 | sessions 14 | skills 12 | tools 12   合计 99
$ web_server.py 里 @app.<verb> 装饰器计数
135
```
即:**99 条路由已经搬出去,135 条还在主文件**;主文件仍有 17,732 行,搬走的 7 个模块合计 3,616 行。

### 2.2 抽的判据(从证据反推,仓库无成文规则——见 §2.5 负结论)

七个模块的取舍高度一致,判据是三条**同时成立**:

1. **是一条完整的 URL 家族**,而不是散点:`/api/git/*`、`/api/sessions/*`、`/api/cron/*`、`/api/mcp/*`、
   `/api/profiles/*`、`/api/skills/*`、`/api/toolsets|tools/*`。整族一起搬,才可能保住路由顺序(见 §1.2 的 CRITICAL 注释)。
2. **handler 已经很薄**:重活早就在 `*_sync` worker / `_git_op` / `_web_git.*` 里。极端例子是 git:
   138 行装下 19 条路由,每条基本一行。

`hermes_cli/web_routers/git.py:32`
```python
@router.get("/api/git/status")
async def git_status_route(path: str):
    return await _git_op(_web_git.repo_status, _git_path(path))


@router.get("/api/git/worktrees")
async def git_worktrees_route(path: str):
    return {"worktrees": await _git_op(_web_git.worktree_list, _git_path(path))}
```

3. **依赖能被"晚绑定"表达**:handler 只依赖 web_server 上的**可调用**或**可代理的状态**,
   不依赖只在 web_server 模块体里存在的语法级东西。

反过来,**留在主文件的**是三类:
(a) 状态的**所有者**——`_mcp_oauth_flows`、`_SESSION_TOKEN`、`_ACTION_PROCS`、`_session_db_bootstrap_lock` 等;
(b) 被多族共用的解析器——`_profile_scope` / `_config_profile_scope` / `_resolve_profile_dir` /
   `_cron_profile_home` / `_spawn_hermes_action`;
(c) **还没形成"族"的孤块**——pairing(4 条)、webhook(5 条)、credentials/pool(3 条)、memory(3 条)、
   ops(11 条)、gateway lifecycle(2 条)。它们完全符合判据 1~3,只是**还没轮到**;
   这一点是推断,证据是这些块的形态与已抽出的 cron/mcp 毫无二致(都是"薄 handler + 主文件 helper"),
   而 `web_routers/` 里没有它们的空壳。

### 2.3 抽出去的**不是纯搬运**——有四条强制写法约定

**约定一:handler body 逐字不动,但依赖必须换成 `late()` 代理。**

`hermes_cli/web_deps.py:38`
```python
def late(name: str):
    """Late-binding proxy for a callable defined on ``web_server``.

    The returned wrapper looks up ``web_server.<name>`` on every call, so
    async/sync nature, monkeypatched replacements, and module state are all
    resolved at call time — never frozen at import time.
    """

    def _proxy(*args: Any, **kwargs: Any):
        return getattr(_server(), name)(*args, **kwargs)

    _proxy.__name__ = name
    _proxy.__qualname__ = name
    return _proxy
```
`web_deps` 的模块 docstring 把两条理由写死了:直接 import 会**循环依赖**(web_server 要 import router 才能挂载),
把 helper 搬过来会**打断成百上千处 `monkeypatch.setattr(web_server, "_helper", ...)`**。
于是选了"状态留在 web_server,访问改成 call-time 解析"。
可变状态用 `LateState` 代理(转发 `__getitem__`/`__enter__`/`__len__`/比较等),
因为有些状态**定义在 include_router 之后**——比如 `_mcp_oauth_flows` 在 `:12124`,而 mcp router 在 `:12098` 就挂上了。

**约定二:在**原注册点**挂载,一条路由都不许挪位。**

`hermes_cli/web_routers/__init__.py:1`
```python
"""Extracted APIRouter modules for the dashboard web server.

Each module exposes ``router = APIRouter()`` (profiles additionally exposes
``sessions_router``) and is mounted by ``hermes_cli.web_server`` at the exact
point in module execution where the routes were originally registered, so
route-matching order is unchanged.  Shared web_server helpers/state are
reached through the late-binding seam in ``hermes_cli.web_deps``.
"""
```
代价是**一个文件可能被拆成多个 router 并在三个不同位置挂载**:

`hermes_cli/web_routers/sessions.py:1`
```python
"""Session dashboard routes (extracted verbatim from web_server.py).

Three routers because the original registration points are far apart and
global route order matters: ``list_router`` (GET /api/sessions) was registered
before the profiles ``sessions_router`` include, ``search_router``
(GET /api/sessions/search) right after it, and ``manage_router`` (the
mutation/detail endpoints) thousands of lines later - each is mounted at its
original registration point so the app's route table is byte-identical.

Handler bodies are byte-identical; web_server-owned helpers are reached via
the late-binding seam in :mod:`hermes_cli.web_deps` so tests that
``monkeypatch.setattr(web_server, "_helper", ...)`` keep working.
"""
```
对应三处挂载点:`:4827`(list_router)、`:4844`(search_router)、`:11167`(manage_router)。

**约定三:挂载之后立刻把 handler 名字回灌进 web_server 命名空间。**

`hermes_cli/web_server.py:11167`
```python
app.include_router(_sessions_routes.manage_router)
from hermes_cli.web_routers.sessions import (  # noqa: E402,F401 — legacy re-exports; tests call these via web_server.<name>
    bulk_delete_sessions_endpoint,
    import_sessions_endpoint,
    count_empty_sessions_endpoint,
    delete_empty_sessions_endpoint,
    get_session_stats,
    get_session_detail,
    get_session_latest_descendant,
    get_session_messages,
    delete_session_endpoint,
    rename_session_endpoint,
    export_session_endpoint,
    prune_sessions_endpoint,
)
```
七处 include 全是这个模式(`:2752`、`:4827`、`:4835`、`:4844`、`:11167`、`:11739`、`:12098`、`:13226`、
`:13515`、`:13666`、`:13699`)。作用是:**外部世界看到的 `hermes_cli.web_server` 表面完全没变**。

**约定四:logger 与 pydantic 模型也保持同一性。** 每个 router 模块都写
`_log = logging.getLogger("hermes_cli.web_server")`,注释是 "Same logger the handlers used before extraction
(identical logger object)";模型统一搬到 `hermes_cli/web_models.py`,并逐块留 provenance 注释
`# --- from web_server.py (originally lines 1273-1372) ---`,web_server 再全量 re-export。

### 2.4 一句话原则(可迁移)

> 拆巨型路由文件时,**先冻结可观测表面(路由表顺序 + 模块命名空间 + logger 名 + 模型身份),
> 再搬代码**;搬不动的依赖不要跟着搬,给它一个 call-time 解析的缝。
> 判据不是"这段代码有多长",而是"这一族路由能不能整体搬走且不改变匹配顺序"。

### 2.5 负结论(搜索面)

**仓库没有成文的抽取规则文档。** 搜索面:`grep -rn "web_routers" --include=*.md .`(1,492 个 md 文件)
只命中 0 条;`hermes_cli/web_routers/__init__.py`(8 行)、`hermes_cli/web_deps.py`(153 行)的模块
docstring 是**仅有的**规则表述。上面 §2.2 的判据是我从 7 个模块的形态反推的,不是作者写下的。

---

## 3. Pairing 簇(`:12280`–`:12376`)

### 3.1 `_pairing_store` 为什么不需要 `_profile_scope`

`hermes_cli/web_server.py:12288`
```python
def _pairing_store(profile: Optional[str] = None):
    """Pairing store for ``profile`` — the dashboard's own when unspecified.

    Every other admin endpoint scopes by profile, and the gateway already
    keeps one store per served profile (``gateway/run.py``). Without this the
    dashboard and desktop always read the global store, so an operator on a
    named profile approves into a whitelist their gateway never consults.

    ``PairingStore`` resolves the profile's home itself (``default`` maps back
    to the global store), so this only needs to validate the name — no
    ``_profile_scope`` needed, and nothing process-global is swapped across
    the ``await`` boundary.
    """
    from gateway.pairing import PairingStore

    requested = (profile or "").strip()
    if not requested or requested.lower() == "current":
        return PairingStore()

    _resolve_profile_dir(requested)  # 400/404 on an unknown profile

    return PairingStore(profile=requested)
```

**为什么不需要**,拆成两层看:

**第一层——`_profile_scope` 是个昂贵且危险的东西。** 它要做两件事:改 contextvar HERMES_HOME,
**以及**在进程级锁里临时改写 `tools.skills_tool.SKILLS_DIR` / `skill_manager_tool` 的模块属性
(因为那两个模块 import 期就绑死了路径)。姊妹函数 `_config_profile_scope` 的 docstring 把危险讲得最清楚:

`hermes_cli/web_server.py:13633`
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
    """
```
四个 pairing handler 全是 `async def`,天然有 `await` 边界,用 `_profile_scope` 就是踩这个坑。

**第二层——`PairingStore` 根本不读进程级 home,它自己算。** 传了 profile 就走"根 + profiles/<name>"这条路:

`gateway/pairing.py:421`
```python
    def __init__(self, profile: Optional[str] = None):
        # Resolve storage directory lazily — tests use a temp HERMES_HOME
        # and PairingStore may be constructed before the env is set.
        if profile:
            root = get_default_hermes_root()
            profile_home = (
                root
                if profile == "default"
                else root / "profiles" / profile
            )
            self._dir = get_hermes_dir(
                "platforms/pairing",
                "pairing",
                home=profile_home,
            )
        else:
            self._dir = PAIRING_DIR
```
`get_hermes_dir(new, old, home=...)` 的 `home=` 形参正是为这种"一个进程管多个 home"的调用方加的
(`hermes_constants.py:270` 的参数文档:"Profile-aware callers that manage more than one home in the same
process use this instead of temporarily mutating the process or context-local HERMES_HOME")。
所以 `_pairing_store` 只剩一件事要做:**验名**——这就是那行 `_resolve_profile_dir(requested)` 的全部用途
(它的返回值被丢弃)。

`hermes_cli/web_server.py:13393`
```python
def _resolve_profile_dir(name: str) -> Path:
    """Validate ``name`` and resolve to its directory or raise an HTTPException."""
    from hermes_cli import profiles as profiles_mod
    try:
        profiles_mod.validate_profile_name(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not profiles_mod.profile_exists(name):
        raise HTTPException(status_code=404, detail=f"Profile '{name}' does not exist.")
    return profiles_mod.get_profile_dir(name)
```

### 3.2 四条路由各做什么

`hermes_cli/web_server.py:12312`
```python
@app.get("/api/pairing")
async def list_pairing(profile: Optional[str] = None):
    store = _pairing_store(profile)
    return {
        "pending": store.list_pending(),
        "approved": store.list_approved(),
    }
```
**list**:一次返回两张表。`list_pending()` 的行形状实测为
`{platform, request_id, user_id, user_name, age_minutes}`(见 §3.4 探针输出)——注意它**回显了 request_id**,
这正是 approve 的首选入口;一次性配对码本身不回显。

`hermes_cli/web_server.py:12321`
```python
@app.post("/api/pairing/approve")
async def approve_pairing(body: PairingApprove):
    store = _pairing_store(body.profile)
    platform = (body.platform or "").lower().strip()
    # `request_id` is what an admin surface sends after listing pending
    # requests; `code` is the one-time code the user relays from their DM.
    # A GUI that only knows the older field name still works — a value with
    # request-id shape routes to the request path either way.
    target = (body.request_id or body.code or "").strip()
    if not platform or not target:
        raise HTTPException(
            status_code=400, detail="platform and request_id or code are required"
        )

    by_request_id = bool(body.request_id) or store.looks_like_request_id(target)
    if by_request_id:
        result = store.approve_request(platform, target)
    else:
        result = store.approve_code(platform, target.upper())

    if result:
        return {"ok": True, "user": result}
    # Lockout only gates the code path, so only report it there — otherwise a
    # stale request id would surface as a bogus 429 while the platform sat
    # locked out for an unrelated reason.
    if not by_request_id and store._is_locked_out(platform):
        raise HTTPException(
            status_code=429,
            detail=f"Platform '{platform}' is locked out after too many failed approvals.",
        )
    raise HTTPException(
        status_code=404,
        detail=f"Pairing request or code not found or expired for platform '{platform}'.",
    )
```

**approve 的业务语义有四个决定值得记:**

1. **双入口、单出口。** `request_id`(管理员从 list 里点)与 `code`(用户从 DM 里念给管理员)走两条不同的
   store 方法。旧 GUI 只认 `code` 字段,所以还有一条**形状嗅探**兜底:`store.looks_like_request_id(target)`
   ——即使值填在 `code` 字段里,只要长得像 request id 就走 request 路径。
2. **只有 code 路径有锁定。** `_is_locked_out` 只在 `not by_request_id` 时查。理由写在注释里:
   request id 是管理员从自己列表里拿的,不是猜的;拿它去撞一个因别的原因锁定的平台,报 429 是误导。
   ——这是"错误码要对齐用户心智模型"的一个干净样本。
3. **平台名强制小写**(`(body.platform or "").lower().strip()`),而 code 强制大写(`target.upper()`)。
   前者是存储键的归一,后者是配对码的字符集约定。
4. **成功返回 `{"ok": True, "user": <被批准用户对象>}`** —— 前端拿这个对象直接把行从 pending 挪到 approved,
   不用重新拉列表。

`hermes_cli/web_server.py:12357`
```python
@app.post("/api/pairing/revoke")
async def revoke_pairing(body: PairingRevoke):
    store = _pairing_store(body.profile)
    platform = (body.platform or "").lower().strip()
    if not platform or not body.user_id:
        raise HTTPException(status_code=400, detail="platform and user_id are required")
    if store.revoke(platform, body.user_id):
        return {"ok": True}
    raise HTTPException(
        status_code=404,
        detail=f"User {body.user_id} not found in approved list for {platform}.",
    )


@app.post("/api/pairing/clear-pending")
async def clear_pending_pairing(profile: Optional[str] = None):
    store = _pairing_store(profile)
    count = store.clear_pending()
    return {"ok": True, "cleared": count}
```
**revoke**:按 `(platform, user_id)` 从 approved 表里删,删不到就 404——**不是幂等**。
对比同一段里的 `DELETE /api/sessions/{id}`,它被明确做成了幂等,而且理由是一次真实事故:

`hermes_cli/web_routers/sessions.py:641`
```python
            # Resolve exact ids / unique prefixes like every other session endpoint
            # (detail, messages, rename, export all do). A session that no longer
            # exists is an idempotent success: DELETE's contract is "ensure it's
            # gone", and the desktop optimistically removes the row then RESTORES it
            # on any error — so a 404 on an already-absent row resurrected a ghost
            # row and surfaced "session not found". /goal + auto-compression churn
            # leaves transient empty rows (reaped by empty-session hygiene) that
            # race the sidebar snapshot, which is exactly when this fired. Mirrors
            # the bulk-delete endpoint, which already treats ghost ids as success.
```
两者取向不同是可辩护的(撤销授权是安全动作,"我以为撤了其实没撤"必须报错),但**同一个文件里两种 DELETE 语义**
值得在蓝图里写成一条明确原则。

**clear-pending**:清空 pending 表,返回清掉的条数;不碰 approved。

### 3.3 ◇ 「不填 profile」与「填 `default`」指向不同的配对库(已实测)

**成立。** 机制在两处:

`gateway/pairing.py:59`
```python
PAIRING_DIR = get_hermes_dir("platforms/pairing", "pairing")
```
这是**模块级常量**,在 import 期按当时的 `get_hermes_home()` 算死。而带 profile 的那条路径走的是
`get_default_hermes_root()`(见 §3.1 的 `:421` 引用),后者的语义是"**根**",不是"当前 home":

`hermes_constants.py:171`
```python
    In profile mode where ``HERMES_HOME`` is ``<root>/profiles/<name>``,
    returns ``<root>`` so that ``profile list`` can see all profiles.
```

于是在一个 `hermes -p work serve` 起的 dashboard 里:
- 不填 profile → `PAIRING_DIR` → `<root>/profiles/work/platforms/pairing`
- 填 `default` → `get_default_hermes_root()` → `<root>/platforms/pairing`

实测(探针 `/tmp/r8c_probe2.py`,`HERMES_HOME=<tmp>/profiles/work`):

```console
module PAIRING_DIR      : /tmp/r8c-home2-ioe2if1s/profiles/work/platforms/pairing
store(None)._dir        : /tmp/r8c-home2-ioe2if1s/profiles/work/platforms/pairing
store('default')._dir   : /tmp/r8c-home2-ioe2if1s/platforms/pairing
store('work')._dir      : /tmp/r8c-home2-ioe2if1s/profiles/work/platforms/pairing
no-profile == default ? : False
no-profile == work    ? : True
GET /api/pairing            -> [{'platform': 'telegram', 'request_id': '28aacb2dc8d0c074', 'user_id': 'u-here', 'user_name': 'Here', 'age_minutes': 0}]
GET /api/pairing?profile=default -> []
```

**定级 ◇(代码有、文档无),不是 ■。** 理由三条:

1. **有注释解释。** `_pairing_store` 的 docstring 明写 "the dashboard's own when unspecified" 与
   "(``default`` maps back to the global store)"(`hermes_cli/web_server.py:12289`/`:12296`),
   两句合起来正好描述了实测行为。类 docstring 也说了:

   `gateway/pairing.py:414`
   ```python
       When constructed with ``profile="<name>"``, storage resolves from that
       profile's own HERMES_HOME using the same legacy/consolidated layout rules
       as ``hermes -p <name> pairing ...``. This keeps multiplex gateways and
       profile-scoped CLI approvals on one whitelist. Without a profile, storage
       is the global pairing directory for the current HERMES_HOME.
   ```
   注意末句用词是 "the current HERMES_HOME"——**不是 "the root"**,与实测一致。

2. **语义上是对的。** "不填"= 这个进程自己;"default"= 那个叫 default 的 profile。在默认 home 的进程上两者重合,
   在命名 profile 的进程上分开,这正是多 profile dashboard 想要的。

3. **测试已经承认了 import 期绑定这件事**,并据此调整了断言写法:

   `tests/hermes_cli/test_dashboard_admin_endpoints.py:307`
   ```python
           # ...and it never leaked into the global store, whose own pending row
           # is still waiting. (Asserted against this user rather than an empty
           # list: the module-level PAIRING_DIR is bound at import, so the global
           # store carries whatever earlier cases in this class approved.)
           global_view = self.client.get("/api/pairing").json()
           assert PairingStore().is_approved("telegram", "work-1") is False
           assert "work-1" not in [row["user_id"] for row in global_view["approved"]]
           assert "global-1" in [row["user_id"] for row in global_view["pending"]]
   ```

**◇ 的"文档无"部分**(搜索面:`grep -rn "api/pairing" --include=*.md .`,命中 1 个文件):
`website/docs/user-guide/features/web-dashboard.md:527-530` 的 API 表**完全没有 `profile` 这个参数**,
且把 approve 的 body 写成 `{platform, code}`,而代码接受 `{platform, request_id|code, profile}`
且前端首选 `request_id`。文档滞后于代码。

**留给后续轮的一个未取证疑点**:`PAIRING_DIR` 是 import 期常量,意味着"不填 profile"这条路径**看不见**
运行期的 `set_hermes_home_override`。缓解手段是每次无 profile 构造都会跑一次目录合并:

`gateway/pairing.py:366`
```python
def _migrate_split_pairing_dirs(
    *,
    home: Optional[Path] = None,
    active: Optional[Path] = None,
) -> None:
    home = home or get_hermes_home()
    old_dir = home / "pairing"
    new_dir = home / "platforms" / "pairing"
    active = active or PAIRING_DIR
    alternate = new_dir if active.resolve() == old_dir.resolve() else old_dir
    _merge_pairing_dir(active, alternate)
```
所以 "legacy 目录后来才有内容" 那个分裂场景**大概率被治好了**,但我没有为此写探针。锚点见 §10。

### 3.4 ◇ profile 名大小写:cron 家族归一化,pairing 家族不归一化(已实测)

`hermes_cli/profiles.py:306`
```python
def normalize_profile_name(name: str) -> str:
    """Return the canonical profile id used on disk and in CLI ``-p`` argv.

    Named profiles are stored lowercase under ``profiles/<id>/``. The special
    alias ``default`` is matched case-insensitively (``Default`` → ``default``).
    Dashboards and tools may pass title-cased display labels; normalize before
    validation, assignment, and subprocess spawn (see issue #18498).
    """
    if not isinstance(name, str):
        name = str(name)
    stripped = name.strip()
    if not stripped:
        raise ValueError("profile name cannot be empty")
    if stripped.casefold() == "default":
        return "default"
    return stripped.lower()
```
这段 docstring 明确指示 "Dashboards and tools may pass title-cased display labels; **normalize before validation**"。
cron 家族照做了:

`hermes_cli/web_server.py:11647`
```python
def _cron_profile_home(profile: Optional[str]) -> Tuple[str, Path]:
    """Resolve a profile query value to (profile_name, HERMES_HOME)."""
    from hermes_cli import profiles as profiles_mod

    raw = (profile or _cron_default_profile()).strip() or "default"
    try:
        canon = profiles_mod.normalize_profile_name(raw)
        profiles_mod.validate_profile_name(canon)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not profiles_mod.profile_exists(canon):
        raise HTTPException(status_code=404, detail=f"Profile '{canon}' does not exist.")
    return canon, profiles_mod.get_profile_dir(canon)
```
`_resolve_profile_dir`(§3.1 引用)**直接 validate、不 normalize**。实测(探针 `/tmp/r8c_probe1.py`):

```console
/api/pairing?profile=work                -> 200  {"pending":[],"approved":[]}
/api/pairing?profile=Work                -> 400  {"detail":"Invalid profile name 'Work'. Must match [a-z0-9][a-z0-9_-]{0,63}"}
/api/cron/jobs?profile=work              -> 200  []
/api/cron/jobs?profile=Work              -> 200  []
```
影响面不止 pairing:`_profile_scope` / `_config_profile_scope` / `_installed_hub_identifiers`
都经 `_resolve_profile_dir`,即整个 MCP / skills / tools / profiles 族对 `?profile=Work` 一律 400。
定级 **◇**(不是 ■):前端只发它自己从 `/api/profiles` 拿到的小写名,所以线上不触发;
但对第三方调用方是一条不一致的 API 契约,且违背 `normalize_profile_name` 自己写的调用指引。

---

## 4. 凭据池(`:12564`–`:12728`):密钥值会不会被读回

### 4.1 结论:池端点本身**写得进、读不出**

`hermes_cli/web_server.py:12573`
```python
def _pool_entry_summary(entry: Any, index: int) -> Dict[str, Any]:
    """Redacted, display-safe view of one PooledCredential.

    ``index`` is 1-based to match CredentialPool.remove_index().
    """
    token = getattr(entry, "access_token", "") or ""
    return {
        "index": index,
        "id": getattr(entry, "id", None),
        "label": getattr(entry, "label", None),
        "auth_type": getattr(entry, "auth_type", None),
        "source": getattr(entry, "source", None),
        "priority": getattr(entry, "priority", 0),
        "last_status": getattr(entry, "last_status", None),
        "request_count": getattr(entry, "request_count", 0),
        "token_preview": redact_key(token) if token else "",
        "has_refresh": bool(getattr(entry, "refresh_token", None)),
    }
```
唯一涉及密文的字段是 `token_preview`,值来自 `redact_key` → `agent.redact.mask_secret`:

`agent/redact.py:442`
```python
def mask_secret(
    value: str,
    *,
    head: int = 4,
    tail: int = 4,
    floor: int = 12,
    placeholder: str = "***",
    empty: str = "",
) -> str:
```
即最多露头 4 尾 4,总长不足 `head+tail+floor` 时整条 `***`;`refresh_token` 连预览都没有,只出一个布尔。

`hermes_cli/web_server.py:12593`
```python
@app.get("/api/credentials/pool")
async def list_credential_pool():
    from agent.credential_pool import load_pool
    from hermes_cli.auth import read_credential_pool

    providers = []
    # read_credential_pool(None) lists every provider that has pooled entries;
    # load_pool() then gives us the rich PooledCredential objects per provider.
    raw_pool = read_credential_pool()
    for provider_id in sorted(raw_pool.keys()):
        try:
            pool = load_pool(provider_id)
        except Exception:
            _log.exception("load_pool(%s) failed", provider_id)
            continue
        entries = pool.entries()
        if not entries:
            continue
        providers.append({
            "provider": provider_id,
            "entries": [
                _pool_entry_summary(e, i) for i, e in enumerate(entries, start=1)
            ],
        })
    return {"providers": providers}
```
`raw_pool`(auth.json 里的原始 dict)**只用来取 provider 名**(`raw_pool.keys()`),从不进响应体。
POST 只回 `{"ok", "provider", "count"}`,DELETE 只回 `{"ok","provider","count","cleaned","hints"}`
(`cleaned`/`hints` 来自 RemovalStep,是"清了哪个外部文件 / 还要手工做什么"的文本,不含密钥)。

**auth.json 本身也被 Files API 拉黑:**

`hermes_cli/web_server.py:1769`
```python
_SENSITIVE_MANAGED_FILE_BASENAMES = frozenset({
    "auth.json",
    "auth.lock",
    "credentials",
    "config.yaml",
    ".anthropic_oauth.json",
```
且 `.env` 由前缀规则拦下:

`hermes_cli/web_server.py:1815`
```python
    lowered = name.lower()
    if lowered == ".env" or lowered.startswith(".env.") or lowered == ".envrc":
        return True
    return lowered in _SENSITIVE_MANAGED_FILE_BASENAMES
```

**负结论 + 搜索面**:在 `hermes_cli/web_server.py`(17,732 行)与 `hermes_cli/web_routers/*.py`(全部 7 个模块)
上 grep `credential_pool|credentials/pool|read_credential_pool|access_token`,凭据池相关命中全部落在
`:12567`–`:12727` 这一块内,**没有任何一处把 `access_token` / `refresh_token` 原值放进响应**;
`redact_key` 在 web_server 内共 5 处调用(`:7053`、`:7197`、`:8310`、`:12068`、`:12588`),全是"出站前打码"。

### 4.2 ◇ 但同一段里有两条**旁路**能把同样的密钥读回来

**旁路一(设计上的、有额外加固):`POST /api/env/reveal`。** 池条目的 `source` 可以是一个 `.env` 变量
(`load_pool()` 会从 `.env` 反复 re-seed,见 §4.3),那个变量的**原值**是可以被读回的:

`hermes_cli/web_server.py:7597`
```python
@app.post("/api/env/reveal")
async def reveal_env_var(
    body: EnvVarReveal, request: Request, profile: Optional[str] = None
):
    """Return the real (unredacted) value of a single env var.

    Protected by:
    - Ephemeral session token (generated per server start, injected into SPA)
    - Rate limiting (max 5 reveals per 30s window)
    - Audit logging
    """
```
这是**有意为之**且三重加固(token + 5次/30秒限流 + 审计日志)。注意它读的是 `.env`,
所以经 `POST /api/credentials/pool` 写进 **auth.json** 的那把手工 key 读不回来。

**旁路二(◇,无额外加固):`/api/ops/backup` + `/api/ops/backup/download`。**
备份包**逐字**含 `.env` 与 `auth.json`,而默认输出目录正是 download 端点允许的目录。实测(探针 `/tmp/r8c_probe6.py`):

```console
members: ['.env', 'auth.json', 'config.yaml']
  .env: PRESENT -> b'OPENAI_API_KEY=sk-live-SECRET-0123456789\n'
  auth.json: PRESENT -> b'{"credential_pool": {"openai": [{"id": "aaa", "access_token": "sk-pool'
  config.yaml: PRESENT -> b'model:\n  provider: openai\n'
download dir     : /tmp/r8c-home6-ocoeh6a2/backups
archive under it : True
```
即:**凭据池端点自己守住了"写得进读不出"的形状,但 Ops 簇在同一鉴权面上把整个凭据库打包下发。**
两者共用同一道中间件门,所以从威胁模型看,`token_preview` 的打码在"会话令牌已泄露"这个场景下不提供额外保护。
(不定级 ■:备份下载对运维是刚需,且路径被限制在 `~/.hermes/backups`;但这条**跨簇**的等价关系没有任何注释或文档提到,
故记 ◇,并建议 R12 蓝图把它写成一条"备份端点即最高权限端点"的设计原则。)

### 4.3 顺带:DELETE 为什么要 suppress

`hermes_cli/web_server.py:12672`
```python
@app.delete("/api/credentials/pool/{provider}/{index}")
async def remove_credential_pool_entry(provider: str, index: int):
    """Remove a pool entry.  ``index`` is 1-based (matches the list response).

    Removal must be sticky (#55217): ``load_pool()`` re-seeds entries from
    their backing source (.env var, OAuth singleton file, custom-provider
    config) on every call, so deleting only the pool row silently reverts on
    the next dashboard refresh.  We dispatch through the same RemovalStep
    registry the CLI ``hermes auth remove`` uses: each source cleans up its
    external state and suppresses ``(provider, source)`` so the seeders skip
    it.  Manual entries have no registered step — nothing external to clean,
    no suppression needed (they aren't re-seeded).
    """
```
这是本段里最值得抄的一条设计教训:**池是"投影"不是"真相"**——真相分散在 `.env`、OAuth 单例文件、
custom provider 配置里,`load_pool()` 每次都重新投影。所以"删一行"必须翻译成"在源头上清理 + 登记抑制",
否则下一次刷新它自己长回来。并且抑制是**先于**清理保证的:

`hermes_cli/web_server.py:12709`
```python
        except Exception:
            # Cleanup is best-effort, but suppression is the actual bug fix —
            # without it the entry resurrects on the next load_pool().  Apply
            # it even when source-specific cleanup blew up.
```
对称地,POST 会**解除**该 provider 的全部抑制(`:12649`–`:12663`),语义是"重新加一把 key = 明确的再启用信号"。

---

## 5. Operations(`:12799`–`:13180`):backup / import 到底打包与还原什么

### 5.1 backup 打包什么

`hermes_cli/web_server.py:12832`
```python
def _dashboard_backup_dir() -> Path:
    return get_hermes_home() / "backups"


def _new_dashboard_backup_path() -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return _dashboard_backup_dir() / f"hermes-backup-{stamp}-{secrets.token_hex(4)}.zip"


@app.post("/api/ops/backup")
async def run_backup(body: BackupRequest):
    args = ["backup"]
    archive: Optional[Path] = None
    output = (body.output or "").strip()
    if output:
        args.extend(["-o", output])
    else:
        archive = _new_dashboard_backup_path()
        try:
            archive.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Could not create backup directory: {exc}",
            )
        args.extend(["-o", str(archive)])
    try:
        proc = _spawn_hermes_action(args, "backup")
    except Exception as exc:
        _log.exception("Failed to spawn backup")
        raise HTTPException(status_code=500, detail=f"Failed to run backup: {exc}")
    response = {"ok": True, "pid": proc.pid, "name": "backup"}
    if archive is not None:
        response["archive"] = str(archive)
    return response
```
端点自己不打包,只是 spawn `hermes backup -o <path>`。**真正的范围由 `hermes_cli/backup.py` 定义:
整个 HERMES_HOME 根目录**(`get_default_hermes_root()`,故包含 `profiles/*` 全部子 profile),
排除项只有"可再生的东西":

`hermes_cli/backup.py:51`
```python
_EXCLUDED_DIRS = {
    "hermes-agent",     # the codebase repo — re-clone instead
    "__pycache__",      # bytecode caches — regenerated on import
```
`.env` / `auth.json` / `state.db` **都不在排除表里**——排除的文件名只有三个:

`hermes_cli/backup.py:88`
```python
_EXCLUDED_NAMES = {
    ".backup.lock",
    "gateway.pid",
    "cron.pid",
}
```
外加:符号链接一律跳过(`_should_skip_backup_file`,`hermes_cli/backup.py:325`,注释 "zipfile.write() follows
file symlinks, so skip links before any archive write can copy data from outside HERMES_HOME");
`*.db` 走 `sqlite3.backup()` 一致快照,`.db-wal/.db-shm/.db-journal` 剔除;
以及一个**保留前缀 `_external/`**,用来把 HERMES_HOME 之外的 memory provider 状态(`~/.honcho` 等)
按"相对 $HOME"编码打进包里(`hermes_cli/backup.py:135`)。

§4.2 的探针已实证 `.env` / `auth.json` / `config.yaml` 逐字进包。

**下载端点是**严格**限制在备份目录内的:**

`hermes_cli/web_server.py:12869`
```python
@app.get("/api/ops/backup/download")
async def download_dashboard_backup(archive: str):
    try:
        backup_dir = _dashboard_backup_dir().expanduser().resolve(strict=False)
        target = Path(archive).expanduser().resolve(strict=True)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup not found")
    except (OSError, RuntimeError):
        raise HTTPException(status_code=400, detail="Invalid backup path")

    if not _path_is_under(backup_dir, target):
        raise HTTPException(status_code=403, detail="Backup is outside the dashboard backup directory")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Backup not found")

    return FileResponse(
        path=str(target),
        media_type="application/zip",
        filename=target.name,
        content_disposition_type="attachment",
    )
```
`resolve(strict=True)` 在**比较之前**做,所以 `../` 与符号链接都被压平后再判定——写法是对的。

### 5.2 import 会覆盖什么:**会覆盖凭据与配置**

`hermes_cli/web_server.py:12892`
```python
@app.post("/api/ops/import")
async def run_import(body: ImportRequest):
    archive = (body.archive or "").strip()
    if not archive:
        raise HTTPException(status_code=400, detail="archive path is required")
    if not os.path.isfile(archive):
        raise HTTPException(status_code=404, detail=f"Archive not found: {archive}")
    args = ["import", archive]
    if body.force:
        args.append("--force")
    try:
        proc = _spawn_hermes_action(args, "import")
    except Exception as exc:
        _log.exception("Failed to spawn import")
        raise HTTPException(status_code=500, detail=f"Failed to run import: {exc}")
    return {"ok": True, "pid": proc.pid, "name": "import"}
```

还原目标是**根**,不是当前 profile:

`hermes_cli/backup.py:869`
```python
    hermes_root = get_default_hermes_root()
```

覆盖是**逐文件直写、无备份、无 diff**:

`hermes_cli/backup.py:969`
```python
            target = hermes_root / rel

            # Security: reject absolute paths and traversals
            try:
                target.resolve().relative_to(hermes_root.resolve())
            except ValueError:
                errors.append(f"  {rel}: path traversal blocked")
                continue

            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                if target.name in _SECRET_FILE_NAMES:
                    os.chmod(target, 0o600)
                restored += 1
```
`_SECRET_FILE_NAMES` 就是被覆盖的那三个:

`hermes_cli/backup.py:119`
```python
_IMPORT_SKIP_NAMES = {
    "gateway_state.json",
    "gateway.pid",
    "cron.pid",
    "gateway.lock",
    "processes.json",
}

# zipfile.open() drops Unix mode bits on extract; restore tightens these to 0600.
_SECRET_FILE_NAMES = {".env", "auth.json", "state.db"}
```
即:**`.env`、`auth.json`、`state.db`、`config.yaml` 全部被包里的版本原样覆盖**,
唯一豁免的是 `_IMPORT_SKIP_NAMES` 那五个"跟机器绑定的运行时状态"(理由写在 `hermes_cli/backup.py:94`–`117`:
`gateway_state.json` 会驱动容器启动协调器,还原一个别的机器上的值会让网关卡在 starting 并从 Nous portal 掉线,NS-508)。
另外 `_external/` 成员会写到 **HERMES_HOME 之外**,落在 `$HOME` 相对位置(有 `relative_to(home_dir)` 约束)。

**"会不会覆盖"的另一半:非 `--force` 时其实跑不起来。**

`hermes_cli/backup.py:888`
```python
        # Check for existing installation
        has_config = (hermes_root / "config.yaml").exists()
        has_env = (hermes_root / ".env").exists()

        if (has_config or has_env) and not args.force:
            print()
            print("Warning: Target directory already has Hermes configuration.")
            print("Importing will overwrite existing files with backup contents.")
            print()
            try:
                answer = input("Continue? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                sys.exit(1)
            if answer not in {"y", "yes"}:
                print("Aborted.")
                return
```
而 dashboard 把子进程的 stdin 接到了 `/dev/null`:

`hermes_cli/web_server.py:3813`
```python
    popen_kwargs: Dict[str, Any] = {
        "cwd": str(PROJECT_ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
        "env": {**action_env, **(env_overrides or {})},
    }
```
所以 `input()` 立刻 EOFError → 打印 "Aborted." → `sys.exit(1)`。这条链路作者自己在模型上写清楚了:

`hermes_cli/web_models.py:495`
```python
class ImportRequest(BaseModel):
    archive: str
    # Pass --force to `hermes import`. The spawned action runs with
    # stdin=DEVNULL, so the CLI's interactive "Continue? [y/N]" overwrite
    # prompt hits EOF and auto-aborts ("Aborted.", exit 1) whenever the
    # target already has a config — which it always does when the dashboard
    # itself is running from it. The dashboard shows its own confirm modal
    # before calling this endpoint, then sends force=True so the restore
    # proceeds non-interactively.
    force: bool = False
```
**结论:确认闸门被从 CLI 移到了浏览器。** 这是一个诚实但值得记的取舍——服务端不再有"你确定吗"这一层,
`force=true` 就是全部授权。

### 5.3 来源校验有多弱

`hermes_cli/backup.py:806`
```python
def _validate_backup_zip(zf: zipfile.ZipFile) -> tuple[bool, str]:
    """Check that a zip looks like a Hermes backup.

    Returns (ok, reason).
    """
    names = zf.namelist()
    if not names:
        return False, "zip archive is empty"

    # Look for telltale files that a hermes home would have
    markers = {"config.yaml", ".env", "state.db"}
    found = set()
    for n in names:
        # Could be at the root or one level deep (if someone zipped the directory)
        basename = Path(n).name
        if basename in markers:
            found.add(basename)

    if not found:
        return False, (
            "zip does not appear to be a Hermes backup "
            "(no config.yaml, .env, or state databases found)"
        )

    return True, ""
```
**全部校验就是这个。** 没有清单文件、没有版本号、没有校验和、没有签名、不检查是不是本机产出。
条件是"**任意路径下出现过 `config.yaml`/`.env`/`state.db` 之一的 basename**"——
一个只含 `whatever/deep/.env` 的 zip 就通过。上传路径额外多两道:文件名消毒 + zip 魔数:

`hermes_cli/web_server.py:12974`
```python
    if not zipfile.is_zipfile(target):
        target.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="Uploaded archive is not a valid zip file",
        )

    args = ["import", str(target)]
    if force:
        args.append("--force")
    try:
        proc = _spawn_hermes_action(args, "import")
    except Exception as exc:
        _log.exception("Failed to spawn import")
        raise HTTPException(status_code=500, detail=f"Failed to run import: {exc}")
```
路径遍历本身是防住的(`relative_to(hermes_root.resolve())`,§5.2 引用),`_external/` 分支也有
`relative_to(home_dir)`(`hermes_cli/backup.py:928`)。**真正的风险不是路径遍历,是内容置换**:
一个通过校验的 zip 可以把 `.env` / `auth.json` / `config.yaml` / `hooks:` 块整体换掉,
而 hooks 块的语义是"下次会话/网关重启时执行任意 shell 命令"(见 `hermes_cli/web_server.py:13046` 的
`create_hook` docstring:"Shell hooks run arbitrary commands, so this is a privileged action")。

### 5.4 ◇ 两条路径策略在同一簇里不对称

- **读**(`/api/ops/backup/download`)严格限制在 `<home>/backups/` 之内,越界 403。
- **写/还原**(`/api/ops/import`)接受**任意本地绝对路径**,只做 `os.path.isfile(archive)`(`:12897`),
  **不要求**在备份目录内。
- **产出**(`/api/ops/backup` 的 `body.output`)也接受任意路径(`:12846`–`:12847`),
  即"把含 `.env`+`auth.json` 的 zip 写到进程能写的任何地方"。

三者在同一道鉴权面之后,却用了三种不同的路径策略。定级 ◇(而非 ■):都在已鉴权之后,
且 import/backup 走 CLI 参数、不是 shell 拼接;但"download 收紧、import/backup 不收紧"这件事
没有任何注释解释,读代码的人会误以为整簇都被 `_path_is_under` 罩着。

### 5.5 ◇ 两个端点在全仓 1,492 个 md 里 0 提及

```verify
搜索面:grep -rn "import-upload\|backup/download" --include=*.md .   → 0 命中
        find . -name "*.md" -not -path "*/node_modules/*" | wc -l   → 1492
文档现状:website/docs/user-guide/features/web-dashboard.md:541 只写
        "| POST /api/ops/doctor · /security-audit · /backup · /import | Diagnostics & maintenance (backgrounded) |"
        —— 没有 /api/ops/backup/download,没有 /api/ops/import-upload,
           没有提 import 会覆盖 .env / auth.json / config.yaml,没有提 force 的语义。
```

---

## 6. Cron 端点 ↔ `cron/scheduler.py`

### 6.1 dashboard 建的任务落到哪

**落到 `<该 profile 的 HERMES_HOME>/cron/jobs.json`。** 链路:
`POST /api/cron/jobs` → `_run_cron_dashboard_io(_create_cron_job_sync, body, profile)`
→ `_call_cron_for_profile(profile_name, "create_job", ...)` → `use_cron_store(home)` 把
`jobs_file` 改写成 `home/cron/jobs.json`(§1.2 已引用 `cron/jobs.py:171`)。

实测(探针 `/tmp/r8c_probe4.py`,`HERMES_HOME=<tmp>/profiles/work`,不带 `?profile=`):
```console
POST /api/cron/jobs           -> 200 {"id": "4d832b6e75b3", "name": "plain-job", ...}
root  jobs.json: (absent)
work  jobs.json: EXISTS ['plain-job']
```
返回的 job 对象会被 `_annotate_cron_job` 补上 `profile` / `profile_name` / `hermes_home` /
`is_default_profile` 四个字段(`hermes_cli/web_server.py:11662`),前端靠它做"这条任务属于谁"的显示与后续路由。

**任务的运行历史**不在 cron 侧,而在 sessions 侧——每次 run 就是一条普通 session:

`hermes_cli/web_server.py:11769`
```python
def _list_cron_job_runs_sync(job_id: str, profile: Optional[str] = None, limit: int = 20):
    """Run sessions produced by a cron job, newest first.

    Cron runs are stored as ordinary sessions whose id is
    ``cron_{job_id}_{timestamp}`` (see cron/scheduler.run_job). A job's history
    is therefore every session whose id carries that prefix; ``source='cron'``
    narrows it and the id prefix binds it to this job. Powers the run-history
    list under each job in the desktop cron detail. Same row shape as
    ``/api/sessions`` so the frontend can reuse SessionInfo.

    Backed by ``SessionDB.list_cron_job_runs`` — a bounded ``[prefix, hi)``
    id-range scan, not the compression-chain CTE used for the recents list,
    so the cost scales with the requested window and not the (unbounded) total
    cron history.
    """
```
docstring 里的 id 格式与实现一致:

`cron/scheduler.py:3030`
```python
    _cron_session_id = f"cron_{job_id}_{_hermes_now().strftime('%Y%m%d_%H%M%S')}"
```
这是一个漂亮的"**用 id 前缀当索引**"设计:不需要给 sessions 表加外键,一次 `[prefix, hi)` 范围扫描就是历史。

**找 job 属于哪个 profile 靠遍历**:`_find_cron_job_profile`(`hermes_cli/web_server.py:11699`)
逐个 profile 调 `list_jobs`,按 `id` 或 `name` 命中即返回。代价是 O(profiles) 次文件 I/O——
所以每个端点都用 `_run_cron_dashboard_io`(threadpool)把它挪出事件循环。

### 6.2 `/api/cron/fire` 为什么在免鉴权名单里

`hermes_cli/web_routers/cron.py:124`
```python
@router.post("/api/cron/fire")
async def cron_fire_webhook(request: Request):
    """Chronos managed-cron fire webhook (NAS -> agent).

    Authenticated by a short-lived NAS-minted JWT (verified by the pluggable
    Chronos fire-verifier), NOT the dashboard session cookie — so this path is
    in ``PUBLIC_API_PATHS`` to bypass the dashboard auth gate, and the JWT is
    the real gate. This is the inbound half of scale-to-zero managed cron: NAS
    POSTs here at fire time, the agent verifies, claims the job (store CAS, so
    at-most-once across replicas / on a NAS retry), runs it, and re-arms the
    next one-shot.

    Lives on the dashboard app (not the api_server adapter) because the
    dashboard is the agent's always-reachable public HTTP surface on hosted
    deployments; the gateway may be idle/scaled down.

    Returns 202 immediately and runs the job in the background so a long agent
    turn never trips NAS's HTTP timeout.
    """
    from plugins.cron_providers.chronos.verify import get_fire_verifier

    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""

    cfg = load_config()
    claims = get_fire_verifier()(
        token=token,
        expected_audience=cfg_get(cfg, "cron", "chronos", "expected_audience", default=""),
        jwks_or_key=cfg_get(cfg, "cron", "chronos", "nas_jwks_url", default="") or None,
        issuer=cfg_get(cfg, "cron", "chronos", "portal_url", default="") or None,
    )
    if claims is None:
        return JSONResponse({"error": "invalid fire token"}, status_code=401)
```

**这条设计要讲清楚的是"为什么免鉴权不等于无鉴权"。** 拆成五步:

**第一步:调用方不是浏览器。** 这是 "scale-to-zero managed cron"——定时器不在 agent 里跑,
在 NAS(Nous account service)那边;到点了 NAS 反向 POST 进来。NAS 手上没有、也不该有 dashboard 的会话 cookie。

**第二步:cookie 门会在 verifier 之前把它打掉。** dashboard 的两道门都是"路径不在白名单就 401":

`hermes_cli/web_server.py:665`
```python
    if path.startswith("/api/") and path not in _PUBLIC_API_PATHS and not is_mcp_oauth_callback:
        if not _has_valid_session_token(request) and not _has_valid_query_token(request, path):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized"},
            )
```
所以不进白名单,NAS 的 bearer-only 回调**永远到不了 JWT 校验那一行**。

**第三步:白名单条目自己声明了"这里的安全边界是 JWT 不是名单"。**

`hermes_cli/dashboard_auth/public_paths.py:54`
```python
    # Chronos managed-cron fire webhook (NAS -> agent). NOT cookie-gated: it
    # carries its own short-lived NAS-minted JWT (purpose=cron_fire), which the
    # handler verifies as the real auth. Must bypass the dashboard auth gate so
    # the NAS relay's bearer-only callback reaches the verifier instead of a
    # 401 no_cookie. The JWT — not this allowlist — is the security boundary.
    "/api/cron/fire",
})
```
这个文件本身的存在也有故事:两道中间件曾各存一份白名单,漂移后 `/api/status` 在旧门下公开、
在 OAuth 门下 401,导致 portal 的存活探测把所有健康实例报成 STARTING(`public_paths.py:11`–`17`)。
现在合成一份 frozenset,并附三条自检:能给外部探测器看吗?能给未登录的 SPA 看吗?能给随手 curl 的人看吗?
——`/api/cron/fire` 通过这三条**不是因为它无害**,而是因为它自带门。

**第四步:verifier 默认 fail-closed(◎)。** 未配置 `expected_audience` / `nas_jwks_url` 时直接拒:

`plugins/cron_providers/chronos/verify.py:101`
```python
    if not token or not expected_audience:
        return None
    if not jwks_or_key:
        # No verification key configured → cannot verify → refuse. We never
        # fall back to unsigned decode for a security boundary.
        logger.warning("cron fire: no JWKS/key configured; refusing token")
        return None
```
校验项是签名(RS/ES 家族,拒对称密钥)、`aud`、`exp`/`nbf`(30s leeway)、`iss`,
外加一个 `purpose == "cron_fire"` 声明——**目的是让一枚通用 agent JWT 不能被重放到这个端点上**
(`plugins/cron_providers/chronos/verify.py:27`–`29`)。
默认配置下 `cron.chronos.expected_audience` 为空 ⇒ 任何 token 都 401 ⇒ 这条公开路径默认零攻击面。
定级 ◎(文档成立但保守):白名单文件的注释说"JWT 是边界",没说"未配置时整条路径等于关闭",而后者才是默认态。

**第五步:幂等由 store CAS 保证,不是由 HTTP 保证。** handler 只做 202 + 后台跑;去重在 `fire_due` 里:

`cron/scheduler_provider.py:103`
```python
        from cron.jobs import claim_job_for_fire, get_job
        from cron.executions import create_execution
        from cron.scheduler import run_one_job

        if not claim_job_for_fire(job_id):
            return False  # another machine already claimed this fire
        job = get_job(job_id)
        if job is None:
            return False  # job removed (e.g. repeat-N exhausted) between arm and fire
        job["execution_id"] = create_execution(job_id, source=self.name)["id"]
        return run_one_job(job, adapters=adapters, loop=loop)
```

`cron/jobs.py:2024`
```python
def claim_job_for_fire(job_id: str, *, claim_ttl_seconds: int = 300) -> bool:
    """Atomically claim a job for a single external 'fire' (multi-machine
    at-most-once). Returns True iff THIS caller won the claim.

    Used by the external-provider fire path (``CronScheduler.fire_due``) when an
    external scheduler (Chronos) signals a job is due across N gateway replicas:
    exactly one wins. Single-machine deployments always win.
```
以及一条"job 已经不在了就回 200 不回 404"的选择,理由是**不让 NAS 重试一个故意不存在的 fire**:

`hermes_cli/web_routers/cron.py:171`
```python
        # Job is gone (cancelled / completed) — nothing to fire. 200 so NAS
        # does not retry a fire that is intentionally absent.
        return JSONResponse({"status": "gone", "job_id": job_id}, status_code=200)
```

**第六步:真正执行时把两样上下文一起换。**

`hermes_cli/web_server.py:11945`
```python
def _fire_cron_job_for_profile(profile: str, job_id: str) -> bool:
    """Run ONE due cron job end-to-end for ``profile`` via the resolved
    scheduler provider's ``fire_due`` (store CAS claim + ``run_one_job``).

    Scope both cron storage and the runtime Hermes home so the job's store,
    config, credentials, scripts, skills, and output all belong to the selected
    profile. Runs with no live adapters; delivery falls back to the per-platform
    send path.
    """
    _profile_name, home = _cron_profile_home(profile)
    from cron import jobs as cron_jobs
    from cron.scheduler_provider import resolve_cron_scheduler
    from hermes_constants import (
        reset_hermes_home_override,
        set_hermes_home_override,
    )

    token = set_hermes_home_override(str(home))
    try:
        with cron_jobs.use_cron_store(home):
            provider = resolve_cron_scheduler()
            return bool(provider.fire_due(job_id, adapters=None, loop=None))
    finally:
        reset_hermes_home_override(token)
```

**一条观察(未定级,交后续轮):** JWT 是拿 **dashboard 自己 profile 的** `cron.chronos.*` 配置校验的
(`load_config()` 无 profile scope,`hermes_cli/web_routers/cron.py:148`),而 `_find_cron_job_profile`
会跨**所有** profile 找 job。即一枚对本进程有效的 fire token 可以触发任意 profile 的任务。
考虑到 chronos 的信任模型是"一个 NAS ↔ 一个 agent 容器",这大概率是有意的;但代码里没有注释说明,
我也没有找到测试断言它。锚点见 §10。

### 6.3 ■(潜在)两个 cron 创建端点对"没传 profile"给出不同答案

`_cron_default_profile` 的 docstring **专门**解释了为什么不能硬编码 `"default"`:

`hermes_cli/web_server.py:11627`
```python
def _cron_default_profile() -> str:
    """Profile to target when a cron request carries no explicit ``profile``.

    A desktop pool backend runs one process per profile (HERMES_HOME already
    scoped), but these cron endpoints deliberately route storage through the
    profiles tree via ``_cron_profile_home`` — so a hardcoded ``"default"``
    fallback would write a non-default profile's job into ``~/.hermes``.
    Resolve the process's own profile instead. ``custom`` (an unrecognized
    HERMES_HOME outside the profiles tree) has no profile-dir equivalent, so
    it keeps the legacy ``default`` fallback.
    """
    try:
        from hermes_cli.profiles import get_active_profile_name

        name = get_active_profile_name()
    except Exception:
        return "default"
    return "default" if name in ("default", "custom") else name
```

但同一个 router 里的蓝图实例化端点,签名就是那个被点名的硬编码回退:

`hermes_cli/web_routers/cron.py:217`
```python
@router.post("/api/cron/blueprints/instantiate")
async def instantiate_blueprint(body: AutomationBlueprintInstantiate, profile: str = "default"):
    """Fill a blueprint's slots and create the cron job (form-submit path)."""
    try:
        from cron.blueprint_catalog import fill_blueprint, get_blueprint, BlueprintFillError

        blueprint = get_blueprint(body.blueprint)
        if blueprint is None:
            raise HTTPException(status_code=404, detail=f"Unknown blueprint: {body.blueprint}")
        try:
            spec = fill_blueprint(blueprint, body.values)
        except BlueprintFillError as exc:
            # Field-level validation error — 422 so the form can show it inline.
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # Blueprint-created jobs deliver to the dashboard's configured target by
        # default; the form's deliver slot overrides via spec["deliver"].
        spec.pop("origin", None)
        # create_job does per-profile file I/O — keep it off the event loop
        # like the sibling cron endpoints (partial avoids **spec keys ever
        # colliding with the wrapper's own parameters).
        _create = functools.partial(_call_cron_for_profile, profile, "create_job", **spec)
        return await _run_cron_dashboard_io(_create)
```
对照 `create_cron_job` 的签名是 `profile: Optional[str] = None`(`hermes_cli/web_routers/cron.py:67`)。

**实测(探针 `/tmp/r8c_probe5.py`,`HERMES_HOME=<tmp>/profiles/work`,两次都不带 `?profile=`):**
```console
POST /api/cron/jobs                   -> 200   → work/cron/jobs.json  ['plain-job']
POST /api/cron/blueprints/instantiate -> 200   → root/cron/jobs.json  ['Morning briefing']
                                                  work/cron/jobs.json (absent)
```

**失效链:** 用户在 `-p work` 的 dashboard 上点一个蓝图 → 任务写进 `~/.hermes/cron/jobs.json`
→ `work` 的 ticker 读的是 `~/.hermes/profiles/work/cron/jobs.json`,永远看不到它
→ 若没有任何进程服务 `default` profile,这个任务**永不触发**;
而 `GET /api/cron/jobs?profile=all` 会跨 profile 列出来并标 `profile: "default"`,
所以 UI 上"任务在那儿"、实际"从不运行"。

**为什么标(潜在)而不是直接 ■:** 两个官方前端都**显式**传值,且把 "all" 折叠成 "default":
`web/src/pages/CronPage.tsx:792` 传 `selectedProfile === "all" ? "default" : selectedProfile`;
`apps/desktop/src/app/cron/index.tsx:458` 同样。所以 SPA/桌面路径不触发。
触发面是**任何不经 SPA 的调用方**(curl、插件、桌面池后端的其它代码路径),以及"all 折叠成 default"
这条 UI 约定本身在命名 profile 后端上也会把任务写到 root。修法一行:把签名改成
`profile: Optional[str] = None`,与 `create_cron_job` 对齐。

### 6.4 ■ `_profile_cli_args("default")` 与同名参数在别处的含义相反

`hermes_cli/web_server.py:13192`
```python
def _profile_cli_args(profile: Optional[str]) -> List[str]:
    """Return ``["-p", <name>]`` for a validated non-default profile.

    Hub install/uninstall/update run in a fresh ``hermes`` subprocess, and
    ``_apply_profile_override()`` reads ``-p`` from argv in the child — the
    only mechanism that reaches import-time-bound globals like
    ``skills_hub.SKILLS_DIR``. Empty/"current" means the dashboard's own
    profile (no args, legacy behavior).
    """
    requested = (profile or "").strip()
    if not requested or requested.lower() in {"current", "default"}:
        return []
    from hermes_cli import profiles as profiles_mod
    _resolve_profile_dir(requested)
    return ["-p", profiles_mod.normalize_profile_name(requested)]
```
**docstring 说 "Empty/`current` 表示 dashboard 自己的 profile",代码却把 `"default"` 也归进这一组。**

实测(探针 `/tmp/r8c_probe3.py`,`HERMES_HOME=<tmp>/profiles/work`):
```console
process home                    : /tmp/r8c-home3-iafnwg8h/profiles/work
_profile_cli_args('default')    : []
_profile_cli_args('work')       : ['-p', 'work']
_profile_cli_args(None)         : []
inside _profile_scope('default'): /tmp/r8c-home3-iafnwg8h
inside _profile_scope(None)     : /tmp/r8c-home3-iafnwg8h/profiles/work
_cron_profile_home('default')   : ('default', PosixPath('/tmp/r8c-home3-iafnwg8h'))
_cron_default_profile()         : work
```
即在同一个进程里,`profile="default"`:
- 经 `_profile_scope` / `_cron_profile_home` → **根**(`<root>`)
- 经 `_profile_cli_args` → **空参数** → 子进程沿用 `HERMES_HOME=<root>/profiles/work` → **work**

**失效链(本段内的两个受害端点):**

`hermes_cli/web_server.py:3888`
```python
def _gateway_subcommand(profile: Optional[str], verb: str) -> List[str]:
    return _profile_cli_args(profile) + ["gateway", verb]
```
⇒ 在 `-p work` 的 dashboard 上,`POST /api/gateway/start?profile=default`(`:12540`)
spawn 的是 `hermes gateway start`(无 `-p`)。子进程的 `_apply_profile_override()` 在没有 `-p` 且
`HERMES_HOME` 的父目录名是 `profiles` 时**直接信任环境变量返回**(`hermes_cli/main.py:632`–`635`),
于是**启动的是 work 的网关,不是 default 的**。用户以为自己启了另一个 profile 的网关。

`hermes_cli/web_routers/mcp.py:445`
```python
    if entry.install is not None:
        # Unique per-entry action name: a shared "mcp-install" would let a
        # re-click (or a second entry) overwrite the tracked process/log while
        # the first clone is still running.
        action = _mcp_install_action_name(name)
        try:
            _spawn_hermes_action(
                _profile_cli_args(effective_profile) + ["mcp", "install", name],
                action,
            )
```
⇒ **同一个 handler 的两条分支对 `profile=default` 给出不同目标**:需要 git bootstrap 的条目走上面这条
(装进 work),不需要的走下面的 `with _profile_scope(effective_profile)`(装进 root,
`hermes_cli/web_routers/mcp.py:467`–`469`)。同一次点击、同一个参数、两个不同的 profile。

同一个 bug 还波及 `web_routers/skills.py:62,82,100` 与 `web_routers/tools.py:618,725`(不在本段范围内,列此备查)。
修法:`_profile_cli_args` 对 `"default"` 返回 `["-p", "default"]`(`hermes -p default` 是合法的,
`hermes_cli/profiles.py:339` 的 `validate_profile_name` 把 `default` 当特殊别名放行,
`normalize_profile_name` 也把它归一到 `"default"`),或至少在 docstring 里写明它被当作"本进程"。

---

## 7. 其余各块的关键点(简)

**MCP OAuth 飞行登记表(`:12122`–`:12274`)。** 三层并发控制:全局 TTL 15 分钟 + GC(`_gc_mcp_oauth_flows`)、
待完成流上限 8(超出 429)、同一 `(home, server)` 同时只允许一个(重复 409)。
`_mcp_oauth_transaction` 再按 `(hermes_home, server_name)` 发一把进程内锁,保证同一台服务器的
token 写入互斥。失败路径做**双向回滚**:`storage.restore(backup, only_if_absent=True)` +
`manager.restore_entry(...)`(`hermes_cli/web_server.py:12220`–`12227`)。

**MCP test 端点为什么不用 `_profile_scope`。** 这是本段里最好的"锁粒度事故"教材:

`hermes_cli/web_routers/mcp.py:157`
```python
    def _probe_scoped():
        # Home-only scope (contextvar), NOT _profile_scope. A probe blocks for
        # as long as the server takes to spawn/connect — a stdio `npx` cold
        # start is many seconds — and _profile_scope holds a process-global
        # skills lock for its ENTIRE body. Holding that across the probe
        # serialized every other endpoint (config/skills/toolsets all take the
        # same lock), so a slow server made unrelated requests time out at 15s.
        # The probe touches no skills globals; it only needs the HERMES_HOME
        # override for .env interpolation + OAuth token resolution, which the
        # contextvar provides (copied into this to_thread worker; and
        # _run_on_mcp_loop re-wraps it onto the MCP event-loop thread).
        with _config_profile_scope(profile):
            tools = _probe_single_server(name, servers[name], details=details)
            token_present = _oauth_tokens_present(name) if needs_oauth_token else True
            return tools, token_present

```
另一处细节:`auth: oauth` 的服务器即使匿名 `tools/list` 成功也要求磁盘上有 token,
否则报"假绿"(`hermes_cli/web_routers/mcp.py:152`–`155`)。

**Webhook(`:12378`–`:12528`)。** 秘钥只在**创建时**回显一次(`summary["secret"] = secret`,`:12493`),
读列表只给 `secret_set: bool`。启用/停用不删订阅(便于恢复),网关热加载订阅文件,不需要重启。

**Memory(`:12730`–`:12797`)。** `PUT /api/memory/provider` 前置 `_require_memory_provider_ready(provider)`
——dashboard **不跑** provider 的交互式 setup hook,只有"可发现 + 可用 + 必填配置齐全"才允许激活。
`POST /api/memory/reset` 只删 `memories/MEMORY.md` / `USER.md`,`target` 白名单三选一。

**Hooks(`:13046`–`:13137`)。** 创建 hook 是特权动作:写 `config.yaml` 的 `hooks:` 块,
`approve=true` 时还写同意清单(`shell_hooks._record_approval`)。删除时**无论有没有删掉配置行都撤销同意**
(`:13129`–`:13133`,注释 "Revoke consent regardless so a re-add re-prompts")——这是对的默认:
宁可让下次重新问一遍。

**Checkpoints(`:13140`–`:13179`)。** list 是纯读(统计文件数 + 字节数,供 UI 显示"清理能回收多少"),
prune 是 spawn CLI —— 理由写在注释里:确认与清理逻辑只留一份,放在 CLI。

---

## 8. 记号汇总

```text
▲ 文档与代码矛盾:0 条(严格意义上的"互相矛盾")
◇ 代码有、文档无 / 内部不一致但可解释:5 条
  ◇-1 §3.3 「不填 profile」≠「填 default」(pairing);已实测;代码注释有、用户文档无。
  ◇-2 §3.4 profile 名大小写:cron 家族 normalize、_resolve_profile_dir 家族不 normalize;
           ?profile=Work 在 /api/pairing 400、在 /api/cron/jobs 200(实测)。
  ◇-3 §4.2 凭据池写得进读不出成立,但同鉴权面的 backup+download 把 .env/auth.json 明文下发(实测)。
  ◇-4 §5.4 同一 Ops 簇里 download 严格限目录、import/backup 接受任意路径,三种策略无注释解释。
  ◇-5 §5.5 /api/ops/backup/download 与 /api/ops/import-upload 在全仓 1,492 个 md 里 0 提及;
           已文档化的 /api/ops/import 也没写"会覆盖 .env/auth.json/config.yaml"。
■ 代码缺陷:2 条
  ■-1 §6.4 _profile_cli_args("default") 返回 [],与 _profile_scope("default") / _cron_profile_home("default")
           指向相反;失效链已给(gateway start/stop 与 mcp catalog install 的两条分支自相矛盾)。实测。
  ■-2 §6.3 instantiate_blueprint 的 profile 默认 "default",与 create_cron_job 的 None 不一致,
           且正是 _cron_default_profile docstring 点名要避免的硬编码;实测两端点落到不同 jobs.json。
           标(潜在):两个官方前端都显式传值,线上不触发。
◎ 文档成立但保守:1 条
  ◎-1 §6.2 public_paths.py 说 "JWT 是边界",实际默认配置下 expected_audience 为空 ⇒ 任何 token 直接 401,
           整条公开路径默认零攻击面(fail-closed),比注释描述的更强。
```

---

## 9. 测试实跑

环境(按 CLAUDE.md 要求同时记录):
```console
$ /home/user/hermes-venv/bin/pip list | tail -n +3 | wc -l
87
```

第一批(pairing / cron / mcp dashboard):
```console
$ cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
    bash scripts/run_tests.sh tests/hermes_cli/test_dashboard_admin_endpoints.py \
      tests/hermes_cli/test_pairing.py tests/hermes_cli/test_web_server_cron_profiles.py \
      tests/hermes_cli/test_cron_fire_dashboard.py tests/hermes_cli/test_cron_dashboard_off_loop.py \
      tests/hermes_cli/test_mcp_dashboard_oauth.py

=== Summary: 6 files, 53 tests passed, 0 failed (100% complete) in 4.7s (8 workers) ===
```

第二批(backup / credential / sessions / 多 profile 配对库):
```console
$ cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
    bash scripts/run_tests.sh tests/hermes_cli/test_backup.py tests/hermes_cli/test_backup_stability.py \
      tests/hermes_cli/test_credential_lifecycle.py tests/hermes_cli/test_sessions_delete.py \
      tests/hermes_cli/test_web_server_session_search.py tests/test_web_server_sessiondb_eventloop.py \
      tests/gateway/test_multiplex_pairing_stores.py

=== Summary: 7 files, 57 tests passed, 0 failed (100% complete) in 2.7s (8 workers) ===
```

**合计 13 个文件、110 个用例、0 失败**,无需诊断项(已知的 5 个容器性必失用例全部不在本批)。

**作为行为规格最有价值的三个**:
- `tests/hermes_cli/test_dashboard_admin_endpoints.py::TestPairingEndpoints::test_pairing_is_isolated_per_profile`
  ——把"命名 profile 的批准必须落进它自己网关读的那张白名单"写成断言,并在注释里承认 `PAIRING_DIR` 是 import 期绑定(§3.3)。
- `tests/hermes_cli/test_cron_fire_dashboard.py`——四条断言正好覆盖 §6.2 的设计:路由必须挂在 dashboard app 上、
  必须在 `PUBLIC_API_PATHS` 里、坏 token 401(且 `fire_due` 不得被调用)、缺 job_id 400、合法 token 202。
- `tests/hermes_cli/test_backup.py::TestImport::{test_preserves_per_profile_gateway_state,
  test_preserves_runtime_pid_and_process_files, test_restores_secret_files_with_0600_perms}`
  ——把 §5.2 的 `_IMPORT_SKIP_NAMES` / `_SECRET_FILE_NAMES` 两张表钉成规格。

**基线洁净性(收工确认):**
```console
$ git -C /home/user/hermes-agent status --porcelain
(空)
$ git -C /home/user/hermes-agent rev-parse HEAD
863e31318553cda8ad61df681d08175364d4164b
```
本段全部探针写在 `/tmp`(`r8c_probe1..6.py`、`r8c_dump.py`),`HERMES_HOME` 一律指向 `tempfile.mkdtemp()`,
未在基线目录下产生任何写入(`scripts/run_tests.sh` 生成的 `test_durations.json` 已被 `.gitignore:35` 忽略)。

---

## 10. 本段未覆盖 / 存疑(每条带锚点 + 一句话现象)

1. **`PAIRING_DIR` 的 import 期绑定会不会真的造成新旧目录分裂?**
   锚点:`gateway/pairing.py:437`(无 profile 分支 `self._dir = PAIRING_DIR`)与
   `gateway/pairing.py:366`(`_migrate_split_pairing_dirs`)。
   现象:`PAIRING_DIR` 在 import 期就把"legacy `pairing/` 还是新 `platforms/pairing/`"这个判断算死了;
   若 legacy 目录在 import **之后**才有内容,该分支不会重新判断。看代码它每次构造都会调
   `_migrate_split_pairing_dirs()` 把 alternate 合并进 active,大概率被治好——**我没有为此写探针,未取证**。

2. **`/api/cron/fire` 的 JWT 用 dashboard 自己的配置校验,却能触发任意 profile 的 job。**
   锚点:`hermes_cli/web_routers/cron.py:148`(`cfg = load_config()`,无 profile scope)
   与 `hermes_cli/web_routers/cron.py:169`(`_find_cron_job_profile` 跨所有 profile 搜)。
   现象:一枚对本进程 `cron.chronos.expected_audience` 有效的 token,可以 fire 到别的 profile 的任务上;
   代码无注释说明这是否有意,`tests/hermes_cli/test_cron_fire_dashboard.py` 也没有断言这一点。

3. **`_pairing_store` 不做 `normalize_profile_name`,但 `PairingStore.__init__` 用 `profile == "default"` 精确比较。**
   锚点:`gateway/pairing.py:428`(`root if profile == "default" else root / "profiles" / profile`)。
   现象:若某个调用方绕过 `_pairing_store`、直接传 `"Default"`,会落到 `<root>/profiles/Default/…`;
   dashboard 路径上被 `_resolve_profile_dir` 的 400 挡住了,**其它调用方(CLI/gateway)我没有逐个查**。

4. **Ops 的 `checkpoints prune` / `doctor` / `security-audit` 三个 spawn 都不带 `-p`。**
   锚点:`hermes_cli/web_server.py:12815`(`_spawn_hermes_action(["doctor"], "doctor")`)、
   `:12825`、`:13175`。
   现象:与 §6.4 的 `_profile_cli_args` 问题同源但方向相反——这三个**根本没有 profile 参数**,
   永远跑在 dashboard 自己的 home 上;是有意还是遗漏,我没有找到注释或 issue 佐证。

5. **`BackupRequest.output` 可写任意路径,是否有更上层的约束?**
   锚点:`hermes_cli/web_server.py:12846`(`args.extend(["-o", output])`,无路径校验)。
   现象:`/api/ops/backup` 可以把含 `.env`+`auth.json` 的 zip 写到进程有写权限的任何位置;
   我只确认了 download 端点读不到它,**没有查是否有部署层(容器只读文件系统、systemd 沙箱)兜底**。

6. **本段路由的鉴权层。** 按分工由本轮另一段负责,本底稿未复查;
   引用其结论:pairing 路由本体零鉴权,全部保护来自中间件链。
   本段唯一自行确认的是 `_require_token` 只在 MCP 的 `/auth` 与 `/oauth/flows/{id}` 两条上额外调用
   (`hermes_cli/web_routers/mcp.py:203`、`:266`),其余端点无路由级检查。

7. **Webhook 簇的 `_write_platform_enabled` 与 `_restart_gateway_after_webhook_enable`。**
   锚点:`hermes_cli/web_server.py:12425`、`:12433`(两个 helper 的定义都在本段之外)。
   现象:`POST /api/webhooks/enable` 会**顺带重启网关**并把 `needs_restart` 回给前端;
   重启的实现与失败语义我未跟进。
