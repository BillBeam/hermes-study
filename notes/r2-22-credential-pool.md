# R2-22 凭据池与限流护栏(子代理底稿)

> 由子代理精读产出,主线抽查定案(credential-pools.md 5 处不符、nous_rate_guard 未见于文档)。
> 基线 863e31318。范围:credential_pool(3147)、credential_sources(443)、
> credential_persistence(174)、rate_limit_tracker(246)、nous_rate_guard(325)、backend_identity(204)。

# 凭据池与限流护栏 机制簇 L1 精读底稿(R2)

**结论:凭据池是"多凭据状态机 + 按语义分级冷却 + 跨进程 flock 同步"的续命内核。**

- 研究对象:NousResearch/hermes-agent @ `863e31318553cda8ad61df681d08175364d4164b`(已用 `git log -1` 校验)。
- 文件范围与实测行数(`wc -l`):

| 文件 | 实测行数 | 角色 |
|---|---|---|
| `agent/credential_pool.py` | 3147 | 核心:池模型、状态机、选择、冷却、刷新、播种 |
| `agent/credential_sources.py` | 443 | 凭据来源的统一"移除契约"(RemovalStep 注册表) |
| `agent/credential_persistence.py` | 174 | 磁盘边界脱敏:borrowed 凭据只存指纹不存明文 |
| `agent/rate_limit_tracker.py` | 246 | x-ratelimit-* 头解析与 `/usage` 展示 |
| `agent/nous_rate_guard.py` | 325 | Nous RPH 跨会话限流断路器(共享文件) |
| `agent/backend_identity.py` | 204 | 失败作用域三轴模型;本簇只用 credential 轴 |

以下所有断言均附 `路径:行号 @ 863e313` 与逐字摘录。

---

## 1. 池的数据模型与状态机

**问题**:同一 provider 可能有多把 API key / 多个 OAuth 账号,每把 key 有独立的健康状态(可用/限流冷却/永久失效),状态要能持久化到磁盘、被多进程共享,还要携带任意 provider 特有元数据而不炸掉 schema。

**机制**:

三态状态机 `None/ok → exhausted → dead`。`agent/credential_pool.py:68-76 @ 863e313`:

```python
STATUS_OK = "ok"
STATUS_EXHAUSTED = "exhausted"
# Terminal failure — the credential will never recover on its own.  Used for
# upstream-permanent OAuth states like ``token_invalidated`` / ``token_revoked``
```
```python
STATUS_DEAD = "dead"
```

条目本体是 dataclass `PooledCredential`,`agent/credential_pool.py:185-196 @ 863e313`:

```python
@dataclass
class PooledCredential:
    provider: str
    id: str
    label: str
    auth_type: str
    priority: int
    source: str
    access_token: str
    refresh_token: Optional[str] = None
    last_status: Optional[str] = None
    last_status_at: Optional[float] = None
```

状态字段五件套:`last_status / last_status_at / last_error_code / last_error_reason / last_error_message / last_error_reset_at`(196-200);身份字段:`id`(6 位 hex,234:`data.setdefault("id", uuid.uuid4().hex[:6])`)、`source`(来源标签,如 `env:OPENROUTER_API_KEY`、`device_code`、`manual`)、`priority`(排序键)。

Provider 特有元数据不进 dataclass 字段,走 `extra` dict + `__getattr__` 透传,`agent/credential_pool.py:159-171 @ 863e313`:

```python
# Fields that are only round-tripped through JSON — never used for logic as attributes.
_EXTRA_KEYS = frozenset({
    "token_type", "scope", "client_id", "portal_base_url", "obtained_at",
    "expires_in", "agent_key_id", "agent_key_expires_in", "agent_key_reused",
    "agent_key_obtained_at", "tls", "secret_source", "secret_fingerprint",
```

`agent/credential_pool.py:220-223 @ 863e313`:

```python
    def __getattr__(self, name: str):
        if name in _EXTRA_KEYS:
            return self.extra.get(name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute {name!r}")
```

**"持久化 token" ≠ "运行时 key"**:`runtime_api_key` 属性把两者解耦——Nous 的运行时凭据是 `agent_key`(NAS invoke JWT),不是 OAuth access_token,`agent/credential_pool.py:263-270 @ 863e313`:

```python
    @property
    def runtime_api_key(self) -> str:
        if self.provider == "nous":
            # Nous stores the runtime inference credential in agent_key for
            # compatibility. It must be a NAS invoke JWT.
            for token, expires_at in (
                (self.agent_key, self.agent_key_expires_at),
```

进入 DEAD 态的判据:仅限 401 + 已知的 OAuth 永久失效 reason,`agent/credential_pool.py:81-88 @ 863e313`:

```python
_TERMINAL_AUTH_REASONS = frozenset({
    "token_invalidated",   # OpenAI Codex: "Your authentication token has been invalidated."
    "token_revoked",        # OAuth 2.0 RFC 7009: token explicitly revoked
    "invalid_token",        # RFC 6750: bearer token is malformed/expired/revoked
    "invalid_grant",        # RFC 6749: refresh_token rejected during refresh
    "unauthorized_client",  # RFC 6749: client no longer authorized
    "refresh_token_reused", # Single-use refresh token consumed by another process
```

状态迁移点 `_mark_exhausted`,`agent/credential_pool.py:810-813 @ 863e313`:

```python
        if self._is_terminal_auth_failure(status_code, normalized_error):
            terminal_status = STATUS_DEAD
        else:
            terminal_status = STATUS_EXHAUSTED
```

DEAD 的退出方式不是 TTL:manual 来源的 DEAD 条目 24h 后被剪枝(`DEAD_MANUAL_PRUNE_TTL_SECONDS = 24 * 60 * 60`,101 行;剪枝逻辑 1891-1906),singleton 播种的 DEAD 条目只能靠显式重登录的写侧同步清除(`_available_entries` 中 1907-1912 直接 `continue`)。

**为什么**:DEAD 态是被 issue 逼出来的,`agent/credential_pool.py:803-807 @ 863e313`:

```python
        # Permanent OAuth failures (token_invalidated, token_revoked, etc.)
        # transition to STATUS_DEAD instead of STATUS_EXHAUSTED.  Without this,
        # a revoked credential gets a 1-hour TTL cooldown and then re-enters
        # rotation, failing immediately every hour until the user manually
        # removes it (issue #32849).  DEAD entries are excluded from rotation
```

