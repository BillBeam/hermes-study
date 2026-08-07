# R2-01 回合主循环:外层迭代循环与退出路径

> 底稿(求全求证)。基线 `863e31318`,路径相对 hermes-agent 仓库根。
> 范围:`agent/conversation_loop.py` 的 `run_conversation`(1233-7334)骨架、
> 预算判定、六级空响应恢复阶梯、验证门、阶段感知错误分诊、finalize 交接。
> 配套:r2-02(介入)、r2-03(流式)、r2-04(重试恢复)、r2-05(工具批次)、
> r2-06(TurnContext/侧车)、r2-13(finalizer)。

## 0. 定位与形态

主循环不在 `run_agent.py`(AGENTS.md 的说法已过期):`AIAgent.run_conversation` 是转发器
(`run_agent.py:7772-7778`),真身是 `agent/conversation_loop.py::run_conversation`——
一个把 parent `AIAgent` 作为第一参数、通过属性访问其全部状态的**自由函数**(god-file 拆解的产物)。

`agent/conversation_loop.py:1-16 @ 863e313`:
```python
"""The agent conversation loop — extracted from ``run_agent.AIAgent``.

This is the biggest single chunk pulled out of ``run_agent.py``: the
roughly 3,900-line :func:`run_conversation` body that drives one user
turn through the agent (model call, tool dispatch, retries, fallbacks,
compression, post-turn hooks, background memory/skill review nudges).
```

设计要点:拆出后为保住既有测试/生产代码对 `run_agent` 符号的 monkeypatch,所有被 patch 的符号
(`handle_function_call`、`_set_interrupt`、`OpenAI`…)经 `_ra()` 间接解析(`conversation_loop.py:324-331`)。
**取舍**:模块拆了,耦合仍在(参数是整个 agent 对象);换来的是可测试性与文件尺寸,不是真正的解耦。

## 1. 回合的五段结构

```
run_conversation(agent, user_message, ...)
 ├─ MoA 解码(1274-1285)+ 每回合状态复位(压缩标志 1290-1292、.env 凭据热刷新 1297-1300)
 ├─ 前奏:build_turn_context(1310-1331)→ 解包 12 个 locals(1332-1342)
 ├─ 回合级 locals:计数器/上限/验证候选(1352-1399)
 ├─ codex_app_server 旁路:整回合交给 codex 子进程运行时(1406-1413)
 ├─ 外层 while 循环(1415-7308)…… 每次迭代 = 一次模型请求 + 响应分流
 └─ finalize_turn(7313-7330)统一收尾
```

外层循环条件(`agent/conversation_loop.py:1415 @ 863e313`):
```python
    while (api_call_count < agent.max_iterations and agent.iteration_budget.remaining > 0) or agent._budget_grace_call:
```

## 2. 每次迭代的固定前奏(循环体 1416-1600)

顺序固定,每步都有理由:
1. **redirect drain**(1416-1424):`_drain_pending_redirect()` 取纠正文本 → `_apply_active_turn_redirect`
   重建回合(见 r2-02);同时把纠正拼进 `original_user_message` 并立即持久化。
2. **checkpoint 去重复位**(1427):`agent._checkpoint_mgr.new_turn()` — 每迭代允许一次快照。
3. **中断检查**(1430-1435):`_interrupt_requested` → break,`_turn_exit_reason="interrupted_by_user"`。
4. **计数与预算**(1437-1449):`api_call_count += 1`;grace 标志消费(见 §3);
   `iteration_budget.consume()` 失败 → break(`budget_exhausted`)。
5. **step_callback**(1453-1478):向 gateway 发 `agent:step` 事件,附上一批工具的 name/args/result
   (从 messages 尾部反扫组装,1456-1475)。
6. **技能 nudge 计数**(1482-1484):`_iters_since_skill += 1`(见 r2-13/记忆闭环)。
7. **pre-API steer drain**(1498-1535):API 调用期间到达的 /steer 在**本轮**注入:反向找最后一条
   tool 消息,`format_steer_marker` 追加到其 content(str 或多模态块都处理);没有 tool 消息则回存
   `_pending_steer`(注入 user 消息会破坏角色交替)。加锁回存(1526-1532)。
8. **tool_call 参数消毒**(1548-1560):`_sanitize_tool_call_arguments` 带**身份键游标**
   `_sanitize_args_cursor` —— 已校验过的历史消息跳过 re-json.loads;压缩/undo 重写列表会破坏前缀
   匹配、强制从分歧点重扫(1543-1547 注释)。
