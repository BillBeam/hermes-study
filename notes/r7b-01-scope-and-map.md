# r7b-01 · 本轮范围钉定与平台接入面地图

> 底稿。基线 `863e31318553cda8ad61df681d08175364d4164b`,全部断言溯源 `路径:行号 @ 863e313`。

## 1. 范围:台账 `round=R7B`,37 文件 / 43,815 行,不增不删

R7 报告开轮时已把原 R7(gateway/ + cron/,100 文件 110,440 行)切成三片,R7B 定为
「gateway/platforms/\*\* + relay/\*\*」。本轮核对台账,与磁盘实际完全一致:

```
$ awk -F'\t' '$5=="R7B"{n++; s+=$3} END{print n" files, "s" lines"}' data/ledger.tsv
37 files, 43815 lines
```

其中 36 个 `.py`(43,411 行,全部 L1)+ 1 个 `gateway/platforms/ADDING_A_PLATFORM.md`
(404 行,L2 —— 它是"作者自绘地图",按 CLAUDE.md 属文档,归 L2 但本轮逐条校验)。

行数最大的 6 个文件占全簇 62%:

| 文件 | 行数 | 角色 |
|---|---|---|
| `gateway/platforms/api_server.py` | 7,188 | OpenAI 兼容 HTTP 入口 |
| `gateway/platforms/base.py` | 6,861 | 适配器基类契约 + 第一层守卫 |
| `gateway/platforms/yuanbao.py` | 5,298 | 元宝(消费级产品前置) |
| `gateway/platforms/qqbot/adapter.py` | 3,273 | QQ 机器人 |
| `gateway/platforms/weixin.py` | 2,419 | 微信 |
| `gateway/relay/adapter.py` | 2,144 | 一对多中继适配器 |

### 1.1 增删决策(逐条说明理由)

任务简报点名「telegram topic 适配」。查证后**不增补** `plugins/platforms/telegram/`:

- topic 适配的**契约面在 R7B 范围内**:钩子安装点与改写逻辑都在 base.py
  (`gateway/platforms/base.py:3311-3344 @ 863e313`),入口门控在 handle_message
  (`gateway/platforms/base.py:5568-5576 @ 863e313`);
- topic 适配的**实现面在 R7 已完成范围内**:三个安装点全部在 run.py,钩子函数
  `_recover_telegram_topic_thread_id` 也在 run.py:

```
$ grep -rn "topic_recovery" --include=*.py . | grep -v '^./tests/'
./gateway/run.py:11100:            adapter.set_topic_recovery_fn(self._recover_telegram_topic_thread_id)
./gateway/run.py:12472:                    adapter.set_topic_recovery_fn(self._recover_telegram_topic_thread_id)
./gateway/run.py:13414:        adapter.set_topic_recovery_fn(self._recover_telegram_topic_thread_id)
./gateway/platforms/base.py:2762:        self._topic_recovery_fn: Optional[Callable[[Any], Optional[str]]] = None
./gateway/platforms/base.py:3311:    def set_topic_recovery_fn(
./gateway/platforms/base.py:3325:    def _apply_topic_recovery(self, event: MessageEvent) -> None:
./gateway/platforms/base.py:5570:        needs_topic_recovery = (
./gateway/platforms/base.py:5576:            await asyncio.to_thread(self._apply_topic_recovery, event)
./plugins/platforms/telegram/adapter.py:8909:        self._apply_topic_recovery(event)
```

  插件侧只剩**一行调用**(`plugins/platforms/telegram/adapter.py:8909 @ 863e313`)。
- 反面代价明确:`plugins/platforms/telegram/adapter.py` 有 10,147 行、台账 `L2 / round=R6`
  (插件生态桶)。为一行调用把它整体提到 L1,会让 R7B 膨胀 23% 且与插件轮次重复。

**定案**:R7B 覆盖 topic 适配的**契约与门控**(base.py 侧),并在底稿中把插件侧调用点作为
交叉引用溯源;`plugins/platforms/telegram/adapter.py` 本体维持 L2 / R6 桶不动。

## 2. 平台接入面全景:三条入站血统

R1 已知"24 个 Platform 枚举 + 22 个插件"。R7B 的结构性发现是:**枚举数不等于内建适配器数**。
`Platform` 枚举 24 个成员(`gateway/config.py:280-303 @ 863e313`):

```python
    LOCAL = "local"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    WHATSAPP_CLOUD = "whatsapp_cloud"
    SLACK = "slack"
    SIGNAL = "signal"
    MATTERMOST = "mattermost"
    MATRIX = "matrix"
    HOMEASSISTANT = "homeassistant"
    EMAIL = "email"
    SMS = "sms"
    DINGTALK = "dingtalk"
    API_SERVER = "api_server"
    WEBHOOK = "webhook"
    MSGRAPH_WEBHOOK = "msgraph_webhook"
    FEISHU = "feishu"
    WECOM = "wecom"
    WECOM_CALLBACK = "wecom_callback"
    WEIXIN = "weixin"
    BLUEBUBBLES = "bluebubbles"
    QQBOT = "qqbot"
    YUANBAO = "yuanbao"
    RELAY = "relay"  # generic relay adapter fronted by the connector (EXPERIMENTAL)
```

