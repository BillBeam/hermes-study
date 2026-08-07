# R5-95 行为规格测试运行记录

> 底稿。基线 `863e31318`(hermes-agent 零改动,只读)。运行器:官方 `scripts/run_tests.sh`
> (密封环境、per-file 子进程隔离、8 workers)。命令模板:
> `HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh <files>`。

## 1. 汇总

本轮七批,合计 **115 文件 / 1,360 passed / 1 failed(环境敏感,定性见 §3)**:

| 批次 | 文件数 | 通过 | 失败 |
|---|---|---|---|
| state 核心(hermes_state 全家 + FTS 迁移/修复) | 21 | 320 | 1 |
| 压缩批一(compressor/anti-thrash/concurrent_fork/worker 隔离等) | 20 | 246 | 0 |
| 上下文/prompt/记忆/检索/检查点(engine/references/builder/memory_*/session_search/checkpoint_manager) | 25 | 395 | 0 |
| 压缩批二(focus/signal_leak/telemetry/tail_anchor/media 等) | 18 | 96 | 0 |
| 残留(prompt_caching/file_safety/surrogate/state_db_guard/cjk_bridge/checkpoint_config) | 6 | 42 | 0 |
| 零化库 + 慢查询日志 | 2 | 9 | 0 |
| 记忆工具/审批/scrubber + 压缩规格(summary_prefix/proactive/micro/idle)+ R4 清账(local_env/shell_hooks/desktop_ui) | 23 | 252 | 0 |

## 2. 与底稿的呼应(测试即规格,精选)

- `test_hermes_state_compression_busy_retry`:SLA 原文 "A live compression lock must delay a
  concurrent append, not destroy the turn" —— r5-02 §4.3 的完整契约(等锁 / 预算内拒 / 持有者零延迟 /
  丢租约 fast-fail)。
- `test_compression_concurrent_fork`:共享 session_id 的两线程并发压缩,孩子数 ≤1、输家收敛到同一子
  id、锁必释放 —— r5-20 ▲5 锁语义的可执行规格(无锁时确定性产出 2 孩子)。
- `test_proactive_tool_result_pruning`:1M 窗口下主阈值不触发而 prune 生效;跑道未长回时第二次调用
  返回输入对象本身一字未动 —— r5-20 ▲4 滞回规格。
- `test_summary_role_template_alternation`:内置 Mistral 交替预检复刻 + Desktop×Devstral 真实失败
  夹具 —— r5-20 ◇2 规格。
- `test_summary_prefix_semantics`:四代历史 handoff 前缀逐字节 pin(prepend-only 契约)。
- `test_context_engine_select_context`:空列表 fail-open(`all([])` 陷阱)+ 基类默认实现被恒等检查
  短路 —— r5-30 ◇4 规格。
- `test_prompt_builder`:截断告警必须指向 config 键名而非常量名;ContextVar 跨会话隔离;威胁扫描
  block-with-placeholder —— r5-30 ▲1 规格。
- `test_fts_cjk_bigram`(现场 gcc 编译 .so):v23 库补装 CJK 索引灰度(loaded≠available、回填中新行
  活索引、完成前不服务)—— r5-10 §2 标记闸三不变式。
- `test_memory_async_sync`:后台 sync FIFO 排水 + 有界弃单报账("既不无限等、也不静默丢")。
- `test_streaming_context_scrubber`:真实 1-80 字符分片的围栏块跨 delta 剥除(#5719)+ 行中散文提及
  不误杀。
- `test_checkpoint_manager`:hash 注入/路径穿越防护、恢复前自拍、orphan 的 dev/ino 佐证。
- `test_zeroed_state_db`:并发隔离不互踩 + 拿不到锁 fail-closed(#68805)。
- `test_wal_checkpoint_strategy` / `test_hermes_state_wal_fallback`:每 50 写 PASSIVE checkpoint、
  WAL 回退全矩阵(静默拒绝也回退、磁盘头已 WAL 绝不降级)。

## 3. 唯一失败:SQLite 版本敏感断言(非代码缺陷)

`tests/test_state_db_malformed_repair.py::test_repair_rebuilds_stale_btree_indexes` 失败于断言
`"wrong # of entries in index idx_messages_session" in reason`。定性(主线亲自复现验证):

- 腐化手法(writable_schema 造空 B-tree)在本机 SQLite 3.45.1 上**有效**,`integrity_check` 检出
  损坏——但先吐每行 `row N missing from index …`(10 行),汇总行 `wrong # of entries…` 排第 11;
  而 `_db_opens_cleanly` 只回传 `problems[:3]`,汇总行被截掉,断言的特定措辞不在其中。
- **机制本身在本机全闭环**:手动复现确认 `_db_opens_cleanly` 检出损坏(reason 非 None)、修复梯
  Strategy 0.5 无条件 REINDEX(不匹配消息文本)修复成功、修后复检干净:
  `repaired: True strategy: reindex_btree / clean after: True`。
- 根因是测试断言吃了 SQLite 版本的 integrity_check 消息排序差异;hermes 官方运行时是 3.51.3+
  (代码 #70055 门也因此把本机 3.45.1 判为 WAL-reset 脆弱版本、自动降 journal_mode=DELETE——该次
  运行顺带实景演示了 r5-02 §1.2 的 WAL 回退防御)。**非 hermes-agent 代码缺陷,不改基线。**

## 4. 环境注记

- 本轮无新增依赖安装(R2 的 anthropic、R4 的 daytona/modal/openssh 沿用)。
- `test_fts_cjk_bigram` 需要 gcc,本容器可用,CJK 分词器 .so 现场编译成功,未 skip。
- 真跑模型仍需 provider 凭据(见 R1 §1.5);本簇测试全部离线(压缩摘要 LLM 均为 stub),不依赖。
