# R5-90 文档-代码冲突定案(R5 范围)

> 底稿。基线 `863e31318`。判定用语:**证实**(文档对)、**证伪**(文档错)、**修正**(方向对、表述不准)、
> **补白**(代码有、文档无)。每条附双方证据;主线均已在源码/文档上逐字复核。

## A. 会话存储(session-storage.md vs hermes_state*)

### 定案 A1 ▲ 「单文件 SQLite 会话库 + 声明式 schema 调和」——证实

R1 条目(hermes_state_schema.py:594)。查实:`_reconcile_columns` 以 SCHEMA_SQL 为唯一真源、
`:memory:` SQLite 解析期望列(零正则)、每次启动 diff+ADD(hermes_state_schema.py:292-348, 572-594);
版本链只留给数据迁移;PK 变更用每启动幂等愈合(gateway_routing #59203、session_model_usage #73823)。
文档 `session-storage.md:146` 对声明式调和的描述与代码一致。**机制证实**;但同页有三处滞后(A2-A4)。

### 定案 A2 证伪 「Current schema version: 23」

`session-storage.md:144`:"Current schema version: **23**",迁移表止于 v23。
代码:`hermes_state_common.py:167` `SCHEMA_VERSION = 25`;v25 = 系统提示内容寻址去重迁移
(hermes_state_schema.py:886-892)。**文档落后两版。**

### 定案 A3 证伪 「up to 15 retries」写重试

`session-storage.md:178,186`:"random jitter (20-150ms, up to 15 retries)"、`_WRITE_MAX_RETRIES = 15`。
代码:该常量**已不存在**(全仓 grep 仅命中文档);重试是时间预算制——常规 20s、转录 60s、观测 0.5s
(`_WRITE_PATIENCE_S` 等,hermes_state.py:1927-1947),2s 后抖动退到 250ms-1s。类头注释明说
次数制正是被 #74478 废掉的旧行为("A destroyed turn — even though the store is healthy and merely
busy")。**文档描述的是已废机制。**

### 定案 A4 修正 「WAL mode」无条件表述

`session-storage.md:13,28` 无条件写 "WAL mode"。代码:WAL 只是默认——NFS/SMB/FUSE/ZFS 回退
DELETE(错误指纹表 + 静默拒绝检测 + disk i/o 歧义消解,hermes_state.py:654-817);
`database.journal_mode` 操作员旋钮;SQLite 3.7.0-3.51.2(除 backports)因 WAL-reset bug
**新库拒绝 WAL**(#70055,本机 3.45.1 实测触发该门并降 DELETE,见 r5-95)。
另 `:135` "three triggers" 实为每索引 3 个 × 3 索引 = 9 个。

### 定案 A5 补白 耐久性防线整体未进文档

零化库隔离(#68474 fail-closed 隔离锁)、malformed schema 多级修复阶梯、写路径一次性 FTS 自愈、
可写性 preflight、锁安全字节访问纪律、macOS `checkpoint_fullfsync`/`synchronous=FULL`、
读写连接分离、压缩租约协议、token 记账异步队列——文档零提及。这是本簇最大的"代码有、地图无"落差
(细节见 r5-02 §1-§4)。

## B. FTS5 会话检索

### 定案 B1 ▲★ 「FTS5 三索引 session_search(discovery/scroll/read/browse)」——证实并细化

R1 条目(hermes_state_search.py:1)。三索引证实:`messages_fts`(unicode61 词级,唯一收 tool 行)、
`messages_fts_trigram`(trigram 子串,视图排除 tool 行,~2.6x 体积)、`messages_fts_cjk`
(cjk_unicode61 双字 bigram,可加载 C 扩展,#65544);`_FTS_TABLES` 权威三元组
(hermes_state.py:9362)。第四条路 LIKE 全表扫是兜底不是索引。四形态证实
(session_search_tool.py:863-873)。增量维护 = 触发器 + 高水位/进度双标记闸 + 分块 CAS 回填,
无后台线程(r5-10 §2)。

### 定案 B2 证伪 「Three calling shapes」

`sessions.md:553` "### Three calling shapes" 与 `memory.md:198` "the three calling shapes
(discovery / scroll / browse)" 均漏 READ 形态;而 `tools-reference.md:158` 写 "Four shapes" 与代码
一致——**文档内部互相矛盾**,以代码(四形态)为准。

### 定案 B3 修正 压缩后内容的可发现性(正面机制,docs 未讲)

压缩归档行(active=0, compacted=1)在 search_messages 默认**可见**、rewind 行(active=0,
compacted=0)隐藏(#38763);discovery 的"当前会话排除"对压缩轮换旧会话与就地归档行**放行**
(防"压缩即失忆",#43175 过滤压缩摘要载荷)。docs 无此语义矩阵。

## C. prompt 装配与上下文工程

### 定案 C1 ▲ 「项目上下文文件注入」——证实(三问全有答案)

R1 条目(prompt_builder.py:2189-2194)。多约定并存:`.hermes.md/HERMES.md → AGENTS.md →
CLAUDE.md → .cursorrules` **首中即停只装一种**(prompt_builder.py:2188-2196);大文件:窗口 6%
动态 cap(20K 地板/500K 顶),保 70% 头+20% 尾,中缝标记指引 read_file,告警进用户状态信道
(ContextVar 隔离);注入前过 `scope="context"` 威胁扫描,命中**整文件替换为 [BLOCKED] 占位符**,
BOM 预剥离防误杀(prompt_builder.py:66-79)。

### 定案 C2 证伪 configuration.md 的 AGENTS.md「递归+合并」

`configuration.md:2303` "Recursive directory walk"、`:2311` "if subdirectories also have AGENTS.md,
all are combined"。代码:启动仅 cwd 顶层("top-level only (no recursive walk)",
prompt_builder.py:2062);子目录版本靠 subdirectory_hints 会话中按导航**附加到工具结果**,永不进
系统提示、永不合并(subdirectory_hints.py:1-14)。developer-guide 的 prompt-assembly.md:260 表述
正确——又一处文档内部矛盾,以代码为准。

### 定案 C3 证伪 prompt-assembly.md 技能索引在 stable 层

`website/docs/developer-guide/prompt-assembly.md:31,38 @ 863e313` 把 skills prompt 列在 stable 层
*(R8-fix 修正锚点:原写 `:31,39`;`:31` 对,但 `:39` 是"memory/profile snapshots are part of the
**volatile** tier"那一条,并非被质疑对象——被质疑的"skills are part of the **stable** tier"在 `:38`。
实质断言不变,见 M-16a)*。代码:技能是运行时可变的,索引刻意放
**volatile 层之首**(system_prompt.py:503-513 长注释:放 stable 会让一次技能变更把整个缓存前缀
从索引处炸掉)。同页示例的分钟级时间戳也证伪:实际 date-only "Conversation started:"
(system_prompt.py:537-543,PR #20451)。另 `:42` 漏 `load_soul_identity` 这条腿(cron 模式
skip_context_files 下仍装 SOUL,system_prompt.py:193)。

### 定案 C4 ◇ 「可插拔 ContextEngine 每轮钩子」——证实(文档罕见地完全同步)

R1 条目(context_engine.py:215-221)。事故("第三方引擎被迫 should_compress 恒真蹭 compress 当
每轮回调")写在钩子 docstring(context_engine.py:236-241);现设计 selection(select_context,
请求前可换本请求消息)与 observation(on_turn_complete,轮后只读)两钩子,no-op 默认 + 宿主
fail-open + 恒等检查跳基类 + 空列表专防(`all([])` 陷阱)。`context-engine-plugin.md` 与代码
逐条一致——**本轮唯一"文档完全正确"的机制页**,与 R3 的 Tool Search 同类,值得记。

## D. R4 清账新发现

### 定案 D1 证伪 base.py 注释的「Windows 子类」

`base.py:645-647` 注释:"the Windows subclass override converts a native C:\Users\x cwd…"。
全仓**不存在**任何 Windows Environment 子类(grep 零命中);所指实为 `LocalEnvironment` 的两个
跨平台 override(`_quote_cwd_for_cd`/`_quote_shell_path`,local.py:1477-1484)+ 模块级
`_IS_WINDOWS` 守卫。源码注释措辞与结构不符(功能无碍)。

### 定案 D2 ◇ local.py 类 docstring 的 cwd 说法过时

`local.py:1419` "CWD persists via file-based read after each command"——现行实现与远端后端共享
stdout marker 解析(R4 已定的 #63255 统一),`_cwd_file` 仅剩 cleanup 遗产。源码内 docstring 漂移。

### 定案 D3 正面 浏览器/hooks 文档与代码一致

`browser.md` hybrid-routing 与 restrict_evaluate 段、`hooks.md` consent 三通道/timeout clamp/双
wire 格式/fail-open 语义,均与代码逐条一致,无新增冲突。

## E. 压缩(context_compressor / conversation_compression)

### 定案 E1 ▲ 「压缩触发决策:双重测量去噪 + 防抖断路器」——证实

R1 条目(context_compressor.py:2629-2634)。查实:触发同时依赖请求前粗估与 provider 返回的真实
prompt_tokens 双度量;粗估对 schema 重请求刻意高估,单靠它会"刚压完又压";防抖 + anti-thrash
断路器持久化到 sessions 行(cooldown/fallback_streak/ineffective_count,state 侧 get/set 在
hermes_state.py:3736-4006,策略在压缩引擎)。行为规格:test_compression_anti_thrash_persistence /
_recovery(本轮全过)。细节见 r5-20。

### 定案 E2 ◇ 「摘要角色交替修复与 provider 兼容护栏」——证实

context_compressor.py:6661-6668 附近:摘要作为合成消息插回后满足 Mistral 严格交替模板(模板跳过
tool 消息)、Anthropic/Bedrock 兼容。见 r5-20。

### 定案 E3 ◇ 「结构化 handoff 摘要生成」——证实

context_compressor.py:3749-3752 附近:逐字保住用户最新未完成请求、防已完成写成待办、不翻译用户
语言、不泄密钥、ghost-skill 防护。行为规格 test_compress_focus / test_compressed_summary_metadata
/ test_context_compressor_summary_continuity(全过)。见 r5-20。

### 定案 E4 ▲ 「确定性工具结果剪枝 + proactive prune 的 prompt-cache 滞回」——证实

context_compressor.py:2886-2890 附近:大窗口模型 50% 阈值少触发,旧工具输出每轮重发;独立的无
LLM 剪枝路径 + 滞回保 prompt cache。ContextEngine ABC 的 `prune_tool_results_only` 默认安全 no-op
(context_engine.py:194-211)即其插件面。见 r5-20。

### 定案 E5 ▲ 「压缩执行基础设施:锁/栅栏/超时/in-place 落库」——证实

conversation_compression.py:887-889 附近。state 侧已由 r5-02 独立证实:compression_locks 租约表
(TTL + 结构化 holder + 死进程即时回收 + 只按 holder 续约)、`publish_compression_child` 单事务
原子发布(读者要么见活父要么见完整子)、`archive_and_compact` 就地软归档、非持有写者 5s 短等后拒
(#75083)。行为规格 test_hermes_state_compression_busy_retry(SLA:"A live compression lock must
delay a concurrent append, not destroy the turn")、test_compression_concurrent_fork(全过)。
见 r5-20 + r5-02 §4。

### 定案 E6 压缩专页七处过时(r5-20 §11 逐条钉死)

`context-compression-and-caching.md` 大结构与代码相符(双压缩系统、三阶段算法、in-place 单稳定 id),
但精确处七连错:①Phase-1 替换文本——文档说空占位符 "[Old tool output cleared…]",代码是工具语义
一行摘要,`_PRUNED_TOOL_PLACEHOLDER` 只作幂等判据从不写入(测试逐字 pin "informative, not a blank
placeholder");②摘要模板标题——文档的 "Next Steps/Remaining Work" 已被 "Historical Task Snapshot/
Active State" 等替换(旧标题会被读成活指令);③摘要上限 12,000 vs 代码 `_SUMMARY_TOKENS_CEILING =
10_000`;④孤儿 tool_call——文档说"插桩",代码明确剥离(插桩被 Codex `call_id != id` 修复器静默丢
弃的事故);⑤"摘要模型窗口必须 ≥ 主模型 / 整段单次发送 / 失败静默丢弃"三点全反——实际 160K 字符
聚合上限、aux 窗口不足自动降阈、失败走中止保原文或确定性 fallback + 显式警告;⑥`protect_first_n`
"hardcoded、always preserved"——实为配置键且首压后衰减为 0(#11996);⑦首屏 "Fires at 50%" 未提
小窗口 75% 地板(同页 per-model 节反而写对了,内部不一致)。

## F. 记忆存储侧(memory_manager / memory_provider / memory_tool / checkpoint_manager)

### 定案 F1 ▲ 「MemoryProvider 插件框架 + MemoryManager 编排」——证实

R1 条目(memory_manager.py:580-584)。慢/卡死 provider 不阻塞用户回合(超时 + 线程隔离)、坏
schema 不毒化工具集、多后端协调。见 r5-40。

### 定案 F2 ◇ 「记忆上下文防注入围栏」——证实

memory_manager.py:354-361 附近:fenced block + 流式 Scrubber 防模型回显注入记忆块 + 写入威胁
扫描(threat_patterns `strict` 域,与 r5-30 §2 的三域分层一致)。见 r5-40。

### 定案 F3 ▲ 「记忆写入审批门禁 + 外部漂移/坏读守护」——证实

memory_tool.py:941-947 附近:自治写入走 write_approval 共享框架;漂移/坏读守护防外部 MEMORY.md
被篡改后静默进系统提示。见 r5-40。

### 定案 F4 checkpoint 语义澄清 + 三处文档出入

checkpoint_manager **只存文件快照不存会话消息**(shadow git store,LLM 不可见的透明基础设施);
与 R4 的 process_registry "checkpoint"(后台进程元数据 JSON)同名不同物;与 state.db 唯一交点是
CLI /rollback 成功后顺带 /undo 一轮对齐上下文。文档出入:
- **证伪「at most one checkpoint per directory per turn」**(checkpoints-and-rollback.md:34 + 模块
  docstring 同误):`new_turn()` 唯一生产调用点在工具循环 while 体内,注释自书 "so each iteration
  can take one snapshot"——去重窗口是**一次 API 迭代**,多迭代回合可多张快照。
- **证伪 README:26「FTS5 session search with LLM summarization」**:session_search 是纯 DB 检索,
  工具 schema 自述 "no LLM calls",memory.md:190 也写 "no LLM summarization"——README 与自家文档
  直接矛盾,以代码为准(无 LLM 摘要)。
- **修正 memory.md 未提批量 shape**:代码 schema 把 operations 批量原子调用列为首选(预算只查最终
  态)且配 3 次熔断(#42405),文档还在教"先删后加"的多步流程。
- 脆弱点记录:auto_prune 不删 orphan 是靠两个调用点显式传 `delete_orphans=False`,函数默认值却是
  True——文档承诺由约定而非类型保证。

## 小结

| # | 条目 | R1 标记 | 判定 |
|---|---|---|---|
| A1 | 声明式 schema 调和 | ▲ | 证实 |
| A2 | schema version 23 | 新发现 | **证伪**(实为 25) |
| A3 | 15 次写重试 | 新发现 | **证伪**(时间预算制,#74478) |
| A4 | 无条件 WAL / three triggers | 新发现 | 修正(默认+三回退;9 触发器) |
| A5 | 耐久性防线 | 新发现 | 补白(本簇最大落差) |
| B1 | FTS5 三索引四形态 | ▲★ | 证实并细化 |
| B2 | Three calling shapes | 新发现 | **证伪**(四形态;文档内部矛盾) |
| B3 | 压缩后可发现性语义 | 新发现 | 补白 |
| C1 | 项目上下文注入 | ▲ | 证实 |
| C2 | AGENTS.md 递归合并 | 新发现 | **证伪**(仅顶层+渐进 hints;文档内部矛盾) |
| C3 | 技能索引在 stable / 分钟级时间戳 | 新发现 | **证伪**(volatile 之首;date-only) |
| C4 | ContextEngine 每轮钩子 | ◇ | 证实(文档完全同步的反例) |
| D1 | Windows 子类 | 新发现 | **证伪**(类不存在,注释漂移) |
| D2 | local.py cwd docstring | 新发现 | ◇ 源码 docstring 漂移 |
| D3 | browser/hooks 文档 | — | 正面:一致 |
| E1-E5 | 压缩五条 | ▲▲▲◇◇ | 全部证实 |
| E6 | 压缩页两处口径 | 新发现 | 修正 |
| F1-F3 | 记忆三条 | ▲◇▲ | 全部证实 |

规律(与 R3/R4 一致并加深):**机制描述大体对、精确处(版本号/默认值/数量/层位)系统性滞后**;
文档内部自相矛盾出现三次(three vs four shapes、AGENTS.md 两页打架、tools.md:88 vs :90 系 R4);
`context-engine-plugin.md` 与 Tool Search 一样是"复杂机制反而文档最全"的反例——不能假设复杂机制
必无文档。