9. **角色交替修复**(1578-1585):`repair_message_sequence_with_cursor` 防 `tool → user` 尾部
   (空响应脚手架剥离 + 新 user 消息落地的组合会造成);修复同时重算 SessionDB flush 游标(#44837)。

## 3. 预算:IterationBudget + grace 死标志 + finalizer 兜底

- `IterationBudget`(`agent/iteration_budget.py:40-43`)线程安全 consume/refund;
  构造默认 **90**(`agent/agent_init.py:470`,`run_agent.py:446`),CLI 配置默认 500 在 `cli.py:475`。
- **grace-call 是死代码**(R2 定案,详 r2-90 条目 1):`_budget_grace_call` 仅在
  `agent/agent_init.py:892` 初始化为 False;全仓唯一的其他写点是消费点
  `conversation_loop.py:1444-1445`(置回 False)。While 条件里的 `or agent._budget_grace_call`
  永不为真。真实兜底在 finalizer(见 r2-13):`budget_fallback_eligible` → `_handle_max_iterations`
  注入 user 消息 + 发一次**剥离 tools** 的 summary 调用(`agent/turn_finalizer.py:141`)。
- **refund 点**:execute_code-only 的迭代退款(`conversation_loop.py:6412-6414` 注释起);
  redirect 重建也退款(r2-02)。设计动机:程序化工具调用与用户纠偏不该吃预算。

消费点证据(`agent/conversation_loop.py:1444-1449 @ 863e313`):
```python
        if agent._budget_grace_call:
            agent._budget_grace_call = False
        elif not agent.iteration_budget.consume():
            _turn_exit_reason = "budget_exhausted"
```

## 4. api_messages 重建与 api_content 侧车回放(1587-1679)

每迭代从 `messages`(干净转录)重建 `api_messages`(线上字节),规则:
- 每条消息 copy 后剥离簿记字段:`api_content`、`display_kind/display_metadata`、`_row_id`、
  `reasoning`(拷入 `reasoning_content` 后删)、`finish_reason`、`_thinking_prefill`(1596-1662)。
- **当前回合 user 消息**(idx == current_turn_user_idx):优先用前奏盖章的 `api_content`
  (记忆预取+插件注入的确切字节),没有则现场 `compose_user_api_content`(1617-1633)。
- **历史 user/assistant 消息**:回放各自侧车的历史字节,保证 provider prompt-cache 前缀
  逐字节稳定(1634-1648;user 行带注入侧车,user+assistant 行可带 sanitize-divergence 侧车)。

`agent/conversation_loop.py:1591-1596 @ 863e313`:
```python
            # api_content is the persistence sidecar carrying the exact bytes
            # sent to the API for this message when they differ from the clean
            # stored content (see compose_user_api_content in turn_context).
            # It is bookkeeping, never a provider field — pop it from EVERY
            # outgoing copy.
```

## 5. 响应分流:工具分支(5956-6570)

`assistant_message.tool_calls` 为真时:
1. **id 唯一化**(5972):模型复用同一 id 会让后一个调用的结果被 pre-API 消毒器丢弃。
2. **名字修复与三振**(5976-6060):`_repair_tool_call` 先自动修名;
   **混合批次策略**(5997-6012):有效+无效混合时只 error 无效的、执行有效的、**不计 strike**
   (退化模型如 gpt-5.6 大上下文会发 6 真 + 1 空名;整批作废会扔掉真工作);
   纯无效批次计 `_invalid_tool_retries`,3 次后终止回合(partial=True),终止前
   `close_interrupted_tool_sequence` 补假 assistant 收尾防 `tool→user`(6031)。
3. **JSON 参数校验**(6066 起)→ 持久化先行:canonical append 失败则**不执行副作用工具**、
   break(`session_persistence_failed`,6337-6345)——"UI 不得观察到仅存在于内存的行"。
4. **执行**:`agent._execute_tool_calls(...)`(6365,见 r2-05)。
5. 执行后:持久化失败再查一次(6367-6374);工具护栏可控停机
   (`_tool_guardrail_halt_decision` → `guardrail_halt`,6376-6397);
   截断重试计数清零(6402);`_stream_needs_break = True`(6410,下次真文本前补一个段落断);
   execute_code-only 退款(6412+);活动心跳(6568)后 `continue`。

## 6. 文本分支:六级空响应恢复阶梯(6572-6870)

`final_response = assistant_message.content or ""`;若 `_has_content_after_think_block` 为假,逐级下探:

| 级 | 条件 | 动作 | 守卫 | 行号 |
|---|---|---|---|---|
| 1 部分流恢复 | 已流出的 `_current_streamed_assistant_text` 有实内容 | 剥 think 后直接作为最终回复,`_response_was_previewed=False`(让 gateway 补发说明) | — | 6589-6615 |
| 2 前回合内容回退 | `_last_content_with_tools` 存在且**该回合全部工具是 housekeeping** | 用前回合叙述作为最终回复(substantive 工具的叙述是中途旁白,不用) | 一次性(用后清空) | 6617-6641 |
| 3 工具后 nudge | 近 5 条内有 tool 消息 | 合成 assistant "(empty)" + user nudge(都带 `_empty_recovery_synthetic`),保住 `tool→assistant→user` 交替 | `_post_tool_empty_retried` 一次性 | 6643-6708 |
| 4 思考预填续写 | 有结构化 reasoning 或行内 `<think>` | 原样 append(标 `_thinking_prefill`)让模型看到自己的思考续写文本 | `_thinking_prefill_retries < 2` | 6710-6742 |
| 5 空响应退避重试 | 真空(剥 think 无内容)且(无结构化 或 预填耗尽) | jittered backoff 5-60s,0.2s 步进睡眠随时可中断,每 30s touch 活动心跳 | `_empty_content_retries < 3` | 6744-6803 |
| 6 fallback 切换 | 仍真空且有 `_fallback_chain` | `_try_activate_fallback()` 成功则清零 L5 计数重来 | 链耗尽为止 | 6805-6835 |

全部耗尽 → 终局 "(empty)":`_empty_terminal_sentinel` 标记(**不持久化**——持久化会让后续
"continue" 回合把 "(empty)" 当真实回复回放,长工具会话会卡死在空响应循环,6848-6853 注释),
先 `_drop_trailing_empty_response_scaffolding` 剥掉本轮脚手架(6845;该函数带角色交替回退逻辑,
见文件 1943-1984)。有 reasoning 时落日志并提示用户(6856+)。

## 7. 终局劫持:三道验证门(7000-7206)

文本终局在 append `final_msg` 前依次过三道门,任一触发都:把候选存入
`_pending_verification_response`(+记录是否已流出 `_..._previewed`)、**清空 final_response**、
`continue`——这样后续预算耗尽时 finalizer 能用候选兜底,又不会把门触发误当完成(#61631):

1. **verify-on-stop**(~7000-7094):基于证据的验证 nudge(计 `_verification_stop_nudges`),
   nudge 静默运行(不噪扰终端,7077-7081)。
2. **pre_verify 钩子**(7096-7156):本回合有文件改动(`_turn_file_mutation_paths`)且注册了
   `pre_verify` hook 时,插件/shell 生成继续消息;姿态(coding 与否)会话内解析一次并缓存
   (7110-7115);真实回复先持久化并作为 interim 发给 UI,只有 nudge 标 `_pre_verify_synthetic`
   从持久转录剥除(#65919 §7)。
3. **kanban 终态工具守卫**(7158-7206):worker 必须以 kanban_complete/block 收尾;
   叙述式 stop 会被 nudge 1-2 次(`build_kanban_stop_nudge`),防 dispatcher 记 protocol_violation。

三门都过 → append,`_turn_exit_reason = "text_response(finish_reason=...)"`,break(7208-7213)。

## 8. 阶段感知错误分诊(7215-7308)

外层大 try 罩住"API 请求 + 本地后处理"两个阶段;异常时遍历 traceback 的模块名集合:
- 命中 `_LOCAL_PROCESSING_MODULES`(`conversation_loop.py:111-116`)且未命中
  `_API_CALL_MODULES`(117-121)→ **本地确定性 bug**:不重试(重试只会烧预算,#66267),
  立即以道歉文本终局(`local_processing_error`)。
- 否则按 API 错误处理:只在接近 max_iterations 时才终局(`error_near_max_iterations`),
  其余情况继续循环重试。
- 两种情况都先补齐未应答的 tool 结果(7262-7284):已 append 的 assistant(tool_calls) 之后,
  给每个没有 tool 结果的 id 补 error 结果,保住 API 合法序列;不注入合成 user/assistant
  (7286-7290 注释:污染历史、烧 token、破坏交替)。

`agent/conversation_loop.py:7234-7237 @ 863e313`:
```python
            _hit_local = bool(tb_module_names & _LOCAL_PROCESSING_MODULES)
            _hit_api = bool(tb_module_names & _API_CALL_MODULES)

            _is_local_processing_error = _hit_local and not _hit_api
```

## 9. 退出理由清单(_turn_exit_reason 全集,本文件内)

`unknown`(初值 1370)/ `interrupted_by_user`(1432)/ `budget_exhausted`(1447)/
`ollama_runtime_context_too_small`(1912)/ `interrupted_during_api_call`(5633)/
`all_retries_exhausted_no_response`(5688)/ `session_persistence_failed`(6342、6371)/
`guardrail_halt`(6378)/ `partial_stream_recovery`(6598)/ `fallback_prior_turn_content`(6629)/
`empty_response_exhausted`(6843)/ `text_response(finish_reason=…)`(7210)/
`local_processing_error(…)`(7300)/ `error_near_max_iterations(…)`(7303)。
诊断字段随 finalize 传出(7327),是排障与测试断言的锚点。

## 10. 重实现要点(最小等价机制)

1. 双上限预算:调用数上限 + 可退款预算对象(线程安全),**不要**中途注入"预算快用完"
   (真实失效模式:模型提前摆烂,#7915);兜底用"最后一次无工具 summary 调用"。
2. 干净转录与线上字节分离(api_content 侧车)是 prompt cache 稳定的前提;每次迭代从转录重建
   请求消息并回放历史侧车。
3. 空响应恢复必须是阶梯而非单一重试,且每级配一次性守卫;终局哨兵不得持久化。
4. 错误按"发生阶段"分诊:本地确定性错误零重试。
5. 任何合成消息(nudge/预填/哨兵)都要 (a) 保住角色交替 (b) 带可剥离标记。
6. 退出理由字符串全程携带,finalize 统一消费。

## 11. 行为规格(测试)

见 r2-95 测试记录:`tests/agent/test_turn_finalizer_iteration_limit_exit.py`(预算耗尽收尾)、
`tests/agent/test_budget_reasoning_details_exclusion.py` 等;运行结果在 r2-95。
