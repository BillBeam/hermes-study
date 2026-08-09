# r9a 底稿 · 两条移交项的全仓普查(H-R8D-e / H-R8D-f)

> 研究对象基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(只读)。
> 溯源约定:凡对代码行为的断言,**锚点单独成行、置于代码块之前**,格式 `路径:行号 @ 863e313`。
> 本文是底稿(证据层),求全求证、允许啰嗦。
>
> 这两条移交项都是"上一轮只看到一个个例、没做普查"的形状,所以本文的价值全在**普查的完备性**:
> 每一条全称判断(尤其是否定判断)后面都附**搜索面**——搜了什么模式、覆盖哪些路径、排除了什么、
> 为什么这个面是完备的。按项目制度,不写搜索面的全称否定等于"我没看见"。

---

## 0. 两条移交项的处置(先给结论)

| 移交项 | 处置 | 一句话 |
|---|---|---|
| **H-R8D-e** 带凭据的裸 `urlopen` | **关闭并加重** | 个例属实但**不是最严重的那个**;普查在 99 个非测试裸 `urlopen` 里找出 **44 个带凭据**、其中 **21 个 URL 可控**;最重的一处是 `gateway/relay/media.py:174`——URL 来自**入站事件**,门禁是一次 `in` 子串判断,任何含 `/relay/media/` 的 URL 都会拿到网关 bearer |
| **H-R8D-f** 挂在 `PYTEST_CURRENT_TEST` 上的安全判断 | **关闭**(结论收窄,不加重) | 全仓非测试代码命中 **10 处**,同类惯用法(`sys.modules` 探 pytest / `PYTEST_ADDOPTS` / `sys.argv` 嗅探 / CI 变量)**零命中**;10 处里只有 `managed_scope.py:49` 一处**移除安全控制**,其余 9 处要么 fail-closed(拒绝写真实凭据库)、要么纯可用性(看门狗不上膛) |

---

# 普查一:H-R8D-e —— 带凭据的裸 `urlopen`

移交项原文:

> **H-R8D-e**(移交 R9):锚点 `hermes_cli/models.py:4612`——Bearer 令牌走裸 `urlopen`,
> 而 `base_url` 是**配置可控**的;全仓 60+ 个裸 `urlopen` 里还有多少**带凭据**,上一轮**未普查**。

## 1.1 先读封装:`urllib_security.py` 提供什么、是不是强制的

**结论先行:仓库自己写了一个专门解决"凭据跟着重定向跑到别的主机"的封装,但它是"可选的库函数",不是"强制的通道"。全仓 99 个非测试裸 `urlopen` 里只有 5 处调用它。**

要理解这个封装解决什么,先看 Python 标准库的默认行为——**这是整条风险链的物理基础**:

```verify
python3 -c "
import inspect, urllib.request, sys
print('python', sys.version.split()[0])
print(inspect.getsource(urllib.request.HTTPRedirectHandler.redirect_request))
" | sed -n '1p;28,34p'
```

```console
python 3.11.15
        CONTENT_HEADERS = ("content-length", "content-type")
        newheaders = {k: v for k, v in req.headers.items()
                      if k.lower() not in CONTENT_HEADERS}
        return Request(newurl,
                       headers=newheaders,
                       origin_req_host=req.origin_req_host,
                       unverifiable=True)
```

标准库在跟随 30x 重定向时,**除 `Content-Length` / `Content-Type` 外的全部请求头原样搬到新 URL**——
包括 `Authorization`。也就是说:只要 `urlopen` 跟随了一次跨主机重定向,你挂在 `Request` 上的
Bearer 就会被送到新主机。**这不是 hermes 的 bug,是 stdlib 的既定行为**;hermes 的
`urllib_security.py` 就是为这件事写的。

封装的白名单只有两个头,注释写明了理由——不猜凭据头的名字,而是反过来列出**安全的**头:

`hermes_cli/urllib_security.py:11-14` @ 863e313

```python
# Headers safe to forward to a different origin. Everything else is dropped:
# custom provider headers routinely carry credentials under arbitrary names.
_CROSS_ORIGIN_SAFE_HEADERS = frozenset({"accept", "user-agent"})
_DEFAULT_PORTS = {"http": 80, "https": 443}
```

跨源时的清洗动作(先让 stdlib 判定 307/308 的方法语义,再按白名单剥头):

`hermes_cli/urllib_security.py:46-57` @ 863e313

```python
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
```

对外的唯一入口。注意 `opener_factory` 那句注释:**测试接缝是显式参数,而不是"检测到 `urlopen` 被 mock 了就关掉安全"**——这一点和普查二的主题正好呼应:

`hermes_cli/urllib_security.py:112-132` @ 863e313

```python
def open_credentialed_url(
    request: urllib.request.Request,
    *,
    timeout: float,
    opener_factory: Callable[..., Any] | None = None,
):
    """Open a request without forwarding credentials across origins.

    The default preserves an application-installed opener's proxy, TLS,
    cookies, custom protocol handlers, and instrumentation while replacing its
    redirect handler. ``opener_factory`` is an explicit test seam; security is
    never disabled based on global ``urlopen`` identity.
    """
    if opener_factory is None:
        opener = _secure_opener_from_installed_policy(request.full_url)
        for name, value in getattr(opener, "_hermes_initial_addheaders", ()):
            if not request.has_header(name):
                request.add_header(name, value)
    else:
        opener = opener_factory(SafeCredentialRedirectHandler(request.full_url))
    return opener.open(request, timeout=timeout)
```

**它是不是强制的?不是。** 它是一个普通函数,调用与否全凭调用点自觉。搜索面见 §1.3,
非测试代码里的调用点只有 5 处:

```text
走了封装的 5 个调用点(非测试)
  hermes_cli/azure_detect.py:163      _http_get_json
  hermes_cli/azure_detect.py:274      _probe_anthropic_messages
  hermes_cli/models.py:41             _urlopen_model_catalog_request(models.py 内部的统一出口)
  plugins/model-providers/anthropic/__init__.py:32  fetch_models
  providers/base.py:232               fetch_models(所有 provider 的基类默认实现)
```

`models.py` 自己建了一个内部出口,把"目录抓取"这一类请求统一收口:

`hermes_cli/models.py:39-41` @ 863e313

```python
def _urlopen_model_catalog_request(req: urllib.request.Request, *, timeout: float):
    """Open catalog requests without forwarding headers across origins."""
    return open_credentialed_url(req, timeout=timeout)
```

这就让 §1.2 的个例格外扎眼:**同一个文件里有 13 处 `Request(` 构造、11 处走了这个出口,
唯独 3 处没走,而没走的那 3 处里恰好有唯一一处带 Bearer 的**。

## 1.2 复核个例:`hermes_cli/models.py:4612`(行号无漂移)

移交项给的行号**准确**。完整函数如下(注意它是私有的 `_fetch_ai_gateway_models`,
与同文件 1620 行那个公开的 `fetch_ai_gateway_models` 同名不同体):

`hermes_cli/models.py:4595-4622` @ 863e313

```python
def _fetch_ai_gateway_models(timeout: float = 5.0) -> Optional[list[str]]:
    """Fetch available language models with tool-use from AI Gateway."""
    api_key = os.getenv("AI_GATEWAY_API_KEY", "").strip()
    if not api_key:
        return None
    base_url = os.getenv("AI_GATEWAY_BASE_URL", "").strip()
    if not base_url:
        from hermes_constants import AI_GATEWAY_BASE_URL
        base_url = AI_GATEWAY_BASE_URL

    url = base_url.rstrip("/") + "/models"
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": _HERMES_USER_AGENT,
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return [
                m["id"]
                for m in data.get("data", [])
                if m.get("id")
                and m.get("type") == "language"
                and "tool-use" in (m.get("tags") or [])
            ]
    except Exception:
        return None
```

