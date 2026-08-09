# R9B 底稿 · 主线定案

本文件是 R9B **主线**(非子代理)独立取证的定案。子代理各簇的定案在各自
`notes/r9b-raw-*.md` 的定案节。全部锚点针对基线 `863e313`。

---

## 1. H-R9A-d 结清:凭据获取侧有主机允许清单,凭据**使用**侧没有

**移交项原文(R9A §11)**:`tools/skills_sync_client.py:318` 的 `resolve_sync_base_url`
——「同步端点只做 `strip()`,无 scheme 校验无主机白名单,而其上挂 Nous JWT bearer;
走 `requests` 故 `urlopen` 普查抓不到」。

**结论:现象属实,但移交项给的定位与严重性都要修正。** 分三段说。

### 1.1 定位修正:函数在 `:307`,不在 `:318`

`:318` 是函数体第一行(`env = os.getenv(...)`),函数头在 `:307`。

`tools/skills_sync_client.py:307-320 @ 863e313`

```python
def resolve_sync_base_url() -> Optional[str]:
    """Resolve the sync-plane base URL.

    Order: HERMES_SYNC_BASE_URL env bridge -> config.yaml ``sync.base_url`` ->
    the production plane. Returns a base without a trailing slash (e.g.
    ``https://host``); the ``/v1/sync/`` prefix is appended by the client.

    The production default means a normal user never configures a URL — the
    env var and config key exist to point a dev/staging build at another
    plane. Returns None only if the default is somehow blanked out.
    """
    env = os.getenv("HERMES_SYNC_BASE_URL")
    if env and env.strip():
        return env.strip().rstrip("/")
```

**取值链**:`HERMES_SYNC_BASE_URL` 环境变量 → `config.yaml` 的 `sync.base_url`
→ 常量默认 `DEFAULT_SYNC_BASE_URL`。三条路径都只做 `.strip().rstrip("/")`,
**没有 scheme 校验,没有主机允许清单**。

*(这条定位错误本身就是 H-R9A-h 要解决的形态:移交表格行内的锚点从不被校验。
R9B 把表格锚点纳入机械校验后,`:318` 因落在 `resolve_sync_base_url` 函数体内
而被「格子指外层构造」这条豁免放过——所以它不是**漂移**,是**不够精确**。
下面一律用 `:307`。)*

### 1.2 bearer 是会话级头,挂在**每一个**发往该 base 的请求上

`tools/skills_sync_client.py:771-778 @ 863e313`

```python
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 30.0):
        self.base = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        import requests  # core dependency

        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {api_key}"
```

`api_key` 来自 `resolve_identity()`,它转调
`hermes_cli.auth.resolve_nous_runtime_credentials()` 取**真实 Nous JWT**:

`tools/skills_sync_client.py:246-247 @ 863e313`

```python
def resolve_identity() -> Dict[str, Any]:
    """Resolve the Nous bearer + owner + dev-gate flag.
```

因为设在 `Session.headers` 上,**该 base 下的每个请求都会带上它** ——
包括这个作者自己注明"无需鉴权"的端点:

`tools/skills_sync_client.py:785-787 @ 863e313`

```python
    def capabilities(self) -> Dict[str, Any]:
        """GET /v1/sync/capabilities (sync contract). No auth required."""
        r = self._session.get(self._url("capabilities"), timeout=self.timeout)
```

**即"不需要 token 的探测请求也会把 token 送出去"**:一个被改过 base 的实例,
连握手那一下就已经泄了。

`requests` 的用法也印证了移交项的另一半:该文件用 `requests.Session`(`:775`),
所以 R8D 的 `urlopen` 普查确实抓不到它。

### 1.3 严重性修正:同一仓库对**同一个 bearer** 已有这道防线,只是没装在这一侧

这是本条最有价值的部分。`hermes_cli/auth.py` 对**取 token 的那一端**(portal)
装了主机允许清单 + scheme 校验,而且注释把威胁模型写得一字不差:

`hermes_cli/auth.py:6238-6241 @ 863e313`

```python
            # A persisted/stale portal_base_url is where the refresh token gets
            # POSTed on refresh — reject any host outside the allowlist so a
            # poisoned value can't exfiltrate the bearer, healing to the default.
            # Trusted operator env overrides bypass this network-value gate.
```

允许清单本体:

`hermes_cli/auth.py:2235-2239 @ 863e313`

