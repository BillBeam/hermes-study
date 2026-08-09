# r7c-raw-delivery · 投递面 9 文件底稿

> 基线 `863e31318553cda8ad61df681d08175364d4164b`。所有断言格式为 `路径:行号 @ 863e313` + 代码原文。
> 本切片 9 个文件共 2327 行,全部逐行精读。
>
> | 文件 | 行数 |
> |---|---|
> | `gateway/delivery.py` | 646 |
> | `gateway/delivery_ledger.py` | 374 |
> | `gateway/response_filters.py` | 147 |
> | `gateway/mirror.py` | 206 |
> | `gateway/rich_sent_store.py` | 83 |
> | `gateway/sticker_cache.py` | 124 |
> | `gateway/dead_targets.py` | 143 |
> | `gateway/runtime_footer.py` | 181 |
> | `gateway/streaming_tts_consumer.py` | 423 |

---

## 0. 一句话

**这 9 个文件不是"一条投递流水线",而是投递面上互不隶属的 9 个小机制;真正的主投递路径在
`gateway/platforms/base.py` 里(适配器自己 `_send_with_retry` → `send()`),`delivery.py` 的
`DeliveryRouter` 只是 cron/多目标扇出的第二条路径,并且它的公开入口 `deliver()` 在全仓
零生产调用点 —— 连带整个 `dead_targets.py` 一起处于休眠状态。**

---

## 1. 投递链路全景

先把"一条 agent 回复怎么变成平台上的消息"走一遍,标出这 9 个文件各自插在哪。

### 1.1 交互式主路径(用户在 Telegram 发一句话)

这是**生产上真正跑的那条**。它**完全不经过 `delivery.py`**。

```
用户消息
  → 适配器 inbound(Telegram adapter)
      · 贴纸 → gateway/sticker_cache.py(视觉描述缓存,把图片变成文字注入)
      · 回复了一条 rich message → gateway/rich_sent_store.py lookup(找回被引用的原文)
  → gateway/run.py _handle_message_with_agent → _run_agent_inner
      · 流式文本 → gateway/stream_consumer.py
          └─ 用 gateway/response_filters.py 判断 NO_REPLY / [SILENT] 是否要憋住
      · 语音输入且开了 auto-TTS → gateway/streaming_tts_consumer.py(与文本流并联,tee)
  → run.py 拼最终文本
      · gateway/runtime_footer.py build_footer_line() 追加页脚(默认关)
      · gateway/response_filters.py is_intentional_silence_agent_result() 判静默
  → gateway/platforms/base.py 的 finalize 段
      · gateway/delivery_ledger.py record_obligation + mark_attempting  ← 发之前记账
      · delivery_adapter._send_with_retry(...)                          ← 重试在这一层
      · gateway/delivery_ledger.py mark_delivered / mark_failed         ← 发之后销账
  → 平台上出现消息
```

崩溃恢复:下次开机 `gateway/run.py:11447` 调 `_redeliver_pending_obligations()`,
从 `delivery_ledger` 捞出上次没销账的行重发。

### 1.2 cron / 扇出路径(定时任务把简报发到某个 chat)

这条才用 `delivery.py`,而且**只用它的私有方法**:

```
cron/scheduler.py 执行 job
  → gateway/response_filters.py is_autonomous_silence_response()  判断 [SILENT] 抑制
  → DeliveryRouter(config, adapters)                              cron/scheduler.py:1806
  → router._deliver_to_platform(target, text, metadata)           cron/scheduler.py:1819  ← 注意是私有方法
      · 超长 → 落盘审计 + 截断(非分片适配器)
      · 静默叙述("*(silent)*"、🔇、".")→ 丢弃
      · Telegram 私聊话题三态路由
      · transport.send() → adapter.send()                          ← 这里没有重试
  → gateway/mirror.py mirror_to_session()                         cron/scheduler.py:727/858/951
      把简报以 user 角色写回目标会话,让下一轮对话有上下文
```

### 1.3 关键分工:`delivery.py` vs 适配器 `send()`(R7B 读过的)

| 关注点 | 在哪一层 | 证据 |
|---|---|---|
| **重试 / 退避 / FloodWait** | 适配器 `BasePlatformAdapter._send_with_retry` | `gateway/platforms/base.py:5042` |
| **长消息分片** | 适配器 `send()` 内部,由 `splits_long_messages` 声明 | `gateway/platforms/base.py:2698`(默认 False)、`plugins/platforms/telegram/adapter.py:631`(True) |
| **超长内容落盘 + 截断兜底** | `DeliveryRouter._deliver_to_platform` | `gateway/delivery.py:488-523` |
| **格式降级(markdown 失败退纯文本)** | 适配器 `_send_with_retry` | `gateway/platforms/base.py:5054-5057` |
| **多目标扇出 / 目标串解析** | `DeliveryRouter.deliver` + `DeliveryTarget.parse` | `gateway/delivery.py:230-291, 318-391`(**零生产调用**) |
| **native / relay 传输选择** | `resolve_delivery_transport`(共享函数) | `gateway/delivery.py:92-131` |
| **顺序保证** | 无。`deliver()` 是 `for target in targets` 串行循环,单目标内无排队 | `gateway/delivery.py:341` |
| **超时** | 无 timeout。cron 侧在调用方加 `future.result(timeout=60)` | `cron/scheduler.py` 的 `_deliver_to_platform` 调用点 |
| **崩溃后不丢** | `delivery_ledger`(只覆盖 1.1 主路径,不覆盖 cron) | `gateway/platforms/base.py:6060-6113` |

**要点:`delivery.py` 是"路由 + 内容适配"层,不是"传输可靠性"层。**
可靠性(重试/分片/降级)全部下沉在适配器里。

---

## 2. 逐文件

---

### 2.1 `gateway/delivery.py`(646 行)—— 路由面,但主入口是死的

#### 问题

一段 agent 输出可能要送到:回到原会话("origin")、送到平台的 home 频道("telegram")、
送到指定 chat("telegram:123456")、送到指定话题("telegram:123456:17585")、
或者只落地成文件("local")。而且平台可能是 relay 代理的(一个 RELAY 适配器背后代理 N 个逻辑平台)。
需要一个地方把"目标串"翻译成"真正的 adapter + chat_id + metadata"。

#### 实现

**(a) 目标串解析 `DeliveryTarget.parse`**(`gateway/delivery.py:230-279 @ 863e313`):

```python
    @classmethod
    def parse(cls, target: str, origin: Optional[SessionSource] = None) -> "DeliveryTarget":
```
```python
        # Check for platform:chat_id or platform:chat_id:thread_id format
        # Use the original case for chat_id/thread_id to preserve case-sensitive IDs
        if ":" in target_stripped:
            parts = target_stripped.split(":", 2)
            platform_str = parts[0].lower()  # Platform names are case-insensitive
```

平台名小写化、chat_id/thread_id 保留大小写(Slack 的 `C0123ABCD45` 大小写敏感)。
`split(":", 2)` 最多切三段,所以 Slack 的 `thread_ts`(`1700000000.000100`,含点不含冒号)能整段落到 thread_id。
未知平台名一律降级成 LOCAL(`gateway/delivery.py:270-271, 278-279`),**不报错** —— 静默降级,
这是个取舍:配置写错平台名不会炸,但也不会告诉你。

**(b) 传输解析 `resolve_delivery_transport`**(`gateway/delivery.py:104-143 @ 863e313`):

```python
    live_adapters = adapters or {}
    native = live_adapters.get(platform)
    native_config = config.platforms.get(platform)
    # Preserve DeliveryRouter's historical support for explicitly supplied live
    # adapters with no config block, but never let an explicitly disabled native
    # adapter shadow an enabled Relay transport.
    if native is not None and (native_config is None or native_config.enabled):
        return DeliveryTransport(
            adapter=native,
            config=native_config,
            transport_platform=platform,
        )

    relay = live_adapters.get(Platform.RELAY)
    relay_config = config.platforms.get(Platform.RELAY)
    fronts_platform = getattr(relay, "fronts_platform", None)
    if (
        relay is not None
        and (relay_config is None or relay_config.enabled)
        and callable(fronts_platform)
        and fronts_platform(platform)
    ):
```

规则:**原生适配器优先;relay 只有在它的已认证握手身份集里明确声明"我代理这个平台"时才有资格。**
`fronts_platform` 的实现(`gateway/relay/adapter.py:598-611 @ 863e313`):

```python
    def fronts_platform(self, platform: Any) -> bool:
        """Whether the authenticated relay transport advertises ``platform``.

        This is the restart-safe delivery ownership signal: it comes from the
        configured identity set sent during handshake, not from an inbound
        chat cache learned only after a user sends another message.
        """
```

设计理由写在 `gateway/delivery.py:99-103`:握手身份集在重启后立刻可用,
而"按 chat 学到的缓存"要等用户再发一条消息才有 —— 所以重启后的投递不依赖 per-chat 缓存。

`DeliveryTransport.send`(`gateway/delivery.py:82-97`)保留逻辑平台身份:

```python
        if self.is_relay:
            return await self.adapter.send_for_platform(
                logical_platform,
                chat_id,
                content,
                metadata=metadata,
            )
        return await self.adapter.send(chat_id, content, metadata=metadata)
```

注意这里**没有 `reply_to` 形参** —— 走 DeliveryRouter 的投递永远不是"回复某条消息",
除非通过 metadata 里的 `telegram_reply_to_message_id`(适配器侧读取点:
`plugins/platforms/telegram/adapter.py:1187`)。

**(c) 超长输出两段式处理**(`gateway/delivery.py:475-523 @ 863e313`):

```python
        # Guard: handle oversized cron output.
        #
        # Two independent decisions:
        #   1. AUDIT SAVE — when content exceeds MAX_PLATFORM_OUTPUT, the full
        #      output is always written to disk as a recoverable audit trail.
        #      This fires regardless of adapter capability (best-effort).
        #   2. TRUNCATION — for non-chunking adapters, content above the cap is
        #      truncated with a footer pointing to the saved file.  Chunking-
        #      capable adapters (splits_long_messages=True) receive the full
        #      payload and split natively in their send().
```

阈值 `MAX_PLATFORM_OUTPUT = 4000`(`gateway/delivery.py:23`),注释解释为什么不是 4096:

```python
# Cap before gateway-level truncation of cron output for non-chunking platform
# delivery.  Telegram's hard API limit is 4096; the headroom covers the "full
# output saved to …" footer appended on truncation.  Adapters that split long
# messages natively (BasePlatformAdapter.splits_long_messages) bypass this
# entirely — the adapter chunks in its own send() and the full output is
# preserved.
MAX_PLATFORM_OUTPUT = 4000
```

审计落盘是 best-effort,失败只 warning(`gateway/delivery.py:493-500`);
但如果适配器不分片、需要在 footer 里写路径,就必须重试落盘,这次失败是真失败
(`gateway/delivery.py:512-516`):

```python
                # Non-chunking adapter — truncate with footer.  The footer
                # needs a valid path, so if the best-effort save above failed,
                # retry it here (a failure now is a real delivery problem).
                if saved_path is None:
                    saved_path = self._save_full_output(content, job_id)
```

**(d) 静默叙述过滤(反回环)**(`gateway/delivery.py:36-55, 525-544 @ 863e313`):

