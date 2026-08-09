# R9B 底稿 · 视频生成簇

> 底稿定位:求全求证,面向"要凭它重实现同等机制"的自己。允许啰嗦、允许罗列。
> 溯源约定:所有 `路径:行号` 均相对基线仓库根 `/home/user/hermes-agent`,
> commit `863e31318553cda8ad61df681d08175364d4164b`(下称 `@ 863e313`)。
> 锚点一律单独成行、置于代码块之前。

---

## 0. 本簇范围与文件清单

本轮精读 5 个文件,合计 2,756 行:

| 文件 | 行数 | 一句话定位 |
|---|---|---|
| `agent/video_gen_provider.py` | 590 | 视频后端的 ABC(抽象基类)+ 落盘助手 + **一个可复用的 OpenAI 兼容后端实现** |
| `agent/video_gen_registry.py` | 133 | 后端注册表与"当前活跃后端"解析 |
| `tools/video_generation_tool.py` | 575 | 统一工具 `video_generate`:后端无关的调度层 + 动态 schema |
| `tools/flux3_video_tool.py` | 1249 | BFL FLUX 3 的 6 个原生工具(经 Nous 托管网关),**自带轮询循环与落盘** |
| `tools/xai_video_tools.py` | 209 | xAI Imagine 的 video edit / extend 两个专用工具 |

**先给一个总纲(后面逐条取证)**:这 5 个文件不是一套机制,而是**两套并列、互不知情的视频子系统**,
外加第三个附着在其中一套上的小补丁:

1. **插件化统一面**(`video_gen_provider` + `video_gen_registry` + `video_generation_tool`,
   toolset 名 `video_gen`)——一个工具 `video_generate`,后端由插件注册,**同步阻塞直到视频出来**。
2. **BFL 直连面**(`flux3_video_tool`,toolset 名 `bfl`)——6 个工具,**submit 立即返回 job id +
   一个自带长轮询的 poll 工具**,完全不走 `VideoGenProvider` ABC。
3. **xAI 特例补丁**(`xai_video_tools`,挂在 toolset `video_gen` 下)——只做 edit/extend,
   因为统一面明确把 edit/extend 排除在外了。

---

## 1. 一次视频生成请求的完整走法(重点:长任务怎么等)

### 1.1 视频与图像最大的差别:耗时

统一工具自己的描述里就把这件事写死给模型看了。

`tools/video_generation_tool.py:419-433 @ 863e313`

```python
_GENERIC_DESCRIPTION = (
    "Generate a video from a text prompt (text-to-video), animate a "
    "still image (image-to-video), or guide generation with reference images. "
    "Pass `image_url` to animate an image or `reference_image_urls` for "
    "reference-to-video. Video edit/extend workflows are not part of this "
    "unified surface; use a dedicated provider-specific tool when one is "
    "available. The backend and model family are user-configured via "
    "`hermes tools` → Video Generation; the agent does not pick them. "
    "Long-running generations may take 30 seconds to several minutes — "
    "the call blocks until the video is ready. Returns the result in the "
    "`video` field — either an HTTP URL or an absolute file path. To show "
    "it to the user, reference that path/URL in your response using the "
    "file-delivery convention for the current platform (your platform "
    "guidance describes how files are delivered here)."
)
```

**结论:统一面选的是"同步阻塞"。** 没有 webhook 回调,没有把 job id 交回给模型。

BFL 面选的是相反的答案 —— submit / poll 分离,而且**把等待搬进 poll 工具内部**。

`tools/flux3_video_tool.py:1011-1020 @ 863e313`

```python
GET_RESULT_SCHEMA = {
    "name": "bfl_flux3_get_result",
    "description": (
        "Poll a FLUX 3 video job by the job id a generate tool returned. Generation takes minutes "
        "and a long Generating phase is normal. This call waits for you while the job runs, so it "
        "may run for several minutes; if it returns still generating, just call it again. Do not "
        "sleep between calls. "
        "On Ready the clip is downloaded for you and the response gives its local path; your only "
        "remaining step is to deliver that file as the response describes."
    ),
```

### 1.2 三套"等法"并存,三个不同的超时数字

| 路径 | 等法 | 死线 | 轮询间隔 | 锚点 |
|---|---|---|---|---|
| `OpenAICompatibleVideoGenProvider`(DeepInfra / Sora / OpenRouter) | 同步阻塞 + 自研有界轮询 | **900s** | 5s | `agent/video_gen_provider.py:408` 的 `_poll_interval_s: float = 5.0` |
| xAI 插件(`plugins/video_gen/xai`) | 同步阻塞 + 自研轮询 | **240s** | 5s | `plugins/video_gen/xai/__init__.py:52`:`DEFAULT_TIMEOUT_SECONDS = 240` |
| FAL 插件(`plugins/video_gen/fal`) | 同步阻塞,**交给 SDK,无本地死线** | 无 | SDK 内部 | `plugins/video_gen/fal/__init__.py:571` 的 `result = handle.get()` |
| BFL `bfl_flux3_get_result` | 异步 + 有界轮询,超时后返回"再叫我一次" | **240s 兜底 / 180s 轮询预算** | 5s | `tools/flux3_video_tool.py:215` 的 `_CALL_BACKSTOP_SECONDS = 240.0` |

三个数字互不知情。下面逐个取证。

#### (a) OpenAI 兼容后端:900s,自己重写了 SDK 的轮询

这是本簇最值得学的一段设计说明——它写清楚了"为什么不用 SDK 自带的 `create_and_poll`"。

`agent/video_gen_provider.py:402-409 @ 863e313`

```python
    # Polling cadence for the async video job. The OpenAI SDK's
    # ``create_and_poll`` defaults to ~1 poll/second and loops forever on a
    # non-terminal status, so a multi-minute job issues hundreds of sequential
    # requests and a stuck job pins its tool-executor worker thread with no way
    # out. We hand-roll a bounded poll instead: a coarse interval plus a hard
    # wall-clock deadline that surfaces a timeout error.
    _poll_interval_s: float = 5.0
    _poll_deadline_s: float = 900.0
```

`agent/video_gen_provider.py:419-441 @ 863e313`

```python
    def _create_and_poll(self, client: Any, call_kwargs: Dict[str, Any]) -> Any:
        """Create the video job and poll to completion with a hard deadline.

        Replaces ``client.videos.create_and_poll`` (unbounded 1/s loop) with a
        coarse interval and a wall-clock cap. Returns the terminal video object
        (any status); raises :class:`TimeoutError` if the deadline passes
        first.
        """
        import time

        video = client.videos.create(**call_kwargs)
        terminal = {"completed", "succeeded", "failed", "error", "cancelled", "canceled"}
        deadline = time.monotonic() + self._poll_deadline_s
        while getattr(video, "status", None) not in terminal:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"video job {getattr(video, 'id', '?')} did not reach a terminal "
                    f"status within {int(self._poll_deadline_s)}s "
                    f"(last status={getattr(video, 'status', None)!r})"
                )
            time.sleep(self._poll_interval_s)
            video = client.videos.retrieve(video.id)
        return video
```

**要点**:
- `terminal` 集合刻意收了 6 个词,涵盖不同厂商的措辞(`completed` vs `succeeded`,
  `cancelled` vs `canceled`)。
- 但"终态"和"成功态"是两个概念,后面还要再判一次:

`agent/video_gen_provider.py:526-541 @ 863e313`

```python
            # Terminal success status differs across backends: DeepInfra reports
            # "succeeded", OpenAI/Sora reports "completed". Accept both.
            status = getattr(video, "status", None)
            if status not in ("completed", "succeeded"):
                # ``video.error`` is a structured SDK object (pydantic
                # VideoCreateError), not a string — str() it so the response
                # dict stays JSON-serializable for the tool layer.
                job_error = getattr(video, "error", None)
                return error_response(
                    error=str(job_error) if job_error else f"video job ended with status={status!r}",
                    error_type="job_failed",
                    provider=self.name,
                    model=model_id,
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                )
```

- `TimeoutError` **不外抛**,而是被统一 catch 成 `error_type="api_error"` 的普通失败响应:

`agent/video_gen_provider.py:512-524 @ 863e313`

```python
        try:
            try:
                video = self._create_and_poll(client, call_kwargs)
            except Exception as exc:  # noqa: BLE001 - surface any SDK/API/timeout failure uniformly
                logger.debug("%s video generation failed", self.name, exc_info=True)
                return error_response(
                    error=f"{self.name} video generation failed: {exc}",
                    error_type="api_error",
                    provider=self.name,
                    model=model_id,
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                )
```

**取舍**:900s = 15 分钟的同步阻塞。这段时间里工具执行线程被完全占住。
下面 1.3 会说明这个数字在不同宿主下的实际后果不一样(有的宿主 300s 就把它掐了)。

#### (b) BFL:submit / poll 分离 + "把等待搬进工具内部"

这是本簇最讲究的一段。设计理由写在常量旁边的长注释里,值得整块抄下来。

`tools/flux3_video_tool.py:202-221 @ 863e313`

```python
# One get_result call looks repeatedly rather than a fixed twice. The job
# endpoint answers immediately — there is no long poll — so every second
# between looks is a second a finished clip goes unnoticed, and many
# short-spaced looks per call cut both that notice delay and the number of
# times the model has to decide to keep waiting.
#
# Two bounds keep the loop inside the agent's per-tool ceiling. model_tools'
# async bridge abandons a tool at 300s and reports it to the model as a bare
# "TimeoutError:" — no job id, no sign the generation is still alive — which is
# the worst answer this tool can give, so neither bound may approach it.
# _CALL_BACKSTOP_SECONDS is the wall-clock guarantee over the whole handler;
# _POLL_BUDGET_SECONDS stops new looks earlier still, and the difference
# between them is what a clip finishing on the last look has to download in.
_CALL_BACKSTOP_SECONDS = 240.0
_POLL_BUDGET_SECONDS = 180.0
# The gap between looks, and so the notice delay on a finished job. The
# gateway's poll limiter allows 120 a minute per principal, and it only ever
# has one generation of ours to answer for, so this cadence spends about a
# tenth of what it permits.
_POLL_GAP_SECONDS = 5.0
```

`tools/flux3_video_tool.py:222-245 @ 863e313`

```python
# The budget is counted as it is spent — the waits and the time each look
# actually takes — rather than read off a wall clock. A slow gateway therefore
# costs looks instead of overrunning the call, and the loop stays testable
# without a fake clock.
#
# Waits are taken in slices so they stay answerable. Nothing outside a tool can
# end a call that has already started — the executor only checks for an
# interrupt between tools — so a tool that blocks this long watches the flag
# itself.
_POLL_WAIT_SLICE_SECONDS = 1.0
# A poll's own read timeout. It has to clear the gateway's server-side poll
# budget, which bounds one status read at 45s across its retries and its
# regional redirect hops: cutting a poll off before the server would give up
# turns a slow-but-healthy read into a transport error, and an error ends the
# loop. Still far below the submit path's patience, so a wedged poll cannot
# quietly spend the whole call either.
_POLL_READ_TIMEOUT_SECONDS = 60.0
# How many looks in a row may fail to reach the gateway before the loop gives
# up on the call. A blip costs a look rather than the whole remaining budget:
# ending on the first one hands the model an error it can only answer by
# polling again immediately, which is the burst this loop exists to prevent.
# Bounded so a gateway that is genuinely down is reported promptly instead of
# being retried for minutes.
_MAX_CONSECUTIVE_TRANSPORT_ERRORS = 3
```

轮询循环本体:

`tools/flux3_video_tool.py:699-741 @ 863e313`

```python
async def _poll_until_done(url: str, save_to, started: float) -> str:
    """Look until the job settles, the budget runs out, or the user stops.

    The waiting is absorbed here rather than asked of the model. A model has no
    clock: told to wait it emits "I'll check back in a minute" and its next
    action lands immediately, so guidance produced a burst of polls rather than
    a paced one. Waiting inside the call cannot be skipped, needs no shell, and
    works the same on every platform.
    """
    spent = 0.0
    unanswered = 0
    while True:
        look_started = time.monotonic()
        raw = await _call_gateway("GET", url, read_timeout=_POLL_READ_TIMEOUT_SECONDS)
        spent += time.monotonic() - look_started

        if _is_transport_error(raw):
            # The job is upstream and unaffected by our failure to ask about
            # it, so a blip costs this look and the loop tries again.
            unanswered += 1
            if unanswered >= _MAX_CONSECUTIVE_TRANSPORT_ERRORS:
                return raw
            gap = _POLL_GAP_SECONDS
        else:
            unanswered = 0
            throttled_for = _retry_after_seconds(raw)
            if throttled_for is None and _poll_is_finished(raw):
                return await _save_if_ready(raw, save_to, started)
            # Never faster than our own cadence, however short a wait the
            # gateway names: its number is a floor on politeness, not a licence
            # to hammer.
            gap = _POLL_GAP_SECONDS if throttled_for is None else max(throttled_for, _POLL_GAP_SECONDS)

        if gap <= 0 or spent + gap >= _POLL_BUDGET_SECONDS:
            # Out of budget. A still-generating status carries the gateway's own
            # "call again"; a throttle we could not outwait carries its wait.
            return raw
        if not await _wait_between_looks(gap):
            # Interrupted mid-wait: hand back the status we already have rather
            # than spending a round trip the user has just asked us to stop for.
            return raw
        spent += gap
```

外层还套了一层 `asyncio.wait_for` 硬兜底,超时后**返回一条普通的"再叫我一次"文本,而不是抛异常**:

`tools/flux3_video_tool.py:755-767 @ 863e313`

```python
    started = time.monotonic()

    # The loop stops itself once its budget is spent, but a look already in
    # flight still runs to completion, and a download follows it. This is the
    # wall-clock guarantee over all of that: whatever stalls inside, the model
    # is answered from here rather than by the async bridge, whose own timeout
    # arrives as a bare "TimeoutError:".
    try:
        return await asyncio.wait_for(
            _poll_until_done(url, save_to, started), timeout=_CALL_BACKSTOP_SECONDS
        )
    except asyncio.TimeoutError:
        return _still_generating(job_id)
```

`tools/flux3_video_tool.py:684-696 @ 863e313`

```python
def _still_generating(job_id: str) -> str:
    """The backstop's answer: an ordinary "call again", never a raised timeout."""
    return json.dumps(
        {
            "result": (
                "Still generating. This call reached its own time limit, which the job is "
                f"unaffected by — call bfl_flux3_get_result again with id={job_id} to keep "
                "waiting."
            ),
            "details": {"id": job_id, "status": "Generating"},
        },
        ensure_ascii=False,
    )
```

