# r7 底稿 · gateway/run.py 第 8 段(18967–21424)—— voice 频道 / 媒体投递 / 后台任务 / 生命周期通知 / 会话上下文

> 溯源约定:所有断言紧跟 `路径:行号 @ 863e313` + 代码原文。本段属 GatewayRunner 类体
> (run.py 全文 27146 行)。研究对象只读。

覆盖范围(逐机制):
1. Discord voice 频道 join/leave/超时清理(18967–19070)
2. 重复语音转写去重(19071–19110)
3. voice 频道输入 → 合成 MessageEvent 全管线(19112–19189)
4. voice 回复判定 `_should_send_voice_reply`(19191–19269)
5. voice 回复发送 `_send_voice_reply`(19271–19342)
6. 流式后媒体投递 `_deliver_media_from_response`(19344–19451)
7. 后台任务运行框架 `_run_background_task(+inner)`(19455–19686)
8. Telegram topic 能力探测 / System topic / setup 截图 / 标题清洗(19694–19790)
9. Discord auto-thread 与 relay lane 判定(19792–19869)
10. Discord 语义化改名(19871–20025)
11. Telegram topic 语义化改名(20027–20170)
12. Telegram capability hint / help / off / root status / restore(20172–20350)
13. `_execute_mcp_reload`(20358–20463)
14. 破坏性 slash 确认原语(20467–20661)
15. `_read_user_config`(20663–20674)
16. thread metadata 构造(20676–20762)
17. reply anchor(20764–20767)
18. `/update` 平台白名单(20778–20789)
19. update 通知 watcher(20793–21169)
20. restart 通知(21171–21248)
21. home channel 启动通知(21250–21331)
22. `_set_session_env` / `_clear_session_env` 与 session_context 的关系(21333–21374,重点)
23. `_run_in_executor_with_context`(21375–21384)
24. executor 管理(21386–21423)

---

## 1. Discord voice 频道 join / leave / 超时清理

**问题**:Discord 的语音频道(voice channel)是独立于文字频道的实时音频房间。要让 agent
"进房听人说话、用 TTS 答话",runner 必须:找到用户所在的语音频道、建立连接、把 adapter
的语音回调接回 runner、并在离开/超时后把 runner 侧状态(voice_mode、auto-TTS)清干净。

**实现**:`_get_guild_id` 从 raw_message 里兼容两种形态取 guild(服务器)ID:

`gateway/run.py:18967-18978 @ 863e313`
```python
    def _get_guild_id(event: MessageEvent) -> Optional[int]:
        """Extract Discord guild_id from the raw message object."""
        raw = getattr(event, "raw_message", None)
        if raw is None:
            return None
        # Slash command interaction
        if hasattr(raw, "guild_id") and raw.guild_id:
            return int(raw.guild_id)
        # Regular message
        if hasattr(raw, "guild") and raw.guild:
            return raw.guild.id
        return None
```

`_handle_voice_channel_join` 的关键次序:**先接回调、后 join** —— 否则连接建立后
立刻到达的语音输入会丢:

`gateway/run.py:18997-19008 @ 863e313`
```python
        # Wire callbacks BEFORE join so voice input arriving immediately
        # after connection is not lost.
        if hasattr(adapter, "_voice_input_callback"):
            adapter._voice_input_callback = self._handle_voice_channel_input
        if hasattr(adapter, "_on_voice_disconnect"):
            adapter._on_voice_disconnect = self._handle_voice_timeout_cleanup
        # Let the adapter's inactivity timer see the live voice-reply mode so it
        # doesn't disconnect a deliberately text-only (/voice off) session.
        if hasattr(adapter, "_voice_mode_getter"):
            adapter._voice_mode_getter = lambda chat_id: self._voice_mode.get(
                self._voice_key(Platform.DISCORD, str(chat_id)), "off"
            )
```

三个回调槽位都定义在 Discord 插件 adapter 上(`plugins/platforms/discord/adapter.py:1039-1045
@ 863e313`,注释 `# set by run.py`),即 **adapter 只留钩子、策略全在 runner** 的控制反转。
join 成功后记录 guild→文字频道 / guild→source 双映射,并把该 chat 的 voice_mode 置为 "all"
且持久化:

`gateway/run.py:19023-19029 @ 863e313`
```python
        if success:
            adapter._voice_text_channels[guild_id] = int(event.source.chat_id)
            if hasattr(adapter, "_voice_sources"):
                adapter._voice_sources[guild_id] = event.source.to_dict()
            self._voice_mode[self._voice_key(event.source.platform, event.source.chat_id)] = "all"
            self._save_voice_modes()
            self._set_adapter_auto_tts_enabled(adapter, event.source.chat_id, enabled=True)
```

join 抛异常时给出可操作的错误信息(PyNaCl/davey 依赖缺失时直接给 pip 命令,
`gateway/run.py:19015-19020 @ 863e313`),并清回调防悬挂。

leave 侧的关键取舍:**即使 leave_voice_channel 抛异常,也无条件清理 runner 侧状态**:

`gateway/run.py:19049-19059 @ 863e313`
```python
        try:
            await adapter.leave_voice_channel(guild_id)
        except Exception as e:
            logger.warning("Error leaving voice channel: %s", e)
        # Always clean up state even if leave raised an exception
        self._voice_mode[self._voice_key(event.source.platform, event.source.chat_id)] = "off"
        self._save_voice_modes()
        self._set_adapter_auto_tts_disabled(adapter, event.source.chat_id, disabled=True)
        if hasattr(adapter, "_voice_input_callback"):
            adapter._voice_input_callback = None
```

adapter 的不活动计时器断线时反向调用 `_handle_voice_timeout_cleanup(chat_id)`
(`gateway/run.py:19061-19069 @ 863e313`),把 runner 侧 voice_mode 置 off——因为
adapter 摸不到 runner 的 `_voice_mode` 字典。adapter 侧的调用点:
`plugins/platforms/discord/adapter.py:4382-4384 @ 863e313`
(`self._on_voice_disconnect(str(text_ch_id))`,传的是**文字频道 id 字符串**,与 runner
侧签名一致)。

**voice_mode 状态存储**:`_voice_key` 是 `f"{platform.value}:{chat_id}"`
(`gateway/run.py:6352-6354 @ 863e313`);持久化到
`_VOICE_MODE_PATH = _hermes_home / "gateway_voice_mode.json"`(`gateway/run.py:6350 @ 863e313`);
`_load_voice_modes` 会跳过不带平台前缀的 legacy key 并告警(`gateway/run.py:6371-6378`)。
合法值三态:`{"off", "voice_only", "all"}`(`gateway/run.py:6365`)。

