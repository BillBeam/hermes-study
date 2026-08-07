# r7b-60 · relay 隧道 —— 一个适配器前置任意多个平台

> 底稿。基线 `863e31318553cda8ad61df681d08175364d4164b`。
> 覆盖 `gateway/relay/{__init__,adapter,transport,ws_transport,descriptor,auth,media,command_manifest}.py`。

## 0. 一句话

relay 把"接一个新平台"的成本从**改 16 处核心代码**降到**改 0 处** ——
代价是引入一个进程外对端(connector,另一个仓库、TypeScript 写的),
以及一整套必须逐字节对齐的跨语言协议。

## 1. 从一个场景说起

你想让 Hermes 上 Discord。走内建路径要改 16 个集成点(见 `r7b-01` §3);
走插件路径要写一个完整适配器,处理 Discord 的网关协议、分片、组件交互。

relay 的答案是:**都不做**。你部署一个 connector(对端已经实现了 Discord),
Hermes 侧只跑一个 `RelayAdapter`,注册为 `Platform.RELAY` **一个**枚举值。
connector 把 Discord 消息归一化成 Hermes 的 `MessageEvent` 送过来。

于是问题变成:**一个适配器,怎么表现得像 N 个不同能力的平台?**

## 2. `CapabilityDescriptor`:握手时协商出来的"平台人格"

```
The connector hands a ``CapabilityDescriptor`` to the gateway's ``RelayAdapter``
at handshake time; it tells the adapter which platform it is fronting and which
capabilities to advertise to the ``GatewayStreamConsumer`` (char limit,
draft-streaming, edit/threading support, markdown dialect, length unit). It is
the linchpin of the generalization: one gateway adapter serves Discord,
Telegram, Matrix, Signal, ... without per-platform branching.
```

(`gateway/relay/descriptor.py:3-9 @ 863e313`)

**这正是 `r7b-10` §1 那组能力位的"数据化"**:能力位本来是**方法**(子类覆盖),
在 relay 里变成一个**可序列化的 frozen dataclass**,从对端传过来。
描述符字段与能力位的对应关系写在模块头(`gateway/relay/descriptor.py:15-29 @ 863e313`):

```
- ``max_message_length`` -> ``PlatformEntry.max_message_length`` / adapter
  ``MAX_MESSAGE_LENGTH`` attribute (read by stream_consumer).
- ``len_unit``           -> selects which ``message_len_fn`` the adapter installs
  ("chars" = builtin len; "utf16" = Telegram-style UTF-16 code-unit counting).
- ``supports_draft_streaming`` -> adapter ``supports_draft_streaming()`` probe.
- ``supports_edit``      -> whether edit-based streaming is possible (Discord/
  Telegram yes; Signal/SMS no -> consumer degrades to one-message-per-segment).
```

`frozen=True` 有明确理由(`gateway/relay/descriptor.py:44-48 @ 863e313`):

```python
    """Immutable capability descriptor negotiated at relay handshake.

    Frozen so a descriptor cannot be mutated after handshake — the adapter
    advertises a fixed capability profile for the life of the connection.
    """
```

### 2.1 版本演进:加法式 + 双向兼容

`CONTRACT_VERSION = 1`(`gateway/relay/descriptor.py:38 @ 863e313`),注释规定
"Bump additively (never reinterpret an existing field)"(`:36-37`)。

**新网关 + 老 connector** —— 老 connector 不发新字段,靠 dataclass 默认值兜底。
`supported_ops` 的 fail-open 是这条的典范(`gateway/relay/descriptor.py:80-92 @ 863e313`):

```python
    def supports_op(self, op: str) -> bool:
        """Whether the connector advertises the outbound op ``op``.

        Fail-open for legacy connectors: an empty ``supported_ops`` means the
        connector predates op discovery, so assume the legacy op set (the four
        ops every connector implemented before the field existed). A NEW op
        (e.g. ``get_chat_info``) is therefore only True when explicitly
        advertised — exactly the discovery semantics Phase 1 needs: the gateway
        can probe capability without trying the op and parsing an error.
        """
        if not self.supported_ops:
            return op in self.LEGACY_OPS
        return op in self.supported_ops
```

