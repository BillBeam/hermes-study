# R9B 底稿 · 语音合成 TTS

> 证据约定:凡对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` **单独成行、置于代码块之前**,
> 紧跟逐字源码摘录。基线 `/home/user/hermes-agent` 只读,commit `863e31318553cda8ad61df681d08175364d4164b`。
> 非源码块用 ```verify(可复现 shell)/ ```console(输出)/ ```text 显式标注。

---

## 0. 本簇范围与文件清单

```verify
cd /home/user/hermes-agent && wc -l \
  agent/tts_provider.py agent/tts_registry.py tools/tts_tool.py \
  tools/tts_streaming.py tools/tts_text_normalize.py \
  tools/neutts_synth.py tools/audio_container.py
```

```console
   274 agent/tts_provider.py
   134 agent/tts_registry.py
  3964 tools/tts_tool.py
   488 tools/tts_streaming.py
   278 tools/tts_text_normalize.py
   110 tools/neutts_synth.py
    97 tools/audio_container.py
  5345 total
```

一句话定位:

| 文件 | 角色 |
|---|---|
| `agent/tts_provider.py` | **插件后端的抽象基类(ABC)**。ABC = abstract base class,Python 里"只定义接口、不给实现"的父类;子类必须实现被 `@abc.abstractmethod` 标记的方法 |
| `agent/tts_registry.py` | 插件后端的**进程内注册表**:名字 → 实例的字典 + 一把锁 |
| `tools/tts_tool.py` | **本簇的全部实体**:10 个内建 provider、command provider 运行器、插件分发、容器修复、主工具函数、流式播放器、工具 schema 注册 |
| `tools/tts_streaming.py` | **流式合成的 provider 半边**:句子切分器 + 4 个"分块 PCM"流式后端 + 打断闩锁 |
| `tools/tts_text_normalize.py` | **朗读前文本规范化**:把聊天 Markdown 变成"能读出口的稿子" |
| `tools/neutts_synth.py` | NeuTTS 的**独立子进程入口脚本**(模型 ~500MB,合成完就退出) |
| `tools/audio_container.py` | **全仓唯一的音频容器魔数嗅探器**(出站修复 + 入站语音条缓存共用) |

---

## 1. `tools/tts_tool.py` 结构测绘(3,964 行)

先回答"它为什么这么长":**不是缓存,不是设备管理,是 provider 堆叠**。
按 `# ===` 横幅切段,10 个内建 provider 的实现合计约 1,050 行(1368–2776),
command provider 那一整套(模板渲染 / shell 引号上下文 / 进程树超时清理 / 环境变量擦洗)
约 650 行(580–1232),主函数 375 行(2779–3157),流式播放器 565 行(3297–3861)。
**没有任何音频缓存**——每次调用都新合成、新写文件;只有两个"已加载模型"的 LRU
(Piper voice / KittenTTS model,上限 3)。

| 行段 | 职责 | 锚点 + 摘录 |
|---|---|---|
| 1–101 | 模块 docstring、导入、`get_env_value` / `_resolve_provider_key` 两个"晚绑定"取值口 | `tools/tts_tool.py:63`:`def get_env_value(name, default=None):` |
| 102–203 | **懒导入区**:每个第三方 SDK 一个 `_import_*`,首次用到才 import(headless / 无 PortAudio 环境不炸) | `tools/tts_tool.py:107`:`def _import_edge_tts():` |
| 205–297 | 默认常量:各 provider 的默认 voice/model/base_url + **每 provider 输入字符上限表** | `tools/tts_tool.py:274`:`PROVIDER_MAX_TEXT_LENGTH: Dict[str, int] = {` |
| 300–463 | 上游响应读取(**16 MiB 硬顶**)、写文件、`_resolve_max_text_length` 六级回落 | `tools/tts_tool.py:336`:`def _read_tts_response_bytes(` |
| 466–577 | 配置装载 `_load_tts_config`、`_get_provider`、MiniMax 区域/端点/凭据**原子选择** | `tools/tts_tool.py:512`:`def _resolve_minimax_tts_runtime(` |
| 580–1232 | **command provider 全套**:内建名集合、命名解析、shell 模板渲染与引号上下文、进程树终止、空闲超时读取循环 | `tools/tts_tool.py:611`:`BUILTIN_TTS_PROVIDERS = frozenset({` |
| 1235–1365 | ffmpeg → Opus 转码 + **容器嗅探与 `.ogg` 修复** | `tools/tts_tool.py:1332`:`def _repair_ogg_container(file_str: str) -> str:` |
| 1368–2418 | **云端 provider 实现**:edge / elevenlabs / openai(+deepinfra 复用)/ xai / minimax / mistral / gemini | `tools/tts_tool.py:1371`:`async def _generate_edge_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:` |
| 2421–2503 | NeuTTS(本地,子进程) | `tools/tts_tool.py:2453`:`def _generate_neutts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:` |
| 2506–2713 | Piper(本地)+ **模型 LRU 缓存** | `tools/tts_tool.py:2518`:`def _tts_cache_get_or_load(cache: Dict[str, Any], key: str, load: Callable[[], Any]) -> Any:` |
| 2716–2776 | KittenTTS(本地) | `tools/tts_tool.py:2724`:`def _generate_kittentts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:` |
| 2779–3157 | **主工具函数**:规范化 → 解析 provider → 截断 → 选路径 → 分发 → 容器修复 → Opus 判定 → JSON 信封 | `tools/tts_tool.py:2782`:`def text_to_speech_tool(` |
| 3160–3294 | `check_tts_requirements`(必须与分发链一一对应)+ OpenAI 音频凭据解析 | `tools/tts_tool.py:3163`:`def check_tts_requirements() -> bool:` |
| 3297–3861 | **流式播放器**:遗留 markdown 正则、`_SyncSentencePipeline`、`stream_tts_to_speaker` | `tools/tts_tool.py:3444`:`def stream_tts_to_speaker(` |
| 3864–3902 | `__main__` 自检打印 | — |
| 3905–3964 | **工具注册**:`TTS_SCHEMA` + `registry.register` | `tools/tts_tool.py:3910`:`TTS_SCHEMA = {` |

**读法建议**:要理解机制只需读 3 段——`text_to_speech_tool`(2782–3157)、
command provider 那一段(580–1232)、`stream_tts_to_speaker`(3444–3861)。
10 个 provider 实现是同一模板的重复填空(读配置 → 拼 payload → POST/SDK → 写文件),
读 2 个(`_generate_openai_tts`、`_generate_gemini_tts`)就能推出其余 8 个。

---

## 2. 一次「把这段话读出来」的完整走法

模型调用 `text_to_speech(text="…")`。全部发生在 `text_to_speech_tool` 里,顺序如下。

### 2.1 先规范化,再算长度

`tools/tts_tool.py:2822-2828` @ 863e313

```python
    try:
        from tools.tts_text_normalize import prepare_spoken_text
        text = prepare_spoken_text(text, max_chars=None)
    except Exception:
        text = text.strip()
    if not text:
        return tool_error("Text is empty after TTS cleanup", success=False)
```

注意 `max_chars=None`:规范化阶段**不截断**,截断留给下一步的 per-provider 上限——
因为规范化会**改变长度**(去掉代码块变短、`°C` → `degrees Celsius` 变长),
先截后规范会截错位置。

### 2.2 per-provider 字符上限截断

`tools/tts_tool.py:2853-2859` @ 863e313

```python
    max_len = _resolve_max_text_length(provider, tts_config)
    if len(text) > max_len:
        logger.warning(
            "TTS text too long for provider %s (%d chars), truncating to %d",
            provider, len(text), max_len,
        )
        text = text[:max_len]
```

`_resolve_max_text_length` 是六级回落(`tools/tts_tool.py:415-426` 的 docstring 自述):
`tts.<provider>.max_text_length` → `tts.providers.<provider>.max_text_length` →
ElevenLabs 按 `model_id` 查表 → `PROVIDER_MAX_TEXT_LENGTH` →
`DEFAULT_COMMAND_TTS_MAX_TEXT_LENGTH`(5000)→ `FALLBACK_MAX_TEXT_LENGTH`(4000)。

`tools/tts_tool.py:438-441` @ 863e313

```python
    if isinstance(override, bool):
        override = None
    if isinstance(override, int) and override > 0:
        return override
```

**为什么显式排 bool**:Python 里 `isinstance(True, int)` 为真,不排掉的话
`max_text_length: true` 会被当成 `1`,把每次合成截成一个字。这条是"配置写错不能变成静默灾难"的具体化。

### 2.3 平台决定要不要 Opus

`tools/tts_tool.py:2866-2868` @ 863e313

```python
    from gateway.session_context import get_session_env
    platform = get_session_env("HERMES_SESSION_PLATFORM", "").lower()
    want_opus = platform in OPUS_VOICE_PLATFORMS
```

`OPUS_VOICE_PLATFORMS` 是 5 个平台的集合,带一条来自事故的注释:

`tools/tts_tool.py:632-642` @ 863e313

```python
# Platforms whose native voice-bubble delivery requires Ogg/Opus audio.
# Previously only Telegram was recognized, so Matrix/Feishu/WhatsApp/Signal
# voice replies were synthesized as MP3 and rendered as broken attachments
# (#14841, #45557 and siblings).
OPUS_VOICE_PLATFORMS = frozenset({
    "telegram",
    "matrix",
    "feishu",
    "whatsapp",
    "signal",
})
```

### 2.4 选输出路径与扩展名

`tools/tts_tool.py:2912-2920` @ 863e313

```python
        if command_provider_config is not None:
            fmt = _get_command_tts_output_format(command_provider_config)
            file_path = out_dir / f"tts_{timestamp}.{fmt}"
        # Use .ogg for Telegram with providers that support native Opus output,
        # otherwise fall back to .mp3 (Edge TTS will attempt ffmpeg conversion later).
        elif want_opus and provider in {"openai", "elevenlabs", "mistral", "gemini"}:
            file_path = out_dir / f"tts_{timestamp}.ogg"
        else:
            file_path = out_dir / f"tts_{timestamp}.mp3"
```

调用方给了 `output_path` 时,先过两道安全闸。第一道是 `..` 穿越检查:

`tools/tts_tool.py:2880-2889` @ 863e313

```python
        from tools.path_security import has_traversal_component
        if has_traversal_component(output_path):
            return json.dumps({
                "success": False,
                "error": (
                    f"output_path contains '..' traversal component: "
                    f"{output_path}. Use an absolute path or one relative "
                    "to the current directory without '..'."
                ),
            }, ensure_ascii=False)
```

它上方的注释把威胁模型写得很直白:`output_path="audio/../../etc/cron.d/x"`
是提示注入能拿到的原语,而 TTS 是**无人值守**的工具面。第二道是受保护路径:

`tools/tts_tool.py:2898-2907` @ 863e313

```python
        from agent.file_safety import is_write_denied

        if is_write_denied(str(file_path)):
            return json.dumps({
                "success": False,
                "error": (
                    f"output_path targets a protected credential or system path: "
                    f"{file_path}. Choose a normal audio output location."
                ),
            }, ensure_ascii=False)
```

### 2.5 分发(优先级链)

分发链的**顺序本身就是设计**:command → plugin → 10 个内建 elif → edge 兜底。

`tools/tts_tool.py:2944-2949` @ 863e313

```python
        elif provider not in BUILTIN_TTS_PROVIDERS and (
            _plugin_path := _dispatch_to_plugin_provider(
                text, file_str, provider, tts_config,
            )
        ) is not None:
            file_str = _plugin_path
```

海象运算符 `:=` 在这里是必需的:插件分发**返回 None 表示"没找到,继续往下"**,
返回路径表示"我处理了"。用普通 `if` 就得先调一次再判断,而调用有副作用(会写文件)。

### 2.6 合成后:容器修复

`tools/tts_tool.py:3080-3086` @ 863e313

```python
        # Class-level container repair: several backends silently write
        # MP3/WAV bytes into a .ogg output path (Edge, Piper, xAI,
        # OpenAI-compatible servers without opus support), which platforms
        # like Telegram render as broken 0-second voice bubbles. Sniff the
        # magic bytes once here — covering every current and future
        # provider — and transcode in place when they don't match.
        file_str = _repair_ogg_container(file_str)
```

这是**类级修复**:不给每个 provider 打补丁,而是在出口处嗅探一次魔数。设计取舍很清楚——
用一次 12 字节读换掉 N 个 provider 的 N 份特判。

### 2.7 Opus 转换与"语音条"标记

`tools/tts_tool.py:3115-3125` @ 863e313

```python
        elif (
            want_opus
            and provider in {"edge", "neutts", "minimax", "xai", "kittentts", "piper"}
            and not file_str.endswith(".ogg")
        ):
            opus_path = _convert_to_opus(file_str)
            if opus_path:
                file_str = opus_path
                voice_compatible = True
        elif provider in {"elevenlabs", "openai", "mistral", "gemini"}:
            voice_compatible = want_opus and file_str.endswith(".ogg")
```

### 2.8 返回信封

`tools/tts_tool.py:3130-3141` @ 863e313

```python
        # Build response with MEDIA tag for platform delivery
        media_tag = f"MEDIA:{file_str}"
        if voice_compatible:
            media_tag = f"[[audio_as_voice]]\n{media_tag}"

        return json.dumps({
            "success": True,
            "file_path": file_str,
            "media_tag": media_tag,
            "provider": provider,
            "voice_compatible": voice_compatible,
        }, ensure_ascii=False)
```

`MEDIA:<path>` 与 `[[audio_as_voice]]` 是**给网关看的带内指令**,不是给模型看的。
网关侧在 `gateway/platforms/base.py:4485-4486` 解析 `[[audio_as_voice]]`,
在 `gateway/platforms/base.py:1847` 把这两个标记从要发给用户的文本里剥掉。

---

## 3. 逐机制

### 3.1 provider 抽象与 registry:与 image/video 不同构,与 STT 同构

`agent/tts_provider.py` 定义 `TTSProvider`,只有两个抽象成员:`name` 与 `synthesize`。

`agent/tts_provider.py:180-191` @ 863e313

```python
    @abc.abstractmethod
    def synthesize(
        self,
        text: str,
        output_path: str,
        *,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        format: str = DEFAULT_OUTPUT_FORMAT,
        **extra: Any,
    ) -> str:
```

`**extra` 是**前向兼容口**:未来 schema 加参数时,老插件不改代码也不会因为多收一个关键字参数而崩。
`stream()` 是**可选**的,默认实现直接抛异常,分发器回落到 `synthesize()` + 读整文件:

`agent/tts_provider.py:238-242` @ 863e313

```python
        raise NotImplementedError(
            f"TTS provider {self.name!r} does not implement streaming "
            "synthesis. Use synthesize() instead, or implement stream() "
            "if your backend supports it."
        )
```

registry 的核心不变量是「**内建名永远赢**」,而且**两处**都查:

`agent/tts_registry.py:48-60` @ 863e313

```python
_BUILTIN_NAMES = frozenset({
    "edge",
    "elevenlabs",
    "openai",
    "minimax",
    "xai",
    "mistral",
    "gemini",
    "neutts",
    "kittentts",
    "piper",
    "deepinfra",
})
```

`tools/tts_tool.py:611-623` @ 863e313

```python
BUILTIN_TTS_PROVIDERS = frozenset({
    "edge",
    "elevenlabs",
    "openai",
    "minimax",
    "xai",
    "mistral",
    "gemini",
    "neutts",
    "kittentts",
    "piper",
    "deepinfra",
})
```

两份常量是**故意重复**的:`tools.tts_tool` 要 import `agent.tts_registry` 做分发,
反向 import 会成环。代价用一条回归测试兜住:

`tests/agent/test_tts_registry.py:208-211` @ 863e313

```python
    def test_registry_builtins_match_dispatcher_builtins(self):
        from tools.tts_tool import BUILTIN_TTS_PROVIDERS

        assert tts_registry._BUILTIN_NAMES == BUILTIN_TTS_PROVIDERS, (
```

第二道防线在分发器里(注册时挡不住的场景:插件先注册、后来才加内建同名):

`tools/tts_tool.py:743-749` @ 863e313

```python
    if key in BUILTIN_TTS_PROVIDERS:
        return None
    # Defense in depth: command-provider check should already have
    # short-circuited the caller. If a same-name command config exists,
    # bail so the command path wins.
    if _is_command_provider_config(_get_named_provider_config(tts_config, key)):
        return None
```

**与兄弟簇的同构关系(已核对文件级 API 面)**:

```verify
cd /home/user/hermes-agent && for f in tts transcription image_gen video_gen; do
  echo "== $f =="; grep -n '^def \|^_BUILTIN_NAMES\|^_providers' agent/${f}_registry.py; done
```

```console
== tts ==
48:_BUILTIN_NAMES = frozenset({
63:_providers: Dict[str, TTSProvider] = {}
67:def register_provider(provider: TTSProvider) -> None:
112:def list_providers() -> List[TTSProvider]:
119:def get_provider(name: str) -> Optional[TTSProvider]:
131:def _reset_for_tests() -> None:
== transcription ==
40:_BUILTIN_NAMES = frozenset({
52:_providers: Dict[str, TranscriptionProvider] = {}
56:def register_provider(provider: TranscriptionProvider) -> None:
102:def list_providers() -> List[TranscriptionProvider]:
109:def get_provider(name: str) -> Optional[TranscriptionProvider]:
121:def _reset_for_tests() -> None:
== image_gen ==
32:_providers: Dict[str, ImageGenProvider] = {}
36:def register_provider(provider: ImageGenProvider) -> None:
60:def list_providers() -> List[ImageGenProvider]:
67:def get_provider(name: str) -> Optional[ImageGenProvider]:
75:def get_active_provider() -> Optional[ImageGenProvider]:
142:def _reset_for_tests() -> None:
== video_gen ==
36:_providers: Dict[str, VideoGenProvider] = {}
40:def register_provider(provider: VideoGenProvider) -> None:
64:def list_providers() -> List[VideoGenProvider]:
71:def get_provider(name: str) -> Optional[VideoGenProvider]:
79:def get_active_provider() -> Optional[VideoGenProvider]:
130:def _reset_for_tests() -> None:
```

结论:**TTS 与 STT(transcription)完全同构**——都有 `_BUILTIN_NAMES` 保留名、都没有
`get_active_provider()`;**image_gen / video_gen 是另一支**——registry 里带
`get_active_provider()`(自己读配置解析当前 provider)、没有保留名机制。
**没有共用上层**:七个 registry(`browser` / `image_gen` / `transcription` / `tts` /
`video_gen` / `web_search` + `plugin_llm`)各自复制了同一份 `_providers` + `_lock` +
四个函数的骨架,全仓没有一个泛型 registry 基类。

搜索面:`ls agent/*registry*.py` 列出 6 个 registry 文件,逐个 `grep '^def '` 比对函数名集合;
没有找到任何 `class .*Registry` 或被这些模块共同 import 的注册基础设施。

### 3.2 三层扩展面的解析顺序

`agent/tts_provider.py:12-23` @ 863e313

