# R9B 底稿 · 视觉理解与终端呈现

> 证据约定:凡对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` **单独成行、置于代码块之前**,
> 紧跟逐字源码摘录。非源码块显式标语言(`verify` / `text` / `console`)。
> 基线只读,收工前 `git -C /home/user/hermes-agent status --porcelain` 为空。

---

## 0. 本簇范围与文件清单

本轮精读 12 个文件,合计 5,214 行(`wc -l` 实测):

```verify
cd /home/user/hermes-agent && wc -l tools/vision_tools.py agent/display.py \
  agent/markdown_tables.py agent/i18n.py agent/portal_tags.py tools/terminal_hints.py \
  tools/focus_pane_tool.py agent/thread_scoped_output.py agent/reactions.py \
  tools/react_to_message_tool.py agent/battery.py agent/onboarding.py
# → 5214 total
```

| 文件 | 行数 | 一句话职责 |
|---|---:|---|
| `tools/vision_tools.py` | 1925 | 把一张图/一段视频送进模型上下文的两条路径(原生 / 辅助 LLM) |
| `agent/display.py` | 1547 | **工具调用**在 CLI 里的呈现:预览行、spinner、内联 diff、失败标记 |
| `agent/markdown_tables.py` | 309 | 用 `wcwidth` 重排模型吐出的 markdown 表格 |
| `agent/i18n.py` | 282 | 静态用户可见串的多语言查表 |
| `agent/portal_tags.py` | 144 | **不是呈现**:发往 Nous Portal 的用量归属标签 |
| `tools/terminal_hints.py` | 170 | **不是终端 UI**:terminal 工具失败时给模型的一句恢复建议 |
| `tools/focus_pane_tool.py` | 70 | 让 agent 在桌面 App 里切换面板 |
| `agent/thread_scoped_output.py` | 147 | 把 stdout/stderr 静音**限制在单个线程内** |
| `agent/reactions.py` | 56 | **不是平台 emoji 反应**:检测用户对 agent 的示好("good bot") |
| `tools/react_to_message_tool.py` | 167 | 是平台 emoji 反应:agent 给某条消息贴一个 emoji |
| `agent/battery.py` | 131 | 状态栏电量读数 |
| `agent/onboarding.py` | 266 | 一次性首触提示 + 首条消息的建档引导 |

**先说三个名字骗人的文件**(下面 §3 展开):`portal_tags` 与终端无关、
`terminal_hints` 与终端 UI 无关、`reactions` 与平台 reaction 无关。
这三个如果按名字归类,会把整簇的叙事讲歪。

---

## 1. `tools/vision_tools.py` — agent 怎么「看图」

### 1.1 结构测绘

自上而下五段:

| 段 | 行区间 | 内容 |
|---|---|---|
| 惰性依赖 + 配置解析 | 44–194 | `async_call_llm` 惰性绑定、下载超时、50 MB 下载上限、CPU 执行器 |
| 取图与格式归一 | 213–539 | URL 形状/SSRF 校验、magic-byte 嗅探、SVG 光栅化、下载重试 |
| 编码与尺寸控制 | 542–769 | base64 data URL、三档字节阈值、Pillow 逐级降采样 |
| 两条分析路径 | 772–1382 | 原生快路径(把像素塞进 tool_result)/ 旧路径(辅助 LLM 出文字) |
| 注册 + 视频 | 1464–1925 | `vision_analyze` 注册、`video_analyze` 全套 |

顶层没有类,全是模块级函数 + 两个 `registry.register(...)`。

`tools/vision_tools.py:44`

```python
# ``agent.auxiliary_client`` pulls credential_pool → hermes_cli.auth → httpx
# → rich (~50 ms cold); only vision handlers need it. Loaded lazily; both
# names stay module attributes so tests can keep patching
# ``tools.vision_tools.async_call_llm``. Truthy-skip: injected mocks win.
async_call_llm: Any = None
extract_content_or_reasoning: Any = None
```

**取舍**:模块被工具注册表在启动时导入,所以它必须便宜;把辅助客户端推迟到真的要调 LLM 时再拉,
省掉约 50 ms 冷启动。代价是两个模块级 `None` 变量 + 一个 `_load_auxiliary_client()` 守卫,
可读性差一点,但换来了「测试能直接 patch 模块属性」这一副作用。

### 1.2 一次「看图回答」的走法(原生快路径)

用户说「看看这张截图」→ 模型调 `vision_analyze(image_url=..., question=...)`。
入口是 `_handle_vision_analyze`,第一件事是问:主模型自己能不能看图?

`tools/vision_tools.py:1514`

```python
    if _should_use_native_vision_fast_path():
        logger.info("vision_analyze: native fast path")
        return await _vision_analyze_native(image_url, question, task_id=task_id)
```

判定逻辑分两步:先问路由「这一轮的图片输入模式是不是 native」,再问「这个 provider 收不收
tool_result 里的图片」。

`tools/vision_tools.py:872`

```python
        provider = _read_main_provider()
        model = _read_main_model()
        cfg = load_config()
        if decide_image_input_mode(provider, model, cfg) != "native":
            return False
        return (
            _supports_media_in_tool_results(provider, model)
            or _lookup_supports_vision(provider, model, cfg) is True
        )
```

第二问是一张手工维护的 provider 表。聚合器一律放行:

`tools/vision_tools.py:814`

```python
    _AGGREGATORS = {
        "openrouter", "nous", "vertex", "bedrock", "anthropic-vertex",
        "google-vertex",
    }
    if p in _AGGREGATORS:
        return True
```

Gemini 是唯一按**模型名**而非 provider 名分档的:

`tools/vision_tools.py:829`

```python
    # Gemini — gate on model name; older Gemini variants did not support
    # multimodal functionResponse. Gemini 3.x does.
    if p in {"google", "gemini", "google-gemini", "google-vertex-gemini"}:
        if not isinstance(model, str):
            return False
        m = model.strip().lower()
        if "gemini-3" in m or "gemini-pro-3" in m or "gemini-flash-3" in m:
            return True
        return False
```

**未知 provider 一律返回 False**(保守),再由 `ProviderProfile.supports_vision` 和用户显式
`model.supports_vision` 两个逃生口兜底。

走原生路径时,返回的**不是字符串**,而是一个「多模态信封」:

`tools/vision_tools.py:926`

```python
    return {
        "_multimodal": True,
        "content": [
            {"type": "text", "text": text_part},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ],
        "text_summary": summary,
        "meta": {
            "image_url": image_url[:200],
            "size_bytes": image_size_bytes,
            "native_vision": True,
        },
    }
```

信封统一用 **OpenAI 风格的 `image_url` + data URL**,再由各 provider 适配层翻译成
Anthropic 的 `tool_result` image block / Responses 的 `input_image` / OpenAI 的
`image_url` tool content。`text_summary` 是给不支持多模态 tool result 的 provider 的降级文本。

> **设计要点**:图片进 prompt 的形式**只有一种** —— base64 data URL,不走远程 URL 直传。
> 即便用户给的就是一个 http URL,也先下载到本地再编码(`_download_to_bytes` →
> `_image_to_base64_data_url`)。这样 provider 侧不需要能访问那个 URL,SSRF/权限/私有网段
> 三件事在本地一次性解决;代价是每张图都要过一遍本机的 CPU 编码和网络下载。

### 1.3 旧路径:辅助 LLM 出文字

主模型不能看图时,退回「找另一个能看图的模型,让它把图描述成文字」:

`tools/vision_tools.py:1519`

```python
    full_prompt = (
        "Fully describe and explain everything about this image, then answer the "
        f"following question:\n\n{question}"
    )
```

请求体就是标准的 OpenAI 多模态 `content` 数组:

`tools/vision_tools.py:1229`

```python
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": comprehensive_prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url
                        }
                    }
                ]
            }
        ]
```

**「先描述全部、再回答问题」**这个提示词形状是刻意的:辅助模型的输出会作为纯文本进入主模型
的上下文,主模型此后再也看不到像素,所以必须一次性把可能有用的信息全榨出来。这也是原生快路径
的价值 —— 它把这一层信息损失整个去掉了。

### 1.4 尺寸/token 成本怎么控:三档字节阈值 + 一档像素阈值

`tools/vision_tools.py:568`

```python
# Absolute hard ceiling for vision API payloads (20 MB) — above this, no major
# provider accepts the image and we reject outright.
_MAX_BASE64_BYTES = 20 * 1024 * 1024
```

`tools/vision_tools.py:581`

```python
_EMBED_TARGET_BYTES = 4 * 1024 * 1024
```

`tools/vision_tools.py:590`

```python
_EMBED_MAX_DIMENSION = 7900
```

`tools/vision_tools.py:594`

```python
_RESIZE_TARGET_BYTES = 5 * 1024 * 1024
```

四个数各管一件事:

| 常量 | 值 | 触发时机 |
|---|---|---|
| `_MAX_BASE64_BYTES` | 20 MB | 硬顶,超了直接报错 |
| `_EMBED_TARGET_BYTES` | 4 MB | **写进历史前**主动缩到这个大小(Anthropic 单图 5 MB 限,留余量) |
| `_EMBED_MAX_DIMENSION` | 7900 px | 同上,但管**边长**(Anthropic 8000 px 限,与字节限独立) |
| `_RESIZE_TARGET_BYTES` | 5 MB | provider 已经拒了之后**事后**缩到这个大小再重试一次 |

**为什么要有「主动缩」这一档**,注释说得很直白:

`tools/vision_tools.py:572`

```python
# Proactive embed cap (4 MB).  This is the size we resize an image DOWN to
# before embedding it into conversation history, regardless of the 20 MB hard
# ceiling.  Anthropic's per-image base64 limit is 5 MB; once an oversized image
# is baked into history (e.g. a vision tool-result), it is re-sent on every
# subsequent turn and permanently wedges the session with a 400 that retries
# can't clear (the bad bytes are immutable history).  Capping at embed time —
# with headroom under 5 MB — is the only durable fix.  Matches the post-failure
# shrink target in agent.conversation_compression so behaviour is consistent
# whether we resize proactively or reactively.
_EMBED_TARGET_BYTES = 4 * 1024 * 1024
```

这是本簇最值得抄的一条设计原则:**凡是要写进不可变历史的东西,校验必须发生在写入前,
不能依赖失败后重试**。一张 6 MB 的图混进历史,之后每一轮都会重发、每一轮都 400,
而重试不可能改掉已经在历史里的字节 —— 会话就此永久卡死。

像素维度那一档是后补的,补的是一个只有字节检查漏得掉的洞:

`tools/vision_tools.py:583`

```python
# Proactive embed dimension cap (px, longest side).  Anthropic enforces an
# 8000px per-side ceiling INDEPENDENTLY of the 5 MB byte cap — a tall full-page
# screenshot can be well under 5 MB yet far over 8000px (e.g. 1200×12000 at
# 0.06 MB), so the byte-only embed check above lets it slip into immutable
# history un-resized and the session bricks on a non-retryable 400.  We cap at
# 7900 (headroom under 8000) so the proactive resize shrinks tall small-byte
# images before they are embedded.
_EMBED_MAX_DIMENSION = 7900
```

原生路径里两个检查是**或**关系:

`tools/vision_tools.py:1042`

```python
        _over_bytes = len(image_data_url) > _EMBED_TARGET_BYTES
        _over_dims = await _run_encode_on_cpu_executor(
            _image_exceeds_dimension, temp_image_path, _EMBED_MAX_DIMENSION,
        )
        if _over_bytes or _over_dims:
            image_data_url = await _run_encode_on_cpu_executor(
                _resize_image_for_vision,
                temp_image_path, mime_type=detected_mime_type,
                max_base64_bytes=_EMBED_TARGET_BYTES,
                max_dimension=_EMBED_MAX_DIMENSION,
            )
