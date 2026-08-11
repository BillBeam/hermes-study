# R11F 底稿 · 片 D —— dashboard 与可观测型插件

> **范围**:`plugins/{kanban, hermes-achievements, dashboard_auth, observability}`,29 文件 / 16,993 行。
> **深度**:L2 = 结构级理解 = **读接口面而不读实现体**。可以不读实现,不可以抽样接口。
> **溯源约定**:凡对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` **单独成行、置于块之前**;
> 围栏块为基线逐字原文,非源码块用 ```text / ```console / ```verify 显式声明。
> 基线 = `/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`,**只读**。
> **记号**:▲ = 地图(README / 仓库根 AGENTS.md / website/docs)与代码矛盾;
> **▲(码内)** = 模块 docstring 或代码注释与代码矛盾(与地图级 ▲ **分开计数**);
> ◇ = 代码有、文档无;■ = 代码缺陷;◎ = 文档成立但显著保守。

**术语锚定**(首次出现):

- **dashboard(仪表盘)**:`hermes dashboard` 起的本地 web 服务,浏览器里管理这个 agent。
- **dashboard plugin(仪表盘插件)**:往这个 web 服务里同时挂**前端页签**和**后端路由**的插件。
- **FastAPI / APIRouter**:Python 的 web 框架;`APIRouter` 是一组路由的容器,可整体挂到某个前缀下。
- **manifest(清单)**:插件目录里描述自己是什么的元数据文件。本片有两种:
  `plugin.yaml`(后端插件清单)与 `dashboard/manifest.json`(仪表盘扩展清单),**两者键面完全不同**。
- **hook(钩子)**:内核在固定生命周期点回调插件的函数,如"每次调模型前""每次工具调用后"。
- **ABC(抽象基类)**:Python 里用 `@abstractmethod` 标出"子类必须实现"的方法的基类;
  少一个方法就实例化不了。
- **provider(提供方)**:实现某个 ABC 的可替换后端。本片指 dashboard 登录方式的四种实现。
- **OIDC / OAuth 2.0 / PKCE**:标准登录协议族;PKCE 是给"没法保存密钥的客户端"用的防截获扩展。
- **bearer token(承载令牌)**:HTTP 头 `Authorization: Bearer <串>`,拿到串就等于拿到权限。
- **task_events**:kanban 的**只追加**事件表;前端靠轮询它的自增 id 拿增量。
- **WAL(预写日志)**:SQLite 的一种模式,读事务不阻塞写事务。
- **ATOF / ATIF**:NVIDIA NeMo Relay 定义的两种 agent 轨迹导出格式(逐事件 JSONL / 整条轨迹 JSON)。

---

## 0. 范围、方法与环境

**本片文件清单口径**:`data/r11f/slices/D.txt`,29 文件 / 16,993 行。

```verify
awk -F'\t' '{n++; l+=$2} END{printf "files=%d\tlines=%d\n", n, l}' data/r11f/slices/D.txt
```

```text
files=29	lines=16993
```

**方法**。本片三个探针全部只做 **AST / 文本解析**,**不 import 被测模块**,
因此不触发基线的惰性安装、无网络副作用:

| 探针 | 做什么 |
|---|---|
| `data/r11f/probes/d_route_surface.py` | HTTP 路由面枚举(方法/路径/处理函数/形参表) |
| `data/r11f/probes/d_manifest_surface.py` | 清单键面 + `hooks` 声明与代码注册的对账 |
| `data/r11f/probes/d_auth_provider_matrix.py` | dashboard_auth 四 provider 对 ABC 的实现面矩阵 |

**环境**。唯一执行基线代码的动作是跑一次配套测试,带惰性安装封印:

```console
$ HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
    /home/user/hermes-venv/bin/python -m pytest -q \
    plugins/hermes-achievements/tests/test_achievement_engine.py
...........                                                              [100%]
11 passed in 0.29s

$ ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l
87
```

**11 通过 / 0 失败 / 0 跳过,venv 87 包**(与 CLAUDE.md 记录的基线环境一致)。
本片范围内不触发 CLAUDE.md 记录的 6 个容器环境必然失败用例。
取证前后 `git -C /home/user/hermes-agent status --porcelain` 均为空。

**本片与已有底稿的分工**。`notes/r9d-raw-kanban-todo-cron.md` 读的是 kanban 的**工具面**
(`tools/kanban_tools.py` 等,模型怎么用板子);`notes/r8c-raw-dashboard-auth.md` 读的是
`hermes_cli/dashboard_auth/`(宿主框架侧);`notes/r10-raw-web-dashboard.md` 读的是 dashboard 本体。
**本片读的是插件侧**:同一块板子的 **HTTP 面**、四个 auth provider 的**插件实现体**、
以及两个可观测插件。三者不重叠。

---

## 1. 判据 1 —— 点名表(29/29)

### 1.1 `plugins/kanban/`(5 文件 / 8,969 行)

| 路径 | 行 | 一句话角色 |
|---|---:|---|
| `plugins/kanban/dashboard/plugin_api.py` | 2862 | **本片最大的接缝**:kanban 板子的 45 条 HTTP 路由 + 1 条 WebSocket,挂到 `/api/plugins/kanban/` |
| `plugins/kanban/dashboard/manifest.json` | 14 | 仪表盘扩展清单:声明页签路径 `/kanban`、前端入口、CSS、后端 api 文件 |
| `plugins/kanban/dashboard/dist/index.js` | 4469 | 板子的**前端全部**:手写 IIFE,自称 "no build step"(见 §2.6) |
| `plugins/kanban/dashboard/dist/style.css` | 1592 | 板子样式;全部颜色引用主题 CSS 变量,不写死调色板 |
| `plugins/kanban/systemd/hermes-kanban-dispatcher.service` | 32 | **已废弃**的独立调度器 systemd 单元;调度器现默认跑在网关内 |

### 1.2 `plugins/hermes-achievements/`(10 文件 / 2,836 行)

| 路径 | 行 | 一句话角色 |
|---|---:|---|
| `plugins/hermes-achievements/dashboard/plugin_api.py` | 1061 | 成就插件后端:6 条路由 + 成就目录常量 + 会话扫描/评估引擎 |
| `plugins/hermes-achievements/dashboard/manifest.json` | 11 | 仪表盘扩展清单;页签 `/achievements`,位置 `after:analytics` |
| `plugins/hermes-achievements/dashboard/dist/index.js` | 726 | 成就页前端;含一张内联 Lucide 图标 SVG 表 |
| `plugins/hermes-achievements/dashboard/dist/style.css` | 146 | 成就页样式 |
| `plugins/hermes-achievements/tests/test_achievement_engine.py` | 171 | 该插件**自带**的 11 个单元测试(行为规格,本片实跑通过) |
| `plugins/hermes-achievements/README.md` | 150 | 插件说明 + 来源声明(上游 MIT 项目 vendored 进来) |
| `plugins/hermes-achievements/LICENSE` | 21 | MIT 许可证正本(vendored 代码必须随附) |
| `plugins/hermes-achievements/docs/achievements-performance-spec.md` | 174 | 性能重构**规格**(草案:砍掉 `/overview` 与顶栏槽位) |
| `plugins/hermes-achievements/docs/achievements-performance-implementation-spec.md` | 219 | 上条的**实现级细化**(面向执行) |
| `plugins/hermes-achievements/docs/achievements-performance-implementation-plan.md` | 157 | 上条的**执行计划**(状态:黑客松评审窗口后执行) |

*注:此表 10 行 = 10 个文件,`docs/` 下三份是三个不同文件,已逐个列全。
另有两个 `docs/assets/*.png` 截图不在本片清单内(台账按文本文件盘点)。*

**四组分组计数与本片总数的对账**(29 = 5 + 10 + 8 + 6):

```verify
awk -F'\t' '{split($1,a,"/"); g=a[2]; n[g]++; l[g]+=$2} END{for(k in n) printf "%s\t%d files\t%d lines\n", k, n[k], l[k]}' data/r11f/slices/D.txt | sort
```

```text
dashboard_auth	8 files	2344 lines
hermes-achievements	10 files	2836 lines
kanban	5 files	8969 lines
observability	6 files	2844 lines
```

*(这个分组数第一版把 achievements 写成了 9 —— 因为 `docs/` 三份在草稿里被当成一组数了一次。
分组计数就该用命令算,这正是"凡出现 N 个就要有 verify 块"那条规矩要防的形态。)*

### 1.3 `plugins/dashboard_auth/`(8 文件 / 2,344 行)

四个 provider,每个 = 一个 `__init__.py` + 一份 `plugin.yaml`。**共同形态**:
`kind: backend`,插件入口 `register(ctx)` 在**凭据配置齐全时**才注册 provider,否则记一条
`LAST_SKIP_REASON` 并静默返回 —— 于是 loopback / `--insecure` 用户完全不受影响。

| 路径 | 行 | 一句话角色 |
|---|---:|---|
| `plugins/dashboard_auth/basic/__init__.py` | 491 | 用户名/密码登录:无外部 IDP、无数据库,会话是自签 HMAC 无状态令牌,口令用 stdlib scrypt |
| `plugins/dashboard_auth/basic/plugin.yaml` | 7 | 上者的清单;`requires_env: HERMES_DASHBOARD_BASIC_AUTH_USERNAME` |
| `plugins/dashboard_auth/nous/__init__.py` | 671 | Nous Portal 的 OAuth 2.0(授权码 + PKCE);校验 Portal 自定义 JWT **access token** |
| `plugins/dashboard_auth/nous/plugin.yaml` | 7 | 上者的清单;`requires_env: HERMES_DASHBOARD_OAUTH_CLIENT_ID` |
| `plugins/dashboard_auth/self_hosted/__init__.py` | 862 | 通用自托管 OIDC(Authentik/Keycloak/…);走发现文档,校验 **ID token** |
| `plugins/dashboard_auth/self_hosted/plugin.yaml` | 8 | 上者的清单;`requires_env` 两条:ISSUER + CLIENT_ID |
| `plugins/dashboard_auth/drain/__init__.py` | 291 | **非交互**服务凭据:给 `/api/gateway/drain` 一条 bearer 通道,注册期熵检查,失败即闭 |
| `plugins/dashboard_auth/drain/plugin.yaml` | 7 | 上者的清单;`requires_env: HERMES_DASHBOARD_DRAIN_SECRET` |

### 1.4 `plugins/observability/`(6 文件 / 2,844 行)

| 路径 | 行 | 一句话角色 |
|---|---:|---|
| `plugins/observability/langfuse/__init__.py` | 1137 | Langfuse 追踪导出:把一次会话映射成一棵 trace 树,含**脱敏与截断**管线 |
| `plugins/observability/langfuse/plugin.yaml` | 14 | 清单;两条 `requires_env` + 六条 `hooks` |
| `plugins/observability/langfuse/README.md` | 53 | 启用方式(opt-in)与所需凭据 |
| `plugins/observability/nemo_relay/__init__.py` | 1023 | NVIDIA NeMo Relay 桥:注册会话初始化器 + 十个钩子,导出 ATOF/ATIF |
| `plugins/observability/nemo_relay/plugin.yaml` | 15 | 清单;**无** `requires_env`,十条 `hooks` |
| `plugins/observability/nemo_relay/README.md` | 602 | 本片最长的文档:Relay 概念、两种导出格式、动态插件配置面 |

