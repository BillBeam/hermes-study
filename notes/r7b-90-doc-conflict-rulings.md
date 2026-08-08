# r7b-90 · 文档-代码冲突定案(R7B)

> 底稿。基线 `863e31318553cda8ad61df681d08175364d4164b`。
> 记号:**▲** = 文档所述与代码矛盾(证伪);**◇** = 代码有真实机制而文档无载。
> 每条给出双方原文与溯源,读本文件即完成验证。

## 0. 汇总

**24 条:▲ 6 条(含 R7 移交 1 条定案)、◇ 18 条。**
*(R8-fix 修正:原记 ▲ 7 / ◇ 17。B-4 经 review-1 阻断-4 复核后由 ▲ 降为 ◇——
文档没有说过原判归给它的那句话,矛盾不存在。总数 24 不变,见本文件 B-4 节的改判说明。)*
其中 1 条(B-13)是**本学习项目上一轮报告**的简化,非仓库文档问题,单列并更正。

## 1. R7 移交项定案

### ▲ B-1 —— 第一层守卫"设置中断事件":**证伪**

**文档**(`website/docs/developer-guide/gateway-internals.md:86 @ 863e313`):

> 1. **Level 1 — Base adapter** (`gateway/platforms/base.py`): Checks `_active_sessions`.
>    If the session is active, queues the message in `_pending_messages` **and sets an
>    interrupt event**. This catches messages *before* they reach the gateway runner.

中文镜像同错(`website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/developer-guide/gateway-internals.md:86 @ 863e313`):
"将消息加入 `_pending_messages` 队列**并设置中断事件**"。

**代码**:base.py 全文只有一处 `.set()`,且不在 `handle_message` 里:

```
$ grep -n "\.set()" gateway/platforms/base.py
4813:                interrupt_event.set()
```

该处属于 `interrupt_session_activity`(`gateway/platforms/base.py:4808-4813 @ 863e313`):

```python
    async def interrupt_session_activity(self, session_key: str, chat_id: str, metadata=None) -> None:
        """Signal the active session loop to stop and clear typing immediately."""
        if session_key:
            interrupt_event = self._active_sessions.get(session_key)
            if interrupt_event is not None:
                interrupt_event.set()
```

其生产调用点全部在**第二层或其代理**:

```
$ grep -rn "interrupt_session_activity" --include=*.py . | grep -v "^./tests/"
./gateway/relay/adapter.py:626:        await self.interrupt_session_activity(session_key, chat_id)
./gateway/run.py:23127:                await adapter.interrupt_session_activity(
./gateway/run.py:23131:                await adapter.interrupt_session_activity(session_key, source.chat_id)
```

**定案**:置中断位是**第二层(GatewayRunner)的动作**,反向调进适配器;第一层从不置位。
第一层的忙时行为是「命令旁路 / 入单槽 / 交给 `_busy_session_handler`」三选一
(`gateway/platforms/base.py:5592-5744 @ 863e313`)。文档把两层动作合并叙述,
会让读者以为"消息一进适配器就打断当前回合"——恰恰相反。

R7 移交项**结案**。

## 2. 新立 ▲(6 条)

### ▲ B-2 —— `/stop` 与 `/approve` 走同一条 inline 路:**证伪**

**文档**(`website/docs/developer-guide/gateway-internals.md:59-61 @ 863e313`):

> 2. **Base adapter** checks active session guard:
>    - If `/approve`, `/deny`, `/stop` → bypass guard (dispatched inline)

**代码**:两类命令走**不同**路径(`gateway/platforms/base.py:5611-5625 @ 863e313`):

```python
                # /stop, /new, /reset must cancel the in-flight adapter task
                # and preserve ordering of queued follow-ups.  Route those
                # through the dedicated handoff path that serializes
                # cancellation + runner response + pending drain.
                # (Registry-derived: busy_policy == "interrupt_then_dispatch".)
                if cmd and is_interrupt_then_dispatch(cmd):
                    self._discard_text_debounce(session_key)
                    try:
                        await self._dispatch_active_session_command(event, session_key, cmd)
```

