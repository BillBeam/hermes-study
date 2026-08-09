# r9d-90 · 移交项取证 D —— H-R9C-a(portal base url 不查白名单)+ H-R9C-b(secrets_cli 落盘侧)

> 本文是**移交项定案所需的取证底稿**,不是覆盖轮次的机制笔记。
> 溯源约定:凡对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` 单独成行、置于代码块之前。
> **本文涉及的 `hermes_cli/nous_billing.py`、`hermes_cli/auth.py`、`hermes_cli/secrets_cli.py`、
> `hermes_cli/config.py` 都不在 R9D 的 49 文件范围内**(`agent/file_safety.py` 在),
> 所以本文**不改台账分层**,只为主线提供足以对 H-R9C-a / H-R9C-b 定案的证据。

## 0. 基线状态自检

```verify
git -C /home/user/hermes-agent status --porcelain    # 输出为空
git -C /home/user/hermes-agent rev-parse HEAD        # 863e31318553cda8ad61df681d08175364d4164b
```

实跑结果:`status --porcelain` **输出为空**,`HEAD` = `863e31318553cda8ad61df681d08175364d4164b`。
本轮全部实验都在 `/tmp` 的临时 HERMES_HOME 与本地回环端口上进行,未写入基线一个字节。

---

# 一、H-R9C-a —— `resolve_portal_base_url` 不查主机白名单

## 1.1 原移交项复述

R9C 移交表原文(`reports/round-9c-external-interfaces.md` 第 410 行,**下框内是移交表转录,
不是基线源码**):

```text
锚点:hermes_cli/nous_billing.py:179 的 resolve_portal_base_url
现象:读环境变量与存储的 portal_base_url 时不查 _NOUS_PORTAL_ALLOWED_HOSTS,
      而返回值在 :399-402 被用作 Authorization: Bearer 的目的地;
      同仓库 hermes_cli/auth.py:5900 读同一存储字段时是查清单的。
      文件不在 R9C 的 47 个内,故未定案。
```

## 1.2 锚点核对(三个锚点全部核到当前准确行号)

| 移交项给的锚点 | 核对结果 | 当前准确锚点(声明式) |
|---|---|---|
| `nous_billing.py:179` 的 `resolve_portal_base_url` | **指向函数体首行,不是函数头**。`def` 在 `:173`,`:179` 是读环境变量那一行 | 函数头 `hermes_cli/nous_billing.py:173`:`def resolve_portal_base_url(state: Optional[dict[str, Any]] = None) -> str:`;环境变量行 `hermes_cli/nous_billing.py:179`:`env = os.getenv("HERMES_PORTAL_BASE_URL") or os.getenv("NOUS_PORTAL_BASE_URL")` |
| `nous_billing.py:399-402` | **准确**。`:399` 拼 URL,`:401` 拼 Bearer 头 | `hermes_cli/nous_billing.py:399`:`url = f"{base}{path}"`;`hermes_cli/nous_billing.py:401`:`"Authorization": f"Bearer {token}",` |
| `auth.py:5900` | **准确**,就是白名单判定那一行 | `hermes_cli/auth.py:5900`:`if parsed_portal_url.hostname and parsed_portal_url.hostname not in _NOUS_PORTAL_ALLOWED_HOSTS:` |

被质疑的函数全文:

`hermes_cli/nous_billing.py:173 @ 863e313`

```python
def resolve_portal_base_url(state: Optional[dict[str, Any]] = None) -> str:
    """Resolve the portal base URL with login-time precedence.

    ``HERMES_PORTAL_BASE_URL`` → ``NOUS_PORTAL_BASE_URL`` → stored auth-state
    ``portal_base_url`` → registry default. Trailing slash stripped.
    """
    env = os.getenv("HERMES_PORTAL_BASE_URL") or os.getenv("NOUS_PORTAL_BASE_URL")
    if env and env.strip():
        return env.strip().rstrip("/")
    if state:
        stored = state.get("portal_base_url")
        if isinstance(stored, str) and stored.strip():
            return stored.strip().rstrip("/")
    return DEFAULT_PORTAL_BASE_URL
```

返回值怎么变成 Bearer 的目的地(`_request` 内):

`hermes_cli/nous_billing.py:399 @ 863e313`

```python
    url = f"{base}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
```

`base` 从哪来(同文件 `_resolve_token_and_base`):

`hermes_cli/nous_billing.py:271 @ 863e313`

```python
    base = resolve_portal_base_url(state)
```

## 1.3 `_NOUS_PORTAL_ALLOWED_HOSTS` 是什么、谁定义、还有谁查它

**定义**(唯一定义处):

`hermes_cli/auth.py:2232 @ 863e313`

```python
# Allowlist of valid Nous Portal hosts. A portal_base_url outside this
# set is treated as a misconfiguration and falls back to the default.
# "localhost" / "127.0.0.1" are valid for local development and testing.
_NOUS_PORTAL_ALLOWED_HOSTS: FrozenSet[str] = frozenset({
    "portal.nousresearch.com",
    "localhost",
    "127.0.0.1",
})
```

**搜索面(负结论的成本条款)。** 我在基线仓库根执行:

```verify
cd /home/user/hermes-agent && grep -rn "_NOUS_PORTAL_ALLOWED_HOSTS" \
    --include=*.py --include=*.ts --include=*.tsx --include=*.md .
```

命中 **6 处,无其它文件**:`hermes_cli/auth.py` 的 `:2235`(定义)、`:2340`(文档字符串引用)、
`:5900`(判定)、`:6257`(判定),以及 `tests/hermes_cli/test_nous_portal_staging_allowlist.py`
的 `:36`(import)、`:50` / `:55`(断言)。**排除项**:`node_modules`、二进制、`.pyc`
未参与匹配(grep 默认按文本扫,`--include` 限定了扩展名);另用不带 `--include` 的同一模式复扫
`agent/`、`gateway/`、`tools/`、`providers/`、`apps/`,零命中。
所以**全仓只有 `hermes_cli/auth.py` 这一个模块查这张清单**,`nous_billing.py` 连 import 都没有。
该模块的模块级注释还专门解释了它为什么不 import `auth`:

`hermes_cli/nous_billing.py:41 @ 863e313`

```python
# Scope the privileged billing endpoints require. Mirrored from
# hermes_cli.auth.NOUS_BILLING_MANAGE_SCOPE (kept here too so this module has no
# import-time dependency on the much heavier auth module).
BILLING_MANAGE_SCOPE = "billing:manage"
```

**两个查它的地方各自在做什么。**

`hermes_cli/auth.py:5893 @ 863e313`

```python
        else:
            portal_base_url = (
                _optional_base_url(state.get("portal_base_url"))
                or DEFAULT_NOUS_PORTAL_URL
            ).rstrip("/")

            parsed_portal_url = urlparse(portal_base_url)
            if parsed_portal_url.hostname and parsed_portal_url.hostname not in _NOUS_PORTAL_ALLOWED_HOSTS:
                logger.warning(
                    "auth: ignoring invalid portal_base_url %r (host %r not in allowlist), using default",
                    portal_base_url, parsed_portal_url.hostname,
                )
                portal_base_url = DEFAULT_NOUS_PORTAL_URL
