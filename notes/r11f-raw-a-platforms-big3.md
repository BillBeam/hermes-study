# R11F 片 A 底稿 —— `plugins/platforms/{discord,telegram,slack}` 三大适配器(L2 结构级)

> 溯源约定:凡对 hermes-agent 的断言,紧跟 `路径:行号 @ 863e313` 与代码原文块。
> 锚点一律单独成行、置于块之前。
> L2 = **读接口面不读实现体**:本片穷举的是「三家与宿主 / 与平台之间的每一条接缝」,
> 适配器内部的 170 / 164 / 120 个私有方法**不逐个读实现**,但**逐类归口**(见 §2.1)。

**范围**:15 文件 / 31,082 行,是全仓最大的三个平台适配器。

```verify
awk -F'\t' '{n++; l+=$2} END{printf "%d 文件 / %d 行\n", n, l}' data/r11f/slices/A.txt
```

```text
15 文件 / 31082 行
```

---

## 1. 点名表(判据 1:15 个文件逐个全路径 + 一句话角色)

| # | 全路径 | 行 | 角色 |
|---|---|---:|---|
| 1 | `plugins/platforms/discord/__init__.py` | 3 | 包门面:`from .adapter import register`,把 `register` 提到包顶层供插件管理器发现 |
| 2 | `plugins/platforms/discord/adapter.py` | 10138 | Discord 适配器主体:`DiscordAdapter(BasePlatformAdapter)` + 27 条原生 slash + 语音 + 线程 + `register(ctx)` 入口 |
| 3 | `plugins/platforms/discord/ffmpeg_utils.py` | 43 | ffmpeg 可执行文件发现:委托给仓库公共发现器,再叠加 `FFMPEG_PATH` 显式覆盖与 Windows winget 兜底 |
| 4 | `plugins/platforms/discord/plugin.yaml` | 34 | Discord 插件清单:8 个顶层键、1 条 `requires_env`、4 条 `optional_env` |
| 5 | `plugins/platforms/discord/recovery.py` | 112 | 重连消息补投的持久化台账:profile 域内的小 SQLite 库 `discord_message_recovery.db`,保留 30 天 |
| 6 | `plugins/platforms/discord/voice_mixer.py` | 387 | 软件混音器:discord.py 只允许一条 opus 流,本模块在其**上游**把「环境底噪 + 语音」混成一帧并做 ducking |
| 7 | `plugins/platforms/slack/__init__.py` | 3 | 包门面(同 1) |
| 8 | `plugins/platforms/slack/adapter.py` | 9088 | Slack 适配器主体:`SlackAdapter(BasePlatformAdapter)` + Socket Mode 12 类事件 + Block Kit 交互 + `register(ctx)` |
| 9 | `plugins/platforms/slack/block_kit.py` | 688 | 把 agent 的 markdown 渲染成 Slack Block Kit(纯函数、不碰客户端、失败即返回 `None` 让调用方回落纯文本) |
| 10 | `plugins/platforms/slack/plugin.yaml` | 45 | Slack 插件清单:8 个顶层键、**2** 条 `requires_env`(bot + app token)、5 条 `optional_env` |
| 11 | `plugins/platforms/telegram/__init__.py` | 3 | 包门面(同 1) |
| 12 | `plugins/platforms/telegram/adapter.py` | 10147 | Telegram 适配器主体:`TelegramAdapter(BasePlatformAdapter)` + 论坛话题 + 流式编辑 + inline keyboard + `register(ctx)` |
| 13 | `plugins/platforms/telegram/plugin.yaml` | 35 | Telegram 插件清单:8 个顶层键、1 条 `requires_env`、4 条 `optional_env` |
| 14 | `plugins/platforms/telegram/telegram_ids.py` | 51 | `chat_id` 归一化:Bot API 同时接受数字 ID 与 `@username`,本模块避免历史上那句 `int(chat_id)` 崩溃 |
| 15 | `plugins/platforms/telegram/telegram_network.py` | 305 | 保留主机名的回落传输:`api.telegram.org` 被本地 DNS 解析到不可达地址时,用 DoH 发现备用 IPv4 并重试 TCP,SNI 仍是原主机名 |

**没有 `pip_dependencies` 键**:三份 manifest 都不声明依赖。依赖走 `tools/lazy_deps.py` 的
`platform.<name>` 条目,由 `check_fn` 在**首次调用时惰性安装**(见 §2.8)。

---

## 2. 判据 2:接缝穷举

本片认定三家适配器共有 **8 个对外接缝**。逐个给机械枚举命令、条数与全表。

### 2.1 宿主 ABC 契约面 —— `BasePlatformAdapter`

`gateway/platforms/base.py:2629 @ 863e313`

```
class BasePlatformAdapter(ABC):
    """
    Base class for platform adapters.
```

枚举命令与条数:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/a_adapter_surface.py
```

```text
BASE gateway/platforms/base.py:2629 BasePlatformAdapter  methods=126 abstract=4 class_attrs=18
  abstract: connect disconnect get_chat_info send
DISCORD   plugins/platforms/discord/adapter.py:976 DiscordAdapter  methods=194 class_attrs=8
  abstract_impl=4 abstract_miss=0 override=20 extra=170 attr_override=2 attr_extra=6
TELEGRAM  plugins/platforms/telegram/adapter.py:617 TelegramAdapter  methods=194 class_attrs=29
  abstract_impl=4 abstract_miss=0 override=26 extra=164 attr_override=8 attr_extra=21
SLACK     plugins/platforms/slack/adapter.py:855 SlackAdapter  methods=142 class_attrs=12
  abstract_impl=4 abstract_miss=0 override=18 extra=120 attr_override=5 attr_extra=7
```

**读法**:基类 126 个方法里只有 **4 个**是 `@abstractmethod`;其余 122 个都带默认实现,
子类**可覆盖可不覆盖**。三家的差异不在「实现了没有」,而在「覆盖了哪 20 / 26 / 18 个」。

**四个抽象方法,三家全部实现,零缺口**:

| 抽象方法 | 基类锚点 | discord | telegram | slack |
|---|---|---|---|---|
| `connect` | `gateway/platforms/base.py:3471` 的 `async def connect` | `:1210` | `:3663` | `:1753` |
| `disconnect` | `gateway/platforms/base.py:3491` 的 `async def disconnect` | `:1771` | `:4295` | `:2264` |
| `send` | `gateway/platforms/base.py:3496` 的 `async def send` | `:3027` | `:4432` | `:2439` |
| `get_chat_info` | `gateway/platforms/base.py:6671`:`    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:` | `:5235` | `:7566` | `:4265` |

**三家各自覆盖了哪些基类具体方法**(逐项列全,不抽样;全表另见
`data/r11f/a/adapter-contract-matrix.tsv`,126 行 = 基类全部方法 × 三家在位与否):

| 家 | 覆盖数 | 逐项 |
|---|---:|---|
| discord | 20 | `__init__` `cancel_background_tasks` `create_handoff_thread` `edit_message` `format_message` `format_tool_preview` `on_processing_complete` `on_processing_start` `play_tts` `send_animation` `send_clarify` `send_document` `send_image` `send_image_file` `send_multiple_images` `send_slash_confirm` `send_typing` `send_video` `send_voice` `stop_typing` |
| telegram | 26 | `__init__` `_ea_escape` `_mark_connected` `_mark_disconnected` `_set_fatal_error` `create_handoff_thread` `delete_message` `edit_message` `format_message` `message_len_fn` `on_processing_complete` `on_processing_start` `prefers_fresh_final_streaming` `send_animation` `send_clarify` `send_document` `send_draft` `send_image` `send_image_file` `send_multiple_images` `send_slash_confirm` `send_typing` `send_video` `send_voice` `streaming_overflow_limit` `supports_draft_streaming` |
| slack | 18 | `__init__` `create_handoff_thread` `delete_message` `edit_message` `format_message` `on_processing_complete` `on_processing_start` `send_clarify` `send_document` `send_image` `send_image_file` `send_multiple_images` `send_private_notice` `send_slash_confirm` `send_typing` `send_video` `send_voice` `stop_typing` |

**三家都覆盖的 13 个** = `__init__` `create_handoff_thread` `edit_message` `format_message`
`on_processing_complete` `on_processing_start` `send_clarify` `send_document` `send_image`
`send_image_file` `send_multiple_images` `send_slash_confirm` `send_typing` `send_video` `send_voice`
—— 这是「一个平台适配器至少要重写什么」的经验答案:**连接三件套 + 媒体七件套 + 格式化 + 交互两件套**。

**只有一家覆盖的**:
- discord 独有:`cancel_background_tasks` `format_tool_preview` `play_tts`(语音回放)
- telegram 独有:`_ea_escape` `_mark_connected` `_mark_disconnected` `_set_fatal_error`
  `message_len_fn` `prefers_fresh_final_streaming` `send_draft` `streaming_overflow_limit`
  `supports_draft_streaming`(**流式编辑**那一簇 —— 只有 Telegram 把「边生成边改同一条消息」做到底)
- slack 独有:`send_private_notice`(ephemeral 消息,Slack 才有的原语)
- discord + slack 有、telegram 无:`stop_typing`
- telegram + slack 有、discord 无:`delete_message`
- discord + telegram 有、slack 无:`send_animation`(GIF/动图)

**「多出来的」170 / 164 / 120 个方法归口**(L2 不读实现体,但要交代它们是什么):
全部是各家的私有实现(`_` 前缀占绝大多数)、平台 SDK 回调、以及模块级工厂
(`_build_adapter` / `_standalone_send` / `_apply_yaml_config` / `interactive_setup` /
`check_*_requirements`)。它们**不构成对外接缝**,除了被宿主 `getattr` 探到的那一批 —— 见 §2.3。

### 2.2 能力开关面 —— 基类类属性

基类用 18 个类属性表达「这个平台能干什么」,子类靠**覆盖类属性**而不是重写方法来声明能力。
基类全表(18 项):`REQUIRES_EDIT_FINALIZE` `_ACK_EMOJI` `_EA_CMD_BUDGET` `_EA_CODE_CLOSE`
`_EA_CODE_OPEN` `_EA_HEADER` `_EA_REASON_LABEL` `_EA_SMART_DENY_LINE` `_FAIL_EMOJI` `_OK_EMOJI`
`gateway_runner` `interactive_resume` `splits_long_messages` `supports_async_delivery`
`supports_code_blocks` `supports_inchannel_continuable` `supports_status_text` `typed_command_prefix`

三家覆盖情况(逐项列全):

| 类属性 | 基类默认(锚点) | discord | telegram | slack |
|---|---|---|---|---|
| `splits_long_messages` | `gateway/platforms/base.py:2698`:`    splits_long_messages: bool = False` | `True` | `True` | `True` |
| `supports_code_blocks` | `gateway/platforms/base.py:2648`:`    supports_code_blocks: bool = False` | `True` | `True` | `True` |
| `supports_status_text` | `gateway/platforms/base.py:2656`:`    supports_status_text: bool = False` | — | — | `True` |
| `supports_inchannel_continuable` | `gateway/platforms/base.py:2725`:`    supports_inchannel_continuable: bool = False` | — | — | `True` |
| `typed_command_prefix` | `gateway/platforms/base.py:2710`:`    typed_command_prefix: str = "/"` | — | — | `'!'` |
| `REQUIRES_EDIT_FINALIZE` | `gateway/platforms/base.py:3523`:`    REQUIRES_EDIT_FINALIZE: bool = False` | — | `True` | — |
| `_EA_HEADER` / `_EA_CODE_OPEN` / `_EA_CODE_CLOSE` / `_EA_CMD_BUDGET` / `_EA_SMART_DENY_LINE` | 基类文本模板 | — | 全部覆盖(HTML 版) | — |
| `supports_async_delivery` | `gateway/platforms/base.py:2690`:`    supports_async_delivery: bool = True` | — | — | — |
| `interactive_resume` | `gateway/platforms/base.py:2738`:`    interactive_resume: bool = True` | — | — | — |

**`typed_command_prefix` 这一格是整张表里信息量最大的**:Slack 把打字命令前缀改成 `!`,
因为 `/` 在 Slack 里已被平台自己的 slash 机制占用 —— 用户打 `/stop` 会被 Slack 截走,
不会进消息事件。基类因此把「命令前缀」做成可覆盖属性,而不是在调用点写
`if platform == SLACK`。这条设计在基类注释里是明写的。

`gateway/platforms/base.py:2709 @ 863e313`

```
    # "typed_command_prefix", "/"); no per-platform branching at call sites.
    typed_command_prefix: str = "/"
