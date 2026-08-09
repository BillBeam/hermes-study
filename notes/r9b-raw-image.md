# R9B 底稿 · 图像生成与路由

> 底稿定位:求全求证,面向"要凭它重实现同等机制"的自己。允许啰嗦、允许罗列。
> 溯源约定:凡对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` 单独成行、置于代码块之前。
> 基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(只读)。

---

## 0. 本簇范围与文件清单(行数)

| 文件 | 行数 | 一句话职责 |
|---|---|---|
| `tools/image_generation_tool.py` | 1668 | `image_generate` 工具本体 + **内置 FAL 实现**(模型目录、payload 构造、提交、升采样、三级分派、动态 schema) |
| `agent/image_routing.py` | 821 | **与图像生成无关**:决定"用户这一轮附带的图片"以 native(原图给主模型)还是 text(先 `vision_analyze` 转文字)进入对话 |
| `agent/image_gen_provider.py` | 393 | 图像生成后端的**抽象基类 + 公共工具函数**(响应形状、落盘、宽高比归一) |
| `tools/image_source.py` | 391 | **与图像生成无关**:`vision_analyze` / 视频工具的**输入媒体统一解析器**(data:/http/file/沙箱),含 SSRF 与沙箱confinement |
| `agent/image_gen_registry.py` | 145 | provider 注册表 + "谁是当前活跃 provider"的解析 |
| `tools/fal_common.py` | 163 | FAL SDK 公共层:惰性 import、托管队列网关客户端、HTTP 状态提取 |

**这一簇的第一个反直觉事实:名字里带 image 的六个文件其实分属三条互不相干的链路。**

- 链路 A(出图):`image_generation_tool.py` → `image_gen_registry.py` → `image_gen_provider.py` → `fal_common.py` → `plugins/image_gen/*`
- 链路 B(入图,给主模型看):`image_routing.py`,调用方是 `cli.py` / `gateway/run.py` / `tui_gateway/server.py`
- 链路 C(入图,给 vision 工具读字节):`image_source.py`,调用方是 `tools/vision_tools.py` / `tools/flux3_video_tool.py`

链路 A 与链路 C **没有任何调用关系**——出图工具从不通过 `image_source.py` 解析用户给的源图。这一点是后面 ■-1 的根。
搜索面见 §5 ■-1 的 ```verify``` 块。

---

## 1. 一次图像生成请求的完整走法

### 1.1 前置:用户这一轮如果**带了图**(链路 B)

`agent/image_routing.py:5`

```
  native  — attach images as OpenAI-style ``image_url`` content parts on the
            user turn. Provider adapters (Anthropic, Gemini, Bedrock, Codex,
            OpenAI chat.completions) already translate these into their
            vendor-specific multimodal formats.

  text    — run ``vision_analyze`` on each image up-front and prepend the
            description to the user's text. The model never sees the pixels;
            it only sees a lossy text summary. This is the pre-existing
            behaviour and still the right choice for non-vision models.
```

决策入口 `decide_image_input_mode(provider, model, cfg, *, requested_provider="")`,每轮消息调用一次。

`agent/image_routing.py:476`

```python
    mode_cfg = "auto"
    if isinstance(cfg, dict):
        agent_cfg = cfg.get("agent") or {}
        if isinstance(agent_cfg, dict):
            mode_cfg = _coerce_mode(agent_cfg.get("image_input_mode"))

    if mode_cfg == "native":
        return "native"
    if mode_cfg == "text":
        return "text"
```

`agent/image_routing.py:502`

```python
    if supports is True:
        return "native"
    if _explicit_aux_vision_override(cfg):
        return "text"
    return "text"
```

注意这里的收尾:`auto` 分支下**两条 return 都是 `"text"`**。`_explicit_aux_vision_override(cfg)` 的返回值在这里对结果**没有影响**——它保留下来纯粹是文档意图(把"有显式 aux vision 后端"这条路径写出来)。这不是缺陷(结果正确),但重实现时要知道:**这个 if 是纯注释性的**。

- native 模式下真正干活的是 `build_native_content_parts(user_text, image_paths, image_urls)`,返回 OpenAI 风格 content 数组。
- 调用方:`gateway/run.py:21446`(`Runner._decide_image_input_mode`)、`cli.py:13768`、`tui_gateway/server.py:9499`。
- 另有 `agent/auxiliary_client.py:6551`、`tools/vision_tools.py:869`、`tools/computer_use/vision_routing.py:116` 复用 `_lookup_supports_vision`。

### 1.2 主链路:模型调用 `image_generate`

工具注册(模块尾部,import 时执行):

`tools/image_generation_tool.py:1658`

```python
registry.register(
    name="image_generate",
    toolset="image_gen",
    schema=IMAGE_GENERATE_SCHEMA,
    handler=_handle_image_generate,
    check_fn=check_image_generation_requirements,
    requires_env=[],
    is_async=False,   # sync fal_client API to avoid "Event loop is closed" in gateway
    emoji="🎨",
    dynamic_schema_overrides=_build_dynamic_image_schema,
)
```

`_handle_image_generate` 是**三级分派**,顺序固定:

`tools/image_generation_tool.py:1501`

```python
def _handle_image_generate(args, **kw):
    prompt = args.get("prompt", "")
    if not prompt:
        return tool_error("prompt is required for image generation")
    aspect_ratio = args.get("aspect_ratio", DEFAULT_ASPECT_RATIO)
    image_url = args.get("image_url")
    reference_image_urls = args.get("reference_image_urls")
    task_id = kw.get("task_id")
```

1. **插件 provider 分派** `_dispatch_to_plugin_provider(...)` —— 仅当 `image_gen.provider` 显式设置**且不等于 `"fal"`** 时接管;
2. **托管 Krea 特判** `_maybe_route_managed_krea(...)` —— 仅当 `image_gen.model` 是原生 `krea-2-*` id 且托管网关可解析时接管;
3. **内置 FAL 兜底** `image_generate_tool(...)`。

`tools/image_generation_tool.py:1534`

```python
    raw = image_generate_tool(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        image_url=image_url,
        reference_image_urls=reference_image_urls,
    )
    return _postprocess_image_generate_result(raw, task_id=task_id)
```

三条路的返回值都过同一个 `_postprocess_image_generate_result`。

### 1.3 内置 FAL 路的内部顺序(第 3 级)

1. `_resolve_fal_model()` → `(model_id, meta)`;
2. 收集 `source_images = [image_url] + reference_image_urls`,决定 `use_edit`;
3. 校验:prompt 非空 → 后端可达 → 源图与 edit 能力匹配 → aspect_ratio 归一;
4. 组 payload(`_build_fal_payload` 或 `_build_fal_edit_payload`);
5. `_submit_fal_request(endpoint, arguments)` → `handler.get()`(**同步阻塞**);
6. 可选 Clarity 升采样(仅 `flux-2-pro` 且非 edit);
7. 返回 `{"success": true, "image": <URL>, "modality": ...}` 的 JSON **字符串**。

### 1.4 交付(结果怎么变成用户看到的图)

`_postprocess_image_generate_result` 只在 `image` 是**绝对本地路径**时才补字段:

`tools/image_generation_tool.py:818`

```python
    if not isinstance(payload, dict) or not payload.get("success"):
        return raw

    image = payload.get("image")
    if not isinstance(image, str) or not _looks_like_absolute_file_path(image):
        return raw

    env = _active_terminal_env(task_id)
    agent_path = _agent_visible_cache_path(image, env)
    if not agent_path or agent_path == image:
        return raw

    if env is not None:
        _force_artifact_sync(env)

    payload.setdefault("host_image", image)
    payload.setdefault("agent_visible_image", agent_path)
    return json.dumps(payload, ensure_ascii=False)
```

`tools/image_generation_tool.py:723`

```python
def _looks_like_absolute_file_path(value: str) -> bool:
    if not value or not isinstance(value, str):
        return False
    lower = value.lower()
    if lower.startswith(("http://", "https://", "data:")):
        return False
    if os.path.isabs(value):
        return True
    return len(value) >= 3 and value[1] == ":" and value[2] in {"/", "\\"}
```

→ **FAL 路返回 http URL,所以这段整体是 no-op。** 只有落盘型 provider(xai/openai/deepinfra/krea/openrouter/openai-codex)才会走进去。

网关侧自动附件:

`gateway/run.py:1557`

```python
_JSON_MEDIA_TOOL_PATH_FIELDS = ("host_image", "image", "agent_visible_image")
```

`gateway/run.py:1564`

```python
_TOOL_MEDIA_RE = re.compile(
    r'MEDIA:((?:[A-Za-z]:[/\\]|/|~\/)\S+\.(?:png|jpe?g|gif|webp|'
    r'mp4|mov|avi|mkv|webm|ogg|opus|mp3|wav|m4a|'
    r'flac|epub|pdf|zip|rar|7z|docx?|xlsx?|pptx?|'
    r'txt|csv|apk|ipa))',
    re.IGNORECASE,
)
```

`gateway/run.py:1628`

```python
        if tool_name == "image_generate" and "MEDIA:" not in content:
            try:
                payload = json.loads(content)
            except Exception:
                payload = None
            if isinstance(payload, dict) and payload.get("success"):
                for field in _JSON_MEDIA_TOOL_PATH_FIELDS:
                    path = payload.get(field)
                    if (isinstance(path, str)
                            and _TOOL_MEDIA_RE.fullmatch(f"MEDIA:{path}")
                            and path not in history_media_paths):
                        media_tags.append(f"MEDIA:{path}")
                        break
            continue
```

**关键**:`_TOOL_MEDIA_RE` 的路径类只接受 `X:/` / `/` / `~/` 开头,`https://…` 的 `h` 后面不是 `:`,**匹配不上**。所以:
- 落盘型 provider(本地绝对路径)→ 网关自动附上 `MEDIA:` 标签,交付确定;
- **FAL 路(URL)→ 自动附件路径完全不触发**,交付只能靠模型自己在回复里把 URL 写出来。

这就是为什么工具描述里写的是"按当前平台的文件交付约定去引用它",而不是"发 `MEDIA:` 标签"——见 §5 ▲-3。

---

## 2. 逐文件 / 逐机制

### 2.1 `agent/image_gen_provider.py`(393)—— provider 抽象与公共件

**职责**:定义后端接口 + 提供所有 provider 都要用的四个公共函数(宽高比归一、参考图归一、b64 落盘、URL 落盘、成功/失败响应构造)。

#### 2.1.1 ABC 形状:一个抽象属性 + 一个抽象方法,其余全给默认实现

`agent/image_gen_provider.py:64`

```python
class ImageGenProvider(abc.ABC):
    """Abstract base class for an image generation backend.

    Subclasses must implement :meth:`generate`. Everything else has sane
    defaults — override only what your provider needs.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Stable short identifier used in ``image_gen.provider`` config.

        Lowercase, no spaces. Examples: ``fal``, ``openai``, ``replicate``.
        """
```

可选 hook(都有默认值):`display_name`(默认 `name.title()`)、`is_available()`(默认 `True`)、`list_models()`(默认 `[]`)、`get_setup_schema()`(默认从 `display_name` 派生)、`default_model()`(默认取 `list_models()[0]["id"]`)、`capabilities()`。

`capabilities()` 的默认值是**纯文生图**,这是刻意的向后兼容:

`agent/image_gen_provider.py:160`

```python
        return {
            "modalities": ["text"],
            "max_reference_images": 0,
        }
```

> **取舍**:默认 text-only 意味着一个老插件不改一行代码也不会被误当成支持图生图。代价是新插件必须**记得**覆写,否则动态 schema 会告诉模型"这个模型不支持 image_url",从而白白丢功能。作者选了"沉默降级"而不是"沉默升级"。

#### 2.1.2 `generate()` 的签名就是路由契约

`agent/image_gen_provider.py:165`

```python
    @abc.abstractmethod
    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        *,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
```

- **一个工具覆盖两种模态**:有 `image_url`/`reference_image_urls` 就走编辑端点,没有就走文生图。路由判据是"入参在不在",不是新开一个工具。
- `**kwargs` 是**强制的前向兼容口子**:docstring 明写实现"MUST ignore unknown keys (no TypeError)"。调用侧对不遵守这条的老插件有兜底(见 §2.4.6)。

#### 2.1.3 统一响应形状

`success_response(...)` / `error_response(...)` 产出固定 7~8 键的 dict:`success / image / model / prompt / aspect_ratio / modality / provider`(+ 失败时 `error / error_type`)。`image` 可以是 URL 也可以是绝对路径——**这个二义性是全簇下游所有分支判断的根源**(`_postprocess_image_generate_result`、`_TOOL_MEDIA_RE`)。

#### 2.1.4 `save_url_image()`:为什么要把远端 URL 拉回本地

docstring 给的理由是 URL 会过期(Telegram `send_photo`、浏览器抓取都可能在过期后才解析)。实现里三处细节值得抄:

**(a) 扩展名推断:content-type 表优先,URL 后缀兜底,最后 png**

`agent/image_gen_provider.py:299`

```python
    content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    extension = _URL_IMAGE_CONTENT_TYPES.get(content_type)
    if extension is None:
        url_path = url.split("?", 1)[0].lower()
        for ext in ("png", "jpg", "jpeg", "webp", "gif"):
            if url_path.endswith(f".{ext}"):
                extension = "jpg" if ext == "jpeg" else ext
                break
    if extension is None:
        extension = "png"
```

`_URL_IMAGE_CONTENT_TYPES` 只有 5 个条目,注释写明**故意不用 `mimetypes`**:"we never want to inherit a content-type that points at HTML or JSON when the API gives us a degenerate response"。即:白名单表既是省 import,更是**防止把错误页当图片存下来**。

**(b) 流式写入 + 硬上限 25 MB,超限删文件并抛错**

`agent/image_gen_provider.py:314`

```python
    bytes_written = 0
    with path.open("wb") as fh:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            bytes_written += len(chunk)
            if bytes_written > max_bytes:
                fh.close()
                try:
                    path.unlink()
                except OSError:
                    pass
                raise ValueError(
                    f"Image at {url} exceeds {max_bytes // (1024 * 1024)}MB cap; refusing to cache."
                )
            fh.write(chunk)
```

**(c) 0 字节也算失败**(`bytes_written == 0` → 删文件 + `ValueError`)。

落盘位置固定 `$HERMES_HOME/cache/images/`,文件名 `<prefix>_<YYYYMMDD_HHMMSS>_<8位uuid>.<ext>`。

> **取舍**:`save_url_image` 用同步 `requests`(函数内 import)。它跑在同步工具线程里,所以不需要 async;代价是不能复用 `image_source.py` 那套 SSRF/策略校验——这里下载的是**provider 自己返回的 URL**(可信),不是模型给的 URL(不可信),所以作者认为不需要。这个区分要记住:**同一个仓库里"下载图片"有两套完全不同的安全姿势,判据是 URL 从哪来。**

---

### 2.2 `agent/image_gen_registry.py`(145)—— 注册表与"谁是活跃后端"

**职责**:一个进程级 `Dict[str, ImageGenProvider]` + 一把 `threading.Lock`,加上"没配置时选谁"的三段回退。

#### 2.2.1 注册:类型闸门 + 覆盖式重注册

`agent/image_gen_registry.py:43`

```python
    if not isinstance(provider, ImageGenProvider):
        raise TypeError(
            f"register_provider() expects an ImageGenProvider instance, "
            f"got {type(provider).__name__}"
        )
    name = provider.name
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Image gen provider .name must be a non-empty string")
    with _lock:
        existing = _providers.get(name)
        _providers[name] = provider
```

同名重注册 = 覆盖 + debug 日志,注释说明这是为热重载/测试循环服务。

注意**两层类型检查**:`register_provider` 抛 `TypeError`,但插件侧的 `PluginContext.register_image_gen_provider` 先自己查一遍并**只记 WARNING 不抛**——坏插件不能把宿主搞崩。

`hermes_cli/plugins.py:679`

```python
        from agent.image_gen_provider import ImageGenProvider
        from agent.image_gen_registry import register_provider

        if not isinstance(provider, ImageGenProvider):
            logger.warning(
                "Plugin '%s' tried to register an image_gen provider that does "
                "not inherit from ImageGenProvider. Ignoring.",
                self.manifest.name,
            )
            return
```

#### 2.2.2 发现机制:内置 backend 插件**自动加载**,用户插件 opt-in

`hermes_cli/plugins.py:1449`

```python
            # Built-in backends auto-load — they ship with hermes and must
            # just work. Selection among them (e.g. which image_gen backend
            # services calls) is driven by ``<category>.provider`` config,
            # enforced by the tool wrapper.
            if manifest.source == "bundled" and manifest.kind == "backend":
                self._load_plugin(manifest)
                continue
```

`plugins/image_gen/fal/plugin.yaml` 的 manifest:

```yaml
name: fal
version: 1.0.0
description: "FAL.ai image generation backend (flux-2-klein, flux-2-pro, nano-banana, gpt-image-1.5, recraft-v3, etc.)."
author: NousResearch
kind: backend
requires_env:
  - FAL_KEY
```

仓库内 **7 个内置 image_gen 插件**:`deepinfra` / `fal` / `krea` / `openai` / `openai-codex` / `openrouter` / `xai`,各自 `register(ctx)` 调 `ctx.register_image_gen_provider(...)`。`openrouter` 是唯一一个在循环里注册**多个** provider 的。

#### 2.2.3 `get_active_provider()`:显式配置 vs 可用性,两套语义

`agent/image_gen_registry.py:116`

```python
    # 1. Explicit config wins — return regardless of is_available() so the
    #    user gets a precise downstream error message rather than a silent
    #    backend switch.
    if configured:
        provider = snapshot.get(configured)
        if provider is not None:
            return provider
        logger.debug(
            "image_gen.provider='%s' configured but not registered; falling back",
            configured,
        )

    # 2. Fallback: single registered provider — but only if it's actually
    #    available (no credentials = don't surface it as "active").
    available = [p for p in snapshot.values() if _is_available_safe(p)]
    if len(available) == 1:
        return available[0]

    # 3. Fallback: prefer legacy FAL for backward compat, when available.
    fal = snapshot.get("fal")
    if fal is not None and _is_available_safe(fal):
        return fal

    return None
```

**这是全簇最值得抄的一个设计**:

- **显式配置的 provider 即使 `is_available()==False` 也照样返回**——因为用户明确说了要它,后面报"X_API_KEY 未设置"比"我悄悄换了个后端"有用得多;
- **未配置时的回退才用 `is_available()` 过滤**——不能因为用户碰巧有个 OPENAI_API_KEY 就把他推上一个付费图像后端;
- `_is_available_safe` 把 `is_available()` 包在 try 里,**一个写坏的 provider 不能让整个解析崩掉**;
- 回退第 2 步是"恰好只有一个可用"而不是"取第一个",避免了顺序依赖。

**重要的作用域事实**:`get_active_provider()` 在**本簇的出图主链路上没有被调用**。真正的分派用的是 `_read_configured_image_provider()` + `get_provider(name)`。它的唯一非测试消费者在电子宠物的形象生成里:

`agent/pet/generate/imagegen.py:82`

```python
    _discover()
    from agent.image_gen_registry import get_active_provider, get_provider
```

搜索面(全仓 `.py`,排除 `tests/`)。**必须限定到 image_gen 的那一个** —— 全仓另有一个同名但完全无关的函数,指的是推理 provider,裸搜 `get_active_provider` 会把它连同 5 处调用一起捞进来:

`hermes_cli/auth.py:1777`

```python
def get_active_provider() -> Optional[str]:
    """Return the currently active provider ID from auth store."""
    auth_store = _load_auth_store()
    return auth_store.get("active_provider")
```

```verify
cd /home/user/hermes-agent && grep -rn "image_gen_registry import get_active_provider\|image_gen_registry\.get_active_provider" --include=*.py . | grep -v "^./tests/"
```

实测 2 处命中:`agent/pet/generate/imagegen.py:83` 是**唯一真实调用点**;另一处只是视频孪生里一条说"我照着它写的"的注释,连回退逻辑都是同一形状:

`agent/video_gen_registry.py:122`

```python
    # Mirrors agent/image_gen_registry.get_active_provider().
    available = [p for p in snapshot.values() if _is_available_safe(p)]
    if len(available) == 1:
        return available[0]
```

#### 2.2.4 `_reset_for_tests()`

一个显式的测试后门(清空 `_providers`),`tests/agent/test_image_gen_registry.py` 与 `tests/tools/test_image_generation_image_to_image.py` 的 autouse fixture 都用它。全局单例 + 测试后门,是 harness 里很常见的取舍:**要么注入依赖(改所有调用方),要么留个后门(改测试)**,这里选了后者。

---

### 2.3 `agent/image_routing.py`(821)—— 它到底在路由什么

**先纠一个望文生义**:这 821 行**不路由图像生成**。它路由的是"用户这一轮附上来的图片,怎么塞进给主模型的那条消息里"。三块内容:

| 块 | 行数区间 | 干什么 |
|---|---|---|
| A. 引用抽取 | `agent/image_routing.py:52` 的 `_VALID_MODES` 起至 ~148 | 从自由文本里扫出本地图片路径 / 图片 URL |
| B. 能力解析 + 模式决策 | ~151–506 | 主模型支不支持 vision → native 还是 text |
| C. 字节到 content part | ~509–814 | 读文件 → 嗅探 MIME → 必要时转码 PNG → base64 data URL → 组 parts |

#### 2.3.1 块 A:引用抽取(`extract_image_refs`)

两条正则:

`agent/image_routing.py:68`

```python
_LOCAL_IMAGE_PATH_RE = re.compile(
    r"(?<![/:\w.])(?:~/|/)(?:[\w.\-]+/)*[\w.\-]+\.(?:" + _IMAGE_EXT_PATTERN + r")\b",
    re.IGNORECASE,
)

# http(s) URL ending in an image extension (optionally followed by a
# query string). Case-insensitive on the extension. Strict ``http(s)://``
# scheme so we don't accidentally grab ``file://`` URLs or other shapes.
_IMAGE_URL_RE = re.compile(
    r"https?://[^\s<>\"']+?\.(?:" + _IMAGE_EXT_PATTERN + r")(?:\?[^\s<>\"']*)?",
    re.IGNORECASE,
)
```

设计点:
- `(?<![/:\w.])` 反向零宽断言,防止把 URL 里的路径片段当成本地路径抓走;
- 扩展名白名单 `_IMAGE_EXTS` 只 9 个,注释说明**故意收紧**——文档/压缩包由网关的 `extract_local_files()` 走 `send_document`,不能被当成 vision part;
- **跳过代码块**:`` ``` `` 围栏与行内反引号的 span 先算出来,落在里面的匹配一律跳过。理由是"贴进任务正文当例子的片段不该被当成真附件";
- 本地路径要 `os.path.isfile()` 校验才收,URL 不校验(provider 请求时自己拉);
- `OSError` 被吞掉(`ENAMETOOLONG`/`EINVAL` 的病态输入不能让整轮崩)。

#### 2.3.2 块 B:能力解析——`supports_vision` 覆盖的四层查找

`_supports_vision_override(cfg, provider, model, *, requested_provider="")` 的顺序:

1. `model.supports_vision`(顶层快捷方式)
2. `providers.<provider>.models.<model>.supports_vision`(或别名 `vision`)
3. 同上,但 provider 键的**候选集**是 `{requested_provider, provider, model.provider}` 各自再加上 `custom:` 前缀剥离形式
4. `custom_providers`(遗留 list 形式)

为什么要一个候选集?因为命名自定义 provider 在运行时被规范化成 `provider="custom"`,而 config 里还是用户写的名字。

严格布尔强转是这块最值得抄的细节:

`agent/image_routing.py:159`

```python
_TRUE_TOKENS = frozenset({"true", "yes", "on", "1"})
_FALSE_TOKENS = frozenset({"false", "no", "off", "0"})
```

注释讲清了动机:`bool("false")` 在 Python 里是 `True`,用户在 YAML 里写 `supports_vision: "false"`(加了引号——常见错误)就会**静默打开** native vision。所以只认 YAML 1.1/1.2 承认的布尔字面量 + 真 bool + 整数 0/1,其余一律返回 `None` 让调用方继续往下找 models.dev。

回退链:config 覆盖 → `agent.models_dev.get_model_capabilities` → (若判定像本地 Ollama)`query_ollama_supports_vision` 探测 → `None`。

`_lookup_supports_vision` 里还有一条**身份借用防护**:

`agent/image_routing.py:400`

```python
    # Named custom providers are canonicalized to ``provider="custom"`` by
    # runtime resolution.  The original CLI/config name is carried in the
    # context-local main runtime so capability lookup can still select the
    # exact custom_providers entry.  Require an exact provider+model match:
    # background/auxiliary lookups must never borrow another turn's identity.
```

即:从 context-local 运行时里取 `requested_provider` 之前,必须先确认运行时的 provider+model 与本次查询**完全一致**,否则后台/辅助查询会借到别的 turn 的身份。

#### 2.3.3 块 C:字节 → content part

**(1) 魔术字节嗅探优先于文件名**

`_sniff_mime_from_bytes` 覆盖 PNG/JPEG/GIF/WEBP/BMP/ISO-BMFF(AVIF、HEIC 家族)/TIFF/ICO/SVG。docstring 给的动机是真实事故:Discord 会给代理/动画贴纸的 PNG 标 `content_type=image/webp`,而 Anthropic 严格校验 `media_type` 与真实字节一致,不一致直接 HTTP 400。

**(2) 非通用格式转码为 PNG**

`agent/image_routing.py:586`

```python
_UNIVERSALLY_SUPPORTED_MIMES = frozenset({
    "image/png", "image/jpeg", "image/gif", "image/webp",
})
```

`agent/image_routing.py:707`

```python
    mime = _guess_mime(path, raw=raw)
    if mime not in _UNIVERSALLY_SUPPORTED_MIMES:
        transcoded = _transcode_to_png(raw)
        if transcoded is None:
            logger.warning(
                "image_routing: %s is %s which is not accepted by all major "
                "vision providers and could not be transcoded to PNG; "
                "skipping this attachment.",
                path, mime,
            )
            return None
        logger.info(
            "image_routing: transcoded %s (%s) -> image/png for provider compatibility",
            path.name, mime,
        )
        raw = transcoded
        mime = "image/png"
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"
```

`_transcode_to_png` 用 Pillow,并**按需注册可选插件**(`pillow_heif.register_heif_opener()`、`import pillow_avif`),两个 import 都吞异常——插件缺失只表现为"Pillow 解不了这个格式",不会崩。SVG 是矢量,Pillow 栅格化不了,被跳过(记日志)。

**(3) 凭据读闸门**

`agent/image_routing.py:691`

```python
    try:
        from agent.file_safety import raise_if_read_blocked

        raise_if_read_blocked(str(path))
    except ValueError as exc:
        logger.warning("image_routing: blocked local image attachment %s -- %s", path, exc)
        return None
    except Exception:
        # Keep attachment routing best-effort if the guard itself is unavailable.
        pass
```

`tests/agent/test_image_routing.py:423` 的 `test_file_to_data_url_blocks_read_denied_image_path` 把一个真 PNG 命名为 `.env`,断言返回 `None`;`test_native_content_parts_blocks_image_symlink_to_read_denied_file` 断言指向 `.env` 的符号链接也被拦。

**(4) 尺寸:反应式而非预防式**

`agent/image_routing.py:509`

```python
# Image size handling is REACTIVE rather than proactive: we attempt native
# attachment at full size regardless of provider, and rely on
# ``run_agent._try_shrink_image_parts_in_messages`` to shrink + retry if
# the provider rejects the request (e.g. Anthropic's hard 5 MB per-image
# ceiling returned as HTTP 400 "image exceeds 5 MB maximum").
#
# Why reactive: our knowledge of provider ceilings is partial and evolving
# (OpenAI accepts 49 MB+, Anthropic 5 MB, Gemini 100 MB, others unknown).
# A proactive per-provider table would be stale the moment a provider raises
# or lowers its limit, and silently degrading quality for users on providers
# that would have accepted the full image is the worse failure mode.
# The shrink-on-reject path loses 1 API call + maybe 1s of Pillow work when
# it fires, which is cheaper than permanent quality loss.
```

> **这是全簇最好的一段"为什么"注释**,值得整段抄进蓝图:*不要为一张会腐烂的外部限制表付出静默降质的代价;宁可多花一次 API 调用。*

**(5) 路径提示(string handle)**

`build_native_content_parts` 在文本 part 里为每张图追加一行:本地图 `[Image attached at: <path>]`,URL `[Image attached: <url>]`。理由:MCP/skill 工具的参数是 `image_url: str`,模型需要一个**字符串把手**才能对同一张图再调工具,否则要多一次往返。text 模式那边由 `Runner._enrich_message_with_vision` 产出对应提示,两种模式行为一致。

---

### 2.4 `tools/image_generation_tool.py`(1668)—— 本簇最大的一块

**职责(六件事)**:FAL 模型目录 / payload 翻译 / 提交与托管网关 / 升采样 / 三级分派 / 动态 schema。

#### 2.4.1 模型目录 `FAL_MODELS`:数据即翻译规则

11 个条目。每条的字段就是一套完整的翻译规则:

`tools/image_generation_tool.py:98`

```python
    "fal-ai/flux-2/klein/9b": {
        "display": "FLUX 2 Klein 9B",
        "speed": "<1s",
        "strengths": "Fast, crisp text",
        "price": "$0.006/MP",
        "size_style": "image_size_preset",
        "sizes": {
            "landscape": "landscape_16_9",
            "square": "square_hd",
            "portrait": "portrait_16_9",
        },
        "defaults": {
            "num_inference_steps": 4,
            "output_format": "png",
            "enable_safety_checker": False,
        },
        "supports": {
            "prompt", "image_size", "num_inference_steps", "seed",
            "output_format", "enable_safety_checker",
        },
        "upscale": False,
        # Image-to-image / editing: FLUX.2 [klein] 9B edit endpoint takes
        # `image_urls` (list). Natural-language edits, multi-ref.
        "edit_endpoint": "fal-ai/flux-2/klein/9b/edit",
        "edit_supports": {
            "prompt", "image_urls", "num_inference_steps", "seed",
            "output_format", "enable_safety_checker",
        },
        "max_reference_images": 9,
    },
```

三个尺寸族(`size_style`):

| 族 | 值形态 | 用它的模型 |
|---|---|---|
| `image_size_preset` | `landscape_16_9` / `square_hd` / `portrait_16_9`(gpt-image-2 用 `*_4_3`) | flux-2 系、z-image、qwen、recraft、ideogram、gpt-image-2 |
| `aspect_ratio` | `16:9` / `1:1` / `9:16` | nano-banana-pro、krea/v2 两款 |
| `gpt_literal` | `1536x1024` / `1024x1024` / `1024x1536` | gpt-image-1.5 |

11 个模型的能力矩阵(从目录直接读出):

| model id | size_style | upscale | edit_endpoint | max_reference_images |
|---|---|---|---|---|
| `fal-ai/flux-2/klein/9b`(默认) | preset | False | `fal-ai/flux-2/klein/9b/edit` | 9 |
| `fal-ai/flux-2-pro` | preset | **True** | `fal-ai/flux-2-pro/edit` | 9 |
| `fal-ai/z-image/turbo` | preset | False | 无 | — |
| `fal-ai/nano-banana-pro` | aspect_ratio | False | `fal-ai/nano-banana-pro/edit` | 2 |
| `fal-ai/gpt-image-1.5` | gpt_literal | False | `fal-ai/gpt-image-1.5/edit` | **16** |
| `fal-ai/gpt-image-2` | preset(4:3) | False | `openai/gpt-image-2/edit` | **16** |
| `fal-ai/ideogram/v3` | preset | False | `fal-ai/ideogram/v3/edit` | 1 |
| `fal-ai/recraft/v4/pro/text-to-image` | preset | False | 无 | — |
| `fal-ai/qwen-image` | preset | False | `fal-ai/qwen-image-2/pro/edit` | 3 |
| `fal-ai/krea/v2/medium/text-to-image` | aspect_ratio | False | 无 | — |
| `fal-ai/krea/v2/large/text-to-image` | aspect_ratio | False | 无 | — |

注意 `fal-ai/gpt-image-2` 的编辑端点在 **`openai/` 命名空间**(不是 `fal-ai/`),目录注释专门点了这一条。

目录里三处**成本决策被写死**,不给用户开关:

- gpt-image-1.5 / gpt-image-2 的 `quality` 钉在 `"medium"`(`tools/image_generation_tool.py:271` 注释:`"high" is 3-4x the per-image cost at the same size`);
- nano-banana-pro 的 `resolution` 钉在 `"1K"`(4K 双倍价);
- z-image/turbo 的 `enable_prompt_expansion: False`(注释 `avoid the extra per-request charge`)。

`tests/tools/test_image_generation.py:197` 的 `test_resolve_gpt_quality_function_is_gone` 甚至断言那个曾经存在的运行时查找函数**已被删除**——把"钉死"变成一条可执行的规格。

> **取舍**:目录是**代码里的字面量**,不是配置文件,也不是从 FAL API 拉的。好处是可版本控制、可被测试断言、零启动开销;代价是 FAL 上新模型/改价必须发版。模块 docstring 明说"Pricing shown in UI strings is as-of the initial commit; we accept drift and update when it's noticed"——**把漂移写成显式接受的取舍**,这个态度值得抄。

#### 2.4.2 `_resolve_fal_model()`:配置 → 环境变量 → 默认

顺序是 `image_gen.model`(config.yaml)→ `FAL_IMAGE_MODEL`(env)→ `DEFAULT_MODEL`。未知 model id **不报错**,记 WARNING 后回落默认。

`tests/tools/test_image_generation.py:217` 的 `test_config_wins_over_env_var` 把这个优先级钉成规格。

代码注释称 `FAL_IMAGE_MODEL` 是 "undocumented; undocumented backward-compat for tests/scripts"(原文 `# Env var escape hatch (undocumented; backward-compat for tests/scripts).`),但 `website/docs/user-guide/features/image-generation.md:184` **确实把它写进了文档**。这不是 ▲(文档为真),是**代码注释过期**,记为观察项(§6 移交-4)。

#### 2.4.3 payload 构造:白名单是主要安全属性

`tools/image_generation_tool.py:604`

```python
    supports = meta["supports"]
    # ``prompt`` is required by every FAL text-to-image endpoint; keep it even
    # if a model's ``supports`` whitelist omits it, so a missing whitelist entry
    # can't silently strip the prompt and send an empty request.
    return {
        k: v for k, v in payload.items()
        if k in supports or k == "prompt"
    }
```

编辑版多了一个"必留键"集合:

`tools/image_generation_tool.py:660`

```python
    # ``prompt`` and ``image_urls`` are required by every FAL edit endpoint;
    # keep them even if a model's ``edit_supports`` whitelist omits them, so a
    # missing whitelist entry can't silently drop the prompt or the source
    # images and send a broken edit request.
    _required = {"prompt", "image_urls"}
    return {
        k: v for k, v in payload.items()
        if k in edit_supports or k in _required
    }
```

> **设计原则**:白名单过滤 + **必留键旁路**。白名单防的是"给模型发了它会拒的键";必留键防的是"白名单本身写漏了,于是发出去一个空请求"。两个失败模式方向相反,所以都要防。
> `tests/tools/test_image_generation_image_to_image.py:71` 的 `TestMandatoryKeysSurviveWhitelist` 专门注入一个 `edit_supports={"seed"}` 的假模型来钉这条。

编辑 payload 的尺寸处理与文生图不同——**只有 `edit_supports` 明说接受时才发**:

`tools/image_generation_tool.py:644`

```python
    # Only express output size when the edit endpoint advertises the key.
    # gpt-image-2 edit auto-infers size from the input, so `image_size` is
    # intentionally absent from its edit_supports whitelist.
    if size_style in {"image_size_preset", "gpt_literal"} and "image_size" in edit_supports:
        payload["image_size"] = sizes[aspect]
    elif size_style == "aspect_ratio" and "aspect_ratio" in edit_supports:
        payload["aspect_ratio"] = sizes[aspect]
```

overrides 的合并规则:`None` 值**不覆盖默认**(`if v is not None`),`tests/tools/test_image_generation.py:174` 的 `test_none_override_does_not_replace_default` 钉住它。

#### 2.4.4 参数校验(全部在 `image_generate_tool` 的 try 里)

| 校验 | 行为 | 锚点 |
|---|---|---|
| prompt 空 | `raise ValueError("Prompt is required and must be a non-empty string")` | `tools/image_generation_tool.py:901` 的 `if not prompt or not isinstance(prompt, str)` |
| 无后端 | `raise ValueError(_build_no_backend_setup_message())` | `tools/image_generation_tool.py:904` 的 `if not (fal_key_is_configured() or _resolve_managed_fal_gateway())` |
| 给了源图但模型不支持编辑 | 明确报错,**不静默丢图** | `tools/image_generation_tool.py:910` 的 `if source_images and not edit_endpoint` |
| aspect_ratio 非法 | WARNING 后回落 landscape,**不报错** | `tools/image_generation_tool.py:919` 的 `if aspect_lc not in VALID_ASPECT_RATIOS` |
| 参考图超上限 | 静默截断到 `max_reference_images` | `tools/image_generation_tool.py:938` 的 `max_refs = int(meta.get("max_reference_images") or 1)` |

"给了源图但模型不支持编辑"这一条是本文件里错误信息写得最好的一处:

`tools/image_generation_tool.py:910`

```python
        if source_images and not edit_endpoint:
            raise ValueError(
                f"Model '{meta.get('display', model_id)}' ({model_id}) is not "
                f"capable of image-to-image / editing. Provide a text-only "
                f"prompt (omit image_url), or switch to an edit-capable model "
                f"via `hermes tools` → Image Generation."
            )
```

**三要素**:出了什么事 + 为什么 + 两条可执行的下一步。全簇的错误信息基本都是这个模板。

参考图截断:

`tools/image_generation_tool.py:936`

```python
        if use_edit:
            # Clamp reference count to the model's declared cap.
            max_refs = int(meta.get("max_reference_images") or 1)
            clamped_sources = source_images[:max_refs] if max_refs > 0 else source_images
            arguments = _build_fal_edit_payload(
                model_id, prompt, clamped_sources, aspect_lc,
                seed=seed, overrides=overrides,
            )
            endpoint = edit_endpoint
            logger.info(
                "Editing image with %s (%s) — %d source image(s), prompt: %s",
                meta.get("display", model_id), endpoint, len(clamped_sources),
                prompt[:80],
            )
```

注意 `clamped_sources` 截的是**主图 + 参考图合并后的列表**,即 `max_reference_images` 实际是"源图总数上限"而不是"参考图上限"。名字与语义有偏差,重实现时别抄名字。

#### 2.4.5 提交、凭据与托管网关

**凭据选择**:

`tools/image_generation_tool.py:452`

```python
def _resolve_managed_fal_gateway():
    """Return managed fal-queue gateway config when the user prefers the gateway
    or direct FAL credentials are absent."""
    if fal_key_is_configured() and not prefers_gateway("image_gen"):
        return None
    return resolve_managed_tool_gateway("fal-queue")
```

→ 有 `FAL_KEY` **且**没打开 `image_gen.use_gateway` = 直连;否则试托管网关。

`fal_key_is_configured()` 同时看 `os.environ` 和 `~/.hermes/.env`(经 `hermes_cli.config.get_env_value`),**空白串算未设置**:

`tests/tools/test_image_generation_env.py:4`

```python
def test_fal_key_whitespace_is_unset(monkeypatch):
    # Whitespace-only FAL_KEY must NOT register as configured, and the managed
    # gateway fallback must be disabled for this assertion to be meaningful.
    monkeypatch.setenv("FAL_KEY", "   ")

    from tools import image_generation_tool

    monkeypatch.setattr(
        image_generation_tool, "_resolve_managed_fal_gateway", lambda: None
    )

    assert image_generation_tool.check_fal_api_key() is False
```

**提交**:

`tools/image_generation_tool.py:484`

```python
def _submit_fal_request(model: str, arguments: Dict[str, Any]):
    """Submit a FAL request using direct credentials or the managed queue gateway."""
    # Trigger the lazy import on first call. Idempotent.
    _load_fal_client()
    request_headers = {"x-idempotency-key": str(uuid.uuid4())}
    managed_gateway = _resolve_managed_fal_gateway()
    if managed_gateway is None:
        return fal_client.submit(model, arguments=arguments, headers=request_headers)
```

每次提交带一个 `x-idempotency-key`(随机 UUID),这样 SDK 内部重试不会重复计费。

**托管网关 4xx 翻译**——这是"重试/错误呈现"里最有价值的一段:

`tools/image_generation_tool.py:505`

```python
        status = _extract_http_status(exc)
        if status is not None and 400 <= status < 500:
            gateway_message = ""
            if status in {401, 402, 403}:
                gateway_message = (
                    "\n\n"
                    + nous_tool_gateway_unavailable_message(
                        "managed FAL image generation",
                        force_fresh=True,
                    )
                )
            raise ValueError(
                f"Nous Subscription gateway rejected model '{model}' "
                f"(HTTP {status}). This model may not yet be enabled on "
                f"the Nous Portal's FAL proxy. Either:\n"
                f"  • Set FAL_KEY in your environment to use FAL.ai directly, or\n"
                f"  • Pick a different model via `hermes tools` → Image Generation."
                f"{gateway_message}"
            ) from exc
```

`raise ... from exc` 保留原异常链(`tests/tools/test_image_generation.py:324` 断言 `exc_info.value.__cause__ is bad_request`)。非 4xx(连接错误、超时)**原样冒泡**,让上层决定重试/诊断(`tests/tools/test_image_generation.py:327` 钉住)。

**重试:本模块自己一次都没写。** 唯一的重试来自 `fal_client.client._maybe_retry_request`(见 §2.6)。`image_generate_tool` 的整个函数体裹在一个 `try/except Exception` 里,**任何异常都转成 `{"success": false, ...}` JSON 返回,不向上抛**:

`tools/image_generation_tool.py:1020`

```python
    except Exception as e:
        generation_time = (datetime.datetime.now() - start_time).total_seconds()
        error_msg = f"Error generating image: {str(e)}"
        logger.error("%s", error_msg, exc_info=True)

        response_data = {
            "success": False,
            "image": None,
            "error": str(e),
            "error_type": type(e).__name__,
        }
```

> **取舍**:工具永不抛异常 = 模型总能拿到一个可读的结果并自己决定下一步(换模型 / 改提示词 / 放弃)。代价是**真正的 bug 也被降级成"生成失败"**,只在日志里留 `exc_info=True`。

#### 2.4.6 升采样(Clarity Upscaler)

常量全在模块级(`UPSCALER_FACTOR=2`、`UPSCALER_CREATIVITY=0.35`、`UPSCALER_RESEMBLANCE=0.6`、`UPSCALER_GUIDANCE_SCALE=4`、`UPSCALER_NUM_INFERENCE_STEPS=18`)。

`tools/image_generation_tool.py:974`

```python
        should_upscale = bool(meta.get("upscale", False)) and not use_edit
```

`tools/image_generation_tool.py:986`

```python
            if should_upscale:
                upscaled_image = _upscale_image(img["url"], prompt.strip())
                if upscaled_image:
                    formatted_images.append(upscaled_image)
                    continue
                logger.warning("Using original image as fallback (upscale failed)")

            original_image["upscaled"] = False
            formatted_images.append(original_image)
```

三条规则:
- **按模型门控**——只有 `flux-2-pro` 开(为向后兼容,它是加模型选择器之前的默认);
- **编辑一律跳过**——编辑端点返回的已是最终构图,升采样是文生图的质量补丁;
- **失败即降级**——`_upscale_image` 整个包在 try 里返回 `None`,调用方回落原图,只记 WARNING。

"只有 flux-2-pro"这条被写成遍历整个目录的不变量断言:

`tests/tools/test_image_generation.py:50`

```python
    def test_only_flux2_pro_upscales_by_default(self, image_tool):
        """Upscaling should default to False for all new models to preserve
        the <1s / fast-render value prop. Only flux-2-pro stays True for
        backward-compat with the previous default."""
        for mid, meta in image_tool.FAL_MODELS.items():
            if mid == "fal-ai/flux-2-pro":
                assert meta["upscale"] is True, \
                    "flux-2-pro should keep upscale=True for backward-compat"
            else:
                assert meta["upscale"] is False, \
                    f"{mid} should default to upscale=False"
```

"编辑跳过升采样"由 `tests/tools/test_image_generation_image_to_image.py:135` 的 `def test_edit_skips_upscaler` 钉住(它给 `_upscale_image` 打桩并断言桩没被调用)。

#### 2.4.7 插件分派与老插件兼容

`tools/image_generation_tool.py:1283`

```python
    configured = _read_configured_image_provider()
    if not configured or configured == "fal":
        return None  # unset/explicit FAL keeps the legacy FAL path
```

`"fal"` 走内置路而不是 `plugins/image_gen/fal/` —— 因为那个插件本身只是个**注册适配器**,它的 `generate()` 又调回 `_it.image_generate_tool`(见 §2.7)。所以两条路结果一致,少一层。

provider 找不到时先**强制刷新一次**再报错(长会话里 config 可能中途变了):

`tools/image_generation_tool.py:1302`

```python
    if provider is None:
        try:
            # Long-lived sessions may have discovered plugins before a bundled
            # backend was patched in or before config changed. Retry once with
            # a forced refresh before surfacing a missing-provider error.
            _ensure_plugins_discovered(force=True)
            provider = get_provider(configured)
        except Exception as exc:
            logger.debug("image_gen plugin force-refresh skipped: %s", exc)
```

**老插件签名太窄的兜底**——这是 `**kwargs` 契约的执行点:

`tools/image_generation_tool.py:1338`

```python
    except TypeError as exc:
        # A provider whose generate() signature predates image_url support
        # (third-party plugin not yet updated) — retry without the new kwargs
        # so text-to-image keeps working, but surface a clear note when the
        # user actually asked for an edit.
        if "image_url" in kwargs or "reference_image_urls" in kwargs:
```

**注意:注释说的 "retry without the new kwargs" 在代码里并不存在** —— 这个分支直接返回 `error_type: "modality_unsupported"` 的 JSON,没有任何重试。测试 `tests/tools/test_image_generation_image_to_image.py:223` 的 `test_legacy_provider_edit_request_surfaces_clear_error` 断言的正是"返回错误"。所以注释过期,行为以代码+测试为准。记为移交项(§6 移交-3)。

四种错误 `error_type`:`provider_not_registered` / `modality_unsupported` / `provider_exception` / `provider_contract`(返回非 dict)。**分类本身是给模型看的**——模型据此决定是换模型还是换提示词。

#### 2.4.8 动态 schema:把后端能力写进工具描述

`tools/image_generation_tool.py:1547`

```python
# Why dynamic: whether the active model supports image-to-image / editing
# depends entirely on the user's configured backend + model. Telling the
# model up front ("the active model is text-to-image only — image_url will be
# rejected") saves a wasted turn. Memoized by config.yaml mtime in
# model_tools.get_tool_definitions(), so it rebuilds when the user switches
# model/provider via `hermes tools` or `/skills`.
```

`_active_image_capabilities()` 的解析顺序**镜像运行时分派**:配了插件 provider 就问插件的 `capabilities()`,否则查内置 FAL 目录。三种描述分支:

`tools/image_generation_tool.py:1631`

```python
    if "image" in modalities and "text" in modalities:
        max_refs = info.get("max_reference_images") or 0
        ref_note = (
            f"; up to {max_refs} reference image(s) via reference_image_urls"
            if max_refs and max_refs > 1
            else ""
        )
        parts.append(
            "- supports both text-to-image (omit image_url) and "
            f"image-to-image / editing (pass image_url){ref_note} — "
            "routes automatically"
        )
```

注册表侧的执行点:

`tools/registry.py:711`

```python
            if entry.dynamic_schema_overrides is not None:
                try:
                    overrides = entry.dynamic_schema_overrides()
                    if isinstance(overrides, dict):
                        schema_with_name.update(overrides)
                except Exception as exc:
                    logger.warning(
                        "dynamic_schema_overrides for tool %s raised %s; "
                        "using static schema",
                        name, exc,
                    )
```

抛异常就回落静态 schema。`_build_dynamic_image_schema` 内部也自带 try(`_active_image_capabilities` 失败就用通用描述),**两层兜底**。

#### 2.4.9 惰性 import:64 ms 的冷启动账

`tools/image_generation_tool.py:31`

```python
# fal_client is imported lazily — see _load_fal_client(). Pulling it
# eagerly added ~64 ms to every CLI cold start because
# discover_builtin_tools() imports this module unconditionally during
# the registry walk, even when image generation is never used.
#
# Tests that monkeypatch this attribute (e.g.
# ``monkeypatch.setattr(image_tool, "fal_client", fake_fal_client)``)
# still work: _load_fal_client() short-circuits when the attribute is
# anything truthy, so a test-installed mock is not overwritten by a
# subsequent real import.
fal_client: Any = None
```

`_load_fal_client()` 的短路条件是 `if fal_client is not None` —— **模块全局既是缓存也是测试注入点**。这也是 `fal_common.py` 顶部那段"为什么有状态的东西留在旧模块"的原因(见 §2.6)。

#### 2.4.10 并发上限(唯一的"配额"概念)

本簇**没有任何成本/配额/预算逻辑**。唯一的资源约束是并发度,而且在**工具执行器**里而不是本模块:

`agent/tool_executor.py:95`

```python
_MAX_TOOL_WORKERS = 8
_DEFAULT_IMAGE_PARALLEL_REQUESTS = 4
```

`agent/tool_executor.py:222`

```python
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = _DEFAULT_IMAGE_PARALLEL_REQUESTS
    return max(1, min(limit, _MAX_TOOL_WORKERS))
```

`agent/tool_executor.py:229`

```python
def _max_workers_for_tool_batch(runnable_calls) -> int:
    """Return the worker cap for a concurrent tool batch."""
    if not runnable_calls:
        return 0
    max_workers = _MAX_TOOL_WORKERS
    if any(
        (call[2] if len(call) >= 3 else None) == "image_generate"
        for call in runnable_calls
    ):
        max_workers = min(max_workers, _image_generate_parallel_limit())
    return min(len(runnable_calls), max_workers)
```

即:一批工具调用里**只要有一个是 `image_generate`,整批的并发上限就被压到 image 的上限**。理由(`agent/tool_executor.py:202` 的 docstring):图像生成够慢,值得并发,但突发会撞 TTFB / 限流。

负结论(搜索面写明):**本簇 6 个文件 + 7 个 image_gen 插件里,没有任何按次计费 / 预算 / 配额的执行代码。**
搜索面 = 本簇 6 个文件 + `plugins/image_gen/`(`--include=*.py`,故排除 `__pycache__` 的 `.pyc`),模式 `budget|quota|spend|credits?|\bcost\b` 大小写不敏感:

```verify
cd /home/user/hermes-agent && grep -rniE "budget|quota|spend|credits?|\bcost\b" --include=*.py agent/image_gen_provider.py agent/image_gen_registry.py agent/image_routing.py tools/image_generation_tool.py tools/image_source.py tools/fal_common.py plugins/image_gen/
```

实测 7 处命中,**全部是注释或 UI 字符串**:`tools/image_generation_tool.py:203` / `:273` 是解释为什么把档位钉死的价格注释;`tools/image_source.py:43` / `:338` 的 "budget" 指**字节数**(ingest 上限)不是钱;`plugins/image_gen/{openai-codex,krea,openai}` 三处是模型简介里的 "lowest cost" 之类文案。

**搜索面为什么不含 `agent/tool_executor.py`**:它确实有一整套 `budget` 机制,但那是**工具输出的 token 预算**,与图像生成的钱无关 ——

`agent/tool_executor.py:51`

```python
from tools.budget_config import BudgetConfig, DEFAULT_BUDGET, budget_for_context_window
```

把它放进搜索面只会让这条命令的输出与结论相反(实测会多出 30 余处 `budget` 命中)。本簇从 `tool_executor.py` 只借了并发上限那一段。

---

### 2.5 `tools/image_source.py`(391)—— 输入媒体的统一解析器(不属于出图链路)

**职责**:把"模型/工具给的一个媒体来源字符串"解析成 `(bytes, mime, origin)`,并在**唯一的一处**做尺寸与类型检查。

`tools/image_source.py:1`

```python
"""Single resolver for every media source -> bytes + mime.

All source handling (data:/http(s)/file/local/container) funnels through
:func:`resolve_image_source` so size and magic-byte checks are enforced exactly
once.  Returns raw bytes (not a path): the downstream step is base64 -> data URL
(RFC 2397) and provider base64 content blocks.
```

调用方(非测试)只有两处文件:`tools/vision_tools.py`(两个调用点)与 `tools/flux3_video_tool.py`。

`tools/vision_tools.py:987`

```python
        from tools.image_source import (
            ImageResolutionError,
            ResolveContext,
            resolve_image_source,
        )

        try:
            resolved = await resolve_image_source(image_url, ResolveContext(task_id=task_id))
        except ImageResolutionError as exc:
            return tool_error(str(exc), success=False)
```

#### 2.5.1 分派顺序

`tools/image_source.py:95`

```python
async def resolve_image_source(
    src: str,
    ctx: ResolveContext,
    *,
    permitted: tuple = ("image",),
) -> ResolvedImage:
    if not isinstance(src, str) or not src.strip():
        raise SourceNotFound("image_url is required", src=str(src))
    s = src.strip()
    if s.startswith("data:"):
        data, mime = _resolve_data_url(s)
        return _finalize(data, mime, "data", s, permitted)
    if s.startswith(("http://", "https://")):
        reason = _http_block_reason(s)
        if reason:
            raise SourceUnsafe(reason, src=s)
        return _finalize(await _download_to_bytes(s), "", "http", s, permitted)

    if _SCHEME_RE.match(s) and not s.lower().startswith("file://"):
        raise UnsupportedScheme(
            "Unrecognized image source scheme. Use an http(s) URL, a local "
            "file path, a file:// URI, or a data: URL.",
            src=s,
        )
```

`data:` → `http(s)` → 其它 scheme 拒绝(`ftp://`、`s3://`、`gopher://`…)→ 剩下全按文件系统路径处理(**包括裸相对名 `pic.png`**,`tests/tools/test_image_source.py:64` 明确钉住这条不能回归)。

异常类型分了 5 种(`UnsupportedScheme` / `SourceUnsafe` / `SourceTooLarge` / `SourceNotFound` / `NotAnImage`),都带 `src` 与 `origin`,方便上游给模型精确报错。

#### 2.5.2 SSRF 面:预检 + 重入检查

`tools/image_source.py:174`

```python
def _http_block_reason(url: str) -> Optional[str]:
    """Return a human-readable block reason, or None when the URL is allowed.

    Pre-flight short-circuit: policy-blocked URLs are refused BEFORE any
    network I/O. ``_download_image`` re-checks policy internally (per attempt
    and against the final redirect target) — that second evaluation is
    intentional, not redundant: this one guarantees no bytes move for a
    blocked URL; the inner one covers redirects and non-resolver callers.
    Preserves the specific website-policy message so the agent sees *why*.
    """
```

`tools/image_source.py:187`

```python
    if not is_safe_url(url):
        return "blocked: unsafe or private URL"
    blocked = check_website_access(url)
    if blocked:
        return blocked.get("message") or "blocked by website policy"
    return None
```

`is_safe_url`(`tools/url_safety.py:415`)解析主机名到 IP、拒私网段、**fail-closed**(DNS 失败也拒),且云元数据端点(`169.254.169.254`、`metadata.google.internal`)**无视 `security.allow_private_urls` 开关永远拒**。

实际下载走 `tools.vision_tools._download_image`,注释说明它同时执行 50 MB 流上限、重定向 SSRF 防护、站点策略。下载到 `NamedTemporaryFile`,读完 `finally: tmp.unlink(missing_ok=True)`。

> **两层校验不是冗余**:外层保证"被拒的 URL 一个字节都不走",内层保证"重定向到内网也拒" + "不经解析器的调用方也受保护"。这个理由写在注释里,是很好的范本。

#### 2.5.3 路径穿越面 / 终端后端 confinement(GHSA-gpxw-6wxv-w3qq)

这是全文件的核心。模型可以给任意路径,而 vision 是**宿主侧**读文件的;但在非本地终端后端下,其它文件工具都被关在沙箱里。不处理的话,`vision_analyze('/etc/passwd')` 就是一个越狱。

`tools/image_source.py:122`

```python
    candidate = s[len("file://"):] if s.lower().startswith("file://") else s
    p = Path(os.path.expanduser(candidate))
    # Confinement decision (see module docstring). Under a non-local backend
    # a path is host-readable ONLY if it lands in a media cache (after
    # translating a container-visible cache path back to its host mount);
    # every other path is read inside the sandbox via exec-read, so a host
    # path outside the caches never yields the host's bytes.
    host_target = _permitted_host_read_target(p, ctx)
    if host_target is not None and host_target.is_file():
```

`tools/image_source.py:252`

```python
    if _is_local_terminal_backend():
        try:
            return p.resolve()
        except Exception:  # noqa: BLE001 — unresolved path: let is_file() fail downstream
            return p

    from tools.credential_files import from_agent_visible_cache_path

    host_candidate = Path(from_agent_visible_cache_path(str(p)))
    try:
        real = host_candidate.resolve()
    except Exception:  # noqa: BLE001 — cannot resolve -> not a safe host read
        return None
    for root in _media_cache_roots():
        try:
            real.relative_to(root.resolve())
            return real
        except ValueError:
            continue
    return None
```

判据链:
1. **本地后端** → 任意路径可读(明写是"chosen posture",不是疏漏);
2. **非本地后端** → 先把"容器可见的缓存路径"翻译回宿主挂载点,再 `resolve()`(**跟符号链接**),再逐个 `relative_to()` 缓存根。**先 resolve 再判前缀**是防符号链接逃逸的关键顺序;
3. 不在缓存里 → **不读宿主**,改成在沙箱里 exec-read。

符号链接逃逸的回归用例(**在缓存目录里种一个指向宿主密钥的软链**):

`tests/tools/test_image_source.py:176`

```python
    @pytest.mark.asyncio
    async def test_symlink_in_cache_pointing_outside_is_not_host_read(self, tmp_path, monkeypatch):
        """A symlink planted inside a cache dir that points at a host secret must
        not be host-read (resolve() escapes the cache) — it routes to sandbox."""
        home = tmp_path / "hermes"
        isrc = _reload(monkeypatch, home)
        monkeypatch.setenv("TERMINAL_ENV", "docker")
        secret = tmp_path / "outside" / "id_rsa"
        secret.parent.mkdir(parents=True)
        secret.write_bytes(b"HOST-PRIVATE-KEY")
        cache_dir = home / "cache" / "images"
        cache_dir.mkdir(parents=True)
        link = cache_dir / "sneaky.png"
        try:
            link.symlink_to(secret)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unsupported")
```

缓存根白名单(`tools/image_source.py:221` 的 `_media_cache_roots`):`cache/` `images/` `image_cache/` `audio_cache/` `video_cache/` `temp_vision_images/` `temp_video_files/`,全在 `$HERMES_HOME` 下。

宿主可读时还要过一次**凭据读闸门**:

`tools/image_source.py:138`

```python
        try:
            from agent.file_safety import raise_if_read_blocked
        except Exception:  # noqa: BLE001 — guard unavailable: proceed
            raise_if_read_blocked = None
        if raise_if_read_blocked is not None:
            try:
                raise_if_read_blocked(str(host_target))
            except ValueError as exc:
                raise SourceUnsafe(str(exc), src=s, origin="file")
```

注释点明:这是"有意的、具体的拒绝",而不是"靠魔术字节嗅探顺手拒掉"——`.env` 恰好不是图片所以会被 `NotAnImage` 拒,但那是**偶然**,不能当安全属性用。

沙箱 exec-read:

`tools/image_source.py:318`

```python
    qp = shlex.quote(str(p))
    res = await asyncio.to_thread(
        env.execute,
        f"head -c {_MAX_INGEST_BYTES + 1} < {qp} | base64 | tr -d '\\n'")
    if res.get("returncode", 1) != 0:
        raise SourceNotFound(f"could not read '{p}' inside the sandbox", src=src, origin="container")
    try:
        data = base64.b64decode(res.get("output", ""), validate=True)
    except Exception as exc:
        raise NotAnImage(f"sandbox returned non-image data for '{p}': {exc}", src=src)
    if len(data) > _MAX_INGEST_BYTES:
        raise SourceTooLarge("media exceeds size limit", src=src, origin="container")
    return _finalize(data, "", "container", src, permitted)
```

四个细节都有理由:
- `head -c N+1`:在**沙箱内**就把读量截断,`/dev/zero` 之类不能把无界 base64 灌进宿主内存;`+1` 用来区分"正好到上限"和"超上限";
- **输入重定向 `< path` 而不是 `base64 path`**:完全绕开 argv,前导横杠路径不会被当成选项 ——

`tests/tools/test_image_source.py:200`

```python
class TestExecReadSafety:
    @pytest.mark.asyncio
    async def test_exec_read_is_bounded_and_redirect_safe(self, tmp_path, monkeypatch):
        """Leading-dash paths go through an input redirect (no argv exposure)
        and the read is size-bounded via head -c."""
```

  (用例喂的路径是 `/workspace/-i-etc-shadow.png`,断言命令里含 `head -c <上限+1> < `。)
- `base64 | tr -d '\n'`:`base64 -w0` 是 GNU 独有,BusyBox 没有;
- `asyncio.to_thread`:`env.execute` 是阻塞的后端 exec,不能占着事件循环。

**fail-closed**:没有活跃沙箱 env 时**拒绝**而不是回落宿主读。

`tests/tools/test_image_source.py:163`

```python
    @pytest.mark.asyncio
    async def test_non_cache_path_fails_closed_without_sandbox(self, tmp_path, monkeypatch):
        """No active sandbox env -> refuse rather than fall back to a host read."""
        home = tmp_path / "hermes"
        isrc = _reload(monkeypatch, home)
        monkeypatch.setenv("TERMINAL_ENV", "docker")
        secret = tmp_path / "id_rsa"
        secret.write_bytes(b"HOST-PRIVATE-KEY")

        with patch("tools.image_source._get_active_env", return_value=None):
            with pytest.raises(isrc.SourceNotFound):
                await isrc.resolve_image_source(str(secret), isrc.ResolveContext(task_id="t1"))
```

#### 2.5.4 尺寸与类型的唯一收口 `_finalize`

`tools/image_source.py:43`

```python
# Raw-bytes INGEST budget — what the resolver will load before handing off.
# This is deliberately the 50MB download cap (tools/vision_tools._VISION_MAX_DOWNLOAD_BYTES),
# NOT the 20MB provider payload cap. The 20MB cap (_MAX_BASE64_BYTES) is a
# *post-resize* limit enforced at the call sites: an oversized raw image must
# still reach the resizer so it can be downscaled under the payload cap. Capping
# raw bytes at 20MB here would reject every 20-50MB photo before resize can run.
_MAX_INGEST_BYTES = 50 * 1024 * 1024
```

> **两个上限必须分开**这条是很容易做错的:如果把"入口上限"设成"出口上限",所有需要缩放的大图在缩放之前就被拒了。

类型判定:图片按**魔术字节**(`_detect_image_mime_type_from_bytes`),SVG 特判放行(调用点再栅格化),视频按**扩展名表 + mp4 容器嗅探**。视频用扩展名的理由写在 docstring 里:下游都会再校验一次(上传网关把 content-type 签进预签名 URL,厂商拒绝解不了的输入),所以猜错在那边是**干净的拒绝**而不是这里的洞。

`data:` URL 还有一个**解码前的尺寸闸**:

`tools/image_source.py:159`

```python
def _resolve_data_url(s: str) -> tuple[bytes, str]:
    header, _, payload = s.partition(",")
    if ";base64" not in header:
        raise NotAnImage("data: URL must be base64-encoded", src=s[:64])
    declared = header[len("data:"):].split(";", 1)[0].strip() or "application/octet-stream"
    # Cheap pre-decode size gate on the encoded length (~4/3 expansion).
    if (len(payload) * 3) // 4 > _MAX_INGEST_BYTES:
        raise SourceTooLarge("data: URL exceeds size limit", src=s[:64])
    try:
        data = base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise NotAnImage(f"invalid base64 in data: URL: {exc}", src=s[:64])
    return data, declared  # real mime verified in _finalize via magic bytes
```

`declared` 只是记录,**真 MIME 一律以魔术字节为准**;`src=s[:64]` 保证异常信息不会把整个 base64 打进日志。

---

### 2.6 `tools/fal_common.py`(163)—— FAL 的公共层

**是哪家 provider 的公共层**:FAL.ai,同时服务 `tools/image_generation_tool.py` 与 `plugins/video_gen/fal/`。

模块 docstring 里最有价值的是**为什么只搬无状态的部分**:

`tools/fal_common.py:15`

```python
Stateful pieces (cache globals, ``_managed_fal_client*`` selectors,
``_submit_fal_request``) intentionally stay on
:mod:`tools.image_generation_tool`. That module is the patch target for
existing test suites (``tests/tools/test_image_generation.py``,
``tests/tools/test_managed_media_gateways.py``) and for the
``plugins/image_gen/fal/`` plugin's ``_it`` indirection — moving the
caches here would silently defeat ``monkeypatch.setattr(image_tool,
"_managed_fal_client", None)`` because the lookups would go against
``fal_common``'s namespace instead. See the per-rule walkthrough at
issue #26241 for details.
```

> **可迁移原则**:重构提取公共层时,**模块全局变量的"归属"就是测试补丁的锚点**。把有状态的东西搬走会静默废掉 monkeypatch(不是报错,是补丁打空)。所以这里只搬了纯函数和一个自带引用的类。

#### 2.6.1 惰性 import + lazy_deps

`tools/fal_common.py:44`

```python
    try:
        from tools.lazy_deps import ensure as _lazy_ensure
        _lazy_ensure("image.fal", prompt=False)
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001 — lazy_deps surfaces install hints
        raise ImportError(str(exc))
    import fal_client  # type: ignore  # noqa: WPS433 — intentionally lazy
    return fal_client
```

两个 except 分工不同:`ImportError` = `lazy_deps` 自己不在(老装法),放过继续裸 import;**其它异常** = `lazy_deps` 明确说"这个 feature 装不了",转成 `ImportError` 并**带上它的安装提示文本**。这正是本轮 3 个测试失败看到的那句(§4)。

#### 2.6.2 凭据怎么传

**直连**:`FAL_KEY` 环境变量(或 `~/.hermes/.env`),由 `fal_client` SDK 自己读。本模块不碰。

**托管网关**:`_ManagedFalSyncClient(fal_client, key=<nous_user_token>, queue_run_origin=<gateway_origin>)`。

`tools/fal_common.py:90`

```python
    def __init__(self, fal_client: Any, *, key: str, queue_run_origin: str):
        sync_client_class = getattr(fal_client, "SyncClient", None)
        if sync_client_class is None:
            raise RuntimeError("fal_client.SyncClient is required for managed FAL gateway mode")

        client_module = getattr(fal_client, "client", None)
        if client_module is None:
            raise RuntimeError("fal_client.client is required for managed FAL gateway mode")

        self._queue_url_format = _normalize_fal_queue_url_format(queue_run_origin)
        self._sync_client = sync_client_class(key=key)
        self._http_client = getattr(self._sync_client, "_client", None)
        self._maybe_retry_request = getattr(client_module, "_maybe_retry_request", None)
        self._raise_for_status = getattr(client_module, "_raise_for_status", None)
        self._request_handle_class = getattr(client_module, "SyncRequestHandle", None)
        self._add_hint_header = getattr(client_module, "add_hint_header", None)
        self._add_priority_header = getattr(client_module, "add_priority_header", None)
        self._add_timeout_header = getattr(client_module, "add_timeout_header", None)
```

即:**Nous 用户令牌被当成 FAL key 传给 SDK 的 `SyncClient`**,由网关那边换成真 FAL 凭据。所有请求打到 `<gateway_origin>/<application>`:

`tools/fal_common.py:128`

```python
        url = self._queue_url_format + application
        if path:
            url += "/" + path.lstrip("/")
        if webhook_url is not None:
            url += "?" + urlencode({"fal_webhook": webhook_url})
```

`tools/fal_common.py:55`

```python
def _normalize_fal_queue_url_format(queue_run_origin: str) -> str:
    normalized_origin = str(queue_run_origin or "").strip().rstrip("/")
    if not normalized_origin:
        raise ValueError("Managed FAL queue origin is required")
    return f"{normalized_origin}/"
```

提交与句柄:

`tools/fal_common.py:146`

```python
        response = self._maybe_retry_request(
            self._http_client,
            "POST",
            url,
            json=arguments,
            timeout=getattr(self._sync_client, "default_timeout", 120.0),
            headers=request_headers,
        )
        self._raise_for_status(response)

        data = response.json()
        return self._request_handle_class(
            request_id=data["request_id"],
            response_url=data["response_url"],
            status_url=data["status_url"],
            cancel_url=data["cancel_url"],
            client=self._http_client,
        )
```

**这里就是本簇唯一的重试点**:`_maybe_retry_request` 是 `fal_client.client` 的私有函数,通过 `getattr` 借用。这是**刻意寄生 SDK 内部 API**——七个 `getattr(client_module, ...)` 里有三个是必需的(缺就 `RuntimeError`),四个是可选的(hint/priority/timeout header)。

> **取舍**:寄生私有 API 换来"托管模式与直连模式共用一套重试/错误语义",代价是 SDK 升级可能一夜之间打断。作者用**构造期显式断言 + 清晰的 RuntimeError 文案**把这个风险从"运行时诡异行为"降成"启动即报错",并把版本钉死:

`pyproject.toml:166`

```toml
# Image generation backends
fal = ["fal-client==0.13.1"]
```

`_extract_http_status` 兼容两种异常形态(`.response.status_code` 与 `.status_code`):

`tests/tools/test_image_generation.py:279`

```python
class TestExtractHttpStatus:
    """Status-code extraction should work across exception shapes."""

    def test_extracts_from_response_attr(self, image_tool):
        exc = _MockHttpxError(403)
        assert image_tool._extract_http_status(exc) == 403
```

托管客户端在 `image_generation_tool` 侧按 `(origin, token)` 缓存并加锁复用,理由写在 docstring:`"Reuse the managed FAL client so its internal httpx.Client is not leaked per call."`

---

### 2.7 `plugins/image_gen/fal/`(211)—— 一个只做注册的适配器(理解本簇必读)

它不是第二份实现,而是**注册适配器**,一切经 `import tools.image_generation_tool as _it` 的**调用期间接**取值:

`plugins/image_gen/fal/__init__.py:100`

```python
    def capabilities(self) -> Dict[str, Any]:
        # Whether image-to-image is available depends on the currently-
        # selected FAL model (each model entry declares an edit_endpoint or
        # not). Report the active model's actual surface so the dynamic tool
        # schema is accurate.
        import tools.image_generation_tool as _it

        try:
            _model_id, meta = _it._resolve_fal_model()
        except Exception:  # noqa: BLE001
            return {"modalities": ["text"], "max_reference_images": 0}
        if meta.get("edit_endpoint"):
            return {
                "modalities": ["text", "image"],
                "max_reference_images": int(meta.get("max_reference_images") or 1),
            }
        return {"modalities": ["text"], "max_reference_images": 0}
```

**函数体内 import 而不是模块顶部 import**,就是为了让测试对 `image_tool.*` 的 monkeypatch 生效。

对照:非 FAL 的 6 个插件都**自己读本地文件**并转 data URL / 上传。例如 OpenAI 插件:

`plugins/image_gen/openai/__init__.py:150`

```python
    # Local file path — enforce the shared credential-read guard before reading.
    from agent.file_safety import raise_if_read_blocked

    raise_if_read_blocked(ref)
    with open(ref, "rb") as fh:
        data = fh.read()
    name = os.path.basename(ref) or "image.png"
    return data, name
```

这正是 §5 ■-1 的对照组。

---

## 3. 配置项与环境变量

### 3.1 config.yaml 键

**关键事实:`image_gen` 根键不在 `DEFAULT_CONFIG` 里。**

`hermes_cli/config.py:1854`

```python
_EXTRA_KNOWN_ROOT_KEYS = {
    "custom_providers",  # legacy list form; modern equivalent is providers: {}
    "fallback_model",    # optional single dict or chain list; omitted when disabled
    "mcp_servers",       # MCP server definitions written by setup/tools flows
    # Roots read from the raw user YAML (or written by our own flows) that are
    # intentionally absent from DEFAULT_CONFIG:
    "image_gen",         # image-generation provider config (agent/image_gen_registry.py)
```

→ **没有集中的默认值定义,每个读取点自带默认**。这是重实现时最容易踩的坑:想知道 `image_gen.*` 有哪些键,只能去 grep 读取点。

| 键 | 默认值 | 定义/读取处 | 作用 |
|---|---|---|---|
| `image_gen.provider` | 无(未设 = 走内置 FAL) | `agent/image_gen_registry.py:99` 的 `raw = section.get("provider")`;`tools/image_generation_tool.py:1254` 的 `value = section.get("provider")` | 选哪个插件后端 |
| `image_gen.model` | 无(→ `FAL_IMAGE_MODEL` → `DEFAULT_MODEL`) | `tools/image_generation_tool.py:541` 的 `img_cfg.get("model")` | 选模型;也传给插件 `generate(model=…)` |
| `image_gen.use_gateway` | `False` | `tools/tool_backend_helpers.py:287` 的 `return is_truthy_value(section.get("use_gateway"), default=False)` | 强制走 Nous 托管网关 |
| `image_gen.max_parallel_requests` | `4`,钳到 `[1, 8]` | `agent/tool_executor.py:215` 的 `image_gen.get("max_parallel_requests")` | 一批工具调用里 image 的并发上限 |
| `agent.image_input_mode` | `"auto"` | `hermes_cli/config_defaults.py:240` | 入站图 native / text / auto |
| `model.supports_vision` | 无 | `agent/image_routing.py:212` 的 `top = _coerce_capability_bool(model_cfg.get("supports_vision"))` | 顶层 vision 能力覆盖 |
| `providers.<p>.models.<m>.supports_vision` / `.vision` | 无 | `agent/image_routing.py:241` 的 `coerced = _coerce_capability_bool(` | 按 provider+model 覆盖 |
| `custom_providers[].models.<m>.supports_vision` / `.vision` | 无 | `agent/image_routing.py:250` 的 `custom_providers = cfg.get("custom_providers")` | 遗留 list 形式同上 |
| `auxiliary.vision.{provider,model,base_url}` | `""`/`auto` | `agent/image_routing.py:377` 的 `provider = str(vision.get("provider") or "").strip().lower()` | 是否有显式辅助 vision 后端 |
| `security.allow_lazy_installs` | `True` | `hermes_cli/config_defaults.py:2158` | 关掉后 `fal-client` 不会被按需安装 |
| `security.allow_private_urls` | — | `tools/url_safety.py:421` 的 docstring | 影响 `image_source` 的 http 预检 |

`hermes_cli/config_defaults.py:235`

```python
        #   "text"   — always pre-analyze with vision_analyze and prepend the
        #              description as text; the main model never sees pixels.
        # Affects gateway platforms, the TUI, and CLI /attach.  vision_analyze
        # remains available as a tool regardless of this setting — the routing
        # only controls how inbound user images are presented.
        "image_input_mode": "auto",
```

### 3.2 环境变量

| 变量 | 默认 | 读取处 | 作用 |
|---|---|---|---|
| `FAL_KEY` | 未设 | `tools/tool_backend_helpers.py:301` 的 `value = _scoped_credential("FAL_KEY") or None` | FAL 直连凭据;空白串算未设 |
| `FAL_IMAGE_MODEL` | `""` | `tools/image_generation_tool.py:550` 的 `model_id = os.getenv("FAL_IMAGE_MODEL", "").strip()` | 模型逃生阀(优先级低于 config) |
| `IMAGE_TOOLS_DEBUG` | `"false"` | `tools/image_generation_tool.py:443` 的 `_debug = DebugSession("image_tools", env_var="IMAGE_TOOLS_DEBUG")` | 逐调用 JSON 调试日志 |
| `KREA_API_KEY` | 未设 | `hermes_cli/config_defaults.py:3708` | Krea 后端凭据 |
| `TERMINAL_ENV` | `"local"` | `tools/image_source.py:218` 的 `return os.getenv("TERMINAL_ENV", "local").strip().lower() in ("local", "")`;`tools/image_generation_tool.py:771` | 决定 confinement 姿势与缓存路径翻译 |
| `HERMES_HOME` | 平台默认(`~/.hermes`) | `hermes_constants.py:114` 的 `def get_hermes_home() -> Path:` | 缓存/日志根 |
| `HERMES_DISABLE_LAZY_INSTALLS` | 未设(测试里设 `"1"`) | `tests/conftest.py:484` | 测试禁止按需 pip |

`DebugSession` 的日志落点:

`tools/debug_helpers.py:43`

```python
    def __init__(self, tool_name: str, *, env_var: str) -> None:
        self.tool_name = tool_name
        self.enabled = os.getenv(env_var, "false").lower() == "true"
        self.session_id = str(uuid.uuid4()) if self.enabled else ""
        self.log_dir = get_hermes_home() / "logs"
```

→ 是 `$HERMES_HOME/logs/`,不是文档说的 `./logs/`(见 §5 ▲-4)。

---

## 4. 测试作为行为规格

### 4.1 环境

```verify
ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l
/home/user/hermes-venv/bin/pip list | tail -n +3 | wc -l
```

实测 **89 个包**(两种数法一致),**不是** CLAUDE.md 记的 R8B 的 87。差额已按"直接断言、不要间接推断"查到具体是哪两个:

```verify
ls -dlt --time-style=+%Y-%m-%dT%H:%M /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | head -4
```

```console
drwxr-xr-x 3 root root 4096 2026-08-09T04:51 .../anthropic-0.87.0.dist-info
drwxr-xr-x 3 root root 4096 2026-08-09T04:51 .../docstring_parser-0.18.0.dist-info
drwxr-xr-x 3 root root 4096 2026-08-09T04:27 .../aiohttp-3.14.1.dist-info
drwxr-xr-x 3 root root 4096 2026-08-09T04:27 .../aiosignal-1.4.0.dist-info
```

即 `anthropic 0.87.0` + `docstring_parser 0.18.0` 于 **04:51** 落盘,晚于 04:27 那批(`aiohttp` / `brotlicffi`,CLAUDE.md 记载的 87 包基线)。**本子代理全程没有执行过任何 pip 安装**;这两个包是本轮同批其它会话装进这个共享 venv 的。记在这里是因为 CLAUDE.md 立过规矩:用例数是环境的函数,下一轮拿到不同的数才好判断是代码变了还是环境变了。

`fal-client` **仍然不在**(见 §4.3):

```verify
ls -d /home/user/hermes-venv/lib/python*/site-packages/fal* 2>&1 | head -3
```

```console
ls: cannot access '/home/user/hermes-venv/lib/python*/site-packages/fal*': No such file or directory
```

### 4.2 跑了什么、结果

```verify
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
  tests/tools/test_image_generation.py tests/tools/test_image_generation_image_to_image.py \
  tests/tools/test_image_generation_plugin_dispatch.py tests/tools/test_image_generation_artifacts.py \
  tests/tools/test_image_generation_env.py tests/tools/test_image_source.py \
  tests/agent/test_image_routing.py tests/agent/test_image_gen_registry.py
