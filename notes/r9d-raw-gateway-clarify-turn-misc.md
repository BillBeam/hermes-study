# r9d-F · 工具网关、澄清与回合杂项

> **溯源约定**:凡对代码的断言,锚点单独成行写在代码块之前,格式 `路径:行号 @ 863e313`,
> 路径从基线仓库根 `/home/user/hermes-agent` 解析。围栏块为逐字源码摘录;
> ```text / ```console / ```verify 为作者声明的非源码内容(命令、实验输出、示意)。
> **断言强度**分三档,每条findings里标注:**实跑复现**(本轮真跑出来的)、
> **静态对读**(读两处代码推出来的)、**推定未取证**(没验证,列在第 5 节)。

**本片文件清单(14 文件 / 3440 行,全部读完)**

| 路径 | 行数 | 组 |
|---|---|---|
| `tools/managed_tool_gateway.py` | 452 | (1) 工具网关 |
| `tools/tool_backend_helpers.py` | 311 | (1) 工具网关 |
| `tools/__init__.py` | 25 | (1) 工具网关 |
| `tools/clarify_gateway.py` | 459 | (2) 澄清机制 |
| `tools/clarify_tool.py` | 266 | (2) 澄清机制 |
| `agent/think_scrubber.py` | 396 | (3) 回合周边 |
| `agent/title_generator.py` | 402 | (3) 回合周边 |
| `tools/hook_output_spill.py` | 232 | (3) 回合周边 |
| `tools/thread_context.py` | 120 | (3) 回合周边 |
| `tools/budget_config.py` | 114 | (3) 回合周边 |
| `tools/debug_helpers.py` | 105 | (3) 回合周边 |
| `agent/replay_cleanup.py` | 323 | (4) 进程与清理 |
| `agent/process_bootstrap.py` | 227 | (4) 进程与清理 |
| `agent/__init__.py` | 8 | (4) 进程与清理 |

---

## 1. 这一片解决什么问题(先场景)

这 14 个文件不构成一个子系统,它们是**一次回合(turn)周围的一圈基础设施**。
把它们串起来的最好方式是走一遍一次消息网关回合的生命周期,看每个文件在哪一格插进来:

1. **进程刚起来** —— `agent/__init__.py` 一行 import 触发 jiter 原生扩展预加载;
   `agent/process_bootstrap.py` 把 `openai.OpenAI` 换成惰性代理(省 240ms 启动)、
   把 stdout/stderr 包成不会因断管而崩溃的写入器、解析 `HTTPS_PROXY`/`NO_PROXY`。
2. **恢复上一次没跑完的会话** —— `agent/replay_cleanup.py` 把持久化 transcript 里
   「悬空的 assistant(tool_calls)」和「被打断的 assistant→tool 块」清掉,
   否则模型看到未回答的工具调用会重新发起,`docker restart` 类工具会因此进入无限重启循环;
   同一个文件还负责让**过期的高危确认语**(“confirm shutdown”)失效。
3. **回合开始,构造 prompt** —— `tools/hook_output_spill.py` 把体积超标的 hook 注入上下文
   落盘、在 prompt 里换成 head/tail 预览,防止一个话痨插件把每一轮的前缀缓存全部打穿。
4. **模型开始流式输出** —— `agent/think_scrubber.py` 是一个**跨 delta 的状态机**,
   把 `<think>…</think>` 推理块从**外发给用户的每一个增量**里擦掉。
5. **模型调工具** —— `tools/budget_config.py` 决定单条工具结果 / 整回合工具输出的字符预算;
   `tools/thread_context.py` 把审批/sudo 回调与 ContextVar 传播进工具执行的 worker 线程
   (不传的话网关会话会掉进「非交互 → 自动批准」分支,危险命令无提示直接跑);
   `tools/debug_helpers.py` 是几个工具共用的调试日志壳。
6. **模型需要问用户** —— `tools/clarify_tool.py`(schema + 校验 + 转发)
   \+ `tools/clarify_gateway.py`(线程安全的阻塞队列原语)。这是本片最有意思的一块:
   **agent 跑在 worker 线程上、用户的回复走 event loop**,所以需要一个模块级的
   `threading.Event` 表来跨线程解锁。
7. **模型要用托管的第三方工具** —— `tools/managed_tool_gateway.py` 解析 Nous 工具网关的
   地址与 bearer、并提供大文件预签名上传协议;`tools/tool_backend_helpers.py` 决定
   「直连凭据 vs 托管网关」怎么选、凭据从哪读(多 profile 复用一个进程时这是个雷区)。
8. **回合结束** —— `agent/title_generator.py` 在守护线程里用首轮对话生成会话标题。

一句话概括这一片的主线:**它们都是「让一次回合在真实世界里不崩、不泄、不卡死」的胶水**,
而每一块胶水的设计取舍,都能从它注释里点名的那个 issue 编号倒推出当初是怎么被现实教育的。

---

## 2. 逐文件 / 逐机制精读

### 2.1 两个 `__init__.py`:一个刻意无副作用,一个专门为了副作用

这两个文件放在一起读才有意思:它们对「包 import 该不该有副作用」给出了**相反**的答案,
而且各自都写明了理由。

`tools/__init__.py` 的立场是「尽量什么都别做」。

tools/__init__.py:2 @ 863e313

> Tools package namespace.
>
> Keep package import side effects minimal. Importing ``tools`` should not
> eagerly import the full tool stack, because several subsystems load tools while
> ``hermes_cli.config`` is still initializing.

理由写得很具体:**有子系统在 `hermes_cli.config` 还没初始化完的时候就在加载工具**,
如果 `import tools` 会连带把整个工具栈拉起来,就会撞上循环导入。
所以它只导出一个函数,而且这个函数还是延迟 import 的:

tools/__init__.py:18 @ 863e313

```python
def check_file_requirements():
    """File tools only require terminal backend availability."""
    from .terminal_tool import check_terminal_requirements

    return check_terminal_requirements()
```

这个函数的语义本身也值得记一笔:**文件工具的可用性检查被定义为「终端后端可用性」的别名**。
换句话说 file 工具不是在本地直接 `open()`,而是走 terminal 后端所在的那个环境
(本地 / Docker / 远程),所以「文件工具能不能用」等价于「终端后端在不在」。
全仓唯一调用方是 `tools/file_tools.py:2156`。

`agent/__init__.py` 走的是完全相反的路子——它全部 8 行里,有价值的就是最后一行,
而这一行**就是为了它的 import 副作用**:

agent/__init__.py:8 @ 863e313

```python
from . import jiter_preload as _jiter_preload  # noqa: F401
```

被 import 的模块在文件末尾自调用:

agent/jiter_preload.py:39 @ 863e313

```python
preload_jiter_native_extension()
```

它解决的问题很窄但很典型:OpenAI SDK 在构造流式响应时会 import `jiter`(一个 Rust 写的
高速 JSON 解析器),在某些 Windows 安装上,这个原生扩展**第一次在流式请求的工作线程里
被 import 会失败**,但在主线程早期 import 就没事。于是把它提到 `agent` 包 import 时做掉。
`# noqa: F401` 是对 linter 说「我知道这个名字没被用,它就是为了副作用」。

**可迁移的设计原则**:包 `__init__` 有没有副作用不是风格问题,是**约束**问题——
`tools` 的约束是「会被半初始化的配置层拉起来」,`agent` 的约束是「有个原生扩展必须在主线程先加载」。
两个约束不同,结论就相反。把理由写进 docstring,是让后来者不会「统一风格」把其中一个改坏。

---

### 2.2 `tools/managed_tool_gateway.py` —— 托管工具怎么被代理出去

**场景**:用户没有 BFL(FLUX)的 API key,但买了 Nous 的订阅。他说「生成一段视频」。
Hermes 不去连 BFL,而是把请求发到 Nous 自己的网关,由网关代付、代调。
这个文件就是这条路径上的**寻址 + 鉴权 + 大文件上传**三件事。

#### 2.2.1 寻址:两套并存的地址方案

第一套是**每个 vendor 一个子域**:

tools/managed_tool_gateway.py:159 @ 863e313

```python
def build_vendor_gateway_url(vendor: str) -> str:
    """Return the gateway origin for a specific vendor."""
    vendor_key = f"{vendor.upper().replace('-', '_')}_GATEWAY_URL"
    explicit_vendor_url = os.getenv(vendor_key, "").strip().rstrip("/")
    if explicit_vendor_url:
        return explicit_vendor_url

    shared_scheme = get_tool_gateway_scheme()
    shared_domain = os.getenv("TOOL_GATEWAY_DOMAIN", "").strip().strip("/")
    if shared_domain:
        return f"{shared_scheme}://{vendor}-gateway.{shared_domain}"

    return f"{shared_scheme}://{vendor}-gateway.{_DEFAULT_TOOL_GATEWAY_DOMAIN}"
```

三层覆盖顺序:`{VENDOR}_GATEWAY_URL` 精确覆盖 → `TOOL_GATEWAY_DOMAIN` 换域 → 默认
`https://{vendor}-gateway.nousresearch.com`。注意 vendor 名里的 `-` 会被转成 `_`
再拼环境变量名(`fal-queue` → `FAL_QUEUE_GATEWAY_URL`)。

第二套是**一个共享 origin + 路径分 vendor**,用一个伪 vendor 名去复用上面那个 builder:

tools/managed_tool_gateway.py:236 @ 863e313

```python
_MANAGED_GATEWAY_VENDOR = "tool"
```

于是 `managed_vendor_endpoints("flux3")` 给出的是
`https://tool-gateway.nousresearch.com/api/flux3`,而
`build_vendor_gateway_url("flux3")` 给出的是 `https://flux3-gateway.nousresearch.com`。
**实跑复现**(见 §3.2 探针 `probe_gw.py`):

```console
    build('tool')  = https://tool-gateway.nousresearch.com
    build('flux3') = https://flux3-gateway.nousresearch.com
    endpoints('flux3') = {'origin': 'https://tool-gateway.nousresearch.com', 'base_url': 'https://tool-gateway.nousresearch.com/api/flux3', 'upload_path': '/api/uploads/flux3'}
```

两套并存的分工从调用方看得很清楚:老一批 vendor(`openai-audio` / `fal-queue` /
`modal` / `firecrawl` / `browser-use`)用 `resolve_managed_tool_gateway` 走子域方案;
新的 `flux3` 走 `managed_vendor_endpoints` 走路径方案。
**搜索面**:`git grep -n "resolve_managed_tool_gateway\|is_managed_tool_gateway_ready\|managed_vendor_endpoints" -- '*.py'`,
排除 `tests/`,得 `hermes_cli/setup.py`、`hermes_cli/nous_subscription.py`、
`tools/transcription_tools.py`、`tools/web_tools.py`、`tools/image_generation_tool.py`、
`tools/terminal_tool.py`、`tools/tts_tool.py`(子域方案)与 `tools/flux3_video_tool.py`(路径方案)。

代码里明确写了「为什么要把可用 vendor 钉死在源码里,而不是从远端拉目录」:

tools/managed_tool_gateway.py:222 @ 863e313

```python
# Vendors the gateway serves on its own origin (rather than on a
# `{vendor}-gateway` host) are pinned HERE, in code, the same way every other
# managed vendor's gateway URL is pinned: adding one is a Hermes release, and
# the exact URL a user's agent may connect to is reviewable in this file. A
# runtime discovery catalog was tried and deliberately removed — a remote
# endpoint that can add tools to every entitled install is a bigger trust
# surface than a code diff.
```

这是本片最值得学的一条设计取舍:**「一个能给所有已授权安装加工具的远程端点,
比一次代码 diff 是更大的信任面」**——所以宁可牺牲「加 vendor 不用发版」的便利。

#### 2.2.2 鉴权:两个 token 读取函数,分给两类调用方

`peek_nous_access_token()` 与 `read_nous_access_token()` 的区别是**要不要触发 OAuth 刷新**。
可用性扫描(`hermes tools` 列表、状态栏绘制、`is_available()` 检查)必须走 peek,
否则每次画一次界面就同步发一次刷新请求。真要发请求的路径走 read:

tools/managed_tool_gateway.py:124 @ 863e313

```python
    nous_provider = _read_nous_provider_state() or {}
    cached_token = peek_nous_access_token()

    if cached_token and not _access_token_is_expiring(
        nous_provider.get("expires_at"),
        _NOUS_ACCESS_TOKEN_REFRESH_SKEW_SECONDS,
    ):
        return cached_token
```

