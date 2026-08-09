# r9a 底稿 · 结清 H-R8D-b —— `hermes_cli/kanban_db.py` 两段"与任务板无关"区间的复核与精读

> 研究对象基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(只读)。
> 溯源约定:凡对代码行为的断言,**锚点单独成行、置于代码块之前**,格式 `路径:行号 @ 863e313`。
> 本文是底稿(证据层),求全求证、允许啰嗦。**表格里的行号一律写成裸数字区间**(如 `1380–2840`),
> 不带 `路径:` 前缀 —— 这样引用校验器只对"锚点 + 紧跟的块"这一种形状计数,表格是索引不是证据。
> 全文所有代码块由脚本从基线逐行抽取生成,不经手工转录。

**本文要结清的移交项(R8D 原文):**

> **H-R8D-b**(移交 R9):锚点 `hermes_cli/kanban_db.py:1382-2840` 与 `:6757-9180`——
> R8D 把 `kanban_db.py`(10,275 行)整体判为 L2「结构级理解」,但实测它里面有约 3,881 行
> (**SQLite 灾难自愈** + **进程监管器**)与任务板业务无关,按分层判据本该是 L1「机制精读」。
> 教训被 R8D 记为判据本身的问题:**按文件判层会把大文件里的异质区间一起判掉**。

---

## 0. 复核结论速览

**这是复核,不是背书。R8D 的四个断言里,两个成立、一个部分成立、一个过宽;另有两处附带偏差。**

```text
断言 1  两段合计约 3,881 行                     →  成立(1,459 + 2,422 = 3,881,口径见 §1.2)
断言 2  第一段是"SQLite 灾难自愈"                →  成立;但该段 22.6% 是纯 kanban schema 迁移
断言 3  第二段是"进程监管器"                     →  部分成立;它同时是**任务板调度器**,
                                                   两者在这 2,424 行里是缠在一起的
断言 4  两段"与任务板业务无关"                   →  **对第一段基本成立(64.4% 可整段移植),
                                                   对第二段不成立(仅 18.7% 可整段移植)**
附带    行号标签 6757-9180                       →  偏差 2 行:真实小节是 6755–9178
附带    "监管器 = 一段连续区间"                  →  **错**。监管器另有 5 处在这两段之外,
                                                   最大的一处是 release_stale_claims(4454–4597,144 行)
```

**因此本文对分层的建议(详见 §6)不是"整文件升 L1",而是:layer 列保持 `L2`,
把"已精读区间"写进 `status` 列的文本里。** 理由:R8D 记的教训还差最后一句 ——
问题不在"异质",而在**分层单位(文件)与阅读单位(机制)本来就不是同一个东西**,
而台账的阻断性不变量(五层行数加总 = 全仓总行数)要求单位必须是文件。

---

## 1. 边界复核:这两段实际起止在哪

### 1.1 文件用三行 banner 分节,小节边界是可机械判定的

`hermes_cli/kanban_db.py` 全文 10,275 行(`wc -l` 实测),用 `# ---…---` / `# 标题` / `# ---…---`
三行横幅切成 24 个小节。第一段的横幅:

`hermes_cli/kanban_db.py:1380-1382 @ 863e313`

```python
# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------
```

第二段的横幅:

`hermes_cli/kanban_db.py:6755-6757 @ 863e313`

```python
# ---------------------------------------------------------------------------
# Respawn guard constants
# ---------------------------------------------------------------------------
```

复现命令(把每个横幅的**标题行**行号和标题打出来;注意用字面量 `------` 而不是
`-{40,}` —— 本容器的 awk 是 mawk 1.3.4,**不支持区间量词**,写成 `-{40,}` 会静默输出空):

```verify
cd /home/user/hermes-agent && awk '/^# ------/{t=NR+1} NR==t && /^# [A-Z]/{printf "%5d  %s\n", NR, substr($0,3)}' hermes_cli/kanban_db.py
```

它打出 **24 个**标题,其中本文关心的两个是 `1381 Connection helpers` 与
`6756 Respawn guard constants`。**它打不出第 6735 行的 `# Dispatcher (one-shot pass)`** ——
那个横幅**少了开头那条虚线**(只有"标题 + 收尾虚线"两行),所以任何按三行横幅识别小节的
脚本都会漏掉它。这也是段 B 的调度器常量(6738–6753)看上去"无主"的原因。

### 1.2 R8D 的行号:一处口径、一处偏差

R8D 底稿的分段表里,这两段的行数是 **1459** 和 **2422**;而移交项写的区间标签是
`1382-2840` 与 `6757-9180`。两者的关系是:

```text
段 A   横幅 1380–1382,内容到 2840(2841 是下一个横幅的第一行)
       R8D 标签 1382–2840 = 1459 行  ← 与它自己的计数一致(从横幅**收尾行**算起)
       含横幅的完整小节 1380–2840 = 1461 行

段 B   横幅 6755–6757,内容到 9178(9179 是下一个横幅 "Long-lived dispatcher daemon" 的第一行)
       R8D 标签 6757–9180 = 2424 行  ← **与它自己的计数 2422 差 2**
       6757–9178 = 2422 行 才是它计数对应的区间
       含横幅的完整小节 6755–9178 = 2424 行

合计   1459 + 2422 = 3,881  ← 移交项里"约 3,881 行"的来源,口径无误
```

**偏差的具体后果**:标签 `6757-9180` 的尾部两行 9179、9180 其实属于**下一小节**的横幅:

`hermes_cli/kanban_db.py:9179-9183 @ 863e313`

```python
# ---------------------------------------------------------------------------
# Long-lived dispatcher daemon
# ---------------------------------------------------------------------------

def run_daemon(
```

本文后续一律用**含横幅的完整小节**口径:**段 A = 1380–2840(1,461 行)**,
**段 B = 6755–9178(2,424 行)**,合计 **3,885 行**。

### 1.3 实质错误:进程监管器不是一段连续区间

这是本次复核最重要的一条。段 B 里确实有监管器,但监管器**并不都在段 B 里**。
有 5 处在段 B 之外,而且其中一处是整个回收链上最先跑、代码量最大的那一环:

```text
监管器散落在段 B 之外的部分(实测)
  219–239    DEFAULT_CLAIM_TTL_SECONDS / DEFAULT_CLAIM_HEARTBEAT_MAX_STALE_SECONDS
             / RECLAIM_DEFER_GRACE_SECONDS —— 三个回收阈值
  242–323    _resolve_claim_ttl_seconds / DEFAULT_CRASH_GRACE_SECONDS
             / KANBAN_RATE_LIMIT_EXIT_CODE / _resolve_crash_grace_seconds
             / _resolve_rate_limit_cooldown_seconds
  4454–4597  release_stale_claims —— **144 行**,TTL 过期回收 + 活进程续租 + 心跳陈旧兜底
  6735–6753  DEFAULT_FAILURE_LIMIT / DEFAULT_LOG_ROTATE_BYTES
             / KANBAN_TERMINAL_TIMEOUT_GRACE_SECONDS(挂在 "Dispatcher (one-shot pass)" 横幅下)
  9179–9237  run_daemon —— 长驻调度循环本体
```

`release_stale_claims` 被漏掉尤其要紧,因为 `dispatch_once` 的第一步就是调它,
而它内部要用段 B 里的 `_pid_alive` / `_terminate_reclaimed_worker` /
`_worker_survived_termination`:

`hermes_cli/kanban_db.py:4506-4512 @ 863e313`

```python
        if (
            host_local
            and row["worker_pid"]
            and _pid_alive(row["worker_pid"])
            and not heartbeat_stale
        ):
            new_expires = now + _resolve_claim_ttl_seconds()
```

**"按文件判层会把异质区间一起判掉"这条教训要补一句:按区间判层同样会把跨区间的机制切断。**
段 B 这个标签,恰好把一条完整的"回收链"从中间剪开了。

顺带记下 `RECLAIM_DEFER_GRACE_SECONDS` 的存在理由,它是整章最好的一段事故注释:

`hermes_cli/kanban_db.py:231-239 @ 863e313`

```python
# Grace added to a claim when a reclaim is deferred because the previous
# host-local worker is still alive after a termination attempt. Releasing the
# claim in that state would spawn a duplicate alongside the surviving worker —
# the runaway seen when a cgroup memory.high throttle parks a worker in
# uninterruptible (D) state, where a pending SIGKILL cannot be delivered until
# the throttle lifts. Holding the claim a short grace and retrying next tick
# stops the duplication; once no duplicate is spawned the pressure eases, the
# signal lands, and the following tick reclaims cleanly.
RECLAIM_DEFER_GRACE_SECONDS = 120
```

---

## 2. 判据:换到一个完全没有任务板的项目里,还成立吗

### 2.1 判定方法

对每个函数/常量块问同一个问题:**把它整段拷进一个没有 `tasks` 表、没有 assignee、
没有 worker 概念的项目,它是否仍然编译、仍然有意义?** 三档:

- **是** —— 只依赖 `sqlite3` / `os` / `pathlib` / 本模块内的通用工具,整段可移植;
- **半** —— 骨架通用(信号阶梯、锁、轮转),但函数体里嵌了 kanban 的 SQL 或状态名;
- **否** —— 直接读写 `tasks` / `task_runs` / `task_events`,或直接拼 `hermes -p <profile>` 命令行。

下面两张表是**我的判断**,不是从代码里读出来的事实,所以用 ```text 声明为非源码块。
行数由区间相减得到,列和已核对(段 A 合计 1461、段 B 合计 2424)。

### 2.2 段 A 逐块归类 —— 64.4% 可整段移植

```text
  行区间        行数   内容                                          可移植
  1380–1382        3   横幅                                            —
  1383–1403       21   _INITIALIZED_PATHS / _SQLITE_HEADER / 隔离保留数 是
  1404–1422       19   _resolve_busy_timeout_ms                        是
  1423–1448       26   _sqlite_connect(+ 活连接登记)                  是
  1449–1532       84   _cross_process_init_lock(有界 flock)           是
  1533–1616       84   _dispatch_tick_lock(非阻塞单写者)              是
  1617–1662       46   WAL 周期 checkpoint(TRUNCATE)                  是
  1663–1717       55   TLS 记录探测 + SQLite header 校验               是
  1718–1736       19   KanbanDbCorruptError                            是
  1737–1784       48   _prune_corrupt_backups(隔离文件轮转)           是
  1785–1860       76   _backup_corrupt_db(内容寻址隔离)               是
  1861–1946       86   可修复错误模式 + _attempt_index_reindex_repair   是
  1947–2041       95   _guard_existing_db_is_healthy(连接时闸门)      是
  2042–2147      106   RepairResult + repair_db(CLI 入口)             是
  2148–2259      112   connect(快慢两条路径)                          半(尾部跑 SCHEMA_SQL)
  2260–2294       35   connect_closing(FD 泄漏修复)                   是
  2295–2324       30   init_db                                         是
  2325–2654      330   _migrate_add_optional_columns + _REBUILD_SPECS   否(纯 kanban 列/表)
  2655–2729       75   _table_has_drifted + _rebuild_drifted_tables     半(机制通用,表名业务)
  2730–2766       37   _check_file_length_invariant(撕裂扩展检测)     是
  2767–2799       33   busy 抖动重试常量 + _execute_boundary_with_retry 是
  2800–2840       41   write_txn                                       是
  ----------------------------------------------------------------------------
  是 941 行(64.4%)   半 187 行(12.8%)   否 330 行(22.6%)   横幅 3 行
```

### 2.3 段 B 逐块归类 —— 只有 18.7% 可整段移植

```text
  行区间        行数   内容                                          可移植
  6755–6757        3   横幅                                            —
  6758–6789       32   配额/鉴权正则、成功窗口、PR URL 正则             半
  6790–6848       59   DispatchResult(结果桶,全是任务板语义)         否
  6849–6862       14   _recent_worker_exits 有界登记表常量              是
  6863–6928       66   _record_worker_exit / _classify_worker_exit      是
  6929–6951       23   reap_worker_zombies                             是
  6952–7015       64   _pid_alive(跨平台 + 僵尸态识别)                是
  7016–7093       78   _terminate_reclaimed_worker + 存活判定           是
  7094–7134       41   _defer_reclaim_for_live_worker                  否
  7135–7185       51   heartbeat_worker                                否
  7186–7299      114   enforce_max_runtime                             半
  7300–7434      135   _STALE_HEARTBEAT_GAP + detect_stale_running     半
  7435–7445       11   _error_fingerprint                              是
  7446–7516       71   协议违规重试预算 + _protocol_violation_streak    否
  7517–7786      270   detect_crashed_workers                          半
  7787–7949      163   _record_task_failure(熔断器)                   否
  7950–8010       61   兼容别名 / _set_worker_pid / 清零计数器          否
  8011–8145      135   check_respawn_guard(四道重生闸门)              否
  8146–8202       57   has_spawnable_ready / has_spawnable_review       否
  8203–8674      472   dispatch_once + _dispatch_once_locked            否
  8675–8756       82   worker 日志轮转                                  是
  8757–8872      116   hermes argv 解析(PATHEXT / .cmd shim / 无 CWD)是
  8873–8902       30   _worker_terminal_timeout_env                     半
  8903–8962       60   toolsets 解析 + 旧 worker 会话重打标            否
  8963–9178      216   _default_spawn(拼命令行 + Popen)               否
  ----------------------------------------------------------------------------
  是 454 行(18.7%)  半 581 行(24.0%)  否 1,386 行(57.2%)  横幅 3 行
