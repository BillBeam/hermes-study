# r7b-50 · 九个内建适配器 —— 同一份契约,九种"平台现实"

> 底稿。基线 `863e31318553cda8ad61df681d08175364d4164b`。
> 覆盖 signal / whatsapp_cloud+common / weixin / webhook+filters+msgraph / bluebubbles /
> qqbot / yuanbao / api_server(见 `r7b-40`)/ media_cache / helpers / _http_client_limits。

## 0. 一句话

九个适配器验证同一件事:**基类契约的价值不在于"统一了什么",而在于"允许各平台在哪些
维度上不一样"**。

## 1. 入站血统:四种,没有一种是"标准的"

| 适配器 | 入站方式 | 溯源 |
|---|---|---|
| Signal | signal-cli daemon 的 **SSE 流**;出站是同一 daemon 的 **JSON-RPC 2.0 over HTTP** | `gateway/platforms/signal.py:1-12 @ 863e313` |
| WhatsApp Cloud | Meta **HTTP webhook**(需公网 URL)+ 自建监听端口 | `gateway/platforms/whatsapp_cloud.py:12-25 @ 863e313` |
| Weixin | **长轮询** `getupdates` | `gateway/platforms/weixin.py:1-11 @ 863e313` |
| Yuanbao | **WebSocket**(AUTH_BIND + 心跳 + T05 收 / T06 发) | `gateway/platforms/yuanbao.py:1-16 @ 863e313` |
| BlueBubbles | 本机 macOS 服务器的 **inbound webhook** + REST 出站 | `gateway/platforms/bluebubbles.py:1-9 @ 863e313` |
| Webhook(通用) | 任意 **HTTP POST**,动态路由 | `gateway/platforms/webhook.py` |
| api_server | **HTTP**(OpenAI 兼容) | `r7b-40` |

**没有共性可抽**。这就是为什么基类不定义"如何收消息",只定义
`connect()` / `set_message_handler()` / `handle_message(event)` 三点契约:
**收的方式随平台,收到之后的路只有一条。**

Signal 的形态最能说明"平台现实"的荒诞度 —— 收用 SSE,发用 JSON-RPC,两个协议、
一个进程外守护进程(`gateway/platforms/signal.py:2-5 @ 863e313`):

```
Connects to a signal-cli daemon running in HTTP mode.
Inbound messages arrive via SSE (Server-Sent Events) streaming.
Outbound messages and actions use JSON-RPC 2.0 over HTTP.
```

## 2. 证明发信人是平台本人:三种签名 + 一种"没有"

### 2.1 WhatsApp Cloud:`X-Hub-Signature-256`,**必须用原始字节**

```python
    def _verify_signature(self, raw_body: bytes, header: str) -> bool:
        """Verify the X-Hub-Signature-256 HMAC.

        Meta sends ``sha256=<hex>``; we compute the same HMAC with
        ``app_secret`` as the key and ``raw_body`` (UTF-8 bytes, not
        re-serialized JSON) as the message. Constant-time compare.
        """
```

(`gateway/platforms/whatsapp_cloud.py:1525-1531 @ 863e313`)

**"not re-serialized JSON" 是这类校验的第一坑**:`json.loads` 再 `json.dumps` 会改
键序、空白、Unicode 转义,HMAC 立刻不匹配。必须留住**收到的原始字节**。
relay 的投递签名也写了同一条(`gateway/relay/auth.py:154-157 @ 863e313`)。

比较同样先编码成 bytes,理由与 api_server 一致(`gateway/platforms/whatsapp_cloud.py:1544-1548 @ 863e313`)。

### 2.2 通用 Webhook:一个端点上认**五种**签名方言

`_validate_signature` 依次尝试(`gateway/platforms/webhook.py:1040-1130 @ 863e313`):
Svix(`svix-id`/`svix-timestamp`/`svix-signature`,签 `"{id}.{ts}.{body}"`)、
GitHub(`X-Hub-Signature-256: sha256=<hex>`)、GitLab(`X-Gitlab-Token`,**明文比对**)、
自有 V2(`X-Webhook-Signature-V2` 签 `"<ts>.<body>"`,带时间戳防重放)、自有 V1。