`_NOUS_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 120`,即**提前 2 分钟就当作要过期**。
另外 `_access_token_is_expiring` 在 `expires_at` 解析失败(缺字段 / 格式不认)时返回 `True`,
即**未知一律当作要刷新**——失败方向选的是「多刷一次」而不是「带着死 token 发出去」。

`is_managed_tool_gateway_ready()` 默认把 `token_reader` 换成 peek,
`resolve_managed_tool_gateway()` 默认用 read,这个默认值的分工就是上面那条规则的落地。

#### 2.2.3 信任边界:`is_managed_nous_gateway_url`

这是「哪些 URL 配拿到我们的 bearer / 配读本地文件去上传」的**唯一闸门**:

tools/managed_tool_gateway.py:291 @ 863e313

```python
    builder = gateway_builder or build_vendor_gateway_url
    try:
        expected = urlsplit(builder(_MANAGED_GATEWAY_VENDOR))
        actual = urlsplit(url.strip())
    except ValueError:
        return False

    return bool(actual.scheme) and (actual.scheme, actual.netloc) == (expected.scheme, expected.netloc)
```

**实跑复现**的行为矩阵(`probe_gw.py`):

```console
  'https://tool-gateway.nousresearch.com:8443/x'           -> False   # 端口不同 = 不同 origin,正确
  'https://TOOL-GATEWAY.nousresearch.com/x'                -> False   # 大小写不同 → 拒(见 ■-3)
  'https://tool-gateway.nousresearch.com.evil.example/x'   -> False   # 后缀攻击被挡住,正确
  '//tool-gateway.nousresearch.com/x'                      -> False   # 无 scheme → 拒,正确
  is_managed('https://flux3-gateway.nousresearch.com/x')   -> False   # 子域方案的 origin 不算 managed
```

最后一条要特别注意:**这个闸门只认 `tool` 这一个伪 vendor 的 origin**。
子域方案(`flux3-gateway.…`)的 origin 送进来一律 False,于是
`managed_gateway_auth_headers` 返回 `{}`。当前没有调用方这么用,但两套地址方案共存
+ 闸门只认其中一套,是个容易踩的形状。

#### 2.2.4 大文件上传:三步预签名协议

原来媒体参数是 base64 内联的,整个工具调用被网关的请求上限卡在约 2MB 真实字节、
视频完全没戏。现在改成:

1. `POST origin + upload_path`,带声明的 content type 与**精确字节长度**;
2. 网关回一个预签名的单对象 PUT URL(短过期,type 和 length 被签进去)+ 一个 token;
3. PUT 直接打到存储(**不经过网关**),工具参数里只填 `nous-upload:<token>`。

最值得学的是这里对**两个 http 客户端的刻意区分**:

tools/managed_tool_gateway.py:418 @ 863e313

```python
        presign_timeout = httpx.Timeout(_MEDIA_UPLOAD_PRESIGN_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=presign_timeout) as client:
            presign = await client.post(
                presign_url,
                headers=headers,
                json={"contentType": mime, "contentLength": len(data)},
            )
```

presign 用**普通 client**(不做 SSRF 防护),PUT 用 `create_ssrf_safe_async_client`。理由写在注释里:

tools/managed_tool_gateway.py:408 @ 863e313

```python
        # Two clients on purpose, split by whose address we are trusting.
        #
        # The presign POST goes to `presign_url`, which is entirely determined
        # by the managed gateway origin (already validated by
        # is_managed_nous_gateway_url) plus the pinned upload_path — the same
        # first-party host the vendor calls go to freely. SSRF-guarding it
        # protects against nothing and would reject a local gateway on
        # 127.0.0.1, so it uses a plain client. The PUT target, by contrast, is
        # a URL the gateway *returned*, so it keeps the SSRF-safe client as
        # defense in depth (real presigned URLs are public R2, which it allows).
```

**可迁移的设计原则**:SSRF 防护该按「这个地址是谁决定的」来上,不是按「这是不是一次外发请求」来上。
自己拼的地址不需要,别人返回的地址必须要。

超时也分了三档,理由写在源码里:presign 15s;PUT 的 read 60s、write 300s——
因为「一段 50MB 的视频在普通家用上行带宽上,一刀切 60s 会把合法请求切死」。

---

### 2.3 `tools/tool_backend_helpers.py` —— 后端选择与凭据在哪

这个文件是「同一个能力有直连和托管两条路时,选哪条、用谁的钥匙」的公共实现。

#### 2.3.1 三态模式:`auto` / `direct` / `managed`

tools/tool_backend_helpers.py:127 @ 863e313

```python
    if normalized_mode == "managed":
        selected_backend = "managed" if managed_enabled and managed_ready else None
    elif normalized_mode == "direct":
        selected_backend = "direct" if has_direct else None
    else:
        selected_backend = "managed" if managed_enabled and managed_ready else "direct" if has_direct else None
```

`direct` 与 `managed` 是**排他**的(选不到就是 `None`,不回落),只有 `auto` 会先托管后直连。
返回的 dict 里还带一个 `managed_mode_blocked`,专门表达「用户明确要 managed 但没权益」——
这个状态不能用 `selected_backend is None` 表达,因为「要 direct 但没凭据」也是 None,
两者给用户的提示完全不同。这是把「为什么没选上」和「没选上」分开建模的例子。

#### 2.3.2 凭据解析:多 profile 复用一个进程时的雷区

`resolve_provider_secret` 的解析顺序是 config → 环境/scope → 凭据池,
但中间插了一段**在多路复用下直接短路**的逻辑:

tools/tool_backend_helpers.py:199 @ 863e313

```python
    try:
        from agent.secret_scope import is_multiplex_active

        if is_multiplex_active():
            # Under multiplexing the profile scope is authoritative: do not
            # fall through to the process-global .env or credential pool,
            # which may belong to a different profile than the current turn.
            return ""
    except Exception:  # pragma: no cover — secret_scope is in-repo
        pass
```

**这段是本片最重要的安全逻辑之一**。场景:一个网关进程同时服务多个用户 profile。
`os.environ` 里的 `OPENAI_API_KEY` 是**启动时哪个 profile 的 `.env` 恰好被加载**决定的,
和当前这一回合属于谁没关系。如果这里回落到进程全局的环境/凭据池,
A 用户的 TTS 请求就会用 B 用户的 OpenAI 账号鉴权并**计费给 B**。
所以在多路复用下,scope 未命中 = 没有,**不允许回落**,宁可返回 `""` 让工具报「没配 key」。

`resolve_openai_audio_api_key()` 的 docstring 把这个事故形态写得很直白,
并点名同样的路由已经用在 WeChat 发送路径和 `agent/vertex_adapter` 上:

tools/tool_backend_helpers.py:256 @ 863e313

```python
    """Prefer the voice-tools key, but fall back to the normal OpenAI key.

    Routed through the profile secret scope rather than reading ``os.environ``
    directly: in a multiplex gateway serving several profiles from one
    process, ``os.environ`` reflects whichever profile's ``.env`` happened to
    load at boot, not the profile the current turn belongs to. A raw read here
    lets one profile's TTS reply / voice-note transcription authenticate as —
    and get billed against — a different profile's OpenAI account. Same
    routing the WeChat send path and ``agent/vertex_adapter`` already use; see
    ``agent/secret_scope.py``.
```

另一个细节:凭据池要查**两个键**——

tools/tool_backend_helpers.py:231 @ 863e313

```python
        for pool_key in (provider_id, f"custom:{provider_id}"):
```

因为 registry 内置 provider 用裸 id 入池,而 `config.yaml` 里 `providers.<name>` /
`custom_providers` 声明的 provider 用 `custom:<name>` 前缀入池。
这是 #68003 的修法:`hermes auth add <provider>` 加的 key 原来对语音工具不可见,
因为语音工具只看环境变量和 `.env`。

`managed_nous_tools_enabled()` 有一条明确的失败方向声明——权益未知/出错一律 `False`,**「绝不阻塞启动」**:

tools/tool_backend_helpers.py:28 @ 863e313

```python
    Tool Gateway availability fails closed on unknown/error entitlement.  We
    intentionally catch all exceptions and return False — never block startup.
    ``force_fresh=True`` is for interactive configuration flows that should
    reflect a just-purchased subscription, credits, or pool grant immediately.
```

---

### 2.4 `tools/clarify_tool.py` + `tools/clarify_gateway.py` —— agent 反问用户

这是本片被要求重点看的一块。分两层:`clarify_tool.py` 是**平台无关的 schema + 校验 + 转发**,
`clarify_gateway.py` 是**网关模式下的跨线程阻塞原语**,真正的 UI 在各平台适配器里。

#### 2.4.1 `clarify_tool.py`:一个 dict 引发的跨平台污染

最有教学价值的是 `_flatten_choice`:

tools/clarify_tool.py:44 @ 863e313

```python
    if c is None:
        return ""
    if isinstance(c, str):
        return c.strip()
    if isinstance(c, dict):
        for key in ("label", "description", "text", "title"):
            v = c.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""
    if isinstance(c, (list, tuple)):
        return " ".join(_flatten_choice(x) for x in c).strip()
    return str(c).strip()
```

事故形态(docstring 讲得很完整):schema 声明 choices 是裸字符串,但 LLM 有时会吐
`[{"description": "..."}]`。一个天真的 `str(c)` 会把整个 dict 变成 Python repr
`{'description': '...'}`,然后**这串 repr 会同时出现在 CLI 面板、Discord 按钮、
Telegram 编号列表上,并且被原样当成用户的答案返回**。
修在这个平台无关的唯一入口,一次修掉整类问题,而不是每个适配器修一遍。

解包顺序 `label → description → text → title` 是「LLM 工具调用里面向用户的规范键」;
**`name` 和 `value` 被刻意排除**——它们是组件形状的字段,可能装的是枚举原值或短标识符,
不是人类可读标签。全都不匹配就返回 `""` 被丢掉,理由是「一个垃圾标签比没有这个选项更糟」。

`_invoke_callback` 用**签名检查**而不是「先试再 catch TypeError」来判断回调收不收
`multi_select` 关键字:

tools/clarify_tool.py:59 @ 863e313

```python
def _invoke_callback(callback, question, choices, multi_select):
    """Invoke the platform callback, passing multi_select if supported.

    Uses signature inspection (not a ``TypeError`` retry) to decide whether
    the callback accepts the ``multi_select`` keyword — a retry-on-TypeError
    approach would re-invoke a *compatible* callback that raised TypeError
    internally, potentially prompting the user twice.
```

**这是一条很好的通用教训**:`try/except TypeError` + 重试,分不清「签名不匹配的 TypeError」
和「函数体内部抛的 TypeError」,后者重试会**把用户问两遍**。有副作用的调用不能靠异常重试探测签名。

没有回调时的行为:

tools/clarify_tool.py:159 @ 863e313

```python
    if callback is None:
        return tool_error("Clarify tool is not available in this execution context.")
```

子代理走的就是这条路——所以子代理调 clarify 直接拿到工具错误,不会去打扰用户:

tools/delegate_tool.py:1533 @ 863e313

```python
            clarify_callback=None,
```

#### 2.4.2 `clarify_gateway.py`:跨线程阻塞的形状

核心难题在模块 docstring 里说清了:CLI 模式下 `input()` 是同步的,轻松;
网关模式下 **agent 跑在 worker 线程、用户的回复由 event loop 处理**,
需要一个线程安全的原语。状态做成**模块级**(和 `tools.approval` 同形),
这样平台适配器不需要持有 `GatewayRunner` 的反向引用就能解锁。

数据结构是两张表:`_entries`(clarify_id → entry,给按钮回调用)和
`_session_index`(session_key → [clarify_id],FIFO,给文本兜底拦截和会话清理用)。

**等待循环**是这块的精华:

tools/clarify_gateway.py:131 @ 863e313

```python
    # 0 / negative → unlimited: no deadline, poll forever in 1s slices.
    unlimited = timeout is None or float(timeout) <= 0.0
    deadline = None if unlimited else time.monotonic() + float(timeout)
    activity_state = {"last_touch": time.monotonic(), "start": time.monotonic()}
    while True:
        if deadline is None:
            slice_s = 1.0
        else:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            slice_s = min(1.0, remaining)
        if entry.event.wait(timeout=slice_s):
            break
        if touch_activity_if_due is not None:
            touch_activity_if_due(activity_state, "waiting for user clarify response")
```

**为什么不直接 `Event.wait(timeout=600)`**——docstring 写了:
那样线程会 10 分钟零活动,网关的**不活动看门狗**会在用户还在打字的时候把 agent 杀掉。
所以切成 1 秒一片,每片之间敲一次心跳。这是「阻塞等待」和「活性检测」两个机制打架时的标准解法:
**把长等待切成短等待,在缝隙里履行对活性检测的义务**。

