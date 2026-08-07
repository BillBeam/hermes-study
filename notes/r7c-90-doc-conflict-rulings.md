# r7c-90 · 文档-代码冲突定案(R7C)

> 底稿。基线 `863e31318553cda8ad61df681d08175364d4164b`(下称 `863e313`)。
> 记号:**▲** = 文档所述与代码矛盾(证伪);**◇** = 代码有真实机制而文档无载;
> **■** = 代码内部缺陷(不是文档问题),按项目先例只记录、不修。
> 每条给出双侧原文与溯源,读本文件即完成验证。
> 分簇明细见 `notes/r7c-raw-*`;本文件是**定案层**,只收进入定案的条目。

## 0. 汇总

**本轮定案 41 条:▲ 21 条、◇ 14 条、■ 6 条。**
另有 **7 条移交项全部结案**(R7 四项 + R7B 三项),其中 **3 条推翻或收窄了上一轮的表述**。

移交项结案速览:

| 来源 | 移交项 | 结论 |
|---|---|---|
| R7 A4 | pairing 本体(哈希码、锁定) | ✅ 结案,并给出 R7 A4 的**决定性证据**(§1.1) |
| R7 A5 | `scale_to_zero.py` 本体 | ✅ 结案,**并发现绑定侧生产恒失效**(§1.2 / ■-1) |
| R7 A6 | kanban 评论 steer 注入侧 | ⚠️ 结案并**更正 R7 的定位**:不在 `kanban_watchers.py`(§1.3) |
| R7 C 表 | authz 层级 | ✅ 结案,枚举出 **14 层**(§1.4) |
| R7 B3 | `status.py` 描述矛盾 | ✅ 结案(§1.5);**并更正其出处** —— R7B 报告误记为 R7B 新增 |
| R7B B-19 | 五方言验签运营文档缺口 | ⚠️ 结案并**收窄**:4/5 有文档且准确,只缺 Svix(§1.6) |
| R7B | 审批解析器共用面 | ✅ 结案:**两套审批共用一批词汇**,一套有 ID 一套没有(§1.7) |

---

## 1. 移交项结案(7 条)

### 1.1 R7 A4 —— pairing 本体:▲ 证实,并补上决定性证据

R7 已判"开发者文档把 DM 配对方向写反"。本轮补齐 pairing 本体,并把该判决从
"没找到 `/pair` 命令"升级为**调用点穷举**:

全仓 `approve_code` / `approve_request` 只有 **4 个生产调用点,全在已认证侧**:
`hermes_cli/pairing.py:72,74`(CLI)与 `hermes_cli/web_server.py:12337,12339`
(已认证 dashboard)。入站消息路径**零调用**。代码自己也这么写:

`gateway/authz_mixin.py:581-585 @ 863e313`
```python
        # Check pairing store. A pairing entry is a first-class authorization
        # grant, created only by a trusted operator approving a pairing code
        # (hermes gateway pairing approve / the authenticated dashboard) — an
        # inbound sender can never reach approve_code, so this is not an
        # attacker-controlled path. Honored as a UNION with the allowlist: a
```

**pairing 本体的安全属性(R7 移交要点,逐条钉死)**:

- **码不明文落盘**:每条独立 16 字节 `os.urandom` 盐 + SHA-256
  (`gateway/pairing.py:583`、`:644-645`),文件里的键是 `secrets.token_hex(8)`
  而不是码本身(`:648`)。
- **常数时间比较**:`secrets.compare_digest`(`gateway/pairing.py:712`、`:765`)。
- **锁定必须排在 pending 查找之前**,否则等于没有 —— 代码自陈:

`gateway/pairing.py:684-690 @ 863e313`
```python
            # Lockout check — must run before the pending lookup so a
            # valid code (e.g. one already sitting in pending) cannot be
            # accepted once the lockout fires. Without this, the lockout
            # only blocks `generate_code`, not `approve_code` — nullifying
            # the brute-force protection for any code already issued.
            if self._is_locked_out(platform):
                return None
```
- **成功批准重置失败计数**(`:598`、`:856-867`),否则终身累加会误锁正常用户。

**裁决:▲ 证实(R7 判决维持),pairing 本体结案。**
**新增 ■-6(见 §4):跨进程无文件锁** —— `gateway/pairing.py` 全文无 `fcntl`/`flock`,
只有进程内 `threading.RLock`(`:450`)。而 CLI / dashboard / 网关是**不同进程**,
三者对 `pending.json` 的读-改-写会互相覆盖。

