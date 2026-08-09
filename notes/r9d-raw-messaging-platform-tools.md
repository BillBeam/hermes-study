# r9d-raw-messaging-platform-tools · 消息外发与平台工具(第 D 片)

> **溯源约定**:凡对 hermes-agent 行为的断言,紧跟 `路径:行号 @ 863e313` 与代码原文块。
> 锚点一律**单独成行、置于块之前**。三反引号围栏 = 逐字源码摘录;`>` 引用块 = 文档摘录;
> ```` ```text / ```console / ```verify ```` = 作者声明的非源码(命令、输出、实验记录)。
> 基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`。
>
> **本片文件清单(6 文件 / 5052 行,全部读完)**:
>
> | 路径 | 行数 | 一句话定位 |
> |---|---|---|
> | `tools/send_message_tool.py` | 2116 | 跨平台统一发消息引擎(**不是**模型工具) |
> | `tools/discord_tool.py` | 1116 | Discord 服务器读/管工具(`discord` / `discord_admin`) |
> | `tools/homeassistant_tool.py` | 514 | 智能家居 REST 控制(`ha_*` 四件套) |
> | `tools/feishu_doc_tool.py` | 138 | 飞书文档正文读取(`feishu_doc_read`) |
> | `tools/feishu_drive_tool.py` | 431 | 飞书云盘评论读/写(`feishu_drive_*` 四件套) |
> | `tools/yuanbao_tools.py` | 737 | 腾讯元宝群成员/贴纸/私信(`yb_*` 五件套) |

**术语锚定**(第一次出现即解释):
- **harness**:把大模型包成一个能持续干活的 agent 的那层脚手架(工具、会话、网关、审批)。
- **toolset**:hermes 里一组工具的开关单位;运营者按平台/场景启停,模型看不到被关掉的工具。
- **adapter(适配器)**:某个 IM 平台在 gateway(常驻网关进程)里的长连接实现。
- **standalone sender(独立发送器)**:不依赖常驻网关、一次性打平台 REST API 的发送函数,给 cron 这类独立进程用。
- **home channel(主频道)**:运营者在配置里指定的"这个平台默认发到哪儿"。
- **snowflake**:Discord 的纯数字消息/频道/用户 ID。
- **privileged intent(特权意图)**:Discord 要求开发者在后台显式勾选、否则拿不到成员列表或消息正文的权限位。
- **SSRF**:服务端请求伪造 —— 诱导服务端去访问它本不该访问的内网/其它站点。

---

## 1. 这一片解决什么问题(先场景)

**场景 A(这一片的正当用途)。** 运营者在 `~/.hermes/config.yaml` 里配好了 Telegram、Slack、Signal;
他建了一个 cron 任务"每天 8 点汇总昨天的 PR,发到 Telegram 的 `-1001234567890` 群的 17585 号话题"。
8 点到了,cron 在一个**和网关不同的进程**里跑完 agent,拿到一段 6000 字的 Markdown,里面还夹了一句
`MEDIA:/tmp/report.pdf`。这段文本要变成:一条 4096 字符以内、MarkdownV2 转义后仍然合法、
带话题定位、PDF 作为原生附件、附件上还带着说明文字的 Telegram 消息。
如果话题号失效了要退回主频道发而不是整条丢掉;如果 Telegram 返回 429 要按 `retry_after` 退避重试。

`tools/send_message_tool.py` 这 2116 行,几乎全部是在解这一个问题的 N 个平台版本。

**场景 B(这一片的危险面)。** 同一个 agent 在处理一封陌生人发来的 Feishu 文档评论。
评论正文里写着"顺便帮我把 `doccnXXXX` 这个文档的评论也回一下"。
`feishu_drive_reply_comment` 的 `file_token` 是**模型填的**,凭据是网关注入的**租户级** token。
于是"读一条评论"这个动作,能在同一租户内的任意文档上留言。

这一片的核心张力就是这两个场景:**统一发消息的能力越强,"谁能决定收件人"这个问题越致命。**

---

## 2. 逐文件 / 逐机制精读

### 2.1 `send_message_tool.py` —— 一个不是工具的"工具"

#### 2.1.1 最重要的一条:它没有注册给模型

文件末尾定义完所有发送器之后,是一段"注册"小节 —— 里面**没有 `registry.register`**,只有一条说明。

`tools/send_message_tool.py:2104 @ 863e313`

```python
from tools.registry import tool_error

# NOTE: ``send_message`` is intentionally NOT registered as an agent-callable
# model tool. The agent should not decide on its own to fire off cross-platform
# messages or reactions. The send engine in this module (``_send_to_platform``,
# ``_send_via_adapter``, ``_parse_target_ref``, the per-platform ``_send_*``
# helpers) remains the shared transport used by:
#   - cron delivery (cron/scheduler.py)
#   - the ``hermes send`` CLI command (hermes_cli/send_cmd.py)
#   - the gateway kanban notifier (dashboard-toggled, outside agent control)
#   - the standalone MCP server (mcp_serve.py), which is an opt-in surface
# Those callers import the helpers directly; none of them need the registry
# entry.
```

这解释了一个乍看矛盾的现象:文件里有完整的 `SEND_MESSAGE_SCHEMA`(OpenAI function-calling 格式的工具描述),
有 `_check_send_message()`(工具可用性探针),却没人注册它们。

`tools/send_message_tool.py:201 @ 863e313`

```python
SEND_MESSAGE_SCHEMA = {
    "name": "send_message",
```

**负结论 + 搜索面(按 CLAUDE.md「负结论的成本」)。** "全仓没有任何地方把 `send_message` 注册成模型工具"这条,
我用的搜索面是:在基线仓库根对 `--include=*.py` 全仓 grep 三个符号
`SEND_MESSAGE_SCHEMA` / `send_message_tool` / `_check_send_message`(排除 `tests/`),
以及对字面量 `"send_message"` 的全仓 grep(排除 `tests/`)。

```verify
cd /home/user/hermes-agent && grep -rn 'SEND_MESSAGE_SCHEMA\|send_message_tool\|_check_send_message' --include=*.py . | grep -v '^./tests/'
cd /home/user/hermes-agent && grep -rn '"send_message"' --include=*.py . | grep -v '^./tests/'
```

第一条命令的全部命中都是"注释里提到"或"直接 import 内部 helper";第二条命中 6 处,
均为**消费方名单**而非注册点(`agent/display.py` 两处渲染格式化、`agent/tool_guardrails.py:55` 的
mutating 工具集合、`tools/delegate_tool.py:53` 的子代理黑名单、`acp_adapter/tools.py:73` 的 UI 精修名单、
以及本文件自己的 schema)。**这条负结论的可信度就等于这两条 grep 的完备性** —— 它不覆盖插件在运行时
动态注册的可能(见 §5「未取证」)。

**设计取舍(值得抄的):** 把"传输层"和"模型可调用面"彻底分开。同一份发送引擎服务四个调用方
(cron / CLI / kanban 通知器 / opt-in 的 MCP server),而"要不要让模型自己决定发消息"是一个
**独立的、可撤销的**决定 —— 撤销它只需要删掉一次 `registry.register`,不需要动 2000 行传输代码。
代价是:那 4 处残留名单(display / guardrails / delegate / acp)现在指向一个不存在的工具,
形成了"读代码的人以为模型有这个工具"的假象(见 §4 的 ◇-1)。

#### 2.1.2 目标解析:`_parse_target_ref` —— 每个平台一套 ID 形状

`tools/send_message_tool.py:530 @ 863e313`

```python
def _parse_target_ref(platform_name: str, target_ref: str):
    """Parse a tool target into chat_id/thread_id and whether it is explicit."""
    if platform_name == "telegram":
        match = _TELEGRAM_TOPIC_TARGET_RE.fullmatch(target_ref)
        if match:
```

target 的语法是 `platform[:target_ref]`,`target_ref` 再按平台各自的形状解析成
`(chat_id, thread_id, is_explicit)`。文件头部那 20 条正则就是这套形状库:

| 平台 | 锚点 + 摘录 | 形状 |
|---|---|---|
| Telegram | `tools/send_message_tool.py:20`:`_TELEGRAM_TOPIC_TARGET_RE = re.compile(r"^\s*(-?\d+)(?::(\d+))?\s*$")` | 数字群 ID,可选 `:话题号` |
| 飞书 | `tools/send_message_tool.py:21`:`_FEISHU_TARGET_RE = re.compile(r"^\s*((?:oc\|ou\|on\|chat\|open)_[-A-Za-z0-9]+)(?::([-A-Za-z0-9_]+))?\s*$")` | `oc_`/`ou_` 前缀 |
| Slack | `tools/send_message_tool.py:28`:`_SLACK_TARGET_RE = re.compile(r"^\s*([CGD][A-Z0-9]{8,})\s*$")` | C/G/D 会话 ID |
| 微信 | `tools/send_message_tool.py:34`:`_WEIXIN_TARGET_RE = re.compile(r"^\s*((?:wxid\|gh\|v\d+\|wm\|wb)_[A-Za-z0-9_-]+\|[A-Za-z0-9._-]+@chatroom\|filehelper)\s*$")` | wxid / 群 @chatroom |
| 元宝 | `tools/send_message_tool.py:35`:`_YUANBAO_TARGET_RE = re.compile(r"^\s*((?:group\|direct):[^:]+)\s*$")` | `group:` / `direct:` |
| 电话类 | `tools/send_message_tool.py:43`:`_PHONE_PLATFORMS = frozenset({"photon", "signal", "sms", "whatsapp"})` | E.164 `+8613…` |
| WhatsApp | `tools/send_message_tool.py:51`:`_WHATSAPP_JID_RE = re.compile(` | `@g.us` / `@s.whatsapp.net` / `@lid` |
| 邮件 | `tools/send_message_tool.py:58`:`_EMAIL_TARGET_RE = re.compile(r"^\s*[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\s*$")` | 邮件地址 |

**`is_explicit` 这个返回值是整个安全模型的关键。** 它的语义不是"格式合法",而是
**"这是一个平台原生 ID,直接拿去发,不要过通讯录"**。`_handle_send` 里:

`tools/send_message_tool.py:358 @ 863e313`

```python
def _handle_send(args):
    """Send a message to a platform target."""
    target = args.get("target", "")
    message = args.get("message", "")
    if not target or not message:
        return tool_error("Both 'target' and 'message' are required when action='send'")

    parts = target.split(":", 1)
    platform_name = parts[0].strip().lower()
    target_ref = parts[1].strip() if len(parts) > 1 else None
    chat_id = None
    thread_id = None

    if target_ref:
        chat_id, thread_id, is_explicit = _parse_target_ref(platform_name, target_ref)
```