**另一个 join 入口**:除了 /voice join 命令,平台连接/重连时也无条件接上
`_voice_input_callback`(`gateway/run.py:11122-11124`、重连路径 `12485-12487 @ 863e313`,
后者注释引 #60623:重连后忘记重新接回调导致语音输入静默丢失)。

**重实现要点**:
- 回调必须在 join 之前接好(消息竞态);join 失败/异常路径必须把回调清回 None。
- runner 与 adapter 各有一份状态(mode 字典 vs 连接对象),清理必须两边都做、且
  leave 失败也要清 runner 侧(状态一致优先于操作成功)。
- adapter 只留 `_voice_input_callback/_on_voice_disconnect/_voice_mode_getter` 三个钩子,
  策略(mode、授权、TTS 开关)全部留在 runner——插件化平台不用 import runner。
- 不活动断线计时器需要能读"当前 voice mode",否则会把故意 text-only 的会话踢下线
  (`_voice_mode_getter` 存在的唯一理由,19003-19008 注释)。
- 依赖类错误(PyNaCl)要翻译成用户可执行的修复命令,不要只抛原始异常。

## 2. 重复语音转写去重 `_is_duplicate_voice_transcript`

**问题**:语音捕获偶尔会在几秒内把同一句话吐两次(STT 分段抖动),造成第二次排队的
agent run 和重叠的语音答复。

**实现**:按 (guild_id, user_id) 维护最近转写窗口,正规化(压空白、去标点、小写)后
先做精确匹配,长句(≥16 字符)再用 `SequenceMatcher` 相似度 ≥0.95 做近似匹配:

`gateway/run.py:19086-19110 @ 863e313`
```python
        now = time.monotonic()
        window_seconds = 12.0
        key = (guild_id, user_id)
        recent_store = getattr(self, "_recent_voice_transcripts", None)
        if not isinstance(recent_store, dict):
            recent_store = {}
            self._recent_voice_transcripts = recent_store
        recent = [
            (ts, txt)
            for ts, txt in recent_store.get(key, [])
            if now - ts <= window_seconds
        ]

        for _, prior in recent:
            if prior == normalized:
                recent_store[key] = recent
                return True
            if len(prior) >= 16 and len(normalized) >= 16:
                if SequenceMatcher(None, prior, normalized).ratio() >= 0.95:
                    recent_store[key] = recent
                    return True

        recent.append((now, normalized))
        recent_store[key] = recent[-5:]
        return False
```

**设计理由与取舍**:12 秒窗口 + 每 key 只留 5 条 → 内存有界;短句不做模糊匹配
(避免把 "yes"/"yeah" 这类真实的连续短答误杀);用 `time.monotonic()` 免受系统时钟
调整影响;`getattr` 惰性建 store 兼容 `object.__new__` 的裸 runner 测试替身。

**重实现要点**:
- 去重键要含说话人(guild+user),不能全局去重——两个人先后说同一句是合法输入。
- 精确 + 高阈值模糊双层;模糊层设最短长度门槛。
- 窗口和容量双限,防泄漏;命中时也要顺手把过期项裁掉(19101/19105 回写 recent)。

## 3. voice 输入 → 合成 MessageEvent 全管线 `_handle_voice_channel_input`

**问题**:语音转写不是平台原生消息,没有现成的 MessageEvent;但要让它享受完整管线
(会话、typing、agent、TTS 回复),就必须合成一个"看起来像正常消息"的事件。

**实现**:入口来自 adapter 的 STT sink(`plugins/platforms/discord/adapter.py:4542-4546
@ 863e313`,转写完成后 `await self._voice_input_callback(guild_id=..., user_id=..., transcript=...)`)。
runner 侧流程:查 guild→文字频道映射 → 复用 join 时存的 source 字典重建 SessionSource
(保证语音输入与绑定文字会话**共享同一 session**)→ 授权检查 → 去重 → 把转写回显到
文字频道(带 @everyone/@here 消毒)→ 合成事件:

`gateway/run.py:19128-19142 @ 863e313`
```python
        # Build source — reuse the linked text channel's metadata when available
        # so voice input shares the same session as the bound text conversation.
        source_data = getattr(adapter, "_voice_sources", {}).get(guild_id)
        if source_data:
            source = SessionSource.from_dict(source_data)
            source.user_id = str(user_id)
            source.user_name = str(user_id)
        else:
            source = SessionSource(
                platform=Platform.DISCORD,
                chat_id=str(text_ch_id),
                user_id=str(user_id),
                user_name=str(user_id),
                chat_type="channel",
            )
```

合成事件用 SimpleNamespace 伪造 raw_message,让 `_get_guild_id` / `_send_voice_reply`
仍能拿到 guild_id;并解析绑定文字频道的 channel_prompt(引 #50149:语音输入此前拿不到
按频道注入的上下文提示,与打字消息行为不一致):

`gateway/run.py:19170-19189 @ 863e313`
```python
        from types import SimpleNamespace
        # Resolve the bound text channel's channel_prompt so voice input gets
        # the same per-channel context as typed messages (#50149).
        channel_prompt: Optional[str] = None
        resolver = getattr(adapter, "_resolve_channel_prompt", None)
        if callable(resolver):
            try:
                resolved = resolver(str(text_ch_id))
                channel_prompt = resolved if isinstance(resolved, str) else None
            except Exception:
                channel_prompt = None
        event = MessageEvent(
            source=source,
            text=transcript,
            message_type=MessageType.VOICE,
            raw_message=SimpleNamespace(guild_id=guild_id, guild=None),
            channel_prompt=channel_prompt,
        )

        await adapter.handle_message(event)
```

授权在回显**之前**做(19144-19156):未授权用户的语音既不回显也不进管线。

**重实现要点**:
- 合成事件而不是旁路管线:一切会话/打断/流式/TTS 逻辑天然复用,零特殊分支。
- source 要从 join 时的快照重建(session 归属),只覆盖 user 字段。
- 先授权后回显(不给未授权者制造可见副作用);回显文本消毒 @everyone/@here
  (19162,插入零宽空格)。
- raw_message 伪造成"最小可用"形状即可,但要写明哪些下游依赖它(guild_id)。
- 每个与打字消息共享的注入点(channel_prompt、session、mention 等)都要显式对齐,
  否则语音 lane 会悄悄退化(#50149 即此类)。

## 4. voice 回复判定 `_should_send_voice_reply`

**问题**:一次 turn 结束后"要不要由 runner 补一条 TTS 语音回复"是多方博弈:chat 级
/voice 模式、全局 auto_tts、agent 自己是否已调 TTS 工具、base adapter 是否已经处理、
流式是否已消费了文本。判定错了要么双份语音、要么没有语音。

**实现**:三层判定。第一层——模式开关(chat 显式模式优先,全局 auto_tts 仅作无显式
模式时的回退):

`gateway/run.py:19225-19232 @ 863e313`
```python
        should = (
            (voice_mode == "all")
            or (voice_mode == "voice_only" and is_voice_input)
            # ``voice.auto_tts`` is synced into the adapter on gateway startup.
            # It is the fallback only when the chat has no explicit mode;
            # otherwise the chat-level all/voice_only/off choice takes precedence.
            or (voice_mode is None and adapter_auto_tts)
        )
```

第二层——**本 turn 内** agent 是否已调过 `text_to_speech` 工具(从 agent_messages 尾部
找最后一条 user 消息,只扫描其后的 assistant tool_calls),防止 agent 已自主发声后
runner 再复读:

`gateway/run.py:19240-19255 @ 863e313`
```python
        # Dedup: agent already called TTS tool in THIS turn only
        last_user_idx = None
        for i, msg in enumerate(reversed(agent_messages)):
            if msg.get("role") == "user":
                last_user_idx = len(agent_messages) - 1 - i; break
        turn_messages = agent_messages[last_user_idx:] if last_user_idx is not None else agent_messages
        has_agent_tts = any(
            msg.get("role") == "assistant"
            and any(
                (tc.get("function") or {}).get("name") == "text_to_speech"
                for tc in (msg.get("tool_calls") or [])
            )
            for msg in turn_messages
        )
        if has_agent_tts:
            return False
```

第三层——语音输入 + base adapter auto-TTS 的分工:平时语音输入交给 base adapter 的
auto-TTS(它的 play_tts 在连着 VC 时会直接在语音频道播),runner 让位;**但当流式已经
把文本消费掉(already_sent=True)时,base adapter 收到的是 None、无文本可 TTS,runner
必须接管**(19257-19263;docstring 19198-19208 同述)。

调用点在 turn 收尾处,且还要先排除"流式 TTS 已完成"的情况(#60671,流式管线自身已
播过音频):`gateway/run.py:18130-18139 @ 863e313`
```python
            _stts_adapter = self._adapter_for_source(source)
            _streaming_tts_done = (
                _stts_adapter is not None
                and bool(getattr(_stts_adapter, "_streaming_tts_turn_completed", lambda *_a, **_k: False)(session_key, run_generation))
            )
            if (
                not _streaming_tts_done
                and self._should_send_voice_reply(event, response, agent_messages, already_sent=_already_sent)
            ):
                await self._send_voice_reply(event, response)
```

**重实现要点**:
- 语音去重要限定"本 turn":全历史扫描会因上一 turn 的 TTS 调用永久禁声。
- 显式 per-chat 模式 > 全局默认;None(从未设置)才落到全局。
- 多个可能发声的主体(agent 工具、base adapter auto-TTS、流式 TTS、runner 兜底)必须
  排出唯一责任人;`already_sent` 这类管线状态是分工判定的输入,不是噪音。
- 错误响应(`Error:` 前缀)不 TTS(19209-19210)。

## 5. voice 回复发送 `_send_voice_reply`

**问题**:TTS 产物的容器格式因平台而异(Telegram 等平台的原生语音气泡要求 Ogg/Opus,
其他平台 MP3 即可);且"发到哪"分两路:连着语音频道就地播放 vs 发语音文件消息。

**实现**:先 `_strip_markdown_for_tts(text[:4000])` 清掉 markdown 再合成;输出路径由
`build_auto_tts_output_path(platform)` 决定扩展名:

`gateway/run.py:19282-19291 @ 863e313`
```python
            # Platform-aware output path: platforms whose native voice
            # bubbles require Ogg/Opus (OPUS_VOICE_PLATFORMS — Telegram,
            # Matrix, Feishu, WhatsApp, Signal) get an explicit .ogg path;
            # the TTS tool's central container repair guarantees real
            # Ogg/Opus bytes for every provider. Others keep MP3.
            audio_path = build_auto_tts_output_path(event.source.platform)

            result_json = await asyncio.to_thread(
                text_to_speech_tool, text=tts_text, output_path=audio_path
            )
```

`build_auto_tts_output_path` 的设计理由(`gateway/platforms/base.py:164-180 @ 863e313`):
平台感知放在**调用方**而非 TTS 工具的 `HERMES_SESSION_PLATFORM` contextvar——因为该
contextvar 在 post-handler 阶段已被 `_clear_session_env` 清掉,靠它判平台永远得到 MP3
(#57049、#36685 的事故根因);`OPUS_VOICE_PLATFORMS = {"telegram","matrix","feishu",
"whatsapp","signal"}`(`tools/tts_tool.py:636-642 @ 863e313`)是单一权威。

投递两路:连 VC 则 `play_in_voice_channel`;否则 `send_voice`,并给 metadata 打
`notify=True`(镜像 base.py 最终文本路径,让 Telegram "important 模式" 下最终语音也
走正常推送而非静默消息;先 dict() 克隆防止污染共享 metadata):

`gateway/run.py:19307-19327 @ 863e313`
```python
            guild_id = self._get_guild_id(event)
            if (guild_id
                    and hasattr(adapter, "play_in_voice_channel")
                    and hasattr(adapter, "is_in_voice_channel")
                    and adapter.is_in_voice_channel(guild_id)):
                await adapter.play_in_voice_channel(guild_id, actual_path)
            elif adapter and hasattr(adapter, "send_voice"):
                reply_anchor = self._reply_anchor_for_event(event)
                thread_meta = self._thread_metadata_for_source(event.source, reply_anchor)
                # Mark the auto voice reply as notify-worthy. ...
                if thread_meta is not None:
                    thread_meta = dict(thread_meta)
                    thread_meta["notify"] = True
                else:
                    thread_meta = {"notify": True}
```

清理:`finally` 里对 `{audio_path, actual_path} - {None}` 逐个 unlink(19337-19342)——
注意 `actual_path` 可能因 opus 转换与请求路径不同(19298-19299),所以两个都删。

**重实现要点**:
- 平台→容器格式的映射要在还知道平台的地方决定,不要依赖可能已被清掉的 ambient 状态
  (#57049/#36685 的教训:contextvar 生命周期 ≠ 调用生命周期)。
- TTS 工具返回 JSON,`file_path` 以返回值为准(转换可能改名);success 与文件存在双验。
- 临时产物删除要覆盖"请求路径"和"实际路径"两个。
- 发送 metadata 修改前先克隆(并发共享)。

## 6. 流式后媒体投递 `_deliver_media_from_response`

**问题**:流式(streaming)模式下文本已边生成边发出,常规的 `_process_message_background`
后处理被跳过,响应里的 `MEDIA:` 附件标签(项目内约定:模型在回复里写
`MEDIA:/path/to/file` 表示"把这个文件发给用户")就永远不会投递。

**实现**:turn 收尾处,`already_sent 且未 failed` 时调用(`gateway/run.py:18152-18158
@ 863e313`)。核心取舍写在 docstring:**流式后补扫描是 EXPLICIT-ONLY**——与非流式路径
(base.py 会用 `extract_local_files` 自动探测裸本地路径)不同:

`gateway/run.py:19356-19364 @ 863e313`
```python
        Unlike the non-streaming path in ``gateway/platforms/base.py`` (which
        also auto-detects bare local paths via ``extract_local_files``), this
        post-stream rescan is EXPLICIT-ONLY. The visible reply has already
        been streamed verbatim, so a bare path string here was either (a)
        already shown to the user as text, or (b) stale tool/inspected
        content that was never part of the intended visible reply. Promoting
        such paths into uploads after the fact sent files the model never
        asked to deliver (#20834). Only ``MEDIA:`` directives — the explicit
        attachment contract — trigger post-stream uploads.
```

第二个反例修正:**不做跨 turn 去重**(#73771)——最终流式回复里的 MEDIA: 是模型
"有意附上"(包括用户要求重发),不能因历史发过就吞;陈旧的自动追加标签在上游
`_collect_auto_append_media_tags` 用 history_media_paths 去重:

`gateway/run.py:19380-19387 @ 863e313`
```python
            # Do NOT deduplicate explicit MEDIA tags against prior turns here
            # (#73771). This rescan is already EXPLICIT-ONLY (see docstring):
            # a MEDIA: directive in the final streamed reply is the model
            # deliberately attaching a file — including a user-requested
            # resend. Stale auto-appended tags are deduped upstream in
            # _collect_auto_append_media_tags with history_media_paths.
            # Mirrors the same filter removal on the non-streaming path in
            # gateway/platforms/base.py.
```

分发逻辑:先捕获 `[[as_document]]` 标记(在 extract_media 剥掉它之前,19370-19374)——
带此标记时图片扩展名文件也走 `send_document` 保原始字节(Telegram sendPhoto 会重压缩到
~1280px);否则图片聚成一批 `send_multiple_images`(利于 Signal 多附件 RPC),其余按
扩展名 + `should_send_media_as_audio`(`gateway/platforms/base.py:141-161 @ 863e313`,
Telegram 只在 is_voice=True 时把 opus/ogg 当语音气泡)三路分发 voice/video/document
(19426-19448),每个文件单独 try/except,单个失败不拖累其余。

**重实现要点**:
- 流式和非流式要各自有媒体投递终点,且明确两者规则差异(显式 vs 自动探测)并写下理由。
- "从文本里捡路径当附件"在文本已可见之后是危险操作(#20834:发出模型从未想发的文件)。
- 去重责任分层:自动追加层去重(防复读),显式指令层不去重(尊重意图,#73771)。
- 格式标记(`[[as_document]]`)要在剥离之前捕获;图片批量发送与逐个发送分路。
- 分发按 (扩展名, is_voice, 平台) 三元决定,平台差异(Telegram sendPhoto 压缩、
  sendVoice 只收 opus)集中到共享谓词。

## 7. 后台任务运行框架 `_run_background_task(+inner)`

**问题**:`/background <prompt>` 要在**不动当前会话历史**的前提下,独立跑一个完整
agent 会话并把结果送回原 chat。入口在
`gateway/slash_commands.py:3321-3332 @ 863e313`(`asyncio.create_task(self._run_background_task(...))`
fire-and-forget,任务加入 `self._background_tasks` 防 GC,done_callback 自摘除)。

**实现(外壳)**:多租户 profile 作用域包裹——与 `_run_agent` 同款模式:

`gateway/run.py:19471-19480 @ 863e313`
```python
        if not getattr(getattr(self, "config", None), "multiplex_profiles", False):
            return await self._run_background_task_inner(
                prompt, source, task_id, event_message_id, media_urls, media_types,
            )

        profile_home = self._resolve_profile_home_for_source(source)
        with _profile_runtime_scope(profile_home):
            return await self._run_background_task_inner(
                prompt, source, task_id, event_message_id, media_urls, media_types,
            )
```

**实现(inner)**:完整复刻主流程的运行时装配——`_resolve_session_agent_runtime`(模型
与凭据)、无 api_key 早退并回报、`_get_platform_tools`(平台工具集)、
`_resolve_session_reasoning_config` / `_resolve_session_service_tier` /
`_resolve_turn_agent_config`(逐 turn 路由)、vision 富化(把图片附件转描述,与主流程
同款,19536-19549)。然后在 executor 线程里建独立 AIAgent:

`gateway/run.py:19551-19591 @ 863e313`(节选)
```python
            def run_sync():
                agent = AIAgent(
                    model=turn_route["model"],
                    **turn_route["runtime"],
                    ...
                    session_id=task_id,
                    platform=platform_key,
                    ...
                    session_db=getattr(self._session_db, "_db", self._session_db),
                    # Reload from disk — do not reuse the startup snapshot (#60955).
                    fallback_model=self._refresh_fallback_model(),
                )
                try:
                    return agent.run_conversation(
                        user_message=enriched_prompt,
                        task_id=task_id,
                    )
                finally:
                    self._cleanup_agent_resources(agent)

            result = await self._run_in_executor_with_context(run_sync)
```

要点:`session_id=task_id`(形如 `bg_HHMMSS_xxxxxx`,slash_commands.py:3312)→ 全新
会话,不碰当前 chat 的 session;`fallback_model` 从磁盘重读而非启动快照(#60955:
用户改了 config 里的 fallback,后台任务仍用旧值);agent 用完必 `_cleanup_agent_resources`。

**结果投递**(19597-19686):抽 MEDIA / 图片,拼 `✅ Background task complete\nPrompt: "…"`
头部;文本、图片 URL、媒体文件(voice/video/image_file/document 四路,与流式/看板路径
镜像,19632-19634 注释)逐类发送;空响应也要发"(No response generated)";顶层异常兜底
发 `❌ Background task {task_id} failed: {e}`(19677-19686)。所有 send 都带
`_thread_metadata_for_source(source, event_message_id)`,结果回到发起时的线程/topic。

**重实现要点**:
- 后台任务 = 新 session_id + 完整运行时装配复刻,而不是复用主 agent 对象;凭据、
  工具集、reasoning、profile 逐项对齐主流程,否则后台行为与前台漂移。
- 结果投递必须"总有回音":成功、空响应、异常三态都各有消息;头部带 prompt 预览
  让用户对得上号。
- 运行时快照(fallback_model 之类)要明确"启动时读"还是"每次读",跨 turn 的配置
  热更新只有后者能生效(#60955)。
- fire-and-forget 任务要强引用集合 + done_callback 摘除,防 asyncio 弱引用 GC。

## 8. Telegram topic 能力探测 / System topic / setup 截图 / 标题清洗

**问题**:Telegram 私聊多话题(Bot API 的 DM topics,多会话并行)需要 BotFather 端开启
Threads Settings;gateway 要能探测能力、引导用户开启、并在激活后建一个管理用 System topic。

**实现**:
- `_get_telegram_topic_capabilities`(19694-19720):调 Bot API `getMe`,`_field` 帮助函数
  兼容三种承载(对象属性 / `api_kwargs` dict / 纯 dict),返回
  `has_topics_enabled` / `allows_users_to_create_topics`;探测失败返回 `{"checked": False}`
  (三态:查过且有值 / 查过为 None / 没查成)。
- `_ensure_telegram_system_topic`(19722-19761):激活后走
  `adapter._create_dm_topic(chat_id, "System")` → 发介绍消息 → `pin_chat_message`
  置顶(disable_notification=True);三步每步失败都 debug 级日志静默降级,后一步依赖
  前一步产物(thread_id、message_id)缺失即 return。
- `_send_telegram_topic_setup_image`(19763-19779):发内置截图
  `gateway/assets/telegram-botfather-threads-settings.jpg`,指导用户在 BotFather 里开
  Threads Settings;文件不存在直接 return(可裁剪的资产)。
- `_sanitize_telegram_topic_title`(19781-19790):压空白、空则 "Hermes Chat"、超 120
  截到 117+"...":

`gateway/run.py:19783-19790 @ 863e313`
```python
        cleaned = re.sub(r"\s+", " ", str(title or "")).strip()
        if not cleaned:
            return "Hermes Chat"
        # Telegram forum topic names are short (currently 1-128 chars). Keep
        # extra room for multi-byte titles and avoid trailing ellipsis churn.
        if len(cleaned) > 120:
            cleaned = cleaned[:117].rstrip() + "..."
        return cleaned
```

**重实现要点**:
- 平台能力探测返回三态而非 bool,让调用方能区分"没开"与"探测不了"。
- 引导性 UI(截图、System topic)全部 best-effort,失败静默降级不阻塞主流程。
- 平台字段访问要兼容库版本差异(属性 / api_kwargs / dict 三形态)。
- 标题长度限制留余量(120<128),避免贴边导致多字节/后续追加溢出。

## 9. Discord auto-thread 与 relay lane 判定

**问题**:Hermes 可把频道里的对话自动开成 Discord thread(子线程),随后要用自动生成的
会话标题给 thread 语义化改名。但"这是不是我们刚自动建的 thread"在两条通路上判据完全
不同:原生 Discord 连接 vs 经上游 relay 连接器(connector)转发。

**实现**:三个判定器。

原生 lane——事件**已经发生在**自动建的 thread 里(第 2+ turn),靠 adapter ingest 时
盖的标记:

`gateway/run.py:19792-19800 @ 863e313`
```python
    def _is_discord_auto_thread_lane(self, source: SessionSource) -> bool:
        """Return True only for Discord threads Hermes just auto-created."""
        return (
            source.platform == Platform.DISCORD
            and source.chat_type == "thread"
            and bool(getattr(source, "auto_thread_created", False))
            and bool(source.thread_id)
            and bool(getattr(source, "auto_thread_initial_name", None))
        )
```

标记来源:原生 adapter `plugins/platforms/discord/adapter.py:7869-7871 @ 863e313`
(ingest 时 `auto_thread_created=auto_threaded_channel is not None` 等),relay 通路
`gateway/relay/ws_transport.py:224-225 @ 863e313`(从 connector 的 inbound 字段读)。

relay-频道 lane——**shape-only**(只看形状):relay 转发的 Discord 频道事件、connector
"可能"会把我们的回复自动开 thread;注册期(投递前)不能查 send-result 缓存,因为反馈
还不存在:

`gateway/run.py:19802-19815 @ 863e313`
```python
    def _is_relay_discord_channel_lane(self, source: SessionSource) -> bool:
        """Shape-only check: a relay-delivered Discord CHANNEL event whose
        reply the connector MAY auto-thread (title-turn registration gate).

        Deliberately does NOT consult the send-result cache: at registration
        time (before delivery) the feedback can't exist yet. The rename lane
        polls the cache at fire time instead."""
        return (
            source.platform == Platform.DISCORD
            and bool(source.chat_id)
            and not source.thread_id
            and source.chat_type in ("group", "channel")
            and getattr(source, "delivered_via_upstream_relay", False) is True
        )
```

`_relay_auto_thread_info`(19817-19869)解决**标题 turn**(第 1 个来回)的根本困境:
自动标题在首次交互就触发,而那时事件 source 还是父频道事件(thread 尚不存在,无标记
可盖),原生判定永远不命中(docstring 内 staging repro 2026-07-29:初始标题正常、语义
改名从不发生)。两级来源:优先 connector 在 inbound 上盖的 `prospective_thread_id`
(= 锚消息 id = 它将要自动建的 thread id,**确定且逐消息**——相对地,send-result 缓存
每父频道只有一个槽位,同频道多个 auto-thread 时只有第一个能改名,staging repro
2026-08-02);回退到 `adapter.auto_thread_info_for_chat(chat_id)` 读 relay adapter 的
send-result 缓存(`gateway/relay/adapter.py:1002-1008 @ 863e313`),兼容不盖
prospective_thread_id 的旧 connector:

`gateway/run.py:19846-19854 @ 863e313`
```python
        if source.platform != Platform.DISCORD or not source.chat_id:
            return None
        if not getattr(source, "delivered_via_upstream_relay", False):
            return None
        prospective = getattr(source, "prospective_thread_id", None)
        if prospective:
            # Deterministic per-thread identity; the empty initial-name marker
            # signals the caller to rely on the connector-side no-clobber guard.
            return (str(prospective), "")
```

**重实现要点**:
- 同一功能在直连/中继两条通路上的"身份判据"要分别设计:直连靠 ingest 标记,中继靠
  connector 反馈;标题 turn(资源尚未创建)是第三种时序,需要 prospective id 这类
  "预告身份"。
- 判定分两阶段:注册期用 shape-only 宽判(不依赖尚不存在的反馈),执行期查实。
- 每消息确定性 id 优于每 chat 单槽缓存(并发多 thread 场景,2026-08-02 repro)。
- 返回值里用空 initial_name 作为"改用 connector 侧守卫"的信号,避免再传布尔。

## 10. Discord 语义化改名调度与执行

**问题**:自动会话标题生成在**后台线程**完成,要把"改 thread 名"这件事安全地送回事件
循环,并在两条 lane 上分别处理"不许覆盖人工改名"(no-clobber)与租户路由。

**实现**:标题回调注册在 turn 收尾(`gateway/run.py:5690-5702 @ 863e313`):Telegram
topic lane 注册 `_schedule_telegram_topic_title_rename`,Discord 两 lane(原生标记 lane
或 relay shape lane)注册 `_schedule_discord_semantic_thread_rename`。5697-5702 的注释
记录了第三次 staging repro(2026-07-31):**注册期若按缓存读结果做门禁,则永远不注册**
——所以注册按 shape 宽判、执行期再查实。

调度器(20\75-20025):后台线程 → `asyncio.get_running_loop()` 失败则退回
`self._gateway_loop` → `dataclasses.replace(source)` 拷贝(防跨线程共享可变 source)→
`safe_schedule_threadsafe`(`agent/async_utils.py:34-68 @ 863e313`:包装
`run_coroutine_threadsafe`,失败时 close 协程防 "never awaited" 泄漏、返回 None)→
future 加 done_callback 记录失败。

执行器 `_rename_discord_auto_thread_for_session_title`(19885-19973):relay_info 为 None
且非原生 lane 时,对 relay shape lane 做**有界轮询**等 connector 反馈(标题线程与产生
send-result 的投递赛跑):

`gateway/run.py:19908-19918 @ 863e313`
```python
            if not self._is_relay_discord_channel_lane(source):
                return
            for _ in range(20):  # up to ~10s
                relay_info = self._relay_auto_thread_info(source)
                if relay_info is not None:
                    break
                await asyncio.sleep(0.5)
            if relay_info is None:
                # True miss: the connector did not auto-thread this reply
                # (policy off, DM, already-threaded, or send failed).
                return
```

no-clobber 守卫分 lane:relay lane 让 **connector 用它自己的 created-name 记忆**执行
守卫(gateway 无法逐字节复现初始名——正规化漂移曾让所有 relay 改名被静默拒绝);原生
lane 保留旧的字符串守卫 `only_if_current_name=auto_thread_initial_name`。另外 relay lane
必须传父频道 id:connector 出口守卫的租户判别缓存按**父频道 chat_id** 键控,而
rename_thread 默认 chat_id=thread id,查不到就拒绝("target not routed to an onboarded
tenant",staging 2026-08-01 的真实故障):

`gateway/run.py:19959-19966 @ 863e313`
```python
        try:
            renamed = await rename_thread(
                target_thread_id,
                thread_name,
                prefer_connector_created=use_connector_guard,
                only_if_current_name=guard_name,
                parent_chat_id=parent_chat_id,
            )
```

relay 侧实现:`gateway/relay/adapter.py:2085-2093 @ 863e313`(签名含
`prefer_connector_created` / `parent_chat_id`,发 `thread_rename` op,
`only_if_connector_created` 走 connector 记忆守卫)。

标题清洗 `_sanitize_discord_thread_title`(19871-19883):Discord thread 名上限 100 个
**UTF-16 码元**(emoji 计双),所以用 `utf16_len`/`_prefix_within_utf16_limit`
(`gateway/platforms/base.py:190-209 @ 863e313`)截到 80/77+"...",不用 Python 码点切片。

**▲ 文档-代码冲突/缺陷候选(本段最重要的一条)**:run.py:19960-19965 对
`rename_thread` **无条件**传 `prefer_connector_created=` 与 `parent_chat_id=` 两个
关键字参数;relay adapter 签名接受它们,但**原生 Discord 插件 adapter 的签名不接受**:

`plugins/platforms/discord/adapter.py:6866-6872 @ 863e313`
```python
    async def rename_thread(
        self,
        thread_id: str,
        name: str,
        *,
        only_if_current_name: Optional[str] = None,
    ) -> bool:
```

原生 lane(use_connector_guard=False)调用时这两个 kwarg 仍会传入 → 调用点立即抛
TypeError(async 函数坏 kwarg 在调用时同步抛),被 19972-19973 的
`except Exception: logger.debug(...)` 静默吞掉——即**基线上原生 lane 的语义化改名
大概率是静默 no-op**。测试只用宽签名的 fake 覆盖了 relay lane
(`tests/gateway/relay/test_relay_threads.py:386-389 @ 863e313`),原生插件 adapter 的真实
签名未被该路径测试。run.py:19930 注释"Native-marker lane keeps the legacy string guard"
描述的意图与实际(TypeError)不符。待 R8+ 用测试验证定案。

**重实现要点**:
- 后台线程回事件循环:loop 兜底(_gateway_loop)、source 深拷贝、协程调度失败要
  close(泄漏三件套)。
- "赛跑的反馈"用有界轮询,并区分"还没到"与"真没有"(轮询超时 = 真 miss)。
- no-clobber 守卫放在拥有权威记忆的一侧(connector),不要跨系统逐字节比对字符串。
- 出口守卫的鉴权缓存按什么键控,调用方必须知道并配合传参(父频道 id)。
- 对多态 adapter 方法传扩展 kwargs 前,确认所有实现签名兼容(或加 **kwargs 契约),
  且不要让 `except Exception` 把 TypeError 这类编程错误当运行时噪音吞掉。

## 11. Telegram topic 语义化改名

**问题**:同款"自动标题→改名",但对象是 Telegram DM topic,且多了三层"不该改"的
判定:操作员全局禁用、操作员声明的固定 topic、topic 已绑到别的 session。

**实现**:`_rename_telegram_topic_for_session_title`(20027-20110)串四道闸:
1. lane 判定 `_is_telegram_topic_lane`(`gateway/run.py:6745-6754 @ 863e313`:TELEGRAM
   + chat_type=="dm" + topic mode 开 + thread_id 非 general);
2. 操作员开关 `_telegram_topic_auto_rename_disabled`(20112-20133,配置
   `gateway.platforms.telegram.extra.disable_topic_auto_rename`,bool/字符串
   `"1"/"true"/"yes"/"on"` 都认);用途注释:用户自管 topic(ad-hoc Threaded Mode)时
   自动改名会反复覆盖用户起的名(20038-20040);
3. 操作员声明 topic(extra.dm_topics)不改——**在类上取 `_get_dm_topic_info` 而非实例**,
   因为 MagicMock 的 getattr 会自动造属性,实例级 hasattr 对一切测试替身都是 True;
   且只有 dict 形返回才算操作员声明:

`gateway/run.py:20052-20063 @ 863e313`
```python
        adapter = self._adapter_for_source(source)
        if adapter is not None:
            get_info = getattr(type(adapter), "_get_dm_topic_info", None)
            if callable(get_info):
                try:
                    operator_topic = get_info(adapter, str(source.chat_id), str(source.thread_id))
                except Exception:
                    operator_topic = None
                # Only treat dict-shaped returns as operator-declared; a
                # bare MagicMock or other sentinel shouldn't count.
                if isinstance(operator_topic, dict):
                    return
```

4. session 绑定校验(20065-20076):topic 当前绑定的 session_id ≠ 本次标题所属 session
   则不改(标题属于旧会话,防串写);查询失败也放弃(fail-closed)。

执行:优先 adapter 封装 `rename_dm_topic`;否则直接摸 bot 的
`edit_forum_topic`/`editForumTopic`(snake/camel 双探测,int 转型失败再退回原始字符串,
20091-20108)——兼容多版本 python-telegram-bot。

调度器 `_schedule_telegram_topic_title_rename`(20135-20170)与 Discord 版同构
(loop 兜底、source 拷贝、safe_schedule_threadsafe、done_callback)。

**重实现要点**:
- "自动改名"类功能的默认答案应当是"多一层理由就不改":显式开关 > 操作员声明 >
  归属校验,全部 fail-closed。
- 测试替身(MagicMock)友好性是真实设计输入:在类上解析方法 + 只认形状正确的返回值,
  两处一致(20049-20051 与 `_is_telegram_dm_topic_target` 20749-20752 互为镜像)。
- 第三方库 API 兼容:方法名双拼、参数类型双试。

## 12. Telegram capability hint / help / off / root status / restore

- `_should_send_telegram_capability_hint`(20174-20191):BotFather 截图上传限频,
  per-chat monotonic 时间戳,冷却 300s(`_TELEGRAM_CAPABILITY_HINT_COOLDOWN_S = 300.0`,
  20172)。同构的 lobby 提醒限频在 6758-6776(冷却 30s)。
- `_telegram_topic_help_text`(20193-20213):/topic 帮助文案,五步说明多会话模式
  (root DM 变 system lobby、/new 只重置当前 topic、/topic <id> 恢复旧会话)。
- `_disable_telegram_topic_mode_for_chat`(20215-20249):/topic off。先查
  `is_telegram_topic_mode_enabled`(未启用则幂等提示),再
  `disable_telegram_topic_mode`;成功后**重置两个 debounce 字典**防止下次激活看到陈旧
  冷却(20238-20243);回复明确说明"Telegram 里已有 topics 不会被删,只是不再按独立
  会话门控"。
- `_telegram_topic_root_status_message`(20252-20296):root lobby 状态页——列最多 10 个
  未链接(unlinked)的历史会话(id+标题+预览),并给出可直接照抄的恢复示例
  `/topic {sessions[0].id}`;查询失败静默按空列表处理。
- `_restore_telegram_topic_session`(20298-20350):`/topic <id>` 把旧会话装进当前 topic。
  校验链:resolve_session_id(支持前缀)→ 存在性 → `source=="telegram"` → 属主
  user_id 匹配 → 未被链接到其他 topic(或已链接到本 topic,幂等):

`gateway/run.py:20313-20335 @ 863e313`(节选)
```python
        linked = await self._session_db.is_telegram_session_linked_to_topic(session_id=session_id)
        current_binding = await self._session_db.get_telegram_topic_binding(
            chat_id=str(source.chat_id),
            thread_id=str(source.thread_id),
        )
        if linked:
            if not current_binding or current_binding.get("session_id") != session_id:
                return "That session is already linked to another Telegram topic."
        ...
        try:
            await self._session_db.bind_telegram_topic(
                ..., managed_mode="restored",
            )
        except ValueError as exc:
            if "already linked" in str(exc):
                return "That session is already linked to another Telegram topic."
            raise
```

绑定后回显标题 + 最后一条 assistant 消息(从 get_messages 倒扫,20338-20345),给用户
"接上了哪段对话"的即时确认。

**重实现要点**:
- 恢复类命令的校验链:存在 → 类型 → 属主 → 排他绑定;应用层先查 + DB 层约束兜底
  (ValueError "already linked" 双保险,竞态安全)。
- 所有提示类消息按 chat 限频;禁用功能时连同限频状态一起复位。
- 状态页给"可直接复制执行"的示例命令,而非抽象说明。

## 13. `_execute_mcp_reload`

**问题**:/reload-mcp 要断开并重连所有 MCP(Model Context Protocol,外部工具服务器
协议)server,并让**已存在的会话**在下一 turn 就看到新工具——此前用户只能 /new
(丢历史)才能拿到新工具。

**实现**:diff 三集合(before/after 的 server 名,锁内快照),shutdown 与 discover 都
丢进默认 executor 防塞事件循环(20365-20386);然后遍历 agent 缓存原地刷新工具:

`gateway/run.py:20406-20428 @ 863e313`(节选)
```python
            try:
                from tools.mcp_tool import refresh_agent_mcp_tools
                _cache = getattr(self, "_agent_cache", None)
                _cache_lock = getattr(self, "_agent_cache_lock", None)
                if _cache_lock is not None and _cache:
                    with _cache_lock:
                        for _sess_key, _entry in list(_cache.items()):
                            ...
                            # Preserve each cached agent's build-time toolset
                            # selection EXACTLY: a gateway session built with a
                            # restricted enabled_toolsets (e.g. ["safe"]) must
                            # NOT silently gain tools after a reload. This is the
                            # opposite of the interactive CLI/TUI /reload-mcp,
                            # which is a single user re-applying their own config
                            # edit; gateway agents are per-session and may be
                            # deliberately locked down. (Contract is asserted by
                            # test_reload_mcp_preserves_per_agent_toolset_overrides.)
                            refresh_agent_mcp_tools(_agent, quiet_mode=True)
```

安全语义:gateway 会话刷新**严格保留各 agent 构建时的 toolset 选择**(锁死的会话不能
因 reload 悄悄扩权)——与 CLI/TUI 的 /reload-mcp 语义刻意相反(单用户重应用自己的配置)。
契约由 `test_reload_mcp_preserves_per_agent_toolset_overrides` 断言(LT 行为规格)。

最后向会话转写**尾部追加**一条 user 角色的变更通告,保住前缀的 prompt cache:

`gateway/run.py:20435-20450 @ 863e313`(节选)
```python
            # Inject a message at the END of the session history so the
            # model knows tools changed on its next turn.  Appended after
            # all existing messages to preserve prompt-cache for the prefix.
            ...
            reload_msg = {
                "role": "user",
                "content": f"[IMPORTANT: MCP servers have been reloaded. {change_detail}{tool_summary}. The tool list for this conversation has been updated accordingly.]",
            }
```

缓存失效的成本已在上游确认过(20402-20405 注释:用户经 slash-confirm 门同意)。
调用方:`gateway/slash_commands.py:5205-5240 @ 863e313`(`_handle_reload_mcp_command`,
gate key `approvals.mcp_reload_confirm`,confirm 后调 `_execute_mcp_reload`)。

**重实现要点**:
- 热重载三件事:重连、给活跃 agent 原地换工具表、给模型一条"工具变了"的历史通告。
- 通告追加在历史尾部(prompt cache 前缀不动),用 user 角色(assistant 伪造历史会
  污染模型自我认知)。
- 刷新工具时的权限不变量:reload 不得使受限会话扩权;并写测试锁死该契约。
- 阻塞型 IO(server 连接)全部下线程;before/after 集合 diff 在锁内取快照。

## 14. 破坏性 slash 确认原语

**问题**:/new /reset /undo(销毁对话)与 /reload-mcp(炸 prompt cache)这类命令需要
"确认一次 / 永久放行 / 取消"三选一的确认交互,且要同时支持按钮平台与纯文本平台。

**实现**:注释块(20467-20481)描述双通道:按钮 UI(Telegram/Discord/Slack/Matrix/
Feishu 覆写 `send_slash_confirm`,点击回 `tools.slash_confirm.resolve(session_key,
confirm_id, choice)`)与文本回退(/approve、/always、/cancel,由 `_handle_message`
的早期拦截匹配 `get_pending()`)。

`_maybe_confirm_destructive_slash`(20483-20593):gate key
`approvals.destructive_slash_confirm`(默认 True)每次**从磁盘 fresh 读**(20509-20516,
让"Always"点击后无需重启即生效);关着直接 `await execute()`。`_on_confirm` 的
"always" 分支要点:`save_config_value` **自吞错误、以返回值报告结果**,所以必须检查
返回值而不是 try 是否抛;持久化失败时动作照跑,但明确告知"偏好没存上,下次还会问":

`gateway/run.py:20528-20546 @ 863e313`(节选)
```python
                try:
                    from cli import save_config_value
                    # save_config_value swallows its own errors and reports the
                    # outcome in the return value, so the try block alone says
                    # nothing about whether the write landed.
                    persisted = bool(
                        save_config_value("approvals.destructive_slash_confirm", False)
                    )
                    if persisted:
                        logger.info(...)
                    else:
                        logger.warning(
                            "Could not persist destructive_slash_confirm=false "
                            "(session=%s); config.yaml is not writable",
                            session_key,
                        )
```

结果为字符串才追加 note;EphemeralReply 等结构化回复不动(20570-20574)。

`_request_slash_confirm`(20595-20661):生成 confirm_id(计数器,裸 runner 测试替身
无 `_slash_confirm_counter` 时惰性建,20624-20628);**先 register 再发送**,防超快
点击与 send 返回赛跑:

`gateway/run.py:20631-20633 @ 863e313`
```python
        # Register the pending confirm FIRST so a super-fast button click
        # cannot race the send_slash_confirm return.
        _slash_confirm_mod.register(session_key, confirm_id, command, handler)
```

按钮成功 → 返回 None(按钮自解释,不发冗余文本);失败/无按钮 → 返回 prompt 文本本身
作为回复(20657-20661)。

**存储与解析**(`tools/slash_confirm.py @ 863e313`):模块级 `_pending` dict + RLock,
按 session_key 键控(新确认覆盖旧的,`register` docstring 51-62);`resolve`(99-140)
校验 confirm_id 匹配(防被更新的 prompt 顶掉后旧按钮误触)、**先 pop 再跑 handler**
(防双击二次执行)、超时 300s 拒绝。文本回退拦截在
`gateway/run.py:14655-14694 @ 863e313`:工具级危险命令审批(tools/approval)**优先**于
slash-confirm(同一个 /approve 词,先解锁阻塞中的工具线程);接受 `!` 前缀变体(Slack
线程里 `/` 被平台吞);不认识的回复不消费、落到正常分发,并 `clear_if_stale` 清陈旧
确认(用户显然已经翻篇)。

调用方:/new(`gateway/run.py:15066 @ 863e313`)、/reset|/clear(15260)、
/reload-mcp(slash_commands.py:5233)、昂贵模型切换警告(slash_commands.py:2433,
复用 `_request_slash_confirm` 但无 "always" 持久化——"每次昂贵切换都该显式决定")。

**重实现要点**:
- 确认状态放模块级 store(adapter 无需 runner 反向引用即可 resolve);register 先于
  send(竞态);resolve 先 pop 后执行(幂等);confirm_id 防陈旧按钮。
- 同一确认词汇被多个子系统使用时要定义优先级(工具审批 > slash 确认)。
- "永久放行"的持久化结果必须如实反馈;写失败 ≠ 拒绝执行,但要说清楚。
- 按钮成功时抑制文本 ack;文本回退时 prompt 即 ack——一条消息不重复出现两次。
- gate 每次从磁盘读(`_read_user_config`,20663-20674:`load_config()` 失败返回 {},
  即 fail-open 到"需要确认"一侧,因为 `approvals.get(..., True)` 默认 True)。

## 15-17. `_read_user_config` / thread metadata / reply anchor

`_read_user_config`(20663-20674):对 `hermes_cli.config.load_config` 的薄封装,异常
返回 `{}`;供 slash-confirm gate 每次读盘。

`_thread_metadata_for_source`(20676-20694):从 source 提取
(platform, chat_id, thread_id, chat_type, reply_to) 调 `_thread_metadata_for_target`;
Slack 额外注入 `slack_team_id`(scope_id,多 workspace 路由)。

`_thread_metadata_for_target`(20696-20730):**合成发送**(goal 续跑、状态通知等只有
路由状态、没有事件对象的发送)所需 metadata 的唯一构造点。thread_id 为 None 直接
None;Telegram DM topic 目标要加双字段:

`gateway/run.py:20717-20729 @ 863e313`
```python
            metadata["telegram_dm_topic_reply_fallback"] = True
            # Telegram DM topic lanes need direct_messages_topic_id in metadata
            # so synthetic/queued messages (goal continuations, status notices)
            # route to the correct topic even when reply anchor is unavailable.
            tid = str(thread_id)
            if tid and tid not in {"", "1"}:
                metadata["direct_messages_topic_id"] = tid
            if reply_to_message_id is not None:
                metadata["telegram_reply_to_message_id"] = str(reply_to_message_id)
        if platform == Platform.SLACK and reply_to_message_id is not None:
            # Slack's reply_in_thread=false path uses message_id to distinguish
            # real existing threads from synthetic top-level session keys.
            metadata["message_id"] = str(reply_to_message_id)
```

`_is_telegram_dm_topic_target`(20732-20762):chat_type=="dm" 直接 True;否则查
adapter 的操作员声明 topic 表——同样"在类上解析方法 + 只认 dict 返回"的 MagicMock
防御(20745-20752 注释,镜像 §11 的守卫)。

`_reply_anchor_for_event`(20764-20767):staticmethod,纯转发到模块级
`gateway/platforms/base.py:106-138 @ 863e313`。后者的平台规则:Slack 的
`_hermes_no_thread_response` 合成事件返回 None(reaction 手递到目标频道要发顶层消息,
带 reply_to 会被 `_resolve_thread_ts` 当线程锚);Telegram DM topic 回复触发消息本身
(回复早先的 topic seed 会渲染到 lane 外);Telegram 群组 forum topic 返回 None
(按 topic metadata 路由,不用 reply);Feishu 有 reply_to_message_id 用之;默认
`event.message_id`。

**重实现要点**:
- "回到哪个线程/topic"的知识只写一处(单一构造点),事件路径与合成路径共用。
- reply anchor 与 thread metadata 是两个正交概念:前者是"回复哪条消息",后者是
  "投进哪条 lane";平台对两者的解释各不相同,规则要按平台枚举并注明反例。
- 测试替身防御(类上取方法 + 形状校验)在所有 adapter 内省点保持一致。

## 18-19. `/update` 平台白名单与 update 通知 watcher

**白名单**(20778-20789):`_UPDATE_ALLOWED_PLATFORMS` frozenset 列出允许 /update 的
内置消息平台;ACP/API server/webhook 等编程接口不许触发系统更新;插件化平台(discord、
mattermost 等)不在此集合——它们在 PlatformEntry 上声明 `allow_update_command=True`,
由 `_handle_update_command` 的 registry 回退承认(20780-20783 注释)。

**问题**:`hermes update --gateway` 是**脱离 gateway 进程**跑的(更新会重启 gateway
自身),进度、交互式提问、退出码只能靠 `_hermes_home` 下的标记文件传递:
`.update_pending.json`(发起方路由信息)/ `.update_output.txt`(累计输出)/
`.update_prompt.json`(更新进程要问用户)/ `.update_response`(用户答复)/
`.update_exit_code`(结果)。

**实现**:`_schedule_update_notification_watch`(20793-20804)单飞(已有未完成 task 就
不再起)。`_watch_update_progress`(20806-21050)主循环(poll 2s、流式聚合 4s、超时
30min):
- 从 claimed/pending 文件解析回发目标(platform/chat_id/thread_id/session_key,旧文件
  无 session_key 时拼 `f"{platform}:{chat_id}"` 兜底,20834-20858);
- 解析不到 adapter → 降级为"只等完成"模式,且**持续重试直到 `_send_update_notification`
  真正投递成功**(平台可能几秒后才重连上;只查一次会永远错过通知,20863-20878 注释);
- 增量流式:按 `bytes_sent` 偏移读新内容 → strip ANSI → 3500 字/块包 ``` 代码围栏发送
  (20884-20911);
- 交互提问转发:`.update_prompt.json` 出现且本会话无未答提问时,先 flush 缓冲(让用户
  看到上下文)、优先平台原生按钮 `send_update_prompt`(在**类**上探测,20993)、退回
  文本("Reply /approve (yes) or /deny (no), or type your answer directly");然后置
  `update_prompt_pending=True` 抑制同进程重复转发,但**提问文件留在盘上**——gateway
  若中途重启,下一个 watcher 能从盘恢复再转发(21016-21023 注释);
- 用户答复的回填在 `_handle_message` 拦截(`gateway/run.py:14513-14561 @ 863e313`):
  /approve→"y"、/deny→"n"、其他文本原样;**已注册 slash 命令绕过拦截**并写空答复让
  更新进程按默认值继续(否则 /new /help 会被吞成更新答案、或更新进程阻塞到 30 分钟
  超时,14518-14520 与 14562-14568 注释);写入用 tmp+replace 原子替换;
- 完成:flush 余量 → 按 exit code 发 ✅/❌ → 删全部标记文件 → 清 pending 标志
  (20913-20955);超时:写 `exit_code=124` 伪码、发超时消息、同样清理(21031-21050)。

`_send_update_notification`(21052-21169)是无流式的 legacy 完成通知(watcher 解析不到
adapter 时的回退 / 启动时检查)。关键正确性细节:
- **claim 语义**:`pending_path.replace(claimed_path)` 原子改名防多方重复消费
  (21073-21078);
- 更新还没完成(无 exit_code)→ 改名**还回** pending、返回 False 让调用方重试
  (21089-21094);
- adapter 未重连 → 同样还回并保留标记,绝不删——否则用户永远不知道更新结果:

`gateway/run.py:21108-21124 @ 863e313`(节选)
```python
            if not adapter and chat_id:
                # The update finished, but the target platform has not
                # reconnected yet (common right after the restart that
                # `hermes update` triggers). Treating "adapter missing" as a
                # definitive skip would delete the markers and silently lose the
                # completion notification ... Preserve the markers instead so
                # a later retry (the watcher poll loop, or the next gateway
                # startup) can deliver the result once the adapter is back.
                logger.info(...)
                cleanup = False
                active_pending_path = pending_path
                claimed_path.replace(pending_path)
                return False
```

- 输出超 3500 字取**尾部**(结论在尾部,21139-21140);
- 所有 Discord 发送包 `_non_conversational_metadata`(`gateway/run.py:452-462 @ 863e313`:
  仅对 discord 平台加 `non_conversational=True`,生命周期消息不当对话处理)。

启动接线:`gateway/run.py:11396-11404 @ 863e313`(启动先试一次
`_send_update_notification`;没送成且标记仍在 → `_schedule_update_notification_watch`)。

**重实现要点**:
- 跨进程 + 跨重启的进度/交互协议用文件系统:pending(路由)/output(append 流)/
  prompt(问)/response(答)/exit_code(果);消费用 rename-claim 原子化。
- "投递失败"与"无需投递"必须区分:前者保留标记重试(平台重连窗口),后者才清理。
- 提问转发的幂等靠进程内 pending 标志,崩溃恢复靠盘上文件不删——两层各管一种故障。
- 用户输入通道被临时征用时,必须给已注册命令留逃生门,且要解除对端进程的阻塞
  (写默认答复),不能只是本端绕过。
- 输出截断取尾;ANSI 必须剥;超时也要给对端伪造 exit code 完成收尾。

## 20-21. restart 通知与 home channel 启动通知

`_send_restart_notification`(21171-21248):/restart 发起 chat 的"回来了"回执。读
`.restart_notify.json` → `resolve_delivery_transport`(`gateway/delivery.py:92 @ 863e313`,
统一原生 adapter 与 relay 通路)→ 尊重平台级开关 `gateway_restart_notification`
(21197-21203)→ relay 通路补 `user_id`/`scope_id` 判别字段(21213-21218)。发送后**必须
检查 SendResult**:

`gateway/run.py:21225-21236 @ 863e313`
```python
            # adapter.send() catches provider errors (e.g. "Chat not found")
            # and returns SendResult(success=False) rather than raising, so
            # we must inspect the result before claiming success — otherwise
            # the log line is misleading and hides real delivery failures.
            if result is not None and getattr(result, "success", True) is False:
                logger.warning(
                    "Restart notification to %s:%s was not delivered: %s",
                    platform_str,
                    chat_id,
                    getattr(result, "error", "send returned success=False"),
                )
                return None
```

返回投递目标三元组 `(platform, chat_id, thread_id)` 供启动流程去重;`finally` 无条件
unlink 标记(一次性,不像 update 标记要重试——restart 回执丢了损失可接受)。

`_send_home_channel_startup_notifications`(21250-21331):向各平台配置的 home channel
广播"gateway online"。`skip_targets` 参数避免与更精确的 restart 回执重复砸同一 chat;
逐平台:无 home 配置跳过、无 transport 跳过、平台开关关着跳过、目标已发过跳过;relay
通路补 user_id/scope_id;同样检查 SendResult 才计入 delivered 集合;单平台异常不影响
其他平台(21323-21329)。调用方(`gateway/run.py:11424-11434 @ 863e313`)只在
**非 chat 发起的计划内重启**(终端/SIGUSR1/service)才广播——chat 发起的 /restart 已有
精确回执,不该再泄漏到 home channel;发送前对所有平台统一 sleep 1s 等 adapter 稳定
(11406-11410,Discord 重连后立刻发线程消息易失败)。

**重实现要点**:
- 生命周期通知分两级:精确回执(发起 chat)与广播(home channel),用 skip 集合防重。
- send 返回错误对象而非抛异常的 API,调用方必须显式验 success,否则日志撒谎。
- 每平台一个开关(`gateway_restart_notification`);relay 目标要带租户判别字段。
- 一次性标记(restart)与需重试标记(update)清理策略不同,取决于丢失代价。

## 22. `_set_session_env` / `_clear_session_env` 与 session_context 的关系(重点)

**问题**:工具层(shell 工具、消息工具、TTS……)需要知道"当前这条消息来自哪个
platform/chat/user/session"。老办法塞 `os.environ` 在并发 gateway 下是灾难:两条并发
消息互相覆盖对方的会话标识,工具把结果发错 chat。

**实现**:`contextvars.ContextVar` —— 每个 asyncio task 有独立的上下文拷贝,天然并发
隔离:

`gateway/run.py:21333-21353 @ 863e313`(节选)
```python
    def _set_session_env(self, context: SessionContext) -> list:
        """Set session context variables for the current async task.

        Uses ``contextvars`` instead of ``os.environ`` so that concurrent
        gateway messages cannot overwrite each other's session state.
        ...
        """
        from gateway.session_context import set_session_vars
        # Propagate the adapter's async-delivery capability so async tools
        # (terminal notify_on_complete / watch_patterns, delegate_task
        # background=True) know whether this channel can wake a later turn.
        # Default True keeps CLI / unknown paths working; stateless adapters
        # (api_server) declare supports_async_delivery=False. ...
        _adapters = getattr(self, "adapters", None) or {}
        _adapter = _adapters.get(context.source.platform)
        _async_delivery = getattr(_adapter, "supports_async_delivery", True)
        return set_session_vars(
            platform=context.source.platform.value,
            chat_id=context.source.chat_id,
            ...
            async_delivery=_async_delivery,
            cron_session="",
        )
```

传入的字段:platform/chat_id/chat_type/chat_name/thread_id/user_id/user_name/
session_key/message_id/profile,外加两个特殊量:
- `async_delivery`:本通道能否在 turn 结束后唤醒后续投递(terminal 的
  notify_on_complete、delegate_task background=True 依赖它);从 adapter 的
  `supports_async_delivery` 读,默认 True(CLI/未知路径可用),api_server 这类无状态
  请求-响应 adapter 声明 False。
- `cron_session=""`:显式标记"非 cron 会话"。对端是三态语义
  (`gateway/session_context.py:239-241 @ 863e313`:`_UNSET` 保留 legacy
  `os.environ["HERMES_CRON_SESSION"]` 回退、`"1"` 标记 cron、`""` 显式非 cron 并**掩盖
  泄漏的 env**)。

**与 `set_session_vars` 的关系(核心)**:`gateway/session_context.py:206-271 @ 863e313`
是权威实现——十几个模块级 ContextVar(74-128 行,默认值 `_UNSET` 哨兵),
`set_session_vars` 逐个 `.set()` 收集 token 返回,并置全局
`_session_context_engaged = True`(246-247):子进程 env 桥接据此从"os.environ 回退"
切换到"ContextVar 权威、_UNSET 即剥除"。它还顺带 `set_session_cwd(cwd)`(265-270)。

**清理端的真实语义与 docstring 冲突**:`_clear_session_env` 的 docstring 说
"Restore session context variables to their pre-handler values"
(`gateway/run.py:21370-21371 @ 863e313`),但它调用的 `clear_session_vars` 实际**不是
恢复**,而是全部置 `""`:

`gateway/session_context.py:274-284 @ 863e313`
```python
def clear_session_vars(tokens: list) -> None:
    """Mark session context variables as explicitly cleared.

    Sets all variables to ``""`` so that ``get_session_env`` returns an empty
    string instead of falling back to (potentially stale) ``os.environ``
    values.  The *tokens* argument is accepted for API compatibility with
    callers that saved the return value of ``set_session_vars``, but the
    actual clearing uses ``var.set("")`` rather than ``var.reset(token)``
    to ensure the "explicitly cleared" state is distinguishable from
    "never set" (which holds the ``_UNSET`` sentinel).
    """
```

设计理由:三态哨兵(`_UNSET`=从未设置→允许 os.environ 回退 / `""`=显式清除→抑制回退 /
非空=权威值)比 token 恢复更重要——token reset 会退回 `_UNSET`,重新打开"读到陈旧
os.environ"的口子。代价是**不可嵌套**(set_session_vars docstring 226-230 明说
"not nestable/stack-safe")。`async_delivery` 是唯一例外:清除时回 `_UNSET` 而非
falsy(305-306),因为"清过的上下文"应回落到默认支持(CLI 路径),不能被误判为
无状态 adapter 的显式退订。

**使用桥架**:主消息处理 `_process_message_background` 内
`_session_env_tokens = self._set_session_env(context)`(`gateway/run.py:16419 @ 863e313`)
… `finally: self._clear_session_env(_session_env_tokens)`(18292-18293)。session_key
即由此传播给工具(4407 注释)。

**重实现要点**:
- 并发 harness 的"当前会话是谁"必须用 task-local(contextvars),不能用进程全局
  (os.environ);但为兼容 CLI/子进程,保留 env 回退并用三态哨兵管理它。
- "清除"设计成显式状态而非栈恢复:安全性(压制陈旧 env)> 嵌套能力;不可嵌套要写
  进契约。
- capability 类变量(async_delivery)清除后应回默认态哨兵,不能与显式 False 混同。
- 通道能力(能否异步回投)由 adapter 声明、经 contextvar 下发到工具层,工具据此决定
  能否承诺"完成后通知你"。

## 23. `_run_in_executor_with_context`

**问题**:agent 的阻塞工作(run_conversation)在线程池跑,但 §22 的 ContextVar 是
task-local 的——裸 `run_in_executor` 会让工具在工作线程里读到空上下文,消息发错 chat。

**实现**:`copy_context()` 抓当前快照,让线程内经 `ctx.run(func)` 执行:

`gateway/run.py:21375-21384 @ 863e313`
```python
    async def _run_in_executor_with_context(self, func, *args):
        """Run blocking work in the thread pool while preserving session contextvars."""
        loop = asyncio.get_running_loop()
        ctx = copy_context()
        return await loop.run_in_executor(
            self._get_executor(),
            ctx.run,
            func,
            *args,
        )
```

调用方:主 agent 执行(`gateway/run.py:25190`)、后台任务(19591)、agent 资源清理
(9615-9618,带 `asyncio.wait_for` 超时,#53175:清理卡死不许拖住事件循环)。

**重实现要点**:
- contextvars 不会自动跨线程;进线程池必须 `copy_context().run` 包一层,且全 harness
  统一走这一个封装(否则总有一条路径漏)。
- 快照语义:线程内对 ContextVar 的修改不回传事件循环侧——正好符合"工具只读会话
  标识"的用法。

## 24. executor 管理 `_get_executor` / `_shutdown_executor`

**问题**:gateway 需要自有线程池(而非 loop 默认 executor):可控的容量与线程命名、
关闭时不影响 loop 默认池、且要处理"关闭中还有人来要 executor"的竞态。

**实现**:双检惰性创建 + closing 标志:

`gateway/run.py:21393-21403 @ 863e313`
```python
        with lock:
            if getattr(self, "_executor_closing", False):
                raise RuntimeError("Gateway is shutting down; executor unavailable")
            executor = getattr(self, "_executor", None)
            if executor is None or getattr(executor, "_shutdown", False):
                executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=10,
                    thread_name_prefix="hermes-gateway",
                )
                self._executor = executor
            return executor
```

细节:锁本身也是惰性建(21388-21391,裸 runner 兼容);检查私有 `_shutdown` 属性,
外部把池关了也能重建;`max_workers=10` 即并发 agent turn 的硬上限;线程名前缀
`hermes-gateway` 便于 profiling/dump 归因。关闭(21405-21422):锁内置
`_executor_closing=True` 并摘引用,锁外 `shutdown(wait=False, cancel_futures=True)`
(TypeError 回退兼容 Python<3.9 签名);docstring 强调"不碰 loop 默认 executor"。

**重实现要点**:
- harness 自有池与 loop 默认池分离;容量 = 并发 turn 上限,显式可数。
- 关闭序:标志位(拒新)→ 摘引用 → 锁外 shutdown(cancel_futures);get 侧先查
  closing 再查实例,防关闭后复活。
- 对"池被外部关闭"防御性重建(查 `_shutdown`);老 Python 签名回退。

---

## 文档-代码冲突候选(汇总)

1. **▲ 原生 Discord lane 的 rename_thread 调用签名不兼容**:
   `gateway/run.py:19960-19965 @ 863e313` 无条件传
   `prefer_connector_created=`/`parent_chat_id=`,而原生插件 adapter 签名
   (`plugins/platforms/discord/adapter.py:6866-6872 @ 863e313`)只收
   `only_if_current_name`,原生 lane 调用应抛 TypeError 并被 19972-19973 的
   debug 级 except 吞掉 → 原生 auto-thread 语义改名疑似静默失效。19930 注释
   "Native-marker lane keeps the legacy string guard" 与实际行为冲突。测试仅以宽签名
   fake 覆盖 relay lane(tests/gateway/relay/test_relay_threads.py:386-389)。待验证定案。
2. **◇ `_clear_session_env` docstring 说 "Restore ... to their pre-handler values"**
   (`gateway/run.py:21371 @ 863e313`),实际 `clear_session_vars` 是全部置 `""`、token
   仅作 API 兼容(`gateway/session_context.py:274-284 @ 863e313`)。同文件内
   `set_session_vars` 的 docstring(226-230)已写对;run.py 侧措辞过时。
3. **◇ `stt_echo_transcripts` 配置覆盖不全**:`gateway/config.py:915 @ 863e313` 声明
   "Whether to echo raw STT transcripts back to the user",`_should_echo_stt_transcripts`
   (run.py:19267-19269)只在 Telegram 语音消息 lane 被查(run.py:15935、21769);
   Discord voice 频道的转写回显(run.py:19158-19165)不查该开关,恒回显。
4. **◇ 残缺注释**:`gateway/run.py:21024 @ 863e313`
   `# .update_response to continue — it doesn't re-check` 是半句(上文被编辑掉),
   无法读出主语;行为以代码为准(prompt 文件保留在盘、进程内靠 pending 标志抑制重发)。

## 与其他文件的调用关系(索引)

- `plugins/platforms/discord/adapter.py`:1031-1045(voice 回调槽位/映射)、4139-4230
  (join/leave)、4232(play_in_voice_channel)、4328(get_user_voice_channel)、
  4365-4384(超时断线→ `_on_voice_disconnect`)、4542-4546(STT→`_voice_input_callback`)、
  6866(rename_thread 原生签名)、7869-7871(auto_thread 标记 ingest)。
- `gateway/relay/adapter.py`:1002-1008(auto_thread_info_for_chat)、2085-2133
  (rename_thread relay 签名 + thread_rename op)。
- `gateway/relay/ws_transport.py`:224-225(relay inbound 的 auto_thread 标记)。
- `gateway/platforms/base.py`:106-138(reply anchor 规则)、141-161
  (should_send_media_as_audio)、164-187(build_auto_tts_output_path)、190-209
  (utf16 工具)。
- `gateway/session_context.py`:74-128(ContextVar 表)、206-271(set_session_vars)、
  274-306(clear_session_vars)。
- `agent/async_utils.py`:34-68(safe_schedule_threadsafe)。
- `tools/slash_confirm.py`:51-140(register/get_pending/resolve)。
- `tools/tts_tool.py`:636-642(OPUS_VOICE_PLATFORMS)、text_to_speech_tool、
  `_strip_markdown_for_tts`。
- `tools/mcp_tool.py`:shutdown_mcp_servers / discover_mcp_tools / `_servers` / `_lock`、
  6720(refresh_agent_mcp_tools)。
- `gateway/slash_commands.py`:3301-3335(/background 入口)、5190-5240
  (/reload-mcp 确认)、2433(昂贵模型切换确认)。
- `gateway/delivery.py`:92(resolve_delivery_transport)。
- run.py 内部:452(_non_conversational_metadata)、5685/5702(标题回调注册)、
  6352-6421(voice mode 存取与 auto-TTS 集合)、6745(_is_telegram_topic_lane)、
  11122-11124 与 12485-12487(voice 回调接线)、11396-11434(启动通知序列)、
  14513-14580(update 答复拦截)、14655-14694(slash-confirm 文本拦截)、
  15066/15260(destructive 确认调用)、16419 与 18292-18293(session env 括号)、
  18130-18160(voice 回复 + 流式媒体投递调用点)。

## 引用 issue / 事故索引

- #50149 语音输入缺 channel_prompt(§3);#20834 流式后裸路径误升级为上传(§6);
  #73771 显式 MEDIA 被跨 turn 去重吞掉(§6);#60955 后台任务用陈旧 fallback_model
  (§7);#57049/#36685 auto-TTS 恒 MP3(contextvar 已清,§5);#60671 流式 TTS 与
  runner TTS 重复(§4);#60623 重连后语音回调未接(§1);#53175 agent 清理卡死
  (§23);staging repro 2026-07-29(relay 标题 turn 无标记)、2026-07-31(注册期查缓存
  永不注册)、2026-08-01(rename 缺父频道 id 被租户守卫拒)、2026-08-02(单槽缓存致
  兄弟 thread 不改名)(§9-10)。