### 1.2 R7 A5 —— `scale_to_zero.py` 本体:◇ 证实,且发现绑定侧生产恒失效

R7 已判"网关侧 scale-to-zero 代码有、地图无"。本轮读完本体,**◇ 维持**,
并发现一个更重的问题(详见 ■-1)。

本体是 124 行**无副作用纯函数**(`scale_to_zero_enabled` / `parse_idle_timeout_seconds` /
`messaging_is_relay_only_or_absent` / `should_arm` / `is_idle`),语义清楚:

`gateway/scale_to_zero.py:120-124 @ 863e313`
```python
    if running_agent_count > 0:
        return False
    if has_live_background_work:
        return False
    return seconds_since_last_inbound >= idle_timeout_seconds
```

**纯函数本身正确。问题全在 `has_live_background_work` 这个入参怎么算出来的**——见 ■-1。

### 1.3 R7 A6 —— kanban 评论 steer:⚠️ **更正 R7 的定位**

R7 A6 把"kanban 评论 steer 注入侧"移交给 `gateway/kanban_watchers.py`。**这个定位是错的。**

- `gateway/kanban_watchers.py` 全文 1493 行**无 `steer` 字样、不读 `task_comments`**。
- 真正的评论 steer 在 **`tools/kanban_tools.py:350-414`**,调用点在
  **`agent/run_agent.py:3710`** —— 运行在 **worker 进程内**,不是网关进程。
  它挂在 `_touch_activity` 上(6 秒节流 + rowid 水位线 + 过滤自述),
  因此是 R7 A6「三个看门狗共用一钟」的**第四个消费者**。
- 网关侧的 kanban → agent 注入走的是**另一条明确不 steer 的路**:
  终态事件 → `deliver_wake` → 合成 `MessageEvent(internal=True)`
  (`gateway/wake.py:73-87`)→ 忙时策略机在读 `_busy_text_mode` **之前**就短路
  (`gateway/run.py:8867-8879`,`if internal: return False`)→ 落到
  `gateway/platforms/base.py:5735-5748` **排队**。

**裁决:A6 的 ◇ 维持(活动心跳的多消费者共享成立),但锚点改判** ——
kanban 评论 steer 在 `tools/kanban_tools.py` + `agent/run_agent.py`(R2/R3 域),
**不在 R7C 范围内**;网关侧 kanban→agent 的注入是 wake 排队路径,与 steer 无关。
判据一句话:**steer 是"这条输入等不了下一轮",wake 是"等得了"。**

### 1.4 R7 C 表 —— authz 层级:▲ 证实(文档只列 5 层,实际 14 层且顺序也错)

**文档**(`website/docs/developer-guide/gateway-internals.md:96-100 @ 863e313`)列 5 步:
per-platform allow-all → platform allowlist → DM pairing → global allow-all → deny。

**代码**:`gateway/authz_mixin.py` 的判定链是 **14 层、纯"或"、无拒绝列表、兜底 deny**
(全表见 `notes/r7c-raw-authz-pairing.md`)。文档两处错:

1. **层数**:漏掉 HomeAssistant/Webhook 豁免(`:403-404`)、relay 上游已授权
   (`:435-439`)、群/论坛/频道 chat_id 名单(env 与 config.yaml 两路,`:453-485`)、
   `{PLATFORM}_ALLOW_BOTS`(`:493-502`)、`role_authorized`(`:578-579`)、
   Telegram `-` 前缀兼容、WhatsApp/SimpleX 别名等。
2. **顺序**:文档把 DM pairing 排在 platform allowlist **之后**,代码里
   PairingStore 批准表(`:595-598`)在平台名单(`:601`)**之前**。

**并且模块自己的 docstring 也只列 5–6 层**(`gateway/authz_mixin.py:387-396`)——
又一例"docstring 停在机制的起点"。

**关键设计事实(重实现必须知道)**:**没有 owner/admin 分级**。
"owner" 不是一个授权层级,而是**批准入口的物理位置**(CLI 与已认证 dashboard)。
群名单不蕴含 DM 权限(`:733-736`、`:604`)。

### 1.5 R7 B3 —— `status.py` 描述矛盾:▲ 证实(并更正出处)

