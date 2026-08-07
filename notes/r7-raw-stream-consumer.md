# R7 底稿 · gateway/stream_consumer.py 全文件精读(2410 行 @ 863e313)

> 溯源约定:`gateway/stream_consumer.py:行号 @ 863e313`,引用块均为逐字摘录(≤25 行)。
> 本文件是网关流式投递的核心:把 agent 工作线程的同步 token 回调,桥接成平台上一条
> 不断被编辑(或 draft 动画)的消息,并在结束时与网关的"正常最终发送"路径做去重协商。

## 0. 文件定位与总体架构

**问题**:agent 在线程池里同步跑,每个 LLM token 触发一次 `stream_delta_callback(text)`;
而平台适配器(Telegram/Discord/Slack…)的发送/编辑是 asyncio 协程。且平台有编辑频率限制
(flood control)、消息长度上限、编辑不改时间戳等约束。

**实现**:模块头自述了三段式桥接。

`gateway/stream_consumer.py:1-14 @ 863e313`
```python
"""Gateway streaming consumer — bridges sync agent callbacks to async platform delivery.

The agent fires stream_delta_callback(text) synchronously from its worker thread.
GatewayStreamConsumer:
  1. Receives deltas via on_delta() (thread-safe, sync)
  2. Queues them to an asyncio task via queue.Queue
  3. The async run() task buffers, rate-limits, and progressively edits
     a single message on the target platform

Design: Uses the edit transport (send initial message, then editMessageText).
This is universally supported across Telegram, Discord, and Slack.

Credit: jobless0x (#774, #1312), OutThisLife (#798), clicksingh (#697).
"""
```

**设计理由**:用 `queue.Queue`(线程安全)做唯一跨线程通道,agent 线程只做 `put`,
所有平台 I/O 集中在单个 asyncio 任务 `run()` 里串行执行——没有锁、没有跨线程 await。
**取舍**:队列是无界的;背压靠 run() 的限速丢合并(编辑总是用全量 `_accumulated`,
中间帧可以整批跳过),而不是靠阻塞生产者。

**重实现要点**
1. 生产者(agent 线程)只允许 `Queue.put`,消费者单协程串行做平台 I/O,状态全部单线程持有。
2. 编辑内容永远是"累计全文 + 光标",而非增量——任何一帧丢失都不影响最终正确性。
3. 所有回调(on_new_message / on_before_finalize)都吞异常,展示层绝不打断 agent 主循环。

---

## 1. 队列哨兵协议:_DONE / _NEW_SEGMENT / _COMMENTARY / _FLUSH

`gateway/stream_consumer.py:42-54 @ 863e313`
```python
# Sentinel to signal the stream is complete
_DONE = object()
_NEW_SEGMENT = object()
_COMMENTARY = object()

# Queue marker for a synchronous flush barrier.  Enqueued as
# ``(_FLUSH, threading.Event)``; the drain loop finalizes and delivers any
# buffered segment, then sets the event.  A caller on the agent worker thread
# uses this (via ``flush_pending_sync``) to block until everything queued
# BEFORE the marker has actually landed on the platform — needed before
# sending a blocking interactive prompt (clarify poll) so the prompt is the
# last thing on screen, not racing ahead of buffered prose.
_FLUSH = object()
```

**协议**:队列里可能出现 5 种元素——`str`(文本 delta)、`_DONE`(流结束)、
`_NEW_SEGMENT`(段边界,工具调用前后)、`("_COMMENTARY", text)` 元组(完整的过渡性
assistant 消息)、`(_FLUSH, threading.Event)` 元组(同步屏障)。用 `object()` 单例做哨兵
+ `is` 比较,零碰撞风险(任何字符串都不可能 `is` 这些对象)。

**_FLUSH 的问题背景**:clarify poll(向用户提问的阻塞交互)走的是另一条"agent 线程阻塞式"
发送路径,若不先排空流式队列,问题会渲染在它自己的铺垫文字**上方**。`flush_pending_sync`
(见 §5)把一个 Event 排在既有 delta 之后,run() 处理到它时先把当前段 finalize 投递,再 set。

**重实现要点**
1. 哨兵用模块级 `object()` 单例 + `is` 判别;带载荷的哨兵用 `(sentinel, payload)` 元组。
2. 段边界(工具边界)必须是队列内哨兵而非旁路标志,才能与 delta 保持 FIFO 顺序。
3. 同步屏障 = 队列内 Event + 消费者置位;调用方必须带超时(消费者可能已死)。

---

## 2. 代码围栏工具:escape_code_fences_for_display / ensure_closed_code_fences

### 2.1 escape_code_fences_for_display(57-72)

`gateway/stream_consumer.py:70-72 @ 863e313`
```python
    if not isinstance(text, str) or "```" not in text:
        return text
    return text.replace("```", "\\`\\`\\`")
```

**问题**:把 reasoning 内容包进外层 ``` 展示时,内部若含 ``` 会把外层围栏截断。
**实现**:每个 ``` 逐字符转义为 `\`\`\``。本文件内并未调用(供网关其他展示路径 import)。

### 2.2 ensure_closed_code_fences(75-124)

**问题**:模型输出被 token 上限截断(finish_reason="length")时留下未闭合的 ```,
Discord/Slack 上其后所有内容都渲染成一个巨型代码块;单反引号孤儿同理会让剩余文本全变行内代码。

`gateway/stream_consumer.py:109-124 @ 863e313`
```python
    # Step 1: fix triple-backtick code-block fences (existing logic)
    if text.count("```") % 2 == 1:
        text = text.rstrip("\n") + "\n```"

    # Step 2: fix single-backtick inline-code spans
    # Remove complete ```…``` regions so their internal backticks don't
    # pollute the standalone count.  Also remove any trailing unclosed
    # ``` that leaks through (defence in depth).
    import re
    without_fences = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    without_fences = re.sub(r"```[^`]*$", "", without_fences)

    if without_fences.count("`") % 2 == 1:
        text = text + "`"

    return text
```

**设计理由/取舍**(docstring 87-100 自述):奇数个 ``` 就补一个闭合——嵌套字面 ``` 极罕见,
误补的代价只是消息尾部多一个空代码块,远好于整条消息变代码块。单反引号计数前先剔除完整
``` 区域,避免代码块内部的 ` 污染计数。

**重实现要点**
1. 奇偶计数补闭合是"错也错得便宜"的策略,优先选伤害小的失败模式。
2. 数单反引号前必须先剥掉 ``` 区域(含尾部未闭合区域,双保险)。
3. 该函数在每次 `_send_or_edit` 出站前调用(见 §14),所以流式中间帧也不会出现半开围栏。

---

## 3. StreamConsumerConfig(127-153)

`gateway/stream_consumer.py:127-153 @ 863e313`
```python
@dataclass
class StreamConsumerConfig:
    """Runtime config for a single stream consumer instance."""
    edit_interval: float = _DEFAULT_STREAMING_EDIT_INTERVAL
    buffer_threshold: int = _DEFAULT_STREAMING_BUFFER_THRESHOLD
    cursor: str = _DEFAULT_STREAMING_CURSOR
    buffer_only: bool = False
    # When >0, the final edit for a streamed response is delivered as a
    # fresh message if the original preview has been visible for at least
    # this many seconds.  ...  Ported from
    # openclaw/openclaw#72038.  Default 0 = always edit in place (legacy
    # behavior).  The gateway enables this selectively per-platform.
    fresh_final_after_seconds: float = 0.0
    # Streaming transport selection:
    #   "auto"  — prefer native draft streaming (e.g. Telegram sendMessageDraft)
    #             when the adapter + chat supports it; fall back to edit.
    #   "draft" — explicitly request native draft streaming; fall back to
    #             edit when unsupported.
    #   "edit"  — progressive editMessageText (legacy/default behavior).
    #   "off"   — handled by the gateway before the consumer is even built.
    transport: str = "edit"
    # Hint for the consumer about the originating chat type (e.g. "dm",
    # "group", "supergroup", "forum").  Used to gate native draft streaming,
    # which is platform-specific (Telegram drafts are DM-only).
    chat_type: str = ""
```

