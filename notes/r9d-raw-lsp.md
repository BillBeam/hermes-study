# r9d 底稿 · LSP 子系统(`agent/lsp/` 的 11 个文件)

> 求全求证型底稿。凡对 hermes-agent 行为的断言,紧跟 `路径:行号 @ 863e313` 与代码原文块;
> 锚点单独成行、置于块前。非源码块用 ```text / ```verify / ```console 显式标注。
> 基线:`863e31318553cda8ad61df681d08175364d4164b`,工作区只读、未改动。

本片精读文件(合计 4,708 行,**11 个全部逐行读完**):

| 文件 | 行数 | 角色 |
|---|---|---|
| `agent/lsp/servers.py` | 1187 | 27 个语言服务器的注册表:扩展名匹配 / 项目根解析 / spawn 配方 |
| `agent/lsp/client.py` | 1029 | 单个 `(server, workspace)` 的异步 LSP 客户端:进程、JSON-RPC、文档版本、诊断等待 |
| `agent/lsp/manager.py` | 744 | 服务层:后台事件循环线程、客户端池、broken-set、delta 基线、空闲回收 |
| `agent/lsp/install.py` | 412 | 缺失二进制的自动安装(npm / go),装到 `<HERMES_HOME>/lsp/` |
| `agent/lsp/cli.py` | 299 | `hermes lsp status/list/install/install-all/restart/which` |
| `agent/lsp/eventlog.py` | 233 | 结构化事件日志 + 「稳态静默」去重 |
| `agent/lsp/workspace.py` | 223 | git 工作区闸门 + 逐服务器项目根上行搜索 |
| `agent/lsp/protocol.py` | 196 | `Content-Length` 分帧 + JSON-RPC 2.0 信封 |
| `agent/lsp/range_shift.py` | 149 | 编辑后行号平移映射(difflib opcodes) |
| `agent/lsp/reporter.py` | 130 | 诊断 → 模型可读的 `<diagnostics>` 块(裁剪 + 净化) |
| `agent/lsp/__init__.py` | 106 | 进程级单例 + atexit 兜底 |

**术语锚定(首次出现)**
- **LSP**(Language Server Protocol):编辑器与语言服务器之间的标准协议,基于 JSON-RPC 2.0,
  用 `Content-Length` 头分帧;这里 harness 扮演「编辑器」这一侧。
- **push 诊断 / pull 诊断**:服务器主动发 `textDocument/publishDiagnostics` 通知叫 push;
  客户端主动发 `textDocument/diagnostic` 请求去要叫 pull。LSP 3.17 两种都有,不同服务器只支持其中一种。
- **文档版本(document version)**:客户端每次 `didChange` 递增的整数,用来判断服务器回来的诊断
  描述的是哪一版内容。
- **ghost diagnostics(幽灵诊断)**:模型改完文件后,harness 把**上一版内容**的诊断当成当前诊断报回去,
  模型于是去追一个自己已经修好的错。这是本子系统整个设计的核心敌人。
- **broken-set**:spawn/初始化失败过的 `(server_id, root)` 对,本进程内不再重试。
- **delta 基线(delta baseline)**:写入前拍下的诊断快照;写入后只报「不在基线里的」那些。

---

## 0. 一页结论

**这一片解决什么问题**:让 agent 写完一个文件之后,拿到的不是「语法能不能 parse」这种
微秒级的浅检查,而是**真语言服务器给的语义诊断**(类型错、未定义名、缺 import),
并且**只报这次编辑引入的那些**。为此它要把一个外部长驻进程接进一个同步的工具调用路径,
还要保证这个外部进程再怎么慢、卡、崩,都不能让 `write_file` 失败。

**六个最值得记住的结论:**

1. **整个防幽灵机制建立在「文档版本」这一个整数上,不用时间戳。** 每个存储的 push/pull 结果
   都带一个版本 tag,`tag >= 当前版本` 才算新鲜;一次 `didChange` 把版本 +1,**所有旧结果自动失效**,
   既不用清空存储也不存在竞态窗口。`wait_for_diagnostics` 超时返回 `False` 时,服务层把它翻译成
   `None`(「无判决」)而不是 `[]`(「干净」)——这两者不能混。
2. **`range_shift.py` 解决的不是并发竞态,是坐标系竞态。** 它对付的是「基线诊断在编辑前的行号 vs
   编辑后的行号」这个纯确定性的坐标不一致(见 §5)。
3. **超时值有两套,而且外层比内层紧。** 内层(client)最长 45s 初始化 / 5s(或 full 模式 10s)等诊断;
   外层(manager 同步调用)`max(8.0, wait_timeout+3.0)`。**外层先炸,而外层炸的后果是把这对
   `(server, root)` 永久标 broken**。本片最重的两条 ■ 都出在这个夹缝里(§4.3、§4.4)。
4. **诊断噪音的裁剪是三段式**:delta 过滤(只报新引入的)→ 严重度过滤(**硬编码只留 ERROR**)→
   条数与字符数上限(每文件 20 条 / 全文 4000 字符),外加一层**把语言服务器输出当作不可信输入**
   的净化(防提示注入)。
5. **`servers.py` 的 1187 行几乎全是数据**:27 个 `ServerDef` + 27 个 spawn 构造器 + 25 个根解析器。
   加一个新语言最少要动 3 处、最多 5 处(见 §7.3)。
6. **install.py 会联网**(`npm install` / `go install`),**但 hermes 自己不做任何校验、不做版本钉死**
   ——`gopls@latest`、npm 包不带版本,完整性完全托付给 npm registry / Go 模块校验和数据库(见 §8)。

---

## 1. 先场景:一次 `write_file` 在 LSP 层的完整走法

调用点在 `tools/file_operations.py`,不在本片,但不看它就讲不清本片的时序。

`tools/file_operations.py:1556-1558 @ 863e313`

```python
        # ``beforeFileEdited`` pattern but wired to the local LSP
        # rather than an external IDE.
        self._snapshot_lsp_baseline(path)
```

`tools/file_operations.py:1637-1643 @ 863e313`

```python
        lsp_diagnostics: Optional[str] = None
        if lint_result.success or lint_result.skipped:
            block = self._maybe_lsp_diagnostics(
                path, pre_content=pre_content, post_content=content
            )
            if block:
                lsp_diagnostics = block
```

于是一次写入的顺序是:

```text
1. 读旧内容 pre_content(为 lint delta 与 LSP 行移位图两用)
2. svc.snapshot_baseline(path)        <- LSPService: didOpen/didChange 旧内容 + 等诊断 => 基线
3. 原子写盘
4. 进程内语法检查(ast.parse / json.loads ...)
5. 语法干净才继续:build_line_shift(pre, post) -> svc.get_diagnostics_sync(delta=True, line_shift=...)
   -> 服务层:didChange 新内容 + didSave + 等「新鲜」诊断 -> 减去(平移过的)基线
6. reporter.report_for_file(...) -> "<diagnostics file=...>" 塞进 WriteResult.lsp_diagnostics
```

**关键取舍**:第 5 步的语法闸门(`lint_result.success or lint_result.skipped`)意味着
**一个连语法都不过的文件永远不会走到 LSP**。理由写在调用点注释里:没必要问一个语言服务器
一个 parse 都过不了的文件。代价是:语法错时模型只拿到语法错这一条信息。

**LSP 只在本地后端跑**。

`tools/file_operations.py:2022-2026 @ 863e313`

```python
        try:
            from tools.environments.local import LocalEnvironment
        except Exception:  # noqa: BLE001
            return False
        return isinstance(env, LocalEnvironment)
```

Docker / Modal / SSH / Daytona 后端下文件在沙箱里,宿主上的语言服务器看不到,所以整条 LSP 路直接跳过。
这条边界很重要:`LSPClient.open_file` 是**自己 `Path(...).read_text()` 从宿主磁盘读文件**的
(见 §3.4),沙箱路径下它读到的要么是不存在,要么是另一个同名文件。

---

## 2. 闸门:什么时候 LSP 才跑(`workspace.py` 223 行)

### 2.1 git 工作区闸门

`agent/lsp/workspace.py:193-204 @ 863e313`

```python
    cwd = cwd or os.getcwd()
    cwd_root = find_git_worktree(cwd)
    if cwd_root is not None:
        if is_inside_workspace(file_path, cwd_root):
            return cwd_root, True
        # File is outside the cwd's worktree — try the file's own
        # location as a secondary anchor.  Useful for monorepos where
        # the user opens an unrelated checkout.
    file_root = find_git_worktree(file_path)
    if file_root is not None:
        return file_root, True
    return None, False
```

设计意图写在模块 docstring 里:Telegram/Discord 网关的 cwd 是用户 home,不该因为用户
贴了一段 python 就起一个 pyright 守护进程。**「是不是项目」这个判断被简化成「有没有 .git」**
——一个极粗但零配置、零误报成本的近似。

`.git` 是文件也算(`git worktree add` 建出来的工作树里 `.git` 是文件)。

`agent/lsp/workspace.py:73-78 @ 863e313`

```python
        git_marker = cur / ".git"
        try:
            if git_marker.exists():
                resolved = str(cur)
                _workspace_cache[str(start_path)] = (resolved, True)
                return resolved
```

### 2.2 ■ 负缓存让文档教的 `git init` 在本进程内无效

缓存是**正负都缓存**的,且只在服务 shutdown 时清。

`agent/lsp/workspace.py:62-66 @ 863e313`

```python
    # Cache check
    cached = _workspace_cache.get(str(start_path))
    if cached is not None:
        root, _is_git = cached
        return root
```

`agent/lsp/workspace.py:87-88 @ 863e313`

```python
    _workspace_cache[str(start_path)] = (None, False)
    return None
```

于是:一个长驻会话在非 git 目录里跑过一次文件操作之后,`(None, False)` 就钉在缓存里了;
用户此后 `git init`,**本进程内 LSP 永远不会醒**。而文档恰恰教用户这么做:

`website/docs/user-guide/features/lsp.md:297-301 @ 863e313`

> **Editing a file outside any git repo**
>
> By design, LSP only runs inside a git repository. If the project isn't
> yet initialized, run `git init` to enable LSP diagnostics. Otherwise the
> in-process syntax-only fallback applies.

**实跑复现**(P2):

```console
=== P2 find_git_worktree negative cache survives a later `git init` ===
before git init: None
after  git init: None
after clear_cache(): /tmp/p2-v8hf2qac
```

判定:**■ + ▲**(代码缺陷,且与该标题下的整段文档矛盾——这一段三句话,前两句成立,
第三句「run `git init` to enable」在长驻进程里不成立)。
缓解路径存在但没被文档提到:`hermes lsp restart` → `shutdown_service()` → `LSPService.shutdown()` →
`clear_cache()`——可是那条路自己也是坏的(§9.2)。

### 2.3 ■ `nearest_root` 的 ceiling 差一层,项目根能逃出 git 工作树

`servers.py` 里所有走 `_root_or_workspace` 的解析器都把 ceiling 设成**工作区的父目录**:

`agent/lsp/servers.py:205-210 @ 863e313`

```python
    found = nearest_root(
        file_path,
        markers,
        excludes=excludes,
        ceiling=os.path.dirname(workspace) if workspace else None,
    )