**这是本簇最强的一条设计教训**:长任务工具的失败模式不是"超时",而是"**超时后给模型的那句话没有信息量**"。
`TimeoutError:` 让模型无法判断 job 是死了还是还活着;`_still_generating` 把 job id 还回去,
把"继续等"变成模型能执行的下一步。

轮询期间还要响应用户中断——因为执行器只在**工具之间**检查中断标志:

`tools/flux3_video_tool.py:306-317 @ 863e313`

```python
async def _wait_between_looks(seconds: float) -> bool:
    """Hold the call open until the next look; False if the user interrupted."""
    from tools.interrupt import is_interrupted

    remaining = seconds
    while remaining > 0:
        if is_interrupted():
            return False
        this_slice = min(_POLL_WAIT_SLICE_SECONDS, remaining)
        await asyncio.sleep(this_slice)
        remaining -= this_slice
    return True
```

"限流(throttle)是唯一值得在工具内部吞掉的拒绝",理由写得很直白:

`tools/flux3_video_tool.py:270-279 @ 863e313`

```python
def _retry_after_seconds(raw: str) -> Optional[float]:
    """How long the gateway asked us to wait, when a refusal is a throttle.

    A throttle is the one refusal worth absorbing here rather than handing
    back. Returning it ends the call, and the model it lands on has no clock —
    told to wait, it asks again immediately — so a rate limit answered that way
    produces a tighter loop than the one that tripped it. The gateway sends the
    wait as a number alongside the message, so there is nothing to parse out of
    prose.
    """
```

"没答复"和"答了个不"必须区分开,并且是靠**标志位**而不是靠匹配错误文案:

`tools/flux3_video_tool.py:293-303 @ 863e313`

```python
def _is_transport_error(raw: str) -> bool:
    """True when the gateway did not answer, as opposed to answering "no".

    Set by ``_call_gateway`` on the paths where nothing readable came back, so
    this reads a flag rather than matching on the text of a message.
    """
    try:
        payload = json.loads(raw)
    except Exception:
        return False
    return isinstance(payload, dict) and payload.get("transport_error") is True
```

终态集合直接照抄网关侧的 BFL 状态词:

`tools/flux3_video_tool.py:247-250 @ 863e313`

```python
# Mirrors the gateway's BFL statuses
_TERMINAL_POLL_STATUSES = frozenset(
    {"Ready", "Error", "Request Moderated", "Content Moderated", "Task not found"}
)
```

### 1.3 "300s / 420s 的宿主天花板"这件事需要精确化(重要)

flux3 的注释断言"model_tools' async bridge abandons a tool at 300s"。查证结果:**这句话成立,但只在一条分支上成立**。

`model_tools.py:177-180 @ 863e313`

```python
        future = pool.submit(propagate_context_to_thread(_run_in_worker))
        try:
            return future.result(timeout=300)
        except concurrent.futures.TimeoutError:
```

这个 300s 只在"当前线程已经有一个正在跑的事件循环"(网关 / RL 环境)这条分支里。另外两条分支没有超时:

`model_tools.py:202-207 @ 863e313`

```python
    if threading.current_thread() is not threading.main_thread():
        worker_loop = _get_worker_loop()
        return worker_loop.run_until_complete(coro)

    tool_loop = _get_tool_loop()
    return tool_loop.run_until_complete(coro)
```

而且这条桥**只对 `is_async=True` 的工具生效**:

`tools/registry.py:772-777 @ 863e313`

```python
        try:
            if entry.is_async:
                from model_tools import _run_async
                result = _run_async(entry.handler(args, **kwargs))
            else:
                result = entry.handler(args, **kwargs)
```

- `bfl_flux3_*` 六个工具全是 `is_async=True`(见 2.4),所以确实受这条 300s 约束(在网关分支上)。
- `video_generate` 是 `is_async=False`(`tools/video_generation_tool.py:573` 的 `is_async=False`),
  **不经过这条桥**,因此那 900s / 240s / FAL 的无界等待没有这条 300s 兜底。
- 另有一条 420s 的天花板,但只作用在**并发批量执行**路径上:

`agent/tool_executor.py:97-99 @ 863e313`

```python
# Keep this above the stock auxiliary.web_extract timeout (360s) so the batch
# guard does not preempt a slow-but-valid summarization attempt.
_DEFAULT_CONCURRENT_TOOL_TIMEOUT_S = 420.0
```

**推论(标注为推定,未实跑)**:一次 `video_generate` 调用如果落在 FAL 后端且 FAL 侧长时间不返回,
在"单工具串行执行 + CLI 主线程"这条路径上没有任何本地死线。这是本簇最大的一条不对称。
见 §5 ■-3。

---

## 2. 逐文件 / 逐机制

### 2.1 `agent/video_gen_provider.py`(590 行)

#### 2.1.1 它比 image 版(393 行)多出来的到底是什么

逐段比对(`agent/image_gen_provider.py` 全文结构 vs 本文件),多出来的主要是三块:

| 多出的东西 | 位置 | 行数量级 |
|---|---|---|
| `OpenAICompatibleVideoGenProvider` 整个可复用后端 | `agent/video_gen_provider.py:379` 的 `class OpenAICompatibleVideoGenProvider(VideoGenProvider):` | ~212 行(379–590) |
| `save_bytes_video` / `save_url_video` 两个落盘助手 | `agent/video_gen_provider.py:233` 的 `def save_bytes_video(` | ~85 行 |
| `capabilities()` 的字段扩到 8 个(image 版只有 2 个) | `agent/video_gen_provider.py:138` 的 `def capabilities(self) -> Dict[str, Any]:` | ~30 行 |

image 版的 `capabilities()` 只声明两个键:

`agent/image_gen_provider.py:160-163 @ 863e313`

```python
        return {
            "modalities": ["text"],
            "max_reference_images": 0,
        }
```

video 版声明 8 个:

`agent/video_gen_provider.py:157-166 @ 863e313`

```python
        return {
            "modalities": ["text"],
            "aspect_ratios": list(COMMON_ASPECT_RATIOS),
            "resolutions": list(COMMON_RESOLUTIONS),
            "max_duration": 10,
            "min_duration": 1,
            "supports_audio": False,
            "supports_negative_prompt": False,
            "max_reference_images": 0,
        }
```

**所以"video provider 比 image provider 大 200 行"的答案是:大头不是抽象本身,而是抽象里塞了一个具体实现**
—— `OpenAICompatibleVideoGenProvider`。它的存在理由写在类 docstring 里:

`agent/video_gen_provider.py:379-397 @ 863e313`

```python
class OpenAICompatibleVideoGenProvider(VideoGenProvider):
    """Generic text/image-to-video over the OpenAI ``client.videos`` API.

    DeepInfra, OpenAI/Sora, and OpenRouter all expose the same
    ``POST /videos`` async-job shape (``create`` → poll → ``download_content``),
    so the SDK call lives here once. A concrete backend only needs to declare
    its identity and credentials::

        class FooVideoGenProvider(OpenAICompatibleVideoGenProvider):
            name = "foo"
            _env_key = "FOO_API_KEY"
            _default_base_url = "https://api.foo.com/v1/openai"
            def list_models(self):
                return [...]   # entries with an "id" key; default_model() uses [0]

    ``image_url`` routes to image-to-video; its absence routes to text-to-video.
    Provider-specific fields (``image_url``/``negative_prompt``/``seed``) ride
    in ``extra_body`` so they pass through the SDK unchanged.
    """
```

实际吃到这份红利的只有 DeepInfra 一家,整个插件因此只有 90 行:

`plugins/video_gen/deepinfra/__init__.py:25-30 @ 863e313`

```python
class DeepInfraVideoGenProvider(OpenAICompatibleVideoGenProvider):
    """Text-to-video and image-to-video via DeepInfra's OpenAI-compatible API."""

    name = "deepinfra"
    _env_key = "DEEPINFRA_API_KEY"
    _default_base_url = "https://api.deepinfra.com/v1/openai"
```

#### 2.1.2 统一响应形状

ABC 的 docstring 把响应键写死成契约(这是重实现时最该照抄的部分):

`agent/video_gen_provider.py:30-45 @ 863e313`

```python
Response shape
--------------
All providers return a dict built by :func:`success_response` /
:func:`error_response`. Keys:

    success         bool
    video           str | None      URL or absolute file path
    model           str             provider-specific model identifier
    prompt          str             echoed prompt
    modality        str             "text" | "image" (which mode was used)
    aspect_ratio    str             provider-native (e.g. "16:9") or ""
    duration        int             seconds (0 if not applicable)
    provider        str             provider name (for diagnostics)
    error           str             only when success=False
    error_type      str             only when success=False
"""
```

`modality` 这个字段是"事后诊断"用的——它记录**实际打的是哪个端点**,而不是调用方要求了什么:

`agent/video_gen_provider.py:330-335 @ 863e313`

```python
    """Build a uniform success response dict.

    ``video`` may be an HTTP URL or an absolute filesystem path.
    ``modality`` is ``"text"`` (text-to-video) or ``"image"`` (image-to-video) —
    indicates which endpoint was actually hit, useful for diagnostics.
    """
```

`extra` 走 `setdefault`,即**插件不能覆盖标准字段**:

`agent/video_gen_provider.py:346-349 @ 863e313`

```python
    if extra:
        for k, v in extra.items():
            payload.setdefault(k, v)
    return payload
```

#### 2.1.3 "一个工具管两种模态"的路由约定,以及被刻意排除的东西

`agent/video_gen_provider.py:17-28 @ 863e313`

```python
Unified surface
---------------
One tool — ``video_generate`` — covers **text-to-video** and **image-to-video**.
The router is the presence of ``image_url``: if it's set, the provider routes
to its image-to-video endpoint; if it's omitted, the provider routes to
text-to-video. Users pick one **model family** (e.g. Pixverse v6, Veo 3.1,
Kling O3 Standard); the provider handles which underlying FAL/xAI endpoint
to hit.

Video edit and video extend are intentionally NOT exposed in this surface —
the inconsistency across backends is too large for one unified tool. If
those use cases warrant attention later they can ship as separate tools.
```

**这段是理解 `xai_video_tools.py` 存在理由的钥匙**:edit/extend 被从统一面里排除,
于是需要它们的后端只能另开工具。§2.5 就是这句话的兑现。

#### 2.1.4 产物落盘:三个助手 + 一个大小上限

`agent/video_gen_provider.py:204-210 @ 863e313`

```python
def _videos_cache_dir() -> Path:
    """Return ``$HERMES_HOME/cache/videos/``, creating parents as needed."""
    from hermes_constants import get_hermes_home

    path = get_hermes_home() / "cache" / "videos"
    path.mkdir(parents=True, exist_ok=True)
    return path
```

`save_url_video` 是三个助手里唯一有网络行为的,它的存在理由是"**厂商给的交付 URL 会在下游取用前过期**":

`agent/video_gen_provider.py:255-271 @ 863e313`

```python
def save_url_video(
    url: str,
    *,
    prefix: str = "video",
    timeout: float = 180.0,
    max_bytes: int = 200 * 1024 * 1024,
) -> Path:
    """Download a video URL and write it under ``$HERMES_HOME/cache/videos/``.

    The video twin of :func:`agent.image_gen_provider.save_url_image`: several
    backends (DeepInfra, FAL) return an *ephemeral* delivery URL that expires
    before a downstream consumer can fetch it, so we materialise the bytes
    locally at tool-completion time. Streams with a size cap.

    Raises on any network / HTTP / oversize error so callers can fall back to
    returning the bare URL.
    """
```

大文件怎么办:**流式 + 200MB 硬上限 + 超限即删**,并且**0 字节也算失败**:

`agent/video_gen_provider.py:292-316 @ 863e313`

```python
    bytes_written = 0
    with path.open("wb") as fh:
        for chunk in response.iter_content(chunk_size=256 * 1024):
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
                    f"Video at {url} exceeds {max_bytes // (1024 * 1024)}MB cap; refusing to cache."
                )
            fh.write(chunk)

    if bytes_written == 0:
        try:
            path.unlink()
        except OSError:
            pass
        raise ValueError(f"Video at {url} was empty (0 bytes).")

    return path
```

扩展名推断有三级回退(Content-Type → URL 后缀 → `mp4`):

`agent/video_gen_provider.py:277-286 @ 863e313`

```python
    content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    extension = _URL_VIDEO_CONTENT_TYPES.get(content_type)
    if extension is None:
        url_path = url.split("?", 1)[0].lower()
        for ext in ("mp4", "webm", "mov", "mkv"):
            if url_path.endswith(f".{ext}"):
                extension = ext
                break
    if extension is None:
        extension = "mp4"
```

落盘失败时的降级策略——**能给 URL 就给 URL,不硬失败**:

`agent/video_gen_provider.py:555-576 @ 863e313`

```python
            try:
                if url:
                    # Materialise the (often short-lived) delivery URL locally.
                    video_ref = str(save_url_video(url, prefix=self.name))
                else:
                    # OpenAI/Sora style: no public URL — pull bytes via the SDK.
                    raw = client.videos.download_content(video.id).read()
                    video_ref = str(save_bytes_video(raw, prefix=self.name))
            except Exception as exc:  # noqa: BLE001
                if url:
                    # Best-effort: hand back the URL rather than fail outright.
                    logger.debug("%s: saving video locally failed (%s); returning URL", self.name, exc)
                    video_ref = url
                else:
                    return error_response(
                        error=f"{self.name} video job succeeded but no output could be retrieved: {exc}",
                        error_type="empty_response",
                        provider=self.name,
                        model=model_id,
                        prompt=prompt,
                        aspect_ratio=aspect_ratio,
                    )
```

**清理策略**:`$HERMES_HOME/cache/videos` 的清理只有一个调用方——**网关的每小时管家循环,24 小时 TTL**。

`gateway/platforms/base.py:1103-1109 @ 863e313`

```python
def cleanup_video_cache(max_age_hours: int = 24) -> int:
    """
    Delete cached videos older than *max_age_hours*.

    Returns the number of files removed.
    """
    return _cleanup_cache_dir(get_video_cache_dir(), max_age_hours)
```

`gateway/run.py:26161-26169 @ 863e313`

```python
    # Every platform media cache prunes on the same hourly cadence — one loop
    # over (name, cleanup_fn), not a copy-pasted try/except per cache.
    MEDIA_CACHE_CLEANUPS = (
        ("Image", cleanup_image_cache),
        ("Document", cleanup_document_cache),
        ("Audio", cleanup_audio_cache),
        ("Video", cleanup_video_cache),
        ("Screenshot", cleanup_screenshot_cache),
    )
```