只有 `is_explicit == False` 才会去查 `gateway.channel_directory.resolve_channel_name`。
也就是说:**通讯录不是白名单,只是"人话名字 → ID"的便利层。**
任何一个形状对的数字/JID/邮箱都能绕过它直达平台 API。这一点对第 (b) 问至关重要:
即使调用方被限制成"只能用通讯录里的名字",它照样可以直接给出裸 ID。

`gateway/channel_directory.py:533 @ 863e313`

```python
def resolve_channel_name(platform_name: str, name: str) -> Optional[str]:
    """
    Resolve a human-friendly channel name to a numeric ID.
```

#### 2.1.3 收件人到底谁说了算 —— 本片最重要的结论

分四层回答:

**(1) `send_message` 这个"工具"本身:模型碰不到。** 见 §2.1.1。
四个调用方里,cron 的 target 来自任务的 `deliver` 字段,CLI 的来自 `hermes send --to`,
kanban 通知器来自 dashboard 配置,MCP server 来自外部 MCP 客户端。

**(2) 但 cron 的 `deliver` 是模型可写的 —— 于是禁令被绕过一跳。**
`cronjob` 是**注册了的**模型工具,它的 `deliver` 参数在 schema 里就是自由字符串,
描述里直接给了 `platform:chat_id:thread_id` 的样例。

`tools/cronjob_tools.py:1073 @ 863e313`

```python
            "deliver": {
                "type": "string",
```

而 cron 解析这个字符串用的正是本片的 `_parse_target_ref`:

`cron/scheduler.py:1173 @ 863e313`

```python
    if ":" in deliver_value:
        platform_name, rest = deliver_value.split(":", 1)
        platform_key = platform_name.lower()

        from tools.send_message_tool import _parse_target_ref

        parsed_chat_id, parsed_thread_id, is_explicit = _parse_target_ref(platform_key, rest)
        if is_explicit:
            chat_id, thread_id = parsed_chat_id, parsed_thread_id
        else:
```

带冒号的分支**无条件返回**这个目标,没有任何白名单、没有 `_is_known_delivery_platform` 检查
(那个检查只在"裸平台名"分支里):

`cron/scheduler.py:1210 @ 863e313`

```python
        return {
            "platform": platform_name,
            "chat_id": chat_id,
            "thread_id": thread_id,
        }
```

投递时又回到本片:

`cron/scheduler.py:1500 @ 863e313`

```python
    from tools.send_message_tool import _send_to_platform
```

**结论(静态对读,未端到端实跑):** 模型不能直接 `send_message`,但可以
`cronjob(action='create', schedule=…, deliver='telegram:-100…:17', prompt='…')`,
让同一套引擎在下一个 tick 把它想发的内容发到它自己挑的目标。
`send_message` 那条 NOTE 声称的"The agent should not decide on its own to fire off cross-platform messages"
在**跨越一次 cron 创建之后不成立**。这条是本片最强的发现之一,记为 ■-1。

**(3) 模型可直接调用的外发工具,收件人全部由模型决定。** 这一片里注册了的工具:

| 工具 | 收件人来源 | 锚点 + 摘录 |
|---|---|---|
| `yb_send_dm` | 模型给 `group_code`+`name`(或直接 `user_id`) | `tools/yuanbao_tools.py:290`:`async def send_dm(` |
| `yb_send_sticker` | 模型给 `chat_id`,缺省才回落当前会话 | `tools/yuanbao_tools.py:205`:`async def send_sticker(` |
| `feishu_drive_reply_comment` | 模型给 `file_token`+`comment_id` | `tools/feishu_drive_tool.py:281`:`def _handle_reply_comment(args: dict, **kwargs) -> str:` |
| `feishu_drive_add_comment` | 模型给 `file_token` | `tools/feishu_drive_tool.py:351`:`def _handle_add_comment(args: dict, **kwargs) -> str:` |
| `discord` / `discord_admin` | 模型给 `guild_id`/`channel_id`/`user_id`/`role_id` | `tools/discord_tool.py:986`:`def _run_discord_action(` |
| `ha_call_service` | 模型给 `entity_id` | `tools/homeassistant_tool.py:252`:`def _handle_call_service(args: dict, **kw) -> str:` |

也就是说:**唯一"收件人由运营者配置"的工具,恰恰是被拿掉的那个。**
剩下这些能改世界的工具(私信任何群友、在任何文档留言、删任何消息、开关任何设备),
收件人全部是模型自由填的字符串。

**(4) 唯一的运营者闸门是 toolset 开关,不是逐次审批。** `registry.register` 的签名里
**没有任何审批参数**:

`tools/registry.py:521 @ 863e313`

```python
    def register(
        self,
        name: str,
        toolset: str,
        schema: dict,
        handler: Callable,
        check_fn: Callable = None,
        requires_env: list = None,
        is_async: bool = False,
        description: str = "",
        emoji: str = "",
        max_result_size_chars: int | float | None = None,
        dynamic_schema_overrides: Callable = None,
        override: bool = False,
    ):
```

#### 2.1.4 失败回落:三层降级 + 每平台特判

`_send_via_adapter` 是通用回落路径,文档串把三级顺序写得很清楚:

`tools/send_message_tool.py:688 @ 863e313`

```python
async def _send_via_adapter(
    platform,
    pconfig,
    chat_id,
    chunk,
    *,
    thread_id=None,
    media_files=None,
    force_document=False,
):
    """Send a message via a live gateway adapter, with a standalone fallback
    for out-of-process callers (e.g. cron running separately from the gateway).
```

三级是:① 本进程里活着的 gateway adapter(`_gateway_runner_ref()` 弱引用);
② 插件在 `PlatformEntry.standalone_sender_fn` 上注册的一次性 REST 发送器;
③ 一条把两条路都说清楚的错误。

**为什么需要 ②(值得抄的设计):** cron 常常跑在**独立进程**里,`_gateway_runner_ref()` 返回 `None`。
如果没有 ②,所有插件平台的 cron 投递都会失败在 `No live adapter for platform '<name>'`。
这是"同一个能力必须同时支持进程内长连接和进程外一次性调用"这个约束的通用解法:
**把一次性发送器挂到注册表上,而不是散落在调用方 if-else 里。**

但 `_send_to_platform` 里仍然保留了一大串按平台的特判分支,理由各不相同,都值得记:

- **Telegram**:整条消息一次性交给 `_send_telegram`,**不预先分块** —— 因为 MarkdownV2 转义会
  把 `!` `.` `-` 变成 `\!` `\.` `\-`,原本 <4096 的文本格式化后会超限;所以要在**格式化之后**按
  UTF-16 单位分块。
- **Matrix**:强制走原生 adapter,因为走裸 HTTP 的话 E2EE 房间里的纯文本消息会带红色挂锁
  (未加密),而且每条消息重建 olm/megolm 会话会耗尽对端一次性密钥。
- **Discord / Slack / WhatsApp / 飞书**:带附件时走插件的 `standalone_sender_fn`,以拿到
  各自的原生上传通道(files_upload_v2 / Baileys /send-media / lark 上传)。
- **Weixin**:分支放在**最前面**,注释说明是为了不被无关的可选依赖(lark-oapi 那条重导入路径)拖累。

#### 2.1.5 长度、分块与截断(问题 e 的一半)

长度上限的来源有两层:内置平台从 adapter 类属性拿,插件平台从注册表条目上拿 —— 而它的默认值是"无限制":

`gateway/platform_registry.py:93 @ 863e313`

```python
    # Max message length for smart-chunking.  0 = no limit.
    max_message_length: int = 0
```

实测各插件声明值:

```verify
cd /home/user/hermes-agent && grep -rn "max_message_length=" plugins/platforms/*/adapter.py
```

```text
discord      2000
email        50000
feishu       8000
google_chat  4000
irc          450
slack        39000
teams        28000
telegram     4096
wecom        4000
whatsapp     4096
```

分块函数是共享的 `BasePlatformAdapter.truncate_message`,会保护代码围栏边界并加 `(1/3)` 序号:

`gateway/platforms/base.py:6693 @ 863e313`

```python
    def truncate_message(
        content: str,
        max_length: int = 4096,
        len_fn: Optional["Callable[[str], int]"] = None,
    ) -> List[str]:
```

`len_fn` 这个参数是给 Telegram 用的:Telegram 按 **UTF-16 码元**计长,而 Python `len()` 按码点,
一个 emoji 在 Telegram 眼里是 2、在 Python 眼里是 1。

**■-2(实测静态对读):QQBot 走的是硬截断而不是分块。** `Platform.QQBOT` 既不在
`_MAX_LENGTHS` 初始表里,也没有 `plugins/platforms/qqbot/` 插件,于是
`platform_registry.get("qqbot")` 拿不到长度 → `chunks = [message]`(整条不分块)→
`_send_qqbot` 直接切前 4000 字符,并且**照常返回 `success: True`**:

`tools/send_message_tool.py:2042 @ 863e313`

```python
            payload = {"content": message[:4000], "msg_type": 0}
```

搜索面:`ls plugins/platforms/` 全列(22 个目录,无 qqbot);
`grep -rn "max_message_length=" plugins/platforms/*/adapter.py gateway/platform_registry.py` 无 qqbot 命中。

```verify
cd /home/user/hermes-agent && ls plugins/platforms/ | grep -c qqbot ; grep -rn "qqbot" gateway/platform_registry.py plugins/ --include=*.py | wc -l
```

两条都输出 `0`。**后果**:超过 4000 字的 cron 汇总发到 QQ 频道会被静默砍半截,
调用方拿到 `success: True`,没有 warning。对比同文件里 Signal 失败会往 `warnings` 里塞条目、
Telegram 找不到媒体文件也会塞 warning —— 这个截断是**这套代码里唯一一处无声的内容丢失**。

#### 2.1.6 附件与 caption:一个被反复咬过的产品细节

`_media_caption_split` 是"要不要把文字挂到媒体气泡上"的**唯一决策点**。它的 docstring
写出了这个函数存在的原因(一个真实报障):

`tools/send_message_tool.py:89 @ 863e313`

```python
def _media_caption_split(text, media_files, *, max_caption_len):
    """Decide whether the accompanying text should ride on the media bubble.

    Single enforced chokepoint for the ``MEDIA:<path> caption`` behavior
    across every standalone sender. ``hermes send`` (and the send_message
    tool / cron) strips the ``MEDIA:`` tag and leaves the remaining prose as
    ``text``; historically each platform sent that ``text`` as a *separate*
    message before an uncaptioned media bubble, splitting the reported case
    ``hermes send --to whatsapp "MEDIA:/x.png This Caption"`` into two parts.
```