V2 的检查顺序留了一条注释,记录了一个真实的漏检
(`gateway/platforms/webhook.py:1071-1075 @ 863e313`):

```python
        # Checked independently of (and before) legacy V1 below — a sender
        # that only ever sends V2 headers must still validate here; nesting
        # this inside `if generic_sig:` would silently skip V2-only senders.
```

**故事**:V2 的校验原本嵌在 `if generic_sig:`(V1 头存在)里面。只发 V2 头的发送方
没有 V1 头,于是整个校验块**被跳过** —— 不是拒绝,是**静默跳过**,请求被当作无签名放行。
教训:**多方言校验必须是并列的独立分支,不能嵌套**,否则新增方言会被旧方言的存在性判定吞掉。

### 2.3 全平台共用的一条防线:非 ASCII 头不得让服务端 500

```python
def _hmac_str_equal(provided: str, expected: str) -> bool:
    """Timing-safe equality for two ``str`` values, tolerant of non-ASCII input.

    ``hmac.compare_digest`` raises ``TypeError`` when given a ``str`` that
    contains non-ASCII characters. The ``provided`` value here is an
    attacker-controlled signature/token header on a public, unauthenticated
    webhook endpoint, so a single non-ASCII byte would otherwise raise out of
    the request handler and return a 500 instead of rejecting the request.
    Comparing as UTF-8 bytes keeps the constant-time guarantee while making a
    hostile header fail closed with a clean rejection.
    """
    return hmac.compare_digest(provided.encode(), expected.encode())
```

(`gateway/platforms/webhook.py:158-169 @ 863e313`)

同一个坑在 `api_server._check_auth`(`gateway/platforms/api_server.py:1752-1759 @ 863e313`)
和 `whatsapp_cloud._verify_signature`(`:1544-1548`)各修了一次。
**一个字节的 UTF-8 就能把常量时间比较变成 500** —— 而 500 与 401 的区别对攻击者是信息。

### 2.4 QQBot:凭据本身要加密下发