默认值来自 `gateway/config.py:715-717 @ 863e313`:
```python
DEFAULT_STREAMING_EDIT_INTERVAL: float = 0.8
DEFAULT_STREAMING_BUFFER_THRESHOLD: int = 24
DEFAULT_STREAMING_CURSOR: str = " ▉"
```

- `edit_interval`:两次编辑的最小间隔(0.8s,自适应退避会把它翻倍,见 §15)。
- `buffer_threshold`:24 个码点——即使间隔没到,攒够 24 字符也触发编辑(防迟滞)。
- `cursor`:" ▉" 打字光标,附在中间帧尾部,finalize 时去掉。
- `buffer_only`:True 时**只**在 done/段界/commentary 时投递(Matrix 用,见 §17)。
- `fresh_final_after_seconds`:>0 时长寿命预览的最终帧改为"发新消息+删旧预览",
  让可见时间戳反映完成时刻,移植自 openclaw/openclaw#72038;默认 0=原地编辑。
- `transport`:auto/draft/edit;"off" 由网关在构建 consumer 之前就拦掉(23937-23941 的
  `_scfg.transport != "off"` 判定),consumer 里对 "off" 只是防御性当 edit 处理(1688-1689)。

**重实现要点**
1. 配置是 per-consumer 数据类,平台差异(cursor 抑制、fresh-final 开关)由网关在构建时裁剪,
   consumer 本体保持平台无关。
2. "off" 在上游消灭,下游仍防御性处理——层间契约要双向兜底。
3. 阈值语义分清:buffer_threshold 是码点数的 debounce 启发式,长度上限检测才用平台单位
  (run() 内 867-871 的注释明说这点)。

---

## 4. __init__ 状态字段全景(192-322)

状态字段是本文件复杂度的根源,分组记录:

**投递目标与预览追踪**

`gateway/stream_consumer.py:220-243 @ 863e313`
```python
        self._queue: queue.Queue = queue.Queue()
        self._accumulated = ""
        # Full segment text mirror of ``_accumulated`` that is NOT truncated
        # when overflow splits seal head chunks.  Used to record a reconciliable
        # turn-final payload for multi-message deliveries (#78541).
        self._stream_ledger = ""
        self._message_id: Optional[str] = None
        # Wall-clock timestamp (time.monotonic) when ``_message_id`` was
        # first assigned from a successful first-send.  Used by the
        # fresh-final logic to detect long-lived previews whose edit
        # timestamps would be stale by completion time.  Ported from
        # openclaw/openclaw#72038.
        self._message_created_ts: Optional[float] = None
        # Every real preview message id the consumer has put on screen during
        # this response (first send + any continuation messages from oversized
        # edits/sends).  The fresh-final path deletes all of them when it
        # re-delivers the completed answer as a single (rich) message, so a
        # reply that was split across the platform's edit limit while streaming
        # doesn't leave stale fragments above the final message.
        self._preview_message_ids: "set[str]" = set()
        # IDs from only the active text segment.  A tool boundary preserves
        # the run-wide set for fresh-final bookkeeping, but a failure recovery
        # must never delete an earlier finalized preamble/commentary message.
        self._segment_preview_message_ids: "set[str]" = set()
```

关键区分:
- `_accumulated`:活动段缓冲,溢出分片封存 head 后会被截断成只剩尾块;
- `_stream_ledger`:同段全文镜像,**不**随封存截断——供 #78541 的对账(见 §18);
- `_preview_message_ids`(全轮)vs `_segment_preview_message_ids`(仅当前段):
  fresh-final 清理用前者(删掉本轮所有预览碎片),失败恢复(`_send_empty_fallback_final`)
  只能用后者——绝不能删掉早前已 finalize 的段首消息(1561-1566 注释)。

**fallback 状态**(244-260):`_already_sent`(有任何东西上过屏)、`_edit_supported`
(编辑永久失效开关)、`_last_sent_text`(跳过重复编辑)、`_last_edit_overflowed`
(上次编辑被适配器拆成续篇)、`_fallback_final_send`(进入"最终只发未见尾部"模式)、
`_fallback_prefix`(用户已见前缀)、`_fallback_preserve_partial_messages`(Telegram 部分
溢出投递后,前缀是正式内容不许删)、`_max_fallback_flood_retry_seconds = 5.0`(fallback
重试不等超过 5s 的 flood 冷却)。

**最终去重协议字段**(261-290):

`gateway/stream_consumer.py:263-290 @ 863e313`
```python
        self._final_response_sent = False
        # Set when the final response content was sent to the user via
        # streaming, even if the final edit (cursor removal etc.)
        # subsequently failed.
        self._final_content_delivered = False
        # Exact cleaned payload of the turn-final delivery that set the flags
        # above.  The gateway compares this against the completed
        # ``final_response`` before trusting the flags: a *successful* finalize
        # edit that carried only a stale preview snapshot must not suppress the
        # complete send (#71643).  ``None`` means "no record" — legacy trust,
        # so paths that predate the record keep their behavior.
        self._delivered_final_text: Optional[str] = None
        # True when the current turn's answer was delivered across multiple
        # sealed messages (overflow split / adapter continuation adoption).
        # When a payload was recorded (via ``_stream_ledger`` /
        # ``_record_turn_final_payload``), ``delivered_final_matches`` can still
        # reconcile.  Payload-less split delivery must NOT inherit legacy trust
        # (#78541) — that combination was swallowing complete Telegram group
        # replies after an early/partial multi-message delivery.
        self._turn_split_delivery = False
        self._delivered_commentary_texts: list[str] = []
        # Retains the finalized visible text of each streaming segment so
        # ``has_delivered_text`` can still match after ``_reset_segment_state``
        # clears ``_last_sent_text``. ... (#65919 review)
        self._delivered_segment_texts: list[str] = []
```

四层记录:布尔标志(sent/delivered)→ 精确载荷(`_delivered_final_text`)→ 分片标志
(`_turn_split_delivery`)→ 历史段/commentary 文本列表。协议详解见 §18。

