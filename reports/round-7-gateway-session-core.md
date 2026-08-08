# Round 7 报告 · 网关会话核心与多路复用

**一句话结论:网关会话核心学透,定案 7+11 条。**

头条发现:`gateway/memory_monitor.py` 是**休眠模块**——从 cline 移植、注释详尽、测试齐全,
但全仓零生产调用点,连 docstring 声称的 `logging.memory_monitor` 配置块都不存在
(主线全仓 grep 复核,notes/r7-90 B8)。

## 0. 执行说明

- **实际执行模型**:`claude-fable-5`(Fable 5)。依据:运行环境系统提示显式声明
  "You are powered by the model named Fable 5. The exact model ID is claude-fable-5",
  且子代理转写元数据含同一模型标识;无独立第三方自证渠道,如实注明。
- **执行方式**:主线亲读全部 10 个小文件(session_context/session_state/session_stall/
  turn_lease/turn_context/wake/stream_events/stream_dispatch/message_timestamps/
  profile_routing,约 2.6k 行)与 run.py/session.py/config.py/stream_consumer 的决定性段落
  (会话键构造、busy-steer 决策块、租约挂接、run generation、三看门狗、配对码发放、
  scale-to-zero、Platform 枚举);15 个精读子代理分段覆盖其余(run.py 十三段 + session.py +
  config.py + stream_consumer + 测试盘点),底稿全部落盘 `notes/r7-raw-*`(合计约 8,900 行),
  主线对每份底稿抽查行号与跨文件引用(共 15+ 处,全部逐字命中;含用 grep 复核并**采信后
  写入定案**的 memory_monitor 零调用点、goal 前缀逃逸、multi-profile fails-fast 三项)。
- **中途事件**:首次并行批(Workflow,20 代理)完成 2 段后撞会话用量上限(18 代理失败,
  07:00 UTC 重置);已完成产出无损保存;重置后改用"子代理直接写文件、只回短摘要"方式
  补齐——更省主线上下文、抗中断,建议后续轮沿用。

## 1. 本轮范围(开轮钉死,写入台账与 assign_layers.py)

原方案 R7 = 整个 gateway/ + cron/(100 文件 / 110,440 行)超单轮预算,按 R1 方案拆分条款
切三片(理由与清单见 notes/r7-01):

- **R7(本轮,16 文件 / 38,343 行,全 L1)**:run.py(27,146)、session.py(3,490)、
  config.py(2,688)、stream_consumer/events/dispatch(2,713)、session_context/state/stall
  (1,092)、turn_lease/turn_context(433)、wake(184)、memory_monitor(230)、
  profile_routing(166)、message_timestamps(166)、__init__(35)。