`/approve` `/deny` 才走注释所称的 "Other bypass commands … just need direct dispatch —
they don't cancel the running task"(`gateway/platforms/base.py:5627-5630 @ 863e313`)。

**定案**:两者都"绕过守卫",但一类只读、一类改写会话生命周期,合并叙述会误导实现者。

### ▲ B-3 —— `ADDING_A_PLATFORM.md` 指向的参考实现文件不存在

**文档**(`gateway/platforms/ADDING_A_PLATFORM.md:125 @ 863e313`):

> See `gateway/platforms/telegram.py`, `discord.py`, and `whatsapp_cloud.py` for
> reference implementations.

同文件 `gateway/platforms/ADDING_A_PLATFORM.md:58-61 @ 863e313`
*(R8-fix 修正锚点:原写 `:66-70`,那五行讲的是"mixin 必须排在基类前",与本条无关;
"WhatsApp does this" 这段实际在 `:58-61`,所属段落起于 `:55`。)*:

> WhatsApp does this: `gateway/platforms/whatsapp.py` (Baileys bridge) and
> `gateway/platforms/whatsapp_cloud.py` (Meta Cloud API) both inherit from
> `WhatsAppBehaviorMixin` in `gateway/platforms/whatsapp_common.py`.

**代码**:

```
$ for f in gateway/platforms/telegram.py gateway/platforms/discord.py gateway/platforms/whatsapp.py; do
    [ -f "$f" ] && echo "EXISTS: $f" || echo "MISSING: $f"; done
MISSING: gateway/platforms/telegram.py
MISSING: gateway/platforms/discord.py
MISSING: gateway/platforms/whatsapp.py
```

telegram / discord 迁至 `plugins/platforms/*/adapter.py`;Baileys 版 WhatsApp 在
`plugins/platforms/whatsapp/adapter.py:381 @ 863e313`(**确实**继承 `WhatsAppBehaviorMixin`,
所以结论对、路径错)。

**定案**:三处路径失实。同文档 "Quick Verification" 一节给出的自检 grep
(`gateway/platforms/ADDING_A_PLATFORM.md:400-402 @ 863e313`)**扫描集里没有 `plugins/`**,
所以这类漂移不会被它自己的验证手法发现。

> **R7C 修订(2026-08-07)**:此处原写作"§16 给出的自检 grep 只扫 `gateway/`",两点失准,
> 现更正 —— **结论不变**。
> (a) 该 grep 的扫描集是**六个路径**,不止 `gateway/`:
>
> `gateway/platforms/ADDING_A_PLATFORM.md:400-402 @ 863e313`
> ```bash
> # Grep for your platform name to find any missed integration points
> grep -r "telegram\|discord\|whatsapp\|slack" gateway/ tools/ agent/ cron/ hermes_cli/ toolsets.py \
>   --include="*.py" -l | sort -u
> ```
> (b) 它不在 §16(§16 是 "Tests",`:372`),而在其后的 "## Quick Verification"
> (`:392`)一节。
> **结论为什么不变**:六个路径里**依然没有 `plugins/`**,而 B-3 的三处失效路径指向的正是
> `plugins/platforms/*/adapter.py`。扫描集更大,但恰好漏掉了唯一相关的那个目录 ——
> 自检手法发现不了自己这条 ▲,这一判断成立。

### ◇ B-4 —— 相邻两节讲的是两套降级机制,而文档从不说破哪五个方法没有基类桩

> **R8-fix 改判(review-1 阻断-4 / M-4a):原定 ▲,现降为 ◇,锚点由 `:105` 改为 `:103` / `:113`。**
> 原判说文档"把三个基类没有的方法列在『有基类默认桩』的标题下"。**这一点不成立**:
> 那个标题下只有五个媒体方法,而它们在基类里都有实现;三个交互方法在**紧随其后的另一个标题**下。
> ▲ 的定义是"文档所述与代码矛盾",这里文档没这么说,矛盾不存在,故撤 ▲。
> 下面是重新取证后的定案。原判的**代码侧全部成立**,错的是把两个小节当成了一个。

