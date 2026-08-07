# R2-13 finalize_turn:回合收尾的单一咽喉

> 底稿。基线 `863e31318`。范围:`agent/turn_finalizer.py`(756 行,全文精读)。
> 它是所有 break/正常终局共同流经的收尾点——"收尾即契约"。

## 0. 形态与来历

从 `conversation_loop` 尾部逐字搬出(god-file 拆解 Phase 1 step 4),行为中性、单一 return
(`turn_finalizer.py:1-21`)。logger 从 `agent.conversation_loop` 惰性导入以避免环并保留日志名(17-20)。

## 1. 预算耗尽兜底:三分支(94-142)

```python
    budget_exhausted = (
        api_call_count >= agent.max_iterations
        or agent.iteration_budget.remaining <= 0
    )
    budget_fallback_eligible = (
        budget_exhausted and not interrupted and not failed
        and str(_turn_exit_reason) in {"unknown", "budget_exhausted"}
    )
```
(`turn_finalizer.py:94-103 @ 863e313`,原文压缩空行)

- **分支 A 验证候选保留**(112-126):`final_response is None` 且有 `_pending_verification_response`
  且 eligible → 直接用被验证门扣下的那个答案,不再发模型调用("Preserve that exact answer instead
  of replacing it with another fallible model call",115-117)。`previewed` 标志只在候选真被复用时
  置位(#65919 response-loss blocker)。
- **分支 B summary 兜底**(127-142):没有候选 → `agent._handle_max_iterations(messages, api_call_count)`
  注入 user 消息并发**一次剥离 tools 的 summary 调用**(`turn_finalizer.py:141`)。
- **exit_reason 收敛**:两分支都改写为 `max_iterations_reached(used/max)`。
- **kanban 联动**(144-191):任一预算兜底若在 kanban worker 内(`HERMES_KANBAN_TASK`),
  经 `_record_task_failure(outcome="timed_out", release_claim=True)` 上报——走失败断路器
  而非 kanban_block(#29747 gap 2)。

`completed` 判定(193-201):有响应、未 failed、且(未到上限 或 正常文本终局)。

## 2. cleanup_errors:逐项防护而非一把梭(236-260, 675-679)

trajectory 落盘、任务资源清理(VM/浏览器)各自 try/except,失败**不吞掉响应**,
以 `result["cleanup_errors"]` 列表向调用方袒露(#8049:"the response is still returned either way")。

## 3. 持久化前的转录整形(262-357)

顺序严格:
1. `_drop_trailing_empty_response_scaffolding`(267)—— 私有重试脚手架不得入库
   (否则 "continue" 回合回放 "(empty)" 再陷空响应循环,262-265 注释)。
2. `_drop_verification_continuation_scaffolding`(273)—— 只剥合成 nudge
   (`_verification_stop_synthetic` / `_pre_verify_synthetic`,50-53),真实候选留在 state.db。
3. 中断时 `close_interrupted_tool_sequence`(289-291)—— 干净 /stop 后 tool 结果是尾部,
   不补假 assistant 就会持久化 `tool→user`,严格 provider(Gemini/Claude)会拒绝并在下回合
   幻觉续写用户消息(#48879)。
4. **#43849/#44100 不变式**:「已交付 final_response ⇒ 转录里有 assistant 行」,在这个
   所有恢复 break 都流经的**单一咽喉**执行(293-347):
   - 尾部非 assistant → append;
   - 尾部是**纯 tool-call assistant 行**(有 tool_calls 无文本,`_is_pure_tool_call_tail`,31-42)
     → **就地填 content**(不 append,避免 assistant→assistant),再 pop `_db_persisted` 标记
     并把 `agent._db_flush_scan_prefix = None`(335-347)——这是全仓唯一一处活字典就地摘标记,
     必须同时失效有界 flush 游标,否则 /resume 读回 `content=""` 跨会话复发。
   - `content != final_response` 守卫防验证候选重复(#65919 §7)。
5. `_apply_persist_user_message_override`(355-357):模型请求已完成,把 API-only 的
   语音/换模/技能引导替换回干净用户输入再写最终快照(#48677/#63766)。

## 4. 收尾期 micro-compaction 门(359-384)

回合定稿后、持久化前跑 micro-compact 摊薄压缩成本。门条件极其防御:
`_micro_compact_enabled is True`(**严格 is True** + callable 检查——MagicMock 的 truthy
自动属性曾让测试里的 mock 压缩器把转录整个抹掉,367-371 注释);
`_persist_disabled` 的后台 review fork **禁止** micro-compact(烧辅助 LLM + 可能对
canonical 会话 archive_and_compact,377-383)。

## 5. result 契约(~600-691)

`final_response / messages / api_calls / completed / partial / interrupted /
response_transformed / response_previewed / model / provider / base_url /
七种 token 计数 / estimated_cost_usd / cost_status / cost_source / last_prompt_tokens /
service_tier / session_id`;条件字段:`guardrail`(护栏停机元数据)、`error`
(持久化失败时,gateway 显示 status=error、桌面弹 disk-full,668-674)、
`cleanup_errors`、`pending_steer`(683-685:最终回复后才到的 /steer 交还调用方作为
下一 user 回合,不静默丢弃)、`interrupt_message`。

## 6. 学习闭环触发点(698-724)

- 技能触发**此刻**判定:`_iters_since_skill >= _skill_nudge_interval`(本回合工具迭代数,698-704)。
- 外部记忆 `_sync_external_memory_for_turn`(707-712)。
- `_spawn_background_review`(716-724):**响应送达后**才 fork("never competes with the
  user's task for model attention"),best-effort。
- 记忆 provider 的 on_session_end/shutdown **不在这**(726-731):run_conversation 每条消息
  调一次,回合级 shutdown 会杀死第二条消息前的 provider;真正的会话终止在 CLI atexit/gateway 过期。
- 插件钩子 `on_session_end` 每回合末必发(736-751,带 turn_exit_reason 等)。

## 7. 重实现要点

1. 收尾必须是单一咽喉:所有 break 路径共享同一套「转录整形+不变式+持久化+result 组装」。
2. 「交付了什么 ⇒ 转录里必须有什么」这类不变式放在咽喉处校验/修复,而不是散在每个 break 点。
3. 预算兜底优先复用被门扣下的候选答案,其次才是额外 summary 调用(省一次调用且更忠实)。
4. 清理失败要袒露(cleanup_errors)而不是吞掉或让回合失败。
5. 自我改进类后台任务的触发点放在"响应已交付"之后。