```

第二处(`_resolve_effective_routing_metadata`)把**理由**写得最清楚:

`hermes_cli/auth.py:6238 @ 863e313`

```python
            # A persisted/stale portal_base_url is where the refresh token gets
            # POSTed on refresh — reject any host outside the allowlist so a
            # poisoned value can't exfiltrate the bearer, healing to the default.
            # Trusted operator env overrides bypass this network-value gate.
```

**关键分工(这条决定了移交项该怎么判):环境变量分支不查清单,是本仓库**明文写下的设计**,
不是疏漏。**

`hermes_cli/auth.py:2337 @ 863e313`

```python
    ``HERMES_PORTAL_BASE_URL=https://portal.staging-nousresearch.com`` into
    the container env). The env source is trusted (the OS user/deployment
    set it themselves), so — like the inference override — it must NOT be
    gated by ``_NOUS_PORTAL_ALLOWED_HOSTS``: that allowlist exists to reject
    an untrusted NETWORK-provided value (a poisoned portal_base_url
    persisted to auth.json), not a value the operator explicitly configured.
```

而且这是一次**真实事故**的修复:回归测试文件 `tests/hermes_cli/test_nous_portal_staging_allowlist.py`
的模块 docstring 记录,2026-07 一台由 nous-account-service 在 staging 环境开出来的托管 agent,
容器 env 里被打了 `HERMES_PORTAL_BASE_URL=https://portal.staging-nousresearch.com`,
而旧代码先读 state 再读 env、且一律过白名单,于是 staging 的 refresh token 被重放到**生产**
token 端点,生产返回 `invalid_grant` → 触发 `_quarantine_nous_oauth_state` → **整个凭据池被清空**。

> `tests/hermes_cli/test_nous_portal_staging_allowlist.py:19 @ 863e313`
>
> Prod correctly rejected that with ``invalid_grant``, which triggered
> ``_quarantine_nous_oauth_state`` and wiped the entire credential pool.

**结论(第 2 问):** 移交项里"读环境变量时不查清单"这半句,**不是缺陷**——它与
`auth.py` 的既定策略一致(即上面那段 `_nous_portal_env_override` docstring),并且有专门的回归测试
(`tests/hermes_cli/test_nous_portal_staging_allowlist.py::TestPortalEnvOverrideHelper::test_env_override_not_gated_by_allowlist`)。
真正的差异只剩下**存储字段那半句**。

## 1.4 可达性判定:`portal_base_url` 这个存储字段是谁写的

这一问决定 ■ 还是"设计缺口"。R9C 的判法是:**用户在向导里亲手填的地址不算 ■**。

**搜索面。** 我在基线仓库根执行:

```verify
cd /home/user/hermes-agent && grep -rn "portal_base_url" --include=*.py . | grep -v "^./tests/"
```

得到 **130 处**(不含 `tests/`),另用 `--include=*.ts --include=*.tsx --include=*.js` 扫前端,
命中 11 处、全部在 `apps/desktop/electron/main.ts` 与 `ui-tui/`,且都是**读**。
我逐一看了这 130 处中**所有写进会被持久化的 dict 的赋值**,写入面只有下面五类:

| # | 写入点(声明式锚点) | 值的来源 | 是否过白名单 |
|---|---|---|---|
| 1 | `hermes_cli/auth.py:8796` 的 `_nous_device_code_login` | 函数参数 → `--portal-url` 命令行标志 → env → 注册表默认值 | 否(操作者来源,按设计不该过) |
| 2 | `hermes_cli/auth.py:8880`:`"portal_base_url": portal_base_url,` | 同上,登录成功后落 auth.json | 否(同上) |
| 3 | `hermes_cli/auth.py:5982`:`state["portal_base_url"] = portal_base_url` | **已过白名单**的那个变量(`:5893-5905`) | **是** |
| 4 | `hermes_cli/auth.py:6482`:`state["portal_base_url"] = portal_base_url`(`_resolve_effective_routing_metadata` 的回写) | **已过白名单**(见上面 1.3 引的 `:6238` 注释块) | **是** |
| 5 | `hermes_cli/auth.py:5352`:`"portal_base_url",` (`_merge_shared_nous_oauth_state` 的键列表) | 跨 profile 的**本地共享文件**,该文件由 `_write_shared_nous_state` 写,值取自上面已净化的 state | 间接是 |

`--portal-url` 这个标志的四个注册点(搜索面:`grep -rn '"--portal-url"' --include=*.py .`,
命中 4 处,无其它)——**全部是操作者手输**:

| 注册点(声明式锚点) | 归属命令 |
|---|---|
| `hermes_cli/subcommands/login.py:49`:`"--portal-url", help="Portal base URL (default: production portal)"` | `hermes login` |
| `hermes_cli/subcommands/auth.py:34`:`auth_add.add_argument("--portal-url", help="Nous portal base URL")` | `hermes auth add` |
| `hermes_cli/subcommands/model.py:28`:`"--portal-url",` | `hermes model`(Nous 登录) |
| `hermes_cli/subcommands/dashboard.py:204`:`"--portal-url",` | `hermes dashboard register` |

**关键对照:同一个登录响应里,`inference_base_url` 是可以被服务端改写的,`portal_base_url` 不能。**

`hermes_cli/auth.py:8872 @ 863e313`

```python
    resolved_inference_url = (
        _optional_base_url(token_data.get("inference_base_url"))
        or requested_inference_url
    )
    if resolved_inference_url != requested_inference_url:
        print(f"Using portal-provided inference URL: {resolved_inference_url}")
```

`token_data` 是 Portal 的 token 响应体,所以 `inference_base_url` **确有网络来源**——
这也是 `_validate_nous_inference_url_from_network` 这个"网络来源专用校验器"存在的原因。
而紧挨着它的那句写 `portal_base_url`(上表第 2 行)用的是 `portal_base_url` 局部变量,
**没有读 `token_data`**。

**负结论(带搜索面):在本基线里,不存在任何把网络响应体的值写进 `portal_base_url` 的代码路径。**
搜索面 = 上面那 130 处非测试 `portal_base_url` 命中的逐条阅读 + 对 `_save_provider_state` /
`_save_provider_state_to_source` / `set_provider_auth_state` 全部调用方的复核
(`grep -rn "save_provider_state\|set_provider_auth_state" --include=*.py . | grep -v "^./tests/"`,
命中 24 处,已逐条看过 `state` 的构造来源)。**排除项**:`tests/` 下的 fixture(它们直接构造
带任意 host 的 auth.json,是测试意图,不是产品路径);桌面端只读 env、连 stored 都不读——

`apps/desktop/electron/main.ts:6489 @ 863e313`

```typescript
function resolvePortalBaseUrl() {
  const raw = process.env.HERMES_PORTAL_BASE_URL || process.env.NOUS_PORTAL_BASE_URL || DEFAULT_NOUS_PORTAL_URL

  return String(raw).trim().replace(/\/+$/, '')
}
```

