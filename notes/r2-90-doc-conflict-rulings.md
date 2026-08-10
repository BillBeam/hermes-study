# R2-90 文档-代码冲突定案(R2 机制簇范围)

> 基线 `863e31318`。对第一轮标记的 ▲(文档不符)与 ◇(文档未载)中**属于 R2 机制簇**的条目
> 逐条定案:证实 / 证伪 / 修正。每条附代码复核证据。R1 编号指 `reports/round-1-survey.md` §2.16。

## A. 结论一览

| # | 条目(R1 出处) | 定案 | 证据 |
|---|---|---|---|
| 1 | grace-call 循环注释(AGENTS.md:351-353,R1 §2.16-1) | **证实(死代码)** | 见 §B.1 |
| 2 | max_iterations 默认 500(AGENTS.md:328,R1 §2.16-2) | **证实(实为 90)** | 见 §B.2 |
| 3 | 中断不注入部分响应(agent-loop.md:124,R1 §2.16-3) | **证实(redirect 会注入)** | 见 §B.3 |
| 4 | 请求包在 _interruptible_api_call(agent-loop.md:108,R1 §2.16-4) | **证实(默认流式)** | r2-23 定案 c / r2-03 |
| 5 | 多工具并发 via ThreadPoolExecutor(agent-loop.md:133,R1 §2.16-5) | **证实(实为分段调度)** | r2-05 §1 |
| 6 | "system_and_3" 缓存布局(website/docs/developer-guide/context-compression-and-caching.md:396,R1 §2.16-6) | **证实(默认是静态前缀切分)** | r2-23 定案 b |
| 7 | fallback "returns False if already activated"(provider-runtime.md:180,R1 §2.16-7) | **证实(靠 _fallback_index 推进)** | r2-23 定案 a |
| 8 | 辅助任务"独立自动探测链"(provider-runtime.md:196,R1 §2.16-8) | **证伪→修正(默认 main-first)** | r2-21 定案 4a |
| 9 | FailoverReason 驱动恢复未见于文档(R1 ◇) | **证实** | r2-23 定案 d |
| 10 | Nous Portal 双线路由未见于文档(R1 ◇ 2.2-2) | **证实** | r2-20 定案 a |
| 11 | Codex Harmony 中和未见于文档(R1 ◇ 2.2-9) | **证实** | r2-20 定案 b |
| 12 | Anthropic OAuth/Claude Code 身份伪装(R1 ◇ 2.2-14) | **证实(伪装部分文档盲区)** | r2-20 定案 c |
| 13 | 凭据池条目文档不符(R1 ▲ 2.2-4) | **证实(5 处具体不符)** | r2-22 定案 10.1 |
| 14 | nous_rate_guard 未见于文档(R1 ◇ 2.2-8) | **证实** | r2-22 定案 10.2 |
| 15 | 用量归一与定价未见于文档(R1 ◇ 2.2-11) | **证实** | r2-21 定案 4b |
| 16 | **[R2 新增]** 流式 stale/读超时注释漂移 | **新发现** | 见 §B.4 |

R2 范围内:▲/◇ 条目 **15 条定案(14 证实 + 1 证伪修正)+ 1 条新发现**。无一条被推翻为"文档正确"。

## B. 需本人复核的四条(其余引各底稿定案)

### B.1 grace-call 死代码 — 证实

`_budget_grace_call` 在 while 条件里作为兜底(`agent/conversation_loop.py:1415` `... or agent._budget_grace_call`),
但全仓仅有两处**写**,都是 `= False`:

```
agent/agent_init.py:892:    agent._budget_grace_call = False        # 初始化
agent/conversation_loop.py:1445:            agent._budget_grace_call = False   # 消费处置回 False
```

无任何 `= True`。故 `or agent._budget_grace_call` 分支永不可达。真实预算兜底走 finalizer 的
无工具 summary 调用(`agent/turn_finalizer.py:127-141`,见 r2-13 §1)。AGENTS.md:351-353 宣称
"a one-turn grace call" 与实现不符。

### B.2 max_iterations 默认值 — 证实为 90

```
run_agent.py:446:        max_iterations: int = 90,  # Default tool-calling iterations (shared with subagents)
agent/agent_init.py:470:    max_iterations: int = 90,  # Default tool-calling iterations (shared with subagents)
```

构造默认是 **90**。文档/docstring 的 500(AGENTS.md:328、`agent/iteration_budget.py:5`)是**过时**:
500 只作为 `cli.py:14484-14485` 的 `getattr(self.agent, "max_iterations", 500)` **兜底默认**出现
(即 agent 对象没有该属性时的回退),不是真实构造默认。

### B.3 中断不注入部分响应 — 证实(redirect 会注入)

agent-loop.md:124 称中断时 "No partial response is injected into conversation history"。
实际 **redirect 路径显式注入**:`_apply_active_turn_redirect`(`agent/conversation_loop.py:122-201`)把已流出的
可见文本剥 `<think>` 后作为降级 checkpoint 注入 messages,脚手架文本写入 api_content 侧车供 provider 回放
(见 r2-02 §4)。文档描述的是纯 interrupt 语义,漏了 redirect 这条新增路径。

### B.4 [R2 新增] 流式 stale / 读超时注释漂移

`agent/conversation_loop.py:2330-2331` 注释写 "90s stale-stream detection, 60s read timeout",与代码不符:

- 流式 stale 默认 **180s**:`agent/chat_completion_helpers.py:4063` `env_float("HERMES_STREAM_STALE_TIMEOUT", 180.0)`
- 流式读超时默认 **120s**:`agent/chat_completion_helpers.py:3028` `env_float("HERMES_STREAM_READ_TIMEOUT", 120.0)`
- 90s 是**非流式** stale 基线:`run_agent.py:1426` `return 90.0, True`

`website/docs/reference/environment-variables.md:802-803` 的默认值与代码一致(180/120)——所以这是
**源码内注释**漂移,不是文档漂移。已据此修正本项目 `notes/r2-03`。归类:代码内注释-代码冲突(仍是学习产出)。

## C. 对台账/报告的处置

以上 16 条(15 定案 + 1 新增)进 round-2 报告的"文档-代码冲突定案"节。其中 R1 已收录 15 条,
本轮把结论从"第一轮判断"升级为"精读证实/证伪";第 16 条为 R2 新发现。以代码为准的原则下,
凡后续轮次引用这些机制,均以本定案为准。
