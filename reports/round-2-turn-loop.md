# R2 报告:回合主循环与模型接入

**一句话结论:回合引擎学透,双产出到位。**

- 基线:`863e31318`(只读,工作树零改动,校验一致)
- 本轮机制簇:回合主循环与模型接入(R1 方案 §3.3 的 R2)
- 分支:`claude/hermes-agent-round-2-ogproh`(从合并后的 main 起);R1 已 PR #1 合入 main
- 产出形态:**底稿 12 篇 `notes/r2-*`(求全求证)+ 成品章 1 篇 `chapters/r2-*`(求读,含 5 张 Mermaid 图)**,
  双产出制度已写入 CLAUDE.md 对后续每轮生效。

---

## 1. 台账报数(三项校验全过)

`scripts/assign_layers.py` 本轮起保留 status 列(重生成不清空进度);R2 范围在台账中显式钉死。
`scripts/verify_ledger.py /home/user/hermes-agent data/ledger.tsv` 实测:

```
OK baseline=863e31318 files=8530 total_lines=2608452
  L1: files=412  lines=382,770
  L2: files=2282 lines=811,076
  L3: files=1895 lines=602,085
  L4: files=560  lines=55,902
  LT: files=3381 lines=756,619
  SUM == repo total: 2,608,452   ✓ (文件集一致 + 行数复算一致 + 分层加总 = 全仓总行数)
```

本轮 status 更新:

| status | 文件数 | 说明 |
|---|---:|---|
| R2-deep-read | 46 | R2 机制簇 L1 精读文件(68,645 行),含 run_agent/conversation_loop/turn_*/adapters/credential_pool/error_classifier/prompt_caching/auxiliary_client 等 |
| R2-structure | 72 | provider 插件注册面(plugins/model-providers/ + providers/),结构级理解 |
| R1-inventoried | 8412 | 尚未开工的文件 |

R2 覆盖 118 文件 / 71,531 行。**方案修订两处**(已写入台账 round 列并在此说明理由):

1. **上下文工程(压缩/构建)并入 R5**。R1 原方案把它列为独立候选,但精读发现压缩与会话状态、
   持久化(active/compacted 双标志、in-place archive_and_compact、resume 世系)强耦合,拆开会把一个
   机制切碎;并入 R5"会话状态与持久化"一轮学更完整。台账中 context_compressor/conversation_compression/
   prompt_builder/system_prompt 等 13 文件已改标 R5。
2. **委派/多智能体并入 R9**。moa_loop/subagent_lifecycle/delegation_context 与 batch_runner(研究管线)
   共享"子代理隔离"概念,合并到 R9"研究管线"一轮。

## 2. 底稿与成品章清单

**底稿 `notes/`(12 篇,凡断言紧跟 `路径:行号 @ 863e313` + 代码原文)**:
`r2-01-turn-loop`(外层循环/退出路径/六级空响应阶梯)、`r2-02-intervention`(三级介入)、
`r2-03-streaming`(强制流式/单写者栅栏)、`r2-05-tool-executor`(分段调度/两道门)、
`r2-06-turn-context-sidecar`(前奏/api_content 侧车)、`r2-13-turn-finalizer`(收尾咽喉)、
`r2-20-adapters`(4 wire 协议适配器)、`r2-21-auxiliary-metadata-pricing`(辅助 LLM/元数据/定价)、
`r2-22-credential-pool`(凭据池/限流护栏)、`r2-23-classify-retry-fallback-cache`(分类/重试/故障转移/缓存断点)、
`r2-90-doc-conflict-rulings`(定案)、`r2-95-tests`(测试运行记录)。

**成品章 `chapters/r2-turn-loop-and-model-access.md`**:独立可读,面向没读过代码的工程师,
5 张 GitHub 可渲染的 Mermaid 图(turn 生命周期、三级介入、api_mode 分发、故障转移、六级空响应阶梯),
关键断言以 `路径:行号 @ 863e313` 溯源。这是 R12《设计蓝图》的正文之一。

## 3. 行为规格测试(225 用例全过)

官方 `scripts/run_tests.sh`(密封环境、per-file 子进程隔离)跑 R2 代表性测试:分类器 72、缓存 19、
retry_state 3、凭据池冷却/路由/有界轮换 26、fallback 链/冷却 21、辅助 main-first 15、定价 11、
finalizer 5、Nous 双线 25、retry_utils……**合计 225 passed / 0 failed**。唯一波折:缺可选依赖 `anthropic`
时 2 例 ImportError(非代码缺陷),补装后全过。详见 `notes/r2-95-tests.md`。hermes-agent 保持基线、零改动。

## 4. 文档-代码冲突定案(R2 范围,16 条)

对 R1 标记的 ▲/◇ 中属本簇的逐条定案(证据见 `notes/r2-90`):**15 条定案(14 证实 + 1 证伪修正)+ 1 条
R2 新发现**,无一条被推翻为"文档正确"。要点:

- **▲ 全部证实/修正**:主循环不在 run_agent.py、grace-call 是死代码、max_iterations 默认 90 非 500、
  默认流式非 `_interruptible_api_call`、工具分段调度非无脑并发、缓存默认"静态前缀切分"非 system_and_3、
  fallback 靠 `_fallback_index` 推进非"already activated 返回 False"、中断 redirect 会注入 checkpoint;
  辅助任务"独立探测链"**证伪**为默认 main-first。
- **◇ 全部证实**:错误分类器恢复体系、Nous Portal 双线路由、Codex Harmony 中和 + issuer 隔离、
  Anthropic OAuth 身份伪装、nous_rate_guard 跨会话断路器、用量归一与定价——均"代码有、文档无"。
- **R2 新发现**:`conversation_loop.py:2330-2331` 注释"90s stale / 60s read"是**源码内注释漂移**,
  实际流式 stale 180s、读超时 120s(env-variables.md 与代码一致),90s 是非流式基线。已据此修正本项目 notes。

L1 完成标准自评:对簇内每个机制,能讲清问题/实现/设计理由/取舍(成品章即证),能凭底稿重实现同等机制
(底稿每节末列"重实现要点"),达标。

## 5. 下一轮建议

**下一轮做 R3:工具基础设施**(`tools/registry.py`、`model_tools.py`、`toolsets.py`、schema 清洗、
输出限长、tool_search 渐进披露、分层审批与安全层、`code_execution_tool` 的 RPC、`mcp_tool` 客户端侧安全)。
理由:R2 已学透"循环怎么调模型、怎么执行一批工具",R3 自然下沉到"工具本身怎么注册/发现/分发/限长/审批"
——是 R2 §3.9 分段调度的上游。R3 与 R4(终端与执行环境)相邻,可在同一心智模型下连续推进。

打法沿用 R2:主线精读注册/分发/安全核心(registry、model_tools、approval、path/url 安全、code_execution),
schema 清洗与 mcp 客户端可用子代理并行深挖;产出底稿 `notes/r3-*` + 成品章 `chapters/r3-*`(含 Mermaid);
跑 tools 相关测试作行为规格;定案 R3 范围的 ▲/◇;更新台账 status 为 `R3-*` 并重跑校验报数。

无阻塞事项。真跑模型仍需任一 provider 凭据(见 R1 报告 §1.5),纯代码学习与测试不依赖它;
本轮已实测 venv + `.[dev]` + 补装 `anthropic` 后测试全绿。