**所以:要让一个恶意 host 进入 `state["portal_base_url"]`,攻击者必须能写
`~/.hermes/auth.json` 或跨 profile 共享存储——那是本地文件写权限,已经越过了这条防线要防的边界。**
上面 1.3 引的那段 "poisoned value can't exfiltrate the bearer" 注释,把这个字段当成
"网络来源、可能被投毒"来防,属于**纵深防御**,不代表本基线里真有那条投毒路径。

**第 3 问结论:** 存储字段 `portal_base_url` 在本基线内**只有操作者来源**(命令行 `--portal-url` /
env / 默认值 / 本地共享文件)。按 R9C"用户亲手填的地址不算 ■"的判法,
**"`nous_billing` 不查白名单"这件事本身,不构成 ■,是设计缺口(纵深防御不对齐)。**

## 1.5 第 4 问:HTTP 客户端与重定向——**这里才是 ■**

`nous_billing._request` 用的是**裸 `urllib.request.urlopen`**,不是仓库自己的
`open_credentialed_url`:

`hermes_cli/nous_billing.py:410 @ 863e313`

```python
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
```

**搜索面**:`grep -rn "open_credentialed_url" --include=*.py .` 命中 16 处(其中 5 处在
`tests/`、2 处是 `hermes_cli/urllib_security.py` 自身的定义与 `__all__`),产品侧**调用方只有 4 个**:

| 产品侧调用方(声明式锚点) |
|---|
| `providers/base.py:218`:`from hermes_cli.urllib_security import open_credentialed_url` |
| `hermes_cli/azure_detect.py:49`:`from hermes_cli.urllib_security import open_credentialed_url` |
| `hermes_cli/models.py:25`:`from hermes_cli.urllib_security import open_credentialed_url` |
| `plugins/model-providers/anthropic/__init__.py:7`:`from hermes_cli.urllib_security import open_credentialed_url` |

**`hermes_cli/nous_billing.py` 与 `hermes_cli/nous_account.py` 都不在其中。**

仓库自己的安全 opener 做的正是"跨源就摘头":

`hermes_cli/urllib_security.py:45 @ 863e313`

```python
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Let urllib enforce status/method semantics first (notably 307/308).
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None

        resolved_url = urllib.parse.urljoin(req.full_url, newurl)
        if url_origin(resolved_url) != self._original_origin:
            # Use an allowlist rather than guessing credential header names.
            # normalize_extra_headers permits arbitrary secret-bearing names.
            for name, _value in list(redirected.header_items()):
                if name.lower() not in self._cross_origin_safe_headers:
                    redirected.remove_header(name)
        return redirected
```

而 CPython 3.11 的默认实现只摘 `content-length` / `content-type`,**`Authorization` 原样带走**:

```verify
/home/user/hermes-venv/bin/python -c "import urllib.request,inspect;print(inspect.getsource(urllib.request.HTTPRedirectHandler.redirect_request))" | tail -8
```

输出(实跑,Python 3.11.15):

```text
        CONTENT_HEADERS = ("content-length", "content-type")
        newheaders = {k: v for k, v in req.headers.items()
                      if k.lower() not in CONTENT_HEADERS}
        return Request(newurl,
                       headers=newheaders,
                       origin_req_host=req.origin_req_host,
                       unverifiable=True)
```

**实测复现(与 R9C 的 H-R9A-a 定案同型)。** 我起了两个回环 HTTP 服务:A 用 302 把请求重定向到 B
(`127.0.0.1` 与 `localhost` 在 `url_origin` 眼里是不同 origin),把 `nous_billing` 的令牌缓存
直接塞成 `("SECRET-BEARER-TOKEN", "http://127.0.0.1:<A>")`,然后调 `nb._request("GET", ...)`;
对照组用 `open_credentialed_url` 发同一个请求。

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python \
  /tmp/claude-0/-home-user-hermes-study/11b9bcbd-a8fd-518c-931a-498c7a1d5f37/scratchpad/redirect_probe.py
```

```text
A saw Authorization: Bearer SECRET-BEARER-TOKEN
B saw Authorization: Bearer SECRET-BEARER-TOKEN
[open_credentialed_url] A saw Authorization: Bearer SECRET-BEARER-TOKEN
[open_credentialed_url] B saw Authorization: None
```

脚本原文留在 scratchpad(`redirect_probe.py`),主线要复核可以照抄下面这份最小复现(等价、不依赖 scratchpad):

```text
两个 http.server:B 返回 200 并记录 headers;A 返回 302 Location=http://localhost:<B端口>/…
import hermes_cli.nous_billing as nb
nb._token_cache = (9e18, "SECRET-BEARER-TOKEN", f"http://127.0.0.1:{A端口}")
nb._request("GET", "/api/billing/probe")
断言:B 收到的 Authorization 头非空 → 泄漏成立
```

**这条比"不查白名单"严重得多,因为它不需要任何本地写权限:**
即便 `base` 就是白名单内的 `https://portal.nousresearch.com`,只要该端点(或链路上任何能控制
3xx 的中间物)返回一个跨源 302,`billing:manage` 作用域的 Bearer JWT 就被送到目的地。
R9C 对 H-R9A-a 的定案说"只做主机校验而不换成 `open_credentialed_url`,**实测仍会泄漏**"——
**本处完全同型**:先校验 `base` 的主机、再用裸 `urlopen` 发,校验的是第一跳,泄漏发生在第二跳。

**同型兄弟点(顺手记,便于后续统一处置):**

`hermes_cli/nous_account.py:567 @ 863e313`

```python
    base = (portal_base_url or "https://portal.nousresearch.com").rstrip("/")
    url = f"{base}/api/oauth/account"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=8) as resp:
```

同一模式:Bearer + 裸 `urlopen`。

## 1.6 第 5 问:测试覆盖

跑了下面 6 个文件:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/hermes_cli/test_nous_billing_request.py \
  tests/hermes_cli/test_billing_portal_url.py tests/hermes_cli/test_nous_portal_staging_allowlist.py \
  tests/hermes_cli/test_billing_scope_stepup.py tests/agent/test_billing_view.py \
  tests/hermes_cli/test_urllib_security.py
