# R2-03 流式:强制流式、单写者栅栏、逐 delta 清洗

> 底稿。基线 `863e31318`。范围:`run_agent.py:6277-6440`、`agent/stream_single_writer.py`(70 行全读)、
> `agent/conversation_loop.py:2329-2416`、`agent/stream_diag.py`(概览)。
> interruptible_streaming_api_call 本体(chat_completion_helpers.py:2528)细节见 r2-10(故障转移簇)。

## 1. 无消费者也强制流式(conversation_loop.py:2329-2381)

`_use_streaming = True` 是默认,理由写死在注释里(2329-2339):流式给了非流式没有的
细粒度健康检查——**90s 陈旧流检测、60s 读超时**;没有它,provider 用 SSE ping 保活但永不给
响应时,安静模式调用方(子代理)会无限挂起。四个例外:
1. `agent._disable_streaming`(2352-2353):provider 曾答"stream 不支持",本会话余下都走非流式;
2. copilot-acp(子进程 stdio,返回 SimpleNamespace 非流,2358-2363);
3. MoA 无消费者(2373-2374):facade 在无 stream 请求时返回完整响应,保持旧行为;
4. Mock client(测试,2375-2381)。

非流式路径不是直调,而是 `relay_llm.execute(..., agent._interruptible_api_call, ...)`
(2395-2416)——带 session/provider/model/call_role 元数据的托管执行。

▲ 定案(详 r2-90):agent-loop.md:108 说请求包在 `_interruptible_api_call()`——已过期,
默认路径是 `_interruptible_streaming_api_call`(2391-2394)。

## 2. 单写者令牌栅栏(#65991;run_agent.py:6277-6333 + agent/stream_single_writer.py)

问题:重试/故障转移会开启新的流尝试,旧线程上未死透的流把迟到 chunk 交错写进回合。
机制:
- `_claim_stream_writer()`:每个流尝试开始消费前调用;共享 token 单调递增,**thread-local**
  存自己的 token(6289-6294)。从未 claim 的线程(非流式调用方)永远不会被栅栏拦。
- `_stream_writer_superseded()`:tls token 存在且 ≠ 当前共享 token → 本线程是陈旧写者(6302-6315)。
- 消费点:`_fire_stream_delta` / `_fire_reasoning_delta` 开头拦截(6335-6341、6393-6399),
  丢弃计数 `_stream_writer_dropped`,**稀疏日志**(第 1 次 + 2 的幂次;6323-6333:
  既不让超噪陈旧流刷爆日志,也不静默掩盖真 provider 故障)。
- **best-effort 包装**(`agent/stream_single_writer.py:31-70`):跨模块调用经
  `claim_stream_writer(agent)` / `stream_writer_is_current(agent, token)`,agent 没有栅栏方法
  或抛异常时**降级为不设防继续流**——栅栏只允许丢"可证明被取代"的流,永不丢唯一合法写者;
  背景是部分更新 checkout/热重载/测试替身导致 cron 任务因 AttributeError 死掉的真实事故(11-15)。

## 3. 逐 delta 清洗管线(run_agent.py:6335-6391)

`_fire_stream_delta` 顺序:
1. 栅栏检查(见上);
2. `_stream_needs_break`:工具批次后首个真文本前补一个 `\n\n`(6342-6351,防跨工具边界的文本
   粘连,又不会连续工具迭代堆空行);
3. **有状态 think scrubber**(6352-6366):`_stream_think_scrubber.feed(text)`——早期版本按
   delta 跑 `_strip_think_blocks` 正则,标签跨 delta 分裂时(MiniMax-M2.7 把 `<think>` 与内容
   分开发)下游状态机看不到开标签,推理内容泄漏为正文(#17924);
4. **有状态 context scrubber**(6367-6374):记忆上下文 fenced span 跨 chunk 也不能漏到 UI(#5719);
5. 首 delta 剥前导换行(6375-6379);
6. 分发给 `stream_delta_callback`(显示)与 `_stream_callback`(TTS),任一送达则
   `_record_streamed_assistant_text(text)`(6382-6391)——这是空响应阶梯 L1"部分流恢复"的数据源。

## 4. 陈旧流检测与读超时(接口层)

`interruptible_streaming_api_call`(chat_completion_helpers.py:2528)带 90s 无新 delta 的
陈旧流检测与 60s 读超时;中断经 `_active_request_abort` 关 socket(r2-02 §1/§3)。
细节与证据在 r2-10。

## 5. 重实现要点

1. "永远流式"不是为了 UX,是为了**健康检查**——把挂死检测内建在传输层。
2. 多次流尝试并存时,用"单调 token + thread-local 声明"实现最后写者胜,且失败模式必须是
   "不设防"而非"误杀唯一写者"。
3. 逐 delta 文本变换(think 剥除、上下文围栏)必须是**有状态流式**处理器,决不能按 delta 跑正则。
4. 已流出文本要记账(供部分流恢复、previewed 判定复用)。
