# r8b-raw-cli-voice-approval —— cli.py 11800-14800(MCP 重载 / 语音 / 审批 / 密钥)

> 底稿(证据层)。研究对象 `/home/user/hermes-agent` @ `863e313`,只读。
> 溯源约定:每个事实断言后紧跟 `路径:行号 @ 863e313` 与逐字代码块。
> 覆盖范围:`cli.py` 11749–14806(段首函数 `_confirm_and_reload_mcp` 起于 11749,
> 段尾函数 `_audio_level_bar` 止于 14806),外加为验证前提而下钻的
> `tools/approval.py`、`tools/terminal_tool.py`、`hermes_cli/callbacks.py`、
> `hermes_cli/secret_prompt.py`、`tools/voice_mode.py`、`tools/wake_word.py`、`run_agent.py`。

---

## 0. 自验记录

### 0.1 三条前提的检验结论(先报结论,细节见 §2)

| # | 前提原文 | 判定 | 一句话 |
|---|---|---|---|
| 1 | "审批 UI 只是一个提示框,真正的 allow/deny 策略在 `tools/approval.py`" | **基本成立,但有重要补充** | 策略确实在 `approval.py`;但 cli.py 被信任的那一件事(返回一个裁决字符串)落在一个 **fail-open 的映射**上:任何不等于 `"timeout"` / `"deny"` 的返回值都被当成"批准"。cli.py 无法突破 hardline / sudo-stdin / user-deny 三道地板,也无法在 smart-deny 场景下持久化 allowlist(那由 approval.py 单独加锁),但它 **能** 把一次危险命令批准掉。另外 cli.py 展示的是 **脱敏后**的命令,执行的是原始命令。 |
| 2 | "密钥捕获会在屏幕上打码,且从不写入会话 transcript" | **后半句成立;前半句有一个真实缺口** | transcript / 历史侧完全干净(返回给模型的 dict 不含明文、`Buffer.reset()` 不带 `append_to_history`、Ctrl+S 暂存被 filter 屏蔽);屏幕打码靠 `PasswordProcessor` + `_secret_state` filter,**但 `_cancel_secret_capture()` 只清 state 不清输入缓冲区**,从 `chat()` 的中断监视器进入这条路径时没有任何 `buffer.reset()`,已输入的明文密钥会留在 composer 里且掩码已随 state 一起消失。 |
| 3 | "唤醒词看门狗跑在后台线程,退出时被干净停止" | **前半句成立;后半句只是"近似成立"** | 线程是 `daemon=True`,不会阻塞解释器退出;但 **退出路径里没有任何代码把 `_wake_word_active` 置 False**——`_run_cleanup` 只调 `stop_listening()`。看门狗在 `_wake_suspended == False`(常态)时会一直 `continue`,整个 cleanup 期间以 4Hz 空转,只能靠 `_should_exit` 或解释器 daemon 回收终止。"不会泄漏出进程"成立,"被干净停止"不成立。 |

### 0.2 锚点复核

本稿共 **189** 处 `路径:行号 @ 863e313` 锚点(含重复引用)。复核分两轮:

**第一轮(人工抽样,152 处)**:手工列出 152 个 (文件, 行号, 期望首行) 三元组,与源码逐行比对。
命中 8 处不一致——其中 5 处是我在**核对脚本**里凭记忆写错了期望值(稿内本来是对的),
**3 处是稿内真实漂移**。

**第二轮(机器全量,96 处)**:写脚本直接从本稿正文解析出每一个"锚点 + 紧随其后的代码块"配对,
把代码块逐字节与源文件从该行号开始的内容比对。首次运行命中 **2 处**不一致(1 处引文末行被截断、
1 处锚点-代码块错配),修正后**重跑 96 对全部命中、0 处不一致**;同时校验全部 189 个锚点的
行号都在对应文件范围内(0 处越界)。

**第三轮(行内锚点人工扫描,约 93 处)**:把每个未带代码块的行内锚点连同它指向的源码行整行打印出来
逐条确认语义匹配。命中 **1 处**不一致(文档锚点指到了 `:::warning` 而非表格行),已修正。

**最终修正记录(共 5 处,均已改正)**:

| 位置 | 原写 | 改为 | 性质 |
|---|---|---|---|
| §2.3 `_reload_skills` docstring | `cli.py:11928` | `cli.py:11924` | 锚点比代码块首行晚了 4 行 |
| §2.2 `refresh_agent_mcp_tools` docstring | 引文末行截断成 `    surface.` | 补全为完整行 | 代码块非逐字 |
| §2.12.4 sudo 还原快照 | 一个锚点挂了两个代码块,且第二块缩进 20 空格 | 拆成 `cli.py:13267` / `cli.py:13280` 两个锚点,缩进改回 16 空格 | 锚点-代码块错配 + 缩进错 |
| §5.1 唤醒词块注释 | `cli.py:12906` | `cli.py:12907` | 引用短语实际起于下一行 |
| §4-◇7 `mode: off` 文档 | `security.md:57` | `security.md:55` | 指到了 `:::warning` 而非表格行 |

**结论**:全部含代码块的断言现已机器验证为逐字一致;纯行内锚点(约 93 处)也逐条打印过
其指向的源码行并人工确认语义匹配。

### 0.3 复核脚本(可重跑)

```
python3 - <<'PY'
import io, re, os
draft = io.open("notes/r8b-raw-cli-voice-approval.md", encoding="utf-8").read().split("\n")
ROOT = "/home/user/hermes-agent"
cache = {}
def src(f):
    if f not in cache:
        cache[f] = io.open(os.path.join(ROOT, f), encoding="utf-8").read().split("\n")
    return cache[f]
anchor_re = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|md)):(\d+) @ 863e313`")
anchors, pairs = [], []
for i, ln_ in enumerate(draft):
    for m in anchor_re.finditer(ln_):
        anchors.append((m.group(1), int(m.group(2)), i+1))
i, last = 0, None
while i < len(draft):
    ms = list(anchor_re.finditer(draft[i]))
    if ms: last = (ms[-1].group(1), int(ms[-1].group(2)), i+1)
    if draft[i].strip() == "```" and last is not None:
        j, blk = i+1, []
        while j < len(draft) and draft[j].strip() != "```":
            blk.append(draft[j]); j += 1
        if i - last[2] <= 3: pairs.append((last, blk, i+1))
        last = None; i = j+1; continue
    i += 1
bad = 0
for (f, ln, dln), blk, bl in pairs:
    L = src(f)
    for k, q in enumerate(blk):
        a = L[ln-1+k] if 0 <= ln-1+k < len(L) else "<EOF>"
        if a != q:
            bad += 1
            print(f"MISMATCH draft:{bl} {f}:{ln} +{k}\n  quoted:{q!r}\n  actual:{a!r}")
            break
