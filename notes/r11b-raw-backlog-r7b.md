# r11b 底稿 · 片 B1 —— R7B 那 12 个 L1 文件(4,960 行)的补读

> **定位**:证据层底稿,求全求证,不求好读。成品章由主线写。
> **溯源约定**:凡对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` 单独成行、
> 置于代码块之前;围栏块是基线逐字摘录(本文件的全部围栏块由脚本从基线抽取,不手抄)。
> **上游成品章**:`chapters/r7b-platform-integration.md`(平台接入面)。本片补的正是那一章
> 没有落到文件级的那批实现。

---

## 0. 这一片在还什么账

R9D 点名了一批「台账写着 `*-deep-read`、但全部产出语料里没有任何一条可溯源断言」的 L1 文件。
`data/r11b/backlog-38.tsv` 里 `round=R7B` 的 12 行就是本片的对象,合计 4,960 行,
全部落在 `gateway/platforms/` 与 `gateway/relay/` 下。

**第一步:台账说它们学到什么程度**(本仓库根跑;`sub(/\r$/,"")` 是因为台账是 CRLF 行尾):

```verify
awk -F"\t" 'NR>1{sub(/\r$/,"",$0); if ($1 ~ /^gateway\/(platforms\/(yuanbao_(proto|media|sticker)|msgraph_webhook|media_cache)\.py|relay\/command_manifest\.py)$/ || ($1 ~ /^gateway\/platforms\/qqbot\// && $1 !~ /(adapter|crypto)\.py$/)) printf "%-45s %s\n", $1, $6}' data/ledger.tsv | sort
```

```text
gateway/platforms/media_cache.py              R7B-deep-read
gateway/platforms/msgraph_webhook.py          R7B-deep-read
gateway/platforms/qqbot/__init__.py           R7B-deep-read
gateway/platforms/qqbot/chunked_upload.py     R7B-deep-read
gateway/platforms/qqbot/constants.py          R7B-deep-read
gateway/platforms/qqbot/keyboards.py          R7B-deep-read
gateway/platforms/qqbot/onboard.py            R7B-deep-read
gateway/platforms/qqbot/utils.py              R7B-deep-read
gateway/platforms/yuanbao_media.py            R7B-deep-read
gateway/platforms/yuanbao_proto.py            R7B-deep-read
gateway/platforms/yuanbao_sticker.py          R7B-deep-read
gateway/relay/command_manifest.py             R7B-deep-read
```

**第二步:语料里实际有多少条指向它们的行号锚点**(`--exclude="r11b-*"` 排除本轮正在写的底稿,
否则本文件自己的锚点会污染读数):

```verify
for p in gateway/platforms/yuanbao_proto.py gateway/platforms/yuanbao_media.py gateway/platforms/qqbot/chunked_upload.py gateway/platforms/yuanbao_sticker.py gateway/platforms/qqbot/keyboards.py gateway/platforms/msgraph_webhook.py gateway/platforms/qqbot/onboard.py gateway/platforms/media_cache.py gateway/relay/command_manifest.py gateway/platforms/qqbot/__init__.py gateway/platforms/qqbot/constants.py gateway/platforms/qqbot/utils.py; do n=$(grep -rE --exclude="r11b-*" "$p:[0-9]" notes chapters reports reviews 2>/dev/null | wc -l); printf "%-45s %s\n" "$p" "$n"; done
```

```text
gateway/platforms/yuanbao_proto.py            0
gateway/platforms/yuanbao_media.py            0
gateway/platforms/qqbot/chunked_upload.py     0
gateway/platforms/yuanbao_sticker.py          0
gateway/platforms/qqbot/keyboards.py          0
gateway/platforms/msgraph_webhook.py          0
gateway/platforms/qqbot/onboard.py            0
gateway/platforms/media_cache.py              0
gateway/relay/command_manifest.py             0
gateway/platforms/qqbot/__init__.py           0
gateway/platforms/qqbot/constants.py          0
gateway/platforms/qqbot/utils.py              0
```

十二个 `R7B-deep-read`,十二个零。**`status` 列在这 12 个文件上高于实际交付**,这就是本片要还的账。

**本片按机制成簇写**,十个簇覆盖 12 个文件。每个文件的断言索引见 §15,可逐条对照交付判据。

**这 12 个文件在 r7b 章里的位置**:r7b 章讲的是接入面的**骨架**(基类能力位、第一层守卫、
api_server、媒体外泄边界、relay 描述符)。这 12 个文件是骨架下面的**肉**——
三个内建适配器(QQ Bot / 元宝 / MSGraph Webhook)各自的平台方言实现、一层跨适配器的
媒体共享层、以及 relay 侧的命令声明。r7b 章一次都没提到它们,所以这一片同时也是
那一章的**空缺清单**(见 §12)。

---

## 1. 簇一:入站媒体的 mime↔扩展名共享层 —— `gateway/platforms/media_cache.py`(202 行)

### 1.1 它解决什么问题

**场景**:用户在 BlueBubbles(iMessage 桥)里发来一张 HEIC 照片,在 WhatsApp 里发来一段
语音条(`audio/ogg`)。适配器把字节下载下来之后,要落到本地缓存目录,并且**得给它取个文件名**。
取什么扩展名,决定了下游能不能读:视觉工具读不了 `.heic`,STT(语音转文字)管线按扩展名白名单收活。

于是每个适配器历史上都手搓了一张 mime→扩展名表,而且**这些表故意互相不一致**。
这个模块把它们收进一处,同时保证每个适配器的输出**逐字节不变**。

`gateway/platforms/media_cache.py:1` @ 863e313

```python
"""Shared mime↔extension dispatch for inbound (downloaded) platform media.

Historically every gateway adapter hand-rolled its own mime→extension map
before handing downloaded bytes to the cache primitives in
``gateway.platforms.base`` (``cache_image_from_bytes``,
``cache_audio_from_bytes``, ``cache_document_from_bytes``).  Those maps
*disagree* with each other on purpose — e.g. BlueBubbles coerces
``image/heic`` to ``.jpg`` because downstream vision tools can't read HEIC,
while WhatsApp Cloud pins ``audio/ogg`` to ``.ogg`` (not the RFC-correct
``.oga`` Python's ``mimetypes`` returns) because the STT pipeline whitelists
extensions.
```

模块自己列了它拥有的四样东西:

`gateway/platforms/media_cache.py:13` @ 863e313

```python
This module owns:

* ``DEFAULT_MIME_TO_EXT`` — the union table of entries the adapters already
  agree on (plus a few uncontroversial document types).
* ``DEFAULT_EXT_TO_MIME`` — the canonical inverse (used by Signal to map a
  sniffed extension back to a content type).
* ``ext_for_mime`` / ``mime_for_ext`` — lookup helpers that accept
  per-adapter ``overrides`` so each adapter's historical (divergent)
  behavior is preserved byte-for-byte.
* ``cache_media_bytes`` — one-call dispatch: classify the mime, resolve the
  extension, and write to the right cache (image / audio / document).
```

### 1.2 设计:三段式解析 + 逐段可关

核心是 `ext_for_mime` 的解析顺序,而**每一段都能被调用方单独关掉**:

`gateway/platforms/media_cache.py:118` @ 863e313

```python
    if overrides:
        ext = overrides.get(primary)
        if ext:
            return ext
    if use_defaults:
        ext = DEFAULT_MIME_TO_EXT.get(primary)
        if ext:
            return ext
    if use_mimetypes:
        ext = mimetypes.guess_extension(primary)
        if ext:
            return ext
    return fallback
```

`overrides` → 共享默认表 → Python 标准库 `mimetypes` → `fallback`。
`use_defaults` / `use_mimetypes` 两个开关的存在,本身就是这次重构的**行为保全契约**:
一个历史上从不查 `mimetypes` 的适配器,迁过来之后必须继续不查。

### 1.3 ■-B1-01:共享表建成了,但**没有一个生产调用方在用它**

模块把 `DEFAULT_MIME_TO_EXT` 说成「适配器们已经达成一致的并集表」:

`gateway/platforms/media_cache.py:47` @ 863e313

```python
# Union of the per-adapter maps where the adapters already agree (or where
# only one adapter pinned the type and no other adapter contradicts it).
# Entries deliberately favor the common-in-the-wild extension over the
# RFC-correct one (``audio/ogg`` → ``.ogg``, not ``.oga``) because the
# downstream STT/vision pipelines whitelist real-world extensions.
DEFAULT_MIME_TO_EXT: dict[str, str] = {
```

问题是:**四个生产调用点全部传了 `use_defaults=False`**,即全部跳过这张表。

`gateway/platforms/whatsapp_cloud.py:177` @ 863e313

```python
    return ext_for_mime(
        mime,
        # preserves historical whatsapp_cloud mapping: overrides →
        # mimetypes → None, never the shared default table.
        overrides=_WHATSAPP_MIME_EXTENSION_OVERRIDES,
        use_defaults=False,
        use_mimetypes=True,
        fallback=None,
```

`gateway/platforms/qqbot/adapter.py:1822` @ 863e313

```python
            # preserves historical qqbot mapping: trust mimetypes'
            # guess (never the shared table) and fall back to .jpg.
            ext = ext_for_mime(
                content_type,
                use_defaults=False,
                use_mimetypes=True,
                fallback=".jpg",
            ) or ".jpg"
            return cache_image_from_bytes(data, ext)
```

BlueBubbles 的两个调用点(图片、音频)同样传 `use_defaults=False`。
唯一真正读共享表的是 Signal,而它读的是**反向表**,并且注释直说这张反向表与它自己的历史表逐字节相同:

`gateway/platforms/signal.py:126` @ 863e313

```python
# Historical Signal ext→mime table now lives in
# gateway.platforms.media_cache.DEFAULT_EXT_TO_MIME (byte-identical);
# kept as a module alias for backwards compatibility with any callers
# that referenced the private name.
_EXT_TO_MIME = DEFAULT_EXT_TO_MIME
```

**搜索面(负结论必须交代)**:在基线的 `gateway/ plugins/ tools/ agent/` 四棵树里,
以 `--include=*.py` 搜 `DEFAULT_MIME_TO_EXT` 与 `use_defaults=` 两个模式,输出按 `sort` 固定顺序。
`tests/` 不计入「生产调用方」,下面的命令也没扫它,这一点如实说明:结论限定为
「**非测试树里没有任何一处让 `use_defaults` 保持默认 True**」。

```verify
cd /home/user/hermes-agent && grep -rn "DEFAULT_MIME_TO_EXT\|use_defaults=" --include=*.py gateway plugins tools agent | sort
```

```text
gateway/platforms/bluebubbles.py:841:                    use_defaults=False,
gateway/platforms/bluebubbles.py:853:                    use_defaults=False,
gateway/platforms/media_cache.py:107:    Resolution order: ``overrides`` → ``DEFAULT_MIME_TO_EXT`` (if
gateway/platforms/media_cache.py:123:        ext = DEFAULT_MIME_TO_EXT.get(primary)
gateway/platforms/media_cache.py:15:* ``DEFAULT_MIME_TO_EXT`` — the union table of entries the adapters already
gateway/platforms/media_cache.py:52:DEFAULT_MIME_TO_EXT: dict[str, str] = {
gateway/platforms/qqbot/adapter.py:1826:                use_defaults=False,
gateway/platforms/whatsapp_cloud.py:182:        use_defaults=False,
```

`DEFAULT_MIME_TO_EXT` 的读取点只有一处(`media_cache.py` 第 123 行),而它在 `if use_defaults:` 之下,
四个调用点全部把它关掉。**这张表在运行时是死的。**

**这算不算缺陷?** 我判它是 ■ 而不是「无害的文档」,理由是它有实际代价:
读到这个模块的人会以为「共享表是新平台的默认行为」,于是新写一个适配器时理所当然地
不传 `use_defaults`,拿到的就是**和现有四个适配器都不一样的**第五种映射。
表本身没错,错在它被命名成 `DEFAULT_*` 却从不作为默认生效——**一个"默认值"从没被任何人默认到**。

**取舍的正面读法**(要一并写下来,否则这条会被误读成"重构失败"):这次重构的**目标**
就写在模块开头——那些表 `disagree with each other on purpose`。
它要的是**把分歧集中到一处、并用测试钉住**,不是消除分歧。从这个目标看它成功了:
四张历史表现在都以 `overrides` 的形式并排放着,谁和谁不一样一眼可见。
`DEFAULT_MIME_TO_EXT` 是**给未来第五个适配器准备的默认**,只是没有人告诉读者这一点。

### 1.4 ■-B1-02:两个同名 `cache_media_bytes`,签名与返回类型都不兼容

模块声称自己拥有一个「一次调用完成分派」的入口:

`gateway/platforms/media_cache.py:155` @ 863e313

```python
def cache_media_bytes(
    data: bytes,
    mime: str,
    *,
    filename_hint: str = "",
    kind_hint: Optional[str] = None,
    ext_overrides: Optional[Mapping[str, str]] = None,
) -> str:
```

而同一个包的兄弟模块里有一个**同名函数**,签名完全不同:

`gateway/platforms/base.py:1966` @ 863e313

```python
def cache_media_bytes(
    data: bytes,
    *,
    filename: str = "",
    mime_type: str = "",
    default_kind: Optional[str] = None,
) -> Optional[CachedMedia]:
```

差异逐条:

| 维度 | `media_cache` 版 | `base` 版 |
|---|---|---|
| mime 参数 | 第二个**位置**参数 | **关键字**参数 |
| 文件名 | 关键字 `filename_hint` | 关键字 `filename` |
| 类别提示 | 关键字 `kind_hint` | 关键字 `default_kind` |
| 视频 | **没有** video 分支,落到 document | 有独立 video 分支 |
| 返回 | 裸路径字符串 | 结构体或 None(含路径/mime/kind/显示名) |

两者互相**不能替换**:把 `base` 版的调用原样指向 `media_cache` 版会 `TypeError`;
就算参数对上了,返回类型也从对象变成裸字符串,`None` 这个「图片校验失败」的信号会消失。

```verify
cd /home/user/hermes-agent && grep -rn "^def cache_media_bytes" --include=*.py gateway plugins tools agent | sort
```

```text
gateway/platforms/base.py:1966:def cache_media_bytes(
gateway/platforms/media_cache.py:155:def cache_media_bytes(
```

**并且 `media_cache` 版没有生产调用方**:Teams 与 Telegram 两个插件适配器
`from gateway.platforms.base import cache_media_bytes`,`media_cache` 版只被
`tests/gateway/test_media_cache.py` 调用。所以这个包里现在有一个**没人用、且与常用同名函数
签名冲突**的入口——一次 `from ... import cache_media_bytes` 写错模块名就静默换了语义。

### 1.5 ◇-B1-01:模块自带一条至今未清的 TODO

`gateway/platforms/media_cache.py:32` @ 863e313

```python
NOTE: ``gateway/platforms/weixin.py`` also has a private mime map
(``_mime_from_filename``) but is intentionally NOT migrated here — another
in-flight branch edits that file.  Follow-up: fold it in once that lands.
```

基线里 `gateway/platforms/weixin.py` 的私有 mime 映射函数仍在(定义在该文件第 686 行,
使用在第 1666 行),即这条 follow-up 在 863e313 尚未落地。这不是缺陷,是**一条把
"为什么这里不干净"写进代码的注释**——值得抄的做法:重构留下的缺口写进模块开头,
而不是留给下一个读者猜。

---

## 2. 簇二:QQ Bot 从一个文件变成一个包 —— `qqbot/__init__.py`(91)·`constants.py`(74)·`utils.py`(71)

### 2.1 `__init__.py`:一个只为「不改任何 import 路径」而存在的门面

**场景**:`gateway/platforms/qqbot.py` 长到需要拆分。拆成包之后,所有
`from gateway.platforms.qqbot import X` 都会断——包括**测试**。

`gateway/platforms/qqbot/__init__.py:1` @ 863e313

```python
"""
QQBot platform package.

