# R3 报告:工具基础设施 + 成品章可读性标准修订

**一句话结论:工具系统学透,三章达新标准。**

- 基线:`863e31318`(只读,工作树零改动,校验一致)
- 本轮机制簇:工具基础设施(R2 报告建议的 R3)
- 分支:`claude/hermes-agent-round-3-ogproh`(从合并后的 main 起);R2 已作 PR #2 合入 main
- 三件事同批交付:① CLAUDE.md 成品章可读性标准全文修订;② 补写 r1 全景章 + 按新标准重写 r2 章 +
  新写 r3 章;③ 执行 R3 机制簇(底稿 6 篇 + 成品章 + 定案 + 测试)。

---

## 1. 成品章可读性标准修订(CLAUDE.md,对本轮起所有章生效)

按本卡验收标准,把双产出制度里的成品章标准全文更新:**目标读者画像**从"合格工程师"收紧为"有多年后端
经验、没读过本仓库、不熟 LLM provider 生态与 Python 异步生态的工程师"。六条硬标准:术语锚定(专名首次
出现给一句话中文解释)、先场景后机制(每个机制以一次具体请求/故障开场)、双读法(快读 TL;DR + 精读路径
各自自洽)、事故讲成故事(issue 教训讲成因果经过、编号只作溯源)、可读性不牺牲可验证性(仍配行号、图可
渲染)、独立可读。附推荐骨架(TL;DR / 从一个场景说起 / 全景 / 逐机制 / 可迁移原则 / 地图与代码出入 / 延伸)。

## 2. 三章成品(全部达新标准,GitHub 可渲染 Mermaid)

- **`chapters/r1-what-is-hermes-agent.md`**(全景开篇章,《设计蓝图》第一章):hermes 是什么、全仓地图
  (8530 文件/五层台账)、为什么值得逐条读透、各章阅读路线。素材复用 R1 报告与台账,达新标准。
- **`chapters/r2-turn-loop-and-model-access.md`**(按新标准重写):加 TL;DR、每个机制场景开场、术语锚定
  (turn/tool_calls/provider/prompt cache/prefill 等)、事故讲成故事、5 张 Mermaid 图。
- **`chapters/r3-tool-infrastructure.md`**(本轮新写):工具系统四大块——窄腰、安全防线、execute_code、
  schema 经济,3 张 Mermaid 图。

## 3. 台账报数(三项校验全过)

`assign_layers.py` 加 R3 显式规则;`verify_ledger.py` 实测:

```
OK baseline=863e31318 files=8530 total_lines=2608452
  L1: files=412  lines=382,770
  L2: files=2282 lines=811,076
  L3: files=1895 lines=602,085
  L4: files=560  lines=55,902
  LT: files=3381 lines=756,619
  SUM == repo total: 2,608,452   ✓ (文件集一致 + 行数复算一致 + 分层加总 = 全仓总行数)
```

本轮 status 更新:**R3-deep-read 32 文件**、**R3-structure 3 文件**(mcp_oauth*),R3 覆盖 35 文件 / 31,533 行。
累计已学:R2(118 文件)+ R3(35 文件),R1-inventoried 降至 8377。

**R3 范围说明**:显式列举 registry/model_tools/toolsets、schema 清洗、三层输出限长、tool_search、
lazy_deps/fuzzy_match、审批与安全层(approval/url_safety/threat_patterns/tirith/skills_guard/osv_check/
tool_guardrails)、execute_code + env 洗净、mcp 客户端侧(mcp_tool/oauth/watchdog/schema_cache)。
`tool_executor.py`/`tool_dispatch_helpers.py`(工具批次执行)R2 已覆盖,不重复。`patch_parser.py` 归 R4
(属 file 工具)。

## 4. 底稿与成品章清单

**底稿 `notes/`(6 篇,凡断言紧跟 `路径:行号 @ 863e313` + 代码原文)**:
`r3-01-registry-dispatch`(窄腰:AST 自注册/check_fn TTL+宽限/插件覆盖授权/分发管线)、
`r3-10-approval-security`(分层审批/SSRF 双层/威胁扫描/tirith/工具护栏/写入审批)、
`r3-20-schema-output-toolsearch`(多后端 schema 清洗/三层输出限长/渐进披露/lazy_deps/fuzzy_match)、
`r3-30-execute-code-mcp-client`(execute_code 三态 RPC/环境洗净/审批传播 + MCP 七道防护)、
`r3-90-doc-conflict-rulings`(定案)、`r3-95-tests`(测试运行记录)。

