# R5 报告:会话状态与持久化

**一句话结论:记忆侧学透,定案二十条。**

- 基线:`863e31318`(只读,工作树零改动,校验一致)
- 本轮机制簇:会话状态与持久化(R4 报告建议的 R5,含 R2 并入本轮的上下文工程/压缩线)
- 分支:`claude/hermes-agent-round-5-ogproh`(从合并后的 main 起);R4 已作 PR #4 合入 main
- 本轮实际执行模型:**claude-opus-4-8**(依据:系统提示"Model identity"节声明 `claude-opus-4-8`,
  会话中途用户 `/model claude-fable-5` 切换后由 system-reminder 确认切至 `claude-fable-5`;两段均无独立
  自证手段,如实并陈)
- 交付:底稿 9 篇 + 成品章 1 章 + 定案 20 条 + 测试 1,360 用例 + 台账 status 更新并重跑校验

---

## 1. 台账报数(三项校验全过)

`assign_layers.py` 加 R5 显式规则(吸纳跨轮桶文件,理由见 §范围);`verify_ledger.py` 实测:

```
OK baseline=863e31318 files=8530 total_lines=2608452
  L1: files=412  lines=382,770
  L2: files=2282 lines=811,076
  L3: files=1895 lines=602,085
  L4: files=560  lines=55,902
  LT: files=3381 lines=756,619
  SUM == repo total: 2,608,452   ✓ (文件集一致 + 行数复算一致 + 分层加总 = 全仓总行数)
```

本轮 status 更新:**R5-deep-read 31 文件 / 46,104 行**(27 个 R5-round 文件 + 4 个从 R4-structure 升级
深读的文件)。累计已学:R2(118)+ R3(35)+ R4(35)+ R5(31)= **219 文件**,R1-inventoried 降至 8311。

**R4-structure 四文件处置(卡片要求)**:`local.py`、`browser_tool.py`、`shell_hooks.py`、`desktop_ui.py`
本轮由清账子代理精读到 L1,status 从 `R4-structure` 升为 `R5-deep-read`,**R4-structure 归零**。理由:
R5 的会话状态与执行环境的 local/browser 后端强相关(env 净化单一权威、SSRF 接线),顺势补齐欠账最经济;
结论记入 `notes/r5-60`。

**R5 范围调整说明**:以台账 `round=R5`(17 文件)为基础,显式吸纳——`hermes_state_search`(原 R6,FTS5
被本卡点名)、`session_search_tool`/`checkpoint_manager`/`memory_tool`(原 R3-R4 桶)、`memory_manager`/
`memory_provider`/`session_activity`(原 R3-R7 桶)、`native/fts5_cjk` 分词器本体(原 R10)。共 27 文件 /
38,349 行。增删已写进 `scripts/assign_layers.py` 显式规则并重生成台账(status 列保留)。

## 2. 底稿与成品章清单

**底稿 `notes/`(9 篇,凡断言紧跟 `路径:行号 @ 863e313` + 代码原文)**:
- `r5-01-state-schema-portability`(主线:声明式 schema 调和 + PK 幂等愈合 + 导入六防线 + 活动心跳契约)
- `r5-02-hermes-state-sessiondb`(子代理:八层耐久性防御 / 多进程写协议 / 会话生命周期 / 压缩落库两路径)
- `r5-10-fts5-session-search`(子代理:三索引分工 + 触发器标记闸 + 四形态 + CJK 分词器)
- `r5-20-context-compression`(子代理:触发去噪 + 确定性剪枝滞回 + 交接摘要 + 角色交替 + 锁与栅栏)
- `r5-30-prompt-context-engineering`(子代理:系统提示三层 + 项目文件注入 + ContextEngine 双钩子)
- `r5-40-checkpoint-memory`(子代理:文件检查点 + 内建/外部记忆 + 围栏防注入 + 写审批门禁)
- `r5-60-r4-structure-cleanup`(子代理:local.py/browser_tool/shell_hooks/desktop_ui 补齐 L1)
- `r5-90-doc-conflict-rulings`(定案 20 条)+ `r5-95-tests`(测试记录)

主线亲读 `r5-01` 与 4 个小文件(session_activity/message_content/hermes_state_schema/portability),并对
每篇子代理底稿逐条抽查关键行号——`should_compress`(compressor:2629)、压缩锁 rationale
(conversation_compression:2325)、记忆围栏(memory_manager:347)、写审批门禁(memory_tool:941)、
三索引权威元组(hermes_state:9362)、schema 调和(schema:294)、Windows 子类不存在(base:645 + grep 零
命中)、checkpoint 每迭代去重(conversation_loop:1426)等**均逐字命中**;全部定案由主线亲自复核。

**成品章 `chapters/r5-session-state-and-persistence.md`**(新可读性标准,GitHub 可渲染 Mermaid):五块
(会话库 / 压缩 / 检索 / prompt 装配 / 长期记忆)+ 检查点;场景开场、术语锚定、事故讲成故事、地图与
代码出入融进叙述。

## 3. 行为规格测试(1,360 用例全过,1 例环境敏感)

官方 `run_tests.sh`(密封环境、per-file 隔离、8 workers)本轮七批:

