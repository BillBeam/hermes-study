# r7b-40 · `gateway/platforms/api_server.py` —— 把 OpenAI 协议接到有状态 agent 上

> 底稿。基线 `863e31318553cda8ad61df681d08175364d4164b`。7,188 行,全簇最大文件。

## 0. 一句话

api_server 是一个**伪装成 OpenAI 的适配器**:它继承 `BasePlatformAdapter`,
但入站不是聊天消息而是 HTTP 请求;它最难的部分不是协议兼容,而是**把无状态协议
映射到有状态会话**,以及**别把一个能执行终端命令的端点暴露到网络上**。

## 1. 从一个场景说起

你在 Open WebUI 里配一个 "OpenAI 兼容" 端点指向 Hermes,然后连问三句话。
Open WebUI 是**无状态客户端**:它每次都把**完整历史**塞进 `messages` 重发一遍,
自己不带任何会话 id。

但 Hermes 的 agent 是**有状态**的:它有 Docker 沙箱工作目录、有工具审批记录、
有长期记忆。三句话必须落到**同一个会话**,否则第二句问"刚才那个文件呢"就找不到沙箱。

没有会话 id,怎么认出"这是同一段对话"?

## 2. 三种会话身份,按可信度分层

### 2.1 指纹派生(零配置,默认)

```python
def _derive_chat_session_id(
    system_prompt: Optional[str],
    first_user_message: str,
) -> str:
    """Derive a stable session ID from the conversation's first user message.

    OpenAI-compatible frontends (Open WebUI, LibreChat, etc.) send the full
    conversation history with every request.  The system prompt and first user
    message are constant across all turns of the same conversation, so hashing
    them produces a deterministic session ID that lets the API server reuse
    the same Hermes session (and therefore the same Docker container sandbox
    directory) across turns.
    """
    seed = f"{system_prompt or ''}\n{first_user_message}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"api-{digest}"
```

(`gateway/platforms/api_server.py:1264-1279 @ 863e313`)

**洞察**:无状态客户端虽然不给 id,但它给的东西里**有一部分是这段对话的不变量** ——
系统提示 + 第一条用户消息。哈希它们就得到一个确定性 id。零客户端改造。

**取舍**:两段对话若系统提示和首句完全相同(比如两次都从 "hi" 开始),会**撞进同一会话**。
所以它只是默认兜底,可信路径见下。

### 2.2 `X-Hermes-Session-Id` —— 会话续接(要鉴权)

```python
        # Security: session continuation exposes conversation history, so it is
        # only allowed when the API key is configured and the request is
        # authenticated.  Without this gate, any unauthenticated client could
        # read arbitrary session history by guessing/enumerating session IDs.
        provided_session_id = request.headers.get("X-Hermes-Session-Id", "").strip()
        if provided_session_id:
            if not self._api_key:
```

(`gateway/platforms/api_server.py:3952-3961 @ 863e313`)

给了这个头,**历史从 state.db 读,而不是从请求体读**
(`gateway/platforms/api_server.py:3989-3995 @ 863e313`)。这正是它必须鉴权的原因:
**它是一个读别人历史的原语**。校验三关(`:3979-3988`):

```python
            from gateway.session import _is_path_unsafe
            if re.search(r'[\r\n\x00]', provided_session_id) or _is_path_unsafe(provided_session_id):
```

控制字符(防头注入 + 防日志伪造)、路径穿越(id 会被插进磁盘产物文件名)、长度上限 256。
注释说明它**复用原生网关的同一个入口守卫** `gateway.session._is_path_unsafe`
—— 两条入站血统共用一份路径安全判定,不各写一份。

### 2.3 `X-Hermes-Session-Key` —— 长期记忆作用域(要鉴权)

两个头**正交**,docstring 讲得很清楚(`gateway/platforms/api_server.py:2049-2057 @ 863e313`):

```python
        """Extract and validate the ``X-Hermes-Session-Key`` header.

        The session key is a stable per-channel identifier that scopes
        long-term memory (e.g. Honcho sessions) across transcripts.  It
        is independent of ``X-Hermes-Session-Id``: callers may send
        either, both, or neither.
```

即:**id 是"哪一段转写",key 是"谁的记忆"**。开新转写(`/new` 语义)时 id 轮换,
key 不变,所以长期记忆跨转写延续。这是 R6 精读的记忆生态在 HTTP 面的挂接点。