风险链拆成三段:

**(a) URL 是配置可控的。** `base_url` 来自 `AI_GATEWAY_BASE_URL` 环境变量,这是**文档化的用户可改项**:

`website/docs/reference/environment-variables.md:23` @ 863e313

> | `AI_GATEWAY_BASE_URL` | Override AI Gateway base URL (default: `https://ai-gateway.vercel.sh/v1`) |

而 hermes 的"环境变量"并不只是 shell 里的东西——`~/.hermes/.env` 在启动时被加载,
并且仓库自己提供了写这个文件的 API(`hermes_cli/config.py:3865` 的 `save_env_value`、
web 控制台的 `set_env_var`)。所以"改 base_url"等价于"能写 `~/.hermes/.env` 或能改进程环境"。

**(b) 凭据被附在同一个请求上。** `Authorization: Bearer {api_key}`,`api_key` 来自
`AI_GATEWAY_API_KEY`。

**(c) 没走封装。** 同文件 41 行的 `_urlopen_model_catalog_request` 就在那里,这一处直接
`urllib.request.urlopen(req, ...)`。

**这条链的准确强度评估(比移交项原文更收窄一点):** `base_url` 与 `api_key` 来自**同一个信任域**
(同一份 `.env` / 同一个进程环境)。能改 base_url 的人通常也能直接读 api_key,所以"把 key 引到攻击者
主机"这一步并不额外增加多少能力。**这一处真正的、无法靠信任域论证消掉的残余风险是重定向**:
配置指向的合法网关(或任何中间设备)返回一次 30x,Bearer 就跟着走——见 §1.1 的 stdlib 行为。
换句话说,`models.py:4612` 是一个**真问题、但不是最重的那类**;真正危险的是 URL 来自
**运行时数据**而凭据来自配置的那一类(§1.5)。

## 1.3 搜索面(完备性声明)

**语料**:`git grep`,即基线**已跟踪文件**。这一点必须写出来——工作区里存在
`optional-skills/research/osint-investigation/scripts/__pycache__/*.pyc` 这类**被 `.gitignore` 忽略的
残留物**,普通 `grep -r` 会把它们算进来:

```verify
cd /home/user/hermes-agent && git check-ignore -v optional-skills/research/osint-investigation/scripts/__pycache__/fetch_senate_ld.cpython-311.pyc; git ls-files optional-skills/research/osint-investigation/scripts/__pycache__/ | wc -l
```

```console
.gitignore:60:__pycache__/	optional-skills/research/osint-investigation/scripts/__pycache__/fetch_senate_ld.cpython-311.pyc
0
```

**模式与范围**(逐条给出实际跑的命令,重跑可复现):

```verify
cd /home/user/hermes-agent
# 1) 全仓(含测试、含文档)出现 urlopen 的行数
git grep -c "urlopen" -- . | awk -F: '{s+=$NF} END{print "all-lines:", s}'
# 2) .py 里 urlopen( 调用行(含测试)
git grep -c "urlopen(" -- '*.py' | awk -F: '{s+=$NF} END{print "py-call-lines:", s}'
# 3) .py 里 urlopen( 调用行(排除测试)
git grep -c "urlopen(" -- '*.py' ':!tests/' ':!*/tests/*' | awk -F: '{s+=$NF} END{print "nontest-call-lines:", s}'
# 4) Request( 构造点(排除测试)
git grep -oE "urllib\.request\.Request\(|urlrequest\.Request\(|[^._a-zA-Z]Request\(" -- '*.py' ':!tests/' ':!*/tests/*' | wc -l
# 5) 安全封装的调用点(含定义行)
git grep -c "open_credentialed_url(" -- '*.py' ':!tests/' | awk -F: '{s+=$NF} END{print "wrapper-lines:", s}'
```

```console
all-lines: 354
py-call-lines: 160
nontest-call-lines: 100
112
wrapper-lines: 6
```

从 100 行减到 **99 个真实调用点**的两处扣除,都点名列出以便复核:
`hermes_cli/nous_billing.py:462` 是注释行(`# urlopen() wraps CONNECT-phase timeouts…`),
`hermes_cli/models.py:39` 是 `def _urlopen_model_catalog_request(` 的定义行。
封装 6 行里 1 行是 `hermes_cli/urllib_security.py:112` 的 `def`,故**实际调用点 5 个**。
99 + 5 = **104 个非测试 HTTP 出口**,分布在 **66 个文件**。

**排除了什么、为什么可以排除**:

1. `tests/` 与 `*/tests/`(41 个调用点)——测试代码不是产品行为;但**其中 4 个反而是证据**
   (`tests/hermes_cli/test_urllib_security.py` 的 4 个用例证明封装确实在网线上剥头),§1.6 引用。
2. **非 `urlopen` 的 HTTP 出口**:`urlretrieve`、`build_opener().open()`、`http.client`。
   这一类**没有排除,单独查过**,结果见下(它们是移交项措辞之外的补充面,不查会漏掉三处独立的
   重定向硬化实现):

```verify
cd /home/user/hermes-agent && git grep -n "urlretrieve\|build_opener\|install_opener\|opener\.open" -- '*.py' ':!tests/' ':!*/tests/*'
```

```console
agent/outbound_webhooks.py:517:_opener = urlrequest.build_opener(_NoRedirectHandler)
agent/outbound_webhooks.py:533:            with _opener.open(req, timeout=delivery["timeout"]) as resp:
hermes_cli/update_cmd.py:733:    from urllib.request import urlretrieve
hermes_cli/update_cmd.py:762:        urlretrieve(zip_url, zip_path)
hermes_cli/update_cmd.py:1911:        urllib.request.urlretrieve(PSUTIL_URL, archive)
hermes_cli/urllib_security.py:90:        installed = urllib.request.build_opener()
hermes_cli/urllib_security.py:99:    secured = urllib.request.build_opener(*handlers)
hermes_cli/urllib_security.py:132:    return opener.open(request, timeout=timeout)
optional-skills/finance/stocks/scripts/stocks_client.py:32:_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cookie_jar))
optional-skills/finance/stocks/scripts/stocks_client.py:123:            with _opener.open(req, timeout=15) as resp:
optional-skills/finance/stocks/scripts/stocks_client.py:159:        with _opener.open(req, timeout=10) as resp:
optional-skills/finance/stocks/scripts/stocks_client.py:168:        with _opener.open(req, timeout=10) as resp:
scripts/ci/live_comment.py:316:    opener = urllib.request.build_opener(_NoRedirectHandler)
scripts/ci/live_comment.py:319:        opener.open(urllib.request.Request(archive_download_url, headers={
scripts/ci/timings_report.py:74:            with urllib.request.urlopen(req) as resp:
scripts/iso-certify.py:369:            with urllib.request.urlopen(rest_url, timeout=30) as fh:
scripts/iso-certify.py:411:            with urllib.request.urlopen(rest_url, timeout=30) as fh:
scripts/install_psutil_android.py:85:        urllib.request.urlretrieve(PSUTIL_URL, archive)
skills/creative/comfyui/scripts/_common.py:602:    opener = urllib.request.build_opener(_RedirectHandler(original_host, follow_redirects))
skills/creative/comfyui/scripts/_common.py:605:        resp = opener.open(req, timeout=timeout)
tools/wake_word.py:616:    urllib.request.urlretrieve(_SHERPA_KWS_MODEL_URL, archive)  # noqa: S310
```

3. **不排除文档/网站**:`website/docs/**` 的 4 处 `urlopen` 是教程示例代码,不构成产品行为,
   但已逐条看过、无凭据。