```

```text
=== Summary: 8 files, 105 tests passed, 2 failed (100% complete) in 2.2s (8 workers) ===
FAILED tests/tools/test_image_generation.py::TestManagedGatewayErrorTranslation::test_4xx_translates_to_value_error_with_remediation
FAILED tests/tools/test_image_generation.py::TestManagedGatewayErrorTranslation::test_non_http_exception_from_managed_bubbles_up
```

```verify
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
  tests/plugins/image_gen/ tests/tools/test_managed_media_gateways.py \
  tests/gateway/test_image_input_routing_runtime.py tests/agent/test_custom_providers_vision.py
```

```text
=== Summary: 10 files, 139 tests passed, 1 failed (100% complete) in 3.1s (8 workers) ===
FAILED tests/tools/test_managed_media_gateways.py::test_managed_fal_submit_uses_gateway_origin_and_nous_token
```

合计 **18 个文件、244 通过、3 失败**。

### 4.3 三条失败的逐条诊断:同一个根因,**非代码缺陷**

三条都在 `_submit_fal_request` 的第一行炸,报文完全一样:

```console
tools/fal_common.py:50: ImportError
E  ImportError: Feature 'image.fal' unavailable: lazy installs disabled (security.allow_lazy_installs=false). To enable manually: uv pip install 'fal-client==0.13.1'  (or: pip install 'fal-client==0.13.1').
```

因果链(三步都已核实):

1. `fal-client` **不在 `[dev]` extra 里**,而在专门的 `fal` extra 里 ——
   `pyproject.toml:167`:`fal = ["fal-client==0.13.1"]`;实测 venv 里 `site-packages/fal*` 不存在。
2. 测试 conftest **主动关掉了按需安装**,防止单测跑起真 pip ——
   `tests/conftest.py:484`:`monkeypatch.setenv("HERMES_DISABLE_LAZY_INSTALLS", "1")`。
3. `_submit_fal_request` **无条件先调 `_load_fal_client()`**(`tools/image_generation_tool.py:487`),即使这三条用例已经把 `_get_managed_fal_client` 打了桩、其实用不到真 SDK。

结论:**缺可选依赖 `fal-client`**,与 CLAUDE.md 里记载的 `aiohttp` 情形同类。装上 `[fal]` extra 即可转绿——但本轮**按共享资源纪律未安装**,故留为已诊断的已知失败。

`tests/conftest.py:476`

```python
    # Lazy feature deps (tools/lazy_deps.py) pip-install on demand by design —
    # _allow_lazy_installs() fails open for users. Unit tests must never reach
    # pip/the network: with the SDK absent, any agent init whose tool checks
    # touch a lazy feature (e.g. check_tts_requirements →
    # ensure("tts.elevenlabs")) spawns a real pip install — which hangs to the
    # suite timeout under tests that set fake proxy env vars. The kill-switch
    # makes ensure() raise FeatureUnavailable immediately instead.
    # tests/tools/test_lazy_deps.py overrides this var in both directions.
    monkeypatch.setenv("HERMES_DISABLE_LAZY_INSTALLS", "1")