它同样要求鉴权,理由与 §2.2 对称(`gateway/platforms/api_server.py:2058-2062 @ 863e313`):

> Security: like session continuation, accepting a caller-supplied
> memory scope requires API-key authentication so that an
> unauthenticated client on a local-only server can't inject itself
> into another user's long-term memory scope by guessing a key.

**注意"写"方向**:session-id 的风险是**读**别人历史;session-key 的风险是
**写进**别人的长期记忆域。两个方向都堵。

上限 256 的理由也写下来了(`gateway/platforms/api_server.py:2039-2046 @ 863e313`):
aiohttp 已经有 8 KiB 的头上限,但这里更紧,免得调用方用一个几 KB 的"会话键"烧内存,
并且"sanitized form is safe to pass into Honcho / state.db"。

## 3. 会话绑定的**单一收口**(#10760)

```python
    def _bind_api_server_session(
        *,
        chat_id: str = "",
        session_key: str = "",
        session_id: str = "",
    ) -> list:
        """Bind session contextvars for an API-server agent run.

        This is the SINGLE structural chokepoint every API-server agent-entry
        path must use to seed session context — it hardwires
        ``platform="api_server"`` and ``async_delivery=False`` so a new route
        physically cannot reintroduce the silent-no-op bug (#10760) by
        forgetting to mark the channel as non-delivering. There is no
        ``async_delivery`` parameter to get wrong; the stateless HTTP path can
        never wake the agent after the turn ends, on ANY route.
```

(`gateway/platforms/api_server.py:5925-5940 @ 863e313`)