```

### 2.4 段 A "与任务板无关"的最硬证据:同一仓库里有第二套独立实现

如果这套自愈逻辑真是 kanban 的业务代码,它不会在一个和任务板毫无关系的数据库上被重写一遍。
但 `state.db`(会话/消息库)有自己的一条自愈阶梯,其中**第 0.5 级就是同一个症状、同一个动作**:

`hermes_state.py:1452-1473 @ 863e313`

```python
    # ── Strategy 0.5: rebuild stale B-tree indexes (#63386) ──
    # PRAGMA integrity_check can report "wrong # of entries in index" when a
    # B-tree index (e.g. idx_sessions_handoff_state) falls out of sync with its
    # base table. REINDEX rewrites the index b-tree from the canonical table
    # rows using the existing index definition, fixing the mismatch without
    # touching data or FTS schema.
    try:
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        try:
            conn.execute("REINDEX")
            conn.commit()
        finally:
            conn.close()
        if _db_opens_cleanly(db_path) is None:
            report["repaired"] = True
            report["strategy"] = "reindex_btree"
            logger.warning(
                "state.db B-tree indexes rebuilt via REINDEX: %s", db_path
            )
            return report
    except sqlite3.DatabaseError as exc:
        logger.warning("state.db REINDEX pass failed: %s", exc)
```

同一个 `wrong # of entries in index`,同一个 REINDEX,写在一个完全不认识 `tasks` 表的文件里。
**"它换到没有任务板的项目里仍然成立"不是我的推断,是这个仓库自己已经做过的实验。**

### 2.5 段 B "与任务板无关"为什么不成立

段 B 里行数最大的三块 —— `dispatch_once`/`_dispatch_once_locked`(472)、
`_default_spawn`(216)、`_record_task_failure`(163)—— 合计 851 行(35.1%),
每一块都在直接操作任务板的表或拼 Hermes 自己的命令行。举一个最不可辩的:

`hermes_cli/kanban_db.py:8360-8364 @ 863e313`

```python
    ready_rows = conn.execute(
        "SELECT id, assignee FROM tasks "
        "WHERE status = 'ready' AND claim_lock IS NULL "
        "ORDER BY priority DESC, created_at ASC"
    ).fetchall()
```

以及 spawn 出来的命令本身:

`hermes_cli/kanban_db.py:9096-9105 @ 863e313`

```python
    cmd = [
        *_resolve_hermes_argv(),
        "-p", profile_arg,
        "--cli",
        # Worker subprocesses switch to a profile-scoped HERMES_HOME above,
        # so they see that profile's shell-hook allowlist instead of the
        # dispatcher's root allowlist. Pass --accept-hooks explicitly so
        # profile-local worker sessions still register configured hooks.
        "--accept-hooks",
    ]
```

**结论:段 B 是"一个进程监管器 + 一个任务板调度器"的合体**,监管原语(僵尸回收、判活、
信号阶梯、指纹、日志轮转、argv 解析)确实通用且值得精读,但它们只占 454 行;
剩下 1,970 行是任务板业务。移交项那句"与任务板业务无关"对段 B 是**过宽的**。

---

## 3. 精读段 A:SQLite 灾难自愈

### 3.1 先看一次真实故障:板子突然打不开了

场景:用户的机器上,`~/.hermes/kanban/boards/<slug>/kanban.db` 的开头几十个字节
不再是 `SQLite format 3\x00`,而是一段 **TLS 记录头**。板子上几百张卡片全部不可读。
这不是假想 —— 代码为它专门写了一个探测函数:

`hermes_cli/kanban_db.py:1664-1677 @ 863e313`

```python
def _looks_like_tls_record_at(data: bytes, offset: int) -> bool:
    """Return True for a TLS record header at ``data[offset:]``."""
    if len(data) < offset + 5:
        return False
    content_type = data[offset]
    major = data[offset + 1]
    minor = data[offset + 2]
    length = int.from_bytes(data[offset + 3:offset + 5], "big")
    return (
        content_type in {0x14, 0x15, 0x16, 0x17}
        and major == 0x03
        and minor in {0x00, 0x01, 0x02, 0x03, 0x04}
        and 0 < length <= 18432
    )
```

`content_type ∈ {0x14,0x15,0x16,0x17}`(change_cipher_spec / alert / handshake /
application_data)、`major == 0x03`、`minor ≤ 0x04`、长度 `0 < len ≤ 18432`(TLS
明文记录上限 2^14 + 扩展余量)—— 这是 TLS 记录头的四条不变量。**为什么一个任务板
数据库里会出现 TLS 记录?** 因为某个进程把一个 socket 的读缓冲写进了错误的 fd。
探测点有两个:偏移 0(整个文件被覆盖)和偏移 5(前 5 字节 `SQLit` 侥幸保留)。

如果没有这个探测,用户看到的只会是一句 `file is not a database`。有了它,报错长这样:

`hermes_cli/kanban_db.py:1706-1716 @ 863e313`

```python
    if head.startswith(_SQLITE_HEADER):
        return
    signature = ""
    if head.startswith(b"SQLit") and _looks_like_tls_record_at(head, 5):
        signature = " (TLS record header detected at byte offset 5)"
    elif _looks_like_tls_record_at(head, 0):
        signature = " (TLS record header detected at byte offset 0)"
    raise sqlite3.DatabaseError(
        "file is not a database: invalid SQLite header for "
        f"{path}{signature}; first_32={head[:32].hex(' ')}"
    )
```

**`first_32=<hex>` 是整段自愈设计里最省钱的一行**:它让"我这个文件到底被谁写坏了"
这个问题在**第一次报错时**就能回答,而不需要用户回传数据库(里面有任务正文)。

### 3.2 它防的是哪几类损坏

代码把损坏分成四类,每一类的检测点、动作、兜底都不同:

```text
  类别                     检测点                          动作                    数据风险
  (1) 非 SQLite 文件       _validate_sqlite_header         直接抛 DatabaseError    无(未触碰文件)
      (TLS 误写/截断/换文件) 字节级、连接建立**之前**
  (2) 仅索引损坏           integrity_check 消息全部匹配     内容寻址隔离 → REINDEX  无(索引由表重建)
      (索引与表 b-tree 失配) 两条 index-scoped 正则          → 复检 → 放行
  (3) 其他一切损坏         integrity_check 有任一条不匹配   内容寻址隔离 → 抛      无(拒绝打开)
      (页损坏/malformed)                                    KanbanDbCorruptError
  (4) 撕裂扩展             提交后比对 page_count 与文件长度 抛 DatabaseError        —(已提交的写)
      (header 声称的页数 >   仅在**非 WAL** 日志模式下生效
       实际文件页数)
```

注意第 (4) 类被刻意限制在非 WAL 模式:WAL 下刚提交的页合法地还留在 `-wal` 里,
主文件短于 header 声称的页数**是正常的**:

`hermes_cli/kanban_db.py:2746-2758 @ 863e313`

```python
    from hermes_cli.sqlite_safe_read import file_length_matches_header

    # In WAL mode a just-committed page can still live in the -wal file, so
    # the main file legitimately lags its page count. Only enforce the
    # invariant under a rollback journal, where every committed page must
    # already be in the main file.
    try:
        row = conn.execute("PRAGMA journal_mode").fetchone()
        journal_mode = str(row[0]).lower() if row and row[0] is not None else ""
    except sqlite3.Error:
        return
    if journal_mode == "wal":
        return
```

`file_length_matches_header` 走的是 `hermes_cli.sqlite_safe_read`,**不重新 open 文件**。
原因写在同一段注释里,是本簇最反直觉的一条硬知识:

`hermes_cli/kanban_db.py:2737-2744 @ 863e313`

```python
    Both sides are read WITHOUT opening the database file. The header side
    comes from ``PRAGMA page_count`` over the existing connection; the on-disk
    side from ``stat()``. An earlier version read the header field with a bare
    ``open(path,"rb")`` -- but ``close()`` cancels every POSIX advisory lock
    this process holds on the file, so that probe silently dropped the locks
    of concurrent writers (and of a running VACUUM) and let other processes
    write into a database a writer still believed it owned. That is the
    documented corruption route in sqlite.org/howtocorrupt.html section 2.2.
```

**`close()` 会取消本进程在该文件上的所有 POSIX 咨询锁** —— 这是 POSIX `fcntl` 锁的
著名语义缺陷(同一进程内**任何**一次 `close()` 都会清掉该进程对该 inode 的全部锁,
哪怕关的是另一个 fd)。所以"为了检查损坏而打开文件读几个字节"这个动作本身,
就是 sqlite.org/howtocorrupt.html §2.2 记载的一条**制造**损坏的路径。整个段 A 里
凡是要读字节的地方,都绕开了裸 `open()`。

### 3.3 检测手段:三道闸,顺序是设计的一部分

`hermes_cli/kanban_db.py:2206-2219 @ 863e313`

```python
    with _cross_process_init_lock(path):
        # Read-only file/sidecar preflight (port of kilocode#12508) —
        # repair-or-refuse before the header/integrity probes so a stray
        # read-only kanban.db fails with an actionable message instead of
        # "attempt to write a readonly database" mid-init.
        from hermes_state import preflight_db_writability
        preflight_db_writability(path, db_label=f"kanban.db ({path.name})")
        # Cheap byte-level check first — catches the #29507 TLS-overwrite shape
        # and other invalid-header cases without opening a sqlite connection.
        _validate_sqlite_header(path)
        # Full integrity probe — catches corruption past the header (malformed
        # pages, broken internal metadata). Cached per-path after first success
        # via _INITIALIZED_PATHS so it only runs once per process per path.
        _guard_existing_db_is_healthy(path)
```

顺序 **preflight 可写性 → 字节级 header → 完整 integrity_check** 是从便宜到昂贵排的:
`_validate_sqlite_header` 只读 64 字节;`integrity_check` 要走遍每一页。而只读文件系统
的 preflight 排在最前,是为了让"只读的 kanban.db"报出可操作的错误,而不是在初始化中途
抛一句 `attempt to write a readonly database`。

`integrity_check` 的结果判定极其严格 —— **必须是恰好一行 `ok`**:

`hermes_cli/kanban_db.py:1875-1883 @ 863e313`

```python
def _integrity_messages_ok(messages: list[str]) -> bool:
    """True iff ``PRAGMA integrity_check`` output is the single ``ok`` row."""
    return len(messages) == 1 and messages[0].strip().lower() == "ok"


def _run_integrity_check(conn: sqlite3.Connection) -> list[str]:
    """Return all ``PRAGMA integrity_check`` message rows as strings."""
    rows = conn.execute("PRAGMA integrity_check").fetchall()
    return [str(row[0]) for row in rows if row is not None and row[0] is not None]
```

### 3.4 修复动作:只修索引,且先隔离后修

哪些错误算"可修"由两条正则定义,**不硬编码索引名**:

`hermes_cli/kanban_db.py:1862-1872 @ 863e313`

```python
# Repairable integrity_check error classes. Both shapes are *index-scoped*:
# the table b-tree is intact and only a secondary index disagrees with it,
# which REINDEX rebuilds losslessly from the table data. The index name is
# parsed generically from the message — no hardcoded index list. Any other
# integrity_check message (page corruption, "database disk image is
# malformed", freelist damage, …) is NOT repairable this way and keeps the
# fail-closed behavior.
_REPAIRABLE_INDEX_ERROR_PATTERNS = (
    re.compile(r"^wrong # of entries in index (?P<index>.+)$"),
    re.compile(r"^row \d+ missing from index (?P<index>.+)$"),
)
```

判定是**全称**的:只要有一条消息落在这两条模式之外,整个文件就不可修:

`hermes_cli/kanban_db.py:1894-1912 @ 863e313`