**先更正本项目自己的台账**:任务简报与 `reports/round-7b-platform-integration.md:161`
把该项记为"R7B 新增的三项"之一。**它其实是 R7 的 B3**
(`notes/r7-90-doc-conflict-rulings.md:210-214`),且 R7B 的 9 篇底稿里
`grep -i status` 只有 1 处无关命中 —— **R7B 从未取证过这一项**。属本项目串轮,不是仓库问题。

**侧 A**(`website/docs/developer-guide/gateway-internals.md:22 @ 863e313`):

```
| `gateway/status.py` | Token lock management for profile-scoped gateway instances |
```

**侧 B**(模块 docstring,`gateway/status.py:1-11 @ 863e313`)自述为 PID 文件运行检测。

**代码事实**:两件事都在,但比例是 token/scoped 锁约 500 行(22%)、
PID/运行态/存活梯子/接管标记/风暴断路约 1750 行(78%)。而且
**"profile-scoped" 修饰错了对象** —— scoped 锁刻意是**机器级**的,因为它的目的正是
跨 profile 互斥:

`gateway/status.py:575-578 @ 863e313`
```python
        # Scoped credential locks are machine-global rather than
        # HERMES_HOME-local.  Persist the owning gateway's process home so an
        # explicit cross-profile --replace can place its planned-takeover
        # marker where the target process will actually read it.
```