**为什么这个面是完备的(针对"没有别的带凭据裸 urlopen"这条否定)**:凭据要进入一个
`urllib` 请求,只有三条路——(i) `Request(headers={...})` 字面量,(ii) `req.add_header(...)`,
(iii) 由**调用方**以 `headers` 形参传进来。前两条用 AST 在**整个外层函数体**内枚举
(不是靠正则读那一行),第三条单独枚举了所有"形参名含 header"的 HTTP helper 并逐个追调用方:

```verify
cd /home/user/hermes-agent && python3 - <<'PY'
import ast, subprocess
from pathlib import Path
ROOT = Path(".")
files = subprocess.run(["git","grep","-l","-E",r"urlopen\(","--","*.py"],
                       capture_output=True, text=True).stdout.split()
hits = []
for rel in files:
    if rel.startswith("tests/") or "/tests/" in rel:
        continue
    tree = ast.parse((ROOT/rel).read_text(errors="replace"))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in list(n.args.args)+list(n.args.kwonlyargs)]
            if any("header" in a.lower() for a in args) and \
               "urlopen(" in "\n".join((ROOT/rel).read_text(errors="replace")
                                       .splitlines()[n.lineno-1:n.end_lineno]):
                hits.append(f"{rel}:{n.lineno} def {n.name}({', '.join(args)})")
print("\n".join(sorted(set(hits))))
PY
```

```console
hermes_cli/nous_billing.py:382 def _request(method, path, body, extra_headers, timeout, _retried_auth)
optional-skills/mcp/mcp-oauth-remote-gateway/scripts/diagnose-oauth-mcp.py:46 def _post(url, data, headers, form, timeout)
optional-skills/productivity/telephony/scripts/telephony.py:237 def _json_request(method, url, headers, params, form, json_body)
optional-skills/research/osint-investigation/scripts/_http.py:22 def get(url, params, headers, user_agent, max_retries, backoff, timeout)
plugins/platforms/a2a/tools.py:81 def _http_get_json(url, headers, timeout)
plugins/platforms/a2a/tools.py:87 def _http_post_json(url, body, headers, timeout)
```

第四条路——**凭据不在头里,而在 URL query 或 POST body**——也单独扫过(否则会漏掉
OAuth token 交换、`?api_key=` 这一类):

```verify
cd /home/user/hermes-agent && for f in $(git grep -l -E "urlopen\(" -- '*.py' ':!tests/' ':!*/tests/*'); do git grep -n -i -E "[?&](api_?key|apikey|key|token|access_token|auth|secret)=" -- "$f"; done | grep -viE ":[0-9]+: *#" | grep -vE "web_server\.py:(2423|14571|14686|14701|14928|14992)"
```

```console
optional-skills/health/fitness-nutrition/scripts/nutrition_search.py:27:        f"{BASE}/foods/search?api_key={API_KEY}"
plugins/platforms/google_chat/oauth.py:642:                f"https://oauth2.googleapis.com/revoke?token={creds.token}",
scripts/iso-certify.py:215:        self.url = f"ws://127.0.0.1:{port}/api/ws?token={token}"
skills/productivity/google-workspace/scripts/setup.py:470:                f"https://oauth2.googleapis.com/revoke?token={creds.token}",
```

(被 `grep -vE` 排掉的 6 行是 `hermes_cli/web_server.py` 里描述**自己服务端**
`?token=` 认证的文档字符串,不是出站请求;点名列出以便复核,不是静默过滤。)

## 1.4 判定表:104 个非测试 HTTP 出口的逐点判定

先给三档 URL 可控性的定义,后面整张表按它分档——这个分档是本次普查最重要的产出,
因为移交项原文只说"配置可控",而**同为"可控",三档的攻击门槛差着数量级**:

```text
档位定义
  C  运行时数据控制 URL —— URL 来自 HTTP 响应体、入站事件、对端消息。
     攻击者不需要任何本地权限,只要能影响那份数据。凭据来自配置。→ 最危险
  B  配置/环境控制 URL —— URL 来自 .env / config.yaml / auth.json / CLI 参数。
     攻击者需要能写这些文件或改进程环境。凭据通常来自同一份配置(同信任域)。
  A  URL 硬编码或白名单 —— 常量、常量拼接、dict 白名单查表。
     唯一残余风险是 30x 重定向把头带走(§1.1)。
```

**判定表(只列"带凭据"的 44 个;其余 60 个无凭据,理由见表后)**

