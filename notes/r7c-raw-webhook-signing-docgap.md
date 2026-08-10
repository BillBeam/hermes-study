# r7c-raw-webhook-signing-docgap · 五方言验签与运营文档缺口

> 基线 `863e31318553cda8ad61df681d08175364d4164b`(下称 `@ 863e313`)。
> 本文对代码行为的每条断言都紧跟 `路径:行号 @ 863e313` 与代码原文块。
> 起点是 R7B 的 ◇ B-19(`notes/r7b-90-doc-conflict-rulings.md:267-269`),但**独立复核后需要修正**。

---

## 0. 一句话

五种方言里**只有 Svix 一种完全无文档**,英文文档其余四种写得准确完整;真正被 R7B 漏掉的是
**zh-Hans 镜像停留在 V2 之前的旧状态**(▲)与**两条 403 分支从未进过响应码表**(▲)。

---

## 1. 五种方言逐一钉死

### 1.0 "五种"这个数字的出处不是我的归纳

commit `1b69c47e9`(2026-07-16,`fix(webhook): reject a non-ASCII signature header instead
of crashing the endpoint`)的正文自己点了名:

```
_validate_signature backs the public webhook receiver. It compared each
attacker-supplied signature/token header (GitHub X-Hub-Signature-256,
GitLab X-Gitlab-Token, generic X-Webhook-Signature / -V2, and the Svix v1
header) ...
Route all five comparisons through a small _hmac_str_equal() helper ...
```

(`git log -1 1b69c47e9`,该 commit 在基线祖先链上。)所以"五方言"是作者自己的口径。

### 1.1 总表

| # | 方言 | 厂商/来源 | 触发头 | 签名算法 | 被签内容 | 时间窗 | 常数时间比较 | 代码 |
|---|------|-----------|--------|----------|----------|--------|--------------|------|
| 1 | Svix | Svix(AgentMail 等 SaaS 用它做投递) | `svix-id` / `svix-timestamp` / `svix-signature` | HMAC-SHA256 → **base64**,头值格式 `v1,<b64>`,空格分隔可多条 | `"{svix-id}.{svix-timestamp}.{raw_body}"` | **±300s**(`tolerance_seconds` 默认参数) | 是(`_hmac_str_equal`) | `gateway/platforms/webhook.py:1039-1055`、`:1143-1191` |
| 2 | GitHub | GitHub(Gitea/Forgejo 同格式) | `X-Hub-Signature-256` | HMAC-SHA256 → **hex**,带 `sha256=` 前缀 | **raw body** | **无** | 是 | `gateway/platforms/webhook.py:1057-1063` |
| 3 | GitLab | GitLab | `X-Gitlab-Token` | **不是 HMAC**,明文 token 全等比较 | 不签任何内容 | **无** | 是(仍走 `_hmac_str_equal`) | `gateway/platforms/webhook.py:1065-1068` |
| 4 | 自有 V2 | Hermes 自定义(推荐) | `X-Webhook-Signature-V2` + `X-Webhook-Timestamp` | HMAC-SHA256 → **hex**,无前缀 | `"<timestamp>.<raw_body>"` | **±300s**(硬编码字面量 `300`) | 是 | `gateway/platforms/webhook.py:1070-1111` |
| 5 | 自有 V1 | Hermes 自定义(遗留,已废弃) | `X-Webhook-Signature` | HMAC-SHA256 → **hex**,无前缀 | **raw body** | **无**(已知重放洞,首次命中打一次警告) | 是 | `gateway/platforms/webhook.py:1113-1135` |

**优先级是"谁先出现谁生效",顺序固定为 Svix → GitHub → GitLab → V2 → V1**,每个分支一旦进入就
`return`,不会回退到下一个。也就是说:**方言由请求头挑选,而不是由路由配置钉死** —— 见 §1.8。

### 1.2 统一的常数时间比较器 `_hmac_str_equal`

`gateway/platforms/webhook.py:158-169 @ 863e313`:

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

五个分支**全部**经过它(`:1063`、`:1068`、`:1111`、`:1135`、`:1189`),所以"是否常数时间"这一列
五行全是"是"。注意 `compare_digest` 对**长度不等**的输入会快速返回 False,泄漏的是长度而非内容 ——
这是 `compare_digest` 的通用性质,不是本仓库的取舍。

### 1.3 方言 1:Svix

分派逻辑,`gateway/platforms/webhook.py:1039-1055 @ 863e313`:

```python
        # Svix / AgentMail:
        #   svix-id: msg_...
        #   svix-timestamp: unix seconds
        #   svix-signature: v1,<base64-hmac> [v1,<base64-hmac> ...]
        # Signed content is: "{id}.{timestamp}.{raw_body}".  Svix secrets
        # usually start with "whsec_" and the remainder is base64-encoded.
        svix_id = _header("svix-id")
        svix_timestamp = _header("svix-timestamp")
        svix_signature = _header("svix-signature")
        if svix_id or svix_timestamp or svix_signature:
            return self._validate_svix_signature(
                body=body,
                secret=secret,
                msg_id=svix_id,
                timestamp=svix_timestamp,
                signature_header=svix_signature,
            )
```

校验体,`gateway/platforms/webhook.py:1143-1191 @ 863e313`:

```python
    def _validate_svix_signature(
        self,
        body: bytes,
        secret: str,
        msg_id: str,
        timestamp: str,
        signature_header: str,
        tolerance_seconds: int = 300,
    ) -> bool:
        """Validate Svix-compatible signatures used by AgentMail webhooks."""
        if not (msg_id and timestamp and signature_header and secret):
            return False

        try:
            ts = int(timestamp)
        except (TypeError, ValueError):
            return False
        if abs(int(time.time()) - ts) > tolerance_seconds:
            logger.warning("[webhook] Svix signature timestamp outside replay window")
            return False

        if secret.startswith("whsec_"):
            encoded_secret = secret.removeprefix("whsec_")
            try:
                key = base64.b64decode(encoded_secret, validate=True)
            except (binascii.Error, ValueError):
                logger.debug("[webhook] Invalid whsec_ Svix signing secret")
                return False
        else:
            # Be permissive for providers that document Svix-style headers but
            # hand out raw shared secrets rather than whsec_ base64 secrets.
            logger.debug("[webhook] Validating Svix-style signature with raw secret")
            key = secret.encode()

        signed_content = msg_id.encode() + b"." + timestamp.encode() + b"." + body
        expected = base64.b64encode(
            hmac.new(key, signed_content, hashlib.sha256).digest()
        ).decode()

        # Svix can send multiple signatures separated by spaces during secret
        # rotation. Each entry is formatted as "vN,<base64>".
        for part in signature_header.split():
            try:
                version, signature = part.split(",", 1)
            except ValueError:
                continue
            if version == "v1" and _hmac_str_equal(signature, expected):
                return True
        return False
```

要点(全部只在代码里):
- **密钥有两种形态**。`whsec_` 前缀 → 去前缀后 base64 解码得到**二进制** key(`:1164-1170`);
  否则把 secret 的 UTF-8 字节直接当 key(`:1171-1175`)。运维如果把 Svix 控制台里的
  `whsec_xxx` 原样粘进 `config.yaml`,走的是第一条路;如果只粘了 `xxx`,走第二条路且**永远算不对**。
  文档里对这一条**零字**。
- **`validate=True`**(`:1167`)意味着非法 base64 直接 return False,而不是宽容解码。
- **多签名容忍**(`:1182-1190`)是为了 Svix 轮换密钥期间同时发新旧两条签名 —— 只要有一条 `v1` 对上就通过。
- **`tolerance_seconds` 是函数默认参数,调用点没有传**(`:1049-1055` 不含该参数),所以
  实际上是**不可配置的 300 秒**。

