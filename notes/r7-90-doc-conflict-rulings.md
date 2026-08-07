# r7-90 · R7 簇文档-代码冲突定案

> 基线 @ 863e313。范围:锚点落在 R7 切片 16 文件内的 ▲(文档不符)/ ◇(未见于文档)条目,
> 含 R1 能力目录遗留项与本轮新发现。锚点在 R7B/R7C 文件的只列移交、不定案。
> 全部裁决以代码为准;每条给出双侧证据(文档原文位置 + 代码行号)。

## A. R1 能力目录遗留项定案(6 条)

### A1. 能力点 100:会话键格式文档失实 —— ▲ 证伪(文档滞后)

- **文档**:`website/docs/developer-guide/gateway-internals.md:66,78 @ 863e313`:格式
  `agent:main:{platform}:{chat_type}:{chat_id}`,示例 **`agent:main:telegram:private:123456789`**;
  并称 "Thread-aware platforms may include thread IDs in the chat_id portion";全文未提
  multiplex 下的 `agent:<profile>` 命名空间。
- **代码**:chat_type 槽 DM 恒为字面 `"dm"`,从不产生 "private":

`gateway/session.py:1103-1108 @ 863e313`
```python
    if source.chat_type == "dm":
        dm_chat_id = source.chat_id
        if source.platform == Platform.WHATSAPP:
            dm_chat_id = canonical_whatsapp_identifier(source.chat_id)

        dm_parts = [ns, platform, "dm"]
```
  命名空间可变:`_session_key_namespace`(session.py:1038-1055)——默认 `agent:main`
  字节等同历史键;命名 profile → `agent:<profile>`,位置布局不变。thread_id 是**独立段**
  追加(session.py:1113-1114,1166-1167),不是"并进 chat_id portion"。
- **裁决**:三处证伪:示例键的 "private" 槽不存在;profile 命名空间未记载;thread id
  是独立段。文档"Never construct session keys manually"的告诫与 build_session_key
  单一事实源(session.py:1058-1066 docstring)一致,方向正确、细节失实。

### A2. 能力点 101:双层守卫 busy 策略描述停留在早期行为 —— ▲ 证伪(run.py 侧)

- **文档**:`gateway-internals.md:88 @ 863e313`(Two-Level Message Guard 第二层):
  "Everything else triggers `running_agent.interrupt()`"。
