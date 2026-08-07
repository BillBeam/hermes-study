# Round 7 报告 · 网关会话核心与多路复用

**一句话结论:网关会话核心学透,定案九条。**

## 0. 执行说明

- **实际执行模型**:`claude-fable-5`(Fable 5)。依据:运行环境系统提示显式声明
  "You are powered by the model named Fable 5. The exact model ID is claude-fable-5",
  且子代理转写中的思维签名元数据含同一模型标识;此外无独立第三方自证渠道,如实注明。
- **执行方式**:主线亲读全部 10 个小文件(session_context/session_state/session_stall/
  turn_lease/turn_context/wake/stream_events/stream_dispatch/message_timestamps/
  profile_routing/__init__,约 2.6k 行)与 run.py/session.py/config.py/stream_consumer 的
  决定性段落(会话键构造、busy-steer 决策块、租约挂接、run generation、stall/expiry/
  inactivity 看门狗、配对码发放、scale-to-zero、Platform 枚举);15 个精读子代理分段
  覆盖其余(run.py 十三段 + session.py + config.py + stream_consumer + 测试盘点),
  底稿全部落盘 `notes/r7-raw-*`,主线抽查行号与交叉引用(抽查记录见 §3)。
- **中途事件**:第一次并行批(Workflow,20 代理)在完成 2 段后撞上会话用量上限
  (18 代理失败,07:00 UTC 重置);已完成的 2 段产出无损保存,重置后改用
  "子代理直接写文件、只回短摘要"的方式补齐,该方式同时更省主线上下文、抗中断。

## 1. 本轮范围(开轮钉死,写入台账)

原方案 R7 = 整个 gateway/ + cron/(100 文件 / 110,440 行),超单轮预算,按 R1 方案
拆分条款切三片(理由与清单见 notes/r7-01):

- **R7(本轮,16 文件 / 38,343 行,全 L1)**:run.py、session.py、config.py、
  stream_consumer/events/dispatch、session_context/state/stall、turn_lease/context、
  wake、memory_monitor、profile_routing、message_timestamps、__init__。
- **R7B(37 文件 / 43,815 行)**:gateway/platforms/**(含 base.py)+ gateway/relay/**。
- **R7C(47 文件 / 28,282 行)**:其余 gateway/*.py(delivery/shutdown/slash/authz/
  pairing/status/kanban_watchers 等)+ cron/**。

GatewayRunner 的三个 mixin(authz/kanban/slash)按"表面 vs 引擎"原则划归 R7C,
本轮交代缝的存在与调用点。

## 2. 主要学习成果(详见成品章 chapters/r7-gateway-session-core.md)

1. **确定性会话键**:dm/group/thread 三分支纯函数(session.py:1058-1179),DM 无 chat_id
   回落发信人 id 防跨用户泄漏;WhatsApp JID/LID 规范化;Discord prospective thread 让
   "频道发起、线程继续"同键;multiplex 用 `agent:<profile>` 命名空间且默认字节兼容。
2. **三层并发防线**:contextvars 会话身份(入口 reset 治 create_task 上下文继承泄漏)、
   SessionState 按清理时机三层分层(治 19 裸 dict 边界漂移)、回合租约按 resolved
   session_id 串行化(治 #64934 转写绞碎),配 run generation 单调代数治迟到副作用(#28686)。
3. **忙时策略机**:interrupt(默认)/queue/steer/redirect + 两个价值感知自动降级
   (#30170 子代理、#56391 压缩)+ internal 事件护栏 + FIFO 保消息边界(#43066)。
4. **流式桥三层**:类型化事件(stream_events)→ 适配器路由(stream_dispatch)→
   投递引擎(stream_consumer:限速编辑、draft、围栏平衡、fresh-final、终稿字节级去重
   #71643/#78541)。
5. **看护面单一进度钟**(#72039):stall 通知(纯函数策略、观测缺失不算恢复)、
   线程看门狗(独立于事件循环、按基线+代数精确收割)、会话过期 finalize、RSS 监控。
6. **带外注入走真实入口**:wake 双策略(push 合成事件 / API self-post 治平行会话)、
   busy-steer 中途注入(失败一律回落排队)。
7. **agent 缓存治理**:配置签名判复用,LRU 128 + TTL 1h + 过期联动三线逐出,
   逐出前提交记忆。

## 3. 证据与复核

- 主线亲读 + 子代理底稿双轨;主线对每份子代理底稿抽查行号引用与跨文件引用
  (已验:run-01 四处、run-02 三处、stream-consumer 两处交叉引用,全部逐字命中)。
- 台账:status 更新后 verify_ledger 三项全过(数字见 §6)。

## 4. 文档-代码冲突定案(R7 范围,九条,详见 notes/r7-90)

- **证伪** gateway-internals.md 四处:会话键示例 `private` 槽不存在(代码恒 `dm`)、
  忙时守卫"其余一律 interrupt()"停留在 steer/redirect/降级之前、DM 配对方向写反
  (无 /pair 命令,实为陌生人自动收码 + owner CLI 批准)、"20+ 平台"低估(24 枚举 +
  22 插件)。
- **证实 ◇** 两条:scale-to-zero 网关侧整套无文档;活动心跳的网关侧三看门狗同钟消费。
- **新记三条**:profile_routing docstring specificity 数字与自身示例不符(轻微)、
  `_TELEGRAM_NOISY_STATUS_RE` 命名漂移(实为全平台)、stream_consumer 模块头仍称
  edit-only transport(draft 通道已存在)。
- 移交:base.py 第一层守卫(R7B);authz 层级、pairing 本体、kanban steer、
  scale_to_zero.py、status.py 描述矛盾(R7C);REPL 忙时输入(R8)。
- 规律延续:机制方向大体对,分支图谱与精确值系统性滞后;用户文档常比开发者文档新。

## 5. 测试作为行为规格(详见 notes/r7-95)

四批共约 60 文件 / 700+ 用例全部通过(0 行为失败;一次 venv 缺 aiohttp 为环境问题)。
含 42 文件规格大盘(440 passed,21.6s)与本簇 12+4 个 issue 号命名测试。

## 6. 台账报数

- verify_ledger:OK baseline=863e31318 files=8530 total_lines=2,608,452;
  L1 files=436 lines=404,894;L2 2,258/788,952;L3 1,895/602,085;L4 560/55,902;
  LT 3,381/756,619;SUM == repo total。
- 本轮 status:R7 16 文件 → `R7-deep-read`。

## 7. 下一轮建议

**下一轮做 R7B:平台接入面**(gateway/platforms/** 37 文件 43,815 行:base.py 6,861 行的
适配器基类契约与双层守卫第一层、api_server 7,188 行的 OpenAI 兼容入口与会话绑定、
telegram 侧的 topic 机制适配、whatsapp/signal/qqbot/yuanbao 等代表性适配器、relay 隧道)。
理由:R7 已把"核心如何复用"钉死,R7B 是它的消费端——base.py 的 `_active_sessions`/
`_pending_messages` 第一层守卫、`supports_async_delivery` 能力位、`render_message_event`
渲染钩子都在本轮以接口断言出现,该轮转正;R7 移交的 ▲(第一层守卫文档描述)也在该轮定案。
打法沿用本轮:开轮钉范围 → 主线亲读 base.py + 子代理分段平台 → 测试作规格 →
定案 → 双产出 → 台账校验。