**事故讲成因果经过:** 用户敲 `hermes send --to whatsapp "MEDIA:/x.png This Caption"`,
期待收到一张带文字说明的图;实际收到两条 —— 先一条纯文字 "This Caption",再一条无说明的图。
根因是 `MEDIA:` 标签被剥离后,剩下的文字走的是"正文"通路,媒体走的是"附件"通路,两条通路互不知情。
修法不是在 WhatsApp 分支里打补丁,而是把"合并还是分开"抽成一个所有发送器共用的纯函数,
返回 `(caption, body_text)`:合并时 `body_text` 为空串,分开时 `caption` 为 `None`。

它拒绝合并的四种情形都有理由:多文件(说明该配哪张图有歧义)、语音/音频条
(说明文字在语音条上会显示成一个独立标签而不是气泡说明)、空文字、超长。

Telegram 侧还要**二次检查**:因为 caption 也要被 MarkdownV2 转义,转义会膨胀长度。

`tools/send_message_tool.py:85 @ 863e313`

```python
_TELEGRAM_CAPTION_LIMIT = 1024
_DEFAULT_CAPTION_LIMIT = 4096
```

还有一个很细的兜底:如果决定了走 caption 模式(于是**不发独立正文**),结果那个媒体文件在磁盘上没了,
代码会把 caption 文字单独补发一条,以免"话被静默吞掉":

`tools/send_message_tool.py:1344 @ 863e313`

```python
        for media_path, is_voice in media_files:
            if not os.path.exists(media_path):
                warning = f"Media file not found, skipping: {media_path}"
                logger.warning(warning)
                warnings.append(warning)
                # Caption mode suppressed the separate text send; if the file
```

#### 2.1.7 速率限制与重试(问题 e 的另一半)

三种截然不同的策略并存在同一个文件里,这个对比本身很有教学价值:

**Telegram —— 指数退避 + 服务器指定优先。**

`tools/send_message_tool.py:158 @ 863e313`

```python
def _telegram_retry_delay(exc: Exception, attempt: int) -> float | None:
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        try:
            return max(float(retry_after), 0.0)
        except (TypeError, ValueError):
            return 1.0
```

注意:**超时不重试**:

`tools/send_message_tool.py:166 @ 863e313`

```python
    text = str(exc).lower()
    if "timed out" in text or "timeout" in text:
        return None
```

只有 502/503/504/429 才退避
`2 ** attempt` 秒,最多 3 次。为什么超时不重试?因为一个超时的发送**可能已经送达**,
重试会造成重复消息;而 502/429 是明确的"没收到"。这是一个正确的取舍,但代码里没写这个理由。

**Signal —— 进程级令牌桶调度器 + 用户可见的排队提示。**
Signal 对附件的限流极凶,所以这里做得最重:附件按 32 个一批分组,每批过一次
`SignalAttachmentScheduler.acquire(n)`,失败后把服务器给的 `retry_after` 喂回调度器,
**并且**当预估等待超过 10 秒时,会先给用户发一条"图还在传,等约 X 秒"的说明消息。

`gateway/platforms/signal_rate_limit.py:33 @ 863e313`

```python
SIGNAL_MAX_ATTACHMENTS_PER_MSG = 32  # per-message attachment cap (source: Signal-{Android,Desktop} source code)
```

`gateway/platforms/signal_rate_limit.py:36 @ 863e313`

```python
SIGNAL_RATE_LIMIT_MAX_ATTEMPTS = 2  # initial attempt + 1 retry
SIGNAL_BATCH_PACING_NOTICE_THRESHOLD = 10.0  # if estimated waiting time > 10s, notify the user about the delay
```

最值得抄的一点:**调度器是进程级共享的**,所以这个工具发的图和网关收到消息后自动回复的图
**共用同一个桶**。否则两条路各自以为自己没超限,合起来必然被封。

**Discord 工具侧 —— 完全没有限流处理。** 见 §2.2.4。

#### 2.1.8 凭据与出网(问题 c)

本片 6 个文件的 HTTP 客户端分布(实测):

```verify
cd /home/user/hermes-agent && grep -n "follow_redirects\|allow_redirects\|urlopen\|httpx\.\|aiohttp\.\|urllib\." tools/send_message_tool.py tools/discord_tool.py tools/homeassistant_tool.py tools/feishu_doc_tool.py tools/feishu_drive_tool.py tools/yuanbao_tools.py
```

```text
send_message_tool.py : aiohttp(Slack DM 解析) + httpx(Signal / QQBot)
discord_tool.py      : urllib.request(全部)
homeassistant_tool.py: aiohttp(全部四个动作)
feishu_doc_tool.py   : 无(走 lark_oapi SDK 的 client.request)
feishu_drive_tool.py : 无(同上)
yuanbao_tools.py     : 无(走 gateway 里的 WebSocket adapter 单例)
六个文件里 follow_redirects / allow_redirects 的命中数:0
```

**没有任何一处显式设置重定向策略**,所以全部吃默认值:

- `httpx.AsyncClient` 默认 `follow_redirects=False` → **不跟随**,最安全。
- `aiohttp.ClientSession` 默认 `allow_redirects=True` → 跟随;但 aiohttp 3.14.1 在
  **跨 origin 时会剥掉 `Authorization`**(见下)。
- `urllib.request.urlopen` 默认跟随;而 stdlib 的 `HTTPRedirectHandler.redirect_request`
  **只剥 `content-length` / `content-type`,不剥 `Authorization`**。

我把这两条都**实跑复现**了(纯本地 socket,不联外网):

```verify
# 实验 1:aiohttp 3.14.1 的跨 origin 剥 Authorization 逻辑(读源码,非猜测)
/home/user/hermes-venv/bin/python -c "
import aiohttp, inspect
print('aiohttp', aiohttp.__version__)
src = inspect.getsource(aiohttp.client.ClientSession._request)
for i,l in enumerate(src.split(chr(10))):
    if 'AUTHORIZATION' in l.upper(): print(i, l.strip())"
```

```text
aiohttp 3.14.1
...
435  if url.origin() != redirect_origin:
438      headers.pop(hdrs.AUTHORIZATION, None)
440      headers.pop(hdrs.PROXY_AUTHORIZATION, None)
```

```verify
# 实验 2:urllib 会不会把 Authorization 带过跨 origin 重定向
# (起两个本地 socket:A 返回 302 指向 B;看 B 收到什么头)
/home/user/hermes-venv/bin/python - <<'PY'
import socket, threading, urllib.request
seen = {}
def server(name, sock, respond):
    while True:
        conn, _ = sock.accept()
        seen.setdefault(name, []).append(conn.recv(65535).decode("latin1"))
        conn.sendall(respond); conn.close()
a = socket.socket(); a.bind(("127.0.0.1", 0)); a.listen(5); pa = a.getsockname()[1]
b = socket.socket(); b.bind(("127.0.0.1", 0)); b.listen(5); pb = b.getsockname()[1]
redirect = f"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:{pb}/stolen\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode()
ok = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"
threading.Thread(target=server, args=("A", a, redirect), daemon=True).start()
threading.Thread(target=server, args=("B", b, ok), daemon=True).start()
req = urllib.request.Request(f"http://127.0.0.1:{pa}/api/v10/users/@me/guilds",
      headers={"Authorization": "Bot SUPERSECRET"})
urllib.request.urlopen(req, timeout=5).read()
import time; time.sleep(0.3)
for name in ("A", "B"):
    for raw in seen.get(name, []):
        auth = [l for l in raw.split("\r\n") if l.lower().startswith("authorization")]
        print(f"[{name}] {raw.splitlines()[0]}  ->  {auth}")
PY
```

```text
[A] GET /api/v10/users/@me/guilds HTTP/1.1  ->  ['Authorization: Bot SUPERSECRET']
[B] GET /stolen HTTP/1.1  ->  ['Authorization: Bot SUPERSECRET']
```

**结论(见 §4 ■-3):** `tools/discord_tool.py` 是本片唯一一个"凭据跟着重定向走"的形态。
它的缓解因素是 base URL 是常量(见 §2.2.1),所以要利用它需要 discord.com 自己发出跨站 302;
但这是**唯一一个没有任何 origin 检查**的客户端,而同仓库里明明有现成的
下面这个 SSRF 安全客户端 —— 而它在别处是被用着的。

`tools/url_safety.py:841 @ 863e313`

```python
def create_ssrf_safe_client(**kwargs: Any) -> Any:
    """Create an ``httpx.Client`` with connect-time SSRF validation."""
```

`tools/skills_hub.py:298 @ 863e313`

```python
    with create_ssrf_safe_client(timeout=timeout, follow_redirects=False) as client:
        return client.get(url)
```

#### 2.1.9 错误文本的脱敏(容易被忽略但很关键)

所有返回给模型/用户的错误都过一遍 `_sanitize_error_text`:

`tools/send_message_tool.py:138 @ 863e313`

```python
def _sanitize_error_text(text) -> str:
    """Redact secrets from error text before surfacing it to users/models."""
    redacted = redact_sensitive_text(text)
    redacted = _URL_SECRET_QUERY_RE.sub(lambda m: f"{m.group(1)}***", redacted)
    redacted = _GENERIC_SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}=***", redacted)
    return redacted
```

**为什么必须有:** 平台 SDK 抛的异常经常把完整请求 URL(含 `?access_token=…`)塞进 `str(exc)`。
如果原样返回,这个 token 就进了模型上下文 → 进了会话历史 → 可能被后续消息带出去。
这是一个"错误路径也是数据出口"的典型例子。

还有一个更细的:Signal 群 ID 在结果里会被打码,因为群 ID 本身就是敏感的:

`tools/send_message_tool.py:151 @ 863e313`

```python
def _display_chat_id(platform_name: str, chat_id: str) -> str:
    """Return a result-safe chat identifier for tool transcripts/log consumers."""
    if platform_name == "signal" and str(chat_id).startswith("group:"):
        return "group:***"
    return chat_id
```

#### 2.1.10 一个漂亮的小机制:cron 重复投递抑制

cron 会把 agent 的最终回复**自动投递**到目标。如果 agent 在跑的过程中又自己调了一次发消息
发到同一个目标,用户就会收到两条。于是:

`tools/send_message_tool.py:657 @ 863e313`

