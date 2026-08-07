# r7-95 · 测试作为行为规格:运行记录

> 环境:/home/user/hermes-venv(python3 venv,`pip install -e "/home/user/hermes-agent[dev]"`),
> 执行方式 `HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh <files>`。
> 补装:aiohttp(test_wake_delivery 依赖,venv 初装缺失,非代码问题)。

## 批次 1:会话状态与看门狗核心(5 文件,39 passed / 0 failed)

```
tests/gateway/test_turn_lease.py                 # 租约:争用串行化/超时降级/身份检查释放/rebind
tests/gateway/test_session_stall_watchdog.py     # stall:notify-once/观测缺失不算恢复/两处候选源
tests/gateway/test_session_state_cleanup.py      # SessionState 三层清理边界
tests/gateway/test_session_context_inheritance.py# contextvars 继承泄漏:入口 reset 语义
tests/gateway/test_memory_monitor.py             # RSS 监控:启动幂等/关机快照
```

## 批次 2:steer/wake/流式/路由(10 文件,其中 5 文件复跑计 83 passed / 0 failed)

```
tests/gateway/test_steer_command.py              # /steer 忙时注入与回落
tests/gateway/test_steer_fifo_overwrite.py       # steer 与 FIFO 边界:不双投不丢失
tests/gateway/test_wake_delivery.py              # wake 两策略:push 合成事件 / API self-post(429 退避)
tests/gateway/test_stream_consumer.py            # 流式桥主循环
tests/gateway/test_stream_consumer_draft.py      # Telegram 原生 draft 流
tests/gateway/test_stream_consumer_fresh_final.py# fresh-final:长流终稿新消息化
tests/gateway/test_stream_consumer_silence.py    # 有意沉默标记抑制
tests/gateway/test_stream_consumer_thread_routing.py # 线程路由元数据
tests/gateway/test_profile_routing.py            # profile 分层匹配 specificity
tests/gateway/test_handoff_thread_session_key.py # handoff 线程会话键
```

## 批次 3:busy/会话/缓存(15 文件,153 passed / 0 failed)

```
tests/gateway/test_session.py                        # build_session_key 全分支 + SessionStore 基础
tests/gateway/test_agent_cache.py                    # agent 缓存复用/逐出
tests/gateway/test_busy_session_ack.py               # busy ack 去抖
tests/gateway/test_internal_event_never_interrupts_busy_session.py  # internal 事件护栏(不打断不 steer)
tests/gateway/test_compression_interrupt_demotion_56391.py          # 压缩飞行中 interrupt→queue 降级
tests/gateway/test_max_concurrent_sessions.py        # 并发会话上限槽
tests/gateway/test_queue_command.py                  # /queue 命令
tests/gateway/test_queue_consumption.py              # 队列消费顺序(消息边界)
tests/gateway/test_10710_auto_reset_evicts_cached_agent.py          # auto-reset 逐出缓存 agent(#10710)
tests/gateway/test_35809_auto_reset_clean_context.py                # auto-reset 清会话域(#35809)
tests/gateway/test_48031_model_switch_after_auto_reset.py           # 边界后 /model 覆盖不残留(#48031)
tests/gateway/test_session_boundary_security_state.py               # 边界安全态漏斗(审批/update 提示)
tests/gateway/test_session_hygiene.py                # hygiene 预压缩
tests/gateway/test_interrupt_key_match.py            # interrupt 键匹配(run generation 绑定)
tests/gateway/test_session_env.py                    # _set_session_env / session_context 绑定
```

**小计:30 个测试文件,275 个用例,全部通过,0 失败。**
(批次 2 首跑时 test_wake_delivery 2 例因 venv 缺 aiohttp 报 ModuleNotFoundError,
装依赖后全绿;记录为环境问题,非行为差异。)

## 批次 4:规格价值 Top-42 大盘(42 文件,440 passed / 0 failed,21.6s)

清单来源:notes/r7-raw-tests-inventory.md 第二节(子代理按 import 符号判定归属,
覆盖十个机制组;6 个模块唯一直测卷 turn_lease/stream_events/wake/memory_monitor/
message_timestamps/turn_context 全部入选;与批次 1-3 有部分重叠)。
执行:`bash scripts/run_tests.sh $(cat spec42.txt)` → **42 files, 440 tests passed, 0 failed**。

## 总计

四批合并去重后:**约 60 个测试文件、700+ 用例,全部通过,0 行为失败**
(仅一次环境性失败:venv 缺 aiohttp,补装后全绿)。
本簇 issue 号命名测试 12 个(#7100 #10710 #13121 #35809 #35994 #42039 #48031 #53175
#64674 #71671 #73297 #75349)+ 4 个后缀命名(#11016 #30170 #31501 #76354),
全部作为行为规格在批次中运行或在底稿中引用。
