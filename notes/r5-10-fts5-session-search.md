# R5 底稿 · FTS5 跨会话检索

**结论(≤20 字):三索引三分工,触发器带闸,四形态低 token 钻取。**

> 溯源约定:所有断言紧跟 `路径:行号 @ 863e313` + 逐字代码摘录(行号实测于基线 commit 863e31318553cda8ad61df681d08175364d4164b,hermes-agent 只读)。
> 本底稿覆盖:`hermes_state_search.py`(2230 行,L1)、`tools/session_search_tool.py`(1161 行,L1)、`native/fts5_cjk/fts5_cjk.c`(252 行)+ `build.sh` + `README.md`(结构级);为证据完整性延伸引用了 `hermes_state_common.py` / `hermes_state.py` / `hermes_state_schema.py` 的 FTS 相关段落(这三个文件的全量精读归属各自轮次)。

---

## ▲★ 定案:「跨会话召回:FTS5 三索引 session_search(discovery/scroll/read/browse)」

**定案成立,细节修正如下:**

1. **三索引确认**:`messages_fts`(unicode61 词级,唯一覆盖 tool 行)、`messages_fts_trigram`(trigram 子串,排除 tool 行)、`messages_fts_cjk`(cjk_unicode61 双字 bigram,排除 tool 行,依赖可加载 C 扩展)。三者都是 v23 external-content 表(不复制正文),权威列表在 `hermes_state.py:9362 @ 863e313`:
   ```python
   _FTS_TABLES = ("messages_fts", "messages_fts_trigram", "messages_fts_cjk")
   ```
2. **第四条路是 LIKE 全表扫描**,作为永远可用的兜底(短 CJK、tokenizer 缺失、索引损坏时),不是索引。
3. **工具面四形态确认**(discovery/scroll/read/browse);官方 user-guide 文档仍写"Three calling shapes",是文档滞后(见 §6)。
4. **增量维护 = 触发器 + 标记闸 + 手动分块回填**:没有后台线程自动回填;`fts_rebuild_step` 只被 `optimize_fts_storage`(CLI `hermes sessions optimize-storage`)前台驱动,回填期间查询侧用"缺口补查"保证召回不缺(见 §2.4、§3.5)。

---

## 1. 三索引:建表语句、tokenizer、分工

### 1.1 模块契约

`hermes_state_search.py` 是 `SessionDB` 的纯 mixin(无 `__init__`、无自有状态),`hermes_state_search.py:1-9 @ 863e313`:

```python
"""Full-text / trigram / CJK message search and FTS maintenance for SessionDB.

Mixin contract: this is a plain mixin class consumed by
``hermes_state.SessionDB``. It defines no ``__init__`` and no state of its
own; methods access the host's attributes (``self._conn``, ``self.db_path``,
``self._execute_write`` and other SessionDB methods) established by
``SessionDB.__init__``. It must never import hermes_state (cycle) — shared
module-level constants live in hermes_state_common.
"""
```

### 1.2 索引一:`messages_fts` —— unicode61 词级,全角色覆盖

建表 DDL(未写 `tokenize=`,即 FTS5 默认 unicode61 词级分词;external-content 直接挂 `messages` 表),`hermes_state_common.py:415-422 @ 863e313`:

```sql
FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    tool_name,
    tool_calls,
    content='messages',
    content_rowid='id'
);
```

"默认即 unicode61"由查询侧注释自证,`hermes_state_search.py:1819-1821 @ 863e313`:

```python
        # Pure-Latin queries run against the unicode61 ``messages_fts`` table,
        # whose tokenizer does not insert a boundary between Latin letters and
        # adjacent CJK characters: "修改youer服务端" is indexed as one token,
```

**分工**:拉丁/词级查询主索引;三索引中唯一收录 `role='tool'` 行(tool 输出仍可搜,见 1.3 的排除说明)。

### 1.3 索引二:`messages_fts_trigram` —— trigram 子串,排除 tool 行

为什么排除 tool 行 + 成本账,`hermes_state_common.py:465-478 @ 863e313`:

```python
# Trigram FTS5 table for CJK substring search.  The default unicode61
# tokenizer splits CJK characters into individual tokens, breaking phrase
# matching.  The trigram tokenizer creates overlapping 3-byte sequences so
# substring queries work natively for any script (CJK, Thai, etc.).
#
# The trigram index is the most expensive index in state.db (~2.6x the size
# of the text it covers), and ``role='tool'`` rows are ~90% of message bytes
# while being almost entirely machine noise (base64 payloads, file dumps,
# delegation transcripts).  The index therefore reads through
# ``messages_fts_trigram_src``, a view that excludes tool rows — they stay
# fully stored in ``messages`` and fully searchable via the standard
# ``messages_fts`` index; they just don't get trigram (CJK substring)
# treatment.  ``search_messages`` routes CJK queries that filter on
# ``role='tool'`` to the LIKE fallback for the same reason.
```

DDL:external-content 挂到排除 tool 行的**视图**上,`hermes_state_common.py:479-492 @ 863e313`:

```sql
FTS_TRIGRAM_SQL = """
CREATE VIEW IF NOT EXISTS messages_fts_trigram_src AS
    SELECT id, role, content, tool_name, tool_calls
    FROM messages
    WHERE role <> 'tool';

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts_trigram USING fts5(
    content,
    tool_name,
    tool_calls,
    content='messages_fts_trigram_src',
    content_rowid='id',
    tokenize='trigram'
);
```

**分工**:任意文字的子串匹配(CJK 短语、泰文等),但每个查询词至少 3 字符(3 个 CJK 字符 = 9 UTF-8 字节)才能产生 trigram。需要 SQLite >= 3.34(缺失时仅降级该索引,`hermes_state.py:2341-2353`)。

### 1.4 索引三:`messages_fts_cjk` —— cjk_unicode61 双字 bigram(可加载扩展)