```

而 `nearest_root` 的循环是「**先在 cur 上查 marker,再判断 cur 是不是 ceiling**」:

`agent/lsp/workspace.py:156-165 @ 863e313`

```python
        # Then check markers.
        for marker in markers_list:
            try:
                if (cur / marker).exists():
                    return str(cur)
            except OSError:
                continue
        # Stop conditions.
        if ceiling_path is not None and cur == ceiling_path:
            return None
```

两者相乘的结果:**工作区父目录那一层的 marker 是会被采信的**。
`/tmp/outer/pyproject.toml` + git 工作树在 `/tmp/outer/repo` 时,编辑 `repo/x.py` 得到的
LSP 工作区根是 `/tmp/outer`——**在 git 工作树之外**,而 §2.1 那道闸门的全部意义就是不越界。

**实跑复现**(P1):

```console
=== P1 nearest_root ceiling off-by-one ===
  git worktree   = /tmp/p1-ush8ttr8/outer/repo
  _root_python() = /tmp/p1-ush8ttr8/outer
  escaped worktree = True
```

后果不是崩,是**语言服务器被指着一个更大的目录索引**(pyright 在 home 目录级的 `pyproject.toml`
下会去索引整个 home),以及 `_clients` 的 key 变成工作树外的路径。判定 **■**(中等)。

### 2.4 exclude 语义:两次走查区分「没找到」和「被排除」

`nearest_root` 对「exclude 命中」和「什么都没找到」都返回 `None`,调用方要区分,于是重走一遍:

`agent/lsp/servers.py:211-224 @ 863e313`

```python
    if found is None and excludes:
        # Distinguish "no marker found" from "exclude hit": when
        # excludes are configured, None means gated off.
        # Re-check without excludes — if still None, we fall back to
        # workspace; if found, the exclude hit and we return None.
        recheck = nearest_root(
            file_path,
            markers,
            ceiling=os.path.dirname(workspace) if workspace else None,
        )
        if recheck is not None:
            return None  # exclude triggered
        return workspace
    return found or workspace
```

全仓只有一个 exclude 使用者:TypeScript 家族遇到 `deno.json` 就整个让位。

`agent/lsp/servers.py:828-842 @ 863e313`

```python
def _root_typescript(file_path: str, workspace: str) -> Optional[str]:
    return _root_or_workspace(
        file_path,
        workspace,
        [
            "package-lock.json",
            "bun.lockb",
            "bun.lock",
            "pnpm-lock.yaml",
            "yarn.lock",
            "package.json",
            "tsconfig.json",
        ],
        excludes=["deno.json", "deno.jsonc"],
    )
```

marker 的顺序是有意义的:**锁文件排在 `package.json` 前面**,这样 monorepo 里
`packages/foo/package.json` 不会把根抢到子包上(锁文件通常只在仓库根)。这是可迁移的设计细节。

---

## 3. 客户端:一个进程、一条 JSON-RPC(`protocol.py` + `client.py`)

### 3.1 分帧:196 行手写,不引 `vscode-jsonrpc`

`agent/lsp/protocol.py:54-63 @ 863e313`

```python
def encode_message(obj: dict) -> bytes:
    """Encode a JSON-RPC envelope as a Content-Length framed byte string.

    The body is encoded as compact UTF-8 JSON (no spaces between
    separators) — matches what ``vscode-jsonrpc`` emits and keeps the
    Content-Length count exact.
    """
    body = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body
```

读侧对「服务器行为不端」做了三道防御,都是重实现时容易漏的:

`agent/lsp/protocol.py:88-95 @ 863e313`

```python
        # Defensive cap against a server streaming headers without ever
        # emitting CRLF-CRLF.  Caps total header bytes at 8 KiB — a
        # well-behaved server fits in well under 200 bytes.
        header_bytes += len(line)
        if header_bytes > 8192:
            raise LSPProtocolError(
                "LSP header block exceeded 8 KiB without terminator"
            )
```

`agent/lsp/protocol.py:114-115 @ 863e313`

```python
    if n < 0 or n > 64 * 1024 * 1024:  # 64 MiB sanity cap
        raise LSPProtocolError(f"unreasonable Content-Length: {n}")
```

第三道是「干净 EOF vs 断帧」的区分:

`agent/lsp/protocol.py:80-87 @ 863e313`

```python
        except asyncio.IncompleteReadError as e:
            # EOF while reading headers.  If we hadn't started a header
            # block, treat as clean EOF; otherwise the framing is bad.
            if not e.partial and not headers:
                return None
            raise LSPProtocolError(
                f"unexpected EOF while reading LSP headers (partial={e.partial!r})"
            ) from e
```

「消息间的 EOF」返回 `None`(正常关闭),「头读一半的 EOF」抛协议错。这个区分让 `shutdown` 路径
不会打出一堆假告警。

异常分两类,分界线写得很清楚:`LSPProtocolError` = 线格式/信封坏了;`LSPRequestError` =
服务器**按协议**返回了错误响应。前者要杀连接,后者是正常业务结果。

### 3.2 进程 spawn:`start_new_session=True` 是一次事故的修复

`agent/lsp/client.py:306-324 @ 863e313`

```python
        try:
            # start_new_session=True detaches the LSP server into its own
            # process group / session. Without this, the LSP server inherits
            # the gateway's pgid (= TUI parent PID). When mcp_tool's
            # _kill_orphaned_mcp_children races with LSP spawn and sweeps the
            # gateway's child set, it captures the LSP PID, records the
            # inherited pgid, and killpg() then kills the TUI parent itself.
            # See tui_gateway_crash.log "killpg → SIGTERM received" stacks.
            self._proc = await asyncio.create_subprocess_exec(
                cmd[0],
                *cmd[1:],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self._cwd,
                start_new_session=True,
                creationflags=creationflags,
            )
```

**事故讲成故事**:MCP 层有个「清扫孤儿子进程」的例程,它按 pgid 批量 `killpg`。
LSP 服务器起来时继承了网关的 pgid,而网关的 pgid 恰好等于 TUI 父进程 PID;
清扫例程扫到这个新 PID、记下它继承来的 pgid、然后 `killpg` —— 于是**把 TUI 自己杀了**。
修法是让 LSP 服务器自成 session,不再和网关共享 pgid。`tools/mcp_tool.py:2486` 与
`tui_gateway/server.py:369` 各留了一条互指的注释。

stderr **必须**被抽干,否则管道缓冲区满了服务器就挂死:

`agent/lsp/client.py:330-334 @ 863e313`

```python
        # Drain stderr at debug level — if we don't, the pipe buffer
        # fills and the server hangs.
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        # Start the reader loop.
        self._reader_task = asyncio.create_task(self._reader_loop())
```

### 3.3 版本即新鲜度:防幽灵诊断的全部机制

`agent/lsp/client.py:155-161 @ 863e313`

```python
    version: int = 0
    text: str = ""
    push: List[Dict[str, Any]] = field(default_factory=list)
    pull: List[Dict[str, Any]] = field(default_factory=list)
    push_version: int = -1
    pull_version: int = -1
    seed_seen: bool = False
```

`agent/lsp/client.py:163-167 @ 863e313`

```python
    def fresh_push(self, version: Optional[int] = None) -> bool:
        return self.push_version >= (self.version if version is None else version)

    def fresh_pull(self, version: Optional[int] = None) -> bool:
        return self.pull_version >= (self.version if version is None else version)
```

**这就是全部**。`didChange` 把 `version` +1,所有 tag 更小的存储结果自动过期:

`agent/lsp/client.py:769-774 @ 863e313`

```python
            # Bumping the version is the whole invalidation story:
            # every stored result tagged with an older version is now
            # stale by definition (see _DocState).
            doc.version = new_version
            doc.text = text
            return new_version
```

服务器不回显版本号时的兜底也很讲究:

`agent/lsp/client.py:703-710 @ 863e313`

```python
        doc.seed_seen = True
        doc.push = diagnostics
        # Tag with the echoed document version when the server provides
        # one; otherwise credit the current version — a push observed
        # after we sent the change describes the changed content (or
        # newer).  Note doc.version is -1 for never-opened paths
        # (e.g. relatedDocuments spillover), keeping them unfresh.
        doc.push_version = version if isinstance(version, int) else doc.version
```

「观察到 push 的时刻 doc.version 是多少,就记多少」——这是一个**保守方向正确**的近似:
它可能把一个其实描述旧内容的 push 记成新的(如果服务器在我们发 didChange 之前就把 push 排好队了),
但不会把新的记成旧的。`seed_diagnostics_on_first_push` 就是补这个洞的:

`agent/lsp/client.py:694-701 @ 863e313`

```python
        if self._seed_first_push and not doc.seed_seen:
            # First push: seed the store WITHOUT a freshness tag.  It
            # arrives before the user-triggered didChange could've
            # produced fresh diagnostics, so it must never satisfy a
            # waiter — it's baseline data only.
            doc.seed_seen = True
            doc.push = diagnostics
            return
```

只有 typescript 打开了这个开关(`servers.py:290` 的 `seed_diagnostics_on_first_push=True`
与 `servers.py:984` 的 `seed_first_push=True`),因为 tsserver 会在 didOpen 之后立刻推一波
「项目级」诊断,那一波不该满足任何等待者。

**pull 侧用「发出请求时的版本」而不是「收到响应时的版本」打 tag**,这是对的:

`agent/lsp/client.py:821-823 @ 863e313`

```python
        abs_path = os.path.abspath(path)
        doc = self._docs.get(abs_path)
        sent_version = doc.version if doc else -1
```

如果请求在途时用户又改了文件,`doc.version` 已经涨了,`pull_version = sent_version` 就自动过期。

### 3.4 全量同步:即使服务器说支持增量也发整篇

`agent/lsp/client.py:749-761 @ 863e313`

```python
            content_changes: List[Dict[str, Any]]
            if self._sync_kind == 2:
                content_changes = [
                    {
                        "range": {
                            "start": {"line": 0, "character": 0},
                            "end": _end_position(old_text),
                        },
                        "text": text,
                    }
                ]
            else:
                content_changes = [{"text": text}]
```

设计理由写在模块 docstring:装成增量、实际发整篇替换,所有主流服务器都吃,省掉整套 range 记账。
**取舍**:大文件每次都全量过管道;换来的是零 range 记账、零「客户端与服务器文档不同步」的可能。
对一个「一次编辑跑一次」的 harness 而言这个换法是对的(编辑器要 IME 逐字符同步,harness 不用)。

### 3.5 ■ `_end_position` 用 Python 码点数列,但握手时宣告的是 utf-16

`agent/lsp/client.py:125-127 @ 863e313`

```python
    lines = text.splitlines(keepends=False)
    last_line = len(lines) - 1
    last_col = len(lines[-1]) if lines else 0
```

`agent/lsp/client.py:421 @ 863e313`

```python
                "general": {"positionEncodings": ["utf-16"]},
