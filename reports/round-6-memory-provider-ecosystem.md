# R6 报告:记忆 provider 生态与检索存储收尾

**一句话结论:八后端学透,定案十二条。**

- 基线:`863e31318`(只读,工作树零改动,校验一致)
- 本轮机制簇:记忆 provider 生态(R5 报告建议的 R6)+ query_rewrite + optimize-storage 深水区 +
  MCP OAuth 清账
- 分支:`claude/hermes-agent-round-6-ogproh`(从合并后 main 起);R5 已作 PR #5 合入 main
- 本轮实际执行模型:**claude-fable-5**(依据:会话内用户 `/model claude-fable-5` 切换后由 system-reminder
  确认;系统提示仍声明底层配置为 `claude-opus-4-8`,无独立自证手段,如实并陈——与 R5 尾段一致)
- 交付:底稿 8 篇 + 成品章 1 章 + 定案 12 条 + 测试 659 用例 + 台账 status 更新并重跑校验

---

## 1. 台账报数(三项校验全过)

`assign_layers.py` 加 R6 显式规则(记忆后端实现 .py 促升 L1);`verify_ledger.py` 实测:

```
OK baseline=863e31318 files=8530 total_lines=2608452
  L1: files=436  lines=404,894
  L2: files=2258 lines=788,952
  L3: files=1895 lines=602,085
  L4: files=560  lines=55,902
  LT: files=3381 lines=756,619
  SUM == repo total: 2,608,452   ✓ (文件集一致 + 行数复算一致 + 分层加总 = 全仓总行数)
```

本轮 status 更新:**R6-deep-read 27 文件 / 24,423 行**(24 个记忆后端 L1 实现 + 3 个 mcp_oauth)。
累计已学:R2(118)+ R3(35)+ R4(35)+ R5(31)+ R6(27)= **243 文件**,R1-inventoried 降至 8287。

**范围调整**:8 个记忆后端的实现 `.py` 由 L2 促升 L1(L1 文件 412→436,+24 文件/+22,124 行),
README/plugin.yaml 保持 L2。理由:R6 卡片要求对本簇达 L1 完成标准,这些 `.py` 是 MemoryProvider ABC
契约的全部生产实现,机制精读才能定案各家取舍。规则写进 `scripts/assign_layers.py` 并重生成台账
(status 列保留)。

**R3-structure 三文件处置(卡片要求)**:`tools/mcp_oauth.py`、`mcp_oauth_manager.py`、
`mcp_dashboard_oauth.py` 本轮由清账子代理精读到 L1,status 从 `R3-structure` 升为 `R6-deep-read`,
**R3-structure 归零**。理由:MCP OAuth 与 R3 学过的 mcp_tool 七道防护同簇,顺势补齐欠账;结论记入
`notes/r6-60`。

## 2. 底稿与成品章清单

**底稿 `notes/`(8 篇,凡断言紧跟 `路径:行号 @ 863e313` + 代码原文)**:
- `r6-01`(主线:插件装载器 + query_rewrite ◇ 定案 + config schema + optimize-storage 编排深水区)
- `r6-10`(子代理:honcho——身份阶梯 / 双层召回状态机 / OAuth 轮换 / 写口清洗)
- `r6-20`(子代理:openviking REST + commit 屏障 + 崩溃恢复;byterover CLI 包装)
- `r6-30`(子代理:hindsight / supermemory / retaindb——三种写离线风格横向对比)
- `r6-40`(子代理:mem0 三形态云 + holographic 纯本地 HRR 相位数学)
- `r6-60`(子代理:MCP OAuth 三件套,R3-structure 清账)
- `r6-90`(定案 12 条)+ `r6-95`(测试记录)

主线亲读 `r6-01`(装载器/query_rewrite/config_schema/optimize-storage 编排)与 hermes_state_search
的 optimize 编排段;对 6 篇子代理底稿逐条抽查关键行号——mem0 三形态路由(:280-288)、user_id 哨兵
(:56-62)、mem0 版本漂移(_setup:954 vs plugin.yaml)、holographic bind 相位加(:77-84)与共享连接
注册表(store:101)、honcho 会话名优先级(client:793-806)、cli 点号 host 键残留(:1113)、
writeFrequency 主路径绕过、openviking commit 守卫(:3421-3429)、hindsight drop 语义(:1293)、
supermemory max_retries=0、retaindb SQLite write-behind、mcp_oauth asend 桥(manager:419)与两条 docs
证伪(auto-bump 串零命中、SSE OAuth 支持)——**均逐字命中**;全部定案由主线亲自复核。

