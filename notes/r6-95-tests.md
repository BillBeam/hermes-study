# R6-95 行为规格测试运行记录

> 底稿。基线 `863e31318`(零改动)。运行器:官方 `scripts/run_tests.sh`(密封、per-file 隔离、8 workers)。

## 1. 汇总

四批合计 **48 文件 / 659 passed / 0 failed**:

| 批次 | 文件数 | 通过 |
|---|---|---|
| honcho(plugin 全家 + client 并发/配置/fail-open + config_schema) | 15 | 242 |
| 其余 7 后端(openviking/byterover/hindsight×4/holographic×5/mem0×4/retaindb×2/supermemory + 向量存储) | 22 | 318 |
| MCP OAuth(oauth/manager/cold_load_expiry/bidirectional/integration/metadata/remote_gateway_skill) | 7 | 74 |
| 补批(dashboard_oauth×2 / 401_handling / memory_lazy_install) | 4 | 25 |

## 2. 环境依赖(与 R2/R4 同款模式)

`test_hindsight_provider.py` 初跑 6 失败:`_lazy_ensure("memory.hindsight")` 在密封环境禁懒装且
`hindsight-client` 未装。补装 `hindsight-client==0.6.1`(tools/lazy_deps.py:194 声明的规格)后 57/57 全过。
非代码缺陷。其余后端测试全部离线 stub,无需真实凭据。

## 3. 行为规格精选(与底稿呼应)

- `test_honcho_startup_fail_open`:"第 1 轮之外绝不等待"——turn 1 有界等待 ≥0.5s 返 "",turn 2-4
  各 <0.4s 立即返 ""(r6-10 §2.3 契约)。
- `test_session.py::test_sync_turn_strips_leaked_memory_context_before_honcho_ingest`:写口清洗防
  画像自我污染(注入块回流不得进入用户模型)。
- `test_oauth.py` 三件套:refresh token 轮换持久化 / 失败 fail-open / 锁内重读采用他进程轮换结果。
- `test_openviking.py::test_prefetch_e2e_sends_limit_and_reads_l2_content`:真 HTTPServer 假扮
  OpenViking,线上契约逐字段锁死(limit=24、score_threshold=0、无 top_k/mode)、L2 全文注入。
- `test_openviking_provider.py::test_session_needs_commit_guard_wins_over_stale_turn_count`:
  commit 守卫先于 turn_count(#28296 M3 防同会话双 commit)。
- `test_hindsight_provider.py::test_prefetch_waits_for_pending_retain_before_recall` /
  `test_timed_out_ops_are_dropped_not_repolled`:读后写栅栏顺序 + drop 换 liveness(r6-30 §1.8)。
- `test_supermemory_provider.py::test_shutdown_joins_threads_and_flushes_buffer`:缓冲 + 边界一次写
  生命周期(partial: True 兜底)。
- `test_retaindb_provider.py::test_upload_file_rejects_hermes_credential_store`:文件外传必过
  harness 读闸。
- `test_mem0_v3.py::test_prefetch_*`(Event 见证版):3s 热路径等待、超时弃注入、结果下轮消费;
  `test_create_backend_*`:oss>host>platform 路由与提示词标签一致性。
- `test_holographic_store.py::test_failed_write_does_not_pin_lock`(autocommit 无悬挂事务)+
  8 线程并发零 "database is locked";`test_holographic_retrieval.py`:自然语言查询 FTS5 消毒规格。
- `test_mcp_oauth_cold_load_expiry.py`:绝对过期播种四组断言(Fix A 完整契约,含 BetterStack 式
  分离源预飞行 + 无 token 零网络)。
- `test_mcp_oauth_bidirectional.py`:唯一驱动 httpx `asend` 往返的测试——生成器桥双向契约
  (坏桥在首个响应 AttributeError)。

## 4. 注记

真跑各云后端(honcho/mem0/supermemory/retaindb/hindsight cloud/openviking 云端)需各自 API key,
测试全部 stub 化不依赖;本轮未配置任何凭据。
