# R5 底稿 · 上下文压缩

范围:`agent/context_compressor.py`(6883 行)、`agent/conversation_compression.py`(4014 行)、`agent/manual_compression_feedback.py`(120 行),全部 L1 精读;基线 `863e31318553cda8ad61df681d08175364d4164b`。所有行号实测于该 commit。

**一句话结论:五条 R1 标记全部证实(其中 ▲1/▲4/▲5 实际机制远比标记描述丰富),压缩子系统 = "策略层 ContextCompressor(纯算法,可测)+ 宿主层 compress_context(锁/栅栏/超时/落库)+ 反馈层 manual_compression_feedback(纯文案)"三层分工。**

---

## 0. 三个文件的分工与全景

- `context_compressor.py`:`ContextCompressor(ContextEngine)` — 默认上下文引擎。纯策略/算法层:触发判定、确定性剪枝、边界切分、摘要生成、摘要消息装配、微压缩(micro-compaction)。不直接拥有 agent 引用,持久化只通过被注入的 `_session_db` duck-typed 接口。
- `conversation_compression.py`:从 AIAgent 抽出的宿主层。`compress_context()` 负责并发锁、提交栅栏(commit fence)、超时包装、in-place 落库/会话轮转(rotation)、system prompt 保持、记忆/上下文引擎边界通知、遥测。另含启动可行性探测 `check_compression_model_feasibility` 和图片缩小恢复 `try_shrink_image_parts_in_messages`。
- `manual_compression_feedback.py`:手动 `/compress` 的用户可见文案生成(纯函数,无副作用),被 `cli.py:11131,11245`、`gateway/slash_commands.py:4036,4264`、`tui_gateway/methods_session.py` 等消费。

类头对算法的自述,`agent/context_compressor.py:1318-1327 @ 863e313`:

```python
class ContextCompressor(ContextEngine):
    """Default context engine — compresses conversation context via lossy summarization.

    Algorithm:
      1. Prune old tool results (cheap, no LLM call)
      2. Protect head messages (system prompt + first exchange)
      3. Protect tail messages by token budget (most recent ~20K tokens)
      4. Summarize middle turns with structured LLM prompt
      5. On subsequent compactions, iteratively update the previous summary
    """
```

---

## 1. 定案 ▲1「压缩触发决策:双重测量去噪 + 防抖断路器」——**证实,且实际是"双测量 + 一次防抖 + 三个独立断路器 + 定时探针 + 持久化"**

### 1.1 阈值怎么算

触发点 = `effective_input_budget × threshold_percent`,并叠加四层修正。`agent/context_compressor.py:2210-2250 @ 863e313`:

```python
    @staticmethod
    def _compute_threshold_tokens(
        context_length: int, threshold_percent: float, max_tokens: int | None = None,
    ) -> int:
        ...
        effective_window = context_length - (max_tokens or 0)
        if effective_window <= 0:
            effective_window = context_length
        pct_value = int(effective_window * threshold_percent)
        floored = max(pct_value, MINIMUM_CONTEXT_LENGTH)
        if effective_window > 0 and floored >= effective_window:
            return max(1, min(int(effective_window * ContextCompressor._MIN_CTX_TRIGGER_RATIO),
                              effective_window - 1))
        return floored
```