```

### 4.4 测试断言了哪些不变量(作者认为什么是对的)

| 不变量 | 锚点 |
|---|---|
| 默认模型必须是 Klein 9B | `tests/tools/test_image_generation.py:36` 的 `def test_default_model_is_klein` |
| 每个目录条目必须有 9 个必填键 | `tests/tools/test_image_generation.py:40` 的 `def test_all_entries_have_required_keys` |
| **只有** flux-2-pro 开升采样 | `tests/tools/test_image_generation.py:50` 的 `def test_only_flux2_pro_upscales_by_default` |
| 任何模型的 payload 键必须是其 `supports` 的子集 | `tests/tools/test_image_generation.py:147` 的 `def test_payload_keys_are_subset_of_supports_for_all_models` |
| nano-banana **绝不能**同时拿到 `image_size` | `tests/tools/test_image_generation.py:155` 的 `def test_nano_banana_never_gets_image_size` |
| gpt-image-2 的 BYOK key / guidance_scale / seed 一律剥掉 | `tests/tools/test_image_generation.py:118` 的 `def test_gpt2_strips_byok_and_unsupported_overrides` |
| GPT 质量钉死 medium,运行时查找函数**必须不存在** | `tests/tools/test_image_generation.py:197` 的 `def test_resolve_gpt_quality_function_is_gone` |
| agent 可见参数**恰好**这 4 个,required 只有 prompt | `tests/tools/test_image_generation.py:247` 的 `def test_schema_exposes_expected_agent_params` |
| 白名单写漏也不能丢 prompt / image_urls | `tests/tools/test_image_generation_image_to_image.py:77` 的 `def test_edit_keeps_prompt_and_image_urls` |
| 编辑跳过升采样 | `tests/tools/test_image_generation_image_to_image.py:135` 的 `def test_edit_skips_upscaler` |
| 老签名插件收到编辑请求 → `modality_unsupported` | `tests/tools/test_image_generation_image_to_image.py:223` 的 `def test_legacy_provider_edit_request_surfaces_clear_error` |
| 非缓存宿主路径在沙箱下必须读容器的文件 | `tests/tools/test_image_source.py:132` 的 `async def test_host_secret_outside_cache_routes_to_sandbox_not_host` |
| 缓存目录里的符号链接指向外部 → 不宿主读 | `tests/tools/test_image_source.py:177` 的 `async def test_symlink_in_cache_pointing_outside_is_not_host_read` |
| 无沙箱 env 时 fail-closed | `tests/tools/test_image_source.py:164` 的 `async def test_non_cache_path_fails_closed_without_sandbox` |
| 裸相对文件名必须仍然可解析 | `tests/tools/test_image_source.py:65` 的 `async def test_bare_relative_path_resolves` |
| BMP 必须被转码成 PNG | `tests/agent/test_image_routing.py:395` 的 `def test_bmp_transcoded_to_png` |
| PNG **不得**被重编码(保字节) | `tests/agent/test_image_routing.py:411` 的 `def test_png_passes_through_no_transcode` |
| `.env` 命名的图片不得被附上 | `tests/agent/test_image_routing.py:423` 的 `def test_file_to_data_url_blocks_read_denied_image_path` |
| 显式 aux vision 不得抢占 vision-capable 主模型的 native | `tests/agent/test_image_routing.py:66` 的 `def test_auto_prefers_native_for_vision_capable_main_model_even_with_aux_configured` |
| 配置未注册的 provider → `get_active_provider()` 回落 | `tests/agent/test_image_gen_registry.py:67` 的 `image_gen_registry.register_provider(_FakeProvider("fal"))` |

---

## 5. 定案

### ▲-1 文档把 FAL 的参考图上限说成 9,代码里 gpt-image 两款是 16

判定范围:整行表格行,归 `## Image-to-Image / Editing` → `### Which backends support editing` 管。