Re-exports the main adapter symbols from ``adapter.py`` (the original
``qqbot.py``) so that **all existing import paths remain unchanged**::

    from gateway.platforms.qqbot import QQAdapter          # works
    from gateway.platforms.qqbot import check_qq_requirements  # works

New modules:
    - ``constants`` — shared constants (API URLs, timeouts, message types)
    - ``utils`` — User-Agent builder, config helpers
    - ``crypto`` — AES-256-GCM key generation and decryption
    - ``onboard`` — QR-code scan-to-configure flow
"""
```

门面把**私有名**也一并转出去,这是最能说明设计意图的一处:

`gateway/platforms/qqbot/__init__.py:17` @ 863e313

```python
# -- Adapter (original qqbot.py) ------------------------------------------
from .adapter import (  # noqa: F401
    QQAdapter,
    QQCloseError,
    check_qq_requirements,
    _coerce_list,
    _ssrf_redirect_guard,
)
```

`_coerce_list` 与 `_ssrf_redirect_guard` 都带下划线前缀,按惯例不该出现在包的公开面上。
它们在这里,是因为**测试直接从包根导入它们**:

`tests/gateway/test_qqbot.py:74` @ 863e313

```python
class TestCoerceList:
    def _fn(self, value):
        from gateway.platforms.qqbot import _coerce_list
        return _coerce_list(value)
```

`tests/gateway/test_qqbot.py:116` @ 863e313

```python
    def test_connect_uses_redirect_guard_hook(self):
        from gateway.platforms.qqbot import QQAdapter, _ssrf_redirect_guard
```

换句话说,**「所有既有 import 路径不变」这条契约的执行者是测试**,不是约定。

顺带一条:`_coerce_list` 在 adapter 里只是 `utils.coerce_list` 的向后兼容别名——

`gateway/platforms/qqbot/adapter.py:145` @ 863e313

```python
def _coerce_list(value: Any) -> List[str]:
    """Coerce config values into a trimmed string list."""
    return _coerce_list_impl(value)
```

——于是包根**同时**导出 `_coerce_list`(旧名)和 `coerce_list`(新名),两者是同一个实现。

### 2.2 ◇-B1-02:门面 docstring 的「新模块」清单漏了两个

上面第一段摘录里的 `New modules:` 列表只写了 `constants` / `utils` / `crypto` / `onboard`,
而同一个文件后面还转出了另外两个模块的符号:

`gateway/platforms/qqbot/__init__.py:37` @ 863e313

```python
# -- Chunked upload --------------------------------------------------------
from .chunked_upload import (  # noqa: F401
    ChunkedUploader,
    UploadDailyLimitExceededError,
    UploadFileTooLargeError,
)
```

`gateway/platforms/qqbot/__init__.py:44` @ 863e313

```python
# -- Inline keyboards ------------------------------------------------------
from .keyboards import (  # noqa: F401
    ApprovalRequest,
```

包里实际有 6 个新模块,自述只列了 4 个。**代码内自述与代码本身的偏差**,与 r7b 章 ▲5
(`gateway/platforms/whatsapp_cloud.py` 模块 docstring 里的失效路径引用)是同一物种:
注释里的**清单**和注释里的**路径**一样会腐烂,而且没有任何机制会发现。

### 2.3 `constants.py`:平台方言的常量面

这个文件是 QQ 平台**方言参数的集中处**:端点、超时、重连退避、消息长度上限、消息类型枚举、
媒体类型枚举。值得单独拎出来的两组:

`gateway/platforms/qqbot/constants.py:37` @ 863e313

```python
DEFAULT_API_TIMEOUT = 30.0
FILE_UPLOAD_TIMEOUT = 120.0
CONNECT_TIMEOUT_SECONDS = 20.0

RECONNECT_BACKOFF = [2, 5, 10, 30, 60]
MAX_RECONNECT_ATTEMPTS = 100
RATE_LIMIT_DELAY = 60  # seconds
QUICK_DISCONNECT_THRESHOLD = 5.0  # seconds
MAX_QUICK_DISCONNECT_COUNT = 3

ONBOARD_POLL_INTERVAL = 2.0  # seconds between poll_bind_result calls
ONBOARD_API_TIMEOUT = 10.0
```

`RECONNECT_BACKOFF` 是一张**显式的退避表**而不是公式,`QUICK_DISCONNECT_THRESHOLD` +
`MAX_QUICK_DISCONNECT_COUNT` 是「短连接抖动」的判据——连上 5 秒内就断、连续 3 次,
说明不是网络抖动而是**服务端在拒绝**,该停。这与 r7b 章 3.4 节讲的 api_server #38803
(把配置错误误判成瞬时故障,无限重试泄漏 fd)是同一个问题的**另一种解法**:
api_server 靠**返回值语义**区分可重试/不可重试,QQ Bot 靠**行为模式**(断得太快太频)。

`gateway/platforms/qqbot/constants.py:54` @ 863e313

```python
MAX_MESSAGE_LENGTH = 4000
DEDUP_WINDOW_SECONDS = 300
DEDUP_MAX_SIZE = 1000
```

`MAX_MESSAGE_LENGTH = 4000` 就是 r7b 章 3.1 节那组能力位里的「一条消息最长多少」在 QQ 上的取值;
`DEDUP_WINDOW_SECONDS` / `DEDUP_MAX_SIZE` 是**入站去重**的窗口与容量——
和 §9 里 MSGraph 那份收据去重是同一形状的机制(有界 LRU),只是这里以常量形式暴露。

### 2.4 ■-B1-03:注释指向一个全仓不存在的环境变量名

`gateway/platforms/qqbot/constants.py:17` @ 863e313

```python
# The portal domain is configurable via QQ_API_HOST for corporate proxies
# or test environments.  Default: q.qq.com (production).
PORTAL_HOST = os.getenv("QQ_PORTAL_HOST", "q.qq.com")
```

注释说「可用 `QQ_API_HOST` 配置」,**下一行读的是 `QQ_PORTAL_HOST`**。

```verify
cd /home/user/hermes-agent && grep -rn --exclude-dir=__pycache__ "QQ_API_HOST" . | sort
```

```text
./gateway/platforms/qqbot/constants.py:17:# The portal domain is configurable via QQ_API_HOST for corporate proxies
```

**搜索面**:基线全树、不限文件类型、只排除 `__pycache__`(它含编译产物,与源码同义且不稳定)。
`QQ_API_HOST` 在整个仓库只出现这一次,就是这条注释本身——**它命名了一个不存在的开关**。
一个照着注释去设 `QQ_API_HOST` 的运维,会得到「设了没反应」而且无处可查。

**有意思的是方向**:这一次**网站文档是对的**(环境变量参考页与 QQ Bot 用户指南都写
`QQ_PORTAL_HOST`,见 §5.4 的两条引用),错的是**代码注释**。
r7b 章第 5 节的结论是「没有测试守着的文档会腐烂」;这里给它加一句:
**代码注释同样没有测试守着,而且没人会去 review 一条三行外就自证矛盾的注释。**

### 2.5 `utils.py`:三个小东西,一个真教训

`gateway/platforms/qqbot/utils.py:42` @ 863e313

```python
def get_api_headers() -> Dict[str, str]:
    """Return standard HTTP headers for QQBot API requests.

    Includes ``Content-Type``, ``Accept``, and a dynamic ``User-Agent``.
    ``q.qq.com`` requires ``Accept: application/json`` — without it,
    the server returns a JavaScript anti-bot challenge page.
    """
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": build_user_agent(),
    }
```

这条 docstring 记下了一个**只有踩过才知道**的事实:`q.qq.com` 在缺 `Accept: application/json`
时不返回 JSON,而是返回一个 **JavaScript 反爬挑战页**。表现是「HTTP 200,但解析 JSON 抛异常」,
排查方向会被完全带偏。把这类平台怪癖写进 header 构造函数的 docstring,是这个文件最大的价值。

User-Agent 的构造也值得一提:

`gateway/platforms/qqbot/utils.py:25` @ 863e313

```python
def build_user_agent() -> str:
    """Build a descriptive User-Agent string.

    Format::

        QQBotAdapter/<qqbot_version> (Python/<py_version>; <os>; Hermes/<hermes_version>)

    Example::

        QQBotAdapter/1.0.0 (Python/3.11.15; darwin; Hermes/0.9.0)
    """
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    os_name = platform.system().lower()
    hermes_version = _get_hermes_version()
    return f"QQBotAdapter/{QQBOT_VERSION} (Python/{py_version}; {os_name}; Hermes/{hermes_version})"
```

UA 里同时带**适配器版本**(`QQBOT_VERSION`,constants 里手工 bump)、**Python 版本**、
**操作系统**和 **Hermes 版本**。这是给平台侧做问题定位用的:出问题时对方能直接从 UA 读出
「哪个版本的哪个适配器在什么环境下发的」。代价是 `QQBOT_VERSION` 靠人记得 bump——

`gateway/platforms/qqbot/constants.py:7` @ 863e313

```python
# ---------------------------------------------------------------------------
# QQBot adapter version — bump on functional changes to the adapter package.
# ---------------------------------------------------------------------------

QQBOT_VERSION = "1.1.0"
```

——那句 `bump on functional changes` 就是这个代价的自白。

---

## 3. 簇三:QQ Bot 的大文件三步上传 —— `gateway/platforms/qqbot/chunked_upload.py`(602 行)

### 3.1 场景与协议

**场景**:agent 生成了一个 40 MB 的 PDF,要发到 QQ 群里。QQ v2 的内联 base64 上传封顶约 10 MB,
超过就必须走三步分片流程。

`gateway/platforms/qqbot/chunked_upload.py:1` @ 863e313

```python
"""QQ Bot chunked upload flow.

The QQ v2 API caps inline base64 uploads (``file_data`` / ``url``) at ~10 MB.
For files between 10 MB and ~100 MB we have to use the three-step chunked
upload flow::

    1. POST /v2/{users|groups}/{id}/upload_prepare
       → returns upload_id, block_size, and an array of pre-signed COS part URLs.
    2. For each part:
         PUT the part bytes to its pre-signed COS URL,
         then POST /v2/{users|groups}/{id}/upload_part_finish to acknowledge.
    3. POST /v2/{users|groups}/{id}/files with {"upload_id": ...}
       → returns the ``file_info`` token the caller uses in a RichMedia
       message.

```

三步是 `upload_prepare`(拿 upload_id + 分片大小 + 一批预签名 COS URL)→ 逐片 `PUT` 到 COS
并 `upload_part_finish` 确认 → `POST /files` 换回 `file_info` 令牌。
注意**分片字节不经过 QQ 的 API**,直传腾讯云对象存储(COS),API 只做编排。

### 3.2 依赖注入:这个模块不认识适配器

`gateway/platforms/qqbot/chunked_upload.py:192` @ 863e313

```python
ApiRequestFn = Callable[..., Awaitable[Dict[str, Any]]]
"""Signature of the adapter's ``_api_request`` callable.

We pass the bound method in rather than importing the adapter, to avoid
circular imports and keep this module testable in isolation.
"""
```

`api_request` 和 `http_put` 都是**传进来的可调用对象**,模块不 import 适配器。
理由写在 docstring 里:避免循环导入 + 可单测。适配器侧就是把两个绑定方法递进来:

`gateway/platforms/qqbot/adapter.py:3052` @ 863e313

```python
        uploader = ChunkedUploader(
            api_request=self._api_request,
            http_put=self._http_client.put,
            log_tag=self._log_tag,
        )
```

**可迁移**:一个「多步骤外部协议驱动器」最好只依赖两个动词(发 API、传字节),
而不是依赖它的宿主。这样它的测试不需要造一个适配器。

### 3.3 服务端声明的数值一律夹逼

`gateway/platforms/qqbot/chunked_upload.py:264` @ 863e313

```python
        max_concurrent = min(prepare.concurrency, _MAX_CONCURRENT_PARTS)
        retry_timeout = min(
            prepare.retry_timeout if prepare.retry_timeout > 0 else _PART_FINISH_DEFAULT_TIMEOUT,
            _PART_FINISH_MAX_TIMEOUT,
        )
        logger.info(
            "[%s] Prepared: upload_id=%s block_size=%s parts=%d concurrency=%d",
            self._log_tag, prepare.upload_id, format_size(prepare.block_size),
            len(prepare.parts), max_concurrent,
        )
```

`concurrency` 与 `retry_timeout` 都来自 `upload_prepare` 的响应,即**对端说了算**。
两者都被夹在本地常量之内:并发上限 10,重试窗上限 600 秒;`retry_timeout <= 0` 时回落默认 120 秒;
`concurrency` 为 0 时在解析阶段就被 `or _DEFAULT_CONCURRENT_PARTS` 兜住,为负时最终被
下面这个 `max(concurrency, 1)` 兜住:

`gateway/platforms/qqbot/chunked_upload.py:590` @ 863e313

```python
async def _run_with_concurrency(
    tasks: List[Callable[[], Awaitable[None]]],
    concurrency: int,
) -> None:
    """Run a list of thunks with a bounded number in flight at once."""
    concurrency = max(concurrency, 1)
    sem = asyncio.Semaphore(concurrency)

    async def _wrap(thunk: Callable[[], Awaitable[None]]) -> None:
        async with sem:
            await thunk()

    await asyncio.gather(*(_wrap(t) for t in tasks))
```

这正是 r7b 章第 4 节原则 13「反序列化边界上,类型正确 ≠ 取值合理」的一个**正面样本**:
relay 描述符那处是踩了坑之后补的(`max_message_length = 0` 会把每条回复截成空串),
这里是**一开始就把每个来自对端的数值都夹住**。两处放在一起,正好是同一条原则的反例与正例。

### 3.4 分片偏移用统一步长,分片长度用每片声明

`gateway/platforms/qqbot/chunked_upload.py:359` @ 863e313

```python
        part_index = part.index
        # Per-part block_size wins; fall back to the response-level value.
        actual_block_size = part.block_size if part.block_size > 0 else rsp_block_size
        offset = (part_index - 1) * rsp_block_size
        length = min(actual_block_size, file_size - offset)