```

三家**自己新增**的类属性(不在基类里,6 / 21 / 7 条):

| 家 | 数 | 逐项 |
|---|---:|---|
| discord | 6 | `MAX_MESSAGE_LENGTH` `PLAYBACK_TIMEOUT` `PLAYBACK_TIMEOUT_PADDING` `VOICE_TIMEOUT` `_KEEPALIVE_INTERVAL` `_SPLIT_THRESHOLD` |
| telegram | 21 | `FALLBACK_ON_FINAL_EDIT_FLOOD` `MAX_MESSAGE_LENGTH` `MEDIA_GROUP_WAIT_SECONDS` `RESEND_FINAL_ON_EMPTY_STREAM_FALLBACK` `RICH_MESSAGE_MAX_BYTES` `RICH_MESSAGE_MAX_CHARS` `_BOT_IDENTITY_PROBE_TIMEOUT` `_BOT_IDENTITY_TTL_SECONDS` `_FOREIGN_BOT_HANDLE_RE` `_GENERAL_TOPIC_THREAD_ID` `_GT_VERB_DISPATCH` `_MODEL_PAGE_SIZE` `_PROVIDER_PAGE_SIZE` `_RICH_CJK_RE` `_RICH_DETAILS_RE` `_RICH_MATH_IN_DETAILS_RE` `_SPLIT_THRESHOLD` `_TEXT_BATCH_FAST_DELAY_S` `_TEXT_BATCH_FAST_LEN` `_TEXT_BATCH_SHORT_DELAY_S` `_TEXT_BATCH_SHORT_LEN` |
| slack | 7 | `MAX_MESSAGE_LENGTH` `_MARKDOWN_BLOCK_MAX` `_REACTION_EMOJI_MAP` `_SLACK_CDN_EXACT_HOSTS` `_SLACK_CDN_HOST_SUFFIXES` `_SLASH_CTX_MAX` `_SLASH_CTX_TTL` |

`MAX_MESSAGE_LENGTH` **三家都有、基类没有** —— 它是 §2.3 说的鸭子类型钩子,不是 ABC 的一部分。

### 2.3 鸭子类型可选钩子面(ABC 之外的隐形契约)

**这是本片最值得记的一条结构发现**:适配器真正的对外面 ≠ ABC。宿主还会
`getattr(adapter, "<名字>", 默认)` 去探一批**可有可无**的属性/方法,这些名字
既不在 ABC 里、也不在 `PlatformEntry` 里、更不在 `plugin.yaml` 里 —— 它们只以
**字符串字面量**的形式活在 `gateway/` 与 `hermes_cli/` 的源码中。

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/a_duck_hooks.py | head -3
```

```text
duck-typed hooks probed on adapters: 57 (probe sites 93)
  in BasePlatformAdapter     : 22
  NOT in BasePlatformAdapter : 35
```

**57 个被探的名字 / 93 个探测点**,其中 **35 个基类里根本没有**。全表在
`data/r11f/a/duck-hooks.tsv`(58 行 = 表头 + 57 项);与本片三家相关的逐项:

| 钩子 | 首个探测点 | discord | telegram | slack |
|---|---|---|---|---|
| `MAX_MESSAGE_LENGTH` | `gateway/run.py:3983` 的 `getattr` | ✓ | ✓ | ✓ |
| `send_or_update_status` | `gateway/run.py:777` 的 `getattr` | — | ✓ | ✓ |
| `FALLBACK_ON_FINAL_EDIT_FLOOD` | `gateway/stream_consumer.py:2320` 的 `getattr` | — | ✓ | — |
| `RESEND_FINAL_ON_EMPTY_STREAM_FALLBACK` | `gateway/stream_consumer.py:1377` 的 `getattr` | — | ✓ | — |
| `_create_dm_topic` / `ensure_dm_topic` / `rename_dm_topic` | `gateway/run.py:19729` 的 `getattr` | — | ✓ | — |
| `rename_thread` / `refresh_skill_group` / `_resolve_channel_prompt` / `_voice_sources` | `gateway/run.py:19922` 的 `getattr` | ✓ | — | — |
| `_bot` | `gateway/run.py:19697` 的 `getattr` | — | ✓ | — |
| `_client` | `gateway/channel_directory.py:219` 的 `getattr` | ✓ | — | — |
| `_team_clients` | `gateway/channel_directory.py:305` 的 `getattr` | — | — | ✓ |

**余下 24 个非基类钩子三家都没有,但它们不是死代码** —— 实现方在别的适配器里。
抽查五个(搜索面:`git grep -n "def <名>" -- '*.py'`,排除 `hermes_agent-0.20.0/` 影子副本):

| 钩子 | 实现方(锚点 + 摘录) |
|---|---|
| `auto_thread_info_for_chat` | `gateway/relay/adapter.py:1002`:`    def auto_thread_info_for_chat(` |
| `go_dormant` | `gateway/relay/adapter.py:872`:`    async def go_dormant(self) -> bool:` |
| `active_agent_work_count` | `gateway/platforms/api_server.py:1460`:`    def active_agent_work_count(self) -> int:` |
| `list_channels` | `plugins/platforms/simplex/adapter.py:860`:`    async def list_channels(self) -> Optional[List[Dict[str, Any]]]:` |
| `dispatch_http_event` | `plugins/platforms/google_chat/adapter.py:1495`:`    async def dispatch_http_event(self, envelope: Dict[str, Any]) -> Dict[str, Any]:` |

**探针口径要说清**(判据:同一指标多方法测量必须分别标注):本探针只认
`getattr(<变量>, "<字面量>", …)` 且 `<变量>` 名在一份 11 项的白名单里
(`adapter` / `_adapter` / `self._adapter` / …)。**这是下界不是全集**:
`getattr` 用变量作键、或宿主写 `hasattr` / `try: adapter.x`,本探针都够不到。
探针初版还有一个真 bug:只认 `ast.Assign` 不认 `ast.AnnAssign`,于是基类里
`self._pending_messages: Dict[str, MessageEvent] = {}` 这类**带类型标注的实例属性**
被全判成「基类没有」,`NOT in base` 虚高了 6 条(41 → 35)。已修,见
`data/r11f/probes/a_duck_hooks.py` 里 `_names_of_class` 的注释。

