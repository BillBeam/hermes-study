# R5 · 会话状态与持久化 —— 让 agent 跨天记住你

> **读者定位**:你有多年后端经验,但没读过这份代码,也不熟 LLM 生态与 Python 异步。读完这一章,你能
> 不看源码就讲清一个成熟 agent harness 的"记忆侧":一次对话怎么落进一个 SQLite 文件、上下文塞满了怎么
> 压缩、agent 怎么搜自己几个月前的对话、`/new` 到底是清空还是另起、长期记忆怎么进系统提示又不被投毒——
> 并据此设计同级别的持久层。
>
> **溯源约定**:`路径:行号 @ 863e313` 指基线 commit `863e31318` 下 hermes-agent 仓库根的相对路径与行号,
> 可逐条复核。每节末尾指向底稿 `notes/r5-*`,那里有更细的证据。

---

## TL;DR(快读路径:读这一段就有全貌)

先锚几个词:

- **state.db**:一个 SQLite 文件(`~/.hermes/state.db`),存下所有会话的消息。它是 CLI、网关、桌面端、
  定时任务**共享的唯一事实源**。
- **WAL(Write-Ahead Logging)**:SQLite 的一种日志模式,让"多个读 + 一个写"能并发。它依赖内存映射和
  文件锁,在 NFS/SMB 这类网络文件系统上不可靠。
- **上下文压缩(compression)**:对话变长后会撑爆模型的上下文窗口(它一次能读的 token 上限);压缩把
  中段旧对话用一段 LLM 生成的摘要替换,腾出空间。
- **FTS5**:SQLite 内建的全文检索引擎。agent 用它搜自己过去的对话("我上个月怎么修那个 bug 的?")。
- **prefix cache(前缀缓存)**:provider 对"逐字节相同的请求前缀"免重复计费/免重算。持久层的几乎每个
  决策都在绕开"别弄脏这个前缀"。

R5 讲的记忆侧,可以分成五块,每块解决一个具体问题:

1. **会话库(state.db)**:一个 SQLite 文件扛住多进程共享 + 恶劣文件系统 + 各种崩溃,靠八层耐久性防御和
   一套按业务重要性分档的写重试。
2. **上下文压缩**:对话满了怎么无损归档旧轮、生成一段"交接摘要"、还不把已完成的事写成待办、不泄密钥、
   不在并发下分叉出孤儿会话。
3. **跨会话检索(session_search)**:三个 FTS5 索引各管一类查询(英文词级 / 任意子串 / 中日韩),外加
   LIKE 兜底,把"搜自己的过去"做成低 token 成本的钻取。
4. **prompt 装配**:系统提示按"变化概率"分三层,项目上下文文件按优先级选一个、超长截断、注入前过威胁
   扫描。
5. **长期记忆**:两个纯文本文件当常驻记忆冻结进系统提示;外部记忆后端当"可以宕的慢速旁路";召回内容
   围栏隔离防注入;自治写入要用户审批。

贯穿全章两条设计哲学:**一切进系统提示的内容都是攻击面**(写入扫、载入扫、围栏、流式剥块、重放兜底);
**prefix cache 不变量高于一切**(冻结快照、日期粒度时间戳、in-place 归档、滞回剪枝都在服务它)。

如果你只想要结论,到这里够了。想看每个机制从一个具体场景怎么长出来,继续读。

---

## 1. 从一个场景说起:一句"继续昨天那个"的一生

你昨天让 agent 帮你重构一个模块,聊了两百轮,今天开一个新终端,说"继续昨天那个重构,先把测试补上"。
这句话背后,记忆侧要做一连串事:

1. **找回昨天的会话**:昨天的两百轮消息在 `state.db` 里。但"昨天那个"可能已经被压缩过——原始两百轮被
   归档、换成了一段摘要 + 最近若干轮。恢复时要沿"压缩世系"走到最新的那一段。
2. **重建系统提示**:把你的长期记忆(MEMORY.md、你是谁 USER.md)、可用技能索引、项目的 AGENTS.md
   装配进系统提示——而且要按缓存友好的顺序,让今天这次请求尽量命中昨天暖着的前缀缓存。
3. **可能立刻又要压缩**:恢复进来的历史本就接近窗口上限,补上测试的工具输出可能就触发压缩。
4. **可能要搜更早的**:如果"昨天那个"其实分散在好几次会话里,agent 会用 session_search 搜"重构 + 模块名"
   把相关片段捞回来。
5. **一路都在落盘**:每一轮的新消息增量写进 `state.db`,写失败要重试(可能有别的进程正持锁),但绝不能
   把用户这一轮弄丢。

这一章就是拆开这条链,把每一环背后的设计讲清楚。

---

## 2. 全景:记忆侧的五块与数据流

```mermaid
flowchart TD
    U[用户消息] --> ASM[prompt 装配<br/>三层系统提示 + 项目文件 + 记忆快照]
    ASM --> LLM[模型请求]
    LLM --> RESP[模型回复]
    RESP --> FLUSH[增量落盘<br/>每轮一个批事务]
    FLUSH --> DB[(state.db<br/>SQLite 单一事实源)]
    DB --> FTS[三个 FTS5 索引<br/>词级 / 子串 / CJK]
    FTS --> SEARCH[session_search<br/>discovery / scroll / read / browse]
    SEARCH -.召回片段.-> ASM

    RESP --> TRIG{上下文满了?}
    TRIG -->|是| COMP[压缩<br/>归档旧轮 + 生成交接摘要]
    COMP --> DB
    ASM --> MEM[长期记忆<br/>常驻 MEMORY.md + 外部 provider 召回]
    MEM -.围栏隔离.-> ASM
    COMP -.KV-cache 保前缀.-> ASM
```