**其它**:`_adapter_requires_finalize`(296-298,`REQUIRES_EDIT_FINALIZE is True`——
用 `is True` 而非 `bool(...)`,防 MagicMock 的 truthy 自动属性误开路径,这个"测试替身
防御"模式全文件反复出现);`_run_still_current`(300-303,/new、/stop 后弃流);
think 过滤状态(306-307);draft 状态(316-321);`_before_finalize_notified`(322)。

类级常量:`_MAX_FLOOD_STRIKES = 3`(171-173);`_OPEN_THINK_TAGS/_CLOSE_THINK_TAGS`
(178-185,注释要求与 cli.py、run_agent.py 的标签表同步);`_draft_id_counter`(190,
类级单调计数——Telegram 对同 chat 内复用同 draft_id 的连续调用做动画,所以每个响应/
每个段要新的非零 id)。

**重实现要点**
1. "已投递"必须分层记录:布尔标志会撒谎(#71643),要存精确载荷做事后对账。
2. 预览 id 追踪要分"全轮"与"当前段"两个集合,清理范围取决于场景。
3. 每个从外部对象读取的能力开关都用 `is True` 收窄,测试替身的 truthy Mock 不会误触发。
4. draft id 用类级计数器保证全进程唯一递增,而非 per-instance。

---

## 5. 同步侧 API:on_delta / finish / on_segment_break / on_commentary / flush_pending_sync

`gateway/stream_consumer.py:590-604 @ 863e313`
```python
    def on_delta(self, text: str) -> None:
        """Thread-safe callback — called from the agent's worker thread.

        When *text* is ``None``, signals a tool boundary: the current message
        is finalized and subsequent text will be sent as a new message so it
        appears below any tool-progress messages the gateway sent in between.
        """
        if text:
            self._queue.put(text)
        elif text is None:
            self.on_segment_break()

    def finish(self) -> None:
        """Signal that the stream is complete."""
        self._queue.put(_DONE)
```

注意 `on_delta("")` 什么都不做(空串既不入队也不是段界)。`on_segment_break`(493-495)
put `_NEW_SEGMENT`;`on_commentary`(497-500)put `(_COMMENTARY, text)`,空文本忽略。

`flush_pending_sync`(502-523)——同步屏障:

`gateway/stream_consumer.py:517-523 @ 863e313`
```python
        evt = threading.Event()
        try:
            self._queue.put((_FLUSH, evt))
        except Exception:
            return False
        return evt.wait(timeout=max(0.0, float(timeout)))
```

配套的 `_signal_flush`(535-550)集中处理"每条退出路径都要 set event":run() 里正常
底部路径(1163-1164)、溢出分片 early-continue 路径(993-994)、以及 finally 清扫
(1206-1218,run() 因取消/异常退出时把队列里残留的 _FLUSH 全部唤醒)。漏 set 不是死锁
(调用方有超时)但会白等满超时——所以三处都要盖到。

**调用方**:run.py clarify poll 前,`gateway/run.py:5021-5025 @ 863e313`:
```python
                _sc = ctx.stream_consumer_holder[0] if ctx.stream_consumer_holder else None
                _flush = getattr(_sc, "flush_pending_sync", None)
                if callable(_flush):
                    _flush(timeout=3.0)
```

**重实现要点**
1. 同步侧 API 只做入队,永不碰平台;None delta 语义重载为段界是历史契约,新设计建议显式事件。
2. 屏障的 set 责任要集中成一个幂等助手,并在消费循环所有 early-exit 路径 + finally 里调用。
3. 屏障等待方永远带超时,消费者已退出时靠 finally 清扫立即唤醒。

---

## 6. think 标签过滤:_filter_and_accumulate(614-759)

**问题**:MiniMax 等模型把 `<think>...</think>` 推理块直接混在 content 里流出。最终响应
会被 `run_agent.py _strip_think_blocks` 清洗,但流式中间帧在清洗**之前**就上屏了——
所以 consumer 必须自带一台与 CLI `_stream_delta` 等价的状态机(606-612 注释)。

核心:`_think_buffer + text` 拼成工作缓冲,循环内按 `_in_think_block` 分两态:

- **块内**(631-650):找最早闭合标签(大小写不敏感——先 `buf.lower()` 再匹配小写标签,
  628-630 注释:模型会发 `<Think>`、`<THINKING>` 等混合大小写变体);找到则丢弃块内文本、
  退出块态;没找到则只保留可能是"闭合标签前缀"的尾部(max_tag 长度)进 `_think_buffer`,
  其余整段丢弃。
- **块外**(651-713):找最早**处于块边界**的开标签。边界判定:

`gateway/stream_consumer.py:651-681 @ 863e313`
```python
            else:
                # Look for earliest opening tag at a block boundary
                # (start of text / preceded by newline + optional whitespace).
                # This prevents false positives when models *mention* tags
                # in prose (e.g. "the <think> tag is used for…").
                best_idx = -1
                best_len = 0
                for tag in self._OPEN_THINK_TAGS:
                    tag_lower = tag.lower()
                    search_start = 0
                    while True:
                        idx = lower_buf.find(tag_lower, search_start)
                        if idx == -1:
                            break
                        # Block-boundary check (mirrors cli.py logic)
                        if idx == 0:
                            is_boundary = (
                                not self._accumulated
                                or self._accumulated.endswith("\n")
                            )
                        else:
                            preceding = buf[:idx]
                            last_nl = preceding.rfind("\n")
                            if last_nl == -1:
                                is_boundary = (
                                    (not self._accumulated
                                     or self._accumulated.endswith("\n"))
                                    and preceding.strip() == ""
                                )
                            else:
                                is_boundary = preceding[last_nl + 1:].strip() == ""
```

即:标签只有出现在文本开头/换行后(前面只有空白)才算真标签,防止把散文里**提及**的
`<think>` 误吞。没找到开标签时,再检查尾部是否是某开标签的**前缀**(696-704,逐标签逐
长度试 `endswith`),是则截留进 `_think_buffer` 等下一个 delta;否则整段过
`_strip_orphan_close_tags` 后累加。

`_strip_orphan_close_tags`(715-746):无配对开标签的闭合标签(如模式切换丢了开标签时
单飞的 `</think>`)永远是噪声,连同其后空白一起剥掉;注释声明与
`agent/think_scrubber.py::StreamingThinkScrubber._strip_orphan_close_tags` 镜像,保证
流式过滤与终稿清洗行为一致。

`_flush_think_buffer`(748-758):got_done 时把截留的"疑似标签前缀"放行(仍剥孤儿闭合),
否则等待中的真实文本会丢。

**重实现要点**
1. 跨 delta 的标签匹配必须有 hold-back 缓冲:尾部可能是标签前缀就截留,长度上限=最长标签。
2. 开标签要做块边界判定(行首),否则散文提及会被吞;闭标签不需要(块内何处闭合都有效)。
3. 大小写不敏感:lower 视图上匹配 lower 标签,一套逻辑覆盖全部变体。
4. 孤儿闭合标签单独剥,与终稿清洗器共享同一算法(双路径一致性)。
5. 流结束必须 flush hold-back,否则最后几个字符静默丢失。

---

## 7. run() 主循环总览(760-1228)

### 7.1 启动:长度函数、限额、draft 解析(762-793)

`gateway/stream_consumer.py:770-779 @ 863e313`
```python
        _len_fn: "Callable[[str], int]" = (
            self.adapter.message_len_fn_for_chat(self.chat_id)
            if isinstance(self.adapter, _BasePlatformAdapter)
            else len
        )
        # Rich-capable adapters (Telegram rich messages) raise this above the
        # legacy per-message limit so a reply that fits one rich send/draft
        # isn't fragmented at 4096 while streaming.  See _raw_message_limit.
        _raw_limit = self._raw_message_limit()
        _safe_limit = max(500, _raw_limit - _len_fn(self.cfg.cursor) - 100)
```

长度函数与上限都是 **per-chat** 解析(relay 适配器一个实例前置 N 个平台:Discord 2000 /
Telegram 4096 / Slack 39000,且 Telegram 按 UTF-16 计长);`_raw_message_limit`(1858-1886)
还允许适配器用 `streaming_overflow_limit()` 把上限抬到富消息级别(Telegram Rich Message
32768),避免能装进一条富消息的回复在流式期被 4096 拆碎。安全限额留 100 + 光标长度余量。
随后 `_resolve_draft_streaming()`(§12)决定本轮是否走 draft,并领取新 draft_id。

### 7.2 队列 drain(803-831)

非阻塞 `get_nowait` 循环:文本进 `_filter_and_accumulate`;碰到 `_DONE`/`_NEW_SEGMENT`/
`_COMMENTARY`/`_FLUSH` 任一哨兵立刻 break——**一次迭代最多处理一个哨兵**,保证段界/
commentary 与其前后文本的处理顺序严格 FIFO。`_FLUSH` 同时置 `got_flush=True` 与
`got_segment_break=True`(821-828):屏障语义=像工具边界一样 finalize 当前段。

每轮迭代顶部检查 `_run_still_current()`(800-801),会话被 /new、/stop 重置后直接 return,
不再投递陈旧 delta。循环尾部 `await asyncio.sleep(0.05)`(1166)避免忙等。

### 7.3 got_done:静默标记抑制(836-853)

`gateway/stream_consumer.py:849-853 @ 863e313`
```python
                    if _is_intentional_silence_response(
                        self._clean_for_display(self._accumulated)
                    ):
                        await self._suppress_silence_marker()
                        return
```

**问题**:agent 决定不回复时输出裸控制标记(NO_REPLY / [SILENT]);网关的整响应过滤器在
非流式路径能拦住,但流式 consumer 在它跑之前就把原始标记编辑上屏了。got_done 时若终稿
恰是标记,走 `_suppress_silence_marker`(§13)撤回预览。`is_intentional_silence_response`
(gateway/response_filters.py:56-62)只匹配**恰好是**标记的响应,提及标记的正文正常投递。

### 7.4 限速判定与部分标记抑制(855-892)

`gateway/stream_consumer.py:858-872 @ 863e313`
```python
                should_edit = (
                    got_done
                    or got_segment_break
                    or commentary_text is not None
                )
                if not self.cfg.buffer_only:
                    should_edit = should_edit or (
                        (elapsed >= self._current_edit_interval
                            and self._accumulated)
                        # buffer_threshold is intentionally codepoint-based:
                        # it's a debounce heuristic ("send updates roughly
                        # every N visible characters"), not a platform-limit
                        # check. _len_fn is reserved for overflow detection.
                        or len(self._accumulated) >= self.cfg.buffer_threshold
                    )
```

哨兵事件必发;常规 tick 要求"距上次编辑 ≥ 当前间隔(可退避加倍)且有内容"或"攒满
buffer_threshold 码点"。`buffer_only`(Matrix)禁掉常规 tick。之后 883-892:若缓冲的
规范形仍可能是静默标记前缀(`is_partial_silence_marker`,如 "NO" 在通往 "NO_REPLY" 的
路上),**推迟**这个 tick 的显示——只延迟不丢弃,got_done 必然裁决(是标记则抑制,否则
照常 flush),所以碰巧以 "NO" 开头的真散文不会丢。

### 7.5 溢出分片 A:无编辑目标时封存 head(893-995)

条件:`_len_fn(_accumulated) > _safe_limit and _message_id is None`(首条消息或段界后)。
用 `_truncate_for_stream`(§9)切块,**只把前 n-1 块作为定稿消息发出**(逐块
`_send_new_chunk`,reply_to 链式串联),末块留在 `_accumulated` 继续当活动预览:

`gateway/stream_consumer.py:900-915 @ 863e313`
```python
                        # No existing message to edit (first message or after a
                        # segment break).  Seal only the overflowing head chunks
                        # as fixed messages, then keep the trailing chunk in
                        # _accumulated so the normal send/edit path below makes
                        # it the active preview.  That lets chunk 2, 3, ... keep
                        # updating in-place as later streamed deltas arrive
                        # instead of posting every split as an immutable message.
                        chunks = self._truncate_for_stream(
                            self._accumulated, _safe_limit, _len_fn,
                        )
                        if len(chunks) <= 1:
                            # A malformed/legacy adapter result must not leave
                            # this overflow branch with an unsplittable payload.
                            chunks = self._split_text_chunks(
                                self._accumulated, _safe_limit, _len_fn,
                            )
```

head 全部落地才截断 `_accumulated`(935-942);任何 head 失败则整段保留、清空编辑目标,
让 fallback 完整兜底(943-949)。任一块落地即置 `_turn_split_delivery = True`(951-959,
注释:必须在尾块发送**之前**置位,因为 fresh-final 会删除全部 tracked 预览,一旦 head
封存,活动消息不再持有全文,删除即丢已投递文本,#78541)。

got_done 时在此分支内直接终局(962-980):尾块 `_send_or_edit(finalize=True)`,
`_final_response_sent = chunks_delivered and tail_delivered`(970-971 注释引 #10748:
`_already_sent` 可能来自早前进度消息,不能作为"终稿已投"的证据),成功则记录 ledger
载荷(§18)后 return。

### 7.6 溢出分片 B:有编辑目标时 edit-split 循环(996-1035)

`gateway/stream_consumer.py:998-1035 @ 863e313`(节选)
```python
                    while (
                        _len_fn(self._accumulated) > _safe_limit
                        and self._message_id is not None
                        and self._edit_supported
                    ):
                        _cp_budget = _custom_unit_to_cp(
                            self._accumulated, _safe_limit, _len_fn,
                        )
                        split_at = self._accumulated.rfind("\n", 0, _cp_budget)
                        if split_at < _cp_budget // 2:
                            split_at = _cp_budget
                        chunk = self._accumulated[:split_at]
```

把预算内最后一个换行作为切点(不足预算一半则硬切),用 `finalize=True,
is_turn_final=False` 编辑现有消息成定稿(1010-1022 注释:这条 head 永远不会再被编辑,
必须现在拿到富文本终排,否则前面的分片渲染裸 markdown 只有最后一片是排好的;
is_turn_final=False 防 fresh-final 把"turn 已投递"记在非终稿上,#29346 语义)。
成功则 `_accumulated` 砍头、`_message_id=None`(下一轮首发尾块)、置 split 标志;
失败或已进 fallback 则 break 保全文给 fallback(1023-1029)。

之后常规帧:`display_text = _accumulated (+cursor)`,`_send_or_edit(finalize=(got_done
or got_segment_break), is_turn_final=got_done)`(1037-1053)——段界 finalize 是为
DingTalk AI Cards 这类需要显式闭合的平台,不闭合上一段会停在 loading 态(1041-1046)。

### 7.7 got_done 终局决策树(1056-1119)

先 `_notify_before_finalize()`(1056-1058,Telegram 暂停 typing,防慢速 MarkdownV2
终排期间 typing 状态闪烁)。然后按序:

1. `_fallback_final_send` → `_send_fallback_final(_accumulated)`(§10);
2. `_final_response_sent` 已置(fresh-final 在 finalize tick 已投递)→ 只补记
   `_final_content_delivered` + ledger,**不再**做第二次 finalize(1066-1074 注释:
   再编辑会重复消息/重复删除);
3. `current_update_visible and (not _adapter_requires_finalize or
   _last_edit_overflowed)` → 本 tick 的编辑已带 finalize=True 送达全文,跳过冗余终编
   (1075-1094;溢出续篇场景强制跳过——对全文再 finalize 会再次溢出拆分,把分片重复上屏);
4. `_message_id` 存在 → 显式 `_send_or_edit(finalize=True)`;失败且**这次失败本身**把
   consumer 打进 fallback(终编耗尽 flood strikes)→ 立即 `_send_fallback_final`,
   不能带着 pending fallback 返回网关,否则网关全量重发造成前缀重复(1105-1113);
5. 都不是且 `not _already_sent` → 普通 `_send_or_edit`(纯缓冲从未上屏的情况)。

每个成功分支都 `_record_turn_final_payload(_accumulated)`(§18)。

### 7.8 commentary 与段界(1121-1157)

commentary:前后各一次 `_reset_segment_state()` 包夹 `_send_commentary`(1121-1125)
——commentary 是独立完整消息,不能与流式段共享消息状态。

段界(1141-1157):**#8124 尾巴抢救**——段界编辑没把累计内容送达(flood 未升级 fallback
或已在 fallback)时,`_accumulated` 里还有用户没见过的 pre-boundary 文本,重置前必须
`_flush_segment_tail_on_edit_failure()` 发续篇,否则工具边界前生成的文本静默丢失。
然后 `_reset_segment_state(preserve_no_edit=True)`。

`__no_edit__` 哨兵例外(1127-1140 注释):平台不返回真实 message id(Signal、
github_comment webhook)时,若段界把 `_message_id` 重置为 None,每个工具边界都会重新
走"首发"路径——**一次 PR 下发出 155 条评论**的事故;保留哨兵,让全部续文最终经
`_send_fallback_final` 一次性投递。

`_reset_segment_state`(552-588):清 message_id/accumulated/ledger/last_sent/fallback
状态/段预览集,**先**把 `_last_sent_text` 的定稿文本存进 `_delivered_segment_texts`
(#65919:段界擦掉唯一投递记录后,网关的最终抑制认不出已投递响应);清终稿标志
(571-575 注释引 #29346:段界意味着刚投的是过渡铺垫不是终稿;安全性依据=got_done 在任何
reset 之前 return,run.py 只在 consumer 任务退出后读标志);draft 模式下 bump draft_id
(579-588,注释引 openclaw #32535 的 inter-tool-call text leak:每个文本块经 finalize
变成独立可见消息,下一块用新 draft 动画,不覆盖已定稿的旧 draft)。

### 7.9 取消与 finally(1168-1218)

CancelledError:best-effort 以 `finalize=True, is_turn_final=False` 补一次终排编辑
(1169-1183,注释:不 finalize 的话 Telegram 整条回复停在裸预览排版,而下面的成功标志
又抑制了网关的格式化重发);只有这次 best-effort 真成功才补置终稿标志(1187-1196 注释:
以前无条件把 already_sent 提升成 final_response_sent,导致只投了 "Let me search…" 铺垫
也抑制网关兜底)。finally:清扫队列中残留 `_FLUSH` 并唤醒等待者(1199-1218)。

**重实现要点(run 主循环)**
1. 一次迭代一个哨兵,文本尽量批量合并——顺序正确性与限速合并两者兼得。
2. 溢出分片分两形:无目标时"封存 head、尾块继续活动预览";有目标时"把现有消息定稿为 head"。
   head 一律 finalize=True(终排)+ is_turn_final=False(不冒领 turn 投递)。
3. 终局是显式优先级决策树:fallback > 已 fresh-final > 本 tick 已达 > 显式终编 > 未发补发;
   每个成功出口都要记录精确载荷。
4. 段界重置前先抢救未投递尾巴;无真实 id 的平台用哨兵防"每工具边界发一条新消息"。
5. 取消路径的投递确认只认本路径亲手的成功,不继承 already_sent。
6. 静默标记三段式:中间帧对"可能是标记前缀"只延迟;终稿恰为标记则撤回;其余照常。

---

## 8. _send_new_chunk(1241-1276)

发送封存 head 块:清洗后 `adapter.send(reply_to=上一块 id, metadata=_metadata_for_send(
final=got_done, expect_edits=True))`;成功则采纳新 id、track 预览、`_notify_new_message()`
并返回新 id 供下一块串线程;失败置 `_edit_supported=False` 并返回原 reply_to(调用方以
`new_id is None or new_id == reply_to` 判失败,925 行)。空白块直接返回 reply_to 视为跳过。

`_metadata_for_send`(324-348):合并基础 metadata + `reply_to_message_id` +
`expect_edits`(预览消息必须走 Telegram 可编辑的 legacy 发送路径)+ `notify`(final=True
时;Mattermost 用它判断线程根损坏时是否允许摊平)。

---

## 9. 分片器:_split_text_chunks / _balance_fences_across_chunks / _truncate_for_stream

- `_balance_fences_across_chunks`(1292-1302):薄委托到
  `gateway/platforms/helpers.balance_fences_across_chunks`——块尾闭合孤儿 ```、下一块重开。
- `_split_text_chunks`(1304-1328):委托 `split_text_fence_aware(prefer_paragraphs=False,
  balance_fences=True)`——换行优先切分 + 围栏平衡,fallback 发送用。
- `_truncate_for_stream`(1330-1355):**优先用适配器的 `truncate_message`**(平台自带
  词边界/围栏/表格规则,consumer 不得用纯换行切分覆盖);Base 子类传 `len_fn=`,legacy
  适配器用两参形;返回值不是 list[str] 则回退自家切分器。

**重实现要点**
1. 切分规则的权威在适配器,consumer 只在适配器缺席/返回畸形时回退。
2. 任何切分都要围栏平衡,否则中间块把后续消息拖进代码块渲染。
3. 非码点长度单位(UTF-16)统一经 `_custom_unit_to_cp` 二分折算(base.py:224-232)。

---

## 10. fallback 终投:_send_fallback_final(1357-1552)/ _send_empty_fallback_final(1554-1636)

**问题**:流式编辑中途失效(flood 打满、传输错误、平台不回 id)后,终稿必须完整送达,
且不能与已可见的部分内容重复。

`_send_fallback_final` 流程:
1. 清洗 + `ensure_closed_code_fences`(1362-1366,注释:围栏闭合要在算 continuation
   **之前**,否则只发尾部时闭合围栏到不了用户);
2. `_continuation_text`(1285-1290):终稿以已见前缀(`_fallback_prefix` 或
   `_visible_prefix()`)开头则只取余下尾部;
3. **continuation 为空**的三岔(1369-1441):
   - 适配器声明 `RESEND_FINAL_ON_EMPTY_STREAM_FALLBACK is True`(Telegram:客户端可能
     丢失/只保留部分预览)→ `_send_empty_fallback_final` 重发全文提交;返回 "ambiguous"
     (超时,可能已送达)只保 `_final_content_delivered` 防重复,"failed" 则清双标志让
     网关正常终投(1389-1398);
   - #10807:前缀来自**工具边界前的上一段**导致误判"已展示"时(final_text 非空且 ≠
     可见前缀),全文照发;
   - 真·已展示 → 补一刀去光标编辑(#7183 防冻结 ▉),置 sent/delivered 标志并
     `_record_turn_final_payload(final_text)`(1432-1440,注释:走 recorder 让 split 轮
     记 ledger 全文而非尾部,否则 #78541 对账误判 mismatch 重发已见文本);
4. per-chat 限额切块逐发,每块 flood 失败重试一次(`_fallback_flood_retry_delay` 限
   5s 内,§11);**部分成功**:置 `_already_sent`(防重复部分)但**不置**
   `_final_response_sent`(1486-1498,让网关仍投完整答案);**全失败**:连
   `_already_sent` 都清掉,放行网关再试一次(1499-1505);
5. 全部成功后删除冻结的部分预览——仅当 `continuation == final_text`(重发的是全文)且
   未置 preserve 标志(1513-1537 注释:只发尾部时部分消息**就是**答案的头,删掉它=
   "Gemini 只发了后半"症状);置全部成功标志 + 记录载荷。

`_send_empty_fallback_final`:重发全文,成功后删除**仅当前段**的预览
(`_segment_preview_message_ids`,1561-1566:段界故意保留全轮集合给 fresh-final,失败
恢复绝不能删早前定稿的铺垫/commentary);三态返回 delivered/failed/ambiguous,
`_send_failure_may_have_delivered`(1638-1645)以 "timeout" 字样 + `retryable is not
True` 判 ambiguous。**载荷记录刻意绕开 recorder 记 verbatim**(1620-1631 注释:此路径
刚删掉了封存段预览,屏上只剩这条新消息;若记 ledger 会为刚删除的文本冒领投递,网关抑制
后用户只剩答案的一小截——#78541 的吞吃换个方式复活)。

**重实现要点**
1. fallback 的核心是前缀去重:只发未见尾部;但要识别"前缀属于上一段"的假阳性(#10807)。
2. 部分成功/全失败/全成功三态对网关暴露不同标志组合,兜底责任精确移交。
3. 删旧预览只在"重发了全文"时安全;发尾部时旧消息是内容本体。
4. 超时是不可判定态:单独一档 ambiguous,保守保去重、放弃确认。
5. 载荷记录的语义 = "此刻屏上实际可见的东西",删除了什么就不能记什么。

---

## 11. flood 退避(1647-1667 + _send_or_edit 内 2305-2359)

判定:`_is_flood_error`(1663-1667)——错误串含 "flood"/"retry after"/"rate"。
编辑路径策略(2305-2334):strike 计数 +1,`_current_edit_interval` 翻倍封顶 10s;
strike < 3 时只减速不禁用;打满 3 次或非 flood 错误 → 进 fallback 模式(记
`_fallback_prefix`、禁编辑、best-effort 去光标)。成功编辑把 strike 清零(2243-2244)。
**turn-final 特例**(2317-2325):适配器声明 `FALLBACK_ON_FINAL_EDIT_FLOOD is True` 时,
终编碰 flood 不再攒 strike 直接 fallback——终稿投递不等退避;且跳过去光标的化妆编辑
(2353-2359:再编辑消耗同一份 flood 预算,拖延载着答案的 fallback 发送)。
fallback 侧:`_fallback_flood_retry_delay`(1647-1661)取 `retry_after`(缺省 3s),
超过 `_max_fallback_flood_retry_seconds=5.0` 就不等了,把终投让给网关(255-260 注释:
Telegram 适配器编辑重试本身已 bound 在 5s,流任务不该为更长冷却挂住)。

**重实现要点**
1. 中间帧编辑失败可以慢慢退(指数间隔),终稿投递不能等——两种预算分开。
2. strike 要连续计数、成功清零;永久禁用是最后手段。
3. 退避上限(10s)与 fallback 等待上限(5s)都要封顶,长冷却直接换路径而非硬等。

---

## 12. draft streaming(1669-1750 + _send_or_edit 2109-2136)

**问题**:Telegram Bot API 9.5 的 `sendMessageDraft` 能渲染原生打字动画(比编辑流畅、
无 flood 编辑成本),但 draft 没有 message_id、仅 DM 可用、需要 ptb 22.6+。

`_resolve_draft_streaming`(1669-1710):transport=edit/off → False;非 Base 适配器
(测试 Mock)→ False;否则问 `adapter.supports_draft_streaming(chat_type, metadata)`
(base.py:2943 起,考虑 DM-only 与版本门);"draft" 被拒时 log 降级到 edit。
run() 开头解析一次,领新 draft_id(786-793)。

`_send_or_edit` 中的路由(2120-2136):仅当 `_use_draft_streaming and not finalize and
_message_id is None` 才发 draft 帧——finalize 帧必须是真消息(draft 无法定稿,常规
sendMessage 天然清除客户端 draft 并留下历史记录);段界后已建立 edit 目标的段继续走编辑。
帧去重:与 `_last_sent_text` 相同则跳过。**draft 成功不置 `_already_sent`**(2129-2134
注释:该标志门控网关兜底终投,draft 不是真消息,终投必须发生)。

`_send_draft_frame`(1712-1750):首次失败即永久禁用本轮 draft(`_draft_failures += 1`,
`_use_draft_streaming = False`),后续帧回落编辑路径(有 flood 退避可自适应)。
段界 bump draft_id(586-588,§7.8)。

**重实现要点**
1. draft 是纯预览通道:终稿必须走真消息;draft 成功绝不设置任何"已投递"标志。
2. 能力探测集中在适配器钩子,consumer 只问结果;探测异常一律降级。
3. 失败一次就降级到编辑,不重试 draft——预览通道不值得复杂恢复逻辑。
4. draft_id 每响应/每段递增,复用 id 才有动画连续性,跨段必须换 id 防覆盖已定稿内容。

---

## 13. 静默标记撤回:_suppress_silence_marker(2015-2059)

删除全部预览 id + 当前 message_id(best-effort `delete_message`),然后**清空一切状态并
把标志全部置 False**:

`gateway/stream_consumer.py:2046-2055 @ 863e313`
```python
        self._preview_message_ids = set()
        self._message_id = None
        self._accumulated = ""
        self._stream_ledger = ""
        self._last_sent_text = ""
        self._already_sent = False
        self._final_response_sent = False
        self._final_content_delivered = False
        self._delivered_final_text = None
        self._turn_split_delivery = False
```

docstring(2024-2029)点明协议:什么都没投递,所以标志必须 False——网关不会把标记当成
已投递回复;而网关自己的整响应过滤会把标记变 "",所以也不会有兜底发送。`_already_sent`
同样清掉,防网关的 already_sent 短路。

---

## 14. _send_or_edit 全解(2061-2410)

出站统一管道:`_clean_for_display`(剥 MEDIA:/[[audio_as_voice]] 指令,1228-1239,
委托 base 的 `strip_media_directives_for_display`;媒体文件由 run.py 的
`_deliver_media_from_response` 流后单独投递)→ `ensure_closed_code_fences` →
纯光标/空白帧短路返回 True(2083-2092)→ **_MIN_NEW_MSG_CHARS 门**(2093-2107):

`gateway/stream_consumer.py:2102-2107 @ 863e313`
```python
        _MIN_NEW_MSG_CHARS = 4
        if (self._message_id is None
                and self.cfg.cursor
                and self.cfg.cursor in text
                and len(_visible_stripped) < _MIN_NEW_MSG_CHARS):
            return True  # too short for a standalone message — accumulate more
```

快速工具连打时模型常先吐 1-2 个 token 再转工具调用,"X ▉" 独立消息若后续去光标编辑被限
流,▉ 白块(tofu)永久留屏(Telegram/Matrix 实测),所以首发门槛 4 个可见字符;已有消息
的编辑不受限。

**编辑分支**(2139-2364):no-op 跳过(内容与上次相同;例外:REQUIRES_EDIT_FINALIZE
适配器的 finalize 帧必须发,streaming UI 才能退出进行中状态,2141-2150)→ fresh-final
门(§15)→ `_edit_message`(385-412:带 finalize kwarg 的适配器契约;metadata 仅在
签名支持时传)→ 成功:track 续篇 id;**续篇采纳**(2227-2240):适配器把超长编辑拆成
原消息+N 续篇时,`result.message_id` 是最后一条续篇——采纳新 id、清 `_last_sent_text`、
置 `_last_edit_overflowed` 与 `_turn_split_delivery`、fire `_notify_new_message`(工具
气泡要排到新续篇下方)→ 失败:先看 #36965/#25349 场景(2247-2271:终稿化妆编辑失败但
全文已可见、只剩光标——置 `_final_content_delivered` 并记录载荷,防网关把长答案重发一遍;
2264-2270 注释:post-#78541 若不记录,split 轮对账 mismatch 又会重发)→
**partial_overflow**(2272-2299):Telegram 只送达部分溢出块——采纳
`last_message_id`,记 `delivered_prefix` 为 fallback 前缀,置 preserve 标志(前缀是正式
内容),进 fallback 且禁编辑,返回 False 让 got_done 的 fallback 只补尾部 → 否则 flood
strike 逻辑(§11)。

**首发分支**(2365-2407):`adapter.send(reply_to=_initial_reply_to_id, expect_edits=
True)` 落到正确话题/线程;成功但无 message_id → `_message_id = "__no_edit__"` 哨兵 +
进 fallback(2391-2397,防每 delta/每段界重进首发路径);fire `_notify_new_message`
(网关把工具进度气泡"线性化":内容气泡出现后,下一个 tool.started 开新气泡在其下方,
而不是编辑上方旧气泡——on_new_message 在 run.py:4516-4520 绑定为
`ctx.progress_queue.put(("__reset__",))`)。首发失败 → `_edit_supported = False`。

---

## 15. fresh-final 机制(1836-2013 + _send_or_edit 2151-2204)

**问题**(openclaw/openclaw#72038):慢流(reasoning 模型)场景,预览消息在第一个 token
时创建,几分钟后才完成;Telegram 编辑不更新可见时间戳,最终答案挂着"几分钟前"的时间戳,
且在会话列表里不置顶。**解**:finalize 时若预览已存活 ≥ 阈值,改为发**新消息**+尽力删除
全部旧预览,让时间戳=完成时刻。

三个判定件:
- `_should_send_fresh_final`(1836-1856):阈值>0、有真实 id(非 None/`__no_edit__`)、
  `monotonic() - _message_created_ts >= threshold`。
- `_adapter_prefers_fresh_final`(1907-1935):适配器无关时间阈值的主动偏好——Telegram
  的 `sendRichMessage` 发送路径渲染比 MarkdownV2 编辑路径更富,finalize 走编辑会肉眼
  降级预览,宁可重发+删除;`is True` 收窄防 Mock。
- gate 组合逻辑(2184-2204):

`gateway/stream_consumer.py:2184-2204 @ 863e313`
```python
                    _has_prefers_hook = (
                        hasattr(type(self.adapter),
                                "prefers_fresh_final_streaming")
                        or "prefers_fresh_final_streaming"
                            in getattr(self.adapter, "__dict__", {})
                    )
                    _prefers_fresh = self._adapter_prefers_fresh_final(text)
                    if (
                        finalize
                        and (
                            _prefers_fresh
                            or (
                                not _has_prefers_hook
                                and self._should_send_fresh_final()
                            )
                        )
                        and await self._try_fresh_final(
                            text, is_turn_final=is_turn_final,
                        )
                    ):
                        return True
```

**#47048**:适配器**显式**返回 False 时,时间阈值不得越权——Telegram 上 fresh-final 发
Rich Message 与已可见的 MarkdownV2 预览重叠(旧消息只是 best-effort 删除,删不掉就双份
在屏)。所以钩子存在即拥有否决权;没有钩子的适配器才吃时间阈值。钩子存在性检查查**类**
+ 实例 `__dict__`(MagicMock 访问即创建属性,查实例会误报)。

`_try_fresh_final`(1937-2013):
- **#78541 前置守卫**(1961-1962):`_turn_split_delivery` 时直接 False——split 轮的
  `text` 只是尾块,删封存 head=抹掉已收到的文本,全文在屏上无处可寻;保留旧消息走编辑。
- 发新消息(final=True metadata)→ 成功后 best-effort 删 `_preview_message_ids` ∪ 当前
  id(跳过刚发的新 id)→ 采纳新 id + 刷新 `_message_created_ts`;无 id 则 `__no_edit__`。
- `is_turn_final=True` 才置 `_final_response_sent`(1943-1947:工具边界的段 finalize 是
  铺垫,不得冒领 turn 投递,#29346)。

**网关侧开关**:`gateway/run.py:23806-23815 @ 863e313`
```python
        # Fresh-final applies to Telegram only — other
        # platforms either edit in place cheaply (Discord,
        # Slack) or don't have the timestamp-on-edit /
        # edit-timestamp-stays-stale problem.
        # (Ported from openclaw/openclaw#72038.)
        _fresh_final_secs = (
            float(getattr(scfg, "fresh_final_after_seconds", 0.0) or 0.0)
            if source.platform == Platform.TELEGRAM
            else 0.0
        )
```

**重实现要点**
1. "编辑不刷时间戳"是平台属性,fresh-final 必须 per-platform 开关,默认关。
2. 适配器显式偏好 > 时间阈值;显式 False 是否决不是弃权。
3. 重发+删除只在"新消息持有全文"时安全;分片投递轮一律禁用(先置 split 标志再发尾块)。
4. 删除永远 best-effort,可见性(新消息在)优先于整洁(旧预览删净)。
5. 采纳新 id 后要刷新 created_ts,保证后续 finalize 重试的判定一致。

---

## 16. _send_commentary(1806-1834)

发送完整过渡消息(如工具间的解说)。**刻意不置 `_already_sent`**:

`gateway/stream_consumer.py:1817-1830 @ 863e313`
```python
            # Note: do NOT set _already_sent = True here.
            # Commentary messages are interim status updates (e.g. "Using browser
            # tool..."), not the final response. Setting already_sent would cause
            # the final response to be incorrectly suppressed when there are
            # multiple tool calls. See: https://github.com/NousResearch/hermes-agent/issues/10454
            if result.success:
                # Commentary counts as fresh content — close off any
                # stale tool bubble above it so the next tool starts a
                # new bubble below.
                self._notify_new_message()
                # Record the exact delivered text so run.py can confirm whether
                # an interim "preview" actually carried the final response, vs.
                # unrelated commentary delivered during a session split (#14238).
                self._delivered_commentary_texts.append(text)
            return result.success
```

#10454:多工具轮里 commentary 置 already_sent 会让终稿被抑制。#14238:但要记录精确文本,
因为压缩/会话切分时终稿可能恰好以 commentary 形式提前送达——`has_delivered_text` 靠这个
列表精确匹配,而不是靠布尔标志猜。

---

## 17. 最终去重协议:_stream_ledger / _record_turn_final_payload / delivered_final_matches / has_delivered_text

这是全文件最精巧的部分:consumer 与网关"正常最终发送"路径之间的**对账协议**。

**问题演化**:
- 原始:consumer 置 `final_response_sent` → 网关信标志抑制终投。
- **#71643**:finalize 编辑**成功**却只载有最后一帧预览快照——快照与流结束之间生成的
  delta 从未到达任何 API 调用,标志照设,网关抑制,用户丢尾巴。→ 标志不可信,须记录
  **精确载荷**事后对账。
- **#78541**:多消息分片投递轮,`_accumulated` 只剩尾块,记录的载荷是尾部 → 对账
  mismatch → 网关在用户已收到的答案上再发全文;或反向:payload-less split 继承 legacy
  trust → Telegram 群里早期/部分分片投递后整条回复被吞。→ 引入 `_stream_ledger`
  (不随封存截断的段全文)与 `_turn_split_delivery` 标志。

`_record_turn_final_payload`(421-441):

`gateway/stream_consumer.py:436-441 @ 863e313`
```python
        source = text or ""
        if self._turn_split_delivery and self._stream_ledger:
            source = self._stream_ledger
        self._delivered_final_text = ensure_closed_code_fences(
            self._clean_for_display(source)
        ).strip()
```

split 轮用 ledger 全文替换调用方给的尾块;归一化(剥媒体指令+闭围栏+strip)与出站管道
一致,保证与网关手里的 `final_response` 可比。

`delivered_final_matches`(443-478)三态:
- **True**:记录载荷 == 目标(或 `has_delivered_text` 在段/commentary 历史里精确命中,
  474-477——终稿可能在段界前就以别的记录送达);抑制安全。
- **False**:有记录但明确不符,**或** payload-less split(467-470,#78541 拒绝 legacy
  trust);网关必须终投。
- **None**:非 split 且无记录(前 record 时代路径)——网关保留旧的信标志行为,不回退
  ambiguous-timeout 去重(457-460)。

`has_delivered_text`(480-491):目标与"可见前缀(去光标)/ commentary 历史 / 段历史"
逐一 strip 后精确相等。

**网关消费端**(两处):
1. `_stream_confirmed_final_delivery`(run.py:25071-25106):`final_response_sent` 为
   True 时仍过 matcher,仅 **False** 推翻标志;`previewed`(interim 回调声称见过终稿)
   时用 `has_delivered_text` 精确验证(#14238)。
2. 抑制决策(run.py:25862-25932):`final_content_delivered` 同样过 matcher;
   `_stale_finalized`(matcher 返回 False)时不但不抑制,还优先尝试**把预览编辑成全文**
   (25920-25929,一条修正消息优于两条;split 轮除外——message_id 只是最后一块,编辑它
   会错),编辑失败则放行正常终投。空响应哨兵 "(empty)" 与 plugin 转换过的响应永不抑制。

**重实现要点**
1. 去重要三态:确认送达/确认未达/不可判——不可判档位保护既有超时去重语义。
2. "记录什么"的唯一准则是"此刻屏上可见的整体":split 记 ledger 全文(head 在屏),
   删除式恢复记 verbatim(head 已删,§10)。
3. 记录与比较两侧用同一归一化管道,否则永远 mismatch。
4. 布尔标志只作快路径,任何抑制决策前都要过载荷对账。
5. 段界/commentary 的历史文本列表是第三层证据,覆盖"终稿提前以别的形态送达"的情况。

---

## 18. 调用关系图

**构建**(两条 agent 路径共享 `_build_stream_consumer_config`,run.py:23758-23825):
- in-process 路径(run.py:4500-4534):`on_missing_cursor="raise"`——不支持编辑的平台
  (QQ/WeChat)直接 RuntimeError 跳过流式(23788-23797:没有编辑能力时首条部分消息永远
  无法更新,会造成部分+完整双消息);Matrix 清空 cursor 且 `buffer_only=True`
  (23799-23805,部分客户端把 ▉ 渲染成 tofu);fresh-final 仅 Telegram。consumer 带
  `on_new_message=progress_queue.put(("__reset__",))`(工具气泡线性化)、
  `on_before_finalize=pause_typing`(Telegram)、`run_still_current`。
- proxy 路径(run.py:23945-23964):`on_missing_cursor="fallback"`(无 cursor 也照流)。

**任务生命周期**:
- in-process:`_start_stream_consumer` 轮询 holder 最多 10s 后 `run()`(24852-24862,
  consumer 在线程池内 agent 构建后才创建);agent 线程 `run_conversation` 返回后
  `finish()`(5449-5451);外层 `wait_for(stream_task, 5.0)` 超时则 cancel
  (25789-25812)。
- proxy:SSE 循环把 delta 喂 `on_delta`,结束 `finish()` + `wait_for 5s` / cancel
  (24069-24074)。

**事件喂入**(新 seam):`GatewayEventDispatcher`(gateway/stream_dispatch.py:88-99)
把类型化事件路由给**适配器**的 `render_message_event(event, sink)`,Base 默认实现
(gateway/platforms/base.py:3052-3063)1:1 映射回 consumer 原语:

```python
        if isinstance(event, MessageChunk):
            if event.text:
                sink.on_delta(event.text)
        elif isinstance(event, MessageStop):
            # An intermediate stop (text → tool → text) is a segment break;
            # the terminal stop is signalled by the gateway via finish(),
            # not here, so we only break segments on non-final stops.
            if not event.final:
                sink.on_segment_break()
        elif isinstance(event, Commentary):
            if event.text:
                sink.on_commentary(event.text)
```

即:MessageChunk→on_delta;**非终**MessageStop→段界(终态 stop 由网关 finish() 发,
不在此处);Commentary→on_commentary。dispatcher 自身无平台知识、无 asyncio,是 agent
工作线程可直接调用的同步路由器(stream_dispatch.py:16-18);工具事件走独立的进度队列,
与文本流不再赛跑(9-14)。旧路径(直接回调)仍在:run.py:4526-4531 的
`_stream_delta_cb` 直接 `consumer.on_delta` 并 tee 给流式 TTS(#60671);
`_interim_assistant_cb`(4544-4553)按 `already_streamed` 分流 on_segment_break /
on_commentary。

**结果消费**:§17 的两处 + `already_sent` / `message_id` 属性(350-363)。

---

## 19. 文档-代码冲突候选(▲)与观察(◇)

1. ▲ **模块头 docstring 过时**(stream_consumer.py:10-11):"Design: Uses the edit
   transport… This is universally supported" 描述的是 legacy 设计;代码已有三种 transport
   (edit/draft/auto,127-153)与 Telegram 原生 draft 路径(1669-1750),docstring 未更新。
2. ▲ **头部 Credit 的 issue 号疑指上游**(stream_consumer.py:13):`#774/#1312/#798/#697`
   与正文引用的 5 位数 hermes issue(#71643 等)不在同一量级,应是早期/上游仓库编号,
   读者按本仓库 issue 检索会落空。
3. ◇ 注释里混用两个 issue 空间:`openclaw/openclaw#72038`、`#32535` 显式标注了外部仓库,
   而 `#78541/#71643/#65919/#10454/#14238/#8124/#10807/#7183/#36965/#25349/#29346/
   #47048/#10748/#51828/#33793/#34517/#45517/#10748` 为本仓库编号;10454 一处带完整 URL
   (1821),其余裸号,溯源便利性不一致。
4. ◇ website/docs 无 stream consumer 专章(developer-guide/agent-loop.md 只在回调表里
   提到 `stream_delta_callback` 一行),本文件的行为契约(去重协议、fallback 语义)只存在
   于代码注释——地图上这是一块作者未绘制的区域,而非冲突。
5. ◇ `escape_code_fences_for_display`(57-72)在本文件内无调用点,是导出给其它模块的
   工具函数;单看本文件会误以为死代码。

---

## 20. 总结:可迁移的设计骨架

1. **单队列单消费者**:同步生产 put,异步消费独占状态与 I/O;哨兵对象承载控制流。
2. **全量编辑而非增量**:每帧发累计全文,丢帧免费;限速=时间间隔 ∪ 字符阈值,双门任一即发。
3. **失败阶梯**:no-op 跳过 → 指数退避(3 strikes)→ 永久禁编辑 → 前缀去重的 fallback
   终投 → 完全让位网关;每级对上层暴露精确的责任移交标志。
4. **投递证据分层**:布尔标志(快路径)+ 精确载荷(对账)+ 分片标志(载荷语义修正)+
   历史文本列表(异形送达);三态对账保护每一代修复的语义。
5. **平台差异全部下沉适配器钩子**(长度单位、上限、切分、draft 支持、fresh-final 偏好、
   finalize 需求、fallback 重发偏好),consumer 用 `is True` 收窄读取,Mock 免疫。
6. **每一条注释里的 issue 号都是一次真实事故**:155 条 PR 评论(`__no_edit__`)、被吞的
   Telegram 群回复(#78541)、丢失的尾巴(#71643)、双份长答案(#36965)、冻结的 ▉
   (#7183)——本文件是"流式投递所有已知失败模式"的活清单。
