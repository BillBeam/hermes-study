# r7-01 · R7 范围钉死与网关会话核心结构地图

> 基线:NousResearch/hermes-agent @ 863e31318553cda8ad61df681d08175364d4164b(下记 @ 863e313)。
> 本篇是 R7 开轮定界底稿:切片决策、理由、run.py 结构地图、簇内文件关系总览。

## 1. 切片决策(写入台账与 scripts/assign_layers.py)

原方案(reports/round-1-survey.md 学习方案表)R7 = 整个 gateway/ + cron/(台账原 R7 桶
100 文件 / 110,440 行),超出单轮 3-6 万行 L1 预算。按 R1 方案允许的拆分条款
("如单轮超预算,允许在当轮报告里拆分…并更新台账 round 列")切成三片:

| 片 | 内容 | 文件数 | 行数 | 状态 |
|---|---|---|---|---|
| **R7(本轮)** | 会话核心与多路复用:session_key 路由、会话状态、看门狗、steer、流式桥、配置 | 16 | 38,343 | 本轮 L1 |
| R7B | 平台接入面:gateway/platforms/**(含 base.py、api_server)+ gateway/relay/** | 37 | 43,815 | 待后轮 |
| R7C | 运维生命周期与调度:其余 gateway/*.py(delivery/shutdown/slash/authz/pairing/status/kanban_watchers…)+ cron/** | 47 | 28,282 | 待后轮 |

R7 十六文件清单(台账 round=R7,全部 L1):

```
gateway/run.py                27,146   多路复用主体:TurnRunner + GatewayRunner + 启动/家务
gateway/session.py             3,490   session_key 构造 + SessionStore/SessionEntry + 上下文提示
gateway/config.py              2,688   GatewayConfig/PlatformConfig/重置策略/multiplex 配置
gateway/stream_consumer.py     2,410   agent→平台 流式投递桥
gateway/session_context.py       495   contextvars 会话上下文(取代 os.environ)
gateway/session_state.py         476   SessionState 三层状态容器(turn/conversation/persistent)
gateway/turn_lease.py            302   按 resolved session_id 的回合租约
gateway/memory_monitor.py        230   RSS 内存监控线程
gateway/wake.py                  184   后台完成事件唤醒(push 注入 / API self-post)
gateway/stream_events.py         171   类型化流事件契约
gateway/profile_routing.py       166   多 profile 分层路由
gateway/message_timestamps.py    166   时间戳只渲染一次
gateway/stream_dispatch.py       132   GatewayEventDispatcher(adapter 渲染钩子路由)
gateway/turn_context.py          131   TurnContext 提取缝(闭包→dataclass)
gateway/session_stall.py         121   会话 stall 通知策略(纯函数)
gateway/__init__.py               35   包导出
                                       合计 38,343 行
```

**切片边界理由**:
- R7 片 = "一个 agent 核心如何被多平台多用户复用"的最小闭环:消息进(路由/busy 分流)→
  回合跑(租约/状态/流式出)→ 看护(stall/expiry/inactivity/memory)→ 带外注入(steer/wake)。
  这些文件互相强耦合(run.py 直接 import 其余 15 个中的 13 个),必须同轮读。
- 平台适配器(R7B)是该核心的**消费者**:base.py 的双层守卫第一层、各平台收发细节,
  与"核心如何复用"正交,可后轮独立读(本轮涉及处以接口断言 + 行号引用交代)。
- 运维面(R7C)是该核心的**外骨骼**:shutdown/restart 细节、delivery 重投、slash 命令面、
  鉴权配对,依赖本轮概念但机制独立。
- mixin 归属说明:GatewayRunner 组合三个 mixin(gateway/run.py:5759
  `class GatewayRunner(GatewayAuthorizationMixin, GatewayKanbanWatchersMixin, GatewaySlashCommandsMixin)`),
  mixin 文件 authz_mixin.py / kanban_watchers.py / slash_commands.py 均划入 R7C——它们是
  挂在核心类上的**表面**(鉴权面/看板面/命令面),不是复用引擎本体;本轮只交代缝的存在与调用点。

## 2. run.py 结构地图(27,146 行怎么切)

顶层结构(grep `^class |^async def |^def ` @ 863e313):

```
1-1923      模块辅助(上):hygiene 冷却、脱敏、恢复注记、replay、媒体标签、重启通知…
1924-3669   模块辅助(下):multiplex 配置装载、runtime kwargs、媒体判定、
            回合进程收割 _reap_gateway_turn_processes:2841、
            回合不活跃看门狗 _watch_gateway_turn_inactivity:2951、
            session_key 解析 _parse_session_key:3352、config 装载链
3670-5758   class TurnRunner(2,089 行):单回合的进度/流式/审批协作件
5759-26041  class GatewayRunner(20,283 行):多路复用主体
  5759-5872   会话状态访问器(_sessions_map/_session_state/…)
  5873-6257   __init__:全部状态字段
  6258-7690   适配器连接/断连、telegram topic、_session_key_for_source:6679、
              _resolve_session_agent_runtime:6933、scale-to-zero
  7691-9183   队列 _enqueue_fifo:7691、per-channel 配置解析、busy 装载、
              并发上限 _claim_active_session_slot:8528、
              busy 总入口 _handle_active_session_busy_message:8742
  9184-10663  drain/shutdown 通知/restart/startup restore/obligations 重投
  10664-12658 start():10664、_spawn_supervised:11577、
              _session_expiry_watcher:11926、stall 看门狗 _check_session_stalls:12146、
              reconnect watcher
  12659-14327 stop():12659、secondary profiles、_create_adapter:13712、
              busy 斜杠快捷命令(/stop /new /queue /steer /goal):14098-14327
  14328-16275 _handle_message:14328(1,417 行主入口)、
              _prepare_inbound_message_text:15778
  16276-18966 _handle_message_with_agent:16276(2,019 行回合编排)、goal/heartbeat
  18967-21423 voice channel、媒体投递、后台任务、thread/topic 改名、通知、
              _set_session_env:21333、executor
  21424-23757 vision/STT enrich、watch 注入 _inject_watch_notification:21909、
              async delegation、agent 缓存判据 _agent_config_signature:22608、
              租约释放/rebind:22859/22888、run generation:23014-23063、
              agent 缓存治理 _enforce_agent_cache_cap:23568/_sweep_idle_cached_agents:23650
  23758-26041 stream consumer 装配、_run_agent_via_proxy:23827、_run_agent:24112、
              _run_agent_inner:24265(回合真正执行)
26042-27146 模块尾:planned stop watcher、_start_gateway_housekeeping:26131(60s 家务)、
            _start_cron_ticker:26291、start_gateway:26360、main():27021
```

依据(类边界):

`gateway/run.py:3670,5759 @ 863e313`
```python
class TurnRunner:
...
class GatewayRunner(GatewayAuthorizationMixin, GatewayKanbanWatchersMixin, GatewaySlashCommandsMixin):
```

## 3. 簇内文件关系总览

```
入站:  platform adapter(R7B) → GatewayRunner._handle_message
          ├─ 鉴权(authz_mixin, R7C)/斜杠(slash_commands, R7C)
          ├─ busy? → _handle_active_session_busy_message → steer()/queue/interrupt
          └─ 空闲 → _handle_message_with_agent
                      ├─ session.py: build_session_key / SessionStore(load/switch)
                      ├─ turn_lease.py: SessionTurnLeaseRegistry.acquire(resolved sid)
                      ├─ session_state.py: SessionState.turn(agent/started_ts/lease)
                      ├─ run generation(persistent.run_generation,#28686)
                      └─ _run_agent_inner
                           ├─ session_context.py: set_session_vars(contextvars)
                           ├─ turn_context.py: TurnContext(闭包提取缝)→ TurnRunner
                           └─ stream: agent 回调 → stream_events → stream_dispatch
                                       → stream_consumer(异步限速编辑)→ adapter
带外:  wake.py(后台完成→synthetic internal 事件 / API self-post)
        _inject_watch_notification(进程 watch 完成注入)
        steer(busy 模式下 running_agent.steer() 中途注入)
看护:  _session_stall_watcher(30s 扫,策略在 session_stall.py 纯函数)
        _session_expiry_watcher(300s 扫,会话过期重置)
        _watch_gateway_turn_inactivity(回合级 1800s 默认)
        memory_monitor.py(5min RSS 快照线程)
        _start_gateway_housekeeping(60s 家务线程)
配置:  config.py(GatewayConfig)→ load_gateway_config_for_runner(run.py:1974)
        profile_routing.py(guild/channel/thread → profile)→ 会话键命名空间
```

## 4. 台账操作记录

- scripts/assign_layers.py 在 L1 区新增 16 条显式 R7 规则 + R7B/R7C 桶规则
  (`gateway/platforms/*.py`→R7B、`gateway/relay/*.py`→R7B、`gateway/*.py`→R7C、
  `cron/**/*.py`→R7C;L2 侧 `gateway/platforms/**`→R7B、`gateway/**`→R7C、`cron/**`→R7C)。
- 重生成后 verify_ledger 三项全过:files=8530,total=2,608,452,各层行数与前轮一致
  (切片只动 round 列,不动 layer)。
