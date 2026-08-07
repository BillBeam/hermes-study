# R2-95 行为规格测试运行记录

> 基线 `863e31318`,只读。运行方式:官方 `scripts/run_tests.sh`(密封环境、per-file
> 子进程隔离、TZ=UTC/LANG=C.UTF-8),`HERMES_PYTHON=/home/user/hermes-venv/bin/python`。
> venv 由 `pip install -e ".[dev]"` 建;补装 `anthropic>=0.39.0` 后无缺依赖。

## 结果汇总(全绿)

| 批次 | 文件 | 用例 | 结果 |
|---|---|---|---|
| 1 | test_error_classifier / test_prompt_caching / test_turn_retry_state / test_credential_pool_sole_cooldown / test_nous_rate_guard / test_retry_utils | 129 | ✅ 129 passed |
| 2 | test_provider_fallback / test_24996_fallback_exhaustion_cooldown / test_credential_pool_routing / test_credential_pool_unmatched_rotation_bound / test_auxiliary_main_first / test_usage_pricing / test_turn_finalizer_iteration_limit_exit | 71 | ✅ 71 passed |
| 3 | test_nous_portal_anthropic_wire(补装 anthropic 后) | 25 | ✅ 25 passed |

合计 **225 用例全过,0 失败**。

## 环境依赖记录

- 首次跑 `test_nous_portal_anthropic_wire.py::TestClientShape::*` 2 例失败,原因是
  `agent/anthropic_adapter.py:813` 在缺 `anthropic` 包时抛 ImportError——这是**可选依赖缺失**
  (`.[dev]` 不含 `anthropic`),非代码缺陷。`pip install 'anthropic>=0.39.0'` 后 25/25 全过。
- 完整测试套件需 `.[all]` 才能全跑;R2 相关的核心逻辑测试(分类器/缓存/重试/池/定价/finalizer)
  在纯 `.[dev]` 下即全绿。

## 这些测试作为行为规格印证了底稿的哪些断言

- **test_error_classifier.py(72✓)**:FailoverReason 枚举全表、状态码/错误体沿 cause 链提取、
  429 三分(overloaded 不轮转 / rate_limit 轮转 / upstream 换模型不换 key)、cert vs SSL-alert
  顺序敏感——印证 r2-23 §1。
- **test_prompt_caching.py(19✓)**:4 断点预算、canonical 不带 marker、半截 tool_call 不烧断点、
  静态前缀=整条时零空 text block——印证 r2-23 §5。
- **test_provider_fallback.py(14✓)**:链推进游标、跳过未配置/抛异常项、Nous 双线 api_mode、
  同后端身份跳过——印证 r2-23 §3。
- **test_24996_fallback_exhaustion_cooldown.py(7✓)**:非限流耗尽 armed +5s、限流耗尽 60s 不被
  覆盖、连续限流指数封顶——印证 r2-23 §3 冷却语义。
- **test_credential_pool_sole_cooldown.py(7✓)** / **test_credential_pool_routing.py(17✓)** /
  **test_credential_pool_unmatched_rotation_bound.py(2✓)**:冷却=f(状态码,语义,池型)、
  429 归因带失败方身份、匹配不上时有界且不误伤——印证 r2-22 §3/§9。
- **test_auxiliary_main_first.py(15✓)**:`_resolve_auto` main-first、主不可用先走 task fallback_chain
  不碰主链/OpenRouter——印证 r2-21 §1.3、定案 4a。
- **test_usage_pricing.py(11✓)**:DeepSeek 原生缓存归一、代理顶层 Anthropic 缓存字段回退、
  价目表不变量——印证 r2-21 §3。
- **test_turn_finalizer_iteration_limit_exit.py(5✓)**:预算耗尽收尾——印证 r2-13 §1。
- **test_nous_portal_anthropic_wire.py(25✓)**:模型前缀双线路由、Portal Bearer 不带 x-api-key——
  印证 r2-20 定案 a。
