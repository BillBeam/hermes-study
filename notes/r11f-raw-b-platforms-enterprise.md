# R11F 片 B 底稿 —— 企业/协议型平台适配器(feishu / matrix / google_chat / wecom / dingtalk)

> 本文是 R11F 第六轮插件面 L2 结构级理解的**片 B 底稿**,证据层,求全求证不求好读。
> 基线 `/home/user/hermes-agent`,commit `863e31318553cda8ad61df681d08175364d4164b`,只读。
> 一切对基线行为的断言写作 `路径:行号 @ 863e313`,锚点单独成行、置于块前。
> 本片重心是**判据 2(接缝穷举)**:凡对外接缝逐项列全,并给机械枚举命令与条数。

**术语锚定(首次出现给一句话中文解释,与成品章硬标准 1 同源)**

- **适配器(adapter)**:把某个聊天平台的收发协议翻译成 Hermes 内核统一事件的那一层代码。
- **宿主(host)**:基线里 `plugins/` 之外、加载并驱动插件的那部分(`gateway/` `cron/` `hermes_cli/`)。
- **ABC**:Python 的抽象基类。基类上标了 `@abstractmethod` 的方法,子类不实现就无法实例化。
- **清单(manifest)**:插件目录里的 `plugin.yaml`,声明插件叫什么、要哪些环境变量。
- **回调(callback)/webhook**:平台把消息 **POST 到你的 HTTP 端点**这种入站方式,
  与"你主动连上去长连接"相对。
- **重放(replay)**:攻击者把一条**曾经合法**的、带正确签名的请求原样再发一次。
- **端到端加密(E2EE)**:消息在两端设备上加解密,中间的服务器只见密文。
- **鸭子契约(duck contract)**:宿主用 `getattr(adapter, "xxx", None)` 问适配器
  "你有没有 xxx",有就用 —— 这个 `xxx` 不在 ABC 上,却同样是契约。本文自铸的说法。

---

## 0. 片 B 范围

```verify
cd /home/user/hermes-study && awk -F'\t' '{n++; l+=$2} END{printf "片 B: %d 文件 / %d 行\n", n, l}' data/r11f/slices/B.txt
```

```text
片 B: 21 文件 / 22273 行
```

五家的共同点是**认证与回调面复杂**:企业应用要签名校验、回调 URL、租户/企业 ID;
matrix 是联邦协议还带 E2EE。所以本片的核心横向对比放在**入站验证面**。

---

## 1. 判据 1 —— 点名表(21/21,每个文件全路径 + 一句话角色)

同型薄文件(五个 `__init__.py`)归为一组,**组内仍逐个列全路径**。

### 1.1 包入口(5 文件,15 行)

五个文件**逐字相同**,都只做一件事:把 `adapter.py` 里的 `register` 提升为包级符号,
供插件加载器 `import plugins.platforms.<name>` 后取用。

`plugins/platforms/dingtalk/__init__.py:1 @ 863e313`

```
from .adapter import register

__all__ = ["register"]
```

- `plugins/platforms/dingtalk/__init__.py` —— DingTalk 插件包入口,导出 `register`。
- `plugins/platforms/feishu/__init__.py` —— 飞书/Lark 插件包入口,导出 `register`。
- `plugins/platforms/google_chat/__init__.py` —— Google Chat 插件包入口,导出 `register`。
- `plugins/platforms/matrix/__init__.py` —— Matrix 插件包入口,导出 `register`。
- `plugins/platforms/wecom/__init__.py` —— 企业微信插件包入口,导出 `register`。

### 1.2 清单(5 文件,226 行)

- `plugins/platforms/dingtalk/plugin.yaml` —— DingTalk 清单:2 个必填 env、4 个可选 env,
  描述里点名走 dingtalk-stream SDK 的 Stream Mode。
- `plugins/platforms/feishu/plugin.yaml` —— 飞书清单:2 必填、5 可选;描述提到
  WebSocket 或 webhook 两种传输、以及云文档评论事件与会议邀请两条非消息入口。
- `plugins/platforms/google_chat/plugin.yaml` —— Google Chat 清单:1 必填、7 可选;
  **唯一一份 `author` 不是 NousResearch 的**(`author: Ramón Fernández`),
  且是唯一带注释解释 `requires_env` 富字典写法为什么值得用的清单。
- `plugins/platforms/matrix/plugin.yaml` —— Matrix 清单:2 必填、5 可选。
  **本片唯一一份声明了代码根本不读的 env 的清单**,见 §7 记号 `H-R11F-B-b`。
- `plugins/platforms/wecom/plugin.yaml` —— 企业微信清单:2 必填、**9 可选**(本片最多);
  描述明说这一个插件注册**两个**平台(`wecom` 走 WebSocket、`wecom_callback` 走 HTTP 回调)。

### 1.3 适配器主体(5 文件,18,721 行)

- `plugins/platforms/dingtalk/adapter.py`(1,897 行)—— DingTalk 适配器。入站走
  dingtalk-stream SDK 的 Stream Mode 长连接(`register_callback_handler`),
  出站走**会话 webhook**(每条入站消息自带的一次性回复地址)+ 可选 AI 卡片流式。
- `plugins/platforms/feishu/adapter.py`(5,874 行)—— 飞书/Lark 适配器,本片最大文件。
  两种传输(`websocket` / `webhook`)、三层用户 ID(open_id/user_id/union_id)、
  富文本 post 结构的双向渲染、跨重启持久化去重、处理状态 reaction。
- `plugins/platforms/google_chat/adapter.py`(3,738 行)—— Google Chat 适配器。
  入站有两条路:宿主 api_server 转来的 **Google 签名 JWT 回调**,或 Cloud Pub/Sub 拉取;
  出站走 Chat REST API;附件走每用户 OAuth(见 `oauth.py`)。
- `plugins/platforms/matrix/adapter.py`(5,284 行)—— Matrix 适配器。mautrix SDK 同步循环入站,
  可选 E2EE(olm / megolm),HTML 消毒器、房间身份、审批/选择器等交互原语。
- `plugins/platforms/wecom/adapter.py`(1,928 行)—— 企业微信智能机器人适配器。
  自建 WebSocket 协议帧(`aibot_subscribe` / `aibot_msg_callback` / `aibot_send_msg`),
  并在文件末尾的 `register(ctx)` 里**一次注册两个平台**。

### 1.4 支撑模块(6 文件,3,311 行)

- `plugins/platforms/feishu/feishu_comment.py`(1,382 行)—— 飞书云文档评论事件处理。
  解析 `drive.notice.comment_add_v1`,拉评论时间线,**自己起一个 AIAgent** 回复评论
  (不走网关消息管线),并把 lark 客户端注入工具线程局部变量。
- `plugins/platforms/feishu/feishu_comment_rules.py`(429 行)—— 评论功能的访问控制规则。
  三级回退(精确文档 > 通配 `*` > 顶层 > 代码默认),配置文件 mtime 缓存热重载,
  另带一个 pairing(配对授权)存储。
- `plugins/platforms/feishu/feishu_meeting_invite.py`(212 行)—— 飞书会议邀请事件处理。
  把 `vc.bot.meeting_invited_v1` 转成**合成 MessageEvent** 走正常网关管线
  (与评论模块的"自起 agent"相反,模块 docstring 自己点明了这个对比)。
- `plugins/platforms/google_chat/oauth.py`(695 行)—— Google Chat 的**每用户 OAuth 助手**。
  存在的唯一理由是 Chat 的 `media.upload` 端点硬拒服务账号鉴权,
  所以每个用户要在自己的 DM 里跑一次 `/setup-files` 授权。
- `plugins/platforms/wecom/callback_adapter.py`(451 行)—— 企业微信**回调模式**适配器
  (自建应用)。自建 aiohttp 服务器收加密 XML,解密后入队、立刻 ACK,
  回复走 access_token 的 `message/send` 主动推送。
- `plugins/platforms/wecom/wecom_crypto.py`(142 行)—— 企业微信 BizMsgCrypt 兼容实现:
  SHA1 签名 + AES-256-CBC + PKCS7,与腾讯官方 `WXBizMsgCrypt` 同线格式。

**判据 1 自报:达成。** 21/21 全部出现全路径 + 一句话角色。

---

## 2. 判据 2 面之一 —— 适配器对宿主 ABC 的实现面

### 2.1 枚举命令与条数

探针 `data/r11f/probes/b_adapter_contract.py` 用纯 AST 比对
`gateway/platforms/base.py` 的 `BasePlatformAdapter` 类体与六个适配器类的类体
(**不 import 被测代码** —— 基线的可选依赖是惰性联网安装的)。

```verify
cd /home/user/hermes-study && HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/b_adapter_contract.py
```

```text
BasePlatformAdapter: 成员 126,其中 @abstractmethod 4
平台	IMPL-ABSTRACT	MISS-ABSTRACT	OVERRIDE	PLUGIN-ONLY	类体成员合计
dingtalk	4	0	6	26	36
feishu	4	0	12	140	156
google_chat	4	0	14	32	50
matrix	4	0	13	78	95
wecom	4	0	8	52	64
wecom_callback	4	0	1	14	19
```