```python
def _maybe_skip_cron_duplicate_send(platform_name: str, chat_id: str, thread_id: str | None):
    """Skip redundant cron send_message calls when the scheduler will auto-deliver there."""
```

它比较 `HERMES_CRON_AUTO_DELIVER_{PLATFORM,CHAT_ID,THREAD_ID}` 三个会话环境变量,
命中就返回一个 `success: True, skipped: True` 的结果,并在 `note` 里**教调用方怎么做对**
("把要给用户看的内容放进最终回复")。这个"拒绝执行 + 解释正确做法"的返回形态,
比单纯报错对 LLM 调用方友好得多,值得抄。

---

### 2.2 `discord_tool.py` —— 双工具切分 + 动态 schema

#### 2.2.1 请求层

`tools/discord_tool.py:44 @ 863e313`

```python
DISCORD_API_BASE = "https://discord.com/api/v10"
_DISCORD_RESPONSE_BODY_MAX_BYTES = 4 * 1024 * 1024
_DISCORD_ERROR_BODY_MAX_BYTES = 64 * 1024
```

响应体有 4MB 上限、错误体 64KB 上限 —— 这是防"一个 fetch_messages 把模型上下文撑爆"的
**读取侧**限流,做得很到位(`_read_limited_response_body` 读 `limit+1` 字节再判断,
避免了先读完再检查的内存放大)。

`tools/discord_tool.py:79 @ 863e313`

```python
def _discord_request(
    method: str,
    path: str,
    token: str,
    params: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 15,
) -> Any:
    """Make a request to the Discord REST API."""
    url = f"{DISCORD_API_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "Hermes-Agent (https://github.com/NousResearch/hermes-agent)",
        },
    )
```

**注意 `path` 是 f-string 拼出来的**,里面的 `channel_id` / `message_id` / `guild_id` 等
**全部是模型直接给的、未经任何格式校验的字符串**。校验只查"有没有给":

`tools/discord_tool.py:1034 @ 863e313`

```python
    missing = [p for p in _REQUIRED_PARAMS.get(action, []) if not local_vars.get(p)]
    if missing:
        return tool_error(
            f"Missing required parameters for '{action}': {', '.join(missing)}"
        )
```

这和同一片里的 Home Assistant 工具形成了**刺眼的对照** —— HA 为了完全相同的形状
(把参数插进 `/api/services/{domain}/{service}`)专门加了正则并写了理由(见 §2.3.2)。
Discord 这边一模一样的形状,零校验。

我实跑确认了 **urllib 客户端不会归一化 `..`,而是原样发到线上**:

```verify
/home/user/hermes-venv/bin/python - <<'PY'
import socket, threading, urllib.request
cap=[]
def serve(s):
    c,_=s.accept(); cap.append(c.recv(65535).decode("latin1").split("\r\n")[0])
    c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"); c.close()
s=socket.socket(); s.bind(("127.0.0.1",0)); s.listen(1); p=s.getsockname()[1]
threading.Thread(target=serve,args=(s,),daemon=True).start()
channel_id = "../../guilds/999/bans"
req=urllib.request.Request(f"http://127.0.0.1:{p}/api/v10/channels/{channel_id}/messages",
    headers={"Authorization":"Bot SECRET"})
urllib.request.urlopen(req,timeout=5).read()
print("REQUEST-LINE:", cap[0])
PY
```

```text
REQUEST-LINE: GET /api/v10/channels/../../guilds/999/bans/messages HTTP/1.1
```

**能走到哪一步取决于 Discord 边缘是否归一化点段,这一半我没有取证**(没有也不会配置真实 token)。
写进 §5「未取证 / 推定」。但**客户端侧不设防**这一半是实跑确认的。

#### 2.2.2 双工具切分:core / admin

`tools/discord_tool.py:632 @ 863e313`

```python
_ACTIONS = {
    "list_guilds": _list_guilds,
    "server_info": _server_info,
    "list_channels": _list_channels,
    "channel_info": _channel_info,
    "list_roles": _list_roles,
    "member_info": _member_info,
    "search_members": _search_members,
    "fetch_messages": _fetch_messages,
    "list_pins": _list_pins,
    "pin_message": _pin_message,
    "unpin_message": _unpin_message,
    "delete_message": _delete_message,
    "create_thread": _create_thread,
    "add_role": _add_role,
    "remove_role": _remove_role,
}

_CORE_ACTION_NAMES = frozenset({"fetch_messages", "search_members", "create_thread"})
_ADMIN_ACTION_NAMES = frozenset(_ACTIONS.keys()) - _CORE_ACTION_NAMES
```

**15 个动作,一个都不是"发消息"。** 发消息始终归 gateway adapter / send 引擎管,
这个工具只做"读服务器 + 管理"。这是一条清晰的职责边界。

切分成两个工具(而不是一个工具 + 参数开关)的好处是:**toolset 是运营者的开关粒度**,
于是"允许 agent 读频道"和"允许 agent 删消息/发角色"可以分别开关。
两者都在默认关闭名单里:

`hermes_cli/tools_config.py:156 @ 863e313`

```python
_DEFAULT_OFF_TOOLSETS = {"homeassistant", "spotify", "discord", "discord_admin", "video", "video_gen", "x_search", "a2a"}
```

#### 2.2.3 动态 schema:两道过滤 + 一个冷启动性能坑

模块 docstring 把设计意图写得很完整:

`tools/discord_tool.py:10 @ 863e313`

```python
The schema exposed to the model is filtered by two gates:

1. Privileged intents detected from GET /applications/@me at schema
   build time. Actions that require an intent the bot doesn't have
   (search_members / member_info → GUILD_MEMBERS intent) are hidden.
   fetch_messages is kept regardless of MESSAGE_CONTENT intent, but
   its description is annotated when the intent is missing.

2. User config allowlist at ``discord.server_actions``. If the user
   sets a comma-separated list (or YAML list) of action names, only
   those appear in the schema. Empty/unset means all intent-available
   actions are exposed.
```

**冷启动坑与它的修法,是本片最好的一段工程故事。**

`tools/discord_tool.py:231 @ 863e313`

```python
def _detect_capabilities_nonblocking(token: str) -> Dict[str, Any]:
    """Non-blocking capability lookup for schema builds.

    Resolution order:
      1. In-process memory cache (populated by a previous sync/bg detection).
      2. Fresh disk cache (populated by a previous process).
      3. Permissive default + fire-and-forget background detection that
         populates both caches for the next schema build / process.

    Rationale: ``_detect_capabilities`` makes a blocking HTTPS call to
    discord.com (measured ~2s, up to 5s on the timeout) and used to run
    inside ``get_tool_definitions`` → ``AIAgent.__init__`` — i.e. on the
    critical path of the FIRST TOKEN of every cold process for any user
    with DISCORD_BOT_TOKEN set, on every platform.  The permissive default
    mirrors the existing detection-failure fallback: all actions exposed,
    call-time 403s mapped to guidance by ``_enrich_403``.
    """
```

**因果经过:** 只要用户设了 `DISCORD_BOT_TOKEN`,每个冷启动进程在构建工具定义时就会同步打一次
discord.com,首 token 延迟凭空多 2~5 秒 —— 而且是在**所有平台**上,即使这次会话跟 Discord 无关。
修法有三层巧思:

1. **三级缓存**:内存 → 磁盘(24h TTL)→ 宽松默认值 + 后台探测。
2. **宽松默认**(全部动作可见)而不是保守默认:因为探测失败时本来就走这条路,
   而运行时 403 有 `_enrich_403` 翻译成人话("机器人缺 MANAGE_ROLES 权限,或目标角色排位高于机器人")。
   **保守默认会让功能悄悄消失,宽松默认只会让一次调用失败并附带修复指引** —— 后者可诊断得多。
3. **本进程内把默认值钉死**,后台探测的结果只写磁盘、**不改本进程的内存缓存**。理由写在注释里:

`tools/discord_tool.py:257 @ 863e313`

```python
    # Cold start — pin the permissive default for THIS process (schema
    # stability: tool schemas must not change between agent inits within a
    # live process, or the per-conversation prompt cache breaks) and detect
    # in the background for the NEXT process via the disk cache.
```

**prompt cache(提示缓存)**是把请求前缀哈希后复用 KV 的省钱机制;工具定义在前缀里,
schema 变了整个缓存就失效。这一条把"性能优化"和"计费正确性"的关系讲透了,非常值得抄。

磁盘缓存的 key 是 token 的 SHA-256 前 16 位,不是 token 本身:

`tools/discord_tool.py:181 @ 863e313`

```python
def _token_cache_key(token: str) -> str:
    """Stable non-reversible cache key for a bot token."""
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
```

写盘用临时文件 + `tmp.replace(path)` 做原子替换,避免并发进程读到半截 JSON。

#### 2.2.4 限流:没有

`tools/discord_tool.py` 里对 429 / `Retry-After` **一处处理都没有**。搜索面:
在该文件内 grep `429`、`Retry-After`、`rate` 三个模式,命中三处全部无关
(注释里的 "comma-separated list"、以及 `_channel_info` 回显的 `rate_limit_per_user` 字段)。

```verify
cd /home/user/hermes-agent && grep -n "429\|Retry-After\|rate" tools/discord_tool.py
```

后果:429 会变成 `DiscordAPIError(429, body)`,再变成一条 `tool_error` 交给模型,
模型很可能立刻重试 → 更严重的限流。403 反倒被翻译得很细致:

`tools/discord_tool.py:964 @ 863e313`

```python
def _enrich_403(action: str, body: str) -> str:
    """Return a user-friendly guidance string for a 403 on ``action``."""
    hint = _ACTION_403_HINT.get(action)
    base = f"Discord API 403 (forbidden) on '{action}'."
```

429 却什么都没有。对比同片 Signal 那套调度器,这是明显的不对称。
考虑到 `discord` 的 `fetch_messages` 是模型会连续调用的读接口,这个缺口是真实的(■-4)。

---

### 2.3 `homeassistant_tool.py` —— 能开关物理设备的工具,闸门在哪一层(问题 d)

#### 2.3.1 结论先行:**没有逐次审批,只有两道静态闸门**

- **闸门一(可用性)**:`HASS_TOKEN` 存在与否。

`tools/homeassistant_tool.py:345 @ 863e313`

```python
def _check_ha_available() -> bool:
    """Tool is only available when HASS_TOKEN is set."""
    return bool(get_secret("HASS_TOKEN"))
```

- **闸门二(域黑名单)**:六个能执行代码/发起请求的 HA 服务域被硬编码拒绝。

`tools/homeassistant_tool.py:54 @ 863e313`