**取舍**:extra dict 牺牲了类型安全换 schema 弹性;三态而非细粒度枚举(如 refreshing/probing)换取磁盘表示简单——瞬时子状态全部落在 reason/error_code 字段上由读取方解释。

**重实现要点**:① 状态机最少三态,DEAD 必须与 EXHAUSTED 区分,退出路径不同(TTL vs 显式重授权);② 条目要有稳定 id(token 会轮换,不能拿 token 当身份);③ "存储 token" 与 "运行时 key" 必须分离成两个访问器。

---

## 2. 轮换与选择算法

**问题**:每次模型调用要从池里选一把可用 key;失败后要精确定位"是哪把 key 失败了"再标记轮换——current 指针是共享可变态,并发轮次/其他进程会把它指向无辜的健康 key。

**机制**:

四种策略,`agent/credential_pool.py:109-118 @ 863e313`:

```python
STRATEGY_FILL_FIRST = "fill_first"
STRATEGY_ROUND_ROBIN = "round_robin"
STRATEGY_RANDOM = "random"
STRATEGY_LEAST_USED = "least_used"
```

策略从 `config.yaml` 的 `credential_pool_strategies.<provider>` 读取,非法值回退 `fill_first`(521-534)。`_select_unlocked` 先算 `_available_entries(clear_expired=True, refresh=True)`(过滤冷却中/DEAD、清除到期冷却、触发 OAuth 刷新),再按策略挑选:random 随机(1995-1998);least_used 取 `request_count` 最小并自增(2000-2006);round_robin 把选中者移到队尾并重写全体 priority 后持久化(2008-2015);fill_first 默认取第一个,`agent/credential_pool.py:2017-2019 @ 863e313`:

```python
        entry = available[0]
        self._current_id = entry.id
        return entry, pending_refresh
```

**失败归因**:`mark_exhausted_and_rotate()` 按 `credential_id` → `api_key_hint` → current 的优先级定位失败条目(2042-2056),归因理由在消费侧写得很清楚,`agent/agent_runtime_helpers.py:988-998 @ 863e313`:

```python
    # Attribute the failure to the API key the agent actually dispatched the
    # request with, not to pool.current(). The current() pointer is shared,
    # mutable state — round-robin select() advances it on every call, and
    # concurrent turns or a second process (gateway/dashboard) reloading the
    # pool reset it to None — so by the time recovery runs it routinely points
    # at a DIFFERENT, healthy entry. Marking that entry exhausted copies this
    # request's error/reset time onto it and can take the whole pool offline
    # from a single rate-limited key (#43747). ``_swap_credential`` keeps
    # ``agent.api_key`` in sync with the entry in use, so it identifies the
    # failing entry exactly; fall back to current()'s key only when the agent
    # carries no key at all.
```

稳定 id 的绑定由 `sync_credential_pool_entry_id`(`agent/agent_runtime_helpers.py:897-913`)在每次换 key 后重算,防 OAuth 刷新导致 api_key 值漂移后归因失败。