```text
═══ C 档:URL 由运行时数据控制 + 带凭据 + 未走封装 ══════════════════ 3 处 ═══
 1  gateway/relay/media.py:174          Authorization: Bearer <网关 upgrade token>
    URL 来自入站事件 event.media_urls;门禁 is_relay_media_url() 是
    `"/relay/media/" in url` 子串判断 → 任意主机可命中。■ 最重
 2  optional-skills/research/osint-investigation/scripts/_http.py:49
    Authorization: Token <CourtListener/Senate LDA API key>
    URL 来自上一页响应的 payload["next"](fetch_courtlistener.py:101 /
    fetch_senate_ld.py:107),头在整个翻页循环里不变
 3  hermes_cli/diagnostics_upload.py:114 (无 header 凭据,但 URL 本身是凭据)
    presigned upload_url 来自 NAS 响应;诊断包 PUT 到响应指定的地方

═══ B 档:URL 由配置/环境控制 + 带凭据 + 未走封装 ═════════════════ 18 处 ═══
 4  hermes_cli/models.py:4612           Bearer AI_GATEWAY_API_KEY   ← 移交项锚点
                                        base=AI_GATEWAY_BASE_URL(env/.env)
 5  hermes_cli/nous_account.py:574      Bearer access_token / portal_base_url(auth.json)
 6  hermes_cli/nous_billing.py:413      Bearer / resolve_portal_base_url(env→auth.json→默认)
 7  hermes_cli/dashboard_register.py:141 Bearer / portal_base_url(auth.json 或 --portal 覆盖)
 8  hermes_cli/gateway_enroll.py:130    Bearer / connector_base_url(参数)
 9  gateway/relay/__init__.py:472       Bearer / provision_url ← relay dial URL(config)
10  gateway/relay/__init__.py:729       Bearer / policy_url  ← 同上
11  gateway/relay/__init__.py:557       client_secret 在 form body /
                                        token_url ← GATEWAY_RELAY_IDP_TOKEN_URL 或
                                        gateway.idp.token_url
12  gateway/relay/media.py:140          Bearer / base_url(config)——上传方向
13  plugins/memory/hindsight/__init__.py:205  Bearer / api_url(插件配置)
14  plugins/memory/supermemory/__init__.py:417 Bearer / self._base_url(插件配置)
15  plugins/model-providers/actual/__init__.py:65 Bearer / ACTUAL_BASE_URL(env)
                                        ■ 基类同名方法走了封装,这个覆写把它丢了
16  plugins/platforms/a2a/tools.py:83   Bearer / peer url(config a2a_agents)
17  plugins/platforms/a2a/tools.py:91   同上(POST)
18  agent/proxy_sources/iron_proxy.py:959 Bearer / host:port ← proxy.yaml 管理监听器
19  hermes_cli/copilot_auth.py:219      device_code 流 / host 形参(GHE 自建域名)
20  hermes_cli/copilot_auth.py:265      同上(轮询,携带 device_code)
21  skills/.../google-workspace/scripts/gws_bridge.py:54
                                        client_secret+refresh_token 在 body /
                                        URL = google_token.json 里的 token_uri
22  optional-skills/mcp/.../diagnose-oauth-mcp.py:56  Bearer / --mcp-url 或 token JSON

═══ A 档:URL 硬编码或白名单 + 带凭据 + 未走封装 ══════════════════ 23 处 ═══
    (唯一残余风险 = 30x 重定向带走头;按 §1.1 这是真实的,但需要上游合谋/被攻陷)
23  hermes_cli/copilot_auth.py:553      Bearer / _TOKEN_EXCHANGE_URL 常量
24  hermes_cli/web_server.py:4466       xi-api-key / api.elevenlabs.io 常量
25  hermes_cli/webhook.py:302           X-Hub-Signature-256(HMAC,非可复用凭据)/ 用户给的 url
26  optional-skills/devops/watchers/scripts/watch_github.py:127 Bearer GITHUB_TOKEN /
                                        api.github.com 常量
27  plugins/platforms/feishu/adapter.py:5480  app_secret 在 body / _ONBOARD_OPEN_URLS 白名单
28  plugins/platforms/feishu/adapter.py:5494  Bearer tenant_access_token / 同上
29  plugins/platforms/feishu/adapter.py:5264  注册表单 / _ONBOARD_ACCOUNTS_URLS 白名单
30  tools/discord_tool.py:108           Authorization: Bot / DISCORD_API_BASE 常量
31  tools/tirith_security.py:290        Authorization: token GITHUB_TOKEN / github.com 常量
                                        ◇ 但签名是通用 _download_file(url,...),未来任何
                                        调用方传任意 URL 都会自动带上 token(latent)
32  optional-skills/productivity/telephony/scripts/telephony.py:261
                                        Basic/Bearer(Twilio/Vapi/Bland)/ 三个常量 base
33  agent/anthropic_adapter.py:1136     refresh_token 在 body / 两个常量端点
34  agent/anthropic_adapter.py:1599     授权码+verifier 在 body / _OAUTH_TOKEN_URLS 常量
35  hermes_cli/web_server.py:10284      同上(dashboard PKCE 回调)
36  plugins/platforms/google_chat/oauth.py:640   token 在 query / oauth2.googleapis.com 常量
37  skills/.../google-workspace/scripts/setup.py:468  同上
38  optional-skills/health/fitness-nutrition/scripts/nutrition_search.py:33
                                        api_key 在 query / api.nal.usda.gov 常量
39  scripts/ci/live_comment.py:138      Bearer GITHUB_TOKEN / api.github.com(CI-only)
40  scripts/ci/live_comment.py:153      同上
41  scripts/ci/live_comment.py:264      同上
42  scripts/ci/live_comment.py:335      同上
43  scripts/ci/publish_e2e_evidence.py:68   同上
44  scripts/ci/publish_e2e_evidence.py:218  同上

═══ 走了安全封装的 5 处 ═══════════════════════════════════════════ 安全 ═══
    providers/base.py:232                所有 provider 的默认 fetch_models
    plugins/model-providers/anthropic/__init__.py:32  x-api-key
    hermes_cli/azure_detect.py:163 / :274
    hermes_cli/models.py:41              models.py 的目录抓取统一出口(11 处经它)
    另:plugins/model-providers/custom/__init__.py:81 base_url 完全由用户配置,
        但它 super().fetch_models(...) 回到基类 → 间接走封装。判为安全。

═══ 判为"无凭据"的 60 处 ═══════════════════════════════════════════════════
  判定依据(三条同时成立才判无凭据):
   (a) AST 在外层函数体内枚举到的 header 名只有 Accept / Content-Type /
       User-Agent / Accept-Language / X-* 非凭据头;
   (b) 该函数没有 headers 形参(或有,但全部调用方已逐个查过,见 §1.3 的六个 helper);
   (c) URL 里没有 §1.3 第四条扫出的 key/token query 参数。
  典型:blockchain / drug-discovery / arxiv / polymarket / maps / unbroker 等公开
  API 客户端;localhost 探活(browser_connect.py:173、web_server.py:1664、
  tui_gateway/server.py:13784、mem0/_setup.py 的 4 处 Ollama 探测);
  paste 上传(debug.py 的 3 处);managed-node 下载(hermes_constants.py:399/414)。
```

## 1.5 三个比移交锚点更重的发现

### ■ 发现 1:`gateway/relay/media.py:174` —— 子串门禁 + 入站事件 URL + 网关 bearer

这是本次普查里唯一一处**攻击者不需要任何本地权限**的凭据外泄原语。

门禁函数只有一行,判的是"URL 里有没有 `/relay/media/` 这个子串",**不是 origin 比对**:

`gateway/relay/media.py:92-94` @ 863e313

```python
    def is_relay_media_url(self, url: str) -> bool:
        """Is ``url`` a connector re-host reference (needs our bearer to GET)?"""
        return "/relay/media/" in (url or "")
```

下载路径据此决定要不要挂上网关的 per-gateway bearer,然后**裸 `urlopen`**:

`gateway/relay/media.py:162-174` @ 863e313

```python
        if not url:
            return None
        needs_auth = self.is_relay_media_url(url)
        if needs_auth and not self.enabled:
            return None
        headers = {}
        if needs_auth:
            headers["Authorization"] = f"Bearer {self._bearer()}"

        def _get() -> Optional[str]:
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_S) as resp:
```

而 `url` 来自入站事件的 `media_urls` —— 也就是从 relay 连接对面送过来的数据:

`gateway/relay/adapter.py:461-474` @ 863e313

```python
            urls = list(getattr(event, "media_urls", None) or [])
            if not urls:
                return
            client = self._get_media_client()
            localized: list[str] = []
            for url in urls:
                if not isinstance(url, str) or not url:
                    continue
                if client is None:
                    # No authenticated client: keep public URLs, drop re-hosts.
                    if "/relay/media/" not in url:
                        localized.append(url)
                    continue
                path = await client.download(url)
```

**攻击走法**:任何能让一条入站事件的 `media_urls` 里出现
`https://attacker.tld/relay/media/x` 的位置(被攻陷或恶意的 connector、任何能注入该字段的
上游平台适配器),都会让本网关**主动**把 `make_upgrade_token(gateway_id, secret)`
以 `Authorization: Bearer` 发到 `attacker.tld`。不需要重定向、不需要本地文件写权限。
拿到该 token 即可冒充本网关向 connector 建立 relay 升级连接。

对照 §1.1 的封装:`url_origin()` 做的正是"scheme + host + 有效端口"三元组比对,
如果这一处用 `open_credentialed_url` 或先做 origin 比对,该原语不成立。

### ◇ 发现 2:同一个基类,一个覆写走封装、一个覆写丢了封装

基类 `providers/base.py` 的默认 `fetch_models` 明确走封装:

`providers/base.py:218-232` @ 863e313

```python
        from hermes_cli.urllib_security import open_credentialed_url

        req = urllib.request.Request(url)
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Accept", "application/json")
        # Some providers (e.g. OpenCode Zen) sit behind a WAF that blocks
        # the default ``Python-urllib/<ver>`` User-Agent.  Set a generic
        # hermes-cli UA so the catalog endpoint is reachable.
        req.add_header("User-Agent", _profile_user_agent())
        for k, v in self.default_headers.items():
            req.add_header(k, v)

        try:
            with open_credentialed_url(req, timeout=timeout) as resp:
```

`custom` 覆写只加了一个"base_url 为空就别发"的前置判断,然后回到基类——**安全属性被继承**:

`plugins/model-providers/custom/__init__.py:77-81` @ 863e313

```python
    ) -> list[str] | None:
        """Custom/Ollama: base_url is user-configured; fetch if set."""
        if not (base_url or self.base_url):
            return None
        return super().fetch_models(api_key=api_key, base_url=base_url, timeout=timeout)
```

`actual` 覆写则整段重写,`ACTUAL_BASE_URL` 环境变量优先,`Authorization: Bearer` 手工挂上,
最后是裸 `urlopen`——**安全属性被静默丢弃**:

`plugins/model-providers/actual/__init__.py:52-66` @ 863e313

```python
        base_url = _normalize_actual_base_url(
            os.getenv("ACTUAL_BASE_URL", "").strip() or base_url or self.base_url
        )
        if not base_url:
            return None

        req = urllib.request.Request(base_url + "/models")
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", _profile_user_agent())

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
```

八个 `plugins/model-providers/*` 覆写 `fetch_models`,只有 `actual` 与 `anthropic` 真正发网络请求
(其余 6 个 `bedrock` / `copilot-acp` / `copilot`? 见下方 verify:它们的覆写体内根本没有 HTTP 出口),
而这两个里一个走封装、一个不走:

```verify
cd /home/user/hermes-agent && for f in actual anthropic bedrock copilot-acp custom kimi-coding openrouter vertex; do printf '%-14s ' "$f"; git grep -c "urlopen(\|open_credentialed_url(" -- "plugins/model-providers/$f/__init__.py" | awk -F: '{printf "http-out=%s ", $NF}'; git grep -c "super().fetch_models" -- "plugins/model-providers/$f/__init__.py" | awk -F: '{printf "super=%s", $NF}'; echo; done 2>/dev/null; echo "(空白 = 0)"
```

```console
actual         http-out=1 
anthropic      http-out=1 
bedrock        
copilot-acp    
custom         super=1
kimi-coding    
openrouter     
vertex         
(空白 = 0)
```

**这是"库函数式安全"的固有代价**:封装不是通道,继承者只要重写方法就能把它丢掉,
而且丢掉的过程没有任何提示。§1.6 的可迁移结论正是从这里来的。

### ◇ 发现 3:全仓有**三套**互不相干的重定向硬化实现

除了 `hermes_cli/urllib_security.py`,另外两处各自又写了一遍:

`agent/outbound_webhooks.py:504-517` @ 863e313

```python
class _NoRedirectHandler(urlrequest.HTTPRedirectHandler):
    """Refuse to follow redirects.

    urllib's default handler converts a redirected POST into a body-less
    GET — the signed payload would be silently dropped and the headers
    re-sent to a location the user never configured.  Treat any 3xx as a
    delivery failure instead (surfaced as HTTPError by returning None).
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


_opener = urlrequest.build_opener(_NoRedirectHandler)
```

`skills/creative/comfyui/scripts/_common.py:587-599` @ 863e313

```python
        def redirect_request(self, req2, fp, code, msg, hdrs, newurl):
            if not self.follow:
                return None
            new_host = (urlparse(newurl).hostname or "").lower()
            if new_host != self.original_host:
                # Build a new request with cleaned headers
                clean_headers = {
                    k: v for k, v in req2.header_items()
                    if k.lower() not in {"x-api-key", "authorization", "cookie"}
                }
                new_req = urllib.request.Request(newurl, headers=clean_headers, method="GET")
                return new_req
            return super().redirect_request(req2, fp, code, msg, hdrs, newurl)
```

三套的策略各不相同:`urllib_security` 是**跨源剥非白名单头**(允许跟随),
`outbound_webhooks` 是**一律不跟随**,comfyui 是**跨主机剥三个硬编码头名**
(`x-api-key`/`authorization`/`cookie`)——正是 `urllib_security.py:11-14` 注释里
明确否掉的"猜凭据头名字"做法。三者对"同主机不同端口"的判定也不同:
`urllib_security.url_origin` 把端口算进 origin,comfyui 只比 hostname。

## 1.6 仓库自己的行为规格:封装确实在网线上剥头

这不是我推断的,仓库有 4 个用例直接断言"网线上看不到那个头":

```verify
cd /home/user/hermes-agent && grep -n "def test_" tests/hermes_cli/test_urllib_security.py
```

```console
102:    def test_cross_host_redirect_drops_arbitrary_credentials_on_wire(self):
132:    def test_same_host_different_port_drops_credentials_on_wire(self):
181:    def test_explicit_opener_factory_is_instrumentable_without_security_bypass(self):
214:    def test_installed_request_processor_cannot_resurrect_cross_origin_secret(self):
```

`test_same_host_different_port_...` 这一条尤其值得记:**同主机不同端口也算跨源**,
这正是 comfyui 那套实现漏掉的。

## 1.7 结论:H-R8D-e **关闭并加重**

- 移交项的个例**属实、行号无漂移**,但它的严重度**低于移交项原文的暗示**:`base_url` 与
  `api_key` 同信任域,残余风险主要是重定向。
- 普查把"还有多少带凭据"这个问题答完了:**99 个非测试裸 `urlopen` 里 44 个带凭据**,
  其中 **21 个 URL 可控**(C 档 3 + B 档 18),**23 个 URL 硬编码**(仅重定向暴露)。
  走封装的只有 **5 个**。
- **加重的理由**是发现 1:`gateway/relay/media.py:174` 的门禁是子串判断、URL 来自入站事件、
  凭据是网关身份令牌,构成**无需本地权限的凭据外泄原语**——比移交锚点严重一个量级。
- 记号:■ `gateway/relay/media.py:94` 子串门禁;◇ `plugins/model-providers/actual/__init__.py:65`
  覆写丢封装;◇ 三套并行的重定向硬化实现。

**向后续轮移交**(带锚点 + 一句话现象):

- **H-R9A-a**:`gateway/relay/media.py:94` —— `is_relay_media_url` 用
  `"/relay/media/" in url` 做门禁,`media.py:174` 据此给**任意主机**挂上网关 bearer,
  URL 来自 `gateway/relay/adapter.py:461` 的入站 `event.media_urls`。需确认 connector
  侧是否另有约束(本轮只看了 Python 侧,connector 是 TS 实现,不在本仓库)。
- **H-R9A-b**:`optional-skills/research/osint-investigation/scripts/fetch_courtlistener.py:101` ——
  `next_url = payload.get("next")` 把服务器响应里的 URL 直接喂给带 `Authorization` 头的
  `_http.get()`,翻页循环内头不变;`fetch_senate_ld.py:107` 同形。
- **H-R9A-c**:`plugins/model-providers/actual/__init__.py:65` —— 覆写 `fetch_models` 时
  丢掉了基类 `providers/base.py:232` 的 `open_credentialed_url`;需要一条"覆写必须保留
  封装"的机制(而不是靠人记得),否则每个新 provider 插件都是一次重来。

---

# 普查二:H-R8D-f —— 挂在 `PYTEST_CURRENT_TEST` 上的安全判断

移交项原文:

> **H-R8D-f**(移交 R9):锚点 `hermes_cli/managed_scope.py:49` 的 `PYTEST_CURRENT_TEST`——
> 全仓还有多少**安全判断**挂在这个环境变量上,上一轮**未取证**。
> (上一轮已判定:这个个例是**写明了意图的测试接缝**,不是疏忽,但仍记 ■,
>  归类为「测试接缝具备生产后果」。)

## 2.1 复核个例:`hermes_cli/managed_scope.py:49`(行号无漂移)

移交项给的行号**准确**。函数与它的 docstring:

`hermes_cli/managed_scope.py:41-49` @ 863e313

```python
def _under_pytest() -> bool:
    """True when running inside the test suite.

    Used to ignore the system default ``/etc/hermes`` during tests so a real
    managed scope on a developer/CI box can't leak policy into the suite. Tests
    that exercise managed scope set ``HERMES_MANAGED_DIR`` explicitly, which is
    still honored (the override path below runs before this guard takes effect).
    """
    return "PYTEST_CURRENT_TEST" in os.environ
```

它在解析链里的位置——`HERMES_MANAGED_DIR` 覆盖先跑,然后这个守卫**吃掉 `/etc/hermes` 这一档**:

`hermes_cli/managed_scope.py:52-71` @ 863e313

```python
def get_managed_dir() -> Optional[Path]:
    """Resolve the managed-scope directory, or None when no scope is present.

    Resolution (highest priority first):
      1. ``$HERMES_MANAGED_DIR`` — deployment/bootstrap path override (IT-only;
         never persisted to any .env). Honored only when set to a non-empty value
         AND the directory exists.
      2. ``/etc/hermes`` — POSIX default, when it exists. Ignored under pytest so
         a real system managed scope can't leak into the test suite.

    A non-existent directory at either tier resolves to None (no managed scope),
    which is the common case and must be cheap + side-effect-free.
    """
    override = os.environ.get("HERMES_MANAGED_DIR", "").strip()
    if override:
        p = Path(override)
        return p if p.is_dir() else None
    if _under_pytest():
        return None
    return _DEFAULT_MANAGED_DIR if _DEFAULT_MANAGED_DIR.is_dir() else None
```

**攻击者若能设置这个环境变量会得到什么?** 完整答案是"managed scope 这一整层消失",
而这一层不是某个孤立开关,它是**全局配置叠加层**。三条后果,逐条取证:

**(a) 管理员钉住的任何配置键不再生效。** `apply_managed_overlay` 被套在配置加载的所有入口上
(CLI、gateway、cron):

```verify
cd /home/user/hermes-agent && git grep -n "apply_managed_overlay" -- '*.py' ':!tests/' | cat
```

```console
cli.py:634:    defaults = managed_scope.apply_managed_overlay(defaults)
cron/jobs.py:1159:            cfg = managed_scope.apply_managed_overlay(cfg)
cron/scheduler.py:3230:                    _cfg = managed_scope.apply_managed_overlay(_cfg)
gateway/config.py:1290:            yaml_cfg = managed_scope.apply_managed_overlay(yaml_cfg)
gateway/run.py:1880:            cfg = managed_scope.apply_managed_overlay(cfg)
gateway/run.py:2054:            _cfg = managed_scope.apply_managed_overlay(_cfg)
gateway/run.py:3188:        raw = managed_scope.apply_managed_overlay(raw if isinstance(raw, dict) else {})
gateway/run.py:8442:                cfg = managed_scope.apply_managed_overlay(cfg)
```

`load_managed_config()` 一旦拿到 `None` 就返回 `{}`,叠加层变成空操作:

`hermes_cli/managed_scope.py:115-125` @ 863e313

```python
def load_managed_config() -> dict:
    """Parsed managed config.yaml, or {} when absent/malformed (fail-open)."""
    managed_dir = get_managed_dir()
    if managed_dir is None:
        return {}
    parsed = _cached_read(
        managed_dir / "config.yaml",
        _CONFIG_CACHE,
        lambda f: yaml.safe_load(f) or {},
    )
    return parsed if isinstance(parsed, dict) else {}
```

**(b) 用户写配置时不再被拦。** 批量保存原本会剥掉管理员钉住的叶子键:

`hermes_cli/config.py:3530-3545` @ 863e313

```python
        # Managed scope: strip any leaf the managed layer pins, so a bulk write
        # (wizard / programmatic save) never persists a user value that would
        # silently lose to managed on the next load. Single-key `config set`
        # hard-rejects (see set_config_value); this is the mechanical safety net
        # for bulk writes so the unmanaged remainder still lands.
        from hermes_cli import managed_scope

        managed_keys = managed_scope.managed_config_keys()
        if managed_keys:
            config, _stripped = _strip_dotted_keys(copy.deepcopy(config), managed_keys)
            if _stripped:
                print(
                    f"Note: {len(_stripped)} managed setting(s) were not saved "
                    f"(managed by your administrator): {', '.join(sorted(_stripped))}",
                    file=sys.stderr,
                )
```

**(c) 管理员钉住的环境变量可以被用户覆写。** `is_env_managed` 直接建立在 `load_managed_env()` 上,
后者同样返回 `{}`:

`hermes_cli/managed_scope.py:212-214` @ 863e313

```python
def is_env_managed(name: str) -> bool:
    """True if the env var name is pinned by the managed .env layer."""
    return name in load_managed_env()
```

`hermes_cli/config.py:3870-3882` @ 863e313

```python
    # Managed scope guard: a managed env key can't be set by the user — the
    # managed .env wins at load anyway. Distinct from is_managed() above.
    from hermes_cli import managed_scope

    if managed_scope.is_env_managed(key):
        managed_dir = managed_scope.get_managed_dir()
        src = (managed_dir / ".env") if managed_dir else "the managed scope"
        print(
            f"Cannot set {key}: it is managed by your administrator ({src}) "
            f"and cannot be changed.",
            file=sys.stderr,
        )
        return
```

**净结论**:在一台部署了 `/etc/hermes` 的机器上,**任何能给 hermes 进程设一个环境变量的位置**
(shell 环境、systemd unit 的 `Environment=`、`~/.hermes/.env`、父进程),把
`PYTEST_CURRENT_TEST` 设成任意非空值,就能**整体关闭 IT 推送的不可变策略层**。
这确实是"写明了意图的测试接缝",但它的生产后果是**移除一个安全控制**,不是延长一个超时——
上一轮记 ■ 并归类为「测试接缝具备生产后果」是准确的,本轮的补充是把"后果"具体化到上面三条。

**一处值得记的设计反差**:`urllib_security.open_credentialed_url` 的测试接缝是
**显式形参 `opener_factory`**,注释里明确写了"security is never disabled based on global
`urlopen` identity"(§1.1 代码块)。同一个仓库里,两种测试接缝的设计取向正好相反。

## 2.2 「同类惯用法」清单怎么定的

一个 Python 进程要判断"我是不是在测试里跑",可用的信号面是**有限且可枚举**的。
把它们全列出来,再逐个搜,才能支撑"没有别的"这条否定:

```text
信号族                       为什么它属于这一类                          搜法
─────────────────────────────────────────────────────────────────────────────
1 PYTEST_CURRENT_TEST        pytest 每个用例前后写/删的环境变量,是      字面量
                             "现在正在跑某个用例"的唯一官方信号
2 pytest 的其它环境变量       PYTEST_ADDOPTS / PYTEST_VERSION /          字面量
                             PYTEST_XDIST_WORKER / PYTEST_DISABLE_
                             PLUGIN_AUTOLOAD——同一族,进程级而非用例级
3 sys.modules 探测            "pytest 被 import 了吗"——不依赖环境变量,   正则
                             是环境变量之外唯一进程内可靠信号;
                             unittest 同理
4 sys.argv 嗅探               "命令行是不是 pytest"——最粗糙的一种         正则
5 项目自有测试开关            HERMES_*TEST* / *_TESTING / *TEST_MODE /   环境变量名
                             *ALLOW_TEST* / MOCK / FAKE / STUB / E2E     全量枚举
6 CI 环境探测                 CI / GITHUB_ACTIONS——"自动化环境"是         字面量
                             "测试态"的近邻,常被同样用来改行为
7 配置里的 testing 布尔        config.get("testing") 一类               正则
```

**为什么是这七族、没有第八族**:一个进程能知道的东西只有三处来源——环境变量(1、2、5、6)、
进程内解释器状态(3、4)、自己的配置文件(7)。这三处已被穷举。剩下的理论可能性是
"探测调用栈里有没有 pytest 帧",属于同族 3 的变体,用同一条正则(含 `pytest` 字面量)覆盖。

## 2.3 搜索面

**语料**:`git grep`(已跟踪文件),非测试代码 = 排除 `tests/` 与 `*/tests/`。
第 1 族**不排除任何路径**(先看全仓,再分测试/非测试),因为要报"全仓多少处"。