```python
_BLOCKED_DOMAINS = frozenset({
    "shell_command",    # arbitrary shell commands as root in HA container
    "command_line",     # sensors/switches that execute shell commands
    "python_script",    # sandboxed but can escalate via hass.services.call()
    "pyscript",         # scripting integration with broader access
    "hassio",           # addon control, host shutdown/reboot, stdin to containers
    "rest_command",     # HTTP requests from HA server (SSRF vector)
})
```

这段黑名单上面的注释,是整段设计的前提 —— HA 的长效 token 是**全权**的,没有 scope:

`tools/homeassistant_tool.py:51 @ 863e313`

```python
# Service domains blocked for security -- these allow arbitrary code/command
# execution on the HA host or enable SSRF attacks on the local network.
# HA provides zero service-level access control; all safety must be in our layer.
```

**除此之外没有第三道闸门。** 负结论的搜索面:
① `registry.register` 的完整签名(`tools/registry.py:521-535`)里无任何审批/确认参数;
② 在 `tools/approval.py`、`agent/`、`hermes_cli/` 下 grep `ha_call_service` 与 `homeassistant`
(`--include=*.py`),命中全部是 toolset 名单 / 配置向导 / 指标分类,**没有一处是审批钩子**。

```verify
cd /home/user/hermes-agent && grep -rn "ha_call_service" --include=*.py tools/approval.py agent/ hermes_cli/ ; echo "exit=$?"
```

上面这条**零命中**(`grep` 退出码 1)。也就是说:**模型调用 `ha_call_service` 打开你家门锁,
不会弹任何确认。**

更进一步:`homeassistant` 虽然在默认关闭名单里,但只要检测到凭据就**自动移出**默认关闭:

`hermes_cli/tools_config.py:2300 @ 863e313`

```python
            if "homeassistant" in default_off and _homeassistant_credentials_present():
                default_off.remove("homeassistant")
```

`hermes_cli/tools_config.py:2355 @ 863e313`

```python
        # Home Assistant is already runtime-gated by its check_fn (requires
        # HASS_TOKEN to register any tools). When a user has configured
        # HASS_TOKEN, they've explicitly opted in — don't also strip it via
        # _DEFAULT_OFF_TOOLSETS, which would silently drop HA from platforms
        # (e.g. cron) that run through _get_platform_tools without an
        # explicit saved toolset list. Without this, Norbert's HA cron jobs
        # regressed after #14798 made cron honor per-platform tool config.
```

**取舍是被显式做出的**(注释解释了为什么:否则 cron 里的 HA 任务会静默失效),
但结果是:**"配了 token" ≡ "授权模型无条件控制家里所有设备"**。
在一个会读取不可信输入(邮件/群消息/网页)的 agent 里,这是本片里风险最高的一处设计
(记为 ◇-2:代码如此、文档未点明)。

#### 2.3.2 校验顺序:一处写得非常好的防御

`tools/homeassistant_tool.py:252 @ 863e313`

```python
def _handle_call_service(args: dict, **kw) -> str:
    """Handler for ha_call_service tool."""
    domain = args.get("domain", "")
    service = args.get("service", "")
    if not domain or not service:
        return tool_error("Missing required parameters: domain and service")

    # Validate domain/service format BEFORE the blocklist check — prevents
    # path traversal in /api/services/{domain}/{service} and blocklist bypass
    # via payloads like "shell_command/../light".
    if not _SERVICE_NAME_RE.match(domain):
        return tool_error(f"Invalid domain format: {domain!r}")
    if not _SERVICE_NAME_RE.match(service):
        return tool_error(f"Invalid service format: {service!r}")

    if domain in _BLOCKED_DOMAINS:
        return tool_error(
            f"Service domain '{domain}' is blocked for security. "
            f"Blocked domains: {', '.join(sorted(_BLOCKED_DOMAINS))}"
        )
```

**顺序本身就是防御。** 如果先查黑名单再查格式,`domain="shell_command/../light"`
既不在黑名单里(字符串不等),又能在拼进 URL 后被服务器归一化成 `shell_command`。
先做格式白名单(`^[a-z][a-z0-9_]*$`)就把这条路彻底堵死。

正则的理由写在定义处:

`tools/homeassistant_tool.py:42 @ 863e313`

```python
# Regex for valid HA service/domain names (e.g. "light", "turn_on", "shell_command").
# Only lowercase ASCII letters, digits, and underscores — no slashes, dots, or
# other characters that could allow path traversal in URL construction.
# The domain and service are interpolated into /api/services/{domain}/{service},
# so allowing arbitrary strings would enable SSRF via path traversal
# (e.g. domain="../../api/config") or blocked-domain bypass
# (e.g. domain="shell_command/../light").
```

**这正是 Discord 工具缺的那块(§2.2.1)。** 同一个仓库、同一片、同一种形状,一个补了一个没补 —— 
这是"安全修复没有横向扩散"的教科书例子。

#### 2.3.3 一个真实的漏网:`ha_get_state` 的 entity_id 校验有、`_async_list_entities` 无需

`_handle_get_state` 用 `_ENTITY_ID_RE` 校验:

`tools/homeassistant_tool.py:239 @ 863e313`

```python
    entity_id = args.get("entity_id", "")
    if not entity_id:
        return tool_error("Missing required parameter: entity_id")
```

`_handle_call_service` 也校验 `entity_id`:

`tools/homeassistant_tool.py:273 @ 863e313`

```python
    entity_id = args.get("entity_id")
    if entity_id and not _ENTITY_ID_RE.match(entity_id):
        return tool_error(f"Invalid entity_id format: {entity_id}")
```
但 `data` 参数是模型给的**任意 JSON 对象**,原样并进 payload:

`tools/homeassistant_tool.py:143 @ 863e313`

```python
def _build_service_payload(
    entity_id: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the JSON payload for a HA service call."""
    payload: Dict[str, Any] = {}
    if data:
        payload.update(data)
    # entity_id parameter takes precedence over data["entity_id"]
    if entity_id:
        payload["entity_id"] = entity_id
    return payload
```

注意注释点明了 `entity_id` 参数**覆盖** `data["entity_id"]` —— 这是有意的:
否则模型可以用校验过的 `entity_id="light.a"` 过关,再用 `data={"entity_id": "lock.front_door"}` 偷换。
但 `data` 里的**其它**键(如 `target`、`area_id`、`device_id` —— HA 的服务调用同样接受这些定位字段)
不受任何约束。**推定(未取证)**:`data={"area_id": "whole_house"}` 可以把
一次 `light.turn_off` 扩大到全屋,绕过 `entity_id` 白名单的粒度意图。见 §5。

#### 2.3.4 事件循环适配

`tools/homeassistant_tool.py:208 @ 863e313`

```python
def _run_async(coro):
    """Run an async coroutine from a sync handler."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already inside an event loop -- create a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=30)
    else:
        return asyncio.run(coro)
```

这是"同步工具处理器 + 异步 HTTP 客户端"的通用桥。注意它是**本文件私有**的
`_run_async`,和 `model_tools._run_async`(send_message 用的那个)是两份实现 —— 轻微重复。

---

### 2.4 飞书两件套 —— 凭据完全来自调用上下文

#### 2.4.1 机制:线程局部注入的 SDK 客户端

两个文件都没有任何凭据读取代码。客户端是**别人塞进来的**:

`tools/feishu_drive_tool.py:25 @ 863e313`

```python
def get_client():
    """Return the lark client for the current thread, or None."""
    return getattr(_local, "client", None)
```

塞它的只有一处(搜索面:全仓 `--include=*.py` grep `feishu_doc_tool|feishu_drive_tool` 与 `set_client`,
排除 `tests/`;命中即下面这一处):

`plugins/platforms/feishu/feishu_comment.py:1057 @ 863e313`

```python
    logger.info("[Feishu-Comment] _run_comment_agent: injecting lark client into tool thread-locals")
    from tools.feishu_doc_tool import set_client as set_doc_client
    from tools.feishu_drive_tool import set_client as set_drive_client
    set_doc_client(client)
    set_drive_client(client)
```

而那个 agent 是**专门为"回一条文档评论"造的一次性 agent**,工具集被钉死成两个:

`plugins/platforms/feishu/feishu_comment.py:1085 @ 863e313`

```python
            enabled_toolsets=["feishu_doc", "feishu_drive"],
```

**这是本片里唯一一个"能力随上下文注入、离开上下文即失效"的设计**,很值得抄:
凭据既不在环境变量里、也不在工具模块里,而是随着"这一次事件处理"的生命周期存在。
`threading.local()` 的选择也对 —— 工具处理器跑在工作线程里,线程局部天然是"每次调用一份"。

#### 2.4.2 但可见性和有效性对不上(◇-3)

注册时的 `check_fn` 只检查 **lark_oapi 这个包能不能被找到**,不检查有没有客户端:

`tools/feishu_doc_tool.py:54 @ 863e313`

```python
def _check_feishu():
    # Use ``importlib.util.find_spec`` — it checks whether ``lark_oapi``
    # is importable without actually executing its ``__init__``.
```

于是只要装了 lark_oapi,**任何**会话的模型都能在工具列表里看到 `feishu_doc_read` 等 5 个工具,
调用时才拿到 `Feishu client not available (not in a Feishu comment context)`。
这是"工具可见性 ≠ 工具可用性"的一处噪音:白白占 prompt、白白诱发一次失败调用。

`find_spec` 那个优化本身是对的(真 import 要 ~5 秒,而这个探针在每次 `hermes` 启动时都跑),
但它把**依赖存在性**当成了**上下文存在性**。

#### 2.4.3 权限粒度:租户级 token + 模型自选 file_token

`file_token` 是模型参数,没有"必须等于触发本次事件的那个文档"的约束:

`tools/feishu_drive_tool.py:351 @ 863e313`

```python
def _handle_add_comment(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client not available")

    file_token = args.get("file_token", "").strip()
    content = args.get("content", "").strip()
    if not file_token or not content:
        return tool_error("file_token and content are required")
```

而请求用的是**租户级** access token:

`tools/feishu_drive_tool.py:52 @ 863e313`

```python
        .token_types({AccessTokenType.TENANT})
```

**攻击面(静态对读,未实跑):** 触发这个 agent 的是**任何人**在**任何**该 bot 能看到的文档里
留的一条评论;评论正文进入模型上下文;模型据此选 `file_token`。
所以一条恶意评论可以指使 agent 去另一个文档留言(内容也由那条评论决定)。
这是 §1 场景 B 的完整链路。记为 ◇-4。