```

降采样策略:**先减半边长(最多 5 轮),每一档再试 3 个 JPEG 质量**;PNG 没有质量档位,只能减尺寸。

`tools/vision_tools.py:715`

```python
    quality_steps = (85, 70, 50) if pil_format == "JPEG" else (None,)
```

`tools/vision_tools.py:747`

```python
        for q in quality_steps:
            buf = _io.BytesIO()
            save_kwargs = {"format": pil_format}
            if q is not None:
                save_kwargs["quality"] = q
            img.save(buf, **save_kwargs)
            encoded = base64.b64encode(buf.getvalue()).decode("ascii")
            candidate = f"data:{out_mime};base64,{encoded}"
            if len(candidate) <= max_base64_bytes and _dims_ok(img.width, img.height):
```

**注意:token 成本并没有被直接建模。** 代码里没有任何「按 token 计价/预算」的图片逻辑,
控的是**字节和像素**,靠 provider 侧的 tile 计费规则间接约束 token。
(搜索面:在 `tools/vision_tools.py` 全文 grep `token`,只有 `max_tokens=2000` / `max_tokens=4000`
两处输出上限,无输入侧 token 估算;见 §6 ◇-3。)

### 1.5 格式归一化:SVG 与冷门格式

MIME 判定**不信扩展名**,走 magic bytes:

`tools/vision_tools.py:245`

```python
def _detect_image_mime_type_from_bytes(data: bytes) -> Optional[str]:
    """Magic-byte MIME sniff on raw bytes (authoritative; no extension trust).

    Returns ``None`` for anything without a recognized image header — including
    SVG, which has no magic bytes. The resolver special-cases SVG (sniffs
    ``<svg``) and passes it through for rasterization at the call sites.
    """
```

允许直接内嵌的类型只有四种:

`tools/vision_tools.py:272`

```python
_ANTHROPIC_SUPPORTED_MEDIA_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/gif", "image/webp"}
)
```

其余格式在**编码之前**转成 PNG。SVG 需要外部光栅化器,四种依次尝试,全失败就给一条可操作的错误:

`tools/vision_tools.py:348`

```python
    if detected_mime == "image/svg+xml":
        if _rasterize_svg_to_png(image_path, out_path):
            return out_path, "image/png", None
        return (
            None,
            None,
            "This is an SVG, which vision models cannot read directly, and no "
            "SVG rasterizer is installed (tried cairosvg, svglib, rsvg-convert, "
            "inkscape). Convert the SVG to PNG first — e.g. open it in a browser "
            "and screenshot it, or install a rasterizer "
            "(`pip install cairosvg`) — then re-run vision_analyze on the PNG.",
        )
```

**取舍**:宁可失败也不内嵌不支持的 media_type —— 理由同 §1.4,不可变历史里的一个坏
media_type 会让会话永久 400。错误文案是写给**模型**看的(它会转述给用户),所以给了
两条具体出路而不是一句 "unsupported format"。

### 1.6 下载:SSRF 与「值不值得重试」

重定向也要重新校验 —— 这是 SSRF 最常见的绕过口:

`tools/vision_tools.py:426`

```python
    async def _ssrf_redirect_guard(response):
        """Re-validate each redirect target to prevent redirect-based SSRF.

        Without this, an attacker can host a public URL that 302-redirects
        to http://169.254.169.254/ and bypass the pre-flight is_safe_url check.

        Must be async because httpx.AsyncClient awaits event hooks.
        """
```

重试按**错误类别**分:

`tools/vision_tools.py:396`

```python
    if isinstance(error, (PermissionError, ValueError)):
        return False
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if 400 <= status < 500 and status != 429:
            return False
        return True
    return True
```

即:4xx(除 429)、策略拦截、体积超限 = 终局,立刻失败;429/5xx/网络抖动 = 重试,退避 2/4/8 秒。
**这条在 `_download_video` 里没有对应实现** —— 视频下载对所有异常一律退避重试三次
(见 §6 ■-1)。

体积上限 50 MB,先看 `Content-Length` 再看实际字节(防止服务端撒谎):

`tools/vision_tools.py:96`

```python
# Hard cap on downloaded image file size (50 MB). Prevents OOM from
# attacker-hosted multi-gigabyte files or decompression bombs.
_VISION_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
```

### 1.7 多图怎么办:CPU 突发闸

这是本簇最长的一段注释(`tools/vision_tools.py:101–129`),讲的是一次真实生产事故。
现象:模型对一段视频的每一帧都调一次 `vision_analyze`,几十个 base64 编码 + Pillow 缩放
同时开跑,把所有核吃满,共享事件循环没核可用,dashboard 的 `/api/status` 探活超时,
实例被判 UNHEALTHY —— 但其实什么都没崩。

修法**不是**限制并发分析数:

`tools/vision_tools.py:116`

```python
# The fix is NOT to cap how many vision analyses run — multi-image workflows
# ("compare these 6 screenshots", "read this 10-page scan") legitimately want
# high concurrency, and the slow part (the LLM stream) is network-bound and
# harmless to the loop. We cap ONLY the CPU burst: the encode/resize is offloaded
# to a dedicated, bounded executor sized to the host's usable core count. That
# is the resource the incident actually exhausted (cores), so bounding it to
# cores is *correct*, not an arbitrary number — excess encodes queue on the
# executor instead of all running at once, the LLM calls stay fully concurrent,
# and the loop always keeps a core. No fixed ceiling: the limit tracks the host.
```

于是有了一个**专用**执行器(不复用默认池,因为默认池和 gateway/web server 共享):

`tools/vision_tools.py:191`

```python
_vision_cpu_executor = ThreadPoolExecutor(
    max_workers=_VISION_CPU_WORKERS,
    thread_name_prefix="vision-encode",
)
```

worker 数默认 = 宿主可用核数(尊重 cgroup/affinity),可被 env 与 config 覆盖,但
**小于 1 的值一律忽略**,闸门无法被关掉:

`tools/vision_tools.py:160`

```python
    env_val = os.getenv("HERMES_VISION_MAX_CONCURRENCY", "").strip()
    if env_val:
        try:
            parsed = int(env_val)
            if parsed >= 1:
                return parsed
        except ValueError:
            pass
    try:
        from hermes_cli.config import cfg_get, load_config
        cfg = load_config()
        val = cfg_get(cfg, "auxiliary", "vision", "max_concurrency")
        if val is not None:
            parsed = int(val)
            if parsed >= 1:
                return parsed
    except Exception:
        pass
    return _detect_host_cpus()
```

老的「整体并发信号量」被降级成一个空壳,注释里留了墓志铭:

`tools/vision_tools.py:941`

```python
@contextlib.asynccontextmanager
async def _vision_concurrency_slot():
    """Deprecated no-op shim kept for backward compatibility.

    The fan-out cap was narrowed to the CPU-bound encode/resize burst only
    (see :data:`_vision_cpu_executor` / :func:`_run_encode_on_cpu_executor`).
    Holding a slot across the whole analysis serialized legitimate multi-image
    workflows behind the slow LLM call, which is exactly what we don't want.
    This context manager no longer gates anything; encode/resize is bounded
    where it actually runs. Retained only so any external caller importing it
    keeps working.
    """
    yield
```

**可迁移的原则**:限流要限在**真正被耗尽的资源**上。「同时跑几个视觉分析」不是资源,
「同时占几个核」才是;把闸门放在后者,上限就有一个正确的数(核数)而不是一个拍脑袋的数。

选 `ThreadPoolExecutor` 而不是 asyncio 信号量也有硬理由:每次视觉调用跑在
`model_tools._run_async` 的**每线程独立事件循环**上,绑定在单个 loop 上的 asyncio 原语
根本协调不了跨线程(`tools/vision_tools.py:126–129`)。

### 1.8 截图从哪来

`vision_analyze` 自己不截图,它只认一个**统一解析器** `tools/image_source.py`,
把 `data:` / `http(s)` / `file://` / 裸路径 / 沙箱容器路径五种来源统一成字节:

`tools/vision_tools.py:1154`

```python
        # Resolve the source to raw bytes through the single resolver (unifies
        # data:/http/file/local/container and enforces terminal-backend
        # confinement). Materialize to a temp file so the existing path-based
        # encode/resize pipeline below is reused verbatim.
```

`tools/image_source.py:87`

```python
    origin: str  # one of: data | http | file | local | container
```

关键的安全姿态在于:**终端后端不是本机时,宿主路径只有落在「媒体缓存目录」里才允许读**,
其余路径都改成在沙箱里 exec-read:

`tools/image_source.py:221`

```python
def _media_cache_roots() -> list:
    """Agent-managed media cache directories under HERMES_HOME (host side).

    The only host paths vision may read under a non-local backend: gateway-
    downloaded inbound media and the tools' own URL-download temp dirs. Covers
    the consolidated ``cache/`` layout and the legacy flat directories.
    """
```

截图的实际来源是**别的工具**:浏览器工具的 `browser_vision` 自己截图后走同一套分析
(`tools/browser_tool.py:4170`),桌面/剪贴板/PDF 上传落在 `~/.hermes/images/`
(`tools/image_source.py:233`),gateway 收到的图片落在 `cache/images`。
`vision_analyze` 只是这些产物的**消费端**。

### 1.9 有没有 OCR 回退

**没有。** 视觉链路里不存在任何 OCR 兜底:图读不了就报错,不会退化成本地文字识别。

搜索面:在基线仓库根对全部 `*.py` 执行大小写混合匹配 `ocr|OCR|tesseract|Tesseract`,
排除 `tests/`,命中 14 处,逐条判读后**没有一处**在视觉/图片链路上:

```verify
cd /home/user/hermes-agent && grep -rn "ocr\|OCR\|tesseract\|Tesseract" --include=*.py . \
  | grep -v "^./tests/"
# 命中分三类,均非 OCR 回退:
#   (a) skills/productivity/ocr-and-documents/  —— 独立技能,marker-pdf,不由视觉工具调用
#   (b) gateway/run.py:2765 —— 提示词里让模型「去用 ocr-and-documents 技能」
#   (c) 其余为 core.autocrlf / Socrates / tesseracttars 等误命中的子串
```

也就是说:OCR 在这个 harness 里是**一个技能(skill)**,不是视觉工具的降级路径。
模型要读扫描件,得自己决定去调那个技能。

### 1.10 video_analyze

同一文件后 370 行是视频版,结构对称但明显更粗糙:

- 扩展名 → MIME(不做 magic byte 嗅探),`.avi`/`.mkv` 一律谎报成 `video/mp4`
  (`tools/vision_tools.py:1554–1562`);
- 只有一个 50 MB 硬顶,20 MB 时打 warning,**没有任何降采样/转码**;
- 请求体用 `video_url` 类型(非 OpenAI 标准字段,实际是 OpenRouter/Gemini 方言);
- 超时下限 180 s(config 里配得更小也会被抬到 180)。

`tools/vision_tools.py:1731`

```python
        if len(video_data_url) > _MAX_VIDEO_BASE64_BYTES:
            raise ValueError(
                f"Video too large for API: base64 payload is {data_size_mb:.1f} MB "
                f"(limit {_MAX_VIDEO_BASE64_BYTES / (1024 * 1024):.0f} MB). "
                f"Compress or trim the video and retry."
            )
```