```

```text
=== Summary: 6 files, 49 tests passed, 0 failed (100% complete) in 5.3s (8 workers) ===
```

**6 文件 / 49 passed / 0 failed。** 环境:`/home/user/hermes-venv`,`pip list` 条目数

```verify
/home/user/hermes-venv/bin/pip list 2>/dev/null | tail -n +3 | wc -l
ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l
```

两条都实测为 **87**(与 R8B 记录的 87 个包一致,本轮**未装任何包**)。Python 3.11.15。

覆盖分布(这是本节的重点):

| 断言 | 有没有测试 | 证据 |
|---|---|---|
| `resolve_portal_base_url()` 无 env 时回落默认值 | **有** | `tests/agent/test_billing_view.py:254` 的 `def test_portal_base_url_default(monkeypatch):` |
| env 覆盖**绕过**白名单是有意为之 | **有** | `tests/hermes_cli/test_nous_portal_staging_allowlist.py:49` 的 `def test_env_override_not_gated_by_allowlist(self, monkeypatch):` |
| stored `portal_base_url` 分支被 `nous_billing` 采信 | **有,而且是被钉住的期望** | `tests/hermes_cli/test_billing_scope_stepup.py:72`:`assert captured["portal_base_url"] == "https://preview.example.com"` |
| `_request` 跨源重定向不泄漏 Bearer | **没有** | `tests/hermes_cli/test_nous_billing_request.py` 的 5 个用例全部 monkeypatch 掉 `urlopen`(见 `:21` 的 `class _FakeResp(io.BytesIO):`),重定向语义从未被触发 |
| `open_credentialed_url` 跨源摘头 | **有(10 个用例)** | `tests/hermes_cli/test_urllib_security.py:15` 的 `open_credentialed_url` |

注意第三行:`test_billing_scope_stepup.py` 用 `"https://preview.example.com"`(**不在白名单里**)
作 stored 值并断言它被原样使用,注释写的是 "Reuses the prior credential's deployment URLs
(so a preview stays a preview)"。也就是说,**"stored 值不过白名单"在 step-up 这条路径上是被测试
钉住的既定行为**——真要改成过白名单,得同时处理这条用例。这进一步支持"不查白名单"应判为
**设计取舍/缺口**而非 ■。

## 1.7 H-R9C-a 处置结论

**改判 + 拆分定案。原移交项把两件事捆在一句话里,一半推翻、一半加重。**

1. **推翻**:"读**环境变量**时不查白名单"是缺陷 —— **不成立**。这是
   `hermes_cli/auth.py:2337`(`_nous_portal_env_override` docstring,见 1.3)
   明文规定的策略(操作者来源可信、必须绕过白名单),由 2026-07 的真实事故催生,有专门回归测试。
   两个模块在这一半上是**一致**的,不是分歧。
2. **降级**:"读**存储字段**时不查白名单,而 `hermes_cli/auth.py:5900` 查" —— 分歧属实,但
   **不判 ■,判"设计缺口(纵深防御不对齐)"**。理由:`portal_base_url` 在本基线内没有网络写入路径
   (搜索面见 1.4),要投毒必须先有本地文件写权限;而且 step-up 路径上有测试把"stored 值原样使用"
   钉成了期望行为。按 R9C"用户亲手填的地址不算 ■"的判法,这里连"用户亲手填"都算宽的
   ——只有操作者能填。
3. **加重(新增 ■)**:同一函数的下游 `_request` 用**裸 `urllib.request.urlopen`**
   而非 `open_credentialed_url`,**跨源 302 会把 `billing:manage` 的 Bearer JWT 原样送到新目的地**,
   已实测复现。这条**不依赖任何本地写权限**,是 H-R9C-a 真正该留下的那条。
   与 R9C 的 H-R9A-a **同型**,建议主线合并成同一条处置(统一换 `open_credentialed_url`),
   并把 1.5 末尾那个 `_fetch_nous_account_info` 作为第三个同型站点一并处理。

记号归属:**■**(第 3 点)+ **◇**(第 2 点)。◇ 的依据是文档侧对 env 覆盖只写了用途、
没写它同时绕过主机白名单:

`website/docs/reference/environment-variables.md:128 @ 863e313`

> | `HERMES_PORTAL_BASE_URL` | Override Nous Portal URL (for development/testing) |

这句**字面为真**(它确实是"覆盖 Portal URL,供开发/测试用"),所以**不是 ▲**;
按"代码有、文档无"记 ◇。

---

# 二、H-R9C-b —— `hermes_cli/secrets_cli.py` 的凭据落盘侧

## 2.1 原移交项复述

R9C 移交表原文(`reports/round-9c-external-interfaces.md` 第 411 行)大意:
D 片指出真正的"凭据落盘那一侧"在 `hermes_cli/secrets_cli.py`(token 写 `.env`),
R9C 只按需读了两处、没有系统读过;`tools/credential_files.py` 一行落盘代码都没有。

**范围声明:`hermes_cli/secrets_cli.py`(745 行)不在 R9D 的 49 文件范围内**,
本节是**结构级理解**,产出用于给 H-R9C-b 定案,**不改台账层级**。

## 2.2 结构级理解:五条命令、凭据从哪进、往哪落

`hermes_cli/secrets_cli.py` 是 `hermes secrets bitwarden ...` 的 CLI 处理层
(Bitwarden Secrets Manager,简称 BSM——Bitwarden 的机器账号密钥托管服务;
`bws` 是它的官方命令行二进制)。模块 docstring 自报的五条子命令:

`hermes_cli/secrets_cli.py:1 @ 863e313`

```python
"""CLI handlers for ``hermes secrets bitwarden ...``.

Subcommands:
    setup    — interactive wizard: install bws, prompt for token + project, test fetch
    status   — show current config + binary version + token validation status
    sync     — run a fetch right now and show what would be applied (dry-run friendly)
    disable  — flip ``secrets.bitwarden.enabled`` to False
    install  — just download the bws binary (no token / project required)
"""
```

实际注册的是**六条**——`register_cli` 里还有 `token`(轮换令牌),docstring 漏了它:

`hermes_cli/secrets_cli.py:78 @ 863e313`

```python
    token = sub.add_parser(
        "token",
        help="Rotate the access token: validate a new one and store it in .env",
    )
```

▲ 记号候选?**不是。** docstring 里那个 "Subcommands:" 列表少列一项属于**不完整**而非**矛盾**,
且它是源码注释不是"作者自绘地图"(README / AGENTS.md / website/docs)。按项目记号定义,
记 **◇**(代码有 `token` 子命令、模块 docstring 无)。

**凭据从哪进(三个入口,全部本地):**

| 入口 | 声明式锚点 | 备注 |
|---|---|---|
| `--access-token` 标志 | `hermes_cli/secrets_cli.py:53`:`"--access-token",` | 会进 shell 历史与 `ps`,help 文本自己写了 "will be stored in .env" |
| 掩码交互输入 | `hermes_cli/secrets_cli.py:185`:`token = masked_secret_prompt(f"  Paste access token ({token_env}): ").strip()` | 不回显 |
| 已在进程 env 里 | `hermes_cli/secrets_cli.py:462`:`token = os.environ.get(token_env, "").strip()` | `sync` 只读 env,不读 `.env` 文件 |

**往哪落(两个目的地):**

1. **访问令牌本体 → `~/.hermes/.env`**,键名由 `secrets.bitwarden.access_token_env` 决定
   (默认 `BWS_ACCESS_TOKEN`):

`hermes_cli/secrets_cli.py:183 @ 863e313`

```python
    token = (args.access_token or "").strip()
    if not token:
        token = masked_secret_prompt(f"  Paste access token ({token_env}): ").strip()
    if not token:
        console.print("  [red]Empty token, aborting.[/red]")
        return 1
    if not token.startswith("0."):
        console.print(
            "  [yellow]Warning: token doesn't start with '0.' — usually that means "
            "you pasted something other than a BSM access token.  Continuing anyway.[/yellow]"
        )

    save_env_value(token_env, token)
    os.environ[token_env] = token  # so the test fetch below sees it
    console.print(f"  [green]✓[/green] stored in {get_env_path()} as {token_env}")