**"空 = 遗留四件套,而不是空 = 什么都不支持"**。这让能力发现**加进来时不破坏任何人**:
老 connector 继续工作(拿到遗留集),新 op 只在显式声明时才为真。

**老网关 + 新 connector** —— `from_json` 丢弃未知键(`gateway/relay/descriptor.py:101-106 @ 863e313`):

```python
        Unknown keys are ignored (forward-compat: a newer connector may send
        fields this gateway does not know yet); missing optional keys fall back
        to dataclass defaults.
```

**双向兼容 = 未知字段丢弃 + 缺失字段默认值 + 只加不改语义。** 三条缺一不可。

### 2.2 信任边界上的归一化

`from_json` 的输入来自**网络对端**,所以它是一个信任边界:

```python
        # Normalize the chunking bound at the trust boundary. A connector may
        # advertise max_message_length 0 ("no limit"), and a buggy/hostile one
        # may send 0 or a negative; either is a degenerate value that would flow
        # straight into the adapter's MAX_MESSAGE_LENGTH and truncate_message().
        # Map it to the documented 4096 default ...
        if "max_message_length" in filtered:
            try:
                if int(filtered["max_message_length"]) <= 0:
                    filtered["max_message_length"] = 4096
            except (TypeError, ValueError):
                filtered["max_message_length"] = 4096
```

(`gateway/relay/descriptor.py:107-119 @ 863e313`)

**为什么这条重要**:`max_message_length = 0` 会一路流进 `truncate_message()`,
把每条回复截成空串 —— 一个"合法 JSON、类型正确"的值造成全量静默数据丢失。
`supported_ops` 同理,畸形值降级成 `()`(遗留集)而不是抛异常
(`:120-133`),"malformed input never breaks the handshake"。

**可迁移原则**:反序列化边界上,**类型正确不等于取值合理**。每个会流进控制逻辑的
数值都要有"退化值 → 文档化默认值"的归一化。

## 3. 线格式:字段映射就是契约

`_event_from_wire`(`gateway/relay/ws_transport.py:172-286 @ 863e313`)把 connector 的
snake_case 载荷还原成 `MessageEvent`。几处关键决策:

### 3.1 显示名 vs 用户名

```python
        # Native adapters surface the human-facing DISPLAY name as user_name
        # (e.g. Discord `message.author.display_name`); the connector sends the
        # raw platform username as user_name plus optional user_display_name /
        # user_handle enrichments (contract §3). Prefer the display name for
        # parity with native lanes — session keys derive from user_id, never
        # user_name, so this is presentation-only and key-stable.
        user_name=(
            src.get("user_display_name")
            or src.get("user_name")
            or src.get("user_handle")
        ),
```

(`gateway/relay/ws_transport.py:194-204 @ 863e313`)

注释末句是关键安全断言:**会话键只由 `user_id` 推导,永不用 `user_name`**。
所以这个三级回落是纯呈现,改它不会让会话漂移。若会话键用了显示名,
用户改个昵称就换了会话 —— 更糟的是,**改成别人的昵称就能撞进别人的会话**。

### 3.2 上游信任标记:本地盖章,永不读线

```python
        # Authentic upstream-trust signal: this event arrived over the
        # per-instance-authenticated relay WS, so the connector already resolved
        # it to this instance's owner-bound author. ``platform`` is the
        # UNDERLYING platform (e.g. discord), not ``relay`` — authz keys the
        # upstream-trust decision off THIS flag, not off ``platform`` (which
        # would miss because the relay adapter is registered under
        # ``Platform.RELAY``). Stamped here, never read off the wire.
        delivered_via_upstream_relay=True,
```