**Svix 分支的触发条件是 `or` 而非 `and`**(`:1048`)。只要三个头里出现**任意一个**,就锁定 Svix 分支,
另外两个缺失时在 `:1153-1154` 直接 return False。这带来一个副作用:任何请求只要多带一个
`svix-id: x`,就会让 GitHub / V2 签名**永远得不到校验**,请求被 401 拒。这是**拒绝服务面**而非绕过面
(攻击者本来也拿不到 200),但对运维意味着:**上游代理若注入 svix-* 头会静默打死整条路由**。

### 1.4 方言 2:GitHub

`gateway/platforms/webhook.py:1057-1063 @ 863e313`:

```python
        # GitHub: X-Hub-Signature-256 = sha256=<hex>
        gh_sig = request.headers.get("X-Hub-Signature-256", "")
        if gh_sig:
            expected = "sha256=" + hmac.new(
                secret.encode(), body, hashlib.sha256
            ).hexdigest()
            return _hmac_str_equal(gh_sig, expected)
```

无时间戳 → **无重放保护**。GitHub 自身也不提供,防重放靠 §1.9 的幂等缓存(按 `X-GitHub-Delivery`),
不是靠签名。注意这里连同 `sha256=` 前缀一起做常数时间比较,大小写敏感(GitHub 发小写 hex)。

对照:同仓 `whatsapp_cloud` 适配器实现了**同一个头的另一份代码**,并做了大小写归一化,
`gateway/platforms/whatsapp_cloud.py:1525-1548 @ 863e313`:

```python
    def _verify_signature(self, raw_body: bytes, header: str) -> bool:
        """Verify the X-Hub-Signature-256 HMAC.
        ...
        """
        if not self._app_secret or not header:
            return False
        if not header.startswith("sha256="):
            return False
        expected_hex = header[len("sha256="):].strip()
        if not expected_hex:
            return False
        computed = hmac.new(
            self._app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        # Compare as bytes: compare_digest raises TypeError on a str with
        # non-ASCII characters, and the signature is a raw request header.
        return hmac.compare_digest(
            computed.lower().encode(), expected_hex.lower().encode()
        )
```

两处实现独立演化:whatsapp 版本 `.strip()` + `.lower()`,通用 webhook 版本都没有。同一个
Meta/GitHub 头,同一个仓库,两套宽容度 —— 不是 bug(两边都 fail-closed),但是**重复实现**。

### 1.5 方言 3:GitLab

`gateway/platforms/webhook.py:1065-1068 @ 863e313`:

```python
        # GitLab: X-Gitlab-Token = <plain secret>
        gl_token = request.headers.get("X-Gitlab-Token", "")
        if gl_token:
            return _hmac_str_equal(gl_token, secret)
```

这一条**根本不是签名**:GitLab 把共享密钥明文回传,服务端做全等比较。含义:
**GitLab 路由的 secret 会以明文出现在每一次 HTTP 请求头里**,一旦中间有 TLS 终止代理并记录 header,
密钥即泄漏。而且它**不绑定 body** —— 拿到 token 就能构造任意 payload。这个安全等级差异,
英文文档只写了"plain secret string match, not HMAC"(见 §2.3),没有点破后果。

### 1.6 方言 4:自有 V2(唯一带重放保护的自有格式)

`gateway/platforms/webhook.py:1070-1111 @ 863e313`:

```python
        # Generic V2: X-Webhook-Signature-V2 = <hex HMAC-SHA256 of "<timestamp>.<body>">
        #             X-Webhook-Timestamp = <unix seconds> (required for V2)
        # Checked independently of (and before) legacy V1 below — a sender
        # that only ever sends V2 headers must still validate here; nesting
        # this inside `if generic_sig:` would silently skip V2-only senders.
        #
        # The presence of X-Webhook-Signature-V2 alone selects V2 mode and
        # commits to it — it must NOT fall through to the V1 branch just
        # because the timestamp is missing/malformed/expired. A sender
        # migrating to V2 typically sends both V1 and V2 headers together
        # for compatibility; if incomplete V2 fell through to V1, an
        # attacker who captured one such mixed request could strip the
        # X-Webhook-Timestamp header from a replay and have it validate
        # against the still-present, still-unprotected V1 signature instead
        # — silently downgrading a V2-protected request back to the replay
        # hole V2 exists to close.
        v2_sig = request.headers.get("X-Webhook-Signature-V2", "")
        if v2_sig:
            v2_timestamp = request.headers.get("X-Webhook-Timestamp", "")
            if not v2_timestamp:
                logger.warning(
                    "[webhook] Route '%s' sent X-Webhook-Signature-V2 with "
                    "no X-Webhook-Timestamp — rejecting rather than "
                    "falling back to legacy V1",
                    request.match_info.get("route_name", ""),
                )
                return False
            try:
                ts = int(v2_timestamp)
            except (TypeError, ValueError):
                return False
            if abs(int(time.time()) - ts) > 300:
                logger.warning(
                    "[webhook] Route '%s' generic HMAC V2 timestamp outside replay window",
                    request.match_info.get("route_name", ""),
                )
                return False
            signed_content = v2_timestamp.encode() + b"." + body
            expected_v2 = hmac.new(
                secret.encode(), signed_content, hashlib.sha256
            ).hexdigest()
            return _hmac_str_equal(v2_sig, expected_v2)
```

三条独立的 fail-closed 出口(缺 timestamp `:1096`、非整数 `:1100`、超窗 `:1106`),**都不回退到 V1**。
窗口 `300` 是**字面量**,不可配置(对比 Svix 的默认参数,至少形式上是参数)。

### 1.7 方言 5:自有 V1(遗留)

`gateway/platforms/webhook.py:1113-1141 @ 863e313`:

```python
        # Generic V1 (legacy): X-Webhook-Signature = <hex HMAC-SHA256 of body>
        # (deprecated — no replay protection, since the signature only
        # covers the body: a captured (body, signature) pair replays
        # indefinitely with no timestamp binding it to a specific delivery.)
        # Only reachable when X-Webhook-Signature-V2 was not sent at all —
        # see the guard above.
        generic_sig = request.headers.get("X-Webhook-Signature", "")
        if generic_sig:
            expected = hmac.new(
                secret.encode(), body, hashlib.sha256
            ).hexdigest()
            route_name = request.match_info.get("route_name", "")
            if route_name not in self._v1_signature_warned:
                self._v1_signature_warned.add(route_name)
                logger.warning(
                    "[webhook] Route '%s' uses legacy body-only HMAC (no "
                    "timestamp), which is vulnerable to replay attacks. Add "
                    "an 'X-Webhook-Timestamp' header and switch to "
                    "'X-Webhook-Signature-V2' (HMAC-SHA256 of "
                    "'<timestamp>.<body>').",
                    route_name,
                )
            return _hmac_str_equal(generic_sig, expected)

        # No recognised signature header but secret is configured → reject
        logger.debug(
            "[webhook] Secret configured but no signature header found"
        )
        return False
```

去重集合在构造函数里,`gateway/platforms/webhook.py:200-202 @ 863e313`:

```python
        # Routes already warned about legacy V1 body-only signatures
        # (once-per-route so a busy sender doesn't spam the log).
        self._v1_signature_warned: set[str] = set()
```

**每路由只警告一次,且只进 log。**运维如果不看 gateway 日志,永远不知道自己还在用有重放洞的 V1。

### 1.8 没有"钉死方言"的配置项 —— 这是最大的设计取舍

```
$ grep -n "signature_mode\|require_v2\|sig_mode\|dialect\|signature_type\|allowed_signature" \
      gateway/platforms/webhook.py gateway/config.py
(无输出)
```

后果:即使一个路由的真实上游只发 V2,攻击者只要**把 V2 头整个删掉、只留一条历史上抓到的 V1 签名**,
就会落进 V1 分支并**永久重放成功**。`:1076-1085` 的注释只堵住了"V2 头还在、timestamp 被删"这一种
降级;"V2 头也删掉"这一种堵不住,因为 V1 与 V2 **共用同一个 secret**。仓库自己把这一点写成了测试
(见 §5,`test_v1_replay_attack_succeeds_demonstrating_the_hole_v2_closes`),即**明知且接受**。