**负结论(搜索面写明)**:全仓只有 `gateway/run.py` 一处引用 `cleanup_video_cache`。
搜索面 = 全仓所有 `*.py`(**含 tests**),模式为字面量 `cleanup_video_cache`,无排除目录:

```verify
cd /home/user/hermes-agent && grep -rn "cleanup_video_cache" --include=*.py .
```

实测输出 3 行:定义 1 行(`gateway/platforms/base.py:1103`)+ 调用 2 行(`gateway/run.py:26150` 的 import、
`gateway/run.py:26167` 的 tuple 项)。**即:纯 CLI 使用(不起网关)时,视频缓存无人清理。**

#### 2.1.5 `save_b64_video` 是零调用方的公开 API

```verify
cd /home/user/hermes-agent && grep -rn "save_b64_video" --include=*.py .
```

实测只有 1 行(`agent/video_gen_provider.py:213` 的定义),全仓无任何调用方(含 tests)。
它是给插件作者用的 API,并且被开发者文档点名推荐(见 §5 ◇-2)。不是缺陷,是一条"文档先行"的 API。

### 2.2 `agent/video_gen_registry.py`(133 行)

#### 2.2.1 与 image_gen_registry 同构 —— 而且是**明写的同构**

`agent/video_gen_registry.py:18-22 @ 863e313`

```python
Mirrors ``agent/image_gen_registry.py`` so the two surfaces behave the
same: the unconfigured fallback is filtered by ``is_available()`` so a box
that has credentials for only one backend (e.g. DeepInfra, while the
``fal``/``xai`` plugins also register unconditionally) auto-selects it
instead of returning ``None``.
```

结构上是逐函数对应:`register_provider` / `list_providers` / `get_provider` /
`get_active_provider` / `_reset_for_tests`,一把 `threading.Lock`,一个模块级 dict。
**没有共用的上层抽象**——两套注册表是复制粘贴的同构,不是泛型化的。
(`agent/image_gen_registry.py` 145 行 vs 本文件 133 行,差异主要是 image 侧多一段 in-tree FAL 兜底相关的注释。)

#### 2.2.2 活跃后端解析:显式配置 = 失败关闭;未配置 = 按可用性单选

`agent/video_gen_registry.py:98-109 @ 863e313`

```python
    with _lock:
        snapshot = dict(_providers)

    if configured:
        provider = snapshot.get(configured)
        if provider is not None:
            return provider
        logger.debug(
            "video_gen.provider='%s' configured but not registered; failing closed",
            configured,
        )
        return None
```

`agent/video_gen_registry.py:111-127 @ 863e313`

```python
    def _is_available_safe(p: VideoGenProvider) -> bool:
        """Wrap ``is_available()`` so a buggy provider doesn't kill resolution."""
        try:
            return bool(p.is_available())
        except Exception as exc:  # noqa: BLE001
            logger.debug("video_gen provider %s.is_available() raised %s", p.name, exc)
            return False

    # Fallback: single *available* provider — filter by is_available() so a
    # box with credentials for only one backend auto-selects it even when
    # other providers (fal/xai) register unconditionally without keys.
    # Mirrors agent/image_gen_registry.get_active_provider().
    available = [p for p in snapshot.values() if _is_available_safe(p)]
    if len(available) == 1:
        return available[0]

    return None
```

**设计要点(值得抄)**:
- 写错 provider 名 → 返回 None,而不是"退回到某个后端"。理由在测试里写得比代码还清楚
  (`tests/agent/test_video_gen_registry.py:76` 的 `"""A typo must not silently route a paid request to another backend."""`)。
- `is_available()` 由插件实现,可能抛异常;这里用 `_is_available_safe` 包一层,
  **一个坏插件不能让整个解析崩掉**。
- "恰好一个可用"才自动选;两个可用则返回 None(逼用户显式选),零个也返回 None。

#### 2.2.3 注册的两道校验 + 幂等重注册

`agent/video_gen_registry.py:47-61 @ 863e313`

```python
    if not isinstance(provider, VideoGenProvider):
        raise TypeError(
            f"register_provider() expects a VideoGenProvider instance, "
            f"got {type(provider).__name__}"
        )
    name = provider.name
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Video gen provider .name must be a non-empty string")
    with _lock:
        existing = _providers.get(name)
        _providers[name] = provider
    if existing is not None:
        logger.debug("Video gen provider '%s' re-registered (was %r)", name, type(existing).__name__)
    else:
        logger.debug("Registered video gen provider '%s' (%s)", name, type(provider).__name__)
```

注意 `get_provider` 对入参做了 `.strip()`,但 `register_provider` **没有** strip `provider.name`
(只判非空)。所以插件若把 name 写成 `" xai "`,注册键带空格、`get_provider(" xai ")` 反而查不到。
属边角,记在 §6 移交。

### 2.3 `tools/video_generation_tool.py`(575 行)

#### 2.3.1 定位:一个"不带任何后端"的工具

`tools/video_generation_tool.py:14-18 @ 863e313`

```python
The tool itself is intentionally backend-agnostic and ships **no in-tree
provider** — turn on a backend by enabling a plugin (``hermes plugins
enable video_gen/<name>``) and selecting it in ``hermes tools`` → Video
Generation.
```

#### 2.3.2 后端解析:两次插件发现

`tools/video_generation_tool.py:226-244 @ 863e313`

```python
def _resolve_active_provider():
    """Return the active provider object or None.

    Forces plugin discovery before checking the registry — handles cases
    where a long-lived session was started before a plugin was installed.
    """
    try:
        from agent.video_gen_registry import get_active_provider
        from hermes_cli.plugins import _ensure_plugins_discovered

        _ensure_plugins_discovered()
        provider = get_active_provider()
        if provider is None:
            _ensure_plugins_discovered(force=True)
            provider = get_active_provider()
        return provider
    except Exception as exc:
        logger.debug("video_gen provider resolution failed: %s", exc)
        return None
```

第一次是幂等发现(便宜),失败后才 `force=True` 重扫。**"贵的重试只在便宜的失败后做"**。

#### 2.3.3 参数处理:全部软化,不硬拒

`tools/video_generation_tool.py:273-293 @ 863e313`

```python
def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "1", "yes", "on"}:
            return True
        if v in {"false", "0", "no", "off"}:
            return False
    return None
```

`_normalize_reference_images` 甚至接受**单个字符串**当作单元素列表:

`tools/video_generation_tool.py:296-307 @ 863e313`

```python
def _normalize_reference_images(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return None
    out: List[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out or None
```

**设计取向很明确**:模型给的参数一律"能捞就捞",捞不上来就当没给,让后端自己 clamp。
唯一的硬拒是空 prompt 和 edit/extend 字段:

`tools/video_generation_tool.py:322-331 @ 863e313`

```python
    # Soft validation — providers do their own. Prompt is required by the
    # schema; the backend may still accept image-only on its image-to-video
    # endpoint but our surface always needs a prompt.
    if not prompt:
        return tool_error("prompt is required for video generation")
    if "operation" in args or "video_url" in args:
        return tool_error(
            "video_generate only supports text-to-video, image-to-video, and "
            "reference-to-video; use a provider-specific tool for video edit/extend"
        )
```

这条 `"operation" in args or "video_url" in args` 是**给模型的纠偏提示**:模型见过
`xai_video_edit(video_url=...)`,很容易把 `video_url` 塞进 `video_generate`。
schema 里没有 `additionalProperties: False`,所以这类多余键会真的到达 handler,需要在这里拦。
测试把这条钉成了规格(`tests/tools/test_video_generation_dispatch.py:92` 的 `def test_edit_extend_fields_not_in_schema(self):`)。

#### 2.3.4 model 三级解析,以及一个隐藏 kwarg

`tools/video_generation_tool.py:339-355 @ 863e313`

```python
    # Resolve model: explicit arg wins, then config, then provider default.
    model = model_override or _read_configured_video_model() or provider.default_model()

    kwargs: Dict[str, Any] = {
        "model": model,
        "_model_override_explicit": bool(model_override),
        "image_url": image_url,
        "reference_image_urls": reference_image_urls,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "negative_prompt": negative_prompt,
        "audio": audio,
        "seed": seed,
    }
    # Drop None entries so providers see clean defaults.
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
```

`_model_override_explicit` 是**没有写进 ABC 签名的私有约定**:工具层已经把 config 里的
`video_gen.model` 折叠进 `model` 了,后端拿到 `model` 时无法区分"用户在工具调用里显式指定"
和"来自配置"。xAI 插件用它来决定要不要接受一个它不认识的 model id:

`plugins/video_gen/xai/__init__.py:444-447 @ 863e313`

```python
        return run_xai_video_generation(
            prompt=prompt,
            model=model,
            explicit_model=bool(kwargs.get("_model_override_explicit")),
```

**这是一条真实的设计债**:ABC 文档说 `kwargs` 是"未来 schema 会暴露的前向兼容参数"
(`agent/video_gen_provider.py:193-195`),但实际被用来传一个**永远不会进 schema 的内部信号**。

#### 2.3.5 插件契约违约的两类处理

`tools/video_generation_tool.py:357-376 @ 863e313`

```python
    try:
        result = provider.generate(prompt=prompt, **kwargs)
    except TypeError as exc:
        # A provider that hasn't widened its signature is a bug, not a
        # caller error — log and surface a clear contract message.
        logger.warning(
            "video_gen provider '%s' rejected kwargs (signature too narrow): %s",
            getattr(provider, "name", "?"), exc,
        )
        return json.dumps(error_response(
            error=(
                f"Provider '{getattr(provider, 'name', '?')}' signature is "
                f"out of date with the video_generate schema. Report this "
                f"to the plugin author."
            ),
            error_type="provider_contract",
            provider=getattr(provider, "name", ""),
            model=model or "",
            prompt=prompt,
        ))
```

以及"返回值不是 dict"也算契约违约:

`tools/video_generation_tool.py:390-399 @ 863e313`

```python
    if not isinstance(result, dict):
        return json.dumps(error_response(
            error="Provider returned a non-dict result",
            error_type="provider_contract",
            provider=getattr(provider, "name", ""),
            model=model or "",
            prompt=prompt,
        ))

    return json.dumps(result)
```

**要点**:`TypeError` 被单独 catch,并翻译成"**插件签名过期,去找插件作者**",
而不是笼统的 "provider error"。这是插件化系统里很值钱的一条:
把"宿主升级了 schema、插件没跟上"这一类错误做成**可识别、可归因**的错误类型。

#### 2.3.6 动态 schema:让工具描述反映"当前这台机器上真实可用的能力"

`tools/video_generation_tool.py:406-416 @ 863e313`

```python
# Why dynamic: the user's configured backend determines which modalities
# (text / image / refs), aspect ratios, resolutions, durations, and
# audio/negative-prompt flags are real. A model that calls video_generate
# without knowing the active backend wastes a turn on something like
# "fal-ai/veo3.1/image-to-video requires image_url". Surfacing the per-model
# surface in the description means the model usually gets the call right on
# the first try.
#
# Memoization: model_tools.get_tool_definitions() keys its cache on
# config.yaml mtime, so when the user changes provider/model via
# `hermes tools` or `/skills`, the schema rebuilds automatically.
```

构建过程必须用**和执行同一条**的解析逻辑,否则描述和行为会脱节:

`tools/video_generation_tool.py:475-489 @ 863e313`

```python
    configured_model = _read_configured_video_model()

    # Reflect the *resolved* active provider (same resolution the handler uses
    # in _resolve_active_provider): an explicit ``video_gen.provider``, or —
    # when unset — the single available registered backend. Keeping the
    # description in sync with execution stops the agent from being told
    # "no backend configured" while a call would actually succeed.
    provider = _resolve_active_provider()

    if provider is None:
        parts.append(
            "\nNo video backend is available. Calls will return an error "
            "until the user picks one via `hermes tools` → Video Generation."
        )
        return {"description": "\n".join(parts)}
```

只挑"和后端总体能力不同"的模型级注意事项,避免噪音:

`tools/video_generation_tool.py:447-462 @ 863e313`

```python
    modalities = set(model_meta.get("modalities") or [])
    modality = model_meta.get("modality")  # FAL's plugin uses this key for single-modality entries
    if modality:
        modalities.add(modality)

    if "image" in modalities and "text" not in modalities:
        caveats.append(
            "this model is image-to-video only — image_url is REQUIRED; "
            "text-only calls will be rejected"
        )
    elif "text" in modalities and "image" not in modalities:
        caveats.append(
            "this model is text-to-video only — image_url is not supported"
        )

    return caveats
```

`provider.capabilities()` / `provider.list_models()` 全部 try/except 兜底(插件抛异常不能让 schema 构建失败):

`tools/video_generation_tool.py:491-498 @ 863e313`

```python
    try:
        caps = provider.capabilities() or {}
    except Exception:
        caps = {}
    try:
        models = provider.list_models() or []
    except Exception:
        models = []
```

**唯一的后端硬编码分支**在这里(通用工具里出现具体 provider 名,是个味道):

`tools/video_generation_tool.py:541-556 @ 863e313`

```python
    if provider.name == "xai":
        parts.append(
            "- chaining: for edit/extend pass the public HTTPS MP4 in `video` "
            "or `public_url` from the prior Imagine result (files-cdn). For "
            "image-to-video / reference-to-video pass public image URLs the "
            "same way"
        )
        try:
            from tools.xai_http import xai_storage_notice_text

            notice = xai_storage_notice_text("video_gen")
        except Exception:
            notice = ""
        if notice:
            parts.append(f"- storage: {notice}")
```

#### 2.3.7 注册

`tools/video_generation_tool.py:565-575 @ 863e313`

```python
registry.register(
    name="video_generate",
    toolset="video_gen",
    schema=VIDEO_GENERATE_SCHEMA,
    handler=_handle_video_generate,
    check_fn=check_video_generation_requirements,
    requires_env=[],
    is_async=False,
    emoji="🎬",
    dynamic_schema_overrides=_build_dynamic_video_schema,
)
```

可见性门(任一后端可用即显示),并顺手触发插件发现:

`tools/video_generation_tool.py:199-218 @ 863e313`

```python
def check_video_generation_requirements() -> bool:
    """Return True when at least one registered provider reports available.

    Triggers plugin discovery (idempotent) so user-installed plugins are
    visible to the toolset gate.
    """
    try:
        from agent.video_gen_registry import list_providers
        from hermes_cli.plugins import _ensure_plugins_discovered

        _ensure_plugins_discovered()
        for provider in list_providers():
            try:
                if provider.is_available():
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False
```

### 2.4 `tools/flux3_video_tool.py`(1249 行)—— 为什么一个具体后端比通用工具还大