(`gateway/relay/ws_transport.py:232-240 @ 863e313`)

**"Stamped here, never read off the wire" 是整个 relay 安全模型的支点**。
这个标志的含义是"本事件从已鉴权的 relay WS 上进来",所以它**只能由接收端根据
自己所在的代码路径盖章**。如果它是线上字段,任何能构造 JSON 的人都能自称可信。

配合 `authorization_is_upstream = True`(`r7b-10` §1.1),两者构成完整链条:
传输层鉴权(WS bearer)→ 接收路径盖章 → 授权层据章免除 env allowlist 复判。

### 3.3 平台枚举的回落

```python
    try:
        platform_enum = Platform(platform)
    except ValueError:
        platform_enum = Platform.RELAY
```

(`gateway/relay/ws_transport.py:182-186 @ 863e313`)

connector 声称前置一个 Hermes 不认识的平台时,退回 `Platform.RELAY` 而不是崩溃。
消息类型同理(`:241-244`,未知类型 → `TEXT`)。**未知的枚举值不是错误,是版本差。**

## 4. 帧类型:一条 WS 上跑六种语义

`_handle_frame`(`gateway/relay/ws_transport.py:823-889 @ 863e313`):

| 帧 | 语义 |
|---|---|
| `descriptor` | 能力描述符,**每个 hello 过的身份一帧** |
| `inbound` | 一条归一化消息;带 `bufferId` 时需 ack |
| `going_idle_ack` | 对端确认已转入"仅缓冲"状态(scale-to-zero) |
| `outbound_result` | 对 `requestId` 的应答,唤醒等待的 future |
| `interrupt_inbound` | 对端要求中断某会话 |
| `passthrough_forward` | 对端已在边缘 ACK 过的直通请求 |

### 4.1 多平台描述符累积

```python
            # Phase 1.5 multi-platform: one descriptor frame arrives per hello'd
            # identity. Accumulate them keyed by the descriptor's own platform so
            # the adapter can resolve PER-CHAT capabilities (e.g. Discord's 2000
            # vs Telegram's 4096 max_message_length) instead of collapsing N
            # platforms onto whichever descriptor arrived last.
            if descriptor.platform:
                self._descriptors_by_platform[descriptor.platform] = descriptor
            # The FIRST descriptor of this connection generation is the session
            # default (the primary identity's) — later arrivals must NOT
            # overwrite it, or the scalar capability surface silently becomes
            # last-writer-wins across platforms.
            if self._descriptor is None:
                self._descriptor = descriptor
```

(`gateway/relay/ws_transport.py:831-843 @ 863e313`)

**"一个适配器像 N 个平台"在此落地**:按平台存一张表,加一个"首个描述符即默认"的标量。
没有那句 `if self._descriptor is None`,标量能力面就变成**最后到达者胜**,
Discord 的 2000 字上限会被 Telegram 的 4096 覆盖,回复被 Discord 拒收。

### 4.2 撤销 vs 冷启动竞态

```python
            # Phase 7 Unit 7d-B: a received descriptor means the WS upgrade auth
            # passed and the connector accepted us — record that we've handshaked
            # at least once, so a LATER 4401 close is read as a revocation
            # (opt-out), not a cold-start race.
            self._handshake_succeeded = True
```

(`gateway/relay/ws_transport.py:844-848 @ 863e313`)

**同一个 4401 关闭码有两种含义**:握手前收到 = "密钥还没生效/时钟偏差",该重试;
握手成功后收到 = "凭据被撤销",该停止重连。用"是否曾经握手成功"这一位来区分。
**可迁移原则**:错误码常常一码多义,靠**连接生命周期状态**消歧,而不是靠错误码本身。

### 4.3 缓冲投递的 ack

```python
                # Phase 5 §5.3: a buffered delivery (replayed on reconnect) carries
                # a bufferId; ack it after the handler has durably taken it so the
                # connector advances its delivery-leg buffer cursor (no dup). A live
                # delivery has no bufferId — nothing to ack.
```