**文档 · 第一节**(`gateway/platforms/ADDING_A_PLATFORM.md:103 @ 863e313`):

> ### Optional methods (have default stubs in base)

该标题辖下只有 `:105-111` 的**五个媒体方法**表格(`send_document` / `send_voice` /
`send_video` / `send_animation` / `send_image_file`)。**这五个在基类里确实都有实现**,
所以该标题对它自己的表格是**准确的**:

`gateway/platforms/base.py:3991 @ 863e313`

```python
    async def send_animation(
```

(另四个同形:`:4062` `send_voice`、`:4205` `send_video`、`:4232` `send_document`、
`:4305` `send_image_file`。)

**文档 · 第二节**(`gateway/platforms/ADDING_A_PLATFORM.md:113 @ 863e313`):

> ### Interactive UX (recommended if your platform supports tappable buttons)

这是**另一个标题**,辖下是 `:117-123` 的五个交互方法表格,唯一的行为承诺在 `:115`:

`gateway/platforms/ADDING_A_PLATFORM.md:115 @ 863e313`

> If your platform supports interactive button/menu messages, implement these for a more polished agent experience. They all degrade gracefully to plain text when not overridden:

**代码**:这一节的五个方法里,**两个有基类桩、三个没有**,而文档对这个分界只字未提。

```verify
$ grep -nE "def (send_clarify|send_slash_confirm)" gateway/platforms/base.py
3745:    async def send_slash_confirm(
3780:    async def send_clarify(
$ grep -nE "def (send_exec_approval|send_model_picker|send_choice_picker)" gateway/platforms/base.py ; echo "exit=$?"
exit=1                     # 零命中
```

优雅降级**真实存在**(所以 `:115` 那句话为真),但那三个的降级实现在调用点的**类型探测**:

```python
            and getattr(type(adapter), "send_choice_picker", None) is not None
```

(`gateway/slash_commands.py:3463 @ 863e313`;`send_model_picker` 同形于
`gateway/slash_commands.py:1779 @ 863e313`;`send_exec_approval` 于
`gateway/run.py:5181 @ 863e313`)

**定案(◇,文档缺口而非文档矛盾)**:同一份文档用**相邻两节**表达了**两套不同**的降级机制
——`:103` 那节是"基类有桩",`:113` 那节是"调用点类型探测"——但从不说破后者是另一套,
更不说破该节五个方法里**只有两个**(`send_clarify` / `send_slash_confirm`)有基类桩。
实现者无法从文档得知 `send_exec_approval` / `send_model_picker` / `send_choice_picker`
没有可 `super()` 的默认实现;他不会撞见 `AttributeError`(因为没人叫他去调 `super()`),
但他**也无从判断这三个方法是"可以不写"还是"必须自己从零写"**——而这正是这一节存在的目的。

**为什么原判会指错**:两个小节在文档里只隔一张五行表格,而它们的**标题措辞刚好互补**
(一个说"有默认桩",一个说"不覆盖就降级")。读到第二节的承诺时,很容易把它挂回第一节的标题。
**教训与阻断-1 同形**:判定一条文档断言时,**要先确认它归哪个标题管**——
文档的层级结构本身就是断言的一部分,而这一层从来没有被任何脚本校验过(见 M-16a)。

### ▲ B-5 —— `whatsapp_cloud.py` 自己的模块 docstring 指向不存在的兄弟文件

**文档**(`gateway/platforms/whatsapp_cloud.py:7-12 @ 863e313`,**代码文件自身的 docstring**):

```
- ``whatsapp.py``      — unofficial Baileys bridge, personal accounts, no
                         public URL needed, account-ban risk.
- ``whatsapp_cloud.py`` (this file) — official Meta Cloud API, Business
                         account required, public webhook URL required,
                         token-based auth.
```

**代码**:`gateway/platforms/whatsapp.py` 不存在(见 B-3 的 `for` 循环输出)。