```verify
cd /home/user/hermes-agent && git grep -c "PYTEST_CURRENT_TEST" -- . | cat
```

```console
agent/credential_pool.py:1
cli.py:1
gateway/run.py:1
hermes_cli/_early_recovery.py:2
hermes_cli/auth.py:5
hermes_cli/main.py:1
hermes_cli/managed_scope.py:1
tests/cli/test_exit_watchdog_signal_arm.py:1
tests/hermes_cli/test_config_loader_e2e.py:1
tests/hermes_cli/test_checkout_mutation_guards.py:2
```

全仓 16 行、10 个文件;非测试 12 行、7 个文件。12 行里 2 行是注释/docstring
(`hermes_cli/_early_recovery.py:179`、`hermes_cli/auth.py:1006`),**实际判断点 10 处**。

第 2、3、4、6、7 族——**全部零命中**,命令与输出如下(这是本节所有否定结论的全部依据):

```verify
cd /home/user/hermes-agent
echo "--- 族2 pytest 其它环境变量 ---"
git grep -nE "PYTEST_ADDOPTS|PYTEST_VERSION|PYTEST_XDIST|PYTEST_DISABLE_PLUGIN_AUTOLOAD" -- '*.py' ':!tests/' ':!*/tests/*'
echo "--- 族3 sys.modules 探测 ---"
git grep -nE "sys\.modules.*(pytest|unittest)|(\"|')pytest(\"|').*sys\.modules" -- '*.py' ':!tests/' ':!*/tests/*'
echo "--- 族4 sys.argv 嗅探 ---"
git grep -nE "sys\.argv.*pytest|pytest.*sys\.argv" -- '*.py' ':!tests/' ':!*/tests/*'
echo "--- 族6 CI 探测 ---"
git grep -nE "environ(\.get\(|\[)\s*[\"']CI[\"']|getenv\(\s*[\"']CI[\"']" -- '*.py' ':!tests/' ':!*/tests/*'
echo "--- 族7 testing 布尔配置键 ---"
git grep -nE "config\.get\(\s*[\"'](testing|test_mode|is_test)[\"']" -- '*.py' ':!tests/' ':!*/tests/*'
echo "--- 以上五族命中数 ---"
```

```console
--- 族2 pytest 其它环境变量 ---
--- 族3 sys.modules 探测 ---
--- 族4 sys.argv 嗅探 ---
--- 族6 CI 探测 ---
--- 族7 testing 布尔配置键 ---
--- 以上五族命中数 ---
```

第 5 族(项目自有测试开关)用的是**枚举而不是猜关键词**:把非测试代码里**所有**
`os.getenv(...)` / `os.environ.get(...)` / `os.environ[...]` / `os.environ.setdefault(...)`
的**字面量变量名**抽出来去重,再过一遍测试语义的词表。这样不会因为想不到某个名字而漏掉:

```verify
cd /home/user/hermes-agent && git grep -noE "(getenv|environ\.get|environ\.setdefault)\(\s*[\"'][A-Za-z0-9_]+[\"']|environ\[\s*[\"'][A-Za-z0-9_]+[\"']" -- '*.py' ':!tests/' ':!*/tests/*' | sed -E "s/.*[\"']([A-Za-z0-9_]+)[\"'].*/\1/" | sort -u | grep -iE "test|mock|fake|stub|e2e|dummy|seam|pytest|unittest"
```

```console
HERMES_DDGS_ALLOW_TEST_HOOKS
HERMES_TEST_FILE_RETRIES
HERMES_TEST_FILE_TIMEOUT
HERMES_TEST_PATHS
HERMES_TEST_SLICE
HERMES_TEST_WORKERS
MATRIX_E2EE_MODE
PYTEST_CURRENT_TEST
```

(`MATRIX_E2EE_MODE` 是 Matrix 端到端**加密**,被 `e2e` 误命中,不是测试开关——
写出来是因为按"shell 命令即证据"的规矩,命令输出必须与结论一致,不能悄悄删行。)

`HERMES_TEST_{WORKERS,PATHS,SLICE,FILE_TIMEOUT,FILE_RETRIES}` 五个只被
`scripts/run_tests_parallel.py` 与 `scripts/run_tests.sh` 读——它们是**测试运行器自己的参数**,
不改被测代码的任何行为:

```verify
cd /home/user/hermes-agent && git grep -l "HERMES_TEST_WORKERS\|HERMES_TEST_SLICE\|HERMES_TEST_FILE_TIMEOUT\|HERMES_TEST_FILE_RETRIES\|HERMES_TEST_PATHS" -- . ':!tests/'
```

```console
scripts/run_tests.sh
scripts/run_tests_parallel.py
```

`HERMES_DDGS_ALLOW_TEST_HOOKS` 是唯一一个"改被测代码行为"的项目自有测试开关,单独判定见 §2.4。

## 2.4 判定表

```text
═══ 安全相关(改掉的行为落在审批/沙箱/凭据/网络/文件写入上)═══════ 6 处 ═══

■ 移除安全控制(方向:fail-OPEN)————————————————————————————— 1 处
 1  hermes_cli/managed_scope.py:49   _under_pytest()
    改掉:get_managed_dir() 不再返回 /etc/hermes → 管理员钉住的配置键与
          环境变量整层失效,用户值重新获胜(§2.1 三条后果已取证)
    方向:fail-open —— 设了变量 = 少一层控制

◻ 保护凭据(方向:fail-CLOSED,设了变量只会更保守)—————————————— 5 处
 2  hermes_cli/auth.py:1007          _auth_file_path()
    改掉:HERMES_HOME 解析到真实 ~/.hermes/auth.json 时 raise RuntimeError
 3  hermes_cli/auth.py:1072          _load_global_auth_store()
    改掉:全局 auth store 指向真实 HOME 时返回 {} 而不是读
 4  hermes_cli/auth.py:4552          xAI OAuth 刷新的 write-through
    改掉:目标是真实 HOME 的 auth.json 时直接 return,不写
 5  agent/credential_pool.py:609     凭据池刷新路径的同一个 write-through
    改掉:同上(注释里写明"mirrors the read-side guard")
 6  hermes_cli/auth.py:5283          _nous_shared_store_path()
    改掉:共享 Nous store 指向真实根时 raise RuntimeError
    —— 这 5 处若在生产被设上,后果是 hermes 读不到/写不回自己的凭据库
       (DoS / 反复要求重新登录),不是凭据外泄。方向正确。

═══ 非安全相关(测试便利:看门狗、重装、超时)══════════════════ 4 处 ═══
 7  cli.py:1095                      退出看门狗不上膛(否则 30s 后 os._exit(0)
                                     会打死测试 worker)——可用性
 8  gateway/run.py:12774             关停看门狗不上膛——可用性
 9  hermes_cli/main.py:7690          _pytest_owns_live_checkout():**合取**
                                     root == 本 checkout 才成立 → 抑制恢复面包屑
10  hermes_cli/_early_recovery.py:185 同形合取 → 抑制真实的
                                     ensurepip + pip install --force-reinstall
    —— 9/10 两处是合取判断,单设环境变量拿不到任何东西;且它们**抑制**的是
       修复动作,后果是"不自愈",仍属可用性

═══ 项目自有测试开关的唯一"改行为"者:判为非安全相关 ═══════════════════
    plugins/web/ddgs/_search_worker.py:89  HERMES_DDGS_ALLOW_TEST_HOOKS
    理由三条(default-deny 的教科书写法,与上面第 1 处形成对照):
      (a) 双重门禁:环境变量 == "1" **且** 请求体里带 test_hook 字段;
      (b) 默认拒绝:变量未设 → 直接回 {"ok": false, "error": "test_hook refused"};
      (c) 载荷惰性:hook 只有 sleep / gil / success / error / empty,不碰
          文件、网络、凭据;
    且父进程只在自己要用 hook 时才把变量塞进子进程环境(provider.py:163),
    不是常开。
```