### 2.4 插件 → 宿主注册面 —— `ctx.register_platform(...)`

这是插件把自己交给宿主的**唯一**入口。三家的 `register(ctx)` 结构完全同型:

`plugins/platforms/telegram/adapter.py:10128 @ 863e313`

```
def register(ctx) -> None:
    """Plugin entry point — called by the Hermes plugin system."""
    ctx.register_platform(
        name="telegram",
        label="Telegram",
        adapter_factory=_build_adapter,
        check_fn=check_telegram_requirements,
        is_connected=_is_connected,
        required_env=["TELEGRAM_BOT_TOKEN"],
        install_hint="Run `hermes setup` to install Telegram support.",
        setup_fn=interactive_setup,
        apply_yaml_config_fn=_apply_yaml_config,
        allowed_users_env="TELEGRAM_ALLOWED_USERS",
        allow_all_env="TELEGRAM_ALLOW_ALL_USERS",
        cron_deliver_env_var="TELEGRAM_HOME_CHANNEL",
        standalone_sender_fn=_standalone_send,
        max_message_length=4096,
        emoji="✈️",
        allow_update_command=True,
    )
```

可传键的**完整**集合来自 `PlatformEntry` 数据类 —— `register_platform` 只显式吃 7 个形参,
其余走 `**entry_kwargs` 原样转发给 dataclass 构造器,**未知键当场 TypeError**,
所以字段表就是完整可传键集,没有隐藏入口。

`hermes_cli/plugins.py:970 @ 863e313`

```
        Extra keyword arguments are forwarded to ``PlatformEntry`` (e.g.
        ``setup_fn``, ``emoji``, ``allowed_users_env``, ``platform_hint``).
        Unknown keys raise TypeError from the dataclass constructor.
```

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/a_register_seam.py
```

```text
ENTRY gateway/platform_registry.py::PlatformEntry  fields=22 plugin_passable=21 (host-set: source)
discord   plugins/platforms/discord/adapter.py:10105  passed=16 omitted=5 unknown=0
  passed : adapter_factory allow_all_env allow_update_command allowed_users_env apply_yaml_config_fn check_fn cron_deliver_env_var emoji install_hint is_connected label max_message_length name required_env setup_fn standalone_sender_fn
  omitted: validate_config plugin_name pii_safe platform_hint env_enablement_fn
telegram  plugins/platforms/telegram/adapter.py:10130  passed=16 omitted=5 unknown=0
  passed : adapter_factory allow_all_env allow_update_command allowed_users_env apply_yaml_config_fn check_fn cron_deliver_env_var emoji install_hint is_connected label max_message_length name required_env setup_fn standalone_sender_fn
  omitted: validate_config plugin_name pii_safe platform_hint env_enablement_fn
slack     plugins/platforms/slack/adapter.py:9054  passed=16 omitted=5 unknown=0
  passed : adapter_factory allow_all_env allow_update_command allowed_users_env apply_yaml_config_fn check_fn cron_deliver_env_var emoji install_hint is_connected label max_message_length name required_env setup_fn standalone_sender_fn
  omitted: validate_config plugin_name pii_safe platform_hint env_enablement_fn
COMMON   三家都传的键 = 16: adapter_factory allow_all_env allow_update_command allowed_users_env apply_yaml_config_fn check_fn cron_deliver_env_var emoji install_hint is_connected label max_message_length name required_env setup_fn standalone_sender_fn
ONLY-discord   (无)
ONLY-telegram  (无)
ONLY-slack     (无)
```

**结论(横向对比的第一条)**:**注册面在三家之间是零差异的** —— 同样 16 个键、
同样省略 5 个、没有任何一家多传或少传。三家全部差异都在 ABC 实现体与平台侧,
**接口面本身完全收敛**。全表(22 字段 × 三家取值)在 `data/r11f/a/register-platform-matrix.tsv`。

只有取值不同的四格值得记:

| 字段 | discord | telegram | slack |
|---|---|---|---|
| `max_message_length` | `2000` | `4096` | `39000` |
| `emoji` | `'🎮'` | `'✈️'` | `'💼'` |
| `required_env` | 1 条 | 1 条 | **2 条** |
| `check_fn` | `check_discord_requirements` | `check_telegram_requirements` | `check_slack_requirements` |

三家共同省略的 5 个键 = `validate_config` `plugin_name` `pii_safe` `platform_hint`
`env_enablement_fn`。其中 `plugin_name` 由宿主自己补默认值。

`hermes_cli/plugins.py:987 @ 863e313`

```
        entry_kwargs.setdefault("plugin_name", self.manifest.name)
```

### 2.5 `plugin.yaml` 清单面

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/a_manifest_and_env.py --mode=manifest
```

```text
== plugins/platforms/discord/plugin.yaml
   top_keys(8): author description kind label name optional_env requires_env version
   requires_env: DISCORD_BOT_TOKEN  [description password prompt url]
   optional_env: DISCORD_ALLOWED_USERS  [description password prompt]
   optional_env: DISCORD_ALLOW_ALL_USERS  [description password prompt]
   optional_env: DISCORD_HOME_CHANNEL  [description password prompt]
   optional_env: DISCORD_HOME_CHANNEL_NAME  [description password prompt]
== plugins/platforms/telegram/plugin.yaml
   top_keys(8): author description kind label name optional_env requires_env version
   requires_env: TELEGRAM_BOT_TOKEN  [description password prompt url]
   optional_env: TELEGRAM_ALLOWED_USERS  [description password prompt]
   optional_env: TELEGRAM_ALLOW_ALL_USERS  [description password prompt]
   optional_env: TELEGRAM_HOME_CHANNEL  [description password prompt]
   optional_env: TELEGRAM_HOME_CHANNEL_NAME  [description password prompt]
== plugins/platforms/slack/plugin.yaml
   top_keys(8): author description kind label name optional_env requires_env version
   requires_env: SLACK_BOT_TOKEN  [description password prompt url]
   requires_env: SLACK_APP_TOKEN  [description password prompt url]
   optional_env: SLACK_ALLOWED_USERS  [description password prompt]
   optional_env: SLACK_ALLOW_ALL_USERS  [description password prompt]
   optional_env: SLACK_HOME_CHANNEL  [description password prompt]
   optional_env: SLACK_HOME_CHANNEL_NAME  [description password prompt]
   optional_env: SLACK_THREAD_REQUIRE_MENTION  [description password prompt]
```

**三份 manifest 的顶层键集完全相同,都是这 8 个**:`name` `label` `kind` `version`
`description` `author` `requires_env` `optional_env`。派工书列的全仓 15 个顶层键里,
本片三份**一个都没用到**的有 7 个:`hooks` `provides_web_providers` `pip_dependencies`
`provides_browser_providers` `platforms` `provides_tools` `external_dependencies`。
即:**平台型插件不往宿主注册工具/Web provider/浏览器 provider**,它们的注册全部走
§2.4 的 `ctx.register_platform`,不走 manifest 声明。

**env 子字段面**(设置向导的输入面)逐条列全,共 **16 条** env(1+4 / 1+4 / 2+5):
`requires_env` 的 3 条都带 `url`(引导用户去哪儿开 token)且 `password: true`;
`optional_env` 的 13 条都不带 `url` 且 `password: false`。**只有 `requires_env` 用 `url`,
只有 `requires_env` 是密文** —— 这两条在三份 manifest 上是一致的,构成一条隐式约定。

Slack 是三家里唯一需要**两个** token 的:Socket Mode 要 bot token(`xoxb-`)
调 Web API,还要 app-level token(`xapp-`,scope `connections:write`)开 WebSocket。

`plugins/platforms/slack/plugin.yaml:18 @ 863e313`

```
  - name: SLACK_APP_TOKEN
    description: "Slack app-level token for Socket Mode (xapp-..., scope connections:write)"
    prompt: "Slack App Token (xapp-...)"
    url: "https://api.slack.com/apps"
    password: true
```

Slack 也是唯一多出一条 `optional_env` 的(`SLACK_THREAD_REQUIRE_MENTION`),
而 discord 有等价的 `DISCORD_THREAD_REQUIRE_MENTION` **却没有**写进 manifest —— 见 §2.6。

### 2.6 环境变量面 + `config.yaml` → env 桥

