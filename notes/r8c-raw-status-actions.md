# R8C 底稿 · `hermes_cli/web_server.py` 2725–6250 —— Git ops / 网关拓扑 / Curator / Portal / Diagnostics / Status 动作

> 基线:`863e31318553cda8ad61df681d08175364d4164b`(下称 `863e313`)。
> 溯源约定:凡对 hermes-agent 行为的断言,**锚点单独成行**(`路径:行号 @ 863e313`)紧接代码原文块;
> 非源码块(shell 输出 / 我做的表 / 推演)一律用 ```` ```text ```` / ```` ```console ```` / ```` ```verify ```` 声明。
> 记号:▲ 文档与代码矛盾;◇ 代码有文档无;■ 代码缺陷(必须给失效链);◎ 文档成立但保守。

本轮范围是 `hermes_cli/web_server.py` 的 2725–6250 行,连带三处"同一件事的另外两块":
`hermes_cli/web_git.py`(713 行)、`hermes_cli/web_routers/git.py`(138 行);以及本段挂载的
`sessions` / `profiles` 两个路由模块。基线只读,全程未在 `/home/user/hermes-agent` 下执行任何写盘命令,
临时脚本写在 `/tmp`;收工复核见 §10。

---

## 1. 本段的地图

### 1.1 行号区间 → 职责

这一段名义上被 6 条段落横幅切开,但**横幅与真实内容并不一一对应**(见 §1.3 ◇-A)。
下表是我按 `@app.` 路由与 `def` 边界重排后的真实分块(行号区间为闭区间):

```text
区间            块名                         对外形态                              性质
------------------------------------------------------------------------------------------------
2725-2773      Git ops 装配                 挂载 19 条 /api/git/* 路由            胶水 + 兜底
2774-2811      (38 行空白)                   —                                    重构残留
2812-2882      端口表 + _profile_platform_ports  无路由(被 2884 调用)             纯函数
2884-2941      _collect_profile_gateway_topology 无路由(被 /api/status 调用)      文件系统 + 进程表扫描
2944-2983      拓扑 TTL 缓存                 无路由                                并发保护
2986-2997      _load_configured_gateway_platforms 无路由                          阻塞调用搬离事件循环
3000-3006      /api/ssh/ownership           GET                                   只读
3008-3016      /api/health                  GET(公开)                            只读,极轻
3018-3352      /api/status                  GET(公开)                            只读,本段最重的读
3355-3476      /api/system/stats            GET                                   只读(psutil)
3479-3525      Curator                      GET / PUT / POST                      读 + 写状态 + 起子进程
3527-3585      Learning graph / node        GET / DELETE / PUT                    读 + 改技能与记忆
3588-3633      Portal                       GET                                   读(但会走网络,见 §6.1)
3636-3703      Diagnostics                  4 × POST                              3 个起子进程 + 1 个同步外传
3706-3993      动作基础设施 + 网关动作        —                                    子进程台账 + 日志尾巴
3995-4082      /api/gateway/restart /drain  POST                                  改本机状态
4085-4301      /api/hermes/update(+check)   POST / GET                            **改本机文件**
4304-4766      Audio(STT / TTS / TTS-WS)    POST ×3 + WebSocket                   外部 API + 流式
4769-4805      /api/actions/{name}/status   GET                                   读日志尾巴
4808-4848      会话/档案路由挂载             挂载 4 条路由                          胶水
4850-6244      Provider 字段 + 记忆后端       ~10 条 /api/memory /api/config 路由    读写凭据与配置
```

**注意**:`data/ledger.tsv` 与任务书都把 3708 起称作"Gateway + update actions",但那条横幅
实际统辖到 6247 行(下一条横幅处),中间夹着 audio、动作状态、会话路由、provider/记忆后端四大块。
"最大的一块"名副其实,但它不是**一件事**。

### 1.2 逐块「为什么需要」

**Git ops(2725)——为什么 harness 要自己实现 git。**
Hermes 的桌面端(Electron)本来在**用户本机**直接调 git:coding rail 的分支徽标、worktree 泳道、
Codex 式 review 面板、切分支,全是本地 git。一旦用户把桌面端连到**远程 gateway**,那些本地 git
调用就打在了错误的文件系统上——你在看自己笔记本的 diff,而 agent 在改服务器上的代码。
所以后端必须把同一套 git 能力镜像成 REST。

`hermes_cli/web_server.py:2726-2731 @ 863e313`

```python
# Git ops — the remote half of the desktop coding rail + review pane.
#
# The desktop runs these as Electron-local git on the user's machine; over a
# remote gateway that's the wrong filesystem, so we mirror them here (same auth
# gate + path hardening as /api/fs). Logic lives in ``hermes_cli.web_git``;
# these are thin, executor-offloaded wrappers (git/gh can block).
```

**端口表 + 拓扑(2812 / 2884)——为什么 Status 页要知道"谁在服务谁"。**
Hermes 支持多档(profile):`default`、`coder`、`work`…… 每档一个 `HERMES_HOME`。网关既可以
一个进程多路复用多档(`gateway.multiplex_profiles`),也可以每档各起一个进程。用户在 Status 页
要回答的问题是"我这台机器上到底跑着几个网关、它们各服务哪些档、各自占了哪些端口"。这个问题
没有任何单一数据源能答——必须枚举 profile 目录 + 探进程表 + 读每档的 `gateway_state.json`。

**Curator(3481)——为什么后台要有人打扫技能。**
agent 会自己创建技能(skill)。创建容易,淘汰难:长期不用的技能仍然占 prompt 预算。Curator 是
一个**辅助模型任务**,空闲时被触发,把陈旧技能标 stale、更久不用的归档(从不删除),并可以合并
重叠技能。Dashboard 需要暴露它的状态与"暂停 / 立刻跑一次"。

**Portal(3590)——为什么要一个只读的 Nous 面板。**
Hermes 可以挂在 Nous Portal 下面用托管推理与托管工具(Tool Gateway)。用户要看的是"我登没登录、
订阅覆盖了哪些能力、当前哪些能力走 Portal 哪些走自配 provider"。

**Diagnostics(3638)——为什么要有一键取证。**
用户报 bug 时最贵的往往不是修,而是**问出足够的现场**。这四个端点把"跑 `hermes dump`""打日志尾巴"
"把它们传成可分享链接""迁移旧 config"做成按钮。

**Gateway + update actions(3708)——为什么按钮要变成脱离的子进程。**
`hermes gateway restart` 和 `hermes update` 都是分钟级的长动作,且 `update` 会**替换正在运行的
代码**。HTTP 请求不能等它;更不能让它跟着请求一起被取消。所以设计是:起一个 detached 子进程,
stdout/stderr 重定向到 `~/.hermes/logs/<action>.log`,请求立刻返回 pid,前端再用
`/api/actions/<name>/status` 轮询日志尾巴。

### 1.3 本段的结构性观察

**◇-A:段落横幅与真实内容脱节。** 3706 那条横幅自称 "Gateway + update actions",其正文只解释了
两条命令(restart / update)的子进程约定,却统辖了 2533 行、覆盖 audio、action-status、会话路由、
provider/记忆后端四个完全无关的簇。读横幅会严重低估这一区。

**◇-B:2774–2811 是 38 行连续空白**,是 git 路由被抽到 `web_routers/git.py` 后留下的疤。
全文件共 14 处 ≥6 行的连续空白,这是最长的一处:

```verify
$ python3 - <<'EOF'   # 在 /tmp 下跑,只读基线
runs of >=6 blank lines: 14
(2774, 2811, 38)   ← 本段
(13531, 13556, 26)
(11333, 11346, 14)
... 另 11 处
EOF
```

意义:凡是看到这种疤,基本就能推断"这里刚做过 extract-module 重构",而重构留下的**兼容再导出**
(§2.1)是理解本段接口面的关键。

---

## 2. Git ops 三块怎么分工(必答 2)

### 2.0 一次具体请求的走法

用户在远程 dashboard 的 review 面板点了某个文件的 "revert"。浏览器发出:

```text
POST /api/git/review/revert
X-Hermes-Session-Token: <ephemeral>
{"path": "/srv/work/myrepo", "file": "src/a.py"}
```

它依次经过:token/cookie 认证中间件 → `web_routers/git.py` 的 `git_revert_route` →
`late("_git_path")` 回到 `web_server._git_path` 把 `path` 规范化 → `late("_git_op")` 把
`web_git.review_revert` 丢进线程池 → `web_git` 里 `subprocess.run(["git", ...])` 真正落地。
三块各管一段,下面逐块拆。

### 2.1 三块的职责边界

```text
块                              管什么                                     不管什么
--------------------------------------------------------------------------------------------
web_routers/git.py (138 行)     HTTP 形状:19 条路由的 URL、查询参数、       不含任何 git 逻辑;
                                Pydantic body 模型、返回值包装              不含认证;不含路径处理
web_server.py:2737-2747         两个跨切面动作:①把阻塞调用搬离事件循环     不知道具体是哪条 git 命令
                                ②把变更失败映射成 400;③路径规范化
web_git.py (713 行)             全部 git/gh 语义:porcelain v2 解析、       不知道 HTTP、不知道认证、
                                diff/numstat、worktree、ship flow           不做路径校验(注释明写"调用方传入已加固的 cwd")
```

`hermes_cli/web_git.py:8-10 @ 863e313`

```python
Everything shells out to the system ``git`` (and ``gh`` for ship info / PRs).
Reads degrade to ``None`` / empty on a non-repo; mutations raise so the renderer
can surface a toast. Callers pass an already path-hardened ``cwd``.
```

这条 docstring 是三块契约的书面版:**读操作降级、写操作抛异常、路径由调用方负责**。
"读降级 / 写抛" 落到代码就是两个不同的 helper:

`hermes_cli/web_git.py:58-68 @ 863e313`

```python
def _git_out(cwd: str, args: list[str]) -> str:
    """stdout of a git command, or "" on any failure."""
    code, out, _ = _git(cwd, args)
    return out if code == 0 else ""


def _git_ok(cwd: str, args: list[str]) -> None:
    """Run a git mutation, raising RuntimeError with stderr on failure."""
    code, _, err = _git(cwd, args)
    if code != 0:
        raise RuntimeError(err.strip() or f"git {' '.join(args)} failed")
```

——`_git_ok` 抛的正是 `RuntimeError`,而 `_git_op` 只捕 `RuntimeError`。这不是巧合,是**跨模块
的约定型异常**:`web_git` 用 `RuntimeError` 表示"这是一次用户可见的 git 失败",`web_server`
把它翻成 400。任何别的异常(比如 `_fs_path` 抛的 `HTTPException`、或者真正的编程错误)都不会
被这层吞掉。

### 2.2 路由层:一层薄到几乎透明的转发

`hermes_cli/web_routers/git.py:32-34 @ 863e313`

```python
@router.get("/api/git/status")
async def git_status_route(path: str):
    return await _git_op(_web_git.repo_status, _git_path(path))
```

19 条路由几乎都是这一行的变体。它们**不写 `_require_token`**——认证由全局中间件负责(§2.5)。

路由模块拿不到 `_git_op` / `_git_path` 的直接引用,因为 `web_server` 反过来 import 它(循环):

`hermes_cli/web_routers/git.py:26-29 @ 863e313`

```python
# Late-bound web_server helpers (resolved at call time; cycle-safe,
# monkeypatch-transparent).
_git_op = late("_git_op")
_git_path = late("_git_path")
```

`late()` 返回的代理**每次调用**才去 `sys.modules` 取属性:

`hermes_cli/web_deps.py:46-51 @ 863e313`

```python
    def _proxy(*args: Any, **kwargs: Any):
        return getattr(_server(), name)(*args, **kwargs)

    _proxy.__name__ = name
    _proxy.__qualname__ = name
    return _proxy
```

这解决了两个问题:循环导入,以及**测试的 monkeypatch 接缝**——全仓大量测试写
`monkeypatch.setattr(web_server, "_helper", ...)`,如果路由模块在 import 期把函数对象绑死,
这些补丁就全部失效。同一动机也解释了 2753 那段"遗留再导出":

`hermes_cli/web_server.py:2753-2757 @ 863e313`

```python
from hermes_cli.web_routers.git import (  # noqa: E402,F401 — legacy re-exports; tests call these via web_server.<name>
    git_status_route,
    git_worktrees_route,
    git_branches_route,
    git_base_branches_route,
```

**可迁移的设计原则**:当你把一个 god-module 切成路由模块时,**状态留在原地、只搬形状**,
再用一层 late-binding 代理跨过循环。这比"把 helper 也搬走"便宜得多,因为 helper 的调用方
(尤其是测试)往往比路由本身多一个数量级。

### 2.3 为什么 git 操作要包一层 `_git_op`

`hermes_cli/web_server.py:2737-2743 @ 863e313`

```python
async def _git_op(fn, *args):
    """Run a (blocking) git op off the event loop; map a failed mutation to 400."""
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, fn, *args)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "git operation failed")
```

**问题演出来**:FastAPI/Starlette 的 `async def` 处理器跑在**单条事件循环线程**上。
`web_git` 里每次 git 调用都是 `subprocess.run(...)` —— 同步阻塞,超时上限 30 秒:

`hermes_cli/web_git.py:24-26 @ 863e313`

```python
_GIT_TIMEOUT = 30
_GH_TIMEOUT = 30
_MAX_BUFFER = 32 * 1024 * 1024
```

如果直接在 `async def` 里调,一次 `git fetch origin <branch>`(`worktree_add` 会做,见 §2.6)
在网络卡住时能把**整个 dashboard 的事件循环钉死 30 秒**:所有 WebSocket 心跳、`/api/status`
轮询、chat 流式输出全部停摆。`run_in_executor(None, ...)` 把它丢进默认线程池,循环立刻让出。

第二个职责是**异常翻译**。`web_git` 的写操作抛 `RuntimeError`(§2.1),不翻译的话 FastAPI
会当成未处理异常返回 500,前端只能弹"服务器错误";翻成 400 + `str(exc)` 之后,前端 toast
里显示的是 git 自己的 stderr(例如 `error: pathspec 'foo' did not match any file(s)`)。
**这是一次典型的"把下游的错误信息保真地送到用户眼前"设计**,代价是把 git 的 stderr 直接
回显给了调用方(认证后可见,不是对外泄露面)。

**取舍:默认线程池是有限的。** `run_in_executor(None, ...)` 用的是解释器默认 `ThreadPoolExecutor`,
且这个池被本文件里**很多别的东西**共用(拓扑扫描 §3.3、`_load_configured_gateway_platforms`、
`_probe_state_db` 等)。一批并发的 git 请求会挤占同一个池。文件里已经因为这个池被挤爆吃过一次
事故(§3.3 的 GIL 风暴),但 git 这条路径没有额外限流。

### 2.4 `_git_path` 到底做了什么(路径参数怎么防越界)

这是本段**最需要说清楚的一点**,因为它和直觉相反。

`hermes_cli/web_server.py:2746-2747 @ 863e313`

```python
def _git_path(path: str) -> str:
    return str(_fs_path(path))
```

它只是 `_fs_path` 的字符串化。而 `_fs_path` 是:

`hermes_cli/web_server.py:1906-1923 @ 863e313`

```python
def _fs_path(raw_path: str) -> Path:
    raw = str(raw_path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Path is required")
    if "\0" in raw:
        raise HTTPException(status_code=400, detail="Invalid path")
    try:
        if raw.lower().startswith("file:"):
            parsed = urllib.parse.urlparse(raw)
            if parsed.netloc and parsed.netloc not in {"", "localhost"}:
                raise ValueError
            raw = urllib.request.url2pathname(parsed.path)
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        return candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid path")
```

逐条看它**做了什么**:
1. 空路径 → 400;
2. 含 NUL 字节 → 400(挡住 `path\0.txt` 这类截断把戏);
3. `file:` URL 允许,但 netloc 只接受空或 `localhost`(挡住 `file://evil.example/…`);
4. `~` 展开;
5. 相对路径按**服务进程的 cwd** 拼成绝对;
6. `resolve(strict=False)` —— 展开 `..` 与符号链接,不要求存在。

它**没有做**的事:**没有任何 root 白名单 / 前缀约束**。`..` 被 `resolve()` 消解成一个真实
绝对路径,然后原样放行。实测(脚本在 `/tmp`,只读调用):

```console
$ /home/user/hermes-venv/bin/python /tmp/r8c_fspath_probe.py
'/etc' -> /etc
'/etc/passwd' -> /etc/passwd
'~' -> /root
'../../etc' -> /home/etc
'file:///etc/hostname' -> /etc/hostname
```

所以准确的说法是:**`_fs_path` 是"路径规范化 + 三条畸形输入拒绝",不是沙箱。**
横幅那句 "same auth gate + path hardening as /api/fs"(2729-2730)**字面完全成立**——它确实
和 `/api/fs` 完全一样;但 "path hardening" 这个词会让读者以为存在越界防护,实际上防护等级是
"认证即全盘"。

**◇-C:同一个 dashboard 里存在两套语义不同的路径面,只有一套有牢笼。**
`/api/files`(managed files)有 `locked_root`,在托管布局下会 403:

`hermes_cli/web_server.py:2207-2208 @ 863e313`

```python
    if root is not None and not _path_is_under(root, resolved):
        raise HTTPException(status_code=403, detail="Path outside managed files root")
```

`hermes_cli/web_server.py:2167-2169 @ 863e313`

```python
    if _default_hermes_root_is_opt_data():
        root = _ensure_managed_root(_HOSTED_MANAGED_FILES_ROOT) if create_root else _HOSTED_MANAGED_FILES_ROOT
        return ManagedFilesPolicy(default_path=root, locked_root=root, can_change_path=False)
```

而 `/api/fs/*` 与 `/api/git/*` 走 `_fs_path`,**在同一部署下不受这个 root 约束**。

**为什么这不是 ■(我查证过的判断)**:如果 `locked_root` 是安全边界,那 `/api/git/*` 就是绕过它
的后门。但同一个认证会话**本来就能开 shell**——`/api/pty` 是无条件开启的:

`hermes_cli/web_server.py:349-355 @ 863e313`

```python
# In-browser Chat tab (/chat, /api/pty, /api/ws, …).  Always enabled: the
# desktop app and the dashboard's own Chat tab both drive the agent over the
# `/api/ws` + `/api/pty` WebSockets, so the embedded-chat surface is an
# unconditional part of the dashboard.  Kept as a module-level constant (rather
# than inlining ``True`` at every gate) so the WS endpoints and the SPA token
# injection share a single, testable seam.
_DASHBOARD_EMBEDDED_CHAT_ENABLED = True
```

有 PTY 就有整台主机。所以 `locked_root` 是**产品/UX 边界**("Files 页从这里开始浏览"),不是
安全边界,`/api/git/*` 不受约束与威胁模型一致。**但把这条写进底稿是必要的**:下一个读
`locked_root` 的人极可能把它误当沙箱。

### 2.5 认证在哪一层

git 路由自己不写 `_require_token`,靠全局中间件按路径前缀兜:

`hermes_cli/web_server.py:663-670 @ 863e313`

```python
    path = request.url.path
    is_mcp_oauth_callback = path.startswith("/api/mcp/oauth/callback/")
    if path.startswith("/api/") and path not in _PUBLIC_API_PATHS and not is_mcp_oauth_callback:
        if not _has_valid_session_token(request) and not _has_valid_query_token(request, path):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized"},
            )
```

`/api/git/*` 不在 `PUBLIC_API_PATHS` 里(那份清单只有 7 条,见 `hermes_cli/dashboard_auth/public_paths.py:33-60`),
所以默认 401。测试把这条钉成了行为规格:

`tests/hermes_cli/test_web_server_git.py:101-105 @ 863e313`

```python
def test_git_endpoints_require_auth(repo):
    unauth = TestClient(web_server.app)

    assert unauth.get("/api/git/status", params={"path": str(repo)}).status_code == 401
    assert unauth.post("/api/git/review/stage", json={"path": str(repo)}).status_code == 401
```

**设计要点**:认证做成 `startswith("/api/")` 的**默认拒绝 + 显式白名单**,而不是每条路由自己加
装饰器。这样"新加一条路由忘了加认证"这个最常见的漏洞类型在结构上就不成立——新路由默认是被保护的。
白名单文件自己的 docstring 把"能进白名单"的判据写死成三条自检(能否给外部探活探针 / 未登录 SPA /
任意 curl 看),这是我在本段见到的最值得抄的一条工程约定。

### 2.6 `web_git.py` 里三个值得单独记的设计

**(a) 非交互契约。** 这些 git/gh 调用服务的是 REST 请求,**没有人能回答凭据提示**:

`hermes_cli/web_git.py:38-42 @ 863e313`

```python
    Runs non-interactively (stdin nulled, ``GIT_TERMINAL_PROMPT=0``): these
    calls serve authenticated REST requests from the dashboard/desktop, so a
    credential prompt from ``fetch``/``push``/``pull`` could never be answered
    — it would just hang the request until the timeout. Failing fast surfaces
    the real auth error in the toast instead.
```

`gh` 那侧用它自己的开关:

`hermes_cli/web_git.py:435-436 @ 863e313`

```python
    env = noninteractive_git_env()
    env["GH_PROMPT_DISABLED"] = "1"
```

**这是"子进程边界上必须掐掉交互"的教科书案例**:凡是把 CLI 工具包成服务,交互提示都会退化成
"挂到超时",而超时的表征(30 秒后 500)和真正的网络故障无法区分。掐掉之后,失败立刻带着
真实原因回来。

**(b) 一次 status 喂三个消费者。** porcelain v2 的 `-z` 输出只解析一遍,一个生成器同时供
coding rail、review 列表、commit 流程用:

`hermes_cli/web_git.py:166-169 @ 863e313`

```python
def _walk_entries(raw: str):
    """Yield (tag, xy, path) per changed file from ``git status --porcelain=v2 -z``,
    skipping branch headers and the rename/copy origin-path records. One walker
    feeds the rail, the review list, and the commit flow."""
```

其中 rename/copy(tag `2`)记录后面**紧跟一条 origin-path 记录**,必须多吞一格,否则路径全错位:

`hermes_cli/web_git.py:179-183 @ 863e313`

```python
        elif tag in ("1", "2"):
            xy = rec.split(" ")[1]
            path = rec.split(" ", 8)[-1] if tag == "1" else rec.split(" ", 9)[-1]
            if tag == "2":
                i += 1  # rename/copy: the origin path is the next NUL record
            yield tag, xy, resolve_rename_path(path)
```

**(c) 新文件的 +N 要自己数。** `git diff HEAD` 忽略 untracked,所以"这一轮只新建了文件"的
会话会显示 +0。它自己补了一次有上限的扫描:

`hermes_cli/web_git.py:240-246 @ 863e313`

```python
    # +/- vs HEAD (tracked), then fold in untracked insertions — `git diff HEAD`
    # ignores them, so a new-file-only turn would otherwise read +0 (bounded scan).
    added = removed = 0
    for a, r in _numstat(cwd, ["HEAD"]).values():
        added += a
        removed += r
    added += sum(_untracked_insertions(cwd, f["path"]) for f in files[:_UNTRACKED_SCAN_CAP] if f["untracked"])
```

**(d) 写操作会改任意目录(与 §2.4 合起来看)。** `worktree_add` 在一个还不是 repo 的目录里
会 `git init` 并造一个空根提交:

`hermes_cli/web_git.py:559-561 @ 863e313`

```python
def _ensure_repo(cwd: str) -> None:
    """A new project folder may not be a repo (or has no commit to branch from);
    init it with a root commit so worktrees just work. No-op for a committed repo."""
```

这条被测试当规格钉住了(注意它断言"已有文件不会被悄悄提交"):

`tests/hermes_cli/test_web_server_git.py:83-96 @ 863e313`

```python
    added = client.post(
        "/api/git/worktree/add", json={"path": str(folder), "branch": "feature/plain"}
    ).json()

    assert added["branch"] == "feature/plain"
    assert Path(added["path"]).is_dir()
    assert (folder / ".git").exists()
    _git(folder, "rev-parse", "--verify", "HEAD")

    status = client.get("/api/git/status", params={"path": str(folder)}).json()
    assert status["branch"] == status["defaultBranch"]
    assert status["branch"]
    # Existing files are not silently committed by repo initialization.
    assert any(file["path"] == "notes.txt" and file["untracked"] for file in status["files"])
```

而 `review_revert` 是**破坏性**的,且它刻意不用 `_git_ok`(失败静默):

`hermes_cli/web_git.py:361-366 @ 863e313`

```python
def review_revert(cwd: str, file_path: str | None) -> dict:
    """Discard changes back to the committed state (restore tracked, remove untracked)."""
    target = ["--", file_path] if file_path else ["--", "."]
    _git(cwd, ["checkout", "HEAD", *target])
    _git(cwd, ["clean", "-fd", *target])
    return {"ok": True}
```

`file_path` 为空时 target 是 `.`,即"整个工作树回滚 + `clean -fd`"。结合 §2.4 的无 root 约束:
一个已认证会话可以对主机上**任意一个 git 仓库**发起全树回滚。同 §2.4 的结论——在"有 PTY 就有
主机"的威胁模型下这不构成越权,但它是本段破坏力最大的单个操作,值得在成品章里点名。

---

## 3. `_collect_profile_gateway_topology`(必答 3)

### 3.1 "拓扑"是什么

返回三个字段,`/api/status` 直接铺进响应:

`hermes_cli/web_server.py:2887-2899 @ 863e313`

```python
    Returns ``{"profiles": [...], "gateway_mode": ..., "gateways": [...]}``:

    * ``profiles`` — every profile on the host (default + named), from
      ``profiles_to_serve(True)`` (the cheap enumeration chokepoint — no
      per-profile config reads or skill counts).
    * ``gateways`` — one entry per profile with a LIVE gateway process:
      ``{"profile", "ports", "served_profiles"?}``.  Liveness reuses
      ``_check_gateway_running`` so this agrees with the profiles sidebar.
    * ``gateway_mode`` — ``"multiplex"`` when the default gateway serves
      multiple profiles (gateway.multiplex_profiles), ``"single"`` for one
      live gateway, ``"multiple"`` for independent per-profile gateways,
      ``"none"`` when nothing is running.
```

四态判定是一条纯粹的 if 阶梯,`multiplex` 由 `default` 档的 `served_profiles` 长度决定:

`hermes_cli/web_server.py:2921-2930 @ 863e313`

```python
        served = [str(p) for p in ((runtime or {}).get("served_profiles") or [])]
        if name == "default" and len(served) > 1:
            multiplex = True
        entry: Dict[str, Any] = {
            "profile": name,
            "ports": _profile_platform_ports(home, runtime),
        }
        if served:
            entry["served_profiles"] = served
        gateways.append(entry)
```

`hermes_cli/web_server.py:2932-2941 @ 863e313`

```python
    if multiplex:
        mode = "multiplex"
    elif len(gateways) > 1:
        mode = "multiple"
    elif len(gateways) == 1:
        mode = "single"
    else:
        mode = "none"

    return {"profiles": profile_names, "gateway_mode": mode, "gateways": gateways}
```

**整段函数是"绝不抛"的**:枚举失败返回 `gateway_mode: "unknown"`,单档探活失败就 `continue`。

`hermes_cli/web_server.py:2900-2906 @ 863e313`

```python
    try:
        from hermes_cli.profiles import _check_gateway_running, profiles_to_serve
        from gateway.status import read_runtime_status
        homes = profiles_to_serve(True)
    except Exception:
        _log.debug("profile/gateway topology enumeration failed", exc_info=True)
        return {"profiles": [], "gateway_mode": "unknown", "gateways": []}
```

这条被测试钉住:

`tests/hermes_cli/test_web_server_gateway_topology.py:90-92 @ 863e313`

```python
        monkeypatch.setattr(profiles_mod, "profiles_to_serve", _boom)
        topo = _collect_profile_gateway_topology()
        assert topo == {"profiles": [], "gateway_mode": "unknown", "gateways": []}
```

**设计原则**:`/api/status` 是**公开探活端点**,任何一个"顺带展示"的子系统都不许让它 500。
这里的写法是"每个子块各自 try/except + 明确的降级值",而不是在最外层包一个大 try。
降级值本身带语义(`"unknown"` ≠ `"none"`),下游能区分"没跑"和"没测出来"。

### 3.2 端口怎么分配

端口**不是分配出来的,是解析出来的**——它是"这些适配器现在监听在哪"的最佳猜测。
先有一张静态表,把每个会绑端口的平台映射到 `(配置键, 适配器默认端口)`:

`hermes_cli/web_server.py:2812-2827 @ 863e313`

```python
# Host TCP ports each port-binding gateway platform listens on, as
# ``platform-name -> (config port key, adapter default)``.  Mirrors
# ``PORT_BINDING_PLATFORM_VALUES`` in gateway/config.py and each adapter's
# DEFAULT_PORT / DEFAULT_WEBHOOK_PORT constant.  Used only for the dashboard's
# gateway-topology readout — best-effort display data, not a bind source.
_PORT_BINDING_PLATFORM_PORTS: Dict[str, Tuple[str, int]] = {
    "webhook": ("port", 8644),
    "api_server": ("port", 8642),
    "msgraph_webhook": ("port", 8646),
    "feishu": ("webhook_port", 8765),
    "wecom_callback": ("port", 8645),
    "bluebubbles": ("webhook_port", 8645),
    "sms": ("webhook_port", 8080),
    "whatsapp_cloud": ("port", 8090),
    "line": ("port", 8646),
}
```

（注:上面这一段是逐字原文;表里 `whatsapp_cloud` 的键在基线中是 `webhook_port`,见下方 §9-Q4。）

然后只对"运行时报告为活着"的平台解析端口——死态被显式排除:

`hermes_cli/web_server.py:2829-2830 @ 863e313`

```python
# Platform states that mean the adapter is NOT serving its port right now.
_PLATFORM_DEAD_STATES = frozenset({"fatal", "disconnected", "stopped"})
```

配置读取走**被探测那一档自己的 `config.yaml`**,而不是当前进程的 `load_config()`:

`hermes_cli/web_server.py:2854-2858 @ 863e313`

```python
    try:
        # Multi-profile probe: load_config() targets the ACTIVE profile's
        # home, so read the probed profile's file via the raw primitive.
        from hermes_cli.config import read_user_config_raw
        cfg = read_user_config_raw(profile_home / "config.yaml")
```

**这是多档系统里最容易写错的一处**:`load_config()` 是有隐式上下文的(当前 profile),
在"遍历所有 profile"的循环里调它会让每一档都读到同一份配置。这里改用无上下文的原语。

优先级复刻网关自己的合并顺序(后写者胜 → 顶层 `platforms:` 覆盖 `gateway.platforms:`):

`hermes_cli/web_server.py:2860-2867 @ 863e313`

```python
        # gateway.platforms first, top-level platforms second — later wins,
        # matching the precedence in gateway.config.load_gateway_config().
        for src in ((gateway_cfg or {}).get("platforms"), cfg.get("platforms")):
            if not isinstance(src, dict):
                continue
            for plat_name, plat_block in src.items():
                if isinstance(plat_block, dict):
                    blocks.setdefault(plat_name, {}).update(plat_block)
```

我核对了被复刻的那一侧,顺序一致(先合 nested、后合 top-level):

`gateway/config.py:1449-1450 @ 863e313`

```python
            _merge_platform_map(gateway_platforms)
            _merge_platform_map(yaml_cfg.get("platforms"))
```

这条优先级也被测试钉住:

`tests/hermes_cli/test_web_server_gateway_topology.py:27-34 @ 863e313`

```python
    def test_top_level_platforms_wins_over_gateway_block(self, tmp_path):
        (tmp_path / "config.yaml").write_text(
            "gateway:\n  platforms:\n    webhook:\n      port: 1111\n"
            "platforms:\n  webhook:\n    port: 2222\n",
            encoding="utf-8",
        )
        runtime = {"platforms": {"webhook": {"state": "connected"}}}
        assert _profile_platform_ports(tmp_path, runtime) == {"webhook": 2222}
```

最后取值时还兼容 `extra:` 嵌套,并对非法值兜底回默认:

`hermes_cli/web_server.py:2871-2881 @ 863e313`

```python
    ports: Dict[str, int] = {}
    for name in active:
        port_key, default_port = _PORT_BINDING_PLATFORM_PORTS[name]
        block = blocks.get(name) or {}
        extra = block.get("extra") if isinstance(block.get("extra"), dict) else {}
        raw = block.get(port_key, (extra or {}).get(port_key, default_port))
        try:
            ports[name] = int(raw)
        except (TypeError, ValueError):
            ports[name] = default_port
    return ports
```

**◎-A:函数自己声明了它解析不到的一层。** env 覆盖(如那一档 `.env` 里的 `WEBHOOK_PORT`)
不解析,docstring 明写:

`hermes_cli/web_server.py:2840-2842 @ 863e313`

```python
    falling back to the adapter default.  Display-only: env-var port overrides
    (e.g. ``WEBHOOK_PORT`` in that profile's .env) are not resolved here.
    """
```

这是一个**诚实的保守声明**:显示层不追求与绑定层严格一致,并把"我可能是错的"写进契约
(横幅同样写了 "best-effort display data, not a bind source")。比起硬凑一致,这更省。

### 3.3 有没有缓存:有,而且它是一次事故的产物

**故事**:桌面端在等后端起来时,会以约 1 次/秒轮询 `/api/status`。没有缓存时,每次轮询都跑一遍
完整拓扑扫描——每档一次 `yaml.safe_load`(纯 Python loader)+ psutil 进程表探测 + realpath 遍历,
而且全都丢进**默认线程池**。多档安装上并发的扫描互相叠加,**握着 GIL 14–16 秒**,事件循环饿死;
桌面端等的 `gateway.ready` WebSocket 消息永远不来,启动升级成 "Hermes couldn't start" 弹层。

`hermes_cli/web_server.py:2944-2954 @ 863e313`

```python
# /api/status is polled ~1/s by the desktop app while it waits for the backend
# (and again by the dashboard badge). Each uncached call above walks 7+ profile
# homes (yaml.safe_load with the pure-Python loader + psutil process-table
# probes + realpath walks) inside the default executor; concurrent polls pile
# up and hold the GIL for 14-16s, starving the event loop — the desktop WS
# never receives gateway.ready and boot fails ("event loop stalled ... GIL
# pressure suspected"). Topology changes on gateway start/stop, so a short TTL
# cache with a collapse lock keeps the scan to one per window. The cache also
# remembers which collector produced the entry: tests monkeypatch
# _collect_profile_gateway_topology per case, and the identity check keeps
# them hermetic without needing a reset hook (a swapped collector is a miss).
```

（测试文件把同一因果又讲了一遍,并给出 issue 号 #60800:
`tests/test_web_server_status_topology_cache.py:3-9`。)

缓存本体三个字段 + 一把锁 + 10 秒 TTL:

`hermes_cli/web_server.py:2955-2957 @ 863e313`

```python
_TOPOLOGY_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None, "fn": None}
_TOPOLOGY_CACHE_LOCK = threading.Lock()
_TOPOLOGY_CACHE_TTL = 10.0
```

命中判定**同时比 TTL 与 collector 身份**:

`hermes_cli/web_server.py:2960-2967 @ 863e313`

```python
def _topology_cache_get(fn: Any) -> Optional[Dict[str, Any]]:
    if (
        _TOPOLOGY_CACHE["data"] is not None
        and _TOPOLOGY_CACHE["fn"] is fn
        and time.monotonic() - _TOPOLOGY_CACHE["ts"] < _TOPOLOGY_CACHE_TTL
    ):
        return _TOPOLOGY_CACHE["data"]
    return None
```

取数是**双检锁 + 请求合并**(double-checked locking):锁外先探一次(热路径无锁),没命中再拿锁、
锁内再探一次,只有真正的第一个线程执行扫描,其余 7 个在锁上排队然后直接吃缓存:

`hermes_cli/web_server.py:2970-2983 @ 863e313`

```python
def _collect_profile_gateway_topology_cached() -> Dict[str, Any]:
    fn = _collect_profile_gateway_topology
    cached = _topology_cache_get(fn)
    if cached is not None:
        return cached
    with _TOPOLOGY_CACHE_LOCK:
        cached = _topology_cache_get(fn)
        if cached is not None:
            return cached
        data = fn()
        _TOPOLOGY_CACHE["data"] = data
        _TOPOLOGY_CACHE["fn"] = fn
        _TOPOLOGY_CACHE["ts"] = time.monotonic()
        return data
```

注意 `fn = _collect_profile_gateway_topology` 是**调用时读模块全局**,不是闭包捕获——
这正是 monkeypatch 能生效、且身份检查能起作用的前提。

四条测试就是这个缓存的完整行为规格(TTL 内只扫一次 / 过期重扫 / 8 线程合并成 1 次 / 换 collector 必须 miss):

`tests/test_web_server_status_topology_cache.py:67-69 @ 863e313`

```python
def test_topology_cache_collapses_concurrent_scans(monkeypatch):
    """Concurrent status polls must not each run their own scan — that pile-up
    is exactly the GIL storm the cache exists to prevent."""
```

`tests/test_web_server_status_topology_cache.py:97-100 @ 863e313`

```python
def test_topology_cache_misses_when_collector_is_swapped(monkeypatch):
    """Tests (and hot-reload scenarios) monkeypatch the collector; a swapped
    function identity must be a cache miss so stale data from the previous
    collector never leaks across the swap."""
```

**"把测试隔离需求写进生产代码"值不值得?** 这里的 `fn` 身份检查纯粹是为了让测试免用 reset hook。
它有真实成本(多一个字段、多一个比较),但换来的是**任何 monkeypatch 都自动隔离**,不需要每个
测试记得清缓存——忘了清缓存是这类模块级缓存最经典的串扰源。我认为这笔交易划算,且它顺带对
热重载场景也正确。

### 3.4 拓扑在 `/api/status` 里怎么被切成两半

`hermes_cli/web_server.py:3322-3326 @ 863e313`

```python
        topology = await asyncio.get_running_loop().run_in_executor(
            None, _collect_profile_gateway_topology_cached
        )
        status["profiles"] = topology["profiles"]
        status["gateway_mode"] = topology["gateway_mode"]
```

`hermes_cli/web_server.py:3339-3347 @ 863e313`

```python
        if not auth_required:
            status.update({
                "hermes_home": str(get_hermes_home()),
                "config_path": str(get_config_path()),
                "env_path": str(get_env_path()),
                "gateway_pid": gateway_pid,
                "gateway_health_url": _GATEWAY_HEALTH_URL,
                "gateways": topology["gateways"],
            })
```

**按敏感度切分**:profile **名字**和 `gateway_mode` 是产品面(Nous Cloud Portal 隔着网络读
`/api/status` 渲染档位列表),必须穿过认证门;而 `gateways[]` 里含**主机端口**,属于部署侦察,
和绝对路径、PID 一起只在 loopback 暴露。这条切分被两条测试分别钉住(loopback 全给 / gated 只给名字):

`tests/hermes_cli/test_web_server_gateway_topology.py:151-157 @ 863e313`

```python
            assert data["profiles"] == ["default", "coder"]
            assert data["gateway_mode"] == "multiplex"
            # But the per-gateway detail (host ports = recon) stays gated,
            # alongside hermes_home / gateway_pid.
            assert "gateways" not in data
            assert "hermes_home" not in data
            assert "gateway_pid" not in data
```

**◇-D:同一响应里两个网关字段的新鲜度不同,窗口内可自相矛盾。**
`gateway_running` 走 `resolve_gateway_liveness` → `get_running_pid_cached`,那层缓存除了 TTL
还**比对 PID/lock/runtime-status 文件签名**,所以 start/stop 会被很快看见:

`gateway/status.py:2236-2238 @ 863e313`

```python
            cached_at, cached_signature, cached_pid = cached
            if now - cached_at <= ttl_seconds and cached_signature == signature:
                return cached_pid
```

而 `_TOPOLOGY_CACHE` 是**纯 10 秒 TTL,没有签名、也没有任何动作端点去主动失效它**——
`/api/gateway/start`(:12541)、`/stop`(:12553)、`/restart`(:3995)都不碰这个缓存。
失效链:点了 "Start gateway" → 网关起来 → 下一次 `/api/status` 里 `gateway_running: true`
(签名变了,立刻新鲜)但 `gateway_mode` 仍可能是 `"none"`、`gateways: []`(TTL 未到)。
最长约 10 秒的自相矛盾。搜索面:我在 `hermes_cli/web_server.py` 全文 grep `_TOPOLOGY_CACHE`,
只有 2955–2982 的定义与读写,**没有任何写端点引用它**;测试里的清理函数 `_reset_cache`
只存在于 `tests/test_web_server_status_topology_cache.py:18`。
严重度:低(纯展示、10 秒、自愈),但它是 §3.1 那条"降级值带语义"原则的一处漏网——
此刻的 `"none"` 并不真的意味着 none。**修法很便宜**:三个网关动作端点各加一行
`_TOPOLOGY_CACHE["data"] = None`。

---

## 4. Gateway + update actions(必答 4)

### 4.1 Status 页上的按钮 → 端点 → 动作名

```text
按钮(Status/System 页)   HTTP                                动作名 (name)      落地命令
--------------------------------------------------------------------------------------------------------
Start gateway            POST /api/gateway/start             gateway-start      hermes [-p X] gateway start
Stop gateway             POST /api/gateway/stop              gateway-stop       hermes [-p X] gateway stop
Restart gateway          POST /api/gateway/restart           gateway-restart    hermes [-p X] gateway restart
(NAS 驱动,非按钮)        POST /api/gateway/drain             —                  写 .drain_request.json 标记
Check for updates        GET  /api/hermes/update/check       —                  只读,不落子进程
Update Hermes            POST /api/hermes/update             hermes-update      hermes update
Run doctor               POST /api/ops/doctor                doctor             hermes doctor
Security audit           POST /api/ops/security-audit        security-audit     hermes security audit
Backup / Import          POST /api/ops/backup /import        backup / import    hermes backup / import
Prune checkpoints        POST /api/ops/checkpoints/prune     checkpoints-prune  hermes checkpoints prune
Prompt size              POST /api/ops/prompt-size           prompt-size        hermes prompt-size
Support dump             POST /api/ops/dump                  dump               hermes dump
Migrate config           POST /api/ops/config-migrate        config-migrate     hermes config migrate
Run curator now          POST /api/curator/run               curator-run        hermes curator run
Skills 安装/卸载/更新      POST /api/skills/hub/*              skills-*           hermes skills ...
Generate share link      POST /api/ops/debug-share           —                  **同步**,不落子进程
所有按钮的日志            GET  /api/actions/{name}/status     —                  尾读 ~/.hermes/logs/<name>.log
```

动作名 → 日志文件是一张写死的白名单(17 条),`/api/actions/{name}/status` 不在表里就 404
——URL 里的 `name` 永远不会拼进路径:

`hermes_cli/web_server.py:3721-3740 @ 863e313`

```python
# Short ``name`` (from the URL) → absolute log file path.
_ACTION_LOG_FILES: Dict[str, str] = {
    "gateway-restart": "gateway-restart.log",
    "gateway-start": "gateway-start.log",
    "gateway-stop": "gateway-stop.log",
    "hermes-update": "hermes-update.log",
    "doctor": "action-doctor.log",
    "security-audit": "action-security-audit.log",
    "backup": "action-backup.log",
    "import": "action-import.log",
    "checkpoints-prune": "action-checkpoints-prune.log",
    "skills-install": "action-skills-install.log",
    "skills-uninstall": "action-skills-uninstall.log",
    "skills-update": "action-skills-update.log",
    "curator-run": "action-curator-run.log",
    "prompt-size": "action-prompt-size.log",
    "dump": "action-dump.log",
    "config-migrate": "action-config-migrate.log",
    "tools-post-setup": "action-tools-post-setup.log",
}
```

`hermes_cli/web_server.py:4772-4774 @ 863e313`

```python
    log_file_name = _ACTION_LOG_FILES.get(name)
    if log_file_name is None:
        raise HTTPException(status_code=404, detail=f"Unknown action: {name}")
```

**设计要点**:这是"**枚举而非拼接**"防路径穿越的标准写法。URL 段只用来在字典里查,查不到就 404,
`name` 本身从不进入 `Path(...)`。比起写正则校验 `name`,这个做法**不可能有绕过**。

### 4.2 子进程怎么起(三条约定)

`hermes_cli/web_server.py:3784-3794 @ 863e313`

```python
def _spawn_hermes_action(
    subcommand: List[str],
    name: str,
    *,
    env_overrides: Optional[Dict[str, str]] = None,
) -> subprocess.Popen:
    """Spawn ``hermes <subcommand>`` detached and record the Popen handle.

    Uses the running interpreter's ``hermes_cli.main`` module so the action
    inherits the same venv/PYTHONPATH the web server is using.
    """
```

**(1) 用当前解释器 `-m hermes_cli.main`,而不是找 PATH 里的 `hermes`。**

`hermes_cli/web_server.py:3803 @ 863e313`

```python
    cmd = [_dashboard_spawn_executable(), "-m", "hermes_cli.main", *subcommand]
```

理由是**动作必须跑在和 web server 同一个 venv 里**。PATH 上的 `hermes` 可能是另一份安装
(pipx / 系统包 / 旧版本),那样 `hermes update` 就会去更新错的那份。

**(2) 必须摘掉 `_HERMES_GATEWAY` 环境变量。** dashboard 跑在 gateway 进程里,继承的环境带着
这个标记;子进程带着它跑 `gateway restart` 会撞上进程内的重启循环保护而 exit 1 —— 表现是
"点了重启,什么也没发生":

`hermes_cli/web_server.py:3805-3811 @ 863e313`

```python
    # The dashboard runs *inside* the gateway process, so os.environ carries
    # _HERMES_GATEWAY=1. Inheriting it makes a spawned `hermes gateway restart`
    # trip the in-process restart-loop guard and exit 1 — silently failing the
    # dashboard's auto-restart paths. The gateway's own restart watcher already
    # drops it (gateway/run.py); mirror that here (#52470).
    action_env = {**os.environ, "HERMES_NONINTERACTIVE": "1"}
    action_env.pop("_HERMES_GATEWAY", None)
```

**这是 §2.6(a) 同一条原则的第二次出现**:跨进程边界时,**环境继承是默认的、通常是错的**。
这里同时正向加了 `HERMES_NONINTERACTIVE=1`(告诉 CLI 别问问题)、负向删了一个标记。

**(3) stdin 关死 + 会话脱离 + 日志重定向。**

`hermes_cli/web_server.py:3813-3823 @ 863e313`

```python
    popen_kwargs: Dict[str, Any] = {
        "cwd": str(PROJECT_ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
        "env": {**action_env, **(env_overrides or {})},
    }
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = windows_detach_flags()
    else:
        popen_kwargs["start_new_session"] = True
```

`stdin=DEVNULL` 的理由横幅写得很清楚:任何漏网的 `input()` 会立刻拿到 EOF 而不是永久挂起
(3710-3711)。`start_new_session=True` 让子进程脱离进程组——否则 `hermes update` 重启 gateway
时会连同自己一起被信号带走。

再加一个易漏的细节:父进程的日志 fd 必须立刻关,否则每起一个动作漏一个 fd:

`hermes_cli/web_server.py:3826-3829 @ 863e313`

```python
    # The child inherits its own duplicated fd for stdout/stderr, so the
    # parent's handle can be released immediately — otherwise we leak one
    # fd per spawned action.
    log_file.close()
```

### 4.3 幂等:双击重启按钮会怎样

`hermes_cli/web_server.py:3963-3970 @ 863e313`

```python
    subcommand = _gateway_subcommand(profile, "restart")
    existing = _ACTION_PROCS.get("gateway-restart")
    if existing is not None and existing.poll() is None:
        existing_command = _ACTION_COMMANDS.get("gateway-restart")
        if existing_command is None or existing_command == tuple(subcommand):
            return existing, True
        raise RuntimeError("gateway restart already in progress for another profile")
    return _spawn_hermes_action(subcommand, "gateway-restart"), False
```

在飞的重启会被**复用**(返回 `reused=True`),而不是再起一个——两个并发的
`hermes gateway restart` 会在"杀掉再启动"这条路径上互相抢。跨档冲突则显式抛错。

`hermes update` 同样去重,并把 `action_id` 回带给前端:

`hermes_cli/web_server.py:4129-4141 @ 863e313`

```python
    existing = _ACTION_PROCS.get("hermes-update")
    if existing is not None and existing.poll() is None:
        response = {
            "ok": True,
            "pid": existing.pid,
            "name": "hermes-update",
            "already_running": True,
        }
        action_id = _ACTION_IDS.get("hermes-update")
        if action_id:
            response["action_id"] = action_id
        return response
```

`tests/hermes_cli/test_web_server.py:1049-1054 @ 863e313`

```python
        monkeypatch.setattr(
            web_server,
            "_spawn_hermes_action",
            lambda *_args, **_kwargs: pytest.fail("must not spawn a duplicate update"),
        )
        web_server._ACTION_PROCS["hermes-update"] = Proc()
        web_server._ACTION_IDS["hermes-update"] = "b" * 32
```

**◇-E:去重只做在 restart / update 上,start / stop 没有。**
`/api/gateway/start`(12541-12550)与 `/stop`(12553-12562)直接 `_spawn_hermes_action`,
连点两下会起两个子进程并让 `_ACTION_PROCS["gateway-start"]` 只保留后一个 handle,
前一个进程的退出码从此无人知晓。搜索面:grep `_ACTION_PROCS.get` 全文只有 3964(restart)、
4129(update)、4779(status 读取)三处。严重度低(gateway start 自身有 PID 锁),记录备查。

### 4.4 `hermes update` 这类"会改本机文件"的动作是怎么被限制的

**四道闸,按顺序**:

**闸 1(授权)**:`/api/hermes/update` 不在 `PUBLIC_API_PATHS`,由 §2.5 的全局中间件挡住。
loopback 走 session token,非 loopback 走 OAuth/密码 cookie —— 而且非 loopback **一定**有门:

`hermes_cli/web_server.py:483-491 @ 863e313`

```python
    ``allow_public`` (the legacy ``--insecure`` escape hatch) NO LONGER disables
    the gate. It is accepted for backward-compat with old launch scripts and
    desktop shells but is ignored: a non-loopback bind ALWAYS requires an auth
    provider (OAuth or the bundled password provider). This closes the
    unauthenticated-public-dashboard hole behind the June 2026 ``hermes-0day``
    MCP-persistence campaign, where ``--insecure --host 0.0.0.0`` left the
    config/MCP/agent surface open to internet scanners.
    """
    return host not in _LOOPBACK_HOST_VALUES
```

**闸 2(容器/托管)**:`_dashboard_local_update_managed_externally()` —— 这就是任务书要找的
"容器里不该给这个按钮"的判断:

`hermes_cli/web_server.py:4088-4102 @ 863e313`

```python
    if _dashboard_local_update_managed_externally():
        message = (
            "Hermes updates are managed outside this dashboard in "
            "containerized environments. The built-in local updater is "
            "disabled here."
        )
        _record_completed_action("hermes-update", message, exit_code=1)
        return {
            "ok": False,
            "pid": None,
            "name": "hermes-update",
            "error": "dashboard_update_managed_externally",
            "message": message,
            "update_command": "managed outside dashboard",
        }
```

它的判据分三步,且刻意与"安装方式检测"解耦:

`hermes_cli/web_server.py:2118-2132 @ 863e313`

```python
def _dashboard_local_update_managed_externally() -> bool:
    """Return true when the dashboard should not offer ``hermes update``.

    Containerized dashboards are updated by the outer launcher/image, not by an
    in-browser local update action. Keep this dashboard capability separate
    from install-method detection: manual git/pip installs inside containers can
    still behave like their actual install method in the CLI.

    However, when the install method is ``git`` (a bind-mounted checkout inside
    a container — e.g. the hermes-webui image sharing the Hermes source tree),
    the dashboard's ``hermes update`` button is the correct update path and
    should not be suppressed. Other containerized install methods remain
    externally managed unless their apply path is proven safe inside the
    running container filesystem.
    """
```

`hermes_cli/web_server.py:2133-2153 @ 863e313`

```python
    if _default_hermes_root_is_opt_data():
        return True
    try:
        from hermes_constants import is_container

        if not is_container():
            return False
    except Exception:
        return False
    # We are inside a container, but the install may still be self-managed.
    # If the install method is git, the dashboard update button works against
    # the mounted checkout and should be offered. Keep pip blocked inside
    # containers: its apply path mutates the running container filesystem and
    # is not the bind-mounted checkout case this gate is meant to recover.
    try:
        method = detect_install_method(PROJECT_ROOT)
        if method == "git":
            return False
    except Exception:
        pass
    return True
```

判据读作:①`HERMES_HOME` 就是 `/opt/data`(托管布局)→ 禁;②不在容器里 → 放行;
③在容器里但安装方式是 git(绑定挂载的源码树)→ 放行;④其余容器内安装 → 禁。
第 ③ 条是后补的:它承认"容器"不等于"不可自更新",绑挂 checkout 的 webui 镜像里这个按钮才是
正确路径。第 ④ 条对 pip 保持禁止,理由写得很直白——pip 的 apply 路径会改**运行中容器的文件系统**。

**闸 3(安装方式)**:通过闸 2 之后,docker / nix 安装再各自劝返,**都不起子进程**:

`hermes_cli/web_server.py:4104-4116 @ 863e313`

```python
    install_method = detect_install_method(PROJECT_ROOT)
    if install_method == "docker":
        message = format_docker_update_message()
        _record_completed_action("hermes-update", message, exit_code=1)
        return {
            "ok": False,
            "pid": None,
            "name": "hermes-update",
            "error": "docker_update_unsupported",
            "message": message,
            "update_command": recommended_update_command_for_method(install_method),
        }
```

**这里有一个很漂亮的一致性设计**:被拒绝的动作不是简单返回错误,而是**合成一条"已完成的动作
记录"**写进同一个日志文件,于是前端那套"轮询 `/api/actions/hermes-update/status` 看尾巴"的
通用逻辑不用为拒绝路径写第二套:

`hermes_cli/web_server.py:3753-3768 @ 863e313`

```python
def _record_completed_action(name: str, message: str, exit_code: int = 1) -> None:
    """Record a non-spawned action result and write it to the action log."""
    log_file_name = _ACTION_LOG_FILES[name]
    _ACTION_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _ACTION_LOG_DIR / log_file_name
    with open(log_path, "ab", buffering=0) as log_file:
        log_file.write(
            f"\n=== {name} completed {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode()
        )
        log_file.write(message.encode("utf-8", errors="replace"))
        if not message.endswith("\n"):
            log_file.write(b"\n")
    _ACTION_PROCS.pop(name, None)
    _ACTION_COMMANDS.pop(name, None)
    _ACTION_IDS.pop(name, None)
    _ACTION_RESULTS[name] = {"exit_code": exit_code, "pid": None}
```

测试把"拒绝也要能从 action-status 尾巴里读到"钉住了:

`tests/hermes_cli/test_web_server.py:998-1002 @ 863e313`

```python
        status = self.client.get("/api/actions/hermes-update/status")
        assert status.status_code == 200
        status_data = status.json()
        assert status_data["running"] is False
        assert status_data["exit_code"] == 1
```

**闸 4(UI 层的"先查后更")**:`GET /api/hermes/update/check` 只报告不落地,并在托管场景下
**连安装方式都不去探**(测试用 `pytest.fail` 把这条钉死):

`hermes_cli/web_server.py:4240-4252 @ 863e313`

```python
    if _dashboard_local_update_managed_externally():
        return {
            "install_method": "managed-runtime",
            "current_version": __version__,
            "behind": None,
            "update_available": False,
            "can_apply": False,
            "update_command": "managed outside dashboard",
            "message": (
                "Hermes updates are managed outside this dashboard in "
                "containerized environments."
            ),
        }
```

`tests/hermes_cli/test_dashboard_admin_endpoints.py:812-821 @ 863e313`

```python
        monkeypatch.setattr(
            ws,
            "detect_install_method",
            lambda *a, **k: pytest.fail(
                "managed runtime update check should not probe install method"
            ),
        )

        body = self.client.get("/api/hermes/update/check").json()
        assert body["install_method"] == "managed-runtime"
        assert body["can_apply"] is False
```

同一个判据还提前铺进 `/api/status`,让前端连按钮都不渲染:

`hermes_cli/web_server.py:3229 @ 863e313`

```python
            "can_update_hermes": not _dashboard_local_update_managed_externally(),
```

前端确实读它:

`web/src/pages/SystemPage.tsx:515 @ 863e313`

```typescript
      if (status?.can_update_hermes === false) return;
```

**可迁移的设计原则**:一个"会改本机"的动作要有**三段式**——能力声明(status 里的布尔)、
执行前拒绝(端点里的同一判据)、拒绝也留痕(合成动作记录)。前端只做展示,**判据不能只写在前端**:
这里后端把同一个函数用了三次(3229 / 4088 / 4240),前端读它只是省一次点击。

### 4.5 drain:一个没有控制通道的控制端点

`hermes_cli/web_server.py:4025-4030 @ 863e313`

```python
    Body: ``{"action": "drain"}`` (begin) or ``{"action": "cancel"}`` (cancel).
    Begin writes the ``.drain_request.json`` marker the gateway's
    ``_drain_control_watcher`` observes (flip to ``draining`` + refuse new
    turns); cancel removes it (revert to ``running`` + re-accept). Idempotent
    on both sides. This endpoint only writes/removes the marker — the gateway
    process owns the actual state transition (there is no HTTP control channel
    into the running gateway; the marker IS the channel, decisions.md Q-B).
```

值得单记:dashboard 跑在 gateway **进程内**,却仍然用**文件标记 + watcher** 而不是直接改内存
状态。理由是这个端点也可能被 NAS 用 bearer token 从外部调用(见 4016-4023 的 docstring),
而 gateway 的状态机必须只有一个写入者。**"进程内也走同一条外部通道"**避免了两套状态转换路径。

---

## 5. Diagnostics(必答 5):打包了什么、有没有脱敏

### 5.1 四个端点、两种形态

`hermes_cli/web_server.py:3636-3640 @ 863e313`

```python
# ---------------------------------------------------------------------------
# Diagnostics: prompt-size, support dump, debug upload, config migrate.
# All produce text output, so they spawn background actions tailed via
# /api/actions/<name>/status.
# ---------------------------------------------------------------------------
```

▲/◇-F:横幅说 "All produce text output, so they spawn background actions",但**第四个不是**。
`debug-share` 是**同步**的,且它自己的 docstring 明确说了为什么:

`hermes_cli/web_server.py:3670-3680 @ 863e313`

```python
@app.post("/api/ops/debug-share")
async def run_debug_share_endpoint(body: DebugShareRequest | None = None):
    """Upload a redacted debug report + full logs and return the paste URLs.

    Unlike the other diagnostics actions (doctor, dump, prompt-size) this is
    *synchronous*: the whole point of ``debug share`` is the set of shareable
    URLs it produces, so we run the upload in a worker thread and return the
    structured ``{urls, failures, redacted, ...}`` payload directly. The
    dashboard renders those as real, copyable links instead of scraping a log
    tail. Pastes auto-delete after 6 hours (handled inside the share core).
    """
```

两条注释直接打架(横幅 vs 函数 docstring),以函数为准。这属于横幅在扩写后没跟上。

前三个都是三行的同一模板(起子进程、返回 pid):

`hermes_cli/web_server.py:3652-3658 @ 863e313`

```python
@app.post("/api/ops/dump")
async def run_dump():
    try:
        proc = _spawn_hermes_action(["dump"], "dump")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed: {exc}")
    return {"ok": True, "pid": proc.pid, "name": "dump"}
```

### 5.2 `hermes dump` 打包什么:**结论是「没有 .env、没有 config.yaml」**

这是任务书点名要查实的一条。逐条查证:

**(a) 输出是一张固定字段表,不是文件内容。** 全部 `lines.append` 调用共 20 处,字段是
version / os / python / openai_sdk / profile / hermes_home / model / provider / terminal /
api_keys / features / config_overrides:

`hermes_cli/dump.py:354-362 @ 863e313`

```python
    lines.append(f"version:          {ver_str}")
    lines.append(f"os:               {os_info}")
    lines.append(f"python:           {sys.version.split()[0]}")
    lines.append(f"openai_sdk:       {openai_ver}")
    lines.append(f"profile:          {profile}")
    lines.append(f"hermes_home:      {display_hermes_home()}")
    lines.append(f"model:            {model}")
    lines.append(f"provider:         {provider}")
    lines.append(f"terminal:         {backend}")
```

**(b) API key 一律只报 set / not set。** 只有 `--show-keys` 才显示,且**仍然过掩码**:

`hermes_cli/dump.py:397-402 @ 863e313`

```python
    for env_var, label in api_keys:
        val = os.getenv(env_var, "")
        if show_keys and val:
            display = _redact(val)
        else:
            display = "set" if val else "not set"
```

`hermes_cli/dump.py:115-123 @ 863e313`

```python
def _redact(value: str) -> str:
    """Redact all but first 4 and last 4 chars.

    Thin wrapper over :func:`agent.redact.mask_secret`. Returns ``""`` for
    an empty value (matches the historical behavior of this helper —
    ``hermes dump`` formats empty values as blank, not as ``"(not set)"``).
    """
    from agent.redact import mask_secret
    return mask_secret(value)
```

而 dashboard 与 debug-share 两条路径都**不传** `--show-keys`:

`hermes_cli/web_server.py:3655 @ 863e313`

```python
        proc = _spawn_hermes_action(["dump"], "dump")
```

`hermes_cli/debug.py:568-569 @ 863e313`

```python
    class _FakeArgs:
        show_keys = False
```

**(c) config 只输出一张 15 项白名单的"非默认值"。** 不是整份 `config.yaml`:

`hermes_cli/dump.py:236-253 @ 863e313`

```python
    interesting_paths = [
        ("agent", "max_turns"),
        ("agent", "gateway_timeout"),
        ("agent", "session_stall_timeout"),
        ("agent", "tool_use_enforcement"),
        ("terminal", "backend"),
        ("terminal", "docker_image"),
        ("terminal", "persistent_shell"),
        ("browser", "allow_private_urls"),
        ("compression", "enabled"),
        ("compression", "threshold"),
        ("compression", "in_place"),
        ("display", "streaming"),
        ("display", "skin"),
        ("display", "show_reasoning"),
        ("privacy", "redact_pii"),
        ("tts", "provider"),
    ]
```

**负结论 + 搜索面**:我在 `hermes_cli/dump.py`(457 行)全文查了 `read_text` / `open(` /
`config.yaml` / `.env` 的读取式引用,dump **不会把 `.env` 或 `config.yaml` 的内容读出来放进
输出**;`.env` 只被读**键名**(`_dotenv_key_names()`,`hermes_cli/dump.py:22-48`),
用来判断"这个 key 是不是只在 shell 里而不在 .env 里"。**所以本轮没有在这条路径上发现 ■。**

### 5.3 `debug share` 打包什么:报告 + 四份完整日志

`hermes_cli/debug.py:702-711 @ 863e313`

```python
    bundle: dict[str, str] = {"report": report}
    if agent_log:
        bundle["agent.log"] = agent_log
    if gateway_log:
        bundle["gateway.log"] = gateway_log
    if gui_log:
        bundle["gui.log"] = gui_log
    if desktop_log:
        bundle["desktop.log"] = desktop_log
```

每份分别上传到**公共**粘贴服务:

`hermes_cli/debug.py:789-800 @ 863e313`

```python
    # 1. Summary report (required — raises on failure so callers can fall back)
    urls["Report"] = upload_to_pastebin(report, expiry_days=expiry)

    # 2-5. Full logs (optional — failures are collected, not raised)
    for label in ("agent.log", "gateway.log", "gui.log", "desktop.log"):
        content = bundle.get(label)
        if not content:
            continue
        try:
            urls[label] = upload_to_pastebin(content, expiry_days=expiry)
        except Exception as exc:
            failures.append(f"{label}: {exc}")
```

`hermes_cli/debug.py:57-58 @ 863e313`

```python
_PASTE_RS_URL = "https://paste.rs/"
_DPASTE_COM_URL = "https://dpaste.com/api/"
```

### 5.4 **有没有脱敏:有。** 这是脱敏那几行

`hermes_cli/debug.py:425-439 @ 863e313`

```python
def _redact_log_text(text: str) -> str:
    """Run ``redact_sensitive_text`` with ``force=True`` over upload-bound text.

    Uses ``force=True`` so redaction fires regardless of the operator's
    ``security.redact_secrets`` setting. The local on-disk log file is
    not modified; only the in-memory copy headed for the public paste
    service is sanitized. Returns the redacted text (or the original
    when empty / non-string).
    """
    if not text:
        return text
    from agent.redact import redact_sensitive_text

    text = redact_sensitive_text(text, force=True)
    return _EMAIL_ADDRESS_RE.sub("[REDACTED_EMAIL]", text)
```

`hermes_cli/debug.py:523-525 @ 863e313`

```python
        if redact:
            tail_text = _redact_log_text(tail_text)
            full_text = _redact_log_text(full_text)
```

三个要点:
1. **`force=True`**——绕过用户的 `security.redact_secrets` 开关。用户可以关掉日志里的脱敏,
   但**外传边界**上必须脱。这是"安全边界不看用户偏好"的正确做法。
2. **只脱内存副本**,本地日志文件不动(便于本地排障)。
3. **额外脱邮箱**(`_EMAIL_ADDRESS_RE`)——`redact_sensitive_text` 管的是凭据形状,邮箱是
   在这一层专门补的。

上传物上还打了一条可见横幅,让看粘贴的人知道被处理过:

`hermes_cli/debug.py:41-44 @ 863e313`

```python
_REDACTION_BANNER = (
    "[hermes debug share: log content redacted at upload time. "
    "run with --no-redact to disable]\n"
)
```

**并且 Nous 内部通道也强制走同一份已脱敏快照**——这句话解释了为什么"收集"和"脱敏"要合并成
一个函数:

`hermes_cli/debug.py:656-661 @ 863e313`

```python
    This is the single source of collection + redaction shared by both
    destinations: the paste.rs path (:func:`build_debug_share`) and the
    Nous-S3 path (``--nous``).  Centralising it guarantees the Nous bundle is
    built from the *same* force-redacted snapshots as the public paste path —
    redaction is the safety boundary, so the Nous path must never see raw
    logs.
```

**可迁移的设计原则**:**脱敏必须发生在"收集"这一步,而不是"发送"这一步**。一旦有两个目的地,
放在发送侧就要写两遍,写两遍就一定会漏一遍。

### 5.5 ◇-G:CLI 有同意闸,dashboard 端点没有

CLI 路径在上传前**强制取得同意**,非交互还会直接退出:

`hermes_cli/debug.py:814-835 @ 863e313`

```python
def _confirm_upload(args) -> bool:
    """Require explicit consent before any debug-share upload.

    The privacy notice is printed by the caller. This gates the actual
    upload: with ``--yes`` (or ``-y``) we proceed unprompted; otherwise we
    ask an interactive ``[y/N]`` question. In a non-interactive context
    (no TTY on stdin — scripts, CI, piped input) we refuse rather than
    hang or upload silently, so debug data can't be exposed without a
    deliberate ``--yes``.

    Returns True to proceed with the upload, False to abort.
    """
    if bool(getattr(args, "yes", False)):
        return True
    if not sys.stdin.isatty():
        print(
            "ERROR: Non-interactive mode requires --yes to confirm upload.\n"
            "       This prevents accidental exposure of personal data.\n"
            "       Use --local to view the report without uploading.",
            file=sys.stderr,
        )
        sys.exit(1)
```

它配套的隐私告知**逐条点名了不会被脱敏的东西**:

`hermes_cli/debug.py:198-212 @ 863e313`

```python
_PRIVACY_NOTICE = """\
⚠️  This will upload system info + logs to a PUBLIC paste service.

Cryptographic secrets (API keys, tokens, passwords) are redacted before
upload, but the following personal data is NOT redacted and will be public:
  • Your display name and persistent platform user ID
  • Verbatim content of your recent messages (prompts, responses, tool output)
  • Local filesystem paths
  • Any other PII present in the logs

The resulting URL is public to anyone who has the link. Pastes auto-delete
after 6 hours, but may be archived by third parties in the meantime.

Use --local to view the report without uploading.
"""
```

而 dashboard 端点**直接调核心函数**,不经过 `_confirm_upload`,也不回显这份清单:

`hermes_cli/web_server.py:3681-3689 @ 863e313`

```python
    from hermes_cli.debug import build_debug_share

    req = body or DebugShareRequest()
    try:
        result = await asyncio.to_thread(
            build_debug_share,
            log_lines=max(1, min(int(req.lines), 5000)),
            redact=bool(req.redact),
        )
```

而且 `redact: false` 是**被支持并被测试钉住的**行为:

`tests/hermes_cli/test_dashboard_admin_endpoints.py:846-858 @ 863e313`

```python
    def test_redact_false_is_honored(self, monkeypatch):
        import hermes_cli.debug as dbg

        monkeypatch.setattr(
            dbg, "upload_to_pastebin", lambda c, expiry_days=7: "https://paste.rs/x"
        )
        monkeypatch.setattr(dbg, "_schedule_auto_delete", lambda *a, **k: None)
        monkeypatch.setattr(dbg, "_best_effort_sweep_expired_pastes", lambda: None)
        monkeypatch.setattr("hermes_cli.dump.run_dump", lambda a: None)

        r = self.client.post("/api/ops/debug-share", json={"redact": False})
        assert r.status_code == 200
        assert r.json()["redacted"] is False
```

前端把 redact 做成一个**默认勾选**的复选框,但按钮本身**没有二次确认弹窗**:

`web/src/pages/SystemPage.tsx:1379-1392 @ 863e313`

```typescript
              <Checkbox
                checked={shareRedact}
                disabled={sharing}
                id="share-redact"
                onCheckedChange={(checked) => setShareRedact(checked === true)}
              />

              <Label
                className="cursor-pointer select-none text-xs font-normal normal-case tracking-normal text-muted-foreground"
                htmlFor="share-redact"
              >
                Redact credential-shaped tokens before upload (recommended)
              </Label>
```

前端的说明文字比 CLI 的告知短得多,**没有点名"你最近消息的逐字内容会公开"**:

`web/src/pages/SystemPage.tsx:1355-1359 @ 863e313`

```typescript
                  <span className="text-xs text-muted-foreground max-w-prose">
                    Uploads system info + logs to a public paste service and
                    returns links to send the Hermes team. Pastes auto-delete
                    after 6 hours.
                  </span>
```

**判定:◇ 不是 ■。** 理由:(1) 端点需要认证;(2) 点按钮本身可视作同意,复选框把 redact
显式暴露了;(3) `redact=False` 是被测试固化的产品决定,不是疏漏。**但这条必须写进移交项**:
两条路径对"同一次外传"的同意标准不一致——CLI 认为"非交互 = 拒绝上传",dashboard 认为
"一次点击 = 同意 + 可关脱敏"。造 harness 时这类**同一能力两个入口、闸门强度不同**的模式
是最容易漏掉的一类风险面,值得单独立规矩:**外传能力的同意闸应该做在核心函数里,而不是在某一个
入口的包装层里**(对照 §5.4 把脱敏做进收集层的做法——同意闸没有享受同样的待遇)。

### 5.6 ◇-H:三个 Diagnostics 端点在文档里,`debug-share` 不在

搜索面:`grep -rn "api/ops/debug-share" --include=*.md .` 全仓 **0 命中**;
`website/docs/user-guide/features/web-dashboard.md:549` 只登记了另外三个:

`website/docs/user-guide/features/web-dashboard.md:549 @ 863e313`

> | `POST /api/ops/prompt-size` · `/dump` · `/config-migrate` | Diagnostics (backgrounded) |

即:**唯一一个会把数据送出主机的诊断端点,是唯一没被写进 API 表的那个**。同一份文档里
`POST /api/hermes/update`(会改本机文件)也缺席,只登记了 `/update/check`。

---

## 6. Portal(:3590)与 Curator(:3481)

### 6.1 Portal:解决什么问题,是不是只读

**解决的问题**:用户可以让 Hermes 挂在 Nous Portal 下用托管推理和托管工具。这一页回答
"我登没登录 / 推理走哪个地址 / 我的订阅覆盖了哪些能力 / 哪些能力目前走 Portal、哪些走自配 provider"。

`hermes_cli/web_server.py:3588-3590 @ 863e313`

```python
# ---------------------------------------------------------------------------
# Portal endpoint — Nous Portal auth + Tool Gateway routing status (read-only).
# ---------------------------------------------------------------------------
```

**auth 那一半确实是免刷新的**,且注释解释了为什么必须免刷新:

`hermes_cli/web_server.py:3597-3604 @ 863e313`

```python
    try:
        from hermes_cli.auth import get_nous_auth_status_local

        # Read-only dashboard endpoint: refresh-free snapshot so polling
        # never performs an OAuth refresh or burns a refresh token.
        auth = get_nous_auth_status_local() or {}
    except Exception:
        auth = {}
```

`hermes_cli/auth.py:6724-6731 @ 863e313`

```python
def get_nous_auth_status_local() -> Dict[str, Any]:
    """Refresh-free Nous auth snapshot for read-only display surfaces.

    Unlike :func:`get_nous_auth_status`, this NEVER calls
    ``resolve_nous_runtime_credentials()`` and therefore never performs an
    OAuth refresh POST or consumes a single-use refresh token. It reports the
    persisted auth-store state, classifying the access token with a local
    invoke-JWT decode only.
```

**这个设计点值得单记**:OAuth refresh token 常常是**一次性**的(用一次换一对新的)。一个每几秒
被轮询的状态面板如果走"顺手刷新一下"的路径,会不断消耗 refresh token,并制造并发刷新竞争
(两个刷新同时用同一个 token,后到的那个被服务端判为重放 → 整个登录终态失效)。所以状态展示面
必须有一条**只读快照**的 API,和"我真的要用这个凭据"的路径分开。

**◇-I:同一个端点的第二半不是免刷新的。** `features` 那一段走的是另一条链:

`hermes_cli/web_server.py:3606-3611 @ 863e313`

```python
    features = []
    try:
        from hermes_cli.nous_subscription import get_nous_subscription_features

        feats = get_nous_subscription_features(cfg)
        if feats is not None:
```

`hermes_cli/nous_subscription.py:358-364 @ 863e313`

```python
    try:
        if force_fresh:
            account_info = get_nous_portal_account_info(force_fresh=True)
        else:
            account_info = get_nous_portal_account_info()
    except Exception:
        account_info = None
```

`get_nous_portal_account_info` 在**本地 JWT 已过期/缺失**时会落到 `_fresh_account_info`,
后者调用的是 refresh-aware 的解析器:

`hermes_cli/nous_account.py:361-375 @ 863e313`

```python
    if not force_fresh:
        jwt_info = _info_from_valid_jwt(
            access_token,
            state=state,
            portal_base_url=portal_base_url,
            min_jwt_ttl_seconds=min_jwt_ttl_seconds,
        )
        if jwt_info is not None:
            return jwt_info

    return _fresh_account_info(
        state=state,
        force_fresh=force_fresh,
        portal_base_url=portal_base_url,
    )
```

`hermes_cli/nous_account.py:386-389 @ 863e313`

```python
    try:
        from hermes_cli.auth import get_provider_auth_state, resolve_nous_access_token

        access_token = resolve_nous_access_token()
```

`hermes_cli/auth.py:5859 @ 863e313`

```python
    """Resolve a refresh-aware Nous Portal access token for managed tool gateways."""
```

**修正后的准确表述**:`/api/portal` 对本机状态是只读的(不写 config),但它**不是无副作用的**——
`features` 分支在 JWT 过期时会发起网络请求,并可能触发一次 OAuth refresh。缓解是两层缓存
(账户信息 60 秒:`hermes_cli/nous_account.py:31`;token 解析另有短窗缓存),所以轮询不会每次都
烧 token。严重度:低。但横幅那句 "(read-only)" 会让读者以为整段免网络,值得在成品章里改写成
"只读本机状态;features 分支可能走网络"。

### 6.2 Curator:解决什么问题,有没有副作用

**解决的问题**——agent 自建技能只增不减:

`agent/curator.py:1-19 @ 863e313`

```python
"""Curator — background skill maintenance orchestrator.

The curator is an auxiliary-model task that periodically reviews agent-created
skills and maintains the collection. It runs inactivity-triggered (no cron
daemon): when the agent is idle and the last curator run was longer than
``interval_hours`` ago, ``maybe_run_curator()`` spawns a forked AIAgent to do
the review.

Responsibilities:
  - Auto-transition lifecycle states based on derived skill activity timestamps
  - Spawn a background review agent that can pin / archive / consolidate /
    patch agent-created skills via skill_manage
  - Persist curator state (last_run_at, paused, etc.) in .curator_state

Strict invariants:
  - Only touches agent-created skills (see tools/skill_usage.is_agent_created)
  - Never auto-deletes — only archives. Archive is recoverable.
  - Pinned skills bypass all auto-transitions
```

**三个端点的副作用等级**:

**`GET /api/curator` —— 只读**,而且是"读不到就给默认值"的读:

`hermes_cli/web_server.py:3494-3506 @ 863e313`

```python
    try:
        state = curator.load_state()
    except Exception:
        state = {}
    return {
        "enabled": _safe_call(curator, "is_enabled", True),
        "paused": _safe_call(curator, "is_paused", False),
        "interval_hours": _safe_call(curator, "get_interval_hours", None),
        "last_run_at": state.get("last_run_at"),
        "min_idle_hours": _safe_call(curator, "get_min_idle_hours", None),
        "stale_after_days": _safe_call(curator, "get_stale_after_days", None),
        "archive_after_days": _safe_call(curator, "get_archive_after_days", None),
    }
```

`hermes_cli/web_server.py:3580-3585 @ 863e313`

```python
def _safe_call(mod, fn_name: str, default):
    try:
        fn = getattr(mod, fn_name, None)
        return fn() if callable(fn) else default
    except Exception:
        return default
```

`_safe_call` 同时兜住"函数不存在"(旧版 curator 模块)和"函数抛异常"两种情况——这是**跨版本
兼容**的写法,让 dashboard 不必和 `agent.curator` 同步演进。

**`PUT /api/curator/paused` —— 写状态文件**:

`hermes_cli/web_server.py:3509-3514 @ 863e313`

```python
@app.put("/api/curator/paused")
async def set_curator_paused(body: CuratorPause):
    from agent import curator

    curator.set_paused(bool(body.paused))
    return {"ok": True, "paused": bool(body.paused)}
```

`agent/curator.py:124-127 @ 863e313`

```python
def set_paused(paused: bool) -> None:
    state = load_state()
    state["paused"] = bool(paused)
    save_state(state)
```

**`POST /api/curator/run` —— 起子进程,副作用最大**(会真的归档技能):

`hermes_cli/web_server.py:3517-3524 @ 863e313`

```python
@app.post("/api/curator/run")
async def run_curator():
    """Trigger a curator review now (backgrounded; tail via action status)."""
    try:
        proc = _spawn_hermes_action(["curator", "run"], "curator-run")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run curator: {exc}")
    return {"ok": True, "pid": proc.pid, "name": "curator-run"}
```

**◇-J:同一横幅下的多档一致性不一致。** 紧挨着的 learning-graph 三个端点都接 `?profile=` 并用
`_profile_scope` 包住;curator 的三个端点**都不接 profile**,即"暂停/立刻跑"永远作用于
dashboard 自己那一档:

`hermes_cli/web_server.py:3527-3538 @ 863e313`

```python
@app.get("/api/learning/graph")
async def get_learning_graph(profile: Optional[str] = None):
    """Learning graph payload for the desktop panel.

    Profile-scoped view of learned, non-base skills plus memory chunks, with
    graph links derived from skill relations and memory-skill overlap.
    """
    try:
        from agent.learning_graph import build_learning_graph

        with _profile_scope(profile):
            return build_learning_graph()
```

搜索面:`grep -n "profile" hermes_cli/web_server.py` 在 3488–3525 区间无命中;
`_spawn_hermes_action(["curator", "run"], ...)` 也没有像网关那样走 `_profile_cli_args`
(对照 `hermes_cli/web_server.py:3888-3889`)。后果:在多档安装上,从档 B 的界面点
"Run curator now",跑的是档 A(dashboard 自身)的技能库。严重度:中(会作用于错误的数据集),
但需要"多档 + dashboard 切档"才触发,且 curator 从不删除只归档,可恢复。

**顺带记一条被同一横幅罩住、但语义更重的东西**:learning-node 的 DELETE / PUT 会**直接改写技能
文件与记忆块**——横幅只说 "Curator endpoints — background skill-maintenance status + controls",
完全没有提这三条:

`hermes_cli/web_server.py:3556-3565 @ 863e313`

```python
@app.delete("/api/learning/node")
async def delete_learning_node(body: LearningNodeRef):
    """Delete a journey node — skills are archived (restorable), memories removed."""
    from agent.learning_mutations import delete_node

    with _profile_scope(body.profile):
        res = delete_node(body.id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("message", "delete failed"))
    return res
```

注意 docstring 里的不对称:**技能是归档(可恢复),记忆是删除(不可恢复)**。

---

## 7. 本段挂载的路由(任务书点名的四处)

`hermes_cli/web_server.py:2750-2752 @ 863e313`

```python
from hermes_cli.web_routers import git as _git_routes  # noqa: E402

app.include_router(_git_routes.router)
```

`hermes_cli/web_server.py:4825-4830 @ 863e313`

```python
from hermes_cli.web_routers import sessions as _sessions_routes  # noqa: E402

app.include_router(_sessions_routes.list_router)
from hermes_cli.web_routers.sessions import (  # noqa: E402,F401 — legacy re-exports; tests call these via web_server.<name>
    get_sessions,
)
```

`hermes_cli/web_server.py:4833-4839 @ 863e313`

```python
from hermes_cli.web_routers import profiles as _profiles_routes  # noqa: E402

app.include_router(_profiles_routes.sessions_router)
from hermes_cli.web_routers.profiles import (  # noqa: E402,F401 — legacy re-exports; tests call these via web_server.<name>
    get_profiles_sessions,
    get_profiles_sessions_sidebar,
)
```

`hermes_cli/web_server.py:4844-4847 @ 863e313`

```python
app.include_router(_sessions_routes.search_router)
from hermes_cli.web_routers.sessions import (  # noqa: E402,F401 — legacy re-exports; tests call these via web_server.<name>
    search_sessions,
)
```

四处挂载对应的路由(用 grep 列全,非源码块):

```text
_git_routes.router            → 19 条 /api/git/*(见 §2)
_sessions_routes.list_router  → GET /api/sessions            (web_routers/sessions.py:50)
_profiles_routes.sessions_router → GET /api/profiles/sessions        (web_routers/profiles.py:59)
                                 GET /api/profiles/sessions/sidebar  (web_routers/profiles.py:203)
_sessions_routes.search_router → GET /api/sessions/search      (web_routers/sessions.py:166)
```

**为什么一个模块被拆成三个 router 分三处挂?** 因为 FastAPI 的路由匹配是**注册顺序优先**,
而 `web_server` 里在这三处之间还夹着别的路由(尤其是 `/api/sessions/{id}` 这类带路径参数的),
`/api/sessions/search` 必须排在 `/api/sessions/{session_id}` **之前**才不会被后者吃掉。
把同一模块的路由拆成命名 router、在原来的行位置分别 `include_router`,是**保持注册顺序不变**的
最小侵入做法——这也是 `git.py` 头部那句 "Handler bodies are byte-identical to their previous
in-web_server form" 的同一动机:

`hermes_cli/web_routers/git.py:1-7 @ 863e313`

```python
"""Git dashboard routes (extracted verbatim from web_server.py).

Handler bodies are byte-identical to their previous in-web_server form; the
helpers they call (``_git_op``, ``_git_path``) still live in web_server and are
reached via the late-binding seam in :mod:`hermes_cli.web_deps`, so
``monkeypatch.setattr(web_server, ...)`` keeps working.
"""
```

**可迁移的设计原则**:拆一个 17k 行的巨型路由模块,最大的风险不是逻辑搬错,而是**隐式顺序依赖
被打断**。这里的做法是:①按块拆成多个 router;②在原行位置挂载,顺序守恒;③handler 逐字搬;
④helper 留在原地用 late-binding 取。四条合起来把"重构"降级成了"移动文本"。

---

## 8. 记号汇总

```text
记号   编号   一句话                                                        锚点
--------------------------------------------------------------------------------------------------
◇     A     段落横幅 "Gateway + update actions" 统辖 2533 行、覆盖四个       web_server.py:3706-3714
            无关簇(audio / action-status / 会话路由 / provider)
◇     B     2774–2811 是 38 行连续空白(git 路由抽离的重构疤)               web_server.py:2774-2811
◇     C     /api/files 有 locked_root 牢笼,/api/fs + /api/git 没有;         web_server.py:2207 vs 2746
            因 /api/pty 无条件开启,判定为 UX 边界而非安全边界
◇     D     _TOPOLOGY_CACHE 纯 10s TTL、无签名、无端点主动失效;             web_server.py:2955
            与签名感知的 get_running_pid_cached 在窗口内可自相矛盾          gateway/status.py:2237
◇     E     restart/update 有在飞去重,start/stop 没有                       web_server.py:12541,12553
▲/◇   F     Diagnostics 横幅说四个都 backgrounded,debug-share 实为同步      web_server.py:3638 vs 3674
◇     G     CLI 的 _confirm_upload 同意闸不在核心函数里,dashboard 绕过它    debug.py:814 vs web_server.py:3681
◇     H     唯一会外传数据的诊断端点 debug-share 不在 API 文档表里           web-dashboard.md:549
◇     I     /api/portal 横幅标 (read-only),features 分支会走网络并可能刷新   web_server.py:3589 vs 3610
◇     J     curator 三端点不接 ?profile=,邻居 learning-* 全接               web_server.py:3517 vs 3527
◎     A     _profile_platform_ports 自陈不解析 env 端口覆盖(诚实保守)      web_server.py:2840-2842
◎     B     文档对 /api/status 的描述只说 4 类字段,实际返回 20+ 类           web-dashboard.md:416
■     —     本段未发现(逐条排查见 §5.2 的负结论与搜索面)
```

**关于 ■ 的负结论与搜索面**:任务书重点提示 support dump / debug upload 是"经典凭据外泄面"。
我按三条路径查实:(1) `hermes_cli/dump.py` 全文 457 行,输出字段是固定 20 处 `lines.append`,
API key 恒为 `set`/`not set`,config 只输出 15 项白名单差异,`.env` 只读键名不读值;
(2) `hermes_cli/debug.py` 的 bundle 只含 `report` + 四份日志,**不含任何配置文件**;
(3) 上传前统一过 `redact_sensitive_text(force=True)` + 邮箱正则。
排除项:未审 `agent/redact.py` 的正则覆盖度本身(是否漏掉某种凭据形状)——那是另一块的活,
列入 §9 存疑。**结论:本段没有"打包 .env / config.yaml 出去"的失效链,不记 ■。**

---

## 9. 测试实跑

环境(按 CLAUDE.md 要求同时记):

```console
$ ls -d /home/user/hermes-venv && /home/user/hermes-venv/bin/pip list | tail -n +3 | wc -l
/home/user/hermes-venv
87
```

第一批(拓扑 + git):

```console
$ cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
    bash scripts/run_tests.sh tests/test_web_server_status_topology_cache.py \
      tests/hermes_cli/test_web_server_gateway_topology.py \
      tests/hermes_cli/test_web_server_git.py tests/hermes_cli/test_noninteractive_git.py
=== Summary: 4 files, 19 tests passed, 0 failed (100% complete) in 2.0s (8 workers) ===
```

第二批(诊断 + 动作 + 更新闸):

```console
$ cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
    bash scripts/run_tests.sh tests/hermes_cli/test_debug.py \
      tests/hermes_cli/test_dashboard_admin_endpoints.py tests/hermes_cli/test_web_server.py \
      tests/hermes_cli/test_dump_env_visibility.py tests/hermes_cli/test_curator_status.py
=== Summary: 5 files, 231 tests passed, 0 failed (100% complete) in 9.4s (8 workers) ===
```

**合计 9 个文件、250 个用例、0 失败。** 无需诊断根因(容器已知的 5 个必然失败用例
——无 IPv6 / root / 离线 models.dev——都不在本轮选的文件里)。

选文件的搜索面:`ls tests/ | grep web_server` 得 4 个(其中
`test_install_ps1_web_server_syntax_probe.py`、`test_web_server_sessiondb_eventloop.py`
与本段无关);`ls tests/hermes_cli | grep -iE "git|status|update|dump|topolog|debug|curator|portal|action|gateway"`
得 45 个,其中 `test_update_*` 共 16 个测的是 `hermes update` 命令本身(不是 dashboard 端点),
`test_gateway_*` 共 12 个测的是网关生命周期本身,均属别的簇,本轮不跑。

---

## 10. 基线只读复核

```console
$ git -C /home/user/hermes-agent rev-parse HEAD
863e31318553cda8ad61df681d08175364d4164b
$ git -C /home/user/hermes-agent status --porcelain
(空)
```

本轮在基线目录下只执行了读操作与 `scripts/run_tests.sh`(其产物 `test_durations.json` 被
`.gitignore` 覆盖,`--porcelain` 为空可证);唯一的临时脚本 `/tmp/r8c_fspath_probe.py`、
`/tmp/r8c_ex.py` 都写在 `/tmp`。

---

## 11. 本段未覆盖 / 存疑(每条带锚点文件 + 行号 + 一句话现象)

1. **Audio 簇整体未读(462 行)** —— 锚点 `hermes_cli/web_server.py:4304`
   (`@app.post("/api/audio/transcribe")`)到 `:4766`。现象:`/api/audio/speak-stream` 是本文件
   里除 `/api/pty` 外唯一的**流式 WebSocket**,自带握手协议(`{"text"}` / `{"done"}` / `{"stop"}`
   → `start` / PCM 帧 / `end` / `fallback`,见 `:4626-4633`),且有独立的 `_ws_auth_ok` /
   `_ws_request_is_allowed` 双闸(`:4635-4640`)——WebSocket 不走 HTTP 中间件,认证是另一套。
   建议单独一轮和 `/api/pty`、`/api/ws` 合并读。

2. **Provider 字段与记忆后端簇未读(约 1400 行)** —— 锚点 `hermes_cli/web_server.py:4876`
   (`def _provider_field_entry`)到 `:6122`。现象:这一片有 `_write_provider_flat`(:5105)、
   `_install_memory_provider_pip_dependencies`(:5408)、
   `_install_memory_provider_external_dependencies`(:5468)——**dashboard 会 pip install
   任意后端依赖**,是本段第二个"改本机"的面,但它不在 `_ACTION_LOG_FILES` 的动作台账里,
   授权与限制路径尚未查。

3. **`agent/redact.py` 的正则覆盖度未验证** —— 锚点 `agent/redact.py:659`
   (`def redact_sensitive_text`)。现象:§5.4 证明了外传路径**调用了**脱敏,但没有验证
   这 13 条 pattern 覆盖哪些凭据形状、有没有已知漏网(docstring 在 `:695-702` 提到有"廉价
   子串预检"做性能门,预检写错就是静默漏脱)。这是判断 §5 结论强度的关键前置。

4. **`/api/status` 主体(3018–3352)只读了拓扑与敏感度切分两处** —— 锚点
   `hermes_cli/web_server.py:3054`(`def _bounded_health_probe`)。现象:该函数为跨容器
   健康探测单独开了一个 `ThreadPoolExecutor(max_workers=1)` 并设超时,注释说"只在本地 PID
   探测落空时才付这个超时"——这条"分级探活阶梯"(`resolve_gateway_liveness` 的 4 个 probe
   参数,`:3082-3089`)本身值得单独取证,本轮未做。

5. **`_ACTION_LOG_DIR` 在 import 期固化** —— 锚点 `hermes_cli/web_server.py:3716`
   (`_ACTION_LOG_DIR: Path = get_hermes_home() / "logs"`)。现象:它在模块导入时求值,
   因此不受 `_profile_scope` / `set_hermes_home_override` 的 contextvar 影响。我判断这是
   **有意为之**(动作日志应集中在 dashboard 自己的 home,便于 `/api/actions/*/status` 统一尾读),
   但没有找到把这个意图写下来的注释或测试,存疑。

6. **`_git_op` 用默认线程池、无限流** —— 锚点 `hermes_cli/web_server.py:2741`
   (`return await loop.run_in_executor(None, fn, *args)`)。现象:默认池被本文件多处共用
   (拓扑扫描 `:3322`、`_load_configured_gateway_platforms` `:3101`、`_probe_state_db` `:3261`),
   而单次 git 调用可阻塞 30 秒(`hermes_cli/web_git.py:24`)。是否存在"一批 git 请求把池占满、
   进而拖慢 `/api/status`"的路径,本轮未做压测验证。

7. **`gateway_drain` 的 token 认证插件未读** —— 锚点 `hermes_cli/web_server.py:4016-4019`
   (docstring 里的 "the ``dashboard_auth/drain`` plugin registers this exact path as a token route")。
   现象:这是本段唯一一条**认证由插件动态注册**的路由,`plugins/dashboard_auth/drain` 未读;
   文档(`website/docs/user-guide/features/web-dashboard.md:970`)说它"fails closed,
   密钥 < 256 bit 直接拒绝注册",未取证。

8. **`_PORT_BINDING_PLATFORM_PORTS` 与适配器常量的一致性只核了顺序、没核值** —— 锚点
   `hermes_cli/web_server.py:2817`(表定义)。现象:注释声称该表 "Mirrors
   ``PORT_BINDING_PLATFORM_VALUES`` in gateway/config.py and each adapter's DEFAULT_PORT /
   DEFAULT_WEBHOOK_PORT constant";我核对了**合并优先级**(§3.2,一致),但**没有逐项核对
   9 个平台的键名与默认端口是否真的等于各适配器常量**。表里 `bluebubbles` 与 `wecom_callback`
   都写 8645、`msgraph_webhook` 与 `line` 都写 8646,重复值看着可疑,值得下一轮逐项比对。