```

2. **非机密的开关/项目 ID/区域 → `~/.hermes/config.yaml`**:

`hermes_cli/secrets_cli.py:288 @ 863e313`

```python
    secrets_cfg["enabled"] = True
    secrets_cfg["project_id"] = project_id
    secrets_cfg["server_url"] = server_url
    secrets_cfg.setdefault("access_token_env", token_env)
    secrets_cfg.setdefault("cache_ttl_seconds", 300)
    secrets_cfg.setdefault("override_existing", True)
    secrets_cfg.setdefault("auto_install", True)
    save_config(cfg)
```

**拉下来的密钥值本身不经过本文件落盘**——`sync --apply` 只写进程内存:

`hermes_cli/secrets_cli.py:502 @ 863e313`

```python
        if args.apply:
            os.environ[key] = secrets[key]
            applied += 1
            table.add_row(key, "[green]exported[/green]" + (" (overrode)" if already else ""))
```

密钥值的磁盘缓存在 `agent/secret_sources/bitwarden.py` 的 `bws_cache.json` /
`bws_cache.enc.json`(R9C 已查),不在本文件。

**令牌怎么交给 `bws` 子进程:走 env,不走 argv**(所以不会出现在 `ps` 里):

`hermes_cli/secrets_cli.py:611 @ 863e313`

```python
    # Secret-manager CLI child: intentionally receives tokens — no scrub,
    # no HOME rewrite (bws stores state under the real user home).
    from tools.environments.local import build_subprocess_env
    env = build_subprocess_env(scrub_secrets=False, inherit_profile_home=False)
    env["BWS_ACCESS_TOKEN"] = token
    env.setdefault("NO_COLOR", "1")
    if server_url:
        env["BWS_SERVER_URL"] = server_url
```

**`status` 不打印令牌**,只打印布尔:

`hermes_cli/secrets_cli.py:332 @ 863e313`

```python
    table.add_row("Enabled",         _yn(enabled))
    table.add_row("Token env var",   token_env)
    table.add_row("Token in env",    _yn(token_set))
```

## 2.3 落盘的权限位与原子性

`save_env_value` 是唯一落盘函数(`hermes_cli/config.py`):

`hermes_cli/config.py:3865 @ 863e313`

```python
def save_env_value(key: str, value: str):
    """Save or update a value in ~/.hermes/.env."""
```

路径:

`hermes_cli/config.py:698 @ 863e313`

```python
def get_env_path() -> Path:
    """Get the .env file path (for API keys)."""
    return get_hermes_home() / ".env"
```

**先写临时文件、fsync、再原子 replace,然后处理权限位:**

`hermes_cli/config.py:3925 @ 863e313`

```python
    fd, tmp_path = tempfile.mkstemp(dir=str(env_path.parent), suffix='.tmp', prefix='.env_')
    # Preserve original permissions so Docker volume mounts aren't clobbered.
    original_mode = None
    if env_path.exists():
        try:
            original_mode = stat.S_IMODE(env_path.stat().st_mode)
        except OSError:
            pass
    try:
        with os.fdopen(fd, 'w', **write_kw) as f:
            f.writelines(lines)
            f.flush()
            os.fsync(f.fileno())
        atomic_replace(tmp_path, env_path)
        # Preserve the original file mode (e.g. 0640 for Docker volume mounts)
        # instead of letting _secure_file unconditionally tighten to 0600.
        if original_mode is not None:
            try:
                os.chmod(env_path, original_mode)
            except OSError:
                pass
        else:
            _secure_file(env_path)
```

`_secure_file` 的语义与两个跳过条件:

`hermes_cli/config.py:822 @ 863e313`

```python
def _secure_file(path):
    """Set file to owner-only read/write (0600). No-op on Windows.

    Skipped in managed mode — the NixOS activation script sets
    group-readable permissions (0640) on config files.

    Skipped in containers — Docker/Podman volume mounts often need broader
    permissions.  Set HERMES_SKIP_CHMOD=1 to force-skip on other systems.
    """
    if is_managed() or _is_container():
        return
```

**这里有一个值得记下的设计细节:即使 `_secure_file` 被容器/managed 条件跳过,新建的 `.env`
仍然是 0600**——因为内容是 `tempfile.mkstemp` 创建的(mkstemp 固定 0600),
`atomic_replace` 只是把它 rename 过去。**只有当 `.env` 已存在时**,`original_mode` 分支会
**原样保留旧权限**(哪怕是 0644),这是为 Docker 卷挂载有意让步的取舍,不是缺陷。

实测(临时 HERMES_HOME,非容器、以 root 跑):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python \
  /tmp/claude-0/-home-user-hermes-study/11b9bcbd-a8fd-518c-931a-498c7a1d5f37/scratchpad/env_deny_probe.py
```

```text
env path      : /tmp/hermes-home-frc1g9yc/.env
exists        : True
mode          : 0o600
content       : BWS_ACCESS_TOKEN=0.deadbeef.secret-token-value
read_blocked  : True
write_denied  : True
block msg     : Access denied: /tmp/hermes-home-frc1g9yc/.env is a Hermes credential store and cannot be r
project .env read_blocked: True
cache/bws_cache.json         read_blocked=True write_denied=False
cache/bws_cache.enc.json     read_blocked=False write_denied=True
cache/op_cache.json          read_blocked=False write_denied=False
```

**mode = 0600,明文存储**(`.env` 本来就是明文格式)。写入前还有两道键名闸:

| 闸(声明式锚点) | 作用 |
|---|---|
| `hermes_cli/config.py:158`:`_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")` | 键名必须是合法 POSIX 变量名 |
| `hermes_cli/config.py:219`:`def _reject_denylisted_env_var(key: str) -> None:` | 挡掉 `LD_PRELOAD` / `PYTHONPATH` / `PATH` / `EDITOR` / `HERMES_HOME` 这类会影响子进程执行或 Hermes 运行时位置的键名 |

这一点对 `secrets_cli` 是有意义的:令牌键名不是写死的,而是**从 config.yaml 读来的可配置值**——

`hermes_cli/secrets_cli.py:181 @ 863e313`

```python
    token_env = secrets_cfg.get("access_token_env", "BWS_ACCESS_TOKEN")
```

如果没有那两道闸,一个被改坏的 config 就能借 `save_env_value` 往 `.env` 里写 `PATH=`。
(本条属**静态对读推出**,未实测,见第三节 U-3。)

## 2.4 交叉核对:落盘点在不在 agent 的读禁清单里(第 3 问,实证)

**这是 H-R9C-b 最重要的一问:凭据落到 `.env`,agent 自己读不读得到?**