**答案:它根本不是"一个后端",它是一整条自带传输层、上传协议、轮询循环、下载落盘和交付话术的独立管线,
而且不复用 `VideoGenProvider` 的任何一行。** 逐项拆开(行数为粗略归属):

| 组成 | 大致行段 | 通用面有没有对应物 |
|---|---|---|
| 模块 docstring:设计原则声明 | 1–27 | 无 |
| 本地路径判定(从退役的 MCP 媒体遍历器搬来) | 64–103 | 无 |
| 网关 REST 传输层(含 guidance / error 语义) | 106–182 | 无(通用面用 SDK) |
| 媒体上传(presign → PUT → `nous-upload:` 引用) | 185–401 | 无 |
| 轮询常量 + 循环 + 中断响应 | 202–317, 699–767 | 有,但简单得多 |
| 成品下载 + 落盘 + 交付话术 | 404–624 | 只有 `save_url_video` |
| 6 份钉死的 schema | 828–1052 | 1 份动态 schema |
| 一整篇提示词指南(纯文本常量) | 1055–1178 | 无 |
| 6 次 `registry.register` | 1181–1249 | 1 次 |

**光是那篇 prompting guide 就是 119 行的字符串常量**(1060–1178),它本身也是一个工具的返回值。

#### 2.4.1 设计声明:schema 钉死在本地,策略从服务器来

`tools/flux3_video_tool.py:1-27 @ 863e313`

```python
"""Native BFL FLUX 3 video generation tools, backed by the Nous tool gateway.

These are native tools in the ``image_generate`` mold: schemas and
descriptions are pinned here as build-time facts, the handlers speak the
gateway's own REST contract, and ``check_fn`` hides the whole toolset only when
there is no Nous sign-in to call it with — never on entitlement, which is the
gateway's to rule on. No runtime discovery, and no server-supplied schema is
ever consulted — that is the point of the design.

The wire is two calls against the gateway's managed mount, and it names the
vendor but not the vendor's API:

- ``POST {base}/generations`` with ``{mode, prompt, ...}`` -> ``{id, status,
  guidance}``
- ``GET {base}/generations/<id>`` -> the job state plus ``guidance``

``guidance`` is the gateway's live policy channel: exact waits, what to do
next, and how to deliver a finished clip ship from the server so they cannot
drift from what it actually enforces. Handlers surface it verbatim as the
tool's result text, and surface ``error.message`` the same way on a refusal.

Media inputs: handlers know their own media fields explicitly. A local file
path is resolved through :func:`tools.image_source.resolve_image_source`
(sandbox confinement, credential guard) and delivered via the Nous upload
protocol (presign, direct PUT to storage, ``nous-upload:<token>`` reference).
URLs pass through untouched.
"""
```

**这里有一条很关键的分工**:
- **schema / 描述 / 提示词方法论** = 本地钉死(build-time fact),不从服务器取,理由是
  "一个能给每台已授权安装追加工具的远程端点,信任面比一次代码 diff 大"
  (`tools/managed_tool_gateway.py:226-228`)。
- **策略数字(等多久、限额、怎么交付)** = 服务器 `guidance` 字段实时下发,原样透传给模型,
  这样它不会和服务器真正执行的规则漂移。

`tools/flux3_video_tool.py:178-182 @ 863e313`

```python
    guidance = payload.pop("guidance", None)
    return json.dumps(
        {"result": guidance or "Request accepted.", "details": payload},
        ensure_ascii=False,
    )
```

#### 2.4.2 传输层:拒绝 ≠ 故障

`tools/flux3_video_tool.py:121-133 @ 863e313`

```python
    """One REST round trip, rendered as this tool's result.

    The gateway's ``guidance`` (on success) and ``error.message`` (on a
    refusal) are both written for a model to act on, so they are surfaced
    verbatim. A refusal is a normal outcome the model can respond to — being
    throttled is not a broken tool — so only genuinely unreadable responses
    become ``error``.

    Those unreadable ones carry ``transport_error`` as well. A refusal is the
    gateway's ruling on the request; a transport failure is the absence of one,
    and says nothing about the job. The poll loop tells them apart on that key
    rather than on the wording of a message.
    """
```

三种"读不出来"的情况都打 `transport_error`:连不上、body 不是 JSON、body 不是 dict。

`tools/flux3_video_tool.py:162-168 @ 863e313`

```python
    if not isinstance(payload, dict):
        # An edge or a proxy answering in HTML rather than the gateway itself,
        # which is what a 502 or 504 in front of it looks like from here.
        return json.dumps({
            "error": f"The video-generation gateway answered HTTP {response.status_code} with an unreadable body.",
            "transport_error": True,
        })
```

401 单独处理(带 `needs_reauth`):

`tools/flux3_video_tool.py:154-155 @ 863e313`

```python
    if response.status_code == 401:
        return json.dumps({"error": _SIGN_IN_MESSAGE, "needs_reauth": True})
```

submit 和 poll 用**不同的读超时**,理由写在常量旁:

`tools/flux3_video_tool.py:52-57 @ 863e313`

```python
# Submit sits behind the gateway's upstream call plus upload-reference
# resolution, so it is given a generous read timeout. A poll passes its own,
# much shorter one (see _POLL_READ_TIMEOUT_SECONDS): the job endpoint answers
# at once, and a poll allowed to hang this long would spend the whole call.
_TRANSPORT_READ_TIMEOUT_SECONDS = 180.0
_TRANSPORT_CONNECT_TIMEOUT_SECONDS = 10.0
```

#### 2.4.3 媒体输入:所有媒体字段都要消毒,不只当前 mode 用到的那个

`tools/flux3_video_tool.py:189-199 @ 863e313`

```python
# Every media field the gateway understands, and the media kind each accepts.
# `input_image` and `input_images` are interchangeable server-side, so both
# must be sanitized whatever the mode.
_MEDIA_FIELDS = {
    "input_image": ("image",),
    "input_images": ("image",),
    "input_video": ("video",),
}
# The vendor takes at most ten keyframes. Checked here as well as server-side
# so an over-long list is refused before it spends the caller's upload quota.
_MAX_IMAGES = 10
```

`tools/flux3_video_tool.py:337-345 @ 863e313`

```python
async def _prepare_media(args: dict, task_id: Optional[str]) -> dict:
    """Replace local paths with upload references in every media field.

    Deliberately covers all media fields rather than the one this mode
    expects. The gateway accepts `input_image` and `input_images`
    interchangeably, so a value left unsanitized in the "wrong" field still
    reaches the vendor — as a raw local path, which both fails the generation
    and discloses the user's directory layout to a third party.
    """
```

**这是一条安全教训**:"只处理这个 mode 声明要用的字段"是错的,因为服务器可能把两个字段等同看待,
未消毒的那个会把**用户本机绝对路径**发给第三方。

本地路径判定刻意做窄,并且**先排除 base64**:

`tools/flux3_video_tool.py:71-98 @ 863e313`

```python
# A whole string of base64 alphabet (optionally line-wrapped, optionally
# padded). Base64's alphabet includes "/", so an inline JPEG payload always
# starts with "/9j/" — which reads as an absolute path unless caught first.
_BASE64_PAYLOAD = re.compile(r"^[A-Za-z0-9+/\r\n]+={0,2}[\r\n]*$")
# Real filesystem paths are short; base64 of even a thumbnail runs to
# thousands of characters. Anything this long and alphabet-pure is a payload.
_MIN_BASE64_PAYLOAD_LENGTH = 256


def _looks_like_local_path(value: str) -> bool:
    """True for things we should read off disk rather than forward as-is.

    Deliberately narrow: only explicitly rooted paths and ``file://`` qualify.
    Bare names are ambiguous with opaque ids, URLs pass through, and base64
    payloads (checked first — a JPEG's base64 starts ``/9j/``) fall through
    untouched.
    """
    if len(value) >= _MIN_BASE64_PAYLOAD_LENGTH and _BASE64_PAYLOAD.match(value):
        return False
    if value.startswith("file://"):
        return True
    if value == "~" or value.startswith(("~/", "~\\")):
        return True
    if value.startswith(("/", "./", "../", ".\\", "..\\")):
        return True
    if _WINDOWS_DRIVE_PATH.match(value) or value.startswith("\\\\"):
        return True
    return False
```

多张关键帧**并发上传**,并且先热一次 token —— 这条注释描述了一个真实的竞态:

`tools/flux3_video_tool.py:320-334 @ 863e313`

```python
def _warm_nous_token() -> None:
    """Refresh the Nous token once, before any parallel upload needs it.

    ``read_nous_access_token`` takes no lock and, when a refresh fails, falls
    back to returning the stale cached token. Uploading in parallel therefore
    had every request discover the token was expiring at the same instant and
    fire its own refresh; the rotating refresh token means the first wins and
    the rest quietly send the stale bearer, which the gateway answers with 401.
    One warm-up call first puts a fresh token in the cache, so the fan-out all
    reads it instead of racing for it.
    """
    try:
        read_nous_access_token()
    except Exception as exc:  # pragma: no cover — the real read retries below
        logger.debug("Nous token warm-up failed before parallel uploads: %s", exc)
```

`tools/flux3_video_tool.py:352-362 @ 863e313`

```python
        if isinstance(value, list):
            if len(value) > _MAX_IMAGES:
                raise ValueError(f"{field} takes at most {_MAX_IMAGES} images; you passed {len(value)}.")
            # Uploaded together rather than one after another: each entry is a
            # presign round trip plus a full-file PUT, and ten keyframes in
            # sequence took long enough that a submit looked hung.
            prepared[field] = list(
                await asyncio.gather(*(_deliver_media(entry, permitted, task_id) for entry in value))
            )
        else:
            prepared[field] = await _deliver_media(value, permitted, task_id)
```

text-to-video 走另一条:**直接把媒体字段删掉**,不上传:

`tools/flux3_video_tool.py:366-372 @ 863e313`

```python
def _without_media(args: dict) -> dict:
    """Drop media fields entirely — for the mode that takes none.

    The gateway ignores them for text-to-video, so stripping here matches its
    behaviour while avoiding an upload the caller never needed.
    """
    return {k: v for k, v in dict(args or {}).items() if k not in _MEDIA_FIELDS}
```

#### 2.4.4 产物交付:客户端下载 + 签名 URL 从不外泄

`tools/flux3_video_tool.py:441-456 @ 863e313`

```python
async def _save_if_ready(raw: str, save_to, started: float) -> str:
    """Download a finished clip and swap the signed URL for a local path.

    The URL is handled here rather than by the model on purpose. It is long and
    percent-encoded, and re-keying it into a shell command dropped characters
    often enough to be the main failure mode of this tool — a corrupted
    signature is rejected, but `curl` still writes the rejection body to the
    output file and exits 0, so it read as success. Passing the exact string
    from this response removes the transcription step entirely.

    It also keeps a bearer credential out of the transcript: the signed URL
    grants the clip to anyone holding it for the next 15-60 minutes, and
    returning it put it in the model's context and the saved conversation. The
    gateway already scrubs presigned URLs for *input* media for exactly this
    reason; this makes the output side match.
    """
```

**这是本簇第二条最强的教训**:一个"看起来成功了"的失败
——`curl` 拿到被拒的签名 URL,把拒绝页写进 mp4 文件,退出码 0。
修法不是"教模型小心",而是**把这一步从模型手里拿走**。

签名 URL 无论下载成没成功都被摘掉:

`tools/flux3_video_tool.py:468-489 @ 863e313`

```python
    result = details.get("result")
    url = result.get("sample") if isinstance(result, dict) else None
    if not isinstance(url, str) or not url.strip():
        return raw

    # Dropped whether or not the save succeeds. A retry re-polls, which mints a
    # fresh URL, so nothing is lost by not handing this one to the model.
    result.pop("sample", None)

    try:
        target, size = await _download_video(url.strip(), save_to, started)
    except Exception as exc:
        payload["result"] = (
            f"The clip finished but saving it failed: {type(exc).__name__}: {exc}. "
            "Poll this job again to retry the download; the job itself is unaffected."
        )
        return json.dumps(payload, ensure_ascii=False)

    details["saved_path"] = str(target)
    details["saved_bytes"] = size
    payload["result"] = _delivery_lead_in(target) + str(payload.get("result") or "")
    return json.dumps(payload, ensure_ascii=False)
```

下载本身:**SSRF 防护 + `.part` 临时名 + 最小字节数校验 + 失败即删**。

`tools/flux3_video_tool.py:511-545 @ 863e313`

```python
async def _download_video(url: str, save_to, started: float) -> tuple:
    """Stream the clip to disk, returning (path, bytes).

    SSRF-guarded, for the same reason the upload PUT is: this URL comes from
    the vendor by way of the gateway, and it is fetched from the user's own
    machine. Real result URLs are public CDN objects, which the guard allows.
    """
    import httpx

    from tools.url_safety import create_ssrf_safe_async_client

    target = _resolve_destination(save_to, _filename_from_url(url))
    # Written under a .part name and renamed only once it is complete and
    # plausible, so a failed download can never leave something that looks like
    # a playable file behind.
    partial = target.with_name(target.name + ".part")
    timeout = httpx.Timeout(_DOWNLOAD_CONNECT_TIMEOUT_SECONDS, read=_download_read_timeout(started))

    try:
        async with create_ssrf_safe_async_client(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with partial.open("wb") as handle:
                    async for chunk in response.aiter_bytes():
                        handle.write(chunk)

        size = partial.stat().st_size
        if size < _MIN_PLAUSIBLE_VIDEO_BYTES:
            raise ValueError(f"the download returned only {size} bytes, which is not a video")
        partial.replace(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
```

`tools/flux3_video_tool.py:416-421 @ 863e313`

```python
# A rejection page is a few hundred bytes of XML; a clip is megabytes. Anything
# smaller than this is not the video, whatever the HTTP status said.
_MIN_PLAUSIBLE_VIDEO_BYTES = 64 * 1024
# Enough collision suffixes to be useful, few enough to fail fast if something
# is generating files in a loop.
_MAX_FILENAME_ATTEMPTS = 50
```

下载的读超时**从整通调用剩余预算里现算**,并且明确禁止向上钳位:

`tools/flux3_video_tool.py:424-438 @ 863e313`

```python
def _download_read_timeout(started: float) -> float:
    """What is left of the call for a download, never more than the ceiling.

    Without this the download's own generous timeout outlives the agent's
    per-tool ceiling, and the "saving failed, poll again to retry" answer below
    is never reached: the bridge kills the call first and the model is told
    only "TimeoutError", with no indication the clip exists and is one poll
    away.

    Must not invent time past what remains: clamping upward used to schedule a
    download the outer ``asyncio.wait_for`` then cancelled, answering with a
    false ``_still_generating`` while the job was already Ready.
    """
    left = _CALL_BACKSTOP_SECONDS - (time.monotonic() - started) - _DOWNLOAD_GRACE_SECONDS
    return max(0.0, min(_DOWNLOAD_READ_TIMEOUT_SECONDS, left))
```