**定案**:与 B-3 同一次迁移留下的第二处滞后。价值在于它**不在 markdown 里,在 .py 里** ——
把 R7 的规律再推进一格:**"接线声明"会说谎,同一个包内的模块 docstring 也会说谎。**

### ▲ B-6 —— `docs/session-lifecycle.md` 把单槽写成"覆盖"

**文档**(`docs/session-lifecycle.md:455-457 @ 863e313`):

```
adapter._pending_messages: Dict[session_key, MessageEvent]
    └── Single "next-up" slot per session. Overwritten on repeat sends
        (burst collapse). Shared with photo-burst follow-ups.
```

**代码**:`merge_pending_message_event` 有**四条**分支(`gateway/platforms/base.py:2455-2499 @ 863e313`):
双方 PHOTO → 媒体列表**拼接**(`:2463-2469`);任一方带媒体 → **合并**(`:2472-2489`);
`merge_text=True` 且双方 TEXT → **逐行追加**(`:2491-2497`);其余才是覆盖(`:2499`)。

**定案**:"overwritten" 只对第四条成立。按文档理解会以为连拍只留最后一张。

### ▲ B-7 —— `AGENTS.md` 的两层守卫条款遗漏第一层的策略机接口

**文档**(`AGENTS.md:1241-1246 @ 863e313`):

> When an agent is running, messages pass through two sequential guards:
> (1) **base adapter** (`gateway/platforms/base.py`) queues messages in
> `_pending_messages` when `session_key in self._active_sessions`, and
> (2) **gateway runner** (`gateway/run.py`) intercepts `/stop`, `/new`, …

**代码**:第一层在入槽**之前**先问 `_busy_session_handler`
(`gateway/platforms/base.py:5711-5713 @ 863e313`):

```python
            if self._busy_session_handler is not None:
                try:
                    if await self._busy_session_handler(event, session_key):
                        return
```

返回 True 即**完全不入槽**。R7 已定案 interrupt/queue/steer/redirect 四种忙时策略
都由这个回调承载。

**定案**:程度轻于 B-1(方向没错),但"一律入槽"的表述会让人以为第一层没有可插拔策略面。
该条款本身是给贡献者的行为准则("新命令必须绕过两层"),这部分**正确**,不推翻。

## 3. 新立 ◇(17 条)

按簇归并列出;每条均给出溯源,详细论证见对应底稿。

### 3.1 base.py 契约面(`r7b-10`)

- **◇ B-8**:`render_message_event` 的"呈现层不得回流历史"宪法条款
  (`gateway/platforms/base.py:3040-3042 @ 863e313`:"nothing rendered here is persisted
  to conversation history. History is owned by the agent") —— 跨平台一致性的核心不变量,
  `website/docs/**` 与 `AGENTS.md` 均无对应描述。
- **◇ B-9**:能力探测一律走 `type(adapter)` 而非实例,全仓一致
  (`gateway/slash_commands.py:1779`、`:3463`、`gateway/run.py:5181`、`:23113-23114` @ 863e313),
  无任何文档陈述这条约定。
- **◇ B-10**:平台锁的 takeover **只在显式 `gateway run --replace` 首连时武装**,
  重连永不抢锁(`gateway/platforms/base.py:2770-2774 @ 863e313`)—— 无文档。

### 3.2 第一层守卫(`r7b-20`)

- **◇ B-11**:#17758(递归排水致 C 栈耗尽 SIGSEGV → 改 `create_task` 交棒,
  `gateway/platforms/base.py:6324-6338 @ 863e313`)与 #48300(释放-删属主顺序错误
  致永久死锁,`:6492-6510`)两条因果链只存在于代码注释;`docs/session-lifecycle.md`
  讲了数据结构,未讲**回合链交棒与属主转移**。
- **◇ B-12**:clarify 文本拦截(`gateway/platforms/base.py:5656-5706 @ 863e313`)
  与 `/approve` 死锁同类同修法,两份文档均无载。

### 3.3 媒体与出网(`r7b-30`)

