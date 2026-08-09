# R5-01 声明式 schema 调和 + 会话可携带性(主线精读)

> 底稿。基线 `863e31318`。范围:`hermes_state_schema.py`(1079)、`hermes_state_portability.py`(714)、
> `agent/session_activity.py`(106)、`agent/message_content.py`(50)。
> hermes_state.py 本体与 hermes_state_common 由子代理深挖(r5-02),本篇覆盖 SessionDB 的
> schema 簇与 portability 簇两个 mixin,均主线逐行亲读。

## 0. Mixin 契约

两个文件同款开头(`hermes_state_schema.py:3-8 @ 863e313`):

```python
Mixin contract: this is a plain mixin class consumed by
``hermes_state.SessionDB``. It defines no ``__init__`` and no state of its
own; methods access the host's attributes (``self._conn``, ``self.db_path``,
``self._execute_write`` and other SessionDB methods) established by
``SessionDB.__init__``. It must never import hermes_state (cycle) — shared
module-level constants live in hermes_state_common.
```

9691 行的 SessionDB 按职责簇拆成 mixin(schema / portability / search),无自有状态、禁止反向导入,
共享常量下沉到 common——这是"单巨类拆文件"的一种低风险做法(不改运行时结构,只改文件组织)。

## 1. 声明式 schema 调和(▲ R1 条目,定案:证实)

**问题**:state.db 是 CLI/gateway/TUI/cron 多进程共享的唯一事实源,schema 随版本快速演进。传统
版本号-迁移链的痛点:迁移被重排/插队后某列被跳过,后续代码引用不存在的列崩掉。

**机制**(`hermes_state_schema.py:335-347 @ 863e313`):

```python
    def _reconcile_columns(self, cursor: sqlite3.Cursor) -> None:
        """Ensure live tables have every column declared in SCHEMA_SQL.

        Follows the Beets/sqlite-utils pattern: the CREATE TABLE definition
        in SCHEMA_SQL is the single source of truth for the desired schema.
        On every startup this method diffs the live columns (via PRAGMA
        table_info) against the declared columns, and ADDs any that are
        missing.
```

- **期望列的解析不用正则**:`_parse_schema_columns` 把 SCHEMA_SQL 灌进一个 `:memory:` SQLite,
  用 `PRAGMA table_info` 抽列——"SQLite itself handles all syntax … zero regex edge cases"
  (hermes_state_schema.py:292-333)。加列 = 只改 SCHEMA_SQL,下次启动自动出现。
- **每次启动跑,幂等自愈**:`_init_schema` 里 executescript(SCHEMA_SQL) 后立刻调和
  (hermes_state_schema.py:587-594),即使版本迁移被跳过列也会补上。
- **版本号保留但只管数据迁移**:"The schema_version table is retained for future data migrations
  (transforming existing rows) which cannot be handled declaratively"(hermes_state_schema.py:582-583)。

**调和表达不了的一类:PK 变更 → 专用"愈合"函数**。SQLite 不能 ALTER PRIMARY KEY,于是有两个
每次启动无条件跑的 PK 重建:

- `_heal_gateway_routing_pk`(hermes_state_schema.py:379-450,#59203):早期表是
  `session_key TEXT PRIMARY KEY` 无 scope 列;调和只能 ADD scope 列,复合 PK 永远落不上,
  于是每次 upsert 报 "ON CONFLICT clause does not match…"、退回 sessions.json、刷警告。
  修:rename→新表(复合 PK)→`INSERT OR REPLACE` 按 updated_at 升序拷贝(撞键新行胜)→drop 旧表。
- `_heal_session_model_usage_pk`(hermes_state_schema.py:452-570,#73823):v22 前已到 v22+ 的库
  PK 缺 task 维度,版本门槛不可达,每次记账 upsert 失败**中止整个写事务、静默清零 token 与成本记账**。
  修同款 rebuild;注意 FK 窗口(hermes_state_schema.py:496-506):

```python
        # FK-off window: ... INSERT OR IGNORE does NOT suppress
        # foreign-key violations (OR IGNORE only covers uniqueness/NOT
        # NULL conflicts), so an orphaned usage row ... would abort the
        # whole rebuild.  Disable FK enforcement for the copy and restore
        # it afterwards.
```

**再一类调和的坑:ADD COLUMN 丢默认值**(hermes_state_schema.py:624-639,#51646):老版调和器
重建列类型时没带 `NOT NULL DEFAULT 1`,于是 INSERT 省略该列写入 NULL,`WHERE active = 1` 的
transcript 加载器**把整段历史藏没了**。修:每次启动无条件 `UPDATE messages SET active = 1
WHERE active IS NULL`(原先门槛在 version<12,对已 v12+ 的库永不再跑——所以改成无条件)。

**取舍**:调和让"加列"零成本、免版本链;代价是 PK/索引/数据变换仍要专门路径,且调和器自身的 bug
(丢 DEFAULT)会静默传播——修复模式是"无条件幂等愈合",而不是再加版本门槛。

## 2. FTS 的三层防御:探测、退化、opt-in 大迁移

### 2.1 FTS5 可用性探测与只降不崩

- 探测靠真建一张 temp 虚表(hermes_state_schema.py:60-69);跑在无 FTS5 的 sqlite 运行时上时,
  **只丢触发器**保核心持久化继续(hermes_state_schema.py:643-649),未来运行时有 FTS5 再由
  `CREATE TRIGGER IF NOT EXISTS` 修回。
- 缺 trigram tokenizer ≠ 整个 FTS 不可用:`_fts_table_probe` 区分两种错误,只关对应面
  (hermes_state_schema.py:275-290)。

### 2.2 触发器"收窄"迁移

宽触发器 `AFTER UPDATE ON messages` 每次碰行都开销(含状态/压缩写);新 DDL 是
`AFTER UPDATE OF <列>`。但 `CREATE TRIGGER IF NOT EXISTS` **不会替换**既有宽触发器——
于是 `_migrate_broad_fts_update_triggers`(hermes_state_schema.py:95-178)查 sqlite_master、
drop 仍宽的、重放当前 DDL;CJK 触发器失败走隔离(fail-closed:清可用性 + 落 `fts_cjk_stale`
面包屑 + drop 残缺触发器,hermes_state_schema.py:192-215),防"后续 open 用 IF NOT EXISTS
把缺口盖住而不重建"。

### 2.3 v23 FTS 存储重设计:**opt-in,不自动**(hermes_state_schema.py:854-884)

```python
                # OPT-IN, NOT AUTOMATIC. The transition (demote old vtables →
                # new external-content schema → backfill → teardown → VACUUM)
                # is disk-heavy (transient ~2x file size to fully reclaim via
                # VACUUM) and long (~1-2h background on a 25 GB DB).
```

背景数字(同段注释,#22478/#43690/#55233):v11 inline FTS 每表全量私拷贝,trigram 还盖
role='tool' 行(~90% 消息字节)~2.6x 放大——重度用户 **25 GB 库里 18.9 GB 是 FTS**(~75%)。
迁移到 external-content 能砍掉,但过程瞬时 ~2x 磁盘 + 1-2 小时。设计判断:"Doing it silently on
every big user's next open … is the wrong default",于是只落一个 `fts_optimize_available` 标志,
由 `hermes sessions optimize-storage` 作为一次**自愿、检查磁盘、报进度**的前台操作执行。

**解耦版本号**(hermes_state_schema.py:876-882, 894-933):FTS 布局单独用 `fts_storage_version`
标记,主 schema_version 照常推进——否则一个永不 optimize 的用户会卡住所有后续迁移。中断的
optimize(残留 demoted 垃圾表/回搬标记/空外部索引对非空 messages)**不打标**,标记是"完全迁移完成"
的唯一事实源。传统 vs 外部内容 FTS 双布局并存期间,legacy 库只 ensure 旧 DDL、绝不混建 v23 视图
(hermes_state_schema.py:976-999)。

## 3. 可携带性:导出/导入的防御性契约(portability mixin)

### 3.1 导出

- 单会话 = 行 + 全消息(hermes_state_portability.py:266-272);**压缩世系导出**把整条
  compression lineage 拼成一个逻辑会话(segments + 扁平 messages,hermes_state_portability.py:274-292)
  ——压缩在 state 层是"分叉出新会话"的证据(细节归 r5-02/r5-03)。
- 系统提示内容寻址:会话行存 `system_prompt_hash`,读取时
  `LEFT JOIN system_prompts sp ON sp.hash = …`(hermes_state_portability.py:115, 186),
  v25 迁移把旧的每会话内联提示搬进共享表(hermes_state_schema.py:886-892, 39-58)。

### 3.2 导入的六道防线(hermes_state_portability.py:376-714)

1. **强校验**:类型逐字段(文本字段必须 str、model_config 必须 JSON object)、条数/单会话消息数/
   单会话字节/总字节四个上限,任一错则**整批拒绝**(errors 非空直接返回,不做半截导入)。
2. **已存在即跳过**:同 id 不覆盖(hermes_state_portability.py:559-565)。
3. **父边安全**:父会话存在(库里或同批)才连边,否则**脱附**(detached)而不是 FK 失败
   (hermes_state_portability.py:687-702)。
4. **环检测**:`_would_create_cycle` 沿"本批 + 库内"父链走,闭环只丢**闭合边**,保留无环部分
   (hermes_state_portability.py:668-701)。
5. **运行时状态刻意重置**:"Gateway routing, handoff, rewind, and other live runtime state are
   intentionally reset: this restores conversation history, not ownership of a live channel or
   process"(hermes_state_portability.py:382-384)。
6. **活动字段的不对称契约**(#76354,hermes_state_portability.py:386-393):

```python
        Activity contract (#76354 review S4): export INCLUDES the live
        activity fields (``last_activity_at`` / ``last_activity_description``
        / ``last_activity_provenance``) because they are part of the durable
        row, but import deliberately RESETS them to NULL. Resurrecting a
        stale "working ..." label on a machine where no agent is running
        would fabricate activity the watchdog and session listings act on.
        This asymmetry is intentional and covered by regression
        (tests/gateway/test_watchdog_review_76354.py::test_s4_export_includes_activity_import_resets_it).
```

导出带活动戳(它是持久行的一部分),导入清空(别的机器上没有 agent 在跑,复活"working…"标签
会骗过看门狗)。有专门回归测试钉死这条不对称。

### 3.3 读路径的两个工程细节

- **cron 运行列表绕开重 CTE**(hermes_state_portability.py:71-129):cron 会话 id 形如
  `cron_{job}_{ts}`,通用富列表走"从所有 source='cron' 行播种的递归压缩链 CTE + 前导通配 id 查询",
  规模随全库 cron 堆增长,桌面端超时。专用路径用半开区间 `[prefix, prefix_hi)` 做**索引范围扫**
  (`prefix_hi` = 末字节 +1,hermes_state_portability.py:96-101),工作量只随请求窗口走。
- **批量富行取数的 900 变量分块**(hermes_state_portability.py:161-175):老 SQLite
  `SQLITE_MAX_VARIABLE_NUMBER=999`,limit=10000 的调用方存在,IN 列表按 900 分块;上限收敛在
  这个唯一 choke point,不散落调用点。取数前 `flush_token_counts()` 保证 read-your-writes。

## 4. 会话活动契约(session_activity.py)与消息文本拍平(message_content.py)

**session_activity.py**(#72016/#72039)是"活动心跳"的**观测侧契约**:只有时间戳 + 限长描述
(120 字符,session_activity.py:19, 42-47)+ 小闭集 provenance 枚举(UNKNOWN + 三个压缩写者,
session_activity.py:32-39);通知/超时/杀会话策略都不在这里。关键常量
(session_activity.py:21-29 注释 + :29):

```python
SESSION_ACTIVITY_HEARTBEAT_MIN_INTERVAL_SECONDS = 60.0
```

注释写死契约:"MUST stay >= 30s — the SessionDB write path is contended … deliberately a code
constant, independent of any compression.* or agent.* config, so no configuration can turn the
heartbeat into a high-frequency writer"。**心跳频率是代码常量、不给配置**——防任何配置把观测心跳
变成高频写者压垮争用的写路径。唯一旁路是终端戳的 force_persist;`reset_session_activity_persist_window`
(session_activity.py:63-74)给 /compress 后"卡在压缩中标签"的场景强制下一次写穿。

**message_content.py**:`flatten_message_text` 从各种 provider 消息形状(str / parts 列表 /
Responses 对象)拍平出可见文本,图像/音频 part 归空(message_content.py:7-8, 34-50)——
是 FTS 索引与预览的文本源头小工具。

## 5. 重实现要点

1. schema 管理用"声明式调和"(SCHEMA_SQL 唯一真源 + 启动时 PRAGMA diff + ADD COLUMN),
   解析期望列直接用 `:memory:` SQLite 而非正则;版本链只留给数据迁移。
2. 调和表达不了的(PK 变更)写成**每次启动无条件跑的幂等愈合**(rename→rebuild→copy→drop),
   注意 OR IGNORE 不吞 FK 冲突、要开 FK-off 窗口。
3. 大而慢的存储布局迁移做成 **opt-in 显式命令**,用独立布局版本标记与主 schema 版本解耦;
   中断态不打标,标记 = "完全完成"的唯一事实源。
4. 导入外部数据:整批强校验、父边脱附代替 FK 失败、环只剪闭合边、**运行时状态一律重置**
   (导出含、导入清的不对称要有回归测试)。
5. 观测型心跳的写频率用代码常量钉死,不暴露给配置;热点列表查询给专用索引范围扫路径。

## 6. 延伸

hermes_state.py 本体(耐久性防御/多进程/生命周期)见 r5-02;FTS5 检索面见 r5-10;
压缩见 r5-20;prompt 装配见 r5-30;检查点与记忆见 r5-40。