`website/docs/user-guide/features/image-generation.md:118`

> | **FAL.ai** (edit-capable models below) | ✓ | up to 9 | routes to the model's `/edit` endpoint |

代码:

`tools/image_generation_tool.py:252`

```python
        "max_reference_images": 16,
```

`tools/image_generation_tool.py:293`

```python
        "max_reference_images": 16,
```

(分别属于 `fal-ai/gpt-image-1.5` 与 `fal-ai/gpt-image-2` 两个条目。)

FAL 各模型实际上限:9 / 9 / 2 / **16** / **16** / 1 / 3。文档"up to 9"是一个**上界断言**,被 16 直接证伪。而且这个数会通过动态 schema 直接告诉模型(`tools/image_generation_tool.py:1634` 的 `f"; up to {max_refs} reference image(s) via reference_image_urls"`),所以文档与模型看到的提示不一致。
**不是 ◎**:"up to 9" 字面为假,不是保守为真。

### ▲-2 文档说 "Hermes materializes them to the local cache",但默认的 FAL 路不落盘

判定范围:整条 bullet,归 `## Limitations` 管。

`website/docs/user-guide/features/image-generation.md:215`

> - **Temporary URLs** — backends return hosted URLs that expire after hours/days; Hermes materializes them to the local cache so delivery still works after expiry