#### 2.4.4 分页参数没夹紧(小)

schema 说 `page_size` 最大 100,代码直接 `str(page_size)` 传下去,不夹紧:

`tools/feishu_drive_tool.py:147 @ 863e313`

```python
    queries = [
        ("file_type", file_type),
        ("user_id_type", "open_id"),
        ("page_size", str(page_size)),
    ]
```

对比同片 `yuanbao_tools.search_sticker` 是夹紧的:

`tools/yuanbao_tools.py:181 @ 863e313`

```python
    try:
        safe_limit = max(1, min(50, int(limit) if limit else 10))
    except (TypeError, ValueError):
```

后果轻微(服务端会拒),但"schema 里写了上限、代码不执行上限"是一个会传染的坏习惯。

---

### 2.5 `yuanbao_tools.py` —— 本片唯一直接给模型的"主动发消息"能力

#### 2.5.1 五个工具

| 工具 | 性质 | 锚点 + 摘录 |
|---|---|---|
| `yb_query_group_info` | 读 | `tools/yuanbao_tools.py:55`:`async def get_group_info(group_code: str) -> dict:` |
| `yb_query_group_members` | 读(**枚举全部群成员**) | `tools/yuanbao_tools.py:83`:`async def query_group_members(` |
| `yb_search_sticker` | 读(本地贴纸表) | `tools/yuanbao_tools.py:172`:`async def search_sticker(query: str = "", limit: int = 10) -> dict:` |
| `yb_send_sticker` | **写**(任意 chat_id) | `tools/yuanbao_tools.py:205`:`async def send_sticker(` |
| `yb_send_dm` | **写**(任意群成员,带附件) | `tools/yuanbao_tools.py:290`:`async def send_dm(` |

`yb_query_group_members` + `yb_send_dm` 组成一条完整的"枚举 → 定向私信"链:
前者返回全部成员的 `user_id` 与昵称,后者接受 `user_id` 直接发。
**没有主频道约束、没有"只能回复发起人"的限制、没有审批。**

#### 2.5.2 凭据与出网路径

这个文件**不打 HTTP**,全部经由 gateway 里的 WebSocket 适配器单例:

`tools/yuanbao_tools.py:28 @ 863e313`

```python
def _get_active_adapter():
    """Lazy import to avoid ImportError when gateway.platforms.yuanbao is unavailable."""
    try:
        from gateway.platforms.yuanbao import get_active_adapter
        return get_active_adapter()
    except ImportError:
        return None
```

`send_message_tool` 的元宝分支也走同一个单例,并且注释解释了为什么不能像 HTTP 平台那样临时建客户端:

`tools/send_message_tool.py:2074 @ 863e313`

```python
async def _send_yuanbao(chat_id, message, media_files=None):
    """Send via Yuanbao using the running gateway adapter's WebSocket connection.

    Yuanbao uses a persistent WebSocket — unlike HTTP-based platforms, we
    cannot create a throwaway client.  We obtain the running singleton from
    the adapter module itself (``get_active_adapter``).
```

**取舍:** WebSocket 平台天然没有"独立发送器"这条回落路径,所以元宝的 cron 投递
**必须**和网关同进程。这是长连接协议的固有代价,值得在设计自己的 harness 时提前想清楚:
**"能不能在网关之外发出去"是选平台协议时的一个硬约束,不是实现细节。**

#### 2.5.3 本地文件出网:有闸门,而且挂对了地方

`yb_send_dm` 允许模型给出**绝对本地路径**当附件。处理器在调用业务函数前过一遍全局媒体闸门:

`tools/yuanbao_tools.py:475 @ 863e313`

```python
    media_files = BasePlatformAdapter.filter_media_delivery_paths(media_files)
```

而且它**先把消息正文里内联的 `MEDIA:<path>` 也抠出来再一起过滤**,注释写明了理由
("模型经常把路径写正文里而不是用 media_files 参数"):

`tools/yuanbao_tools.py:470 @ 863e313`

```python
    message = args.get("message", "")
    from gateway.platforms.base import BasePlatformAdapter
    embedded_media, message = BasePlatformAdapter.extract_media(message)
    if embedded_media:
        media_files.extend(embedded_media)
```

闸门本身在 `gateway/platforms/base.py`:

`gateway/platforms/base.py:4339 @ 863e313`

```python
    def filter_media_delivery_paths(media_files) -> List[Tuple[str, bool]]:
        """Drop unsafe MEDIA paths and normalize accepted paths."""
        safe_media: List[Tuple[str, bool]] = []
        for media_path, is_voice in media_files or []:
            raw = str(media_path)
            safe_path = validate_media_delivery_path(raw)
            if safe_path:
                safe_media.append((safe_path, bool(is_voice)))
            else:
                logger.warning("Skipping unsafe MEDIA directive path: %s", _log_safe_path(raw))
        return safe_media
```

**但闸门只在 registry 处理器里,不在业务函数 `send_dm` 里。** 任何直接
`from tools.yuanbao_tools import send_dm` 的新调用方都会绕过它。
`send_message_tool._handle_send` 同样是在处理器层过滤(`:443`)。
这是一个**结构性脆弱点**:安全检查挂在"外壳"而不是"内核"上。记为 ◇-5。

#### 2.5.4 schema 里写给模型的"行为规训"

`yb_send_sticker` 的描述里有一段异常强硬的措辞,值得单独看:

`tools/yuanbao_tools.py:700 @ 863e313`

```python
            "CRITICAL: Whenever the user asks you to send a sticker / 贴纸 / 表情包, you MUST "
            "use this tool. DO NOT draw a PNG via execute_code / Pillow / matplotlib and "
            "then call send_image_file — that produces a fake 'sticker' image instead of a "
            "real TIM face and is the WRONG path. If no suitable sticker_id is known, call "
```

这是一条**从真实误用反推出来的 schema 修补**:模型被要求"发个表情包",它会自作聪明地
用 Pillow 画一张 PNG 再当图片发。修法是在工具描述里把错误路径点名否掉。
教训:**工具描述是 harness 的一部分,不是文档** —— 它是唯一能在模型做决定之前干预的地方。

---

## 3. 测试作为行为规格

环境记录(按 CLAUDE.md「报测试数时必须一并记环境」):

```verify
ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l
/home/user/hermes-venv/bin/python -c "import sys; print(sys.version)"
/home/user/hermes-venv/bin/python -c "import aiohttp; print(aiohttp.__version__)"
/home/user/hermes-venv/bin/python -c "import telegram" ; echo "telegram import exit=$?"
/home/user/hermes-venv/bin/python -c "import importlib.util; print(importlib.util.find_spec('lark_oapi'))"
```

```text
site-packages dist-info 条目数:87
Python 3.11.15
aiohttp 3.14.1
telegram: ModuleNotFoundError: No module named 'telegram'   (exit=1)
lark_oapi: None(未安装)
```

### 3.1 跑了什么、结果如何

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/tools/test_send_message_tool.py tests/tools/test_send_message_target_parse.py \
  tests/tools/test_send_message_react.py tests/tools/test_send_message_slack.py \
  tests/tools/test_send_message_missing_platforms.py tests/tools/test_send_message_telegram_proxy.py
```

```text
=== Summary: 6 files, 18 tests passed, 0 failed (100% complete) in 2.3s ===
  ✓ tests/tools/test_send_message_tool.py            (1s, 1.1s)   ← 注意:0 个用例
  ✓ tests/tools/test_send_message_missing_platforms.py (9✓)
  ✓ tests/tools/test_send_message_telegram_proxy.py    (2✓)
  ✓ tests/tools/test_send_message_slack.py             (2✓)
  ✓ tests/tools/test_send_message_target_parse.py      (3✓)
  ✓ tests/tools/test_send_message_react.py             (2✓)
```

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/tools/test_discord_tool.py tests/tools/test_homeassistant_tool.py \
  tests/tools/test_feishu_tools.py tests/gateway/test_homeassistant.py \
  tests/tools/test_discord_send_message_caption.py tests/tools/test_telegram_send_message_caption.py \
  tests/tools/test_slack_send_message_media.py tests/tools/test_whatsapp_send_message_media.py
```

```text
=== Summary: 8 files, 127 tests passed, 0 failed (100% complete) in 4.2s ===
  test_discord_tool.py 45✓ / test_homeassistant_tool.py 37✓ / tests/gateway/test_homeassistant.py 17✓
  test_whatsapp_send_message_media.py 19✓ / test_slack_send_message_media.py 3✓
  test_discord_send_message_caption.py 2✓ / test_telegram_send_message_caption.py 2✓
  test_feishu_tools.py 2✓
```

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/test_yuanbao_integration.py tests/gateway/test_yuanbao_media_ssrf.py tests/test_yuanbao_pipeline.py
```

```text
=== Summary: 3 files, 88 tests passed, 0 failed (100% complete) in 1.5s ===
  test_yuanbao_pipeline.py 70✓ / test_yuanbao_integration.py 17✓ / test_yuanbao_media_ssrf.py 1✓
```

**合计:17 个文件,233 个用例通过,0 失败。**

### 3.2 逐条诊断:一个静默整文件跳过(最重要的测试发现)

`tests/tools/test_send_message_tool.py` 是本片主文件的**主测试**(1700+ 行,47 个 `def test_`),
本轮**一个用例都没跑**,而运行器显示 `✓`:

```verify
cd /home/user/hermes-agent && grep -c "def test_" tests/tools/test_send_message_tool.py
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -m pytest tests/tools/test_send_message_tool.py --collect-only -q
```

```text
47
no tests collected in 0.09s
```

根因在文件第 16 行:

`tests/tools/test_send_message_tool.py:10 @ 863e313`

```python
import pytest

# python-telegram-bot is an optional dep — skip the entire module when
# it isn't installed (e.g. CI bare env). Tests that patch telegram.Bot
# or call _send_telegram need it; tests for other platforms don't but
# keeping the whole file consistent is simpler.
_HAS_TELEGRAM = pytest.importorskip("telegram", reason="python-telegram-bot not installed") is not None
```

**诊断:环境限制 + 用例组织问题的叠加。**
`python-telegram-bot` 在本容器 venv 里没装(它在 `[telegram]` extra 里,`[dev]` 不含),属**环境限制**。
但注释自己承认 `tests for other platforms don't [need it] but keeping the whole file consistent is simpler` —— 
把 Slack DM 解析、Signal 限流分批、Matrix 复用活适配器、WhatsApp caption、
`_send_via_adapter` 三级回落等**与 Telegram 无关**的 47 个用例,一起绑在一个可选依赖上。
**后果**:在任何没装 telegram extra 的环境里,本片 2116 行核心代码的行为规格是**零覆盖**,
而 CI 输出是绿的。这是 CLAUDE.md 讲的"无声的口子"在测试侧的同构体。