**注意:视频编码没有走 CPU 执行器**,`_video_to_base64_data_url` 在事件循环线程上直接
读 50 MB 文件并 base64 —— 正是 §1.7 那次事故要防的形状,只是发生在视频这一侧(见 §6 ■-2)。

---

## 2. `agent/display.py` — 终端呈现主干(以及它**不是**什么)

### 2.1 结构测绘 + 一句纠偏

`agent/display.py:1`

```python
"""CLI presentation -- spinner, kawaii faces, tool preview formatting.

Pure display functions and classes with no AIAgent dependency.
Used by AIAgent._execute_tool_calls for CLI feedback.
"""
```

**这个文件不渲染流式回答,也不做终端能力探测。** 它是「**工具调用**在终端里长什么样」的
纯函数库:输入是工具名 + 参数 + 结果 + 耗时,输出是一行字符串。

| 段 | 行区间 | 内容 |
|---|---|---|
| skin 感知的 ANSI/emoji | 24–171 | diff 配色从皮肤引擎懒解析并缓存;工具 emoji 三级回退 |
| shell 命令摘要 | 200–348 | 手写的引号感知分词器,把复合命令压成一行 |
| 显示前脱敏 | 361–414 | `browser_type` 的 text 强制过密钥正则 |
| 工具预览 | 417–595 | 每个内置工具挑一个「主参数」做单行预览 |
| 友好动词标签 | 598–757 | `web_search` → "Searching the web for …" |
| 平台状态短语 | 687–730 | Slack 的 `is running scripts/run_tests.sh…` |
| 内联 diff | 760–1047 | 写文件前快照 → 事后 unified diff → 上色 → 截断 |
| KawaiiSpinner | 1050–1278 | 三态降级的转圈动画 |
| 完成行 + 失败检测 | 1281–1542 | `┊ 🔍 search  xxx  1.2s` 这类行 |

流式回答的渲染在 `cli.py`(§3.1 会用到),终端宽度探测也在 `cli.py`
(`shutil.get_terminal_size`,`cli.py:2940` 等十余处)。

### 2.2 一次工具调用在终端里的走法

以 `terminal` 工具跑一条 `cd x && npm test 2>&1 | head -20` 为例:

**(1) 起 spinner**。`agent/tool_executor.py:26` 从本模块导入 `KawaiiSpinner` 等六个符号。

**(2) 算预览行**。`build_tool_preview` 对 `terminal` 走 `summarize_shell_command`:

`agent/display.py:325`

```python
def summarize_shell_command(command: str) -> str:
    """Compact shell wrapper/plumbing for display while preserving raw command elsewhere."""
    original = _oneline(command)
    if not original:
        return ""

    segments = _split_shell_compound(original)
    if len(segments) <= 1:
        return _clean_shell_segment(segments[0] if segments else original) or original

    core: list[str] = []
    for segment in segments:
        cleaned = _clean_shell_segment(segment)
        head = _shell_head_word(cleaned)
        if cleaned and head not in _SHELL_SILENT_HEADS and not _is_shell_boundary_echo(cleaned):
            core.append(cleaned)

    if not core:
        return original
    if len(core) == 1:
        return core[0]

    count = len(core) - 1
    return f"{core[0]} + {count} {'command' if count == 1 else 'commands'}"
```

这里有一个自写的**引号感知 shell 分词器**(`_split_shell_words` / `_split_shell_compound`,
`agent/display.py:208–289`),只为了把 `cd`、`export`、`set` 这类"管道"段和
`| head` 这类尾巴摘掉,让用户看见真正在跑的那条命令。

`agent/display.py:200`

```python
_SHELL_SILENT_HEADS = {"cd", "pushd", "popd", "export", "set", "unset", "source", ".", "true", "false", ":"}
_SHELL_PIPE_TAIL_HEADS = {"head", "tail", "wc", "sort", "uniq"}
```

**取舍**:为了一行显示,写了近 150 行手工解析器,而不是引入 `shlex` 或 bash 语法树。
理由推测是 `shlex` 处理不了 `&&`/`||`/重定向的分段语义,且这里只求「看起来对」,
解析错了最坏结果是预览难看一点 —— 不影响执行。(**未验证**:仓库里没有写出这条理由。)

**(3) 套友好动词**。

`agent/display.py:610`

```python
_TOOL_VERBS: dict[str, str] = {
    "web_search": "Searching the web",
    "web_extract": "Reading",
    "browser_navigate": "Browsing",
    "browser_click": "Clicking",
    "browser_type": "Typing",
    "read_file": "Reading",
    "write_file": "Writing",
    "patch": "Editing",
    "search_files": "Searching files",
    "terminal": "Running",
    "execute_code": "Running code",
    "image_generate": "Generating image",
    "video_generate": "Generating video",
    "text_to_speech": "Generating speech",
    "vision_analyze": "Looking at the image",
    "session_search": "Searching past sessions",
    "skill_view": "Reading skill",
    "skills_list": "Listing skills",
    "skill_manage": "Updating skill",
    "delegate_task": "Delegating",
    "cronjob": "Scheduling",
    "clarify": "Asking",
    "memory": "Updating memory",
    "todo": "Updating tasks",
}
```

`agent/display.py:598`

```python
# =========================================================================
# Friendly tool labels (human-phrased verbs for built-in tools)
#
# Turns "web_search <query>" into "Searching the web for <query>" — the
# ChatGPT-style "Searching…/Reading…" surface.  Curated and built-in only:
# we know each core tool's semantics, so the verb is fixed, not computed.
# Custom/plugin/MCP tools have no entry and fall back to the raw preview.
# =========================================================================
```

**「策展而非推导」**是这里的核心决定:动词表只覆盖内置工具,MCP/插件工具没有条目就回落到
原始预览。代价是新增内置工具要记得改表;收益是永远不会出现「Executing mcp__foo__bar-ing」
这类机器造句。

**(4) 收尾出完成行**。`cli.py:12114` 调 `get_cute_tool_message`,拿到形如
`┊ 💻 $  npm test  4.2s` 的一行。失败时前缀变红并附一个短后缀。

`agent/display.py:1321`

```python
    # Terminal: non-zero exit code is the canonical failure signal.
    if tool_name == "terminal":
        if isinstance(data, dict):
            exit_code = data.get("exit_code")
            if exit_code is not None and exit_code != 0:
                err_msg = data.get("error")
                if err_msg:
                    return True, f" [{_trim_error(str(err_msg))}]"
                return True, f" [exit {exit_code}]"
        return False, ""
```

多模态结果(§1.2 那个信封)在这里被特判成**成功**,因为它根本不是字符串:

`agent/display.py:1344`

```python
    # Generic heuristic for non-terminal tools
    # Multimodal tool results (dicts with _multimodal=True) are not strings —
    # treat them as successes since failures would be JSON-encoded strings.
    if not isinstance(result, str):
        return False, ""
```

整条渲染路径外面还包了一层"显示绝不打断回合"的兜底:

`agent/display.py:1532`

```python
def get_cute_tool_message(
    tool_name: str, args: dict, duration: float, result: str | None = None,
) -> str:
    """Render a completion label without letting cosmetic failures escape."""
    try:
        return _get_cute_tool_message(tool_name, args, duration, result=result)
    except Exception as exc:  # noqa: BLE001 — display must never abort a turn
        logger.debug("Tool completion label failed for %s: %s", tool_name, exc)
        safe_name = tool_name[:9] if isinstance(tool_name, str) and tool_name else "tool"
        safe_duration = f"{duration:.1f}s" if isinstance(duration, (int, float)) else "done"
        return f"┊ ⚡ {safe_name:9} completed  {safe_duration}"
```

### 2.3 非 TTY / prompt_toolkit:spinner 的三态降级

这是全簇「终端能力探测」最集中的一段,而且探的**不是**颜色能力,是**输出通道形态**:

`agent/display.py:1184`

```python
    def _animate(self):
        # When stdout is not a real terminal (e.g. Docker, systemd, pipe),
        # skip the animation entirely — it creates massive log bloat.
        # Just log the start once and let stop() log the completion.
        if not self._is_tty:
            self._write(f"  [tool] {self.message}", flush=True)
            while self.running:
                time.sleep(0.5)
            return

        # When running inside prompt_toolkit's patch_stdout context the CLI
        # renders spinner state via a dedicated TUI widget (_spinner_text).
        # Driving a \r-based animation here too causes visual overdraw: the
        # StdoutProxy injects newlines around each flush, so every frame lands
        # on a new line and overwrites the status bar.
        if self._is_patch_stdout_proxy():
            while self.running:
                time.sleep(0.1)
            return
```

三态:

| 通道 | 行为 |
|---|---|
| 管道 / CI / systemd(非 TTY) | 只打一行 `[tool] …`,结束时打 `[done] … (4.2s)`;**不动画** |
| prompt_toolkit `patch_stdout` | 完全静默,交给 TUI widget 画 |
| 真 TTY | `\r` 覆写动画,12 帧/秒,带皮肤"翅膀" |

`agent/display.py:1168`

```python
    def _is_patch_stdout_proxy(self) -> bool:
        """Return True when stdout is prompt_toolkit's StdoutProxy.

        patch_stdout wraps sys.stdout in a StdoutProxy that queues writes and
        injects newlines around each flush().  The \\r overwrite never lands on
        the correct line — each spinner frame ends up on its own line.

        The CLI already drives a TUI widget (_spinner_text) for spinner display,
        so KawaiiSpinner's \\r-based animation is redundant under StdoutProxy.
        """
```

还有两个细节值得抄:

**(a) 构造时就抓住 stdout**,防止子 agent 的 `redirect_stdout(devnull)` 把它变成黑洞:

`agent/display.py:1137`

```python
        # Capture stdout NOW, before any redirect_stdout(devnull) from
        # child agents can replace sys.stdout with a black hole.
        self._out = sys.stdout
```

**(b) 清行用空格而不是 `\033[K`**,因为 `patch_stdout` 下 ANSI 会被打乱:

`agent/display.py:1259`

```python
        is_tty = self._is_tty
        if is_tty:
            # Clear the spinner line with spaces instead of \033[K to avoid
            # garbled escape codes when prompt_toolkit's patch_stdout is active.
            blanks = ' ' * max(self.last_line_len + 5, 40)
            self._write(f"\r{blanks}\r", end='', flush=True)
```

**ANSI 与 markdown 怎么协调**:在 `display.py` 里两者根本不相遇 —— 这里只出 ANSI(diff 配色、
红色失败前缀),markdown 由 `cli.py` 的 `final_response_markdown` 决定 render/strip/raw,
表格那一步由 `agent/markdown_tables.py` 处理(§3.1)。**分层是清晰的:
display.py 管工具行(ANSI),cli.py 管回答体(markdown)。**

### 2.4 显示前脱敏

`agent/display.py:373`

```python
    Redaction is forced here regardless of the global ``security.redact_secrets``
    preference: a typed credential leaking into chat history is a security
    boundary, not mere log hygiene.
    """
```

`browser_type` 的 `text` 参数在进日志/进进度通知/进模型之前强制过一遍密钥正则,
但**只在识别出密钥形状时替换**,普通搜索词原样保留可读:

`agent/display.py:382`

```python
    redacted = redact_sensitive_text(needle, force=True)
    if redacted == needle:
        # Nothing secret-looking in the typed text; leave payload untouched.
        return value
```

### 2.5 内联 diff:先快照,后对比

写文件类工具在**执行前**先把目标文件读进内存:

`agent/display.py:837`