动机与设计总述,`hermes_state.py:1540-1564 @ 863e313`:

```python
# The trigram tokenizer needs >=3 chars per query term, so 1-2 char CJK
# terms (ubiquitous in Korean/Chinese: 일본, 구글, 项目, ...) fall through
# to a LIKE full-table scan — measured 3-6s CPU per query on multi-GB
# installs and the dominant base cost of session_search on CJK workloads.
#
# ``cjk_unicode61`` (native/fts5_cjk/, a ~250-line loadable FTS5 tokenizer
# with no dependencies) wraps unicode61: maximal CJK runs are re-emitted as
# overlapping character bigrams (Lucene CJKAnalyzer semantics), everything
# else passes through unchanged. FTS5 phrase semantics turn a query term's
# consecutive bigrams into exact substring matching down to 2 chars at
# index speed. Contributed by Soju06 (PR #65544).
#
# Same v23 storage discipline as the trigram table it replaces:
# external-content over a tool-row-excluding view (zero inline text
# copies; tool rows stay searchable via ``messages_fts``), triggers gated
# on a DEDICATED marker pair (``fts_cjk_rebuild_high_water`` /
# ``fts_cjk_rebuild_progress``) so a cjk-only backfill — e.g. the
# trigram→cjk upgrade on an already-optimized DB — never gates the
# complete ``messages_fts`` index's triggers.
#
# The table exists ONLY when the loadable tokenizer is available
# (``~/.hermes/lib/libfts5_cjk.so``, built by ``native/fts5_cjk/build.sh``).
```

DDL,`hermes_state.py:1572-1586 @ 863e313`:

```sql
FTS_CJK_TABLE_SQL = """
CREATE VIEW IF NOT EXISTS messages_fts_cjk_src AS
    SELECT id, role, content, tool_name, tool_calls
    FROM messages
    WHERE role <> 'tool';

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts_cjk USING fts5(
    content,
    tool_name,
    tool_calls,
    content='messages_fts_cjk_src',
    content_rowid='id',
    tokenize='cjk_unicode61'
);
"""
```

扩展加载(config 开关 `sessions.cjk_fts`/环境变量、.so 路径可覆盖、永不 raise),`hermes_state.py:1646-1668 @ 863e313`:

```python
def load_fts5_cjk_extension(conn: sqlite3.Connection) -> bool:
    """Best-effort load of the cjk_unicode61 tokenizer into ``conn``.

    Returns False (never raises) when the .so is absent, the feature is
    disabled via ``sessions.cjk_fts``, or this Python build has extension
    loading compiled out — every caller treats False as "behave exactly as
    before the cjk index existed".
    """
    if not _cjk_fts_config_enabled():
        return False
    path = fts5_cjk_so_path()
    if not path.exists():
        return False
    try:
        conn.enable_load_extension(True)
        try:
            conn.load_extension(str(path))
        finally:
            conn.enable_load_extension(False)
        return True
    except Exception:
        logger.warning("fts5_cjk extension load failed (%s)", path, exc_info=True)
        return False
```

写连接在 `__init__` 里先加载扩展再建 schema(`hermes_state.py:2161`:`self._fts_cjk_loaded = load_fts5_cjk_extension(self._conn)`);每个只读连接也要各自加载(tokenizer 注册在连接内存里,不在 DB 文件里),`hermes_state.py:2283-2288 @ 863e313`:

```python
            # Load the CJK tokenizer extension on this connection so
            # messages_fts_cjk queries work on the read path. The .so
            # registers the tokenizer in the connection's in-memory
            # registry, not the database file, so mode=ro is fine.
            if self._fts_cjk_loaded:
                load_fts5_cjk_extension(conn)
```

两个可用性状态位分层:`_fts_cjk_loaded`(本进程能分词)与 `_fts_cjk_available`(表可查且非 stale 且回填已完成),`hermes_state.py:2037-2042`。

### 1.5 为什么三个索引而不是一个

每个 tokenizer 的能力/成本不可兼得,代码给了完整证据链:

| 索引 | 能力 | 缺陷(原文证据) |
|---|---|---|
| `messages_fts` (unicode61) | 词级排序检索,体积最小,覆盖 tool 行 | 整段 CJK 是一个 token,2 字查询永不命中(`fts5_cjk.c:4-8`);拉丁字母粘在 CJK 边上不切分(#54242,`hermes_state_search.py:1819-1826`) |
| `messages_fts_trigram` (trigram) | 任意文字子串匹配 + rank + snippet | 体积 ~2.6x、故排除 tool 行(`hermes_state_common.py:470-473`);每词 ≥3 字符(`hermes_state_search.py:1212-1227`);需 SQLite ≥ 3.34 |
| `messages_fts_cjk` (cjk_unicode61) | 2 字 CJK 精确子串、索引速度;拉丁/CJK 混排切开 | 依赖可加载 C 扩展,宿主可能没有(`hermes_state.py:1560-1564`);孤立单字只有 unigram,单字查询语义比 LIKE 窄(`hermes_state_search.py:1194-1210`) |

即:**一个索引没有任何 tokenizer 能同时做到"词级排序 + 任意子串 + 2 字 CJK + 全宿主可用"**,于是按查询形状路由到能力最强的可用索引,LIKE 扫描做全兜底(§3)。

**重实现要点(§1)**
- external-content FTS(`content='表/视图'`)让索引零正文拷贝;想按行子集建索引,把 content 指向一个 `WHERE` 视图即可(rowid 仍是基表 id)。
- 机器噪音(tool 输出)只进最便宜的词级索引,不进高倍率子串索引——用"视图裁剪"而非"不存"。
- CJK 双字 bigram + FTS5 短语语义(一个查询词发射的连续 token 自动成短语)= 2 字级子串精确匹配,这是 Lucene CJKAnalyzer 的老方案,在 SQLite 上用 250 行 C 包装 unicode61 就能拿到。
- 能力探测要分层:模块缺失(FTS5 全关)≠ 单 tokenizer 缺失(仅该索引降级),错误串区分见 `hermes_state.py:2326-2353`。

---

## 2. 增量维护:触发器 + 标记闸 + 分块回填

### 2.1 触发器与"回填标记闸"

核心不变式:回填期间哪些行"在索引里"由两个 `state_meta` 键定义,每个触发器用同一谓词把闸,`hermes_state_common.py:396-414 @ 863e313`:

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

INSERT 触发器实例(base 索引),`hermes_state_common.py:424-432 @ 863e313`:

```sql
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

DELETE/UPDATE 触发器用 external-content 专用的 `'delete'` 命令(把旧值喂回去生成删除 token);trigram/cjk 触发器额外 `WHEN role <> 'tool'`,UPDATE 还监听 `role` 列变化(role 翻转 = 进出索引),`hermes_state_common.py:516-533`(trigram)与 `hermes_state.py:1611-1628`(cjk,用独立标记对 `fts_cjk_rebuild_*`)。触发器名单:`hermes_state_common.py:187-194`(6 个)+ `hermes_state.py` 侧 `_FTS_CJK_TRIGGERS`(`hermes_state_common.py:537-541`,3 个),共 9 个。

### 2.2 UPDATE OF 列窄化(写放大事故的修法)

`hermes_state_common.py:444-448 @ 863e313`:

```sql
-- UPDATE OF skips the trigger entirely for non-content column writes
-- (status/compacted/observed/etc.), which is stronger than the WHEN gate
-- alone and avoids FTS I/O saturation on large state.db (#68858 / #73639).
CREATE TRIGGER IF NOT EXISTS messages_fts_update
AFTER UPDATE OF content, tool_name, tool_calls ON messages
```

事故因果:老触发器是宽 `AFTER UPDATE`,任何状态位翻转(active/compacted/observed)都要跑一遍 FTS delete+insert;大库上批量状态更新打满 FTS I/O(#68858/#73639)。修成 `UPDATE OF 内容列` + `IS NOT` 双保险后,状态更新完全绕过触发器体。迁移端还有专门一步把旧宽触发器替换掉、且 cjk 触发器如果无法安全重建就打 stale 隔离(`hermes_state_schema.py:117-210`,行为规格 `tests/test_fts_update_of_narrowing.py`)。

### 2.3 会话压缩/改写历史后索引怎么跟

关键:**压缩不改写内容列,只翻状态位,所以索引根本不用动;可见性在查询期用 WHERE 过滤**。`archive_and_compact` 文档自述,`hermes_state.py:6954-6961 @ 863e313`:

```python
        - The archived pre-compaction turns stay on disk (active=0) and stay
          DISCOVERABLE: they are marked compacted=1, and search_messages()
          includes compacted=1 rows by default — so session_search still finds
          them, unlike rewind/undo rows (active=0, compacted=0) which stay
          hidden. They remain in the FTS index (the messages_fts* triggers
          index on INSERT / drop on DELETE and don't key on active/compacted;
          flipping to active=0 is a content-preserving UPDATE) and are
          recoverable via get_messages(..., include_inactive=True).
```

查询期的对应过滤(#38763 语义:rewind 行隐藏、压缩归档行可见),`hermes_state_search.py:1457-1461 @ 863e313`:

```python
        if not include_inactive:
            # Live rows (active=1) AND compaction-archived rows (compacted=1)
            # are discoverable; only rewind/undo rows (active=0, compacted=0)
            # are hidden. See archive_and_compact() / #38763.
            where_clauses.append("(m.active = 1 OR m.compacted = 1)")
```

旧式"压缩轮换"(结束旧会话、开 `parent_session_id` 子会话)不动 messages 行,索引同样无感;可见性归工具面的 lineage 逻辑处理(§4.2)。真正删除(会话删除等)走 DELETE 触发器正常出索引。

### 2.4 分块回填引擎(无后台线程;CAS 认领 + 节流)

设计动机,`hermes_state.py:2862-2894 @ 863e313`(节选):

```python
    # `optimize_fts_storage()` (the `hermes sessions optimize-storage`
    # command) drops the legacy inline FTS indexes and backfills the new
    # external-content ones. A single blocking rebuild measured ~16 minutes
    # of held write lock on a real 25 GB DB, so the backfill runs in small
    # chunks, each in its own short write transaction:
    ...
    #   - multiple processes sharing the DB don't double-run it — each chunk
    #     claims work by compare-and-swap on fts_rebuild_progress, so even a
    #     concurrent second runner just interleaves chunks safely.
    ...
    _FTS_REBUILD_CHUNK_ROWS = 500
    _FTS_REBUILD_DUTY_FACTOR = 4.0      # sleep >= 4x chunk cost (≤20% duty)
    _FTS_REBUILD_MIN_PAUSE = 0.2        # seconds — floor between chunks
```

单块认领:进度值在 `BEGIN IMMEDIATE` 事务内重读(即认领),行区间按 id 而非行数(容忍空洞),进度与数据同事务提交(崩溃原子),`hermes_state_search.py:220-257 @ 863e313`(节选):

```python
        def _do(conn):
            # Re-read progress inside the write transaction (BEGIN IMMEDIATE
            # is already held by _execute_write) — this is the claim: two
            # workers can't read the same progress value concurrently.
            ...
            upper = min(progress + chunk, high_water)
            conn.execute(
                "INSERT INTO messages_fts(rowid, content, tool_name, tool_calls) "
                "SELECT id, content, tool_name, tool_calls FROM messages "
                "WHERE id > ? AND id <= ?",
                (progress, upper),
            )
            ...
            # Publish progress in the same transaction as the rows it
            # covers — crash-atomic: either both land or neither does.
```

收尾做 ±1000 id 的边界补扫(anti-join `*_docsize`,防迁移瞬间漏行),然后清标记(`hermes_state_search.py:111-159`;cjk 同构 335-359)。v22→v23 迁移的"降级"是 O(1) schema 手术:`PRAGMA writable_schema` 删 vtable 定义、shadow 表改名 `fts_v22_trash_*`,重删表数据推迟到分块 teardown(`hermes_state_search.py:605-671`)。整个迁移**明确 opt-in、前台、可续跑**,不自动触发(`hermes_state_schema.py:863-884`;每块之间按 4 倍块耗时睡眠,防止把共享 DB 的活网关饿死——实测早期版本占写锁 ~85%,`hermes_state_search.py:755-767`)。此外还有一套孤儿标记/空索引修复逻辑(`_repair_optimize_bookkeeping`、`_seed_fts_rebuild_markers`,`hermes_state_search.py:443-562`)和"拒绝在有残留工作时盖 `fts_storage_version` 章"的 settle 复核(`hermes_state_search.py:798-889`)。

### 2.5 日常维护与自愈

- **有界 merge 代替 optimize**:每 1000 次写触发一轮(`hermes_state.py:2625-2626`),每索引 ≤4 条 `('merge', 500)` 命令,先把 `usermerge` 降到 2 否则低层段永不合并;无界 `'optimize'` 实测持锁 9-18s/索引,会耗尽并发写者的重试耐心(`hermes_state.py:1950-1964`、`hermes_state_search.py:2161-2230`)。
- **损坏自愈**:MATCH 读到 `DatabaseError`(corrupt shadow table)→ 每实例一次 `INSERT INTO t(t) VALUES('rebuild')` 原地重建后重试;读写两侧共用同一恢复(`hermes_state_search.py:1781-1794`、`hermes_state.py:2736-2783`,#50502/#66296/#66724)。
- **tokenizer 缺失自愈**:无扩展进程打开带 cjk 索引的库时,先写 `fts_cjk_stale` 面包屑再 DROP cjk 触发器,保消息写活;stale 索引禁止服务读、禁止重装触发器(对未索引 rowid 发 'delete' 是 FTS5 标准腐蚀路径),只能下次 `optimize-storage` 从零重建(`hermes_state.py:2437-2468`、`hermes_state_search.py:361-398`)。

**重实现要点(§2)**
- external-content FTS 的同步铁律:索引成员关系必须与触发器闸严格一致,多删(对不在索引的行发 'delete')即腐蚀,少删即脏条目。用"id ≤ P OR id > H"单谓词同时服务回填与正常态(标记缺失时 COALESCE 退化为恒真)。
- 触发器写放大要用 `AFTER UPDATE OF 内容列` 从语法层掐,不能只靠 WHEN。
- 历史改写(压缩)设计成"翻状态位 + 查询期过滤",索引就永远不用跟着改写走。
- 大索引迁移三件套:O(1) 降级(writable_schema + rename)、分块 CAS 回填(进度与数据同事务)、限占空比节流(sleep ≥ k×块耗时)。
- 每一步都要假设"进程随时死在两条语句之间",为每个崩溃窗口留可续跑/可修复路径;`executescript` 会隐式 COMMIT,绝不能放进显式写事务里(`hermes_state_search.py:392-395`)。

---

## 3. 查询侧:sanitize → 路由 → 合并排序

### 3.1 Sanitizer(6 步,线性扫描防回溯)

`hermes_state_search.py:1085-1162 @ 863e313`(骨架摘录):

```python
    @staticmethod
    def _sanitize_fts5_query(query: str) -> str:
        ...
        # Cap user-controlled FTS input before any regex processing.
        query = query[:MAX_FTS5_QUERY_CHARS]
        # Step 1: Extract balanced double-quoted phrases ... single linear
        # scan rather than a regex so pathological quote runs cannot induce
        # backtracking.
        ...
        # Step 2: Strip remaining (unmatched) FTS5-special characters.
        sanitized = re.sub(r'[+{}():\"^]', " ", sanitized)
        # Step 3: Collapse repeated * ... remove leading *
        # Step 4: Remove dangling boolean operators at start/end
        # Step 5: Wrap unquoted dotted and/or hyphenated terms in double
        # quotes.  FTS5's tokenizer splits on dots and hyphens, turning
        # ``chat-send`` into ``chat AND send`` and ``P2.2`` into ``p2 AND 2``.
        sanitized = re.sub(r"\b(\w+(?:[._-]\w+)+)\b", r'"\1"', sanitized)
        # Step 6: Restore preserved quoted phrases
```

上限常量 `MAX_FTS5_QUERY_CHARS = 2_048`(`hermes_state_common.py:184`)。`:` 单独强调:FTS5 列过滤算子,`TODO: fix` 会被解析成 `column:term` 报 "no such column"(注释 1133-1137)。

### 3.2 路由决策树(与日志归因一致)

慢查询日志把路径名固化下来(`HERMES_SEARCH_SLOW_MS`,默认 1000ms;这是 2026-07 那次"LIKE 全扫拖垮 session_search"排查后的可观测性补丁,`hermes_state_search.py:1320-1327`),路径判定 `hermes_state_search.py:1358-1378 @ 863e313`:

```python
    def _describe_search_path(self, query: str) -> str:
        """Best-effort name of the routing path a query takes (log-only)."""
        try:
            sanitized = self._sanitize_fts5_query(query or "")
            if not sanitized:
                return "empty"
            if not self._contains_cjk(sanitized):
                return "fts5"
            raw = sanitized.strip('"').strip()
            if self._fts_cjk_available and not self._has_lone_cjk_run(raw):
                return "fts_cjk"
            tokens = [
                t for t in raw.split()
                if t.upper() not in {"AND", "OR", "NOT"} and self._contains_cjk(t)
            ]
            short = any(self._count_cjk(t) < 3 for t in tokens)
            if self._count_cjk(raw) >= 3 and not short and self._trigram_available:
                return "trigram"
            return "like_scan"
        except Exception:
            return "unknown"
```

即:**非 CJK → `messages_fts`;CJK → cjk 索引(可用且无孤立单字)→ trigram(每词 ≥3 CJK 字)→ LIKE**。

### 3.3 CJK 路由的三个精确闸

1. **孤立单字回 LIKE**:bigram 索引对 ≥2 字连段只存 bigram,单字仅在孤立时有 unigram,所以 1 字查询在索引里匹配不到"长串内部",LIKE 语义更宽,`hermes_state_search.py:1194-1210 @ 863e313`:

```python
    @classmethod
    def _has_lone_cjk_run(cls, query: str) -> bool:
        """True when any maximal CJK run in the query is a single char.

        The cjk-bigram index stores bigrams for runs >=2 chars and unigrams
        only for isolated chars, so a 1-char CJK term can't match inside
        longer runs there — those queries keep the LIKE substring route.
        """
```

2. **逐 token 的 3 字检查(#20494)**:`"广西 OR 桂林 OR 漓江"` 总 CJK 数 6 ≥3 但每词只有 2 字,trigram 必然 0 命中,必须整体路由 LIKE,且 LIKE 端把每个非算子 token 拆成独立 `LIKE ... OR ...` 条件(`hermes_state_search.py:1516-1526`、1721-1738)。
3. **role_filter 含 'tool' 时强制 LIKE**:trigram/cjk 都不含 tool 行(`hermes_state_search.py:1529-1533`)。

CJK 判定的码点表(统一表意文字/扩展 A/B、CJK 符号、平/片假名、谚文音节),`hermes_state_search.py:1164-1172`。

### 3.4 零结果拉丁回退(#54242)

unicode61 不在拉丁与相邻 CJK 之间切边界,`修改youer服务端` 整体一个 token,`MATCH "youer"` 永远 0 命中。修法:主查询 0 结果且非 CJK 且不要 tool 行时,依次退 cjk 索引(把拉丁段切出来,等价精确 token 命中)→ trigram(需每词 ≥3 字符),**严格只增不重排**,`hermes_state_search.py:1822-1875 @ 863e313`(决策注释节选):

```python
        # so MATCH "youer" finds nothing even though the substring is present
        # (#54242). When the exact-token search returns nothing, retry on the
        # substring-capable indexes. Preference order:
        #   1. messages_fts_cjk (when built): its tokenizer splits Latin runs
        #      off adjacent CJK, so "youer" is an exact ranked token match.
        #   2. messages_fts_trigram: substring matching, needs >=3-char
        #      tokens (shorter tokens produce no trigrams).
        # Gated on a zero-result miss so successful Latin searches keep their
        # unicode61 ranking — strictly additive, never reorders existing
        # hits. Trade-off on the trigram leg: any zero-result Latin query
        # gains substring semantics (e.g. "cat" can then match
        # "concatenate"). Genuinely absent terms still return []. Skipped for
```

三个 FTS 路径向 MATCH 传参前都做同一处理:非算子 token 逐个 `"..."` 包裹(内部 `"`→`""`),AND/OR/NOT 保留(`hermes_state_search.py:1259-1266`)。

### 3.5 排序、合并、回填缺口补查、结果整形

- **排序**:默认纯 BM25 `ORDER BY rank`;`sort="newest"/"oldest"` 时时间为主、rank 破平(`hermes_state_search.py:1445-1452`);LIKE 兜底固定按时间倒序、忽略 sort(1764)。
- **回填缺口补查**:回填未完时索引缺 `(P, H]` 区间,若结果不足 limit,就只对这段 id 区间做降级 LIKE 补查(FTS 查询降解为 AND 子串词),按 id 去重后追加——**召回优先于精度,区间随回填收敛到零成本**,`hermes_state_search.py:1796-1817 @ 863e313`:

```python
        # Deferred-rebuild supplement (schema v23): while the background
        # backfill is pending, the FTS indexes only cover rows outside the
        # (progress, high_water] gap. Top the results up with a bounded LIKE
        # scan over just that id range so search never silently loses old
        # messages mid-rebuild. The range shrinks as the backfill advances,
        # so this cost decays to zero. The CJK LIKE-fallback path above
        # already scans the whole base table and needs no supplement.
```

- **结果整形**:snippet 由 `snippet(表, -1, '>>>', '<<<', '...', 40)` 生成;可选 `context`(前后各 1 条,截 200 字符,仅当投影需要才逐条查);**最后统一 `match.pop("content")`——只回 snippet 省 token**(`hermes_state_search.py:1941-1943`);`fields` 白名单投影(`_SEARCH_MESSAGE_RESULT_FIELDS`,39-67)。

**重实现要点(§3)**
- 用户查询进 MATCH 前必须过独立 sanitizer:上限截断、线性扫描保护引号短语、剥特殊字符、点/连字符词强制短语化(否则 `my-app.config.ts` 被拆成 AND 词组)。
- 路由按"查询形状 × 索引可用性"决策,且**给每条路径起名并打进慢日志**——否则下次性能回归又要靠 trace 考古。
- 所有降级路径(索引缺失、损坏、回填中)都要保证"结果变慢/变粗但不静默变少";回退只在 0 结果时触发,保住主路径的排序质量。
- 兜底 LIKE 必须转义 `%`/`_`(`escape_like`,`hermes_state_common.py:37-46`)。

---

## 4. 工具面 `session_search`:四形态与低 token 钻取

### 4.1 单形状工具,参数推断模式

`tools/session_search_tool.py:863-873 @ 863e313`:

```python
    """Single-shape tool. Mode inferred from which args are set.

    Discovery: pass ``query``.
    Scroll:    pass ``session_id`` + ``around_message_id``.
    Read:      pass ``session_id`` (no anchor) — dumps the whole session.
    Browse:    pass nothing.

    Pass ``profile`` to read another profile's sessions (e.g. resolving an
    ``@session:<profile>/<id>`` link). Scroll wins over read/discovery when an
    anchor is set — the agent has asked for a specific slice.
    """
```

优先级:scroll(有锚点)> read(仅 session_id)> browse(无 query)> discovery。`@session:<profile>/<id>` 链接值直接传进来会被自动拆分(888-893)。工具 schema 里"FOUR CALLING SHAPES"全文描述见 999-1034,并要求模型引用会话时逐字写 `link` 值(desktop 渲染成带标题的链接)。默认排除来源 `("kanban", "subagent", "tool")`(第 40 行)。

### 4.2 discovery:一次调用给出"目标→命中→结局"

流程(`_discover`,690-845):
1. `search_messages(..., limit=300, fields=7 列投影)` —— 宽扫 300 行原始 FTS 命中(常量 `_DISCOVER_SCAN_LIMIT = 300`,第 56 行),投影里**不带 context/snippet 之外的正文**,因为最终响应自己水合窗口(59-68)。
2. **cron 降权(#19434)**:稳定排序把自动化来源排到交互会话之后——排除会造成"只召回 cron"的反面,降权保 cron 仍可达,`tools/session_search_tool.py:42-50 + 233-247 @ 863e313`:

```python
# Automation sources that are kept searchable but DEMOTED below interactive
# sessions in discover ranking. Cron jobs run on a schedule and accumulate
# large volumes of repetitive vocabulary (recurring project names, dates,
# "session", summaries); under bare BM25 they dominate the top-N FTS rows and
# starve out the user's own interactive sessions, producing "recall blindness"
# where only cron sessions surface (#19434). Demoting — not excluding — keeps
# cron content reachable when it's the only match, while interactive sessions
# always win when both match.
_DEMOTED_SESSION_SOURCES = ("cron",)
```

3. **按 lineage 去重**:每条命中沿 `parent_session_id` 走到根(`_resolve_to_parent`,114-146),同一 lineage 只留 BM25 最好的一条;标题精确匹配结果(`resolve_session_by_title`)占首位(623-687)。
4. **当前会话排除 + 两个记忆黑洞例外**:当前 lineage 默认跳过(已在上下文里),但压缩轮换旧会话(`end_reason='compression'`)与就地压缩归档行(`active=0, compacted=1`)必须放行——它们已被摘要挤出活上下文,`tools/session_search_tool.py:755-780 @ 863e313`(节选):

```python
        # Skip the current session lineage — UNLESS the content has been
        # compression-summarised out of the live context (memory black hole
        # after compression). Two sub-cases:
        #
        # Legacy rotation: the FTS hit lives in a session that itself ended
        # with end_reason='compression'. That session's content has been
        # replaced by a summary in the continuation child, so it must stay
        # discoverable. A delegation child living under a compression
        # continuation does NOT have end_reason='compression' itself, so it
        # stays excluded.
        #
        # In-place compaction: the FTS hit lives on the SAME session_id as the
        # current session, but the matched message row is an archived
        # (active=0, compacted=1) row. The live-context load filters active=1,
        # so that content is no longer in context — let it through.
```

5. **每个存活命中水合 anchored view**:`get_anchored_view(hit_sid, msg_id, window=5, bookend=3)` —— 锚点 ±5 条(默认只留 user/assistant,锚点本身任何角色都保留)+ 会话前 3 条 + 后 3 条(空正文的纯 tool-call 轮被跳过),设计意图 `hermes_state_search.py:919-921 @ 863e313`:

```python
        Bookends let an FTS5 hit anywhere in a long session yield the goal
        (opening) and the resolution (closing) on a single call — without
        loading the whole transcript.
```

6. **token 预算**:窗口消息截 4000 字符、bookend 截 1200(带 `content_truncated`/`original_content_chars` 元数据,250-295;820-825);bookend 里疑似压缩摘要前缀(`[CONTEXT COMPACTION` / `[CONTEXT SUMMARY]:`)的消息被过滤,防把巨型压缩载荷经搜索带回新会话(#43175,75-78 + 815-825);ANSI 转义序列剥掉(262-267)。
7. 响应附 `messages_before/after`(供 scroll 续钻)、`link`、以及回填进行中的 `index_rebuild` 提示(`_annotate_rebuild_status`,211-230,让模型知道薄结果 ≠ 事实)。

### 4.3 scroll:锚点翻页协议

`_scroll`(481-615):`get_messages_around` 原语(`hermes_state.py:7096-7174`:锚点存在性检查 → 前 window+1 条 DESC + 后 window 条 ASC,`messages_before/after` 判边界)。窗口钳制 [1,20];当前 lineage 守卫沿用 discovery 的两个例外(否则 discovery 刚返回的压缩历史会被 scroll 拒收,516-544);**lineage rebind**:模型把父会话 id 配了子会话的消息 id 时,若同 lineage 则静默改绑并附 warning(566-589)。翻页协议 = 把上一窗口的首/尾 id 回传为新锚点,边界消息在两窗都出现当定位标(schema 文本 1020-1024)。

### 4.4 read 与 browse

- **read**(387-434):整段转储,大会话回 head 20 + tail 10 并提示用 scroll 钻中段;目标 profile 未命中时**扫描所有 profile 的 state.db(只读)按 id 定位**(`_locate_session_db`,343-384,会话 id 全局唯一,模型丢了 profile 段也能找回)。
- **browse**(437-478):`list_sessions_rich` 按最近活跃取 limit+5 条,跳过当前会话与一切子会话(delegation/压缩延续),返回标题/预览/时间戳。

**重实现要点(§4)**
- 召回工具的核心产品形态是"一次调用 = 会话级摘要三明治(开头 bookend + 命中窗口 + 结尾 bookend)",而不是"消息命中列表"——模型不需要为判断相关性付整段转录的 token。
- 原始 FTS 行只是"发现计划"输入:宽扫(300)→ 类别降权(cron)→ lineage 去重 → 限量水合。排序修正一定要**稳定排序**,类内保 BM25。
- "已在上下文里的内容不要再喂回来"需要精确的例外集:凡被摘要挤出活上下文的(轮换旧会话、就地归档行)必须重新可见,否则压缩即失忆。
- 一切正文出口都设截断预算并标注截断元数据;机器噪音(压缩摘要、ANSI)在工具面再过滤一层。
- 形态推断(按参数组合)让单工具承载 4 个动作,省一个 enum 参数,也避免模型选错 mode;但优先级必须显式定义(锚点 > 只读 > 浏览 > 检索)。

---

## 5. `native/fts5_cjk/` 结构级:cjk_unicode61 分词器

### 5.1 策略:包装 unicode61,CJK 连段重发射为 bigram

自述,`native/fts5_cjk/fts5_cjk.c:4-21 @ 863e313`(节选):

```c
** Why: SQLite's unicode61 tokenizer treats a CJK run as ONE token
** ("웅기가말했다" indexes as a single 6-char token), so a 2-char Korean
** query can never match inside it. The stock trigram tokenizer fixes
** substring search but needs >=3 chars per query term — 2-char Korean
** words (일본, 구글, 우리, ...) fall through to a full-table LIKE scan,
** measured at 3-6s per query on a 6.8GB messages table and the #1 driver
** of hermes session_search latency.
**
** What: wrap unicode61. Every token it emits is re-examined; maximal CJK
** runs inside the token are re-emitted as overlapping character BIGRAMS
** (Lucene CJKAnalyzer semantics), non-CJK segments pass through unchanged.
** A lone CJK char (run length 1) is emitted as a unigram. Because FTS5
** turns consecutive tokens emitted from one query term into a phrase,
** a query word like 캘린더 → [캘린][린더] gets exact substring semantics
** with index-speed lookups, down to 2-char terms.
```

结构四件套:
1. **委托构造**:`cjkCreate` 通过 `fts5_api.xFindTokenizer("unicode61")` 拿到内建 tokenizer 并实例化,额外参数原样透传(如 `remove_diacritics 2`),`fts5_cjk.c:173-194`。
2. **回调拦截**:`cjkTokenize` 把自己的 `cjkInnerCallback` 塞给 unicode61,每个 unicode61 token 过 `cjk_emit` 再发射(204-213)。
3. **`cjk_emit` 核心**(96-165):快路径——token 内无 CJK 码点则原样透传;否则线性切分:非 CJK 段整段发射;CJK 连段用三元素滚动边界数组发 overlapping bigram,单字连段发 unigram;字节偏移按 token 内位置映射并 clamp 到 `[iStart,iEnd)`(CJK 折叠是恒等,偏移精确;变长折叠的重音拉丁只影响高亮不影响匹配,86-95)。CJK 判定表(34-47)比 Python 端多覆盖谚文字母 Jamo、兼容表意字、片假名音标扩展。自带宽容 UTF-8 解码器(无效字节按单字节解码,保证终止,49-70)。
4. **注册**:`SELECT fts5(?1)` + `sqlite3_bind_pointer` 拿 `fts5_api`,`xCreateTokenizer(pFts, "cjk_unicode61", ...)` 注册;入口 `sqlite3_ftscjk_init`(SQLite 按文件名推导)+ 下划线拼法别名(217-252)。

### 5.2 构建与安装

`native/fts5_cjk/build.sh:10-18 @ 863e313`:

```bash
CFLAGS_EXTRA=""
if ! echo '#include <sqlite3ext.h>' | gcc -E -xc - >/dev/null 2>&1; then
  CFLAGS_EXTRA="-Ivendor"
fi

gcc -shared -fPIC -O2 -Wall -Wextra $CFLAGS_EXTRA fts5_cjk.c -o libfts5_cjk.so
dest="${1:-$HOME/.hermes/lib}"
mkdir -p "$dest"
install -m 0644 libfts5_cjk.so "$dest/libfts5_cjk.so"
```

无系统头文件时用 `vendor/` 内公版 amalgamation 头,零依赖;装到 `~/.hermes/lib/libfts5_cjk.so`(`HERMES_FTS5_CJK_SO` 可覆盖,`hermes_state.py:1631-1636`)。`native/fts5_cjk/README.md:14-22` 与代码一致:装好后下次 SessionDB open 建索引;已有数据需 `hermes sessions optimize-storage` 回填;新消息即刻活索引;`sessions.cjk_fts: false` 可关。

**重实现要点(§5)**
- 给 SQLite 加自定义分词最省的路子是**包装内建 tokenizer 而非重写**:委托构造 + 回调拦截,只处理自己关心的码段,其余透传(参数、大小写折叠、变音处理全部白拿)。
- bigram+短语语义是"2 字级子串搜索"的最小实现;偏移映射必须 clamp,否则 snippet 高亮越界。
- 可加载扩展注册在连接上而非文件上——每条(含只读)连接都要 load;设计降级路径时把"没有扩展的进程打开这个库"当成常态而不是异常(§2.5 的 stale 面包屑机制)。

---

## 6. 文档-代码对照(▲=冲突,◇=滞后/出入)

| # | 文档断言 | 代码事实 | 判定 |
|---|---|---|---|
| 1 | README.md:19:"…searches its own past conversations…" | 属实:session_search 四形态,FTS5 支撑,零 LLM 调用(`tools/session_search_tool.py:982-998`) | 一致 |
| 2 | `website/docs/user-guide/sessions.md:553`:"### Three calling shapes"(仅列 Discovery/Scroll/Browse) | 代码四形态,READ 是独立分支(`tools/session_search_tool.py:917-936`),工具 schema 自述 "FOUR CALLING SHAPES"(同文件 999) | ▲ 文档漏 READ 形态 |
| 3 | `website/docs/user-guide/features/memory.md:198`:"the three calling shapes (discovery / scroll / browse)" | 同上 | ▲ 同一滞后的第二处 |
| 4 | `website/docs/reference/tools-reference.md:158`:"Four shapes: discovery…scroll…read…browse" | 与代码一致 | 一致(可见 docs 内部互相矛盾,2/3 是旧文) |
| 5 | `website/docs/developer-guide/session-storage.md:144`:"Current schema version: **23**";迁移表止于 v23(165) | `SCHEMA_VERSION = 25`(`hermes_state_common.py:167`);v25 = system prompt 去重迁移(`hermes_state_schema.py:886-892`) | ▲ 版本号滞后两版 |
| 6 | `session-storage.md:135-138`:"kept in sync via three triggers…cover all three indexed columns" | 每索引 3 个触发器 × 3 索引 = 9 个;单索引描述正确 | ◇ 表述只覆盖 base 索引,未提 trigram/cjk 触发器与 role 闸 |
| 7 | `memory.md:205`:"~20ms FTS5 query, ~1ms scroll";`sessions.md:573`:"15–50ms" | 性能主张,代码无对应断言;慢日志阈值默认 1000ms(`hermes_state_search.py:1345`) | ◇ 不可由代码验证,仅记录 |
| 8 | `session-storage.md:17-19` 架构树列出三张 FTS 表含 `messages_fts_cjk` | 与代码一致 | 一致 |
| 9 | `native/fts5_cjk/README.md` 全文 | 逐条与 `load_fts5_cjk_extension`/`_ensure_fts_cjk_schema`/`optimize_fts_storage` 行为吻合 | 一致 |

---

## 7. 配套测试(行为规格)

**清单**(均在 @ 863e313;标 ✅ 的本轮实测运行通过):

| 文件 | 覆盖 |
|---|---|
| ✅ `tests/test_fts_cjk_bigram.py`(244 行,9 test;现场 gcc 编译 .so) | cjk 索引全生命周期:2 字韩文命中、混排/ASCII、单字回 LIKE、config 关断、v23 库补装索引+回填、v22 一步迁到 cjk、#54242 拉丁嵌 CJK 恢复、tool 行排除计数、integrity-check |
| ✅ `tests/test_search_slow_query_log.py`(60 行,5 test) | 慢日志阈值、路径归因(fts5/fts_cjk/trigram/like_scan)、包装器不改结果 |
| ✅ `tests/tools/test_session_search.py`(825 行,39 test) | 四形态、形态优先级、scroll 翻页协议、跨 profile、cron 降权、压缩摘要过滤、lineage、就地压缩/轮换可发现性 |
| `tests/test_fts_update_of_narrowing.py`(283 行,9 test) | UPDATE OF 窄化触发器安装/迁移/绕过、cjk 触发器隔离与恢复 |
| `tests/hermes_state/test_get_anchored_view.py` / `test_get_messages_around.py`(91/106 行) | 窗口/bookend/角色过滤/锚点保留/边界计数/前滚重锚 |
| `tests/test_hermes_state.py` 相关类 | `TestFTS5Search`(sanitizer、投影、context)、`TestCJKSearchFallback`、`TestFTS5ToolCallIndexing`、`TestFTSExternalContentMigration`(降级崩溃窗恢复等)、`TestOptimizeFts`(merge 步进)、`TestSessionIdSearch` 等 |

**行为规格 A —— 压缩后就地归档内容必须重新可发现**(`tests/tools/test_session_search.py:564-598 @ 863e313`):在会话 `s_compact` 写两条含 "spectral phoenix" 的消息 → `archive_and_compact` 用摘要替换活上下文 → 以 `current_session_id="s_compact"` 搜 "spectral phoenix",**必须命中且 session_id 就是当前会话**;对照组:未压缩的活内容(`s_live`)同参搜索必须 `count == 0`。这条把 §4.2 的"记忆黑洞例外"钉成回归测试:当前会话排除规则的边界不是"同会话",而是"是否仍在活上下文里"。

**行为规格 B —— v23 库补装 CJK 索引的灰度语义**(`tests/test_fts_cjk_bigram.py:111-143 @ 863e313`):先在无扩展环境写 10 条韩文消息,再换有扩展环境重开:断言 `_fts_cjk_loaded=True` 但 `_fts_cjk_available=False`(回填未完不服务)、`fts_cjk_rebuild_status()["pending"]`、`fts_optimize_available()=True`;**回填中新消息由 id 闸触发器活索引、旧查询走 legacy 路由仍有结果**;`optimize_fts_storage` 后 `_describe_search_path("기존") == "fts_cjk"` 且 10 条全召回。这条完整覆盖 §2 标记闸的三个不变式:新行即时入索引、旧行等回填、回填完成前索引绝不对外服务。

---

## 8. 遗留与交接

- 本底稿引用的 `hermes_state.py`(写路径/`_read_ctx`/健康探针)与 `hermes_state_schema.py`(迁移链)只取了 FTS 相关证据,两文件整体机制归其所属轮次精读。
- `resolve_session_by_title` / `list_sessions_rich` 的实现细节(标题唯一索引、lineage 投影)在会话列表簇,本轮仅作为 discovery 的依赖引用。
- 测试环境注记:本容器有 gcc,cjk .so 现场编译成功,故 CJK 测试未被 skip——报告数据可复现:`tests/test_search_slow_query_log.py + tests/test_fts_cjk_bigram.py` 14 passed,`tests/tools/test_session_search.py` 39 passed(`HERMES_PYTHON=/home/user/hermes-venv/bin/python`)。