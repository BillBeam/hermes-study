# R3-95 行为规格测试运行记录

> 基线 `863e31318`,只读。官方 `scripts/run_tests.sh`(密封环境、per-file 子进程隔离、
> TZ=UTC/LANG=C.UTF-8),`HERMES_PYTHON=/home/user/hermes-venv/bin/python`(venv 已含 anthropic)。

## 结果汇总(全绿)

| 批次 | 文件 | 用例 | 结果 |
|---|---|---|---|
| 1 | test_hardline_blocklist / test_url_safety / test_threat_patterns / test_schema_sanitizer / test_tool_search / test_tool_result_storage / test_tool_output_limits / test_fuzzy_match / test_tool_guardrails | 409 | ✅ 409 passed |
| 2 | test_code_execution / test_env_passthrough / test_mcp_security(hermes_cli) / test_osv_check / test_write_approval / test_skills_guard / test_tirith_security | 167 | ✅ 167 passed |
| 3 | test_mcp_schema_cache / test_mcp_stdio_watchdog | 13 | ✅ 13 passed |

合计 **589 用例全过,0 失败**。hermes-agent 保持基线、零改动。

## 这些测试印证的底稿断言

- **test_hardline_blocklist(183✓)**:硬底线在 yolo 之前触发、yolo/session-yolo/mode=off/cron-approve
  都不能绕过、容器旁路、`len(HARDLINE_PATTERNS) <= 20`、引号/花括号/根塌缩/子壳绕过回归——印证 r3-10 §1、定案 8.1。
- **test_url_safety(61✓)**:公网放行/私网拦、DNS 失败无代理 fail-closed 而配代理非字面 IP fail-open、
  metadata 主机名/字面 IP 配代理仍拦、connect 时 IP 钉扎抛 SSRFConnectionBlocked——印证 r3-10 §3、定案 8.2/8.3。
- **test_schema_sanitizer(19✓)**:裸 object 补 properties、type 数组多分支保 anyOf、可空 union 折叠 +
  nullable hint、dependentRequired 字面量护栏、well-formed 不变——印证 r3-20 机制 A。
- **test_tool_result_storage(26✓)**:三层落盘、内容走 stdin 不进命令串(#22906)、路径注入中和、
  6×42K 加总超预算触发第三层、read_file cap 必须是 100_000 非 inf——印证 r3-20 机制 B。
- **test_tool_search(30✓)**:核心工具永不 defer、不可分类者留 visible、会话范围防越权(TestRegression_
  ToolsetScoping 12+1)、blind-call 探针、桥接经真 handle_function_call 触发 hook——印证 r3-20 机制 C、r3-01 §5。
- **test_fuzzy_match(45✓)**:9 策略链、相似度策略禁 replace_all、escape-drift/unicode/缩进护栏——印证 r3-20 机制 E。
- **test_tool_guardrails(7✓)**:签名只存哈希、warn 默认 hard_stop opt-in、web_search 超上限无视 hard_stop——印证 r3-10 §6。
- **test_code_execution(端到端)**:env 洗净(API keys 不在子进程)、RPC token fail-closed、单连接串行、
  stub 签名不漂移——印证 r3-30 A2/A3/A6。
- **test_env_passthrough**:passthrough 不能覆盖 provider blocklist(GHSA-rhgp-j443-p4rf)、
  黑名单 import 失败 fail-closed、多路复用无 scope 抛错——印证 r3-30 A4。
- **test_mcp_security(hermes_cli)**:SSH key persistence 载荷被拦、spawn 前过滤 evil、迁移禁用危险条目——印证 r3-30 B4。
- **test_osv_check**:只拦 MAL-* 忽略 CVE、fail-open、缓存 clean 与 blocked——印证 r3-30 B3。
- **test_tirith_security**:退出码作真源、熔断器、供应链校验——印证 r3-10 §5。
- **test_mcp_stdio_watchdog(2✓)**:getppid 孤儿判定、包裹形状保留真命令 argv——印证 r3-30 B5。
- **test_write_approval**:门只延迟不丢弃、skills 一律 stage、后台 stage——印证 r3-10 §7。
- **test_skills_guard**:信任×裁决矩阵、community dangerous force 不可覆盖——印证 r3-10 §4。