```python
def capture_local_edit_snapshot(tool_name: str, function_args: dict | None) -> LocalEditSnapshot | None:
    """Capture before-state for local write previews."""
    paths = _resolve_local_edit_paths(tool_name, function_args)
    if not paths:
        return None

    snapshot = LocalEditSnapshot(paths=paths)
    for path in paths:
        snapshot.before[str(path)] = _snapshot_text(path)
    return snapshot
```

执行后拿现盘对比出 unified diff,再逐行上色、按「最多 6 个文件 / 80 行」截断:

`agent/display.py:99`

```python
_MAX_INLINE_DIFF_FILES = 6
_MAX_INLINE_DIFF_LINES = 80
```

diff 的配色不是写死的,而是从皮肤引擎懒解析 + 进程内缓存;取不到就用一组暗色终端默认值:

`agent/display.py:45`

```python
def _diff_ansi() -> dict[str, str]:
    """Return ANSI escapes for diff display, resolved from the active skin."""
    global _diff_colors_cached
    if _diff_colors_cached is not None:
        return _diff_colors_cached

    # Defaults that work on dark terminals
    dim = "\033[38;2;150;150;150m"
    file_c = "\033[38;2;180;160;255m"
    hunk = "\033[38;2;120;120;140m"
    minus = "\033[38;2;255;255;255;48;2;120;20;20m"
    plus = "\033[38;2;255;255;255;48;2;20;90;20m"
```

注意用的是 **24-bit truecolor**(`38;2;R;G;B`),没有任何 8 色/256 色降级分支,
也没有 `NO_COLOR` / `TERM=dumb` 探测(搜索面见 §6 ◇-1)。

---

## 3. 逐机制

### 3.1 `agent/markdown_tables.py` — 为什么表格要单独 309 行

**问题**:模型按「一个字符 = 一格」来对齐 markdown 表格。CJK 和大多数 emoji 在终端里占**两格**,
于是表头对齐、每一行往右漂 N 格。

`agent/markdown_tables.py:1`

```python
"""CJK/wide-character-aware re-alignment of model-emitted markdown tables.

Models pad markdown tables assuming each character occupies one terminal
cell. CJK glyphs and most emoji render as two cells, so the model's
spacing collapses into drift the moment a table reaches a real terminal —
header pipes line up, every body row drifts right by N cells per CJK
char.
```

**做法**:用 `wcwidth.wcswidth` 算显示列宽重新补空格,保留管道和横线,让它在
`strip`(不渲染 markdown)模式下依然读得像表格。

难点一:`wcswidth` 对某些「emoji + 变体选择符」序列返回 `-1`。这里的处置是**钳到 0**
并把取舍写进文档:

`agent/markdown_tables.py:23`

```python
There is a small, intentional caveat: ``wcwidth`` returns ``-1`` for some
emoji-with-variation-selector sequences (e.g. ``⚠️``); we clamp those to
0 so they do not corrupt the column width math. The 1-cell drift on
those specific glyphs is preferable to silently widening every table
that contains one.
"""
```

难点二:**换行**。终端软折行会在视觉上毁掉列对齐,哪怕字节完全对齐。所以宽度超预算时
整表改成纵向 key-value:

`agent/markdown_tables.py:105`

```python
def _render_block(rows: List[List[str]], available_width: int | None = None) -> List[str]:
    """Render ``rows`` (header + body, divider implied) at uniform widths.

    If ``available_width`` is given and the rebuilt horizontal table
    would exceed it, fall back to a vertical key-value rendering so
    rows do not soft-wrap mid-cell — terminal soft-wrap destroys
    column alignment visually even when the underlying bytes are
    perfectly padded, which is exactly the "tables look broken"
    user report this code path is meant to address.
    """
```

`agent/markdown_tables.py:211`

```python
def _render_vertical(
    rows: List[List[str]], ncols: int, available_width: int
) -> List[str]:
    """Render a too-wide table as vertical ``Header: value`` rows.

    Mirrors Claude Code's narrow-terminal fallback in
    ``MarkdownTable.tsx``: each body row becomes a small block of
    ``Header: cell-value`` lines (continuation lines indented two
    spaces) separated by a thin ``─`` divider between rows.  Keeps
    every line narrower than ``available_width`` so the terminal does
    not soft-wrap mid-cell.
    """
```

难点三:**流式**。表格是逐行到达的,不能边到边排 —— 排到第三行才知道第一列该多宽,
而前两行已经打出去了。CLI 的做法是把表格行**攒到侧缓冲区**,块结束时一次性排版打印:

`cli.py:6829`

```python
        while "\n" in self._stream_buf:
            line, self._stream_buf = self._stream_buf.split("\n", 1)

            # Hold table-shaped lines in a side-buffer so we can re-pad
            # the whole block once it ends.  Streaming line-by-line, we
            # cannot re-align mid-table without reflowing already-printed
            # rows; the cost is that the user sees the table appear in a
            # single batch when the block closes instead of row-by-row.
            if self._in_stream_table:
                if looks_like_table_row(line) or is_table_divider(line):
                    self._stream_table_buf.append(line)
                    continue
                # Block ended — flush the realigned table, then fall
                # through to print the current (non-table) line.
                _flush_table_buf()
            elif looks_like_table_row(line):
                self._stream_table_buf.append(line)
                self._in_stream_table = True
                continue
```

宽度预算来自实时终端尺寸,并**故意留 2 格余量**防止 resize 竞态:

`cli.py:2927`

```python
def _terminal_width_for_streaming() -> int:
    """Display cells available inside the streamed response box.

    The streaming path prefixes every line with ``_STREAM_PAD`` (now
    empty — flush-left so copy/paste stays clean) inside an open
    response panel.  The realigner uses this number as its budget when
    deciding whether to keep a horizontal table or fall back to
    vertical key-value rendering.  We subtract a small safety margin
    so terminal-resize races don't push a borderline table into
    mid-cell soft-wrap.
    """

    try:
        cols = shutil.get_terminal_size((80, 24)).columns
    except Exception:
        cols = 80
    return max(20, cols - len(_STREAM_PAD) - 2)
```

`looks_like_table_row` 故意宽松,因为误判的代价只是**晚一行打印**:

`agent/markdown_tables.py:83`

```python
def looks_like_table_row(row: str) -> bool:
    """True when ``row`` could plausibly be a markdown table row.

    Used by streaming callers to decide whether to buffer an in-flight
    line. We are intentionally permissive here — the realigner itself
    only rewrites blocks that are accompanied by a divider, so a false
    positive here at most delays the print of one line.
    """
```

这个模块还被 gateway 的两个平台适配器复用(`gateway/platforms/helpers.py:325`、
`gateway/platforms/weixin.py:692`),它们只借 `split_table_row` 这一个纯函数,
注释里明确写着「三处共用同一个切分器」。

### 3.2 `agent/i18n.py` — 多语言

**范围极窄,而且写死在文档字符串里**:

`agent/i18n.py:1`

```python
"""Lightweight internationalization (i18n) for Hermes static user-facing messages.

Scope (thin slice, by design): only the highest-impact static strings shown
to the user by Hermes itself -- approval prompts, a handful of gateway slash
command replies, restart-drain notices.  Agent-generated output, log lines,
error tracebacks, tool outputs, and slash-command descriptions all stay in
English.
```

覆盖面实测:**17 种语言 × 351 条键 = 5,967 条串**。

```verify
cd /home/user/hermes-agent && ls locales/*.yaml | wc -l   # → 17
# 逐档展平计数(与 _flatten_into 同规则:只收字符串叶子):
python3 - <<'EOF'
import yaml, pathlib
def flat(n,p,o):
    if isinstance(n,dict):
        for k,v in n.items(): flat(v, f"{p}.{k}" if p else str(k), o)
    elif isinstance(n,str): o[p]=n
for f in sorted(pathlib.Path("locales").glob("*.yaml")):
    d={}; flat(yaml.safe_load(f.read_text(encoding="utf-8")) or {}, "", d)
    print(f.stem, len(d))
EOF
# → 每一档都是 351
```

支持语言表:

`agent/i18n.py:43`

```python
SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "en", "zh", "zh-hant", "ja", "de", "es", "fr", "tr", "uk",
    "af", "ko", "it", "ga", "pt", "ru", "hu", "ar",
)
DEFAULT_LANGUAGE = "en"
```

**语言怎么选**,三级 + 兜底:

`agent/i18n.py:221`

```python
def get_language() -> str:
    """Resolve the active language using env > config > default order."""
    env_lang = os.environ.get("HERMES_LANGUAGE")
    if env_lang:
        return _normalize_lang(env_lang)
    cfg_lang = _config_language_cached()
    if cfg_lang:
        return cfg_lang
    return DEFAULT_LANGUAGE
```

外加 `t(key, lang=...)` 的显式覆盖,共四级。别名表覆盖了自然语言名(`chinese`)、
本族名(`русский`、`한국어`、`العربية`)和区域标签(`zh-CN`、`fr-CA`),最后还兜一层
「砍掉区域后缀再试」:

`agent/i18n.py:137`

```python
    # Try stripping a region suffix (e.g. "pt-br" -> "pt" won't be supported,
    # but "zh-CN" -> "zh" will).
    base = key.split("-", 1)[0]
    if base in SUPPORTED_LANGUAGES:
        return base
    return DEFAULT_LANGUAGE
```

**查不到永不崩**是硬约束,三级回退:目标语 → 英文 → 键名本身。

`agent/i18n.py:250`

```python
    target = _normalize_lang(lang) if lang else get_language()
    catalog = _load_catalog(target)
    value = catalog.get(key)

    if value is None and target != DEFAULT_LANGUAGE:
        # Fall through to English rather than showing a key path to the user.
        value = _load_catalog(DEFAULT_LANGUAGE).get(key)

    if value is None:
        # Last-ditch: return the key itself.  A broken catalog should not
        # crash anything; it just looks ugly until someone fixes it.
        logger.debug("i18n miss: key=%r lang=%r", key, target)
        value = key
```

`str.format` 失败也不抛,直接返回未插值的原串(`agent/i18n.py:264–272`)。

目录定位支持打包场景(Nix 封装):

`agent/i18n.py:105`

```python
    override = os.getenv("HERMES_BUNDLED_LOCALES", "").strip()
    if override:
        candidate = Path(override)
        if candidate.is_dir():
            return candidate
        logger.warning(
            "HERMES_BUNDLED_LOCALES points to a non-directory path (%s); "
            "falling back to bundled/source locale resolution",
            override,
        )
```

**取舍**:整个模块 282 行、零第三方 i18n 框架(不用 gettext/babel),catalog 是扁平化
YAML + 进程内 `dict` 缓存 + `lru_cache(maxsize=1)` 的配置读取。
代价是没有复数规则、没有性别/格变化 —— 对「审批提示 + 少量 slash 回复」这个范围够用。

### 3.3 `agent/portal_tags.py` — portal tag 是什么

**先纠正命名歧义:这里的 "portal" 不是 UI 的传送门,是 Nous Portal(Nous 的 API 门户)。**
这个文件跟终端呈现毫无关系,解决的是「**用量归属**」:每一个打到 Nous Portal 的请求,
都要带同一组标签,好让 Nous 把用量归到 Hermes Agent 名下并按客户端版本分桶。

`agent/portal_tags.py:1`

```python
"""Centralized Nous Portal request tags.

Every Hermes request that hits the Nous Portal — main agent loop, auxiliary
client (compression / titles / vision / web_extract / session_search / etc.),
and any future code path — must carry the same product-attribution tags so
Nous can attribute usage to Hermes Agent and bucket it by client release.
```

**为什么要有这个模块**,理由写得很实在 —— 四个调用点曾经各写各的字面量,漂了:

`agent/portal_tags.py:20`