`agent/file_safety.py` 的凭据文件名清单:

`agent/file_safety.py:272 @ 863e313`

```python
    # Credential / secret stores. Exact-file matches under either
    # HERMES_HOME or <root>.
    credential_file_names = (
        "auth.json",
        "auth.lock",
        ".anthropic_oauth.json",
        ".env",
        "webhook_subscriptions.json",
        os.path.join("auth", "google_oauth.json"),
        # Bitwarden Secrets Manager disk cache: stores plaintext secret values
        # to avoid re-fetching across back-to-back CLI invocations. The file
        # was introduced by #31968 but not added to this guard.
        os.path.join("cache", "bws_cache.json"),
    )
```

**`.env` 在里面**,而且还有第二道**按 basename 全盘拦截**的兜底:

`agent/file_safety.py:329 @ 863e313`

```python
    if resolved.name.lower() in _BLOCKED_PROJECT_ENV_BASENAMES:
        return (
            f"Access denied: {path} is a secret-bearing environment file "
            "and cannot be read to prevent credential leakage. "
            "If you need to check the file structure, read .env.example instead. "
            "(Defense-in-depth — not a security boundary; the terminal tool can still bypass.)"
        )
```

其中的 basename 集合:

`agent/file_safety.py:183 @ 863e313`

```python
_BLOCKED_PROJECT_ENV_BASENAMES: set[str] = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.test",
    ".env.staging",
    ".envrc",
}
```

**实证结论(上节 `env_deny_probe.py` 输出,两边对读):**

| 文件 | 谁写的 | `get_read_block_error` | `is_write_denied` |
|---|---|---|---|
| `<HERMES_HOME>/.env`(BWS 令牌落点) | `hermes_cli/secrets_cli.py:195`:`save_env_value(token_env, token)` | **True**(命中凭据清单,消息为 "is a Hermes credential store") | **True** |
| 任意目录下的 `.env` | 用户项目 | **True**(命中 basename 兜底) | — |
| `cache/bws_cache.json` | `agent/secret_sources/bitwarden.py` | **True** | False |
| `cache/bws_cache.enc.json` | 同上 | **False** | True |
| `cache/op_cache.json` | 1Password 侧同一个 `DiskCache` | **False** | False |

**所以第 3 问的答案是:落盘点 `.env` **在**禁读清单里,H-R9C-b 担心的"凭据落到 `.env`
而 `.env` 不在禁读清单里"这个形态**不成立**。** 三条边都堵着:令牌本体(`.env`)禁读、
明文值缓存(`bws_cache.json`)禁读、加密缓存(`bws_cache.enc.json`)禁写。
真正漏的两处 R9C 已经立了案,与本文件无关:`op_cache.json` 两边都不拦(R9C ■-1)、
配置侧 `terminal.credential_files` 不走禁清单(R9C ■-2,`.env` 可被挂进沙箱)。
**注意口径**:`get_read_block_error` 自己的 docstring 就写明这**不是安全边界**——

`agent/file_safety.py:217 @ 863e313`

```python
    **This is NOT a security boundary.** The terminal tool runs as the
    same OS user with shell access; the agent can still ``cat auth.json``
    or ``cat ~/.hermes/.env`` and exfiltrate the file. The read-deny exists
    as defense-in-depth that:
```

所以"在清单里"= 该有的防线都在,不等于 agent 绝对读不到。

## 2.5 补读发现的一条 ■:`setup` 在令牌未验证前就覆盖了正在工作的令牌

`cmd_token`(轮换)把这条性质当成**卖点写进了 docstring**:

`hermes_cli/secrets_cli.py:370 @ 863e313`

```python
    """Rotate the BSM access token without re-running the whole setup wizard.

    Prompts for (or accepts via ``--access-token``) a new machine-account
    token, probes Bitwarden with it (unless ``--no-verify``), and only then
    persists it to .env — so a bad paste never bricks the working token.
    """
```

代码确实如此——先探测,失败就直接返回:

`hermes_cli/secrets_cli.py:404 @ 863e313`

```python
    if not args.no_verify:
        binary = bw.find_bws(install_if_missing=True)
        if binary is None:
            console.print(
                "[red]bws binary not available — cannot verify.  "
                "Re-run with --no-verify to store anyway.[/red]"
            )
            return 1
        console.print("Verifying against Bitwarden…")
        projects = _list_projects(binary, token, console, server_url=server_url)
        if projects is None:
            console.print(
                "[red]✗ New token was rejected — nothing was changed.[/red]"
            )
            return 1
```

成功才在后面的 `hermes_cli/secrets_cli.py:432`:`save_env_value(token_env, token)` 落盘。

**但 `cmd_setup` 是相反的顺序:先落盘(`hermes_cli/secrets_cli.py:195`:`save_env_value(token_env, token)`),
后验证(`hermes_cli/secrets_cli.py:258`:`secrets, warnings = bw.fetch_bitwarden_secrets(`)。**
而 `setup` 并不是"只跑一次"的命令——本文件自己在多处引导用户**重跑它**:

`hermes_cli/secrets_cli.py:426 @ 863e313`

```python
                f"[yellow]Warning: configured project {project_id} is not visible "
                "to this machine account.  Grant it access in the Bitwarden web "
                "app or re-run `hermes secrets bitwarden setup` to pick a "
                "different project.[/yellow]"
```

**实测复现**(桩掉 `bws` 二进制与网络,先放一个"正在工作"的令牌,再用一个坏令牌跑 `setup`):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python \
  /tmp/claude-0/-home-user-hermes-study/11b9bcbd-a8fd-518c-931a-498c7a1d5f37/scratchpad/setup_overwrite_probe.py
```

```text
before        : BWS_ACCESS_TOKEN=0.GOOD-WORKING-TOKEN
  ✓ stored in /tmp/hermes-home-0f3re2fi/.env as BWS_ACCESS_TOKEN
  ✗ Fetch failed: 401 Unauthorized: access token is invalid
cmd_setup rc  : 1
after         : BWS_ACCESS_TOKEN=0.BAD-PASTED-TOKEN
good token still on disk: False
```

**命令返回 1、屏幕上明说"Fetch failed",但磁盘上那个能用的令牌已经被无声换成了坏的。**
下一次 Hermes 启动会拿坏令牌去拉密钥并失败。而 BSM 令牌**创建后无法再取回**——
这一点是向导自己在第一屏告诉用户的:

`hermes_cli/secrets_cli.py:129 @ 863e313`

```python
            "Copy the token (starts with [cyan]0.[/cyan]…) — it cannot be retrieved later.",
```

所以用户手上未必还有那个旧值——需要回 Bitwarden 后台重新签发。

严重度:**■(可恢复,不涉密泄)**。它不泄漏凭据,只破坏可用性,且用户重跑正确令牌即可修复;
但它与同文件 `cmd_token` 明文承诺的性质**直接冲突**,属于"同一份代码里两套标准"。

**同型兄弟点**:1Password 侧一样是先落盘:

`hermes_cli/onepassword_secrets_cli.py:160 @ 863e313`

```python
    token = (args.token or "").strip()
    if token:
        save_env_value(token_env, token)
        os.environ[token_env] = token