manifest 只声明 5 / 5 / 7 条 env,而适配器实际读的远不止。两个口径分别报:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/a_manifest_and_env.py --mode=summary
```

```text
discord   manifest_keys=8 requires_env=1 optional_env=4 literal=34 envcall=25 undeclared_literal=30 undeclared_envcall=23
telegram  manifest_keys=8 requires_env=1 optional_env=4 literal=24 envcall=20 undeclared_literal=20 undeclared_envcall=19
slack     manifest_keys=8 requires_env=2 optional_env=5 literal=21 envcall=17 undeclared_literal=15 undeclared_envcall=14
```

**两个口径必须分别标注**(不是同一测量做了两遍):
- `literal` = 平台目录下**任意字符串字面量**形如 `<PREFIX>_[A-Z0-9_]+`。**宽**:能抓到先塞进
  常量元组、再循环读的名字 —— discord 的门控键就是这样一张表:

`plugins/platforms/discord/adapter.py:383 @ 863e313`

```
_GATE_ENV_KEYS = (
    "DISCORD_ALLOWED_USERS",
    "DISCORD_ALLOWED_ROLES",
    "DISCORD_ALLOWED_CHANNELS",
    "DISCORD_IGNORED_CHANNELS",
    "DISCORD_NO_THREAD_CHANNELS",
    "DISCORD_FREE_RESPONSE_CHANNELS",
    "DISCORD_MISSED_MESSAGE_BACKFILL_CHANNELS",
```

  宽口径的代价是误吞同形状的非 env 字面量 —— 全片实测 **1 处**:`SLACK_AVAILABLE`
  其实是模块注入命名空间的**字典键**,不是环境变量。

`plugins/platforms/slack/adapter.py:301 @ 863e313`

```
        return {
            "AsyncApp": AsyncApp,
            "AsyncSocketModeHandler": AsyncSocketModeHandler,
            "AsyncWebClient": AsyncWebClient,
            "aiohttp": aiohttp,
            "SLACK_AVAILABLE": True,
        }
```

- `envcall` = 只认直接出现在 `os.getenv(...)` / `os.environ.get(...)` / `os.environ[...]` /
  `_env_bool(...)` 里的字面量。**窄**:漏掉上面那种常量表间接读法。

**「manifest 没声明」不等于「用户配不了」**:第三条入口是 `apply_yaml_config_fn`,
把 `config.yaml` 的 `<platform>:` 段翻译成 `os.environ[...]` 写入。

`plugins/platforms/discord/adapter.py:9903 @ 863e313`

```
    The DiscordAdapter reads its runtime configuration via ``os.getenv()``
    throughout the connect / handle code paths (``DISCORD_ALLOWED_USERS``,
    ``DISCORD_REQUIRE_MENTION``, ``DISCORD_FREE_RESPONSE_CHANNELS``,
    ``DISCORD_AUTO_THREAD``, ``DISCORD_REACTIONS``,
    ``DISCORD_IGNORED_CHANNELS``, ``DISCORD_ALLOWED_CHANNELS``,
    ``DISCORD_NO_THREAD_CHANNELS``, ``DISCORD_HISTORY_BACKFILL``,
    ``DISCORD_HISTORY_BACKFILL_LIMIT``, ``DISCORD_ALLOW_MENTION_*``,
    ``DISCORD_REPLY_TO_MODE``, ``DISCORD_THREAD_REQUIRE_MENTION``,
    ``DISCORD_BOTS_REQUIRE_INLINE_MENTION``).
    Rather than rewrite ~50 call sites inside the adapter to read from
    ``PlatformConfig.extra`` instead, this hook keeps the existing
    env-driven model and merely owns the YAML→env translation here, next to
    the adapter that consumes it.
```

三条入口的收支:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/a_yaml_env_bridge.py
```

```text
discord   manifest_env=5 yaml_bridge_env=16 yaml_keys=21 adapter_reads=25 env_only=9
telegram  manifest_env=5 yaml_bridge_env=17 yaml_keys=19 adapter_reads=20 env_only=3
slack     manifest_env=7 yaml_bridge_env=13 yaml_keys=13 adapter_reads=17 env_only=2
```

**`env_only`** = 既不在 manifest、也不由 YAML 桥写入的 env,**只能靠直接设环境变量**。
逐条列全(14 条,全表 `data/r11f/a/yaml-env-bridge.tsv`):

| 平台 | env-only 逐条 |
|---|---|
| discord(9) | `DISCORD_ALLOW_ANY_ATTACHMENT` `DISCORD_COMMAND_SYNC_POLICY` `DISCORD_HIDE_SLASH_COMMANDS` `DISCORD_IGNORE_NO_MENTION` `DISCORD_MAX_ATTACHMENT_BYTES` `DISCORD_MISSED_MESSAGE_BACKFILL` `DISCORD_MISSED_MESSAGE_BACKFILL_LIMIT` `DISCORD_MISSED_MESSAGE_BACKFILL_MAX_DISPATCHES` `DISCORD_MISSED_MESSAGE_BACKFILL_WINDOW_SECONDS` |
| telegram(3) | `TELEGRAM_WEBHOOK_HOST` `TELEGRAM_WEBHOOK_SECRET` `TELEGRAM_WEBHOOK_URL` |
| slack(2) | `SLACK_DEDUP_TTL_SECONDS` `SLACK_MENTION_PATTERNS` |

**横向读法**:discord 的 env-only 是三家最多的,而且整整 4 条是同一族
(`MISSED_MESSAGE_BACKFILL*`,断线补投)—— 一个**完整子系统**没有 YAML 入口。
telegram 的 3 条全是 webhook 模式的(它默认走 long-poll,webhook 是次要路径)。
slack 只有 2 条,配置面最收敛。

### 2.7 平台侧交互入口面(向平台注册的命令 / 事件 / 按钮)

**这是三家分歧最大的接缝 —— 同一件事三种做法。**

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/a_interaction_surface.py
```

```text
DISCORD  slash=27 client_event=3 ui_view=6 ui_button=9
TELEGRAM add_handler=10 callback_prefix_produced=13 callback_prefix_consumed=14 consumed_only=1
  consumed-but-never-produced: gt
  produced-but-never-consumed: (无)
SLACK    event=12 command=1 action_direct=6 action_via_loop=7
```

全表:`data/r11f/a/{discord,telegram,slack}-interaction.tsv`(45 / 37 / 21 行)。

#### 2.7.1 命令注册:一份注册表,三种投影

三家的命令**来源是同一个**注册表,但投影方式完全不同。

`hermes_cli/commands.py:102 @ 863e313`

```
COMMAND_REGISTRY: list[CommandDef] = [
    # Session
    CommandDef("start", "Acknowledge platform start pings without a reply", "Session",
               gateway_only=True, busy_policy="dispatch", busy_handler="start"),
```

**discord —— 27 个手写装饰器打底,再从注册表自动补齐。**

`plugins/platforms/discord/adapter.py:5427 @ 863e313`

```
    def _register_slash_commands(self) -> None:
        """Register Discord slash commands on the command tree."""
        if not self._client:
            return

        tree = self._client.tree

        @tree.command(name="new", description="Start a new conversation")
        async def slash_new(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/reset", "New conversation started~")
```

27 条手写的逐项(名字 / 描述 / 锚点全表见 `data/r11f/a/discord-interaction.tsv`):
`/new` `/reset` `/model` `/reasoning` `/personality` `/retry` `/undo` `/status` `/sethome`
`/stop` `/steer` `/compress` `/title` `/resume` `/usage` `/help` `/insights` `/reload-mcp`
`/reload-skills` `/voice` `/update` `/restart` `/approve` `/deny` `/thread` `/queue` `/background`。
手写的价值是**只有它们能带 Discord 的富参数 UI** —— `app_commands.describe`(参数提示)
与 `app_commands.choices`(下拉枚举);`/reasoning` 一条就挂了 11 个 Choice。
手写之外再从注册表自动补,并给自己留一格:

`plugins/platforms/discord/adapter.py:5635 @ 863e313`

```
        # Native commands above are registered first and are the highest
        # priority, so they always survive the 100-command cap. Reserve one
        # slot for the consolidated ``/skill`` group registered further below.
        slot_cap = _DISCORD_MAX_APP_COMMANDS - 1
```

**telegram —— 纯投影,没有一条手写。** 注册表 → `telegram_menu_commands()` → `BotCommand`
列表 → 对三个 scope 各调一次 `set_my_commands`。

`plugins/platforms/telegram/adapter.py:3605 @ 863e313`

```
                # Telegram allows up to 100 commands but has an undocumented
                # payload size limit (~4KB total).  Hermes defaults to 60 to
                # keep built-ins plus common skill commands visible while
                # staying under the threshold; users can tune the cap via
                # platforms.telegram.extra.command_menu.
                max_commands = telegram_menu_max_commands()
                menu_commands, hidden_count = telegram_menu_commands(max_commands=max_commands)
                bot_commands = [BotCommand(name, desc) for name, desc in menu_commands]
                # Register for all scopes independently — Telegram picks the
                # narrowest matching scope per chat type (forum topics fall
                # through to AllGroupChats or Default).
                for scope_cls in (BotCommandScopeDefault, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats):
```

**slack —— 一个正则匹配器吃掉全部命令。** 不是 N 个装饰器,是 1 个。

`plugins/platforms/slack/adapter.py:2057 @ 863e313`

```
            _slash_names = [name for name, _d, _h in slack_native_slashes()]
            if _slash_names:
                _slash_pattern = _re.compile(
                    r"^/(?:" + "|".join(_re.escape(n) for n in _slash_names) + r")$"
                )
            else:  # pragma: no cover - registry always non-empty
                _slash_pattern = _re.compile(r"^/hermes$")

            @self._app.command(_slash_pattern)
```

Slack 这条路还有一个**平台侧前置条件**,写在紧邻的注释里:命令必须**同时**声明在
Slack app manifest 里,否则 Socket Mode 根本不会投递该事件 —— 代码注册得再全也没用。

`plugins/platforms/slack/adapter.py:2049 @ 863e313`

```
            # The slash commands must ALSO be declared in the Slack app
            # manifest (see `hermes slack manifest`). In Socket Mode, Slack
            # routes the command event through the socket regardless of the
            # manifest's request URL, but it will not deliver an event for
            # a slash command the manifest doesn't declare.
```

**三种投影的取舍**:

| | discord | telegram | slack |
|---|---|---|---|
| 注册粒度 | 每命令一个装饰器(27)+ 自动补 | 一次性提交整张菜单 | 一个正则匹配全部 |
| 上限 | 100(`plugins/platforms/discord/adapter.py:85`:`_DISCORD_MAX_APP_COMMANDS = 100`) | 100 硬上限,默认自限 60(~4KB payload) | 无代码侧上限,受 app manifest 约束 |
| 富参数 UI | 有(`describe` / `choices`) | 无(只有 name+desc) | 无(文本 payload) |
| 超限行为 | 计 `dropped_over_cap` 静默丢弃 | `hidden_count` 计数并记日志 | 不适用 |
| 平台侧前置条件 | 需 command sync(`DISCORD_COMMAND_SYNC_POLICY`) | 无 | **必须**在 app manifest 声明 |

#### 2.7.2 入站事件订阅面

| discord(3,`@self._client.event`) | telegram(10,`add_handler`) | slack(12,`@self._app.event`) |
|---|---|---|
| `on_ready` `plugins/platforms/discord/adapter.py:1329` 的 `@self._client.event` | `TelegramMessageHandler` × 4 + `CallbackQueryHandler` × 1,**注册两遍**(冷启 `:3876`、重连 `:4008`) | `message` `app_mention` `app_home_opened` `app_context_changed` `file_shared` `file_created` `file_change` `reaction_added` `reaction_removed` `assistant_thread_started` `assistant_thread_context_changed` + 兜底正则 |
| `on_message` `plugins/platforms/discord/adapter.py:1345` 的 `async def on_message` | 按 `filters` 分流:`TEXT & ~COMMAND` / `COMMAND` / `LOCATION|VENUE` / 媒体五合一 | 兜底那条是 `plugins/platforms/slack/adapter.py:2028` 的 `@self._app.event(re.compile(r".*"))` |
| `on_voice_state_update` `plugins/platforms/discord/adapter.py:1349` 的 `async def on_voice_state_update` | | |

**Slack 的兜底事件处理器是一个真实事故的产物,值得单独讲**(判据:事故讲成故事)。
现象:接了 `user_change` 这类高频事件的 Slack app,在大型 workspace 里每个成员改一次状态
就触发一次;slack-bolt 对**没有匹配监听器**的事件返回 HTTP 404 且**永不发 Socket Mode ack**。
Slack 侧统计到失败率超过「60 分钟内 95%」的阈值,就**自动关停该 app 的 Event Subscriptions**
—— 所有入站消息静默死亡,直到有人手工去后台重开。修法不是去改订阅列表,而是在**所有具名
监听器之后**注册一个匹配 `.*` 的空 ack(bolt 派发给第一个匹配者,所以具名的永远优先)。

`plugins/platforms/slack/adapter.py:2008 @ 863e313`

```
            #   1. Correctness at scale: without a matching listener,
            #      slack-bolt returns HTTP 404 for every unhandled event
            #      envelope and never sends the Socket Mode ack. When the app
            #      is subscribed to high-volume events (user_change fires on
            #      every presence/status change for the whole org), the flood
            #      of un-acked 404s pushes Slack's failure rate past its
            #      95%/60-min threshold and Slack auto-disables the app's
            #      Event Subscriptions — silently killing ALL inbound
            #      delivery until manually re-enabled.
```

#### 2.7.3 按钮 / 交互组件面

| | discord | telegram | slack |
|---|---|---|---|
| 原语 | `discord.ui.View` + `@discord.ui.button` | `InlineKeyboardButton(callback_data=...)` | Block Kit `action_id` |
| 数量 | 6 个 View / 9 个按钮 | 13 个 `callback_data` 前缀 | 6 个直接 + 7 个循环注册 = 13 个 action_id |
| 路由 | 对象方法(按钮绑在 View 实例上) | **字符串前缀**,单一 `CallbackQueryHandler` 分发 | action_id 字符串或正则 |
| 生命周期 | View 有 `on_timeout`(6 处) | 无超时,靠前缀 + 校验 | 无超时 |

discord 6 个 View 逐项:`ExecApprovalView`(`:8372`)`SlashConfirmView`(`:8535`)
`UpdatePromptView`(`:8650`)`ModelPickerView`(`:8746`)`ChoicePickerView`(`:9076`)
`ClarifyChoiceView`(`:9167`);9 个按钮:`Allow Once` `Allow Session` `Always Allow` `Deny`
`Approve Once` `Always Approve` `Cancel` `Yes` `No`。

telegram 13 个前缀逐项(产出侧):`cl` `cp` `ea` `mb` `mc` `mg` `mm` `mp` `mpg` `mpv` `mx` `sc`
`update_prompt`。**消费侧多一个 `gt`** —— 见 §5 的 ◇。

slack 13 个 action_id 逐项:前 4 个用一个常量元组循环注册 ——

`plugins/platforms/slack/adapter.py:2074 @ 863e313`

```
            # Register Block Kit action handlers for approval buttons
            for _action_id in (
                "hermes_approve_once",
                "hermes_approve_session",
                "hermes_approve_always",
                "hermes_deny",
            ):
                self._app.action(_action_id)(self._handle_approval_action)
```

其余 9 个:`hermes_confirm_once` `hermes_confirm_always` `hermes_confirm_cancel`(同款循环,`:2085`)、
`hermes_feedback`(`:2092`)、`^hermes_clarify_choice_\d+$`(正则,`:2098`)、
`hermes_clarify_other`(`:2101`),外加**插件注册的**那一路(`:2145`,数量运行期才定)。

**slack 独有第 14 类入口:插件可以注册自己的 Block Kit action。**

`plugins/platforms/slack/adapter.py:2103 @ 863e313`

```
            # Register plugin-provided Block Kit action handlers.
            #
            # Plugins call ``ctx.register_slack_action_handler(action_id, cb)``
            # at register() time; the manager queues them and the adapter
            # wires them into AsyncApp here so slack_bolt's matcher knows
            # about them before Socket Mode starts dispatching events.
```

这是**平台特有的插件二级注册面**,宿主侧有专门的一个 `PluginContext` 方法接它:

`hermes_cli/plugins.py:1009 @ 863e313`

```
    def register_slack_action_handler(
        self,
        action_id: Any,
        callback: Callable,
    ) -> None:
        """Register a Slack Block Kit action handler from a plugin.
```

discord / telegram 没有对应物 —— 它们的按钮由
适配器自己造,插件插不进去。

### 2.8 依赖面 —— `plugin.yaml` 不写,`lazy_deps` 写

三份 manifest 都没有 `pip_dependencies`。依赖在 `tools/lazy_deps.py` 里按
`platform.<name>` 键登记,由 `check_fn` 首次调用时惰性安装。

`tools/lazy_deps.py:206 @ 863e313`

```
    "platform.telegram": ("python-telegram-bot[webhooks]==22.6",),
```

`tools/lazy_deps.py:221 @ 863e313`

```
    "platform.slack": (
        "slack-bolt==1.29.0",
        "slack-sdk==3.43.0",
        "aiohttp==3.14.1",  # CVE-2026-34513/34518/34519/34520/34525 + 34993(RCE)/47265
    ),
```

`plugins/platforms/discord/adapter.py:435 @ 863e313`

```
def check_discord_requirements() -> bool:
    """Check if Discord dependencies are available.

    Lazy-installs discord.py via ``tools.lazy_deps.ensure("platform.discord")``
    on first call if not present. After successful install, re-binds module
    globals so ``DISCORD_AVAILABLE`` becomes True.
    """
```

**这正是本项目「惰性安装纪律」要防的形状**:`check_fn` 是宿主在**列举可用平台**时就会调的,
于是「问一句 Discord 能不能用」这个动作可以联网 pip 装包并改变当前 venv。本片全部命令
都带 `HERMES_DISABLE_LAZY_INSTALLS=1`,且**所有探针只做 AST 静态解析、不 import 基线任何模块**。

与 `pyproject.toml` 的 extra 对应关系有一处**不对称**,值得记:

| 平台 | `pyproject.toml` 独立 extra | 只在 `messaging` 里 |
|---|---|---|
| discord | 无 | ✓ `pyproject.toml:176` 的 `discord.py[voice]==2.7.1` |
| telegram | 无 | ✓ `pyproject.toml:176` 的 `python-telegram-bot[webhooks]==22.6` |
| slack | **有**(`pyproject.toml:178`:`slack = ["slack-bolt==1.29.0", "slack-sdk==3.43.0", "aiohttp==3.14.1"]`) | 也在 |

即 `pip install hermes-agent[slack]` 装得到 Slack,但**没有** `[discord]` / `[telegram]`
这两个 extra,只能装整个 `[messaging]` 或依赖惰性安装。

---

## 3. 判据 3:一条端到端链(Slack `@bot` 提问 → 回到同一线程)

场景:用户在 `#eng` 频道发 `@hermes 帮我看看昨天的构建为什么挂了`。逐跳:

| # | 跳 | 锚点 |
|---|---|---|
| 1 | Slack 通过 Socket Mode 投来 `app_mention` 事件 | `plugins/platforms/slack/adapter.py:1952` 的 `@self._app.event("app_mention")` |
| 2 | 转交统一入口(与 `message` 事件共用,靠去重防双触发) | `plugins/platforms/slack/adapter.py:1954` 的 `await self._handle_slack_message(event, body)` |
| 3 | 过滤 / 鉴权 / 取媒体 / 判 mention 门控 | `plugins/platforms/slack/adapter.py:5228` 的 `async def _handle_slack_message` |
| 4 | 组装平台无关的 `MessageEvent`,把 `thread_ts` 记进 metadata | `plugins/platforms/slack/adapter.py:6281` 的 `msg_event = MessageEvent(` |
| 5 | 交回基类 | `plugins/platforms/slack/adapter.py:6344` 的 `await self.handle_message(msg_event)` |
| 6 | 基类分派(快速返回,后台起任务,保证新消息仍可打断) | `gateway/platforms/base.py:5554` 的 `async def handle_message` |
| 7 | 调用宿主注入的处理器 | `gateway/platforms/base.py:5838` 的 `response = await self._message_handler(event)` |
| 8 | 该处理器由 GatewayRunner 在挂载适配器时注入 | `gateway/run.py:11093` 的 `adapter.set_message_handler(self._primary_message_handler())` |
| 9 | 非多路复用时它就是 `GatewayRunner._handle_message` → agent 一轮 | `gateway/run.py:13625` 的 `def _primary_message_handler` |
| 10 | 回文落回基类的发送路径 | `gateway/platforms/base.py:6091` 的 `result = await delivery_adapter._send_with_retry(` |
| 11 | 重试壳先调抽象 `send` | `gateway/platforms/base.py:5060` 的 `result = await self.send(` |
| 12 | 回到 Slack 实现 | `plugins/platforms/slack/adapter.py:2439` 的 `async def send` |
| 13 | 把 `reply_to` 还原成 `thread_ts`(回到原线程而不是频道底部) | `plugins/platforms/slack/adapter.py:2527` 的 `thread_ts = self._resolve_thread_ts(reply_to, metadata)` |
| 14 | 发出 | `plugins/platforms/slack/adapter.py:2558` 的 `).chat_postMessage(**kwargs)` |

第 5 跳是**整条链的收腰处**:适配器把平台报文翻成 `MessageEvent` 之后,
再往下一行代码都不知道这是 Slack。

`plugins/platforms/slack/adapter.py:6281 @ 863e313`

```
        msg_event = MessageEvent(
            text=(command_probe_text if is_command_text else text),
            message_type=msg_type,
            source=source,
            raw_message=event,
            message_id=ts,
            media_urls=media_urls,
            media_types=media_types,
            reply_to_message_id=thread_ts if thread_ts != ts else None,
            channel_prompt=_channel_prompt,
            channel_context=channel_context,
            reply_to_text=reply_to_text,
            auto_skill=_auto_skill,
            metadata={
                "slack_team_id": team_id,
                "slack_channel_id": channel_id,
                "slack_thread_ts": thread_ts,
            },
        )
```

平台专属的东西只剩两处:`raw_message`(原样保留报文)与 `metadata` 里三个 `slack_*` 键。
第 13 跳靠的正是 `slack_thread_ts` 这一格 —— **线程归属信息穿过整个平台无关内核,
在出口处被还原**。这是本仓库处理「平台特性」的通用手法:不给内核加平台分支,
而是让平台自己带一个不透明口袋进去、出来时自己掏。

---

## 4. 判据 4:逐字取证

本底稿的**无语言标记**围栏块 ```` ``` ```` **全部**是基线逐字摘录(整块每一行),分布在
§2.1 / §2.2 / §2.4 / §2.5 / §2.6 / §2.7 / §2.8 / §3 / §5;```` ```verify ```` 与 ```` ```text ````
是声明式非源码块(命令与它的输出),`>` 引用块是文档摘录。判据 4 只要求 2 个,本片明确点名三处:

| 处 | 锚点 + 首行摘录 | 为什么选它 |
|---|---|---|
| §2.7.1 | `plugins/platforms/slack/adapter.py:2057`:`            _slash_names = [name for name, _d, _h in slack_native_slashes()]` | Slack 用**一个正则**吃掉全部 slash,与 discord 的 27 个装饰器构成本片最强对比 |
| §2.4 | `plugins/platforms/telegram/adapter.py:10128`:`def register(ctx) -> None:` | 插件交给宿主的唯一入口,20 行全文逐字 |
| §3 | `plugins/platforms/slack/adapter.py:6281`:`        msg_event = MessageEvent(` | 端到端链的收腰处,平台报文在这一行之后消失 |

---

## 5. 判据 5:记号

### ▲(地图级,1 条)—— `H-R11F-A-a`

**`website/docs` 把 `get_chat_info()` 标成「optional override」,而代码里它是 `@abstractmethod`。**

文档侧。按 CLAUDE.md 的要求,先定这条断言归哪个标题管、整段说了什么:

| 层级 | 锚点 + 摘录 |
|---|---|
| 归属标题 | `website/docs/developer-guide/adding-platform-adapters.md:14`:`## Architecture Overview` |
| 主句 | `website/docs/developer-guide/adding-platform-adapters.md:21`:`Every adapter extends` |

主句之后是五个 bullet,前三个标 `*(abstract)*`、后两个标 `(optional override)`:

`website/docs/developer-guide/adding-platform-adapters.md:23 @ 863e313`

> - **`connect()`** — Establish connection (WebSocket, long-poll, HTTP server, etc.) *(abstract)*
> - **`disconnect()`** — Clean shutdown *(abstract)*
> - **`send()`** — Send a text message to a chat *(abstract)*
> - **`send_typing()`** — Show typing indicator (optional override)
> - **`get_chat_info()`** — Return chat metadata (optional override)

代码侧:

`gateway/platforms/base.py:6670 @ 863e313`

```
    @abstractmethod
    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
```

```verify
grep -n -B1 "async def get_chat_info" /home/user/hermes-agent/gateway/platforms/base.py; grep -n "get_chat_info()" /home/user/hermes-agent/website/docs/developer-guide/adding-platform-adapters.md
```

```text
6670-    @abstractmethod
6671:    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
27:- **`get_chat_info()`** — Return chat metadata (optional override)
```

**为什么是真矛盾而不是措辞松**:`send_typing` 那一条是对的(基类有具体实现,不写也能跑);
`get_chat_info` 不写则**类根本无法实例化**(Python ABC 在 `__init__` 前就抛 `TypeError`)。
照这份 bullet 写一个「省掉 get_chat_info」的最小适配器,启动即崩。

同一页的代码模板反而是对的 —— 它把四个抽象方法一个不落地写全了:

`website/docs/developer-guide/adding-platform-adapters.md:88 @ 863e313`

>     async def send(self, chat_id, content, reply_to=None, metadata=None):
>         # Send message via platform API
>         return SendResult(success=True, message_id="...")
>
>     async def get_chat_info(self, chat_id):
>         return {"name": chat_id, "type": "dm"}

**所以照抄模板的人不会踩坑,只有照读 bullet 列表的人会** —— 这正是「文档的层级结构本身
就是断言的一部分」那条规矩要防的形状:同一份文档里,概览段落与代码模板给出了相反的契约。

**全仓无一例外**(负结论,搜索面写明):对 `plugins/platforms/*/adapter.py` 里
**全部**直接继承 `BasePlatformAdapter` 的类做 AST 检查,`connect`/`disconnect`/`send`/`get_chat_info`
四个方法**一个都不缺**。搜索面 = `plugins/platforms/*/adapter.py` 的一层 glob
(不含 `gateway/platforms/` 的内置适配器,不含 `tests/`,不含影子副本 `hermes_agent-0.20.0/`);
判据 = 类的 `bases` 里有名为 `BasePlatformAdapter` 的 `ast.Name`(**不认**别名 import 与
带点的属性写法,这是本口径的已知下界)。

```verify
cd /home/user/hermes-agent && python3 -c "
import ast, pathlib
miss, tot = [], 0
for p in sorted(pathlib.Path('.').glob('plugins/platforms/*/adapter.py')):
    for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
        if isinstance(n, ast.ClassDef) and any(isinstance(b, ast.Name) and b.id=='BasePlatformAdapter' for b in n.bases):
            tot += 1
            names = {i.name for i in n.body if isinstance(i,(ast.FunctionDef, ast.AsyncFunctionDef))}
            gone = sorted({'connect','disconnect','send','get_chat_info'} - names)
            if gone: miss.append(f'{p}:{n.lineno} {n.name} missing={\" \".join(gone)}')
print('BasePlatformAdapter subclasses in plugins/platforms:', tot)
print('missing at least one abstract method:', len(miss))
for m in miss: print(' ', m)
"
```

```text
BasePlatformAdapter subclasses in plugins/platforms: 22
missing at least one abstract method: 0
```

### ▲(码内,1 条)—— `H-R11F-A-b`

**`telegram_ids.py` 的注释声称用户名下界是 5,而紧邻的正则写的是 4。**

`plugins/platforms/telegram/telegram_ids.py:17 @ 863e313`

```
# Telegram usernames are 5-32 chars: letters, digits, underscores, with a
# leading "@". (Telegram also permits 4-char usernames for some legacy/official
# accounts, but the 5-32 public rule is the safe lower bound for routing.)
_TELEGRAM_USERNAME_RE = re.compile(r"@[A-Za-z0-9_]{4,32}")
```

注释的括号句明写「**虽然**平台也允许 4 字符用户名,**但**这里采用 5-32 这条公开规则作为
安全下界」——它在陈述**代码做了什么选择**,而代码下一行就用了 `{4,32}`。三句里的每一句
单独看都为真(平台规则是 5-32、确实存在 4 字符遗留账号),**错的是它对自身实现的描述**,
所以不是「保守但为真」的 ◎,是矛盾。

影响面很小(放宽而非收紧,只是多认了一类合法账号),但它正是**人工评审抓不住、
机器也没在查**的那一类:注释与它下面那一行之间没有任何校验。
按 CLAUDE.md 记 **▲(码内)**,与地图级 ▲ 分两行计数。

### ◇(代码有、文档无,1 条)—— `H-R11F-A-c`

**Telegram 适配器内置一条 gmail-triage 出仓脚本执行面:10 个动词、按钮回调直接
`create_subprocess_exec` 跑 `~/.hermes/scripts/gmail-triage/*.sh`,全仓 markdown 零提及,
且这批按钮的生产者也不在仓库里。**

`plugins/platforms/telegram/adapter.py:6697 @ 863e313`

```
    _GT_VERB_DISPATCH = {
        "send":         ("send-draft.sh",      [],         "✓ sent draft",         False),
        "archive":      ("archive.sh",         [],         "✓ archived",           False),
        "draft":        ("draft-blank.sh",     [],         "✓ drafted reply",      False),
        "spam":         ("spam.sh",            [],         "✓ marked spam",        False),
        "mute":         ("mute-add.sh",        ["email"],  "✓ muted",              True),
        "mute-domain":  ("mute-add.sh",        ["domain"], "✓ muted domain",       True),
        "trust":        ("trusted-ops-add.sh", ["email"],  "✓ trusted",            True),
        "trust-domain": ("trusted-ops-add.sh", ["domain"], "✓ trusted domain",     True),
        "vip":          ("vip-add.sh",         ["email"],  "✓ marked VIP",         True),
        "vip-domain":   ("vip-add.sh",         ["domain"], "✓ marked VIP domain",  True),
    }
```

**为什么它是接缝而不是内部实现**:它是一条**出仓**契约 —— 约定了目录
(`~/.hermes/scripts/gmail-triage/`)、10 个文件名、每个脚本的实参形状
(`arg` 恒为第一位置参,`extra_args` 追加)、以及回调数据格式 `gt:<verb>:<arg>`。
任何人想接上它,要写的是仓库外的十个 shell 脚本;而这份契约**只存在于这段代码里**。

**负结论 1:`gt:` 前缀在全仓没有生产者。** 搜索面 = 基线全部**被 git 跟踪**的文件
(`git grep`,因而自动排除 `__pycache__` 与未跟踪物),模式 `gt:`;命中 11 个文件,
逐个判过:`apps/desktop/electron/main.ts:4492`(HTML 实体表 `gt: '>'`)、
`ui-tui/src/lib/externalLink.ts:31`(同)、`locales/de.yaml:216`(德语 "Hinzugefügt:")、
`tests/agent/test_auxiliary_client.py`(`mock_gt:` 变量名)、3 个 `.png`(二进制)、
`scripts/release.py:787`(注释里提到 "gmail-triage gt: callbacks")、
`plugins/platforms/telegram/adapter.py`(消费侧本身)。
**没有一处是 `callback_data` 的产出。**

```verify
cd /home/user/hermes-agent && printf 'producers=%s consumers=%s\n' "$(git grep -h 'callback_data' -- '*.py' | grep -c 'gt:')" "$(git grep -hc 'startswith("gt:")' -- 'plugins/platforms/telegram/adapter.py')"
```

```text
producers=0 consumers=1
```

**负结论 2:全仓 markdown / mdx 零提及 gmail-triage。** 搜索面 = `git grep -rn` 限定
`'*.md' '*.mdx'`,模式 `gmail-triage\|gmail_triage`,零命中(命令退出 1、无输出)。

```verify
cd /home/user/hermes-agent && git grep -rn "gmail-triage\|gmail_triage" -- '*.md' '*.mdx' | wc -l
```

```text
0
```

**这条 ◇ 的分量在于它的方向**:一个平台适配器里长出了一整套与该平台无关的
业务能力(邮件分诊),并且是**执行任意用户脚本**的能力。它没有出现在 manifest 的任何
键里(不是 `hooks`、不是 `provides_tools`)、没有出现在 `register_platform` 的任何参数里,
因而**任何按「插件注册面」去枚举系统能力的做法都数不到它**。

### ■(代码缺陷,1 条,低severity)—— `H-R11F-A-d`

**`discord/adapter.py` 与 `discord/voice_mixer.py` 把 `from __future__ import annotations`
写在模块字符串之前,于是那段文字不是 docstring,`__doc__` 为 `None`。**

`plugins/platforms/discord/adapter.py:1 @ 863e313`

```
from __future__ import annotations

"""
```

对照组:同片另两家把 docstring 放在第一位,行为正确 ——
`plugins/platforms/telegram/adapter.py:1` 的 `"""`、`plugins/platforms/slack/adapter.py:1` 的 `"""`。

全仓普查:这个形状**只有 2 处,且两处都在本片**。搜索面 = 基线全部 `*.py`
(`rglob`),排除 `__pycache__` 与影子副本 `hermes_agent-0.20.0/`;判据 = AST 的
`body[0]` 是 `from __future__ import …` **且** `body[1]` 是裸字符串表达式
(等价于 `ast.get_docstring(module) is None` 而作者显然想写 docstring)。

```verify
cd /home/user/hermes-agent && python3 -c "
import ast, pathlib
hits=[]
for p in sorted(pathlib.Path('.').rglob('*.py')):
    s=str(p)
    if '__pycache__' in s or s.startswith('hermes_agent-0.20.0/'): continue
    try: body=ast.parse(p.read_text(encoding='utf-8')).body
    except Exception: continue
    if len(body)>1 and isinstance(body[0], ast.ImportFrom) and body[0].module=='__future__' \
       and isinstance(body[1], ast.Expr) and isinstance(body[1].value, ast.Constant) \
       and isinstance(body[1].value.value, str):
        hits.append((s[2:] if s.startswith('./') else s)+':'+str(body[1].lineno))
print('orphan-module-docstring:', len(hits))
for h in hits: print(' ', h)
"
```

```text
orphan-module-docstring: 2
  plugins/platforms/discord/adapter.py:3
  plugins/platforms/discord/voice_mixer.py:3
```

**严重性要如实说:运行期无影响。** 我在 `hermes_cli/plugins.py`、`gateway/`、`tools/` 里
搜过 `__doc__` 的读取点,**插件加载器不读适配器模块的 `__doc__`**(命中的 13 处全在
`scripts/` 下,且都是 `argparse(description=__doc__)` 这种自己读自己)。代价落在
`help()` / `pydoc` / 任何按 `__doc__` 生成文档的工具上 —— `voice_mixer.py` 那段 30 行的
设计说明(讲清了「为什么要自己写混音器」)在这些工具里**完全看不见**。

---

## 6. 三家横向对比总表(本片最有价值的产出)

同一个 ABC,三种实现选择:

| 接缝 | discord | telegram | slack | 差异性质 |
|---|---|---|---|---|
| 抽象方法实现 | 4/4 | 4/4 | 4/4 | **零差异** |
| 注册面 `register_platform` 键 | 16 | 16 | 16 | **零差异**(只有取值不同) |
| manifest 顶层键 | 8 | 8 | 8 | **零差异** |
| 覆盖的基类具体方法 | 20 | 26 | 18 | 中等 |
| 新增类属性 | 6 | 21 | 7 | 大(telegram 三倍) |
| 命令注册模型 | 27 手写装饰器 + 注册表自动补 | 纯投影 `set_my_commands` × 3 scope | 单正则匹配器 | **完全不同** |
| 命令上限 | 100(硬) | 100 硬 / 60 自限 | 无(受 app manifest) | 完全不同 |
| 入站事件 | 3 个 client event | 10 个 handler(注册两遍) | 12 个 event + 兜底正则 | 完全不同 |
| 按钮原语 | `discord.ui.View` 对象 | `callback_data` 字符串前缀 | Block Kit `action_id` | 完全不同 |
| 按钮超时 | 有(`on_timeout` × 6) | 无 | 无 | — |
| 插件可注册自己的按钮 | 否 | 否 | **是**(`register_slack_action_handler`) | slack 独有 |
| 流式编辑 | 无 | **全套**(`send_draft` / `supports_draft_streaming` / `streaming_overflow_limit` / `REQUIRES_EDIT_FINALIZE`) | 无 | telegram 独有 |
| 状态文本 | 无 | 无 | `supports_status_text=True` | slack 独有 |
| 打字命令前缀 | `/`(默认) | `/`(默认) | `!` | slack 独有 |
| 语音 | **全套**(`voice_mixer.py` / `ffmpeg_utils.py` / `play_tts` / `_voice_sources`) | 无 | 无 | discord 独有 |
| 断线补投 | `recovery.py` + 4 个 env | 靠 Bot API 服务端队列(`is_reconnect`) | 无 | 完全不同 |
| 网络逃生舱 | `DISCORD_PROXY` | `telegram_network.py`(DoH + 直连 IP 回落) | 无 | telegram 独有 |
| 富渲染 | 原生 markdown | HTML(`_EA_*` 模板全覆盖) | `block_kit.py`(688 行,opt-in) | 完全不同 |
| env-only 配置项 | 9 | 3 | 2 | discord 最散 |
| 独立 pip extra | 无 | 无 | **有**(`slack`) | slack 独有 |

**读这张表的一句话结论**:hermes 的平台插件契约把「必须一样」的部分压到了极小
(4 个抽象方法 + 16 个注册键 + 8 个 manifest 键,三家**完全一致**),
把「允许不一样」的部分放到了两处 —— **覆盖哪些基类具体方法**(能力协商)与
**平台侧怎么注册交互**(平台自己的世界)。ABC 不试图统一按钮模型、不试图统一命令模型,
只统一「消息进来变成 `MessageEvent`、回文出去调 `send`」这一条腰。

**可迁移的设计原则**(供 R12 装订时取用):
1. **抽象方法要少到能背下来**。126 个方法里只有 4 个是强制的;其余给默认实现,
   让「不实现」成为一个有意义的默认行为(`format_message` 默认原样返回)。
2. **能力用类属性声明,不用 `if platform ==` 分支**。`typed_command_prefix` / `supports_code_blocks` /
   `supports_status_text` 这一组把「平台能干什么」变成数据,调用点因此没有平台分支。
3. **平台特性靠不透明口袋穿过内核**。`MessageEvent.metadata` 里那三个 `slack_*` 键
   在内核里一次都没被读过,出口处适配器自己掏出来还原线程。
4. **但要警惕第二套隐形契约**:`getattr(adapter, "x", default)` 是极方便的可选钩子机制,
   代价是它**不在任何一份声明里**——本片实测 57 个探测名字里 35 个基类没有。
   如果要重做,应当把这批名字做成一份显式的 `OptionalHooks` 协议或注册表,
   否则「适配器到底要实现什么」这个问题**没有任何单一出处可以回答**。

---

## 7. 移交项

| 案号 | 现象(锚点 + 一句话) | 建议去向 |
|---|---|---|
| `H-R11F-A-a` | `website/docs/developer-guide/adding-platform-adapters.md:27`:`- **\`get_chat_info()\`** — Return chat metadata (optional override)` 把一个 `@abstractmethod` 标成可选;同页代码模板反而写对了 | 记入本轮 ▲(地图级)计数;R12 讲适配器契约时引为「文档腐烂」实例 |
| `H-R11F-A-b` | `plugins/platforms/telegram/telegram_ids.py:20`:`_TELEGRAM_USERNAME_RE = re.compile(r"@[A-Za-z0-9_]{4,32}")` 与它上面三行注释自称的「5-32 安全下界」不符 | 记入 ▲(码内),与地图级分开计数 |
| `H-R11F-A-c` | `plugins/platforms/telegram/adapter.py:6697`:`    _GT_VERB_DISPATCH = {` —— 10 个动词的出仓脚本执行面,`gt:` 回调全仓零生产者、markdown 零提及 | 建议后续轮次做一次「适配器内的出仓契约」普查:还有哪些适配器藏着这种不经 manifest / 不经 `register_platform` 的能力 |
| `H-R11F-A-d` | `plugins/platforms/discord/adapter.py:3`:`"""` —— `from __future__` 抢在模块字符串之前,`__doc__` 为 None;全仓仅 2 处,均在本片 | 低优先;若后续有「代码卫生」类轮次可一并处理 |
| `H-R11F-A-e` | 鸭子类型钩子面无单一出处:`gateway/run.py:3983` 的 `getattr` 这类探测点共 93 处、57 个名字,其中 35 个不在 `BasePlatformAdapter` 里,也不在 `PlatformEntry`(`gateway/platform_registry.py:39` 的 `class PlatformEntry`)里 | 建议 B/C 片按同一探针跑各自的适配器,汇总成全平台的「隐形契约表」;探针可直接复用 `data/r11f/probes/a_duck_hooks.py` |
| `H-R11F-A-f` | 本片探针 `data/r11f/probes/a_duck_hooks.py` 的适配器变量白名单只有 11 个名字,`hasattr` / `try: adapter.x` 两种写法完全没覆盖 —— 35 这个数是**下界** | 若 B/C/D/E/F 片要引用这个数,须一并引用本条限度说明 |

---

## 8. 判据自报

| 判据 | 状态 | 说明 |
|---|---|---|
| 1 点名到位 | **达成** | 15/15 文件在 §1 逐个给出全路径 + 一句话角色,无归组 |
| 2 接缝穷举 | **达成** | 8 个接缝逐个给枚举命令 + 条数 + 全表(§2.1–§2.8);5 张全表落盘 `data/r11f/a/` |
| 3 端到端链 | **达成** | §3 一条 14 跳的 Slack `@mention` → 回线程链,逐跳带锚点 |
| 4 逐字取证 | **达成** | 16 个围栏块全部为基线逐字摘录(整块每一行) |
| 5 记号 | **达成** | ▲(地图级)×1、▲(码内)×1、◇×1、■×1,共 4 条,全部带锚点;2 条负结论各写了搜索面 |

**判据本身是否需要修订**:不需要。但记一条给主线:**判据 2 的「对外接缝」在平台适配器上
有一类是判据没预设的** —— §2.3 的鸭子类型钩子面。它既不在 ABC、也不在 manifest、
也不在注册调用里,**任何按「声明」去枚举的做法都数不到它**,只能反过来从**宿主侧**扫
`getattr`。建议把「反向扫宿主对插件的探测点」写进后续 L2 派工书的接缝清单,
否则每一片都会漏掉同一类东西。

---

## 完成信号

**片号**:R11F 片 A —— `plugins/platforms/{discord,telegram,slack}`(15 文件 / 31,082 行)

**产出文件**:
- 底稿:`notes/r11f-raw-a-platforms-big3.md`
- 探针(6):`data/r11f/probes/a_adapter_surface.py`、`a_manifest_and_env.py`、
  `a_register_seam.py`、`a_interaction_surface.py`、`a_yaml_env_bridge.py`、`a_duck_hooks.py`
- 数据(10):`data/r11f/a/adapter-contract-matrix.tsv`(127 行)、`adapter-surface.json`(5167)、
  `register-platform-matrix.tsv`(23)、`manifest-keys.txt`(23)、`env-undeclared.txt`(68)、
  `yaml-env-bridge.tsv`(102)、`discord-interaction.tsv`(45)、`telegram-interaction.tsv`(37)、
  `slack-interaction.tsv`(21)、`duck-hooks.tsv`(58)

**关卡读数**(本底稿单独跑):`verify_citations.py` → `citations=33 OK=29 UNCHECKED=4`,
**可校验比例 87.9%**(下限 70%),`table_anchors=58 OK=42 UNCHECKED=16`,零 MISMATCH / 零 TABLE-DRIFT;
`verify_evidence_commands.py` → `paired=13 unpaired=0 differing=0 timedout=0`,
`runnability ran=0 runfail=0`。

**五条判据**:1 达成 / 2 达成 / 3 达成 / 4 达成 / 5 达成。无「部分达成」项。

**点名文件数**:15 / 15。

**接缝枚举命令与条数**(8 个接缝):

| 接缝 | 命令 | 条数 |
|---|---|---|
| 宿主 ABC 契约面 | `a_adapter_surface.py` | 基类 126 方法 / 4 抽象;三家覆盖 20 / 26 / 18,新增 170 / 164 / 120 |
| 能力开关面 | `a_adapter_surface.py --mode=json` | 基类 18 类属性;三家覆盖 2 / 8 / 5,新增 6 / 21 / 7 |
| 鸭子类型钩子面 | `a_duck_hooks.py` | 57 名字 / 93 探测点,35 个不在基类 |
| 注册面 | `a_register_seam.py` | `PlatformEntry` 22 字段 / 21 可传;三家各传 16、省 5、未知 0 |
| manifest 清单面 | `a_manifest_and_env.py --mode=manifest` | 三份各 8 顶层键;env 共 16 条(1+4 / 1+4 / 2+5) |
| env 面 | `a_manifest_and_env.py --mode=summary` | 宽口径 34 / 24 / 21,窄口径 25 / 20 / 17 |
| YAML→env 桥 | `a_yaml_env_bridge.py` | 桥写 env 16 / 17 / 13,YAML 键 21 / 19 / 13,env-only 9 / 3 / 2 |
| 平台交互入口面 | `a_interaction_surface.py` | discord 27 slash + 3 event + 6 view + 9 button;telegram 10 handler + 13 产出前缀 / 14 消费前缀;slack 12 event + 1 command + 13 action |

**新铸记号编号**:`H-R11F-A-a`(▲ 地图级)、`H-R11F-A-b`(▲ 码内)、`H-R11F-A-c`(◇)、
`H-R11F-A-d`(■)、`H-R11F-A-e`(移交:隐形契约面无单一出处)、
`H-R11F-A-f`(移交:本片探针口径下界说明)。

**基线状态**:只读,`git -C /home/user/hermes-agent status --porcelain` 为空;
所有执行基线代码的命令均带 `HERMES_DISABLE_LAZY_INSTALLS=1`;
全部探针只做 AST 静态解析,**未 import 基线任何模块**,未触发惰性安装,venv 未变动。