```

`offset` 用**响应级** `rsp_block_size`(统一步长),`length` 用**每片**的 `block_size`。
看着不对称,其实是对的:分片在文件里是等距铺开的,只有最后一片更短,
所以「位置按统一步长算、长度按本片声明算」是唯一自洽的组合;`min(...)` 再兜一次底。
这段值得记下来的原因是:**如果两处都用每片声明的大小,最后一片之前的任何一片声明了不同大小,
后续所有偏移都会错位**,而错位上传在 COS 侧不会报错,
只会在 `complete_upload` 之后产出一个内容被打乱的文件。

### 3.5 ■-B1-04:`UploadFileTooLargeError` 全仓从未被抛出

模块声明了两个业务异常,并在 `upload()` 的 docstring 里承诺会抛它们:

`gateway/platforms/qqbot/chunked_upload.py:236` @ 863e313

```python
        :returns: The raw response dict from ``complete_upload`` — contains
            ``file_info`` that the caller uses in a RichMedia message body.
        :raises UploadDailyLimitExceededError: On biz_code 40093002.
        :raises UploadFileTooLargeError: When the file exceeds the platform limit.
        :raises RuntimeError: On other API or I/O failures.
        """
```

适配器也为它准备了一条专门的 `except` 分支,产出一句面向用户的话:

`gateway/platforms/qqbot/adapter.py:3001` @ 863e313

```python
        except UploadFileTooLargeError as exc:
            logger.warning(
                "[%s] File too large: %s (%s, platform limit %s)",
                self._log_tag, exc.file_name, exc.file_size_human, exc.limit_human,
            )
            return SendResult(
                success=False,
                error=(
                    f"{exc.file_name!r} ({exc.file_size_human}) exceeds the "
                    f"QQ per-file upload limit ({exc.limit_human})."
                ),
                retryable=False,
```

但**没有任何地方 `raise` 它**。

```verify
cd /home/user/hermes-agent && grep -rn "UploadFileTooLargeError" --include=*.py gateway plugins tools agent hermes_cli tests | sort; echo "--- raise 点 ---"; grep -rn "raise Upload" --include=*.py . | sort
```

```text
gateway/platforms/qqbot/__init__.py:41:    UploadFileTooLargeError,
gateway/platforms/qqbot/__init__.py:79:    "UploadFileTooLargeError",
gateway/platforms/qqbot/adapter.py:126:    UploadFileTooLargeError,
gateway/platforms/qqbot/adapter.py:3001:        except UploadFileTooLargeError as exc:
gateway/platforms/qqbot/adapter.py:3032:        :raises UploadFileTooLargeError: When the file exceeds the platform limit.
gateway/platforms/qqbot/chunked_upload.py:239:        :raises UploadFileTooLargeError: When the file exceeds the platform limit.
gateway/platforms/qqbot/chunked_upload.py:27:- :class:`UploadFileTooLargeError` — file exceeds the platform per-file limit.
gateway/platforms/qqbot/chunked_upload.py:92:class UploadFileTooLargeError(Exception):
tests/gateway/test_qqbot.py:455:        from gateway.platforms.qqbot.chunked_upload import UploadFileTooLargeError
tests/gateway/test_qqbot.py:456:        exc = UploadFileTooLargeError("huge.bin", 200 * 1024 * 1024, 100 * 1024 * 1024)
--- raise 点 ---
./gateway/platforms/qqbot/chunked_upload.py:336:                raise UploadDailyLimitExceededError(
```

**搜索面**:`gateway plugins tools agent hermes_cli tests` 六棵树的 `*.py` 搜类名;
再对全树 `*.py` 搜 `raise Upload` 前缀,唯一命中是**另一个**异常
(`UploadDailyLimitExceededError`)。所以:
`UploadFileTooLargeError` 有类定义、有两处 docstring 承诺、有一条 `except` 分支、有一个测试,
**唯独没有抛出点**。

**后果**:超过平台单文件上限的文件不会走到那条友好提示,而是掉进适配器的通用
`except Exception` 分支,把 QQ API 的原始错误串抛给模型。用户看到的不是
「超过 QQ 单文件上限」,是一段 biz_code。

**这条最值得学的是它为什么活下来**:测试是有的——

`tests/gateway/test_qqbot.py:454` @ 863e313

```python
    def test_too_large_includes_limit(self):
        from gateway.platforms.qqbot.chunked_upload import UploadFileTooLargeError
        exc = UploadFileTooLargeError("huge.bin", 200 * 1024 * 1024, 100 * 1024 * 1024)
        assert exc.file_name == "huge.bin"
        assert "MB" in exc.file_size_human
        assert "MB" in exc.limit_human
        assert "huge.bin" in str(exc)
```

它测的是**手工构造的异常实例的消息格式**,不是**这个异常会在什么条件下被抛出**。
一个只测「异常对象长什么样」的用例,对「没有人抛它」完全无感,还会给出覆盖率与信心。
**行为规格要钉的是触发条件,不是数据类的字符串表示。**

### 3.6 取舍:一片失败时,兄弟分片不会被取消

`_run_with_concurrency` 用的是不带 `return_exceptions` 的 `asyncio.gather`(见 §3.3 的第二段摘录末行)。
Python 的语义是:第一个异常立即向上传播,**其余任务不被取消**,继续在后台把自己的分片 PUT 完。
上层媒体发送路径会返回失败,而这些孤儿任务仍在向 COS 传数据。
对 40 MB 级别的上传,这意味着**一次失败可能仍然把整个文件传完**,只是没人去 `complete_upload`。
不是数据正确性问题,是**带宽与配额**问题(而配额恰好是 `40093002` 那条日限的计量对象)。

---

## 4. 簇四:QQ Bot 的按钮审批 —— `gateway/platforms/qqbot/keyboards.py`(461 行)

### 4.1 场景:审批从「打字」变成「点按钮」

r7b 章 3.2 节讲了审批命令为什么必须绕过第一层守卫(agent 阻塞在 `Event.wait` 上,
`/approve` 若进了待处理单槽就是死锁)。那一节讲的是**文字命令**的路径。
这个文件讲的是**按钮**的路径:

`gateway/platforms/qqbot/keyboards.py:1` @ 863e313

```python
"""QQ Bot inline keyboards + approval / update-prompt senders.

QQ Bot v2 supports attaching inline keyboards to outbound messages. When a
user clicks a button, the platform dispatches an ``INTERACTION_CREATE``
gateway event containing the button's ``data`` payload. The bot must ACK the
interaction promptly via ``PUT /interactions/{id}`` or the user sees an
error indicator on the button.

```

**「必须及时 ACK」这句话值得对照 r7b 章 3.6 节**:Discord 的按钮点击要求 3 秒内 ACK,
托管网关做不到,于是 relay 让 connector 在边缘先 ACK。QQ 这里没有 relay 这一层,
所以 ACK 必须由网关自己在同一条 WS 上及时发出——**同一个约束,两种架构下的两种解法**。

### 4.2 按钮回传数据是一个自描述字符串

`gateway/platforms/qqbot/keyboards.py:21` @ 863e313

```python
``button_data`` formats::

    approve:<session_key>:<decision>      # decision = allow-once|allow-always|deny
    update_prompt:<answer>                # answer = y|n

Ported from WideLee's qqbot-agent-sdk v1.2.2 (``approval.py`` + ``dto.py``
keyboard types). Authorship preserved via Co-authored-by.
```

`button_data` 是平台原样带回来的一小段文本,所以它必须**自带路由信息**:
决定要回给哪一个挂起的审批,靠的是嵌在里面的 `session_key`。

`gateway/platforms/qqbot/keyboards.py:44` @ 863e313

```python
# Pattern: approve:<session_key>:<decision>
# session_key may itself contain colons (e.g. agent:main:qqbot:c2c:OPENID),
# so the session_key group is greedy but trails the decision.
_APPROVAL_DATA_RE = re.compile(
    r"^approve:(.+):(allow-once|allow-always|deny)$"
)

# Pattern: update_prompt:y | update_prompt:n
_UPDATE_PROMPT_RE = re.compile(r"^update_prompt:(y|n)$")
```

注释点破了这个正则唯一的难点:**`session_key` 自己就含冒号**
(形如 `agent:main:qqbot:c2c:OPENID`)。`(.+)` 贪婪 + `$` 锚定,使得回溯只会在
**最后一个**冒号处切出决定值,于是 key 里有多少冒号都不影响。
一个更"整洁"的写法(把 key 限制成不含冒号)在这里是错的。

**可迁移**:回调数据是**平台代管的不可信文本**,它的编码格式要能容纳你自己的标识符里
可能出现的一切分隔符。要么像这里一样把分隔符放在**末端**并锚定,要么就别用分隔符。

### 4.3 互斥按钮组:一个 UI 细节里的状态机

`gateway/platforms/qqbot/keyboards.py:113` @ 863e313

```python
@dataclass
class KeyboardButton:
    """One button in a keyboard.

    :param group_id: Buttons sharing a ``group_id`` are mutually exclusive —
        clicking one greys the rest.
    """
    id: str
    render_data: KeyboardButtonRenderData
    action: KeyboardButtonAction
    group_id: str = "default"
```

同一 `group_id` 的按钮互斥——点其中一个,其余变灰。配合 `click_limit`(默认 1)和
`visited_label`(点击后的文案),平台侧就**替你实现了"一次性决定"的 UI 语义**:
用户点完「允许一次」,「始终允许」和「拒绝」自动失效并留在原位。
这省掉了网关侧的"审批已过期/已决定"的重绘逻辑——**能把状态机推给平台就推给平台**。

### 4.4 ■-B1-05:`ApprovalSender` 是一个没人用、且会丢参数的孤儿类

模块 docstring 把它列为对外提供的东西之一,类 docstring 也写得像是给适配器用的:

`gateway/platforms/qqbot/keyboards.py:337` @ 863e313

```python
class ApprovalSender:
    """Send an approval-request message with an inline keyboard.

    Decoupled from the adapter via callables so it can be unit-tested in
    isolation. Pass the adapter's ``_send_message_with_keyboard`` helper
    (or any equivalent) as ``post_message``.
    """
```

三处不对:

**(a) docstring 说的参数名不存在。** 它让你「把适配器的 `_send_message_with_keyboard`
作为 `post_message` 传进来」,而构造函数根本没有 `post_message` 这个参数:

`gateway/platforms/qqbot/keyboards.py:345` @ 863e313

```python
    def __init__(
        self,
        post_c2c: PostMessageFn,
        post_group: PostMessageFn,
        log_tag: str = "QQBot",
    ) -> None:
        self._post_c2c = post_c2c
        self._post_group = post_group
        self._log_tag = log_tag
```

**(b) 它点名的适配器方法也不存在。** 适配器上的方法叫 `send_with_keyboard`:

`gateway/platforms/qqbot/adapter.py:2617` @ 863e313

```python
    async def send_with_keyboard(
            self,
            chat_id: str,
            content: str,
            keyboard: InlineKeyboard,
            reply_to: Optional[str] = None,
    ) -> SendResult:
```

**(c) 它把 `allow_permanent` 丢了。** `ApprovalRequest` 有这个字段,而 `send()` 不传:

`gateway/platforms/qqbot/keyboards.py:368` @ 863e313

```python
        :returns: ``True`` on success, ``False`` on failure.
        """
        text = build_approval_text(req)
        keyboard = build_approval_keyboard(req.session_key)

```

对照**真正在用的**那条路径——适配器自己把它接上了:

`gateway/platforms/qqbot/adapter.py:2681` @ 863e313

```python
        from gateway.platforms.qqbot.keyboards import build_approval_text
        return await self.send_with_keyboard(
            chat_id,
            build_approval_text(req),
            build_approval_keyboard(
                req.session_key,
                allow_permanent=getattr(req, "allow_permanent", True),
            ),
            reply_to=reply_to,
        )
```

`allow_permanent=False` 的含义是「这次不允许持久化授权」(例如命中了危险模式、
或运营方一次性放行),此时键盘不该出现「⭐ 始终允许」:

`gateway/platforms/qqbot/keyboards.py:204` @ 863e313

```python
def build_approval_keyboard(session_key: str, *, allow_permanent: bool = True) -> InlineKeyboard:
    """Build the approval keyboard, hiding persistent scope when unavailable.

    Layout: ``[✅ 允许一次] [⭐ 始终允许] [❌ 拒绝]`` — all three share
    ``group_id='approval'`` so clicking one greys out the rest.

    :param session_key: Embedded into ``button_data`` so the decision
        routes back to the right pending approval.
    """
```

也就是说,**如果有人照 docstring 用了 `ApprovalSender`,会在本该只给"一次"的场合
把"始终允许"按钮发出去**——这是一个**安全语义**的丢失,不只是 UI 瑕疵。

```verify
cd /home/user/hermes-agent && grep -rn "ApprovalSender\|_send_message_with_keyboard" --include=*.py . | sort
```

```text
./gateway/platforms/qqbot/__init__.py:47:    ApprovalSender,
./gateway/platforms/qqbot/__init__.py:82:    "ApprovalSender",
./gateway/platforms/qqbot/keyboards.py:18:- :class:`ApprovalRequest` + :class:`ApprovalSender` — high-level helper that
./gateway/platforms/qqbot/keyboards.py:328:# ── ApprovalSender ───────────────────────────────────────────────────
./gateway/platforms/qqbot/keyboards.py:337:class ApprovalSender:
./gateway/platforms/qqbot/keyboards.py:341:    isolation. Pass the adapter's ``_send_message_with_keyboard`` helper
```

**搜索面**:基线全树 `*.py`,两个模式(类名、docstring 点名的方法名)。命中 6 行,
全部在 `keyboards.py` 自身与包门面的转出清单里——**没有任何调用方,也没有任何测试**。
`_send_message_with_keyboard` 只在那条 docstring 里出现过一次,即它从来不曾存在。

**判为 ■ 而不是 ◇ 的理由**:它不是"代码有、文档无",而是"**代码在,但和它自己的说明书
对不上,且行为比在用的那条路径弱**"。孤儿代码本身不危险,危险的是它**长得像可用的公共 API**
(挂在包门面的导出清单上),而它的说明书会把使用者引向一个错误的调用形状和一个更弱的安全默认。

### 4.5 交互事件的归一化

`gateway/platforms/qqbot/keyboards.py:432` @ 863e313

```python
    @property
    def operator_openid(self) -> str:
        """Best available operator openid (group → member; c2c → user)."""
        return (
            self.group_member_openid
            or self.user_openid
            or self.resolver_user_id
        )
```

QQ 在群场景给 `group_member_openid`、在私聊给 `user_openid`,还有一个 `resolved.user_id`。
`operator_openid` 把三者折成一个「谁点的按钮」——这是**授权判定要用的那个身份**,
所以它必须只有一个取值口径。三级回落的顺序(群成员 → 私聊用户 → resolved)
把"最具体的身份优先"写死了。

---

## 5. 簇五:QQ Bot 的扫码配号 —— `gateway/platforms/qqbot/onboard.py`(220 行)

### 5.1 场景

**场景**:运维在终端跑网关设置向导,选 QQ Bot。他不想去开放平台后台复制粘贴
`app_id` / `client_secret`,而是希望**用手机扫个码就配好**。这个文件实现的就是这条路:
建绑定任务 → 终端里画二维码 → 轮询扫码结果 → 本地解密拿到密钥。

`gateway/platforms/qqbot/onboard.py:1` @ 863e313

```python
"""
QQBot scan-to-configure (QR code onboard) module.

Mirrors the Feishu onboarding pattern: synchronous HTTP + a single public
entry-point ``qr_register()`` that handles the full flow (create task →
display QR code → poll → decrypt credentials).

Calls the ``q.qq.com`` ``create_bind_task`` / ``poll_bind_result`` APIs to
generate a QR-code URL and poll for scan completion.  On success the caller
receives the bot's *app_id*, *client_secret* (decrypted locally), and the
scanner's *user_openid* — enough to fully configure the QQBot gateway.