**身份匹配不上任何条目时的有界回退(#70401)**:提供了身份但匹配不到条目时,绝不标记任何 key(避免误伤),但轮换次数以"可用条目一圈"为上限,`agent/credential_pool.py:2077-2080 @ 863e313`:

```python
                self._unmatched_rotation_streak += 1
                available_count, _ = self._available_entries()
                available_count = len(available_count)
                if self._unmatched_rotation_streak > max(available_count, 1):
```

超限返回 None 让错误上浮;单条目池直接判定"无处可转"返回 None(2100-2107)。streak 在任何一次真实命中或成功 select 后清零(1774、2111)。

**Sibling 一起标死**:同一 runtime key 可能背着多个池条目(显式条目 + `model_config` 自动播种条目),只标第一个会导致选择器把同一把已耗尽的 key 再递回来、caller 无限 `continue`。`agent/credential_pool.py:2131-2137 @ 863e313`:

```python
            failed_runtime_key = getattr(entry, "runtime_api_key", None)
            if identity_supplied and failed_runtime_key:
                siblings_marked = False
                for sibling in self._entries:
                    if sibling.id == entry.id:
                        continue
                    if sibling.runtime_api_key == failed_runtime_key:
```

**并发租约(delegate 子代理用)**:`acquire_lease()` 优先选租约数低于软上限(`DEFAULT_MAX_CONCURRENT_PER_CREDENTIAL = 1`,575 行)的条目,全部到顶时仍返回最少租约者而非阻塞,`agent/credential_pool.py:2205-2213 @ 863e313`:

```python
            below_cap = [
                entry for entry in available
                if self._active_leases.get(entry.id, 0) < self._max_concurrent
            ]
            candidates = below_cap if below_cap else available
            chosen = min(
                candidates,
                key=lambda entry: (self._active_leases.get(entry.id, 0), entry.priority),
            )
```

**空池日志节流**:池空/全冷却时每次选择都会打 INFO,Windows 上多进程共享轮转日志锁被打爆(`RuntimeError: Cannot acquire lock after 20 attempts`,137-151 行注释,引 #58265 的同类修法),故 60s 窗口内只打一次(`NO_AVAILABLE_ENTRIES_LOG_THROTTLE_SECONDS = 60.0`,151 行;`_log_no_available_entries` 1964-1976;成功选择后重置窗口 1990-1993)。

**为什么**:#70401 的注释解释了无界轮换的实际灾难(`agent/credential_pool.py:2063-2071`:"the caller retries the same dead token forever (~6/sec, starving the event loop so chat interrupts are never processed)")。

**取舍**:归因优先精确性(宁可不标记也不误标);lease 是"软"上限(超载时不阻塞,退化为最少租约),牺牲隔离性换活性。

**重实现要点**:① 失败标记必须带失败方身份(id + key hint),禁止默认标 current;② 身份匹配不上时的轮换必须有界且不写冷却;③ 同 key 多条目要联动标记;④ 热路径上的重复日志要节流并在恢复后重置窗口。

---

## 3. 冷却 TTL 分级(按状态码 + 分类语义)

**问题**:不同失败该冷却多久?401 可能是瞬时鉴权抖动;429 是限流;402 是没钱;403 既可能是边缘节点瞬时限流也可能是花费上限(billing)。单 key 池里一小时的冷却等于一小时硬故障。

**机制**:常量分级,`agent/credential_pool.py:124-132 @ 863e313`:

```python
EXHAUSTED_TTL_401_SECONDS = 5 * 60           # 5 minutes
EXHAUSTED_TTL_429_SECONDS = 60 * 60          # 1 hour
EXHAUSTED_TTL_DEFAULT_SECONDS = 60 * 60      # 1 hour
```
```python
EXHAUSTED_TTL_SOLE_CREDENTIAL_SECONDS = 60   # 1 minute
```

决策函数 `_exhausted_ttl`,`agent/credential_pool.py:332-342 @ 863e313`:

```python
    if error_code == 401:
        return EXHAUSTED_TTL_401_SECONDS
    base = EXHAUSTED_TTL_429_SECONDS if error_code == 429 else EXHAUSTED_TTL_DEFAULT_SECONDS
```
```python
    is_billing = error_code == 402 or failure_reason == FAILURE_REASON_BILLING
    if sole_credential and not is_billing:
        return min(base, EXHAUSTED_TTL_SOLE_CREDENTIAL_SECONDS)
    return base
```

三层覆盖顺序(`_exhausted_until`,423-435):**provider 给的绝对 reset 时间 > TTL 分级**:

```python
    reset_at = _parse_absolute_timestamp(getattr(entry, "last_error_reset_at", None))
    if reset_at is not None:
        return reset_at
```

reset 时间来源有三:错误上下文里的 `reset_at/resets_at/retry_until` 绝对时间戳(408-412,epoch 秒/毫秒/ISO 都收,345-372);报文里的相对延迟正则(`_extract_retry_delay_seconds`,375-395,识别 `quotaResetDelay`、`retry after Ns`、OpenCode Go 周限的 `Resets in 4hr 5min`)。

**failure_reason 为什么要持久化**:HTTP 状态码不足以定级——403 的 billing 和 403 的 edge-throttle 冷却需求相反。分类器(`agent/error_classifier.py`)的裁决以字符串形式随条目写入磁盘,`agent/credential_pool.py:164-171 @ 863e313`(`_EXTRA_KEYS` 内注释):

```python
    # Classified failure semantics for the last exhaustion, as decided by
    # agent/error_classifier.py. The raw HTTP status is not enough to size a
    # cooldown: providers return 403 for both an edge throttle (transient,
    # seconds) and a spending/key limit (billing, needs a real fix). Persisted
    # with the entry so a restart doesn't downgrade a billing bench back to a
    # 60s transient cooldown.
```

sole_credential 判定用"非 DEAD 条目 ≤1"(1831-1833),且 `next_available_at()` 也必须用同一口径(700-702),否则 fallback 回切闸会为 60s 冷却等一小时(697-699 注释)。

**为什么**:`agent/credential_pool.py:127-131` 注释直接给出理由:"a 1-hour bench means an hour of hard failures with nothing to fall back to. Throttles (429/403/5xx) are transient and reset in seconds"。

**取舍**:TTL 是启发式,信任 provider 的 reset_at 优先;billing 永远满冷却(quick retry 无意义);sole-credential 缩短只适用于瞬时类——这是"活性 vs 无谓重试"的双向裁剪。

**重实现要点**:① 冷却 = f(状态码, 分类语义, 池型),三个输入缺一不可;② provider reset 时间要兼容 epoch 秒/毫秒/ISO/相对文案四种格式;③ 分类语义必须随条目持久化,否则重启降级。

---

## 4. 跨进程同步机制

**问题**:CLI、gateway、cron、dashboard、多 profile 会同时读写同一 `auth.json`;OAuth refresh token 是单次使用的;进程 A 的内存快照落盘会覆盖进程 B 刚写的冷却/新条目(lost update)。

**机制**(四层):

**(a) 跨进程 flock**。所有 auth.json 事务走 `_auth_store_lock` → `_file_lock`(每线程可重入、fcntl/msvcrt 双实现),`hermes_cli/auth.py:1157-1161 @ 863e313`:

```python
                if fcntl:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
```

**(b) 写侧合并**。`write_credential_pool` 在锁内重读磁盘:磁盘上有而内存快照没有的条目(别的进程新增的)合并回来,除非在 `removed_ids` 里(有意删除),`hermes_cli/auth.py:1698-1712 @ 863e313`:

```python
        merged: List[Dict[str, Any]] = [
            _merge_disk_cooldown_state(
                entry, existing_by_id.get(entry.get("id")), provider_id
            )
            if isinstance(entry, dict)
            else entry
            for entry in sanitized_entries
        ]
        for disk_entry in existing_list:
```

两侧都有的条目,状态字段按 `last_status_at` 新者胜、且仅当磁盘状态仍有效(DEAD 或未过期的 EXHAUSTED)时才采纳,`hermes_cli/auth.py:1632-1635 @ 863e313`:

```python
        disk_ts = _parse_absolute_timestamp(disk_entry.get("last_status_at")) or 0.0
        mem_ts = _parse_absolute_timestamp(entry.get("last_status_at")) or 0.0
        if disk_ts <= mem_ts:
            return entry
```

token 变化(重授权)则永不复活旧冷却(1628-1631)。

**(c) 选择前从外部真源拉取**。`_available_entries` 对处于 EXHAUSTED/DEAD 的 OAuth 条目,先从其外部真源同步(别的进程可能已刷新):anthropic ← `~/.claude/.credentials.json`(1843-1848)、nous / openai-codex / xai-oauth ← auth.json singleton(1853-1882)。同步成功即清空错误状态并持久化(见 `_sync_codex_entry_from_auth_store` 958-967 的 `field_updates` 全清)。这一步是"另一个进程重登录 → 本进程池条目冻结在 `last_error_reset_at` 后面几个小时"这个 bug 的解药(890-901 docstring)。

**(d) Profile ↔ 全局根双层读写**。读:profile 池空时按 provider 回退读全局根,profile 有任何条目即整体遮蔽(`read_credential_pool`,`hermes_cli/auth.py:1539-1548` docstring,引 #18594);写:refresh 后若 grant 本来解析自全局根,只写回根、绝不给 profile 创建遮蔽键,`agent/credential_pool.py:1194-1201 @ 863e313`(#74339):

```python
                # Fix: use ``_load_provider_state_with_source`` to learn
                # where the state was resolved from.  When the grant was
                # resolved from the global root, write back *only* to root
                # and skip ``_store_provider_state`` for the profile so the
                # profile does not accrue a shadowing ``providers.<id>``
                # key that blocks both the root fallback and the write-through
```

写回全局根的动机(#48415/#43589):`agent/credential_pool.py:583-589 @ 863e313`:

```python
    Best-effort write-through for the multi-profile rotation hazard
    (#48415 / #43589): nous, openai-codex, and xai-oauth rotate the
    refresh_token on refresh, so when a profile pool refresh rotates a grant
    it resolved from the root fallback, the rotated chain must land back in
    root. Otherwise root keeps a now-revoked refresh token and every other
    profile reading the stale root grant dies with ``refresh_token_reused`` /
```

另注意 `_sync_device_code_entry_to_auth_store` 全部走 `set_active=False`(1159-1167 注释):token 轮换是副作用,不允许悄悄翻转用户的 active_provider。

**取舍**:选择的是"乐观快照 + 写时合并"而非"全程持锁"——池的内存操作只持线程锁,磁盘冲突推迟到 write 时按时间戳裁决;代价是需要 `removed_ids` 显式协议防止删除被合并复活。

**重实现要点**:① 单次使用 refresh token 的世界里,"落盘的最后写入者"必须是持有最新链的那个,write-through 到共享真源不可省;② lost-update 合并要区分"新增条目"与"状态字段",后者按时间戳 + 有效性裁决;③ 有意删除要显式传 tombstone(removed_ids)。

---

## 5. OAuth 池与刷新

**问题**:OAuth access token 会过期,refresh token 是单次使用;刷新是网络 I/O + 跨进程锁(可阻塞 20s+),不能在池的线程锁内做;refresh token 被别的进程消耗后重放会触发 `refresh_token_reused` 级联撤销。

**机制**:

**主动刷新判定** `_entry_needs_refresh`(1745-1767):anthropic 按 `expires_at_ms` 提前 120s;codex/xai 按 JWT 声明加 skew;nous 显式不在枚举时刷新(1762-1766 注释:"Nous refresh can require network access and should happen when runtime credentials are actually resolved, not merely when the pool is enumerated")。

**Deferred refresh(锁外刷新)**:单次使用 token 的 provider(codex/xai)在 `_available_entries` 里不当场刷,收集成 `pending_refresh` 返回,`agent/credential_pool.py:1941-1944 @ 863e313`:

```python
            if refresh and self._entry_needs_refresh(entry):
                if self.provider in ("openai-codex", "xai-oauth"):
                    # Defer single-use-token refresh to avoid holding the
                    # threading lock during cross-process flock + network I/O.
```

`select()` 在锁外执行这些刷新,然后**重选一次**(1769-1782);`acquire_lease()` 同样(2178-2189)。这就是 `self._lock` 用 RLock 的原因(639-644 注释):锁外刷新路径调用的 `_replace_entry/_persist` 自己拿锁,锁内调用者可重入。

**单次使用 token 的原子刷新序列**:sync→POST→write-back 整段裹在跨进程 flock 里,超时按刷新 POST 超时 + 余量放大(`_single_use_refresh_lock_timeout`,1329-1346),`agent/credential_pool.py:1296-1305 @ 863e313`:

```python
        # Codex and xAI OAuth refresh tokens are single-use.  The
        # sync→POST→write-back sequence below must run atomically across Hermes
        # processes: otherwise two processes can both adopt the same on-disk
        # token, both POST it, and the loser gets ``refresh_token_reused``.
```

等锁的进程拿到锁后先在锁内重同步,发现赢家已轮换就直接采纳、跳过 POST(1321-1326)。

**刷新失败的三级处理**(`_refresh_entry_impl` 的 except 块,1425-1689):① 重同步真源,若 refresh_token 已变说明输给了并发方 → 采纳新链并清状态返回(xai 1473-1490、codex 1548-1565、nous 1622-1638、anthropic 走 credentials 文件重试一次 1430-1466);② 判定为终态刷新错误(`_is_terminal_*_refresh_error`)→ **隔离(quarantine)**:清掉 auth.json 里的 token、写入 `last_auth_error{relogin_required: True}`、把所有 singleton 播种条目从池中移除并以 `removed_ids` 落盘(xai 1496-1543、codex 1571-1618、nous 1639-1687);③ 其余 → `_mark_exhausted(entry, None)`(1688)。清 auth.json 前有比对护栏:只有 store 里的 refresh_token 为空或与本条目一致才清(1507-1509),防止把别人刚写的新链清掉。

**Codex 配额提前恢复探测(#43747)**:Codex 429 的 `last_error_reset_at` 可以在几天后(周窗口),但用户可能提前解锁;选择路径上对 429 形错误做节流的活探测,命中则解除冻结,`agent/credential_pool.py:1711-1717 @ 863e313`:

```python
        A Codex 429 persists a ``last_error_reset_at`` that can be days in
        the future (weekly windows), but the upstream window can reopen
        before then — the user redeems a banked rate-limit reset via the
        Codex CLI / ChatGPT UI, upgrades their plan, or OpenAI resets the
        window.  Without this check the pool keeps the credential frozen
        until the stale timestamp elapses even though the account is
        usable (issue #43747).
```

调用点在 `_available_entries` 冷却未到期的分支里(1923-1927),仅 `clear_expired=True` 时触发。

**取舍**:锁外刷新引入了"刷新窗口内条目可能被并发轮换"的复杂度(靠 RLock + 自锁原语 + 显式加锁的 quarantine 段兜住),换来的是池消费者不被 20s+ 的 flock/网络阻塞;终态 quarantine 宁可删条目也不留下会被 `_seed_from_singletons` 无限复活的死状态。

**重实现要点**:① 单次使用 refresh token 的刷新必须"跨进程锁内:先采纳-后消费";② 刷新失败先怀疑"输给并发方",再怀疑"终态",最后才标 exhausted;③ 终态处理要同时清池和清真源,且用 tombstone 防复活;④ provider 声称的 reset 时间要允许被活探测证伪。

---

## 6. 凭据来源解析与持久化

**问题**:凭据散落在 env、`~/.hermes/.env`、auth.json singleton、`~/.claude/.credentials.json`、`~/.qwen/oauth_creds.json`、`gh auth token`、config.yaml 等九种来源;池要自动发现它们,但用户删除一个凭据后不能被下次加载"复活";借来的秘密不能明文落盘。

**机制**:

**加载管道** `load_pool(provider)`(3084-3147):读磁盘 → 检查是否需要脱敏/auth_type 归一 → `custom:*` 池走 `_seed_custom_pool`(config 的 `api_key` + `model.api_key`,3011-3081),其余走 `_seed_from_singletons` + `_seed_from_env` → 剪枝失效播种条目 → anthropic 归一 priority(`_normalize_pool_priorities` 按 source_rank 排序,2423-2429)→ 有变化才写盘(带 `removed_ids`)。

**Env 播种偏好 .env**:`get_env_prefer_dotenv`(2830-2846)以 `~/.hermes/.env` 为权威、os.environ 兜底,并处理未解析的 `op://` 引用;理由:2824-2827 注释("Stale env vars from parent processes (Codex CLI, test scripts, etc.) should not override deliberate changes to the .env file")。

**非破坏性读(#9331)**:进程 A 没有某 env var 不能删掉别的进程还在用的磁盘条目——`load_pool` 剪枝时 env 来源不剪,`agent/credential_pool.py:3129-3137 @ 863e313`:

```python
        # ``load_pool()`` is a non-destructive read for env-seeded entries: a
        # process missing a provider env var must not delete the persisted
        # pool entry for every other process (#9331). File-backed singletons
        # still prune when their backing file is gone.
        changed |= _prune_stale_seeded_entries(
            entries,
            singleton_sources | env_sources,
            prune_env_sources=False,
        )
```

**Upsert 语义**:同 source 条目就地更新、去重;token 变化即清空旧错误状态(2398-2406:"When the credential token itself changes (key rotation), clear any exhaustion/error state — the old status is stale for the new key")。

**Suppression(移除的粘性)**:`hermes auth remove` 后,`(provider, source)` 写入 auth.json 的 `suppressed_sources`(`hermes_cli/auth.py:1717-1725`),每个 `_seed_from_*` 分支在 upsert 前查 `is_source_suppressed` 跳过——否则移除会在下次 `load_pool()` 被无声撤销。移除的外部清理由 `credential_sources.py` 的 RemovalStep 注册表统一,`agent/credential_sources.py:27-36 @ 863e313`:

```python
Now every source registers a ``RemovalStep`` that does exactly three things
in the same shape:

    1. Clean up whatever externally-readable state the source reads from
       (.env line, auth.json block, OAuth file, etc.)
    2. Suppress the ``(provider, source_id)`` in auth.json so the
       corresponding ``_seed_from_*`` branch skips the upsert on re-load
```

注册顺序即匹配优先级(first match),copilot 的 `env:*` 必须排在通用 env 步骤之前(378-386:"ORDER MATTERS...")。所有权决定清理方式:自有文件删(`hermes_pkce` 219 行 `oauth_file.unlink()`)、他人文件只 suppress 不删(claude_code 194-204、qwen-cli 322-332、Codex CLI 的 `~/.codex/auth.json` 288-303)。

**播种的用户同意护栏**:anthropic 只有被显式配置为 provider 时才自动发现外部 OAuth(2466-2476,引 PR #4210:"Without this gate, auxiliary client fallback chains silently read ~/.claude/.credentials.json without user consent");且用户在 setup 选了 API-key 路线(有 `ANTHROPIC_API_KEY` 且无 OAuth env)时,**禁止**播种 OAuth 并主动剪掉历史 OAuth 条目,`agent/credential_pool.py:2486-2492 @ 863e313`:

```python
        # into the anthropic pool — otherwise rotation on a 401/429 silently
        # flips the session onto an OAuth credential, which forces the Claude
        # Code identity injection, `mcp_` tool-name rewrite, and claude-cli
        # User-Agent header (`agent/anthropic_adapter.py:2128`).  Users who
        # explicitly opted into the API-key path are explicitly opting OUT of
        # that masquerade.  Prefer ~/.hermes/.env over os.environ for the
```

**磁盘边界脱敏**(`credential_persistence.py`):白名单之外的一切非 manual 来源视为 borrowed,`agent/credential_persistence.py:20-26 @ 863e313`:

```python
_PERSISTABLE_PROVIDER_SOURCES = frozenset({
    ("anthropic", "hermes_pkce"),
    ("minimax-oauth", "oauth"),
    ("nous", "device_code"),
    ("openai-codex", "device_code"),
    ("xai-oauth", "device_code"),
})
```

borrowed 条目落盘时剥掉所有秘密值字段(键名匹配 `_SECRET_VALUE_KEYS` + 后缀表,含 camelCase 归一),只留元数据 + SHA-256 前 16 位指纹(`sanitize_borrowed_credential_payload`,151-174)。脱敏在两处执行:`PooledCredential.to_dict()`(261)和最终写边界 `write_credential_pool`(hermes_cli/auth.py:1681-1685)——双保险,因为 caller 可能传裸 dict。运行时侧,未 hydrate 的空 key 条目永不被选中(`agent/credential_pool.py:1838-1839`:`if entry.auth_type == AUTH_TYPE_API_KEY and not entry.runtime_api_key: continue`)。

**取舍**:"播种是幂等 upsert + suppression 门"的组合把"自动发现"与"用户移除意志"这对矛盾拆开;脱敏采用默认拒绝(fail closed)的白名单——新来源不改白名单就自动只存指纹。

**重实现要点**:① 每个来源三件套:reader 分支、suppression 门、RemovalStep,缺一个移除就会回魂;② load 必须是对共享状态的非破坏性读;③ 磁盘边界脱敏要在最终写入点强制执行而不能只信上游;④ 借来的秘密存指纹以便变更检测,不存明文。

---

## 7. RPH 跨会话限流护栏(nous_rate_guard + rate_limit_tracker)

**问题**:`agent/nous_rate_guard.py:7-10 @ 863e313`:

```python
Each 429 from Nous triggers up to 9 API calls per conversation turn
(3 SDK retries x 3 Hermes retries), and every one of those calls counts
against RPH.  By recording the rate limit state on first 429 and checking
it before subsequent attempts, we eliminate the amplification effect.
```

多会话(CLI/gateway/cron/auxiliary)并发时每个会话都独立放大。

**机制**(共享文件断路器,三个动词):

- **record**:429 时把 reset 时间写入 `$HERMES_HOME/rate_limits/nous.json`(`_state_path`,29-36),reset 解析优先级 `x-ratelimit-reset-requests-1h` > `x-ratelimit-reset-requests` > `retry-after`(54-58),都没有则 error_context 的 reset_at,再没有默认 300s(97-104)。原子写:mkstemp + `atomic_replace`(118-122)。
- **check**:每次 Nous 请求前读文件,`nous_rate_limit_remaining()` 返回剩余秒或 None;过期即读即删(147-158)。
- **clear**:任一会话成功请求后删除文件(163-170)。

**真假限流判别** `is_genuine_nous_rate_limit`(192-244):Nous Portal 是多上游聚合器,429 有两种含义,`agent/nous_rate_guard.py:202-212 @ 863e313`:

```python
      (a) The caller's own RPM / RPH / TPM / TPH bucket on Nous is
          exhausted — a genuine rate limit that will last until the
          bucket resets.
      (b) The upstream provider is out of capacity for a specific model
          — transient, clears in seconds, and has nothing to do with
          the caller's quota on Nous.
```

判据两路:429 响应自身 headers 里有 `remaining == 0` 且 reset ≥ 60s 的桶(`_MIN_RESET_FOR_BREAKER_SECONDS = 60.0`,189 行;`_has_exhausted_bucket` 286-297);或上一次成功响应捕获的 last-known-good 状态里已有耗尽桶(300-325)。两路都不命中 → 判为上游容量问题,不 trip 断路器。

**rate_limit_tracker 的角色**:纯解析/展示层。12 个 `x-ratelimit-*` 头(agent/rate_limit_tracker.py:8-21 schema 注释)解析成 `RateLimitState`(四桶:requests/tokens × min/hour),`RateLimitBucket.remaining_seconds_now` 按捕获时刻校正(50-53)。捕获点:流式响应建立时 `agent/chat_completion_helpers.py:3106-3109 @ 863e313`:

```python
        def _stream_created(raw_stream: Any) -> None:
            response = getattr(raw_stream, "response", None)
            agent._capture_rate_limits(response)
            agent._capture_credits(response)
```

存到 `agent._rate_limit_state`(`run_agent.py:3791-3806`),供 `/usage`(cli.py:11394、gateway/slash_commands.py:5053 经 `format_rate_limit_display`)和上面的判真第二信号使用。

**消费闭环**(conversation_loop 三处):

请求前守卫,`agent/conversation_loop.py:2147-2154 @ 863e313`:

```python
            if agent.provider == "nous":
                try:
                    from agent.nous_rate_guard import (
                        nous_rate_limit_remaining,
                        format_remaining as _fmt_nous_remaining,
                    )
                    _nous_remaining = nous_rate_limit_remaining()
                    if _nous_remaining is not None and _nous_remaining > 0:
```

命中则跳过 API 调用直接尝试 fallback,无 fallback 则带 reset 时间失败返回(2163-2186)。

429 记录(仅当池未恢复且判真),`agent/conversation_loop.py:4564-4569 @ 863e313`:

```python
                        _genuine_nous_rate_limit = is_genuine_nous_rate_limit(
                            headers=_err_hdrs,
                            last_known_state=agent._rate_limit_state,
                        )
                        if _genuine_nous_rate_limit:
                            record_nous_rate_limit(
```

判真后设 `retry_count = max(0, max_retries - 1)` 精确再入循环一次,让顶部守卫统一走 fallback/bail(4582-4590 注释解释了为何不直接置满)。

成功清除,`agent/conversation_loop.py:3468-3471 @ 863e313`:

```python
                if agent.provider == "nous":
                    try:
                        from agent.nous_rate_guard import clear_nous_rate_limit
                        clear_nous_rate_limit()
```

**取舍**:断路器状态放文件而非池条目——因为要跨"会话"而不只是跨"进程内的池实例",且 Nous 一个账号对应整个 provider(池轮换帮不上);60s 阈值牺牲了对短限流的防护,换取聚合器上游抖动不误伤全部模型(注释 210-213 记载了 DeepSeek 429 连坐 Kimi/MiMo 的真实 bug)。所有守卫代码 fail-open(`except Exception: pass`),护栏永不反噬主循环。

**重实现要点**:① 跨会话断路器 = 共享文件 + 原子写 + 读时过期清理 + 成功即清;② trip 之前必须判真:自证(本次 429 headers)或旁证(上次成功的桶状态);③ 聚合器的 429 语义是双关的,断路器阈值要区分账号级与上游级。

---

## 8. backend_identity:credential surface 轴(凭据相关部分)

**问题**:一次 401/402 到底"杀死"了什么?跳过候选的判断曾在六个调用点各写一套字符串比较,每修一处漏五处(模块头 7-12 列了 #22548/#70893/#59561/#72468/#62984 等六个事故)。

**机制**:失败作用域三轴枚举,凭据轴定义 `agent/backend_identity.py:48-51 @ 863e313`:

```python
    #: Auth 401 / payment 402: evidence against the shared credential —
    #: every model reached with it is equally dead.
    CREDENTIAL = "credential"
```

reason → scope 映射:`"auth error"` 与 `"payment error"` 归 CREDENTIAL,未知 reason 默认 MODEL(最小失效轴,58-67)。凭据同面判定 `same_credential_surface`,`agent/backend_identity.py:142-149 @ 863e313`:

```python
    if a.provider and b.provider:
        # Same label = same configured credential. Different labels =
        # different credential config (first-class registry providers
        # explicitly so — #70893; custom entries can each carry their own
        # api_key, so sameness is unprovable and we must not skip).
        return a.provider == b.provider
    # Provider unknown on a side: same explicit URL is the best signal left.
    return bool(a.base_url and a.base_url == b.base_url)
```

关键校准(#70893):`xai-oauth` 与 `xai` 同 host 不同凭据面——两个注册表一等 provider 即使共享推理端点也算不同凭据(`_both_first_class`,114-129)。docstring 明示保守方向(132-141):不可证的轴回答"different"(多试一次浪费一个 RTT)优于回答"same"(误跳过导致 failover 搁浅)。与本簇的关系:凭据池管"同 provider 内哪把 key",backend_identity 管"跨候选时这次失败是否杀死了整个凭据面"——auxiliary fallback 链和 fallback 去重经 `should_skip_candidate(scope=CREDENTIAL)` 消费它。

**重实现要点**:失败分类和身份比较要收敛到单一模块;凭据面比较的默认答案必须偏向"不同"(可恢复的浪费 > 不可恢复的搁浅)。

---

## 9. 边界交互:池如何被消费

**注入链**:启动时 `hermes_cli/runtime_provider.py:1866-1871 @ 863e313` 建池并首选:

```python
    try:
        pool = load_pool(provider) if should_use_pool else None
    except Exception:
        pool = None
    if pool and pool.has_credentials():
        entry = pool.select()
```

池经构造参数进入 agent(`agent/agent_init.py:625`:`agent._credential_pool = credential_pool`),并在 provider 自动探测**之后**做归属校验、不匹配即卸下(`agent/agent_init.py:673-684`,经 `credential_pool_matches_provider`;#63048→#63425 的顺序回归修复)。

**错误恢复主路**:内层重试循环捕获 API 错误分类后调用,`agent/conversation_loop.py:3861-3866 @ 863e313`:

```python
                recovered_with_pool, _retry.has_retried_429 = agent._recover_with_credential_pool(
                    status_code=status_code,
                    has_retried_429=_retry.has_retried_429,
                    classified_reason=classified.reason,
                    error_context=error_context,
                )
```

转发到 `run_agent.py:5953-5963` 再到实现 `agent/agent_runtime_helpers.py:916-1244`。策略矩阵:`upstream_rate_limit` 完全不动池(1041-1058);`billing` 立即轮换(1060-1074);`rate_limit` 首次 429 只置 `has_retried_429=True` 重试同 key、第二次才轮换(1124-1127),但条目已是 EXHAUSTED 或报文含 `usage_limit_reached` 时跳过重试直接轮换(1097/1114-1123);`auth` 先判 entitlement 型 403 跳过刷新(1160-1194),否则 `try_refresh_matching` 定向刷新失败方(1195-1202),同条目连刷超限(#26080)放行 fallback(1211-1227),刷新失败则轮换(1231-1242)。`has_retried_429` 在成功后复位(`agent/conversation_loop.py:3459`:`_retry.has_retried_429 = False  # Reset on success`)。恢复前有 provider 失配护栏(#33088/#33163)与 custom:`<name>` 双命名豁免(agent/agent_runtime_helpers.py:942-986)。

**换 key 的落地**:`_swap_credential`(`run_agent.py:5883-5917`)把 entry 的 runtime key/base_url 写回 agent、重建 OpenAI/Anthropic client、重算路由级 TLS/headers。

**与 fallback 链的先后**:429 时若池可能恢复则不急着 fallback,判据是"池有可用条目**且**条目数 > 1",`run_agent.py:328-332 @ 863e313`:

```python
    if pool is None:
        return False
    if not pool.has_available():
        return False
    return len(pool.entries()) > 1
```

(#11314/#13636:单 key 池 429 后无处可转,等冷却=烧光重试预算,应立刻 fallback。)调用点 `agent/conversation_loop.py:4461-4467`。fallback 换 provider 时卸下主池、装上 fallback provider 自己的池(`agent/chat_completion_helpers.py:1943-1960`,#33163),随后 `sync_credential_pool_entry_id(agent)`(2016-2017)。

**Delegate 子代理**:`tools/delegate_tool.py:1995-2003 @ 863e313`:

```python
    child_pool = getattr(child, "_credential_pool", None)
    leased_cred_id = None
    if child_pool is not None:
        leased_cred_id = child_pool.acquire_lease()
        if leased_cred_id is not None:
            try:
                leased_entry = child_pool.current()
                if leased_entry is not None and hasattr(child, "_swap_credential"):
                    child._swap_credential(leased_entry)
```

结束时 `release_lease`(2578)。子池构建在 tools/delegate_tool.py:3469/3486。

**其它消费者**(结构级):agent/auxiliary_client.py:1043/1059/2148/2243/4225/4460(副 LLM 任务)、agent/account_usage.py:503(`/usage` 账户额度)、agent/anthropic_adapter.py:1332、cron/scheduler.py:3492、hermes_cli/nous_auth_keepalive.py:59、hermes_cli/proxy/adapters/xai.py:111-113(订阅代理按请求建池)、tools/xai_http.py:280、hermes_cli/auth_commands.py:178 起(CLI 管理面)。

---

## 10. 定案:第一轮两条悬案

### 10.1 ▲「凭据池条目存在文档不符」→ **证实,并落实为 5 处具体不符 + 3 处文档正确性确认**

文档:`website/docs/user-guide/features/credential-pools.md`。

**不符 ①(方法不存在)**:文档 Thread Safety 节列举 `mark_used()`,`website/docs/user-guide/features/credential-pools.md:209 @ 863e313`:

```
The credential pool uses a threading lock for all state mutations (`select()`, `mark_exhausted_and_rotate()`, `try_refresh_current()`, `mark_used()`). This ensures safe concurrent access when the gateway handles multiple chat sessions simultaneously.
```

代码里全仓 `grep mark_used` 零命中(`Grep pattern=mark_used glob=*.py` → No matches)。该方法不存在;`request_count` 自增实际发生在 least_used 策略的 `_select_unlocked` 里(agent/credential_pool.py:2000-2006)。**证伪文档**。

**不符 ②(env 剪枝语义已反转)**:`website/docs/user-guide/features/credential-pools.md:193 @ 863e313`:

```
Auto-seeded entries are updated on each pool load — if you remove an env var, its pool entry is automatically pruned. Manual entries (added via `hermes auth add`) are never auto-pruned.
```

代码自 #9331 起 `load_pool` 显式**不**剪 env 条目(agent/credential_pool.py:3129-3137,`prune_env_sources=False`,摘录见 §6)。env 条目只在 `hermes auth` 命令确认来源消失时才剪。**证伪文档**(文档描述的是 #9331 之前的旧行为)。

**不符 ③(冷却表不完整/被代码超越)**:`credential-pools.md:143-145` 的表格给 429→1h、402→1h、401→5min。基线 TTL 与代码常量一致(agent/credential_pool.py:124-126),但代码还有三层文档未提的行为:sole-credential 60s 短冷却(132 行)、`failure_reason=billing` 覆盖状态码(332-342)、终态 401 进 DEAD 而非任何 TTL(810-813)。**文档部分过时/不完整**。

**不符 ④("池先于 fallback"有单 key 例外)**:`credential-pools.md:12` 称 "Pools are tried first — if all pool keys are exhausted, *then* the fallback provider activates";代码在单条目池 429 时直接 fallback、不等冷却(`run_agent.py:328-332`,`return len(pool.entries()) > 1`,#11314)。**文档缺关键例外**。

**不符 ⑤(引用的架构图不在仓库)**:`credential-pools.md:213` 称 "see [`docs/credential-pool-flow.excalidraw`](…) in the repository";`find docs -iname '*credential*' -o -iname '*pool*'` 与全仓 `*excalidraw*` 检索均无此文件。**文档指向不存在的仓内文件**(外链 excalidraw.com 或仍有效,未验证网络资源)。

**同时确认文档正确的部分**(避免过度证伪):429 先重试一次再轮换 + usage-limit 立即轮换与 `agent/agent_runtime_helpers.py:1114-1126` 一致;`reset_at` 覆盖默认冷却与 `agent/credential_pool.py:426-428` 一致;borrowed 凭据只存指纹的 Storage 说明(credential-pools.md:195、257)与 `credential_persistence.py` 完全一致——这一段文档甚至比多数段落更新。

**结论:▲ 成立。credential-pools.md 主干正确,但含 1 处虚构 API、1 处已反转语义、1 处失效文件引用,冷却/fallback 语义落后于 #9331/#11314/#32849 之后的代码。以代码为准。**

### 10.2 ◇「nous_rate_guard 未见于文档」→ **证实**

- `website/docs` 全树 `grep -i "nous.json|rate_limits/|rate guard|amplification"` 唯一命中是无关的 updating.md;`grep -i "credential"` 命中的 195 个文件里没有任何一个描述跨会话限流断路器;`nous-portal.md` 对 429/RPH/rate limit 仅有一处无关表格行(nous-portal.md:57)。
- `AGENTS.md` 中 `credential|rate` 相关命中仅两类:AIAgent 构造参数列表里的 `credential_pool=None`(AGENTS.md:337)和一句 PR 分类示例(158 行 "a rate-limit 're-probe during cooldown' PR"),均非机制描述。
- 与之最接近的用户可见面是 `/usage` 命令(slash-commands.md:127/241 描述 account limits 展示),但那是 `rate_limit_tracker` + `account_usage` 的展示层,不是 `nous_rate_guard` 的断路器。

**结论:◇ 成立。`agent/nous_rate_guard.py`(325 行)及其共享文件 `$HERMES_HOME/rate_limits/nous.json`、真假限流判别、请求前守卫三件套在 website/docs 与 AGENTS.md 中零记载,属"代码有、地图无"的暗机制;其行为规格只存在于源码注释与 `tests/agent/test_nous_rate_guard.py`。**

---

## 11. 测试地图与 3 个行为规格

本簇对应测试(`find tests -name '*credential*' -o -name '*rate*'` 等,列主干):

| 测试文件 | 行数 | 覆盖 |
|---|---|---|
| `tests/agent/test_credential_pool.py` | 2026 | 主行为规格:reset_at 覆盖、sibling 联动标记、DEAD 生命周期、播种/剪枝/脱敏、策略 |
| `tests/agent/test_credential_pool_routing.py` | 545 | 429 轮换全周期 + 归因 + eager-fallback 门 |
| `tests/agent/test_credential_pool_sole_cooldown.py` | 163 | 单 key 池 60s 冷却 vs billing 满冷却 |
| `tests/agent/test_credential_pool_unmatched_rotation_bound.py` | 110 | #70401 有界回退 |
| `tests/agent/test_credential_pool_oauth_writethrough.py` | 319 | profile→root 写穿 |
| `tests/agent/test_credential_pool_deferred_refresh.py` / `_lease_refresh_reselect.py` / `_key_rotation.py` / `_no_entries_log_throttle.py` / `_oat_authtype.py` / `_provider_boundary.py` / `_quarantine_locking.py` | 93-136 | 各专项回归 |
| `tests/agent/test_nous_rate_guard.py` | 284 | 断路器 record/check/clear/判真 |
| `tests/agent/test_rate_limit_tracker.py` | 131 | 头解析/格式化 |
| `tests/agent/test_backend_identity.py` | 139 | 三轴判定 |
| `tests/run_agent/test_fallback_credential_isolation.py` / `test_credential_pool_interrupt.py` / `test_63425_credential_pool_auto_detect.py` | — | 消费侧边界(#33088/#33163/#63425) |

**最像行为规格的 3 个**:

1. **`tests/agent/test_credential_pool_sole_cooldown.py`(163 行)**——把 §3 的冷却矩阵写成了可执行规格:单 key 429/403 在 90s 后 `select()` 必须返回且状态清为 `"ok"`(test_sole_credential_429_recovers_after_short_cooldown,59-71);403+`failure_reason="billing"` 必须 `has_available() is False`(81-96),且 `_exhausted_ttl(403, sole_credential=True, failure_reason="billing") == 60*60` 而无分类时 `== 60`(115-116);402 保持满冷却(119-124);`next_available_at()` 也要按 60s 口径报告(127-148);两个非 DEAD 条目时短冷却失效、双双保持 benched(151-163)。断言直达"冷却=f(状态码,语义,池型)"的全部分支。

2. **`tests/agent/test_credential_pool_unmatched_rotation_bound.py`(110 行)**——#70401 的完整规格:三条目池收到匹配不上任何条目的 401 hint,10 轮 caller 重试内必须收到 None(≤ 一圈即 ≤4 次),且事后 `all(status != "exhausted")`——一把无辜 key 都不许被写冷却(52-87);对照组证明正常匹配路径不受影响:cred-1 被标 exhausted、返回健康的 cred-0(91-110)。这是"归因失败时既要有界又不许误伤"这条双重不变量的最小完备表述。

3. **`tests/agent/test_credential_pool_routing.py`(545 行)**——§9 消费协议的规格:CLI/gateway 的 turn 路由必须把 `credential_pool` 传进 runtime dict(24-79);429 且池有可用凭据时 eager fallback 不得触发,无池/池尽时必须触发(109-147);429 全周期——首个 429 只置 `has_retried_429=True` 不轮换(195-203)、第二个 429 轮换并断言 `mark_exhausted_and_rotate` 收到 `api_key_hint` 与 `failure_reason="rate_limit"`(205-214)、402 立即轮换带 `failure_reason="billing"`(231-239)、agent.api_key 缺失时 hint 回退到 `pool.current().runtime_api_key`(242-278);末段用**真实** CredentialPool 验证 #43747:失败 key ≠ current 时只有失败条目被标 exhausted(285 起)。

---

## 附:机制间关系速览(供讲解用)

```
请求前   nous_rate_guard.check ──(Nous 已限流?)──▶ 跳过调用→fallback/bail
选择     load_pool(播种/剪枝/脱敏) → select(策略) → _available_entries(冷却过滤+跨进程同步+deferred OAuth 刷新)
调用后   rate_limit_tracker.capture(x-ratelimit-*) → agent._rate_limit_state
失败     error_classifier → recover_with_credential_pool
           ├─ upstream_rate_limit → 不动池,fallback 链
           ├─ billing → 立即 mark_exhausted_and_rotate(+sibling 联动)
           ├─ rate_limit → 重试一次→轮换;Nous 判真→写跨会话断路器
           └─ auth → entitlement 门→定向刷新(单次 token 原子序列)→失败轮换/终态 quarantine
落盘     write_credential_pool(flock + lost-update 合并 + tombstone + borrowed 脱敏)
全池尽   _pool_may_recover_from_rate_limit=False → fallback 链(backend_identity 判凭据面去重)
```