```python
Why one helper instead of inlining the literal at each site:
* Four call sites (main loop profile, aux client, run_agent compression
  fallback, web_tools fallback) used to drift apart — see PR #24194 which
  only got the aux site, leaving the main loop sending a different tag set.
* Tests should assert the same tag list everywhere; centralizing makes that
  assertion a one-liner against this module.
```

第二件事更有意思:**用 ContextVar 做「环境会话 id」**。主循环知道 session_id,但
compression / 标题生成 / vision / MoA 这几十个辅助调用点都不知道 —— 它们都从
`auxiliary_client.call_llm` 走,那里没有 session 句柄。与其给每个调用点加参数,
不如让主循环在回合入口**发布**一次:

`agent/portal_tags.py:54`

```python
_conversation_id: ContextVar[Optional[str]] = ContextVar(
    "nous_portal_conversation_id", default=None
)
```

`agent/portal_tags.py:135`

```python
    tags = ["product=hermes-agent", hermes_client_tag()]
    # Ambient context first: the agent loop publishes the lineage ROOT id
    # (stable across context-compression rotation and delegate subagent
    # trees), which is the better conversation key than a per-segment
    # session_id passed explicitly. The explicit argument remains as a
    # fallback for callers running outside any agent turn.
    effective = get_conversation_context() or session_id
    if effective:
        tags.append(conversation_tag(effective))
    return tags
```

选 `ContextVar` 而非模块全局的理由也写明了:一个进程里可能同时跑多个 agent
(gateway 会话、`delegate_task` 子 agent、批处理),模块全局会串号
(`agent/portal_tags.py:48–53`)。

还有一条反直觉的约束:

`agent/portal_tags.py:27`

```python
Do NOT pre-compute these as module-level constants in the consumers. The
version can change at runtime (editable installs, hot-reload tooling), and
``hermes_cli.__version__`` is the canonical source of truth.
"""
```

**可迁移原则**:一个需要出现在「所有出口」的横切事实(版本、租户、会话),
应该是**一个函数**而不是一堆常量,并且用 ContextVar 让深层调用点免于参数透传。

### 3.4 `agent/thread_scoped_output.py` — thread-scoped output 在隔离什么

**问题一句话**:`contextlib.redirect_stdout` 改的是**进程全局**的 `sys.stdout`。
后台线程(比如后台记忆/技能复盘)想把自己静音,一裹上去,同进程里
**其它线程**(比如 gateway 驱动 Telegram 长轮询的事件循环线程)的所有 `print` 也一起丢了。

`agent/thread_scoped_output.py:1`

```python
"""Thread-scoped stdout/stderr silencing for background worker threads.

``contextlib.redirect_stdout``/``redirect_stderr`` reassign the *process-global*
``sys.stdout``/``sys.stderr``.  When a daemon worker thread (e.g. the background
memory/skill review) wraps its whole body in those context managers, every other
thread in the process — including a gateway's asyncio event-loop thread driving a
Telegram long-poll — sees ``sys.stdout``/``sys.stderr`` pointing at ``devnull``
for the full duration.  Any bare ``print`` / ``sys.stderr.write`` from those other
threads is silently lost during that window (see issue #55769 / #55925).
```

**做法**:把 `sys.stdout` 换成一个**按线程路由**的代理。登记为"静音"的线程写进 devnull,
其它线程原样透传到安装时捕获的原流。

`agent/thread_scoped_output.py:54`

```python
    def _target(self) -> TextIO:
        if self._silenced.get(threading.get_ident(), 0) > 0:
            return self._sink
        return self._passthrough
```

计数而非布尔,所以同一线程嵌套静音能正确组合:

`agent/thread_scoped_output.py:48`

```python
        # ident -> nesting depth.  A thread is silenced while depth > 0, so
        # nested ``thread_scoped_silence()`` on the same thread composes
        # correctly (the inner exit decrements rather than fully clearing).
        self._silenced: dict[int, int] = {}
```

**最关键的设计取舍:装上去就永不卸载。**

`agent/thread_scoped_output.py:11`

```python
This module installs a thin proxy as ``sys.stdout``/``sys.stderr`` that routes
writes per-thread: threads registered as "silenced" go to a sink; every other
thread passes through to the *original* stream.  The proxy is installed once,
idempotently, and is never uninstalled (uninstalling would race other threads
mid-write), so the only observable effect for unregistered threads is one extra
attribute lookup per write.
"""
```

卸载会和正在写的线程竞态 —— 于是干脆不卸,代价是每次写多一次属性查找。这是一个
「**用一点点常驻开销换掉一整类竞态**」的典型决定。

代理还把 `write`/`flush` 的异常全吞掉(返回长度或 None),`isatty()` 出错返回 False,
`__getattr__` 转发到**当前线程的**目标流。唯一的例外是 `fileno()` —— 它不吞异常:

`agent/thread_scoped_output.py:98`

```python
    def fileno(self):  # type: ignore[no-untyped-def]
        return self._target().fileno()
```

安装时**不猜「真正的」流**,谁在位就拿谁当透传目标:

`agent/thread_scoped_output.py:114`

```python
        # Capture whatever is currently bound as the passthrough.  If a prior
        # global redirect_stdout is active we deliberately route non-silenced
        # threads to *that* (matching prior behaviour) rather than guessing at
        # the "real" stream.
        passthrough = current if current is not None else sink
```

全仓只有一个调用**模块** —— 后台复盘。搜索面:
`grep -rn "agent\.thread_scoped_output\|thread_scoped_silence" --include=*.py .`
排除 `tests/` 与模块自身,命中 4 行且全在 `agent/background_review.py`:
`:27` 导入、`:693` 一行注释、`:696` 与 `:1011` 两处 `with thread_scoped_silence():`。

### 3.5 `agent/reactions.py` + `tools/react_to_message_tool.py` — 两个同名不同物

**这两个文件不是一回事**,合在一起看才不会误解:

| | `agent/reactions.py` | `tools/react_to_message_tool.py` |
|---|---|---|
| 方向 | 用户 → agent | agent → 用户消息 |
| 是什么 | 检测用户在示好("good bot"、`<3`、❤️) | 给某条消息贴一个 emoji(iMessage tapback) |
| 触发者 | 每个用户回合自动跑,零 token | 模型主动调用的工具 |
| 出口 | `AIAgent.reaction_callback` → CLI 宠物/TUI 爱心/桌面飘心 | SessionDB + `desktop_ui.emit("message.reaction")` |

**(a) 检测侧**。纯正则,不调模型:

`agent/reactions.py:1`

```python
"""Token-free detection of user *reactions* to the agent.

Currently the only reaction is ``vibe`` — an expression of affection or
gratitude toward the agent (``ily``, ``<3``, ``love you``, ``good bot``, a heart
emoji, …). Detection is a curated regex/lexicon: **no model call, no tokens**.
```

刻意**只匹配"对 agent 的示好"而不是泛正面情绪**:

`agent/reactions.py:11`

```python
Generalized on purpose: :func:`detect_reaction` returns a reaction *kind*
string, so new kinds (other emoji reactions, etc.) can be added here without
touching any caller. We match affection specifically — not general positive
sentiment — so "this is great" does NOT fire, but "good bot" / "❤️" do.
"""
```

正则里连 `</3`(破碎的心)都排掉了:

`agent/reactions.py:35`

```python
            r"<3+",  # <3, <33 … but not </3
```

调用点在回合上下文里,包在 try/except 里、明确标注"纯装饰、绝不致命":

`agent/turn_context.py:601`

```python
    # Cosmetic side-signal: detect an affection "reaction" (ily / <3 / good bot)
    # and notify the host so it can play hearts. Token-free, never touches the
    # conversation, and never fatal — a purely optional UI beat.
    reaction_callback = getattr(agent, "reaction_callback", None)
    if reaction_callback is not None:
        try:
            from agent.reactions import detect_reaction

            kind = detect_reaction(original_user_message)
            if kind:
                reaction_callback(kind)
        except Exception:
            pass
```

**(b) 工具侧**。**平台差异怎么抹平:并没有在这里抹平。** 这个工具**只**服务桌面 App:

`tools/react_to_message_tool.py:1`

```python
#!/usr/bin/env python3
"""Let the agent react to a message with an emoji in the Hermes desktop app.

The conversational counterpart to the user's tapback: the same reaction store,
the same one-per-author semantics, just written with ``author="agent"``.

Gated on ``HERMES_DESKTOP`` (like the other GUI affordances) so it costs nothing
on every other surface — the platform adapters already expose reactions through
``send_message(action="react")``, and this is the desktop's equivalent.
```

也就是说:**Telegram/Discord/Slack 那边的 emoji 反应走的是 `send_message(action="react")`,
不是这个工具**;这个工具是桌面 App 缺 `send_message` 通路时的等价物。抹平发生在
`send_message` 那一层,不在这里。

默认目标是「触发本轮的那条用户消息」,并提供「往回数几条」:

`tools/react_to_message_tool.py:48`

```python
    row_id = message_row_id
    target_role = "user"
    if row_id is None:
        # Default target: the latest user message. `messages_back` steps to
        # earlier user turns (1 = the one before, etc.) for retroactive
        # reactions — quoting text would be ambiguous, ids aren't visible to
        # the model, but "two messages ago" is how a person thinks about it.
        back = max(0, int(messages_back or 0))
        row_id = db.latest_message_row_id(session_key, role="user", offset=back)
```

**两级开关**:环境变量 + 配置项,两个都要为真:

`tools/react_to_message_tool.py:92`

```python
def check_react_requirements() -> bool:
    """Desktop GUI only, and opt-in.

    HERMES_DESKTOP is set on the gateway the app spawns; the feature itself is
    off by default and enabled from Settings → Appearance (the desktop mirrors
    the toggle into ``display.message_reactions``).
    """
    if not env_var_enabled("HERMES_DESKTOP"):
        return False
    try:
        from hermes_cli.config import load_config_readonly

        display = load_config_readonly().get("display")
    except Exception:
        return False
    return isinstance(display, dict) and bool(display.get("message_reactions", False))
```

最值得注意的是**工具描述本身就是行为规范**,而且写得非常"人":

`tools/react_to_message_tool.py:112`

```python
    "description": (
        "React to a message with a single emoji, the way you'd tapback in iMessage. "
        "Reach for it when a reaction is what a person would do: something funny gets "
        "a 😂, warmth gets a ❤️, a plan you're on board with gets a 👍 — then just "
        "carry on with whatever the message actually needs. If a reaction says it "
        "all, it can BE the reply (skip the redundant 'sounds good!' turn). Use it "
        "like a person would: occasionally, when felt — not on every message, and "
        "never as a status signal. NEVER narrate or explain a reaction ('I reacted "
        "with...', 'Reacting now') — the emoji appearing on the bubble is the whole "
        "point, and commentary kills it. Defaults to the user's most recent message. "
        "One reaction per message: a different emoji replaces yours, an empty string "
        "retracts it."
    ),
```

「**别解说你的反应**」这条约束只能写在描述里 —— 没有代码能拦住模型多说一句话。
这是 tool description 作为**行为契约**而不仅是 API 文档的样本。

### 3.6 `tools/terminal_hints.py` — 不是终端提示,是失败恢复提示

**给谁看:模型,不是用户。** 命令非零退出时,原始 stderr 常把模型带进无效的诊断循环
(比如只有 `python3` 却反复重试 `python`)。这个模块在 terminal 工具的退出码语义表之上
加一层「输出模式」层。

`tools/terminal_hints.py:1`

