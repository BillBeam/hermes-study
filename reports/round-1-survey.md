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

---

## 二、harness 能力点清单

(见下文 —— 由 14 路子系统挖掘汇总,每条含:解决什么问题 / 实现落点(路径:行号)/ 规模复杂度 / 学习价值;`◇` 标记 = 代码有而官方文档没讲,`▲` 标记 = 文档宣称与代码不符。)

PLACEHOLDER_CAPABILITIES

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

PLACEHOLDER_NEXT