```python
_NOUS_PORTAL_ALLOWED_HOSTS: FrozenSet[str] = frozenset({
    "portal.nousresearch.com",
    "localhost",
    "127.0.0.1",
})
```

执行处(主机不在清单、或 scheme 不可信,就**回落到默认值**而不是照用):

`hermes_cli/auth.py:6255-6266 @ 863e313`

```python
                if (
                    not portal_host
                    or portal_host not in _NOUS_PORTAL_ALLOWED_HOSTS
                    or not trusted_scheme
                ):
                    logger.warning(
                        "auth: ignoring invalid portal_base_url %r "
                        "(host %r or scheme not allowed), using default",
                        portal_url,
                        portal_host,
                    )
                    portal_url = DEFAULT_NOUS_PORTAL_URL
```

**所以这不是"作者没想到主机允许清单",而是"想到了、写了、只装在了取凭据那一端"。**
`skills_sync_client.py` 里连一处 scheme/host 校验都没有:

```verify
cd /home/user/hermes-agent && grep -n "urlparse\|urlsplit\|scheme\|allowlist\|whitelist" tools/skills_sync_client.py
```

上面这条命令在基线上**只有 1 行输出**(`:207` 的一句注释,讲的是
`resolve_nous_runtime_credentials()` 自己遵守 portal 允许清单),
**没有任何一处是本文件对 base_url 做的校验**。作为对照,同目录的
`tools/skills_hub.py` 有 `_guarded_http_get`(`tools/skills_hub.py:302`)
和整个 `tools/skills_guard.py` 模块。

### 1.4 但它今天**不是**一条可远程利用的路径 —— 这一半移交项说过头了

要让 bearer 发给攻击者,得先能写 `HERMES_SYNC_BASE_URL` 或 `config.yaml` 的
`sync.base_url`。**全仓没有任何代码写 `sync.base_url`。** 搜索面如下:

```verify
cd /home/user/hermes-agent && grep -rn "sync\.base_url\|\"sync\"\]\[\|'sync'\]\[" --include=*.py . | grep -v "^./tests/"
```

命中只有 `hermes_cli/main.py` 的两处,**都是提示用户"没配"的错误文案**,不是写入:

`hermes_cli/main.py:4713-4718 @ 863e313`

```python
            )
        elif not status.get("base_url"):
            print(
                "\nNo sync base URL configured (config.yaml sync.base_url or "
                "HERMES_SYNC_BASE_URL). Sync is inert.",
                file=sys.stderr,
```
`sync` 段也不在 `DEFAULT_CONFIG` 里(搜索面:`hermes_cli/config_defaults.py`
全文搜 `"sync"`,唯一命中是 `:800` 的 `"stream_processing_mode": "async",  # "sync" or "async"`,
是注释里的词,不是配置段)。

**所以现状是**:`sync.base_url` 只有操作者手改 `config.yaml` 或设环境变量能给值。
这与 auth.py 那道防线所防的东西**不同型**——那道防线明确防的是
「**网络来的**值被持久化进 `auth.json`」(`:6238` 注释原文
"A persisted/stale portal_base_url"、`:2340-2342` 另有一段说它
"exists to reject an untrusted NETWORK-provided value")。

**定案:■(潜在的不对称防御),不是"可利用的凭据外泄"。**
把它记成后者会是一条正结论级别的夸大。

**未验证、留给后续轮的那一半**:若存在**任意写 config.yaml** 的远程路径,
这条就立刻升级为真实外泄。已知候选是 R8C 记的 dashboard `/api/ops/import`
(`reports/round-8c-dashboard-and-web.md` 的 H-R8C-f:backup 打包整个 HERMES_HOME、
import 覆盖凭据与配置,来源校验仅"zip 里出现过某个 basename")。
**本轮没有重跑那条路径**,不据此下结论;作为移交项交出去(见 §3)。

### 1.5 可迁移的设计教训

> 一个防线的价值 = 它覆盖了该资产的**几条**出口,而不是它写得多严。
> 这里 bearer 有两条出口——**取**(portal refresh)与**用**(sync plane)——
> 允许清单只装在取的那条。审计凭据时应当先枚举「这个 secret 会被送到哪几个由配置决定的
> 目的地」,再逐条问「这个目的地由谁决定、有没有校验」,
> 而不是逐个文件读过去看有没有 `urlparse`。

---

## 2. 台账口径:本轮 46 个文件全部由 R1-inventoried 转 R9B-deep-read

见报告 §台账报数。
