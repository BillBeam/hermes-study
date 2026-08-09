# R9B · 多模态交付面

多模态交付面读完,表格锚点补上校验。

> 本轮范围以台账 `round=R9B` 为准。全部锚点针对基线
> `863e31318553cda8ad61df681d08175364d4164b`(下称 `863e313`)。

## 1. 开工先核范围

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{for(i=1;i<=6;i++) sub(/\r$/,"",$i); if($5=="R9B"){n++; l+=$3}} END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

开工读数 **46 文件 / 27,325 行**,与任务书给的数一致,无需修订。

本簇是**多模态交付面**:agent 怎么把结果交付给人、怎么接收人给的非文本输入。
按机制切六片派工,切分**逐文件核对过覆盖**(无遗漏、无重叠,脚本核过):

| 片 | 文件数 | 行数 | 内容 |
|---|---|---|---|
| A 图像生成与路由 | 6 | 3,581 | `agent/image_gen_provider.py`、`image_gen_registry.py`、`image_routing.py`、`tools/image_generation_tool.py`、`image_source.py`、`fal_common.py` |
| B 视频生成 | 5 | 2,756 | `agent/video_gen_provider.py`、`video_gen_registry.py`、`tools/video_generation_tool.py`、`flux3_video_tool.py`、`xai_video_tools.py` |
| C 语音合成 TTS | 7 | 5,345 | `agent/tts_provider.py`、`tts_registry.py`、`tools/tts_tool.py`、`tts_streaming.py`、`tts_text_normalize.py`、`neutts_synth.py`、`audio_container.py` |
| D 语音输入与唤醒 | 5 | 6,776 | `agent/transcription_provider.py`、`transcription_registry.py`、`tools/transcription_tools.py`、`voice_mode.py`、`wake_word.py` |
| E 视觉理解与终端呈现 | 12 | 5,214 | `tools/vision_tools.py`、`agent/display.py` 等 12 个 |
| F 虚拟宠物 pet | 11 | 3,653 | `agent/pet/` 全部 |
| **合计** | **46** | **27,325** | 与台账一字不差 |

## 2. 开工杂项:H-R9A-h 结清(本轮验收项 ①)

**移交项说的是「移交表格行内的锚点恒记 UNCHECKED、从不被任何一次校验碰过」。
实测下来这个盲区比移交项描述的大一个数量级。**

### 2.1 盲区实测

配对规则是「锚点 → **紧跟其后**的块」,而 Markdown 表格行后面永远是下一行表格,
于是写在表格里的锚点**永远配不上块**。全语料实测:

```text
语料内(非围栏)引用总数 ≈ 15,471
其中位于表格行内 = 1,569  (10.1%)
```

**不止移交表——是全语料 10.1% 的引用从未被任何东西比对过。**

### 2.2 处置:改脚本,把表格行的**内联**摘录纳入校验

表格行把摘录写在行内,所以脚本改为把锚点与**紧跟其后的那一个反引号片段**配对:

```text
| ... | `hermes_cli/commands.py:1275`:`_SLACK_VIA_HERMES_ONLY = frozenset({...})` | ... |
| ... | `gateway/relay/media.py:92` 的 `is_relay_media_url`                        | ... |
```

判定分五档:落在 `[锚点, 锚点+12]` 内 → `TABLE-OK`;摘录正好是锚点所在函数/类的头行
→ `TABLE-OK`(格子指的是外层构造,是正当写法);在 ±40 行内找得到但两条都不满足
→ `TABLE-DRIFT`(**阻断**);行号越界 → `TABLE-OUT-OF-RANGE`(**阻断**);
找不到或没有声明式摘录 → `TABLE-UNCHECKED`。

**只认「紧跟锚点」那一个片段,不扫全行。** 初版扫全行,55 处命中里约四分之三是
「本格提了个符号名,而它恰好在文件别处出现过」。猜作者指的是哪一次出现正是关卡变噪音的方式;
`text/console/verify` 那一栏早已定下同一条原则:**声明,不靠嗅探**。

**表格锚点单独计数,不并入 `citations` 总数。** 1,700 余个多为散文的表格格子
会把可校验比例拉走约 30 个点,而那是跨轮比较用的数。