> Three coexisting TTS extension surfaces — in resolution order:
>
> 1. **Built-in providers** (``BUILTIN_TTS_PROVIDERS`` in
>    :mod:`tools.tts_tool`) — native Python implementations (edge, openai,
>    elevenlabs, …). **Always win** — plugins cannot shadow them.
> 2. **Command-type providers** declared under ``tts.providers.<name>:
>    type: command`` (PR #17843, commit ``2facea7f7``). Wire any local
>    CLI into Hermes with shell-template placeholders. **Wins over a
>    same-name plugin** — config is more local than plugin install.
> 3. **Plugin-registered providers** (this ABC). For backends that need a
>    Python SDK, streaming bytes, OAuth refresh, or voice-listing APIs
>    the shell-template grammar can't reasonably express.

代码里的实际顺序是 **command → plugin → 内建 elif 链 → edge 兜底**
(`tools/tts_tool.py:2928 / 2944 / 2951…3044`),但因为 command 分支与 plugin 分支
都先 `if key in BUILTIN_TTS_PROVIDERS: return None`,净效果与 docstring 描述的
"内建优先"一致。**理由(locality)**:用户 `config.yaml` 里写的名字比"碰巧装了个插件"更贴近本机意图。

**command provider 的三个非显然细节**:

1. **按 shell 引号上下文分别转义**。`_shell_quote_context` 扫模板到占位符位置,
   判断它落在裸上下文 / `'…'` / `"…"` 里,再选对应转义。
   `tools/tts_tool.py:908-920` @ 863e313

```python
    if quote_context == "'":
        return value.replace("'", r"'\''")
    if quote_context == '"':
        return (
            value
            .replace("\\", "\\\\")
            .replace('"', r'\"')
            .replace("$", r"\$")
            .replace("`", r"\`")
        )
    if os.name == "nt":
        return subprocess.list2cmdline([value])
    return shlex.quote(value)
```

2. **超时是"空闲超时"不是"总超时"**:任一路输出都会把 deadline 往后推。
   `tools/tts_tool.py:1100-1104` @ 863e313

```python
        if chunk is None:
            open_streams.discard(name)
            continue
        chunks[name].append(chunk)
        deadline = time.monotonic() + timeout
```

   取舍:长文本合成的 CLI 会持续打进度,不该被总时长掐死;彻底卡死的仍会被 120s 空闲兜住。

3. **子进程环境默认擦洗 Hermes 机密**,靠 `env_passthrough` 白名单显式放行。
   `tools/tts_tool.py:1032-1036` @ 863e313

```python
    scrubbed = hermes_subprocess_env(inherit_credentials=False)
    for key in env_passthrough or []:
        value = os.environ.get(key)
        if value is not None:
            scrubbed[key] = value
```

### 3.3 流式合成:文本边生成边合成,按句切

**是的,边生成边合成**,但粒度是**句**不是 token。两条路,一个契约(int16 单声道 PCM)。

#### 切句:`SentenceChunker`

`tools/tts_streaming.py:84-85` @ 863e313

```python
# Sentence boundary: after .!? followed by whitespace, or a blank line.
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])(?:\s|\n)|(?:\n\n)")
```

`tools/tts_streaming.py:103-118` @ 863e313

```python
    def feed(self, delta: str) -> List[str]:
        """Absorb *delta*; return every complete sentence now ready to speak."""
        self.buf = _THINK_BLOCK_RE.sub("", self.buf + delta)
        if "<think" in self.buf and "</think>" not in self.buf:
            return []  # open think tag — the closing tag may arrive next delta
        out: List[str] = []
        start = 0  # skip boundaries that would leave the head too short
        while m := SENTENCE_BOUNDARY_RE.search(self.buf, start):
            head = self.buf[: m.end()]
            if len(head.strip()) < self.min_len:
                start = m.end()
                continue
            out.append(head)
            self.buf = self.buf[m.end():]
            start = 0
        return out
```

三个设计点:

- **`min_len=20` 的短片段合并**:`"Ha!"` 不单独成一段音频,而是跟着下一句一起送。
  否则会听到一串极短的、彼此有间隙的碎音。
- **`<think>` 跨 delta 的处理**:每次 feed 都对**整个缓冲**重跑一次剥离正则;
  见到未闭合的 `<think` 就整批不吐,等闭合标签。这解决的是"推理块被切成两半、
  前半已经被读出来了"的问题。
- **重跑剥离 = O(buf) per delta**,是拿 CPU 换正确性;缓冲通常只有一两句,可接受。

同一个切句器被三个界面共用(`tools/tts_tool.py:3480` 的 CLI 播放器、
`gateway/streaming_tts_consumer.py:79`、`hermes_cli/web_server.py:4684`),
docstring 明说是为了"每个界面切得一模一样"。

#### 首字节延迟怎么优化:两级

**第一级:选真流式后端。** 4 个注册的分块 PCM 后端:

| 后端 | 传输 | 锚点 + 摘录 |
|---|---|---|
| elevenlabs | 分块 HTTP,`pcm_24000` | `tools/tts_streaming.py:220`:`@register("elevenlabs")` |
| openai | `with_streaming_response`,`response_format="pcm"` | `tools/tts_streaming.py:291`:`response_format="pcm",` |
| gemini | SSE(`streamGenerateContent?alt=sse`),base64 PCM | `tools/tts_streaming.py:368`:`url = f"{base_url}/models/{model}:streamGenerateContent"` |
| xai | WebSocket(`wss://api.x.ai/v1/tts`) | `tools/tts_streaming.py:454`:`self.section.get("streaming_url") or "wss://api.x.ai/v1/tts"` |

`tools/tts_streaming.py:175-179` @ 863e313

```python
# Fallback priority for ``tts.streaming.provider: auto`` — best chunked
# latency/quality first. Deliberately hard-coded (a UX decision, not a
# config knob); edge is absent because it has no chunked-PCM API — the
# dispatcher's per-sentence sync path keeps it conversational instead.
_PROVIDER_PRIORITY: List[str] = ["elevenlabs", "gemini", "openai", "xai"]
```

**关键取舍(写在 `resolve_streaming_provider` 的 docstring 里)**:
配置的 provider 没有分块 API 时,**不偷偷换 provider**,而是回落到"逐句同步合成"。
理由:用户选的是**声音**,为了低延迟换掉他的声音是错的默认。

**第二级:非流式后端也逐句播。** `_SyncSentencePipeline` 把"合成"与"播放"重叠:

`tools/tts_tool.py:3376-3387` @ 863e313

```python
    def __init__(self, stop_event: threading.Event, *, lookahead: int = 2):
        self._stop = stop_event
        self._queue: "queue.Queue[Optional[tuple[str, Future]]]" = queue.Queue(
            maxsize=max(1, lookahead)
        )
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="tts-sync-synth"
        )
        self._player = threading.Thread(
            target=self._drain, name="tts-sync-play", daemon=True
        )
        self._player.start()
```

`max_workers=1` 是**故意的**:句子按 FIFO 合成,provider 永远看不到本循环发出的并发请求
(与串行路径同样的有效并发度),只是把第 n+1 句的合成挪到第 n 句播放期间。

#### 背压与缓冲

三处显式的界:

`tools/tts_tool.py:3532-3535` @ 863e313

```python
        _audio_queue: queue.Queue[Optional[queue.Queue[Optional[bytes]]]] = queue.Queue()
        _prefetch_threads: list[threading.Thread] = []
        _prefetch_sem = threading.Semaphore(3)
        _CHUNK_QUEUE_MAX = 64
```

`tools/tts_tool.py:3702-3719` @ 863e313

```python
        def _enqueue_audio(text_to_speak: str) -> None:
            """Synthesize *text_to_speak* and start prefetching immediately."""
            assert streamer is not None
            try:
                audio_iter = streamer.stream(text_to_speak)
            except Exception as exc:
                logger.warning("Streaming TTS synthesis failed: %s", exc)
                return
            _prefetch_sem.acquire()
            chunk_queue: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=_CHUNK_QUEUE_MAX)
            _audio_queue.put(chunk_queue)
            t = threading.Thread(
                target=_consume_to_queue,
                args=(audio_iter, chunk_queue),
                daemon=True,
            )
            _prefetch_threads.append(t)
            t.start()
```

- **信号量 3**:最多 3 个句子在同时预取。满了以后 `_enqueue_audio` 在生产者线程上阻塞,
  这就是对"模型比嘴快"的背压。
- **每句 chunk 队列上限 64**:单句的 PCM 缓冲上限。
- **每句 16 MiB 硬顶**(`_capped`):

`tools/tts_streaming.py:296-310` @ 863e313

```python
def _capped(chunks: Iterator[bytes], label: str) -> Iterator[bytes]:
    """Pass chunks through, aborting past the 16 MiB per-sentence cap.

    The streaming mirror of ``_read_tts_response_bytes``'s bounded-body
    invariant: one sentence of PCM should never approach the cap, so
    exceeding it means a runaway/hostile upstream — stop pulling.
    """
    total = 0
    for chunk in chunks:
        total += len(chunk)
        if total > _STREAM_SENTENCE_BYTE_CAP:
            logger.warning("%s exceeded %d bytes for one sentence; truncating",
                           label, _STREAM_SENTENCE_BYTE_CAP)
            return
        yield chunk
```

- **空闲冲刷**:生产者 0.5s 没给新 delta 且缓冲超过 100 字符,就先把它读出来——
  避免"模型卡住时用户干等一段已经写好的话"。

`tools/tts_tool.py:3812-3815` @ 863e313

```python
                # Idle producer: flush a long buffer instead of sitting on it
                if len(chunker.buf) > long_flush_len:
                    for sentence in chunker.flush():
                        _speak_sentence(sentence)
```

#### 打断闩锁(barge-in 的模型侧)

`tools/tts_streaming.py:66-82` @ 863e313

```python
SPEECH_INTERRUPTED_NOTE = (
    "[Note: the user interrupted your previous spoken reply before it finished.]"
)
_INTERRUPT_TTL_S = 120.0
_interrupted_at: Optional[float] = None


def mark_speech_interrupted() -> None:
    global _interrupted_at
    _interrupted_at = time.monotonic()


def take_speech_interrupted() -> bool:
    """Pop the latch; True when a barge happened within the TTL."""
    global _interrupted_at
    at, _interrupted_at = _interrupted_at, None
    return at is not None and time.monotonic() - at < _INTERRUPT_TTL_S
```

设计点:这条 note 是**只进 API 调用、不落盘**的(与 CLI 的换模型提示同源);
120s TTL 防止一次很久以前的打断给一条无关消息加注。
消费方:`cli.py:14026-14028`、`tui_gateway/server.py:9595-9601`。

#### 播放层在哪一层

**播放不在 provider 层,在 `stream_tts_to_speaker` 里**,而且有两条:

- **PortAudio 直写**:`sd.OutputStream(samplerate=streamer.sample_rate, channels=…, dtype="int16")`,
  PCM 按 2 字节对齐后 `numpy.frombuffer(..., dtype="<i2")` 写入。
  写失败会最多重建 3 次流(`_reinit_output_stream`),再失败就整体降级到临时文件路径。
- **临时 WAV + 系统播放器**:`_play_via_tempfile` 把 PCM 包成 WAV 交给
  `tools.voice_mode.play_audio_file`(afplay / ffplay / aplay)。

macOS 上**直接不走 PortAudio**:

`tools/tts_tool.py:3496-3502` @ 863e313

```python
            # On macOS, skip the sounddevice OutputStream entirely: PortAudio/
            # CoreAudio init triggers a kTCCServiceMediaLibrary permission
            # prompt even though output needs no media-library access. Leaving
            # output_stream=None routes each sentence through the tempfile
            # -> play_audio_file -> afplay path. See PR #62601 / #13291.
            if platform.system() == "Darwin":
                output_stream = None
```

这是一条**产品级的取舍**:为了不弹一个跟功能无关的系统权限框,主动放弃最低延迟路径。

`_play_via_tempfile` 里还藏着一条 Windows 教训:

`tools/tts_tool.py:3784-3790` @ 863e313

```python
                # wave.open() given a file object flushes but does NOT close it
                # (it only closes files it opened itself, by name), so the OS
                # handle to tmp stays open.  On Windows an open write handle
                # blocks the system player from reading the file and blocks the
                # os.unlink() below (WinError 32, swallowed → temp .wav files
                # pile up).  Release the handle before playback and cleanup.
                tmp.close()
```

### 3.4 文本规范化:为什么、处理了什么

**为什么**:TTS provider 收到的应该是**朗读稿**,不是聊天 Markdown。
`**粗体**` 会被读成"星号星号"、表格竖线会被读成"vertical bar"、emoji 会被读成
"smiling face"、`<think>` 推理块用户想**看**不想**听**。

`tools/tts_text_normalize.py:271-278` @ 863e313

```python
    spoken = strip_nonspoken_blocks(text)
    spoken = strip_markdown_for_tts(spoken)
    spoken = normalize_symbols_for_tts(spoken)
    spoken = smooth_whitespace_for_tts(spoken)
    spoken = flatten_newlines_for_payload(spoken)
    if max_chars is not None and max_chars > 0 and len(spoken) > max_chars:
        spoken = spoken[:max_chars].rstrip()
    return spoken
```

五道工序,顺序有强依赖:

| # | 函数 | 处理什么 |
|---|---|---|
| 1 | `strip_nonspoken_blocks` | `<think>…</think>`(含未闭合)、run_agent 的"文件改动校验器"页脚 |
| 2 | `strip_markdown_for_tts` | 代码块整段删、图片留 alt、链接留文字、裸 URL 删、行内代码/粗体/斜体/删除线剥标记、标题打**哨兵**、引用/列表/水平线剥前缀、表格竖线 → `; ` |
| 3 | `normalize_symbols_for_tts` | 温度区间与单位、km/h / mm / cm / m、`5/month` → `5 per month`、五种货币、`%`、`&`、`→ ⇒ ≈ ~`、项目符号、变体选择符、emoji |
| 4 | `smooth_whitespace_for_tts` | 把标题哨兵折进下一句、给每行补句末标点、合并空白 |
| 5 | `flatten_newlines_for_payload` | 换行 → 句读,压成**单行** |

几处非显然的设计:

**(a) 标题不是删掉,是用哨兵折进下一句。**

`tools/tts_text_normalize.py:16-19` @ 863e313

```python
# Sentinel appended to former heading lines so smooth_whitespace_for_tts can
# fold a heading into the sentence that follows it ("Weather, it will be sunny")
# rather than leaving a bare "Weather." label that reads abruptly aloud.
_HEAD = "\x00"
```

**(b) 最后压成单行,是为某个具体后端的 bug。**

`tools/tts_text_normalize.py:244-249` @ 863e313

```python
def flatten_newlines_for_payload(text: str) -> str:
    """Collapse newlines into sentence breaks for single-line TTS payloads.

    Some OpenAI-compatible backends (e.g. Kokoro) truncate synthesis at the
    first newline (#9004).  The smoothing pass already terminates each line
    with punctuation, so newlines can safely become plain spaces.
    """
```

**(c) 单位换算只在"前面是数字"时触发。**

`tools/tts_text_normalize.py:132-134` @ 863e313

```python
    # Numeric rates only ("5/month" -> "5 per month").  Requiring digit-then-letter
    # keeps "and/or", "N/A", "TCP/IP" and dates like "2026/06" intact.
    text = re.sub(r"(?<=\d)\s*/\s*(?=[A-Za-z])", " per ", text)
```

**(d) 非 ASCII 字符在源码里写成转义,是刻意的。**

`tools/tts_text_normalize.py:7-8` @ 863e313

```python
Non-ASCII characters are written as escapes on purpose so the file stays free of
invisible/look-alike glyphs.
```

(注:这条 docstring 与实际不完全一致——`tools/tts_text_normalize.py:50` 的
`"☀-➿"`、`:110` 的空格类字符、`:113` 之后的 `°`、`:148-152` 的 `•◦▪▫→⇒≈`
都是**字面量**而非转义。声明与实现的偏差记在 §6 观察项。)

**实测**(用 venv 直接调库,非源码块):

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python -c "
from tools.tts_text_normalize import prepare_spoken_text
print(repr(prepare_spoken_text('## Weather\n\nIt will be 11-17 °C tomorrow, ~30% chance of rain, wind 25 km/h.')))
print(repr(prepare_spoken_text('<think>x</think>Done. Cost: US\$1,200 & A\$50, i.e. 5/month.')))
"
```

```console
'Weather, It will be 11 to 17 degrees Celsius tomorrow, about 30 percent chance of rain, wind 25 kilometres per hour.'
'Done. Cost: 1,200 US dollars and 50 Australian dollars, i. e. 5 per month.'
```

注意第二例的 `i.e.` → `i. e.`:见 §6 ■-5。

**同一个清理器服务所有 TTS 路径**——工具调用、网关自动 TTS、语音模式流式、Web 面板;
`tools/tts_tool.py` 里那一份**遗留正则管线**(`_MD_CODE_BLOCK` 等,3300–3319)只是
`prepare_spoken_text` 抛异常时的兜底:

`tools/tts_tool.py:3332-3336` @ 863e313

```python
    try:
        from tools.tts_text_normalize import prepare_spoken_text
        return prepare_spoken_text(text, max_chars=None)
    except Exception:
        pass
```

### 3.5 `audio_container.py`:全仓唯一的容器嗅探器

97 行,零依赖,纯魔数判定。**它是被三方共用的单点**:

`tools/audio_container.py:3-16` @ 863e313

> ONE sniffer owns container detection for the whole codebase:
>
> - **Outbound** (``tools/tts_tool.py``): TTS backends silently ignore the
>   requested opus format (Edge emits MP3, Piper writes WAV, ...), so the
>   synthesized file is sniffed and repaired when the bytes don't match the
>   ``.ogg`` extension (PR #73072).
> - **Inbound** (``gateway/platforms/base.py`` ``cache_audio_from_bytes`` /
>   ``cache_audio_from_url``): platform adapters frequently pass a wrong or
>   guessed extension for voice notes (Telegram ``.oga``, iOS Signal M4A-branded
>   MP4, RIFF/WAVE attachments). The cache sniffs the real container so STT and
>   downstream players get an honest extension — the inbound mirror of the
>   outbound repair.
> - ``gateway/platforms/signal.py`` ``_guess_extension`` delegates its audio/AV
>   branches here instead of duplicating the byte patterns.

三条判定难点各有注释支撑:

`tools/audio_container.py:57-62` @ 863e313

```python
    if len(data) >= 8 and data[4:8] == b"ftyp":
        # Brand at bytes 8-11: audio brands ("M4A ", "M4B ") are voice
        # notes / audiobooks; everything else (isom/mp42/avc1/qt) is video.
        if len(data) >= 12 and data[8:12].lower() in _MP4_AUDIO_BRANDS:
            return "m4a"
        return "mp4"
```

`tools/audio_container.py:71-77` @ 863e313

```python
    if len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        # ``0xFF 0xFx`` is shared by MP3 and ADTS AAC. Bits 3-1 of byte 1
        # disambiguate: ADTS has ``ID=0`` and ``layer=00`` (mask 0xF6,
        # target 0xF0); MP3 has ``ID=1`` and ``layer`` in {01,10,11}.
        if (data[1] & 0xF6) == 0xF0:
            return "aac"
        return "mp3"
```

**刻意不管图片**:RIFF 要看第 8-11 字节的 form type 才能分 `WAVE`(音频)与 `WEBP`(图片),
模块只认音频/AV,`WEBP` 返回 `None`,把图片判定留给调用方先做。这是"一个模块只声明它真懂的东西"。

出站修复只做**容器级**判断:

`tools/tts_tool.py:1341-1345` @ 863e313

```python
    if not file_str.endswith(".ogg"):
        return file_str
    container = _sniff_audio_container(file_str)
    if container in ("ogg", "unknown"):
        return file_str
```

修复失败时**改名成诚实的扩展名**,而不是留一个骗人的 `.ogg`——
"宁可给一个能放的普通音频,也不给一个 0 秒的语音条"。

`tools/tts_tool.py:1355-1363` @ 863e313

```python
    # ffmpeg unavailable/failed: rename to the honest extension.
    honest = file_str[:-4] + "." + container
    try:
        os.replace(file_str, honest)
        logger.warning(
            "Could not transcode %s to Ogg/Opus — renamed to %s so the "
            "file is delivered with its real format", file_str, honest,
        )
        return honest
```

### 3.6 `neutts_synth.py`:本地模型,跑在独立子进程里

**本地模型**(不是远端)。`neutts` 是 Neuphonic 的开源本地 TTS;这个文件是一个
`argparse` 入口脚本,由 `tts_tool` 用 `subprocess.run` 拉起。

`tools/neutts_synth.py:2-5` @ 863e313

```python
"""Standalone NeuTTS synthesis helper.

Called by tts_tool.py via subprocess to keep the TTS model (~500MB)
in a separate process that exits after synthesis — no lingering memory.
```

**为什么走子进程而不是 in-process 缓存**(与 Piper/KittenTTS 的做法相反):
模型 ~500MB,常驻会把一个长跑的网关进程撑大;NeuTTS 是"偶尔用"的本地兜底,
用"每次冷启动"换"进程 RSS 不涨"。代价是每次合成多一次模型加载。

两条硬知识写在脚本里:

`tools/neutts_synth.py:62-66` @ 863e313

```python
    # llama_cpp (backbone) offloads to GPU only for the literal string "gpu";
    # torch (codec) only accepts "cuda". A single --device value can't satisfy
    # both — "cuda" silently no-ops on the backbone, leaving it on CPU.
    backbone_device = "gpu" if args.device == "cuda" else args.device
    codec_device = args.device
```

`tools/neutts_synth.py:21-22` @ 863e313

```python
def _write_wav(path: str, samples, sample_rate: int = 24000) -> None:
    """Write a WAV file from float32 samples (no soundfile dependency)."""
```

`soundfile` 装不上时用 `struct` 手写 44 字节 RIFF 头——本地 provider 的依赖要能"少一个也能跑"。
NeuTTS 是**声音克隆式**的:必须给参考音频 + 参考文本,仓库自带默认样本
(`tools/neutts_samples/jo.wav` / `jo.txt`,见 `tools/tts_tool.py:2443-2450`)。

### 3.7 音频格式/采样率/容器怎么协商

**没有协商协议,是三层"约定 + 事后修正"**:

1. **调用方定扩展名**。CLI 默认 `.mp3`;网关按平台定:

`gateway/platforms/base.py:178-187` @ 863e313

```python
    from tools.tts_tool import OPUS_VOICE_PLATFORMS

    ext = "ogg" if _platform_name(platform) in OPUS_VOICE_PLATFORMS else "mp3"
    audio_path = os.path.join(
        tempfile.gettempdir(),
        "hermes_voice",
        f"tts_reply_{uuid.uuid4().hex[:12]}.{ext}",
    )
    os.makedirs(os.path.dirname(audio_path), exist_ok=True)
    return audio_path
```

   注意 docstring 解释了**为什么平台感知放在调用方**而不是 TTS 工具里:
   `HERMES_SESSION_PLATFORM` contextvar 在网关跑自动 TTS 之前已经被清掉了(#57049、#36685)。

2. **provider 各自把扩展名翻成自己的格式参数**。三种翻译方式并存:
   - OpenAI 系:`_tts_response_format_from_path` → `opus/wav/flac/mp3`;
   - ElevenLabs:`.ogg` → `opus_48000_64`,否则 `mp3_44100_128`;
   - xAI:只在**非默认**时才发 `output_format`(保持文档化的最小 payload);
   - Gemini:**固定** 24kHz/单声道/16-bit PCM,无容器,由 Hermes 补 WAV 头再按需 ffmpeg 转码——

`tools/tts_tool.py:2067-2071` @ 863e313

```python
    """Wrap raw signed-little-endian PCM with a standard WAV RIFF header.

    Gemini TTS returns audio/L16;codec=pcm;rate=24000 -- raw PCM samples with
    no container. We add a minimal WAV header so the file is playable and
    ffmpeg can re-encode it to MP3/Opus downstream.
```

   - 本地三家(neutts/piper/kittentts):**只会写 WAV**,由调用侧转。

3. **事后嗅探修正**(§3.5)。

**采样率**在流式路径上是**由 provider 声明、播放侧照办**:
`StreamingTTSProvider.sample_rate` 默认 24000,`sd.OutputStream(samplerate=streamer.sample_rate, …)`。
四个流式后端全部是 24kHz——所以实际上"协商"退化成了一个所有人都同意的常数。

---

## 4. 配置项与环境变量

### 4.1 DEFAULT_CONFIG 里的 `tts.*`

```verify
grep -cP '^tts\.' /home/user/hermes-study/data/r8a-config-keys.tsv
```

```console
41
```

41 个键(含 branch 节点),全部定义在 `hermes_cli/config_defaults.py:1425-1502`。
provider 默认值:

`hermes_cli/config_defaults.py:1425-1428` @ 863e313

```python
    "tts": {
        # Set explicitly to pin a backend:
        # "edge" (free) | "elevenlabs" (premium) | "openai" | "xai" | "minimax" | "mistral" | "gemini" | "deepinfra" | "neutts" (local) | "kittentts" (local) | "piper" (local)
        "provider": "edge",
```

**默认 edge 是一条明确的产品判断**:

`tools/tts_tool.py:488-495` @ 863e313

```python
def _get_provider(tts_config: Dict[str, Any]) -> str:
    """Get the explicitly configured TTS provider or the free default.

    Inference credentials do not imply consent to paid speech generation.
    Users opt into cloud TTS by setting ``tts.provider`` (normally through
    ``hermes tools``); otherwise the historical Edge backend remains active.
    """
    return (tts_config.get("provider") or DEFAULT_PROVIDER).lower().strip()
```

"有推理凭据 ≠ 同意付费语音"。同一条原则也写在 `check_tts_requirements` 上:
可用性必须与 dispatch 一一对应,不能拿无关的云凭据把 edge 说成可用。

`tools/tts_tool.py:3164-3168` @ 863e313

```python
    """Return whether the explicitly resolved TTS provider can run.

    Availability must mirror :func:`text_to_speech_tool` dispatch. Unrelated
    cloud credentials do not make the default Edge backend usable, and an
    explicitly selected backend is checked on its own requirements.
```

### 4.2 代码读、DEFAULT_CONFIG 里没有的键

搜索面:对 `tools/tts_tool.py` + `tools/tts_streaming.py` 里所有
`*_config.get("…")` / `section.get("…")` / `cfg.get("…")` 取键,与
`data/r8a-config-keys.tsv` 的 `tts.*` 41 行比对。

| 键 | 读取处 | DEFAULT_CONFIG | 文档 |
|---|---|---|---|
| `tts.speed`(全局) | `tools/tts_tool.py:1386`:`speed = float(edge_config.get("speed", tts_config.get("speed", 1.0)))` | 无 | 有(tts.md:48) |
| `tts.use_gateway` | `tools/tts_tool.py:3260`:`if cfg_api_key and not prefers_gateway("tts"):` | 无 | 有(nous-portal.md:225-227) |
| `tts.streaming.provider` | `tools/tts_streaming.py:201`:`streaming_cfg = tts_config.get("streaming") or {}` | 无 | 仅 `docs/streaming-tts.md:35` |
| `tts.voice` / `tts.model` / `tts.output_format` | `tools/tts_tool.py:774`:`voice = tts_config.get("voice") if isinstance(tts_config, dict) else None` | 无 | 无 |
| `tts.providers.<name>.*` | `tools/tts_tool.py:663`:`providers = _get_provider_section(tts_config, "providers")` | 无(用户自建) | 有(tts.md:259-362) |
| `tts.<p>.max_text_length` | `tools/tts_tool.py:437`:`override = prov_cfg.get("max_text_length") if prov_cfg else None` | 无(有注释) | 有(tts.md:177-185) |
| `tts.elevenlabs.base_url` / `.wss_url` | `tools/tts_tool.py:149`:`base_url = (el_config.get("base_url") or "").rstrip("/")` | 无 | 无 |
| `tts.elevenlabs.streaming_model_id` | `tools/tts_streaming.py:244`:`"streaming_model_id",` | 无 | 无 |
| `tts.gemini.base_url` / `tts.mistral.base_url` | `tools/tts_tool.py:2022`:`base_url = mi_config.get("base_url")` | 无 | 无 |
| `tts.openai.api_key` / `.language` | `tools/tts_tool.py:3258`:`cfg_api_key = openai_cfg.get("api_key") or ""` | 无 | 有 |
| `tts.minimax.region` / `group_id` / `emotion` / `sample_rate` / `bitrate` / `vol` / `pitch` | `tools/tts_tool.py:1897`:`emotion = mm_config.get("emotion", "neutral")` | 无 | region/vol/pitch 有;emotion/sample_rate/bitrate/group_id 无 |
| `tts.xai.text_normalization` / `speech_tags` / `streaming_url` | `tools/tts_tool.py:1766`:`xai_config.get("auto_speech_tags", xai_config.get("speech_tags")),` | 无 | text_normalization 有;后两个无 |
| `tts.piper.speaker_id` 等 7 个高级旋钮 | `tools/tts_tool.py:2637`:`_raw_speaker = piper_config.get("speaker_id", 0)` | 注释形式 | speaker_id 无,其余有 |
| `tts.kittentts.speed` / `clean_text` | `tools/tts_tool.py:2743`:`clean_text = kt_config.get("clean_text", True)` | 无 | 有 |
| `tts.deepinfra.speed` / `base_url` | `tools/tts_tool.py:1627`:`speed=float(di_config.get("speed", tts_config.get("speed", 1.0))),` | 注释形式 | 部分 |

### 4.3 环境变量

本簇**直接**用 `get_env_value` 读的只有 4 个,全是 base_url 覆盖,不是凭据:

```verify
cd /home/user/hermes-agent && grep -o 'get_env_value("[A-Z_]*")' tools/tts_tool.py tools/tts_streaming.py | grep -o '"[A-Z_]*"' | sort -u
```

```console
"GEMINI_BASE_URL"
"MINIMAX_GROUP_ID"
"OPENAI_BASE_URL"
"XAI_BASE_URL"
```

**凭据一律走 `_resolve_provider_key` → `resolve_provider_secret`**(config > env/.env > 凭据池):

`tools/tts_tool.py:78-91` @ 863e313

```python
def _resolve_provider_key(env_var: str, provider_id: str) -> str:
    """Resolve a TTS provider API key via the shared voice-key resolver.

    Delegates to ``tools.tool_backend_helpers.resolve_provider_secret`` —
    the single owner of STT/TTS key resolution (config > env/.env > the
    credential pool populated by ``hermes auth add <provider_id>``).
    Resolved at call time so tests that reload the helpers module see the
    live function.
    """
    try:
        from tools.tool_backend_helpers import resolve_provider_secret
    except ImportError:  # pragma: no cover — helpers are in-repo
        return str(get_env_value(env_var) or "").strip()
    return resolve_provider_secret(env_var, provider_id, env_getter=get_env_value)
```

经此解析的凭据变量:`ELEVENLABS_API_KEY`、`MINIMAX_API_KEY`、`MINIMAX_CN_API_KEY`、
`DEEPINFRA_API_KEY`、`GEMINI_API_KEY`、`GOOGLE_API_KEY`、`MISTRAL_API_KEY`;
OpenAI 侧经 `resolve_openai_audio_api_key`(`VOICE_TOOLS_OPENAI_KEY` → `OPENAI_API_KEY`,
两者都再过 `resolve_provider_secret`);xAI 侧经 `tools.xai_http.resolve_xai_http_credentials`
(OAuth 或 `XAI_API_KEY`)。

**为什么 `get_env_value` 要在函数里晚绑定**(而不是模块顶部 import):

`tools/tts_tool.py:63-69` @ 863e313

```python
def get_env_value(name, default=None):
    """Read env values through the live config module.

    Tests may monkeypatch and later restore ``hermes_cli.config.get_env_value``
    before this module is imported. Resolve the helper at call time so TTS does
    not keep a stale imported function for the rest of the test process.
    """
```

---

## 5. 测试作为行为规格

### 5.1 环境

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/pip list 2>/dev/null | tail -n +3 | wc -l
```

```console
89
```

Python 3.11.15,pytest 9.1.1。

**⚠ 本轮共享 venv 在我跑测试期间从 87 涨到 89**,必须记下来(CLAUDE.md 的"用例数是环境的函数"):
本轮开工时实测 **87**(= `[dev]` extra + `aiohttp 3.14.1` + `brotlicffi 1.2.0.1`,与 R8B 记录一致),
收工前复测 **89**。按"直接断言不要推断"去查 `site-packages/*.dist-info` 的时间戳,
新增的两个是 **`anthropic-0.87.0`** 与 **`docstring_parser-0.18.0`**——是并行的兄弟子代理装的,
不是我装的。两者都不被本簇任何 `importorskip` 门控,故对下面的数不构成解释;
但下面报的 292 是在 **89 包**环境下重跑取得的(跑前跑后各测一次包数,均为 89),
以保证"数与环境"成对。**`numpy` 在 89 包环境下仍然缺席**(见 §5.3)。

### 5.2 跑数

```verify
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/tools/test_tts_*.py tests/tools/test_audio_container.py \
  tests/agent/test_tts_registry.py tests/gateway/test_streaming_tts_consumer.py \
  tests/gateway/test_streaming_tts_gateway_regression.py tests/gateway/test_tts_media_routing.py \
  tests/gateway/test_base_auto_tts_output_format.py tests/hermes_cli/test_plugins_tts_registration.py \
  tests/hermes_cli/test_tts_picker.py tests/hermes_cli/test_setup_tts_xai_oauth.py \
  2>&1 | grep -E "^=== Summary"
```

```console
=== Summary: 36 files, 292 tests passed, 0 failed (100% complete) in 8.9s (8 workers) ===
```

**292 passed / 0 failed**;另有 3 个 skip,`run_tests.sh` 的 Summary 行不报 skip 数
(它把整文件 skip 显示为 `(1s, …)`),所以下面单独诊断。

### 5.3 三个 skip 的逐条诊断(**均属环境,非代码缺陷**)

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python -m pytest \
  tests/tools/test_tts_streaming.py tests/tools/test_tts_streaming_e2e.py -q -rs
```

```console
SKIPPED [1] tests/tools/test_tts_streaming.py:20: could not import 'numpy': No module named 'numpy'
SKIPPED [1] tests/tools/test_tts_streaming_e2e.py:26: ELEVENLABS_API_KEY not set
SKIPPED [1] tests/tools/test_tts_streaming_e2e.py:54: no streaming-capable TTS key set
```

1. **`test_tts_streaming.py` 整个文件被跳过**,因为 `numpy` 不在 `[dev]` extra 里。
   `tests/tools/test_tts_streaming.py:20` @ 863e313

```python
pytest.importorskip("numpy")
```

   **这是本簇最值得记的环境事实**:流式 TTS 的**唯一**单元测试文件(SentenceChunker、
   registry/resolver、分块播放路径、逐句同步兜底)在只装 `[dev]` 的环境里**一个用例都不跑**,
   而门禁只显示"0 failed"。`numpy` 是 `stream_tts_to_speaker` 播放路径的**真实运行时依赖**,
   不是"测试多要了个包":

   `tools/tts_tool.py:3597-3599` @ 863e313

```python
            assert streamer is not None
            if output_stream is not None:
                import numpy as _np
```

   缺的包:**numpy**(属平台/可选 extra,本轮按共享资源纪律未安装)。

2、3. `test_tts_streaming_e2e.py` 两个用例要真实凭据(设计如此,离线必跳)。

### 5.4 当行为规格用的几条

| 断言 | 锚点 + 摘录 |
|---|---|
| 内建名与分发器名集合不得漂移 | `tests/agent/test_tts_registry.py:211`:`assert tts_registry._BUILTIN_NAMES == BUILTIN_TTS_PROVIDERS, (` |
| 真 Ogg 文件不被动 | `tests/tools/test_tts_container_repair.py:60`:`def test_real_ogg_untouched(self, tmp_path):` |
| xAI 已有显式标签则不再改写(**用尖括号形式**) | `tests/tools/test_tts_xai_speech_tags.py:25`:`text = "Bonjour. [pause] <whisper>Déjà balisé.</whisper>"` |
| 辅助模型改写的结果必须真的发给 API | `tests/tools/test_tts_xai_speech_tags.py:66`:`def test_generate_xai_tts_sends_auxiliary_rewriter_output_to_api(` |
| 切句器在边界到达的那一刻就吐句 | `tests/tools/test_tts_streaming.py:28`:`def test_cuts_sentence_the_moment_its_boundary_arrives(self):`(本环境 skip) |

---

## 6. 定案

### ▲ 文档与代码矛盾(3 条)

**▲-1 `tts.md` 的平台投递表把 WhatsApp 写成 MP3 附件,代码已把它列入 Opus 语音条平台。**

判定范围:`### Platform Delivery` 标题(`website/docs/user-guide/features/tts.md:33`)
下的整张 4 行表。

`website/docs/user-guide/features/tts.md:35-40` @ 863e313

> | Platform | Delivery | Format |
> |----------|----------|--------|
> | Telegram | Voice bubble (plays inline) | Opus `.ogg` |
> | Discord | Voice bubble (Opus/OGG), falls back to file attachment | Opus/MP3 |
> | WhatsApp | Audio file attachment | MP3 |
> | CLI | Saved to `~/.hermes/audio_cache/` | MP3 |

代码侧 `whatsapp` 在 `OPUS_VOICE_PLATFORMS` 里(见 §2.3 摘录 `tools/tts_tool.py:632-642`),
网关按该集合直接给 `.ogg` 路径(§3.7 摘录 `gateway/platforms/base.py:178-187`),
并在 `voice_compatible` 时加 `[[audio_as_voice]]`。代码里那条注释还**点名**说明
"以前只认 Telegram,导致 Matrix/Feishu/WhatsApp/Signal 被合成成 MP3、渲染成坏附件"——
即文档描述的正是**已修复的旧行为**。表格同时漏了 Matrix / Feishu / Signal 三行。

**▲-2 同一张表把 CLI 默认目录写成 `~/.hermes/audio_cache/`,代码的新装默认是 `~/.hermes/cache/audio`。**

`tools/tts_tool.py:261-265` @ 863e313

```python
def _get_default_output_dir() -> str:
    from hermes_constants import get_hermes_dir
    return str(get_hermes_dir("cache/audio", "audio_cache"))

DEFAULT_OUTPUT_DIR = _get_default_output_dir()
```

`hermes_constants.py:278-282` @ 863e313

```python
    home = home or get_hermes_home()
    old_path = home / old_name
    if _legacy_path_has_content(old_path):
        return old_path
    return home / new_subpath
```

即 `audio_cache` **只在旧目录已存在且有内容时**才用;新装一律 `cache/audio`。
文档把兼容路径写成了默认路径。

**▲-3 command provider 的 `output_format` 取值集合,文档在同一节里自相矛盾且都与代码不符。**

判定范围:`### Custom command providers` 节内的两处。正文处列 8 个值(与代码一致):

`website/docs/user-guide/features/tts.md:288` @ 863e313

> **Supported `output_format` values:** `mp3` (default), `wav`, `ogg`, `flac`, `m4a`, `aac`, `amr`, `opus`. Your command must actually produce that format (e.g. via `ffmpeg`); Hermes only validates the declared value and names the output file accordingly. An unknown value falls back to `mp3`. The chosen format is also exposed to the command as the `{format}` placeholder.

而 `#### Optional keys` 表与 `#### Placeholders` 表只列 4 个:

`website/docs/user-guide/features/tts.md:347` @ 863e313

> | `output_format`    | `mp3`   | One of `mp3` / `wav` / `ogg` / `flac`. Auto-inferred from the output extension if Hermes picks a path.      |

代码:

`tools/tts_tool.py:627-629` @ 863e313

```python
COMMAND_TTS_OUTPUT_FORMATS = frozenset(
    {"mp3", "wav", "ogg", "flac", "m4a", "aac", "amr", "opus"}
)
```

同一行还有第二处不符:"Auto-inferred from the output extension **if Hermes picks a path**"
——方向反了。Hermes 自己挑路径时走的是**不带 path** 的
`_get_command_tts_output_format(command_provider_config)`(`tools/tts_tool.py:2913`),
即**用配置去定扩展名**;推断扩展名的分支只在传入了 `output_path` 时才有输入,
而那条路径又先被 `_configured_command_tts_output_path` 按配置改写过
(`tools/tts_tool.py:2895-2897`)。

### ◎ 文档成立但显著保守(1 条)

**◎-1 "没有 ffmpeg 时哪些 provider 退化成普通附件"漏了 xAI 与 Gemini。**

`website/docs/user-guide/features/tts.md:211` @ 863e313

> Without ffmpeg, Edge TTS, MiniMax TTS, NeuTTS, KittenTTS, and Piper audio are sent as regular audio files (playable, but shown as a rectangular player instead of a voice bubble).

字面为真(这五家确实如此),但**同一节**的 `:194` 与 `:195` 已经写明 Gemini 与 xAI 也依赖 ffmpeg;
代码侧 `xai` 在需要 `_convert_to_opus` 的集合里(§2.7 摘录 `tools/tts_tool.py:3115-3125`),
Gemini 无 ffmpeg 时把 WAV 原样拷到目标路径:

`tools/tts_tool.py:2406-2411` @ 863e313

```python
        else:
            logger.warning(
                "ffmpeg not found; writing raw WAV to %s (extension may be misleading)",
                output_path,
            )
            shutil.copyfile(wav_path, output_path)
```

字面为真故不计 ▲。

### ◇ 代码有、文档无(4 条)

**◇-1 五个配置键在全部用户可见文档里零命中。**

搜索面:`website/docs/`(全站)+ `docs/` + `README.md` + `AGENTS.md` + `.env.example`,
逐键 `grep -rn`;`speech_tags` 另用 `grep -rnE '\bspeech_tags'` 以排除 `auto_speech_tags` 的子串命中。

```verify
cd /home/user/hermes-agent && for k in speaker_id streaming_url streaming_model_id wss_url; do
  echo -n "$k => "; grep -rn -- "$k" website/docs/ docs/ README.md AGENTS.md .env.example 2>/dev/null | wc -l; done
echo -n "\\bspeech_tags => "; grep -rnE '\bspeech_tags' website/docs/ docs/ README.md AGENTS.md .env.example 2>/dev/null | wc -l
```

```console
speaker_id => 0
streaming_url => 0
streaming_model_id => 0
wss_url => 0
\bspeech_tags => 0
```

对应读取点:`tts.piper.speaker_id`(`tools/tts_tool.py:2637`)、
`tts.xai.streaming_url`(`tools/tts_streaming.py:454`)、
`tts.elevenlabs.streaming_model_id`(`tools/tts_streaming.py:243-246`)、
`tts.elevenlabs.wss_url`(`tools/tts_tool.py:152`)、
`tts.xai.speech_tags`(`tools/tts_tool.py:1766`,`auto_speech_tags` 的兼容别名)。

**◇-2 TTS 插件 provider 的 per-provider 配置命名空间与 STT 插件相反,且无文档。**

`tools/tts_tool.py:774-781` @ 863e313

```python
    voice = tts_config.get("voice") if isinstance(tts_config, dict) else None
    model = tts_config.get("model") if isinstance(tts_config, dict) else None
    speed = tts_config.get("speed") if isinstance(tts_config, dict) else None
    fmt = (
        tts_config.get("output_format", DEFAULT_COMMAND_TTS_OUTPUT_FORMAT)
        if isinstance(tts_config, dict)
        else DEFAULT_COMMAND_TTS_OUTPUT_FORMAT
    )
```

即插件拿到的是 **`tts.voice` / `tts.model` / `tts.speed` / `tts.output_format`(顶层)**,
不是内建 provider 用的 `tts.<name>.voice`。而 STT 的插件契约文档明写是分节的:

`website/docs/user-guide/features/tts.md:636` @ 863e313

> Plugins read their per-provider configuration from `stt.<provider>` in `config.yaml`, mirroring how built-ins read `stt.openai.model` / `stt.mistral.model`:

TTS 文档的 `### Python plugin providers` 一节(`:364-441`)**从头到尾没有说**插件的
voice/model/speed 从哪个键读。后果:两个插件 provider 无法各自配置声音——顶层只有一份。

**◇-3 `tts.gemini.audio_tags` 除了布尔,还接受 `{enabled: …}` 字典形式,文档只写布尔。**

`tools/tts_tool.py:2134-2138` @ 863e313

```python
def _gemini_audio_tags_enabled(gemini_config: Dict[str, Any], model: str) -> bool:
    raw = gemini_config.get("audio_tags")
    if isinstance(raw, dict):
        raw = raw.get("enabled")
    enabled = _config_bool(raw, default=DEFAULT_GEMINI_AUDIO_TAGS)
```

**◇-4 流式 TTS 在用户站点文档(`website/docs/`)里完全不存在,只在仓库内 `docs/streaming-tts.md`。**

搜索面:`grep -rn 'tts.streaming\|streaming.*TTS' website/docs/` 与
`grep -rn 'tts.streaming' website/docs/ docs/ README.md AGENTS.md .env.example`。

```verify
cd /home/user/hermes-agent && grep -rn -- "tts.streaming" website/docs/ docs/ README.md AGENTS.md .env.example 2>/dev/null
```

```console
docs/streaming-tts.md:15:2. **Sentence chunker** — `tools.tts_streaming.SentenceChunker` accumulates
docs/streaming-tts.md:35:To override, set `tts.streaming.provider` in your `config.yaml`:
docs/streaming-tts.md:69:1. Subclass `StreamingTTSProvider` in `tools/tts_streaming.py`
docs/streaming-tts.md:74:5. Add tests in `tests/tools/test_tts_streaming.py`
```

四条命中全在 `docs/streaming-tts.md` 一个文件里,其中三条其实是模块名
`tools.tts_streaming` 的子串,真正提到配置键 `tts.streaming.provider` 的只有 `:35` 一条。
`website/docs/` 下**零命中**——用户看的 `website/docs/user-guide/features/tts.md`(718 行)
通篇没有 streaming 一节。

### ■ 代码缺陷(5 条)

**■-1(实测)xAI 的"用户已显式打标签就别再改写"守卫,认不出它自己规定的合法写法。**

`_XAI_SPEECH_TAG_RE` 的**包裹型**标签分支只匹配**尖括号**形式 `<whisper>…</whisper>`:

`tools/tts_tool.py:1665-1668` @ 863e313

```python
_XAI_SPEECH_TAG_RE = re.compile(
    r"(\[(?:" + "|".join(_XAI_INLINE_SPEECH_TAGS) + r")\]|</?(?:" + "|".join(_XAI_WRAPPING_SPEECH_TAGS) + r")>)",
    flags=re.IGNORECASE,
)
```

而**同一个文件里的系统提示词**明确禁止尖括号、要求 BBCode 式 `[tag]…[/tag]`:

`tools/tts_tool.py:1716-1717` @ 863e313

```python
        "- Use wrapping `[tag]...[/tag]` for sustained effects (whisper, soft, slow, fast, loud, etc.).\n"
        "- Do not use angle-bracket tags like `<tag>...</tag>` — xAI uses BBCode-style closing tags with `[/tag]`.\n"
```

于是守卫失效:

`tools/tts_tool.py:1699-1702` @ 863e313

```python
    # If the user/model already supplied explicit speech tags, trust them
    # and don't re-rewrite.
    if _XAI_SPEECH_TAG_RE.search(clean):
        return local
```

实测(直接调基线模块,只读):

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python -c "
from tools.tts_tool import _XAI_SPEECH_TAG_RE
for s in ['[whisper]Deja balise.[/whisper]', '<whisper>Deja balise.</whisper>', '[emphasis]x[/emphasis]', '[pause]']:
    print(repr(s), '-> match:', bool(_XAI_SPEECH_TAG_RE.search(s)))
"
```

```console
'[whisper]Deja balise.[/whisper]' -> match: False
'<whisper>Deja balise.</whisper>' -> match: True
'[emphasis]x[/emphasis]' -> match: False
'[pause]' -> match: True
```

**后果**:用户按 xAI 官方 / 本仓提示词的写法手写 `[whisper]…[/whisper]`,
在 `auto_speech_tags: true` 时仍会被送去辅助模型重写一遍——多一次 LLM 调用,
且用户的原始表演意图可能被覆盖。现有测试恰好只钉了尖括号那一支
(`tests/tools/test_tts_xai_speech_tags.py:25`),所以这条一直是绿的。

**■-2(推定,本容器无 ffmpeg 未能实测)`.ogg` 输出对三个本地 WAV provider 会产出 Ogg/Vorbis,
而容器修复只看容器不看编解码,直接放行。**

Gemini 分支明确加了 `-acodec libopus`,并**在注释里写明 ffmpeg 对 `.ogg` 的默认是 Vorbis**:

`tools/tts_tool.py:2389-2402` @ 863e313

```python
            # For .ogg output, force libopus encoding (Telegram voice bubbles
            # require Opus specifically; ffmpeg's default for .ogg is Vorbis).
            if output_path.lower().endswith(".ogg"):
                cmd = [
                    ffmpeg, "-i", wav_path,
                    "-acodec", "libopus", "-ac", "1",
                    "-b:a", "48k", "-vbr", "on",
                    "-application", "voip", "-compression_level", "10",
                    "-y", "-loglevel", "error",
                    output_path,
                ]
            else:
                cmd = [ffmpeg, "-i", wav_path, "-y", "-loglevel", "error", output_path]
            result = subprocess.run(cmd, capture_output=True, timeout=30, stdin=subprocess.DEVNULL, creationflags=windows_hide_flags())
```

Piper 的同类转换**没有**这个分支:

`tools/tts_tool.py:2700-2704` @ 863e313

```python
    if wav_path != output_path:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            conv_cmd = [ffmpeg, "-i", wav_path, "-y", "-loglevel", "error", output_path]
            subprocess.run(conv_cmd, check=True, timeout=30, stdin=subprocess.DEVNULL, creationflags=windows_hide_flags())
```

NeuTTS(`tools/tts_tool.py:2494-2497`)与 KittenTTS 是同一份写法:

`tools/tts_tool.py:2766-2771` @ 863e313

```python
    if wav_path != output_path:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            conv_cmd = [ffmpeg, "-i", wav_path, "-y", "-loglevel", "error", output_path]
            subprocess.run(conv_cmd, check=True, timeout=30, stdin=subprocess.DEVNULL, creationflags=windows_hide_flags())
            os.remove(wav_path)
```

而网关自动 TTS 对 telegram/matrix/feishu/whatsapp/signal **明确传 `.ogg` 路径**
(§3.7 摘录),此时 `wav_path != output_path` 成立,走的正是这条裸 ffmpeg 分支。
产出的文件魔数是 `OggS`,`_repair_ogg_container` 判定 `container == "ogg"` 直接返回
(§3.5 摘录 `tools/tts_tool.py:1341-1345`),测试也把这条钉死了
(`tests/tools/test_tts_container_repair.py:60`:`def test_real_ogg_untouched(self, tmp_path):`)。

与之矛盾的是网关侧的承诺:

`gateway/platforms/base.py:172-176` @ 863e313

```python
    (``tools.tts_tool.OPUS_VOICE_PLATFORMS`` — the single source of truth)
    get an explicit ``.ogg`` path; the tool's central container repair
    (``_repair_ogg_container``) then guarantees real Ogg/Opus bytes for every
    provider, including MP3-only backends like Edge TTS. Everything else
    keeps the MP3 default.
```

对 Edge(把 MP3 塞进 `.ogg`)这个保证成立;对本地三家(自己先转成了 Ogg/Vorbis)不成立。

**未验证部分**:本容器 `which ffmpeg` 为空,无法实跑确认转码结果确为 Vorbis。
"ffmpeg 对 `.ogg` 默认 Vorbis"这一事实取自**基线自身的注释**(`tools/tts_tool.py:2390`),
不是我的外部知识。修复方向也现成:这三处应改调 `_ffmpeg_transcode_to_opus`。

**■-3 工具 schema 的 provider 枚举漏了 `deepinfra`,模型无法从 schema 发现它。**

`tools/tts_tool.py:3937-3946` @ 863e313

```python
            "provider": {
                "type": "string",
                "description": (
                    "Optional TTS provider override. Accepts built-in names "
                    "(edge, openai, elevenlabs, minimax, xai, mistral, gemini, "
                    "neutts, kittentts, piper), user-declared command provider "
                    "names from tts.providers.<name>, or plugin-registered names. "
                    "When omitted, the configured tts.provider from config.yaml is used."
                )
            }
```

10 个名字,少 `deepinfra`;但 `BUILTIN_TTS_PROVIDERS` 有 11 个(§3.1 摘录),
且 dispatch 分支真实存在:

`tools/tts_tool.py:2973-2982` @ 863e313

```python
        elif provider == "deepinfra":
            try:
                _import_openai_client()
            except ImportError:
                return json.dumps({
                    "success": False,
                    "error": "DeepInfra TTS uses the 'openai' SDK but it isn't installed."
                }, ensure_ascii=False)
            logger.info("Generating speech with DeepInfra TTS...")
            _generate_deepinfra_tts(text, file_str, tts_config)
```

同一处遗漏还出现在 `text_to_speech_tool` 的 docstring:

`tools/tts_tool.py:2807-2812` @ 863e313

```python
        provider: Optional TTS provider override. When set, bypasses the
            configured ``tts.provider`` and uses this provider instead.
            Accepts built-in names (``edge``, ``openai``, ``elevenlabs``,
            ``minimax``, ``xai``, ``mistral``, ``gemini``, ``neutts``,
            ``kittentts``, ``piper``), user-declared command provider names
            from ``tts.providers.<name>``, or plugin-registered provider
```

以及两个 ABC/registry 模块的 docstring:

`agent/tts_registry.py:11-17` @ 863e313

```python
Built-ins-always-win
--------------------
Plugin names that collide with a built-in TTS provider (``edge``,
``openai``, ``elevenlabs``, ``minimax``, ``gemini``, ``mistral``,
``xai``, ``piper``, ``kittentts``, ``neutts``) are rejected at
registration with a warning. This invariant is also re-checked at
dispatch time in :func:`tools.tts_tool._dispatch_to_plugin_provider`.
```

(`agent/tts_provider.py:79-81` 是同一份 10 名清单。)
`TestBuiltinSync` 只比对两个**常量集合**,管不到这四处散文。

**■-4 同一个函数对"默认输出目录"给出三种互不相同的说法。**

`tools/tts_tool.py:2795-2801` @ 863e313

```python
    On messaging platforms, the returned MEDIA:<path> tag is intercepted
    by the send pipeline and delivered as a native voice message.
    In CLI mode, the file is saved to ~/voice-memos/.

    Args:
        text: The text to convert to speech.
        output_path: Optional custom save path. Defaults to ~/voice-memos/<timestamp>.mp3
```

docstring 说 `~/voice-memos/`;同文件的 schema 说 `<hermes_home>/audio_cache/`:

`tools/tts_tool.py:3920-3923` @ 863e313

```python
            "output_path": {
                "type": "string",
                "description": f"Optional custom file path to save the audio. Defaults to {display_hermes_home()}/audio_cache/<timestamp>.mp3"
            },
```

实际是 `get_hermes_dir("cache/audio", "audio_cache")`(§▲-2 摘录),新装为 `~/.hermes/cache/audio`。
其中 schema 那份是**模型可见**的,影响模型对 `output_path` 缺省行为的判断。

**■-5(实测,轻)文本规范化会把带内点的缩写拆开:`U.S.A.` → `U. S. A.`、`i.e.` → `i. e.`。**

`tools/tts_text_normalize.py:206-207` @ 863e313

```python
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])([A-Za-z])", r"\1 \2", text)
```

这条规则本意是给"压平换行后粘在一起的句子"补空格(`sunny.It will` → `sunny. It will`),
缩写是附带损伤。数字不受影响(要求后接 `[A-Za-z]`)。

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python -c "
from tools.tts_text_normalize import prepare_spoken_text
for c in ['The U.S.A. and e.g. Dr. Smith.', 'Version 3.11.15 is out.']:
    print(repr(c), '->', repr(prepare_spoken_text(c)))
"
```

```console
'The U.S.A. and e.g. Dr. Smith.' -> 'The U. S. A. and e. g. Dr. Smith.'
'Version 3.11.15 is out.' -> 'Version 3.11.15 is out.'
```

影响有限(多数引擎对 `U. S. A.` 与 `U.S.A.` 读法接近),记为轻级。

### 观察项(不计记号)

- **`tts_text_normalize.py` 的模块 docstring 声称"非 ASCII 一律写成转义"**
  (`tools/tts_text_normalize.py:7-8`),但同文件里的 `°`(`:119-123`)、
  `•◦▪▫→⇒≈`(`:148-152`)、以及 emoji 正则最后一段都是**字面量**:

  `tools/tts_text_normalize.py:48-53` @ 863e313

```python
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "☀-➿"
    "]+",
    flags=re.UNICODE,
)
```

- **`tools/tts_streaming.py:47` 的 docstring 说"所有流式 provider 的取钥都走 `_resolve_key`"**,
  但 `OpenAIStreamer` 没有用它:

  `tools/tts_streaming.py:270-272` @ 863e313

```python
    @staticmethod
    def available() -> bool:
        return bool(_openai_config_api_key() or resolve_openai_audio_api_key())
```

  实质无害——`resolve_openai_audio_api_key` 内部同样委托 `resolve_provider_secret`,
  故不计 ▲/■:

  `tools/tool_backend_helpers.py:272-275` @ 863e313

```python
    return (
        resolve_provider_secret("VOICE_TOOLS_OPENAI_KEY", "")
        or resolve_provider_secret("OPENAI_API_KEY", "openai-api")
    )
```

- **七个 registry 无共用基类**(§3.1),各自 ~130 行复制。是待抽象点,不是缺陷。
- **`_speak_sentence` 的去重表无上界**,逐句 O(n) 线性比对且**永久**丢弃重复句;
  长会话里既是 O(n²) 也可能吞掉合法的重复应答。因 `SentenceChunker(min_len=20)`
  会把短句并进下一句,实际触发概率不高。

  `tools/tts_tool.py:3520-3522` @ 863e313

```python
        long_flush_len = 100
        queue_timeout = 0.5
        _spoken_sentences: list[str] = []  # track spoken sentences to skip duplicates
```

---

## 7. 移交项

| # | 锚点 + 摘录 | 一句话现象 |
|---|---|---|
| H-R9B-a | `tools/tts_tool.py:2703`:`conv_cmd = [ffmpeg, "-i", wav_path, "-y", "-loglevel", "error", output_path]` | ■-2 的 Vorbis 推定**未实测**(本容器 `which ffmpeg` 为空);任何有 ffmpeg 的环境跑一次 `ffprobe` 即可定案:neutts/piper/kittentts 三处裸转码,`.ogg` 目标时产出的编解码到底是不是 Vorbis |
| H-R9B-b | `tests/tools/test_tts_streaming.py:20`:`pytest.importorskip("numpy")` | 流式 TTS 唯一的单元测试文件在只装 `[dev]` 的环境里 **0 用例执行**,门禁仍显示 0 failed;下一轮若要把流式当行为规格引用,必须先装 numpy 或在报告里明记"未执行" |
| H-R9B-c | `tools/tts_tool.py:774`:`voice = tts_config.get("voice") if isinstance(tts_config, dict) else None` | ◇-2:TTS 插件从**顶层** `tts.voice/model/speed/output_format` 取参,与 STT 插件文档化的 `stt.<provider>.*` 分节契约相反;需确认是有意设计还是遗漏(影响"两个插件 provider 能否各自配声音") |
| H-R9B-d | `tools/tts_tool.py:1666`:`r"(\[(?:" + "|".join(_XAI_INLINE_SPEECH_TAGS) + r")\]|</?(?:" + "|".join(_XAI_WRAPPING_SPEECH_TAGS) + r")>)",` | ■-1:包裹型标签的检测正则用尖括号,与本文件系统提示词要求的 `[tag]…[/tag]` 相反;修复面还需查 xAI 官方到底接受哪种(本轮未查 xAI 文档,只在仓内取证) |
| H-R9B-e | `tools/tts_tool.py:3522`:`_spoken_sentences: list[str] = []  # track spoken sentences to skip duplicates` | 观察项:流式去重表无上界、永久丢弃重复句;未评估长会话下的实际影响 |
| H-R9B-f | `website/docs/user-guide/features/tts.md:39`:`| WhatsApp | Audio file attachment | MP3 |` | ▲-1 只核到了 TTS 工具这一侧(生成 `.ogg` + 打 `[[audio_as_voice]]`);**未核** WhatsApp 适配器收到该标记后实际怎么发,R9 后续簇若覆盖 gateway 平台层应回补 |
| H-R9B-g | (环境,非基线文件)`/home/user/hermes-venv`:`anthropic-0.87.0` + `docstring_parser-0.18.0` | 共享 venv 在 R9B 期间被并行子代理从 **87 包**装到 **89 包**;本簇的 292 已在 89 包下重跑取过一次,但**同轮其他子代理若在 87 包下取数,两份数不可直接比**;下一轮报测试数前先测包数 |