**故事(#10760)**:agent 有"异步投递"能力 —— 后台任务跑完后主动给你发消息。
在 Telegram 上这没问题(网关持有长连接,随时能推)。但 HTTP 是**请求-响应**:
回合结束、连接关闭,**没有任何通道**能把后续消息送回去。早期某条路由忘了标记
"本通道不能异步投递",于是 agent 欢快地安排了一个后台通知 —— 然后**静默丢失**。
用户什么也没收到,日志里也没有错误。

**修法是结构性的**:不是"记得传 `async_delivery=False`",而是**把这个参数从签名里删掉**。
函数硬编码 `async_delivery=False`,于是**新路由物理上无法传错** —— 没有可以传错的参数。

**可迁移原则**:当一个必须永远取某值的参数反复被忘记时,正确的修法是**消灭这个参数**,
而不是加文档或加断言。让错误状态不可表达。

同时注意 `finally` 里必须 `clear_session_vars`(`:5942-5946`),因为绑定是**请求级**的,
不能外溢到后来在**可投递**接口上恢复的同一会话。

## 4. 鉴权与启动守卫:一个能跑终端命令的端点

### 4.1 启动即拒绝

```python
        if not has_usable_secret(self._api_key, min_length=16):
            logger.error(
                "[%s] Refusing to start: API_SERVER_KEY is a "
                "placeholder or too short (<16 chars). This endpoint "
                "dispatches terminal-capable agent work — a guessable "
                "key is remote code execution. ...
```

(`gateway/platforms/api_server.py:6971-6980 @ 863e313`)

**连 loopback-only 绑定也要求密钥**(`:6948-6953`):

```python
                "[%s] Refusing to start: API_SERVER_KEY is required for the API server, "
                "including loopback-only binds on %s.",
```

理由是同机上的任何进程/浏览器页面都能打 loopback。**"本地就安全"是错的。**

强度检查器导入失败时 **fail closed**(`gateway/platforms/api_server.py:6955-6970 @ 863e313`):

```python
            # Fail CLOSED. This guard is the only thing between a guessable
            # key and a terminal-capable endpoint, so "the check could not be
            # run" must not resolve to "start anyway" — the same posture
            # tools/credential_files.py takes when its deny-list cannot be
            # consulted.
```

### 4.2 #38803:一次"可重试"分类错误烧掉整个网关

```python
            # A rejected API_SERVER_KEY is a configuration error, not a
            # transient blip — the key will not become valid on its own. A
            # bare ``return False`` makes the reconnect watcher in
            # gateway.run treat it as retryable and loop forever at the
            # backoff cap, re-instantiating the adapter (and its
            # ResponseStore sqlite connection) every retry (#38803: ~501
            # leaked connections / 1002 fds over 2.5 days until EMFILE took
            # the whole gateway down).
```

(`gateway/platforms/api_server.py:6991-6999 @ 863e313`)

**故事**:密钥配错 → `connect()` 返回 False → 重连看门狗当成网络抖动 → 无限重试。
每次重试**重新构造适配器**,而适配器构造时会开一个 SQLite 连接(`ResponseStore`)。
构造出来的适配器随即被丢弃,但**连接没关**。2.5 天后泄漏约 501 个连接 / 1002 个 fd,
撞上 `EMFILE`,**整个网关**(不只是 api_server)挂掉。

修法是把它标成 `retryable=False`,从重连队列里摘掉。

**可迁移原则**:失败分类(可重试 / 不可重试)是**资源安全**问题,不只是用户体验问题。
"配置错误"被误分类成"瞬时故障",代价是一个无限循环 + 每圈泄漏一点资源。

### 4.3 鉴权本身

```python
            # Compare as bytes: ``hmac.compare_digest`` raises TypeError on a
            # str containing non-ASCII characters, and ``token`` is the raw
            # client-supplied header. A stray non-ASCII byte in the key would
            # otherwise crash this handler (500) instead of returning a clean
            # 401.
            if hmac.compare_digest(token.encode(), expected_key.encode()):
```

(`gateway/platforms/api_server.py:1752-1759 @ 863e313`)

常量时间比较 + **先编码成 bytes**。一个非 ASCII 字节的 Authorization 头本来会让
`hmac.compare_digest` 抛 `TypeError` → 500。**500 和 401 泄漏的信息量不同**,
而且 500 说明服务端崩了一条路径。

多 profile(multiplex)下**具名 profile 必须 fail closed**
(`gateway/platforms/api_server.py:1731-1739 @ 863e313`):

```python
            # Preserve the historical no-key test/manual-wiring behavior only
            # for the default listener. Named profiles must fail closed rather
            # than inherit the listener owner's key.
```

即"无密钥则放行"这个历史行为**只**保留给默认监听器,具名 profile 一律 401 ——
否则 profile B 的调用者会用 profile A 的密钥进来。

### 4.4 不是所有路由都用 API_SERVER_KEY

路由表里有两条**用别的凭据**(`gateway/platforms/api_server.py:2009-2012`、`:2030-2032 @ 863e313`):

```python
            # Generic platform HTTP event callback ingress. Authenticated by
            # the target adapter's own verifier (platform-signed bearer), NOT
            # API_SERVER_KEY — external platforms hold no API server key.
            ("POST", "/api/platforms/{platform}/events", self._handle_platform_event_callback),
```

```python
            # Chronos managed-cron fire webhook (NAS → agent). Authenticated
            # by a NAS-minted JWT (NOT API_SERVER_KEY).
            routes.append(("POST", "/api/cron/fire", self._handle_cron_fire))
```

**一个 HTTP 服务器上并存三种信任来源**:运营方密钥、平台签名、NAS 签发的 JWT。
读代码时最容易犯的错就是假设"所有路由一个鉴权"。

## 5. HTTP 面独有的三个工程问题

### 5.1 准入与排水的原子性

```python
    """Reserve an authenticated API turn before its handler first awaits.

    Gateway shutdown and aiohttp requests share an event loop. Keeping the
    drain check and reservation in one non-awaiting block prevents a request
    admitted immediately before shutdown from becoming invisible while it is
    still parsing its body or resolving session state.
    """
```

(`gateway/platforms/api_server.py:1107-1116 @ 863e313`)

鉴权 → 查排水 → 占位,**三步之间不 await**。因为一旦 await,关停可能插进来,
而此时请求"还没开始算工作量",于是关停以为没活了就走了 —— 请求被腰斩。

`_reserve_pending_api_work` 还支持**detach**(`:1147-1160`):handler 把工作交给
后台任务时,预留随之转移,由任务的 done 回调负责释放。**关停可见性跨越了任务边界。**

### 5.2 幂等缓存

`_IdempotencyCache`(`gateway/platforms/api_server.py:1210-1256 @ 863e313`)+
`_make_request_fingerprint`(`:1258-1262`):同一个幂等键重复提交返回同一结果。
HTTP 客户端超时重发是常态,而一个 agent 回合可能有副作用(发消息、写文件),
**不能重放**。

### 5.3 并发上限

```python
        """Read the concurrent-run cap from config.yaml (0 disables).

        gateway.api_server.max_concurrent_runs. Falls back to the historical
        default of 10 when unset or malformed. Negative values are clamped
        to 0 (disabled).
```

(`gateway/platforms/api_server.py:1559-1568 @ 863e313`)

聊天平台的并发天然被"人打字的速度"限住;HTTP 没有这个限制,一个循环脚本能瞬间起 1000 个
agent。所以 HTTP 面必须自己加闸。

## 6. 审批走 HTTP 的完整往返

`POST /v1/runs/{run_id}/approval`(`gateway/platforms/api_server.py:6772 @ 863e313`)。
关键设计:

- **别名归一**(`:6791-6793`):`approve` / `approved` / `allow` → `once`;
  合法集合 `{once, session, always, deny}`。
- **无活跃审批返回 409**(`:6802-6810`)而非 404 —— 区分"这个 run 不存在"
  和"这个 run 现在没在等审批"。
- 最终落到 `tools.approval.resolve_gateway_approval`(`:6817-6823`)——
  **与聊天平台的按钮回调是同一个解析器**。

**这条最能说明 R7B 的主题**:审批这件事,Telegram 用内联键盘、Discord 用组件、
HTTP 用一个 POST,但**解析器只有一个**。适配器负责"怎么问",网关负责"答案是什么意思"。

## 7. 【文档-代码冲突候选】

**▲ B-13**:任务简报(源自 R7 报告 §8)称 api_server 的会话绑定头是
`X-Hermes-Session-Id`。代码里**是两个头**,且 R7B 的核心机制其实是
`X-Hermes-Session-Key`(长期记忆作用域)与 `X-Hermes-Session-Id`(转写续接)
**正交并存**(`gateway/platforms/api_server.py:2049-2057 @ 863e313`)。
这不是仓库文档的错,是**上一轮报告的简化**,在此更正备案。

**◇ B-14**:`/api/platforms/{platform}/events` 与 `/api/cron/fire` 两条路由
**不使用 API_SERVER_KEY**,各自有独立信任来源(`gateway/platforms/api_server.py:2009-2012`、
`:2030-2032 @ 863e313`)。`website/docs/**` 中未见对"API server 上并存三种鉴权"的说明,
而这直接影响运营方对该端口的暴露决策。

**◇ B-15**:`_derive_chat_session_id` 的会话指纹派生(§2.1)是无状态客户端能用上
Hermes 有状态会话的**全部原因**,且带有"首句相同则撞会话"的实际后果;
`website/docs/**` 无对应描述。

**◇ B-16**:`gateway.api_server.max_concurrent_runs`(§5.3)与
#38803 的不可重试分类(§4.2)均只见于代码。

## 8. 【bug 候选】

无(本轮已核对的段落内)。`_check_auth` 在**默认监听器 + 无密钥**时 `return None`
(放行)看起来危险,但 `connect()` 的启动守卫已经保证进程根本起不来
(`gateway/platforms/api_server.py:6944-6982 @ 863e313`),docstring 也自陈
"the no-key branch only exists for tests or unsupported manual wiring"
(`:1719-1721`)。判定为**有前置保证的死分支**,不计入 bug。

## 9. 【重实现要点】

1. **无状态客户端 → 有状态会话**:从请求里找不变量(系统提示 + 首句)哈希成确定性 id,
   零客户端改造;同时提供显式头作为可信路径。
2. **"哪段转写"与"谁的记忆"是两个身份**,必须正交,否则开新转写会丢长期记忆。
3. **任何接受调用方指定会话身份的头都要鉴权**:读方向泄漏历史,写方向污染记忆。
4. **必须永远取某值的参数,要从签名里删掉**,而不是靠文档提醒(#10760)。
5. **能执行代码的端点,启动就要拒绝弱密钥**,loopback 也不例外,检查器不可用时 fail closed。
6. **失败要分类为可重试/不可重试**;误分类会变成无限重试 + 每圈资源泄漏(#38803)。
7. **准入与排水检查必须在同一个不 await 的块里**,并支持预留随后台任务转移。
8. **HTTP 面必须自己加并发闸和幂等缓存**,聊天平台的自然节流在这里不存在。
9. **一个 HTTP 服务器可以并存多种信任来源**,不要假设全局单一鉴权。
10. **"怎么问"归适配器,"答案什么意思"归网关**:审批/澄清的解析器全平台共用一份。