**29/29 全部点名,无遗漏。**

---

## 2. 判据 2 —— 接缝穷举(本片重心)

这一片的插件与平台适配器形态不同:它们不实现某个消息平台 ABC,而是
**往宿主 web 服务器挂路由**、**往内核钩子表挂回调**、**往 auth 框架挂 provider**。
下面六个接缝逐一穷举,每个都给机械枚举命令与条数。

### 2.0 先看宿主怎么装:插件路由是怎么变成 URL 的

在讲 51 条路由之前,得先确定这些路径**前缀是什么、谁决定的**。

`hermes_cli/web_server.py:17305 @ 863e313`

```
            router = getattr(mod, "router", None)
            if router is None:
                _log.warning("Plugin %s api file has no 'router' attribute", plugin["name"])
                continue
            app.include_router(router, prefix=f"/api/plugins/{plugin['name']}")
            _log.info("Mounted plugin API routes: /api/plugins/%s/", plugin["name"])
        except Exception as exc:
            _log.warning("Failed to load plugin %s API routes: %s", plugin["name"], exc)
```

**契约就三条**:(a) 清单的 `api` 键指向一个 py 文件;(b) 该文件必须导出一个名叫 `router`
的对象;(c) 它被挂到 `/api/plugins/<清单 name>/` 下。

**挂载在模块导入期一次性完成** —— 不是每次请求现算,也没有卸载路径:

`hermes_cli/web_server.py:17315 @ 863e313`

```
# Mount plugin API routes before the SPA catch-all.
_mount_plugin_api_routes()
```

所以**运行中禁用一个插件不会卸掉它已挂上的路由**,这正是宿主另加一道请求期闸门的原因:

`hermes_cli/web_server.py:584 @ 863e313`

```
    path = request.url.path
    if path.startswith("/api/plugins/"):
```

三道与本片直接相关的宿主级闸门,**按请求经过的顺序**:

| # | 闸门 | 锚点 + 摘录 | 它挡什么 |
|---|---|---|---|
| 1 | token-auth 缝 | `hermes_cli/web_server.py:685`:`return await token_auth_middleware(request, call_next)` | 给注册过的路由开 bearer 通道(drain 用它) |
| 2 | 会话令牌闸门 | `hermes_cli/web_server.py:665`:`if path.startswith("/api/") and path not in _PUBLIC_API_PATHS and not is_mcp_oauth_callback:` | 所有 `/api/` 无凭据一律 401 |
| 3 | 插件启用闸门 | `hermes_cli/web_server.py:585`:`if path.startswith("/api/plugins/"):` | 运行中被禁用的插件,其路由改回 404 |

**闸门 3 的顺序是有意的**,不是巧合。它注册在 auth 之前(于是执行在 auth 之后),
理由写在它自己的 docstring 里:

`hermes_cli/web_server.py:578 @ 863e313`

> Registered BEFORE the auth middlewares (so it executes AFTER them): a
> request that hasn't cleared auth must get auth's 401 first, never this
> gate's 404 — otherwise an unauthenticated caller could fingerprint which
> plugins are installed/enabled by reading the status code.

**即 404/401 的先后本身是信息泄露面**:先 404 会让未登录的人靠状态码枚举出你装了哪些插件。

**负结论:`/api/plugins/*` 不在任何免鉴权名单里。** 搜索面 = 两道 auth 闸门**共用的同一份**
frozenset,`hermes_cli/dashboard_auth/public_paths.py` 的 `PUBLIC_API_PATHS`。
它被旧闸门以别名导入:

`hermes_cli/web_server.py:393 @ 863e313`

```
from hermes_cli.dashboard_auth.public_paths import (
    PUBLIC_API_PATHS as _PUBLIC_API_PATHS,
)
```

被新闸门直接使用:

`hermes_cli/dashboard_auth/middleware.py:81 @ 863e313`

```
    if path in PUBLIC_API_PATHS:
```

把这份名单的全部条目列出来看:

```verify
grep -o '"/api/[a-z/]*"' /home/user/hermes-agent/hermes_cli/dashboard_auth/public_paths.py | sort
```

```text
"/api/config/defaults"
"/api/config/schema"
"/api/cron/fire"
"/api/dashboard/plugins"
"/api/dashboard/themes"
"/api/health"
"/api/model/info"
"/api/status"
```

**八条,没有 `/api/plugins/`。** 注意 `/api/dashboard/plugins` 长得像但不是同一个东西 ——
那是**列出装了哪些插件**的核心端点(免鉴权,只吐清单),而 `/api/plugins/<name>/...`
是**插件自己的后端**(全部要鉴权)。这两个路径差一个词、语义差一个数量级,
是本片最容易读错的一处。

### 2.1 接缝一:HTTP 路由面 —— **51 条,逐条列全**