- **◇ B-13**:媒体投递两模式与三个环境变量
  (`HERMES_MEDIA_DELIVERY_STRICT` / `HERMES_MEDIA_ALLOW_DIRS` /
  `HERMES_MEDIA_TRUST_RECENT_SECONDS`,`gateway/platforms/base.py:1150-1156 @ 863e313`)
  在全部文档中**零命中**:

```
$ grep -rln "HERMES_MEDIA_" website/ docs/ *.md
(无输出)
```

  这是一条**安全决策**(公开部署是否开严格模式),该进文档而没进。
- **◇ B-14**:允许根**优先于**内置拒绝名单
  (`gateway/platforms/base.py:1191-1194 @ 863e313`)—— "运营方意图胜过内置策略"
  的语义无文档。
- **◇ B-15**:入站媒体上限 `gateway.max_inbound_media_bytes`(默认 128 MiB,`0` 关闭,
  `gateway/platforms/base.py:709-723 @ 863e313`)全部文档零命中:

```verify
$ grep -rln "max_inbound_media_bytes" website/ docs/ *.md ; echo "exit=$?"
exit=1                     # 零命中;该键只出现在 .py 里
$ grep -rln "max_inbound_media_bytes" --include=*.py .
./gateway/platforms/base.py
./hermes_cli/config_defaults.py
./tests/gateway/test_platform_base.py
./plugins/platforms/discord/adapter.py
```

### 3.4 api_server(`r7b-40`)

- **◇ B-16**:`/api/platforms/{platform}/events` 与 `/api/cron/fire` **不用**
  `API_SERVER_KEY`,各有独立信任来源(平台签名 / NAS 签发 JWT,
  `gateway/platforms/api_server.py:2009-2012`、`:2030-2032 @ 863e313`)。
  "一个端口上并存三种鉴权"直接影响暴露决策,无文档。
- **◇ B-17**:`_derive_chat_session_id` 的会话指纹派生
  (`gateway/platforms/api_server.py:1264-1279 @ 863e313`)—— 无状态客户端能用上
  有状态会话的全部原因,且带"首句相同则撞会话"的实际后果,无文档。
- **◇ B-18**:`gateway.api_server.max_concurrent_runs`
  (`gateway/platforms/api_server.py:1559-1568 @ 863e313`)与 #38803 的
  不可重试分类(`:6991-6999`,误分类致 2.5 天泄漏 1002 fd)只见于代码。

### 3.5 适配器(`r7b-50`)

- **◇ B-19**:通用 webhook 支持的**五种签名方言**(Svix / GitHub / GitLab /
  自有 V2 / 自有 V1,`gateway/platforms/webhook.py:1040-1130 @ 863e313`)
  在 `website/docs/**` 无完整枚举 —— 这是"我的 SaaS 能否直接对接"的能力清单。
- **◇ B-20**:双栈绑定的完整推理(为何 `None` 而非 `0.0.0.0` 或 `::`,
  `gateway/platforms/webhook.py:111-129 @ 863e313`)与 `SO_REUSEADDR` 的
  macOS/Linux 语义分叉(`:307-320`)只在代码注释。
- **◇ B-21**:Signal 附件速率的**本地令牌桶模拟 + 429 反向校准**
  (`gateway/platforms/signal_rate_limit.py:2-14 @ 863e313`)无文档。
- **◇ B-22**:`_http_client_limits` 的 #18451(7 个长驻适配器 × httpx 默认
  keepalive 撞 256 fd 上限,`gateway/platforms/_http_client_limits.py:12-19 @ 863e313`)
  与其两个调优环境变量只在代码注释。

### 3.6 relay(`r7b-60`)

- **◇ B-23**:`delivered_via_upstream_relay` 的"本地盖章、**永不读线**"不变量
  (`gateway/relay/ws_transport.py:232-240 @ 863e313`)是 relay 授权模型的支点,
  仅存在于代码注释。