其中 4 篇由子代理并行深挖产出,主线逐条抽查关键行号(schema:382、tool_result:113、code_execution:703、
env_passthrough:113、mcp_tool:5519 等均逐字命中);r3-01 与全部定案由主线亲自精读复核。

## 5. 行为规格测试(589 用例全过)

官方 `scripts/run_tests.sh`(密封环境、per-file 子进程隔离)跑 R3 代表性测试:hardline 183、url_safety 61、
tool_search 30、schema_sanitizer 19、tool_result_storage 26、fuzzy_match 45、threat_patterns 23、
tool_guardrails 7、code_execution/env_passthrough/mcp_security/osv/write_approval/skills_guard/tirith 167、
mcp_schema_cache/stdio_watchdog 13……**合计 589 passed / 0 failed**。hermes-agent 保持基线、零改动。

## 6. 文档-代码冲突定案(R3 范围,10 条 + 2 新发现)

对 R1 标记的 ▲/◇ 中属本簇的逐条定案(证据见 `notes/r3-90`),无一条被推翻为"文档完全正确":

- **▲ 全证实/修正**:安全文档的 `UNRECOVERABLE_BLOCKLIST` 符号**代码里不存在**(真实是 `HARDLINE_PATTERNS`),
  但机制描述正确;"允许私网"开关不解封云元数据/链接本地段(始终封);DNS 失败仅未配代理时 fail-closed;
  check_fn 实为 30s TTL + 60s 宽限。
- **◇ 有证实有证伪**:schema 多后端清洗 + 参数名往返未见于文档(证实,仅 Gemini-adapter 侧一句模糊提及);
  三层输出限长(修正:第一层已文档化、二三层未见);execute_code(证实:README 属实但严重低估机制深度);
  MCP 客户端侧(修正:命名/动态注册已文档化,但描述注入扫描、恶意包预检、可疑配置过滤、孤儿清理、跨源
  鉴权剥离等 5 道安全防护未见于文档——本簇最大落差);**Tool Search 渐进披露证伪**——它有一整页专门且
  比代码注释更全的文档。
- **R2 新发现 2 条**:fuzzy_match docstring 自称"9-strategy"却只列 8 条;model_tools.py:579 内联注释的 tool_search
  阈值(10% vs 实际 5%,且已不再 gate 激活)双重陈旧。均为源码内注释漂移,记录在案。

L1 完成标准自评:对簇内每个机制,能讲清问题/实现/设计理由/取舍(成品章即证),能凭底稿重实现(底稿每节
末列"重实现要点"),达标。

## 7. 下一轮建议

**下一轮做 R4:终端与执行环境**(`tools/terminal_tool.py`、`tools/environments/` 的 7 种后端 base/local/
docker/ssh/singularity/modal/daytona/vercel_sandbox、`process_registry`、`daemon_pool`、浏览器自动化栈、
computer_use、`patch_parser`)。理由:R3 学的是"工具怎么注册/分发/审批",R4 自然下沉到"工具的命令到底
在哪执行、怎么在七种后端上统一抽象、后台进程/serverless 持久化/浏览器怎么驱动"——是 R3 审批层(命令要
不要拦)与 execute_code(远端 RPC 走哪个环境)的执行侧。

打法沿用 R3:主线精读环境抽象基类与本地/docker 后端,ssh/modal/daytona/vercel 与浏览器栈用子代理并行深挖;
产出底稿 `notes/r4-*` + 成品章 `chapters/r4-*`(新标准)+ 测试作规格 + 定案 R4 范围 ▲/◇(其中 tools.md:88
"容器关机即删"已在 R1 标记、待 R4 定案)+ 更新台账 status 为 `R4-*` 并重跑校验报数。

无阻塞事项。真跑模型仍需任一 provider 凭据(见 R1 报告 §1.5),纯代码学习与测试不依赖它;本轮 venv +
`.[dev]` + anthropic 下测试全绿。
