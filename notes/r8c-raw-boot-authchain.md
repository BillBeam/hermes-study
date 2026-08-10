# R8C 底稿 · `hermes_cli/web_server.py` 1–830 —— 启动、事件状态、session token、HTTP 中间件链

> 溯源约定:凡对 hermes-agent 行为的断言,**锚点 `路径:行号 @ 863e313` 单独成行,置于代码块之前**,
> 块内为基线逐字原文。非源码块(实测输出、判定表、我自己的推演)用 ```text / ```console / ```verify
> 围栏声明。路径一律从基线仓库根解析。
>
> 记号:▲ = 文档/注释所述与代码矛盾;◇ = 代码有、文档无;■ = 代码缺陷;◎ = 文档成立但显著保守。

## 0. 取证条件

```console
$ git -C /home/user/hermes-agent rev-parse HEAD
863e31318553cda8ad61df681d08175364d4164b
$ git -C /home/user/hermes-agent status --porcelain     # 开工前 + 收工后各跑一次,两次均空
(空)
```

对基线只做 Read/Grep/sed 纯读。实测用的 venv 是 `/home/user/hermes-venv`
(starlette 1.3.1 / fastapi 0.141.1),实测脚本写在 scratchpad、
`cwd` 设在 scratchpad、`HERMES_HOME` 指向 scratchpad、`PYTHONDONTWRITEBYTECODE=1`,
不向基线写任何字节(收工后 `git status --porcelain` 复核为空,见上)。

全文件 17732 行;本段覆盖 1–830 行,以及为把判定链走完而必须追出去的
`hermes_cli/dashboard_auth/{public_paths,middleware,token_auth}.py`、
`start_server` 的相关片段(:17423–17562)、`approve_pairing` 路由本体(:12321)。

---

## 1. 核心问题一:六个 HTTP 中间件的实际执行顺序

### 1.1 结论先给

**`@app.middleware("http")` 是「后注册先执行」(LIFO / 栈式)。** 但这句话对本文件还不够用——
本文件除了 6 个 `@app.middleware("http")`,还有 1 个用 `app.add_middleware()` 注册的 `CORSMiddleware`,
它**注册得最早,因此跑得最晚(最内层)**。真实的七层顺序(外 → 内)是:

```text
请求进来
  1. _dashboard_health_middleware   (:751)  ← 最外层
  2. _token_auth_seam               (:674)
  3. auth_middleware                (:650)
  4. _dashboard_auth_gate           (:644)
  5. _plugin_api_runtime_gate       (:568)
  6. host_header_middleware         (:538)
  7. CORSMiddleware                 (:373)  ← 最内层,紧贴路由
  → 路由 / 处理器
响应回去时逆序穿出(7 → 1)
```

注意这与"注册顺序 = 执行顺序"的直觉**完全相反**,也与文件里 :640 那条注释所说的顺序**完全相反**(见 §5 ▲-1)。

### 1.2 机制:三段代码把 LIFO 定死了

FastAPI/Starlette 不在基线仓库里,所以下面这三段引自 venv 的第三方库
(**不是基线,不带 `@ 863e313` 锚点**,故用 ```text 围栏声明):

第一段——FastAPI 的装饰器只是 `add_middleware` 的糖:

```text
# /home/user/hermes-venv/lib/python3.11/site-packages/fastapi/applications.py:4723-4727
        def decorator(func: DecoratedCallable) -> DecoratedCallable:
            self.add_middleware(BaseHTTPMiddleware, dispatch=func)
            return func

        return decorator
```

第二段——`add_middleware` 是 **`insert(0, ...)`**,即每次注册都插到列表**最前面**:

```text
# /home/user/hermes-venv/lib/python3.11/site-packages/starlette/applications.py:98-101
    def add_middleware(self, middleware_class: _MiddlewareFactory[P], *args: P.args, **kwargs: P.kwargs) -> None:
        if self.middleware_stack is not None:  # pragma: no cover
            raise RuntimeError("Cannot add middleware after an application has started")
        self.user_middleware.insert(0, Middleware(middleware_class, *args, **kwargs))
```

第三段——建栈时对列表 **`reversed()`** 逐个包住 router:

```text
# /home/user/hermes-venv/lib/python3.11/site-packages/starlette/applications.py:57-77
    def build_middleware_stack(self) -> ASGIApp:
        ...
        middleware = (
            [Middleware(ServerErrorMiddleware, handler=error_handler, debug=debug)]
            + self.user_middleware
            + [Middleware(ExceptionMiddleware, handlers=exception_handlers, debug=debug)]
        )

        app = self.router
        for cls, args, kwargs in reversed(middleware):
            app = cls(app, *args, **kwargs)
        return app
```

推演(两次反转的净效果):

```verify
注册顺序:        CORS, host_header, plugin_gate, auth_gate, auth_mw, token_seam, health
insert(0) 之后
user_middleware: [health, token_seam, auth_mw, auth_gate, plugin_gate, host_header, CORS]
                   idx0                                                            idx6

reversed() 从尾往头包:先包 CORS(最贴 router = 最内),最后包 health(最外)
=> 洋葱层:  health(token_seam(auth_mw(auth_gate(plugin_gate(host_header(CORS(router)))))))
=> 执行顺序: idx0 先跑。即「user_middleware 的下标顺序 = 执行顺序」,
             而下标顺序 = 注册顺序的逆序。
=> 一句话:**最后注册的先执行**;用 add_middleware 早早注册的 CORS 反而最内。
```

### 1.3 实测(对**真实的 `hermes_cli.web_server.app`**,不是玩具 app)

```console
$ HERMES_HOME=<scratch> PYTHONDONTWRITEBYTECODE=1 python  # 见 §0
A) middleware stack of the REAL app (index 0 = outermost = runs first):
   [0] _dashboard_health_middleware
   [1] _token_auth_seam
   [2] auth_middleware
   [3] _dashboard_auth_gate
   [4] _plugin_api_runtime_gate
   [5] host_header_middleware
   [6] CORSMiddleware
```

同一机制在玩具 app 上打过 enter/exit 轨迹,`enter` 序列与下标序列一致、`exit` 逆序,
确认「下标 0 = 最外 = 先执行」不是巧合:

```text
enter F(last-registered) → E → D → C → B → A(first-registered)
exit  A → B → C → D → E → F
```

### 1.4 注册点逐个取证

`CORSMiddleware`——本文件唯一一个用 `add_middleware` 注册的,也是唯一一个非 `BaseHTTPMiddleware` 的:

`hermes_cli/web_server.py:373`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)
```

六个 `@app.middleware("http")`,按源码行号(= 注册顺序)升序:

`hermes_cli/web_server.py:538`

```python
@app.middleware("http")
async def host_header_middleware(request: Request, call_next):
```

`hermes_cli/web_server.py:568`

```python
@app.middleware("http")
async def _plugin_api_runtime_gate(request: Request, call_next):
```

`hermes_cli/web_server.py:644`

```python
@app.middleware("http")
async def _dashboard_auth_gate(request: Request, call_next):
    from hermes_cli.dashboard_auth.middleware import gated_auth_middleware
    return await gated_auth_middleware(request, call_next)
