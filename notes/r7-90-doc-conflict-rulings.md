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
  1. internal 合成事件**永不**打断/steer,静默排队(gateway/run.py:8867-8879,注释明言设计不变量);
  2. steer 模式经 `running_agent.steer()` 中途注入,失败回落 queue(gateway/run.py:8929-8961);
  3. interrupt 模式有两个自动降级:活跃子代理(#30170,gateway/run.py:8905-8915)与压缩飞行中
     (#56391,gateway/run.py:8916-8926)一律降为 queue;
  4. 支持 `_supports_active_turn_redirect` 的 agent 走 redirect 原地转向(gateway/run.py:8962-8976)。
  默认模式确为 interrupt(`_load_busy_input_mode` gateway/run.py:8278-8288:非法/未设→"interrupt"),
  文档的方向没错,分支图谱严重过时。
- **裁决**:证伪(描述的是 steer/redirect/降级机制引入前的行为)。
  第一层(base.py `_pending_messages` + interrupt event)锚在 R7B 文件,移交 R7B 复核。
  行为规格:test_steer_command / test_internal_event_never_interrupts_busy_session /
  test_compression_interrupt_demotion_56391(本轮全部跑通)。

### A3. 能力点 99:"20+ external messaging platforms" 口径偏小 —— ◎ 保守表述(原记 ▲,R8-fix 改判)

- **文档**:`gateway-internals.md:9 @ 863e313`:"connects Hermes to 20+ external messaging
  platforms"。
- **代码**:`Platform` 枚举 24 个显式成员(gateway/config.py:280-303,含 local/api_server/
  webhook 等非聊天面)+ `_missing_` 动态成员只认 bundled 插件目录扫描与运行时注册
  (config.py:305-368),R1 清点 plugins/platforms/ 22 个插件平台;逻辑平台合计 30+。
- **裁决(R8-fix 改判,review-1 建议-13 / M-16e)**:**不计 ▲,新增记号 ◎「保守表述」。**
  ▲ 在本项目里的定义是"文档所述与代码矛盾"。这里 **24 ≥ 20,"20+" 字面为真**,矛盾不存在——
  原裁决自己也写了"'20+'字面不算错",却仍判为"证伪"并计入 ▲。
  正确表述:**文档成立但显著保守**(枚举 24 个显式成员 + `plugins/platforms/` 22 个目录)。
  **为什么值得单列**:▲ 条数是贯穿 R2–R8B 用来衡量"地图腐烂程度"的跨轮指标,
  把一个"保守但为真"的表述计进去,会让这个指标不可比。R7 因此把"四处硬伤"改为**三处**。

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
  且配对响应全程限速(gateway/run.py:14474-14478,14501-14510)。
- **裁决**:证伪。用户文档 messaging/index.md 与代码一致(R1 已核),开发者文档方向写反。
  pairing.py 本体(哈希码、锁定)移交 R7C。

### A5. scale-to-zero 网关侧无文档 —— ◇ 证实

- **文档**:官方文档仅 cron-internals.md:132 在 Chronos 托管语境提 scale-to-zero;
  README/AGENTS.md/website docs 无网关侧记载(R1 判断)。
- **代码**:网关侧完整存在:后台活工作判定 `_scale_to_zero_has_live_background_work`
  (gateway/run.py:7429-7455:background tasks + async delegation + process registry 三查)、
  idle 超时配置 `gateway.scale_to_zero.idle_timeout_minutes`(gateway/run.py:7457-7469)、
  armed 判定(gateway/run.py:7494-7528,含 #relay-only 修复:只数 enabled 平台,注释 7504-7512)、
  `HERMES_SCALE_TO_ZERO` 挂牌(gateway/run.py:7531-7533 docstring "no HERMES_SCALE_TO_ZERO stamp")、
  watcher(gateway/run.py:7611-7667)。
- **裁决**:◇ 证实(代码有、地图无)。helper 文件 gateway/scale_to_zero.py 移交 R7C 深读。

### A6. 能力点 12:活动心跳的网关侧消费 —— ◇ 证实(R7 部分)

- **要点**:agent 侧 `_touch_activity`(run_agent.py,R2 域)维护的活动时间戳,在网关侧被
  **三个看门狗共用一钟**消费(#72039 单一进度源契约):
  1. 回合级不活跃看门狗:线程轮询 `get_activity_summary().seconds_since_activity`
     (gateway/run.py:2964-2975),超时打断 + 按基线收割进程;
  2. stall 通知:`_session_activity_for_stall`(gateway/run.py:12129-12144)同源取数,
     策略纯函数在 session_stall.py(27-60,观测缺失不算恢复);
  3. 回合租约等待超时与看门狗同取 `HERMES_AGENT_TIMEOUT` 默认 1800(gateway/run.py:16588,
     gateway/turn_lease.py:63-66 注释点名同钟设计)。
- **裁决**:◇ 证实。kanban 评论 steer 注入侧(kanban_watchers.py)移交 R7C。

## B. 本轮新发现(3 条)

### B1. profile_routing 模块 docstring 的 specificity 数字与示例不符 —— ▲(轻微)

- **文档(代码内 docstring)**:`gateway/profile_routing.py:6-9 @ 863e313`:
  "platform + chat_id + thread_id (exact thread) — specificity 14"。
- **代码**:算术为 guild=2、chat=4、thread=8(gateway/profile_routing.py:63-72);同 docstring 的
  配置示例 thread-route 只声明 chat+thread(33-37)→ specificity 12,不是 14;
  14 仅当 guild+chat+thread 三者齐备。排序语义(最specific先匹配)不受影响。
- **裁决**:docstring 数字示意失准,机制正确。轻微,不影响使用。

### B2. `_TELEGRAM_NOISY_STATUS_RE` 命名漂移 —— ▲(轻微,子代理 run-01 发现、主线复核)

- 常量名带 `_TELEGRAM_` 前缀(gateway/run.py:90),但消费者 `_prepare_gateway_status_message`
  对**所有**非 raw-text 聊天平台生效(gateway/run.py:725-755;#39293 已把 #28533 的 Telegram-only
  过滤推广到全部聊天面)。名字是历史遗留,误导作用域。

### B4. stream_consumer 模块头仍称 edit-only transport —— ▲(docstring 滞后)

- **文档(模块 docstring)**:`gateway/stream_consumer.py:10-11 @ 863e313`:
  "Design: Uses the edit transport (send initial message, then editMessageText)"。
- **代码**:`StreamConsumerConfig.transport` 已支持 `auto/draft/edit/off` 四态,Telegram DM
  可走原生 draft 动画(gateway/stream_consumer.py:142-153,1669-1750);edit 只是默认与回落。
- **裁决**:docstring 写于 draft 通道引入前,未更新。机制侧详见 r7-raw-stream-consumer。

### B5. start() docstring 返回值语义失实 —— ▲(子代理 run-07 发现、主线复核)

- **文档(docstring)**:`gateway/run.py:10668 @ 863e313`:"Returns True if at least one
  adapter connected successfully"。
- **代码**:start() 全路径 return True(10664-11576 区间 grep 无 `return False`);失败通过
  exit-reason 属性(should_exit_with_failure/exit_code,gateway/run.py:6664-6677)表达,
  connected_count==0 走四层决策树(纯致命 exit 78 / degraded / cron-only)而非返回 False。
- **裁决**:证伪;返回值已退化为惯例,真实信号在属性上。

### B6. 重启失败计数注释与实现相反 —— ▲(子代理 run-06 发现、主线复核)

- **注释**:`gateway/run.py:9717-9718 @ 863e313`:"Keep any entries that are still above 0
  even if not active now (they might become active again next restart)"。
- **代码**:`new_counts` 仅由 `active_session_keys` 构建(9714-9716),非活跃条目被**丢弃**,
  与注释所述"保留"相反。
- **裁决**:注释失实(行为上丢弃更保守:非活跃会话的失败计数清零,不会误熔断)。

### B7. goal 续跑前缀识别逃逸 —— bug 候选(代码内部不一致,非文档问题)

- `_is_goal_continuation_event` 按前缀识别 goal 续跑合成事件:
  `gateway/run.py:7753 @ 863e313`
  ```python
        return str(text).startswith("[Continuing toward your standing goal]\nGoal:")
  ```
- 但 gate-failed 续跑模板首行为 `"[Continuing toward your standing goal — a quality gate
  failed]\n"`(hermes_cli/goals.py:132-134),em-dash 后缀使前缀不匹配 → gate-failed 续跑
  事件不被识别为 goal 续跑,`/goal pause`/`clear` 的摘除与 drain 复核对它失效。
- **处置**:hermes-agent 只读,不修;作为学习产出记录(识别谓词与模板集合脱耦的反例)。

### B8. memory_monitor 全仓零生产调用点 —— ◇▲(本轮头等发现;子代理 run-13 首报、主线全仓复核)

- **模块自述**:`gateway/memory_monitor.py:27-28 @ 863e313`:"Config: ``logging.memory_monitor``
  in ``config.yaml`` — see ``hermes_cli/config.py`` for the defaults block."
- **主线全仓复核**:`grep -rn "memory_monitor|start_memory_monitoring" --include="*.py" .`
  除模块自身与 tests/gateway/test_memory_monitor.py 外**零命中**;hermes_cli/config.py 中
  **不存在** `memory_monitor` 配置块。即:该模块从 cline/cline#10343 移植、带完整测试,
  但网关启动路径(start_gateway/main)从未调用 `start_memory_monitoring()`,声称的配置
  接线也不存在——**休眠模块**。
- **裁决**:▲ docstring 声称的配置集成不存在;◇ 机制本体"代码有、接线无、文档无"。
  学习价值:测试通过 ≠ 已接线;"移植完成"与"投入生产"之间隔着一个调用点。

### B9. run-13 段其余三条(子代理发现、主线抽验 docstring 侧)

- `main()` 的 `--verbose` 旗标解析后从未使用(gateway/run.py:27021 起参数区)——死旗标。
- gateway/run.py:25115 附近注释称 "env var takes precedence",而 #18413 之后实际是 config 无条件
  覆盖 env——注释滞后。
- `_start_cron_ticker` docstring 引用的 debug.py 仅存在于 docstring,仓库无此文件。

### B10. multi-profile 同凭据冲突:"startup fails fast" 失实 —— ▲(子代理 run-08 发现、主线复核)

- **文档**:`website/docs/user-guide/multi-profile-gateways.md:189 @ 863e313`:"If two
  profiles configure the same `(platform, token)`, startup fails fast naming both profiles"。
- **代码**:`gateway/run.py:13336-13345 @ 863e313`——检测到重复凭据 claim 时记 ERROR
  ("refusing to start the duplicate")并**只跳过该重复 adapter**,网关整体继续启动;
  且注释说明故意不 disconnect(防误杀 primary 侧共享状态)。"命名双方"成立(日志含
  owner 与当前 profile),"fails fast"(整体快速失败)不成立。
- **裁决**:证伪(实际行为更宽容:局部拒绝而非整体失败)。

### B11. 原生 Discord 语义改名 kwargs 失配 —— bug 候选(子代理 run-11 发现、主线复核)

- 调用方:`gateway/run.py:19960-19966 @ 863e313`
  ```python
            renamed = await rename_thread(
                target_thread_id,
                thread_name,
                prefer_connector_created=use_connector_guard,
                only_if_current_name=guard_name,
                parent_chat_id=parent_chat_id,
            )
  ```
- 被调方(原生 Discord 插件适配器):`plugins/platforms/discord/adapter.py:6866-6872
  @ 863e313`——签名仅收 `only_if_current_name`,不收 `prefer_connector_created`/
  `parent_chat_id` → 原生 lane 调用抛 TypeError,被 `except Exception: logger.debug(...)`
  (gateway/run.py:19972-19974)吞成 debug 日志——**原生 Discord 自动线程语义改名疑似静默失效**
  (relay lane 的 rename_thread 收全参,测试仅覆盖 relay fake)。
- **处置**:hermes-agent 只读,不修;记录为"能力探测靠 TypeError + 宽 except"的反例。
  注:被调方在 R7B 文件,但调用方与吞异常点均在 run.py(R7),故本轮记案,R7B 轮复核
  relay 侧签名后可终案。

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

## D. 补定案

### D1. 能力点 82:网关路由持久化与对等体会话找回 —— ◇▲ 证实(session.py 侧,本轮定案)

- **代码侧**(证据详见 notes/r7-raw-session-py):路由持久化双路——`gateway_routing` 表
  (scope=sessions_dir)为**主源**、sessions.json 为 legacy 镜像,快路(单行 UPSERT)与
  慢路(全量重写)共享一个 generation 计数器构成总序(session.py:1479-1543);会话行冗余
  存 session_key,使进程重启后可从 DB **精确重建** 键→会话映射(_recover_session_from_db /
  _query_recoverable_session / _record_gateway_session_peer,session.py:1865-2034);可复活
  判定走 end_reason 白名单;Slack scoped 查询禁 peer 回退 + legacy key 一次性认领。
- **文档侧**:session-storage.md 对 gateway_routing 仅一行提及(R1 已核),主/从关系、
  generation 总序、end_reason 白名单、legacy 认领协议均无文档;SessionStore 类 docstring
  的 JSONL 回退话术已过时(spec 002 已删该机制;子代理发现、主线采信其 grep 复核)。
- **裁决**:◇(整套找回协议"代码有、地图无")+ ▲(docstring 滞后)双证实。R1 判断维持
  并补全:R5 学的是表侧,本轮补齐 SessionStore 消费侧,该能力点闭环。

### D2. 子代理其余候选的处置

- session-py:▲ gateway-internals.md Session Key Format 滞后——并入 A1(同一条,证据加厚)。
- run-05:双层守卫 bypass 命令清单不完整(真源 commands.py busy_policy 注册表)——并入 A2。
- run-04:scale-to-zero 注释引用仓库外 `~/nous/specs` 编号(D3/F7/NS-609 等)不可解引用
  ——记录为"注释引用私有规格库"现象,不计冲突(无从证伪)。
- gateway-config:StreamingConfig transport 文档缺 draft 态等 5 条——机制侧已并入 B4,
  其余留在 r7-raw-gateway-config 底稿备查。
- run-10:hygiene 阈值/heartbeat 重启语义等 5 条——留底稿备查,其中 AGENTS.md 条款侧
  待 R11 文档全面对照轮统一裁决。