Reference: https://bot.q.qq.com/wiki/develop/api-v2/
"""
```

它被网关设置向导直接调用:

`hermes_cli/gateway.py:6047` @ 863e313

```python
    if method_idx == 0:
        # ── QR scan-to-configure ──
        try:
            from gateway.platforms.qqbot import qr_register

            credentials = qr_register()
```

### 5.2 密钥不走明文:本地生成 AES 密钥,服务端加密回传

`gateway/platforms/qqbot/onboard.py:84` @ 863e313

```python
def _create_bind_task(timeout: float = ONBOARD_API_TIMEOUT) -> Tuple[str, str]:
    """Create a bind task and return *(task_id, aes_key_base64)*.

    Raises:
        RuntimeError: If the API returns a non-zero ``retcode``.
    """
    import httpx

    url = f"https://{PORTAL_HOST}{ONBOARD_CREATE_PATH}"
    key = generate_bind_key()

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.post(url, json={"key": key}, headers=get_api_headers())
```

`generate_bind_key()` 在**本地**生成一把密钥,随建任务请求上行;扫码完成后服务端返回的是
`bot_encrypt_secret`,由 `decrypt_secret(encrypted_secret, aes_key)` 在本地解开。
于是**明文 client_secret 从不在响应体里出现**。这是扫码配号这类流程的标准形状,
值得记下来的是它把「谁持有解密能力」钉在了发起方。

### 5.3 二维码过期的三次续期

`gateway/platforms/qqbot/onboard.py:207` @ 863e313

```python
            if status == BindStatus.EXPIRED:
                if refresh_count >= _MAX_REFRESHES:
                    logger.warning("[QQBot onboard] QR code expired %d times — giving up", _MAX_REFRESHES)
                    return None
                print(f"\n  QR code expired, refreshing... ({refresh_count + 1}/{_MAX_REFRESHES})")
                break  # next for-loop iteration creates a new task
```

外层 `for refresh_count in range(_MAX_REFRESHES + 1)` 负责「换一张码」,内层 `while` 负责轮询;
`BindStatus.EXPIRED` 时 `break` 出内层,外层就会新建一个任务。整体寿命由
`timeout_seconds`(默认 600 秒)统一封顶,而不是由续期次数决定——两道闸门,谁先到算谁。

### 5.4 ▲-B1-01:`QQ_PORTAL_HOST` 只改了三条 URL 中的两条,二维码那条是写死的

文档两处都把这个变量说成「覆盖 QQ portal 主机」,并且明确给出 sandbox 用法。

`website/docs/reference/environment-variables.md:478` @ 863e313

> | `QQ_PORTAL_HOST` | Override the QQ portal host (set to `sandbox.q.qq.com` to route through the sandbox gateway; default: `q.qq.com`). |

`website/docs/user-guide/messaging/qqbot.md:56` @ 863e313

> | `QQ_PORTAL_HOST` | Override the QQ portal host (set to `sandbox.q.qq.com` for sandbox routing) | `q.qq.com` |

(两条都在各自文档的 `## Environment Variables` 标题下的表里,整句就是这一格,
没有别的从句需要一并判定。)

代码侧:`_create_bind_task` 与 `_poll_bind_result` 确实用 `PORTAL_HOST` 拼 URL(见 §5.2 的摘录),
**但递给用户去扫的那条 URL 用的是一个写死了主机名的模板**:

`gateway/platforms/qqbot/constants.py:25` @ 863e313

```python
# QR-code onboard endpoints (on the portal host)
ONBOARD_CREATE_PATH = "/lite/create_bind_task"
ONBOARD_POLL_PATH = "/lite/poll_bind_result"
QR_URL_TEMPLATE = (
    "https://q.qq.com/qqbot/openclaw/connect.html"
    "?task_id={task_id}&_wv=2&source=hermes"
)
```

`gateway/platforms/qqbot/onboard.py:144` @ 863e313

```python
def build_connect_url(task_id: str) -> str:
    """Build the QR-code target URL for a given *task_id*."""
    return QR_URL_TEMPLATE.format(task_id=quote(task_id))
```

于是设了 `QQ_PORTAL_HOST=sandbox.q.qq.com` 之后:**绑定任务建在 sandbox,
而用户被要求去扫一张指向生产 `q.qq.com` 的二维码**——那边不存在这个 `task_id`。
轮询会一直拿到 `PENDING`,直到 600 秒超时,而日志里不会有任何异常。

**判 ▲ 的理由**:文档说的是「覆盖 portal 主机 / 走 sandbox 路由」,而二维码 URL 的主机
`q.qq.com` **正是同一个 portal 主机**(上面那段摘录第一行的注释自己写着
`QR-code onboard endpoints (on the portal host)`),它没有被覆盖。这不是"文档没提",
是"文档说了而代码只做了一部分",属矛盾。

**搜索面**:`PORTAL_HOST|QR_URL_TEMPLATE|QQ_PORTAL_HOST` 三个模式,在
`--include=*.py --include=*.md --include=*.ts --include=*.mdx --include=*.yaml --include=*.yml
--include=*.toml --include=*.json` 下扫全树;`PORTAL_HOST` 的**全部**使用点是
`_create_bind_task` 与 `_poll_bind_result` 各一处,`QR_URL_TEMPLATE` 的唯一使用点是
`build_connect_url`,三处都在这个 onboard 模块里,别处没有。

### 5.5 ▲-B1-02(相邻发现,已越出本片 12 文件但同源):`QQ_SANDBOX` 是一个没人读的开关

紧挨着上一条,文档还列了另一个 QQ 沙箱变量:

`website/docs/reference/environment-variables.md:479` @ 863e313

> | `QQ_SANDBOX` | Enable QQ sandbox mode for development testing (`true`/`false`) |

```verify
cd /home/user/hermes-agent && grep -rni --exclude-dir=__pycache__ "qq_sandbox" . | sort
```

```text
./hermes_cli/config_defaults.py:4152:    "QQ_SANDBOX": {
./website/docs/reference/environment-variables.md:479:| `QQ_SANDBOX` | Enable QQ sandbox mode for development testing (`true`/`false`) |
```

**搜索面**:全树、不限扩展名、忽略大小写、排除 `__pycache__`。只有两处:一处是文档,
一处是 CLI 的环境变量目录(它决定设置向导会**提示用户填什么**):

`hermes_cli/config_defaults.py:4152` @ 863e313

```python
    "QQ_SANDBOX": {
        "description": "Enable QQ sandbox mode for development testing (true/false)",
        "prompt": "QQ Sandbox Mode",
        "category": "messaging",
    },
```

**没有任何代码读取它**——QQ Bot 包里 `sandbox` 一词只出现在关闭码 4914 的注释里。
所以设置向导会引导用户配一个**完全无效**的开关,
而真正管 sandbox 的是上一条那个只生效一半的 `QQ_PORTAL_HOST`。

这条的锚点文件不在本片 12 个之内,但它是 §5.4 的直接邻居,记在这里并列入 §移交。

### 5.6 两处稳健性观察(不判缺陷,但要记)

**(a) 轮询循环吞掉一切异常。**

`gateway/platforms/qqbot/onboard.py:187` @ 863e313

```python
        # ── Poll loop ──
        while time.monotonic() < deadline:
            try:
                status, app_id, encrypted_secret, user_openid = _poll_bind_result(task_id)
            except Exception:
                time.sleep(ONBOARD_POLL_INTERVAL)
                continue
```

`_poll_bind_result` 在 `retcode != 0` 时抛 `RuntimeError`,而这里 `except Exception` 一律吞掉、
睡 2 秒再来。设计意图明显是「网络抖动不该让扫码流程崩」,代价是**永久性失败与暂时性失败
完全同形**:两者都表现为"转 10 分钟然后超时"。这与 §2.3 里 QQ Bot 连接层
(短连接抖动计数 + 快速失败)的态度正相反,同一个包里两种取舍。

**(b) 这条 HTTP 路径没有 SSRF 守卫。**

`gateway/platforms/qqbot/onboard.py:95` @ 863e313

```python
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.post(url, json={"key": key}, headers=get_api_headers())
```

用的是裸的 `httpx.Client`,不是仓库里那个装了连接期校验的安全客户端,也没有挂重定向守卫。
对比同一个包的适配器侧:

`gateway/platforms/qqbot/adapter.py:344` @ 863e313

```python
            self._http_client = create_ssrf_safe_async_client(
                timeout=30.0,
                follow_redirects=True,
                event_hooks={"response": [_ssrf_redirect_guard]},
                limits=platform_httpx_limits(),
            )
```

目标 URL 由 `PORTAL_HOST` 决定,而它来自**运维自己设的环境变量**,
所以这不是攻击面(运维本就能指向任何地方);但 `follow_redirects=True` 意味着
portal 一次 307 重定向就能把「本地生成的 AES 密钥」这个请求体原样带到别的主机。
**一致性缺口,不是可利用漏洞。**

### 5.7 ◇-B1-03:这个文件零测试覆盖

```verify
cd /home/user/hermes-agent && grep -rn "qqbot.onboard\|_create_bind_task\|_poll_bind_result\|build_connect_url\|BindStatus" tests | sort; echo "(以上为空即零命中)"; ls tests/gateway/ | grep -i onboard
```

```text
(以上为空即零命中)
test_feishu_onboard.py
```

**搜索面**:`tests/` 全树,五个模式(模块路径、两个私有 HTTP 助手、公开 URL 构造函数、状态枚举)。
零命中。而**同一形状的飞书扫码流程有一份专门的测试文件**,里面覆盖了成功流、轮询失败、
探测失败仍成功三种路径。上面 §5.1 的模块 docstring 明说自己
`Mirrors the Feishu onboarding pattern`——**镜像了实现,没镜像测试**。
§5.4 那条 ▲ 能活下来,和这里零覆盖是同一件事的两面。

---

## 6. 簇六:元宝的手写 protobuf —— `gateway/platforms/yuanbao_proto.py`(1,418 行)

### 6.1 场景与分层

**场景**:元宝(腾讯 Yuanbao)的机器人通道走 WebSocket,帧体是 protobuf 二进制。
Hermes 要么引入 protobuf 运行时 + 生成代码,要么**手写 wire-format 编解码**。它选了后者。

> **术语**:*protobuf wire format* —— Google Protocol Buffers 的二进制编码。每个字段编码成
> 「tag(字段号<<3 | 线型)+ 值」,整数用变长的 varint,字符串/嵌套消息用「长度前缀 + 字节」。
> 解析器**不需要知道 schema** 也能把一条消息拆成 (字段号, 线型, 原始值) 的列表——
> 这正是手写实现可行的原因。

`gateway/platforms/yuanbao_proto.py:1` @ 863e313

```python
"""
yuanbao_proto.py - Yuanbao WebSocket 协议编解码（纯 Python 实现）

协议层级：
  WebSocket frame
    └── ConnMsg (protobuf: trpc.yuanbao.conn_common.ConnMsg)
          ├── head: Head  (cmd_type, cmd, seq_no, msg_id, module, ...)
          └── data: bytes  (业务 payload，标准 protobuf)
                └── InboundMessagePush / SendC2CMessageReq / SendGroupMessageReq / ...
                      (trpc.yuanbao.yuanbao_conn.yuanbao_openclaw_proxy.*)
```

两层:外层 `ConnMsg`(连接层,含 head 与一段不透明的 `data`),内层是业务 protobuf。
文件里还专门澄清了一处**容易被 `.proto` 注释误导**的地方:

`gateway/platforms/yuanbao_proto.py:12` @ 863e313

```python
注意：conn 层（ConnMsg）本身是标准 protobuf，不是自定义二进制格式。
     conn.proto 注释里的自定义格式（magic+head_len+body_len）仅用于 quic/tcp，
     WebSocket 直接传 ConnMsg protobuf bytes（无粘包问题，每个 ws frame = 一条消息）。