`gateway/platforms/qqbot/crypto.py` 不验签,它解密**扫码配置**时服务端回传的 client_secret
(`gateway/platforms/qqbot/crypto.py:1 @ 863e313`,"AES-256-GCM utilities for QQBot
scan-to-configure credential decryption"):

```python
def generate_bind_key() -> str:
    """Generate a 256-bit random AES key and return it as base64.

    The key is passed to ``create_bind_task`` so the server can encrypt
    the bot's *client_secret* before returning it.  Only this CLI holds
    the key, ensuring the secret never travels in plaintext.
    """
```

密文布局 `IV(12) ‖ ciphertext ‖ AuthTag(16)`(`gateway/platforms/qqbot/crypto.py:22-26 @ 863e313`)。
**这是"配置流程本身也是攻击面"的实例**:扫码绑定要把 bot 密钥从服务端送到本机,
中间经过一次 HTTP 响应 —— 于是本机先造一把一次性 AES 密钥,让服务端用它加密。

## 3. 平台的"物理约束"如何进入代码

### 3.1 Weixin:每条回复必须回带 `context_token`

```
- Long-poll ``getupdates`` drives inbound delivery.
- Every outbound reply must echo the latest ``context_token`` for the peer.
- Media files move through an AES-128-ECB encrypted CDN protocol.
- QR login is exposed as a helper for the gateway setup wizard.
```

(`gateway/platforms/weixin.py:5-11 @ 863e313`)

"每条回复回带对端最新 context_token" 意味着适配器必须**维护每个 peer 的最新 token**,
且它随每次入站更新。这是基类完全无法预见的状态,只能留在适配器里。

### 3.2 WhatsApp:24 小时会话窗

```
- Phase 5 — 24-hour conversation window + template fallback.
```

(`gateway/platforms/whatsapp_cloud.py:25 @ 863e313`)

Meta 规定:用户最后一次发言 24 小时后,商业账号只能发**预审模板**,不能发自由文本。
这不是技术限制,是**商业策略被编码进 API**。适配器要么在窗内自由发,要么回落模板。

同类的时间窗约束在 `ADDING_A_PLATFORM.md:44-55 @ 863e313` 被抽象成了一条通用建议
(LINE 的 60 秒一次性 reply token、WhatsApp 24h),给出的接法是**覆盖 `_keep_typing`**
并 `await super()._keep_typing(...)` 保住心跳。

### 3.3 每条消息的媒体上限逐类不同

```python
    "image": 5 * 1024 * 1024,        # 5 MB (JPEG, PNG)
    "video": 16 * 1024 * 1024,       # 16 MB
    "audio": 16 * 1024 * 1024,       # 16 MB (MP3, AAC, AMR, OGG opus)
    "document": 100 * 1024 * 1024,   # 100 MB
    "sticker": 100 * 1024,           # 100 KB animated, 500 KB static
```

(`gateway/platforms/whatsapp_cloud.py:113-117 @ 863e313`)

而 Signal 的约束是**每条消息附件数**与**账号级速率**两条:

```python
SIGNAL_MAX_ATTACHMENTS_PER_MSG = 32  # per-message attachment cap (source: Signal-{Android,Desktop} source code)
SIGNAL_RATE_LIMIT_BUCKET_CAPACITY = 50  # server-side token-bucket capacity for attachments rate limiting
```

(`gateway/platforms/signal_rate_limit.py:36-37 @ 863e313`)

### 3.4 Signal 没有 markdown,只有字节范围

```python
    """Convert markdown to plain text + Signal textStyles list.

    Signal doesn't render markdown. Instead it uses ``bodyRanges`` (exposed by
    signal-cli as ``textStyle`` / ``textStyles`` params) with the format
    ``start:length:STYLE``.

    Positions are measured in UTF-16 code units because that's what the Signal
    protocol uses.

    Supported styles: BOLD, ITALIC, STRIKETHROUGH, MONOSPACE.
    """
```

(`gateway/platforms/signal_format.py:12-24 @ 863e313`)

**又是 UTF-16**(与 Telegram 长度单位同源),但用途不同:这里是**样式区间的偏移量**。
把 `**bold**` 转成 "纯文本 + `start:length:BOLD`",而 start/length 必须按 UTF-16 数,
否则一个 emoji 就让后面所有样式错位。

列表符号的处理值得单独看(`gateway/platforms/signal_format.py:31-42 @ 863e313`):

```python
        """Replace Markdown bullet markers with plain Unicode bullets.

        Signal does not render Markdown list syntax, so ``- item`` and
        ``* item`` otherwise arrive as literal Markdown markers. Preserve
        fenced code blocks byte-for-byte; list-looking lines inside code are
        code, not prose bullets.
        """
        parts = re.split(r"(```.*?```)", source, flags=re.DOTALL)
        for idx, part in enumerate(parts):
            if idx % 2 == 1:
                continue
```

**代码块要逐字保留** —— 一段 shell 脚本里的 `- flag` 不是列表项。用 `re.split` 保留
分隔符、按奇偶索引跳过代码块,是这类"只改散文不改代码"变换的标准写法,
全仓多处复用(`gateway/platforms/base.py` 的媒体标记剥离、`helpers.py` 的围栏切分同形)。

### 3.5 Signal 速率限制:用**服务端的权威提示**校准本地模型

```
Process-wide token-bucket simulator that mirrors the per-account
attachment rate limit signal-cli/Signal-Server enforce. Producers
(``SignalAdapter.send_multiple_images`` and the ``send_message`` tool's
Signal path) call ``acquire(n)`` before an attachment send; on a 429
they call ``feedback(retry_after, n)`` so the model recalibrates from
the server's authoritative hint.

The scheduler serializes concurrent calls through an ``asyncio.Lock``,
giving FIFO fairness across agent sessions sharing one signal-cli
daemon.
```

(`gateway/platforms/signal_rate_limit.py:2-14 @ 863e313`)

**三个设计点**:(a) 本地**模拟**服务端的令牌桶,先自我节流,别把 429 打出去;
(b) 真挨了 429 就用 `Retry-After` **反向校准**本地模型 —— 本地模拟只是先验,
服务端是权威;(c) 进程级 `asyncio.Lock` 给共享同一个 daemon 的多个 agent 会话
**FIFO 公平**,而不是让某个会话饿死。

**可迁移原则**:客户端限流是"先验模型 + 服务端反馈校正"的闭环,不是写死的常数。

## 4. 共享层:重复三次以上才抽

`gateway/platforms/helpers.py` 的存在理由写在模块头(`:1-6 @ 863e313`):

```
Shared helper classes for gateway platform adapters.

Extracts common patterns that were duplicated across 5-7 adapters:
message deduplication, text batch aggregation, markdown stripping,
and thread participation tracking.
```

每个类的 docstring 都点名了它替换掉的重复
(`MessageDeduplicator`:"discord, slack, dingtalk, wecom, weixin, mattermost, feishu"
—— `gateway/platforms/helpers.py:30-33 @ 863e313`;
`TextBatchAggregator`:"telegram, discord, matrix, wecom, feishu" —— `:100-101`;
`strip_markdown`:"sms.py, bluebubbles.py, feishu.py" —— `:200-201`;
`ThreadParticipationTracker`:"discord.py and matrix.py" —— `:220-222`;
`redact_phone`:"signal.py, sms.py, bluebubbles.py" —— `:286-287`)。

**这是一条清晰的抽象纪律**:不预先设计共享层,等到同一段代码在 5-7 个适配器里
逐字重复了,再抽出来,并**在 docstring 里记下它替换了谁**。

### 4.1 `MessageDeduplicator` 的双重上界

```python
        self._seen[msg_id] = now
        if len(self._seen) > self._max_size:
            cutoff = now - self._ttl
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
            if len(self._seen) > self._max_size:
                # TTL pruning alone does not cap the cache when every entry is
                # still fresh. Keep the newest entries so the helper's
                # max_size bound is enforced under sustained traffic.
```

(`gateway/platforms/helpers.py:56-66 @ 863e313`)

**TTL 剪枝不足以封顶**:突发流量下所有条目都"新鲜",于是必须再按时间排序截尾。
两个上界(时间 + 条数)缺一不可 —— 只有 TTL 会在高峰期无界增长,只有条数会在
低峰期把仍需去重的老条目挤掉。

### 4.2 `TextBatchAggregator` 的分片启发式

```python
        # Use longer delay when the last chunk looks like a split message
        delay = self._split_delay if last_len >= self._split_threshold else self._batch_delay
```

(`gateway/platforms/helpers.py:158-159 @ 863e313`)

用户在客户端粘了一段长文,客户端自己切成多条发。**最后一片恰好等于平台上限**,
就是"后面还有"的信号 → 用更长的 `split_delay`(默认 2.0s)等下一片,
而不是普通的 `batch_delay`(0.6s)。

### 4.3 `_http_client_limits`:#18451 的 fd 耗尽

```
httpx's default ``keepalive_expiry`` is 5 seconds.  On macOS behind
Cloudflare Warp (and other transparent proxies), peer-initiated FIN can
sit in ``CLOSE_WAIT`` longer than that before the local socket actually
drains — which, multiplied across 7 long-lived adapters plus the LLM
client and MCP clients, walks straight into the default 256 fd limit.
See #18451.
```

(`gateway/platforms/_http_client_limits.py:12-19 @ 863e313`)

**故事**:七个长驻适配器各持一个 httpx 连接池,默认空闲连接留 5 秒。在 Cloudflare Warp
这类透明代理后,对端 FIN 后的套接字会在 `CLOSE_WAIT` 里停留更久才真正释放。
**7 个适配器 × 池大小 + LLM 客户端 + MCP 客户端** 累加,撞上 macOS 默认 256 fd 上限。
修法是把 `keepalive_expiry` 收到 2.0 秒、`max_keepalive_connections` 收到 10
(`:20-25`),即**主动更早地关闲连接**。

这与 api_server 的 #38803(泄漏 1002 fd)是**同一类事故的两个入口**:
一个是重试循环泄漏,一个是连接池滞留。**fd 是网关的第一稀缺资源。**

### 4.4 `__init__.py`:导入成本也是成本

```python
# QQAdapter and YuanbaoAdapter were previously imported eagerly here, but
# nothing in the codebase consumes ``from gateway.platforms import
# QQAdapter`` (every real call site uses the long-form path
# ``from gateway.platforms.qqbot import QQAdapter``). The eager imports
# pulled in qqbot's chunked-upload + keyboards + onboard machinery and
# yuanbao's websocket stack — about 48 ms wall and ~8 MB RSS on every
# CLI invocation, even ones that never touch a gateway adapter.
```

(`gateway/platforms/__init__.py:11-19 @ 863e313`)

用 PEP 562 的模块级 `__getattr__` 延迟导入(`:34-41`),既保住公开再导出的向后兼容,
又把 48ms / 8MB 从**每一次 CLI 调用**上摘掉。**CLI 的启动时间是用户每天付好几次的税。**

## 5. 跨适配器能力位对照

| 适配器 | `enforces_own_access_policy` | 交互 UX | 特有能力 |
|---|---|---|---|
| WhatsApp Cloud | ✔(mixin 提供 dm/group policy) | `send_exec_approval`(`whatsapp_cloud.py:845`) | 24h 窗、模板回落 |
| QQBot | ✔ | `send_exec_approval`(`qqbot/adapter.py:2701`) | 分片上传、按钮键盘 |
| Weixin | ✔ | — | context_token、AES CDN |
| Yuanbao | ✔ | — | WS + 心跳 + AUTH_BIND |
| Signal | — | — | bodyRanges 样式、附件速率桶 |
| BlueBubbles | — | — | tapback 反应、纯文本 |
| Webhook | — | — | 动态路由、五方言验签 |
| Relay | `authorization_is_upstream=True` | `send_exec_approval`(`relay/adapter.py:1702`) | 一对多 |
| api_server | — | HTTP 审批端点 | OpenAI 兼容 |

`WhatsAppBehaviorMixin` 的契约声明得非常显式(`gateway/platforms/whatsapp_common.py:19-31 @ 863e313`):

```
Mixin contract — the adapter must set these on ``self`` before any of the
mixin's methods are called (typically in ``__init__``):

    self.config        # gateway.config.PlatformConfig
    self.name          # str — adapter name (used in log lines)
    self._dm_policy             # str: "open" | "allowlist" | "disabled"
    self._allow_from            # set[str]
    self._group_policy          # str: "open" | "allowlist" | "disabled"
    self._group_allow_from      # set[str]
    self._mention_patterns      # list[re.Pattern]
    self._reply_prefix          # Optional[str]
```

Python 的 mixin 没有接口检查,所以**把"宿主必须提供什么"写成 docstring 契约**
是唯一的防线。MRO 顺序也必须约束(`ADDING_A_PLATFORM.md:71-74 @ 863e313`):
mixin 必须排在 `BasePlatformAdapter` **之前**,否则基类的 `format_message` 会赢。

## 6. 双栈绑定:一次真实的"可达性"事故

```python
# Why not "0.0.0.0" (the old default) or "::"?
#   - "0.0.0.0" binds IPv4 ONLY. On IPv6-only private networks — notably Fly.io
#     6PN, where an agent's ``<app>.internal`` name resolves to an ``fdaa:…``
#     IPv6 address — an IPv4-only listener is unreachable. That is exactly why
#     hosted-agent webhook routes were publicly unreachable: the edge router
#     reverse-proxies to ``<app>.internal:8644`` over 6PN (IPv6) but the adapter
#     was listening on 0.0.0.0 (v4 only) → connection refused.
#   - "::" is NOT a safe fix: on hosts where the kernel sets IPV6_V6ONLY=1
#     (verified on Fly machines), binding "::" yields an IPv6-ONLY socket, which
#     then breaks the IPv4 loopback health check (``curl 127.0.0.1:8644/health``)
#     and the AF_INET port-conflict probe in connect().
#   - ``None`` asks the event loop to create a listening socket per resolved
#     family, so both 127.0.0.1 (v4) and the 6PN fdaa (v6) are served regardless
#     of the bindv6only sysctl.
DEFAULT_HOST = None
```

(`gateway/platforms/webhook.py:111-129 @ 863e313`)

**故事**:托管环境里 webhook 路由全部不可达。原因是监听在 `0.0.0.0`(仅 IPv4),
而边缘路由器走 IPv6 私网回源 → connection refused。直觉的修法 `"::"` **更糟**:
在 `IPV6_V6ONLY=1` 的内核上它变成纯 IPv6 套接字,反而打断了 IPv4 的
本地健康检查和端口冲突探测。**正解是 `None`** —— 让事件循环按解析出的每个地址族
各建一个监听套接字。

端口冲突探测也随之改了(`gateway/platforms/webhook.py:304-306 @ 863e313`):

```python
        # Do not probe only one address family before binding. With the
        # dual-stack default, an IPv6-only listener can already own this port
        # while 127.0.0.1 still looks free.
```

`SO_REUSEADDR` 的取舍则按平台分叉(`gateway/platforms/webhook.py:307-320 @ 863e313`):
macOS(BSD 语义)下两个 `SO_REUSEADDR` 套接字会**静默瓜分流量且都报告成功**,所以关掉;
Linux 下它只允许越过 TIME_WAIT,关掉会让快速重启在 ~60 秒内绑不上,所以保留默认。

**这是"同一个 socket 选项在两个 OS 上语义不同"的教科书案例。**

## 7. 【文档-代码冲突候选】

**▲ B-17**:`gateway/platforms/whatsapp_cloud.py:14-19 @ 863e313` 的**模块 docstring 自身**:

```
- ``whatsapp.py``      — unofficial Baileys bridge, personal accounts, no
                         public URL needed, account-ban risk.
```

`gateway/platforms/whatsapp.py` 不存在;Baileys 适配器在
`plugins/platforms/whatsapp/adapter.py:381 @ 863e313`。这与 `r7b-10` §6 ▲B-3
是同一次迁移留下的两处滞后(一处在 `ADDING_A_PLATFORM.md`,一处在**代码注释里**)。
本轮据此把 R7 的规律再推进一格:**"接线声明"会说谎,连同一个包内的模块 docstring
也会说谎。**

**◇ B-18**:`gateway/platforms/webhook.py` 支持的**五种签名方言**
(Svix / GitHub / GitLab / 自有 V2 / 自有 V1,`:1040-1130 @ 863e313`)在
`website/docs/**` 未见完整枚举。对"我的 SaaS 能不能直接对接"这个最常见问题,
这是应当文档化的能力清单。

**◇ B-19**:双栈绑定的完整推理(§6,`gateway/platforms/webhook.py:111-129 @ 863e313`)
与 `SO_REUSEADDR` 的平台分叉(`:307-320`)只存在于代码注释。

**◇ B-20**:Signal 附件速率的**本地令牌桶模拟 + 429 反向校准**
(`gateway/platforms/signal_rate_limit.py:2-14 @ 863e313`)无文档记载。

## 8. 【bug 候选】

无新增。§2.2 记录的"V2 嵌套在 V1 判定里会被静默跳过"是**已修**的历史缺陷,
注释保留作为回归说明,不是当前 bug。

## 9. 【重实现要点】

1. **不要试图统一入站**:SSE / webhook / 长轮询 / WebSocket / 子进程各有各的形态;
   只统一"收到之后走哪条路"。
2. **验签必须用原始字节**,不得反序列化后重新序列化。
3. **多方言验签要并列独立分支**,嵌套会让新方言被旧方言的存在性判定吞掉。
4. **常量时间比较前先 encode**,否则一个非 ASCII 头就是 500。
5. **客户端限流 = 本地先验模型 + 服务端 429 反馈校正**,并用锁保证多会话 FIFO 公平。
6. **去重缓存要时间 + 条数双上界**。
7. **样式偏移量的单位要跟平台走**(Signal / Telegram 都是 UTF-16 码元)。
8. **文本变换要保护代码块**:`re.split` 留分隔符 + 奇偶跳过是标准写法。
9. **fd 是网关第一稀缺资源**:收紧连接池空闲期,并确保失败分类不会造成重试泄漏。
10. **监听地址用 `None` 而非 `0.0.0.0` 或 `::`**,让事件循环按地址族各建套接字。
11. **mixin 契约写进 docstring 并约束 MRO 顺序** —— Python 不会替你检查。
12. **重复 5 次以上再抽共享层**,并在 docstring 里记下它替换了谁。
13. **包根 `__init__` 用 PEP 562 延迟导入**,CLI 启动时间是每天付多次的税。