**成品章 `chapters/r6-memory-provider-ecosystem.md`**(新可读性标准,GitHub 可渲染 Mermaid):四块
(统一 ABC 插座 / 八后端智能光谱 / 三条贯穿纪律 / MCP OAuth 胶水)+ 以 298 秒事故开篇;地图与代码出入
及元规律融进叙述。

## 3. 行为规格测试(659 用例全过)

官方 `run_tests.sh`(密封、per-file 隔离、8 workers)四批合计 **48 文件 / 659 passed / 0 failed**:
honcho 全家 15 文件/242、其余七后端 22 文件/318、MCP OAuth 7 文件/74、补批 4 文件/25。

沿用 R2/R4 记录的可选依赖模式:`test_hindsight_provider` 初跑 6 失败(密封环境禁懒装且
`hindsight-client` 未装),补装 `hindsight-client==0.6.1` 后 57/57 全过——非代码缺陷。各云后端测试全部
stub 化,不需真实凭据,本轮未配置任何凭据。

## 4. 文档-代码冲突定案(R6 范围,12 条)

逐条定案(证据见 `notes/r6-90`)。本轮抓到两类**新的系统性腐烂源**:

- **表格类宣称最易腐烂**:8 家后端 README 的优先级表/数值限制表/配置项表/工具清单几乎家家漂移——
  honcho 会话名优先级表方向错(网关键实为第一)、"card 200 tokens"是删了实现的化石、retaindb "7 memory
  types" 实为 6、工具表列 5 实注册 10、mem0 `user_id` 默认值实为哨兵、`--mode` 表漏 selfhosted、
  supermemory `capture_mode` 是死配置、holographic/hindsight 配置项两处各缺一半。
- **plugin.yaml 的 `hooks` 键全仓无消费者**:加载器只读 description,hooks 声明纯装饰;hindsight
  声明 `on_session_end` 却未实现该方法,byterover/openviking 的 hooks 声明也与实现不符——声明性元数据
  与分发机制脱节。

其余:query_rewrite ◇(R1)证实(双层防注入);根 README Honcho dialectic 宣称证实(主体在服务端);
honcho `writeFrequency` 四态实现但 provider 主路径绕过(gateway 只剩孤儿注释);openviking `auto`
搜索模式 ≡ fast、copy-profile setup 路径不存在;mem0 `_setup` 版本检查 (2,0,7) 落后 plugin.yaml
(2.0.10);memory-providers.md 总览"8 provider/一次一个"证实;optimize-storage 编排层 r5-10 结论复核
成立;MCP OAuth 新增两条 docs 证伪(oauth-over-ssh 的 auto-bump 提示串零命中且行为不成立;
mcp-config-reference 说仅 StreamableHTTP、代码支持 SSE)。

**规律(与 R3-R5 一致并加深)**:插件 README 漂移方向 100% 是"文档落后代码",无一处代码落后 README。

L1 完成标准自评:对簇内每个后端,能讲清它把智能放在哪(本地数学/本地 daemon/CLI/云)、ABC 各方法怎么
映射、失败方向如何、与另外七家的取舍差异(成品章的"智能光谱"与横向对比即证);能凭底稿重实现(每篇
末列"重实现要点")。达标。

## 5. 下一轮建议

**下一轮做 R7:网关与多路复用**(`gateway/session.py`、`session_context`、`session_state`、
`session_stall`、`memory_monitor` 等——R5 台账里 `round=R7` 的 gateway 侧文件;网关如何为 Telegram/
Discord/Slack 多平台多用户复用一个 agent 核心、会话路由、不活跃看门狗、带外 steer 注入)。理由:R2 学
运行时、R5 学会话持久化、R6 学记忆生态——R7 自然上升到"这一切怎么被一个长驻网关服务包起来,同时服务
几十个并发用户"。R6 已把记忆的多租户身份(user_id/peer/container_tag)与 multiplex 密钥隔离钉死,R7 是
它的宿主侧。台账 `round=R7` 现有约 5 个 gateway L1 文件 + 多个 R3-R7 桶文件,开轮先按惯例钉死范围。

打法沿用 R4-R6:主线读 gateway 会话核心与看门狗,session_context/state/stall/memory_monitor 用子代理
并行深挖;产出底稿 `notes/r7-*` + 成品章 `chapters/r7-*`(新标准)+ 测试作规格 + 定案 R7 范围 ▲/◇ +
更新台账 status 为 `R7-*` 并重跑校验报数。

无阻塞事项。真跑各云记忆后端需各自 API key(honcho/mem0/supermemory/retaindb/hindsight cloud/
openviking 云端),纯代码学习与测试不依赖它;本轮 venv + `.[dev]` + hindsight-client 下测试 659 全绿。