实现方式：手写 varint / protobuf wire-format 编解码，不依赖第三方 protobuf 库。
"""
```

`conn.proto` 注释里那套 `magic+head_len+body_len` 的自定义分帧**只用于 quic/tcp**;
WebSocket 每帧即一条消息,不存在粘包,所以直接传 `ConnMsg` 的 protobuf 字节。
**把"我为什么没实现 spec 里的那一段"写进模块 docstring**——这是逆向协议实现最该留的一类注释。

### 6.2 手写编码器复刻了 proto3 的「默认值不上线」

`gateway/platforms/yuanbao_proto.py:302` @ 863e313

```python
    """编码 ConnMsg.Head"""
    buf = b""
    if cmd_type != 0:
        buf += _encode_field(1, WT_VARINT, _encode_varint(cmd_type))
    if cmd:
        buf += _encode_field(2, WT_LEN, _encode_string(cmd))
    if seq_no != 0:
        buf += _encode_field(3, WT_VARINT, _encode_varint(seq_no))
    if msg_id:
        buf += _encode_field(4, WT_LEN, _encode_string(msg_id))
    if module:
        buf += _encode_field(5, WT_LEN, _encode_string(module))
    if need_ack:
        buf += _encode_field(6, WT_VARINT, _encode_varint(1))
    if status != 0:
        buf += _encode_field(10, WT_VARINT, _encode_varint(status & 0xFFFFFFFFFFFFFFFF))
    return buf
```

每个字段都带 `if`:值为 0 / 空串 / False 时**整个字段不编码**。这是 proto3 的语义
(默认值不上线,解码方按缺省补),不是随手写的优化——如果漏了这些 `if`,
对端用标准 protobuf 库解出来的结果仍然正确,但字节流与官方客户端不一致,
任何做字节级比对或签名的中间层都会出问题。

与之配套的是序列号生成器:

`gateway/platforms/yuanbao_proto.py:108` @ 863e313

```python
_seq_lock = threading.Lock()
_seq_counter = 0
_SEQ_MAX = 2 ** 32 - 1  # uint32 上限


def next_seq_no() -> int:
    """生成递增序列号（线程安全，溢出时归零）"""
    global _seq_counter
    with _seq_lock:
        val = _seq_counter
        _seq_counter = (_seq_counter + 1) & _SEQ_MAX
    return val
```

计数器从 0 起、先取值后自增,所以**进程内第一条消息的 `seq_no` 是 0**,
而按上面的 proto3 规则,`seq_no=0` 的字段**不会出现在线上**。实测:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'PY'
import sys
sys.path.insert(0, ".")
from gateway.platforms import yuanbao_proto as P
print("DEBUG_MODE               =", P.DEBUG_MODE)
print("first next_seq_no()      =", P.next_seq_no())
h0 = P._encode_head(cmd_type=0, cmd="ping", seq_no=0, msg_id="m1", module="conn_access")
h1 = P._encode_head(cmd_type=0, cmd="ping", seq_no=1, msg_id="m1", module="conn_access")
print("head fields, seq_no=0    :", sorted(fn for fn, wt, v in P._parse_fields(h0)))
print("head fields, seq_no=1    :", sorted(fn for fn, wt, v in P._parse_fields(h1)))
print("decode_inbound_push(bad) :", P.decode_inbound_push(b"\xff"))
try:
    P.decode_conn_msg(b"\xff\xff")
except Exception as e:
    print("decode_conn_msg(bad)     :", type(e).__name__, e)
PY
```

```text
DEBUG_MODE               = False
first next_seq_no()      = 0
head fields, seq_no=0    : [2, 4, 5]
head fields, seq_no=1    : [2, 3, 4, 5]
decode_inbound_push(bad) : None
decode_conn_msg(bad)     : ValueError unknown wire type 7 at pos 1
```

`seq_no=0` 时 head 只有字段 2/4/5(cmd / msg_id / module),字段 3 缺席;`seq_no=1` 时才出现。
**这是对的**(与官方客户端一致),但对一个靠 seq 做请求-响应配对的实现来说,
「第一条请求没有 seq」是必须知道的事实——这也是为什么这份实现主要靠 `msg_id` 配对
(`encode_biz_msg` 把调用方给的 `req_id` 放进 `head.msg_id`)。

### 6.3 两层解码的错误处理**故意不一致**

上面同一个探针还打出:`decode_conn_msg` 遇到坏字节**抛 ValueError**,
而 `decode_inbound_push` 遇到坏字节**返回 None**。

`gateway/platforms/yuanbao_proto.py:740` @ 863e313

```python
        }
        # 过滤空值（保持 API 整洁）
        return {k: v for k, v in result.items() if v or k in {"msg_body", "msg_seq"}}
    except Exception as e:
        if DEBUG_MODE:
            logger.debug("[yuanbao_proto] decode_inbound_push failed: %s", e)
        return None
```

分工是清楚的:连接层解码失败 = 这条 WS 帧根本不是 `ConnMsg`,属于**协议级故障**,该炸给上层;
业务层解码失败 = 某一类推送我们没见过,属于**版本差**,该丢掉继续跑。
这正是 r7b 章第 4 节原则 15(「未知的枚举值不是错误,是版本差」)在解码层的落法。

### 6.4 ■-B1-06:两条失败日志被一个永远为 False 的常量关死

上一个探针的第一行:`DEBUG_MODE = False`。而 `decode_inbound_push` 的失败日志写在
`if DEBUG_MODE:` 之下(见 §6.3 摘录的后三行),另一处 forward 解码的失败日志同理。

`gateway/platforms/yuanbao_proto.py:28` @ 863e313

```python
# Debug 开关
# ============================================================

DEBUG_MODE = False


def _dbg(label: str, data: bytes) -> None:
    if DEBUG_MODE:
        hex_str = " ".join(f"{b:02x}" for b in data[:64])
        ellipsis = "..." if len(data) > 64 else ""
        logger.debug("[yuanbao_proto] %s (%dB): %s", label, len(data), hex_str + ellipsis)
```

**搜索面**:基线全树 `*.py` 搜 `DEBUG_MODE`,命中 4 处——本文件里的
定义一处与使用三处,外加 `tools/debug_helpers.py` 一处**无关**的 docstring 提及
(它讲的是它替换掉的另一套 DEBUG_MODE)。
**没有任何地方给这个模块的 `DEBUG_MODE` 赋值**,也没有环境变量或配置项接到它上面。

后果:一条解不开的入站推送会被**完全静默地丢弃**——没有日志、没有指标、没有异常。
在一个逆向出来的协议实现里,这恰恰是最需要可观测性的地方:对端加了个字段、
换了个 wire type,现场表现是"消息偶尔收不到",而日志里什么都没有。
`_dbg` 那套十六进制转储明明写好了(上面摘录的后 5 行),却只能靠改源码打开。

**这条与 §6.3 的取舍是两件事**:"解不开就丢"是对的;"丢了不留痕"不是。

### 6.5 auth-bind 里那个写死的实例号

`gateway/platforms/yuanbao_proto.py:1147` @ 863e313

```python
    # DeviceInfo
    dev_buf = b""
    if app_version:
        dev_buf += _encode_field(1, WT_LEN, _encode_string(app_version))
    if operation_system:
        dev_buf += _encode_field(2, WT_LEN, _encode_string(operation_system))
    dev_buf += _encode_field(10, WT_LEN, _encode_string(str(HERMES_INSTANCE_ID)))
    if bot_version:
        dev_buf += _encode_field(24, WT_LEN, _encode_string(bot_version))
```

`DeviceInfo.instance_id`(字段 10)恒等于 `HERMES_INSTANCE_ID`:

`gateway/platforms/yuanbao_proto.py:97` @ 863e313

```python
# openclaw instance_id（固定值 17）
HERMES_INSTANCE_ID = 17
```

这是**平台侧分配给这个集成的身份号**,和 UA 一样是给对端做来源识别的。
注意它被 `str()` 之后当**字符串**编码——字段 10 在 wire 上是长度前缀的 `"17"`,不是 varint 17。
手写编码器里这类「schema 说 string 而值看起来像数字」的地方,
是最容易写错、且错了对端只会报一个泛化错误的地方。

### 6.6 解码结果会**丢掉所有假值字段**

见 §6.3 的摘录第三行:结果 dict 被一个条件推导式过滤,只有 `msg_body` 与 `msg_seq` 被显式豁免,
其余空字符串、0、空列表全被删掉。理由写着「保持 API 整洁」,
代价是**返回的 dict 的键集合随内容而变**:调用方读群号在私聊消息上会 `KeyError`,必须一律 `.get()`。
这是一个典型的「为了打印好看而牺牲结构稳定」的取舍,值得作为反面样本记下来——
**解码器的输出形状应当由 schema 决定,不由某一条消息的取值决定**。

---

## 7. 簇七:元宝的出网下载与 COS 直传 —— `gateway/platforms/yuanbao_media.py`(665 行)

### 7.1 场景

**场景**:模型在回复里带了一个图片 URL,或者用户在元宝里发来一个文件。两种情况下网关都要
**在服务端**把字节取下来,再上传到腾讯云对象存储(COS),然后把 COS 的地址拼进腾讯 IM 的消息体。
这条链路上有两个安全面:**出网下载**(SSRF)和**云存储签名**。

> **术语**:*SSRF*(服务端请求伪造)—— 让服务器去访问它内网里的地址。经典目标是
> `169.254.169.254`,云厂商的元数据端点,能读出实例凭据。
> *COS* —— 腾讯云对象存储;这里用的是它的 `q-sign-algorithm=sha1` 签名方案。

### 7.2 下载:预检 + 边下边核

`gateway/platforms/yuanbao_media.py:253` @ 863e313

```python
        # GET 下载（流式读取，防止超限）
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "").split(";")[0].strip()

            chunks: list[bytes] = []
            downloaded = 0
            async for chunk in resp.aiter_bytes(65536):
                downloaded += len(chunk)
                if downloaded > max_bytes:
                    raise ValueError(
                        f"文件过大: 已超过 {max_size_mb} MB 限制"
                    )
                chunks.append(chunk)
```

先用 HEAD 读 `content-length` 提前拒绝,再在流式 GET 里**逐块累加复核**。
这正是 r7b 章第 4 节原则 20 的字面落地:**对端声明的尺寸只能用于提前拒绝,不能用于确认放行**。
一个撒谎的 `content-length`(声明 1 KB 实际 1 GB)会在第 16 个块被拦下,而不是把内存打爆。

### 7.3 ■-B1-07:重定向守卫的判定式在 httpx 里**永远不成立**

`gateway/platforms/yuanbao_media.py:220` @ 863e313

```python
    # SSRF protection: yuanbao downloads model-supplied and inbound URLs
    # server-side. Reject private/internal targets up front, and re-validate
    # every redirect hop so a public URL can't 302 to http://169.254.169.254/.
    from tools.url_safety import create_ssrf_safe_async_client, is_safe_url

    if not is_safe_url(url):
        raise ValueError(f"Blocked unsafe URL (SSRF protection): {url}")

    async def _redirect_guard(response: httpx.Response) -> None:
        if response.is_redirect and response.next_request:
            redirect_url = str(response.next_request.url)
            if not is_safe_url(redirect_url):
                raise ValueError(
                    f"Blocked redirect to private/internal address: {redirect_url}"
                )
```

注释承诺 `re-validate every redirect hop so a public URL can't 302 to http://169.254.169.254/`。
判定式是 `response.is_redirect and response.next_request`。

**问题**:在 `httpx.AsyncClient` 的 response 事件钩子里,`response.next_request` 通常是 `None`
——它由跟随重定向的机制在**之后**才填。仓库自己**为了修这个 bug** 写过一个共享助手,
它的 docstring 把这件事说得一字不差:

`tools/url_safety.py:850` @ 863e313

```python
def redirect_target_from_response(response: Any) -> Optional[str]:
    """Return the redirect target visible from inside an httpx response hook.

    In ``httpx.AsyncClient`` response event hooks, ``response.next_request`` is
    frequently ``None`` even for a genuine redirect (it is populated later by
    the redirect-following machinery). Relying on ``next_request`` alone means
    an SSRF redirect guard silently never fires: a public URL that 302s to
    ``http://169.254.169.254/`` gets followed anyway. The ``Location`` header,
    however, is already present on the response, so resolve the target from it
    first (handling relative Locations via ``urljoin``) and only fall back to
    ``next_request`` when no ``Location`` header is set.
    """
```

**实测**(用 httpx 的 `MockTransport` 复刻上面那个判定式,看它在一次 302 到元数据端点时是否触发;
顺带把下一段要用的异常层级也打出来):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'PY'
import asyncio, httpx

# (a) except httpx.HTTPStatusError 只可能由 raise_for_status() 抛出
print("HTTPStatusError bases   :", [c.__name__ for c in httpx.HTTPStatusError.__mro__[1:3]])
print("ConnectError caught?    :", issubclass(httpx.ConnectError, httpx.HTTPStatusError))
print("RemoteProtocolError?    :", issubclass(httpx.RemoteProtocolError, httpx.HTTPStatusError))

# (b) 复刻元宝那个重定向判定式,看它在 302 时是否触发
seen = []
async def guard(response):
    if response.is_redirect and response.next_request:
        seen.append(("FIRED", str(response.next_request.url)))
    elif response.is_redirect:
        seen.append(("SKIPPED", response.headers.get("location", "")))

def handler(request):
    if request.url.path == "/pub":
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})
    return httpx.Response(200, text="metadata")

async def main():
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                 follow_redirects=True,
                                 event_hooks={"response": [guard]}) as c:
        r = await c.get("http://public.example/pub")
        print("final url               :", r.url)
    print("guard observations      :", seen)

asyncio.run(main())
PY
```

```text
HTTPStatusError bases   : ['HTTPError', 'Exception']
ConnectError caught?    : False
RemoteProtocolError?    : False
final url               : http://169.254.169.254/latest/meta-data
guard observations      : [('SKIPPED', 'http://169.254.169.254/latest/meta-data')]
```

`SKIPPED` —— 判定式没成立,重定向被照常跟随,最终 URL 就是元数据端点。**这个钩子是死的。**

**同一个仓库里的兄弟们都用了修好的写法**:`gateway/platforms/base.py` 的
`_ssrf_redirect_guard`(QQ Bot 就是 import 的这一个)、`tools/vision_tools.py` 的两处、
`plugins/platforms/slack/adapter.py` 的一处,全部调 `redirect_target_from_response(response)`。
只有元宝这一处手写了一份仍带原 bug 的版本。

**实际风险有多大,要如实说**:客户端是 `create_ssrf_safe_async_client` 造的,
它在**传输层**装了连接期校验——每一跳的 TCP 连接都会重新解析并校验目标 IP,
所以在直连场景下 `169.254.169.254` 仍然连不上。但那份工厂函数的 docstring 自己写着:

`tools/url_safety.py:825` @ 863e313

```python
def create_ssrf_safe_async_client(**kwargs: Any) -> Any:
    """Create an ``httpx.AsyncClient`` with connect-time SSRF validation.

    Direct HTTP(S) connections are resolved, validated, and dialed by IP at
    TCP-connect time while the original request hostname is preserved for Host,
    SNI, and certificate verification.  If httpx routes through a proxy, final
    target resolution is delegated to that configured proxy; treat the proxy as
    a trusted egress boundary.
    """
```

**走代理时最终目标的解析让位给代理**,此时这个死掉的钩子就是重定向这条路上唯一的守卫。
所以这是一条**纵深防御被打掉一层、且注释谎称它还在**的缺陷,不是当场可利用的漏洞。

**顺带一条同源的**:`except httpx.HTTPStatusError` 那个兜底也是错的类型。

`gateway/platforms/yuanbao_media.py:242` @ 863e313

```python
        # 先 HEAD 检查大小
        try:
            head = await client.head(url)
            content_length = int(head.headers.get("content-length", 0) or 0)
            if content_length > 0 and content_length > max_bytes:
                raise ValueError(
                    f"文件过大: {content_length / 1024 / 1024:.1f} MB > {max_size_mb} MB"
                )
        except httpx.HTTPStatusError:
            pass  # 部分服务器不支持 HEAD，忽略
```

注释说「部分服务器不支持 HEAD,忽略」,但 `httpx.HTTPStatusError` **只可能由
`raise_for_status()` 抛出**(上面探针第 1~3 行:它是 `HTTPError` 的子类,而
`ConnectError` / `RemoteProtocolError` 都不是它的子类),而这段代码**没有调
`raise_for_status()`**。真实情况是:服务器用 405 拒绝 HEAD 时根本不抛异常
(于是"忽略"是靠 `content_length == 0` 达成的,而不是靠这个 `except`);
服务器**直接断连**拒绝 HEAD 时抛的是 `RemoteProtocolError`,**不被这个 `except` 捕获**,
整个下载失败。另外 `int(...)` 在 `content-length` 是畸形值时抛 `ValueError`,同样不被捕获。
**一个类型写错的 `except` 比没有 `except` 更糟:它让读者以为这里已经兜住了。**

### 7.4 COS 签名:全部手写,没引 SDK

`gateway/platforms/yuanbao_media.py:302` @ 863e313

```python
    now = int(time.time())
    q_sign_time = f"{start_time or now};{(start_time or now) + expire_seconds}"

    # Step 1: SignKey = HMAC-SHA1(SecretKey, q-sign-time)
    sign_key = hmac.new(
        secret_key.encode("utf-8"),
        q_sign_time.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()
```

签名是四步:`SignKey = HMAC-SHA1(SecretKey, q-sign-time)` → 拼 HttpString(方法/路径/
排序后的参数/排序后的头)→ 取 SHA1 → `Signature = HMAC-SHA1(SignKey, StringToSign)`。
模块开头写明了动机:用 `httpx` 替代 `cos-nodejs-sdk-v5`,**避免为一个平台引入一整个 SDK**。
取舍很清楚:少一条依赖链,多一段必须自己维护的密码学拼装代码。

### 7.5 ■-B1-08(潜伏):签名有效期的起点与长度取自两个不同的时间基准

`gateway/platforms/yuanbao_media.py:518` @ 863e313

```python
    # 计算签名有效期
    now = int(time.time())
    sign_start = start_time if start_time else now
    sign_expire = (expired_time - now) if expired_time and expired_time > now else 3600
```

`sign_start` 取**凭证签发时间**(`startTime`,过去的某一刻),
`sign_expire` 取**从现在起的剩余寿命**(`expiredTime - now`)。
而签名窗口是这样拼的:

`gateway/platforms/yuanbao_media.py:302` @ 863e313

```python
    now = int(time.time())
    q_sign_time = f"{start_time or now};{(start_time or now) + expire_seconds}"
```

于是窗口终点 = `startTime + (expiredTime - now)`。
**只要凭证不是刚签发的,这个终点就比真正的过期时间早**,早出的量正好是凭证已经活过的时长。
极端情形:凭证寿命过半时才用,窗口终点 ≈ `now`,签名**一签出来就过期**,COS 直接 403。

**当前不触发**,因为调用方是「拿凭证 → 立刻上传」,`startTime ≈ now` 时两个基准重合。
所以这是一条**潜伏缺陷**:任何一次「缓存/复用 COS 凭证」的优化都会把它引爆,
而症状(403 SignatureDoesNotMatch)看起来像密钥错误,不像时间窗错误。
正确写法是让两端来自同一基准:起点取 `startTime`、长度取 `expiredTime - startTime`。

### 7.6 图片尺寸:四种格式的纯 Python 头解析

`gateway/platforms/yuanbao_media.py:121` @ 863e313

```python
def parse_image_size(data: bytes) -> Optional[dict[str, int]]:
    """
    解析图片宽高（支持 JPEG/PNG/GIF/WebP），无需第三方依赖。
    返回 {"width": w, "height": h} 或 None（无法识别）。
    """
    return (
        _parse_png_size(data)
        or _parse_jpeg_size(data)
        or _parse_gif_size(data)
        or _parse_webp_size(data)
    )
```

`build_image_msg_body` 要往 TIM 消息体里填 `width` / `height`,而为此引入 Pillow 太重。
于是 PNG / JPEG / GIF / WebP 四种格式各写了一段**只读文件头**的解析
(PNG 直接读 IHDR 的两个大端 u32;JPEG 要扫段直到 SOF0/SOF2;WebP 还分 VP8/VP8L/VP8X 三种子格式)。
四个函数全部「看不懂就返回 None」,`parse_image_size` 用 `or` 串起来。
**取舍**:省掉一个重依赖,代价是新增格式(AVIF、HEIC)时静默丢失尺寸——
而尺寸缺失在 IM 侧的表现是图片以默认比例显示,不是报错。

---

## 8. 簇八:元宝贴纸 —— `gateway/platforms/yuanbao_sticker.py`(558 行)

### 8.1 场景

**场景**:模型想在元宝里回一个「六六六」表情。TIM 协议里表情是 `TIMFaceElem`,
需要一个 `sticker_id` + `package_id`。模型只知道自然语言,于是需要一层
「中文描述 → 贴纸元数据」的查找。这个文件 = 一张 59 条的内置贴纸表 + 一个模糊搜索 + 消息体构造。

`gateway/platforms/yuanbao_sticker.py:1` @ 863e313

```python
"""
Yuanbao sticker (TIMFaceElem) support.