```

`hermes_cli/web_server.py:650`

```python
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
```

`hermes_cli/web_server.py:674`

```python
@app.middleware("http")
async def _token_auth_seam(request: Request, call_next):
```

`hermes_cli/web_server.py:751`

```python
@app.middleware("http")
async def _dashboard_health_middleware(request: Request, call_next):
```

**负结论:全仓没有第二处往这个 `app` 上挂中间件的地方。** 搜索面:
`grep -n 'app.middleware(\|app.add_middleware('` 覆盖 `hermes_cli/web_server.py` 全文
(命中 7 处,即上列 1 + 6);再用
`grep -rn 'add_middleware\|\.middleware("http")' --include=*.py hermes_cli/ gateway/ plugins/ tools/`
排除 `web_server.py` 自身后**零命中**。未搜 `tests/`(测试挂中间件不影响生产链)、
`web/`(TS 前端)、`apps/desktop/`(TS)。

### 1.5 逐层放行/拦截判据

| # | 层(外→内) | 只在什么条件下**动手** | 动手时返回 | 否则 |
|---|---|---|---|---|
| 1 | `_dashboard_health_middleware` :751 | 从不拦截 | —(只计数并 re-raise) | 透传 |
| 2 | `_token_auth_seam` :674 | `is_token_route(path)` 为真(精确匹配已注册路径) | 401 / 503;成功则打 `token_authenticated` 标 | 透传 |
| 3 | `auth_middleware` :650 | `auth_required` 为假 **且** `path.startswith("/api/")` **且** 不在 `_PUBLIC_API_PATHS` **且** 不是 `/api/mcp/oauth/callback/*` **且** 无有效 session token / query token | `401 {"detail":"Unauthorized"}` | 透传 |
| 4 | `_dashboard_auth_gate` :644 | `auth_required` 为真 **且** 非 `token_authenticated` **且** `_path_is_public(path)` 为假 **且** 无有效 bearer/cookie | 401 JSON(`/api/*`)或 302 → `/login`(HTML);provider 不可达时 503 | 透传 |
| 5 | `_plugin_api_runtime_gate` :568 | `path.startswith("/api/plugins/")` **且** 请求已认证 **且** 该插件被禁用/未启用 | `404 {"detail":"Plugin not found"}` | 透传 |
| 6 | `host_header_middleware` :538 | `app.state.bound_host` 已设 **且** `_is_accepted_host(Host, bound_host)` 为假 | 400 Invalid Host header | 透传 |
| 7 | `CORSMiddleware` :373 | 跨源 OPTIONS 预检 / 加响应头 | 预检响应 | 透传 |

第 3 层的判据原文:

`hermes_cli/web_server.py:663`

```python
    path = request.url.path
    is_mcp_oauth_callback = path.startswith("/api/mcp/oauth/callback/")
    if path.startswith("/api/") and path not in _PUBLIC_API_PATHS and not is_mcp_oauth_callback:
        if not _has_valid_session_token(request) and not _has_valid_query_token(request, path):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized"},
            )
    return await call_next(request)
```

第 3 层的两条前置短路(**这两条是理解整条链的关键**:第 2、4 层的"已认证"标记会让第 3 层直接让路):

`hermes_cli/web_server.py:656`

```python
    if getattr(request.state, "token_authenticated", False):
        return await call_next(request)
    # When the OAuth gate is active, cookie-based auth (gated_auth_middleware
    # above) is authoritative.  The legacy _SESSION_TOKEN path is loopback-only
    # and is skipped here so the gate's session attachment isn't overridden.
    if getattr(request.app.state, "auth_required", False):
        return await call_next(request)
```

第 4 层的判据(实现在另一个文件里,`_dashboard_auth_gate` 只是个转发壳):

`hermes_cli/dashboard_auth/middleware.py:332`

```python
    if not getattr(request.app.state, "auth_required", False):
        return await call_next(request)
```

`hermes_cli/dashboard_auth/middleware.py:339`

```python
    if getattr(request.state, "token_authenticated", False):
        return await call_next(request)
```

`hermes_cli/dashboard_auth/middleware.py:343`

```python
    if _path_is_public(path):
        return await call_next(request)
```

第 2 层的判据:

`hermes_cli/dashboard_auth/token_auth.py:162`

```python
    path = request.url.path
    if not is_token_route(path):
        return await call_next(request)
```

### 1.6 一个结构性事实:WebSocket **完全不经过**这六层

`BaseHTTPMiddleware`(六个 `@app.middleware("http")` 全部是它)在非 `http` scope 上直接放行:

```text
# /home/user/hermes-venv/lib/python3.11/site-packages/starlette/middleware/base.py:101-104
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
```

所以 `/api/ws`、`/api/pty`、`/api/pub`、插件的 `/events` 这些 WS 升级请求
**既不过 `auth_middleware`,也不过 `host_header_middleware`**。这正是本文件在 14500+ 另起
一整套 WS 专用守卫(`_ws_client_reason` / `_ws_host_origin_is_allowed` / ticket 校验)的原因。
仓库自己把这条契约钉成了测试:

`tests/hermes_cli/test_web_server.py:3414`

```python
    def test_plugin_websocket_unaffected_by_http_middleware(self):
```

---

## 2. 核心问题二:移交项 H-3 —— `/api/pairing/approve` 到底由哪一层保证

### 2.1 先修一个锚点

R8A 移交时写的锚点是 `hermes_cli/web_server.py:12320`,基线上 12320 是空行;
真实位置是 **12321(装饰器)/ 12322(函数)**:

`hermes_cli/web_server.py:12321`

```python
@app.post("/api/pairing/approve")
async def approve_pairing(body: PairingApprove):
    store = _pairing_store(body.profile)
```

### 2.2 路由本体:**零**自带鉴权

`approve_pairing` 的签名只有 `body: PairingApprove`——**没有 `request: Request` 参数,
没有 `Depends(...)`,函数体里没有调用 `_require_token`**。也就是说这个路由的全部鉴权
100% 来自中间件链,路由本身对"谁在调我"一无所知。

**负结论:这不是我漏看了。** 搜索面:`sed -n '12321,12357p' hermes_cli/web_server.py` 读了函数全文
(装饰器 12321、函数体 12322–12354,末尾是 `raise HTTPException(status_code=404, ...)`,
下一个路由 `@app.post("/api/pairing/revoke")` 在 12357);
`grep -rn "pairing/approve"` 覆盖全仓 `*.py/*.ts/*.tsx/*.md`,命中 6 处
(路由定义 1、前端 `web/src/lib/api.ts:1089`、桌面端 `apps/desktop/src/hermes.ts:1196`、
测试 2、文档 `website/docs/user-guide/features/web-dashboard.md:528`),
其中**没有任何一处**给它加过路由级依赖。

对照:同文件里确实存在路由级鉴权这一手段(`_require_token`,:431),它被别的敏感端点用。
`approve_pairing` 没用。

`hermes_cli/web_server.py:431`

```python
def _require_token(request: Request) -> None:
```

### 2.3 逐层判定:每个豁免名单都不包含它

**(a) 第 2 层 `_token_auth_seam` —— 不是 token 路由。**
token 路由是**运行时注册**的集合,不是常量:

`hermes_cli/dashboard_auth/token_auth.py:56`

```python
_token_routes: set[str] = set()
```

`hermes_cli/dashboard_auth/token_auth.py:60`

```python
def register_token_route(path: str) -> None:
```

**负结论:全仓只有一个生产调用方,注册的是 `/api/gateway/drain`。**
搜索面:`grep -rn "register_token_route" --include=*.py .`(全仓,含 tests),命中 6 处 =
定义处 2 + docstring 引用 2 + 测试 1(`tests/hermes_cli/test_dashboard_token_auth.py:230`,注册
`/api/gateway/drain`)+ 生产 1:

`plugins/dashboard_auth/drain/__init__.py:280`

```python
        register_token_route(DRAIN_ROUTE_PATH)
```

`plugins/dashboard_auth/drain/__init__.py:85`

```python
DRAIN_ROUTE_PATH = "/api/gateway/drain"
```

实测确认(对真实 app):`is_token_route("/api/pairing/approve") == False`。

**(b) 第 3 层 `auth_middleware` 的 `PUBLIC_PATHS` —— 不包含它。**
名单不在 web_server.py 里,而是从 `dashboard_auth.public_paths` 导入的共享 frozenset
(:393–395 导入,别名 `_PUBLIC_API_PATHS`):

`hermes_cli/dashboard_auth/public_paths.py:33`

```python
PUBLIC_API_PATHS: frozenset[str] = frozenset({
```

名单全量共 **8 条**(逐字列出,以免"我没看见"):
`/api/health`、`/api/status`、`/api/config/defaults`、`/api/config/schema`、
`/api/model/info`、`/api/dashboard/themes`、`/api/dashboard/plugins`、`/api/cron/fire`。
`/api/pairing/approve` 不在其中。**且匹配是精确相等(`path not in ...`),不是前缀展开**,
所以不存在"父路径被放行连带子路径"的口子。

`/api/cron/fire` 在名单里是有意为之——它自带 NAS 签发的短时 JWT 作为真正的鉴权边界,
名单只是让 bearer-only 回调不被 cookie gate 拦掉:

`hermes_cli/dashboard_auth/public_paths.py:54`

```python
    # Chronos managed-cron fire webhook (NAS -> agent). NOT cookie-gated: it
    # carries its own short-lived NAS-minted JWT (purpose=cron_fire), which the
    # handler verifies as the real auth. Must bypass the dashboard auth gate so
    # the NAS relay's bearer-only callback reaches the verifier instead of a
    # 401 no_cookie. The JWT — not this allowlist — is the security boundary.
    "/api/cron/fire",
```

**(c) 第 3 层的另一个口子 `_has_valid_query_token` —— 也不包含它。**

`hermes_cli/web_server.py:421`

```python
_QUERY_TOKEN_API_PATHS: frozenset[str] = frozenset({"/api/files/download"})
```

**(d) 第 4 层 `_dashboard_auth_gate` 的 `_path_is_public` —— 也不包含它。**
它是"`PUBLIC_API_PATHS` 精确匹配 **或** `_GATE_PUBLIC_PREFIXES` 前缀匹配":

`hermes_cli/dashboard_auth/middleware.py:81`

```python
    if path in PUBLIC_API_PATHS:
        return True
    return any(
        path == prefix or path.startswith(prefix)
        for prefix in _GATE_PUBLIC_PREFIXES
    )
```

`hermes_cli/dashboard_auth/middleware.py:49`

```python
_GATE_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/auth/login",
    "/auth/callback",
    "/auth/native/authorize",
    "/auth/native/token",
    "/auth/native/refresh",
    "/auth/password-login",
    "/auth/logout",
    "/login",
    "/api/auth/providers",
    "/api/mcp/oauth/callback/",
    "/assets/",
    "/favicon.ico",
    "/ds-assets/",
    "/fonts/",
    "/fonts-terminal/",
)
```

15 条,没有任何一条是 `/api/pairing/approve` 的前缀。实测确认
`_path_is_public("/api/pairing/approve") == False`。

### 2.4 `should_require_auth` 在什么绑定地址下让整条 token 鉴权被跳过

先看它自己:

`hermes_cli/web_server.py:467`

```python
_LOOPBACK_HOST_VALUES: frozenset = frozenset({
    "localhost", "127.0.0.1", "::1",
})
```

`hermes_cli/web_server.py:491`

```python
    return host not in _LOOPBACK_HOST_VALUES
```

注意函数签名有 `allow_public` 参数(`--insecure`),但**函数体根本没读它**——它被显式作废了:

`hermes_cli/web_server.py:483`

```python
    ``allow_public`` (the legacy ``--insecure`` escape hatch) NO LONGER disables
    the gate. It is accepted for backward-compat with old launch scripts and
    desktop shells but is ignored: a non-loopback bind ALWAYS requires an auth
    provider (OAuth or the bundled password provider). This closes the
    unauthenticated-public-dashboard hole behind the June 2026 ``hermes-0day``
    MCP-persistence campaign, where ``--insecure --host 0.0.0.0`` left the
    config/MCP/agent surface open to internet scanners.
```

实测真值表(第二列是传 `allow_public=True` 的结果,证明它确实无效):

```console
should_require_auth('127.0.0.1'     ) = False   (allow_public=True -> False)
should_require_auth('localhost'     ) = False   (allow_public=True -> False)
should_require_auth('::1'           ) = False   (allow_public=True -> False)
should_require_auth('0.0.0.0'       ) = True    (allow_public=True -> True)
should_require_auth('::'            ) = True    (allow_public=True -> True)
should_require_auth('192.168.1.50'  ) = True    (allow_public=True -> True)
should_require_auth('100.64.0.1'    ) = True    (allow_public=True -> True)
should_require_auth('10.0.0.5'      ) = True    (allow_public=True -> True)
should_require_auth('LOCALHOST'     ) = True    (allow_public=True -> True)   ← 大小写不折叠,fail-safe 方向
should_require_auth('127.0.0.2'     ) = True    (allow_public=True -> True)   ← 只有那 3 个字面量算 loopback
```

**关键**:`auth_required=False`(= 第 4 层整体空转)**只在 3 个字面量 host 上发生**,
而这 3 个 host 意味着 socket 只监听回环——局域网根本连不上 TCP。
反过来,`auth_required=True`(= 第 3 层整体空转、token 鉴权被跳过)只在非回环绑定上发生,
而那时第 4 层 cookie gate 是接管方。**两条链是互补的,不存在同时空转的窗口。**

绑定值写进 `app.state` 的地方,以及"没有 provider 就拒绝起服务"的 fail-closed:

`hermes_cli/web_server.py:17463`

```python
    app.state.auth_required = should_require_auth(host)
```

`hermes_cli/web_server.py:17478`

```python
    if app.state.auth_required:
        # The gate engages on every non-loopback bind. Require at least one
        # provider to be registered, else fail closed — there is no longer an
        # escape hatch that serves the dashboard without authentication.
        from hermes_cli.dashboard_auth import list_providers
        if not list_providers():
```

`hermes_cli/web_server.py:17549`

```python
            raise SystemExit(
                f"Refusing to bind dashboard to {host} — the auth gate "
                f"engages on non-loopback binds, but no auth providers are "
                f"registered.\n\n" + _fix_hint
            )
```

`hermes_cli/web_server.py:17562`

```python
    app.state.bound_host = host
```

默认绑定值(函数默认参数与 CLI 默认值一致,都是 `127.0.0.1`):

`hermes_cli/web_server.py:17424`

```python
    host: str = "127.0.0.1",
```

`hermes_cli/subcommands/dashboard.py:30`

```python
        "--host", default="127.0.0.1", help="Host (default 127.0.0.1)"
```

### 2.5 H-3 判定表(每种绑定组合)

```verify
记号:PASS=放行进入下一层  BLOCK=在此层返回错误  —=该层空转
路径固定为 POST /api/pairing/approve,请求方为「未认证的局域网主机」

┌─ A. bound_host ∈ {127.0.0.1, localhost, ::1}(默认;auth_required=False)
│   TCP 层:socket 只监听回环 → 局域网主机连不上,请求根本到不了 ASGI。
│   即便通过同机反代/SSH 隧道把流量送进回环:
│     1 health        PASS
│     2 token_seam    —      (不是已注册 token 路由)
│     3 auth_middleware  BLOCK 401  ← 没有 X-Hermes-Session-Token / Bearer <token>
│   结论:BLOCK(401)
│
├─ B. bound_host = 0.0.0.0 或 ::(auth_required=True)
│   起服务前置条件:list_providers() 非空,否则 SystemExit 拒绝启动(:17549)
│     1 health        PASS
│     2 token_seam    —
│     3 auth_middleware  —      (auth_required=True → :661 直接透传)
│     4 auth_gate     BLOCK 401 {"error":"unauthenticated","reason":"no_cookie"}
│   注:host_header 层对 0.0.0.0 是无条件放行(:526),但它在第 6 层,轮不到它决定。
│   结论:BLOCK(401)
│
├─ C. bound_host = 具体非回环地址(192.168.x.x / Tailscale IP / 100.64.x.x)
│   同 B(auth_required=True,provider 必须存在),额外多一道:
│     6 host_header   要求 Host 精确等于 bound_host —— 但已在第 4 层被 401,轮不到
│   结论:BLOCK(401)
│
├─ D. bound_host 未设置(app 被别的 ASGI runner 直接跑,没走 start_server)
│   auth_required getattr 默认 False,bound_host getattr 默认 None
│     3 auth_middleware  BLOCK 401
│     6 host_header      —      (`if bound_host:` 为假,整层跳过)
│   结论:BLOCK(401)
│
└─ E. 大小写/畸形 host 值(如 --host LOCALHOST、--host 127.0.0.2)
    should_require_auth 返回 True → 落回 B/C 分支(fail-safe 方向,更严不更松)
    结论:BLOCK(401)

=> 四种绑定形态 + 畸形值,**没有任何一种组合**能让未认证请求打到 approve_pairing。
```

### 2.6 实测(真实 app,逐组合)

```console
E) loopback bind (auth_required=False, bound_host=127.0.0.1):
   no token, Host=testserver -> 401 {'detail': 'Unauthorized'}
   no token, Host=127.0.0.1  -> 401 {'detail': 'Unauthorized'}
   WITH token                -> 404 {'detail': "Pairing request or code not found ..."}   ← 穿透到 handler
   ?token= query only        -> 401 {'detail': 'Unauthorized'}                            ← 查询串口子不覆盖它

F) LAN bind (auth_required=True, bound_host=192.168.1.50):
   no cookie             -> 401 {'error':'unauthenticated','reason':'no_cookie','login_url':'/login'}
   legacy session token  -> 401 {同上}      ← gated 模式下 _SESSION_TOKEN 一律不认

G) 0.0.0.0 bind (auth_required=True), Host: evil.test:
   no cookie             -> 401 {'error':'unauthenticated','reason':'no_cookie'}
```

`WITH token → 404` 是**阳性对照**:它证明 401 确实来自中间件而不是路由不存在,
也证明带凭据时请求确实能穿透到 handler(404 是 handler 自己发的"没有这个配对码")。
`legacy session token → 401` 证明第 3、4 层不是"或"关系而是**按 `auth_required` 二选一**:
gated 模式下旧 token 一文不值。

配套的行为规格(测试给 client 装了 session header,即测试也只能在带凭据时打通):

`tests/hermes_cli/test_dashboard_admin_endpoints.py:22`

```python
    client = TestClient(app)
    client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
```

同类端点的"无凭据必 401"规格(pairing 自己没有专门的 401 用例,这是全局规格):

`tests/hermes_cli/test_web_server.py:1317`

```python
    def test_unauthenticated_api_blocked(self):
```

### 2.7 路径形态旁路探测(为"确定的结论"补最后一块)

前面的判定都建立在"`path` 就是 `/api/pairing/approve`"上。攻击者当然会试着改写 path。
实测(回环绑定、无凭据):

```console
H) path-shape bypass probes (loopback bind, NO credential):
   POST /api/pairing/approve         -> 401  {'detail': 'Unauthorized'}
   POST /API/pairing/approve         -> 405  {'detail': 'Method Not Allowed'}
   POST /Api/Pairing/Approve         -> 405  {'detail': 'Method Not Allowed'}
   POST /api/pairing/approve/        -> 401  {'detail': 'Unauthorized'}
   POST //api/pairing/approve        -> 405  {'detail': 'Method Not Allowed'}
   POST /api/./pairing/approve       -> 401  {'detail': 'Unauthorized'}
   POST /api/x/../pairing/approve    -> 401  {'detail': 'Unauthorized'}
```

解读:405 的三行**确实绕过了 `auth_middleware`**(因为 `path.startswith("/api/")` 大小写敏感、
不做 `//` 归一),但**同样绕不到 handler**——Starlette 的路由匹配同样大小写敏感/不归一,
它们落到 SPA catch-all,而 catch-all 只接 GET,于是 405。**没有实际暴露**,但这是一处
"两个大小写敏感性恰好对齐才安全"的隐性耦合,记为 §5 ◇-3。

### 2.8 H-3 结论

**不能。** 在默认配置(`--host 127.0.0.1`)下,局域网未认证请求连 TCP 都建立不了;
即便流量被同机反代送进回环,`auth_middleware`(:665)也会先返回 401。
把绑定改成任何非回环地址后,`should_require_auth` 必然返回 True,
`start_server` 在**没有注册鉴权 provider 时直接拒绝启动**(:17549),
启动成功则 `gated_auth_middleware` 对这条路径返回 401。
**`/api/pairing/approve` 的全部保护来自中间件链,路由本体零鉴权;
起作用的是第 3 层(回环/token 模式)或第 4 层(非回环/cookie 模式),二者按 `auth_required` 互斥接管。**

代价与脆弱点(设计层面,值得写进成品章):这个端点的安全性完全寄生在
"路径以 `/api/` 开头 + 不在 8 条白名单里"这两个条件上。任何一天有人往
`PUBLIC_API_PATHS` 里加一条前缀式条目、或把这个路由挪到 `/api/` 之外、
或引入一个会归一化大小写的前置代理,它就会**静默失去全部鉴权**——
因为它自己不会喊。`_require_token`(:431)这套路由级手段本可以做"双保险",此处没用。

---

## 3. 核心问题三:`_lifespan` 与三个启动辅助

### 3.1 `_lifespan`(:217)启动段

`hermes_cli/web_server.py:217`

```python
@asynccontextmanager
async def _lifespan(app: "FastAPI"):
    app.state.event_channels = {}  # dict[str, set]
    app.state.event_lock = asyncio.Lock()
    app.state.pty_active_session_files = {}  # dict[str, Path]
```

**为什么这些状态放 `app.state` 而不是模块级全局**——这是本段最值得学的一条设计:
`asyncio.Lock()` 会绑定**创建它时**的事件循环;模块级全局在 import 时创建,
一旦模块跨多个 `TestClient` 实例或 uvicorn reload 复用,锁就绑在一个已经死掉的循环上。

`hermes_cli/web_server.py:144`

```python
# State lives on app.state (not module-level globals) so that asyncio.Lock is
# created on the running event loop during lifespan startup.  A module-level
# asyncio.Lock() binds to whatever loop was active at import time, which breaks
# when the same module is used across TestClient instances or uvicorn reloads.
```

配套的兜底:三个 `_get_*` 取值器都做"lifespan 没跑过就懒初始化",
让不带 `with` 的 `TestClient` 用法继续能跑(:273 / :290 / :304)。

`hermes_cli/web_server.py:273`

```python
def _get_event_state(app: "FastAPI"):
```

启动段其余动作,按发生顺序:

`hermes_cli/web_server.py:234`

```python
    _warm_gateway_module()
```

`hermes_cli/web_server.py:241`

```python
    if os.getenv("HERMES_DESKTOP") == "1":
        cron_stop = threading.Event()
        cron_thread = threading.Thread(
            target=_start_desktop_cron_ticker,
            args=(cron_stop,),
            daemon=True,
            name="desktop-cron-ticker",
        )
        cron_thread.start()
```

`hermes_cli/web_server.py:252`

```python
    pty_reaper_task = asyncio.create_task(run_reaper(PTY_REGISTRY))
```

`hermes_cli/web_server.py:256`

```python
    selftest_task = asyncio.create_task(_dashboard_selftest_loop())
```

`hermes_cli/web_server.py:260`

```python
    auto_archive_task = asyncio.create_task(_auto_archive_ticker_loop())
```

### 3.2 `_lifespan` 关闭段

`hermes_cli/web_server.py:264`

```python
    finally:
        pty_reaper_task.cancel()
        selftest_task.cancel()
        auto_archive_task.cancel()
        await PTY_REGISTRY.close_all()
        if cron_stop is not None:
            cron_stop.set()
```

四个后台工蜂各自的落点:

- `run_reaper` —— 60s 一轮,回收超时/死掉的 keep-alive PTY 会话。
  `hermes_cli/pty_session.py:129`
  ```python
  async def run_reaper(registry: "PtySessionRegistry", *, interval: float = 60.0) -> None:
  ```
  注册表参数(TTL 30 分钟、上限 16 个会话、缓冲 1 MiB):
  `hermes_cli/web_server.py:14440`
  ```python
  PTY_REGISTRY = PtySessionRegistry(
      ttl=30 * 60,
      max_sessions=16,
      buffer_cap=1 * 1024 * 1024,
      read_timeout=_PTY_READ_CHUNK_TIMEOUT,
  )
  ```
- `_dashboard_selftest_loop` —— 见 §4.4。
- `_auto_archive_ticker_loop` —— 3600s 一轮、首轮延迟 90s,把陈旧会话归档。
  存在理由是"后端连开几天、期间没人请求 `/api/sessions`,机会式触发就永远不发生":
  `hermes_cli/web_server.py:11311`
  ```python
  async def _auto_archive_ticker_loop(
      interval_s: float = 3600.0, initial_delay_s: float = 90.0
  ) -> None:
  ```

**注意一个非对称**:三个 asyncio task 用 `cancel()`(不 await,不保证已停),
PTY 注册表用 `await ...close_all()`(阻塞等它关干净),cron 线程用 `Event.set()`
(daemon 线程,不 join)。三种收尾语义对应三种资源:纯定时器可以硬砍,
持有子进程/pty fd 的必须等,跨进程文件锁的靠标志位自然退出。

### 3.3 `_start_desktop_cron_ticker`(:150)为什么需要

场景:用户在桌面 App 里建了一条 cron。桌面 App 起的是 `hermes dashboard` 后端,**不是 gateway**;
而 cron 的 tick 循环平时住在 `hermes gateway run` 里。没有这段代码,这条 cron 永远不会触发。

`hermes_cli/web_server.py:150`

```python
def _start_desktop_cron_ticker(stop_event: "threading.Event", interval: int = 60) -> None:
    """Tick the cron scheduler from inside the desktop dashboard backend.

    The scheduler tick loop normally lives in ``hermes gateway run`` — but the
    desktop app spawns a ``hermes dashboard`` backend, not a gateway, so a cron
    a user creates in the app would never fire. We run the resolved cron
    scheduler provider here (no live adapters; delivery falls back to the
    per-platform send path).

    Cross-process safe: the built-in provider's ``cron.scheduler.tick`` takes
    the ``cron/.tick.lock`` file lock, so this never double-fires alongside a
    real gateway on the same HERMES_HOME — whichever process grabs the lock
    first wins the tick.
    """
```

**"同一个 HERMES_HOME 上真 gateway 也在跑怎么办"**——靠 `cron/.tick.lock` 文件锁,谁抢到谁 tick。
这是个值得抄的模式:与其在启动时判断"我该不该做这件事",不如让所有候选者都去抢一把跨进程锁,
把"只做一次"的正确性交给锁,而不是交给启动顺序。

`hermes_cli/web_server.py:164`

```python
    from cron.scheduler_provider import resolve_cron_scheduler
```

(函数内部 import,不在模块顶层——避免 `hermes dashboard` 以外的路径白白付 cron 层的 import 代价。)

### 3.4 `_warm_gateway_module`(:171)为什么需要

事故经过(可以直接讲成故事):Windows 冷装机上,用户点开桌面 App,
App 起后端并等一个 WebSocket ready 探针。后端 socket 已经开了、探针打进来了,
但第一次 import 那几条重模块链会触发 .pyc 编译 + Defender 实时扫描,
在 Python 3.11 + Windows 上**这个 import 不释放 GIL**,于是 `run_in_executor` 也救不了——
事件循环整整冻住 15–22 秒,超过桌面端 10 秒的 ready 超时,App 报"连不上"。

`hermes_cli/web_server.py:171`

```python
def _warm_gateway_module() -> None:
    """Pre-import heavy modules so the event loop is not stalled on first use.

    On a cold Windows install, importing these module chains triggers .pyc
    compilation and Defender real-time scans that can stall the event loop
    for 15-30s. The original fix (pre-#60800) only warmed
    ``hermes_cli.gateway``. But the first WS connection and its initial
    RPC burst (``setup.status``, ``setup.runtime_check``,
    ``gateway.ready``→``resolve_skin``) pull in several *other* heavy
    chains that were still imported on the loop thread, contributing to
    the ~14s cold-start stall (#60800). Warm them all here so the cost
    is paid in a worker thread while the server socket is already open.
    """
```

修法两代:第一代只预热 `hermes_cli.gateway`,结果第一条 WS 连接的 RPC 首发
(`setup.status` / `setup.runtime_check` / `gateway.ready`→`resolve_skin`)
又把**另外几条**重链拽到循环线程上,残留 ~14s 卡顿(#60800)。第二代把它们全列出来:

`hermes_cli/web_server.py:184`

```python
    for mod in (
        "hermes_cli.gateway",
        # setup.status / setup.runtime_check resolve provider auth state,
        # which imports copilot_auth (→ subprocess module) and scans
        # credential files. First import is noticeably slow on Windows.
        "hermes_cli.auth",
        "hermes_cli.copilot_auth",
        "hermes_cli.runtime_provider",
        # resolve_skin() reads config + initialises the skin engine.
        # Even though handle_ws now calls it via asyncio.to_thread
        # (see tui_gateway/ws.py), warming it here avoids the first-call
        # import cost inside that thread.
        "hermes_cli.skin_engine",
        # model.options / picker context — parses provider catalogs and
        # the models.dev cache on first use.
        "hermes_cli.inventory",
        "hermes_cli.model_switch",
    ):
        try:
            __import__(mod)
        except Exception:
            pass
```

调用点的注释把"为什么放在 yield 之前而不是丢线程池"说得很直白:

`hermes_cli/web_server.py:228`

```python
    # Import hermes_cli.gateway eagerly *before* the lifespan yield so the
    # GIL-heavy .pyc compilation and Defender scan cost is absorbed during
    # backend initialisation — before the server socket accepts probes.
    # On Windows + Python 3.11 the import does not release the GIL, so
    # run_in_executor still froze the event loop for 15-22 s, causing the
    # Desktop's 10-second WebSocket ready-probe to time out (GH-73083).
```

`except Exception: pass` 是刻意的:预热纯属优化,任何一条链 import 失败都不该让后端起不来。

### 3.5 `_resolve_restart_drain_timeout`(:208)取值来源

`hermes_cli/web_server.py:208`

```python
def _resolve_restart_drain_timeout() -> float:
    try:
        from hermes_cli.gateway import _get_restart_drain_timeout
        return _get_restart_drain_timeout()
    except ImportError:
        from gateway.restart import DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
        return DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
```

取值链(优先级从高到低):

**R11C 片 C 改:围栏由 ```verify 改为 ```text —— 块里是取值链的说明,不是命令。**
原样跑它会得到 `bash: -c: line 1: '1. 环境变量 HERMES_RESTART_DRAIN_TIMEOUT(非空即用)'`。
内容一字未动。

```text
1. 环境变量 HERMES_RESTART_DRAIN_TIMEOUT(非空即用)
2. config.yaml 的 agent.restart_drain_timeout
3. DEFAULT_CONFIG["agent"]["restart_drain_timeout"] = 0
   → 全部经 parse_restart_drain_timeout(),异常/空值回落默认,结果 max(0.0, value)
兜底:如果连 hermes_cli.gateway 都 import 不进来(ImportError),
     直接用 gateway.restart 的常量 —— 即上面第 3 档。
```

`hermes_cli/gateway.py:3270`

```python
def _get_restart_drain_timeout() -> float:
    """Return the configured gateway restart drain timeout in seconds."""
    raw = os.getenv("HERMES_RESTART_DRAIN_TIMEOUT", "").strip()
    if not raw:
        cfg = read_raw_config()
        agent_cfg = cfg.get("agent", {}) if isinstance(cfg, dict) else {}
        raw = str(
            agent_cfg.get(
                "restart_drain_timeout", DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
            )
        )
    return parse_restart_drain_timeout(raw)
```

`gateway/restart.py:23`

```python
DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT = float(
    DEFAULT_CONFIG["agent"]["restart_drain_timeout"]
)
```

`hermes_cli/config_defaults.py:47`

```python
        "restart_drain_timeout": 0,
```

**默认值是 0 = 立刻打断,不排空**。理由写在默认值旁边:这段超时必须短于 systemd 的
`TimeoutStopSec`,否则会在清理到一半时吃 SIGKILL;要"让在跑的 turn 自然跑完"应该用
另一个键 `restart_after_turn_timeout`。

唯一消费者是 `/api/status`(或同族状态端点)——把解析结果吐给 NAS,让它自己算轮询期限;
而且**特意丢到线程池**,理由又是那条 Windows 冷启动 import 卡顿:

`hermes_cli/web_server.py:3168`

```python
        restart_drain_timeout = await asyncio.get_running_loop().run_in_executor(
            None, _resolve_restart_drain_timeout
        )
```

---

## 4. 核心问题四:session token 体系(:322–380 及其消费点)

### 4.1 token 从哪来

`hermes_cli/web_server.py:330`

```python
def _resolve_session_token() -> str:
    return os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN") or secrets.token_urlsafe(32)


_SESSION_TOKEN = _resolve_session_token()
_SESSION_HEADER_NAME = "X-Hermes-Session-Token"
_SSH_OWNER_NONCE: Optional[str] = None
```

两条来源、一条兜底:

**R11C 片 C 改:围栏由 ```verify 改为 ```text —— 块里是两条来源与兜底的说明,不是命令。**
内容一字未动。

```text
桌面 App 场景:App 主进程自己造 token,通过 HERMES_DASHBOARD_SESSION_TOKEN 注入子进程,
              这样 App 主进程也能代用户调 /api/*(它拿得到 token)。
纯 CLI 场景:  环境变量为空 → secrets.token_urlsafe(32) 现场生成。
共同点:      **进程内内存,不落盘,进程一死就没了**(注释 :325-326 明说 "it dies when
              the process exits")。所以它是"会话"token 而不是"凭据"。
```

`hermes_cli/web_server.py:320`

```python
# ---------------------------------------------------------------------------
# Session token for protecting sensitive endpoints (reveal).
# The desktop shell mints the token and injects it via
# HERMES_DASHBOARD_SESSION_TOKEN so its main process can authenticate the
# /api calls it makes on the user's behalf; otherwise we generate one fresh
# on every server start. Either way it dies when the process exits and is
# injected into the SPA HTML so only the legitimate web UI can use it.
# ---------------------------------------------------------------------------
```

还有一条**运行时改写**通道,给桌面端 SSH 远程会话用(`start_server` 开头调用,:17447):

`hermes_cli/web_server.py:339`

```python
def _apply_ssh_session_token(token: str) -> None:
    global _SESSION_TOKEN
    if token:
        _SESSION_TOKEN = token


def _apply_ssh_owner_nonce(nonce: Optional[str]) -> None:
    global _SSH_OWNER_NONCE
    _SSH_OWNER_NONCE = nonce
```

### 4.2 怎么下发

**注入 SPA 的 index.html**,不设"发 token 的接口"——这是关键设计:如果有一个
`GET /api/token` 之类的端点,它必然是公开的,那 token 就等于没有。

`hermes_cli/web_server.py:16107`

```python
                f'<script>window.__HERMES_SESSION_TOKEN__="{_SESSION_TOKEN}";'
```

而且**gated 模式下这一行根本不发**——两条分支各走各的:

`hermes_cli/web_server.py:16095`

```python
        gated = bool(getattr(app.state, "auth_required", False))
        gated_js = "true" if gated else "false"
        if gated:
            bootstrap_script = (
                f"<script>"
                f"window.__HERMES_DASHBOARD_EMBEDDED_CHAT__={chat_js};"
                f'window.__HERMES_BASE_PATH__="{prefix}";'
                f"window.__HERMES_AUTH_REQUIRED__={gated_js};"
                f"</script>"
            )
```

前端据此选择鉴权方案(token vs cookie+ticket),后端据此在 :661 / :332 分流。
**一个布尔量同时驱动前后端选路**,没有第二处配置,这是个干净的接缝。

### 4.3 怎么校验:两条 header + 一条 query

`hermes_cli/web_server.py:398`

```python
def _has_valid_session_token(request: Request) -> bool:
    """True if the request carries a valid dashboard session token.

    The dedicated session header avoids collisions with reverse proxies that
    already use ``Authorization`` (for example Caddy ``basic_auth``). We still
    accept the legacy Bearer path for backward compatibility with older
    dashboard bundles.
    """
    session_header = request.headers.get(_SESSION_HEADER_NAME, "")
    if session_header and hmac.compare_digest(
        session_header.encode(),
        _SESSION_TOKEN.encode(),
    ):
        return True

    auth = request.headers.get("authorization", "")
    expected = f"Bearer {_SESSION_TOKEN}"
    return hmac.compare_digest(auth.encode(), expected.encode())
```

要点三条:(1) 专用 header `X-Hermes-Session-Token` 是**为了不和反代抢 `Authorization`**
——Caddy 的 `basic_auth` 会占用它;(2) 仍收 `Bearer` 是给旧 bundle 的兼容;
(3) 全部用 `hmac.compare_digest` 常量时间比较,防时序侧信道。

### 4.4 `_has_valid_query_token`(:424):为什么要给**特定 path** 开查询串口子

`hermes_cli/web_server.py:418`

```python
# Routes that may also authenticate via a ``?token=`` query param, for download
# links opened by the OS shell or a new browser tab where the session header
# can't be set. Kept narrow — same query-token tradeoff as the /api/pty WS.
_QUERY_TOKEN_API_PATHS: frozenset[str] = frozenset({"/api/files/download"})


def _has_valid_query_token(request: Request, path: str) -> bool:
    if path not in _QUERY_TOKEN_API_PATHS:
        return False
    token = request.query_params.get("token", "")
    return bool(token) and hmac.compare_digest(token.encode(), _SESSION_TOKEN.encode())
```

**问题给的假设需要修正一半**:子代理任务书猜"这通常是给 WebSocket/EventSource 用的"。
证据显示——**这条 HTTP 层的口子只开给一个普通 GET 下载路由,不是给 WS 的**;
WS 用的是**另一套**、独立的 `?token=` 校验,根本不经过 HTTP 中间件(见 §1.6)。
两者是"同一个取舍的两次独立应用",不是同一段代码。

(a) 这条口子的真实动机——**OS shell / 新标签页打开的下载链接设不了自定义 header**:

`hermes_cli/web_server.py:2416`

```python
@app.get("/api/files/download")
async def download_managed_file(request: Request, path: str):
    """Stream a managed file as an attachment download.

    Remote clients (desktop app, browser dashboard) open agent-written files
    that live on *this* gateway's disk, not theirs. Auth-gated like every other
    managed-files route — ``auth_middleware`` additionally accepts the session
    token as a ``?token=`` query param here so a shell/browser-opened download
    (which can't set the session header) still authenticates. See ``/api/pty``
    for the same query-token precedent.
    """
```

(b) WS 那一套的动机是**浏览器 WS 升级请求根本没法带 `Authorization`**:

`hermes_cli/web_server.py:14400`

```python
# Auth: ``?token=<session_token>`` query param (browsers can't set
# Authorization on the WS upgrade).  Same ephemeral ``_SESSION_TOKEN`` as
# REST.  Localhost-only — we defensively reject non-loopback clients even
# though uvicorn binds to 127.0.0.1.
```

(c) 为什么"开口子"要**逐路径白名单**而不是全局开关:query token 会进浏览器历史、
进 Referer、进反代 access log。所以只给"确实做不到 header"的路径开,一条一条列。
gated 模式下这条 legacy 通道**整条作废**,WS 改用一次性 30s ticket:

`hermes_cli/web_server.py:14701`

```python
    The legacy ``?token=`` path is unconditionally rejected in gated mode
    (the SPA bundle isn't carrying the token any longer, and a leaked
    ``_SESSION_TOKEN`` must not grant WS access once the gate is engaged).
```

实测印证(见 §2.6 E 组第 4 行):对 `/api/pairing/approve` 用 `?token=<正确 token>`
仍然 401 —— 白名单是**精确路径集合**,不是"带对 token 就行"。

### 4.5 自检回路 `_dashboard_selftest_once/_loop`(:781 / :803)

**它解决的场景**:进程还活着、`/api/health` 也 200,但状态库 wedge 了,
**每一个需要鉴权的请求都 500**。纯 liveness 探针看不出来。于是每 60 秒用**真 token**
在进程内(ASGI transport,不走网络)打一次会碰 DB 的鉴权路由:

`hermes_cli/web_server.py:781`

```python
async def _dashboard_selftest_once() -> None:
    """Run one authenticated in-process self-test request and record it."""
    try:
        import httpx
    except ImportError:
        return  # optional dependency — skip cleanly, leave status "unknown"
    try:
        transport = httpx.ASGITransport(app=app)
        # base_url uses a loopback name so the Host-header middleware accepts
        # the request on loopback binds.
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as client:
            resp = await client.get(
                _DASHBOARD_SELFTEST_ROUTE,
                headers={_SESSION_HEADER_NAME: _SESSION_TOKEN},
            )
        DASHBOARD_HEALTH.record_selftest(resp.status_code == 200, resp.status_code)
    except Exception:
        DASHBOARD_HEALTH.record_selftest(False, None)
```

`hermes_cli/web_server.py:777`

```python
_DASHBOARD_SELFTEST_INTERVAL_SECONDS = 60.0
_DASHBOARD_SELFTEST_ROUTE = "/api/sessions?limit=1"
```

三处细节值得抄:
1. `base_url="http://127.0.0.1"` 是**专为 `host_header_middleware` 准备的**——
   自检请求也要过完整中间件链,所以 Host 必须像个合法回环请求。
2. gated 模式下这条探针会**假警报 401**(:661 让它透传给 cookie gate,而它没 cookie),
   所以循环里直接跳过:
   `hermes_cli/web_server.py:812`
   ```python
        # On OAuth-gated binds the legacy session token is not honoured, so
        # the probe would false-alarm 401 — skip until the gate is off.
        if getattr(app.state, "auth_required", False):
            continue
   ```
3. httpx 是可选依赖,没装就干净退出、状态停在 `"unknown"`,不伪造 ok/failing。

结果喂给 `/api/status` 的 `components` 字段。而 `/api/status` 是**公开路径**,
所以 `DashboardHealth.snapshot()` 有一条硬契约:**只导出枚举和计数,绝不导出
异常消息、请求路径、token**:

`hermes_cli/web_server.py:688`

```python
# ---------------------------------------------------------------------------
# Dashboard component health — in-process error/self-test counters that feed
# the ``components`` dict on ``/api/status``.  That endpoint is in
# ``PUBLIC_API_PATHS``, so everything exported from here must be counts and
# enums only: no exception messages, no request paths, no tokens.
# ---------------------------------------------------------------------------
```

`hermes_cli/web_server.py:736`

```python
    def snapshot(self) -> Dict[str, Any]:
        """Public component payload: status enum + counts + timestamps only."""
        errors = self.recent_error_count()
        status = "degraded" if (errors or self.selftest_status == "failing") else "ok"
        return {
            "status": status,
            "recent_unhandled_errors": errors,
            "last_error_at": self.last_error_at,
            "selftest": self.selftest_status,
        }
```

`last_error_path` 字段确实存在,但**故意不进 snapshot**,注释在字段定义处直接标了
`internal-only, never serialized`(:712)。**"字段可以存,但导出面要独立定义"**——
这是把"公开载荷无秘密"从约定变成结构的做法。

---

## 5. 记号发现

### ▲-1 `hermes_cli/web_server.py:640` —— 注释写的中间件顺序与实际**完全相反**

锚点与原文:

`hermes_cli/web_server.py:639`

```python
# the injected ``_SESSION_TOKEN``.  Registered between host_header and
# auth_middleware so the order is: host check → cookie auth → token auth.
```

**现象**:注释断言执行顺序是 `host check → cookie auth → token auth`。
实测顺序是 `token auth(auth_middleware, idx2)→ cookie auth(auth_gate, idx3)→ host check(idx5)`
——**三项完全倒序**。"Registered between host_header and auth_middleware" 这半句
(指注册位置在 :538 与 :650 之间)是对的;由它推出的执行顺序是错的,
因为作者在这里把 Starlette 的 LIFO 当成 FIFO 用了。

**影响**:纯注释错误,不改变运行行为(§2 已证明鉴权结论不受影响)。但它会误导
下一个改这段代码的人:比如有人想"在 host 检查之后再做 cookie 鉴权",按注释推理会得出
错误的注册位置。同文件 :578 与 :755 两条注释对同一机制的描述是**正确**的,
三处并存,读者无从判断该信哪条。

### ▲-2 `hermes_cli/web_server.py:678` —— "Registered LAST so it runs FIRST" 已过期

`hermes_cli/web_server.py:678`

```python
    Registered LAST so it runs FIRST (Starlette middleware is outermost-last).
```

**现象**:`_token_auth_seam` 注册于 :674,其后还有 `_dashboard_health_middleware`(:751)。
所以它既不是"最后注册"(健康层才是),也不是"第一个跑"(实测它是 idx1,第二个跑)。
同一句话在 `hermes_cli/dashboard_auth/token_auth.py:20` 还有一份拷贝
(`runs OUTERMOST (installed last in web_server.py)`),同样过期。

而健康层自己的注释是对的、并且**显式承认自己在 token seam 之后注册**:

`hermes_cli/web_server.py:755`

```python
    Registered after ``_token_auth_seam`` so it is the outermost layer
    (Starlette middleware is outermost-last) — nothing below can raise past
```

**影响**:轻。语义上 `_token_auth_seam` 仍是**最外层的鉴权中间件**(健康层不做鉴权决策),
所以它想表达的不变式成立。但字面陈述已被后加的健康层作废,且跨两个文件都没同步。
典型的"加中间件时改了新层的注释、忘了改被顶掉那层的注释"。

### ▲-3 `hermes_cli/web_server.py:524` —— "requires --insecure" 已被 2026-06 硬化作废

`hermes_cli/web_server.py:523`

```python
    # 0.0.0.0 bind means operator explicitly opted into all-interfaces
    # (requires --insecure per web_server.start_server). No Host-layer
    # defence can protect that mode; rely on operator network controls.
    if bound_host in {"0.0.0.0", "::"}:
        return True
```

**现象**:注释说绑 `0.0.0.0` "requires --insecure per web_server.start_server"。
但同文件 :483–489 已写明 `--insecure` 是 no-op;`start_server` 里 `allow_public`
唯一的作用是打一条 warning(:17469),真正的门槛变成了"必须注册鉴权 provider,
否则 SystemExit"(:17478–17553)。同样的过期说法在 WS 层又出现一次:

`hermes_cli/web_server.py:14574`

```python
    Explicit non-loopback bind (``--host 0.0.0.0``, ``--host ::``, or a
    specific address such as a Tailscale/LAN IP, always with
    ``--insecure``): allow any peer. The operator explicitly opted into
```

**影响**:注释误导 + 安全推理被削弱。按注释,`0.0.0.0` 上"没有 Host 层防御"是
因为运维显式选了 `--insecure`;实际上 `--insecure` 已经不存在这个语义,该模式下的
真正保护是 cookie gate。用户文档那边是对的
(`website/docs/user-guide/features/web-dashboard.md:30` 与 `:579` 都写明 no-op),
所以这是**代码内注释落后于用户文档**——与常见方向相反,值得单独记一笔。

### ◇-1 CORS 层实际只对 8 个公开路径生效,无任何文档交代

`CORSMiddleware` 用 `add_middleware` 在所有 `@app.middleware("http")` **之前**注册(:373),
在 LIFO 下成为**最内层**(实测 idx6)。后果:任何跨源浏览器对**受控 `/api/` 路径**的
预检 OPTIONS,会先被 `auth_middleware`(idx2)401 掉,CORSMiddleware 根本收不到,
自然也不会发 `Access-Control-Allow-Origin`。实测:

```console
I) CORS preflight consequence of CORSMiddleware being INNERMOST:
   OPTIONS /api/pairing/approve (cross-origin preflight) -> 401 | ACAO: None
   OPTIONS /api/status  (PUBLIC path preflight)          -> 200 | ACAO: http://localhost:5173
```

**这不是漏洞(方向是 fail-closed)**,但意味着 :369–371 那段"限制 CORS 到 localhost 源"
的配置,对真正敏感的路径**一次也没起过作用**——它只在 8 个 `PUBLIC_API_PATHS`
和非 `/api/` 路径上生效。实践中不影响开发,因为 Vite dev server 走的是同源代理而不是 CORS:

`web/vite.config.ts:136`

```text
  proxy: {
      "/api": {
        target: BACKEND,
        ws: true,
      },
```

(上块用 ```text 声明:它是 TS 配置片段的节选,首行不是 :136 的逐字全文,不作源码引用。)

**影响**:一层安全配置事实上是惰性的,而没有任何注释说明这件事;
将来若有人真需要跨源调用受控 API,会花很久才发现问题不在 CORS 配置而在中间件层序。

### ◇-2 两个近同名、内容不同的 loopback 集合,且其中一个含测试专用值

`hermes_cli/web_server.py:467`

```python
_LOOPBACK_HOST_VALUES: frozenset = frozenset({
    "localhost", "127.0.0.1", "::1",
})
```

`hermes_cli/web_server.py:14537`

```python
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})
```

**现象**:同一文件里两个只差一个词的常量。前者管 HTTP 层与 `should_require_auth`
(3 个值),后者管 WS 层对端判定(4 个值,多一个 `"testclient"`)。
`"testclient"` 是 Starlette `TestClient` 的默认 `client.host`,出现在生产代码的
WS 对端白名单里。

**影响**:(a) 命名几乎不可区分,改一个忘另一个的概率很高;
(b) 任何能让 `ws.client.host` 变成字符串 `"testclient"` 的路径(例如某个反代把
`X-Forwarded-For` 写成这个值 + `proxy_headers` 开启)都会被 WS 层当成回环放行。
本轮**未取证**该路径是否可达(`proxy_headers` 只在 `auth_required=True` 时开启,
而那时 `_ws_client_reason` 在 :14549 直接 `return None`,可能自然规避),
留作存疑项(见 §6)。

### ◇-3 `auth_middleware` 的路径判据不做归一,安全性依赖"路由同样不归一"

`auth_middleware` 只对 `path.startswith("/api/")` 的请求执行鉴权(:665)。
`/API/pairing/approve`、`//api/pairing/approve` 都不满足这个前缀测试,
于是**完全不过鉴权**就透传给了路由。实测(§2.7)它们最终得到 405 而不是 200,
是因为 Starlette 的路由匹配**恰好同样**大小写敏感、同样不折叠 `//`,于是落到只接 GET 的
SPA catch-all。

对照:gated 模式那条链是 **deny-by-default**(`if _path_is_public(path): pass else 鉴权`),
大小写变体反而被正确 401。**两条链在这一点上强度不同**:回环链是 allow-by-default
(只有 `/api/` 前缀才被管),gated 链是 deny-by-default。

**影响**:当前无实际暴露,但这是"两个组件的大小写敏感性必须永远一致"的隐性契约,
既没写进注释也没有测试钉住。前置代理做路径归一、或将来引入大小写不敏感路由,
都会把它变成真洞。

### ◇-4 `_GATE_PUBLIC_PREFIXES` 15 条里 10 条没有尾斜杠,而注释只讨论了带尾斜杠的那几条

注释(`hermes_cli/dashboard_auth/middleware.py:44-48`)专门论证了"`/assets/` 带尾斜杠
所以匹配 `/assets/foo.css` 而不匹配 `/assetsleak`",但名单里 `"/login"`、
`"/auth/logout"`、`"/api/auth/providers"`、`"/favicon.ico"` 等 10 条**没有尾斜杠**,
`startswith` 会让 `/api/auth/providersXYZ`、`/loginXYZ` 一并公开。

**当前不可利用**:全仓 `/auth/*` 与 `/api/auth/*` 路由共 11 条
(`hermes_cli/dashboard_auth/routes.py:132/152/182/289/379/650/742/778/799/841/894`),
其中 `/api/auth/me` 与 `/api/auth/ws-ticket` **都不以 `/api/auth/providers` 开头**,
没有前缀碰撞。搜索面:`grep -rn '"/api/auth/\|"/login\|"/auth/'` 覆盖
`hermes_cli/dashboard_auth/routes.py` 与 `hermes_cli/web_server.py`,只取带
`@router.`/`@app.` 的定义行;未搜插件自带路由(`_mount_plugin_api_routes` 挂载的
`/api/plugins/*` 不落在这些前缀内)。

**影响**:注释建立的"尾斜杠纪律"只贯彻了三分之一;将来新增一条
`/api/auth/providers-admin` 之类的路由就会**默认公开**,且不会有任何告警。

### ◎-1 `_plugin_api_runtime_gate` 的层序推理是对的,而且被测试钉住了

这是本段唯一一处**作者把 LIFO 想对了、并且写清了为什么必须这样**的地方,值得作为正面样本:

`hermes_cli/web_server.py:578`

```python
    Registered BEFORE the auth middlewares (so it executes AFTER them): a
    request that hasn't cleared auth must get auth's 401 first, never this
    gate's 404 — otherwise an unauthenticated caller could fingerprint which
    plugins are installed/enabled by reading the status code. We only reach
    the enabled/disabled check for a request that auth already let through.
```

理由是**防指纹**:如果插件门在鉴权之前跑,未认证调用者可以靠 404 vs 401 的差异
枚举出这台机器装了哪些插件。实测确认(存在的插件和不存在的插件都是 401,无差别):

```console
J) plugin gate never fires before auth (fingerprint oracle check):
   GET /api/plugins/_definitely_not_a_plugin_/x   no-token -> 401
   GET /api/plugins/kanban/tasks                  no-token -> 401
```

并且它自己**还在层内再判一次已认证**(不只靠层序),是双保险:

`hermes_cli/web_server.py:589`

```python
        _authed = (
            getattr(request.state, "token_authenticated", False)
            or getattr(request.app.state, "auth_required", False)
            or _has_valid_session_token(request)
            or _has_valid_query_token(request, path)
        )
```

对应测试:

`tests/hermes_cli/test_web_server.py:3397`

```python
    def test_non_kanban_plugin_route_requires_auth(self):
```

### ◎-2 `host_header_middleware` 在最内层,对公开路径仍然有效

因为它是最内层,受控路径上"坏 Host + 无凭据"先吃 401(不是 400)。
但**对 8 个公开路径,它是唯一的守卫,而且确实拦住了**:

```console
K) host_header_middleware is INNERMOST: bad Host + good token:
   Host=evil.test + valid token -> 400 {'detail': 'Invalid Host header. ...'}
   Host=evil.test + NO token    -> 401 {'detail': 'Unauthorized'}
   GET /api/status Host=evil.test (public path) -> 400 {'detail': 'Invalid Host header...'}
```

也就是说 GHSA-ppp5-vxwm-4cf7 那条 DNS rebinding 防线**没有因为层序靠内而失效**:
攻击者关心的是"能不能拿到数据",受控路径上鉴权先挡(更严),公开路径上 Host 检查挡。
文档没提这个层序,读者容易以为 Host 检查是第一道——**结论安全,但推理路径与直觉不同**。

---

## 6. 本段未覆盖 / 存疑(每条带锚点 + 一句话现象)

1. **`"testclient"` 能否被外部构造出来** —— 锚点 `hermes_cli/web_server.py:14537`
   (`_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})`)。
   现象:生产 WS 对端白名单里含测试专用主机名;本轮只确认了它的存在与
   `_ws_client_reason`(:14549)在 `auth_required=True` 时提前 `return None`,
   **没有取证**"uvicorn `proxy_headers=True` 时 `ws.client.host` 是否可能被
   `X-Forwarded-For` 改写成任意字符串"。这条要么证伪、要么升格为 ■。

2. **`/api/pairing/approve` 的 CLI 侧锁定报告不一致(R8A 原始 H-3 的另一半)** ——
   锚点 `website/docs/user-guide/features/web-dashboard.md:528`
   (`| POST /api/pairing/approve | Approve a code. Body: {platform, code} |`)
   vs `hermes_cli/web_server.py:12327-12331`(代码同时接受 `request_id` 与 `code`,
   且 `request_id` 优先)。现象:文档只写 `code` 一个字段。本轮只负责鉴权层,
   路由本体的字段/锁定语义按任务书由 R8A 已定案,这里仅补一条:**文档字段表也漏了 `profile`**
   (`hermes_cli/web_server.py:12323` `store = _pairing_store(body.profile)`)。

3. **`_dashboard_health_middleware` 只在最外层计 5xx,但 401/400 早在内层返回** ——
   锚点 `hermes_cli/web_server.py:765`(`if response.status_code >= 500:`)。
   现象:鉴权风暴(大量 401)不会让 `selftest`/`recent_unhandled_errors` 有任何反应,
   `/api/status` 的 `degraded` 判据(:739)对"被打爆的公开面"是盲的。未判定这是取舍还是缺口。

4. **`_SESSION_TOKEN` 被 `_apply_ssh_session_token` 运行时改写后,已注入的 SPA HTML 怎么办** ——
   锚点 `hermes_cli/web_server.py:339`(`def _apply_ssh_session_token(token: str) -> None:`)。
   现象:它在 `start_server` 开头(:17447)改全局,而 `mount_spa` 的 `_serve_index` 每次请求
   现读 `_SESSION_TOKEN`(:16107),看上去自洽;但**未验证**是否存在
   "先有页面拿到旧 token、再被改写"的窗口(例如同进程二次调用 `start_server`)。

5. **CORS 预检 401 是否影响任何真实客户端** —— 锚点 `hermes_cli/web_server.py:373`
   (`app.add_middleware(`)。现象:实测跨源预检对受控路径必 401;已确认 Vite dev 走同源代理
   (`web/vite.config.ts` 的 `server.proxy["/api"]`),**未查**桌面端 `apps/desktop/`
   与任何浏览器扩展/嵌入场景是否有跨源直调。

6. **1–830 行内未逐行精读的部分**:`DashboardHealth` 的滚动窗口实现细节
   (`hermes_cli/web_server.py:730` `def recent_error_count(self) -> int:`,
   `deque(maxlen=256)` 与 300s 窗口的相互作用——超过 256 个错误时窗口计数会被 maxlen 截断,
   现象未验证是否影响 `degraded` 判据),以及 :824 之后的
   `_memory_provider_options`(超出本段边界,归下一段)。
