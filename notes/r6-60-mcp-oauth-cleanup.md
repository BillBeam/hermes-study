# R6 底稿 · MCP OAuth 客户端三件套

> 对象:`tools/mcp_oauth.py`(1369 行)、`tools/mcp_oauth_manager.py`(785 行)、`tools/mcp_dashboard_oauth.py`(145 行),基线 `863e31318553cda8ad61df681d08175364d4164b`,只读。
> 溯源约定:`路径:行号 @ 863e313` + 逐字代码块(行号实测)。涉及 MCP Python SDK 的断言另标 `mcp==1.28.1 site-packages`(该版本由 `pyproject.toml:240 @ 863e313` 钉死:`mcp = ["mcp==1.28.1", ...]`),不冒充仓库代码。
> 本稿为 R3 欠账清偿:R3 已把 `mcp_tool.py` 七道客户端防护读到 L1,三个 OAuth 文件当时只到结构级,本稿补到 L1。

---

## 0. 三件套分工一句话

- `mcp_oauth.py`:**不实现 OAuth 协议本身**。协议(发现、DCR、PKCE、state、换 token、刷新)全部委托给 MCP SDK 的 `OAuthClientProvider`;本文件提供三块胶水——磁盘 token 存储(`HermesTokenStorage`)、浏览器回调接收(loopback HTTP 小服务器 + stdin 粘贴回退)、装配入口(`build_oauth_auth`)。文件头自述即如此:

  `tools/mcp_oauth.py:9-19 @ 863e313`
  ```python
  Uses the MCP Python SDK's ``OAuthClientProvider`` (an ``httpx.Auth`` subclass)
  which handles discovery, dynamic client registration, PKCE, token exchange,
  refresh, and step-up authorization automatically.

  This module provides the glue:
      - ``HermesTokenStorage``: persists tokens/client-info to disk so they
        survive across process restarts.
      - Callback server: ephemeral localhost HTTP server to capture the OAuth
        redirect with the authorization code.
      - ``build_oauth_auth()``: entry point called by ``mcp_tool.py`` that wires
        everything together and returns the ``httpx.Auth`` object.
  ```

- `mcp_oauth_manager.py`:**进程级单例管理器**。每个 (HERMES_HOME, server) 一个 provider 实例,负责跨进程 token 变更感知(mtime 盘监视)、401 并发去重、冷启动过期修复(SDK 子类 `HermesMCPOAuthProvider`)、死客户端注册自愈。自述为"全进程唯一实例化 SDK provider 的地方":

  `tools/mcp_oauth_manager.py:18-21 @ 863e313`
  ```python
  Replaces what used to be scattered across eight call sites in `mcp_oauth.py`,
  `mcp_tool.py`, and `hermes_cli/mcp_config.py`. This module is the ONLY place
  that instantiates the MCP SDK's `OAuthClientProvider` — all other code paths
  go through `get_manager()`.
  ```

- `mcp_dashboard_oauth.py`:**把两个"人机回调"从 loopback 移进 dashboard**。协议仍归 SDK;本文件只是一个 145 行的会合点(rendezvous)数据类 + ContextVar,使 GUI(web dashboard / desktop)场景下"展示授权 URL"与"接收回调"走已鉴权的 dashboard HTTP 会话而不是本机 loopback 端口。

  `tools/mcp_dashboard_oauth.py:1-6 @ 863e313`
  ```python
  """Dashboard-mediated callback bridge for MCP OAuth.

  The MCP SDK remains responsible for discovery, DCR, PKCE, state validation and
  token exchange. This module only moves the two human/browser callbacks from a
  loopback listener into the already-authenticated dashboard session.
  """
  ```

---

## 1. OAuth 模式定性(任务点 1)

**结论:OAuth 2.1 authorization code + PKCE(S256)+ RFC 7591 动态客户端注册(DCR)+ RFC 9728 受保护资源元数据(PRM)/RFC 8414 授权服务器元数据(ASM)双段发现 + RFC 8707 resource 指示器。这正是 MCP 规范 Authorization 章(2025-06-18 版)要求的完整客户端形态。** Hermes 一行协议代码都没写,全在 SDK 里;逐项对照:

**(a) PKCE S256,128 字符 verifier**(SDK 实现,Hermes 继承):

`mcp/client/auth/oauth2.py:66-69 @ mcp==1.28.1 site-packages`
```python
code_verifier = "".join(secrets.choice(string.ascii_letters + string.digits + "-._~") for _ in range(128))
digest = hashlib.sha256(code_verifier.encode()).digest()
code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
```

**(b) authorization code 流 + 随机 state + S256 声明**:

`mcp/client/auth/oauth2.py:337-345 @ mcp==1.28.1 site-packages`
```python
state = secrets.token_urlsafe(32)
...
    "state": state,
    "code_challenge": pkce_params.code_challenge,
    "code_challenge_method": "S256",
```

**(c) RFC 7591 DCR**:SDK 401 分支 Step 4,`client_info` 缺失时 `create_client_registration_request(...)` → `yield registration_request`(`oauth2.py:585-593 @ mcp==1.28.1`)。Hermes 侧对应两件事:① 配置了 `oauth.client_id` 时**预注册**、跳过 DCR(§2.8);② DCR 被 IdP 判死时**自动 poison 重注册**(§3.6)。

**(d) RFC 8707 resource 参数与 PRM 资源校验(混淆代理防御的一半)**:SDK 在授权与换 token 请求里带 `resource`,并校验 PRM 声明的 resource 必须匹配 MCP server URL:

`mcp/client/auth/oauth2.py:270-277 @ mcp==1.28.1 site-packages`
```python
async def _validate_resource_match(self, prm: ProtectedResourceMetadata) -> None:
    """Validate that PRM resource matches the server URL per RFC 8707."""
    ...
    if not check_resource_allowed(requested_resource=default_resource, configured_resource=prm_resource):
        raise OAuthFlowError(f"Protected resource {prm_resource} does not match expected {default_resource}")
```

**(e) Hermes 声明的 client metadata**——公共客户端(`token_endpoint_auth_method: none`)、authorization_code + refresh_token 两种 grant:

`tools/mcp_oauth.py:1210-1216 @ 863e313`
```python
    metadata_kwargs: dict[str, Any] = {
        "client_name": client_name,
        "redirect_uris": [AnyUrl(redirect_uri)],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": auth_method,
    }
```
只有当用户给了 `client_secret` 或 provider 特判(Figma)时才转机密客户端 `client_secret_post`(`tools/mcp_oauth.py:1206-1208 @ 863e313`:`auth_method = "client_secret_post" if cfg.get("client_secret") else "none"`)。