文件名从 URL 派生,但**厂商可控的路径段要重写字符集**:

`tools/flux3_video_tool.py:548-555 @ 863e313`

```python
def _filename_from_url(url: str) -> str:
    from pathlib import PurePosixPath
    from urllib.parse import unquote, urlsplit

    name = PurePosixPath(unquote(urlsplit(url).path)).name
    # The path segment is vendor-controlled, so keep only a plain filename.
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).lstrip(".")[:120]
    return name or "flux3-video.mp4"
```

**永不覆盖已有文件**:

`tools/flux3_video_tool.py:616-624 @ 863e313`

```python
def _free_path(candidate):
    """`name.mp4` -> `name-2.mp4` -> `name-3.mp4` … so nothing is clobbered."""
    if not candidate.exists():
        return candidate
    for suffix in range(2, _MAX_FILENAME_ATTEMPTS + 2):
        sibling = candidate.with_name(f"{candidate.stem}-{suffix}{candidate.suffix}")
        if not sibling.exists():
            return sibling
    raise ValueError(f"could not find a free filename next to {candidate}")
```

#### 2.4.5 落盘位置随"交付面"而变

`tools/flux3_video_tool.py:576-596 @ 863e313`

```python
def _default_directory():
    """Where a clip lands when the caller named no location.

    On a messaging platform the user has no filesystem — the only way they
    ever see the clip is as an attachment — so it goes to the gateway's own
    video cache, which is an unconditionally allowed delivery root. Downloads
    is not: an operator running HERMES_MEDIA_DELIVERY_STRICT=1 delivers only
    from the cache roots, so a clip saved to Downloads there is dropped on the
    way out and the user is shown a reply with nothing attached.
    """
    from pathlib import Path

    if _delivers_as_an_attachment():
        try:
            from hermes_constants import get_hermes_dir

            return get_hermes_dir("cache/videos", "video_cache")
        except Exception:
            logger.debug("Could not resolve the video cache dir; using Downloads", exc_info=True)
    downloads = Path.home() / "Downloads"
    return downloads if downloads.is_dir() else Path.cwd()
```

而"是不是聊天面"要问共享分类器,不能自己判断:

`tools/flux3_video_tool.py:558-573 @ 863e313`

```python
def _delivers_as_an_attachment() -> bool:
    """True on a surface where the clip is received rather than opened off disk.

    Deferred to the shared classifier so this tool cannot drift from the rest
    of the codebase about what counts as a chat channel. It matters here that
    the API server and webhooks are *not* one: they carry a platform value but
    no attachment channel, and neither strips an unfulfilled MEDIA: tag out of
    the reply, so treating them as messaging puts the literal tag in front of
    the caller.
    """
    try:
        from gateway.session_context import session_is_messaging_surface

        return session_is_messaging_surface()
    except Exception:
        return False
```

交付话术:在聊天面上,**把那一行 `MEDIA:` 标签原样写好交给模型抄**,而不是描述它:

`tools/flux3_video_tool.py:492-508 @ 863e313`

```python
def _delivery_lead_in(target) -> str:
    """Opens the result text, ahead of the gateway's own delivery guidance.

    On a messaging platform the tag is spelled out rather than described. The
    model has to reproduce this path exactly or the file is not sent, and the
    reply is published either way — the tag is stripped from the text whether
    or not it named a real file, so a wrong path reads to the user as a
    message that simply forgot the attachment. Handing over the finished line
    removes the step where that goes wrong; only this side knows the path.
    """
    if _delivers_as_an_attachment():
        return (
            f"Saved to {target}. To deliver it, copy the next line into your reply exactly as "
            f"written, alone on its own line, with nothing added around it:\n"
            f"MEDIA:{target}\n"
        )
    return f"Saved to {target}. "
```

而且 `bfl_flux3_get_result` 被登记进网关的"模型忘了写 MEDIA 标签时自动补"名单:

`gateway/run.py:1494-1503 @ 863e313`

```python
# Tool results can contain literal MEDIA: examples in docs, logs, or other
# ordinary outputs. Only tools that intentionally create deliverable media
# artifacts should be eligible for automatic append when the model omits them
# from the final gateway reply.
_AUTO_APPEND_MEDIA_TOOL_NAMES = {
    "text_to_speech",
    "text_to_speech_tool",
    "image_generate",
    "bfl_flux3_get_result",
}
```

#### 2.4.6 可见性门:登录即可见,授权由服务器裁决

`tools/flux3_video_tool.py:804-825 @ 863e313`

```python
def check_bfl_requirements() -> bool:
    """Visible to anyone signed in to Nous; the gateway rules on the rest.

    No entitlement check. What an account may generate — plan, credits, per
    account limits — is the gateway's decision, and it refuses with a reason
    written for the model to act on; deciding it a second time here can only
    disagree with the server and hide the tools from someone entitled to them.

    A sign-in is still required, because the gateway takes a Nous bearer and
    nothing else: with no credential every call could only ever answer "sign
    in", so the six schemas would be pure cost on every API call.

    Stays a pair of file reads — no portal probe, no OAuth refresh. Behind the
    registry's 30s cache this still runs on every CLI start, gateway session
    and cron tick.
    """
    try:
        if _endpoints() is None:
            return False
        return _has_nous_credential()
    except Exception:
        return False
```

`tools/flux3_video_tool.py:778-791 @ 863e313`

```python
def _has_nous_credential() -> bool:
    """True when a Nous bearer is on hand, without spending a refresh to learn it.

    Two lookups, because the transport itself has two.
    ``peek_nous_access_token`` covers the env override and the active store's
    cached token. A profile that was never logged into separately has neither,
    and reads the credential from the global-root ``auth.json`` — the same
    fallback ``resolve_nous_access_token`` takes when the transport refreshes.
    Probing only the first would hide the tools from a profile whose calls
    would have gone through perfectly well.

    Neither lookup validates or refreshes the token: an expired credential is
    the gateway's 401 to report, and that answer already asks for a sign-in.
    """
```

**可迁移原则**:`check_fn` 是一个**每次 CLI 启动 / 每个网关会话 / 每个 cron tick 都跑**的热路径
(registry 有 30s 缓存),所以它只能做文件读,不能做网络探测。
"能不能用"由本地凭据判断,"允不允许用"交给服务器在拒绝里说明。

#### 2.4.7 6 个工具的注册与共享 schema 片段

`tools/flux3_video_tool.py:1185-1194 @ 863e313`

```python
registry.register(
    name="bfl_flux3_text_to_video",
    toolset=_TOOLSET,
    schema=TEXT_TO_VIDEO_SCHEMA,
    handler=_handle_text_to_video,
    check_fn=check_bfl_requirements,
    requires_env=[],
    is_async=True,
    emoji="🎬",
)
```

六个 mode 的 handler 极薄,差别只在"要不要消毒媒体字段":

`tools/flux3_video_tool.py:646-673 @ 863e313`

```python
async def _submit(mode: str, args: dict) -> str:
    endpoints = _endpoints()
    if endpoints is None:
        return _error("BFL video generation is not available in this build.")
    return await _call_gateway("POST", f"{endpoints['base_url']}/generations", _submit_args(mode, args))


async def _handle_text_to_video(args: dict, **kwargs) -> str:
    return await _submit("text_to_video", _without_media(args))


async def _handle_image_to_video(args: dict, **kwargs) -> str:
    try:
        prepared = await _prepare_media(args, kwargs.get("task_id"))
    except ValueError as exc:
        return _error(str(exc))
    return await _submit("image_to_video", prepared)


async def _handle_keyframes_to_video(args: dict, **kwargs) -> str:
    images = (args or {}).get("input_images")
    if not isinstance(images, list) or not images:
        return _error("input_images must be a non-empty list of 1-10 images (local paths or URLs).")
    try:
        prepared = await _prepare_media(args, kwargs.get("task_id"))
    except ValueError as exc:
        return _error(str(exc))
    return await _submit("keyframes_to_video", prepared)
```

参数**原样转发**,校验交给服务器:

`tools/flux3_video_tool.py:635-643 @ 863e313`

```python
def _submit_args(mode: str, args: dict) -> dict:
    """The wire body: the model's arguments, minus Nones, plus our mode.

    Arguments pass through as the model gave them; the gateway owns validation
    and the translation onto the vendor's own fields.
    """
    body = {k: v for k, v in dict(args or {}).items() if v is not None}
    body["mode"] = mode
    return body
```

schema 用 `additionalProperties: False`(与 `video_generate` 相反):

`tools/flux3_video_tool.py:909-915 @ 863e313`

```python
    "parameters": {
        "type": "object",
        "properties": _shared_submit_properties(),
        "required": ["prompt"],
        "additionalProperties": False,
    },
}
```

一条很有意思的**跨参数约束写进了描述里**(JSON Schema 表达不了):

`tools/flux3_video_tool.py:964-975 @ 863e313`

```python
            "keyframe_indices": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0, "maximum": 480},
                "minItems": 1,
                "maxItems": 10,
                "description": (
                    "One unique non-negative frame index per image (24fps). Each must be at most "
                    'duration×24, so set an explicit duration rather than "auto" whenever you pin '
                    'indices — "auto" resolves to 5, 10, 15 or 20 seconds and an index past the '
                    "length it picks is rejected."
                ),
            },
```

#### 2.4.8 提示词指南本身就是一个工具

`tools/flux3_video_tool.py:1043-1052 @ 863e313`

```python
PROMPTING_GUIDE_SCHEMA = {
    "name": "bfl_flux3_prompting_guide",
    "description": (
        "Read this before your first FLUX 3 generation. The prompting and grounding guide: how "
        "to research a subject so it renders as itself, how to assemble a prompt, which generate "
        "tool fits, and how to save and deliver the finished clip. Takes no arguments and spends "
        "no generation budget."
    ),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}
```

指南内容里最值得记的一段——**它在教模型"不要自己等"**:

`tools/flux3_video_tool.py:1149-1155 @ 863e313`

```
The waiting is not yours to do. bfl_flux3_get_result takes the pause itself
while a job is still running, so one call can occupy several minutes and comes
back within seconds of the job finishing. If it returns still generating, just
call it again — no sleeping, no interval to judge, nothing to time.

A job survives client restarts: re-poll the same id rather than resubmitting,
which would only spend your budgets on duplicate work.
```

以及交付环节最常见的失败形态:

`tools/flux3_video_tool.py:1165-1174 @ 863e313`

```
Then deliver that file so the clip plays inline. Which markup plays inline is the
host's decision, so check your system prompt or platform instructions and use
exactly the form they give; the common ones are a MEDIA: tag alone on its own
line and a markdown embed. Two things break it. Write the real absolute path,
with ~ expanded. And keep the markup plain: wrapping it in bold, backticks or a
code fence, or rewriting it as a [link](path), turns an inline player into
literal text or a click-target. That is the most common way this step fails,
and it reads as success because the filename is on screen. Where the
instructions call for no delivery markup, or the host has no such mechanism,
follow them and state the absolute path in plain text.
```

指南里刻意**不放策略数字**,理由写在节标题注释上:

`tools/flux3_video_tool.py:1055-1058 @ 863e313`

```python
# ---------------------------------------------------------------------------
# Pinned prompting guide (methodology only — policy numbers such as waits and
# limits arrive live in the gateway's tool responses, so they cannot drift)
# ---------------------------------------------------------------------------
```

### 2.5 `tools/xai_video_tools.py`(209 行)—— 并列还是特例?

**答案:是"统一面的特例补丁",不是并列的第三套系统。** 三条证据:

**(1) toolset 归属**:它注册在 `video_gen` 下,和 `video_generate` 同一个 toolset。

`tools/xai_video_tools.py:189-198 @ 863e313`

```python
registry.register(
    name="xai_video_edit",
    toolset="video_gen",
    schema=XAI_VIDEO_EDIT_SCHEMA,
    handler=_handle_xai_video_edit,
    check_fn=_check_xai_video_requirements,
    requires_env=[],
    is_async=False,
    emoji="video",
)
```

`toolsets.py:146-156 @ 863e313`

```python
    "video_gen": {
        "description": (
            "Video generation tools. Single ``video_generate`` tool covers "
            "text-to-video (prompt only) and image-to-video (prompt + "
            "image_url), plus reference-to-video. Provider-specific edit/"
            "extend workflows may appear as separate tools. Configure via "
            "``hermes tools`` → Video Generation."
        ),
        "tools": ["video_generate", "xai_video_edit", "xai_video_extend"],
        "includes": []
    },
```

**(2) 自我描述**:两个 schema 都明说"因为 edit 是 provider 特有,所以从 `video_generate` 里分出来"。

`tools/xai_video_tools.py:70-77 @ 863e313`

```python
XAI_VIDEO_EDIT_SCHEMA: Dict[str, Any] = {
    "name": "xai_video_edit",
    "description": (
        "Edit an existing video with xAI Imagine. This is separate from "
        "`video_generate` because video editing is provider-specific. "
        "`video_url` must be the public HTTPS MP4 URL from a prior Imagine "
        "result (`video` or `public_url` on files-cdn)."
    ),
```

**(3) 可见性门是"配置成 xai 才出现"**,即它是活跃后端的附属工具:

`tools/xai_video_tools.py:18-28 @ 863e313`

```python
def _configured_for_xai_video() -> bool:
    try:
        cfg = load_config()
    except Exception:
        return False
    section = cfg.get("video_gen") if isinstance(cfg, dict) else None
    return isinstance(section, dict) and section.get("provider") == "xai"


def _check_xai_video_requirements() -> bool:
    return _configured_for_xai_video() and has_xai_video_credentials()
```

而 BFL 那套是自己独立的 toolset `bfl`,和 `video_gen` 无任何交集:

`toolsets.py:158-166 @ 863e313`

```python
    "bfl": {
        "description": (
            "Black Forest Labs FLUX 3 video generation through the Nous tool "
            "gateway: per-mode submit tools (text, image, keyframes, "
            "continuation), a poll tool, and a prompting guide. Generations "
            "take minutes, so submit returns a job id and the model polls for "
            "the result."
        ),
        "tools": [
```

#### 2.5.1 一个值得注意的耦合:工具层**模块级**导入插件

`tools/xai_video_tools.py:9-15 @ 863e313`