**读法**:基类 126 个成员里只有 **4 个**是抽象的,六个适配器**全部实现、零缺口**。
所以"必须实现的契约"极小,而"可以改的默认行为"极大(126 - 4 = 122 个具体成员)。
这正是这套 harness 的设计取舍:**ABC 只钉住生命周期与收发的最小骨架,
其余全部给出可用默认值**,新平台从"能跑"到"跑得好"是一条连续的坡,不是一道墙。

### 2.2 四个抽象方法(逐项列全,6 平台 × 4 = 24 条)

```verify
cd /home/user/hermes-study && HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/b_adapter_contract.py --kind IMPL-ABSTRACT | tail -n +2 | awk -F'\t' '{printf "%s.%s @ %s:%s\n", $1, $2, $4, $5}'
```

```text
dingtalk.connect @ async def:287
dingtalk.disconnect @ async def:375
dingtalk.get_chat_info @ async def:1158
dingtalk.send @ async def:985
feishu.connect @ async def:1754
feishu.disconnect @ async def:1807
feishu.get_chat_info @ async def:2404
feishu.send @ async def:1928
google_chat.connect @ async def:985
google_chat.disconnect @ async def:1152
google_chat.get_chat_info @ async def:3304
google_chat.send @ async def:2057
matrix.connect @ async def:1583
matrix.disconnect @ async def:2016
matrix.get_chat_info @ async def:2123
matrix.send @ async def:2059
wecom.connect @ async def:225
wecom.disconnect @ async def:271
wecom.get_chat_info @ async def:1561
wecom.send @ async def:1422
wecom_callback.connect @ async def:125
wecom_callback.disconnect @ async def:183
wecom_callback.get_chat_info @ async def:266
wecom_callback.send @ async def:210
```

**读法**:每个平台的这四个方法都在**同一个文件**里,行号跨度从 `wecom_callback` 的
125–266(141 行)到 `google_chat` 的 985–3304(2,319 行)。
抽象契约本身极窄,窄到可以在一屏里读完;把它撑到几千行的是各家平台自己的翻译工作量。

### 2.3 覆写具体方法的面(54 条,逐项列全)

```verify
cd /home/user/hermes-study && HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/b_adapter_contract.py --kind OVERRIDE | tail -n +2 | awk -F'\t' '{print $1"\t"$2}' | awk -F'\t' '{a[$2]=a[$2]" "$1} END{for(k in a) print k"\t"a[k]}' | sort
```

```text
__init__	 dingtalk feishu google_chat matrix wecom wecom_callback
delete_message	 google_chat
edit_message	 dingtalk feishu google_chat matrix
enforces_own_access_policy	 wecom
format_message	 feishu google_chat matrix
on_processing_complete	 feishu google_chat matrix
on_processing_start	 feishu matrix
send_animation	 feishu google_chat
send_clarify	 google_chat
send_document	 dingtalk feishu google_chat matrix wecom
send_image	 dingtalk feishu google_chat matrix wecom
send_image_file	 dingtalk feishu google_chat matrix wecom
send_multiple_images	 matrix
send_typing	 dingtalk feishu google_chat matrix wecom
send_video	 feishu google_chat matrix wecom
send_voice	 feishu google_chat matrix wecom
stop_typing	 google_chat matrix
```

**读法**:被覆写最普遍的是**媒体发送族**(`send_image` / `send_image_file` /
`send_document` 五家全覆写)。基类的默认实现是"把媒体当一段文字发出去",
每家平台都有自己的原生上传 API,所以这一族必然被换掉。
反过来 `handle_message`、`_process_message_background`、`_send_with_retry`
这些**编排逻辑一个平台都没覆写** —— 编排留在宿主,平台只管翻译。这是这套设计最值钱的一条边界。

`wecom_callback` 只覆写 `__init__` 一项,是本片"最薄适配器"的样本:
451 行里 19 个类体成员,其中 4 个抽象实现 + 1 个覆写 + 14 个私有。

### 2.4 逐字取证(判据 4 之一)—— `enforces_own_access_policy` 是本片唯一被覆写的属性

`plugins/platforms/wecom/adapter.py:890 @ 863e313`

```
    @property
    def enforces_own_access_policy(self) -> bool:
        """WeCom gates DM/group access at intake via dm_policy/group_policy."""
        return True
```

这一条是**授权面**的接缝:基类默认让宿主的 `_is_sender_authorized` 做准入,
而企业微信自己在适配器里做(它的 `_is_dm_allowed` 被 `gateway/authz_mixin.py:668`
用鸭子契约取用,见 §3)。**六家里只有它这么做。**

---

## 3. 判据 2 面之二 —— 鸭子契约面(ABC 之外的隐式协议)

这是本片认为**最值得写进蓝图**的一个发现:上面那张表把 342 个成员归进 PLUGIN-ONLY,
读起来像"插件私有实现"。**其中有一部分根本不是私有的** —— 宿主会用
`getattr(adapter, "<名字>", None)` 去问适配器有没有它。这些名字**不在 ABC 上、
不在任何签名里、也不在文档里**,但漏实现就是功能静默消失。

探针 `data/r11f/probes/b_duck_contract.py` 用 AST 找宿主代码里
`getattr(x, "字面量")` / `hasattr(x, "字面量")` 的第二个参数
(**不是文本 grep** —— 那会命中同名注释),宿主面 = 基线里除 `tests/` 与 `plugins/`
之外的全部 `.py`(排除 `plugins/` 是有意的:插件 getattr 自己的方法不构成宿主契约)。

```verify
cd /home/user/hermes-study && HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/b_duck_contract.py --full
```

```text
platform	member	adapter_lineno	host_sites	first_host_site
dingtalk	REQUIRES_EDIT_FINALIZE	225	2	gateway/stream_consumer.py:297
dingtalk	SUPPORTS_MESSAGE_EDITING	216	1	gateway/run.py:23795
feishu	_add_reaction	3141	1	gateway/platforms/base.py:4942
feishu	_reactions_enabled	3138	1	gateway/platforms/base.py:4946
feishu	_remove_reaction	3181	1	gateway/platforms/base.py:4943
feishu	_resolve_channel_prompt	3290	1	gateway/run.py:19174
feishu	send_exec_approval	2037	1	gateway/run.py:5181
feishu	send_update_prompt	2143	1	gateway/run.py:20993
google_chat	dispatch_http_event	1495	1	gateway/platforms/api_server.py:1832
google_chat	verify_http_event_request	1520	1	gateway/platforms/api_server.py:1831
matrix	send_choice_picker	2669	1	gateway/slash_commands.py:3463
matrix	send_exec_approval	2516	1	gateway/run.py:5181
matrix	send_model_picker	2588	1	gateway/slash_commands.py:1779
wecom	_is_dm_allowed	900	1	gateway/authz_mixin.py:668
TOTAL	14
```

**14 条绑定 / 13 个不同名字。** 分三类看:

| 类 | 名字 | 谁问 | 漏实现的后果 |
|---|---|---|---|
| 能力声明(类常量) | `SUPPORTS_MESSAGE_EDITING`、`REQUIRES_EDIT_FINALIZE` | `gateway/run.py:23795`:`_adapter_supports_edit = getattr(adapter, "SUPPORTS_MESSAGE_EDITING", True)`、另见 `gateway/stream_consumer.py:297` | 流式消费者按"不支持编辑"降级,每段话发一条新消息 |
| 交互原语 | `send_exec_approval`、`send_model_picker`、`send_choice_picker`、`send_update_prompt` | `gateway/run.py:5181`:`if getattr(type(ctx._status_adapter), "send_exec_approval", None) is not None:`、另见 `gateway/slash_commands.py:1779`、`:3463`、`gateway/run.py:20993` | 审批/选择器回落成纯文本提示 |
| 平台钩子 | `verify_http_event_request` + `dispatch_http_event`、`_add_reaction` 三兄弟、`_is_dm_allowed`、`_resolve_channel_prompt` | `gateway/platforms/api_server.py:1831`:`verifier = getattr(adapter, "verify_http_event_request", None)`、另见 `gateway/platforms/base.py:4942`、`gateway/authz_mixin.py:668`、`gateway/run.py:19174` | 该条入站/授权/提示词通道整条不存在 |

**第三类里 `verify_http_event_request` + `dispatch_http_event` 这一对最重要**:
Google Chat 的 HTTP 入站**不是自己起服务器**,而是挂在宿主 api_server 的
通用平台回调路由上,靠这一对方法被认领。

`gateway/platforms/api_server.py:1831 @ 863e313`

```
        verifier = getattr(adapter, "verify_http_event_request", None)
        dispatcher = getattr(adapter, "dispatch_http_event", None)
        if verifier is None or dispatcher is None:
            return web.json_response(
                _openai_error(
                    "Platform adapter does not support HTTP events",
                    code="platform_http_events_unsupported",
                ),
                status=503,
            )
```