### 2.3 落地即阻断,因为积压在同一轮清零了

不走 R7C→R8A / R8C→R8D 那种「先加查、后升格」的分期——那个分期是为了避免关卡
对着自己没造成的积压狂叫。本轮全语料 **5 处真漂移全部改正**:

| 位置 | 原写 → 改为 | 依据 |
|---|---|---|
| `notes/r7c-raw-slash-c.md:1335` 的 `_SLACK_VIA_HERMES_ONLY` | `:1276` → `:1275` | 赋值语句在 `:1275`,`:1276` 是空行 |
| `notes/r8a-raw-pairing-and-config-cmd.md:1231` 的 `--force` | `:45-47` → `:44-47` | `--force` 字面量在 `:44`,原范围把它切在外面 |
| `reports/round-8c-dashboard-and-web.md:357` 的 `upload-stream` | `:2488` → `:2487` | 路由字面量在装饰器行 `:2487` |
| `reports/round-8c-dashboard-and-web.md:359` 的 `_SECRET_SOURCES` | `:667` → `:666` | 赋值在 `:666` |
| `reports/round-8d-cli-completion.md:426` 的 `_SECRET_SOURCES` | `:667` → `:666` | 同上,由 R8C 原样复制传下 |

**后三处正是移交项点名的那两条 R8D 一行漂移(其中一条被复制成两份)。**
它们历经 R8D / R9A 两轮"引用关卡全绿",因为**没有任何一次校验读过它们**。
`reports/` 两份按 CLAUDE.md「正文不静默改写,唯一例外是引用行号」处理:
只改行号,并各自新增**勘误节**点名。

### 2.4 关卡不是空绿(负控自检)

造一份含五种形态的自检文件跑一遍:

```text
| 正确锚点 | `hermes_cli/env_loader.py:666`:`_SECRET_SOURCES`     | 应 TABLE-OK           |
| 漂 1 行  | `hermes_cli/env_loader.py:667`:`_SECRET_SOURCES`     | 应 TABLE-DRIFT        |
| 漂 20 行 | `hermes_cli/env_loader.py:646`:`_SECRET_SOURCES`     | 应 TABLE-DRIFT        |
| 越界     | `hermes_cli/env_loader.py:999999`:`_SECRET_SOURCES`  | 应 TABLE-OUT-OF-RANGE |
| 纯散文   | `hermes_cli/env_loader.py:666` 讲的是密钥来源表        | 应 TABLE-UNCHECKED    |
```

实跑输出 `table_anchors=5 DRIFT=2 OK=1 OUT-OF-RANGE=1 UNCHECKED=1`,**退出码 1**,五档全部符合预期。
其中「同一函数内漂 20 行」这一档是**本轮中途加严**的结果:第一版为压假阳性加了
「同构造内只有相邻才算漂移」的豁免,实测发现在「只认紧跟锚点的声明式摘录」之后
该豁免对真实语料**零收益**(去掉后全语料 DRIFT 数不变),遂删除——
它唯一的作用是放过一类真漂移。

### 2.5 制度落账

CLAUDE.md 已写入:第四类块的判定规则、`enclosing_headers` 两条豁免的理由、
覆盖面的如实交代,以及一条新硬规——**移交表的锚点必须用声明式写法**
(锚点后紧跟反引号摘录),否则它照旧记 TABLE-UNCHECKED。
移交表是唯一会被下一轮当作起点直接使用的东西,它漂了就是下一轮直接找错地方。

**覆盖面如实说**:未声明摘录的表格锚点(1,710 中的 1,623)仍是 UNCHECKED。
本关卡把下限从「表格锚点一个都不查」抬到「**声明了指向什么的表格锚点必被查**」,
**不是把表格全查了**。

## 3. 台账报数

```verify
cd /home/user/hermes-study && python3 scripts/verify_ledger.py /home/user/hermes-agent data/ledger.tsv
```

```text
OK baseline=863e31318 files=8530 total_lines=2608452
  L1: files=563 lines=522207
  L2: files=2131 lines=671639
  L3: files=1895 lines=602085
  L4: files=560 lines=55902
  LT: files=3381 lines=756619
  SUM == repo total: 2608452
```