```python
"""Output-pattern failure hints for the terminal tool.

When a command exits non-zero, the raw stderr often confuses models into
wasted diagnostic turns (e.g. retrying `python` when only `python3` exists,
or re-sending a gh field list that the installed gh doesn't support).
```

**规则表**(照抄,因为它本身就是可迁移的设计准则):

`tools/terminal_hints.py:11`

```python
Design rules (keep these when adding patterns):

* Only fires on non-zero exit codes — never annotate success.
* At most ONE hint per result, first match wins; patterns are ordered by
  observed frequency in production trajectories (state.db mining, Aug 2026).
* Scans only the first ``_SCAN_CHARS`` of output — hints must key on error
  headers, not deep context.
* Hints state the *next action*, not a diagnosis essay. One or two sentences.
* Pure function, no I/O, no config reads — trivially unit-testable.
```

**最有说服力的地方是它的数据来源**:每条模式旁边都注着生产频次。

`tools/terminal_hints.py:21`

```python
Frequencies quoted below come from a 250k-terminal-result window of the
production session DB (Aug 2026): together these classes cover ~14k failed
calls whose retry chains averaged 1.4 extra tool turns each.
"""
```

`tools/terminal_hints.py:48`

```python
def _hint_command_not_found(command: str, output: str) -> Optional[str]:
    # ~1,010x generic; 837x of them are bare `python` on python3-only distros.
    m = re.search(r"(?:bash: line \d+: |bash: |sh: \d*:? ?)?([\w.+-]+): command not found", output)
    if not m:
        return None
    missing = m.group(1)
    if missing == "python":
        return (
            "This system has no bare `python` — use `python3`, or the "
            "project venv's interpreter (e.g. .venv/bin/python)."
        )
```

排序按频次,退出码提示排在输出模式之后:

`tools/terminal_hints.py:128`

```python
# Ordered by production frequency — first match wins.
_OUTPUT_HINTS: list[Callable[[str, str], Optional[str]]] = [
    _hint_gh_unknown_json_field,
    _hint_merge_conflict,
    _hint_command_not_found,
    _hint_module_not_found,
    _hint_already_exists,
    _hint_gh_rate_limit,
    _hint_permission_denied,
]

# Exit-code-only hints for codes the semantics table in terminal_tool does
# not cover per-command. Checked after output patterns.
_EXIT_CODE_HINTS: dict[int, str] = {
    126: "Exit 126: the file was found but is not executable — `chmod +x` it or invoke it via its interpreter (e.g. `bash script.sh`).",
    137: "Exit 137: the process was SIGKILLed — usually out-of-memory or an external kill. Reduce memory use or check `dmesg | tail` before retrying.",
    124: "Exit 124: the command hit its timeout. Raise timeout= (foreground max 600s) or run it with background=true and notify_on_complete=true.",
}
```

单个模式抛异常不会拖垮整体(逐条 try):

`tools/terminal_hints.py:159`

```python
    if exit_code == 0:
        return None
    window = (output or "")[:_SCAN_CHARS]
    if window:
        for fn in _OUTPUT_HINTS:
            try:
                hint = fn(command or "", window)
            except Exception:
                continue
            if hint:
                return hint
    return _EXIT_CODE_HINTS.get(exit_code)
```

**可迁移原则**:harness 最值钱的一类改进,是把「模型常犯的重复错误」离线挖出来,
做成**一句话的下一步动作**塞回工具结果。这里的经济账很清楚:~14k 次失败 × 平均 1.4 个
多余工具轮次 —— 一条提示省掉的是真金白银的 token 和延迟。

### 3.7 `tools/focus_pane_tool.py` — 焦点面板

70 行,是本簇最小的完整工具。桌面 App 里有五个面板,agent 可以主动切:

`tools/focus_pane_tool.py:16`

```python
PANES = ("chat", "files", "terminal", "review", "sessions")
```

`tools/focus_pane_tool.py:19`

```python
def focus_pane_tool(pane: str) -> str:
    """Ask the desktop GUI to reveal and focus ``pane``."""
    name = (pane or "").strip().lower()
    if name not in PANES:
        return tool_error(f"pane must be one of: {', '.join(PANES)}.")

    try:
        ok = desktop_ui.emit("pane.reveal", {"pane": name})
    except Exception as exc:
        return tool_error(f"Failed to focus the {name} pane: {exc}")
    if not ok:
        return tool_error("Pane focus is only available in the Hermes desktop app.")

    return json.dumps({"success": True, "pane": name}, ensure_ascii=False)
```

最有意思的是**渲染端的克制**:

`tools/focus_pane_tool.py:1`

```python
#!/usr/bin/env python3
"""Reveal/focus a pane in the Hermes desktop GUI.

Gated on ``HERMES_DESKTOP`` (like the other GUI affordances). Emits
``pane.reveal`` through the shared ``desktop_ui`` bridge; the renderer runs each
pane's own reveal path and only acts on the active window (a background turn
never moves the user's focus). To show a URL/file, use ``open_preview``.
"""
```

**「后台回合永远不会抢用户的焦点」**这一条是在渲染端而不是工具端实现的 —— 工具只负责
发意图,是否兑现由前端根据窗口是否激活决定。这是 agent 控制 GUI 时的正确分层:
**工具表达意图,前端保留否决权。**

### 3.8 `agent/battery.py` — agent 为什么关心电量

**它不为 agent 决策服务,只是状态栏的一个元素。**

`agent/battery.py:1`

```python
"""System-battery read-out for the CLI/TUI status bar.

Reads the host battery through ``psutil`` (already a Hermes dependency) and
exposes a compact, colour-coded label.  Everything degrades to "unavailable"
when there is no battery (desktops, servers, VMs) or when the read fails, so
callers can render the result unconditionally and simply show nothing.

The status bar repaints often (every keystroke and on a ~1s idle refresh), so
:func:`read_battery` memoises the last reading for a few seconds instead of
hitting ``psutil`` on every frame.
"""
```

设计上值得注意的三点:

**(1) "不可用"是一等状态,不是异常。** 没电池的服务器、psutil 缺 `sensors_battery`、
读数抛异常 —— 全部收敛到同一个 `UNAVAILABLE` 单例,调用方无脑渲染即可。

`agent/battery.py:38`

```python
UNAVAILABLE = BatteryStatus(available=False)
```

**(2) 缓存是为渲染频率服务的**,不是为性能洁癖:

`agent/battery.py:48`

```python
_CACHE_TTL_SECONDS = 8.0
_cache: Optional[tuple[float, BatteryStatus]] = None
```

`cli.py:5289`

```python
        # Battery read-out (first status-bar element when enabled). Reads are
        # memoised for a few seconds inside agent.battery, so polling it on
        # every status-bar repaint is cheap.
        if getattr(self, "_battery_visible", False):
            try:
                from agent.battery import (
                    battery_category,
                    format_battery,
                    read_battery,
                )
```

**(3) 分档反直觉但正确**:插着电时永远是 "good",不看百分比。

`agent/battery.py:105`

```python
def battery_category(status: BatteryStatus) -> str:
    """Bucket a reading into a colour category: good/warn/bad/critical/dim."""
    if not status.available or status.percent is None:
        return CATEGORY_DIM
    # On AC power the level isn't a concern — always read as healthy.
    if status.charging:
        return CATEGORY_GOOD
    pct = status.percent
    if pct <= 10:
        return CATEGORY_CRITICAL
    if pct <= 20:
        return CATEGORY_BAD
    if pct <= 50:
        return CATEGORY_WARN
    return CATEGORY_GOOD
```

默认关闭(`display.battery: false`),`/battery` 命令切换并持久化(`cli.py:5100–5110`)。
另一个消费方是 TUI(`tui_gateway/methods_tools.py:23`)。

### 3.9 `agent/onboarding.py` — 首次运行引导

**核心设计:没有首次运行问卷。** 提示挂在"用户第一次撞到某个行为分叉"的那一刻:

`agent/onboarding.py:1`

```python
"""
Contextual first-touch onboarding hints.

Instead of blocking first-run questionnaires, show a one-time hint the *first*
time a user hits a behavior fork — message-while-running, first long-running
tool, etc.  Each hint is shown once per install (tracked in ``config.yaml`` under
``onboarding.seen.<flag>``) and then never again.

Keep this module tiny and dependency-free so both the CLI and gateway can import
it without pulling in heavy modules.
"""
```

四个闩:

`agent/onboarding.py:26`

```python
BUSY_INPUT_FLAG = "busy_input_prompt"
TOOL_PROGRESS_FLAG = "tool_progress_prompt"
OPENCLAW_RESIDUE_FLAG = "openclaw_residue_cleanup"
PROFILE_BUILD_FLAG = "profile_build_offered"
```

**与配置初始化的关系**:这个模块**不参与**配置初始化(那是 setup wizard 的事),
它只往已有的 `config.yaml` 里写 `onboarding.seen.<flag> = True`,而且失败即放弃:

`agent/onboarding.py:216`

```python
def mark_seen(config_path: Path, flag: str) -> bool:
    """Persist ``onboarding.seen.<flag> = True`` to ``config_path``.

    Uses the atomic YAML writer so a concurrent process can't observe a
    partially-written file.  Returns True on success, False on any error
    (including the config file being absent — onboarding is best-effort).
    """
    try:
        import yaml
        from hermes_cli.config import atomic_config_write
    except Exception as e:  # pragma: no cover — dependency issue
        logger.debug("onboarding: failed to import yaml/utils: %s", e)
        return False
```

同一条提示分 gateway / CLI 两个措辞版本(markdown vs 纯文本),而且**按当前生效的模式
说实话** —— 不是一句通用文案:

`agent/onboarding.py:36`

```python
def busy_input_hint_gateway(mode: str) -> str:
    """Hint shown the first time a user messages while the agent is busy.

    ``mode`` is the effective busy_input_mode that was just applied, so the
    message matches reality ("I just interrupted…" vs "I just queued…").
    """
```

最重的一块是**首条消息的建档引导**。默认是 `ask`(提议),可关成 `off`:

`agent/onboarding.py:147`

```python
def profile_build_mode(config: Mapping[str, Any]) -> str:
    """Resolve the onboarding profile-build mode from config.

    Returns one of:
      ``"ask"``  — on first contact, OFFER to build a profile (default).
      ``"off"``  — never offer; the first-message note stays a plain intro.

    Read from ``config.onboarding.profile_build``. Unknown / missing values
    fall back to ``"ask"`` so the default experience offers the flow. Any
    network/account lookups inside the flow are separately consented to in
    conversation — this setting only governs whether the offer is made.
    """
```

引导本身是一段追加到首条消息后面的 system note,**逐级要授权**:

`agent/onboarding.py:179`

```python
    return (
        "\n\n[System note: This is the user's very first message ever. "
        "After a one-sentence introduction (mention /help shows commands), "
        "OFFER — do not assume — to build a short profile of them so you can "
        "be more useful, and explain they can decline or do it later. If and "
        "ONLY IF they accept:\n"
        "  1. Ask for whatever they're comfortable sharing (name, what they "
        "do, how they like you to work). Volunteered facts come first.\n"
        "  2. Before ANY external lookup, say what you intend to look up and "
        "get explicit consent for that step. Never read their connected "
        "accounts (email, calendar, etc.) silently — ask each time.\n"
        "  3. With consent, you may use web_search to confirm public details "
        "(e.g. employer, public profiles) from the data points they gave.\n"
        "  4. Save each confirmed, durable fact with the memory tool using "
        "target=\"user\" — keep entries compact and high-signal.\n"
        "If they decline at any point, stop immediately and continue normally. "
        "Keep the whole exchange light and conversational, not an interrogation.]"
    )
```