#### 2.4.3 回答本片被点名的三个问题

**(a) 网关(非交互)场景下「反问」往哪去?**

走 `agent.clarify_callback`,在网关里定义为 `_clarify_callback_sync`:

gateway/run.py:4988 @ 863e313

```python
        def _clarify_callback_sync(question: str, choices, multi_select: bool = False) -> str:
            from tools import clarify_gateway as _clarify_mod
            import uuid as _uuid

            if not ctx._status_adapter:
```

流程:注册 entry → 暂停「正在输入」指示 → **刷新流消费者里还没送出的散文**
(排序屏障,否则问题会渲染在它自己的解释上面)→ 把 `send_clarify` 调度到 event loop 上、
`fut.result(timeout=15)` 等发送结果 → 阻塞在 `wait_for_response`。
适配器没实现 `send_clarify` 时走基类的编号列表默认实现:

gateway/platforms/base.py:3809 @ 863e313

```python
        which works on every platform — the user replies with a number
        ("2") or with the literal choice text, and the gateway intercepts
        and resolves.  For the text fallback path, the default calls
        ``mark_awaiting_text()`` so that the gateway text-intercept
        (:meth:`GatewayRunner._maybe_intercept_clarify_text`) catches the
        user's reply instead of timing out.
```

**(b) 超时没人回答会怎样?**

`wait_for_response` 返回 `None`,回调把它翻译成一句 sentinel 交还给模型:

gateway/run.py:5057 @ 863e313

```python
                # Couldn't deliver the prompt — clean up and return
                # sentinel so the agent can fall back to a sensible
                # default rather than hanging.
                _clarify_mod.clear_session(ctx.session_key or "")
                return "[clarify prompt could not be delivered]"

            timeout = _clarify_mod.get_clarify_timeout()
            response = _clarify_mod.wait_for_response(clarify_id, timeout=float(timeout))
            if response is None or response == "":
                # Timeout or session-boundary cancellation
```

超时默认 3600 秒。这个默认值是从 600 秒改上来的,理由写在 `get_clarify_timeout` 的 docstring 里:

tools/clarify_gateway.py:413 @ 863e313

```python
    the button, short enough that a genuinely abandoned prompt eventually
    unblocks the agent thread instead of pinning the running-agent guard
    forever.  The old 600s default evicted the entry mid-think, so a late
    tap landed on a dead entry and the agent hung on ``running: clarify``
    (#32762).
```

解析顺序**实跑复现**(`probe_clarify.py`):

```console
  {}                                                             -> 3600
  {'agent': {'clarify_timeout': 30}}                             -> 30
  {'clarify': {'timeout': 5}, 'agent': {'clarify_timeout': 30}}  -> 5
  {'agent': {'clarify_timeout': 'abc'}}                          -> 3600
  {'agent': {'clarify_timeout': 0}}                              -> 0
  {'clarify': {'timeout': None}}                                 -> 3600
```

对应代码:

tools/clarify_gateway.py:399 @ 863e313

```python
    raw = (config.get("clarify") or {}).get("timeout")
    if raw is None:
        raw = (config.get("agent") or {}).get("clarify_timeout", 3600)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 3600
```

注意 `clarify.timeout` 显式设成 `None` 会退回 `agent.clarify_timeout` 而不是被当成 0——
因为判据是 `raw is None`,不是 `if not raw`。

**(c) 会不会把回合卡死?**

在有真人的平台上不会:超时会解除阻塞。但有三条真实的卡死路径:

- **`agent.clarify_timeout: 0` = 无限等待**。这是文档化的配置:

  website/docs/user-guide/configuration.md:2292 @ 863e313

  > clarify_timeout: 3600        # Seconds to wait for user clarification response (0 or less = unlimited)

  **实跑复现**:
  `wait_for_response(id, timeout=0)` 的线程在 0.3 秒后仍然存活,只有 `clear_session` 能让它退出。
  这与本模块 docstring 第 13-14 行「supports timeouts so a user who never responds does NOT hang
  the agent thread forever (which would also pin the gateway's running-agent guard)」的立意
  正好相反——配置提供了一个把这条保护关掉的开关。
- **webhook 平台**:见 §4 的 ■-1,`clarify` 在 webhook 工具集里,而 webhook 的默认投递是写日志、
  返回 success,于是 agent 会为一个没人能回答的问题原地等满一小时。
- **`clear_session` 的连带取消**:发送失败时网关调的是

  gateway/run.py:5060 @ 863e313

  ```python
                  _clarify_mod.clear_session(ctx.session_key or "")
  ```

  取消的是**该会话下所有**待决 clarify,不是刚注册那一个。
  **实跑复现**:一个 session 注册两条,`clear_session` 返回 `2`。

`clear_session` 的取消值也值得记:

tools/clarify_gateway.py:364 @ 863e313

```python
    with _lock:
        ids = list(_session_index.pop(session_key, []) or [])
        entries = [_entries.pop(cid, None) for cid in ids]
    cancelled = 0
    for entry in entries:
        if entry is None:
            continue
        # Empty string sentinel — agent code can distinguish from a real
        # response by inspecting the wait_for_response return value
        # alongside its own timeout deadline.  Most callers just treat any
        # falsy result as "user did not respond".
        entry.response = ""
        entry.event.set()
        cancelled += 1
    return cancelled
```

即:**超时返回 `None`,取消返回 `""`**,两者可区分——但 `gateway/run.py:5065` 的调用方
用 `response is None or response == ""` 把两者合并成同一条消息了,区分能力在这里被丢掉。

#### 2.4.4 文本兜底的强制转换规则

`_coerce_text_response` 决定「用户敲的这行字算不算对 clarify 的回答」。
**实跑复现**的完整行为表:

单选、原生按钮模式(`awaiting_text=False`,choices=`["staging","prod"]`):

```console
  '2'          -> 'prod'        # 数字选择
  'STAGING'    -> 'staging'     # 大小写不敏感的精确标签匹配
  'whatever'   -> None          # 任意散文 → 拒绝,消息继续走普通回合
  after mark_awaiting_text, 'whatever' -> 'whatever'   # 点了 Other 之后接受自由文本
```

多选(`multi_select=True`,choices=`["staging","prod","dev"]`):

```console
  '1,3'                -> '["staging", "dev"]'
  '1 3'                -> '["staging", "dev"]'
  'staging, prod'      -> '["staging", "prod"]'
  '4'                  -> None          # 越界数字 → 整条拒绝
  '1,bogus'            -> None          # 有一个 token 不认 → 整条拒绝
  'just some prose'    -> None
```

「越界就整条拒」的理由与编码约定都写在 `_coerce_text_response` 的 docstring 里:

tools/clarify_gateway.py:216 @ 863e313

```python
        can retry instead of silently getting a partial selection
      - Selections are returned as a JSON array string, which the clarify
        tool's ``_parse_multi_select_response`` decodes back into a list
```

即:让用户重试,而不是**悄悄拿到一个部分选择**;多选结果编码成 JSON 数组字符串,
再由 `clarify_tool._parse_multi_select_response` 解回列表——这是两个模块之间的编码约定。

「空格也当分隔符」有个前置条件:

tools/clarify_gateway.py:284 @ 863e313

```python
        parts = text.split()
        if len(parts) > 1 and all(p.strip().isdigit() for p in parts):
            tokens = [p.strip() for p in parts]
        else:
            tokens = [text]
```

只有**全部 token 都是数字**时空格才算分隔符,否则整串当一个 token——
否则 `staging prod` 这种带空格的选项标签会被切碎。

---

### 2.5 `agent/think_scrubber.py` —— 把思考内容从外发里擦掉(隐私面重点)

#### 2.5.1 它为什么必须是有状态的

模块 docstring 讲的事故非常具体:MiniMax-M2.7 会把
`delta1="<think>"`、`delta2="Let me check their config"`、`delta3="</think>"` 分三个 delta 发。
原来在 `_fire_stream_delta` 里**按 delta 跑正则**,delta1 被「未闭合开标签」那条规则整个吃掉,
于是**下游的状态机根本没看见开标签**,把 delta2 当成正常内容显示出去,推理内容泄露给用户。
更糟的是 ACP、api_server、TTS 这些自己不跑状态机的消费者,**从来就没有任何防线**。

现在的挂载点:

run_agent.py:6361 @ 863e313

```python
            think_scrubber = getattr(self, "_stream_think_scrubber", None)
            if think_scrubber is not None:
                text = think_scrubber.feed(text or "")
```

即**每一个外发增量都先过它**,之后再过 context scrubber(记忆上下文擦除)。
流结束时调 `flush()`,把被扣住的、结果不是标签的尾巴放出去:

run_agent.py:6033 @ 863e313

```python
        think_scrubber = getattr(self, "_stream_think_scrubber", None)
        if think_scrubber is not None:
            think_tail = think_scrubber.flush()
```

#### 2.5.2 三条判定规则

1. **闭合对优先且不设边界门控**(`_find_earliest_closed_pair`):`<tag>X</tag>` 无论出现在哪都擦。
   理由:闭合对是「有意的、有界的构造」,即使出现在行中间的散文里,也几乎肯定是模型在内联泄露推理。
2. **未闭合开标签必须在块边界**(`_find_open_at_boundary` + `_is_block_boundary`):
   只有在流开头、换行之后(可带空白)、或当前行只发过空白时,才认为是真的开块。
   这是为了不把「use `<think>` tags here」这种**提到**标签名的散文吃掉。
3. **孤儿闭标签一律删**(`_strip_orphan_close_tags`),连同其后的空白。

标签集合是**字面量**,不是正则:

agent/think_scrubber.py:79 @ 863e313

```python
    _OPEN_TAG_NAMES: Tuple[str, ...] = (
        "think",
        "thinking",
        "reasoning",
        "thought",
        "REASONING_SCRATCHPAD",
    )

    # Materialise literal tag strings so the hot path does string
    # operations, not regex compilation per feed().
    _OPEN_TAGS: Tuple[str, ...] = tuple(f"<{name}>" for name in _OPEN_TAG_NAMES)
    _CLOSE_TAGS: Tuple[str, ...] = tuple(f"</{name}>" for name in _OPEN_TAG_NAMES)

    # Pre-compute the longest tag (for partial-tag hold-back bound).
    _MAX_TAG_LEN: int = max(len(tag) for tag in _OPEN_TAGS + _CLOSE_TAGS)
```

**这个选择是本节最大的发现来源**:字面量意味着 `<think type="x">`
(带任何属性的开标签)**不被识别**。见 §4 ■-4。

#### 2.5.3 边界输入实测(本轮实跑)

探针见 §3.2 `probe_scrub.py` / `probe_cmp.py`。全部为**实跑复现**:

```console
'closed-pair'              ["<think>","secret plan","</think>","Hello"] -> 'Hello'          擦净
'open-at-start'            ["<think>","secret plan"]                    -> ''               擦净
'uppercase'                '<THINK>secret</THINK>Visible'               -> 'Visible'        擦净(大小写不敏感)
'split-tag'                ["<thi","nk>","sec","ret","</thi","nk>","Visible"] -> 'Visible'  擦净(跨 delta 拼标签)
'orphan-close'             'Use the </think> marker like this.'         -> 'Use the marker like this.'
'midline-open-then-close'  'Answer: <think>secret\n</think>Visible'     -> 'Answer: Visible'  闭合对无视边界规则
'newline-open'             ['Hi there\n','<think>secret</think... ']    -> 'Hi there\n'
---- 以下为泄露 ----
'nested'    '<think>outer <think>inner</think> tail-of-outer</think>Visible' -> ' tail-of-outerVisible'
'attr-tag'  '<think type="x">secret</think>Visible'   -> '<think type="x">secretVisible'
'space-tag' '< think >secret</think >Visible'         -> '< think >secret</think >Visible'
'midline-open' 'Answer: <think>secret plan'           -> 'Answer: <think>secret plan'
'analysis-tag' '<analysis>secret</analysis>Visible'   -> '<analysis>secret</analysis>Visible'
'pipe-tag'  '<|thinking|>secret<|/thinking|>Visible'  -> '<|thinking|>secret<|/thinking|>Visible'
```

逐条判读:

- **nested**(嵌套同名标签):非贪婪匹配吃到**第一个**闭标签,于是外层的尾巴
  ` tail-of-outer` 作为可见内容发出去。这是模型嵌套自省时的推理内容泄露。
  注意:非流式的正则路径**结果完全一致**,所以这不是流式实现的锅,是
  「非贪婪 `<tag>.*?</tag>`」这个语义本身的必然结果——两条路径至少**一致**。
- **attr-tag / space-tag / analysis-tag / pipe-tag**:标签集之外的形态,原样透传。
- **midline-open**:行中间的未闭合开标签,按第 2 条规则**故意不擦**。
  这是一个明确的取舍:宁可漏擦,不可把提到标签名的散文吃掉。

#### 2.5.4 流式路径与最终路径的行为分叉(强断言)

把同一个输入分别喂给 `StreamingThinkScrubber` 和 `strip_think_blocks`(非流式正则路径),
**实跑复现**:

```console
input   : '<think type="x">secret</think>Visible'
  stream: '<think type="x">secretVisible'
  regex : ''
input   : '<think type="x">secret'
  stream: '<think type="x">secret'
  regex : ''
input   : '<thinking id="1">secret\nmore secret'
  stream: '<thinking id="1">secret\nmore secret'
  regex : ''
input   : 'Answer: <think>secret plan'
  stream: 'Answer: <think>secret plan'
  regex : 'Answer: secret plan'
```

分叉的机制在两边的模式定义里一目了然。非流式路径的**未闭合**分支用 `\b[^>]*>`,**接受属性**:

agent/agent_runtime_helpers.py:78 @ 863e313

```python
_UNTERMINATED_REASONING_BLOCK_PATTERN = re.compile(
    rf'(?:^|\n)[ \t]*<(?:{"|".join(_REASONING_TAG_NAMES)})\b[^>]*>.*$',
    re.DOTALL | re.IGNORECASE,
)
```

而**闭合对**分支不接受属性:

agent/agent_runtime_helpers.py:55 @ 863e313

```python
_REASONING_TAG_NAMES = ("think", "thinking", "reasoning", "REASONING_SCRATCHPAD", "thought")
_TOOL_CALL_TAG_NAMES = ("tool_call", "tool_calls", "tool_result", "function_call", "function_calls")

_REASONING_BLOCK_PATTERNS = tuple(
    re.compile(rf"<{name}>.*?</{name}>", re.DOTALL | re.IGNORECASE)
    for name in _REASONING_TAG_NAMES
)
```

于是 `<think type="x">secret</think>Visible` 在正则路径下,先被闭合对模式**跳过**(不匹配),
再被未闭合模式从开标签一路吃到字符串末尾——连 `Visible` 一起吃掉,返回 `''`。
用户看到的是:**流式过程中完整看到推理内容,流结束后整条回复变空**。

#### 2.5.5 「什么算推理标签」被独立实现了至少 7 次

**搜索面**:`git grep -n "REASONING_SCRATCHPAD" -- '*.py'`,排除 `tests/`。命中的独立定义:

| 位置 | 形态 | 是否接受属性 | 标签集 |
|---|---|---|---|
| `agent/think_scrubber.py:79`:`_OPEN_TAG_NAMES: Tuple[str, ...] = (` | 字面量元组 | 否 | 5 个 |
| `agent/agent_runtime_helpers.py:55`:`_REASONING_TAG_NAMES = ("think", "thinking", "reasoning", "REASONING_SCRATCHPAD", "thought")` | 正则(闭合对) | 否 | 5 个 |
| `agent/agent_runtime_helpers.py:78` 的 `_UNTERMINATED_REASONING_BLOCK_PATTERN` | 正则(未闭合) | **是** | 5 个 |
| `agent/auxiliary_client.py:9364`:`r"<(?:think\|thinking\|reasoning\|thought\|REASONING_SCRATCHPAD)>"` | 正则 | 否 | 5 个 |
| `agent/conversation_loop.py:2948`:`r'<(?:think\|thinking\|reasoning\|REASONING_SCRATCHPAD)[^>]*>'` | 正则 | **是** | **4 个(缺 thought)** |
| `cli.py:234`:`_REASONING_TAGS = (` | 字面量元组 | 否 | 5 个 |
| `cli.py:6643`:`_OPEN_TAGS = ("<REASONING_SCRATCHPAD>", "<think>", "<reasoning>", "<THINKING>", "<thinking>", "<thought>")` | 字面量元组 | 否 | 5 个(`<THINKING>` 冗余) |
| `gateway/stream_consumer.py:179`:`"<REASONING_SCRATCHPAD>", "<think>", "<reasoning>",` | 字面量元组 | 否 | 5 个(`<THINKING>` 冗余) |

`gateway/stream_consumer.py:175` 的注释坦白了这个状况:

gateway/stream_consumer.py:176 @ 863e313

```python
    # Must stay in sync with cli.py _OPEN_TAGS/_CLOSE_TAGS and
    # run_agent.py _strip_think_blocks() tag variants.
```

它点了 2 个同步对象,而实际至少有 8 处定义、3 种不同的属性策略、2 种不同的标签集。
`cli.py:6643` 与 `gateway/stream_consumer.py:179` 里的 `<THINKING>` 条目是**冗余**的
(两处比较都先 `.lower()`),说明这些副本是手抄扩散出来的。

---

### 2.6 `agent/title_generator.py` —— 会话标题会不会把用户内容送去模型

**会,而且是明确设计如此。** 送的是首轮对话双方各前 500 字符:

agent/title_generator.py:133 @ 863e313

```python
    # Truncate long messages to keep the request small
    user_snippet = _summarize_user_message(user_message)[:500]
    assistant_snippet = assistant_response[:500] if assistant_response else ""

    language = _title_language()
    prompt = _TITLE_PROMPT_PINNED_LANGUAGE.format(language=language) if language else _TITLE_PROMPT

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"User: {user_snippet}\n\nAssistant: {assistant_snippet}"},
    ]
```

接收方是 `agent.auxiliary_client.call_llm(task="title_generation", ..., main_runtime=main_runtime)`。
`call_llm` 的 `task` 参数从 `auxiliary.title_generation.*` 读 provider/model:

agent/auxiliary_client.py:8658 @ 863e313

```python
              "session_search", "skills_hub", "mcp", "title_generation").
              Reads provider:model from config/env. Ignored if provider is set.
        provider: Explicit provider override.
```

所以**这段内容可以被发到与主对话不同的 provider**。
文档在配置页给出的示例状态就是一个异构组合:

website/docs/user-guide/configuration.md:1059 @ 863e313

> `[ ] title_generation     currently: openrouter / google/gemini-3-flash-preview`

文档也承认了这条数据流并给出了关闭方式:

website/docs/user-guide/skills/optional/security/security-web-pentest.md:86 @ 863e313

> - If the engagement is sensitive, set `auxiliary.title_generation.enabled: false`
>   in `~/.hermes/config.yaml` for the session.

所以这**不是 ▲**(文档没说错),但是一条值得在蓝图里写清的数据流事实。

其余设计要点:

- **`_summarize_user_message`**:`/skill` 调用会展开成一条内嵌整个 skill 正文的消息,
  直接拿去起标题会把会话命名成**那个 skill 的散文**,而不是用户的请求。所以先用
  `describe_skill_invocation` 还原成 `/work — fix the title leak` 再送。
- **`runtime_validator`**:后台线程抓了运行时快照之后,用户可能已经 `/model` 换了模型;
  发请求前再校验一次,返回 False 就静默跳过,免得**把运行时已经卸载的模型又拉起来**(#19027)。
  校验器自己抛异常时**fail open**——一个坏掉的校验器不该把起标题功能整个关掉。
- **输出清洗四步**:先用 `strip_think_blocks`(复用规范 scrubber,不是自己写个 `<think>` 正则),
  再剥引号,再剥 `title:` 前缀,再 **只保留第一行非空行**。最后一步的理由:

  agent/title_generator.py:167 @ 863e313

  ```python
          # A title is one line. A model that ignores "return ONLY the title" and
          # answers the prompt instead (a shell transcript, a bulleted plan) would
          # otherwise be stored verbatim and truncated mid-command. Keep the first
          # non-empty line — the closest thing to a title in that response.
          title = next((line.strip() for line in title.splitlines() if line.strip()), "")
  ```
- **`_persist_session_title`**:走 `set_auto_title_if_empty`(谓词 + 写在一个事务里),
  保证生成期间用户手动 `/title` 不会被覆盖;撞唯一标题索引时用
  `get_next_title_in_lineage()` 加 `#N` 后缀而不是把会话留成无标题(#50537)。
- **`auto_title_session` 的兜底 catch**:这是守护线程的入口,异常逃出去会经 threading
  默认 excepthook 把 traceback 喷进用户终端。它点名的典型触发场景是
  **`hermes update` 之后的陈旧模块窗口**——惰性 import 从磁盘读到新源码,
  而已缓存的模块还是旧版本,ImportError 会在每次自动起标题时重复出现直到进程重启。
  于是日志措辞里直接把「重启进程」写进去,让用户能自查。
- **上下文发布**:`_auto_title_session` 在裸守护线程里显式重建两个 ambient 上下文——
  `set_conversation_context(root)`(Portal 标签)与 `set_accounting_context`(记账),
  否则标题调用的 token 用量记不到这个会话头上(#23270)。
  这是「用裸线程做后台工作」必须付的代价:**ContextVar 不会自动跟过去**。

触发门控在 `maybe_auto_title`:统计历史里 user 消息数 > 2 就不做;
配置读取**放在这个便宜的门控之后**,免得长会话每一轮都去碰配置文件。

---

### 2.7 `tools/hook_output_spill.py` —— 钩子输出溢出到哪

**场景**:一个 shell hook 或 Python 插件的 `pre_llm_call` 返回 `{"context": "..."}`,
这段文本会被拼进**当前回合的 user 消息**,并且在此后**每一次 API 调用**里都带着。
一个吐 debug dump 的 hook 会让每一轮 prompt 膨胀,并且在被追加的那一刻**打穿 prompt 缓存前缀**。

做法(移植自 openai/codex PR #21069):超过阈值就落盘,prompt 里换成 head/tail 预览 + 路径。

tools/hook_output_spill.py:115 @ 863e313

```python
def _resolve_spill_dir(directory_override: Optional[str], session_id: Optional[str]) -> Path:
    """Return the directory where spill files for this session live."""
    if directory_override:
        base = Path(os.path.expanduser(directory_override))
    else:
        from hermes_constants import get_hermes_home

        base = Path(get_hermes_home()) / "hook_outputs"

    # Group by session so spills are contained per conversation.
    session_segment = session_id or "no-session"
    # Defensive: strip path separators so a weird session id can't
    # escape the directory.
    session_segment = session_segment.replace("/", "_").replace("\\", "_").replace("..", "_")
    return base / session_segment
```

这段的**防御是真起作用的**,理由比注释说的更强:Python 的 `Path.__truediv__` 遇到
**绝对路径右操作数会直接替换掉左边的 base**(`Path("/a") / "/etc"` → `Path("/etc")`)。
先把 `/` 换掉,才让后面的拼接不可能逃逸。**实跑复现**:

```console
  None           -> /tmp/spillbase/no-session
  '../../etc'    -> /tmp/spillbase/____etc
  '/etc/passwd'  -> /tmp/spillbase/_etc_passwd
  'a/../../b'    -> /tmp/spillbase/a_____b
  '..'           -> /tmp/spillbase/_
```

(顺带:`.replace("..", "_")` 那一步在分隔符已经被换掉之后其实是冗余的,但无害。)

另外注意这里 `get_hermes_home()` 是**在落盘时调用**的,所以是 profile 感知的——
这一点和 `tools/debug_helpers.py` 形成对照,见 §2.9 与 ■-6。

不变量在 docstring 里声明得很干净:

tools/hook_output_spill.py:33 @ 863e313

```python
* Behaviour-preserving when ``enabled: false`` or when content is under
  the cap — return the input string unchanged.
* Never raises. Any I/O error (disk full, permission denied, missing
  HERMES_HOME, etc.) falls back to a byte-length truncation with an
  in-prompt notice — the hook context still reaches the model, just
  bounded in size.
* Spill files are grouped by session so a ``/new`` session doesn't grow
  them forever in one directory.
```

落盘失败时预览头会写成 `unavailable — spill write failed`,而不是假装存了。

写入:

tools/hook_output_spill.py:209 @ 863e313

```python
    try:
        spill_dir = _resolve_spill_dir(directory_override, session_id)
        spill_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.txt"
        spill_path = spill_dir / filename
        # Write the raw text plus a trailing newline so tail readers
        # (``tail -f``, editors) don't report "missing newline".
        spill_path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        saved_path = str(spill_path)
```

见 §4 的 ■-5(权限)与 ◇-4(无清理)。

---

### 2.8 `tools/thread_context.py` —— 把回合上下文传播进工作线程

这是本片**安全性最高**的一个小文件。它解决的问题在 docstring 里点了两个 CVE 级的编号:
裸 `threading.Thread` / `ThreadPoolExecutor` 的 worker 从**空的 `contextvars.Context`**
开始,并且没有线程局部的审批/sudo 回调,于是在这样的线程里派发工具会静默丢掉:

- 审批的 session/platform ContextVar → 网关会话掉进 `check_dangerous_command` 的
  **非交互自动批准分支**,危险命令无提示直接执行(#33057, #30882);
- CLI 的审批/sudo 线程局部回调 → `prompt_dangerous_approval` 够不到用户
  (GHSA-qg5c-hvr5-hjgr, #15216)。

实现是「父线程快照 + 子线程安装 + 退出必清」:

tools/thread_context.py:78 @ 863e313

```python
    ctx = contextvars.copy_context()
    parent_approval_cb = parent_sudo_cb = None
    setters = None
    try:
        get_approval, get_sudo, set_approval, set_sudo = _callback_api()
        parent_approval_cb = get_approval()
        parent_sudo_cb = get_sudo()
        setters = (set_approval, set_sudo)
    except Exception:
        logger.debug("Could not capture parent approval/sudo callbacks", exc_info=True)

```

关键是**失败方向**声明:安装回调失败就让回调保持 `None`,而这是安全的结果——

tools/thread_context.py:74 @ 863e313

```python
    denies dangerous commands when no callback is registered in an interactive
    context, and the gateway approval queue blocks when its notify callback is
    absent.
    """
```

即 `prompt_dangerous_approval` 在交互场景下没有注册回调时**拒绝**危险命令,
网关审批队列在没有 notify 回调时**阻塞**。fail-closed。

`finally` 里无条件 `set_approval(None)` / `set_sudo(None)`,理由是线程池会**复用线程**,
不清的话一个被回收的线程会攥着一个已销毁 CLI 实例的引用。

有一个**未文档化的使用约束**(见 ◇-5):`ctx.run()` 不能被并发进入,
所以 `propagate_context_to_thread` 返回的包装器**只能给一个线程用**。
**实跑复现**:同一个包装器在两个线程上并发调用,第二个抛
`RuntimeError: cannot enter context: <_contextvars.Context object at 0x...> is already entered`。
顺序复用是可以的(实测两次串行调用都成功)。
全仓 9 个调用点(`git grep -n "propagate_context_to_thread(" -- '*.py'`,排除 tests 与本模块)
**全部是在提交处内联构造包装器**,所以这条约束目前是潜伏的地雷,不是活的 bug。

---

### 2.9 `tools/budget_config.py` 与 `tools/debug_helpers.py`

#### `budget_config.py`:按上下文窗口缩放的工具结果预算

三层预算:单条结果阈值(Layer 2)、整回合聚合预算(Layer 3)、落盘后的内联预览大小。
解析优先级 **pinned > 配置覆盖 > registry 每工具值 > 默认**:

tools/budget_config.py:49 @ 863e313

```python
        if tool_name in PINNED_THRESHOLDS:
            return PINNED_THRESHOLDS[tool_name]
        if tool_name in self.tool_overrides:
            return self.tool_overrides[tool_name]
        from tools.registry import registry
        registry_value = registry.get_max_result_size(tool_name, default=self.default_result_size)
        if registry_value == float("inf"):
            return registry_value
        return min(registry_value, self.default_result_size)
```

两个细节值得学:

- **`read_file` 被钉成 `float("inf")`**:

  tools/budget_config.py:9 @ 863e313

  ```python
  # Tools whose thresholds must never be overridden.
  # read_file=inf prevents infinite persist->read->persist loops.
  PINNED_THRESHOLDS: Dict[str, float] = {
      "read_file": float("inf"),
  }
  ```

  理由是防止 `persist → read → persist` 的无限循环:落盘机制本身把大结果写成文件让模型去
  `read_file`,如果 `read_file` 的结果也会被落盘,就自己咬自己。
  **「用来读溢出物的工具必须免疫溢出机制」**是个可迁移的规则。
- **registry 的每工具值被 `min()` 压到 `default_result_size`**:web / terminal / x_search
  都在 registry 里注册了固定的 100K,如果不压,一个按小模型窗口缩放过的预算会被
  每工具注册值**重新吹回**模型窗口之外(#23767)。

缩放规则:单结果占窗口 15%、整回合占 30%,4 字符/token,
上限钉在历史默认值(所以大模型行为逐字节不变),下限 8K/16K(所以小模型仍可用)。
`context_length` 为 0 或 None 时直接回默认配置。

#### `debug_helpers.py`:三个工具共用的调试日志壳

`DebugSession(tool_name, env_var=...)`,由 `WEB_TOOLS_DEBUG` / `VISION_TOOLS_DEBUG` /
`IMAGE_TOOLS_DEBUG` 三个环境变量分别激活,关闭时所有方法都是廉价 no-op。

tools/debug_helpers.py:43 @ 863e313

```python
    def __init__(self, tool_name: str, *, env_var: str) -> None:
        self.tool_name = tool_name
        self.enabled = os.getenv(env_var, "false").lower() == "true"
        self.session_id = str(uuid.uuid4()) if self.enabled else ""
        self.log_dir = get_hermes_home() / "logs"
        self._calls: list[Dict[str, Any]] = []
        self._start_time = datetime.datetime.now().isoformat() if self.enabled else ""

        if self.enabled:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            logger.debug("%s debug mode enabled - Session ID: %s",
                         tool_name, self.session_id)
```

三个实例都是**模块级**构造的,例如:

tools/web_tools.py:433 @ 863e313

```python
_debug = DebugSession("web_tools", env_var="WEB_TOOLS_DEBUG")
```

另两处在 `tools/vision_tools.py:72` 与 `tools/image_generation_tool.py:443`。
因此 `enabled` 和 `log_dir` 都在**模块 import 时**定格。`log_dir` 定格带来的问题见 ■-6。

---

### 2.10 `agent/process_bootstrap.py` —— 它其实不管子进程

**先纠正一个容易产生的预期**:这个文件的名字像是「子进程起法 + 环境变量继承」,
但它**不 spawn 任何子进程,也不构造任何子进程环境**。
**搜索面**:在该文件内 `grep -nE "subprocess|Popen|os\.exec|fork|spawn|env=|environ\["` **零命中**
(只有 `os.environ.get` 的读取,在 `_get_proxy_from_env` 里)。
它的三件事在 docstring 里列得很清楚——惰性 OpenAI SDK import、抗崩溃 stdio、HTTP 代理解析:

agent/process_bootstrap.py:3 @ 863e313

```python
Three concerns, all tied to ``AIAgent`` boot-time / runtime IO setup:

1. **Lazy OpenAI SDK import** — ``_load_openai_cls`` + ``_OpenAIProxy``
   defer the 240ms-ish ``from openai import OpenAI`` cost until first use,
```
**所以「会不会把凭据继承给子进程」这个问题在本文件里不成立**,需要去找真正 spawn 子进程的模块
(不在本片范围内)——这条作为移交项 H-R9D-F-e。

三件事各自的设计要点:

**(1) 惰性 OpenAI import**:`_OpenAIProxy` 是个模块级单例,同时实现 `__call__` 和
`__instancecheck__`,所以 `OpenAI(...)` 能构造、`isinstance(client, OpenAI)` 也能过,
而 `from openai import OpenAI` 那 240ms 推迟到第一次真用。
`patch("run_agent.OpenAI", ...)` 的测试写法也保住了。

**(2) `_SafeWriter`**:

agent/process_bootstrap.py:87 @ 863e313

```python
    def write(self, data):
        try:
            return self._inner.write(data)
        except (OSError, ValueError):
            return len(data) if isinstance(data, str) else 0

    def flush(self):
        try:
            self._inner.flush()
        except (OSError, ValueError):
            pass
```

捕两类异常各有出处:`OSError: [Errno 5] Input/output error` 来自 systemd / Docker /
无头守护进程下 stdout 管道失效;`ValueError: I/O operation on closed file` 来自子代理跑在
ThreadPoolExecutor 线程里、共享 stdout 句柄在线程拆解与清理之间被关掉。
写失败时**谎报写入了 `len(data)` 字节**——这是有意的:调用方看到短写会重试,
而重试在一个已死的管道上只会再失败一次。
docstring 特别点了**双重故障**这个形态:`except` 处理器里自己也 print,于是异常处理本身崩掉。

`_install_safe_stdio` 有幂等保护(`not isinstance(stream, _SafeWriter)`),重复调用不会套娃。

**(3) 代理**:`_get_proxy_from_env` 按 `HTTPS_PROXY → HTTP_PROXY → ALL_PROXY`
(以及小写变体)取第一个非空值;`_get_proxy_for_base_url` 再用
`urllib.request.proxy_bypass_environment(host)` 尊重 `NO_PROXY`。

`build_keepalive_http_client` 里两条注释记了两次事故:
- **不用自定义 `socket_options` transport**——它在反向代理后面会破坏流式(#54049, #12952),
  并且因为剥掉 `TCP_NODELAY` 而拖慢 TLS 握手。改用 HTTP 连接池层的
  `keepalive_expiry=20.0`(在反代典型的 30-60 秒超时之前先回收空闲连接)。
- **无代理时显式挂载 plain transport**(而不是什么都不挂):这样可以关掉 httpx 默认的
  `trust_env` 代理路径,免得 macOS 的系统代理设置(`urllib.request.getproxies()` 返回的,
  **不含 ExceptionsList**)被套用上来。
- `read=None`(流式 SSE 端点不设读超时),`verify` 同时传给 client **和** 挂载的 transport
  ——因为「挂载的 transport 拥有它那个 scheme 的 SSL 上下文」。

---

### 2.11 `agent/replay_cleanup.py` —— 回放清理:删什么、误删风险

三个独立机制放在一个文件里。

#### (a) 剥离被中断的 assistant→tool 块

进程在工具循环中途被杀(重启/关机命令、陈旧超时、中断先于工具结果落盘),
持久化的 transcript 会以一个悬空的 `assistant(tool_calls)` 或一个被中断的 `assistant→tool`
块结尾。恢复时模型看到这个破尾巴,**自然会重发那个没被回答的调用**——
如果那个调用就是 `docker restart` / `systemctl restart` / `hermes gateway restart`,
就是 #49201 的无限重启循环。

判据:

agent/replay_cleanup.py:30 @ 863e313

```python
def is_interrupted_tool_result(content: Any) -> bool:
    """Return True if a tool result indicates the tool was interrupted."""
    if not isinstance(content, str):
        return False
    lowered = content.lower()
    if "[command interrupted]" in lowered:
        return True
    if "exit_code" in lowered and ("130" in lowered or "-1" in lowered):
        return "interrupt" in lowered
    return False
```

**这是纯字符串嗅探,没有任何结构化标记**,误判面很大,见 ■-2。

处置分两档,这个分档是本文件最好的设计:
- **只读工具** → 整块**删掉**;
- **有副作用的工具**(`tool_may_have_side_effect`)→ **不删**,把工具结果**改写**成
  `[Orphan recovery: interrupted side-effecting tool may have executed; its effect is UNKNOWN.
  Inspect state before retrying.]` 并打上 `effect_disposition="unknown"`。
  日志用 WARNING 级别记「Recovered dangling side-effecting tool call(s) as UNKNOWN instead of erasing them」。

**可迁移的设计原则**:清理历史时,**「可能已经发生的副作用」不能被静默抹掉**,
只能被降级成「结果未知,请先检查状态」。抹掉等于对模型撒谎说这件事没发生过。

`strip_dangling_tool_call_tail` 只在尾巴是**完全没有 tool 答复**的
`assistant(tool_calls)` 时才动手;只要有任何一条 tool 答复,就说明这是个正常推进中的
工具循环,原样保留。

#### (b) 过期的高危确认语

场景(#59607):用户说「确认强制重开机」,agent 执行 `shutdown.exe`,主机重启把网关进程杀了,
**assistant 的工具结果没来得及写**,transcript 尾巴停在 assistant 的文本回复上,
而 user 角色里那句确认语还在。几分钟后用户回来随口说一句「你在吗?」,
LLM 看到那句陈旧确认语,可能把新回合理解成**再次确认**,把破坏性操作再跑一遍。

过期窗口 **60 秒**,理由是「破坏性副作用不该活过任何一次重启或会话恢复间隙;用户随时可以重新确认」:

agent/replay_cleanup.py:208 @ 863e313

```python
# How long a high-risk confirmation phrase remains valid.
# Short on purpose: dangerous side effects should not survive any restart
# or session resumption gap. The user can always re-confirm if needed.
_DANGEROUS_CONFIRMATION_EXPIRY_SECONDS = 60.0
```

处置方式是**就地涂改而不是删除**:

agent/replay_cleanup.py:298 @ 863e313

```python
    for msg in agent_history:
        if (
            isinstance(msg, dict)
            and msg.get("role") == "user"
            and is_dangerous_confirmation(msg.get("content", ""))
        ):
            ts = msg.get("timestamp")
            if ts is not None and (now - float(ts)) > expiry_seconds:
```

删掉会在事故尾巴里留下两条连续的 assistant 消息,违反 provider 强制的严格角色交替。
所以保留消息、保留角色,只把触发文本换成 sentinel。
并且**顺手丢掉 `api_content` 边车**——那里存着上次实际发出去的原始字节,
就是这次涂改要作废的那句确认语,不丢的话重放时会在线路上把涂改撤销。
这是个很容易漏的细节:**内容有两份副本时,只改一份等于没改**。

判据同样是子串嗅探:

agent/replay_cleanup.py:249 @ 863e313

```python
    if not isinstance(content, str):
        return False
    text = content.strip().lower()
    return any(pattern in text for pattern in _DANGEROUS_CONFIRMATION_PATTERNS)
```

**实跑复现**的误判与漏判:

```console
  True  <- 'please do NOT confirm shutdown of the server'
  True  <- "the docs say: type 'confirm reboot' to proceed"
  True  <- 'confirm rebooting is unnecessary'
  False <- 'hello'
```

误判方向是**安全的**(多涂改一条,用户重新确认即可)。真正的问题是覆盖面:
`_DANGEROUS_CONFIRMATION_PATTERNS` 是一份硬编码的英文 + 繁体中文清单
(繁体那三条注释写着 "i18n variants observed in the original incident"),
其他语言的确认语**永远不会过期**。见 ◇-6。

还有一个更硬的门:**没有 `timestamp` 字段的消息一律不动**。**实跑复现**:

```console
  no-ts  -> [{'role': 'user', 'content': 'confirm shutdown'}]        # 原样,未涂改
  old-ts -> [A high-risk confirmation previously giv...              # 涂改了
  assistant-role -> [{'role': 'assistant', 'content': 'confirm shutdown', 'timestamp': 0.0}]  # 只看 user 角色
```

docstring 把「无 timestamp 不动」解释成向后兼容(遗留 transcript 与内存测试脚手架没有时间戳)。
但这意味着**这层保护对任何不带 timestamp 的历史来源是完全无效的**,而是否带 timestamp
取决于持久化层,不在本文件里。见移交项 H-R9D-F-c。

#### (c) `sanitize_replay_history` 的顺序

先剥「历史中任意位置的被中断块」,再剥「尾部悬空的未回答 tool_calls」。
顺序不能反:前者可能把尾巴变成新的悬空 assistant。
调用方:

tui_gateway/methods_session.py:518 @ 863e313

```python
        history = sanitize_replay_history(raw_history)
```

同文件 `:606` 还有一处,导入在 `tui_gateway/server.py:37`。
docstring 明确说这些函数原来在 `gateway/run.py` 里,提出来是因为
**WebUI 那条恢复路径原来静默跳过了这套清理**——同一个 bug 在一个界面上修了、另一个界面没修,
提取共享实现是修法的一部分。

---

## 3. 测试作为行为规格

### 3.1 跑了什么

环境:`/home/user/hermes-venv/bin/python`(Python 3.11.15),**87 个包**
(`pip list` 去表头计数 = 87;`site-packages/*.dist-info` 计数 = 87,两者一致),
以 root 运行(`id -u` = 0),SQLite 3.45.1,离线。**本轮未安装任何包**。

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh \
  tests/tools/test_managed_tool_gateway.py tests/tools/test_tool_backend_helpers.py \
  tests/tools/test_clarify_tool.py tests/tools/test_clarify_gateway.py \
  tests/tools/test_budget_config.py tests/tools/test_debug_helpers.py \
  tests/tools/test_hook_output_spill.py
```

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh \
  tests/agent/test_think_scrubber.py tests/agent/test_title_generator.py \
  tests/agent/test_replay_cleanup.py tests/gateway/test_clarify_active_session_bypass.py \
  tests/gateway/test_clarify_progress_leak.py tests/gateway/test_clarify_thread_followup_not_swallowed.py
```

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh \
  tests/agent/test_jiter_preload.py tests/tools/test_terminal_truncation_spill.py \
  tests/gateway/test_discord_clarify_buttons.py tests/gateway/test_slack_clarify_buttons.py \
  tests/gateway/test_telegram_clarify_buttons.py tests/plugins/platforms/photon/test_poll_clarify.py \
  tests/gateway/test_title_command.py
```

结果:

```console
=== Summary: 7 files, 125 tests passed, 0 failed (100% complete) in 3.3s (8 workers) ===
=== Summary: 6 files, 44 tests passed, 0 failed (100% complete) in 3.2s (8 workers) ===
=== Summary: 7 files, 33 tests passed, 0 failed (100% complete) in 2.8s (8 workers) ===
```

**合计 20 个文件、202 passed、0 failed、0 静默跳过**(未观察到 `importorskip` 整文件跳过;
`s` 计数为 0)。本片没有撞上任何已知容器限制(无 IPv6 / root / 离线 / SQLite 措辞)。

### 3.2 测试没覆盖到的边界(本轮自建探针)

四个探针脚本放在会话临时目录(不入库),内容与结果已在 §2 逐条引用:

| 脚本 | 覆盖 | 关键产出 |
|---|---|---|
| `probe_scrub.py` | think_scrubber 15 种边界输入 | 属性标签 / 嵌套 / 行中未闭合 的泄露 |
| `probe_cmp.py` | 流式 scrubber vs 非流式正则 | 4 组输入上两条路径结果不一致 |
| `probe_clarify.py` | clarify_gateway 8 组语义 | 无限等待、连带取消、多选强转表 |
| `probe_misc.py` / `probe_misc2.py` | replay_cleanup / thread_context / spill | 误判样本、并发 ctx RuntimeError、目录消毒 |
| `probe_gw.py` | managed_tool_gateway 寻址与鉴权 | http 明文 bearer、大小写敏感、域可被 env 改写 |

`tests/tools/test_clarify_gateway.py` 的 23 个用例覆盖了注册/解析/多选强转/清理,
但**不覆盖 `timeout <= 0` 的无限等待路径**(那条路径没有 deadline,单测里不好写)。
`tests/agent/test_think_scrubber.py` 的 20 个用例覆盖了跨 delta 拼标签、边界规则、
孤儿闭标签、flush 语义,但**不覆盖带属性的标签、嵌套标签、以及与非流式路径的一致性**。

---

## 4. 发现清单

强度标注:**实跑复现** > **静态对读** > **推定未取证**(推定项一律在 §5,不进本节)。

### ■-1 webhook 会话把 `clarify` 留在工具集里,而 webhook 的默认投递没有回话通道

**强度:静态对读**(三处代码对读;未真起 webhook 端到端跑)。

`clarify` 在 webhook 的「安全子集」里:

toolsets.py:91 @ 863e313

```python
_HERMES_WEBHOOK_SAFE_TOOLS = [
    "web_search",
    "web_extract",
    "vision_analyze",
    "clarify",
]
```

webhook 适配器**没有覆写 `send_clarify`**(`grep -n "async def send_clarify" gateway/platforms/webhook.py`
零命中),因此走 `gateway/platforms/base.py:3780` 的编号列表默认实现,它最终调 `self.send(...)`。
而 webhook 的 `send` 在默认投递类型下是**写一行日志然后报成功**:

gateway/platforms/webhook.py:376 @ 863e313

```python
        deliver_type = delivery.get("deliver", "log")

        if deliver_type == "log":
            logger.info("[webhook] Response for %s: %s", chat_id, content[:200])
            return SendResult(success=True)
```

于是在 `gateway/run.py:5057` 的回调里 `send_ok = True`,agent 工作线程进入
`wait_for_response(clarify_id, 3600.0)`,而 webhook 交付**没有入站回复通道**可以解锁它。
后果是这一次 webhook 触发的 agent 回合原地占用一小时(`clarify_timeout: 0` 时永久),
并且正是本模块 docstring 声称超时机制要防的那个形态:

tools/clarify_gateway.py:12 @ 863e313

```python
    fires ``resolve_gateway_clarify(clarify_id, response)``,
  * supports timeouts so a user who never responds does NOT hang the agent
    thread forever (which would also pin the gateway's running-agent guard).
```

文档对这个对照关系的表述是自洽的但结果矛盾:

website/docs/reference/toolsets-reference.md:97 @ 863e313

> | `hermes-api-server` | Drops `clarify`, `text_to_speech`, `computer_use`, the kanban tools, and the desktop-GUI pane tools. Keeps everything else — suitable for programmatic access where user interaction isn't possible. |

website/docs/reference/toolsets-reference.md:117 @ 863e313

> | `hermes-webhook` | Restricted safe subset — only `web_search`, `web_extract`, `vision_analyze`, and `clarify`. Webhook-triggered runs get no terminal, file, or browser access. |

即:**「因为无法与用户交互所以去掉 clarify」的理由用在了 api-server 上,
但同样无法交互的 webhook 却把 clarify 留着,还称之为「安全子集」**。
(此处不判 ▲,因为两句文档各自都如实描述了代码;矛盾在代码的两处决定之间。)

### ■-2 `is_interrupted_tool_result` 是纯子串嗅探,一条正常的 `read_file` 结果会被整块删除

**强度:实跑复现**。

agent/replay_cleanup.py:35 @ 863e313

```python
    if "[command interrupted]" in lowered:
        return True
    if "exit_code" in lowered and ("130" in lowered or "-1" in lowered):
        return "interrupt" in lowered
```

`"-1" in lowered` 会命中任何形如 `2026-1-5` 的日期。**实跑复现**:

```console
  True  <- 'Log line: user reported \'[command interrupted]\' in ticket'
  True  <- 'exit_code: 0\nBuild dated 2026-10-01 was interrupted by nobody'
  True  <- '{"exit_code": 0, "stdout": "2026-1-5 the job was not interrupted"}'
```

端到端后果(**实跑复现**,`probe_misc2.py`):一次成功的 `read_file`,内容里恰好含
字面量 `[command interrupted]`(读日志、读工单、读本仓库自己的源码都可能),
在恢复时整个 `assistant(tool_calls) + tool` 块被删:

```console
  in : 4 msgs; out: 2 msgs
    user 'read the log'
    assistant 'The log shows ...'
```

模型在恢复后**看不到自己读过这个文件**,只看到一句凭空出现的「日志显示……」。
副作用工具方向被降级成 `[Orphan recovery: ...] effect_disposition=unknown`,同样是误报,
会让模型去检查一个根本没被打断的操作。

### ■-3 `is_managed_nous_gateway_url` 对主机名大小写敏感

**强度:实跑复现**(不可达性为**静态对读**)。

tools/managed_tool_gateway.py:298 @ 863e313

```python
    return bool(actual.scheme) and (actual.scheme, actual.netloc) == (expected.scheme, expected.netloc)
```

`urlsplit(...).netloc` **保留原始大小写**(`.hostname` 才小写化)。
**实跑复现**:`is_managed_nous_gateway_url('https://TOOL-GATEWAY.nousresearch.com/x')` → `False`。
DNS 主机名不区分大小写,所以这是同一个 origin 被判成不同 origin。
失败方向是**安全的**(拒发 bearer、拒绝上传),后果是功能不可用而不是凭据泄露。

**可达性**:目前不可达。`tools/flux3_video_tool.py` 里所有 URL 都由本地
`endpoints['base_url']` 拼出(`:650`、`:753`),从不使用网关返回的 URL,
所以传进来的大小写恒与 builder 输出一致。**搜索面**:
`grep -n "_call_gateway(\|_poll_until_done(\|f\"{endpoints\['base_url'\]}" tools/flux3_video_tool.py`,
以及 `grep -rn "managed_gateway_auth_headers\|is_managed_nous_gateway_url" --include=*.py .` 排除 tests
(命中仅 `tools/flux3_video_tool.py` 与本模块自身)。属**潜伏的加固缺口**,不是当前活的缺陷。

### ■-4 流式 think scrubber 不识别带属性的推理标签,导致推理内容流给用户、随后整条回复变空

**强度:实跑复现**。这是本片最强的一条。

标签是字面量拼出来的(`agent/think_scrubber.py:79-90`,已在 §2.5.2 引用),
所以 `<think type="x">` 不匹配任何开标签;而结尾的 `</think>` 会被
`_strip_orphan_close_tags` 当成孤儿闭标签**删掉**,于是推理内容**看起来像正常散文**发给用户。
而非流式路径的未闭合模式 `\b[^>]*>`(`agent/agent_runtime_helpers.py:78-81`,已引用)**接受属性**,
会从开标签一路吃到字符串末尾。两条路径**实跑复现**的分叉:

```console
input   : '<think type="x">secret</think>Visible'
  stream: '<think type="x">secretVisible'      ← 流式:推理内容原样送达用户
  regex : ''                                    ← 最终:连正文 'Visible' 一起被吃掉
```

用户体验:流式过程中完整看到模型的内部推理,流结束后那条消息变成空。
两个方向的错都发生在同一个输入上。挂载点确认在 `run_agent.py:6361-6363`(已引用),
即这条路径覆盖 CLI、网关、ACP、api_server、TTS 的所有外发增量。

同类但更弱的形态(均为**实跑复现**):`< think >`(标签内有空格)、
`<analysis>` / `<scratchpad>` / `<|thinking|>`(不在标签集里)一律原样透传;
嵌套 `<think>a<think>b</think>c</think>` 泄露外层尾巴 `c`——但嵌套这一条
**流式与非流式结果一致**,是非贪婪语义的必然结果,不算路径分叉。

### ■-5 溢出的 hook 上下文以 0644 落盘,与仓库内同类敏感落盘的 0600/0700 惯例不一致

**强度:实跑复现**。

`tools/hook_output_spill.py:209-217`(已引用)用 `Path.write_text` + `Path.mkdir`,
不设 mode、不 chmod。**实跑复现**:

```console
mode: 644   dir mode: 755
content: 'SECRET-TOKEN-abcdefghijklmnopqrstuvwxyz-END\n'
```

落盘的是**任意 hook 注入的上下文**——一个 dump 环境变量、贴出配置文件、
或把 API 响应原样返回的 hook,其产物就落在 `~/.hermes/hook_outputs/<session>/<uuid>.txt`,
同机其他用户可读。

**对照**:同一个仓库对「把会话内容落盘」这件事有 0700/0600 的先例——
`gateway/shutdown_flush.py` 落的是**待发送的会话消息**:

gateway/shutdown_flush.py:43 @ 863e313

```python
    flush_dir = get_hermes_home() / "pending_messages"
    flush_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        os.chmod(flush_dir, 0o700)
```

**搜索面**:`grep -rn "0o600\|0o700" --include=*.py .` 排除 tests,得 ~19 处命中,
分布在 `cli.py`、`gateway/shutdown_flush.py`、`gateway/pairing.py`、
`gateway/platforms/weixin.py`、`gateway/platforms/api_server.py`、`cron/jobs.py`、
`cron/suggestions.py`、`agent/proxy_sources/iron_proxy.py`。
`tools/hook_output_spill.py` 不在其中。

### ■-6 `DebugSession` 在模块 import 时定格 `get_hermes_home()`,多 profile 下调试日志会写错 profile

**强度:静态对读**(机制链清晰;未在真多 profile 网关下复现)。

`tools/debug_helpers.py:47`(已在 §2.9 引用)是
`self.log_dir = get_hermes_home() / "logs"`,而三个实例都在模块级构造
(`tools/web_tools.py:433`、`tools/vision_tools.py:72`、`tools/image_generation_tool.py:443`)。

`get_hermes_home()` 是**上下文局部**的:

hermes_constants.py:114 @ 863e313

```python
def get_hermes_home() -> Path:
    """Return the Hermes home directory (default: platform-native path).

    Resolution order: context-local override (see
    :func:`set_hermes_home_override`) → ``HERMES_HOME`` env var → the
    platform-native default.  This is the single source of truth — all other
    copies should import this.
```

所以在一个进程服务多个 profile 的网关里,所有 `*_TOOLS_DEBUG` 日志都会落到
**import 时刻那个 profile** 的 `logs/` 下,与 `tools/tool_backend_helpers.py:199-208`
那段「多路复用下 profile scope 是权威」的原则相悖。
同一个 `get_hermes_home()`,`tools/hook_output_spill.py:122` 在**落盘时**调用(正确),
`tools/debug_helpers.py:47` 在**import 时**调用(定格)。
同样地,`self.enabled` 也定格,因此 import 之后再设环境变量不生效。
影响面限于开启了 `WEB_TOOLS_DEBUG` / `VISION_TOOLS_DEBUG` / `IMAGE_TOOLS_DEBUG` 的场景。

### ■-7 clarify 超时提示对小于 60 秒的超时会说「0m」

**强度:实跑复现**(算术);**静态对读**(触发路径)。

gateway/run.py:5065 @ 863e313

```python
            if response is None or response == "":
                # Timeout or session-boundary cancellation
                return f"[user did not respond within {int(timeout / 60)}m]"
```

`int(30/60) == 0`、`int(0/60) == 0`(**实跑复现**)。于是:
`agent.clarify_timeout: 30` 超时后模型收到「user did not respond within **0m**」;
`agent.clarify_timeout: 0`(无限等待)被 `clear_session` 取消时,同样报「within 0m」——
而这条路径根本没有超时。同一句话把「超时」和「会话被清理」也混在了一起
(`clear_session` 返回 `""`、超时返回 `None`,原语区分得开,调用方合并了)。
纯提示文案缺陷,不影响控制流。

### ◇-1 `clear_session` 在单条 clarify 发送失败时连带取消整个会话的待决 clarify

**强度:实跑复现**。

`gateway/run.py:5060` 在 `send_ok=False` 时调 `clear_session(session_key)`,
而 `tools/clarify_gateway.py:364-378`(已引用)会解锁**该会话下所有** entry。
**实跑复现**:同一 session 注册两条,`clear_session` 返回 `2`。
当前是否会有并发的多条待决 clarify,取决于 agent 是否被允许并行发起 clarify:

website/docs/developer-guide/agent-loop.md:134 @ 863e313

> - Exception: tools marked as interactive (e.g., `clarify`) force sequential execution

所以现状下大概率只有一条。属于「实现比意图宽」的形状,不是当前活的 bug。

### ◇-2 `register` 与 `wait_for_response` 之间没有 finally 保护,注册后不等待会永久泄漏 entry

**强度:实跑复现**。

**实跑复现**:只调 `register("leak", "sess4", ...)` 不调 `wait_for_response`,
`_entries` / `_session_index` 里那条永远留着:

```console
  _entries keys after register-only: ['leak']
  _session_index: {'sess4': ['leak']}
```

清理只发生在 `wait_for_response` 的收尾和 `clear_session` 里:

tools/clarify_gateway.py:148 @ 863e313

```python
    with _lock:
        # Remove from indices regardless of resolution outcome.
        _entries.pop(clarify_id, None)
        ids = _session_index.get(entry.session_key)
        if ids and clarify_id in ids:
            ids.remove(clarify_id)
            if not ids:
                _session_index.pop(entry.session_key, None)
```

`gateway/run.py:4990-5061` 的回调在 `register` 之后、
`wait_for_response` 之前还有若干可能抛异常的步骤(`pause_typing_for_chat`、
`flush_pending_sync`、`safe_schedule_threadsafe`),它们都被各自的 `try/except` 包住,
所以现状下不会跳过 `wait_for_response`。但**这份保证来自调用方的纪律,而不是原语本身**。
`unregister_notify` 会兜底调 `clear_session`,是目前唯一的回收网:

tools/clarify_gateway.py:448 @ 863e313

```python
def unregister_notify(session_key: str) -> None:
    """Drop the per-session notify callback and cancel any pending clarify entries."""
    with _lock:
        _notify_cbs.pop(session_key, None)
    # Cancel any pending entries so blocked threads unwind when the run
    # ends (interrupt, completion, gateway shutdown).
    clear_session(session_key)
```

### ◇-3 「什么算推理标签」在全仓被独立实现了至少 8 处,属性策略与标签集互不一致

**强度:实跑复现**(表格里每一处的形态与属性策略都由源码逐条核对)。
详见 §2.5.5 的表与搜索面。`gateway/stream_consumer.py:175` 的
「Must stay in sync with cli.py … and run_agent.py …」只点了 2 个同步对象。

### ◇-4 溢出文件没有任何清理机制

**强度:实跑复现**(搜索面完整)。

**搜索面**:`git grep -n "hook_outputs"`(**全部已跟踪文件,不限扩展名**),
全部 8 处命中为:`tools/hook_output_spill.py` 2 处(自身)、
`tests/tools/test_hook_output_spill.py` 4 处、`website/docs/developer-guide/plugins/index.md` 2 处。
**没有任何 TTL、上限、`/new` 时清理、或 `hermes` 子命令**会删这个目录。
文档也只说写进去,不提清理:

website/docs/developer-guide/plugins/index.md:645 @ 863e313

> Per-hook context is capped at `10,000` characters by default. Anything above the cap is written to `$HERMES_HOME/hook_outputs/<session_id>/<uuid>.txt` and replaced with a head/tail preview plus the saved path.

模块自己的 docstring 说「Spill files are grouped by session so a ``/new`` session doesn't grow
them forever in one directory」——注意这句只承诺**不在一个目录里无限增长**,
没有承诺**总量有限**。字面为真,故不判 ▲。

### ◇-5 `propagate_context_to_thread` 返回的包装器不能并发复用,该约束未文档化

**强度:实跑复现**。

`tools/thread_context.py:78` 的 `ctx = contextvars.copy_context()` 与 `:118` 的 `ctx.run(_inner)`
决定了:同一个包装器在两个线程上并发调用时,第二个抛
`RuntimeError: cannot enter context: <_contextvars.Context object at 0x...> is already entered`
(**实跑复现**);串行复用则正常(两次串行调用分别返回 6 和 8)。
模块 docstring 的用法示例只说「在父线程调用它、把返回值作为 worker 的 target」,
没有说「一个包装器只能给一个线程」:

tools/thread_context.py:23 @ 863e313

```python
returned callable as the worker's target::

    t = threading.Thread(target=propagate_context_to_thread(loop_fn), args=(...))
    # or
    executor.submit(propagate_context_to_thread(worker_fn), *args)
```
**搜索面**:`git grep -n "propagate_context_to_thread(" -- '*.py'` 排除 `tests/` 与本模块,
9 个调用点(`agent/tool_executor.py:1178`、`tools/async_delegation.py:804`/`:1045`、
`tools/code_execution_tool.py:1146`/`:1422`、`agent/moa_loop.py:857`、
`agent/conversation_compression.py:925`、`model_tools.py:177`、`run_agent.py:1814-1820`)
**全部在提交处内联构造**,无一处把包装器提到循环外。故为潜伏约束,非活的缺陷。

### ◇-6 高危确认语的过期清单只覆盖英文与三条繁体中文

**强度:实跑复现**。

agent/replay_cleanup.py:217 @ 863e313

```python
_DANGEROUS_CONFIRMATION_PATTERNS: tuple = (
    "confirm forced restart",
    "confirm forced reboot",
    "confirm shutdown",
    "confirm reboot",
    "confirm power off",
    "yes, delete everything",
    "confirm wipe",
    "confirm factory reset",
    # i18n variants observed in the original incident
    "確認強制重開機",
    "確認強制重開",
    "確認重啟",
)
```

注释里 "i18n variants observed in the original incident" 已承认这是**从一次事故里抄下来的清单**,
不是一个语言无关的机制。任何用其他语言(简体中文「确认关机」、日语、西班牙语……)
确认的用户,#59607 那条保护对他完全无效。
另外该函数只检查 `role == "user"`(**实跑复现**:assistant 角色的同样文本不被涂改),
所以若确认语被 assistant 复述或落进工具结果,它照样活着。

### ◇-7 `TOOL_GATEWAY_SCHEME=http` 会让 Nous OAuth bearer 走明文,且不限于回环地址

**强度:实跑复现**。

tools/managed_tool_gateway.py:147 @ 863e313

```python
def get_tool_gateway_scheme() -> str:
    """Return configured shared gateway URL scheme."""
    scheme = os.getenv("TOOL_GATEWAY_SCHEME", "").strip().lower()
    if not scheme:
        return _DEFAULT_TOOL_GATEWAY_SCHEME

    if scheme in {"http", "https"}:
        return scheme

    raise ValueError("TOOL_GATEWAY_SCHEME must be 'http' or 'https'")
```

**实跑复现**(`TOOL_GATEWAY_SCHEME=http`,token_reader 注入 `'SECRET'`):

```console
    build('tool')  = http://tool-gateway.nousresearch.com
    is_managed('http://tool-gateway.nousresearch.com/api/flux3/x') = True
    auth_headers(...) = {'Authorization': 'Bearer SECRET'}
```

即 `Authorization: Bearer <Nous 访问令牌>` 会被明文发到一个**公网主机名**。
源码里给本地网关留口子的理由是「SSRF 防护会拒掉 127.0.0.1 上的本地网关」:

tools/managed_tool_gateway.py:414 @ 863e313

```python
        # protects against nothing and would reject a local gateway on
        # 127.0.0.1, so it uses a plain client. The PUT target, by contrast, is
        # a URL the gateway *returned*, so it keeps the SSRF-safe client as
        # defense in depth (real presigned URLs are public R2, which it allows).
```

即这类开关是为本地开发准备的,但 `TOOL_GATEWAY_SCHEME` 是**全局**的,没有限制成回环/私网地址。
同理 `TOOL_GATEWAY_DOMAIN=evil.example` 会让 `is_managed_nous_gateway_url` 对
`https://tool-gateway.evil.example/...` 判 True 并附上 bearer(**实跑复现**)。
这是「env 可信」的设计前提,但源码里这句话的措辞比实际保证要强:

tools/managed_tool_gateway.py:284 @ 863e313

```python
    Anything granting a URL extra trust — our bearer, reading files off disk to
    upload — must gate on this rather than on a name, so an arbitrary URL can
    never inherit that trust.
    """
```

闸门是**相对于同一份 env 派生的 origin** 自比对,不是钉死在 nousresearch.com。

### ◎-1 `_build_preview` 在 head+tail > 总长时会重复输出中间内容

**强度:实跑复现**。默认配置下不可达(10000 vs 500+500),仅在自定义
`max_chars < preview_head + preview_tail` 时出现:

```console
[hook output truncated — 10 chars; full content saved to /x]
--- head ---
01234567
--- tail ---
23456789
```

对应代码:

tools/hook_output_spill.py:142 @ 863e313

```python
    head_chunk = text[:head] if head > 0 else ""
    tail_chunk = text[-tail:] if tail > 0 and total > head else ""
```

判据是 `total > head`,不是 `total > head + tail`。纯观感问题,列在这里备查。

---

## 5. 未取证 / 推定

以下各条**没有取到证据**,不得当作结论传下去:

1. **webhook 端到端确实会挂满一小时(■-1 的最后一跳)。** 我核到了三处代码
   (`toolsets.py:91`、`gateway/platforms/webhook.py:376`、`gateway/run.py:5057`),
   但**没有真起一个 webhook 路由跑一次带 clarify 的回合**,也没有确认
   webhook 会话在 `gateway/run.py` 里一定拿到 `_clarify_callback_sync`
   (`ctx._status_adapter` 对 webhook 是否非空未验)。若 `ctx._status_adapter` 为 None,
   回调在 `gateway/run.py:4992` 直接 `return ""`,则不挂。这是本条断言唯一的缺口。

2. **`deliver: github_comment` 等非 log 投递类型下 clarify 的行为。**
   `gateway/platforms/webhook.py:382` 起还有其他投递分支,未逐一读。

3. **transcript 持久化层是否给 user 消息写 `timestamp`。**
   `strip_stale_dangerous_confirmations` 的整层保护依赖这个字段
   ,但字段由持久化层写入,不在本片文件里,未追。

   agent/replay_cleanup.py:304 @ 863e313

   ```python
               ts = msg.get("timestamp")
               if ts is not None and (now - float(ts)) > expiry_seconds:
   ```

4. **`agent.secret_scope.is_multiplex_active()` 的实际生效范围。**
   §2.3.2 那段短路逻辑的重要性完全取决于它在什么时候返回 True,未读该模块。

5. **`tool_may_have_side_effect` 的判定口径。**
   `agent/replay_cleanup.py` 的「删 vs 降级」分档完全依赖它,但它在
   `agent/tool_result_classification.py` 里,不在本片,未读。误判方向未知。

6. **`_flatten_choice` 里被排除的 `name`/`value` 键是否真的会造成问题。**
   docstring 给了理由(组件形状字段可能装枚举原值),但没有 issue 编号,未找到对应事故。

7. **托管媒体上传的 presign 响应契约(`uploadUrl` / `token` 字段名)是否与网关实际一致。**
   无凭据、无法真跑;仅读出客户端侧期望:

   tools/managed_tool_gateway.py:432 @ 863e313

   ```python
           upload_url = payload.get("uploadUrl") if isinstance(payload, dict) else None
           token = payload.get("token") if isinstance(payload, dict) else None
           if not (isinstance(upload_url, str) and upload_url and isinstance(token, str) and token):
               raise RuntimeError("the gateway's upload response was malformed")
   ```

8. **`peek_nous_access_token` 与 `read_nous_access_token` 在真实 OAuth 刷新下的行为。**
   `hermes_cli/auth.resolve_nous_access_token` 未读,刷新失败时回落到过期 cached_token 的后果未验证:

   tools/managed_tool_gateway.py:142 @ 863e313

   ```python
           logger.debug("Nous access token refresh failed: %s", exc)

       return cached_token
   ```

9. **■-6 在真实多 profile 网关下的复现。** 机制链是静态对读出来的
   (模块级构造 + 上下文局部的 `get_hermes_home`),没有真起多 profile 环境验证。

10. **`_MEDIA_UPLOAD_PUT_WRITE_TIMEOUT_SECONDS = 300` 与「50MB 视频」的对应关系。**
    源码注释声称上限约 50MB:

    tools/managed_tool_gateway.py:343 @ 863e313

    ```python
    # The PUT carries up to 50MB of video; a flat 60s would fail a legitimate
    # clip on an ordinary residential uplink, so only the write phase is long.
    _MEDIA_UPLOAD_PUT_READ_TIMEOUT_SECONDS = 60.0
    ```

    但代码里没有任何长度检查,这个数字是服务端的还是客户端的,未证。

---

## 6. 本片移交项

| 编号 | 锚点(带声明式摘录) | 一句话现象 | 建议轮次 |
|---|---|---|---|
| H-R9D-F-a | `toolsets.py:94`:`    "clarify",` | webhook 的「安全子集」含 `clarify`,而 `gateway/platforms/webhook.py:378` 的 `if deliver_type == "log":` 分支只写日志就报 success,agent 会为一个没人能答的问题阻塞到 `agent.clarify_timeout`(默认 3600s);需真起一次 webhook 回合确认 `ctx._status_adapter` 非空 | R10 网关片 |
| H-R9D-F-b | `agent/think_scrubber.py:89`:`    _OPEN_TAGS: Tuple[str, ...] = tuple(f"<{name}>" for name in _OPEN_TAG_NAMES)` | 字面量标签集不认 `<think type="x">`,推理内容随流式增量原样送达用户;而 `agent/agent_runtime_helpers.py:79` 的未闭合正则用 `\b[^>]*>` 接受属性、会把整条回复吃空——同一输入两条路径结果相反 | R10 隐私/输出片 |
| H-R9D-F-c | `agent/replay_cleanup.py:304`:`            ts = msg.get("timestamp")` | 高危确认语过期保护对**不带 `timestamp`** 的历史消息完全不生效;该字段由持久化层写入,需在会话存储片确认哪些恢复路径带时间戳 | R10 状态/持久化片 |
| H-R9D-F-d | `agent/replay_cleanup.py:37`:`    if "exit_code" in lowered and ("130" in lowered or "-1" in lowered):` | `"-1"` 子串会命中 `2026-1-5` 这类日期,一次成功的 `read_file` 结果因内容含 `[command interrupted]` 被整块从回放历史删除(实跑复现);判定依赖的 `tool_may_have_side_effect` 在 `agent/tool_result_classification.py`,本片未读 | R10 工具分类片 |
| H-R9D-F-e | `agent/process_bootstrap.py:1`:`"""Process-level bootstrap helpers for ``run_agent``.` | 本模块**不 spawn 子进程、不构造子进程环境**(文件内 `subprocess\|Popen\|os\.exec\|fork\|spawn\|env=\|environ\[` 零命中),「凭据是否继承给子进程」这个问题需要去找真正 spawn 的模块(`tools/code_execution_tool.py`、`tools/terminal_tool.py`、`agent/environments/*`) | R10/R11 执行环境片 |
| H-R9D-F-f | `tools/managed_tool_gateway.py:298`:`    return bool(actual.scheme) and (actual.scheme, actual.netloc) == (expected.scheme, expected.netloc)` | 用 `netloc`(保留大小写)而非 `hostname`(小写化)比对,`https://TOOL-GATEWAY.…` 被判非托管、bearer 不发;当前所有调用方都自拼 URL 故不可达,若将来有调用方使用网关返回的 URL 即活化 | R11 安全复核 |
| H-R9D-F-g | `tools/hook_output_spill.py:216`:`        spill_path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")` | 任意 hook 注入上下文以 0644 落盘、目录 0755、无任何清理机制;对照 `gateway/shutdown_flush.py:44` 的 `flush_dir.mkdir(parents=True, exist_ok=True, mode=0o700)` | R11 安全复核 |
| H-R9D-F-h | `tools/debug_helpers.py:47`:`        self.log_dir = get_hermes_home() / "logs"` | 在模块 import 时定格 profile 感知的 `get_hermes_home()`,多 profile 网关下三个工具的调试日志会写进 import 时那个 profile;对照同一函数在 `tools/hook_output_spill.py:122` 是落盘时调用 | R11 多 profile 片 |

---

## 7. 交付自检

**基线只读**:交付前实跑,输出为空。

```verify
git -C /home/user/hermes-agent status --porcelain
```

```console
(空输出,退出码 0)
```

`git -C /home/user/hermes-agent log -1 --format=%H` = `863e31318553cda8ad61df681d08175364d4164b`,与基线一致。
测试运行会写 `test_durations.json`,但该文件不被 `git status --porcelain` 报告(未跟踪且被忽略),
上面这条命令在**跑完全部 20 个测试文件之后**执行,输出仍为空。

**未装任何包**:全程未执行 `pip install` / `venv` 扩包;venv 包数交付前后均为 **87**
(`/home/user/hermes-venv/bin/pip list | tail -n +3 | wc -l` = 87,
`ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l` = 87)。
所有跑基线代码的命令均带 `HERMES_DISABLE_LAZY_INSTALLS=1`。

**未改 `scripts/`**:本轮只写 `/home/user/hermes-study/notes/r9d-raw-gateway-clarify-turn-misc.md`
一个文件;探针脚本写在会话临时目录,不入库。

**引用关卡**(本文件单独跑):

```verify
python3 scripts/verify_citations.py /home/user/hermes-agent notes/r9d-raw-gateway-clarify-turn-misc.md
```

```console
citations=110  OK=80  UNCHECKED=30
可校验比例 OK/110 = 72.7%
table_anchors=20  OK=16  UNCHECKED=4
OK: every code-block-backed citation matches the baseline
```

即 **可校验比例 72.7%,高于 70% 下限**;无 MISMATCH、无 BLOCK-DRIFT、无 TABLE-DRIFT。
移交表 8 条锚点全部使用「锚点 + 紧跟反引号摘录」的声明式写法,均被机械校验。

**14 个文件全部读完**,非抽样:`tools/__init__.py`(25)、`tools/budget_config.py`(114)、
`tools/clarify_gateway.py`(459)、`tools/clarify_tool.py`(266)、`tools/debug_helpers.py`(105)、
`tools/hook_output_spill.py`(232)、`tools/managed_tool_gateway.py`(452)、
`tools/thread_context.py`(120)、`tools/tool_backend_helpers.py`(311)、`agent/__init__.py`(8)、
`agent/process_bootstrap.py`(227)、`agent/replay_cleanup.py`(323)、
`agent/think_scrubber.py`(396)、`agent/title_generator.py`(402)= 3440 行。
另为交叉验证读了 `gateway/run.py`、`gateway/platforms/base.py`、`gateway/platforms/webhook.py`、
`gateway/stream_consumer.py`、`agent/agent_runtime_helpers.py`、`agent/auxiliary_client.py`、
`agent/conversation_loop.py`、`cli.py`、`toolsets.py`、`tools/flux3_video_tool.py`、
`tools/delegate_tool.py`、`agent/tool_executor.py`、`hermes_cli/oneshot.py`、
`hermes_constants.py`、`gateway/shutdown_flush.py`、`agent/jiter_preload.py` 的相关片段。