五层加总 = 全仓总行数 **2,608,452**,守恒。本轮 46 个文件的 `status`
由 `R1-inventoried` 转 **`R9B-deep-read`**。

**恢复必报项 —— `R1-inventoried` 剩余**:

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$6); if($6=="R1-inventoried"){n++; l+=$3}} END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

**7,832 文件 / 2,008,064 行**(开工时 7,878 / 2,035,389,本轮减 46 文件 / 27,325 行)。

## 4. L1 全量 deep-read 的剩余判定(本轮验收项 ②)

| | 文件 | 行数 |
|---|---|---|
| 已 deep-read(R2–R9A + 本轮 R9B) | 467 | 476,499 |
| **仍未 deep-read** | **96** | **45,708** |
| L1 合计 | 563 | 522,207 |

**剩余轮次:两轮。** 剩余 96 文件全部已定轮,无无主文件:

| 轮 | 文件 | 行数 |
|---|---|---|
| R9C | 47 | 19,274 |
| R9D | 49 | 26,434 |

**对 R12 的后果**:R8D 的 H-R8D-i 判定「R12 的前置条件是『L1 全部 deep-read』
而非『R11 做完』」,R9A 把它量化为「再做完 R9B / R9C / R9D 三轮」。
本轮做完 R9B,**该数字更新为:再做完 R9C / R9D 两轮**,与 R10 / R11 进度无关。
按本轮实测的单轮容量(46 文件 / 27,325 行),R9C(19,274 行)与 R9D(26,434 行)
都在已验证的容量之内,**不需要再拆**。

## 5. 定案

### 5.1 记号报数

| 簇 | ▲ | ◇ | ■ | ◎ |
|---|---|---|---|---|
| A 图像 | 4 | 3 | 1 | 0 |
| B 视频 | 3 | 3 | 6 | 1 |
| C TTS | 3 | 4 | 5 | 1 |
| D 语音输入 | 4 | 1 | 2 | 2 |
| E 视觉与呈现 | 2 | 4 | 2 | 1 |
| F pet | 1 | 3 | 2 | 1 |
| **合计** | **17** | **18** | **18** | **6** |

合计 59 条。**六簇各自计数,未做跨簇去重**,合计数不宜直接用于跨轮比较。

### 5.2 主线全链复核的四条(实跑,不是照抄底稿)

**■ D-1:配好 DeepInfra 转录后端时「喊得醒,开不了口」。**
权威名单八个内置转录后端:

`tools/transcription_tools.py:341-350 @ 863e313`

```python
BUILTIN_STT_PROVIDERS = frozenset({
    "local",
    "local_command",
    "groq",
    "openai",
    "mistral",
    "xai",
    "elevenlabs",
    "deepinfra",
})
```

语音模式里那份副本只有七个,漏了最后一个:

`tools/voice_mode.py:2193-2201 @ 863e313`

```python
    native_stt_available = stt_provider in {
        "local",
        "local_command",
        "groq",
        "openai",
        "mistral",
        "xai",
        "elevenlabs",
    }
```

唤醒词那侧用第三种写法,而它的 docstring **自称与语音模式同一套标准**:

`tools/wake_word.py:808-810 @ 863e313`

```python
    A wake without STT arms the mic but every captured utterance dies at
    transcription — a useless (and confusing) experience. Same standard as
    voice mode's ``check_voice_requirements``: enabled + a real provider.
```

主线实跑对照(两个密钥都设好,这一步是关键——首次复现两侧都是 `False`,
因为两个密钥都没设,补上才隔离出差异):

```text
  groq        voice_mode.stt_available=True    wake_word._stt_ready()=True
  deepinfra   voice_mode.stt_available=False   wake_word._stt_ready()=True
```

**「能唤醒,不能说话」是跑出来的,不是读码推断的。**

**■ C-1:提示词要求方括号,检测器只认尖括号。**

`tools/tts_tool.py:1716-1717 @ 863e313`

```python
        "- Use wrapping `[tag]...[/tag]` for sustained effects (whisper, soft, slow, fast, loud, etc.).\n"
        "- Do not use angle-bracket tags like `<tag>...</tag>` — xAI uses BBCode-style closing tags with `[/tag]`.\n"
```

