# R5 底稿 · hermes_state 会话库

对象:`hermes_state.py`(9691 行)+ `hermes_state_common.py`(614 行),基线 `863e31318553cda8ad61df681d08175364d4164b`(已实测 `git -C /home/user/hermes-agent rev-parse HEAD` 相符)。溯源格式一律 `路径:行号 @ 863e313`,行号用 `grep -n` / `Read` 实测。

两文件分工总览:`hermes_state.py` 是 SessionDB 主体(连接管理、耐久性防御、会话/消息 CRUD、压缩锁、token 记账、生命周期);`hermes_state_common.py` 是被抽出的**纯常量层**——DDL、FTS 触发器 SQL、共享 SQL 片段——供 `hermes_state_search / hermes_state_schema / hermes_state_portability` 三个 mixin 引用而不产生循环 import(hermes_state_common.py:1-7 @ 863e313)。SessionDB 类本身由四部分拼成:

`hermes_state.py:1890 @ 863e313`
```python
class SessionDB(SessionSearchMixin, SessionSchemaMixin, SessionPortabilityMixin):
```

---

## 1. SQLite 耐久性防御工事(state.db 跑在恶劣文件系统上的逐层防御)

**解决什么问题**:state.db 是全家桶(CLI/gateway/TUI/cron/桌面端)的唯一事实源,但用户会把 `~/.hermes` 放在 NFS、SMB、FUSE、ZFS、macOS virtiofs 上,会 sudo 跑一次留下 root-owned 文件,会在 macOS 关机时被 launchd 掐死,会碰上 SQLite 自身的 WAL-reset corruption bug。任何一层失败的默认后果都是"/resume、/title、/history、/branch 全部静默失效"。这一节按"从打开到写入"的顺序逐层列防御。

### 1.0 层 0:打开前的可写性预检(preflight)

首连接之前先检查 db 文件、`-wal`/`-shm` 边车、父目录的读写权限;在 Hermes home 树内的文件直接 `chmod u+rw` 修复,树外的 fail-fast 并给出确切命令;绝不删 `-wal`:

`hermes_state.py:1154-1177 @ 863e313`
```python
def preflight_db_writability(
    db_path: Path,
    *,
    db_label: str = "state.db",
) -> None:
    """Refuse-or-repair read-only DB files BEFORE the first connection opens.

    Port of Kilo-Org/kilocode#12508's startup preflight. A stray read-only
    ``state.db`` / ``-wal`` / ``-shm`` (sudo run, restored backup, copied
    dotfiles) previously surfaced as an opaque
    ``sqlite3.OperationalError: attempt to write a readonly database`` raised
    from deep inside ``_init_schema`` — naming no file and no fix — and the
    obvious wrong "fix" (deleting the ``-wal``) silently loses committed
    transactions. This preflight:

    - **Repairs** permissions with ``chmod u+rw`` when the file lives inside
      the Hermes home tree (``get_hermes_home()``) — the safe repair scope:
      Hermes owns those files, and the OS makes ``chmod`` fail on files the
      user doesn't own, which bounds the repair exactly.
    - **Fails fast with an actionable error** naming the exact file and the
      exact ``chmod`` command for anything else (root-owned files, read-only
      mounts, custom paths outside the home tree).
    - Never deletes or truncates a WAL sidecar — once writable, the normal
      open path checkpoints its committed frames into the DB as intended.
```

报错文案里专门警告不要删 `-wal`(hermes_state.py:1219-1224 @ 863e313):

```python
        wal_note = (
            " Do NOT delete the -wal file — it contains committed data that "
            "will be merged into the database once it is writable."
            if p.name.endswith("-wal")
            else ""
        )
```

挂接点:`SessionDB.__init__` 在 mkdir 之后、首连接之前调用(hermes_state.py:2110-2111 @ 863e313)。

### 1.1 层 1:零化库检测与隔离(#68474)

**问题**:某类故障(更新中断/文件系统抽风)会留下一个"大小 > 0 但全是 NUL 字节"的 state.db。SQLite 打开它报通用的 "file is not a database",无恢复路径。**实现**:打开前做字节级探针——注意探针本身有锁安全约束(见 1.7 层):

`hermes_state.py:1737-1748 @ 863e313`
```python
def is_zeroed_state_db(
    path: Path, *, probe_bytes: int = 100, force: bool = False
) -> bool:
    """Detect the #68474 zeroed state.db signature (size>0, NUL header).

    Byte-level probe, so it is only safe BEFORE any connection to *path*
    exists in this process: ``close()`` cancels every POSIX advisory lock the
    process holds on the file, which can pull the EXCLUSIVE lock out from
    under a running VACUUM and corrupt the database. The read is routed
    through ``read_header_bytes_preopen``, which refuses (returning False
    here) once a connection is live. Pass ``force=True`` only for offline
    files -- quarantined copies, snapshots, archives.
```

判定核心(hermes_state.py:1768-1773 @ 863e313):

```python
    head = read_header_bytes_preopen(
        path, length=max(16, probe_bytes), force=force
    )
    if not head or head.startswith(b"SQLite format 3"):
        return False
    return all(byte == 0 for byte in head)
```

命中后**隔离而不删除**:`quarantine_zeroed_state_db` 把文件 rename 成 `state.db.zeroed-<ts>-<pid>.bak`(连同 `-wal`/`-shm`),让后续打开得到一个全新空库。关键的多进程正确性:rename 受一个跨进程 flock(`state.db.quarantine.lock`)保护,5 秒拿不到锁就 **fail closed**——宁可不隔离也不与另一个启动进程对同一活文件双重动作:

`hermes_state.py:1815-1827 @ 863e313`
```python
        if not acquired:
            # Fail closed: do NOT proceed without the lock. A slow or paused
            # startup that still owns the lock can overlap this fallback and
            # the two processes can act on the same live file (#68805 review).
            logger.error(
                "quarantine lock for %s not acquired within 5s — refusing to "
                "quarantine without the cross-process lock. The zeroed file "
                "is left in place. If sessions fail to load, restore from "
                "state-snapshots via `hermes snapshot list` / "
                "`hermes snapshot restore <id>`.",
                path,
            )
            return None
```

拿到锁后还要**锁内复检**(另一进程可能已隔离并建了新库,hermes_state.py:1828-1842 @ 863e313)。`__init__` 的挂接:隔离失败且文件仍是零化时拒绝打开并抛出带指引的错误(hermes_state.py:2137-2140 @ 863e313):

```python
                # If quarantine failed, do not open the zeroed file (would fail
                # opaquely or risk further damage). Raise with the clear message.
                if qpath is None and self.db_path.exists() and is_zeroed_state_db(self.db_path):
                    raise sqlite3.DatabaseError(msg)
```