print(f"anchors={len(anchors)} verified_pairs={len(pairs)} mismatched={bad}")
PY
```

(在 `/home/user/hermes-study` 下运行;最后一次运行输出
`anchors=189 verified_pairs=96 mismatched=0`。)

---

## 1. 段内地图

按定义顺序列出本段的全部方法(缩进的是嵌套函数):

| 行号 | 名称 | 一句话职责 |
|---|---|---|
| 11749 | `_confirm_and_reload_mcp` | `/reload-mcp` 的交互确认层(Once / Always / Cancel),Always 会写 `approvals.mcp_reload_confirm: false` |
| 11816 | `_reload_mcp` | 真正的重载:断开→重读 config→重连→刷新 agent 工具快照→往历史里注入一条通知 |
| 11920 | `_reload_skills` | 技能重载。**刻意不注入历史消息**,改用一次性 pending note |
| 12002 | `_on_tool_gen_start` | 模型开始生成工具参数时,关掉流式框并打一行"preparing X" |
| 12022 | `_on_tool_progress` | 工具生命周期事件总入口:MoA 展示、宠物状态、spinner、滚动回显、`_pending_tool_info` 收发 |
| 12164 | `_on_tool_start` | 为写类工具抓 before 快照 |
| 12175 | `_on_tool_complete` | 写类工具完成后渲染 inline diff;`delegate_task` 背景派发的一次性提示 |
| 12210 | `_voice_start_recording` | 录音启动:能力检查→原子置位→读 `voice.*` 配置→建 recorder→beep→start→电平刷新线程 |
| 12304 | └ `_on_silence` | VAD 静音回调(由 recorder 在**独立线程**上调用) |
| 12338 | └ `_refresh_level` | 0.15s 心跳,只为让电平条重绘 |
| 12349 | `_voice_stt_model` | STT 模型名解析(local provider 特判为 `stt.local.model`,默认 `base`) |
| 12370 | `_voice_stt_provider` | STT provider 名(小写) |
| 12381 | `_voice_restart_recording_async` | 连续模式下把 `start()` 挪到后台线程(它可能阻塞) |
| 12392 | `_voice_stop_and_transcribe` | 停录→beep→转写→停止短语判定→入队;失败保留 wav;无语音 3 次退出连续模式 |
| 12517 | `_voice_speak_response_async` | 起 TTS 线程 + 兜底再武装全双工监听 |
| 12538 | `_voice_speak_response` | TTS 正文:文本规范化→合成 mp3→播放→清理 |
| 12611 | `_voice_full_duplex_listener` | 整轮全双工监听:生成期打断 agent、播放期切 TTS |
| 12665 | └ `_should_stop` | 监听终止条件(voice off / agent 结束且 TTS 播完) |
| 12675 | └ `_on_trigger` | 触发时的两相处理 |
| 12723 | `_voice_submit_barge_utterance` | 把打断捕获的音频转写并作为下一轮输入 |
| 12753 | `_voice_beeps_enabled` | `voice.beep_enabled`,用 `is_truthy_value` 处理 YAML 引号字符串 |
| 12767 | `_enable_voice_mode` | `/voice on`:环境检测→依赖检测→置位→读 `auto_tts`→打印帮助 |
| 12836 | `_typed_voice_stop` | **打字**输入停止短语等价于**说出**停止短语 |
| 12863 | `_disable_voice_mode` | 取消录音、后台 shutdown 音频流、切 TTS、置 `_voice_tts_done` |
| 12911 | `_maybe_start_wake_word` | 启动时按 surface 白名单决定是否开唤醒词 |
| 12921 | `_start_wake_word_listener` | 建引擎 + 抢麦克风租约 + 启动看门狗 |
| 12973 | `_stop_wake_word_listener` | 停唤醒词并释放全局 owner |
| 12992 | `_on_wake_word` | 听到唤醒词后的动作:暂停探测器→多 profile 路由→新会话→单次录音 |
| 13051 | `_start_wake_watchdog` | **本段前提 3 的主体**:0.25s 轮询,空闲 3 次后 resume 探测器 |
| 13092 | `_show_wake_word_status` | `/wake status` |
| 13122 | `_toggle_voice_tts` | `/voice tts` |
| 13139 | `_show_voice_status` | `/voice status` |
| 13158 | `_persist_prompt_summary` | 模态框消失后往 scrollback 补一行"问题 → 结果" |
| 13177 | `_clarify_callback` | clarify 工具的平台回调(队列 + 超时轮询) |
| 13254 | `_sudo_password_callback` | sudo 密码提示(45s 固定超时) |
| 13302 | `_approval_callback` | **本段前提 1 的主体**:危险命令审批提示,全程持 `_approval_lock` |
| 13381 | `_approval_choices` | 选项集合的唯一生成点 |
| 13392 | `_computer_use_approval_callback` | computer_use 的裁决词表转换 |
| 13414 | `_handle_approval_selection` | 回车/数字键落子;`view` 是唯一不入队的选项 |
| 13440 | `_get_approval_display_fragments` | 审批面板渲染 + 行预算裁剪 |
| 13612 | `_secret_capture_callback` | 转发到 `hermes_cli/callbacks.py:prompt_for_secret` |
| 13615 | `_capture_modal_input_snapshot` | 模态弹出前把用户草稿存起来并清空 composer |
| 13629 | `_restore_modal_input_snapshot` | 模态结束后还原草稿 |
| 13642 | `_clear_active_overlays_for_interrupt` | 中断时一次性排空四种模态的等待队列 |
| 13688 | `_submit_secret_response` | **本段前提 2 的主体**:把密钥投进队列并拆掉面板 |
| 13698 | `_cancel_secret_capture` | 等价于提交空串 |
| 13701 | `_clear_secret_input_buffer` | 清 composer(存在,但 §3-D4 指出的路径没调用它) |
| 13708 | `chat()` | 一轮对话的全部编排(约 850 行) |
| 13861 | └ `_stage_user_message` | 在持久化锁下把用户消息挂进历史 |
| 13936 | └ `display_callback` | 非流式模型时由 TTS 消费者代为显示 |
| 13963 | └ `stream_callback` | token → TTS 队列 |
| 13977 | └ `run_agent` | agent 线程主体:**在本线程重新注册 thread-local 回调** |
| 14563 | `_clear_terminal_on_exit` | `ESC[3J ESC[2J ESC[H` |
| 14597 | `_persist_active_session_before_close` | 关闭前的尽力持久化(本段唯一正确处理 alias 陷阱的地方) |
| 14682 | `_print_exit_summary` | 退出摘要 + resume 提示 |
| 14757 | `_get_tui_prompt_symbols` | 提示符与状态后缀 |
| 14796 | `_audio_level_bar` | RMS → 8 级方块字符 |

---

## 2. 逐机制精读

### 2.1 `/reload-mcp`:一个"贵操作"的确认层

**为什么需要这一层**:MCP 工具的 schema 被烘进 system prompt,重载 = 换 system prompt = provider 端
prompt cache 全废,下一条消息按满价重发全部 input token。这在长上下文 / 高推理模型上是真金白银。
所以作者给 `/reload-mcp` 单独加了确认门。

门的读取方式值得注意:它**现读**配置而不是用进程内的 `CLI_CONFIG` 快照,这样上一句
"Always Approve" 写进 config.yaml 之后同一进程里立刻生效。`cli.py:11762 @ 863e313`

```
        # Gate check — respects prior "Always Approve" clicks.
        try:
            cfg = load_cli_config()
            approvals = cfg.get("approvals") if isinstance(cfg, dict) else None
            confirm_required = True
            if isinstance(approvals, dict):
                confirm_required = bool(approvals.get("mcp_reload_confirm", True))
        except Exception:
            confirm_required = True

        if not confirm_required:
            with self._busy_command(self._slow_command_status(cmd_original)):
                self._reload_mcp()
            return
```

三选项模态复用的是 destructive slash 的那套 composer 模态(不是 `input()`),
`cli.py:11779 @ 863e313`:

```
        choices = [
            ("once", "Approve Once", "reload now"),
            ("always", "Always Approve", "reload now and silence this prompt permanently"),
            ("cancel", "Cancel", "leave MCP tools unchanged"),
        ]
        raw = self._prompt_text_input_modal(
            title="⚠️  /reload-mcp — Prompt cache invalidation warning",
```

**为什么不能用 `input()`**:`/reload-mcp` 由 `process_loop` 派发(`cli.py:10172 @ 863e313`),
而 `process_loop` 不在主线程上。prompt_toolkit 独占 stdin,非主线程的 `input()` 在 Windows 上会
直接和它死锁;这段历史写在 `_prompt_text_input_modal` 的 docstring 里,`cli.py:8686 @ 863e313`:

```
        **Platform note (Windows — issue #33961):**
        Earlier code bypassed the modal on ``sys.platform == "win32"`` and fell
        back to a raw ``input()`` prompt.  When the confirm was triggered from the
        ``process_loop`` daemon thread (the normal case) that ``input()`` ran off
        the main thread and deadlocked against prompt_toolkit's stdin ownership —
        the user saw a frozen cursor and Ctrl-C was swallowed (bare ``/reset``
        froze; ``/reset now`` worked only because it skips the prompt entirely).
```

模态的返回值经 `_normalize_slash_confirm_choice` 归一化,别名表是**为这个三元组硬编码**的
(`1/once/approve/yes/y/ok` → once,`2/always/remember` → always,`3/cancel/nevermind/no/n` → cancel),
`cli.py:8812 @ 863e313`:

```
        aliases = {
            "1": "once",
            "once": "once",
            "approve": "once",
            "yes": "once",
            "y": "once",
            "ok": "once",
            "2": "always",
            "always": "always",
            "remember": "always",
            "3": "cancel",
            "cancel": "cancel",
            "nevermind": "cancel",
            "no": "cancel",
            "n": "cancel",
        }
```

同时 `allowed = {choice[0] for choice in choices}` 做二次过滤(`cli.py:8828 @ 863e313`),
所以给一个只有 once/cancel 的模态输入 "2" 会返回 None → 调用方按"未识别"取消。设计是保守的。

### 2.2 `_reload_mcp`:additive-preserving 的工具快照重建

重载三步(断开 → 重读 → 重连)之后,真正难的是**把 agent 手里那份工具快照换掉**。agent 在构建时
一次性 snapshot `agent.tools`,之后再也不读注册表。这里没有自己重建,而是走共享 helper,
`cli.py:11857 @ 863e313`:

```
            # Refresh the agent's tool list so the model can call new tools.
            # Route through the shared helper so this CLI /reload-mcp path stays
            # in lockstep with the TUI RPC / gateway reload / late-binding paths
            # (name-diff, thread-safe, and — critically — additive-preserving so
            # memory-provider and context-engine tools survive the rebuild).
```

"additive-preserving"是关键词:`get_tool_definitions()` 只返回注册表派生的工具,而 `agent_init`
在那之后又**直接往 `agent.tools` 上追加**了两族工具(外部 memory provider 的、context engine 的
`lcm_*`)。天真的 `agent.tools = get_tool_definitions(...)` 会静默删掉它们。
`tools/mcp_tool.py:6743 @ 863e313`:

```
    Crucially it is **additive-preserving**: ``get_tool_definitions`` returns
    only the registry-derived tools, but ``agent_init`` appends two further
    families directly onto ``agent.tools`` *after* that — external
    memory-provider tools (mem0/honcho/…) and context-engine tools
    (``lcm_*``).  A naive ``agent.tools = get_tool_definitions(...)`` would
    silently DELETE those.  So after rebuilding the registry set we re-run the
    same post-build injectors ``agent_init`` used, reconstructing the full
    surface.  The new ``(tools, valid_tool_names)`` pair is published together
```

另一个细节:`enabled_toolsets` 是启动时解析一次的,本次会话中新 enable 的 MCP server 名字不在里面,
所以要临时合并进去,否则新加的 server 会被过滤掉。`cli.py:11870 @ 863e313`:

```
                enabled_override = None
                et = self.enabled_toolsets
                if et and "all" not in et and "*" not in et:
                    merged = list(et)
                    for _name in sorted(connected_servers):
                        if _name not in merged:
                            merged.append(_name)
                    enabled_override = merged
```

**注入历史消息**这一步是本段最可疑的设计之一。`cli.py:11887 @ 863e313`:

```
            # Inject a message at the END of conversation history so the
            # model knows tools changed.  Appended after all existing
            # messages to preserve prompt-cache for the prefix.
            change_parts = []
```

实际写入点在同一函数末尾,`cli.py:11899 @ 863e313`:

```
            self.conversation_history.append({
                "role": "user",
                "content": f"[IMPORTANT: MCP servers have been reloaded. {change_detail}{tool_summary}. The tool list for this conversation has been updated accordingly.]",
            })
```
(`cli.py:11899 @ 863e313`)

紧接着的"立刻持久化",`cli.py:11904 @ 863e313`:

```
            # Persist session immediately so the session log reflects the
            # updated tools list (self.agent.tools was refreshed above).
            if self.agent is not None:
                try:
                    self.agent._persist_session(
                        self.conversation_history,
                        self.conversation_history,
                    )
                except Exception:
                    pass  # Best-effort
```

**这里两个参数是同一个 list 对象**。往下追 `_persist_session` → `_flush_messages_to_session_db_unlocked`,
它用 `conversation_history` 的对象身份来判断"哪些消息已经是持久的",`run_agent.py:2083 @ 863e313`:

```
            history_ids = {
                id(item) for item in (conversation_history or [])
                if isinstance(item, dict)
            }
```

然后在写入循环里,`run_agent.py:2128 @ 863e313`:

```
                # Already-durable messages: either carried over from the loaded
                # history copy, or seeded by a caller. Stamp them so future
                # flushes skip them without consulting any id() set again.
                if id(msg) in history_ids or id(msg) in seed_ids:
                    msg[_DB_PERSISTED_MARKER] = True
                    continue
```

传同一个 list ⇒ 每一条消息的 `id` 都在 `history_ids` 里 ⇒ **全部被盖上"已持久化"戳并跳过写库**。
包括刚 append 的那条 MCP 通知。而 `_save_session_log`(JSON 快照)默认是 no-op,
`run_agent.py:2949 @ 863e313`:

```
        if not getattr(self, "_session_json_enabled", False):
            return
```

也就是说这次"立刻持久化"在默认配置下**一个字节都没写**,还顺手让那条通知永远写不进 `state.db`。

这不是我的臆测——同一份代码库在关闭路径上**专门防了这个 alias 陷阱**,`cli.py:14633 @ 863e313`:

```
            # A normal turn builds a new list that reuses the resumed-history dicts.
            # Keep that CLI history as the baseline so a signal between assigning
            # ``_session_messages`` and the turn's DB flush cannot append its durable
            # prefix a second time. Once the CLI takes the turn result, however, both
            # names can point at the same live list; passing that alias would mark an
            # unflushed tail durable without writing it. Marker-only persistence is
            # correct only in that alias case.
```

并且真的做了防御(`cli.py:14651 @ 863e313`):

```
            elif not isinstance(conversation_history, list) or conversation_history is messages:
                conversation_history = None
```

→ 缺陷 **D1**、**D16**。

### 2.3 对照组:`_reload_skills` 为什么不注入历史

同一个文件里、隔了 4 行的另一个重载路径,做法完全相反,而且把理由写死在 docstring 里。
`cli.py:11924 @ 863e313`:

```
        Skills don't need to live in the system prompt for the model to use
        them (they're invoked via ``/skill-name``, ``skills_list``, or
        ``skill_view`` at runtime), so this does NOT clear the prompt cache.
        It rescans the slash-command map, prints the diff for the user, and
        — if any skills were added or removed — queues a one-shot note that
        gets prepended to the next user message. This preserves message
        alternation (no phantom user turn injected out of band) and keeps
        prompt caching intact.
```

以及实现处的注释,`cli.py:11970 @ 863e313`:

```
            # Queue a one-shot note for the NEXT user turn. The CLI's agent
            # loop prepends ``_pending_skills_reload_note`` (if set) to the
            # API-call-local message at ~L8770, then clears it — same
            # pattern as ``_pending_model_switch_note``. Nothing is written
            # to conversation_history here, so message alternation stays
            # intact and no out-of-band user turn is persisted.
```

这条 note 的消费点在 `run_agent()` 内部,`cli.py:14020 @ 863e313`:

```
                _srn = getattr(self, '_pending_skills_reload_note', None)
                if _srn:
                    agent_message = _prepend_note_to_message(agent_message, _srn)
                    self._pending_skills_reload_note = None
```

**可迁移的结论**:同一个仓库里存在两种"告诉模型环境变了"的做法——注入幽灵 user turn(MCP)
与 API-local 前缀 note(skills / model switch / speech-interrupted)。后者显然是演进后的正确做法
(不破坏 alternation、不进 transcript、不打断 prompt cache 前缀),前者是遗留。→ 缺陷 **D2**。

### 2.4 工具进度回调:一个被 display mode 门控的状态机

`_on_tool_progress` 是 CLI 的"工具生命周期总线"。它同时承担 5 件事:MoA 参考模型输出的展示、
桌宠状态、spinner 文本、per-turn 统计、滚动回显。

值得单独讲的是 `tool.started` 时把参数**寄存**、`tool.completed` 时**取回**的这一对操作——
目的是让完成时的那行"可爱提示"能带上参数摘要。寄存侧,`cli.py:12158 @ 863e313`:

```
            # Store args for stacked scrollback line on completion
            self._pending_tool_info.setdefault(function_name, []).append(
                function_args if function_args is not None else {}
            )
```

取回侧,`cli.py:12101 @ 863e313`:

```
            if function_name and self.tool_progress_mode in {"new", "all", "verbose"}:
                duration = kwargs.get("duration", 0.0)
                # Pop stored args from tool.started for this function
                stored = self._pending_tool_info.get(function_name)
                stored_args = stored.pop(0) if stored else {}
                if stored is not None and not stored:
                    del self._pending_tool_info[function_name]
```

**寄存无条件、取回被 mode 门控**。`off` 是合法 mode(`cli.py:4252 @ 863e313` 把 `False` 归一为
`"off"`),focus view 更是直接把它钉成 `off`,`-Q` 批处理也设成 `off`(`cli.py:18369 @ 863e313`)。
在这些模式下 `_pending_tool_info` 只进不出,按工具名累积整个进程生命周期的参数字典——
而 `function_args` 可以是一次 45 KB 的 `write_file` payload(这个体量正是 `_on_tool_gen_start`
docstring 自己举的例子,`cli.py:12007 @ 863e313`)。→ 缺陷 **D3**。

另外这段里有一条值得学的 bugfix 注释,解释了为什么 `verbose` 必须和 `all` 一起进白名单
(非流式模型没有 `_on_tool_gen_start` 提交的"preparing"行,verbose 模式下就一行滚动记录都不剩),
`cli.py:12092 @ 863e313`:

```
            # Print stacked scrollback line for "new" / "all" / "verbose" modes.
            # "verbose" was previously omitted here, so non-streaming model
            # calls (MoA aggregator, copilot-acp) rendered each tool only into
            # the transient spinner line — which overwrites itself, so no
            # scrollable tool history accumulated. Streaming models hid the bug
            # because _on_tool_gen_start commits a "preparing" line per tool;
            # non-streaming calls never emit that, leaving verbose mode with no
            # committed line at all. "verbose" is strictly more than "all", so
            # it must commit at least the same line.
```

### 2.5 录音启动:三层防御

`_voice_start_recording` 有三处防御性设计,每一处都对应一类真实故障。

**(a) 原子 check-and-set 防重入**,`cli.py:12244 @ 863e313`:

```
        # Prevent double-start from concurrent threads (atomic check-and-set)
        with self._voice_lock:
            if self._voice_recording:
                return
            self._voice_recording = True
```

**(b) recorder 构造失败必须回滚标志位**——否则 `_voice_recording` 永远是 True,以后每次启动都被
上面那个 guard 静默吃掉。`cli.py:12263 @ 863e313`:

```
        # Recorder creation can fail (no input device, PortAudio init error).
        # Reset the flag on failure or _voice_recording stays True forever and
        # every future voice start is silently skipped by the guard above.
        if self._voice_recorder is None:
            try:
                self._voice_recorder = create_audio_recorder()
            except Exception:
                with self._voice_lock:
                    self._voice_recording = False
                raise
```

**(c) 配置项的类型守卫,且显式排除 `bool`**。Python 里 `bool` 是 `int` 的子类,
手写 `silence_threshold: true` 会变成 `1`(几乎等于"任何声音都算说话")。
`cli.py:12274 @ 863e313`:

```
        # Apply config-driven silence params (numeric-guarded so YAML
        # scalar corruption doesn't break recording start-up).
        #
        # ``bool`` is explicitly excluded from the numeric check — in
        # Python bool is a subclass of int, so a hand-edited
        # ``silence_threshold: true`` would otherwise be forwarded as
        # ``1`` instead of falling back to the 200 default (Copilot
        # round-12 on #19835).
        _threshold = voice_cfg.get("silence_threshold")
        _duration = voice_cfg.get("silence_duration")
        self._voice_recorder._silence_threshold = (
            _threshold if isinstance(_threshold, (int, float)) and not isinstance(_threshold, bool) else 200
        )
```

`max_recording_seconds` 用同一套守卫,并且注释坦白它此前是死配置,`cli.py:12290 @ 863e313`:

```
        # voice.max_recording_seconds — hard cap on a single recording's length.
        # Same numeric guard as the silence params (bool excluded: a hand-edited
        # ``max_recording_seconds: true`` must not become ``1`` — it falls back
        # to the documented 120 default, mirroring the silence-param handling).
        # An explicit numeric value <= 0 disables the cap. Previously this
        # documented key was never read (dead config); wiring it here makes it
        # take effect.
        _max_rec = voice_cfg.get("max_recording_seconds")
        self._voice_recorder._max_recording_seconds = (
            (_max_rec if _max_rec > 0 else 0.0)
            if isinstance(_max_rec, (int, float)) and not isinstance(_max_rec, bool)
            else 120.0
        )
```

**但这三个属性是 setattr 到 recorder 实例上的,而 recorder 有两种实现**。
Termux 后端根本不读它们,`tools/voice_mode.py:683 @ 863e313`:

```
class TermuxAudioRecorder:
    """Recorder backend that uses Termux:API microphone capture commands."""

    supports_silence_autostop = False

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._recording = False
        self._start_time = 0.0
        self._recording_path: Optional[str] = None
        self._current_rms = 0
```

它的 `start()` 第一行就把静音回调丢掉了,`tools/voice_mode.py:709 @ 863e313`:

```
    def start(self, on_silence_stop=None) -> None:
        del on_silence_stop  # Termux:API does not expose live silence callbacks.
```

Python 允许给实例挂任意属性,所以不会报错——只是三个"已生效"的配置在 Termux 上是静默死配置。
→ 缺陷 **D13**。

CLI 侧确实按 `supports_silence_autostop` 换了提示文案(`cli.py:12328 @ 863e313`),但没有对
`max_recording_seconds` 做同等提示:

```
        _label = self._voice_record_key_label()
        if getattr(self._voice_recorder, "supports_silence_autostop", True):
            _recording_hint = f"auto-stops on silence | {_label} to stop & exit continuous"
        elif _is_termux_environment():
            _recording_hint = f"Termux:API capture | {_label} to stop"
```

**静音回调不在音频回调线程上跑**,这是一个很重要的解耦——否则 `_on_silence` 里的
`with self._voice_lock:` 会和 `_disable_voice_mode` 持锁调 `recorder.cancel()` 形成
锁序倒置。`tools/voice_mode.py:992 @ 863e313`:

```
                if should_fire:
                    with self._lock:
                        cb = self._on_silence_stop
                        self._on_silence_stop = None  # fire only once
                    if cb:
                        def _safe_cb():
                            try:
                                cb()
                            except Exception as e:
                                logger.error("Silence callback failed: %s", e, exc_info=True)
                        threading.Thread(target=_safe_cb, daemon=True).start()
```

### 2.6 STT 解析:local provider 的特判

`_voice_stt_model` 的存在理由是"local backend 必须拿到一个真实模型名",
`cli.py:12349 @ 863e313`:

```
    def _voice_stt_model(self) -> Optional[str]:
        """STT model override from config, or None for the provider default.

        For the local provider, prefer stt.local.model (default ``base``) so the
        CLI passes a real model name into the local STT backend.
        """
        try:
            from hermes_cli.config import load_config
            stt_config = load_config().get("stt", {})
            if not isinstance(stt_config, dict):
                return None
            provider = str(stt_config.get("provider") or "").strip().lower()
            if provider == "local":
                local_config = stt_config.get("local") or {}
                if not isinstance(local_config, dict):
                    local_config = {}
                return local_config.get("model") or "base"
            return stt_config.get("model")
```

`_voice_stt_provider` 单独存在只为一件事:local provider 首次使用要从 Hugging Face 下模型,
必须换一句不一样的提示,不然用户会以为卡死。`cli.py:12428 @ 863e313`:

```
            stt_model = self._voice_stt_model()
            if self._voice_stt_provider() == "local":
                _cprint(
                    f"{_DIM}Preparing local STT model '{stt_model}' "
                    f"(first use may download it from Hugging Face)...{_RST}"
                )
            else:
                _cprint(f"{_DIM}Transcribing...{_RST}")
```

### 2.7 `_voice_stop_and_transcribe`:三条容易踩错的分支

**(a) 转写失败时保留 wav**——长口述丢了没法找回。`cli.py:12469 @ 863e313`:

```
            # Clean up temp file unless transcription failed. On failure, keep
            # the source recording so long dictation is not lost.
            try:
                if wav_path and os.path.isfile(wav_path):
                    if transcription_failed:
                        _cprint(f"{_DIM}Recording preserved at: {wav_path}{_RST}")
                    else:
                        os.unlink(wav_path)
```

**(b) "无语音 3 次退出连续模式"必须扣掉 agent 忙 / TTS 播报的时间段**——用户在那时保持沉默是
**正确行为**,不该被计数。这是一个非常典型的"状态机计数器要按语义门控"的例子。
`cli.py:12480 @ 863e313`:

```
            # Track consecutive no-speech cycles to avoid infinite restart loops.
            # While the agent is mid-turn or TTS is speaking, the user is
            # CORRECTLY silent (waiting/listening) — those cycles must not
            # count, or a multi-minute tool run ends the voice chat under
            # the user. The stop phrase and barge-in still work during the
            # hold (they run on their own paths above).
            stop_continuous_restart = False
            _tts_done = getattr(self, "_voice_tts_done", None)
            _activity_hold = bool(
                getattr(self, "_agent_running", False)
                or (_tts_done is not None and not _tts_done.is_set())
            )
```

**(c) 谁负责重启录音是分工的**:提交了转写 → `process_loop` 在 `chat()` 之后重启;没提交 →
这里自己重启。`cli.py:12505 @ 863e313`:

```
            # If no transcript was submitted but continuous mode is active,
            # restart recording so the user can keep talking.
            # (When transcript IS submitted, process_loop handles restart
            # after chat() completes.)
```

### 2.8 全双工 barge-in:从"只在播放时听"到"整轮都听"

这是本段设计上最值得学的一处。旧实现叫 `_voice_barge_in_monitor`,只在 TTS 播放时开麦,
结果有两个致命问题:生成期完全听不见用户;而且监听器把**自己扬声器的串音**当成噪声基线去校准,
导致触发阈值被抬到不可达。docstring 把这段事故讲得很完整,`cli.py:12611 @ 863e313`:

```
    def _voice_full_duplex_listener(self) -> None:
        """Full-duplex agent-turn listener: mic live for the WHOLE turn.

        Armed at utterance-submit (chat() start in continuous voice mode) and
        disarmed when the turn is fully done (agent finished + TTS played).
        Replaces the old per-playback ``_voice_barge_in_monitor``, which only
        listened while TTS audio was playing — during LLM generation the mic
        was dead, so the user could not interject by voice at all (and the
        playback monitor calibrated against its own speaker bleed, making
        the trigger unreachable; see tools.voice_mode.full_duplex_listen).
```

新方案的两相处理:生成期没有音频可切,直接**打断 agent 轮次**——复用和 Ctrl+C / 打字打断
同一个 seam。`cli.py:12689 @ 863e313`:

```
                else:
                    # Generation phase: no audio to cut — interrupt the
                    # in-flight agent turn (same seam as typed interrupt).
                    logger.debug(
                        "full-duplex listener tripped during generation — "
                        "interrupting agent turn"
                    )
                    _pipe_stop = getattr(self, "_voice_tts_stop", None)
                    if _pipe_stop is not None:
                        _pipe_stop.set()  # never let the stale reply speak
```

底层的相位隔离(播放期**冻结**基线、额外抬到 `PLAYBACK_MIN_TRIGGER`、开播后 `grace_ms` 抑制瞬态)
在 `tools/voice_mode.py:1971 @ 863e313`:

```
    * ``playback`` — TTS audio flowing. The quiet baseline is HELD (never
      recalibrated against speaker bleed); the trigger is additionally
      clamped up to ``PLAYBACK_MIN_TRIGGER`` so bleed alone can't trip it,
      and a *grace_ms* window after playback first starts suppresses trips
      from the playback onset transient.
```

**单例保护是有洞的**。listener 用一个惰性创建的 Event 做"一次只有一个监听器持麦",
`cli.py:12636 @ 863e313`:

```
        fd_active = getattr(self, "_voice_fd_active", None)
        if fd_active is None:
            fd_active = threading.Event()
            self._voice_fd_active = fd_active
        if fd_active.is_set():
            return  # one listener owns the mic for this turn
        fd_active.set()
```

这是**无锁的 check-and-set**,而且 Event 本身还是惰性创建的(`__init__` 里没有初始化——
对照 `cli.py:4722 @ 863e313` 初始化了 `_voice_tts_done` / `_voice_barge_capture` 却没有
`_voice_fd_active`)。两个并发首调者可以各自创建一个 Event 并各自 `set()` 自己那个,双双通过。
而调用方确实有两处会并发:`chat()` 起始处(`cli.py:13894 @ 863e313`)和
`_voice_speak_response_async`(`cli.py:12527 @ 863e313`),后者的注释还断言这是安全的:

```
        # Spoken barge-in must work on the whole-file fallback path too. The
        # full-duplex agent-turn listener normally already covers playback
        # (armed at turn start in chat()); this arm is an idempotent safety
        # net for speak calls outside a chat turn — the listener refuses to
        # double-arm via _voice_fd_active.
```

→ 缺陷 **D6**。

### 2.9 `_voice_tts_done` 的早退空洞

`_voice_speak_response_async` **先 clear 再起线程**,`cli.py:12517 @ 863e313`:

```
    def _voice_speak_response_async(self, text: str) -> None:
        """Schedule TTS and mark it pending before continuous recording can restart."""
        if not self._voice_tts or not text:
            return
        self._voice_tts_done.clear()
        threading.Thread(
            target=self._voice_speak_response,
            args=(text,),
            daemon=True,
        ).start()
```

线程体 `_voice_speak_response` 的第一件事是**再检查一次** `_voice_tts`,而这个早退分支
**在 `try` 之前**,`cli.py:12538 @ 863e313`:

```
    def _voice_speak_response(self, text: str):
        """Speak the agent's response aloud using TTS (runs in background thread)."""
        if not self._voice_tts:
            return
        self._voice_tts_done.clear()
        try:
```

`finally: self._voice_tts_done.set()` 在 `cli.py:12607 @ 863e313`:

```
        finally:
            self._voice_tts_done.set()
```

所以只要在"async 已 clear、线程还没跑到 guard"这个窗口里 `_voice_tts` 变成 False,
`_voice_tts_done` 就**永远保持 clear**。后果链条很长:`_should_stop()` 会一直返回 False
(`cli.py:12670 @ 863e313`),全双工监听器不放麦;`_voice_stop_and_transcribe` 的
`_activity_hold` 永远为真,无语音计数永不递增。

`_disable_voice_mode` 把这个洞堵住了(它显式 set),`cli.py:12894 @ 863e313`:

```
        self._voice_tts_done.set()
```

但 `_toggle_voice_tts`(`/voice tts`)没有,`cli.py:13128 @ 863e313`:

```
        with self._voice_lock:
            self._voice_tts = not self._voice_tts
        status = "enabled" if self._voice_tts else "disabled"
```

→ 缺陷 **D5**。

### 2.10 唤醒词:一个"租约 + 看门狗"的模型

设计意图写在一整段块注释里,`cli.py:12898 @ 863e313`:

```
    # ── Wake word ("Hey Hermes") ─────────────────────────────────────────
    #
    # An always-on hotword listener (tools/wake_word.py) that, on detecting
    # the wake phrase, starts a fresh session and captures one utterance via
    # the existing voice pipeline — the "Hey Siri" pattern, fully on-device.
    #
    # The detector holds the microphone, so it must be paused while a voice
    # turn records (two input streams on one device is unreliable). On wake we
    # pause it and mark the system suspended; a lightweight watchdog resumes it
    # once the turn finishes and the CLI is idle again — covering every exit
    # path (transcript submitted, no speech, or transcription error) without
    # threading resume logic through the voice machinery.
```

**这是本段最值得抄的设计模式**:与其把 resume 逻辑穿进语音状态机的每一条退出路径
(提交转写 / 无语音 / 转写出错 / 用户 Ctrl+C…),不如设一个"suspended"标志 + 一个轮询看门狗,
让**幂等的空闲判定**去覆盖所有退出路径。这把 N 条路径的正确性问题化约成 1 条。

看门狗本体,`cli.py:13051 @ 863e313`:

```
    def _start_wake_watchdog(self):
        """Resume the paused detector when the CLI returns to a stable idle."""
        if getattr(self, "_wake_watchdog_started", False):
            return
        self._wake_watchdog_started = True

        def _loop():
            idle_polls = 0
            try:
                while getattr(self, "_wake_word_active", False) and not getattr(self, "_should_exit", False):
                    time.sleep(0.25)
                    if not getattr(self, "_wake_suspended", False):
                        idle_polls = 0
                        continue
                    busy = (
```

空闲判定与"连续 3 次才动手"的抖动抑制,`cli.py:13065 @ 863e313`:

```
                    busy = (
                        self._agent_running
                        or self._voice_recording
                        or getattr(self, "_voice_processing", False)
                        or not self._pending_input.empty()
                    )
                    if busy:
                        idle_polls = 0
                        continue
                    # Require a few consecutive idle polls (~0.75s) so we don't
                    # resume in the gap between VAD stop and the agent starting.
                    idle_polls += 1
                    if idle_polls >= 3:
```

线程创建与标志复位,`cli.py:13087 @ 863e313`:

```
            finally:
                self._wake_watchdog_started = False

        threading.Thread(target=_loop, daemon=True, name="wake-watchdog").start()
```

#### 前提 3 的逐项检验

**"跑在后台线程"** —— 成立。`daemon=True`,有名字 `wake-watchdog`(`cli.py:13090 @ 863e313`)。
daemon 属性意味着它**不可能阻塞解释器退出**:CPython 的 `Py_FinalizeEx` 只 join 非 daemon 线程。

**"退出时被干净停止"** —— 不成立。全仓唯一的退出清理点只调了 `stop_listening`,
`cli.py:1191 @ 863e313`:

```
    try:
        from tools.wake_word import stop_listening as _stop_wake_word
        if _cli_wake_owner is not None:
            _stop_wake_word(owner=_cli_wake_owner)
    except Exception:
        pass
```

它**没有**把 `self._wake_word_active` 置 False(`_cli_wake_owner` 是 CLI 实例,但这里只把它当
owner token 传给 wake_word 模块)。看门狗循环的常态分支是 `_wake_suspended == False` →
`continue`,**永远不会去调 `resume_listening`,也就永远不会发现探测器已经没了**。
于是它在整个 cleanup 期间(可能是数秒的 MCP / browser / memory teardown)继续以 4Hz 空转,
直到 `_should_exit` 变 True 或进程结束。

值得注意的是,**如果**恰好处在 suspended 状态,它会自愈:`resume_listening` 在
`_detector is None` 时返回 False(`tools/wake_word.py:1368 @ 863e313`):

```
def resume_listening(*, owner: object) -> bool:
    """Re-open the microphone only when ``owner`` holds the lease."""
    with _detector_lock:
        if _detector is None or _detector_owner is not owner:
            return False
        _detector.resume()
        return True
```

而 CLI 侧对 False 的处理是把 `_wake_word_active` 置 False,循环下一轮就退出
(`cli.py:13079 @ 863e313`):

```
                        try:
                            from tools.wake_word import resume_listening
                            if resume_listening(owner=self):
                                self._wake_suspended = False
                            else:
                                self._wake_word_active = False
                        except Exception as e:
                            logger.debug("wake word resume failed: %s", e)
```

这也顺带说明:cleanup 之后看门狗**不可能把麦克风复活**——租约已经作废。这一点是安全的。
但注意 `else: self._wake_word_active = False` 这一支是**静默**的:唤醒词功能挂掉时用户看不到
任何提示,`/wake status` 会显示 OFF 而没有原因。→ 缺陷 **D8**、**D15**。

**"能否泄漏线程"** —— `_wake_watchdog_started` 由**启动方置位、由线程自己在 `finally` 里清位**,
这是一个经典的竞态形状:`/wake off` 后立刻 `/wake on`,如果新的 `_start_wake_watchdog()` 在旧线程
执行 `finally` 之前读到 `True`,新监听器就没有看门狗——下一次唤醒后探测器被 pause 且**永远不会
被 resume**。窗口只有几条字节码宽,概率极低,但形状是真的。→ 缺陷 **D7**。

### 2.11 审批 UI(前提 1 的正面检验)

#### 2.11.1 cli.py 侧到底做了什么

`_approval_callback` 做三件事:序列化并发请求、把状态挂到 UI、阻塞等一个字符串。
`cli.py:13315 @ 863e313`:

```
        Uses _approval_lock to serialize concurrent requests (e.g. from
        parallel delegation subtasks) so each prompt gets its own turn
        and the shared _approval_state / _approval_deadline aren't clobbered.
        """
        import time as _time

        with self._approval_lock:
            timeout = int(CLI_CONFIG.get("approvals", {}).get("timeout", 300))
            response_queue = queue.Queue()
```

超时后的返回值是字符串 `"timeout"`(不是 `"deny"`),`cli.py:13372 @ 863e313`:

```
            self._approval_state = None
            self._approval_deadline = 0
            self._paint_now()
            _cprint(f"\n{_DIM}  ⏱ Timeout — denying command{_RST}")
            self._persist_prompt_summary(
                "⚠", "Approval", command, "timed out (no response)",
            )
            return "timeout"
```

选项集合只有一个生成点,`cli.py:13381 @ 863e313`:

```
    def _approval_choices(self, command: str, *, allow_permanent: bool = True,
                          smart_denied: bool = False) -> list[str]:
        """Return approval choices for a dangerous command prompt."""
        if smart_denied:
            choices = ["once", "deny"]
        else:
            choices = ["once", "session", "always", "deny"] if allow_permanent else ["once", "session", "deny"]
        if len(command) > 70:
            choices.append("view")
        return choices
```

`view` 是唯一**不入队**的选项,它只是把面板切成展开态并把自己从选项里摘掉,
`cli.py:13427 @ 863e313`:

```
        chosen = choices[selected]
        if chosen == "view":
            state["show_full"] = True
            state["choices"] = [choice for choice in choices if choice != "view"]
            if state["selected"] >= len(state["choices"]):
                state["selected"] = max(0, len(state["choices"]) - 1)
            self._invalidate()
            return

        state["response_queue"].put(chosen)
```

所以 cli.py **实际能投进队列的值只有** `once` / `session` / `always` / `deny`(用户操作)
或 `deny`(中断清理,见 `cli.py:13658 @ 863e313`)。加上超时路径的 `"timeout"`,
cli.py 的输出字母表是封闭的。

#### 2.11.2 决策到底在哪里做

回调注册链:cli.py → `tools.terminal_tool.set_approval_callback`(**thread-local**)→
`check_all_command_guards` → `tools.approval`。注册点 `cli.py:7143 @ 863e313` 与
`cli.py:13984 @ 863e313`(后者在 agent 线程内**重新注册**,因为 TLS 不跨线程):

```
                set_sudo_password_callback(self._sudo_password_callback)
                set_approval_callback(self._approval_callback)
```

TLS 化的原因是一个安全公告,`tools/terminal_tool.py:280 @ 863e313`:

```
def set_approval_callback(cb):
    """Register a callback for dangerous command approval prompts.

    Per-thread scope — ACP sessions that run concurrently in a
    ThreadPoolExecutor each have their own callback slot. See
    GHSA-qg5c-hvr5-hjgr.
    """
    _callback_tls.approval = cb
```

**三道地板在 prompt 之前**,cli.py 完全够不着:`tools/approval.py:3757 @ 863e313`:

```
    # Hardline floor: unconditional block for catastrophic commands
    # (rm -rf /, mkfs, dd to raw device, shutdown/reboot, fork bomb,
    # kill -1). Applies BEFORE yolo / mode=off / cron approve-mode so
    # no session-level setting can bypass it.
    is_hardline, hardline_desc = detect_hardline_command(command)
    if is_hardline:
        logger.warning("Hardline block: %s (command: %s)", hardline_desc, command[:200])
        return _hardline_block_result(hardline_desc, command)
```

后面依次是 sudo-stdin guard(`approval.py:3771`)、用户自定义 deny 规则(`approval.py:3780`),
然后才是 yolo / `mode: off` 的旁路(`approval.py:3789`)。

**cli.py 被信任的到底是什么**——就是这段映射。`tools/approval.py:3382 @ 863e313`:

```
    if choice == "deny":
        return {
            "approved": False,
            "message": (
                f"BLOCKED: User denied this potentially dangerous action "
                f"(matched '{description}'). Do NOT retry — the user has "
                "explicitly rejected it."
            ),
            "pattern_key": pattern_key,
            "description": description,
            "outcome": "denied",
            "user_consent": False,
        }

    if choice == "session":
        approve_session(session_key, pattern_key)
    elif choice == "always":
        approve_session(session_key, pattern_key)
        approve_permanent(pattern_key)
        save_permanent_allowlist(_permanent_approved)

    return {"approved": True, "message": None}
```

**这是 fail-open 的尾巴**:落到最后一行的条件是"不是 timeout、不是 deny",而不是"是 once"。
一个返回 `None`、返回 `""`、返回 `"view"`、或者抛出后被上游吞掉再返回怪值的回调,
都会被判成 approved。唯一的兜底在更外层——回调抛异常时 fail-closed,
`tools/approval.py:2768 @ 863e313`:

```
    if approval_callback is not None:
        try:
            callback_kwargs = {"allow_permanent": allow_permanent}
            if smart_denied:
                callback_kwargs["smart_denied"] = True
            return approval_callback(
                display_command, display_description, **callback_kwargs
            )
        except Exception as e:
            logger.error("Approval callback failed: %s", e, exc_info=True)
            return "deny"
```

所以"cli.py 崩了"是安全的,"cli.py 返回了个奇怪字符串"是不安全的。当前实现不会,
但这是一个**契约靠调用方自律、而不是靠被调方枚举校验**的边界。→ 缺陷 **D12**。

**cli.py 无法削弱的一条策略**:smart-DENY 的 owner override 是"一次性"的,即使 cli.py 返回
`"always"`,approval.py 也不会持久化。`tools/approval.py:4210 @ 863e313`:

```
    # Smart-DENY owner overrides are one-operation scoped. Preserve existing
    # persistence for manual mode and smart ESCALATE.
    if not smart_denied_for_owner:
        for key, _, is_tirith in warnings:
            if choice == "session" or (choice == "always" and is_tirith):
                # tirith: session only (no permanent broad allowlisting)
                approve_session(session_key, key)
```

即:`_approval_choices` 在 `smart_denied` 时藏掉 session/always 只是 **UI 层的礼貌**,
真正的强制在 approval.py。这是正确的分层。

#### 2.11.3 显示的命令 ≠ 执行的命令

审批面板拿到的 `command` 已经过脱敏,`tools/approval.py:2760 @ 863e313`:

```
    # Redact secrets before any user-visible rendering. The original
    # `command` is still what executes after approval; only the displayed
    # copy is scrubbed. Reuses the same redaction module used for memory
    # and log sanitization so tokens mask consistently across surfaces.
    from agent.redact import redact_sensitive_text
    display_command = redact_sensitive_text(command)
    display_description = redact_sensitive_text(description)
```

这是一个**有意识的取舍**(防止 token 泄进终端 scrollback / `persist_prompts` 那一行),
但它的代价是:用户批准的字符串和实际执行的字符串不是同一份。→ 缺陷 **D10**。

#### 2.11.4 面板的行预算:命令可能被截断到看不见

`_get_approval_display_fragments` 的优先级是"标题 + 命令 + 选项必须渲染出来",
描述被挤到最下面截断。`cli.py:13443 @ 863e313`:

```
        Layout priority: title + command + choices must always render, even if
        the terminal is short or the description is long. Description is placed
        at the bottom of the panel and gets truncated to fit the remaining row
        budget. This prevents HSplit from clipping approve/deny off-screen when
        tirith findings produce multi-paragraph descriptions or when the user
        runs in a compact terminal pane.
```

但当命令本身塞不下时,**命令也会被截断**,`cli.py:13558 @ 863e313`:

```
        # If the command itself is too long to leave room for choices (e.g. user
        # hit "view" on a multi-hundred-character command), truncate it so the
        # approve/deny buttons still render. Keep at least 1 row of command.
        max_cmd_rows = max(1, available - chrome_rows - len(choice_wrapped))
        if len(cmd_wrapped) > max_cmd_rows:
            keep = max(1, max_cmd_rows - 1) if max_cmd_rows > 1 else 1
            cmd_wrapped = cmd_wrapped[:keep] + _wrap_panel_text(
                "… (command truncated — use /logs or /debug for full text)",
                inner_text_width,
            )
```

这条兜底提示指向的两个命令**在 CLI 里根本不存在**。全仓搜索 `/logs` 只在 TUI gateway 有
(`tui_gateway/server.py:11750`),`/debug` 一个都没有。

全仓搜索实跑输出(非源码引用,故不参与行号校验):

```
$ grep -rn "\"/logs\"|'/logs'|\"/debug\"|'/debug'" --include=*.py .
./tui_gateway/methods_complete.py:291:                "text": "/logs",
./tui_gateway/methods_complete.py:292:                "display": "/logs",
./tui_gateway/server.py:11750:    ("/logs", "Show recent gateway log lines", "TUI"),
```

也就是说:在窄终端上审批一条超长命令时,用户会被要求为一段**看不全、且没有办法看全**的命令
做安全决策。→ 缺陷 **D9**。

顺带:数字键是直通的,`cli.py:15840 @ 863e313`:

```
        # Number keys for quick approval selection (1-9, 0 for 10th item)
        def _make_approval_number_handler(idx):
            def handler(event):
                if self._approval_state and idx < len(self._approval_state["choices"]):
                    self._approval_state["selected"] = idx
                    self._handle_approval_selection()
                    event.app.invalidate()
            return handler
```

默认选项序是 `["once", "session", "always", "deny"]`,所以按 **`3` = 立刻写入永久 allowlist**,
无二次确认。→ 缺陷 **D11**。

#### 2.11.5 并发:锁的粒度

`_approval_lock` 覆盖的是**整个等待过程**(含 300s 超时),不是只覆盖状态写入。
第二个并发审批请求会阻塞在 `acquire()` 上,既没有超时也没有任何 UI 提示——
面板上只有第一条命令,第二个 delegate 子任务看起来像是卡死了。→ 缺陷 **D17**。

### 2.12 密钥捕获(前提 2 的正面检验)

#### 2.12.1 结构

CLI 侧只是转发,真正的状态机在 `hermes_cli/callbacks.py`。`cli.py:13612 @ 863e313`:

```
    def _secret_capture_callback(self, var_name: str, prompt: str, metadata=None) -> dict:
        return prompt_for_secret(self, var_name, prompt, metadata)
```

提交点是本段的 `_submit_secret_response`,`cli.py:13688 @ 863e313`:

```
    def _submit_secret_response(self, value: str) -> None:
        if not self._secret_state:
            return
        self._secret_state["response_queue"].put(value)
        self._secret_state = None
        self._secret_deadline = 0
        # Modal teardown — paint directly so the secret panel clears at once and
        # isn't held by the _invalidate throttle/resize guard (#41098).
        self._paint_now()

    def _cancel_secret_capture(self) -> None:
        self._submit_secret_response("")

    def _clear_secret_input_buffer(self) -> None:
        if getattr(self, "_app", None):
            try:
                self._app.current_buffer.reset()
            except Exception:
                pass
```

#### 2.12.2 屏幕打码:靠 `PasswordProcessor` + 一个 filter

`cli.py:16493 @ 863e313`:

```
        # --- Input processors for password masking and inline placeholder ---

        # Mask input with '*' when the sudo password prompt is active
        input_area.control.input_processors.append(
            ConditionalProcessor(
                PasswordProcessor(),
                filter=Condition(
                    lambda: bool(cli_ref._sudo_state) or bool(cli_ref._secret_state)
                ),
            )
        )
```

**关键性质:掩码的生命周期绑在 `_secret_state` 上,而不是绑在缓冲区内容上。**
一旦 `_secret_state = None`,同一份缓冲区文本就会以明文渲染。

无 TUI 的回退路径有独立的打码实现(raw mode + 每字符写一个 `*`),
`hermes_cli/secret_prompt.py:16 @ 863e313`:

```
def _collect_masked_input(
    read_char: Callable[[], str],
    write: Callable[[str], object],
    prompt: str,
    *,
    mask: str = "*",
) -> str:
    """Read one secret line while writing a mask character per typed char."""
    value: list[str] = []
    write(prompt)
```

#### 2.12.3 transcript / 历史侧:干净

四个可能泄漏的面都检查过:

**(a) 返回给模型的 dict 不含明文。** `save_env_value_secure` 只回三个字段,
`hermes_cli/config.py:4072 @ 863e313`:

```
def save_env_value_secure(key: str, value: str) -> Dict[str, Any]:
    # Route through the unified credential lifecycle so a rotation via the
    # secret-capture path also refreshes any config.yaml mirror of the old
    # value and lifts a prior env-source suppression (#62269 fix family).
    from hermes_cli.credential_lifecycle import save_provider_env_credential

    save_provider_env_credential(key, value)
    return {
        "success": True,
        "stored_as": key,
        "validated": False,
    }
```

调用方在其上再拼一条自陈消息,`hermes_cli/callbacks.py:157 @ 863e313`:

```
            stored = save_env_value_secure(var_name, value)
            _dhh = display_hermes_home()
            cprint(f"\n{_DIM}  ✓ Stored secret in {_dhh}/.env as {var_name}{_RST}")
            return {
                **stored,
                "skipped": False,
                "message": "Secret stored securely. The secret value was not exposed to the model.",
            }
```

**(b) 不进 prompt_toolkit 的 FileHistory。** 历史文件是
`FileHistory(str(self._history_file))`(`cli.py:16390 @ 863e313`),而 prompt_toolkit 只在
`reset(append_to_history=True)` 时写入。密钥提交路径用的是不带参数的 `reset()`
(默认 `append_to_history=False`),`cli.py:15278 @ 863e313`:

```
            # --- Secret prompt: submit the typed secret ---
            if self._secret_state:
                text = event.app.current_buffer.text
                self._submit_secret_response(text)
                event.app.current_buffer.reset()
                event.app.invalidate()
                return
```

对照:普通消息提交处用的是 `reset(append_to_history=True)`(如 `cli.py:15394 @ 863e313`)。

**(c) 不进 Ctrl+S 草稿暂存。** 暂存本身就是纯内存的(`cli.py:4705 @ 863e313`):

```
        # Ctrl+S prompt stash — park a half-written draft, send something
        # else, bring the draft back.  Session-scoped and in-memory only:
        # drafts routinely contain secrets, so nothing is written to disk.
```

而且模态期间按键 filter 直接把 Ctrl+S 屏蔽掉(`cli.py:15581 @ 863e313`):

```
        # --- Ctrl+S prompt stash -------------------------------------------
        # Park a half-written draft, send something else, then bring the draft
        # back.  Suppressed while a modal prompt owns the composer (sudo /
        # secret / approval / clarify) so Ctrl+S can't stash a password.
        _stash_filter = Condition(
            lambda: not cli_ref._clarify_state
            and not cli_ref._approval_state
            and not cli_ref._sudo_state
            and not cli_ref._secret_state
```

**(d) 不进 scrollback 摘要。** `_persist_prompt_summary` 只被 clarify(`cli.py:13229`)和
approval(`cli.py:13358`、`cli.py:13376`)调用,密钥路径不调。

#### 2.12.4 缺口:`_cancel_secret_capture` 不清缓冲区

三条取消路径里,两条在**调用方**补了 `reset()`:

- ESC:`cli.py:16104 @ 863e313`

```
            if self._secret_state:
                self._cancel_secret_capture()
                event.app.current_buffer.reset()
                event.app.invalidate()
                return
```

- Ctrl+C / Ctrl+Q 的 overlay 清理:`cli.py:15974 @ 863e313`

```
            if _overlay_cleared:
                self._clear_active_overlays_for_interrupt()
                event.app.current_buffer.reset()
                event.app.invalidate()
```

- 超时(在 callbacks.py 内)显式调 `_clear_secret_input_buffer`,`hermes_cli/callbacks.py:174 @ 863e313`:

```
    if hasattr(cli, "_clear_secret_input_buffer"):
        try:
            cli._clear_secret_input_buffer()
        except Exception:
            pass
```

**第四条路径没有补**:`chat()` 的中断监视器在检测到 `_interrupt_queue` 有消息时,
直接调 `_clear_active_overlays_for_interrupt()`,后面**没有任何 buffer reset**
(它跑在 chat 线程上,拿不到 `event.app`)。`cli.py:14157 @ 863e313`:

```
                            self.agent.interrupt(interrupt_msg)
                            # Clear any active overlay states the interrupted agent
                            # left behind.  approval/clarify/sudo/secret prompts gate
                            # input (read_only condition + keypress filter) until
                            # explicitly reset — without this the CLI freezes after
                            # an interrupt until the prompt's own timeout expires (#14026).
                            self._clear_active_overlays_for_interrupt()
```

而 overlay 清理里对密钥的处理就是 `_cancel_secret_capture()`,`cli.py:13682 @ 863e313`:

```
        if self._secret_state:
            try:
                self._cancel_secret_capture()
            except Exception:
                self._secret_state = None
```

后果:`_secret_state` 变 None → `PasswordProcessor` 的 filter 失效 → 已输入的**明文密钥**
留在 composer 里可见;更糟的是,下一次回车会把它当成普通聊天消息发给 agent(此时
`cli.py:15279` 的分支不再命中)。触发条件见 §3-D4。

**类比证据**:sudo 路径的作者显式意识到了缓冲区必须还原——`_sudo_password_callback` 在进入时
`_capture_modal_input_snapshot()`(清空并保存草稿)、退出时 `_restore_modal_input_snapshot()`
(覆盖掉刚输入的密码)。进入时,`cli.py:13267 @ 863e313`:

```
        self._capture_modal_input_snapshot()
        self._sudo_state = {
            "response_queue": response_queue,
        }
```

退出时,`cli.py:13280 @ 863e313`:

```
                self._sudo_state = None
                self._sudo_deadline = 0
                self._restore_modal_input_snapshot()
```

密钥路径**没有**用 snapshot 机制(它用的是"进入时清空缓冲区"),因此少了这层自动还原。

### 2.13 `chat()`:线程本地回调与中断的交接

本段最长的函数。只挑三个和本主题相关的点。

**(a) 回调必须在 agent 线程内重新注册。** `cli.py:13977 @ 863e313`:

```
            def run_agent():
                nonlocal result
                # Set callbacks inside the agent thread so thread-local storage
                # in terminal_tool is populated for this thread.  The main thread
                # registration (run() line ~9046) is invisible here because
                # _callback_tls is threading.local().  Matches the pattern used
                # by acp_adapter/server.py for ACP sessions.
```

并在 `finally` 里清掉,防止线程复用时抓着已销毁 CLI 的引用,`cli.py:14080 @ 863e313`:

```
                    # Clear thread-local callbacks so a reused thread doesn't
                    # hold stale references to a disposed CLI instance.
                    try:
                        set_sudo_password_callback(None)
                        set_approval_callback(None)
                        set_secret_capture_callback(None)
                    except Exception:
                        pass
```

**注意这里的安全含义**:清空之后如果还有别的线程需要审批,它就落到
`prompt_dangerous_approval` 的"无回调 + prompt_toolkit 活着 → 直接 deny"分支
(`tools/approval.py:2780 @ 863e313`),fail-closed。这是刻意的:

```
    # Fail-closed guard: if prompt_toolkit owns the terminal (interactive
    # CLI session) and no approval callback is registered on this thread,
    # the input() fallback below would spawn a daemon thread whose read
    # can never see Enter -- the user's keystrokes go to prompt_toolkit,
    # not input(), producing an invisible 60s deadlock (issue #15216).
```

**(b) yolo 的 session key 绑定。** `/yolo` 是按 session_id 生效的,所以 agent 线程要把
contextvar 绑上,否则 `is_current_session_yolo_enabled()` 查不到。`cli.py:13990 @ 863e313`:

```
                # Bind this turn's approval session key into the contextvar so
                # ``tools.approval.is_current_session_yolo_enabled()`` resolves
                # against the same key that ``/yolo`` toggles under (see
                # ``_toggle_yolo`` → ``enable_session_yolo(self.session_id)``).
                # Mirrors ``tui_gateway/server.py`` and ``gateway/run.py`` which
                # bind the same contextvar before invoking the agent.
```

**(c) 中断后 agent 线程可以被"抛弃"。** 这是一个明确的取舍:宁可留一个 daemon 线程,
也不让 CLI 冻住。`cli.py:14192 @ 863e313`:

```
            if interrupt_msg is not None:
                # Interrupt path: poll briefly, then move on.  The agent
                # thread is daemon — it dies on process exit regardless.
                for _wait_tick in range(50):  # 50 * 0.2s = 10s max
```

配套的一致性处理很细:被抛弃时**不能**清 interrupt flag,因为那是让卡住的工具最终解开的信号。
`cli.py:14350 @ 863e313`:

```
                # If the interrupt landed after finalize_turn()'s
                # clear_interrupt(), the stale flag would instantly abort the
                # NEXT turn at its first loop check. Clear it now that we've
                # claimed the message — but ONLY if the agent thread actually
                # exited. If it's still alive (abandoned after the 10s wait),
                # the flag is what makes the wedged tool eventually unwind;
                # clearing it would un-signal that thread.
```

### 2.14 退出路径与音频电平条

`_persist_active_session_before_close` 是本段唯一**正确**处理 alias 陷阱的持久化调用点
(见 §2.2 的对照),它还处理了"UI 已接受新输入但 worker 还持有旧快照"的中间态,
`cli.py:14623 @ 863e313`:

```
            if isinstance(pending_cli_message, dict) and not any(
                message is pending_cli_message for message in messages
            ):
                # The UI has accepted a new input but the worker still exposes its
                # prior snapshot. Include only that staged dict; the baseline below
                # keeps any durable resumed prefix from being re-appended.
                messages = [*messages, pending_cli_message]
```

`_audio_level_bar` 是全段最短的函数,`cli.py:14796 @ 863e313`:

```
    def _audio_level_bar(self) -> str:
        """Return a visual audio level indicator based on current RMS."""
        _LEVEL_BARS = " ▁▂▃▄▅▆▇"
        rec = getattr(self, "_voice_recorder", None)
        if rec is None:
            return ""
        rms = rec.current_rms
        # Normalize RMS (0-32767) to 0-7 index, with log-ish scaling
        # Typical speech RMS is 500-5000, we cap display at ~8000
        level = min(rms, 8000) * 7 // 8000
        return _LEVEL_BARS[level]
```

几点核对(都**没有**问题,记录以免后续误判):
- `rec` 先取到本地变量,`_disable_voice_mode` 并发把 `self._voice_recorder = None` 不会导致 AttributeError。
- 两种 recorder 都提供 `current_rms` 且都是 `int`——Termux 版恒为 0(`tools/voice_mode.py:705 @ 863e313`):

```
    @property
    def current_rms(self) -> int:
        return self._current_rms
```

- 索引范围:`_LEVEL_BARS` 长 8,`min(rms, 8000) * 7 // 8000` ∈ [0, 7],不会越界。
- 注释里的 "log-ish scaling" 与代码不符:实现是**线性**映射再截断到 8000,没有任何对数。
  这是注释与代码的小出入(§4)。

它的唯一消费点是提示符片段,`cli.py:14823 @ 863e313`:

```
        if self._voice_recording:
            bar = self._audio_level_bar()
            return _state_fragment("class:voice-recording", "●", bar)
```

刷新靠 §2.5 那个 0.15s 心跳线程,`cli.py:12337 @ 863e313`:

```
        # Periodically refresh prompt to update audio level indicator
        def _refresh_level():
            while True:
                with self._voice_lock:
                    still_recording = self._voice_recording
                if not still_recording:
                    break
```

---

## 3. 可疑缺陷清单

### D1 —— `/reload-mcp` 的"立刻持久化"是空操作,且把新消息永久标记为已持久化

- **现象**:`_reload_mcp` 注入的 `[IMPORTANT: MCP servers have been reloaded...]` 用户消息
  永远不会出现在 `state.db` 里;`/resume` 后的会话看不到这条通知。更严重的是这次调用会把
  `conversation_history` 里**所有**尚未落库的消息一并盖上 `_db_persisted` 戳,以后再也写不进去。
- **锚点**:`cli.py:11908 @ 863e313`(传同一个 list);`run_agent.py:2083 @ 863e313`
  (`history_ids` 按对象身份构造);`run_agent.py:2131 @ 863e313`(命中即 stamp + continue);
  `run_agent.py:2949 @ 863e313`(JSON 快照默认关闭,所以另一条写路径也是 no-op)。
- **为什么可疑**:同一文件的关闭路径**专门**防了这个 alias(`cli.py:14651 @ 863e313`),
  并在注释里写明"passing that alias would mark an unflushed tail durable without writing it"
  (`cli.py:14637 @ 863e313`)。`/reload-mcp` 违反了这条自述不变量。
- **触发条件**:任何一次 `/reload-mcp`(且 `self.agent is not None`)。默认配置即触发。
- **置信度**:**高**(纯数据流推理,三处代码互证)。

### D2 —— `/reload-mcp` 注入幽灵 user turn,与 `_reload_skills` 的既定做法冲突

- **现象**:连续两次 `/reload-mcp`(中间不发消息)会在历史里留下两条相邻的 `role: user`;
  即使只一次,如果上一条恰好也是 user(例如被中断的轮次),也会破坏 alternation。
- **锚点**:`cli.py:11899 @ 863e313`(直接 append user 消息);
  `cli.py:11929 @ 863e313`(`_reload_skills` docstring 明确说不这么做的理由是
  "This preserves message alternation (no phantom user turn injected out of band)")。
- **为什么可疑**:仓库已经演化出了正确做法(pending note,`cli.py:14020 @ 863e313`),
  MCP 路径是没跟上的遗留。
- **触发条件**:`/reload-mcp` 在一条 user 消息之后立即执行,或连续执行两次。
- **置信度**:**中**(形状确定;实际是否报错取决于 adapter 是否合并相邻 user 消息,未在本轮验证)。

### D3 —— `_pending_tool_info` 在非回显模式下只进不出(进程级累积)

- **现象**:`display.tool_progress: off`、focus view、`-Q` 批处理下,每次工具调用的
  `function_args` 都被存进 `_pending_tool_info` 且永不弹出。长会话下持续增长。
- **锚点**:`cli.py:12158 @ 863e313`(无条件 append);`cli.py:12101 @ 863e313`
  (pop 被 `self.tool_progress_mode in {"new", "all", "verbose"}` 门控);
  `cli.py:18369 @ 863e313`(`-Q` 设成 `"off"`)。
- **为什么可疑**:`function_args` 可以很大——`_on_tool_gen_start` 的 docstring 自己举的例子
  就是"a large payload (e.g. 45 KB write_file)"(`cli.py:12007 @ 863e313`)。
- **触发条件**:`tool_progress` 不在白名单的三种取值之内 + 长时间会话。
- **置信度**:**高**(控制流直读)。

### D4 —— 中断路径取消密钥捕获时,明文密钥留在输入缓冲区且掩码已失效

- **现象**:密钥提示框打开、用户已输入部分密钥时,如果走 `chat()` 的中断监视器路径取消,
  `_secret_state` 被清空(掩码 filter 随之失效),但输入缓冲区没有被 reset——
  明文出现在 composer 里;此后回车会把它当普通消息发给 agent。
- **锚点**:`cli.py:13682 @ 863e313`(`_cancel_secret_capture()`,无 buffer reset);
  `cli.py:13688 @ 863e313`(`_submit_secret_response` 本身不碰 buffer);
  `cli.py:14157 @ 863e313`(chat 线程上的调用点,后面没有 reset);
  `cli.py:16496 @ 863e313`(掩码 filter 绑在 `_secret_state` 上);
  `cli.py:13701 @ 863e313`(`_clear_secret_input_buffer` 存在但这条路径不调它)。
- **为什么可疑**:另外三条取消路径(ESC / Ctrl+C / 超时)都补了清理,唯独这条漏了;
  且 sudo 路径用 snapshot 机制天然免疫。属于"同类路径覆盖不全"。
- **触发条件**:需要在密钥提示框打开期间,`_interrupt_queue` 里恰好有一条未被消费的消息。
  由于 `_secret_state` 活跃时 Enter 被 `cli.py:15279` 抢走,消息只能来自提示框打开**之前**
  排队的输入,而队列每 0.1s 被消费一次(`cli.py:14139 @ 863e313`)——窗口很窄。
- **置信度**:**中**(代码路径确定无疑;实际触发概率低,因为竞态窗口窄)。

### D5 —— `_voice_tts_done` 可能永久停留在 clear 状态

- **现象**:全双工监听器不再释放麦克风,`_voice_stop_and_transcribe` 的无语音计数永不递增,
  连续语音模式表现为"卡在听"。
- **锚点**:`cli.py:12521 @ 863e313`(async 先 clear);
  `cli.py:12540 @ 863e313`(线程体早退分支在 `try` 之前);
  `cli.py:12607 @ 863e313`(`finally` 的 set 因此不执行);
  `cli.py:12670 @ 863e313`(`_should_stop` 依赖它);
  `cli.py:13128 @ 863e313`(`/voice tts` 关闭时**不** set)。
- **为什么可疑**:`_disable_voice_mode` 显式补了 `self._voice_tts_done.set()`
  (`cli.py:12894 @ 863e313`),说明作者知道这个 Event 有"可能没人 set"的风险,
  但只堵了一条路径。
- **触发条件**:在 `_voice_speak_response_async` clear 之后、线程体读到 `self._voice_tts`
  之前执行 `/voice tts`(或任何把 `_voice_tts` 置 False 而不 set Event 的路径)。
- **置信度**:**中低**(窗口极窄,但缺失的 `finally` 覆盖是结构性的)。

### D6 —— 全双工监听器的单例保护是无锁 check-and-set,且 Event 惰性创建

- **现象**:理论上可以有两个 `full_duplex_listen` 同时开麦。
- **锚点**:`cli.py:12636 @ 863e313`(惰性创建 + 无锁 check-and-set);
  `cli.py:4722 @ 863e313`(`__init__` 初始化了兄弟 Event 却没初始化 `_voice_fd_active`);
  两个并发武装点 `cli.py:13894 @ 863e313` 与 `cli.py:12532 @ 863e313`。
- **为什么可疑**:注释断言"the listener refuses to double-arm via _voice_fd_active"
  (`cli.py:12530 @ 863e313`),但实现给不了这个保证。同一文件里
  `_voice_start_recording` 的同类保护是**带锁**的(`cli.py:12244 @ 863e313`),
  说明作者本来懂这个模式。
- **触发条件**:`chat()` 起始与 `_voice_speak_response_async` 的兜底武装在几十微秒内相撞。
- **置信度**:**中低**。

### D7 —— `_wake_watchdog_started` 由启动方置位 / 线程清位,`/wake off` + `/wake on` 有丢看门狗的窗口

- **现象**:新的唤醒词监听器可能没有看门狗;下一次唤醒后探测器被 pause 且永不 resume,
  唤醒词静默失效直到再 `/wake off; /wake on`。
- **锚点**:`cli.py:13053 @ 863e313`(启动方置位);`cli.py:13087 @ 863e313`(线程 `finally` 清位);
  `cli.py:12977 @ 863e313`(`_stop_wake_word_listener` 置 `_wake_word_active = False`);
  `cli.py:12967 @ 863e313`(重启时调 `_start_wake_watchdog`);
  `cli.py:12935 @ 863e313`(幂等早返回分支**不**调 `_start_wake_watchdog`)。
- **为什么可疑**:标志的置位方和清位方在不同线程,中间没有同步原语。
- **触发条件**:`/wake off` 之后在旧线程执行 `finally` 之前(几条字节码)完成 `/wake on`。
- **置信度**:**低**(窗口极窄),但形状是标准竞态。

### D8 —— 退出清理不通知看门狗,它靠 daemon 属性被动收尸

- **现象**:`_run_cleanup` 期间(可能数秒)看门狗仍以 4Hz 空转;`_wake_word_active` 从未被
  退出路径置 False。另外 `resume_listening` 失败时把 `_wake_word_active` 置 False 是**静默**的,
  用户不知道唤醒词已经死了。
- **锚点**:`cli.py:1191 @ 863e313`(cleanup 只调 `stop_listening`);
  `cli.py:13060 @ 863e313`(循环条件只看 `_wake_word_active` / `_should_exit`);
  `cli.py:13062 @ 863e313`(非 suspended 时直接 `continue`,永不检查探测器是否还在);
  `cli.py:13083 @ 863e313`(静默降级)。
- **为什么可疑**:与 `_run_cleanup` 里其它子系统的处理不对称——别的都显式 teardown。
  安全性上是 OK 的(`tools/wake_word.py:1368 @ 863e313` 保证租约作废后 resume 必失败),
  但"干净停止"这个说法不成立。
- **触发条件**:每次退出。
- **置信度**:**高**(现象);影响低(daemon 线程,且有 `_arm_exit_watchdog` 兜底强制
  `os._exit(0)`,`cli.py:1119 @ 863e313`)。

### D9 —— 审批面板会截断命令,兜底提示指向不存在的 `/logs` / `/debug`

- **现象**:窄终端 + 长命令时,用户看到 `… (command truncated — use /logs or /debug for full text)`,
  但这两个命令在 CLI 里不存在(只有 TUI gateway 有 `/logs`)。用户无法看到自己正在批准的完整命令。
- **锚点**:`cli.py:13565 @ 863e313`(提示文案);`cli.py:13562 @ 863e313`(截断逻辑);
  `cli.py:13388 @ 863e313`(`view` 只在 `len(command) > 70` 时提供);
  `tui_gateway/server.py:11750 @ 863e313`(唯一的 `/logs`,属于 TUI 不属于 CLI)。
- **为什么可疑**:这是**安全决策界面**的信息完整性问题——被截断的恰恰是要审的内容。
- **触发条件**:`available - chrome_rows - len(choice_wrapped) < len(cmd_wrapped)`,
  即终端行数少(reserved_below 固定按 6 行预算,`cli.py:13548 @ 863e313`)或命令很长。
- **置信度**:**高**(命令不存在这一点是全仓 grep 确认的)。

### D10 —— 展示的命令是脱敏副本,执行的是原始命令

- **现象**:用户批准的字符串与实际执行的字符串不是同一份。
- **锚点**:`tools/approval.py:2760 @ 863e313`(注释与实现都明说)。
- **为什么可疑**:这是有意识的取舍(防 token 进 scrollback),但脱敏规则一旦命中命令的**语义部分**
  (例如某段看起来像 token 的参数),用户批准的就不是他以为的东西。
- **触发条件**:命令里含被 `agent.redact.redact_sensitive_text` 识别为敏感的片段。
- **置信度**:**高**(事实层);风险评级**中**(未验证 redact 规则的误报率)。

### D11 —— 数字键 `3` 直通"永久 allowlist",无二次确认

- **锚点**:`cli.py:15849 @ 863e313`(0-9 全部绑定);`cli.py:13387 @ 863e313`
  (默认序 `["once", "session", "always", "deny"]`);`cli.py:13436 @ 863e313`(直接入队)。
- **为什么可疑**:与"deny 在最后一位"叠加,误按 `3` 的代价(永久放行一类命令)远大于误按 `4`。
- **触发条件**:审批面板打开时按数字键。
- **置信度**:**高**(事实);是否算缺陷取决于产品取舍。

### D12 —— 裁决映射是 fail-open 的:非 `timeout`/`deny` 即批准

- **锚点**:`tools/approval.py:3382 @ 863e313`(`_run_approval_gate` 尾部);
  `tools/approval.py:4192 @ 863e313`(`check_all_command_guards` 尾部同形状)。
- **为什么可疑**:安全边界的默认值应当是拒绝。目前靠"cli.py 的输出字母表恰好封闭"来保证正确,
  没有在 approval.py 侧做白名单校验(`if choice not in {"once","session","always"}: return deny`)。
  一旦有新的 surface 接入这个回调协议(ACP / TUI / 第三方),这是最容易踩的坑。
- **触发条件**:任何返回值不在预期集合内的审批回调实现。
- **置信度**:**高**(代码直读)。

### D13 —— `voice.max_recording_seconds` / `silence_*` 在 Termux 后端是死配置

- **锚点**:`cli.py:12284 @ 863e313`、`cli.py:12297 @ 863e313`(无条件 setattr);
  `tools/voice_mode.py:683 @ 863e313`(`TermuxAudioRecorder` 不声明这些属性);
  `tools/voice_mode.py:709 @ 863e313`(`del on_silence_stop`,连静音回调都丢弃);
  `tools/voice_mode.py:857 @ 863e313`(只有 `AudioRecorder` 读 `_max_recording_seconds`)。
- **为什么可疑**:CLI 已经按 `supports_silence_autostop` 换了**提示文案**
  (`cli.py:12329 @ 863e313`),说明作者知道两种后端能力不同,但没对 `max_recording_seconds`
  做同等提示;文档也把它写成无条件的 "Hard stop for long recordings"。
- **触发条件**:Termux 环境 + 配置了这三个键之一。
- **置信度**:**高**。

### D14 —— `_disable_voice_mode` 的复合条件可能漏掉标志复位

- **锚点**:`cli.py:12866 @ 863e313`:

```
        with self._voice_lock:
            if self._voice_recording and self._voice_recorder:
                self._voice_recorder.cancel()
                self._voice_recording = False
```

- **为什么可疑**:`_voice_recording` 的复位与 `_voice_recorder` 非空绑在同一个条件里。
  若两者短暂不一致(例如另一线程刚把 recorder 置 None),`_voice_recording` 会永久停在 True,
  之后所有 `_voice_start_recording` 都被 §2.5(a) 的 guard 静默吃掉——正是 §2.5(b) 注释
  警告的那种状态。
- **触发条件**:`_voice_recorder = None` 与 `_disable_voice_mode` 交错。注意 `_voice_recorder = None`
  的赋值在锁**外**(`cli.py:12883 @ 863e313`)。
- **置信度**:**低**(需要特定交错;当前唯一的置 None 点就在本函数内)。

### D15 —— 唤醒捕获失败后 `_voice_mode` 停在 True

- **锚点**:`cli.py:13042 @ 863e313`:

```
        with self._voice_lock:
            self._voice_mode = True
        self._voice_continuous = False
        try:
            self._voice_start_recording()
        except Exception as e:
            _cprint(f"{_DIM}Wake capture failed: {e}{_RST}")
            # Leave _wake_suspended set; the watchdog resumes once idle.
```

- **为什么可疑**:异常分支只关心 `_wake_suspended`,没有回滚 `_voice_mode`。用户没主动开语音,
  却进入了 voice mode(提示符变 🎤,`_typed_voice_stop` 开始拦截打字的 "stop")。
- **触发条件**:唤醒词触发时语音依赖不满足(如没配 STT),`_voice_start_recording` 抛
  `RuntimeError`(`cli.py:12235 @ 863e313`)。
- **置信度**:**中低**(路径确定;是否算缺陷取决于是否有意为之)。

### D16 —— `_reload_mcp` 的持久化注释描述了一个不存在的效果

- **锚点**:`cli.py:11904 @ 863e313`("so the session log reflects the updated tools list");
  `run_agent.py:621 @ 863e313`(`_ensure_db_session` 建的 session 行里没有 tools 字段);
  `run_agent.py:2949 @ 863e313`(JSON 快照默认关)。
- **为什么可疑**:session 行记录的是 `source / model / model_config / system_prompt / cwd / profile`,
  **没有 tools**;`_persist_session` 也只处理消息。注释描述的因果不存在。
- **触发条件**:阅读代码时被注释误导。
- **置信度**:**高**。

### D17 —— `_approval_lock` 覆盖整个等待窗口,第二个并发审批无限期静默阻塞

- **锚点**:`cli.py:13321 @ 863e313`(`with self._approval_lock:` 包住整个循环);
  `cli.py:13336 @ 863e313`(deadline 在**取得锁之后**才计算)。
- **为什么可疑**:好处是第二个请求不会因为排队而"提前超时";代价是它在 `acquire()` 上
  **没有超时、没有 UI 提示**。并行 delegate 子任务同时命中危险命令时,用户只看到一条,
  另一条静默等待最长 300s(第一条超时)才轮到自己。
- **触发条件**:并行子任务同时触发审批。
- **置信度**:**中**(行为确定;是否算缺陷取决于产品预期)。

---

## 4. 与文档/注释的出入

> 记号:▲ = 文档/注释与代码冲突,以代码为准;◇ = 文档/注释不完整或误导。

**▲ 1. 审批面板指向不存在的命令。** `cli.py:13565 @ 863e313` 写
`"… (command truncated — use /logs or /debug for full text)"`,但 CLI 无 `/logs`、无 `/debug`
(全仓仅 `tui_gateway/server.py:11750` 有一个 TUI 侧的 `/logs`)。定案:以代码为准,该提示是错的。

**▲ 2. `voice.max_recording_seconds` 的文档没有后端条件。**
`website/docs/user-guide/configuration.md:1886 @ 863e313`:

```
  max_recording_seconds: 120    # Hard stop for long recordings
```

`website/docs/user-guide/features/voice-mode.md:413 @ 863e313` 同样无条件。
实际只有 `AudioRecorder`(sounddevice)后端生效,Termux 后端完全忽略(见 D13)。

**▲ 3. `_reload_mcp` 的持久化注释。** `cli.py:11904 @ 863e313` 声称
"so the session log reflects the updated tools list";实际既没有 tools 字段,持久化本身
在默认配置下也不写任何东西(见 D1 / D16)。

**▲ 4. `_audio_level_bar` 的 "log-ish scaling"。** `cli.py:14803 @ 863e313`:

```
        # Normalize RMS (0-32767) to 0-7 index, with log-ish scaling
        # Typical speech RMS is 500-5000, we cap display at ~8000
        level = min(rms, 8000) * 7 // 8000
```

实现是线性映射 + 截断,没有任何对数成分。

**▲ 5. 全双工监听器的"拒绝重复武装"断言。** `cli.py:12530 @ 863e313` 声称
"the listener refuses to double-arm via _voice_fd_active";实现是无锁 check-and-set,
给不了这个保证(见 D6)。

**◇ 6. `terminal_tool` 的 "CLI mode is single-threaded"。**
`tools/terminal_tool.py:256 @ 863e313`:

```
# CLI mode is single-threaded, so each thread (the only one) holds its
# own callback exactly like before. Gateway mode resolves approvals via
# the per-session queue in tools.approval, not through these callbacks,
# so it's unaffected.
```

CLI 实际上有大量线程(agent 线程、process_loop、语音录制 / TTS / 全双工监听、唤醒看门狗、
电平刷新、exit watchdog)。这条注释成立**只是因为** `chat()` 在 agent 线程里重新注册了
一遍回调(`cli.py:13984 @ 863e313`)。注释描述的前提是错的,结论碰巧对。

**◇ 7. `security.md` 对 `approvals.mode: off` 的描述过强。**
`website/docs/user-guide/security.md:55 @ 863e313` 写
"**off** | Disable all approval checks — equivalent to running with `--yolo`. All commands
execute without prompts."。实际 hardline 地板、sudo-stdin guard、用户 deny 规则都在
`mode` 判定**之前**执行(`tools/approval.py:3761 / 3771 / 3780 @ 863e313`),`mode: off` 一样绕不过。
文档只在 YOLO 那一段做了 hardline 例外说明,没有对 `mode: off` 做同样说明。

**◇ 8. `voice.barge_in_threshold_multiplier` 默认值的链路。**
`website/docs/user-guide/features/voice-mode.md:187 @ 863e313` 写默认 `3.0`,**结论正确**,
但 cli.py 侧读到的默认是 `0`(`cli.py:12655 @ 863e313`),经 `multiplier=_mult or None`
(`cli.py:12710 @ 863e313`)传下去,最终由 `tools/voice_mode.py:1932 @ 863e313`
`DEFAULT_BARGE_MULTIPLIER = 3.0` 兜底。副作用:显式配置 `0` 与不配置**不可区分**,
都会退回 3.0。记为不完整而非冲突。

---

## 5. 移交

### 5.1 本段确认的、可迁移的设计要点(给"造自己的 harness"用)

1. **"贵操作"要有单独的确认门 + 一次性豁免开关**。`/reload-mcp` 的门不是安全门,是**成本门**
   (prompt cache 失效 = 真金白银)。这类门应当:现读配置(让"Always"立刻生效)、
   走 UI 原生模态而非 `input()`(避免和 TUI 抢 stdin)、Always 时把开关写进配置文件而不是内存。
2. **告诉模型"环境变了"有两种做法,选后者**:注入幽灵 user turn(破坏 alternation、进 transcript、
   可能触发 provider 拒绝)vs. API-call-local 的一次性前缀 note(不进历史、不破坏 cache 前缀)。
   本仓库同时存在两种,新代码(skills / model switch / speech-interrupted)全部用后者。
3. **N 条退出路径的资源回收,化约成 1 个"suspended 标志 + 幂等看门狗"**。唤醒词的麦克风让渡
   就是这么做的,注释里明确说这是为了"covering every exit path ... without threading resume
   logic through the voice machinery"(`cli.py:12907 @ 863e313`)。代价是引入一个轮询线程,
   而这个线程的**终止条件必须被退出路径显式触发**——本仓库正是漏了这一步(D8)。
4. **回调式安全边界要在被调方做白名单校验,不要靠调用方自律**。approval.py 的
   "非 deny/timeout 即 approved" 是 fail-open 尾巴(D12);正确形状是
   `if choice not in APPROVE_VERDICTS: return deny`。
5. **UI 掩码的生命周期不要绑在"模态状态"上,要绑在"缓冲区内容"上**。本仓库把
   `PasswordProcessor` 的 filter 绑在 `_secret_state`,于是每一条清 state 的路径都必须
   **额外记得**清缓冲区——四条路径漏了一条(D4)。更稳的做法是 state 清空时**由清空方**
   同步清缓冲,或者干脆用 sudo 那套 snapshot(进入时保存并清空、退出时无条件覆盖回写)。
6. **配置项的类型守卫必须显式排除 `bool`**(Python 里 `bool` 是 `int` 子类)。
   `cli.py:12274 @ 863e313` 的注释把这个坑讲得很清楚,值得直接抄。
7. **多后端实现下,"配置已生效"要按后端能力分别声明**。setattr 到实例上的参数在不实现它的
   后端上是静默死配置(D13)。至少要像 `supports_silence_autostop` 那样给出能力位并在 UI 上体现。

### 5.2 未验证 / 留给后续轮次

- D2 的实际影响需要看 adapter 层是否合并相邻 user 消息(R2 的 adapter 底稿可能已有结论)。
- D10 的风险评级需要读 `agent/redact.py` 的规则集,评估误报率。
- `_get_approval_display_fragments` 的 `reserved_below = 6`(`cli.py:13548 @ 863e313`)是
  "Measured at ~6 rows during live PTY approval prompts" 的经验值,不同 skin / 状态栏宽度下
  是否仍准确未验证。
- `tests/cli/test_cli_approval_ui.py` 与 `tests/cli/test_cli_secret_capture.py` 是本段的行为规格。
  值得注意的是:**没有任何测试断言"密钥不会进入 transcript / 历史"**,也没有测试覆盖 D4 的
  中断取消路径。若要补测试,这两处是最有价值的。
- 本段未运行任何测试(本轮定位为静态精读)。运行方式见 `CLAUDE.md` 的测试环境章节。

### 5.3 给成品章的素材优先级

按"读者能复述"的价值排序,建议成品章优先讲:
1. 唤醒词的"租约 + 看门狗"模式(§2.10)——最完整的一个设计故事,含正反两面。
2. 全双工 barge-in 从"只在播放时听"到"整轮都听"的演进(§2.8)——事故因果清晰,可讲成故事。
3. 审批的分层(cli.py = 提示与词表,approval.py = 策略与地板)与那条 fail-open 尾巴(§2.11)。
4. 两种"通知模型环境变了"的做法对比(§2.2 / §2.3)——一个仓库内部演进的活标本。