`tools/tts_tool.py:1665-1668 @ 863e313`

```python
_XAI_SPEECH_TAG_RE = re.compile(
    r"(\[(?:" + "|".join(_XAI_INLINE_SPEECH_TAGS) + r")\]|</?(?:" + "|".join(_XAI_WRAPPING_SPEECH_TAGS) + r")>)",
    flags=re.IGNORECASE,
)
```

主线导入基线模块实跑:`'[whisper]x[/whisper]'` → `False`(提示词**要求**的写法),
`'<whisper>x</whisper>'` → `True`(提示词**禁止**的写法)。
后果由它自己的注释点明:

`tools/tts_tool.py:1699-1702 @ 863e313`

```python
    # If the user/model already supplied explicit speech tags, trust them
    # and don't re-rewrite.
    if _XAI_SPEECH_TAG_RE.search(clean):
        return local
```

按规定写法手打标签的用户**拿不到这份信任**,文本会被送去辅助模型重写。

**■ A-1:schema 对模型承诺可传本地路径,默认后端原样透传不读文件。**

`tools/image_generation_tool.py:1198-1204 @ 863e313`

```python
                    "Optional source image to edit/transform (image-to-image). "
                    "When provided, the active backend routes to its image "
                    "editing endpoint; when omitted, it generates from text "
                    "alone. Pass a public URL or an absolute local file path "
                    "from the conversation. Only honored by models that "
                    "support editing — the description above indicates whether "
                    "the active model does."
```

`tools/image_generation_tool.py:640-642 @ 863e313`

```python
    payload: Dict[str, Any] = dict(meta.get("defaults", {}))
    payload["prompt"] = (prompt or "").strip()
    payload["image_urls"] = list(image_urls)
```

**▲ E-1:文档少列一种界面语言,同一句还断言它不工作。**

`agent/i18n.py:43-46 @ 863e313`

```python
SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "en", "zh", "zh-hant", "ja", "de", "es", "fr", "tr", "uk",
    "af", "ko", "it", "ga", "pt", "ru", "hu", "ar",
)
```

`website/docs/user-guide/configuration.md:1727` 只列 16 种(缺 `ar`),
且**同一句**以 "Unknown values fall back to English." 收尾;管辖标题是
`website/docs/user-guide/configuration.md:1723` 的 `### UI language for static messages`。
主线另核:`locales/ar.yaml`、`en.yaml`、`zh.yaml` 叶子键**各 351(相等)**,
`tests/agent/test_i18n.py:40` 与 `:51` 两处参数化都遍历 `SUPPORTED_LANGUAGES` 故覆盖 `ar`。
**「列漏了但其实完全能用」才使 ▲ 成立**——若只是少说一个数,那是 ◎ 不是 ▲。

### 5.3 主线独立取证:R9A 移交的两条(凭据发往何处)

**■ H-R9A-d(结清,现象属实但两侧都要修正)**:
`tools/skills_sync_client.py:307` 的 `resolve_sync_base_url` 三条取值路径都只做
`strip().rstrip("/")`,无 scheme 校验无主机允许清单;而 `SyncClient` 把 Nous JWT
设成 **Session 级** `Authorization` 头(`tools/skills_sync_client.py:778`),
该 base 下每个请求都带,**包括作者自己注明 "No auth required" 的 capabilities 探测**。

- **加重的一半**:同一仓库对**同一个 bearer** 已经写了这道防线,只装在**取**凭据那一端
  ——`hermes_cli/auth.py:6238` 的注释把威胁模型写得一字不差
  ("poisoned value can't exfiltrate the bearer"),配 `_NOUS_PORTAL_ALLOWED_HOSTS` 与回落默认值。
  **不是没想到,是只装了一侧。**
- **减轻的一半**:全仓**没有任何代码写 `sync.base_url`**(搜索面见底稿),
  `sync` 段也不在 `DEFAULT_CONFIG` 里。今天它只能由操作者手配,
  与 auth.py 那道防线所防的「网络来的值被持久化」**不同型**。
  故定 **■ 潜在不对称防御,不是可利用的凭据外泄**——记成后者是夸大。