(`gateway/relay/ws_transport.py:855-859 @ 863e313`)

**ack 在 handler 返回之后**,不是收到就 ack。这是 at-least-once 的正确姿势:
先持久接收,再推进对端游标。R7 已定案网关只承诺 at-least-once,这里是同一承诺在
relay 侧的兑现。

### 4.4 直通平面:让托管网关不需要公网入口

```python
            # Phase 5 §5.1: a forwarded passthrough-plane request (Discord
            # interaction, Twilio, …) the connector already edge-ACKed. It rides
            # the SAME outbound WS as inbound messages so a hosted gateway needs
            # no public inbound port.
```

(`gateway/relay/ws_transport.py:877-881 @ 863e313`)

Discord 的交互(按钮点击)要求**3 秒内 ACK**,否则用户看到"交互失败"。
托管网关可能在冷启动或跨地域,做不到。解法:**connector 在边缘先 ACK**,
然后把真实请求顺着**已有的出站 WS** 转发进来。网关不需要开任何入站端口。

**这是 relay 架构最大的附加收益**:出站单向连接同时解决了"NAT 后无公网 IP"
与"延迟敏感的边缘 ACK"两个问题。

## 5. 认证:两套 HMAC,必须与 TypeScript 逐字节对齐

```
1. **WS upgrade auth** (gateway → connector): the gateway presents
   ``Authorization: Bearer <token>`` on the ``/relay`` WebSocket upgrade, where
   ``token = make_upgrade_token(gateway_id, secret)``. Mirrors the connector's
   ``relayAuthToken.ts`` ``makeToken`` (``src/core/relayAuthToken.ts``):
   ``base64url(f"{payload}:{exp}:{sig}")`` with
   ``sig = HMAC_SHA256(f"{payload}:{exp}", secret).hexdigest()`` and
   ``payload == gateway_id``.

2. **Inbound delivery signature** (connector → gateway): the connector signs
   each inbound POST with the per-tenant *delivery key*, carried as
   ``x-relay-timestamp`` + ``x-relay-signature`` headers; the gateway verifies
   before accepting the event. ... ``sig = HMAC_SHA256(f"{ts}.{body_json}", key)``
   over the EXACT request body bytes, with a replay-window skew check.
```

(`gateway/relay/auth.py:6-24 @ 863e313`)

几处细节值得抄:

**(a) 多密钥验证列表**(`gateway/relay/auth.py:61-81 @ 863e313`),支持轮换窗口:

```python
    """Constant-time check that ``sig_hex`` is a valid HMAC of ``payload`` under
    ANY of ``secrets`` (rotation window). Length-mismatched candidates are
    skipped without a timing leak.
    """
```

轮换期同时接受新旧密钥,于是**换密钥不作废在途 token**。

**(b) base64url 不带 padding**,为了对齐 Node 的 `Buffer.toString("base64url")`
(`gateway/relay/auth.py:87-92 @ 863e313`);验证侧再补回 padding
(`:118-121`)。跨语言协议里,**编码的边角细节就是协议的一部分**。

**(c) 从右往左切**(`gateway/relay/auth.py:112-113 @ 863e313`):

```python
    Splits from the right so a payload may itself contain colons (mirrors the
    connector's ``verifyToken``).
```

payload 里可能有冒号,所以 `rsplit` 语义必须两侧一致。

**(d) 签名材料是 `f"{ts}.{body_json}"` 且必须是收到的原字节**
(`gateway/relay/auth.py:153-158 @ 863e313`):

```python
    ``body_json`` MUST be the exact request body bytes decoded as UTF-8 — the
    connector signs over the literal serialized body, so the gateway verifies
    over the literal received body (no re-serialization).
```

与 WhatsApp Cloud 的 `X-Hub-Signature-256`(`r7b-50` §2.1)是同一条铁律。