```

区别是 `onepassword` 的 `setup` **根本不验证**令牌,所以没有"验证失败却已覆盖"的自相矛盾,
只是同样缺少"先验后写"。

**测试覆盖(搜索面):**

```verify
cd /home/user/hermes-agent && grep -rn "cmd_setup\|secrets_cli" tests/ --include=*.py
```

命中中与本文件相关的只有 `tests/hermes_cli/test_secrets_bitwarden_non_tty.py`(2 个用例,
只测非 TTY 缺参报错)与 `tests/hermes_cli/test_secrets_token_rotation.py`(2 个用例)。
**没有任何用例断言"验证失败时 `.env` 保持不变"**——连 `cmd_token` 那条被写进 docstring 的
承诺也没有测试钉住(`tests/hermes_cli/test_secrets_token_rotation.py:56` 的
`def test_bw_token_no_verify_skips_probe(bw_env, monkeypatch):` 测的是**跳过**探测那条路径)。
排除项:`tests/hermes_cli/test_setup_reconfigure.py` / `test_setup_noninteractive.py` /
`test_memory_setup.py` 里的 `cmd_setup` 是**别的模块**的同名函数(`hermes_cli.main` 的安装向导 /
memory 向导),与本文件无关。

跑的测试:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/hermes_cli/test_secrets_bitwarden_non_tty.py \
  tests/hermes_cli/test_secrets_token_rotation.py tests/hermes_cli/test_bitwarden_status.py \
  tests/hermes_cli/test_secret_prompt.py tests/test_bitwarden_secrets.py
```

```text
=== Summary: 5 files, 28 tests passed, 0 failed (100% complete) in 1.3s (8 workers) ===
```

**5 文件 / 28 passed / 0 failed。**

## 2.6 H-R9C-b 处置结论

**关闭并改述:补读完成,并发现一条 ■。**

1. **补读完成。** `hermes_cli/secrets_cli.py` 已获结构级理解:6 条子命令
   (docstring 只列了 5,漏 `token` —— ◇),凭据三个入口(`--access-token` / 掩码提示 / 进程 env),
   两个落点(令牌 → `~/.hermes/.env`;开关与项目 ID → `config.yaml`),
   拉回的密钥值**不经本文件落盘**(`sync --apply` 只写 `os.environ`)。
2. **落盘卫生:合格。** `save_env_value` 走 `mkstemp` + `fsync` + `atomic_replace`;
   新建文件 0600(实测);已存在文件保留原权限(为 Docker 卷挂载有意让步);
   键名过 `_ENV_VAR_NAME_RE` + `_reject_denylisted_env_var` 两道闸;
   令牌经 env 交给 `bws` 子进程而非 argv;`status` 不回显令牌。
3. **移交项担心的那个形态不成立。** `.env` **在** `agent/file_safety.py` 的读禁清单里
   (而且被两条规则各拦一次),已实测。真正的两个洞(`op_cache.json`、
   `terminal.credential_files` 绕过禁清单)R9C 已立案,不属本文件。
4. **新增 ■:`cmd_setup` 在验证前落盘**,重跑向导时一次坏粘贴会无声销毁正在工作的令牌
   (实测复现,返回码 1 但磁盘已改),与同文件 `cmd_token` docstring 明文承诺的
   "a bad paste never bricks the working token" 自相矛盾;1Password 侧同型。
   建议修法:把 `:195` 的 `save_env_value` 挪到 `:258` 的 test fetch 之后
   (向导已经在 `:196` 用 `os.environ[token_env] = token` 让后续步骤看得见这个令牌,
   所以推迟落盘不影响向导流程)。

---

# 三、未取证 / 推定

| # | 事项 | 强度 | 锚点 |
|---|---|---|---|
| U-1 | "跨源 302 泄漏 Bearer" 是在**回环 HTTP** 上复现的,没有对真实 `portal.nousresearch.com` 发过请求(项目边界:不配置付费凭据、不发真实带凭据请求)。真实 Portal 是否会返回跨源 302 **未取证**——但该 ■ 的成立不依赖它:泄漏面是"任何能控制 3xx 的链路环节" | **实跑复现(机制层)+ 推定(真实端点行为)** | `hermes_cli/nous_billing.py:413`:`with urllib.request.urlopen(req, timeout=timeout) as resp:` |
| U-2 | 我读了 130 处非测试 `portal_base_url` 命中来支撑"无网络写入路径",但**没有**穷举 `state` 这个 dict 的所有别名传递(例如经 `**kwargs` 展开后再写回)。若存在这样的路径,1.4 的负结论会被推翻 | **静态对读推出** | `hermes_cli/auth.py:5346`:`for key in (` (`_merge_shared_nous_oauth_state` 的键复制循环) |
| U-3 | `_reject_denylisted_env_var` 能挡住把 `access_token_env` 配成 `PATH` 这类攻击,是**读代码推出**的;我只实测了正常键名 `BWS_ACCESS_TOKEN` 落盘成功,**没有**实测一个被改坏的 `config.yaml` 走完 `cmd_setup` | **静态对读推出** | `hermes_cli/config.py:219`:`def _reject_denylisted_env_var(key: str) -> None:` |
| U-4 | `cmd_setup` 的 ■ 我是用桩函数(替换 `bw.find_bws` / `bw.fetch_bitwarden_secrets`)复现的,**没有**真的装 `bws` 二进制跑一遍(离线容器,且不应下载二进制)。桩替换的是网络与外部进程,被测的落盘顺序是真实代码 | **实跑复现(桩掉外部依赖)** | `hermes_cli/secrets_cli.py:195`:`save_env_value(token_env, token)` |
| U-5 | `_fetch_nous_account_info` 里那个同型泄漏点**未单独实测**,只做了静态同型比对 | **静态对读推出** | `hermes_cli/nous_account.py:574`:`with urllib.request.urlopen(req, timeout=8) as resp:` |
| U-6 | 本文对 `hermes_cli/secrets_cli.py` 是**结构级**理解,`_resolve_server_url`(`:669-745`)的交互分支未逐行读 | **知悉用途** | `hermes_cli/secrets_cli.py:669`:`def _resolve_server_url(` |

---

# 四、给主线的定案表(声明式锚点)