- **代码**:第二层实际是一台模式机,"everything else 一律 interrupt"至少错四处:
  1. internal 合成事件**永不**打断/steer,静默排队(run.py:8867-8879,注释明言设计不变量);
  2. steer 模式经 `running_agent.steer()` 中途注入,失败回落 queue(run.py:8929-8961);
  3. interrupt 模式有两个自动降级:活跃子代理(#30170,run.py:8905-8915)与压缩飞行中
     (#56391,run.py:8916-8926)一律降为 queue;
  4. 支持 `_supports_active_turn_redirect` 的 agent 走 redirect 原地转向(run.py:8962-8976)。
  默认模式确为 interrupt(`_load_busy_input_mode` run.py:8278-8288:非法/未设→"interrupt"),
  文档的方向没错,分支图谱严重过时。
- **裁决**:证伪(描述的是 steer/redirect/降级机制引入前的行为)。
  第一层(base.py `_pending_messages` + interrupt event)锚在 R7B 文件,移交 R7B 复核。
  行为规格:test_steer_command / test_internal_event_never_interrupts_busy_session /
  test_compression_interrupt_demotion_56391(本轮全部跑通)。

### A3. 能力点 99:"20+ external messaging platforms" 口径偏小 —— ▲ 证伪(方向正确)

- **文档**:`gateway-internals.md:9 @ 863e313`:"connects Hermes to 20+ external messaging
  platforms"。
- **代码**:`Platform` 枚举 24 个显式成员(gateway/config.py:280-303,含 local/api_server/
  webhook 等非聊天面)+ `_missing_` 动态成员只认 bundled 插件目录扫描与运行时注册
  (config.py:305-368),R1 清点 plugins/platforms/ 22 个插件平台;逻辑平台合计 30+。
- **裁决**:证伪(实际能力大于文档口径;"20+"字面不算错但显著低估)。R1 判断维持。

### A4. 能力点 106:DM 配对方向写反 —— ▲ 证伪(开发者文档)

- **文档**:`gateway-internals.md:104-108 @ 863e313`:"Admin: /pair → Gateway 给码 →
  新用户回码即配对"。
- **代码**:全仓无 `/pair` 命令(gateway/、hermes_cli/ grep 仅得 `unauthorized_dm_behavior`
  的 "pair" 取值)。真实方向相反:陌生 DM 在 `unauthorized_dm_behavior=="pair"`(默认,
  config.py:941,198-207)时**自动收到**配对码,并被告知让 owner 在 CLI 批准:

`gateway/run.py:14493-14500 @ 863e313`
```python
                        await adapter.send(
                            source.chat_id,
                            f"Hi~ I don't recognize you yet!\n\n"
                            f"Here's your pairing code: `{code}`\n\n"
                            f"Ask the bot owner to run:\n"
                            f"`hermes {profile_arg}pairing approve "
                            f"{platform_name} {code}`"
                        )
```
  且配对响应全程限速(run.py:14474-14478,14501-14510)。
- **裁决**:证伪。用户文档 messaging/index.md 与代码一致(R1 已核),开发者文档方向写反。
  pairing.py 本体(哈希码、锁定)移交 R7C。

### A5. scale-to-zero 网关侧无文档 —— ◇ 证实

- **文档**:官方文档仅 cron-internals.md:132 在 Chronos 托管语境提 scale-to-zero;
  README/AGENTS.md/website docs 无网关侧记载(R1 判断)。
- **代码**:网关侧完整存在:后台活工作判定 `_scale_to_zero_has_live_background_work`
  (run.py:7429-7455:background tasks + async delegation + process registry 三查)、
  idle 超时配置 `gateway.scale_to_zero.idle_timeout_minutes`(run.py:7457-7469)、
  armed 判定(run.py:7494-7528,含 #relay-only 修复:只数 enabled 平台,注释 7504-7512)、
  `HERMES_SCALE_TO_ZERO` 挂牌(run.py:7531-7533 docstring "no HERMES_SCALE_TO_ZERO stamp")、
  watcher(run.py:7611-7667)。
- **裁决**:◇ 证实(代码有、地图无)。helper 文件 gateway/scale_to_zero.py 移交 R7C 深读。

### A6. 能力点 12:活动心跳的网关侧消费 —— ◇ 证实(R7 部分)

- **要点**:agent 侧 `_touch_activity`(run_agent.py,R2 域)维护的活动时间戳,在网关侧被
  **三个看门狗共用一钟**消费(#72039 单一进度源契约):
  1. 回合级不活跃看门狗:线程轮询 `get_activity_summary().seconds_since_activity`
     (run.py:2964-2975),超时打断 + 按基线收割进程;
  2. stall 通知:`_session_activity_for_stall`(run.py:12129-12144)同源取数,
     策略纯函数在 session_stall.py(27-60,观测缺失不算恢复);
  3. 回合租约等待超时与看门狗同取 `HERMES_AGENT_TIMEOUT` 默认 1800(run.py:16588,
     turn_lease.py:63-66 注释点名同钟设计)。
- **裁决**:◇ 证实。kanban 评论 steer 注入侧(kanban_watchers.py)移交 R7C。

## B. 本轮新发现(3 条)

### B1. profile_routing 模块 docstring 的 specificity 数字与示例不符 —— ▲(轻微)

- **文档(代码内 docstring)**:`gateway/profile_routing.py:6-9 @ 863e313`:
  "platform + chat_id + thread_id (exact thread) — specificity 14"。
- **代码**:算术为 guild=2、chat=4、thread=8(profile_routing.py:63-72);同 docstring 的
  配置示例 thread-route 只声明 chat+thread(33-37)→ specificity 12,不是 14;
  14 仅当 guild+chat+thread 三者齐备。排序语义(最specific先匹配)不受影响。
- **裁决**:docstring 数字示意失准,机制正确。轻微,不影响使用。

### B2. `_TELEGRAM_NOISY_STATUS_RE` 命名漂移 —— ▲(轻微,子代理 run-01 发现、主线复核)

- 常量名带 `_TELEGRAM_` 前缀(run.py:90),但消费者 `_prepare_gateway_status_message`
  对**所有**非 raw-text 聊天平台生效(run.py:725-755;#39293 已把 #28533 的 Telegram-only
  过滤推广到全部聊天面)。名字是历史遗留,误导作用域。

### B3. gateway-internals.md Key Files 表 status.py 描述与其 docstring 不符 —— 记录待 R7C

- 文档表:`gateway/status.py | Token lock management for profile-scoped gateway instances`
  (gateway-internals.md:22);status.py 模块 docstring 自述为 PID 文件网关运行检测
  (status.py:1-10)。status.py 属 R7C,本轮只记录矛盾线索,定案移交。

## C. 移交清单(锚点在 R7B/R7C,不在本轮定案)

| 条目 | 锚点 | 移交 |
|---|---|---|
| 能力点 101 第一层守卫(_pending_messages + interrupt event 描述) | gateway/platforms/base.py | R7B |
| 能力点 103 授权层级(文档 5 层 vs 代码更多层) | gateway/authz_mixin.py | R7C |
| 能力点 106 pairing.py 本体(盐化哈希/限速/锁定) | gateway/pairing.py | R7C |
| 能力点 121 kanban 运行中评论 steer 注入 | gateway/kanban_watchers.py | R7C |
| scale_to_zero.py 判定函数本体 | gateway/scale_to_zero.py | R7C |
| status.py 文档描述矛盾(B3) | gateway/status.py | R7C |
| 能力点 98 REPL 忙时输入(cli.py) | cli.py | R8 |

## D. 待补定案(等子代理证据合入后本轮内定)

- 能力点 82:网关路由持久化与对等体会话找回(session.py:1865-2034 侧)——
  session-py 底稿合入后定案(hermes_state gateway_routing 表侧 R5 已学)。
- 子代理各段新报的 docstring/issue 引用不符候选——逐条主线复核后追加。