代码:内置 FAL 路把 FAL 返回的 URL **原样**放进 `image` 字段。

`tools/image_generation_tool.py:1006`

```python
        response_data = {
            "success": True,
            "image": formatted_images[0]["url"] if formatted_images else None,
            "modality": modality,
        }
```

搜索面(三个文件全文,模式覆盖 base64 / data URL / 上传 / 文件读写):

```verify
cd /home/user/hermes-agent && grep -nE "base64|b64|data:|upload|read_bytes|open\(|Path\(" tools/image_generation_tool.py tools/fal_common.py plugins/image_gen/fal/__init__.py
```

实测只有 2 处命中,都与落盘无关:`tools/image_generation_tool.py:727`(`_looks_like_absolute_file_path` 的 scheme 判断,只作用于**输出**)与 `:769`(SSH 环境同步的注释)。

对照组:其余 6 个插件全部调用 `save_url_image` / `save_b64_image` 落到 `$HERMES_HOME/cache/images/`:

```verify
cd /home/user/hermes-agent && grep -rn "save_url_image\|save_b64_image" --include=*.py plugins/image_gen/
```

**因此该 bullet 对文档自己的主角(FAL,且是默认后端)不成立。** 另外注意:`gateway/platforms/weixin.py:2125` 的 `async def _download_remote_media(self, url: str) -> str:` 确实会下载远端 URL,但那是**企业微信必须先上传媒体**的平台特例,落的是 `NamedTemporaryFile`,不是"local cache",不能支撑这条通用断言。