- state 核心 21 文件 / 320(WAL 回退矩阵、malformed 修复阶梯、压缩锁 × 写耐心、可写性预检)
- 压缩批一 20 文件 / 246 + 批二 18 文件 / 96(anti-thrash、concurrent_fork、worker 隔离、tail_anchor)
- 上下文/prompt/记忆/检索/检查点 25 文件 / 395
- 残留 6 文件 / 42 + 零化库/慢日志 2 文件 / 9
- 记忆/审批/scrubber + 压缩规格 + R4 清账 23 文件 / 252

**合计 115 文件 / 1,360 passed / 1 failed。** 唯一失败
`test_state_db_malformed_repair.py::test_repair_rebuilds_stale_btree_indexes` 是**测试断言吃了 SQLite
版本差异**(本机 3.45.1 的 `integrity_check` 先吐逐行 `missing from index`、汇总行 `wrong # of entries`
排第 11,被 `_db_opens_cleanly` 的 `problems[:3]` 截掉)——主线手动复现确认**修复机制本机全闭环**
(检出损坏 → Strategy 0.5 REINDEX → 修后干净),非 hermes-agent 代码缺陷,不改基线。详见 `notes/r5-95`。
顺带:该次运行因 #70055 门把本机 3.45.1 判为 WAL-reset 脆弱版、自动降 `journal_mode=DELETE`,实景演示了
r5-02 的 WAL 回退防御。

## 4. 文档-代码冲突定案(R5 范围,20 条)

逐条定案(证据见 `notes/r5-90`),规律与 R3/R4 一致并加深:**机制描述大体对,精确处系统性滞后**。头条:

- **证伪** `session-storage.md` 多处:schema version 23(实为 25)、写重试"最多 15 次"(实为时间预算制,
  #74478 废弃)、无条件 WAL(实为默认 + 四回退 + 漏洞版本拒 WAL)、"three triggers"(实为 9 个)。整套
  耐久性防线文档零提及——本簇最大"代码有、地图无"落差。
- **证伪** session_search "Three calling shapes"(实为四形态)、README "LLM summarization"(实为纯 DB
  检索,零 LLM)。
- **证伪** prompt-assembly 技能索引在 stable 层(实为 volatile 之首)、分钟级时间戳(实为 date-only)、
  configuration.md AGENTS.md "递归合并"(实为顶层 + 渐进 hints)。
- **证伪** base.py 注释的"Windows 子类"——**该类全仓不存在**,实为 LocalEnvironment 的两个跨平台
  override + 模块级 `_IS_WINDOWS` 守卫。
- **证伪** 压缩专页七处(空占位符 vs 工具语义摘要、旧模板标题、上限 12000 vs 10000、孤儿 tool_call
  插桩 vs 剥离、"摘要窗口必须 ≥ 主模型且失败静默丢弃" vs 自动降阈+中止保原文、protect_first_n 永久 vs
  首压衰减、"Fires at 50%" 未提 75% 地板)。
- **证伪** checkpoint "每目录每回合至多一张"(实为每 API 迭代)。
- R1 标记 ▲/◇ 属本簇的全部**证实**:声明式 schema、FTS5 三索引四形态、项目上下文注入、ContextEngine
  每轮钩子、压缩五条、记忆三条。
- **正面反例**:`context-engine-plugin.md` 与代码逐条一致(与 R3 Tool Search 同类)。
- **文档内部自相矛盾三处**:three vs four shapes、AGENTS.md 两页打架、README vs memory.md 的 LLM 摘要。

L1 完成标准自评:对簇内每个机制,能讲清问题/实现/设计理由/取舍(成品章即证),能凭底稿重实现(底稿
每节末列"重实现要点");且主线复核推翻了一处子代理认知(确认 base.py 注释的 Windows 子类不存在),
体现"抽查不轻信"。达标。

## 5. 下一轮建议

**下一轮做 R6:记忆 provider 生态 + 会话检索存储层收尾**(`plugins/memory/*` 的 8 个外部后端——honcho/
mem0/hindsight/holographic/openviking/byterover/retaindb/supermemory;`hermes_state_search` 若本轮未尽的
optimize-storage 迁移深水区;`query_rewrite` 记忆检索查询改写)。理由:R5 学的是"记忆的 harness 侧编排
与防护"(MemoryManager/MemoryProvider ABC/围栏/审批),R6 自然下沉到"具体后端怎么实现召回/写入、各家
取舍如何"——R5 已把接口边界(ABC 契约 + 归一化 + 隔离)钉死,R6 是照着这张契约逐个读实现。台账
`round=R6` 现有约 40+ 文件(plugins/memory 各家 + hermes_state_search),开轮先按 R5 打法钉死范围。

打法沿用 R4/R5:主线读 ABC 契约的落地样例(如 honcho 的 sync_turn/oauth)+ query_rewrite,8 个后端用
子代理分组并行深挖;产出底稿 `notes/r6-*` + 成品章 `chapters/r6-*`(新标准)+ 测试作规格 + 定案 R6 范围
▲/◇ + 更新台账 status 为 `R6-*` 并重跑校验报数。

无阻塞事项。真跑模型仍需任一 provider 凭据(见 R1 报告 §1.5),纯代码学习与测试不依赖它;本轮 venv +
`.[dev]` 下测试 1,360 全绿(1 例 SQLite 版本敏感,已定性)。
