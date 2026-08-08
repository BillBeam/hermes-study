# 附卷:hermes-agent harness 能力点全清单(170 条,含代码证据摘录)

主卷:`reports/round-1-survey.md`。数据源:`data/capability-mining.json`(14 路子系统矿工的结构化产出),由 `scripts/render_capabilities.py` 渲染。
基线:`863e31318553cda8ad61df681d08175364d4164b`;所有 `路径:行号` 相对 hermes-agent 仓库根。

能力点总计 **170** 个(14 个子系统),其中 **60** 个为『◇ 代码有、官方文档没讲』,**69** 个附带『▲ 文档宣称与代码不符』记录;另有 **54** 条独立文档-代码冲突(见 2.16)。全部条目含精确证据,完整代码摘录在 `data/capability-mining.json`(本报告内嵌其首条证据摘录);主循环、凭据池等 15 条证据已按行号抽查复核,全部命中。


### 2.1 Agent 核心循环(run_agent.py AIAgent + agent/conversation_loop.py run_conversation 及回合生命周期协作者)

这是 hermes-agent 的心脏:AIAgent 类(run_agent.py,8167 行)持有全部运行时状态与线程安全的用户介入 API(interrupt/steer/redirect/流式回调/凭据刷新),而真正的主循环在 agent/conversation_loop.py 的 run_conversation(约 6000 行的 while 循环)。每个用户回合经历:build_turn_context 前奏(stdio 防护、系统提示恢复、MCP 刷新、preflight 压缩、插件注入、api_content 侧车组装)→ 外层迭代循环(预算判定、redirect 应用、消息重建与逐字节回放)→ 内层重试循环(TurnRetryState 一次性守卫下的限流退避、按提供商 OAuth 刷新、压缩重启、截断续写、内容过滤故障转移)→ 响应分流(工具批次经 segment planner 分段并发执行,或文本终局经空响应恢复阶梯与验证门)→ finalize_turn 收尾(预算耗尽 summary、trajectory/持久化逐项防护、kanban 上报)。设计上最鲜明的特征是"分层恢复":几乎每种失败(空响应、截断、丢 tool-call、流中断、会话持久化失败)都有专用的有界重试阶梯,且每级用一次性布尔守卫防止无限循环;以及"persist-what-you-send"不变式:发给 provider 的字节与干净转录分离存储(api_content 侧车),保证 prompt cache 前缀逐字节稳定。中断被细分为三个粒度(硬停、steer 不打断、redirect 只取消模型请求并原地重建回合),流式输出用单调令牌栅栏解决重试竞态。预算耗尽的 grace-call 标志位是死代码(从未置 True),实际兜底走 finalize_turn 的无工具 summary 调用。

关键文件(15 个,行数实测,余见 JSON):`run_agent.py`(8167), `agent/conversation_loop.py`(7334), `agent/turn_context.py`(1275), `agent/turn_finalizer.py`(756), `agent/tool_executor.py`(2403), `agent/iteration_budget.py`(62), `agent/turn_retry_state.py`(92), `agent/turn_summary.py`(310)


#### 1. 迭代预算与预算耗尽收尾(IterationBudget + grace-call 死标志 + 无工具 summary 兜底)  **[▲文档不符]**

- **解决**:agent 循环可能无限打转烧钱;但中途插入'预算快用完'警告又会让模型在复杂任务上过早放弃(#7915)。需要一个只在真正耗尽时才介入、且父子 agent 各自独立计数的预算机制。
- **实现**:外层 while 条件同时检查 api_call_count < max_iterations、iteration_budget.remaining > 0 和 _budget_grace_call;IterationBudget 是线程安全的 consume/refund 计数器,父 agent 创建、子 agent 各持独立实例(delegation.max_iterations 默认 50),execute_code 回合会 refund 不占预算。真正的耗尽兜底不在循环内:finalize_turn 检测 budget_fallback_eligible 后调用 agent._handle_max_iterations,注入一条 user 消息并发起一次剥离 tools 的 summary 调用作为最终答复。
- **证据**:`agent/conversation_loop.py:1415` · `agent/conversation_loop.py:1444` · `agent/iteration_budget.py:40` · `agent/turn_finalizer.py:141`
  ```
      while (api_call_count < agent.max_iterations and agent.iteration_budget.remaining > 0) or agent._budget_grace_call:
  ```
- **规模**:约 200 LOC(iteration_budget.py 62 行 + 循环判定 + finalizer 兜底 + chat_completion_helpers.handle_max_iterations);逻辑不复杂但语义微妙(refund、grace、父子独立)。
- **学习价值**:高 — '只在耗尽时通知一次、给一次无工具 summary 机会'是对'预算压力提示导致模型摆烂'这一真实失效模式的直接回应;refund 机制(execute_code/redirect 重建不计费)也是预算设计里少见的细节。同时它是死代码教训:grace 标志位保留在 while 条件里但全仓库无人置 True。
- **▲ 文档不符**:AGENTS.md:351-353 宣称循环带'a one-turn grace call',但 _budget_grace_call 仅在 agent/agent_init.py:892 初始化为 False,全仓库(含 _budget_exhausted_injected)无任何置 True 代码——grace 分支永远不可达,实际兜底走 finalize_turn 的 summary 调用。且 AGENTS.md:328 与 agent/iteration_budget.py:5 docstring 都称默认 500,实际 run_agent.py:446 / agent_init.py:470 构造默认是 90,500 只是 cli.py:475 的 CLI 配置默认。

#### 2. 三级用户介入:interrupt(硬停)/ steer(不打断注入)/ redirect(只取消模型请求)

- **解决**:用户在 agent 干活时说话有三种意图:彻底停下、顺带补充指示、纠正方向但不作废已完成的工作。单一 interrupt 无法区分,会把轻量纠偏变成'杀掉整回合重来'。
- **实现**:interrupt() 置 _interrupt_requested 并按线程 id 精确下发 _set_interrupt(仅本 agent 执行线程 + 并发工具 worker tids + 递归传播到子 agent),hard_cancel 经压缩提交栅栏原子发布;steer() 只把文本暂存 _pending_steer,工具批次结束后由 apply_pending_steer_to_tool_results 追加到最后一条 tool 结果(带 marker,保持角色交替),循环顶部还有 pre-API drain 让 API 调用期间到达的 steer 在本轮就被看到;redirect() 在工具执行期降级为 steer,否则只中断模型请求(不波及工具 worker 和子 agent),把纠正文本放入 _pending_redirect。三者共享 _pending_redirect_lock 防 /stop 与纠正互相竞态。
- **证据**:`run_agent.py:3121` · `run_agent.py:3305` · `run_agent.py:3258` · `agent/agent_runtime_helpers.py:3921`
  ```
          if self._execution_thread_id is not None:
              _set_interrupt(True, self._execution_thread_id)
              self._interrupt_thread_signal_pending = False
  ```
- **规模**:约 400 LOC(run_agent.py:3028-3392 + runtime_helpers steer 注入 + 循环内多处 drain 点);线程安全与竞态处理密集,复杂度高。
- **学习价值**:高 — 把'用户介入'按破坏性分成三个粒度、并用按线程 id 定域的中断信号支持同进程多 agent(gateway),是 harness 交互设计的高质量范本;steer 借 tool 结果 piggyback 保持角色交替的手法尤其值得学。

#### 3. Redirect 活转重建:_apply_active_turn_redirect + restart_with_redirected_messages 预算退款重试  **[◇未见于文档、▲文档不符]**

- **解决**:取消一个进行中的模型请求后,不完整的 provider reasoning 块不能回放(Anthropic 签名/Responses 配对要求),而把已流式展示的思维链写回转录会被输出分类器判定为 prefill 越狱,曾永久毒化 4 个会话('empty response 风暴')。需要一种 provider 安全、缓存安全、且不丢用户已见文本的回合重建方式。
- **实现**:循环顶部 drain _pending_redirect 后,_apply_active_turn_redirect 只保留剥掉 <think> 的可见文本作为降级 checkpoint:脚手架文本('[This response was interrupted by a user correction.]')写入 api_content 侧车仅供 provider 回放,干净转录 content 保持用户原话;无可见文本时行标记 display_kind="hidden"。若取消发生在重试/退避等待中,置 _retry.restart_with_redirected_messages,循环对该次迭代做 api_call_count -= 1 且 iteration_budget.refund() 后重试同一逻辑迭代;响应完成与 redirect 跨线程交叉时(_redirect_crossed_response)丢弃陈旧响应改走重建。
- **证据**:`agent/conversation_loop.py:1416` · `agent/conversation_loop.py:183` · `agent/conversation_loop.py:5626` · `agent/conversation_loop.py:2468`
  ```
          _redirect_text = agent._drain_pending_redirect()
          if _redirect_text:
              _apply_active_turn_redirect(agent, messages, _redirect_text)
  ```
- **规模**:约 150 LOC 核心(conversation_loop.py:122-201 + 循环内 5 处 preserve_redirect 分支);不变式推理密集(80 行注释记录事故复盘),复杂度高。
- **学习价值**:高 — 注释里写明的两条不变式(裸思维链绝不序列化回可回放内容;脚手架走 api_content 侧车不进转录)来自真实生产事故(2026-07 四个会话被 prefill 判定砖死),是'中断-重定向'机制最容易踩的坑的一手记录。
- **▲ 文档不符**:website/docs/developer-guide/agent-loop.md:124 称中断后 'No partial response is injected into conversation history',与代码相反:redirect 显式把可见部分响应作为 checkpoint(api_content)注入 messages,partial_stream_recovery(conversation_loop.py:6597-6615)还把已流出的部分文本直接提升为 final_response。

#### 4. TurnRetryState:单次 API 尝试的一次性恢复守卫矩阵  **[◇未见于文档]**

- **解决**:内层重试循环对同一次模型调用要做十几种截然不同的恢复(按提供商 OAuth 刷新、429 凭据池、压缩重启、续写重启、思维签名剥离、图片缩放、llama.cpp 语法回退等),这些守卫曾是散落在 2400 行循环体里的约 16 个裸布尔局部变量,极易漏置或误复用。
- **实现**:TurnRetryState 是 dependency-free 的 dataclass,把守卫收敛为一个对象:每类恢复分支由一个 *_attempted 布尔保证每次尝试至多触发一次,4 个 restart_with_* 字段作为循环体外读取的重启信号(压缩/续写/内容过滤故障转移/redirect)。每次外层迭代新建实例(conversation_loop.py:2133),retry_count/max_retries 等 while 力学变量刻意留作普通局部变量;__iter__ 提供 (name, value) 遍历便于测试。
- **证据**:`agent/turn_retry_state.py:43` · `agent/turn_retry_state.py:83` · `agent/conversation_loop.py:2133`
  ```
      codex_auth_retry_attempted: bool = False
      anthropic_auth_retry_attempted: bool = False
  ```
- **规模**:92 LOC dataclass 本体,但守卫贯穿 conversation_loop.py 内层循环约 3400 行;模式简单,覆盖面大。
- **学习价值**:中 — '一次性守卫 + 重启信号'是所有重试型 harness 的通用骨架;把 bookkeeping 与 while 力学变量刻意分离的取舍(docstring 里明说)是可借鉴的重构判断。

#### 5. 无消费者也强制流式 + 流单写者令牌栅栏(#65991)  **[◇未见于文档、▲文档不符]**

- **解决**:非流式调用无法区分'provider 还在生成'与'连接挂死用 SSE ping 续命',子 agent 等安静模式调用者会无限悬挂;另一方面重试会产生并发的新旧两条流,陈旧流的 delta 若继续写入会污染本回合累计文本与去重比较。
- **实现**:循环默认 _use_streaming = True——即使没有任何显示/TTS 消费者也走 _interruptible_streaming_api_call,以获得 90s 陈旧流检测与 60s 读超时(仅 ACP/MoA 无消费者/Mock 客户端例外)。每次流尝试先 _claim_stream_writer() 递增共享单调令牌并存入 thread-local;_fire_stream_delta/_fire_reasoning_delta/_record_streamed_assistant_text 入口检查 _stream_writer_superseded(),被更新尝试取代的旧流所有 delta 被静默栅栏掉(按 2 的幂稀疏告警)。delta 先经有状态 think scrubber(跨 delta 拆分的 <think> 标签)再经 context scrubber 过滤后才到达回调。
- **证据**:`agent/conversation_loop.py:2329` · `run_agent.py:6290` · `run_agent.py:6339`
  ```
                  # Always prefer the streaming path — even without stream
                  # consumers.  Streaming gives us fine-grained health
                  # checking (90s stale-stream detection, 60s read timeout)
                  # that the non-streaming path lacks.  Without this,
  ```
- **规模**:约 400 LOC(run_agent.py:6026-6434 流状态管理 + 循环内 _use_streaming 决策);并发正确性推理复杂度高。
- **学习价值**:高 — '流式当健康检查用'颠覆了'没人看就不用流'的直觉,解决了 SSE ping 挂死这类难排查问题;单调令牌 + thread-local 的单写者栅栏是解决重试/流竞态的干净方案,可直接移植到任何流式 harness。
- **▲ 文档不符**:website/docs/developer-guide/agent-loop.md:108 称 API 请求包在 _interruptible_api_call() 里;实际主循环默认全部走 _interruptible_streaming_api_call(conversation_loop.py:2348-2394),非流式仅是显式禁用/特例回退。

#### 6. 空响应六级恢复阶梯  **[◇未见于文档]**

- **解决**:弱模型/劣化 provider 常在工具结果后返回空内容、只输出 reasoning、或流中断只送出一半——直接判失败会浪费整回合已完成的工具工作,盲目重试又会无限烧预算。
- **实现**:无工具调用且剥掉 <think> 后无内容时按序尝试:(1) partial stream recovery——已流式送达的文本直接用作 final_response;(2) 上一轮'内容+纯 housekeeping 工具'的旧内容作为答案;(3) post-tool nudge——补一条合成 user 消息('You just executed tool calls but returned an empty response...')要求继续,每轮一次;(4) thinking-only prefill——把只有 reasoning 的 assistant 消息原样附加(_thinking_prefill 标记)让模型接着自己的思考写正文,至多 2 次;(5) 真空响应带抖动退避重试 3 次;(6) 激活 fallback provider 链;全部失败才落 '(empty)' 终局哨兵(_empty_terminal_sentinel 不持久化),且若有 reasoning 会把前 500 字符作为'可能含答案的最后推理'展示给用户。所有合成脚手架在终局前被 pop 掉。
- **证据**:`agent/conversation_loop.py:6597` · `agent/conversation_loop.py:6725` · `agent/conversation_loop.py:6760` · `agent/conversation_loop.py:6852`
  ```
                      if agent._has_content_after_think_block(_partial_streamed):
                          _turn_exit_reason = "partial_stream_recovery"
                          _recovered = agent._strip_think_blocks(_partial_streamed).strip()
  ```
- **规模**:约 320 LOC(conversation_loop.py:6588-6903)+ 分散的计数器复位点;分支逻辑与失效模式知识密集。
- **学习价值**:高 — 这是对'模型静默失败'最完整的分层处置样本:每一级都对应一类真实失效(#9400 弱模型工具后沉默、mimo 永远填 reasoning 字段导致守卫失效等),且展示了合成消息如何标记为脚手架避免毒化持久转录。

#### 7. 截断续写(指数放大输出预算)与 dropped tool-call 再提示  **[◇未见于文档]**

- **解决**:输出被 max_tokens 截断或流中途断线时,直接返回半截答案不可接受;另一类失效是 provider 报 finish_reason="tool_calls" 却送来空 tool_calls 数组(Copilot 上的 claude 系,2026-07),回合会把'计划叙述'当最终答案提前结束。
- **实现**:截断路径:把部分内容存入 truncated_response_parts、追加续写 user 提示(区分'流中断'与'真输出上限',丢失 tool-call 时提示分块重试),置 restart_with_length_continuation;重启时 _ephemeral_max_output_tokens 按 2^length_continue_retries 指数放大(基数 max_tokens 或 4096,上限 32768),至多 4 次后返回 partial=True 结果。截断的是 tool-call JSON 时走独立的 truncated_tool_call_retries(也 4 次)。dropped tool-call:在终局化 chokepoint 检查 finish_reason=="tool_calls" 且数组为空,注入 _dropped_toolcall_nudge 标记的合成对('issue the actual tool call now'),连续 3 次为限,任一成功工具轮清零。
- **证据**:`agent/conversation_loop.py:3106` · `agent/conversation_loop.py:5675` · `agent/conversation_loop.py:6974` · `agent/conversation_loop.py:6953`
  ```
                                  messages.append(continue_msg)
                                  agent._session_messages = messages
  ```
- **规模**:约 300 LOC(3020-3160 截断分类 + 5667-5682 预算放大 + 6962-7018 dropped 恢复);对 provider 具体失效模式的经验编码密集。
- **学习价值**:中 — 指数放大输出预算的续写策略和'finish_reason 与 payload 自相矛盾'的检测都是从生产观察反推的防御;'连续失速计数、成功即清零'的预算设计比全局上限更合理。

#### 8. 工具批次分段调度(segment planner)+ 并发执行的中断/超时/授权栅栏  **[▲文档不符]**

- **解决**:整批并发会让有副作用的工具乱序执行,整批串行又浪费只读工具的并行机会;并发执行还要解决:中断如何到达各 worker 线程、批次超时后 gate 里停着的 worker 不能再醒来执行、危险工具的用户授权不能并发弹窗。
- **实现**:_execute_tool_calls 对多工具批次调用 _plan_tool_batch_segments,按只读性、文件目标是否重叠、MCP opt-in 把批次切成 parallel/sequential 段:单段同质批保留原单路径,混合批由 execute_tool_calls_segmented 按发出顺序逐段执行。并发路径用 start_condition 按提交顺序串行化 dispatch(有界等待防楔死),batch_abandoned 事件在超时/中断时唤醒所有停在门口的 worker 直接退出,_ConcurrentToolAuthorizationGate 串行化授权询问且从超时里扣除人等待时间;中断时对每个 worker tid 下发 _set_interrupt 并给已运行工具 3s 优雅退出窗口,未执行的调用统一补'cancelled'工具结果保持 tool_call/result 配对。
- **证据**:`run_agent.py:7614` · `agent/tool_executor.py:885` · `agent/tool_executor.py:1294` · `agent/tool_executor.py:1303`
  ```
              from agent.tool_dispatch_helpers import _plan_tool_batch_segments
              _active_env = get_active_env(effective_task_id)
              _exec_cwd = Path(_active_env.cwd) if _active_env is not None and _active_env.cwd else None
              segments = _plan_tool_batch_segments(tool_calls, execution_cwd=_exec_cwd)
  ```
- **规模**:约 1700 LOC(tool_executor.py 并发+分段执行器 + tool_dispatch_helpers.py planner);线程池、条件变量、多重栅栏,子系统内复杂度最高。
- **学习价值**:高 — '安全子集并发、副作用段做屏障'的分段模型比'全并发或全串行'精细得多;abandon 事件解决的'超时后 gate 停靠 worker 幽灵 dispatch'是并发工具执行最阴险的 bug 类别,注释里的权衡(宁可泄漏挂死线程也不 join 死锁整批)很有参考价值。
- **▲ 文档不符**:website/docs/developer-guide/agent-loop.md:133 称多工具一律经 ThreadPoolExecutor 并发、仅 interactive 工具例外强制串行;实际是 segment planner 按只读性/文件目标重叠/MCP opt-in 分段,混合批逐段执行(run_agent.py:7593-7633),并发只给 parallel-safe 段。

#### 9. 验证门劫持终局:verify-on-stop / pre_verify 钩子 / kanban 终态工具守卫 + 候选答案保底

- **解决**:模型想停(finish_reason=stop)不等于任务完成:改了代码没验证、kanban worker 没调 kanban_complete 就叙述性收尾。需要在'接受最终答案'的关口插一道可扩展的闸门,又不能在预算耗尽时把被扣下的答案弄丢。
- **实现**:文本终局前依次检查三道门:verify_on_stop(基于本回合 _turn_file_mutation_paths 生成证据型 nudge)、pre_verify 插件/shell 钩子(get_pre_verify_continue_message,受 max_verify_nudges 限制)、kanban stop guard(worker 未以终态工具结束时 nudge,至多 2 次)。任一门触发时:真实 assistant 答案照常持久化并作为 interim 消息展示,合成 nudge 打上 _verification_stop_synthetic 等标记(finalizer 会剥离),final_response 清空但存入 _pending_verification_response;若后续把预算耗尽,finalize_turn 的 continuation_budget_exhausted 分支恢复该候选为最终答案而非再发一次可能失败的 summary 调用(#65919 response-loss blocker)。
- **证据**:`agent/conversation_loop.py:7089` · `agent/conversation_loop.py:7071` · `agent/turn_finalizer.py:118` · `agent/conversation_loop.py:7175`
  ```
                      _pending_verification_response = final_response
                      _pending_verification_response_previewed = (
                          agent._interim_content_was_streamed(final_response or "")
                      )
                      final_response = None
  ```
- **规模**:约 230 LOC(conversation_loop.py:7037-7206 + finalizer 保底分支);三道门共享同一 pending-candidate 契约。
- **学习价值**:高 — 'stop 是提案不是决定'的闸门架构 + '被扣下的答案必须显式建档、预算耗尽时按出处恢复'的 response-loss 防护,是 agent 停止条件工程里最值得抄的完整方案;三道门复用同一契约也展示了如何做可插拔的终局策略。

#### 10. TurnContext 回合前奏 + api_content『persist-what-you-send』侧车  **[◇未见于文档]**

- **解决**:每回合的一次性设置(系统提示恢复、preflight 压缩、插件/记忆注入)与循环体纠缠会让 6000 行循环不可维护;更深的问题是:注入内容若直接改写用户消息,持久转录被污染;若每次现注入,历史消息的线上字节会漂移,provider prompt cache 前缀从注入点开始整段失效。
- **实现**:build_turn_context 把全部前奏收敛为一个函数,返回 TurnContext dataclass(messages、current_turn_user_idx、plugin_user_context、ext_prefetch_cache 等)供循环读取;协作函数以参数显式传入避免 import cycle。注入走 api_content 侧车:当前回合 user 消息在前奏时由 compose_user_api_content 把记忆预取+插件上下文组成的确切线上字节盖章存为 api_content,构建 api_messages 时当前消息用盖章值、历史 user/assistant 消息回放各自侧车的历史字节——干净 content 与线上字节永久分离,前缀逐字节稳定。前奏还做 between-turns MCP 工具刷新(仅在新回合首次请求前扩展前缀,保证缓存安全)与 sys.modules 门控省掉 0.4s 的 mcp 包导入。
- **证据**:`agent/turn_context.py:309` · `agent/conversation_loop.py:1634` · `agent/conversation_loop.py:1648` · `agent/turn_context.py:429`
  ```
  class TurnContext:
      """Values produced by the turn prologue and consumed by the turn loop."""
  ```
- **规模**:turn_context.py 1275 行 + 循环内约 60 行回放逻辑;侧车不变式贯穿持久化/压缩/redirect 多个子系统。
- **学习价值**:高 — api_content 侧车同时解决'转录洁净'与'prompt cache 字节稳定'两个互相矛盾的需求,是上下文注入类 harness 的关键设计;MCP 刷新的缓存安全时点选择(前奏、首次请求前)也是缓存意识工程的好例子。

#### 11. 阶段感知错误分诊:本地处理 bug 与 API 错误按 traceback 模块集区分  **[◇未见于文档]**

- **解决**:循环的大 try/except 同时罩住 API 请求和响应后处理。确定性的本地 bug(如把多模态 list 传进正则)重试必然原样复现,只会烧光迭代预算;而网络类错误又必须重试。异常本身无法区分这两类。
- **实现**:外层 except 遍历 e.__traceback__ 收集途经文件名集合,与 _LOCAL_PROCESSING_MODULES / _API_CALL_MODULES 两个集合求交:碰过本地后处理 helper 且从未进入 interruptible API helper 判为本地 bug,立即以道歉文案终局(_turn_exit_reason=local_processing_error)而非重试(#66267)。同一 handler 还会为已 append 的 assistant tool_calls 补齐未应答 tool_call_id 的错误结果,维持 provider 的配对要求;完整 traceback 以 ERROR 级同时落 agent.log 与 errors.log(此前 DEBUG 级导致偶发故障不可复现)。
- **证据**:`agent/conversation_loop.py:7234` · `agent/conversation_loop.py:7295` · `agent/conversation_loop.py:7276`
  ```
              _hit_local = bool(tb_module_names & _LOCAL_PROCESSING_MODULES)
              _hit_api = bool(tb_module_names & _API_CALL_MODULES)
  ```
- **规模**:约 95 LOC(conversation_loop.py:7215-7308);技巧新颖但实现紧凑。
- **学习价值**:中 — 用 traceback 途经模块集合做'可重试性'分诊,是在无法给所有异常打类型标签的现实约束下的实用发明;'确定性错误不烧预算'这一原则适用于一切重试系统。

#### 12. 活动心跳与 kanban 带外 steer 注入(_touch_activity)  **[◇未见于文档]**

- **解决**:网关按不活跃超时(默认 1800s)杀会话,长退避/长工具间隙会被误杀且死因不可知;kanban worker 是无交互的派生进程,用户想对跑着的任务说话只能等它死掉重派。
- **实现**:_touch_activity 在每次 API 调用、工具执行、流 chunk、退避等待(每 30s)处刷新 _last_activity_ts/_last_activity_desc,限频(60s)投影到 SessionDB 供网关超时处理器与'still working'通知消费;当 HERMES_KANBAN_TASK 存在时顺带做 worker 心跳防看板 watchdog 误回收,并调用 inject_new_comments_from_env(self) 把任务卡上新增的人类评论折叠进正在运行的回合——等价于对活任务的带外 /steer,无需重启 worker。退避循环里的 touch 点(150×0.2s=30s)保证限流等待期间网关仍看到存活。
- **证据**:`run_agent.py:3707` · `agent/conversation_loop.py:5610` · `run_agent.py:3698`
  ```
                  heartbeat_current_worker_from_env()
                  # Fold any new operator notes into the running turn (OUT-OF-BAND
  ```
- **规模**:约 160 LOC(run_agent.py:3666-3790)+ 循环内十余个 touch 调用点;胶水多、思想清晰。
- **学习价值**:中 — '活动时钟即观测协议'(desc 携带正在做什么,超时被杀时能报死因)与借心跳通道向活回合注入用户评论,都是长跑 agent 运维性的低成本高收益手法;kanban 文档只写了评论在重派时被读取,活注入完全未记载。

**本子系统文档-代码冲突(5 条):**

- 宣称:AGENTS.md:351-353:'The core loop is inside run_conversation() — entirely synchronous, with interrupt checks, budget tracking, and a one-turn grace call'(并在 355-357 展示含 _budget_grace_call 的 while 条件)
  实际:_budget_grace_call 仅在 agent/agent_init.py:892 被初始化为 False,全仓库(含 _budget_exhausted_injected)没有任何将其置 True 的代码——grace-call 分支永远不可达,是死脚手架;实际的预算耗尽兜底是 finalize_turn 经 handle_max_iterations 追加 user 消息并发起一次无工具 summary 调用(turn_finalizer.py:127-141)。(证据:`agent/agent_init.py:892`)
- 宣称:AGENTS.md:328:'max_iterations: int = 500, # tool-calling iterations (shared with subagents)';agent/iteration_budget.py:5 docstring 同样称'parent's cap comes from max_iterations (default 500)'
  实际:AIAgent.__init__(run_agent.py:446)与 init_agent(agent/agent_init.py:470)的默认值都是 90;500 只是 CLI 配置层的 max_turns 默认(cli.py:475),直接构造 AIAgent 的程序化调用者得到 90 而非 500。(证据:`run_agent.py:446`)
- 宣称:website/docs/developer-guide/agent-loop.md:124:中断时'No partial response is injected into conversation history'
  实际:redirect 路径显式把已展示的部分响应降级为 checkpoint 注入 messages(api_content 侧车,conversation_loop.py:164-197);partial_stream_recovery(conversation_loop.py:6594-6615)更把已流式送出的部分文本直接提升为最终答复。(证据:`agent/conversation_loop.py:183`)
- 宣称:website/docs/developer-guide/agent-loop.md:108:'API requests are wrapped in _interruptible_api_call() which runs the actual HTTP call in a background thread'
  实际:主循环默认永远优先流式路径 _interruptible_streaming_api_call——即使没有任何流式消费者——以获得 90s 陈旧流检测/60s 读超时;非流式 _interruptible_api_call 只是禁用流或特例(ACP、MoA 无消费者、Mock)时的回退。(证据:`agent/conversation_loop.py:2348`)
- 宣称:website/docs/developer-guide/agent-loop.md:133-134:'Multiple tool calls → executed concurrently via ThreadPoolExecutor;Exception: tools marked as interactive (e.g., clarify) force sequential execution'
  实际:实际调度由 _plan_tool_batch_segments 决定:按只读工具、文件目标不重叠、MCP opt-in 把批次切成 parallel/sequential 段,混合批按发出顺序逐段执行(execute_tool_calls_segmented),并发仅授予 parallel-safe 段,而非'先并发、interactive 例外'。(证据:`run_agent.py:7617`)

### 2.2 模型提供商与 API 适配层 (Model Providers & API Adapter Layer)

该子系统是 Hermes agent harness 的"多 provider 接入与续命"层,把 20+ 推理 provider 的差异从核心 agent loop 里彻底剥离。核心是 api_mode 抽象:同一个 loop 通过 determine_api_mode() 把请求分派到 chat_completions / anthropic_messages / codex_responses / bedrock_converse 四种 wire 协议,各 adapter(anthropic/codex_responses/gemini_native/bedrock/vertex/azure_identity)负责 messages、tools、response 的双向翻译并 normalize 成统一的 OpenAI 风格对象。Provider 元数据用声明式 ProviderProfile + 34 个自注册插件(plugins/model-providers/)承载,支持 $HERMES_HOME 用户覆盖。续命机制由三块组成:CredentialPool 做多 key/OAuth 池轮换与分级冷却、跨进程 token 同步;error_classifier 用 FailoverReason 枚举把错误映射成恢复动作;try_activate_fallback 做 turn-scoped 多级 provider/model 热切换并同步 client/协议/池/缓存/上下文窗全部运行时状态。此外还有 prompt cache 4-断点保护策略、Nous 跨会话 RPH 护栏、auxiliary_client 的副任务独立路由、usage 归一与定价、models.dev 元数据探测等配套。整体约 3.8 万行,是 harness 里最复杂的子系统之一。

关键文件(25 个,行数实测,余见 JSON):`agent/auxiliary_client.py`(9976), `agent/chat_completion_helpers.py`(4363), `agent/model_metadata.py`(3370), `agent/anthropic_adapter.py`(3177), `agent/credential_pool.py`(3147), `agent/error_classifier.py`(1841), `agent/bedrock_adapter.py`(1573), `agent/codex_responses_adapter.py`(1590)


#### 13. 多 api_mode 抽象与统一分发 (chat_completions / anthropic_messages / codex_responses / bedrock_converse)

- **解决**:同一个 agent loop 要驱动 OpenAI-wire、Anthropic 原生 Messages、OpenAI Responses、AWS Bedrock Converse 四种完全不同的线协议,还要在 fallback/切换时动态换协议。若把 provider 差异散落在 loop 里会不可维护。
- **实现**:wire 协议抽象成 agent.api_mode 字符串。determine_api_mode()(hermes_cli/providers.py:671)按 host-mandated → Nous 双线 → transport 表 → bedrock 顺序解析;_dispatch_nonstreaming_api_request()(chat_completion_helpers.py:451)按 api_mode 分派到 _run_codex_stream / _anthropic_messages_create / bedrock converse / MoA / OpenAI 五条路径,把各 adapter 的返回统一 normalize 成 OpenAI 风格 SimpleNamespace 供 loop 消费。每个 adapter 文件(codex_responses_adapter/gemini_native_adapter/bedrock_adapter)负责 messages/tools/response 双向翻译。
- **证据**:`agent/chat_completion_helpers.py:467` · `hermes_cli/providers.py:684` · `agent/bedrock_adapter.py:741`
  ```
      if agent.api_mode == "codex_responses":
          request_client = make_client("codex_stream_request")
          return agent._run_codex_stream(
  ```
- **规模**:分发核心约 60 行(451-511),四个 adapter 合计约 4500 行
- **学习价值**:高 — 把线协议差异收敛成一个枚举字段 + 单点分发,是多 provider harness 的核心解耦手法,值得直接借鉴 api_mode + normalize-to-canonical 的模式。

#### 14. Nous Portal 双线协议路由 (同 provider 按模型走 anthropic_messages 或 chat_completions)  **[◇未见于文档、▲文档不符]**

- **解决**:Nous Portal 既在 /v1/chat/completions 上代理 OpenAI-兼容目录,又在 /v1/messages 上原生服务 anthropic/* 目录。同一个 provider 名字下,Claude 流量必须走原生 Anthropic 线以拿到 inner-block cache_control 断点和 thinking block,其它模型走 OpenAI 线。
- **实现**:nous_api_mode()(hermes_cli/providers.py:652)按模型 id 前缀 anthropic/ 判定:命中返回 anthropic_messages,否则 chat_completions。determine_api_mode() 在 transport 表查询前对 {nous,nous-portal,nousresearch} 做特判 carve-out,因为 Hermes overlay 把整个 Portal 目录标成 openai_chat,不特判就会把 Claude 钉在错误的线上。
- **证据**:`hermes_cli/providers.py:666` · `hermes_cli/providers.py:693`
  ```
      if str(model or "").strip().lower().startswith("anthropic/"):
          return "anthropic_messages"
  ```
- **规模**:约 50 行
- **学习价值**:中 — 展示了 provider 身份与 wire 协议不是一一对应、需按模型再分流的真实工程需求,是路由层的一个易被忽略的坑。
- **▲ 文档不符**:provider-runtime.md 只列 Nous 为一个 provider,未说明它对 anthropic/* 模型会切换到原生 Messages 线(dual-wire)。

#### 15. Anthropic prompt cache 保护策略 (4 断点 + 静态前缀切分 + failover 重贴)  **[▲文档不符]**

- **解决**:Anthropic 每请求最多 4 个 cache_control 断点。既要缓存稳定的 system 前缀(跨会话复用),又要缓存最近的对话尾部(会话内复用),还要兼容 OpenRouter 信封布局(空 content 消息贴顶层 marker 会被忽略、role:tool 顶层 marker 会静默挂起),并且 mid-turn failover 换 provider 后要按新 provider 的策略重贴。
- **实现**:build_prompt_cache_plan/apply_anthropic_cache_control(prompt_caching.py)先 strip 旧 marker,再用 _apply_system_cache_markers 把 system 拆成 [静态前缀|易变后缀] 两个 marker,剩余 4-breakpoints_used 个 marker 贴到最近可承载的非 system 消息;_can_carry_marker() 对信封布局排除空 content / 纯 tool_calls 消息避免浪费断点;direct_native_tool_cache 分支把一个断点让给 tools 数组。strip_anthropic_cache_control() 支持 failover 后按新 provider 重贴(#72626)。
- **证据**:`agent/prompt_caching.py:382` · `agent/prompt_caching.py:47` · `agent/prompt_caching.py:338`
  ```
      remaining = 4 - breakpoints_used
      non_sys = [
  ```
- **规模**:394 行,纯函数无状态
- **学习价值**:高 — prompt cache 断点预算的精细分配(静态前缀 vs 滚动窗口 vs tools)+ 跨 provider 信封差异处理,是省 75% 输入成本的关键工程,细节极多值得深挖。
- **▲ 文档不符**:context-compression-and-caching.md 只描述旧的 "system_and_3" 布局(断点1=system + 最后3条),没有描述代码里默认的 静态前缀切分 + 末尾2条 的新布局(prompt_caching.py:1-8 与 348-364 明确说明静态前缀存在时用 前缀+system尾+末2条)。

#### 16. 凭据池轮换 (多 key/OAuth 池、状态机、冷却 TTL、跨进程同步、按状态码分级)  **[▲文档不符]**

- **解决**:同一 provider 可能有多把 API key 或多个 OAuth 账号;某把 key 被 429/401/402/billing 打死后要冷却并轮换到下一把,且要区分瞬时限流与真实计费耗尽,还要处理唯一 key 不能轮换、失败身份匹配不上任何 entry 时不能误伤健康 key、多 entry 共享同一 runtime key 要一起标死等边界。
- **实现**:CredentialPool(credential_pool.py:633)持有 PooledCredential 列表,mark_exhausted_and_rotate() 按 credential_id/api_key_hint 定位失败 entry;_exhausted_ttl() 按状态码分级冷却(401 短、429/默认基线、sole_credential 时瞬时限流缩短但 billing 保持满 bench);_unmatched_rotation_streak 上限一圈防 OAuth 401 无限空转(#70401);同一 runtime_api_key 的 sibling entry 一起标 exhausted;_available_entries() 在选择前从 credentials 文件/auth.json 同步其它进程刷新的 token(anthropic/nous/openai-codex/xai-oauth),Codex 还会 live-probe quota 是否提前 reopen(#43747)。策略经 get_pool_strategy() 读 fill_first/round_robin/least_used/random。
- **证据**:`agent/credential_pool.py:332` · `agent/credential_pool.py:2077` · `agent/credential_pool.py:2132`
  ```
      if error_code == 401:
          return EXHAUSTED_TTL_401_SECONDS
      base = EXHAUSTED_TTL_429_SECONDS if error_code == 429 else EXHAUSTED_TTL_DEFAULT_SECONDS
  ```
- **规模**:3147 行,单文件 harness 里最复杂的状态机之一
- **学习价值**:高 — 凭据池是长期无人值守 agent 的续命核心:冷却分级、跨进程 token 同步、身份匹配失败的有界回退,每一条都是被真实 issue 打磨出的,复用价值极高。
- **▲ 文档不符**:credential-pools.md 记录了 4 种策略,但未提及 sibling-key 一起标死、unmatched-rotation 有界回退、Codex quota 提前 reopen 的 live-probe 等续命细节。

#### 17. 错误分类器 (FailoverReason 枚举驱动恢复策略)  **[◇未见于文档]**

- **解决**:一个 API 错误可能意味着换 key、换模型、压缩上下文、降级图片、剥离 replay blob、退避重试或直接放弃——retry loop 不该自己去反复解析原始异常。
- **实现**:classify_api_error()(error_classifier.py:623)把异常归一成 ClassifiedError,携带 reason(FailoverReason 枚举,含 auth/billing/rate_limit/upstream_rate_limit/overloaded/context_overflow/image_too_large/invalid_encrypted_content/thinking_signature/oauth_long_context_beta_forbidden 等 20+ 类)和 retryable/should_compress/should_rotate_credential/should_fallback 四个动作提示位;_classify_by_status/_classify_402/_classify_400/_classify_by_message 分层判定,还能识别 OpenRouter upstream 错误把 upstream provider 名剥出来。
- **证据**:`agent/error_classifier.py:90` · `agent/error_classifier.py:36` · `agent/error_classifier.py:118`
  ```
      retryable: bool = True
      should_compress: bool = False
      should_rotate_credential: bool = False
      should_fallback: bool = False
  ```
- **规模**:1841 行
- **学习价值**:高 — 把"错误 → 恢复动作"用一个枚举 + 动作位集中判定,让 retry loop 只读结论不再解析,是错误恢复架构的教科书式解耦。

#### 18. Fallback model 链 (turn-scoped 多级 provider/model 切换 + 池重绑 + 缓存重评估)  **[▲文档不符]**

- **解决**:主模型持续报错时要按配置的 (provider, model) 链逐个切换,换 provider 时要重建 client、换 wire 协议、重绑凭据池防止污染主 provider、按新模型重评 prompt cache 与 context window,并对 rate_limit/billing 做指数退避冷却防止 replay 风暴。
- **实现**:try_activate_fallback()(chat_completion_helpers.py:1730)推进 _fallback_index 走 _fallback_chain;经 backend_identity.should_skip_candidate 跳过解析到同一后端的条目;经 resolve_provider_client 建新 client;rate_limit/billing/upstream_rate_limit 时 _rate_limited_until 按 60s*2^n 上限 4h 退避;换 provider 时清掉主 pool 再 load_pool(fb_provider)(#33163);anthropic 目标建原生 client,其余换 OpenAI client 并保留 default_headers;重评 _anthropic_prompt_cache_policy、更新 context_compressor、rewrite_prompt_model_identity 保持自我认知同步。
- **证据**:`agent/chat_completion_helpers.py:1756` · `agent/chat_completion_helpers.py:1946` · `agent/chat_completion_helpers.py:2020`
  ```
              backoff_count = getattr(agent, "_rate_limit_backoff_count", 0)
              agent._rate_limit_backoff_count = backoff_count + 1
              backoff_seconds = min(60 * (2 ** backoff_count), 14400)
  ```
- **规模**:activation 约 390 行(1730-2116)
- **学习价值**:高 — 跨 provider 热切换要同步的状态(client/协议/池/缓存/上下文窗/身份)一个都不能漏,这段代码枚举了所有需要一起翻转的运行时状态,是 fallback 实现的完整清单。
- **▲ 文档不符**:provider-runtime.md 的 activation-flow 写 "Returns False immediately if already activated",但代码并不在 _fallback_activated 为真时早退,而是靠 _fallback_index >= len(_fallback_chain) 判定链耗尽、逐条推进多级链——文档描述的是旧的单对 fallback 语义。

#### 19. 辅助 LLM 路由 (auxiliary_client:压缩/视觉/标题/搜索的独立 provider 链)  **[▲文档不符]**

- **解决**:压缩、视觉、web 抽取、会话搜索、标题生成等副 LLM 任务不应污染主对话模型的凭据/上下文,又要能默认复用用户主模型、支持 per-task 覆盖、有自己的 fallback 链、健康度缓存和并发上限。
- **实现**:_resolve_auto()(auxiliary_client.py:5391)优先用主 provider+主模型跑副任务,失败才走 openrouter→nous→custom→api-key 探测链(_get_provider_chain:3594);MoA 虚拟 provider 会解析成真实 aggregator;402 打过的 provider 进 _aux_unhealthy_until 缓存 10 分钟跳过;_try_configured_fallback_chain 读 auxiliary.<task>.fallback_chain 并用 backend_identity 的 FailureScope 区分 model 级 vs credential 级失败;per-task max_concurrency 用 BoundedSemaphore 限流;辅助 client 有专用的 Codex/Anthropic/Bedrock adapter shim。
- **证据**:`agent/auxiliary_client.py:3607` · `agent/auxiliary_client.py:3635` · `agent/auxiliary_client.py:5167`
  ```
      return [
          ("openrouter", _try_openrouter),
          ("nous", _try_nous),
          ("local/custom", _try_custom_endpoint),
          ("api-key", _resolve_api_key_provider),
  ```
- **规模**:9976 行,子系统最大文件
- **学习价值**:高 — 把"副任务用哪个模型"做成默认跟随主模型 + 独立 fallback + 健康缓存 + 并发闸,是多模型 agent 控成本控稳定性的关键,值得整体学习其分层。
- **▲ 文档不符**:provider-runtime.md 说辅助任务 "use their own independent provider auto-detection chain",但代码 Step 1 其实是默认复用主 provider+主模型,探测链仅在主模型无可用 client 时才启用——文档略去了 "默认跟随主模型" 这一优先层。

#### 20. Nous RPH 跨会话限流护栏 (防 429 重试放大)  **[◇未见于文档]**

- **解决**:Nous Portal 一次 429 会触发多达 9 次 API 调用(3 SDK retry × 3 Hermes retry),每次都吃 RPH 配额;且 CLI/gateway/cron/auxiliary 多会话并发时会各自重试放大限流。
- **实现**:nous_rate_guard.py 把限流状态写进 $HERMES_HOME/rate_limits/nous.json 共享文件(atomic_replace 原子写),所有会话在请求前 nous_rate_limit_remaining() 读该文件判断是否仍在冷却;record_nous_rate_limit() 按 x-ratelimit-reset-requests-1h > per-minute > retry-after 优先级解析 reset 时间,无 header 则默认 300s;is_genuine_nous_rate_limit() 用 header 桶区分真限流与误报。
- **证据**:`agent/nous_rate_guard.py:3` · `agent/nous_rate_guard.py:54`
  ```
  Writes rate limit state to a shared file so all sessions (CLI, gateway,
  cron, auxiliary) can check whether Nous Portal is currently rate-limited
  ```
- **规模**:325 行
- **学习价值**:中 — 用文件系统做跨进程限流广播是轻量而有效的 harness 技巧,避免重试放大对配额型 provider 尤其重要。

#### 21. Codex Responses 适配 (Harmony token 中和 + encrypted_content issuer 隔离)  **[◇未见于文档]**

- **解决**:ChatGPT Codex 后端保留 Harmony wire token,历史里出现字面量会被 invalid_prompt 拒;reasoning.encrypted_content 被封给签发它的端点,把 Codex 的 blob 回放给 xAI 会 400 invalid_encrypted_content。单会话切模型不能被不可解密的 reasoning 块污染。
- **实现**:codex_responses_adapter.py 的 _neutralize_harmony_tokens() 把 <|start|> 等保留 token 用全角竖线重写,并对 Category-Cf 隐藏字符做鲁棒处理(U+200B 会被后端剥离);_classify_responses_issuer() 给每个持久化 reasoning item 打 issuer 标签(xai_responses/github_responses/codex_backend/other:<base_url>),回放时按 issuer 过滤跨端点的 blob;chat<->Responses input 双向转换与 function_call id 的确定性生成。
- **证据**:`agent/codex_responses_adapter.py:83` · `agent/codex_responses_adapter.py:44`
  ```
  _HARMONY_CONTROL_TOKEN_RE = re.compile(
      r"<\|(start|end|channel|message|constrain|return|call)\|>"
  ```
- **规模**:1590 行
- **学习价值**:中 — encrypted_content 按签发端点隔离、Harmony 保留 token 中和,都是 Responses API 特有的坑,做多 provider 时不踩就会 400 满地。

#### 22. Provider profile 插件注册表 (声明式 ProviderProfile + 34 个内置 provider 插件)

- **解决**:20+ 推理 provider 的 auth/endpoint/quirk 若用一堆布尔 flag 传给 transport 会失控;还要支持用户在 $HERMES_HOME 下覆盖内置 provider 而不改仓库代码。
- **实现**:ProviderProfile(providers/base.py:38)声明式承载 name/api_mode/env_vars/base_url/fallback_models/supports_vision/fixed_temperature/default_aux_model 及 prepare_messages/build_extra_body/build_api_kwargs_extras/fetch_models 等可覆写 hook;providers/__init__.py 惰性扫描 plugins/model-providers/<name>/(内置 34 个:openrouter/anthropic/nous/openai-codex/gemini/bedrock/vertex/xai/zai/kimi-coding/minimax… 每个 __init__.py 调 register_provider 自注册)+ $HERMES_HOME 用户插件(last-writer-wins 覆盖)+ 遗留 providers/*.py。OpenRouter profile 覆写 build_api_kwargs_extras 处理 Claude 4.6+ 强制 reasoning 的 verbosity 映射。
- **证据**:`providers/base.py:43` · `providers/__init__.py:62` · `plugins/model-providers/openrouter/__init__.py:169`
  ```
      name: str
      api_mode: str = "chat_completions"
  ```
- **规模**:base.py 238 行 + 34 个插件目录(13-213 行不等)
- **学习价值**:高 — 声明式 profile + 插件自注册 + 用户覆盖,是把 provider 差异从 transport 里彻底剥离的干净架构,新增 provider 零改 loop 代码,复用价值高。

#### 23. 用量归一与定价 (跨 4 种 usage 形状 + 官方定价快照 + Codex reset credit 兑换)  **[◇未见于文档]**

- **解决**:Anthropic/Codex Responses/OpenAI Chat/各 OpenAI-兼容代理的 usage 字段形状各异(cache read/write、reasoning token 藏在不同嵌套里),要归一成统一 token 桶算成本;Codex 账号还有"banked reset credit"可兑换以恢复配额窗口。
- **实现**:normalize_usage()(usage_pricing.py:1205)按 api_mode 分三支解析,OpenAI 支还回退读 Anthropic 风格顶层字段(OpenRouter/Vercel 代理 Claude)和 DeepSeek 的 prompt_cache_hit_tokens,reasoning token 同时读 output_tokens_details 和 completion_tokens_details 两种形状;get_pricing_entry 优先官方 docs 快照 _OFFICIAL_DOCS_PRICING 再 metadata/OpenRouter。account_usage.py 的 redeem_codex_reset_credit() 复刻 Codex CLI:GET usage 读 banked 数与窗口使用率,未耗尽则拒绝(除非 --force),POST consume 带 uuid 幂等键兑换。
- **证据**:`agent/usage_pricing.py:1261` · `agent/account_usage.py:670`
  ```
              cache_read_tokens = _to_int(
                  getattr(response_usage, "prompt_cache_hit_tokens", 0)
  ```
- **规模**:usage_pricing 1432 行 + account_usage 902 行
- **学习价值**:中 — usage 归一化的 provider 形状差异极多(cache/reasoning token 藏法各异),是准确记账的隐形工作量;Codex reset credit 兑换是罕见的 provider 计费 API 对接。

#### 24. 模型元数据探测与缓存 (models.dev 目录 + 本地端点 num_ctx 探测 + 从错误反推上下文窗)

- **解决**:上下文窗口/最大输出/定价/能力位要么来自 models.dev 社区目录,要么要向本地端点(Ollama/LM Studio/vLLM)实时探测,还要在 context_length_exceeded 报错里反推真实上限以做逐级降档。且不能因网络失败阻塞热路径。
- **实现**:models_dev.py 三级取数(内存缓存→磁盘缓存任意年龄→仅在完全无缓存时联网,失败退避 5 分钟,后台守护线程刷新);model_metadata.py 的 fetch_endpoint_model_metadata 向端点 /models 拉,query_ollama_num_ctx / detect_local_server_type 探测本地服务;parse_context_limit_from_error() 用多个正则从 vLLM/各家报错文本抽 max_model_len,get_next_probe_tier 走 CONTEXT_PROBE_TIERS 逐级降档;端点 blackhole 缓存避免反复打死端点。
- **证据**:`agent/models_dev.py:12` · `agent/model_metadata.py:1518`
  ```
    1. In-memory cache (fresh, or stale served immediately while a single
       background daemon thread refreshes)
  ```
- **规模**:model_metadata 3370 行 + models_dev 903 行
- **学习价值**:中 — stale-while-revalidate 缓存 + 从 provider 报错文本反推上下文上限,是 agent 在异构端点上稳定运行的实用手法。

#### 25. Bedrock / Vertex / Azure Entra 企业端点适配

- **解决**:AWS Bedrock 用 boto3 Converse 而非 HTTP、需 stale-connection 检测与 client 失效重建;Vertex 用 GCP service-account JWT;Azure Foundry 支持 keyless 的 Entra ID bearer,而 Anthropic SDK 只接受静态字符串 key 无 callable-token 契约。
- **实现**:bedrock_adapter.py 提供 converse/converse_stream 封装 + normalize 成 OpenAI 形状、is_stale_connection_error 触发 invalidate_runtime_client 重建、discover_bedrock_models 发现推理 profile;vertex_adapter.py 惰性装 google-auth 换 access token 走 OpenAI-兼容端点;azure_identity_adapter.build_token_provider 返回零参 callable,anthropic_adapter._build_anthropic_client_with_bearer_hook 给 SDK 塞一个 httpx 请求 event hook 每次请求现铸 JWT 重写 Authorization 头(SDK 无 callable 契约的绕行)。
- **证据**:`agent/chat_completion_helpers.py:501` · `agent/anthropic_adapter.py:707`
  ```
              if is_stale_connection_error(_bedrock_exc):
                  invalidate_runtime_client(region)
  ```
- **规模**:bedrock 1573 + vertex 228 + azure_identity 571 行
- **学习价值**:中 — 给只吃静态 key 的 SDK 用 httpx event hook 注入 per-request bearer,是对接企业 keyless 认证的通用绕行技巧。

#### 26. Anthropic OAuth / Claude Code 身份伪装与凭据刷新  **[◇未见于文档]**

- **解决**:用 Anthropic OAuth/setup-token 访问时,Anthropic 按 user-agent 与 header 路由,缺 Claude Code 指纹会间歇 500;还要区分 sk-ant OAuth token、第三方代理 key、MiniMax/Kimi 的 Bearer-auth 端点,并支持从 keychain/文件读 Claude Code 凭据、PKCE 刷新 OAuth token。
- **实现**:build_anthropic_client()(anthropic_adapter.py:777)按 base_url/key 形状选 auth:Kimi coding 端点强制 User-Agent claude-code/0.1.0;_requires_bearer_auth 端点走 auth_token;OAuth token 走 auth_token + anthropic-beta + user-agent claude-code/<ver> (external, cli) + x-app cli 指纹;并清 env 填入的 api_key 防 x-api-key 与 Bearer 双认证。read_claude_code_credentials 从 keychain/文件读,refresh_anthropic_oauth_pure 做 PKCE 刷新;max_retries=0 把重试交给外层 loop 以尊重 Retry-After。
- **证据**:`agent/anthropic_adapter.py:891` · `agent/anthropic_adapter.py:863`
  ```
          kwargs["auth_token"] = api_key
          kwargs["default_headers"] = {
  ```
- **规模**:3177 行
- **学习价值**:中 — OAuth 订阅路径必须模拟 Claude Code 客户端指纹才稳定,以及把 SDK 重试关掉交给外层尊重 Retry-After,都是 Anthropic 原生接入的实战细节。

#### 27. 插件 LLM 门面 (plugin_llm 信任门控 + relay_llm 托管执行)

- **解决**:可信插件需要自己发 LLM 调用(hook 改写错误、gateway 适配翻译等),但绝不能看到原始 OAuth/API key,也不能随意 override provider/model/agent/profile;同时物理 provider 尝试要能走 NeMo Relay 做托管执行与记账。
- **实现**:plugin_llm.py 把 ctx.llm.complete/complete_structured 暴露给插件,_TrustPolicy + _resolve_trust_policy 从 config.yaml plugins.entries.<id>.llm 读 allow_*_override 与 allowlist,缺配置即 fail-closed 全默认拒绝;底层复用 auxiliary_client.call_llm 由 host 掌握路由/auth/fallback。relay_llm.py 的 execute/stream 把每次物理 provider 尝试包进 runtime.relay.llm.execute 托管执行,ManagedLlmStream 与 AnthropicStreamAccumulator 处理流式与逻辑调用完成。
- **证据**:`agent/plugin_llm.py:205` · `agent/relay_llm.py:38`
  ```
      Missing config → fully restrictive policy (default deny on every
      override). The policy is resolved per-call rather than cached so
  ```
- **规模**:plugin_llm 1046 + relay_llm 1239 行
- **学习价值**:中 — 给插件开放 LLM 能力又不泄露凭据、用 fail-closed 信任门控,是安全暴露 host 能力的范式;relay 托管执行则是可观测/记账的接入点。

**本子系统文档-代码冲突(3 条):**

- 宣称:context-compression-and-caching.md:396 描述 prompt cache 用 "system_and_3" 布局:断点1=system prompt,断点2-4=最后3条非 system 消息的滚动窗口。
  实际:prompt_caching.py 默认布局是 静态 system 前缀 + system 尾 + 最后2条消息(4 断点),仅在无静态前缀时才回退到 system+末3条;还有 direct_native_tool_cache 分支把一个断点让给 tools 数组。文档只写了回退布局。(证据:`agent/prompt_caching.py:1`)
- 宣称:provider-runtime.md:180 fallback activation flow 写 "Returns False immediately if already activated or not configured"。
  实际:try_activate_fallback 不在 _fallback_activated 为真时早退,而是靠 _fallback_index >= len(_fallback_chain) 判定多级链是否耗尽并逐条推进——文档描述的是旧的单对 fallback 语义,与现在的多级链实现不符。(证据:`agent/chat_completion_helpers.py:1764`)
- 宣称:provider-runtime.md:196 写辅助任务 "use their own independent provider auto-detection chain",暗示副任务用独立探测链选 provider。
  实际:_resolve_auto Step 1 默认直接用主 provider+主模型跑副任务,openrouter→nous→custom→api-key 探测链仅在主模型无可用 client 时才作为兜底启用。文档略去了"默认跟随主模型"这一优先层。(证据:`agent/auxiliary_client.py:5437`)

### 2.3 上下文工程(压缩/构建/预算)

该子系统覆盖 Hermes-Agent 上下文生命周期的全部三个环节:构建(system_prompt.py + prompt_builder.py 按 stable/context/volatile 三层缓存分带组装系统提示,并注入 SOUL.md/.hermes.md/AGENTS.md/CLAUDE.md/.cursorrules 等上下文文件,注入前经威胁扫描)、预算(context_breakdown.py 的 /context 分解、prompt_builder 的动态字符上限、compressor 的 threshold/tail budget 推导)、压缩(context_engine.py 定义可插拔 ContextEngine ABC,context_compressor.py 的 6883 行内置引擎实现阈值触发的三段式批量压缩、确定性工具结果剪枝、可选逐轮 micro-compaction,conversation_compression.py 负责 host 侧编排:会话锁、commit fence、进度感知超时、in-place archive_and_compact 落库与系统提示保留)。整个设计被一条核心约束贯穿:prompt cache 不许无谓破坏——系统提示一旦生成就整会话冻结(日期只精确到天)、压缩是唯一允许改写历史的时刻、proactive prune 与 micro-compact 都以"cache 断点是否值得付"作为提交门槛。外围文件处理请求级卫生(message_sanitization、think_scrubber、bounded_response、message_content)与用户侧引用展开(context_references 的 @file/@url),根目录 trajectory_compressor.py 则是同一套"保头保尾压中间"思想在离线训练数据上的复刻。

关键文件(16 个,行数实测,余见 JSON):`agent/context_compressor.py`(6883), `agent/conversation_compression.py`(4014), `agent/context_engine.py`(489), `agent/context_breakdown.py`(360), `agent/context_references.py`(605), `agent/prompt_builder.py`(2206), `agent/system_prompt.py`(685), `agent/bounded_response.py`(148)


#### 28. 三层缓存分带的系统提示组装

- **解决**:系统提示既要装身份/工具指导/工作区快照/技能索引/记忆等大量动态内容,又必须让上游 prompt cache(显式 cache_control 与隐式最长前缀两类后端)每轮命中;任意一处字节变化都会从该点起废掉 KV 缓存。
- **实现**:build_system_prompt_parts 把提示切成 stable(跨会话稳定的身份+指导)/context(cwd 相关:workspace 快照、上下文文件)/volatile(技能索引、记忆、时间戳)三个有序带,按'最易变的放最后'排序;整串在 build_system_prompt 中缓存到 agent._cached_system_prompt,整会话不再重渲染,仅压缩边界经 invalidate_system_prompt 重建;时间戳只精确到日期,保证提示全天字节稳定。coding_context 把 git 工作区快照单独放进 context 带,使 stable 前缀跨会话可复用。
- **证据**:`agent/system_prompt.py:554-558` · `agent/system_prompt.py:537-540` · `agent/system_prompt.py:166-168`
  ```
      return {
          "stable":   "\n\n".join(p.strip() for p in stable_parts   if p and p.strip()),
          "context":  "\n\n".join(p.strip() for p in context_parts  if p and p.strip()),
          "volatile": "\n\n".join(p.strip() for p in volatile_parts if p and p.strip()),
      }
  ```
- **规模**:system_prompt.py 685 行 + prompt_builder.py 2206 行 + coding_context.py 916 行;复杂度中高——分带排序规则、缓存失效点、静态前缀重建都要互相咬合
- **学习价值**:高 — 把系统提示当成缓存层级来设计(稳定度分带 + 日期粒度时间戳 + 整会话冻结)是 agent harness 里少见的、可直接迁移的成本工程手法;AGENTS.md 只写了'缓存不许破'的政策,分带机制本身只存在于代码。

#### 29. 项目上下文文件注入(AGENTS.md/CLAUDE.md 等)  **[▲文档不符]**

- **解决**:agent 需要在启动时拿到项目规范(AGENTS.md/CLAUDE.md/.cursorrules 等),但要解决三个问题:多种约定并存时选哪个、大文件挤爆小上下文模型、以及上下文文件本身可能携带 prompt 注入。
- **实现**:build_context_files_prompt 用'第一个命中即胜'的优先级链加载唯一一种项目上下文(.hermes.md 走到 git root,其余仅 cwd 顶层),SOUL.md 独立注入;每个文件先过 _scan_context_content 威胁扫描(命中即整体替换为 [BLOCKED] 占位),再按 _dynamic_context_file_max_chars 头尾截断——无显式配置时上限随模型窗口缩放(floor 20K、ceiling 500K 字符),截断警告经 ContextVar 收集后回显给用户;fallback 到 Hermes 安装树的 cwd 会被拒绝以免加载本仓贡献者 AGENTS.md。
- **证据**:`agent/prompt_builder.py:2189-2194` · `agent/prompt_builder.py:74-77` · `agent/prompt_builder.py:1306-1309`
  ```
          project_context = (
              _load_hermes_md(cwd_path, context_length)
  ```
- **规模**:prompt_builder.py 中约 300 行(扫描/发现/加载/截断)+ threat_patterns 共享库;复杂度中
- **学习价值**:中 — 优先级链、随窗口缩放的截断预算、注入前威胁扫描三件套是上下文文件注入的完整答案;'截断时留 read_file 恢复路径'的细节值得抄。
- **▲ 文档不符**:website/docs/user-guide/configuration.md:2303 称 AGENTS.md 为 'Recursive directory walk'、:2311 称 'AGENTS.md is hierarchical: if subdirectories also have AGENTS.md, all are combined'——代码中 _load_agents_md 明确 'top-level only (no recursive walk)'(prompt_builder.py:2062),子目录 AGENTS.md 只由 SubdirectoryHintTracker 在工具调用时懒发现并注入 tool result,并非启动时合并;:2313 'capped at context_file_max_chars characters (default 20,000)' 也与动态默认(null→随窗口 20K-500K)相悖,同文档 :671 自己都写了动态默认。

#### 30. 渐进式子目录上下文发现

- **解决**:monorepo 里每个子目录可能有自己的 AGENTS.md;启动时全量装入会撑爆系统提示,且中途改系统提示会破 prompt cache。
- **实现**:SubdirectoryHintTracker 监听每次工具调用的路径参数(含 terminal 命令的 shlex 拆词),对新目录及最多 5 层祖先按 AGENTS.md→CLAUDE.md→.cursorrules 优先级加载一个 hint,追加到 tool result(不动系统提示);SHA-256 内容摘要去重(symlink/备份副本只注入一次)、排除 node_modules/vendor/backup 等目录、拒绝工作区之外的路径以防 ~/.claude/CLAUDE.md 跨 agent 污染,每目录一次、单文件 8K 字符封顶,并复用同一威胁扫描。
- **证据**:`agent/subdirectory_hints.py:30-34` · `agent/subdirectory_hints.py:294-296` · `agent/subdirectory_hints.py:10-11`
  ```
  _HINT_FILENAMES = [
      "AGENTS.md", "agents.md",
  ```
- **规模**:341 行独立模块;复杂度低中
- **学习价值**:中 — '把新上下文注入 tool result 而非系统提示'是 cache 友好的上下文追加范式(借鉴 Block/goose),摘要去重与工作区边界防污染是容易漏掉的工程细节。

#### 31. 可插拔 ContextEngine 抽象与每轮上下文选择钩子  **[◇未见于文档]**

- **解决**:不同的长上下文策略(摘要压缩、DAG、检索式选择)需要可替换,且第三方引擎曾被迫让 should_compress() 恒真来蹭 compress() 当每轮回调,把'选择上下文'与'压缩上下文'混为一谈。
- **实现**:context_engine.py 定义 ABC:必选 update_from_response/should_compress/compress,可选 prune_tool_results_only、select_context(请求级替换消息列表,运行在 cache-control 与 sanitizer 之前,默认 no-op 保证字节不变)、on_turn_complete(带 usage 的轮末观察)、get_tool_schemas/handle_tool_call(引擎自带工具如 lcm_grep)。plugins/context_engine/ 目录按 register(ctx) 或 ContextEngine 子类两种模式发现加载,config 的 context.engine 单选,_EngineCollector 还能把引擎的斜杠命令转发进全局插件命令表。
- **证据**:`agent/context_engine.py:215-221` · `agent/context_engine.py:249-251` · `plugins/context_engine/__init__.py:33-36`
  ```
      def select_context(
          self,
  ```
- **规模**:context_engine.py 489 行 + 插件加载器 286 行;复杂度中——难点在钩子与 cache/sanitizer 的排序契约
- **学习价值**:中 — 把'压缩(太长→变短)'与'选择(本轮属于另一份上下文)'拆成正交动词,并在 docstring 里写死与 prompt cache/请求 sanitizer 的排序契约,是上下文引擎接口设计的好范本;AGENTS.md 只提到插件目录存在,select_context/on_turn_complete 契约全在代码里。

#### 32. 压缩触发决策:双重测量去噪 + 防抖断路器  **[▲文档不符]**

- **解决**:触发要同时依赖两种度量(请求前的粗估与 provider 返回的真实 prompt_tokens),粗估对 schema 重的请求刻意高估会引发刚压完又压;而系统提示+工具 schema 是不可压缩地板,地板本身超阈值时每轮都'成功压缩却仍超标',陷入无限压缩循环。
- **实现**:should_compress_info 返回 (bool, reason),reason 暴露 cooldown:<s>/ineffective 供上层警告用户;should_defer_preflight_to_real_usage 在压缩后置 awaiting_real_usage_after_compression 恰好推迟一轮,让真实用量到达后再判;防抖裁决只在 update_from_response 里用真实 prompt_tokens 打分('是否降到阈值下'而非'消息数是否变少'),连续 2 次无效或 2 次 fallback 边界即熔断,熔断经 _ANTI_THRASH_RECOVERY_SECONDS 后放一次试探(probation probe);cooldown/streak/strike 三类护栏写穿 SessionDB,同会话的兄弟 agent 共享,重启不解除。另有 aux 模型可行性检查:压缩模型窗口小于主模型阈值时就地下调 threshold_tokens 与 tail 预算。
- **证据**:`agent/context_compressor.py:2629-2634` · `agent/context_compressor.py:2513-2517` · `agent/context_compressor.py:2733-2736` · `agent/conversation_compression.py:1699-1701`
  ```
          tokens = prompt_tokens if prompt_tokens is not None else self.last_prompt_tokens
          if tokens < self.threshold_tokens:
              return False, None
          if self._automatic_compression_blocked():
              return False, self._compression_block_reason() or "blocked"
  ```
- **规模**:context_compressor.py 中约 600 行(触发/裁决/护栏/持久化)+ conversation_compression 的可行性检查约 250 行;复杂度高
- **学习价值**:高 — 这是'压缩会失败且会空转'这一现实的完整工程答案:真实用量裁决、一轮延迟去噪、双计数熔断、限时试探恢复、跨进程持久化护栏——每一层都对应一个真实 issue 编号,任何自建 harness 都会踩同样的坑。
- **▲ 文档不符**:configuration.md 只以一句 'honors the same failure-cooldown, anti-thrash, and per-session lock guards' 带过;<10% 两连击熔断、probation probe、粗估/真实双测量去噪机制文档均未描述。

#### 33. 三段式批量压缩管线(头保护衰减/token 预算尾部/边界对齐)

- **解决**:把超长对话压回预算内,同时不能:切断 tool_call/tool_result 配对(provider 400)、丢掉最新的用户任务与助手回复、让早期轮次在多次压缩中'化石化'永生、或把上一次的 handoff 摘要当普通消息层层堆叠。
- **实现**:compress() 五阶段:①确定性剪枝+删除平台空回显;②边界计算——头保护在首次压缩后衰减为 0(仅留系统提示,#11996),尾部按 tail_token_budget(threshold×summary_target_ratio)反向累加、1.5x 软顶避免切在超大消息中间,_align_boundary_backward/forward 保证不劈开工具组,再用锚点链保证最新 user/assistant 消息必在尾部;③扫描并回收窗口内旧 handoff 摘要(rehydrate 进 _previous_summary,merged handoff 拆回真实内容,防化石堆叠);④生成/迭代更新摘要,失败时按 auth/network/config 分类决定 abort(原样返回)或确定性 fallback;⑤重组:系统提示追加 compaction note、_strip_historical_media 清掉历史图像 base64、_sanitize_tool_pairs 清孤儿配对。
- **证据**:`agent/context_compressor.py:6148-6152` · `agent/context_compressor.py:4759-4760` · `agent/context_compressor.py:1568-1570` · `agent/context_compressor.py:6447-6451` · `agent/context_compressor.py:6785`
  ```
          compress_start = self._protect_head_size(messages)
          compress_start = self._align_boundary_forward(messages, compress_start)
  
          # Use token-budget tail protection instead of fixed message count
          compress_end = self._find_tail_cut_by_tokens(messages, compress_start)
  ```
- **规模**:compress() 本体约 830 行,加边界/锚点/摘要扫描辅助约 1500 行;复杂度极高
- **学习价值**:高 — 教科书级的'保头保尾压中间'完整实现:头保护衰减防化石化、token 预算而非条数定尾、工具组对齐防孤儿、旧摘要回收防堆叠、按失败类别决定 abort-vs-fallback,每个决策都有 issue 号背书。

#### 34. 摘要消息的角色交替修复与 provider 兼容护栏  **[◇未见于文档]**

- **解决**:压缩摘要作为一条合成消息插回对话后,必须同时满足:Mistral 严格模板的 user/assistant 交替(且模板会跳过 tool 消息)、Anthropic/Bedrock 首条可见消息必须是 user、vLLM/Qwen 拒绝零 user 文本请求(400 No user query found);弱模型还会把摘要里引用的历史用户请求当新指令执行。
- **实现**:以 _template_visible_role(而非字面相邻消息)计算摘要两侧的模板可见角色,优先与头部交替、与尾部碰撞时翻转,两边都碰撞则把摘要合并进首条尾部消息;compress_start==0 或头是 system 时强制 user 开头(#52160);若压缩后头尾都不存在非空文本的 user 消息则强制摘要落 user 槽(#58753,图像-only user 消息不算存活);独立插入的摘要统一追加 _SUMMARY_END_MARKER,防弱模型把 '## Active Task' 引文当新输入(#11475)或把摘要复述为自己的输出(#33256);COMPRESSED_SUMMARY_HAS_USER_TURN_KEY 元数据记录零 user 出处,防迭代摘要凭空捏造用户请求(#64650)。
- **证据**:`agent/context_compressor.py:6661-6668` · `agent/context_compressor.py:6615` · `agent/context_compressor.py:6696-6697`
  ```
          if (
              last_head_role is None
              or last_head_role in {"assistant", "tool"}
              or _force_user_leading
          ):
  ```
- **规模**:compress() 内约 250 行角色/合并逻辑 + _template_visible_role 等辅助;复杂度高
- **学习价值**:高 — '往对话里插一条合成消息'在多 provider 环境下的全部隐性约束都被枚举并解决了——交替模板、首 user 强制、零 user 400、摘要被误当指令/被复述——是任何做压缩/注入的 harness 都会逐一撞上的暗礁,官方文档只字未提。

#### 35. 结构化 handoff 摘要生成(迭代更新/时间锚定/记忆注入/ghost-skill 防护)  **[◇未见于文档]**

- **解决**:摘要不是普通总结:要逐字保住用户最新未完成请求、防止把已完成动作写成待办导致复跑、不能翻译用户语言、不能泄露密钥、不能让'已被剪枝的 skill 指令'在摘要里被改写成模糊描述而丢失重载提示,零 user 会话不能捏造用户。
- **实现**:_generate_summary 用固定分节模板(Historical Task/Goal/Completed Actions/Active State/Blocked/Key Decisions/Relevant Files/Critical Context…),存在旧摘要时走迭代更新;按 _transcript_has_real_user_turn 切换双版本指令(零 user 时强制写 sentinel、禁写 User asked);TEMPORAL ANCHORING 规则把已完成动作改写成带日期的过去式事实;memory provider 的 on_pre_compress 返回文本经 sanitize_memory_context 脱敏截断后以 JSON 字符串+HTML 转义包进 <memory-provider-context>,声明'仅作素材不作指令';[SKILL_PRUNED:] 标记在调用前确定性收集、调用后 _reinject_pruned_skill_markers 回注;focus_topic 与旧摘要过 _redact_compaction_text 强制脱敏;摘要预算按被压内容 20% 缩放,封顶窗口 5%。
- **证据**:`agent/context_compressor.py:3749-3752` · `agent/context_compressor.py:3621-3625` · `agent/context_compressor.py:3615-3618` · `agent/conversation_compression.py:2750-2754`
  ```
              _temporal_anchoring_rule = (
                  f"\nTEMPORAL ANCHORING: The current date is {_today_str}. When an "
  ```
- **规模**:_generate_summary 及模板/序列化/回注辅助约 900 行;复杂度高
- **学习价值**:中 — 展示了 handoff 摘要 prompt 的成熟形态:结构化模板+逐字引用最新请求+反向信号(stop/undo)优先+时间锚定防复跑;'LLM 会把确定性标记改写成模糊描述,所以调用前收集、调用后回注'是对抗摘要模型的通用技巧,细节全部不在文档。

#### 36. 确定性工具结果剪枝与 proactive prune 的 prompt-cache 滞回  **[▲文档不符]**

- **解决**:大窗口模型上 50% 阈值的批量压缩很少触发,旧工具输出(终端 dump、文件读取)每轮原样重发;但任何改写已发送历史的剪枝都会从改写点起废掉 provider 的 prompt-cache 前缀,繁忙工具循环里若每轮都剪就等于每轮破缓存。
- **实现**:_prune_old_tool_results 四个确定性 pass(零 LLM):①MD5 去重,旧副本替换为回引(全表扫描含保护尾,因去重无损);②非尾部大工具结果替换为 1 行摘要([terminal] ran `npm test` -> exit 0…);③截断超大 tool_call 参数但保持合法 JSON;④保护尾内'压力降级'——保护区超软顶 1.5x 时连尾内大输出也降级(#61932),skill_view 的 ghost-skill 保护此时被覆盖。独立入口 prune_tool_results_only 由低触发线 proactive_prune_tokens 驱动,提交前需满足 min_reclaim_tokens(默认 4096),提交后设 rearm 水位 = after + max(reclaimed, trigger, min_reclaim) 并写穿 DB,强制历史重新长满一个触发量才允许下一次 cache-breaking 改写,并要求 archive_and_compact 原子落库,否则整体 no-op。
- **证据**:`agent/context_compressor.py:2886-2890` · `agent/context_compressor.py:3144-3146` · `agent/context_compressor.py:3151-3156` · `agent/context_compressor.py:3011-3013`
  ```
              h = hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()[:12]
              if h in content_hashes:
                  # This is an older duplicate — replace with back-reference
                  result[i] = {**msg, "content": "[Duplicate tool output — same content as a more recent call]"}
                  pruned += 1
  ```
- **规模**:约 700 行(_prune_old_tool_results + prune_tool_results_only + 摘要行生成);复杂度高
- **学习价值**:高 — '确定性剪枝先于 LLM 摘要'与'把 cache 断点当预算管理(最小回收门槛 + rearm 滞回)'是大窗口时代最实用的两条上下文成本策略;压力降级 pass④ 解决的'保护尾自身撑爆预算'死角文档未提。
- **▲ 文档不符**:configuration.md:840 记录了 proactive prune 三参数,但压缩内部的第 4 个压力降级 pass(#61932,保护尾内降级、skill 保护被覆盖)与 ghost-skill 保护机制未见于任何文档。

#### 37. Micro-compaction 逐轮滚动压缩

- **解决**:批量压缩是一次性大爆破:触发时要同步等一个大摘要调用,用户明显感知卡顿;希望把这笔账分期——在每轮结束的空闲时间吸收一小段历史。
- **实现**:默认关闭(compression.micro_compact),因为每个 pass 都改写已发送历史、每轮破一次 prompt-cache 前缀;开启后 finalize_turn 里 _micro_compact 每 N 轮取滚动摘要游标后的最旧一个 exchange,序列化后经 aux 模型并入滚动摘要,splice 回 transcript 并 archive_and_compact 原子落库;摘要变'臃肿'时触发 defrag(原地重写摘要文本,不动游标);同游标连续失败 3 次跳过该 exchange;恢复会话时从 marker 文本 rehydrate 滚动摘要;批量压缩完成后整套 micro 状态重置,防止旧滚动摘要 supersede 掉信息更多的批量 marker。
- **证据**:`agent/context_compressor.py:2346-2350` · `agent/context_compressor.py:5656-5657` · `agent/context_compressor.py:6854-6858`
  ```
          # ── Micro-compaction (per-turn rolling compaction) ─────────
          # Default: OFF. Each pass rewrites already-sent history, so it breaks
  ```
- **规模**:约 450 行(游标解析/exchange 切分/微摘要/defrag/splice/DB 同步/遥测);复杂度高
- **学习价值**:中 — '分期付账 vs 一次爆破'的第三种压缩节奏,且诚实地把 prompt-cache 代价写进默认值决策(默认关);滚动摘要 defrag 与批量压缩的状态互斥是多压缩机制共存时的关键协调点,docs/micro-compaction.md 有专页。

#### 38. 压缩执行基础设施:锁/栅栏/超时/in-place 落库/keep-prompt  **[▲文档不符]**

- **解决**:压缩是唯一改写持久化会话状态的操作,又依赖一个可能挂死的外部摘要 LLM:并发的兄弟 agent 会双压同一会话造成孤儿分叉;超时后迟到的 worker 不能再提交;摘要模型慢但健康不该被杀;压缩后重建系统提示会白白破坏本地后端 KV 缓存。
- **实现**:compress_context 以 state.db 原子压缩锁(按旧 session_id 键)串行化并发压缩,CompressionCommitFence 把生命周期切成 pre-commit(可取消)与 commit(必须完成、超限只告警)两段,run_compress_context_with_progress_timeout 用'流式 token 即进展'的 inactivity 预算+总天花板在共享守护线程池上跑 worker,池满时拒绝新任务而非排队(pool_saturated 遥测);默认 in_place 模式经 archive_and_compact 把旧行软归档(active=0,可搜索可恢复)、压缩集原子写为新 active 行,session id 终身不变;压缩后若缓存系统提示仍逐字包含重载后的记忆块则原样保留(keep-prompt),避免重建破坏本地 KV 前缀,否则才重建。
- **证据**:`agent/conversation_compression.py:887-889` · `agent/conversation_compression.py:3141-3147` · `agent/conversation_compression.py:3200-3202` · `agent/conversation_compression.py:2287`
  ```
      if not _try_admit_compression_job():
          logger.warning(
              "Context compression pool saturated (%d workers busy) — "
  ```
- **规模**:conversation_compression.py 4014 行的主体;复杂度极高(锁租约刷新线程、心跳、遥测、rotation 兼容路径并存)
- **学习价值**:高 — 把'调用一个可能挂死的 LLM 来改写持久状态'做成了事务系统:两段式栅栏、进展感知超时、有界准入、软归档式 in-place 提交——是 harness 里最少被讨论但最容易出数据事故的部分;keep-prompt 的逐字包含判定(而非快照对等)文档完全未提。
- **▲ 文档不符**:configuration.md 记录了 in_place 与各超时参数,但 CompressionCommitFence 两段式提交、池饱和拒绝、keep-prompt KV 保留、压缩锁租约刷新等机制均无文档。

#### 39. 离线训练轨迹压缩器(trajectory_compressor.py)

- **解决**:训练数据侧:采出的 agent 轨迹超过训练序列长度预算(如 15250 token),直接截断会丢训练信号;需要在保住任务设定与结局的前提下把中段压进预算。
- **实现**:与运行时压缩同构的'保头保尾压中间':保护首 system/human/gpt/tool 与最后 N 轮,从第二个 tool response 起只压'刚好够'的中段,用 HF tokenizer(默认 Kimi-K2-Thinking)精确计数而非 char/4 粗估,经 OpenRouter(默认 gemini-3-flash)生成单条 human 角色摘要替换被压区,边界经 _snap_boundary 对齐干净的轮次;支持目录/JSONL/采样率批处理、每轨迹超时、并发上限与压缩率指标输出(compression_metrics.json)。
- **证据**:`trajectory_compressor.py:9-13` · `trajectory_compressor.py:512-513` · `trajectory_compressor.py:90-91`
  ```
  1. Protect first turns (system, human, first gpt, first tool)
  2. Protect last N turns (final actions and conclusions)
  ```
- **规模**:1598 行独立脚本;复杂度中
- **学习价值**:中 — 同一压缩思想在'在线推理(粗估、容错优先)'与'离线训练(精确 tokenizer、指标优先)'两种约束下的对照实现,说明 harness 的上下文策略可以直接反哺训练数据工程;README 仅一句带过。

**本子系统文档-代码冲突(3 条):**

- 宣称:website/docs/user-guide/configuration.md:2303 的表格称 AGENTS.md 作用域为 'Recursive directory walk',:2311 进一步称 '**AGENTS.md** is hierarchical: if subdirectories also have AGENTS.md, all are combined.'
  实际:启动时 _load_agents_md 只读 cwd 顶层('AGENTS.md — top-level only (no recursive walk)');只有 .hermes.md/HERMES.md 才向上走到 git root。子目录 AGENTS.md 由 SubdirectoryHintTracker 在工具调用触及该目录时才懒发现,注入的是 tool result 而非系统提示,从不'合并'为一份。website/docs/user-guide/features/context-files.md 与 which-file-does-what.md 的描述是对的,configuration.md 这两行是陈旧表述。(证据:`agent/prompt_builder.py:2062`)
- 宣称:website/docs/user-guide/configuration.md:2313:'All loaded context files are capped at `context_file_max_chars` characters (default 20,000) with smart truncation.'
  实际:context_file_max_chars 默认是 null:无显式配置时上限由 _dynamic_context_file_max_chars 按模型窗口动态缩放(floor 20,000、ceiling 500,000 字符),20K 只是下限而非默认值;同一文档 :671 自己写的默认就是 'dynamic cap scaled to the model's context window',:2313 是同文档内的陈旧残留。(证据:`agent/prompt_builder.py:1309`)
- 宣称:AGENTS.md:1140:'The ONLY time we alter context is during context compression.'(Prompt Caching Must Not Break 政策)
  实际:严格说改写已发送历史的路径有三条:批量 compress()、proactive prune_tool_results_only(独立于压缩阈值的无 LLM 剪枝)、micro-compaction(每 N 轮改写一次)。后两者虽同属 compressor 所有并各自设置了 cache 滞回/节奏门槛(代码注释自认 'a committed prune rewrites message bodies the provider has already seen … exactly like a compression boundary'),但按字面'仅压缩时改上下文'的说法已不完全成立,政策文字未更新以涵盖这两条 opt-in 路径。(证据:`agent/context_compressor.py:3096-3099`)

### 2.4 记忆与学习闭环(memory + self-improvement loop)

这是 README 第 19/26 行 self-improving 宣称背后的子系统,由五条环互扣:(1) 有界双文件记忆 MEMORY.md/USER.md 以冻结快照进系统提示,memory 工具自治增删改并受审批门禁与漂移守护保护;(2) nudge 闭环——按用户回合数(默认 10)与工具迭代数计数,响应送达后 fork 一个工具白名单受限、持久化被切断、前缀缓存字节对齐的后台 review agent,按精调 prompt 决定写记忆或创建/修补 class-level 技能,技能归属由 is_background_review() provenance 区分 agent 自创与用户所有;(3) curator 以空闲+7 天间隔在后台做技能生命周期管理(active→stale→archived 只归档不删,LLM 伞状合并默认关闭,动手前 tar.gz 快照可回滚),数据底座是 .usage.json 遥测 sidecar;(4) 跨会话召回由纯 SQLite 的 FTS5 三索引(词/trigram/CJK)session_search 提供 discovery/scroll/read/browse 四模式,零 LLM;(5) 外部记忆经 MemoryProvider 插件框架接入(8 个 bundled provider,单选),MemoryManager 负责超时隔离、防注入围栏、写镜像与辅助模型 query 改写,Honcho 集成实现多 pass dialectic 用户建模。学习产物通过 /journey 图谱、learning_mutations 编辑删除与 insights 报表对用户可视可控。总体印象:代码比 README 更严谨——README 的 'LLM summarization' 检索宣称已过期,'nudge' 实为对话外后台 fork,而防注入/防数据丢失/成本控制的大量工程在文档中只字未提。

关键文件(33 个,行数实测,余见 JSON):`agent/memory_manager.py`(1241), `agent/memory_provider.py`(357), `tools/memory_tool.py`(1240), `agent/background_review.py`(1081), `agent/turn_context.py`(1275), `agent/turn_finalizer.py`(756), `agent/learn_prompt.py`(150), `agent/learning_graph.py`(328)


#### 40. 有界双文件持久记忆(MEMORY.md/USER.md)+ 冻结快照注入

- **解决**:跨会话持久记忆若无限增长会吃掉上下文预算,且中途改动会破坏 LLM 前缀缓存;需要一种有界、可自我整理、缓存友好的记忆载体。
- **实现**:tools/memory_tool.py 的 MemoryStore 维护两个 § 分隔的文件:MEMORY.md(默认 2200 字符,agent 自我笔记)与 USER.md(1375 字符,用户画像),入口是单一 memory 工具(add/replace/remove + 原子 batch,replace/remove 用唯一子串定位)。系统提示注入走『冻结快照』:format_for_system_prompt 只返回 load_from_disk() 时刻的快照,带用量百分比头部;会话中写盘立即持久但不改系统提示,保住前缀缓存。超限不静默丢弃而是报错并回显全部条目,逼模型在同回合内自行整合腾位(_consolidation_failures 计数防打转)。
- **证据**:`tools/memory_tool.py:686-688` · `tools/memory_tool.py:62-67` · `tools/memory_tool.py:892-893`
  ```
          This returns the state captured at load_from_disk() time, NOT the live
          state. Mid-session writes do not affect this. This keeps the system
          prompt stable across all turns, preserving the prefix cache.
  ```
- **规模**:tools/memory_tool.py 1240 行;中等复杂度(文件锁、原子写、批量语义、快照/实时双视图)
- **学习价值**:高 — 『字符上限 + 满了报错逼 agent 自己整合 + 冻结快照护缓存』是一套完整可移植的有界记忆设计,直接回答了 agent 记忆无限膨胀与缓存失效两大痛点。

#### 41. 记忆/技能 nudge 计数器 → 后台自我改进 review fork  **[▲文档不符]**

- **解决**:README 宣称 agent 会『nudge 自己持久化知识』:需要一种既不打断用户任务、又不污染主会话上下文/前缀缓存的周期性自我反思机制。
- **实现**:turn_context.py 每个用户回合递增 _turns_since_memory(默认 nudge_interval=10,重启后从历史 user 消息数取模恢复计数,#22357),conversation_loop.py 按工具迭代数递增 _iters_since_skill;调用 memory/skill_manage 工具会在 tool_executor.py 归零计数。触发后不在对话里注入任何文字(turn_context.py:588 明确 'no nudge injection'),而是 turn_finalizer 在响应送达后 spawn 一个 fork 的 AIAgent(background_review.py):线程级工具白名单只留 memory+skills、_persist_disabled 阻断对真实会话 DB 的写入(防『curator 夺舍』)、继承父会话 cached system prompt 与 byte-identical tools 以命中前缀缓存(实测省 ~26% 成本)、危险命令 auto-deny。/refine [focus] 可手动带焦点触发同一 fork。codex_app_server 路径在 codex_runtime.py 里复刻同一套触发。
- **证据**:`agent/turn_context.py:593-599` · `agent/turn_finalizer.py:716-722` · `agent/background_review.py:903-909` · `agent/background_review.py:828` · `agent/tool_executor.py:597-600`
  ```
      if (agent._memory_nudge_interval > 0
              and "memory" in agent.valid_tool_names
              and agent._memory_store):
          agent._turns_since_memory += 1
          if agent._turns_since_memory >= agent._memory_nudge_interval:
  ```
- **规模**:background_review.py 1081 行 + turn_context/turn_finalizer/codex_runtime 中的触发点;高复杂度(fork 隔离、缓存字节级对齐、持久化隔离)
- **学习价值**:高 — 这是『self-improving』宣称的真正落地点:计数触发 + 响应后 fork + 工具白名单 + 持久化隔离 + 前缀缓存复用,是后台自反思 agent 的教科书级工程方案,坑(fork 写脏父会话、缓存 miss、stdout 泄漏)都有注释记录。
- **▲ 文档不符**:README.md:19 说 'nudges itself to persist knowledge',字面暗示会话内提醒;实际代码明确不注入对话(turn_context.py:588 'Preserve the original user message (no nudge injection).'),nudge 实为会话外的后台 review fork。官方 memory.md 文档口径(background self-improvement review)与代码一致,README 措辞偏营销。

#### 42. 技能自创建/自改进提示词体系 + provenance 归属  **[▲文档不符]**

- **解决**:『从经验创建技能、使用中自改进』需要明确:何时该写技能、写成什么形态、哪些技能不许动、以及自动创建与用户手写技能的所有权边界。
- **实现**:background_review.py 内置三份长 prompt(_MEMORY_REVIEW_PROMPT/_SKILL_REVIEW_PROMPT/_COMBINED_REVIEW_PROMPT):要求 review fork 'Be ACTIVE',目标形态是 CLASS-LEVEL 伞状技能 + references/templates/scripts 子文件;修改优先级为『先补当前加载过的技能 → 再补现有伞 → 加支撑文件 → 最后才新建』;明确保护清单(bundled/hub/pinned/user-owned 不许写)与反模式清单(环境性失败、『工具坏了』类负断言、未验证的失败路径不得固化)。归属上 skill_manager_tool.py 只有当 is_background_review() 为真时才打 agent_created 标记——前台用户指挥创建的技能属于用户,curator 永不碰。
- **证据**:`agent/background_review.py:182-186` · `tools/skill_manager_tool.py:1599-1605`
  ```
  _SKILL_REVIEW_PROMPT = (
      "Review the conversation above and update the skill library. Be "
      "ACTIVE — most sessions produce at least one skill update, even if "
      "small. A pass that does nothing is a missed learning opportunity, "
      "not a neutral outcome.\n\n"
  ```
- **规模**:三份 review prompt 约 240 行精调文本 + tools/skill_provenance.py 78 行;文本工程密度极高
- **学习价值**:高 — 这些 prompt 是多年实战教训的浓缩:反『一次会话一个技能』、反『把失败固化成规则』、用户抱怨算一级技能信号、后台自治写与前台用户所有权分离——做技能自学习闭环时几乎每条都会踩到。
- **▲ 文档不符**:README.md:26 'Autonomous skill creation after complex tasks' 中的『复杂任务后』实际是工具迭代计数阈值(_iters_since_skill >= 10)近似,并非任务复杂度判断。

#### 43. Curator:空闲触发的技能生命周期管理(prune + 可选 consolidation + 快照回滚)

- **解决**:自创建技能会无限堆积成上百个窄技能,污染系统提示技能索引、浪费 token;需要后台维护但又不能误删用户资产。
- **实现**:agent/curator.py:无 cron 守护,由 CLI 会话启动/gateway tick 调 maybe_run_curator(),门控 enabled、paused、interval(默认 7 天)、min_idle 2h;首次观察只 seed 时间戳延迟一个周期。确定性 prune(apply_automatic_transitions)按 last_activity 把 active→stale(30d)→archived(90d,可恢复,从不删除),pinned 与被 cron job 引用的技能视同 pin 跳过,use_count=0 的新技能有宽限地板。LLM consolidation(伞状合并)默认 OFF(DEFAULT_CONSOLIDATE=False),开启时 fork AIAgent(toolsets=[skills,terminal], max_iterations=9999)跑伞构建 prompt,支持 dry-run 报告。每次真跑前 curator_backup.snapshot_skills 打 tar.gz 快照(含 .usage.json/.archive/.curator_state/cron-jobs.json),rollback 连 cron 的技能引用一并还原且回滚本身可撤销。
- **证据**:`agent/curator.py:70-73` · `agent/curator.py:371-377` · `agent/curator.py:340-341` · `agent/curator.py:78` · `agent/curator_backup.py:1-4` · `agent/curator.py:2009-2016`
  ```
  DEFAULT_INTERVAL_HOURS = 24 * 7  # 7 days
  DEFAULT_MIN_IDLE_HOURS = 2
  DEFAULT_STALE_AFTER_DAYS = 30
  DEFAULT_ARCHIVE_AFTER_DAYS = 90
  ```
- **规模**:curator.py 2019 行 + curator_backup.py 757 行;高复杂度(调度门控、状态机、报告 diff/reconcile、快照回滚含 cron 引用修复)
- **学习价值**:高 — 展示了『自动化维护必须默认保守』的完整落地:只归档不删除、贵的 LLM 步骤默认关、动手前先快照、cron 依赖视同 pin、dry-run 先行——是给任何 agent 资产做后台 GC 的参考实现。

#### 44. 技能使用遥测 sidecar(.usage.json)——学习闭环的数据底座  **[◇未见于文档]**

- **解决**:curator 的 stale/archive 判定、学习图谱、insights 报表都需要每个技能的使用/修改/创建事实,且不能把运营元数据写进用户拥有的 SKILL.md。
- **实现**:tools/skill_usage.py 用 ~/.hermes/skills/.usage.json sidecar(文件锁 + 原子写)按技能名记 use_count/view_count/patch_count、created_by、state(active/stale/archived)、pinned 等;bump 全部 best-effort 不阻断底层工具。/skill 斜杠调用与 bundle 展开走 bump_use(skill_commands.py),skill_view 工具读技能被显式计为『使用』(喂 curator 的 stale 计时器);skill_manage 的 edit/patch/write_file 走 bump_patch。curated_report()/is_curator_managed() 是 curator 与 journey 图谱的读取口径。
- **证据**:`tools/skill_usage.py:3-6` · `tools/skills_tool.py:1941-1946`
  ```
  Tracks per-skill usage metadata in a sidecar JSON file (~/.hermes/skills/.usage.json)
  keyed by skill name. Counters are bumped by the existing skill tools (skill_view,
  ```
- **规模**:tools/skill_usage.py 1340 行;中等复杂度(锁、原子写、provenance 判定、bundled/hub 清单交叉)
- **学习价值**:中 — 『遥测放 sidecar 不进内容文件、bump 永不 raise、view 计为 use』是把学习信号采集做得对用户无感的可复用套路。

#### 45. MemoryProvider 插件框架 + MemoryManager 编排(8 个 bundled provider)  **[▲文档不符]**

- **解决**:外部记忆后端(云服务/本地库)质量参差,必须保证:慢/卡死的 provider 不能阻塞用户回合,坏 schema 不能毒化整个工具集,多后端不能互相打架。
- **实现**:agent/memory_provider.py 定义 ABC(prefetch/sync_turn/on_turn_start/on_pre_compress/on_session_switch/on_memory_write/get_tool_schemas 等生命周期钩子);plugins/memory/__init__.py 扫描 bundled 8 个 provider(byterover、hindsight、holographic、honcho、mem0、openviking、retaindb、supermemory)+ $HERMES_HOME/plugins 用户目录,memory.provider 配置单选。MemoryManager 强制只允许一个外部 provider;外部 prefetch 跑在守护线程上 8s 超时,卡死线程被记账、下回合直接跳过直到其返回;工具 schema 归一化(双重包裹修复,#47707)且禁止遮蔽核心工具名(#40466);末回合 sync_all/queue_prefetch_all 进单 worker 后台执行器,shutdown 按写/预取分级 drain 并上报被放弃的写。内置 memory 工具的成功写通过 notify_memory_tool_write 镜像给外部 provider(staged/失败写严格不外传)。
- **证据**:`agent/memory_manager.py:580-584` · `agent/memory_manager.py:418-424` · `agent/agent_init.py:1707-1710` · `agent/memory_manager.py:1064-1071`
  ```
          thread.join(self._external_prefetch_timeout)
          if thread.is_alive():
              logger.warning(
                  "Memory provider '%s' prefetch timed out after %.1fs; skipping it until "
                  "the stuck call returns",
  ```
- **规模**:memory_manager.py 1241 + memory_provider.py 357 + plugins/memory 共 22124 行(8 个 provider);框架层高复杂度
- **学习价值**:高 — 外部依赖隔离的范本:超时+卡死记账、单外部实例、schema 归一化、核心工具名保护、镜像写 fail-closed、关机分级 drain,每一条都对应一个真实事故编号。
- **▲ 文档不符**:MemoryManager 的 docstring(agent/memory_manager.py:365-368)宣称『The builtin provider is always first』,但代码库中不存在任何 name=='builtin' 的 MemoryProvider 实现;agent_init.py 只注册外部插件,内置 MEMORY.md 存储(agent._memory_store)根本不在 manager 体系内,所有 `provider.name == "builtin"` 分支实为死路径。

#### 46. 记忆上下文防注入围栏:fenced block + 流式 Scrubber + 写入威胁扫描  **[◇未见于文档]**

- **解决**:召回的记忆既进模型上下文又源自可被污染的存储:要防 provider 伪造围栏提权、防模型把注入的记忆块回显给用户、防恶意内容借记忆写入常驻系统提示。
- **实现**:三层防御:(1) build_memory_context_block 把 prefetch 结果包进 <memory-context> 围栏加『NOT new user input』系统注记,注入只发生在用户消息的 API 副本(api_content sidecar,存储内容保持干净且字节可重放护缓存);sanitize_context 先剥掉 provider 自带的伪围栏。(2) StreamingContextScrubber 是跨 chunk 的流式状态机,清洗模型回显的 memory-context 片段(单次 regex 无法跨 delta 匹配),流结束仍在 span 内则整段丢弃。(3) 写入侧 _scan_memory_content 用共享 threat_patterns 的 strict 档扫描注入/外传模式——因为记忆是冻结快照,毒条目会跨会话常驻。query_rewrite 输出还要过 _INSTRUCTION_LEAK_RE 防指令走私。
- **证据**:`agent/memory_manager.py:354-361` · `agent/memory_manager.py:182-183` · `tools/memory_tool.py:86-88` · `agent/turn_context.py:77-80`
  ```
      return (
          "<memory-context>\n"
          "[System note: The following is recalled memory context, "
          "NOT new user input. Treat as authoritative reference data — "
          "this is the agent's persistent memory and should inform all responses.]\n\n"
  ```
- **规模**:围栏+scrubber 约 250 行 + threat_patterns 共享库;流式状态机实现精巧
- **学习价值**:高 — 把『记忆即攻击面』想全了:注入方向(伪围栏)、回显方向(流式清洗)、持久化方向(strict 扫描),且注入走 API 副本不碰存储内容以同时保住缓存与整洁转录,值得整套搬走。

#### 47. 跨会话召回:FTS5 三索引 session_search(discovery/scroll/read/browse)  **[▲文档不符]**

- **解决**:『搜索自己的过去对话』需要在一个 SQLite 里同时支持词级英文、子串、CJK 检索,并把结果以低 token 成本、可继续钻取的形态交给模型。
- **实现**:hermes_state_search.py(SessionSearchMixin,2230 行)维护三套索引:messages_fts(BM25 词检索)、messages_fts_trigram(子串,约 2.6x 存储,排除 tool 行)、messages_fts_cjk(CJK bigram),带查询消毒(引号短语保留、悬空布尔词剔除、连字符/点号词包引号)、增量 merge、分步重建与存储优化。tools/session_search_tool.py 是模型面工具:单一 shape 四模式(query→discovery 按 lineage 去重 + ±5 消息窗 + 首尾 bookends;session_id+anchor→scroll;仅 session_id→整段 read,跨 profile 可寻址 @session:<profile>/<id>;无参→browse),cron 会话只降权不排除(#19434 recall blindness),kanban/subagent/tool 会话隐藏,压缩产物摘要从 bookends 剔除(#43175)。
- **证据**:`hermes_state_search.py:1` · `tools/session_search_tool.py:21-23` · `tools/session_search_tool.py:42-50` · `hermes_state_search.py:1243-1245`
  ```
  """Full-text / trigram / CJK message search and FTS maintenance for SessionDB.
  ```
- **规模**:hermes_state_search.py 2230 + session_search_tool.py 1161 行;高复杂度(三索引、查询路由、重建状态机)
- **学习价值**:高 — 纯 SQLite 零 LLM 的跨会话记忆检索完整实现:三索引路由、FTS5 查询消毒、lineage 去重、自动化会话降权、bookends 低成本预览,是 agent 长期记忆检索层的高质量参照。
- **▲ 文档不符**:README.md:26 与 website/docs/index.mdx:123 宣称 'FTS5 session search with LLM summarization for cross-session recall',但代码明确 'No LLM calls anywhere'(session_search_tool.py:23,模块史注明 summary LLM 路径已在合并重构时移除);website/docs/user-guide/sessions.md:551 也写明 'No LLM calls, no summarization' —— README/index 的 LLM summarization 属过期宣称。

#### 48. 辅助模型记忆检索查询改写(query_rewrite)  **[◇未见于文档]**

- **解决**:用户原话往往不是好的记忆检索 query(冗长、含指令、指代悬空),直接喂给外部记忆后端召回质量差且有 prompt 注入风险。
- **实现**:plugins/memory/query_rewrite.py 用 auxiliary.memory_query_rewrite 槽位的辅助 LLM 把最新用户消息改写为一条 <=240 字符的英文检索问句;输入按 head/tail 截断到 4000 字符并以 JSON 字符串包裹标明 data-only;输出过五道验证(必须问句开头、必须含 user/history/preference 等记忆锚词、命中 _INSTRUCTION_LEAK_RE 即弃、不得多句、超长弃)——任何失败返回 "" 回退旧行为。Honcho provider 在 _run_dialectic_depth 第 0 pass 优先使用改写结果。
- **证据**:`plugins/memory/query_rewrite.py:41` · `plugins/memory/query_rewrite.py:96-101` · `plugins/memory/honcho/__init__.py:1153-1155`
  ```
  _SYSTEM_PROMPT = """You rewrite a user's latest message into one concise English question for memory retrieval.
  ```
- **规模**:139 行;小而精
- **学习价值**:中 — 『辅助小模型改写检索 query + 正则验证栅栏 + 失败静默回退』是提升 RAG/记忆召回质量的低成本模式,验证栅栏(防指令走私、强制记忆锚定)设计尤其可借鉴。

#### 49. Honcho dialectic 用户建模集成(多 pass 推理 + 自适应深度)

- **解决**:README 宣称『builds a deepening model of who you are across sessions』:需要把对话持续喂给用户建模服务,并在每回合以可控成本取回『此刻最相关的用户认知』。
- **实现**:plugins/memory/honcho/(共约 6500 行)实现 MemoryProvider 全钩子:会话初始化走后台线程 + dialectic 预热;prefetch 按 dialecticCadence 节流,_run_dialectic_depth 执行最多 3 个 pass(pass0 冷启动问『Who is this person?』/暖会话问会话相关上下文,pass1 自审补缺口,pass2 矛盾调和),_signal_sufficient 对上一 pass 结果做结构启发式判断、信号足够即提前止损;_apply_reasoning_heuristic 按 query 长度(>=120/400 字符)升 reasoning level 并封顶;sync_turn 后台把 (user, assistant) 回合写回 peer/session,on_memory_write 把内置 memory 工具的写镜像成 Honcho observation;gateway 身份(user_id/chat_id/thread)映射到 peer/session key 实现按人按聊天室隔离。5 个模型面工具(honcho_profile/search/context/reasoning/conclude)。
- **证据**:`plugins/memory/honcho/__init__.py:1088-1093` · `plugins/memory/honcho/__init__.py:1186-1190` · `plugins/memory/honcho/__init__.py:1167-1171`
  ```
              if is_cold:
                  return (
                      "Who is this person? What are their preferences, goals, "
                      "and working style? Focus on facts that would help an AI "
                      "assistant be immediately useful."
  ```
- **规模**:honcho 插件 __init__ 1550 + session 1447 + client 1113 + cli 1967 + oauth 约 1050 行;整体最重的 provider 之一
- **学习价值**:高 — 多 pass 自辩证检索(冷/暖 prompt 分流、信号足够即止、按 query 长度调推理档)是把『用户建模服务』集成进 harness 的成熟样板,成本控制手段全部代码化。

#### 50. 记忆写入审批门禁 + 外部漂移/坏读守护  **[▲文档不符]**

- **解决**:记忆会自动进系统提示,自治写入需要用户可控;同时 memory 文件可能被 patch 工具/并发会话/手改污染,盲目重写会静默丢数据甚至清空全部记忆。
- **实现**:写路径三重防护:(1) _apply_write_gate/_apply_batch_write_gate 接 tools/write_approval 框架,决策 allow/block/stage——非交互场景(gateway/后台 review)写入被 stage 成 pending 记录,用户以 /memory pending 审批,apply_memory_pending 在无 live agent 的上下文(gateway/GUI)也按同样字符上限执行。(2) _detect_external_drift 在每次变更前对盘上原文做 round-trip 校验,发现工具外内容则拍 .bak.<ts> 快照并拒写,错误信息附带 remediation 步骤(#26045)。(3) 文件存在但读失败时返回 _READ_FAILED 哨兵拒绝写入,避免『读成空 → 保存 → 清空记忆』。
- **证据**:`tools/memory_tool.py:941-947` · `tools/memory_tool.py:102-107` · `tools/memory_tool.py:131-134`
  ```
      decision = wa.evaluate_gate(wa.MEMORY, inline_summary=summary, inline_detail=detail)
  
      if decision.allow:
          return None
  
  ```
- **规模**:memory_tool.py 内约 300 行防护逻辑 + tools/write_approval 共享框架
- **学习价值**:高 — 『自治写入必须可审批、共享文件必须 round-trip 校验、读失败不等于空』三条防数据丢失原则的完整实现,对任何让 agent 写用户持久状态的系统都是必修课。
- **▲ 文档不符**:审批门禁在 memory.md 有文档,但 drift 检测(.bak 快照 + 拒写 + remediation)与坏读哨兵在 README/website 均未提及(仅存在于代码,hidden 部分)。

#### 51. /learn 显式技能蒸馏 + 学习可视化 journey 图谱

- **解决**:自动闭环之外还需要:用户显式指着任意材料说『学会它』;以及把学到的东西(技能+记忆)可视、可编辑、可删除,否则学习是黑箱。
- **实现**:agent/learn_prompt.py 的 build_learn_prompt 把 /learn 请求(目录/URL/『刚才做的事』/粘贴笔记 + 约束)组装成单条指令,内嵌 HARDLINE 技能写作标准(description<=60 字符否则索引截断不路由、author 恒为 Hermes 防环境身份泄漏、Hermes 工具措辞规范),CLI/gateway/TUI 三端共用。agent/learning_graph.py 构建『学习图谱』:只取非 base 且 (agent 创建或被用过) 的技能为节点,MEMORY.md/USER.md 的 § 块为一等记忆节点,related_skills 声明边 + 词面重叠打分的 memory→skill 边(每卡最多 4 条);learning_mutations.py 把节点 id 映射回盘上做编辑/删除(删技能=归档可恢复,删记忆重写文件),供 /journey TUI、桌面星图与 CLI 共用;learning_graph_render.py 是终端时间线渲染。insights.py 则从 state.db 汇总技能/工具/成本用量做 hermes insights 报表。
- **证据**:`agent/learn_prompt.py:119-120` · `agent/learning_graph.py:263-267` · `agent/learning_mutations.py:137-141`
  ```
          "[/learn] The user wants you to learn a reusable skill from the "
          "request below, and save it.\n\n"
  ```
- **规模**:learn_prompt 150 + learning_graph 328 + learning_mutations 206 + learning_graph_render 658 + insights 1162 行
- **学习价值**:中 — 『学习必须可视且可撤销』:学习产物统一成图谱节点、删除永远走可恢复归档、显式 /learn 与自动闭环共用同一套技能标准,是让 self-improving 获得用户信任的产品化层。

**本子系统文档-代码冲突(4 条):**

- 宣称:README.md:26 与 website/docs/index.mdx:123 宣称闭环学习包含 'FTS5 session search with LLM summarization for cross-session recall'
  实际:session_search 工具明确零 LLM:模块 docstring 写 'No LLM calls anywhere — every shape returns actual messages from the DB',并注明重构时移除了 summary LLM 路径('no summary LLM path');website 自己的 sessions.md:551 与 memory.md:190 也写明无 LLM 摘要——README/index.mdx 是过期宣称,且与站内其余文档互相矛盾(证据:`tools/session_search_tool.py:23`)
- 宣称:agent/memory_manager.py:365-368 docstring 宣称 'Orchestrates the built-in provider plus at most one external provider. The builtin provider is always first.'
  实际:代码库中不存在任何 name=='builtin' 的 MemoryProvider 实现;agent_init.py 只在配置了外部 provider 时才创建 MemoryManager 并仅注册该外部插件,内置 MEMORY.md/USER.md 存储(agent._memory_store)完全独立于 manager,所有 provider.name=='builtin' 分支(prefetch 直通、on_memory_write 跳过)均为不可达路径(证据:`agent/agent_init.py:1707-1710`)
- 宣称:README.md:19 'nudges itself to persist knowledge' 与 README.md:26 'Agent-curated memory with periodic nudges' 暗示会话内周期性提醒
  实际:nudge 从不注入对话:turn_context.py:588 注释 'Preserve the original user message (no nudge injection).';计数器到阈值只是置 should_review_memory 标志,由 turn_finalizer 在响应送达后 spawn 后台 review fork(对用户不可见,仅完成后打一行 'Self-improvement review' 摘要)。website memory.md 口径正确,README 措辞与机制不符(证据:`agent/turn_context.py:588`)
- 宣称:README.md:26 'Autonomous skill creation after complex tasks'(暗示按任务复杂度触发)
  实际:技能 review 触发条件是纯工具迭代计数:conversation_loop.py 每次工具迭代递增 _iters_since_skill,达到 creation_nudge_interval(默认 10)即触发,与任务是否『复杂』无语义判断;skill_manage 被调用即清零(证据:`agent/turn_finalizer.py:700-704`)

### 2.5 工具基础设施与安全(tool infrastructure & security)

该子系统是 hermes-agent 的『窄腰』:所有工具经 tools/registry.py 的单例注册表自注册(AST 自动发现+磁盘缓存),model_tools.py 在其上提供 get_tool_definitions(带 memo、动态 schema 重建、多后端清洗、tool-search 装配)与 handle_function_call(参数纠偏、middleware/hook、审批拦截、桥接解包)两大入口;toolsets.py 用可组合 toolset 定义各平台工具面,核心集 _HERMES_CORE_TOOLS 被平台 bundle 复用且禁用 bundle 时受保护。安全侧呈多层纵深:approval.py 的 hardline 硬底线→用户 deny→smart LLM guardian→CLI/gateway 人审栈,tirith 外部扫描器与 threat_patterns/skills_guard 内容级扫描,url_safety 的 SSRF 预检+connect-time DNS 钉扎,write_approval 对持久写入的门禁,agent/tool_guardrails 的循环护栏。上下文经济由三层输出防御(per-tool 截断→沙箱持久化→per-turn 预算)与 Tool Search 渐进披露共同保障;execute_code 用 UDS/TCP/文件三态 RPC 实现 README 宣称的编程式工具调用,凭证靠 env 洗净+token 鉴权隔离;mcp_tool.py 则把外部 MCP 服务器当不受信输入全面设防(OSV 预检、描述注入扫描、命名撞车 fail-closed、watchdog 孤儿清理)。整体设计特点是:每条安全规则都先于 yolo 旁路排序、fail-open/closed 语义显式可配、且几乎每个 workaround 都注释了触发它的真实故障编号。

关键文件(28 个,行数实测,余见 JSON):`tools/registry.py`(956), `model_tools.py`(1569), `toolsets.py`(1004), `toolset_distributions.py`(358), `tools/schema_sanitizer.py`(591), `tools/tool_output_limits.py`(110), `tools/tool_result_storage.py`(254), `tools/budget_config.py`(114)


#### 52. 自注册工具注册表:AST 自动发现 + check_fn 可用性 TTL 缓存与瞬断宽限  **[▲文档不符]**

- **解决**:harness 需要一个不用手工维护清单的工具注册/发现机制,同时工具可用性探测(Docker daemon、playwright、API key)昂贵且会抖动——一次探测超时就会让整个 toolset 从子代理 schema 里消失。
- **实现**:每个 tools/*.py 在模块导入时调用 registry.register() 自注册 ToolEntry(schema/handler/check_fn/toolset/emoji/max_result_size/dynamic_schema_overrides);discover_builtin_tools() 用 AST 扫描 tools/ 目录找顶层 registry.register() 调用并按 (mtime_ns,size) 缓存判定结果到磁盘。check_fn 结果按 (fn, multiplex-profile-scope) 缓存 30s TTL,且在上次成功 60s 内的失败被当作 flake 直接返回 last-good True 且不缓存失败,防止工具集中途闪断;registry._generation 计数器驱动 get_tool_definitions 的 memo 失效,LRU 上限 8 条(#19251)。dispatch() 统一桥接 async handler(_run_async 持久事件循环)并把非法返回类型规范化为 tool_error。
- **证据**:`tools/registry.py:84-86` · `tools/registry.py:316-320` · `model_tools.py:348-358`
  ```
      for path in sorted(tools_path.glob("*.py")):
          if path.name in {"__init__.py", "registry.py", "mcp_tool.py"}:
              continue
  ```
- **规模**:registry.py 956 行 + model_tools.py 1569 行,中高复杂度(多线程锁、双层缓存、profile 维度隔离)
- **学习价值**:高 — 自注册+AST 发现+磁盘缓存是零维护成本的插件化工具体系范式;check_fn 的 last-good 宽限窗口解决了『可用性探测抖动导致工具静默消失』这一真实生产问题,值得任何 harness 借鉴。
- **▲ 文档不符**:website/docs/developer-guide/tools-runtime.md 只说 check_fn『cached per-call』并展示无缓存的简化代码,未提及代码中实际存在的 30s TTL 缓存(_CHECK_FN_TTL_SECONDS, registry.py:216)与 60s 瞬断宽限(_CHECK_FN_FAILURE_GRACE_SECONDS, registry.py:220)机制。

#### 53. 插件覆盖/注销权限门(基于 handler.__globals__ 归属与调用帧检查)  **[▲文档不符]**

- **解决**:第三方插件在同一进程内可调用 registry.register/deregister,若无授权检查,插件能静默替换内置工具 handler(供应链攻击面)或先 deregister 再 register 绕过覆盖检查。
- **实现**:register(override=True) 时通过 handler.__globals__['__name__'] 确定 handler 定义所在的插件命名空间(定义期绑定,lambda/回调无法洗白),对照 register_plugin_override_policy 记录的 operator 显式 opt-in(plugins.entries.<id>.allow_tool_override),未授权则 raise PermissionError;deregister() 因无 handler 参数,用 sys._getframe(2) 取调用方模块名,插件删除非本插件工具且无 opt-in 时同样拒绝(封堵 deregister-then-register 绕过),mcp-* toolset 豁免以支持动态刷新的 nuke-and-repave。
- **证据**:`tools/registry.py:548-549` · `tools/registry.py:516-517` · `tools/registry.py:651-655`
  ```
                      _owner = self._plugin_owner_of(handler)
                      if _owner is not None and not self._plugin_override_policy.get(_owner, False):
  ```
- **规模**:约 180 行(registry.py 472-670),精巧但安全语义密集
- **学习价值**:高 — 同进程插件模型下的最小可行权限边界设计:授权绑定到代码定义位置而非调用时刻,deregister 侧用帧检查补齐绕过路径,是『无沙箱插件系统如何防内置工具被劫持』的完整案例。
- **▲ 文档不符**:tools-runtime.md 只记载了 register 覆盖需 allow_tool_override;deregister 侧的同等权限门(防先删后注册绕过)在 README/AGENTS.md/website 均未提及。

#### 54. 工具 Schema 多后端兼容清洗层(含 property-key 重命名往返)  **[◇未见于文档]**

- **解决**:MCP/插件产出的 JSON Schema 在 llama.cpp(GBNF grammar)、Anthropic、OpenAI Codex 端点、xAI、Gemini 等严格后端上会 400 整个请求(裸字符串 schema、type 数组、nullable anyOf、$ref 旁的 default、非法 property key 如 Cloudflare 的 issue_class~neq)。
- **实现**:sanitize_tool_schemas 在 get_tool_definitions 返回前深拷贝并递归修复:裸字符串→{type:...}、object 无 properties 注入空 dict、type:[X,"null"]→单 type+nullable:true、多类型数组→anyOf 保留全部分支、顶层 combinator 剥离(Codex)、$ref 兄弟 default 剥离(Fireworks)、非法 property key 确定性重命名并在 dispatch 时经 unrename_tool_args 还原为原始 wire 名。另有两个 reactive 清洗仅在后端 400 后触发:strip_pattern_and_format(llama.cpp regex 子集)与 strip_slash_enum(xAI 拒绝含 '/' 的 enum)。
- **证据**:`tools/schema_sanitizer.py:370-377` · `tools/schema_sanitizer.py:52-53` · `model_tools.py:764-765`
  ```
          if key == "type" and isinstance(value, list):
              has_null = "null" in value
              non_null = [t for t in value if isinstance(t, str) and t != "null"]
              if len(non_null) == 1:
                  out["type"] = non_null[0]
  ```
- **规模**:schema_sanitizer.py 591 行,中等复杂度但边界 case 极多(每条规则都对应一个真实后端故障)
- **学习价值**:高 — 这是『一套工具 schema 跑遍所有推理后端』的活标本:每条清洗规则注释了触发它的具体后端错误;重命名+dispatch 时逆映射的往返设计保证模型看到的 schema 与 wire 调用一致,是多提供商 harness 的必修课。

#### 55. LLM 工具参数纠偏(coerce_tool_args + 递归 JSON 字符串修复)  **[◇未见于文档]**

- **解决**:开源权重模型(DeepSeek/Qwen/GLM)频繁把数字/布尔发成字符串、把数组字段发成 JSON 编码字符串、把裸标量当数组元素,直接 dispatch 会产生令模型困惑的工具失败。
- **实现**:handle_function_call 入口先按注册 schema 对每个参数做安全强转:"42"→42、"true"→True、JSON 字符串→list/dict、schema 为 array 时裸标量包装成单元素列表、nullable 字段的 "null"→None;_normalize_json_strings_for_schema 再按 items/properties schema 递归下钻,修复数组元素或嵌套对象字段本身是 JSON 字符串的情况(schema 引导解析,type:string 的合法 JSON 样字符串不被误伤)。失败时保留原值,绝不阻断 dispatch。
- **证据**:`model_tools.py:782-783` · `model_tools.py:888-892`
  ```
          if expected == "array" and value is not None and not isinstance(value, (list, tuple)):
              if isinstance(value, str):
  ```
- **规模**:约 320 行(model_tools.py 730-1045),低-中复杂度
- **学习价值**:中 — 对开源模型友好度影响巨大且实现干净:schema 引导的递归纠偏是提升 tool-calling 成功率的低成本高收益手段;identity 保持(无变化返回原对象)便于检测 no-op。

#### 56. 三层工具输出限长与结果持久化(per-tool cap → 沙箱落盘 → per-turn 预算)  **[◇未见于文档]**

- **解决**:工具输出可能撑爆上下文窗口:单个超大结果、或多个中等结果在同一 turn 内累加超预算;简单截断会永久丢失信息。
- **实现**:第一层各工具自截断,上限由 tool_output_limits 从 config.yaml 的 tool_output 段读取(max_bytes/max_lines/max_line_length,默认 50K/2000/2000);第二层 maybe_persist_tool_result 在结果超过 registry.get_max_result_size(默认 100K,read_file 钉死为 inf 防 persist→read→persist 死循环)时经 env.execute() 把全文写进沙箱 /tmp/hermes-results/(stdin 管道绕过 Linux 128KB MAX_ARG_STRLEN),上下文中只留 <persisted-output> 预览+路径;第三层 enforce_turn_budget 在单 turn 聚合超 200K 时按大小从大到小继续落盘直到达标。
- **证据**:`tools/tool_result_storage.py:171-175` · `tools/tool_result_storage.py:114-116` · `tools/budget_config.py:11-13`
  ```
      if effective_threshold == float("inf"):
          return content
  
      if len(content) <= effective_threshold:
          return content
  ```
- **规模**:tool_result_storage.py 254 行 + budget_config.py 114 行 + tool_output_limits.py 110 行,低复杂度高杠杆
- **学习价值**:高 — 『持久化而非截断』+三层防御是上下文管理的优雅方案:全文落在沙箱内任意后端可 read_file 回读,read_file 阈值钉死 inf 防自激振荡这个细节尤其值得学。

#### 57. 分层命令审批体系(hardline floor / user deny / smart LLM guardian / CLI+gateway 人审)  **[▲文档不符]**

- **解决**:agent 执行 shell 命令需要在『不打扰用户』与『不可逆破坏』之间分层:灾难命令必须无条件拦、危险命令需人审、误报要能被 LLM 自动放行、无人值守(cron/gateway)场景要有异步审批通道。
- **实现**:check_all_command_guards 按序执行:hardline 硬底线(rm -rf / 及系统目录/mkfs/dd 写裸设备/fork bomb/kill -1/关机,连 --yolo 与 approvals.mode=off 都不可绕)→ sudo -S 无 SUDO_PASSWORD 时的猜密码拦截 → 用户 approvals.deny glob(同样先于 yolo)→ yolo/off 旁路 → 永久 allowlist → tirith+DANGEROUS_PATTERNS 汇总为单一审批 → mode=smart 时辅助 LLM(防注入:剥壳注释、<command> 定界、系统提示告警)给 APPROVE/DENY/ESCALATE → CLI 同步 prompt 或 gateway 异步按钮(阻塞 agent 线程、心跳保活、拒绝语义『Silence is not consent』防重试改写)。附带连续拒绝熔断计数、human_wait_window 把等人时长从批处理 deadline 中扣除、检测归一化层反混淆(引号拆分、$( ) 字面替换、grep pattern 摘除防误报)。parser-limit 拦截会把超大 payload 自动存成脚本并告知 bash <file> 恢复路径。
- **证据**:`tools/approval.py:451-453` · `tools/approval.py:3761-3764` · `tools/approval.py:3955-3957` · `tools/approval.py:4080-4086`
  ```
      (_RM_FLAG_PREFIX + _hardline_rm_path(r'/(?:(?:\.\.?)?/)*(?:\.\.?)?\**|/ \*'), "recursive delete of root filesystem"),
      (_RM_FLAG_PREFIX + _hardline_rm_path(_HARDLINE_SYSTEM_DIRS), "recursive delete of system directory"),
      (_RM_FLAG_PREFIX + _hardline_rm_path(r'(?:~|\$\{?HOME\}?)(?:/?|/\*)?'), "recursive delete of home directory"),
  ```
- **规模**:approval.py 4557 行,全仓最重的安全模块;含数百行反混淆 shell 词法分析
- **学习价值**:高 — 这是完整的『危险操作审批栈』教科书:不可绕底线/用户 deny/LLM guardian/人审四层清晰分离,拒绝消息面向 LLM 心理学设计(点名 retry/rephrase/换路径三种规避),审批等待与 watchdog/批处理 deadline 的交互都有工业级处理。
- **▲ 文档不符**:website/docs/user-guide/security.md:101 声称 hardline 模式列表『kept in sync with tools/approval.py::UNRECOVERABLE_BLOCKLIST』,但代码中不存在该符号——实际符号是 HARDLINE_PATTERNS(approval.py:434)。

#### 58. Tirith 外部二进制预执行扫描集成(自动安装+签名校验+熔断)

- **解决**:纯正则模式匹配抓不住内容级威胁(同形异义 URL、curl|bash、终端注入);集成外部扫描器又引入供应链风险、二进制缺失/崩溃拖垮 agent 的新问题。
- **实现**:check_command_security 以子进程运行 tirith check --json,退出码为判决唯一来源(0=allow/1=block/2=warn),JSON 仅做 findings 富化且截断(50 条/500 字符);二进制缺失时从 GitHub releases 后台自动安装,强制 SHA-256 校验,有 cosign 时再验 GitHub Actions workflow 签名(identity regexp 钉到 release.yml@refs/tags/v);连续 3 次 spawn/超时故障打开进程级熔断(#41400 修复 20 分钟挂死),fail_open 可配为 fail-closed(import 失败时合成 warn finding 走人审,cron 场景直接 block,#20733)。tirith 的 block/warn 不再是硬拦而是并入统一审批 prompt,tirith 类 finding 永不进永久 allowlist(session 上限)。
- **证据**:`tools/tirith_security.py:776-778` · `tools/tirith_security.py:753-754` · `tools/tirith_security.py:44-45` · `tools/approval.py:4214-4216`
  ```
          result = subprocess.run(
              [tirith_path, "check", "--json", "--non-interactive",
  ```
- **规模**:tirith_security.py 872 行,含完整的下载/校验/安装/失败标记状态机
- **学习价值**:中 — 展示了『如何安全地依赖一个外部安全工具』:退出码与富化解耦、供应链验证、熔断防拖垮、fail-open/closed 显式可配且 import 失败也不静默放行——这些运维语义比扫描本身更有学习价值。

#### 59. SSRF 双层防护:URL 预检 + httpx connect 时 DNS 钉扎(防 rebinding)  **[▲文档不符]**

- **解决**:web/browser/vision 工具抓取 LLM 给出的 URL 会被用于打内网与云元数据端点窃取实例凭证;传统预检后 DNS rebinding 仍可在真正连接时解析到内网地址。
- **实现**:is_safe_url 解析主机并逐 IP 检查:云元数据 IP/主机名(169.254.169.254、ECS task metadata、Alibaba、IPv4-mapped IPv6 变体)与整个 link-local 段无条件封禁(security.allow_private_urls 开关也不放行),RFC1918/loopback/CGNAT(100.64.0.0/10 需显式处理因 is_private 不覆盖)默认封禁可 opt-out;第二层用自定义 httpcore network backend 替换 httpx 连接池,在 connect_tcp 时重新解析并只拨号已审 IP(_MAX_SSRF_CONNECT_IPS=8),关闭预检与连接之间的 rebinding 窗口,并拒绝 Unix socket 连接。DNS 失败默认 fail-closed,但配置了代理且非字面 IP 时委托代理解析(沙箱环境兼容)。
- **证据**:`tools/url_safety.py:487-490` · `tools/url_safety.py:543-545` · `tools/url_safety.py:210`
  ```
              # Always block cloud metadata IPs and link-local, even with toggle on
              if ip in _ALWAYS_BLOCKED_IPS or any(ip in net for net in _ALWAYS_BLOCKED_NETWORKS):
                  logger.warning(
                      "Blocked request to cloud metadata address: %s -> %s",
  ```
- **规模**:url_safety.py 874 行,含 sync/async 双 transport 注入与既有 client 就地加固
- **学习价值**:高 — connect-time DNS pinning 是多数 agent 框架缺失的一层——预检式 SSRF 防护在 rebinding 面前形同虚设;IPv4-mapped IPv6 与 CGNAT 这两个 Python ipaddress 盲区的显式处理也是高价值细节。
- **▲ 文档不符**:security.md:665 声称 allow_private_urls=true 后『no longer reject RFC 1918 / loopback / link-local / CGNAT / cloud-metadata destinations』,但代码里云元数据 IP/主机名与整个 169.254.0.0/16 link-local 段在开关开启时仍然无条件封禁(url_safety.py:487-493、436-439);security.md:654 称 DNS 失败一律 fail-closed,而代码在配置了代理且主机名非字面 IP 时 fail-open 放行由代理解析(url_safety.py:466-472)。

#### 60. 内容级威胁模式库与技能安装信任分级(threat_patterns + skills_guard)

- **解决**:提示注入/promptware/C2 载荷会经 web 页面、MCP 响应、memory 写入、skill 安装进入系统提示;不同来源可容忍的误报率不同,一刀切的模式库要么漏报要么把安全研究内容全拦掉。
- **实现**:threat_patterns 按攻击类别组织 (regex, id, scope) 三元组,scope 三档:all(经典注入+外泄,零误报)/context(加 C2/角色劫持,用于工具结果与上下文文件,只警不拦)/strict(加持久化/SSH 后门,用于用户可介入的 memory/skill 写入,可拦);扫描前 NFKC 归一化打掉全角同形绕过、原文检查 17 个不可见 Unicode 字符、有界 filler (?:\w+\s+){0,8} 防回溯爆炸、65536 字符扫描上限。skills_guard 独立维护约 400 行技能威胁模式,按来源信任分级(builtin/trusted/community/agent-created)× 判决(safe/caution/dangerous)查 INSTALL_POLICY 矩阵决定 allow/block/ask,community+dangerous 连 --force 都不可覆盖,扫描结果按内容摘要缓存。
- **证据**:`tools/threat_patterns.py:245` · `tools/threat_patterns.py:59` · `tools/skills_guard.py:55-60` · `tools/skills_guard.py:807-811`
  ```
      normalised = unicodedata.normalize("NFKC", content)
  ```
- **规模**:threat_patterns.py 284 行 + skills_guard.py 1161 行;模式条目均带误报权衡注释
- **学习价值**:高 — scope 分级(检得广 vs 拦得准)与信任×判决二维矩阵是内容安全策略工程的范本;每条模式旁写明『为什么这个词不能加』的注释(如 praxis 被移除)体现了对误报成本的严肃对待。

#### 61. Tool Search 渐进式工具披露(3 桥接工具 + BM25 + 分层 listing + 会话范围防越权)

- **解决**:大量 MCP/插件工具的 schema 会吃掉数万 token 上下文(如 Cloudflare ~3300 工具仅名字就 ~32K token),但直接砍掉又让模型不知道有哪些能力可用。
- **实现**:get_tool_definitions 末步把非核心(MCP/插件)工具从 schema 数组换成 tool_search/tool_describe/tool_call 三个桥接工具;_HERMES_CORE_TOOLS 永不延迟。分层披露:Tier1 在 min(threshold_pct×context, listing_max_tokens) 预算内把目录(名字+短描述,超预算退化为 names-only)嵌入 tool_search 描述,Tier2 只嵌每服务器一行摘要;检索用自实现 BM25。tool_call 解包后递归回 handle_function_call,pre/post hook、审批、限长对真实工具名全量生效;并二次校验目标在会话 scoped_deferrable 集合内,防受限子代理经桥接调用未授权工具;调用前按延迟工具 schema probe 校验必填参数,缺参直接返回参数 schema 而非下游黑箱失败。目录每次从活 tool-defs 重建,无跨 turn 状态。
- **证据**:`model_tools.py:1246-1248` · `tools/tool_search.py:291-295` · `tools/tool_search.py:10-11`
  ```
              _scoped_deferrable = _ts_mod.scoped_deferrable_names(current_defs)
              if underlying_name not in _scoped_deferrable:
                  return _return_bridge_result(
  ```
- **规模**:tool_search.py 1078 行 + model_tools.py 桥接段约 110 行,中高复杂度
- **学习价值**:高 — 工具目录渐进披露是 2026 年 harness 前沿(与 Anthropic Tool Search Tool 同构),此实现的独到处在于:无状态目录防漂移、listing 三档退化、桥接对 hook 体系完全透明、以及会话范围双重校验堵住的提权路径。

#### 62. execute_code 编程式工具调用:UDS/TCP/文件三态 RPC + token 鉴权 + 环境洗净

- **解决**:多步工具链每步都要一次推理往返且中间结果占满上下文;让 LLM 写脚本直连工具又会暴露进程凭证并绕过审批体系。
- **实现**:父进程生成 hermes_tools.py 桩模块:本地走 Unix domain socket(macOS 用 /tmp 避开 104 字节路径限制,Windows 退化为 127.0.0.1 TCP),远端(Docker/SSH/Modal/Daytona)走文件 RPC(req_/res_ 原子重命名+自适应轮询);仅脚本 stdout 回到上下文。RPC 服务器逐请求用 secrets.compare_digest 校验 32 字节随机 token(经子进程 env 传递,UDS 文件 chmod 0600),强制 7 工具白名单(SANDBOX_ALLOWED_TOOLS ∩ 会话已启用工具,由调用方传入防子代理篡改进程全局)、50 次调用上限、剥离 terminal 的 background/pty 参数;所有调用走 handle_function_call 使审批/hook/限长照常生效,且 RPC 线程经 propagate_context_to_thread 继承审批上下文防 gateway 静默放行(#33057)。子进程 env 经 _scrub_child_env 洗净:KEY/TOKEN/SECRET/BEARER/APIKEY 等子串全拦,仅安全前缀、操作型 HERMES_* 与 env_passthrough 显式 opt-in 通过。脚本整体还先过 check_execute_code_guard 人审(#30882)。
- **证据**:`tools/code_execution_tool.py:703-708` · `tools/code_execution_tool.py:63-71` · `tools/code_execution_tool.py:259-262` · `tools/code_execution_tool.py:1413-1415`
  ```
                  if not rpc_token or not secrets.compare_digest(
                      # Compare as bytes: compare_digest raises TypeError on a
                      # str with non-ASCII characters, and the token comes from
                      # sandbox-script-supplied JSON.
                      str(request.get("token") or "").encode(), rpc_token.encode()
  ```
- **规模**:code_execution_tool.py 2087 行,高复杂度(三种传输、两种执行模式 project/strict、远端文件轮询协程)
- **学习价值**:高 — README 第 28 行宣称的『Write Python scripts that call tools via RPC』的完整落地:凭证隔离靠 RPC 边界而非信任脚本,审批上下文跨线程/跨进程传播,文件 RPC 让同一机制覆盖所有远端后端——是 Programmatic Tool Calling 的参考实现。

#### 63. MCP 客户端侧安全与动态注册(命名规范、注入扫描、OSV 预检、watchdog、schema 缓存)  **[▲文档不符]**

- **解决**:外部 MCP 服务器是最大的不受信输入面:恶意 npm 包、工具描述藏注入、name 冲突劫持内置工具、stdio 子进程泄漏成孤儿、慢服务器拖死启动。
- **实现**:工具按 mcp__<server>__<tool> 双下划线规范命名并各自归入 mcp-{server} toolset;注册前 _scan_mcp_description 用 10 条注入模式扫描工具描述并告警;stdio spawn 前先对真实 command/args 做 OSV.dev 恶意包预检(12s 超时 fail-open,且刻意在 watchdog 包裹前执行防预检落空),再包一层 parent-death watchdog 防 kill -9 留孤儿;配置层 _filter_suspicious_mcp_servers 丢弃外泄形状的 server 条目、_build_safe_env 只透传安全 env;lossy 名称归一化撞名时全部 fail-closed 跳过而非随机选 handler;include/exclude 支持 fnmatch glob;tools/list 等分页跟随 nextCursor 且 50 页封顶;磁盘 schema 缓存(config 指纹键)让 dashboard 启动不必拉起子进程;list_changed 通知触发 nuke-and-repave 动态刷新,连接失败有指数退避+熔断,elicitation 请求路由到统一人审面(request_elicitation_consent,fail-closed 为 decline)。
- **证据**:`tools/mcp_tool.py:5524-5526` · `tools/mcp_tool.py:2406-2411` · `tools/mcp_tool.py:549-551` · `tools/mcp_tool.py:5817-5820` · `tools/approval.py:4484-4486`
  ```
      safe_server = sanitize_mcp_name_component(server_name)
      safe_tool = sanitize_mcp_name_component(tool_name)
      return f"{MCP_TOOL_NAME_PREFIX}{safe_server}{_MCP_NAME_DELIM}{safe_tool}"
  ```
- **规模**:mcp_tool.py 7230 行(全仓最大工具文件)+ mcp_schema_cache/watchdog/osv_check 约 500 行,极高复杂度
- **学习价值**:高 — 把 MCP 当不受信第三方对待的全套客户端侧防御在一处:spawn 前供应链检查、描述注入扫描、命名撞车 fail-closed、进程生命周期兜底,是接入外部工具生态时的威胁清单模板。其中 pre-spawn OSV 恶意包预检与描述注入扫描在官方文档均无记载。
- **▲ 文档不符**:cli-commands.md 只记载了手动 `hermes security audit` 的 OSV 扫描;stdio MCP 每次启动前自动执行的 OSV 恶意包预检(mcp_tool.py:2398-2422)与工具描述注入扫描(_scan_mcp_description)在 README/AGENTS.md/website 文档中均未提及。

**本子系统文档-代码冲突(4 条):**

- 宣称:website/docs/user-guide/security.md:101 — hardline 模式表『kept in sync with tools/approval.py::UNRECOVERABLE_BLOCKLIST』
  实际:代码中不存在 UNRECOVERABLE_BLOCKLIST 符号(grep 全仓 0 命中);硬底线列表实际叫 HARDLINE_PATTERNS,定义于 tools/approval.py:434,编译版为 HARDLINE_PATTERNS_COMPILED(:480)。(证据:`tools/approval.py:434`)
- 宣称:website/docs/user-guide/security.md:665 — 开启 security.allow_private_urls 后『web tools, the browser, vision URL fetches, and gateway media downloads no longer reject RFC 1918 / loopback / link-local / CGNAT / cloud-metadata destinations』
  实际:代码中云元数据 IP/主机名与整个 link-local 段(_ALWAYS_BLOCKED_IPS / _ALWAYS_BLOCKED_NETWORKS 含 169.254.0.0/16)在 allow_private_urls 开启时仍无条件封禁:is_safe_url 先查 _BLOCKED_HOSTNAMES(:437),再在逐 IP 循环中『Always block cloud metadata IPs and link-local, even with toggle on』(:487-493)后才应用开关。文档声称 link-local 与 cloud-metadata 也被放行与实现不符(放行的只有 RFC1918/loopback/CGNAT)。(证据:`tools/url_safety.py:488`)
- 宣称:website/docs/user-guide/security.md:654 — 『DNS failures are treated as blocked (fail-closed)』
  实际:is_safe_url 对 DNS 失败有代理豁免:当 HTTPS_PROXY 等代理变量已配置且主机名不是字面 IP 时,getaddrinfo 失败会 return True 放行、把解析委托给代理(『proxy configured, allowing through for proxy-side resolution』),并非一律 fail-closed。(证据:`tools/url_safety.py:466-472`)
- 宣称:website/docs/developer-guide/tools-runtime.md:91 — 『Check results are cached per-call — if multiple tools share the same check_fn, it only runs once』(并展示每次调用直接执行 check_fn 的简化代码)
  实际:check_fn 结果实际有跨调用的 30 秒 TTL 缓存(_CHECK_FN_TTL_SECONDS=30.0)且按 multiplex profile 维度隔离,另有 60 秒 last-good 宽限窗口:上次成功 60s 内的失败被判定为 flake,返回缓存的 True 且不缓存失败,防止瞬时探测抖动让整个 toolset 从 schema 中消失。文档描述的仅是最内层 per-call 去重。(证据:`tools/registry.py:216-220`)

### 2.6 终端与执行环境(terminal backends、后台进程、serverless 持久化、浏览器/桌面自动化)

该子系统是 Hermes 的『手』:tools/terminal_tool.py 按 TERMINAL_ENV 在 7 种后端(local/docker/ssh/singularity/modal/daytona/vercel_sandbox,另有经 Nous 网关的 managed Modal 第 8 个环境类)上执行 shell 命令,全部后端收敛到 tools/environments/base.py 的 BaseEnvironment 抽象——spawn-per-call 进程 + export -p/declare -f 会话快照重放 + stdout 内嵌 CWD 标记,从而在只有一次性 exec 原语的环境上重建有状态 shell。环境按 task_id 缓存复用(双检锁),空闲 5 分钟回收但被活跃后台进程保活;Docker 走标签化跨进程容器复用 + 启动期 orphan reaper,Modal/Daytona/Vercel/Singularity 分别用文件系统快照、stop-resume、平台快照、overlay 目录实现 README 宣称的 serverless 休眠,SSH/Modal/Daytona 另配事务性 FileSyncManager 双向同步凭据/skills/缓存。tools/process_registry.py 提供跨后端一致的后台进程语义(本地 pipe/PTY,沙箱内 nohup+log/pid/exit 三文件轮询),叠加 notify_on_complete/watch_patterns 通知、strike 限流与全局熔断、checkpoint 崩溃恢复和 PID-reuse 防误杀。安全面贯穿始终:子进程 secret blocklist 与 skill passthrough 防绕过(GHSA-rhgp-j443-p4rf)、快照会话变量排除(#71296 注入修复)、Docker cap-drop 硬化与 iron-proxy egress 强制。浏览器/桌面自动化独立成栈:browser_tool 多引擎多后端矩阵、CDPSupervisor 对话框桥与 frame 观察、browser_cdp 逃生舱、computer_use 经 cua-driver MCP 驱动三平台桌面并按模型能力路由截图。

关键文件(36 个,行数实测,余见 JSON):`tools/terminal_tool.py`(3432), `tools/environments/base.py`(1370), `tools/environments/local.py`(1687), `tools/environments/docker.py`(2029), `tools/environments/modal.py`(478), `tools/environments/managed_modal.py`(282), `tools/environments/modal_utils.py`(210), `tools/environments/daytona.py`(270)


#### 64. 统一环境抽象:spawn-per-call + 会话快照重放  **[▲文档不符]**

- **解决**:7 种执行后端(local/docker/ssh/singularity/modal/daytona/vercel_sandbox)底层能力差异巨大(有的只有阻塞 SDK exec 调用,没有真实 subprocess),但 agent 需要一个『有状态 shell』的统一假象:cwd、export 的环境变量、函数、alias 都要跨命令持久。
- **实现**:tools/environments/base.py 的 BaseEnvironment 定义唯一契约:子类只需实现 _run_bash() 和 cleanup()。init_session() 用一次 login bash 把 export -p / declare -f / alias -p 原子写入(mktemp+mv,避开 macOS bash 3.2 无 $BASHPID 的并发写撕裂)一个快照文件;每条命令由 _wrap_command() 包装成『source 快照 → cd → eval 用户命令 → 重新 dump 快照 → printf CWD 标记』的完整脚本,cwd 通过 stdout 内嵌的 __HERMES_CWD_<session>__ 标记回传并从输出剥除。SDK 型后端(Modal/Daytona)通过 _ThreadedProcessHandle 把阻塞 exec_fn 适配成带 os.pipe stdout 的 ProcessHandle 鸭子类型,stdin 则降级为 heredoc 嵌入(_stdin_mode="heredoc")。快照失败时逐级回退:bash -l per command → 非 login bash -c(Windows Git-Bash 崩坏场景)。
- **证据**:`tools/environments/base.py:706` · `tools/environments/base.py:823` · `tools/environments/base.py:374`
  ```
  f"mv -f {_snap_tmp} {_quoted_snap} || rm -f {_snap_tmp}\n"
  f"builtin cd -- {_quoted_cwd} 2>/dev/null || true\n"
  f"printf '\\n{self._cwd_marker}%s{self._cwd_marker}\\n' \"$(pwd -P)\"\n"
  ```
- **规模**:base.py 1370 行,加各后端子类共约 6400 行;复杂度高(跨 bash 3.2/MSYS/远端 POSIX 的可移植 shell 生成)
- **学习价值**:高 — 『快照重放代替常驻 shell』是 harness 设计的一个可迁移范式:无需 pty/tmux 就能在任意只支持一次性 exec 的后端上重建有状态 shell,且每步都有原子性与降级路径,值得作为多后端抽象的参考实现。
- **▲ 文档不符**:文档只说 'Filesystem, current working directory, and exported environment variables persist between calls',完全没有讲快照文件机制、原子 mv、以及函数/alias 也被持久化。

#### 65. 非阻塞输出 drain + 有界头尾捕获 + 溢出 spill 文件  **[◇未见于文档、▲文档不符]**

- **解决**:三个真实故障:(1) 用户命令 background 出的孙进程持有 stdout 管道写端,阻塞式 readline 会让工具挂死到孙进程退出(#8340);(2) 超长输出(verbose build)全量驻留内存会 OOM 进程(#64435);(3) 中断/超时/Python 退出时 setsid 出去的子进程组会变 PPID=1 孤儿继续跑。
- **实现**:base.py::_wait_for_process 是所有后端共享的等待循环:select() 100ms 轮询 + 『bash 已退出且管道空闲 3 个周期就停止 drain』解决孙进程管道悬挂;incremental UTF-8 decoder 处理 4096 字节 chunk 边界的多字节字符;_BoundedOutputCollector 维护 40/60 头尾窗口,溢出时把完整流 tee 到 ~/.hermes/cache/terminal-output/out-*.log(上限 5MB,7 天自动清理),结果里附 full_output_path 让 agent 免重跑取回全量输出;自适应轮询从 5ms 指数退避到 200ms(echo 类命令 ~6ms 返回)。中断走 tools/interrupt.py 的线程作用域集合(每个线程只看自己的中断位,网关多会话并发下互不误杀),检测到即 _kill_process(本地后端 override 为 killpg 杀整个进程组)并返回 exit 130;KeyboardInterrupt/SystemExit 也在 finally 中杀进程组。
- **证据**:`tools/environments/base.py:1056` · `tools/environments/base.py:1216` · `tools/interrupt.py:68` · `tools/environments/base.py:1113`
  ```
  elif proc.poll() is not None:
      # bash is gone and the pipe was idle for ~100ms.  Give
      # it two more cycles to catch any buffered tail, then
      # stop — otherwise we wait forever on a grandchild pipe.
      idle_after_exit += 1
  ```
- **规模**:约 500 行核心循环 + interrupt.py 113 行;复杂度高(并发、平台差异、多个已修 bug 的回归防御)
- **学习价值**:高 — 这是 harness『把 shell 输出安全喂给 LLM』问题的完整答案:内存有界、全量可恢复、孙进程不挂死、中断按线程隔离,每个决策都对应一个真实 issue 编号,极适合逐条学习。
- **▲ 文档不符**:full_output_path / spill 文件恢复机制、头尾 40/60 截断策略在 README/website 文档中完全未提及。

#### 66. 后台进程注册表:本地 PTY/pipe 与沙箱内 nohup 双路径

- **解决**:terminal(background=true) 要在所有后端上给出一致的 spawn/poll/wait/kill/stdin 语义;但非本地后端没有宿主机 Popen 句柄,且交互式 CLI(claude/codex/REPL)在无 TTY 时会挂死。
- **实现**:tools/process_registry.py 的 ProcessRegistry 单例管理 ProcessSession(200KB 滚动输出缓冲、完成事件、watcher 元数据)。本地路径 spawn_local:Popen([shell, "-lic", f"set +m; {cmd}"], start_new_session=True) + reader 线程(buffer.read1 增量读 + select 防孙进程管道悬挂);pty=true 时改用 ptyprocess/winpty 生成 30x120 伪终端并支持 write_stdin/submit_stdin/close_stdin(sendeof)。非本地路径 spawn_via_env:把命令包成 `( nohup bash -lc CMD > log 2>&1; rc=$?; printf rc > exit ) & echo $! > pid`,在沙箱内落 log/pid/exit 三个文件,_env_poller_loop 每 2s 通过 env.execute 用 cat 拉增量、kill -0 探活、读 exit 文件收尾;后端消失时标记 completion_reason="lost"。空闲沙箱回收线程(_cleanup_inactive_envs)会因 has_active_processes 刷新 _last_activity 保活沙箱。
- **证据**:`tools/process_registry.py:879` · `tools/process_registry.py:737` · `tools/process_registry.py:1099`
  ```
  bg_command = (
      f"mkdir -p {quoted_temp_dir} && "
      f"( nohup bash -lc {quoted_command} > {quoted_log_path} 2>&1; "
      f"rc=$?; printf '%s\\n' \"$rc\" > {quoted_exit_path} ) & "
      f"echo $! > {quoted_pid_path} && cat {quoted_pid_path}"
  ```
- **规模**:process_registry.py 2529 行;复杂度高(三种 spawn 路径 × 通知 × 恢复)
- **学习价值**:高 — 『沙箱内后台进程 = log/pid/exit 三文件 + 轮询』是把后台进程语义推广到任意只有 exec 接口的远端环境的通用配方;PTY 交互路径(stdin 写入、EOF、桌面终端镜像)也是 agent 驱动交互式 CLI 的少见完整实现。

#### 67. 进程 checkpoint 崩溃恢复 + PID-reuse 防误杀  **[◇未见于文档]**

- **解决**:网关重启/崩溃后,之前 spawn 的后台进程仍在跑;直接按 checkpoint 里的 PID 认领是危险的——内核可能已把该 PID 复用给无关进程(如用户的浏览器),后续 kill/树杀会误杀陌生进程。
- **实现**:每次 spawn/退出原子写 ~/.hermes/processes.json(atomic_json_write),记录 pid、pid_scope(host/sandbox)、以及 /proc/<pid>/stat 第 22 字段的内核启动 ticks(host_start_time)。recover_from_checkpoint() 启动时只认领 host 作用域且 _host_pid_is_ours(pid, recorded_start) 校验启动时间一致的进程,恢复为 detached 会话(可报状态可 kill、不可读输出);sandbox 作用域 PID 对重启后的宿主无意义,直接跳过;watcher 配置随 checkpoint 持久化并在恢复后重新入队(pending_watchers)恢复通知。kill 路径 _terminate_host_pid 同样带 expected_start 校验。
- **证据**:`tools/process_registry.py:2134` · `tools/process_registry.py:103`
  ```
  recorded_start = entry.get("host_start_time")
  if not self._host_pid_is_ours(pid, recorded_start):
  ```
- **规模**:约 300 行(checkpoint 写入/恢复/校验);复杂度中
- **学习价值**:中 — PID + 内核启动时间双因子身份校验是长驻 harness 做进程收养/清扫时必须掌握的安全细节,大多数 agent 框架都缺这层防御。

#### 68. 后台进程通知:notify_on_complete / watch_patterns + 双层限流熔断 + 会话路由  **[▲文档不符]**

- **解决**:agent 不该轮询等待长任务,但『输出匹配即通知』在循环打日志的任务上会瞬间刷爆用户消息渠道;网关多会话并发时,通知还必须投递回拥有该进程的会话而不是随便哪个在 drain 的会话。
- **实现**:reader/poller 线程对每个新输出 chunk 调 _check_watch_patterns:每会话硬性 15s 冷却窗口(WATCH_MIN_INTERVAL_SECONDS),冷却期内的命中记 strike,连续 3 个 strike 窗口(WATCH_STRIKE_LIMIT)永久禁用该会话 watch 并自动升级为 notify_on_complete(附带一条 watch_disabled 说明事件);之上还有全局熔断器 _global_watch_admit(10s 窗口 >15 条即跳闸 30s,恢复时发汇总『N 条被抑制』事件)。事件进 completion_queue,drain_notifications 按 owns_event 回调(正向所有权证明,压缩链感知)或 session_key 相等做路由,不属于本会话的事件重新入队,async_delegation 事件 fail-closed。事件携带 watcher_platform/chat_id/thread_id 等路由元数据,可直达 Telegram/Discord 等消息平台。
- **证据**:`tools/process_registry.py:70` · `tools/process_registry.py:285` · `tools/process_registry.py:1327`
  ```
  WATCH_MIN_INTERVAL_SECONDS = 15   # Minimum spacing between consecutive watch matches
  WATCH_STRIKE_LIMIT = 3            # Strikes in a row → disable watch + promote to notify_on_complete
  ```
- **规模**:约 600 行(watch/drain/format);复杂度高(限流状态机 + 多会话路由语义)
- **学习价值**:高 — 『事件驱动代替轮询』+『strike 状态机自动降级』+『正向所有权证明路由』是自主 agent 通知系统的三个核心难题的成套解法,可直接迁移到任何多会话 harness。
- **▲ 文档不符**:watch_patterns/notify_on_complete 在 goals.md 与工具描述中有提及,但 strike 降级、全局熔断器、watch_disabled/watch_overflow_* 事件类型在官方文档中均无记载,只存在于代码内的模型工具描述字符串里。

#### 69. Serverless 持久化:Modal 文件系统快照 / Daytona stop-resume / Vercel 快照 / Singularity overlay + 远端文件同步

- **解决**:云沙箱按秒计费,session 间保持沙箱常驻成本高;但销毁沙箱又会丢掉 agent 装的包和写的文件。README 宣称的『hibernates when idle and wakes on demand』需要每个后端用各自原语实现。
- **实现**:四种持久化策略按后端原语各自实现,统一以 task_id 为键存 JSON store:Modal cleanup() 时调 sandbox.snapshot_filesystem.aio() 把整个文件系统存成镜像,snapshot_id 写入 ~/.hermes/modal_snapshots.json,下次创建以该快照为 base image 恢复(失败自动删快照回退基础镜像);Daytona 用 sandbox.stop()/start()(_ensure_sandbox_ready 在每次 execute 前把 STOPPED/ARCHIVED 状态的沙箱唤醒),按 hermes-{task_id} 命名 + label 定位复用;Vercel Sandbox 用官方 snapshot API 存 vercel_sandbox_snapshots.json;Singularity 用 --overlay 目录(cleanup 后目录留在宿主)。非 bind-mount 的远端后端(SSH/Modal/Daytona)另配 FileSyncManager:mtime+size 变更检测、事务性批量上传(Daytona 单 HTTP multipart,580 个文件 5min→2s)、cleanup 时 tar 打包 sync_back(2GiB 上限 + 3 次退避重试),把凭据/skills/缓存同步进沙箱、把沙箱内 .hermes 变更带回宿主。
- **证据**:`tools/environments/modal.py:453` · `tools/environments/daytona.py:261` · `tools/environments/singularity.py:204` · `tools/environments/file_sync.py:169`
  ```
  async def _snapshot():
      img = await self._sandbox.snapshot_filesystem.aio()
      return img.object_id
  ```
- **规模**:modal.py 478 + daytona.py 270 + vercel_sandbox.py 662 + singularity.py 268 + file_sync.py 484 ≈ 2160 行;复杂度中高
- **学习价值**:高 — 同一个『持久化』语义在四种云原语(镜像快照/停机恢复/平台快照/overlay 文件系统)上的映射对照,是学习 serverless agent 环境成本工程的绝佳样本;FileSyncManager 的事务回滚 + 批量传输优化也是远端沙箱的通用组件。

#### 70. Docker 硬化沙箱 + 标签化跨进程容器复用 + 孤儿 reaper  **[▲文档不符]**

- **解决**:Docker 后端既要是安全边界(agent 可 pip/npm/apt 但不能提权逃逸),又要兑现『一个长命容器跨 session 共享』:进程内复用、Hermes 进程重启后复用、崩溃后不留僵尸容器。
- **实现**:容器以 --cap-drop ALL + 最小 cap 回加 + no-new-privileges + pids-limit 256 + tmpfs 尺寸限制启动(cgroup 探测失败时优雅降级);持久模式把 ~/.hermes/sandboxes/docker/<task_id>/{home,workspace} bind 到 /root 与 /workspace。跨进程复用:容器打 hermes-agent=1 / hermes-task-id / hermes-profile / hermes-egress 四个 label,_find_reusable_container 用 docker ps -a --filter label= 探测并按需 docker start,egress=off 时还要后过滤拒绝带 egress 指纹的旧容器(防止 egress disable 后继续复用烤进了代理配置的容器);cleanup() 在 persist_across_processes=True(默认)时对容器是 no-op——容器内后台进程跨 /quit 存活;资源回收交给启动期的 reap_orphan_containers(只清扫 Exited 且超过 2×idle 窗口、profile 匹配的容器,每进程只跑一次)。
- **证据**:`tools/environments/docker.py:339` · `tools/environments/docker.py:1961` · `tools/environments/docker.py:1824`
  ```
  _BASE_SECURITY_ARGS = [
      "--cap-drop", "ALL",
      "--cap-add", "DAC_OVERRIDE",
      "--cap-add", "CHOWN",
      "--cap-add", "FOWNER",
  ```
- **规模**:docker.py 2029 行;复杂度高(安全参数 × 复用状态机 × egress 指纹)
- **学习价值**:高 — 标签化容器身份 + 复用指纹 + 启动期 reaper 是把『容器当持久 VM 用』做对的完整工程;egress 标签防降级复用这类跨特性一致性问题尤其值得学。
- **▲ 文档不符**:website/docs/user-guide/features/tools.md:88 声称 'The container is stopped and removed on shutdown',但默认 persist_across_processes=True 下 cleanup() 是 no-op,容器在 Hermes 退出后继续运行,只被下次启动的 orphan reaper 按空闲策略回收(docker.py:1961-1966,cleanup 的 docstring 自己也承认这一点)。

#### 71. iron-proxy egress 强制接入:MITM CA 注入 + per-provider 代理 token

- **解决**:沙箱里 agent 可以任意发起网络请求;要做出栈审计/域名白名单,必须把容器的所有 HTTPS 流量强制经过宿主侧 MITM 代理,并且不能把真实 API key 交进沙箱。
- **实现**:_egress_proxy_args_for_docker() 在容器创建时:(1) 只读挂载 iron-proxy CA 到 /etc/ssl/certs/hermes-egress-ca.crt;(2) 注入 HTTPS_PROXY/HTTP_PROXY(host.docker.internal + --add-host host-gateway)、REQUESTS_CA_BUNDLE/SSL_CERT_FILE/CURL_CA_BUNDLE/NODE_EXTRA_CA_CERTS,并通过哨兵 _HERMES_EGRESS_NODE_OPTIONS_APPEND 对用户已有 NODE_OPTIONS 追加 --use-openssl-ca 收窄 Node 系统 CA store 的绕过面;(3) 从 mappings.json 给每个 provider 注入代理 token 顶替真实 env 名(含 alias),真实 key 留在宿主由代理换发。enforce_on_docker=true(默认)下代理未配置/未运行/CA 丢失/映射为空都直接 RuntimeError 拒绝启动沙箱而非静默降级。
- **证据**:`tools/environments/docker.py:498` · `tools/environments/docker.py:540`
  ```
  "HTTPS_PROXY": proxy_url,
  "https_proxy": proxy_url,
  ```
- **规模**:约 250 行(docker.py 393-634)+ agent/proxy_sources 依赖;复杂度中高
- **学习价值**:中 — 『代理 token 顶替真实凭据 + CA 信任链逐运行时注入 + fail-closed 强制』是沙箱网络治理的标准三件套;Python/curl 替换系统 CA 而 Node 只追加的非对称性分析很有教学价值。

#### 72. 子进程 secret 卫生:blocklist + 动态 secret 判定 + skill passthrough 防绕过 + 快照会话变量排除

- **解决**:本地后端的子进程默认继承网关的 os.environ,里面有全部推理 key、消息平台 token、辅助模型 key;而共享的 bash 快照又会把第一个会话的 HERMES_SESSION_* 泄露给后续所有会话(跨会话身份混淆),甚至可被 Matrix 房间名里带换行的注入载荷利用(#71296)。
- **实现**:三层防御:(1) local.py 的 _HERMES_PROVIDER_ENV_BLOCKLIST 由 provider/工具注册表推导 + 手工补充,_is_hermes_internal_secret 用 AUXILIARY_*_API_KEY / GATEWAY_RELAY_*_{SECRET,KEY,TOKEN} 模式无条件剥离动态命名 secret;(2) tools/env_passthrough.py 的 skill 声明 passthrough 允许放行第三方 key,但拒绝放行任何 blocklist 内的 Hermes 凭据(GHSA-rhgp-j443-p4rf 恶意 skill 绕过的修复),多 profile 时值经 secret scope 解析;(3) base.py 快照 dump 在子 shell 里先 unset ${!HERMES_SESSION_*} 等前缀再 export -p(而非行级 grep,防多行值走私),配合 _inject_session_context_env 每命令由 ContextVar 权威重注入,ContextVar 未绑定且多会话引擎已启用时直接剥离防外来会话身份。
- **证据**:`tools/environments/local.py:474` · `tools/env_passthrough.py:54` · `tools/environments/base.py:470`
  ```
  passthrough = _is_passthrough(key)
  if key in _HERMES_PROVIDER_ENV_BLOCKLIST and not passthrough:
      continue
  ```
- **规模**:local.py 相关约 500 行 + env_passthrough.py 223 行 + base.py 快照排除;复杂度高(带 CVE 修复史)
- **学习价值**:高 — 包含一个真实 GHSA 和一个真实注入漏洞(#71296)的修复全过程,展示了『模型可写入的配置面(skill frontmatter、聊天房间名)都是攻击面』这一 harness 安全第一课。

#### 73. shell 语义修补层:sudo -S 密码管道 + `A && B &` 子壳重写 + 前台命令引导  **[◇未见于文档]**

- **解决**:模型写的 shell 有系统性坑:bare sudo 无 TTY 直接失败;`A && B &` 被 bash 解析成 `(A && B) &`,B 是服务器时子壳永远 wait 导致管道悬挂进程泄漏(#68915);模型爱在前台跑 dev server 然后超时。
- **实现**:terminal_tool.py 提供三个命令改写/守卫:_transform_sudo_command 词法级识别每个真实 sudo 调用(跳过字符串/env 赋值),重写为 sudo -S -p '',按调用次数生成 N 行密码 stdin(SUDO_PASSWORD 配置、缓存、或 45s 交互提示回调;认证失败自动作废缓存),Modal/Daytona 无 stdin 管道则由 wrap_modal_sudo_pipe 变体处理;_rewrite_compound_background 是一个手写 tokenizer,在深度 0 处把 `A && B &` 重写为 `A && { B & }`(brace group 不 fork 子壳),正确处理引号/括号/重定向 `&>`/`>&` 且幂等,前台 execute 和 spawn_local 都过这一层;_foreground_background_guidance 对前台的服务器/watch 类命令直接报错引导用 background=true。
- **证据**:`tools/terminal_tool.py:1049` · `tools/terminal_tool.py:959`
  ```
  # Trailing newline is required: sudo -S reads one line per invocation.
  # Compound commands (`sudo a && sudo b`) need one password line each.
  ```
- **规模**:约 600 行(sudo 变换 + 重写器 + 各类 guard);复杂度中高(手写 shell 词法分析)
- **学习价值**:中 — 展示 harness 如何在不改模型行为的前提下用命令改写吸收 shell 语义坑;`(A && B) &` 子壳 wait 陷阱本身就是值得记住的 bash 知识点。

#### 74. 浏览器自动化架构:CDP supervisor + 对话框桥 + raw CDP 逃生舱 + Camofox/云后端矩阵  **[▲文档不符]**

- **解决**:浏览器自动化有多后端(本地 agent-browser Chromium、Browserbase/Browser Use 云、Camofox 隐身 Firefox、外接 CDP),而 JS 原生对话框(alert/confirm/prompt)会卡死自动化——某些云 CDP 代理还会在 agent 看到之前就自动 dismiss。
- **实现**:tools/browser_supervisor.py 每个 task_id 起一个后台线程 + asyncio 的 CDPSupervisor,持单条 WebSocket 订阅 Page/Runtime/Target 事件(含 OOPIF 自动 attach),维护线程安全快照(pending 对话框、frame 树、console 环形缓冲);对话框桥用 Page.addScriptToEvaluateOnNewDocument 覆写 window.alert/confirm/prompt,改为向虚构主机 hermes-dialog-bridge.invalid 发同步 XHR,由 CDP Fetch 域在网络解析前拦截挂起,agent 通过 browser_dialog 工具 respond_to_dialog 决定 accept/dismiss/输入文本——因此在 Browserbase 上也可用(原生对话框根本不触发)。supervisor 不进工具 schema,状态经 browser_snapshot 合并透出。tools/browser_cdp_tool.py 提供 browser_cdp 任意 CDP 方法直通(私密页面时收敛到白名单方法),tools/browser_camofox.py 对接 Camofox 反检测 Firefox 服务器(CDP override 优先),agent/browser_provider.py 定义云 provider 插件抽象。所有 supervisor 出错文本经 redact_cdp_url 抹掉 ?token= 凭据。
- **证据**:`tools/browser_supervisor.py:95` · `tools/browser_supervisor.py:140` · `tools/browser_cdp_tool.py:3` · `tools/browser_camofox.py:127` · `tools/browser_tool.py:916`
  ```
  DIALOG_BRIDGE_HOST = "hermes-dialog-bridge.invalid"
  DIALOG_BRIDGE_URL_PATTERN = f"http://{DIALOG_BRIDGE_HOST}/*"
  ```
- **规模**:browser_tool.py 5098 + browser_supervisor.py 1518 + browser_camofox.py 953 + browser_cdp_tool.py 684 + browser_provider.py 177 ≈ 8400 行;复杂度很高
- **学习价值**:高 — 『同步 XHR + Fetch 拦截伪主机』把不可拦截的原生对话框变成 agent 可决策事件,是 CDP 层面非常聪明的技巧;supervisor 作为不进 schema 的旁路观察者、raw CDP 逃生舱 + 私密页白名单的分层设计都值得借鉴。
- **▲ 文档不符**:browser.engine=lightpanda(无渲染器高速引擎,含截图请求自动回退 Chrome 的 _run_chrome_fallback_command 机制)在 README/AGENTS.md/website 全部文档中零记载,仅存在于代码。

#### 75. computer_use 跨平台桌面控制 + 截图视觉路由

- **解决**:任意 tool-calling 模型(不限 Anthropic computer-use 原生格式)都要能驱动 macOS/Windows/Linux 桌面;而文本-only 主模型收到 tool result 里的截图会在 provider 边界 400/404 崩溃(#24015)。
- **实现**:tools/computer_use/ 通过 MCP-over-stdio 驱动外部 cua-driver 二进制(后台线程跑专用 asyncio loop 做同步封送),提供 click/type/hotkey/drag/screenshot/launch_app 等动作,capture 支持 som(截图+编号标记)/vision/ax(纯 accessibility 树)三种模式,返回 _multimodal 信封由各 provider 适配器拆装;vision_routing.should_route_capture_to_aux_vision 按『显式 auxiliary.vision 配置 > 用户声明 supports_vision > provider 是否接受 tool-result 图片 + models.dev 元数据』决定截图是直接多模态返回还是先经辅助视觉模型转成文字;browser_route.py 把 cua-driver 的类型化浏览器动作以会话态适配进同一个 computer_use 工具(ref 只在最新快照内有效、每次变更失效);doctor.py 输出逐项健康检查而非静默失败。
- **证据**:`tools/computer_use/vision_routing.py:183` · `tools/computer_use/tool.py:594` · `tools/computer_use/cua_backend.py:3`
  ```
  if _explicit_aux_vision_override(cfg):
      return True
  ```
- **规模**:tools/computer_use/ 共 7122 行;复杂度高
- **学习价值**:中 — 『能力探测驱动的视觉路由』(截图给谁看由 provider/model 能力矩阵决定)解决的是所有多模型 harness 都会遇到的 tool-result 多模态兼容问题,SOM/AX 双通道让纯文本模型也能操作 GUI。

**本子系统文档-代码冲突(3 条):**

- 宣称:website/docs/user-guide/features/tools.md:88:『One persistent container ... The container is stopped and removed on shutdown.』
  实际:默认 persist_across_processes=True 时 DockerEnvironment.cleanup() 对容器是刻意的 no-op:容器在 Hermes 进程退出后继续运行(容器内后台进程存活),只在下次 Hermes 启动时由 reap_orphan_containers 按『空闲超过 2×lifetime』策略回收;stop+rm 仅在 force_remove=True 或用户显式设 TERMINAL_DOCKER_PERSIST_ACROSS_PROCESSES=false 时发生。cleanup 的 docstring 自己写明『stopping it on every Hermes exit breaks that promise』。(证据:`tools/environments/docker.py:1961`)
- 宣称:AGENTS.md:243 目录树注释:『tools/environments/ # Terminal backends (local, docker, ssh, modal, daytona, singularity)』只列 6 种
  实际:代码实际含 8 个环境类:除注释列出的 6 种外还有 vercel_sandbox.py(VercelSandboxEnvironment,TERMINAL_ENV=vercel_sandbox)和 managed_modal.py(ManagedModalEnvironment,经 Nous tool gateway 的托管 Modal,由 TERMINAL_MODAL_MODE 选择);terminal_tool._create_environment 的错误信息列举了全部 7 个 TERMINAL_ENV 值。(证据:`tools/terminal_tool.py:1764`)
- 宣称:工具描述与 tools-reference 均称 terminal 输出会返回给模型,未提及任何截断恢复手段(README/website 无 full_output_path 记载)
  实际:前台命令输出超过 tool_output.max_bytes 时按 40/60 头尾窗口截断,同时完整流被 tee 到 ~/.hermes/cache/terminal-output/out-*.log(5MB 上限),结果 JSON 附 output_total_chars 与 full_output_path 字段供 agent 用 read_file 取回全量输出——该机制仅存在于代码。(证据:`tools/environments/base.py:1220`)

### 2.7 会话状态与持久化(SessionDB / checkpoint / trajectory / replay 清理)

该子系统是 Hermes Agent 的持久层核心:单个 SQLite 文件 ~/.hermes/state.db 承载全部会话元数据、完整消息转写、按模型/任务维度的用量记账、gateway 路由索引、跨进程压缩锁与异步委托簿记,由 SessionDB(hermes_state.py, 9691 行)加三个 mixin(schema/搜索/可移植)实现。它在 harness 意义上做了五件大事:(1) 多进程安全的写引擎——BEGIN IMMEDIATE + 抖动重试 + 按业务重要性分级的锁等待预算,叠加 WAL 回退、macOS F_FULLFSYNC、零化库隔离、多级 schema 自修复等事故驱动的耐久性防御;(2) 会话可恢复性——active/compacted 双标志软删除同时支撑 /undo(rewind)与非破坏性压缩归档,resolve_resume_session_id 沿压缩世系走到真正持有最新消息的 tip,replay_cleanup 在回放前剥离崩溃留下的悬空 tool 调用并把副作用调用标记为 UNKNOWN、给危险确认加 60s TTL;(3) 跨平台连续性——session_key/对等体元组落库 + gateway_routing 表让路由索引可丢可重建,handoff 状态机用 sessions 行上的条件 UPDATE 实现 CLI→消息平台的原子会话交接;(4) 文件系统安全网——CheckpointManager 用共享 bare git store 做 LLM 不可见的每回合快照与回滚,file_state/tool_result_storage 在进程内提供跨子代理写冲突守卫与大结果落盘;(5) 研究管线——save_trajectory 把运行轨迹以 ShareGPT JSONL 双轨(成功/失败)落盘供训练,与 state.db 分离。另有 token 记账后台写线程(coalescing 队列 + atexit 排空)、AsyncSessionDB to_thread 包装、prune/vacuum/auto-archive 存储治理与 Telegram topic 绑定迁移等配套设施。官方 session-storage.md 覆盖了大约一半能力,且版本号、重试模型、WAL 声明均已滞后于代码。

关键文件(15 个,行数实测,余见 JSON):`hermes_state.py`(9691), `hermes_state_common.py`(614), `hermes_state_schema.py`(1079), `hermes_state_portability.py`(714), `hermes_state_search.py`(2230), `tools/checkpoint_manager.py`(1953), `agent/trajectory.py`(56), `agent/replay_cleanup.py`(323)


#### 76. 单文件 SQLite 会话库 + 声明式 schema 调和  **[▲文档不符]**

- **解决**:harness 需要在 CLI/gateway/TUI/cron 多进程共享一份持久会话库,且 schema 随版本快速演进;传统按版本号排队的迁移链容易因插队/重排漏掉列,导致老库损坏或字段缺失。
- **实现**:全部会话状态存在 ~/.hermes/state.db 一个 SQLite 文件里(sessions/messages/session_model_usage/state_meta/gateway_routing/compression_locks/async_delegations 七张表,SCHEMA_SQL 定义于 hermes_state_common.py)。启动时 _init_schema 先 executescript(SCHEMA_SQL),再用 _reconcile_columns() 把活库列与 SCHEMA_SQL 声明 diff 后 ADD COLUMN 补齐(Beets/sqlite-utils 模式),版本号链只保留无法声明式表达的数据迁移(v16 委托子会话打标、v20 用量回填、v22 PK 重建、v23 FTS 外容量布局);PK 无法 ALTER 的表用 _heal_gateway_routing_pk/_heal_session_model_usage_pk 整表重建自愈。SCHEMA_VERSION=25。
- **证据**:`hermes_state_schema.py:594` · `hermes_state_common.py:167`
  ```
          self._reconcile_columns(cursor)
  
          # Rebuild gateway_routing if it still carries the pre-scope PRIMARY
          # KEY (session_key alone). ADD COLUMN cannot fix a PK, so this is
          # the one table-shape repair reconciliation can't express.
  ```
- **规模**:SCHEMA_SQL+DDL 约 420 行(hermes_state_common.py),调和/迁移逻辑约 1000 行(hermes_state_schema.py);复杂度高——要兼容 v1..v25 全部历史库形态
- **学习价值**:高 — 声明式 schema 调和(diff 活库 vs 单一真源 SQL)是消灭版本迁移链腐化的实用模式,任何长寿命 agent harness 的本地存储都值得照抄;PK 无法 ALTER 时的重建自愈也是 SQLite 实战必修课。
- **▲ 文档不符**:website/docs/developer-guide/session-storage.md:144 写 'Current schema version: **23**',代码是 SCHEMA_VERSION = 25(hermes_state_common.py:167);文档迁移表也缺 v24/v25。

#### 77. SQLite 耐久性防御工事(WAL 回退 / macOS F_FULLFSYNC / 零化库隔离 / 多级自修复)  **[◇未见于文档、▲文档不符]**

- **解决**:state.db 是 harness 的唯一事实源,跑在 NFS/SMB/virtiofs、macOS launchd 关机、带 WAL-reset bug 的 SQLite 构建等各种恶劣环境上,任何一次损坏都等于用户全部会话历史丢失。
- **实现**:apply_wal_with_fallback() 在 WAL 不可用的文件系统上降级 DELETE 并去重报错;在带上游 WAL-reset 损坏 bug(3.7.0–3.51.2)的 SQLite 构建上主动拒绝为新库开 WAL。macOS 上 _apply_macos_checkpoint_barrier/_enforce_macos_synchronous_full 强制 checkpoint_fullfsync=1 + synchronous=FULL,因为 Darwin 的 fsync 不保证落盘(issue #30636 的根因)。启动前 is_zeroed_state_db 用 pre-open 字节探针识别 #68474 全零文件签名,quarantine_zeroed_state_db 在跨进程 flock 下把它改名隔离。repair_state_db_schema 按破坏性递增尝试:FTS 'rebuild' 原地重建 → REINDEX → sqlite_master 去重 → 丢弃 FTS schema+VACUUM,canonical 行永不改动。日常写路径上每 50 次写做 PASSIVE wal_checkpoint(TRUNCATE 曾在 65K+ 页库上引发 B-tree 损坏,#45383)。
- **证据**:`hermes_state.py:546` · `hermes_state.py:1771` · `hermes_state.py:673`
  ```
      if sys.platform != "darwin":
          return
      try:
          conn.execute("PRAGMA checkpoint_fullfsync=1")
      except sqlite3.OperationalError:
  ```
- **规模**:hermes_state.py 前 1900 行几乎全是这类防御(约 1400 行),每条路径都引用真实 issue 号;复杂度极高
- **学习价值**:高 — 这是生产级本地持久化的『事故驱动工程』教科书:每个防御都对应一个真实损坏事故(macOS fsync 语义、WAL-reset bug、零化文件、FTS shadow 表损坏),对任何要把用户数据放进 SQLite 的 harness 都是高价值参考。
- **▲ 文档不符**:session-storage.md:28 断言 'WAL mode for concurrent readers + one writer' 是关键设计,但代码在有 WAL-reset bug 的构建上对新库拒开 WAL(hermes_state.py:673-676),且 journal_mode 可经 config 配成 delete(hermes_state.py:614 resolve_journal_mode);零化隔离/多级修复/macOS 屏障文档完全未提。

#### 78. 分级耐心预算的写事务引擎(BEGIN IMMEDIATE + 抖动重试)  **[◇未见于文档、▲文档不符]**

- **解决**:gateway + CLI + worktree 子代理多进程同写一个 state.db,SQLite 内建确定性退避会造成 convoy 效应;而转写(transcript)写失败会直接毁掉用户一个回合,不能与普通写同等对待。
- **实现**:_execute_write() 统一所有写:BEGIN IMMEDIATE 让锁竞争在事务开始就暴露,locked/busy 时释放 Python 锁、随机 jitter(20-150ms,慢锁后退到 250ms-1s)重试。耐心是分级预算而非次数:普通写 _WRITE_PATIENCE_S=20s,转写关键写 _TRANSCRIPT_WRITE_PATIENCE_S=60s(append_message 显式传入,#74478),活动心跳只给 0.5s。撞上他人压缩锁时只等 _COMPRESSION_BUSY_WAIT_S=5s(#75083)。FTS shadow 表损坏导致的写失败会触发一次性 _try_runtime_fts_rebuild 后立即重试;'no more rows available' 这类构建相关瞬态错误按消息文本(而非异常类)识别重试。
- **证据**:`hermes_state.py:2610` · `hermes_state.py:1927`
  ```
                  with self._lock:
                      self._conn.execute("BEGIN IMMEDIATE")
                      try:
                          result = fn(self._conn)
                          self._conn.commit()
  ```
- **规模**:_execute_write 及重试/合并辅助约 250 行,加上异步 token 记账队列(queue_token_counts/_token_writer_loop,约 240 行)构成完整写路径;复杂度中高
- **学习价值**:高 — 『按写的业务重要性分配锁等待预算』(转写 60s vs 心跳 0.5s)是很少见但非常正确的设计——把“哪次写失败会毁掉用户回合”编码进了持久层;jitter 破 convoy、消息文本级错误分类都可直接复用。
- **▲ 文档不符**:session-storage.md:177-190 描述为 'Short SQLite timeout (1 second)、up to 15 retries、_WRITE_MAX_RETRIES = 15',但代码中不存在 _WRITE_MAX_RETRIES,已改为截止时间制耐心预算(hermes_state.py:1927-1928)。

#### 79. 软删除双标志消息模型:rewind/undo 与非破坏性压缩共用 active/compacted  **[◇未见于文档、▲文档不符]**

- **解决**:undo 和上下文压缩都要“从模型视野里拿走消息”,但直接 DELETE 会毁掉审计线索、训练数据和可搜索历史,还会把 FTS 索引拖进 delete 风暴。
- **实现**:messages 表带 active(默认 1)与 compacted(默认 0)两个标志。rewind_to_message()(/undo、/rewind 底座,cli.py:8497、gateway/session.py:3428)把目标 user 行及之后所有行翻成 active=0 并累加 sessions.rewind_count,restore_rewound() 可翻回;语义是『用户收回』(active=0, compacted=0),搜索默认不含。archive_and_compact()(#38763 单会话 id 终身制的压缩路径)在一个事务里把现役行翻成 active=0+compacted=1 再插入压缩摘要行;语义是『被总结掉』——live 加载(get_messages* 默认 WHERE active=1)只看到压缩集,但 search_messages 默认包含 compacted=1 行,历史仍可搜可恢复(include_inactive=True)。
- **证据**:`hermes_state.py:7670` · `hermes_state.py:6987`
  ```
                  conn.execute(
                      f"UPDATE messages SET active = 0 WHERE id IN ({placeholders})",
                      ids,
                  )
              conn.execute(
  ```
- **规模**:rewind/restore 约 110 行 + archive_and_compact/has_archived_messages 约 90 行,再加所有读路径的 active=1 过滤;概念复杂度高于代码量
- **学习价值**:高 — 用两个正交标志区分『用户收回』与『压缩归档』并让搜索/回放/审计各取所需,是会话存储里最优雅的设计之一;比 Claude Code 的 JSONL 重写式 undo 保留了更多可恢复性。
- **▲ 文档不符**:slash-commands.md 把 /undo 描述为 'Remove the last user/assistant exchange',实际是软删除(active=0)且行永久保留可恢复;archive_and_compact 的 compacted 语义在官方文档无任何记载。

#### 80. 压缩世系 + resume 重定向 + 跨进程压缩租约锁  **[◇未见于文档、▲文档不符]**

- **解决**:自动上下文压缩会结束当前会话并 fork 继续子会话(parent_session_id 链),多进程下 resume 旧 id 会读到压缩前转写、丢“最新回复”;两个进程同时压缩同一会话会把世系劈成两条;压缩进行中落地的 steer 消息会写进错误的转写。
- **实现**:三层机制:(1) resolve_resume_session_id() 先用 get_compression_tip() 沿 end_reason='compression' 的父子链走到最新 tip,显式排除 _branched_from/_delegate_from/source='tool' 子会话防止 resume 被子代理劫持,再向下找最深有消息节点(#15000,深度上限 32/100 防环)。(2) compression_locks 表实现 TTL=300s 的跨进程租约:try_acquire_compression_lock 单事务 DELETE 过期 + INSERT OR IGNORE + SELECT 确认,结构化 holder 里 pid 已死则立即回收。(3) append_message/append_messages_batch 事务内跑 _check_transcript_write_guards:他人持有活租约则抛 SessionCompressionInProgressError(_execute_write 等 5s 再放弃),会话已 end_reason='compression' 则抛 CompressionSessionClosedError,配合 find_live_compression_child 只在恰好一个活直接子时才安全转移。
- **证据**:`hermes_state.py:7213` · `hermes_state.py:4108` · `hermes_state.py:6266`
  ```
          try:
              tip = self.get_compression_tip(session_id)
          except Exception:
              tip = session_id
          if tip and tip != session_id:
  ```
- **规模**:锁 + 冷却 + 世系 + resume 重定向合计约 900 行(hermes_state.py:3445-3660、4008-4185、5719-5777、7176-7263),是本文件最难的部分
- **学习价值**:高 — 把『上下文压缩』当成需要分布式租约、世系追踪、失败冷却(compression_failure_cooldown/fallback_streak/ineffective_count 列)的一等持久化事件,是多进程 harness 独有的深水区;desktop『回来后回复不见了』这类 bug 的修法全在这里。
- **▲ 文档不符**:session-storage.md 只在架构图里列了一行 'compression_locks — Cross-process compression locking',租约回收、写入准入守卫、resume 重定向、失败冷却列全部未记载。

#### 81. 跨平台会话交接(/handoff)持久状态机

- **解决**:用户在 CLI 里跑到一半想转到 Telegram/Discord 继续同一对话;CLI 进程和 gateway 进程互不相通,需要一个双进程都可见、崩溃可恢复的交接协议。
- **实现**:交接状态直接放在 sessions 行上(handoff_state/handoff_platform/handoff_error 三列)。CLI 端 /handoff 调 request_handoff() 用条件 UPDATE 原子置 pending(仅当空闲或已终态),然后 0.5s 轮询 get_handoff_state 等终态(hermes_cli/cli_commands_mixin.py:904)。gateway 端 _handoff watcher 循环 list_pending_handoffs()(按 idx_sessions_handoff_state 索引),用 claim_handoff() 的 'UPDATE ... WHERE handoff_state=пending' 原子抢占(多 gateway 安全),在目标平台开新线程、把目的地重新绑定到同一 session_id、伪造一条合成用户回合让 agent 在新地方自报到,最后 complete_handoff/fail_handoff 收尾(gateway/run.py:11698-11710)。
- **证据**:`hermes_state.py:9592` · `hermes_state.py:9645`
  ```
              cur = conn.execute(
                  "UPDATE sessions "
  ```
- **规模**:SessionDB 侧约 90 行(hermes_state.py:9585-9674)+ CLI/gateway 消费端约 200 行;协议简单但跨进程语义严谨
- **学习价值**:中 — 用共享 SQLite 行做进程间工作队列(条件 UPDATE 抢占 = 免额外基建的 leader election)是轻量 harness 的实用招式;“同一 session_id 换宿主平台继续”体现了会话与前端解耦的存储设计。

#### 82. 网关路由持久化与对等体会话找回(session_key / gateway_routing)  **[◇未见于文档、▲文档不符]**

- **解决**:gateway 原以 sessions.json 做『平台对等体 → 会话』路由索引,进程级重启 bug 会把它整个丢掉,导致 Telegram 群/Discord 频道的用户突然“失忆”。
- **实现**:路由三重落库:(1) sessions 行持久化确定性 session_key + 完整对等体元组(user_id/chat_id/chat_type/thread_id/display_name/origin_json,#9006),record_gateway_session_peer 在显式 resume 换道时可用递归 CTE 把整条压缩世系一起改绑;(2) gateway_routing 表按 (scope, session_key) 存完整序列化 SessionEntry,scope=sessions_dir 路径,彻底取代 sessions.json;(3) find_latest_gateway_session_for_peer() 在索引丢失时从 sessions 行重建映射——只把 end_reason 属于已知误杀类('agent_close'、'ws_orphan_reap')或未结束且有消息的行视为可恢复,显式对话边界(/new、压缩分裂)不复活;精确 key 未命中时退化为要求完整对等体元组匹配,绝不跨聊天/线程/用户。
- **证据**:`hermes_state.py:3405` · `hermes_state.py:3224`
  ```
                    AND (s.ended_at IS NULL OR s.end_reason IN ('agent_close', 'ws_orphan_reap'))
                    AND (COALESCE(s.message_count, 0) > 0 OR EXISTS (
  ```
- **规模**:hermes_state.py:3103-3443 约 340 行,另有 Telegram topic 绑定迁移(8851-9360)约 500 行;复杂度高
- **学习价值**:中 — 『快索引可丢、真源可重建』的双层路由设计,以及按 end_reason 白名单区分“误杀可复活”与“用户显式结束”的恢复语义,是多平台 gateway harness 的关键鲁棒性模式。
- **▲ 文档不符**:session-storage.md 架构图仅一行 'gateway_routing — Gateway routing metadata';对等体找回的 end_reason 白名单、压缩世系整体改绑 CTE 均无文档。

#### 83. 回放前转写消毒:中断尾剥离、副作用 UNKNOWN 化、危险确认过期  **[◇未见于文档]**

- **解决**:进程被 kill/重启在 tool 循环中间死掉时,持久转写以悬空 assistant(tool_calls) 或中断 tool 结果结尾;resume 后模型会重发未应答的调用,造成无限重启循环(#49201),更危险的是陈旧的『确认强制重启』文本会被模型当成新确认再次执行破坏性动作(#59607)。
- **实现**:agent/replay_cleanup.py 提供纯函数 sanitize_replay_history(),被消息 gateway 与 TUI/WebUI 两条 resume 路径共享。strip_interrupted_tool_tails 移除含中断标记的 assistant→tool 块;strip_dangling_tool_call_tail 处理零应答尾部。关键区分:只读工具直接删块,而 tool_may_have_side_effect 的调用不删——为每个 call 合成 effect_disposition='unknown' 的工具结果,内容明说『可能已执行、效果未知、重试前先检查状态』,防止模型盲目重放副作用。strip_stale_dangerous_confirmations 对匹配确认词表(含中文变体)且超过 60s 的 user 消息原地改写为过期哨兵(保留角色以维持严格交替),并 drop_stale_api_content 丢弃字节级 sidecar 防止旧确认原文重上 wire。
- **证据**:`agent/replay_cleanup.py:168` · `agent/replay_cleanup.py:313`
  ```
              content = (
                  "[Orphan recovery: this tool may have executed before Hermes stopped; "
                  "its effect is UNKNOWN. Inspect current state before retrying.]"
                  if disposition == "unknown"
                  else "[Orphan recovery: this read-only tool did not complete and had no effect.]"
  ```
- **规模**:agent/replay_cleanup.py 323 行纯函数;另有 hermes_state.py 侧 _strip_stale_tool_call_markers/purge_stale_tool_call_markers 做持久层同类清理;复杂度中
- **学习价值**:高 — 『crash 后 resume 安全』是 agent harness 最容易踩的坑:副作用调用不能删只能标 UNKNOWN、危险确认必须带 TTL、改写要保持角色交替——三条都是从真实事故(无限重启循环、误触发关机)提炼的安全不变量,几乎无处可学。

#### 84. 共享影子 git 仓库的文件系统检查点(CheckpointManager)  **[▲文档不符]**

- **解决**:agent 的 write_file/patch/破坏性 terminal 命令可能毁掉用户文件,需要 LLM 不可见的自动快照与回滚,且不能污染用户项目目录、不能因十几个 worktree 重复存储同一批 blob。
- **实现**:v2 设计用单一共享 bare store(~/.hermes/checkpoints/store),GIT_DIR+GIT_WORK_TREE+GIT_INDEX_FILE 三环境变量隔离,零 git 状态泄入用户目录;每项目一个 refs/hermes/<hash16> 引用 + 独立 index 文件,git 内容寻址天然跨 worktree 去重(旧版每目录一个影子仓,12 个 worktree 浪费约 500MB)。ensure_checkpoint 每回合每目录至多一次(new_turn 清 dedup 集),_take 走纯 plumbing:read-tree 播种 index → add -A → 剔除超限大文件 → diff-index 无变化即跳过 → write-tree → commit-tree → update-ref(带 CAS 旧值)。restore 前先自动拍 pre-rollback 快照实现『撤销撤销』;retention_days/max_snapshots/max_total_size_mb 三维修剪 + gc --prune=now,工作目录消失需 _workdir_is_observably_gone 多信号确认才删 ref。
- **证据**:`tools/checkpoint_manager.py:1100` · `tools/checkpoint_manager.py:944`
  ```
          commit_args = ["commit-tree", tree_sha, "-m", reason, "--no-gpg-sign"]
          if has_ref:
              commit_args = ["commit-tree", tree_sha, "-p", ref_commit, "-m", reason, "--no-gpg-sign"]
  ```
- **规模**:tools/checkpoint_manager.py 1953 行;git plumbing + 存储治理 + 遗留迁移,复杂度高
- **学习价值**:高 — 与 Claude Code 的 rewind 机制同类但实现更透明:纯 git plumbing、单店去重、restore 自拍快照、体积/年龄/孤儿三维治理,是给任何 harness 加“文件系统时光机”的完整参考实现。
- **▲ 文档不符**:文档(configuration.md『Checkpoints』/ checkpoints-and-rollback 页)讲了开关与配置项,但共享单店去重架构、pre-rollback 自动快照、legacy 迁移未见于官方文档,属实现层未记载细节。

#### 85. ShareGPT 轨迹落盘(research/训练数据管线入口)

- **解决**:Nous 用 Hermes Agent 生成工具调用训练数据,需要把每次 agent 运行的完整对话以训练可用格式(ShareGPT)持久化,并区分成功/失败样本。
- **实现**:agent/trajectory.py 的 save_trajectory() 把 ShareGPT 格式对话连同 model/completed/timestamp 元数据追加为 JSONL:成功进 trajectory_samples.jsonl,失败进 failed_trajectories.jsonl。convert_scratchpad_to_think 把 <REASONING_SCRATCHPAD> 标签改写成训练侧惯用的 <think>。转换逻辑 _convert_to_trajectory_format 留在 AIAgent 上,被 run_agent.py:2340(单次运行 --save-trajectory)与 batch_runner.py:358(批量数据生成)共同调用;与 state.db 完全独立(文档明确 batch/RL 轨迹不入库),下游接 trajectory_compressor.py 做训练前压缩。
- **证据**:`agent/trajectory.py:41` · `agent/trajectory.py:20`
  ```
      if filename is None:
          filename = "trajectory_samples.jsonl" if completed else "failed_trajectories.jsonl"
  ```
- **规模**:agent/trajectory.py 仅 56 行,但它是 batch_runner/trajectory_compressor 整条研究管线的持久化入口;复杂度低
- **学习价值**:中 — 展示了『产品 harness 兼作训练数据工厂』的最小接口:运行时转写(state.db)与训练轨迹(ShareGPT JSONL)双轨分离,成功/失败分流本身就是数据标注。

#### 86. 会话导出/导入可移植层(含压缩世系合并与运行态消毒)  **[◇未见于文档、▲文档不符]**

- **解决**:用户要在机器间搬迁会话、备份历史,但直接搬行会带来三类灾难:外键指向不存在的父会话、导入陈旧的 handoff/活动心跳等『活运行态』被看门狗当真、压缩劈开的多段会话在新机上支离破碎。
- **实现**:SessionPortabilityMixin:export_session_lineage() 把整条压缩世系合并为一个逻辑会话 dict(segments + 拼接 messages);import_sessions() 做强 schema 校验(上限 _IMPORT_MAX_SESSIONS、字段逐个类型检查),已存在 id 跳过,父指针只在父已存在或同批导入且 _would_create_cycle 检环通过时才回填,否则 detach;gateway 路由、handoff、rewind、last_activity_* 活动字段全部有意重置为 NULL——『导入恢复的是对话历史,不是活频道或进程的所有权』(#76354 review S4,防止看门狗对幻影活动做出反应);system_prompt 经 _store_system_prompt 走 hash 去重的 system_prompts 表。
- **证据**:`hermes_state_portability.py:692` · `hermes_state_portability.py:287`
  ```
                  if parent_exists and not _would_create_cycle(session_id, parent_id):
                      conn.execute(
  ```
- **规模**:hermes_state_portability.py 714 行,导入校验/消毒约 350 行;复杂度中高
- **学习价值**:中 — 『导出包含活运行态、导入必须消毒活运行态』这条不对称契约,是会话可移植性里最容易漏的安全点;世系合并导出也演示了把物理分段还原为逻辑会话的正确姿势。
- **▲ 文档不符**:session-storage.md 只记载 export_session/export_all/prune;import_sessions、export_session_lineage、运行态重置契约完全无文档。

#### 87. 工具结果三层落盘 + 跨子代理文件新鲜度守卫  **[◇未见于文档]**

- **解决**:巨型工具输出(构建日志、文件 dump)会撑爆上下文窗口,粗暴截断又丢信息;并行子代理同写一个文件时,A 用陈旧读缓存覆盖 B 的修改会造成静默数据丢失。
- **实现**:tools/tool_result_storage.py 三层防御:工具自截断 → maybe_persist_tool_result 超过阈值把全文经 env.execute() 写进沙箱 /tmp/hermes-results/{tool_use_id}.txt(内容走 stdin 管道绕开 Linux MAX_ARG_STRLEN 128KB argv 上限),上下文里只留 <persisted-output> 预览 + 路径,模型可 read_file 分页取回 → enforce_turn_budget 对单回合聚合超 200K 时按大小贪心落盘。tools/file_state.py 的进程级单例 FileStateRegistry 记录 per-agent 读戳(mtime/时刻/是否分页部分读)与全局 last-writer,check_stale 在写前按严重度返回三类警告(兄弟子代理后写、外部 mtime 漂移、从未读过/仅部分读),lock_path 提供 per-path 锁包住 read→modify→write;delegate_tool 用 writes_since 在子代理完成时提醒父代理哪些已读文件被改。
- **证据**:`tools/tool_result_storage.py:114` · `tools/file_state.py:184`
  ```
      cmd = f"mkdir -p {shlex.quote(storage_dir)} && cat > {shlex.quote(remote_path)}"
      result = env.execute(cmd, timeout=30, stdin_data=content)
      return result.get("returncode", 1) == 0
  ```
- **规模**:tool_result_storage.py 254 行 + file_state.py 332 行;两者都是小而精的进程内状态层,复杂度中
- **学习价值**:高 — 这两个是并行多代理 harness 的标配缺件:结果落盘把“上下文预算”变成可分页外存(且照顾了远程沙箱一致性),文件新鲜度守卫等于给文件系统加了乐观并发控制——分页部分读也算 stale 这一细节尤其见功力。

**本子系统文档-代码冲突(4 条):**

- 宣称:website/docs/developer-guide/session-storage.md:144 声称 'Current schema version: **23**',迁移表也止于 v23
  实际:代码基线 SCHEMA_VERSION = 25(v24/v25 未见于文档迁移表)(证据:`hermes_state_common.py:167`)
- 宣称:session-storage.md:177-190 声称写竞争用 'Short SQLite timeout (1 second)'、'up to 15 retries',并引用常量 _WRITE_MAX_RETRIES = 15
  实际:代码中不存在 _WRITE_MAX_RETRIES;重试已改为截止时间制耐心预算:普通写 _WRITE_PATIENCE_S = 20.0s,转写关键写 _TRANSCRIPT_WRITE_PATIENCE_S = 60.0s,活动心跳 _ACTIVITY_WRITE_PATIENCE_S = 0.5s,慢锁后 jitter 退避到 250ms-1s(证据:`hermes_state.py:1927`)
- 宣称:session-storage.md:13/28 声称 state.db 无条件运行 'SQLite, WAL mode'、'WAL mode for concurrent readers + one writer' 是关键设计决策
  实际:apply_wal_with_fallback 在 WAL 不兼容文件系统上降级 DELETE;在带上游 WAL-reset 损坏 bug 的 SQLite 构建(3.7.0-3.51.2)上对新库主动拒开 WAL;journal_mode 还可经 config.yaml database.journal_mode 显式配成 delete(resolve_journal_mode)(证据:`hermes_state.py:674`)
- 宣称:website/docs/reference/slash-commands.md:45 把 /undo 描述为 'Remove the last user/assistant exchange'(移除)
  实际:底层 rewind_to_message 是软删除:行保留在库中翻成 active=0,可经 restore_rewound/include_inactive=True 恢复,并累加 sessions.rewind_count 审计计数;并非物理移除(证据:`hermes_state.py:7613`)

### 2.8 CLI 前端(cli.py + hermes_cli/)

Hermes 的 CLI 前端由 18555 行的 cli.py(HermesCLI:prompt_toolkit 全屏 REPL/TUI,含流式渲染、状态栏、审批/澄清/秘密输入三类模态、语音+唤醒词、pet 吉祥物、worktree 管理)与 hermes_cli/ 下 262 个文件的命令行工具箱组成,main.py 的 argparse 全树挂了几十个子命令(setup/model/gateway/dashboard/update/doctor/kanban/curator/profile/plugins/skills/...)。架构核心是三个「单一事实源」:commands.py 的 COMMAND_REGISTRY 同时驱动 CLI 分发、gateway busy 策略、Telegram/Slack 菜单和 tab 补全五个消费方(slash_exec.py 再为信息类命令提供表面无关执行器);config.py 的分层加载器族(load_config/load_config_readonly/read_raw_config/read_user_config_raw)带 last-known-good 回退与 managed-scope 管理员覆盖;skin_engine.py 的 YAML 皮肤一份定义同步 CLI/TUI/桌面三表面。此外还有 import 前预解析 -p 的多 profile 实例机制、插件系统向 argparse 与会话斜杠双通道注入命令、_startup_fast/meta_path 惰性补丁等启动延迟工程、带双重验证与自动回滚的自更新管线,以及 17k 行 FastAPI dashboard(把同一 `hermes --tui` 二进制经 PTY-over-WebSocket 嵌进浏览器并支持断线重连)。文档覆盖总体良好(AGENTS.md/website 对注册表、皮肤、插件均有专章),但 slash_exec 执行器层、配置 LKG 回退、启动优化和更新回滚验证均为代码独有;发现两处文档与代码不符(前缀歧义解析规则、PTY 桥的 Windows 支持)。

关键文件(30 个,行数实测,余见 JSON):`cli.py`(18555), `hermes_cli/main.py`(12599), `hermes_cli/commands.py`(2260), `hermes_cli/slash_exec.py`(272), `hermes_cli/config.py`(5434), `hermes_cli/config_defaults.py`(4313), `hermes_cli/setup.py`(3645), `hermes_cli/model_setup_flows.py`(3151)


#### 88. 中央命令注册表 COMMAND_REGISTRY(五方复用 + busy_policy 中台)

- **解决**:同一套斜杠命令要在 CLI REPL、gateway 消息平台、Telegram 菜单、Slack manifest、tab 补全五个表面保持一致;若各处手写 if-chain,加一个命令/别名要改五处且必然漂移。此外 agent 忙时(mid-run)每个命令的行为(拒绝/直接执行/先打断再执行)也需要统一声明。
- **实现**:hermes_cli/commands.py 用 frozen dataclass CommandDef(name/aliases/args_hint/subcommands/cli_only/gateway_only/gateway_config_gate/busy_policy/busy_handler/execute)构成 ~90 条的 COMMAND_REGISTRY 列表。派生物全部在 import 时生成:COMMANDS/COMMANDS_BY_CATEGORY/SUBCOMMANDS(CLI help+补全)、GATEWAY_KNOWN_COMMANDS(gateway 分发)、telegram_bot_commands()(setMyCommands,连字符转下划线、限 100 条并按 _TELEGRAM_MENU_PRIORITY 排序)、slack_app_manifest()/slack_subcommand_map()(Slack slash 清单)、SlashCommandCompleter/SlashCommandAutoSuggest(prompt_toolkit 补全)。cli.py process_command 用 resolve_command() 把别名归一为 canonical 名再 dispatch;gateway/run.py 的 _dispatch_busy_slash_command 按 CommandDef.busy_policy(dispatch/reject/interrupt_then_dispatch)+busy_handler 表驱动 mid-run 行为,取代手写 if-chain。cli_only 命令可用 gateway_config_gate 配置点位在 gateway 侧解锁。
- **证据**:`hermes_cli/commands.py:3` · `hermes_cli/commands.py:75` · `cli.py:9849` · `hermes_cli/commands.py:600` · `gateway/run.py:14117`
  ```
  Central registry for all slash commands. Every consumer -- CLI help, gateway
  dispatch, Telegram BotCommands, Slack subcommand mapping, autocomplete --
  derives its data from ``COMMAND_REGISTRY``.
  ```
- **规模**:commands.py 2260 行 + gateway/run.py 中 Guard-1/Guard-2 消费点;中等复杂度,数据驱动设计非常干净
- **学习价值**:高 — 多表面 agent 产品(CLI/IM/桌面)命令一致性的教科书解法:单一 dataclass 注册表 + import 时派生 + busy_policy 声明式中台,值得直接照搬。

#### 89. 表面无关命令执行器 slash_exec.EXECUTORS(registry-owned execution)  **[◇未见于文档]**

- **解决**:信息类命令(/version、/profile、/help、/bundles、/egress)的核心文本在 CLI、gateway、TUI 三个表面各写一份会漂移;而把执行器直接挂进 commands.py 又会让 gateway 无 prompt_toolkit 环境无法 import 注册表。
- **实现**:hermes_cli/slash_exec.py 定义 CommandContext/CommandReply 两个 frozen dataclass 与 EXECUTORS 字典(纯格式化函数,无 agent/session 副作用)。CommandDef.execute 只存字符串 key(不存 callable),commands.py 因此不 import slash_exec,保持 gateway import 轻量、无环。各表面经 run_execute() 解析后只叠加自己的装饰(Rich markup / emoji markdown / _telegramize_command_mentions)。不变量:执行器输出只依赖 ctx.args/ctx.options、绝不依赖 ctx.surface,由 tests/hermes_cli/test_commands_execute.py 强制核心文本跨表面逐字一致。
- **证据**:`hermes_cli/slash_exec.py:3` · `hermes_cli/slash_exec.py:14`
  ```
  Shared, surface-independent executors for informational slash commands.
  ``CommandDef.execute`` (hermes_cli/commands.py) names a key in
  :data:`EXECUTORS`; each surface (CLI REPL, gateway, TUI slash worker via the
  CLI) resolves that key through :func:`run_execute` and applies only its own
  decoration (Rich markup, emoji/markdown, ``_telegramize_command_mentions``)
  ```
- **规模**:272 行,小而精;配套测试强制不变量
- **学习价值**:高 — 「注册表存字符串 key 而非 callable」解决 import 重量与循环依赖,同时用测试锁定跨表面文本一致——多前端 harness 的低成本去重范式。

#### 90. 配置加载器族(load_config / load_config_readonly / read_raw_config / read_user_config_raw)+ last-known-good + managed overlay  **[◇未见于文档]**

- **解决**:config.yaml 同时被热路径读取(每 API turn)、写回路径修改、诊断路径检查:一个加载器无法同时满足性能(deepcopy ~135us/次)、写回正确性(不能把几百个默认键持久化进用户文件)、和策略安全(用户改坏 YAML 时不能静默丢掉 approvals.deny 等安全规则)。
- **实现**:config.py 提供分层加载器:load_config()(DEFAULT_CONFIG 深合并 + 迁移 + ${VAR} 展开,返回 deepcopy)/load_config_readonly()(免 deepcopy 快路径)/read_raw_config()(原始 YAML,写回专用)/read_raw_config_readonly()/read_user_config_raw()(逐字读盘,docstring 穷举列出仅有的三类合法调用点)。缓存键为 (mtime_ns,size) 并叠加 managed 配置文件签名与 env 快照(#58514:env 变化使 ${VAR} 展开失效)。解析失败时退回进程内 last-known-good(移植 openai/codex#31188 不变量)而非默认值;managed scope(/etc/hermes)在用户展开之后 leaf 级覆盖,防止用户 ${VAR} 遮蔽管理员钉死值;atomic_config_write() 先 require_readable_config_before_write() 再原子写,防止「读不到→当成空→覆盖」抹掉整个配置。
- **证据**:`hermes_cli/config.py:3357` · `hermes_cli/config.py:3391` · `hermes_cli/config.py:3132` · `hermes_cli/config.py:3099`
  ```
                  # Within a running process we still have the last successfully
                  # loaded config — keep serving it until the file is fixed.
                  # Fresh processes with no last-known-good keep the existing
                  # DEFAULT_CONFIG fallback.
                  lkg = _LAST_EXPANDED_CONFIG_BY_PATH.get(path_key)
  ```
- **规模**:config.py 5434 行 + config_defaults.py 4313 行 + config_migrations.py;高复杂度,是全仓库被引用最广的模块之一
- **学习价值**:高 — 长驻 agent 的配置层三难(热路径性能/写回保真/安全规则不可静默丢失)的完整解:LKG 回退、env 快照失效、managed leaf 覆盖、fail-closed 原子写都可直接借鉴。

#### 91. Profile 多实例:import 前 -p 预解析 + shell wrapper + 独立 HERMES_HOME + 档案导入导出

- **解决**:一台机器上要跑多个互相隔离的 agent 身份(不同模型/技能/gateway/凭据),且 HERMES_HOME 决定所有模块的路径常量,必须在任何 hermes 模块 import 之前就定下来。
- **实现**:main.py _apply_profile_override() 在 argparse 之前手工扫 argv 找 -p/--profile(并跳过 `mcp add --args` 透传区、处理 sudo 场景用 SUDO_USER 反解 home),经 profiles.py resolve_profile_env() 映射到 ~/.hermes/profiles/<name> 并设置 HERMES_HOME。create_wrapper_script() 在 ~/.local/bin/<alias> 生成 `exec hermes -p <profile> "$@"` 的 shell/bat 包装,使每个 profile 变成独立可执行命令;删除时校验内容含 "hermes -p" 防误删。每个 profile 可注册独立 gateway systemd/launchd 服务(_maybe_register_gateway_service),export_profile/import_profile 走带路径清洗的 tar 安全解包(_safe_extract_profile_archive)实现 profile 分发。
- **证据**:`hermes_cli/main.py:517` · `hermes_cli/profiles.py:473` · `hermes_cli/profiles.py:2246`
  ```
  def _apply_profile_override() -> None:
      """Pre-parse --profile/-p and set HERMES_HOME before imports."""
  ```
- **规模**:profiles.py 2262 行 + profile_distribution.py 782 行 + main.py 预解析段;中高复杂度
- **学习价值**:中 — 「路径常量在 import 时固化」是 Python harness 常见坑,这里的 pre-import argv 扫描 + wrapper 脚本别名化是务实解法;tar 安全解包与 per-profile 服务注册是完整多租户细节。

#### 92. 皮肤引擎(YAML 数据驱动、三表面同步)+ 终端明暗自动检测(OSC 11)

- **解决**:CLI/TUI/桌面 GUI 三个表面的主题若各自硬编码颜色会割裂;且深色皮肤在浅色终端上不可读,而终端背景色没有标准探测 API。
- **实现**:skin_engine.py 把皮肤定义为 ~/.hermes/skins/*.yaml(colors/light_colors/spinner faces·verbs·wings/branding/prompt symbol),缺省字段继承 default 皮肤,gateway 把解析后的调色板推给 TUI 与桌面(tui_gateway resolve_skin/skin.changed),一份 YAML 同时换三个表面。cli.py 侧做明暗自适应:_detect_light_mode() 按 env 覆盖(HERMES_LIGHT)→ HERMES_TUI_THEME → 背景 hex 亮度 → COLORFGBG → _query_osc11_background()(向终端发 OSC 11 查询背景色,100ms 超时,SSH 下禁用以免迟到回包漏进 prompt_toolkit 变成按键,恢复 termios 时用 TCSAFLUSH 冲洗残包)逐级探测;_install_skin_light_mode_hook() 包装 SkinConfig.get_color 在浅色终端下重映射低对比色。
- **证据**:`hermes_cli/skin_engine.py:8` · `cli.py:2576` · `cli.py:2591`
  ```
  This module is the source of truth: it resolves the active skin, and the gateway
  pushes the resolved palette to the TUI and desktop (see tui_gateway's
  ```
- **规模**:skin_engine.py 1068 行 + cli.py 内 ~250 行明暗检测/重映射;中等复杂度
- **学习价值**:中 — OSC 11 探测的工程细节(超时、SSH 禁用、TCSAFLUSH 清残包)是终端程序少见的高质量实现;「主题即数据、一处定义三表面生效」与插件 SDK 同构。

#### 93. 通用插件系统的双通道命令注入(hermes 子命令 + 会话斜杠命令)

- **解决**:第三方插件需要把自己的命令挂进 harness 的两个入口:终端级 `hermes <cmd>`(argparse)与会话级 `/<cmd>`(CLI+gateway 聊天中),且不能与内建命令冲突、不能让每次 `hermes --help` 都付出加载全部插件的 500-650ms 代价。
- **实现**:plugins.py PluginContext 提供 register_cli_command(name, help, setup_fn, handler_fn)(setup_fn 收到 argparse 子解析器自建参数树)与 register_command(name, handler, description, args_hint)(会话斜杠命令,handler 可同步可异步,gateway 两者都处理);后者注册前用 commands.resolve_command() 查重,与内建冲突则警告跳过。main.py 在 _plugin_cli_discovery_needed() 判定(目标是已知内建子命令时跳过插件发现)后,遍历 get_plugin_manager()._cli_commands 动态 add_parser 注入 argparse 树;deferred platform 插件按首个位置参数按需 import(issue #54678)。同一 PluginManager 还承载 register_tool/register_platform/register_context_engine/register_tts_provider 等十余个扩展点与 hook/middleware 总线。
- **证据**:`hermes_cli/plugins.py:584` · `hermes_cli/main.py:11664` · `hermes_cli/plugins.py:563`
  ```
          # Reject if it conflicts with a built-in command
          try:
              from hermes_cli.commands import resolve_command
              if resolve_command(clean) is not None:
  ```
- **规模**:plugins.py 2510 行 + plugins_cmd.py 2082 行 + main.py 注入段;高复杂度(含 manifest 五种 kind、entry-point 扫描、hook/middleware)
- **学习价值**:高 — 展示了 harness 插件命令面的完整闭环:双通道注册、内建冲突防护、惰性发现避免启动税、命令与注册表/补全/gateway 菜单自动打通。

#### 94. 启动延迟工程:stdlib-only fast path + sys.meta_path 延迟补丁 + 惰性 agent 导入  **[◇未见于文档]**

- **解决**:`hermes --version` / 裸交互启动不应支付重 import(openai 类型树 ~166ms/30MB、yaml、argparse 全树、插件);但又必须保证补丁(如 AsyncHttpxClientWrapper.__del__ 置空)在 SDK 首次实例化前生效,且 fast path 副本不与正式逻辑漂移。
- **实现**:hermes_cli/_startup_fast.py 是 main.py 重 import 墙之前唯一允许的轻量模块(仅 os/sys 文件探测),由守卫测试 test_startup_fast_import_weight 在子进程里 import 并断言无重模块混入——docstring 直接记载了历史上 fast 副本漂移导致 Termux --version NameError 的事故(eb4040242)。cli.py 安装 _AsyncHttpxDelNeuter 这个 sys.meta_path finder:拦截 openai._base_client 的首次 import,包装 spec.loader.exec_module 在模块加载完成后把 __del__ 置为 no-op,再自我摘除;省下冷启动 166ms 同时由 import 系统保证 import-then-instantiate 顺序。AIAgent/get_tool_definitions 等在 cli.py 里都是惰性转发函数,首个 prompt 之前不加载 agent/tool 注册表(_prepare_deferred_agent_startup)。
- **证据**:`hermes_cli/_startup_fast.py:3` · `cli.py:851` · `cli.py:901`
  ```
  This module is imported by ``hermes_cli/main.py`` BEFORE its heavy import
  wall (config, argparse tree, logging, providers). Everything here must stay
  **stdlib-only and cheap** (os/sys file probes; no yaml, no hermes_cli.config,
  no argparse). A guard test (``test_startup_fast_import_weight``) subprocess-
  imports this module and fails if any heavy module sneaks into sys.modules.
  ```
- **规模**:_startup_fast.py 222 行 + cli.py/main.py 分散 ~500 行;技巧密度高
- **学习价值**:高 — meta_path finder 做「必须在 SDK import 前生效的补丁」的延迟安装,加上用守卫测试防 fast-path 副本漂移,是 Python CLI 启动优化里罕见的系统化做法。

#### 95. 模块化 setup 向导(section 独立可跑 + quick/blank-slate/portal 一键流 + 非交互守卫)

- **解决**:首次安装要配模型、终端后端、消息平台、工具密钥等大量维度;全量向导对老用户太重,headless/CI 环境跑交互向导会挂死,而新用户需要一条零到可用的最短路径。
- **实现**:setup.py 把向导拆成 SETUP_SECTIONS 七元组(model/tts/terminal/gateway/tools/telemetry/agent),每节是独立函数,`hermes setup <section>` 单独进入并各自 save_config;run_setup_wizard 自动探测新装/已装(existing 走 reconfigure 摘要 + 跳过已配置节)。快速路径:_run_first_time_quick_setup(最少提问)、_run_blank_slate_setup(最小工具集)、--portal 一键 Nous OAuth+选模+Tool Gateway(复用 hermes model 的同一 _model_flow_nous 流程避免手写分叉)。无 TTY 时 print_noninteractive_setup_guidance 直接给出 .env/config 手工路径并退出;进入前自动把现有 config.yaml 备份为时间戳 .bak(#3522),另有 _offer_openclaw_migration 从 openclaw 迁移。交互原语(prompt_choice/prompt_checklist)统一走 curses_ui.py 的 checklist/radiolist(带模糊搜索),无 curses 时退化为编号文本。
- **证据**:`hermes_cli/setup.py:2842` · `hermes_cli/setup.py:2940` · `hermes_cli/setup.py:2984`
  ```
  SETUP_SECTIONS = [
      ("model", "Model & Provider", setup_model_provider),
  ```
- **规模**:setup.py 3645 行 + model_setup_flows.py 3151 行 + tools_config.py 5452 行 + curses_ui.py 997 行;高复杂度
- **学习价值**:中 — onboarding 分层(全量/单节/quick/blank-slate/portal 一键)与「一键流复用既有 flow 而非手写分叉」的取舍值得学;非交互守卫和 config 预备份是必要的防御细节。

#### 96. 自更新管线:语法+跨模块导入双重验证与自动回滚  **[◇未见于文档]**

- **解决**:`hermes update`(git pull / zip 替换)可能落下带冲突标记的文件或半新半旧的树,导致 CLI 自身无法启动(自更新把自己砖了),用户失去修复工具。
- **实现**:update_cmd.py 在更新落盘后跑两级验证:_validate_critical_files_syntax 用 py_compile 逐个编译启动关键文件(pyc 写进临时目录避免污染 __pycache__),_validate_critical_modules_import 在子进程真实 import hermes_cli.main/run_agent/model_tools/toolsets 以捕捉「语法正确但跨模块引用断裂」;失败即自动回滚到更新前 SHA(_capture_head_sha)。zip 路径用 _stage_replacement/_atomic_replace_dir/_commit_staged_replacements 做 staged 原子目录替换;git 路径自动 stash/恢复本地改动、fork 场景自动加 upstream remote 并提示同步;更新中断写 marker 文件供下次启动检测,gateway 场景经 _gateway_prompt 走消息端交互确认。
- **证据**:`hermes_cli/update_cmd.py:123` · `hermes_cli/update_cmd.py:162`
  ```
      These are the files imported on every ``hermes`` startup; if any of them
      has a syntax error (orphan merge-conflict markers, bad ref to a name
  ```
- **规模**:update_cmd.py 5540 行;高复杂度(git/zip 双通道、stash、staged 替换、npm/pip 增量刷新)
- **学习价值**:中 — 自更新工具「不能把自己砖掉」的完整防御模板:parse 与 import 双验证 + 自动回滚 + staged 原子替换 + 中断 marker,对任何自更新 CLI 通用。

#### 97. Dashboard Web 服务器 + PTY-over-WebSocket 终端桥(可重连 keep-alive 会话)  **[▲文档不符]**

- **解决**:浏览器/桌面壳里要嵌入与终端完全一致的 agent 交互(TUI 的 slash 弹窗、审批、皮肤都不重写一遍),且刷新页面不能杀掉正在跑的 agent 进程。
- **实现**:web_server.py 是 17k 行 FastAPI 服务(`hermes dashboard`/`hermes serve`):REST 管 config/env/sessions/jobs,ephemeral session token 认证(WS 升级用 ?token= 查询参数)、Host 头校验、loopback 限定。/api/pty 端点在 PTY 后面 spawn 与 CLI 相同的 `hermes --tui` 二进制,字节流经 WebSocket 送浏览器 xterm.js 渲染,resize 走 \x1b[RESIZE:c;r] 内联转义;POSIX 用 pty_bridge.py(ptyprocess+fcntl/termios,字节安全 I/O),Windows 用 win_pty_bridge.py(pywinpty/ConPTY),两者暴露相同 spawn/read/write/resize/close 接口使 handler 零平台分支。?attach=<token> 时进程注册进 PtySessionRegistry(ttl 30min、16 会话上限、1MB 回放缓冲),断线/刷新后可重连续接。
- **证据**:`hermes_cli/web_server.py:14393` · `hermes_cli/web_server.py:14436` · `hermes_cli/pty_bridge.py:3`
  ```
  # /api/pty — PTY-over-WebSocket bridge for the dashboard "Chat" tab.
  #
  ```
- **规模**:web_server.py 17732 行 + pty_bridge.py 293 + pty_session.py 195 + win_pty_bridge.py 184 + web_routers/;极高复杂度
- **学习价值**:中 — 「浏览器复用同一 TUI 二进制而非重写前端」是嵌入式 agent 终端的省力架构;keep-alive attach registry 解决 Web 端最痛的刷新丢进程问题,细节(回放缓冲、reaper、上限)完整。
- **▲ 文档不符**:文档(cli-commands.md 的 dashboard/serve 条目)只讲到嵌入 Chat 需要 [pty] extra;?attach= keep-alive 会话注册表、1MB 回放缓冲与 30 分钟 TTL 等可重连机制未见任何文档描述。

#### 98. REPL 忙时输入策略(interrupt/queue/steer)与斜杠前缀展开  **[▲文档不符]**

- **解决**:agent 正在跑时用户按 Enter 该发生什么(打断?排队?中途注入?)需要可配置;斜杠命令太多,用户只想敲 /h、/mod 这样的前缀。
- **实现**:HermesCLI 从 display.busy_input_mode 读三态策略:interrupt(重定向当前 run)/queue(排到下一 turn)/steer(经 /steer 在下一次工具调用后注入),/busy 命令运行时切换;与 gateway 侧 CommandDef.busy_policy 是同一问题的 CLI 本地版。未命中精确命令时 process_command 做前缀展开:在内建 COMMANDS+skill commands+bundles 全集上取 startswith 匹配,多命中时先取精确、再取唯一最短(/qui→/quit 而非 /quint-pipeline),仍歧义则列出 "Did you mean",展开后带参重入 process_command 并防同 token 无限递归。
- **证据**:`cli.py:4285` · `cli.py:10493` · `cli.py:10506`
  ```
          # busy_input_mode: "interrupt" (Enter redirects current run),
          # "queue" (Enter queues for next turn), or "steer" (Enter injects
  ```
- **规模**:cli.py 内分散 ~400 行(process_command 尾部 + 输入回调);中等复杂度
- **学习价值**:中 — 「忙时 Enter 语义三态化」是交互式 agent 的关键 UX 决策点;前缀解析的 exact→unique-shortest→ambiguous 阶梯与补全集合保持一致的做法可复用。
- **▲ 文档不符**:website/docs/reference/slash-commands.md:214 称歧义前缀时 "the first match in registry order wins";实际代码(cli.py:10500-10528)是先精确、再唯一最短匹配,仍歧义则拒绝执行并打印 "Ambiguous command … Did you mean",不存在按注册表顺序取首个的逻辑。

**本子系统文档-代码冲突(2 条):**

- 宣称:website/docs/reference/slash-commands.md:214:"When a prefix is ambiguous (matches multiple commands), the first match in registry order wins."
  实际:cli.py 的前缀解析在歧义时先找精确匹配、再找唯一最短匹配(/qui→/quit),两者都不唯一时不执行任何命令,而是打印 "Ambiguous command: … Did you mean: …";全仓库(cli.py、gateway/run.py、commands.py)均无"按注册表顺序取第一个匹配"的实现。(证据:`cli.py:10506`)
- 宣称:hermes_cli/pty_bridge.py 模块 docstring(:11-16)称 PTY 桥 "POSIX-only","Native Windows ConPTY … that's tracked as a future enhancement",Windows 上 dashboard /chat 只显示推荐 WSL 的横幅。
  实际:web_server.py 已经落地了 Windows 分支:sys.platform 为 win 时 import hermes_cli/win_pty_bridge.py 的 WinPtyBridge(pywinpty/ConPTY,184 行,与 PtyBridge 同接口),"future enhancement" 实际已实现,pty_bridge.py 自身的模块文档滞后。(证据:`hermes_cli/web_server.py:14412`)

### 2.9 消息网关(gateway/ + gateway/platforms/ + plugins/platforms/,多平台单进程 messaging gateway)

gateway/ 是 hermes-agent 的常驻消息网关:单个 asyncio 进程同时连接 30+ 个消息平台(gateway/platforms/ 内置 9 个直连适配器 + relay 通用连接器 + plugins/platforms/ 22 个插件适配器,经 platform_registry 惰性加载),把各平台事件归一为 MessageEvent,按 build_session_key 确定性路由到会话并驱动 AIAgent 回合。围绕这条主链,它实现了消息型 harness 的一整套生存性机制:双层 busy 守卫(adapter _active_sessions/_pending_messages + runner busy_input_mode 的 interrupt/steer/redirect/queue 谱系,含子代理/压缩自动降级与 /approve、clarify 旁路)、按 resolved session_id 的回合租约防转写交错、GatewayStreamConsumer 把同步 token 流限速编辑/Telegram draft 流式投到平台、delivery ledger 用 state.db 四态检查点保证最终回复 crash 后诚实 at-least-once 重投、DM 配对(盐化哈希码 + owner CLI 批准)与多层 default-deny 授权联合、scale-to-zero 闲置休眠、指数退避重连 + 重启环路断路器 + resume-pending 恢复、关机 flush/取证/看门狗,以及 multiplex_profiles 单进程多租户(per-profile HERMES_HOME/secret scope/凭据冲突仲裁)与 profile_routes 按频道路由人格。文档(website/docs/developer-guide/gateway-internals.md)对主架构有覆盖,但守卫语义、配对方向、会话键示例均已过时,turn lease、delivery ledger 恢复细节、scale-to-zero 网关层、关机保全体系基本只存在于代码与源内注释。

关键文件(38 个,行数实测,余见 JSON):`gateway/run.py`(27146), `gateway/platforms/base.py`(6861), `gateway/session.py`(3490), `gateway/config.py`(2688), `gateway/stream_consumer.py`(2410), `gateway/slash_commands.py`(5693), `gateway/authz_mixin.py`(888), `gateway/pairing.py`(905)


#### 99. 单进程多平台适配器总线(~30+ 平台,注册表 + 惰性加载 + 动态枚举)  **[▲文档不符]**

- **解决**:一个 agent 需要同时驻留在 Telegram/Discord/Slack/WhatsApp/Signal/飞书/企微/QQ/iMessage 等几十个消息平台上,但不能为每个平台起一个进程,也不能让每次 `hermes chat` 启动都 import 几十个重型平台 SDK。
- **实现**:GatewayRunner.start() 在单个 asyncio 事件循环里遍历 config.platforms,逐个 _create_adapter 并统一挂上 message_handler/fatal_error_handler/busy_session_handler/authorization_check;适配器统一继承 gateway/platforms/base.py 的 BasePlatformAdapter。平台来源三层:gateway/platforms/ 内置 9 个直连适配器(signal、weixin、bluebubbles、qqbot、yuanbao、whatsapp_cloud、msgraph_webhook、webhook、api_server)+ gateway/relay/ 通用 relay 适配器 + plugins/platforms/ 下 22 个插件平台(telegram、discord、slack、matrix、feishu、wecom、teams、line、irc、ntfy、photon、a2a 等)。插件平台经 platform_registry 注册,且注册的是 register_deferred 惰性 loader——真正 import SDK 推迟到 gateway 启动/发送时;Platform 枚举用 _missing_ 为插件平台动态造 pseudo-member,保证 Platform("irc") is Platform("irc")。连接失败的平台进入 _failed_platforms 由 reconnect watcher 兜底。
- **证据**:`gateway/run.py:11051-11054` · `gateway/platform_registry.py:187` · `gateway/run.py:11093-11096`
  ```
          for platform, platform_config in self.config.platforms.items():
              if await self._abort_startup_if_shutdown_requested():
                  return True
              if not platform_config.enabled:
                  continue
  ```
- **规模**:gateway/run.py 27146 行 + base.py 6861 行 + platform_registry.py 332 行 + 22 个插件适配器(telegram 10147 行、discord 10138 行、slack 9088 行……),总量超 10 万行;复杂度极高
- **学习价值**:高 — 这是把一个 agent loop 挂到任意多个消息前端的标准范式:统一 MessageEvent 抽象 + 基类适配器 + 注册表/惰性加载,值得任何多前端 harness 借鉴;惰性 loader 解决的『CLI 启动被平台 SDK 拖慢数秒』是真实工程痛点。
- **▲ 文档不符**:website/docs/developer-guide/gateway-internals.md:9 说 "20+ external messaging platforms";实测 plugins/platforms/ 22 个 + gateway/platforms/ 9 个内置 + relay + wecom_callback,逻辑平台超 30 个,文档口径偏小(用户文档 messaging/index.md 的能力矩阵列了 28 个聊天平台,未含 api_server/webhook/relay)。

#### 100. 确定性会话键与多档案命名空间路由  **[▲文档不符]**

- **解决**:同一条消息必须稳定地映射到唯一会话(DM 按人隔离、群按 chat/人隔离、线程共享),否则会出现跨用户历史串线;多 profile 复用同一进程时还不能让两个 profile 的同平台会话相撞。
- **实现**:gateway/session.py 的 build_session_key() 是会话键唯一事实来源:格式 agent:<ns>:<platform>:<chat_type>:...,DM 附 chat_id/参与者 id/thread_id,群聊按 group_sessions_per_user 附 user_id,thread 默认全员共享;Slack 额外插 workspace scope_id,WhatsApp 做 JID/LID canonical 化防止别名翻转裂成两个会话,Discord 用 prospective_thread_id 把『频道首条消息』与其自动线程后续消息并成同一会话。_session_key_namespace() 把 profile 塞进历史上恒为 "main" 的槽位:default→agent:main 字节级兼容旧键,命名 profile→agent:<profile>,positional parser 不变。adapter 侧(base.py handle_message)与 runner 侧(_session_key_for_source)各自调它,保证两层守卫 key 一致。
- **证据**:`gateway/session.py:1053-1055` · `gateway/session.py:1058-1063` · `gateway/session.py:1156-1159`
  ```
      if not profile or profile == "default":
          return "agent:main"
      return f"agent:{profile}"
  ```
- **规模**:session.py 3490 行(键构造约 120 行,其余为 SessionStore 持久化/恢复);概念密度高
- **学习价值**:高 — 『路由键 = 平台×会话形态×隔离策略』的组合学是所有消息型 harness 的地基;把 profile 塞进兼容槽位而非改 schema 的做法,是零迁移多租户化的教科书案例。
- **▲ 文档不符**:gateway-internals.md:78 给的示例键是 `agent:main:telegram:private:123456789`,但代码里 chat_type 是 "dm"(session.py:1103 `if source.chat_type == "dm":`),从不产生 "private" 槽;multiplex 下的 agent:<profile> 命名空间也未在该文档提及。

#### 101. 双重消息守卫 + busy 策略(steer/redirect/queue/interrupt 与自动降级)  **[▲文档不符]**

- **解决**:agent 跑长任务时用户还在继续发消息:既不能丢、不能乱序、不能把控制命令(/stop、/approve)当聊天文本吞掉,也不能让一句闲聊把跑了几分钟的子代理任务全部打断。
- **实现**:第一层守卫在 BasePlatformAdapter.handle_message:_active_sessions 持 per-key guard,活跃时新消息进 _pending_messages 合并/去抖(照片连拍合并、文本 debounce),但 /stop、/approve、/deny 等 bypass 命令与 clarify 回答走 inline 直达 runner(否则死锁);第二层在 GatewayRunner._handle_active_session_busy_message:先做鉴权与 draining 检查,再把裸词 "yes/no" 路由到审批 handler,然后按 busy_input_mode 分派——steer 用 running_agent.steer() 中途注入、interrupt 优先尝试 running_agent.redirect(),不行才真 interrupt;当 agent 有活跃子代理(#30170)或压缩进行中(#56391)时把 interrupt 自动降级为 queue。落队消息走 _queue_or_replace_pending_event FIFO,每条文本保持独立回合边界(#43066)。
- **证据**:`gateway/platforms/base.py:5736-5741` · `gateway/run.py:8905-8908` · `gateway/platforms/base.py:5610-5616`
  ```
                  logger.debug(
                      "[%s] New message while session %s is active — queuing follow-up "
                      "(no interrupt, will cascade after current turn)",
                      self.name,
                      session_key,
  ```
- **规模**:base.py handle_message + busy 分支约 1200 行,run.py 侧 busy handler 约 450 行;是网关最精细的状态机
- **学习价值**:高 — 这是『运行中 agent 如何接续收消息』问题的最完整实现:双层守卫 + 命令旁路 + steer/redirect/queue 谱系 + 子代理保护降级,几乎每个分支都对应一个真实事故编号,可直接当消息型 harness 的需求清单。
- **▲ 文档不符**:gateway-internals.md:86 称第一层守卫『queues the message in _pending_messages and sets an interrupt event』、:88 称第二层『Everything else triggers running_agent.interrupt()』;代码里默认是排队不打断(base.py:5736-5748),interrupt 只是 busy_input_mode 的一种,还有 steer/redirect,且子代理/压缩期间会强制降级为 queue——文档描述的是早期行为。

#### 102. 流式输出桥 GatewayStreamConsumer(sync delta → 限速编辑/原生 draft)

- **解决**:LLM 的 token 流来自 agent 工作线程(同步回调),而消息平台没有 token 流概念,只能反复 editMessageText 或用 Telegram sendMessageDraft;还要处理平台限长、flood control、思维链标签过滤、截断代码栅栏。
- **实现**:GatewayStreamConsumer.on_delta() 线程安全入 queue.Queue,异步 run() 任务批量 drain 后按 edit_interval/buffer_threshold 限速编辑同一条消息;传输可选 edit/draft(_resolve_draft_streaming,Telegram DM 用递增 draft_id 动画,最终答案落一条真消息)、fresh_final_after_seconds 让长回合的最终回复另发新消息校正时间戳;_filter_and_accumulate 剥 <think> 系标签,ensure_closed_code_fences 修补被截断的 ``` 栅栏,_is_partial_silence_marker 阻止 NO_REPLY 这类静默标记闪现,flood control 连续 3 次失败后永久停编辑,_FLUSH 屏障让 clarify 交互提示不被缓冲文本超车。run.py TurnRunner 把 consumer.on_delta 装为 agent 的 stream_delta_callback,并 tee 给 streaming-TTS 消费者。
- **证据**:`gateway/stream_consumer.py:786-789` · `gateway/stream_consumer.py:863-872` · `gateway/run.py:4526-4528`
  ```
          self._use_draft_streaming = self._resolve_draft_streaming()
          if self._use_draft_streaming:
              type(self)._draft_id_counter += 1
              self._draft_id = type(self)._draft_id_counter
  ```
- **规模**:stream_consumer.py 2410 行 + stream_dispatch.py 132 + stream_events.py 171 + streaming_tts_consumer.py 423;中高复杂度
- **学习价值**:高 — 『token 流→消息平台』的阻抗匹配是消息型 agent 的核心工程题,这里给出限速编辑、draft 传输、UTF-16 长度函数、栅栏修复、静默抑制、flush 屏障等一整套可复用手法。

#### 103. 投递义务台账(delivery ledger:crash 后最终回复不丢、诚实 at-least-once)

- **解决**:回合已烧完 token、最终回复只存在于 Python 局部变量里,gateway 在 finalize 与平台 ACK 之间崩溃/重启就会无痕丢失这条回复(#58818 等)。
- **实现**:base.py 在发送最终文本前把 (session_key, message_ref, content) 哈希成 obligation_id,依次写 state.db 三个检查点 record_obligation(pending)→mark_attempting→mark_delivered/mark_failed,全部 best-effort 不阻塞真实发送;启动时 run.py:_redeliver_pending_obligations 先于 resume 扫描,sweep_recoverable() 用 owner_pid+进程启动时间判活、原子改 owner 防止双 gateway 重复认领,只认领本次 boot 已连接平台的行以免白烧 attempts;pending 行直接重发,attempting/failed 行(可能已送达)带可见 "♻️ Recovered reply" 前缀,attempts 上限 3 + 24h stale 转 abandoned 防毒行;重投后 clear_resume_pending 防止 resume 路径再花钱重跑同一回合。
- **证据**:`gateway/delivery_ledger.py:68-71` · `gateway/platforms/base.py:6087` · `gateway/run.py:10374-10379`
  ```
  RECOVERED_MARKER = (
      "♻️ Recovered reply — the gateway restarted during delivery, "
      "so this may be a duplicate:\n\n"
  )
  ```
- **规模**:delivery_ledger.py 374 行 + base.py 记账段约 70 行 + run.py 重投约 105 行;中等复杂度、契约设计极精
- **学习价值**:高 — 把『发出的最终回复』当成分布式义务来记账,pending/attempting 语义区分 + 可见重复标记的 honest at-least-once 契约,是 LLM 场景下 exactly-once 不可得时的最佳工程答案(前一版 outbox 因静默重发被否决,#61790)。

#### 104. 回合租约 SessionTurnLeaseRegistry(按 resolved session_id 串行化转写)  **[◇未见于文档]**

- **解决**:busy 守卫都按路由键(routing key)加锁,但 /resume、Telegram topic tip-walk、异步委托 pinning 会让多个路由键映射到同一个 session_id——两个回合在两份 agent 对象上并发写同一转写,产生永久 user;user 交替楔子(#64934)。
- **实现**:在会话解析定案之后、加载转写之前,按 resolved session_id 申请 asyncio 租约(run.py:16584),路由键守卫保证同键消息到不了这里,所以只有别名键路由才会真正竞争;超时 fail-open 返回 degraded token(宁可退回旧的不串行行为也不楔死会话);token 记 (owner_key, generation),release 做身份校验保证陈旧 unwind 不会释放新回合的租约;压缩中途轮换 session_id 时 rebind() 把同一把锁登记到新 id 下,关闭 rotation-alias 窗口;注册表上限 512、只驱逐 idle 项。
- **证据**:`gateway/run.py:16584-16589` · `gateway/turn_lease.py:190-192` · `gateway/turn_lease.py:29-33`
  ```
              _lease_token = await _lease_registry.acquire(
                  session_entry.session_id,
                  owner_key=_quick_key,
                  generation=run_generation,
                  timeout=_float_env("HERMES_AGENT_TIMEOUT", 1800),
  ```
- **规模**:turn_lease.py 302 行 + run.py 挂接/释放/rebind 约 120 行;小而精
- **学习价值**:高 — 教科书级的并发课:锁的粒度必须跟『被保护资源的身份』(session_id)对齐而非跟路由键对齐;fail-open + generation 校验 + mid-flight rebind 三件套对任何有 alias 路由的 harness 都适用。

#### 105. DM 配对安全(盐化哈希配对码 + 限速/锁定 + allowlist 镜像)  **[▲文档不符]**

- **解决**:静态 user-id allowlist 运维成本高,但开放 DM 又会被陌生人白嫖;需要一个陌生人可自助发起、只有 owner 能批准、且防爆破防骚扰的授权握手。
- **实现**:陌生用户 DM 时(unauthorized_dm_behavior="pair",默认 pairing)runner 用 PairingStore.generate_code 发一个 8 位无歧义字母表配对码给该用户,提示其转给 owner 执行 `hermes pairing approve <platform> <code>`;码只存盐化 SHA-256(pending 文件泄露也不暴露码),1 小时过期、每用户 10 分钟 1 次限速、每平台最多 3 个 pending、5 次失败批准触发 1 小时锁定,文件 0600。批准后若运营者已配置该平台 allowlist env,则把用户镜像写进 allowlist 保持单一可见事实源;未配置 allowlist 的开放网关不会因首次配对被悄悄锁死(option i)。multiplex 下每 profile 一个 PairingStore,授权检查按 source.profile 路由到对应白名单;WhatsApp 做 JID 别名展开匹配。
- **证据**:`gateway/pairing.py:641-645` · `gateway/run.py:14496-14499` · `gateway/pairing.py:186-189`
  ```
              code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
  
  ```
- **规模**:pairing.py 905 行 + run.py 接入约 70 行;中等复杂度,安全设计对标 OWASP/NIST SP 800-63-4
- **学习价值**:中 — 自助码 + owner 带外批准的授权握手可直接移植到任何 bot;『grant 镜像进运营者自己的 allowlist、开放网关不因配对被锁死』体现了对配置事实源漂移的深思。
- **▲ 文档不符**:gateway-internals.md:104-108 描述为『Admin: /pair → Gateway 给 admin 一个码 → 新用户回码即配对』;代码里不存在 /pair 命令,方向相反:陌生用户 DM 自动收到码(run.py:14479-14500),owner 在 CLI 上 `hermes pairing approve` 批准。用户文档 messaging/index.md:344-358 与代码一致,开发者文档写反了。

#### 106. 多层授权联合与 upstream 委托(含 busy 路径同等鉴权)  **[▲文档不符]**

- **解决**:几十个平台各有身份/allowlist 形态(env、config.yaml、群级、bot 消息、无 user_id 的频道广播、relay 上游已鉴权流量),必须统一成一个 default-deny 的联合判定,且忙碌路径不能有比冷路径更松的洞。
- **实现**:GatewayAuthorizationMixin._is_user_authorized 按序检查:HOMEASSISTANT/WEBHOOK 由连接/HMAC 自身鉴权直接放行;delivered_via_upstream_relay is True(显式 bool 身份检查,防 MagicMock 真值失守)或适配器声明 authorization_is_upstream 时委托给已认证上游;群/论坛/频道级 chat allowlist(TELEGRAM_GROUP_ALLOWED_CHATS 等)在 no-user-id 守卫之前跑;{PLATFORM}_ALLOW_BOTS 放行 bot 流量;然后 per-platform allow-all → env/config allowlist → pairing 批准表 → GATEWAY_ALLOW_ALL_USERS → 默认拒绝。multiplex 下 _platform_gate_env 走 profile secret scope,scope 里没有的键返回 default 而不是回落进程 env,防止 profile A 的 allowlist 泄进 profile B(#72348)。busy 路径 _handle_active_session_busy_message 第一行复刻同样检查,堵住『共享线程里未授权用户向活跃会话注入消息』(#17775)。
- **证据**:`gateway/authz_mixin.py:435-439` · `gateway/run.py:8748-8750` · `gateway/authz_mixin.py:64-69`
  ```
          if source.delivered_via_upstream_relay is True or self._adapter_authorization_is_upstream(
              source.platform,
              profile=adapter_profile,
          ):
              return True
  ```
- **规模**:authz_mixin.py 888 行 + pairing 联动;分支多、每个例外都有事故号
- **学习价值**:高 — 展示了真实世界 default-deny 授权的全部毛边:匿名管理员、bot 消息、上游已鉴权 relay、多 profile secret 隔离、热/冷路径一致性——是给 agent 加多平台门禁时的完整 checklist。
- **▲ 文档不符**:gateway-internals.md:94-100 只列了 5 层(allow-all/allowlist/pairing/global/deny);代码里还有 relay upstream 委托、群级 chat allowlist、ALLOW_BOTS、HA/Webhook 免检等文档未列的层级。

#### 107. Scale-to-zero 闲置休眠(relay dormant + 平台级 suspend)  **[◇未见于文档、▲文档不符]**

- **解决**:托管在 Fly 这类按运行计费的平台时,空闲 gateway 也占一台常驻机器;要能在无回合、无入站、无后台工作时把流量降到零让平台挂起机器,又不能丢消息、不能误伤直连平台的长连接。
- **实现**:纯函数层 scale_to_zero.py 定义三重武装条件(HERMES_SCALE_TO_ZERO Labs env 戳 + 消息面仅 relay 或无平台 + 已注册 wakeUrl)与 idle 谓词(无 running agent + 超时无入站 + 无活跃后台工作:bg delegate/kanban/bg terminal/cron/API run);run.py:_scale_to_zero_watcher 每 30s 检查,满足即标记 runtime status=draining 并调 relay adapter.go_dormant()——只关 socket、保留 reconnect supervisor,绝不走 disconnect()/stop 排水路径,进程保活由 Fly autostop:"suspend" 冻结、wakeUrl poke 自动唤醒后 supervisor 重拨、connector 回放缓冲积压;唤醒后设 cooldown 防止刚 drain 完积压又立刻再休眠。
- **证据**:`gateway/scale_to_zero.py:104` · `gateway/run.py:7638-7643` · `gateway/scale_to_zero.py:120-124`
  ```
      return bool(enabled) and bool(relay_only_or_absent) and bool(wake_url)
  ```
- **规模**:scale_to_zero.py 124 行(纯函数)+ run.py watcher/前提检查约 250 行;小体量高设计密度
- **学习价值**:中 — 『行为层消费传输层原语』的分层范式(gateway 决策 idle,relay 提供 buffered-flip/go_dormant,平台负责真正 suspend)以及把每个决策编号写进 docstring 的做法值得学习;serverless 化 agent 的关键路径。
- **▲ 文档不符**:官方文档只在 Chronos 托管 cron 语境提到 scale-to-zero(cron-internals.md:132),gateway 侧的 HERMES_SCALE_TO_ZERO 开关、idle 谓词与 go_dormant 休眠序列在 README/AGENTS.md/website docs 均无记载。

#### 108. 断线重连与重启体系(指数退避 + 重启环路断路器 + resume-pending)  **[◇未见于文档]**

- **解决**:平台 socket 掉线、进程被 SIGTERM、agent 自己把 gateway 重启进死循环——这三类中断都要自愈,且重启后被打断的会话要接着跑而不是丢失。
- **实现**:_platform_reconnect_watcher 对 _failed_platforms 30s→300s 封顶指数退避无限重试(可重试错误永不放弃、坏凭据立即出队;自动熔断已被移除,因为它曾让 DNS 抖动后的 bot 静默死亡),重连时 is_reconnect=True 保留平台侧离线消息队列(#46621);重启路径分层:/restart 或 SIGUSR1 先等活跃回合(after_turn_timeout)再 stop() 内排水(drain_timeout),supervisor 场景用 exit 75(EX_TEMPFAIL)请求服务管理器重启、exit 78 表致命配置错误停止重启;restart_loop_guard 把『带 restart-interrupted 会话的 boot』时间戳持久化到 restart_loop.json,60s 内 ≥3 次即跳过 auto-resume 打断 SIGTERM respawn 死循环(#30719 defense-3);启动时 _redeliver_pending_obligations → _schedule_resume_pending_sessions 恢复被打断会话,resume 又受 freshness window 与 stale redelivery 检查约束。
- **证据**:`gateway/run.py:12479-12481` · `gateway/restart_loop_guard.py:136-137` · `gateway/restart.py:10`
  ```
                      success = await self._connect_adapter_with_timeout(
                          adapter, platform, is_reconnect=True
                      )
  ```
- **规模**:reconnect watcher ~210 行 + restart 路径(run.py 9698-10330 一带)~600 行 + restart.py 120 + restart_loop_guard.py 150;高复杂度
- **学习价值**:高 — 自治 agent 最危险的故障模式是『它有能力重启自己』;这里的三层防御 + 持久化 boot 窗口断路器 + sysexits 与 supervisor 的约定,是长时运行 harness 生存性设计的范本。

#### 109. 关机数据保全(pending flush + 转写抢救 + 关机取证/看门狗)  **[◇未见于文档]**

- **解决**:关机瞬间,内存里的 _pending_messages 和 agent 未落库的 _session_messages 是仅存副本,FTS5 损坏或 clear() 会造成永久用户数据丢失;此外还要能事后解释『谁杀了 gateway』和『关机为何卡死』。
- **实现**:shutdown_flush.py 三个钩子:flush_pending_to_file 在 clear() 之前把非空 pending 槽原子写入 <hermes_home>/pending_messages/(0600 + 目录 fsync);recover_pending_to_db 启动后经 SessionDB.append_message 回灌(FTS/元数据走正路)并删除 flush 文件;flush_agent_history_to_file 在 _flush_messages_to_session_db 抛错时兜底转储活体转写(#72680)。shutdown_forensics.py 在收到信号时快照 /proc 里 parent/兄弟进程线索定位杀手并可 spawn 异步诊断,check_systemd_timing_alignment 检查 drain 超时与 TimeoutStopSec 的错位;shutdown_watchdog.py 用独立线程定时器在事件循环卡死时转储所有线程栈,loop_heartbeat 心跳文件供跨进程判活。
- **证据**:`gateway/shutdown_flush.py:10-12` · `gateway/shutdown_flush.py:82-86` · `gateway/shutdown_forensics.py:104`
  ```
  1. ``flush_pending_to_file()`` — called BEFORE ``_pending_messages.clear()``
     during shutdown.  Serialises any non-empty pending slots to a JSON file
  ```
- **规模**:shutdown_flush.py 321 + shutdown_forensics.py 462 + shutdown_watchdog.py 457,合计约 1240 行;中等复杂度
- **学习价值**:中 — 『关机路径是数据丢失高发区』的系统性回答:先落盘再 clear、启动回灌、取证快照、卡死看门狗四件套,适合任何持久会话 harness 抄作业。

#### 110. 多 profile 复用 multiplex + profile 路由(单进程多租户)

- **解决**:一台机器上跑多个人格/配置(不同模型、技能、记忆、凭据)的 agent,如果各起一个 gateway 会浪费资源且 bot token 冲突;还要能把同一 Discord 服务器的不同频道路由到不同 profile。
- **实现**:gateway.multiplex_profiles 开启后,_start_secondary_profile_adapters 在同一进程为每个非活跃 profile 在其自己的 HERMES_HOME + secret scope(_profile_runtime_scope)下创建并连接适配器,存入 _profile_adapters[profile],message handler 先 stamp source.profile 再进共享 _handle_message,使该回合解析到对应 profile 的配置/技能/凭据;这是唯一同时看到所有 profile 凭据的点,故在此做凭据指纹与监听端口的冲突检测(两个 profile 轮询同一 bot token 直接拒绝);默认 profile 上没有 token 的平台被跳过而不是进死循环重连(#64674);每 profile 一个 PairingStore。另一维度 profile_routing.py 按 platform+guild/chat/thread 的 specificity(2/4/8 加权)最specific-first 匹配 profile_routes,Discord 线程经 parent_chat_id 继承频道路由。
- **证据**:`gateway/run.py:13195-13196` · `gateway/run.py:11063` · `gateway/profile_routing.py:96-98`
  ```
          if not getattr(self.config, "multiplex_profiles", False):
              return 0
  ```
- **规模**:run.py multiplex 段约 450 行 + profile_routing.py 166 + authz/pairing/session key 的 profile 分支散布全网关;高复杂度横切关注点
- **学习价值**:高 — 单进程多租户的完整横切改造:命名空间化会话键、per-profile secret scope、凭据冲突仲裁、per-profile 白名单——展示了在成熟单租户系统上做多租户化时每一层都要动的位置。

#### 111. 后台完成事件唤醒(wake:push 注入 vs API self-POST 双策略)  **[◇未见于文档]**

- **解决**:后台任务(delegate_task background、bg terminal)完成时要把结果注入原会话继续对话;push 型平台可以造合成消息,但无状态的 API server 会话若走常规路径会落进一个键不匹配的平行会话,结果永远不可见。
- **实现**:wake.py 按 adapter.supports_async_delivery 分流:push 型平台构造 MessageEvent(internal=True) 走 adapter.handle_message 原路注入(internal 事件在 busy 时静默排队、绝不打断当前回合);API server 型改为向本机 /v1/chat/completions 自 POST,带原始 X-Hermes-Session-Id 头走真实入口恢复真会话,403 缺 API key 时宁可 raise 也不落进无人查看的指纹会话;瞬时错误(429 并发帽、连接错)按 2/5/10s 退避重试,失败上抛让调用方回卷游标重试而不是默默丢事件。
- **证据**:`gateway/wake.py:80-86` · `gateway/wake.py:116-121` · `gateway/run.py:8878-8879`
  ```
          synth_event = MessageEvent(
              text=text,
  ```
- **规模**:wake.py 184 行 + run.py 各 watcher(_async_delegation_watcher/_run_process_watcher/completion 分类投递)约 600 行;中等复杂度
- **学习价值**:中 — 『后台完成如何回到对话』是 agent harness 常见盲区;这里的 push/自 POST 双策略、internal 事件不打断不致谢的语义、失败上抛回卷游标,构成一套完整的事件重入契约。

**本子系统文档-代码冲突(4 条):**

- 宣称:website/docs/developer-guide/gateway-internals.md:86-88:第一层守卫『queues the message in `_pending_messages` and sets an interrupt event』,第二层『Everything else triggers `running_agent.interrupt()`』
  实际:base adapter 默认排队且明确不打断(日志原文 "no interrupt, will cascade after current turn");是否打断由 runner 的 busy_input_mode(interrupt/steer/queue)决定,interrupt 模式还优先尝试 redirect(),且在有活跃子代理(#30170)或压缩进行中(#56391)时自动降级为 queue(证据:`gateway/platforms/base.py:5736`)
- 宣称:website/docs/developer-guide/gateway-internals.md:104-108:DM 配对流程为『Admin: /pair → Gateway 发码给 admin → 新用户回码 ABC123 → Paired!』
  实际:不存在 /pair 命令且方向相反:未授权用户 DM 时 gateway 自动 generate_code 把码发给该用户,并提示『Ask the bot owner to run: hermes pairing approve <platform> <code>』——由 owner 在 CLI 带外批准(用户文档 messaging/index.md:344-358 的描述才与代码一致)(证据:`gateway/run.py:14496`)
- 宣称:website/docs/developer-guide/gateway-internals.md:78:会话键示例 `agent:main:telegram:private:123456789`
  实际:键的 chat_type 槽取自 source.chat_type,DM 分支判定条件是 `if source.chat_type == "dm":`,生成 `agent:main:telegram:dm:<chat_id>`,从不产生 "private";且 multiplex 下命名空间可为 agent:<profile>,文档未提(证据:`gateway/session.py:1103`)
- 宣称:website/docs/developer-guide/gateway-internals.md:9:『connects Hermes to 20+ external messaging platforms』;README.md:25 只列『Telegram, Discord, Slack, WhatsApp, Signal, and CLI』
  实际:实测 plugins/platforms/ 有 22 个插件平台目录(全部 kind: platform),gateway/platforms/ 另有 9 个内置适配器(signal、weixin、bluebubbles、qqbot、yuanbao、whatsapp_cloud、msgraph_webhook、webhook、api_server)加 gateway/relay/ 通用 relay 与 wecom_callback,逻辑平台总数 30+(证据:`gateway/config.py:272`)

### 2.10 委派与多智能体(delegation & multi-agent)

该子系统提供 Hermes 的四条多智能体路径:(1) delegate_task 同进程子代理——在主线程构建隔离的子 AIAgent(全新对话、独立终端会话/task_id、工具集交集+黑名单、skip_context_files/skip_memory),leaf/orchestrator 角色控制再委派能力并受 max_spawn_depth(默认 1=扁平)与全局 kill switch 约束;顶层模型调用一律后台执行,批量作为单个异步单元 join 后经持久化完成队列(state.db + claim/ack 投递协议)以全新回合回注对话,配套双层无进度停滞检测(同步心跳 staleness + 异步 stale monitor)取代墙钟超时、摘要按父上下文余量预算截断并溢写落盘、可 tail 的强制脱敏实时转录。(2) Kanban 看板——以 SQLite(kanban.db)为唯一协调内核的跨进程多 worker 队列:gateway 内嵌 dispatcher 每 tick 在板级单写锁下做 TTL/心跳/PID 三重回收、依赖促升与 CAS claim,再以 env 注入方式 spawn 全进程 worker(hermes -p <profile> chat -q),worker 经 kanban_* 工具收尾,harness 层有 stop-nudge、goal judge 完成门、自动心跳与运行中评论 steer 注入;delegation_context 的 ContextVar 标记防止同进程子代理/cron 冒充 dispatcher 属主。(3) research 场景批量轨迹生成——batch_runner(多进程+checkpoint+工具集概率采样+每样本容器镜像)与 mini_swe_runner(单 terminal 工具+哨兵完成)。(4) MoA——虚拟 provider 形式的 mixture-of-agents:参考模型并行 fan-out 后由聚合器作为 acting model 走正常代理循环,advisory view 把工具转录扁平化为纯文本以兼容严格 provider。另有面向插件的 SubagentLifecycleService 公共生命周期 API。AGENTS.md 的委派一节明显滞后于代码(background 语义、toolsets 参数、max_spawn_depth 默认值均与实现不符),而 website 用户文档基本准确。

关键文件(24 个,行数实测,余见 JSON):`tools/delegate_tool.py`(3931), `tools/async_delegation.py`(1515), `agent/subagent_lifecycle.py`(540), `agent/delegation_context.py`(161), `tools/delegation_live_log.py`(424), `agent/kanban_stop.py`(108), `hermes_cli/kanban_db.py`(10275), `hermes_cli/kanban.py`(3236)


#### 112. 同进程子代理构建与隔离(delegate_task)  **[▲文档不符]**

- **解决**:父代理需要把重推理/高噪音子任务外包出去,同时防止子任务的中间工具调用和推理污染父上下文,并防止子代理获得父代理没有的能力或触发用户交互/共享状态副作用。
- **实现**:delegate_task 在主线程用 _build_child_agent 构建全新 AIAgent:全新对话(无父历史)、独立 task_id/终端会话、skip_context_files/skip_memory、ephemeral_system_prompt 由 goal+context+workspace hint 拼装。工具集三层治理:显式请求时与父工具集做交集(_expand_parent_toolsets 先展开复合工具集)、_strip_blocked_tools 剥离纯黑名单工具集、DELEGATE_BLOCKED_TOOLS(delegate_task/clarify/memory/send_message/cronjob)经 disabled_toolsets 在复合工具集展开后逐工具减除。子代理线程内安装非交互审批回调(默认 auto-deny)避免 input() 死锁父 TUI。凭据/模型/推理配置继承父代理,也可被 delegation.provider 配置整体重定向到便宜模型。
- **证据**:`tools/delegate_tool.py:48` · `tools/delegate_tool.py:1281` · `tools/delegate_tool.py:1527` · `tools/delegate_tool.py:76`
  ```
  DELEGATE_BLOCKED_TOOLS = frozenset(
      [
          "delegate_task",  # no recursive delegation
          "clarify",  # no user interaction
          "memory",  # no writes to shared MEMORY.md
  ```
- **规模**:delegate_tool.py 共 3931 行,其中构建/隔离路径(_build_child_agent、toolset 治理、审批回调)约 900 行,复杂度高(凭据继承、api_mode 重推导、MCP 工具集保留等大量边界分支)。
- **学习价值**:高 — 这是 harness 子代理隔离的教科书实现:工具集交集+黑名单双层防越权、上下文/记忆隔离、线程内审批回调防死锁,每个设计都对应真实事故编号,可直接迁移到任何多代理框架。
- **▲ 文档不符**:AGENTS.md:993 称单任务可传可选 toolsets 参数,但模型侧 schema(DELEGATE_TASK_SCHEMA)根本没有 toolsets 字段,代码注释明确 'the model cannot choose or narrow them (no model-facing toolsets arg)'(tools/delegate_tool.py:2966-2968);website 用户文档(delegation.md:158)则是对的。

#### 113. leaf/orchestrator 角色与 spawn 深度治理  **[▲文档不符]**

- **解决**:嵌套委派会指数级放大 API 开销并可能形成失控代理树,需要按角色精确授予再委派能力,并有全局熔断与深度上限。
- **实现**:角色只有 leaf(默认,不能再委派)与 orchestrator(保留 delegation 工具集)。_build_child_agent 是唯一降级点:只有 orchestrator_enabled 开关打开且 child_depth < max_spawn_depth 时角色才生效,否则静默降级为 leaf。深度用 child._delegate_depth 逐层传递,delegate_task 入口再做 depth >= max_spawn 的硬拒绝。默认 MAX_DEPTH=1 即完全扁平(orchestrator 在默认配置下是 no-op),max_spawn_depth 有下限 1 无上限。orchestrator 的系统提示会追加'何时该/不该委派'与真实深度说明,避免模型幻想不存在的嵌套能力;工具 schema 的 role 描述也按当前配置动态改写(Nesting IS/OFF)。另有 set_spawn_paused 全局暂停开关供 TUI/RPC 冻结新 spawn。
- **证据**:`tools/delegate_tool.py:127` · `tools/delegate_tool.py:1242` · `tools/delegate_tool.py:931` · `tools/delegate_tool.py:3756`
  ```
  MAX_DEPTH = 1  # flat by default: parent (0) -> child (1); grandchild rejected unless max_spawn_depth raised.
  ```
- **规模**:角色/深度相关代码(_normalize_role、_get_max_spawn_depth、_get_orchestrator_enabled、动态 schema、系统提示分支)约 300 行,逻辑集中、边界清晰。
- **学习价值**:高 — 把'能力授予'从模型自由裁量改为配置驱动+单点降级,并把真实限额动态写回工具 schema 让模型看到真话——这是治理代理树失控的成熟模式。
- **▲ 文档不符**:AGENTS.md:1005 称 max_spawn_depth 默认 2(暗示 orchestrator 开箱可用),代码默认是 1(tools/delegate_tool.py:127),默认配置下 role=orchestrator 会被静默降级为 leaf;website delegation.md:303 则正确写明 'default 1 = flat, so role=orchestrator is a no-op at defaults'。delegate_task 内部注释 2846 行 'default 2 for parity' 也是陈旧的。

#### 114. 后台委派:持久化完成队列与 claim/ack 投递协议  **[▲文档不符]**

- **解决**:后台子代理的结果必须在父代理空闲时以全新回合注入对话(不能拼接在 tool result 与 assistant 消息之间破坏角色交替和 prompt cache),且进程重启、多个消费者竞争、会话轮换时结果不能丢失或被错误会话吞掉。
- **实现**:顶层模型发起的 delegate_task 一律后台执行(_model_background_value:非子代理即 background),批量作为一个异步单元 join 全部子代理后推送单条合并事件。dispatch_async_delegation(_batch) 在 _records_lock 单锁内做容量检查+登记(满员直接拒绝并回退同步执行,不排队),同时把 dispatch 写入 ~/.hermes/state.db 的 async_delegations 表。完成时 _push_completion_event 携带自包含任务源块(goal/context/model/时间/结果)入共享 process_registry.completion_queue;投递用 claim_completion_delivery 的 SQL CAS(300 秒 claim 过期、delivery_attempts 计数、超过 8 次转终态 dropped)实现跨进程互斥;重启后 restore_undelivered_completions 恢复 pending 事件并打 restored=True 标记强制正向所有权校验,recover_abandoned_delegations 按 owner_pid+进程启动时间判定属主死亡并记 outcome=unknown。
- **证据**:`tools/async_delegation.py:9` · `tools/async_delegation.py:766` · `tools/async_delegation.py:394` · `tools/async_delegation.py:363` · `tools/delegate_tool.py:3889`
  ```
  When the child finishes, a completion event is pushed onto the SHARED
  ``process_registry.completion_queue`` with ``type="async_delegation"``. The
  CLI (``cli.py`` process_loop) and gateway (``_run_process_watcher`` /
  ```
- **规模**:async_delegation.py 1515 行 + delegate_tool.py 后台分发段约 250 行;复杂度非常高(SQLite 持久化、claim CAS、会话路由、有限会话降级同步、wake 自 POST)。
- **学习价值**:高 — 完整展示了'后台代理结果如何安全回注对话'这一 harness 核心难题的工程解:复用完成队列保消息交替合法、durable claim/ack 防丢防重、restored 标记防新会话吞旧结果,每一步都有 issue 编号佐证。
- **▲ 文档不符**:AGENTS.md:986-989 仍描述'默认父代理同步等待、background=true 才异步',而代码中模型侧 background 参数已 DEPRECATED/IGNORED(schema 3854-3864),顶层调用一律后台;AGENTS.md:1012-1013 称后台委派 'still process-local',而完成事件实际持久化在 state.db 并在重启后恢复投递(仅子代理执行本身不跨重启)。website delegation.md 的 'Durable background completions' 一节是准确的。

#### 115. 双层无进度停滞检测(取代墙钟超时)

- **解决**:对子代理设统一墙钟超时会误杀合法的长任务(深度审查、慢推理模型),但完全不设防又会让卡死的子代理永远占住父回合或让后台委派永远显示 dispatched。
- **实现**:默认 DEFAULT_CHILD_TIMEOUT=None(无硬超时,child_timeout_seconds 可选回开)。同步路径:_run_single_child 起心跳线程每 30 秒把子代理活动转发给父的 _touch_activity 防网关误杀;同时跟踪 (iteration, current_tool, last_activity_ts) 三元组,全部冻结才累计 stale 周期,idle 阈值 15 周期(450s)、in-tool 阈值 40 周期(1200s),超限则停止心跳让网关 inactivity 超时自然触发。异步路径:单例 _stale_monitor_loop 通过注入的 progress_fn 采样所有子代理的进度 token,冻结超阈先 interrupt、给 120s 宽限让其走正常 finalize,仍不返回才强制发 stalled 终态事件。流式 chunk 与模型等待中的 activity 心跳都算进度,慢模型不会被误判。
- **证据**:`tools/delegate_tool.py:732` · `tools/delegate_tool.py:748` · `tools/delegate_tool.py:2072` · `tools/async_delegation.py:109`
  ```
  DEFAULT_CHILD_TIMEOUT: Optional[float] = None
  ```
- **规模**:同步心跳 + 异步 stale monitor 合计约 450 行,复杂度中高(区分 idle/in-tool 双阈值、interrupt→grace→force-finalize 三段式)。
- **学习价值**:高 — '基于进度而非时长'的停滞检测是对朴素 timeout 的重要升级,idle/in-tool 双阈值与 interrupt+宽限+强制终结三段式在长任务代理系统里普适。

#### 116. 子代理摘要上下文预算与溢写分页  **[◇未见于文档]**

- **解决**:批量 fan-out 的 N 份完整摘要同时进入父上下文会撑爆窗口,触发压缩/429 死亡螺旋(issue #9126),但直接截断又会丢失子代理产出。
- **实现**:_parent_summary_char_budget 用父代理剩余上下文余量(context_length - session_prompt_tokens - 压缩器保留)乘 _SUMMARY_HEADROOM_FRACTION=0.5 再除以批大小,按 ~4 chars/token 换算出每份摘要预算(下限 2000 字符),再与静态上限 delegation.max_summary_chars(默认 24000)取 MIN。超预算的摘要做 75% 头 + 25% 尾按行边界切片,全文 _spill_summary_to_file 落盘到 cache/delegation/(该目录被只读挂载进 Docker/Modal/SSH 远端后端),并在截断 footer 里给出精确的 read_file path/offset/limit 指令让父代理可分页读中间被省略部分。
- **证据**:`tools/delegate_tool.py:723` · `tools/delegate_tool.py:1907` · `tools/delegate_tool.py:1860`
  ```
  _SUMMARY_HEADROOM_FRACTION = 0.5
  ```
- **规模**:约 200 行(_spill/_trim/_parent_summary_char_budget/_apply_summary_budget),实现精巧、独立可移植。
- **学习价值**:高 — '动态余量预算 + 头尾保留 + 溢写落盘 + 自描述分页指针'是处理子代理→父代理信息回传的上乘方案,比固定截断优雅得多,且完全不丢信息。

#### 117. 委派实时转录(live transcripts)与强制脱敏

- **解决**:父代理/用户在子代理运行期间只能盲等合并摘要,无法观察子代理在做什么;而转录文件会被只读挂载进远端沙箱,任何凭据落入其中都等于泄漏。
- **实现**:每次 delegate_task 在 cache/delegation/live/<delegation_id>/task-<n>.log 预创建带头部的 append-only 日志(tail -f 立即可用),wrap_progress_callback 把子代理的 assistant 文本/thinking/工具调用/工具结果/生命周期标记逐行写入,每行单行化+截断;路径通过工具返回值和 live_transcripts_hint 告知模型可随时 tail。写入前所有文本经 redact_sensitive_text(force=True) 强制脱敏(即使全局开关关闭),redactor 不可用时宁可扣留整行。保留 7 天,新 dispatch 时机会式清理。所有写入永不向 agent loop 抛异常,首次失败即禁用该 writer。
- **证据**:`tools/delegation_live_log.py:3` · `tools/delegation_live_log.py:97` · `tools/delegate_tool.py:3382`
  ```
  Every ``delegate_task`` dispatch creates one append-only, human-readable log
  per child under::
  ```
- **规模**:delegation_live_log.py 424 行,复杂度中等;设计约束(永不抛异常、侧信道零缓存影响、强制脱敏)写得非常明确。
- **学习价值**:中 — 侧信道可观测性(不动消息内容、不碰 prompt cache)+ 把脱敏当安全边界强制执行,是多代理系统可观测性的实用范式;实现本身不难但边界意识值得学。

#### 118. ContextVar 委派语境隔离与 Kanban 身份防伪  **[◇未见于文档]**

- **解决**:delegate_task 子代理与父代理同进程,若父进程本身是 Kanban dispatcher 派生的 worker(env 里有 HERMES_KANBAN_*),子代理或 worker 内触发的 cron job 会被误认为任务属主,可能 kanban_complete 关掉 worker 的任务、覆盖真实结果。
- **实现**:delegation_context.py 用两个 ContextVar 标记:delegated_child_context()(子代理构建+执行期间)与 non_dispatcher_owned_context()(worker 内 in-process cron)。唯一判定谓词 is_dispatcher_owned_worker_context() 要求两者皆否才信任 HERMES_KANBAN_* 身份。刻意不改 os.environ(env 是进程全局,会饿死 worker 自己的 claim 心跳)。跨 fork 时 delegated_child_subprocess_env/scrub_kanban_env 剥除 7 个 HERMES_KANBAN_* 变量并注入 HERMES_DELEGATED_CHILD_CONTEXT=1 血统标记。kanban_tools 的所有变更类工具经 _reject_delegated_child_mutation 对子代理直接拒绝,工具可见性 check_fn 也按此谓词分流 worker 面/orchestrator 面。
- **证据**:`agent/delegation_context.py:104` · `agent/delegation_context.py:133` · `tools/kanban_tools.py:95`
  ```
      if _DELEGATED_CHILD_CONTEXT.get():
          return False
      return not _NON_DISPATCHER_OWNED_CONTEXT.get()
  ```
- **规模**:delegation_context.py 161 行 + kanban_tools.py 门控约 100 行;代码量小但概念密度高(ContextVar vs env、同进程多身份)。
- **学习价值**:高 — 同进程多代理的'身份混淆'是极易被忽略的攻击面/事故源,这里用 ContextVar 作用域化身份而非污染全局 env 的做法非常干净,值得任何嵌套代理系统借鉴。

#### 119. Kanban dispatcher:原子 claim、回收与并发治理

- **解决**:多个全进程 worker + 可能并存的多个 dispatcher 共享一个 SQLite 看板,需要防止双 dispatcher 竞争、防止任务被双领取、检测崩溃/超时/失联 worker,并限制全局与每 profile 并发。
- **实现**:dispatch_once 每 tick 先拿板级跨进程非阻塞 _dispatch_tick_lock(输者返回 skipped_locked 不写库),然后顺序执行:release_stale_claims(TTL 过期)→ detect_stale_running(心跳超时)→ detect_crashed_workers(worker_pid 死亡+启动时间校验,含限流 requeue)→ enforce_max_runtime → recompute_ready(父任务全 done 才促升)。claim_task 在 write_txn 里用 'UPDATE ... WHERE status=ready AND claim_lock IS NULL' 的 CAS 原子转 running 并插入 task_runs 行,还会在 claim 点强制'父未完成不得运行'的结构不变量。max_spawn 是活跃并发上限(计入已 running)而非每 tick 预算;另有 max_in_progress、max_in_progress_per_profile、failure_limit 连续失败自动 block 熔断。默认由 gateway 内嵌 dispatcher 跑,独立 daemon 已弃用需 --force。
- **证据**:`hermes_cli/kanban_db.py:4289` · `hermes_cli/kanban_db.py:8252` · `hermes_cli/kanban_db.py:8304` · `hermes_cli/kanban_db.py:8320`
  ```
              UPDATE tasks
                 SET status        = 'running',
                     claim_lock    = ?,
                     claim_expires = ?,
                     started_at    = COALESCE(started_at, ?)
  ```
- **规模**:kanban_db.py 10275 行(claim/回收/dispatch 核心约 2000 行)+ hermes_cli/kanban.py 3236 行 CLI;复杂度极高,是仓内最大的多代理协调内核。
- **学习价值**:高 — 以 SQLite 为唯一协调内核实现多代理工作队列(CAS claim、TTL/心跳/PID 三重回收、单写 tick 锁、活跃并发语义)是'无新服务'多代理调度的完整参考实现。

#### 120. Kanban worker 生命周期协议(env 注入 spawn、stop-nudge、goal judge 门)

- **解决**:dispatcher 派生的 worker 是普通 CLI 代理进程,必须让它准确知道自己的任务身份/看板/工作区,必须以 kanban_complete/kanban_block 终态收尾(否则记 protocol violation),且 goal 模式下不能自说自话绕过验收。
- **实现**:_default_spawn 以 'hermes -p <assignee> --cli chat -q "work kanban task <id>"' 起 detached 子进程:注入 HERMES_KANBAN_TASK/RUN_ID/CLAIM_LOCK/DB/BOARD/WORKSPACES_ROOT 钉死板上下文,HERMES_HOME 切 profile 配置,TERMINAL_CWD 锚定工作区,清除会话路由 env,输出重定向到板级 per-task 日志并轮转,返回 PID 供崩溃检测。HERMES_KANBAN_TASK 触发 kanban_* 工具进 schema。agent/kanban_stop.py 在 worker 无终态工具就想收尾时注入最多 2 次合成 nudge 强制其调用 kanban_complete/kanban_block。kanban_complete 对 goal_mode 任务先过辅助 judge(judge_goal),verdict!=done 则拒绝完成并指导补证据或建续任务;还有 created_cards 幻觉卡检测与 artifact 保全校验。
- **证据**:`hermes_cli/kanban_db.py:9019` · `hermes_cli/kanban_db.py:9155` · `agent/kanban_stop.py:89` · `tools/kanban_tools.py:754`
  ```
      env["HERMES_KANBAN_TASK"] = task.id
      env["HERMES_KANBAN_WORKSPACE"] = workspace
  ```
- **规模**:_default_spawn 约 210 行 + kanban_stop.py 108 行 + kanban_tools.py 完成/阻塞路径约 400 行;复杂度高(env 钉死、profile 切换、日志轮转、多重完成门)。
- **学习价值**:高 — 展示了'把 LLM 代理当不可靠进程管理'的全套协议:身份经 env 注入、终态经合成 nudge 强制、验收经独立 judge 把关、汇报经幻觉检测过滤——每层都在补模型不守协议的坑。

#### 121. 运行中 worker 双向通道:自动心跳 + 评论 steer 注入  **[◇未见于文档、▲文档不符]**

- **解决**:长时任务 worker 若忘记调 kanban_heartbeat 会被 dispatcher 误回收;操作员想给运行中的 worker 补充指示,原本只能走 block→comment→unblock 或重启,时延和进度损失都大。
- **实现**:agent loop 周期性调用 heartbeat_current_worker_from_env():从 HERMES_KANBAN_TASK/RUN_ID/CLAIM_LOCK 取身份,限流后自动执行 heartbeat_claim(续 claim TTL)+ heartbeat_worker(板面心跳),run_id 钉死防止给已被回收的旧 run 心跳。inject_new_comments_from_env() 以 6 秒最小间隔轮询任务评论表,首轮只播种水位(历史评论已在 worker 上下文里),之后把非本 profile 作者的新评论拼成 '[delivered mid-run]' 通知,经 agent.steer() 走 out-of-band steer 通道注入正在运行的会话,让操作员几秒内'对话'运行中的任务。两者均 best-effort、永不向 agent loop 抛异常。
- **证据**:`tools/kanban_tools.py:312` · `tools/kanban_tools.py:403` · `tools/kanban_tools.py:410`
  ```
              claim_lock = os.environ.get("HERMES_KANBAN_CLAIM_LOCK")
              try:
  ```
- **规模**:两个函数合计约 140 行,轻量但接进 agent loop 的钩子位置关键。
- **学习价值**:中 — 'harness 替模型兜底履约(自动心跳)'+'人类经 steer 通道实时干预运行中代理'是多代理人机协同的两个实用小机制,水位/限流/自动过滤自身评论的细节可直接抄。
- **▲ 文档不符**:kanban 文档只描述模型手动调用 kanban_heartbeat(kanban.md:297,395)与评论在(重)spawn 时读入(kanban.md:64),未提及 harness 层的自动心跳兜底与运行中评论 steer 注入。

#### 122. 批量轨迹生成(batch_runner + toolset 概率采样 + mini_swe_runner)

- **解决**:research 场景需要对成千上万 prompt 并行跑完整代理会话产出训练轨迹,要求断点续跑、工具集多样性采样、每样本独立沙箱镜像,以及一个极简单工具的 SWE 基线 runner。
- **实现**:BatchRunner 把 JSONL 数据集切批,multiprocessing.Pool(num_workers) + imap_unordered 并行跑批,每完成一批原子写 checkpoint.json(completed_prompts 集合)支持 --resume 崩溃续跑;每条 prompt 经 sample_toolsets_from_distribution 按分布(default/research/science/development/safe 等)独立掷骰采样工具集制造轨迹多样性,支持数据集行内 image 字段为该任务注册 Docker/Modal/Singularity/Daytona 镜像覆盖;代理以 skip_context_files/skip_memory 运行保持轨迹干净,输出含 tool_stats/reasoning_stats。mini_swe_runner 则是仅暴露单个 terminal 工具的极简循环,用命令输出中的 MINI_SWE_AGENT_FINAL_OUTPUT 哨兵判定完成,产出与 batch_runner 兼容的 Hermes from/value 轨迹格式。
- **证据**:`batch_runner.py:920` · `batch_runner.py:961` · `toolset_distributions.py:271` · `batch_runner.py:344` · `mini_swe_runner.py:525`
  ```
          with Pool(processes=self.num_workers) as pool:
  ```
- **规模**:batch_runner.py 1330 行 + mini_swe_runner.py 732 行 + toolset_distributions.py 358 行;复杂度中等,工程化程度(进度条、checkpoint、镜像预检)较高。
- **学习价值**:中 — 是'代理 harness 兼作训练数据工厂'的直接样本:工具集概率采样制造分布多样性、轨迹格式与 ephemeral system prompt 分离、断点续跑,这些是做 agent RL/SFT 数据管线的常见需求。

#### 123. MoA(Mixture of Agents)循环:并行参考模型 + 聚合器代行  **[▲文档不符]**

- **解决**:困难任务需要多模型视角,但仍要保留正常代理循环(工具调用、迭代、中断、会话持久化);参考模型不能拿到工具 schema(严格 provider 会 400),又必须看到代理真实做过什么才能给出有依据的建议。
- **实现**:MoA 是虚拟 provider:preset 的 aggregator 是 acting model,MoAChatCompletions 在每次主模型调用前经 _run_references_parallel 并行 fan-out 全部参考模型(ThreadPoolExecutor + 轮询 wait 支持用户中断,被放弃的在飞调用经 late_accounting_sink 补记费用),_reference_messages 把完整对话扁平化为纯 user/assistant 文本——工具调用渲染成 '[called tool: name(args)]'、工具结果头尾截断折入前一 assistant 回合,结尾必补合成 user 回合满足 Anthropic 无前缀填充规则;参考输出按 state 签名缓存(新工具结果=miss 重跑)。聚合器收到参考指导块后以正常工具 schema 行动。另有 every_n 节奏、privacy_filter(display/full 两级 PII 脱敏)、全部参考失败时跳过聚合直接降级、moa_trace 落盘全保真 JSONL(含每参考完整输入输出与用量成本)。
- **证据**:`agent/moa_loop.py:789` · `agent/moa_loop.py:1012` · `agent/moa_loop.py:1113` · `agent/moa_loop.py:1505` · `agent/moa_trace.py:127`
  ```
      Like ``delegate_task``'s batch mode, every reference is dispatched at once
      and we block until all of them finish before handing the joined results to
      the aggregator. Output order matches ``reference_models`` so the
  ```
- **规模**:moa_loop.py 2384 行 + moa_trace.py 167 行;复杂度很高(缓存签名、跨 provider 消息形状兼容、中断后费用追认、隐私过滤)。
- **学习价值**:高 — 把 MoA 做成'OpenAI 兼容 facade 的虚拟 provider'而非独立循环,使其零成本复用整个 harness(工具、会话、中断);advisory view 的消息形状工程(扁平化工具转录、末尾合成 user 回合)浓缩了大量跨 provider 兼容实战经验。
- **▲ 文档不符**:website/docs/user-guide/features/mixture-of-agents.md:55 称参考模型'receive only the conversation's user/assistant text — not the Hermes system prompt or tool-call transcript',但代码的 advisory view 刻意保留工具转录:tool_calls 渲染为 '[called tool: ...]'、工具结果折入 assistant 文本(agent/moa_loop.py:1006-1016);'不含 system prompt'部分属实,'不含 tool-call transcript'与实现相反。

**本子系统文档-代码冲突(6 条):**

- 宣称:AGENTS.md:986-989:"By default the parent waits for the child's summary before continuing its own loop. With `background=true`, Hermes returns a delegation id immediately"
  实际:模型侧 background 参数已 DEPRECATED/IGNORED(schema 描述明说 'Setting this has no effect'),注册 handler 用 _model_background_value 强制:顶层(depth==0)模型调用一律后台执行,只有 orchestrator 子代理(depth>0)同步等待自己的 worker。(证据:`tools/delegate_tool.py:3889`)
- 宣称:AGENTS.md:993:"**Single:** pass `goal` (+ optional `context`, `toolsets`)"
  实际:DELEGATE_TASK_SCHEMA 的 properties 只有 goal/context/tasks/role/background,没有 toolsets;delegate_task 调用 _build_child_preserving_parent_tools 时硬编码 toolsets=None,注释明确 'the model cannot choose or narrow them (no model-facing toolsets arg)'。website delegation.md:158 的说法才与代码一致。(证据:`tools/delegate_tool.py:2967`)
- 宣称:AGENTS.md:1005:role="orchestrator" "bounded by `delegation.max_spawn_depth` (default 2)"
  实际:代码默认 MAX_DEPTH = 1('flat by default'),_get_max_spawn_depth 无配置时返回 1,因此默认配置下 child_depth(1) < max_spawn(1) 不成立,role=orchestrator 被静默降级为 leaf;website delegation.md:303 正确写明 'default 1 = flat, so role=orchestrator is a no-op at defaults'。delegate_task 内部 2846 行注释 'default 2 for parity' 同样陈旧。(证据:`tools/delegate_tool.py:127`)
- 宣称:AGENTS.md:1012-1013:"background `delegate_task` is detached from the current turn but still process-local"(暗示无任何跨重启机制)
  实际:后台委派的 dispatch 与完成事件持久化在 state.db 的 async_delegations 表:重启后 restore_undelivered_completions 恢复未投递完成事件(打 restored=True 强制所有权校验),recover_abandoned_delegations 把属主进程消失的记录转为 outcome=unknown 并照常投递。仅子代理执行本身不跨重启,结果投递是持久的(website delegation.md 'Durable background completions' 一节有准确描述)。(证据:`tools/async_delegation.py:363`)
- 宣称:website/docs/user-guide/features/mixture-of-agents.md:55:参考模型 "receive only the conversation's user/assistant text — not the Hermes system prompt or tool-call transcript"
  实际:_reference_messages 的 advisory view 刻意保留工具轨迹:assistant 的 tool_calls 渲染为 '[called tool: name(args)]' 文本,tool-role 结果头尾截断后以 '[tool result: ...]' 折入前一 assistant 回合;docstring 明说参考模型 'must see what the agent actually did — its tool calls AND the tool results'。仅 system prompt 被丢弃这半句属实。(证据:`agent/moa_loop.py:1012`)
- 宣称:website/docs/user-guide/features/delegation.md:211:"Background delegations (`delegate_task(background=true)`) are watched by a ..."(仍以 background=true 作为触发方式表述)
  实际:background 参数对模型已无效(DEPRECATED / IGNORED,tools/delegate_tool.py:3854-3864),后台化由 harness 按调用者深度自动决定;该文档其余部分(自动后台、durable completions)与代码一致,仅此处措辞沿用旧参数。(证据:`tools/delegate_tool.py:3857`)

### 2.11 定时任务与后台自治(cron/、agent/background_review.py、agent/outbound_webhooks.py、gateway/wake.py、gateway/kanban_watchers.py、agent/session_activity.py、tools/cronjob_tools.py)

该子系统让 Hermes 在无人值守下自主运转:cron/ 提供一个建立在 jobs.json + flock 之上的完整调度器——60s tick 循环(跨进程文件锁、并行/串行双池)、四种 schedule 语法解析与时区迁移修复、半周期 clamp 的 catchup/grace 窗口(过期 fast-forward 但仍补跑一次)、以及由 advance-first、claim_dispatch 预扣、run_claim 租约心跳和 SQLite 执行台账组成的跨进程 at-most-once 语义栈。每次运行在独立的 cron_{job_id}_{ts} 会话中以 platform="cron"、skip_memory=True 构造 agent,受 600s 不活动看门狗(request_hard_interrupt)与双层注入扫描、gateway 生命周期防护、凭据外泄与模型漂移 fail-closed 保护;prompt 组装管道支持 script 预处理 + wakeAgent 门、no_agent 纯脚本模式和 context_from 链式流水线,产出经 fire-time 解析的多平台投递([SILENT] 静默契约、live adapter 优先、可选 user-role mirror 保持目标会话的角色交替)。触发器经 CronScheduler provider 抽象可替换(外部 fire 走 store CAS 认领,与内置 ticker 共享同一 run_one_job 执行体)。外围的后台自治组件包括:回合后 fork 自我改进回路 background_review(共享父会话 id 蹭前缀缓存但禁止一切持久化)、kanban notifier/dispatcher 守望循环(事件游标原子认领、机器级单例锁)、deliver_wake 双通道会话唤醒(合成 internal 事件或带 X-Hermes-Session-Id 自 POST)以及 HMAC 签名的 outbound webhooks 事件外发。

关键文件(16 个,行数实测,余见 JSON):`cron/scheduler.py`(4428), `cron/jobs.py`(2746), `cron/scheduler_provider.py`(357), `cron/executions.py`(280), `cron/lifecycle_guard.py`(565), `cron/blueprint_catalog.py`(713), `cron/suggestions.py`(260), `cron/suggestion_catalog.py`(154)


#### 124. 60s tick 循环:跨进程文件锁 + 并行/串行双线程池调度  **[▲文档不符]**

- **解决**:多个进程(gateway 内置 ticker、独立 daemon、手动 hermes cron run)可能同时 tick 同一个 jobs.json,导致重复触发;同时单个长任务不能阻塞整个调度器,而带 workdir 的任务会改进程级全局 os.environ['TERMINAL_CWD'],并发会互相污染。
- **实现**:入口 cron/scheduler.py::tick():先以 ~/.hermes/cron/.tick.lock 上非阻塞 flock(Unix)/msvcrt(Windows)排他锁,拿不到锁直接跳过本次 tick;拿到后把 due jobs 按是否有 workdir 分成两组——workdir 任务进单线程 sequential pool(串行),其余进 persistent parallel pool(HERMES_CRON_MAX_PARALLEL / cron.max_parallel_jobs 限并发)。_submit_with_guard 用 _running_job_ids 集合做 in-flight 去重(上一 tick 未完的任务不重复入队),并用 contextvars.copy_context() 把调度线程上下文带进 worker。另有 _ReadWriteLock:workdir 任务持写锁独占 TERMINAL_CWD 覆盖,无 workdir 任务持读锁并行。gateway 异步模式下 tick 不等待任务完成,用 done-callback 在最后一个任务结束后清扫 MCP 孤儿子进程。
- **证据**:`cron/scheduler.py:4182` · `cron/scheduler.py:4266` · `cron/scheduler.py:4291`
  ```
          if fcntl:
              fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
          elif msvcrt:
              msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
  ```
- **规模**:tick() 约 280 行 + 池管理/锁约 200 行;中高复杂度(跨平台锁、双池分区、shutdown 竞态防护)
- **学习价值**:高 — 文件锁 + in-flight 去重 + 双池分区是任何多进程 agent 调度器的通用骨架;TERMINAL_CWD 读写锁展示了『进程级全局状态如何在并行任务下被安全覆盖』的完整解法。
- **▲ 文档不符**:AGENTS.md 只提到 .tick.lock 文件锁;并行/串行双池、workdir 读写锁、in-flight 去重均未见于任何文档。

#### 125. 自然语言 schedule 解析与时区锚定/偏移修复  **[▲文档不符]**

- **解决**:用户以四种语法(时长、every 间隔、5 字段 cron、ISO 时间戳)提交计划;naive 时间戳若按服务器本地时区解释会与配置时区(hermes_time.now())相差数小时,导致 one-shot 永不 due;主机/配置时区迁移后存量 next_run_at 的旧 offset 会造成提前触发+二次触发(#28934)。
- **实现**:cron/jobs.py::parse_schedule() 按顺序尝试:'every X' → interval(parse_duration 换算分钟);5 个以上纯 cron 字段 → croniter 校验后存 expr;含 T/日期形状 → ISO one-shot,naive 时间戳在解析时锚定到 Hermes 配置时区(#51021);裸时长 → now+delta 的 one-shot。due 扫描时 _ensure_aware 把 legacy naive 值按系统本地时区回填;cron 类任务若 stored offset 与 now offset 不一致且 stored 墙钟仍在未来(_timezone_offset_mismatch + _stored_wall_clock_is_future),视为时区迁移,按当前时区重算 next_run_at 而不是按换算后的绝对时刻提前触发。
- **证据**:`cron/jobs.py:587` · `cron/jobs.py:632` · `cron/jobs.py:2376`
  ```
      if schedule_lower.startswith("every "):
          duration_str = schedule[6:].strip()
          minutes = parse_duration(duration_str)
  ```
- **规模**:parse_schedule + 时区辅助约 200 行;中复杂度但边界推理密集(DST vs 迁移的 trade-off 有整段注释)
- **学习价值**:高 — 『墙钟意图 vs 绝对时刻』是所有跨时区调度器的经典坑;这里给出了 naive 锚定、legacy 回填、offset 迁移修复三层完整方案且明确标注了 DST 边界的取舍。
- **▲ 文档不符**:AGENTS.md:1061 宣称支持 "every monday 9am"、website cron.md:135 示例 "every 1d at 09:00"——parse_duration 的正则 ^(\d+)\s*(m|...|days)$ 均不接受这类表达式,实际会 raise ValueError。

#### 126. catchup/grace 窗口:过期 fast-forward 但仍补跑一次

- **解决**:gateway 宕机或长任务超过间隔后积压了多个错过的触发点:全部补跑会 burst-fire,全部跳过又会让『运行时长 > interval+grace』的任务被永远推迟(#33315 perpetual-defer)。
- **实现**:cron/jobs.py::_compute_grace_seconds() 取调度周期的一半、clamp 到 [120s, 7200s];_get_due_jobs_locked() 中若 recurring 任务的 next_run_at 落后超过 grace,则把 next_run_at fast-forward 到下一个未来时点并立即持久化(防 crash 窗口、覆盖外部 fire_due 路径),但该任务仍然 append 进 due 列表执行一次,同时 record_catch_up_occurrence() 记账供 hermes cron status 展示。one-shot 有独立的 ONESHOT_GRACE_SECONDS=120 宽限(创建晚几秒仍可触发),已跑过的 one-shot 永不重新武装。
- **证据**:`cron/jobs.py:745` · `cron/jobs.py:2404` · `cron/jobs.py:116`
  ```
      MIN_GRACE = 120
      MAX_GRACE = 7200  # 2 hours
  ```
- **规模**:约 120 行;逻辑不长但语义精细(fast-forward 与『仍 fire 一次』的组合)
- **学习价值**:高 — 『塌缩积压但保底补一枪』是错过窗口处理的最优折中,直接可移植到任何调度器;grace=半周期 clamp 的启发式也值得抄。

#### 127. at-most-once 语义栈:advance-first / claim_dispatch 预扣 / run_claim 心跳 / 执行台账  **[◇未见于文档、▲文档不符]**

- **解决**:cron 触发有多层重复触发风险:同 HERMES_HOME 上 gateway+desktop 两个 60s ticker 会重复派发 one-shot(#59229);tick 进程在执行中途死掉会让有限次 one-shot 无限重发(#38758);合法长跑任务又不能被误判为死主而被另一进程抢走(#62002);重启后无法知道中断的执行是否产生过副作用。
- **实现**:四层机制:(1) tick 在派发前先在文件锁内批量 advance_next_runs() 推进 recurring 任务的 next_run_at,保证 at-most-once;(2) jobs.py::claim_dispatch() 在副作用发生前原子递增 repeat.completed 并落盘,把有限次 one-shot 从 at-least-once 变为 at-most-times;(3) due 扫描时给 one-shot 盖 run_claim{at, by=machine_id},另一进程读到新鲜 claim 就跳过;运行监控线程按 _RUN_CLAIM_HEARTBEAT_SECONDS 周期用 heartbeat_run_claim(expected_owner=...) 比较所有者后刷新时间戳,让『claim 过期』真正等价于『持有进程已死』,TTL 从 HERMES_CRON_TIMEOUT 推导;(4) cron/executions.py 用 SQLite 台账记录每次 attempt(claimed→running→terminal),重启后 recover_interrupted_executions() 用 PID+进程启动时间验尸,把确认死掉的标为 status='unknown' 且绝不自动重试;wedged one-shot 移除时写 _write_wedged_oneshot_diagnostic 诊断文件(#73973)。
- **证据**:`cron/scheduler.py:4224` · `cron/jobs.py:1902` · `cron/jobs.py:2501` · `cron/jobs.py:1944` · `cron/executions.py:214`
  ```
          advance_next_runs([job["id"] for job in due_jobs])
  ```
- **规模**:跨 jobs.py/scheduler.py/executions.py 约 700 行;高复杂度(多进程、TTL、心跳、验尸恢复的完整分布式语义)
- **学习价值**:高 — 这是整个子系统最硬核的部分:单机文件存储上实现了教科书级 exactly/at-most-once 语义分层(claim before side-effect、lease+heartbeat、owner compare-and-refresh、unknown 而非自动重试),几乎每一层都对应一个真实事故编号。
- **▲ 文档不符**:cron.md:264 只文档了 executions.db 台账一角;claim_dispatch 预扣、run_claim 心跳、advance-first、wedged 诊断文件在 README/AGENTS.md/website 均无覆盖。

#### 128. 不活动看门狗与硬中断(而非文档宣称的 3 分钟)  **[▲文档不符]**

- **解决**:失控的 agent 循环或挂死的 API 调用会永久占住 cron worker 线程;但合法任务可能连续跑几小时,不能用简单墙钟超时一刀切。
- **实现**:run_job 把 agent.run_conversation 提交到单线程池,主线程每 5s 轮询:未完成时读 agent.get_activity_summary().seconds_since_activity(agent 在每次工具调用/API 调用/流式 token 时 _touch_activity 刷新,契约见 agent/session_activity.py),空闲超过 HERMES_CRON_TIMEOUT(默认 600s,0=无限)判定超时,调用 request_hard_interrupt(agent, ...) 硬中断并 raise TimeoutError,失败路径带上 last_activity/iteration/tool 的诊断快照。同一轮询循环还顺带做 one-shot 的 run_claim 心跳。另有独立的 SessionDB 构造超时(默认 10s,单独线程池 submit(SessionDB).result(timeout=...)),防止 wedged sqlite flock 把任务卡在 _running_job_ids 里永远 'already running — skipping'。
- **证据**:`cron/scheduler.py:3577` · `cron/scheduler.py:3654` · `cron/scheduler.py:3684` · `cron/scheduler.py:2961`
  ```
          else:
              _cron_timeout = 600.0
          _cron_inactivity_limit = _cron_timeout if _cron_timeout > 0 else None
  ```
- **规模**:约 180 行;中复杂度(轮询循环叠加心跳、活动快照诊断)
- **学习价值**:高 — 『按活动而非墙钟计超时』是无人值守 agent 的关键设计——允许长任务、只杀真挂死;配合 activity tracker 的诊断快照,超时报错自带 last_activity/tool 上下文。
- **▲ 文档不符**:AGENTS.md:1073 宣称『3-minute hard interrupt on cron sessions』;代码实际是默认 600s 的不活动(inactivity)超时,可经 HERMES_CRON_TIMEOUT 调整、0 为无限,并非 3 分钟也非墙钟;website cron-internals.md:216 的描述才与代码一致。

#### 129. prompt 组装管道:script 预处理 / wakeAgent 门 / no_agent 模式 / context_from 链式任务

- **解决**:定时任务往往需要先采集数据再喂给 LLM,数据无变化时不应烧 token;经典 bash 看门狗根本不需要 LLM;下游任务需要引用上游任务的最新产出形成流水线。
- **实现**:job.script 在构建 prompt 前先执行(_run_job_script:限定 HERMES_HOME/scripts/ 内、resolve 后 relative_to 校验防穿越/符号链接逃逸,.sh/.bash 走 bash 其余走 Python,经 build_subprocess_env 清洗凭据、stdout/stderr 过 redact_sensitive_text);stdout 末行是 {"wakeAgent": false} 则整体跳过 agent(_parse_wake_gate),空 stdout 也直接返回 None 跳过 AI 调用,有输出则以 '## Script Output' 前置注入 prompt。no_agent=True 时脚本即任务:stdout 原样投递、空输出静默、非零退出投递错误告警,完全不构造 AIAgent。context_from 把上游 job 的最新 output/<job>/<ts>.md 注入(job id 必须 12 位 hex 防路径注入,8000 字符截断)。组装完成后按内容分层过注入扫描(见安全栈)。
- **证据**:`cron/scheduler.py:2453` · `cron/scheduler.py:2271` · `cron/scheduler.py:2819` · `cron/scheduler.py:2516` · `cron/scheduler.py:2539`
  ```
      if not isinstance(gate, dict):
          return True
      return gate.get("wakeAgent", True) is not False
  ```
- **规模**:_run_job_script + _build_job_prompt + no_agent 分支约 500 行;中高复杂度
- **学习价值**:高 — 『脚本先行 + wakeAgent 门 + 空输出即静默』把 token 成本压到只在有事发生时才唤醒 LLM;context_from 用文件系统做任务间数据总线,是极轻量的 DAG 流水线实现。

#### 130. 多平台投递:origin/all 路由令牌、home channel、live adapter 优先与 [SILENT] 静默

- **解决**:无人值守任务的产出要送回正确的会话面(创建它的聊天、指定平台/频道/话题、或全部已接入平台),平台可能在任务创建后才接入;E2EE 房间(Matrix)只有 live adapter 能加密;无事可报时不应打扰用户。
- **实现**:deliver 字符串支持 local/origin/platform[:chat[:thread]]/all 及逗号组合,fire 时(而非创建时)解析:'all' 经 _expand_routing_tokens 展开为所有配好 home channel 的平台(_HOME_TARGET_ENV_VARS 映射 17+ 平台的 *_HOME_CHANNEL 环境变量,插件平台经 platform_registry 动态加入),按 (platform, chat_id, thread_id) 去重;origin 缺失时回退 home channel。_deliver_result 对每个 target 先尝试 gateway live adapter(需事件循环真在运行,live_adapter_ready 一次求值防漂移),失败回退无状态 HTTP 发送;MEDIA: 标签抽出为附件。agent 回复 [SILENT](含裸 SILENT/NO_REPLY 变体,经共享 is_autonomous_silence_response 匹配)则跳过投递但输出仍存档;失败任务必投递错误摘要(_summarize_cron_failure_for_delivery)。
- **证据**:`cron/scheduler.py:1283` · `cron/scheduler.py:264` · `cron/scheduler.py:1622` · `cron/scheduler.py:4053`
  ```
      for platform_name in _iter_home_target_platforms():
          if _get_home_target_chat_id(platform_name):
  ```
- **规模**:delivery 解析+发送约 1000 行(_deliver_result 单函数 650 行);高复杂度(平台矩阵×live/standalone×thread 语义)
- **学习价值**:中 — fire-time 解析路由令牌(而非创建时冻结)与 live-adapter-first 回退是多平台投递的通用模式;[SILENT] 契约展示了自治 lane 的静默协议如何与共享匹配器防语义漂移。

#### 131. cron 会话与主会话隔离 + user-role mirror 保交替  **[▲文档不符]**

- **解决**:cron 运行不能污染用户真实会话:写进目标聊天的 assistant turn 会造成 assistant→assistant 破坏严格角色交替(#2221);cron 的系统提示混进记忆会腐蚀用户画像;HERMES_SESSION_* 若从 origin 继承,工具会误以为真人在驱动(通知路由、TTS 格式、send_message 门)。
- **实现**:每次运行造独立会话 id cron_{job_id}_{ts},AIAgent 以 platform="cron"、skip_memory=True、独立 session_db 构造,结束后 end_session('cron_complete') 并按 SessionDB 的 compression 谱系解析最终会话 id 后设标题。set_session_vars(platform="", chat_id="", async_delivery=False) 清空会话上下文并声明无状态通道,使 delegate_task 走同步路径;enter_non_dispatcher_owned_context() 用 ContextVar 防止 cron agent 被误认为 kanban worker。投递默认不写目标会话;开启 attach_to_session/cron.mirror_delivery 后,mirror 以 role="user" + '[Cron delivery: ...]' 前缀落库(consecutive-user 可被 repair_message_sequence 安全合并),且仅镜像 origin 会话、不镜像广播目标;continuable 任务经 _open_continuable_cron_thread 开专属线程或 _seed_cron_channel_session 播种 flat 会话,会话键逐字段对齐用户后续回复会解析到的 build_session_key(Discord 线程键内幕、群聊需 origin 真实 user_id、DM 不嵌 user_id)。
- **证据**:`cron/scheduler.py:3030` · `cron/scheduler.py:3551` · `cron/scheduler.py:719` · `cron/scheduler.py:3167`
  ```
      _cron_session_id = f"cron_{job_id}_{_hermes_now().strftime('%Y%m%d_%H%M%S')}"
  ```
- **规模**:会话隔离+mirror/seeding 约 700 行;高复杂度(角色交替、会话键对齐、per-user 隔离群聊)
- **学习价值**:高 — 『机器产出的消息以 user-role+标签落库』是解决严格交替模型下自治消息注入的标准答案;seed 会话键必须逐字段等于未来入站回复的键,这个约束在别处极少被讲透。
- **▲ 文档不符**:AGENTS.md:1082 与 website cron-internals.md:272 均断言 cron 投递『绝不 mirror 到目标会话』;代码实为 attach_to_session/cron.mirror_delivery 可选开启,且 user-guide cron.md 的 Continuable jobs 一节已文档化该开关——两份内部文档已过时。

#### 132. 无人值守安全栈:双层注入扫描、gateway 生命周期防护、凭据外泄与模型漂移 fail-closed  **[▲文档不符]**

- **解决**:cron 非交互运行会自动批准工具调用,是注入攻击的最佳落点;任务还能调度 'hermes gateway restart' 造成 SIGTERM 重生死循环(#30719);存储的 provider+base_url 组合可把命名 provider 的密钥送到任意主机;未 pin 模型的任务会静默继承全局切换到付费模型($7.73 事故 #44585)。
- **实现**:五层:(1) 创建/更新时 _scan_cron_prompt 用严格模式(_CRON_THREAT_PATTERNS 注入指令 + 命令形状 + _CRON_EXFIL_COMMAND_PATTERNS curl/wget 秘密外传 + 不可见 Unicode 硬阻断,ZWJ emoji 白名单);(2) 运行时对组装 prompt 分层:含技能/注入数据用宽松集(仅无歧义注入指令,不可见字符消毒而非阻断,防误杀永久废掉任务),纯用户 prompt 保持严格集,命中抛 CronPromptInjectionBlocked,agent 不运行并投递 BLOCKED 报告;(3) cron/lifecycle_guard.py 以命令形状正则(hermes gateway restart|stop、launchctl/systemctl/pkill 针对 gateway,含 shell 续行折叠、引用脚本递归扫描 8 层/1MB)在 create_job 拒绝自杀任务;(4) fire 时 _guard_job_credential_exfil 重验 provider/base_url 对,验证器自身出错也 fail closed;(5) 未 pin 任务对比创建时 provider/model 快照,漂移则跳过运行、零推理花费并投递告警。另:cron 运行强制禁用 cronjob/messaging/clarify/memory 工具集(防递归调度),用户 disabled_toolsets 叠加不可被 per-job enabled_toolsets 绕过(#25752)。
- **证据**:`tools/cronjob_tools.py:97` · `cron/scheduler.py:2714` · `cron/lifecycle_guard.py:62` · `cron/scheduler.py:3477` · `cron/scheduler.py:180` · `cron/scheduler.py:2750`
  ```
  _CRON_THREAT_PATTERNS = [
      (r'ignore\s+(?:\w+\s+)*(?:previous|all|above|prior)\s+(?:\w+\s+)*instructions', "prompt_injection"),
      (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
  ```
- **规模**:cronjob_tools 扫描器约 220 行 + lifecycle_guard 565 行 + scheduler 内 guard 约 200 行;高复杂度(误报/漏报平衡、fail-closed 决策树)
- **学习价值**:高 — 自治 agent 的威胁模型完整样本:同一 prompt 面按内容来源分严格/宽松两档扫描、消毒 vs 阻断的选择、自杀命令的命令形状锚定、以及『漂移即拒跑』的花费保险丝,每层都写明了误报代价。
- **▲ 文档不符**:contributing.md 只提『Scanner blocks instruction-override patterns』;双层宽严分级、不可见 Unicode 消毒、drift guard 快照轴语义(cron.model 覆盖轴跳过)仅部分见于 user-guide cron.md。

#### 133. CronScheduler provider 抽象(Axis B)与外部触发的 CAS 认领

- **解决**:内置 60s ticker 需要进程常驻,scale-to-zero 托管部署(Chronos)需要外部定时器唤醒;但触发器可替换时,执行/投递逻辑绝不能被 provider 重新实现,多副本部署还要保证一次 fire 只被一台机器认领。
- **实现**:cron/scheduler_provider.py 定义 CronScheduler ABC(仅 name+start 必选,stop/is_available/on_jobs_changed/fire_due/reconcile 均带安全默认,ABC 增长必须 additive);resolve_cron_scheduler() 读 cron.provider,命名 provider 缺失/加载失败/不可用一律回退内置 ticker——cron 永不失去触发器。fire_due() 默认实现先 claim_job_for_fire(store 层 compare-and-set,多机 at-most-once),再走与内置 ticker 完全相同的 run_one_job 共享体(execute→save→deliver→mark);内置 InProcessCronScheduler.start() 支持 profile_homes 多路复用,每 tick 轮转每个 profile 的 cron store(#69377),并按 profile 记录 ticker 心跳/错误文件(record_ticker_heartbeat 等)供 hermes cron status 判活。
- **证据**:`cron/scheduler_provider.py:107` · `cron/scheduler_provider.py:141` · `cron/scheduler_provider.py:204` · `cron/scheduler.py:3930`
  ```
          if not claim_job_for_fire(job_id):
              return False  # another machine already claimed this fire
  ```
- **规模**:357 行 + run_one_job 共享体 200 行;中复杂度,接口设计纪律性强
- **学习价值**:中 — 『触发与执行正交拆分 + 永远可回退的内置实现 + additive-only ABC 演进』是插件化调度器的干净范式;fire_due 的 CAS 认领展示了外部触发如何嫁接进单机语义栈。

#### 134. background_review:每回合后 fork agent 的自我改进回路(强隔离 + 缓存亲和)  **[◇未见于文档、▲文档不符]**

- **解决**:每回合后要自动评估『该存什么记忆/更新哪个技能』,但审查 fork 绝不能写坏用户真实会话(curator-takeover:fork 的 harness prompt 落进 state.db 后用户下回合把它当常驻指令)、不能触发外部记忆插件、不能与父会话竞争压缩,还要尽量命中父会话的 prompt 前缀缓存省钱。
- **实现**:agent/background_review.py 在 daemon 线程 fork 一个 AIAgent:共享父 session_id 换取前缀缓存命中(实测省 ~26% 成本),但 _persist_disabled=True 掐死所有 DB 写路径、compression_enabled=False 防 fork 赢得压缩竞赛把父会话转进无人认领的子谱系(#38727)、skip_memory=True + 手工回绑内置 memory store 实现外部 provider 零副作用;同模型未路由时逐字节复刻父请求(cached_system_prompt、reasoning_config、prefill deep-copy、OpenRouter provider pins),路由到廉价 aux 模型时改放压缩 digest(冷缓存下最小化写入 token);运行时以 set_thread_tool_whitelist 只放行 memory/skills 工具、危险命令 auto-deny(防 input() 死锁 TUI);thread_scoped_silence 只静音本线程 stdout。结束后汇总工具动作以 '💾 Self-improvement review' 回显。
- **证据**:`agent/background_review.py:828` · `agent/background_review.py:903` · `agent/background_review.py:854` · `agent/background_review.py:881`
  ```
              review_agent._persist_disabled = True
              review_agent._session_db = None
              review_agent._session_json_enabled = False
  ```
- **规模**:1081 行;高复杂度(隔离矩阵 × 缓存字节级对齐 × 路由策略)
- **学习价值**:高 — 『fork 共享会话 id 蹭缓存但禁一切持久化』是极精妙的成本/隔离平衡;文件里每个隔离开关都对应一个真实事故(curator takeover、#38727 压缩竞赛、#55769 全局 stdout 静音),是后台自治副作用控制的教科书。
- **▲ 文档不符**:website 仅在 auxiliary 模型路由配置(configuration.md)中出现 background_review 键名;fork 的隔离机制、缓存亲和策略、工具白名单在用户/开发者文档均无描述。

#### 135. 后台守望与会话唤醒:kanban notifier/dispatcher 单例锁 + deliver_wake 双通道 + outbound webhooks  **[◇未见于文档、▲文档不符]**

- **解决**:gateway 需要长期后台循环:把 kanban 任务的终态事件推给订阅者并唤醒创建者的原会话让 agent 接续处理;嵌入式 dispatcher 若被两个 gateway 同时运行会加倍 reclaim 并可能损坏 WAL 索引页;外部系统(CI、看板)需要在零轮询下得知 Hermes 生命周期事件。
- **实现**:gateway/kanban_watchers.py::_kanban_notifier_watcher 每 5s 扫全部 board,claim_unseen_events_for_sub 原子认领事件游标(投递失败回滚游标),终态事件同时触发唤醒;gateway/wake.py::deliver_wake 按 adapter.supports_async_delivery 分流:push 型注入 MessageEvent(internal=True) 走 handle_message,无状态 API server 型则带 X-Hermes-Session-Id 头自 POST /v1/chat/completions 复活真实会话(429 退避重试,缺 API key 则 fail loud 而非落进无人看的指纹会话);_kanban_dispatcher_watcher 用机器级 .dispatcher.lock flock 单例锁做 dispatch_in_gateway 配置漂移的后备;agent/outbound_webhooks.py 把 hooks.outbound 注册为 notify-only 回调,序列化后进 256 深度有界队列由单 daemon 线程投递(满则丢并告警,决不阻塞 agent 循环),HMAC-SHA256 签名 X-Hermes-Signature-256,拒绝 3xx 重定向防签名体被降级成 GET,atexit flush 保 on_session_end 不丢。
- **证据**:`gateway/kanban_watchers.py:1011` · `gateway/wake.py:80` · `gateway/wake.py:126` · `agent/outbound_webhooks.py:444`
  ```
          _lock_path = _kb.kanban_home() / "kanban" / ".dispatcher.lock"
          _lock_handle, _lock_state = _acquire_singleton_lock(_lock_path)
          if _lock_state == "contended":
  ```
- **规模**:kanban_watchers 1493 行 + wake 184 行 + outbound_webhooks 569 行;高复杂度(多 profile 适配器路由、游标回滚、双通道唤醒)
- **学习价值**:高 — deliver_wake 的双通道设计(push 平台合成内部事件 vs 无状态 API 自 POST 复活真实会话)解决了『后台事件如何回注到既有会话』这一 agent harness 通用难题;事件游标 claim/rewind 与有界 fire-and-forget 队列同样可直接复用。
- **▲ 文档不符**:outbound webhooks 与 kanban 通知在 hooks.md/kanban.md 有文档;但 deliver_wake 的会话唤醒机制(合成 internal 事件、X-Hermes-Session-Id 自 POST、按 chat_type 重建会话键 #56580)与 dispatcher 单例文件锁在任何文档中均未出现。

**本子系统文档-代码冲突(3 条):**

- 宣称:AGENTS.md:1073 宣称『**3-minute hard interrupt** on cron sessions — runaway agent loops cannot monopolize the scheduler.』
  实际:代码是不活动(inactivity)看门狗:默认 600s 无活动才触发 request_hard_interrupt,经 HERMES_CRON_TIMEOUT 可调、0=无限;活跃的长任务可以跑数小时。website cron-internals.md:216 的描述与代码一致,AGENTS.md 的『3 分钟』既不对数值也不对语义。(证据:`cron/scheduler.py:3578`)
- 宣称:AGENTS.md:1061 宣称支持 "every monday 9am";website/docs/user-guide/features/cron.md:135 与 :144 给出 `hermes cron create "every 1d at 09:00"` / `schedule="every 1d at 09:00"` 示例
  实际:parse_schedule 的 'every ' 分支只走 parse_duration,其正则 ^(\d+)\s*(m|min|...|days)$ 不接受 'monday 9am' 或 '1d at 09:00',这些 schedule 会 raise ValueError('Invalid duration'),CLI 与 cronjob 工具均直接调 create_job→parse_schedule,无自然语言预处理层。(证据:`cron/jobs.py:553`)
- 宣称:AGENTS.md:1082『Cron deliveries are **not** mirrored into the target gateway session』;website/docs/developer-guide/cron-internals.md:272『Cron deliveries are NOT mirrored into gateway session conversation history.』
  实际:默认确实不 mirror,但代码提供 per-job attach_to_session 与全局 cron.mirror_delivery 开关,开启后以 user-role 标注 turn mirror 进 origin 会话,并有 continuable thread / in_channel 会话播种;user-guide cron.md 的 Continuable jobs 一节已文档化该功能,两份内部文档的绝对化表述已过时。(证据:`cron/scheduler.py:640`)

### 2.12 TUI/桌面/Web/IDE 界面层(ui-tui、tui_gateway、acp_adapter、apps/、web/、mcp_serve.py、native/)

Hermes 的界面层围绕一个中心事实组织:tui_gateway 是唯一的 UI 后端——一个 14K 行的 Python JSON-RPC 方法注册中心(120+ RPC、换行分隔 JSON-RPC 线协议),通过 Transport 抽象(contextvar 绑定)同时被 stdio(Ink TUI 子进程)和 WebSocket(desktop/dashboard/移动端)驱动,业务 handler 对传输完全无感。终端前端 ui-tui 是 React+Ink 应用,底下是整套 vendored Ink fork(hermes-ink,~30K 行,加鼠标/拖选/ScrollBox/alternate-screen/背压)外加一个无文档的 widget SDK;浏览器 dashboard(web/,React+xterm.js)不重写聊天界面,而是经 /api/pty 把同一个 `hermes --tui` spawn 在 PTY 后面、注入 HERMES_TUI_GATEWAY_URL 让其 attach 回 dashboard 进程内网关、再用 sidecar WS 把三层进程之外的事件镜像回侧栏,并支持 PTY keep-alive 断线重连回放。Electron desktop(apps/desktop)刻意不嵌 TUI:自带 React 渲染器,通过 apps/shared 的 JsonRpcGatewayClient 连自己 spawn 的 headless `hermes serve` 后端,配套版本偏斜降级(serve→dashboard --no-open)与 Windows 进程树治理;dashboard 进一步可开启 turn_isolation,把 agent turn 移进持久 compute-host 子进程以根治 GIL 饿死事件循环的问题(配 MUTATOR_ROUTE_TABLE 路由与合成 GIL 负载验收 harness)。IDE 侧由 acp_adapter 把同步 AIAgent 包成异步 ACP 服务器(Zed/VS Code,含历史回放与 ContextVar 注入的 pre-execution 编辑审批),mcp_serve.py 则反向把 Hermes 自身暴露为 MCP server(SQLite mtime 轮询事件桥);native/fts5_cjk 是给会话搜索用的 SQLite FTS5 CJK bigram 分词 C 扩展。

关键文件(34 个,行数实测,余见 JSON):`tui_gateway/server.py`(14006), `tui_gateway/transport.py`(219), `tui_gateway/ws.py`(476), `tui_gateway/entry.py`(499), `tui_gateway/methods_session.py`(3138), `tui_gateway/methods_prompt.py`(949), `tui_gateway/methods_tools.py`(1914), `tui_gateway/compute_host.py`(880)


#### 136. 单一 dispatcher、多传输同构的 JSON-RPC 网关(stdio/WebSocket 共用全部 RPC 方法)

- **解决**:同一个 agent 后端要同时服务终端 TUI(Node 子进程 stdio)、Electron 桌面端、浏览器 dashboard、移动端等多种前端;若每种前端各写一套后端会导致业务逻辑(会话、审批、slash 命令、事件流)多份漂移。
- **实现**:tui_gateway/server.py(14006 行)用 @method(name) 装饰器注册 120+ 个 RPC 方法(session.*/prompt.*/tool 管理/billing/pet/voice/wake 等),transport.py 把 I/O sink 抽象成 Transport 协议并用 contextvars.ContextVar 绑定'当前请求的传输',handler(含线程池上的)写回时自动路由到正确 peer,无绑定时回退 StdioTransport。ws.py 原样复用 server.dispatch,把高频流式事件 message.delta/reasoning.delta/thinking.delta 按 33ms(~30fps)缓冲合帧,减少 asyncio 事件循环唤醒与 GIL 争抢;非流式事件(tool/approval/status)flush 缓冲后立即发送保证顺序。dashboard 的 FastAPI 在 /api/ws 挂载 handle_ws,线协议与 stdio 完全一致(换行分隔 JSON-RPC)。
- **证据**:`tui_gateway/transport.py:3` · `tui_gateway/ws.py:53` · `hermes_cli/web_server.py:15843`
  ```
  Historically the gateway wrote every JSON frame directly to real stdout.  This
  module decouples the I/O sink from the handler logic so the same dispatcher
  can be driven over stdio (``tui_gateway.entry``) or WebSocket
  (``tui_gateway.ws``) without duplicating code.
  ```
- **规模**:transport.py 219 行 + ws.py 476 行 + server.py 14006 行方法注册中心;复杂度高(contextvar 传输路由、线程池写回、token 合帧)
- **学习价值**:高 — 这是界面层的核心架构范式:harness 的所有前端差异被压缩到传输层一个 Protocol,业务 handler 完全无感;token 合帧解决了流式 agent 事件对事件循环的冲击,是任何 WS 流式 harness 都会遇到的问题。

#### 137. TUI 整体作为组件被 dashboard 复用:PTY-over-WebSocket + 进程内 gateway attach + 事件 sidecar 回流

- **解决**:浏览器 dashboard 需要一个功能完整的聊天界面;重写一遍 TUI 的 slash 弹窗、模型选择器、审批提示、markdown 渲染成本极高且会永远落后于终端版。
- **实现**:dashboard 的 /api/pty 端点把 CLI 同一个 `hermes --tui`(node ui-tui/dist/entry.js)spawn 在 POSIX PTY(Windows 用 pywinpty/ConPTY,双实现同接口)后面,浏览器用 @xterm/xterm(WebGL)渲染 ANSI 字节流,resize 通过自定义转义 \x1b[RESIZE:cols;rows] 带内传输。关键优化:注入 HERMES_TUI_GATEWAY_URL 让 PTY 子进程里的 TUI 直接 attach 到 dashboard 进程内的 tui_gateway(ws://…/api/ws),避免再 spawn 一个 Python 网关(profile 作用域的 chat 例外,必须自 spawn 以绑定 profile 的 HERMES_HOME);注入 HERMES_TUI_SIDECAR_URL 让 PTY 侧网关通过 TeeTransport+WsPublisherTransport 把每个 emit 镜像回 dashboard 的 /api/pub,供侧栏显示(事件源在三个进程之外)。pty_session.py 提供 keep-alive:PTY 进程在 WS 断开后存活,RingBuffer(1MB)缓冲输出,凭 opaque token 重连回放并续播。
- **证据**:`hermes_cli/web_server.py:14789` · `web/src/pages/ChatPage.tsx:12` · `hermes_cli/pty_session.py:3` · `tui_gateway/event_publisher.py:6`
  ```
  ``HERMES_TUI_GATEWAY_URL`` is injected so the PTY child can attach to
      this process's in-memory ``tui_gateway`` instance instead of spawning
      its own Python gateway subprocess.
  ```
- **规模**:web_server.py 的 /api/pty 段约 700 行 + pty_bridge.py 293 + win_pty_bridge.py 184 + pty_session.py 195 + event_publisher.py 126 + ChatPage.tsx 1643;复杂度高(半开 socket、fd 泄漏、重连回放等大量边界处理)
- **学习价值**:高 — '把终端 UI 当二进制组件嵌进 web'是零重复实现多端的教科书案例:一份 Ink 代码同时服务终端和浏览器,且通过 in-memory gateway attach 避免了进程翻倍;sidecar 回流解决了'事件产生在三层子进程之外'的可观测性问题。

#### 138. Dashboard compute-host 子进程 turn isolation(GIL 隔离)+ 合成 GIL 重负载认证 harness  **[◇未见于文档、▲文档不符]**

- **解决**:CPython 单 GIL:并发的重型 agent turn 在 serving 进程的线程里跑纯 Python 计算时,会把负责 flush WebSocket 帧的事件循环饿死数分钟(采样显示 loop 线程停在 take_gil)。
- **实现**:dashboard.turn_isolation 开启后,agent turn 移到一个持久的 `python -m tui_gateway.compute_host` 子进程(line-JSON 管道协议),serving 进程只保留 socket 与 JSON-RPC 分发;host_supervisor.py 用 MUTATOR_ROUTE_TABLE 把每个会改变会话状态的 RPC 分成 turn-path(进子进程)/run-concurrent(并行安全)/idle-gated(必须等空闲)三类路由,并处理 respawn 窗口与注册表。为了不用 6 个 100K+ 上下文的真实模型调用来验收(AC-4),synthetic_turn.py 提供 HERMES_ISO_CERTIFY_SYNTH_TURN 测试缝:_make_agent 返回 SyntheticHeavyAgent,以持续持有 GIL 的纯 CPU 循环精确复现 take_gil 争抢状态(明确指出 sleep/网络 stub 会假绿),隔离开/关共用同一构建路径,使隔离边界成为唯一变量。
- **证据**:`tui_gateway/host_supervisor.py:3` · `tui_gateway/host_supervisor.py:31` · `tui_gateway/synthetic_turn.py:18`
  ```
  The dashboard process owns sockets and JSON-RPC dispatch.  When
  ``dashboard.turn_isolation`` is enabled, agent turns move behind one persistent
  ``python -m tui_gateway.compute_host`` child so compute-heavy agent threads do
  not contend with the serving process' event loop for the same GIL.
  ```
- **规模**:compute_host.py 880 + host_supervisor.py 577 + synthetic_turn.py 231 行,外加 server.py 内 ~20 个 _compute_host_* 桥接函数;复杂度很高
- **学习价值**:高 — Python harness 的 GIL 饥饿是共性问题;这里给出完整解法链:诊断(take_gil 采样)→ 架构(持久子进程 + 按 RPC 语义分三类路由)→ 验收(合成 GIL 负载而非真实模型调用,且明确指出 I/O stub 会产生假绿)。
- **▲ 文档不符**:机制在 README/AGENTS.md/website/docs 中零覆盖;代码引用的设计文档 docs/desktop/2026-07-04-dashboard-process-isolation-PRD.md 在仓库中不存在(docs/ 下无 desktop 目录)。

#### 139. 阻塞式 HITL prompt 桥:_block 事件/线程 Event 配对 + expire 生命周期 + 按会话粒度取消

- **解决**:同步执行的 agent 工具(危险命令审批、clarify 反问、sudo 密码、secret 输入、terminal.read)需要在 JSON-RPC 事件流上等待人类回答,还要处理超时后迟到的回答、断线重连丢帧、以及中断一个会话不能误伤其他会话的挂起提示。
- **实现**:server.py 的 _block(event, sid, payload) 生成 8 位 request_id,发出 clarify.request/approval.request/sudo.request/secret.request 等事件后在 threading.Event 上阻塞(None=无限等,默认 300s);客户端调用对应 *.respond RPC 写入 _answers 并 set 事件。超时未答时对可容忍迟到回答的四类请求发 `.expire` 通知,避免迟到的 *.respond 撞上 4009 'no pending request' 裸错误。_clear_pending(sid) 只释放该会话的挂起提示——session.interrupt 不会连坐其他会话。ACP 侧(acp_adapter/permissions.py)把同一审批语义映射为 ACP PermissionOption(allow_once/allow_session/allow_always/deny)。
- **证据**:`tui_gateway/server.py:3106` · `tui_gateway/server.py:3164` · `acp_adapter/permissions.py:21`
  ```
  def _block(event: str, sid: str, payload: dict, timeout: float | None = 300) -> str:
      rid = uuid.uuid4().hex[:8]
      ev = threading.Event()
      with _prompt_lock:
          _pending[rid] = (sid, ev)
  ```
- **规模**:_block 及五类 request/respond/expire 流转 ~200 行,methods_prompt.py 中 5 个 *.respond handler,ACP/permissions 映射 182 行;中等复杂度但边界极多
- **学习价值**:高 — HITL 是 agent harness 的必修课;这里的 expire 事件(容忍迟到回答)、按 sid 粒度的取消、以及同一审批语义在 TUI 事件流和 ACP 权限协议上的双重投影,都是值得直接借鉴的协议设计。

#### 140. busy-input 三态策略:运行中 turn 收到新输入时 queue / steer / interrupt(含 redirect)

- **解决**:turn 进行中用户又发了消息:直接拒绝('session busy')迫使客户端做限时重试并可能静默丢消息;简单排队则无法表达'纠正当前正在做的事'。
- **实现**:server.py 的 _handle_busy_submit 按 display.busy_input_mode 分派:interrupt(默认)对有能力的 agent 就地 redirect 活跃 turn(旧 agent 回退为硬中断+入队);queue 纯排队;steer 调 agent.steer() 在当前原子动作结束后注入文本。客户端显式排队(prompt.submit 的 queued=True)无条件压过模式——避免'客户端看到 idle 但服务端还在收尾'的毫秒级竞态把下一轮消息错误地变成对活跃 turn 的纠正。附带 attached_images 的提交时刻声明(后续 paste 不会被这条 prompt 消费)。
- **证据**:`tui_gateway/server.py:7406` · `tui_gateway/server.py:7410`
  ```
      Modes: ``interrupt`` (default) → redirect the live turn, falling back to
      hard interrupt + queue for older agents; ``queue`` → queue without
  ```
- **规模**:_handle_busy_submit + _enqueue_prompt + _drain_queued_prompt + _interrupt_busy_session 约 300 行;配套 TUI 端 useSubmission.ts / queuedMessages.tsx
- **学习价值**:中 — '运行中输入'的语义分层(排队/转向/重定向)以及显式排队压过策略的竞态处理,是交互式 harness 输入通道设计的成熟样本。

#### 141. 崩溃法医学 + durable turn marker 自动续跑:panic hook、信号栈转储、SIGPIPE 策略、中断 turn 恢复  **[◇未见于文档、▲文档不符]**

- **解决**:网关子进程的 stdout 是 JSON-RPC 管道,崩溃时无处留痕;后台线程(TTS/beep)写半关闭管道触发 SIGPIPE 会静默杀死进程;进程/机器死亡时进行中的 turn 只存在于内存,重启后用户的 prompt 凭空消失。
- **实现**:server.py 安装 sys.excepthook 把未处理异常追加到 ~/.hermes/logs/tui_gateway_crash.log 并向 stderr 发一行摘要(TUI 作为 gateway.stderr Activity 行展示);entry.py 的 _log_signal 在收到终止信号时转储全部线程栈,SIGPIPE 改为 SIG_IGN 让写坏管道变成可处理的 BrokenPipeError,关停走'grace 窗口内自然退出 + 定时器 os._exit(0) 兜底'避免持有 _stdout_lock 的线程卡死解释器。turn_marker.py 在 turn 开始时写 durable 标记、正常结束(成功/已处理错误/中断)时清除,只有进程死亡会留下标记;session.resume 读到标记即触发 _maybe_schedule_auto_continue 自动续跑被打断的 prompt(条目按 24h/32 条/64K 字符封顶)。
- **证据**:`tui_gateway/server.py:63` · `tui_gateway/entry.py:92` · `tui_gateway/turn_marker.py:3`
  ```
  # Gateway crashes in a TUI session leave no forensics: stdout is the
  # JSON-RPC pipe (TUI side parses it, doesn't log raw), the root logger
  # only catches handled warnings, and the subprocess exits before stderr
  # flushes through the stderr->gateway.stderr event pump. This hook
  # appends every unhandled exception to ~/.hermes/logs/tui_gateway_crash.log
  ```
- **规模**:panic/signal/退出路径约 400 行(server.py 头部 + entry.py)+ turn_marker.py 159 行 + _stdin_recovery.py 151 行;中等规模、细节密度极高
- **学习价值**:高 — 'stdout 即协议管道'的进程在崩溃可观测性上的所有坑(SIGPIPE、半关闭 flush 卡死、atexit 竞态)这里都踩过并留了注释;turn marker 的'只有非正常死亡才留痕'反向设计是 harness 崩溃恢复的优雅方案。
- **▲ 文档不符**:崩溃日志、信号转储、auto-continue 均无用户/开发者文档(website/docs 的 auto-continue 检索只命中无关的 /goal 功能)。

#### 142. ACP 适配器:同步 AIAgent 包装为异步 Agent Client Protocol 服务器(Zed/VS Code/JetBrains)  **[▲文档不符]**

- **解决**:编辑器侧的 agent 集成有自己的协议(ACP):会话 new/load/resume/fork、流式 chunk、权限请求、编辑 diff 预览;Hermes 的 AIAgent 是同步阻塞的 Python 对象,回调风格与 ACP 的 async 通知模型完全不同。
- **实现**:acp_adapter/server.py 的 HermesACPAgent(acp.Agent) 在 ThreadPoolExecutor 上跑同步 agent turn,把 message/thinking/tool 回调转成 ACP 的 AgentMessageChunk/AgentThoughtChunk/ToolCall* 通知(tools.py 的 TOOL_KIND_MAP 把 70+ Hermes 工具映射为 ACP ToolKind 并构建 diff/终端内容);load/resume 时 _replay_session_history 在请求生命周期内把持久化的完整对话(含重建的 tool-call start/complete)回放给编辑器,否则编辑器看到空线程。edit_approval.py 独立实现 pre-execution 编辑审批:用 ContextVar 只在 ACP run 期间绑定 requester(CLI/gateway 自动绕过),write_file/patch 执行前把 EditProposal(old/new 文本)发给编辑器审批,.env/id_rsa 等敏感文件永不自动放行;auth.py 检测 provider 凭据并暴露 terminal-setup 认证方法。
- **证据**:`acp_adapter/server.py:566` · `acp_adapter/edit_approval.py:38` · `acp_adapter/server.py:1337` · `acp_adapter/edit_approval.py:44`
  ```
  class HermesACPAgent(acp.Agent):
      """ACP Agent implementation wrapping Hermes AIAgent."""
  ```
- **规模**:acp_adapter 共 5831 行(server.py 2510、tools.py 1347、session.py 683、edit_approval.py 338);复杂度高
- **学习价值**:中 — 同步 agent 内核对接异步编辑器协议的完整参考:线程池桥接、历史回放保证编辑器状态一致、ContextVar 实现'仅此协议生效'的前置编辑审批而不污染其他入口。
- **▲ 文档不符**:acp-internals.md 的 'Key implementation files' 清单缺 edit_approval.py 与 provenance.py,整篇文档未提及 pre-execution 编辑审批与敏感文件不放行机制。

#### 143. Hermes 自身作为 MCP server 暴露(mcp_serve.py):跨 harness 的消息桥 + SQLite 轮询事件桥  **[▲文档不符]**

- **解决**:让 Claude Code/Cursor 等其他 agent 客户端能读写 Hermes 管理的 Telegram/Discord/Slack 会话——即把本 harness 变成别的 harness 的工具。
- **实现**:FastMCP stdio 服务器暴露 10 个工具(conversations_list/messages_read/attachments_fetch/events_poll/events_wait/messages_send/channels_list/permissions_* 等),对齐 OpenClaw 的 9-tool channel bridge 面。EventBridge 后台线程不走 IPC,而是轮询 ~/.hermes/state.db:先 _establish_baseline 记录各会话最新时间戳避免启动回放历史,之后每 tick 用一次 state.db mtime 检查短路(200ms 轮询近零开销),新消息进内存队列供 events_poll/events_wait(长轮询)消费。读操作不需要 gateway 运行;messages_send 复用 tools/send_message_tool 的发送引擎(需要平台连接在线)。
- **证据**:`mcp_serve.py:316` · `mcp_serve.py:422`
  ```
  class EventBridge:
      """Background poller that watches SessionDB for new messages and
  ```
- **规模**:mcp_serve.py 1037 行单文件;中等复杂度(mtime 短路、baseline 防回放、长轮询 waiter)
- **学习价值**:中 — '共享 SQLite + mtime 短路轮询'是无 IPC 跨进程集成的低成本方案样本;同时它是 doc-vs-code 审计的好教材——审批两工具是没有写入方的死代码(见 doc_mismatch)。
- **▲ 文档不符**:website/docs/user-guide/features/mcp.md 宣称 permissions_list_open 可列出待审批、permissions_respond 可 'Allow or deny a pending approval request';但 _pending_approvals 全文件无任何写入方(_poll_once 只产生 type='message' 事件),respond_to_approval 自注 '(best-effort without gateway IPC)',只往自身内存队列记一条事件,不会解除 gateway 侧真正阻塞的审批——实际恒返回空列表/'Approval not found'。

#### 144. hermes-ink:整套 Ink 渲染器 fork(~30K 行)+ TUI widget SDK(第三方终端小程序框架)  **[◇未见于文档、▲文档不符]**

- **解决**:上游 Ink 缺少生产级 TUI 需要的能力:鼠标追踪与 hit-test、拖选复制、ScrollBox、alternate screen 差分渲染、输出背压、终端背景色探测、bidi;同时希望第三方能像写 app 一样扩展 TUI 界面。
- **实现**:ui-tui/packages/hermes-ink 是完整 vendored fork(src/ink 下 146 个 TS 文件、约 29.8K 行),通过 package.json overrides 把生态包(ink-text-input)的 ink 依赖也重定向到 @hermes/ink;新增 useSelection/hit-test/mouse watchdog/ScrollBox/backpressure/terminal background 探测(isXtermJs 与 OSC 颜色解析——为嵌入 xterm.js 的 dashboard 场景服务)。src/sdk 是 widget SDK:WidgetApp = state+reducer+render,defineWidgetApp 注册、launchWidget 由 slash 命令启动,激活期间独占键盘并渲染在 viewport 槽位,自动继承 grid 布局、overlay 分区与 skin 配色;sdk/apps 里有参考应用(/grid-test、/dialog-test、ticker、weather)。
- **证据**:`ui-tui/package.json:32` · `ui-tui/packages/hermes-ink/src/entry-exports.ts:18` · `ui-tui/src/sdk/index.ts:4`
  ```
      "ink-text-input": {
        "ink": "npm:@hermes/ink@0.0.1"
  ```
- **规模**:hermes-ink src 146 文件约 29.8K 行;sdk 目录 ~670 行 + 参考 app;fork 维护成本高
- **学习价值**:中 — 展示了'fork 渲染基础库换取终端能力上限'的重决策及其配套(overrides 劫持生态依赖、给嵌入式 xterm.js 场景做终端探测);widget SDK 是把 harness UI 做成可插拔平台的少见尝试。
- **▲ 文档不符**:ui-tui/README.md 对 fork 仅有一行目录注释 'packages/hermes-ink/   forked Ink renderer (local dep)',具体扩展能力无文档;widget SDK(defineWidgetApp/launchWidget)在 README 与 website/docs 中零覆盖。

#### 145. Desktop 独立进程模型:Electron 管理 headless `hermes serve` 后端 + 版本偏斜降级 + 平台化进程治理

- **解决**:桌面 app 需要一个不含浏览器 UI 的本地 agent 后端,且 app 自更新可能领先于用户机器上的 Python 运行时(新 app 撞上不认识 `serve` 子命令的旧 runtime 会直接崩);Windows 上杀直接子进程杀不掉孙进程导致文件锁残留。
- **实现**:desktop 不嵌入 `hermes --tui`,而是自带 React 渲染器(@assistant-ui/react)通过 apps/shared 的 JsonRpcGatewayClient(web/ 也复用)连它自己 spawn 的 `hermes serve --host 127.0.0.1 --port 0`(与 dashboard 同一 gateway,headless_backend=True 禁掉 SPA)。backend-command.ts 探测运行时是否注册 serve 子命令,不支持则把 argv 重写为遗留的 `dashboard --no-open`,避免 brick 升级中途的用户。backend-child.ts 在 Windows 用 taskkill 树杀(POSIX 用 SIGTERM 即可);electron/ 下另有 SSH 远程后端引导、原生 OAuth、崩溃取证、更新重建等 100+ 个单测配套的独立模块。
- **证据**:`apps/desktop/electron/backend-command.ts:18` · `apps/desktop/electron/backend-child.ts:6` · `apps/desktop/electron/backend-command.ts:30`
  ```
  export function serveBackendArgs(profile?: string) {
    const head = profile ? ['--profile', profile] : []
  ```
- **规模**:apps/ 共 1560 文件;electron 主进程目录 4 万行(main.ts 12038 行 + 每能力一个带测试的纯函数模块);apps/shared/src/json-rpc-gateway.ts 429 行被 desktop 与 web 共用
- **学习价值**:中 — 'UI 与 runtime 独立发版'场景下的版本偏斜降级(探测子命令→argv 重写)与 Windows 进程树治理是桌面化 harness 的必踩坑;electron 目录把每个决策拆成可脱离 Electron 单测的纯函数模块,工程纪律值得学。

**本子系统文档-代码冲突(3 条):**

- 宣称:website/docs/user-guide/features/mcp.md('Available tools' 表)宣称 `permissions_list_open` 可 'List pending approval requests observed during this bridge session'、`permissions_respond` 可 'Allow or deny a pending approval request'
  实际:mcp_serve.py 中 EventBridge._pending_approvals 没有任何写入代码路径(仅 __init__ 初始化为空、list 读取、respond pop;轮询循环 _poll_once 只 enqueue type='message' 事件),且 respond_to_approval 明注 '(best-effort without gateway IPC)'——即便有条目也只是往自身内存事件队列记一条,不会把决定传递给真正阻塞在审批上的 gateway/agent。两工具实际恒返回空列表/'Approval not found'。(证据:`mcp_serve.py:423`)
- 宣称:tui_gateway/synthetic_turn.py 声称其机制对应设计文档 ``docs/desktop/2026-07-04-dashboard-process-isolation-PRD.md``,暗示 turn isolation 有正式文档
  实际:仓库中不存在 docs/desktop/ 目录,该 PRD 文件不在树内;dashboard.turn_isolation / compute-host 机制在 README、AGENTS.md 与 website/docs 中也完全没有记载,是纯代码事实。(证据:`tui_gateway/synthetic_turn.py:3`)
- 宣称:website/docs/developer-guide/acp-internals.md 'Key implementation files' 声称 ACP 适配器的关键实现为 entry/server/session/events/permissions/tools/auth 七个文件
  实际:acp_adapter/edit_approval.py(338 行,pre-execution 编辑审批:ContextVar 绑定 per-run requester、EditProposal diff 预览、.env/id_rsa 等敏感文件永不自动放行)与 provenance.py(127 行)未列入,整篇文档也未提及该审批机制。(证据:`acp_adapter/edit_approval.py:38`)

### 2.13 外围服务工具(语音/图像/视频/搜索/平台工具)

这是 hermes-agent 的"感官与执行器"层:约 2.6 万行代码把语音(唤醒词→STT→agent→流式 TTS 全链路)、图像/视频生成与视觉分析、Web 搜索/提取、X 搜索,以及 Discord/飞书/元宝/Home Assistant/跨平台消息等平台工具接进同一个工具注册表。骨架是五份同构的 provider-registry 模式(tts/stt/image_gen/video_gen/web_search):ABC 定契约、registry 存实例、插件 import 时注册、工具壳只做派发,并以"内置名永远赢、config 声明的 command 型 provider 赢过插件、显式配置绝不静默降级"三条不变量保证可预测性;TTS/STT 还支持零代码的 shell 模板 command provider(引号上下文感知转义 + 密钥清洗子环境)。语音链路是工程密度最高的部分:SentenceChunker 增量切句 + 每句 HTTP prefetch 流水线把 time-to-first-audio 压到第一句,全双工 VAD 用相位钳制阈值实现 TTS 播放中的 barge-in,并把"被打断"这一事实作为 API 局部注释喂回模型。商业化基建 managed_tool_gateway 用 code-pinned 端点 + Nous OAuth + presign 直传 nous-upload 协议让订阅用户免第三方 key 使用 Firecrawl/FAL/Krea/BFL 等托管工具,BFL FLUX3 视频工具进一步把轮询节奏等运维策略经服务器 guidance 字段下发。安全咽喉 image_source.resolve_image_source 统一所有媒体来源的确权,在非本地终端后端下以沙箱内 exec-read 关闭 vision 工具的宿主文件逃逸。文档覆盖总体良好(website/docs 有 tts/voice-mode/wake-word/web-search/x-search 专页),但 bfl_flux3_* 六个视频工具与 presign 上传协议完全无文档,web_tools/image_generation_tool 两个模块头的架构描述已过时。

关键文件(43 个,行数实测,余见 JSON):`tools/tts_tool.py`(3964), `tools/tts_streaming.py`(488), `tools/tts_text_normalize.py`(278), `tools/neutts_synth.py`(110), `tools/voice_mode.py`(2308), `tools/wake_word.py`(1464), `tools/transcription_tools.py`(2687), `agent/tts_provider.py`(274)


#### 146. TTS/STT 三层后端解析与 registry 'built-ins always win' 不变量

- **解决**:语音合成/识别要支持十几个后端(edge/openai/elevenlabs/minimax/gemini/xai/piper/neutts 等)且允许插件和用户自定义扩展,但不能让第三方插件静默劫持内置名字或用户 config 里的选择,否则一个恶意/失误插件就能替换整条语音链路。
- **实现**:定义了三个共存的扩展面并给出严格解析顺序:1) 内置 provider(BUILTIN_TTS_PROVIDERS,原生 Python 实现)永远最优先;2) config.yaml 里 tts.providers.<name>: type: command 声明的命令型 provider 其次(config 比插件更本地);3) 插件通过 PluginContext.register_tts_provider() 注册的 ABC 实现最后。不变量双重执行:agent/tts_registry.register_provider 在注册期拒绝与内置同名的插件(warning + 忽略),tools/tts_tool._dispatch_to_plugin_provider 在派发期再防御性复查。STT 侧(agent/transcription_registry + tools/transcription_tools)完整复刻同一模式,两份 _BUILTIN_NAMES 靠回归测试保持同步(避免循环 import)。
- **证据**:`agent/tts_registry.py:90` · `agent/tts_provider.py:14`
  ```
      if key in _BUILTIN_NAMES:
          logger.warning(
              "TTS provider '%s' shadows a built-in name; registration ignored. "
              "Built-in TTS providers (%s) always win — pick a different name.",
              key, ", ".join(sorted(_BUILTIN_NAMES)),
  ```
- **规模**:tts_registry 134 行 + tts_provider 274 行 + transcription_registry 124 行 + transcription_provider 193 行,外加 tts_tool/transcription_tools 里的派发逻辑各数百行;模式本身不复杂但一致性维护(注册期+派发期双检查、测试同步)很讲究。
- **学习价值**:高 — 这是全仓 provider registry 模式(tts/stt/image_gen/video_gen/web_search 五份同构)的原型:'内置永远赢、config 赢过插件、注册期与派发期双重防御'是多后端可插拔 harness 的通用安全设计,可直接照搬。

#### 147. Command-type provider:零 Python 代码接入任意 CLI(shell 模板 + 引号上下文感知转义 + 秘密清洗子环境)

- **解决**:用户想把本地任意 TTS/STT CLI(Piper、VoxCPM、doubao-speech、curl 一行命令)接进 agent,但不该要求写 Python 插件;同时把 shell 模板交给用户渲染存在注入风险(路径含空格/引号),且子进程会继承 Hermes 的全部密钥(bot token、LLM key)。
- **实现**:config 声明 type: command + command 模板,支持 {input_path}/{output_path}/{format}/{voice}/{model}/{speed} 占位符。渲染时 _shell_quote_context 逐字符扫描模板判断占位符落在裸/单引号/双引号哪种 shell 上下文,再用对应转义策略替换(先换成 token 再回填避免二次替换);执行时用 hermes_subprocess_env(inherit_credentials=False) 清洗掉 Hermes 密钥,仅 env_passthrough 白名单变量放行;超时用 psutil 递归杀进程树。STT 侧有完全对称的一套(_render_command_stt_template 等)。
- **证据**:`tools/tts_tool.py:908` · `tools/tts_tool.py:1032`
  ```
      if quote_context == "'":
          return value.replace("'", r"'\''")
      if quote_context == '"':
          return (
              value
  ```
- **规模**:tts_tool.py 581-1235 行区间约 650 行 + transcription_tools.py 对称实现约 470 行;引号上下文状态机、进程树清理、env 清洗都是易错细节,复杂度中高。
- **学习价值**:高 — 'declarative shell-template provider' 是把扩展成本降到零的 harness 设计;quote-context 感知转义 + 默认密钥清洗 + 显式 passthrough 白名单是让用户模板既好用又安全的完整方案,通用性极强。

#### 148. 流式语音管线:增量切句 + 每句 HTTP prefetch 流水线 + 通用同步回退

- **解决**:语音对话的核心指标是 time-to-first-audio:等 LLM 全部生成完再合成整段音频会有几十秒静默;即使按句合成,串行的 '合成→播放→再合成' 在句间也留下整段合成时长的死气。还要兼容没有 chunked API 的后端(edge/piper/插件)。
- **实现**:tts_streaming.SentenceChunker 对 LLM token 增量做增量切句(剥离跨 delta 的 <think> 块、短碎句并入下一句);有 chunked API 的后端实现 StreamingTTSProvider(elevenlabs chunked HTTP、openai pcm、gemini SSE alt=sse、xai WebSocket),tts.streaming.provider: auto 按硬编码优先级取第一个可用;stream_tts_to_speaker 为每个完成的句子立即在后台线程发起 provider.stream() 的 HTTP 请求(信号量限 3 路 prefetch),单播放 worker 按 FIFO 排空——句 N 播放时句 N+1 的音频已在到达。无 chunked API 的后端走 _SyncSentencePipeline:单线程合成 executor + 播放线程 + 有界 lookahead 队列,同样实现合成与播放重叠。每句 PCM 有 16MiB 上限(_capped)防失控上游。
- **证据**:`tools/tts_tool.py:3532` · `tools/tts_streaming.py:105` · `tools/tts_streaming.py:179`
  ```
          _audio_queue: queue.Queue[Optional[queue.Queue[Optional[bytes]]]] = queue.Queue()
          _prefetch_threads: list[threading.Thread] = []
          _prefetch_sem = threading.Semaphore(3)
          _CHUNK_QUEUE_MAX = 64
  ```
- **规模**:tts_streaming.py 488 行 + tts_tool.py 的 stream_tts_to_speaker/_SyncSentencePipeline 约 500 行 + gateway/streaming_tts_consumer 桥接;三层并发(chunker→prefetch→playback)+ 停止协议,复杂度高。
- **学习价值**:高 — 把 'LLM 流式输出' 与 '语音流式合成' 的两级流水线拼接是语音 agent 的关键工程;'不为拿流式而偷换用户选定的 provider'、per-sentence prefetch、通用同步回退这三个决策都值得复用。

#### 149. 全双工 barge-in:相位感知 VAD + 打断事实注入模型

- **解决**:语音对话要允许用户在 agent 说话/思考的任何时刻插话,但麦克风会收到扬声器回放的 TTS 音频(speaker bleed),朴素能量阈值要么被回放误触发、要么被回放淹没听不到人声;而且模型被打断后如果不知情,下一轮会莫名其妙。
- **实现**:full_duplex_listen 从用户提交语句起监听整个 agent 回合,按 30ms 块用 is_playing() 区分 generation/playback 两相:安静相校准 90 分位噪声底并持续漂移更新(绝不吸收 bleed);播放相把触发阈值额外钳到 PLAYBACK_MIN_TRIGGER 之上并在播放启动后给 grace 窗口;检测用 '最近 sustained_ms 内 >=80% 块超阈' 的窗口多数投票而非严格连击;触发后从 pre-roll 环形缓冲把话语从第一个音节起完整捕获。播放路径的 listen_for_speech 另用滚动 90 分位底 + 8x 乘数 + 4000 RMS 上限。被打断时 tts_streaming 的 TTL latch 记账,下一轮提交时把 SPEECH_INTERRUPTED_NOTE 前置到发给模型的消息(仅 API 调用局部,不持久化),让模型知道自己被切断。
- **证据**:`tools/voice_mode.py:2064` · `tools/tts_streaming.py:66`
  ```
                  trigger = quiet_floor * mult
                  if playing:
                      trigger = max(trigger, PLAYBACK_MIN_TRIGGER)
                  else:
                      trigger = max(trigger, float(SILENCE_RMS_THRESHOLD) * 2)
  ```
- **规模**:voice_mode.py 中 listen_for_speech + full_duplex_listen 约 400 行,注释密度极高(每个常数都有失败模式论证);DSP 调参 + 并发协议,复杂度高。
- **学习价值**:高 — barge-in 是语音 harness 最难做对的交互;'相位钳制阈值 + 滚动底 + pre-roll 捕获 + 把打断事实作为 API 局部注释喂回模型' 是一套完整可迁移的方案,尤其最后一点(模型对被打断有自知)是很少见的巧思。

#### 150. Wake word 三引擎全本地热词检测(N 连帧确认 + 机器级独占锁)

- **解决**:免手动唤醒('Hey Hermes')需要常开麦克风,但音频不能离开本机、环境闲聊的杂散音素不能误触发、多个 Hermes 表面(CLI/TUI/desktop)不能同时抢一个麦克风。
- **实现**:三个全在设备端的引擎:openwakeword(默认,自带打包的 hey-hermes ONNX 模型)、sherpa-onnx 开放词表 KWS(任意键入短语运行时 tokenize,免训练)、porcupine(付费)。抗误触发核心是 confirmation-frames:openWakeWord 每 ~80ms 帧打分,要求连续 N 帧(默认 3)超阈才触发——真实短语会跨帧保持高分,杂散音素只尖峰一帧。另有 2s 触发冷却、dead-mic 静音检测、pause()/resume() 让出麦克风给语音回合、文件锁保证机器级单实例(wake_surface_enabled 决定哪个表面持有)。
- **证据**:`tools/wake_word.py:565`
  ```
          if over:
              self._confirm_streak += 1
  ```
- **规模**:wake_word.py 1464 行:3 个引擎适配 + 模型下载/tflite 运行时桥接 + 需求自检 + 检测器线程/锁,复杂度中高。
- **学习价值**:中 — 把 'Hey Siri' 模式装进开源 agent 的完整参考:引擎抽象 _Engine、隐私边界(检测全本地)、N 连帧确认这个简单有效的防误触发手段,以及麦克风独占协调,对做语音入口的 harness 有直接参考价值。

#### 151. STT 自动探测链 + 双阈值幻觉段过滤

- **解决**:语音转写要在 '本地免费' 与 '云端付费' 间自动选择且不背着用户偷换;Whisper 对静音/噪声会幻觉出 'Thank you for watching' 之类的假转写,直接进 agent 会触发错误回合。
- **实现**:_get_provider 显式配置时严格尊重(不可用则返回 none 而非静默换云端);未配置时按 local > groq > openai > mistral > xai > elevenlabs > deepinfra 探测,本地缺依赖先走 lazy-install,DeepInfra 刻意垫底防止常见的聊天用 key 抢占 STT 选择,mistral 因 PyPI 恶意包事件在 auto 路径被跳过。幻觉过滤三层:faster-whisper 段级 AND 门(no_speech_prob 高且 avg_logprob 低才丢,安静但真实的语音只会命中其一而存活)、Silero VAD 前置、voice_mode 的 26 短语黑名单 + 重复模式正则兜底。
- **证据**:`tools/transcription_tools.py:1071` · `tools/transcription_tools.py:1601` · `tools/voice_mode.py:1254`
  ```
      if _HAS_FASTER_WHISPER:
          return "local"
  ```
- **规模**:transcription_tools.py 2687 行(8 个云/本地后端 + command/plugin 派发 + 分块转写 + CUDA 回退);幻觉过滤本身小而精。
- **学习价值**:中 — '显式配置绝不静默降级、auto 探测有明确优先级论证(含供应链事件的黑名单)' 是可信 provider 选择的范本;段级置信度 AND 门过滤幻觉是把 ASR 输出接入 agent 前必须做的卫生步骤。

#### 152. Nous Managed Tool Gateway:代码内 pin 的 vendor 端点 + presign 直传 nous-upload 媒体协议  **[◇未见于文档]**

- **解决**:让订阅用户不带任何第三方 API key 就能用 Firecrawl/FAL/OpenAI-TTS/BFL 等付费工具,需要一个统一代理;但 '服务器下发工具目录' 会让远端能给所有安装注入新工具,且 base64 内联媒体在请求上限下最多 ~2MB、视频完全不可行。
- **实现**:tools/managed_tool_gateway.py 是所有托管 vendor 的公共层:build_vendor_gateway_url 按 {vendor}-gateway.<domain> 规则在代码里 pin 端点(曾试过运行时 discovery catalog 后刻意移除——远端可注入工具的信任面大于一次代码 diff);token 分 peek(可用性扫描不触发同步 OAuth refresh)与 read(带 120s skew 的刷新)两条路径;is_managed_nous_gateway_url 保证 bearer/本地文件读取等额外信任只授予自建 origin。媒体走三步 presign 协议:POST 声明 contentType+length 拿短时效签名 PUT URL 与 token → 字节直传对象存储(绕开网关请求上限)→ 工具参数只携带 nous-upload:<token> 不透明引用(绑定本 principal、只能经网关兑付,泄露即失效)。entitlement 刻意不在客户端判断,由网关拒绝语句权威表达。
- **证据**:`tools/managed_tool_gateway.py:445` · `tools/managed_tool_gateway.py:167`
  ```
              put = await client.put(upload_url, content=data, headers={"Content-Type": mime})
          if put.status_code != 200:
              raise RuntimeError(f"storage refused the upload (HTTP {put.status_code})")
  
          return f"nous-upload:{token}"
  ```
- **规模**:managed_tool_gateway.py 452 行 + fal_common.py 的 _ManagedFalSyncClient 163 行 + 各 vendor 工具/插件里的接入点;设计密度高(信任边界、token 生命周期、上传协议)。
- **学习价值**:高 — '托管工具网关' 是订阅型 agent 产品的核心基建;三个决策极具学习价值:端点必须 code-pinned 可 review、entitlement 只由服务器裁决、大媒体用 presign 直传 + 不透明 token 引用而非内联 base64。docs 有 tool-gateway.md 讲功能,但 presign/nous-upload 协议本身完全没有文档。

#### 153. BFL FLUX3 视频工具:服务器 guidance 作为活策略通道 + 预算化轮询循环  **[◇未见于文档、▲文档不符]**

- **解决**:长耗时视频生成任务需要客户端轮询,但轮询节奏、限流等待、交付方式等策略若硬编码在客户端就会与服务器实际执行的策略漂移;而工具执行器 300s 超时会把仍在跑的任务报告成裸 TimeoutError(丢失 job id)。
- **实现**:六个 bfl_flux3_* 原生工具只做两种 REST 调用(POST /generations、GET /generations/<id>),网关响应里的 guidance 字段(下一步做什么、等多久、如何交付)被逐字作为工具结果文本呈给模型——策略从服务器下发所以永不漂移;拒绝(4xx error.message)与传输失败(transport_error)在 poll 循环里按 key 区分,拒绝是正常可回应结果。get_result 内部做多次短间隔轮询:_CALL_BACKSTOP_SECONDS=240 / _POLL_BUDGET_SECONDS=180 双上限确保远离执行器 300s 天花板,预算按实际花费记账、等待切片检查中断、连续 3 次传输失败才放弃。媒体输入经 resolve_image_source 走沙箱确权后用 nous-upload 协议直传。
- **证据**:`tools/flux3_video_tool.py:178` · `tools/flux3_video_tool.py:215` · `tools/flux3_video_tool.py:1186`
  ```
      guidance = payload.pop("guidance", None)
      return json.dumps(
          {"result": guidance or "Request accepted.", "details": payload},
          ensure_ascii=False,
      )
  ```
- **规模**:flux3_video_tool.py 1249 行,其中约 200 行是常数选择的论证注释;轮询预算、错误分型、媒体交付路径,复杂度中高。
- **学习价值**:高 — 两个罕见且高价值的 harness 模式:1) 'guidance 通道'——把易漂移的运维策略(等待时长、限流话术)全部服务器下发、客户端逐字转述给模型;2) 长任务轮询如何在工具执行器超时天花板下做预算化设计。整个 bfl 工具集在官方文档零覆盖。
- **▲ 文档不符**:website/docs/reference/tools-reference.md:11 宣称全部视频工具为 3 个(video_generate、xai_video_edit、xai_video_extend),未提及代码里注册的 6 个 bfl_flux3_* 工具;tool-gateway.md 的网关能力列表也不含视频生成。

#### 154. image_generate 统一 surface:FAL 模型目录 supports 白名单 + 插件派发 + managed Krea 模型级路由  **[▲文档不符]**

- **解决**:一个 image_generate 工具要覆盖 7+ 后端(FAL 目录 11 个模型、openai、xai、krea、openrouter、deepinfra、openai-codex)和两种模态(文生图/图生图编辑),各 FAL 模型对未知参数的拒绝方式还各不相同;托管模式下部分 Krea 模型要走专属网关。
- **实现**:FAL_MODELS 目录为每个模型声明 size_style 家族(preset 枚举/宽高比/字面尺寸)、defaults 与 supports 白名单,_build_fal_payload 把统一输入(prompt+aspect_ratio)翻译成模型原生 payload 并剥掉白名单外的 key。模态路由靠 image_url/reference_image_urls 的存在与否,provider 自己选文生图或编辑端点;旧签名插件收到新 kwargs 抛 TypeError 时降级重试并给出清晰错误。派发顺序:_maybe_route_managed_krea(仅托管模式、krea-2-* 原生模型 id 时拦截到 Krea 专属网关)→ 插件 registry 派发(provider 显式配置且非 fal)→ 传统 FAL 路径(BYO key 或经 _ManagedFalSyncClient 走 fal-queue 网关)。
- **证据**:`tools/image_generation_tool.py:91` · `tools/image_generation_tool.py:1284` · `tools/image_generation_tool.py:1447`
  ```
  # ``supports`` is a whitelist of keys allowed in the outgoing payload — any
  # key outside this set is stripped before submission so models never receive
  ```
- **规模**:image_generation_tool.py 1668 行 + agent/image_gen_provider.py 393 行 + registry 145 行 + plugins/image_gen 七个后端 3369 行;目录驱动的 payload 翻译是主要复杂度。
- **学习价值**:中 — '统一工具 surface + 声明式模型目录 + per-model supports 白名单' 是多模型媒体生成工具的标准解法;模型 id 级别的托管路由(同名能力在 BYO 与托管模式走不同网关)展示了商业化 harness 的真实复杂度。
- **▲ 文档不符**:模块 docstring(tools/image_generation_tool.py:5)仍写 'Provides image generation via FAL.ai',而实际该工具经 registry 派发到 openai/xai/krea/openrouter/deepinfra/openai-codex 等插件后端,FAL 只是遗留回退路径;网站文档(image-generation.md)是准确的,过时的只是模块头。

#### 155. 入站图像 native/text 双模路由 + 统一媒体源解析器(沙箱确权)

- **解决**:用户附图该直接作为多模态 content part 给主模型看原始像素,还是先用辅助 vision 模型转成文字?决策依赖主模型能力元数据。同时所有媒体来源(data:/http/file/容器路径)必须过同一个安全咽喉,否则非本地终端后端下 vision_analyze('/etc/passwd') 会变成沙箱逃逸读宿主文件。
- **实现**:decide_image_input_mode 每回合读 agent.image_input_mode(auto/native/text):auto 下主模型 supports_vision=True(config 覆盖或 models.dev 元数据,含 Ollama 探测)则 native 附加,否则 auxiliary.vision 作为 text 管道兜底;图像尺寸采取 reactive 策略——全尺寸先发、被 provider 400 拒绝后 shrink 重试,而非维护会过期的 per-provider 上限表。resolve_image_source 是唯一媒体入口:50MB ingest 上限、SSRF 检查、credential 文件读取守卫(.env/auth.json 直接拒绝);非本地终端后端下只有媒体缓存目录可宿主读,其余路径一律经 exec-read 在沙箱内取字节——读到的是容器文件而非宿主文件,修 'vision 看不见容器文件' 的同一机制顺带关闭了逃逸(GHSA-gpxw-6wxv-w3qq)。
- **证据**:`agent/image_routing.py:502` · `tools/image_source.py:153`
  ```
      if supports is True:
          return "native"
      if _explicit_aux_vision_override(cfg):
          return "text"
      return "text"
  ```
- **规模**:image_routing.py 821 行 + image_source.py 391 行 + vision_tools.py 里的 native fast-path/重试/缩放约 600 行;能力元数据查询、确权矩阵、reactive 缩放,复杂度高。
- **学习价值**:高 — 多模态 harness 的两个根本问题在此都有成熟答案:输入路由(native 优先、辅助 vision 仅作 text-only 模型的兜底、reactive shrink-on-reject 优于维护 provider 上限表)与媒体安全咽喉(单一 resolver + 后端相关确权,把安全修复和功能修复统一在同一机制里)。

#### 156. Web 搜索/提取 per-capability registry + 确定性 truncate-and-store 长页分页  **[▲文档不符]**

- **解决**:8 个 web 后端能力参差(brave-free/ddgs/searxng/xai 只有 search),要允许 search 与 extract 各选后端且插件化迁移后不改变老用户的落点;长网页塞进上下文是 token 炸弹,但 LLM 摘要既慢又贵还有损。
- **实现**:全部 8 个后端迁为 plugins/web/<vendor> 插件,经 agent/web_search_registry 解析:显式配置的后端即使 is_available()=False 也返回(让用户拿到精确的 'X_API_KEY is not set' 而非静默换后端)→ 唯一可用捷径 → 与迁移前 _get_backend 完全一致的 legacy 优先级走查;每步都过 supports_search/supports_extract 能力过滤。web_extract 长页处理零 LLM:75% 头 + 25% 尾按 markdown 行边界截窗,全文落盘到 cache/web(bind-mount 进远端后端只读),footer 给出确切的 read_file path/offset/limit 调用让模型自己翻被省略的中段;内联 base64 图统一替换成 [IMAGE: alt] 占位符防 token 炸弹。
- **证据**:`agent/web_search_registry.py:184` · `tools/web_tools.py:560`
  ```
      if configured:
          provider = snapshot.get(configured)
          if provider is not None and _capable(provider):
              return provider
  ```
- **规模**:web_tools.py 1237 行 + web_search_registry.py 304 行 + provider ABC 211 行 + plugins/web 八个后端 3933 行;解析规则与迁移兼容性是主要设计功夫。
- **学习价值**:高 — 两个可直接复用的 harness 决策:1) '显式配置忽略可用性也要返回' 让错误信息精确而不是静默降级;2) truncate-and-store + 自描述 footer 把长内容分页的主动权交给模型(教它下一步怎么调 read_file),完全确定性、零模型成本,优于 LLM 摘要。
- **▲ 文档不符**:tools/web_tools.py:20-22 模块 docstring 仍宣称 'Uses OpenRouter API with Gemini 3 Flash Preview for intelligent content extraction / creates markdown summaries',但实际代码路径已是零 LLM 的 truncate-and-store(同文件 750 行与 1193 行的 schema 描述均明确 'no LLM summarization');网站 web-search.md 与代码一致,过时的是模块头。

#### 157. x_search degraded 无引用检测:识别 '模型编的' 与 '索引查的'

- **解决**:xAI 的 x_search 在过滤条件(handle/日期)命中零结果时仍返回 200 与一段由模型自身知识合成的回答,与真实引用支撑的结果外观完全相同,agent 会把编造当检索结果转述给用户。
- **实现**:工具在响应上叠加防御信号:任一收窄过滤器激活且顶层 citations 与内联 url_citation 两个引用通道均为空时置 degraded=true 并给出 degraded_reason(列出激活的过滤器),提示调用方放宽过滤/换源;此外 from_date/to_date 在 HTTP 前做客户端校验(格式、倒置、纯未来区间)fail-fast 省 API 调用。凭证按 SuperGrok OAuth > 直连 OAuth > XAI_API_KEY 优先级解析并自动续期。
- **证据**:`tools/x_search_tool.py:418`
  ```
          degraded = bool(active_filters) and not citations and not inline_citations
          degraded_reason = (
  ```
- **规模**:x_search_tool.py 552 行;信号逻辑本身小巧,价值在思路。
- **学习价值**:中 — 对 '上游 200 但内容不可信' 的工具响应做客户端语义标注,是 harness 层对抗 LLM-backed API 幻觉的通用手段——工具不仅转发结果,还告诉模型该结果的证据等级。

**本子系统文档-代码冲突(4 条):**

- 宣称:tools/web_tools.py 模块 docstring(20-22 行)宣称:'LLM Processing: Uses OpenRouter API with Gemini 3 Flash Preview for intelligent content extraction; Extracts key excerpts and creates markdown summaries to reduce token usage'。
  实际:web_extract 实际是零 LLM 的确定性 truncate-and-store:头 75%+尾 25% 截窗、全文落盘、footer 指引 read_file 翻页;同文件 750 行 docstring 与 1193 行工具 schema 均写明 'no LLM summarization'。OpenRouter 摘要路径已不存在。(证据:`tools/web_tools.py:527`)
- 宣称:website/docs/reference/tools-reference.md:11 宣称视频工具共 3 个:'3 video tools (`video_generate`, `xai_video_edit`, `xai_video_extend`)';全站文档(含 tool-gateway.md)无任何 BFL/FLUX3 视频提及。
  实际:tools/flux3_video_tool.py 顶层 registry.register 另注册了 6 个 bfl toolset 工具:bfl_flux3_text_to_video、bfl_flux3_image_to_video、bfl_flux3_keyframes_to_video、bfl_flux3_video_continuation、bfl_flux3_get_result、bfl_flux3_prompting_guide。(证据:`tools/flux3_video_tool.py:1186`)
- 宣称:tools/image_generation_tool.py 模块 docstring(第 5 行)称该模块 'Provides image generation via FAL.ai',并把架构描述为 FAL 模型目录。
  实际:image_generate 现在优先经 agent/image_gen_registry 派发到插件后端(openai、xai、krea、openrouter、deepinfra、openai-codex),还有 managed Krea 模型级路由;FAL 只是 provider 未配置或显式为 'fal' 时的遗留回退路径。(证据:`tools/image_generation_tool.py:1284`)
- 宣称:docs(website/docs/user-guide/features/tool-gateway.md 等)描述了托管网关可用的工具面,但从未提及媒体上传机制;grep 全部 docs 无 'presign'/'nous-upload' 任何出现。
  实际:tools/managed_tool_gateway.py 实现了完整的三步媒体上传协议:POST presign(声明 contentType+contentLength)→ 字节直传对象存储(绕过网关请求上限,支撑 50MB 视频)→ 工具参数携带绑定 principal 的 nous-upload:<token> 不透明引用。(证据:`tools/managed_tool_gateway.py:449`)

### 2.14 安装/更新/运维基建(installer、self-update、doctor、测试/CI/发布、日志/路径/i18n 基座)+ 文档-代码冲突专项

该子系统是 hermes-agent 作为"用户自持 agent harness"的地基:源码检出式安装(install.sh/install.ps1/setup-hermes.sh 把仓库放到 $HERMES_HOME/hermes-agent 并用 uv.lock 哈希校验建 venv),之上是一个把自更新做成可回滚事务的 `hermes update` 管线(git ff-only + 9 文件语法编译守卫自动 reset --hard 回滚 + 子进程 import 探针 + 断点续传 marker + Windows ZIP 两阶段替换回退),配套跨 Python/Rust/Electron 字节兼容的更新互斥锁和 2777 行的 doctor 诊断/自修复系统。基座模块提供 profile 感知的 HERMES_HOME 三层解析(ContextVar/env/平台默认,带跨 profile 误写警告)、异步脱敏日志、原子写基元、Windows UTF-8 bootstrap、托管 Node/uv 工具链自举自愈。工程侧有 fail-open 的 CI change classifier + orchestrator 工作流、env -i 密封 + per-file 子进程隔离 + flaky 一次重试 + LPT 时长切片的测试基建、CalVer/SemVer 双版本发布脚本与免冲突贡献者映射目录,以及 17 语言的静态文案 i18n 薄片。文档对照总体质量高(updating.md 的 9 文件守卫、1 GiB 跳过、SIGHUP 防护等均与代码一致),但仍抓到 6 处漂移:compose 注释的过时 ENTRYPOINT、不存在的 submodule 更新、语言列表漏 ar、测试规模数字 3 倍漂移、doctor --ack 未入 CLI 参考、依赖安装机制被简化描述。

关键文件(43 个,行数实测,余见 JSON):`hermes_cli/update_cmd.py`(5540), `hermes_cli/update_lock.py`(289), `hermes_cli/main.py`(12599), `hermes_cli/doctor.py`(2777), `hermes_cli/managed_uv.py`(1304), `hermes_cli/backup.py`(1904), `hermes_cli/security_advisories.py`(453), `hermes_bootstrap.py`(239)


#### 158. hermes update 多阶段自愈更新管线(git 主路径)  **[▲文档不符]**

- **解决**:源码检出式安装(~/.hermes/hermes-agent)在用户机器上自更新时,任何一步失败(坏 commit 过了 CI、依赖装一半、终端断线、gateway 占用 venv)都可能把 CLI 直接砖掉。harness 需要一个'永远可回退、可续传'的更新事务。
- **实现**:入口 `_cmd_update_impl`(update_cmd.py:3564,~1900 行)串起完整事务:Windows 并发 hermes.exe/venv 持有者守卫(exit 2)→ pre-update snapshot → 暂停 Windows gateway → `git fetch` + `merge --ff-only`(失败则 reset --hard origin/branch)→ 关键 9 文件 `py_compile` 语法守卫,失败自动 `git reset --hard <pre_pull_sha>` 回滚 → 子进程 import 探针(`_validate_critical_modules_import`,只把 FIRST_PARTY_MODULE_ROOTS 的 ImportError 视为坏树)→ 分层依赖安装(`.[all]` 失败则逐 extra 重试,见 main.py:_install_python_dependencies_with_optional_fallback)→ 断点续传 marker(`_write_update_incomplete_marker`,下次启动由 `_recover_from_interrupted_install` 续装)→ 清 __pycache__ + importlib.reload 更新敏感模块 → lazy 后端刷新 → gateway 恢复/重启。另有 SIGHUP→SIG_IGN + update.log 镜像防终端断线,`_normalize_managed_eol`/`_discard_lockfile_churn` 消除 EOL/lockfile 噪声脏树。
- **证据**:`hermes_cli/update_cmd.py:94-97` · `hermes_cli/update_cmd.py:4013-4015` · `hermes_cli/main.py:9011-9013` · `hermes_cli/update_cmd.py:174-175`
  ```
  _UPDATE_CRITICAL_FILES = (
      "hermes_cli/main.py",
      "hermes_cli/config.py",
      "hermes_cli/__init__.py",
  ```
- **规模**:update_cmd.py 5540 行 + main.py 中约 1500 行 update 辅助;复杂度极高(Windows 文件锁、gateway 编排、git 状态机、断点恢复交织)
- **学习价值**:高 — 这是'agent 自更新'工程化的完整范本:每一步都有失败模式分析和回滚/续传路径,语法编译守卫 + 子进程 import 探针的双层验证(parse 通过≠import 通过)是可以直接搬走的模式。
- **▲ 文档不符**:website/docs/getting-started/updating.md:28 称 git pull 步骤会 'updates submodules',但仓库无 .gitmodules,update_cmd.py/main.py 中无任何 submodule 处理代码。

#### 159. Windows ZIP 两阶段替换更新回退路径  **[◇未见于文档]**

- **解决**:Windows 上杀毒/NTFS 过滤驱动会让 git 文件 I/O 直接报 Invalid argument,git 路径不可用;而逐目录覆盖式解压更新一旦中断会留下 agent/ 新、tools/ 旧的'每个文件都合法但整树不可启动'的半更新状态。
- **实现**:`_update_via_zip`(update_cmd.py:725)从 GitHub 下载分支 ZIP,先做 zip-slip realpath 校验并拒绝 symlink 成员(防更新镜像被投毒后经解压植入任意文件);拒绝非 main 的 --branch(静态归档无法尊重分支);预检磁盘空间(staging 拷贝 ×1.2 余量);然后两阶段替换(#76104):phase 1 把所有顶级 entry 拷到同文件系统 staging 路径,phase 2 用 rename 逐个换入,任一失败则回滚所有已换入项并 `_discard_staged` 清理残留,保证'要么全部生效要么原样保留'。保留集 {venv, node_modules, .git, .env} 不动。
- **证据**:`hermes_cli/update_cmd.py:784-788` · `hermes_cli/update_cmd.py:832-834` · `hermes_cli/update_cmd.py:841-846`
  ```
                  mode = (member.external_attr >> 16) & 0o170000
                  if _stat.S_ISLNK(mode):
                      raise ValueError(
                          f"ZIP contains unsupported symlink member: {member.filename}"
                      )
  ```
- **规模**:约 500 行(_update_via_zip + _stage_replacement/_atomic_replace_dir/_commit_staged_replacements/_discard_staged);中高复杂度
- **学习价值**:高 — 'stage-then-swap + 全量回滚'是对无 git 事务能力环境做原子目录树替换的标准解,zip-slip/symlink 双重校验展示了更新通道的供应链威胁模型。

#### 160. 跨进程更新互斥锁(update_lock.py,与 Rust/Electron 字节兼容)  **[◇未见于文档]**

- **解决**:终端 `hermes update`、dashboard 的 Update 按钮、桌面 Tauri `hermes-setup --update` 三个入口可能同时更新同一棵检出树,两个 updater 并发改写源码会留下半更新树;但 Tauri 父进程持锁期间又要 spawn 子 `hermes update`,天然会自死锁。
- **实现**:复用 Tauri 已有的 `<HERMES_HOME>/.hermes-update-in-progress` marker(内容 pid+起始时间)作为全入口统一锁,格式与 apps/bootstrap-installer 的 Rust UpdateMarkerGuard 和 electron/update-marker.ts 字节兼容。marker 仅当 pid 存活且年龄 < 20 分钟才算活锁,过期由先发现者删除自愈。父子 handoff 双机制:HERMES_UPDATE_HANDOFF_PID 环境变量(必须同时是活 marker 持有者,伪造无效)或持有者是本进程祖先(psutil parents 链,治愈老版本 staged updater 永不发 env var 的舰队)。release 只在自己仍是 owner 时删 marker,避免删掉 handoff 伙伴改写后的锁。exit code 2 与 Tauri 的 UPDATE_EXIT_CONCURRENT 合同一致。
- **证据**:`hermes_cli/update_lock.py:65` · `hermes_cli/update_lock.py:245-250` · `hermes_cli/update_lock.py:104-106` · `hermes_cli/update_lock.py:82`
  ```
  UPDATE_MARKER_MAX_AGE_SECONDS = 20 * 60
  ```
- **规模**:289 行,单文件;概念密度高(跨语言字节兼容、祖先识别、stale 自愈)
- **学习价值**:高 — 跨 Python/Rust/TypeScript 三运行时共享同一个文件锁并保持字节兼容、用'进程祖先链'解决旧版本 orchestrator 无法握手的舰队升级问题,是罕见且精巧的多入口互斥设计。

#### 161. hermes doctor 诊断/自修复/安全公告确认系统  **[▲文档不符]**

- **解决**:跨平台安装(源码/Docker/Nix/Termux/Windows)的故障面极大:证书坏、venv 半更新、版本文件漂移、被投毒的依赖包、可疑 MCP stdio 命令、s6/systemd 服务状态——用户报障时需要一条命令给出可执行的修复清单。
- **实现**:`run_doctor`(doctor.py:708,主体约 2000 行)按 20+ 个 `_section` 顺序检查:Security Advisories(detect_compromised 扫描已装的被投毒包版本,`--ack <id>` 持久化确认)、MCP stdio 命令安全校验、Python/SSL/必装包、config 结构 + 废弃键、`_check_version_consistency`(pyproject.toml vs hermes_cli.__version__ 漂移检测)、s6/systemd 监督状态、API 连通性、Tool 可用性、Skills Hub、Memory provider、Profiles。`--fix` 走自动修复分支,如 certifi 损坏时 force-reinstall 进当前解释器并清 importlib 缓存后复验;不可自动修的进 manual_issues 汇总输出。
- **证据**:`hermes_cli/doctor.py:720-721` · `hermes_cli/doctor.py:501` · `hermes_cli/doctor.py:397-398`
  ```
      if ack_target:
          from hermes_cli.security_advisories import (
  ```
- **规模**:doctor.py 2777 行 + security_advisories.py 453 行;广度大、单项逻辑中等
- **学习价值**:中 — 价值在检查项清单本身(把历史事故一条条固化成检查),以及'检查→自动修复→manual_issues 汇总'的三级结构;--ack 把安全公告变成带确认状态机的用户流程值得借鉴。
- **▲ 文档不符**:website/docs/reference/cli-commands.md:772 只记载 `hermes doctor [--fix]`,未提 `--ack <advisory-id>`(仅 user-guide/security.md:767 提及)。

#### 162. 供应链防御型依赖策略 + wheel 构建禁令

- **解决**:2026-05-12 Mini Shai-Hulud 蠕虫污染 PyPI 上的 mistralai 2.4.6:若依赖用范围版本,隔离前几小时内所有新装机都会中招。同时 pip/PyPI 发行会丢失 bundled 资产(locales、skills、web_dist),产生残废安装。
- **实现**:pyproject.toml 全部直接依赖 `==X.Y.Z` 精确钉死并写明政策(改版必须同步 `uv lock`);`[all]` extra 只含无法 lazy-install 的组件,可疑上游(mistral、supermemory、mem0)被刻意排除出 [all],改由 tools/lazy_deps.py 首次使用时安装,使单个被隔离的发行版不再炸掉全量新装。setup-hermes.sh 优先 `uv sync --extra all --locked`(uv.lock 记录全部传递依赖 SHA256,被替换的包哈希不符直接拒装),失败才降级到无哈希校验的 `_try_install` 多级回退。setup.py 覆写 sdist/bdist_wheel 命令:除非 HERMES_NIX_BUILD=1(uv2nix 沙箱)否则抛错,从机制上封死 pip/brew 发行渠道。`exclude-newer = "14 days"` 让 uv 解析时拒绝 14 天内的新包,给上游投毒事件留出隔离窗口。
- **证据**:`pyproject.toml:20-22` · `setup.py:47-51` · `setup-hermes.sh:254` · `pyproject.toml:371-372`
  ```
    # Core — every direct dep is exact-pinned to ==X.Y.Z (no ranges).
    # Rationale: ranges allow PyPI to ship a fresh version of a transitive
    # at any time without a code review on our side. Exact pins mean the
  ```
- **规模**:pyproject.toml 449 行(注释即策略文档)+ setup.py 74 行 + setup-hermes.sh 相关约 80 行
- **学习价值**:高 — 把一次真实供应链事故转化为四层制度(精确钉死、lazy-install 隔离带、lock 哈希校验、14 天新包冷静期),并用 setup.py 命令覆写在构建系统层面禁掉不受支持的发行渠道,是 agent 依赖治理的完整教材。

#### 163. CI 平价测试基建:密封环境 + per-file 子进程隔离 + flaky 一次重试

- **解决**:17k+ 测试在开发机(有真实 API key、本地时区、16+ 核)和 CI 上行为不一致,曾多次'本地绿 CI 红';xdist 持久 worker 跨文件泄漏模块级状态是主要 flake 源;偶发失败又会掩盖真回归。
- **实现**:scripts/run_tests.sh 用 `env -i` 从空环境白名单式重建(PATH/HOME/TZ=UTC/LANG=C.UTF-8/PYTHONHASHSEED=0,Windows 位置变量与测试旋钮单独显式转发,保证'凭据不可能泄入'可一眼审计),先 `compileall` 预编译字节码避免 ~2000 个子进程重复编译,再 exec run_tests_parallel.py。后者放弃 xdist,每个测试文件独立 `python -m pytest <file>` 子进程 + 信号量限并发,300s per-file 超时杀进程组;失败文件在新子进程重试一次,过了算绿但打进 `⚠ FLAKY` 汇总(附两次输出)强制修复——确定性回归两次都挂,无法被洗绿。venv 探测要求 import pytest 成功,防止选中无 pytest 的 release venv 出现 '0 tests passed 视觉绿'。
- **证据**:`scripts/run_tests.sh:169-171` · `scripts/run_tests_parallel.py:94-95` · `scripts/run_tests_parallel.py:88-91` · `scripts/run_tests.sh:56`
  ```
  exec env -i \
    PATH="$PATH" \
    HOME="$HOME" \
  ```
- **规模**:run_tests.sh 183 行 + run_tests_parallel.py 1142 行;设计精炼,权衡记录完整
- **学习价值**:高 — 'flaky 重试但大声报告'与'per-file 而非 per-test 隔离'(250ms×850 文件 vs ×17k 测试的成本推演)是测试基建里最值得抄的两个决策;env -i 白名单是本地/CI 平价的根本手段。

#### 164. 基于历史时长的 LPT 测试切片 + CI duration 缓存回流  **[◇未见于文档]**

- **解决**:12 个并行 CI 切片若按文件名均分,慢文件扎堆的切片会顶到 per-file 超时并拖长整体 wall time;每个矩阵 job 各自发现/切片又是 N 倍冗余。
- **实现**:runner 把每个文件的子进程 wall-clock 写入 test_durations.json;`--generate-slices N` 在 generate job 里跑一次 LPT(最长处理时间优先贪心装箱,`_compute_lpt_slices`)产出 matrix,各 test job 用 `--files` 接收现成清单。tests.yml 用 actions/cache 以 `test-durations-${run_id}` 保存、`restore-keys: test-durations-` 前缀回退恢复(注释明确记录:没有前缀回退时缓存永远 miss、切片失衡把重文件推向超时的事故);main 分支绿后 save-durations job 合并各切片 artifact 回写缓存。无缓存的新文件按 P50≈2.0s 估计,保证首轮也能合理分布。
- **证据**:`scripts/run_tests_parallel.py:600-603` · `.github/workflows/tests.yml:39-40` · `scripts/run_tests_parallel.py:585`
  ```
      for f, dur in file_durs:
          min_idx = min(range(slice_count), key=lambda i: bucket_totals[i])
  ```
- **规模**:runner 内约 150 行 + tests.yml 中 generate/save-durations 两个 job;中等复杂度
- **学习价值**:中 — 自带时长画像的 LPT 切片是把 CI wall time 变成一等优化目标的轻量做法;'缓存 key 永不精确命中所以必须 restore-keys 前缀'这类 GitHub Actions 陷阱记录得很实在。

#### 165. CI change classifier(fail-open 车道分类)+ orchestrator 工作流

- **解决**:monorepo(Python + 桌面 TS + 网站 + installer + Docker)里每个 PR 全量跑所有 job 太贵,但漏跑一个相关 lane 会让回归在 main 上才爆。
- **实现**:scripts/ci/classify_changes.py 从 stdin 读变更路径,输出 10 个布尔 lane(python/python_prod/docker_meta/frontend/site/scan/deps/npm_lock/installer/mcp_catalog)到 $GITHUB_OUTPUT。契约是 fail open, never closed:空 diff 或任何 .github/ 变更→全开;python 是 denylist(只有每个文件都可证明是纯 prose/前端才跳过,未知路径保持开);skills/ 虽像文档但被判定 python 相关(skill-doc 测试读该树)。python_prod 区分'改了产品代码'与'只改测试',让 tests-only PR 跳过 Desktop E2E/Docker 等产品 job。ci.yml 作为唯一 orchestrator:detect job 跑一次分类,12+ 个 workflow_call 子工作流按 lane 条件触发,最终 all-checks-pass 聚合供 branch protection;push-to-main 时分类器直接全开,保证合并后验证不弱化。CI 敏感文件(workflows/actions)变更要求 ci-reviewed 标签,label-rerun.yml 在补标签后自动重跑失败 job。
- **证据**:`scripts/ci/classify_changes.py:49` · `scripts/ci/classify_changes.py:28-29` · `.github/workflows/ci.yml:69-72`
  ```
  _PY_SKIP = ("docs/", "website/") + _FRONTEND
  ```
- **规模**:classify_changes.py 172 行 + ci.yml 390 行 + 25 个 workflow 文件;分类器本身小而设计考究
- **学习价值**:高 — 'python 用 denylist、其他 lane 用 allowlist'的不对称设计精确对应各 lane 的漏报代价;python_prod 与 python 的拆分(测试-only PR 占 ~17%)是 CI 成本工程的好样本。AGENTS.md 甚至据此规定'断言 JS 工件的测试必须放进 vitest 而非 pytest',文档与机制闭环。

#### 166. 发布流程:CalVer tag + SemVer 双版本、三文件版本同步、免冲突贡献者映射  **[◇未见于文档]**

- **解决**:发布需要同时维护 git tag(CalVer)、Python 包版本(SemVer)、桌面 Electron 版本三处一致;changelog 要把数百个 commit 归类并 @ 到正确的 GitHub 账号,而 salvage PR 的作者邮箱五花八门,集中式映射字典曾造成持续 merge 冲突。
- **实现**:scripts/release.py:`get_last_tag` 取 v20* 最新 CalVer tag,`next_available_tag` 处理同日多发(v2026.5.16.2);`update_version_files` 一次改三处:hermes_cli/__init__.py 的 __version__/__release_date__、pyproject.toml version、apps/desktop/package.json version(与 Python 包锁步)。`categorize_commit` 按 conventional-commit 正则 + 启发式归类生成 changelog,`resolve_author` 依次查 AUTHOR_MAP → GitHub noreply 模式 → git name。作者映射从冻结的 LEGACY_AUTHOR_MAP 字典迁移到 contributors/emails/ 目录(一邮箱一文件,文件内容为 login,新增永不冲突;目前 440 个文件),scripts/add_contributor.py 幂等写入并拒绝为同一邮箱改绑不同 login;.github/workflows/contributor-check.yml 在 PR 带未映射邮箱时红灯并打印修复命令。
- **证据**:`scripts/release.py:2211-2213` · `scripts/release.py:41-43` · `scripts/release.py:2146-2148`
  ```
      desktop_pkg = REPO_ROOT / "apps" / "desktop" / "package.json"
      if desktop_pkg.exists():
  ```
- **规模**:release.py 2637 行(其中 ~2000 行是冻结的 LEGACY_AUTHOR_MAP)+ add_contributor.py 103 行 + contributors/emails 440 文件
- **学习价值**:中 — '一文件一映射消灭 merge 冲突'+'CI 强制未映射邮箱红灯'把贡献者归属做成了机器可执行的流程;三文件版本锁步则是 doctor 版本一致性检查的另一半。

#### 167. Profile 感知的 HERMES_HOME 解析与跨 profile 误写守卫  **[◇未见于文档]**

- **解决**:119+ 个文件通过 get_hermes_home() 解析状态目录;多 profile(~/.hermes/profiles/<name>)与 Docker(/opt/data)布局下,子进程若忘传 HERMES_HOME 会静默落回默认 profile,把数据写进错误的家目录(issue #18594),且同进程内嵌 /chat 还需要按请求切 profile。
- **实现**:hermes_constants.py 提供三层解析:ContextVar `_HERMES_HOME_OVERRIDE`(set_hermes_home_override,按任务/请求作用域)→ HERMES_HOME 环境变量 → 平台默认(POSIX ~/.hermes,Windows %LOCALAPPDATA%\hermes)。当 env 未设但 `active_profile` 文件指向非 default profile 时,`_warn_profile_fallback_once` 直写 stderr 发一次性大警告(不走 logging:30+ 模块导入期调用早于日志配置)而不抛错(抛错会砖掉模块级调用者)。`get_process_hermes_home` 刻意无视 ContextVar,供机器级资产(dashboard 主题等)在请求切了 profile 时仍指向进程启动 home;`get_default_hermes_root` 识别 `<root>/profiles/<name>` 形状取根,兼容 Docker 布局;`get_hermes_dir(new,old)` 做带'空目录不算占用'判定的目录布局向后兼容(#27602 空 pairing/ 遮蔽真数据的回归)。
- **证据**:`hermes_constants.py:100-102` · `hermes_constants.py:194-195` · `hermes_constants.py:132-134`
  ```
              f"[HERMES_HOME fallback] HERMES_HOME is unset but active "
              f"profile is {active!r}. Falling back to {fallback_home}, which "
              f"is the DEFAULT profile — not {active!r}. Any data this "
  ```
- **规模**:hermes_constants.py 前 300 行为核心;概念难度高(三种作用域语义 + 多布局兼容)
- **学习价值**:高 — '同一路径函数的三种作用域语义'(任务级 ContextVar / 进程级 env / 平台默认)+ '不能抛错只能大声警告'的兼容性权衡,是多租户 agent 状态目录设计的核心课题;文档只讲 profile 用法,不讲这个守卫。

#### 168. Hermes 托管 Node 工具链自举与自愈  **[◇未见于文档]**

- **解决**:TUI/web UI 构建需要满足 engines 要求的 Node,但用户机器上的 node 可能缺失、属于用户自己(nvm/brew/Nix,不能动)、被中断安装留成'bin/npm 存在但 lib/cli.js 缺失'的坏树,或 major 过旧。
- **实现**:hermes_constants.py 维护 $HERMES_HOME/node 托管树:`node_tool_runnable` 不信任文件存在性,用 `--version` 实际探活(坏 wrapper 立刻 MODULE_NOT_FOUND);`bootstrap_hermes_managed_node` 在用户工具链不满足要求时私有部署托管树(POSIX shell 出 scripts/lib/node-bootstrap.sh 的 `_nb_install_bundled_node`,带 HERMES_NODE_SKIP_LINKS=1 不遮蔽用户 PATH;Windows 直接从 nodejs.org 下载 portable zip 解压);`heal_hermes_managed_node` 每进程最多一次地重下坏树;`_managed_node_tree_outdated` 把'低于目标 major(默认 22,HERMES_NODE_TARGET_MAJOR 可调)'视同坏树触发同一条 heal 路径,老用户下次启动即升级而非等重装;heal 失败时旧 Node 仍返回(old Node beats no Node)。查找顺序 POSIX 先 node/bin、Windows 先 node/,并注明与 Electron 侧 backend-env.ts 镜像同步。
- **证据**:`hermes_constants.py:582-585` · `hermes_constants.py:460` · `hermes_constants.py:352-357`
  ```
                  major = int(result.stdout.decode().strip().lstrip("v").split(".")[0])
              except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
  ```
- **规模**:hermes_constants.py:285-680 约 400 行 + node-bootstrap.sh 437 行;中高复杂度
- **学习价值**:中 — '绝不修改用户自己的工具链,而是私有部署一棵自己拥有的树'+'探活而非存在性检查'+'过旧与损坏共用同一条 heal 路径'是 harness 管理外部运行时依赖的成熟模式。

#### 169. 中央日志基建:异步队列 + 脱敏 + Windows 跨进程轮转 + 外部轮转自愈  **[▲文档不符]**

- **解决**:TUI、gateway、MCP server、CLI 命令多进程同时写同一组日志文件:Windows 上 stdlib 轮转 rename 撞开着的句柄报 WinError 32(日志卡死在 5MiB 阈值);轮转锁等待若发生在事件循环线程会冻结 agent;logrotate 外部轮转后旧 fd 静默写进 .1 文件;日志里还不能出现密钥。
- **实现**:hermes_logging.py `setup_logging` 建 agent.log(INFO+)/errors.log(WARNING+)/gateway.log/gui.log 四路 RotatingFileHandler,全部套 `RedactingFormatter` 脱敏;Windows 平台在 import 期把 RotatingFileHandler 别名成 concurrent-log-handler 的跨进程锁版本(POSIX 保持 stdlib,因 NixOS 管理模式依赖其 _open/doRollover 生命周期做 0660 chmod)。所有文件 handler 不直接挂 root,而是经 `_NonFormattingQueueHandler`(浅拷贝 record 防跨线程变异竞态)进 SimpleQueue,由 QueueListener 工作线程写盘——发射线程永不阻塞在轮转锁上;`drain_log_queue` 在硬退出路径用限时线程 join 防 listener 卡锁时冻结 shutdown。`_ManagedRotatingFileHandler` 每次 emit 前比对 baseFilename 的 dev/ino,检测 logrotate/mv 外部轮转后自动 reopen。session 上下文经 record factory 注入 `[session_id]` 标签供过滤。
- **证据**:`hermes_logging.py:64-67` · `hermes_logging.py:636-639` · `hermes_logging.py:591-592`
  ```
  if sys.platform == "win32":
      from concurrent_log_handler import (  # noqa: E402
  ```
- **规模**:800 行;并发细节密集(队列、跨进程锁、inode 探测、平台分叉)
- **学习价值**:中 — 多进程 agent 日志的四个经典坑(Windows 轮转锁、事件循环阻塞、外部轮转、密钥泄漏)在一个文件里全部给出带事故编号的解;'Windows 换实现、POSIX 保 stdlib'的平台不对称决策记录得很清楚。
- **▲ 文档不符**:AGENTS.md:273-274 只列出 agent.log/errors.log/gateway.log,未提 mode="gui" 时创建的 gui.log(hermes_logging.py:352-362);异步队列架构亦无任何文档。

#### 170. i18n 薄片:17 语言目录 + 英语回退 + 键名兜底  **[▲文档不符]**

- **解决**:面向终端用户的静态文案(审批提示、gateway 回复、重启排空通知)需要本地化,但全量 i18n 会拖累所有日志/错误/工具输出;坏的翻译目录绝不能让 agent 崩溃。
- **实现**:agent/i18n.py 刻意限定薄片范围:仅最高影响的静态串走 `t(key)`。locales/<lang>.yaml(repo 根,17 个文件)嵌套 YAML 被拍平成点号键;语言解析顺序 t(lang=) > HERMES_LANGUAGE env > config display.language(lru_cache 缓存,reset_language_cache 失效)> en。`_normalize_lang` 接受自然别名(chinese/zh-CN/繁体各地区码/日德西法等)并剥离地区后缀。查键三级兜底:目标语言 → 英语 → 返回键名本身(破目录只难看不崩溃);format 失败也只 warning 并退回未格式化文本。打包安装经 HERMES_BUNDLED_LOCALES 指向密封目录(Nix wrapper 设置)。
- **证据**:`agent/i18n.py:43-46` · `agent/i18n.py:254-256` · `agent/i18n.py:105`
  ```
  SUPPORTED_LANGUAGES: tuple[str, ...] = (
      "en", "zh", "zh-hant", "ja", "de", "es", "fr", "tr", "uk",
  ```
- **规模**:i18n.py 282 行 + locales/ 17 个 YAML(en.yaml 453 行);低复杂度、边界处理完善
- **学习价值**:低 — 'thin slice by design'的范围克制和三级兜底(目标语→en→键名)值得记一笔,但机制本身常规;主要价值是发现了文档漏列 ar 的漂移。
- **▲ 文档不符**:website/docs/user-guide/configuration.md:1662 与 :1727 列出的支持语言均缺 `ar`(阿拉伯语),而代码 SUPPORTED_LANGUAGES 含 ar 且 locales/ar.yaml 存在。

**本子系统文档-代码冲突(6 条):**

- 宣称:docker-compose.yml:19-20 注释宣称镜像默认 ENTRYPOINT 是 `["/init", "/opt/hermes/docker/main-wrapper.sh"]`("or let docker use the image's default ENTRYPOINT, which is `[\"/init\", \"/opt/hermes/docker/main-wrapper.sh\"]`")
  实际:Dockerfile 实际为 `ENTRYPOINT [ "/opt/hermes/docker/entrypoint-dispatch.sh" ]` + `CMD [ ]`(dispatcher 在 PID-1 场景才转交 /init);website/docs/user-guide/docker.md:485,498 已更新为 dispatcher,唯 docker-compose.yml 注释仍是旧世界。(证据:`Dockerfile:456`)
- 宣称:website/docs/getting-started/updating.md:28 宣称 `hermes update` 的 Git pull 步骤 "pulls the latest code from the `main` branch and updates submodules"
  实际:仓库根本没有 .gitmodules,hermes_cli/update_cmd.py 与 main.py 中不存在任何 submodule 处理代码;实际执行的是 `git fetch` + `git merge --ff-only origin/<branch>`(分歧时 reset --hard)。(证据:`hermes_cli/update_cmd.py:3965-3966`)
- 宣称:website/docs/user-guide/configuration.md:1727 宣称支持语言为 "en, zh, zh-hant, ja, de, es, fr, tr, uk, af, ko, it, ga, pt, ru, hu"(共 16 种,1662 行的行内注释同样漏列)
  实际:代码 SUPPORTED_LANGUAGES 为 17 种,额外包含 "ar"(阿拉伯语),locales/ar.yaml 存在且 i18n 别名表覆盖 ar-sa/ar-eg 等地区码。(证据:`agent/i18n.py:43-46`)
- 宣称:AGENTS.md:269 宣称测试套件规模为 "Pytest suite (~17k tests across ~900 files as of May 2026)"
  实际:基线 commit 实测 `find tests -name 'test_*.py' | wc -l` = 2667 个文件、`def test_` 计数 23639 个;AGENTS.md 自己也声明 "File counts shift constantly",但该数字已漂移约 3 倍(文件数),引用时需按实测为准。(证据:`AGENTS.md:269`)
- 宣称:website/docs/reference/cli-commands.md:769-777 将 doctor 的完整用法记为 `hermes doctor [--fix]`,选项表仅含 --fix
  实际:doctor 还接受 `--ack <advisory-id>` 快路径(持久化安全公告确认并跳过其余诊断,未知 ID exit 2);该 flag 注册于 hermes_cli/subcommands/doctor.py:26,仅 user-guide/security.md:767 顺带提到。(证据:`hermes_cli/doctor.py:717-720`)
- 宣称:website/docs/getting-started/updating.md:30 宣称依赖步骤 "runs `uv pip install -e \".[all]\"` to pick up new or changed dependencies"
  实际:首选路径确为 `-e .[all]`,但实际是 `_install_python_dependencies_with_optional_fallback`:失败后降级为 base `-e .` + 逐 extra 重试并汇报跳过项,Termux 下自动改用 `.[termux-all]` 组;此前还会 `uv self update` 托管 uv。文档描述的是理想路径而非机制全貌(轻微简化,非硬错误)。(证据:`hermes_cli/main.py:8490-8499`)

### 2.15 全局观察(跨子系统)

1. **恢复阶梯 + 一次性守卫**是全仓最一致的工程签名:空响应、截断、限流、OAuth 失效、流中断、更新失败、平台断连——每种失败都有专用有界重试阶梯,并用一次性布尔守卫防死循环(`agent/turn_retry_state.py`、`hermes_cli/update_cmd.py` 等)。
2. **prompt cache 字节级稳定**是贯穿性设计约束(api_content 侧车、冻结记忆快照、缓存感知斜杠命令),AGENTS.md 也将其列为最高设计红线,代码与宣称一致。
3. **单体巨文件 + 循环依赖 + 函数内延迟 import** 是演化路径的代价;学习时以机制为单位切片,而不是以文件为单位。


---

## 勘误(R8-fix,review-1 处置,2026-08-08)

本附卷正文保持历史原样,以下为经复核成立的修正。修正卡:`claude/hermes-r8fix-review-1`。

1. **【M-8】两处引用各差 1 行,而校验脚本一直在报另一个引用**。

   | 位置 | 原引用 | 实际 | 围栏块首行 |
   |---|---|---|---|
   | `:342` 证据行第 1 个引用 | `agent/models_dev.py:11` | **`:12`** | `Data resolution order:` 在 `:12`,不在 `:11` |
   | `:826` 证据行第 1 个引用 | `tools/tool_result_storage.py:172-178` | **`:171-175`** | `if effective_threshold == float("inf"):` 在 `:171`,块长 5 行 |

   **值得记的不是这两个 1,是为什么它们一直没被修。** 这两行各带 2–3 个并列引用,
   而 `verify_citations.py` 的多引用逻辑是"逐个试,谁匹配算谁,都不匹配则回落到最后一个"
   ——**回落之后的报错只印那个回落对象**。于是维护者看到的是
   "`tools/budget_config.py:11` 找不到",而那个引用根本没错,真正漂了的是同一行的第一个。
   本附卷 185 个"带围栏块的引用行"里有 **180 行(97.3%)** 是多引用行
   (`notes/` 只有 1.6%,`chapters/` 为 0),**误导性报错正好集中在最早、最少人回看的这一份**。
   R8-fix 已给脚本的 MISMATCH 文本加上"本行 N 处引用,以下为回落对象,漂的可能是另一个"。
   行号已就地改正(否则校验器无法通过),本条即是它的公开记录。

2. **【M-16b】`tools-runtime.md:96` → `:91`**(正文第 939 行)。理由同
   `reports/round-1-survey.md` 勘误第 1 条,四处副本已同改。

3. **【M-15】本附卷无结论句,现正式定为豁免**。首行是"主卷:reports/round-1-survey.md"。
   CLAUDE.md 的"报告第一句 ≤20 字结论"自 R8-fix 起明确**豁免纯数据附卷**——
   它是主卷的数据附件,本身不承载结论。豁免在 `scripts/verify_report_headline.py`
   里以显式名单实现,不靠脚本猜。

4. **未处理项(如实申报)**:本附卷 170 条能力点里,review-1 只抽核了 2 条(即上面 M-8 那两处),
   **其余 168 条的代码摘录未经第二方复核**;`data/capability-mining.json` 同样未复核。
   这是本附卷当前最大的未验面。