**取舍**:隔离(保字节做取证/snapshot 恢复)优于当场重建或报死;fail-closed 优于 fail-open(#68805 复盘:两进程可对同一活文件动作)。

### 1.2 层 2:WAL 模式与三种回退

**背景注释块**把整个问题域写清楚了(hermes_state.py:289-317 @ 863e313,节选 289-305):

```python
# SQLite's WAL mode requires shared-memory (mmap) coordination and fcntl
# byte-range locks that don't reliably work on network filesystems (NFS,
# SMB/CIFS, some FUSE mounts, WSL1).  Upstream documents this explicitly:
# https://www.sqlite.org/wal.html#sometimes_queries_return_sqlite_busy_in_wal_mode
#
# On those filesystems ``PRAGMA journal_mode=WAL`` raises
# ``sqlite3.OperationalError: locking protocol`` (SQLITE_PROTOCOL).  If we
# propagate that, every feature backed by state.db / kanban.db breaks
# silently — /resume, /title, /history, /branch, kanban dispatcher, etc.
#
# ZFS is a separate case: its COW + mmap semantics can corrupt the WAL
# shared-memory (-shm) file under concurrent connection bursts, presenting
# as ``disk I/O error`` rather than ``locking protocol``.
#
# Instead, fall back to ``journal_mode=DELETE`` (the pre-WAL default) which
# works on NFS and ZFS.  Concurrency drops — concurrent readers are blocked
```

识别"WAL 不兼容"的错误指纹(hermes_state.py:315-319 @ 863e313):

```python
_WAL_INCOMPAT_MARKERS = (
    "locking protocol",       # SQLITE_PROTOCOL on NFS/SMB
    "not authorized",         # Some FUSE mounts block WAL pragma outright
    "disk i/o error",         # ZFS SHM corruption under concurrent connections
)
```

`apply_wal_with_fallback`(hermes_state.py:654-817 @ 863e313)是核心函数,逐分支:

**(a) 操作员显式配置**。`database.journal_mode`(config.yaml)是权威旋钮,默认 `wal`,非法值安全回落(hermes_state.py:614-637 @ 863e313)。`cli-config.yaml.example:15-16 @ 863e313` 有文档:`journal_mode: "wal"  # Supported values: "wal", "delete"`。显式 `delete` 时还要校验 SQLite 真的接受了 DELETE(hermes_state.py:734-741)。

**(b) WAL-reset bug 门(#70055)**。链接的 SQLite 版本落在漏洞区间(3.7.0–3.51.2,除 backport 3.50.7 / 3.44.6)时,**拒绝对新库启用 WAL**,判定逻辑在 `hermes_cli/sqlite_runtime.py:24-37 @ 863e313`:

```python
def is_sqlite_wal_reset_vulnerable(
    version_info: tuple[int, ...],
) -> bool:
    """Return whether *version_info* contains SQLite's WAL-reset bug."""
    info = _version_tuple(version_info)
    if info < (3, 7, 0):
        return False
    if info >= (3, 51, 3):
        return False
    if (3, 50, 7) <= info < (3, 51, 0):
        return False
    if (3, 44, 6) <= info < (3, 45, 0):
        return False
    return True
```

这个门有一段罕见的"决策考古"注释,记录它曾被错误 revert 又被恢复的实证过程(hermes_state.py:678-687 @ 863e313):

```python
    This gate (#70055) is deliberately RETAINED. An earlier revision of the
    lock-cancellation fix (#71724) reverted it on the theory that DELETE was
    "the mode that corrupts", but that comparison was confounded: the clean
    WAL result came from SQLite 3.53.1, which carries BOTH the WAL-reset fix
    AND 3.51.0's defenses against close()-broken POSIX locks, so it says
    nothing about 3.50.4.  Re-measured on the actually-bundled 3.50.4 with
    the lock fix in place, WAL and DELETE are both clean (0/3 each) — i.e.
    there is no evidence that WAL is safer here, and upstream still documents
    the WAL-reset bug as real through 3.51.2 with serious consequences.  Until
    a fixed runtime is delivered, keep new databases out of WAL.
```

**(c) 静默拒绝检测**。`PRAGMA journal_mode=WAL` 是"设置即查询":macOS NFS / SMB / AgentFS overlay 上它**不抛错但不生效**,只返回仍然生效的模式。所以必须信返回行而不是"没抛异常"(区域 `hermes_state.py:743-767`,下面这段起于 747):

`hermes_state.py:747-756 @ 863e313`

```python
        # except branch below. But macOS NFS — and SMB/CIFS, and the AgentFS
        # NFS overlay — refuse the switch WITHOUT raising: the pragma simply
        # returns the still-effective mode (e.g. ``delete``). Trust the
        # returned row, not the mere absence of an exception; otherwise we
        # report a false ``"wal"`` AND skip the fallback WARNING, leaving the
        # DB silently in DELETE (reader-blocks-writer) with no signal.
        row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        mode = str(row[0]).strip().lower() if row and row[0] is not None else ""
        if mode == "wal":
            _apply_macos_checkpoint_barrier(conn)
            _enforce_macos_synchronous_full(conn)
            return "wal"
```

**(d) `disk i/o error` 的歧义消解**。它既可能是 ZFS/APFS-CoW 的确定性 WAL 不兼容,也可能是一次性瞬态 EIO;把瞬态当永久降级信号曾造成"进程 A 降到 DELETE、兄弟进程仍设 WAL"的混合日志模式损坏(修复于 5c49cd0ed0)。方案:重试 pragma 两次,瞬态自愈返回 wal,确定性失败落入受保护的 DELETE 回退(hermes_state.py:788-807 @ 863e313)。

**(e) 绝不活体降级**。磁盘头已是 WAL 的库(其他 gateway/cron 连接可能仍持有它)一律不切 DELETE——NFS 路径与漏洞路径都遵守(hermes_state.py:808-811;`_apply_delete_for_wal_reset_bug` 内 840-846 @ 863e313):

```python
        # Don't downgrade if another process already set WAL on disk.
        existing = _on_disk_journal_mode(conn)
        if existing == "wal":
            raise
```

**(f) 降级要吵**。回退到 DELETE 是真实的并发损失(写阻塞读),记 ERROR 而非 WARNING,且按 (进程, db_label) 去重防止 NFS 上 kanban 每操作一次刷一条(hermes_state.py:928-951 @ 863e313)。`require_wal=True` 的调用方会得到 `WalUnsupportedError` 而非静默降级(640-651);当前所有调用方都保持默认 False,让 NFS 安装继续可用(689-693)。

### 1.3 层 3:macOS 专属 fsync 屏障

**问题**:Darwin 上 `fsync()` 被 Apple 文档明确说明**不保证落盘也不保证写序**;launchd 系统关机会丢页缓存(等效断电),于是 WAL checkpoint 的 fsync "报告已耐久"的页可能从未上盘,把主库写成 malformed image(issue #30636 "SIGTERM during launchd shutdown under high load")。两个 PRAGMA 兜住:

`hermes_state.py:546-551 @ 863e313`
```python
    if sys.platform != "darwin":
        return
    try:
        conn.execute("PRAGMA checkpoint_fullfsync=1")
    except sqlite3.OperationalError:
        pass
```

成本取舍写在 docstring(hermes_state.py:537-540 @ 863e313):只在 checkpoint 边界(WAL 帧落进主库处)打 `F_FULLFSYNC` 屏障,摊到约 +0.1 ms/commit;而全量 `fullfsync=1`(每次 commit 的 WAL sync 都刷)约 +4 ms。第二个是 `synchronous=FULL`(hermes_state.py:554-581 @ 863e313):Darwin 默认 NORMAL 只 fsync,checkpoint 与进程终止竞态可留下半写 btree 页(`btreeInitPage error 11`),因此每次 WAL 激活成功后强制 FULL,"即使先前连接设过 NORMAL"(569-572)。两者都 best-effort 不抛错。

### 1.4 层 4:checkpoint 策略(何时把 WAL 刷回主库)

- 常规:每 50 次成功写做一次 **PASSIVE** checkpoint(`_CHECKPOINT_EVERY_N_WRITES = 50`,hermes_state.py:1949;调用点 2623-2624)。为什么不用 TRUNCATE:历史上周期性 TRUNCATE 在大库(65K+ 页)上因独占锁下一次性 checkpoint 数千帧的 I/O 压力造成 B-tree 损坏(issue #45383),见区域 `hermes_state.py:2785-2801`,下面这段起于 2789:

`hermes_state.py:2789-2796 @ 863e313`

```python
        requiring an exclusive lock.  PASSIVE is safe for frequent
        periodic use because it does not block concurrent writers and
        cannot corrupt B-tree pages under I/O pressure.

        PASSIVE does not truncate the WAL file — it stays at its
        high-water mark.  WAL truncation happens in :meth:`close`
        (TRUNCATE) and pre-VACUUM checkpoints, which run infrequently
        under controlled conditions.
```

- 收尾:`close()` 里可写连接尝试一次 TRUNCATE checkpoint 收缩 WAL 文件(hermes_state.py:2849-2851 @ 863e313)。

### 1.5 层 5:打开期多级自修复(malformed schema 类)

**问题定性**(hermes_state.py:1019-1044 @ 863e313):`sqlite_master` 自身不一致(典型:两条 `CREATE VIRTUAL TABLE messages_fts`)时,SQLite 在准备**第一条语句**时就解析全 schema,于是连 `PRAGMA journal_mode` 都抛错——所以它在 `apply_wal_with_fallback` 期间、远早于 `_init_schema` 就命中;唯一还能用的操作是 `PRAGMA writable_schema=ON` + 直改 `sqlite_master`。用户可见症状:桌面端显示 "no sessions" 而磁盘上躺着 200+ 文件。关键事实:**canonical 的 sessions/messages 数据完好,坏的只是派生 schema**。

打开路径的挂接(hermes_state.py:2204-2226 @ 863e313):

```python
            except sqlite3.DatabaseError as exc:
                # The malformed-schema class (e.g. a duplicate sqlite_master
                # row for messages_fts) fails on the very first statement —
                # before _init_schema can run — so it can't be caught at the
                # FTS-rebuild layer. Recover by repairing sqlite_master in
                # place (backup first; canonical sessions/messages preserved),
                # then reopen once. This is what lets Desktop/Dashboard
                # self-heal instead of silently showing "no sessions".
                if not is_malformed_db_error(exc) or not _claim_repair_attempt(self.db_path):
                    raise
                ...
                report = repair_state_db_schema(self.db_path)
                if not report.get("repaired"):
                    raise
                _connect_and_init_with_lock_patience()
```

`_claim_repair_attempt`(1095-1107)是进程级一次性闸:同一路径同进程只修一次,防修复循环、也串行化并发 open 的手术。

**健康判定** `_db_opens_cleanly`(hermes_state.py:1244-1367 @ 863e313)四连探:① `PRAGMA journal_mode`(踩 malformed 解析);② `PRAGMA integrity_check`;③ 对三张 FTS 表跑 `MATCH '""'` 读探针(#66724:shadow 段坏时读表正常但 MATCH 抛 `DatabaseError`,官方修复工具的 check-only 曾误报健康);④ **回滚式写探针**——BEGIN IMMEDIATE 插一条探针消息再 ROLLBACK,专抓 #50502 那类"读全好、integrity_check 过、但每条 INSERT 都被 FTS 触发器打死"的损坏(1334-1346)。能力缺失(无 fts5 模块 / 无 trigram / 无 cjk tokenizer)全部显式排除,绝不误判为损坏(1298-1319、1356-1361)。

**修复阶梯** `repair_state_db_schema`(hermes_state.py:1370-1535 @ 863e313),从最不破坏开始逐级升级,每级修完都重跑 `_db_opens_cleanly` 验证:

1. 先做原始字节备份 `state.db.malformed-backup-<ts>`(1414-1416;备份函数在进程内仍有活连接时**拒绝**裸拷贝,因为 open/close 会取消 POSIX 锁,1131-1138)。
2. **Strategy 0**:FTS5 `'rebuild'` 命令就地重建索引(schema 完整保留,1432-1434):
   ```python
                    conn.execute(
                        f"INSERT INTO {table_name}({table_name}) VALUES('rebuild')"
                    )
   ```
3. **Strategy 0.5**:`REINDEX` 重建失同步的 B-tree 索引(#63386 "wrong # of entries in index",1458-1471)。
4. **Strategy 1**:`writable_schema=ON` 后对 `sqlite_master` 按 (type,name) 去重、保最小 rowid(FTS 索引保留,1479-1491)。
5. **Strategy 2**:删掉全部 `messages_fts%` schema 行 + `VACUUM`,下次 open 时从 canonical messages 重建(1509-1513)。
6. 全失败:ERROR 指向备份文件,人工恢复(1529-1534)。

### 1.6 层 6:运行期写路径的一次性 FTS 自愈

FTS shadow 表损坏时,每条消息写入都会经同步触发器抛 malformed/corrupt 类错误。`_execute_write` 的 `DatabaseError` 分支挂了一次性就地重建(hermes_state.py:2667-2681 @ 863e313):

```python
            except sqlite3.DatabaseError as exc:
                if _is_no_more_rows(exc) and self._sleep_before_write_retry(deadline, patience_s):
                    continue
                # Corrupt FTS shadow tables make every write raise the
                # malformed/corrupt error class through the FTS sync triggers
                # while the canonical messages table is intact. The gateway
                # session store has its own retry queue for transcript
                # appends (#65637 salvage), but cron and CLI writers call
                # SessionDB directly — without this, their writes hard-fail
                # until the next process restart triggers the offline repair.
                # Rebuild the FTS index in place (once per instance) via
                # rebuild_fts() and retry the failed write immediately.
                if not self._try_runtime_fts_rebuild(exc):
                    raise
                continue
```

`_try_runtime_fts_rebuild` 每实例只试一次(`_fts_runtime_rebuild_attempted`,2752),错误类判定兼容两种 SQLite 版本的报错措辞(`database disk image is malformed` 与 `fts5: corrupt structure record`,2720-2734)。修复成功→重试原写入;失败→指向离线修复路径。

### 1.7 层 7:锁安全的字节访问纪律(贯穿所有层)

所有对 db 文件的**字节级**读(零化探针、备份拷贝)都必须发生在本进程无活连接时,因为 POSIX 语义下同进程任何 fd 的 `close()` 会取消该文件上的全部 advisory lock——可能把正在跑的 VACUUM 的 EXCLUSIVE 锁抽走。因此连接一律走注册制(hermes_state.py:1702-1715 @ 863e313):

```python
def _connect_tracked_db(path, tracking_path=None, **kwargs):
    """``sqlite3.connect`` that registers the open fd for lock-safety.

    While a connection is live, byte-level probes of the same file are
    refused: an ``open()``/``close()`` cancels every POSIX advisory lock this
    process holds on it -- including a running VACUUM's EXCLUSIVE lock.
```

且"helper 缺失才容忍降级、连接失败必须传播"——静默改用未跟踪连接会让守卫在该连接生命周期内全程失效,正是该模块要防的失败模式(1710-1714)。

### 1.8 层 8:错误可解释性

- init 失败的原因被存进进程级 `_last_init_error`(321-328),`/resume` 等命令用 `format_session_db_unavailable` 输出 `Session database not available: locking protocol (state.db may be on NFS/SMB/FUSE/ZFS — see …)`(475-495)。故意**不在成功时清除**:多线程下并发成功 open 会把另一线程正要格式化的失败原因抹掉(341-355、2240-2247)。
- 磁盘满单独定性(`_DISK_FULL_MARKERS` + errno.ENOSPC,1065-1092),供上层把"磁盘满"与"数据库坏"区分开。

**重实现要点(机制 1)**
1. 把"文件系统敌意"当一等公民:WAL 启用必须验证**返回值**而非异常缺失;错误指纹表 + 显式重试消歧 `disk i/o error`。
2. 三条铁律:磁盘头已 WAL 绝不活体降级;字节级探针只在无活连接时做;备份永远先于手术。
3. 自修复要分层且证据驱动:一次性闸防循环;每级修完用同一个健康探针复验;健康探针必须覆盖"读好写坏"(回滚式写探针)与"表好 MATCH 坏"(空短语探针)两类。
4. 平台耐久性差异要显式补:macOS 的 fsync 谎言用 `checkpoint_fullfsync=1` + `synchronous=FULL` 补,并把成本算清楚写下来。
5. checkpoint 用 PASSIVE 高频 + TRUNCATE 仅收尾;周期性 TRUNCATE 在大库上是实证过的损坏源。
6. 已知上游 bug(WAL-reset)按版本区间做门,并保留"为什么这个门曾被 revert 又被恢复"的实证记录,防止后人再拆。

---

## 2. 多进程共享(gateway + CLI + TUI + cron 同写一个 state.db)

**解决什么问题**:多个独立 hermes 进程共享 state.db。SQLite 只有单写者;它内建的 busy handler 是确定性睡眠表,高并发下产生 convoy(所有竞争者同节奏重试);且兄弟进程会合法地长持锁(VACUUM、close 时的 TRUNCATE checkpoint、旧版本进程的无界 FTS optimize)。

### 2.1 连接布局

每个 SessionDB 实例:**一条写连接**(`check_same_thread=False`,`timeout=1.0`,`isolation_level=None` 自管事务)+ 进程内 `threading.Lock` 串行化本进程写(hermes_state.py:2143-2155 @ 863e313):

```python
                self._conn = _connect_tracked_db(
                    str(self.db_path),
                    check_same_thread=False,
                    # Short timeout — application-level retry with random
                    # jitter handles contention instead of sitting in
                    # SQLite's internal busy handler for up to 30s.
                    timeout=1.0,
                    # auto-starts transactions on DML, which conflicts with
                    # our explicit BEGIN IMMEDIATE.  None = we manage
                    # transactions ourselves.
                    isolation_level=None,
                )
```

**读路径分离(仅 WAL 下)**:召回/浏览查询走 per-thread 只读连接(`mode=ro` URI),完全绕开 `self._lock`——gateway 所有 agent 共享一个 SessionDB,这把全局锁曾是 choke point;DELETE 模式(NFS 回退)下读会撞 SQLITE_BUSY 风暴,所以保留旧的"共享写连接 + 锁"路径(hermes_state.py:2253-2321 @ 863e313):

```python
    def _get_read_conn(self) -> Optional[sqlite3.Connection]:
        """Per-thread read-only connection, or None when unavailable.

        Only used under WAL: WAL readers see a consistent snapshot and never
        block on (or get blocked by) the writer, so recall/browse queries can
        skip self._lock entirely. Under DELETE journal mode (NFS fallback) a
        reader can hit SQLITE_BUSY storms during writes, so we keep the
        legacy locked single-connection path there.

        Fresh read transactions begin per statement (autocommit), so each
        query observes everything committed so far — read-your-writes holds
        for the flush-then-search patterns in a turn.
```

读连接被一个强引用集合持有防 GC 泄漏 tracked fd,`close()` 置 `_read_conns_closed` 标志防"drain 后又注册"竞态(2014-2023、2837-2846)。另有 `read_only=True` 构造模式:跨 profile 聚合用,`mode=ro` 打开、完全跳过 schema init、**不取任何写锁**,轮询别的 profile 的活库不干扰其后端(2054-2070)。

### 2.2 写协议:BEGIN IMMEDIATE + 时间预算 + 抖动重试

统一入口 `_execute_write`(区域 `hermes_state.py:2562-2690`)。核心循环起于 2608:

`hermes_state.py:2608-2620 @ 863e313`

```python
        while True:
            try:
                with self._lock:
                    self._conn.execute("BEGIN IMMEDIATE")
                    try:
                        result = fn(self._conn)
                        self._conn.commit()
                    except BaseException:
                        try:
                            self._conn.rollback()
                        except Exception:
                            pass
                        raise
```
(2608-2620)

BEGIN IMMEDIATE 让锁冲突在事务**开始**时暴露而非 commit 时。`locked/busy` 时释放 Python 锁、睡随机抖动再重试。**预算是时间制不是次数制**,理由写在类头(hermes_state.py:1908-1917 @ 863e313):

```python
    # Patience is TIME-based, not attempt-based.  A shared state.db is
    # legitimately held for multi-second stretches by sibling Hermes
    # processes: a TRUNCATE checkpoint at close on a large WAL, VACUUM after
    # an auto-prune, offline recovery, or an older still-running process
    # whose FTS maintenance predates the bounded-merge protocol (every
    # `hermes update` leaves mixed-version processes sharing the DB until
    # the old ones exit).  An attempt-counted budget (~15s incidental worst
    # case) silently loses that race and surfaces as
    # session_persistence_failed — a destroyed turn — even though the store
    # is healthy and merely busy (#74478).
```

四档预算(hermes_state.py:1927-1947 @ 863e313):

```python
    _WRITE_PATIENCE_S = 20.0
    _TRANSCRIPT_WRITE_PATIENCE_S = 60.0
    ...
    _ACTIVITY_WRITE_PATIENCE_S = 0.5
    ...
    _COMPRESSION_BUSY_WAIT_S = 5.0
    _WRITE_RETRY_MIN_S = 0.020   # 20ms
    _WRITE_RETRY_MAX_S = 0.150   # 150ms
    _WRITE_RETRY_SLOW_AFTER_S = 2.0
    _WRITE_RETRY_SLOW_MIN_S = 0.250  # 250ms
    _WRITE_RETRY_SLOW_MAX_S = 1.000  # 1s
```

- 常规写 20s;**转录写**(append_message / append_messages_batch / 会话行创建)60s——失败即毁掉用户一轮(6445-6452、3093-3096);观测型心跳写 0.5s——绝不能拖响应关键路径(#76354,4225-4230);压缩锁碰撞单独 5s(见 §4)。
- 抖动前 2 秒走 20-150ms(毫秒级争用快速回收),超过后退到 250ms-1s(不用 BEGIN IMMEDIATE 锤长持有者),且不超过 deadline(`_sleep_before_write_retry`,2692-2718)。
- 预算耗尽的报错**重新措辞**,防止被读成磁盘/权限损坏(2654-2662):`database is locked (another Hermes process held the state.db write lock for over 60s — likely a long maintenance operation such as VACUUM ... the database itself is healthy)`。
- 另一个消息域重试:`no more rows available`——争用 WAL append 下的瞬态引擎错,异常**类**随 SQLite 构建变化(有的是 InterfaceError,在 DatabaseError 之外),故按消息不按类匹配(2598-2606、2682-2690)。

**打开也有耐心**:`_init_schema` 的 DDL 也可能撞上兄弟进程的长持锁,旧版本会 fail 整个 open → 整轮禁用持久化(#74478);现在 open 用同样的抖动等待包裹,非锁错误立刻传播(hermes_state.py:2164-2200 @ 863e313)。

### 2.3 跨进程业务锁:compression_locks 表

DB 内的租约表(DDL 在 hermes_state_common.py:326-331)承载"谁在压缩这个会话"的跨进程互斥。获取是单事务的 DELETE-expired + INSERT OR IGNORE + SELECT 确认(hermes_state.py:4054-4121 @ 863e313);过期锁与**死进程锁**都可回收——holder 串格式 `pid=<n>:...`,只有内核证明该 PID 不存在才立即回收,任何存疑(legacy 格式、权限错、同进程)都等 TTL(区域 `hermes_state.py:94-118`,下面这段起于 100):

`hermes_state.py:100-105 @ 863e313`

```python
    for the full TTL makes every new turn repeatedly attempt compaction. Reclaim
    only when the kernel proves that PID no longer exists; legacy/unstructured
    holders, same-process holders, permission errors, and any probe doubt
    remain protected until normal TTL expiry (conservative: PID reuse must
    never steal a live lease, and a wrongly-kept lease self-heals via TTL).
```

续约**只按 holder 不按 expires_at** 判归属:活着的 owner 被调度饿过 TTL 后必须能复活自己仍未被抢的行,否则它会在无租约保护下继续压缩轮换——正是竞争路径可分叉 lineage 的窗口;SQLite 串行化写保证 reclaim 与 refresh 不会交错出双主(hermes_state.py:4014-4030 @ 863e313)。锁子系统故障时 acquire **fail open 返回 False**(调用方跳过压缩,是安全方向,4138-4140)。

### 2.4 进程内异步化

- **token 记账队列**:每次 API 调用后的 token/cost 增量走 `queue_token_counts` 入 deque,daemon 写线程批量应用,相邻同路由增量合并(absolute 覆盖型绝不合并),`flush_token_counts` 可等待排空,close/atexit 排干;写线程死了会自动重生;coalesce 失败降级为逐条应用,记账丢失只记日志绝不打断一轮(hermes_state.py:4609-4837 @ 863e313)。busy 标志的置位顺序(先 busy 后清队列)专门为 flush 的无锁快路径设计(4711-4714)。
- **AsyncSessionDB**:每个调用 `asyncio.to_thread` 转线程的通用转发器,保证阻塞 SQLite 调用不冻结事件循环(hermes_state.py:9677-9691 @ 863e313)。

**重实现要点(机制 2)**
1. 单写连接 + 短 SQLite timeout(1s)+ 应用层随机抖动重试,是打破 convoy 的组合;BEGIN IMMEDIATE 把冲突前移。
2. 重试预算按**时间**并按写入的业务重要性分档(转录 60s > 常规 20s > 观测 0.5s);预算耗尽的报错要说人话。
3. WAL 下读写连接分离(读 per-thread `mode=ro`),DELETE 回退下退回单连接加锁——读路径策略必须随 journal mode 切换。
4. 跨进程互斥放在 DB 里做租约表:TTL + 结构化 holder(含 pid)+ 死进程即时回收 + "只按 holder 续约";存疑一律保守。
5. 瞬态错误按**消息**识别,不信异常类(SQLite 构建间不稳定)。

---

## 3. 会话生命周期(落盘 / 恢复 / new 与 reset)

### 3.1 会话怎么落盘:增量 append-only,每轮一个批事务

会话行创建是**宽容 upsert**:gateway 先建裸行(source+user_id),agent 随后带真 model/model_config/system_prompt 再调 `create_session`,`ON CONFLICT` 用 COALESCE 只补 NULL、绝不覆盖已有值(文档在 `hermes_state.py:2948-2958`,SQL 见下)

`hermes_state.py:2992-2994 @ 863e313`

```python
                   ON CONFLICT(id) DO UPDATE SET
                       model = COALESCE(sessions.model, excluded.model),
                       model_config = COALESCE(sessions.model_config, excluded.model_config),
```

带 `parent_session_id` 的子会话从父行回填 cwd/git_repo_root/git_branch/profile_name(只填 NULL;修 #64709 lineage 每次 fork 掉出项目侧栏、及跨 profile 跳会话 bug);**仅压缩 fork**(父 `end_reason='compression'`)额外继承 gateway 路由七列,防"建子后、gateway 重记 peer 前崩溃"把子会话困成不可路由(#59527);delegate/subagent 子会话**绝不**继承路由键,否则 peer 恢复可能把 gateway 流量指进子代理会话(hermes_state.py:3033-3092 @ 863e313)。`ensure_session` 是同一 upsert 的别名(5110-5119)。系统提示词按 sha256 去重存 `system_prompts` 表,行上只存 hash(1975-1994)。

**消息落盘是增量的,不是全量重写**。agent 侧 `_flush_messages_to_session_db_unlocked`(run_agent.py:2003-2262 @ 863e313)给每个已写入的消息 dict 盖内在标记 `_DB_PERSISTED_MARKER`,每次 flush 只扫出未标记的新消息,一轮的全部新行(user+assistant+tool,典型 3-8 条)通过 `append_messages_batch` 以**一个 BEGIN IMMEDIATE/commit** 落库(run_agent.py:2262;hermes_state.py:6454-6525)。标记法取代位置切片(repair_message_sequence 收缩历史后切片会空掉、投递的回复永不落库,#46053)与 `id(msg)` 集合(CPython 地址复用别名,#50372)。`append_messages_batch` 的 `chunk_rows` 参数给大拷贝(branch 种子上千行,实测 10k 行≈2.4s 单事务,FTS 触发器逐行跑)分块提交防饿死并发写者(6479-6499)。计数器 `message_count/tool_call_count` 在同事务内聚合更新(6508-6519)。

**边界护栏**:两个 append 入口共享 `_check_transcript_write_guards`,在写事务**内部**执行(hermes_state.py:6251-6282 @ 863e313):活压缩锁的非持有者 → `SessionCompressionInProgressError`(瞬态,见 §4);目标会话已被压缩关闭 → `CompressionSessionClosedError`(永久,调用方必须改投 live continuation)。

### 3.2 怎么恢复 / resume

读取两形态:`get_messages`(原始行,默认 `active = 1`,`ORDER BY id`)与 `get_messages_as_conversation`(OpenAI 会话格式)。**按 AUTOINCREMENT id 排序而非 timestamp** 是刻意的(hermes_state.py:7301-7308 @ 863e313):

```python
                # Order by AUTOINCREMENT id (true insertion order), NOT timestamp:
                # append_message stamps rows with time.time(), which is not
                # monotonic (WSL2, NTP steps, VM/laptop sleep resume). A later
                # row can carry an earlier timestamp than its predecessor, and
                # ORDER BY timestamp would then sort an assistant tool_calls row
                # after its tool response, breaking tool-call/response adjacency
                # and triggering an HTTP 400 on replay. This matches get_messages
                # — see c03acca50 for the original fix.
```

会话格式转换(`_rows_to_conversation`,7331-7462)要点:`api_content` 边车**逐字返回**(不 sanitize 不 strip),replay 用它替换 content 保持 provider prompt cache 前缀字节稳定(7361-7368);装载时跑两道防御性清洗——剥离旧版本泄漏进真实会话的后台 review harness 消息及其 curator 回复(7429-7439;判定在 372-394),剥离 #78148 的裸工具调用标记(7440-7446);`repair_alternation=True` 供**live replay** 调用方修复持久化的交替违规(如 user;user),只改内存列表不改库(7280-7289)。

**resume 目标重定向**是两步(hermes_state.py:7176-7263 @ 863e313):先 `get_compression_tip` 沿"父 `end_reason='compression'` 的子链"走到尖端——排除 `_branched_from`/`_delegate_from`/`source='tool'` 子,排序偏好"自身也是压缩延续 > 仍存活 > 已关闭的 stale 兄弟(如 ws_orphan_reap)",这替换了脆弱的 `started_at >= ended_at` 时序判据(gateway 与压缩竞态下真延续可先于父 ended_at 写入,而 stale websocket 建的兄弟反而满足时序;症状是桌面端"回来发现回复丢了",5719-5777);再从尖端向下走"最有消息的后代"(深度上限 32 防环)。

### 3.3 /new 与 /reset 的状态层语义:**永远轮换,从不清空**

- CLI `/new`:先把当前轮未 flush 的消息补 flush 进**旧**会话(#47202 防丢),然后 `end_session(old_session_id, "new_session")`,再生成新 session_id;新库行在首次 flush 时惰性创建;立即空掉的旧会话被清理防止刷屏 /resume(cli.py:8151-8169 @ 863e313,关键行 8151):

```python
            self._session_db.end_session(old_session_id, "new_session")
```

- gateway `/new`/`/reset` → `reset_session`:内存映射换新 entry + 新 id,旧行用 `promote_to_session_reset` 而非 `end_session` 关闭(gateway/session.py:2931-2942 @ 863e313):

```python
                # Promote (not plain end_session): an accidental
                # agent_close/ws_orphan_reap end must not survive an explicit
                # user reset, or recovery resurrects the reset session
                # (#61993 — the user's /new was silently undone).
                _promote = getattr(self._db, "promote_to_session_reset", None)
                if callable(_promote):
                    _promote(db_end_session_id, "session_reset")
```

两个原语的语义差(区域 `hermes_state.py:3591-3665`;下面这段起于 3653):`end_session` **第一个 reason 赢**(`WHERE ... AND ended_at IS NULL`,已结束即 no-op——压缩分裂会话必须保住 `end_reason='compression'`,不被 /resume 后失同步的 CLI 用别的 reason 覆盖);`promote_to_session_reset` 则额外允许覆盖两个"事故性"reason:

`hermes_state.py:3653-3659 @ 863e313`

```python
            cursor = conn.execute(
                "UPDATE sessions SET ended_at = ?, end_reason = ? "
                "WHERE id = ? AND (ended_at IS NULL "
                "OR end_reason IN ('agent_close', 'ws_orphan_reap'))",
                (now, reason, session_id),
            )
```

因为恢复查询把 `agent_close`/`ws_orphan_reap` 视为可恢复;若 reset 只用 no-op 的 end_session,已被 agent 清理误关的行仍可恢复,stale-route recovery 会带全部历史复活刚被 reset 的会话(#61220/#61993/#63539,3632-3640)。**清空原语 `clear_messages`(7996-8006)存在但全仓无生产调用方**(实测 grep 仅定义处)——即 /new /reset 都不是"清空同一会话",而是"关旧开新",历史永远保留在旧行下。撤销类操作(/rewind)也是软删:`active=0` 保留在盘,`rewind_count` 递增,可 `restore_rewound` 翻回(7610-7719)。

**重实现要点(机制 3)**
1. 转录持久化用"逐消息内在标记 + 每轮一个批事务"的增量 append;绝不用位置切片或 id() 集合去重。
2. 会话行用 COALESCE-only-NULL 的 upsert 解决"多个写者不同时刻各知道一部分元数据"的问题;lineage 继承按子会话类型区分(压缩 fork 继承路由,subagent 绝不)。
3. 恢复顺序键必须单调(自增 id),时间戳只做展示;重放路径要有边车保 prompt-cache 字节稳定,还要有针对历史污染的装载期清洗。
4. "新会话"永远是轮换 + 显式 end_reason,不是删除;end_reason 是一张小状态机:第一个 reason 赢,但显式用户意图(reset)可覆盖已知的事故性 reason 集合,且该集合必须与恢复查询的"可恢复集合"保持同步。

---

## 4. 与压缩的关系:state 层的两条落库路径

压缩引擎(context_compressor,另文)改写历史时,state 层提供两种形态:

### 4.1 轮换式(rotation fork):`publish_compression_child`

老式/gateway 压缩把父会话关闭、开新子会话装压缩后转录。关键是**单事务原子发布**(hermes_state.py:3503-3604 @ 863e313):

```python
        """Atomically close a parent and publish its durable compression child.

        The parent closure, child row, and compacted handoff become visible in
        one transaction. Readers can therefore observe either the live parent or
        a complete child, never an ended parent with a missing/empty child.
        """
```

事务内顺序:① 校验压缩租约仍属于本 holder 且未过期(`require_compression_lease`,3510-3522,失则 `CompressionSessionBusyError: Compression lease lost before publication`);② 校验父存在且未结束;③ 建子行并继承父的 cwd/branch/repo_root/profile/路由七列(3538-3571);④ 插入压缩后消息 + 写计数(3572-3578);⑤ 关父 `end_reason='compression'`,且用 `rowcount != 1` 检测发布期间父被并发改动(3579-3587)。配套读方:`find_live_compression_child` 只在"恰好一个活直接延续"时返回,多个歧义 fail closed(3445-3486);resume 方向由 `get_compression_tip`/`resolve_resume_session_id` 兜底(§3.2)。

### 4.2 就地式(in-place):`archive_and_compact`

#38763 之后的方向:会话终生一个 id,压缩不轮换。实现是"软归档 + 插入压缩集"的单事务(区域 `hermes_state.py:6938-7008`,核心一段起于 6987):

`hermes_state.py:6987-6994 @ 863e313`

```python
            conn.execute(
                "UPDATE messages SET active = 0, compacted = 1 "
                "WHERE session_id = ? AND active = 1",
                (session_id,),
            )
            inserted, tool_calls_total = self._insert_message_rows(
                conn, session_id, compacted_messages
            )
```

语义矩阵(docstring 6949-6961):`active=1` = live 上下文(get_messages/get_messages_as_conversation 默认只取它);`active=0, compacted=1` = "被摘要掉"——**仍可被 search_messages 发现**(FTS 触发器不看 active/compacted,翻 active 是内容不变的 UPDATE,不动索引);`active=0, compacted=0` = rewind/undo 的"用户收回",搜索默认隐藏。`message_count` 跟 live 集对齐。`model_config_patch` 同事务合并,`on_missing="raise"` 保证压缩不 commit 到已消失的会话行(6970-6979)。

对照的破坏式原语 `replace_messages`(/retry、/undo、/compress 旧路径):整删重插一个事务,默认删**全部**行(FTS 同步掉索引);`active_only=True` 只换 live 行,保住 archive_and_compact 留下的归档层——与就地压缩共存的 rewrite 调用方必须用它(6866-6922)。它同样拒绝写压缩已关闭的会话(6895-6905)。

### 4.3 并发写者与压缩的互动

普通 turn 写者撞上活压缩锁时不立刻失败:`_execute_write` 捕获 `SessionCompressionInProgressError` 后在 `_COMPRESSION_BUSY_WAIT_S = 5s` 内等待重试——压缩通常几秒内发布,无等待会把用户一轮打成 `session_persistence_failed`、还误导运维查磁盘(#75083);但预算故意短:租约是**正确性边界**,长时间/卡死的压缩之后放进来的写是"stale turn 落进父会话",必须拒绝(hermes_state.py:2628-2648 @ 863e313)。而"压缩者发现自己租约没了"是永久错误,直接 fast-fail 不烧预算(1686-1699)。行为规格测试见 §7。

压缩失败的冷却/回退簿记(cooldown、fallback_streak、ineffective_count)也落在 sessions 行上,state 层只提供 get/set(3736-4006),策略在压缩引擎侧。

**重实现要点(机制 4)**
1. 历史改写只能有两种形态,且都必须单事务:轮换式"关父+建子+装货"原子发布(读者要么见活父、要么见完整子);就地式"软归档+插入"(id 恒定,历史零destruction)。
2. 用两个正交 bit 编码行状态:`active`(是否进 live 上下文)× `compacted`(为何离开:被摘要 vs 被收回),搜索可见性按语义区分。
3. 压缩互斥 = DB 租约 + 发布前复验 + rowcount 断言,三点缺一不可;非持有写者短等后拒绝,持有者永不被自己的锁挡。
4. 破坏式 replace 必须提供 `active_only` 变体,否则与就地压缩组合会静默清掉归档层。

---

## 5. hermes_state_common:声明式 schema(common 侧)

**解决什么问题**:9691 行的 hermes_state 拆成 mixin 后,DDL 与共享 SQL 片段若留在主模块会形成 import 环;且 schema 演进需要"改一处、处处生效"的单一真源。common 是**零逻辑**(除三个小工具函数)的常量模块,hermes_state 全量 re-import 保持向后兼容(hermes_state.py:48-75)。

### 5.1 版本常量:两个独立版本号

`hermes_state_common.py:167 @ 863e313`
```python
SCHEMA_VERSION = 25
```

`hermes_state_common.py:170-178 @ 863e313`
```python
# FTS storage-layout version, tracked INDEPENDENTLY of SCHEMA_VERSION in the
# state_meta key ``fts_storage_version``. The main schema version advances
# freely on open (so future migrations always land); the FTS *layout* only
# reaches the current version when a DB is either born fresh or explicitly
# optimized via ``hermes sessions optimize-storage``. A legacy DB sits at
# layout 0 (marker absent) with a working inline index until the user opts in.
#   1 = v23 external-content layout (content/tool_name/tool_calls,
#       tool-row-excluded trigram)
FTS_STORAGE_VERSION = 1
```

这是关键分工:主 schema 版本随 open 自由推进(声明式调和保证未来迁移总能落地),FTS 布局版本只在"新生库"或"用户显式 optimize"时到位——磁盘重、耗时长的迁移绝不自动跑(hermes_state.py:2228-2234 也重申:opt-in、绝不 open 时自动)。

### 5.2 SCHEMA_SQL:单一真源 + 列调和

`SCHEMA_SQL`(hermes_state_common.py:197-373)用全 `CREATE TABLE IF NOT EXISTS` 声明 8 张表(schema_version、system_prompts、sessions 56 列、messages 23 列、session_model_usage、state_meta、gateway_routing、compression_locks、async_delegations)+ 基础索引。消费方式(schema mixin 侧,只述分工):`_init_schema` 先 `executescript(SCHEMA_SQL)`,再 `_reconcile_columns()` **解析 SCHEMA_SQL 提取期望列、diff 活表、ADD 缺失列**——增列只需改 SCHEMA_SQL 一处(hermes_state_schema.py:294-348、572-594 @ 863e313);版本号链只留给数据迁移与索引/FTS 变更。

**DEFERRED_INDEX_SQL 为什么单列**(hermes_state_common.py:376-380 @ 863e313):

```python
# Indexes that reference columns added in later schema versions must be
# created AFTER _reconcile_columns() has had a chance to ADD them on
# existing databases. SCHEMA_SQL above is run by sqlite executescript
# which would otherwise fail on legacy DBs ("no such column: active").
DEFERRED_INDEX_SQL = """
```

即声明式调和的执行顺序约束被物化成两个常量:表+老列索引先跑,引用新列的索引(如 `idx_messages_session_active`)等调和后跑。

### 5.3 FTS DDL:外容表 + 高水位标记门控触发器

v23 布局:`messages_fts` 是 external-content FTS5 表(`content='messages'`,零文本拷贝),同步靠三个触发器。触发器全部被 `state_meta` 里一对标记门控,这是**后台分块重建**能与在线写共存的机制(hermes_state_common.py:396-414 @ 863e313):

```python
# ── Deferred FTS rebuild bookkeeping (schema v23) ──
# While a background index rebuild is pending, two state_meta keys define
# which message rows are currently IN the FTS indexes:
#
#   fts_rebuild_high_water  H — MAX(messages.id) at the moment the old
#                                indexes were dropped
#   fts_rebuild_progress    P — highest id the chunked backfill has indexed
#
# A row is indexed iff  id <= P  (backfilled)  OR  id > H  (inserted after
# the drop; ids are AUTOINCREMENT so new rows are always > H and the insert
# triggers index them live).  Rows in (P, H] are not yet indexed.
#
# Every trigger below gates on that same predicate: firing an FTS5
# external-content 'delete' for a row that is NOT in the index corrupts the
# index, and skipping it for a row that IS indexed leaves a stale entry.
# When no rebuild is pending both keys are absent and COALESCE turns the
# predicate into a tautology (id > -1 OR id <= -1), i.e. normal operation.
```

insert 触发器示例(424-432):

```python
CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages
WHEN (new.id > COALESCE((SELECT CAST(value AS INTEGER) FROM state_meta
                         WHERE key = 'fts_rebuild_high_water'), -1)
   OR new.id <= COALESCE((SELECT CAST(value AS INTEGER) FROM state_meta
                          WHERE key = 'fts_rebuild_progress'), -1))
BEGIN
    INSERT INTO messages_fts(rowid, content, tool_name, tool_calls)
    VALUES (new.id, new.content, new.tool_name, new.tool_calls);
END;
```

update 触发器还叠了 `AFTER UPDATE OF content, tool_name, tool_calls` 列限定 + `IS NOT` 值比较双保险(444-451):

```python
-- UPDATE OF skips the trigger entirely for non-content column writes
-- (status/compacted/observed/etc.), which is stronger than the WHEN gate
-- alone and avoids FTS I/O saturation on large state.db (#68858 / #73639).
```

——这正是 §4.2 "翻 active=0 不动 FTS"的实现基础。

**trigram 表**(CJK/任意脚本子串搜索)同构,但读源是排除 `role='tool'` 行的视图 `messages_fts_trigram_src`:trigram 索引最贵(约文本 2.6 倍),而 tool 行占消息字节约 90% 且几乎全是机器噪音;tool 行仍全存 `messages`、仍可经标准 `messages_fts` 搜到,只是不做 CJK 子串处理(hermes_state_common.py:465-478 @ 863e313)。cjk_unicode61 变体(在 hermes_state.py:1538-1629,因依赖可加载扩展而不放 common)用**独立标记对** `fts_cjk_rebuild_*`,cjk-only 回填不门控主索引触发器;无 tokenizer 的进程自愈方式是**掉触发器保写入**、置 `FTS_CJK_STALE_KEY`(common:544-548)标记索引过期,等能干的主机 optimize 重建——"stale 索引必须掉触发器"因为对索引从未持有的 rowid 发 external-content 'delete' 正是 FTS5 的经典损坏手法(hermes_state.py:1566-1571)。

**LEGACY DDL 为什么还在**(hermes_state_common.py:551-561 @ 863e313):

```python
# ── Legacy (v22 / inline-content) FTS DDL ──────────────────────────────
# Used ONLY to keep an existing pre-v23 install's search working and its
# triggers repairable UNTIL the user opts into `hermes db optimize`. This is
# the exact inline shape v11..v22 shipped: each virtual table stores its own
# copy of ``content || tool_name || tool_calls`` and the trigram table indexes
# every row (including role='tool'). We never CREATE these on a fresh install —
# fresh installs are born on the v23 external-content schema above. These
# constants exist so a legacy DB is never accidentally handed the v23 DDL
# (which would create the external-content trigram source VIEW and leave the
# DB in a mixed, broken state). `optimize_fts_storage()` is what migrates a
# legacy DB to the v23 shape.
```

即 legacy 常量的存在本身是防御:修 legacy 库的触发器时必须发 legacy 形状的 DDL,防混合布局。

### 5.4 共享 SQL 片段(被多个 mixin 插值的查询原子)

- **预览三件套**(28-80):`_PREVIEW_RAW_SELECT` 对 /skill 脚手架消息取"头 400 + 尾 400"宽片段(打字指令在尾部),`_shape_preview` 在 Python 侧还原成 `/work — fix the title leak` 式短预览;普通消息取头 63 截 60。
- **子会话分类谓词**(83-114):`_BRANCH_CHILD_SQL`(稳定标记 `$._branched_from` OR legacy 时序启发)、`_COMPRESSION_CHILD_SQL`、`_ephemeral_child_sql`(= 非 branch 非 compression 的 delegate/subagent,级联删除目标)、`_LISTABLE_CHILD_SQL`(picker 只显示根 + branch 子)。这一组是 §3/§4 里"谁可见、谁级联删、谁能当 resume 目标"的唯一 SQL 定义点。
- **recency 表达式**(117-139):`MAX(last_activity_at, MAX(messages.timestamp))` COALESCE `started_at`,注释解释心跳限速 ~60s 会滞后于新消息,不能偏好 stale 心跳。
- `escape_like`(37-46):LIKE 通配转义,配 `ESCAPE '\'`,防 `_`(分支名/路径常见)静默放宽匹配。
- `MAX_FTS5_QUERY_CHARS = 2048`(184):对抗性输入前的查询长度上限。

**重实现要点(机制 5)**
1. DDL 做成"全 IF NOT EXISTS 的声明式真源 + 启动期列 diff 调和",版本号链只留给数据迁移;引用新列的索引单独一组、调和后执行。
2. 外容 FTS 的在线重建 = 双标记(高水位 H / 进度 P)+ 所有触发器共用同一谓词;`(P, H]` 即"未索引区间"。触发器谓词错一处就是索引损坏,所以谓词只写一遍(SQL 常量)。
3. 昂贵索引(trigram)用视图过滤低价值行;可选 tokenizer 缺失时"掉触发器保写入 + stale 标记 + 择机重建"。
4. legacy 布局的 DDL 要保留为常量并显式隔离,防止修复路径把新 DDL 发给旧库造成混合布局。
5. 跨查询共享的业务谓词(子会话分类、recency)下沉为 SQL 片段常量,保证列表/删除/恢复三方判定一致。

---

## 6. 文档对照(README / AGENTS.md / website/docs vs 代码)

README(所有语言版)完全不提 state.db/SessionDB;根 AGENTS.md 仅一行定位(`AGENTS.md:236 @ 863e313`:`hermes_state.py       # SessionDB — SQLite session store (FTS5 search)`),无冲突。主要对照对象是 `website/docs/developer-guide/session-storage.md`:

**文档说了但代码不是这样:**

| # | 文档 | 代码 |
|---|------|------|
| 1 | `session-storage.md:144`:"Current schema version: **23**" | `hermes_state_common.py:167`:`SCHEMA_VERSION = 25`(文档的迁移表也止于 23,缺 24/25) |
| 2 | `session-storage.md:178,186`:"random jitter (20-150ms, **up to 15 retries**)"、`_WRITE_MAX_RETRIES = 15` | 该常量已不存在(全仓 grep 仅文档);重试是**时间预算制**:`_WRITE_PATIENCE_S = 20.0` / `_TRANSCRIPT_WRITE_PATIENCE_S = 60.0`,且抖动 2s 后退到 250ms-1s(hermes_state.py:1927-1947)。注释里明说次数制 "~15s worst case" 正是被 #74478 废掉的旧行为 |
| 3 | `session-storage.md:13,28`:无条件 "WAL mode" | WAL 只是默认:有 NFS/SMB/FUSE/ZFS 回退 DELETE(hermes_state.py:654-817)、`database.journal_mode` 操作员旋钮(614-637)、WAL-reset 漏洞构建上**新库拒绝 WAL**(710-719)。同样过时的还有 hermes_state.py:10 自己的文件头注释 |
| 4 | `session-storage.md:135`:"kept in sync via **three** triggers" | 每个索引家族各 3 个,共最多 9 个(messages_fts / trigram / cjk;`_FTS_TRIGGERS` common:187-194、`_FTS_CJK_TRIGGERS` common:537-541);且 cjk 表整个未进文档正文的触发器叙述 |
| 5 | `session-storage.md:369-383` 的 "Recent Sessions with Preview" 示例 SQL:`SUBSTR(m.content,1,63)` 按 `ORDER BY m.timestamp` | 实际预览是 scaffold 感知的 CASE 表达式(头+尾拼接,common:59-68),排序键是 `_sql_session_last_active` 的"心跳与消息取新"表达式(common:117-139);文档示例作为教学 SQL 可用,但与产品行为不同 |
| 6 | `session-storage.md:399-401`:`db.clear_messages(...)` 列为常规清理操作 | 原语存在(hermes_state.py:7996)但全仓无生产调用方;真实的"重新开始"路径是轮换 + end_reason(§3.3) |

**代码有但文档没讲(择要):**

1. 整个耐久性防线:零化库隔离(#68474)、malformed schema 多级自修复阶梯、写路径一次性 FTS 自愈、可写性 preflight、锁安全字节访问——文档零提及(唯一接近的是 Database Location 一节列了 -wal/-shm 文件名)。
2. macOS 耐久性补丁(`checkpoint_fullfsync=1`、强制 `synchronous=FULL`,hermes_state.py:519-581)。
3. `database.*` 配置面:`journal_mode`/`cache_size`/`mmap_size`/`temp_store`/`wal_autocheckpoint`/`journal_size_limit`(hermes_state.py:957-1016;`cli-config.yaml.example:15-18` 有,website docs 无——`grep -rn journal_mode website/docs docs` 零命中)。
4. 读路径分离(WAL 下 per-thread 只读连接)与 `read_only=True` 跨 profile 模式(2253-2321、2054-2102)。
5. `active`/`compacted` 的语义矩阵与 `archive_and_compact` 就地压缩(文档只在 "Abridged" 列名里带过 active/compacted;倒是 `docs/micro-compaction.md:142-147` 讲了,website 开发者指南没讲)。
6. 压缩锁表/租约协议、`publish_compression_child` 原子发布、写护栏异常族(§4 全部)。
7. token 记账异步队列与 AsyncSessionDB(§2.4)。
8. FTS_STORAGE_VERSION 双版本制与 opt-in optimize(common:170-178)——文档 v23 行提了 "opt-in transition" 半句,未讲双版本机制。

---

## 7. 配套测试清单与行为规格

`find tests -name '*state*'` 中属于本簇的(排除无关的 browser/file/turn state):

- `tests/test_hermes_state.py`(165 个 test,主行为面)
- `tests/test_hermes_state_wal_fallback.py`(WAL 回退矩阵)
- `tests/test_zeroed_state_db.py`(零化隔离)
- `tests/test_state_db_malformed_repair.py`(修复阶梯)
- `tests/test_hermes_state_compression_busy_retry.py`(压缩锁 × 写耐心)
- `tests/test_hermes_state_compression_locks.py`(租约协议)
- `tests/test_hermes_state_readonly_preflight.py`(层 0 预检)
- `tests/hermes_state/test_session_read_state.py`(已读/未读位)
- 相邻但属别簇:`tests/agent/test_compression_rotation_state.py`、`tests/run_agent/test_compression_abort_state_reset.py` 等。

最像**行为规格**的三个:

1. **`tests/test_hermes_state_compression_busy_retry.py`** —— 模块 docstring 直接是一份 SLA:"A live compression lock must delay a concurrent append, not destroy the turn."。断言:普通写者等出 0.3s 后释放的锁且消息不丢(`test_append_waits_out_a_live_compression_lock`:`elapsed >= 0.25` 且行存在);永不释放的锁在预算内被拒(`elapsed >= 0.4` 且 `< 10`,抛 `CompressionSessionBusyError`);**锁持有者自己写零延迟**(`< 0.2s`);丢失租约 fast-fail 不烧预算。这五条合起来就是 §4.3 的完整契约。
2. **`tests/test_hermes_state_wal_fallback.py`**(22 个 test)—— 逐条覆盖 §1.2 的分支矩阵:`locking protocol`/`not authorized` 回退 DELETE、**静默拒绝**也回退并告警(`test_falls_back_when_wal_silently_refused`)、瞬态 disk i/o 重试后恢复 WAL vs 持续性回退 DELETE、磁盘头已 WAL 绝不降级(两个变体)、无关 OperationalError 原样抛、ERROR 按 db_label 去重且各库独立、`require_wal` 三态、init 失败原因被捕获进 `/resume` 文案。
3. **`tests/test_state_db_malformed_repair.py`** —— 阶梯的因果规格:先证明损坏类症状(`test_duplicate_fts_makes_every_statement_fail`:重复 schema 让**每条**语句失败),再证明各级修复(读损坏就地 rebuild、写损坏被写探针抓到并就地修复、REINDEX 修 stale b-tree 且**保留行数据**)、修复后搜索可用、每进程只自动修一次、不可修文件安全失败。零化簇同理:`test_concurrent_quarantine_no_clobber` 与 `test_quarantine_fails_closed_when_lock_held` 把 #68805 的 fail-closed 契约钉死。

---

## 8. 覆盖边界说明

本底稿覆盖 `hermes_state.py` + `hermes_state_common.py` 两文件的五大机制。同文件中未展开的次要面:gateway 路由表 CRUD(3206-3444)、Telegram topic 绑定(8851-9362)、handoff 状态机(9585-9675)、prune/vacuum/auto-archive(8333-8668、9392-9583)、会话标题/归档/置顶/已读位(5294-5688)——均为常规 CRUD,复用 §2 的写协议,无独立机制;`hermes_state_schema.py`(调和与迁移执行)、`hermes_state_search.py`(FTS 查询侧)、`hermes_state_portability.py`(导入导出)按计划属后续轮次,本文仅在分工处引用。