Ported from yuanbao-openclaw-plugin/src/sticker/.

TIMFaceElem wire format:
    {
        "msg_type": "TIMFaceElem",
        "msg_content": {
            "index": 0,          # always 0 per Yuanbao convention
            "data": "<json>",    # serialised sticker metadata
        }
    }

The `data` field carries a JSON string with the sticker's metadata so the
receiver can look up the correct asset in the emoji pack.
"""
```

表里每条都带一串**同义词**当 `description`(如「六六六」的 `666 厉害 牛 棒 绝了 好强 awesome`),
这是给模糊搜索用的召回面——**表本身就是检索索引**。

### 8.2 两个入口,两种语义

agent 侧有两个工具:一个返回 Top-N 候选让模型挑,一个直接发。后者先按 id 精确查,查不到再按名字查:

`gateway/platforms/yuanbao_sticker.py:331` @ 863e313

```python
def get_sticker_by_name(name: str) -> Optional[dict]:
    """
    按名称查找贴纸，支持模糊匹配。

    匹配优先级：
      1. 完全相等（name）
      2. name 包含查询词（前缀/子串）
      3. description 包含查询词（同义词搜索）
      4. 通用模糊评分（与 sticker-search 同算法），命中即返回得分最高的一条

    返回 sticker dict，找不到返回 None。
    """
    if not name:
```

四级:全等 → 名字双向包含 → 描述包含 → 通用模糊评分。

### 8.3 ■-B1-09:`get_sticker_by_name` 对任何非空查询都必然命中

`gateway/platforms/yuanbao_sticker.py:344` @ 863e313

```python
        return None

    query = name.strip()

    if query in STICKER_MAP:
        return STICKER_MAP[query]

    for key, sticker in STICKER_MAP.items():
        if query in key or key in query:
            return sticker

    for sticker in STICKER_MAP.values():
        desc = sticker.get("description", "")
        if query in desc:
            return sticker

    matches = search_stickers(query, limit=1)
    return matches[0] if matches else None
```

最后一级 `search_stickers(query, limit=1)` 是**全表打分排序**,而它在「最高分 ≤ 0」时
仍然返回前 N 条:

`gateway/platforms/yuanbao_sticker.py:494` @ 863e313

```python
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[0][0] if scored else 0
    if top <= 0:
        return [s for _, s in scored[:safe_limit]]

    if top >= 22:
        floor = 18.0
    elif top >= 12:
        floor = max(10.0, top * 0.5)
    else:
        floor = max(6.0, top * 0.35)

    filtered = [pair for pair in scored if pair[0] >= floor]
    out = filtered if filtered else scored
    return [s for _, s in out[:safe_limit]]
```

`if top <= 0:` 那一支直接把排序结果切片返回——**没有"找不到"这个出口**。
于是 `get_sticker_by_name` 只有在 `name` 是**空串**时才返回 `None`。

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'PY'
import sys
sys.path.insert(0, ".")
from gateway.platforms.yuanbao_sticker import STICKER_MAP, get_sticker_by_name
print("STICKER_MAP entries:", len(STICKER_MAP))
print("single-char keys   :", [k for k in STICKER_MAP if len(k) == 1])
for q in ["", "   ", "no-such-sticker-9f3", "qwertyuiop", "太阳能板"]:
    s = get_sticker_by_name(q)
    print("get_sticker_by_name(%-21r) -> %s" % (q, s["name"] if s else None))
PY
```

```text
STICKER_MAP entries: 59
single-char keys   : ['酷', '睡', '吓', '哼', '困', '哦', '怒']
get_sticker_by_name(''                   ) -> None
get_sticker_by_name('   '                ) -> 六六六
get_sticker_by_name('no-such-sticker-9f3') -> 比心
get_sticker_by_name('qwertyuiop'         ) -> 比心
get_sticker_by_name('太阳能板'               ) -> 太阳
```

三件事被这个探针钉住:

1. **纯 ASCII 乱码也命中**:`no-such-sticker-9f3` 与 `qwertyuiop` 都返回「比心」。
   调用方拿不到「没这个贴纸」的信号,模型也就永远学不会自己名字写错了。
2. **纯空白串返回第一条**:`"   "` 不满足 `if not name`,`query` 变成空串,
   于是第二级的 `query in key` 对**第一个键**立即为真,返回表里的第一条「六六六」。
   `""` 和 `"   "` 走出两种完全不同的结果,而两者对用户是同一个输入。
3. **单字键会吃掉任何含该字的查询**:表里有 7 个单字键(`酷 睡 吓 哼 困 哦 怒`),
   第二级的 `key in query` 让「我好困哦」这类句子在**字典插入顺序**上先命中谁就是谁。
   `太阳能板 → 太阳` 是同一机制的温和版本。

**下游后果**:调用侧写了一条永远走不到的错误分支:

`gateway/platforms/yuanbao.py:4004` @ 863e313

```python
        if sticker_name is not None:
            sticker = get_sticker_by_name(sticker_name)
            if sticker is None:
                raise ValueError(f"Sticker not found: {sticker_name!r}")
            return build_sticker_msg_body(sticker)
```

那句 `raise ValueError` 只在 `sticker_name` 恰好是空串时可达。

**判 ■ 而非「设计取舍」的理由**:模糊匹配兜底本身是合理取舍(宁可发个近似的,
也别让对话卡在"没找到"),但**必须把"这是兜底命中"传出去**。现在的形状是
「一个返回 `Optional[dict]` 的函数,实际上永不返回 `None`」——
签名在撒谎,于是每一个照签名写「若为空则报错」的调用方都写了死代码。
最小修法:让 `search_stickers` 的兜底分支与 `get_sticker_by_name` 各自带一个
是否精确命中的出参,而不是改变兜底策略。

### 8.4 评分函数:一份可以直接抄的中文模糊匹配

`gateway/platforms/yuanbao_sticker.py:444` @ 863e313

```python
def _score_field(haystack: str, query: str) -> float:
    hay = _normalize_text(haystack)
    q = _normalize_text(query)
    if not hay or not q:
        return 0.0
    hay_c = _compact_text(haystack)
    q_c = _compact_text(query)
    best = 0.0
    if hay == q:
        best = max(best, 100.0)
    if q in hay:
        best = max(best, 92 + min(6, len(q)))
    if len(q) >= 2 and hay.startswith(q):
        best = max(best, 88.0)
    if q_c and q_c in hay_c:
        best = max(best, 86.0)
    best = max(best, _multiset_char_hit_ratio(q_c, hay_c) * 62)
    best = max(best, _bigram_jaccard(q_c, hay_c) * 58)
    best = max(best, _longest_subsequence_ratio(q_c, hay_c) * 52)
    if len(q) == 1 and q in hay:
        best = max(best, 68.0)
    return best
```

四个信号叠加取最大:子串/前缀命中给高分档(100 / 92+ / 88 / 86),
字符多重集覆盖率 ×62、bigram Jaccard ×58、最长子序列比 ×52。
`_compact_text` 先做 NFKC 归一化再剥掉标点空白,所以「打 call」和「打call」同形。
**中文没有词边界**,所以这里没有分词,直接上字符级多重集与 bigram——
这是中文短串匹配里成本最低、效果够用的一档做法,值得单独记住。

动态阈值那一段(§8.3 的第二个摘录)也是个可抄的模式:**阈值随最高分浮动**
——最高分很高时(≥22)用固定地板 18 卡掉长尾;最高分本来就低时按比例放宽,
保证「弱匹配也能返回一点东西」。代价就是 §8.3 那条:它永远不返回空。

### 8.5 消息体:`index` 恒为 0,真正的信息在 JSON 里

`gateway/platforms/yuanbao_sticker.py:540` @ 863e313

```python
def build_sticker_msg_body(sticker: dict) -> list:
    """
    从 STICKER_MAP 中的 sticker dict 直接构造 TIMFaceElem 消息体。

    这是 send_sticker() 的内部辅助，确保 data 字段与原始 JS 插件一致。
    """
    data_payload = json.dumps(
        {
            "sticker_id": sticker["sticker_id"],
            "package_id": sticker["package_id"],
            "width": sticker.get("width", 128),
            "height": sticker.get("height", 128),
            "formats": sticker.get("formats", "png"),
            "name": sticker["name"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return build_face_msg_body(face_index=0, data=data_payload)
```

`TIMFaceElem` 的传统语义是 `index` = 表情编号,而元宝的约定是 `index` 恒 0、
真实元数据放在 `data` 字段的 JSON 字符串里。`separators=(",", ":")` 与
`ensure_ascii=False` 都是**为了和原 JS 插件产出逐字节一致**——
这类「序列化参数即协议」的细节,是移植类实现最容易漏、且漏了对端只报泛化错误的地方。

`build_face_msg_body` 保留了两个「兼容旧接口」的参数,docstring 里明说其中一个当前未使用:

`gateway/platforms/yuanbao_sticker.py:511` @ 863e313

```python
def build_face_msg_body(
    face_index: int,
    face_type: int = 1,
    data: Optional[str] = None,
) -> list:
    """
    构造 TIMFaceElem 消息体。

    Yuanbao 约定：
      - index 固定传 0（服务端通过 data 字段识别具体表情）
      - data 为 JSON 字符串，包含 sticker_id / package_id 等字段

    Args:
        face_index: 保留字段，暂时不影响 wire format（Yuanbao 固定 index=0）。
                    当 face_index > 0 时视为旧版 QQ 表情 ID，直接放入 index。
        face_type:  保留字段（兼容旧接口，当前未使用）。
        data:       已序列化的 JSON 字符串；为 None 时仅传 index。
```

这类保留参数的正确做法就是像这里一样**在 docstring 里写清楚"保留、当前不影响 wire format"**,
而不是删掉或默默忽略。

---

## 9. 簇九:Microsoft Graph 变更通知入口 —— `gateway/platforms/msgraph_webhook.py`(453 行)

### 9.1 场景:这不是聊天适配器

**场景**:一场 Teams 会议结束,生成了转写文件。M365 需要告诉 Hermes「这件事发生了」。
这就是这个适配器的全部工作:它是一个**入站事件监听器**,不是用户能对它打字的聊天通道。

> **术语**:*Microsoft Graph change notification* —— M365 的 webhook。你先注册一个订阅
> (告诉它「资源 X 变了就 POST 到我这个 URL」),它先发一次 GET 握手要你原样回显
> `validationToken`,之后每次变更都 POST 一个 `{"value": [...]}` 批次,
> 每条都带上你注册时给的 `clientState` 共享密钥。

它的 `send()` 只把内容打进日志——因为这条通道**没有出站方向**:

`gateway/platforms/msgraph_webhook.py:193` @ 863e313

```python
    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        logger.info("[msgraph_webhook] Response for %s: %s", chat_id, content[:200])
        return SendResult(success=True)
```

### 9.2 双栈绑定:与 r7b 章同一处历史 bug 的第三个受害者

`gateway/platforms/msgraph_webhook.py:33` @ 863e313

```python
# ``None`` → aiohttp/asyncio ``create_server`` binds one listening socket per
# address family (IPv4 + IPv6). The old "0.0.0.0" default bound IPv4 ONLY and
# was unreachable over IPv6-only private networks (e.g. Fly.io 6PN) — same
# bug as the LINE adapter (NS-603) and gateway/platforms/webhook.py
# (d542894ad). Pin a host via extra.host. The all-interfaces default still
# requires extra.allowed_source_cidrs (see _source_allowlist_required_but_missing).
DEFAULT_HOST = None
DEFAULT_PORT = 8646
DEFAULT_WEBHOOK_PATH = "/msgraph/webhook"
```

`DEFAULT_HOST = None` 而不是 `"0.0.0.0"`,注释里点名了两个同款前例(LINE 适配器 NS-603、
通用 webhook 的 d542894ad)。这与 CLAUDE.md「已知环境限制」里记的
`gateway/platforms/webhook.py` 的 `DEFAULT_HOST = None` 是同一个语义:
**按解析出的每个地址族各建一个套接字**。`"0.0.0.0"` 只绑 IPv4,在 IPv6-only 的私有网络
(Fly.io 6PN)上不可达。三个适配器踩了同一个坑,**注释链把它们串了起来**——
这是仓库里少见的、把"同类 bug 的前例"写进代码的做法。

### 9.3 失败关闭:公网绑定必须带来源 CIDR 白名单

`gateway/platforms/msgraph_webhook.py:148` @ 863e313

```python
    def _source_allowlist_required_but_missing(self) -> bool:
        # host=None binds all interfaces (both families) — network-accessible.
        host_is_public = self._host is None or is_network_accessible(self._host)
        return host_is_public and not self._allowed_source_networks

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        if self._client_state is None:
            logger.error(
                "[msgraph_webhook] Refusing to start without extra.client_state configured"
            )
            return False
        if self._source_allowlist_required_but_missing():
            logger.error(
                "[msgraph_webhook] Refusing to start: binding to %s requires "
                "extra.allowed_source_cidrs. Configure the Microsoft Graph "
                "source CIDRs or bind to loopback (127.0.0.1/::1) behind a "
                "tunnel or reverse proxy.",
                self._host,
            )
            return False
```

两道启动前闸门:没配 `client_state` 不启动;绑到网络可达地址却没配
`allowed_source_cidrs` 也不启动,并且错误信息直接给出两条出路(配微软的出网段,
或绑回环走隧道/反代)。**这是失败关闭(fail-closed)**:默认不安全的配置不是警告,是拒绝启动。

同一个判据在请求路径上**又查了一遍**:

`gateway/platforms/msgraph_webhook.py:316` @ 863e313

```python
    def _source_ip_allowed(self, request: "web.Request") -> bool:
        """Return True if the request's source IP is in the configured allowlist.

        Loopback-only binds may omit ``allowed_source_cidrs`` for local reverse
        proxies and dev tunnels. Network-accessible binds fail closed until an
        explicit CIDR allowlist is configured.
        """
        if self._source_allowlist_required_but_missing():
            return False
        if not self._allowed_source_networks:
            return True
        peer = request.remote or ""
        if not peer:
            return False
        try:
            peer_addr = ipaddress.ip_address(peer)
        except ValueError:
            return False
        return any(peer_addr in network for network in self._allowed_source_networks)
```

`connect()` 已经拒绝启动了,这里再查一次是纯冗余——**但这正是对的**:
运行期配置若被换掉(重载、多 profile),第二道闸门仍在。而且它对
`request.remote` 为空、无法解析成 IP 的情况都返回 False,同样是失败关闭。

### 9.4 声明的长度只用于提前拒绝

`gateway/platforms/msgraph_webhook.py:245` @ 863e313

```python
        try:
            content_length = request.content_length
        except Exception:
            content_length = None
        if content_length is not None and content_length > self._max_body_bytes:
            return web.Response(status=413)

        try:
            raw_body = await request.read()
        except Exception:
            return web.Response(status=400)
        if len(raw_body) > self._max_body_bytes:
            return web.Response(status=413)