其余可跑到的用例把**部分**行为补回来了:`test_send_message_target_parse.py`(目标解析)、
`test_send_message_slack.py`(Slack 用户→DM)、`test_send_message_react.py`(表情回应)、
`test_send_message_missing_platforms.py`(未配置平台的报错)、
`test_slack_send_message_media.py` / `test_whatsapp_send_message_media.py` /
`test_discord_send_message_caption.py` / `test_telegram_send_message_caption.py`(caption 决策)。

### 3.3 飞书两个工具:几乎没有行为测试

`tests/tools/test_feishu_tools.py` 全文只有两个用例,而且都只验注册与 schema 形状:

`tests/tools/test_feishu_tools.py:24 @ 863e313`

```python
    def test_all_tools_registered(self):
        for tool_name, toolset in self.EXPECTED_TOOLS.items():
            entry = registry.get_entry(tool_name)
            self.assertIsNotNone(entry, f"{tool_name} not registered")
            self.assertEqual(entry.toolset, toolset)
```

`tools/feishu_doc_tool.py` + `tools/feishu_drive_tool.py` 合计 569 行、5 个会写外部系统的工具,
**行为规格为零**(没有一个用例调用过任何 `_handle_*`)。搜索面:`tests/` 下 grep
`feishu_doc_tool|feishu_drive_tool`,只命中这一个文件。

### 3.4 `yuanbao_tools.py` 的覆盖也很薄

搜索面:`grep -rln "yuanbao_tools" tests/` → 只有 `tests/test_yuanbao_integration.py` 一个文件,
其中提到 `yuanbao_tools` 的上下文是 toolset 注册检查:

`tests/test_yuanbao_integration.py:223 @ 863e313`

```python
    def test_yuanbao_toolset_registered(self):
```

`send_dm` 的成员消歧、多匹配返回候选、部分失败聚合 —— 都没有用例。

### 3.5 未撞到已知的 6 条容器必失败用例

本轮跑的 17 个文件里不含 CLAUDE.md 列出的那 6 条(无 IPv6 / root / 离线 / SQLite 措辞),
所以 0 失败是干净的 0 失败,不是被已知限制掩盖的。

---

## 4. 发现清单

> 强度标注:**实跑复现** = 我在本容器跑出来了;**静态对读** = 读代码 + 跨文件对照推出;
> **推定未取证** = 有理由怀疑但没能证实(全部同时列进 §5)。

### ■ 代码缺陷

**■-1 —— `send_message` 的"不给模型"禁令,可被模型经 `cronjob` 一跳绕过。**(静态对读)
`tools/send_message_tool.py:2106` 的 NOTE 声称 "The agent should not decide on its own to fire off
cross-platform messages";但 `cronjob` 是注册了的模型工具,其 `deliver` 参数
(`tools/cronjob_tools.py:1073`)是自由字符串,`cron/scheduler.py:1177` 用**本片的**
`_parse_target_ref` 解析它,带冒号的分支在 `cron/scheduler.py:1210` **无条件返回**该目标,
再由 `cron/scheduler.py:1500` 交回本片的 `_send_to_platform`。
即模型可以 `cronjob(action='create', deliver='telegram:<任意群>:<任意话题>', prompt=…)`,
让同一引擎在下一 tick 发出它选定的内容到它选定的目标。
**这不是理论**:通讯录不是白名单(§2.1.2),裸 ID 直通。

**■-2 —— QQBot 超长消息静默截断并返回成功。**(静态对读 + 负结论已给搜索面)
`tools/send_message_tool.py:2042` 的 `message[:4000]`;`Platform.QQBOT` 无 `_MAX_LENGTHS` 条目
也无 qqbot 插件(`ls plugins/platforms/` 22 项无 qqbot;registry 零命中),
于是不分块 → 直接切 → `{"success": True}`,无 warning。
这是本片唯一一处**无声的内容丢失**。

**■-3 —— `tools/discord_tool.py` 用 urllib,凭据会跟着跨 origin 重定向走。**(实跑复现)
`tools/discord_tool.py:108` 的 `urllib.request.urlopen` 默认跟随重定向,
stdlib `HTTPRedirectHandler.redirect_request` 只剥 `content-length`/`content-type`,
`Authorization: Bot <token>` 原样带到新 origin(§2.1.8 实验 2 已复现)。
同片的 aiohttp 3.14.1 会剥(实验 1),httpx 默认不跟随。
仓库里现成的 `create_ssrf_safe_client` 未被使用,而 kanban 那条附件下载路径是显式关掉重定向的:

`tools/kanban_tools.py:1086 @ 863e313`

```python
            current_url,
            headers={"User-Agent": "hermes-kanban/attach"},
            timeout=30,
            follow_redirects=False,
```

缓解:base URL 是常量 `DISCORD_API_BASE`。

**■-4 —— Discord 工具零限流处理。**(静态对读 + 已给搜索面)
`tools/discord_tool.py` 全文无 429 / `Retry-After` 处理;429 变成一条错误字符串交给模型,
模型很可能立即重试。对比同片 Signal 的进程级调度器与 Telegram 的指数退避,是明显不对称。

**■-5 —— Discord 的路径参数零格式校验,而同片 HA 为完全相同的形状专门做了防御。**
(客户端不归一化 `..` 这一半**实跑复现**;能否命中真实端点**未取证**,见 §5)
`tools/discord_tool.py:88` 的 `url = f"{DISCORD_API_BASE}{path}"`,`path` 由模型给的
`channel_id`/`message_id` 等 f-string 拼成;`tools/discord_tool.py:1034` 只检查非空。
`tools/homeassistant_tool.py:259-265` 为同一形状加了白名单正则并在注释里写明理由。

### ▲ 文档与代码矛盾

**▲-1 —— `website/docs/reference/tools-reference.md` 的 `discord` 工具动作列表,一半是不存在的动作。**(静态对读)

`website/docs/reference/tools-reference.md:242 @ 863e313`

> | `discord` | Read and participate in a Discord server. Actions include `search_members`, `fetch_messages`, `send_message`, `react`, `fetch_channel`, `list_channels`, and more. | `DISCORD_BOT_TOKEN` |

整行判定(按 CLAUDE.md「整句/整段一并判定」):该行归 `## \`discord\` toolset` 标题管,描述的是
**注册名为 `discord` 的那一个工具**。代码里 `discord` 工具的动作集是
`_CORE_ACTIONS` = `{fetch_messages, search_members, create_thread}`
(`tools/discord_tool.py:650` 的 `_CORE_ACTION_NAMES`)。
逐项核:`search_members` ✓、`fetch_messages` ✓、`send_message` ✗(`_ACTIONS` 无此键)、
`react` ✗、`fetch_channel` ✗(有 `channel_info`,名字不同且属 admin)、
`list_channels` ✗(存在但属 `discord_admin`,不属 `discord`)。
**六项里三项不存在、一项名字错、一项归错工具。**

**▲-2 —— 同文件 `discord_admin` 行列举的管理能力,大半不存在。**(静态对读)

`website/docs/reference/tools-reference.md:250 @ 863e313`

> | `discord_admin` | Manage a Discord server via the REST API: list guilds/channels/roles, create/edit/delete channels, manage role grants, timeouts, kicks, and bans. | `DISCORD_BOT_TOKEN` + bot permissions |

代码里 `_ADMIN_ACTIONS` = `_ACTIONS` 减去 core 三项 = `{list_guilds, server_info, list_channels,
channel_info, list_roles, member_info, list_pins, pin_message, unpin_message, delete_message,
add_role, remove_role}`(由 `tools/discord_tool.py:651` 计算)。
"list guilds/channels/roles" ✓、"manage role grants" ✓;
**"create/edit/delete channels" ✗、"timeouts" ✗、"kicks" ✗、"bans" ✗** —— 四项能力代码里根本没有。

**▲-3 —— `website/docs/user-guide/messaging/slack.md` 的一整节讲"agent 的 `send_message` 工具",而 agent 没有这个工具。**(静态对读)

`website/docs/user-guide/messaging/slack.md:820 @ 863e313`

> ### Sending messages and media (`send_message`)
>
> The agent's `send_message` tool accepts the same target shapes: a channel ID (`C…`/`G…`), a DM conversation (`D…`), or a bare user ID (`U…`/`W…`), which is resolved to the user's DM on every send path — text, media, and interactive prompts alike.

整节判定:标题 `### Sending messages and media (\`send_message\`)` 与其下唯一一段正文,
主语明确是 "The agent's `send_message` tool"。代码侧见 §2.1.1:**该工具从未注册**。
段落里关于**目标形状**的技术描述本身是对的(对应 `_parse_target_ref` 与
`_resolve_slack_user_target`),错的是"这是 agent 的工具"这个归属。

**这条 ▲ 的分量在于:同一份文档树里另一处是对的**,说明这是一次**没有扫干净的迁移**:

`website/docs/user-guide/skills/bundled/research/research-research-paper-writing.md:2169 @ 863e313`

> | **cron `deliver:`** | Notify the user when experiments complete or drafts are ready even if they're not in chat — schedule the check as a cron job with a messaging `deliver:` target (the agent no longer has a `send_message` tool; outbound delivery is handled by cron/`hermes send`). |

有意思的是:这条**正确的**文档,恰恰把 ■-1 的绕行路径当成推荐做法写了出来 —— 
"agent 没有 send_message 工具了,改用 cron 的 deliver"。

### ◇ 代码有、文档无

**◇-1 —— 四处指向已删工具的残留名单。**(静态对读)
`agent/tool_guardrails.py:55`(`"send_message"` 在 `MUTATING_TOOL_NAMES` 里)、
`tools/delegate_tool.py:53`(子代理黑名单)、`acp_adapter/tools.py:73`(ACP 精修工具名单)、
`agent/display.py:530` 与 `:1504`(两处渲染分支)。
全部是死代码,但会让读代码的人(和读文档的人)以为模型有这个工具。
`website/docs/user-guide/features/delegation.md:164` 还把它列进子代理禁用清单 —— 
禁一个不存在的工具,字面为真、实质为空。