```python
from hermes_cli.config import load_config
from plugins.video_gen.xai import (
    has_xai_video_credentials,
    run_xai_video_edit,
    run_xai_video_extend,
)
from tools.registry import registry, tool_error
```

`tools/*.py` 是被自动发现并 import 的(AST 扫顶层 `registry.register` 调用):

`tools/registry.py:100-106 @ 863e313`

```python
        else:
            registers = _module_registers_tools(path)
            cache_dirty = True
        fresh_cache[abs_path] = [stat_key[0], stat_key[1], registers]
        if registers:
            module_names.append(f"tools.{path.stem}")
```

**后果**:`plugins/video_gen/xai/__init__.py`(925 行,顶层 `import httpx`)会在**每次工具发现时被导入**,
与该插件是否 enabled 无关。插件的 `register(ctx)` 不会被调用(所以 provider 不会进注册表),
但模块被 import 了。这打破了"每个后端都是插件、按需加载"的整洁性。
另一面:`plugins/video_gen/fal` 和 `deepinfra` 没有对应的 tools 文件,不受影响。

#### 2.5.2 URL 校验只做协议前缀

`tools/xai_video_tools.py:60-67 @ 863e313`

```python
def _normalize_public_video_url(video_url: Any) -> Optional[str]:
    """Require a public HTTPS MP4 URL (``http``/``https`` only)."""
    cleaned = _clean_string(video_url)
    if not cleaned:
        return None
    if cleaned.lower().startswith(("http://", "https://")):
        return cleaned
    return None
```

docstring 说 "HTTPS MP4",实现只校验 `http://` / `https://` 前缀,不校验扩展名,也接受明文 http。
属"文档字符串比实现严"的小出入(记 §5 ■-4)。

#### 2.5.3 handler 结构

`tools/xai_video_tools.py:164-186 @ 863e313`

```python
def _handle_xai_video_extend(args: Dict[str, Any], **_kw: Any) -> str:
    prompt = _clean_string(args.get("prompt"))
    video_url = _normalize_public_video_url(args.get("video_url"))
    model = _clean_string(args.get("model"))
    duration = _coerce_int(args.get("duration"))

    if not prompt:
        return tool_error("prompt is required for xAI video extend")
    if not video_url:
        return tool_error(
            "video_url must be a public HTTPS MP4 URL (the `video`/`public_url` "
            "from a prior Imagine result)"
        )
    if not _configured_for_xai_video():
        return _provider_not_configured_error()

    result = run_xai_video_extend(
        prompt=prompt,
        video_url=video_url,
        duration=duration,
        model=model,
    )
    return json.dumps(result)
```

注意 `check_fn` 已经查过一次配置,handler 里又查一次 —— **纵深校验**:
`check_fn` 只影响 schema 是否下发,长会话里配置可能中途改掉。

---

## 3. 配置项与环境变量

### 3.1 `video_gen` 根键:合法但**不在 DEFAULT_CONFIG 里**

`hermes_cli/config.py:1861 @ 863e313`

```python
    "video_gen",         # video-generation provider config (agent/video_gen_registry.py)
```

它在 `_EXTRA_KNOWN_ROOT_KEYS` 里,注释说明了这批键的性质:

`hermes_cli/config.py:1852-1856 @ 863e313`

```python
_EXTRA_KNOWN_ROOT_KEYS = {
    "custom_providers",  # legacy list form; modern equivalent is providers: {}
    "fallback_model",    # optional single dict or chain list; omitted when disabled
    "mcp_servers",       # MCP server definitions written by setup/tools flows
    # Roots read from the raw user YAML (or written by our own flows) that are
```

**含义**:`video_gen` 没有默认值,配置文件里默认根本没有这一节;
只有走过 `hermes tools` → Video Generation 才会被写出来。
这解释了 §2.2.2 里"未配置时按可用性单选"这条兜底为什么必要。

### 3.2 本簇涉及的配置键全表

```verify
cd /home/user/hermes-agent && grep -rn "video_gen\." --include=*.py --include=*.md --include=*.ts --include=*.tsx . 2>/dev/null | grep -v "^./tests/" | grep -oE "video_gen\.[a-z_]+" | sort | uniq -c | sort -rn
```

实测(排除 tests/):`video_gen.provider` 14 次、`video_gen.model` 7 次、`video_gen.xai` 2 次、
`video_gen.use_gateway` 1 次、`video_gen.managed_by_nous` 1 次、`video_gen.fal` 1 次。

| 键 | 默认 | 定义/读取处 | 作用 |
|---|---|---|---|
| `video_gen.provider` | 无(不存在) | `agent/video_gen_registry.py:92` 的 `raw = section.get("provider")` | 选活跃后端;写错即失败关闭 |
| `video_gen.model` | 无 | `tools/video_generation_tool.py:188` 的 `value = _read_video_gen_section().get("model")` | 默认模型族 |
| `video_gen.use_gateway` | False | `tools/tool_backend_helpers.py:278` 的 `def prefers_gateway(config_section: str) -> bool:` | 是否强制走 Nous 托管网关 |
| `video_gen.fal.model` | 无 | `plugins/video_gen/fal/__init__.py:25` 的 `3. ``video_gen.fal.model`` in ``config.yaml``` | 后端内的模型族(优先于 `video_gen.model`) |
| `video_gen.xai.storage.enabled` | True | `tools/xai_http.py:186` 的 `enabled = _coerce_bool(storage.get("enabled"), True)` | xAI 存储:出永久 public URL |
| `video_gen.xai.storage.public_url` | True | `tools/xai_http.py:187` 的 `public_url = _coerce_bool(storage.get("public_url"), True)` | 是否要 public URL |
| `video_gen.xai.storage.expires_after` | None(不过期) | `tools/xai_http.py:188` 的 `expires_after = _coerce_expires_after(storage.get("expires_after"))` | 保留期(秒) |

`tools/xai_http.py:165-179 @ 863e313`

```python
def read_xai_imagine_storage_config(section_name: str) -> Dict[str, Any]:
    """Read storage settings for xAI Imagine under image_gen/video_gen config.

    Supported config shape:

        image_gen:
          xai:
            storage:
              enabled: true
              public_url: true
              expires_after: null     # omit for permanent public URLs

    The same shape is accepted under ``video_gen.xai.storage``. Storage is on
    by default so xAI returns permanent public URLs instead of short-lived CDN URLs.
    """
```

### 3.3 环境变量

| 变量 | 用途 | 锚点 |
|---|---|---|
| `FAL_KEY` | FAL 直连凭据 | R8A 资产 `data/r8a-env-vars.tsv` 第 73 行(唯一在册的视频相关变量) |
| `DEEPINFRA_API_KEY` | DeepInfra 凭据 | `plugins/video_gen/deepinfra/__init__.py:29` 的 `_env_key = "DEEPINFRA_API_KEY"` |
| `XAI_API_KEY` | xAI 凭据(或 Grok OAuth) | `plugins/video_gen/xai/__init__.py:45` 的 `DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"` 同节 |
| `FAL_VIDEO_MODEL` | FAL 模型族覆盖 | `plugins/video_gen/fal/__init__.py:24` 的 `2. ``FAL_VIDEO_MODEL`` env var` |
| `<NAME>_BASE_URL` | OpenAI 兼容后端的 base_url 覆盖 | `agent/video_gen_provider.py:446` 的 `override = os.environ.get(f"{self.name.upper()}_BASE_URL", "").strip()` |
| `HERMES_MEDIA_DELIVERY_STRICT` | 严格交付根;影响 flux3 默认落盘位置 | `tools/flux3_video_tool.py:582` 的 `is not: an operator running HERMES_MEDIA_DELIVERY_STRICT=1 delivers only` |
| `TOOL_GATEWAY_URL` / `TOOL_GATEWAY_DOMAIN` | Nous 工具网关地址(BFL 用) | `tools/managed_tool_gateway.py:235` 的 `# build_vendor_gateway_url (honors TOOL_GATEWAY_URL / TOOL_GATEWAY_DOMAIN).` |

`agent/video_gen_provider.py:443-447 @ 863e313`

```python
    def _base_url(self) -> str:
        import os

        override = os.environ.get(f"{self.name.upper()}_BASE_URL", "").strip()
        return override or self._default_base_url
```

**注意 `<NAME>_BASE_URL` 是个"隐式"环境变量族**:变量名由 `provider.name` 大写拼出来,
所以任何新插件都自动多一个环境变量,而它不会出现在任何静态清单里(R8A 的 151 条静态列表抓不到它)。

### 3.4 网关端点构造(BFL)

`tools/managed_tool_gateway.py:238-245 @ 863e313`

```python
def managed_vendor_base_path(vendor: str) -> str:
    """Base path for a managed vendor's REST routes on the gateway host."""
    return f"/api/{vendor}"


def managed_vendor_upload_path(vendor: str) -> str:
    """Media upload endpoint for a managed vendor, on the same host."""
    return f"/api/uploads/{vendor}"
```

`tools/flux3_video_tool.py:49-50 @ 863e313`

```python
_TOOLSET = "bfl"
_VENDOR = "bfl"
```

即 BFL 的两个端点是 `{origin}/api/bfl/generations` 与 `{origin}/api/uploads/bfl`。

### 3.5 toolset 默认关闭 + "刚发布的 toolset"回填

`hermes_cli/tools_config.py:103-106 @ 863e313`

```python
    ("video",           "🎬 Video Analysis",            "video_analyze (requires video-capable model)"),
    ("image_gen",       "🎨 Image Generation",          "image_generate"),
    ("video_gen",       "🎬 Video Generation",          "video_generate (text/image/reference)"),
    ("bfl",             "🎬 BFL FLUX 3 Video",          "bfl_flux3_*"),
```

`hermes_cli/tools_config.py:156 @ 863e313`

```python
_DEFAULT_OFF_TOOLSETS = {"homeassistant", "spotify", "discord", "discord_admin", "video", "video_gen", "x_search", "a2a"}
```

**注意:`video_gen` 默认关闭,`bfl` 不在这个集合里** —— 但 `bfl` 走的是另一条"刚发布则回填开启"的路径:

`hermes_cli/tools_config.py:2180-2185 @ 863e313`

```python
#: Not gated on a Nous sign-in here: the six ``bfl_flux3_*`` tools carry
#: ``check_fn=check_bfl_requirements``, so an enabled toolset still ships zero
#: schemas to a user with no Nous credential — the same split Home Assistant
#: uses. Probing the portal from this path would put a network call on every
#: CLI start, gateway session and cron tick.
_RECENTLY_SHIPPED_TOOLSETS = frozenset({"bfl"})
```

---

## 4. 测试作为行为规格

### 4.1 环境记录(CLAUDE.md 要求)

```verify
/home/user/hermes-venv/bin/pip list | tail -n +3 | wc -l
ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l
```

实测均为 **87**(`[dev]` extra + aiohttp 3.14.1 + brotlicffi 1.2.0.1),与 CLAUDE.md 记录一致。

### 4.2 本簇测试文件清单

| 文件 | 行数 | 覆盖对象 |
|---|---|---|
| `tests/tools/test_flux3_video_tool.py` | 1043 | flux3 全部(gating / submit / poll / 保存 / 媒体 / 路径判定 / schema) |
| `tests/tools/test_video_generation_tool_surface_matrix.py` | 236 | 端到端路由矩阵(config→registry→provider→出网) |
| `tests/hermes_cli/test_video_gen_picker.py` | 183 | `hermes tools` 选择器 |
| `tests/tools/test_video_generation_dynamic_schema.py` | 105 | 动态 schema 构建 |
| `tests/tools/test_video_generation_dispatch.py` | 96 | `video_generate` 调度错误路径 |
| `tests/agent/test_video_gen_registry.py` | 84 | 注册表 |
| `tests/gateway/test_video_context_note.py` | 50 | 入站视频附件的上下文提示(与本簇相邻,非生成路径) |

插件侧另有 `tests/plugins/video_gen/`(651 行,4 文件),不在本轮 5 文件范围内,仅作参照。

### 4.3 实跑结果

```verify
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/tools/test_flux3_video_tool.py tests/tools/test_video_generation_dispatch.py tests/tools/test_video_generation_dynamic_schema.py tests/agent/test_video_gen_registry.py
```

实测:**4 files, 84 tests passed, 0 failed**(flux3 75 ✓、dynamic_schema 2 ✓、dispatch 3 ✓、registry 4 ✓)。

```verify
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/tools/test_video_generation_tool_surface_matrix.py
```

实测:**8 failed, 1 passed**。逐条诊断如下。

### 4.4 8 条失败的诊断:缺可选依赖 `fal-client`,不是代码缺陷

失败的 8 条全部是 FAL 相关(6 条参数化的 `test_fal_text_only_routes_to_text_endpoint`
+ `test_tool_model_arg_overrides_config` + `test_tool_model_arg_with_image_url_routes_to_override_image_endpoint`);
唯一通过的 1 条是 xAI 的。

用 `-l`(showlocals)拿到真正的失败内容:

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python -m pytest tests/tools/test_video_generation_tool_surface_matrix.py::test_tool_model_arg_overrides_config -x -q -l 2>&1 | grep -A5 "^result"
```

实测输出:

```console
result     = {'success': False, 'video': None, 'error': 'fal_client Python package not installed (pip install fal-client)', 'error_type': 'missing_dependency', ...}
```

**根因链(逐环已核)**:

1. 测试把假的 `fal_client` 塞进 `sys.modules`
   (`tests/tools/test_video_generation_tool_surface_matrix.py:61` 的 `monkeypatch.setitem(__import__("sys").modules, "fal_client", fake_fal)`)。
2. 但插件不是直接 `import fal_client`,而是先过 lazy_deps:

`tools/fal_common.py:44-52 @ 863e313`

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

3. `ensure("image.fal")` 查的是 **distribution 元数据**,不是 `sys.modules`:

`tools/lazy_deps.py:829-832 @ 863e313`

```python
def feature_missing(feature: str) -> tuple[str, ...]:
    """Return the subset of specs for ``feature`` not currently installed."""
    return tuple(s for s in feature_specs(feature) if not _is_satisfied(s))
```

`tools/lazy_deps.py:190 @ 863e313`

```python
    "image.fal": ("fal-client==0.13.1",),
```

`tools/lazy_deps.py:602-609 @ 863e313`

```python
    pkg = _pkg_name_from_spec(spec)
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:
        return False
    try:
        installed = version(pkg)
    except PackageNotFoundError:
```

4. `fal-client` 属于 `fal` extra,不在 `[dev]` 里:

`pyproject.toml:167 @ 863e313`

```toml
fal = ["fal-client==0.13.1"]
```

```verify
/home/user/hermes-venv/bin/pip show fal-client
```

实测:`WARNING: Package(s) not found: fal-client`。

**判定**:与 CLAUDE.md 里 `aiohttp` 那条同型 —— 平台/可选 extra 缺失导致的失败,**不是代码缺陷、不是容器缺陷**。
但和 aiohttp 那条有一处不同值得记:aiohttp 缺失表现为**收集期 ImportError**(一眼可辨),
而这里表现为**断言失败**(`assert False is True`),而且这些用例**没有任何 skip 守卫**。
一个只装 `[dev]` 的人会看到 8 条"路由测试挂了",而真实原因是没装 fal-client。记 §5 ■-5。

### 4.5 从测试里读出来的行为规格(挑最有信息量的)

**(a) 轮询预算必须留在 300s 天花板之下** ——测试把这条不变式钉死了:

`tests/tools/test_flux3_video_tool.py:606-611 @ 863e313`

```python
    def test_the_pacing_stays_clear_of_the_agents_per_tool_ceiling(self):
        # The whole point of the two bounds: a clip finishing on the last look
        # still has to be downloaded inside the backstop, and the backstop has
        # to answer before model_tools' async bridge abandons the tool at 300s.
        assert _DEFAULT_POLL_BUDGET_SECONDS < _DEFAULT_CALL_BACKSTOP_SECONDS
        assert _DEFAULT_CALL_BACKSTOP_SECONDS < 300.0
```

**(b) 签名 URL 绝不进模型上下文**:

`tests/tools/test_flux3_video_tool.py:622-645 @ 863e313`

```python
    def test_ready_saves_the_clip_and_never_returns_the_signed_url(self, tmp_path):
        # The signed URL is a bearer credential for the clip and it used to be
        # re-keyed into a shell command by hand, dropping characters. Neither
        # can happen if the model never sees it.
        signed = "https://cdn.example/container/flux3-clip.mp4?sig=abc%2Bdef%3D&se=2026"
        response = _FakeResponse(200, {"id": "bfl_job_1", "status": "Ready", "result": {"sample": signed}, "guidance": "Deliver the saved file."})

        with _fake_download(b"x" * (128 * 1024)) as fetched:
            parsed, _requests = _call(
                flux3._handle_get_result,
                {"id": "bfl_job_1", "save_to": str(tmp_path)},
                response,
            )

        saved = tmp_path / "flux3-clip.mp4"
        assert saved.read_bytes() == b"x" * (128 * 1024)
        assert parsed["details"]["saved_path"] == str(saved)
        assert parsed["details"]["result"].get("sample") is None
        assert signed not in json.dumps(parsed)
        # The gateway still owns the delivery wording; the client only supplies
        # the path it cannot know.
        assert parsed["result"].startswith(f"Saved to {saved}.")
        assert "Deliver the saved file." in parsed["result"]
        assert fetched == [signed]
```

**(c) 下载超时不得超过兜底(且不得向上钳位)**:

`tests/tools/test_flux3_video_tool.py:613-620 @ 863e313`

```python
    def test_download_timeout_never_outlives_the_backstop(self):
        # Near the end of the call, remaining budget after grace is a few
        # seconds. Clamping that up used to schedule a download the outer
        # wait_for then cancelled, answering "still generating" for a Ready job.
        started = time.monotonic() - (
            flux3._CALL_BACKSTOP_SECONDS - flux3._DOWNLOAD_GRACE_SECONDS - 2.0
        )
        assert flux3._download_read_timeout(started) <= 2.0 + 0.5  # clock noise only
```

**(d) 永不覆盖**:

`tests/tools/test_flux3_video_tool.py:647-655 @ 863e313`

```python
    def test_ready_never_overwrites_an_existing_file(self, tmp_path):
        (tmp_path / "flux3-clip.mp4").write_bytes(b"an earlier clip")
        response = _FakeResponse(200, {"id": "bfl_job_1", "status": "Ready", "result": {"sample": "https://cdn.example/x/flux3-clip.mp4?sig=a"}, "guidance": "g"})

        with _fake_download(b"y" * (128 * 1024)):
            parsed, _requests = _call(flux3._handle_get_result, {"id": "bfl_job_1", "save_to": str(tmp_path)}, response)

        assert parsed["details"]["saved_path"] == str(tmp_path / "flux3-clip-2.mp4")
        assert (tmp_path / "flux3-clip.mp4").read_bytes() == b"an earlier clip"
```

**(e) 注册表:写错 provider 名必须失败关闭**:

`tests/agent/test_video_gen_registry.py:75-84 @ 863e313`

```python
    def test_unknown_explicit_config_fails_closed(self, tmp_path, monkeypatch):
        """A typo must not silently route a paid request to another backend."""
        import yaml

        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "config.yaml").write_text(
            yaml.safe_dump({"video_gen": {"provider": "ghost"}})
        )
        video_gen_registry.register_provider(_FakeProvider("only"))
        assert video_gen_registry.get_active_provider() is None
```

**(f) 路由矩阵是参数化自发现的**——加一个新 family 自动进矩阵:

`tests/tools/test_video_generation_tool_surface_matrix.py:132-140 @ 863e313`

```python
# We parametrize over the catalog so the test discovers new families
# automatically. If someone adds 'sora-2' to FAL_FAMILIES, this matrix
# picks it up — no test changes needed beyond confirming the endpoints.
def _all_fal_families():
    from plugins.video_gen.fal import FAL_FAMILIES
    return list(FAL_FAMILIES.keys())


@pytest.mark.parametrize("family_id", _all_fal_families())
def test_fal_text_only_routes_to_text_endpoint(matrix_env, family_id):
```

**(g) 文本模式绝不泄露图片键**(这是"统一面路由"最容易出的错):

`tests/tools/test_video_generation_tool_surface_matrix.py:160-163 @ 863e313`

```python
    # Payload must NOT contain any image-shaped key
    payload = fal_calls[0]["arguments"] or {}
    image_keys = [k for k in payload if "image" in k and "url" in k]
    assert not image_keys, f"{family_id} text-only leaked image keys: {image_keys}"
```

---

## 5. 定案

记号:▲ = 文档与代码矛盾;◇ = 代码有、文档无;■ = 代码缺陷;◎ = 文档成立但显著保守。

### ▲-1 开发者文档把两条"与 image_gen 的差异"说反了

`website/docs/developer-guide/video-gen-provider-plugin.md:12 @ 863e313`

> Video-gen mirrors [Image Generation Provider Plugins](/developer-guide/image-gen-provider-plugin) almost line-for-line — if you've built an image-gen backend, you already know the shape. The main differences: a `capabilities()` method advertising modalities/aspect-ratios/durations, and a routing convention (pass `image_url` to use image-to-video, omit it to use text-to-video — the provider picks the right endpoint internally).

**判定(整句 + 归属标题)**:该句在 `# Building a Video Generation Provider Plugin` 标题下、开篇 `:::tip` 块内,
断言的是"video 相对 image 的**主要差异**"。逐个子句核:

- 子句 A "a `capabilities()` method" 是差异 → **假**。`ImageGenProvider` 有同名方法:

`agent/image_gen_provider.py:143 @ 863e313`

```python
    def capabilities(self) -> Dict[str, Any]:
```

  真正的差异只是**返回的键更多**(image 2 个 vs video 8 个,见 §2.1.1),而不是"多了一个方法"。
- 子句 B "a routing convention (pass `image_url` …)" 是差异 → **假**。image 侧用的是同一套约定,
  且写在它自己的 ABC docstring 里:

`agent/image_gen_provider.py:175-178 @ 863e313`

```python
        Routing: if ``image_url`` (or any ``reference_image_urls``) is
        provided, the provider should route to its image-to-image / edit
        endpoint; otherwise text-to-image. ``image_url`` is the primary
        source image to edit; ``reference_image_urls`` are additional
```

  连它自己的开发者文档也写了同样的东西:

`website/docs/developer-guide/image-gen-provider-plugin.md:116-119 @ 863e313`

> ```python
>     def capabilities(self) -> Dict[str, Any]:
>         # Declare whether this backend supports image-to-image / editing.
>         # The tool layer surfaces this in the dynamic schema so the model
>         # knows when `image_url` is honored. Default (if you omit this) is

**危害**:这句是给"已经写过 image 后端"的读者做迁移导航的。它会让读者去找一个 image 侧没有的方法
(其实有),并以为路由约定是新东西(其实一样)。**两个被点名的"主要差异",一个都不是差异。**

### ▲-2 开发者文档漏掉了 `save_url_video`,并推荐了它专门为之存在的反面做法

`website/docs/developer-guide/video-gen-provider-plugin.md:225-227 @ 863e313`

> ## Where to save artifacts
>
> If your backend returns base64, use `save_b64_video()` to write under `$HERMES_HOME/cache/videos/`. For raw bytes from a follow-up HTTP fetch, use `save_bytes_video()`. Otherwise return the upstream URL directly — the gateway resolves remote URLs on delivery.

**判定(整段 + 归属标题 `## Where to save artifacts`)**:
- 前两句为真(`save_b64_video` / `save_bytes_video` 都在 `agent/video_gen_provider.py:213` 与 `:233`)。
- 第三句 "Otherwise return the upstream URL directly" 与**同一文件里的参考实现直接冲突**:
  仓库唯一那个通用后端 `OpenAICompatibleVideoGenProvider` 明确**不这么做**,它下载落盘,理由就是 URL 会过期:

`agent/video_gen_provider.py:543-547 @ 863e313`

```python
            # Resolve the output. Providers expose it either as a delivery URL in
            # the job's ``data`` list (DeepInfra, FAL-style) or only via the SDK
            # download endpoint (OpenAI/Sora). Download the bytes and save locally
            # so the caller gets a durable file — DeepInfra's delivery URLs in
            # particular are short-lived. Matches plugins/image_gen/deepinfra.
```

- 而这一整节**只字未提 `save_url_video`** —— 正是为这个场景写的那个助手(`agent/video_gen_provider.py:255`)。

**判定结论**:▲(文档给出的做法与仓库参考实现的做法相反),并附带一条 ◇(见 ◇-2)。
第三句后半 "the gateway resolves remote URLs on delivery" 的真伪**未定**,见 §6 移交项 H-R9B-a。

### ▲-3 `video_generate` 的"无后端"错误消息点名了一个不存在的后端,漏了一个存在的

`tools/video_generation_tool.py:259-265 @ 863e313`

```python
    msg = (
        "No video generation backend is configured. Run `hermes tools` → "
        "Video Generation to enable one (xAI, FAL, or Google Veo)."
    )
    return json.dumps(error_response(
        error=msg, error_type="no_provider_configured",
    ))
```

**负结论的搜索面**:全仓(**含 tests**)所有 `*.py`,模式为字面量 `register_video_gen_provider`:

```verify
cd /home/user/hermes-agent && grep -rn "register_video_gen_provider" --include=*.py .
```

实测命中 6 行,其中**实际注册后端的只有 3 处**:`plugins/video_gen/xai/__init__.py:925`、
`plugins/video_gen/deepinfra/__init__.py:90`、`plugins/video_gen/fal/__init__.py:624`;
其余 3 行是 ABC/registry 的 docstring 与 `hermes_cli/plugins.py:737` 的方法定义。
目录侧一致:

```verify
cd /home/user/hermes-agent && ls plugins/video_gen/
```

实测:`deepinfra  fal  xai`(3 个)。

即:**没有 Google 后端**(Veo 3.1 是 FAL 的一个 model family,`plugins/video_gen/fal/__init__.py:17` 的
`    veo3.1        fal-ai/veo3.1                                  /  fal-ai/veo3.1/image-to-video`),
而真实存在的 DeepInfra 没被这条消息提到。这是一条**直接给用户看的**引导语,把人指向一个不存在的选项。
归 ▲(代码里的自述与代码事实矛盾)兼 ■(用户可见文案错误)。

### ◎-1 开发者文档说"三处发现",实为四处(第四处默认关闭)

`website/docs/developer-guide/video-gen-provider-plugin.md:26-31 @ 863e313`

> Hermes scans for video-gen backends in three places:
>
> 1. **Bundled** — `<repo>/plugins/video_gen/<name>/` (auto-loaded with `kind: backend`)
> 2. **User** — `~/.hermes/plugins/video_gen/<name>/` (opt-in via `plugins.enabled`)
> 3. **Pip** — packages declaring a `hermes_agent.plugins` entry point

实际发现流程是四段,第三段是 project plugins:

`hermes_cli/plugins.py:1378-1384 @ 863e313`

```python
        # 3. Project plugins (./.hermes/plugins/)
        if _env_enabled("HERMES_ENABLE_PROJECT_PLUGINS"):
            project_dir = Path.cwd() / ".hermes" / "plugins"
            logger.debug("Scanning project plugins: %s", project_dir)
            project_manifests = self._scan_directory(project_dir, source="project")
            logger.debug("  project: %d manifest(s)", len(project_manifests))
            manifests.extend(project_manifests)
```

`hermes_cli/plugins.py:5-14 @ 863e313`

```python
Discovers, loads, and manages plugins from four sources:

1. **Bundled plugins** – ``<repo>/plugins/<name>/`` (shipped with hermes-agent;
   ``memory/`` and ``context_engine/`` subdirs are excluded — they have their
   own discovery paths)
2. **User plugins**   – ``~/.hermes/plugins/<name>/``
3. **Project plugins** – ``./.hermes/plugins/<name>/`` (opt-in via
   ``HERMES_ENABLE_PROJECT_PLUGINS``)
4. **Pip plugins**     – packages that expose the ``hermes_agent.plugins``
   entry-point group.
```

**判定为 ◎ 而非 ▲**:文档列出的三处**每一处都真实存在且真的被扫**;漏掉的第四处需要
`HERMES_ENABLE_PROJECT_PLUGINS` 显式开启,默认安装下"三处"就是完整答案。
按 CLAUDE.md "字面为真就不是 ▲" 的口径,这属于"成立但保守"。

### ◇-1 整个 `bfl` toolset(6 个工具、1249 行)在 website/docs 里零覆盖

```verify
cd /home/user/hermes-agent && grep -rn "bfl_flux3" --include=*.md --include=*.mdx --include=*.yaml --include=*.yml --include=*.json --include=*.ts --include=*.tsx . | grep -v "^./tests/"
```

实测:**零命中**。搜索面 = 全仓所有 `.md/.mdx/.yaml/.yml/.json/.ts/.tsx`,排除 `tests/`,
模式为字面量 `bfl_flux3`。

工具参考文档里的"当前注册表快照"也只数到 3 个视频工具:

`website/docs/reference/tools-reference.md:11 @ 863e313`