**(e) 时间戳在签名材料内**,配 300 秒偏移窗(`:141-146`、`:170-175`)——
签名同时防篡改和防重放。

## 6. 自举:一个只有 token 的容器如何成为已注册对端

```
Boot-time relay self-provision: mint relay creds in-process, no human, no disk.

Fires when relay is configured (``relay_url()`` set) and NO per-gateway secret
is already present, AND the agent can resolve its own Nous access token. ...
The creds live ONLY in process memory — never written to ``~/.hermes/.env``.
```

(`gateway/relay/__init__.py:566-576 @ 863e313`)

### 6.1 触发条件的选择本身是个教训

```
The trigger is deliberately NOT ``is_managed()``: that means
"package-manager/NixOS-managed" and is False on a NAS-hosted Fly agent (which
sets neither ``HERMES_MANAGED`` nor a ``.managed`` marker), so gating on it
blocked the exact hosted case this is for. The real signal is "you pointed me
at a connector and didn't pin a secret" — which is both NAS-independent and
self-guarding
```

(`gateway/relay/__init__.py:578-585 @ 863e313`)

**故事**:自举原本用 `is_managed()` 做开关。但 `is_managed()` 的语义是
"由包管理器/NixOS 托管",而托管在 Fly 上的 agent 两个标记都不设 —— 于是这个开关
**恰好把它要服务的场景挡在外面**。

修法是换一个**由意图本身推出**的条件:"你给了我 connector 地址,又没钉死密钥"。
三种部署各自落到正确分支(`:586-593`),而且这个条件**自带守卫** ——
运营方钉了密钥就自动跳过,不会覆盖人工配置。

**可迁移原则**:自动化的触发条件应当直接表达"该不该做",而不是借用一个
**碰巧相关**的环境标志。借用的标志会在你没预料的部署形态上失配。

### 6.2 无状态是特性

```
Stateless: process-env creds don't survive a restart, so a hosted container
re-provisions every boot; the connector's rotation window covers a still-
connected prior instance.
```

(`gateway/relay/__init__.py:596-599 @ 863e313`)

凭据只在进程内存里,重启就重新申请。这消除了"凭据文件泄漏"与"凭据文件过期"两类问题,
代价由 §5(a) 的轮换窗口承担 —— 旧实例还连着也不会被踢。

### 6.3 永不抛

```
Returns True if it provisioned, False otherwise. NEVER raises: a provision
failure logs and returns False so the gateway still boots (and
``register_relay_adapter`` will simply dial unauthenticated / be rejected,
rather than the whole gateway crashing).
```

(`gateway/relay/__init__.py:600-604 @ 863e313`)

**一个可选平台的自举失败,不得让整个网关起不来。**

### 6.4 身份来源:两种 IdP

`_resolve_relay_identity_token`(`gateway/relay/__init__.py:491-508 @ 863e313`)
按优先级支持通用 OIDC client_credentials(自建 IdP / 气隙环境)与 Nous Portal(默认)。
前者让 relay 能在**完全不依赖厂商门户**的环境里用起来 —— 对一个开源 harness,
这是"能不能进企业"的分水岭。

## 7. `RelayAdapter`:把描述符变成行为

- `_descriptor_for_chat(chat_id)`(`gateway/relay/adapter.py:175-203 @ 863e313`)
  → 按 chat 解析出该平台的描述符,喂给 `max_message_length_for_chat` /
  `message_len_fn_for_chat` / `supports_draft_streaming`(`:204-216`)。
  **`r7b-10` §1.3 的"每 chat 长度单位"在这里第一次有了非平凡实现。**
- `authorization_is_upstream` 覆盖为 `True`(`gateway/relay/adapter.py:136-148 @ 863e313`)。
- `fronts_platform` / `_platform_is_fronted`(`:598-615`)—— 网关据此把某平台的
  出站路由到 relay。