```python
    names: list[str] = []
    saw_any = False
    for raw in messages:
        message = (raw or "").strip()
        if not message:
            continue
        for pattern in _REPAIRABLE_INDEX_ERROR_PATTERNS:
            match = pattern.match(message)
            if match:
                break
        else:
            return None
        saw_any = True
        name = match.group("index").strip()
        if name and name not in names:
            names.append(name)
    if not saw_any or not names:
        return None
    return names
```

这里的 `for ... else: return None` 是 Python 特有的写法 —— 内层 `for` 没有 `break`
(即没有任何模式匹配上)时才执行 `else`,直接判"不可修"。

修复本体:先 `REINDEX "<name>"` 逐个重建,失败则退回整库 `REINDEX`:

`hermes_cli/kanban_db.py:1927-1945 @ 863e313`

```python
    try:
        conn = _sqlite_connect(path)
    except sqlite3.Error as exc:
        return False, [f"could not reopen for REINDEX: {exc}"]
    try:
        try:
            for name in index_names:
                escaped = name.replace('"', '""')
                conn.execute(f'REINDEX "{escaped}"')
        except sqlite3.Error:
            # Per-index rebuild failed (unresolvable parsed name, auto
            # index, …) — bare REINDEX rebuilds every index in the DB.
            conn.execute("REINDEX")
        messages = _run_integrity_check(conn)
    except sqlite3.Error as exc:
        return False, [f"REINDEX failed: {exc}"]
    finally:
        conn.close()
    return _integrity_messages_ok(messages), messages
```

`escaped = name.replace('"', '""')` 是 SQL 标识符转义(REINDEX 不支持参数绑定,
只能拼字符串,而索引名来自 `integrity_check` 的输出文本)。逐个失败就退回整库,
是因为 `integrity_check` 有时报的是 SQLite **内部自动索引**的名字,那种名字
`REINDEX "<name>"` 解析不了。

### 3.5 隔离:内容寻址 + 数量上限

隔离文件名不是时间戳,是**主库文件的 sha256 前 16 位**:

`hermes_cli/kanban_db.py:1828-1847 @ 863e313`

```python
    digest = hashlib.sha256()
    try:
        with resolved.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    token = digest.hexdigest()[:16]
    candidate = parent / f"{base_name}.corrupt.{token}.bak"
    # Defensive: candidate must still be inside parent after construction.
    if candidate.parent != parent:
        return None
    if not candidate.exists():
        try:
            shutil.copy2(resolved, candidate)
        except OSError:
            return None
        # A NEW backup landed on disk — enforce the retention cap so
        # mutating-corruption loops can't accumulate quarantines forever.
        _prune_corrupt_backups(parent, base_name, keep=candidate)
```

**为什么用内容寻址而不是时间戳**:同一份坏字节会被反复撞见(网关重启、调度器每 tick
重试、多 profile 同时连同一个板),时间戳命名会产生 N 份一模一样的副本;内容寻址天然去重。
而"坏字节本身在变"(部分修复、持续损坏)时指纹会变,于是每一种形态各留一份 —— 这正是
需要数量上限的原因:

`hermes_cli/kanban_db.py:1741-1752 @ 863e313`

```python
    """Cap the number of retained ``<db>.corrupt.<hash>.bak`` files.

    Content-addressed backups dedupe identical corrupt bytes, but a board
    whose file keeps changing between corruption events (partial repairs,
    ongoing damage, fleets of retrying dispatchers) can still accumulate
    backups without bound — a user reported 124 of them. After creating a
    new backup we keep only the ``_CORRUPT_BACKUP_RETENTION`` most recent
    (by mtime) and delete the rest, including their copied ``-wal``/``-shm``
    sidecars. ``keep`` (the just-created backup) is never pruned regardless
    of its mtime — ``shutil.copy2`` preserves the source file's timestamp,
    which may be older than existing backups. Best-effort: prune failures
    never mask the corruption error the caller is about to raise.
```

`keep` 参数存在的理由值得单独记:`shutil.copy2` **保留源文件的 mtime**,所以刚做出来的
备份可能比已有备份"更旧",按 mtime 排序会把它自己剪掉。

`hermes_cli/kanban_db.py:1762-1774 @ 863e313`

```python
    budget = _CORRUPT_BACKUP_RETENTION - (1 if keep is not None else 0)
    budget = max(budget, 0)
    if len(backups) <= budget:
        return

    def _mtime(item: Path) -> float:
        try:
            return item.stat().st_mtime
        except OSError:
            return 0.0

    backups.sort(key=_mtime, reverse=True)
    for stale in backups[budget:]:
```

隔离动作本身也可能是危险的 —— 指纹要读整个文件,而"读整个文件"就要 `close()`:

`hermes_cli/kanban_db.py:1809-1827 @ 863e313`

```python
    # This reads the whole DB file to fingerprint it. That is a close()-on-a-
    # database-file hazard (it cancels this process's POSIX advisory locks --
    # see hermes_cli.sqlite_safe_read), so it must only run once the board has
    # been taken out of service. Every caller reaches here on the corrupt/
    # quarantine path after closing its probe connection, but another
    # SessionDB/kanban connection elsewhere in the process would still be at
    # risk -- so REFUSE rather than warn-and-proceed. Losing a forensic copy
    # is strictly better than corrupting the live database we are trying to
    # rescue.
    from hermes_cli.sqlite_safe_read import has_live_connection

    if has_live_connection(resolved):
        _log.error(
            "refusing to quarantine %s: a connection to it is still open in "
            "this process, and fingerprinting the file would cancel that "
            "connection's POSIX locks. Close all connections first.",
            resolved,
        )
        return None
```

**这里的选择是"宁可丢取证副本,也不损坏正在抢救的库"**,而且是 `_log.error` + 返回 `None`,
不是警告后继续。这个 fail-closed 的取向,正是 §5 的 ■-1 要用到的对照面。

### 3.6 兜底:fail-closed,拒绝在损坏文件上重建 schema

`hermes_cli/kanban_db.py:2014-2040 @ 863e313`

```python
    if reason is None:
        return
    # Quarantine FIRST — both the repair path and the fail-closed path
    # preserve the pre-touch bytes before anything mutates the file.
    backup = _backup_corrupt_db(resolved)
    index_names = _repairable_index_names(messages)
    if index_names:
        _log.warning(
            "kanban DB %s failed integrity_check with index-only errors "
            "(%s); pre-repair backup at %s — attempting REINDEX auto-repair.",
            resolved, ", ".join(index_names),
            backup if backup is not None else "<backup failed>",
        )
        repaired, post = _attempt_index_reindex_repair(resolved, index_names)
        if repaired:
            _log.warning(
                "kanban DB %s auto-repaired via REINDEX (%s); "
                "integrity_check now clean. Pre-repair copy kept at %s.",
                resolved, ", ".join(index_names),
                backup if backup is not None else "<backup failed>",
            )
            return
        reason = (
            f"{reason}; REINDEX auto-repair attempted but integrity_check "
            f"still returned {post[0] if post else '<no row>'!r}"
        )
    raise KanbanDbCorruptError(resolved, backup, reason)
```