但 `GatewayRunner._create_adapter` 只剩 **9 个内建分支**,且**插件注册表先查**
(`gateway/run.py` `_create_adapter` 段落,分支依次为 WHATSAPP_CLOUD / SIGNAL / WEIXIN /
API_SERVER / WEBHOOK / MSGRAPH_WEBHOOK / BLUEBUBBLES / QQBOT / YUANBAO)。工厂开头的注释
自陈了这个顺序:

> Checks the platform_registry first (plugin adapters), then falls
> through to built-ins (there are none for plugin platforms).

于是接入面实际分三条血统:

1. **内建适配器**(R7B 本体):`gateway/platforms/*.py`,9 个 + `RelayAdapter`;
2. **插件适配器**:`plugins/platforms/<name>/adapter.py`,22 个(telegram / discord / slack /
   matrix / feishu / teams / line …),由插件注册表提供,**零核心改动**;
3. **中继(relay)**:`Platform.RELAY` 一个枚举、一个适配器,由外部 connector 在对端
   前置**任意多个**平台 —— 见 §3。

这解释了 R7 定案里"README 说 20+ 平台低估"的另一面:平台数不是靠内建适配器堆出来的。

## 3. 三种"接一个平台"的成本曲线

| 路径 | 代价 | 何时用 |
|---|---|---|
| 插件 | 一个目录 + `plugin.yaml` + `adapter.py`,核心零改动 | 社区 / 第三方,默认推荐 |
| 内建 | `ADDING_A_PLATFORM.md` 列出 **16 个集成点** | 核心贡献者,平台需深度耦合 |
| relay | 对端 connector 实现,网关侧 **0 改动** | 一个 connector 复用给多平台 |

内建路径的 16 个集成点(`gateway/platforms/ADDING_A_PLATFORM.md` §1–§16 @ 863e313):
核心适配器、Platform 枚举、适配器工厂、授权映射表(**两个 dict 都要改**)、SessionSource、
系统提示 hints、toolset、cron 投递 `platform_map`、send_message 工具 `platform_map` +
`_send_to_platform`、cronjob 工具 schema、频道目录、状态显示、安装向导、手机号脱敏、
文档 5 处、测试。文档自己给出的验证手法很说明问题:

```bash
grep -r "telegram\|discord\|whatsapp\|slack" gateway/ tools/ agent/ cron/ hermes_cli/ toolsets.py \
  --include="*.py" -l | sort -u
# Check each file in the output — if it mentions other platforms but not yours, you missed it
```

即:**内建路径没有单一注册点,靠 grep 找散落的耦合**。这正是插件路径与 relay 路径存在的
理由,也是本轮最重要的可迁移教训之一(见成品章「可迁移的设计原则」)。

## 4. 双层守卫:第一层在哪里(R7 移交项的落点)

R7 已定案第二层(网关侧回合租约,按 resolved session_id 串行化)。第一层在 base.py,
按 `session_key` 在**适配器进程内**串行化,两个字典构成状态:

```python
        # Track active message handlers per session for interrupt support.
        # _active_sessions stores the per-session interrupt Event; _session_tasks
        # maps session → the specific Task currently processing it so that
        # session-terminating commands (/stop, /new, /reset) can cancel the
        # right task and release the adapter-level guard deterministically.
        # Without the owner-task map, an old task's finally block could delete
        # a newer task's guard, leaving stale busy state.
        self._active_sessions: Dict[str, asyncio.Event] = {}
        self._pending_messages: Dict[str, MessageEvent] = {}
        self._session_tasks: Dict[str, asyncio.Task] = {}
```

(`gateway/platforms/base.py:2775-2785 @ 863e313`)

三元组的分工是本轮要讲清的核心:`_active_sessions` = 忙标志兼中断信号(Event 本身可 set
用于中断),`_pending_messages` = 单槽待处理消息,`_session_tasks` = 属主任务(用于精确
取消与"释放时校验 guard 身份")。释放必须带 guard 校验:

```python
        current_guard = self._active_sessions.get(session_key)
        if current_guard is None:
            return
        if guard is not None and current_guard is not guard:
            return
        del self._active_sessions[session_key]
```

(`gateway/platforms/base.py:5325-5330 @ 863e313`)

以及入口自愈(#11016 裂脑):

```python
        # On-entry self-heal: if the adapter still has an _active_sessions
        # entry for this key but the owner task has already exited (done or
        # cancelled), the lock is stale.  Clear it and fall through to
        # normal dispatch so the user isn't trapped behind a dead guard —
        # this is the split-brain tail described in issue #11016.
        if session_key in self._active_sessions:
            self._heal_stale_session_lock(session_key)
```

(`gateway/platforms/base.py:5584-5590 @ 863e313`)

详细逐分支见 `notes/r7b-raw-base-08-first-layer-guard.md`;文档描述的定案见
`notes/r7b-90-doc-conflict-rulings.md`。

## 5. 本轮底稿清单

| 底稿 | 覆盖 |
|---|---|
| `r7b-01-scope-and-map.md` | 本文:范围、增删理由、接入面地图 |
| `r7b-raw-base-01..08-*.md` | base.py 6,861 行分 8 段 |
| `r7b-raw-api-01..07-*.md` | api_server.py 7,188 行分 7 段 |
| `r7b-raw-adp-*.md` | yuanbao / qqbot / weixin / whatsapp / signal / webhook / bluebubbles / helpers |
| `r7b-raw-relay-*.md` | relay adapter / transport+descriptor / provisioning+auth |
| `r7b-90-doc-conflict-rulings.md` | ▲/◇ 定案 |
| `r7b-95-tests.md` | 测试作行为规格 |