宿主对这个鸭子契约有一处**很好的防御**,值得抄进自己的 harness:验证器抛异常时
**默认拒绝**,而不是让异常冒泡成 500(500 也许会被上游重试成功)。

`gateway/platforms/api_server.py:1850 @ 863e313`

```
        except Exception:
            # Fail closed: a crashing verifier must never admit the event.
            logger.exception(
                "Platform HTTP event verifier failed for %s", platform_name
            )
            ok, code = False, "platform_event_verifier_error"
```

**◇(代码有、文档无)**:这 13 个名字构成的可选协议,基线里没有任何一份文档把它列全。
`gateway/platforms/ADDING_A_PLATFORM.md` 是最接近的"怎么加一个平台"指南,
但它不在 CLAUDE.md 给 ▲ 划的地图范围(README / 仓库根 AGENTS.md / website/docs)内,
所以本条记 **◇**,不记 ▲。铸号 `H-R11F-B-e`。

---

## 4. 判据 2 面之三 —— `plugin.yaml` 清单面

### 4.1 顶层键集(五份逐份列全)

```verify
cd /home/user/hermes-study && HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/b_manifest_env_reach.py --keys
```

```text
platform	n_keys	keys
dingtalk	8	name,label,kind,version,description,author,requires_env,optional_env
feishu	8	name,label,kind,version,description,author,requires_env,optional_env
google_chat	8	name,label,kind,version,description,author,requires_env,optional_env
matrix	8	name,label,kind,version,description,author,requires_env,optional_env
wecom	8	name,label,kind,version,description,author,requires_env,optional_env
UNION	8	author,description,kind,label,name,optional_env,requires_env,version
```

**五份键集完全一致,各 8 个键,并集也是 8。** 派工书给的全仓 15 个顶层键里,
本片一个都没用到的有 7 个:`hooks`、`provides_web_providers`、`pip_dependencies`、
`provides_browser_providers`、`platforms`、`provides_tools`、`external_dependencies`。
这说明**平台型插件用的是清单的一个很窄的子集** —— 它们不往宿主注册工具/网页提供者,
只声明身份与环境变量;真正的注册全部发生在 `register(ctx)` 的代码里(见 §5)。

### 4.2 env 声明面(38 条逐条列全)+ 每条能否被代码读到

判据说明写在探针里:**"谁在读它"的判据是字面量出现,不是语义。** 一个变量名可以被
`os.getenv(NAME)` 读、被 `_get_scoped_secret(NAME)` 读,也可以作为
`register_platform(cron_deliver_env_var="NAME")` 这样的注册参数被宿主间接读 ——
三种写法的共同点只有"这个字符串在某个 `.py` 里出现过"。
所以判据就定在这里,并按三个互不重叠的面分别报数(`py_prod` 非 tests 的 `.py`、
`py_test` 仅 `tests/`、`docs` 仅 `website/` 的 `.md`),让"只有测试提到它"
和"只有文档提到它"当场可见。**统计按词边界,不用子串** ——
否则 `MATRIX_HOME_CHANNEL` 会被 `MATRIX_HOME_CHANNEL_NAME` 顺带记一笔,
`py_prod == 0` 这个判据就被稀释了。

```verify
cd /home/user/hermes-study && HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/b_manifest_env_reach.py --env | tail -3
```

```text
wecom	optional_env	WECOM_CALLBACK_TOKEN	name,description,prompt,password	4	1	4	gateway/config.py
wecom	optional_env	WECOM_CALLBACK_ENCODING_AES_KEY	name,description,prompt,password	4	1	4	gateway/config.py
TOTAL	38
```

全表 38 行落在 `data/r11f/b/manifest-env-reach.tsv`。**每条 env 的子字段面**是齐的:
38 条**全部**用富字典写法,`name`/`description`/`prompt`/`password` 四个子字段一条不缺,
其中 5 条另带 `url`(dingtalk 的两条 client 凭据、feishu 的两条 app 凭据、
google_chat 的 `GOOGLE_CHAT_PROJECT_ID`)。派工书列的第五个子字段 `password` 也全在。

```verify
cd /home/user/hermes-study && HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/b_manifest_env_reach.py --env | tail -n +2 | grep -v '^TOTAL' | awk -F'\t' '{c[$4]++} END{for(k in c) printf "%d 条: %s\n", c[k], k}' | sort -rn
```

```text
33 条: name,description,prompt,password
5 条: name,description,prompt,url,password
```

### 4.3 清单声明了、生产代码一个字都不读的 env

```verify
cd /home/user/hermes-study && HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/b_manifest_env_reach.py --env --dead
```

```text
platform	block	env	subfields	py_prod	py_test	docs	first_py_prod
matrix	optional_env	MATRIX_HOME_CHANNEL	name,description,prompt,password	0	1	1	-
matrix	optional_env	MATRIX_HOME_CHANNEL_NAME	name,description,prompt,password	0	1	1	-
TOTAL	2
```

**38 条里恰好 2 条死掉,都在 matrix。** 详见 §7 的 `H-R11F-B-b`。

### 4.4 清单为什么不是死 YAML —— 它真的进设置向导

这一步是上面那条判据成立的前提:如果 `optional_env` 根本没人读,
声明一个不存在的变量就只是无害的注释。实际不是。

`hermes_cli/config.py:5396 @ 863e313`

```
            # Merge required + optional env var declarations.
            entries = list(manifest.get("requires_env") or [])
            entries.extend(manifest.get("optional_env") or [])
```

`hermes_cli/config.py:5419 @ 863e313`

```
                OPTIONAL_ENV_VARS[name] = {
                    "description": (
                        meta.get("description")
                        or f"{label} configuration"
                    ),
                    "prompt": meta.get("prompt") or name,
                    "url": meta.get("url") or None,
                    "password": is_secret,
                    "category": meta.get("category") or "messaging",
                }
```

`OPTIONAL_ENV_VARS` 就是 `hermes config` 设置向导的输入面。所以清单里写的每一条 env
**都会被端到用户面前让他填**。填一个没人读的变量,用户拿不到任何反馈。

---

## 5. 判据 2 面之四 —— `register_platform` 注册面

第三个契约面(前两个是 ABC 实现面与鸭子契约面)是 `register(ctx)` 里那串关键字参数。
`hermes_cli/plugins.py:953` 的签名只固定 6 个形参,其余全部走 `**entry_kwargs`
转发给 `PlatformEntry` 数据类 —— 所以**这个面的真实形状只能从调用点读出来,读签名读不到**。

```verify
cd /home/user/hermes-study && HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/b_register_kwargs.py --matrix
```

```text
kwarg	dingtalk	feishu	google_chat	matrix	wecom	wecom_callback	in_PlatformEntry
adapter_factory	Y	Y	Y	Y	Y	Y	Y
allow_all_env	Y	Y	Y	Y	Y	Y	Y
allow_update_command	Y	Y	Y	Y	Y	Y	Y
allowed_users_env	Y	Y	Y	Y	Y	Y	Y
apply_yaml_config_fn	Y	Y	-	Y	-	-	Y
check_fn	Y	Y	Y	Y	Y	Y	Y
cron_deliver_env_var	Y	Y	Y	Y	Y	-	Y
emoji	Y	Y	Y	Y	Y	Y	Y
env_enablement_fn	-	-	Y	-	-	-	Y
install_hint	Y	Y	Y	Y	Y	Y	Y
is_connected	Y	Y	Y	Y	Y	Y	Y
label	Y	Y	Y	Y	Y	Y	Y
max_message_length	-	Y	Y	Y	Y	-	Y
name	Y	Y	Y	Y	Y	Y	Y
platform_hint	-	-	Y	-	-	-	Y
required_env	Y	Y	Y	Y	Y	Y	Y
setup_fn	Y	Y	Y	Y	Y	-	Y
standalone_sender_fn	Y	Y	Y	Y	Y	-	Y
validate_config	Y	Y	Y	-	Y	Y	Y

PlatformEntry 字段数	22
片 B 用到的关键字数	19
片 B 一个都没用到的 PlatformEntry 字段	source,plugin_name,pii_safe
```

**19/22 覆盖,一条不漏地列全了。** 三个没用到的里,`source` 与 `plugin_name`
是 `register_platform` 自己填的(它 `setdefault("plugin_name", …)` 并硬传 `source="plugin"`),
真正"六家都没用"的只有 `pii_safe`(会话描述里是否脱敏 PII)。

**六个调用点里的四处不齐,逐条点名**(这正是"接缝穷举"要抓的东西):