```

`content_length`(请求头,发送方说的)用来提前 413;`len(raw_body)`(实际读到的)再查一次。
和 §7.2 元宝下载那段是同一条原则的另一侧——**入站和出站都遵守它**。
外加 aiohttp 自己的 `client_max_size`(在 `connect()` 里按同一个上限设),一共三层。

### 9.5 常量时间比较,并且先 encode 成字节

`gateway/platforms/msgraph_webhook.py:356` @ 863e313

```python
    def _verify_client_state(self, notification: Dict[str, Any]) -> bool:
        """Verify the Graph-supplied clientState matches the configured secret.

        Uses ``hmac.compare_digest`` instead of ``==`` so that a mismatch
        doesn't leak how many leading characters matched via string-compare
        timing. The configured client_state is a shared secret (documented in
        the setup guide as "generate with ``openssl rand -hex 32``"), so a
        timing-safe compare is the right primitive.
        """
        expected = self._client_state
        if expected is None:
            return False
        provided = self._string_or_none(notification.get("clientState"))
        if provided is None:
            return False
        # Compare as bytes: ``compare_digest`` raises TypeError on a str with
        # non-ASCII characters, and clientState comes from the request body.
        return hmac.compare_digest(provided.encode(), expected.encode())
```

`hmac.compare_digest` 而不是 `==`(防时序侧信道),并且**先 `.encode()`**——
注释直接写明理由:`compare_digest` 对含非 ASCII 字符的 `str` 会抛 `TypeError`,
而 `clientState` 来自请求体,攻击者可控。这就是 r7b 章第 4 节原则 21
(「常量时间比较前先 encode 成字节 —— 一个非 ASCII 字符就能把 401 变成 500」)的**实例**;
r7b 章把它列成了原则,却没有指出仓库里落实它的具体位置,这里补上。

### 9.6 状态码即协议:让 Graph 知道该不该重试

`gateway/platforms/msgraph_webhook.py:303` @ 863e313

```python
        self._duplicate_count += duplicates
        # If anything ingested OR deduped, return 202 with empty body so
        # Graph acks successfully and we don't leak internal counters. If
        # every item failed auth, return 403 so an attacker POSTing fake
        # notifications gets a clear reject. Other failures (malformed,
        # resource-not-accepted) are the sender's configuration problem,
        # so 400.
        if accepted or duplicates:
            return web.Response(status=202)
        if auth_rejected and not other_rejected:
            return web.Response(status=403)
        return web.Response(status=400)
```

三档:**收下或去重过 → 202**(空体,不泄漏内部计数),**整批 clientState 全错 → 403**
(让伪造方明确被拒),**其余 → 400**(发送方配置问题)。
「去重也算 202」这一条尤其关键:Graph 的重投必须被 ack,否则它会一直重投同一条。
这是 r7b 章 3.4 节 #38803 那条原则(失败分类是资源安全问题)在**入站**方向的镜像:
出站要分清"重试有没有意义",入站要告诉对端"你该不该重试"。

### 9.7 有界去重:集合查、双端队列淘汰

`gateway/platforms/msgraph_webhook.py:375` @ 863e313

```python
    def _has_seen_receipt(self, receipt_key: str) -> bool:
        return receipt_key in self._seen_receipts

    def _remember_receipt(self, receipt_key: str) -> None:
        self._seen_receipts.add(receipt_key)
        self._seen_receipt_order.append(receipt_key)
        while len(self._seen_receipt_order) > self._max_seen_receipts:
            oldest = self._seen_receipt_order.popleft()
            self._seen_receipts.discard(oldest)
```

`set` 负责 O(1) 判重,`deque` 负责 FIFO 淘汰,上限 `max_seen_receipts`(默认 5000)。
去重键只在通知自带 `id` 时才有:

`gateway/platforms/msgraph_webhook.py:100` @ 863e313

```python
    @staticmethod
    def _build_receipt_key(notification: Dict[str, Any]) -> Optional[str]:
        explicit_id = str(notification.get("id") or "").strip()
        if explicit_id:
            return f"id:{explicit_id}"
        return None
```

没有 id 的通知**不参与去重**但仍会被处理——宁可重复处理,不可漏。

### 9.8 ◇-B1-04:三处代码行为没有写进这个平台的文档

这个平台的文档质量在全仓里算高的(配置表、状态码表、排障表都齐),但有三处代码行为没进去:

**(a) `max_body_bytes` 与 413。** 文档的配置表列了 7 个 `extra.*` 设置,不含 `max_body_bytes`;
状态码表也没有 413。

`website/docs/user-guide/messaging/msgraph-webhook.md:116` @ 863e313

> Status code table:

```verify
cd /home/user/hermes-agent && grep -n "max_body_bytes\|413" website/docs/user-guide/messaging/msgraph-webhook.md | sort; echo "(以上为空即零命中)"
```

```text
(以上为空即零命中)
```

**搜索面**:只扫这一份文档,两个模式。零命中。
对比:**通用 webhook 的文档是写了的**(`website/docs/user-guide/messaging/webhooks.md` 第 386 行
有一行 `413 Payload Too Large` 的说明),所以这不是"项目不写这类字段",是这一份漏了。

**(b) POST 带 `validationToken` 也会被回显。**

`gateway/platforms/msgraph_webhook.py:239` @ 863e313

```python
        # Graph never sends validationToken on POST, but tolerate it for
        # defensive clients that replay the handshake in-band.
        validation_token = request.query.get("validationToken", "")
        if validation_token:
            return web.Response(text=validation_token, content_type="text/plain")
```

文档的状态码表只写了「GET with `validationToken` → 200」。实际 POST 带这个查询参数
同样回显,而且**在 `clientState` 校验之前**。它被来源 IP 白名单挡着,
且 `content_type="text/plain"` 限制了反射利用面,所以不是漏洞;但它是一条文档没有的入口。

**(c) `prompt` 模板。**

`gateway/platforms/msgraph_webhook.py:407` @ 863e313

```python
    def _render_prompt(self, notification: Dict[str, Any]) -> str:
        template = self.config.extra.get("prompt", "")
        if template:
            payload = {
                "notification": notification,
                "resource": notification.get("resource", ""),
                "change_type": notification.get("changeType", ""),
                "subscription_id": notification.get("subscriptionId", ""),
            }
            return self._render_template(template, payload)
        rendered = json.dumps(notification, indent=2, sort_keys=True)[:4000]
        return f"Microsoft Graph change notification:\n\n```json\n{rendered}\n```"
```

`extra.prompt` 支持 `{notification.xxx}` 这种点路径取值的自定义模板,
没配就回落到一段 JSON 代码块(截断到 4000 字)。文档的配置表里没有 `prompt` 这一项。

---

## 10. 簇十:relay 的命令清单 —— `gateway/relay/command_manifest.py`(145 行)

### 10.1 场景:令牌在谁手里,谁就得注册命令

r7b 章 3.6 节讲了 relay 把「接平台」整体外包:connector 前置真实平台,网关只跑一个
`RelayAdapter`。这里是那条路上的一个具体后果:**Discord 的斜杠命令必须先注册到 Discord**,
而注册要用 bot token。原生模式下 token 在网关手里,relay 模式下 token 在 connector 手里。

`gateway/relay/command_manifest.py:1` @ 863e313

```python
"""Gateway-declared slash-command manifest for the relay lane (Phase 4).

The native Discord adapter registers its slash commands directly on the
Discord command tree (`_register_slash_commands`,
plugins/platforms/discord/adapter.py) — it holds the bot token. Over the
relay the CONNECTOR holds the token, so the gateway DECLARES the same
command set on its `hello` frame (`command_manifest`) and the connector
reconciles Discord's global application-command registration against it
(gateway-gateway `DiscordCommandRegistrar`: GET → diff → bulk PUT,
idempotent, best-effort).
```

于是分工反过来:**网关「声明」它支持哪些命令,connector 去和 Discord 对账**
(GET 现有注册 → 比对 → 批量 PUT,幂等、尽力而为)。

### 10.2 声明搭在握手帧上,而且只对 Discord 发

`gateway/relay/ws_transport.py:472` @ 863e313

```python
            # Phase 4: declare the gateway's slash-command set on the Discord
            # hello. The connector (which holds the bot token) reconciles
            # Discord's global registration against it — idempotent, detached,
            # best-effort on its side; a connector predating the field ignores
            # it (additive). Only Discord has an app-command registry.
            if platform == "discord":
                try:
                    from gateway.relay.command_manifest import build_relay_command_manifest

                    hello["command_manifest"] = build_relay_command_manifest()
                except Exception:  # noqa: BLE001 - manifest is enrichment, never blocks the handshake
                    logger.debug("relay command manifest build failed", exc_info=True)
            await self._send(hello)
```

三个设计点:
- **只有 Discord 有应用命令注册表**,所以只在 `platform == "discord"` 的 hello 上带;
- 整段包在 `try/except` 里,注释写明 `manifest is enrichment, never blocks the handshake`
  ——**装饰性字段不得让握手失败**;
- 旧版 connector 收到不认识的字段直接忽略,即 r7b 章原则 16「未知字段丢弃」的正向用法。

### 10.3 声明一条命令**不需要写任何处理器**

交互从 passthrough 平面回来后被归一化成和文字命令**同形**的 `"/name args"` COMMAND 事件,
于是分发器现成的斜杠命令面就是处理器。线格式与失败模式也写清楚了:

`gateway/relay/command_manifest.py:22` @ 863e313

```python
Wire shape (per entry): {name, description, options?} where options rows are
Discord option objects passed through verbatim. Names must satisfy
Discord's CHAT_INPUT rules ([a-z0-9_-]{1,32}); the connector drops invalid
entries (fail-open per entry, never the whole manifest).
"""
```

`{name, description, options?}`,`options` 行是 Discord 的 option 对象**原样透传**;
名字必须满足 Discord 的 `CHAT_INPUT` 规则,
**非法条目由 connector 逐条丢弃,不会让整份清单失效**(逐条 fail-open)。
这是「跨进程契约」的一个好形状:**格式约束写在声明侧的注释里,执行在对面,
失败粒度是条目而不是整体**。

### 10.4 ▲-B1-03:自称「镜像原生命令树」,27 条里有 1 条描述文案不一致

`gateway/relay/command_manifest.py:12` @ 863e313

```python
This module is that declaration: the single source of truth for what the
relay lane advertises. It MIRRORS the native tree — same names, same
descriptions — so a user moving between a native-Discord deployment and a
hosted/relay one sees the same command palette. Interactions come back over
the passthrough plane and are normalized by
RelayAdapter._discord_interaction_to_event into the same "/name args"
COMMAND events the dispatcher already routes, so declaring a command here
requires NO new handler — the dispatcher's existing slash surface is the
handler.
```

`It MIRRORS the native tree — same names, same descriptions` ——**同名、同描述**
是这里明确许下的承诺,而且给了理由(用户在两种部署之间迁移时看到同一套命令面板)。

机械核对:把原生 Discord 适配器命令树上的 `@tree.command(name=..., description=...)` 全抽出来,
和 `build_relay_command_manifest()` 逐条比:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'PY'
import re, sys
sys.path.insert(0, ".")
from gateway.relay.command_manifest import build_relay_command_manifest
src = open("plugins/platforms/discord/adapter.py", encoding="utf-8").read()
nat = dict(re.findall(r'@tree\.command\(name="([^"]+)", description="([^"]*)"', src))
rel = {e["name"]: e["description"] for e in build_relay_command_manifest()}
print("native=%d relay=%d only_native=%s only_relay=%s" % (len(nat), len(rel), sorted(set(nat)-set(rel)), sorted(set(rel)-set(nat))))
for k in sorted(set(nat) & set(rel)):
    if nat[k] != rel[k]:
        print("DESC-DIFF %s" % k)
        print("  native: %s" % nat[k])
        print("  relay : %s" % rel[k])
PY
```

```text
native=27 relay=27 only_native=[] only_relay=[]
DESC-DIFF reload-skills
  native: Re-scan ~/.hermes/skills/ for new or removed skills
  relay : Re-scan skills for new or removed entries
```

两边**命令名完全一致**(27 对 27,两个方向的差集都空)——「same names」成立。
**「same descriptions」不成立**:`reload-skills` 一条不同。

`plugins/platforms/discord/adapter.py:5532` @ 863e313

```python
        @tree.command(name="reload-skills", description="Re-scan ~/.hermes/skills/ for new or removed skills")
        async def slash_reload_skills(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/reload-skills")
```

`gateway/relay/command_manifest.py:110` @ 863e313

```python
        {"name": "reload-mcp", "description": "Reload MCP servers from config"},
        {
            "name": "reload-skills",
            "description": "Re-scan skills for new or removed entries",
        },
```

原生写 `Re-scan ~/.hermes/skills/ for new or removed skills`,
relay 写 `Re-scan skills for new or removed entries`。用户在两种部署之间迁移时,
这一条的描述文案会变——正是那句承诺要防的事。

**判 ▲ 的理由与先例**:这是**代码内的模块 docstring** 与代码的矛盾,不是 `website/docs`。
R7B 的 ▲5 已经确立了这个先例(`gateway/platforms/whatsapp_cloud.py` 自己的模块 docstring 里
的失效路径引用被计为 ▲),本条沿用同一口径。

**严重性要如实说:低。** 只是一句 UI 描述文案,不影响命令能否被调用
(名字全对,而分发靠名字)。它的价值在于**证明这类"两处必须同步"的声明会漂**:
清单是手抄的镜像,没有任何测试把两边对起来。relay 那一簇本来有一份
`tests/gateway/relay/test_contract_doc_conformance.py` 做代码-文档一致性检查
(r7b 章第 5 节说 relay 的契约文档是全仓最准的,原因就在这份测试),
但它管的是 `docs/relay-connector-contract.md`,**没有覆盖"原生树 ↔ relay 清单"这一对**。
上面那条命令就是缺失的那个测试,15 行,可以直接搬进 `tests/`。

---

## 11. 定案汇总

| 号 | 记号 | 一句话 | 锚点(声明式) |
|---|---|---|---|
| ■-B1-01 | ■ | 共享 mime 表建成但四个生产调用点全部 `use_defaults=False`,运行时是死表 | `gateway/platforms/media_cache.py:123`:`ext = DEFAULT_MIME_TO_EXT.get(primary)` |
| ■-B1-02 | ■ | 同包两个同名分派函数签名与返回类型都不兼容,其中一个无生产调用方 | `gateway/platforms/media_cache.py:155`:`def cache_media_bytes(` |
| ■-B1-03 | ■ | 注释说开关叫 `QQ_API_HOST`,下一行读的是另一个名字,前者全仓不存在 | `gateway/platforms/qqbot/constants.py:19`:`PORTAL_HOST = os.getenv("QQ_PORTAL_HOST", "q.qq.com")` |
| ■-B1-04 | ■ | 文件过大异常有类、有 docstring 承诺、有 except、有测试,唯独无抛出点 | `gateway/platforms/qqbot/chunked_upload.py:92`:`class UploadFileTooLargeError(Exception):` |
| ■-B1-05 | ■ | `ApprovalSender` 无调用方、docstring 参数名与方法名都不存在、且丢 `allow_permanent` | `gateway/platforms/qqbot/keyboards.py:371`:`keyboard = build_approval_keyboard(req.session_key)` |
| ■-B1-06 | ■ | 两条解码失败日志被永为 False 的调试常量关死,坏帧完全静默丢弃 | `gateway/platforms/yuanbao_proto.py:31`:`DEBUG_MODE = False` |
| ■-B1-07 | ■ | 重定向 SSRF 守卫的判定式在 httpx 钩子里永不成立;仓库另有修好的共享版本 | `gateway/platforms/yuanbao_media.py:229`:`if response.is_redirect and response.next_request:` |
| ■-B1-08 | ■ | COS 签名窗口起点用签发时间、长度用剩余寿命,凭证一旦复用即签出即过期 | `gateway/platforms/yuanbao_media.py:521`:`sign_expire = (expired_time - now) if expired_time and expired_time > now else 3600` |
| ■-B1-09 | ■ | 贴纸按名查找返回 `Optional` 却对任何非空查询必然命中 | `gateway/platforms/yuanbao_sticker.py:496`:`if top <= 0:` |
| ▲-B1-01 | ▲ | 文档称 `QQ_PORTAL_HOST` 覆盖 portal 主机,二维码那条 URL 写死生产主机 | `gateway/platforms/qqbot/constants.py:29`:`"https://q.qq.com/qqbot/openclaw/connect.html"` |
| ▲-B1-02 | ▲ | 文档与设置向导都列了 `QQ_SANDBOX`,全仓无任何代码读取它 | `hermes_cli/config_defaults.py:4152`:`"QQ_SANDBOX": {` |
| ▲-B1-03 | ▲ | relay 清单自称与原生树「same descriptions」,27 条里 `reload-skills` 不同 | `gateway/relay/command_manifest.py:13`:`relay lane advertises. It MIRRORS the native tree — same names, same` |
| ◇-B1-01 | ◇ | 模块自带的 weixin mime 表合并 TODO 在基线仍未清 | `gateway/platforms/media_cache.py:33`:`but is intentionally NOT migrated here` |
| ◇-B1-02 | ◇ | 包门面 docstring 的「新模块」清单漏了分片上传与键盘两个模块 | `gateway/platforms/qqbot/__init__.py:38`:`from .chunked_upload import (  # noqa: F401` |
| ◇-B1-03 | ◇ | QQ 扫码配号零测试覆盖,而同形状的飞书流程有专门测试文件 | `gateway/platforms/qqbot/onboard.py:156`:`def qr_register(timeout_seconds: int = 600) -> Optional[dict]:` |
| ◇-B1-04 | ◇ | MSGraph webhook 文档漏了体积上限 / 413 / POST 回显 / 自定义模板四项 | `gateway/platforms/msgraph_webhook.py:43`:`DEFAULT_MAX_BODY_BYTES = 1_048_576` |
| ◎-B1-01 | ◎ | 分片上传 docstring 说「10 MB 到 100 MB 之间」,实际所有本地文件都走它 | `gateway/platforms/qqbot/chunked_upload.py:4`:`For files between 10 MB and ~100 MB we have to use the three-step chunked` |