- 移交项原写的锚点 `:318` 是函数体第一行,函数头在 `:307`;已在底稿更正。

**■ H-R9A-a(一并结清,比上一条重一个量级)**:
`gateway/relay/media.py:92-94` 的 `is_relay_media_url` 只做子串 `"/relay/media/" in url`,
**不看主机**;判为真就挂网关 bearer 并 `urlopen` 出去(`gateway/relay/media.py:169`)。
而 `url` 来自 `gateway/relay/ws_transport.py:268` —— **relay 帧的原始载荷,未经任何校验**。
**触发者是入站消息,不是本机配置**,这是它更重的原因。
最刺眼的是正确的比较值 `self._base_url` 就是**同一个类的实例字段**
(`gateway/relay/media.py:80`),修法不需要新配置也不需要新依赖。
该函数 docstring 自己把契约写成主机级("connector re-host URLs"),
子串判断不足以实现那句话——故记 ■ 不记 ▲。

**未取证的部分已如实标注**:没有构造入站帧实跑,没有逐平台确认哪些适配器会把
终端用户提供的 URL 放进 `media_urls`,故「终端用户可直接触发」是**推定**;
已确证的是「**能在入站帧里放 `media_urls` 的一方**可以触发」。

### 5.4 结构性结论

**本簇 35 条缺陷与文档冲突(■ 18 + ▲ 17)里,多数是同一种病:
同一份知识被写了第二遍,然后两份副本漂开了。**
关于「这个后端支持什么」,本簇同时存在四份副本,写给四个不同读者——
工具 schema(给模型)、系统提示词(给模型)、用户文档(给人)、代码里的判定表(给程序自己)
——而**没有任何机制保证它们一致**。上面 §5.2 四条恰好各占一种组合。
成品章 `chapters/r9b-multimodal-delivery.md` 把这条作为主线展开。