对自建 harness 的启示:**方言协商必须是配置态而非请求态**。请求头选择校验算法 = 让攻击者选算法。

### 1.9 `_header()` 的大小写宽容只对 Svix 生效

`gateway/platforms/webhook.py:1032-1037 @ 863e313`:

```python
        def _header(name: str) -> str:
            return (
                request.headers.get(name, "")
                or request.headers.get(name.lower(), "")
                or request.headers.get(name.upper(), "")
            )
```

只有 Svix 分支用 `_header()`,其余四个分支直接 `request.headers.get(...)`。实测 aiohttp 的
`request.headers` 本身就是大小写不敏感的:

```
$ /home/user/hermes-venv/bin/python -c "
from aiohttp.test_utils import make_mocked_request
r = make_mocked_request('POST','/x',headers={'Svix-Id':'msg_1'})
print(type(r.headers).__name__, '| get(svix-id) ->', repr(r.headers.get('svix-id')))"
CIMultiDictProxy | get(svix-id) -> 'msg_1'
```

所以 `_header()` 在生产路径上是**冗余**的;它真正起作用的地方是单元测试的 mock —— 测试用普通
`dict` 当 headers(`tests/gateway/test_webhook_adapter.py:80-92`,`req.headers = headers or {}`),
普通 dict 大小写敏感。这不是 bug,但是"防御性代码被测试脚手架反向塑形"的一个标本。

### 1.10 配置项:secret 配在哪

**全局(环境变量)**,`gateway/config.py:2173-2187 @ 863e313`:

```python
    # Webhook platform
    webhook_enabled = is_truthy_value(getenv("WEBHOOK_ENABLED", ""))
    webhook_port = getenv("WEBHOOK_PORT")
    webhook_secret = getenv("WEBHOOK_SECRET", "")
    if webhook_enabled:
        if Platform.WEBHOOK not in config.platforms:
            config.platforms[Platform.WEBHOOK] = PlatformConfig()
        config.platforms[Platform.WEBHOOK].enabled = True
        if webhook_port:
            try:
                config.platforms[Platform.WEBHOOK].extra["port"] = int(webhook_port)
            except ValueError:
                pass
        if webhook_secret:
            config.platforms[Platform.WEBHOOK].extra["secret"] = webhook_secret
```

**全局 + 每路由(YAML)**,读取点 `gateway/platforms/webhook.py:191-195 @ 863e313`:

```python
        _cfg_host = config.extra.get("host", DEFAULT_HOST)
        self._host: Optional[str] = _cfg_host or None
        self._port: int = int(config.extra.get("port", DEFAULT_PORT))
        self._global_secret: str = config.extra.get("secret", "")
        self._static_routes: Dict[str, dict] = config.extra.get("routes", {})
```

回退关系(路由优先,回退全局),`gateway/platforms/webhook.py:657 @ 863e313`:

```python
        secret = route_config.get("secret", self._global_secret)
```

**启动期强制**,`gateway/platforms/webhook.py:252-272 @ 863e313`:

```python
        # Validate routes at startup — secret is required per route
        for name, route in self._routes.items():
            secret = route.get("secret", self._global_secret)
            if not secret:
                raise ValueError(
                    f"[webhook] Route '{name}' has no HMAC secret. "
                    f"Set 'secret' on the route or globally. "
                    f"For testing without auth, set secret to '{_INSECURE_NO_AUTH}'."
                )

            # Safety rail: refuse to start if INSECURE_NO_AUTH is combined with a
            # non-loopback bind. The escape hatch is for local testing only;
            # serving an unauthenticated route on a public interface is a
            # deployment-grade footgun we'd rather crash early than ship.
            if secret == _INSECURE_NO_AUTH and not _is_loopback_host(self._host):
                raise ValueError(
                    f"[webhook] Route '{name}' uses INSECURE_NO_AUTH secret "
                    f"but is bound to non-loopback host '{self._host}'. "
                    f"INSECURE_NO_AUTH is for local testing only. "
                    f"Refusing to start to prevent accidental exposure."
                )
```

**结论:一个 secret 服务五种方言,没有 per-dialect key。**Svix 的 `whsec_` 与 GitLab 的明文
token 在配置上是**同一个字段**,靠 §1.3 的 `startswith("whsec_")` 运行时嗅探区分。

### 1.11 `webhook_filters.py` 与验签无关

任务简报点名了这个文件,复核结论:**它不参与签名校验**。
`gateway/platforms/webhook_filters.py:1 @ 863e313`:

```python
"""Route-local filters and script transforms for the webhook adapter."""
```

```
$ grep -n "hmac\|signature\|Signature\|secret\|verify" gateway/platforms/webhook_filters.py
(无输出)
```

它做的是**过签名之后**的 payload 过滤与脚本变换(对应文档路由属性 `filters` / `script`)。
本文不再展开。

---

## 2. 文档侧穷尽检索

所有命令在 `/home/user/hermes-agent` 下执行,基线 commit `863e313`。

### 2.1 Svix:全仓 Markdown 命中 0

```
$ grep -rniF "svix" website/docs/ website/i18n/ README.md README.es.md README.zh-CN.md \
       README.ur-pk.md AGENTS.md docs/ | wc -l
0
$ grep -rniF --include="*.md" "svix" . | wc -l
0
$ grep -rniF "svix" website/ | wc -l          # 含 .mdx/.ts/.json/userStories 全部前端资产
0
$ grep -rnF --include="*.md" "whsec_" . | wc -l
0
$ grep -rnF "v1,<" website/docs/ website/i18n/ | wc -l
0
```

按方言名 / 头名 / 密钥前缀 / 签名格式四路交叉检索,**全仓所有 `.md` 与整个 `website/` 目录树对
Svix 的命中数是 0**。Svix 这个词在仓库里只出现 37 行,全部在
`gateway/platforms/webhook.py`(22 行)、`tests/gateway/test_webhook_adapter.py`(14 行)、
`scripts/release.py`(1 行贡献者致谢)。

### 2.2 五个头在各文档面的命中数

```
$ for kw in "X-Hub-Signature-256" "X-Gitlab-Token" "X-Webhook-Signature-V2" \
            "X-Webhook-Signature" "X-Webhook-Timestamp" "INSECURE_NO_AUTH"; do
    a=$(grep -rniF -- "$kw" website/docs/ | wc -l)
    b=$(grep -rniF -- "$kw" website/i18n/ | wc -l)
    c=$(grep -rniF -- "$kw" README.md AGENTS.md | wc -l)
    printf "%-24s docs=%-4s i18n=%-4s README+AGENTS=%s\n" "$kw" "$a" "$b" "$c"
  done
X-Hub-Signature-256      docs=4    i18n=4    README+AGENTS=0
X-Gitlab-Token           docs=4    i18n=4    README+AGENTS=0
X-Webhook-Signature-V2   docs=1    i18n=0    README+AGENTS=0
X-Webhook-Signature      docs=2    i18n=1    README+AGENTS=0
X-Webhook-Timestamp      docs=1    i18n=0    README+AGENTS=0
INSECURE_NO_AUTH         docs=4    i18n=4    README+AGENTS=0
```

(`X-Webhook-Signature` 的 2 / 1 含 `-V2` 的子串匹配。)
**README 与根 AGENTS.md 对 webhook 验签只字未提。**`signature` 在这两个文件里只命中 1 行,
且与 webhook 无关 —— `AGENTS.md:317 @ 863e313`:

```markdown
session context, budget, credential pool, etc.). The signature below is the
```

### 2.3 英文正文:四种方言写得对且全

`website/docs/user-guide/messaging/webhooks.md:453-462 @ 863e313`:

```markdown
### HMAC signature validation

The adapter validates incoming webhook signatures using the appropriate method for each source:

- **GitHub**: `X-Hub-Signature-256` header — HMAC-SHA256 hex digest prefixed with `sha256=`
- **GitLab**: `X-Gitlab-Token` header — plain secret string match
- **Generic (V2, recommended)**: `X-Webhook-Signature-V2` + `X-Webhook-Timestamp` headers — HMAC-SHA256 hex digest of `<timestamp>.<body>`. The timestamp (Unix seconds) must be within ±300 seconds of the server clock, which prevents captured requests from being replayed later.
- **Generic (V1, legacy)**: `X-Webhook-Signature` header — raw HMAC-SHA256 hex digest of the body only. Still accepted for backward compatibility, but it has no replay protection (a captured request replays indefinitely); the gateway logs a deprecation warning once per route. Switch senders to V2.

If a secret is configured but no recognized signature header is present, the request is rejected.
```

逐条比对代码:

| 文档断言 | 代码 | 结论 |
|---|---|---|
| GitHub = `sha256=` + hex | `:1060-1062` | ✅ |
| GitLab = 明文字符串匹配 | `:1068` | ✅ |
| V2 签 `<timestamp>.<body>` | `:1107` | ✅ |
| V2 窗口 ±300 秒 | `:1101` `abs(...) > 300` | ✅ |
| V1 只签 body、无重放保护 | `:1121-1123` + 注释 `:1113-1116` | ✅ |
| V1 警告"每路由一次" | `:1125-1126` + `:200-202` | ✅ |
| 配了 secret 但无可识别头 → 拒 | `:1137-1141` | ✅ |

**这七条全部准确。**所以 R7B 的"无完整枚举"必须收窄为:**缺的是 Svix 这一种,不是"这簇没文档"。**

### 2.4 ▲ 新发现:zh-Hans 镜像停在 V2 之前

`website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/user-guide/messaging/webhooks.md:452-460 @ 863e313`:

```markdown
### HMAC 签名验证

适配器使用适合各来源的方式验证传入的 webhook 签名：

- **GitHub**：`X-Hub-Signature-256` 请求头——以 `sha256=` 为前缀的 HMAC-SHA256 十六进制摘要
- **GitLab**：`X-Gitlab-Token` 请求头——明文 secret 字符串匹配
- **通用**：`X-Webhook-Signature` 请求头——原始 HMAC-SHA256 十六进制摘要

若已配置 secret 但请求中不存在已识别的签名请求头，则请求被拒绝。
```

中文读者看到的是:通用方式只有一种,叫 `X-Webhook-Signature`。而这一种**恰恰是代码里已废弃、
有重放洞、命中即打警告的 V1**。英文版的"V2 recommended / V1 legacy no replay protection"
整段**不存在**。这不是"缺文档",这是**文档把废弃方案讲成唯一方案** —— 归 ▲(文档与代码冲突)。

同一文件还缺 multiplex profile 绑定段落(英文 `webhooks.md:468-471` 与路由属性表 `:83`;
中文文件 `grep -n "profile"` 只命中 1 行,且是脚本目录的语境,与路由绑定无关)。

时间线证据:

```
$ git log -3 --format="%h %ad %s" --date=short -- website/docs/user-guide/messaging/webhooks.md
8c5e84653 2026-07-27 fix(gateway): bind HTTP auth to routed profiles
0cf2e39c4 2026-07-02 feat(gateway): add webhook payload filters
708b57e00 2026-07-04 fix(webhook): rate-limit V1 deprecation warning + document V2 signature

$ git log -3 --format="%h %ad %s" --date=short -- \
    website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/user-guide/messaging/webhooks.md
aabfedcac 2026-07-08 docs(webhook): complete filters + route-scripts coverage across doc surfaces (#60983)
76135b329 2026-05-25 docs(i18n): translate all docs into Simplified Chinese (zh-Hans) (#31942)
```