| 移交项 | 处置 | 核心锚点 | 主线可独立重跑的复核 |
|---|---|---|---|
| **H-R9C-a** | **改判**:env 分支非缺陷(推翻);stored 分支降级为设计缺口;**新增 ■ = 裸 `urlopen` 跨源重定向泄漏 Bearer**,与 H-R9A-a 同型 | `hermes_cli/nous_billing.py:413`:`with urllib.request.urlopen(req, timeout=timeout) as resp:`;对照 `hermes_cli/urllib_security.py:112` 的 `open_credentialed_url`;策略依据 `hermes_cli/auth.py:2340`:`gated by ``_NOUS_PORTAL_ALLOWED_HOSTS``: that allowlist exists to reject` | 跑 `redirect_probe.py`(见 1.5),看 B 端是否收到 `Authorization`;再跑上面那 6 个测试文件确认 49/0 |
| **H-R9C-b** | **关闭并改述**:补读完成、落盘卫生合格、`.env` **在**禁读清单里(原担心形态不成立);**新增 ■ = `cmd_setup` 验证前落盘** | `hermes_cli/secrets_cli.py:195`:`save_env_value(token_env, token)`;禁清单 `agent/file_safety.py:278`:`".env",`;反例承诺 `hermes_cli/secrets_cli.py:374`:`persists it to .env — so a bad paste never bricks the working token.` | 跑 `env_deny_probe.py` 看 `read_blocked=True` / `mode=0o600`;跑 `setup_overwrite_probe.py` 看 rc=1 而 `.env` 已被改 |

---

# 五、附录:三个复现脚本全文(主线可原样落盘重跑)

下面三段**不是基线源码**,是本轮为取证写的一次性探针。主线把它们存成同名 `.py`
放在任意可写目录(不要放进基线仓库),按各节给出的 `verify` 命令跑即可。

## A. `redirect_probe.py` —— 跨源 302 是否带走 Bearer(1.5 用)

```text
"""Probe: does hermes_cli.nous_billing._request leak Authorization across a
cross-host redirect? Two loopback servers; A 302-redirects to B.
127.0.0.1 and localhost are different origins for url_origin().
"""
import json, sys, threading, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, "/home/user/hermes-agent")

captured = {}


def make_handler(name, redirect_to=None):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            captured.setdefault(name, []).append(dict(self.headers))
            if redirect_to:
                self.send_response(302)
                self.send_header("Location", redirect_to + self.path)
                self.end_headers()
            else:
                body = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def log_message(self, *a):
            pass
    return H


srv_b = HTTPServer(("127.0.0.1", 0), make_handler("B"))
port_b = srv_b.server_address[1]
srv_a = HTTPServer(("127.0.0.1", 0), make_handler("A", f"http://localhost:{port_b}"))
port_a = srv_a.server_address[1]
for s in (srv_a, srv_b):
    threading.Thread(target=s.serve_forever, daemon=True).start()

import hermes_cli.nous_billing as nb

nb._token_cache = (9e18, "SECRET-BEARER-TOKEN", f"http://127.0.0.1:{port_a}")
try:
    nb._request("GET", "/api/billing/probe")
except Exception as exc:
    print("request raised:", type(exc).__name__, exc)

print("A saw Authorization:", captured.get("A", [{}])[0].get("Authorization"))
print("B saw Authorization:", captured.get("B", [{}])[0].get("Authorization") if captured.get("B") else "<B never hit>")

# contrast: open_credentialed_url
from hermes_cli.urllib_security import open_credentialed_url
captured.clear()
req = urllib.request.Request(
    f"http://127.0.0.1:{port_a}/api/billing/probe",
    headers={"Authorization": "Bearer SECRET-BEARER-TOKEN", "Accept": "application/json"},
)
with open_credentialed_url(req, timeout=5) as r:
    r.read()
print("[open_credentialed_url] A saw Authorization:", captured.get("A", [{}])[0].get("Authorization"))
print("[open_credentialed_url] B saw Authorization:", captured.get("B", [{}])[0].get("Authorization") if captured.get("B") else "<B never hit>")
```

## B. `env_deny_probe.py` —— `.env` 落盘权限位与读禁清单(2.3 / 2.4 用)

```text
"""Probe: is the file secrets_cli lands the BWS token in (~/.hermes/.env)
covered by the agent read-deny list? And what mode does it get?
"""
import os, stat, sys, tempfile
from pathlib import Path

home = tempfile.mkdtemp(prefix="hermes-home-")
os.environ["HERMES_HOME"] = home
os.environ.setdefault("HERMES_DISABLE_LAZY_INSTALLS", "1")
sys.path.insert(0, "/home/user/hermes-agent")

from hermes_cli.config import get_env_path, save_env_value
from agent.file_safety import get_read_block_error, is_write_denied

save_env_value("BWS_ACCESS_TOKEN", "0.deadbeef.secret-token-value")

p = get_env_path()
print("env path      :", p)
print("exists        :", p.exists())
print("mode          :", oct(stat.S_IMODE(p.stat().st_mode)))
print("content       :", p.read_text().strip())
print("read_blocked  :", bool(get_read_block_error(str(p))))
print("write_denied  :", is_write_denied(str(p)))
print("block msg     :", (get_read_block_error(str(p)) or "")[:90])

# a project-local .env elsewhere on disk
other = Path(tempfile.mkdtemp()) / ".env"
other.write_text("X=1\n")
print("project .env read_blocked:", bool(get_read_block_error(str(other))))

# contrast with the bitwarden caches R9C examined
for rel in ("cache/bws_cache.json", "cache/bws_cache.enc.json", "cache/op_cache.json"):
    fp = Path(home) / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("{}")
    print(f"{rel:28s} read_blocked={bool(get_read_block_error(str(fp)))} write_denied={is_write_denied(str(fp))}")
```

## C. `setup_overwrite_probe.py` —— `setup` 验证前落盘(2.5 用)

```text
"""Probe: does `hermes secrets bitwarden setup` overwrite a WORKING token in
.env with a bad paste before the token has been validated?

Contrast with cmd_token, whose docstring promises "only then persists it to
.env — so a bad paste never bricks the working token".
"""
import argparse, os, sys, tempfile, types
from pathlib import Path

home = tempfile.mkdtemp(prefix="hermes-home-")
os.environ["HERMES_HOME"] = home
os.environ.setdefault("HERMES_DISABLE_LAZY_INSTALLS", "1")
sys.path.insert(0, "/home/user/hermes-agent")

from hermes_cli.config import get_env_path, save_env_value
import hermes_cli.secrets_cli as sc

# 1) a working token is already on disk
save_env_value("BWS_ACCESS_TOKEN", "0.GOOD-WORKING-TOKEN")
print("before        :", get_env_path().read_text().strip())

# 2) stub out everything that would touch the network / the bws binary
sc.bw.find_bws = lambda install_if_missing=False: Path("/usr/bin/bws")
sc.bw.install_bws = lambda force=False: Path("/usr/bin/bws")
sc._bws_version = lambda _p: "1.0.0"


def _fail_fetch(**kw):
    raise RuntimeError("401 Unauthorized: access token is invalid")


sc.bw.fetch_bitwarden_secrets = _fail_fetch

args = argparse.Namespace(
    access_token="0.BAD-PASTED-TOKEN",
    project_id="11111111-2222-3333-4444-555555555555",
    server_url="https://vault.bitwarden.eu",
)
rc = sc.cmd_setup(args)
print("cmd_setup rc  :", rc)
print("after         :", get_env_path().read_text().strip())
print("good token still on disk:", "GOOD-WORKING-TOKEN" in get_env_path().read_text())
```