- **R7B(37 文件 / 43,815 行)**:gateway/platforms/**(含 base.py、api_server)+ relay/**。
- **R7C(47 文件 / 28,282 行)**:其余 gateway/*.py(delivery/shutdown/slash/authz/pairing/
  status/kanban_watchers…)+ cron/**。

GatewayRunner 三个 mixin(authz/kanban/slash)按"表面 vs 引擎"原则归 R7C,本轮交代缝与调用点。

## 2. 主要学习成果(成品章 chapters/r7-gateway-session-core.md)

1. **确定性会话键**:dm/group/thread 三分支纯函数(session.py:1058-1179);DM 无 chat_id
   回落发信人 id 防跨用户泄漏;WhatsApp JID/LID 规范化;Discord prospective thread 令
   "频道发起、线程继续"同键;multiplex 用 `agent:<profile>` 命名空间且默认字节兼容。
2. **三层并发防线**:contextvars 会话身份(入口 reset 治 create_task 上下文继承泄漏)、
   SessionState 按清理时机三层分层(治 19 裸 dict 边界漂移,#48031 等四事故)、回合租约按
   resolved session_id 串行化(治 #64934 转写绞碎;身份检查释放/超时 fail-open/压缩轮换
   rebind),配 run generation 单调代数治迟到副作用(#28686,永不重置)。
3. **忙时策略机**:interrupt(默认)/queue/steer/redirect + 两个价值感知自动降级(#30170
   子代理、#56391 压缩)+ internal 事件护栏 + FIFO 保消息边界(#43066)+ steer 语音折叠
   (#58780);busy 命令面已表驱动化(CommandDef.busy_policy)。
4. **流式桥三层**:类型化事件(stream_events)→ 适配器路由(stream_dispatch,可"吃掉"
   事件)→ 投递引擎(stream_consumer:限速编辑、draft、围栏平衡、fresh-final、终稿字节级
   去重 #71643/#78541)。
5. **看护面单一进度钟**(#72039):stall 通知(纯函数策略、观测缺失不算恢复)、线程看门狗
   (独立于事件循环、按"归属+基线+代数"精确收割)、会话过期 finalize(3 次失败落旗);
   第四条线 memory_monitor 实为休眠模块(见头条)。
6. **带外注入走真实入口**:wake 双策略(push 合成事件 / API self-post 治"平行会话");
   busy-steer 失败一律回落排队;完成投递三层去重(producer 身份 / SQLite durable claim /
   进程内 inflight),明确只承诺 at-least-once。
7. **agent 缓存治理**:配置签名判复用(用户身份入签名是 #27371 记忆归属修复,牺牲共享
   prompt cache);LRU 128 + TTL 1h + 过期联动三线逐出;逐出前提交记忆。
8. **启动/停机工程**:start() 十二阶段(connected_count==0 四层决策树、恢复三部曲)、
   stop() 十七阶段(exit 75 重启协议、pending 落盘 #72680)、_spawn_supervised 治
   裸 create_task 无声死亡(#71758)、reconnect 无限重试 + 三失败路强制 dispose(#37011)。

## 3. 覆盖与证据

- 底稿:主线 6 篇(r7-01/20/60/80/90/95)+ 子代理原始底稿 15 篇(r7-raw-*),
  全部断言带 `路径:行号 @ 863e313` + 逐字代码块。
- 复核:主线亲读约 5k 行 + 对 15 份子代理底稿逐份抽查(全部命中);三项子代理发现
  经主线独立 grep/sed 复核后才写入定案(memory_monitor、goal 前缀、fails-fast)。

## 4. 文档-代码冲突定案(R7 范围,7 条遗留定案 + 10 条新立,详见 notes/r7-90)

**遗留 7 条全部定案**:
- **证伪** gateway-internals.md 四处:会话键示例 `private` 槽不存在(代码恒 `dm`,
  且缺 profile 命名空间/scope/participant 段)、忙时守卫"其余一律 interrupt()"停留在
  steer/redirect/降级之前、DM 配对方向**写反**(无 /pair 命令;实为陌生人自动收码 +
  owner CLI 批准)、"20+ 平台"低估(24 枚举 + 22 插件)。
- **证实 ◇** 三条:scale-to-zero 网关侧整套无文档;活动心跳网关侧三看门狗同钟消费;
  gateway_routing 对等体找回协议(主/从、generation 总序、end_reason 白名单)代码有地图无。

**新立 11 条**:memory_monitor 休眠(◇▲,头条)、multi-profile "fails fast" 失实、
stream_consumer 模块头仍称 edit-only、start() 返回值语义失实、重启计数注释与实现相反、
goal gate-failed 模板逃逸前缀检查(bug 候选,只记录不修)、原生 Discord 语义改名 kwargs
失配且 TypeError 被 debug 吞(bug 候选)、profile_routing specificity 数字失准、
`_TELEGRAM_NOISY_STATUS_RE` 命名漂移、run-13 三小项(死旗标/注释滞后/幽灵 debug.py)、
status.py 描述矛盾(移交 R7C)。

**移交**:base.py 第一层守卫(R7B);authz 层级、pairing 本体、kanban steer、
scale_to_zero.py 本体(R7C);REPL 忙时输入(R8);AGENTS.md 条款(R11)。

规律延续并加深:**机制方向大体对,分支图谱与精确值系统性滞后;用户文档常比开发者文档新;
本轮新增一类——"接线声明"也会说谎(模块声称的集成不存在)**。

## 5. 测试作为行为规格(notes/r7-95)

四批约 60 文件 / 700+ 用例全部通过(0 行为失败;一次 venv 缺 aiohttp 为环境问题):
核心 5 文件 39 例、steer/wake/流式 10 文件、busy/会话/缓存 15 文件 153 例、
规格 Top-42 大盘 440 例(21.6s)。本簇 issue 号命名测试 12+4 个全部纳入。

## 6. 台账报数

- verify_ledger 三项全过:OK baseline=863e31318 files=8530 total_lines=2,608,452;
  L1 436/404,894;L2 2,258/788,952;L3 1,895/602,085;L4 560/55,902;LT 3,381/756,619;
  SUM == repo total。
- round 列:R7 16 文件(38,343 行)/ R7B 37(43,815)/ R7C 47(28,282);
  本轮 status:R7 全部 16 文件 → `R7-deep-read`。

## 7. L1 完成标准自评

对簇内每个机制能讲清问题/实现/设计理由/取舍(成品章即证),能凭底稿重实现(每机制
附"重实现要点");主线复核推翻/修正了子代理与任务简报的多处认知(memory_monitor
"启动点"不存在、时间戳注入位置在 _handle_message_with_agent 而非 _prepare_inbound、
_is_stale_restart_redelivery 调用点在 slash_commands),体现"抽查不轻信"。达标。

## 8. 下一轮建议

**下一轮做 R7B:平台接入面**(gateway/platforms/** + relay/**,37 文件 43,815 行:
base.py 6,861 行的适配器基类契约与双层守卫第一层、api_server 7,188 行的 OpenAI 兼容入口
与 `X-Hermes-Session-Id` 会话绑定、telegram topic 适配、whatsapp/signal/qqbot/yuanbao 等
代表性适配器、relay 隧道)。理由:R7 已把"核心如何复用"钉死,R7B 是它的消费端——
base.py 的 `_active_sessions`/`_pending_messages` 第一层守卫、`supports_async_delivery`
能力位、`render_message_event` 渲染钩子本轮均以接口断言出现,该轮转正;R7 移交的 ▲
(第一层守卫文档描述)在该轮定案。打法沿用本轮:开轮钉范围 → 主线亲读 base.py +
子代理分段(直接写文件、只回摘要)→ 测试作规格 → 定案 → 双产出 → 台账校验。

---

## 勘误(R8-fix,review-1 处置,2026-08-08)

本报告正文保持历史原样,以下为经复核成立的补记。修正卡:`claude/hermes-r8fix-review-1`。

1. **【M-25】本报告漏报了全局进度,现补报。** R2–R6 每轮都报"`R1-inventoried` 剩余",
   **R7 起中断五轮**(R7 / R7B / R7C / R8A / R8B 全文 grep `累计已学` 与 `R1-inventoried` 零命中),
   只报本轮文件数与五层快照。**而五层快照几乎不动**——L3 / L4 / LT 连续五轮一字未改——
   于是读者从报告里**读不出"还剩多少没开工"**。
   CLAUDE.md 的最终目的第 3 条("全仓每个源文件都被明确交代,没有黑洞")的**唯一可观测指标
   恰恰是台账的 `status` 列,不是分层列**。报了不变的那个数,停报了会变的那个数。

   本轮(R7)补报:**处理 16 个文件;`R1-inventoried` 由上一轮收口值降至 8271。**
   该值按各轮 `status` 计数从 R6 自报的 8287 逐轮推出,并与台账当前实测收口一致:

   ```verify
   $ awk -F'\t' 'NR>1{c[$6]++} END{for(k in c) print c[k], k}' data/ledger.tsv | sort -rn | head -1
   8122 R1-inventoried
   # 8287 −16(R7) −37(R7B) −47(R7C) −15(R8A) −50(R8B) = 8122 ✓
   ```

   R8-fix 已把"`R1-inventoried` 剩余文件数与行数"恢复为**每轮报告必报项**并写进 CLAUDE.md。