- 输出预留:窗口先减去 `max_tokens`(#43547,大 max_tokens 会把可用输入压小);
- 64K 下限 `MINIMUM_CONTEXT_LENGTH`;下限 ≥ 窗口时退化为 85% 触发(`_MIN_CTX_TRIGGER_RATIO = 0.85`,:2135,#14690);
- 小窗口地板(raise-only):<512K 的模型阈值比例至少 75%,`agent/context_compressor.py:664-665 @ 863e313`:

```python
_SMALL_CTX_WINDOW_LIMIT = 512_000
_SMALL_CTX_THRESHOLD_PERCENT = 0.75
```

理由(:657-663 注释):50% 触发下 128K-262K 模型每压完 1-2 轮又触发,不可压缩地板(system prompt + 工具 schema + 保护尾 + 滚动摘要)吃掉大部分回收量。
- 绝对 token 上限 `compression.threshold_tokens`(取比例阈值与 cap 的较小者,:2179-2191),`update_model()` 切模型后重算并重新套 cap(:2074-2081)。
- 每模型覆盖 `model_thresholds`:最长子串匹配胜出,`resolve_model_threshold`(:1292-1315,模块级导出给插件引擎复用)。

### 1.2 双重测量:粗估 vs provider 真实 prompt_tokens

标记锚点即判定入口,`agent/context_compressor.py:2629-2634 @ 863e313`:

```python
        tokens = prompt_tokens if prompt_tokens is not None else self.last_prompt_tokens
        if tokens < self.threshold_tokens:
            return False, None
        if self._automatic_compression_blocked():
            return False, self._compression_block_reason() or "blocked"
        return True, None
```

`should_compress` 每轮被调两次、用两种度量——这是反抖动裁决**不能**放在这里的直接原因,`:2506-2512 @ 863e313`:

```python
            # It must NOT live in should_compress(): that runs twice per turn
            # with two different measures (a rough preflight estimate and the
            # real post-response count, #36718), and the rough one can dip below
            # the threshold and reset the strike every turn, re-opening the loop.
            # Keying on real usage compares like with like and fires exactly once
            # per compaction.
```

**去噪路径一(粗估偏高时递延)**:`should_defer_preflight_to_real_usage(rough_tokens)`,`:2546-2586`。粗估器对 schema 密集请求故意高估;若上一次 provider 真实读数证明请求实际低于阈值,且粗估相对当时基线只增长了 `max(4096, 5%×threshold)` 以内,preflight 递延给真实读数。

**去噪路径二(压完立即防抖)**:压缩边界完成后宿主层设 `last_prompt_tokens = -1` 并置 `awaiting_real_usage_after_compression = True`,`agent/conversation_compression.py:3504-3507 @ 863e313`:

```python
        agent.context_compressor.last_compression_rough_tokens = _compressed_est
        agent.context_compressor.last_prompt_tokens = -1
        agent.context_compressor.last_completion_tokens = 0
        agent.context_compressor.awaiting_real_usage_after_compression = True
```

而递延逻辑对该态精确防"刚压完又压",`agent/context_compressor.py:2561-2572 @ 863e313`:

```python
        # ``last_prompt_tokens = -1``, but ``last_real_prompt_tokens`` still
        # holds the STALE pre-compression value (above threshold — that's why
        # compaction fired).  Without this guard that stale value defeats the
        # ``last_real_prompt_tokens >= threshold_tokens`` check below, so
        # preflight fires a SECOND compaction before the provider has reported
        # real token usage for the now-shorter conversation.  Defer for exactly
        # one turn; update_from_response() clears the flag when real usage
        # arrives.  (#36718)
        if self.awaiting_real_usage_after_compression:
            return True
```

**裁决(唯一写 strike 的地方)**:`update_from_response()` 收到真实 `prompt_tokens` 后,若 `_verify_compaction_cleared_threshold` 已被上一个完成边界武装且读数仍 ≥ 阈值,记一次"无效压缩" strike,`agent/context_compressor.py:2513-2517 @ 863e313`:

```python
            if self._verify_compaction_cleared_threshold:
                if self.last_prompt_tokens >= self.threshold_tokens:
                    self._record_ineffective_compression_verdict(
                        self._ineffective_compression_count + 1,
                    )
```

有效性的定义是"prompt 是否降到阈值下",而不是"消息数是否变少"——因为不可压缩地板(50+ 工具时 schema 即 20-30K tokens,#14695)可能独自超阈(:2497-2505 注释)。任何低于阈值的真实读数都清零 strike(:2485-2493)。

### 1.3 断路器族(blocked 的三个来源)

`_compression_block_reason`,`agent/context_compressor.py:2648-2656 @ 863e313`:

```python
        _cooldown_remaining = self._summary_failure_cooldown_until - time.monotonic()
        if _cooldown_remaining > 0:
            return f"cooldown:{_cooldown_remaining:.0f}"
        if (
            self._ineffective_compression_count >= 2
            or self._fallback_compression_streak >= 2
        ):
            return "ineffective"
        return None
```

1. **摘要失败 cooldown**(#11529 冻屏环:摘要 429 → 插 fallback → token 仍超阈 → 每轮重触发)。梯度见 §8。
2. **ineffective strikes ≥ 2**:真实读数裁决的"压了没用"。
3. **fallback streak ≥ 2**:连续两个边界只能用确定性 fallback 摘要(独立计数;普通"请求变小了"不清零它,只有健康的 LLM 摘要边界清零,`record_completed_compaction` :1830-1868)。

**恢复探针**(#14694):断路器绝不永久。被阻塞后 300 秒(`_ANTI_THRASH_RECOVERY_SECONDS = 300.0`,:2144)放行一次探针——把计数降到 1(持久化,兄弟 agent 同步解锁);若探针再失败,下一次裁决立即重新跳闸。最坏情况 = 每 300s 一次尝试,有界。恢复时钟**故意不持久化**且在第一次被阻塞评估时才懒惰武装:进程重启加载到已跳闸计数(#69872)时必须先等满整窗(#54923 "重启不得解除武装"契约),`:2733-2758`。

**持久化与多 agent 一致性**:strike、fallback streak、cooldown 三者都经 `_session_db` 读写(`_load/_persist_ineffective_compression_count` :1777-1817 等,#54923);热路径不读库,只有"本地判定为 blocked"时才 `_refresh_durable_guards()` 重读一次再复判(:2682-2694),防止另一 agent 已清除的持久行被本地陈旧快照永久阻塞。

**定案**:▲1 证实。"双重测量去噪"与"防抖"均在;"断路器"实际是三个独立断路器 + 300s 定时探针 + 三态持久化,比 R1 标记描述的机制更完整。

### 重实现要点

- 触发裁决用"真实 prompt_tokens 是否降回阈下"而非"消息数是否减少";裁决点必须唯一且只吃同种度量。
- 压缩完成后用哨兵(-1 + awaiting 标志)强制等一轮真实读数,否则粗估的陈旧值会立刻二次触发。
- 断路器要三件套:失败 cooldown(带梯度)、无效计数、降级计数;彼此语义不同不要合并。跳闸必须配定时探针,且计数要落库、重启不解除。
- 阈值计算必须扣输出预留、给小窗口抬地板、给"下限≥窗口"的退化情形留 85% 逃生口。

---

## 2. 定案 ▲4「确定性工具结果剪枝与 proactive prune 的 prompt-cache 滞回」——**证实**

### 2.1 Phase-1 剪枝的四个 pass(无 LLM)

`_prune_old_tool_results`(:2781-3065)在保护尾边界(token 预算走读 + 消息数下限,下限被钳制在 `_MAX_TAIL_MESSAGE_FLOOR = 8`,:644)之外做:

**Pass 1 去重**——标记锚点行,`agent/context_compressor.py:2884-2892 @ 863e313`:

```python
            if len(content) < 200:
                continue
            h = hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()[:12]
            if h in content_hashes:
                # This is an older duplicate — replace with back-reference
                result[i] = {**msg, "content": "[Duplicate tool output — same content as a more recent call]"}
                pruned += 1
            else:
                content_hashes[h] = (i, msg.get("tool_call_id", "?"))
```

倒序遍历,保留最新完整副本,旧的等值结果换成回指。去重是无损的,故**不受尾部保护限制**(读同一文件 5 次只留最新)。

**Pass 2 降级**:>200 字符(proactive 路径抬到 8000)的旧工具结果换成**信息性一行摘要**(不是空白占位符),由 `_summarize_tool_result`(:1129-1289)按工具名生成,如 `[terminal] ran `npm test` -> exit 0, 47 lines output`。该函数外层 try/except 保证畸形历史参数绝不炸掉压缩(压缩会在同一历史上重试,炸=死循环,:1143-1154)。`skill_view` 结果 >5000 字符时降级带 ghost-skill 标记(§4.4)。

**Pass 3 截参**:非尾部 assistant 消息里 >500 字符的 `tool_calls.function.arguments` 在**解析后的 JSON 结构内**收缩字符串叶子再重新序列化——直接切字节会产生非法 JSON,MiniMax 等 provider 对每个后续请求 400,会话卡死(#11762),`agent/context_compressor.py:936-959 @ 863e313`(docstring 记录了事故形态)。

**Pass 4 压力降级**(#61932):多次 in-place 压缩后几乎所有消息都在保护尾里、但都是巨型已完成工具输出,摘要"空中间"无济于事。当保护区自身 > `protect_tail_tokens × 1.5` 软顶时,在保护区内部降级(始终留 `_PRESSURE_KEEP_RECent_MESSAGES = 3` 条最近消息;仍超顶则除最新一条 tool 外全降;最后手段连最新 tool 也降,:2990-3063)。压力 pass 显式无视"刚加载 skill 保护"(:3013-3017)。

### 2.2 proactive prune:独立触发 + prompt-cache 滞回

**为什么大窗口模型需要独立剪枝路径**——`prune_tool_results_only` docstring,`agent/context_compressor.py:3070-3078 @ 863e313`:

```python
        """Deterministic, no-LLM tool-result prune for the cost-oriented path.

        Runs the Phase-1 prune (``_prune_old_tool_results``) WITHOUT the
        compression summary phase, gated on ``proactive_prune_tokens`` rather
        than the (much higher) full-compression threshold. On large-window
        models ``should_compress()`` (≈50% of the window) rarely fires, so old
        tool outputs otherwise ride in history and are re-sent verbatim on every
        subsequent turn; this reclaims them early with no quality-risky LLM
        summarization.
```

1M 窗口下 50% 阈值 ≈ 500K,几乎永不触发;旧工具输出每轮原样重发,纯烧钱。所以给一个低得多的独立 token 触发点(配置 `compression.proactive_prune_tokens`,默认 0=关,`hermes_cli/config_defaults.py:593-605 @ 863e313`)。尾部保护用**消息数**(`protect_last_n`)而非 `tail_token_budget`——后者从 50% 阈值派生(1M 窗口≈100K tokens),会把整个会话都"保护"起来剪不到任何东西(:3080-3084)。

**滞回怎么保 prompt cache**——PROMPT-CACHE CONTRACT,`agent/context_compressor.py:3096-3106 @ 863e313`:

```python
        PROMPT-CACHE CONTRACT: a committed prune rewrites message bodies the
        provider has already seen, invalidating the cached prefix from the
        earliest rewritten message forward — exactly like a compression
        boundary. A prune therefore commits only when it reclaims
        ``proactive_prune_min_reclaim_tokens`` and disarms until message history
        has regrown a full trigger-sized runway. Below either gate the INPUT list
        object is returned unchanged — the standard no-op caller contract
        (callers gate bookkeeping on ``result is not input``).
```

两道闸:

```python
# agent/context_compressor.py:3143-3156 @ 863e313
        after = sum(_estimate_msg_budget_tokens(m) for m in pruned_msgs)
        reclaimed = max(0, before - after)
        if reclaimed < self.proactive_prune_min_reclaim_tokens:
            return messages, 0
        ...
        runway = max(
            reclaimed,
            self.proactive_prune_tokens,
            self.proactive_prune_min_reclaim_tokens,
        )
        next_rearm_tokens = after + runway
```

- 最小回收闸(默认 4096 tokens):不够本就不提交,避免"每新增一个 tool pair 就把一个老 pair 挤出尾部→每轮重写→每轮破缓存";
- 复位跑道(rearm runway):提交后记录 `after + runway` 为下次允许点(§入口闸 `before < self._proactive_prune_rearm_tokens` 即返回,:3116-3117),即 prompt 必须**重新长回刚回收的量级**才允许下一次破缓存的重写——这就是滞回。跑道值经 `archive_and_compact(..., model_config_patch=...)` 与剪枝结果**同事务**落库(:3160-3166),重启后 `_load_proactive_prune_rearm_tokens` 恢复(:1729-1745);换模型时同时清内存值与持久值(:2126-2128);一次完整压缩边界把跑道清零(:6858 及宿主层 `model_config_patch={KEY: None}`,agent/conversation_compression.py:3203-3205)。
- 能力闸:绑定的 session store 没有 `archive_and_compact`(无法原子提交)则直接不扫(:3122-3129);DB 提交失败则整体放弃、返回原列表(:3167-3173)。

**定案**:▲4 证实。两问都有明确代码答案:独立路径是因为大窗口下主阈值失效 + 尾预算派生失真;滞回 = 最小回收闸 + 持久化复位跑道,把破缓存从"每轮"摊薄成"episodic"。

### 重实现要点

- 剪枝分层:无损去重(可进保护区)→ 信息性降级(带工具语义的一行摘要,绝不用空白占位)→ 结构内 JSON 截参(保证合法性)→ 压力降级(保护区超软顶时的逃生口)。
- 任何"重写已发送历史"的优化都等价一次 prompt-cache 破坏,必须配:最小收益闸 + 再武装跑道 + 跑道持久化,并与被重写的转录同事务提交。
- 剪枝函数遵守 no-op 契约:无变更时返回**输入对象本身**,调用方用 `is` 判定是否需要记账。

---

## 3. 支撑机制:头/尾保护与边界切分(为 §4/§5 铺底,简记)

- 头保护:system prompt 永远隐式保护;`protect_first_n`(默认 3)只在**第一次**压缩生效,之后衰减为 0(#11996 早期轮次"化石化"跨子会话永生),重启后靠头部区域是否存在 handoff 摘要推断已衰减态。`agent/context_compressor.py:4759-4773 @ 863e313`:

```python
        if self.compression_count >= 1 or self._previous_summary:
            return 0
        if messages and self.protect_first_n > 0:
            ...
            if any(
                self._is_context_summary_message(msg)
                for msg in messages[first_non_system:restart_probe_end]
            ):
                return 0
        return self.protect_first_n
```

- 尾切分 `_find_tail_cut_by_tokens`(:5119-5253):从尾倒走累计 token 至 `tail_token_budget × 1.5` 软顶;整个转录都装得下时用裸预算重走(#40803 无限压缩环);随后依次锚定——不切开 tool 组(`_align_boundary_backward`)、最后一条**可行动**用户消息必须在尾里(#10896:用户最新请求被压进中间区,SUMMARY_PREFIX 又叫模型只理睬摘要后的消息,任务凭空消失)、用户消息在 `head_end` 位置被夹时前推整个 turn-pair(#22523 因果耦合:半个 pair 被摘要成"待办"导致已完成任务重做)、最后一条可见 assistant 回复必须在尾里(#29824:用户刚读过的回复变成"Context compaction"方块)、可配置的最后 N 条真实用户消息(`min_tail_user_messages`)。锚定链单调(尾只增不减),最后前对齐一次防止强抬的下限落进 tool 组中间(:5241-5253)。
- 孤儿修复 `_sanitize_tool_pairs`(:4637-4713):压缩后孤儿 tool result 删除、孤儿 tool_calls **剥离**(不是插桩——插桩曾被下游 `repair_message_sequence` 因 `call_id != id`(Codex Responses)静默丢弃从而复暴露孤儿,:4650-4657),剥空后补 `"(tool call removed)"` 占位内容。

### 重实现要点

- 尾保护是 token 预算 + 多重语义锚(最新用户/最新助手回复/tool 组完整性),锚只许把尾变大;锚间顺序与单调性要写成显式契约。
- 头保护要衰减,否则早期消息跨压缩永生。
- 孤儿修复选"删除/剥离"而非"插桩",避免与下游修复器的 id 语义分歧。

---

## 4. 定案 ◇3「结构化 handoff 摘要生成」——**证实**

### 4.1 handoff 前缀:摘要的"使用说明书"

`SUMMARY_PREFIX`(:100-127)开宗明义:REFERENCE ONLY、不得回答摘要里的问题、只响应摘要之后最新用户消息、话题重叠≠恢复旧任务、反向信号(stop/undo/never mind)立即终止在飞工作、记忆永远权威、**工具仍然全开**(#65848:早期版本缺这句,强 REFERENCE ONLY 措辞外溢成"工具抑制",生产上出现连续 7 轮只叙述不动手)。四代历史前缀 `_HISTORICAL_SUMMARY_PREFIXES`(:262-362)被逐字节冻结(prepend-only,`test_summary_prefix_semantics.py` 逐字节 pin),重压缩时旧前缀必须剥掉否则陈旧指令(如 "resume exactly from Active Task")永久劫持回复(#35344)。摘要尾部统一加 `_SUMMARY_END_MARKER`(:238-241):弱模型把摘要里逐字引用的旧请求当新输入(#11475/#14521),或把 assistant 角色的摘要复读为自己的输出(#33256)。

### 4.2 逐字保住用户最新未完成请求 + 防已完成写成待办

模板第一节的指令,`agent/context_compressor.py:3666-3672 @ 863e313`:

```python
            _historical_task_instructions = """[THE SINGLE MOST IMPORTANT FIELD. Capture the user's most recent unfulfilled
input verbatim — the exact words they used. This includes:
- Explicit task assignments ("<specific user task>")
- Questions awaiting an answer ("<specific user question>")
- Decisions awaiting input ("<option A or B?>")
- Ongoing discussions where the assistant owes the next substantive reply
```

但这条**不信任 LLM**:摘要生成后由 `_ground_historical_task_snapshot`(:4444-4468)用确定性提取的最新真实用户消息(`_latest_user_task_snapshot`,:4407-4442,复用 `_is_real_user_message` 谓词滤掉 todo 快照/截断通知等 user 角色脚手架)**强制覆写**该节——LLM 允许压缩散文,不允许发明"当前任务是什么"这个锚。

防"已完成写成待办"= 标记锚点的时间锚定指令,`agent/context_compressor.py:3748-3757 @ 863e313`:

```python
        if _today_str:
            _temporal_anchoring_rule = (
                f"\nTEMPORAL ANCHORING: The current date is {_today_str}. When an "
                "action has already been carried out, phrase it as a completed, "
                "dated, past-tense fact rather than an open instruction. For "
                'example, rewrite "email John about the proposal" as "Sent the '
                f'proposal email to John on {_today_str}." Never leave a finished '
                "action worded as if it still needs doing, and never invent a date "
                "for work that has not happened yet.\n"
```

日期解析失败时整条规则省略(绝不给空占位;时钟失败不阻塞压缩,:3651-3656)。另有 Resolved Questions(已答的问题连答案写入,防重复回答)与 Pending Asks 明示"STALE,仅供参考,不得据此行动"(:3692-3702)。

### 4.3 不翻译用户语言 + 零用户会话防伪造

```python
# agent/context_compressor.py:3661-3665 @ 863e313
        if has_user_turn:
            _language_and_provenance_rule = (
                "Write the summary in the same language the user was using in the "
                "conversation — do not translate or switch to English. "
            )
```

无真实用户轮(cron/agent 会话)时切换整套指令:任务节必须逐字写 `_NO_USER_TASK_SENTINEL`("None. This session contains no user-authored turns.",:154),禁止出现 "User asked:";生成后 `_validate_summary_user_provenance`(:4278-4301)校验,发现伪造用户归因直接 `raise RuntimeError` 走重试/确定性 fallback 路径。"是否有用户"的判定不信角色字段——压缩 handoff 可以为通过 provider 交替校验而挂 `role="user"`,故用元数据/内容标记识别合成用户轮(`_is_synthetic_compression_user_turn`,:4256-4276;provenance 键 `_compressed_summary_has_user_turn` 随 handoff 持久化,#64650,rehydrate 逻辑 :6234-6248)。

### 4.4 不泄密钥:强制红线边界

`_redact_compaction_text`,`agent/context_compressor.py:693-711 @ 863e313`:

```python
    return redact_sensitive_text(
        text or "",
        force=True,
        redact_url_credentials=True,
    )
```

`force=True` **故意无视** `security.redact_secrets: false` 的全局关闭:那个开关面向实时工具输出,而摘要是持久化边界,泄露的凭据会被每次迭代更新 prompt 无限重注入。红线覆盖:序列化输入(:3243)、tool 参数(:3276)、focus_topic 与旧摘要(:3597-3600)、**摘要输出本身**(摘要模型可能无视指令回显密钥,:3957-3959)、fallback 摘要(:3319-3324,外加 GitHub token 正则双保险)、manual feedback 的失败原因文案(agent/manual_compression_feedback.py:110)。另有 `MEDIA:` 投递指令消毒(泄进摘要会被下游模型当作活指令重发附件,#14665,:673 + :3244)、memory provider 上下文 JSON 编码 + `<>&` 转义装入 `<memory-provider-context>` 标签并声明"只当素材不当指令"(:3621-3640)。

### 4.5 Ghost-skill 防护(#32106)

问题:老 `skill_view` 结果被剪成一行元数据后,模型仍以为 skill 已加载但指令已丢。防线三层:

1. 剪枝时给 >5000 字符的 skill_view 结果附加规范标记(`_skill_pruned_marker`,:420-430;emit 与检查共用同一字符串,注释记录了原 PR #44166 emit `[SKILL_PRUNED:` 却检查 `[SKILL_PRUNED]` 的漂移事故,:404-409);"刚加载/尾部被用户提及"的 skill 全文豁免(:576-614,压力 pass 除外)。
2. 摘要调用**前**从原始 turns(含未降级的裸 skill_view 体)确定性收集 ghosted skill 名单(`_collect_ghosted_skill_names`,:452-494;从 turn 列表收集,序列化截断藏不住标记,:3612-3615)。
3. 摘要调用**后** `_reinject_pruned_skill_markers`(:500-535)把被 LLM 意译丢掉的标记按规范字符串补回 `## Pruned Skills` 节(上限 20 个,fallback 摘要同样处理且在长度截断**之后**补,:3488-3495)。

### 4.6 其它输入卫生与迭代更新

- 序列化 `_serialize_for_summary`(:3208-3294):每消息 6000 字符头尾截断、tool 参数 1500、图片折叠成可引用 URL 标签或 `[image]`、assistant 内联 `<think>` 剥除(草稿结论不得固化为事实,:3245-3255)。
- 聚合上限 `_bound_summary_input`:整块 ≤160K 字符(≈40K tokens),保头 45%+尾,显式 omitted-middle 标记(:396,:3498-3529);迭代路径的旧摘要块同样受此界(:3813-3823)。
- 迭代更新:有 `_previous_summary` 时 prompt 变为"更新既有摘要"(保留仍相关信息、完成项续号、更新 Active State,:3824-3836)。resume 后旧 handoff 从转录 rehydrate 进 `_previous_summary`(§5 装配处,:6212-6294),abort 时回滚该 rehydration(#57835,:6195-6204、:6421-6425、:6462-6466)。
- 摘要预算:`max(2000, min(20%×内容, min(5%×窗口, 10000)))`(:371-377、:3184-3193),但**只作 prompt 提示,绝不上 wire 的 max_tokens**——思考型模型会把 cap 烧在推理上产生截断摘要与压缩循环(:3869-3878)。

**定案**:◇3 证实。五个子项(逐字任务锚、防完成写成待办、语言保持、红线、ghost-skill)全部有独立机制,且任务锚与 ghost-skill 都是"prompt 指令 + 确定性后校正"的双保险结构。

### 重实现要点

- handoff 前缀是产品级 prompt 工程资产:逐字节冻结历史版本、重压缩时剥旧贴新;摘要首尾都要显式边界标记。
- 关键锚(当前任务、prune 标记、用户存在性)不能只靠 prompt 指令,必须生成后确定性覆写/回注/校验。
- 摘要是持久化边界:红线必须 force、双向(输入+输出)、覆盖一切旁路输入(focus、旧摘要、memory context)。
- 摘要调用不设 wire 级输出上限;输入侧才设界(逐消息 + 聚合双层)。

---

## 5. 定案 ◇2「摘要消息的角色交替修复与 provider 兼容护栏」——**证实**

### 5.1 Mistral 交替模板:按"模板可见角色"选角

`_template_visible_role`,`agent/context_compressor.py:204-211 @ 863e313`:

```python
    if not isinstance(message, dict):
        return None
    role = message.get("role")
    if role == "tool":
        return None
    if role == "assistant" and message.get("tool_calls"):
        return None
    return role
```

Mistral 系模板(Devstral/Mistral Small 3.x/Magistral)渲染时强制 user/assistant 交替但**豁免 tool 流**。按字面邻居选角的经典失败(:193-200 docstring):保护头以 `[user, assistant(tool_calls), tool]` 结尾,字面末角色是 tool → 摘要被钉成 user;模板只数到 user → user→user,llama.cpp/Mistral 后端整请求 Jinja 交替错误 HTTP 500;摘要已持久化,每次重试重放同一污染历史,**会话不可恢复**。修复:头尾邻居角色都取模板可见角色再选角(:6578-6607)。

### 5.2 选角与兜底级联(标记锚点)

`agent/context_compressor.py:6661-6668 @ 863e313`:

```python
        if (
            last_head_role is None
            or last_head_role in {"assistant", "tool"}
            or _force_user_leading
        ):
            summary_role = "user"
        else:
            summary_role = "assistant"
```

其后:若与尾首可见角色撞车且翻转不撞头,则翻转(:6671-6681);两头都撞时放弃独立消息,**并入尾首消息**(`_merge_summary_into_tail`,:6687)。合并有两种形态(:6727-6761):强制 user 引导时摘要前置(摘要 + END_MARKER + 原尾内容,让真实请求出现在摘要边界之后);普通交替合并时原尾内容用 `[PRIOR CONTEXT ...]` / `[END OF PRIOR CONTEXT — COMPACTION SUMMARY BELOW]` 定界包裹在前、摘要在后、END_MARKER 收尾——防"幽灵消息"泄漏。合并目标默认字面尾首(豁免行是理想载体,不新增可见轮次);仅强制修复路径改指第一条模板可见行(:6709-6726)。`classify_summary_content` 能区分 standalone/merged 两形态(:6195-4221),重压缩时 merged handoff 的真实前尾内容会被解包保留而非连摘要一起丢(#47274,`_strip_context_summary_handoff_message` :4507-4624)。

### 5.3 Anthropic/Bedrock 护栏与零用户护栏

```python
# agent/context_compressor.py:6608-6615 @ 863e313
        # When the only protected head message is the system prompt, the
        # summary becomes the first *visible* message in the API request
        # (most adapters — Anthropic, Bedrock — send the system prompt as
        # a separate ``system`` parameter, not inside ``messages[]``).
        # Anthropic unconditionally rejects requests whose first message
        # is not role=user, so we must pin the summary to "user" and
        # prevent the flip logic below from reverting it (#52160).
        _force_user_leading = compress_start == 0 or last_head_role == "system"
```

零用户护栏(#58753,:6616-6656):自动压缩路径的 messages 不含 system prompt,唯一真实用户轮落入被压中间区时(如 kanban worker),压缩后可能零 user 消息,vLLM/Qwen 回不可重试的 `400 No user query found`,每次 resume 重放同一污染历史。判定用"非空文本的 user 轮"而非裸角色(仅存的 user 轮可能是无字幕截图——`_strip_historical_media` 的锚图片保持原样、文本为空);触发时摘要必须以 `role="user"` 落位(摘要文本永非空,失败时也有确定性 fallback 顶上)。

**定案**:◇2 证实。且不止 Mistral/Anthropic:还包括 merged 形态的可逆解包、零用户 400 护栏、supersede 后相邻 user 轮的主动合并(micro 路径 `_merge_adjacent_user_turns`,:5985-6025)。

### 重实现要点

- 交替合法性要按"目标 provider 模板数得到的角色序列"推理,不是消息列表字面顺序;tool 流豁免是关键差异点。
- 角色选择做成级联:头优先 → 尾撞车翻转 → 双撞并入尾;并入必须带定界符且可被下轮压缩无损解包。
- 两条 provider 硬约束单列为强制位:首可见消息必须 user(Anthropic/Bedrock)、请求必须含非空 user 文本(vLLM 系)。
- 记住失败的放大器:摘要是持久化消息,一次角色选错=永久污染,所以这里值得过度设防。

---

## 6. 定案 ▲5「压缩执行基础设施:锁/栅栏/超时/in-place 落库/keep-prompt」——**证实**

### 6.1 并发兄弟 agent 双压同一会话的孤儿分叉问题(锁)

`agent/conversation_compression.py:2324-2333 @ 863e313`:

```python
    # ── Compression lock ────────────────────────────────────────────────
    # Atomic, state.db-backed lock per session_id.  Without this, two
    # AIAgent instances that share the same session_id (most commonly the
    # parent-turn agent and its background-review fork — see
    # ``agent/background_review.py``: ``review_agent.session_id =
    # agent.session_id``) can each call compress() on overlapping
    # snapshots of the same conversation.  Both succeed, both rotate
    # ``agent.session_id`` to a fresh id, both create child sessions in
    # state.db parented to the same old id.  The gateway's SessionEntry
    # only catches one rotation, so the other child becomes an orphan
```

场景:主轮 agent 与 background-review fork 共享 session_id,各自在重叠快照上压缩、各自轮转出子会话——同一父会话两个孩子,gateway 只跟到一个,另一个成了**静默吞写入的孤儿分叉**(Damien 事故)。方案:state.db 持久锁,按旧 session_id 键控;holder 串 `pid:tid:agent-instance:nonce`(:1326-1343)便于运维辨认死持有者;TTL 300s + 后台租约刷新线程(`_CompressionLockLeaseRefresher`,:1487-1573——首次刷新立即执行防短 TTL 在启动开销中过期;连续失败容忍窗 = 一个 TTL,锁绝不因卡住的刷新器超期持有)。抢锁失败即本轮弃权返回原消息,并设 `agent._compression_skipped_due_to_lock = holder or True`(:2475-2519)供 manual feedback 区分文案(§10)。锁 API 结构性缺失(热更新版本偏差)才 fail-open,其余一切异常 fail-closed(:2352-2474)。释放在 `finally` 里且晚于全部轮转后记账(:3561-3571)。

迟到竞争者:拿到锁后先查父会话是否已被别人轮转(`_session_was_rotated_by_compression`),是则 `_adopt_live_compression_child` 收敛到唯一活孩子(:2602-2640;两读一验防孩子再轮转竞态,:1207-1289)。轮转模式下租约生效后重读持久父转录,若比调用方快照**多**(长度比较,故意不做内容等值——历史轮的就地变异是合法的,内容等值曾把繁忙会话永久卡死)则采纳持久快照继续(:2704-2743)。

### 6.2 外部摘要 LLM 挂死的超时(栅栏 + progress-aware 包装)

`CompressionCommitFence`(:445-690)让"取消 vs 提交"有确定性边界:取消要么在提交边界前赢(此后 `begin_commit` 拒绝准入),要么等待已开始的提交完整结束——**提交绝不半途弃置**。要点:`begin_commit` 持栅栏锁直到 `finish_commit`,故另设 lock-free 的 `commit_in_flight` Event 供宿主在提交挂死期间也能到达超时告警循环(F1);`revoke_commit_admission` 在宿主任何 unwind 路径(KeyboardInterrupt/取消/异常)上 lock-free 阻断未来提交(F2);worker 拿到持久锁后向栅栏发布 **holder-qualified** 的租约释放钩子,超时的宿主可立刻释放死 worker 的租约让新压缩进场,DB 释放按 holder 过滤故无 ABA(F4,自 PR #71569 移植);`touch_progress`/`seconds_since_progress` 是流式摘要的前进心跳。

宿主包装 `run_compress_context_with_progress_timeout`(:819-1088):worker 丢进 4 线程共享 daemon 池,**inactivity 预算**(默认 `context_timeout_seconds=120`)+ 硬顶(`context_total_ceiling_seconds=600`,配置见 `hermes_cli/config_defaults.py:649-672 @ 863e313`)——慢但仍在产 token 的摘要模型不被杀,只有真沉默/涓流才被切;超时后 fence-cancel、返回原消息 + 惰性重建的 fallback prompt,worker 线程留在池里 detached(其迟到提交被栅栏挡死)。提交阶段超过硬顶时按 30s 分片继续等并升级日志(WARNING→ERROR)+ 一次 `on_commit_overrun` 回调——"摘要阶段有界;提交阶段只记录不弃置"(:994-1051)。池准入有界(F6):4 个 slot 全占时**快速失败**本轮不压(标记锚点行),`agent/conversation_compression.py:887-896 @ 863e313`:

```python
    if not _try_admit_compression_job():
        logger.warning(
            "Context compression pool saturated (%d workers busy) — "
            "refusing new compression this cycle and continuing without "
            "compression. Wedged workers are fence-cancelled and free their "
            "slot when they return; if this persists, check the summary "
            "provider health.",
            _COMPRESS_EXECUTOR_MAX_WORKERS,
        )
```

排队会让任务在预算内根本不启动、又在 worker 恢复时作为陈旧作业跑起来。陈旧作业启动前也先查栅栏(:909-919)。超时后宿主调 `ContextCompressor.record_timeout_failure`(agent/context_compressor.py:1975-1991)进入 60/300/900s cooldown 梯子;fence 取消后 worker 迟到成功的摘要**不得**清掉宿主刚记的 cooldown(`_compression_cancelled_check` 钩子,agent/context_compressor.py:1993-2011 + agent/conversation_compression.py:2819-2825)。取消赢时,压缩尝试期间被变异的一切可回滚状态按显式 allow-list 快照/恢复(`_COMPRESSOR_ATTEMPT_STATE_FIELDS`,:248-302),持久 cooldown 行在租约内先取权威快照、回滚时精确还原(:387-442、:305-384)。

### 6.3 in-place 落库(压缩结果怎么写回持久层)

默认 `compression.in_place: true`(#38763)。`agent/conversation_compression.py:3177-3206 @ 863e313`:

```python
                if in_place:
                    # ── In-place compaction: keep the same session_id ──────────
                    ...
                    # Durable, NON-DESTRUCTIVE replace: soft-archive the
                    # pre-compaction turns (active=0, kept on disk + FTS-searchable +
                    # recoverable) and insert `compressed` as the new live (active=1)
                    # set, atomically.
                    ...
                    agent._session_db.archive_and_compact(
                        agent.session_id,
                        compressed,
                        model_config_patch={
                            PROACTIVE_PRUNE_REARM_MODEL_CONFIG_KEY: None,
                        },
                    )
```

同一 session_id、旧行软归档(active=0, compacted=1,仍可 FTS 搜索/恢复)、新压缩集原子插入;随后 `update_system_prompt` + 清 flush 身份集合(:3213-3217、:3323-3327),下一轮按身份 diff 只追加真正的新消息。这消灭了整个"会话轮转 bug 簇"(/goal 丢失、孤儿会话、跨界搜索断裂)。legacy 轮转路径(:3219-3319):先把未持久化的当前轮 flush 进旧会话(以 `_persist_user_message_idx` 锚定已持久前缀防整段重插,#68196/#47202),再 `publish_compression_child` **单事务**发布父关闭 + 子行 + 压缩 handoff(读者不可能观察到"父已结束、子为空"的中间态;`require_compression_lease` 使发布依赖仍持有的租约),然后迁移 /goal(#33618)、heartbeat、标题续号,失败则回滚到父会话防孤儿(:3337-3383,含 proactive 跑道的精准恢复)。flush 基线由 `conversation_history_after_compression`(:1846-1882)按 in-place/rotation/abort 三态给出——in-place 之后**必须**把压缩集当已持久历史,否则同轮 flush 会把它们再插一遍、上下文翻倍再触发压缩。压缩器侧配套不变式:任何消息不得带 `_db_persisted` 标记离开 `compress()`(`_strip_persistence_markers` 终扫,agent/context_compressor.py:214-231 + 6819-6823,#57491——带标记的复制会让轮转 flush 跳过所有行,压缩转录从 state.db 消失)。

### 6.4 keep-prompt(保 KV-cache 前缀)

`agent/conversation_compression.py:3141-3161 @ 863e313`:

```python
        if (
            cached_system_prompt is not None
            and getattr(agent, "_memory_manager", None) is None
            and _cached_prompt_reflects_builtin_memory(agent, cached_system_prompt)
        ):
            new_system_prompt = cached_system_prompt
            agent._cached_system_prompt = cached_system_prompt
            ...
            reconstruct_static_prefix(
                agent,
                system_message=system_message,
                log_label="compression keep-prompt",
            )
```

压缩通常要重建 system prompt(重新载入记忆),但重建=本地后端 KV-cache 前缀报废。快路径条件:内建记忆(无外部 provider)且缓存 prompt **逐字包含**重载后的当前记忆块(包含性检查而非"重载前后快照相等"——gateway/TUI 从 DB 恢复的缓存 prompt 可能早于会话中途的记忆写入,快照两边相等而 prompt 实际已陈旧,保留会把旧记忆锁死一辈子,:211-245)。命中则字节不动地保留并重建稳定前缀标记层。

### 6.5 边界后记账(摘录)

真实用量哨兵(§1.2);`record_completed_compaction` 只在 `_last_compression_made_progress` 为真时武装裁决(:3512-3525);文件读/skill_view 去重缓存清空(压缩后原文已被摘掉,重读必须返回全文,:3527-3541);memory provider `on_session_switch(reason="compression", reset=False)` 与 context engine `on_session_start(boundary_reason="compression")` 双模式都触发(:3421-3456);压缩 ≥2 次警告质量退化(:3464-3471);`session:compress` 事件带 `in_place` 标志(:3477-3487);压缩后调 `trim_memory` 归还分配器页(agent/context_compressor.py:6826-6844)。Codex app-server 会话整条路由改走 `thread/compact`(本地转录只是镜像,Hermes 摘要器压不到真实线程,#36801,:2217-2242 + :3574-3716)。

**定案**:▲5 证实。三问对应:孤儿分叉 = 共享 session_id 的兄弟 agent 双轮转,靠 state.db 持久锁 + 迟到者收敛;挂死超时 = fence + inactivity 预算 + 提交不可弃置 + 有界池准入 + cooldown 梯子;写回 = in-place `archive_and_compact` 软归档原子换活集(默认),rotation 单事务发布子会话为遗留路径。

### 重实现要点

- 会话级持久锁必须:holder 可辨识、TTL+租约刷新、holder-qualified 释放(防 ABA)、失败方向明确(结构性缺失 fail-open,实现异常 fail-closed)、迟到者有收敛路径。
- "取消 vs 提交"要有单一栅栏做确定性边界;提交一旦开始绝不弃置,但要 lock-free 可观测以便挂死时告警。
- LLM 超时用 inactivity 预算而非墙钟,配硬顶防涓流;线程池准入有界、拒绝优于排队;超时后的迟到成功不得覆盖超时记账。
- 落库首选同 id 软归档原子换活集;轮转必须单事务发布并携带租约;两种模式的 flush 基线语义都要显式返回给调用方。
- system prompt 尽量按"包含性"判定复用,保 KV-cache;记忆陈旧性用内容包含而非快照相等判断。

---

## 7. 压缩用哪个模型(auxiliary 路由,接口侧)

压缩器**不自己选模型**,把选择完全委托给 auxiliary 路由:`call_llm(task="compression", main_runtime={...})`,`agent/context_compressor.py:3859-3868, 3880-3881 @ 863e313`:

```python
            call_kwargs = {
                "task": "compression",
                "main_runtime": {
                    "model": self.model,
                    "provider": self.provider,
                    ...
                },
                ...
            }
            if self.summary_model:
                call_kwargs["model"] = self.summary_model
```

- 构造时 `summary_model_override=None`(`agent/agent_init.py:2485 @ 863e313`),即默认无实例级覆盖,一切走配置。
- `call_llm` 的 task 语义:读 `auxiliary.compression.{provider,model,base_url,api_key,key_env,api_mode}`,显式参数 > 配置 > "auto" 自动检测链(`_resolve_task_provider_model`,`agent/auxiliary_client.py:7333-7345 @ 863e313`);配置里 `model: auto` 被归一为 None(否则字面 "auto" 上 wire,provider 返回 200 + 错误文本正文被当作摘要接受,:7367-7384)。
- 超时:`timeout=None` 时读 `auxiliary.compression.timeout`,且压缩任务有 300s **下限地板**(推理型辅助模型合法地慢,120s 默认导致流超时→确定性 fallback,#54915),`agent/auxiliary_client.py:7514 @ 863e313`:

```python
_COMPRESSION_TIMEOUT_FLOOR_SECONDS = 300.0
```

- 可行性探测(懒执行于首次压缩尝试,省 ~400ms 冷启动,agent/conversation_compression.py:2260-2274):aux 模型窗口 <64K 硬拒(ValueError 阻止会话启动,:1676-1686);aux 窗口 < 主模型阈值时**自动下调本会话阈值到 aux 窗口**并同步 tail 预算与 threshold_percent,给出含可行性验算的 config 修改建议(:1688-1805,#67422:建议值先按压缩器自己的地板/预留数学重算,不可行的建议不给)。
- 失败回退链(接口侧):独立 summary_model 失败 → `_fallback_to_main_for_compression` 清空 `summary_model` 立即用主模型重试一次(agent/context_compressor.py:3531-3560);`call_llm` 内部对 task="compression" 的超时还有同 provider 重试特判(agent/auxiliary_client.py:8875-8880)。中断保护:摘要调用包在 `aux_interrupt_protection()` 里,压缩是原子的,途中来消息不得把摘要撕成两半(#23975,:3899-3906);宿主层再套 `aux_progress_hook` 把流式 token 喂给栅栏心跳(agent/conversation_compression.py:2787-2813)。

---

## 8. 压缩失败的降级路径(完整梯子)

按发生顺序:

1. **摘要模型失败,可归类**(404/503/model_not_found/超时/429/502/504/JSON 解码失败(#22244)/流提前关闭(#18458)):若配置了独立 summary_model 且未回退过 → 立即改用**主模型**重试(agent/context_compressor.py:4058-4077);未归类的未知错误也给一次主模型重试("丢 N 轮上下文几乎总比多试一次糟",:4088-4098)。
2. **重试后仍失败** → 记 cooldown:超时类走 60/300/900s 递增梯子(#62452,同一结构性超时每 60s 重烧一次全额超时会把每轮变成分钟级卡顿,:4114-4126);JSON/流断 30s;其它 60s;无 provider 配置 600s(:628, 3985-3996)。返回 None。
3. **compress() 分流**(:6447-6495):`abort_on_summary_failure=True`(配置)或**终态访问/配额错误**(401/402/403、无 key、确认性配额耗尽——`_is_summary_access_or_quota_error`,:73-94)或**瞬时网络错误**(#29559/#25585)→ **整体中止**:消息原样返回、`_last_compress_aborted=True`、不轮转、rehydration 回滚(#57835)。理由:凭据坏了/网络闪断时,为一个占位摘要毁掉中间窗口是零收益的降级。
4. **默认路径(非中止)** → 插入**确定性 fallback 摘要** `_build_static_fallback_summary`(:3296-3496):本地提取用户请求/工具动作/文件路径/错误文本 + 旧摘要快照 + 最后被丢轮次,红线后限 8000 字符,丢弃中间窗口;记 `_last_summary_fallback_used` / `_last_summary_dropped_count` 供 gateway/CLI 显式警告。
5. **fallback streak ≥ 2** → 断路器阻断自动压缩(§1.3),300s 探针恢复。
6. **预 LLM 可行性跳过**(#60451,:6379-6408):已有 ≥1 次真实 strike 且中间区 < 10%×阈值 → 不打 LLM 直接走确定性丢弃;对 streak **中性**(既不加也不清,:1844-1857),`force=True` 的手动 /compress 不跳。
7. **宿主级**:锁竞争弃权、池饱和快速失败、fence 超时返回原消息 + cooldown 梯子、提交失败回滚父会话——都不丢数据,只是"本轮不压"。
8. **中止后的用户面**:`compress_context` 发 `⚠ Compression aborted: ... Run /compress to retry, or /new` 警告(:2948-2973);手动 /compress 的 `force=True` 先清 cooldown 立即重试(:6094-6098)。

---

## 9. micro-compaction(滚动微压缩,默认关)

配置 `compression.micro_compact`(默认 False——每 pass 重写已发送历史 = 每轮破一次 prompt-cache 前缀,`hermes_cli/config_defaults.py:617-628 @ 863e313`)。机制:每(第 N)个完成轮,在空闲期把**最老的未吸收 exchange**(一个完整 agent turn:assistant + tools 直到下一个 user,user 轮**永不**被吸收——"用户的原话是唯一无法从上下文重建的东西",agent/context_compressor.py:5347-5356)经 aux LLM 合并进滚动摘要,拼接为 assistant 角色 marker(`user → marker(assistant) → user` 天然合法交替,:5897-5911);滚动摘要是累积的,supersede 掉旧 micro marker(两道包含性闸:本 pass 起点非空 + 候选带 `MICRO_COMPACT_MARKER_KEY`——batch marker 含有滚动摘要没有的历史,绝不误删,:5939-5960);摘要自身超 2000 tokens 时 defrag(对摘要文本本身再 aux 压一遍、原位改写 marker、不动转录形状,:5522-5584);每次 splice 后 `archive_and_compact` 原子落库(否则 resume 双载摘要+原文,:5851-5881);同位置连续 3 次失败跳过该 exchange(:5689-5701);batch 压缩完成即作废 micro 状态,下次从 batch marker rehydrate(:6846-6857)。与 batch 路径共用序列化器与 `task="compression"` 路由(micro 调用带 `max_tokens=min(1500,...)`、`temperature=0.1`,:5477-5482)。

---

## 10. manual_compression_feedback 是什么

120 行纯函数模块,手动 `/compress` 的用户反馈文案层,两个入口:

- `describe_compression_lock_skip(lock_signal)`(:10-37):锁跳过文案。**必须**区分"确认有持有者"(报 holder,请等待)与"抢锁失败但无确认持有者"(`try_acquire_compression_lock` 内部吞了 `sqlite3.Error` 返回 False,失败≠有人在压;误报 "already in progress" 会在锁子系统坏掉时误导用户,:14-22)。
- `summarize_manual_compression(before, after, before_tokens, after_tokens, compression_state)`(:40-120):按压缩器的 `_last_compress_aborted` / `_last_summary_fallback_used` / no-op 四态生成 headline + token 行 + note;特判"消息更少但估算 token 反升"(摘要更稠密,:100-104);失败原因文案过 `redact_sensitive_text(force=True)`(:106-111,UI 边界绝不因全局红线关闭而漏凭据)。消费方:`cli.py:11131,11245`、`gateway/slash_commands.py:4036,4264`、`tui_gateway/methods_session.py`、`tui_gateway/server.py`(CompressionLockHeld 携带 holder)。

### 重实现要点(§7-§10 合并)

- 摘要模型选择做成"任务名路由 + 主运行时兜底 + 单次主模型回退",压缩器只关心接口;超时给压缩任务单独抬地板。
- 降级梯子要区分三类终局:可重试(cooldown)、不可重试(中止保原文)、可接受损失(确定性 fallback);"中止"必须回滚一切副作用包括 rehydration。
- 用户反馈把"锁被确认持有"与"抢锁失败"分开措辞;一切跨 UI 边界的错误文本强制红线。

---

## 11. 文档-代码出入(website/docs + README)

对照页:`website/docs/developer-guide/context-compression-and-caching.md`(唯一压缩专页);README 仅两处提及(`README.md:30,154 @ 863e313`,/compress 命令表,无冲突);根 `AGENTS.md:23,1140` 只说"唯一改上下文的时机是压缩",与代码一致。专页出入 7 处:

1. **Phase-1 占位符 vs 信息性摘要**。文档:`website/docs/developer-guide/context-compression-and-caching.md:238-241 @ 863e313`:

> Old tool results (>200 chars) outside the protected tail are replaced with:
> ```
> [Old tool output cleared to save context space]
> ```

代码:替换文本是 `_summarize_tool_result` 生成的工具语义一行摘要(agent/context_compressor.py:1129-1141);常量 `_PRUNED_TOOL_PLACEHOLDER`(:399)只作幂等跳过判据(:2925),从不被写入。测试 pin 死了这一点(`tests/agent/test_proactive_tool_result_pruning.py:87`:`assert m["content"] != _PRUNED_TOOL_PLACEHOLDER  # informative, not a blank placeholder`)。**文档过时。**

2. **摘要模板结构**。文档 :276-302 给出 `## Progress / ### Done / ### In Progress / ## Next Steps` 模板;代码模板(:3762-3811)是 `## Historical Task Snapshot / ## Completed Actions / ## Active State / ## Resolved Questions / ## Pruned Skills` 等,且模块 docstring 明说旧标题已被替换,`agent/context_compressor.py:10 @ 863e313`:

```
  - Historical (reference-only) section headings replace "Next Steps"/"Remaining Work" to avoid reading as active instructions
```

**文档过时**(旧标题会被读成活指令,正是历史前缀修了好几轮的事故)。

3. **摘要 token 上限常数**。文档 :306-307:`Maximum: min(context_length × 0.05, 12,000) tokens`;代码 `_SUMMARY_TOKENS_CEILING = 10_000`(:377,:1580-1582)。文档 :217 的算例 `min(200,000 × 0.05, 12,000) = 10,000` 数值碰巧对(10K=5%×200K),常数错。**文档过时。**

4. **孤儿 tool_call 处理**。文档 :318:`Tool calls whose results were removed → stub result injected`;代码明确剥离而非插桩,并记录了插桩方案被废除的原因(agent/context_compressor.py:4650-4657,Codex Responses `call_id != id` 时桩被下游修复器丢弃)。**文档过时。**

5. **摘要模型窗口要求与失败行为**。文档 :269-271 警告框:"summary model must have a context window at least as large as the main agent model's / entire middle section is sent in a single call / drops the middle turns without a summary, silently losing context"。代码三点相反:(a) 摘要输入有 160K 字符聚合上限 + 逐消息截断(:396,:3498-3529),不是无界整段;(b) aux 窗口不足时启动探测**自动下调阈值**使压缩可行(agent/conversation_compression.py:1688-1722),硬要求只是 64K 下限;(c) 失败不再"静默丢弃":终态错误中止保原文,其余插入结构化确定性 fallback 且 gateway/CLI 显式警告(§8)。**文档过时/失真。**

6. **protect_first_n"硬编码、永远保留"**。文档 :113:`protect_first_n | 3 | (hardcoded) | System prompt + first exchange always preserved`。代码:是配置键(`hermes_cli/config_defaults.py:664`),且首压后衰减为 0(agent/context_compressor.py:4759-4773,#11996)。**文档两点皆误。**

7. **触发点表述**。文档开头示意图 :49 写死 "Fires at 50% of context (default)";代码对 <512K 窗口地板到 75%(:2206-2208)。文档在 per-model overrides 一节(:154-157)有正确的地板描述,但首屏示意与参数表(:108)未提。**部分过时(内部不一致)。**

另:文档未覆盖但代码已有的机制(非冲突,记为缺口):`threshold_tokens` 绝对 cap、`max_attempts`、`proactive_prune_*`、`micro_compact_*`、`abort_on_summary_failure`、`context_timeout_seconds` 族(以上都在 `hermes_cli/config_defaults.py:560-700` 有注释)、feasibility 自动降阈、断路器/cooldown 族、Historical prefix 代际。

---

## 12. 配套测试清单(LT,行为规格参照)

`tests/agent/` 下压缩簇(实测存在):

- 触发/反抖动/断路器:`test_compaction_anti_thrash.py`、`test_compression_anti_thrash_persistence.py`、`test_compression_anti_thrash_recovery.py`、`test_preflight_compression_gate.py`、`test_compression_small_ctx_threshold_floor.py`(含"摘要调用不得带 wire max_tokens"契约)、`test_compression_max_attempts_config.py`
- 剪枝/预算:`test_proactive_tool_result_pruning.py`、`test_proactive_prune_config.py`、`test_proactive_prune_restart_safety.py`、`test_compressor_tool_call_budget.py`(#28053)、`test_compressor_image_tokens.py`
- 尾锚/边界:`test_compressor_actionable_tail_anchor.py`、`test_compressor_assistant_tail_anchor.py`、`test_compressor_tail_cut_oob_fix.py`、`test_compressor_tail_cut_tool_pair_floor.py`
- 摘要语义/角色:`test_summary_prefix_semantics.py`(历史前缀逐字节 pin)、`test_summary_prefix_tool_use.py`、`test_summary_role_template_alternation.py`、`test_compressed_summary_metadata.py`、`test_context_compressor_temporal_anchoring.py`、`test_context_compressor_zero_user_provenance.py`、`test_compressor_zero_user_guard.py`、`test_context_compressor_summary_continuity.py`、`test_compaction_redaction_boundaries.py`、`test_compressor_media_stripping.py`、`test_compressor_historical_media.py`
- 宿主/并发/超时:`test_compression_concurrent_fork.py`、`test_compress_context_progress_timeout.py`、`test_compression_review_76354.py`、`test_compression_worker_isolation_76354.py`、`test_compression_interrupt_protection.py`(#23975)、`test_compression_rotation_state.py`、`test_idle_compaction.py`、`test_idle_compaction_lock_and_guards.py`、`test_compression_progress.py`、`test_auxiliary_compression_timeout_floor.py`、`test_compression_attempt_telemetry.py`、`test_compression_fallback_budget.py`、`test_post_compression_trim.py`、`test_pre_compress_memory_context.py`、`test_compress_focus.py`、`test_compress_signal_leak.py`、`test_compression_logging_session_context.py`、`test_compression_count_warning_36908.py`
- 其它:`test_micro_compaction.py`、`test_manual_compression_feedback.py`、`test_context_compressor.py`(主套件)、`test_context_compressor_cross_session_guard.py`、`test_context_compressor_session_end_clears_state.py`

### 行为规格概述(挑 3)

**规格 A:摘要角色必须通过 Mistral 模板的交替预检**(`tests/agent/test_summary_role_template_alternation.py:95-107 @ 863e313`)。测试自带一个 Mistral 交替检查的忠实复刻:

```python
def _mistral_alternation_ok(messages: list[dict]) -> bool:
    """Replay the Mistral template's pre-flight alternation check: count
    only user and assistant-without-tool_calls messages; the counted
    sequence must go user, assistant, user, assistant, ..."""
```

用捕获自 Hermes Desktop v0.19.0 × llama.cpp Devstral 的真实失败形态(docstring :4-27:`[system, user, assistant(tool_calls), tool, SUMMARY(user), ...]` → 模板数出 user→user → 整请求 500,且摘要已持久化导致会话永久损坏)作为夹具,断言修复后:摘要落为 assistant(`test_captured_devstral_shape_emits_assistant_summary`)、装配结果整体通过交替预检(`test_captured_shape_passes_mistral_alternation`)、双撞时并入尾(`test_visible_head_assistant_visible_tail_user_merges`)、#58753 强制 user 护栏仍然赢(`test_zero_user_guard_still_forces_user`)、任何情况下无字面连续 user(`test_no_literal_consecutive_user_roles`)。这是 ◇2 的可执行规格。

**规格 B:共享 session_id 的并发压缩不得分叉血统**(`tests/agent/test_compression_concurrent_fork.py:489-575 @ 863e313`)。两个绑定同一 state.db、同一 session_id 的 agent 在两个线程同时 `_compress_context`;契约是三条不变式:父会话孩子数 `<= 1`(0 也合法——赢家的 create_session 在写争用下耗尽重试后安全回滚到父;`>= 2` 才是分叉 bug);离开父 id 的 agent 必须收敛到**同一个**子 id(输家经 `_adopt_live_compression_child` 收敛是修复生效而非分叉);结束后锁必须已释放。docstring 明说无锁时该夹具**确定性**产出 2 个孩子。这是 ▲5 锁语义的可执行规格,且展示了"断言精确 ==1 在争用回滚下是错的"这一测试演化教训。

**规格 C:proactive prune 必须先挣回缓存破坏才许再破**(`tests/agent/test_proactive_tool_result_pruning.py:111-144 @ 863e313`)。1M 窗口下先证明 `should_compress(120_000) is False`(全量压缩根本不会跑)而 prune 在 120K 就回收了 3 个大结果且内容是信息性摘要非占位符;然后追加新 tool pair 把两个旧大结果挤出保护尾——它们已是合法剪枝候选,但因 prompt 未长回 `after + max(reclaimed, 48000, 4096)` 跑道,第二次调用返回**输入对象本身**、一字未动(`assert blocked is grown`);人工把转录喂回跑道以上后,第三次调用才再次提交。这是 ▲4 滞回的可执行规格(`test_successful_full_compression_resets_proactive_runway` 另 pin 了"全量压缩边界重置跑道")。

---

## 13. 附:本簇涉及的关键常量速查(均 `agent/context_compressor.py @ 863e313`)

| 常量 | 行 | 值 | 语义 |
|---|---|---|---|
| `_MIN_SUMMARY_TOKENS` / `_SUMMARY_RATIO` / `_SUMMARY_TOKENS_CEILING` | 371/373/377 | 2000 / 0.20 / 10000 | 摘要预算下限/比例/上限 |
| `_SUMMARY_INPUT_MAX_CHARS` | 396 | 160000 | 摘要输入聚合上限(≈40K tokens) |
| `_SKILL_VIEW_PRUNE_MIN_CHARS` / `_MAX_PRUNED_SKILL_MARKERS` | 413/417 | 5000 / 20 | ghost-skill 阈值/标记上限 |
| `_SUMMARY_FAILURE_COOLDOWN_SECONDS` | 628 | 600 | 无 provider 长冷却 |
| `_FALLBACK_SUMMARY_MAX_CHARS` | 633 | 8000 | 确定性 fallback 摘要上限 |
| `_MAX_TAIL_MESSAGE_FLOOR` | 644 | 8 | 尾消息数下限的钳制 |
| `_FEASIBILITY_SKIP_MIDDLE_FRACTION` | 650 | 0.10 | 预 LLM 跳过的中间区占比 |
| `_SMALL_CTX_WINDOW_LIMIT` / `_SMALL_CTX_THRESHOLD_PERCENT` | 664/665 | 512K / 0.75 | 小窗口阈值地板 |
| `_IMAGE_TOKEN_ESTIMATE` | 623 | 1600 | 每图 token 估计(对齐 Claude Code) |
| `_MIN_CTX_TRIGGER_RATIO` | 2135 | 0.85 | 退化窗口触发比 |
| `_ANTI_THRASH_RECOVERY_SECONDS` | 2144 | 300.0 | 断路器探针窗 |
| (conversation_compression.py)`DEFAULT_CONTEXT_TIMEOUT_SECONDS` / `..._CEILING` | 695/696 | 120 / 600 | 宿主 inactivity 预算/硬顶 |
| (同上)`_COMPRESS_EXECUTOR_MAX_WORKERS` | 729 | 4 | 压缩池准入上限 |
| (auxiliary_client.py)`_COMPRESSION_TIMEOUT_FLOOR_SECONDS` | 7514 | 300.0 | 压缩任务超时地板 |

延伸:配置全集 `hermes_cli/config_defaults.py:560-700`;构造注入 `agent/agent_init.py:2479-2500`;/compress 消费端 `cli.py:11131-11245`、`gateway/slash_commands.py:4036-4264`。