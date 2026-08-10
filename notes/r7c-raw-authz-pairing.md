# r7c-raw-authz-pairing —— 网关授权层 + DM 配对 + WhatsApp 身份 + 频道目录

> 底稿(证据层)。切片:`gateway/authz_mixin.py`(888)、`gateway/pairing.py`(905)、
> `gateway/whatsapp_identity.py`(206)、`gateway/channel_directory.py`(637)。
> 全部溯源到 `路径:行号 @ 863e313`(基线 commit `863e31318553cda8ad61df681d08175364d4164b`)。
> 本轮已实际运行相关测试(见 §8),11 个测试文件 111 用例全绿。

---

## 0. 一句话

授权是**默认拒绝的"并集"模型**(任一凭据命中即放行,没有拒绝列表);配对码**只存盐化
SHA-256、常数时间比较**,批准路径**只有 CLI 与已认证 dashboard 两条**,聊天里回码永远不能配对
——这一条直接坐实 R7 的 A4 定案。

---

## 1. `authz_mixin.py`:授权层级

### 1.1 它是什么、被谁 mix

模块本身是 god-file 拆分的产物,自称"行为中性搬运":

`gateway/authz_mixin.py:1-16 @ 863e313`
```python
"""User-authorization methods for ``GatewayRunner``.

Extracted from ``gateway/run.py`` as part of the god-file decomposition campaign
(``~/.hermes/plans/god-file-decomposition.md``, Phase 3 mechanical mixin lifts).
This mixin holds the inbound-message authorization cluster: whether a user/chat
is allowed to talk to the agent, the per-adapter DM policy, and the
unauthorized-DM behavior.

Behavior-neutral: every method is lifted verbatim from ``GatewayRunner``.
``self.*`` calls resolve unchanged via the MRO. Neutral dependencies import at
module top; the module-level ``logger`` is imported lazily inside the one method
that uses it (``from gateway.run import logger`` resolves at call time, when
``gateway.run`` is fully loaded) so this module never imports ``gateway.run`` at
import time -> no import cycle. The lazy import preserves the exact logger name
(``"gateway.run"``) so log records are unchanged.
"""
```

**宿主类唯一**(全仓 grep `GatewayAuthorizationMixin` 只有三处命中:定义、import、继承):

`gateway/run.py:5759 @ 863e313`
```python
class GatewayRunner(GatewayAuthorizationMixin, GatewayKanbanWatchersMixin, GatewaySlashCommandsMixin):
```

**为什么用 mixin 而不是独立服务**:方法体大量依赖 `self.adapters` / `self._profile_adapters` /
`self.pairing_store` / `self.config` / `self._warned_telegram_group_users_legacy` 这些 runner 实例
状态(`gateway/authz_mixin.py:118, 120, 174, 380, 384, 272, 721`),抽成服务要么把这堆状态全部作为参数传进去,
要么反向持有 runner 引用。mixin 是**零风险的机械切分**——`self.*` 走 MRO 解析,行为逐字不变;
拆分目的是缩小 `run.py`(2.6 万行)的体积,不是引入抽象层。代价:`authz_mixin` 无法脱离 runner
单测,测试里普遍用 `object.__new__(GatewayRunner)` 造裸壳(代码里多处为此加 `getattr` 兜底,
见 `gateway/authz_mixin.py:150-151, 238-240`)。

### 1.2 判定的输入与配置来源

**输入是一个 `SessionSource` 对象**(`gateway/session.py` 定义),不是散装的 platform+user_id:

`gateway/authz_mixin.py:386 @ 863e313`
```python
    def _is_user_authorized(self, source: SessionSource) -> bool:
```

用到的字段:`source.platform`、`source.user_id`、`source.user_name`、`source.chat_id`、
`source.chat_type`、`source.profile`、`source.is_bot`、`source.role_authorized`、
`source.delivered_via_upstream_relay`、以及非序列化的 `source._transport_adapter_ref`。

其中两个是**适配器写入的信任标记**,定义在 SessionSource 上:

`gateway/session.py:179 @ 863e313`
```python
    role_authorized: bool = False  # True when adapter granted access via role (not user ID)
```

`gateway/session.py:217 @ 863e313`
```python
    delivered_via_upstream_relay: bool = False
```

`delivered_via_upstream_relay` 的注释点名它是**故意不上线的**(不能被对端伪造、不能从持久化恢复):

`gateway/session.py:206-216 @ 863e313`
```python
    # Internal, wire-INVISIBLE trust signal: True when this event was delivered
    # to the gateway over the per-instance-authenticated relay WebSocket (the
    # Team Gateway connector). The connector authenticates the gateway's socket
    # with a per-instance secret and resolves owner-only author bindings BEFORE
    # delivering, so a relay-delivered event is already authorized as this
    # instance's bound user. ``platform`` carries the UNDERLYING platform
    # (e.g. ``discord``) for session-keying/egress, NOT ``relay`` — so authz
    # must key the upstream-trust decision off THIS flag, not off ``platform``.
    # Set locally by the relay transport (``ws_transport._event_from_wire``);
    # deliberately excluded from ``to_dict``/``from_dict`` so a peer can never
    # forge it across the wire or have it restored from persistence.
```

`_transport_adapter_ref` 是**进程内 weakref**,由基类 `build_source` 挂上:

`gateway/platforms/base.py:6664-6668 @ 863e313`
```python
        # In-process transport provenance is deliberately not serialized by
        # SessionSource.to_dict(). The live receiving adapter is authoritative
        # for this turn even when profile_routes selects a different runtime.
        source._transport_adapter_ref = weakref.ref(self)
        return source
```

**配置来源有四条路**,由两个 helper 收口:

1. `_auth_env(name)` —— profile secret scope 优先,**miss 时回落 `os.environ`**
   (`gateway/authz_mixin.py:31-43`);
2. `_platform_gate_env(name)` —— multiplex 下 scope **权威**,miss 直接返回 default,
   **不回落 `os.environ`**(`gateway/authz_mixin.py:46-72`);
3. `config.platforms[platform].extra`(YAML,`gateway/authz_mixin.py:272-281` 等);
4. 活体 adapter 的已解析属性(`adapter._dm_policy` / `_group_policy` / `_groups` /
   `_allow_from` / `config.extra`)。

`_platform_gate_env` 的存在理由(#72348)写得很清楚:

`gateway/authz_mixin.py:46-58 @ 863e313`
```python
def _platform_gate_env(name: str, default: str = "") -> str:
    """Read a platform allow/deny gate env var with per-profile isolation.

    Like ``_auth_env`` but authoritative under multiplex: when a profile
    secret scope is installed AND multiplexing is active, a key absent from
    the scope returns ``default`` instead of falling through to
    ``os.environ``. Under multiplex the process env may hold ANOTHER
    profile's first-writer-bridged value (the YAML→env bridges in the
    Discord/Telegram adapters' ``_apply_yaml_config`` are first-writer-wins),
    so falling through would leak profile A's allowlist into profile B
    (issue #72348). Single-profile deployments — no scope installed, or
    multiplex off — behave exactly like the legacy ``os.getenv`` read.
    """
```

### 1.3 层级枚举表(按 `_is_user_authorized` 实际执行顺序)

| # | 层名 | 判定位置 | 命中结果 | 输入依据 | env 读法 |
|---|------|----------|----------|----------|----------|
| 0 | 系统平台豁免(HomeAssistant / Webhook) | `gateway/authz_mixin.py:403-404` | `True` | `source.platform` | — |
| 1 | 上游已授权(relay / `authorization_is_upstream`) | `gateway/authz_mixin.py:435-439` | `True` | `delivered_via_upstream_relay` **或** adapter flag | — |
| 2 | 群/论坛/频道**按 chat_id** 授权(env) | `gateway/authz_mixin.py:453-467` | `True` | `chat_type ∈ {group,forum,channel}` + `chat_id` | `_platform_gate_env` |
| 3 | 群 chat_id 授权(config.yaml `extra.group_allowed_chats`) | `gateway/authz_mixin.py:475-485` | `True` | 活体 adapter 的 `config.extra` | — |
| 4 | 机器人放行(`{PLATFORM}_ALLOW_BOTS ∈ {mentions,all}`) | `gateway/authz_mixin.py:493-502` | `True` | `source.is_bot` | `_platform_gate_env` |
| 5 | **无 user_id → 拒绝** | `gateway/authz_mixin.py:504-505` | `False` | `user_id` 为空 | — |
| 6 | 单平台放行一切(`{PLATFORM}_ALLOW_ALL_USERS`) | `gateway/authz_mixin.py:569-571` | `True` | — | `_auth_env` |
| 7 | 适配器已校验的角色授权(Discord role) | `gateway/authz_mixin.py:578-579` | `True` | `source.role_authorized is True` | — |
| 8 | **配对批准表**(PairingStore) | `gateway/authz_mixin.py:595-598` | `True` | platform + user_id | 文件 |
| 9a | 无任何 env 名单 → 适配器自有策略(仅 `allowlist`) | `gateway/authz_mixin.py:609-674` | `True/False` | `dm_policy`/`group_policy`/每群 `allow_from` | — |
| 9b | 无任何 env 名单 → `extra.allow_from` / `group_allow_from` | `gateway/authz_mixin.py:679-689` | `True` | 活体 adapter `config.extra` | — |
| 9c | 无任何 env 名单 → `GATEWAY_ALLOW_ALL_USERS` | `gateway/authz_mixin.py:691` | bool | — | `_auth_env` |
| 10 | 群 chat_id 名单(env,`{group,forum}`) | `gateway/authz_mixin.py:696-701` | `True` | `chat_type ∈ {group,forum}` | `_auth_env`(见 601-607) |
| 11 | Telegram 旧格式兼容(`-` 开头当 chat_id) | `gateway/authz_mixin.py:709-731` | `True` | 值以 `-` 开头 | `_auth_env` |
| 12 | 用户名单并集(平台名单 ∪ 群用户名单 ∪ 全局名单),含 `*` 通配 | `gateway/authz_mixin.py:737-748` | `True` | user_id | `_auth_env` |
| 13 | 别名扩展后再比一次(WhatsApp / SimpleX / `@` 前缀) | `gateway/authz_mixin.py:750-783` | bool | user_id 别名集 | — |
| 14 | **兜底:拒绝** | `gateway/authz_mixin.py:783`(交集为空) | `False` | — | — |

> **注意层 5 的位置**:2/3/4 三层被**故意提到 `if not user_id` 之前**,因为 Telegram 匿名管理员帖、
> 频道广播、Slack Workflow Builder 的 `subtype=bot_message` 都没有 `user_id`,但运营者显式列了 chat
> 就该放行。代码明写了这个理由:
>
> `gateway/authz_mixin.py:443-452 @ 863e313`
> ```python
>         # Telegram (and similar) authorize entire group/forum/channel chats
>         # by chat ID via TELEGRAM_GROUP_ALLOWED_CHATS / QQ_GROUP_ALLOWED_USERS.
>         # That allowlist is chat-scoped, so it must work even when
>         # source.user_id is None — Telegram emits anonymous-admin posts,
>         # sender_chat traffic, and channel broadcasts with no `from_user`,
>         # and an operator who explicitly listed the chat expects those to
>         # be honored. Run this check before the no-user-id guard below so
>         # documented behavior matches reality
>         # (website/docs/reference/environment-variables.md,
>         # website/docs/user-guide/messaging/telegram.md).
> ```

### 1.4 owner / admin 概念:**不存在**

`_is_user_authorized` 只有**布尔一档**:授权 / 不授权。没有 owner、没有 admin、没有分级权限。
"owner" 在这一簇里只是**外部角色**(拿着 shell 或 dashboard 密码的人)——它体现为
**批准动作只能从 CLI/dashboard 发起**(§2.5),而不是消息平台上的某个用户 id。

- **群组 vs DM 的区别不是权限等级,而是不同的名单维度**:
  - DM:`{PLATFORM}_ALLOWED_USERS` / `GATEWAY_ALLOWED_USERS` / 配对表;
  - 群:额外多出 `{PLATFORM}_GROUP_ALLOWED_USERS`(按发送者 id)与
    `{PLATFORM}_GROUP_ALLOWED_CHATS`(按 chat id)。
- 群名单**不反向蕴含 DM 权限**,注释明说:

`gateway/authz_mixin.py:733-736 @ 863e313`
```python
        # Check if user is in any allowlist. In group/forum chats,
        # TELEGRAM_GROUP_ALLOWED_USERS is the scoped allowlist and should not
        # imply DM access; TELEGRAM_ALLOWED_USERS remains the platform-wide
        # allowlist and still works everywhere for backward compatibility.
```
  实现上通过 604 行的条件读取达成:`group_user_allowlist` **只在 group/forum 时才被读入**,
  DM 场景下它是空串,自然不进 737-741 的并集。

### 1.5 组合逻辑:全是"或",没有"且",也没有拒绝列表

`gateway/authz_mixin.py:737-748` 把三份名单 `update` 进同一个 `allowed_ids` 集合,再与 `check_ids` 求交:

`gateway/authz_mixin.py:737-748 @ 863e313`
```python
        allowed_ids = set()
        if platform_allowlist:
            allowed_ids.update(uid.strip() for uid in platform_allowlist.split(",") if uid.strip())
        if group_user_allowlist:
            allowed_ids.update(uid.strip() for uid in group_user_allowlist.split(",") if uid.strip())
        if global_allowlist:
            allowed_ids.update(uid.strip() for uid in global_allowlist.split(",") if uid.strip())

        # "*" in any allowlist means allow everyone (consistent with
        # SIGNAL_GROUP_ALLOWED_USERS precedent)
        if "*" in allowed_ids:
            return True
```

**全仓在 `_is_user_authorized` 中没有任何 deny-list / block-list 分支**:没有
`{PLATFORM}_BLOCKED_USERS`、没有 `denied_from`。唯一"负向"的东西是 `dm_policy: disabled`
(适配器 intake 层直接不转发,`gateway/platforms/whatsapp_common.py:256-257`),那属于
**平台级开关**而不是用户级黑名单。

⇒ **优先级问题无解也无须解**:因为不存在两份冲突的名单。任何一条命中即 `return True`,
剩下的分支不再执行。这是设计取舍:**运营心智极简(加一个人=往任一名单加一行)**,
代价是**无法"允许全组但排除某人"**——想排除只能改成显式白名单。

配对表与名单也是**并集**,注释专门解释了这不是绕过:

`gateway/authz_mixin.py:581-594 @ 863e313`
```python
        # Check pairing store. A pairing entry is a first-class authorization
        # grant, created only by a trusted operator approving a pairing code
        # (hermes gateway pairing approve / the authenticated dashboard) — an
        # inbound sender can never reach approve_code, so this is not an
        # attacker-controlled path. Honored as a UNION with the allowlist: a
        # paired user is authorized regardless of the allowlist, and when an
        # allowlist IS configured, operator approval also writes the user into
        # that allowlist (see PairingStore._approve_user), keeping a single
        # operator-visible source of truth. (#23778: the original bypass was the
        # inbound message/approval-button gate, not this gate; that gate is
        # fixed separately.)
        # In multiplex gateways, route to the per-profile PairingStore so each
        # profile's whitelist is isolated; falls back to the global store when
        # the source has no profile or the profile isn't registered.
```

### 1.6 安全默认值:**封闭**(但有三处例外必须点名)

**主线是封闭的。** 什么都不配 →`_is_user_authorized` 走到 691 行:

`gateway/authz_mixin.py:690-691 @ 863e313`
```python
            # No allowlists configured -- check global allow-all flag
            return _auth_env("GATEWAY_ALLOW_ALL_USERS").lower() in {"true", "1", "yes"}
```
未设 `GATEWAY_ALLOW_ALL_USERS` → `False`。启动时会 warn 一次:

`gateway/run.py:10884-10892 @ 863e313`
```python
        if not _any_allowlist and not _allow_all:
            logger.warning(
                "No env user allowlists configured. Messaging platforms default to "
                "pairing/allowlist policies and will deny unknown senders unless you "
                "configure platform allowlists (e.g., TELEGRAM_ALLOWED_USERS=your_id) "
                "or explicitly opt in with GATEWAY_ALLOW_ALL_USERS=true plus "
                "dm_policy/group_policy: open on the platform."
            )
```

**三处例外(即"信任委派",不是 fail-open):**

1. **HomeAssistant / Webhook 无条件 True**——理由是这两条通道的认证发生在别处
   (HASS_TOKEN、HMAC 签名):

`gateway/authz_mixin.py:398-404 @ 863e313`
```python
        # Home Assistant events are system-generated (state changes), not
        # user-initiated messages.  The HASS_TOKEN already authenticates the
        # connection, so HA events are always authorized.
        # Webhook events are authenticated via HMAC signature validation in
        # the adapter itself — no user allowlist applies.
        if source.platform in {Platform.HOMEASSISTANT, Platform.WEBHOOK}:
            return True
```

2. **relay 上游授权无条件 True**——`is True` 的严格身份比较是防 MagicMock 自动真值:

`gateway/authz_mixin.py:431-439 @ 863e313`
```python
        # ``is True`` (not just truthiness): the marker is a real bool on a
        # SessionSource, and an explicit identity check refuses to authorize a
        # non-bool stand-in (e.g. a MagicMock attribute auto-vivifies truthy in
        # tests) — defensive against accidental fail-open.
        if source.delivered_via_upstream_relay is True or self._adapter_authorization_is_upstream(
            source.platform,
            profile=adapter_profile,
        ):
            return True
```

3. **`{PLATFORM}_ALLOW_ALL_USERS` / `GATEWAY_ALLOW_ALL_USERS`**——显式 opt-in。

**最精彩的一处是"曾经 fail-open、后被修掉"的 #34515**:自有策略适配器(WeCom / Weixin /
Yuanbao / QQBot / WhatsApp)在 intake 层就按 `dm_policy` 拦过一道,网关本想"既然它到了网关就说明
它通过了适配器的检查"。但适配器的 `open` 策略是转发一切,这样读就是 fail-open:

`gateway/authz_mixin.py:609-632 @ 863e313`
```python
        if not platform_allowlist and not group_user_allowlist and not group_chat_allowlist and not global_allowlist:
            # No env allowlist configured. Adapters that own their own
            # config-driven access policy (dm_policy / group_policy /
            # allow_from / group_allow_from) gate access at intake, so for those
            # platforms we can honor the adapter's decision instead of the
            # env-only default-deny below -- but ONLY when that decision was an
            # actual allowlist restriction.
            #
            # The adapters default dm_policy / group_policy to "open", which
            # forwards EVERY sender. Reading "reached the gateway" as
            # authorization in that case would admit the whole external network
            # with no operator-configured allowlist -- the fail-open SECURITY.md
            # §2.6 forbids ("an allowlist is required for every enabled
            # network-exposed adapter ... code paths that fail open when no
            # allowlist is configured are code bugs"). "disabled" never
            # forwards, and "pairing" forwards unpaired DMs only so the gateway
            # can run its pairing handshake (the pairing-store check above
            # already denied this sender). So trust the adapter only when its
            # effective policy for THIS chat type is "allowlist"; for "open" /
            # "pairing" / anything else, fall through to default-deny, where
            # GATEWAY_ALLOW_ALL_USERS, the per-platform {PLATFORM}_ALLOW_ALL_USERS
            # flag (checked above), and the pairing flow remain the explicit
            # opt-ins to broader access. (#34515 follow-up: trusting "open" was a
            # fail-open.)
```

**#34515 的第二段**(同一编号的后续修复):即使策略是 `allowlist`,也不能只看"它到了网关"——
配对 revoke 会清掉 `WHATSAPP_ALLOWED_USERS`,而适配器构造时快照的 `_allow_from` 还留着旧值:

`gateway/authz_mixin.py:653-674 @ 863e313`
```python
                if effective_policy == "allowlist":
                    # Trust allowlist intake only when the live adapter still
                    # allowlists this sender. Pairing revoke can clear
                    # WHATSAPP_ALLOWED_USERS while a construction-time
                    # ``_allow_from`` snapshot would otherwise keep authorizing
                    # until restart; re-check when the adapter exposes a DM
                    # allowlist helper. Adapters without that helper keep the
                    # historical "reached the gateway under allowlist policy"
                    # rubber-stamp (#34515).
                    if source.chat_type not in {"group", "forum", "channel"}:
                        adapter = self._authorization_adapter(
                            source.platform,
                            profile=adapter_profile,
                        )
                        dm_check = (
                            getattr(adapter, "_is_dm_allowed", None)
                            if adapter is not None
                            else None
                        )
                        if callable(dm_check):
                            return bool(dm_check(user_id))
                    return True
```

还有一道**启动期硬闸**:自有策略平台若 `dm_policy`/`group_policy` 为 `open` 而没有 allow-all
opt-in,**网关拒绝启动**:

`gateway/run.py:2428-2456 @ 863e313`
```python
def _own_policy_open_startup_violation(config) -> Optional[str]:
    """Return a startup-abort reason when open policy lacks allow-all opt-in."""
    for platform, platform_config in getattr(config, "platforms", {}).items():
        if not getattr(platform_config, "enabled", False):
            continue
        open_env = _OWN_POLICY_OPEN_ENV.get(platform)
        if not open_env:
            continue
        dm_env, group_env, allow_all_env = open_env
        extra = getattr(platform_config, "extra", None) or {}
        dm_policy = str(
            extra.get("dm_policy")
            or (_getenv(dm_env, "pairing") if dm_env else "pairing")
        ).strip().lower()
```
命中后 `gateway/run.py:10902-10913` 打 error 并 `_request_clean_exit(reason)`。

### 1.7 多 profile 隔离:适配器解析链(fail-closed)

`_authorization_adapter` 是**最容易出事的一环**——挑错适配器会让回复从错误的 bot 发出去。
它对"有 profile 标记但注册表里没有该 profile"的情况**明确 fail closed**:

`gateway/authz_mixin.py:120-128 @ 863e313`
```python
            profile_adapters = getattr(self, "_profile_adapters", None) or {}
            if profile_name in profile_adapters:
                return profile_adapters[profile_name].get(platform)
            # Fail closed: a stamped secondary profile with no registry entry
            # (e.g. its adapter failed to connect) must NOT fall back to the
            # default profile's adapter — that sends replies out the wrong bot.
            return None
        adapters = getattr(self, "adapters", None) or {}
        return adapters.get(platform)
```

而 `_adapter_for_source` 有一条**relay 专用旁路**:relay 消息的 `source.platform` 是**底层平台**
(discord/slack),但真正能发出去的只有那一个 `RelayAdapter`:

`gateway/authz_mixin.py:143-149 @ 863e313`
```python
        if getattr(source, "delivered_via_upstream_relay", False) is True:
            # One process-level RelayAdapter owns the connector socket for all
            # multiplexed profiles. Secondary profiles intentionally do not
            # register their own relay adapters, so profile-aware lookup would
            # fail and suppress streamed delivery for those profiles.
            adapters = getattr(self, "adapters", None) or {}
            return adapters.get(Platform.RELAY)
```

`_pairing_store_for` 走 per-profile 配对库,缺省回落全局库:

`gateway/authz_mixin.py:380-384 @ 863e313`
```python
        per_profile = getattr(self, "pairing_stores", None) or {}
        profile = getattr(source, "profile", None)
        if profile and profile in per_profile:
            return per_profile[profile]
        return getattr(self, "pairing_store", None)
```
两个字段的产地:`gateway/run.py:6221-6222`(全局 + 空 map)、`gateway/run.py:13255-13261`
(为每个 served profile 建 store,active profile 复用全局的)。

### 1.8 `_get_unauthorized_dm_behavior`:陌生人 DM 怎么处理

**取值只有两个,不是四个。** `unauthorized_dm_behavior` 的合法值集合硬编码在:

`gateway/config.py:198-203 @ 863e313`
```python
def _normalize_unauthorized_dm_behavior(value: Any, default: str = "pair") -> str:
    """Normalize unauthorized DM behavior to a supported value."""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"pair", "ignore"}:
            return normalized
    return default
```
默认值:`gateway/config.py:941 @ 863e313`
```python
    unauthorized_dm_behavior: str = "pair"  # "pair" or "ignore"
```

> **四取值的是另一个东西**:适配器的 `dm_policy ∈ {open, allowlist, disabled, pairing}`
> (`authz_mixin.py:254-255` 的 docstring 列举)。两者在
> `_get_unauthorized_dm_behavior:837-847` 处**映射**:`pairing → "pair"`,
> `allowlist|disabled → "ignore"`,`open` 不表态(落到下一步)。

六级解析顺序,docstring 与代码一致:

`gateway/authz_mixin.py:791-807 @ 863e313`
```python
        """Return how unauthorized DMs should be handled for a platform.

        Resolution order:
        1. Explicit per-platform ``unauthorized_dm_behavior`` in config — always wins.
        2. Email defaults to ``"ignore"`` unless explicitly opted into
           pairing. Inboxes may contain arbitrary unread human messages, so
           replying with pairing codes is not a safe platform default.
        3. Explicit global ``unauthorized_dm_behavior`` in config — wins for
           chat-shaped platforms when no per-platform override is set.
        4. When an adapter-level DM policy opts into pairing or silent drop, honor it.
        5. When an allowlist (``PLATFORM_ALLOWED_USERS``,
           ``PLATFORM_GROUP_ALLOWED_USERS`` / ``PLATFORM_GROUP_ALLOWED_CHATS``,
           or ``GATEWAY_ALLOWED_USERS``) is configured, default to ``"ignore"`` —
           the allowlist signals that the owner has deliberately restricted
           access; spamming unknown contacts with pairing codes is both noisy
           and a potential info-leak. (#9337)
        6. No allowlist and no explicit config → ``"pair"`` (open-gateway default).
        """
```

**#9337 的设计取舍**:配了名单 ⇒ 运营者是想收紧的 ⇒ 给陌生人回配对码既吵又泄露"这里有个 bot"。
所以 **`pair` 只在"完全没配名单的开放网关"上生效**(879-888)。

---

## 2. `pairing.py`:配对码全生命周期

### 2.1 设计意图与安全参数(模块头)

`gateway/pairing.py:1-19 @ 863e313`
```python
"""
DM Pairing System

Code-based approval flow for authorizing new users on messaging platforms.
Instead of static allowlists with user IDs, unknown users receive a one-time
pairing code that the bot owner approves via the CLI.

Security features (based on OWASP + NIST SP 800-63-4 guidance):
  - 8-char codes from 32-char unambiguous alphabet (no 0/O/1/I)
  - Cryptographic randomness via secrets.choice()
  - 1-hour code expiry
  - Max 3 pending codes per platform
  - Rate limiting: 1 request per user per 10 minutes
  - Lockout after 5 failed approval attempts (1 hour)
  - File permissions: chmod 0600 on all data files
  - Codes are never logged to stdout

Storage: ~/.hermes/pairing/
"""
```

常量集中在顶部,**每一个都是可调的安全参数**:

`gateway/pairing.py:46-59 @ 863e313`
```python
# Unambiguous alphabet -- excludes 0/O, 1/I to prevent confusion
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8

# Timing constants
CODE_TTL_SECONDS = 3600             # Codes expire after 1 hour
RATE_LIMIT_SECONDS = 600            # 1 request per user per 10 minutes
LOCKOUT_SECONDS = 3600              # Lockout duration after too many failures

# Limits
MAX_PENDING_PER_PLATFORM = 3        # Max pending codes per platform
MAX_FAILED_ATTEMPTS = 5             # Failed approvals before lockout

PAIRING_DIR = get_hermes_dir("platforms/pairing", "pairing")
```

**熵**:32^8 = 2^40 ≈ 1.1×10^12。配合 5 次失败锁定 1 小时,在线爆破不可行。
但注意 **`ALPHABET` 只有 32 个字符是为了人类抄写**(去掉 0/O、1/I),这是可用性对熵的让步:
若用完整 base32(含 0/1)也只是 2^40,差别不大;真正的防线是锁定,不是熵。

### 2.2 生成:明文只在内存里活一瞬

`gateway/pairing.py:609-663 @ 863e313`
```python
    def generate_code(
        self, platform: str, user_id: str, user_name: str = ""
    ) -> Optional[str]:
        """
        Generate a pairing code for a new user.

        Returns the code string, or None if:
          - User is rate-limited (too recent request)
          - Max pending codes reached for this platform
          - User/platform is in lockout due to failed attempts

        The code is NOT stored in plaintext.  Only a salted SHA-256 hash is
        persisted so that reading the pending file does not reveal codes.
        """
        with self._lock:
            self._cleanup_expired(platform)
            normalized_user_id = self._normalize_user_id(platform, user_id)

            # Check lockout
            if self._is_locked_out(platform):
                return None

            # Check rate limit for this specific user
            if self._is_rate_limited(platform, user_id):
                return None

            # Check max pending
            pending = self._load_json(self._pending_path(platform))
            if len(pending) >= MAX_PENDING_PER_PLATFORM:
                return None

            # Generate cryptographically random code
            code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))

            # Hash the code with a random salt before storing
            salt = os.urandom(16)
            code_hash = self._hash_code(code, salt)

            # Use a unique entry id as the key (not the code itself)
            entry_id = secrets.token_hex(8)

            # Store pending request with hashed code
            pending[entry_id] = {
                "hash": code_hash,
                "salt": salt.hex(),
                "user_id": normalized_user_id,
                "user_name": user_name,
                "created_at": time.time(),
            }
            self._save_json(self._pending_path(platform), pending)

            # Record rate limit
            self._record_rate_limit(platform, user_id)

            return code
```

### 2.3 【明确回答】配对码**是哈希存储的**,不是明文

- **哈希算法**:每条记录**独立 16 字节随机盐** + SHA-256:

`gateway/pairing.py:580-583 @ 863e313`
```python
    @staticmethod
    def _hash_code(code: str, salt: bytes) -> str:
        """Hash a pairing code with the given salt using SHA-256."""
        return hashlib.sha256(salt + code.encode("utf-8")).hexdigest()
```

- **文件里的键不是码**,而是独立的 `secrets.token_hex(8)` 请求 id(`gateway/pairing.py:648`);
- **比较是常数时间**,用 `secrets.compare_digest`:

`gateway/pairing.py:711-715 @ 863e313`
```python
                candidate_hash = self._hash_code(code, salt)
                if secrets.compare_digest(candidate_hash, entry["hash"]):
                    matched_key = entry_id
                    matched_entry = entry
                    break
```

- 测试双重钉住(§8):`test_pending_file_contains_hash_and_salt` 断言 hash 是 64 位 hex、
  salt 是 32 位 hex、**明文码既不作 key 也不作任何 value**;`test_plaintext_code_not_stored`
  直接断言 `code not in raw_text`。

> **取舍点**:SHA-256 无 KDF 拉伸。理由成立——8 字符定长高熵随机码不是人选密码,离线爆破对手
> 拿到 pending.json 时通常已经拿到了整个 `~/.hermes`(里面有真凭据),而且码 1 小时就过期。
> 用 bcrypt/argon2 只会给每次 approve 增加延迟,不换来实际安全。

### 2.4 有效期 / 一次性 / 限速 / 锁定

| 机制 | 实现 | 行号 | 粒度 |
|------|------|------|------|
| 有效期 1h | `_cleanup_expired` 在 generate/approve/list 入口各调一次 | `gateway/pairing.py:871-895`;调用点 `624, 681, 754, 782` | 每平台 |
| 一次性 | `_finish_approval` 先 `del pending[matched_key]` 再落盘 | `gateway/pairing.py:589-590` | 每条 |
| 单用户限速 10min | `_is_rate_limited` 按 `{platform}:{alias}` 查时间戳 | `gateway/pairing.py:816-824` | 每用户(含别名) |
| 待批上限 3 | `len(pending) >= MAX_PENDING_PER_PLATFORM` | `gateway/pairing.py:637-638` | **每平台(全局)** |
| 爆破锁定 5 次/1h | `_record_failed_attempt` | `gateway/pairing.py:842-854` | **每平台(全局)** |
| 成功即清零 | `_reset_failed_attempts` | `gateway/pairing.py:856-867`,调用点 `598` | 每平台 |

**一次性**是"删了才批"的顺序,不是标志位:

`gateway/pairing.py:585-607 @ 863e313`
```python
    def _finish_approval(
        self, platform: str, pending: dict, matched_key: str, matched_entry: dict
    ) -> dict:
        """Remove a pending request and approve its user. Must hold self._lock."""
        del pending[matched_key]
        self._save_json(self._pending_path(platform), pending)

        # A successful approval proves the requester is legitimate, so the
        # brute-force failure streak must not carry over. Without this,
        # isolated mistyped codes accumulate across the gateway's lifetime
        # (the counter is persisted in _rate_limits.json and only ever
        # reset when a lockout fires) and eventually trip a spurious
        # lockout on a single fresh typo — rejecting even a valid code.
        self._reset_failed_attempts(platform)
```
这段注释本身就是一次事故复盘:计数器持久化在 `_rate_limits.json`,**只在锁定触发时才归零**;
没有成功重置的话,几个月里零星打错的码会累加,最后某天一次手误就触发莫名其妙的锁定。

**锁定必须在 pending 查找之前**——否则锁定形同虚设(已发出去的码照样能批):

`gateway/pairing.py:684-690 @ 863e313`
```python
            # Lockout check — must run before the pending lookup so a
            # valid code (e.g. one already sitting in pending) cannot be
            # accepted once the lockout fires. Without this, the lockout
            # only blocks `generate_code`, not `approve_code` — nullifying
            # the brute-force protection for any code already issued.
            if self._is_locked_out(platform):
                return None
```

锁定实现(注意它同时把 `_failures` 归零,所以是"每 5 次锁 1 小时",不是"第 5 次之后永远锁"):

`gateway/pairing.py:842-854 @ 863e313`
```python
    def _record_failed_attempt(self, platform: str) -> None:
        """Record a failed approval attempt. Triggers lockout after MAX_FAILED_ATTEMPTS."""
        limits = self._load_json(self._rate_limit_path())
        fail_key = f"_failures:{platform}"
        fails = limits.get(fail_key, 0) + 1
        limits[fail_key] = fails
        if fails >= MAX_FAILED_ATTEMPTS:
            lockout_key = f"_lockout:{platform}"
            limits[lockout_key] = time.time() + LOCKOUT_SECONDS
            limits[fail_key] = 0  # Reset counter
            print(f"[pairing] Platform {platform} locked out for {LOCKOUT_SECONDS}s "
                  f"after {MAX_FAILED_ATTEMPTS} failed attempts", flush=True)
        self._save_json(self._rate_limit_path(), limits)
```
> 这是全文件唯一的 `print`;**它不打码**,符合模块头"Codes are never logged to stdout"。

**限速的键含别名**,所以 WhatsApp 用户不能靠 LID↔手机号两种形态各拿一次码:

`gateway/pairing.py:816-833 @ 863e313`
```python
    def _is_rate_limited(self, platform: str, user_id: str) -> bool:
        """Check if a user has requested a code too recently."""
        limits = self._load_json(self._rate_limit_path())
        for alias in self._user_id_aliases(platform, user_id):
            key = f"{platform}:{alias}"
            last_request = limits.get(key, 0)
            if (time.time() - last_request) < RATE_LIMIT_SECONDS:
                return True
        return False

    def _record_rate_limit(self, platform: str, user_id: str) -> None:
        """Record the time of a pairing request for rate limiting."""
        limits = self._load_json(self._rate_limit_path())
        now = time.time()
        for alias in self._user_id_aliases(platform, user_id):
            key = f"{platform}:{alias}"
            limits[key] = now
        self._save_json(self._rate_limit_path(), limits)
```

> **DoS 面**:`MAX_PENDING_PER_PLATFORM = 3` 是**平台级全局**。三个陌生人各要一次码,
> 第四个(哪怕是正当用户)在 1 小时内拿不到码——`generate_code` 返回 None,
> `run.py:14501-14508` 给他回"Too many pairing requests right now~"。
> 缓解:运营者可 `hermes pairing clear-pending`。这是**刻意的小上限换爆破面小**。

### 2.5 批准流程:两条入口,都在"已认证"侧

**CLI 侧**:`hermes pairing approve <platform> <request-id|code>`

parser:`hermes_cli/subcommands/pairing.py:23-33 @ 863e313`
```python
    pairing_approve_parser = pairing_sub.add_parser(
        "approve", help="Approve a pairing request"
    )
    pairing_approve_parser.add_argument(
        "platform", help="Platform name (telegram, discord, slack, whatsapp)"
    )
    pairing_approve_parser.add_argument(
        "code",
        metavar="request-id|code",
        help="Request ID from 'pairing list', or the code the bot DM'd the user",
    )
```
挂载:`hermes_cli/main.py:11599-11601`(`build_pairing_parser(subparsers, cmd_pairing=cmd_pairing)`);
handler:`hermes_cli/main.py:11159-11162` → `hermes_cli/pairing.py:11-28`。

分派逻辑(形状判定,不是猜):

`hermes_cli/pairing.py:66-80 @ 863e313`
```python
def _cmd_approve(store, platform: str, code: str):
    """Approve a pairing request id (from ``pairing list``) or a DM'd code."""
    platform = platform.lower().strip()
    code = code.strip()

    if store.looks_like_request_id(code):
        result = store.approve_request(platform, code)
    else:
        result = store.approve_code(platform, code.upper())
```

形状不可能撞车,因为 request id 是 16 位小写 hex,码是 8 位大写不含 hex 歧义字母:

`gateway/pairing.py:723-733 @ 863e313`
```python
    @staticmethod
    def looks_like_request_id(value: str) -> bool:
        """True when ``value`` has the shape of a ``list_pending`` request id.

        Request ids are ``secrets.token_hex(8)`` (16 lowercase hex chars);
        pairing codes are 8 chars from an unambiguous uppercase alphabet that
        excludes every hex letter's ambiguity partner. The two shapes cannot
        collide, so callers accepting either can dispatch on this.
        """
        value = str(value or "").strip()
        return len(value) == 16 and all(c in "0123456789abcdefABCDEF" for c in value)
```

**Dashboard 侧**:`POST /api/pairing/approve`(`hermes_cli/web_server.py:12321-12352`),
同样两路分派;它**不在 auth 白名单里**(`hermes_cli/dashboard_auth/public_paths.py:33-64`
的 `PUBLIC_API_PATHS` 只有 `/api/health`、`/api/status`、config defaults/schema、model info、
themes/plugins、`/api/cron/fire`),所以走 dashboard 认证网关。

**request-id 路径存在的理由**:管理界面要列出待批请求,但**不能显示码**(码是 DM 给用户的一次性
凭据)。所以 `list_pending` 返回一个服务端 id:

`gateway/pairing.py:735-751 @ 863e313`
```python
    def approve_request(self, platform: str, request_id: str) -> Optional[dict]:
        """
        Approve a pending pairing request by its server-side request id.

        This is the grant path for authenticated admin surfaces (``hermes
        pairing list``, the dashboard/desktop approve buttons), which show
        pending requests but must never reveal the one-time code DM'd to the
        user. Returns ``{user_id, user_name}`` on success, ``None`` for an
        unknown/expired request id.

        Unlike :meth:`approve_code` this does NOT count a miss toward the
        brute-force lockout, and is not itself gated by one. The lockout
        protects the 8-char code space against guessing over a messaging
        channel; a request id is only ever obtained by an admin already
        authenticated to this store, so a stale id means "the row you clicked
        expired", not an attack. Counting it here let a few GUI clicks on a
        stale list lock the operator out of the CLI's code path too.
        """
```

`list_pending` 的字段是**白名单式**的,不含任何码派生物:

`gateway/pairing.py:794-800 @ 863e313`
```python
                    results.append({
                        "platform": p,
                        "request_id": str(entry_id) if is_modern else "",
                        "user_id": info.get("user_id", ""),
                        "user_name": info.get("user_name", ""),
                        "age_minutes": age_min,
                    })
```

**批准后写到哪:**

1. `{platform}-approved.json`(`_approve_user`,以规范化 user_id 为键,记 `user_name` +
   `approved_at`),并且**先删掉所有别名重复项**:

`gateway/pairing.py:534-555 @ 863e313`
```python
    def _approve_user(self, platform: str, user_id: str, user_name: str = "") -> None:
        """Add a user to the approved list. Must be called under self._lock."""
        approved = self._load_json(self._approved_path(platform))
        normalized_user_id = self._normalize_user_id(platform, user_id)
        duplicate_ids = [
            approved_user_id
            for approved_user_id in approved
            if self._user_ids_match(platform, approved_user_id, normalized_user_id)
        ]
        for approved_user_id in duplicate_ids:
            del approved[approved_user_id]

        approved[normalized_user_id] = {
            "user_name": user_name,
            "approved_at": time.time(),
        }
        self._save_json(self._approved_path(platform), approved)

        # Mirror the grant into the operator's allowlist when one is configured
        # (option i), so the pairing store and the allowlist stay a single
        # visible source of truth. No-op on open gateways.
        _sync_allowlist_add(platform, normalized_user_id)
```

2. **条件性地**镜像进 `.env` 的平台名单(#23778 "option i"):**只在运营者已有名单时才写**,
   否则会把开放网关静默变成封闭网关:

`gateway/pairing.py:175-201 @ 863e313`
```python
def _sync_allowlist_add(platform: str, user_id: str) -> None:
    """Add ``user_id`` to the platform allowlist env var IF one is configured.

    Option (i): only materialize the grant into the allowlist when the operator
    already runs an allowlist for this platform. On an open gateway (no
    allowlist) we do nothing — the pairing store remains the grant record and
    the authz union honors it, so we never silently convert an open gateway into
    a locked one on first pairing.
    """
    env_var = _allowlist_env_for_platform(platform)
    if not env_var:
        return
    current = _read_allowlist_env(env_var)
    if not current:
        return  # No allowlist configured — leave the gateway open (option i).
```

**revoke 的对称性问题**——批准时写的是规范化手机号,撤销时运营者常传 JID/带设备后缀的形态,
精确串匹配会删不掉:

`gateway/pairing.py:292-303 @ 863e313`
```python
def _sync_allowlist_remove(platform: str, user_id: str) -> None:
    """Remove ``user_id`` (and WhatsApp alias equivalents) from the allowlist.

    Matching must mirror PairingStore / authz WhatsApp alias rules: approve
    mirrors a normalized phone into ``WHATSAPP_ALLOWED_USERS``, while revoke
    is often invoked with a JID or device-suffix form. Exact-string delete
    would leave the allowlist entry and keep the sender authorized.

    Also clears matching entries from any in-process platform adapter
    ``_allow_from`` snapshot so sole-entry revocation is effective without a
    gateway restart.
    """
```
还要清活体适配器的构造期快照(否则"删了唯一一条名单项"要等重启才生效):

`gateway/pairing.py:261-268 @ 863e313`
```python
def _sync_live_adapter_allowlist_remove(platform: str, user_id: str) -> None:
    """Clear revoked principals from in-process adapter allowlist snapshots.

    ``WhatsAppAdapter`` (and Cloud) snapshot ``_allow_from`` at construction.
    Pairing revoke updates ``WHATSAPP_ALLOWED_USERS`` / cloud env, but when the
    revoked principal was the sole entry the env key is removed entirely.
    Intake must not keep authorizing from the stale snapshot until restart.
    """
```
`*` 通配在增删两侧都被保护(`pairing.py:191, 311-315, 240-257`)。

### 2.6 并发安全:进程内有锁,跨进程无锁

**进程内**:`threading.RLock` 保护所有 read-modify-write:

`gateway/pairing.py:448-451 @ 863e313`
```python
        # Protects all read-modify-write cycles. The gateway runs multiple
        # platform adapters concurrently in threads sharing one PairingStore.
        self._lock = threading.RLock()
        self._profile = profile  # for diagnostics / log lines
```
网关只建**一个**全局 store(`gateway/run.py:6221`)+ 每 profile 一个(`gateway/run.py:13255-13261`),
同一 profile 的所有平台线程共享同一把锁 ⇒ **两个陌生人同时请求配对是安全的**:
两次 `generate_code` 串行化,各拿一个 `secrets.token_hex(8)` 键,不会互相覆盖;
`MAX_PENDING_PER_PLATFORM` 的检查与写入也在同一临界区内,不会超发。

**落盘是原子的**(临时文件 + fsync + rename + chmod 0600):

`gateway/pairing.py:379-402 @ 863e313`
```python
def _secure_write(path: Path, data: str) -> None:
    """Write data to file with restrictive permissions (owner read/write only).

    Uses a temp-file + atomic rename so readers always see either the old
    complete file or the new one — never a partial write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        atomic_replace(tmp_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # Windows doesn't support chmod the same way
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

**跨进程无锁——这是真实的窗口。** 全文件 grep 无 `fcntl` / `flock` / `FileLock`。
CLI(`hermes pairing approve`)与 dashboard 各自 `PairingStore()` 新实例、新 RLock,
与网关进程完全独立。场景:网关正为陌生人 B 跑 `generate_code`(读 pending → 改 → 写),
同一瞬间运营者 CLI 批准 A(读 pending → 删 A → 写)。两侧各自的 `os.replace` 都是原子的,
**但整个 read-modify-write 不是**——后写的那一方会用自己读到的旧快照覆盖对方的改动。
后果是丢一条 pending(B 的码作废,或 A 的删除被回滚导致码可复用一次)。

> 影响面小(需要秒级重合 + 人工操作),但**重实现时应该上文件锁**。
> 另外 `atomic_replace` 会先解引用 symlink(`utils.py:111-115`),这是 #16743 的修复
> (托管部署把 `~/.hermes/*.json` symlink 到 git 仓库,朴素 `os.replace` 会把软链换成实体文件)。

### 2.7 存储位置与两次目录迁移事故

`PAIRING_DIR` 是**模块级常量**,在 import 时求值一次:

`gateway/pairing.py:59 @ 863e313`
```python
PAIRING_DIR = get_hermes_dir("platforms/pairing", "pairing")
```

`get_hermes_dir` 的语义是"旧目录**有内容**就用旧的,否则用新的":

`hermes_constants.py:278-282 @ 863e313`
```python
    home = home or get_hermes_home()
    old_path = home / old_name
    if _legacy_path_has_content(old_path):
        return old_path
    return home / new_subpath
```

**事故 A(#27602)**:早期版本只判"旧目录存在",安装脚手架 / 手动 `mkdir` 留下的**空** `pairing/`
会遮蔽真正装着数据的 `platforms/pairing/`,已配对用户全部失效:

`hermes_constants.py:259-265 @ 863e313`
```python
    A bare empty ``<old_name>/`` directory does **not** count as "the
    legacy install is in use" — install scaffolds, manual ``mkdir`` work,
    and cleared-then-abandoned locations all create empty stubs that
    would otherwise silently shadow real data populated at
    ``<new_subpath>/``. See #27602 for the pairing-store regression where
    a dormant empty ``pairing/`` orphaned approved-user data in
    ``platforms/pairing/``.
```

**事故 B(数据被切成两半)**:两个目录**都有内容**时,旧目录赢,新目录的批准记录被忽略,
已配对的 Feishu 用户被重新要码。修法是构造时合并:

`gateway/pairing.py:340-347 @ 863e313`
```python
def _merge_pairing_dir(active_dir: Path, alternate_dir: Path) -> None:
    """Merge split legacy/new pairing data into the active PairingStore dir.

    Older installs use ``{HERMES_HOME}/pairing`` while newer code/docs may
    write ``{HERMES_HOME}/platforms/pairing``. If both directories exist, the
    gateway must not silently ignore approved users sitting in the inactive
    location; otherwise already-paired Feishu users get asked for a fresh code.
    """
```
合并规则是"活动侧优先、非活动侧补齐"(`gateway/pairing.py:360-363`:`merged.update(current)`)。
每次 `PairingStore.__init__` 都会跑一遍(`pairing.py:439-447`)。

**事故 C(#10270,Docker 权限)**:`docker exec` 默认 root,写出的 0600 root:root 文件,
gateway(gosu 降权为 `hermes`)读不到。原来的 `except OSError` 会静默吞掉,用户始终"未授权":

`gateway/pairing.py:467-497 @ 863e313`
```python
    def _load_json(self, path: Path) -> dict:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except PermissionError as e:
                # Surface this loudly: a 0600 file owned by a different user
                # (classic Docker symptom: `docker exec` runs as root and writes
                # the file, then the gateway process — running as `hermes` after
                # gosu drop — can't read it) would otherwise be swallowed by
                # the generic OSError branch below, silently leaving the user
                # marked unauthorized. See issue #10270.
                try:
                    st = path.stat()
                    owner_info = f"owner_uid={st.st_uid} mode={oct(st.st_mode)[-4:]}"
                except OSError:
                    owner_info = "<stat failed>"
                # os.geteuid doesn't exist on Windows; the Docker scenario is
                # POSIX-only, but the gateway (and this fallback) runs anywhere.
                euid = os.geteuid() if hasattr(os, "geteuid") else "n/a"
                logger.warning(
                    "Pairing file %s exists but is not readable as uid=%s (%s; %s). "
                    "If you ran `docker exec <container> hermes pairing approve ...` as root, "
                    "re-run with `docker exec -u hermes <container> ...` and "
                    "chown the existing file to the hermes user, or restart the "
                    "container so the entrypoint can fix ownership.",
                    path, euid, owner_info, e,
                )
                return {}
```
**注意 fail-closed**:读不到就当空 dict,即"没人被批准",而不是"放行"。

### 2.8 legacy pending 条目的容错

升级时旧的明文 pending.json 里没有 `salt`/`hash`,三个入口一律跳过而不是崩:

`gateway/pairing.py:694-706 @ 863e313`
```python
            # Find the entry whose hash matches the provided code.
            # Tolerate legacy plaintext-key entries (no salt/hash) and
            # malformed entries — skip them rather than KeyError, so an
            # in-place upgrade across an existing pending.json doesn't
            # crash on the first approve call. Legacy entries get pruned
            # at their TTL by _cleanup_expired.
            matched_key = None
            matched_entry = None
            for entry_id, entry in pending.items():
                if not isinstance(entry, dict):
                    continue
                if "salt" not in entry or "hash" not in entry:
                    continue
```
`_cleanup_expired` 把"没有数值 `created_at`"的条目一律当过期删掉(`gateway/pairing.py:882-889`)。

### 2.9 profile 作用域

`gateway/pairing.py:421-447 @ 863e313`
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
CLI 侧不传 profile(`hermes_cli/pairing.py:15` `store = PairingStore()`),
**靠 `-p` 在 import 之前改 `HERMES_HOME`** 达成同样效果:

`hermes_cli/main.py:517-518, 684 @ 863e313`
```python
def _apply_profile_override() -> None:
    """Pre-parse --profile/-p and set HERMES_HOME before imports."""
...
        os.environ["HERMES_HOME"] = hermes_home
```
(`_apply_profile_override()` 在 `hermes_cli/main.py:690` 模块级直接调用。)
所以 `gateway/run.py:14486-14492` 给用户看的 `hermes -p <profile> pairing approve ...` 是**能工作的**。

---

## 3. R7 移交项 A4 落地:pairing 本体证据链

R7 已定案"开发者文档把 DM 配对方向写反"。本轮补上决定性证据:

### 3.1 文档侧(自绘地图)

`website/docs/developer-guide/gateway-internals.md:102-111 @ 863e313`
```text
### DM Pairing Flow

```text
Admin: /pair
Gateway: "Pairing code: ABC123. Share with the user."
New user: ABC123
Gateway: "Paired! You're now authorized."
```

Pairing state is persisted in `gateway/pairing.py` and survives restarts.
```

这段描述了三件代码里都不存在的事:(a) 管理员用 `/pair` 命令要码;(b) 网关把码显示给管理员;
(c) **新用户在聊天里回码即完成配对**。

### 3.2 代码侧:决定性反证

**反证 1 —— 全仓只有两个 `approve_code` / `approve_request` 调用点,都在已认证侧。**
`grep -rn "approve_code\|approve_request" --include=*.py`(排除 tests/ 与 pairing.py 自身)
只得到:`hermes_cli/pairing.py:72,74`(CLI)与 `hermes_cli/web_server.py:12337,12339`(dashboard)。
**没有任何入站消息处理路径调用它们**。代码自己也这么断言:

`gateway/authz_mixin.py:584-585 @ 863e313`
```python
        # inbound sender can never reach approve_code, so this is not an
        # attacker-controlled path. Honored as a UNION with the allowlist: a
```

**反证 2 —— 全仓无 `/pair` 命令。** `grep -rn "add_parser(\"pairing\"" ` 只命中
`hermes_cli/subcommands/pairing.py:16`(顶层 `hermes pairing`,不是网关斜杠命令)。

**反证 3 —— 真实方向:陌生人自动收码,并被告知让 owner 去 CLI 批。**

`gateway/run.py:14455-14500 @ 863e313`
```python
        elif not self._is_user_authorized(source):
            logger.warning("Unauthorized user: %s (%s) on %s", source.user_id, source.user_name, source.platform.value)
            # In DMs: offer pairing code. In groups: silently ignore.
            if (
                source.chat_type == "dm"
                and self._get_unauthorized_dm_behavior(
                    source.platform,
                    profile=source.profile,
                )
                == "pair"
            ):
                platform_name = source.platform.value if source.platform else "unknown"
                pairing_store = self._pairing_store_for(source)
                if pairing_store is None:
                    logger.error(
                        "Cannot offer pairing code on %s: no pairing store",
                        platform_name,
                    )
                    return None
                # Rate-limit ALL pairing responses (code or rejection) to
                # prevent spamming the user with repeated messages when
                # multiple DMs arrive in quick succession.
                if pairing_store._is_rate_limited(platform_name, source.user_id):
                    return None
                code = pairing_store.generate_code(
                    platform_name, source.user_id, source.user_name or ""
                )
                if code:
                    adapter = self._adapter_for_source(source)
                    if adapter:
                        store_profile = getattr(pairing_store, "profile", None)
                        profile_arg = (
                            f"-p {store_profile} "
                            if isinstance(store_profile, str)
                            and store_profile
                            and store_profile != "default"
                            else ""
                        )
                        await adapter.send(
                            source.chat_id,
                            f"Hi~ I don't recognize you yet!\n\n"
                            f"Here's your pairing code: `{code}`\n\n"
                            f"Ask the bot owner to run:\n"
                            f"`hermes {profile_arg}pairing approve "
                            f"{platform_name} {code}`"
                        )
```

**反证 4 —— 用户文档方向正确**(与代码一致,R1 已核):

`website/docs/user-guide/security.md:369-374 @ 863e313`
```text
**How it works:**

1. An unknown user sends a DM to the bot
2. The bot replies with an 8-character pairing code
3. The bot owner runs `hermes pairing approve <platform> <code>` on the CLI
4. The user is permanently approved for that platform
```

### 3.3 为什么这个方向更安全(设计意图复原)

反过来的流程("管理员要码、用户回码")意味着**入站消息通道上存在一个可提交凭据的接口**——
攻击者可以对着 bot 猛刷 8 字符码。真实方向把**校验点搬到 shell / 已认证 dashboard**,
于是:

- 入站通道**只能领码,不能兑码**;
- `MAX_FAILED_ATTEMPTS` 锁定保护的是**运营者手抄码时的手误**与"用户转述码"这条社工路径,
  不是网络爆破面;
- 码泄露的唯一后果是**别人拿着码去求运营者批**——运营者会在 `hermes pairing list` 里
  看到 `user_id`,能自己判断。

代价:**必须有 shell 或 dashboard 访问**才能加人,纯手机运营不了(dashboard 就是为此补的)。

---

## 4. `whatsapp_identity.py`:为什么 WhatsApp 需要专门的身份规范化

### 4.1 真实故障:同一个人在同一段对话里有两个身份

`gateway/whatsapp_identity.py:1-13 @ 863e313`
```python
"""Shared helpers for canonicalising WhatsApp sender identity.

WhatsApp's bridge can surface the same human under two different JID shapes
within a single conversation:

- LID form: ``999999999999999@lid``
- Phone form: ``15551234567@s.whatsapp.net``

Both the authorisation path (:mod:`gateway.run`) and the session-key path
(:mod:`gateway.session`) need to collapse these aliases to a single stable
identity. This module is the single source of truth for that resolution so
the two paths can never drift apart.
...
```

**术语**:JID = Jabber ID,WhatsApp 沿用 XMPP 的地址格式 `<本地部分>@<域>`;
`@s.whatsapp.net` 是手机号形态,`@g.us` 是群,`@lid` 是 **LID(Linked ID)**——
Meta 为隐私引入的、与手机号解耦的稳定标识。桥接层(Baileys)会在两者间**来回切换**。

**两个具体故障:**
1. **授权失效**:运营者在 `WHATSAPP_ALLOWED_USERS` 里填了手机号,某天桥接层开始以 LID 投递,
   同一个人变成陌生人 —— 被要求重新配对。
2. **会话分裂**:同一个人的消息一半落到手机号 session、一半落到 LID session,
   上下文断成两截。

所以规范化不是"美观",是**把两条独立代码路径(authz 与 session-key)锁在同一份真值上**——
docstring 明说 "so the two paths can never drift apart"。

### 4.2 四个函数与各自的职责

**`normalize_whatsapp_identifier`** —— 纯字符串剥皮,不读文件:

`gateway/whatsapp_identity.py:61-67 @ 863e313`
```python
    return (
        str(value or "")
        .strip()
        .replace("+", "", 1)
        .split(":", 1)[0]
        .split("@", 1)[0]
    )
```
`60123456789:47@s.whatsapp.net` → `60123456789`;`999999999999999@lid` → `999999999999999`。
注意它**不能**把 LID 变成手机号——那需要映射表。

**`expand_whatsapp_aliases`** —— 读桥接层的映射文件做 BFS 传递闭包:

`gateway/whatsapp_identity.py:132-170 @ 863e313`
```python
    normalized = normalize_whatsapp_identifier(identifier)
    if not normalized:
        return set()

    session_dir = get_hermes_dir("platforms/whatsapp/session", "whatsapp/session")
    resolved: Set[str] = set()
    queue = [normalized]

    while queue:
        current = queue.pop(0)
        if not current or current in resolved:
            continue
        # Defense-in-depth: reject identifiers that could sneak path
        # separators / traversal segments into the ``lid-mapping-{current}``
        # filename below. The hardcoded ``lid-mapping-`` prefix already
        # prevents escape via pathlib's component split (an attacker can't
        # create ``lid-mapping-..`` as a real directory in session_dir), but
        # this keeps the identifier space to the characters WhatsApp JIDs
        # actually use and avoids depending on that filesystem-layout
        # invariant.
        if not _SAFE_IDENTIFIER_RE.match(current):
            continue

        resolved.add(current)
        for suffix in ("", "_reverse"):
            mapping_path = session_dir / f"lid-mapping-{current}{suffix}.json"
            if not mapping_path.exists():
                continue
```
**安全点**:标识符会被拼进文件名,所以有白名单正则挡路径穿越:

`gateway/whatsapp_identity.py:40-43 @ 863e313`
```python
# WhatsApp JIDs are numeric (or plus-prefixed numeric) with optional
# ``@``, ``.`` and ``:`` separators. ``\w`` is pinned to ASCII so
# full-width digits / Unicode word chars can't sneak through.
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9@.+\-]+$")
```
**返回集合永远含输入本身**(155 行 `resolved.add(current)`),这让调用方可以无脑
`in` 判断而不写兜底分支——docstring 在 127-130 行明确承诺了这个契约。

**`canonical_whatsapp_identifier`** —— 从别名集里挑"最短、同长取字典序小"的作为规范身份:

`gateway/whatsapp_identity.py:202-206 @ 863e313`
```python
    # expand_whatsapp_aliases always includes `normalized` itself in the
    # returned set, so the min() below degrades gracefully to `normalized`
    # when no lid-mapping files are present.
    aliases = expand_whatsapp_aliases(normalized)
    return min(aliases, key=lambda candidate: (len(candidate), candidate))
```
"最短优先"是启发式:手机号(11-13 位)通常短于 LID(15 位),所以偏向手机号——运营者
在配置里写的就是手机号。**取舍**:这不是保证,只是启发;若某天 LID 变短就会翻转。
但由于**两条路径共用这一个函数**,翻转也是同步的,不会造成 authz/session 分裂。

**`to_whatsapp_jid`** —— 反方向,给**出站**用:

`gateway/whatsapp_identity.py:77-96 @ 863e313`
```python
def to_whatsapp_jid(value: str) -> str:
    """Normalize an *outbound* WhatsApp target to a bridge-safe JID.

    Baileys' ``jidDecode`` crashes on a bare phone number — it expects a
    fully-qualified JID such as ``50766715226@s.whatsapp.net``. This helper
    is the inverse of :func:`normalize_whatsapp_identifier`: instead of
    stripping a JID down to its numeric core for comparison, it *builds* the
    JID a send must use.
```
故障很具体:**Baileys 的 `jidDecode` 遇到裸手机号会崩**。修法是发送前统一补域。
无法识别的输入**原样返回**(118 行),让桥接层报有意义的错,而不是被这里改坏。

### 4.3 消费者(已接线,无死代码)

| 函数 | 生产调用点 |
|------|-----------|
| `normalize_whatsapp_identifier` | `gateway/authz_mixin.py:27,764`、`gateway/pairing.py:34,125`、`gateway/run.py:2412`、`gateway/platforms/whatsapp_common.py:237,246`、`gateway/session.py:95`(再导出) |
| `expand_whatsapp_aliases` | `gateway/authz_mixin.py:26,759,763`、`gateway/pairing.py:33,137`、`gateway/run.py:2411`、`gateway/platforms/whatsapp_common.py:236,240,250` |
| `canonical_whatsapp_identifier` | `gateway/session.py:94,1106,1125,1142`、`gateway/run.py:2410`(`# noqa: F401` 再导出) |
| `to_whatsapp_jid` | `plugins/platforms/whatsapp/adapter.py:288,937,1004,1039,1090,1174,1283,1301,1713` |

authz 侧的用法:**名单项和用户 id 双向都展开**,再求交:

`gateway/authz_mixin.py:754-766 @ 863e313`
```python
        # WhatsApp (Baileys + Cloud): resolve phone↔LID / JID aliases so
        # device-suffix and bare-phone allowlist entries match the same principal.
        if source.platform in {Platform.WHATSAPP, Platform.WHATSAPP_CLOUD}:
            normalized_allowed_ids = set()
            for allowed_id in allowed_ids:
                normalized_allowed_ids.update(_expand_whatsapp_auth_aliases(allowed_id))
            if normalized_allowed_ids:
                allowed_ids = normalized_allowed_ids

            check_ids.update(_expand_whatsapp_auth_aliases(user_id))
            normalized_user_id = _normalize_whatsapp_identifier(user_id)
            if normalized_user_id:
                check_ids.add(normalized_user_id)
```

---

## 5. `channel_directory.py`:频道目录

### 5.1 存什么、解决什么问题

`gateway/channel_directory.py:1-7 @ 863e313`
```python
"""
Channel directory -- cached map of reachable channels/contacts per platform.

Built on gateway startup, refreshed periodically (every 5 min), and saved to
~/.hermes/channel_directory.json.  The send_message tool reads this file for
action="list" and for resolving human-friendly channel names to numeric IDs.
"""
```

**它解决的是"出站寻址"问题,不是授权。** 模型/cron 想主动发消息时,只会说
`slack:#engineering` 或 `discord:bot-home` 这种人话;平台 API 要的是 `C0B0QV5434G` /
`1234567890123456789`。目录就是这张翻译表,外加一份"我现在能发到哪些地方"的清单。

数据形状:`{"updated_at": ISO8601, "platforms": {"<platform>": [ {id, name, type, guild?, thread_id?} ]}}`
(`gateway/channel_directory.py:203-206`;条目字段见 `_normalize_adapter_channels:282-291`)。

### 5.2 何时写入(三个触发点)

| 触发 | 位置 |
|------|------|
| 网关启动完成后一次 | `gateway/run.py:11386-11392` |
| 某平台重连成功后 | `gateway/run.py:12499-12503` |
| 后台 housekeeping 每 5 分钟 | `gateway/run.py:26176-26191` |

`gateway/run.py:26155 @ 863e313`
```python
    CHANNEL_DIR_EVERY = 5    # ticks — every 5 minutes
```
housekeeping 跑在**后台线程**,而 `build_channel_directory` 是 async(要发 Slack Web 请求),
所以要跨线程调度回事件循环并等结果:

`gateway/run.py:26179-26190 @ 863e313`
```python
                if loop is not None:
                    # build_channel_directory is async (Slack web calls), and
                    # this runs in a background thread. Schedule onto the
                    # gateway event loop and wait briefly for completion so
                    # refresh failures are still logged via the except.
                    fut = safe_schedule_threadsafe(
                        build_channel_directory(adapters), loop,
                        logger=logger,
                        log_message="Channel directory refresh scheduling error",
                    )
                    if fut is not None:
                        fut.result(timeout=30)
```

### 5.3 何时失效:**全量重建,没有增量失效**

`build_channel_directory` 每次从零构造 `platforms` dict 再整体覆盖写
(`gateway/channel_directory.py:150, 203-209`)。**没有 TTL、没有单条 invalidate**——
"失效"就等于"下一次 5 分钟重建"。持久化在:

`gateway/channel_directory.py:21 @ 863e313`
```python
DIRECTORY_PATH = get_hermes_home() / "channel_directory.json"
```
用 `atomic_json_write`(`gateway/channel_directory.py:209`),写失败只 warn、**保留上一版缓存**
(测试 `test_failed_write_preserves_previous_cache` 钉住)。

**注意 `DIRECTORY_PATH` 是模块级常量**,import 时求值 ⇒ 目录**没有任何 profile 隔离**:
多 profile 网关共用同一个 `channel_directory.json`(见 §6 ◇3)。

### 5.4 三层发现来源 + 一层人工覆盖

```
1. adapter.list_channels()  ── 插件平台的通用钩子(如 SimpleX)
2. 平台特化:_build_discord(guild 枚举) / _build_slack(users.conversations 分页)
3. 会话历史回填:_build_from_sessions → state.db 优先,sessions.json 兜底
4. 人工别名覆盖:channel_aliases.json(每次 build 与每次 load 都重放)
```

**第 3 层有一条重要的安全/正确性约束**——只回填**本进程已连接**的平台:

`gateway/channel_directory.py:167-181 @ 863e313`
```python
    # Platforms that don't support direct channel enumeration get session-based
    # discovery automatically, but only for platforms connected in THIS gateway
    # process. Historical session origins for disabled/decommissioned platforms
    # must not be resurrected into the active send-target directory (stale
    # targets make send_message route to platforms that can no longer deliver).
    _SKIP_SESSION_DISCOVERY = frozenset({"local", "api_server", "webhook"})
    adapter_platform_names = {getattr(p, "value", str(p)) for p in adapters}
    for plat in Platform:
        plat_name = plat.value
        if (
            plat_name in _SKIP_SESSION_DISCOVERY
            or plat_name in platforms
            or plat_name not in adapter_platform_names
        ):
            continue
        platforms[plat_name] = await asyncio.to_thread(_build_from_sessions, plat_name)
```
测试 `test_channel_directory_connected_only.py::test_does_not_resurrect_disconnected_platforms_from_session_history` 钉住。

**第 3 层的数据源迁移(#9006)**:

`gateway/channel_directory.py:405-414 @ 863e313`
```python
def _build_from_sessions(platform_name: str) -> List[Dict[str, str]]:
    """Pull known channels/contacts from gateway session origin data.

    state.db is the primary source (#9006): gateway session rows persist
    origin_json.  Falls back to sessions.json for pre-migration databases.
    """
    entries = _build_from_sessions_db(platform_name)
    if entries:
        return entries
    return _build_from_sessions_json(platform_name)
```

**第 4 层是唯一"人写"的输入**,存在的理由写在常量旁边:

`gateway/channel_directory.py:30-34 @ 863e313`
```python
# User-maintained friendly-name overlay. The directory is fully regenerated
# from live adapters + session data on a timer, so hand-edits to
# channel_directory.json don't survive. Aliases declared here are re-applied
# on every build AND every load, giving durable human-friendly names (and
# letting you pre-name a chat before it has produced any traffic).
# Format: {"<platform>": {"<chat_id>": "<friendly name>", ...}, ...}
CHANNEL_ALIASES_PATH = get_hermes_home() / "channel_aliases.json"
```
它还能**为尚未被发现的 chat 注入占位条目**(所以刚建的群不用等第一条消息就能按名字发):

`gateway/channel_directory.py:74-81 @ 863e313`
```python
            if not matched:
                entries.append({
                    "id": chat_id,
                    "name": friendly,
                    "type": "group" if str(chat_id).endswith("@g.us") else "dm",
                    "thread_id": None,
                })
```
`load_directory` 里也重放一次(`gateway/channel_directory.py:514-516`),这样**新加别名立刻生效**、
不必等下一次 5 分钟重建。

### 5.5 名字解析的四级降级

`gateway/channel_directory.py:547-578 @ 863e313`
```python
    # 0. Exact ID match — case-sensitive, no normalization. Lets callers pass
    # raw platform IDs (e.g. Slack "C0B0QV5434G") even when the format guard
    # in _parse_target_ref hasn't recognized them as explicit.
    raw = name.strip()
    for ch in channels:
        if ch.get("id") == raw:
            return ch["id"]

    query = _normalize_channel_query(name)

    # 1. Exact name match, including the display labels shown by send_message(action="list")
    for ch in channels:
        if _normalize_channel_query(ch["name"]) == query:
            return ch["id"]
        if _normalize_channel_query(_channel_target_name(platform_name, ch)) == query:
            return ch["id"]

    # 2. Guild-qualified match for Discord ("GuildName/channel")
    if "/" in query:
        guild_part, ch_part = query.rsplit("/", 1)
        for ch in channels:
            guild = ch.get("guild", "").strip().lower()
            if guild == guild_part and _normalize_channel_query(ch["name"]) == ch_part:
                return ch["id"]

    # 3. Partial prefix match (only if unambiguous)
    matches = [ch for ch in channels if _normalize_channel_query(ch["name"]).startswith(query)]
    if len(matches) == 1:
        return matches[0]["id"]

    return None
```
**取舍**:第 3 级前缀匹配**只在唯一命中时生效**——歧义时宁可返回 None 让上层报错,
也不猜。这是"发错群"这类不可撤销后果的正确防线。

### 5.6 Slack 分支的两个工程细节

**告警节流**(目录 5 分钟重建一次,持久错误会刷屏):

`gateway/channel_directory.py:22-28 @ 863e313`
```python
# Throttle window for repeated Slack channel-directory refresh failures.
# The directory rebuilds on a timer, so a persistent workspace error (e.g.
# missing scope, revoked token) would otherwise re-log the same warning on
# every refresh. Warn once per (team, error detail) per interval; repeats
# drop to DEBUG.
_SLACK_DIRECTORY_WARNING_INTERVAL_SECONDS = 3600
_slack_directory_warning_last: Dict[tuple[str, str], float] = {}
```
`missing_scope` 更进一步——**直接降到 DEBUG**,因为那是配置选择而非故障
(`gateway/channel_directory.py:324-329, 347-352`)。

**分页安全帽**:`for _page in range(20)`(`gateway/channel_directory.py:315`),
20×200 = 4000 频道封顶,防止恶意/异常游标把刷新卡死。

### 5.7 消费者(已接线)

| 函数 | 生产调用点 |
|------|-----------|
| `build_channel_directory` | `gateway/run.py:11388, 12501, 26185` |
| `resolve_channel_name` | `cron/scheduler.py:1187`、`tools/send_message_tool.py:294,379`、`hermes_cli/send_cmd.py:151` |
| `format_directory_for_display` | `tools/send_message_tool.py:260`、`hermes_cli/send_cmd.py:151`(同 import) |
| `lookup_channel_type` | `plugins/platforms/discord/adapter.py:9596` |
| `load_directory` | 模块内 524/533/580;外部经上述三函数间接使用 |
| 裸读 JSON 文件 | `mcp_serve.py:195-211, 919`(不 import 本模块,自己读文件) |
| 备份清单 | `hermes_cli/backup.py:1098-1099`(两个 json 都在快照列表里) |
| 插件实现 `list_channels` | `plugins/platforms/simplex/adapter.py:863`(注释点名被本模块调用) |

**无死代码。**

---

## 6. ▲/◇ 候选

> ▲ = 文档与代码矛盾;◇ = 代码有而文档无。双侧证据齐备。

### ▲1(已定案,R7 A4)DM 配对方向写反 —— 证据链见 §3

- **文档**:`website/docs/developer-guide/gateway-internals.md:102-111`(`/pair` + 用户回码)
- **代码**:全仓无 `/pair`;`approve_code`/`approve_request` 只有 CLI
  (`hermes_cli/pairing.py:72,74`)与 dashboard(`hermes_cli/web_server.py:12337,12339`)两个调用点;
  入站方向见 `gateway/run.py:14455-14500`
- **裁决**:▲ 证实。**本轮新增决定性证据**:调用点全仓穷举 + `gateway/authz_mixin.py:584-585` 的自陈。

### ▲2 授权检查顺序两处文档各错一处

- **文档 A**:`website/docs/developer-guide/gateway-internals.md:96-100`(原文,未省略;
  其上 `:94` 的引子句为 "The gateway uses a multi-layer authorization check, evaluated in order:")
  ```text
1. **Per-platform allow-all flag** (e.g., `TELEGRAM_ALLOW_ALL_USERS`) — if set, all users on that platform are authorized
2. **Platform allowlist** (e.g., `TELEGRAM_ALLOWED_USERS`) — comma-separated user IDs
3. **DM pairing** — authenticated users can pair new users via a pairing code
4. **Global allow-all** (`GATEWAY_ALLOW_ALL_USERS`) — if set, all users across all platforms are authorized
5. **Default: deny** — unauthorized users are rejected
  ```
  代码里配对表(`gateway/authz_mixin.py:597`)在平台名单(`601`)**之前**,顺序反了;而且漏掉了
  HA/Webhook 豁免、relay 上游、群 chat 名单、ALLOW_BOTS、role_authorized、适配器自有策略
  六层(见 §1.3 表)。
- **文档 B**:`website/docs/user-guide/security.md:325-332` 顺序对(pairing 在名单前),
  但同样只列 6 层,漏掉上述 5 层。
- **代码内 docstring 也漏**:`gateway/authz_mixin.py:387-396` 自称五步,实际十四层。
- **裁决**:▲ 证实(顺序错在开发者文档;覆盖不全在三处)。影响:因为是纯并集,
  顺序错**不改变结果**,只误导读者;覆盖不全会让人误以为 relay/HA 也走名单。

### ▲3 配对数据存储路径过时

- **文档**:`website/docs/user-guide/security.md:437`
  ```text
  **Storage:** Pairing data is stored in `~/.hermes/pairing/` with per-platform JSON files:
  ```
  以及模块头 `gateway/pairing.py:18` `Storage: ~/.hermes/pairing/`
- **代码**:`gateway/pairing.py:59` `PAIRING_DIR = get_hermes_dir("platforms/pairing", "pairing")`
  → 新装是 `~/.hermes/platforms/pairing/`,只有旧目录**有内容**时才回落旧路径
  (`hermes_constants.py:278-282`)。同仓 CLI 提示已经用新路径:
  `hermes_cli/pairing.py:96-97` `"~/.hermes/platforms/pairing/_rate_limits.json"`;
  备份清单两个都列(`hermes_cli/backup.py:1116-1117`)。
- **裁决**:▲ 证实(轻微,但会让运维找错目录)。**含模块自身 docstring**。

### ▲4 文档引用的启动告警文案已不存在

- **文档**:`website/docs/user-guide/security.md:359-365`("The gateway logs a warning at startup:")
  ```text
  No user allowlists configured. All unauthorized users will be denied.
  Set GATEWAY_ALLOW_ALL_USERS=true in ~/.hermes/.env to allow open access,
  or configure platform allowlists (e.g., TELEGRAM_ALLOWED_USERS=your_id).
  ```
- **代码**:`gateway/run.py:10886-10892` 的实际文案完全不同(见 §1.6 引文),
  且语义更弱("default to pairing/allowlist policies and will deny unknown senders unless…")。
  全仓 grep `"No user allowlists configured"` 只命中 `tests/gateway/test_relay_upstream_authz.py:14`
  的注释,**生产代码里不存在这句**。
- **裁决**:▲ 证实(轻微)。

### ▲5 代码注释:自有策略适配器"默认 open" —— 与实际默认值不符

- **注释侧**:`gateway/authz_mixin.py:229-232`("these adapters default to ``open``")、
  `gateway/authz_mixin.py:617-618`("The adapters default dm_policy / group_policy to \"open\"")、
  `gateway/platforms/base.py:2897-2900`(同)
- **代码侧**:所有自有策略适配器的实际默认值是 **`pairing`**:
  - `gateway/platforms/weixin.py:1230` `os.getenv("WEIXIN_DM_POLICY", "pairing")`
  - `gateway/platforms/qqbot/adapter.py:239` `extra.get("dm_policy", "pairing")`
  - `plugins/platforms/wecom/adapter.py:188` `os.getenv("WECOM_DM_POLICY", "pairing")`
  - `plugins/platforms/whatsapp/adapter.py:431` `_wenv("WHATSAPP_DM_POLICY", "pairing")`
  - `gateway/platforms/yuanbao.py:4947-4949` `os.getenv("YUANBAO_DM_POLICY", "pairing")`
  - 启动闸的兜底也是 pairing:`gateway/run.py:2438, 2442`
  - **唯一例外**是 WhatsApp Cloud:`gateway/platforms/whatsapp_cloud.py:287-290`
    无 allow_from 时默认 `"open"`。
- **裁决**:▲ 证实。注释把**唯一例外**当成了通例。**机制本身是对的**(代码只信 `allowlist`),
  但注释里"默认 open 所以不能信"的因果讲反了实际风险面——真实默认是 `pairing`,
  它同样不被信任(`gateway/authz_mixin.py:626-628` 有单独交代),结论不变。

### ▲6 命名漂移两处

- `gateway/authz_mixin.py:583` 注释写 `hermes gateway pairing approve`;
  **真实命令是 `hermes pairing approve`**(`hermes_cli/subcommands/pairing.py:16-24`,
  挂在顶层 subparsers:`hermes_cli/main.py:11601`)。全仓无 `hermes gateway pairing` 子命令。
- `plugins/platforms/discord/adapter.py:8309` 注释写 "mirrors ``authz_mixin._check_authorization``";
  **`_check_authorization` 全仓不存在**(grep 唯一命中就是这句注释),真实方法名是
  `_is_user_authorized`(`gateway/authz_mixin.py:386`)。
- **裁决**:▲ 证实(轻微,但会浪费读者一次 grep)。

### ◇1 request-id 批准路径:代码有、文档无

- **文档**:`website/docs/reference/cli-commands.md:1119`
  ```text
  | `approve <platform> <code>` | Approve a pairing code. |
  ```
  `website/docs/user-guide/security.md:409-410` 同样只给 `hermes pairing approve telegram ABC12DEF`。
  全仓 `grep -rn "request_id\|request-id" website/docs/` **零命中**(配对语境)。
- **代码**:`gateway/pairing.py:735-768` `approve_request`;CLI 形状分派
  `hermes_cli/pairing.py:71-74`;parser metavar 已是 `request-id|code`
  (`hermes_cli/subcommands/pairing.py:31`);`hermes pairing list` 输出里就有 Request ID 列
  (`hermes_cli/pairing.py:42-49`);dashboard `POST /api/pairing/approve` 同样双路
  (`hermes_cli/web_server.py:12330-12339`)。
- **裁决**:◇ 证实。这是**管理界面唯一可用的批准方式**(GUI 拿不到码),却完全没进文档。

### ◇2 `channel_aliases.json`:用户可写的功能,文档零记载

- **文档**:`grep -rn "channel_aliases" website/ *.md` **零命中**。
- **代码**:`gateway/channel_directory.py:32-36`(常量+格式说明)、`39-47`(加载)、
  `50-81`(覆盖+占位注入)、`201`(build 时重放)、`509,516,520`(load 时重放);
  备份清单收录 `hermes_cli/backup.py:1099`;测试 `tests/gateway/test_channel_directory.py:320-355`。
- **裁决**:◇ 证实。用户能用、被备份、有测试,就是没文档。

### ◇3 频道目录**无 profile 隔离**:代码事实,文档未提

- **代码**:`gateway/channel_directory.py:21,36` 两个路径都是模块级
  `get_hermes_home() / ...`,**import 时求值一次**,全文件无 `profile` 字样;
  而同期的配对库(`gateway/pairing.py:421-437`)、adapter 解析
  (`gateway/authz_mixin.py:93-128`)都做了 per-profile。
- **后果推演(我的判断,非代码断言)**:multiplex 网关下 A/B 两个 profile 的频道会写进
  同一份 `channel_directory.json`,`send_message` 的 `action="list"` 会看到别的 profile 的目标。
- **裁决**:◇(代码有此缺口、文档无记载)。列为重实现时要补的点。

### ◇4 `_auth_env` 与 `_platform_gate_env` 的 multiplex 隔离不对称

- **代码 A**:`gateway/authz_mixin.py:46-72` `_platform_gate_env` —— scope 命中即权威,
  **miss 返回 default,不回落 os.environ**(#72348)。
- **代码 B**:`gateway/authz_mixin.py:31-43` `_auth_env` —— `get_secret` 返回 None/空,
  或抛 `UnscopedSecretError` 被 `except Exception: pass` 吞掉后,**一律回落 `os.getenv`**:
```python
def _auth_env(name: str, default: str = "") -> str:
    """Read allowlist/auth env; prefer profile secret_scope under multiplex."""
    if not name:
        return default
    try:
        from agent.secret_scope import get_secret

        val = get_secret(name)
        if val is not None and str(val).strip():
            return str(val).strip()
    except Exception:
        pass
    return (os.getenv(name) or default).strip()
```
- **`get_secret` 的 fail-closed 意图**:`agent/secret_scope.py:152-153, 175-178` —— multiplex
  活跃且无 scope 时 **raise `UnscopedSecretError`**,"so the missing scope is caught loudly
  instead of leaking a cross-profile value"。`_auth_env` 的 bare `except` 恰好把这个信号吃掉。
- **实际影响面**:`_is_user_authorized` 用 `_auth_env` 读的是
  `{PLATFORM}_ALLOW_ALL_USERS`(570)、`{PLATFORM}_ALLOWED_USERS`(601)、
  `{PLATFORM}_GROUP_ALLOWED_*`(605-606)、`GATEWAY_ALLOWED_USERS`(607)、
  `GATEWAY_ALLOW_ALL_USERS`(691)——**恰恰是最核心的五组**。
  而 Discord 适配器 intake 侧对**同一批 key** 用的是 `_platform_gate_env`:
  `plugins/platforms/discord/adapter.py:383-395` 的 `_GATE_ENV_KEYS` 含
  `DISCORD_ALLOWED_USERS`、`DISCORD_ALLOW_ALL_USERS`、`GATEWAY_ALLOWED_USERS`、
  `GATEWAY_ALLOW_ALL_USERS`,`_scoped_gate_env:398-405` 直接转调 `_platform_gate_env`。
- **裁决**:◇(不对称是代码事实,文档无记载)。可能是 #72348 有意的窄修范围,
  但 `_platform_gate_env` 的 docstring 未说明为何用户名单不在保护范围内。
  **列为重实现时要统一的点。**

### ◇5 全局 `unauthorized_dm_behavior: pair` 无法压过"有名单即 ignore"

- **代码**:`gateway/authz_mixin.py:826-829`
```python
        # Check for an explicit global config override.
        if config and hasattr(config, "unauthorized_dm_behavior"):
            if config.unauthorized_dm_behavior != "pair":  # non-default → explicit override
                return config.unauthorized_dm_behavior
```
  默认值就是 `"pair"`(`gateway/config.py:941`),显式写 `pair` 与不写**不可区分**,
  于是走到 879-886 的"有名单→ignore"。想要"既有名单又给陌生人发码"**只能写 per-platform**
  (`platforms.<x>.extra.unauthorized_dm_behavior: pair`,由 812-816 拦截返回)。
- **文档**:`website/docs/user-guide/security.md:385-388` 只说
  "`pair` is the default for chat-style DM platforms" / "Platform sections override the global
  default",没提"全局写 pair 等于没写"。
- **测试**:`tests/gateway/test_unauthorized_dm_behavior.py` 无此用例(已核 §8)。
- **裁决**:◇ / 轻微 ▲。这是"用 sentinel 值当'未设置'"的经典陷阱,重实现要用
  `Optional[str] = None` 区分。

### ◇6 `_get_unauthorized_dm_behavior` 的平台 env 表漏 Yuanbao

- **代码**:`gateway/authz_mixin.py:507-526` 的 `platform_env_map` 含
  `Platform.YUANBAO: "YUANBAO_ALLOWED_USERS"`(525 行);
  `gateway/authz_mixin.py:853-871` 的同名局部表**止于 QQBOT(870),无 YUANBAO**。
- **同类前案**:`tests/gateway/test_unauthorized_dm_behavior.py:381-388` 的注释记载
  #9337 首版就漏过 QQBOT,导致"QQ 运营者配了严格名单,陌生人还是收到配对码"。
- **可达性**:Yuanbao 的 `dm_policy` 默认 `pairing`(`gateway/platforms/yuanbao.py:4947-4949`),
  会在 844-845 行先返回 `"pair"`,所以只有当 `_adapter_dm_policy` 返回空串
  (无活体 adapter 且 config.extra 无 dm_policy)时才会暴露这个遗漏。
- **裁决**:◇(窄,但与已修的 #9337 同型)。

---

## 7. issue 溯源

| # | 位置 | 因果经过(输入→现象→原因→修法) |
|---|------|--------------------------------|
| **#72348** | `gateway/authz_mixin.py:56`(+`plugins/platforms/discord/adapter.py:373-380`) | 输入:multiplex 网关同时跑 profile A、B,两边 config.yaml 各有 `allowed_users`。现象:B 的用户被 A 的名单裁决(或反之)。原因:适配器的 YAML→env 桥是**先写者胜**,`os.environ` 是进程全局,`os.getenv` 读到的是先启动那个 profile 的值。修法:新增 `_platform_gate_env`,multiplex+有 scope 时以 scope 为准,**key 缺失返回 default 而不是回落 env**;适配器侧同步用 `_scoped_gate_env`,且 secondary profile 的 `_apply_yaml_config` 不再往进程 env 写(`adapter.py:418-433`)。 |
| **#4466** | `gateway/authz_mixin.py:487` | 输入:Slack Workflow Builder 发的 `subtype=bot_message`(`user=None`)。现象:自动化消息被当陌生人拒。原因:bot 流量没有 user_id,过不了人类名单。修法:`{PLATFORM}_ALLOW_BOTS ∈ {mentions, all}` 放行,且**必须放在 `if not user_id` 之前**(493-502 在 504 之前)。 |
| **#23778** | `gateway/authz_mixin.py:589`;`gateway/pairing.py:66` | 输入:运营者配了 `TELEGRAM_ALLOWED_USERS`,又通过配对批准了一个人。现象:该人存在于 `approved.json` 却不在名单里,运营者看名单以为"只有这些人",实际多一个,且删名单删不掉他。原因:两份真值源漂移。修法(option i):批准时**若已有名单**就把人一并写进名单(`_sync_allowlist_add:175-201`),撤销时按别名删(`_sync_allowlist_remove:292-327`);**开放网关不写**,免得首次配对把开放网关静默变封闭。注释还澄清 #23778 的原始 bug 是**入站消息/批准按钮那道闸**,不是这道并集闸。 |
| **#34515** | `gateway/authz_mixin.py:631, 661` | (a) 输入:WeCom/WhatsApp 等自有策略适配器 `dm_policy: open`,网关无 env 名单。现象:任何人都能用 bot。原因:网关把"消息到达了网关"当作"适配器已授权",而 `open` 是转发一切。修法:**只在 effective policy == `allowlist` 时才信任**。(b) 输入:`hermes pairing revoke` 删掉 WhatsApp 名单里唯一一项。现象:被撤销的人还能继续用,直到重启。原因:适配器构造时快照了 `_allow_from`。修法:trust 前回调活体适配器的 `_is_dm_allowed(user_id)` 复核(662-673)+ `_sync_live_adapter_allowlist_remove` 清快照(`gateway/pairing.py:261-289`)。 |
| **#15027 / PR #17686** | `gateway/authz_mixin.py:703` | 输入:老用户把 Telegram **chat id**(负数,如 `-1001234`)填进了 `TELEGRAM_GROUP_ALLOWED_USERS`。现象:PR #17686 把该变量改成"发送者 user id"语义后,这些人整群失效。原因:变量语义变更没有兼容层。修法:值以 `-` 开头的当 chat id 处理,并**一次性 warn** 引导迁移到 `TELEGRAM_GROUP_ALLOWED_CHATS`(709-731,`_warned_telegram_group_users_legacy` 保证只 warn 一次)。 |
| **#9337** | `gateway/authz_mixin.py:806` | 输入:运营者配了 `TELEGRAM_ALLOWED_USERS`,陌生人 DM 进来。现象:bot 回了配对码 —— 既暴露"这里有个 Hermes",又给陌生人刷屏。原因:`unauthorized_dm_behavior` 默认 `pair`,没有考虑"配了名单说明想收紧"。修法:任一名单存在即降级为 `ignore`(879-886)。**回归**:首版漏了 QQBOT,`tests/gateway/test_unauthorized_dm_behavior.py:381-388` 立了守卫(见 ◇6:Yuanbao 至今仍漏)。 |
| **#10270** | `gateway/pairing.py:477` | 输入:`docker exec <container> hermes pairing approve telegram ABC12DEF`(默认 root)。现象:CLI 打印"Approved!",用户下条消息仍被拒。原因:approved.json 被写成 `0600 root:root`,网关 gosu 降权为 `hermes` 后读不到;`except OSError` 把 `PermissionError` 一起吞了,返回 `{}`。修法:单独捕 `PermissionError`,warn 出 owner_uid/mode/euid 和 `-u hermes` 的修复指引。文档同步:`website/docs/user-guide/security.md:419-435`。 |
| **#10195** | `gateway/pairing.py:671` | 输入:运营者连打错 5 次码后再输正确码。现象:一直"code not found",无从判断为何。原因:`approve_code` 对无效码和锁定**返回同一个 None**。修法:调用方用 `_is_locked_out(platform)` 消歧,CLI 打印剩余分钟数与手工清除方法(`hermes_cli/pairing.py:81-98`),dashboard 返回 429(`hermes_cli/web_server.py:12345-12350`)。 |
| **#27602** | `hermes_constants.py:263`(经 `gateway/pairing.py:59`) | 输入:安装脚手架/手动 mkdir 留下空的 `~/.hermes/pairing/`,真数据在 `platforms/pairing/`。现象:所有已批准用户失效。原因:`get_hermes_dir` 原来只判"旧目录存在"。修法:改判"旧目录**有内容**"(`_legacy_path_has_content`)。 |
| **#31041**(salvage) | `scripts/release.py:146` 记载 | 内容:"pairing: merge split legacy/new pairing store dirs at PairingStore init so approved users aren't re-prompted to pair" —— 即 `_merge_pairing_dir` / `_migrate_split_pairing_dirs`(`gateway/pairing.py:340-376`)的来源。现象是已配对 Feishu 用户被重新要码(`gateway/pairing.py:345-346`)。 |
| **#9006** | `gateway/channel_directory.py:408` | 会话来源从 `sessions.json` 迁到 `state.db` 的 gateway session 行(`origin_json`);`_build_from_sessions` 保留 json 兜底供未迁移库使用。 |
| **#16743** | `utils.py:99`(经 `gateway/pairing.py:392` `atomic_replace`) | 输入:托管部署把 `~/.hermes/*.json` symlink 到 git 仓库/dotfiles。现象:一次写入后软链变成实体文件,与仓库脱钩。原因:`os.replace(tmp, target)` 会替换软链本身。修法:先 `os.path.realpath` 解引用再 replace。 |
| **GHSA-ppp5-vxwm-4cf7** | `hermes_cli/web_server.py:463-466` | dashboard 的 Host 头校验(DNS rebinding 防护),间接保护 `/api/pairing/*`。 |

---

## 8. 测试(行为规格)

**本轮实跑,全绿**(`HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh …`):
第一批 4 文件 62 用例、第二批 7 文件 49 用例,合计 **11 文件 111 用例 0 失败**。

| 测试文件 | 钉住的行为 |
|----------|-----------|
| `tests/gateway/test_pairing.py`(680 行,29 用例) | **哈希存储**:pending.json 必含 64-hex `hash` + 32-hex `salt`,明文码既非 key 也非任何 value(`:127-162`);**明文全文不出现**(`:155-161`);码唯一性(`:109`);legacy/畸形条目跳过不崩(`:164-228`);限速(`:231`)、pending 上限 3(`:246`);**成功批准重置失败计数**(`:392`)、**锁定挡住 approve_code**(`:416`);TTL 清理(`:459`);revoke(`:481`);`list_pending` **字段白名单 + 摘要前缀两条批准路径都不认**(`:303-330`);**过期 request-id 反复点不触发锁定**(`:332-354`);WhatsApp 旧 raw JID 批准在别名翻转后仍有效(`:356`);**profile 隔离六连**(全局/profile 目录、与 `hermes -p` CLI 同源、default 映射回全局、split 布局合并、批准不泄漏到全局、独立 rate-limit 文件)(`:557-679`);split 目录合并(`:31`);`_secure_write` 权限位(`:95`);**PermissionError 大声 warn**(`:520`)。 |
| `tests/gateway/test_pairing_allowlist_bypass.py`(394 行,13 用例) | 配对与名单的**并集**双向(`:62,70`);**已有名单时批准写入名单**(`:99`)、撤销移除(`:115`);WhatsApp 别名撤销四连(设备 JID→裸号、全形态、Cloud、**保留 `*` 通配**)(`:132-215`);**唯一名单项被撤销后活体适配器立即拒绝、无需重启**(`:216`);显式 config 优先于 env、显式空 `allow_from` 挡住 env 授予、env 补种后重读、env key 被删后拒绝(`:306-393`)。 |
| `tests/gateway/test_unauthorized_dm_behavior.py`(398 行,13 用例) | 有名单→`ignore`(Telegram/Signal/全局/QQBOT 四例,`:300,318,338,381`);无名单→`pair`(`:356`);**Email 无名单也 ignore**(`:369`);WhatsApp LID 发送者匹配手机号名单(`:84`);SimpleX 接受显示名(`:120`);Telegram 旧 chat-id 兼容 + 混合(`:158,184`)。 |
| `tests/gateway/test_config_driven_access_policy.py`(262 行,23 用例) | 基类 `enforces_own_access_policy` 默认 False(`:100`);五个自有策略适配器都声明该 flag(参数化,`:118`);**policy==allowlist 时无 env 名单也授权**(`:136`);**dm_policy==pairing 的 intake 严格拒未知**(`:161`)、空 principal 拒(`:177`);WeCom 开放群 + 每群发送者名单→授权(`:192`);`unauthorized_dm_behavior` 跟随 dm_policy 映射(`:242`);**open 策略不改默认**(`:253`)。 |
| `tests/gateway/test_relay_upstream_authz.py`(175 行,4 用例) | 基类 `authorization_is_upstream` 默认 False(`:84`);非 upstream 适配器仍默认拒(`:96`);**relay 消息带底层 discord platform 也被授权**(`:128`);wire 事件盖 routed profile(`:150`)。 |
| `tests/gateway/test_multiplex_profile_authz.py`(134 行,5 用例) | default profile 信任自己的名单(`:53`);active profile 标记解析到主适配器(`:69`);secondary 名单下未授权 DM 被 ignore(`:77`);适配器 auth 检查盖 secondary profile(`:89`);**secondary 的 open 策略触发启动闸失败**(`:117`)。 |
| `tests/gateway/test_multiplex_pairing_stores.py`(87 行,2 用例) | secondary profile 的 PairingStore 被创建(`:31`);store 目录按 profile 划分(`:64`)。 |
| `tests/hermes_cli/test_pairing.py`(43 行,1 用例) | **CLI 列出的 request-id 与 bot DM 的码两条路都能批准**(`:8`)。 |
| `tests/gateway/test_internal_event_bypass_pairing.py`(215 行,3 用例) | 内部合成事件**完全绕过 authz**(不调 `_is_user_authorized`,`:78`);`notify_on_complete` 从 session store 取 origin(`:127`);**user_id=None 不生成配对码**(`:180`)。 |
| `tests/gateway/test_whatsapp_identity.py`(23 行,1 用例) | 别名在 `platforms/whatsapp/session` 新布局下解析(`:8`)。 |
| `tests/gateway/test_whatsapp_allowlist_lid_resolution.py`(115 行,5 用例) | DM 手机号名单匹配 LID 发送者(含带 `+`,`:65,73`);群 JID 精确匹配仍有效(`:83`);未列 JID 被拦(`:92`);`should_process_message` 端到端(`:102`)。 |
| `tests/gateway/test_whatsapp_to_jid.py`(43 行,2 用例) | 裸手机号→`@s.whatsapp.net`(参数化,`:27`);完整 JID 原样透传(`:40`)。 |
| `tests/gateway/test_channel_directory.py`(357 行,19 用例) | 缺文件返回空壳(`:47`);**写失败保留旧缓存**(`:55`);优先用 adapter `list_channels`(`:74`);**Discord 构建跑在 event loop 之外的线程**(`:95`);名字解析四级(精确/大小写/唯一前缀/无匹配)(`:119-158`);从 sessions.json 构建(`:166`);显示格式化含"未发现频道"提示与显式 platforms 覆盖(`:202-225`);`lookup_channel_type`(`:231,241`);Slack 无 team client 回落 session、`users.conversations` 列举、游标分页(`:266-319`);**别名注入未发现的群、别名穿越重建存活**(`:330,342`)。 |
| `tests/gateway/test_channel_directory_connected_only.py`(35 行,1 用例) | **不从会话历史复活已断开的平台**(`:14`)。 |

**未被测试钉住的行为(重实现时的风险点)**:
- 全局 `unauthorized_dm_behavior: pair` + 有名单 的组合(◇5);
- Yuanbao 在 `_get_unauthorized_dm_behavior` 里的名单遗漏(◇6);
- 跨进程并发写 pending.json(§2.6);
- `_auth_env` 在 multiplex 下的 env 回落(◇4)。

---

## 9. 重实现要点(安全相关的每一处默认值都点名)

### 9.1 授权模型

1. **单档布尔,不做 RBAC。** 没有 owner/admin 等级——"owner" 是拿着 shell/dashboard 的人,
   由**批准动作的入口位置**体现,而不是消息平台上的某个 id。这是极大的简化,
   代价是无法表达"这个人能用 A 工具不能用 B"(那由审批系统 R3 域另行处理)。
2. **并集,不做拒绝列表。** 任一凭据命中即通过。好处:运营心智一行搞定;
   坏处:无法"全组放行但排除某人"。若要加 deny-list,必须**放在所有 allow 之前**,
   否则 `return True` 短路会让它形同虚设。
3. **默认拒绝。** `_is_user_authorized` 兜底是 `False`
   (`gateway/authz_mixin.py:783` 交集为空 / `:691` allow-all 未设)。
4. **信任委派要有"不可伪造的传输标记",不能靠可序列化字段。**
   `delivered_via_upstream_relay` 被**显式排除出 `to_dict`/`from_dict`**
   (`gateway/session.py:214-216`),`_transport_adapter_ref` 是 weakref 且不序列化
   (`gateway/platforms/base.py:6664-6667`)。**照抄这个约束。**
5. **用 `is True` 而不是 truthiness 判信任标记**(`gateway/authz_mixin.py:435, 578`)——
   防 mock/属性自动真值化造成的意外 fail-open。这是廉价且有效的防御。
6. **"消息到达了"≠"已授权"。** 只有当下游策略是**真正的 allowlist 限制**时才承认
   (`gateway/authz_mixin.py:653`)。`open` / `pairing` / 未知一律降级到默认拒绝。#34515 是血的教训。
7. **快照要能被撤销打穿。** 构造期抓的 `_allow_from` 必须有活体复核路径
   (`gateway/authz_mixin.py:662-673`),否则 revoke 要等重启。
8. **无用户身份的流量要单独设计**,不能一律拒(匿名管理员、频道广播、Workflow bot)。
   决定放行的凭据必须是**chat 维度**而不是 user 维度,并且检查要排在 `if not user_id` 之前。
9. **多租户下的 env 读取必须权威、不回落。** `_platform_gate_env` 是对的
   (`gateway/authz_mixin.py:63-69`);`_auth_env` 的回落是缺口(◇4)。
   重实现时**统一走一个权威读取器**,并让 "multiplex 活跃但无 scope" **抛异常而不是吞掉**。
10. **启动期硬闸**:开放策略未显式 opt-in 就拒绝启动
    (`gateway/run.py:2428-2456` + `:10893-10913`)。比运行期 warn 有效得多。

### 9.2 配对系统的每一个默认值

| 参数 | 值 | 位置 | 取舍 |
|------|-----|------|------|
| 字母表 | 32 字符,去 0/O/1/I | `pairing.py:47` | 可抄写性 > 熵(2^40 已够,防线是锁定) |
| 码长 | 8 | `pairing.py:48` | — |
| 随机源 | `secrets.choice` | `gateway/pairing.py:641` | **必须 CSPRNG**,不能 `random` |
| 存储 | 每条独立 16B 盐 + SHA-256 | `pairing.py:583, 644-645` | 无 KDF 拉伸;定长高熵+1h TTL 下可接受 |
| 文件键 | `secrets.token_hex(8)`,**不是码** | `gateway/pairing.py:648` | 使 GUI 能引用条目而不泄露码 |
| 比较 | `secrets.compare_digest` | `gateway/pairing.py:712, 765` | 常数时间,两条批准路径都用 |
| TTL | 3600s | `pairing.py:51` | 清理发生在 generate/approve/list 三入口 |
| 单用户限速 | 600s,**按别名集** | `pairing.py:52, 819-823` | 防别名绕过 |
| 平台待批上限 | 3 | `pairing.py:56` | **全局配额 ⇒ 有 DoS 面**,换来爆破面小 |
| 锁定阈值 | 5 次 | `pairing.py:57` | 只计 `approve_code`,不计 `approve_request` |
| 锁定时长 | 3600s | `pairing.py:53` | 触发后计数归零,不是永久锁 |
| 成功重置计数 | 有 | `pairing.py:598, 856-867` | **必须有**,否则终身累加会误锁 |
| 文件权限 | `chmod 0600` | `pairing.py:394` | Windows 上静默跳过 |
| 落盘 | mkstemp+fsync+atomic_replace | `pairing.py:386-392` | 解 symlink(#16743) |
| 码入日志 | **从不** | 全文件唯一 `print` 在 `:852-853`,不含码 | — |
| 批准入口 | **仅 CLI + 已认证 dashboard** | `hermes_cli/pairing.py:72,74`;`hermes_cli/web_server.py:12337,12339` | 入站通道只能领码不能兑码 |
| 名单镜像 | **仅在已有名单时写** | `pairing.py:187-189` | 不把开放网关静默变封闭 |
| 撤销匹配 | 按别名 + 保留 `*` | `pairing.py:311-315` | 精确串删会漏 |
| 读文件失败 | 返回 `{}`(= 无人被批准) | `pairing.py:494, 496` | **fail closed** |
| 并发 | 进程内 RLock,**跨进程无锁** | `pairing.py:450` | 重实现应加文件锁 |

**额外三条:**

- **`approve_request` 不计入锁定、也不被锁定挡住**(`pairing.py:748-751`)。理由:request id
  只有已认证管理员拿得到,点到过期行是"行陈旧"不是"攻击";若计入,GUI 上点几下就会把运营者
  自己的 CLI 码路径锁死。**这是把"凭据的攻击面"与"UI 的误操作面"分开对待的好例子。**
- **两种凭据的形状必须不可能撞车**(`pairing.py:723-733`):16 位小写 hex vs 8 位大写无歧义字母。
  这样单参数入口才能安全地按形状分派。
- **升级容错**:老格式条目一律跳过而非崩溃,靠 TTL 自然清除
  (`pairing.py:704-706, 882-889`)。持久化 schema 演进要预留这条。

### 9.3 身份规范化

- **凡是平台可能给同一个人两个 id 的,必须有单一真值模块**,并让 authz 与 session-key
  **共用同一个函数**(`gateway/whatsapp_identity.py:9-12` 的自陈)。两条路径各写一份必然漂移。
- **别名集合必须包含输入本身**(`gateway/whatsapp_identity.py:155` + 127-130 的契约声明),
  调用方才能无脑 `in`。
- **别名比较要双向展开**(名单项和待检 id 都展开,`gateway/authz_mixin.py:756-763`)。
- **标识符若会拼进文件名,先过字符白名单**(`gateway/whatsapp_identity.py:43, 152`),
  即使已有前缀常量兜底——"不依赖文件系统布局不变量"是对的。
- **出站与入站的规范化是两个函数,方向相反**(`to_whatsapp_jid` vs
  `normalize_whatsapp_identifier`)。混用会让 Baileys 崩。

### 9.4 频道目录

- **它是缓存,不是真值**:全量重建、无 TTL、无单条失效。重建失败保留旧版
  (`gateway/channel_directory.py:210-211`)。
- **只暴露"本进程连着的平台"**(`gateway/channel_directory.py:168-182`)——历史会话不能复活
  成发送目标,否则消息会路由到发不出去的平台。
- **名字解析歧义时返回 None**(`gateway/channel_directory.py:573-577`),不猜。发错群不可撤销。
- **给人工覆盖留一层**(`channel_aliases.json`),并且**在 build 与 load 都重放**,
  这样人工改动既能穿越重建、又能立即生效(`gateway/channel_directory.py:201, 516`)。
- **周期性刷新的错误日志必须节流**(`gateway/channel_directory.py:22-28, 117-135`),
  配置性错误(`missing_scope`)直接降 DEBUG。
- **分页要有安全帽**(`gateway/channel_directory.py:315` 的 `range(20)`)。
- **缺口(重实现要补)**:无 profile 隔离(◇3);`DIRECTORY_PATH` 模块级求值,
  HERMES_HOME 后变不生效。

---

## 10. 台账建议

| 文件 | 行数 | 建议层 | status |
|------|------|--------|--------|
| `gateway/authz_mixin.py` | 888 | L1 | `R7C-deep-read` |
| `gateway/pairing.py` | 905 | L1 | `R7C-deep-read` |
| `gateway/whatsapp_identity.py` | 206 | L1 | `R7C-deep-read` |
| `gateway/channel_directory.py` | 637 | L1 | `R7C-deep-read` |

配套已读(结构级,非本切片):`hermes_cli/pairing.py`(121)、
`hermes_cli/subcommands/pairing.py`(40)、`hermes_cli/web_server.py:12280-12375`、
`gateway/platforms/base.py:2883-2930 / 6650-6668`、`gateway/relay/adapter.py:130-147`、
`gateway/run.py:2418-2456 / 6214-6222 / 10825-10913 / 13246-13265 / 14440-14511 / 26140-26192`、
`gateway/config.py:198-203 / 941 / 1219-1235`、`hermes_constants.py:247-282`。