**◎-B1-01 补一句口径**:那句「超过 ~10 MB 的内联上限就必须走三步」**字面为真**,
所以按 CLAUDE.md 的记号规则不能记 ▲。但适配器的分派是
「URL → 让平台自己抓;**本地文件 → 一律三步上传**」:

`gateway/platforms/qqbot/adapter.py:2902` @ 863e313

```python
        """Upload media and send as a native message.

        Upload strategy:

        - **HTTP(S) URLs** → single ``POST /v2/{users|groups}/{id}/files``
          with ``url=...``. The QQ platform fetches the URL directly; fastest
          path when the source is already hosted.
        - **Local files** → three-step chunked upload (prepare / PUT parts /
          complete). Handles files up to the platform's ~100 MB per-file
          limit without the ~10 MB inline-base64 cap of the old adapter.
        """
```

分派里没有 10 MB 这个门槛。读者据此会以为小文件走内联 base64,实际不走。

---

## 12. 与 `chapters/r7b-platform-integration.md` 的接口

这一片补的东西**和 r7b 章不冲突,是它的下一层**。逐条对照:

| r7b 章讲到 | 本片补的实例(声明式锚点) |
|---|---|
| 3.1 能力位「一条消息最长多少」 | `gateway/platforms/qqbot/constants.py:54`:`MAX_MESSAGE_LENGTH = 4000` |
| 3.4 #38803 失败分类是资源安全问题 | 入站侧镜像 `gateway/platforms/msgraph_webhook.py:310`:`if accepted or duplicates:` |
| 3.5 媒体外泄边界(出站) | 入站对侧 `gateway/platforms/yuanbao_media.py:261`:`async for chunk in resp.aiter_bytes(65536):` |
| 3.6 relay 把接平台整体外包 | 命令注册也跟着外包 `gateway/relay/command_manifest.py:48`:`def build_relay_command_manifest() -> List[Dict[str, Any]]:` |
| 3.6 Discord 3 秒 ACK 由 connector 边缘完成 | 无 relay 时自己 ACK `gateway/platforms/qqbot/keyboards.py:6`:`error indicator on the button.` |
| 原则 13 取值归一化(relay 描述符是反例) | 正例 `gateway/platforms/qqbot/chunked_upload.py:264`:`max_concurrent = min(prepare.concurrency, _MAX_CONCURRENT_PARTS)` |
| 原则 20 声明尺寸只用于提前拒绝 | 实例 `gateway/platforms/msgraph_webhook.py:256`:`if len(raw_body) > self._max_body_bytes:` |
| 原则 21 常量时间比较前先 encode | 实例 `gateway/platforms/msgraph_webhook.py:373`:`return hmac.compare_digest(provided.encode(), expected.encode())` |
| 第 5 节「没有测试守着的文档会腐烂」 | 推进一格:代码注释同样没测试守着(■-B1-03 / ■-B1-05 / ▲-B1-03 三条都是代码内自述) |

**r7b 章需要被明确交代的空缺**(建议主线在 R11B 成品章里点名):
r7b 章第 2 节的全景图把内建适配器画成「9 个」一个方框,`notes/r7b-50-builtin-adapters.md`
做了九个适配器的横向对照——但**没有下沉到这三个适配器各自的平台方言实现**
(QQ 的分片上传/按钮/扫码、元宝的手写 protobuf/COS、MSGraph 的 webhook 入口)。
本片的十个簇就是那一层。另外 §10 是 r7b 章 3.6 节的直接续写。

---

## 13. 测试作为行为规格

**环境**(按 CLAUDE.md 要求一并记):venv `/home/user/hermes-venv`,`pip list` 去表头
**87 个包**,`site-packages/*.dist-info` 计数同为 **87**;
本片全部执行基线代码的命令都带 `HERMES_DISABLE_LAZY_INSTALLS=1`,
开工时实测惰性安装判定函数返回 `False`,即惰性安装确实关闭。
本片**没有装任何包**,收工时包数仍为 87。基线 `git status --porcelain` 收工时为空。

跑了与本片 12 个文件直接相关的 7 个测试文件(命令末尾抽取汇总行,**不含耗时**,
以免机器速度差异让这条证据在重跑时假失败):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/gateway/test_media_cache.py tests/gateway/test_msgraph_webhook.py tests/gateway/test_qqbot.py tests/gateway/test_qqbot_credential_isolation.py tests/gateway/test_qqbot_scope_paths.py tests/gateway/test_yuanbao_forwarded_heartbeat.py tests/gateway/test_yuanbao_media_ssrf.py 2>&1 | grep -o "[0-9]* files, [0-9]* tests passed, [0-9]* failed"
```

```text
7 files, 129 tests passed, 0 failed
```

**129 passed / 0 failed / 0 skipped**(另有 1 个 xfail,在 `tests/gateway/test_qqbot_scope_paths.py`)。

**这批测试规格里最值得记的三点**:

1. `tests/gateway/test_media_cache.py`(37 例)把**每个适配器的历史输出硬编码成契约**——
   §1.1 摘录里说的「parity tests 把历史输出写死成契约」是真的。这是「重构不许改行为」
   这类工作的正确验收形态:不测新实现"对不对",测它和旧实现**逐一相同**。
2. `tests/gateway/test_yuanbao_media_ssrf.py` 只有 2 例,且只覆盖**预检**
   (直接给的内网 URL 被拦),**没有一例覆盖重定向那一跳**:

`tests/gateway/test_yuanbao_media_ssrf.py:14` @ 863e313

```python
class TestDownloadUrlSSRF:
    @pytest.mark.asyncio
    async def test_metadata_endpoint_blocked(self):
        with pytest.raises(ValueError, match="SSRF protection"):
            await download_url("http://169.254.169.254/latest/meta-data/")

    @pytest.mark.asyncio
    async def test_loopback_blocked(self):
        with pytest.raises(ValueError, match="SSRF protection"):
            await download_url("http://127.0.0.1:8080/secret")
```

   ——§7.3 那条 ■-B1-07 能活下来的直接原因。
3. `tests/gateway/test_qqbot.py`(61 例)覆盖了键盘构造、审批文案、`format_size`、
   异常消息格式,但如 §3.5 所述,**异常的触发条件没有任何一例覆盖**。

---

## 14. 需要但没装

无。本片全部证据只用到 venv 已有的 87 个包(§7.3 的 `MockTransport` 探针用的 `httpx`
已在其中)。未触发任何安装,未访问任何外部网络(探针用的是 httpx 的内存传输,不出网)。

---

## 15. 每个文件的断言索引(交付判据自查)

12 个文件,每个至少一条带行号锚点的可溯源断言。下表按行数降序,`断言数`只计
**本底稿正文中锚点后紧跟代码块**的那些(表格内联锚点、verify 块不计):

| 文件 | 行 | 本片断言数 | 所在簇 | 代表锚点(声明式) |
|---|---|---|---|---|
| `gateway/platforms/yuanbao_proto.py` | 1418 | 8 | §6 | `gateway/platforms/yuanbao_proto.py:304`:`if cmd_type != 0:` |
| `gateway/platforms/yuanbao_media.py` | 665 | 7 | §7 | `gateway/platforms/yuanbao_media.py:229`:`if response.is_redirect and response.next_request:` |
| `gateway/platforms/qqbot/chunked_upload.py` | 602 | 6 | §3 | `gateway/platforms/qqbot/chunked_upload.py:362`:`offset = (part_index - 1) * rsp_block_size` |
| `gateway/platforms/yuanbao_sticker.py` | 558 | 7 | §8 | `gateway/platforms/yuanbao_sticker.py:352`:`if query in key or key in query:` |
| `gateway/platforms/qqbot/keyboards.py` | 461 | 9 | §4 | `gateway/platforms/qqbot/keyboards.py:47`:`_APPROVAL_DATA_RE = re.compile(` |
| `gateway/platforms/msgraph_webhook.py` | 453 | 11 | §9 | `gateway/platforms/msgraph_webhook.py:150`:`host_is_public = self._host is None or is_network_accessible(self._host)` |
| `gateway/platforms/qqbot/onboard.py` | 220 | 6 | §5 | `gateway/platforms/qqbot/onboard.py:146`:`return QR_URL_TEMPLATE.format(task_id=quote(task_id))` |
| `gateway/platforms/media_cache.py` | 202 | 6 | §1 | `gateway/platforms/media_cache.py:122`:`if use_defaults:` |
| `gateway/relay/command_manifest.py` | 145 | 4 | §10 | `gateway/relay/command_manifest.py:24`:`Discord's CHAT_INPUT rules ([a-z0-9_-]{1,32}); the connector drops invalid` |
| `gateway/platforms/qqbot/__init__.py` | 91 | 4 | §2.1-2.2 | `gateway/platforms/qqbot/__init__.py:22`:`_coerce_list,` |
| `gateway/platforms/qqbot/constants.py` | 74 | 5 | §2.3-2.4 | `gateway/platforms/qqbot/constants.py:41`:`RECONNECT_BACKOFF = [2, 5, 10, 30, 60]` |
| `gateway/platforms/qqbot/utils.py` | 71 | 2 | §2.5 | `gateway/platforms/qqbot/utils.py:47`:`the server returns a JavaScript anti-bot challenge page.` |

**上表的断言数是数出来的,不是估的**(本仓库根跑;口径 = 本底稿里
「`路径:行号 @ 863e313` 单独成行」的锚点条数,而这些锚点按制度后面必跟一个代码块):

```verify
for p in gateway/platforms/yuanbao_proto.py gateway/platforms/yuanbao_media.py gateway/platforms/qqbot/chunked_upload.py gateway/platforms/yuanbao_sticker.py gateway/platforms/qqbot/keyboards.py gateway/platforms/msgraph_webhook.py gateway/platforms/qqbot/onboard.py gateway/platforms/media_cache.py gateway/relay/command_manifest.py gateway/platforms/qqbot/__init__.py gateway/platforms/qqbot/constants.py gateway/platforms/qqbot/utils.py; do n=$(grep -cE "^\`$(echo "$p" | sed 's/\./\\./g'):[0-9]+\` @ 863e313$" notes/r11b-raw-backlog-r7b.md); printf "%-45s %s\n" "$p" "$n"; done
```

```text
gateway/platforms/yuanbao_proto.py            8
gateway/platforms/yuanbao_media.py            7
gateway/platforms/qqbot/chunked_upload.py     6
gateway/platforms/yuanbao_sticker.py          7
gateway/platforms/qqbot/keyboards.py          9
gateway/platforms/msgraph_webhook.py          11
gateway/platforms/qqbot/onboard.py            6
gateway/platforms/media_cache.py              6
gateway/relay/command_manifest.py             4
gateway/platforms/qqbot/__init__.py           4
gateway/platforms/qqbot/constants.py          5
gateway/platforms/qqbot/utils.py              2
```

十二个文件全部 ≥2 条,交付判据(每个文件至少一条带行号锚点的可溯源断言)满足。

**派工书标 `Y`(连基名都没被提过)的那几个在本片的落点**:
`gateway/platforms/yuanbao_media.py` → §7(含 2 条 ■);
`gateway/platforms/yuanbao_sticker.py` → §8(含 1 条 ■);
`gateway/platforms/qqbot/keyboards.py` → §4(含 1 条 ■);
`gateway/platforms/qqbot/onboard.py` → §5(含 1 条 ▲ + 1 条 ◇);
`gateway/platforms/media_cache.py` → §1(含 2 条 ■);
`gateway/relay/command_manifest.py` → §10(含 1 条 ▲)。

---

## 移交

| 号 | 去向 | 锚点(声明式) | 一句话现象 |
|---|---|---|---|
| H-B1-a | R11B 主线 / 成品章 | `gateway/relay/command_manifest.py:13`:`relay lane advertises. It MIRRORS the native tree — same names, same` | ▲-B1-03 的机械核对命令(§10.4 的 verify 块)只有 15 行,建议作为一条新测试的雏形交出去:relay 那一簇已有代码-文档一致性测试,却没有任何东西管「原生树 ↔ relay 清单」这一对。 |
| H-B1-b | 下一轮(代码缺陷复核位) | `gateway/platforms/yuanbao_media.py:229`:`if response.is_redirect and response.next_request:` | ■-B1-07:全仓可能还有别的手写重定向守卫沿用 `next_request` 判定式。本片只核了共享助手的 4 个正确调用方与元宝这 1 个错误实现,**没有普查**「自己写 `is_redirect` 判定的地方」。搜索面建议:`--include=*.py` 搜 `is_redirect`,逐一判定是否经由共享助手。 |
| H-B1-c | 下一轮 | `hermes_cli/config_defaults.py:4152`:`"QQ_SANDBOX": {` | ▲-B1-02 越出本片 12 文件:那份环境变量目录会驱动设置向导提示用户填什么,而其中至少 `QQ_SANDBOX` 一项无任何读取方。**这份目录整体有多少条是死的,本片没查**,建议作为一次独立普查(口径:目录里每个键在非目录、非文档处是否被读)。 |
| H-B1-d | 下一轮 | `gateway/platforms/media_cache.py:33`:`but is intentionally NOT migrated here` | ◇-B1-01 是一条写在代码里的 follow-up,基线未清。**仓库里这类"写进注释的待办"有多少、多久没动**,是一个可量化的地图腐烂指标,本片没统计。 |
| H-B1-e | R11B 主线(台账) | `gateway/platforms/media_cache.py:1`:`"""Shared mime↔extension dispatch for inbound (downloaded) platform media.` | 本片 12 个文件在 `data/ledger.tsv` 里的 `status` 仍是 `R7B-deep-read`(§0 第一个 verify 块的输出即证据),应更新为可翻译成「R11B 已补可溯源断言」的状态(如 `R11B-backlog-read`),否则下一轮读台账仍然读不出这笔账已经还了。**改台账不在本片产出清单内,交主线。** |