**可迁移原则**:引导逻辑写在**提示词**里而不是状态机里,于是「用户中途反悔」这种
分支不需要代码支持 —— 模型自己处理。代价是不可强制执行,只能靠模型遵守。

还有一条迁移提示,专管从 OpenClaw 迁过来的用户:

`agent/onboarding.py:131`

```python
def detect_openclaw_residue(home: Optional[Path] = None) -> bool:
    """Return True if an OpenClaw workspace directory is present in ``$HOME``.

    Pure filesystem check — no side effects. ``home`` override exists for tests.
    """
    base = home or Path.home()
    try:
        return (base / ".openclaw").is_dir()
    except OSError:
        return False
```

---

## 4. 配置项与环境变量

### 4.1 配置项(默认值取自 `hermes_cli/config_defaults.py`)

`hermes_cli/config_defaults.py:860`

```python
        "vision": {
            "provider": "auto",    # auto | openrouter | nous | codex | custom
            "model": "",           # e.g. "google/gemini-2.5-flash", "gpt-4o"
            "base_url": "",        # direct OpenAI-compatible endpoint (takes precedence over provider)
            "api_key": "",         # API key for base_url (falls back to OPENAI_API_KEY)
            "timeout": 120,        # seconds — LLM API call timeout; vision payloads need generous timeout
            "extra_body": {},      # OpenAI-compatible provider-specific request fields
            "reasoning_effort": "",  # per-task thinking level: none|minimal|low|medium|high|xhigh|max|ultra (empty = provider default)
            "download_timeout": 30,  # seconds — image HTTP download timeout; increase for slow connections
        },
```

本簇相关配置键一览(默认值来自 R8A 台账 `data/r8a-config-keys.tsv` 与上面的 AST 抽取):

| 键 | 默认 | 谁读 |
|---|---|---|
| `auxiliary.vision.download_timeout` | `30` | `tools/vision_tools.py:87`:`val = cfg_get(cfg, "auxiliary", "vision", "download_timeout")` |
| `auxiliary.vision.timeout` | `120` | `tools/vision_tools.py:1257`:`_vision_cfg = cfg_get(_cfg, "auxiliary", "vision", default={})` |
| `auxiliary.vision.model` | `""` | `tools/vision_tools.py:1528`:`_vmodel = cfg_get(_cfg, "auxiliary", "vision", "model")` |
| `auxiliary.vision.max_concurrency` | **无默认条目** | `tools/vision_tools.py:171`:`val = cfg_get(cfg, "auxiliary", "vision", "max_concurrency")` |
| `auxiliary.vision.temperature` | **无默认条目** | `tools/vision_tools.py:1261`:`_vtemp = _vision_cfg.get("temperature")` |
| `auxiliary.video.model` | 无(回落 vision) | `tools/vision_tools.py:1907`:`_vmodel = cfg_get(_cfg, "auxiliary", "video", "model") or cfg_get(_cfg, "auxiliary", "vision", "model")` |
| `display.language` | `"en"` | `agent/i18n.py:202`:`lang = (cfg.get("display") or {}).get("language")` |
| `display.battery` | `False` | `hermes_cli/config_defaults.py:1163`:`"battery": False,` |
| `display.tool_preview_length` | `0`(无限) | `agent/display.py:113`:`_tool_preview_max_len: int = 0  # 0 = unlimited` |
| `display.friendly_tool_labels` | `True` | `agent/display.py:650`:`_friendly_tool_labels: bool = True` |
| `display.skin` | `"default"` | `agent/display.py:131`:`def _get_skin():` |
| `display.final_response_markdown` | `"strip"` | `cli.py:4308`:`self.final_response_markdown = str(` |
| `display.message_reactions` | **无默认条目**(读取处 `False`) | `tools/react_to_message_tool.py:107`:`return isinstance(display, dict) and bool(display.get("message_reactions", False))` |
| `onboarding.seen` | `{}` | `agent/onboarding.py:207`:`seen = onboarding.get("seen")` |
| `onboarding.profile_build` | `"ask"` | `agent/onboarding.py:164`:`mode = onboarding.get("profile_build")` |
| `security.allow_lazy_installs` | `True` | `hermes_cli/config_defaults.py:2158`:`"allow_lazy_installs": True,` |

### 4.2 环境变量

| 变量 | 作用 | 读取处 |
|---|---|---|
| `HERMES_VISION_DOWNLOAD_TIMEOUT` | 图片下载超时(优先于 config) | `tools/vision_tools.py:78`:`env_val = os.getenv("HERMES_VISION_DOWNLOAD_TIMEOUT", "").strip()` |
| `HERMES_VISION_MAX_CONCURRENCY` | 编码/缩放执行器 worker 数 | `tools/vision_tools.py:160`:`env_val = os.getenv("HERMES_VISION_MAX_CONCURRENCY", "").strip()` |
| `VISION_TOOLS_DEBUG` | 视觉调用落盘调试日志 | `tools/vision_tools.py:72`:`_debug = DebugSession("vision_tools", env_var="VISION_TOOLS_DEBUG")` |
| `AUXILIARY_VISION_MODEL` | 旧式视觉模型覆盖 | `tools/vision_tools.py:1534`:`model = os.getenv("AUXILIARY_VISION_MODEL", "").strip() or None` |
| `AUXILIARY_VIDEO_MODEL` | 旧式视频模型覆盖 | `tools/vision_tools.py:1913`:`model = os.getenv("AUXILIARY_VIDEO_MODEL", "").strip() or os.getenv("AUXILIARY_VISION_MODEL", "").strip() or None` |
| `HERMES_LANGUAGE` | UI 语言(优先于 config) | `agent/i18n.py:223`:`env_lang = os.environ.get("HERMES_LANGUAGE")` |
| `HERMES_BUNDLED_LOCALES` | 打包后的 locale 目录 | `agent/i18n.py:105`:`override = os.getenv("HERMES_BUNDLED_LOCALES", "").strip()` |
| `HERMES_SPINNER_PAUSE` | 暂停 spinner 动画 | `agent/display.py:1209`:`if os.getenv("HERMES_SPINNER_PAUSE"):` |
| `HERMES_DESKTOP` | 桌面 GUI 工具的总闸 | `tools/focus_pane_tool.py:37`:`return env_var_enabled("HERMES_DESKTOP")` |
| `TERMINAL_ENV` | 决定宿主路径能不能直读 | `tools/image_source.py:218`:`return os.getenv("TERMINAL_ENV", "local").strip().lower() in ("local", "")` |

---

## 5. 测试作为行为规格

### 5.1 环境与读数

```console
venv:        /home/user/hermes-venv
dist-info:   89 个(基线 CLAUDE.md 记录为 87 —— 本轮涨了 2,原因见 §7 移交-1)
容器:        root 运行、无 IPv6、无 models.dev 目录(离线)、SQLite 3.45.1
```

### 5.2 本簇测试结果

第一批(agent 侧 11 个文件)全绿:

```console
=== Summary: 11 files, 161 tests passed, 0 failed (100% complete) in 3.8s (8 workers) ===
```

第二批(tools 侧 7 个文件)全绿:

```console
=== Summary: 7 files, 84 tests passed, 0 failed (100% complete) in 7.4s (8 workers) ===
```

`tests/agent/test_vision_routing_31179.py` 8 个用例中 **2 个失败**,两条**都是环境原因,
不是代码缺陷**,逐条诊断如下:

**(a) `TestTextOnlyMainSkippedForVision::test_text_only_main_skipped_when_no_aggregator`
—— 离线导致 models.dev 目录为空。**
该用例要求「主模型是 DeepSeek(纯文本)且无聚合器凭据时,视觉自动链路必须返回 `None`」。
但能力判定查不到条目时**故意宽松**,而同文件的**相邻用例把这条宽松写成了规格**:

`tests/agent/test_vision_routing_31179.py:206`

```python
    def test_unknown_capability_does_not_block(self, isolated_home, monkeypatch):
        """When models.dev has no entry, fall back to permissive (attempt the call).

        This keeps new/custom providers working — only providers we have
        cataloged as text-only are skipped.
        """
```

本容器离线、目录为空,于是**每个** provider 都落进"未知 → 宽松"分支,DeepSeek 不被跳过。
直接探测复现:

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from agent.auxiliary_client import _main_model_supports_vision
print(_main_model_supports_vision('deepseek','deepseek-v4-pro'))"
# → True   (联网环境下 models.dev 目录里 deepseek 标注为不支持视觉,应为 False)
```

**(b) `TestTextOnlyMainSkippedForVision::test_vision_capable_main_used`
—— venv 里缺 `anthropic` SDK。**
该用例要求「主模型是 Anthropic 时自动链路返回一个客户端」。失败时日志是
`resolve_provider_client: anthropic requested but no Anthropic credentials found`
—— **这条日志是误导的**,真实原因是 SDK 缺失(凭据其实解析得到)。链路:

`agent/anthropic_adapter.py:49`

```python
def _get_anthropic_sdk():
    """Return the ``anthropic`` SDK module, importing lazily. None if not installed."""
    global _anthropic_sdk
    if _anthropic_sdk is ...:
        try:
            from tools.lazy_deps import ensure as _lazy_ensure
            _lazy_ensure("provider.anthropic", prompt=False)
        except ImportError:
            pass
```

补上 SDK 后该用例转绿(实测:同一命令重跑,8 个用例变成 7 过 1 挂,只剩 (a))。

### 5.3 值得当规格读的用例

| 用例 | 钉住的规格 |
|---|---|
| `tests/agent/test_i18n.py:41`:`def test_catalog_keys_match_english(lang: str):` | 每个非英文 catalog 的键集必须与 en **完全相等**(不多不少) |
| `tests/agent/test_i18n.py:52`:`def test_catalog_placeholders_match_english(lang: str):` | 每条译文的 `{placeholder}` 集合必须与英文一致 |
| `tests/tools/test_vision_tools.py:765`:`def test_worker_count_tracks_host_cpus_with_env_override(self):` | 64 核 → 64 worker;env 显式值**可以超过**核数;`0` 被忽略回落核数 |
| `tests/tools/test_vision_native_fast_path.py:107`:`def test_oversized_image_resized_under_embed_cap(self, tmp_path):` | 超标图在**写进历史前**被缩到 embed cap 以下 |
| `tests/tools/test_vision_native_fast_path.py:222`:`def test_text_mode_wins_over_supports_vision_override(self, tmp_path):` | 路由判定为 `text` 时,`supports_vision` 覆盖也不能强开原生路径 |
| `tests/agent/test_markdown_tables.py:103`:`def test_vertical_fallback_wraps_long_cell_text_with_indent():` | 宽度不够时转纵向,续行缩进两格 |

i18n 那两条是本簇最重要的护栏:catalog 缺键会**静默**回落英文,靠人 review 抓不住,
所以钉在测试层 —— 与本项目 CLAUDE.md 里「机器该抓的那一类」是同一个道理。

---

## 6. 定案

### ▲ 文档与代码矛盾

**▲-1 `display.language` 的支持值列表漏了 `ar`(阿拉伯语),且该段落把「未列出 = 未知 = 回落英文」
写成了因果。**

代码支持 17 种,含 `ar`:

`agent/i18n.py:43`

```python
SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "en", "zh", "zh-hant", "ja", "de", "es", "fr", "tr", "uk",
    "af", "ko", "it", "ga", "pt", "ru", "hu", "ar",
)
```

`locales/ar.yaml` 存在且与 en 键数相同(351),且被 `tests/agent/test_i18n.py` 的
参数化用例覆盖(参数直接来自 `SUPPORTED_LANGUAGES`)。

文档(标题「### UI language for static messages」管辖的整段)只列 16 种:

`website/docs/user-guide/configuration.md:1727`

> Supported values: `en` (default), `zh` (Simplified Chinese), `zh-hant` (Traditional Chinese), `ja` (Japanese), `de` (German), `es` (Spanish), `fr` (French), `tr` (Turkish), `uk` (Ukrainian), `af` (Afrikaans), `ko` (Korean), `it` (Italian), `ga` (Irish), `pt` (Portuguese), `ru` (Russian), `hu` (Hungarian). Unknown values fall back to English.

**为什么判 ▲ 而不是 ◎**:按 CLAUDE.md「必须把整句/整段一并判定」——
这一段的最后一句 "Unknown values fall back to English." 紧接在枚举之后,
把「不在这张表里」定义为「unknown」。读者据此会得出「设 `ar` 会回落英文」,
而实际会加载 `locales/ar.yaml`。**整段合起来是假的**,不只是保守。
同一处的中文站点译文有同样的缺漏(`website/i18n/zh-Hans/.../configuration.md:1255`),
YAML 注释行(`website/docs/user-guide/configuration.md:1662`)也是同一张 16 项列表。

**▲-2 `vision_analyze` 的模块 docstring 与实现不符:说"用 OpenRouter 上的 Gemini 3 Flash
Preview 处理",实际既不固定 provider 也不固定模型,且默认根本不调辅助模型。**

`tools/vision_tools.py:1096`

```python
    This tool accepts either an HTTP/HTTPS URL or a local file path. For URLs,
    it downloads the image first. In both cases, the image is converted to base64
    and processed using Gemini 3 Flash Preview via OpenRouter API.