正则:
```python
_SILENCE_NARRATION = re.compile(
    r'^[\s*_~`]*\(?\s*(silent|silence|no\s+response|no\s+reply)\s*\.?\)?[\s*_~`]*$'
    r'|^[\s*_~`]*[\U0001F507\.…]+[\s*_~`]*$',
    re.IGNORECASE,
)
```

设计理由(`gateway/delivery.py:525-532`),这是本文件里最值得学的一段:

```python
        # Substrate-level anti-loop guard: drop hallucinated "silence narration"
        # (*(silent)*, 🔇, a bare ".", etc.) before it ever reaches the adapter.
        # In bot-to-bot channels these tokens mirror back and forth until a
        # model crashes with "no content after all retries". Behavioral prompt
        # rules drift across providers; this single chokepoint covers every
        # platform adapter regardless of which persona's prompt failed.
        # Local/file delivery (_deliver_local) is a separate path and is never
        # filtered — saved silence has no loop risk.
```

即:**行为约束(prompt 里写"不要输出 (silent)")会随 provider 漂移,所以在基座上加一个卡口。**
双重保险:64 字长度守卫 + 整串锚定(`gateway/delivery.py:53-55`),
所以 "The deployment ran silently" 不会被误杀。

开关三级:env `HERMES_FILTER_SILENCE_NARRATION` > config `gateway.filter_silence_narration` > 默认 True
(`gateway/delivery.py:448-458`;配置项定义在 `gateway/config.py:911`)。

**(e) Telegram 私聊话题三态路由**(`gateway/delivery.py:554-605 @ 863e313`)

这是本文件最绕的一段。前提:Telegram 私聊(正数 chat_id)里的"话题"和群组 forum topic
形状相同但 API 不同。判定私聊靠 `looks_like_telegram_private_chat_id`
(`gateway/delivery.py:134-147`,正数 = 私聊,负数 = 群/频道/超级群)。

三种分支:

1. **命名话题**(thread_id 不是数字,且 metadata 里没有任何 thread 键)——
   调 `adapter.ensure_dm_topic(chat_id, name)` 现场建/查话题
   (`gateway/delivery.py:572-576`,适配器实现 `plugins/platforms/telegram/adapter.py:3316`):
   ```python
                ensure_dm_topic = getattr(adapter, "ensure_dm_topic", None)
                if ensure_dm_topic is None:
                    raise RuntimeError(
                        "Telegram adapter cannot create named private DM topics"
                    )
   ```
2. **数字 thread_id 的私聊**(`gateway/delivery.py:596-614`)—— 必须有 reply anchor,否则**直接抛**:
   ```python
                reply_anchor = send_metadata.get("telegram_reply_to_message_id")
                if reply_anchor is None:
                    raise RuntimeError(
                        "Telegram private DM topic delivery requires telegram_reply_to_message_id; "
                        "send to the bare chat or provide a reply anchor"
                    )
   ```
   cron 就是被这条卡住的,所以 cron 侧显式把 `thread_id` 塞进 metadata 来绕过检查
   (`cron/scheduler.py:1778-1785 @ 863e313` 注释明说 "the metadata key bypasses that check")。
3. **其它情况** —— 直接 `send_metadata["thread_id"] = target_thread_id`(`gateway/delivery.py:604-605`)。

**(f) 命名话题的"话题被删"自愈**(`gateway/delivery.py:612-639 @ 863e313`):
send 失败且错误文本含 "thread not found"(判定在 `gateway/delivery.py:174-176`),
就用 `force_create=True` 重建话题再发一次:

```python
                refreshed_thread_id = await ensure_dm_topic(
                    target.chat_id,
                    named_telegram_private_topic_name,
                    force_create=True,
                )
```

**这是本文件里唯一的重试** —— 而且是语义重试(重建资源),不是网络重试。

**(g) 硬失败用 raise 而不是返回**(`gateway/delivery.py:640-641`):

```python
            if _send_result_failed(result):
                raise RuntimeError(_send_result_error(result) or f"{target.platform.value} delivery failed")
```

后果:`deliver()` 只能拿到异常字符串,拿不到结构化 `error_kind`,
所以要有 `_classify_dead_from_error_text`(`gateway/delivery.py:191-213`)从文本里反推:

```python
    ``_deliver_to_platform`` raises (it does not return a SendResult) on a hard
    failure, so the ``deliver()`` loop only has the exception string.  Reuse the
    platform-neutral classifier to recover the error_kind from that text.
```

这是一处**自己给自己制造的信息损失**,值得记为设计教训。

#### 取舍

- **静默降级 vs 显式报错**:未知平台名 → LOCAL,不抛。配置手误无声吞掉。
- **raise 而非返回 SendResult**:调用侧简单,但丢失结构化错误,只能再做一次文本分类。
- **`self.output_dir` 在构造时冻结**(`gateway/delivery.py:315`)而 `_save_full_output`
  在调用时重解析(`gateway/delivery.py:442`)—— 同一个文件里两种 HERMES_HOME 解析时机,
  多 profile 场景下可能不一致。
- **`results` 用 `target.to_string()` 做 key**(`gateway/delivery.py:357/372/386`),
  重复目标会互相覆盖,扇出结果统计不准。

#### 死代码 / 命名漂移

- **`DeliveryRouter.deliver()` 零生产调用点**(详见 §3)。连带 `_deliver_local`(`gateway/delivery.py:393`)
  和整个 dead-target 短路逻辑(`gateway/delivery.py:347-362, 369-370, 376-385`)全部不可达。
- `gateway/delivery.py:369` 的 `not _send_result_failed(result)` 实质恒真:
  `_deliver_to_platform` 失败会 raise,能走到这里的只有成功结果或静默过滤返回的
  `{"success": True, ...}`。防御性冗余。
- 文件末尾 `gateway/delivery.py:643-646` 是三行空白 —— 曾经被删掉的代码留下的痕迹。

---

### 2.2 `gateway/delivery_ledger.py`(374 行)—— 唯一"记账"机制

#### 问题

模块 docstring 把它讲得很清楚(`gateway/delivery_ledger.py:1-10 @ 863e313`):

```python
"""Durable delivery-obligation ledger for gateway final responses.

A final agent response that was generated but not yet confirmed-delivered
to the messaging platform is the one artifact the gateway can lose without
a trace: the turn already burned its tokens, the text exists only in a
Python local, and a crash / planned restart between finalize and platform
ACK drops it silently (#58818, #41696, #63695).
```

**这不是去重台账,是"欠条"台账。** 记的是"我欠平台一条消息还没送到"。

#### 记什么

表结构(`gateway/delivery_ledger.py:97-112 @ 863e313`):

```sql
        """CREATE TABLE IF NOT EXISTS delivery_obligations (
            obligation_id TEXT PRIMARY KEY,
            session_key TEXT NOT NULL,
            platform TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            thread_id TEXT,
            content TEXT NOT NULL,
            state TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            owner_pid INTEGER,
            owner_started_at INTEGER,
            last_error TEXT
        )"""
```

**全文 content 都存进去** —— 这是重发的前提(不然重发就得重跑一轮)。

#### 存哪、留多久

- 存 `get_hermes_home() / "state.db"`(`gateway/delivery_ledger.py:74-75`),
  与 `tools.async_delegation` 共库、共 WAL 约定(`gateway/delivery_ledger.py:11-14`)。
- 保留 7 天 + 最多 500 行(`gateway/delivery_ledger.py:63-64`):
  ```python
  _RETENTION_SECONDS = 7 * 24 * 60 * 60
  _MAX_ROWS = 500
  ```
- 超额裁剪按 state 优先级(`gateway/delivery_ledger.py:324-334`):`delivered`(0)先删,
  `abandoned`(1)次之,**未决行(2)最后删** —— 保住真正欠着的债。

#### 四态机 + 崩溃歧义契约

`gateway/delivery_ledger.py:14-31 @ 863e313`:

```python
    record_obligation()   state='pending'     before any send attempt
    mark_attempting()     state='attempting'  immediately before the await
    mark_delivered() /    state='delivered'   only on SendResult.success
    mark_failed()         state='failed'      on a definitive rejection
```
```python
- ``pending``     — the send never started: redeliver plainly, no dup risk.
- ``attempting``  — crashed mid-await: the platform MAY already have the
  message. Redelivered WITH a visible recovered-reply marker so the
  contract is honest at-least-once, never a silent duplicate.
- ``failed``      — definitively rejected once; the restart is a natural
  retry boundary. Also carries the marker.
- ``delivered``   — nothing to do; retention prunes.
```

标记文本(`gateway/delivery_ledger.py:68-71`):

```python
RECOVERED_MARKER = (
    "♻️ Recovered reply — the gateway restarted during delivery, "
    "so this may be a duplicate:\n\n"
)
```

**这是本切片最好的设计:歧义不消除,而是"暴露给人看"。** 不做静默去重,也不做静默丢弃。
`gateway/delivery_ledger.py:21-23` 记录了历史:早先有个 delivery-outbox 尝试(#61790),
契约评审因为"会静默重发歧义消息"把它毙了。

#### 并发怎么控

三层:

1. **进程内 `threading.Lock`**(`gateway/delivery_ledger.py:56`):`_DB_LOCK`,包住每个写事务。
2. **进程间靠 SQLite WAL + `timeout=10`**(`gateway/delivery_ledger.py:81, 95`)。
3. **跨进程行级认领用 CAS**(`gateway/delivery_ledger.py:286-293 @ 863e313`):
   ```python
            cursor = conn.execute(
                """UPDATE delivery_obligations
                   SET owner_pid=?, owner_started_at=?, attempts=attempts+1,
                       updated_at=?
                   WHERE obligation_id=? AND (owner_pid IS ? OR owner_pid=?)""",
                (pid, started, now, oid, owner_pid, owner_pid),
            )
            if cursor.rowcount:
   ```
   WHERE 里带上"我读到的旧 owner_pid",两个网关同时 sweep 时只有一个 rowcount 非零。
   `IS ?` 处理 NULL(`owner_pid IS NULL`)。

**存活判定**用 pid + 进程启动时间双因子(`gateway/delivery_ledger.py:145-176 @ 863e313`),
防 pid 复用:

```python
    if started_at is None:
        return True
    try:
        return int(current_start) == int(started_at)
    except (TypeError, ValueError):
        return True
```

拿不到启动时间时退化到 `os.kill(pid, 0)`,`PermissionError` 算活着(`gateway/delivery_ledger.py:163-170`):

```python
            os.kill(pid, 0)  # windows-footgun: ok — EPERM counts as alive below
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
```

**保守方向一致:不确定就当活着,宁可不重发,也不重复发。**

#### 重发预算怎么不被浪费

`sweep_recoverable` 的 `deliverable_platforms` 参数(`gateway/delivery_ledger.py:250-254 @ 863e313`):

```python
    ``deliverable_platforms`` (platform value strings) restricts claiming to
    platforms the caller can actually send on this boot.  ``attempts`` is the
    redelivery budget, so it must only be spent on a real send: a platform
    that failed to connect would otherwise burn one attempt per boot and hit
    the cap having never been sent once.  Rows for absent platforms are left
    untouched for a later boot; the stale cutoff still bounds them.
```

调用方(`gateway/run.py:10374-10379 @ 863e313`):

```python
            _deliverable = {
                getattr(p, "value", str(p)) for p in self.adapters
            }
            claimed = await asyncio.to_thread(
                sweep_recoverable, None, deliverable_platforms=_deliverable
            )
```

配套测试直接把这条写成规格:`tests/gateway/test_delivery_ledger.py:238`
`test_absent_platform_does_not_burn_attempts`、`:286` `test_row_survives_boots_where_its_platform_is_down`。

#### 毒丸行不会自旋

`gateway/delivery_ledger.py:272-278 @ 863e313`:

```python
            if attempts >= MAX_ATTEMPTS or (now - created_at) > STALE_AFTER_SECONDS:
                conn.execute(
                    """UPDATE delivery_obligations
                       SET state='abandoned', updated_at=? WHERE obligation_id=?""",
                    (now, oid),
                )
                continue
```

`MAX_ATTEMPTS = 3`、`STALE_AFTER_SECONDS = 24h`(`gateway/delivery_ledger.py:61-62`),
且明确不做成配置项(`gateway/delivery_ledger.py:58-60`):

```python
# Redelivery policy knobs (module constants; deliberately not config — the
# ledger itself is gated by ``gateway.delivery_ledger`` and these bounds
# only matter in the rare recovery path).
```

#### 幂等 id

`gateway/delivery_ledger.py:179-185 @ 863e313`:

```python
def compute_obligation_id(session_key: str, message_ref: str, content: str) -> str:
    """Stable id: same turn + same content re-records idempotently, while
    distinct threads/topics on the same chat can never collide (the
    session_key carries platform, chat and thread; ``message_ref`` is the
    triggering inbound message id, distinguishing turns in one session)."""
    payload = f"{session_key}|{message_ref}|{content}"
    return hashlib.sha256(payload.encode("utf-8", "replace")).hexdigest()[:24]
```

注意副作用:`record_obligation` 用 `INSERT OR REPLACE`(`gateway/delivery_ledger.py:202`),
所以同一 id 再记会把 `state` 重置为 `'pending'`、`attempts` 重置为 0。
理论上这是"重发预算被重置"的漏洞,但要求同一轮对同一条入站消息产出**字节完全相同**的回复才触发。

#### 连接泄漏坑(重要教训)

`gateway/delivery_ledger.py:115-132 @ 863e313`:

```python
@contextmanager
def _transaction() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit/rollback on exit, and ALWAYS close it.

    ``sqlite3.Connection.__enter__``/``__exit__`` only commit or roll back the
    transaction; they do not close the connection. Using ``with _connect()``
    alone therefore leaks a connection — and its WAL/SHM file descriptors — on
    every call, deferring the close to the garbage collector. On a long-running
    gateway that exhausts ``RLIMIT_NOFILE`` (the cron-ledger sibling of this
    bug was #69567 / PR #69594). ``record_obligation`` runs on every outbound
    final response, so this ledger is the highest-frequency leaker.
    """
```

`_connect()` 里还有配套的泄漏防护(`gateway/delivery_ledger.py:82-88`):
DDL 失败时先 `conn.close()` 再抛。专门有回归测试 `tests/gateway/test_delivery_ledger_fd_leak.py`。

#### 取舍

- **每条最终回复要写 2 次 SQLite**(`record_obligation` + `mark_attempting`,
  `gateway/platforms/base.py:6073-6087`),再加发完 1 次销账 = 3 次。
  用 `asyncio.to_thread` 卸载到线程池不阻塞事件循环
  (回归测试 `tests/gateway/test_delivery_ledger.py:207` `test_slow_state_update_does_not_block_event_loop`)。
- **`_prune()` 在 `_DB_LOCK` 之外调用**(`gateway/delivery_ledger.py:200-211`:
  `with _DB_LOCK, _transaction()` 块在 210 行结束,211 行才调 `_prune()`),
  且 `_prune` 内部只用 `_transaction()` 不加 `_DB_LOCK`。靠 SQLite 自身锁 + 全 try/except 兜住。
- **只覆盖交互式主路径**:cron 投递、slash 命令回复、ephemeral 回复都不记账
  (`gateway/platforms/base.py:6055-6056`:"Slash-command and ephemeral replies are cheap
  to regenerate and are not recorded.")。
- **全程 best-effort**(`gateway/delivery_ledger.py:36-37`):
  "ledger failures must never block or delay an actual send. Callers wrap every call in try/except."

---

### 2.3 `gateway/response_filters.py`(147 行)—— 两套静默规则 + 一个流式前缀判定

#### 问题

模型有时会"故意不说话"(群聊里别人在聊、cron 任务这一轮没新事)。
需要一个约定让模型能表达"这轮别发"。但约定必须窄:一句
"Use `[SILENT]` when nothing changed" 不能被当成静默。

#### 过滤掉什么

**只有一个 marker 集合**(`gateway/response_filters.py:19-24 @ 863e313`),两套匹配规则共享它:

```python
LIVE_GATEWAY_SILENT_MARKERS = frozenset({
    "[SILENT]",
    "SILENT",
    "NO_REPLY",
    "NO REPLY",
})
```

**规则 A — 交互式(严格)** `is_intentional_silence_response`(`gateway/response_filters.py:56-70`):
整串必须**恰好**是 marker,长度 ≤ 64,空串不算(空串走 empty-response 失败路径)。

**规则 B — 自主车道(宽松)** `is_autonomous_silence_response`(`gateway/response_filters.py:73-111 @ 863e313`)。
docstring 讲清了为什么要两套:

```python
    Autonomous lanes instruct the agent to emit ``[SILENT]`` when a tick
    produced nothing worth a human's attention, and models reliably bracket
    the marker with a short note explaining why they stayed quiet.
```

三种命中形态(`gateway/response_filters.py:98-110`):整串是 marker;marker 独占首行或末行;
`[SILENT]` 作为同行前缀。**明确不做"contains"**:

```python
    # Bracketed sentinel used as a same-line prefix — the documented pattern
    # "[SILENT] No changes detected".  Restricted to the bracketed form so a
    # bare word like "Silent retry succeeded" is NOT swallowed.
```

**规则 C — 流式前缀判定** `is_partial_silence_marker`(`gateway/response_filters.py:123-147 @ 863e313`)。
这个最巧:流式输出是一个 delta 一个 delta 来的,`"NO"` 可能是 `"NO_REPLY"` 的开头,
也可能是 `"NOthing changed"` 的开头。判定"当前 buffer 还有可能长成 marker":

```python
    for candidate in _canonical_silence_candidates(stripped):
        if candidate and any(marker.startswith(candidate) for marker in LIVE_GATEWAY_SILENT_MARKERS):
            return True
```

设计理由(`gateway/response_filters.py:128-131`):

```python
    A buffer whose canonical form is a non-empty *prefix* of a silence marker
    (e.g. ``"NO"`` on the way to ``"NO_REPLY"``, or an exact marker that has
    not yet been terminated by stream-end) is held back so a raw marker is
    never edited onto the screen and then belatedly retracted.
```

**即:宁可延迟几十毫秒,也不要在屏幕上先画出 `NO_REPLY` 再撤回。**

**标点容错**(`gateway/response_filters.py:38-51 @ 863e313`)—— 模型会吐 `.NO_REPLY` 或 `*NO_REPLY*`:

```python
    start = 0
    end = len(text)
    while start < end and text[start] not in "[]" and unicodedata.category(text[start]).startswith("P"):
        start += 1
```

方括号被排除在剥离范围外,理由写在 `gateway/response_filters.py:35-36`:
"Keep square brackets structural so malformed ``[SILENT`` does not become ``SILENT``."
—— 这是防止"半个 marker 被剥成完整 marker"。

**失败轮不静默**(`gateway/response_filters.py:114-120`):

```python
def is_intentional_silence_agent_result(agent_result: dict | None, response: Any) -> bool:
    """Silence markers suppress delivery only for successful agent turns."""
    if not isinstance(agent_result, dict):
        return False
    if agent_result.get("failed"):
        return False
```

#### 顺序敏感吗

**是,但是是"层级顺序"而不是"链式顺序"。** 三个函数互不调用,分别插在三个不同的层:

| 函数 | 生产调用点 | 层 |
|---|---|---|
| `is_partial_silence_marker` | `gateway/stream_consumer.py:888` | 流式渲染中 |
| `is_intentional_silence_response` | `gateway/stream_consumer.py:849` | 流式收尾 |
| `is_intentional_silence_agent_result` | `gateway/run.py:17613`、`gateway/run.py:25623` | turn 收尾 |
| `is_autonomous_silence_response` | `gateway/platforms/webhook.py:97`、`cron/scheduler.py:325` | 自主车道 |

与 `delivery.py` 的 `_is_silence_narration` 是**完全独立的第四套机制**:
后者过滤的是模型幻觉出来的"我保持沉默"叙述(`*(silent)*`、🔇、`.`),
前者过滤的是模型按约定发出的控制标记。两者共存,不互相引用。

#### 死代码

`SILENT_REPLY_TOKEN = "NO_REPLY"`(`gateway/response_filters.py:14`)—— **全仓零引用**
(grep `SILENT_REPLY_TOKEN` 只命中定义行本身,连测试都不用)。

---

### 2.4 `gateway/mirror.py`(206 行)—— 把"送出去的东西"写回会话

#### 问题

Agent 通过 `send_message` 工具主动给某个 chat 发了消息,或者 cron 把简报投到了某个 chat。
**那个 chat 的会话历史里没有这条消息** —— 下次用户在那个 chat 里回一句"这个第 2 条是啥意思",
agent 完全不知道在说什么。

#### 镜像到哪里、镜像什么

镜像到**目标会话的 transcript**(不是审计日志、不是多端同步)。
`mirror_to_session`(`gateway/mirror.py:25-93 @ 863e313`)。

写入路径只有一条(`gateway/mirror.py:79`):

```python
        _append_to_sqlite(session_id, mirror_msg)
```

而 `_append_to_sqlite`(`gateway/mirror.py:197-212 @ 863e313`)只落 role + content:

```python
        db.append_message(
            session_id=session_id,
            role=message.get("role", "assistant"),
            content=message.get("content"),
        )
```

`mirror_msg` 里构造的 `timestamp` / `mirror: True` / `mirror_source`
(`gateway/mirror.py:71-77`)**在 SQLite 边界被丢弃**。

#### 角色选择:一个真实事故

`gateway/mirror.py:40-50 @ 863e313`,这是本文件的核心:

```python
    ``role`` defaults to ``"assistant"`` — correct for the interactive
    ``send_message`` mirror, where the mirrored text is the agent's own
    outgoing reply (a genuine assistant turn). Callers mirroring text that is
    NOT the agent speaking — e.g. a cron brief delivered out-of-band — must
    pass ``role="user"``: the ``mirror``/``mirror_source`` metadata is dropped
    at the SQLite boundary (only role+content persist), so on replay an
    assistant-role mirror is indistinguishable from a real assistant turn and
    produces ``assistant → assistant`` pairs that break strict-alternation
    providers (issue #2221). A user-role mirror collapses safely via
    ``repair_message_sequence``'s consecutive-user merge on every provider.
```

**因果链完整版**(#2221,详见 §5):
metadata 在持久化时被丢 → 重放时 assistant-role 镜像和真正的 assistant 轮无法区分 →
cron 简报镜像落在 agent 上一轮 assistant 之后 → `assistant → assistant` →
严格交替的 provider 直接报错。修法:cron 侧改成 `role="user"` + `[Cron delivery: ...]` 前缀标注来源。

cron 三个调用点都传 `role="user"`:`cron/scheduler.py:727-735`(注释在 `:719-726`,直接引 #2221)、
`cron/scheduler.py:858-866`(`role="user"` 在 `:865`)、
`cron/scheduler.py:951-959`(`role="user"` 在 `:958`)。
`send_message` 工具用默认 assistant:`tools/send_message_tool.py:512-518`。

#### 会话怎么找

`_find_session_id`(`gateway/mirror.py:96-187 @ 863e313`)。两级:

1. **主路径 state.db**(`gateway/mirror.py:119-137`),自 #9006 起:
   ```python
            finder = getattr(db, "find_session_by_origin", None)
            if callable(finder):
                session_id = finder(
                    platform=platform,
                    chat_id=chat_id,
                    thread_id=thread_id,
                    user_id=user_id,
                )
   ```
2. **回退 sessions.json**(`gateway/mirror.py:135-187`),给未迁移的老库。

为什么不能按 session key 匹配(`gateway/mirror.py:107-108`):

```python
    DM session keys don't embed the chat_id (e.g. "agent:main:telegram:dm"),
    so we match on the persisted chat origin, not the key.
```

**多候选时的安全默认**(`gateway/mirror.py:110-114, 168-185`):

```python
    When *user_id* is provided, prefer exact sender matches. If multiple
    same-chat candidates exist and none matches the user, return None instead
    of guessing and contaminating another participant's session.
```

```python
    elif len(candidates) > 1:
        distinct_user_ids = {...}
        if len(distinct_user_ids) > 1:
            return None
```

**宁可不镜像,也不把 A 的消息写进 B 的会话。** 这是隐私/正确性优先于功能完整。

哨兵键跳过(`gateway/mirror.py:148-151`):

```python
        # Skip documentation/metadata sentinels (keys starting with "_", e.g.
        # the gateway's "_README" note) — they are not session entries.
        if str(_key).startswith("_") or not isinstance(entry, dict):
            continue
```

#### 取舍

- **全程吞异常**(`gateway/mirror.py:84-93`、`gateway/mirror.py:202-203`),
  返回 bool。镜像失败不影响发送成功。
- **模块级路径**(`gateway/mirror.py:21-22`):
  ```python
  _SESSIONS_DIR = get_hermes_home() / "sessions"
  _SESSIONS_INDEX = _SESSIONS_DIR / "sessions.json"
  ```
  在 import 时冻结,不跟随 `get_hermes_home()` 的 context-local profile override
  (override 机制见 `hermes_constants.py:114-131`)。多 profile 场景下回退路径会读错 profile 的索引。
  (主路径 state.db 走 `SessionDB()`,不受影响,所以影响面限于未迁移的老库。)
- **连接必关**:`_append_to_sqlite` 和 `_find_session_id` 都有 `finally: db.close()`
  (`gateway/mirror.py:129-130`、`gateway/mirror.py:204-206`),
  配套测试 `tests/gateway/test_mirror.py:122` `test_connection_is_closed_after_use`。

---

### 2.5 `gateway/rich_sent_store.py`(83 行)—— 补平台不回显的洞

#### 问题

`gateway/rich_sent_store.py:1-8 @ 863e313`:

```python
"""Local index of text we've sent via ``sendRichMessage`` (Bot API 10.1).

Telegram does NOT echo a rich message's content back in ``reply_to_message``
when a user replies to it (verified: ``.text``/``.caption`` empty,
``.api_kwargs`` None). So replies to the launchd briefings / any rich send
arrive with no quotable text and the agent is blind to what was referenced.
```

WhatsApp Cloud 同样(`gateway/platforms/whatsapp_cloud.py:2055-2058 @ 863e313`):

```python
        # context.id is set when the user replied to a prior message. Meta's
        # webhook only gives us the quoted message's id (and its author in
        # context.from) — never the quoted text. We resolve the text from
        # rich_sent_store, which we populate on every inbound message (below)
```

#### 缓存什么、键是什么

- **键**:`f"{chat_id}:{message_id}"`(`gateway/rich_sent_store.py:35-36`)
- **值**:`{"t": text[:2000], "ts": int(time.time())}`(`gateway/rich_sent_store.py:53-56`)
- **存储**:`<hermes_home>/state/rich_sent_index.json`(`gateway/rich_sent_store.py:27-32`),
  **懒解析** —— 注释显式说明:
  ```python
      # Resolve via get_hermes_home() so the active profile override is honored.
  ```
  这条被 profile 隔离测试盯着:`tests/test_profile_isolation_runtime.py:100-111`
  `TestRichSentStorePathResolution`。

#### 失效策略

只有**容量淘汰**,没有 TTL(`gateway/rich_sent_store.py:23-24, 57-62 @ 863e313`):

```python
_MAX_ENTRIES = 1000
_MAX_TEXT_CHARS = 2000
```
```python
        # Trim oldest by timestamp when over cap.
        if len(data) > _MAX_ENTRIES:
            for k, _ in sorted(
                data.items(), key=lambda kv: kv[1].get("ts", 0)
            )[: len(data) - _MAX_ENTRIES]:
                data.pop(k, None)
```

`ts` 只用于排序淘汰,不用于过期判定。

#### 并发

**原子替换 + 每进程独立临时文件**(`gateway/rich_sent_store.py:63-66 @ 863e313`):

```python
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, path)  # atomic; tolerates concurrent writers racing
```

注意:这是 **last-writer-wins**,不是无损合并。两个进程并发写会丢一方的新增条目。
对缓存语义可接受(丢了就是查不到引用原文,降级到"看不到引用")。

#### 取舍与命名漂移

- **全程吞异常**(`gateway/rich_sent_store.py:67-68`、`:81-82`),
  docstring 明说 "can never break a send or an inbound message"(`gateway/rich_sent_store.py:12-13`)。
- **每次 `record` 都全量读 + 全量写整个 JSON**。1000 条 × 2000 字符 ≈ 2MB 的读写,
  每条出站 rich 消息一次。这是明显的性能取舍(换来零依赖 + 无 schema 迁移)。
- **命名漂移**:模块叫 `rich_sent_store`、docstring 说 "text we've **sent**",
  但 `gateway/platforms/whatsapp_cloud.py:2094` 用它记录**入站**用户消息:
  ```python
            # Index this message's text by wamid so a later reply to it can
            # resolve the quoted text (Meta's webhook context carries only
            # the id). Mirrors the outbound record in send(). Best-effort.
            if body:
                rich_sent_store.record(chat_id, wamid, body)
  ```
  记为 ◇(见 §4)。

---

### 2.6 `gateway/sticker_cache.py`(124 行)—— 贴纸转文字的省钱缓存

#### 问题

`gateway/sticker_cache.py:1-9 @ 863e313`:

```python
"""
Sticker description cache for Telegram.

When users send stickers, we describe them via the vision tool and cache
the descriptions keyed by file_unique_id so we don't re-analyze the same
sticker image on every send. Descriptions are concise (1-2 sentences).
```

同一套贴纸会被反复发,每次都调视觉模型是纯浪费。

#### 缓存什么、键是什么

- **键**:`file_unique_id` —— Telegram 对同一张贴纸图跨 chat / 跨 bot **稳定**的标识符
  (`gateway/sticker_cache.py:81`:"Telegram's stable sticker identifier")。
  用 `file_id` 就不行(它是 per-bot 的)。
- **值**:`{"description", "emoji", "set_name", "cached_at"}`(`gateway/sticker_cache.py:86-91`)
- **存储**:`get_hermes_home() / "sticker_cache.json"`(`gateway/sticker_cache.py:20`)

#### 失效策略

**没有。** `cached_at` 被写入(`gateway/sticker_cache.py:90`)但全仓无任何读取点做过期判定
(grep `cached_at` 在本文件外只命中 `gateway/status.py` / `agent/model_metadata.py` 的无关变量)。
也没有条数上限。**这个缓存单调增长,永不淘汰。**
合理性:贴纸描述本身不会变;但缓存文件会随时间线性膨胀,且每次读写都是全量 JSON。

#### 写入原子性(比 rich_sent_store 更严)

`gateway/sticker_cache.py:42-59 @ 863e313`:

```python
    fd, tmp_path = tempfile.mkstemp(
        dir=str(CACHE_PATH.parent), suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(CACHE_PATH))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

有 `fsync`、有 `BaseException` 清理临时文件、**且 `_save_cache` 会抛**(不像 rich_sent_store 吞掉)。
调用侧 `plugins/platforms/telegram/adapter.py:9449` 在 try 块里,由外层兜住。

#### 注入文本(这是它的另一半职责)

不只是缓存,还负责把描述包装成给模型看的注入文本
(`gateway/sticker_cache.py:112-141 @ 863e313`):

```python
    return f"[The user sent a sticker{context}~ It shows: \"{description}\" (=^.w.^=)]"
```

动图/视频贴纸走另一条(`gateway/sticker_cache.py:119-128`):

```python
    if emoji:
        return (
            f"[The user sent an animated sticker {emoji}~ "
            f"I can't see animated ones yet, but the emoji suggests: {emoji}]"
        )
```

**注意语气**:`~`、`(=^.w.^=)` 是刻意的"warm-style"(`gateway/sticker_cache.py:101`)。
这是把人格风格硬编码进了基础设施层 —— 换人格时这句话不会跟着换。

调用链(`plugins/platforms/telegram/adapter.py:9400-9463`):
动图直接走占位符 → 查缓存命中直接用 → 未命中下载 + `vision_analyze_tool` + 写缓存 →
视觉失败降级成"a sticker with emoji X"(**降级结果不写缓存**,下次还会重试,
`plugins/platforms/telegram/adapter.py:9451-9456`)。

#### 取舍 / 缺陷

- **`CACHE_PATH` 是模块级常量**(`gateway/sticker_cache.py:20`):
  ```python
  CACHE_PATH = get_hermes_home() / "sticker_cache.json"
  ```
  在 import 时求值,**不跟随 profile override**。
  与 `rich_sent_store._store_path()` 的懒解析(`gateway/rich_sent_store.py:27-32`,并有
  `tests/test_profile_isolation_runtime.py:100` 专门守着)形成**同一切片内的直接矛盾**。
  同类问题也见 `gateway/mirror.py:21-22`。
- 缓存无上限、无 TTL。

---

### 2.7 `gateway/dead_targets.py`(143 行)—— 设计完整但已休眠

#### 问题

`gateway/dead_targets.py:1-10 @ 863e313`:

```python
"""Persistent registry of delivery targets that are confirmed unreachable.

When a messaging platform reports that a target chat is permanently gone — a
deleted group (``Forbidden: the group chat was deleted``), a bot kicked/blocked,
or a deactivated user — re-sending to it on every cron tick or every fan-out
delivery wastes a send attempt against the platform's flood-control envelope and
spams the logs.  This registry lets the delivery layer short-circuit a target it
has already proven dead, while staying self-healing: any successful send to that
target clears the flag, so a user who re-adds the bot (or restores the chat)
recovers automatically with no manual cleanup.
```

#### "死目标"如何判定

两级判定,**刻意收窄**。

**第一级:error_kind 白名单**(`gateway/dead_targets.py:40-42, 93-96 @ 863e313`):

```python
_DEAD_ERROR_KINDS = frozenset({"forbidden", "not_found"})
```
```python
    @staticmethod
    def is_dead_error_kind(error_kind: Optional[str]) -> bool:
        """Return True when ``error_kind`` denotes a permanent whole-chat death."""
        return bool(error_kind) and error_kind in _DEAD_ERROR_KINDS
```

**第二级:`not_found` 要再分血径**(`gateway/dead_targets.py:12-18`):

```python
Scope is deliberately narrow.  Only *whole-chat* deaths are recorded — the
``forbidden`` and chat-level ``not_found`` (``chat not found``) error kinds.
Thread/topic-level ``not_found`` is NOT recorded here: the adapters already
self-heal that by retrying without ``reply_to`` (see the Telegram adapter's
reply-target-deleted path), and a deleted topic does not mean the parent chat is
dead.
```

分界说明在 `gateway/platforms/base.py:2267-2273`,常量在 `gateway/platforms/base.py:2274-2281 @ 863e313`:

```python
_CHAT_LEVEL_NOT_FOUND_SUBSTRINGS = ("chat not found",)
_SUBCHAT_NOT_FOUND_SUBSTRINGS = (
    "message to edit not found",
    "message to reply not found",
    "thread not found",
    "topic_deleted",
    "message_id_invalid",
)
```

冲突时**保守方向:子级读法赢**(`gateway/platforms/base.py:2362-2363, 2369-2372 @ 863e313`):

```python
    both a chat-level and a sub-chat marker are present, the sub-chat reading wins
    (conservative: never kill a chat that may still be reachable).
```
```python
    blob = _error_blob(exc, error_text)
    if any(s in blob for s in _SUBCHAT_NOT_FOUND_SUBSTRINGS):
        return False
    return any(s in blob for s in _CHAT_LEVEL_NOT_FOUND_SUBSTRINGS)
```

`_error_blob`(`gateway/platforms/base.py:2284`)是两个分类器的共享输入,
docstring 明说是为了"can never drift ... and silently disagree on the same failure"。

#### 判定后做什么

**短路 + 记录**(`gateway/delivery.py:347-362 @ 863e313`):

```python
            if (
                target.platform != Platform.LOCAL
                and target.chat_id
                and self.dead_targets.is_dead(target.platform.value, target.chat_id)
            ):
                logger.info(
                    "Skipping delivery to known-dead target %s:%s "
                    "(send to it again to clear)",
                    target.platform.value, target.chat_id,
                )
```

不是"拉黑"也不是"退避" —— 是**永久跳过,直到一次成功发送清除**。

#### 误判怎么恢复

**自愈,零人工**(`gateway/delivery.py:368-370 @ 863e313`):

```python
                    # Successful platform delivery — clear any stale dead flag.
                    if target.chat_id and not _send_result_failed(result):
                        self.dead_targets.clear(target.platform.value, target.chat_id)
```

`clear` 实现(`gateway/dead_targets.py:127-138`)删掉键、落盘、打 info 日志。

**但这里有个逻辑闭环问题**:被标死的目标在 `deliver()` 里会被 `continue` 跳过(`gateway/delivery.py:362`),
**永远不会走到发送成功那一步**。所以"发送成功清除"这条自愈路径的触发条件是:
必须有**另一条不经过 `is_dead` 检查的路径**发成功。而 `deliver()` 是唯一读 `is_dead` 的地方,
`_deliver_to_platform`(cron 走的那条)不读 —— 所以 cron 成功发送**也不会清除**
(因为 cron 用的是 `_deliver_to_platform`,里面没有 `clear` 调用)。
日志文案 "send to it again to clear"(`gateway/delivery.py:354`)在当前代码里没有可达的实现路径。
**但这一切都是理论问题:`deliver()` 本身零生产调用(§3)。**

#### 存储与并发

- `get_hermes_home() / "gateway" / "dead_targets.json"`,**在 `__init__` 里解析**
  (`gateway/dead_targets.py:56-63`)—— 比模块级好,比懒解析差(registry 长期存活时仍是冻结的)。
- `threading.RLock`(`gateway/dead_targets.py:57`)保护内存 dict。
- 落盘走 tmp + `replace`(`gateway/dead_targets.py:81-89`),
  失败只 debug 日志:"Best-effort: keep the in-memory state, don't break delivery."
- 加载时过滤畸形条目(`gateway/dead_targets.py:72-75`):
  ```python
                    # Only keep well-shaped entries.
                    self._dead = {
                        k: v for k, v in raw.items() if isinstance(v, dict)
                    }
  ```
- 记录 `reason`(截断 200 字)+ `marked_at`,只为可观测(`gateway/dead_targets.py:112-117`)。
- 首次标记才打 info 日志(`gateway/dead_targets.py:119-125`),重复标记不刷屏。

#### 死代码

- **`all_dead()`(`gateway/dead_targets.py:140-143`)零调用点**,包括测试。
  docstring 说 "for diagnostics / `hermes` CLI",但 CLI 里没有对应命令。
- **`DeliveryRouter.__init__` 的 `dead_targets` 注入参数(`gateway/delivery.py:303`)
  没有任何生产调用方传值** —— 只有 `tests/gateway/test_dead_targets.py:92`
  `test_shared_registry_is_used_when_injected` 用。
  也就是说 docstring 里说的"shared registry"(`gateway/delivery.py:310-312`)
  在生产上从未共享:每个 `DeliveryRouter` 造一个自己的 registry,
  只通过同一个 JSON 文件间接共享(而且内存副本不会互相刷新)。

---

### 2.8 `gateway/runtime_footer.py`(181 行)—— 纯函数,唯一有配置合并的

#### 问题

想在每条最终回复末尾看到"这条是哪个模型答的、上下文用了多少、在哪个目录跑的"。
但默认不能加 —— 会污染每条聊天消息。

#### 页脚里放什么

四个字段(`gateway/runtime_footer.py:14-22 @ 863e313`):

```python
Available fields:
    model        — bare model id, vendor prefix dropped (``gpt-5.4``)
    context_pct  — last-call context occupancy as a percent (``5%``)
    latency      — wall-clock duration of the turn (``22s``, ``1m05s``)
    cwd          — home-relative working dir (``~``)

``latency`` is opt-in: it is NOT in the default field set, so a footer whose
``fields`` are unset renders exactly as before.
```

默认集合与分隔符(`gateway/runtime_footer.py:40-41`):

```python
_DEFAULT_FIELDS: tuple[str, ...] = ("model", "context_pct", "cwd")
_SEP = " · "
```

#### 什么条件下加

**三层配置合并**(`gateway/runtime_footer.py:71-103 @ 863e313`):

```python
    Merge order (later wins):
        1. Built-in defaults (enabled=False)
        2. ``display.runtime_footer``
        3. ``display.platforms.<platform_key>.runtime_footer``
```

`enabled` 和 `fields` **独立合并**(`gateway/runtime_footer.py:80-84, 91-95`):
平台层可以只覆盖 `enabled` 而继承全局的 `fields`。
`fields` 覆盖要求非空 list(`if isinstance(...) and global_cfg["fields"]`),
所以 `fields: []` 不会把字段清空,而是继承上层 —— 这是刻意的防手误。

`build_footer_line` 是唯一入口(`gateway/runtime_footer.py:151-181`),
`enabled` 为假直接返回 `""`(`gateway/runtime_footer.py:172-173`)。

#### 如何避免污染上下文

关键在**调用点**,不在本模块。`gateway/run.py:17784-17785 @ 863e313`:

```python
            if _footer_line and response and not agent_result.get("already_sent") and not _intentional_silence:
                response = f"{response}\n\n{_footer_line}"
```

四重门:有页脚 / 有正文 / **没被流式提前发过** / 不是故意静默。

流式已经把正文发出去了怎么办?**单独发一条尾巴消息**(`gateway/run.py:18159-18173 @ 863e313`):

```python
                # Streaming already delivered the body text, but the footer was
                # intentionally held back (see the `not already_sent` gate above).
                # Send it now as a small trailing message so Telegram/Discord/etc.
                # still surface the runtime metadata on the final reply.
                if _footer_line:
                    try:
                        _foot_adapter = self._adapter_for_source(source)
                        if _foot_adapter:
                            await _foot_adapter.send(
```

**注意:页脚是拼进 `response` 字符串再返回的,所以它会进入会话历史 —— 本模块不做任何隔离。**
"避免污染上下文"这件事,代码里的答案是"默认关 + 只在最终消息上加",不是"技术上隔离"。

#### 优雅降级

`format_runtime_footer`(`gateway/runtime_footer.py:120-157 @ 863e313`):

```python
    """Render the footer line, or return "" if no fields have data.

    Fields are skipped silently when their underlying data is missing — a
    partially-populated footer is better than a line with ``?%`` or empty slots.
    """
```

- `context_pct` 需要 `context_length > 0`,结果 clamp 到 0-100(`gateway/runtime_footer.py:131-134`)
- `latency` 需要 `turn_seconds is not None and >= 0`(`gateway/runtime_footer.py:135-139`)
- `cwd` 回退到 `TERMINAL_CWD` 环境变量(`gateway/runtime_footer.py:140-143`)
- 未知字段名静默忽略(`gateway/runtime_footer.py:144`)
- 全空返回 `""`(`gateway/runtime_footer.py:146-147`)

`_format_latency`(`gateway/runtime_footer.py:100-108`):`<1s` / `22s` / `1m05s`。
`_model_short`(`gateway/runtime_footer.py:58-62`):`rsplit("/", 1)[-1]`。
`_home_relative_cwd`(`gateway/runtime_footer.py:44-55`):`$HOME` 折成 `~`,异常返回原值。

#### 运行时开关

`/footer` slash 命令(`gateway/slash_commands.py:3862-3946`),
支持 `on|off|status|?` 和裸 `/footer`(切换),写回 `display.runtime_footer.enabled` 全局键
(`gateway/slash_commands.py:3925-3928`),**明确不改平台级覆盖**
(`gateway/slash_commands.py:3873-3875`)。开启后用 `format_runtime_footer` 渲染一个预览
(`gateway/slash_commands.py:3937-3944`)。

37 个测试(`tests/gateway/test_runtime_footer.py`,全仓本切片最多)。

#### 取舍 / 命名漂移

- **本模块是纯函数,零 I/O、零状态**。配置由调用方传入(`user_config: dict`),
  这让它极易测试(37 个测试无一需要 mock 文件系统)。
- **docstring 引用了不存在的函数**:`gateway/runtime_footer.py:32-34`:
  ```python
  ``send_trailing_footer()``.
  ```
  全仓 grep `send_trailing_footer` 只命中这一行 docstring。实际逻辑内联在
  `gateway/run.py:18163-18173`。记为 ▲(见 §4)。

---

### 2.9 `gateway/streaming_tts_consumer.py`(423 行)—— 边生成边说话

#### 问题

用户发了条语音,期待听到语音回复。老做法:等 LLM 全部生成完 → 整段文本转语音 →
发一个音频文件。首字节延迟 = 整个生成时间 + 整段合成时间,几十秒起步。

新做法:**LLM 吐一句就合成一句、播一句**。

#### 与 `stream_consumer.py`(文本流)的关系

**并联,不是串联。** 同一个 `stream_delta_callback` 被 tee 到两个消费者
(`gateway/run.py:4525-4531 @ 863e313`):

```python
                    if _want_stream_deltas:
                        def _stream_delta_cb(text: str) -> None:
                            if ctx._run_still_current():
                                _stream_consumer.on_delta(text)
                                # Tee to the streaming-TTS consumer (#60671).
                                if _stts_consumer_ref is not None:
                                    _stts_consumer_ref.on_delta(text)
```

文本流关闭时,还会单独装一个 TTS-only 回调(`gateway/run.py:4536-4542 @ 863e313`):

```python
        # When text streaming is off but streaming TTS is active,
        # install a TTS-only delta callback so the consumer still
        # receives LLM deltas for audio synthesis (#60671).
        if _stream_delta_cb is None and _stts_consumer_ref is not None:
            def _stream_delta_cb(text: str) -> None:
                if ctx._run_still_current():
                    _stts_consumer_ref.on_delta(text)
```

**两者结构对称但目标不同**:文本流消费者不断 **edit** 同一条消息;
TTS 消费者不断 **write** PCM 字节到一个流式音频句柄。

**触发条件三重门**(`gateway/run.py:24805-24810 @ 863e313`):

```python
        if (
            _stts_adapter is not None
            and _is_voice_input
            and _stts_adapter._should_auto_tts_for_chat(source.chat_id)
        ):
```

语音输入 + 该 chat 开了 auto-TTS + 适配器存在。第四重门在消费者内部:
`resolve_streaming_provider` 返回 None 则 `active == False`,holder 不装
(`gateway/run.py:24822-24826`)。

#### 线程模型(这是本文件的骨架)

```
Agent 工作线程                 Gateway 事件循环
─────────────                 ─────────────────
on_delta(text)   ──►  queue.Queue(maxsize=256)  ──►  _run() 抽干
  (同步, 不阻塞)                 (线程安全)              (async)
  SentenceChunker.feed()                              合成 + 写 PCM
```

设计说明(`gateway/streaming_tts_consumer.py:19-25 @ 863e313`):

```python
- ``on_delta`` is synchronous and never blocks the agent thread. It feeds
  deltas into a ``SentenceChunker`` and queues completed clauses onto a
  thread-safe ``queue.Queue``.
- An asyncio task (``run``) runs on the gateway event loop, draining the
  queue, synthesising each clause via a ``StreamingTTSProvider``, and
  writing PCM chunks to the adapter.
- Per-turn state is isolated: each consumer instance owns its own chunker,
  queue, handle, and flags. Concurrent chats cannot cross-contaminate.
```

同步阻塞调用全部用 `asyncio.to_thread` 卸载:
- 队列取(`gateway/streaming_tts_consumer.py:249`):`await asyncio.to_thread(self._queue.get, True, 0.1)`
- provider 迭代(`gateway/streaming_tts_consumer.py:340-349`):
  ```python
      async def _iter_stream_chunks(self, text: str):
          """Yield provider PCM chunks one at a time without blocking the loop."""
          if self._streamer is None:
              return
          iterator = iter(self._streamer.stream(text))
          while True:
              has_chunk, chunk = await asyncio.to_thread(self._next_stream_chunk, iterator)
  ```
  用 `_next_stream_chunk`(`gateway/streaming_tts_consumer.py:351-356`)把同步生成器
  一次一格地喂进线程池 —— 这是"同步迭代器变异步"的标准手法。

#### 怎么切句

用共享的 `SentenceChunker`(`tools/tts_streaming.py:89-124 @ 863e313`),
边界正则(`tools/tts_streaming.py:84-86`):

```python
# Sentence boundary: after .!? followed by whitespace, or a blank line.
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])(?:\s|\n)|(?:\n\n)")
_THINK_BLOCK_RE = re.compile(r"<think[\s>].*?</think>", flags=re.DOTALL)
```

三个关键处理(`tools/tts_streaming.py:103-118 @ 863e313`):

```python
    def feed(self, delta: str) -> List[str]:
        """Absorb *delta*; return every complete sentence now ready to speak."""
        self.buf = _THINK_BLOCK_RE.sub("", self.buf + delta)
        if "<think" in self.buf and "</think>" not in self.buf:
            return []  # open think tag — the closing tag may arrive next delta
        out: List[str] = []
        start = 0  # skip boundaries that would leave the head too short
        while m := SENTENCE_BOUNDARY_RE.search(self.buf, start):
            head = self.buf[: m.end()]
            if len(head.strip()) < self.min_len:
                start = m.end()
                continue
```

1. **剥 `<think>` 块**,且跨 delta 的未闭合 think 标签会整体憋住;
2. **短碎片合并**(`min_len=20`,`tools/tts_streaming.py:99`):"Ha!" 不会单独合成一个小音频片,
   而是跟着下一句一起走(docstring `tools/tts_streaming.py:94-96` 明说);
3. `flush()` 收尾抽干残余(`tools/tts_streaming.py:120-124`)。

合成前再剥一次 markdown(`gateway/streaming_tts_consumer.py:358-366`),
懒 import `tools.tts_tool._strip_markdown_for_tts` 避免循环依赖,ImportError 时退化成恒等函数。

#### 失败回落:三态语义(本文件的核心设计)

`gateway/streaming_tts_consumer.py:27-36 @ 863e313`:

```python
- On successful completion (all clauses synthesised and written), the
  consumer reports ``completed=True`` so the gateway can suppress the
  duplicate whole-file auto-TTS.
- On failure before any audible output, the consumer reports
  ``completed=False`` and clears ``suppress_whole_file`` so the gateway can
  fall back to whole-file TTS.
- On failure after partial audible output, the consumer reports
  ``completed=False`` but keeps ``suppress_whole_file=True`` so the gateway
  does NOT replay the whole response from the beginning.
```

**关键洞见:回落的判据不是"成功/失败",而是"用户耳朵里已经进去声音了没有"。**
一旦有声音出来过,整段重播比不播更糟。

`audible` 标志在**第一个 PCM 块写成功后**才置位(`gateway/streaming_tts_consumer.py:334-338 @ 863e313`):

```python
            was_audible = self._handle.audible
            await self._adapter.write_streaming_tts(self._handle, chunk)
            if not was_audible:
                self._handle.audible = True
                self._suppress_whole_file = True
```

先写、再置位 —— 写抛异常就不算 audible。

收尾四分支(`gateway/streaming_tts_consumer.py:283-306 @ 863e313`):

```python
                if _finish_failed:
                    # finish_streaming_tts() raised — never report full
                    # completion.  If audio was already audible, report
                    # partial and preserve suppression so the gateway
                    # does not replay from the beginning.  If no audio
                    # was audible, permit whole-file fallback.
                    if self._handle.audible:
                        self._partial = True
                        self._completed = False
                        self._suppress_whole_file = True
                    else:
                        self._completed = False
                        self._suppress_whole_file = False
                    await self._safe_abort("finish_streaming_tts failed")
                elif self._handle.audible and not self._dropped:
                    self._completed = True
                    self._suppress_whole_file = True
                elif self._handle.audible and self._dropped:
                    self._partial = True
                    self._completed = False
                    self._suppress_whole_file = True
                else:
                    self._completed = False
                    self._suppress_whole_file = False
```

`_dropped`(队列溢出丢过句子)会把"完整"降级为"部分" —— 音频缺了一句就不算完整,
但也不重播。

单句合成失败走同样的判据(`gateway/streaming_tts_consumer.py:264-274`)。

#### 哨兵不能丢(#60671 加固)

队列有界(`maxsize=256`,`gateway/streaming_tts_consumer.py:91`),满了会 `queue.Full`。
但 `_DONE` / `_ABORT` 哨兵**必须**到达,否则 drain 循环永远不退出。

`_DONE`(`gateway/streaming_tts_consumer.py:189-205 @ 863e313`):

```python
        # Guarantee the _DONE sentinel reaches the queue.  If the bounded
        # queue is full, drain one item to make room — the sentinel is
        # load-bearing and must not be lost (#60671 hardening).
        self._enqueue_done()

    def _enqueue_done(self) -> None:
        """Enqueue the _DONE sentinel, evicting a queued clause if necessary."""
        while True:
            try:
                self._queue.put_nowait(_DONE)
                return
            except queue.Full:
                try:
                    self._queue.get_nowait()
                    self._dropped = True
                except queue.Empty:
                    continue
```

**无限循环 + 强制腾位**。腾出来的位置是丢一句台词 —— 并且诚实地记 `_dropped = True`。

`_ABORT`(`gateway/streaming_tts_consumer.py:393-406 @ 863e313`)用**有限 3 次**尝试:

```python
        for _attempt in range(3):
            try:
                self._queue.put_nowait(_ABORT)
                break
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
        else:
            logger.debug("streaming TTS _ABORT sentinel could not be enqueued")
```

不对称的原因:abort 路径同时把 `self._aborted = True` 置位
(`gateway/streaming_tts_consumer.py:386-389`),drain 循环每轮都检查 `self._aborted`
(`gateway/streaming_tts_consumer.py:246-247, 259-260`),哨兵只是"快速唤醒"手段,丢了也能退出。
`_DONE` 没有这个替代路径,所以必须保证送达。

#### 幂等取消

`abort()`(`gateway/streaming_tts_consumer.py:386-413`)加锁做 test-and-set:

```python
        with self._lock:
            if self._aborted:
                return
            self._aborted = True
```

跨线程调用适配器 abort 用 `call_soon_threadsafe`(`gateway/streaming_tts_consumer.py:404-411`)。
`_safe_abort`(`gateway/streaming_tts_consumer.py:368-378`)吞掉所有异常,
`finally` 里一定置 `handle.aborted = True`。

生产 abort 触发点:三处 barge-in(用户插话)
`gateway/run.py:24954`、`gateway/run.py:25241`、`gateway/run.py:25343`;
一处 finalisation 超时 `gateway/run.py:25468`;一处 cleanup `gateway/run.py:25821`。

#### 收尾编排在调用方

`gateway/run.py:25457-25482 @ 863e313`:

```python
            _stts = streaming_tts_consumer_holder[0]
            if _stts is not None:
                _stts.finish()
                try:
                    await _stts.wait_complete(timeout=10.0)
                except Exception as _stts_done_err:
                    logger.debug("streaming TTS wait_complete error: %s", _stts_done_err)
                if not _stts.done:
                    # Timeout before or after audible audio: abort to free
                    # the consumer task.  Audible streams retain suppression;
                    # silent streams remain eligible for whole-file fallback.
                    _stts.abort("streaming TTS finalisation timeout")
                    await _stts.wait_complete(timeout=2.0)
                if _stts.suppress_whole_file and adapter is not None:
                    _mark_turn = getattr(adapter, "_mark_streaming_tts_completed_turn", None)
                    if callable(_mark_turn):
                        _mark_turn(session_key, run_generation)
```

`finish()` 在**事件循环线程**调,注释说明理由(`gateway/run.py:25450-25452`):
"so early returns from run_sync are also finalised"。

`wait_complete`(`gateway/streaming_tts_consumer.py:413-423 @ 863e313`)用
`asyncio.shield` 包住 task,超时不杀 task:

```python
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        except Exception:
            pass
        return self._completed
```

最终由 `_mark_streaming_tts_completed_turn` 打标,整文件 TTS 兜底路径读它
(`gateway/run.py:18129-18134`)决定跳过。

#### 取舍

- **构造时 `from tools.tts_streaming import ...` 在函数体内**
  (`gateway/streaming_tts_consumer.py:68`)—— 避免 gateway 启动时强依赖 TTS 栈。
- **音频格式由 provider 决定,不由适配器决定**(`gateway/streaming_tts_consumer.py:81-88`):
  ```python
          if self._streamer is not None:
              self._audio_format = AudioFormat(
                  sample_rate=int(getattr(self._streamer, "sample_rate", AudioFormat.sample_rate)),
  ```
  没有 provider 时才用传入的 `audio_format` 或默认值。适配器只能 `supports_streaming_tts(chat_id, fmt)`
  接受或拒绝(`gateway/streaming_tts_consumer.py:223-225`),**不能协商**。
- **`_run()` 的 `finally` 抽干队列**(`gateway/streaming_tts_consumer.py:310-315`),
  防止 agent 线程还在往里塞时对象无法回收。
- **`on_delta` 的三个短路条件**(`gateway/streaming_tts_consumer.py:158-159`):
  `self._aborted or not self.active or self._finished` —— finish 之后来的 delta 直接丢。

---

## 3. 接线核查表(生产调用点,排除 `tests/`)

| 文件 | 生产调用点 | 结论 |
|---|---|---|
| `gateway/delivery.py` | `gateway/__init__.py:19`(re-export)<br>`gateway/run.py:2364-2367` import `DeliveryRouter` / `looks_like_telegram_private_chat_id` / `resolve_delivery_transport`<br>`gateway/run.py:5935` 构造 router<br>`gateway/run.py:11744`, `21189`, `21270` 用 `resolve_delivery_transport`<br>`gateway/run.py:11797` 用 `looks_like_telegram_private_chat_id`<br>`cron/scheduler.py:1594-1596` `resolve_delivery_transport`<br>`cron/scheduler.py:1750-1754, 1806, 1819` 构造 router + 调 `_deliver_to_platform` | **部分休眠**。模块级函数活跃;`DeliveryRouter` 类本身只有 `_deliver_to_platform`(私有)被 cron 调用 |
| `DeliveryRouter.deliver()` | **无**(全仓 `.deliver(` 只命中 `tests/gateway/test_dead_targets.py:79/85/102`) | **休眠** |
| `DeliveryRouter._deliver_local()` | **无**(只被 `deliver()` 调,`gateway/delivery.py:365`) | **不可达** |
| `DeliveryTarget.parse()` | **无**(cron 用构造函数 `cron/scheduler.py:1807`,不用 parse) | **休眠** |
| `DeliveryTarget.to_string()` | 只在 `deliver()` 内(`gateway/delivery.py:357/372/386`) | **不可达** |
| `self.delivery_router`(run.py) | `gateway/run.py:5935` 构造;`:7323`, `:11348`, `:12488` 三处 **只赋值 `.adapters`,从不调用任何方法** | **休眠对象**:被精心维护但从不使用 |
| `gateway/delivery_ledger.py` | `gateway/platforms/base.py:6062-6087`(record + attempting)、`:6100-6113`(delivered/failed)<br>`gateway/run.py:10361-10369`(sweep,由 `:11447` 触发) | **活跃** |
| `delivery_ledger.debug_rows()` | **无**(仅 `tests/gateway/test_delivery_ledger.py:246`、`test_delivery_ledger_fd_leak.py:79`) | 调试工具,可接受 |
| `gateway/response_filters.py` | `gateway/stream_consumer.py:35-37`(→`:849`, `:888`)<br>`gateway/run.py:17612-17613`, `25622-25623`<br>`gateway/platforms/webhook.py:66, 97`<br>`cron/scheduler.py:323-325` | **活跃** |
| `response_filters.SILENT_REPLY_TOKEN` | **无**(全仓仅定义行 `gateway/response_filters.py:14`) | **死常量** |
| `gateway/mirror.py` | `cron/scheduler.py:717`, `851`, `949`<br>`tools/send_message_tool.py:507` | **活跃** |
| `gateway/rich_sent_store.py` | `plugins/platforms/telegram/adapter.py:1940`, `2028`, `9771`<br>`gateway/platforms/whatsapp_cloud.py:82, 587, 2067, 2098` | **活跃**(两个平台) |
| `gateway/sticker_cache.py` | `plugins/platforms/telegram/adapter.py:9408`(唯一) | **活跃**(单平台) |
| `gateway/dead_targets.py` | 只被 `gateway/delivery.py:59` import;三个调用点 `gateway/delivery.py:350`, `370`, `382` **全在 `deliver()` 里** | **完全休眠**(随 `deliver()` 一起不可达) |
| `dead_targets.all_dead()` | **无**(含测试) | **死代码** |
| `gateway/runtime_footer.py` | `gateway/run.py:17771`(`build_footer_line`)<br>`gateway/slash_commands.py:3877`(`resolve_footer_config`)、`:3937`(`format_runtime_footer`) | **活跃** |
| `gateway/streaming_tts_consumer.py` | `gateway/run.py:24811-24824`(构造 + start)<br>`gateway/run.py:4531`, `4542`(on_delta tee)<br>`gateway/run.py:24954`, `25241`, `25343`(barge-in abort)<br>`gateway/run.py:25459-25473`(finish/wait/abort)<br>`gateway/run.py:25821-25823`(cleanup) | **活跃** |

### 休眠结论

**三处休眠**,严重程度递减:

1. **`DeliveryRouter.deliver()` + `dead_targets.py` 整体**(约 143 + 100 行)。
   `dead_targets.py` 是一个完整、有持久化、有并发保护、有 10 个测试的模块,
   但它唯一的接入点(`deliver()`)在生产上从未被调用。
   这与 R7 发现的 `memory_monitor.py` 同型:**有测试 ≠ 有生产接线**。
   cron 走的是私有 `_deliver_to_platform`,绕过了整个 dead-target 层。
2. **`self.delivery_router`**(`gateway/run.py:5935`)—— 一个被三处代码认真维护
   (每次适配器变动都同步 `.adapters`)却从不调用的对象。这比纯死代码更危险:
   它看起来是活的,维护者会继续维护它。
3. **`SILENT_REPLY_TOKEN`**、**`all_dead()`** —— 单点死符号,无害。

---

## 4. ▲ / ◇ 候选

约定:**▲ = 文档与代码矛盾;◇ = 代码有而文档无。** 双侧证据。

### ▲-1 cron 文档说 `[SILENT]` 是"contains",代码是位置敏感的

- **文档**:`website/docs/user-guide/features/cron.md:440 @ 863e313`
  > If the agent's final response **contains** `[SILENT]`, delivery is suppressed entirely.
- **代码**:`gateway/response_filters.py:83-84 @ 863e313`
  ```python
      ``[SILENT] No changes detected`` pattern).  A token buried mid-sentence
      in a genuine report is still delivered.
  ```
  实现三种命中形态(整串 / 独占首末行 / `[SILENT]` 同行前缀,
  `gateway/response_filters.py:98-110`),**中间出现不命中**。
- **定案**:以代码为准。文档的 "contains" 会让用户以为在报告正文里提一句 `[SILENT]` 就会静默,
  实际不会。

### ▲-2 `runtime_footer` docstring 引用了不存在的函数

- **docstring**:`gateway/runtime_footer.py:31-33 @ 863e313`
  ```python
  piecemeal, the footer is sent as a separate trailing message via
  ``send_trailing_footer()``.
  ```
- **代码**:全仓 grep `send_trailing_footer` 只命中这一行 docstring。
  实际逻辑内联在 `gateway/run.py:18163-18173`,没有具名函数。
- **定案**:命名漂移。行为描述正确(确实是单独一条尾巴消息),函数名是幻觉/遗留。

### ▲-3 配置文档的页脚示例含代码不支持的字段

- **文档**:`website/docs/user-guide/configuration.md:1786-1788 @ 863e313`
  ```
  — claude-opus-4.7 · 12 tool calls · 2m 14s · $0.042
  ```
- **代码**:`gateway/runtime_footer.py:126-144 @ 863e313` 只实现四个字段
  `model` / `context_pct` / `latency` / `cwd`;
  `_SEP = " · "`(`gateway/runtime_footer.py:41`)但没有前导 `— `;
  没有 "tool calls" 分支,没有成本分支。
  同一页 `configuration.md:1773-1778` 的字段表格是**正确的**(只列四个字段)。
- **定案**:示例块过时 / 与同页表格自相矛盾。实际渲染形如 `gpt-5.4 · 5% · ~`。

### ▲-4 cron-internals 说"cron 投递不镜像",实际有开关且默认关但存在

- **文档 A**:`website/docs/developer-guide/cron-internals.md:272 @ 863e313`
  > Cron deliveries are NOT mirrored into gateway session conversation history.
  > They exist only in the cron job's own session. This prevents message
  > alternation violations in the target chat's conversation.
- **文档 B(同仓另一处)**:`website/docs/user-guide/features/cron.md:361-362 @ 863e313`
  ```yaml
  cron:
    mirror_delivery: false   # set true to make cron deliveries continuable
  ```
- **代码**:`cron/scheduler.py:727`、`:858`、`:951` 三处调
  `gateway.mirror.mirror_to_session`,开关读取在 `cron/scheduler.py:640-648 @ 863e313`:
  ```python
      per_job = job.get("attach_to_session")
      if isinstance(per_job, bool):
          return per_job
      try:
          if cfg is None:
              cfg = load_config() or {}
          return bool((cfg.get("cron", {}) or {}).get("mirror_delivery", False))
  ```
- **定案**:cron-internals 是**过时的绝对陈述**。真实语义:默认不镜像(`mirror_delivery: false`),
  但可以开;开了之后用 `role="user"` + `[Cron delivery: ...]` 前缀避免交替违规
  —— 恰好就是 cron-internals 声称"通过不镜像来避免"的那个问题,现在用另一种方式解决了。

### ▲-5 scheduler docstring 说 "assistant turn",代码传 `role="user"`

- **docstring**:`cron/scheduler.py:633-635 @ 863e313`
  > the cron's final output is appended to the target session as an **assistant
  > turn** via the existing ``gateway.mirror.mirror_to_session``
- **代码**:`cron/scheduler.py:719 @ 863e313` 注释
  "Mirror as a USER turn with a labelled prefix, NOT an assistant turn.";
  三个调用点分别在 `:734`、`:865`、`:958` 传 `role="user"`。
- **定案**:同文件内 docstring 未随 #2221 的修复更新。文档 `website/docs/user-guide/features/cron.md:378` 反而是对的
  ("written as a labelled user turn")。

### ◇-1 `gateway.filter_silence_narration` / `HERMES_FILTER_SILENCE_NARRATION` 完全没文档

- **代码**:`gateway/delivery.py:448-458`(读取)、`gateway/config.py:911`(字段定义,默认 True)、
  `gateway/config.py:1202-1203, 1401-1407`(YAML 桥接)、`hermes_cli/config.py:1873`(顶层键白名单)。
- **文档**:`website/docs/` + `README.md` + `AGENTS.md` grep
  `filter_silence_narration` / `HERMES_FILTER_SILENCE` → **零命中**。
- 连带整个"静默叙述过滤"机制(`*(silent)*`、🔇、`.`、`…` 的丢弃)在文档里不存在。
  用户看到 bot 不回一个 "." 会完全不知道发生了什么。

### ◇-2 `dead_targets` 机制无任何文档

- **代码**:`gateway/dead_targets.py` 整个模块 + `gateway/platforms/base.py:2266-2281`。
- **文档**:grep `dead.target` / "group chat was deleted" 在 `website/docs/` → 零命中。
- 加重情节:它同时还是休眠的(§3),所以"文档没写"某种意义上是对的。

### ◇-3 `rich_sent_store` 的实际用途超出其名字与 docstring

- **docstring**:`gateway/rich_sent_store.py:1` "Local index of text we've **sent** via
  ``sendRichMessage`` (Bot API 10.1)"。
- **代码**:`gateway/platforms/whatsapp_cloud.py:2094-2098` 用它索引**入站**用户消息:
  ```python
              # Index this message's text by wamid so a later reply to it can
              # resolve the quoted text (Meta's webhook context carries only
              # the id). Mirrors the outbound record in send(). Best-effort.
              if body:
                  rich_sent_store.record(chat_id, wamid, body)
  ```
  且与 Telegram 的 `sendRichMessage` 无关(WhatsApp Cloud 没有那个 API)。
- **定案**:模块已演化成"平台不回显引用原文时的通用文本索引",名字和 docstring 落后于用途。
- 文档侧:`website/docs/` 对该索引零提及。

### ◇-4 `sticker_cache` 的 profile 隔离缺陷(代码内部矛盾,非文档)

- `gateway/sticker_cache.py:20`:`CACHE_PATH = get_hermes_home() / "sticker_cache.json"` —— **模块级**
- `gateway/rich_sent_store.py:27-30`:同一切片、同类模块,**显式懒解析**并注明
  "so the active profile override is honored",还有 `tests/test_profile_isolation_runtime.py:100` 守着
- `gateway/mirror.py:21-22`:同样是模块级冻结
- `get_hermes_home()` 是 context-local 可覆盖的(`hermes_constants.py:114-131`)
- **定案**:同一子系统内三种解析时机(模块级 / 构造时 / 调用时),
  多 profile 网关下 `sticker_cache` 与 `mirror` 的回退路径会串 profile。

### ◇-5 `state.db` 里多了一张 `delivery_obligations` 表,文档只讲行为不讲存储

- 文档 `website/docs/user-guide/messaging/index.md:235-251` 讲得挺完整(4 条语义 + 3 次/24h/7 天边界 + 开关),
  这是本切片文档质量最好的一处,**与代码一致**(逐条核对:
  `gateway/delivery_ledger.py:61-64`、`:24-31`、`:68-71`、`hermes_cli/config_defaults.py:2463`)。
- 未提及的:表在共享的 `state.db`(`gateway/delivery_ledger.py:74-75`)、
  500 行硬上限(`gateway/delivery_ledger.py:64`)、
  slash-command / ephemeral 回复不记账(`gateway/platforms/base.py:6055-6056`)。
- 归为 ◇(轻微),文档主体是准确的。

---

## 5. issue 溯源

### #58818 / #41696 / #63695 —— 最终回复在 crash 中静默丢失

- **出处**:`gateway/delivery_ledger.py:3-7 @ 863e313`
- **什么输入**:一次正常的 agent 对话轮,模型已经生成完最终回复。
- **什么现象**:网关在"回复生成完"和"平台确认收到"之间崩溃/重启,用户永远收不到回复,
  且没有任何痕迹 —— 日志里看不出丢了东西。
- **为什么**:那段文本此刻**只存在于一个 Python 局部变量里**。token 已经花掉了,
  会话历史可能已经写了,但字符串本身随进程一起蒸发。
  (`gateway/delivery_ledger.py:4-6`:"the turn already burned its tokens, the text exists
  only in a Python local")
- **怎么修**:发送前把 `(session_key, platform, chat_id, thread_id, content)` 写进
  `state.db` 的 `delivery_obligations` 表,发送后销账;下次开机 sweep 未销账的行重发。
  `gateway/run.py:11442-11448` 把 redelivery 排在 resume 之前,理由是
  "redelivering it ... is strictly cheaper and more correct than re-running the whole turn"。
- 另一处引用:`gateway/run.py:26334`。

### #61790 —— 更早的 delivery-outbox 方案被契约评审毙掉

- **出处**:`gateway/delivery_ledger.py:20-23 @ 863e313`
- **什么现象**:早先有一版 outbox,崩溃后会**静默重发**处于歧义状态的消息。
- **为什么被毙**:平台可能已经收到了,静默重发 = 用户看到两条一模一样的回复,
  而且无从判断哪条是重复。
- **怎么修**:改成"诚实的 at-least-once" —— 歧义状态(`attempting` / `failed`)重发时
  加可见前缀 `♻️ Recovered reply — the gateway restarted during delivery, so this may be
  a duplicate:`(`gateway/delivery_ledger.py:68-71`);只有 `pending`(确定没发出去)
  才裸重发。
- **可迁移原则**:分布式投递做不到 exactly-once,那就**把不确定性显式暴露给人**,
  而不是替人猜。

### #69567 / PR #69594 —— sqlite 连接泄漏耗尽文件描述符

- **出处**:`gateway/delivery_ledger.py:117-126 @ 863e313`(cron ledger 是同型 bug 的兄弟)
- **什么输入**:长时间运行的网关,每条最终回复触发一次 `record_obligation`。
- **什么现象**:`RLIMIT_NOFILE` 耗尽,网关开不了新文件/新连接。
- **为什么**:`with sqlite3.connect(...) as conn:` 的 `__exit__` **只提交事务,不关连接**。
  连接和它的 WAL/SHM 文件描述符要等 GC 才释放。
  `record_obligation` 是全网关最高频的写入点(每条最终回复一次),所以这里泄漏最快。
  (`gateway/delivery_ledger.py:125-126`:"``record_obligation`` runs on every outbound
  final response, so this ledger is the highest-frequency leaker.")
- **怎么修**:自建 `@contextmanager _transaction()`,`finally: conn.close()`
  (`gateway/delivery_ledger.py:127-132`);并在 `_connect()` 里补一个
  "DDL 失败时先关连接再抛"的守卫(`gateway/delivery_ledger.py:82-88`)。
  回归测试 `tests/gateway/test_delivery_ledger_fd_leak.py`。
- 同一 bug class 另有 `gateway/readiness.py:38` 提到 `#69678/#69567`。

### #2221 —— cron 镜像用 assistant 角色打断严格交替

- **出处**:`gateway/mirror.py:44-51 @ 863e313`;修复侧注释 `cron/scheduler.py:719-726`
- **什么输入**:一个开了 `mirror_delivery` 的 cron 简报,投到用户的某个 chat。
- **什么现象**:该 chat 的下一轮对话在严格交替的 provider 上直接报错。
- **为什么**:镜像消息构造时带了 `mirror: True` / `mirror_source` 标记
  (`gateway/mirror.py:71-77`),但 `_append_to_sqlite` 只持久化 role + content
  (`gateway/mirror.py:197-201`)—— **标记在持久化边界被丢掉**。
  重放时这条 assistant-role 镜像与真正的 assistant 轮无法区分,
  落在 agent 上一轮 assistant 之后就是 `assistant → assistant`。
- **怎么修**:cron 侧改传 `role="user"`,并在文本前加 `[Cron delivery: <name>]` 标签
  把"这不是 agent 说的"的信息编码进 **content 本身**(因为只有 content 会活下来)。
  连续的 user 轮会被 `repair_message_sequence` 安全合并。
  `gateway/mirror.py:49` 提到 "the exact failure #2313 removed" —— #2313 是上一次尝试。
- **可迁移原则**:**元数据会在某个持久化边界被丢掉;真正必须活下来的信息要编码进主数据本身。**

### #9006 —— 会话查找从 sessions.json 迁到 state.db

- **出处**:`gateway/mirror.py:105-106 @ 863e313`
  ```python
      Queries state.db gateway session rows (primary source since #9006);
      falls back to scanning sessions.json for pre-migration databases.
  ```
- 主路径 `gateway/mirror.py:115-133`,回退路径 `gateway/mirror.py:135-187`。
  回退路径至今保留(向后兼容老库)。

### #60671 —— 流式 TTS 引入 + 哨兵丢失加固

- **出处**:`gateway/streaming_tts_consumer.py:191`、`:392`;
  `gateway/run.py:4475`, `4529`, `4538`, `5453`, `18129`, `24727`, `24792`,
  `24951`, `25238`, `25340`, `25448`, `25686`, `25725`, `25817`;
  测试侧 `tests/gateway/test_streaming_tts_consumer.py:1`(docstring 标注 #60671)
- **什么输入**:一次语音输入,agent 生成一段长回复,LLM 吐 delta 很快。
- **什么现象**(哨兵部分):有界队列(256)被塞满,`finish()` 里 `put_nowait(_DONE)`
  抛 `queue.Full` 被吞掉 → drain 循环收不到终止信号 → **TTS 任务永远不结束**,
  `wait_complete` 每次超时 10 秒,整段音频卡住。
- **为什么**:哨兵和数据走同一个有界队列,数据把哨兵挤掉了。
- **怎么修**:`_enqueue_done()`(`gateway/streaming_tts_consumer.py:194-205`)
  循环强推,队列满就 `get_nowait()` 丢一句台词腾位,并记 `_dropped = True`
  (后续把"完整"降级为"部分",`gateway/streaming_tts_consumer.py:300-303`)。
  `_ABORT` 用有限 3 次(`gateway/streaming_tts_consumer.py:393-403`),因为它有
  `self._aborted` 标志作为备用唤醒路径。
- 另一半 #60671 内容:**consumer 必须在事件循环线程创建**,不能在 executor worker 里
  (`gateway/run.py:24793-24797`),否则外层 interrupt / finalisation 路径引用
  `streaming_tts_consumer_holder[0]` 时 NameError。回归测试
  `tests/gateway/test_streaming_tts_consumer.py:646`
  ("Real gateway regression: no _streaming_tts_consumer NameError (#60671)")
  与整文件 `tests/gateway/test_streaming_tts_gateway_regression.py`。
- **可迁移原则**:**控制信号不要和数据挤同一个有界通道;真要挤,就给控制信号"抢占权"
  并把牺牲(丢数据)记成显式状态。**

### 其它被引用的编号(在我的切片里只作背景)

- `#22773`、`#52060`、`#38922`(`cron/scheduler.py:1740-1750, 1798-1802, 1840-1855`)—— Telegram
  三态话题路由与 cron live-adapter 超时语义,直接影响 `delivery.py:554-605` 的分支为何这么写。

---

## 6. 测试

本切片相关测试文件,以及它们各自把哪条行为写成了规格。

| 测试文件 | 行数 | 覆盖 | 关键规格 |
|---|---|---|---|
| `tests/gateway/test_delivery.py` | 331 | `DeliveryTarget.parse`、relay 解析、Telegram 私聊话题、截断 | `:41` Slack chat_id 大小写保留;`:95` relay 无 inbound 缓存也能投;`:147` 原生赢 relay;`:176` 禁用的原生不遮蔽 relay;`:230` 命名话题先创建;`:254` 数字 thread 需要 reply anchor;`:312` 非分片适配器截断 |
| `tests/gateway/test_dead_targets.py` | 147 | 死目标全生命周期 | `:73` forbidden→标死→短路(适配器不再被调);`:92` 注入共享 registry;`:136` 子级 not_found 不标死;`:141` 双标记时子级赢 |
| `tests/gateway/test_delivery_ledger.py` | 299 | 四态机 + sweep + 重发 | `:98` id 稳定且互不碰撞;`:110` 活主进程的行不被认领;`:171` pending 裸重发并清 resume_pending;`:189` attempting 带 marker;`:207` 慢 DB 不阻塞事件循环;`:238` 平台缺席不烧 attempts;`:286` 跨多次开机存活 |
| `tests/gateway/test_delivery_ledger_fd_leak.py` | 85 | #69567 回归 | 连接不泄漏 |
| `tests/gateway/test_delivery_ledger_producer.py` | 184 | 生产侧接线 | patch `record_obligation`/`mark_attempting`/`mark_delivered` 验证调用顺序 |
| `tests/gateway/test_delivery_silence_filter.py` | 129 | `_is_silence_narration` | 19 个用例:各种 markdown 包裹的 silent、🔇、`.`、`…`,以及不该命中的正常散文 |
| `tests/gateway/test_response_filters.py` | 21 | 两套静默规则 | `:8` 精确 token;`:13` 自主车道容忍独立行注解 |
| `tests/gateway/test_gateway_silence_tokens.py` | 89 | 网关层静默 | — |
| `tests/gateway/test_stream_consumer_silence.py` | — | `is_partial_silence_marker` 在流式中的行为 | — |
| `tests/gateway/test_mirror.py` | 132 | 会话查找 + 连接管理 | `:38` 取最近更新;`:58` thread_id 消歧;`:82` group 用 user_id;`:111` 无匹配返回 False;`:122` 连接必关 |
| `tests/gateway/test_sticker_cache.py` | 59 | 缓存 + 注入文本 | `:17` 损坏文件降级空 dict;`:25` 存取往返;`:39/:44/:52` 注入文本精确格式 |
| `tests/gateway/test_runtime_footer.py` | 319 | 页脚(**本切片测试最多**) | 37 个用例:三层配置合并、每个字段的缺数据降级、latency 格式化、cwd 折叠 |
| `tests/gateway/test_footer_command_mid_run.py` | — | `/footer` 在 turn 进行中切换 | — |
| `tests/gateway/test_streaming_tts_consumer.py` | 675 | 流式 TTS(**本切片最大**) | `:299` 失败后不从头重播;`:505` `_DONE` 哨兵不丢;`:571` 适配器 finish 失败;`:605` 有声后超时干净 abort;`:646` 真实网关路径无 `_streaming_tts_consumer` NameError |
| `tests/gateway/test_streaming_tts_gateway_regression.py` | 157 | #60671 网关侧回归(`:1` docstring 标注 #60671) | 真实 `_run_agent_inner` 路径跑通 |
| `tests/gateway/relay/test_handoff_relay_aliasing.py` | — | `resolve_delivery_transport` 在 handoff 场景 | `:56` |
| `tests/test_profile_isolation_runtime.py` | — | `rich_sent_store` profile 隔离 | `:100-111` `_store_path()` 跟随 override |
| `tests/test_journal_mode_config.py` | — | `delivery_ledger._connect` 的 journal mode | `:140-152`, `:219` |
| `tests/gateway/test_whatsapp_cloud.py` | — | whatsapp 侧 `rich_sent_store` 用法 | — |
| `tests/gateway/test_telegram_rich_messages.py` | — | telegram 侧 `rich_sent_store` 用法 | — |
| `tests/gateway/test_discord_missed_message_backfill.py` | — | ledger 写入卸载到线程 | `:383` `test_send_offloads_final_delivery_ledger_write` |
| `tests/cron/test_scheduler.py` | — | cron 走 `router._deliver_to_platform` | `:383` |

### 实跑结果(基线上)

```
tests/gateway/test_delivery.py tests/gateway/test_dead_targets.py
tests/gateway/test_delivery_ledger.py tests/gateway/test_delivery_ledger_fd_leak.py
tests/gateway/test_response_filters.py tests/gateway/test_mirror.py
tests/gateway/test_runtime_footer.py tests/gateway/test_sticker_cache.py
  → 8 files, 85 tests passed, 0 failed (2.7s)

tests/gateway/test_streaming_tts_consumer.py tests/gateway/test_streaming_tts_gateway_regression.py
tests/gateway/test_delivery_silence_filter.py tests/gateway/test_delivery_ledger_producer.py
tests/gateway/test_gateway_silence_tokens.py
  → 5 files, 42 tests passed, 0 failed (8.3s)
```

合计 **127 通过 / 0 失败**。命令:
`HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh <files>`

### 测试覆盖的盲区

- **`dead_targets` 的 10 个测试全部通过 `DeliveryRouter.deliver()`**
  (`tests/gateway/test_dead_targets.py:4-7` 明说 "Covers the full lifecycle through the real
  ``DeliveryRouter.deliver()`` path"),而这条路径生产上不存在。
  **这是"测试给了虚假的接线信心"的教科书案例。**
- `response_filters.py` 只有 2 个直测(`tests/gateway/test_response_filters.py`),
  其余靠 stream_consumer / webhook / cron 的间接测试。147 行 4 个公开函数,直测偏薄。

---

## 7. 重实现要点

如果我要自己造一个同级别 harness 的投递面,从这 9 个文件里带走的东西:

### 7.1 分层要划死:路由层 ≠ 传输层

- **传输层(适配器)**独占:重试、退避、FloodWait、分片、格式降级、平台 API 细节。
- **路由层**独占:目标解析、多目标扇出、传输选择(native/relay)、内容适配(超长落盘/截断)、
  跨平台通用的内容过滤。
- **两层不要互相下探**。hermes 这里的反例:`_deliver_to_platform` 用 `raise` 而不是返回
  `SendResult`(`gateway/delivery.py:640-641`),导致上层要用**字符串匹配**反推 error_kind
  (`gateway/delivery.py:188-210`)。**结构化错误一旦降级成字符串就再也回不去了。**

### 7.2 投递台账:记"欠条",不记"流水"

- 关键设计:**记的是 content 全文**,不是 id。不然恢复时还得重跑一轮。
- 四态 + 崩溃歧义显式化。`pending`(没发)裸重发,`attempting`/`failed`(可能发了)带可见标记。
  **不要试图做 exactly-once,做"诚实的 at-least-once"。**
- 认领用 CAS(`WHERE owner_pid = <我读到的旧值>`),不用锁。
- **存活判定要双因子**(pid + 进程启动时间),防 pid 复用。不确定时判"活着"(保守方向)。
- **重发预算只花在真能发的平台上**(`deliverable_platforms`)—— 否则一个连不上的平台
  每次开机烧一次 attempt,3 次开机后这条消息就永远被 abandon 了,而它一次都没真发过。
  这个细节非常容易漏,而且漏了以后极难发现。
- 毒丸防护:attempts 上限 + 时间上限 → `abandoned`(保留一段时间供检查,再裁剪)。
- 裁剪要按 state 优先级(`delivered` 先删,未决行最后删)。
- **全程 best-effort**:台账挂掉不能拖慢或阻塞真实发送。
- **sqlite 连接必须显式 close**;`with conn:` 只管事务不管连接(#69567)。

### 7.3 静默约定:一个 marker 集合,多套匹配规则

- 共享一个 frozenset,派生出多条规则(交互严格 / 自主宽松 / 流式前缀),
  确保"永远不会漂移"(`gateway/response_filters.py:86-87` 明写了这个理由)。
- **交互式必须严格**(整串等于 marker),否则正常回复里提一嘴 marker 就被吞。
- **流式要有"前缀判定"**:buffer 还可能长成 marker 时先憋住,
  避免"先画出 NO_REPLY 再撤回"。
- **失败轮不静默** —— 错误信息不能被 marker 吞掉。
- 另外准备一层**基座级反回环过滤**(丢弃 `*(silent)*`、🔇、`.`):
  行为约束会随 provider 漂移,prompt 管不住的东西要在基座上加卡口。
  但必须**长度守卫 + 整串锚定**,不然误伤正常文本。

### 7.4 死目标注册表:自愈优于人工

- 只记录**整体不可达**(chat 没了、bot 被踢/被拉黑),不记录子资源不可达(话题被删、消息被编辑)。
  两者的错误码可能是同一个,必须再分一次血径,且**冲突时按"更保守"解读**
  (`gateway/platforms/base.py:2362-2363`)。
- 自愈:任何一次成功发送清标志,不需要人工介入。
- **但要确保自愈路径可达** —— hermes 这里的教训:标死后 `continue` 跳过,
  就再也没有"成功发送"的机会;而唯一会清标志的代码在同一个不可达的函数里。
  设计时要问:**"清除条件在'已被标记'的状态下还能触发吗?"**
  实践答案:要么加"探测性重试"(每 N 小时放一条过去试),要么加 TTL 自动过期。
- 存储:profile 隔离的小 JSON,读写全 best-effort,损坏降级成内存态。

### 7.5 流式 TTS:回落判据是"用户耳朵里有没有进声音"

- 三态而不是二态:`completed` / `partial(有声但不完整)` / `failed(无声)`。
  **只有第三态才允许整段重播。** 有声之后再重播比不播更糟。
- `audible` 在**第一个字节写成功之后**置位,不是之前。
- 同步→异步用有界队列 + `asyncio.to_thread`;**同步生成器一次一格喂进线程池**
  (`_next_stream_chunk` 那个 `(bool, chunk)` 二元组手法)。
- **控制哨兵不能和数据挤同一个有界队列**。真要挤,给哨兵抢占权,
  并把牺牲(丢的那句台词)记成显式状态,让它影响最终的完整性判定。
- **消费者在事件循环线程创建**,不在 worker 线程 —— 否则外层生命周期路径引用不到它。
- 切句要处理三件事:剥 `<think>`(含跨 delta 的未闭合标签)、合并过短碎片、收尾抽干。
- 与文本流是 tee 关系,不是串联;文本流关闭时要有独立的 TTS-only 回调。

### 7.6 小缓存的通病(4 个文件的共同教训)

`rich_sent_store` / `sticker_cache` / `dead_targets` / `mirror` 四个小文件暴露同一组问题:

- **路径解析时机必须统一**。context-local 的 profile override 下,
  模块级常量(`sticker_cache.py:20`、`mirror.py:21`)= 冻结在 import 时刻 = 串 profile。
  **规则:凡是可被 context 覆盖的路径,一律写成函数,不写成常量。**
- **全量 JSON 读改写是 O(n) 每次操作**,且并发是 last-writer-wins。
  条目上千就该换 sqlite。`sticker_cache` 甚至没有上限。
- **有 `cached_at` 字段不等于有 TTL**。写了时间戳但从不读它做过期判定,
  是一种"看起来有淘汰策略"的假象。
- **原子写要 tmp + `os.replace`**;`sticker_cache` 还加了 `fsync` 和
  `except BaseException` 清理临时文件,是这四个里最严谨的。

### 7.7 页脚这类"展示增强"

- **做成纯函数**(零 I/O、零状态、配置由调用方传入)—— `runtime_footer.py` 37 个测试
  没有一个需要 mock 文件系统,这就是回报。
- 三层配置合并(默认 / 全局 / 平台),`enabled` 和 `fields` 独立合并;
  空 list 视为"未设置"而非"清空"(防手误)。
- 缺数据的字段**静默跳过**,不渲染 `?%` 或空槽;全空返回空串。
- 关键在调用点的门:只加在最终消息、流式已发过就改发独立尾巴消息、故意静默时不加。

### 7.8 最重要的一条:接线要能被检查

本切片最大的收获不是任何一个机制,而是:
**`dead_targets.py` 有 143 行完整实现、10 个通过的测试、详尽的 docstring,却零生产调用点。**

测试通过只证明"这段代码按设计工作",不证明"这段代码在跑"。
造 harness 时应该有一条 CI 检查:**每个模块至少有一个非 `tests/` 的调用点**,
或者显式标注为"仅供插件/外部使用"。否则休眠模块会持续积累维护成本
(`gateway/run.py:7323`/`11348`/`12488` 三处还在认真同步一个从不被调用的 router 的 adapters)。

---

## 8. 遗留问题(下轮或提问)

1. `DeliveryRouter.deliver()` 是历史遗留还是有我没找到的动态调用(插件/eval)?
   已 grep `.deliver(`、`DeliveryRouter`、非 py 文件,均无。倾向"历史遗留"。
2. `gateway/run.py:5935` 的 `self.delivery_router` 是否曾经承担过 cron 投递、
   后来被 `cron/scheduler.py` 自建 router 取代?需要 git log 才能确认(本轮不做)。
3. `dead_targets` 的自愈路径不可达是"因为 deliver() 休眠所以无所谓",
   还是即便 deliver() 活着也是个真 bug?从代码看是后者(§2.7)。