**◇-2 —— 配了 `HASS_TOKEN` 就等于无条件授权模型控制全部智能家居设备,没有逐次审批。**(静态对读 + 负结论已给搜索面)
`tools/homeassistant_tool.py:345` 的 `_check_ha_available` 是唯一可用性闸门;
`hermes_cli/tools_config.py:2300` / `:2362` 把 `homeassistant` 从默认关闭名单里自动移除;
`tools/registry.py:521` 的 `register` 签名无审批参数;`ha_call_service` 在
`tools/approval.py` / `agent/` / `hermes_cli/` 下零命中。
文档侧我未找到任何"HA 工具没有逐次确认"的提示。

**◇-3 —— 飞书 5 个工具的可见性只绑依赖、不绑上下文。**(静态对读)
`tools/feishu_doc_tool.py:54` 的 `_check_feishu` 只做 `find_spec("lark_oapi")`;
真正的可用条件是 `plugins/platforms/feishu/feishu_comment.py:1058` 注入过线程局部客户端。
装了 SDK 的任何会话都会看到这 5 个工具并在调用时失败。

**◇-4 —— 飞书评论 agent 的 `file_token` 由模型自选,凭据是租户级。**(静态对读)
`tools/feishu_drive_tool.py:351`(`file_token` 来自 args)+ `tools/feishu_drive_tool.py:52`
(`AccessTokenType.TENANT`)。一条不可信评论可以指使 agent 去同租户的另一个文档留言。

**◇-5 —— 媒体路径闸门挂在 registry 处理器上,不在业务函数上。**(静态对读)
`tools/yuanbao_tools.py:475` 与下面这处都在**处理器**里调 `filter_media_delivery_paths`:

`tools/send_message_tool.py:442 @ 863e313`

```python
    media_files, cleaned_message = BasePlatformAdapter.extract_media(message)
    media_files = BasePlatformAdapter.filter_media_delivery_paths(media_files)
    mirror_text = cleaned_message.strip() or _describe_media_for_mirror(media_files)
```

而;`yuanbao_tools.send_dm`(`:290`)与
`send_message_tool._send_to_platform`(`:783`)本身不过滤。
任何新的内部调用方直接 import 业务函数即绕过。

### ◎ 文档成立但显著保守

**◎-1 —— `adding-platform-adapters.md` 说"built-in platforms (Telegram, Discord, Slack, etc.) ship direct REST helpers in `tools/send_message_tool.py`",实际这些 helper 大多已迁走。**(静态对读)

`website/docs/developer-guide/adding-platform-adapters.md:324 @ 863e313`

> Why this hook is necessary: built-in platforms (Telegram, Discord, Slack, etc.) ship direct REST helpers in `tools/send_message_tool.py` so cron can deliver without holding the gateway in the same process.

字面判定:这句话的**结论**(所以需要 `standalone_sender_fn` 这个钩子)成立且正是代码现状;
但它举的三个例子里,Discord 与 Slack 的 helper 已经**搬进插件**了 —— 文件里留着墓碑注释:

`tools/send_message_tool.py:1496 @ 863e313`

```python
# _send_slack moved to the slack plugin as _standalone_send
# (plugins/platforms/slack/adapter.py), wired via standalone_sender_fn. #41112.
```

现在只剩 Telegram / Signal / Weixin / BlueBubbles / QQBot / Yuanbao 六个 helper 还在本文件里。
因为这句话没有断言"全部内置平台都在这个文件里",字面不构成矛盾,故记 ◎ 而非 ▲。

---

## 5. 未取证 / 推定

1. **Discord 的 `..` 路径段能否真的命中另一个 API 端点。**(推定未取证)
   锚点 `tools/discord_tool.py:88` 的 `url = f"{DISCORD_API_BASE}{path}"`。
   我已实跑确认 urllib **不归一化**、把 `../..` 原样发到线上(§2.2.1);
   但 Discord 边缘(Cloudflare)是否归一化点段、归一化后 `_delete_message` 的
   `message_id = "../../guilds/G/members/U"` 会不会变成"踢人"——**没有取证**,
   也不打算配置真实 token 去试。复核需要一个真实 bot token 与一个测试服务器。
2. **HA `data` 参数里的 `area_id` / `device_id` / `target` 能否绕过 `entity_id` 粒度。**(推定未取证)
   锚点 `tools/homeassistant_tool.py:144` 的 `_build_service_payload`:代码只保证
   `entity_id` 参数覆盖 `data["entity_id"]`,对 `data` 里的其它定位键无约束。
   HA 服务调用是否接受这些键、接受后是否扩大作用域,需要一个真实 HA 实例复核。
3. **是否存在插件在运行时把 `send_message` 注册成模型工具。**(推定未取证)
   我的搜索面只覆盖基线仓库内的静态 `--include=*.py` grep(见 §2.1.1);
   `registry.register` 允许 `override=True` 的插件注册,外部插件目录不在基线里。
   所以"模型绝对拿不到 send_message"这条,严格说只在**基线自带代码**范围内成立。
4. **■-1 的端到端链路我只做了静态对读,没有实跑。**
   我没有跑起一个网关 + cron + 真实平台去验证"模型创建的 cron 任务真的发到了任意目标"。
   `cron/scheduler.py:1210` 那个 `return` 之后到 `_send_to_platform` 之间还有
   `_expand_routing_tokens`、去重、`wrap_response` 包装等步骤,我读了但没逐行验证有无别的闸门。
5. **`_send_via_adapter` 的三级回落我没有构造失败注入验证。**
   锚点 `tools/send_message_tool.py:688`。这条路径的用例大部分在被静默跳过的
   `tests/tools/test_send_message_tool.py`(`:1649` / `:1682` 有 `_send_via_adapter` 用例)里。
6. **Telegram 那条"超时不重试"的取舍理由是我推断的**,代码里只有
   `tools/send_message_tool.py:166` 的 `if "timed out" in text or "timeout" in text: return None`,
   没有注释解释为什么。我在 §2.1.7 写的"可能已送达"是**我的推断,不是代码的声明**。
7. **QQBot 的 4000 字符是否恰好是 QQ 开放平台的真实上限**,我没有查证;
   ■-2 成立与否不依赖这个数字对不对(缺陷在"静默截断且报成功",不在数字)。

---

## 6. 本片移交项

| 编号 | 锚点 + 摘录 | 一句话现象 | 建议轮次 |
|---|---|---|---|
| H-R9D-D-a | `tools/send_message_tool.py:2106`:`# NOTE: ``send_message`` is intentionally NOT registered as an agent-callable` | 该 NOTE 声称模型不能自主外发,但 `cronjob` 的 `deliver` 是模型可写的自由目标字符串,经 `cron/scheduler.py:1177` 的 `_parse_target_ref` 直通同一引擎;需要一轮把 cron 片与本片合起来定案这条绕行是否被别处闸住 | R10(cron 片) |
| H-R9D-D-b | `tools/send_message_tool.py:2042`:`payload = {"content": message[:4000], "msg_type": 0}` | QQBot 无插件、无 `max_message_length`,超长消息被静默切断且返回 `success: True`,无 warning | R10 |
| H-R9D-D-c | `tools/discord_tool.py:88`:`url = f"{DISCORD_API_BASE}{path}"` | 模型给的 `channel_id`/`message_id` 零格式校验直接拼进 URL;urllib 实测不归一化 `..`;同片 HA 为同一形状专门加了白名单正则(`tools/homeassistant_tool.py:262`) | R10 |
| H-R9D-D-d | `tools/discord_tool.py:108`:`with urllib.request.urlopen(req, timeout=timeout) as resp:` | 本片唯一"凭据跟着重定向走"的客户端(实跑复现 Authorization 跨 origin 保留);仓库已有 `tools/url_safety.py:841` 的 `create_ssrf_safe_client` 未被使用 | R10 |
| H-R9D-D-e | `tests/tools/test_send_message_tool.py:16`:`_HAS_TELEGRAM = pytest.importorskip("telegram", reason="python-telegram-bot not installed") is not None` | 47 个用例(含 Slack/Signal/Matrix/WhatsApp 等与 Telegram 无关的)被一个可选依赖整文件跳过,运行器仍显示 ✓;下一轮报测试数时要把它当"已知静默跳过"记账 | 每轮 |
| H-R9D-D-f | `tools/homeassistant_tool.py:345`:`def _check_ha_available() -> bool:` | 配了 `HASS_TOKEN` 即自动启用(`hermes_cli/tools_config.py:2300`)且无任何逐次审批;审批片若已定案 hermes 的审批只覆盖 terminal/file,需要显式把"物理设备控制无审批"写进结论 | R10(审批片) |
| H-R9D-D-g | `tools/feishu_doc_tool.py:54`:`def _check_feishu():` | 可用性探针只查 `lark_oapi` 是否可导入,真实可用条件是 `plugins/platforms/feishu/feishu_comment.py:1058` 注入的线程局部客户端;装了 SDK 的任何会话都会看到 5 个必失败的工具 | R10 |
| H-R9D-D-h | `website/docs/reference/tools-reference.md:242`:`| `discord` | Read and participate in a Discord server. Actions include `search_members`, `fetch_messages`, `send_message`, `react`, `fetch_channel`, `list_channels`, and more. | `DISCORD_BOT_TOKEN` |` | 该行六个动作里三个不存在、一个名字错、一个归错工具;同表 `:250` 的 `discord_admin` 行也列了四项不存在的能力 | R12 装订前 |

---

## 7. 交付自检

```verify
cd /home/user/hermes-agent && git rev-parse HEAD && git status --porcelain && echo "PORCELAIN-EMPTY-ABOVE"
```

```text
863e31318553cda8ad61df681d08175364d4164b
PORCELAIN-EMPTY-ABOVE
```

- **基线 `git status --porcelain` 输出为空**(交付前已重跑确认,见上)。HEAD 仍为 `863e313`。
- **未在基线里做任何写操作**:全程只用 `sed`/`awk`/`grep`/`git rev-parse`/`git status` 与
  `scripts/run_tests.sh`(该脚本只读运行测试;它会在基线目录写 `test_durations.json`——
  该文件被基线自己的 `.gitignore:35` 忽略(`git check-ignore -v test_durations.json` 输出
  `.gitignore:35:test_durations.json`),故 `git status --porcelain` 仍为空,见上面的自检输出)。
- **未安装任何包**:没有跑过 `pip install` / `venv` 扩包;所有跑基线代码的命令都带
  `HERMES_DISABLE_LAZY_INSTALLS=1`。venv 包数在本轮开始与结束时一致(87)。
- **未修改 `/home/user/hermes-study/scripts/` 下任何文件**。
- **只写了本文件** `/home/user/hermes-study/notes/r9d-raw-messaging-platform-tools.md`;
  临时实验脚本写在会话 scratchpad 目录,不在两个仓库内。