07-04 英文补上 V2;07-08 中文镜像**被动过**(#60983,补 filters 与 route-scripts),
但那一趟没有顺手带上四天前的 V2 段落;07-27 英文再加 profile 绑定,中文再没跟。

**没有任何自动化拦住它。**仓库唯一叫 i18n 的测试是 `tests/agent/test_i18n.py`,
其第 1 行与第 13 行说明它管的是 UI 字符串目录不是文档:

`tests/agent/test_i18n.py:1 @ 863e313`:
```python
"""Tests for agent.i18n -- catalog parity, fallback, language resolution."""
```
`tests/agent/test_i18n.py:13 @ 863e313`:
```python
LOCALES_DIR = Path(__file__).resolve().parents[2] / "locales"
```
```
$ grep -n "website" tests/agent/test_i18n.py
(无输出)
```

对照 R7B 记下的 relay 例外(`tests/gateway/relay/test_contract_doc_conformance.py` 把代码与
`docs/relay-connector-contract.md` 对表):**relay 有一致性测试所以不漂,webhook 文档没有所以漂。**

### 2.5 ▲ 新发现:两条 403 从未进过响应码表

`website/docs/user-guide/messaging/webhooks.md:377-388 @ 863e313`:

```markdown
### Response codes

| Status | Meaning |
|--------|---------|
| `200 OK` | Delivered successfully. Body: `{"status": "delivered", "route": "...", "target": "...", "delivery_id": "..."}` |
| `200 OK` (status=duplicate) | Duplicate `X-GitHub-Delivery` ID within the idempotency TTL (1 hour). Not re-delivered. |
| `401 Unauthorized` | HMAC signature invalid or missing. |
| `400 Bad Request` | Malformed JSON body. |
| `404 Not Found` | Unknown route name. |
| `413 Payload Too Large` | Body exceeded `max_body_bytes`. |
| `429 Too Many Requests` | Route rate limit exceeded. |
| `502 Bad Gateway` | Target adapter rejected the message or raised. The error is logged server-side; the response body is a generic `Delivery failed` to avoid leaking adapter internals. |
```

```
$ grep -n "403" website/docs/user-guide/messaging/webhooks.md
(无输出)
$ grep -n "403" website/i18n/zh-Hans/.../user-guide/messaging/webhooks.md
(无输出)
$ grep -n "status=403\|status=401\|status=404" gateway/platforms/webhook.py
596:                {"error": "Unknown or unconfigured profile"}, status=404
601:                {"error": f"Unknown route: {route_name}"}, status=404
614:                {"error": f"Unknown route: {route_name}"}, status=404
623:                {"error": f"Route disabled: {route_name}"}, status=403
665:                status=403,
673:                    {"error": "Invalid signature"}, status=401
```

代码有两条 403:路由被禁用(`:621-624`)与路由缺 secret(`:658-666`)。表格自称穷举(标题就叫
Response codes)却缺这两行 —— 归 ▲(文档以遗漏的方式与代码冲突)。中英双语同缺。

### 2.6 其余文档面

- `skills/autonomous-ai-agents/hermes-agent/references/webhooks.md:210 @ 863e313`(给 agent 读的
  技能参考,非用户文档):
  ```markdown
  4. **Signature mismatch?** Verify the secret in your service matches the one from `hermes webhook list`. GitHub sends `X-Hub-Signature-256`, GitLab sends `X-Gitlab-Token`.
  ```
  同样只有两种方言。
- `website/docs/reference/environment-variables.md:525 @ 863e313`:
  ```markdown
  | `WEBHOOK_SECRET` | Global HMAC secret for webhook signature validation (used as fallback when routes don't specify their own) |
  ```
  准确,但不提 `whsec_` 形态。
- `website/docs/guides/webhook-github-pr-review.md:267 @ 863e313`:
  ```markdown
  The same adapter works with GitLab. GitLab uses `X-Gitlab-Token` for authentication (plain string match, not HMAC) — Hermes handles both automatically.
  ```
  "**both**" —— 引导读者以为只有两种。

### 2.7 文档侧结论

| 方言 | 英文 docs | zh-Hans | README/AGENTS | 判定 |
|---|---|---|---|---|
| Svix | **完全没有** | 完全没有 | 没有 | **◇**(代码有、文档零) |
| GitHub | 有且准确 | 有且准确 | 没有 | 合格 |
| GitLab | 有且准确(但不点破明文回传后果) | 有且准确 | 没有 | 合格,描述可加强 |
| 自有 V2 | 有且准确(含 ±300s) | **完全没有** | 没有 | **▲**(中文镜像缺失 → 把 V1 讲成唯一方案) |
| 自有 V1 | 有且准确(含 deprecated + 重放说明) | 有,但**未标废弃、未提重放** | 没有 | **▲** |

---

## 3. 运营视角:只看官方文档能不能接通

**结论:接 GitHub / GitLab / 自定义源能通;接任何 Svix 系 SaaS(AgentMail、Resend、Clerk、
Brex 等用 Svix 做投递的服务)不可能通。**

### 3.1 能拿到的(英文文档齐备)

| 运营必答问题 | 文档出处 |
|---|---|
| secret 配哪个 key | 路由级 `secret`,`webhooks.md:82`;全局 `WEBHOOK_SECRET`,`website/docs/user-guide/messaging/webhooks.md:566` |
| 端口/路径 | `WEBHOOK_PORT` 默认 8644,`website/docs/user-guide/messaging/webhooks.md:565`;路径 `/webhooks/<route>`,`webhooks.md:269` |
| 头名字(4/5 种) | `webhooks.md:457-460` |
| V2 容忍窗口 | `webhooks.md:459` "±300 seconds" |
| 验签失败返回什么 | `webhooks.md:383` `401 Unauthorized` |
| 速率限制 | 30/min 固定窗,`webhooks.md:486` |
| 幂等 | `X-GitHub-Delivery` / `X-Request-ID`,1 小时,`webhooks.md:382`、`:395` |
| 本地免鉴权测试 | `INSECURE_NO_AUTH` + 仅回环,`webhooks.md:466`、`:473` |

### 3.2 拿不到的(必须读源码)

1. **Svix 存在这件事本身。**运维看完 `webhooks.md` 的结论会是"我的 AgentMail 走不了,得自己写适配器",
   而代码里 `gateway/platforms/webhook.py:1039-1055` 已经支持了。**这是纯粹的能力浪费。**
2. **Svix 的三个头名**(`svix-id` / `svix-timestamp` / `svix-signature`)。
3. **Svix 密钥两种形态**:`whsec_` 前缀会被 base64 解码(`:1164-1170`),不带前缀按原始字节
   (`:1171-1175`)。粘错一次就是"签名总是不匹配",而**日志只在 debug 级说话**
   (`:1169` `logger.debug("[webhook] Invalid whsec_ Svix signing secret")`)—— 默认日志级别下
   什么都看不到,只有一条通用的 `[webhook] Invalid signature for route %s` warning(`:669-671`)。
   **这是最难自查的一类故障。**
4. **Svix 的 ±300 秒窗口**(`:1150` `tolerance_seconds: int = 300`)。时钟漂移超过 5 分钟的机器上,
   所有 Svix 投递静默 401,而文档只对 V2 讲了 ±300。
5. **Svix 支持轮换期多签名**(`:1182-1190`)—— 能不能无停机轮换密钥,这是运营决策输入。
6. **两条 403 的含义**(§2.5)。收到 403 时运维会去查防火墙/反代,实际是路由被禁或缺 secret。
7. **`svix-id` 也是幂等键。**`gateway/platforms/webhook.py:793-800 @ 863e313`:
   ```python
        # Build a unique delivery ID
        delivery_id = request.headers.get(
            "X-GitHub-Delivery",
            request.headers.get(
                "svix-id",
                request.headers.get("X-Request-ID", str(int(time.time() * 1000))),
            ),
        )
   ```
   文档 `webhooks.md:395` 只说 `X-GitHub-Delivery` / `X-Request-ID`。三选一里漏了一个。
8. **不能按路由钉死方言**(§1.8)。想给一条路由声明"只收 V2"的运维会去翻配置项,翻不到,
   也没有文档说"翻不到是因为不支持"。
9. **CLI 自测只发 GitHub 方言。**`hermes_cli/webhook.py:283-301 @ 863e313`:
   ```python
    import hmac
    import hashlib
    sig = "sha256=" + hmac.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()

    print(f"  Sending test POST to {url}")
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            data=payload.encode(),
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "test",
            },
            method="POST",
        )
   ```
   `hermes webhook test <name>` 通过,**不代表** Svix / V2 通。运维会拿它当"接通了"的证据。

### 3.3 一句话给运维

> 只看官方文档:GitHub、GitLab、自定义 V2/V1 四种能接通,且关键参数(密钥 key、头名、
> ±300s、401)齐全。**Svix 一条信息都没有,必须读 `gateway/platforms/webhook.py:1039-1191`。**
> 中文文档读者还会额外被误导去用有重放洞的 V1。

---

## 4. 验签失败行为与信息泄露面

### 4.1 失败即 401,body 恒定

`gateway/platforms/webhook.py:653-674 @ 863e313`:

```python
        # Validate HMAC signature FIRST (skip only for the explicit local-test
        # INSECURE_NO_AUTH mode). Missing/empty secrets must fail closed here,
        # not only during connect(), so direct handler reuse cannot turn a
        # network webhook route into an unauthenticated agent-dispatch surface.
        secret = route_config.get("secret", self._global_secret)
        if not secret:
            logger.error(
                "[webhook] Route %s has no HMAC secret; refusing request",
                route_name,
            )
            return web.json_response(
                {"error": "Webhook route is missing an HMAC secret"},
                status=403,
            )
        if secret != _INSECURE_NO_AUTH:
            if not self._validate_signature(request, raw_body, secret):
                logger.warning(
                    "[webhook] Invalid signature for route %s", route_name
                )
                return web.json_response(
                    {"error": "Invalid signature"}, status=401
                )
```

- **不静默丢弃**:显式 401 + JSON body。
- **"无签名头"与"签名错"不可区分**:两者都由 `_validate_signature` 返回 False
  (`:1141` 与各分支),走同一个 `:672-673`,body 都是 `{"error": "Invalid signature"}`。
  ✅ 无区分泄露。
- **日志区分**:`:1138-1140` 的"no signature header found"是 **debug** 级,
  `:669-671` 的"Invalid signature"是 **warning** 级。服务端能区分,客户端不能。设计合理。
- **时序侧信道**:五个分支都用 `_hmac_str_equal`(§1.2),比较本身常数时间。但**分支选择本身**
  是可观测的 —— Svix 分支要多做一次 base64 解码 + 时间戳解析,V1 分支最短。攻击者能通过响应时间
  推断"这条路由被哪个分支处理",这不泄漏密钥,只泄漏配置形状。低危。

### 4.2 真正的泄露面:未鉴权即可枚举路由状态

请求处理顺序(全部**早于**任何鉴权):

| 顺序 | 条件 | 响应 | 行号 |
|---|---|---|---|
| 1 | profile 前缀不认识 | 404 `Unknown or unconfigured profile` | `:594-597` |
| 2 | 路由名不存在 | 404 `Unknown route: <name>` | `:599-602` |
| 3 | profile 与路由绑定不符 | 404 `Unknown route: <name>`(**故意伪装**) | `:604-615` |
| 4 | 路由 `enabled: false` | 403 `Route disabled: <name>` | `:621-624` |
| 5 | body 超限 | 413 | `:628-632`、`:646-651` |
| 6 | 路由缺 secret | 403 `Webhook route is missing an HMAC secret` | `:658-666` |
| 7 | 签名错/缺 | 401 `Invalid signature` | `:667-674` |
| 8 | 限流 | 429 | `:676-681` |

第 3 步的伪装是**刻意**的,`gateway/platforms/webhook.py:611-616 @ 863e313`:

```python
            # Match the unknown-route response so callers cannot use profile
            # mismatches to enumerate route bindings.
            return web.json_response(
                {"error": f"Unknown route: {route_name}"}, status=404
            )
```

**但同一个文件对第 2/4/6 步没做任何伪装。**匿名攻击者 POST 一个空 body 就能区分:

- 404 → 路由不存在
- 403 `Route disabled` → 路由**存在**且被禁用(还回显路由名)
- 403 `missing an HMAC secret` → 路由**存在**且配置错误
- 401 → 路由存在、启用、密钥已配

**代码在"隐藏 profile 绑定"上很谨慎,在"隐藏路由存在性"上完全敞开。**这是同一函数内的
不一致取舍。考虑到动态订阅的路由名由 agent 生成、往往可猜(`github-pr`、`alerts` 之类),
枚举成本很低。

### 4.3 枚举探测不消耗任何配额

限流在**第 8 步**,即所有上述分支之后。这是刻意设计,
`tests/gateway/test_webhook_signature_rate_limit.py:63-72 @ 863e313`:

```python
    async def test_invalid_signature_does_not_consume_rate_limit(self):
        """Send requests with invalid signatures up to the rate limit, then
        send a valid-signed request and verify it succeeds.

        BEFORE FIX: Invalid signatures consume the rate limit bucket, so
        after 'rate_limit' bad requests the valid one would get 429.
        AFTER FIX: Invalid signatures are rejected with 401 first (before
        rate limiting), so the rate limit bucket is untouched. The valid
        request after many bad ones still succeeds.
        """
```

**取舍的另一面:攻击者的 404/403/401 探测同样不消耗配额,可以全速跑。**"坏签名不该饿死好请求"
与"坏签名不该免费探测"是一对矛盾,这里选了前者且没有为后者留任何补偿(没有独立的失败计数器/封禁)。
自建 harness 时值得为鉴权失败单独做一层更宽松但存在的限流。

### 4.4 `_reload_dynamic_routes()` 在鉴权之前

`gateway/platforms/webhook.py:585-590 @ 863e313`:

```python
        """POST /webhooks/{route_name} — receive and process a webhook event."""
        # Hot-reload dynamic subscriptions on each request (mtime-gated, cheap)
        self._reload_dynamic_routes()

        route_name = request.match_info.get("route_name", "")
        route_config = self._routes.get(route_name)
```

每个未鉴权请求都触发一次订阅文件的 mtime 检查。注释自称 "cheap",但它确实是一个
**匿名可触发的文件系统操作**,且不受限流保护(§4.3)。低危,记录备查。

---

## 5. 测试覆盖 vs 文档覆盖

### 5.1 测试文件清单

| 文件 | 与验签的关系 |
|---|---|
| `tests/gateway/test_webhook_adapter.py` | 主战场,`TestValidateSignature` 9 个用例 |
| `tests/gateway/test_webhook_integration.py` | GitHub 方言端到端(真起 aiohttp) |
| `tests/gateway/test_webhook_signature_rate_limit.py` | 401 早于 429 的顺序 |
| `tests/gateway/test_webhook_dynamic_routes.py` | 动态路由(含 secret 生成) |
| `tests/gateway/test_webhook_deliver_only.py` | 直投模式 |
| `tests/gateway/test_webhook_session_close.py` | 会话生命周期 |
| `tests/gateway/test_adapter_startup_secret_scope.py` | 启动期 secret 校验 |
| `tests/gateway/test_msgraph_webhook.py` | 另一个适配器(clientState,不是 HMAC) |
| `tests/gateway/test_whatsapp_cloud.py` | 另一份 `X-Hub-Signature-256` 实现 |
| `tests/gateway/test_telegram_webhook_secret.py` | Telegram secret token |
| `tests/gateway/test_cron_fire_webhook.py` | cron 触发,非验签 |

### 5.2 逐方言测试覆盖

```
$ for kw in "X-Hub-Signature-256" "X-Gitlab-Token" "X-Webhook-Signature-V2" \
            "X-Webhook-Timestamp" "svix-signature" "whsec_"; do
    echo "--- $kw ---"; grep -rniF -- "$kw" tests/ | sed 's/:.*//' | sort | uniq -c | sort -rn
  done
--- X-Hub-Signature-256 ---
      9 tests/gateway/test_whatsapp_cloud.py
      3 tests/gateway/test_webhook_signature_rate_limit.py
      3 tests/gateway/test_webhook_adapter.py
      2 tests/gateway/test_webhook_integration.py
--- X-Gitlab-Token ---
      2 tests/gateway/test_webhook_adapter.py
--- X-Webhook-Signature-V2 ---
      4 tests/gateway/test_webhook_adapter.py
--- X-Webhook-Timestamp ---
      3 tests/gateway/test_webhook_adapter.py
--- svix-signature ---
      2 tests/gateway/test_webhook_adapter.py
--- whsec_ ---
      3 tests/gateway/test_webhook_adapter.py
```

| 方言 | 正例(有效签名通过) | 反例 | 时间窗 | 文档 |
|---|---|---|---|---|
| Svix | ✅ `test_validate_svix_signature_raw_secret_valid`(`:264-279`) | ✅ 非 ASCII(`:158-168`) | ❌ **无超窗用例** | **零** |
| GitHub | ✅ 端到端 `tests/gateway/test_webhook_integration.py:113-126`(断言 202) | ✅ 非 ASCII(`:148-155`)、`sha256=invalid` → 401(`tests/gateway/test_webhook_signature_rate_limit.py:99-110`) | n/a | 有 |
| GitLab | ✅ 非 ASCII secret 仍匹配(`:170-176`) | ✅ 非 ASCII(`:148-155`) | n/a | 有 |
| 自有 V2 | ✅ 隐含于 `_generic_v2_signature` helper(`:107-110`) | ✅ 伪造 timestamp(`:196-213`)、✅ 剥离 timestamp 不降级(`:216-242`) | ✅ 伪造 timestamp 即验窗 | 英文有 / 中文无 |
| 自有 V1 | ✅ `test_v1_replay_attack_...`(`:257`) | ✅ 非 ASCII | n/a(明知无窗) | 英文有 / 中文弱 |
| —— | 无签名头 → False(`:134-138`) | | | 有 |

**测试侧唯二缺口**:
1. **Svix 超窗**:`whsec_` 分支(`gateway/platforms/webhook.py:1164-1170`)与 Svix 的 ±300s 拒绝(`:1160-1162`)
   都没有对应用例。测试 helper 支持 `whsec_`(`tests/gateway/test_webhook_adapter.py:115-119`)但没有任何
   测试真的传一个 `whsec_` 开头的 secret —— 三处命中里两处是 helper 分支、一处是 docstring。
   ```
   $ grep -n "whsec_" tests/gateway/test_webhook_adapter.py
   116:        base64.b64decode(secret.removeprefix("whsec_"))
   117:        if secret.startswith("whsec_")
   265:        """Raw shared secrets are accepted for Svix-style senders without whsec_ secrets."""
   ```
2. **多签名轮换**(`webhook.py:1182-1190`)没有"两条签名、第二条才对"的用例。

### 5.3 把 V1 的洞写成测试 —— 这是本仓库最好的一个做法

`tests/gateway/test_webhook_adapter.py:244-261 @ 863e313`:

```python
    def test_v1_replay_attack_succeeds_demonstrating_the_hole_v2_closes(self):
        """Regression/documentation test: a captured (body, signature) V1
        pair replays successfully no matter how much time has passed,
        because the V1 signature has no timestamp binding at all. This is
        the exact vulnerability V2 fixes — it is not asserting desired
        behavior, it is pinning the known, accepted-with-warning legacy
        gap so a future change to V1's semantics doesn't silently alter it
        without a deliberate decision."""
        adapter = _make_adapter()
        body = b'{"event": "push"}'
        secret = "generic-secret"
        sig = _generic_signature(body, secret)
        original_request = _mock_request(headers={"X-Webhook-Signature": sig})
        assert adapter._validate_signature(original_request, body, secret) is True
        # "Time passes" — nothing about a V1 signature depends on time, so
        # a captured pair replayed much later still validates.
        replayed_request = _mock_request(headers={"X-Webhook-Signature": sig})
        assert adapter._validate_signature(replayed_request, body, secret) is True
```

一个**断言漏洞仍然存在**的测试,自称 "not asserting desired behavior ... pinning the known,
accepted-with-warning legacy gap"。这是"让文档可执行"的极致形态:**接受的风险被写成会失败的守卫**。

配套的降级防护,`tests/gateway/test_webhook_adapter.py:216-242 @ 863e313`:

```python
    def test_validate_generic_v2_stripped_timestamp_does_not_downgrade_to_v1(self):
        """Regression test for a downgrade attack found in review: a sender
        migrating to V2 typically sends BOTH the V1 and V2 signatures
        together (for compatibility while both ends update). If an
        attacker captures one such mixed request and replays it with the
        X-Webhook-Timestamp header stripped, the presence of
        X-Webhook-Signature-V2 must still commit to V2 validation and
        reject — it must NOT silently fall through to validating the
        still-present, still-unprotected V1 signature instead. Falling
        through would let an attacker downgrade a V2-protected request
        back into the exact replay hole V2 exists to close, just by
        deleting one header from a captured request."""
```

### 5.4 实跑结果(行为规格已核)

```
$ HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
    "tests/gateway/test_webhook_adapter.py::TestValidateSignature"
=== Summary: 1 files, 9 tests passed, 0 failed (100% complete) in 2.4s (8 workers) ===

$ HERMES_PYTHON=... bash scripts/run_tests.sh \
    tests/gateway/test_webhook_signature_rate_limit.py tests/gateway/test_webhook_integration.py
=== Summary: 2 files, 5 tests passed, 0 failed (100% complete) in 2.9s (8 workers) ===

$ HERMES_PYTHON=... bash scripts/run_tests.sh tests/gateway/test_webhook_adapter.py
1 failed, 33 passed in 1.10s
FAILED tests/gateway/test_webhook_adapter.py::TestDualStackBind::test_default_bind_serves_both_families
E   AssertionError: IPv6 bind missing (the 6PN reachability bug) — got [('0.0.0.0', 44595)]
```

唯一失败是 `TestDualStackBind`,**容器无 IPv6 栈所致的环境失败**,与验签无关(R7B B-20 讨论的
双栈绑定)。验签相关用例 100% 通过。

### 5.5 覆盖对比:这是 R7B "让文档可执行" 规律的又一例证

| 方言 | 代码行 | 测试用例 | 用户文档行(英) | 用户文档行(中) |
|---|---|---|---|---|
| Svix | 17 + 49 = 66 | 2 | **0** | **0** |
| GitHub | 7 | 4 | 1 | 1 |
| GitLab | 4 | 2 | 1 | 1 |
| 自有 V2 | 42 | 3 | 1 | **0** |
| 自有 V1 | 23 | 2 | 1 | 1(且描述错位) |

commit 级证据链更狠:

| commit | 日期 | 作者 | 代码 | 测试 | 文档 |
|---|---|---|---|---|---|
| `bbf02c322` `fix(gateway): validate Svix webhook signatures (#30200)` | 2026-05-24 | BaxBit(外部) | +85 | **+181** | **0** |
| `70449a493` `fix(security): add timestamp-bound V2 signature ...` | 2026-07-04 | MorAlekss(外部) | +41 | **+111** | **0** |
| `708b57e00` `fix(webhook): rate-limit V1 deprecation warning + document V2 signature` | 2026-07-04 | teknium1(维护者) | +22/-8 | 0 | **+3/-1** |
| `d577408f3` `fix(webhook): reject generic V2 signature missing timestamp ...` | 2026-07-04 | MorAlekss | +25 | **+28** | **0** |
| `1b69c47e9` `fix(webhook): reject a non-ASCII signature header ...` | 2026-07-16 | (外部) | — | +regression | **0** |

规律清清楚楚:

> **外部贡献者的验签 PR 从不带文档,但每一次都带大量测试(181 / 111 / 28 行);
> 文档只在维护者亲自跟进的那一次被补上(#58461 的 follow-up,2 小时后,+3 行)。**

Svix 那次(比 V2 早 7 周)没有等到任何一个维护者的 follow-up,于是这个能力**永久隐形**。
V2 那次幸运地在 2 小时内被 teknium1 顺手补了英文,但**中文镜像永远没跟上**(§2.4)。

**这与 R7B 在 relay 上的观察互为正反面**:relay 有
`tests/gateway/relay/test_contract_doc_conformance.py` 强制代码-文档一致,所以它是全仓文档一致性
最好的一簇;webhook 验签有**优秀的测试**却**没有一条测试把文档纳入断言**,于是测试越写越全、
文档越落越远。**测试覆盖率与文档覆盖率是两个独立指标,前者高不代表后者高 —— 除非把文档写进断言。**

---

## 6. 定案建议

### C-01 ◇(代码有、文档无)—— Svix 方言完全无文档 **[确认 R7B B-19,但收窄]**

- **事实**:`gateway/platforms/webhook.py:1039-1055`、`:1143-1191 @ 863e313` 实现完整的
  Svix 兼容验签(含 `whsec_` base64 密钥、±300s 窗口、轮换期多签名);
  全仓 `.md` 与整个 `website/` 对 `svix` / `whsec_` 命中数为 **0**(§2.1)。
- **判定**:**◇**。
- **对 R7B B-19 的修正**:B-19 原文是"五种签名方言……在 `website/docs/**` 无完整枚举"。
  独立复核后,准确表述应为:**五种里只有 Svix 一种无文档,其余四种在英文文档中记载准确完整
  (含 ±300s 窗口、V1 废弃与重放说明,共 7 条断言全部与代码一致,§2.3)。**
  R7B 的措辞会让读者以为整簇缺文档,实际影响面小得多但更尖锐 —— 是**一种具体能力的完全隐形**。
- **运营影响**:高。决定"我的 AgentMail / Resend / Clerk 能不能直接接"的答案,
  官方文档给的是错误的"不能"。

### C-02 ▲(文档与代码冲突)—— zh-Hans 镜像把废弃的 V1 讲成唯一通用方案 **[R7B 未记]**

- **事实**:`website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/user-guide/messaging/webhooks.md:452-460 @ 863e313` 只列三种方言,
  通用一栏写的是 `X-Webhook-Signature`(即代码里已废弃、有重放洞、命中即打 warning 的 V1),
  V2 整段缺失;英文同段(`website/docs/user-guide/messaging/webhooks.md:453-462`)在 2026-07-04
  由 `708b57e00` 补齐,中文镜像 2026-07-08 被动过(`aabfedcac` #60983)却没带上。
- **判定**:**▲**,不是 ◇。文档不是"没写",是"写了并且指向了错误的方案"。
- **放大因素**:没有任何自动化拦截 —— `tests/agent/test_i18n.py` 只管 `locales/*.yaml`,
  不覆盖 `website/i18n/`(§2.4)。

### C-03 ▲(文档与代码冲突)—— 响应码表漏两条 403 **[R7B 未记]**

- **事实**:`website/docs/user-guide/messaging/webhooks.md:377-388 @ 863e313` 的 Response codes
  表列了 200/200-dup/401/400/404/413/429/502,**无 403**;代码有
  `:621-624`(路由禁用)与 `:658-666`(路由缺 secret)两条 403。中英双语同缺。
- **判定**:**▲**(自称穷举的表格以遗漏方式与代码冲突)。

### C-04 ◇ —— `svix-id` 作为第三个幂等键未文档化

- **事实**:`gateway/platforms/webhook.py:793-800 @ 863e313` 的 `delivery_id` 三级回退是
  `X-GitHub-Delivery` → `svix-id` → `X-Request-ID`;文档 `webhooks.md:395` 只说前后两个。
- **判定**:**◇**(是 C-01 的连带,可并入)。

### C-05 观察(不计 ▲/◇)—— 未鉴权路由状态枚举面

- §4.2:同一函数内,profile 绑定被刻意伪装成 404(`:610-615` 有注释说明),
  但路由存在性 / 禁用状态 / 缺 secret 状态**未做任何伪装**,匿名 POST 即可区分;
  且这些分支全部**早于限流**(§4.3),探测不消耗配额。
- 不作为文档冲突记,作为**设计取舍观察**进底稿与成品章。

---

## 7. issue / commit 溯源

### 7.1 代码注释里的 issue 编号

```
$ grep -n "#[0-9]\{4,6\}" gateway/platforms/webhook.py
183:                    # interactive acknowledgement that abandons the task (#57056).
```

**`webhook.py` 全文只有一个 issue 编号,且与验签无关。**`#57056` 讲的是 webhook 路由无人值守时
自动恢复回合不应发交互式确认(`gateway/platforms/webhook.py:180-185 @ 863e313`):

```python
    # No human is present to answer a "session restored — what next?" prompt:
    # webhook runs are event-triggered.  The startup auto-resume turn must
    # instruct the model to FINISH the interrupted work instead of emitting an
    # interactive acknowledgement that abandons the task (#57056).
    interactive_resume: bool = False
```

验签相关的因果经过必须从 commit 历史取,见下。

### 7.2 PR #30200 —— Svix 支持的来源

- **溯源点 1**:`scripts/release.py:1985 @ 863e313`
  ```python
    "baxter@bitreserve.ai": "BaxBit",  # PR #30200 (Svix webhook signature validation)
  ```
- **溯源点 2**:commit `bbf02c322443b7e833d730bbfa1dbd5d246e71e2`,2026-05-24,
  `fix(gateway): validate Svix webhook signatures (#30200)`,作者 BaxBit。
- **改动**:`gateway/platforms/webhook.py` +85,`tests/gateway/test_webhook_adapter.py` +181,
  **文档 0 行**。
- **因果**:外部贡献者(用 AgentMail 的用户)发现 Hermes 收不了 Svix 投递的 webhook →
  加分支 + 大量测试 → 合入 → 从此代码支持而文档不知情。**doc gap 诞生于此。**

### 7.3 #58461 —— V2 时间戳绑定的三连击(2026-07-04 一天之内)

1. `70449a493` 12:11 `fix(security): add timestamp-bound V2 signature for generic webhook replay
   protection`(MorAlekss)。代码 +41,测试 +111,文档 0。
   **因果**:V1 只签 body,抓一次包就能无限重放 → 引入 V2,把 `<timestamp>.<body>` 一起签,
   窗口 300 秒。
2. `708b57e00` 14:17 `fix(webhook): rate-limit V1 deprecation warning + document V2 signature`
   (teknium1,维护者)。commit 正文:
   ```
   - warn once per route instead of on every request (busy senders would
     spam the log)
   - document X-Webhook-Signature-V2 / X-Webhook-Timestamp in the webhooks
     user guide

   Follow-ups for salvaged #58461.
   ```
   **因果**:(a) V1 警告原本每请求一次,一个繁忙上游会刷爆日志 → 改成每路由一次,
   落成 `webhook.py:200-202` 的 `_v1_signature_warned` 集合;(b) 顺手把 V2 写进用户文档(+3 行)。
   **这是全链条里唯一一次文档被更新。**
3. `d577408f3` 16:40 `fix(webhook): reject generic V2 signature missing timestamp instead of
   falling back to V1`(MorAlekss)。代码 +25,测试 +28,文档 0。
   **因果(review 中发现的降级攻击)**:迁移期的发送方通常**同时**发 V1 和 V2 两个签名头;
   原实现里 V2 校验嵌在 V1 分支内/之后,一旦 timestamp 缺失就会掉到 V1 分支。攻击者抓一个
   混发请求 → **只删掉 `X-Webhook-Timestamp` 一个头** → 仍然存在的 V1 签名照样验过 →
   V2 想堵的重放洞被一键还原。修法:`X-Webhook-Signature-V2` 一出现就**锁定** V2 模式,
   缺 timestamp / 非整数 / 超窗一律 return False(`webhook.py:1086-1106`),绝不回退。
   注释固化在 `:1076-1085`,回归测试固化在 `tests/gateway/test_webhook_adapter.py:216-242`。

`#58461` 在仓库源码与文档中**无任何其他引用**:
```
$ grep -rn "58461" --include="*.py" --include="*.md" .
(仅 commit message,无源码/文档引用)
```

### 7.4 `1b69c47e9` —— 非 ASCII 签名头把 401 变成 500(2026-07-16)

commit 正文(完整因果,值得整段引用):

```
_validate_signature backs the public webhook receiver. It compared each
attacker-supplied signature/token header (GitHub X-Hub-Signature-256,
GitLab X-Gitlab-Token, generic X-Webhook-Signature / -V2, and the Svix v1
header) against a computed hex/base64 digest with hmac.compare_digest on
two str values. compare_digest raises TypeError on a str containing
non-ASCII characters, and the header is raw client input on an
unauthenticated endpoint — so any internet client could POST a single
non-ASCII byte in the signature header and raise out of the handler,
returning a 500 instead of a clean 401. Fail-closed, but an on-demand
crash of the request path.

Route all five comparisons through a small _hmac_str_equal() helper that
encodes both sides to UTF-8 bytes before the constant-time compare
(compare_digest has no ASCII restriction on bytes). Semantics are
unchanged for valid signatures; a hostile non-ASCII header now fails
closed with a rejection instead of raising.
```

**什么输入**:`X-Hub-Signature-256: ské-not-a-valid-signature`(任何含非 ASCII 字节的签名头)。
**什么现象**:HTTP 500 而非 401,请求处理路径抛出。
**为什么**:`hmac.compare_digest(str, str)` 在 `str` 含非 ASCII 时抛 `TypeError`;
而这个 `str` 是公网未鉴权端点上的原始客户端输入。
**怎么修**:统一走 `_hmac_str_equal`(`webhook.py:158-169`),两边先 `.encode()` 成 bytes 再比,
`compare_digest` 对 bytes 无 ASCII 限制,常数时间保证不变。
**回归测试**:`tests/gateway/test_webhook_adapter.py:140-155`(GitHub/GitLab/generic 三个头)
与 `:158-168`(Svix)与 `:170-176`(非 ASCII secret 仍要能匹配)。

这条 commit 也是 §1.0 里"五方言"口径的原始出处。

---

## 8. 与本轮其他底稿的接口

- 本文只覆盖**通用 webhook 适配器**的验签。同仓另有三套独立的入站鉴权:
  `whatsapp_cloud._verify_signature`(`gateway/platforms/whatsapp_cloud.py:1525-1548`,
  第二份 `X-Hub-Signature-256` 实现,§1.4)、`msgraph_webhook`(clientState 比对,非 HMAC)、
  Telegram secret token(`TELEGRAM_WEBHOOK_SECRET`,有 GHSA-3vpc-7q5r-276h 强制)。
  若成品章要回答"能接哪些平台",需把这四套一起画。
- `webhook_filters.py` 经复核与验签无关(§1.11),归 R7B 已定的结构级理解层即可。
- C-05 的枚举面与 R7B B-16(一个端口三种鉴权)同源,建议在成品章合并成一节
  "**未鉴权表面**:谁在鉴权之前就能问到答案"。