## 6. 关卡读数

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent chapters/*.md notes/r9b-*.md reports/round-9b-*.md
```

| 范围 | citations | OK | 可校验比例 | table_anchors | 阻断项 |
|---|---|---|---|---|---|
| **当轮 notes 单独**(报告口径) | 775 | 605 | **78.1%** | 215(OK 194) | 0 |
| 全量(chapters 全部 + 当轮 notes/reports) | 1,176 | 791 | 67.3%(合并数,含历史散文章) | 259(OK 210) | 0 |
| 本轮成品章单独 | 16 | 16 | **100.0%** | 5(OK 5) | 0 |

**当轮 notes 78.1%,过 70% 下限**;逐文件最低 70.6%、最高 100%,**七份全部过线**:

```text
r9b-90-rulings.md    70.6%     r9b-raw-present.md   81.4%
r9b-raw-image.md     72.3%     r9b-raw-tts.md       74.6%
r9b-raw-pet.md      100.0%     r9b-raw-video.md     77.8%
                               r9b-raw-voicein.md   73.1%
```

**0 MISMATCH / 0 BLOCK-DRIFT / 0 TABLE-DRIFT / 0 MISSING-FILE / 0 OUT-OF-RANGE,退出码 0,未用 `--fix`。**
报告首句 17 字,过 `verify_report_headline.py`。

关卡确实拦下了东西:各簇自校验首轮合计报出十余处 MISMATCH / BLOCK-DRIFT / TABLE-DRIFT
(B 簇一家就 7 + 1 + 3),全部逐条对着基线核对后**手改**而非 `--fix`。

## 7. 测试(按 CLAUDE.md 连环境一起记)

**范围**:与本簇 46 个文件直接对应的 74 个测试文件。

```text
74 文件   975 passed / 10 failed / 0 收集失败
```

**10 条失败,同一根因,非代码缺陷**:`fal-client` 属 `fal` extra 而**不在 `[dev]`**
(`pyproject.toml:167`),venv 里没有它。

- `tests/tools/test_image_generation.py`(2 条):报 `ImportError: Feature 'image.fal'
  unavailable: lazy installs disabled`。
- `tests/tools/test_video_generation_tool_surface_matrix.py`(8 条):报的是
  `assert False is True`,查局部变量才见 `'error': 'fal_client Python package not installed'`、
  `'error_type': 'missing_dependency'`。

**第二条值得单独记**:缺可选依赖**通常**表现为收集期 ImportError(一眼可辨),
这里却表现为**普通断言失败**——读者会以为路由逻辑坏了。
这是 H-R8D-j(`[dev]` 装不出全绿套件)的一个**更隐蔽的新实例**,已随该项续转。

**环境(本轮验收项 ③,开工与收工各测一次)**:

| 时点 | venv 包数 | dist-info 数 |
|---|---|---|
| 开工(重建 venv 后) | **87** | 87 |
| 收工 | **89** | 89 |

**差额 2 个是 `anthropic 0.87.0` + `docstring_parser 0.18.0`,时间戳 `04:51:12`。**
成因见 §8 第 3 条。**同一套测试在 87 包与 89 包下各跑一次,读数完全相同
(975 passed / 10 failed / 同样 2 个文件),故本轮测试结论不受该漂移影响。**

其余各簇自测(子代理跑,主线未逐条重跑):C 簇 36 文件 292 通过、
D 簇 23 文件 320 通过、F 簇 26 通过。C 簇记下一条环境事实值得留意:
`tests/tools/test_tts_streaming.py` 因 `pytest.importorskip("numpy")` **整文件跳过**,
即流式 TTS 唯一的单测在只装 `[dev]` 的环境里 **0 用例执行**,而门禁显示 0 failed。

## 8. 诚实申报

1. **首句 ≤20 字**:第一句「多模态交付面读完,表格锚点补上校验」17 字,
   经 `verify_report_headline.py` 判定通过。
2. **基线全程干净**:收工复查 `git -C /home/user/hermes-agent status --porcelain` 为空,
   HEAD = `863e31318553cda8ad61df681d08175364d4164b`,无暂存内容、无新 commit。
3. **共享 venv 被改了(纪律违反,如实记)**:任务书要求子代理运行期间不擅自装包。
   实际有一个子代理为诊断一条测试失败,直接调用了会触发惰性安装的代码路径,
   经 `tools/lazy_deps.ensure` 联网装了 2 个包。它**主动申报了此事**并说明未自行卸载
   (怕影响并发兄弟)。主线的处置是**不卸载、改为两次测量并交叉验证**(见 §7),
   确认读数未受影响。
   *附带的学习产出*:这条路径本身是 hermes-agent 的**文档化设计**
   (`tools/lazy_deps.py:18-23` 写明默认开、venv 内安装、可用 `security.allow_lazy_installs: false`
   关掉),**不是缺陷**;但它意味着**一个"读代码"的动作可以产生网络副作用并改变自身运行环境**,
   这对以"环境可复现"为前提的学习项目是个真实的坑。
4. **主线自己犯的一次操作失误**:一次 `cd /home/user/hermes-agent` 之后的 shell 状态残留,
   使随后的 `git add -A && git commit` **发在了基线仓库**而非学习仓库。
   该次提交因基线工作区干净而以 "nothing to commit" 失败,**未产生任何改动**;
   已立即用四项断言复核(porcelain 为空、HEAD 未变、暂存区为空、无新 commit)。
   记在这里是因为它差一点就污染了引用基准,此后所有 git 操作改用显式 `git -C <repo>`。
5. **一次违反"异步完成判定"的失误**:主线在 B 簇子代理**尚未发出完成信号时**,
   用 `git add -A` 把它**正在写入**的底稿扫进了 commit `19c63fc`。
   该子代理随后自己申报了这件事,并在完成前又修了 5 处漂移锚点;
   最终状态以其完成信号后的版本为准,关卡为绿。
   **这正是 CLAUDE.md 那条规矩要防的形状,而这次是主线自己踩的。**
6. **子代理条目按抽核处理**:除 §5.2 四条做了从源码到实跑的全链复核外,
   其余 55 条定案主线**未逐条重跑**,底稿引用时标注来源,不冒充主线全证。
7. **§5.1 的记号报数未做跨簇去重**,合计数不宜直接相加用于跨轮比较,已在该节标注。
8. **可校验比例的两个数**:报告口径(当轮 notes)78.1% 过线;
   全量合并数 67.3% 低于 70%,成因是 `chapters/` 里六份历史成品章天然以散文引用为主
   (校验器已逐章点名 UNCHECKED ≥90%),即 H-R8D-g 的欠账,**本轮未动**。
9. **实际执行模型**:运行时策略禁止把模型标识写入推送到仓库的产物,
   因此**模型标识在本会话回复中给出,不写入本报告**。
   此口径与 R7B / R7C / R8A / R8B / R8D / R9A 一致。

## 9. 移交清单(每条带锚点 + 紧跟反引号摘录 + 一句话现象)

| 移交项 | 去向 | 锚点 | 现象 |
|---|---|---|---|
| **H-R9B-a** | R9C/R9D 任一 | `tools/voice_mode.py:2193` 的 `native_stt_available` | 同一份内置 STT 名单全仓三份、漂了一份;修法是 import 权威集合而非再抄一遍,顺带查全仓还有多少处同型硬编码名单 |
| **H-R9B-b** | R9C/R9D 任一 | `tools/tts_tool.py:1665` 的 `_XAI_SPEECH_TAG_RE` | 包裹型标签只认尖括号而提示词禁止尖括号;现有测试只钉住尖括号那一支,故一直是绿的 |
| **H-R9B-c** | R9C/R9D 任一 | `tools/image_generation_tool.py:642` 的 `payload["image_urls"] = list(image_urls)` | schema 承诺可传本地绝对路径,默认后端 FAL 原样透传不读文件;「FAL 会拒绝文件路径」是推定,未发真请求 |
| **H-R9B-d** | R9C(网关片) | `gateway/relay/media.py:94` 的 `"/relay/media/" in (url or "")` | 网关 bearer 的发送判定用子串不比主机,`url` 来自未校验的入站帧;正确比较值 `self._base_url` 就在同一个类里 |
| **H-R9B-e** | R11A | `pyproject.toml:167` 的 `fal = ["fal-client==0.13.1"]` | 缺 extra 在本簇表现为**普通断言失败**而非收集期 ImportError,比 H-R8D-j 已知的形态更隐蔽 |
| **H-R9B-f** | R11 复盘 | `tools/tts_tool.py:2703` 的 `ffmpeg` 调用 | `.ogg` 目标下三处走裸 ffmpeg(默认 Vorbis),而 Gemini 分支显式加 `-acodec libopus`;**本容器无 ffmpeg,未实跑确认编解码**,推定 |
| **H-R9B-g** | 制度 / R11 复盘 | `tools/lazy_deps.py:20` 的 `security.allow_lazy_installs` | 惰性安装默认开,非交互调用方跳过确认,于是"读代码"可产生网络副作用并改变自身 venv;学习项目需要一条"跑基线代码前先关掉它"的纪律 |
| **H-R8D-g**(续转) | R11B | `chapters/r2-turn-loop-and-model-access.md` 等六章 | 校验器逐章点名 UNCHECKED ≥90%;本轮全量合并比例 67.7%,**欠账未动** |
| **H-R8D-h**(续转) | R11 复盘 | `notes/r8d-str-setup-and-ux.md` 记的两条 docstring 级 ▲ | 模块 docstring 级 ▲ 与「作者自绘地图」级 ▲ 是否分开计数,仍需一次统一裁定;本轮沿用分开处理 |
| **H-R8D-i**(续转) | R12 前置 | 本报告 §4 | R12 前置条件更新为「再做完 R9C / R9D 两轮」,与 R10 / R11 进度无关 |
| **H-R8D-j**(续转) | R11A | `pyproject.toml:36` 的 `` `exa-py`, `fal-client`, `edge-tts` `` 一句 | `pip install -e ".[dev]"` 装不出全绿套件;本轮新增 H-R9B-e 那个更隐蔽的形态 |
| **H-R9A-b / c / e / f / g**(续转) | R9D | 见 `reports/round-9a-capability-organization.md` §11 | R9A 移交、归 R9D 的五条,本轮未动 |

*(各簇底稿另有 30 余条簇内移交项,均带锚点,留在各自底稿的移交节,不在本表重复。)*