- **◇ B-24**:relay 三个模块头标注 EXPERIMENTAL 并给出**转正条件**
  ("until >=2 Class-1 platforms validate it",`gateway/relay/transport.py:18-20 @ 863e313`),
  但 `README.md` / `AGENTS.md` 未向运营方提示 relay 尚未定稿;
  自举为何**不用** `is_managed()` 的推理(`gateway/relay/__init__.py:578-585 @ 863e313`)
  与双 IdP 支持(`:491-512`)同样无用户文档。

> **relay 的例外说明**:`tests/gateway/relay/test_contract_doc_conformance.py`
> 把代码与 `docs/relay-connector-contract.md` 做一致性检查(本轮通过)。
> 所以 relay 是本轮**开发者契约文档一致性最好**的一簇;上列 ◇ 均指向
> **用户/运营文档**缺口。这一对照本身是本轮最有价值的观察之一(见 §5)。

## 4. 非仓库文档:本项目上一轮报告的更正

### B-25(项目内更正,不计入 ▲/◇)

R7 报告 §8 与本轮任务简报称 api_server 的会话绑定头是 `X-Hermes-Session-Id`。
代码里是**两个正交的头**(`gateway/platforms/api_server.py:2051-2059 @ 863e313`):

```python
        The session key is a stable per-channel identifier that scopes
        long-term memory (e.g. Honcho sessions) across transcripts.  It
        is independent of ``X-Hermes-Session-Id``: callers may send
        either, both, or neither.
```

- `X-Hermes-Session-Id` = **哪一段转写**(续接历史,`/new` 时轮换);
- `X-Hermes-Session-Key` = **谁的记忆**(长期记忆作用域,跨转写不变)。

两者都要求 API key 鉴权,但堵的方向不同:id 防**读**别人历史(`:3954-3958`),
key 防**写进**别人的记忆域(`:2058-2062`)。R7 报告的简化在此更正。

## 5. 本轮规律

R7 归纳的"机制方向大体对、分支图谱与精确值系统性滞后;用户文档常比开发者文档新;
接线声明也会说谎"在本轮**全部复现**,并新增两条:

1. **说谎的载体从 markdown 蔓延到 .py 的模块 docstring**(B-5)。文件迁移时,
   markdown 里的路径引用和代码注释里的路径引用**同样会腐烂**,而后者更难被发现 ——
   `ADDING_A_PLATFORM.md` 自带的自检 grep 扫 `gateway/ tools/ agent/ cron/ hermes_cli/ toolsets.py`
   六个路径,**唯独不含 `plugins/`** —— 而 B-3 的失效路径正指向 `plugins/platforms/*/adapter.py`,
   于是它连自己这条 ▲ 都发现不了。
   *(R7C 修订:原写作"只扫 `gateway/`",扫描集表述有误,结论不变;双侧证据见本文件 B-3 定案段。)*

2. **"有测试守着的文档"与"没测试守着的文档"是两个物种**。relay 有
   `test_contract_doc_conformance.py`,于是它的开发者契约文档是全仓最准的;
   `gateway-internals.md` / `session-lifecycle.md` / `ADDING_A_PLATFORM.md` 没有,
   于是本轮 7 条 ▲ 里有 6 条出自它们。**结论:要让文档不腐烂,唯一可靠的手段是
   让它可执行。**这条直接进成品章的"可迁移的设计原则"。

## 6. 向后续轮次移交

- `gateway/platforms/qqbot/{chunked_upload,keyboards,onboard}.py`、
  `yuanbao_{proto,media,sticker}.py`、`msgraph_webhook.py`、`webhook_filters.py`
  本轮按"结构 + 决定性机制"读到 L1 深度,但**分片上传协议**与
  **元宝私有协议帧格式**两处未逐字段展开成互操作规格;若 R12 蓝图需要,
  在 R11 复盘时补一节即可,不另开轮次。
- `plugins/platforms/**`(22 个插件适配器,含 telegram 10,147 行)仍在 R6 插件桶,
  维持 L2;R7B 已把它们依赖的**基类契约**钉死,插件轮次可直接建立在本轮结论上。