关系:**装配**把记忆和历史组成请求;**落盘**把每轮结果增量写进 state.db;**压缩**在满了时改写历史(也写回
state.db);**检索**从 state.db 的 FTS 索引把过去捞回给装配;**长期记忆**既常驻在系统提示、又按需召回。
两条虚线是全章暗线:压缩和装配都时刻在保 prefix cache,召回内容进装配前必须围栏。

---

## 3. 逐机制

### 3.1 会话库:一个 SQLite 文件扛住多进程 + 恶劣文件系统 + 崩溃

**场景**:你把 `~/.hermes` 放在了公司的 NFS 网络盘上(为了多机共享),又偶尔 `sudo` 跑过一次 hermes。
某天桌面端打开显示"没有任何会话",可磁盘上明明躺着两百多个会话文件。到底哪儿坏了?

**设计**:`state.db` 是单一事实源,但它跑的环境充满敌意——网络文件系统、只读文件、断电、甚至 SQLite
自己的 bug。所以它有**八层耐久性防御**(完整逐层见 r5-02 §1),这里讲最能说明设计哲学的三层:

- **WAL 启用要信"返回值"而不是"没抛异常"**。`PRAGMA journal_mode=WAL` 在 macOS NFS/SMB 上有个恶劣
  行为:它**不报错但也不生效**,只是返回仍然生效的旧模式。所以代码信它返回的那一行,而不是"这条语句
  没抛异常"——否则会误报成功、还跳过降级告警,让库悄悄留在写阻塞读的 DELETE 模式却没人知道:

  `hermes_state.py:749-754 @ 863e313`

  ```python
        # returns the still-effective mode (e.g. ``delete``). Trust the
        # returned row, not the mere absence of an exception; otherwise we
        # report a false ``"wal"`` AND skip the fallback WARNING, leaving the
        # DB silently in DELETE (reader-blocks-writer) with no signal.
        row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        mode = str(row[0]).strip().lower() if row and row[0] is not None else ""
  ```

  识别"WAL 不兼容"用一张错误指纹表(`locking protocol` / `not authorized`
  / `disk i/o error`),命中就回退到 pre-WAL 的 DELETE 模式(NFS/ZFS 上能用),并把这次降级记成 ERROR
  而不是 WARNING——因为它是真实的并发损失(整段判定见 `hermes_state.py:743-767 @ 863e313`)。

- **零化库隔离而不删除**。某类崩溃会留下一个"大小非零但全是 NUL 字节"的 state.db。检测到后不删,而是
  改名成 `.zeroed-<时间>-<pid>.bak` 隔离(保字节做取证/快照恢复),让下次打开得到全新空库。关键是这个
  rename 受一把跨进程文件锁保护,**5 秒拿不到锁就 fail closed**——宁可不隔离,也不和另一个正在启动的
  进程对同一个活文件重复动手:

  `hermes_state.py:1815-1818 @ 863e313`

  ```python
        if not acquired:
            # Fail closed: do NOT proceed without the lock. A slow or paused
            # startup that still owns the lock can overlap this fallback and
            # the two processes can act on the same live file (#68805 review).
  ```

  拿不到锁时它连日志都写得像操作手册:告诉你零化文件被原地留下,并给出
  `hermes snapshot list` / `hermes snapshot restore <id>` 两条恢复命令(`hermes_state.py:1819-1827 @ 863e313`)。

- **打开期多级自修复**。上面那个"有文件却显示没有会话"的场景,根因通常是 `sqlite_master`(SQLite 记录
  自己 schema 的内部表)出现重复行,于是**连第一条 `PRAGMA` 都解析失败**——远在正常初始化之前就崩了。
  修复是一道阶梯,从最不破坏开始逐级升级,每修一级都用同一个"健康探针"复验,修好即止。
  修复函数(`hermes_state.py:1370-1535 @ 863e313`)的 docstring 自己就把这道阶梯编了号:

  `hermes_state.py:1380-1389 @ 863e313`

  ```python
      1. **Rebuild FTS indexes in place** via the FTS5 ``'rebuild'`` command,
         which rewrites the internal b-tree segments from the canonical
         ``messages`` rows without dropping or recreating anything. Fixes the
         FTS write-corruption class while preserving the schema intact.
      2. **De-duplicate** ``sqlite_master`` (keep the lowest rowid per
         ``type``/``name``). Fixes the canonical "table X already exists"
         case and PRESERVES the existing FTS index intact.
      3. **Drop the FTS schema** (every ``messages_fts*`` object) + ``VACUUM``.
         The next ``SessionDB()`` open rebuilds the FTS indexes from the
         canonical ``messages`` table.
  ```

  关键洞察:**canonical 的消息数据一直是好的,坏的只是派生出来的索引/schema**——所以修复永远不碰数据,
  这一条也是写死在 docstring 里的:`Canonical ``sessions`` / ``messages`` rows are never modified.`

**多进程写怎么不打架**:每个进程一条写连接 + 短到 1 秒的 SQLite 超时,冲突交给应用层的**随机抖动重试**
处理,而不是坐在 SQLite 内置的确定性睡眠表里(那会让所有竞争者同节奏重试,形成 convoy)。而且重试预算
是**时间制、按业务重要性分档**:用户转录写 60 秒(丢了就毁掉用户一整轮)、常规写 20 秒、观测型心跳写
只有 0.5 秒(绝不拖慢响应关键路径)。三档就是三个并排的类常量:

`hermes_state.py:1927-1933 @ 863e313`