**重实现要点**:① 客户端侧 OAuth 不要自己写协议,选一个实现了 MCP auth 规范全链(PRM→ASM→DCR→PKCE→exchange→refresh→step-up)的 SDK,自己只做存储/回调/装配三块胶水;② 默认公共客户端 + PKCE,机密客户端只在拿到 secret 时启用;③ grant_types 必须同时注册 `refresh_token`,否则后面整个刷新体系无从谈起。

---

## 2. `mcp_oauth.py` 逐机制

### 2.1 SDK 惰性加载与可测性

`import mcp` 花约 170ms,所以模块加载只用 `find_spec` 探测存在性,真类首用时经 `_ensure_sdk_loaded()` 绑定;且模块级名字保留 `None` 占位、真类缓存在 `_SDK_CLASSES`,专为 `patch.object` 与"测试 patch 后复原为 None"两种场景设计(`tools/mcp_oauth.py:63-125 @ 863e313`,关键句:`if g.get(_name) is None: g[_name] = _cls`——被测试替换过的名字不动,只回填 None)。

**重实现要点**:重依赖延迟导入时,把"探测可用"与"实际导入"分开;模块级占位名 + 私有真类缓存,同时满足启动速度、可 patch、patch 后自愈三件事。

### 2.2 交互性三态门:suppress / force / TTY

`_is_interactive()` 的判定顺序:显式抑制 > 显式强制 > stdin 是否 TTY:

`tools/mcp_oauth.py:298-307 @ 863e313`
```python
def _is_interactive() -> bool:
    """Return True if we can reasonably expect to interact with a user."""
    if not _oauth_interactive_enabled.get():
        return False
    if _oauth_interactive_forced.get():
        return True
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False
```