### ▲-3 文档说交付靠 `MEDIA:<url>` 标签,但 MEDIA 匹配器不接受 URL

判定范围:整条第 5 步,归 `## How It Works Internally` 管。

`website/docs/user-guide/features/image-generation.md:188`

> 5. **Delivery** — final image URL returned to the agent, which emits a `MEDIA:<url>` tag that platform adapters convert to native media.

代码三点:

(a) 工具描述**从没提过 MEDIA**,它让模型按平台约定去引用:

`tools/image_generation_tool.py:1170`

```python
        "Returns the result in the `image` field — either a URL or an absolute "
        "file path. To show it to the user, reference that path/URL in your "
        "response using the file-delivery convention for the current platform "
        "(your platform guidance describes how files are delivered here). When "
        "the active terminal backend has a different filesystem, successful "
        "local-file results may also include `agent_visible_image` for "
        "follow-up terminal/file operations."
```

(b) 网关自动附件对 `image_generate` 走的是 **JSON 路径字段**分支,而不是扫 `MEDIA:` 文本 —— 见 §1.4 的 `gateway/run.py:1628` 块;

(c) `_TOOL_MEDIA_RE`(§1.4)与共享的 `MEDIA_TAG_CLEANUP_RE` 的路径类都只接受 `~/` / `/` / `X:/` 起头:

`gateway/platforms/base.py:1702`

```python
MEDIA_TAG_CLEANUP_RE = re.compile(
    r'''[`"'*_]{0,3}MEDIA:\s*'''
    r'''(?P<path>`[^`\n]+?`|"[^"\n]+?"|'[^'\n]+?'|'''
    r'''(?:~/|/|[A-Za-z]:[/\\])\S+?(?:[^\S\n]+\S+?)*?\.(?:''' + _MEDIA_EXT_ALTERNATION + r'''))'''
    r'''(?=[\s`"'*_,;:)\]}\[]|MEDIA:|\.(?:\s|$)|$)[`"'*_]{0,3}\.?''',
    re.IGNORECASE,
)
```

裸 `MEDIA:https://…` 匹配不上(`h` 之后不是 `:`)。所以"emits a `MEDIA:<url>` tag"这个机制描述与代码不符。

### ▲-4 文档说调试日志在 `./logs/`,代码写 `$HERMES_HOME/logs/`

判定范围:整句,归 `## Debugging` 管。

`website/docs/user-guide/features/image-generation.md:198`

> Debug logs go to `./logs/image_tools_debug_<session_id>.json` with per-call details (model, parameters, timing, errors).

代码见 §3.2 的 `tools/debug_helpers.py:43` 块:`self.log_dir = get_hermes_home() / "logs"`。文件名部分文档是对的(`image_tools_debug_<uuid>.json`),**只有目录错**:`get_hermes_home()` 默认是 `~/.hermes`(Windows 为 `%LOCALAPPDATA%\hermes`),与进程 CWD 无关。