三件事按顺序发生:**先隔离**(第 2018 行,注释明写"both the repair path and the
fail-closed path preserve the pre-touch bytes before anything mutates the file")、
再判可修、修不好就抛。抛出的异常同时携带原路径和备份路径:

`hermes_cli/kanban_db.py:1719-1735 @ 863e313`

```python
class KanbanDbCorruptError(RuntimeError):
    """Raised when an existing kanban DB file fails integrity checks.

    Fail-closed guard against silent recreation of a corrupt board file,
    which would otherwise destroy the user's tasks. Carries both the
    original path and the timestamped backup we made before refusing.
    """

    def __init__(self, db_path: Path, backup_path: Optional[Path], reason: str):
        self.db_path = db_path
        self.backup_path = backup_path
        self.reason = reason
        backup_str = str(backup_path) if backup_path is not None else "<backup failed>"
        super().__init__(
            f"Refusing to open corrupt kanban DB at {db_path}: {reason}. "
            f"Original preserved; backup at {backup_str}."
        )
```

**"fail-closed"具体防的是什么**:如果这里放行,后面 `connect()` 会照常
`executescript(SCHEMA_SQL)` —— 而 `CREATE TABLE IF NOT EXISTS` 在一个页损坏的文件上
可能"成功",于是用户看到的是一个**空板子**,几百张卡片静默消失。抛异常是唯一能保住
那些字节的做法。

还有一类必须**不**当成损坏:锁竞争。

`hermes_cli/kanban_db.py:2009-2013 @ 863e313`

```python
    except sqlite3.OperationalError:
        # Lock contention, busy, transient IO — not corruption. Let it propagate.
        raise
    except sqlite3.DatabaseError as exc:
        reason = f"sqlite refused to open file: {exc}"
```

`sqlite3.OperationalError`(database is locked / busy)原样上抛,**不做隔离**。
否则一个正忙的健康板子会被每个撞上锁的进程各隔离一份。

### 3.7 修复过程本身会不会丢数据?逐条回答

```text
  问                                          答       依据
  REINDEX 会动表数据吗                        不会     REINDEX 只按现有索引定义从表 b-tree 重建索引
  修复前的字节保住了吗                        是*      _guard_existing_db_is_healthy 先隔离后修
                                                       (* 例外见 §5 ■-1:隔离失败时仍然会修)
  修复失败会不会留下半修的库                  会        REINDEX 已经写过盘;所以"隔离先行"才是唯一保险
  不可修的类别会被动到吗                      不会      直接抛 KanbanDbCorruptError,连 schema 都不跑
  锁竞争会被误判成损坏并隔离吗                不会      OperationalError 原样上抛
  隔离副本包含 WAL 吗                         是        -wal / -shm 一并 copy2(1848–1858)
  修复后进程内缓存会不会残留"已健康"          不会      repair_db 显式 discard(_INITIALIZED_PATHS)
```

最后一条对应这几行 —— 文件在盘上变过了,进程内的"这个路径已验过"缓存必须作废:

`hermes_cli/kanban_db.py:2134-2138 @ 863e313`

```python
        repaired, post = _attempt_index_reindex_repair(resolved, index_names)
        # The file changed on disk; force the next connect() in this process
        # to re-probe instead of trusting the stale healthy-path cache.
        with _INIT_LOCK:
            _INITIALIZED_PATHS.discard(str(resolved))
```

### 3.8 并发面:两把文件锁 + 一次 WAL 截断 + 一层抖动重试

**锁 1:跨进程初始化锁(有界)。** 首次连接要做 header 校验、integrity 探测、WAL 激活、
增量迁移,这些必须全主机单写者。原实现是裸 `flock(LOCK_EX)`,没有超时:

`hermes_cli/kanban_db.py:1397-1402 @ 863e313`

```python
# Bounded acquire for the cross-process init lock (#36644). The original bare
# blocking flock had no timeout, so a wedged holder blocked the dispatcher's
# next-tick connect forever. We retry a non-blocking acquire up to this
# deadline, polling at this interval, then proceed without the cross-process
# lock (the in-process _INIT_LOCK + idempotent init remain the backstop).
_INIT_LOCK_TIMEOUT_SECONDS = 10.0
```

超时后**不报错,而是继续**:

`hermes_cli/kanban_db.py:1517-1524 @ 863e313`

```python
            if acquired:
                if _IS_WINDOWS:
                    import msvcrt

                    handle.seek(0)
                    locking = getattr(msvcrt, "locking")
                    unlock_mode = getattr(msvcrt, "LK_UNLCK")
                    locking(handle.fileno(), unlock_mode, 1)
```

**"有界地继续"胜过"无界地挂住"**的理由写得很清楚:进程内锁仍在,初始化本身幂等
(`CREATE TABLE IF NOT EXISTS` + 增量迁移),最坏结果是重复劳动而不是损坏。

**快路径连这把锁都不取。** 这是 #36644 的正解:稳态下没有任何 schema 写入需要保护。

`hermes_cli/kanban_db.py:2178-2190 @ 863e313`

```python
    # Fast path: once THIS process has initialized this path, the expensive
    # first-open work (header validation, integrity probe, schema + additive
    # migrations) is already done and cached in _INITIALIZED_PATHS. Acquiring
    # the cross-process init lock on every connect is what let a single stalled
    # holder (e.g. an external `hermes kanban list` mid-integrity-probe) block
    # the long-lived gateway dispatcher's next-tick connect() forever — an
    # unbounded flock with no timeout, no LOCK_NB, no recovery (#36644). On the
    # steady-state path there is nothing for the cross-process lock to protect
    # (no schema/migration writes run), so skip it entirely and just open the
    # connection with WAL/pragmas under the cheap in-process _INIT_LOCK.
    resolved = str(path.resolve())
    if resolved in _INITIALIZED_PATHS:
        conn = _sqlite_connect(path)
```

**锁 2:调度 tick 单写者锁(非阻塞)。** 防的是**两个调度器**同时写同一个 `kanban.db`:

`hermes_cli/kanban_db.py:1541-1556 @ 863e313`

```python
    Motivation (issue #35240): a ``hermes gateway run --replace`` /
    ``gateway restart`` invoked from a shell on a systemd/launchd host can
    leave an orphan gateway whose dispatcher escapes the service cgroup,
    survives ``systemctl restart``, and becomes a *second* long-lived
    writer on the same ``kanban.db``. Two dispatchers that each believe
    they own the file both pass SQLite ``busy_timeout`` and then race on
    WAL frames — the documented root cause of multi-writer corruption.
    The startup guard (``_guard_supervised_gateway_conflict``) blocks the
    common way an orphan is born, but this lock is the defense-in-depth
    that prevents two dispatchers from ever writing concurrently
    *regardless of how the second one got there*.

    The lock is **non-blocking** on purpose: the gateway's async watcher
    must never stall on a held lock. A losing dispatcher simply skips its
    tick (the winner is making progress on the same board), and tries
    again next interval.
```

三点设计要记住:(a) **非阻塞** —— 输的一方直接跳过这一 tick,绝不等;
(b) **按 board 作用域** —— 锁文件是 `kanban.db` 的 `.dispatch.lock` 兄弟;
(c) **拿不到锁文件时退化为 no-op**(`acquired = True`),探测失败不能阻断调度。

**WAL 截断。** `wal_autocheckpoint=100` 是被动的,在多进程忙板上可能被读者永远饿死:

`hermes_cli/kanban_db.py:1618-1631 @ 863e313`

```python
# Periodic WAL checkpoint state for the dispatcher tick path. The kanban
# connections run with ``wal_autocheckpoint=100``, but a passive
# autocheckpoint can be starved forever on a busy multi-process board (any
# reader with an open snapshot blocks the WAL reset), letting the -wal file
# grow without bound between gateway restarts. Once per coarse interval the
# dispatcher — the board's single writer during a tick, and holding the
# dispatch flock — issues an explicit ``wal_checkpoint(TRUNCATE)``.
# Best-effort: a busy/locked checkpoint is logged at DEBUG and retried next
# interval. Keyed per resolved DB path so multi-board dispatchers checkpoint
# each board on its own clock.
_WAL_CHECKPOINT_INTERVAL_SECONDS = 300.0
_LAST_WAL_CHECKPOINT: dict[str, float] = {}
_WAL_CHECKPOINT_LOCK = threading.Lock()

```

于是调度器在**持有 tick 锁时**(它此刻是唯一写者)每 300 秒显式 `wal_checkpoint(TRUNCATE)` 一次。

**抖动重试。** SQLite 自己的 `busy_timeout` 退避近乎确定性,并发写者会同步重撞:

`hermes_cli/kanban_db.py:2768-2779 @ 863e313`

```python
# SQLite's own busy_timeout uses a near-deterministic backoff, so concurrent
# writers re-collide in lockstep under a stampede. A jittered retry on the
# transaction boundary breaks that convoy. Mirrors state.db's _execute_write:
# a fixed 20-150ms jitter band (a 20ms floor prevents a near-zero retry from
# busy-spinning back into the collision). Only BEGIN IMMEDIATE and COMMIT are
# retried -- both are idempotent re-issues that touch no transaction body, so a
# CAS inside write_txn is never replayed. kanban keeps fewer retries than
# state.db (5 vs 15) because its 120s busy_timeout already absorbs most waits;
# the retry is the backstop for the tail SQLite returns BUSY on immediately.
_BUSY_MAX_RETRIES = 5
_BUSY_RETRY_MIN_S = 0.020  # 20ms
_BUSY_RETRY_MAX_S = 0.150  # 150ms
```

只对 `BEGIN IMMEDIATE` 和 `COMMIT` 两个**幂等的事务边界**重试,事务体绝不重放 ——
否则 `write_txn` 里的 CAS 会被执行两次。

**连接上的五个 PRAGMA** 是这套加固的地基:

`hermes_cli/kanban_db.py:2234-2244 @ 863e313`

```python
                # FULL (was NORMAL): fsync before each checkpoint to narrow the
                # crash window that can leave a b-tree page header torn.
                conn.execute("PRAGMA synchronous=FULL")
                conn.execute("PRAGMA wal_autocheckpoint=100")
                conn.execute("PRAGMA foreign_keys=ON")
                # Zero freed pages so a later torn write cannot expose stale
                # cell content; persisted in the DB header for new DBs.
                conn.execute("PRAGMA secure_delete=ON")
                # Surface corrupt cells as read errors instead of silent
                # wrong-data returns.
                conn.execute("PRAGMA cell_size_check=ON")
```

`synchronous=FULL`(每次 checkpoint 前 fsync,收窄崩溃窗口)、`secure_delete=ON`
(释放页清零,防撕裂写暴露旧 cell)、`cell_size_check=ON`(损坏 cell 报读错误
而不是静默返回错数据)—— 三条都是**用性能换"损坏要吵闹"**。

### 3.9 段 A 里那 330 行业务:schema 漂移与重建

`_migrate_add_optional_columns` 是纯 kanban 内容(逐列 `ALTER TABLE tasks ADD COLUMN`),
但它末尾调用的漂移重建**机制**是通用的,值得单独记:

`hermes_cli/kanban_db.py:2671-2687 @ 863e313`

```python
def _rebuild_drifted_tables(conn: sqlite3.Connection) -> None:
    """Rebuild any kanban table whose column types drifted from SCHEMA_SQL.

    Old boards crash the gateway notifier (``int(None)`` on a NULL id in
    ``unseen_events_for_sub``) and never match the ``id > cursor`` filter, so
    every kanban notification is silently lost (#35096). Each affected table is
    rebuilt with the standard SQLite pattern — CREATE new → INSERT shared
    columns → DROP old → RENAME — recreating its indexes too (DROP TABLE takes
    them down). The legacy TEXT ids are dropped (they aren't valid integers);
    AUTOINCREMENT assigns fresh ones and ``last_event_id`` cursors reset to 0,
    so the first post-migration tick replays a task's event history once —
    the safe failure mode for a feature that was already fully broken.

    The whole pass runs in one transaction so an interruption can't leave a
    table half-renamed, and under ``connect()``'s init locks so nothing races
    it. Idempotent: a correctly-typed DB skips every table and returns without
    opening a transaction.
```

老板子把 `id` 建成 `TEXT PRIMARY KEY`,而 `CREATE TABLE IF NOT EXISTS` 跳过已存在的表、
`_add_column_if_missing` 只加列 —— **两者都修不了列类型漂移**,只能重建。
重建走 SQLite 的标准四步(RENAME → CREATE → INSERT 共有列 → DROP),整个过程在一个事务里,
并且重建后要重建索引(DROP TABLE 会把索引一起带走)。**失败模式是"事件历史被重放一次",
对一个本来就完全坏掉的功能来说这是安全的失败方向。**

---

## 4. 精读段 B:进程监管器

### 4.1 先看一次真实故障:被 cgroup 节流的 worker 引发的复制风暴

场景:一个 worker 被 `memory.high` 节流,卡在**不可中断睡眠(D 态)**。调度器发现它的
claim 过期了,于是"回收"这张卡 —— 把状态改回 `ready`、清掉 `claim_lock`。下一 tick,
调度器看见一张 ready 卡,**又 spawn 一个 worker**。而第一个 worker 并没有死:
`SIGKILL` 在 D 态下投递不了,要等节流解除。于是同一张卡上有两个 worker 在写同一个工作区。
再下一 tick,又一个。

修法不是"杀得更狠",而是**杀不掉就不回收**:

`hermes_cli/kanban_db.py:7079-7092 @ 863e313`

```python
def _worker_survived_termination(termination: dict) -> bool:
    """True when we tried to kill our own host-local worker and it is still alive.

    Reclaiming in this state would release the claim and let the dispatcher
    spawn a second worker while the first is still running — the duplication
    loop. Only host-local workers we actually signalled count: a non-local
    claim lock or a no-op attempt (no ``os.kill`` available) must fall through
    to the normal release path, since we cannot manage that worker anyway.
    """
    return bool(
        termination.get("termination_attempted")
        and termination.get("host_local")
        and not termination.get("terminated")
    )
```

判定要同时满足三条:确实尝试过终止、确实是本机自己的 worker、且**它还活着**。
非本机的锁、或者根本没有 `os.kill` 可用的平台,都必须走正常释放路径 ——
"我管不了的 worker"不能拿来当作不回收的理由。

不回收时做的是**续租 + 留痕**:

`hermes_cli/kanban_db.py:7104-7111 @ 863e313`

```python
    """Hold a claim whose worker survived termination instead of releasing it.

    Extends ``claim_expires`` by ``RECLAIM_DEFER_GRACE_SECONDS`` so the task
    stays ``running`` (no duplicate spawn) and records a ``reclaim_deferred``
    event so the hold is visible in ``hermes kanban tail``. The next dispatch
    tick retries the kill; this is self-correcting because not spawning a
    duplicate is what lets the throttled worker finally die.
    """
```

最后一句是这个设计的关键:**"不 spawn 副本"本身就是让被节流的 worker 最终能死掉的原因** ——
不再制造新的内存压力,节流解除,信号落地,下一 tick 干净回收。**这是一个自纠正的循环,
不是一个定时器。**

### 4.2 它监管谁

只监管**本机、由本调度器 spawn 的** worker 子进程。判据是 claim_lock 的主机前缀:

`hermes_cli/kanban_db.py:7561-7566 @ 863e313`

```python
        host_prefix = f"{_claimer_id().split(':', 1)[0]}:"
        for row in rows:
            # Only check liveness for claims owned by this host.
            lock = row["claim_lock"] or ""
            if not lock.startswith(host_prefix):
                continue
```

`_claimer_id()` 形如 `<host>:<pid>:<random>`,取第一段做前缀。跨主机的 PID 在本机没有意义。
文档也明写这是单主机设计(见 §5 ◎-1)。

### 4.3 怎么判活:四条相互独立的证据

```text
  证据           来源                              抓什么                      失效场景
  (1) 进程存在   _pid_alive → gateway.status       进程还在进程表里            僵尸态会误报"活"→ 见下
                 ._pid_exists + /proc State: Z
  (2) 退出状态   waitpid 登记表 _recent_worker_exits 退出码/信号,区分四种死法  pid 被别人回收 → "unknown"
  (3) 心跳       tasks.last_heartbeat_at            进程活着但逻辑死循环        worker 不主动打卡就没有
  (4) 墙钟       task_runs.started_at + max_runtime  这次尝试跑太久了            —
```

(1) 里的僵尸处理是整段最容易被忽略、也最必要的一条:

`hermes_cli/kanban_db.py:6965-6975 @ 863e313`

```python
    **Zombie handling:** the existence check succeeds against zombie
    processes (post-exit, pre-reap) because the process table entry
    still exists. A worker that exits without being reaped by its
    parent would stay "alive" to the dispatcher forever. Dispatcher
    workers are started via ``start_new_session=True`` + intentional
    Popen handle abandonment, so init reaps them quickly — but during
    the window between exit and reap, we'd otherwise see stale "alive"
    signals. On Linux we peek at ``/proc/<pid>/status`` and treat
    ``State: Z`` as dead. On macOS we ask ``ps`` for the BSD ``stat``
    field and treat values containing ``Z`` as dead.
    """
```

`os.kill(pid, 0)` 对**僵尸进程**返回成功(进程表项还在,只是没被回收),所以只靠它
会把一个已经退出的 worker 永远当成"活着"。Linux 上读 `/proc/<pid>/status` 的 `State:` 行:

`hermes_cli/kanban_db.py:6983-6996 @ 863e313`

```python
    if sys.platform == "linux":
        try:
            with open(f"/proc/{int(pid)}/status", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("State:"):
                        # "State:\tZ (zombie)" → dead
                        if "Z" in line.split(":", 1)[1]:
                            return False
                        break
        except (FileNotFoundError, PermissionError, OSError):
            # proc entry gone → already reaped; treat as dead.
            # PermissionError shouldn't happen for our own children but
            # be defensive.
            pass
```

macOS 上没有 `/proc`,退回 `ps -o stat=`(BSD 状态字段含 `Z` 即僵尸),带 1 秒超时。
Windows 上则**绝不能**用 `os.kill(pid, 0)`:

`hermes_cli/kanban_db.py:6960-6963 @ 863e313`

```python
    **DO NOT** use ``os.kill(pid, 0)`` directly on Windows — Python's
    Windows ``os.kill`` treats ``sig=0`` as ``CTRL_C_EVENT`` (bpo-14484)
    and will broadcast it to the target's console group, potentially
    killing unrelated processes.
```

Python 在 Windows 上把 `sig=0` 当成 `CTRL_C_EVENT`(bpo-14484),会广播到目标的控制台组,
**一次"检查存活"可能杀掉一串无关进程**。这条注释本身就值得抄进任何跨平台监管器。

(3) 心跳为什么必须与 (1) 正交:

`hermes_cli/kanban_db.py:7143-7148 @ 863e313`

```python
    """Record a ``heartbeat`` event + touch ``last_heartbeat_at``.

    Called by long-running workers as a liveness signal orthogonal to
    the PID check. A worker that forks a long-lived child (train loop,
    video encode, web crawl) can have its Python still alive while the
    actual work process is stuck; periodic heartbeats catch that.
```

worker 可以 fork 一个长跑子进程(训练循环、视频编码、爬虫),Python 主体还活着而实际
工作已经卡死 —— 只有心跳能抓到。

### 4.4 怎么重启:两个互不消耗的失败预算

**预算 1:统一失败计数器 `consecutive_failures`。** spawn 失败、超时、崩溃全部汇到一处:

`hermes_cli/kanban_db.py:7843-7867 @ 863e313`

```python
    if failure_limit is None:
        failure_limit = DEFAULT_FAILURE_LIMIT
    blocked = False
    with write_txn(conn):
        row = conn.execute(
            "SELECT consecutive_failures, status, max_retries "
            "FROM tasks WHERE id = ?", (task_id,),
        ).fetchone()
        if row is None:
            return False
        failures = int(row["consecutive_failures"]) + 1

        # Per-task override wins over both caller-supplied and default
        # thresholds. None (the common case) falls through.
        task_override = (
            row["max_retries"] if "max_retries" in row.keys() else None
        )
        if task_override is not None:
            effective_limit = int(task_override)
            limit_source = "task"
        else:
            effective_limit = int(failure_limit)
            limit_source = "dispatcher"

        if force_trip or failures >= effective_limit:
```

阈值解析顺序是 **每卡 `max_retries` > 调用方传入 `failure_limit` > `DEFAULT_FAILURE_LIMIT`(2)**。
跳闸后卡片从 `ready`/`running` 变 `blocked` 并发 `gave_up` 事件。

**预算 2:协议违规连击(独立)。** "worker 退出码 0,但卡片还在 running" —— 它没调
`kanban_complete`/`kanban_block`:

`hermes_cli/kanban_db.py:7447-7459 @ 863e313`

```python
# Empirically ~96% of "clean exit without a terminal tool call" tasks complete
# on a later run (a goal-mode finalize nudge, or the model simply emitting the
# tool call next time), so a protocol violation is NOT deterministic — give it a
# bounded retry before the breaker trips instead of blocking on the first hit.
#
# The budget is a violation-only STREAK, not a share of the unified
# ``consecutive_failures`` counter: it counts consecutive clean-exit protocol
# violations (derived from run history by ``_protocol_violation_streak``), so
# earlier timeouts / nonzero exits neither consume nor extend it, and a
# below-budget violation does not tick the unified counter either. A per-task
# ``max_retries`` overrides this bound — the same "task override wins"
# precedence ``_record_task_failure`` documents for every other failure kind.
_PROTOCOL_VIOLATION_FAILURE_LIMIT = 3
```

**这两个预算刻意互不消耗**:一次低于预算的协议违规**不**递增 `consecutive_failures`,
而更早的超时/非零退出也**不**消耗违规预算。理由是经验数据("~96% 的协议违规任务在后续
某次运行里完成"),所以第一次违规不应该等同于一次真失败。streak 的统计还刻意跳过
`rate_limited` 运行 —— 配额墙对任务本身不构成任何证据:

`hermes_cli/kanban_db.py:7495-7514 @ 863e313`

```python
    for row in rows:
        outcome = row["outcome"] or ""
        if outcome == "rate_limited":
            continue
        if outcome == "crashed":
            is_violation = False
            raw_meta = row["metadata"]
            if raw_meta:
                try:
                    is_violation = bool(
                        json.loads(raw_meta).get("protocol_violation")
                    )
                except (ValueError, TypeError):
                    is_violation = False
            if not is_violation:
                is_violation = "protocol violation" in (row["error"] or "")
            if is_violation:
                streak += 1
                continue
        break
```

**配额墙走的是第三条路:既不是失败也不是崩溃。** worker 用 `EX_TEMPFAIL`(75)退出:

`hermes_cli/kanban_db.py:274-282 @ 863e313`

```python
# Sentinel exit code a kanban worker uses to signal "I bailed because the
# provider rate-limited / exhausted quota, not because the task failed."
# The dispatcher's reap classifier maps this to a ``rate_limited`` exit kind
# so ``detect_crashed_workers`` can release the task back to ``ready``
# WITHOUT counting a failure (the circuit breaker must never trip on a
# transient throttle). 75 == BSD ``EX_TEMPFAIL`` (sysexits.h) — the
# conventional "temporary failure, retry later" code, and well clear of the
# 0/1/2 codes the worker uses for success / generic failure / usage error.
KANBAN_RATE_LIMIT_EXIT_CODE = 75
```

`detect_crashed_workers` 认出这个码后把卡片放回 `ready`,**不计失败**,只盖一个错误文本
供重生闸门识别:

`hermes_cli/kanban_db.py:7665-7675 @ 863e313`

```python
                if rate_limited_exit:
                    # Stamp the failure-error column so ``check_respawn_guard``
                    # recognizes this as a quota blocker and defers the
                    # respawn until the window clears — WITHOUT touching
                    # ``consecutive_failures`` (that's the whole point: no
                    # breaker trip on a throttle).
                    conn.execute(
                        "UPDATE tasks SET last_failure_error = ? WHERE id = ?",
                        (error_text[:500], row["id"]),
                    )
                    rate_limited.append(row["id"])
```

### 4.5 重启风暴保护:四道闸 + 一道冷却

`check_respawn_guard` 在每 tick、每张 ready 卡、抢占之前跑,返回非空即**这一 tick 不 spawn**:

`hermes_cli/kanban_db.py:8012-8018 @ 863e313`

```python
def check_respawn_guard(conn: sqlite3.Connection, task_id: str) -> Optional[str]:
    """Return a guard reason if ``task_id`` should NOT be re-spawned, else None.

    Called per ready task in ``dispatch_once`` before any claim attempt.
    Returning a reason defers the spawn this tick; the task stays in
    ``ready`` and gets another chance on the next dispatcher tick.

```

四道闸的顺序本身是一个 bug 修复:

`hermes_cli/kanban_db.py:8069-8078 @ 863e313`

```python
    # 1. Rate-limit cooldown. The most recent run ended ``rate_limited``
    #    (quota wall) — defer while inside the cooldown window, then allow a
    #    cheap probe. Must run BEFORE the blocker_auth regex check, because a
    #    rate-limit requeue stamps a quota-flavored last_failure_error that
    #    the regex would otherwise match → defer forever (no failure counter
    #    increment on this path means the breaker can never free it).
    #
    #    We look at the LATEST run only (ORDER BY ended_at DESC LIMIT 1): if a
    #    newer crash/completion superseded the rate-limit run, this guard
    #    no longer applies and the normal paths take over.
```

**为什么 `rate_limit_cooldown` 必须排在 `blocker_auth` 前面**:限流回队时盖的错误文本
("exited rate-limited (quota wall)")会被 `blocker_auth` 的配额正则**匹配上**;而限流路径
**从不递增** `consecutive_failures`,所以熔断器永远救不了它 —— 卡片会被 `blocker_auth`
永久扣住。冷却窗口走完必须 `return None` 提前返回,而不是落到正则那一步:

`hermes_cli/kanban_db.py:8090-8103 @ 863e313`

```python
        if rl_cooldown <= 0:
            # Cooldown disabled — respawn immediately, and skip the
            # blocker_auth regex so the stamped rate-limit text doesn't
            # re-trap the task.
            return None
        ended_at = latest_run["ended_at"]
        if ended_at is not None and (now - int(ended_at)) < rl_cooldown:
            return "rate_limit_cooldown"
        # Cooldown elapsed — allow the respawn. Return early so the
        # blocker_auth check below doesn't catch the rate-limit text we
        # stamped on the task; this path intentionally retries forever
        # (cheaply, spaced by the cooldown) until quota returns or a real
        # crash/completion supersedes it.
        return None
```

另外两道闸:`recent_success`(窗口 1 小时内有 completed 运行)带一个**显式反悔通道** ——
如果那次成功**之后**又来了显式重排事件(状态改动 / promoted / unblocked / reclaimed),
说明人类是故意要重跑的:

`hermes_cli/kanban_db.py:8110-8133 @ 863e313`

```python
    # 3. Completed run within guard window — proof of recent success.
    #    Exception: an explicit re-queue AFTER that success (an operator
    #    dragging done→ready, a dependency re-promotion, an unblock, a
    #    reclaim) is a deliberate "run it again" — honor it instead of
    #    deferring. Without this, a manual done→ready just sits there,
    #    silently held by the guard, until the window elapses.
    cutoff = now - _RESPAWN_GUARD_SUCCESS_WINDOW
    recent_completed = conn.execute(
        "SELECT ended_at FROM task_runs "
        "WHERE task_id = ? AND outcome = 'completed' AND ended_at >= ? "
        "ORDER BY ended_at DESC LIMIT 1",
        (task_id, cutoff),
    ).fetchone()
    if recent_completed:
        completed_at = int(recent_completed["ended_at"] or 0)
        requeued_after = conn.execute(
            "SELECT 1 FROM task_events "
            "WHERE task_id = ? AND created_at >= ? "
            "AND kind IN ('status', 'promoted', 'unblocked', 'reclaimed') "
            "LIMIT 1",
            (task_id, completed_at),
        ).fetchone()
        if not requeued_after:
            return "recent_success"
```

`active_pr`(24 小时内评论里出现 GitHub PR 链接)防的是**重复开 PR**。

**还有一层是并发上限而非退避**:全局 `max_spawn` 被明确定义成**在跑并发数**而不是每 tick 预算:

`hermes_cli/kanban_db.py:8304-8310 @ 863e313`

```python
    ``max_spawn`` is a **live concurrency cap**, not a per-tick spawn budget:
    it counts tasks already in ``status='running'`` plus this tick's spawns
    against the limit. So ``max_spawn=4`` means "at most 4 workers running
    at any time across the whole board" — matching the gateway's stated
    intent ("limit concurrent kanban tasks"). With a per-tick interpretation
    a 60-second tick interval could grow concurrency by N every minute on a
    busy board and accumulate without bound.
```

按每 tick 预算解释的话,60 秒一 tick 的板子每分钟并发涨 N,无上限。另有
`max_in_progress`(全局)与 `max_in_progress_per_profile`(单 profile,防某个 profile
的本地模型/配额/浏览器池被扇出打爆)。

### 4.6 僵尸与孤儿

**孤儿**:worker 用 `start_new_session=True` 起,并且**故意不保留 Popen 句柄**:

`hermes_cli/kanban_db.py:9155-9164 @ 863e313`

```python
        proc = subprocess.Popen(  # noqa: S603 -- argv is a fixed list built above
            cmd,
            cwd=workspace if os.path.isdir(workspace) else None,
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
            creationflags=subprocess.CREATE_NO_WINDOW if _IS_WINDOWS else 0,
        )
```

`hermes_cli/kanban_db.py:9171-9176 @ 863e313`

```python
    # NOTE: we intentionally do NOT close log_f here — we want Popen's
    # child process to keep writing after this function returns.  The
    # handle is kept alive by the child's inheritance.  The parent's
    # reference goes out of scope and is GC'd, but the OS-level FD stays
    # open in the child until the child exits.
    return proc.pid
```

日志 fd 不关是为了让子进程继续写;进程组独立是为了让调度器崩溃时不连坐 worker。
代价就是**这些子进程会变成僵尸**,必须显式回收:

`hermes_cli/kanban_db.py:6930-6950 @ 863e313`

```python
def reap_worker_zombies() -> "list[int]":
    """Reap all zombie children of this process without blocking.

    Returns the list of reaped PIDs. Safe to call when there are no
    children (returns []). No-op on Windows.
    """
    reaped: "list[int]" = []
    if os.name != "nt":
        try:
            while True:
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    break
                if pid == 0:
                    break
                _record_worker_exit(pid, status)
                reaped.append(pid)
        except Exception:
            pass
    return reaped
```

回收到的退出状态存进一张**有界**的登记表,供后续分类:

`hermes_cli/kanban_db.py:6851-6861 @ 863e313`

```python
# Bounded registry of recently-reaped worker child exits, populated by the
# reap loop at the top of ``dispatch_once`` and consulted by
# ``detect_crashed_workers`` to classify a dead-pid task.
#
# Entry: ``pid -> (raw_wait_status, reaped_at_epoch)``. We keep raw status
# so both ``os.WIFEXITED`` / ``os.WEXITSTATUS`` and ``os.WIFSIGNALED`` can
# be consulted. Entries are trimmed by age (and total size cap as a
# belt-and-braces against unbounded growth on exotic platforms).
_RECENT_WORKER_EXIT_TTL_SECONDS = 600
_RECENT_WORKER_EXITS_MAX = 4096
_recent_worker_exits: "dict[int, tuple[int, float]]" = {}
```

分类器把退出状态翻译成五种死法,每种对应不同处置:

`hermes_cli/kanban_db.py:6915-6927 @ 863e313`

```python
    try:
        if os.WIFEXITED(raw):
            code = os.WEXITSTATUS(raw)
            if code == 0:
                return ("clean_exit", 0)
            if code == KANBAN_RATE_LIMIT_EXIT_CODE:
                return ("rate_limited", code)
            return ("nonzero_exit", code)
        if os.WIFSIGNALED(raw):
            return ("signaled", os.WTERMSIG(raw))
    except Exception:
        pass
    return ("unknown", None)
```

`unknown`(pid 不在登记表里)的存在本身就是一条设计线索:**它承认"这个 pid 可能被别人
回收了"**。这条承认在 §5 的 ■-2 里会变成一个真实的风险面。

### 4.7 七条回收路径一览

```text
  路径                    触发条件                              终止 worker  计失败  卡片去向
  release_stale_claims    claim_expires 过期                     是(本机)   否     ready
    └ 活进程续租          PID 活 且 心跳不陈旧                    否           否     running(延长)
    └ 心跳陈旧兜底        PID 活 但心跳 > 1h                     是           否     ready
  detect_stale_running    运行 > stale_timeout 且 心跳 > 1h      是           否     ready
  detect_crashed_workers  PID 已死(过 30s 启动宽限)            —            视死法  ready / blocked
    └ clean_exit(rc=0)   协议违规                                —            连击预算 ready→(超预算)blocked
    └ rate_limited(75)   配额墙                                  —            否     ready(带冷却)
    └ nonzero / signaled  真崩溃                                  —            是     ready→(超限)blocked
  enforce_max_runtime     本次尝试超 max_runtime_seconds         是(TERM→KILL)是     ready→(超限)blocked
  _defer_reclaim...       杀不掉本机 worker                       已试         否     running(+120s)
```

**"计失败"那一列是整个监管器最难的一处判断**:stale 回收明确**不**计失败,注释写了理由 ——
它是调度器侧的"没看到心跳",不是 worker 出错;把它计进失败会让两个合法的长任务
(>4h 且没显式心跳)把自己熔断掉。

---

## 5. 本轮定案:■ 2 条 / ▲ 2 条 / ◇ 4 条 / ◎ 1 条

### ■-1 隔离失败时,自愈仍然改库,且日志声称"副本已保留"

**这是段 A 里唯一一处 fail-open,而它恰好破坏的是该模块反复声明的那条不变量。**

代码自己的契约(两处,一处在实现里,一处在 CLI 帮助里):

`hermes_cli/kanban_db.py:2016-2018 @ 863e313`

```python
    # Quarantine FIRST — both the repair path and the fail-closed path
    # preserve the pre-touch bytes before anything mutates the file.
    backup = _backup_corrupt_db(resolved)
```

`hermes_cli/kanban.py:941-945 @ 863e313`

```python
            "('wrong # of entries in index <name>' / 'row N missing from "
            "index <name>'), the corrupt file is quarantined to a "
            ".corrupt.<hash>.bak sibling first and the damaged indexes are "
            "rebuilt with REINDEX — the same narrow auto-repair the "
            "connect-time guard applies. Any other corruption class is "
```

而 `_backup_corrupt_db` 是可以返回 `None` 的(见 §3.5:`has_live_connection` 拒绝、
读文件 `OSError`、`shutil.copy2` `OSError`)。返回 `None` 之后,**没有任何分支检查它**:

`hermes_cli/kanban_db.py:2018-2027 @ 863e313`

```python
    backup = _backup_corrupt_db(resolved)
    index_names = _repairable_index_names(messages)
    if index_names:
        _log.warning(
            "kanban DB %s failed integrity_check with index-only errors "
            "(%s); pre-repair backup at %s — attempting REINDEX auto-repair.",
            resolved, ", ".join(index_names),
            backup if backup is not None else "<backup failed>",
        )
        repaired, post = _attempt_index_reindex_repair(resolved, index_names)
```

`repair_db`(`hermes kanban repair` 的实现)是同一形状:

`hermes_cli/kanban_db.py:2125-2134 @ 863e313`

```python
        backup = _backup_corrupt_db(resolved)
        index_names = _repairable_index_names(messages)
        if not index_names:
            return RepairResult(
                status="corrupt",
                db_path=resolved,
                messages=messages,
                backup_path=backup,
            )
        repaired, post = _attempt_index_reindex_repair(resolved, index_names)
```

**可复现判据(输入 → 现象)。** 输入:一个只有索引损坏的板库 + 一次会失败的隔离拷贝
(用 `ENOSPC` 模拟磁盘满 —— 而磁盘满正是最常见的 SQLite 损坏成因之一)。

```verify
cd /home/user/hermes-agent && PYTHONDONTWRITEBYTECODE=1 /home/user/hermes-venv/bin/python - <<'PY'
import os, shutil, sqlite3, sys, tempfile
from pathlib import Path
tmp = Path(tempfile.mkdtemp(prefix="kb-quarantine-"))
os.environ["HERMES_HOME"] = str(tmp / "home")
sys.path.insert(0, "/home/user/hermes-agent")
from hermes_cli import kanban_db as kb

db = tmp / "kanban.db"
kb._INITIALIZED_PATHS.discard(str(db.resolve()))
kb.init_db(db_path=db)
conn = kb.connect(db_path=db)
for i in range(12):
    kb.create_task(conn, title=f"task-{i}")
conn.close()
kb._INITIALIZED_PATHS.discard(str(db.resolve()))

# 制造 index-only 损坏:临时把索引改写成 "WHERE 0" 的部分索引、在这个谎言下 REINDEX
# 掏空它的 b-tree,再把 schema 改回去。integrity_check 于是只报 index-scoped 错误。
name = "idx_tasks_status"
c = sqlite3.connect(db, isolation_level=None)
orig = c.execute("SELECT sql FROM sqlite_master WHERE name = ?", (name,)).fetchone()[0]
c.execute("PRAGMA writable_schema=ON")
c.execute("UPDATE sqlite_master SET sql = ? WHERE name = ?", (orig + " WHERE 0", name))
c.execute("PRAGMA writable_schema=OFF"); c.close()
c = sqlite3.connect(db, isolation_level=None)
c.execute(f'REINDEX "{name}"')
c.execute("PRAGMA writable_schema=ON")
c.execute("UPDATE sqlite_master SET sql = ? WHERE name = ?", (orig, name))
c.execute("PRAGMA writable_schema=OFF"); c.close()
kb._INITIALIZED_PATHS.discard(str(db.resolve()))

def integrity(path):
    c = sqlite3.connect(path)
    try:
        return [r[0] for r in c.execute("PRAGMA integrity_check").fetchall()]
    finally:
        c.close()

print("pre-repair integrity_check:", integrity(db)[:2])

def boom(*a, **k):                      # 模拟磁盘满,恰好打在隔离拷贝上
    raise OSError(28, "No space left on device")
shutil.copy2 = boom
kb.shutil.copy2 = boom

conn = kb.connect(db_path=db); conn.close()   # 连接时闸门在这里跑

print("quarantine files:", [q.name for q in tmp.glob("kanban.db.corrupt.*.bak")])
print("post-repair integrity_check:", integrity(db))
PY
```

现象(实测输出,逐字):

```console
pre-repair integrity_check: ['row 1 missing from index idx_tasks_status', 'row 2 missing from index idx_tasks_status']
kanban DB /tmp/kb-quarantine-.../kanban.db failed integrity_check with index-only errors (idx_tasks_status); pre-repair backup at <backup failed> — attempting REINDEX auto-repair.
kanban DB /tmp/kb-quarantine-.../kanban.db auto-repaired via REINDEX (idx_tasks_status); integrity_check now clean. Pre-repair copy kept at <backup failed>.
quarantine files: []
post-repair integrity_check: ['ok']
```

**三处问题,按严重度排:**

1. 隔离失败(`<backup failed>`)之后**仍然执行了 REINDEX**,即在没有任何取证副本的情况下
   改写了用户的板库。这与第 2016–2017 行注释、以及 CLI 帮助里的 "quarantined … first"
   直接矛盾。
2. 第二条日志说 `Pre-repair copy kept at <backup failed>` —— 字面读作"副本保留在
   `<backup failed>` 这个路径",**是一条主动误导的日志**。用户会去找这个文件。
3. 触发条件与损坏成因高度相关:磁盘满既是损坏的常见成因,又是拷贝失败的常见成因。
   **最需要取证副本的那一刻,恰好是最容易拿不到它的那一刻。**

**修法很小**:`if backup is None: raise KanbanDbCorruptError(...)`(guard 路径)/
`return RepairResult(status="corrupt", ...)`(repair_db 路径)—— 即把这一处对齐到
模块其余部分一致的 fail-closed 取向。`_backup_corrupt_db` 里那段"宁可丢取证副本也不
损坏正在抢救的库"的注释(1815–1817 行)说明作者在**那一层**已经想过这个权衡,
只是没有在**调用层**把 `None` 接住。

**搜索面(负结论)**:`_backup_corrupt_db` 在非测试代码里共 5 处出现 —— 1 处定义(1786)、
1 处**文档字符串引用**(2076,`repair_db` 的 docstring,正是那句
"quarantined … BEFORE any mutation")、**3 处调用**(2018、2119、2125)。其中 2119 在 `repair_db` 的
`except sqlite3.DatabaseError` 分支里,结果直接进 `RepairResult(status="corrupt")`、
**后面不做任何修改动作**,因此无害;有害的是 2018 与 2125 这两处 ——
它们后面紧跟 REINDEX,而**两处都不检查返回值是否为 `None`**。
`grep -rn "backup failed" tests/` **0 命中**,即该分支没有任何测试覆盖。

```verify
cd /home/user/hermes-agent && grep -rn "_backup_corrupt_db" --include=*.py . | grep -v "^./tests"; echo "--- tests mentioning the failed-backup branch ---"; grep -rn "backup failed" tests/ | wc -l
```

### ■-2 `reap_worker_zombies()` 用 `waitpid(-1)`,会替网关进程里**别人的**子进程收尸

`hermes_cli/kanban_db.py:6936-6950 @ 863e313`

```python
    reaped: "list[int]" = []
    if os.name != "nt":
        try:
            while True:
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    break
                if pid == 0:
                    break
                _record_worker_exit(pid, status)
                reaped.append(pid)
        except Exception:
            pass
    return reaped
```

`os.waitpid(-1, WNOHANG)` 回收的是**本进程的任意子进程**,不区分是不是 kanban worker。
而这个函数默认跑在**网关进程**里,每个调度 tick 一次,并且是在**工作线程**上:

`gateway/kanban_watchers.py:1424-1433 @ 863e313`

```python
            try:
                # Reap zombie children before per-board work so a board DB
                # failure cannot block cleanup of unrelated workers.
                pids = await asyncio.to_thread(_kb.reap_worker_zombies)
                if pids:
                    logger.info(
                        "kanban dispatcher: reaped %d zombie worker(s), pids=%s",
                        len(pids),
                        pids,
                    )
```

同一个网关进程里还有别人的子进程。举一个窗口最宽的:后台进程注册表 —— 它 spawn 之后
**立刻返回**,退出码要等到很久以后 `poll()` 才读:

`tools/process_registry.py:781-793 @ 863e313`

```python
        proc = subprocess.Popen(
            [user_shell, "-lic", f"set +m; {safe_command}"],
            text=True,
            cwd=session.cwd,
            env=bg_env,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            **_popen_kwargs,
        )
```

**可复现判据(输入 → 现象)。** 输入:同进程内一个 `Popen` 子进程先退出,随后一次
`waitpid(-1, WNOHANG)` 抢先回收,再由属主调 `wait()`。

```verify
/home/user/hermes-venv/bin/python - <<'PY'
import os, subprocess, sys, time
p = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(42)"])
time.sleep(1.0)                       # 让它退出并变成僵尸
reaped = []                           # 调度器的回收循环:waitpid(-1),不区分是谁的子进程
while True:
    try:
        pid, status = os.waitpid(-1, os.WNOHANG)
    except ChildProcessError:
        break
    if pid == 0:
        break
    reaped.append((pid, os.WEXITSTATUS(status) if os.WIFEXITED(status) else None))
print("stray reaper saw:", reaped)
print("owner Popen.wait() ->", p.wait())
print("real exit code was 42")
PY
```

现象(实测;`pid` 每次不同,退出码那两个数字是恒定的):

```console
stray reaper saw: [(23180, 42)]
owner Popen.wait() -> 0
real exit code was 42
```

**属主拿到的退出码是 0,真实退出码是 42。** 机制是 CPython `subprocess.Popen._try_wait`
在 `ChildProcessError` 时把状态当成 `0`(注释原文:"This child is dead, we can't get the
status")。也就是说 **一个失败的后台命令会被报成成功**。

**诚实的范围界定**:
- 同步 `Popen` + 延后 `poll()`/`wait()`(后台进程注册表就是这个形状)**窗口很宽**,风险实在;
- `asyncio.create_subprocess_exec`(网关里的 `ffprobe`、`/exec` 快命令等)的
  `ThreadedChildWatcher` 已经**阻塞在** `waitpid(pid, 0)` 上,实测三次都是它赢,
  窗口窄得多。我没有构造出稳定复现,不主张这一侧;
- 我**没有**在生产日志里观察到这个错误发生,这是一条**机制层面**的缺陷断言,
  不是一条已发生事故的报告。

**搜索面**:`grep -rn "waitpid" --include=*.py .` 全仓 —— `os.waitpid(-1, ...)`
仅此一处(其余 `waitpid` 均带具体 pid)。同进程共存的 spawn 点由
`grep -rn "subprocess.Popen(\|create_subprocess_" --include=*.py tools/ gateway/ agent/` 枚举。

```verify
cd /home/user/hermes-agent && grep -rn "os\.waitpid" --include=*.py . | grep -v "^./tests"
```

实测只有三处:`scripts/profile-tui.py:458` 与 `:464` 都带具体 pid(只等自己的孩子),
`hermes_cli/kanban_db.py:6941` 是**唯一**一处 `waitpid(-1, ...)`。

**代码自己已经知道这件事**:`_classify_worker_exit` 的 `unknown` 分支注释写的正是
"pid was not in the reap registry (either reaped by something else, …)"。
缺的是**反向**的那一半 —— 它自己就是那个 "something else"。

### ▲-1 文档说熔断器只数 **spawn** 失败,代码数的是**所有**非成功结局

文档(`## Core concepts` 标题下的 Dispatcher 条目,整条一并判定):

`website/docs/user-guide/features/kanban.md:69 @ 863e313`

> - **Dispatcher** — a long-lived loop that, every N seconds (default 60): reclaims stale claims, reclaims crashed workers (PID gone but TTL not yet expired), promotes ready tasks, atomically claims, spawns assigned profiles. Runs **inside the gateway** by default (`kanban.dispatch_in_gateway: true`). One dispatcher sweeps all boards per tick; workers are spawned with `HERMES_KANBAN_BOARD` pinned so they can't see other boards. After `kanban.failure_limit` consecutive spawn failures on the same task (default: 2) the dispatcher auto-blocks it with the last error as the reason — prevents thrashing on tasks whose profile doesn't exist, workspace can't mount, etc.

这一条 bullet 里的断言逐条判定:tick 默认 60 秒 **成立**、
`dispatch_in_gateway: true` 默认 **成立**、"一个 dispatcher 每 tick 扫全部 board" **成立**、
"worker 被钉上 `HERMES_KANBAN_BOARD`" **成立**(见 §2.5 的 `_default_spawn` 摘录);
**只有最后一句不成立** —— 阈值数的不是 "consecutive spawn failures",而是统一计数器:

`hermes_cli/kanban_db.py:7800-7807 @ 863e313`

```python
    """Record a non-success outcome (spawn_failed / crashed / timed_out)
    and maybe trip the circuit breaker.

    Unified replacement for the old spawn-only ``_record_spawn_failure``.
    Every path that ends a task with a non-success outcome funnels
    through here so the ``consecutive_failures`` counter and the
    auto-block threshold stay consistent.

```

差别是可观测的:一张卡片**每次都 spawn 成功**、但连续两次 `timed_out`,按文档不该被
auto-block(它一次 spawn 失败也没有),按代码会被 block。`enforce_max_runtime` 结尾
显式调用 `_record_task_failure(outcome="timed_out")` 即是证据:

`hermes_cli/kanban_db.py:7284-7297 @ 863e313`

```python
        # Increment the unified failure counter. Outside the write_txn
        # above because ``_record_task_failure`` opens its own. If the
        # breaker trips, this flips the task ``ready → blocked`` and
        # emits a ``gave_up`` event on top of the ``timed_out`` we
        # already emitted.
        if cur.rowcount == 1:
            _record_task_failure(
                conn, tid,
                error=f"elapsed {int(elapsed)}s > limit {int(row['max_runtime_seconds'])}s",
                outcome="timed_out",
                release_claim=False,
                end_run=False,
                event_payload_extra={"pid": pid, "sigkill": killed},
            )
```

文档句尾举的例子("profile doesn't exist, workspace can't mount")也全是 spawn 类,
说明这半句整体停留在旧语义上 —— 不是一处措辞,是一处**未跟上重构**的地图。

前两个"成立"的取证(免得下一轮重做):

`gateway/kanban_watchers.py:991-995 @ 863e313`

```python
        if not kanban_cfg.get("dispatch_in_gateway", True):
            logger.info(
                "kanban dispatcher: disabled via config kanban.dispatch_in_gateway=false"
            )
            return
```

`gateway/kanban_watchers.py:1029-1036 @ 863e313`

```python
            interval = float(kanban_cfg.get("dispatch_interval_seconds", 60) or 60)
        except (ValueError, TypeError):
            logger.warning(
                "kanban dispatcher: invalid dispatch_interval_seconds=%r, using default 60",
                kanban_cfg.get("dispatch_interval_seconds"),
            )
            interval = 60.0
        interval = max(interval, 1.0)  # sanity floor — tighter than this is a footgun
```

**按 CLAUDE.md 的规矩把整条 bullet 判完的收益,这里正好演示了一次**:如果只挑
"failure_limit" 那半句来判,读者会以为整条 bullet 都可疑;逐条判完之后,可疑的范围
被压缩到确切的一句,其余四句可以放心引用。

### ▲-2 事件参考表把 `respawn_guarded` 的 reason 列成三个,代码有四个

文档(`## Event reference` 标题下的表格行,整行一并判定):

`website/docs/user-guide/features/kanban.md:1026 @ 863e313`

> | `respawn_guarded` | `{reason}` | Dispatcher refused to re-spawn this ready task this tick. Reasons: `blocker_auth` (last failure was a quota/auth/429 error — wait for the rate window to reset), `recent_success` (a completed run happened in the last hour — wait for review before re-running), `active_pr` (a GitHub PR URL appears in a recent comment — a prior worker already opened a PR). The task stays in `ready`; the next tick gets another chance to spawn. If the underlying condition persists, the normal `consecutive_failures` circuit breaker will auto-block via `gave_up` after `failure_limit` failures. |

这是一张**参考表**里对 payload 取值的枚举("Reasons: … / … / …"),读者会当成完整集合。
代码的第一道闸返回的是第四个值,而且它排在最前:

`hermes_cli/kanban_db.py:8079-8097 @ 863e313`

```python
    rl_cooldown = _resolve_rate_limit_cooldown_seconds()
    latest_run = conn.execute(
        "SELECT outcome, ended_at FROM task_runs "
        "WHERE task_id = ? AND ended_at IS NOT NULL "
        "ORDER BY ended_at DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    if (
        latest_run is not None
        and latest_run["outcome"] == "rate_limited"
    ):
        if rl_cooldown <= 0:
            # Cooldown disabled — respawn immediately, and skip the
            # blocker_auth regex so the stamped rate-limit text doesn't
            # re-trap the task.
            return None
        ended_at = latest_run["ended_at"]
        if ended_at is not None and (now - int(ended_at)) < rl_cooldown:
            return "rate_limit_cooldown"
```

判成 ▲ 而不是 ◇ 的理由:同一份文档在 §"Respawn guard" 正文里也做了同样的三项枚举
(779 行标题下),两处一致地漏掉同一个值;而这个值恰恰是**最常出现**的那个
(任何一次配额墙都会产生它)。读者按文档去解释一条 `{"reason": "rate_limit_cooldown"}`
的事件时,会得到"这个 reason 不存在"的结论。

正文那一处:

`website/docs/user-guide/features/kanban.md:781 @ 863e313`

> The dispatcher refuses to re-spawn a ready task when it hit a quota/auth/429 error on the previous run (`blocker_auth`), or completed a run successfully within the guard window (`recent_success`), or a recent task comment links to a GitHub PR (`active_pr`). This prevents repeat worker storms on the same bug or task while a human catches up. See the `respawn_guarded` row in the [event reference](#event-reference).

### ◇ 代码有、文档无(4 条)

```text
  ◇-1  hermes kanban repair 子命令 + 整套隔离/REINDEX 自愈机制
       website/docs 389 个文件 + README.md + AGENTS.md 里 0 命中
  ◇-2  HERMES_KANBAN_BUSY_TIMEOUT_MS / _CRASH_GRACE_SECONDS
       / _RATE_LIMIT_COOLDOWN_SECONDS / _CLAIM_TTL_SECONDS 四个环境变量,同上 0 命中
  ◇-3  HERMES_BIN(worker 启动路径覆盖),同上 0 命中
  ◇-4  reclaim_deferred 事件(杀不掉活 worker 时的续租留痕)不在事件参考表里
```

前三条一条命令验完(整体 0 命中):

```verify
cd /home/user/hermes-agent && grep -rn -E "HERMES_KANBAN_(BUSY_TIMEOUT_MS|CRASH_GRACE_SECONDS|RATE_LIMIT_COOLDOWN_SECONDS|CLAIM_TTL_SECONDS)|HERMES_BIN|kanban repair" website/docs README.md AGENTS.md | wc -l
```

◇-4 的搜索面与实测:`reclaim_deferred` 与 `claim_extended` 在这份 1,039 行的文档里
**各 0 命中** —— 不只是不在事件参考表里,是整份文档都没提过。

```verify
cd /home/user/hermes-agent && grep -c "reclaim_deferred\|claim_extended" website/docs/user-guide/features/kanban.md
```

这两个事件恰好是 §4.1 那条"复制风暴"事故留下的**唯一可观测痕迹**(`hermes kanban tail`
里看到的就是它们),文档里查不到会让运维读到事件时无从解释。

### ◎-1 文档说"单主机是刻意的",代码比这更严格

`website/docs/user-guide/features/kanban.md:1035 @ 863e313`

> Kanban is deliberately single-host. `~/.hermes/kanban.db` is a local SQLite file and the dispatcher spawns workers on the same machine. Running a shared board across two hosts is not supported — there's no coordination primitive for "worker X on host A, worker Y on host B," and the crash-detection path assumes PIDs are host-local. If you need multi-host, run an independent board per host and use `delegate_task` / a message queue to bridge them.

字面为真,所以不是 ▲。记 ◎ 是因为代码比这句话**更保守**:不只 "crash-detection 假设
PID 是本机的"这一处,而是 **4 处**各自独立地做了主机前缀检查:

```verify
cd /home/user/hermes-agent && grep -n "host_prefix" hermes_cli/kanban_db.py
```

```console
4486:    host_prefix = f"{_claimer_id().split(':', 1)[0]}:"      # release_stale_claims
4496:        host_local = lock.startswith(host_prefix)
7036:    host_prefix = f"{_claimer_id().split(':', 1)[0]}:"      # _terminate_reclaimed_worker
7037:    if not str(claim_lock).startswith(host_prefix):
7207:    host_prefix = f"{_claimer_id().split(':', 1)[0]}:"      # enforce_max_runtime
7221:        if not lock.startswith(host_prefix):
7561:        host_prefix = f"{_claimer_id().split(':', 1)[0]}:"   # detect_crashed_workers
7565:            if not lock.startswith(host_prefix):
```

(注释列是我加的标注,不是源码内容。)**`detect_stale_running` 刻意不在这 4 处之列** ——
它的证据是 `last_heartbeat_at`,那是写在共享 DB 里的、与主机无关的事实,所以它对
非本机的 claim 也照样回收;真正需要本机身份的"终止进程"那一步,它委托给
`_terminate_reclaimed_worker`(第 7036 行那道门)。**这个区分本身就是这段代码里
最讲究的一处:按证据的来源决定要不要做主机检查,而不是一刀切。**

---

## 6. 分层建议(只建议,不改台账)

台账当前这一行(**未改动**):

```text
hermes_cli/kanban_db.py	text	10275	L2	R8D	R8D-structure
```

约束条件必须先摆清楚,否则会推荐出一个动摇阻断关卡的方案:

- 台账**一行 = 一个文件**,没有区间粒度;
- `scripts/verify_ledger.py` 是 R8A 起的阻断关卡,其中一项是
  **五层行数加总 = 全仓总行数 2,608,452**;
- 因此任何"把一个文件拆成两行"的做法,都要么重复计行、要么需要新的加总规则 ——
  **为一个文件改全仓不变量,收益不成比例**;
- 而 `status` 列的既有约定本来就是自由文本("可翻译成已学到什么程度的状态")。

### 四个选项与代价

```text
  选项                         做法                                  代价
  A 整文件升 L1                layer: L2 → L1                        L1 语义被污染:10,275 行里
                                                                     只精读了 3,885 行(37.8%),
                                                                     其余 6,390 行仍是结构级理解。
                                                                     L1 是"能独立重实现"的依据层,
                                                                     一旦允许"部分精读也算 L1",
                                                                     以后没人知道 L1 到底代表什么
  B 保持 L2,只改 status       status → R9A-deep-read-partial        零风险,不动任何不变量;
                               并在 notes 里登记区间                 但台账本身仍读不出"读了哪几段"
  C 保持 L2,区间编码进 status status →                              同样零风险,且台账**自解释**;
                               R9A-deep-read[1380-2840,6755-9178]    代价是 status 变成半结构化字符串
                                                                     (它本来就是自由文本,
                                                                      现有值也没有机器消费者)
  D 台账加区间粒度             拆行 / 加 subrange 列                  要改 verify_ledger.py 的加总规则,
                                                                     即改阻断关卡本身。为 8,530 个文件
                                                                     里的 1 个改全局不变量,不划算
```

### 推荐:选 C

`status` 写成 **`R9A-deep-read[1380-2840,6755-9178]`**,`layer` 保持 `L2`,`round` 从
`R8D` 改成 `R8D+R9A`(或按主线现有惯例只留最新轮次)。理由三条:

1. **它不动任何阻断关卡**:分层列未变,五层加总不变,`verify_ledger.py` 一行都不用改;
2. **它可被机器消费而无需现在就消费**:区间写成 `[a-b,c-d]` 的形状,将来若真要做"区间
   覆盖率"统计,一个正则就能解析;现在不做也不欠债;
3. **它把"这个文件还欠什么"直接写在台账里**:任何人读到这一行,立刻知道 10,275 行里
   有 3,885 行到 L1 了、剩下的没有 —— 而这正是移交项抱怨"读不出来"的那件事。

### 附带的判据建议(给 CLAUDE.md,不擅自改)

R8D 把教训记成"按文件判层会把大文件里的异质区间一起判掉"。本轮复核认为这句话还差半句,
建议补成:

> 分层单位是**文件**,阅读单位是**机制**,两者不重合。台账的 `layer` 列因此只能表达
> **该文件的下限层**;某个文件里已达到更高层的区间,写在 `status` 列并由 notes 承载证据。
> 换言之:`layer` 回答"这个文件最少被理解到什么程度",`status` 回答"实际读到哪了"。

**为什么这半句重要**:按现在的写法,下一轮遇到同样形状(一个大文件里有一段特别值得精读)
的人会再问一遍"那到底该不该升 L1",而这个问题在"一行一文件 + 行数加总"的约束下**无解**。
把 `layer` 明确定义成下限,这个问题就消失了。

---

## 7. 测试与环境

按 CLAUDE.md 的要求,报测试数时一并记环境。

**环境**:`/home/user/hermes-venv`,`pip list` 去掉两行表头后 **87 个包**
(`[dev]` extra + `aiohttp 3.14.1` + `brotlicffi 1.2.0.1`),与 R8B 记录一致。

**结果**:本簇相关 8 个测试文件,**47 用例全部通过,0 失败**。

```verify
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh \
  tests/hermes_cli/test_kanban_db.py tests/hermes_cli/test_kanban_db_repair.py \
  tests/hermes_cli/test_kanban_dispatch_lock.py tests/hermes_cli/test_kanban_init_lock_bounded.py \
  tests/hermes_cli/test_kanban_write_txn_busy_retry.py tests/hermes_cli/test_kanban_reclaim_claim_lock_guard.py \
  tests/hermes_cli/test_kanban_per_profile_cap.py tests/hermes_cli/test_kanban_default_assignee.py
```

```console
=== Summary: 8 files, 47 tests passed, 0 failed (100% complete) in 3.8s (8 workers) ===
```

**一条必须记下的过程教训(它正是"shell 命令即证据"那条规矩要防的形状)。**
我第一次是直接用 `python -m pytest <8 个文件>` 一把跑的,得到 **2 failed, 34 passed**:

```console
=========================== short test summary info ============================
FAILED tests/hermes_cli/test_kanban_db.py::test_rate_limit_exit_requeues_without_counting_failure
FAILED tests/hermes_cli/test_kanban_db.py::test_connect_works_when_wal_is_silently_refused
2 failed, 34 passed in 2.92s
```

单独跑 `test_rate_limit_exit_requeues_without_counting_failure` 却通过。原因在
`scripts/run_tests.sh` 的开头就写着 —— 这个仓库的测试契约是**每个文件一个独立进程**:

`scripts/run_tests.sh:5-9 @ 863e313`

```bash
# What this script enforces:
#   * Per-file isolation via scripts/run_tests_parallel.py — each test
#     file runs in its own freshly-spawned `python -m pytest <file>`
#     subprocess. No xdist, no shared workers, no module-level leakage
#     between files.
```

`kanban_db` 有多个**模块级**可变状态(`_INITIALIZED_PATHS`、`_recent_worker_exits`、
`detect_crashed_workers._last_rate_limited` 函数属性),同进程跨文件会互相污染。
**所以那 2 个失败是我的调用方式造成的,不是代码缺陷** —— 记在这里,免得下一轮
有人拿 `pytest 多文件` 的结果去下判断。

**环境性质**:本容器链接的是 SQLite 3.45.1,被 `apply_wal_with_fallback` 判定为
受 WAL-reset 损坏 bug 影响,于是 kanban 库落到 `journal_mode=DELETE` 而非 WAL:

```console
kanban.db (kanban.db): linked SQLite 3.45.1 is vulnerable to the WAL-reset corruption bug (https://sqlite.org/wal.html#walresetbug) — using journal_mode=DELETE instead of enabling WAL. Upgrade to SQLite 3.51.3+ (or backports 3.50.7 / 3.44.6); Hermes-managed installs can repair the embedded runtime with `hermes update`. See `hermes doctor`. This warning fires once per process per database.
```

**这条对本文有实质影响**:§3.2 的第 (4) 类(撕裂扩展检测)只在**非 WAL** 下生效,
所以在本容器里它是**活的**;在一个 SQLite 够新的生产环境里,同一段代码是 no-op。
下一轮若要复核 `_check_file_length_invariant`,必须先确认所在环境的 `journal_mode`。

**基线洁净性**:全程只读。三次跑测试前后 `git -C /home/user/hermes-agent status --porcelain`
均为空(测试产生的 `__pycache__` / `.pytest_cache` / `test_durations.json` 均被 `.gitignore` 覆盖)。

---

## 8. 结清与移交

### 8.1 H-R8D-b 的结清判定

```text
  子问题                                  结清状态
  1 核实两段真实边界与性质                 已结清。段 A = 1380–2840(1,461 行),
                                          段 B = 6755–9178(2,424 行);R8D 标签
                                          6757-9180 偏差 2 行;监管器另有 5 处在段外
  2 是否与任务板业务无关                   已结清。段 A 64.4% 可整段移植(且有同仓
                                          第二实现佐证);段 B 仅 18.7% —— 原判过宽
  3 精读两段                               已完成(§3、§4)
  4 分层建议                               已给出四选项 + 推荐 C(§6),未改台账
  5 ■ / ▲ / ◇                             ■ 2 / ▲ 2 / ◇ 4 / ◎ 1,均带可复现判据或搜索面
```

**H-R8D-b 关闭。**

### 8.2 本文新开的移交项(每条带锚点文件 + 一句话现象)

- **H-R9A-a(■-1 的处置)**:`hermes_cli/kanban_db.py:2018` 与 `:2125` ——
  `_backup_corrupt_db` 返回 `None`(隔离失败)后没有任何分支检查它,REINDEX 照常执行,
  且日志打印 `Pre-repair copy kept at <backup failed>`。已复现(`ENOSPC` 模拟)。
  待定的是:这算"应上报上游的缺陷"还是"记进设计蓝图的反面教材",主线定。

- **H-R9A-b(■-2 的范围确认)**:`hermes_cli/kanban_db.py:6941` 的
  `os.waitpid(-1, os.WNOHANG)` 与 `tools/process_registry.py:781` 的后台 `Popen` ——
  两者在网关进程里共存,前者会替后者收尸,导致后者的退出码被 CPython 报成 0。
  同步侧已复现;**asyncio 侧三次实测均未复现**(`ThreadedChildWatcher` 抢先)。
  下一轮若要升格这条,需要的是:枚举网关进程里所有"spawn 后延后 poll"的形状,
  确认是否存在比 `process_registry` 更要紧的受害者。

- **H-R9A-c(段 B 剩余业务面未精读)**:`hermes_cli/kanban_db.py:8203-8674`
  (`dispatch_once` / `_dispatch_once_locked`,472 行)—— 本文只读到"它是业务、
  不属于本移交项范围"的粒度,**没有**逐分支精读它的抢占顺序、review 列分发、
  per-profile 上限在 dry_run 下的计数。若后续要写"任务板"成品章,这 472 行是主干。

- **H-R9A-d(◇-4 的取证深度)**:`website/docs/user-guide/features/kanban.md:1021-1026`
  的事件参考表 —— 本文只核了 `respawn_guarded` 一行,`reclaim_deferred` /
  `claim_extended` / `protocol_violation` / `rate_limited` 四个事件是否在表内未逐条核。
  现象:`reclaim_deferred` 在表内 grep 不到。

### 8.3 给 R12《设计蓝图》的可迁移原则(段 A 部分,段 B 见 H-R9A-c 后再补)

1. **把"这个文件是不是我的库"当成一道独立的、连接建立之前的闸门。** 字节级 64 字节
   探测比 `integrity_check` 便宜三个数量级,而且能报出 `first_32=<hex>` 这种可以直接
   定位"谁写坏的"的信息。
2. **检查损坏的动作本身不能制造损坏。** POSIX 咨询锁会被同进程任意一次 `close()` 清空,
   所以"打开文件看一眼"是有代价的。要么复用已有连接,要么显式拒绝(有活连接时不取证)。
3. **自愈的边界要窄到可以证明无损。** 这里只修"索引与表失配"这一类,因为索引可以从表
   无损重建;其余一律 fail-closed。**能自动修的东西,判据必须是全称的**(任一条消息
   不匹配就整体不可修)。
4. **先隔离后修复 —— 并且隔离失败必须阻断修复。** 这是本文 ■-1 的教训:一条只写在
   注释里、没有代码强制的不变量,在失败路径上会被绕过。
5. **隔离文件用内容寻址而不是时间戳**,并配数量上限;上限的实现要注意 `copy2` 保留 mtime。
6. **给"忙"和"坏"两条完全不同的路径。** `OperationalError` 原样上抛,绝不隔离 ——
   否则一个健康但繁忙的库会被每个撞锁的进程各隔离一份。
7. **跨进程初始化锁要有界,超时后继续而不是失败。** 前提是初始化幂等;
   "有界地重复劳动"永远优于"无界地挂住"。
8. **稳态路径上不要取任何跨进程锁。** 首次连接做的所有昂贵检查缓存在进程内,
   之后的连接直接开;否则一个卡住的旁观者进程能把长驻调度器的下一 tick 永久堵死。

---

## 9. 延伸

- 段 A / 段 B 的结构级测绘与全文件分段表:`notes/r8d-str-kanban-and-work.md` §1;
- 另一条 SQLite 自愈阶梯(`state.db` 侧,即本文 §2.4 引的那个"第二实现"):
  `notes/r5-02-hermes-state-sessiondb.md`;
- 会话库的**离线**抢救(与本文互补:本文讲的是**在线**自愈,那边是进程外的抢救):
  `notes/r8d-raw-self-repair.md` 的 `hermes_cli/session_recovery.py` 一节;
- 本文用到的两条共享 helper(`apply_wal_with_fallback` / `preflight_db_writability`)
  都定义在 `hermes_state.py`,同见 `notes/r5-02-hermes-state-sessiondb.md`。