| 平台 | 缺什么 | 后果(已核到消费点) |
|---|---|---|
| `matrix` | `validate_config` | `gateway/platform_registry.py:57`:`# If None, the registry skips config validation and lets the adapter` —— 是**声明过的**回退,不是遗漏 |
| `dingtalk` | `max_message_length` | 注册项落 0;`gateway/relay/descriptor.py:162`:`max_len = getattr(entry, "max_message_length", 0) or 4096` 把 0 映射成 4096,于是 DingTalk **经 relay 桥**时按 4096 切块,而它自己的 `MAX_MESSAGE_LENGTH = 20000`。**保守但不坏** |
| `wecom_callback` | `setup_fn` / `standalone_sender_fn` / `cron_deliver_env_var` / `max_message_length` | 没有交互式设置向导、cron 不能投递到它、离线发送不可用;`send()` 里硬编码 `content[:2048]` |
| 除 `google_chat` 外五家 | `platform_hint` | 只有 Google Chat 给模型注入了平台能力提示词(它那段 21 行的提示词把"能做什么、不能做什么"全写出来了) |

`plugins/platforms/wecom/callback_adapter.py:220 @ 863e313`

```
            payload = {
                "touser": touser,
                "msgtype": "text",
                "agentid": int(str(app.get("agent_id") or 0)),
                "text": {"content": content[:2048]},
                "safe": 0,
            }
```

---

## 6. 判据 2 面之五 —— 入站验证面(本片的横向对比重心)

### 6.1 入站传输三型

```verify
cd /home/user/hermes-agent && grep -rn "router.add_" plugins/platforms/dingtalk/ plugins/platforms/feishu/ plugins/platforms/google_chat/ plugins/platforms/matrix/ plugins/platforms/wecom/ --include=*.py
```

```text
plugins/platforms/feishu/adapter.py:4954:        app.router.add_post(self._webhook_path, self._handle_webhook_request)
plugins/platforms/wecom/callback_adapter.py:156:            self._app.router.add_get("/health", self._handle_health)
plugins/platforms/wecom/callback_adapter.py:157:            self._app.router.add_get(self._path, self._handle_verify)
plugins/platforms/wecom/callback_adapter.py:158:            self._app.router.add_post(self._path, self._handle_callback)
```

**全片只有 4 条自建 HTTP 路由,分属 2 个适配器。** 六个适配器的入站传输是三型:

| 型 | 谁 | 入站怎么来 |
|---|---|---|
| **自建 HTTP 服务器** | `feishu`(webhook 模式)、`wecom_callback` | 适配器自己起 aiohttp,上面 4 条路由 |
| **挂宿主 HTTP 服务器** | `google_chat`(HTTP events 模式) | 鸭子契约 `verify_http_event_request` + `dispatch_http_event`,路由在 `gateway/platforms/api_server.py` |
| **出站长连接(无入站端口)** | `dingtalk`、`wecom`、`matrix`、`feishu`(websocket 模式)、`google_chat`(Pub/Sub 模式) | SDK/自建 WS/同步循环/拉取订阅 |

**这是本片最可迁移的一条结构观察**:同一个 ABC 下,五家平台跑出了三种完全不同的
入站拓扑,而 ABC 上一个字都没提入站——`connect()` 的语义就是"你自己想办法把消息喂给
`handle_message`"。代价是入站安全**完全下放给了适配器**,没有任何统一关卡,下面就是后果。

### 6.2 五家入站验证逐家列全