枚举用 AST 而不是正则:装饰器可以跨行、路径可以是非字面量,正则只在"当前写法恰好规整"时正确,
而这里要给的是**穷举**保证。探针同时断言了两件事,任一不成立枚举面就不完整:
装饰器 owner 只有 `router` 一个(没有第二张路由表),且没有非字面量路径。

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/d_route_surface.py /home/user/hermes-agent --tsv 2>/dev/null | awk -F'\t' 'NR>1{n[$1]++; t++} END{for(f in n) printf "%s\t%d\n", f, n[f]; printf "TOTAL\t%d\n", t}' | sort
```

```text
TOTAL	51
plugins/hermes-achievements/dashboard/plugin_api.py	6
plugins/kanban/dashboard/plugin_api.py	45
```

全表落库在 `data/r11f/d/route-surface.tsv`(含每条路由的形参表)。下面是完整的 51 行,
**按声明顺序**,锚点后紧跟的反引号片段即该行装饰器的逐字原文:

#### hermes-achievements —— 6 条,挂在 `/api/plugins/hermes-achievements/`

| 方法 | 路径 | 锚点 + 摘录 | 处理函数 | 作用 |
|---|---|---|---|---|
| `GET` | `/achievements` | `plugins/hermes-achievements/dashboard/plugin_api.py:999`:`@router.get("/achievements")` | `achievements` | 主数据:全部成就 + 各状态计数 + 快照是否过期 + 扫描进度 |
| `GET` | `/scan-status` | `plugins/hermes-achievements/dashboard/plugin_api.py:1011`:`@router.get("/scan-status")` | `scan_status` | 只要扫描进度(前端轮询用,不触发扫描) |
| `GET` | `/recent-unlocks` | `plugins/hermes-achievements/dashboard/plugin_api.py:1016`:`@router.get("/recent-unlocks")` | `recent_unlocks` | 最近解锁的 20 条,按解锁时间倒序 |
| `GET` | `/sessions/{session_id}/badges` | `plugins/hermes-achievements/dashboard/plugin_api.py:1022`:`@router.get("/sessions/{session_id}/badges")` | `session_badges` | 单场会话**自己**够到的徽章(只用这一场的聚合量) |
| `POST` | `/rescan` | `plugins/hermes-achievements/dashboard/plugin_api.py:1037`:`@router.post("/rescan")` | `rescan` | 强制全量重扫(`force=True`,绕过快照缓存) |
| `POST` | `/reset-state` | `plugins/hermes-achievements/dashboard/plugin_api.py:1042`:`@router.post("/reset-state")` | `reset_state` | **破坏性**:清空解锁记录并作废快照缓存 |

#### kanban —— 45 条,挂在 `/api/plugins/kanban/`

**读面(板子与卡片)**

| 方法 | 路径 | 锚点 + 摘录 | 处理函数 | 作用 |
|---|---|---|---|---|
| `GET` | `/board` | `plugins/kanban/dashboard/plugin_api.py:378`:`@router.get("/board")` | `get_board` | 整块板子按列分组(前端首屏唯一入口) |
| `GET` | `/tasks/{task_id}` | `plugins/kanban/dashboard/plugin_api.py:517`:`@router.get("/tasks/{task_id}")` | `get_task` | 单卡详情(抽屉打开时拉) |
| `GET` | `/stats` | `plugins/kanban/dashboard/plugin_api.py:2099`:`@router.get("/stats")` | `get_stats` | 板子统计计数 |
| `GET` | `/assignees` | `plugins/kanban/dashboard/plugin_api.py:2115`:`@router.get("/assignees")` | `get_assignees` | 出现过的受理人清单(筛选器用) |
| `GET` | `/tasks/{task_id}/log` | `plugins/kanban/dashboard/plugin_api.py:2136`:`@router.get("/tasks/{task_id}/log")` | `get_task_log` | 该任务 worker 进程的日志文件内容 |

**写面(卡片生命周期)**

| 方法 | 路径 | 锚点 + 摘录 | 处理函数 | 作用 |
|---|---|---|---|---|
| `POST` | `/tasks` | `plugins/kanban/dashboard/plugin_api.py:621`:`@router.post("/tasks")` | `create_task` | 建卡 |
| `PATCH` | `/tasks/{task_id}` | `plugins/kanban/dashboard/plugin_api.py:854`:`@router.patch("/tasks/{task_id}")` | `update_task` | **改卡总入口**;拖拽换列走的就是它 |
| `DELETE` | `/tasks/{task_id}` | `plugins/kanban/dashboard/plugin_api.py:1006`:`@router.delete("/tasks/{task_id}")` | `delete_task` | 删卡 |
| `POST` | `/tasks/bulk` | `plugins/kanban/dashboard/plugin_api.py:1230`:`@router.post("/tasks/bulk")` | `bulk_update` | 多选后批量改(单请求,逐条汇报成败) |
| `POST` | `/tasks/{task_id}/comments` | `plugins/kanban/dashboard/plugin_api.py:1153`:`@router.post("/tasks/{task_id}/comments")` | `add_comment` | 评论(也是往运行中的 worker 注入消息的桥) |
| `POST` | `/links` | `plugins/kanban/dashboard/plugin_api.py:1179`:`@router.post("/links")` | `add_link` | 加父子依赖边 |
| `DELETE` | `/links` | `plugins/kanban/dashboard/plugin_api.py:1192`:`@router.delete("/links")` | `delete_link` | 删依赖边 |

**附件面**

| 方法 | 路径 | 锚点 + 摘录 | 处理函数 | 作用 |
|---|---|---|---|---|
| `GET` | `/tasks/{task_id}/attachments` | `plugins/kanban/dashboard/plugin_api.py:696`:`@router.get("/tasks/{task_id}/attachments")` | `list_task_attachments` | 列附件 |
| `POST` | `/tasks/{task_id}/attachments` | `plugins/kanban/dashboard/plugin_api.py:712`:`@router.post("/tasks/{task_id}/attachments")` | `upload_task_attachment` | **本片唯一的 multipart 上传口**(`UploadFile`) |
| `GET` | `/attachments/{attachment_id}` | `plugins/kanban/dashboard/plugin_api.py:782`:`@router.get("/attachments/{attachment_id}")` | `download_attachment` | 下载(`FileResponse` 回原文件) |
| `DELETE` | `/attachments/{attachment_id}` | `plugins/kanban/dashboard/plugin_api.py:809`:`@router.delete("/attachments/{attachment_id}")` | `remove_attachment` | 删附件 |

**运行/诊断面(把"谁在跑什么"暴露给页面)**

| 方法 | 路径 | 锚点 + 摘录 | 处理函数 | 作用 |
|---|---|---|---|---|
| `GET` | `/diagnostics` | `plugins/kanban/dashboard/plugin_api.py:1358`:`@router.get("/diagnostics")` | `list_diagnostics` | 板子健康诊断(卡死、孤儿 run 等) |
| `GET` | `/workers/active` | `plugins/kanban/dashboard/plugin_api.py:1446`:`@router.get("/workers/active")` | `list_active_workers` | 当前活着的 worker 进程 |
| `GET` | `/runs/{run_id}` | `plugins/kanban/dashboard/plugin_api.py:1507`:`@router.get("/runs/{run_id}")` | `get_run_endpoint` | 单次运行记录 |
| `GET` | `/runs/{run_id}/inspect` | `plugins/kanban/dashboard/plugin_api.py:1529`:`@router.get("/runs/{run_id}/inspect")` | `inspect_run_endpoint` | 运行的深检视图 |
| `POST` | `/runs/{run_id}/terminate` | `plugins/kanban/dashboard/plugin_api.py:1601`:`@router.post("/runs/{run_id}/terminate")` | `terminate_run_endpoint` | **杀进程**:终止一次运行 |
| `POST` | `/tasks/{task_id}/reclaim` | `plugins/kanban/dashboard/plugin_api.py:1657`:`@router.post("/tasks/{task_id}/reclaim")` | `reclaim_task_endpoint` | 把卡死的卡从 running 收回 ready |
| `POST` | `/dispatch` | `plugins/kanban/dashboard/plugin_api.py:2176`:`@router.post("/dispatch")` | `dispatch` | 手动踢一次调度 tick |

**辅助 LLM 面(页面上一按就花钱的四条)**

| 方法 | 路径 | 锚点 + 摘录 | 处理函数 | 作用 |
|---|---|---|---|---|
| `POST` | `/tasks/{task_id}/specify` | `plugins/kanban/dashboard/plugin_api.py:1695`:`@router.post("/tasks/{task_id}/specify")` | `specify_task_endpoint` | 让辅助模型把粗想法写成规格并升列 |
| `POST` | `/estimate` | `plugins/kanban/dashboard/plugin_api.py:1804`:`@router.post("/estimate")` | `estimate_text_endpoint` | 对**一段文本**估工作量(建卡前预览) |
| `POST` | `/tasks/{task_id}/estimate` | `plugins/kanban/dashboard/plugin_api.py:1811`:`@router.post("/tasks/{task_id}/estimate")` | `estimate_task_endpoint` | 对**已有卡**估工作量 |
| `POST` | `/tasks/{task_id}/decompose` | `plugins/kanban/dashboard/plugin_api.py:2622`:`@router.post("/tasks/{task_id}/decompose")` | `decompose_task_endpoint` | 让辅助模型把一张大卡拆成子卡 |
| `POST` | `/profiles/{profile_name}/describe-auto` | `plugins/kanban/dashboard/plugin_api.py:2586`:`@router.post("/profiles/{profile_name}/describe-auto")` | `auto_describe_profile` | 让辅助模型给 profile 自动写简介 |

**指派与通知面**

| 方法 | 路径 | 锚点 + 摘录 | 处理函数 | 作用 |
|---|---|---|---|---|
| `POST` | `/tasks/{task_id}/reassign` | `plugins/kanban/dashboard/plugin_api.py:1745`:`@router.post("/tasks/{task_id}/reassign")` | `reassign_task_endpoint` | 换受理 profile |
| `GET` | `/home-channels` | `plugins/kanban/dashboard/plugin_api.py:2001`:`@router.get("/home-channels")` | `get_home_channels` | 可订阅的"回家频道"(卡有进展往哪个 IM 推) |
| `POST` | `/tasks/{task_id}/home-subscribe/{platform}` | `plugins/kanban/dashboard/plugin_api.py:2035`:`@router.post("/tasks/{task_id}/home-subscribe/{platform}")` | `subscribe_home` | 订阅该卡到某平台 |
| `DELETE` | `/tasks/{task_id}/home-subscribe/{platform}` | `plugins/kanban/dashboard/plugin_api.py:2070`:`@router.delete("/tasks/{task_id}/home-subscribe/{platform}")` | `unsubscribe_home` | 退订 |

**多板管理面**

| 方法 | 路径 | 锚点 + 摘录 | 处理函数 | 作用 |
|---|---|---|---|---|
| `GET` | `/boards` | `plugins/kanban/dashboard/plugin_api.py:2357`:`@router.get("/boards")` | `list_boards` | 列所有板子 |
| `POST` | `/boards` | `plugins/kanban/dashboard/plugin_api.py:2400`:`@router.post("/boards")` | `create_board_endpoint` | 新建板子 |
| `PATCH` | `/boards/{slug}` | `plugins/kanban/dashboard/plugin_api.py:2433`:`@router.patch("/boards/{slug}")` | `rename_board` | 改板子元数据(名/描述/默认项目目录) |
| `DELETE` | `/boards/{slug}` | `plugins/kanban/dashboard/plugin_api.py:2473`:`@router.delete("/boards/{slug}")` | `delete_board` | 删板子 |
| `POST` | `/boards/{slug}/switch` | `plugins/kanban/dashboard/plugin_api.py:2483`:`@router.post("/boards/{slug}/switch")` | `switch_board` | 切换 **CLI 侧**的当前板指针 |
| `GET` | `/projects` | `plugins/kanban/dashboard/plugin_api.py:2329`:`@router.get("/projects")` | `list_kanban_projects` | 可选的项目工作区列表 |

**配置面**

| 方法 | 路径 | 锚点 + 摘录 | 处理函数 | 作用 |
|---|---|---|---|---|
| `GET` | `/config` | `plugins/kanban/dashboard/plugin_api.py:1912`:`@router.get("/config")` | `get_config` | 板子相关配置(前端据此显示/隐藏控件) |
| `GET` | `/model-options` | `plugins/kanban/dashboard/plugin_api.py:2201`:`@router.get("/model-options")` | `model_options` | 可选模型下拉项 |
| `GET` | `/profiles` | `plugins/kanban/dashboard/plugin_api.py:2523`:`@router.get("/profiles")` | `list_profile_roster` | profile 花名册 |
| `PATCH` | `/profiles/{profile_name}` | `plugins/kanban/dashboard/plugin_api.py:2553`:`@router.patch("/profiles/{profile_name}")` | `update_profile_description` | 手改 profile 简介 |
| `GET` | `/orchestration` | `plugins/kanban/dashboard/plugin_api.py:2673`:`@router.get("/orchestration")` | `get_orchestration_settings` | 读编排设置 |
| `PUT` | `/orchestration` | `plugins/kanban/dashboard/plugin_api.py:2716`:`@router.put("/orchestration")` | `set_orchestration_settings` | 写编排设置(**全片唯一的 PUT**) |

**推送面**

| 方法 | 路径 | 锚点 + 摘录 | 处理函数 | 作用 |
|---|---|---|---|---|
| `WEBSOCKET` | `/events` | `plugins/kanban/dashboard/plugin_api.py:2787`:`@router.websocket("/events")` | `stream_events` | **全片唯一的 WebSocket**:尾随 `task_events` 表推增量 |

**方法分布**:`GET` 22 / `POST` 17 / `DELETE` 5 / `PATCH` 4 / `PUT` 1 / `WEBSOCKET` 1 = 51。

#### 2.1.1 路由面的第二维:板子作用域

kanban 是多板的,所以**每条路由还有一个"作用在哪块板上"的维度**。探针把形参表也抓下来了,
于是这一维可以机械分:

```verify
awk -F'\t' 'NR>1{t++; if($8 ~ /board:/) b++} END{printf "routes=%d\tboard-param=%d\tno-board-param=%d\n", t, b, t-b}' data/r11f/d/route-surface.tsv
```

```text
routes=51	board-param=30	no-board-param=21
```

**30 条**在函数签名里带 `board` 查询参数。**21 条不带**,分三类,逐条交代:

1. **achievements 的 6 条** —— 那个插件根本没有板子概念。
2. **kanban 里 14 条本就跨板/无板** —— `/boards*`(5 条)、`/profiles*`(3 条)、
   `/orchestration`(2 条)、`/config`、`/model-options`、`/projects`、`/estimate`
   (对一段裸文本估算,不涉及任何卡)。
3. **`WEBSOCKET /events` 1 条** —— 它**是**板子作用域的,只是不走签名参数,而是自己读查询串:

`plugins/kanban/dashboard/plugin_api.py:2809 @ 863e313`

```
        ws_board_raw = ws.query_params.get("board")
        try:
            ws_board = kanban_db._normalize_board_slug(ws_board_raw) if ws_board_raw else None
        except ValueError:
            ws_board = None
```

**这一条要如实说**:探针的判据是"签名里有没有 `board:`",所以它把 `/events` 数进了
"no-board-param",而实际语义是有作用域的。**14 + 6 + 1 = 21,分母对上,没有第 22 条**。
换句话说,kanban 的 45 条里 **30 + 1 = 31 条**受板子作用域约束,14 条按设计跨板。

板子参数的归一化在一个共用助手里,它同时负责把畸形 slug 变成 400 而不是 500:

`plugins/kanban/dashboard/plugin_api.py:97 @ 863e313`

```
def _resolve_board(board: Optional[str]) -> Optional[str]:
    """Validate and normalise a board slug from a query param.

    Raises :class:`HTTPException` 400 on malformed slugs so the browser
    sees a clean error instead of a 500. Returns the normalised slug,
    or ``None`` when the caller omitted the param (which then falls
    through to the active board inside ``kb.connect()``).
    """
```

### 2.2 接缝二:清单键面 —— 8 份 manifest,逐份键集列全

本片有**两种**清单,键面毫无交集,不能混为一谈:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/d_manifest_surface.py /home/user/hermes-agent slice
```

