# R2-02 三级用户介入:interrupt / steer / redirect

> 底稿。基线 `863e31318`。范围:`run_agent.py:3028-3400`(介入 API)、
> `agent/conversation_loop.py`(drain 点与 redirect 重建)、`agent/interrupt_compat.py`。

## 0. 问题

agent 干活时用户说话有三种意图:停下、顺带补充、纠正方向但别浪费已完成的工作。
同进程可能有多个 agent(gateway),中断信号必须按 agent 定域;/stop 与纠正可能竞态。

## 1. interrupt():硬停,全量扇出(run_agent.py:3028-3161)

- **与 redirect 共锁**:`_pending_redirect_lock` 下置 `_interrupt_requested=True`、存
  `_interrupt_message`、**清空 `_pending_redirect`**——"/stop cannot race with an accepted
  correction and accidentally turn itself into a retry"(3055-3056 注释)。
- **hard_cancel 经压缩提交栅栏原子发布**(3057-3077):`_active_compression_commit_fence.
  cancel_before_commit` 在与 begin_commit 相同的锁下 set Event;若 commit 已赢,等其完成再发布停。
  普通中断可能被压缩屏蔽,hard_cancel 不会。
- **codex_app_server 特例**(3096-3106):它自有模型/工具循环,走 `_codex_session.request_interrupt()`。
- **cron 内联请求**(3108-3117):cron 在会话线程上做 API 请求(避免嵌套 interrupt-worker 死锁),
  其 client 注册了 `_active_request_abort`,跨线程中断可立刻关 socket。
- **按线程定域的工具中断**(3118-3129):`_set_interrupt(True, self._execution_thread_id)`——
  只打本 agent 的执行线程;若中断先于线程绑定到达,置 `_interrupt_thread_signal_pending` 延迟下发
  (3124-3129,防误伤调用者线程)。
- **扇出到并发工具 worker tids**(3130-3148):ThreadPoolExecutor worker 各有 tid,
  `is_interrupted()` 只看自己 tid;不扇出的话,已在网络 IO 上挂住的并发 terminal 命令要等到自身超时。
- **递归传播到子 agent**(3149-3159):hard_cancel 走 `request_hard_interrupt(child)`
  (`agent/interrupt_compat.py`:用 `inspect.getattr_static` 防 MagicMock 动态代理误判新 ABI),
  普通中断走 `child.interrupt(message)`。

`hard_interrupt()`(3163-3172)绕过动态派发直调 `AIAgent.interrupt(self, message, hard_cancel=True)`
——旧 ABI 子类可能覆写了 interrupt 而没有 hard_cancel 关键字。

`clear_interrupt(preserve_redirect=False)`(3174-3227):清标志、清 Event、清执行线程与全部
worker tid 的中断位(3202-3218:worker 正常自清,但显式清保证陈旧中断不会跨回合打到复用 tid 的
无关工具);**硬停丢弃 pending steer**(3219-3226:steer 面向的下一次工具迭代已不存在);
`preserve_redirect=True` 仅供循环取消模型请求后重建同一逻辑回合使用。

## 2. steer():不打断注入(run_agent.py:3229-3263)

只把文本存进 `_pending_steer`(加锁,多次调用换行拼接),**不动任何执行**。消费点两处:
- **工具批次后**:`apply_pending_steer_to_tool_results`(agent_runtime_helpers.py:3921)把 steer
  以 marker 追加到最后一条 tool 结果 content —— piggyback 在 tool 输出上保住角色交替。
- **pre-API drain**(conversation_loop.py:1498-1535):API 调用期间到达的 steer 在下一迭代
  构建 api_messages 前注入最后一条 tool 消息(str 与多模态块都处理);无 tool 消息可注入则
  加锁回存,等下一个工具批次。
- **最终回复后到达的 steer**:finalizer 取走放进 `result["pending_steer"]` 交还调用方作为
  下一 user 回合(turn_finalizer.py:683-685),不静默丢失。

## 3. redirect():只取消模型请求(run_agent.py:3265-3355)

语义:"Redirect the active turn without converting it into a new task"。分派逻辑:
1. codex_app_server → 原生 `turn/steer` 协议(3283-3300),不打断子进程。
2. **工具执行期降级为 steer**(3302-3306):"Never kill a tool merely to deliver
   conversational guidance"。
3. 只有 `_model_request_active` Event 置位(模型请求真在飞)才接受;响应已完成则返回 False
   让表面走"排队新回合"(3325-3328)。已有 interrupt 且无既存 redirect 也拒绝(3329-3330)。
   多次 redirect 以 `[Additional user correction]` 拼接(3331-3335)。
4. 接受后:置 `_interrupt_requested=True` 但 `_interrupt_message=None`;**只**打执行线程
   + `_active_request_abort("redirect_abort")` 关流;**不**扇出 worker、**不**传播子 agent
   (3341-3354)——工具与子代理继续跑。

`_model_request_active` 的置位/清除在循环的 API 调用外包裹(conversation_loop.py:2420-2452,
同在 `_pending_redirect_lock` 下),保证 redirect 的"请求在飞"判定与请求生命周期原子一致。

## 4. redirect 的回合重建(conversation_loop.py:122-201, 1416-1424)

循环顶部 `_drain_pending_redirect()` 有值 → `_apply_active_turn_redirect(agent, messages, text)`:
- 已流出的可见文本剥 `<think>` 后作为降级 checkpoint 保留;脚手架文本
  `"[This response was interrupted by a user correction.]"` 写入 **api_content 侧车**仅供
  provider 回放,干净转录保持用户原话;无可见文本时行标记 `display_kind="hidden"`。
  动机(122-160 注释):不完整 reasoning 块不能回放(Anthropic 签名/Responses 配对),
  而把思维链写回转录会被输出分类器判定 prefill 越狱,曾永久毒化会话(empty response 风暴)。
- 纠正文本 append 为真实 user 消息;`original_user_message` 拼上
  `"User correction during the turn: …"`(1419-1423)并立即持久化(1424)。
- 若取消发生在重试/退避等待中:置 `_retry.restart_with_redirected_messages`
  (`agent/turn_retry_state.py:87`),外层据此重建 payload 重试**同一逻辑迭代**;
  预算相应退款(refund)。

## 5. 与 TUI/gateway 的 busy 策略关系

三个 API 是机制层;策略层(收到新输入选 interrupt/steer/redirect/queue)在
gateway `busy_input_mode` 与 tui_gateway busy 三态(R7/R10 范围)。机制/策略分层清晰:
loop 只提供原语。

## 6. 重实现要点

1. 中断信号必须按 agent/线程定域,支持同进程多 agent;并发工具 worker 需要显式扇出。
2. steer 类"不打断注入"的落点选 tool 结果(保角色交替),并设 pre-API drain 让"模型思考期间"
   的输入不延迟一轮。
3. redirect 的准入判定要与模型请求生命周期共锁;与 /stop 共锁防竞态。
4. 取消后的重建:部分输出降级为"provider 可回放、转录不污染"的 checkpoint(侧车),
   纠正入转录为真实 user 消息;预算退款。
5. 兼容旧 ABI/测试替身:hard-stop 直调基类实现 + getattr_static 探测。