- `go_dormant`(`:872-897`)—— scale-to-zero,与 `going_idle_ack` 帧配对。
- `_watch_for_revocation`(`:289-320`)—— 独立轮询,配合 §4.2 的 4401 消歧。
- `on_interrupt` → `interrupt_session_activity`(`gateway/relay/adapter.py:617-626 @ 863e313`),
  即**第二层守卫的动作经由 relay 反向进入第一层**(见 `r7b-20` §5.1)。

## 8. 【文档-代码冲突候选】

**◇ B-21**:`transport.py` / `descriptor.py` / `auth.py` 三个模块头都标注
**EXPERIMENTAL**,并给出撤销条件(`gateway/relay/transport.py:18-20 @ 863e313`):

```
EXPERIMENTAL: may change without a deprecation cycle until >=2 Class-1 platforms
validate it. See docs/relay-connector-contract.md.
```

这是全仓少见的**显式稳定性契约**(明确写出"什么条件下才转正")。
`README.md` / `AGENTS.md` 未见对 relay 实验状态的对应提示,
运营方从用户文档看不出这条路径尚未定稿。

**◇ B-22**:`delivered_via_upstream_relay` 的"本地盖章、永不读线"不变量
(`gateway/relay/ws_transport.py:232-240 @ 863e313`)是 relay 授权模型的支点,
仅存在于代码注释。

**◇ B-23**:自举触发条件为何**不用** `is_managed()`(§6.1)的完整推理
只在代码注释里;它同时解释了三种部署形态的分支,是运营方判断
"我的部署会不会自动申请凭据"的唯一依据。

**◇ B-24**:双 IdP 支持(通用 OIDC client_credentials vs Nous Portal,§6.4)
与其环境变量 `GATEWAY_RELAY_IDP_TOKEN_URL` / `_CLIENT_ID` / `_CLIENT_SECRET` / `_SCOPE`
(`gateway/relay/__init__.py:509-512 @ 863e313`)在 `website/docs/**` 未见记载。

> 说明:`tests/gateway/relay/test_contract_doc_conformance.py` 会把代码与
> `docs/relay-connector-contract.md` 对齐,本轮该测试通过(见 `r7b-95`),
> 所以**开发者文档**层面 relay 是全仓一致性最好的一簇;上述 ◇ 均指向
> **用户/运营文档**缺口,而非开发者契约文档。

## 9. 【bug 候选】

无。

## 10. 【重实现要点】

1. **把能力位数据化**:方法覆盖 → 可序列化描述符,是"一个适配器演 N 个平台"的前提。
2. **描述符 frozen**,握手后不可变,能力面在连接生命周期内恒定。
3. **双向兼容三件套**:未知字段丢弃 + 缺失字段默认值 + 只加不改语义。
4. **反序列化边界要做取值归一化**:类型正确 ≠ 取值合理(`max_message_length=0`
   会静默截空所有回复)。
5. **信任标记必须由接收路径盖章,永不从线上读**。
6. **会话键只由稳定 id 推导**,显示名只作呈现。
7. **多身份场景要按 key 存表 + 显式定义标量默认**,否则退化成最后写入者胜。
8. **错误码一码多义时,靠连接生命周期状态消歧**(握手前 4401 = 重试,握手后 = 撤销)。
9. **缓冲投递先持久接收再 ack**,ack 推进对端游标。
10. **出站单向连接可同时解决 NAT 穿透与边缘低延迟 ACK** —— 直通平面复用同一条 WS。
11. **跨语言 HMAC 要对齐到编码细节**(base64url padding、rsplit 语义、签名材料拼接)。
12. **验证用多密钥列表**支持轮换,不作废在途 token。
13. **自动化触发条件要直接表达意图**,不要借用碰巧相关的环境标志。
14. **可选组件的自举失败必须不阻塞主进程启动**。
15. **给实验性契约写明转正条件**,而不是只标 EXPERIMENTAL。