> **Quick counts (current registry):** ~82 tools — 10 browser tools (core) + 2 CDP-gated browser tools, 4 file tools, 4 Home Assistant tools, 7 terminal tools (`terminal`, `process`, plus desktop-GUI-gated `read_terminal`, `close_terminal`, `open_preview`, `read_preview`, `focus_pane`), 2 web tools, 5 Feishu tools, 7 Spotify tools (registered by the bundled `spotify` plugin), 5 Yuanbao tools, 12 kanban tools (registered when the kanban dispatcher spawns the agent), 3 project tools (desktop/GUI sessions), 2 Discord tools, 3 video tools (`video_generate`, `xai_video_edit`, `xai_video_extend`), and a handful of standalone tools (`memory`, `clarify`, `delegate_task`, `execute_code`, `cronjob`, `session_search`, `skill_view`/`skill_manage`/`skills_list`, `text_to_speech`, `image_generate`, `vision_analyze`, `video_analyze`, `todo`, `computer_use`, `x_search`).

toolset 参考文档同样只有 `video_gen` 与 `video` 两行,无 `bfl`:

```verify
cd /home/user/hermes-agent && grep -in "bfl\|flux3" website/docs/reference/toolsets-reference.md
```

实测:零命中。

**判定 ◇**(代码有、文档无)。注意这与 `_RECENTLY_SHIPPED_TOOLSETS = frozenset({"bfl"})`
(`hermes_cli/tools_config.py:2185`)一致 —— bfl 是刚落地的 toolset,文档还没跟上。
但它是**默认会被回填开启**的 toolset,面向用户却零文档,这条值得记。

### ◇-2 `save_url_video` 在开发者文档里完全不存在

见 ▲-2。`agent/video_gen_provider.py:255` 的 `def save_url_video(` 是本簇唯一处理"短命 URL"的公开助手,
`website/docs/developer-guide/video-gen-provider-plugin.md` 的 `## Where to save artifacts` 一节只列了另外两个。

### ◇-3 `_model_override_explicit` 是一条不在任何 schema / ABC 签名里的私有 kwarg

`tools/video_generation_tool.py:342-344 @ 863e313`

```python
    kwargs: Dict[str, Any] = {
        "model": model,
        "_model_override_explicit": bool(model_override),
```

ABC 对 `**kwargs` 的说明是"未来 schema 会暴露的前向兼容参数":

`agent/video_gen_provider.py:192-196 @ 863e313`

```python
        Implementations should return the dict from :func:`success_response`
        or :func:`error_response`. ``kwargs`` may contain forward-compat
        parameters future versions of the schema will expose —
        implementations MUST ignore unknown keys (no TypeError).
        """
```

而它实际承载的是一个**永远不会进 schema 的内部信号**,且被 xAI 插件消费
(`plugins/video_gen/xai/__init__.py:447` 的 `explicit_model=bool(kwargs.get("_model_override_explicit")),`)。
开发者文档的 `generate()` 示例(`website/docs/developer-guide/video-gen-provider-plugin.md:114-128`)
也没提它。第三方插件作者无从得知这个信号存在。

### ■-1 `video_generate` 不在网关的"忘记贴 MEDIA 标签时自动补"名单里,而 `image_generate` 和 `bfl_flux3_get_result` 在

`gateway/run.py:1498-1503 @ 863e313`

```python
_AUTO_APPEND_MEDIA_TOOL_NAMES = {
    "text_to_speech",
    "text_to_speech_tool",
    "image_generate",
    "bfl_flux3_get_result",
}
```

而且 JSON 载荷取路径的字段名单里也没有 `video`:

`gateway/run.py:1557 @ 863e313`

```python
_JSON_MEDIA_TOOL_PATH_FIELDS = ("host_image", "image", "agent_visible_image")
```

`image_generate` 有一条专门的兜底分支(模型忘了写 MEDIA 时从 JSON 里挖路径):

`gateway/run.py:1625-1628 @ 863e313`

```python
        # JSON-payload tools (image_generate) return a local-file path in a
        # known field rather than a MEDIA: tag. Extract it so delivery is
        # deterministic even when the model omits the path from its reply.
        if tool_name == "image_generate" and "MEDIA:" not in content:
```

**现象**:同一条设计(模型在聊天面忘记引用产物 → 用户收到一条没有附件的回复)对 image 和 flux3 都有兜底,
对 `video_generate` 没有。`video_generate` 的产物字段名是 `video`
(`agent/video_gen_provider.py:337-338` 的 `"success": True,` / `"video": video,`),既不在 tool 名单也不在字段名单。

**严重度**:低-中。它只在"模型忘了"时才触发,而工具描述里已经要求模型自己引用
(`tools/video_generation_tool.py:429-432`)。但另外两个同类工具都上了保险,只有它没有,
这更像遗漏而非取舍——尤其 `video_generate` 在某些后端下返回的正是**本地绝对路径**(§2.1.4),
形态与 `image_generate` 完全一致。

### ■-2 两处"视频缓存目录"的解析方式不一致

`agent/video_gen_provider.py:206-208 @ 863e313`

```python
    from hermes_constants import get_hermes_home

    path = get_hermes_home() / "cache" / "videos"
```

`tools/flux3_video_tool.py:590-592 @ 863e313`

```python
            from hermes_constants import get_hermes_dir

            return get_hermes_dir("cache/videos", "video_cache")
```

`get_hermes_dir` 的语义是"老布局若存在且非空则继续用老的":

`hermes_constants.py:274-276 @ 863e313`

```python
    Returns:
        Absolute ``Path`` — legacy location if it exists with content,
        otherwise the new location.
```

**现象**:在一台**有历史 `~/.hermes/video_cache/` 且非空**的机器上,
provider 侧写 `cache/videos/`,flux3 侧写 `video_cache/`,而网关的清理走的是 `get_video_cache_dir()`
(即 `get_hermes_dir` 语义,`gateway/platforms/base.py:1088`)。
于是 provider 落的盘**既不是 flux3 落的那个目录,也不是被清理的那个目录**。
**严重度**:低(只影响老布局用户,后果是缓存不被清理)。**未实跑复现,判据为读码**。

### ■-3 统一面的长任务在"单工具 + CLI 主线程"路径上没有任何本地死线(FAL 后端)

`plugins/video_gen/fal/__init__.py:569-571 @ 863e313`

```python
        try:
            handle = _submit_fal_video_request(endpoint, payload)
            result = handle.get()
```

`handle.get()` 是 fal SDK 的阻塞等待,插件没给它任何超时。而 `video_generate` 是 `is_async=False`
(`tools/video_generation_tool.py:573`),所以不经过 `model_tools._run_async` 的 300s 分支
(`model_tools.py:179`);`agent/tool_executor.py:99` 的 420s 只作用在并发批量路径上。
另两个后端各有死线(900s / 240s),唯独 FAL 没有。
**未实跑复现,判据为读码 + 三处死线的对照**。

### ■-4 `xai_video_tools` 的 URL 校验比它自己的 docstring 宽

`tools/xai_video_tools.py:61 @ 863e313`

```python
    """Require a public HTTPS MP4 URL (``http``/``https`` only)."""
```

实现只查前缀(`http://` 也放行),不查 `.mp4`。docstring 里 "HTTPS MP4" 与括号里的
"``http``/``https`` only" 本身就自相矛盾。**严重度**:很低(xAI 服务端会自己拒),记录为措辞缺陷。

### ■-5 `emoji="video"` —— 两个 xAI 视频工具的"emoji"是一个英文单词

`tools/xai_video_tools.py:196-197 @ 863e313`

```python
    is_async=False,
    emoji="video",
```

这个值被原样当作展示 emoji 返回:

`agent/display.py:162-167 @ 863e313`

```python
    # 2. Registry default
    try:
        from tools.registry import registry
        emoji = registry.get_emoji(tool_name, default="")
        if emoji:
            return emoji
```

全仓 `tools/` 下 `emoji=` 的取值分布中,只有这两处不是字形:

```verify
cd /home/user/hermes-agent && grep -rn "emoji=" --include=*.py tools/ | grep -oE 'emoji="[^"]*"' | sort | uniq -c | sort -rn | head -30
```

实测:`emoji="🎬"` 7 次(video_generate 1 + flux3 5)、`emoji="📖"` 2 次(含 flux3 指南)、
`emoji="video"` 2 次 —— 后者会让 CLI / 网关的工具行打印出字面 `video` 而不是图标。
**严重度**:纯外观。

### ■-6 测试环境依赖没有 skip 守卫(见 §4.4)

`tests/tools/test_video_generation_tool_surface_matrix.py` 的 6+2 条 FAL 用例在缺 `fal-client` 时
以**断言失败**告终而非 skip。仓库自己在 CLAUDE.md 同型场景(aiohttp)里已经踩过一次
"表现为 ImportError,不是断言失败,容易误判成测试挂了";这里是相反的形态,同样容易误判。
**归 ■(测试脆性)而非代码缺陷。**

---

## 6. 移交项

### H-R9B-a:开发者文档"网关会在交付时解析远程 URL"这句话未定真伪

- **锚点**:`website/docs/developer-guide/video-gen-provider-plugin.md:227` 的
  `Otherwise return the upstream URL directly — the gateway resolves remote URLs on delivery.`
  与 `plugins/video_gen/fal/__init__.py:30` 的 `HTTPS URL from FAL's CDN; the gateway downloads and delivers it.`
- **现象**:我找到的两条出站附件抽取路径都**不接受裸 URL**——
  `gateway/platforms/base.py:4620` 的 `# (?<![/:\w.]) prevents matching inside URLs (e.g. https://…/img.png)`
  显式排除 URL;`gateway/platforms/base.py:1702` 的 `MEDIA_TAG_CLEANUP_RE = re.compile(`
  要求路径以 `~/` / `/` / 盘符开头(**但带引号的形式 `"..."` 是另一条分支,可能放行 URL**)。
  下游 WhatsApp Cloud 确实支持 URL 直发(`gateway/platforms/whatsapp_cloud.py:1129` 的
  `if source.startswith(("http://", "https://")):`),所以**不能断言这条文档是假的**。
- **未做的事**:没有沿"引号包裹的 MEDIA 标签 → extract_media → 交付根校验 → send_video"这条完整链路走一遍,
  也没有实跑。下一轮若要定案,需要把这条链路走通再判 ▲ / ◎ / 无事。

### H-R9B-b:`register_provider` 不 strip name,而 `get_provider` strip

- **锚点**:`agent/video_gen_registry.py:71-76` 的 `def get_provider(name: str) -> Optional[VideoGenProvider]:`
  对入参 `.strip()`;`agent/video_gen_registry.py:52-54` 的 `name = provider.name` 只判非空不 strip。
- **现象**:插件把 `name` 写成 `" xai "` 时,注册键含空格,`get_provider(" xai ")` 因 strip 反而查不到;
  `get_active_provider()` 走 `snapshot.get(configured)`(已 strip 过 configured)同样查不到。
  未验证是否有插件真会这么写;image_gen_registry 是否同形也未核。

### H-R9B-c:`video_gen` 的可见性门与 `xai_video_edit/extend` 的可见性门可以互相矛盾

- **锚点**:`tools/video_generation_tool.py:199` 的 `def check_video_generation_requirements() -> bool:`
  (任一 provider 可用即 True)vs `tools/xai_video_tools.py:27-28` 的
  `def _check_xai_video_requirements() -> bool:`(要求 `video_gen.provider == "xai"` **且**有凭据)。
- **现象**:若用户配了 `video_gen.provider: xai` 但 xai 插件被 `plugins.enabled` 关掉,
  则 `get_active_provider()` 因"配置了但没注册"失败关闭返回 None(`agent/video_gen_registry.py:109` 的 `return None`),
  `video_generate` 报 `provider_not_registered`;
  而 `xai_video_edit` 的 check_fn 只看 config + 凭据、**不看注册表**,仍会下发并可执行
  (因为它直接 import 了 `plugins.video_gen.xai`,见 §2.5.1)。
  即:**同一 toolset 里,generate 挂了但 edit/extend 还活着**。未实跑复现,判据为读码。

### H-R9B-d:插件侧 3 个 provider(1,639 行)本轮未精读

- **锚点**:`plugins/video_gen/xai/__init__.py`(925)、`plugins/video_gen/fal/__init__.py`(624)、
  `plugins/video_gen/deepinfra/__init__.py`(90)。
- **现象**:本轮只按需读了它们的轮询常量、模型族表与 `handle.get()` 一段。
  `FAL_FAMILIES` 六族的 payload 构造(`plugins/video_gen/fal/__init__.py:69` 的 `    "ltx-2.3": {`)、
  xAI 的 storage_options 与 public_url 语义(`plugins/video_gen/xai/__init__.py:58` 的
  `MAX_REFERENCE_IMAGES = 7`)都还没有逐行取证。它们是"视频生成"这一簇的实际执行体,
  应在后续轮次或 R9B 成品章之前补齐。

### H-R9B-e:`tests/hermes_cli/test_video_gen_picker.py`(183 行)与 `tests/plugins/video_gen/`(651 行)本轮未跑

- **锚点**:`tests/hermes_cli/test_video_gen_picker.py`、`tests/plugins/video_gen/test_fal_plugin.py`。
- **现象**:前者覆盖 `hermes tools` → Video Generation 的选择器流程
  (`hermes_cli/tools_config.py:4021` 的 `def _select_plugin_video_gen_provider(plugin_name: str, config: dict, *, use_gateway: bool = False) -> None:`),
  后者覆盖插件本体。考虑到 §4.4 已确认 `fal-client` 缺失,`test_fal_plugin.py` 很可能同样受影响,
  但**未实跑,不下判断**。

---

## 7. 一句话小结(给成品章作者)

这一簇最值得写进《设计蓝图》的不是"怎么调用视频 API",而是**同一个团队在同一个仓库里,
对"长任务怎么等"给出了两个相反的答案,并且都把理由写在了代码旁边**:

- 统一面选**同步阻塞**,代价是一个工具调用可能占住线程 15 分钟,收益是模型只需要一次调用、
  产物直接到手(`tools/video_generation_tool.py:429-430`)。
- BFL 面选**submit + 自带长轮询的 poll**,代价是模型要学会"再叫我一次",
  收益是每次调用都有硬兜底、都能响应中断、都能报告 job 还活着
  (`tools/flux3_video_tool.py:684-696`)。

而且后者把"超时后说什么"当成了一等设计问题——`TimeoutError:` 是个**没有信息量的答案**,
它既不告诉模型 job 死没死,也不给它下一步。把它换成一句带 job id 的"还在生成,再叫我一次",
是这一簇最可迁移的一条经验。