```

LSP 的 `Position.character` 默认单位是 **utf-16 码元**。`len()` 数的是 Python 码点。
最后一行含 BMP 外字符(emoji、部分 CJK 扩展)时两者不等:

```console
=== P3 _end_position counts Python chars, client advertises utf-16 ===
text            = 'a😀'
_end_position   = {'line': 0, 'character': 2}
utf-16 units    = 3
```

后果:`_sync_kind == 2` 时那个「替换全文」的 range 尾巴短了一格,**遵守增量语义的服务器会在文档末尾
留一个残字符**,此后它对该文件的诊断全部基于一份和磁盘不一致的内容。触发条件窄
(要求服务器 advertise 增量 + 旧内容最后一行有星体字符),但一旦触发是静默的、且会一直错下去。
判定 **■**(静态对读 + 单元级复现)。

顺带:`reporter.format_diagnostic` 把服务器给的 `character` 直接 +1 当列号,同样是 utf-16 语义,
对模型只是显示误差,不影响正确性。

### 3.6 服务器 → 客户端方向:只答 6 个方法,其余一律 method-not-found

`agent/lsp/client.py:217-224 @ 863e313`

```python
        self._request_handlers: Dict[str, Callable[[Any], Awaitable[Any]]] = {
            "window/workDoneProgress/create": self._handle_work_done_create,
            "workspace/configuration": self._handle_workspace_configuration,
            "client/registerCapability": self._handle_register_capability,
            "client/unregisterCapability": self._handle_unregister_capability,
            "workspace/workspaceFolders": self._handle_workspace_folders,
            "workspace/diagnostic/refresh": self._handle_diagnostic_refresh,
        }
```

**显式拒绝而不是沉默**很重要:LSP 服务器发的是**请求**(带 id),不回它会让服务器一直等。

`agent/lsp/client.py:592-595 @ 863e313`

```python
        handler = self._request_handlers.get(method)
        if handler is None:
            await self._send_error_response(req_id, ERROR_METHOD_NOT_FOUND, f"method not found: {method}")
            return
```

通知方向则相反——只处理 `publishDiagnostics`,其余静默丢弃(`client.py:604-607`),因为通知无人等。

`workspace/configuration` 的实现是「按点分段在 initializationOptions 里走一遍」:

`agent/lsp/client.py:636-643 @ 863e313`

```python
            cur: Any = self._init_options
            for part in str(section).split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    cur = None
                    break
            out.append(cur)
```

### 3.7 ContentModified 重试

`agent/lsp/client.py:537-544 @ 863e313`

```python
        for attempt in range(MAX_CONTENT_MODIFIED_RETRIES + 1):
            try:
                return await asyncio.wait_for(self._send_request(method, params), timeout=timeout)
            except LSPRequestError as e:
                if e.code == ERROR_CONTENT_MODIFIED and attempt < MAX_CONTENT_MODIFIED_RETRIES:
                    await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                    continue
                raise
