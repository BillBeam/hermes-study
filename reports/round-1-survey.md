# hermes-agent 学习第一轮:全仓测绘、能力点挖掘、学习方案

**一句话结论:重型多面 harness,核心可学,已全仓归层。**

- 研究对象:`https://github.com/NousResearch/hermes-agent`
- **基线(固定不动)**:`863e31318553cda8ad61df681d08175364d4164b  2026-08-06 17:36:40 +0530  "fix: close simplify-pass findings — scheduler sibling site + home-unresolvable totality"`
- 本轮工作方式:clone 到 `/home/user/hermes-agent`(只读)→ 全量盘点脚本 → 14 路子系统并行挖掘(每条断言附 `路径:行号 @ 863e313` + 代码原文)→ 分层台账 + 校验脚本 → 本报告。
- 证据约定:下文所有 `路径:行号` 均相对 hermes-agent 仓库根,`@ 863e313` 省略不再重复标注。

---

## 一、全仓测绘

### 1.1 规模

由 `scripts/inventory.py`(行数规则唯一权威:UTF-8 可解码为文本,行数 = `\n` 数,末行无换行补 1)实测:

```
文件总数   8,530(git ls-files)
文本总行数 2,608,452
二进制文件 560(图片/字体/PDF/音频等,行数记 0)
```

主要语言:Python 3,846 文件、Markdown 1,491、TypeScript 1,366 + TSX 638。

### 1.2 目录结构与规模分布(文本行数)

| 目录 | 行数 | 内容 |
|---|---:|---|
| tests/ | 651,340 | pytest 套件(2,740 文件;AGENTS.md 自述 ~17k tests) |
| apps/ | 320,823 | Electron 桌面应用 + shared JSON-RPC 包 + bootstrap-installer(Tauri/Rust) |
| website/ | 266,947 | Docusaurus 文档站(含中文翻译镜像) |
| hermes_cli/ | 206,371 | CLI 子命令、setup 向导、配置、皮肤引擎、web 仪表盘服务端 |
| skills/ + optional-skills/ | 315,505 | 内置技能 + 可选技能(Markdown + 脚本) |
| plugins/ | 142,432 | 插件体系:memory/model-providers/kanban/context_engine/image_gen/observability/platforms |
| agent/ | 131,676 | Agent 内核 135 文件:provider 适配、上下文压缩、记忆、缓存、显示…… |
| tools/ | 120,109 | 工具实现 135 文件 + environments/(8 个执行后端) |
| gateway/ | 100,668 | 消息网关(约 55 个核心文件 + platforms/ 适配器) |
| ui-tui/ | 92,558 | Ink(React)终端 UI,含自维护 hermes-ink 分叉 |
| (root) | 84,386 | 巨型单文件:cli.py 18,555 行、hermes_state.py 9,691、run_agent.py 8,167…… |
| web/ | 52,114 | dashboard 浏览器前端(xterm.js 嵌入 TUI) |
| scripts/ | 31,578 | 测试基建(CI 平价运行器)、发布、CI 分类器 |
| tui_gateway/ | 25,563 | TUI 的 Python JSON-RPC 后端 |
| native/ | 14,793 | FTS5 CJK 分词原生扩展 |
| cron/ | 9,772 | 调度器 + 任务存储 + blueprint/suggestion 目录 |
| acp_adapter/ | 5,831 | ACP 协议服务器(Zed/JetBrains/VS Code 接入) |
| docs/ | 4,156 | 内部设计文档(wire contract、RCA、micro-compaction、session-lifecycle) |
| 其余 | ~13.2 万 | locales、nix、docker、.github、contributors、mcp-research-data 等 |

### 1.3 核心文件规模实测(wc -l)

```
cli.py 18,555 | hermes_state.py 9,691 | run_agent.py 8,167 | gateway/run.py 27,146
agent/conversation_loop.py 7,334 | tools/mcp_tool.py 7,230 | agent/context_compressor.py 6,883
cron/scheduler.py 4,428 | tools/delegate_tool.py 3,931 | gateway/session.py 3,490
tools/terminal_tool.py 3,432 | hermes_state_search.py 2,230 | tools/code_execution_tool.py 2,087
agent/curator.py 2,019 | model_tools.py 1,569 | toolsets.py 1,004
```

注意:AGENTS.md 自述 run_agent.py "~12k LOC"、cli.py "~11k LOC" 均与实测不符(8,167 / 18,555)——地图过期,以代码为准。

### 1.4 模块依赖真相

AGENTS.md 画的依赖链(`tools/registry ← tools/* ← model_tools ← run_agent/cli`)只描述了**工具注册**这一条线。
用脚本对全部顶层模块的 import 做静态扫描,真实情况是**几乎完全互联的循环依赖图**(agent ↔ run_agent、tools ↔ model_tools、gateway ↔ cli、hermes_constants ↔ hermes_cli 等),靠**函数内延迟 import** 避免导入时循环。这是"单体仓库 + 巨文件 + 后拆模块"演化路径的直接痕迹,学习时不能假设洋葱式分层。

运行时的真实分层(以代码为准):

```
入口:hermes(shell)→ hermes_cli/main.py(profile 覆盖最先执行)→ cli.py / gateway/run.py / tui_gateway / batch_runner
内核:run_agent.py 的 AIAgent(骨架+状态)+ agent/conversation_loop.py(真实主循环)
工具:tools/registry.py(注册表)← tools/*.py(import 时自注册)← model_tools.py(发现+分发)← toolsets.py(暴露面控制)
状态:hermes_state.py SessionDB(SQLite+FTS5)
外设:gateway/platforms、cron、plugins、skills、ui-tui/tui_gateway/acp_adapter/apps
```

关键证据——主循环并不在 AGENTS.md 说的 run_agent.py 里,`run_conversation` 只是转发器:

`run_agent.py:7772` 起:
```python
        """Forwarder — see ``agent.conversation_loop.run_conversation``."""
        from agent.conversation_loop import run_conversation
```

真实主循环 `agent/conversation_loop.py:1415`:
```python
    while (api_call_count < agent.max_iterations and agent.iteration_budget.remaining > 0) or agent._budget_grace_call:
```

(本节其余证据见能力点清单,不重复。)

### 1.5 环境可运行性(本轮实测)