```

实现上:(1) 主模型能看图时**根本不调辅助模型**(§1.2 的原生快路径);
(2) 调辅助模型时 provider 由 `auxiliary.vision.provider`(默认 `auto`)决定,
模型由 `auxiliary.vision.model`(默认空)决定,两者都没有把 Gemini/OpenRouter 写死。
同文件顶部的模块 docstring 反而是对的("OpenRouter, Nous, Codex, native Anthropic,
or a custom OpenAI-compatible endpoint",`tools/vision_tools.py:6`),
即**同一个文件里两处自述互相矛盾**。这一条属于代码内注释而非用户文档,
但按「作者自绘地图」的口径同样计入。

### ◇ 代码有、文档无

**◇-1 终端颜色能力完全不探测:全簇没有 `NO_COLOR`、`TERM=dumb`、8/256 色降级。**

diff 与失败前缀一律输出 24-bit truecolor 或固定 SGR:

`agent/display.py:23`

```python
# ANSI escape codes for coloring tool failure indicators
_RED = "\033[31m"
_RESET = "\033[0m"
```

`agent/display.py:52`

```python
    dim = "\033[38;2;150;150;150m"
    file_c = "\033[38;2;180;160;255m"
    hunk = "\033[38;2;120;120;140m"
    minus = "\033[38;2;255;255;255;48;2;120;20;20m"
    plus = "\033[38;2;255;255;255;48;2;20;90;20m"
```

唯一的"能力探测"是 `isatty()` 和 prompt_toolkit `StdoutProxy` 判定(§2.3),
两者都判**通道形态**不判**颜色能力**。搜索面:

```verify
cd /home/user/hermes-agent && grep -rn "NO_COLOR\|TERM.*dumb\|colorama\|force_terminal" \
  agent/display.py agent/markdown_tables.py cli.py
# agent/display.py / agent/markdown_tables.py:零命中(这就是本条 ◇ 的范围)
# cli.py 3 处,均与 display.py 自己拼的 ANSI 无关:
#   cli.py:3888 / cli.py:7385  force_terminal=True —— rich Console 的构造参数
#   cli.py:14700               一条注释,讲的是退出时清屏(_clear_terminal_on_exit)
```

**◇-2 三个配置键有读取点但 `DEFAULT_CONFIG` 里没有条目**,因此
`hermes config` 之类的枚举看不到它们,只能从代码或本底稿知道:
`auxiliary.vision.max_concurrency`、`auxiliary.vision.temperature`、`display.message_reactions`。
搜索面:对 `hermes_cli/config_defaults.py` grep 这三个名字,零命中;
读取点见 §4.1 表。

**◇-3 图片没有任何 token 成本建模。** 全模块控的是字节与像素,`max_tokens` 只约束**输出**。
搜索面:`grep -n "token" tools/vision_tools.py` 仅 `max_tokens=2000`(图)与
`max_tokens=4000`(视频)两处。

**◇-4 `agent/display.py` 以一个空的段落横幅结尾。**

`agent/display.py:1545`

```python
# =========================================================================
# Honcho session line (one-liner with clickable OSC 8 hyperlink)
# =========================================================================
```

文件到此为止(共 1547 行),横幅之下没有任何代码。全仓 `.py` 里再没有别处出现
"OSC 8"/`\033]8` 的超链接实现:

```verify
cd /home/user/hermes-agent && grep -rn "OSC 8\|osc8\|\\\\033\]8" --include=*.py . | grep -v "^./tests/"
# → 仅 ./agent/display.py:1546 这一行注释本身
```

即这是一段**被删干净了但横幅留下**的残留(归为 ◇ 而非 ■:它不产生错误行为,
只是让读者以为下面还有内容)。

### ■ 代码缺陷

**■-1 `_download_video` 没有错误分类,4xx 也会退避重试三次。**

图片下载有 `_is_retryable_download_error`(§1.6),视频下载没有:

`tools/vision_tools.py:1638`

```python
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                logger.warning("Video download failed (attempt %s/%s): %s", attempt + 1, max_retries, str(e)[:50])
                await asyncio.sleep(wait_time)
```

后果:一个 404 的视频 URL 会白等 2+4=6 秒才失败,策略拦截(`PermissionError`)与
体积超限(`ValueError`)同样要走满三轮 —— 而图片路径上这三类都是"立即失败"。
影响面小(video 是可选 toolset),但它是同一文件里两套标准。

**■-2 视频 base64 编码跑在事件循环线程上,没走 CPU 执行器。**

`tools/vision_tools.py:1728`

```python
        video_data_url = _video_to_base64_data_url(temp_video_path, mime_type=detected_mime)
```

对比图片路径的同一步:

`tools/vision_tools.py:1202`

```python
        image_data_url = await _run_encode_on_cpu_executor(
            _image_to_base64_data_url, temp_image_path, mime_type=detected_mime_type)
```

`_video_to_base64_data_url` 会同步 `read_bytes()` 一个最大 50 MB 的文件再 base64
(`tools/vision_tools.py:1574–1579`),整段阻塞调用线程。这正是 §1.7 那次生产事故
(编码把核吃满、事件循环失去 CPU)的同一形状,只是发生在视频侧且**没有被修**。
**未验证**:没有实测过它是否真的能把 dashboard 探活拖挂 —— 单次 50 MB base64 的
量级比"几十帧图片并发"小得多,所以严重度推定低于原事故。

**■-3 `_try_anthropic` 在 SDK 缺失时报"没有凭据",诊断误导。**
见 §5.2(b):真实条件是 `anthropic` 包不可导入,日志却说
`no Anthropic credentials found`。属于本簇**外**的文件(`agent/auxiliary_client.py:6213`),
在此登记是因为它是本轮两个测试失败之一的直接诊断障碍,不计入本簇缺陷计数。

### ◎ 文档成立但显著保守

**◎-1 `agent/i18n.py` 的 docstring 自称 "thin slice, by design",实际覆盖 351 条键 × 17 语言。**

`agent/i18n.py:3`

```python
Scope (thin slice, by design): only the highest-impact static strings shown
to the user by Hermes itself -- approval prompts, a handful of gateway slash
command replies, restart-drain notices.  Agent-generated output, log lines,
error tracebacks, tool outputs, and slash-command descriptions all stay in
English.
```

「a handful of gateway slash command replies」字面为真(确实只覆盖静态串,
不覆盖 agent 输出),但 351 条键、5,967 条译文,比"a handful"给人的量级大得多。
按 CLAUDE.md 口径:字面为真,故记 ◎ 不记 ▲。

**定案计数:▲ 2 条、◇ 4 条、■ 2 条(另有 1 条簇外登记不计数)、◎ 1 条。**

---

## 7. 移交项

**移交-1:本轮把共享 venv 从 87 个包变成了 89 个 —— `anthropic 0.87.0` 与
`docstring_parser 0.18.0` 是被一次只读探测**触发安装**的。**

锚点:`agent/anthropic_adapter.py:54`:`from tools.lazy_deps import ensure as _lazy_ensure`

现象:我为诊断 `test_vision_capable_main_used` 失败,在 venv 里直接调了
`build_anthropic_client('sk-ant-test')`;它经 `_get_anthropic_sdk()` →
`tools.lazy_deps.ensure("provider.anthropic", prompt=False)` 联网 pip 装了
`anthropic`(+ 依赖 `docstring_parser`)。时间戳可查:

```verify
ls -ld --time-style=full-iso /home/user/hermes-venv/lib/python3.11/site-packages/anthropic-0.87.0.dist-info
# → 2026-08-09 04:51:12 +0000,与该次探测同一分钟
ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l   # → 89
```

这条闸门默认开着(`hermes_cli/config_defaults.py:2158`:`"allow_lazy_installs": True,`),
所以**任何**触碰 Anthropic 适配器的只读探测都会装包。后续轮次报测试数时必须按 89 记,
或先决定是否卸回 87 —— 我没有自行卸载,因为可能有并发子代理正在用这个 venv。
**同时这本身是一条值得写进成品章的观察:一个"读代码"的动作可以产生网络副作用。**

**移交-2:视频路径与图片路径的两处标准不一致,建议合并考察。**

锚点:`tools/vision_tools.py:1728`:`video_data_url = _video_to_base64_data_url(temp_video_path, mime_type=detected_mime)`

现象:视频编码没走 `_run_encode_on_cpu_executor`(■-2),视频下载没走
`_is_retryable_download_error`(■-1)。两条都是"图片侧修过、视频侧没跟上"的形状,
建议下一轮在讲"多模态输入"时一并核实是否还有第三处(如 `tools/audio_*`)。

**移交-3:`display.live_status` 的默认值不在 `DEFAULT_CONFIG` 里,而在 gateway 自己的表里。**

锚点:`gateway/display_config.py:70`:`"live_status": "full",`

现象:`agent/display.py:687` 的 `build_status_phrase` 是给这个键服务的(Slack 状态行),
但它的默认值和解析逻辑住在 `gateway/display_config.py`,与 `hermes_cli/config_defaults.py`
是两套。本轮没有精读 `gateway/display_config.py`(不在本簇 12 文件内),
**未验证**是否还有其它 `display.*` 键走同样的双轨,建议 gateway 那一簇的轮次核。

**移交-4:`tests/agent/test_vision_routing_31179.py::test_text_only_main_skipped_when_no_aggregator`
在离线容器里必然失败,建议加入 CLAUDE.md 的"已知环境限制"表。**

锚点:`tests/agent/test_vision_routing_31179.py:206`:`def test_unknown_capability_does_not_block(self, isolated_home, monkeypatch):`

现象:同文件相邻用例把"models.dev 无条目 → 宽松放行"写成规格;本容器 models.dev 目录为空
(已知限制,与 `test_xai_provider_labels.py` 同源),于是 DeepSeek 也被宽松放行,
"必须跳过纯文本主模型"的断言必然不成立。属容器限制,非代码缺陷。