三处判定的取证:

`plugins/web/ddgs/_search_worker.py:87-96` @ 863e313

```python
    hook = request.get("test_hook")
    if hook:
        if os.environ.get("HERMES_DDGS_ALLOW_TEST_HOOKS") != "1":
            _write_envelope(
                {"ok": False, "error": "test_hook refused (hooks not enabled)"}
            )
            return 3
        envelope = _run_test_hook(str(hook))
        _write_envelope(envelope)
        return 0 if envelope.get("ok") else 1
```

`plugins/web/ddgs/provider.py:155-163` @ 863e313

```python
    request: dict[str, Any] = {"query": query, "safe_limit": safe_limit}
    if _test_hook:
        request["test_hook"] = _test_hook

    from tools.environments.local import _sanitize_subprocess_env

    env = _sanitize_subprocess_env(dict(os.environ))
    if _test_hook:
        env["HERMES_DDGS_ALLOW_TEST_HOOKS"] = "1"
```

两处"合取"守卫的取证(说明单设环境变量拿不到东西):

`hermes_cli/main.py:7679-7692` @ 863e313

```python
def _pytest_owns_live_checkout(root: Path) -> bool:
    """True when running under pytest AND ``root`` is this checkout itself.

    Tests that drive update/recovery without sandboxing ``PROJECT_ROOT``
    must neither litter the live repo root with recovery breadcrumbs
    (a leftover ``.lazy-refresh-incomplete`` / ``.update-incomplete``
    false-arms recovery on the developer's next real launch) nor run a real
    reinstall against the executing venv. Sandboxed tests point at a
    tmp_path and are unaffected (same posture as
    ``managed_scope._under_pytest``)."""
    return (
        "PYTEST_CURRENT_TEST" in os.environ
        and root == Path(__file__).resolve().parent.parent
    )
```

`hermes_cli/_early_recovery.py:174-187` @ 863e313

```python
def _pytest_owns_live_checkout(root: Path) -> bool:
    """True when running under pytest AND ``root`` is this module's own
    checkout — the one whose venv is executing the suite right now.

    Lifecycle tests spawn real subprocesses that import ``hermes_cli.main``
    with recovery armed; ``PYTEST_CURRENT_TEST`` rides the inherited env into
    those children. Without this guard, a genuinely-broken dev venv gets a
    REAL ``ensurepip`` + ``pip install --force-reinstall`` from inside a
    running test suite. Tests that sandbox ``project_root`` to a tmp_path are
    unaffected (same posture as ``managed_scope._under_pytest``)."""
    return (
        "PYTEST_CURRENT_TEST" in os.environ
        and root == Path(__file__).resolve().parent.parent
    )
```

一处 fail-closed 守卫的取证(五处同形,取最有代表性的一处):

`hermes_cli/auth.py:1000-1016` @ 863e313

```python
def _auth_file_path() -> Path:
    path = get_hermes_home() / "auth.json"
    # Seat belt: if pytest is running and HERMES_HOME resolves to the real
    # user's auth store, refuse rather than silently corrupt it. This catches
    # tests that forgot to monkeypatch HERMES_HOME, tests invoked without the
    # hermetic conftest, or sandbox escapes via threads/subprocesses. In
    # production (no PYTEST_CURRENT_TEST) this is a single dict lookup.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        real_home_auth = (Path.home() / ".hermes" / "auth.json").resolve(strict=False)
        try:
            resolved = path.resolve(strict=False)
        except Exception:
            resolved = path
        if resolved == real_home_auth:
            raise RuntimeError(
                f"Refusing to touch real user auth store during test run: {path}. "
                "Set HERMES_HOME to a tmp_path in your test fixture, or run "
```

## 2.5 结论:H-R8D-f **关闭**(结论收窄,不加重)

- 移交项的个例**属实、行号无漂移**,上一轮"写明了意图的测试接缝,但具备生产后果"的定性**成立**;
  本轮把"生产后果"具体化为三条(配置叠加层失效 / 批量写配置不再被剥 / 管理员钉住的 env 可被覆写)。
- "全仓还有多少安全判断挂在这个变量上"这个问题答完了:**非测试代码 10 处判断点**,
  其中**安全相关 6 处**,但 6 处里 **5 处方向是 fail-closed**(设了变量只会更保守),
  **只有 `managed_scope.py:49` 一处是 fail-open**——也就是移交项已经点到的那一处。
- 同类惯用法**七族全部搜过**:族 2/3/4/6/7 **零命中**;族 5 枚举出 6 个项目自有开关,
  5 个是测试运行器参数、1 个(`HERMES_DDGS_ALLOW_TEST_HOOKS`)是 default-deny 的正面样板。
- 所以**不加重**:上一轮的个例就是这一类里唯一的 fail-open 点,不存在"还有一批没发现的"。
- 记号:■ `hermes_cli/managed_scope.py:49`(维持上一轮判定,不新增)。

**向后续轮移交**(带锚点 + 一句话现象):

- **H-R9A-d**:`hermes_cli/managed_scope.py:49` —— `_under_pytest()` 只看
  `"PYTEST_CURRENT_TEST" in os.environ`,而 `hermes_cli/config.py:3874` 的
  `is_env_managed()` 和 `hermes_cli/config.py:3537` 的 `managed_config_keys()` 都建立在它之上;
  需要评估的是"这一层是否应当改用 `sys.modules` 里有没有 `_pytest` 之类**不可由外部环境伪造**
  的信号",本轮只取证、未评估替代方案的代价。

---

# 3. 跨轮可比的数(下一轮可直接复算)

```text
普查一 H-R8D-e ────────────────────────────────────────────────
  语料                              git grep,已跟踪文件
  urlopen 出现行(全仓,含文档)      354
  urlopen( 调用行(.py,含测试)       160
  urlopen( 调用行(.py,非测试)       100   (减 1 注释行 + 1 def 行 = 99 真实调用点)
  Request( 构造点(.py,非测试)       112
  安全封装调用点(非测试)              5   (git grep -c 得 6,含 1 个 def 行)
  非测试 HTTP 出口合计                104   分布在 66 个文件
  ├─ 带凭据                            44
  │   ├─ C 档 URL 由运行时数据控制       3   ← 新发现,最重
  │   ├─ B 档 URL 由配置/环境控制       18   ← 含移交项锚点
  │   └─ A 档 URL 硬编码/白名单         23   (仅重定向暴露)
  └─ 无凭据                            60
  走封装的 5 处全部安全;custom provider 经 super() 间接走封装,判安全
  另存在 3 套互不相干的重定向硬化实现

普查二 H-R8D-f ────────────────────────────────────────────────
  PYTEST_CURRENT_TEST 命中行(全仓)     16   分布在 10 个文件
  ├─ 测试代码                            4   (3 个文件)
  └─ 非测试代码                         12   (7 个文件)
      └─ 去掉 2 行注释/docstring        10   ← 实际判断点
          ├─ 安全相关                    6
          │   ├─ fail-OPEN(移除控制)    1   ← managed_scope.py:49,即移交项锚点
          │   └─ fail-CLOSED(保护凭据)  5
          └─ 非安全相关(可用性)         4
  同类惯用法七族:族 2/3/4/6/7 命中 0;族 5 命中 6(5 个测试运行器参数
  + 1 个 default-deny 的 DDGS hook,判非安全相关)
```

**本轮新开的移交项**:H-R9A-a / H-R9A-b / H-R9A-c(普查一)、H-R9A-d(普查二),
四条都已在各自小节末尾给出锚点文件 + 一句话现象。