两个开关都是 **ContextVar 而非 threading.local**,理由写死在注释里:后台 MCP 发现在发现线程上设置抑制,但实际 connect+OAuth 跑在专用 `mcp-event-loop` 线程(经 `run_coroutine_threadsafe`);asyncio 会把**调用方 context** 拷进被调度协程,ContextVar 能跨线程边界传播,threading.local 不能(`tools/mcp_oauth.py:149-157 @ 863e313`,事故编号 #35927)。三个使用方:

- 后台发现:`hermes_cli/mcp_startup.py:157-167 @ 863e313` —— `with suppress_interactive_oauth(): discover_mcp_tools()`,保证后台发现绝不弹浏览器/读 stdin;
- CLI 登录:`hermes_cli/mcp_config.py:822-835 @ 863e313` —— `hermes mcp login` 即使 stdin 非 TTY(desktop 拉起的终端)也 `force_interactive_oauth()`;
- dashboard:`hermes_cli/web_server.py:12193 @ 863e313` —— `with transaction, force_interactive_oauth(), dashboard_oauth_flow(flow):`,用户在浏览器里、不在 stdin 上。

非交互时的 fail-fast 有**三道递进关卡**,共用一个统一话术生成器 `_raise_if_non_interactive`(`tools/mcp_oauth.py:310-323 @ 863e313`,#57836,附带 `hermes mcp login <server>` 的行动指引):

1. **构建期**:无缓存 token 且非交互 → 构建 provider 时即抛(`tools/mcp_oauth.py:1342-1349 @ 863e313`;manager 侧同款 `tools/mcp_oauth_manager.py:558-569 @ 863e313`,多一个 dashboard-flow 豁免)。
2. **redirect 边界**:有缓存 token 但已废(刷新被拒),SDK 落进授权码流、要弹 URL 时再抛——防止"打印一个没人能完成的 URL 然后傻等 300s"(`tools/mcp_oauth.py:722-735 @ 863e313`)。
3. **callback 边界**:在**绑定监听端口之前**抛——否则会占住端口 300s,下一轮重连撞出 `Errno 98 Address already in use`(`tools/mcp_oauth.py:841-856 @ 863e313`)。

**重实现要点**:① 交互性是三态(强制/抑制/探测)且必须用 ContextVar 承载才能穿过 `run_coroutine_threadsafe`;② 非交互 fail-fast 不能只在入口查一次——token 存在≠token 可用,授权 URL 边界与回调绑定边界各需一道;③ 报错话术集中一处生成,保证每个边界给同样的下一步指引。

### 2.3 token 存储:三文件、0o600、绝对过期、快照回滚

**布局**:每 server 三个 JSON,按 HERMES_HOME 分 profile 隔离(`tools/mcp_oauth.py:434-439 @ 863e313`):
```
HERMES_HOME/mcp-tokens/<server_name>.json         -- tokens
HERMES_HOME/mcp-tokens/<server_name>.client.json   -- client info
HERMES_HOME/mcp-tokens/<server_name>.meta.json     -- oauth server metadata
```
文件名经 `_safe_filename` 消毒(`re.sub(r"[^\w\-]", "_", name).strip("_")[:128] or "default"`,`tools/mcp_oauth.py:196-198 @ 863e313`)——server 名来自用户 config,防路径穿越(配套测试 `TestPathTraversal`)。

**写入**:`_write_json` 用 `os.open(O_EXCL, 0o600)` 原子创建 + `fsync` + `os.replace`,并先 `secure_parent_dir` 把父目录压成 0o700:

`tools/mcp_oauth.py:390-416 @ 863e313`(节选)
```python
    Uses ``os.open`` with ``O_EXCL`` and an explicit mode so the file is
    created atomically at 0o600. The previous ``write_text`` + post-write
    ``chmod`` opened a TOCTOU window where the temp file briefly inherited
    the process umask (commonly 0o644 = world-readable), exposing OAuth
    tokens to other local users between create and chmod. Mirrors the fix
...
    tmp = path.with_suffix(f".tmp.{os.getpid()}.{secrets.token_hex(4)}")
...
        fd = os.open(
            str(tmp),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            stat.S_IRUSR | stat.S_IWUSR,
        )
...
        os.replace(tmp, path)
```
`secure_parent_dir` 拒绝 chmod `/` 及一级目录,防 HERMES_HOME 解析异常时把 `/home` 整个改 0o700(`hermes_constants.py:809-816 @ 863e313`,#25821)。

**绝对过期(Fix A,任务点 3 的核心)**:OAuth 响应只有相对 `expires_in`,进程重启后毫无意义。`set_tokens` 写盘时追加绝对 `expires_at = time.time() + expires_in`(`tools/mcp_oauth.py:504-511 @ 863e313`);`get_tokens` 读盘时反向换算剩余 TTL,并处理没有 `expires_at` 的 legacy 文件(用文件 mtime 作近似写入时刻):

`tools/mcp_oauth.py:475-487 @ 863e313`
```python
        absolute_expiry = data.pop("expires_at", None)
        if absolute_expiry is not None:
            data["expires_in"] = int(max(absolute_expiry - time.time(), 0))
        elif data.get("expires_in") is not None:
            try:
                file_mtime = self._tokens_path().stat().st_mtime
            except OSError:
                file_mtime = None
            if file_mtime is not None:
                try:
                    implied_expiry = file_mtime + int(data["expires_in"])
                    data["expires_in"] = int(max(implied_expiry - time.time(), 0))
```
`expires_at` 在 `model_validate` 前被 `pop` 掉——它不属于 SDK 的 `OAuthToken` schema。这只是修复的一半,另一半在 manager 的 `_initialize`(§3.2)。损坏文件一律 log+返回 None,不炸流程(`:489-493`)。

**metadata 持久化**:SDK 只在内存里留发现到的 `OAuthMetadata`(token_endpoint 等);Hermes 落成 `.meta.json`,否则重启后冷刷新会退回 SDK 猜的 `{server_url}/token`,大多数真实 provider 404,进而强迫整轮浏览器重授权(`tools/mcp_oauth.py:533-543 @ 863e313` 注释 + `save_oauth_metadata`/`load_oauth_metadata`)。

**快照/回滚/自杀开关**:
- `snapshot()`/`restore(snapshot, only_if_absent=True)`:重授权前拍三文件快照,失败时回滚——但 `only_if_absent` 保证不覆盖并发成功写入的新 token(`tools/mcp_oauth.py:564-606 @ 863e313`)。dashboard 重授权事务就靠这对(§4.3)。
- `poison_client_registration()`:IdP 在 token endpoint 回 `invalid_client` 时删 `client.json`+`meta.json`(留 `.bak`),迫使 SDK 下一轮走 `if not client_info` 分支重跑 RFC 7591;**tokens 故意不删**——万一重注册失败,还留着可能有效的 refresh_token(`tools/mcp_oauth.py:608-641 @ 863e313`)。

**重实现要点**:① token 文件必须 O_EXCL+0o600 原子创建,写后 chmod 是 TOCTOU 漏洞;② 持久化必须存**绝对**过期时刻,读时换算相对值喂给 SDK;③ legacy 数据用 mtime 兜底并在下次写入时自愈;④ 授权服务器 metadata 也要持久化,否则冷启动刷新必挂;⑤ 一切破坏性操作(重授权、重注册)先快照、失败回滚、回滚不压新数据。

### 2.4 回调接收:端口、TOCTOU、粘贴回退

**端口选择优先级**(`_configure_callback_port`,`tools/mcp_oauth.py:1052-1098 @ 863e313`):dashboard flow(端口 0,不开监听)→ 缓存的 https 代理 redirect_uri → 显式 `oauth.redirect_port` → **缓存的客户端注册端口** → 新预留临时端口:

`tools/mcp_oauth.py:1095-1097 @ 863e313`
```python
    port = requested or _cached_redirect_port(storage) or _reserve_callback_port()
    cfg["_resolved_port"] = port
    _oauth_port = port  # legacy consumer: _wait_for_callback reads this
```
"缓存端口"一档解决的真实故障:DCR 把 `client_id` 和确切 redirect URI 绑死,重启换随机端口 + 复用旧 client_id ⇒ provider 拒绝 `redirect_uri does not match any registered URIs`;所以从 `client.json` 里的 `redirect_uris` 反解出上次的 loopback 端口复用(`tools/mcp_oauth.py:245-277 @ 863e313`)。

**TOCTOU 关闭(#22161)**:传统 `_find_free_port()`(bind 端口 0 → 读端口号 → 关 socket)与几分钟后 HTTPServer 真正 bind 之间,端口可能被别的进程抢走。Hermes 的做法是**选端口时就 bind 住不放**,socket 存进 `_reserved_sockets`(上限 8,FIFO 逐出防 fd 泄漏,`tools/mcp_oauth.py:210-242 @ 863e313`),等 `_wait_for_callback` 到点**收养**这个已 bind 的 socket 再 `server_activate()`:

`tools/mcp_oauth.py:869-882 @ 863e313`
```python
            server = HTTPServer(
                ("127.0.0.1", port), handler_cls, bind_and_activate=False
            )
            reserved = _reserved_sockets.pop(port, None)
            if reserved is not None:
                # Adopt the reserved (already bound) socket and start listening.
                server.socket.close()
                server.socket = reserved
                server.server_address = reserved.getsockname()
                server.server_activate()
            else:
                server.allow_reuse_address = True
                server.server_bind()
                server.server_activate()
```
显式/缓存端口不预留,走 `allow_reuse_address`(必须**在 bind 前**设,构造后设是 no-op——#44590,TIME_WAIT 残留会挡住下一轮)。bind 失败不再谎报"timed out",直接抛"port already in use + 改 `oauth.redirect_port`"的可行动错误(`:883-893`)。

**并发流隔离(#34588/#34260)**:redirect handler 和 callback waiter 都是**闭包捕获各自端口**的工厂(`_make_redirect_handler(port)` / `_make_callback_waiter(port)`),不读模块级 `_oauth_port`——两个 server 并发 OAuth 时,后者覆盖全局不影响前者。旧全局仅为 legacy `_wait_for_callback` 保留,且 `_oauth_port is None` 时抛 RuntimeError 而非 assert(`-O` 下 assert 会被吃掉,`tools/mcp_oauth.py:794-812 @ 863e313`)。

**等待循环**:HTTP 监听线程(`server.handle_request` 单请求)+ 可选 stdin 粘贴线程赛跑,共享 result dict,先写者胜;主协程 0.5s 轮询、300s 超时,`finally: server.server_close()`(`tools/mcp_oauth.py:895-938 @ 863e313`)。粘贴回退 `_paste_callback_reader` 接受完整 URL / 只有 query / `skip` 等跳过词;`skip` 写入哨兵 `__hermes_user_skipped__`,waiter 把它映射为 `OAuthNonInteractiveError("user_skipped")`,上游按"跳过该 server 继续启动"处理而非硬失败(`tools/mcp_oauth.py:169-176, 928-936, 943-1024 @ 863e313`)。SSH 场景 redirect handler 打印两条出路(粘贴 / `ssh -L` 端口转发),且配置了代理 `redirect_uri` 时换成"无需隧道"的提示(`tools/mcp_oauth.py:744-777 @ 863e313`)。

**redirect_uri 两个旋钮**(`_resolve_redirect_uri`,`tools/mcp_oauth.py:1101-1122 @ 863e313`):
- `oauth.redirect_uri`:公网 HTTPS 代理(如 Tailscale Funnel)转发回本机;
- `oauth.redirect_host: localhost`:只改 URL 里的主机名,监听仍 bind `127.0.0.1`——绕过 Reclaim.ai 这类 WAF 对 query 串里字面 `127.0.0.1` 的 403。
注释强调:client metadata 与预注册 client info 的 redirect_uri **必须同源推导**,不一致授权服务器直接拒。

**重实现要点**:① 临时端口从"探测后释放"改成"探测即持有、监听时收养",这是唯一能真正关掉 select→bind TOCTOU 的做法;② 端口优先级里必须有"上次注册过的端口"一档,否则 DCR 绑定 redirect URI 的 provider 重启必挂;③ 并发流的端口用闭包不用全局;④ HTTP 监听之外必须有 stdin 粘贴回退 + 显式 skip 语义(远程/无隧道场景);⑤ `allow_reuse_address` 在 bind 前设。

### 2.5 CSRF / 混淆代理攻击的防御分层(任务点 2 后半)

- **state**:由 SDK 生成(`secrets.token_urlsafe(32)`)并在回调返回后 `secrets.compare_digest` 常量时间比对,mismatch 抛 `OAuthFlowError`(`oauth2.py:359-362 @ mcp==1.28.1`)。**loopback 回调 handler 本身不校验 state**(`_make_callback_handler` 只是抄参数进 result dict,`tools/mcp_oauth.py:663-689 @ 863e313`)——校验点在 SDK,handler 只是传声筒;本地恶意进程抢先向回调端口塞假 code,会在 SDK 的 state 比对处死掉。dashboard 侧则在**投递前**就比对(§4.2),因为那条 HTTP 路由是免鉴权的。
- **code 注入**:PKCE S256——攻击者拿到 code 也没有 code_verifier,换不出 token。
- **混淆代理(token 被错发)**:RFC 8707 resource 参数 + SDK 的 `_validate_resource_match`(§1d);加上 Hermes 在 `mcp_tool.py` 的**跨源重定向剥 Authorization**(§5),token 不会跟着 3xx 流到别的 origin。
- **回调仅绑 loopback**:监听永远 `127.0.0.1`(即使 `redirect_host: localhost`),不暴露外网。
- **invalid_client 自愈的误杀防线**:manager 动手删注册前,用 `_same_endpoint` 确认响应真的来自发现到的 token endpoint(scheme+host+path 三元比对,`tools/mcp_oauth_manager.py:48-65 @ 863e313`)——防止任意 400 响应触发注册自毁。

**重实现要点**:state 校验必须用常量时间比较且发生在"决定接受这份 code"之前;回调通道免鉴权时(dashboard 公网路由),state 就是唯一的能力凭证,必须在路由层比对;resource 绑定 + 跨源剥头是混淆代理的两道互补闸。

### 2.6 provider 现实补丁:Figma DCR 白名单

Figma 远端 MCP 把 RFC 7591 实现成 **client_name 白名单**:`"Claude Code"`/`"Codex"` 200,其余(含 `"Hermes Agent"`)403——2026-07 实测记录直接写在常量注释里(`tools/mcp_oauth.py:1125-1136 @ 863e313`)。`apply_oauth_provider_defaults` 只填用户未设的键:client_name→`"Claude Code"`、scope→`mcp:connect`、以及 Figma 的另一个坑——注册响应宣称 `token_endpoint_auth_method=none` 却又发 secret、token endpoint 又要求 secret,所以强制 `client_secret_post`(`tools/mcp_oauth.py:1166-1184 @ 863e313`)。注册 403 时 `humanize_oauth_registration_error` 把裸 "403 Forbidden" 翻译成可行动指引(Figma 专版 + 通用版,`tools/mcp_oauth.py:1256-1303 @ 863e313`),CLI 与 dashboard 两侧都调它。

**重实现要点**:DCR 在野外不是开放注册,是各家自定义的准入策略;provider 特判要走"只填未设键"的 defaults 层,用户显式配置永远赢;协议错误要在边界翻译成"下一步做什么"。

### 2.7 装配入口 `build_oauth_auth`

顺序:SDK 可用检查 → copy cfg → provider defaults → storage → 非交互+无 token fail-fast → 配端口 → build client metadata → 预注册落盘(配置了 `client_id` 时直接写 `client.json`,SDK 便跳过 DCR,`tools/mcp_oauth.py:1223-1253 @ 863e313`)→ 用闭包工厂造 redirect/callback handler → 构造 SDK `OAuthClientProvider`(timeout 默认 300s)(`tools/mcp_oauth.py:1306-1369 @ 863e313`)。此函数是 legacy 公共 API;新路径一律走 manager(docstring `:1313-1315` 明说),manager 的 `_build_provider` 复用同一批下划线助手,保证两条构造路径一份实现(`tools/mcp_oauth.py:1043-1049 @ 863e313`)。

---

## 3. `mcp_oauth_manager.py` 逐机制(任务点 3/4)

### 3.1 组织方式:key=(home, server),三层锁

- 缓存键:`(str(resolve(hermes_home)), server_name)`(`tools/mcp_oauth_manager.py:502-510 @ 863e313`)——同名 server 在不同 profile(不同 HERMES_HOME)互不串 token;配套测试 `test_manager_isolates_same_named_servers_by_profile_home`。
- `_entries_lock`(threading.Lock)管 get-or-create;每 entry 一个 `asyncio.Lock` 管盘监视/401 状态(绑定 MCP 事件循环);`_MANAGER_LOCK` 管单例(`:446-461, 768-778`)。
- `get_or_build_provider` 幂等:同名同 URL 返回同实例;**URL 变了丢弃重建**(`:479-487`);这正是 `mcp_tool.py` 重连路径复用同一 provider 的前提(配套测试 `test_provider_is_reused_across_reconnects`)。
- 三种清除语义分开:`remove`(缓存+磁盘全删,login/remove 用)、`evict`(只丢进程内 provider,保磁盘)、`restore_entry`(`setdefault` 回填,不压并发新 entry)(`:590-633`)。

### 3.2 `HermesMCPOAuthProvider._initialize`:冷加载三合一(任务点 3 的"过期冷加载")

SDK 基类 `_initialize` 只加载 `current_tokens`,**不调 `update_token_expiry`**,于是 `token_expiry_time=None`、`is_token_valid()` 对任何旧 token 恒 True——重启后带着僵尸 Bearer 直接打服务器;有的 provider 回 401(能被抓),有的回 200+应用层报错(BetterStack 的 "No teams found",传输层不可见)。子类补三步:

1. **播种过期时刻**(与 §2.3 的 `expires_at` 持久化配对):

   `tools/mcp_oauth_manager.py:181-184 @ 863e313`
   ```python
            await super()._initialize()
            tokens = self.context.current_tokens
            if tokens is not None and tokens.expires_in is not None:
                self.context.update_token_expiry(tokens)
   ```
   之后 SDK 的抢先刷新分支(`oauth2.py:500-507 @ mcp==1.28.1`:`if not self.context.is_token_valid() and self.context.can_refresh_token(): refresh_request = await self._refresh_token()`)才会对真过期的 token 生效。

2. **从磁盘恢复 metadata**(`:189-205`):有 `.meta.json` 就灌回 `context.oauth_metadata`,冷刷新直达正确 token_endpoint。

3. **预飞行发现**(`:207-299`):有 token 但既无盘上也无内存 metadata 时,同步跑一遍 PRM→ASM 双段发现(复用 SDK 自己的 URL builder / response handler,10s 超时)并立即落盘。针对的具体故障:BetterStack 的 MCP 在 `mcp.betterstack.com` 而 token endpoint 在 `betterstack.com/oauth/token`,不预飞行则刷新 404 → 每次重启弹一轮浏览器。失败非致命,退回 SDK 的 401 分支懒发现;无 token 时**跳过**(新装机不白跑两次网络往返,由测试钉死)。

补一个懒路径的对称持久化:401 分支跑完后 `_persist_oauth_metadata_if_changed()` 把 SDK 懒发现的 metadata 也落盘(`:301-320`,在生成器 `StopAsyncIteration` 时调用,`:428-432`)。

**刷新时机与失败路径全图**(SDK 分支 + Hermes 挂点):
```
每个请求进入 async_auth_flow
 ├─ 先问 manager.invalidate_if_disk_changed(外部换过 token?)          [Hermes]
 ├─ token 过期 && 有 refresh_token → 抢先刷新(POST token_endpoint)     [SDK]
 │    └─ 刷新失败 → _initialized=False → 落入完整重授权                 [SDK]
 ├─ token 有效 → 加 Authorization: Bearer → 发请求                      [SDK]
 ├─ 响应 401 → PRM→ASM 发现 → (无 client_info 则 DCR) → 授权码+PKCE     [SDK]
 │    ├─ redirect_handler 弹 URL(非交互→抛 OAuthNonInteractiveError)   [Hermes]
 │    ├─ callback_handler 收 code(loopback/粘贴/dashboard)             [Hermes]
 │    └─ state 比对 → 换 token → set_tokens 落盘(带 expires_at)        [SDK+Hermes]
 ├─ 响应 400/401 且来自 token_endpoint 且 body 含 invalid_client
 │    → poison 注册,下轮重跑 DCR                                       [Hermes]
 └─ 响应 403 insufficient_scope → step-up 重授权                        [SDK]
```

### 3.3 双向生成器桥(一次真实事故)

httpx 的 auth flow 是**双向**异步生成器:驱动方用 `auth_flow.asend(response)` 把 HTTP 响应喂回生成器。PR #11383 曾用 `async for item in inner: yield item` 包装——`asend` 的值被丢弃、内层以 None 恢复,SDK 在 `if response.status_code == 401` 处 `AttributeError`,**每个 OAuth MCP server 第一个响应就炸**,而 CI 没抓到是因为没有任何测试驱动完整 `.asend()` 往返。修复是手写桥:

`tools/mcp_oauth_manager.py:419-432 @ 863e313`
```python
            inner = super().async_auth_flow(request)
            try:
                outgoing = await inner.__anext__()
                while True:
                    incoming = yield outgoing
                    # Sniff the response for a dead-client-registration signal
                    # before handing it back to the SDK (best-effort, GH#36767).
                    await self._maybe_flag_poisoned_client(incoming)
                    outgoing = await inner.asend(incoming)
            except StopAsyncIteration:
                # Persist any metadata the SDK discovered lazily during the
                # 401 branch so a subsequent cold-load skips discovery.
                self._persist_oauth_metadata_if_changed()
                return
```
桥同时是两个旁路钩子的挂点:每个进入的响应先过 invalid_client 嗅探;流结束时持久化懒发现的 metadata。

### 3.4 跨进程盘监视

`invalidate_if_disk_changed`:比对 tokens 文件 `st_mtime_ns` 与 entry 记录值,变了就把 SDK provider 的私有 `_initialized` 置 False,下一个 auth flow 从存储重读(`tools/mcp_oauth_manager.py:657-678 @ 863e313`;`_initialized` 是私有 API,注释声明"在我们钉的 >=1.26.0 版本区间稳定")。调用点两处:每次 `async_auth_flow` 前(`:394-398`,失败非致命)与 `handle_401` 第一步。这是"cron 在外部刷新 token、运行中的会话不重启即生效"的核心;设计参照 Claude Code 的 `invalidateOAuthCacheIfDiskChanged` 与 Codex 的 `refresh_oauth_if_needed`,并明说取舍:每次 tool call 一次 `stat()` 比每次都 await 刷新便宜(`:23-33`)。

### 3.5 401 去重(防雷鸣群)

N 个并发 tool call 用同一个失效 access_token 撞 401 时,只放一个恢复尝试,其余 await 同一个 future:

`tools/mcp_oauth_manager.py:704-711 @ 863e313`
```python
        key = failed_access_token or "<unknown>"
        loop = asyncio.get_running_loop()

        async with entry.lock:
            pending = entry.pending_401.get(key)
            if pending is None:
                pending = loop.create_future()
                entry.pending_401[key] = pending
```
恢复逻辑两步:①盘变了?→ True(caller 重连重试);②SDK `can_refresh_token()`?→ 返回其布尔值(True 表示"重连后 SDK 会在握手时自己刷新")。**manager 自己从不发刷新请求**——刷新永远由 SDK 的 auth flow 在下一个请求里做,manager 只回答"值不值得重试"。细节:任务存进 `self._inflight_tasks` 强引用集合,防事件循环弱引用簿记把任务 GC 掉、留下永远挂起的 waiter(`:456-460, 749-751`;配套测试 `test_handle_401_tracks_inflight_task_to_prevent_gc`);`finally` 里 `pending_401.pop(key)` 清位。

### 3.6 invalid_client 自愈(撤销/清理的自动化半区)

`_maybe_flag_poisoned_client` 判定三条件全真才动手:status∈{400,401}、请求 URL 与发现到的 token_endpoint 同端点(`_same_endpoint`)、body 词边界匹配 `\binvalid_client\b`(**排除** RFC 7591 的 `invalid_client_metadata`,`tools/mcp_oauth_manager.py:370-374 @ 863e313`)。动作:`storage.poison_client_registration()` + 内存 `client_info=None` + `_initialized=False`。**预注册(config 提供 client_id)的永不 poison**——删了也会被 config 重新种上,重注册救不了配置错误(`:143-147, 352-354`)。整个探测 best-effort,任何异常吞掉不断主流程。手动半区:浏览器侧 "Redirect URI Mismatch" 无 HTTP 信号,归 `hermes mcp reauth`(GH#36767)。

**重实现要点(manager 整体)**:① provider 必须进程级单例缓存、按 (home, server) 键控,重连复用同一实例才能让盘监视/去重生效;② 冷启动三件事缺一不可:播种绝对过期、恢复持久化 metadata、必要时预飞行发现;③ 包装 httpx auth flow 必须手写 `asend` 桥,`async for` 转发是静默数据丢失;④ 外部刷新用 mtime 失效而非轮询刷新——一次 stat 换一次可能的往返;⑤ 401 去重按失效 token 键控 future,任务持强引用;⑥ 自动重注册的触发条件要收得极窄(端点匹配+词边界),且永远不碰用户手配的凭据。

---

## 4. `mcp_dashboard_oauth.py` 与 dashboard 接线(任务点 6)

### 4.1 用途

浏览器场景(web dashboard、desktop)里,用户不在 stdin 上、loopback 端口也可能不可达(Hermes 跑在远端/容器)。本模块把 SDK 的两个人机回调改道:`redirect_handler` 不再打印/弹浏览器,而是 `publish_authorization_url` 把 URL 交给 dashboard 前端展示;`callback_handler` 不再开 loopback 监听,而是 `wait_for_callback` 等 dashboard 的 HTTP 回调路由投递。改道判定就是 ContextVar 里有没有当前 flow(`tools/mcp_oauth.py:715-720, 835-839, 1076-1079 @ 863e313`;`_configure_callback_port` 在 dashboard 模式下端口置 0、redirect_uri 用 flow 的公网回调 URL)。

### 4.2 `DashboardOAuthFlow`:线程安全状态机

字段+三个 `threading.Event`(authorization_ready / callback_ready / worker_done)+一把锁(`tools/mcp_dashboard_oauth.py:21-40 @ 863e313`)。关键约束:

- `publish_authorization_url` 从授权 URL 里**解析出 state 存为 `expected_state`**,URL 无 state 直接 ValueError(`:42-52`);
- `deliver_callback` 一次性(重复投递 ValueError)+ state 常量时间比对:

  `tools/mcp_dashboard_oauth.py:69-77 @ 863e313`
  ```python
        with self._lock:
            if self._callback_ready.is_set():
                raise ValueError("OAuth callback already received")
            if (
                self.expected_state is None
                or state is None
                or not secrets.compare_digest(self.expected_state, state)
            ):
                raise ValueError("OAuth callback state mismatch")
  ```
- `wait_for_*` 用 `asyncio.to_thread(event.wait, timeout)` 桥接线程事件与协程(授权 URL 30s、回调 300s);`mark_error` 同时 set 两个 event 防死等;`snapshot()` 给前端轮询用——**不含 code**(配套测试 `test_flow_status_does_not_expose_authorization_code`)。

ContextVar `_current_dashboard_flow` + `dashboard_oauth_flow(flow)` 上下文管理器完成传播(`:130-145`);又因为 `run_coroutine_threadsafe` 的任务在**循环线程**里创建、拷的是循环线程的 context,`mcp_tool._run_on_mcp_loop` 特意在任务自己的作用域里重新 set 一遍(`tools/mcp_tool.py:4431-4449, 4486 @ 863e313`)。

### 4.3 web 侧接线(三条路由 + 一个 worker 事务)

- `POST /api/mcp/servers/{name}/auth`(需 dashboard token):造 `flow_id=secrets.token_urlsafe(24)` 的 flow,redirect_uri 用配置值或**公网回调 URL** `{public_url}/api/mcp/oauth/callback/<server>`(`hermes_cli/web_server.py:12148-12162 @ 863e313`);全局并发上限 8、同 (home,server) 已有未完流 409、TTL 15 分钟 GC(`hermes_cli/web_routers/mcp.py:230-250 @ 863e313`;`hermes_cli/web_server.py:12122-12139`);起 daemon 线程跑 worker,等 30s 拿到授权 URL 即返回 snapshot。
- `GET /api/mcp/oauth/flows/{flow_id}`(需 token):轮询状态。
- `GET /api/mcp/oauth/callback/{server_name}`:**免 dashboard 鉴权**——授权服务器重定向来的浏览器请求不带 dashboard 凭据(`hermes_cli/web_server.py:664-665 @ 863e313`:`is_mcp_oauth_callback = path.startswith("/api/mcp/oauth/callback/")` 从 401 门里豁免)。因此路由层用 **state 匹配来选 flow**(在所有 `authorization_required` 状态的同名候选里 `compare_digest` 命中才投递,`hermes_cli/web_routers/mcp.py:284-304 @ 863e313`)——state 就是这条免鉴权路由的能力凭证;`deliver_callback` 内部再做一次一次性+比对双保险。
- worker `_run_dashboard_mcp_oauth`(`hermes_cli/web_server.py:12171-12251 @ 863e313`):设 HERMES_HOME override + secret scope → `with transaction, force_interactive_oauth(), dashboard_oauth_flow(flow):` → 先 `storage.snapshot()` + `manager.remove()`(强制全新流)→ `_probe_single_server`(超时下限 315s = 300s 回调窗 + 余量)→ **校验 token 真落盘**(`_oauth_tokens_present`,防"server 无鉴权也能 tools/list"的假成功,与 CLI 同款,§4.4)→ `_save_mcp_server` + `mark_approved` + 若 `reconnect_live` 则热重连;任何异常 → `storage.restore(backup, only_if_absent=True)` + `manager.restore_entry` 回滚 + `humanize_oauth_registration_error` 翻译后 `mark_error`。

### 4.4 CLI 对应面:`hermes mcp login` / `reauth`

`_reauth_oauth_server`(`hermes_cli/mcp_config.py:787-884 @ 863e313`)与 dashboard worker 同构:`get_manager().remove(name)` 清盘+清缓存 → `force_interactive_oauth()` 下 `_probe_single_server`(timeout 同样下限 315s)→ `_oauth_tokens_present` 验真。假成功的具体事故写在两处注释里:Google Drive 官方 server 不支持 RFC 7591(注册 400),但 initialize/tools-list **无鉴权也放行**,probe 看起来成功、真 tool call 全部超时;所以"成功"的定义必须是"token 文件存在",不是"probe 通了"(`hermes_cli/mcp_config.py:839-847 @ 863e313`)。

**重实现要点**:① GUI 化 OAuth 不需要动协议,只需把 redirect/callback 两个回调改道成"发布-等待"会合点;② 免鉴权回调路由必须用 state 作能力凭证选流 + 一次性投递 + 常量时间比对;③ 状态轮询接口绝不回传 code;④ 重授权是事务:快照→清空→跑流→**验 token 落盘**→保存,失败回滚且不压新数据;⑤ "登录成功"的判据必须是凭据落盘,不是连接成功。

---

## 5. 与 R3 七道防护的衔接(任务点 5)

R3 台账里 `mcp_tool.py` 的七道客户端防护(命名撞车 fail-closed、恶意包预检、内容类型预检、stdio watchdog、跨源鉴权剥离、断路器、schema 消毒)与 OAuth 的接缝:

1. **鉴权注入点分两路**:静态凭据走 config `headers`(`Authorization: "Bearer sk-..."` 示例,`tools/mcp_tool.py:38-39 @ 863e313`),整 dict 进 httpx client;OAuth 走 `auth=` kwarg——`_auth_type == "oauth"` 时经 manager 取 provider,三种传输(StreamableHTTP 新旧 API、SSE)各自把 `_oauth_auth` 塞进 `auth`(`tools/mcp_tool.py:2779-2788, 2822-2826, 2916-2917, 2960-2961 @ 863e313`;SSE 那处注释记录了"曾建好但没转发、SSE OAuth 静默 401"的老 bug)。Bearer 头由 SDK 在 auth flow 里逐请求注入,不落静态 headers。
2. **跨源鉴权剥离**(第五道防护)对两路都生效:响应事件钩子在重定向目标 (scheme,host,port) 与原始 URL 不同时,把 `next_request` 的 Authorization 弹掉(`tools/mcp_tool.py:2898-2906 @ 863e313`)——OAuth token 与静态 Bearer 都不会跟着 3xx 泄到别的 origin。
3. **内容类型预检对 OAuth 豁免**:无 token 时端点合法地回 401/HTML,预检若照跑会把 OAuth 流挡死在起跑线(`tools/mcp_tool.py:3113-3116 @ 863e313`:`... and self._auth_type != "oauth"`)。
4. **401 恢复链路**:tool handler 抓到 auth 类异常(`_is_auth_error`:SDK 的 OAuthFlowError/OAuthTokenError、Hermes 的 OAuthNonInteractiveError、httpx 401,`tools/mcp_tool.py:3778-3836 @ 863e313`)→ `manager.handle_401`(去重)→ 可恢复则 `_signal_reconnect_and_wait` 撕掉重建 MCP 会话(SDK 在新会话握手时完成实际刷新)→ 重试一次;不可恢复或重试仍败 → `needs_reauth=True` 结构化错误 + **断路器**(第六道防护)`_bump_server_error`,并在错误文案里直接命令模型"Do NOT retry this tool — ask the user to re-authenticate"(`tools/mcp_tool.py:3929-3940 @ 863e313`);反向地,恢复+重连成功即 `_reset_server_error` 关断路器(`:3903-3911`)。
5. **启动期隔离**:后台发现 `suppress_interactive_oauth`(§2.2),`OAuthNonInteractiveError` 被当作"跳过该 server、其余照连",OAuth 的不可用不能拖垮整个 harness 启动(`tools/mcp_tool.py:2776-2778 @ 863e313` 注释:"re-raise so this server is reported as failed without blocking other MCP servers")。
6. **会话过期 ≠ 鉴权过期**:server 端传输会话被 GC 时 token 仍有效,走独立的 session-expired 标记重连,不触发 OAuth 恢复(`tools/mcp_tool.py:3943-3949, 5072-5073 @ 863e313`)。

**重实现要点**:auth 失败的出口必须是**结构化**的 `needs_reauth` + 断路器 + 对模型的明示禁令,否则 LLM 会无限重试或幻觉出"手动刷新"操作;OAuth server 要在预检、启动、会话过期三个机制里都有显式豁免/分流,不能与静态鉴权同路处理。

---

## 6. website/docs vs 代码(任务点 7,双方证据)

**▲ 冲突 1:文档描述了不存在的"端口自动跳号"与提示语。**
- 文档:`website/docs/guides/oauth-over-ssh.md:152 @ 863e313`
  ```
  The redirect never made it back to the remote listener. Check the tunnel is still alive (`ssh -N` doesn't show output, so look at the terminal you started it from), confirm you used the port from the latest `Waiting for callback on ...` line (Hermes may auto-bump if the preferred port is busy), restart the tunnel if needed, and re-run the auth command.
  ```
- 代码:全仓(plugins/tools/agent)搜不到字符串 `Waiting for callback on`(rg 实测零命中);且 MCP OAuth 端口被占时**不 auto-bump**,直接抛可行动错误:`tools/mcp_oauth.py:889-893 @ 863e313`
  ```python
              raise OAuthNonInteractiveError(
                  f"OAuth callback port {port} is already in use ({exc}). "
                  "Close any other in-progress login, or set a free `oauth.redirect_port` "
                  "in the server config, then retry."
              ) from exc
  ```
  定案:该段 troubleshooting 覆盖 Spotify+MCP 两类流,但对 MCP OAuth 而言提示语和 auto-bump 行为都不成立(而且 auto-bump 恰是 §2.4 的"缓存端口一致性"要**避免**的),以代码为准。

**▲ 冲突 2:config 参考页称 OAuth 仅限 Streamable HTTP,代码明确支持 SSE。**
- 文档:`website/docs/reference/mcp-config-reference.md:314 @ 863e313`
  ```
  - Only applies to HTTP/StreamableHTTP transport (`url`-based servers)
  ```
- 代码:`tools/mcp_tool.py:2822-2826 @ 863e313`
  ```python
            if _oauth_auth is not None:
                # Pass OAuth auth through to sse_client so SSE MCP servers
                # behind OAuth 2.1 PKCE work. Previously built but never
                # forwarded — SSE OAuth would silently fail with 401s.
                _sse_kwargs["auth"] = _oauth_auth
  ```
  定案:文档滞后于 SSE OAuth 修复;若把"url-based"读宽也能圆,但"HTTP/StreamableHTTP"的字面排除了 `transport: sse`,以代码为准。

**◇ 核对为一致的关键陈述**(记录避免重查):`user-guide/features/mcp.md:218`(auth: oauth 全托 SDK)、`:240`(token 落 `~/.hermes/mcp-tokens/<server>.json`、0o600——对应 `_get_token_dir`/`_write_json`)、`:221-227`(Figma client_name 白名单——对应 `_FIGMA_DCR_CLIENT_NAME`)、`:260`(`redirect_host: localhost` WAF 绕行——对应 `_resolve_redirect_uri`)、`:264`(Google Drive 假成功 + login 验 token 落盘——对应 `_oauth_tokens_present`)、`:278` 与 `oauth-over-ssh.md:74`(30s 配置重载不够跑 OAuth,用 `hermes mcp login` 的 315s 下限——对应 `hermes_cli/mcp_config.py:834`)、`oauth-over-ssh.md:51-64`(粘贴回退,含裸 `?code=...&state=...`——对应 `_paste_callback_reader`)。

---

## 7. 配套测试台账(任务点:7 个文件 + 2 个行为规格)

`tests/tools/` 下 OAuth 簇 7 文件(LT 层,行为规格参照):

| 文件 | 行数 | 钉死的行为 |
|---|---|---|
| `test_mcp_oauth.py` | 836 | 存储往返、0o600、损坏容错、文件名消毒、端口预留/收养/并发隔离、SSH 提示、非交互三道 fail-fast、suppress 跨 `run_coroutine_threadsafe` 传播、metadata/redirect_uri 参数化 |
| `test_mcp_oauth_manager.py` | 366 | profile 隔离、restore 不压新 entry、盘监视失效、401 任务强引用/引用丢失仍去重、invalid_client poison 三条件(含 `invalid_client_metadata` 不误触) |
| `test_mcp_oauth_cold_load_expiry.py` | 474 | 见下 |
| `test_mcp_oauth_bidirectional.py` | 210 | 见下 |
| `test_mcp_oauth_integration.py` | 175 | 外部刷新免重启生效、401 并发去重端到端、重连复用同一 provider |
| `test_mcp_oauth_metadata.py` | 152 | `.meta.json` 往返、remove 连删、`_initialize` 盘恢复、auth flow 完成时懒持久化 |
| `test_mcp_dashboard_oauth.py` | 113 | flow 状态机、单次回调、dashboard 模式不开 loopback 端口、失败回滚不压新状态 |

毗邻:`tests/tools/test_mcp_tool_401_handling.py`(106 行,needs_reauth 出口)、`tests/hermes_cli/test_mcp_dashboard_oauth.py`(web 路由侧:公网授权 URL、callback 绕 cookie 门、跨 profile 同名、**状态接口不泄 code**)。

**行为规格详述 ①:`test_mcp_oauth_cold_load_expiry.py`** —— 把 Fix A 的完整契约钉成四组断言:`set_tokens` 必须写绝对 `expires_at`(且 `before+3600 <= expires_at <= after+3600` 夹逼,无 `expires_in` 时不得捏造);`get_tokens` 读回的 `expires_in` 必须是剩余 TTL(睡 50ms 后 `3500 < expires_in <= 3600`),已过期文件必须回 `expires_in == 0`;legacy 文件(无 `expires_at`)用 `os.utime` 回拨 mtime 后同样必须钳到 0;`HermesMCPOAuthProvider._initialize` 后 `context.token_expiry_time` 非 None 且落在 `(now+7000, now+7200+5]`。文件头 33 行 docstring 本身就是事故报告:PR #11383 修了盘监视和 401 去重,但留下"相对 expires_in 重启后无意义 + SDK `_initialize` 不播种 expiry ⇒ `is_token_valid()` 恒 True ⇒ 僵尸 Bearer 出门"两个潜伏 bug,并点名 BetterStack 的 200+应用层报错这种传输层不可见的失败形态(`tests/tools/test_mcp_oauth_cold_load_expiry.py:1-33 @ 863e313`)。后两条测试用 `httpx.MockTransport` 演 BetterStack 式分离源发现(PRM 在 `mcp.example.com` 指向 `auth.example.com`,断言 `token_endpoint == https://auth.example.com/oauth/token`),并断言**无 token 时预飞行零网络调用**(`assert calls == []`)。

**行为规格详述 ②:`test_mcp_oauth_bidirectional.py`** —— 唯一手动驱动 httpx `asend` 往返的测试,钉死生成器桥的双向契约。测试一:种好 token+client_info,`flow.__anext__()` 拿到出站请求后 `flow.asend(httpx.Response(200))` 必须干净 `StopAsyncIteration` 结束——坏桥在此处 `AttributeError: 'NoneType' object has no attribute 'status_code'`。测试二:`asend` 一个带 `WWW-Authenticate: Bearer resource_metadata=...` 的 401,断言桥把它送进 SDK 的 401 分支并 yield 出**下一个请求**(元数据发现 GET),`assert isinstance(next_request, httpx.Request)`。docstring 同时解释了 CI 盲区:既有集成测试全部止步于 `_initialize()` 和盘监视,没人驱动过 `.asend()`,所以"每个 OAuth server 第一个响应就炸"的回归静默过关(`tests/tools/test_mcp_oauth_bidirectional.py:20-27 @ 863e313`)。

---

## 8. 台账更新

本轮三文件在 `data/ledger.tsv` 中由 `R3-structure` 升为 L1 精读(建议 status `R6-deep-read`);引用到的 `mcp_tool.py` 相关行、`web_server.py` OAuth 段、`mcp_config.py` login 段维持原层不变。7 个测试文件归 LT 层(行为规格参照)。docs 冲突两处(▲1 auto-bump/提示语、▲2 SSE OAuth)待并入当轮报告的文档-代码冲突清单。