| 平台/模式 | 身份凭证 | 签名/加密 | 时间戳防重放 | 消息去重 | 其他前置闸 |
|---|---|---|---|---|---|
| `feishu` websocket | app_id + app_secret(SDK 握手) | SDK 内部 TLS | 无 | `_seen_message_ids`,TTL 24h、**跨重启持久化** | — |
| `feishu` webhook | `FEISHU_VERIFICATION_TOKEN`(体内 token,`hmac.compare_digest`) | `FEISHU_ENCRYPT_KEY` → SHA256(ts+nonce+key+body),`hmac.compare_digest` | **无** | 同上 | 限流 120/60s(app:path:ip)、Content-Type 白名单、1MB 体上限、30s 读超时、异常计数器 |
| `wecom` | `WECOM_BOT_ID` + `WECOM_SECRET`(`aibot_subscribe` 帧) | WSS | 无 | — | — |
| `wecom_callback` | 每 app 的 `token` | SHA1(sorted(token,ts,nonce,encrypt)) + AES-256-CBC 解密 + `receive_id` 比对 | **无** | `_seen_messages`,TTL **300s**、进程内、>2000 条时剪枝 | 64KB 体上限(aiohttp 层 + 处理器各一道)、`defusedxml` 解析 |
| `google_chat` HTTP | Google 签名的 ID token(`Bearer`) | `google.oauth2.id_token.verify_oauth2_token`(校验 Google 签名 + audience) | 由 JWT 的 `exp` 承担 | `_dedup.is_duplicate(msg_name)` | 服务账号 email 白名单(逗号分隔)、验证器抛异常即拒 |
| `google_chat` Pub/Sub | 服务账号凭据(拉取订阅) | Google 传输层 | — | 同上 | — |
| `matrix` | `MATRIX_ACCESS_TOKEN` 或密码登录 | 可选 E2EE(olm/megolm),`MATRIX_E2EE_MODE` = off/optional/**required** | 启动宽限期(丢弃早于启动的事件)+ 时钟偏移检测 | `_is_duplicate_event(event_id)` | 房间白名单 |
| `dingtalk` | `DINGTALK_CLIENT_ID` + `DINGTALK_CLIENT_SECRET`(SDK Credential) | SDK 内部 | 无 | — | — |

### 6.3 两家自建 HTTP 入站都不做重放窗口 —— 负结论与它的搜索面

**负结论**:片 B 里两个自建 HTTP 入站面(`feishu` webhook、`wecom_callback`)
**都没有对请求时间戳做新鲜度检查**,重放只靠消息 ID 去重挡。

**搜索面**(按 CLAUDE.md「负结论的成本」):搜的是这两个适配器涉及入站验证的全部代码,
模式是与"时间新鲜度"有关的一切写法(`time.time()` / `time.monotonic` /
`datetime.now` / `utcnow` / `replay` / `tolerance` / `skew` / `max_age` / `stale`),
大小写敏感面按正则给出;feishu 侧把范围收窄到 `_handle_webhook_request` 与
`_is_webhook_signature_valid` 两个函数所在的 3537–3665 行区间(区间外的
`time.time()` 属去重与限流,不是签名新鲜度)。**没有排除注释** ——
注释里提到 replay 也算命中,宁可多报。

```verify
cd /home/user/hermes-agent && grep -cE "time\.time\(\)|time\.monotonic|datetime\.now|utcnow|replay|tolerance|skew|max_age|stale" plugins/platforms/wecom/wecom_crypto.py; sed -n '3537,3665p' plugins/platforms/feishu/adapter.py | grep -cE "time\.time\(\)|time\.monotonic|datetime\.now|utcnow|replay|tolerance|skew|max_age|stale"
```

```text
0
0
```

`wecom_crypto.py` 全文零命中,feishu 的两个入站函数区间零命中。
`callback_adapter.py` 里的 3 处 `time.time()` 逐处点名过:`:314` 是消息去重 TTL,
`:423` 与 `:443` 是 access_token 缓存过期 —— **没有一处是签名时间戳的新鲜度检查**。

**后果分级(如实说,不夸大)**:攻击者能做的只是**重放一条曾经真实发出过的消息**,
不能伪造新内容(签名挡住了)。危害面取决于去重窗口:feishu 是 24 小时且跨重启持久化,
`wecom_callback` 是 **300 秒进程内**,进程一重启窗口就清零。所以
`wecom_callback` 是这一格里最薄的一家。铸号 `H-R11F-B-c`。

### 6.4 逐字取证(判据 4 之二)—— 同一件事,两种写法

**正面样本**,飞书 webhook 签名比对:

`plugins/platforms/feishu/adapter.py:3655 @ 863e313`

```
        try:
            body_str = body_bytes.decode("utf-8", errors="replace")
            content = f"{timestamp}{nonce}{self._encrypt_key}{body_str}"
            computed = hashlib.sha256(content.encode("utf-8")).hexdigest()
            # Compare as bytes: compare_digest raises TypeError on a str with
            # non-ASCII characters, and the signature is a raw request header.
            return hmac.compare_digest(computed.encode(), signature.encode())
```

**反面样本**,企业微信回调签名比对:

`plugins/platforms/wecom/wecom_crypto.py:88 @ 863e313`

```
    def decrypt(self, msg_signature: str, timestamp: str, nonce: str, encrypt: str) -> bytes:
        expected = _sha1_signature(self.token, timestamp, nonce, encrypt)
        if expected != msg_signature:
            raise SignatureError("signature mismatch")
```

同一个仓库、同一类工作,一个用恒定时间比较并在注释里写明理由,
另一个用 `!=`。详见 §7 的 `H-R11F-B-a`。

---

## 7. 判据 5 —— 记号(逐条带锚点)

### `H-R11F-B-a` ■ 企业微信回调签名用 `!=` 比对,不是恒定时间比较

**现象**:`plugins/platforms/wecom/wecom_crypto.py:90` 用 `expected != msg_signature`
比对入站回调的 SHA1 签名。攻击者能控制 `timestamp` / `nonce` / `encrypt` / `msg_signature`
四个输入中的全部,`token` 是唯一秘密;逐字节的短路比较给出可测的时间差,
正是 `hmac.compare_digest` 存在的理由。

**为什么这是缺陷而不是风格**:基线**自己**把这条规矩写成了注释模板,
并在同类位置反复执行。仓库范围搜索:

```verify
cd /home/user/hermes-agent && grep -rl "compare_digest" --include=*.py . | grep -v '^./tests/' | wc -l
```

```text
21
```

**搜索面**:`--include=*.py`、全仓、排除 `tests/`(测试里的 compare_digest 是断言辅助,
不是被测行为)、未排除注释。21 个生产文件在用。更窄的一刀:
`plugins/platforms/` 下所有**算了摘要**的文件,看谁用恒定时间比较、谁用裸比较:

```verify
cd /home/user/hermes-agent && for f in $(grep -rl "hexdigest()" --include=*.py plugins/platforms/ | sort); do if grep -q "compare_digest" "$f"; then echo "compare_digest  $f"; else echo "裸比较        $f"; fi; done
```

```text
compare_digest  plugins/platforms/a2a/security.py
裸比较        plugins/platforms/discord/adapter.py
compare_digest  plugins/platforms/feishu/adapter.py
compare_digest  plugins/platforms/line/adapter.py
裸比较        plugins/platforms/wecom/adapter.py
裸比较        plugins/platforms/wecom/wecom_crypto.py
裸比较        plugins/platforms/whatsapp/adapter.py
```

**三个"裸比较"逐个查过,只有一个是真的。** 逐处贴出那一行,让"它不是验签"当场可见:

`plugins/platforms/discord/adapter.py:1868 @ 863e313`

```
        payload = json.dumps(desired, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

—— 斜杠命令集的指纹,用来判断要不要向 Discord 重新注册命令。

`plugins/platforms/wecom/adapter.py:1247 @ 863e313`

```
                "md5": hashlib.md5(data).hexdigest(),
```

—— 分片上传 payload 里的完整性字段,给平台核对用,自己不比对。

`plugins/platforms/whatsapp/adapter.py:353 @ 863e313`

```
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
```

—— 文件内容哈希做缓存键(还截断到 16 个十六进制字符,截断本身就说明它不是签名)。

**三处都不是验证入站签名**。所以 `wecom_crypto.py` 是 `plugins/platforms/` 树里
**唯一**一处"算摘要用于验签、却用裸运算符比对"的地方。

**顺带记一处死分支(同文件,不单独铸号)**:

`plugins/platforms/wecom/wecom_crypto.py:42 @ 863e313`

```
    def encode(cls, text: bytes) -> bytes:
        amount_to_pad = cls.block_size - (len(text) % cls.block_size)
        if amount_to_pad == 0:
            amount_to_pad = cls.block_size
```

`amount_to_pad` 取值恒在 1..32(`block_size` 减一个 `0..block_size-1` 的余数),
于是 `if amount_to_pad == 0:` 永不成立。这一条与腾讯官方 SDK 同形,
属**忠实移植**而非新引入,故只记录不铸号。

### `H-R11F-B-b` ■ + ▲ Matrix 清单声明的 `MATRIX_HOME_CHANNEL` 没有任何代码读

**■ 侧(代码缺陷)**。清单这么写:

`plugins/platforms/matrix/plugin.yaml:34 @ 863e313`

```
  - name: MATRIX_HOME_CHANNEL
    description: "Default room ID for cron / notification delivery"
    prompt: "Home room ID"
    password: false
  - name: MATRIX_HOME_CHANNEL_NAME
    description: "Display name for the Matrix home room"
    prompt: "Home room display name"
```

而同一个插件的注册代码读的是另一个名字:

`plugins/platforms/matrix/adapter.py:5276 @ 863e313`

```
        apply_yaml_config_fn=_apply_yaml_config,
        allowed_users_env="MATRIX_ALLOWED_USERS",
        allow_all_env="MATRIX_ALLOW_ALL_USERS",
        cron_deliver_env_var="MATRIX_HOME_ROOM",
        standalone_sender_fn=_standalone_send,
        max_message_length=DEFAULT_MAX_MESSAGE_LENGTH,
```

宿主的 cron 落点表也读那个名字:

`cron/scheduler.py:264 @ 863e313`

```
_HOME_TARGET_ENV_VARS = {
    "matrix": "MATRIX_HOME_ROOM",
    "telegram": "TELEGRAM_HOME_CHANNEL",
```

**机械判据见 §4.3:38 条声明里恰好这 2 条 `py_prod == 0`,全片仅此一处。**
后果链条完整:§4.4 已证明 `optional_env` 会进 `OPTIONAL_ENV_VARS`,
于是 `hermes config` **会向用户索要 `MATRIX_HOME_CHANNEL`**,
用户填了,cron 投递仍然找不到房间,而且**不会有任何报错**——
它读的是 `MATRIX_HOME_ROOM`,那个是空的。
Matrix 自己的交互式设置向导写的又是另一个名字:

`plugins/platforms/matrix/adapter.py:5188 @ 863e313`

```
        print_info("Leave blank to clear a previously saved home room (cron / notifications).")
        home_room = prompt("Home room ID (leave empty to set later with /set-home)").strip()
        if home_room:
            save_env_value("MATRIX_HOME_ROOM", home_room)
```

所以**走 `hermes gateway setup` 向导的人没事,走 `hermes config` 通用 env 面的人踩坑**
—— 同一个产品的两条设置路径,把同一件事写成了两个变量名。

**▲ 侧(地图与代码矛盾)**。这条不止是代码内部不一致,`website/docs` 也照抄了错的那个。
该文件开篇第 9 行给全文定了性:「Hermes reads environment variables from the process
environment and, for user-managed secrets, from `~/.hermes/.env`.」——
整份表的断言就是"这些是 Hermes 会读的变量"。管辖标题是 `## Messaging`(第 299 行),
表头 `| Variable | Description |`。同一张表里:

`website/docs/reference/environment-variables.md:495 @ 863e313`

> | `MATRIX_HOME_CHANNEL` | Default room ID for cron / notification delivery. |
> | `MATRIX_HOME_CHANNEL_NAME` | Display name for the Matrix home room. |

`website/docs/reference/environment-variables.md:498 @ 863e313`

> | `MATRIX_HOME_ROOM` | Room ID for proactive message delivery (e.g. `!abc123:matrix.org`) |

**同一张表为同一件事列了两个变量,只有第二个是真的。** 判据 5 要求整句/整段一并判定:
:495 这一行是一个完整断言(变量 + 用途),用途正确、变量错误,
**字面不为真,所以是 ▲ 不是 ◎**。中文站同一张表**没有翻译 `MATRIX_HOME_CHANNEL`**,
只留了对的那一条 —— **翻译版反而是对的**:

`website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/reference/environment-variables.md:397 @ 863e313`

> | `MATRIX_HOME_ROOM` | 主动消息投递的房间 ID（例如 `!abc123:matrix.org`） |

### `H-R11F-B-c` ■ 两个自建 HTTP 入站面无重放窗口

证据与搜索面见 §6.3。`wecom_callback` 的 300 秒进程内去重是其中最薄的一格。

### `H-R11F-B-d` ▲(码内)两处模块 docstring 指向基线里不存在的文件

CLAUDE.md 明写模块 docstring 与代码注释**不在地图级 ▲ 的范围内**,故记 ▲(码内),分开计数。

`plugins/platforms/feishu/feishu_comment.py:4 @ 863e313`

> Processes ``drive.notice.comment_add_v1`` events and interacts with the
> Drive v2 comment reaction API.  Kept in a separate module so that the
> main ``feishu.py`` adapter does not grow further and comment-related
> logic can evolve independently.

`plugins/platforms/wecom/callback_adapter.py:3 @ 863e313`

> Unlike the bot/websocket adapter in ``wecom.py``, this handles the standard
> WeCom callback flow: WeCom POSTs encrypted XML to an HTTP endpoint, the
> adapter decrypts it, queues the message for the agent, and immediately
> acknowledges.

两处点名的 `feishu.py` 与 `wecom.py` 在基线里都不存在。**搜索面**:
`find . -name` 精确文件名匹配,全仓,只排除 `.git/`,不限目录不限深度。

```verify
cd /home/user/hermes-agent && find . -name 'wecom.py' -o -name 'feishu.py' | grep -v '\.git/' | wc -l
```

```text
0
```

真实文件名是 `plugins/platforms/feishu/adapter.py` 与 `plugins/platforms/wecom/adapter.py`
—— 插件化迁移时文件被改了名,docstring 没跟。**同形状的还有两处在我片外**:

`gateway/relay/ws_transport.py:46 @ 863e313`

```
try:  # lazy/optional dep — mirrors gateway/platforms/feishu.py
```

`gateway/platforms/helpers.py:199 @ 863e313`

```
    Replaces the identical ``_strip_markdown()`` functions previously
    duplicated in sms.py, bluebubbles.py, and feishu.py.
```

这两处一并记在这里供下一轮取用,但**它们不计进本片的 ▲(码内)条数**(本片只数 2 条)
—— 它们都在 `gateway/` 下,不属任何一片插件面。

### `H-R11F-B-e` ◇ 13 个鸭子契约名字没有任何文档列全

见 §3。

### `H-R11F-B-f` ■ 复核 `H-R9D-D-g`:飞书工具可用性探针与真实可用条件脱节 —— **属实**

派工书要求独立复核,不照抄。复核结论:**原判成立**,并补齐了它的搜索面。

探针这样判"这 5 个工具可用":

`tools/feishu_doc_tool.py:62 @ 863e313`

```
    import importlib.util
    try:
        return importlib.util.find_spec("lark_oapi") is not None
    except (ImportError, ValueError):
        return False
```

而工具真正能干活的条件是线程局部客户端已被注入:

`tools/feishu_doc_tool.py:74 @ 863e313`

```
    client = get_client()
    if client is None:
        return tool_error("Feishu client not available (not in a Feishu comment context)")
```

**全仓唯一的注入点在我片内**:

`plugins/platforms/feishu/feishu_comment.py:1057 @ 863e313`

```
    logger.info("[Feishu-Comment] _run_comment_agent: injecting lark client into tool thread-locals")
    from tools.feishu_doc_tool import set_client as set_doc_client
    from tools.feishu_drive_tool import set_client as set_drive_client
    set_doc_client(client)
    set_drive_client(client)
```

**"唯一"这个负结论的搜索面**:`grep -rn "set_client\b"`,`--include=*.py`,全仓
(含 `tests/`),排除 `def set_client` 那两行定义本身;未排除注释与字符串。

```verify
cd /home/user/hermes-agent && grep -rn "set_client\b" --include=*.py . | grep -v "def set_client"
```

```text
./plugins/platforms/feishu/feishu_comment.py:1058:    from tools.feishu_doc_tool import set_client as set_doc_client
./plugins/platforms/feishu/feishu_comment.py:1059:    from tools.feishu_drive_tool import set_client as set_drive_client
```

受影响工具**实测 5 个**(`check_fn=_check_feishu` 的注册点):

```verify
cd /home/user/hermes-agent && grep -c "check_fn=_check_feishu" tools/feishu_doc_tool.py tools/feishu_drive_tool.py
```

```text
tools/feishu_doc_tool.py:1
tools/feishu_drive_tool.py:4
```

**复核中新查明的两点,原判没写**:

1. **线程模型是对的,不是这条缺陷的一部分。** 注入方 `_run_comment_agent` 被这样调起:

   `plugins/platforms/feishu/feishu_comment.py:1352 @ 863e313`

   ```
       loop = asyncio.get_running_loop()
       response = await loop.run_in_executor(
           None, _run_comment_agent, prompt, client, sess_key,
       )
   ```

   整个 agent 循环跑在**同一个** executor 线程里,工具处理器也在该线程内同步执行,
   所以 `threading.local` 看得见。并且函数退出时把两个客户端都置回 `None`,不会串到下一个任务:

   `plugins/platforms/feishu/feishu_comment.py:1105 @ 863e313`

   ```
       finally:
           set_doc_client(None)
           set_drive_client(None)
   ```

   **注入侧是干净的** —— 这条缺陷的位置在探针,不在注入。
2. **`_check_feishu` 那段注释本身不是 ▲(码内)。** 它说
   "Correctness is preserved because the actual tool handler still does the real
   import when invoked" —— 这句话只声称**导入**这件事仍然正确,而
   `tools/feishu_doc_tool.py:79-83` 确实在处理器里做了真导入。**字面为真就不是 ▲。**
   问题不在这句注释,而在于 `check_fn` 这个接缝**只能表达"依赖装没装"**,
   表达不了"上下文对不对" —— 那是注册面的表达力不足,不是注释说了假话。

**这一点才是可迁移的设计教训**:工具注册表的 `check_fn` 是**进程级、一次性**求值的,
而"能不能用"在这里是**每次调用、每个线程**才有答案的。
把后者塞进前者,必然得到"永远显示可用、每次调用都报错"。

---

## 8. 判据 3 —— 端到端链(企业微信回调模式,逐跳带锚点)

选这一条是因为它**全程可读**:入站验签、解密、入队、内核、回投,每一跳都在片内或宿主的具体行上。

场景:一个企业微信用户在自建应用里给机器人发了一句"帮我查下昨天的日报"。

| # | 跳 | 锚点 | 发生了什么 |
|---|---|---|---|
| 1 | 平台 → 插件 HTTP | `plugins/platforms/wecom/callback_adapter.py:158`:`self._app.router.add_post(self._path, self._handle_callback)` | 企业微信 POST 加密 XML 到 `/wecom/callback` |
| 2 | 体积闸 | `plugins/platforms/wecom/callback_adapter.py:299`:`if len(body_bytes) > _MAX_BODY:` | 超 64KB 直接 413,验签前先挡 |
| 3 | 逐 app 试解 | `plugins/platforms/wecom/callback_adapter.py:306`:`decrypted = self._decrypt_request(` | 一个网关可挂多个自建应用,逐个试 |
| 4 | 验签 | `plugins/platforms/wecom/wecom_crypto.py:89`:`expected = _sha1_signature(self.token, timestamp, nonce, encrypt)` | SHA1(sorted(token,ts,nonce,encrypt)),对不上抛 `SignatureError` |
| 5 | 解密 + 租户核对 | `plugins/platforms/wecom/wecom_crypto.py:110`:`if receive_id != self.receive_id:` | AES-CBC 解出明文,再核对 corp_id,防跨企业投递 |
| 6 | 转事件 | `plugins/platforms/wecom/callback_adapter.py:366`:`def _build_event(self, app: Dict[str, Any], xml_text: str) -> Optional[MessageEvent]:` | XML → `MessageEvent`;chat_id 是 `corp_id:user_id` 复合键 |
| 7 | 去重 | `plugins/platforms/wecom/callback_adapter.py:315`:`if event.message_id in self._seen_messages:` | 企业微信超时会重投,300s 内同 MsgId 直接 ACK |
| 8 | 入队 + 立刻 ACK | `plugins/platforms/wecom/callback_adapter.py:331`:`await self._message_queue.put(event)` | 同步 HTTP 响应里不等 agent,直接 `success` |
| 9 | 出队 → 基类 | `plugins/platforms/wecom/callback_adapter.py:347`:`task = asyncio.create_task(self.handle_message(event))` | `_poll_loop` 把事件交给基类 |
| 10 | 基类编排 | `gateway/platforms/base.py:5554`:`async def handle_message(self, event: MessageEvent) -> None:` | 会话锁、去抖、后台任务,全在宿主 |
| 11 | 调内核 | `gateway/platforms/base.py:5838`:`response = await self._message_handler(event)` | 这个 handler 由 `gateway/run.py:11093`:`adapter.set_message_handler(self._primary_message_handler())` 装上 |
| 12 | handler 是谁 | `gateway/run.py:13629`:`return self._handle_message` | 非多路复用时就是 GatewayRunner 自己的 `_handle_message`(agent 循环入口) |
| 13 | 回投 | `gateway/platforms/base.py:6091`:`result = await delivery_adapter._send_with_retry(` | 拿到回答后走带重试的发送 |
| 14 | 重试壳 → 适配器 | `gateway/platforms/base.py:5060`:`result = await self.send(` | `_send_with_retry` 最终调回适配器的 `send` |
| 15 | 插件 → 平台 | `plugins/platforms/wecom/callback_adapter.py:229`:`resp = await self._http_client.post(` | 用 access_token 打 `qyapi.weixin.qq.com/cgi-bin/message/send` 主动推送 |
| 16 | token 过期自愈 | `plugins/platforms/wecom/callback_adapter.py:235`:`if errcode in {40001, 42001} and _attempt == 0:` | 40001/42001 时清缓存重取一次,再失败才认输 |

**这条链上最值得抄的设计**:第 8 跳。回调型平台**必须秒回**,否则平台判超时并重投。
所以适配器把"收"和"办"彻底解耦——收完立刻 ACK,办完走**另一条出站通道**(主动推送 API)。
代价是回复不再是 HTTP 响应体,于是必须自己维护 access_token(第 16 跳)。
**这是回调型与长连接型适配器的根本分野**,不是实现细节。

---

## 9. 判据 2 面之六 —— 出站发送面

### 9.1 消息长度上限(逐家列全,含三处不一致)

```verify
cd /home/user/hermes-agent && grep -rn "^MAX_MESSAGE_LENGTH\|^DEFAULT_MAX_MESSAGE_LENGTH\|^_MAX_TEXT_LENGTH\|^MATRIX_MAX_MESSAGE_LENGTH_CEILING" plugins/platforms/dingtalk/adapter.py plugins/platforms/feishu/adapter.py plugins/platforms/google_chat/adapter.py plugins/platforms/matrix/adapter.py plugins/platforms/wecom/adapter.py
```

```text
plugins/platforms/dingtalk/adapter.py:132:MAX_MESSAGE_LENGTH = 20000
plugins/platforms/google_chat/adapter.py:230:_MAX_TEXT_LENGTH = 4000
plugins/platforms/matrix/adapter.py:499:DEFAULT_MAX_MESSAGE_LENGTH = 16000
plugins/platforms/matrix/adapter.py:500:MATRIX_MAX_MESSAGE_LENGTH_CEILING = 65535
plugins/platforms/matrix/adapter.py:528:MAX_MESSAGE_LENGTH = DEFAULT_MAX_MESSAGE_LENGTH
plugins/platforms/wecom/adapter.py:115:MAX_MESSAGE_LENGTH = 4000
```

(飞书的 `MAX_MESSAGE_LENGTH = 8000` 写在类体内而非模块级,所以上面这条只锚模块级常量的
正则没有收它;见下表。matrix 出现两次是因为它在 `:528` 又给模块级
`MAX_MESSAGE_LENGTH` 起了一个指向 `DEFAULT_MAX_MESSAGE_LENGTH` 的别名。)

| 平台 | 类上的值 | 注册给宿主的值 | 是否可配 | 出处 |
|---|---|---:|---|---|
| dingtalk | 20000 | **未传(落 0→relay 侧按 4096)** | 否 | `plugins/platforms/dingtalk/adapter.py:213`:`MAX_MESSAGE_LENGTH = MAX_MESSAGE_LENGTH` |
| feishu | 8000 | 8000 | 否 | `plugins/platforms/feishu/adapter.py:1470`:`MAX_MESSAGE_LENGTH = 8000` |
| google_chat | 4000 | 4000 | 否 | `plugins/platforms/google_chat/adapter.py:641`:`MAX_MESSAGE_LENGTH = _MAX_TEXT_LENGTH` |
| matrix | 16000 | 16000 | **是**(env / extra / relay 三源,上限 65535,下限 500) | `plugins/platforms/matrix/adapter.py:524`:`return max(500, min(value, MATRIX_MAX_MESSAGE_LENGTH_CEILING))` |
| wecom | 4000 | 4000 | 否 | `plugins/platforms/wecom/adapter.py:170`:`MAX_MESSAGE_LENGTH = MAX_MESSAGE_LENGTH` |
| wecom_callback | **无类属性** | 未传 | 否 | `plugins/platforms/wecom/callback_adapter.py:224`:`"text": {"content": content[:2048]},` |

**只有 Matrix 把长度做成可配的**,而且做得最完整:三个来源按优先级取,
并夹在 `[500, 65535]` 区间里防止用户填出一个会被服务器拒绝的数。
其余五家硬编码。`wecom_callback` 连类属性都没有,直接在 payload 里切 —— 于是
基类的分块逻辑(`truncate_message`)对它**根本不生效**,超长回复被静默截断而不是分条发出。

### 9.2 出站 API 端点(逐家列全)

| 平台 | 出站入口 | 端点 / 通道 | 富文本形态 |
|---|---|---|---|
| dingtalk | `plugins/platforms/dingtalk/adapter.py:985`:`async def send(` | 入站消息自带的**会话 webhook**(`api|oapi.dingtalk.com` 白名单正则) | `msgtype: markdown`;另有 AI 卡片流式(`alibabacloud_dingtalk.card_1_0`) |
| feishu | `plugins/platforms/feishu/adapter.py:1928`:`async def send(` | lark-oapi SDK 的 `CreateMessageRequest` / `ReplyMessageRequest` | `post` 富文本结构(自建渲染器把 Markdown 转成 post 行列) |
| google_chat | `plugins/platforms/google_chat/adapter.py:2057`:`async def send(` | Chat REST API `chat.googleapis.com/v1/` | 受限 Markdown 子集;Card v2(`card_spec_to_cards_v2`)仅用于内部构造,提示词明说不让模型生成 |
| matrix | `plugins/platforms/matrix/adapter.py:2059`:`async def send(` | mautrix client 发 `m.room.message` | `org.matrix.custom.html` + 自建 HTML 消毒器 `_MatrixHtmlSanitizer` |
| wecom | `plugins/platforms/wecom/adapter.py:1422`:`async def send(` | WebSocket 帧 `aibot_send_msg` | `msgtype: markdown` |
| wecom_callback | `plugins/platforms/wecom/callback_adapter.py:210`:`async def send(` | `qyapi.weixin.qq.com/cgi-bin/message/send` | **只有 `text`**,不支持 markdown |

### 9.3 媒体上传面

| 平台 | 上传方式 | 特殊约束 |
|---|---|---|
| dingtalk | 会话 webhook 直传 / 卡片 | 覆写 `send_image` / `send_image_file` / `send_document`,**不覆写** `send_video` / `send_voice` |
| feishu | `CreateImageRequest` / `CreateFileRequest` | 五种媒体方法全覆写(含 `send_animation`) |
| google_chat | `media.upload` | **服务账号被硬拒**,必须每用户 OAuth,`plugins/platforms/google_chat/oauth.py` 整个文件为此存在 |
| matrix | mautrix `upload_media` | 覆写最多(含 `send_multiple_images`);语音要转码成 ogg(`_matrix_transcode_voice_to_ogg`) |
| wecom | `aibot_upload_media_*` 分片上传 + MD5 | 覆写 5 种媒体方法 |
| wecom_callback | **无** | 一个媒体方法都没覆写,媒体全部回落成文字 |

---

## 10. 可迁移的设计要点(给"造自己的 harness"用)

1. **抽象基类只钉最小骨架。** 126 个成员里只有 4 个是抽象的,这让"接一个新平台"
   的最小代价是 4 个方法,而"接好"是一条连续的坡。
2. **但要把"可选协议"写下来。** 本片挖出 13 个鸭子契约名字,一个文档都没列全(§3)。
   ABC 小的代价必须由**一份显式的可选能力清单**来补,否则新平台作者只能靠读宿主源码
   才知道自己少实现了什么,而少实现的表现是**功能静默降级**,不是报错。
3. **清单声明的每一条 env 都要有消费者,并且要能机械校验这件事。** §4.3 那条判据
   (`py_prod == 0`)十行代码就能写,而它抓到的是一个**跨了清单、注册代码、cron 落点表、
   官方文档四处**的名字不一致(§7 `H-R11F-B-b`)。人工评审抓不住这类,因为四处各自都自洽。
4. **入站安全不能完全下放给适配器。** 同一个 ABC 下跑出三种入站拓扑(§6.1),
   于是"验签怎么比对"(§7 `H-R11F-B-a`)、"要不要重放窗口"(§7 `H-R11F-B-c`)
   各家各判。宿主至少应该提供一个**共享的入站验证工具箱**
   (恒定时间比较 + 时间戳窗口 + 体积闸 + 去重),让适配器"用"而不是"各写一遍"。
   基线其实已经有这个雏形,连注释都把理由写好了:

   `gateway/platforms/webhook.py:166 @ 863e313`

   ```
       Comparing as UTF-8 bytes keeps the constant-time guarantee while making a
       hostile header fail closed with a clean rejection.
       """
       return hmac.compare_digest(provided.encode(), expected.encode())
   ```

   它只是**没被强制走** —— 一个"存在但不是唯一入口"的安全工具箱,
   最终等于把每个适配器作者的记性当成了防线。
5. **`check_fn` 这类"能力探针"要问对问题。** 进程级一次性求值的探针
   回答不了"每次调用、每个线程才有答案"的问题(§7 `H-R11F-B-f`)。
   注册面要么把上下文条件也表达出来,要么就别在探针里假装能表达。
6. **回调型平台的"收/办解耦"是硬要求。** §8 第 8 跳:必须秒回 ACK,
   回复走另一条出站通道,于是必须自管 access_token 与其过期自愈。
   把这条写进平台适配器的设计模板,而不是让每个作者自己撞一次超时重投。

---

## 11. 判据自报

| 判据 | 自报 | 依据 |
|---|---|---|
| 1 点名到位 | **达成** | §1,21/21 全路径 + 角色 |
| 2 接缝穷举 | **达成** | 六个面各有机械枚举命令与条数:ABC 实现面(§2,126/4/0 缺口,54 条覆写全表)、鸭子契约面(§3,14 绑定/13 名)、清单键面(§4.1,8 键 ×5 份)、env 面(§4.2–4.3,38 条 + 2 条死)、注册面(§5,19/22 关键字 + 4 处不齐)、入站面(§6,4 条路由 / 三型 / 逐家表)、出站面(§9,长度 + 端点 + 媒体三张全表) |
| 3 端到端链 | **达成** | §8,16 跳全部带锚点 |
| 4 逐字取证 | **达成** | **25 个**无语言标记的逐字源码围栏块(要求 ≥2),另有 5 个 `>` 文档引用块。引用关卡读数 `OK=30`(25 + 5)、`MISMATCH=0`,即**这 30 个块整块每一行都与基线逐字一致** |
| 5 记号 | **达成** | §7,6 条全部带锚点 |

**记号计数(按 CLAUDE.md 要求分行报)**

- 地图级 ▲:**1**(`H-R11F-B-b` 的 ▲ 侧,`website/docs/reference/environment-variables.md:495`)
- ▲(码内):**2**(`H-R11F-B-d`,片内两处;片外另见两处,不计入)
- ■:**4**(`H-R11F-B-a`、`H-R11F-B-b` 的 ■ 侧、`H-R11F-B-c`、`H-R11F-B-f`)
- ◇:**1**(`H-R11F-B-e`)
- ◎:0

---

## 12. 移交项(锚点 + 一句话现象)

| 案号 | 锚点 + 摘录 | 现象 | 建议去向 |
|---|---|---|---|
| `H-R11F-B-a` | `plugins/platforms/wecom/wecom_crypto.py:90`:`if expected != msg_signature:` | 入站回调签名用裸 `!=` 比对,同仓 21 个生产文件都用 `hmac.compare_digest` | 代码缺陷复核轮 |
| `H-R11F-B-b` | `plugins/platforms/matrix/plugin.yaml:34`:`- name: MATRIX_HOME_CHANNEL` | 清单声明并向用户索要的 env,生产代码零引用;代码读的是 `MATRIX_HOME_ROOM`;`website/docs` 同表两条并列 | 代码缺陷复核轮 + 文档冲突台账 |
| `H-R11F-B-c` | `plugins/platforms/wecom/callback_adapter.py:293`:`msg_signature = request.query.get("msg_signature", "")` | 签名覆盖 timestamp 但从不检查其新鲜度,重放只靠 300s 进程内去重 | 代码缺陷复核轮 |
| `H-R11F-B-d` | `plugins/platforms/wecom/callback_adapter.py:3`:`Unlike the bot/websocket adapter in ``wecom.py``, this handles the standard` | docstring 指向基线里不存在的 `wecom.py`;同形第二处见 `plugins/platforms/feishu/feishu_comment.py:6`:`adapter does not grow further and comment-related` | 文档冲突台账(码内) |
| `H-R11F-B-e` | `gateway/platforms/api_server.py:1831`:`verifier = getattr(adapter, "verify_http_event_request", None)` | 13 个宿主用 getattr 探测的可选协议名,无任何文档列全 | 蓝图装订轮(写进"平台适配器契约"一章) |
| `H-R11F-B-f` | `tools/feishu_doc_tool.py:64`:`return importlib.util.find_spec("lark_oapi") is not None` | 复核 `H-R9D-D-g` 属实:进程级探针答不了每调用/每线程的可用性,5 个工具永远显示可用 | 代码缺陷复核轮(可与 `H-R9D-D-g` 合并结清) |

**跨片提示(不铸号,留给主线)**:片外另有两处同 `H-R11F-B-d` 形状的失效文件名引用
——`gateway/relay/ws_transport.py:46`:`try:  # lazy/optional dep — mirrors gateway/platforms/feishu.py`
与 `gateway/platforms/helpers.py:200`:`duplicated in sms.py, bluebubbles.py, and feishu.py.`。
两者都在 `gateway/` 下,不属任何一片插件面,主线可自行决定归属。

---

## 13. 环境与边界自述

- 基线全程只读;所有执行基线代码的命令都带 `HERMES_DISABLE_LAZY_INSTALLS=1`
  (本片全部探针为纯 AST / 文本读取,不 import 被测模块,故也不触发惰性安装)。
- 未改 `scripts/`、`chapters/`、台账、`CLAUDE.md`,未动 `data/inflight/*.claim`。
- 未扩充共享环境:本片未装任何包,venv 保持 87 包。
- 未跑测试,故不报测试通过数(本片是结构级理解,判据里没有测试项)。
- 写入路径只有三处:本底稿、`data/r11f/probes/b_*.py`(4 个)、`data/r11f/b/*.tsv`(4 个)。

**两道阻断关卡在本片产出上的读数**(合并全量范围由主线在 commit 前跑):

```text
$ python3 scripts/verify_citations.py /home/user/hermes-agent notes/r11f-raw-b-platforms-enterprise.md
citations=37  OK=30  UNCHECKED=7
可校验比例 OK/37 = 81.1%
table_anchors=41  OK=41
OK: every code-block-backed citation matches the baseline

$ python3 scripts/verify_evidence_commands.py notes/r11f-raw-b-platforms-enterprise.md
verify-blocks paired=18  unpaired=0  differing=0  timedout=0
runnability   ran=0  runfail=0  skipped-mutating=0
OK: every paired ```verify command reproduces its pasted output
```

自校验读数按 CLAUDE.md 贴在 ```` ```text ```` 里而不是 ```` ```verify ````
——一个"跑校验器扫本文件"的命令会无限递归。

**关卡当场抓到的错,如实记下来**(它们正是这两道关卡存在的理由):
证据命令关卡首次运行判 `EVIDENCE-DIFF` **4 处**,四处全是手抄输出时漏行/串行
(漏了 `TOTAL` 行、`tail -3` 少贴一行、`grep` 结果漏一条、一个行号抄错);
引用关卡判 `MISMATCH` **1 处** —— `enforces_own_access_policy` 锚点差一行,
而且**连带查出那段 docstring 我抄错了整句**(写成 `WeCom AI Bot enforces allow/deny
inside the adapter itself.`,基线原文是 `WeCom gates DM/group access at intake via
dm_policy/group_policy.`)。**后者正是 BLOCK-DRIFT 全块比对要抓的形态:
人工评审读起来毫无破绽,因为它是一句通顺、意思也大致对的英文。**

---

## 完成信号

**片号**:R11F 片 B(`plugins/platforms/{feishu,matrix,google_chat,wecom,dingtalk}`,21 文件 / 22,273 行)

**产出文件**

- 底稿:`notes/r11f-raw-b-platforms-enterprise.md`
- 探针:`data/r11f/probes/b_adapter_contract.py`、`data/r11f/probes/b_duck_contract.py`、
  `data/r11f/probes/b_manifest_env_reach.py`、`data/r11f/probes/b_register_kwargs.py`
- 数据:`data/r11f/b/adapter-contract-full.tsv`、`data/r11f/b/duck-contract.tsv`、
  `data/r11f/b/manifest-env-reach.tsv`、`data/r11f/b/manifest-keys.tsv`

**五条判据**

1. 点名到位 —— **达成**(21/21 全路径 + 一句话角色,§1)
2. 接缝穷举 —— **达成**(六个面全部给出机械枚举命令与条数,§2/§3/§4/§5/§6/§9)
3. 端到端链 —— **达成**(企业微信回调模式 16 跳,逐跳锚点,§8)
4. 逐字取证 —— **达成**(**25 个**逐字源码围栏块 + 5 个 `>` 文档引用块,要求 ≥2;
   引用关卡 `OK=30 / MISMATCH=0`,整块每一行都比对过)
5. 记号 —— **达成**(6 条带锚点;地图级 ▲ 1、▲(码内) 2、■ 4、◇ 1、◎ 0)

**点名文件数**:21 / 21

**接缝枚举命令与条数**

| 面 | 命令 | 条数 |
|---|---|---|
| ABC 实现面 | `python3 data/r11f/probes/b_adapter_contract.py --full` | 基类 126 成员 / 4 抽象;6 适配器 × 4 抽象 = 24 实现、**0 缺口**;54 条覆写;342 条 PLUGIN-ONLY |
| 鸭子契约面 | `python3 data/r11f/probes/b_duck_contract.py --full` | 14 条绑定 / 13 个不同名字 |
| 清单键面 | `python3 data/r11f/probes/b_manifest_env_reach.py --keys` | 5 份 × 8 键,并集 8 |
| env 面 | `python3 data/r11f/probes/b_manifest_env_reach.py --env` | 38 条;`--dead` 出 **2 条**生产代码零引用 |
| 注册面 | `python3 data/r11f/probes/b_register_kwargs.py --matrix` | 6 个调用点、19 个关键字 / `PlatformEntry` 22 字段、4 处不齐 |
| 入站 HTTP 路由面 | `grep -rn "router.add_" plugins/platforms/{dingtalk,feishu,google_chat,matrix,wecom}/ --include=*.py` | 4 条路由 / 2 个适配器;入站拓扑三型 |
| 出站面 | §9 三张全表(长度上限 6 行、API 端点 6 行、媒体上传 6 行) | 18 行 |

**新铸记号编号**:`H-R11F-B-a`、`H-R11F-B-b`、`H-R11F-B-c`、`H-R11F-B-d`、
`H-R11F-B-e`、`H-R11F-B-f`(六个号各指一个实体,无复用)