- `python3 -m venv` + `pip install -e ".[dev]"` 在本会话环境安装成功(Python 3.11.15,满足 `.python-version` = 3.11);网络无拦截(GitHub clone、PyPI 均通畅,经会话代理)。
- 官方规范测试入口跑通(密封环境、per-file 子进程隔离):`HERMES_PYTHON=<venv>/bin/python bash scripts/run_tests.sh tests/agent/test_turn_finalizer_iteration_limit_exit.py` → `5 tests passed, 0 failed`。hermes-agent 工作树保持基线、零改动(`git status` 干净)。
- **真跑模型所需配置(等待提供,不自行配置)**:任一模型 provider 凭据写入 `~/.hermes/.env` —— `NOUS_API_KEY`(或 `hermes setup --portal` OAuth)/ `OPENROUTER_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 之一即可驱动核心循环;外围工具键(`FIRECRAWL_API_KEY` web 搜索、`FAL_KEY` 图像生成等,全表见 `.env.example`,496 行)可选。纯代码学习与测试套件不需要任何凭据。

---

## 二、harness 能力点清单


标记约定:`◇` = 代码有而官方文档(README/AGENTS.md/website docs)没讲;`▲` = 文档宣称与代码不符;`★` = 在 2.15 有完整详述。

由 14 路子系统并行深挖汇总:能力点 **170** 个,其中 **◇ 60** 个为『代码有、官方文档没讲』,**▲ 69** 个附带『文档宣称与代码不符』记录,另有 **54** 条独立文档-代码冲突(2.17 节收录重点,全量见附卷)。

呈现方式:本节(主卷)给出每个子系统的机制综述 + 全部能力点目录(问题/证据落点/规模/价值)+ 12 条跨子系统精选详述(2.16);**每一条能力点的完整四要素与逐字代码摘录见附卷 `reports/round-1-capabilities-full.md`**(由 `data/capability-mining.json` 渲染,约 37 万字符,超出单条消息承载,故拆卷)。证据可信度:从 14 路产出中抽样 15 条 `路径:行号` 断言逐一与基线源码比对,15/15 逐字命中。


### 2.1 Agent 核心循环(run_agent.py AIAgent + agent/conversation_loop.py run_conversation 及回合生命周期协作者)

这是 hermes-agent 的心脏:AIAgent 类(run_agent.py,8167 行)持有全部运行时状态与线程安全的用户介入 API(interrupt/steer/redirect/流式回调/凭据刷新),而真正的主循环在 agent/conversation_loop.py 的 run_conversation(约 6000 行的 while 循环)。每个用户回合经历:build_turn_context 前奏(stdio 防护、系统提示恢复、MCP 刷新、preflight 压缩、插件注入、api_content 侧车组装)→ 外层迭代循环(预算判定、redirect 应用、消息重建与逐字节回放)→ 内层重试循环(TurnRetryState 一次性守卫下的限流退避、按提供商 OAuth 刷新、压缩重启、截断续写、内容过滤故障转移)→ 响应分流(工具批次经 segment planner 分段并发执行,或文本终局经空响应恢复阶梯与验证门)→ finalize_turn 收尾(预算耗尽 summary、trajectory/持久化逐项防护、kanban 上报)。设计上最鲜明的特征是"分层恢复":几乎每种失败(空响应、截断、丢 tool-call、流中断、会话持久化失败)都有专用的有界重试阶梯,且每级用一次性布尔守卫防止无限循环;以及"persist-what-you-send"不变式:发给 provider 的字节与干净转录分离存储(api_content 侧车),保证 prompt cache 前缀逐字节稳定。中断被细分为三个粒度(硬停、steer 不打断、redirect 只取消模型请求并原地重建回合),流式输出用单调令牌栅栏解决重试竞态。预算耗尽的 grace-call 标志位是死代码(从未置 True),实际兜底走 finalize_turn 的无工具 summary 调用。

关键文件(共 15 个,行数实测,全表见附卷):`run_agent.py`(8167), `agent/conversation_loop.py`(7334), `agent/turn_context.py`(1275), `agent/turn_finalizer.py`(756), `agent/tool_executor.py`(2403), `agent/iteration_budget.py`(62) 等

**能力点目录(共 12 条):**

1. **迭代预算与预算耗尽收尾(IterationBudget + grace-call 死标志 + 无工具 summary 兜底)** ▲ — agent 循环可能无限打转烧钱。证据:`agent/conversation_loop.py:1415` 等4处;规模:约 200 LOC(iteration_budget.py 62 行 + 循环判定 + finalizer 兜底 + c…;价值:高。
2. **三级用户介入:interrupt(硬停)/ steer(不打断注入)/ redirect(只取消模型请求)**★ — 用户在 agent 干活时说话有三种意图:彻底停下、顺带补充指示、纠正方向但不作废已完成的工作。证据:`run_agent.py:3121` 等4处;规模:约 400 LOC(run_agent.py:3028-3392 + runtime_helpers steer 注入 …;价值:高。
3. **Redirect 活转重建:_apply_active_turn_redirect + restart_with_redirected_messages 预算退款重试** ◇ ▲ — 取消一个进行中的模型请求后,不完整的 provider reasoning 块不能回放(Anthropic 签名/Responses 配对要求),而把已流式展示的思维链写回转录…。证据:`agent/conversation_loop.py:1416` 等4处;规模:约 150 LOC 核心(conversation_loop.py:122-201 + 循环内 5 处 preserve…;价值:高。
4. **TurnRetryState:单次 API 尝试的一次性恢复守卫矩阵** ◇ — 内层重试循环对同一次模型调用要做十几种截然不同的恢复(按提供商 OAuth 刷新、429 凭据池、压缩重启、续写重启、思维签名剥离、图片缩放、llama.cpp 语法回退等),…。证据:`agent/turn_retry_state.py:43` 等3处;规模:92 LOC dataclass 本体;价值:中。
5. **无消费者也强制流式 + 流单写者令牌栅栏(#65991)** ◇ ▲ — 非流式调用无法区分'provider 还在生成'与'连接挂死用 SSE ping 续命',子 agent 等安静模式调用者会无限悬挂。证据:`agent/conversation_loop.py:2329` 等3处;规模:约 400 LOC(run_agent.py:6026-6434 流状态管理 + 循环内 _use_streaming …;价值:高。
6. **空响应六级恢复阶梯** ◇ — 弱模型/劣化 provider 常在工具结果后返回空内容、只输出 reasoning、或流中断只送出一半——直接判失败会浪费整回合已完成的工具工作,盲目重试又会无限烧预算。证据:`agent/conversation_loop.py:6597` 等4处;规模:约 320 LOC(conversation_loop.py:6588-6903)+ 分散的计数器复位点;价值:高。
7. **截断续写(指数放大输出预算)与 dropped tool-call 再提示** ◇ — 输出被 max_tokens 截断或流中途断线时,直接返回半截答案不可接受。证据:`agent/conversation_loop.py:3106` 等4处;规模:约 300 LOC(3020-3160 截断分类 + 5667-5682 预算放大 + 6962-7018 droppe…;价值:中。
8. **工具批次分段调度(segment planner)+ 并发执行的中断/超时/授权栅栏** ▲ — 整批并发会让有副作用的工具乱序执行,整批串行又浪费只读工具的并行机会。证据:`run_agent.py:7614` 等4处;规模:约 1700 LOC(tool_executor.py 并发+分段执行器 + tool_dispatch_helpers…;价值:高。
9. **验证门劫持终局:verify-on-stop / pre_verify 钩子 / kanban 终态工具守卫 + 候选答案保底** — 模型想停(finish_reason=stop)不等于任务完成:改了代码没验证、kanban worker 没调 kanban_complete 就叙述性收尾。证据:`agent/conversation_loop.py:7089` 等4处;规模:约 230 LOC(conversation_loop.py:7037-7206 + finalizer 保底分支);价值:高。
10. **TurnContext 回合前奏 + api_content『persist-what-you-send』侧车** ◇★ — 每回合的一次性设置(系统提示恢复、preflight 压缩、插件/记忆注入)与循环体纠缠会让 6000 行循环不可维护。证据:`agent/turn_context.py:309` 等4处;规模:turn_context.py 1275 行 + 循环内约 60 行回放逻辑;价值:高。
11. **阶段感知错误分诊:本地处理 bug 与 API 错误按 traceback 模块集区分** ◇ — 循环的大 try/except 同时罩住 API 请求和响应后处理。证据:`agent/conversation_loop.py:7234` 等3处;规模:约 95 LOC(conversation_loop.py:7215-7308);价值:中。
12. **活动心跳与 kanban 带外 steer 注入(_touch_activity)** ◇ — 网关按不活跃超时(默认 1800s)杀会话,长退避/长工具间隙会被误杀且死因不可知。证据:`run_agent.py:3707` 等3处;规模:约 160 LOC(run_agent.py:3666-3790)+ 循环内十余个 touch 调用点;价值:中。

### 2.2 模型提供商与 API 适配层 (Model Providers & API Adapter Layer)

该子系统是 Hermes agent harness 的"多 provider 接入与续命"层,把 20+ 推理 provider 的差异从核心 agent loop 里彻底剥离。核心是 api_mode 抽象:同一个 loop 通过 determine_api_mode() 把请求分派到 chat_completions / anthropic_messages / codex_responses / bedrock_converse 四种 wire 协议,各 adapter(anthropic/codex_responses/gemini_native/bedrock/vertex/azure_identity)负责 messages、tools、response 的双向翻译并 normalize 成统一的 OpenAI 风格对象。Provider 元数据用声明式 ProviderProfile + 34 个自注册插件(plugins/model-providers/)承载,支持 $HERMES_HOME 用户覆盖。续命机制由三块组成:CredentialPool 做多 key/OAuth 池轮换与分级冷却、跨进程 token 同步;error_classifier 用 FailoverReason 枚举把错误映射成恢复动作;try_activate_fallback 做 turn-scoped 多级 provider/model 热切换并同步 client/协议/池/缓存/上下文窗全部运行时状态。此外还有 prompt cache 4-断点保护策略、Nous 跨会话 RPH 护栏、auxiliary_client 的副任务独立路由、usage 归一与定价、models.dev 元数据探测等配套。整体约 3.8 万行,是 harness 里最复杂的子系统之一。

关键文件(共 25 个,行数实测,全表见附卷):`agent/auxiliary_client.py`(9976), `agent/chat_completion_helpers.py`(4363), `agent/model_metadata.py`(3370), `agent/anthropic_adapter.py`(3177), `agent/credential_pool.py`(3147), `agent/error_classifier.py`(1841) 等

**能力点目录(共 15 条):**

1. **多 api_mode 抽象与统一分发 (chat_completions / anthropic_messages / codex_responses / bedrock_converse)** — 同一个 agent loop 要驱动 OpenAI-wire、Anthropic 原生 Messages、OpenAI Responses、AWS Bedrock Conver…。证据:`agent/chat_completion_helpers.py:467` 等3处;规模:分发核心约 60 行(451-511);价值:高。
2. **Nous Portal 双线协议路由 (同 provider 按模型走 anthropic_messages 或 chat_completions)** ◇ ▲ — Nous Portal 既在 /v1/chat/completions 上代理 OpenAI-兼容目录,又在 /v1/messages 上原生服务 anthropic/* 目录。证据:`hermes_cli/providers.py:666` 等2处;规模:约 50 行;价值:中。
3. **Anthropic prompt cache 保护策略 (4 断点 + 静态前缀切分 + failover 重贴)** ▲★ — Anthropic 每请求最多 4 个 cache_control 断点。证据:`agent/prompt_caching.py:382` 等3处;规模:394 行;价值:高。
4. **凭据池轮换 (多 key/OAuth 池、状态机、冷却 TTL、跨进程同步、按状态码分级)** ▲ — 同一 provider 可能有多把 API key 或多个 OAuth 账号。证据:`agent/credential_pool.py:332` 等3处;规模:3147 行;价值:高。
5. **错误分类器 (FailoverReason 枚举驱动恢复策略)** ◇ — 一个 API 错误可能意味着换 key、换模型、压缩上下文、降级图片、剥离 replay blob、退避重试或直接放弃——retry loop 不该自己去反复解析原始异常。证据:`agent/error_classifier.py:90` 等3处;规模:1841 行;价值:高。
6. **Fallback model 链 (turn-scoped 多级 provider/model 切换 + 池重绑 + 缓存重评估)** ▲ — 主模型持续报错时要按配置的 (provider, model) 链逐个切换,换 provider 时要重建 client、换 wire 协议、重绑凭据池防止污染主 provid…。证据:`agent/chat_completion_helpers.py:1756` 等3处;规模:activation 约 390 行(1730-2116);价值:高。
7. **辅助 LLM 路由 (auxiliary_client:压缩/视觉/标题/搜索的独立 provider 链)** ▲ — 压缩、视觉、web 抽取、会话搜索、标题生成等副 LLM 任务不应污染主对话模型的凭据/上下文,又要能默认复用用户主模型、支持 per-task 覆盖、有自己的 fallbac…。证据:`agent/auxiliary_client.py:3607` 等3处;规模:9976 行;价值:高。
8. **Nous RPH 跨会话限流护栏 (防 429 重试放大)** ◇ — Nous Portal 一次 429 会触发多达 9 次 API 调用(3 SDK retry × 3 Hermes retry),每次都吃 RPH 配额。证据:`agent/nous_rate_guard.py:3` 等2处;规模:325 行;价值:中。
9. **Codex Responses 适配 (Harmony token 中和 + encrypted_content issuer 隔离)** ◇ — ChatGPT Codex 后端保留 Harmony wire token,历史里出现字面量会被 invalid_prompt 拒。证据:`agent/codex_responses_adapter.py:83` 等2处;规模:1590 行;价值:中。
10. **Provider profile 插件注册表 (声明式 ProviderProfile + 34 个内置 provider 插件)** — 20+ 推理 provider 的 auth/endpoint/quirk 若用一堆布尔 flag 传给 transport 会失控。证据:`providers/base.py:43` 等3处;规模:base.py 238 行 + 34 个插件目录(13-213 行不等);价值:高。
11. **用量归一与定价 (跨 4 种 usage 形状 + 官方定价快照 + Codex reset credit 兑换)** ◇ — Anthropic/Codex Responses/OpenAI Chat/各 OpenAI-兼容代理的 usage 字段形状各异(cache read/write、reaso…。证据:`agent/usage_pricing.py:1261` 等2处;规模:usage_pricing 1432 行 + account_usage 902 行;价值:中。
12. **模型元数据探测与缓存 (models.dev 目录 + 本地端点 num_ctx 探测 + 从错误反推上下文窗)** — 上下文窗口/最大输出/定价/能力位要么来自 models.dev 社区目录,要么要向本地端点(Ollama/LM Studio/vLLM)实时探测,还要在 context_le…。证据:`agent/models_dev.py:11` 等2处;规模:model_metadata 3370 行 + models_dev 903 行;价值:中。
13. **Bedrock / Vertex / Azure Entra 企业端点适配** — AWS Bedrock 用 boto3 Converse 而非 HTTP、需 stale-connection 检测与 client 失效重建。证据:`agent/chat_completion_helpers.py:501` 等2处;规模:bedrock 1573 + vertex 228 + azure_identity 571 行;价值:中。
14. **Anthropic OAuth / Claude Code 身份伪装与凭据刷新** ◇ — 用 Anthropic OAuth/setup-token 访问时,Anthropic 按 user-agent 与 header 路由,缺 Claude Code 指纹会间歇…。证据:`agent/anthropic_adapter.py:891` 等2处;规模:3177 行;价值:中。
15. **插件 LLM 门面 (plugin_llm 信任门控 + relay_llm 托管执行)** — 可信插件需要自己发 LLM 调用(hook 改写错误、gateway 适配翻译等),但绝不能看到原始 OAuth/API key,也不能随意 override provider…。证据:`agent/plugin_llm.py:205` 等2处;规模:plugin_llm 1046 + relay_llm 1239 行;价值:中。

### 2.3 上下文工程(压缩/构建/预算)

该子系统覆盖 Hermes-Agent 上下文生命周期的全部三个环节:构建(system_prompt.py + prompt_builder.py 按 stable/context/volatile 三层缓存分带组装系统提示,并注入 SOUL.md/.hermes.md/AGENTS.md/CLAUDE.md/.cursorrules 等上下文文件,注入前经威胁扫描)、预算(context_breakdown.py 的 /context 分解、prompt_builder 的动态字符上限、compressor 的 threshold/tail budget 推导)、压缩(context_engine.py 定义可插拔 ContextEngine ABC,context_compressor.py 的 6883 行内置引擎实现阈值触发的三段式批量压缩、确定性工具结果剪枝、可选逐轮 micro-compaction,conversation_compression.py 负责 host 侧编排:会话锁、commit fence、进度感知超时、in-place archive_and_compact 落库与系统提示保留)。整个设计被一条核心约束贯穿:prompt cache 不许无谓破坏——系统提示一旦生成就整会话冻结(日期只精确到天)、压缩是唯一允许改写历史的时刻、proactive prune 与 micro-compact 都以"cache 断点是否值得付"作为提交门槛。外围文件处理请求级卫生(message_sanitization、think_scrubber、bounded_response、message_content)与用户侧引用展开(context_references 的 @file/@url),根目录 trajectory_compressor.py 则是同一套"保头保尾压中间"思想在离线训练数据上的复刻。

关键文件(共 16 个,行数实测,全表见附卷):`agent/context_compressor.py`(6883), `agent/conversation_compression.py`(4014), `agent/context_engine.py`(489), `agent/context_breakdown.py`(360), `agent/context_references.py`(605), `agent/prompt_builder.py`(2206) 等

**能力点目录(共 12 条):**

1. **三层缓存分带的系统提示组装** — 系统提示既要装身份/工具指导/工作区快照/技能索引/记忆等大量动态内容,又必须让上游 prompt cache(显式 cache_control 与隐式最长前缀两类后端)每轮命…。证据:`agent/system_prompt.py:554-558` 等3处;规模:system_prompt.py 685 行 + prompt_builder.py 2206 行 + coding_c…;价值:高。
2. **项目上下文文件注入(AGENTS.md/CLAUDE.md 等)** ▲ — agent 需要在启动时拿到项目规范(AGENTS.md/CLAUDE.md/.cursorrules 等),但要解决三个问题:多种约定并存时选哪个、大文件挤爆小上下文模型、以…。证据:`agent/prompt_builder.py:2189-2194` 等3处;规模:prompt_builder.py 中约 300 行(扫描/发现/加载/截断)+ threat_patterns 共享库;价值:中。
3. **渐进式子目录上下文发现** — monorepo 里每个子目录可能有自己的 AGENTS.md。证据:`agent/subdirectory_hints.py:30-34` 等3处;规模:341 行独立模块;价值:中。
4. **可插拔 ContextEngine 抽象与每轮上下文选择钩子** ◇ — 不同的长上下文策略(摘要压缩、DAG、检索式选择)需要可替换,且第三方引擎曾被迫让 should_compress() 恒真来蹭 compress() 当每轮回调,把'选择上下…。证据:`agent/context_engine.py:215-221` 等3处;规模:context_engine.py 489 行 + 插件加载器 286 行;价值:中。
5. **压缩触发决策:双重测量去噪 + 防抖断路器** ▲ — 触发要同时依赖两种度量(请求前的粗估与 provider 返回的真实 prompt_tokens),粗估对 schema 重的请求刻意高估会引发刚压完又压。证据:`agent/context_compressor.py:2629-2634` 等4处;规模:context_compressor.py 中约 600 行(触发/裁决/护栏/持久化)+ conversation_c…;价值:高。
6. **三段式批量压缩管线(头保护衰减/token 预算尾部/边界对齐)**★ — 把超长对话压回预算内,同时不能:切断 tool_call/tool_result 配对(provider 400)、丢掉最新的用户任务与助手回复、让早期轮次在多次压缩中'化石化…。证据:`agent/context_compressor.py:6148-6152` 等5处;规模:compress() 本体约 830 行;价值:高。
7. **摘要消息的角色交替修复与 provider 兼容护栏** ◇ — 压缩摘要作为一条合成消息插回对话后,必须同时满足:Mistral 严格模板的 user/assistant 交替(且模板会跳过 tool 消息)、Anthropic/Bedro…。证据:`agent/context_compressor.py:6661-6668` 等3处;规模:compress() 内约 250 行角色/合并逻辑 + _template_visible_role 等辅助;价值:高。
8. **结构化 handoff 摘要生成(迭代更新/时间锚定/记忆注入/ghost-skill 防护)** ◇ — 摘要不是普通总结:要逐字保住用户最新未完成请求、防止把已完成动作写成待办导致复跑、不能翻译用户语言、不能泄露密钥、不能让'已被剪枝的 skill 指令'在摘要里被改写成模糊描述…。证据:`agent/context_compressor.py:3749-3752` 等4处;规模:_generate_summary 及模板/序列化/回注辅助约 900 行;价值:中。
9. **确定性工具结果剪枝与 proactive prune 的 prompt-cache 滞回** ▲ — 大窗口模型上 50% 阈值的批量压缩很少触发,旧工具输出(终端 dump、文件读取)每轮原样重发。证据:`agent/context_compressor.py:2886-2890` 等4处;规模:约 700 行(_prune_old_tool_results + prune_tool_results_only + …;价值:高。
10. **Micro-compaction 逐轮滚动压缩** — 批量压缩是一次性大爆破:触发时要同步等一个大摘要调用,用户明显感知卡顿。证据:`agent/context_compressor.py:2346-2350` 等3处;规模:约 450 行(游标解析/exchange 切分/微摘要/defrag/splice/DB 同步/遥测);价值:中。
11. **压缩执行基础设施:锁/栅栏/超时/in-place 落库/keep-prompt** ▲ — 压缩是唯一改写持久化会话状态的操作,又依赖一个可能挂死的外部摘要 LLM:并发的兄弟 agent 会双压同一会话造成孤儿分叉。证据:`agent/conversation_compression.py:887-889` 等4处;规模:conversation_compression.py 4014 行的主体;价值:高。
12. **离线训练轨迹压缩器(trajectory_compressor.py)** — 训练数据侧:采出的 agent 轨迹超过训练序列长度预算(如 15250 token),直接截断会丢训练信号。证据:`trajectory_compressor.py:9-13` 等3处;规模:1598 行独立脚本;价值:中。

### 2.4 记忆与学习闭环(memory + self-improvement loop)

这是 README 第 19/26 行 self-improving 宣称背后的子系统,由五条环互扣:(1) 有界双文件记忆 MEMORY.md/USER.md 以冻结快照进系统提示,memory 工具自治增删改并受审批门禁与漂移守护保护;(2) nudge 闭环——按用户回合数(默认 10)与工具迭代数计数,响应送达后 fork 一个工具白名单受限、持久化被切断、前缀缓存字节对齐的后台 review agent,按精调 prompt 决定写记忆或创建/修补 class-level 技能,技能归属由 is_background_review() provenance 区分 agent 自创与用户所有;(3) curator 以空闲+7 天间隔在后台做技能生命周期管理(active→stale→archived 只归档不删,LLM 伞状合并默认关闭,动手前 tar.gz 快照可回滚),数据底座是 .usage.json 遥测 sidecar;(4) 跨会话召回由纯 SQLite 的 FTS5 三索引(词/trigram/CJK)session_search 提供 discovery/scroll/read/browse 四模式,零 LLM;(5) 外部记忆经 MemoryProvider 插件框架接入(8 个 bundled provider,单选),MemoryManager 负责超时隔离、防注入围栏、写镜像与辅助模型 query 改写,Honcho 集成实现多 pass dialectic 用户建模。学习产物通过 /journey 图谱、learning_mutations 编辑删除与 insights 报表对用户可视可控。总体印象:代码比 README 更严谨——README 的 'LLM summarization' 检索宣称已过期,'nudge' 实为对话外后台 fork,而防注入/防数据丢失/成本控制的大量工程在文档中只字未提。

关键文件(共 33 个,行数实测,全表见附卷):`agent/memory_manager.py`(1241), `agent/memory_provider.py`(357), `tools/memory_tool.py`(1240), `agent/background_review.py`(1081), `agent/turn_context.py`(1275), `agent/turn_finalizer.py`(756) 等

**能力点目录(共 12 条):**

1. **有界双文件持久记忆(MEMORY.md/USER.md)+ 冻结快照注入** — 跨会话持久记忆若无限增长会吃掉上下文预算,且中途改动会破坏 LLM 前缀缓存。证据:`tools/memory_tool.py:686-688` 等3处;规模:tools/memory_tool.py 1240 行;价值:高。
2. **记忆/技能 nudge 计数器 → 后台自我改进 review fork** ▲★ — README 宣称 agent 会『nudge 自己持久化知识』:需要一种既不打断用户任务、又不污染主会话上下文/前缀缓存的周期性自我反思机制。证据:`agent/turn_context.py:593-599` 等5处;规模:background_review.py 1081 行 + turn_context/turn_finalizer/co…;价值:高。
3. **技能自创建/自改进提示词体系 + provenance 归属** ▲ — 『从经验创建技能、使用中自改进』需要明确:何时该写技能、写成什么形态、哪些技能不许动、以及自动创建与用户手写技能的所有权边界。证据:`agent/background_review.py:182-186` 等2处;规模:三份 review prompt 约 240 行精调文本 + tools/skill_provenance.py 78 …;价值:高。
4. **Curator:空闲触发的技能生命周期管理(prune + 可选 consolidation + 快照回滚)** — 自创建技能会无限堆积成上百个窄技能,污染系统提示技能索引、浪费 token。证据:`agent/curator.py:70-73` 等6处;规模:curator.py 2019 行 + curator_backup.py 757 行;价值:高。
5. **技能使用遥测 sidecar(.usage.json)——学习闭环的数据底座** ◇ — curator 的 stale/archive 判定、学习图谱、insights 报表都需要每个技能的使用/修改/创建事实,且不能把运营元数据写进用户拥有的 SKILL.md。证据:`tools/skill_usage.py:3-6` 等2处;规模:tools/skill_usage.py 1340 行;价值:中。
6. **MemoryProvider 插件框架 + MemoryManager 编排(8 个 bundled provider)** ▲ — 外部记忆后端(云服务/本地库)质量参差,必须保证:慢/卡死的 provider 不能阻塞用户回合,坏 schema 不能毒化整个工具集,多后端不能互相打架。证据:`agent/memory_manager.py:580-584` 等4处;规模:memory_manager.py 1241 + memory_provider.py 357 + plugins/me…;价值:高。
7. **记忆上下文防注入围栏:fenced block + 流式 Scrubber + 写入威胁扫描** ◇ — 召回的记忆既进模型上下文又源自可被污染的存储:要防 provider 伪造围栏提权、防模型把注入的记忆块回显给用户、防恶意内容借记忆写入常驻系统提示。证据:`agent/memory_manager.py:354-361` 等4处;规模:围栏+scrubber 约 250 行 + threat_patterns 共享库;价值:高。
8. **跨会话召回:FTS5 三索引 session_search(discovery/scroll/read/browse)** ▲★ — 『搜索自己的过去对话』需要在一个 SQLite 里同时支持词级英文、子串、CJK 检索,并把结果以低 token 成本、可继续钻取的形态交给模型。证据:`hermes_state_search.py:1` 等4处;规模:hermes_state_search.py 2230 + session_search_tool.py 1161 行;价值:高。
9. **辅助模型记忆检索查询改写(query_rewrite)** ◇ — 用户原话往往不是好的记忆检索 query(冗长、含指令、指代悬空),直接喂给外部记忆后端召回质量差且有 prompt 注入风险。证据:`plugins/memory/query_rewrite.py:41` 等3处;规模:139 行;价值:中。
10. **Honcho dialectic 用户建模集成(多 pass 推理 + 自适应深度)** — README 宣称『builds a deepening model of who you are across sessions』:需要把对话持续喂给用户建模服务,并在每回合…。证据:`plugins/memory/honcho/__init__.py:1088-1093` 等3处;规模:honcho 插件 __init__ 1550 + session 1447 + client 1113 + cli 1…;价值:高。
11. **记忆写入审批门禁 + 外部漂移/坏读守护** ▲ — 记忆会自动进系统提示,自治写入需要用户可控。证据:`tools/memory_tool.py:941-947` 等3处;规模:memory_tool.py 内约 300 行防护逻辑 + tools/write_approval 共享框架;价值:高。
12. **/learn 显式技能蒸馏 + 学习可视化 journey 图谱** — 自动闭环之外还需要:用户显式指着任意材料说『学会它』。证据:`agent/learn_prompt.py:119-120` 等3处;规模:learn_prompt 150 + learning_graph 328 + learning_mutations 2…;价值:中。

### 2.5 工具基础设施与安全(tool infrastructure & security)

该子系统是 hermes-agent 的『窄腰』:所有工具经 tools/registry.py 的单例注册表自注册(AST 自动发现+磁盘缓存),model_tools.py 在其上提供 get_tool_definitions(带 memo、动态 schema 重建、多后端清洗、tool-search 装配)与 handle_function_call(参数纠偏、middleware/hook、审批拦截、桥接解包)两大入口;toolsets.py 用可组合 toolset 定义各平台工具面,核心集 _HERMES_CORE_TOOLS 被平台 bundle 复用且禁用 bundle 时受保护。安全侧呈多层纵深:approval.py 的 hardline 硬底线→用户 deny→smart LLM guardian→CLI/gateway 人审栈,tirith 外部扫描器与 threat_patterns/skills_guard 内容级扫描,url_safety 的 SSRF 预检+connect-time DNS 钉扎,write_approval 对持久写入的门禁,agent/tool_guardrails 的循环护栏。上下文经济由三层输出防御(per-tool 截断→沙箱持久化→per-turn 预算)与 Tool Search 渐进披露共同保障;execute_code 用 UDS/TCP/文件三态 RPC 实现 README 宣称的编程式工具调用,凭证靠 env 洗净+token 鉴权隔离;mcp_tool.py 则把外部 MCP 服务器当不受信输入全面设防(OSV 预检、描述注入扫描、命名撞车 fail-closed、watchdog 孤儿清理)。整体设计特点是:每条安全规则都先于 yolo 旁路排序、fail-open/closed 语义显式可配、且几乎每个 workaround 都注释了触发它的真实故障编号。

关键文件(共 28 个,行数实测,全表见附卷):`tools/registry.py`(956), `model_tools.py`(1569), `toolsets.py`(1004), `toolset_distributions.py`(358), `tools/schema_sanitizer.py`(591), `tools/tool_output_limits.py`(110) 等

**能力点目录(共 12 条):**

1. **自注册工具注册表:AST 自动发现 + check_fn 可用性 TTL 缓存与瞬断宽限** ▲★ — harness 需要一个不用手工维护清单的工具注册/发现机制,同时工具可用性探测(Docker daemon、playwright、API key)昂贵且会抖动——一次探测超时…。证据:`tools/registry.py:84-86` 等3处;规模:registry.py 956 行 + model_tools.py 1569 行;价值:高。
2. **插件覆盖/注销权限门(基于 handler.__globals__ 归属与调用帧检查)** ▲ — 第三方插件在同一进程内可调用 registry.register/deregister,若无授权检查,插件能静默替换内置工具 handler(供应链攻击面)或先 deregis…。证据:`tools/registry.py:548-549` 等3处;规模:约 180 行(registry.py 472-670);价值:高。
3. **工具 Schema 多后端兼容清洗层(含 property-key 重命名往返)** ◇ — MCP/插件产出的 JSON Schema 在 llama.cpp(GBNF grammar)、Anthropic、OpenAI Codex 端点、xAI、Gemini 等严格…。证据:`tools/schema_sanitizer.py:370-377` 等3处;规模:schema_sanitizer.py 591 行;价值:高。
4. **LLM 工具参数纠偏(coerce_tool_args + 递归 JSON 字符串修复)** ◇ — 开源权重模型(DeepSeek/Qwen/GLM)频繁把数字/布尔发成字符串、把数组字段发成 JSON 编码字符串、把裸标量当数组元素,直接 dispatch 会产生令模型困惑…。证据:`model_tools.py:782-783` 等2处;规模:约 320 行(model_tools.py 730-1045);价值:中。
5. **三层工具输出限长与结果持久化(per-tool cap → 沙箱落盘 → per-turn 预算)** ◇ — 工具输出可能撑爆上下文窗口:单个超大结果、或多个中等结果在同一 turn 内累加超预算。证据:`tools/tool_result_storage.py:172-178` 等3处;规模:tool_result_storage.py 254 行 + budget_config.py 114 行 + tool…;价值:高。
6. **分层命令审批体系(hardline floor / user deny / smart LLM guardian / CLI+gateway 人审)** ▲ — agent 执行 shell 命令需要在『不打扰用户』与『不可逆破坏』之间分层:灾难命令必须无条件拦、危险命令需人审、误报要能被 LLM 自动放行、无人值守(cron/gate…。证据:`tools/approval.py:451-453` 等4处;规模:approval.py 4557 行;价值:高。
7. **Tirith 外部二进制预执行扫描集成(自动安装+签名校验+熔断)** — 纯正则模式匹配抓不住内容级威胁(同形异义 URL、curl|bash、终端注入)。证据:`tools/tirith_security.py:776-778` 等4处;规模:tirith_security.py 872 行;价值:中。
8. **SSRF 双层防护:URL 预检 + httpx connect 时 DNS 钉扎(防 rebinding)** ▲ — web/browser/vision 工具抓取 LLM 给出的 URL 会被用于打内网与云元数据端点窃取实例凭证。证据:`tools/url_safety.py:487-490` 等3处;规模:url_safety.py 874 行;价值:高。
9. **内容级威胁模式库与技能安装信任分级(threat_patterns + skills_guard)** — 提示注入/promptware/C2 载荷会经 web 页面、MCP 响应、memory 写入、skill 安装进入系统提示。证据:`tools/threat_patterns.py:245` 等4处;规模:threat_patterns.py 284 行 + skills_guard.py 1161 行;价值:高。
10. **Tool Search 渐进式工具披露(3 桥接工具 + BM25 + 分层 listing + 会话范围防越权)** — 大量 MCP/插件工具的 schema 会吃掉数万 token 上下文(如 Cloudflare ~3300 工具仅名字就 ~32K token),但直接砍掉又让模型不知道有哪…。证据:`model_tools.py:1246-1248` 等3处;规模:tool_search.py 1078 行 + model_tools.py 桥接段约 110 行;价值:高。
11. **execute_code 编程式工具调用:UDS/TCP/文件三态 RPC + token 鉴权 + 环境洗净**★ — 多步工具链每步都要一次推理往返且中间结果占满上下文。证据:`tools/code_execution_tool.py:703-708` 等4处;规模:code_execution_tool.py 2087 行;价值:高。
12. **MCP 客户端侧安全与动态注册(命名规范、注入扫描、OSV 预检、watchdog、schema 缓存)** ▲ — 外部 MCP 服务器是最大的不受信输入面:恶意 npm 包、工具描述藏注入、name 冲突劫持内置工具、stdio 子进程泄漏成孤儿、慢服务器拖死启动。证据:`tools/mcp_tool.py:5524-5526` 等5处;规模:mcp_tool.py 7230 行(全仓最大工具文件)+ mcp_schema_cache/watchdog/osv_…;价值:高。

### 2.6 终端与执行环境(terminal backends、后台进程、serverless 持久化、浏览器/桌面自动化)

该子系统是 Hermes 的『手』:tools/terminal_tool.py 按 TERMINAL_ENV 在 7 种后端(local/docker/ssh/singularity/modal/daytona/vercel_sandbox,另有经 Nous 网关的 managed Modal 第 8 个环境类)上执行 shell 命令,全部后端收敛到 tools/environments/base.py 的 BaseEnvironment 抽象——spawn-per-call 进程 + export -p/declare -f 会话快照重放 + stdout 内嵌 CWD 标记,从而在只有一次性 exec 原语的环境上重建有状态 shell。环境按 task_id 缓存复用(双检锁),空闲 5 分钟回收但被活跃后台进程保活;Docker 走标签化跨进程容器复用 + 启动期 orphan reaper,Modal/Daytona/Vercel/Singularity 分别用文件系统快照、stop-resume、平台快照、overlay 目录实现 README 宣称的 serverless 休眠,SSH/Modal/Daytona 另配事务性 FileSyncManager 双向同步凭据/skills/缓存。tools/process_registry.py 提供跨后端一致的后台进程语义(本地 pipe/PTY,沙箱内 nohup+log/pid/exit 三文件轮询),叠加 notify_on_complete/watch_patterns 通知、strike 限流与全局熔断、checkpoint 崩溃恢复和 PID-reuse 防误杀。安全面贯穿始终:子进程 secret blocklist 与 skill passthrough 防绕过(GHSA-rhgp-j443-p4rf)、快照会话变量排除(#71296 注入修复)、Docker cap-drop 硬化与 iron-proxy egress 强制。浏览器/桌面自动化独立成栈:browser_tool 多引擎多后端矩阵、CDPSupervisor 对话框桥与 frame 观察、browser_cdp 逃生舱、computer_use 经 cua-driver MCP 驱动三平台桌面并按模型能力路由截图。

关键文件(共 36 个,行数实测,全表见附卷):`tools/terminal_tool.py`(3432), `tools/environments/base.py`(1370), `tools/environments/local.py`(1687), `tools/environments/docker.py`(2029), `tools/environments/modal.py`(478), `tools/environments/managed_modal.py`(282) 等

**能力点目录(共 12 条):**

1. **统一环境抽象:spawn-per-call + 会话快照重放** ▲★ — 7 种执行后端(local/docker/ssh/singularity/modal/daytona/vercel_sandbox)底层能力差异巨大(有的只有阻塞 SDK ex…。证据:`tools/environments/base.py:706` 等3处;规模:base.py 1370 行;价值:高。
2. **非阻塞输出 drain + 有界头尾捕获 + 溢出 spill 文件** ◇ ▲ — 三个真实故障:(1) 用户命令 background 出的孙进程持有 stdout 管道写端,阻塞式 readline 会让工具挂死到孙进程退出(#8340)。证据:`tools/environments/base.py:1056` 等4处;规模:约 500 行核心循环 + interrupt.py 113 行;价值:高。
3. **后台进程注册表:本地 PTY/pipe 与沙箱内 nohup 双路径** — terminal(background=true) 要在所有后端上给出一致的 spawn/poll/wait/kill/stdin 语义。证据:`tools/process_registry.py:879` 等3处;规模:process_registry.py 2529 行;价值:高。
4. **进程 checkpoint 崩溃恢复 + PID-reuse 防误杀** ◇ — 网关重启/崩溃后,之前 spawn 的后台进程仍在跑。证据:`tools/process_registry.py:2134` 等2处;规模:约 300 行(checkpoint 写入/恢复/校验);价值:中。
5. **后台进程通知:notify_on_complete / watch_patterns + 双层限流熔断 + 会话路由** ▲ — agent 不该轮询等待长任务,但『输出匹配即通知』在循环打日志的任务上会瞬间刷爆用户消息渠道。证据:`tools/process_registry.py:70` 等3处;规模:约 600 行(watch/drain/format);价值:高。
6. **Serverless 持久化:Modal 文件系统快照 / Daytona stop-resume / Vercel 快照 / Singularity overlay + 远端文件同步** — 云沙箱按秒计费,session 间保持沙箱常驻成本高。证据:`tools/environments/modal.py:453` 等4处;规模:modal.py 478 + daytona.py 270 + vercel_sandbox.py 662 + sing…;价值:高。
7. **Docker 硬化沙箱 + 标签化跨进程容器复用 + 孤儿 reaper** ▲ — Docker 后端既要是安全边界(agent 可 pip/npm/apt 但不能提权逃逸),又要兑现『一个长命容器跨 session 共享』:进程内复用、Hermes 进程重启…。证据:`tools/environments/docker.py:339` 等3处;规模:docker.py 2029 行;价值:高。
8. **iron-proxy egress 强制接入:MITM CA 注入 + per-provider 代理 token** — 沙箱里 agent 可以任意发起网络请求。证据:`tools/environments/docker.py:498` 等2处;规模:约 250 行(docker.py 393-634)+ agent/proxy_sources 依赖;价值:中。
9. **子进程 secret 卫生:blocklist + 动态 secret 判定 + skill passthrough 防绕过 + 快照会话变量排除** — 本地后端的子进程默认继承网关的 os.environ,里面有全部推理 key、消息平台 token、辅助模型 key。证据:`tools/environments/local.py:474` 等3处;规模:local.py 相关约 500 行 + env_passthrough.py 223 行 + base.py 快照排除;价值:高。
10. **shell 语义修补层:sudo -S 密码管道 + `A && B &` 子壳重写 + 前台命令引导** ◇ — 模型写的 shell 有系统性坑:bare sudo 无 TTY 直接失败。证据:`tools/terminal_tool.py:1049` 等2处;规模:约 600 行(sudo 变换 + 重写器 + 各类 guard);价值:中。
11. **浏览器自动化架构:CDP supervisor + 对话框桥 + raw CDP 逃生舱 + Camofox/云后端矩阵** ▲ — 浏览器自动化有多后端(本地 agent-browser Chromium、Browserbase/Browser Use 云、Camofox 隐身 Firefox、外接 CDP…。证据:`tools/browser_supervisor.py:95` 等5处;规模:browser_tool.py 5098 + browser_supervisor.py 1518 + browser_…;价值:高。
12. **computer_use 跨平台桌面控制 + 截图视觉路由** — 任意 tool-calling 模型(不限 Anthropic computer-use 原生格式)都要能驱动 macOS/Windows/Linux 桌面。证据:`tools/computer_use/vision_routing.py:183` 等3处;规模:tools/computer_use/ 共 7122 行;价值:中。

### 2.7 会话状态与持久化(SessionDB / checkpoint / trajectory / replay 清理)

该子系统是 Hermes Agent 的持久层核心:单个 SQLite 文件 ~/.hermes/state.db 承载全部会话元数据、完整消息转写、按模型/任务维度的用量记账、gateway 路由索引、跨进程压缩锁与异步委托簿记,由 SessionDB(hermes_state.py, 9691 行)加三个 mixin(schema/搜索/可移植)实现。它在 harness 意义上做了五件大事:(1) 多进程安全的写引擎——BEGIN IMMEDIATE + 抖动重试 + 按业务重要性分级的锁等待预算,叠加 WAL 回退、macOS F_FULLFSYNC、零化库隔离、多级 schema 自修复等事故驱动的耐久性防御;(2) 会话可恢复性——active/compacted 双标志软删除同时支撑 /undo(rewind)与非破坏性压缩归档,resolve_resume_session_id 沿压缩世系走到真正持有最新消息的 tip,replay_cleanup 在回放前剥离崩溃留下的悬空 tool 调用并把副作用调用标记为 UNKNOWN、给危险确认加 60s TTL;(3) 跨平台连续性——session_key/对等体元组落库 + gateway_routing 表让路由索引可丢可重建,handoff 状态机用 sessions 行上的条件 UPDATE 实现 CLI→消息平台的原子会话交接;(4) 文件系统安全网——CheckpointManager 用共享 bare git store 做 LLM 不可见的每回合快照与回滚,file_state/tool_result_storage 在进程内提供跨子代理写冲突守卫与大结果落盘;(5) 研究管线——save_trajectory 把运行轨迹以 ShareGPT JSONL 双轨(成功/失败)落盘供训练,与 state.db 分离。另有 token 记账后台写线程(coalescing 队列 + atexit 排空)、AsyncSessionDB to_thread 包装、prune/vacuum/auto-archive 存储治理与 Telegram topic 绑定迁移等配套设施。官方 session-storage.md 覆盖了大约一半能力,且版本号、重试模型、WAL 声明均已滞后于代码。

关键文件(共 15 个,行数实测,全表见附卷):`hermes_state.py`(9691), `hermes_state_common.py`(614), `hermes_state_schema.py`(1079), `hermes_state_portability.py`(714), `hermes_state_search.py`(2230), `tools/checkpoint_manager.py`(1953) 等

**能力点目录(共 12 条):**

1. **单文件 SQLite 会话库 + 声明式 schema 调和** ▲ — harness 需要在 CLI/gateway/TUI/cron 多进程共享一份持久会话库,且 schema 随版本快速演进。证据:`hermes_state_schema.py:594` 等2处;规模:SCHEMA_SQL+DDL 约 420 行(hermes_state_common.py);价值:高。
2. **SQLite 耐久性防御工事(WAL 回退 / macOS F_FULLFSYNC / 零化库隔离 / 多级自修复)** ◇ ▲ — state.db 是 harness 的唯一事实源,跑在 NFS/SMB/virtiofs、macOS launchd 关机、带 WAL-reset bug 的 SQLite …。证据:`hermes_state.py:546` 等3处;规模:hermes_state.py 前 1900 行几乎全是这类防御(约 1400 行);价值:高。
3. **分级耐心预算的写事务引擎(BEGIN IMMEDIATE + 抖动重试)** ◇ ▲ — gateway + CLI + worktree 子代理多进程同写一个 state.db,SQLite 内建确定性退避会造成 convoy 效应。证据:`hermes_state.py:2610` 等2处;规模:_execute_write 及重试/合并辅助约 250 行;价值:高。
4. **软删除双标志消息模型:rewind/undo 与非破坏性压缩共用 active/compacted** ◇ ▲ — undo 和上下文压缩都要“从模型视野里拿走消息”,但直接 DELETE 会毁掉审计线索、训练数据和可搜索历史,还会把 FTS 索引拖进 delete 风暴。证据:`hermes_state.py:7670` 等2处;规模:rewind/restore 约 110 行 + archive_and_compact/has_archived_me…;价值:高。
5. **压缩世系 + resume 重定向 + 跨进程压缩租约锁** ◇ ▲ — 自动上下文压缩会结束当前会话并 fork 继续子会话(parent_session_id 链),多进程下 resume 旧 id 会读到压缩前转写、丢“最新回复”。证据:`hermes_state.py:7213` 等3处;规模:锁 + 冷却 + 世系 + resume 重定向合计约 900 行(hermes_state.py:3445-3660、…;价值:高。
6. **跨平台会话交接(/handoff)持久状态机** — 用户在 CLI 里跑到一半想转到 Telegram/Discord 继续同一对话。证据:`hermes_state.py:9592` 等2处;规模:SessionDB 侧约 90 行(hermes_state.py:9585-9674)+ CLI/gateway 消费…;价值:中。
7. **网关路由持久化与对等体会话找回(session_key / gateway_routing)** ◇ ▲ — gateway 原以 sessions.json 做『平台对等体 → 会话』路由索引,进程级重启 bug 会把它整个丢掉,导致 Telegram 群/Discord 频道的用户…。证据:`hermes_state.py:3405` 等2处;规模:hermes_state.py:3103-3443 约 340 行;价值:中。
8. **回放前转写消毒:中断尾剥离、副作用 UNKNOWN 化、危险确认过期** ◇ — 进程被 kill/重启在 tool 循环中间死掉时,持久转写以悬空 assistant(tool_calls) 或中断 tool 结果结尾。证据:`agent/replay_cleanup.py:168` 等2处;规模:agent/replay_cleanup.py 323 行纯函数;价值:高。
9. **共享影子 git 仓库的文件系统检查点(CheckpointManager)** ▲ — agent 的 write_file/patch/破坏性 terminal 命令可能毁掉用户文件,需要 LLM 不可见的自动快照与回滚,且不能污染用户项目目录、不能因十几个 w…。证据:`tools/checkpoint_manager.py:1100` 等2处;规模:tools/checkpoint_manager.py 1953 行;价值:高。
10. **ShareGPT 轨迹落盘(research/训练数据管线入口)** — Nous 用 Hermes Agent 生成工具调用训练数据,需要把每次 agent 运行的完整对话以训练可用格式(ShareGPT)持久化,并区分成功/失败样本。证据:`agent/trajectory.py:41` 等2处;规模:agent/trajectory.py 仅 56 行;价值:中。
11. **会话导出/导入可移植层(含压缩世系合并与运行态消毒)** ◇ ▲ — 用户要在机器间搬迁会话、备份历史,但直接搬行会带来三类灾难:外键指向不存在的父会话、导入陈旧的 handoff/活动心跳等『活运行态』被看门狗当真、压缩劈开的多段会话在新机上支…。证据:`hermes_state_portability.py:692` 等2处;规模:hermes_state_portability.py 714 行;价值:中。
12. **工具结果三层落盘 + 跨子代理文件新鲜度守卫** ◇ — 巨型工具输出(构建日志、文件 dump)会撑爆上下文窗口,粗暴截断又丢信息。证据:`tools/tool_result_storage.py:114` 等2处;规模:tool_result_storage.py 254 行 + file_state.py 332 行;价值:高。

### 2.8 CLI 前端(cli.py + hermes_cli/)

Hermes 的 CLI 前端由 18555 行的 cli.py(HermesCLI:prompt_toolkit 全屏 REPL/TUI,含流式渲染、状态栏、审批/澄清/秘密输入三类模态、语音+唤醒词、pet 吉祥物、worktree 管理)与 hermes_cli/ 下 262 个文件的命令行工具箱组成,main.py 的 argparse 全树挂了几十个子命令(setup/model/gateway/dashboard/update/doctor/kanban/curator/profile/plugins/skills/...)。架构核心是三个「单一事实源」:commands.py 的 COMMAND_REGISTRY 同时驱动 CLI 分发、gateway busy 策略、Telegram/Slack 菜单和 tab 补全五个消费方(slash_exec.py 再为信息类命令提供表面无关执行器);config.py 的分层加载器族(load_config/load_config_readonly/read_raw_config/read_user_config_raw)带 last-known-good 回退与 managed-scope 管理员覆盖;skin_engine.py 的 YAML 皮肤一份定义同步 CLI/TUI/桌面三表面。此外还有 import 前预解析 -p 的多 profile 实例机制、插件系统向 argparse 与会话斜杠双通道注入命令、_startup_fast/meta_path 惰性补丁等启动延迟工程、带双重验证与自动回滚的自更新管线,以及 17k 行 FastAPI dashboard(把同一 `hermes --tui` 二进制经 PTY-over-WebSocket 嵌进浏览器并支持断线重连)。文档覆盖总体良好(AGENTS.md/website 对注册表、皮肤、插件均有专章),但 slash_exec 执行器层、配置 LKG 回退、启动优化和更新回滚验证均为代码独有;发现两处文档与代码不符(前缀歧义解析规则、PTY 桥的 Windows 支持)。

关键文件(共 30 个,行数实测,全表见附卷):`cli.py`(18555), `hermes_cli/main.py`(12599), `hermes_cli/commands.py`(2260), `hermes_cli/slash_exec.py`(272), `hermes_cli/config.py`(5434), `hermes_cli/config_defaults.py`(4313) 等

**能力点目录(共 11 条):**

1. **中央命令注册表 COMMAND_REGISTRY(五方复用 + busy_policy 中台)** — 同一套斜杠命令要在 CLI REPL、gateway 消息平台、Telegram 菜单、Slack manifest、tab 补全五个表面保持一致。证据:`hermes_cli/commands.py:3` 等5处;规模:commands.py 2260 行 + gateway/run.py 中 Guard-1/Guard-2 消费点;价值:高。
2. **表面无关命令执行器 slash_exec.EXECUTORS(registry-owned execution)** ◇ — 信息类命令(/version、/profile、/help、/bundles、/egress)的核心文本在 CLI、gateway、TUI 三个表面各写一份会漂移。证据:`hermes_cli/slash_exec.py:3` 等2处;规模:272 行;价值:高。
3. **配置加载器族(load_config / load_config_readonly / read_raw_config / read_user_config_raw)+ last-known-good + managed overlay** ◇ — config.yaml 同时被热路径读取(每 API turn)、写回路径修改、诊断路径检查:一个加载器无法同时满足性能(deepcopy ~135us/次)、写回正确性(不能…。证据:`hermes_cli/config.py:3357` 等4处;规模:config.py 5434 行 + config_defaults.py 4313 行 + config_migrat…;价值:高。
4. **Profile 多实例:import 前 -p 预解析 + shell wrapper + 独立 HERMES_HOME + 档案导入导出** — 一台机器上要跑多个互相隔离的 agent 身份(不同模型/技能/gateway/凭据),且 HERMES_HOME 决定所有模块的路径常量,必须在任何 hermes 模块 im…。证据:`hermes_cli/main.py:517` 等3处;规模:profiles.py 2262 行 + profile_distribution.py 782 行 + main.py…;价值:中。
5. **皮肤引擎(YAML 数据驱动、三表面同步)+ 终端明暗自动检测(OSC 11)** — CLI/TUI/桌面 GUI 三个表面的主题若各自硬编码颜色会割裂。证据:`hermes_cli/skin_engine.py:8` 等3处;规模:skin_engine.py 1068 行 + cli.py 内 ~250 行明暗检测/重映射;价值:中。
6. **通用插件系统的双通道命令注入(hermes 子命令 + 会话斜杠命令)** — 第三方插件需要把自己的命令挂进 harness 的两个入口:终端级 `hermes <cmd>`(argparse)与会话级 `/<cmd>`(CLI+gateway 聊天中)…。证据:`hermes_cli/plugins.py:584` 等3处;规模:plugins.py 2510 行 + plugins_cmd.py 2082 行 + main.py 注入段;价值:高。
7. **启动延迟工程:stdlib-only fast path + sys.meta_path 延迟补丁 + 惰性 agent 导入** ◇ — `hermes --version` / 裸交互启动不应支付重 import(openai 类型树 ~166ms/30MB、yaml、argparse 全树、插件)。证据:`hermes_cli/_startup_fast.py:3` 等3处;规模:_startup_fast.py 222 行 + cli.py/main.py 分散 ~500 行;价值:高。
8. **模块化 setup 向导(section 独立可跑 + quick/blank-slate/portal 一键流 + 非交互守卫)** — 首次安装要配模型、终端后端、消息平台、工具密钥等大量维度。证据:`hermes_cli/setup.py:2842` 等3处;规模:setup.py 3645 行 + model_setup_flows.py 3151 行 + tools_config…;价值:中。
9. **自更新管线:语法+跨模块导入双重验证与自动回滚** ◇ — `hermes update`(git pull / zip 替换)可能落下带冲突标记的文件或半新半旧的树,导致 CLI 自身无法启动(自更新把自己砖了),用户失去修复工具。证据:`hermes_cli/update_cmd.py:123` 等2处;规模:update_cmd.py 5540 行;价值:中。
10. **Dashboard Web 服务器 + PTY-over-WebSocket 终端桥(可重连 keep-alive 会话)** ▲ — 浏览器/桌面壳里要嵌入与终端完全一致的 agent 交互(TUI 的 slash 弹窗、审批、皮肤都不重写一遍),且刷新页面不能杀掉正在跑的 agent 进程。证据:`hermes_cli/web_server.py:14393` 等3处;规模:web_server.py 17732 行 + pty_bridge.py 293 + pty_session.py 1…;价值:中。
11. **REPL 忙时输入策略(interrupt/queue/steer)与斜杠前缀展开** ▲ — agent 正在跑时用户按 Enter 该发生什么(打断?排队?中途注入?)需要可配置。证据:`cli.py:4285` 等3处;规模:cli.py 内分散 ~400 行(process_command 尾部 + 输入回调);价值:中。

### 2.9 消息网关(gateway/ + gateway/platforms/ + plugins/platforms/,多平台单进程 messaging gateway)

gateway/ 是 hermes-agent 的常驻消息网关:单个 asyncio 进程同时连接 30+ 个消息平台(gateway/platforms/ 内置 9 个直连适配器 + relay 通用连接器 + plugins/platforms/ 22 个插件适配器,经 platform_registry 惰性加载),把各平台事件归一为 MessageEvent,按 build_session_key 确定性路由到会话并驱动 AIAgent 回合。围绕这条主链,它实现了消息型 harness 的一整套生存性机制:双层 busy 守卫(adapter _active_sessions/_pending_messages + runner busy_input_mode 的 interrupt/steer/redirect/queue 谱系,含子代理/压缩自动降级与 /approve、clarify 旁路)、按 resolved session_id 的回合租约防转写交错、GatewayStreamConsumer 把同步 token 流限速编辑/Telegram draft 流式投到平台、delivery ledger 用 state.db 四态检查点保证最终回复 crash 后诚实 at-least-once 重投、DM 配对(盐化哈希码 + owner CLI 批准)与多层 default-deny 授权联合、scale-to-zero 闲置休眠、指数退避重连 + 重启环路断路器 + resume-pending 恢复、关机 flush/取证/看门狗,以及 multiplex_profiles 单进程多租户(per-profile HERMES_HOME/secret scope/凭据冲突仲裁)与 profile_routes 按频道路由人格。文档(website/docs/developer-guide/gateway-internals.md)对主架构有覆盖,但守卫语义、配对方向、会话键示例均已过时,turn lease、delivery ledger 恢复细节、scale-to-zero 网关层、关机保全体系基本只存在于代码与源内注释。

关键文件(共 38 个,行数实测,全表见附卷):`gateway/run.py`(27146), `gateway/platforms/base.py`(6861), `gateway/session.py`(3490), `gateway/config.py`(2688), `gateway/stream_consumer.py`(2410), `gateway/slash_commands.py`(5693) 等

**能力点目录(共 13 条):**

1. **单进程多平台适配器总线(~30+ 平台,注册表 + 惰性加载 + 动态枚举)** ▲ — 一个 agent 需要同时驻留在 Telegram/Discord/Slack/WhatsApp/Signal/飞书/企微/QQ/iMessage 等几十个消息平台上,但不能为…。证据:`gateway/run.py:11051-11054` 等3处;规模:gateway/run.py 27146 行 + base.py 6861 行 + platform_registry.…;价值:高。
2. **确定性会话键与多档案命名空间路由** ▲ — 同一条消息必须稳定地映射到唯一会话(DM 按人隔离、群按 chat/人隔离、线程共享),否则会出现跨用户历史串线。证据:`gateway/session.py:1053-1055` 等3处;规模:session.py 3490 行(键构造约 120 行;价值:高。
3. **双重消息守卫 + busy 策略(steer/redirect/queue/interrupt 与自动降级)** ▲ — agent 跑长任务时用户还在继续发消息:既不能丢、不能乱序、不能把控制命令(/stop、/approve)当聊天文本吞掉,也不能让一句闲聊把跑了几分钟的子代理任务全部打断。证据:`gateway/platforms/base.py:5736-5741` 等3处;规模:base.py handle_message + busy 分支约 1200 行;价值:高。
4. **流式输出桥 GatewayStreamConsumer(sync delta → 限速编辑/原生 draft)** — LLM 的 token 流来自 agent 工作线程(同步回调),而消息平台没有 token 流概念,只能反复 editMessageText 或用 Telegram send…。证据:`gateway/stream_consumer.py:786-789` 等3处;规模:stream_consumer.py 2410 行 + stream_dispatch.py 132 + stream_…;价值:高。
5. **投递义务台账(delivery ledger:crash 后最终回复不丢、诚实 at-least-once)**★ — 回合已烧完 token、最终回复只存在于 Python 局部变量里,gateway 在 finalize 与平台 ACK 之间崩溃/重启就会无痕丢失这条回复(#58818 等)。证据:`gateway/delivery_ledger.py:68-71` 等3处;规模:delivery_ledger.py 374 行 + base.py 记账段约 70 行 + run.py 重投约 10…;价值:高。
6. **回合租约 SessionTurnLeaseRegistry(按 resolved session_id 串行化转写)** ◇ — busy 守卫都按路由键(routing key)加锁,但 /resume、Telegram topic tip-walk、异步委托 pinning 会让多个路由键映射到同一个…。证据:`gateway/run.py:16584-16589` 等3处;规模:turn_lease.py 302 行 + run.py 挂接/释放/rebind 约 120 行;价值:高。
7. **DM 配对安全(盐化哈希配对码 + 限速/锁定 + allowlist 镜像)** ▲ — 静态 user-id allowlist 运维成本高,但开放 DM 又会被陌生人白嫖。证据:`gateway/pairing.py:641-645` 等3处;规模:pairing.py 905 行 + run.py 接入约 70 行;价值:中。
8. **多层授权联合与 upstream 委托(含 busy 路径同等鉴权)** ▲ — 几十个平台各有身份/allowlist 形态(env、config.yaml、群级、bot 消息、无 user_id 的频道广播、relay 上游已鉴权流量),必须统一成一个 …。证据:`gateway/authz_mixin.py:435-439` 等3处;规模:authz_mixin.py 888 行 + pairing 联动;价值:高。
9. **Scale-to-zero 闲置休眠(relay dormant + 平台级 suspend)** ◇ ▲ — 托管在 Fly 这类按运行计费的平台时,空闲 gateway 也占一台常驻机器。证据:`gateway/scale_to_zero.py:104` 等3处;规模:scale_to_zero.py 124 行(纯函数)+ run.py watcher/前提检查约 250 行;价值:中。
10. **断线重连与重启体系(指数退避 + 重启环路断路器 + resume-pending)** ◇ — 平台 socket 掉线、进程被 SIGTERM、agent 自己把 gateway 重启进死循环——这三类中断都要自愈,且重启后被打断的会话要接着跑而不是丢失。证据:`gateway/run.py:12479-12481` 等3处;规模:reconnect watcher ~210 行 + restart 路径(run.py 9698-10330 一带)~…;价值:高。
11. **关机数据保全(pending flush + 转写抢救 + 关机取证/看门狗)** ◇ — 关机瞬间,内存里的 _pending_messages 和 agent 未落库的 _session_messages 是仅存副本,FTS5 损坏或 clear() 会造成永久用…。证据:`gateway/shutdown_flush.py:10-12` 等3处;规模:shutdown_flush.py 321 + shutdown_forensics.py 462 + shutdown…;价值:中。
12. **多 profile 复用 multiplex + profile 路由(单进程多租户)** — 一台机器上跑多个人格/配置(不同模型、技能、记忆、凭据)的 agent,如果各起一个 gateway 会浪费资源且 bot token 冲突。证据:`gateway/run.py:13195-13196` 等3处;规模:run.py multiplex 段约 450 行 + profile_routing.py 166 + authz/p…;价值:高。
13. **后台完成事件唤醒(wake:push 注入 vs API self-POST 双策略)** ◇ — 后台任务(delegate_task background、bg terminal)完成时要把结果注入原会话继续对话。证据:`gateway/wake.py:80-86` 等3处;规模:wake.py 184 行 + run.py 各 watcher(_async_delegation_watcher/_…;价值:中。

### 2.10 委派与多智能体(delegation & multi-agent)

该子系统提供 Hermes 的四条多智能体路径:(1) delegate_task 同进程子代理——在主线程构建隔离的子 AIAgent(全新对话、独立终端会话/task_id、工具集交集+黑名单、skip_context_files/skip_memory),leaf/orchestrator 角色控制再委派能力并受 max_spawn_depth(默认 1=扁平)与全局 kill switch 约束;顶层模型调用一律后台执行,批量作为单个异步单元 join 后经持久化完成队列(state.db + claim/ack 投递协议)以全新回合回注对话,配套双层无进度停滞检测(同步心跳 staleness + 异步 stale monitor)取代墙钟超时、摘要按父上下文余量预算截断并溢写落盘、可 tail 的强制脱敏实时转录。(2) Kanban 看板——以 SQLite(kanban.db)为唯一协调内核的跨进程多 worker 队列:gateway 内嵌 dispatcher 每 tick 在板级单写锁下做 TTL/心跳/PID 三重回收、依赖促升与 CAS claim,再以 env 注入方式 spawn 全进程 worker(hermes -p <profile> chat -q),worker 经 kanban_* 工具收尾,harness 层有 stop-nudge、goal judge 完成门、自动心跳与运行中评论 steer 注入;delegation_context 的 ContextVar 标记防止同进程子代理/cron 冒充 dispatcher 属主。(3) research 场景批量轨迹生成——batch_runner(多进程+checkpoint+工具集概率采样+每样本容器镜像)与 mini_swe_runner(单 terminal 工具+哨兵完成)。(4) MoA——虚拟 provider 形式的 mixture-of-agents:参考模型并行 fan-out 后由聚合器作为 acting model 走正常代理循环,advisory view 把工具转录扁平化为纯文本以兼容严格 provider。另有面向插件的 SubagentLifecycleService 公共生命周期 API。AGENTS.md 的委派一节明显滞后于代码(background 语义、toolsets 参数、max_spawn_depth 默认值均与实现不符),而 website 用户文档基本准确。

关键文件(共 24 个,行数实测,全表见附卷):`tools/delegate_tool.py`(3931), `tools/async_delegation.py`(1515), `agent/subagent_lifecycle.py`(540), `agent/delegation_context.py`(161), `tools/delegation_live_log.py`(424), `agent/kanban_stop.py`(108) 等

**能力点目录(共 12 条):**

1. **同进程子代理构建与隔离(delegate_task)** ▲★ — 父代理需要把重推理/高噪音子任务外包出去,同时防止子任务的中间工具调用和推理污染父上下文,并防止子代理获得父代理没有的能力或触发用户交互/共享状态副作用。证据:`tools/delegate_tool.py:48` 等4处;规模:delegate_tool.py 共 3931 行;价值:高。
2. **leaf/orchestrator 角色与 spawn 深度治理** ▲ — 嵌套委派会指数级放大 API 开销并可能形成失控代理树,需要按角色精确授予再委派能力,并有全局熔断与深度上限。证据:`tools/delegate_tool.py:127` 等4处;规模:角色/深度相关代码(_normalize_role、_get_max_spawn_depth、_get_orchestr…;价值:高。
3. **后台委派:持久化完成队列与 claim/ack 投递协议** ▲ — 后台子代理的结果必须在父代理空闲时以全新回合注入对话(不能拼接在 tool result 与 assistant 消息之间破坏角色交替和 prompt cache),且进程重启…。证据:`tools/async_delegation.py:9` 等5处;规模:async_delegation.py 1515 行 + delegate_tool.py 后台分发段约 250 行;价值:高。
4. **双层无进度停滞检测(取代墙钟超时)** — 对子代理设统一墙钟超时会误杀合法的长任务(深度审查、慢推理模型),但完全不设防又会让卡死的子代理永远占住父回合或让后台委派永远显示 dispatched。证据:`tools/delegate_tool.py:732` 等4处;规模:同步心跳 + 异步 stale monitor 合计约 450 行;价值:高。
5. **子代理摘要上下文预算与溢写分页** ◇ — 批量 fan-out 的 N 份完整摘要同时进入父上下文会撑爆窗口,触发压缩/429 死亡螺旋(issue #9126),但直接截断又会丢失子代理产出。证据:`tools/delegate_tool.py:723` 等3处;规模:约 200 行(_spill/_trim/_parent_summary_char_budget/_apply_summ…;价值:高。
6. **委派实时转录(live transcripts)与强制脱敏** — 父代理/用户在子代理运行期间只能盲等合并摘要,无法观察子代理在做什么。证据:`tools/delegation_live_log.py:3` 等3处;规模:delegation_live_log.py 424 行;价值:中。
7. **ContextVar 委派语境隔离与 Kanban 身份防伪** ◇ — delegate_task 子代理与父代理同进程,若父进程本身是 Kanban dispatcher 派生的 worker(env 里有 HERMES_KANBAN_*),子代…。证据:`agent/delegation_context.py:104` 等3处;规模:delegation_context.py 161 行 + kanban_tools.py 门控约 100 行;价值:高。
8. **Kanban dispatcher:原子 claim、回收与并发治理** — 多个全进程 worker + 可能并存的多个 dispatcher 共享一个 SQLite 看板,需要防止双 dispatcher 竞争、防止任务被双领取、检测崩溃/超时/失联…。证据:`hermes_cli/kanban_db.py:4289` 等4处;规模:kanban_db.py 10275 行(claim/回收/dispatch 核心约 2000 行)+ hermes_c…;价值:高。
9. **Kanban worker 生命周期协议(env 注入 spawn、stop-nudge、goal judge 门)** — dispatcher 派生的 worker 是普通 CLI 代理进程,必须让它准确知道自己的任务身份/看板/工作区,必须以 kanban_complete/kanban_blo…。证据:`hermes_cli/kanban_db.py:9019` 等4处;规模:_default_spawn 约 210 行 + kanban_stop.py 108 行 + kanban_tools…;价值:高。
10. **运行中 worker 双向通道:自动心跳 + 评论 steer 注入** ◇ ▲ — 长时任务 worker 若忘记调 kanban_heartbeat 会被 dispatcher 误回收。证据:`tools/kanban_tools.py:312` 等3处;规模:两个函数合计约 140 行;价值:中。
11. **批量轨迹生成(batch_runner + toolset 概率采样 + mini_swe_runner)** — research 场景需要对成千上万 prompt 并行跑完整代理会话产出训练轨迹,要求断点续跑、工具集多样性采样、每样本独立沙箱镜像,以及一个极简单工具的 SWE 基线 ru…。证据:`batch_runner.py:920` 等5处;规模:batch_runner.py 1330 行 + mini_swe_runner.py 732 行 + toolset_…;价值:中。
12. **MoA(Mixture of Agents)循环:并行参考模型 + 聚合器代行** ▲ — 困难任务需要多模型视角,但仍要保留正常代理循环(工具调用、迭代、中断、会话持久化)。证据:`agent/moa_loop.py:789` 等5处;规模:moa_loop.py 2384 行 + moa_trace.py 167 行;价值:高。

### 2.11 定时任务与后台自治(cron/、agent/background_review.py、agent/outbound_webhooks.py、gateway/wake.py、gateway/kanban_watchers.py、agent/session_activity.py、tools/cronjob_tools.py)

该子系统让 Hermes 在无人值守下自主运转:cron/ 提供一个建立在 jobs.json + flock 之上的完整调度器——60s tick 循环(跨进程文件锁、并行/串行双池)、四种 schedule 语法解析与时区迁移修复、半周期 clamp 的 catchup/grace 窗口(过期 fast-forward 但仍补跑一次)、以及由 advance-first、claim_dispatch 预扣、run_claim 租约心跳和 SQLite 执行台账组成的跨进程 at-most-once 语义栈。每次运行在独立的 cron_{job_id}_{ts} 会话中以 platform="cron"、skip_memory=True 构造 agent,受 600s 不活动看门狗(request_hard_interrupt)与双层注入扫描、gateway 生命周期防护、凭据外泄与模型漂移 fail-closed 保护;prompt 组装管道支持 script 预处理 + wakeAgent 门、no_agent 纯脚本模式和 context_from 链式流水线,产出经 fire-time 解析的多平台投递([SILENT] 静默契约、live adapter 优先、可选 user-role mirror 保持目标会话的角色交替)。触发器经 CronScheduler provider 抽象可替换(外部 fire 走 store CAS 认领,与内置 ticker 共享同一 run_one_job 执行体)。外围的后台自治组件包括:回合后 fork 自我改进回路 background_review(共享父会话 id 蹭前缀缓存但禁止一切持久化)、kanban notifier/dispatcher 守望循环(事件游标原子认领、机器级单例锁)、deliver_wake 双通道会话唤醒(合成 internal 事件或带 X-Hermes-Session-Id 自 POST)以及 HMAC 签名的 outbound webhooks 事件外发。

关键文件(共 16 个,行数实测,全表见附卷):`cron/scheduler.py`(4428), `cron/jobs.py`(2746), `cron/scheduler_provider.py`(357), `cron/executions.py`(280), `cron/lifecycle_guard.py`(565), `cron/blueprint_catalog.py`(713) 等

**能力点目录(共 12 条):**

1. **60s tick 循环:跨进程文件锁 + 并行/串行双线程池调度** ▲ — 多个进程(gateway 内置 ticker、独立 daemon、手动 hermes cron run)可能同时 tick 同一个 jobs.json,导致重复触发。证据:`cron/scheduler.py:4182` 等3处;规模:tick() 约 280 行 + 池管理/锁约 200 行;价值:高。
2. **自然语言 schedule 解析与时区锚定/偏移修复** ▲ — 用户以四种语法(时长、every 间隔、5 字段 cron、ISO 时间戳)提交计划。证据:`cron/jobs.py:587` 等3处;规模:parse_schedule + 时区辅助约 200 行;价值:高。
3. **catchup/grace 窗口:过期 fast-forward 但仍补跑一次** — gateway 宕机或长任务超过间隔后积压了多个错过的触发点:全部补跑会 burst-fire,全部跳过又会让『运行时长 > interval+grace』的任务被永远推迟(#…。证据:`cron/jobs.py:745` 等3处;规模:约 120 行;价值:高。
4. **at-most-once 语义栈:advance-first / claim_dispatch 预扣 / run_claim 心跳 / 执行台账** ◇ ▲ — cron 触发有多层重复触发风险:同 HERMES_HOME 上 gateway+desktop 两个 60s ticker 会重复派发 one-shot(#59229)。证据:`cron/scheduler.py:4224` 等5处;规模:跨 jobs.py/scheduler.py/executions.py 约 700 行;价值:高。
5. **不活动看门狗与硬中断(而非文档宣称的 3 分钟)** ▲★ — 失控的 agent 循环或挂死的 API 调用会永久占住 cron worker 线程。证据:`cron/scheduler.py:3577` 等4处;规模:约 180 行;价值:高。
6. **prompt 组装管道:script 预处理 / wakeAgent 门 / no_agent 模式 / context_from 链式任务** — 定时任务往往需要先采集数据再喂给 LLM,数据无变化时不应烧 token。证据:`cron/scheduler.py:2453` 等5处;规模:_run_job_script + _build_job_prompt + no_agent 分支约 500 行;价值:高。
7. **多平台投递:origin/all 路由令牌、home channel、live adapter 优先与 [SILENT] 静默** — 无人值守任务的产出要送回正确的会话面(创建它的聊天、指定平台/频道/话题、或全部已接入平台),平台可能在任务创建后才接入。证据:`cron/scheduler.py:1283` 等4处;规模:delivery 解析+发送约 1000 行(_deliver_result 单函数 650 行);价值:中。
8. **cron 会话与主会话隔离 + user-role mirror 保交替** ▲ — cron 运行不能污染用户真实会话:写进目标聊天的 assistant turn 会造成 assistant→assistant 破坏严格角色交替(#2221)。证据:`cron/scheduler.py:3030` 等4处;规模:会话隔离+mirror/seeding 约 700 行;价值:高。
9. **无人值守安全栈:双层注入扫描、gateway 生命周期防护、凭据外泄与模型漂移 fail-closed** ▲ — cron 非交互运行会自动批准工具调用,是注入攻击的最佳落点。证据:`tools/cronjob_tools.py:97` 等6处;规模:cronjob_tools 扫描器约 220 行 + lifecycle_guard 565 行 + scheduler…;价值:高。
10. **CronScheduler provider 抽象(Axis B)与外部触发的 CAS 认领** — 内置 60s ticker 需要进程常驻,scale-to-zero 托管部署(Chronos)需要外部定时器唤醒。证据:`cron/scheduler_provider.py:107` 等4处;规模:357 行 + run_one_job 共享体 200 行;价值:中。
11. **background_review:每回合后 fork agent 的自我改进回路(强隔离 + 缓存亲和)** ◇ ▲ — 每回合后要自动评估『该存什么记忆/更新哪个技能』,但审查 fork 绝不能写坏用户真实会话(curator-takeover:fork 的 harness prompt 落进 …。证据:`agent/background_review.py:828` 等4处;规模:1081 行;价值:高。
12. **后台守望与会话唤醒:kanban notifier/dispatcher 单例锁 + deliver_wake 双通道 + outbound webhooks** ◇ ▲ — gateway 需要长期后台循环:把 kanban 任务的终态事件推给订阅者并唤醒创建者的原会话让 agent 接续处理。证据:`gateway/kanban_watchers.py:1011` 等4处;规模:kanban_watchers 1493 行 + wake 184 行 + outbound_webhooks 569 …;价值:高。

### 2.12 TUI/桌面/Web/IDE 界面层(ui-tui、tui_gateway、acp_adapter、apps/、web/、mcp_serve.py、native/)

Hermes 的界面层围绕一个中心事实组织:tui_gateway 是唯一的 UI 后端——一个 14K 行的 Python JSON-RPC 方法注册中心(120+ RPC、换行分隔 JSON-RPC 线协议),通过 Transport 抽象(contextvar 绑定)同时被 stdio(Ink TUI 子进程)和 WebSocket(desktop/dashboard/移动端)驱动,业务 handler 对传输完全无感。终端前端 ui-tui 是 React+Ink 应用,底下是整套 vendored Ink fork(hermes-ink,~30K 行,加鼠标/拖选/ScrollBox/alternate-screen/背压)外加一个无文档的 widget SDK;浏览器 dashboard(web/,React+xterm.js)不重写聊天界面,而是经 /api/pty 把同一个 `hermes --tui` spawn 在 PTY 后面、注入 HERMES_TUI_GATEWAY_URL 让其 attach 回 dashboard 进程内网关、再用 sidecar WS 把三层进程之外的事件镜像回侧栏,并支持 PTY keep-alive 断线重连回放。Electron desktop(apps/desktop)刻意不嵌 TUI:自带 React 渲染器,通过 apps/shared 的 JsonRpcGatewayClient 连自己 spawn 的 headless `hermes serve` 后端,配套版本偏斜降级(serve→dashboard --no-open)与 Windows 进程树治理;dashboard 进一步可开启 turn_isolation,把 agent turn 移进持久 compute-host 子进程以根治 GIL 饿死事件循环的问题(配 MUTATOR_ROUTE_TABLE 路由与合成 GIL 负载验收 harness)。IDE 侧由 acp_adapter 把同步 AIAgent 包成异步 ACP 服务器(Zed/VS Code,含历史回放与 ContextVar 注入的 pre-execution 编辑审批),mcp_serve.py 则反向把 Hermes 自身暴露为 MCP server(SQLite mtime 轮询事件桥);native/fts5_cjk 是给会话搜索用的 SQLite FTS5 CJK bigram 分词 C 扩展。

关键文件(共 34 个,行数实测,全表见附卷):`tui_gateway/server.py`(14006), `tui_gateway/transport.py`(219), `tui_gateway/ws.py`(476), `tui_gateway/entry.py`(499), `tui_gateway/methods_session.py`(3138), `tui_gateway/methods_prompt.py`(949) 等

**能力点目录(共 10 条):**

1. **单一 dispatcher、多传输同构的 JSON-RPC 网关(stdio/WebSocket 共用全部 RPC 方法)** — 同一个 agent 后端要同时服务终端 TUI(Node 子进程 stdio)、Electron 桌面端、浏览器 dashboard、移动端等多种前端。证据:`tui_gateway/transport.py:3` 等3处;规模:transport.py 219 行 + ws.py 476 行 + server.py 14006 行方法注册中心;价值:高。
2. **TUI 整体作为组件被 dashboard 复用:PTY-over-WebSocket + 进程内 gateway attach + 事件 sidecar 回流** — 浏览器 dashboard 需要一个功能完整的聊天界面。证据:`hermes_cli/web_server.py:14789` 等4处;规模:web_server.py 的 /api/pty 段约 700 行 + pty_bridge.py 293 + win_…;价值:高。
3. **Dashboard compute-host 子进程 turn isolation(GIL 隔离)+ 合成 GIL 重负载认证 harness** ◇ ▲ — CPython 单 GIL:并发的重型 agent turn 在 serving 进程的线程里跑纯 Python 计算时,会把负责 flush WebSocket 帧的事件循环…。证据:`tui_gateway/host_supervisor.py:3` 等3处;规模:compute_host.py 880 + host_supervisor.py 577 + synthetic_tur…;价值:高。
4. **阻塞式 HITL prompt 桥:_block 事件/线程 Event 配对 + expire 生命周期 + 按会话粒度取消** — 同步执行的 agent 工具(危险命令审批、clarify 反问、sudo 密码、secret 输入、terminal.read)需要在 JSON-RPC 事件流上等待人类回答…。证据:`tui_gateway/server.py:3106` 等3处;规模:_block 及五类 request/respond/expire 流转 ~200 行;价值:高。
5. **busy-input 三态策略:运行中 turn 收到新输入时 queue / steer / interrupt(含 redirect)** — turn 进行中用户又发了消息:直接拒绝('session busy')迫使客户端做限时重试并可能静默丢消息。证据:`tui_gateway/server.py:7406` 等2处;规模:_handle_busy_submit + _enqueue_prompt + _drain_queued_prompt…;价值:中。
6. **崩溃法医学 + durable turn marker 自动续跑:panic hook、信号栈转储、SIGPIPE 策略、中断 turn 恢复** ◇ ▲ — 网关子进程的 stdout 是 JSON-RPC 管道,崩溃时无处留痕。证据:`tui_gateway/server.py:63` 等3处;规模:panic/signal/退出路径约 400 行(server.py 头部 + entry.py)+ turn_mark…;价值:高。
7. **ACP 适配器:同步 AIAgent 包装为异步 Agent Client Protocol 服务器(Zed/VS Code/JetBrains)** ▲ — 编辑器侧的 agent 集成有自己的协议(ACP):会话 new/load/resume/fork、流式 chunk、权限请求、编辑 diff 预览。证据:`acp_adapter/server.py:566` 等4处;规模:acp_adapter 共 5831 行(server.py 2510、tools.py 1347、session.py…;价值:中。
8. **Hermes 自身作为 MCP server 暴露(mcp_serve.py):跨 harness 的消息桥 + SQLite 轮询事件桥** ▲ — 让 Claude Code/Cursor 等其他 agent 客户端能读写 Hermes 管理的 Telegram/Discord/Slack 会话——即把本 harness …。证据:`mcp_serve.py:316` 等2处;规模:mcp_serve.py 1037 行单文件;价值:中。
9. **hermes-ink:整套 Ink 渲染器 fork(~30K 行)+ TUI widget SDK(第三方终端小程序框架)** ◇ ▲ — 上游 Ink 缺少生产级 TUI 需要的能力:鼠标追踪与 hit-test、拖选复制、ScrollBox、alternate screen 差分渲染、输出背压、终端背景色探测、…。证据:`ui-tui/package.json:32` 等3处;规模:hermes-ink src 146 文件约 29.8K 行;价值:中。
10. **Desktop 独立进程模型:Electron 管理 headless `hermes serve` 后端 + 版本偏斜降级 + 平台化进程治理** — 桌面 app 需要一个不含浏览器 UI 的本地 agent 后端,且 app 自更新可能领先于用户机器上的 Python 运行时(新 app 撞上不认识 `serve` 子命令…。证据:`apps/desktop/electron/backend-command.ts:18` 等3处;规模:apps/ 共 1560 文件;价值:中。

### 2.13 外围服务工具(语音/图像/视频/搜索/平台工具)

这是 hermes-agent 的"感官与执行器"层:约 2.6 万行代码把语音(唤醒词→STT→agent→流式 TTS 全链路)、图像/视频生成与视觉分析、Web 搜索/提取、X 搜索,以及 Discord/飞书/元宝/Home Assistant/跨平台消息等平台工具接进同一个工具注册表。骨架是五份同构的 provider-registry 模式(tts/stt/image_gen/video_gen/web_search):ABC 定契约、registry 存实例、插件 import 时注册、工具壳只做派发,并以"内置名永远赢、config 声明的 command 型 provider 赢过插件、显式配置绝不静默降级"三条不变量保证可预测性;TTS/STT 还支持零代码的 shell 模板 command provider(引号上下文感知转义 + 密钥清洗子环境)。语音链路是工程密度最高的部分:SentenceChunker 增量切句 + 每句 HTTP prefetch 流水线把 time-to-first-audio 压到第一句,全双工 VAD 用相位钳制阈值实现 TTS 播放中的 barge-in,并把"被打断"这一事实作为 API 局部注释喂回模型。商业化基建 managed_tool_gateway 用 code-pinned 端点 + Nous OAuth + presign 直传 nous-upload 协议让订阅用户免第三方 key 使用 Firecrawl/FAL/Krea/BFL 等托管工具,BFL FLUX3 视频工具进一步把轮询节奏等运维策略经服务器 guidance 字段下发。安全咽喉 image_source.resolve_image_source 统一所有媒体来源的确权,在非本地终端后端下以沙箱内 exec-read 关闭 vision 工具的宿主文件逃逸。文档覆盖总体良好(website/docs 有 tts/voice-mode/wake-word/web-search/x-search 专页),但 bfl_flux3_* 六个视频工具与 presign 上传协议完全无文档,web_tools/image_generation_tool 两个模块头的架构描述已过时。

关键文件(共 43 个,行数实测,全表见附卷):`tools/tts_tool.py`(3964), `tools/tts_streaming.py`(488), `tools/tts_text_normalize.py`(278), `tools/neutts_synth.py`(110), `tools/voice_mode.py`(2308), `tools/wake_word.py`(1464) 等

**能力点目录(共 12 条):**

1. **TTS/STT 三层后端解析与 registry 'built-ins always win' 不变量** — 语音合成/识别要支持十几个后端(edge/openai/elevenlabs/minimax/gemini/xai/piper/neutts 等)且允许插件和用户自定义扩展,但…。证据:`agent/tts_registry.py:90` 等2处;规模:tts_registry 134 行 + tts_provider 274 行 + transcription_regi…;价值:高。
2. **Command-type provider:零 Python 代码接入任意 CLI(shell 模板 + 引号上下文感知转义 + 秘密清洗子环境)** — 用户想把本地任意 TTS/STT CLI(Piper、VoxCPM、doubao-speech、curl 一行命令)接进 agent,但不该要求写 Python 插件。证据:`tools/tts_tool.py:908` 等2处;规模:tts_tool.py 581-1235 行区间约 650 行 + transcription_tools.py 对称实…;价值:高。
3. **流式语音管线:增量切句 + 每句 HTTP prefetch 流水线 + 通用同步回退** — 语音对话的核心指标是 time-to-first-audio:等 LLM 全部生成完再合成整段音频会有几十秒静默。证据:`tools/tts_tool.py:3532` 等3处;规模:tts_streaming.py 488 行 + tts_tool.py 的 stream_tts_to_speaker…;价值:高。
4. **全双工 barge-in:相位感知 VAD + 打断事实注入模型** — 语音对话要允许用户在 agent 说话/思考的任何时刻插话,但麦克风会收到扬声器回放的 TTS 音频(speaker bleed),朴素能量阈值要么被回放误触发、要么被回放淹没…。证据:`tools/voice_mode.py:2064` 等2处;规模:voice_mode.py 中 listen_for_speech + full_duplex_listen 约 400…;价值:高。
5. **Wake word 三引擎全本地热词检测(N 连帧确认 + 机器级独占锁)** — 免手动唤醒('Hey Hermes')需要常开麦克风,但音频不能离开本机、环境闲聊的杂散音素不能误触发、多个 Hermes 表面(CLI/TUI/desktop)不能同时抢一个…。证据:`tools/wake_word.py:565`;规模:wake_word.py 1464 行:3 个引擎适配 + 模型下载/tflite 运行时桥接 + 需求自检 + 检测器…;价值:中。
6. **STT 自动探测链 + 双阈值幻觉段过滤** — 语音转写要在 '本地免费' 与 '云端付费' 间自动选择且不背着用户偷换。证据:`tools/transcription_tools.py:1071` 等3处;规模:transcription_tools.py 2687 行(8 个云/本地后端 + command/plugin 派发 …;价值:中。
7. **Nous Managed Tool Gateway:代码内 pin 的 vendor 端点 + presign 直传 nous-upload 媒体协议** ◇ — 让订阅用户不带任何第三方 API key 就能用 Firecrawl/FAL/OpenAI-TTS/BFL 等付费工具,需要一个统一代理。证据:`tools/managed_tool_gateway.py:445` 等2处;规模:managed_tool_gateway.py 452 行 + fal_common.py 的 _ManagedFalS…;价值:高。
8. **BFL FLUX3 视频工具:服务器 guidance 作为活策略通道 + 预算化轮询循环** ◇ ▲ — 长耗时视频生成任务需要客户端轮询,但轮询节奏、限流等待、交付方式等策略若硬编码在客户端就会与服务器实际执行的策略漂移。证据:`tools/flux3_video_tool.py:178` 等3处;规模:flux3_video_tool.py 1249 行;价值:高。
9. **image_generate 统一 surface:FAL 模型目录 supports 白名单 + 插件派发 + managed Krea 模型级路由** ▲ — 一个 image_generate 工具要覆盖 7+ 后端(FAL 目录 11 个模型、openai、xai、krea、openrouter、deepinfra、openai-…。证据:`tools/image_generation_tool.py:91` 等3处;规模:image_generation_tool.py 1668 行 + agent/image_gen_provider.p…;价值:中。
10. **入站图像 native/text 双模路由 + 统一媒体源解析器(沙箱确权)** — 用户附图该直接作为多模态 content part 给主模型看原始像素,还是先用辅助 vision 模型转成文字?决策依赖主模型能力元数据。证据:`agent/image_routing.py:502` 等2处;规模:image_routing.py 821 行 + image_source.py 391 行 + vision_tool…;价值:高。
11. **Web 搜索/提取 per-capability registry + 确定性 truncate-and-store 长页分页** ▲ — 8 个 web 后端能力参差(brave-free/ddgs/searxng/xai 只有 search),要允许 search 与 extract 各选后端且插件化迁移后不改…。证据:`agent/web_search_registry.py:184` 等2处;规模:web_tools.py 1237 行 + web_search_registry.py 304 行 + provide…;价值:高。
12. **x_search degraded 无引用检测:识别 '模型编的' 与 '索引查的'** — xAI 的 x_search 在过滤条件(handle/日期)命中零结果时仍返回 200 与一段由模型自身知识合成的回答,与真实引用支撑的结果外观完全相同,agent 会把编造…。证据:`tools/x_search_tool.py:418`;规模:x_search_tool.py 552 行;价值:中。

### 2.14 安装/更新/运维基建(installer、self-update、doctor、测试/CI/发布、日志/路径/i18n 基座)+ 文档-代码冲突专项

该子系统是 hermes-agent 作为"用户自持 agent harness"的地基:源码检出式安装(install.sh/install.ps1/setup-hermes.sh 把仓库放到 $HERMES_HOME/hermes-agent 并用 uv.lock 哈希校验建 venv),之上是一个把自更新做成可回滚事务的 `hermes update` 管线(git ff-only + 9 文件语法编译守卫自动 reset --hard 回滚 + 子进程 import 探针 + 断点续传 marker + Windows ZIP 两阶段替换回退),配套跨 Python/Rust/Electron 字节兼容的更新互斥锁和 2777 行的 doctor 诊断/自修复系统。基座模块提供 profile 感知的 HERMES_HOME 三层解析(ContextVar/env/平台默认,带跨 profile 误写警告)、异步脱敏日志、原子写基元、Windows UTF-8 bootstrap、托管 Node/uv 工具链自举自愈。工程侧有 fail-open 的 CI change classifier + orchestrator 工作流、env -i 密封 + per-file 子进程隔离 + flaky 一次重试 + LPT 时长切片的测试基建、CalVer/SemVer 双版本发布脚本与免冲突贡献者映射目录,以及 17 语言的静态文案 i18n 薄片。文档对照总体质量高(updating.md 的 9 文件守卫、1 GiB 跳过、SIGHUP 防护等均与代码一致),但仍抓到 6 处漂移:compose 注释的过时 ENTRYPOINT、不存在的 submodule 更新、语言列表漏 ar、测试规模数字 3 倍漂移、doctor --ack 未入 CLI 参考、依赖安装机制被简化描述。

关键文件(共 43 个,行数实测,全表见附卷):`hermes_cli/update_cmd.py`(5540), `hermes_cli/update_lock.py`(289), `hermes_cli/main.py`(12599), `hermes_cli/doctor.py`(2777), `hermes_cli/managed_uv.py`(1304), `hermes_cli/backup.py`(1904) 等

**能力点目录(共 13 条):**

1. **hermes update 多阶段自愈更新管线(git 主路径)** ▲ — 源码检出式安装(~/.hermes/hermes-agent)在用户机器上自更新时,任何一步失败(坏 commit 过了 CI、依赖装一半、终端断线、gateway 占用 ve…。证据:`hermes_cli/update_cmd.py:94-97` 等4处;规模:update_cmd.py 5540 行 + main.py 中约 1500 行 update 辅助;价值:高。
2. **Windows ZIP 两阶段替换更新回退路径** ◇ — Windows 上杀毒/NTFS 过滤驱动会让 git 文件 I/O 直接报 Invalid argument,git 路径不可用。证据:`hermes_cli/update_cmd.py:784-788` 等3处;规模:约 500 行(_update_via_zip + _stage_replacement/_atomic_replace…;价值:高。
3. **跨进程更新互斥锁(update_lock.py,与 Rust/Electron 字节兼容)** ◇ — 终端 `hermes update`、dashboard 的 Update 按钮、桌面 Tauri `hermes-setup --update` 三个入口可能同时更新同一棵检…。证据:`hermes_cli/update_lock.py:65` 等4处;规模:289 行;价值:高。
4. **hermes doctor 诊断/自修复/安全公告确认系统** ▲ — 跨平台安装(源码/Docker/Nix/Termux/Windows)的故障面极大:证书坏、venv 半更新、版本文件漂移、被投毒的依赖包、可疑 MCP stdio 命令、s6…。证据:`hermes_cli/doctor.py:720-721` 等3处;规模:doctor.py 2777 行 + security_advisories.py 453 行;价值:中。
5. **供应链防御型依赖策略 + wheel 构建禁令** — 2026-05-12 Mini Shai-Hulud 蠕虫污染 PyPI 上的 mistralai 2.4.6:若依赖用范围版本,隔离前几小时内所有新装机都会中招。证据:`pyproject.toml:20-22` 等4处;规模:pyproject.toml 449 行(注释即策略文档)+ setup.py 74 行 + setup-hermes.…;价值:高。
6. **CI 平价测试基建:密封环境 + per-file 子进程隔离 + flaky 一次重试** — 17k+ 测试在开发机(有真实 API key、本地时区、16+ 核)和 CI 上行为不一致,曾多次'本地绿 CI 红'。证据:`scripts/run_tests.sh:169-171` 等4处;规模:run_tests.sh 183 行 + run_tests_parallel.py 1142 行;价值:高。
7. **基于历史时长的 LPT 测试切片 + CI duration 缓存回流** ◇ — 12 个并行 CI 切片若按文件名均分,慢文件扎堆的切片会顶到 per-file 超时并拖长整体 wall time。证据:`scripts/run_tests_parallel.py:600-603` 等3处;规模:runner 内约 150 行 + tests.yml 中 generate/save-durations 两个 job;价值:中。
8. **CI change classifier(fail-open 车道分类)+ orchestrator 工作流** — monorepo(Python + 桌面 TS + 网站 + installer + Docker)里每个 PR 全量跑所有 job 太贵,但漏跑一个相关 lane 会让回归在…。证据:`scripts/ci/classify_changes.py:49` 等3处;规模:classify_changes.py 172 行 + ci.yml 390 行 + 25 个 workflow 文件;价值:高。
9. **发布流程:CalVer tag + SemVer 双版本、三文件版本同步、免冲突贡献者映射** ◇ — 发布需要同时维护 git tag(CalVer)、Python 包版本(SemVer)、桌面 Electron 版本三处一致。证据:`scripts/release.py:2211-2213` 等3处;规模:release.py 2637 行(其中 ~2000 行是冻结的 LEGACY_AUTHOR_MAP)+ add_con…;价值:中。
10. **Profile 感知的 HERMES_HOME 解析与跨 profile 误写守卫** ◇ — 119+ 个文件通过 get_hermes_home() 解析状态目录。证据:`hermes_constants.py:100-102` 等3处;规模:hermes_constants.py 前 300 行为核心;价值:高。
11. **Hermes 托管 Node 工具链自举与自愈** ◇ — TUI/web UI 构建需要满足 engines 要求的 Node,但用户机器上的 node 可能缺失、属于用户自己(nvm/brew/Nix,不能动)、被中断安装留成'bi…。证据:`hermes_constants.py:582-585` 等3处;规模:hermes_constants.py:285-680 约 400 行 + node-bootstrap.sh 437 …;价值:中。
12. **中央日志基建:异步队列 + 脱敏 + Windows 跨进程轮转 + 外部轮转自愈** ▲ — TUI、gateway、MCP server、CLI 命令多进程同时写同一组日志文件:Windows 上 stdlib 轮转 rename 撞开着的句柄报 WinError 3…。证据:`hermes_logging.py:64-67` 等3处;规模:800 行;价值:中。
13. **i18n 薄片:17 语言目录 + 英语回退 + 键名兜底** ▲ — 面向终端用户的静态文案(审批提示、gateway 回复、重启排空通知)需要本地化,但全量 i18n 会拖累所有日志/错误/工具输出。证据:`agent/i18n.py:43-46` 等3处;规模:i18n.py 282 行 + locales/ 17 个 YAML(en.yaml 453 行);价值:低。

### 2.15 精选详述(12 条,★ 标于上文目录;全部 170 条同格式详述见附卷)


**三级用户介入:interrupt(硬停)/ steer(不打断注入)/ redirect(只取消模型请求)**

- 解决:用户在 agent 干活时说话有三种意图:彻底停下、顺带补充指示、纠正方向但不作废已完成的工作。单一 interrupt 无法区分,会把轻量纠偏变成'杀掉整回合重来'。
- 实现:interrupt() 置 _interrupt_requested 并按线程 id 精确下发 _set_interrupt(仅本 agent 执行线程 + 并发工具 worker tids + 递归传播到子 agent),hard_cancel 经压缩提交栅栏原子发布;steer() 只把文本暂存 _pending_steer,工具批次结束后由 apply_pending_steer_to_tool_results 追加到最后一条 tool 结果(带 marker,保持角色交替),循环顶部还有 pre-API drain 让 API 调用期间到达的 steer 在本轮就被看到;redirect() 在工具执行期降级为 steer,否则只中断模型请求(不波及工具 worker 和子 agent),把纠正文本放入 _pending_redirect。三者共享 _pending_redirect_lock 防 /stop 与纠正互相竞态。
- 证据:`run_agent.py:3121` · `run_agent.py:3305` · `run_agent.py:3258` · `agent/agent_runtime_helpers.py:3921`
  ```
          if self._execution_thread_id is not None:
              _set_interrupt(True, self._execution_thread_id)
              self._interrupt_thread_signal_pending = False
  ```
- 规模:约 400 LOC(run_agent.py:3028-3392 + runtime_helpers steer 注入 + 循环内多处 drain 点);线程安全与竞态处理密集,复杂度高。
- 学习价值:高 — 把'用户介入'按破坏性分成三个粒度、并用按线程 id 定域的中断信号支持同进程多 agent(gateway),是 harness 交互设计的高质量范本;steer 借 tool 结果 piggyback 保持角色交替的手法尤其值得学。

**TurnContext 回合前奏 + api_content『persist-what-you-send』侧车**  **[◇未见于文档]**

- 解决:每回合的一次性设置(系统提示恢复、preflight 压缩、插件/记忆注入)与循环体纠缠会让 6000 行循环不可维护;更深的问题是:注入内容若直接改写用户消息,持久转录被污染;若每次现注入,历史消息的线上字节会漂移,provider prompt cache 前缀从注入点开始整段失效。
- 实现:build_turn_context 把全部前奏收敛为一个函数,返回 TurnContext dataclass(messages、current_turn_user_idx、plugin_user_context、ext_prefetch_cache 等)供循环读取;协作函数以参数显式传入避免 import cycle。注入走 api_content 侧车:当前回合 user 消息在前奏时由 compose_user_api_content 把记忆预取+插件上下文组成的确切线上字节盖章存为 api_content,构建 api_messages 时当前消息用盖章值、历史 user/assistant 消息回放各自侧车的历史字节——干净 content 与线上字节永久分离,前缀逐字节稳定。前奏还做 between-turns MCP 工具刷新(仅在新回合首次请求前扩展前缀,保证缓存安全)与 sys.modules 门控省掉 0.4s 的 mcp 包导入。
- 证据:`agent/turn_context.py:309` · `agent/conversation_loop.py:1634` · `agent/conversation_loop.py:1648` · `agent/turn_context.py:429`
  ```
  class TurnContext:
      """Values produced by the turn prologue and consumed by the turn loop."""
  ```
- 规模:turn_context.py 1275 行 + 循环内约 60 行回放逻辑;侧车不变式贯穿持久化/压缩/redirect 多个子系统。
- 学习价值:高 — api_content 侧车同时解决'转录洁净'与'prompt cache 字节稳定'两个互相矛盾的需求,是上下文注入类 harness 的关键设计;MCP 刷新的缓存安全时点选择(前奏、首次请求前)也是缓存意识工程的好例子。

**Anthropic prompt cache 保护策略 (4 断点 + 静态前缀切分 + failover 重贴)**  **[▲文档不符]**

- 解决:Anthropic 每请求最多 4 个 cache_control 断点。既要缓存稳定的 system 前缀(跨会话复用),又要缓存最近的对话尾部(会话内复用),还要兼容 OpenRouter 信封布局(空 content 消息贴顶层 marker 会被忽略、role:tool 顶层 marker 会静默挂起),并且 mid-turn failover 换 provider 后要按新 provider 的策略重贴。
- 实现:build_prompt_cache_plan/apply_anthropic_cache_control(prompt_caching.py)先 strip 旧 marker,再用 _apply_system_cache_markers 把 system 拆成 [静态前缀|易变后缀] 两个 marker,剩余 4-breakpoints_used 个 marker 贴到最近可承载的非 system 消息;_can_carry_marker() 对信封布局排除空 content / 纯 tool_calls 消息避免浪费断点;direct_native_tool_cache 分支把一个断点让给 tools 数组。strip_anthropic_cache_control() 支持 failover 后按新 provider 重贴(#72626)。
- 证据:`agent/prompt_caching.py:382` · `agent/prompt_caching.py:47` · `agent/prompt_caching.py:338`
  ```
      remaining = 4 - breakpoints_used
      non_sys = [
  ```
- 规模:394 行,纯函数无状态
- 学习价值:高 — prompt cache 断点预算的精细分配(静态前缀 vs 滚动窗口 vs tools)+ 跨 provider 信封差异处理,是省 75% 输入成本的关键工程,细节极多值得深挖。
- ▲ 文档不符:context-compression-and-caching.md 只描述旧的 "system_and_3" 布局(断点1=system + 最后3条),没有描述代码里默认的 静态前缀切分 + 末尾2条 的新布局(prompt_caching.py:1-8 与 348-364 明确说明静态前缀存在时用 前缀+system尾+末2条)。

**三段式批量压缩管线(头保护衰减/token 预算尾部/边界对齐)**

- 解决:把超长对话压回预算内,同时不能:切断 tool_call/tool_result 配对(provider 400)、丢掉最新的用户任务与助手回复、让早期轮次在多次压缩中'化石化'永生、或把上一次的 handoff 摘要当普通消息层层堆叠。
- 实现:compress() 五阶段:①确定性剪枝+删除平台空回显;②边界计算——头保护在首次压缩后衰减为 0(仅留系统提示,#11996),尾部按 tail_token_budget(threshold×summary_target_ratio)反向累加、1.5x 软顶避免切在超大消息中间,_align_boundary_backward/forward 保证不劈开工具组,再用锚点链保证最新 user/assistant 消息必在尾部;③扫描并回收窗口内旧 handoff 摘要(rehydrate 进 _previous_summary,merged handoff 拆回真实内容,防化石堆叠);④生成/迭代更新摘要,失败时按 auth/network/config 分类决定 abort(原样返回)或确定性 fallback;⑤重组:系统提示追加 compaction note、_strip_historical_media 清掉历史图像 base64、_sanitize_tool_pairs 清孤儿配对。
- 证据:`agent/context_compressor.py:6148-6152` · `agent/context_compressor.py:4759-4760` · `agent/context_compressor.py:1568-1570` · `agent/context_compressor.py:6447-6451` · `agent/context_compressor.py:6785`
  ```
          compress_start = self._protect_head_size(messages)
          compress_start = self._align_boundary_forward(messages, compress_start)
  
          # Use token-budget tail protection instead of fixed message count
          compress_end = self._find_tail_cut_by_tokens(messages, compress_start)
  ```
- 规模:compress() 本体约 830 行,加边界/锚点/摘要扫描辅助约 1500 行;复杂度极高
- 学习价值:高 — 教科书级的'保头保尾压中间'完整实现:头保护衰减防化石化、token 预算而非条数定尾、工具组对齐防孤儿、旧摘要回收防堆叠、按失败类别决定 abort-vs-fallback,每个决策都有 issue 号背书。

**记忆/技能 nudge 计数器 → 后台自我改进 review fork**  **[▲文档不符]**

- 解决:README 宣称 agent 会『nudge 自己持久化知识』:需要一种既不打断用户任务、又不污染主会话上下文/前缀缓存的周期性自我反思机制。
- 实现:turn_context.py 每个用户回合递增 _turns_since_memory(默认 nudge_interval=10,重启后从历史 user 消息数取模恢复计数,#22357),conversation_loop.py 按工具迭代数递增 _iters_since_skill;调用 memory/skill_manage 工具会在 tool_executor.py 归零计数。触发后不在对话里注入任何文字(turn_context.py:588 明确 'no nudge injection'),而是 turn_finalizer 在响应送达后 spawn 一个 fork 的 AIAgent(background_review.py):线程级工具白名单只留 memory+skills、_persist_disabled 阻断对真实会话 DB 的写入(防『curator 夺舍』)、继承父会话 cached system prompt 与 byte-identical tools 以命中前缀缓存(实测省 ~26% 成本)、危险命令 auto-deny。/refine [focus] 可手动带焦点触发同一 fork。codex_app_server 路径在 codex_runtime.py 里复刻同一套触发。
- 证据:`agent/turn_context.py:593-599` · `agent/turn_finalizer.py:716-722` · `agent/background_review.py:903-909` · `agent/background_review.py:828` · `agent/tool_executor.py:597-600`
  ```
      if (agent._memory_nudge_interval > 0
              and "memory" in agent.valid_tool_names
              and agent._memory_store):
          agent._turns_since_memory += 1
          if agent._turns_since_memory >= agent._memory_nudge_interval:
  ```
- 规模:background_review.py 1081 行 + turn_context/turn_finalizer/codex_runtime 中的触发点;高复杂度(fork 隔离、缓存字节级对齐、持久化隔离)
- 学习价值:高 — 这是『self-improving』宣称的真正落地点:计数触发 + 响应后 fork + 工具白名单 + 持久化隔离 + 前缀缓存复用,是后台自反思 agent 的教科书级工程方案,坑(fork 写脏父会话、缓存 miss、stdout 泄漏)都有注释记录。
- ▲ 文档不符:README.md:19 说 'nudges itself to persist knowledge',字面暗示会话内提醒;实际代码明确不注入对话(turn_context.py:588 'Preserve the original user message (no nudge injection).'),nudge 实为会话外的后台 review fork。官方 memory.md 文档口径(background self-improvement review)与代码一致,README 措辞偏营销。

**跨会话召回:FTS5 三索引 session_search(discovery/scroll/read/browse)**  **[▲文档不符]**

- 解决:『搜索自己的过去对话』需要在一个 SQLite 里同时支持词级英文、子串、CJK 检索,并把结果以低 token 成本、可继续钻取的形态交给模型。
- 实现:hermes_state_search.py(SessionSearchMixin,2230 行)维护三套索引:messages_fts(BM25 词检索)、messages_fts_trigram(子串,约 2.6x 存储,排除 tool 行)、messages_fts_cjk(CJK bigram),带查询消毒(引号短语保留、悬空布尔词剔除、连字符/点号词包引号)、增量 merge、分步重建与存储优化。tools/session_search_tool.py 是模型面工具:单一 shape 四模式(query→discovery 按 lineage 去重 + ±5 消息窗 + 首尾 bookends;session_id+anchor→scroll;仅 session_id→整段 read,跨 profile 可寻址 @session:<profile>/<id>;无参→browse),cron 会话只降权不排除(#19434 recall blindness),kanban/subagent/tool 会话隐藏,压缩产物摘要从 bookends 剔除(#43175)。
- 证据:`hermes_state_search.py:1` · `tools/session_search_tool.py:21-23` · `tools/session_search_tool.py:42-50` · `hermes_state_search.py:1243-1245`
  ```
  """Full-text / trigram / CJK message search and FTS maintenance for SessionDB.
  ```
- 规模:hermes_state_search.py 2230 + session_search_tool.py 1161 行;高复杂度(三索引、查询路由、重建状态机)
- 学习价值:高 — 纯 SQLite 零 LLM 的跨会话记忆检索完整实现:三索引路由、FTS5 查询消毒、lineage 去重、自动化会话降权、bookends 低成本预览,是 agent 长期记忆检索层的高质量参照。
- ▲ 文档不符:README.md:26 与 website/docs/index.mdx:123 宣称 'FTS5 session search with LLM summarization for cross-session recall',但代码明确 'No LLM calls anywhere'(session_search_tool.py:23,模块史注明 summary LLM 路径已在合并重构时移除);website/docs/user-guide/sessions.md:551 也写明 'No LLM calls, no summarization' —— README/index 的 LLM summarization 属过期宣称。

**自注册工具注册表:AST 自动发现 + check_fn 可用性 TTL 缓存与瞬断宽限**  **[▲文档不符]**

- 解决:harness 需要一个不用手工维护清单的工具注册/发现机制,同时工具可用性探测(Docker daemon、playwright、API key)昂贵且会抖动——一次探测超时就会让整个 toolset 从子代理 schema 里消失。
- 实现:每个 tools/*.py 在模块导入时调用 registry.register() 自注册 ToolEntry(schema/handler/check_fn/toolset/emoji/max_result_size/dynamic_schema_overrides);discover_builtin_tools() 用 AST 扫描 tools/ 目录找顶层 registry.register() 调用并按 (mtime_ns,size) 缓存判定结果到磁盘。check_fn 结果按 (fn, multiplex-profile-scope) 缓存 30s TTL,且在上次成功 60s 内的失败被当作 flake 直接返回 last-good True 且不缓存失败,防止工具集中途闪断;registry._generation 计数器驱动 get_tool_definitions 的 memo 失效,LRU 上限 8 条(#19251)。dispatch() 统一桥接 async handler(_run_async 持久事件循环)并把非法返回类型规范化为 tool_error。
- 证据:`tools/registry.py:84-86` · `tools/registry.py:316-320` · `model_tools.py:348-358`
  ```
      for path in sorted(tools_path.glob("*.py")):
          if path.name in {"__init__.py", "registry.py", "mcp_tool.py"}:
              continue
  ```
- 规模:registry.py 956 行 + model_tools.py 1569 行,中高复杂度(多线程锁、双层缓存、profile 维度隔离)
- 学习价值:高 — 自注册+AST 发现+磁盘缓存是零维护成本的插件化工具体系范式;check_fn 的 last-good 宽限窗口解决了『可用性探测抖动导致工具静默消失』这一真实生产问题,值得任何 harness 借鉴。
- ▲ 文档不符:website/docs/developer-guide/tools-runtime.md 只说 check_fn『cached per-call』并展示无缓存的简化代码,未提及代码中实际存在的 30s TTL 缓存(_CHECK_FN_TTL_SECONDS, registry.py:216)与 60s 瞬断宽限(_CHECK_FN_FAILURE_GRACE_SECONDS, registry.py:220)机制。

**execute_code 编程式工具调用:UDS/TCP/文件三态 RPC + token 鉴权 + 环境洗净**

- 解决:多步工具链每步都要一次推理往返且中间结果占满上下文;让 LLM 写脚本直连工具又会暴露进程凭证并绕过审批体系。
- 实现:父进程生成 hermes_tools.py 桩模块:本地走 Unix domain socket(macOS 用 /tmp 避开 104 字节路径限制,Windows 退化为 127.0.0.1 TCP),远端(Docker/SSH/Modal/Daytona)走文件 RPC(req_/res_ 原子重命名+自适应轮询);仅脚本 stdout 回到上下文。RPC 服务器逐请求用 secrets.compare_digest 校验 32 字节随机 token(经子进程 env 传递,UDS 文件 chmod 0600),强制 7 工具白名单(SANDBOX_ALLOWED_TOOLS ∩ 会话已启用工具,由调用方传入防子代理篡改进程全局)、50 次调用上限、剥离 terminal 的 background/pty 参数;所有调用走 handle_function_call 使审批/hook/限长照常生效,且 RPC 线程经 propagate_context_to_thread 继承审批上下文防 gateway 静默放行(#33057)。子进程 env 经 _scrub_child_env 洗净:KEY/TOKEN/SECRET/BEARER/APIKEY 等子串全拦,仅安全前缀、操作型 HERMES_* 与 env_passthrough 显式 opt-in 通过。脚本整体还先过 check_execute_code_guard 人审(#30882)。
- 证据:`tools/code_execution_tool.py:703-708` · `tools/code_execution_tool.py:63-71` · `tools/code_execution_tool.py:259-262` · `tools/code_execution_tool.py:1413-1415`
  ```
                  if not rpc_token or not secrets.compare_digest(
                      # Compare as bytes: compare_digest raises TypeError on a
                      # str with non-ASCII characters, and the token comes from
                      # sandbox-script-supplied JSON.
                      str(request.get("token") or "").encode(), rpc_token.encode()
  ```
- 规模:code_execution_tool.py 2087 行,高复杂度(三种传输、两种执行模式 project/strict、远端文件轮询协程)
- 学习价值:高 — README 第 28 行宣称的『Write Python scripts that call tools via RPC』的完整落地:凭证隔离靠 RPC 边界而非信任脚本,审批上下文跨线程/跨进程传播,文件 RPC 让同一机制覆盖所有远端后端——是 Programmatic Tool Calling 的参考实现。

**统一环境抽象:spawn-per-call + 会话快照重放**  **[▲文档不符]**

- 解决:7 种执行后端(local/docker/ssh/singularity/modal/daytona/vercel_sandbox)底层能力差异巨大(有的只有阻塞 SDK exec 调用,没有真实 subprocess),但 agent 需要一个『有状态 shell』的统一假象:cwd、export 的环境变量、函数、alias 都要跨命令持久。
- 实现:tools/environments/base.py 的 BaseEnvironment 定义唯一契约:子类只需实现 _run_bash() 和 cleanup()。init_session() 用一次 login bash 把 export -p / declare -f / alias -p 原子写入(mktemp+mv,避开 macOS bash 3.2 无 $BASHPID 的并发写撕裂)一个快照文件;每条命令由 _wrap_command() 包装成『source 快照 → cd → eval 用户命令 → 重新 dump 快照 → printf CWD 标记』的完整脚本,cwd 通过 stdout 内嵌的 __HERMES_CWD_<session>__ 标记回传并从输出剥除。SDK 型后端(Modal/Daytona)通过 _ThreadedProcessHandle 把阻塞 exec_fn 适配成带 os.pipe stdout 的 ProcessHandle 鸭子类型,stdin 则降级为 heredoc 嵌入(_stdin_mode="heredoc")。快照失败时逐级回退:bash -l per command → 非 login bash -c(Windows Git-Bash 崩坏场景)。
- 证据:`tools/environments/base.py:706` · `tools/environments/base.py:823` · `tools/environments/base.py:374`
  ```
  f"mv -f {_snap_tmp} {_quoted_snap} || rm -f {_snap_tmp}\n"
  f"builtin cd -- {_quoted_cwd} 2>/dev/null || true\n"
  f"printf '\\n{self._cwd_marker}%s{self._cwd_marker}\\n' \"$(pwd -P)\"\n"
  ```
- 规模:base.py 1370 行,加各后端子类共约 6400 行;复杂度高(跨 bash 3.2/MSYS/远端 POSIX 的可移植 shell 生成)
- 学习价值:高 — 『快照重放代替常驻 shell』是 harness 设计的一个可迁移范式:无需 pty/tmux 就能在任意只支持一次性 exec 的后端上重建有状态 shell,且每步都有原子性与降级路径,值得作为多后端抽象的参考实现。
- ▲ 文档不符:文档只说 'Filesystem, current working directory, and exported environment variables persist between calls',完全没有讲快照文件机制、原子 mv、以及函数/alias 也被持久化。

**投递义务台账(delivery ledger:crash 后最终回复不丢、诚实 at-least-once)**

- 解决:回合已烧完 token、最终回复只存在于 Python 局部变量里,gateway 在 finalize 与平台 ACK 之间崩溃/重启就会无痕丢失这条回复(#58818 等)。
- 实现:base.py 在发送最终文本前把 (session_key, message_ref, content) 哈希成 obligation_id,依次写 state.db 三个检查点 record_obligation(pending)→mark_attempting→mark_delivered/mark_failed,全部 best-effort 不阻塞真实发送;启动时 run.py:_redeliver_pending_obligations 先于 resume 扫描,sweep_recoverable() 用 owner_pid+进程启动时间判活、原子改 owner 防止双 gateway 重复认领,只认领本次 boot 已连接平台的行以免白烧 attempts;pending 行直接重发,attempting/failed 行(可能已送达)带可见 "♻️ Recovered reply" 前缀,attempts 上限 3 + 24h stale 转 abandoned 防毒行;重投后 clear_resume_pending 防止 resume 路径再花钱重跑同一回合。
- 证据:`gateway/delivery_ledger.py:68-71` · `gateway/platforms/base.py:6087` · `gateway/run.py:10374-10379`
  ```
  RECOVERED_MARKER = (
      "♻️ Recovered reply — the gateway restarted during delivery, "
      "so this may be a duplicate:\n\n"
  )
  ```
- 规模:delivery_ledger.py 374 行 + base.py 记账段约 70 行 + run.py 重投约 105 行;中等复杂度、契约设计极精
- 学习价值:高 — 把『发出的最终回复』当成分布式义务来记账,pending/attempting 语义区分 + 可见重复标记的 honest at-least-once 契约,是 LLM 场景下 exactly-once 不可得时的最佳工程答案(前一版 outbox 因静默重发被否决,#61790)。

**同进程子代理构建与隔离(delegate_task)**  **[▲文档不符]**

- 解决:父代理需要把重推理/高噪音子任务外包出去,同时防止子任务的中间工具调用和推理污染父上下文,并防止子代理获得父代理没有的能力或触发用户交互/共享状态副作用。
- 实现:delegate_task 在主线程用 _build_child_agent 构建全新 AIAgent:全新对话(无父历史)、独立 task_id/终端会话、skip_context_files/skip_memory、ephemeral_system_prompt 由 goal+context+workspace hint 拼装。工具集三层治理:显式请求时与父工具集做交集(_expand_parent_toolsets 先展开复合工具集)、_strip_blocked_tools 剥离纯黑名单工具集、DELEGATE_BLOCKED_TOOLS(delegate_task/clarify/memory/send_message/cronjob)经 disabled_toolsets 在复合工具集展开后逐工具减除。子代理线程内安装非交互审批回调(默认 auto-deny)避免 input() 死锁父 TUI。凭据/模型/推理配置继承父代理,也可被 delegation.provider 配置整体重定向到便宜模型。
- 证据:`tools/delegate_tool.py:48` · `tools/delegate_tool.py:1281` · `tools/delegate_tool.py:1527` · `tools/delegate_tool.py:76`
  ```
  DELEGATE_BLOCKED_TOOLS = frozenset(
      [
          "delegate_task",  # no recursive delegation
          "clarify",  # no user interaction
          "memory",  # no writes to shared MEMORY.md
  ```
- 规模:delegate_tool.py 共 3931 行,其中构建/隔离路径(_build_child_agent、toolset 治理、审批回调)约 900 行,复杂度高(凭据继承、api_mode 重推导、MCP 工具集保留等大量边界分支)。
- 学习价值:高 — 这是 harness 子代理隔离的教科书实现:工具集交集+黑名单双层防越权、上下文/记忆隔离、线程内审批回调防死锁,每个设计都对应真实事故编号,可直接迁移到任何多代理框架。
- ▲ 文档不符:AGENTS.md:993 称单任务可传可选 toolsets 参数,但模型侧 schema(DELEGATE_TASK_SCHEMA)根本没有 toolsets 字段,代码注释明确 'the model cannot choose or narrow them (no model-facing toolsets arg)'(tools/delegate_tool.py:2966-2968);website 用户文档(delegation.md:158)则是对的。

**不活动看门狗与硬中断(而非文档宣称的 3 分钟)**  **[▲文档不符]**

- 解决:失控的 agent 循环或挂死的 API 调用会永久占住 cron worker 线程;但合法任务可能连续跑几小时,不能用简单墙钟超时一刀切。
- 实现:run_job 把 agent.run_conversation 提交到单线程池,主线程每 5s 轮询:未完成时读 agent.get_activity_summary().seconds_since_activity(agent 在每次工具调用/API 调用/流式 token 时 _touch_activity 刷新,契约见 agent/session_activity.py),空闲超过 HERMES_CRON_TIMEOUT(默认 600s,0=无限)判定超时,调用 request_hard_interrupt(agent, ...) 硬中断并 raise TimeoutError,失败路径带上 last_activity/iteration/tool 的诊断快照。同一轮询循环还顺带做 one-shot 的 run_claim 心跳。另有独立的 SessionDB 构造超时(默认 10s,单独线程池 submit(SessionDB).result(timeout=...)),防止 wedged sqlite flock 把任务卡在 _running_job_ids 里永远 'already running — skipping'。
- 证据:`cron/scheduler.py:3577` · `cron/scheduler.py:3654` · `cron/scheduler.py:3684` · `cron/scheduler.py:2961`
  ```
          else:
              _cron_timeout = 600.0
          _cron_inactivity_limit = _cron_timeout if _cron_timeout > 0 else None
  ```
- 规模:约 180 行;中复杂度(轮询循环叠加心跳、活动快照诊断)
- 学习价值:高 — 『按活动而非墙钟计超时』是无人值守 agent 的关键设计——允许长任务、只杀真挂死;配合 activity tracker 的诊断快照,超时报错自带 last_activity/tool 上下文。
- ▲ 文档不符:AGENTS.md:1073 宣称『3-minute hard interrupt on cron sessions』;代码实际是默认 600s 的不活动(inactivity)超时,可经 HERMES_CRON_TIMEOUT 调整、0 为无限,并非 3 分钟也非墙钟;website cron-internals.md:216 的描述才与代码一致。

### 2.16 文档-代码冲突汇总(独立冲突条目,共 54 条)

以下为矿工在能力点之外单独记录的全部独立冲突(压缩为单句;完整版含上下文见 JSON);与能力点绑定的 ▲ 条目见各自目录项。

1. AGENTS.md:351-353:'The core loop is inside run_conversation() — entirely synchronous, with interrupt checks, budget tracking, and … → **实际**:_budget_grace_call 仅在 agent/agent_init.py:892 被初始化为 False,全仓库(含 _budget_exhausted_injected)没有任何将其置 True 的代码——grace-call 分支永远不可达,是死…(`agent/agent_init.py:892`)
2. AGENTS.md:328:'max_iterations: int = 500, # tool-calling iterations (shared with subagents)' → **实际**:AIAgent.__init__(run_agent.py:446)与 init_agent(agent/agent_init.py:470)的默认值都是 90(`run_agent.py:446`)
3. website/docs/developer-guide/agent-loop.md:124:中断时'No partial response is injected into conversation history' → **实际**:redirect 路径显式把已展示的部分响应降级为 checkpoint 注入 messages(api_content 侧车,conversation_loop.py:164-197)(`agent/conversation_loop.py:183`)
4. website/docs/developer-guide/agent-loop.md:108:'API requests are wrapped in _interruptible_api_call() which runs the actual HTTP c… → **实际**:主循环默认永远优先流式路径 _interruptible_streaming_api_call——即使没有任何流式消费者——以获得 90s 陈旧流检测/60s 读超时(`agent/conversation_loop.py:2348`)
5. website/docs/developer-guide/agent-loop.md:133-134:'Multiple tool calls → executed concurrently via ThreadPoolExecutor → **实际**:实际调度由 _plan_tool_batch_segments 决定:按只读工具、文件目标不重叠、MCP opt-in 把批次切成 parallel/sequential 段,混合批按发出顺序逐段执行(execute_tool_calls_segmented)…(`run_agent.py:7617`)
6. context-compression-and-caching.md:396 描述 prompt cache 用 "system_and_3" 布局:断点1=system prompt,断点2-4=最后3条非 system 消息的滚动窗口 → **实际**:prompt_caching.py 默认布局是 静态 system 前缀 + system 尾 + 最后2条消息(4 断点),仅在无静态前缀时才回退到 system+末3条(`agent/prompt_caching.py:1`)
7. provider-runtime.md:180 fallback activation flow 写 "Returns False immediately if already activated or not configured" → **实际**:try_activate_fallback 不在 _fallback_activated 为真时早退,而是靠 _fallback_index >= len(_fallback_chain) 判定多级链是否耗尽并逐条推进——文档描述的是旧的单对 fallback…(`agent/chat_completion_helpers.py:1764`)
8. provider-runtime.md:196 写辅助任务 "use their own independent provider auto-detection chain",暗示副任务用独立探测链选 provider → **实际**:_resolve_auto Step 1 默认直接用主 provider+主模型跑副任务,openrouter→nous→custom→api-key 探测链仅在主模型无可用 client 时才作为兜底启用(`agent/auxiliary_client.py:5437`)
9. website/docs/user-guide/configuration.md:2303 的表格称 AGENTS.md 作用域为 'Recursive directory walk',:2311 进一步称 '**AGENTS.md** is hierarch… → **实际**:启动时 _load_agents_md 只读 cwd 顶层('AGENTS.md — top-level only (no recursive walk)')(`agent/prompt_builder.py:2062`)
10. website/docs/user-guide/configuration.md:2313:'All loaded context files are capped at `context_file_max_chars` characters (default… → **实际**:context_file_max_chars 默认是 null:无显式配置时上限由 _dynamic_context_file_max_chars 按模型窗口动态缩放(floor 20,000、ceiling 500,000 字符),20K 只是下限而非默认值(`agent/prompt_builder.py:1309`)
11. AGENTS.md:1140:'The ONLY time we alter context is during context compression.'(Prompt Caching Must Not Break 政策) → **实际**:严格说改写已发送历史的路径有三条:批量 compress()、proactive prune_tool_results_only(独立于压缩阈值的无 LLM 剪枝)、micro-compaction(每 N 轮改写一次)(`agent/context_compressor.py:3096-3099`)
12. README.md:26 与 website/docs/index.mdx:123 宣称闭环学习包含 'FTS5 session search with LLM summarization for cross-session recall' → **实际**:session_search 工具明确零 LLM:模块 docstring 写 'No LLM calls anywhere — every shape returns actual messages from the DB',并注明重构时移除了 summar…(`tools/session_search_tool.py:23`)
13. agent/memory_manager.py:365-368 docstring 宣称 'Orchestrates the built-in provider plus at most one external provider. The builtin p… → **实际**:代码库中不存在任何 name=='builtin' 的 MemoryProvider 实现(`agent/agent_init.py:1707-1710`)
14. README.md:19 'nudges itself to persist knowledge' 与 README.md:26 'Agent-curated memory with periodic nudges' 暗示会话内周期性提醒 → **实际**:nudge 从不注入对话:turn_context.py:588 注释 'Preserve the original user message (no nudge injection).'(`agent/turn_context.py:588`)
15. README.md:26 'Autonomous skill creation after complex tasks'(暗示按任务复杂度触发) → **实际**:技能 review 触发条件是纯工具迭代计数:conversation_loop.py 每次工具迭代递增 _iters_since_skill,达到 creation_nudge_interval(默认 10)即触发,与任务是否『复杂』无语义判断(`agent/turn_finalizer.py:700-704`)
16. website/docs/user-guide/security.md:101 — hardline 模式表『kept in sync with tools/approval.py::UNRECOVERABLE_BLOCKLIST』 → **实际**:代码中不存在 UNRECOVERABLE_BLOCKLIST 符号(grep 全仓 0 命中)(`tools/approval.py:434`)
17. website/docs/user-guide/security.md:665 — 开启 security.allow_private_urls 后『web tools, the browser, vision URL fetches, and gateway… → **实际**:代码中云元数据 IP/主机名与整个 link-local 段(_ALWAYS_BLOCKED_IPS / _ALWAYS_BLOCKED_NETWORKS 含 169.254.0.0/16)在 allow_private_urls 开启时仍无条件封禁:is_s…(`tools/url_safety.py:488`)
18. website/docs/user-guide/security.md:654 — 『DNS failures are treated as blocked (fail-closed)』 → **实际**:is_safe_url 对 DNS 失败有代理豁免:当 HTTPS_PROXY 等代理变量已配置且主机名不是字面 IP 时,getaddrinfo 失败会 return True 放行、把解析委托给代理(『proxy configured, allowing …(`tools/url_safety.py:466-472`)
19. website/docs/developer-guide/tools-runtime.md:91 — 『Check results are cached per-call — if multiple tools share the same check_fn,… → **实际**:check_fn 结果实际有跨调用的 30 秒 TTL 缓存(_CHECK_FN_TTL_SECONDS=30.0)且按 multiplex profile 维度隔离,另有 60 秒 last-good 宽限窗口:上次成功 60s 内的失败被判定为 flake…(`tools/registry.py:216-220`)
20. website/docs/user-guide/features/tools.md:88:『One persistent container ... The container is stopped and removed on shutdown.』 → **实际**:默认 persist_across_processes=True 时 DockerEnvironment.cleanup() 对容器是刻意的 no-op:容器在 Hermes 进程退出后继续运行(容器内后台进程存活),只在下次 Hermes 启动时由 reap…(`tools/environments/docker.py:1961`)
21. AGENTS.md:243 目录树注释:『tools/environments/ # Terminal backends (local, docker, ssh, modal, daytona, singularity)』只列 6 种 → **实际**:代码实际含 8 个环境类:除注释列出的 6 种外还有 vercel_sandbox.py(VercelSandboxEnvironment,TERMINAL_ENV=vercel_sandbox)和 managed_modal.py(ManagedModalE…(`tools/terminal_tool.py:1764`)
22. 工具描述与 tools-reference 均称 terminal 输出会返回给模型,未提及任何截断恢复手段(README/website 无 full_output_path 记载) → **实际**:前台命令输出超过 tool_output.max_bytes 时按 40/60 头尾窗口截断,同时完整流被 tee 到 ~/.hermes/cache/terminal-output/out-*.log(5MB 上限),结果 JSON 附 output_tot…(`tools/environments/base.py:1220`)
23. website/docs/developer-guide/session-storage.md:144 声称 'Current schema version: **23**',迁移表也止于 v23 → **实际**:代码基线 SCHEMA_VERSION = 25(v24/v25 未见于文档迁移表)(`hermes_state_common.py:167`)
24. session-storage.md:177-190 声称写竞争用 'Short SQLite timeout (1 second)'、'up to 15 retries',并引用常量 _WRITE_MAX_RETRIES = 15 → **实际**:代码中不存在 _WRITE_MAX_RETRIES(`hermes_state.py:1927`)
25. session-storage.md:13/28 声称 state.db 无条件运行 'SQLite, WAL mode'、'WAL mode for concurrent readers + one writer' 是关键设计决策 → **实际**:apply_wal_with_fallback 在 WAL 不兼容文件系统上降级 DELETE(`hermes_state.py:674`)
26. website/docs/reference/slash-commands.md:45 把 /undo 描述为 'Remove the last user/assistant exchange'(移除) → **实际**:底层 rewind_to_message 是软删除:行保留在库中翻成 active=0,可经 restore_rewound/include_inactive=True 恢复,并累加 sessions.rewind_count 审计计数(`hermes_state.py:7613`)
27. website/docs/reference/slash-commands.md:214:"When a prefix is ambiguous (matches multiple commands), the first match in registry … → **实际**:cli.py 的前缀解析在歧义时先找精确匹配、再找唯一最短匹配(/qui→/quit),两者都不唯一时不执行任何命令,而是打印 "Ambiguous command: … Did you mean: …"(`cli.py:10506`)
28. hermes_cli/pty_bridge.py 模块 docstring(:11-16)称 PTY 桥 "POSIX-only","Native Windows ConPTY … that's tracked as a future enhancement"… → **实际**:web_server.py 已经落地了 Windows 分支:sys.platform 为 win 时 import hermes_cli/win_pty_bridge.py 的 WinPtyBridge(pywinpty/ConPTY,184 行,与 Pty…(`hermes_cli/web_server.py:14412`)
29. website/docs/developer-guide/gateway-internals.md:86-88:第一层守卫『queues the message in `_pending_messages` and sets an interrupt even… → **实际**:base adapter 默认排队且明确不打断(日志原文 "no interrupt, will cascade after current turn")(`gateway/platforms/base.py:5736`)
30. website/docs/developer-guide/gateway-internals.md:104-108:DM 配对流程为『Admin: /pair → Gateway 发码给 admin → 新用户回码 ABC123 → Paired!』 → **实际**:不存在 /pair 命令且方向相反:未授权用户 DM 时 gateway 自动 generate_code 把码发给该用户,并提示『Ask the bot owner to run: hermes pairing approve <platform> <cod…(`gateway/run.py:14496`)
31. website/docs/developer-guide/gateway-internals.md:78:会话键示例 `agent:main:telegram:private:123456789` → **实际**:键的 chat_type 槽取自 source.chat_type,DM 分支判定条件是 `if source.chat_type == "dm":`,生成 `agent:main:telegram:dm:<chat_id>`,从不产生 "private"(`gateway/session.py:1103`)
32. website/docs/developer-guide/gateway-internals.md:9:『connects Hermes to 20+ external messaging platforms』 → **实际**:实测 plugins/platforms/ 有 22 个插件平台目录(全部 kind: platform),gateway/platforms/ 另有 9 个内置适配器(signal、weixin、bluebubbles、qqbot、yuanbao、whats…(`gateway/config.py:272`)
33. AGENTS.md:986-989:"By default the parent waits for the child's summary before continuing its own loop. With `background=true`, Her… → **实际**:模型侧 background 参数已 DEPRECATED/IGNORED(schema 描述明说 'Setting this has no effect'),注册 handler 用 _model_background_value 强制:顶层(depth==…(`tools/delegate_tool.py:3889`)
34. AGENTS.md:993:"**Single:** pass `goal` (+ optional `context`, `toolsets`)" → **实际**:DELEGATE_TASK_SCHEMA 的 properties 只有 goal/context/tasks/role/background,没有 toolsets(`tools/delegate_tool.py:2967`)
35. AGENTS.md:1005:role="orchestrator" "bounded by `delegation.max_spawn_depth` (default 2)" → **实际**:代码默认 MAX_DEPTH = 1('flat by default'),_get_max_spawn_depth 无配置时返回 1,因此默认配置下 child_depth(1) < max_spawn(1) 不成立,role=orchestrator 被静…(`tools/delegate_tool.py:127`)
36. AGENTS.md:1012-1013:"background `delegate_task` is detached from the current turn but still process-local"(暗示无任何跨重启机制) → **实际**:后台委派的 dispatch 与完成事件持久化在 state.db 的 async_delegations 表:重启后 restore_undelivered_completions 恢复未投递完成事件(打 restored=True 强制所有权校验),rec…(`tools/async_delegation.py:363`)
37. website/docs/user-guide/features/mixture-of-agents.md:55:参考模型 "receive only the conversation's user/assistant text — not the Herme… → **实际**:_reference_messages 的 advisory view 刻意保留工具轨迹:assistant 的 tool_calls 渲染为 '[called tool: name(args)]' 文本,tool-role 结果头尾截断后以 '[tool r…(`agent/moa_loop.py:1012`)
38. website/docs/user-guide/features/delegation.md:211:"Background delegations (`delegate_task(background=true)`) are watched by a ...… → **实际**:background 参数对模型已无效(DEPRECATED / IGNORED,tools/delegate_tool.py:3854-3864),后台化由 harness 按调用者深度自动决定(`tools/delegate_tool.py:3857`)
39. AGENTS.md:1073 宣称『**3-minute hard interrupt** on cron sessions — runaway agent loops cannot monopolize the scheduler.』 → **实际**:代码是不活动(inactivity)看门狗:默认 600s 无活动才触发 request_hard_interrupt,经 HERMES_CRON_TIMEOUT 可调、0=无限(`cron/scheduler.py:3578`)
40. AGENTS.md:1061 宣称支持 "every monday 9am" → **实际**:parse_schedule 的 'every ' 分支只走 parse_duration,其正则 ^(\d+)\s*(m|min|...|days)$ 不接受 'monday 9am' 或 '1d at 09:00',这些 schedule 会 raise …(`cron/jobs.py:553`)
41. AGENTS.md:1082『Cron deliveries are **not** mirrored into the target gateway session』 → **实际**:默认确实不 mirror,但代码提供 per-job attach_to_session 与全局 cron.mirror_delivery 开关,开启后以 user-role 标注 turn mirror 进 origin 会话,并有 continuable …(`cron/scheduler.py:640`)
42. website/docs/user-guide/features/mcp.md('Available tools' 表)宣称 `permissions_list_open` 可 'List pending approval requests observed … → **实际**:mcp_serve.py 中 EventBridge._pending_approvals 没有任何写入代码路径(仅 __init__ 初始化为空、list 读取、respond pop(`mcp_serve.py:423`)
43. tui_gateway/synthetic_turn.py 声称其机制对应设计文档 ``docs/desktop/2026-07-04-dashboard-process-isolation-PRD.md``,暗示 turn isolation 有正式文档 → **实际**:仓库中不存在 docs/desktop/ 目录,该 PRD 文件不在树内(`tui_gateway/synthetic_turn.py:3`)
44. website/docs/developer-guide/acp-internals.md 'Key implementation files' 声称 ACP 适配器的关键实现为 entry/server/session/events/permissions/… → **实际**:acp_adapter/edit_approval.py(338 行,pre-execution 编辑审批:ContextVar 绑定 per-run requester、EditProposal diff 预览、.env/id_rsa 等敏感文件永不自动放行…(`acp_adapter/edit_approval.py:38`)
45. tools/web_tools.py 模块 docstring(20-22 行)宣称:'LLM Processing: Uses OpenRouter API with Gemini 3 Flash Preview for intelligent conten… → **实际**:web_extract 实际是零 LLM 的确定性 truncate-and-store:头 75%+尾 25% 截窗、全文落盘、footer 指引 read_file 翻页(`tools/web_tools.py:527`)
46. website/docs/reference/tools-reference.md:11 宣称视频工具共 3 个:'3 video tools (`video_generate`, `xai_video_edit`, `xai_video_extend`)' → **实际**:tools/flux3_video_tool.py 顶层 registry.register 另注册了 6 个 bfl toolset 工具:bfl_flux3_text_to_video、bfl_flux3_image_to_video、bfl_flux3_…(`tools/flux3_video_tool.py:1186`)
47. tools/image_generation_tool.py 模块 docstring(第 5 行)称该模块 'Provides image generation via FAL.ai',并把架构描述为 FAL 模型目录 → **实际**:image_generate 现在优先经 agent/image_gen_registry 派发到插件后端(openai、xai、krea、openrouter、deepinfra、openai-codex),还有 managed Krea 模型级路由(`tools/image_generation_tool.py:1284`)
48. docs(website/docs/user-guide/features/tool-gateway.md 等)描述了托管网关可用的工具面,但从未提及媒体上传机制 → **实际**:tools/managed_tool_gateway.py 实现了完整的三步媒体上传协议:POST presign(声明 contentType+contentLength)→ 字节直传对象存储(绕过网关请求上限,支撑 50MB 视频)→ 工具参数携带绑定 p…(`tools/managed_tool_gateway.py:449`)
49. docker-compose.yml:19-20 注释宣称镜像默认 ENTRYPOINT 是 `["/init", "/opt/hermes/docker/main-wrapper.sh"]`("or let docker use the image's de… → **实际**:Dockerfile 实际为 `ENTRYPOINT [ "/opt/hermes/docker/entrypoint-dispatch.sh" ]` + `CMD [ ]`(dispatcher 在 PID-1 场景才转交 /init)(`Dockerfile:456`)
50. website/docs/getting-started/updating.md:28 宣称 `hermes update` 的 Git pull 步骤 "pulls the latest code from the `main` branch and upd… → **实际**:仓库根本没有 .gitmodules,hermes_cli/update_cmd.py 与 main.py 中不存在任何 submodule 处理代码(`hermes_cli/update_cmd.py:3965-3966`)
51. website/docs/user-guide/configuration.md:1727 宣称支持语言为 "en, zh, zh-hant, ja, de, es, fr, tr, uk, af, ko, it, ga, pt, ru, hu"(共 16 种… → **实际**:代码 SUPPORTED_LANGUAGES 为 17 种,额外包含 "ar"(阿拉伯语),locales/ar.yaml 存在且 i18n 别名表覆盖 ar-sa/ar-eg 等地区码(`agent/i18n.py:43-46`)
52. AGENTS.md:269 宣称测试套件规模为 "Pytest suite (~17k tests across ~900 files as of May 2026)" → **实际**:基线 commit 实测 `find tests -name 'test_*.py' | wc -l` = 2667 个文件、`def test_` 计数 23639 个(`AGENTS.md:269`)
53. website/docs/reference/cli-commands.md:769-777 将 doctor 的完整用法记为 `hermes doctor [--fix]`,选项表仅含 --fix → **实际**:doctor 还接受 `--ack <advisory-id>` 快路径(持久化安全公告确认并跳过其余诊断,未知 ID exit 2)(`hermes_cli/doctor.py:717-720`)
54. website/docs/getting-started/updating.md:30 宣称依赖步骤 "runs `uv pip install -e \".[all]\"` to pick up new or changed dependencies" → **实际**:首选路径确为 `-e .[all]`,但实际是 `_install_python_dependencies_with_optional_fallback`:失败后降级为 base `-e .` + 逐 extra 重试并汇报跳过项,Termux 下自动改用 `…(`hermes_cli/main.py:8490-8499`)

### 2.17 全局观察(跨子系统)

1. **恢复阶梯 + 一次性守卫**是全仓最一致的工程签名:空响应、截断、限流、OAuth 失效、流中断、更新失败、平台断连——每种失败都有专用有界重试阶梯,并用一次性布尔守卫防死循环(`agent/turn_retry_state.py:43`、`hermes_cli/update_cmd.py` 等)。
2. **prompt cache 字节级稳定**是贯穿性设计约束(api_content 侧车、冻结记忆快照、缓存感知斜杠命令、压缩滞回),AGENTS.md 将其列为最高设计红线,代码与宣称一致——这是少数『文档与代码高度一致』的主题。
3. **单体巨文件 + 循环依赖 + 函数内延迟 import** 是快速演化的代价;全仓约 30 个 >2000 行的 Python 文件承载了核心机制,学习必须以机制为单位切片,而非以文件为单位。
4. **安全层出乎意料地厚**:命令审批、SSRF DNS 钉扎、威胁模式扫描、secret 卫生、供应链钉死、注入围栏散布在每个子系统,而官方 README 只轻描淡写提 security 一页——◇ 类能力点近三分之一与安全相关。



---

## 三、学习方案

### 3.1 组织方式与理由

**按"机制"分轮,不按目录分轮。** 理由:测绘显示本仓库是单体演化(巨文件 + 循环依赖 + 函数内延迟 import),同一机制的代码散在根目录巨文件、agent/、tools/、gateway/ 多处(例:委派机制横跨 tools/delegate_tool.py、agent/subagent_lifecycle.py、run_agent.py);按目录读会把一个机制切碎在多轮里。因此每轮圈定一个**机制簇**,把它涉及的所有文件(含对应 tests/ 作为行为规格)一次学透。

**分层定义(台账 layer 列,状态可翻译为"学到什么程度"):**

| 层 | 含义 | 完成标准 |
|---|---|---|
| L1 机制精读 | harness 核心机制实现 | 能讲清问题/实现/设计理由/取舍,能凭笔记重实现同等机制 |
| L2 结构级理解 | 支撑性/外围代码 | 能画出结构与数据流,能定位任意功能落点,不逐行读 |
| L3 知悉用途 | 内容型源文件(技能文档、翻译、示例、文档站) | 编目:知道它是什么、为何存在、何时查阅 |
| L4 有理由排除 | 生成物/锁文件/二进制/媒体/贡献者数据 | 台账记录排除理由,不学习 |
| LT 行为规格参照 | tests/、tests-js/、*.test.ts(x) | 随对应 L1/L2 模块按需查阅,作为行为规格,不独立精读 |

### 3.2 覆盖台账与校验数

台账 `data/ledger.tsv`(path/kind/lines/layer/round/status),由 `scripts/assign_layers.py` 按显式规则生成(**首条匹配生效,不匹配即报错**,保证无黑洞);`scripts/verify_ledger.py` 对基线 checkout 复核:文件集合一致 + 每文件行数复算一致 + 分层加总 = 全仓总行数。本轮实测输出:

```
OK baseline=863e31318 files=8530 total_lines=2608452
  L1: files=412  lines=382,770   (机制精读)
  L2: files=2282 lines=811,076   (结构级理解)
  L3: files=1895 lines=602,085   (知悉用途)
  L4: files=560  lines=55,902    (有理由排除)
  LT: files=3381 lines=756,619   (测试=行为规格参照)
  SUM == repo total: 2,608,452
```

每轮结束:把该轮覆盖文件的 status 从 `R1-inventoried` 更新为 `R<n>-deep-read` / `R<n>-structure` / `R<n>-cataloged` / `excluded`,重跑校验脚本,在当轮报告报数。方案全部执行完 = 所有文件 status 非 `R1-inventoried` = 达成最终目的第 3 条;L1 全部 deep-read + 综合轮产出设计手册 = 达成第 1、2 条。

### 3.3 轮次规划(R2 起每轮一个机制簇)

| 轮 | 机制簇 | 主要文件(全集见台账 round 列) | 产出 |
|---|---|---|---|
| R2 | 回合主循环与模型接入 | agent/conversation_loop.py、run_agent.py、turn_*、iteration_budget、interrupt、oneshot、agent_init、providers/、plugins/model-providers(结构)、credential_pool、error_classifier、retry、prompt_caching、auxiliary_client、hermes_constants | notes/r2-*.md:逐机制笔记 + 最小重实现草图 |
| R3 | 工具基础设施 | tools/registry、model_tools、toolsets、schema_sanitizer、tool_output_limits、tool_result_storage、tool_search、lazy_deps、approval/write_approval、path/url/tirith 安全层、code_execution_tool(RPC)、mcp_tool 客户端 | notes/r3-*.md |
| R4 | 终端与执行环境 | terminal_tool、environments/8 后端、process_registry、daemon_pool、file_sync、browser 栈、computer_use、shell_hooks、runtime_cwd | notes/r4-*.md |
| R5 | 会话状态与持久化 | hermes_state.py、_schema/_common/_portability、checkpoint_manager、trajectory、replay_cleanup、docs/session-lifecycle.md 对照 | notes/r5-*.md |
| R6 | 记忆-技能-学习闭环 | memory_manager/provider、plugins/memory/8 后端、learn_prompt、learning_graph*、insights、curator*、skills 全链(tool/manager/hub/guard/usage/ast_audit/commands/bundles)、hermes_state_search + native/fts5_cjk、skills/ 与 optional-skills/ 编目 | notes/r6-*.md |
| R7 | 网关、调度与后台自治 | gateway/ 核心 55 文件、platforms/base + 代表适配器 3 个、cron/ 全部、background_review、outbound_webhooks、docs/chronos-*.md 对照 | notes/r7-*.md |
| R8 | CLI 与配置面 | cli.py(结构级)、hermes_cli/ 全部、mcp_serve.py、hermes_bootstrap、hermes_logging、utils | notes/r8-*.md |
| R9 | 研究管线 | batch_runner、mini_swe_runner、trajectory_compressor、toolset_distributions、datagen-config-examples、mcp-research-data 编目 | notes/r9-*.md |
| R10 | 界面层(结构级) | ui-tui、tui_gateway、acp_adapter、apps/(desktop+shared+installer)、web/、native/ 收尾 | notes/r10-*.md |
| R11 | 运维基建 + 文档全面对照 + 清账 | scripts/(测试基建/CI 分类器/发布)、docker/nix/.github、locales+i18n、website 结构、docs/ 设计文档全读;L3/L4 逐项确认;台账全绿 | notes/r11-*.md + 清账报告 |
| R12 | 综合:harness 设计手册 | 无新文件;把 R2-R11 笔记合成《同级 harness 设计蓝图》(问题域→机制选型→取舍),自证目标 1、2 | notes/handbook.md |

顺序理由:R2-R5 是内核依赖链(循环→工具→环境→状态),先建骨架;R6 学习闭环是本仓库最独特的卖点但依赖前四轮概念;R7-R8 是产品面;R9-R11 外围收敛;R12 综合。每轮工作量以 L1 3-6 万行精读 + 关联测试抽查为度,单轮可在一个会话内完成;如单轮超预算,允许在当轮报告里拆分为 a/b 两个会话并更新台账 round 列。

---

## 四、下一轮建议

**下一轮做 R2:回合主循环与模型接入。** 理由:它是其余一切机制的地基(工具、压缩、记忆、委派全都挂在循环的扩展点上),且本轮挖掘显示该区高价值密度最高(核心循环 12 条 + 提供商层 15 条能力点,过半为高价值);先学透它,后续每轮都能以"循环的哪个阶段挂进来的"定位新机制。

R2 建议打法:
1. 以 2.15 精选详述为纲,逐机制精读:外层迭代循环(`agent/conversation_loop.py:1415` 起)→ TurnContext 前奏 → 内层重试循环与 TurnRetryState → 工具批次执行(`agent/tool_executor.py`)→ 空响应恢复阶梯 → finalize_turn;然后 api_mode 分发、prompt cache 断点、凭据池、fallback 链。
2. 每机制配套跑对应测试文件(tests/agent/ 下按名索引),把测试当行为规格读;环境本轮已备好。
3. 产出 notes/r2-*.md(问题→机制→关键路径→取舍→重实现要点),更新台账 status 为 `R2-deep-read`,重跑 `verify_ledger.py` 报数。
4. 顺手核销本轮 ▲ 条目中属于 R2 范围的(grace-call 死代码、max_iterations 默认值漂移等),在笔记中定案。

无阻塞事项。若希望在后续轮次真跑模型(观察循环真实行为、验证流式/中断路径),请按 1.5 节提供任一模型 provider 凭据;纯代码学习路线不依赖它。

---

## 勘误(R8-fix,review-1 处置,2026-08-08)

本报告正文保持历史原样,以下为经复核成立的修正。修正卡:`claude/hermes-r8fix-review-1`。

1. **【M-16b】`tools-runtime.md:96` → `:91`**(正文第 599 行,能力点 19 的"宣称"锚点)。
   基线 `website/docs/developer-guide/tools-runtime.md:91 @ 863e313` 才是
   "Check results are **cached per-call**…"那一行;`:96` 是空行,`:97` 已是下一节的
   "Toolsets are named bundles of tools…"。**结论(实为 30s TTL + 60s 宽限)不受影响**,
   漂的只是锚点。同一个错锚点被三份产出继承(本报告、`reports/round-1-capabilities-full.md:939`、
   `notes/r3-90-doc-conflict-rulings.md:13,43`),四处已同改——这正是本项目反复讲的
   "同一语义多份副本"形状,出现在了自己的产出上。行号已就地改正(否则引用校验器无法通过),
   本条即是它的公开记录。

2. **【M-15】本报告首句 23 字,超出"≤20 字"**。首句为
   「重型多面 harness,核心可学,已全仓归层」(按 R8-fix 定稿的口径:剥去
   `一句话结论:` 标签与 Markdown 强调,**中文标点计入**,数到第一个句号)。
   R8-fix 把这条口径写进 CLAUDE.md 并做成脚本 `scripts/verify_report_headline.py`。
   **本报告正文首句不改写**(历史记录),脚本里以"历史豁免"显式列出并指回本条;
   该名单就此封闭,R8-fix 之后的报告一律按 ≤20 执行。
   合规写法示例:「重型 harness,核心可学,全仓已归层」(18 字)。

3. **【M-25】本报告未受影响,但相关制度已恢复**:"`R1-inventoried` 剩余文件数 / 行数"
   自 R7 起停报,R8-fix 已恢复为每轮必报项并写进 CLAUDE.md。当前值见
   `reports/round-8-fix-review-1.md`。