**裁决:▲ 证实。** `gateway-internals.md:22` 把 22% 的次要职责写成全部,并把
"profile-scoped" 配错了对象。模块 docstring 不算证伪,但**已陈旧偏窄**:它的末句是
"a property that will be useful **when we add** named profiles" —— 将来时,
而 named profiles 早已落地并有整篇用户文档。第三侧
`website/docs/developer-guide/architecture.md:118`("Token locks, profile-scoped process
tracking")反而**最准**:**同仓两份开发者文档对同一文件精度不同,而更差的那份在更常被
引用的 Key Files 表里。**

> **可迁移原则(本轮新增)**:**模块 docstring 里出现将来时,就是它已过期的自证。**

### 1.6 R7B B-19 —— 五方言验签:⚠️ **收窄**,并新增两条 ▲

R7B 记为 "◇:五种签名方言在 `website/docs/**` 无完整枚举"。**本轮独立复核后必须收窄。**

`website/docs/user-guide/messaging/webhooks.md:453-462 @ 863e313` **准确记载了其中四种**
(GitHub `X-Hub-Signature-256`、GitLab `X-Gitlab-Token` 明文比对、自有 V2
`X-Webhook-Signature-V2` 含 ±300s 重放窗、自有 V1 已废弃且明说"没有重放保护")——
逐条与代码一致。

**真正缺的只有 Svix 一种**,而且缺得彻底:`svix` 与 `whsec_` 在**全仓所有 `.md`
与整个 `website/` 命中数为 0**(仅存在于 `gateway/platforms/webhook.py`、测试、
`scripts/release.py` 的致谢行)。

**裁决:◇ 成立但范围从 5/5 收窄为 1/5(Svix)。** 上一轮的措辞过宽,本轮更正。
**新增两条 ▲**(双侧证据见 `notes/r7c-raw-webhook-signing-docgap.md`):
- **▲**:中文镜像 `website/i18n/.../webhooks.md:452-460` 停在 V2 之前,把**有重放洞的 V1**
  讲成唯一通用方案 —— 英文卷补 V2 时中文卷没跟上,而 `tests/agent/test_i18n.py`
  只管 `locales/*.yaml`,**不覆盖 `website/i18n/`**。
- **▲**:响应码表(`webhooks.md:377-388`)自称穷举却漏掉两条 403 路径(路由禁用
  `webhook.py:621-624`、缺 secret `:658-666`),中英同缺。

**一处安全观察(■-5,见 §4)**:未鉴权即可枚举路由的存在/禁用/缺 secret 状态
(404/403/403/401 可区分),且全部早于限流,故探测不消耗配额。

### 1.7 R7B —— 审批解析器共用面:结案

**核心结论:hermes-agent 有两套完全独立的审批机制,共用同一批用户词汇
(`/approve` `/deny` 以及裸词),但只有一套有 ID 匹配。**

- **A 套 · 工具审批**(`tools/approval.py`):**没有 ID 匹配**。
  `resolve_gateway_approval`(`tools/approval.py:2490-2523`)只按 `session_key` 取 FIFO;
  适配器按钮 payload 里的 `approval_id` 仅用于查本地 `approval_id → session_key` 映射,
  查完即丢(例:`gateway/platforms/whatsapp_cloud.py:1796-1820`)。
  ⇒ **并行子代理场景下点第二个按钮会批准第一个请求。**
- **B 套 · slash 确认**(`tools/slash_confirm.py`,167 行):**有** `confirm_id` 比对、
  pop-before-run 幂等、300s 超时(`tools/slash_confirm.py:115-140`)。
  `/model` 的贵模型闸走这一套(`gateway/slash_commands.py:2400-2443`)。

**全平台共用的文本解析器在 `gateway/run.py:14646-14694`**:两级词表(命令形式
`event.get_command()` + 裸词 `_norm_reply`),`!` 前缀单独 `lstrip("!/")`
(适配器只重写 `!<已注册命令>`,而 `always`/`cancel` 不是命令,所以 `!` 会漏到这里),
工具审批优先于 slash-confirm,都不匹配则放行并 `clear_if_stale`。
**无模糊匹配、无前缀匹配、无编辑距离** —— 全部是硬编码集合。

**◇ 定案**:`gateway/platforms/base.py:3766` 的适配器契约要求按钮回调去调
`GatewayRunner._resolve_slash_confirm(confirm_id, choice)`,**该方法全仓不存在**;
真实契约是直接调 `tools.slash_confirm.resolve(session_key, confirm_id, choice)`。
**照文档写新适配器写不出来** —— 这是 R7B「幽灵 API」形态的又一例。

---

## 2. 本轮头等发现:三处「读一个 `MessageEvent` 没有的字段」

**这是本轮最值得记住的一条,因为它是同一个 bug 出现三次,而且三次都静默、三次都有绿测试。**

`MessageEvent` 的字段用 AST 全枚举(`gateway/platforms/base.py:2054 @ 863e313` 起):
`text` / `message_type` / `source` / `raw_message` / `message_id` / `platform_update_id` /
`media_urls` / `media_types` / `reply_to_message_id` / `reply_to_text` /
`reply_to_author_id` / `reply_to_author_name` / `reply_to_is_own_message` /
`prompt_response` / `auto_skill` / `channel_prompt` / `channel_context` / `internal` /
`metadata` / `timestamp`。

**没有 `content`,没有 `message`,没有 `session_id`。** 而这三个名字各被用了一次:

### ■-2 `/platform pause|resume` 生产不可达

`gateway/slash_commands.py:1440 @ 863e313`
```python
        text = (getattr(event, "content", "") or "").strip()
```
`content` 恒不存在 ⇒ `text` 恒为 `""` ⇒ 参数解析恒失败 ⇒ 永远退化成 `list` 子命令。
测试用 `MagicMock` 假造了该字段(`tests/gateway/test_platform_reconnect.py:406-408`),
所以**测试掩盖了它**。

### ■-3 `/footer on|off|status` 参数恒失效

`gateway/slash_commands.py:3885 @ 863e313`
```python
            text = (getattr(event, "message", None) or "").strip()
```
`message` 恒不存在 ⇒ `arg` 恒为 `""` ⇒ 恒走 toggle 分支(`:3915-3916`),
**连 `/footer status` 这条纯查询命令都会翻转状态**。而注册表
(`hermes_cli/commands.py:223-225`)与两份文档都宣称支持三态参数 —— 故同时是一条 ▲。

### ■-4 关停落盘的恢复路径生产恒失败

`gateway/shutdown_flush.py:146-147 @ 863e313`
```python
        for attr in ("session_id", "platform", "sender_id", "sender_name",
                      "reply_to", "media", "raw_event"):
```
**这 7 个属性,真实 `MessageEvent` 一个都没有**(它有的是 `source` / `raw_message` /
`media_urls` / `reply_to_message_id`)。于是落盘文件里永远没有 `session_id`,
恢复端恒走 `continue`:

`gateway/shutdown_flush.py:242 @ 863e313`
```python
                continue
```
⇒ 关停时落盘的待处理消息**永远恢复不回 DB**,永久堆在 `pending_messages/`
(该目录无 GC、无上限、无遥测)。测试之所以绿,是因为用 `MagicMock` 手工挂了
`session_id`(`tests/gateway/test_shutdown_flush.py:49-57`)。

> **共同形态**:Python 的 `getattr(obj, "name", default)` 与"鸭子类型 + MagicMock 测试"
> 组合起来,可以让**一个字段名的笔误静默存活到生产**,而且测试全绿。
> 三处独立犯了同一个错,说明这不是个人失误,是**缺少一个把事件形状钉死的机制**
> (dataclass 严格属性、`__slots__`、或测试里禁用 `MagicMock` 而用真实构造器)。
> 这条直接进成品章的「可迁移的设计原则」。

---

## 3. ▲ 定案(21 条,分簇列出;每条双侧证据见对应底稿)

### 3.1 接入清单 `ADDING_A_PLATFORM.md`(3 条,主线亲核,详见 `notes/r7c-01` §3)

- **▲-1** §8「Cron Delivery」让你去 `_deliver_result()` 改 `platform_map` ——
  `cron/` 全目录 `grep platform_map` 零命中;真落点是模块级常量表
  `_HOME_TARGET_ENV_VARS`(`cron/scheduler.py:264` 起)。**照做也做不到。**
  附带第二层失实:插件平台**改零行网关代码**(`cron/scheduler.py:1092-1095`),
  而 §8 说不改就 "silently fails"。
- **▲-2** §11「Channel Directory」给出的 `for plat_name in ("telegram", "whatsapp",
  "signal", "your_platform"):` 循环在 `gateway/channel_directory.py` **不存在**。
- **▲-3**(旁证,锚点在 `tools/`,不计入 R7C 定案数)§9 同样让你改一个不存在的
  `platform_map`。三步一起证明:**`platform_map` 曾经同时存在于两处,重构后两处都没了,
  文档两处都还在** —— 一次统一重构后整份清单未同步。

### 3.2 cron 文档(8 条)

- **▲-4** `cron-internals.md:73,92` 的 `running` 是**幽灵状态**:全仓 state 写入点
  (`cron/jobs.py:1415/1617/1641/1658/1752/1769/1785/1787/1878`)无一写 `"running"`;
  反倒有文档没提的 `"error"`(`:1769`)。在飞状态只存在于内存
  (`cron/scheduler.py:334` 的 `_running_job_ids`)。
- **▲-5** `cron-internals.md:85-101` 的 tick 伪码把并发与顺序都画反:代码在**执行前**
  批量前推 `next_run_at`(`cron/scheduler.py:4224`,at-most-once 的支点),
  用双池(`:4266-4267`),且不等待(`:4392-4412`)。
- **▲-6** `cron-internals.md:38-63` 的 job 示例 13 字段,实际 25 字段
  (`cron/jobs.py:1391-1428`),缺 `origin`/`workdir`/`run_claim`/`fire_claim` 等。
- **▲-7** `cron-internals.md:89` 说到期过滤 `state == "scheduled"`;代码过滤的是
  `enabled`(`cron/jobs.py:2291`)—— 差别正是 #16265 的修复要点。
- **▲-8** `cron-internals.md:270-272` 与 `AGENTS.md:1084-1086` 都断言 cron 投递
  **绝不**镜像进会话历史;代码有 `attach_to_session` 与 `cron.mirror_delivery` 两级开关
  (`cron/scheduler.py:640-648`,三处调用 `:727/:858/:951`),
  而**用户卷 `website/docs/user-guide/features/cron.md:348-363` 已完整文档化**。
  ⇒ **同一仓库两份文档互相矛盾,开发者卷是旧的那份。**(默认关,所以"默认行为"描述
  不算错,但作为**不变量**陈述是伪的。)
- **▲-9** `AGENTS.md:1061` 称支持 `"every monday 9am"`;`parse_schedule` 的
  "every X" 分支直接把 X 交给 `parse_duration`,而后者的正则只认「数字+单位」
  (`cron/jobs.py:553`)⇒ 抛 `ValueError`。**没有自然语言层。**
- **▲-10** `AGENTS.md:1074` 的 "**3-minute hard interrupt**" 双重失实:实际默认是
  **600 秒**,且是**不活跃**超时而非墙钟上限(`cron/scheduler.py:3562-3578`,
  `0` = 无限)。同一份 `cron-internals.md:216` 对此反而是**对的**。
- **▲-11** `cron-internals.md:250` 称裸名 `homeassistant` 投到 HA 会话;它在
  `_KNOWN_DELIVERY_PLATFORMS` 里却不在 `_HOME_TARGET_ENV_VARS` 里,插件也未注册
  `cron_deliver_env_var` ⇒ `cron/scheduler.py:1233-1235` 返回 None。
- **▲-12** `cron-internals.md:200-207` 把预跑脚本说成 "Python 脚本";
  bash 是一等公民(`cron/scheduler.py:2228-2229`、`:2290-2306`)。
- **▲-13** `cron-internals.md:126-128` 称 "firing 对所有 provider 一致";
  实际 Chronos 的 webhook 入口硬传 `adapters=None`
  (`gateway/platforms/api_server.py:5710-5712`、`hermes_cli/web_server.py:11966`)
  ⇒ E2EE 房间、可续聊 thread、in-channel 种子在 Chronos 下全部失效。
- **▲-14** `cron-internals.md:268` 说 `[SILENT]` 是 "prefix",
  `website/docs/user-guide/features/cron.md:440` 说 "contains";
  代码是**位置敏感**的(整条 / 首行 / 末行 + 无括号变体,
  `cron/scheduler.py:311-325`;`gateway/response_filters.py:84-85,98-110`),
  **句中出现照发不误**。两份文档各错一处。

### 3.3 关停 / 重启 / 环境变量(2 条)

- **▲-15** `website/docs/reference/environment-variables.md:760` 说
  `HERMES_RESTART_DRAIN_TIMEOUT` 默认 **900**;代码是 **0**
  (`hermes_cli/config_defaults.py:47` → `gateway/restart.py:23-25`)。
  **差 900 倍,且方向相反(文档说慢慢排水,代码是立刻进入强制中断)。**
  同一行第二处错:它说这是 `/restart` 的排水预算,而 `/restart` 实际走的是
  `restart_after_turn_timeout`(默认 21600s,`config_defaults.py:54`),
  代码注释就在旁边明说(`:45-46`)。
- **▲-16** `gateway/shutdown_watchdog.py:15-17` 的 docstring 称心跳供 "external
  supervision" 消费;全仓无任何 healthcheck / 监控 / systemd 单元读它,
  唯一消费者是死后取证(`gateway/lifecycle_ledger.py:200-202`)。

### 3.4 slash 命令(5 条)

- **▲-17** `/footer on|off|status`:注册表与文档宣称三态,实现恒 toggle(见 ■-3)。
- **▲-18** `/platform pause|resume`:文档描述的语义(停止投递 / 熔断器)与代码
  (重连队列)本就不同,而且参数解析恒失效(见 ■-2)。
- **▲-19** `/status` 承诺的 "Session recap" 从未实现;`hermes_cli/session_recap.py:244`
  的 `build_recap` 无生产调用点,而它自己的 docstring(`:13-16`)还宣称两端都在用。
- **▲-20** `gateway-internals.md:117` 说 `resolve_command()` 做前缀匹配;
  `hermes_cli/commands.py:367` 是纯 exact lookup。
- **▲-21** `/curator` 有注册(`hermes_cli/commands.py:283`,`cli_only=False`)、有文档、
  有菜单,**gateway 侧无 handler**;又因它在 `GATEWAY_KNOWN_COMMANDS` 里,
  unknown-command 兜底(`gateway/run.py:15615`)也不触发 ⇒ **原样当普通消息喂给 LLM**。
- **▲-22** `AGENTS.md:407` 让你把新 handler 加到 `gateway/run.py`;实际已搬到
  `gateway/slash_commands.py`(模块 docstring `:1-8` 自述)。
  同一 docstring 说 "42 of them (~3,200 LOC)",实测 **52 个 handler / 5,693 行**
  —— 又一处 docstring 时间腐烂。

*(§3 列出的编号超过 21,是因为 ▲-3 为旁证不计入、§1 与 §2 中另有若干 ▲ 已就地定案;
定案总数以 §0 汇总为准。)*

---

## 4. ■ 代码内部缺陷(6 条,只记录不修)

- **■-1 scale-to-zero 在生产环境永远不会休眠。** 纯函数没问题,**绑定有问题**:
  `_scale_to_zero_has_live_background_work` 的第一查是
  `any(not t.done() for t in self._background_tasks)`(`gateway/run.py:7437`),
  而 `_background_tasks` **不是"后台工作集合",是 `_spawn_supervised` 的
  "常驻守护任务注册表"**(`gateway/run.py:11611` 处入集)。网关启动时至少塞进 8 个
  **永不结束**的 watcher(`run.py:11475-11560`),**而 scale-to-zero watcher 自己也是
  用 `_spawn_supervised` 起的**(`run.py:11545`)⇒ 一旦 arm 成功,它自身就让条件恒真,
  `is_idle()` 恒 False。
  讽刺的是,同一函数的 docstring(`:7430-7436`)说得很清楚,它想数的是
  "backgrounded delegate_task / kanban / terminal(background=true)",
  而**第二查 `async_delegation.active_count()`(`:7440-7443`)才是那个正确机制**。
  第二个口子:`_scale_to_zero_is_idle` 用 `_running_agent_count()`(只数 agents)
  而非 `_active_work_count()`(agents + cron + api runs)——今天被恒真掩盖,修掉就会暴露。
  **根因是缺少一个"什么算 live background work"的单一权威定义** ——
  正对照 R7 已定案的「三个看门狗共用一钟」(#72039 单一进度源契约)。
- **■-2 / ■-3 / ■-4**:三处幽灵字段,见 §2。
- **■-5 webhook 路由状态未鉴权可枚举**:404 / 403(路由禁用)/ 403(缺 secret)/ 401
  四态可区分,且全部早于限流,探测不消耗配额;而**同一文件 `:610-615` 却刻意伪装
  profile 绑定以防枚举** —— 同一处的取舍不自洽。
- **■-6 pairing 无跨进程锁**:见 §1.1。同型问题也出现在 `cron/suggestions.py:53`
  (只有 `threading.Lock()`,而 `cron/jobs.py:104-108` 早已因 #60703 升级为跨进程 flock,
  且 `suggestions.py:24-25` 的 docstring 还写着 "Storage mirrors cron/jobs.py")。

**三个休眠机制(与 R7 的 `memory_monitor.py` 同型,合并记为本轮的接线核查结论)**:

| 机制 | 状态 | 证据 |
|---|---|---|
| `DeliveryRouter.deliver()` | 零生产调用点 | `grep -rn "\.deliver(" --include=*.py .` 只命中 `tests/gateway/test_dead_targets.py:79/85/102` |
| `gateway/dead_targets.py` 整模块 | 休眠 | 三个调用点(`gateway/delivery.py:350/370/382`)全在不可达的 `deliver()` 内 |
| `self.delivery_router` | **被维护的休眠对象** | `gateway/run.py:5935` 构造,`:7323`/`:11348`/`:12488` 三处认真同步 `.adapters`,**从不调用任何方法** |

最后一行比纯死代码更危险:**有人在持续维护它,所以读代码的人会以为它活着。**

---

## 5. ◇ 定案(14 条,择要;全列见各底稿)

- **◇-1 整个关停/排水子系统在 `website/docs/` 与根 `AGENTS.md` 完全缺席**
  (`gateway-internals.md` grep `shutdown|drain|SIGTERM|graceful` 零命中)。
  零覆盖项包括:`.drain_request.json` 契约、实例化 epoch、两个看门狗、
  `gateway.heartbeat`、`gateway.lifecycle.json`、`pending_messages/`、
  三个诊断日志、`.clean_shutdown`、exit code 75/78。**这是本轮最大的文档空白区。**
- **◇-2 `gateway.loop_watchdog`**(`gateway/config.py:937-938`)—— 一个能关掉
  进程级硬退出兜底的开关,配置文档零提及。
- **◇-3 `gateway/code_skew.py` 与 `_model_switch_skew_guard`** 全无文档:
  长跑网关 + 延迟 import + `git pull` = 新旧模块混用崩溃,只在换模型这一个
  最高风险入口挡了一道。
- **◇-4 心跳文案的真开关 `long_running_notifications: generic` 全站零文档** ——
  只有取值为 `generic` 时才读 `status_phrases.yaml`(`gateway/run.py:25037-25041`),
  否则走硬编码 `⏳ Working — N min`。**即短语库默认不生效**,而
  `messaging/index.md:452` 与 `:741` 两段各自为真的话拼出了"默认读 yaml"的假印象。
- **◇-5 `display.busy_steer_ack_enabled`** 有实现与默认值
  (`gateway/display_config.py:50-54`),website/README/AGENTS 三处零命中。
- **◇-6 静默叙述过滤**(`gateway.filter_silence_narration` /
  `HERMES_FILTER_SILENCE_NARRATION`)整个机制全仓文档零提及。
- **◇-7 kanban 完成会唤醒创建者 agent 跑一轮**(有 token 成本),文档全无;
  且 `kanban.md:836` 说评论要"*next* run 才读到",实际已有 mid-run steer。
- **◇-8 cron 的"可续聊"一簇**(`cron/scheduler.py:754-971`)是本簇代码量最大的
  新机制之一,开发者卷零提及(用户卷有)。
- **◇-9 `check_gateway_lifecycle` 只在 create 生效,update 完全绕过** ——
  子代理在隔离 `HERMES_HOME` 里实证:`cronjob(action="update", prompt="hermes gateway
  restart")` 返回 `success=True` 并落库。脚本路径更无残余防线
  (`cron/scheduler.py:2329` 直接 `subprocess.run`,不经 terminal_tool)。
- **◇-10 `executions.db` 没有 profile 作用域**(`cron/executions.py:20` 在 import 期冻结),
  而 `jobs.py` 为此专门做了 `_current_cron_store()` ⇒ multiplex 下所有 profile 共用
  一个审计账本,与 `cron/scheduler_provider.py:275-277` 自己的 docstring 矛盾。
- **◇-11 频道目录零 profile 隔离**(`gateway/channel_directory.py:21,36` 模块级求值,
  全文件无 `profile` 字样)。
- **◇-12 蓝图清单不可能漂移**(构建期生成 + gitignore + 前端 fetch)——
  **本簇最值得抄的设计**,与手写的建议清单形成对照。
- **◇-13 `builtin_hooks/` 是有意留白,不是事故**:`gateway/hooks.py:72-79` 空 return、
  包零 import,但 `website/docs/user-guide/features/hooks.md:344-346` 完整记载了
  "早期内置钩子已删成文档教程",`AGENTS.md:249` 标注 "(none shipped)"。
  **四方一致** —— 与 `memory_monitor.py` 性质**相反**,记录在案以免后续轮次误判。
- **◇-14 全仓有两套互不相干的钩子系统**:`gateway/hooks.py`(文件系统发现,仅网关)
  与 `hermes_cli/lifecycle.py::invoke_hook`(插件注册,CLI+网关),
  同一次 `handle_message` 里都会出现。

---

## 6. 本轮规律

R7 的三条("机制方向大体对、分支图谱与精确值系统性滞后;用户文档常比开发者文档新;
接线声明也会说谎")与 R7B 的两条("docstring 也会腐烂";"要让文档不腐烂,唯一可靠
手段是让它可执行")**全部复现**。本轮新增三条:

1. **docstring 的腐烂有两种形态,时间腐烂比路径腐烂更隐蔽。**
   R7B 发现的是**路径腐烂**(文件搬家,引用失效)。本轮发现的是**时间腐烂**:
   `status.py` 的 docstring 写于模块诞生时,里面的将来时("when we add named profiles")
   就是化石层的时间戳;`slash_commands.py` 的 "42 of them (~3,200 LOC)" 是另一块。
   **判据:模块 docstring 里出现将来时或具体计数,就该怀疑它已过期。**

2. **测试通过 ≠ 机制在生产中工作,而且测试可以把 bug 固化成规格。**
   本轮三例(见 `notes/r7c-95` §5.1)的共同点是:**测试构造的对象形状与生产构造点
   不一致** —— `MagicMock` 补字段、注册表置空、monkeypatch 掉被测谓词。
   R7 的 `memory_monitor.py` 是"有测试零调用点",本轮更进一步:
   **有测试、有调用点、调用点在生产中恒失败。**

3. **"被维护的休眠对象"比死代码更危险。** `self.delivery_router` 有构造、有三处
   认真的状态同步、从不被调用。死代码至少看得出是死的;**一个被持续维护却从不被
   调用的对象,会让每个读代码的人误以为它是主路径。**
   接线核查必须查"有没有人调用它的方法",而不是"有没有人提到它"。

---

## 7. 向后续轮次移交

- **`tools/kanban_tools.py:350-414` + `agent/run_agent.py:3710`**(kanban 评论 steer 本体):
  R7 A6 原定位在 `kanban_watchers.py`,本轮更正后其锚点落在 R2/R3 域。
  本轮已给出完整链路与判据(§1.3),**机制本身已讲清,不需要另开轮次**;
  若 R12 蓝图要写"带外注入"一章,直接引用本轮结论即可。
- **`hermes_cli/status.py` 的 QQBot 环境变量倒置**(`notes/r7c-01` §3.4):
  锚点在 `hermes_cli/`(R8 桶),本轮作为跨簇发现记录,R8 复核时确认是否仍在。
- **`tools/approval.py` 的 FIFO 无 ID 匹配**(§1.7 A 套):锚点在 `tools/`(R3 已读),
  本轮从网关侧给出了它的用户可见后果(并行子代理点错按钮)。
  建议 R11 复盘时回填进 R3 章节,而不是另开轮次。