```

`-32801 ContentModified` 的语义是「你问的时候文档正在变,重问」。退避 0.5/1.0/2.0 秒。
注意这个循环**只在 pull 诊断路径上用**(`_pull_document_diagnostics`),而它的单次超时是 3s
(`DIAGNOSTICS_REQUEST_TIMEOUT`),最坏情况 4 次请求 + 3.5s 睡眠 = 15.5s,**远超外层预算**——
不过 pull 失败是静默 no-op,所以只会浪费预算不会报错。

---

## 4. 服务层:同步世界与异步世界的桥(`manager.py` 744 行)

### 4.1 一个后台线程跑一个事件循环

`agent/lsp/manager.py:88-99 @ 863e313`

```python
    def _run_forever(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            try:
                loop.close()
            except Exception:  # noqa: BLE001
                pass
```

`agent/lsp/manager.py:111-118 @ 863e313`

```python
        fut = safe_schedule_threadsafe(coro, self._loop)
        if fut is None:
            raise RuntimeError("background loop not running")
        try:
            return fut.result(timeout=timeout)
        except Exception:
            fut.cancel()
            raise
```

这是整片最重要的结构决定:**`tools/file_operations.py` 是同步的,LSP 客户端是异步的**,
中间用一个 daemon 线程 + `run_coroutine_threadsafe` 打通。
`fut.result(timeout=...)` 就是「外层超时」的来源,而 `except Exception: fut.cancel()`
就是「超时后把协程取消掉」的来源——§4.4 的进程泄漏正出在这个 cancel 上。

### 4.2 客户端池、broken-set、spawn 去重

`agent/lsp/manager.py:553-567 @ 863e313`

```python
        key = (srv.server_id, per_server_root)
        if key in self._broken:
            return None
        with self._state_lock:
            client = self._clients.get(key)
            if client is not None and client.is_running:
                self._last_used[key] = time.time()
                eventlog.log_active(srv.server_id, per_server_root)
                return client
            spawning = self._spawning.get(key)
        if spawning is not None:
            try:
                return await spawning
            except Exception:  # noqa: BLE001
                return None
```

`_spawning` 是一张「正在起」的 future 表:并发的两次编辑不会起两个 pyright。
broken-set 是**只进不出**的(只有 `_shutdown_async` 会 `clear()`),这是有意的:
一个起不来的服务器,每次编辑都重付一遍超时代价比不做诊断更糟。

### 4.3 ■ 外层预算 8s vs 内层预算 10s:`wait_mode: full` 会把服务器打成 broken

`agent/lsp/manager.py:311-314 @ 863e313`

```python
            # Outer join budget must exceed the inner wait budget or a
            # slow-but-alive server gets falsely marked broken.
            t = max(8.0, self._wait_timeout + 3.0)
            diags = self._loop.run(self._snapshot_async(file_path), timeout=t)
```

注释把不变量说清楚了:**外层必须大于内层**。但同一个文件里,基线快照那一路
**根本没把用户配置的 `wait_timeout` 传下去**:

`agent/lsp/manager.py:485-486 @ 863e313`

```python
            version = await client.open_file(file_path, language_id=language_id_for(file_path))
            fresh = await client.wait_for_diagnostics(file_path, version, mode=self._wait_mode)
```

对比写入后那一路,它是传的:

`agent/lsp/manager.py:513-515 @ 863e313`

```python
            fresh = await client.wait_for_diagnostics(
                file_path, version, mode=self._wait_mode, timeout=self._wait_timeout
            )
```

`timeout=None` 时内层预算由 mode 决定:

`agent/lsp/client.py:881-884 @ 863e313`

```python
        if timeout is not None and timeout > 0:
            budget = timeout
        else:
            budget = DIAGNOSTICS_FULL_WAIT if mode == "full" else DIAGNOSTICS_DOCUMENT_WAIT
```

`agent/lsp/client.py:77-87 @ 863e313`

```python
# Timeouts (seconds) — mirror OpenCode's constants, scaled to seconds.
INITIALIZE_TIMEOUT = 45.0
DIAGNOSTICS_DOCUMENT_WAIT = 5.0
DIAGNOSTICS_FULL_WAIT = 10.0
DIAGNOSTICS_REQUEST_TIMEOUT = 3.0
PUSH_DEBOUNCE = 0.15
SHUTDOWN_GRACE = 1.0  # seconds between SIGTERM and SIGKILL

# Retry policy for transient ContentModified errors.
MAX_CONTENT_MODIFIED_RETRIES = 3
RETRY_BASE_DELAY = 0.5  # 0.5, 1.0, 2.0 — exponential
```

**算术**:`wait_mode: full`(文档与 `DEFAULT_CONFIG` 都列为合法值)+ 默认 `wait_timeout: 5.0`
⇒ 外层 `max(8.0, 8.0) = 8.0s`,内层 `10.0s`。外层先炸,`_loop.run` 抛 TimeoutError,
被 `snapshot_baseline` 的 `except Exception` 抓到,直接 `_mark_broken_for_file`:

`agent/lsp/manager.py:316-319 @ 863e313`

```python
        except Exception as e:  # noqa: BLE001
            logger.debug("baseline snapshot failed for %s: %s", file_path, e)
            self._mark_broken_for_file(file_path, e)
            self._delta_baseline[os.path.abspath(file_path)] = []
```

**实跑复现**(P6,用仓库自带的 `tests/agent/lsp/_mock_lsp_server.py` 的 `stale` 脚本
——它在 didChange 后故意不推诊断,模拟慢 tsserver):

```console
=== P6 wait_mode='full' + default wait_timeout => snapshot outer(8s) < inner(10s) ===
  wait_mode=document  2nd snapshot took  5.00s  broken=[]  enabled_for=True
lsp[pyright] spawn/initialize failed for /tmp/p6-full-iifn16_g: TimeoutError: 
  wait_mode=full      2nd snapshot took  8.00s  broken=[('pyright', '/tmp/p6-full-iifn16_g')]  enabled_for=False
```

**只改一个文档化的配置值,LSP 就对这个工作区永久关闭了**,而且用户看到的唯一线索是一行
`spawn/initialize failed ... TimeoutError:`(异常消息为空)——它把「等诊断超时」误报成了
「spawn/初始化失败」。判定 **■**(高)。

顺带一条独立的 **■**:`_snapshot_async` 忽略 `lsp.wait_timeout` 本身就是缺陷(配置只对一半路径生效)。

```console
=== P9 _snapshot_async ignores lsp.wait_timeout (uses mode default) ===
  lsp.wait_timeout = 1.0
  snapshot_baseline blocked        5.00s  (mode default 5s -> config ignored)
  get_diagnostics_sync blocked     1.00s  (config honoured)
```

### 4.4 ■ 冷启动超过 8s 同样被打成 broken,且 `INITIALIZE_TIMEOUT = 45` 形同虚设

`_snapshot_async` 里 spawn 与等待共用同一个外层 8s 预算:

`agent/lsp/manager.py:480-486 @ 863e313`

```python
    async def _snapshot_async(self, file_path: str) -> List[Dict[str, Any]]:
        client = await self._get_or_spawn(file_path)
        if client is None:
            return []
        try:
            version = await client.open_file(file_path, language_id=language_id_for(file_path))
            fresh = await client.wait_for_diagnostics(file_path, version, mode=self._wait_mode)
```

也就是说:客户端层给 initialize 留了 45s,但**从 file_operations 进来的每一条路都只有 8s**
(除非用户把 `wait_timeout` 调到 ≥ 5 以上;外层 = `wait_timeout + 3`)。而文档自己说:

`website/docs/user-guide/features/lsp.md:213-217 @ 863e313`

> LSP servers are **lazy-spawned** on first use. Editing a Python file
> in a project that's never seen `.py` traffic spawns pyright; the
> spawn takes 1-3 seconds for most servers (rust-analyzer can take 10+
> on a cold project). Subsequent edits in the same workspace re-use
> the running server.

**实跑复现**(P10,自写的 mock 服务器,initialize 前 sleep 9s):

```console
=== P10 cold spawn slower than the outer 8s budget => pair marked broken ===
  INITIALIZE_TIMEOUT (client) = 45.0s ; outer snapshot budget = max(8, 5+3) = 8.0s
lsp[pyright] spawn/initialize failed for /tmp/p10-8bjct1lk: TimeoutError: 
  snapshot_baseline blocked  8.00s
  broken      = [('pyright', '/tmp/p10-8bjct1lk')]
  enabled_for = False  <- LSP now off for this workspace
  2nd snapshot after broken: 0.000s (short-circuited)
  spawned server pid 10585 still alive 2s after the cancelled spawn: True
```

**同一个实验暴露第二个 ■:被取消的 spawn 会漏一个语言服务器进程。**
根因是 `start()` 只捕获 `Exception`,而 `fut.cancel()` 传进来的是 `CancelledError`(BaseException):

`agent/lsp/client.py:274-281 @ 863e313`

```python
        try:
            await self._spawn()
            await self._initialize()
            self._state = "running"
        except Exception:
            self._state = "error"
            await self._cleanup_process()
            raise
```

于是 `_cleanup_process()`(terminate → 1s → kill)**不执行**;而清扫兜底那一侧也捞不到它,
因为客户端从没被放进 `_clients`:

`agent/lsp/manager.py:451-453 @ 863e313`

```python
        with self._state_lock:
            client = self._clients.pop(key, None)
            self._last_used.pop(key, None)
```

`_clients[key] = client` 只在 `client.start()` 成功之后才发生(`manager.py:608-610`),
被取消的那次永远走不到。再叠上 §3.2 的 `start_new_session=True`——它连父进程组都不在了。
判定 **■**(高:一个冷启动慢的 rust-analyzer 会既关掉诊断、又留下一个几百 MB 的孤儿进程)。

### 4.5 ■ 等待循环在「服务器不支持 pull」时空转,2 秒发了 6855 次请求

`agent/lsp/client.py:888-900 @ 863e313`

```python
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return False

            # Concurrent: document pull + push wait.
            pull_task = asyncio.create_task(self._pull_document_diagnostics(abs_path))
            push_task = asyncio.create_task(self._wait_for_fresh_push(abs_path, version, remaining))
            done, pending = await asyncio.wait(
                {pull_task, push_task},
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
```

`asyncio.wait(..., FIRST_COMPLETED)` 只要**任一个**完成就返回。服务器不支持 pull 时,
`_pull_document_diagnostics` 收到 `-32601` 立即静默返回:

`agent/lsp/client.py:833-835 @ 863e313`

```python
        except (LSPRequestError, LSPProtocolError, asyncio.TimeoutError) as e:
            logger.debug("[%s] document diagnostic pull failed: %s", self.server_id, e)
            return
```

于是每轮:发一次 pull → 立刻被拒 → `asyncio.wait` 返回 → 取消刚建的 push 等待 → 判定不新鲜 → 再来。
**push 等待被反复取消重建,debounce 逻辑等于失效**,而 pull 请求以往返速度刷屏。

**实跑复现**(P7,`stale` 脚本对 `textDocument/diagnostic` 返回 -32601):

```console
=== P7 pull/push wait loop spins when server rejects textDocument/diagnostic ===
  fresh=False elapsed=2.00s  pull attempts in a 2s wait = 6855
```

受影响面:任何 push-only 的服务器(clangd 传统上不支持 pull;仓库自带的 mock 里
`stale` / `slow_push` 两个脚本正是照这个形态写的)。判定 **■**(中高:CPU + 管道洪水;
在真实服务器上还可能把服务器自身拖慢,让「等不到新鲜诊断」变成自我实现的预言)。

修法很直接:pull 失败后应对该文档打上「本服务器不支持 pull」标记并退出 pull 分支,
或者对 pull 加一个最小间隔。

### 4.6 ■ 基线回滚前进用错了 key

`agent/lsp/manager.py:524-530 @ 863e313`

```python
    async def _current_diags_async(self, file_path: str) -> List[Dict[str, Any]]:
        ws, gated = resolve_workspace_for_file(file_path)
        srv = find_server_for_file(file_path)
        if not (ws and gated and srv):
            return []
        with self._state_lock:
            client = self._clients.get((srv.server_id, ws))
```

而客户端是按**逐服务器根**入池的:

`agent/lsp/manager.py:546 @ 863e313`

```python
        per_server_root = srv.resolve_root(file_path, ws_root)
```

`agent/lsp/manager.py:553 @ 863e313`

```python
        key = (srv.server_id, per_server_root)
```

两者在「项目 marker 就在 git 根」时恰好相等,所以平时看不出来;
一旦 marker 在子目录(monorepo、`packages/*/package.json`、`sub/pyproject.toml`),
查找必然落空,基线的向前滚动静默变成 no-op:

`agent/lsp/manager.py:403-408 @ 863e313`

```python
            try:
                fresh = self._loop.run(self._current_diags_async(file_path), timeout=2.0) or []
            except Exception:  # noqa: BLE001
                fresh = []
            if fresh:
                self._delta_baseline[abs_path] = fresh
```

**实跑复现**(P8:git 根 `/tmp/p8-*`,逐服务器根 `/tmp/p8-*/sub`):

```console
=== P8 _current_diags_async keys on the git root, not the per-server root ===
  diagnostics reported     : 1
  client keys              : [('pyright', '/tmp/p8-97ipwd2q/sub')]
  delta baseline after call: {}
  (roll-forward looked up key: ('pyright', '/tmp/p8-97ipwd2q') )
```

**实际影响有限**(因为 `snapshot_baseline` 在每次写入前都会重建基线),
所以这是一条**潜伏缺陷**:任何一个不经 `snapshot_baseline` 就连续调用 `get_diagnostics_sync`
的新调用方,都会拿到没滚动过的基线。判定 **■**(低-中,但确定)。

顺带 **■(低)**:`if fresh:` 意味着「这次没有诊断」不会把基线清空——文件变干净后基线仍留着旧诊断。

### 4.7 空闲回收:一个「不能杀死自己」的循环

`agent/lsp/manager.py:61-62 @ 863e313`

```python
DEFAULT_IDLE_TIMEOUT = 600  # seconds; servers idle for >10min get reaped
MIN_IDLE_TIMEOUT = 30  # floor for config values; must exceed any per-op wait budget
```

`agent/lsp/manager.py:217-222 @ 863e313`

```python
        if 0 < idle_timeout < MIN_IDLE_TIMEOUT:
            # A timeout below the per-operation wait budget could reap a
            # client mid-flight; the resulting outer timeout would then
            # mark the (server, workspace) pair broken for the process
            # lifetime.  Clamp to a safe floor (0 still disables).
            idle_timeout = MIN_IDLE_TIMEOUT
```

注意这条钳位的理由**正是 §4.3 那个缺陷的另一个入口**——作者已经知道「外层超时 ⇒ 永久 broken」
这个放大效应很危险,在回收器这一侧堵了,却漏了 `wait_mode: full` 那一侧。

`agent/lsp/manager.py:640-646 @ 863e313`

```python
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                # A transient sweep error must not kill the reaper —
                # otherwise one bad shutdown permanently re-opens the
                # unbounded-accumulation leak this loop exists to fix.
                logger.debug("LSP idle reaper sweep error: %s", e)
```

「一次扫描失败不能杀死回收器」——把 `CancelledError` 单独放行、其余吞掉,是长循环的标准写法。

`_touch` 的成员判定同样是防「回收与使用交叉」的:

`agent/lsp/manager.py:629-632 @ 863e313`

```python
        key = (client.server_id, client.workspace_root)
        with self._state_lock:
            if key in self._clients:
                self._last_used[key] = time.time()
```

不加这个 `if`,一个刚被回收器 pop 掉的 key 会被 `_touch` 重新写回 `_last_used`,变成永不清理的孤儿条目。

### 4.8 「无判决」与「干净」必须分开

`agent/lsp/manager.py:375-384 @ 863e313`

```python
        if diags is None:
            # The server is alive but never produced diagnostics for the
            # post-edit content within the wait budget (common for
            # tsserver on large projects).  Report "no data" rather than
            # whatever stale state is in the stores — surfacing the
            # previous edit's errors as if they were current is the
            # ghost-diagnostics bug.  The server is NOT marked broken:
            # slow is not dead, and the next edit may well succeed.
            eventlog.log_timeout(server_id, file_path, kind="fresh diagnostics")
            return []
```

`_open_and_wait_async` 返回 `None`(无判决)vs `[]`(检查过、干净)是整条链上语义最细的一处区分,
`wait_for_diagnostics` 的 docstring 专门警告过调用方:

`agent/lsp/client.py:873-877 @ 863e313`

```python
        Returns ``True`` when *fresh* diagnostics arrived (a push at
        or after our didChange, or a pull answered after it) and
        ``False`` on timeout.  Callers must treat ``False`` as "no
        data", NOT as "no errors" — the diagnostic stores may still
        hold stale entries from the previous edit at that point.
```

**注意最终对模型仍是 `[]`**——「无判决」和「干净」在 `WriteResult` 里长得一样
(都是没有 `lsp_diagnostics` 字段)。区别只落在日志。这是一个有意的取舍:
不给模型增加一个「我不知道」的状态,免得它去纠结。

---

## 5. `range_shift.py`:它解决的到底是什么

**它不是并发竞态,是坐标系竞态。** 场景:

```text
编辑前 foo.py:
  1  import os          <- 基线诊断 A: "os imported but unused" @ line 0
  ...
  40 def f(): return undefined_name   <- 基线诊断 B @ line 39

模型在第 10 行插入了 5 行新代码。

编辑后:诊断 B 现在报在 line 44。
delta 过滤的 key 含 range:
  基线里的 B = (severity, code, source, message, 39:x-39:y)
  新诊断里的 B = (severity, code, source, message, 44:x-44:y)
两者 key 不等 => B 被当成「本次编辑引入的新错误」报给模型。
```

`agent/lsp/range_shift.py:5-9 @ 863e313`

```python
LSPService delta filter subtracts the pre-edit baseline from the
post-edit diagnostics keyed on ``(severity, code, source, message,
range)`` — without an adjustment, the shifted-but-otherwise-identical
diagnostics look brand-new and the agent gets flooded with noise.
```

修法是 git blame / unified diff 用的老办法:用 `difflib.SequenceMatcher.get_opcodes()`
造一张分段线性的「编辑前行号 → 编辑后行号」映射,**在做集合差之前**把基线搬到编辑后坐标系。

`agent/lsp/range_shift.py:68-79 @ 863e313`

```python
        for tag, i1, i2, j1, j2 in opcodes:
            if i1 <= line < i2:
                if tag == "equal":
                    # Pre-line N → post-line (N - i1 + j1).
                    return line - i1 + j1
                if tag == "delete":
                    # Pre-line is in a deleted region — no post counterpart.
                    return None
                if tag == "replace":
                    # Replace == delete + insert; the pre-line has no
                    # post counterpart in any meaningful sense.  Drop.
                    return None
```

**三个语义判断值得记住:**

1. `delete` → `None` → 该基线诊断被丢弃。理由:那几行没了,它描述的问题也没了。
   丢弃是**保守方向正确**的:基线变小 ⇒ 过滤掉的更少 ⇒ 最坏是多报,不会漏报。
2. `replace` 也 → `None`。作者在注释里承认这是个判断而非事实(「in any meaningful sense」)。
   代价:在被替换区域里**原本就存在、且编辑后仍然存在**的诊断会被当成新的报出来。
3. 越过最后一个 opcode(`line >= len(pre_lines)`)时锚到文末:

`agent/lsp/range_shift.py:84-86 @ 863e313`

```python
        # Past the last opcode region (line >= len(pre_lines)).
        # Anchor at end of post.
        return max(0, len(post_lines) - 1) if post_lines else None
```

**取舍写在模块 docstring 里,而且交代了上一版方案:**

`agent/lsp/range_shift.py:17-21 @ 863e313`

```python
Trade-off vs. dropping range from the key entirely (the previous
fix): preserves the "new instance of an identical error at a
different line" signal — if the model introduces a second instance
of the same error class at a different location, that one will be
surfaced as new instead of swallowed by content-only dedup.
```

也就是说,更简单的做法(把 range 从 key 里删掉)会让「同一类错在新位置又出现一次」被吞掉。
这是一个真实的信号损失,值 149 行代码去换。**重实现时这一条最值得抄。**

代价则是 `_diag_key` 两处手抄:

`agent/lsp/manager.py:724-727 @ 863e313`

```python
    Mirrors :func:`agent.lsp.client._diagnostic_key`; intentionally
    identical so the two layers agree on diagnostic identity.
    """
    rng = d.get("range") or {}
```

`manager._diag_key`(用于跨编辑 delta)与 `client._diagnostic_key`(用于 push/pull 合并去重)
是**逐字重复的两份实现**,靠注释维持一致。这是典型的「同一份知识写了两遍」——一处改了另一处不会报错。
判定 **◇**(结构债,不是缺陷)。

调用侧只在 pre/post 都拿得到且确实不同时才建映射:

`tools/file_operations.py:2152-2157 @ 863e313`

```python
        if pre_content is not None and post_content is not None and pre_content != post_content:
            try:
                from agent.lsp.range_shift import build_line_shift
                line_shift = build_line_shift(pre_content, post_content)
            except Exception:  # noqa: BLE001
                line_shift = None
```

---

## 6. 诊断怎么被裁成模型吃得下的量(`reporter.py` 130 行)

### 6.1 三道闸门 + 一层净化

`agent/lsp/reporter.py:15-20 @ 863e313`

```python
# agent.  Lift this in config under ``lsp.severities`` if needed.
SEVERITY_NAMES = {1: "ERROR", 2: "WARN", 3: "INFO", 4: "HINT"}
DEFAULT_SEVERITIES = frozenset({1})  # ERROR only

MAX_PER_FILE = 20
MAX_TOTAL_CHARS = 4000
```

`agent/lsp/reporter.py:99-107 @ 863e313`

```python
    filtered = [d for d in diagnostics if (d.get("severity") or 1) in severities]
    if not filtered:
        return ""
    limited = filtered[:max_per_file]
    extra = len(filtered) - len(limited)
    lines = [format_diagnostic(d) for d in limited]
    body = "\n".join(lines)
    if extra > 0:
        body += f"\n... and {extra} more"
```

**取舍**:只留 severity=1(ERROR),warning/info/hint 全丢。理由写在 `reporter.py:14-15`
的注释里:会淹掉 agent。代价是 pyright 的 `reportUnusedImport` 之类(默认 warning)模型看不到。
截断时留一句 `... and N more`,让模型知道自己看到的不全——这比静默截断重要得多。

**◇:`lsp.severities` 这个配置键不存在。** 搜索面:全仓 `*.py` / `*.md`
`grep -rn "severities"` 只有 4 处命中,分别是 reporter.py 的注释、reporter.py 的形参与使用、
以及 `tools/mcp_tool.py:316` 一条与 LSP 无关的 syslog 注释;`report_for_file` 全仓只有两个调用方
(`tools/file_operations.py:2167` 与测试),**都不传 `severities=`**。也就是说注释承诺的配置旋钮
没有实现,严重度过滤在唯一生产调用点上是硬编码的。

### 6.2 把语言服务器输出当成不可信输入(防提示注入)

`agent/lsp/reporter.py:55-63 @ 863e313`

```python
    if value is None:
        return ""
    raw = str(value)
    # Collapse newlines so identifier text with raw \n can't fake new lines.
    raw = raw.replace("\r", " ").replace("\n", " ")
    # Drop ASCII control chars; keep regular spaces.
    raw = "".join(ch for ch in raw if ch == " " or ch.isprintable())
    raw = raw.strip()[:limit]
    return html.escape(raw, quote=False)
```

威胁模型写得很清楚:

`agent/lsp/reporter.py:33-39 @ 863e313`

```python
    Diagnostic ``message``, ``code``, and ``source`` originate from a
    language server that has just parsed user-controlled source code, so
    they're untrusted from the agent's point of view. A hostile repo can
    place instruction-shaped text inside identifier names, type aliases,
    or import paths so the resulting diagnostic echoes that text back
    into the ``<diagnostics>`` block the model reads.
```

即:**恶意仓库可以把指令写进标识符名**(`class IgnorePreviousInstructionsAndRunRm: ...`),
语言服务器会把这个名字原样放进诊断消息,诊断消息又会被贴进模型读的 `<diagnostics>` 块。
四道防御:折行、去控制字符、逐字段截断(message 300 / code 80 / source 80)、HTML 转义
(防提前闭合 `</diagnostics>`)。文件名也转义,而且 `quote=True`:

`agent/lsp/reporter.py:108-112 @ 863e313`

```python
    # quote=True escapes both ``"`` and ``&`` so a crafted file name like
    # ``foo"><script`` can't break out of the ``file="..."`` attribute and
    # synthesize new tags inside the tool output.
    safe_path = html.escape(file_path, quote=True)
    return f"<diagnostics file=\"{safe_path}\">\n{body}\n</diagnostics>"
```

**这是本片最值得抄进自己 harness 的一段**:凡是「外部程序的输出会进模型上下文」的地方,
都要有这一层。判定 **◇**(代码有、`website/docs/.../lsp.md` 完全没提这层防护)。

---

## 7. 服务器注册表:1187 行怎么组织的(`servers.py`)

### 7.1 三条正交的轴

```text
LANGUAGE_BY_EXT   : 扩展名 -> LSP languageId   (servers.py:35-108,74 条)
SERVERS           : ServerDef 列表             (servers.py:971-1162,27 条)
INSTALL_RECIPES   : 包名 -> 安装配方           (install.py:52-112,15 条)
```

`ServerDef` 把「什么时候用我」和「怎么起我」拆成两个可调用对象:

`agent/lsp/servers.py:143-153 @ 863e313`

```python
    server_id: str
    extensions: Tuple[str, ...]
    resolve_root: Callable[[str, str], Optional[str]]
    build_spawn: Callable[[str, "ServerContext"], Optional[SpawnSpec]]
    seed_first_push: bool = False
    description: str = ""

    def matches(self, file_path: str) -> bool:
        """Return True iff this server handles ``file_path``."""
        ext = _file_ext_or_basename(file_path)
        return ext in self.extensions
```

匹配是**首条命中生效**的线性扫描:

`agent/lsp/servers.py:1165-1170 @ 863e313`

```python
def find_server_for_file(file_path: str) -> Optional[ServerDef]:
    """Return the registry entry that handles ``file_path``, or None."""
    for srv in SERVERS:
        if srv.matches(file_path):
            return srv
    return None
```

27 条线性扫描,每次文件操作跑一遍——27 次元组 `in` 判断,可以忽略。
**一个文件只会有一个服务器**:没有「pyright + ruff 一起跑」这种叠加。这是相对编辑器的一个明显简化。

### 7.2 扩展名 vs 基名

`agent/lsp/servers.py:184-188 @ 863e313`

```python
    base = os.path.basename(path)
    _root, ext = os.path.splitext(base)
    if ext:
        return ext.lower()
    return base
```

「有扩展名就用扩展名(小写),没有就用整个基名」——照抄 OpenCode 的 `path.parse(file).ext || file`。
所以 `Dockerfile` 能匹配(注册表里 `extensions=(".dockerfile", "Dockerfile")`),
但 **`Dockerfile.dev`(扩展名 `.dev`)和小写 `dockerfile` 都匹配不上**;基名分支还**没有小写化**,
与扩展名分支不对称。

**实跑复现**(P4):

```console
  a.ksh            server=bash-language-server     languageId=plaintext
  a.sh             server=bash-language-server     languageId=shellscript
  Dockerfile       server=dockerfile-ls            languageId=plaintext
  dockerfile       server=None                     languageId=plaintext
  Dockerfile.dev   server=None                     languageId=plaintext
```

**◇:两处 `languageId` 缺口。** bash 服务器声明了 `.ksh`(`servers.py:1031`),
但 `LANGUAGE_BY_EXT` 里没有 `.ksh`;`Dockerfile` 基名也不在表里(表里只有 `.dockerfile`)。
两者都退化成 `"plaintext"`。而模块自己的注释说这会出事:

`agent/lsp/servers.py:32-34 @ 863e313`

```python
# Language IDs per LSP spec.  Used for ``textDocument/didOpen.languageId``.
# Most servers don't care exactly, but a few (typescript-language-server,
# vue-language-server) refuse files with the wrong ID.
```

### 7.3 加一个新语言要动几处

按现有形态数(以 gopls 为样板):

| # | 位置 | 必需? | 例 |
|---|---|---|---|
| 1 | `agent/lsp/servers.py:35` 的 `LANGUAGE_BY_EXT`:`".go": "go",` | 必需(否则 languageId=plaintext) | `".go": "go"` |
| 2 | `agent/lsp/servers.py:845` 的 `_root_go` | 必需(可复用 `_root_or_workspace`) | marker 列表 |
| 3 | `agent/lsp/servers.py:294` 的 `_spawn_gopls` | 必需 | `_resolve_override` → `_which` → `try_install` 三段式 |
| 4 | `SERVERS` 列表里加一条,如 `agent/lsp/servers.py:1009`:`server_id="gopls",` | 必需 | 见 §7.1 |
| 5 | `agent/lsp/install.py:98` 的 `INSTALL_RECIPES` | 仅当要自动安装 | `{"strategy": "go", ...}` |
| 6 | `agent/lsp/cli.py:268` 的 `aliases` | 仅当 server_id ≠ 配方 key | `"typescript": "typescript-language-server"` |

**即 3~6 处,分布在 3 个文件。** 第 3 项那 27 个 spawn 构造器几乎逐字重复(样板见下),
是本片最大的一块可压缩冗余:

`agent/lsp/servers.py:294-307 @ 863e313`

```python
def _spawn_gopls(root: str, ctx: ServerContext) -> Optional[SpawnSpec]:
    bin_path = _resolve_override(ctx, "gopls") or _which("gopls")
    if bin_path is None:
        from agent.lsp.install import try_install
        bin_path = try_install("gopls", ctx.install_strategy)
        if bin_path is None:
            return None
    return SpawnSpec(
        command=[bin_path],
        workspace_root=root,
        cwd=root,
        env=ctx.env_overrides.get("gopls", {}),
        initialization_options=ctx.init_overrides.get("gopls", {}),
    )
```

27 个里有 12 个是这个形状的逐字复制(只换 id、二进制名、args)。**◇**(可用一个声明式表 + 一个通用构造器
压到 ~150 行;现在的写法换来的是「每个服务器可以有任意特判」——pyright 找 venv、
intelephense 关遥测、bash 提醒装 shellcheck、PSES 整套 bootstrap,确实有 5 个用上了这个自由度)。

### 7.4 有特判的那 5 个

**pyright 找项目 venv**(否则它会用 PATH 上的 python,几乎肯定不是用户的 venv):

`agent/lsp/servers.py:264-274 @ 863e313`

```python
def _detect_python(root: str) -> Optional[str]:
    candidates = []
    if os.environ.get("VIRTUAL_ENV"):
        candidates.append(os.environ["VIRTUAL_ENV"])
    candidates.extend([os.path.join(root, ".venv"), os.path.join(root, "venv")])
    for v in candidates:
        for sub in ("bin/python", "bin/python3", "Scripts/python.exe"):
            p = os.path.join(v, sub)
            if os.path.exists(p):
                return p
    return None
```

**pyright 的 CLI 与 langserver 是两个二进制**,拿到 CLI 要换成兄弟:

`agent/lsp/servers.py:241-246 @ 863e313`

```python
    # If we got the cli ``pyright``, the langserver is its sibling.
    base = os.path.basename(bin_path)
    if base in {"pyright", "pyright.exe"}:
        sibling = os.path.join(os.path.dirname(bin_path), "pyright-langserver")
        if os.path.exists(sibling):
            bin_path = sibling
```

**bash-language-server 的「装了但永远不报错」陷阱**——它把诊断委托给 `shellcheck`:

`agent/lsp/servers.py:352-363 @ 863e313`

```python
    # bash-language-server delegates diagnostics to ``shellcheck``.  Without
    # it on PATH the server starts and accepts requests but never reports
    # any problems — to the user it looks like a working integration that
    # never finds bugs.  Warn once so the gap is visible.
    global _BASH_SHELLCHECK_WARNED
    if not _BASH_SHELLCHECK_WARNED and _which("shellcheck") is None:
        _BASH_SHELLCHECK_WARNED = True
        logger.warning(
            "bash-language-server: shellcheck not found on PATH — "
            "diagnostics will be empty until shellcheck is installed "
            "(apt: shellcheck, brew: shellcheck, scoop: shellcheck)."
        )
```

这是很好的设计意识:**「看起来在工作但永远不报错」比「明确坏掉」更糟**,所以专门造了一条告警,
还在 `hermes lsp status` 里加了一整个 "Backend warnings" 段落(`cli.py:277-299`)去暴露它。

**intelephense 关遥测**(`servers.py:412`),**terraform-ls 开 `validateOnSave`**(`servers.py:456-461`)。

**PowerShellEditorServices** 是唯一不是「一个二进制」的:它是一个 pwsh 模块包,要靠 bootstrap 脚本拉起。

`agent/lsp/servers.py:766-774 @ 863e313`

```python
    inner = (
        f"& '{start_script}' "
        f"-BundledModulesPath '{bundle}' "
        f"-LogPath '{log_path}' "
        f"-SessionDetailsPath '{session_path}' "
        f"-FeatureFlags @() -AdditionalModules @() "
        f"-HostName Hermes -HostProfileId hermes -HostVersion 1.0.0 "
        f"-Stdio -LogLevel Normal"
    )
```

**◇(安全形态)**:bundle 路径来自配置 / `PSES_BUNDLE_PATH` 环境变量 / `HERMES_HOME`,
被直接 f-string 插进单引号里当 PowerShell 脚本执行。路径里出现单引号即可闭合并注入命令。
可信度取决于「谁能写配置/环境变量」——在本项目的威胁模型下配置是可信的,所以定级低,
但重实现时应该用参数数组而不是拼脚本字符串。

`_find_pses_bundle` 的四级查找顺序(`servers.py:703-730`)是一个很好的「手工安装件」定位样板:
配置 → initializationOptions → 环境变量 → 约定的 staging 目录,并且**同时接受包根与内层模块目录**。

---

## 8. 安装:会联网,不校验(`install.py` 412 行)

### 8.1 会不会联网 —— 会,而且是同步阻塞在第一次编辑上

`agent/lsp/install.py:268-276 @ 863e313`

```python
        proc = subprocess.run(
            [npm, "install", "--prefix", str(staging), "--silent", "--no-fund", "--no-audit", *install_targets],
            check=False,
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=300,
            stdin=subprocess.DEVNULL,
            creationflags=windows_hide_flags(),
        )
```

`agent/lsp/install.py:317-326 @ 863e313`

```python
        proc = subprocess.run(
            [go, "install", pkg],
            check=False,
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=600,
            env=env,
            stdin=subprocess.DEVNULL,
            creationflags=windows_hide_flags(),
        )
```

**时序问题**:这两个 `subprocess.run` 是**同步**的,而它们是从 `build_spawn` 里被调用的,
`build_spawn` 又是从 `_get_or_spawn` 这个协程里调用的——**它们会阻塞 LSP 的后台事件循环线程
最长 300s / 600s**。而外层 `_loop.run` 的预算是 8s。所以第一次触碰一个未安装的语言时:
外层 8s 就超时 → `_mark_broken_for_file` → 这对 pair 立刻进 broken-set;
安装还在后台继续跑,装完了也**不会被使用**(broken-set 只进不出)。
判定 **■(推定,未实跑)**——见 §11,我没有网络也没装 npm/go 去验证,但三段代码的组合是明确的。
`stdin=subprocess.DEVNULL` 至少保证了它不会因为交互提示挂死。

### 8.2 校验 —— hermes 自己什么都不做

`agent/lsp/install.py:98 @ 863e313`

```python
    "gopls": {"strategy": "go", "pkg": "golang.org/x/tools/gopls@latest", "bin": "gopls"},
```

`agent/lsp/install.py:54 @ 863e313`

```python
    "pyright": {"strategy": "npm", "pkg": "pyright", "bin": "pyright-langserver"},
```

- **npm 包不带任何版本约束**,装的是当时的 `latest`;不生成/不校验 lockfile;`--no-audit` 关掉审计。
- **go 用 `@latest`**。
- **hermes 不做校验和、不做签名验证、不 pin 版本。** 完整性完全托付给下游:
  npm registry 的 integrity 字段、Go 的 `sum.golang.org` 校验和数据库。
- 装出来的东西是**可执行文件**,随后被 `create_subprocess_exec` 直接执行。

判定 **◇**(不是「代码写错了」,是一个供应链面上的设计选择;`website/docs/.../lsp.md`
的 "Installation locations" 一节只讲了装到哪里,没讲不 pin、不校验)。

隔离做得不错:一切装进 `<HERMES_HOME>/lsp/`,不碰全局工具链。

`agent/lsp/install.py:125-131 @ 863e313`

```python
def hermes_lsp_bin_dir() -> Path:
    """Return the Hermes-owned bin staging dir for LSP servers."""
    from hermes_constants import get_hermes_home

    p = get_hermes_home() / "lsp" / "bin"
    p.mkdir(parents=True, exist_ok=True)
    return p
```

### 8.3 策略与缓存

`agent/lsp/install.py:184-189 @ 863e313`

```python
    if strategy not in {"auto",}:
        # Only ``auto`` triggers an actual install.  In manual/off,
        # we still check whether the binary already exists.
        recipe = INSTALL_RECIPES.get(pkg, {})
        bin_name = recipe.get("bin", pkg)
        return _existing_binary(bin_name)
```

`manual` 与 `off` 走同一条路(只探测)。结果按包名缓存,**成功与失败都缓存**
(`_install_results[pkg] = result`,`install.py:199-201`),所以一次失败在本进程内不会重试——
和 broken-set 同一个哲学。

### 8.4 ◇ `_install_pip` 是死代码

`_do_install` 里有 pip 分支:

`agent/lsp/install.py:230-231 @ 863e313`

```python
    if strategy == "pip":
        return _install_pip(recipe.get("pkg", pkg), bin_name)
```

**但没有任何配方用 `"strategy": "pip"`。** 搜索面:`INSTALL_RECIPES` 是配方的唯一定义处
(`install.py:52-112`),`grep -n '"strategy"' agent/lsp/install.py` 的 15 条命中里
只有 `npm`(9)、`go`(1)、`manual`(4)与两处读取。因此 `_install_pip`(46 行)在出厂配置下不可达。

---

## 9. CLI(`cli.py` 299 行)

### 9.1 ■ `hermes lsp which` 没走别名表,和 `status` 互相矛盾

其余四个子命令都经过 `_recipe_pkg_for` 把 `server_id` 翻成配方 key:

`agent/lsp/cli.py:262-274 @ 863e313`

```python
def _recipe_pkg_for(server_id: str) -> str:
    """Map a registry ``server_id`` to its install-recipe package key."""
    # The mapping lives here (not in install.py) because it's a CLI
    # convenience layer.  Most server_ids are also their own recipe
    # key, but a few differ (e.g. ``vue-language-server`` →
    # ``@vue/language-server``).
    aliases = {
        "vue-language-server": "@vue/language-server",
        "astro-language-server": "@astrojs/language-server",
        "dockerfile-ls": "dockerfile-language-server-nodejs",
        "typescript": "typescript-language-server",
    }
    return aliases.get(server_id, server_id)
```

`which` 独独没走:

`agent/lsp/cli.py:249-254 @ 863e313`

```python
def _cmd_which(server_id: str) -> int:
    from agent.lsp.install import INSTALL_RECIPES, _existing_binary

    recipe = INSTALL_RECIPES.get(server_id)
    bin_name = (recipe or {}).get("bin", server_id)
    resolved = _existing_binary(bin_name)
```

于是对 4 个别名 server_id,`INSTALL_RECIPES.get(server_id)` 必然 `None`,
`bin_name` 退化成 server_id 本身,探测的是一个根本不存在的二进制名。

**实跑复现**(P5:把一个可执行文件放进 `<HERMES_HOME>/lsp/bin/docker-langserver`):

```console
=== P5 `hermes lsp which` ignores _recipe_pkg_for alias map ===
staged binary: /tmp/p5-home-1kbpt8dz/lsp/bin/docker-langserver
detect_status(_recipe_pkg_for('dockerfile-ls')) = installed
dockerfile-ls: not installed
_cmd_which('dockerfile-ls') rc = 1
  typescript               status-path-key=typescript-language-server         which-path-key=typescript
  dockerfile-ls            status-path-key=dockerfile-language-server-nodejs  which-path-key=dockerfile-ls
  astro-language-server    status-path-key=@astrojs/language-server           which-path-key=astro-language-server
  vue-language-server      status-path-key=@vue/language-server               which-path-key=vue-language-server
```

`hermes lsp status` 说 `installed`,同一刻 `hermes lsp which` 说 `not installed`(退出码 1)。
受影响:`typescript`、`dockerfile-ls`、`astro-language-server` 三个必错;
`vue-language-server` 因为配方里 `bin` 恰好等于 server_id 而**偶然**正确。判定 **■**(低,但确定且用户可见)。

### 9.2 ■/▲ `hermes lsp restart` 在独立进程里是个空操作,却打印成功

`agent/lsp/cli.py:241-246 @ 863e313`

```python
def _cmd_restart() -> int:
    from agent.lsp import shutdown_service

    shutdown_service()
    sys.stdout.write("LSP service shut down. Next edit will respawn clients.\n")
    return 0
```

`agent/lsp/__init__.py:86-93 @ 863e313`

```python
    with _service_lock:
        svc = _service
        _service = None
    if svc is not None:
        try:
            svc.shutdown()
        except Exception as e:  # noqa: BLE001
            logger.debug("LSP shutdown error: %s", e)
```

`_service` 是**模块级、进程内**的单例。`hermes lsp restart` 是一次独立的 CLI 进程,
其 `_service` 一直是 `None`(`_cmd_restart` 也从不调用 `get_service()`),
所以 `shutdown_service()` 什么都不做,然后无条件打印 "LSP service shut down."。
它**不可能**影响另一个进程里正在跑的 gateway / chat 会话的客户端池与 broken-set。

而文档把它当成清 broken-set 的官方手段:

`website/docs/user-guide/features/lsp.md:291-295 @ 863e313`

> **Server crashed**
>
> A crashed server is added to the broken-set and won't be retried for
> the rest of the session. Run `hermes lsp restart` to clear the set;
> the next edit re-spawns.

判定 **■ + ▲**。搜索面:全仓 `grep -rn "run_lsp_command\|lsp_command" --include=*.py`
只有 `agent/lsp/cli.py` 内部 4 处命中,`register_subparser` 的唯一调用点是
`hermes_cli/main.py:11419-11420`(argparse 子命令注册)。**没有任何 slash 命令 / TUI 内路径
在 agent 进程内调用它**,所以「同进程重启」这条通路不存在。

同理 `hermes lsp status` 里的 "active clients" 段落在独立 CLI 进程里**恒为 none**
(该进程从未编辑过文件),而且 `_cmd_status` 会调 `get_service()` —— 于是它**真的会
起一个后台事件循环线程**只为打印一张注册表。**◇**。

### 9.3 CLI 的好设计:把「装了但不工作」暴露出来

`agent/lsp/cli.py:143-146 @ 863e313`

```python
    # Surface backend-tool gaps that aren't visible in the registry table:
    # some servers spawn fine but emit no diagnostics without a sidecar
    # binary (bash-language-server -> shellcheck).
    backend_warnings = _backend_warnings()
```

---

## 10. 事件日志:稳态静默(`eventlog.py` 233 行)

`agent/lsp/eventlog.py:45-57 @ 863e313`

```python
# Dedicated logger name so the documented grep recipe survives a
# ``logging.getLogger(__name__)`` rename of any internal module.
event_log = logging.getLogger("hermes.lint.lsp")

# ---------------------------------------------------------------------------
# Once-per-X dedup sets
# ---------------------------------------------------------------------------

_announce_lock = threading.Lock()
_announced_active: set = set()        # keys: (server_id, workspace_root)
_announced_unavailable: set = set()   # keys: (server_id, binary_path_or_name)
_announced_no_root: set = set()       # keys: (server_id, file_path)
_announced_no_server: set = set()     # keys: (server_id,)
```

分级规则值得抄:**稳态事件 DEBUG,状态迁移 INFO 一次,需要用户动手的 WARNING 一次**。

`agent/lsp/eventlog.py:141-154 @ 863e313`

```python
def log_server_unavailable(server_id: str, binary_or_pkg: str) -> None:
    """The server binary couldn't be resolved.  WARNING once per
    (server_id, binary), DEBUG thereafter so a hundred subsequent
    .py edits don't spam the log."""
    key = (server_id, binary_or_pkg)
    if _announce_once(_announced_unavailable, key):
        _emit(
            server_id,
            logging.WARNING,
            f"server unavailable: {binary_or_pkg} not found "
            "(install via `hermes lsp install <id>` or set lsp.servers.<id>.command)",
        )
    else:
        _emit(server_id, logging.DEBUG, f"server still unavailable: {binary_or_pkg}")
```

「一次 WARNING + 后续降级 DEBUG」而不是「一次 WARNING + 后续静默」——保留了可 grep 性。

去重集**故意不做 LRU**:

`agent/lsp/eventlog.py:27-31 @ 863e313`

```python
The dedup is in-process module-level sets.  Each set grows at most by
the number of distinct (server_id, root) and (server_id, binary)
pairs touched in one Python process — bytes of memory in even an
aggressive monorepo session.  Bounded LRU was rejected: evicting an
entry would risk re-firing the WARNING/INFO line we explicitly want
to suppress.
```

回收器会**反向清理**去重集,免得重启后的服务器被记成 "reused client":

`agent/lsp/eventlog.py:199-201 @ 863e313`

```python
    with _announce_lock:
        for key in keys:
            _announced_active.discard(key)
```

这类细节(「缓存要跟着生命周期一起回滚」)是长驻进程里最容易漏的一类。

---

## 11. 测试作为行为规格

### 环境记录(与验收标准同口径)

```verify
/home/user/hermes-venv/bin/pip list | tail -n +3 | wc -l
ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l
```

两条都得 **87**。Python 3.11.15。基线 `pyproject.toml:15` 要求 `>=3.11,<3.14`。
**本片未安装任何包。**

### 跑法与结果

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
  HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/agent/lsp
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
  HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/test_windows_subprocess_no_window_flags.py
```

```console
=== Summary: 15 files, 60 tests passed, 0 failed (100% complete) in 6.0s (8 workers) ===
=== Summary: 1 files, 9 tests passed, 0 failed (100% complete) in 0.9s (8 workers) ===
```

**合计 16 个文件 / 69 passed / 0 failed。**

**静默跳过检查**:`grep -rn "importorskip\|skipif\|pytest.skip" tests/agent/lsp/` **零命中**
——本片测试不依赖任何可选 extra(mock 服务器是纯 stdlib 脚本,用 `sys.executable` 起),
所以「平台 extra 未装」这个容器限制在这里不产生静默跳过。

### 测试覆盖了什么、漏了什么

覆盖到的行为规格(15 个文件):协议分帧与信封分类、client 端到端生命周期、
幽灵诊断(`test_stale_diagnostics.py`)、broken-set、delta key、reporter 转义、
workspace 解析、eventlog 去重、PSES 定位、后端(shellcheck)闸门、shell linter 让位。

**没被任何测试覆盖的,恰好是本片全部 5 条实跑复现的 ■:**

| 缺陷 | 为什么现有测试撞不到 |
|---|---|
| §4.3 `wait_mode: full` 打成 broken | 全部服务层测试都用 `wait_mode="document"`(`tests/agent/lsp/test_stale_diagnostics.py:140` 的 `wait_mode="document",`) |
| §4.4 冷启动 > 8s | mock 的 `slow` 脚本只 sleep 1.0s(`tests/agent/lsp/_mock_lsp_server.py:75` 的 `time.sleep(1.0)`) |
| §4.5 pull 空转 | `test_stale_diagnostics.py` 会跑到这条路,但只断言结果、不数请求数 |
| §4.6 基线 key 错 | 所有 fixture 都把 `resolve_root` 换成 `lambda fp, ws: ws`(`tests/agent/lsp/test_stale_diagnostics.py:108` 的 `resolve_root=lambda fp, ws: ws,`),恰好抹平了两个 key 的差异 |
| §2.3 ceiling 差一层 | `tests/agent/lsp/test_workspace.py` 只有 4 个用例,不覆盖「marker 在工作树父目录」 |

最后一行值得单独记:**测试 fixture 为了省事把 `resolve_root` 换成恒等函数,正好屏蔽掉了
`_current_diags_async` 用错 key 的那个 bug**。这是「测试替身抹平了被测系统的关键区分」的教科书案例。

---

## 12. 发现清单

### ■ 代码缺陷(12 条)

| # | 锚点 | 现象 | 强度 |
|---|---|---|---|
| ■1 | `agent/lsp/manager.py:313`:`t = max(8.0, self._wait_timeout + 3.0)` | `wait_mode: full`(文档化合法值)+ 默认 `wait_timeout: 5.0` ⇒ 外层 8s < 内层 10s ⇒ 基线快照必超时 ⇒ 该 `(server, root)` 被永久标 broken,LSP 对该工作区静默关闭 | 实跑复现(P6) |
| ■2 | `agent/lsp/manager.py:480` 的 `_snapshot_async` | 冷启动 > 8s(文档自称 rust-analyzer 可能 10+s)同样触发 ■1 的路径;`INITIALIZE_TIMEOUT = 45.0` 在 file_operations 路径上不可达 | 实跑复现(P10) |
| ■3 | `agent/lsp/client.py:278`:`except Exception:` | 外层 `fut.cancel()` 抛的是 `CancelledError`(BaseException),`start()` 捕获不到 ⇒ `_cleanup_process()` 不跑 ⇒ 语言服务器进程泄漏;又因 `start()` 未成功,`_clients` 里没有它,`_mark_broken_for_file` 的兜底 pop 也捞不到 | 实跑复现(P10:pid 存活) |
| ■4 | `agent/lsp/client.py:894`:`pull_task = asyncio.create_task(self._pull_document_diagnostics(abs_path))` | 服务器拒绝 pull(-32601)时该 while 循环以往返速度空转:2s 内发出 6855 次 `textDocument/diagnostic`,且 push 等待被反复取消、debounce 失效 | 实跑复现(P7) |
| ■5 | `agent/lsp/manager.py:530`:`client = self._clients.get((srv.server_id, ws))` | 用 git 根查池,池是按逐服务器根建的;marker 在子目录时必然查空,delta 基线的向前滚动静默 no-op | 实跑复现(P8) |
| ■6 | `agent/lsp/servers.py:209`:`ceiling=os.path.dirname(workspace) if workspace else None,` | `nearest_root` 在 ceiling 那一层**先查 marker 再判停**,于是工作树**父目录**的 marker 被采信,项目根逃出 git 工作树 | 实跑复现(P1) |
| ■7 | `agent/lsp/workspace.py:87`:`_workspace_cache[str(start_path)] = (None, False)` | 「不是 git 仓库」被缓存到进程结束;用户按文档 `git init` 之后本进程 LSP 永不醒 | 实跑复现(P2) |
| ■8 | `agent/lsp/cli.py:252`:`recipe = INSTALL_RECIPES.get(server_id)` | `which` 是唯一不走 `_recipe_pkg_for` 的子命令,对 `typescript` / `dockerfile-ls` / `astro-language-server` 报 "not installed" 而同刻 `status` 报 installed | 实跑复现(P5) |
| ■9 | `agent/lsp/client.py:127`:`last_col = len(lines[-1]) if lines else 0` | 位置用 Python 码点数,握手宣告的是 utf-16(`client.py:421`);最后一行含星体字符时增量同步的「全文替换」range 短一格 | 静态对读 + 单元复现(P3) |
| ■10 | `agent/lsp/cli.py:244`:`shutdown_service()` | 独立 CLI 进程里 `_service` 恒为 None,`restart` 是空操作却无条件打印 "LSP service shut down." | 静态对读(搜索面见 §9.2) |
| ■11 | `agent/lsp/manager.py:486`:`fresh = await client.wait_for_diagnostics(file_path, version, mode=self._wait_mode)` | 基线快照路径不传 `timeout=`,`lsp.wait_timeout` 对这一半路径完全失效(也是 ■1 的根因) | 实跑复现(P9) |
| ■12 | `agent/lsp/manager.py:407`:`if fresh:` | 只在非空时滚动基线;文件变干净后旧基线残留 | 静态对读 |

### ▲ 文档与代码矛盾(4 条)

| # | 锚点 | 文档说 | 代码是 | 强度 |
|---|---|---|---|---|
| ▲1 | `hermes_cli/config_defaults.py:2813`:`# current file's diagnostics; ``"full"`` additionally requests` | `"full"` 会额外请求 workspace 级诊断 | 全仓 `grep -rn "workspace/diagnostic"` 仅 1 处命中,是 `client.py:223` 的 **refresh 处理器**;客户端从不发 workspace 诊断请求。`full` 只把默认预算 5s 换成 10s。`client.py:867` 的 docstring 同一说法 | 实跑 grep + 静态 |
| ▲2 | `website/docs/user-guide/features/lsp.md:163`:`#   auto    — install via npm/pip/go install into <HERMES_HOME>/lsp/bin` | auto 会经 npm / **pip** / go 安装 | `INSTALL_RECIPES`(配方唯一定义处,`install.py:52-112`)里 `strategy` 只有 npm/go/manual,**没有一条 pip**;`_install_pip` 出厂不可达。`config_defaults.py:2820` 同一说法 | 静态 + grep |
| ▲3 | `website/docs/user-guide/features/lsp.md:294`:`the rest of the session. Run `hermes lsp restart` to clear the set;` | 用 `hermes lsp restart` 清 broken-set | 跨进程不可能;同进程无调用通路(§9.2 搜索面) | 静态对读 |
| ▲4 | `website/docs/user-guide/features/lsp.md:300`:`yet initialized, run `git init` to enable LSP diagnostics. Otherwise the` | `git init` 后 LSP 就能用 | 负缓存把 `(None, False)` 钉到进程结束(■7) | 实跑复现(P2) |

**判定口径说明**(按 CLAUDE.md 要求「整句/整段一并判定」):
- ▲3 所在的 "**Server crashed**" 小节共两句:第一句「崩了会进 broken-set、本会话不再重试」**成立**;
  第二句「用 restart 清」不成立。
- ▲4 所在的 "**Editing a file outside any git repo**" 小节共三句:前两句成立,第三句不成立。
- ▲1 所在的注释块共三行,讲的是 `wait_mode` 一个键;"document 等 wait_timeout 秒" 这半句
  **对 `get_diagnostics_sync` 成立、对 `snapshot_baseline` 不成立**(■11),后半句 full 那部分不成立。

### ◇ 代码有、文档无(8 条)

| # | 锚点 | 内容 |
|---|---|---|
| ◇1 | `agent/lsp/reporter.py:30` 的 `_sanitize_field` | 把语言服务器诊断当**不可信输入**做提示注入防护(折行/去控制符/逐字段截断/HTML 转义);`lsp.md` 完全没提这层 |
| ◇2 | `agent/lsp/reporter.py:15`:`# agent.  Lift this in config under ``lsp.severities`` if needed.` | 注释承诺的 `lsp.severities` 配置键不存在;唯一生产调用点不传 `severities=`,ERROR-only 硬编码 |
| ◇3 | `agent/lsp/install.py:344` 的 `_install_pip` | 46 行死代码(无配方使用 `"strategy": "pip"`) |
| ◇4 | `agent/lsp/servers.py:1031`:`extensions=(".sh", ".bash", ".zsh", ".ksh"),` | `.ksh` 不在 `LANGUAGE_BY_EXT` ⇒ languageId 退化为 `plaintext`;`Dockerfile` 基名同样缺表;基名分支未小写化,`dockerfile` / `Dockerfile.dev` 匹配不上 |
| ◇5 | `agent/lsp/install.py:98`:`"gopls": {"strategy": "go", "pkg": "golang.org/x/tools/gopls@latest", "bin": "gopls"},` | 自动安装**不 pin 版本、不做任何完整性校验**(`@latest` / 无版本 npm 包 / `--no-audit`),文档的 "Installation locations" 只讲了装到哪 |
| ◇6 | `agent/lsp/servers.py:766`:`inner = (` | PSES 把 bundle 路径 f-string 插进单引号 PowerShell 脚本里执行,存在引号闭合注入面 |
| ◇7 | `agent/lsp/manager.py:713` 的 `_diag_key` | 与 `client._diagnostic_key` 逐字重复两份,靠注释维持一致 |
| ◇8 | `agent/lsp/cli.py:96`:`svc = get_service()` | `hermes lsp status` 会在 CLI 进程里真的创建服务(起后台事件循环线程)只为打一张注册表,而其 "active clients" 恒为 none |

### ◎ 文档成立但保守(1 条)

| # | 锚点 | 内容 |
|---|---|---|
| ◎1 | `website/docs/user-guide/features/lsp.md:9`:`Hermes runs full language servers — pyright, gopls, rust-analyzer,` | 正文说「点名 5 个 + ~20 more」,注册表实为 **27 条**(即 22 more);同页表格已如实列全 27 行,是正文那句偏保守 |

---

## 13. 未取证 / 推定

1. **§8.1 的「首次自动安装必然导致 broken」是推定,未实跑。** 依据是三段代码的组合
   (`install.py:268` 的同步 `subprocess.run(timeout=300)` + `servers.py:238` 在 `build_spawn` 里同步调用它
   + `manager.py:313` 的 8s 外层预算),但我没有网络也没有 npm/go 去实跑。
   锚点:`agent/lsp/servers.py:237-240` 的 `bin_path = try_install("pyright", ctx.install_strategy)`。
   **下一轮可用一个假的 npm(sleep 20 后 exit 0)复现。**
2. **■3 泄漏的进程最终会不会被回收,未查到底。** 实测 2s 后仍存活;理论上 `_proc` 被 GC 时
   asyncio 的 transport 会关掉 stdin,行为良好的服务器会因 EOF 退出。我没有等到 GC / 没有跑长时观察。
3. **`website/docs/.../lsp.md:284` 说日志里找 `[agent.lsp.client]` 条目** —— 客户端 logger 名确实是
   `"agent.lsp.client"`(`client.py:75`),但**日志格式化器是否把 logger 名打成方括号形式,我没有查**
   (那在 logging 配置里,不在本片)。所以这条既没证实也没证伪。
4. **`lsp.md:207-209` 说「Nothing is ever installed to /usr/local/, ~/.local/, or any other shared
   location … removed when you reset the profile」** —— 前半句对二进制成立(都进 `<HERMES_HOME>/lsp/`),
   但 `go install` 必然会写 `GOMODCACHE`/`GOCACHE`(默认 `~/go/pkg/mod`、`~/.cache/go-build`),
   `npm install` 会写 npm cache。这算不算「installed to a shared location」是措辞问题,我不定 ▲。
   后半句「profile reset 会删掉它」需要查 `hermes_cli/profiles.py` 的 profile 目录与 `HERMES_HOME`
   的关系,**超出本片范围,未查**。
5. **■9 的实际后果(增量同步服务器会不会真的留下残字符)未在真服务器上验证。**
   我验证的是 `_end_position` 的返回值与 utf-16 长度不等这个事实。要证实后果需要一个
   advertise `textDocumentSync.change == 2` 且严格按 range 应用的服务器。
6. **`_root_or_workspace` 的 exclude 重走查在「exclude 在 marker 之上层」时的行为**,
   我静态推导认为正确(nearest_root 逐层先查 exclude),但没有构造用例实跑。
   锚点:`agent/lsp/servers.py:211` 的 `if found is None and excludes:`。
7. **`hermes lsp install-all` 与真实 npm 的交互**(尤其 `typescript-language-server` + `typescript`
   的 `extra_pkgs` 机制)未实跑,离线容器无法验证。锚点:`agent/lsp/install.py:64` 的 `"extra_pkgs": ["typescript"],`。

---

## 14. 本片移交项

| 编号 | 锚点 | 一句话现象 | 建议轮次 |
|---|---|---|---|
| H-R9D-A-a | `agent/lsp/manager.py:313`:`t = max(8.0, self._wait_timeout + 3.0)` | 外层预算不随 `wait_mode` 走,`full` 模式下 8s < 内层 10s,基线快照必超时并把 `(server, root)` 永久标 broken(实跑 P6) | R10 缺陷汇总 |
| H-R9D-A-b | `agent/lsp/client.py:894`:`pull_task = asyncio.create_task(self._pull_document_diagnostics(abs_path))` | 服务器拒绝 pull 时该循环空转,2s 发 6855 次请求(实跑 P7) | R10 缺陷汇总 |
| H-R9D-A-c | `agent/lsp/manager.py:530`:`client = self._clients.get((srv.server_id, ws))` | 用 git 根查按逐服务器根建的客户端池,marker 在子目录时必空,基线滚动静默失效(实跑 P8) | R10 缺陷汇总 |
| H-R9D-A-d | `agent/lsp/workspace.py:87`:`_workspace_cache[str(start_path)] = (None, False)` | 「非 git 目录」被永久负缓存,文档教的 `git init` 在本进程内无效(实跑 P2) | R10 文档冲突定案 |
| H-R9D-A-e | `agent/lsp/cli.py:252`:`recipe = INSTALL_RECIPES.get(server_id)` | `hermes lsp which` 漏了 `_recipe_pkg_for` 别名映射,与 `status` 对同一服务器给出相反答案(实跑 P5) | R10 缺陷汇总 |
| H-R9D-A-f | `agent/lsp/client.py:278`:`except Exception:` | 外层取消抛的 `CancelledError` 不被捕获,`_cleanup_process()` 不跑,语言服务器进程泄漏(实跑 P10) | R10 缺陷汇总 |
| H-R9D-A-g | `agent/lsp/servers.py:209`:`ceiling=os.path.dirname(workspace) if workspace else None,` | ceiling 差一层,项目根可以解析到 git 工作树之外(实跑 P1) | R10 缺陷汇总 |
| H-R9D-A-h | `agent/lsp/install.py:238`:`bin_path = try_install("pyright", ctx.install_strategy)` | 同步 `subprocess.run(timeout=300)` 跑在 LSP 后台事件循环上,而外层只有 8s ——**推定**首次自动安装必然把服务器打成 broken,需要一个假 npm 去实跑证实 | R10 取证 |

---

## 15. 交付自检

```verify
git -C /home/user/hermes-agent status --porcelain
git -C /home/user/hermes-agent rev-parse HEAD
```

- 基线 `git status --porcelain` 输出为空(交付前实跑确认);HEAD =
  `863e31318553cda8ad61df681d08175364d4164b`。
- **未安装任何包**(venv 包数交付前后均为 87);未跑 pip / npm / go。
- **未修改 `/home/user/hermes-study/scripts/` 下任何文件**;本片只写
  `/home/user/hermes-study/notes/r9d-raw-lsp.md` 这一个文件。
- 所有实验脚本(P1–P10)写在会话 scratchpad 目录,**不在基线、也不在学习仓库内**;
  实验产生的临时仓库均在 `/tmp` 下由 `tempfile.mkdtemp` 创建。
- 唯一在基线目录内产生的写入是测试运行器的 `test_durations.json` 与 `__pycache__`,
  两者均被 `.gitignore` 覆盖(`.gitignore:35` 命中 `test_durations.json`),故 `status` 仍为空。