### ◇-1 `image_gen.provider` 这个键在整篇图像生成文档里没有出现

配置样例只给了 `model` / `use_gateway` / `max_parallel_requests`:

`website/docs/user-guide/features/image-generation.md:63`

> ```yaml
> image_gen:
>   model: fal-ai/flux-2/klein/9b
>   use_gateway: false            # true if using Nous Subscription
>   max_parallel_requests: 4      # concurrent images in one tool-call batch
> ```

但真正决定"哪个后端服务这次调用"的是 `image_gen.provider`(§1.2 三级分派、§2.2.3 注册表解析)。文档只在散文里说"pick your backend",没有给出这个键名,用户无法手改 config.yaml 切后端。

### ◇-2 编辑请求跳过升采样,文档的升采样表没有提

`website/docs/user-guide/features/image-generation.md:165`

> | Model | Upscale? | Why |
> |---|---|---|
> | `fal-ai/flux-2-pro` | ✓ | Backward-compat (was the pre-picker default) |
> | All others | ✗ | Fast models would lose their sub-second value prop; hi-res models don't need it |

代码里还有第二个门(见 §2.4.6 的 `tools/image_generation_tool.py:974`):`and not use_edit`。所以对 flux-2-pro **做编辑时也不升采样**,表里没有这一维。

### ◇-3 `krea/v2` 两款用 `aspect_ratio` 族,文档的尺寸表只把该列标给 nano-banana-pro

`website/docs/user-guide/features/image-generation.md:151`

> | Agent input | image_size (flux/z-image/qwen/recraft/ideogram) | aspect_ratio (nano-banana-pro) | image_size (gpt-image-1.5) | image_size (gpt-image-2) |

代码里 `fal-ai/krea/v2/medium/text-to-image` 与 `fal-ai/krea/v2/large/text-to-image` 的 `size_style` 都是 `"aspect_ratio"`:

`tools/image_generation_tool.py:385`

```python
        "size_style": "aspect_ratio",
        "sizes": {
            "landscape": "16:9",
            "square": "1:1",
            "portrait": "9:16",
        },
```

列头把该族只归给 nano-banana-pro,漏了这两款。

### ■-1 `image_generate` 的 schema 承诺可传本地绝对路径,但内置 FAL 路把它原样当 URL 发出去

Schema 对模型的承诺:

`tools/image_generation_tool.py:1195`

```python
            "image_url": {
                "type": "string",
                "description": (
                    "Optional source image to edit/transform (image-to-image). "
                    "When provided, the active backend routes to its image "
                    "editing endpoint; when omitted, it generates from text "
                    "alone. Pass a public URL or an absolute local file path "
                    "from the conversation. Only honored by models that "
                    "support editing — the description above indicates whether "
                    "the active model does."
                ),
```

实际处理:

`tools/image_generation_tool.py:640`

```python
    payload: Dict[str, Any] = dict(meta.get("defaults", {}))
    payload["prompt"] = (prompt or "").strip()
    payload["image_urls"] = list(image_urls)
```

`list(image_urls)` 之后不再有任何转换,直接进 `_submit_fal_request` 的 body。可复现验证(只读地 import 基线模块):

```verify
cd /home/user/hermes-agent && HERMES_HOME=/tmp/r9b-fakehome /home/user/hermes-venv/bin/python -c "
from tools.image_generation_tool import _build_fal_edit_payload
p = _build_fal_edit_payload('fal-ai/nano-banana-pro', 'make it night', ['/home/user/.hermes/cache/images/x.png'], 'landscape')
print(repr(p['image_urls']))
"
```

实测输出:

```text
['/home/user/.hermes/cache/images/x.png']
```

负结论的搜索面 = §5 ▲-2 里那条 grep(`tools/image_generation_tool.py` + `tools/fal_common.py` + `plugins/image_gen/fal/__init__.py` 全文,模式 `base64|b64|data:|upload|read_bytes|open\(|Path\(`),**零处本地读文件**。

**影响面**:内置 FAL 路是**默认后端**(`image_gen.provider` 未设时、或设为 `"fal"` 时都走它),且 `image_url` 的**最常见来源正是本地路径**——`agent/image_routing.py` 的 native 附件提示 `[Image attached at: <path>]` 给模型的就是本地绝对路径。模型照 schema 说的做,FAL 端会拒(路径不是 URL)。

**对照**:非 FAL 的插件都实现了本地读取(见 §2.7 的 `plugins/image_gen/openai/__init__.py:150` 块),说明这是 FAL 路**单独**缺的一环,而不是全局的设计取舍。

**性质**:功能缺陷,不是安全缺陷 —— 因为它根本没读文件,所以也不存在凭据泄漏(相应地,`raise_if_read_blocked` 在这条路上也无从执行;它的 docstring 却把 image-gen 的 `image_url` / `reference_image_urls` 列为自己的服务对象):

`agent/file_safety.py:344`

```python
    Shared chokepoint for provider input-loading sites that read a local
    file the model/tool supplied (e.g. image-gen ``image_url`` /
    ``reference_image_urls`` paths). Centralizes the guard so every provider
    enforces the same read boundary with identical semantics instead of each
    open-coding the try/except block (#57698).
```

**未验证部分(明确标注)**:我没有真的向 FAL 发过请求(无凭据),所以"FAL 会拒绝一个文件系统路径"是**推定**,依据是该字段名为 `image_urls`、文档描述为 URL 列表。已验证的只有"本地路径原样进入 payload"这一半。

---

## 6. 移交项

### 移交-1:`decide_image_input_mode` 的 `auto` 尾部两条分支返回同一个值

锚点:`agent/image_routing.py:504` 的 `if _explicit_aux_vision_override(cfg):`
现象:`auto` 分支最后 `if _explicit_aux_vision_override(cfg): return "text"` 与其后的 `return "text"` 返回值完全相同,该 if 对结果无影响;`_explicit_aux_vision_override` 的其余调用方需要单独确认(本轮只核到 `tools/computer_use/vision_routing.py:59` 有一个"镜像实现"的注释)。**结果正确,不是 bug**,但重实现时会误以为这里有两种结果。

### 移交-2:`max_reference_images` 实际截的是"主图+参考图"的总数

锚点:`tools/image_generation_tool.py:939` 的 `clamped_sources = source_images[:max_refs] if max_refs > 0 else source_images`
现象:`source_images` 由 `image_url` 与 `reference_image_urls` 顺序合并而成,截断作用在合并后的列表上;因此对 `ideogram/v3`(cap=1)传一张主图 + 一张参考图时,**参考图会被静默丢弃**(而不是"1 张参考图"被保留)。命名与语义不一致,是否为有意行为待后续轮确认。

### 移交-3:`_dispatch_to_plugin_provider` 的 TypeError 注释声称会重试,代码不会

锚点:`tools/image_generation_tool.py:1340` 的 `# (third-party plugin not yet updated) — retry without the new kwargs`
现象:注释说"retry without the new kwargs so text-to-image keeps working",但该分支直接 `return json.dumps({... "error_type": "modality_unsupported"})`,没有任何重试;`tests/tools/test_image_generation_image_to_image.py:223` 断言的也是返回错误。注释过期,可能误导重实现者。

### 移交-4:`FAL_IMAGE_MODEL` 的"undocumented"注释与 website/docs 冲突

锚点:`tools/image_generation_tool.py:548` 的 `# Env var escape hatch (undocumented; backward-compat for tests/scripts).`
现象:同一个变量在 `website/docs/user-guide/features/image-generation.md:184` 被明确写进"How It Works Internally"的解析顺序里。**文档为真、注释为假**,故不计 ▲,但这是"逃生阀被文档化后没人回来改注释"的典型形状,后续轮若做"注释-文档一致性"扫描可作样本。

### 移交-5:`image_gen.model` 在切换 provider 后可能仍是上一家的模型 id

锚点:`tools/image_generation_tool.py:1326` 的 `kwargs["model"] = configured_model`
现象:`_dispatch_to_plugin_provider` 无条件把 `image_gen.model` 透传给插件的 `generate(model=…)`;若用户先选了 FAL 的 `fal-ai/flux-2/klein/9b`,再把 `image_gen.provider` 改成 `openai`,插件会收到一个 FAL 的模型 id。`hermes_cli/tools_config.py:3876` 的 `_select_plugin_image_gen_provider` 是否同时清/改 `model` **本轮未核**,标为待验证。

### 移交-6:3 条测试失败需 `[fal]` extra 才能转绿

锚点:`tools/fal_common.py:46` 的 `_lazy_ensure("image.fal", prompt=False)`
现象:见 §4.3。若后续轮要把这 3 条纳入绿线,需要 `pip install 'fal-client==0.13.1'` 进共享 venv —— 那会把 venv 包数从 87 变成 88+,**必须在报告里同时更新环境读数**(CLAUDE.md 的"用例数是环境的函数"那条)。本轮按纪律未装。

---

## 7. 可迁移的设计原则(给自己造 harness 时抄的清单)

1. **一个工具覆盖两种模态,路由判据是入参在不在**(`image_url` 有无),而不是两个工具。模型少学一个名字,后端换了也不用改 schema。
2. **能力声明必须是运行时的**:`capabilities()` + `dynamic_schema_overrides` 把"当前这个模型支不支持编辑"写进工具描述,省掉一次注定失败的调用。默认值取**最保守**的那个(text-only),让老实现沉默降级而不是沉默升级。
3. **白名单过滤 + 必留键旁路**:两个方向相反的失败模式(发了不该发的 / 漏了必须发的)都要防,而且必留键要有测试专门注入"写漏的白名单"。
4. **显式配置 vs 自动回退,用不同的可用性语义**:用户明说要谁就返回谁(哪怕不可用,好报精确的错);没明说时才按可用性过滤(别把人推上付费后端)。
5. **不要为易腐的外部限制建表**:尺寸上限用"先试满,被拒了再缩"的反应式路径,注释里把这个取舍写清楚。
6. **两个尺寸上限要分开**:入口 ingest 上限(宽)和出口 payload 上限(紧),把它们设成一个值会让所有需要缩放的输入在缩放前就被拒。
7. **"下载图片"按 URL 的来源分两套姿势**:provider 返回的 URL 可信(直接 requests + 大小上限);模型给的 URL 不可信(SSRF 预检 + 重定向重检 + 站点策略)。
8. **沙箱 confinement 的判据要写成"宿主可读白名单 + 其余走沙箱内读"**,而不是"黑名单拒敏感路径";`resolve()` 必须在 `relative_to()` 之前,否则符号链接直接逃逸;没有沙箱时 **fail-closed**。
9. **在沙箱里读文件要用输入重定向而不是 argv**,并在沙箱内就用 `head -c N+1` 截断。
10. **错误信息三要素**:出了什么事 + 为什么 + 两条可执行的下一步;并给 `error_type` 分类,让模型能据此改路而不是重试同一条。
11. **提取公共层时,模块全局变量的归属就是测试补丁的锚点**:只搬无状态的部分,有状态的留在原地,并把这个理由写进新模块的 docstring。
12. **寄生 SDK 私有 API 时,在构造期显式断言并给出清晰的 RuntimeError**,把风险从"运行时诡异"降到"启动即报错",并钉死依赖版本。
13. **成本决策写死在目录里并用测试钉住**(质量档、分辨率档、prompt 扩写开关),比开放给用户配置更适合"多人共用一个计费出口"的场景 —— 但要把理由写进注释,否则下一个人会以为是漏了功能。

---

## 8. 延伸

- 出图侧的**插件实现**(本轮只精读了 `fal`,另 6 个只做了对照抽样):`plugins/image_gen/{deepinfra,krea,openai,openai-codex,openrouter,xai}/__init__.py`,合计 3369 行。
- **视频孪生**:`agent/video_gen_provider.py` / `agent/video_gen_registry.py` / `tools/video_generation_tool.py`,`image_gen_registry.py` 的 docstring 明说 video 是照着它写的(`agent/video_gen_registry.py:18` 的 `Mirrors ``agent/image_gen_registry.py`` so the two surfaces behave the`)。
- **入图侧的另一半**:`tools/vision_tools.py`(`image_source` 的主消费者)、`run_agent._try_shrink_image_parts_in_messages`(反应式缩图)。
- **选择器 UI**:`hermes_cli/tools_config.py` 的 `_plugin_image_gen_providers` / `_plugin_image_gen_catalog` / `_select_plugin_image_gen_provider`。