```python
    _WRITE_PATIENCE_S = 20.0
    _TRANSCRIPT_WRITE_PATIENCE_S = 60.0
    # Observation-only activity heartbeat/label writes (#76354 review S1):
    # these run on (or adjacent to) the response-critical path and must never
    # wait out the full routine patience under contention. Sub-second budget;
    # a skipped write is retried naturally at the next heartbeat window.
    _ACTIVITY_WRITE_PATIENCE_S = 0.5
```

"为什么是时间制不是次数制"写在这段常量上方的长注释里(`hermes_state.py:1908-1917 @ 863e313`):
这是被 issue #74478 打磨出来的——旧的"最多 15 次重试 ≈ 15 秒"会在一个兄弟进程正常持锁几秒
(比如 VACUUM)时静默丢掉用户一轮,还误导运维去查磁盘。

**可迁移**:把"文件系统敌意"当一等公民——WAL 启用验证返回值而非异常缺失、错误指纹表消歧;三条铁律:
磁盘头已是 WAL 就绝不活体降级、字节级探针只在无活连接时做、手术前必先备份;自修复分层且证据驱动,每级
复验;写重试用时间预算并按业务重要性分档,预算耗尽的报错要说人话("另一个进程持锁超过 60 秒,库本身
是健康的")。

> 底稿:`notes/r5-02-hermes-state-sessiondb.md`、`notes/r5-01-state-schema-portability.md`(声明式 schema)。

### 3.2 声明式 schema:加一列只改一处

**场景**:开发者要给消息表加一列 `finish_reason`。传统做法是写一条带版本号的迁移;但迁移一多,一旦被
重排或插队,某列就可能被跳过,后续代码引用不存在的列直接崩。

**设计**:**声明式调和**。`SCHEMA_SQL` 是唯一真源(全部 `CREATE TABLE IF NOT EXISTS`)。每次启动,代码
把 `SCHEMA_SQL` 灌进一个纯内存 SQLite、用 `PRAGMA table_info` 读出"应该有哪些列",再和活库 diff,
`ALTER TABLE ADD` 缺的列(整个调和过程见 `hermes_state_schema.py:292-348 @ 863e313`)。
"为什么用内存 SQLite 而不是正则"和"加一列只改一处"两句话,作者都写进了同一个 docstring:

`hermes_state_schema.py:296-303 @ 863e313`

```python
        Uses an in-memory SQLite database to parse the SQL — SQLite itself
        handles all syntax (DEFAULT expressions with commas, inline
        REFERENCES, CHECK constraints, etc.) so there are zero regex
        edge cases.  The in-memory DB is opened, the schema DDL is
        executed, and PRAGMA table_info extracts the column metadata.

        Adding a column to SCHEMA_SQL is all that's needed; the
        reconciliation loop picks it up automatically.
```

有一类调和表达不了:改主键(SQLite 不能 `ALTER PRIMARY KEY`)。这类写成**每次启动无条件跑的幂等愈合**
——重命名旧表、建新表、拷数据、删旧表。两个真实案例:网关路由表因缺 scope 列导致每次 upsert 失败刷警告
(#59203);token 记账表因缺 task 维度导致每次记账 upsert 失败、**静默清零全部 token 与成本记账**
(#73823)。

**可迁移**:schema 管理用"声明式真源 + 启动期列 diff + ADD",版本链只留给数据迁移;PK 变更写成幂等
愈合;大而慢的存储布局迁移(比如换 FTS 布局)做成 opt-in 显式命令,用独立版本标记与主 schema 版本
解耦,别在用户下次打开时静默跑一两个小时。

> 底稿:`notes/r5-01-state-schema-portability.md` §1-§2。

### 3.3 上下文压缩:满了怎么优雅地忘

**场景**:一次长任务聊到接近模型窗口上限。再发一个请求就会超限报错。你希望 agent 把中间那些"读文件、
跑测试"的旧轮压掉,但**保住**你最新那句还没做完的请求、保住它刚给你的回复、还不能把"已经发过的邮件"
写成"待办:发邮件"让它重发一遍。

**设计**:压缩分三层——纯算法的策略层(可测)、管锁和落库的宿主层、纯文案的反馈层。整个流程五步,
压缩器类的 docstring 就是这五步的原文:

`agent/context_compressor.py:1321-1326 @ 863e313`

```python
    Algorithm:
      1. Prune old tool results (cheap, no LLM call)
      2. Protect head messages (system prompt + first exchange)
      3. Protect tail messages by token budget (most recent ~20K tokens)
      4. Summarize middle turns with structured LLM prompt
      5. On subsequent compactions, iteratively update the previous summary
```

翻成中文就是:① 无 LLM 地剪掉旧工具结果 → ② 保护头部(系统提示 + 第一轮)→
③ 按 token 预算保护尾部(最近约 20K)→ ④ 用一段结构化 prompt 让 LLM 把中段总结成"交接摘要" →
⑤ 后续再压时迭代更新上一段摘要。

四个最见功力的设计:

- **触发要"双重测量 + 防抖"**,否则会抖成冻屏。模型每轮报两个 token 数:请求前的粗估(对 schema 重的
  请求故意高估)和 provider 返回的真实数。裁决"这次压缩到底有没有用"只认**真实数**,而且只在一个地方
  裁一次——因为粗估会每轮上下跳,放在那里判会把计数器每轮清零、反复重开压缩循环:

  `agent/context_compressor.py:2507-2512 @ 863e313`

  ```python
            # It must NOT live in should_compress(): that runs twice per turn
            # with two different measures (a rough preflight estimate and the
            # real post-response count, #36718), and the rough one can dip below
            # the threshold and reset the strike every turn, re-opening the loop.
            # Keying on real usage compares like with like and fires exactly once
            # per compaction.
  ```

  压完立即把状态设成"等一轮真实读数再说",精确防住"刚压完粗估又冒头、于是又压一次"。再叠三个独立的
  断路器(摘要失败冷却、无效压缩累计、降级摘要连续),外加一个 300 秒定时探针保证断路器绝不永久锁死
  (r5-20 §1)。

- **交接摘要不信任 LLM 写关键锚**。摘要 prompt 的第一条指令是"逐字保住用户最新未完成的请求"——但代码
  不赌 LLM 照做:摘要生成后,用确定性提取的"最新真实用户消息"**强制覆写**那一节。那个方法的名字和
  一句话说明就是全部意图:

  `agent/context_compressor.py:4445-4450 @ 863e313`

  ```python
    def _ground_historical_task_snapshot(
        cls,
        summary: str,
        messages: List[Dict[str, Any]],
    ) -> str:
        """Force the task snapshot section to match a real user turn when possible."""
  ```

  防"已完成写成待办"靠一条塞进 prompt 的时间锚定指令,连改写示例都给好了:

  `agent/context_compressor.py:3750-3756 @ 863e313`

  ```python
                f"\nTEMPORAL ANCHORING: The current date is {_today_str}. When an "
                "action has already been carried out, phrase it as a completed, "
                "dated, past-tense fact rather than an open instruction. For "
                'example, rewrite "email John about the proposal" as "Sent the '
                f'proposal email to John on {_today_str}." Never leave a finished '
                "action worded as if it still needs doing, and never invent a date "
                "for work that has not happened yet.\n"
  ```

  这类"prompt 指令 + 确定性后校正"的双保险贯穿整个摘要生成。

- **摘要是持久化边界,密钥必须强制红线**。摘要一旦落库,泄露的凭据会被之后每一次请求无限重注入。所以
  红线用 `force=True`——**故意无视** `security.redact_secrets: false` 那个面向实时工具输出的全局开关。
  "为什么可以无视用户的开关"这句话,作者直接写在了红线函数的 docstring 里:

  `agent/context_compressor.py:682-688 @ 863e313`

  ```python
    Compaction summaries persist across sessions and are re-injected into
    every subsequent summarizer prompt, so this boundary uses strict mode:

    - ``force=True`` — deliberately overrides ``security.redact_secrets:
      false``. That opt-out targets *live tool output* (e.g. working on the
      redactor itself); a summary is a persistence boundary where a leaked
      credential keeps re-entering prompts indefinitely.
  ```

  而且双向(输入序列化 + 摘要输出都扫)。

- **并发下不能分叉出孤儿会话**。最典型的场景:主对话 agent 和它派生的"后台自我复盘 fork"共享同一个
  session_id,两个都调压缩、各自在重叠快照上成功、各自轮转出一个新子会话——同一父会话两个孩子,网关
  只跟到一个,另一个成了**静默吞写入的孤儿**。这段事故经过就写在锁的上方:

  `agent/conversation_compression.py:2325-2334 @ 863e313`

  ```python
    # Atomic, state.db-backed lock per session_id.  Without this, two
    # AIAgent instances that share the same session_id (most commonly the
    # parent-turn agent and its background-review fork — see
    # ``agent/background_review.py``: ``review_agent.session_id =
    # agent.session_id``) can each call compress() on overlapping
    # snapshots of the same conversation.  Both succeed, both rotate
    # ``agent.session_id`` to a fresh id, both create child sessions in
    # state.db parented to the same old id.  The gateway's SessionEntry
    # only catches one rotation, so the other child becomes an orphan
    # that silently accumulates writes — Damien's repro shape.
  ```

  修法是 state.db 里的一把持久锁(按 session_id 键控,holder 串带 pid 便于辨认死持有者,
  TTL + 后台租约刷新);抢不到锁就本轮弃权;迟到的竞争者发现父会话已被轮转就收敛到那唯一的活孩子。

**落库默认走"就地"而非"轮转"**:同一个 session_id,旧轮软归档(标记 `active=0`,留在盘上、仍可被搜索
和恢复),压缩后的新集原子插入(hermes_state.py 的 `archive_and_compact`)。这消灭了整个"换 session_id
导致 /goal 丢失、孤儿会话、搜索断裂"的 bug 簇。

**可迁移**:压缩分策略/宿主/反馈三层;触发裁决只认真实 token、只裁一次、压完强制等一轮;关键锚(当前
任务、密钥红线)用"prompt 指令 + 确定性后校正"双保险;持久化边界的红线要 force 且双向;会话级持久锁
必须 holder 可辨识、TTL + 租约、迟到者有收敛路径;落库首选同 id 软归档原子换活集。

> 底稿:`notes/r5-20-context-compression.md`。

### 3.4 交接摘要为什么会说错话:三个真实事故

R1 的地图把摘要生成标成一条"◇"(有实现),但底下藏着一串教训,值得讲成故事:

**事故一:摘要把任务弄丢了(#10896)。** 早期版本把中段压成摘要,而摘要前缀又写着"只理睬摘要之后的
最新用户消息"。可如果用户最新那句请求恰好落在被压掉的中段里,它就凭空消失了——agent 压缩完像失忆一样
不知道要干嘛。修法:切分尾部时,把"最后一条可行动的用户消息"强制锚进保护尾,绝不让它进中段
(context_compressor.py 的尾锚链)。

**事故二:已完成的事被重做(#22523)。** 一个完整的"用户请求 + agent 完成"回合(turn-pair)如果被从
中间切开——请求进了摘要、完成留在尾部,或反过来——摘要就可能把它写成"待办",agent 醒来又做一遍。修法:
切分点碰到半个 turn-pair 就整体前推,保持因果耦合。

**事故三:模型模板拒绝整个请求(Mistral 交替)。** Mistral 系模型的对话模板强制 user/assistant 交替,
但**豁免 tool 消息**。如果按消息列表的字面顺序给摘要选角色,可能选出连续两个 user,模板一数就报交替
错误、整个请求 HTTP 500——而摘要已经落库,每次重试都重放这段污染历史,**会话永久损坏**。
源码把这条失败链完整写了下来:

`agent/context_compressor.py:193-200 @ 863e313`

```python
    template sees it. The canonical failure: the protected head ends
    ``[user, assistant(tool_calls), tool]``, so the literal last role is
    ``tool`` and the summary is pinned to ``role="user"`` -- but the last
    role the template counts is ``user``, the template sees user -> user,
    and llama.cpp / Mistral-hosted backends reject the ENTIRE request with
    a Jinja alternation error (HTTP 500). Because the summary persists in
    the stored conversation, every retry replays the same poisoned history
    and the session is unrecoverable.
```

修法:按"模板数得到的可见角色"选角,而不是字面顺序;双撞时把摘要并入尾部消息。

这三个故事共同的教训:摘要是**持久化**消息,一次写错就是永久污染,所以这里值得过度设防——每个关键决策
都配一个确定性的后校正或校验。

> 底稿:`notes/r5-20-context-compression.md` §3-§5。

### 3.5 跨会话检索:三个索引各管一类查询

**场景**:你问 agent"我们几个月前是怎么解决那个 CJK 编码 bug 的?"agent 要在一个可能几 GB 的 SQLite
里,既能搜英文词("encoding")、又能搜任意子串、还能搜中日韩短词("编码"),而且要快、要省 token。

**设计**:一个 tokenizer(分词器)做不到全部,所以建**三个 FTS5 索引**,按查询形状路由(r5-10 §1、§3):

- `messages_fts`(unicode61 词级):英文/拉丁词级检索,体积最小,**唯一收录 tool 行**。缺陷:整段 CJK 被
  当成一个 token,两字查询永远命中不了。
- `messages_fts_trigram`(trigram 三字符):任意文字的子串匹配(中文、泰文都行)。缺陷:每个查询词至少
  3 字符;而且体积是正文的约 2.6 倍,所以它读一个**排除 tool 行的视图**——tool 输出占约 90% 消息字节
  且几乎全是机器噪音(base64、文件转储),不值得进这个贵索引(它们仍全存、仍能被 `messages_fts` 搜到)。
- `messages_fts_cjk`(cjk_unicode61 双字):专治中日韩 1-2 字短词(trigram 够不着的)。它是一个约 250 行
  的可加载 C 扩展,把 CJK 连段重发射成重叠的字符 bigram(Lucene CJKAnalyzer 的老方案),配 FTS5 短语
  语义就得到 2 字级子串精确匹配。

第四条路是 LIKE 全表扫描,当索引都够不着时的永远可用兜底。**为什么值得三个**:没有任何单一 tokenizer
能同时做到"词级排序 + 任意子串 + 2 字 CJK + 全宿主可用"。

**工具面四形态**——一个工具、四种模式,靠"你填了哪几个参数"推断:

`tools/session_search_tool.py:863-872 @ 863e313`

```python
    """Single-shape tool. Mode inferred from which args are set.

    Discovery: pass ``query``.
    Scroll:    pass ``session_id`` + ``around_message_id``.
    Read:      pass ``session_id`` (no anchor) — dumps the whole session.
    Browse:    pass nothing.

    Pass ``profile`` to read another profile's sessions (e.g. resolving an
    ``@session:<profile>/<id>`` link). Scroll wins over read/discovery when an
    anchor is set — the agent has asked for a specific slice.
```

逐个说:**discovery**(给 query,宽扫后按会话世系去重,每个
命中水合成"开头 + 命中窗口 + 结尾"的三明治,一次调用就给出"目标→命中→结局"而不用整段转储)、
**scroll**(给锚点消息 id,前后翻页)、**read**(给 session_id,整段读)、**browse**(什么都不给,列最近
会话)。低 token 的关键就是 discovery 的三明治:模型不用为判断相关性付整段转录的 token,最后统一
`pop("content")` 只回 snippet。

**一处文档定案**:README 说 session_search 带 "LLM summarization",但代码里它是纯 DB 检索、零 LLM 调用
(工具 schema 自述 "no LLM calls"),连自家的 memory.md 都写 "no LLM summarization"——README 与自家
文档直接矛盾,以代码为准。

**可迁移**:多 tokenizer 按查询形状路由 + LIKE 兜底;贵索引用视图裁掉低价值行;召回工具的产品形态是
"一次调用 = 会话级三明治",而非"消息命中列表";所有降级路径(索引缺失/损坏/回填中)要保证"变慢/变粗
但不静默变少"。

> 底稿:`notes/r5-10-fts5-session-search.md`。

### 3.6 prompt 装配:按"变化概率"分层保缓存

**场景**:同一个会话一整天里发几十个请求。系统提示每次都要发给模型。如果它每次字节都变(比如带了精确
到分钟的时间戳),那 provider 的前缀缓存每次都失效,又慢又贵。

**设计**:系统提示**每会话构建一次并缓存**,只有压缩才重建;而且分三层,按"变化概率"排序,让重建时未变
的前缀仍能复用。这个模块的开篇把"为什么"和"哪三层"一次讲完:

`agent/system_prompt.py:3-8 @ 863e313`

```python
The agent's system prompt is built once per session and reused across all
turns — only context compression triggers a rebuild.  This keeps the
upstream prefix cache warm.  See ``hermes-agent-dev``'s
``references/system-prompt-invariant.md`` for the invariants and
``references/self-improvement-loop.md`` for how the background-review
fork inherits the cached prompt verbatim.
```

三层的分工(原文见 `agent/system_prompt.py:10-21 @ 863e313`):

- **stable(最稳)**:身份(SOUL.md 或默认人格)、工具/模型指引、环境提示。
- **context(会话级稳定)**:调用方消息 + 项目上下文文件 + 编码工作区快照。
- **volatile(每次可变)**:技能索引、记忆快照、用户画像、时间戳。

两个精妙点。第一,**技能索引刻意放在 volatile 层之首而不是 stable**——技能是运行时可变的(agent 会话中
新增/改写技能),放 stable 层的话一次技能变更会把缓存前缀从索引处一路炸到底;放 volatile 之首,未变则仍在
复用前缀内,变了只重刷尾部:

`agent/system_prompt.py:504-509 @ 863e313`

```python
    # byte-stable across rebuilds. With the index in the stable band, a rebuild
    # that picked up a skill change would bust the cached prefix from the index
    # down, taking the whole scaffold with it. Render it at the FRONT of the
    # volatile band instead, ahead of the turn-varying memory/timestamp tail:
    # on an implicit longest-prefix backend an unchanged index still falls
    # inside the reused prefix, and a changed one only re-prefills from here on.
```

第二,**时间戳只到日期精度**("Conversation started: Friday, August 07, 2026"),让系统提示全天字节稳定;
模型真要精确时间可以用工具查:

`agent/system_prompt.py:537-543 @ 863e313`

```python
    # Date-only (not minute-precision) so the system prompt is byte-stable
    # for the full day.  Minute-precision changes invalidate prefix-cache KV
    # on every rebuild path (compression boundary, fresh-agent gateway turns,
    # session resume without a stored prompt).  The model can still query the
    # exact wall-clock time via tools when it actually needs it.
    # Credit: @iamfoz (PR #20451).
    timestamp_line = f"Conversation started: {now.strftime('%A, %B %d, %Y')}"
```

**项目上下文文件按优先级选一个,不合并**——一串 `or` 就是全部规则,首中即停:

`agent/prompt_builder.py:2188-2194 @ 863e313`

```python
        # Priority-based project context: first match wins
        project_context = (
            _load_hermes_md(cwd_path, context_length)
            or _load_agents_md(cwd_path, context_length)
            or _load_claude_md(cwd_path, context_length)
            or _load_cursorrules(cwd_path, context_length)
        )
```

即 `.hermes.md → AGENTS.md → CLAUDE.md → .cursorrules`。超长文件按模型窗口的 6% 动态截断
(保 70% 头 + 20% 尾,中缝留一句"用 read_file 读全文"),并向用户状态信道发告警。注入前**全部过威胁扫描**
——命中就把整个文件替换成 `[BLOCKED]` 占位符,而不是仅仅告警:

`agent/prompt_builder.py:74-77 @ 863e313`

```python
    findings = _scan_for_threats(content, scope="context")
    if findings:
        logger.warning("Context file %s blocked: %s", filename, ", ".join(findings))
        return f"[BLOCKED: {filename} contained potential prompt injection ({', '.join(findings)}). Content not loaded.]"
```

**一处文档定案**:configuration.md 说 AGENTS.md 是"递归遍历 + 子目录全合并",但代码是启动仅读 cwd 顶层;
子目录版本靠另一个机制(subdirectory_hints)在会话中按导航**附加到工具结果**、永不进系统提示。同一份
文档的开发者指南页反而写对了——又一处文档内部矛盾。

**可迁移**:系统提示按变化概率分层、一次构建整会话复用;运行时可变的块(技能索引)放最后一层的最前面;
任何会中途变化的信息要么降精度(date-only)、要么声明为"起点快照,用工具复查";多约定文件用严格优先级
而非合并;进系统提示的文本安全策略要严于工具结果(block 而非 warn)。

> 底稿:`notes/r5-30-prompt-context-engineering.md`。

### 3.7 长期记忆:常驻 + 召回 + 三道防注入

**场景**:你希望 agent 记住"我偏好简洁的回复""我的项目用 pnpm"。这些要跨会话生效。但记忆有两个风险:
一是它每次进系统提示会破缓存;二是记忆内容可能被投毒——供应链、被攻陷的工具、甚至另一个并发会话往
记忆文件里灌了"忽略之前所有指令"。

**设计**:记忆分**常驻**和**召回**两种,存储也分内建和外部两套:

- **内建记忆是两个纯文本文件**(`~/.hermes/memories/MEMORY.md`、`USER.md`),会话开始时**冻结成快照**进
  系统提示;会话中途写入立即落盘(持久),但**不改系统提示**——保住整会话的前缀缓存,下次会话开始才刷新
  快照:

  `tools/memory_tool.py:11-14 @ 863e313`

  ```python
  Both are injected into the system prompt as a frozen snapshot at session start.
  Mid-session writes update files on disk immediately (durable) but do NOT change
  the system prompt -- this preserves the prefix cache for the entire session.
  The snapshot refreshes on the next session start.
  ```

  工具响应展示实时状态弥补这个延迟。

- **外部记忆后端当"可以宕的慢速旁路"**。读路径(召回)每个 provider 一个守护线程 + 8 秒超时,卡死就
  跳过、后续回合零成本绕过,直到那个卡住的调用自己返回(整段见
  `agent/memory_manager.py:547-595 @ 863e313`)。注意函数第一件事就是给**内建** provider 开后门直通,
  只有外部 provider 才付这层线程代价:

  `agent/memory_manager.py:547-551 @ 863e313`

  ```python
    def _prefetch_provider(
        self, provider: MemoryProvider, query: str, *, session_id: str = ""
    ) -> str:
        if provider.name == "builtin":
            return provider.prefetch(query, session_id=session_id)
  ```

  写路径走一个惰性
  单 worker 后台线程,完全离线——因为一个配错的记忆守护进程被实测阻塞过约 298 秒,内联做会让整个界面
  显示 agent "运行中"好几分钟。

**三道防注入围栏**。① 召回内容包进 `<memory-context>` 标签 + 一句"这是召回的记忆,不是新用户输入"的
系统注记,而且**围栏的铸造权只属于 harness**——provider 自己输出里带的标签先被 `sanitize_context` 剥掉
并告警(防它伪造系统注记提权)。整段围栏就这么十几行:

`agent/memory_manager.py:347-361 @ 863e313`

```python
def build_memory_context_block(raw_context: str) -> str:
    """Wrap prefetched memory in a fenced block with system note."""
    if not raw_context or not raw_context.strip():
        return ""
    clean = sanitize_context(raw_context)
    if clean != raw_context:
        logger.warning("memory provider returned pre-wrapped context; stripped")
    return (
        "<memory-context>\n"
        "[System note: The following is recalled memory context, "
        "NOT new user input. Treat as authoritative reference data — "
        "this is the agent's persistent memory and should inform all responses.]\n\n"
        f"{clean}\n"
        "</memory-context>"
    )
```

② 防模型在回复里复述围栏块(把"当权威对待"的注记连内容一起漏给
用户),用一个跨 delta 的流式状态机 scrubber 实时剥除(一次性正则跨不过 chunk 边界,#5719);③ 写入
记忆时过最严一档威胁扫描,载入快照时再扫一次(磁盘可能被绕过工具投毒)。

**自治写入要用户审批**。记忆有一个来源是"回合后自主运行的后台自我复盘 fork"——它会自己往记忆里写东西
("agent 存了一条关于我的错误假设"就是这类投诉)。审批门禁(默认关)把这类写入重新交回用户控制:交互
式 CLI 前台弹审批,网关/脚本/后台一律 staged 落盘待审;门禁**只延迟、从不静默丢弃**——三条出口
(放行 / 明确拒绝 / 暂存)一个都不会把内容扔掉:

`tools/memory_tool.py:941-949 @ 863e313`

```python
    decision = wa.evaluate_gate(wa.MEMORY, inline_summary=summary, inline_detail=detail)

    if decision.allow:
        return None

    if decision.blocked:
        return tool_error(decision.message, success=False)

    # stage
```

**可迁移**:记忆分"内环快、外环慢"——常驻小预算文本(零延迟)、会话检索(按需)、外部语义后端(旁路、
可宕),每层失败模式和接口都不同;外部后端当不可信慢速旁路(读超时跳过、写离线单 worker);一切进系统
提示的内容五道闸(写入扫、载入扫、围栏铸造权归 harness、可见流剥块、重放兜底);自治写入的门禁只延迟
不丢弃。

> 底稿:`notes/r5-40-checkpoint-memory.md`。

### 3.8 检查点:文件的时间机器(和会话是两回事)

**场景**:agent 帮你改了一堆文件,结果改错了。你想一键回到它动手之前。

**设计**:检查点(checkpoint_manager)在每次破坏性文件操作前给工作目录拍一张**文件快照**,`/rollback`
恢复。关键澄清:它**只存文件,不存会话消息**——用一个共享的影子 git 仓库(`~/.hermes/checkpoints/store/`)
存快照,LLM 完全看不见它,是透明基础设施。模块开篇的两段话把"它做什么"和"它不是什么"分得很清楚:

`tools/checkpoint_manager.py:2-11 @ 863e313`

```python
Checkpoint Manager — Transparent filesystem snapshots via a single shared
shadow git store.

Creates automatic snapshots of working directories before file-mutating
operations (``write_file``, ``patch``, ``terminal`` with destructive flags),
triggered once per conversation turn.  Provides rollback to any previous
checkpoint.

This is NOT a tool — the LLM never sees it.  It's transparent infrastructure
controlled by the ``checkpoints`` config flag or ``--checkpoints`` CLI flag.
```

它和 state.db 是两套独立系统,
唯一的交点是 CLI `/rollback` 成功后会**顺带撤销一个对话回合**,让模型的上下文和恢复后的文件状态对齐
(否则模型基于幻影文件状态继续编辑)。

几个工程细节:影子 git 用 `GIT_DIR`/`GIT_WORK_TREE` 完全外置、屏蔽用户的 git 配置(否则用户的 gpg 签名
钩子会让每次后台快照弹密码框);单个共享对象库靠 git 内容寻址跨 worktree 去重;恢复前先自拍一张
"pre-rollback 快照"(让你能撤销这次撤销);orphan(工作目录消失)删除极其保守——要用父目录的
`(设备号, inode)` 证明"确实被删了"而不是"网盘暂时没挂载",无人值守时宁可不删。

**一处文档定案**:文档说"每个目录每回合至多一张快照",但代码的去重窗口其实是**一次 API 迭代**(注释
自书 "so each iteration can take one snapshot"),一个多迭代回合可以产生多张。

**可迁移**:文件快照用外置影子 git(屏蔽用户 git 配置)、单对象库跨 worktree 去重;恢复前先自拍;
文件回滚要联动会话回退;删除历史要有"确实被删"的可观察证据(区分删除与卷未挂载)。

> 底稿:`notes/r5-40-checkpoint-memory.md` §1。

---

## 4. 可迁移的设计原则(造你自己的持久层时怎么做)

把这一簇提炼成七条:

1. **单一事实源要扛住敌意环境**。SQLite 会话库跑在 NFS/断电/崩溃里:WAL 启用验证返回值、错误指纹消歧、
   磁盘头已 WAL 绝不活体降级、坏库隔离不删除、打开期分级自修复(数据永不动)。
2. **写重试按业务重要性分档,用时间不用次数**。转录写 60 秒、常规 20 秒、心跳 0.5 秒;预算耗尽的报错
   要说清"库是健康的,只是被别的进程持锁"。
3. **schema 声明式**。真源 + 启动期列 diff + ADD;PK 变更幂等愈合;慢迁移 opt-in 且独立版本号。
4. **prefix cache 不变量高于一切**。冻结快照、日期粒度时间戳、技能索引沉到 volatile 之首、in-place 软
   归档、滞回剪枝——记忆侧几乎每个决策都先问"这会不会弄脏前缀"。
5. **压缩是持久化边界,过度设防**。触发只认真实 token、只裁一次、压完强制等一轮;关键锚用"指令 + 确定性
   后校正"双保险;红线 force 且双向;并发用会话级持久锁防孤儿分叉。
6. **检索按查询形状路由**。多 tokenizer 各管一类 + LIKE 兜底;贵索引裁低价值行;召回给三明治不给整段;
   降级只变慢变粗、不静默变少。
7. **进系统提示的一切都是攻击面**。写入扫 + 载入扫 + 围栏铸造权归 harness + 可见流剥块 + 重放兜底;
   自治写入的门禁只延迟不丢弃。

---

## 5. 地图与代码的出入

官方文档是作者画的地图,与代码冲突时以代码为准。本簇范围内逐条查实(完整证据在
`notes/r5-90-doc-conflict-rulings.md`),结论融进上面的叙述:

- **会话存储页系统性滞后**:schema version 写 23、代码是 25;写重试文档说"最多 15 次"、代码早已是时间
  预算制(那个常量只剩在文档里);无条件说 "WAL mode"、代码是"默认 WAL + 四种回退 + 漏洞版本拒 WAL";
  "three triggers"、实为每索引 3 个共 9 个。整套耐久性防线(零化隔离、多级修复、macOS fsync 补丁)文档
  零提及——本簇最大的"代码有、地图无"落差。
- **session_search 文档内部矛盾**:一处说 "Three calling shapes"、另一处 "Four shapes";README 说带
  "LLM summarization"、memory.md 说 "no LLM summarization"。代码是四形态、纯 DB 检索。
- **prompt 装配页**:技能索引被列在 stable 层(实为 volatile 之首)、时间戳画成分钟级(实为 date-only)、
  AGENTS.md 说递归合并(实为顶层 + 渐进 hints)。同一份文档不同页互相打架。
- **压缩专页七处过时**:空占位符(实为工具语义摘要)、旧标题模板、上限 12000(实 10000)、孤儿 tool_call
  插桩(实为剥离)、"摘要模型窗口必须 ≥ 主模型且失败静默丢弃"(实为自动降阈 + 中止保原文)、
  `protect_first_n` 说 hardcoded 永久(实为配置且首压后衰减)、首屏 "Fires at 50%" 未提小窗口 75% 地板。
- **检查点页**:"每目录每回合至多一张"(实为每 API 迭代);orphan 不删靠调用点约定而非默认值。
- **正面反例**:`context-engine-plugin.md` 与代码逐条一致——和 R3 的 Tool Search 一样,是"复杂机制反而
  文档最全"的反例,提醒不能假设复杂机制必无文档。

一句话总结(与 R3/R4 一致并加深):hermes 的**机制描述大体正确,但精确处——版本号、默认值、数量、
层位——系统性滞后**;而且本轮抓到文档**内部自相矛盾三次**(three vs four shapes、AGENTS.md 两页打架、
README vs memory.md),说明"以代码为准"不只是防文档旧,也是防文档自己跟自己不一致。

---

## 6. 延伸

要证据、代码原文、更细的取舍讨论,下钻对应底稿:

| 主题 | 底稿 |
|---|---|
| hermes_state 会话库:八层耐久性 / 多进程写 / 生命周期 / 压缩落库 | `notes/r5-02-hermes-state-sessiondb.md` |
| 声明式 schema 调和 + 会话可携带性(导入导出) | `notes/r5-01-state-schema-portability.md` |
| FTS5 三索引 + session_search 四形态 + CJK 分词器 | `notes/r5-10-fts5-session-search.md` |
| 上下文压缩:触发 / 剪枝 / 交接摘要 / 角色交替 / 锁与栅栏 | `notes/r5-20-context-compression.md` |
| prompt 装配 + 上下文工程 + ContextEngine 钩子 | `notes/r5-30-prompt-context-engineering.md` |
| 检查点(文件快照)+ 记忆存储侧(内建 + 外部 provider) | `notes/r5-40-checkpoint-memory.md` |
| R4-structure 四文件清账(local.py / browser_tool / shell_hooks / desktop_ui) | `notes/r5-60-r4-structure-cleanup.md` |
| 文档冲突定案(20+ 条) | `notes/r5-90-doc-conflict-rulings.md` |
| 行为规格测试运行记录(115 文件 / 1,360 用例) | `notes/r5-95-tests.md` |