```text
plugins/dashboard_auth/basic/plugin.yaml	name,version,description,author,kind,requires_env
plugins/dashboard_auth/drain/plugin.yaml	name,version,description,author,kind,requires_env
plugins/dashboard_auth/nous/plugin.yaml	name,version,description,author,kind,requires_env
plugins/dashboard_auth/self_hosted/plugin.yaml	name,version,description,author,kind,requires_env
plugins/observability/langfuse/plugin.yaml	name,version,description,author,requires_env,hooks
plugins/observability/nemo_relay/plugin.yaml	name,version,description,author,hooks
plugins/kanban/dashboard/manifest.json	name,label,description,icon,version,tab,entry,css,api
plugins/hermes-achievements/dashboard/manifest.json	name,label,description,icon,version,tab,entry,css,api
```

**六份 `plugin.yaml` 用到 7 个不同顶层键**(`name`/`version`/`description`/`author`/
`kind`/`requires_env`/`hooks`);**两份 `dashboard/manifest.json` 用到 9 个**
(`name`/`label`/`description`/`icon`/`version`/`tab`/`entry`/`css`/`api`),
且两份 JSON 清单**键集完全相同**。

`manifest.json` 九个键各自的语义(逐个,不抽样):

| 键 | 取值(kanban / achievements) | 作用 |
|---|---|---|
| `name` | `kanban` / `hermes-achievements` | **决定路由前缀** `/api/plugins/<name>/`,也是启用/禁用名单里的键 |
| `label` | `Kanban` / `Achievements` | 页签上显示的字 |
| `description` | 一句话 | 插件列表里的副标题 |
| `icon` | `Package` / `Star` | 图标名(取自宿主的图标集) |
| `version` | `1.0.0` / `0.4.0` | 版本号 |
| `tab` | `{path, position}` | 页签挂哪个前端路由、插在谁后面(`after:skills` / `after:analytics`) |
| `entry` | `dist/index.js` | 前端入口 |
| `css` | `dist/style.css` | 样式 |
| `api` | `plugin_api.py` | **后端路由文件**;宿主导入它并取名为 `router` 的对象 |

`plugin.yaml` 七个键里,`kind: backend` 出现在四份 dashboard_auth 清单上、
**不在两份 observability 清单上** —— 后者走的是默认值:

`hermes_cli/plugins.py:1605 @ 863e313`

```
            raw_kind = data.get("kind", "standalone")
```

### 2.3 接缝三:钩子注册面 —— 16 条,清单声明与代码注册逐条对账

两个可观测插件是本片唯一往**内核钩子表**挂东西的。钩子的**真实**注册面是
`register(ctx)` 里的 `ctx.register_hook(...)` 调用,清单里的 `hooks:` 是另一回事(见 §5 的 ■)。
两侧逐条对账:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/d_manifest_surface.py /home/user/hermes-agent hooks
```

```text
plugins/observability/langfuse/plugin.yaml
  declared(6): pre_api_request,post_api_request,pre_llm_call,post_llm_call,pre_tool_call,post_tool_call
  registered(6): pre_api_request,post_api_request,pre_llm_call,post_llm_call,pre_tool_call,post_tool_call
  declared_only: -
  registered_only: -
plugins/observability/nemo_relay/plugin.yaml
  declared(10): on_session_start,on_session_end,on_session_finalize,on_session_reset,pre_llm_call,post_llm_call,pre_approval_request,post_approval_response,subagent_start,subagent_stop
  registered(10): on_session_start,on_session_end,on_session_finalize,on_session_reset,pre_llm_call,post_llm_call,pre_approval_request,post_approval_response,subagent_start,subagent_stop
  declared_only: -
  registered_only: -
```

**6 + 10 = 16 条,两侧完全一致,零差集。**(顺序也一致。)

langfuse 的注册块值得逐字看,因为它解释了"为什么六条里有两对看着重复":

`plugins/observability/langfuse/__init__.py:1128 @ 863e313`

```
def register(ctx) -> None:
    # Register for both hook name variants so the plugin works across
    # Hermes versions.  pre_api_request / post_api_request fire per API
    # call (preferred); pre_llm_call / post_llm_call fire once per turn.
    ctx.register_hook("pre_api_request", on_pre_llm_request)
    ctx.register_hook("post_api_request", on_post_llm_call)
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("post_llm_call", on_post_llm_call)
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)
```

**这是一处很值得学的设计**:插件不知道宿主是新是旧,于是**两套钩子名都注册**。
新宿主两套都发,插件就会**同一件事收到两次** —— `post_api_request` 与 `post_llm_call`
挂的还是**同一个函数** `on_post_llm_call`。它靠函数内部的幂等(按 `_request_key` 区分
每次 API 调用、按 `_trace_key` 归并到同一棵 trace)吸收重复,而不是靠"选一个注册"。
**代价**是每次都要多跑一遍序列化;**收益**是跨版本零配置。

`ctx.register_hook` 只做一件事,不校验名字是否在 `VALID_HOOKS` 里:

`hermes_cli/plugins.py:1194 @ 863e313`

```
        self._manager._hooks.setdefault(hook_name, []).append(callback)
```

合法钩子名的白名单在宿主侧:

`hermes_cli/plugins.py:135 @ 863e313`

```
VALID_HOOKS: Set[str] = {
    "pre_tool_call",
    "post_tool_call",
    "transform_terminal_output",
    "transform_tool_result",
```

它现有 **24** 个名字,本片这 16 条注册涉及的 **14 个不同钩子名全部在其中**
(langfuse 与 nemo_relay 各有 `pre_llm_call` / `post_llm_call` 两条重合,故 16 条对应 14 个名字):

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 -c "
import ast
t = ast.parse(open('/home/user/hermes-agent/hermes_cli/plugins.py').read())
for n in ast.walk(t):
    if isinstance(n, ast.AnnAssign) and getattr(n.target, 'id', '') == 'VALID_HOOKS':
        names = [e.value for e in n.value.elts]
        print('VALID_HOOKS =', len(names))
        print('slice-D hooks all in VALID_HOOKS:', all(h in names for h in [
            'pre_api_request','post_api_request','pre_llm_call','post_llm_call',
            'pre_tool_call','post_tool_call','on_session_start','on_session_end',
            'on_session_finalize','on_session_reset','pre_approval_request',
            'post_approval_response','subagent_start','subagent_stop']))
"
```

```text
VALID_HOOKS = 24
slice-D hooks all in VALID_HOOKS: True
```

*（这个数第一版写的是 26,是数错的 —— 用 AST 数元素个数而不是数源码行,
正是因为那份集合里夹着大段注释,肉眼数必错。）*

### 2.4 接缝四:dashboard_auth 对宿主 ABC 的实现面 —— 4 provider × 7 方法,矩阵列全

这是本片的"平台适配器契约"对应物。宿主的 ABC 有 **5 个抽象方法 + 2 个可选方法 + 3 个能力开关**;
四个 provider 各自实现了哪些、哪些只是抛异常的桩、哪些直接继承基类,一次列全:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/d_auth_provider_matrix.py /home/user/hermes-agent
```

```text
ABC hermes_cli/dashboard_auth/base.py:105 DashboardAuthProvider
  abstract(5): start_login,complete_login,verify_session,refresh_session,revoke_session
  concrete-optional(2): complete_password_login,verify_token
  capability defaults: supports_password=False,supports_token=False,supports_session=True

plugins/dashboard_auth/basic/__init__.py:201 class BasicAuthProvider
  identity: name='basic',display_name='Username & Password'
  capability overrides: supports_password=True
  implemented(4): complete_password_login@244,refresh_session@273,revoke_session@285,verify_session@263
  stub-raises(2): complete_login@235,start_login@229
  inherited-not-overridden(1): verify_token
  extra-public(0): -

plugins/dashboard_auth/drain/__init__.py:140 class DrainSecretProvider
  identity: name='drain-secret',display_name='Drain Control (service credential)'
  capability overrides: supports_token=True,supports_session=False
  implemented(3): revoke_session@203,verify_session@192,verify_token@160
  stub-raises(3): complete_login@185,refresh_session@198,start_login@179
  inherited-not-overridden(1): complete_password_login
  extra-public(0): -

plugins/dashboard_auth/nous/__init__.py:153 class NousDashboardAuthProvider
  identity: name='nous',display_name='Nous Research'
  capability overrides: (none — all ABC defaults)
  implemented(5): complete_login@207,refresh_session@244,revoke_session@368,start_login@179,verify_session@350
  stub-raises(0): -
  inherited-not-overridden(2): complete_password_login,verify_token
  extra-public(0): -

plugins/dashboard_auth/self_hosted/__init__.py:174 class SelfHostedOIDCProvider
  identity: name='self-hosted',display_name='Self-Hosted OIDC'
  capability overrides: (none — all ABC defaults)
  implemented(5): complete_login@245,refresh_session@276,revoke_session@321,start_login@216,verify_session@302
  stub-raises(0): -
  inherited-not-overridden(2): complete_password_login,verify_token
  extra-public(0): -
```

**读法。** 抽象方法必须**定义**(不定义就实例化不了),但定义了可以只抛 `NotImplementedError` ——
所以探针把"真实现"与"桩"分开数;只看有没有 `def` 会把 drain 数成全实现。
`extra-public` 全 0 说明**没有任何 provider 往契约外加公开方法** —— 契约面是闭合的。

**三种形态,对应三种登录语义**:

| 形态 | provider | 走的能力开关 | 契约上的表现 |
|---|---|---|---|
| 完整交互式 OAuth/OIDC | `nous`、`self-hosted` | 全默认 | 5 个抽象方法全部真实现,0 桩 |
| 口令式 | `basic` | `supports_password=True` | 重定向那两个(`start_login`/`complete_login`)成桩,改走 `complete_password_login` |
| 非交互服务凭据 | `drain` | `supports_token=True` + `supports_session=False` | 只真实现 `verify_token`;交互那套 3 桩 2 空实现 |

**`supports_session=False` 这个开关是关键**,它把 drain 挡在 cookie 会话验证的主循环之外。
ABC 侧把理由写在开关旁边:

`hermes_cli/dashboard_auth/base.py:180 @ 863e313`

```
    # When True, this provider does the interactive cookie-session flow (login,
    # verify, refresh). The login page, /auth/login, and the gate's
    # verify/refresh loops consult only supports_session providers, so a
    # token-only credential (e.g. drain) is never offered a login. Mirrors
    # supports_token.
    supports_session: bool = True
```

**drain 的路由级注册面**(它是本片唯一**给一条具体路由开口子**的插件):

`plugins/dashboard_auth/drain/__init__.py:275 @ 863e313`

```
    # Opt the begin/cancel-drain endpoint into the generic token-auth seam so
    # the dashboard's interactive cookie gate doesn't bounce NAS's bearer call.
    try:
        from hermes_cli.dashboard_auth.token_auth import register_token_route

        register_token_route(DRAIN_ROUTE_PATH)
```

**它只开一条路由**,路径常量写死在插件里,连宿主模块都不 import:

`plugins/dashboard_auth/drain/__init__.py:82 @ 863e313`

```
# The path the begin/cancel-drain endpoint lives on. Registered as a
# token-authable route by ``register()`` so the generic seam guards it. Kept
# here (not imported from web_server) to avoid a heavy import at plugin load.
DRAIN_ROUTE_PATH = "/api/gateway/drain"
```

**负结论:本片没有第二个 `register_token_route` 调用方。** 搜索面 = 基线全仓 `.py`
(排除 `tests/` 与 vendored 的 `hermes_agent-0.20.0/`),模式 `register_token_route`,
命中 3 处:插件里的 import 与调用各一(`:278`、`:280`),外加宿主侧的定义。

**失败即闭的门槛是三道并列的检查**,不是一个可配的软告警;任一不过,`register()` 直接返回、
端点保持禁用:

`plugins/dashboard_auth/drain/__init__.py:72 @ 863e313`

```
# Default entropy bar: 43 url-safe-base64 chars ~= 256 bits. token_urlsafe(32)
# produces 43 chars, so a correctly-provisioned secret clears this exactly.
_DEFAULT_MIN_SECRET_CHARS = 43
# A secret must contain at least this many DISTINCT characters — rejects
# degenerate values like "aaaa..." that are long but trivially low-entropy.
_MIN_DISTINCT_CHARS = 16
# Shannon entropy floor (bits) over the secret's characters — a second,
# distribution-aware guard on top of the length + distinct-count checks.
_MIN_SHANNON_BITS = 128.0
```

**三道针对三种不同的坏秘密**:太短、够长但字符太少(`aaaa…`)、够长够杂但分布畸形。
只有第一道是"长度",另外两道各自单独能拦住一类过得了长度检查的垃圾。

### 2.5 接缝五:环境变量面

| 插件 | 清单 `requires_env` | 代码实际读的(全部) |
|---|---|---|
| `basic` | `HERMES_DASHBOARD_BASIC_AUTH_USERNAME` | 上者 + `_PASSWORD_HASH` / `_PASSWORD` / `_SECRET` / `_TTL_SECONDS`(共 5) |
| `nous` | `HERMES_DASHBOARD_OAUTH_CLIENT_ID` | 上者 + `HERMES_DASHBOARD_PORTAL_URL`(共 2) |
| `self-hosted` | `HERMES_DASHBOARD_OIDC_ISSUER`、`_CLIENT_ID` | 上二者 + `client_secret` 等走 config.yaml |
| `drain` | `HERMES_DASHBOARD_DRAIN_SECRET` | 同左(1);行为旋钮走 `dashboard.drain_auth` |
| `langfuse` | `HERMES_LANGFUSE_PUBLIC_KEY`、`_SECRET_KEY` | **8 个 `HERMES_LANGFUSE_*` + 5 个裸 `LANGFUSE_*` 回落** |
| `nemo_relay` | **(无)** | 12 个 `HERMES_NEMO_RELAY_*` |

**langfuse 的 env 面比清单宽**:

`plugins/observability/langfuse/__init__.py:168 @ 863e313`

```
    public_key = _env("HERMES_LANGFUSE_PUBLIC_KEY") or _env("LANGFUSE_PUBLIC_KEY")
    secret_key = _env("HERMES_LANGFUSE_SECRET_KEY") or _env("LANGFUSE_SECRET_KEY")
```

—— 裸 `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL` / `LANGFUSE_ENV` /
`LANGFUSE_RELEASE` 都是合法回落,而清单一个都没声明。**这不构成故障**,因为
`requires_env` 不是加载闸门 —— 它只被安装向导用来提示缺哪些变量
(`hermes_cli/plugins_cmd.py:300`:`def _missing_requires_env_names(manifest: dict) -> list[str]:`)
和被 dashboard 展示(`hermes_cli/web_server.py:5271`:`"required_env": _string_list(manifest.get("requires_env")),`)。
但**后果是真实的**:一个只设了官方 `LANGFUSE_*` 变量的用户,会在安装向导里被提示"缺凭据",
而插件其实能跑。记 ◇(见 §5)。

**langfuse 的可观测配置面全在 env**,共 8 个 `HERMES_LANGFUSE_*`:
`PUBLIC_KEY` / `SECRET_KEY` / `BASE_URL` / `ENV` / `RELEASE` / `SAMPLE_RATE` / `MAX_CHARS` / `DEBUG`。
其中两个是本片"采样与脱敏怎么做"的答案:

**采样**:`SAMPLE_RATE` 直接透传给 Langfuse SDK 构造器,**插件自己不做采样判定**;
解析失败只告警不抛,退回"不设置"即 SDK 默认:

`plugins/observability/langfuse/__init__.py:215 @ 863e313`

```
    if sample_rate:
        try:
            kwargs["sample_rate"] = float(sample_rate)
        except ValueError:
            logger.warning("Invalid HERMES_LANGFUSE_SAMPLE_RATE=%r", sample_rate)
```

**截断**:`MAX_CHARS` 默认 **12000**,是每个上报值的字符上限,读在通用序列化函数的第一行:

`plugins/observability/langfuse/__init__.py:425 @ 863e313`

```
def _safe_value(value: Any, *, max_chars: Optional[int] = None, depth: int = 0,
                parse_json_strings: bool = False) -> Any:
    max_chars = max_chars if max_chars is not None else int(_env("HERMES_LANGFUSE_MAX_CHARS", "12000") or "12000")
```

**脱敏是三层,不是一层**,每层针对一种"上报会出事"的形态:

| 层 | 锚点 + 摘录 | 防什么 |
|---|---|---|
| 凭据预览 | `plugins/observability/langfuse/__init__.py:113`:`def _redact_key_preview(value: str) -> str:` | 操作员把真密钥贴错变量时,告警日志里**只回显前 6 字符** |
| base64 数据 URI | `plugins/observability/langfuse/__init__.py:273`:`def _redact_data_uri(value: str) -> dict[str, Any]:` | 一张内联图片能把一条 trace 撑爆,换成结构化描述 |
| 读文件负载 | `plugins/observability/langfuse/__init__.py:364`:`def _normalize_read_file_payload(value: dict[str, Any], *, args: Any = None) -> dict[str, Any]:` | `read_file` 结果只留头 25 行 / 尾 15 行预览 |

凭据预览这一层的逐字实现(**它决定了"贴错密钥"这件事在日志里留下多少**):

`plugins/observability/langfuse/__init__.py:122 @ 863e313`

```
    if not value:
        return "<empty>"
    if len(value) <= 12:
        return repr(value)
    return repr(value[:6] + "...")
```

**注意 `len <= 12` 那一支是全额回显。** 设计意图写在 docstring 里:短值几乎一定是
`test-key` / `your-key` 这类占位符,回显全文才能让操作员认出自己填了占位符;
真密钥不可能只有 12 字符。**这是一个有意的取舍,不是漏洞** —— 但它确实意味着
"12 字符以内的密钥会被完整写进日志",值得在自己造 harness 时抄这个判断前先想清楚。

**nemo_relay 的 12 个 env** 全是导出配置,分两组:`ATOF_*`(4 个:开关/目录/文件名/追加模式)
与 `ATIF_*`(7 个:开关/目录/文件名模板/子代理导出模式/agent 名/agent 版本/模型名),
外加 `HERMES_NEMO_RELAY_PLUGINS_TOML`(指向一份 Relay 动态插件配置)。
默认值全在一个 dataclass 里,一处可读:

`plugins/observability/nemo_relay/__init__.py:46 @ 863e313`

```
class _Settings:
    plugins_toml_path: str = ""
    plugins_config: dict[str, Any] | None = None
    dynamic_plugins: list[dict[str, Any]] = field(default_factory=list)
    atof_enabled: bool = False
    atof_output_directory: str = ""
    atof_filename: str = "hermes-atof.jsonl"
    atof_mode: str = "append"
    atif_enabled: bool = False
    atif_output_directory: str = ""
    atif_filename_template: str = "hermes-atif-{session_id}.json"
    atif_subagent_export_mode: str = "embedded"
    atif_agent_name: str = "Hermes Agent"
    atif_agent_version: str = "unknown"
    atif_model_name: str = "unknown"
```

**两个导出器默认都是关的**(`atof_enabled` / `atif_enabled` 均为 `False`),
所以"启用插件"与"开始导出"是两步 —— 这与清单 description 的说法一致
("HERMES_NEMO_RELAY_* env vars configure exports **after** the plugin is enabled")。

nemo_relay 还有一个**别的插件都没有的接缝**:它不止挂钩子,还往 Relay 的会话协调器
注册一个初始化器,并且**在钩子注册之前**就把动态插件激活了:

`plugins/observability/nemo_relay/__init__.py:539 @ 863e313`

```
def register(ctx) -> None:
    relay_runtime.SESSION_COORDINATOR.register_session_initializer(
        _SESSION_INITIALIZER_NAME,
        _prepare_core_session,
    )
    # Activate dynamic plugins before Hermes installs the managed execution
    # boundaries that invoke their interceptors.
    if _load_settings().dynamic_plugins:
        _get_runtime()
```

**顺序有语义**:动态插件的拦截器要先在位,Hermes 才能在装执行边界时把它们串进去。
这是本片唯一一处 `register(ctx)` 里**顺序敏感**的初始化。

### 2.6 接缝六:前端产物面 —— 4 个 `dist/` 文件,以及一条**判据修订建议**

派工书把 `plugins/kanban/dashboard/dist/index.js`(4,469 行)与 `dist/style.css`(1,592 行)
称作**构建产物**,要我交代"由什么源码构建、为什么以产物形态入库",并允许我据此提**判据修订建议**。

**实测结论与这个前提相反:这四个文件不是构建产物,是手写源码。** `dist/` 是个名不副实的目录名。

证据一,**文件自己声明**:

`plugins/kanban/dashboard/dist/index.js:1 @ 863e313`

```
/**
 * Hermes Kanban — Dashboard Plugin
 *
 * Board view for the multi-agent collaboration board backed by
 * ~/.hermes/kanban.db. Calls the plugin's backend at /api/plugins/kanban/
 * and tails task_events over a WebSocket for live updates.
 *
 * Plain IIFE, no build step. Uses window.__HERMES_PLUGIN_SDK__ for React +
 * shadcn primitives; HTML5 drag-and-drop for card movement on desktop and
 * a pointer-based fallback for touch.
 */
```

证据二,**宿主的产品说法一致**:

```verify
grep -n "no build step" /home/user/hermes-agent/plugins/kanban/dashboard/dist/index.js; grep -n "no npm build required" /home/user/hermes-agent/hermes_cli/tips.py
```

```text
8: * Plain IIFE, no build step. Uses window.__HERMES_PLUGIN_SDK__ for React +
386:    'Dashboard plugins are drop-in: manifest.json + JS bundle in ~/.hermes/dashboard-plugins/ — no npm build required.',
```

证据三,**形态学**:没有 source map、没有任何构建配置、行长分布是人写的:

```verify
for f in plugins/kanban/dashboard/dist/index.js plugins/kanban/dashboard/dist/style.css plugins/hermes-achievements/dashboard/dist/index.js plugins/hermes-achievements/dashboard/dist/style.css; do printf '%s\tlines=%s\tmaxlen=%s\tsourcemap=%s\n' "$f" "$(wc -l < /home/user/hermes-agent/$f)" "$(awk '{if(length($0)>m)m=length($0)}END{print m}' /home/user/hermes-agent/$f)" "$(grep -c sourceMappingURL /home/user/hermes-agent/$f)"; done; printf 'build-config files under both plugin trees: %s\n' "$(find /home/user/hermes-agent/plugins/kanban /home/user/hermes-agent/plugins/hermes-achievements \( -name 'package*.json' -o -name '*.config.js' -o -name '*.config.ts' -o -name 'tsconfig*.json' -o -name '*.map' \) | wc -l)"
```

```text
plugins/kanban/dashboard/dist/index.js	lines=4469	maxlen=301	sourcemap=0
plugins/kanban/dashboard/dist/style.css	lines=1592	maxlen=129	sourcemap=0
plugins/hermes-achievements/dashboard/dist/index.js	lines=726	maxlen=10921	sourcemap=0
plugins/hermes-achievements/dashboard/dist/style.css	lines=146	maxlen=512	sourcemap=0
build-config files under both plugin trees: 0
```

**kanban 两份最长行 301 / 129 字符,零 source map,零构建配置。** 压缩产物不长这样。
achievements 的 `index.js` 最长行 10,921 字符看着可疑,但那**不是压缩**,是一张内联
SVG 图标表(`plugins/hermes-achievements/dashboard/dist/index.js:45`:`  const LUCIDE = {"flame":"<path d=\"M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294`);
它其余 725 行全是带注释的可读 JS。

**achievements 两份的来历不同,要分开说**:它们是从上游 MIT 项目 vendored 进来的,
而且**入库后被就地改过**——

`plugins/hermes-achievements/dashboard/dist/index.js:3 @ 863e313`

```
  // hermes-achievements dashboard plugin
  // Originally authored by @PCinkusz — https://github.com/PCinkusz/hermes-achievements (MIT).
  // Bundled into hermes-agent. Upstream repo remains the staging ground for new
  // badges and UI iteration; the in-progress scan banner below is a small addition
  // layered on top of the original dist bundle.
```

**"layered on top of the original dist bundle"** —— 上游那边它可能确实是产物,
但在**本仓库里它是被直接编辑的现役源码**,而且改动没有对应的上游源码可回溯。

#### 判据修订建议(H-R11F-D-e)

**建议:这四个文件不应按"构建产物"降级到 L4,现有 L2 归层是对的;
但派工书里"`dist/` = 构建产物"这条默认推定应当改为"按文件实测判定"。**

理由三条:

1. **"由什么源码构建"这个问题在这里没有答案,因为没有源码** —— `dist/index.js` **就是**源码。
   把它排除掉,等于把 kanban 前端的**全部** 4,469 行判成黑洞,而这与本项目
   "全仓每一个源文件都被明确交代,没有黑洞"的最终目的直接冲突。
2. **它承载着接缝的另一半。** 本片判据 3 的端到端链有三跳在这个文件里
   (`:2599` 的 drop 处理、`:740` 的 PATCH、WebSocket 重连)。若它是 L4,
   这条链就只能从服务端半截讲起 —— 而"用户点一下之后发生了什么"恰恰是 L2 要讲清的东西。
3. **判据要可机械执行。** "目录叫 `dist` 就算产物"是个**长相判据**,与 CLAUDE.md 反复
   立过的原则(白名单外的锚点、`sh`/`js`/`rs` 与 ccTLD 重名、`scripts/` 两棵树都有)
   同型:**看长相会误判,要看解析结果**。可机械化的判据建议是三条同时成立才算产物:
   (a) 存在 source map 或压缩迹象(最长行 > ~2000 且注释密度趋零);
   (b) 同仓存在构建配置;(c) 同仓存在对应源码树。
   本片四个文件**三条全不成立**。

**如实说覆盖面**:本建议只对本片实测的这 4 个文件成立。全仓其他 `dist/` 目录**没有查**,
不排除有真产物 —— 这正是建议改成"按文件实测"而不是"一律不排除"的原因。

---

## 3. 判据 3 —— 端到端链:在板子上把一张卡从 todo 拖到 ready

一次具体动作,逐跳带锚点。**七跳,起于鼠标,终于同一个页面上另一处像素变化。**

### 跳 1 —— 浏览器:松开鼠标

用户把卡片拖到 "ready" 列上方松手。列组件的 drop 处理器从 `dataTransfer` 取出任务 id
(自定义 MIME `text/x-hermes-task`,`plugins/kanban/dashboard/dist/index.js:196`:`  const MIME_TASK = "text/x-hermes-task";`),
然后按"是不是多选批量"分岔:

`plugins/kanban/dashboard/dist/index.js:2599 @ 863e313`

```
    const handleDrop = function (e) {
      e.preventDefault();
      setDragOver(false);
      const taskId = e.dataTransfer.getData(MIME_TASK);
      if (!taskId) return;
      if (props.selectedIds && props.selectedIds.has(taskId) && props.selectedIds.size > 1) {
        if (props.onMoveSelected) props.onMoveSelected(props.column.name);
      } else {
        props.onMove(taskId, props.column.name);
      }
    };
```

### 跳 2 —— 浏览器:先改本地状态(乐观更新),再发请求

`onMove` 落到板级的 `moveTask`。它**先**把卡从旧列摘走、插进新列(前端立刻动),
**然后**才发 PATCH;失败时报错并整块重载:

`plugins/kanban/dashboard/dist/index.js:740 @ 863e313`

```
      SDK.fetchJSON(withBoard(`${API}/tasks/${encodeURIComponent(taskId)}`, board), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }).catch(function (err) {
        setError(tx(t, "moveFailed", "Move failed: ") + parseApiErrorMessage(err));
        loadBoard();
      });
```

`API` 是写死的前缀常量 `plugins/kanban/dashboard/dist/index.js:195`:`  const API = "/api/plugins/kanban";`,
与 §2.0 宿主那边 `include_router(..., prefix=f"/api/plugins/{plugin['name']}")` 拼出的前缀
**在两个文件里各写了一遍** —— 靠 `manifest.json` 的 `name` 键把两边对齐,没有共享常量。

### 跳 3 —— 宿主中间件三连

请求依次经过 §2.0 那三道闸门:token-auth 缝放行(不是注册过的 token 路由)→
会话令牌闸门校验(`/api/plugins/...` 不在免鉴权名单里,必须带凭据)→
插件启用闸门(kanban 是 bundled 且未被禁用,放行)。

### 跳 4 —— 插件路由:参数校验与分派

`plugins/kanban/dashboard/plugin_api.py:854 @ 863e313`

```
@router.patch("/tasks/{task_id}")
def update_task(task_id: str, payload: UpdateTaskBody, board: Optional[str] = Query(None)):
    board = _resolve_board(board)
    conn = _conn(board=board)
```

板子 slug 先过 `_resolve_board`(畸形 → 400,不存在 → 404),再开连接。
`status` 字段按目标值分派到不同的内核动词;拖到 `ready` 且当前不是 blocked/scheduled 时,
走"直接置位"这一支:

`plugins/kanban/dashboard/plugin_api.py:889 @ 863e313`

```
            elif s == "ready":
                # Re-open a blocked/scheduled task, or just an explicit status set.
                current = kanban_db.get_task(conn, task_id)
                if current and current.status in ("blocked", "scheduled"):
                    ok = kanban_db.unblock_task(conn, task_id)
                else:
                    # Direct status write for drag-drop (todo -> ready etc).
                    ok = _set_status_direct(conn, task_id, "ready")
```

### 跳 5 —— 内核:一个写事务里做完三件事

`_set_status_direct` 在 `kanban_db.write_txn` 里依次:查父任务是否全 done(**没全 done 就拒绝升到 ready**,
防止调度器派出一个上游没完成的子任务)、更新 `tasks` 行并清掉 claim/pid、
**追加一行 `task_events`**:

`plugins/kanban/dashboard/plugin_api.py:1102 @ 863e313`

```
        conn.execute(
            "INSERT INTO task_events (task_id, run_id, kind, payload, created_at) "
            "VALUES (?, ?, 'status', ?, ?)",
            (task_id, run_id, json.dumps({"status": new_status}), int(time.time())),
        )
```

**这一行 INSERT 就是"回到用户"那半程的起点。** 它和状态更新在同一个事务里,
所以事件永远不会比它描述的状态先被看见。

### 跳 6 —— 内核:事件被 WebSocket 尾随出来

同一个插件里的 `/events` 处理器按固定间隔轮询。**这个常数的注释交代了取舍**
(轮询 vs 通知,选了前者):

`plugins/kanban/dashboard/plugin_api.py:2506 @ 863e313`

```
# the simplest and most robust approach; it adds a fraction of a percent
# of CPU and has no shared state to synchronize across workers.
_EVENT_POLL_SECONDS = 0.3
```

每 0.3 秒按自增 id 拉一次增量,单次上限 200 行:

`plugins/kanban/dashboard/plugin_api.py:2818 @ 863e313`

```
                rows = conn.execute(
                    "SELECT id, task_id, run_id, kind, payload, created_at "
                    "FROM task_events WHERE id > ? ORDER BY id ASC LIMIT 200",
                    (cursor_val,),
                ).fetchall()
```

整个尾随循环只有四行,但每一行都在解一个具体问题:

`plugins/kanban/dashboard/plugin_api.py:2843 @ 863e313`

```
        while True:
            cursor, events = await asyncio.to_thread(_fetch_new, cursor)
            if events:
                await ws.send_json({"events": events, "cursor": cursor})
            await asyncio.sleep(_EVENT_POLL_SECONDS)
```

`to_thread` 让同步的 SQLite 读不堵住事件循环;`if events` 让空轮询不产生流量;
`cursor` 随每批回传,于是断线重连能从断点续("`?since=`" 查询参数)。
**SQLite 的 WAL 模式让这个读循环与调度器的写事务并行**,这一点写在模块头:

`plugins/kanban/dashboard/plugin_api.py:10 @ 863e313`

> Live updates arrive via the ``/events`` WebSocket, which tails the
> append-only ``task_events`` table on a short poll interval (WAL mode lets
> reads run alongside the dispatcher's IMMEDIATE write transactions).

### 跳 7 —— 回到页面

事件带 `cursor` 推给浏览器,前端据此刷新。**闭环意义在于:同一次变更走了两条路回到页面** ——
跳 2 的乐观更新让本人立刻看到,跳 6 的事件流让**同一块板子的其他浏览器/其他人**也看到。
两条路冲突时以服务端为准(跳 2 的 `.catch` 里 `loadBoard()` 整块重载)。

**WebSocket 的鉴权是单独一道**,不共用 HTTP 那条:浏览器无法在升级请求上设
`Authorization` 头,凭据只能走查询串。插件没有自己实现校验,而是委托给宿主的规范闸门:

`plugins/kanban/dashboard/plugin_api.py:2794 @ 863e313`

```
    if not _ws_upgrade_authorized(ws):
        await ws.close(code=http_status.WS_1008_POLICY_VIOLATION)
        return
```

**委托的理由值得抄**:自己实现过一版只认 `_SESSION_TOKEN`,结果**所有 OAuth 网关部署上
这条 WS 一律被拒**,而 dashboard 其他部分都正常 —— 因为 OAuth 模式下浏览器拿的是一次性
ticket 而不是那个 token。改成委托后,插件自动支持宿主的全部三种凭据形态
(loopback token / 一次性 ticket / 进程内部凭据),**且再也不会与核心鉴权漂移**
(`plugins/kanban/dashboard/plugin_api.py:64-86` 的 docstring 完整记录了这次事故)。

---

## 4. 判据 4 —— 逐字取证

本底稿共 **36 个**逐字源码围栏块(锚点单独成行 + 紧跟的 ``` 围栏),另有 **6 处**
`>` 引用块(文档/docstring 摘录)。每个围栏块**整块每一行**都与基线逐字一致 ——
关卡从 R8D 起对整块比对,抄漏半行即 `BLOCK-DRIFT` 阻断。

**判据要求 ≥2,实际 36。** 关卡读数(`scripts/verify_citations.py`,
语料 = 本底稿单文件):

```text
citations=51  OK=42  UNCHECKED=9
可校验比例 OK/51 = 82.4%
table_anchors=67  OK=67
OK: every code-block-backed citation matches the baseline
```

**可校验比例 82.4%,高于 70% 下限。**
**表格锚点声明率单独报**(不并入上面那个比例,R11B 定):**67 / 67 全部声明并校验通过**
—— 本底稿所有表格锚点都写成了「锚点 + 紧跟的反引号摘录」的声明式,零 TABLE-UNCHECKED。

剩余 9 条 UNCHECKED 全部是**有意保留**的散文式区域指路,分三类:
(a) **行号区间**(指一整段 docstring 而不是某一行),整块摘录无意义;
(b) **同段内已有逐字块**,散文里再提一次只是为了行文连贯;
(c) 那一行 **10,921 字符**的内联 SVG 图标表,摘录它没有信息量。

**这个读数对"报告它"不幂等,所以两个读数都报**(CLAUDE.md R11B 的规矩,
本底稿实撞一次)。第一版 §4 在正文里把这 9 条 UNCHECKED **逐条列了出来**,
而列举本身就是 9 个新锚点、且它们同样不跟块 —— 于是同一份文件的读数变成:

```text
不含这一节的逐条清单:  citations=51  OK=42  UNCHECKED=9   → 82.4%
含逐条清单(第一版):  citations=57  OK=42  UNCHECKED=15  → 73.7%
```

**两个数都是真的,分母不同。** 现在正文改成按类交代、不再逐条铸锚点,
故最终读数以本节开头那一份为准。**一份讲锚点覆盖率的文档会改变自己的锚点覆盖率**
—— 这正是 R11B 立"两个读数都报"这条规矩的形状,只不过那次是点名覆盖率、这次是引用关卡。

---

## 5. 判据 5 —— 记号

### ■ H-R11F-D-a:`plugin.yaml` 的 `hooks:` 键,10 份清单在写、0 行代码在读

**现象。** 加载器解析 `plugin.yaml` 时只取 8 个键,其中钩子相关的那个叫 `provides_hooks`:

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

而全仓 97 份清单里,**写 `hooks:` 的有 10 份,写 `provides_hooks:` 的有 0 份**:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/d_manifest_surface.py /home/user/hermes-agent census
```

```text
plugin.yaml total	97
top-level key 'hooks'	10
top-level key 'provides_hooks'	0
  hooks: plugins/disk-cleanup/plugin.yaml
  hooks: plugins/google_meet/plugin.yaml
  hooks: plugins/memory/byterover/plugin.yaml
  hooks: plugins/memory/hindsight/plugin.yaml
  hooks: plugins/memory/holographic/plugin.yaml
  hooks: plugins/memory/honcho/plugin.yaml
  hooks: plugins/memory/openviking/plugin.yaml
  hooks: plugins/observability/langfuse/plugin.yaml
  hooks: plugins/observability/nemo_relay/plugin.yaml
  hooks: plugins/security-guidance/plugin.yaml
```

**即:代码读的那个键没人写,清单写的那个键没人读。** 本片两份 observability 清单都在这 10 份里。

**负结论的搜索面(这条断言的可信度就等于这次搜索的完备性)。** 要证明 `hooks:` 这个**清单键**
无人消费,难点是 `"hooks"` 这个字符串在仓库里到处都是(config.yaml 有个同名的 shell-hooks 段)。
所以搜索分两步:

- 第一步,**谁读 `plugin.yaml`**:`grep -rn "plugin\.yaml" --include=*.py .`(排除 `tests/`),
  命中 8 个消费者模块 —— `hermes_cli/plugins.py`、`plugins_cmd.py`、`config.py`、
  `memory_setup.py`、`web_server.py`、`config_migrations.py`、`gateway/config.py`、`update_cmd.py`。
- 第二步,**这 8 个里谁取 `hooks` 键**:`grep -rn '"hooks"\|\x27hooks\x27' --include=*.py .`(排除 `tests/`),
  12 处命中**逐处判定,无一是清单键**,分三类:

| 类别 | 命中处(全路径) | 为什么不是清单键 |
|---|---|---|
| **config.yaml 的 `hooks` 段** | `hermes_cli/config.py:4658`、`hermes_cli/config_defaults.py:2119`、`hermes_cli/web_server.py:13075`、`hermes_cli/web_server.py:13078`、`hermes_cli/web_server.py:13114`、`hermes_cli/web_server.py:13126`、`agent/shell_hooks.py:239`、`agent/outbound_webhooks.py:175`、`tools/hook_output_spill.py:87`:`        hooks = cfg.get("hooks") if isinstance(cfg, dict) else None` | 读的是用户配置文件,不是插件清单 |
| **CLI 子命令名** | `hermes_cli/main.py:10609`、`hermes_cli/subcommands/hooks.py:16`:`        "hooks",` | 是命令字符串,不是 YAML 键 |
| **运行时已注册数** | `hermes_cli/plugins.py:2016`:`                    "hooks": len(loaded.hooks_registered),`、`cli.py:10235`:`                        if info.get("hooks"):` | 数的是 `register_hook` 实际挂上的回调条数 |
- **排除**:`tests/` 与 vendored 的 `hermes_agent-0.20.0/`(基线里的一份旧版本副本)。

**影响面(不夸大)。** 钩子的真实注册走 `ctx.register_hook`,所以**功能不受影响** ——
§2.3 已实测两个插件 16 条钩子全部正常注册。真正的代价是:
`hermes plugins list` 那一栏的 "N hooks" 只能在插件**已加载**后显示,
而 `provides_hooks` 本是为"未加载也能公示"存在的
(参照同一机制的 `provides_tools`,它在 `hermes_cli/plugins_cmd.py:1855`:`                for tool_name in manifest.get("provides_tools") or []:` 处真被读到了)。
**所以这是一条 `provides_tools` 有、`provides_hooks` 没有的能力缺口,不是崩溃。**

### ▲ H-R11F-D-b:两页开发者文档给同一个字段规定了两个不同的键名

`website/docs/developer-guide/plugins/index.md:71 @ 863e313`

> provides_hooks:
>   - post_tool_call

同页 `:75` 解释这个字段是干什么的:

`website/docs/developer-guide/plugins/index.md:75 @ 863e313`

> This tells Hermes: "I'm a plugin called calculator, I provide tools and hooks." The `provides_tools` and `provides_hooks` fields are lists of what the plugin registers.

而另一页在 `## plugin.yaml` 这个标题下(标题本身就是断言的一部分:它宣称下面这段**是**一份清单)
给的是 `hooks:`:

`website/docs/developer-guide/memory-provider-plugin.md:148 @ 863e313`

> hooks:
>   - on_session_end    # list hooks you implement

**两页对同一个字段各说各话,且仓库的实际做法(10 份清单)跟着后一页走、
加载器跟着前一页走。** 判为地图级 ▲:冲突发生在 `website/docs/` 内部并与代码交叉,
不是"字面为真但保守"。

### ▲(码内) H-R11F-D-c:drain 的模块 docstring 说"五个交互方法都抛 NotImplementedError",实际只有三个

`plugins/dashboard_auth/drain/__init__.py:14 @ 863e313`

```
``drain-control`` principal. It is NOT an interactive identity provider — there
is no login, cookie, session, or refresh. It implements ONLY the token
capability (``supports_token = True`` + ``verify_token``); the five interactive
ABC methods raise ``NotImplementedError``.
```

§2.4 的矩阵实测:`stub-raises(3)` —— 只有 `start_login` / `complete_login` / `refresh_session` 抛。
另外两个是**有意的空实现**,而且代码里就地写明了为什么:

`plugins/dashboard_auth/drain/__init__.py:192 @ 863e313`

```
    def verify_session(self, *, access_token: str) -> Optional[Session]:
        # Not a cookie-session provider — it never mints a Session, so it can
        # never recognise a session cookie. Return None (don't raise) so it
        # stacks harmlessly in the cookie-verify loop.
        return None
```

`revoke_session`(`:203-204`)同理,`return None`。

**这不是文字游戏:如果 docstring 说的是真的,dashboard 就会坏掉。** cookie 验证循环会
逐个咨询 provider;drain 若在这里抛异常,任何一次 cookie 校验都会被它炸掉。
**docstring 描述的行为恰好是一个 bug**,而代码是对的 —— 178 行外的那句注释,
是这个模块里唯一说清这件事的地方。记 ▲(码内),与地图级 ▲ 分开计数。

### ▲(码内) H-R11F-D-d:kanban 插件里一句注释说 HTTP 路由走"plugin-bypass",而同文件 40 行上方说的正相反

`plugins/kanban/dashboard/plugin_api.py:59 @ 863e313`

```
# ---------------------------------------------------------------------------
# Auth helper — WebSocket only (HTTP routes live behind the dashboard's
# existing plugin-bypass; this is documented above).
# ---------------------------------------------------------------------------
```

它说的 "documented above" 指的是模块 docstring,而那段说的是**没有 bypass 了**:

`plugins/kanban/dashboard/plugin_api.py:16 @ 863e313`

> Plugin HTTP routes go through the dashboard's session-token auth middleware
> (``web_server.auth_middleware``) just like core API routes — every
> ``/api/plugins/...`` request must present the session bearer token (or the
> session cookie set when you load the dashboard HTML).

同段 `:29-33` 还专门说 "plugin routes are **no longer** an unauthenticated exception"。
代码侧 §2.0 已实证:`/api/plugins/` 不在 `PUBLIC_API_PATHS` 的 8 条里,
`hermes_cli/web_server.py:665` 对全部 `/api/` 一视同仁。

**结论:`:60-61` 那句 "plugin-bypass" 是安全加固前的遗留注释。** 危害在于它会诱使
下一个改这个文件的人以为"HTTP 那边反正没鉴权",从而在新路由上省掉本该有的检查。
记 ▲(码内)。

### ◇ H-R11F-D-f:langfuse 接受 5 个清单未声明的裸 `LANGFUSE_*` 环境变量

见 §2.5。清单只声明 `HERMES_LANGFUSE_PUBLIC_KEY` / `_SECRET_KEY`,
代码额外接受官方 SDK 命名的 `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` /
`LANGFUSE_BASE_URL` / `LANGFUSE_ENV` / `LANGFUSE_RELEASE` 作为回落:
`plugins/observability/langfuse/__init__.py:169`:`    secret_key = _env("HERMES_LANGFUSE_SECRET_KEY") or _env("LANGFUSE_SECRET_KEY")`。
**代码有、清单无**,记 ◇。后果:只设了官方变量名的用户会在安装向导里被告知"缺凭据",
而插件其实能跑。

**本片记号计数:■ 1 / 地图级 ▲ 1 / ▲(码内) 2 / ◇ 1。**

---

## 6. 移交项

| 案号 | 现象(锚点 + 一句话) | 去向建议 |
|---|---|---|
| `H-R11F-D-a` | `hermes_cli/plugins.py:1664`:`                provides_hooks=data.get("provides_hooks", []),` 读的键 0 份清单在写;10 份清单写的 `hooks:` 无人读 | 主线定案:算 ■ 还是"未完成的特性" |
| `H-R11F-D-b` | `website/docs/developer-guide/memory-provider-plugin.md:148`:`hooks:` 与 `website/docs/developer-guide/plugins/index.md:71`:`provides_hooks:` 规定了两个键名 | 计入本轮地图级 ▲ |
| `H-R11F-D-c` | `plugins/dashboard_auth/drain/__init__.py:192`:`    def verify_session(self, *, access_token: str) -> Optional[Session]:` 返回 None 而非抛异常,与 `:16` 的 docstring 矛盾 | 计入 ▲(码内) |
| `H-R11F-D-d` | `plugins/kanban/dashboard/plugin_api.py:60`:`# Auth helper — WebSocket only (HTTP routes live behind the dashboard's` 说有 plugin-bypass,同文件 `:16` 说没有 | 计入 ▲(码内) |
| `H-R11F-D-e` | 判据修订建议:`plugins/kanban/dashboard/dist/index.js:8`:` * Plain IIFE, no build step. Uses window.__HERMES_PLUGIN_SDK__ for React +` —— `dist/` 不等于构建产物 | 主线采纳后写进下一份派工书 |
| `H-R11F-D-f` | `plugins/observability/langfuse/__init__.py:169`:`    secret_key = _env("HERMES_LANGFUSE_SECRET_KEY") or _env("LANGFUSE_SECRET_KEY")` 接受清单未声明的 env | 计入 ◇ |
| `H-R11F-D-g` | **未查**:`plugins/hermes-achievements/dashboard/plugin_api.py:1042`:`@router.post("/reset-state")` 是破坏性端点(清空解锁记录),只受 dashboard 会话令牌保护、无二次确认;本片未评估其风险等级 | 若开安全专题轮,与其他破坏性插件端点一起看 |
| `H-R11F-D-h` | **未查**:`plugins/kanban/systemd/hermes-kanban-dispatcher.service:1`:`# DEPRECATED — the kanban dispatcher now runs inside the gateway by` 自称废弃,本片未核实"两个调度器同跑"是否真被代码拦住 | 与 kanban 调度器专题合并 |

---

## 7. 判据自报

| 判据 | 达成情况 | 依据 |
|---|---|---|
| **1 点名到位** | **达成** | §1,29/29 全路径 + 一句话角色 |
| **2 接缝穷举** | **达成** | 六个接缝,全部给了机械枚举命令与条数:路由 51、清单键 8 份、钩子 16、ABC 矩阵 4×7、env 面、前端产物 4 |
| **3 端到端链** | **达成** | §3,七跳全部带锚点,起于鼠标松开终于同一页面 |
| **4 逐字取证** | **达成** | 36 个逐字围栏块 + 6 处引用块(要求 ≥2);可校验比例 **82.4%**,表格锚点 **67/67** |
| **5 记号** | **达成** | ■1 / ▲1 / ▲(码内)2 / ◇1,共 5 条全部带锚点 |

**判据修订建议**(派工书 §1 明写这是验收项):见 §2.6 的 `H-R11F-D-e`。

---

## 完成信号

**片号**:R11F 片 D —— `plugins/{kanban, hermes-achievements, dashboard_auth, observability}`
(29 文件 / 16,993 行)。

**产出文件**:

- 底稿 `notes/r11f-raw-d-dashboard-plugins.md`(本文件)
- 探针 `data/r11f/probes/d_route_surface.py`(HTTP 路由面 AST 枚举,含形参表)
- 探针 `data/r11f/probes/d_manifest_surface.py`(清单键面 + hooks 声明/注册对账 + 全仓普查)
- 探针 `data/r11f/probes/d_auth_provider_matrix.py`(dashboard_auth ABC 实现面矩阵)
- 数据 `data/r11f/d/route-surface.tsv`(51 条路由全表 + 形参)
- 数据 `data/r11f/d/route-surface.summary.txt`(枚举自检:每文件条数、owner 唯一性)
- 数据 `data/r11f/d/route-table.md`(机械生成的路由表 markdown 行,§2.1 表格的来源)

**五条判据**:1 达成 / 2 达成 / 3 达成 / 4 达成 / 5 达成。**无"部分达成"项。**

**点名文件数**:**29 / 29**,全部给出全路径 + 一句话角色(§1);
分组 kanban 5 / hermes-achievements 10 / dashboard_auth 8 / observability 6,
命令对账见 §1.2 末尾。

**关卡读数**(本底稿单文件):

```text
verify_citations.py        citations=51  OK=42  UNCHECKED=9   可校验比例 82.4%(下限 70%)
                           table_anchors=67  OK=67(声明式表格锚点,零 TABLE-UNCHECKED)
                           MISMATCH=0  BLOCK-DRIFT=0  TABLE-DRIFT=0
verify_evidence_commands.py paired=12  unpaired=0  differing=0  timedout=0
```

**给主线的一条环境观察(不是本片结论)**:在本片收工时刻跑**全强制范围**
(`chapters/*.md notes/r11f-*.md`)得到 `paired=94 unpaired=0 differing=6`,
其中 **6 条差异全部不在本文件**(本文件单独跑 `differing=0`)。逐份定位到
`notes/r11f-raw-f-longtail-and-plugin-core.md` 有 3 条,余下 3 条落在片 B 的底稿
(该文件单跑超过 110 秒未跑完,未取到确切读数)。
**这不构成"那两片有问题"的判断** —— 按 CLAUDE.md「异步产出的完成判定只以完成信号为准,
不以产物形态推断」,那两份底稿在本片收工时可能仍在写。**记在这里只是让主线在装订前知道要复跑。**

**接缝枚举命令与条数**(六个接缝):

1. **HTTP 路由面 —— 51 条**(kanban 45 + achievements 6)
   `python3 data/r11f/probes/d_route_surface.py /home/user/hermes-agent --tsv | awk -F'\t' 'NR>1{n[$1]++; t++} END{...}'`
   —— 方法分布 `GET` 22 / `POST` 17 / `DELETE` 5 / `PATCH` 4 / `PUT` 1 / `WEBSOCKET` 1。
   板子作用域维度:31 条受板子约束(30 走签名参数 + WS 自读),14 条按设计跨板。
2. **清单键面 —— 8 份 manifest**(6 份 `plugin.yaml` 用 7 个键;2 份 `manifest.json` 用 9 个键,键集相同)
   `python3 data/r11f/probes/d_manifest_surface.py /home/user/hermes-agent slice`
3. **钩子注册面 —— 16 条**(langfuse 6 + nemo_relay 10),清单声明与代码注册**零差集**
   `python3 data/r11f/probes/d_manifest_surface.py /home/user/hermes-agent hooks`
4. **dashboard_auth ABC 实现面 —— 4 provider × 7 方法**(5 抽象 + 2 可选)+ 3 个能力开关;
   `extra-public` 全 0,契约面闭合
   `python3 data/r11f/probes/d_auth_provider_matrix.py /home/user/hermes-agent`
5. **免鉴权名单 —— 8 条**,`/api/plugins/*` 不在其中
   `grep -o '"/api/[a-z/]*"' /home/user/hermes-agent/hermes_cli/dashboard_auth/public_paths.py | sort`
6. **前端产物面 —— 4 个 `dist/` 文件**,零 source map、零构建配置、零对应源码树
   `for f in ...; do printf ... maxlen ... sourcemap ...; done; find ... | wc -l`

**全仓普查(为 ■ 服务)**:97 份 `plugin.yaml` 中,写 `hooks:` 的 **10** 份、
写 `provides_hooks:` 的 **0** 份
(`python3 data/r11f/probes/d_manifest_surface.py /home/user/hermes-agent census`)。

**新铸记号编号**:

| 案号 | 类型 | 一句话 |
|---|---|---|
| `H-R11F-D-a` | ■ | `plugin.yaml` 的 `hooks:` 键 10 份在写、0 行在读;加载器读的 `provides_hooks` 0 份在写 |
| `H-R11F-D-b` | ▲(地图级) | 两页 developer-guide 给同一字段规定了两个键名 |
| `H-R11F-D-c` | ▲(码内) | drain docstring 说五个交互方法都抛异常,实际三抛两返 None |
| `H-R11F-D-d` | ▲(码内) | kanban 注释说 HTTP 路由走 plugin-bypass,同文件 40 行上方与代码均相反 |
| `H-R11F-D-e` | 判据修订建议 | `dist/` 不等于构建产物;建议改为按文件实测(三条并列判据) |
| `H-R11F-D-f` | ◇ | langfuse 接受 5 个清单未声明的裸 `LANGFUSE_*` env |
| `H-R11F-D-g` | 移交(未查) | achievements `POST /reset-state` 是破坏性端点,未评估风险等级 |
| `H-R11F-D-h` | 移交(未查) | kanban systemd 单元自称废弃,未核实双调度器是否真被拦 |

**记号计数**:■ 1 / 地图级 ▲ 1 / **▲(码内) 2**(分开计数)/ ◇ 1;另有判据修订建议 1 条、未查移交 2 条。

**边界自查**:基线 `/home/user/hermes-agent` 全程只读,取证前后
`git -C /home/user/hermes-agent status --porcelain` 均为空;执行基线代码的唯一动作
(跑 achievements 自带测试)带 `HERMES_DISABLE_LAZY_INSTALLS=1`,venv 仍为 **87 包**;
未改 `scripts/`、`chapters/`、台账、`CLAUDE.md`,未动 `data/inflight/*.claim`,
未安装任何包、未运行 npm/node。
