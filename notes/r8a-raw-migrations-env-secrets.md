# R8A 底稿 · 配置面的时间维度与边界维度

> 对象:`hermes_cli/config_migrations.py`(685)、`hermes_cli/env_loader.py`(752)、
> `hermes_cli/secret_prompt.py`(126)、`hermes_cli/fallback_config.py`(101)、
> `hermes_cli/skills_config.py`(202)。基线 `863e31318553cda8ad61df681d08175364d4164b`。
> 本文件是**证据层**:凡断言必带 `路径:行号 @ 863e313` + 原文块。求全不求好读。
>
> **本轮两处「任务书假设与代码不符」先行声明**(下文各节展开取证):
> 1. `fallback_config.py` **不是**「配置读不出来时兜什么底」,它是 **LLM provider 失败转移链**
>    (primary 429/503 时换哪个 provider/model)。真正的「配置读不出来兜底」是
>    `hermes_cli/config.py` 里的 last-known-good + `.corrupt.<ts>.bak` 两件套,与本文件**零调用关系**。
> 2. `skills_config.py` **不是**「skill 自带配置的 schema」,它是 `hermes skills` 这个
>    **交互式开关菜单**(禁用哪些 skill)。skill 自带配置的 schema
>    (`metadata.hermes.config`)在 `agent/skill_utils.py`。

---

## 0. 一页结论

| 文件 | 真实职责 | 最值得记的一件事 |
|---|---|---|
| `config_migrations.py` | 版本化 schema 迁移表 + 驱动 | 13 条迁移里 **至少 2 条(v15、v23)写了等于默认值的内容,被 `_persist_migration` 的 strip_defaults 全量剥掉,磁盘上什么都没留下,但仍向用户报告"已添加"**(§1.6,已实测) |
| `env_loader.py` | `.env` → `os.environ` 的唯一正规入口 | 覆盖顺序是 `shell < 用户 .env < 项目 .env(仅补空) < 外部密钥源 < managed .env`,**managed 故意反转了 env-over-config 的常规优先级**;`.op.env` 是唯一不覆盖的一档 |
| `secret_prompt.py` | 带掩码回显的密钥输入 | **POSIX 分支只吞掉 ESC 字节本身,方向键的 `[A` 会被吞进密钥**(§3.4,已实测);Windows 分支反而是对的 |
| `fallback_config.py` | provider 失败转移链的读取器 | `key_env` 走 `agent.secret_scope.get_secret` 而非裸 `os.getenv`,这是多路复用网关下的跨 profile 凭据隔离点 |
| `skills_config.py` | `hermes skills` 开关菜单 | 与 `agent/skill_utils.py` 是**同语义的两份实现**,且**配置来源不同**(`load_config()` vs 裸 YAML),导致 managed 层对 `skills.disabled` 只对菜单生效、对运行时不生效(§6.2) |

---

## 1. `hermes_cli/config_migrations.py` —— schema 的时间维度

### 1.1 模块定位:从 768 行 if 阶梯改成表驱动

模块 docstring 自陈:它是从 `hermes_cli.config.migrate_config` 里一个 768 行的
`if current_ver < N:` 阶梯抽出来的,**每个 step 的函数体是逐字复制**,只有版本闸门和严格升序
这层骨架进了 `run_migrations` 驱动。

`hermes_cli/config_migrations.py:1 @ 863e313`

```python
"""Table-driven config migration registry.

This module holds the per-version migration steps that used to live as a
768-line ladder of ``if current_ver < N:`` blocks inside
``hermes_cli.config.migrate_config``. Each step is a function
``_migrate_to_N(results, quiet)`` whose body is copied verbatim from the
original block; only the shared skeleton (the version gate and the strict
ascending ordering) lives in the :func:`run_migrations` driver.
```

### 1.2 环依赖规避:`_cfg()` 延迟解析

本模块**故意没有** module-level 的 `import hermes_cli.config`。每个 step 在**调用时**通过
`_cfg()` 拿到活的模块对象再取 `read_raw_config` / `_persist_migration` 等。两个理由:
(a) 断环;(b) 让 `patch("hermes_cli.config.read_raw_config", ...)` 这类测试 monkeypatch 仍然生效
——如果 step 在 import 期就绑定了函数引用,monkeypatch 会打不中。

`hermes_cli/config_migrations.py:69 @ 863e313`

```python
def _cfg():
    """Return the live ``hermes_cli.config`` module (lazy, cycle-free)."""
    from hermes_cli import config

    return config
```

反向侧,`hermes_cli.config` 也是在 `migrate_config` **函数体内**才 import 本模块的
(见 §1.4 的 `config.py:2190` 一段)。

### 1.3 `SUPPORT_FLOOR_VERSION`:支持下限

**是什么**:自动迁移的支持下限,值为 12。低于它的配置**不再自动迁移,也不重写**,
文件保持字节不变,进程继续跑(靠 `load_config()` 读时 deep-merge 默认值)。

`hermes_cli/config_migrations.py:53 @ 863e313`

```python
SUPPORT_FLOOR_VERSION = 12
```

注释给了政策理由(2026 年 7 月定的):v12 之前跨了约两年的版本,继续背着 <12 的迁移步骤
(以及它们消费的 env 桥,如 `HERMES_TOOL_PROGRESS*`)不划算。被删掉的是 v4(tool-progress
`.env` → `config.yaml`)、v5(时区种子)、v9(清 `ANTHROPIC_TOKEN`)。

**用户看到什么**:

`hermes_cli/config_migrations.py:56 @ 863e313`

```python
def support_floor_message() -> str:
    """Human-facing explanation shown when a config is below the floor."""
    from hermes_constants import display_hermes_home

    return (
        f"This config predates version {SUPPORT_FLOOR_VERSION} (~2 years old) "
        "and can no longer be auto-migrated. Back up "
        f"{display_hermes_home()}/config.yaml and run `hermes setup` to "
        f"regenerate, or manually set _config_version: {SUPPORT_FLOOR_VERSION} "
        "after reviewing the changelog."
    )
```

即:告诉用户备份 + `hermes setup` 重生成,或者自己读 changelog 后手写
`_config_version: 12`。这条消息会同时进 `results["warnings"]`、stderr,以及非 quiet 时的 stdout。

### 1.4 闸门到底判什么(闸门**不在**本文件)

三项**同时**成立才拒绝:磁盘上**显式**有 `_config_version` 键、当前版本 < 12、当前版本 < latest。

`hermes_cli/config.py:2196 @ 863e313`

```python
    _explicit_version = _raw_config_has_explicit_version()
    floor_refused = (
        _explicit_version
        and current_ver < SUPPORT_FLOOR_VERSION
        and current_ver < latest_ver
    )
```

第一项是关键区分:**完全没有 `_config_version` 键**的配置不算"古董",算"新写的最小配置"
(profile clone 写裸键、用户手写两行配置),照常走全套阶梯 + 打新版本戳。

`hermes_cli/config.py:1794 @ 863e313`

```python
def _raw_config_has_explicit_version() -> bool:
    """True when config.yaml exists, parses, and carries a ``_config_version`` key.

    Distinguishes an ANCIENT config (explicit old version → refused by the
    v12 support floor) from a fresh minimal/hand-written/cloned config with
    no version key at all (→ migrated + stamped normally). Missing or
    unparseable files return False so they never trip the floor gate.
    """
```

拒绝分支:

`hermes_cli/config.py:2202 @ 863e313`

```python
    if floor_refused:
        msg = support_floor_message()
        results["warnings"].append(msg)
        # stderr so it is visible even on quiet startup paths, matching the
        # corrupt-config warning posture in _warn_config_parse_failure().
        sys.stderr.write(f"⚠ hermes config: {msg}\n")
        if not quiet:
            print(f"  ⚠ {msg}")
```

不拒绝就跑驱动:

`hermes_cli/config.py:2218 @ 863e313`

```python
        run_migrations(current_ver, results, quiet)
```

> **▲ 注释与代码不符(第 1 条)**:`MIGRATIONS` 表上方的注释声称闸门在 `run_migrations()` 里。
>
> `hermes_cli/config_migrations.py:653 @ 863e313`
>
> ```python
>     # every remaining step below. Only configs BELOW 12 are refused by the
>     # floor gate in run_migrations().
> ```
>
> 但 `run_migrations` 全文(§1.5)没有任何 floor 判断,闸门实际在 `config.py:2196`。
> `config.py:2181` 的注释反而说对了(`The floor gate lives here in the wrapper (not in
> run_migrations) so the registry driver stays a pure mechanism that tests can exercise
> directly.`)。**两处注释互相矛盾,代码站在 config.py 这边。**
> 后果不严重(只是读代码的人被指错方向),但它是本文件里唯一一处对"闸门在哪"的错误指路。
> 且 `tests/hermes_cli/test_config.py:1013` 附近确实直接 `run_migrations(11, ...)` 来绕过闸门测 step,
> 证明"驱动是纯机制"是有意为之。

### 1.5 `MIGRATIONS` 表的结构与驱动方式

结构是 `(目标版本, 函数)` 的元组的元组,**严格升序**:

`hermes_cli/config_migrations.py:651 @ 863e313`

```python
MIGRATIONS: Tuple[Tuple[int, Callable[[Dict[str, Any], bool], None]], ...] = (
```

表体(注意 **版本号不连续**:缺 18/19/20/22/24/26/27/28/30):

`hermes_cli/config_migrations.py:655 @ 863e313`

```python
    (12, _migrate_to_12),
    (13, _migrate_to_13),
    (14, _migrate_to_14),
    (15, _migrate_to_15),
    (16, _migrate_to_16),
    (17, _migrate_to_17),
    (21, _migrate_to_21),
    (23, _migrate_to_23),
    (25, _migrate_to_25),
    (29, _migrate_to_29),
    (31, _migrate_to_31),
    (32, _migrate_to_32),
    (33, _migrate_to_33),
```

即:**版本号是全局递增的 schema 序号,不是迁移序号**。有些版本 bump 不需要任何写操作,就没有表项。
文件里有一条**用注释代替函数**的示例(v29→v30):

`hermes_cli/config_migrations.py:528 @ 863e313`

```python
# ── Version 29 → 30: curator.consolidate defaults to false ──
# Consolidation (the LLM umbrella-building fork) is opt-in, OFF by default;
# the deterministic inactivity prune still runs whenever the curator is
# enabled. No write is needed: the schema default (curator.consolidate=false)
# is supplied by load_config()'s deep-merge at read time, and persisting a
# default-valued key would only bloat a lean config (it gets stripped on
# save anyway). Existing installs that WANT the old always-consolidate
# behavior set it to true explicitly via `hermes config set`.
# (No registry entry: this version bump has no migration step.)
```

这条注释**自己就说清了 §1.6 的机制**("persisting a default-valued key ... gets stripped on save
anyway"),这使得 v15/v23 的行为更像是遗漏而不是有意。

驱动本体只有 3 行有效代码:

`hermes_cli/config_migrations.py:683 @ 863e313`

```python
    for target_ver, migration_fn in MIGRATIONS:
        if current_ver < target_ver:
            migration_fn(results, quiet)
```

**关键语义:`current_ver` 在整条阶梯里不推进。** 它由调用方 `check_config_version()` 算一次,
每个 step 都拿同一个初值比较——这是为了逐字复制原来那串顺序 `if` 块的语义。
step 之间**通过文件系统**互相看见对方的写(每个 step 自己 `read_raw_config()` 重读),
所以升序是强制要求。

`hermes_cli/config_migrations.py:671 @ 863e313`

```python
def run_migrations(current_ver: int, results: Dict[str, Any], quiet: bool) -> None:
    """Apply every registered migration whose target version exceeds *current_ver*.

    Replicates the original ladder's semantics exactly: *current_ver* is the
    on-disk schema version captured ONCE (via ``check_config_version()``)
    before any step runs, and it does not advance between steps — each step
    is gated on the same initial value, exactly like the original sequential
    ``if current_ver < N:`` blocks. Steps run in strict ascending registry
    order and mutate ``results`` in place. The final ``_config_version`` bump
    is NOT performed here; it stays in ``migrate_config`` (persisted once,
    after the informational missing-config scan), matching the original flow.
    """
```

`current_ver` 的来源与容错(非整数/布尔/缺失一律当 0 = legacy):

`hermes_cli/config.py:1783 @ 863e313`

```python
def _coerce_config_version(value: Any) -> int:
    """Return a safe integer config version, treating invalid values as legacy."""
    if isinstance(value, bool):
        return 0
    try:
        version = int(value)
    except (TypeError, ValueError):
        return 0
    return max(version, 0)
```

`hermes_cli/config.py:1813 @ 863e313`

```python
def check_config_version() -> Tuple[int, int]:
    """
    Check the raw on-disk config schema version.

    ``load_config()`` deliberately starts from ``DEFAULT_CONFIG`` and deep-merges
    the user's file, which is correct for runtime reads but wrong for deciding
    whether the user's persisted schema has been migrated. A config file with no
    raw ``_config_version`` must remain visible as legacy instead of inheriting
    the latest default version in memory.

    Returns (current_version, latest_version).
    """
```

`latest` 来自 `DEFAULT_CONFIG`:

`hermes_cli/config_defaults.py:3126 @ 863e313`

```python
    "_config_version": 33,
```

**注意 `check_config_version` 的两个"返回 latest,latest"短路**:配置文件不存在,或 YAML 解析失败
(此时只发解析告警,不自动重写)。两种情况下 `current_ver == latest_ver`,阶梯一步不跑、版本也不 bump。
即:**config.yaml 坏了 → 迁移被完全跳过,而且不报"迁移被跳过"**,只报 YAML 解析失败。

### 1.6 每条迁移把什么形状改成什么形状(逐条)

统一约定:每个 step 都 `read_raw_config()`(不 merge 默认值,看用户真正写了什么)→ 原地改 → `_persist_migration(config)`。

| 目标版本 | 函数 | 旧形状 → 新形状 | 是否写盘 |
|---|---|---|---|
| 12 | `_migrate_to_12` | `custom_providers: [ {name,base_url/url/api,…} ]`(列表)→ `providers: {kebab-key: {...}}`(字典);key 由 display name kebab 化,冲突加数字后缀,name 为空则退到 URL hostname;`api_key ∈ {no-key, no-key-required, ""}` 被丢弃;旧列表键 pop 掉 | 是(migrated_count>0 时) |
| 13 | `_migrate_to_13` | `.env` 里的 `LLM_MODEL` / `OPENAI_MODEL` 清空(写 `""`)——2026-03 起 config.yaml 是唯一真相源,这两个键没人读了,留着只造成困惑 | 是(写 `.env`,不是 config.yaml) |
| 14 | `_migrate_to_14` | 扁平 `stt.model` → `stt.<provider>.model`;provider 为 `local`/`local_command` 时,只有当值在 faster-whisper 白名单里才搬进 `stt.local.model`,否则**直接丢弃**(那是个 OpenAI 模型名,喂给 faster-whisper 会 "Invalid model size" 崩) | 是 |
| 15 | `_migrate_to_15` | 补 `display.interim_assistant_messages: true` | **名义上是,实际被剥掉**(§1.7) |
| 16 | `_migrate_to_16` | `display.tool_progress_overrides: {plat: mode}` → `display.platforms: {plat: {tool_progress: mode}}`;**只在目标缺键时填**,不覆盖用户已有值 | 是 |
| 17 | `_migrate_to_17` | `compression.summary_{model,provider,base_url}` 删除;非空/非 `auto` 的值搬去 `auxiliary.compression.*`(同样只在目标为空时填) | 是 |
| 21 | `_migrate_to_21` | 插件从"默认全开(减去 disabled)"改成"opt-in 白名单";扫 `$HERMES_HOME/plugins/*/plugin.y{a,}ml` 把现有**用户**插件祖父条款进 `plugins.enabled`。**bundled 插件不祖父**——对所有人(含老用户)默认关,想用必须显式 opt-in | 是 |
| 23 | `_migrate_to_23` | (1) 把 `curator` 顶层段的默认值写进 config.yaml(只补缺键);(2) 同样写 `auxiliary.curator`;(3) `mkdir -p ~/.hermes/logs/curator` | **(3) 是;(1)(2) 被剥掉**(§1.7) |
| 25 | `_migrate_to_25` | `model_catalog.ttl_hours` 24 → 1;**只改旧默认值 24**,用户改过的别的值不动 | 是 |
| 29 | `_migrate_to_29` | `memory`/`skills` 的三态 `write_mode: on\|off\|approve` → 布尔 `write_approval`;只有显式 `approve` 映射成 `true`,其余(含 `off`)一律 `false`。旧的 "off = 拦住所有写" 语义**被废弃**,要关请用 `memory_enabled: false` | 是 |
| 31 | `_migrate_to_31` | `agent.verify_on_stop` 从 `auto` 哨兵/缺失 → `false`(一次性);显式 `true`/`false` **保留不动** | 是 |
| 32 | `_migrate_to_32` | 补 v31 的漏:v30 首发时 `DEFAULT_CONFIG` 里是字面 `True`,而 `migrate_config` 当时以 `strip_defaults=False` 落盘,于是所有经过 v30 的安装都在 config.yaml 里落了字面 `verify_on_stop: true`;v31 的"保留显式布尔"守卫恰好把这批全跳过了。v32 把**字面 True** 再翻成 False 一次 | 是 |
| 33 | `_migrate_to_33` | `delegation.max_async_children` 废弃,折进 `max_concurrent_children`(取两者较大值,>3 才折),然后删旧键 | 是 |

几条值得单独抄原文的:

**v15 的写(注意它写的就是 schema 默认值):**

`hermes_cli/config_migrations.py:231 @ 863e313`

```python
    if "interim_assistant_messages" not in display:
        display["interim_assistant_messages"] = True
        config["display"] = display
        results["config_added"].append("display.interim_assistant_messages=true (default)")
        _persist_migration(config)
        if not quiet:
            print("  ✓ Added display.interim_assistant_messages=true")
```

对应的 schema 默认值:

`hermes_cli/config_defaults.py:1193 @ 863e313`

```python
        "interim_assistant_messages": True,  # Gateway: send natural mid-turn assistant status messages. Desktop: keep mid-turn narration between tool calls instead of collapsing to the final message.
```

**v23 的自述目的**(第 1 条目的就是"让用户在 config.yaml 里看得见/改得动"):

`hermes_cli/config_migrations.py:383 @ 863e313`

```python
def _migrate_to_23(results: Dict[str, Any], quiet: bool) -> None:
    # ── Version 22 → 23: seed curator defaults + create logs/curator/ ──
    # The curator (background skill maintenance) was added in PR #16049, but
    # existing configs from before that PR (or before the April 2026
    # unification under `auxiliary.curator`) never wrote the curator section
    # to disk. The runtime deep-merge in `load_config()` fills defaults at
    # read time, so the curator *functions*; but users can't see/edit the
    # settings in their `config.yaml`, and `hermes curator status` has no
    # stable logs dir to point at until the first run mkdir's it.
```

它拷的就是 `DEFAULT_CONFIG` 的值本身:

`hermes_cli/config_defaults.py:1842 @ 863e313`

```python
    "curator": {
        "enabled": True,
        # How long to wait between curator runs (hours).  Default: 7 days.
        "interval_hours": 24 * 7,
        # Only run when the agent has been idle at least this long (hours).
        "min_idle_hours": 2,
        # Mark a skill as "stale" after this many days without use.
        "stale_after_days": 30,
```

**v31 的守卫**(只翻"没表态"的状态):

`hermes_cli/config_migrations.py:539 @ 863e313`

```python
def _migrate_to_31(results: Dict[str, Any], quiet: bool) -> None:
    # ── Version 30 → 31: switch verify_on_stop OFF (one-time) ──
    # verify_on_stop defaulted to the "auto" sentinel (surface-aware: on for
    # interactive coding surfaces). In practice the verification narrative was
    # more noise than signal — it even fired on doc/markdown/skill edits with
    # nothing to verify. The new default is OFF. This migration switches
    # existing installs off ONCE, but only when the user never expressed an
    # explicit preference: we rewrite the value only if it's missing or still
    # the "auto" sentinel. An explicit true/false the user set is preserved.
```

> **▲ 注释与代码不符(第 2 条)**:上面写 "The new default is OFF",但 `DEFAULT_CONFIG` 里
> `verify_on_stop` **至今仍是 `"auto"`**:
>
> `hermes_cli/config_defaults.py:158 @ 863e313`
>
> ```python
>         "verify_on_stop": "auto",
> ```
>
> 后果是**老用户与新用户行为分叉**:升级过来的用户被 v31/v32 一次性写死 `false`;
> 而**全新安装**(config 直接生成在 v33,阶梯一步不跑)拿到的是 `"auto"`,即在 CLI/TUI/desktop
> 这些交互式编码界面上 verify-on-stop **仍然是开的**。§8 的实测里 `agent.verify_on_stop: false`
> 确实落了盘,证明 v31 走的是"值 ≠ 默认所以写得进去"这条路——恰恰说明默认值没改。

**v32 对 v31 漏洞的自述**(顺带交代了 `strip_defaults` 这段历史):

`hermes_cli/config_migrations.py:574 @ 863e313`

```python
def _migrate_to_32(results: Dict[str, Any], quiet: bool) -> None:
    # ── Version 31 → 32: flip the BAKED-IN literal true to OFF (one-time) ──
    # The v30→v31 flip above only caught missing/"auto" values. But the very
    # first ship of verify-on-stop (config v30, commit 2f1a47b90) defaulted
    # DEFAULT_CONFIG["agent"]["verify_on_stop"] to a literal True, and
    # migrate_config persists defaults with strip_defaults=False — so every
    # install that updated through v30 got `verify_on_stop: true` written into
    # config.yaml as a literal. v31's guard deliberately preserves an explicit
    # bool, so it skipped that whole population and left them ON. That literal
    # true was never a user choice: the feature had no off-switch worth setting
    # it against until v31 introduced one, so a true persisted before v32 is
    # always the old machine default. Flip it off once here. A true the user
    # sets AFTER v32 (config already at version 32) is never touched.
```

### 1.7 写入不变式:`_persist_migration` —— 以及它吃掉了 v15/v23

**所有** step 必须走这个 helper,不许直接 `save_config`:

`hermes_cli/config.py:2124 @ 863e313`

```python
def _persist_migration(config: Dict[str, Any]) -> None:
    """Persist a migrated config under the migration write invariant.

    THE INVARIANT (single source of truth for the whole migration pipeline):
    a migration may only persist values that DIFFER from the current schema
    default, plus explicit removals/renames of user data. Pure schema defaults
    are never materialised to disk — ``load_config()``'s deep-merge supplies
    them at read time, so writing them adds nothing and actively shadows future
    default changes (see ``save_config``'s docstring). Materialising defaults on
    every version bump is what rewrote hand-curated configs into full
    DEFAULT_CONFIG dumps (the "hermes update / hermes -p blows up my config"
    reports).
```

实现只有一行(strip_defaults 默认 True,`merge_existing` 默认 False):

`hermes_cli/config.py:2147 @ 863e313`

```python
    save_config(config)
```

剥离逻辑:

`hermes_cli/config.py:2698 @ 863e313`

```python
def _strip_default_values(
    config: Dict[str, Any],
    defaults: Dict[str, Any] = DEFAULT_CONFIG,
    preserve_keys: Optional[Set[Tuple[str, ...]]] = None,
) -> Dict[str, Any]:
    """Return *config* without keys whose values match *defaults*.

    Keys in *preserve_keys* (explicitly present in the user's raw config,
    before any normalisation) are always kept even when they equal the
    default, so user-set values such as ``memory.user_char_limit: 2200``
    survive a ``save_config`` round-trip.

    Nested dicts whose every child is stripped are removed entirely so
    default-only subtrees (e.g. ``gateway``) never bloat ``config.yaml``
    when the user has nothing to say about them.
    """
```

`hermes_cli/config.py:2733 @ 863e313`

```python
        if value == default:
            return None
```

**推论(核心发现)**:`preserve_keys` 来自"用户**已经**写在磁盘上的路径"。v15 和 v23 的守卫条件
恰恰是"这个键**还不在**磁盘上",所以它们新加的键**天然不在 preserve_keys 里**;而它们写入的值
**恰好等于 `DEFAULT_CONFIG` 的值**;于是 `_strip_default_values` 把它们全剥掉,子树被剥空后整段删掉。
**磁盘上一个字都不多,但 `results["config_added"]` 仍然报告"已添加"。**

**实测验证**(临时 HERMES_HOME,从 `_config_version: 14` 起跑 `migrate_config(interactive=False, quiet=True)`,
脚本见 §8):

```text
config_added: ['display.interim_assistant_messages=true (default)',
               'plugins.enabled (opt-in allow-list, 0 grandfathered)',
               'curator (8 default key(s))',
               'auxiliary.curator (7 default key(s))',
               'agent.verify_on_stop=false']

--- config.yaml AFTER migration ---
_config_version: 33
model:
  default: openai/gpt-4o
agent:
  verify_on_stop: false
plugins:
  enabled: []
```

即:报告说加了 5 项,盘上只落了 2 项。
- `display.interim_assistant_messages` —— 没了(值 == 默认 True)。
- `curator:` / `auxiliary.curator:` —— **整段没了**(逐键都 == 默认)。**v23 自述的第 1、2 条目的
  100% 落空**,只有第 3 条(mkdir `logs/curator/`)生效。
- `agent.verify_on_stop: false` 落了盘 —— 因为默认是 `"auto"`,`false != "auto"`。
- `plugins.enabled: []` 落了盘 —— 因为 `plugins` 根键**根本不在 `DEFAULT_CONFIG` 里**
  (它在 `_EXTRA_KNOWN_ROOT_KEYS` 白名单),`_strip` 拿 `[]` 和 `None` 比,不相等,于是保留。

**这不是纯粹的无害**:v23 的目的就是"让用户在 config.yaml 里看得见 curator 设置",行为上 curator
照常工作(读时 deep-merge),但**用户看不见、编辑器补全不到、`hermes config` 里也不显示为已设**——
迁移的全部意义被自己的写入不变式吃掉了。v15 同理(但 v15 只是补默认,危害更小)。

**是 bug 还是有意?** 判为 **bug / 至少是两条规则相撞后没人收口**:
`_persist_migration` 的 docstring 明确说"只准写与默认不同的值",而 v15/v23 写的**只有**默认值,
两者从设计意图上就互斥。v29→v30 那段注释(§1.5)证明作者**知道**这条规则,
所以更像是 v15/v23 写在规则确立之前、后来没回头清理。

### 1.8 原子性 / 备份 / 失败了怎么办

- **原子**:`save_config` 最终走 `utils.atomic_yaml_write`,临时文件 + `fsync` + `os.replace`。

  `utils.py:335 @ 863e313`

  ```python
  def atomic_yaml_write(
      path: Union[str, Path],
      data: Any,
      *,
      default_flow_style: bool = False,
      sort_keys: bool = False,
      extra_content: str | None = None,
      create_mode: "int | None" = None,
  ) -> None:
      """Write YAML data to a file atomically.

      Uses temp file + fsync + os.replace to ensure the target file is never
      left in a partially-written state.  If the process crashes mid-write,
      the previous version of the file remains intact.
  ```

- **不做迁移前备份**。整条迁移链**没有任何** `config.yaml.pre-migration.bak` 之类的动作。
  唯一的 `.bak` 是**解析失败时**的取证快照,与迁移无关:

  `hermes_cli/config.py:45 @ 863e313`

  ```python
  def _backup_corrupt_config(config_path: Path) -> Optional[Path]:
      """Preserve a corrupted ``config.yaml`` by copying it to a timestamped ``.bak``.

      When the YAML can't be parsed, ``load_config()`` silently falls back to
      ``DEFAULT_CONFIG`` and the user's broken file stays on disk untouched.
  ```

- **不是一次性事务**:每个 step **各写各的**(每次 `_persist_migration` 都是一次完整落盘)。
  一条 13 步的升级路径最多写 13 次盘,中途异常就停在半路。
- **step 内部的失败处理很不统一**:v13 整个包在 `except Exception: pass` 里
  (`config_migrations.py:162`);v21 的插件扫描包在 try 里、失败就 `grandfathered = []`;
  v23 的 mkdir 失败进 `results["warnings"]`。**但 `_persist_migration` 自身的异常没有任何 step 捕获**
  ——落盘失败会直接冒出 `migrate_config`。

### 1.9 `_config_version` 什么时候前进 + 「跑了迁移但版本不前进」

版本 bump 是**独立于 `run_migrations` 的一次单独落盘**,位置在 `migrate_config` 后半段:

`hermes_cli/config.py:2365 @ 863e313`

```python
    if current_ver < latest_ver and not floor_refused:
        config = read_raw_config()
        config["_config_version"] = latest_ver
        _persist_migration(config)
```

**存在「跑了迁移但版本号不前进」的窗口,而且是真实可达的**:bump 之前隔着两段
**没有 try/except 的交互式 `input()`**(补必填 env 变量、补新增可选 env 变量):

`hermes_cli/config.py:2283 @ 863e313`

```python
    if interactive and missing_env:
        print("\nLet's configure them now:\n")
        for var in missing_env:
            if var.get("url"):
                print(f"  Get your key at: {var['url']}")
            
            if var.get("password"):
                value = masked_secret_prompt(f"  {var['prompt']}: ")
            else:
                value = input(f"  {var['prompt']}: ").strip()
```

用户在这里 Ctrl-C(`KeyboardInterrupt`)或管道 EOF(`EOFError`)→ 异常直接冒出 `migrate_config`
→ **迁移 step 已经全部落盘,`_config_version` 却还停在旧值**。下一次启动会把 §1.6 那整张表
从头再跑一遍。

**这个"重跑"危险吗?** 逐条查过:v12/13/14/16/17/29/33 都由"旧键还在不在"守卫,写完键就没了,重跑是 no-op;
v21 由 `"enabled" not in plugins_cfg` 守卫,而 `plugins.enabled: []` **能落盘**(§1.7),重跑也是 no-op;
v25 由 `ttl_hours == 24` 守卫,改成 1 后不再命中;v31/v32 由 `auto`/字面 True 守卫,翻成 false 后不再命中。
**只有 v15 和 v23 会无限重跑**——恰恰因为它们的写被剥掉了,守卫条件永远为真。
后果是每次启动都多两次无谓落盘 + 重复打印 `✓ Added display.interim_assistant_messages=true` /
`✓ Curator settings now available`,以及 `results["config_added"]` 里的重复噪声。
**判定:低危,但它是 §1.7 那个 bug 的放大器——两个缺陷叠在一起才产生"每次启动都说加了、永远没加上"这个现象。**

另外两个"版本不前进"的情形是**有意**的:
- `floor_refused`(§1.4)——刻意不动文件,包括版本戳。
- `current_ver == latest_ver`——没什么可前进的。
- (以及 §1.5 末尾提到的:config.yaml 解析失败时 `check_config_version` 返回 `(latest, latest)`,
  迁移与 bump 一起被跳过,且**不会**告诉用户"迁移被跳过了"。)

---

## 2. `hermes_cli/env_loader.py` —— 配置值从进程环境来的那条路

### 2.1 入口与调用时机:**import 期**,而且一个进程里会跑好几遍

`load_hermes_dotenv()` 是唯一正规入口。它在多个热模块的**模块顶层**被调用,即 **import 期**:

`cli.py:231 @ 863e313`

```python
load_hermes_dotenv(hermes_home=_hermes_home, project_env=_project_env)
```

`hermes_cli/main.py:697 @ 863e313`

```python
load_hermes_dotenv(project_env=PROJECT_ROOT / ".env")
```

其余 import 期调用点:`gateway/run.py:1829`、`trajectory_compressor.py:56`。
运行期还有 `gateway/run.py:1854`(网关热重载)、`cron/scheduler.py:3189`、`hermes_cli/dump.py:285`。
模块自己的注释确认了"一次启动跑 3–5 遍"这个事实,并说明这正是要有 `_APPLIED_HOMES` 去重的原因:

`hermes_cli/env_loader.py:45 @ 863e313`

```python
# process.  ``load_hermes_dotenv()`` is called at module-import time from
# several hot modules (cli.py, hermes_cli/main.py, run_agent.py,
# trajectory_compressor.py, gateway/run.py, ...), so without this guard the
# Bitwarden status line gets printed 3-5x per startup.  Bitwarden's own
# in-process cache prevents redundant network calls, but the print, the
# config re-parse, and the ASCII sanitization sweep still ran every time.
_APPLIED_HOMES: set[str] = set()
```

### 2.2 「加载太晚」的窗口 —— 存在,而且已经被撞过两次

因为是 import 期加载,**任何在它之前被 import 的模块,如果在模块顶层快照了 `os.getenv(...)`,
就永远拿不到 `.env` 的值**。仓库里有两处**已被真实事故驱动**的补丁,可以作证这个窗口是真的:

**(a) `agent.redact` 的 import 期快照**。`main.py` 必须在 `setup_logging()` 之前
把 `security.redact_secrets` 从 config.yaml 桥到 env,否则 `agent.redact` 在 import 时
只读一次 env var,config.yaml 的开关就被无视:

`hermes_cli/main.py:699 @ 863e313`

```python
# Bridge security.redact_secrets from config.yaml → HERMES_REDACT_SECRETS env
# var BEFORE hermes_logging imports agent.redact (which snapshots the flag at
# module-import time). Without this, config.yaml's toggle is ignored because
# the setup_logging() call below imports agent.redact, which reads the env var
# exactly once. Env var in .env still wins — this is config.yaml fallback only.
```

**(b) `load_config()` 缓存住了"加载 .env 之前"的 `${VAR}` 展开**(issue #58514)。
`load_config()` 的缓存键原本只有文件 mtime/size,于是一次"跑在 `load_hermes_dotenv()` 之前"的
`load_config()` 会把未展开的字面量(如 `auxiliary.<task>.api_key`)钉死整个进程生命周期。
修法是给缓存额外挂一份 env 快照:

`hermes_cli/config.py:3326 @ 863e313`

```python
            # Without this, a load_config() that ran before load_hermes_dotenv()
            # pins unexpanded literals (e.g. auxiliary.<task>.api_key) for the
            # life of the process (#58514).
```

对应的快照函数:

`hermes_cli/config.py:2563 @ 863e313`

```python
def _env_ref_snapshot(obj, snapshot=None):
    """Map every ``${VAR}`` / ``${env:VAR}`` name referenced in config values
    to its current ``os.environ`` value (``None`` when unset).

    Stored alongside cached ``load_config()`` results so a cache hit can
    detect that the cached expansion was made against a *different*
    environment — e.g. a ``load_config()`` that ran before
    ``load_hermes_dotenv()`` populated the process env, or an env var
    rotated in-process after the first load. File mtime/size alone cannot
    see either case (#58514).
```

**结论**:窗口是真的,作者的对策不是"提前加载"而是"**让下游能检测到自己读早了**"
(env 快照失配就作废缓存)。这是个可迁移的设计点:**当加载顺序无法保证时,把"我是在哪个环境下算出这个值的"
一起缓存,比强行排顺序更稳。**

### 2.3 找哪些路径、什么顺序、谁覆盖谁

主体只有 60 行,顺序即语义:

`hermes_cli/env_loader.py:462 @ 863e313`

```python
def load_hermes_dotenv(
    *,
    hermes_home: str | os.PathLike | None = None,
    project_env: str | os.PathLike | None = None,
) -> list[Path]:
    """Load Hermes environment files with user config taking precedence.

    Behavior:
    - `~/.hermes/.env` overrides stale shell-exported values when present.
    - project `.env` acts as a dev fallback and only fills missing values when
      the user env exists.
    - if no user env exists, the project `.env` also overrides stale shell vars.
    """
```

home 的解析(参数 > `HERMES_HOME` 环境变量 > `~/.hermes`):

`hermes_cli/env_loader.py:477 @ 863e313`

```python
    home_path = Path(hermes_home or os.getenv("HERMES_HOME", Path.home() / ".hermes"))
```

**(1) 用户 `.env`,`override=True`**——即**覆盖已存在的 `os.environ`**:

`hermes_cli/env_loader.py:487 @ 863e313`

```python
    if user_env.exists():
        _load_dotenv_with_fallback(user_env, override=True)
        loaded.append(user_env)
        # Mirror reload_env() known-key cleanup so inherited Hermes keys
        # absent from this profile's .env do not leak into the runtime.
        _clear_known_keys_missing_from_dotenv(user_env)
```

**(2) `<home>/.op.env`,`override=False`**——唯一一档**不覆盖**的:

`hermes_cli/env_loader.py:504 @ 863e313`

```python
    op_env = home_path / ".op.env"
    if op_env.exists() and not os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"):
        _load_dotenv_with_fallback(op_env, override=False)
```

理由(注释 494–503):它只是 1Password 的 bootstrap token 容器,gitignored,不进 `.env`;
systemd 的 `EnvironmentFile=` 应当优先,所以不覆盖。

**(3) 项目 `.env`,`override=not loaded`**——即:用户 `.env` 存在过就只补空,否则也覆盖 shell:

`hermes_cli/env_loader.py:508 @ 863e313`

```python
    if project_env_path and project_env_path.exists():
        _load_dotenv_with_fallback(project_env_path, override=not loaded)
        loaded.append(project_env_path)
```

**(4) 外部密钥源(Bitwarden / 1Password / …)→ (5) managed `.env` → (6) terminal 配置桥**:

`hermes_cli/env_loader.py:512 @ 863e313`

```python
    _apply_external_secret_sources(home_path)
    _apply_managed_env()
```

`hermes_cli/env_loader.py:527 @ 863e313`

```python
    _reapply_terminal_config_bridge(home_path)
```

**最终优先级(低 → 高)**:

```
shell 导出的 os.environ
  < 用户 ~/.hermes/.env            (override=True)
  < 项目 ./.env                    (仅当用户 .env 不存在时才 override;否则只补空)
  < 外部密钥源 (registry.apply_all)
  < managed .env                   (override=True,机器级,与 profile 无关)
  < config.yaml 的 terminal.* 显式键 (最后一手,只覆盖用户真写过的键)
```

其中 `.op.env` 插在(1)与(3)之间但**永不覆盖**,只填 `OP_SERVICE_ACCOUNT_TOKEN` 这一个空位。

**managed 一档是刻意反转优先级的**(通常是 env 压 config,这里是 admin 的 env 压一切):

`hermes_cli/env_loader.py:559 @ 863e313`

```python
def _apply_managed_env() -> None:
    """Apply the managed-scope .env last, with override, so it beats user/shell.

    Managed scope is machine-global (independent of HERMES_HOME / profile). v1
    enforcement is "applied last with override=True" — at the end of startup load
    ``os.environ`` holds the managed value for every managed key, beating both the
    user ``.env`` and any pre-existing shell export. This deliberately inverts the
    usual env-over-config precedence for the pinned keys (see
    ``docs/design/managed-scope.md`` §4.1).

    This does NOT prevent the agent from later mutating ``os.environ`` in-process
    or ``export``-ing in a subprocess shell; that hard boundary is a documented
    v2 item (design §8.1). v1 relies on filesystem permissions only.
```

**最后一档(terminal 桥)存在的原因是个真实事故**:config.yaml 是 `terminal.*` 的文档化真相源,
但上面那几档都 `override=True`,于是 `~/.hermes/.env` 里一条陈旧的 `TERMINAL_ENV=docker`
每次 reload 都会重新赢回去;长驻进程(网关每轮 reload、cron)会在会话中途把后端翻回旧值(#29186、#67323):

`hermes_cli/env_loader.py:515 @ 863e313`

```python
    # config.yaml is the documented source of truth for terminal.* settings,
    # but the dotenv loads above run with override=True — so a stale
    # TERMINAL_ENV=docker left in ~/.hermes/.env (e.g. written by an older
    # `hermes setup` before the user switched terminal.backend in config.yaml)
    # silently wins again on every reload. Startup launchers bridge
    # config→env once, but long-lived processes (gateway per-turn reload,
    # cron standalone runs) call load_hermes_dotenv() repeatedly and used to
    # flip the effective backend back to the stale .env value mid-session
    # (#29186, #67323). Re-apply config.yaml's explicit terminal keys last so
    # the documented config path always wins. Runs after _apply_managed_env()
    # so the merged config (which already carries the managed overlay) is
    # what lands in the env.
```

### 2.4 「继承键清洗」:窄到只有 6 个键

用户 `.env` 加载后,会把**父 Hermes 进程注入、但本 profile 的 `.env` 里没写**的键从 `os.environ` 删掉。
范围**故意极窄**,只有行为路由类的键,**绝不含凭据**:

`hermes_cli/env_loader.py:76 @ 863e313`

```python
_PROFILE_MANAGED_ENV_KEYS: frozenset[str] = frozenset({
    "HERMES_ACP_AUTH_METHOD",
    "HERMES_ACP_AUTO_APPROVE",
    "HERMES_COPILOT_ACP_COMMAND",
    "HERMES_COPILOT_ACP_ARGS",
    "COPILOT_CLI_PATH",
    "COPILOT_ACP_BASE_URL",
})
```

理由写得很清楚:`export OPENAI_API_KEY=…` 是**文档化的合法用法**,启动期的清洗**无法区分**
"用户 shell 导出"和"父进程泄漏",全量清洗会在每次 `hermes` 调用时删掉用户导出的凭据。
跨 profile 的**凭据**隔离改由**读时**的 `agent.secret_scope.get_secret` 负责:

`hermes_cli/env_loader.py:114 @ 863e313`

```python
def _clear_known_keys_missing_from_dotenv(path: Path) -> None:
    """Remove inherited profile-managed Hermes keys absent from ``.env``.

    After the profile's ``.env`` has been loaded with ``override=True``,
    scan the file for which profile-managed keys it explicitly defines and
    delete any such key that exists in ``os.environ`` but is *not* present
    in the file.

    Scope is deliberately NARROW: only ``_PROFILE_MANAGED_ENV_KEYS`` —
```

**注意"存在但为空"也算定义**(`KEY=` 会被记进 `defined`),所以用空赋值可以显式"清掉继承值"。
对应测试 `tests/hermes_cli/test_env_loader.py:211`(`test_empty_assignment_in_user_env_is_preserved`)。

### 2.5 解析器:自写还是用库?—— **两者都有,而且是三份**

**主路径用库**(`python-dotenv==1.2.2`,`pyproject.toml:42`),带 UTF-8 → latin-1 的降级重试:

`hermes_cli/env_loader.py:342 @ 863e313`

```python
def _load_dotenv_with_fallback(path: Path, *, override: bool) -> None:
    try:
        load_dotenv(dotenv_path=path, override=override, encoding="utf-8")
    except UnicodeDecodeError:
        load_dotenv(dotenv_path=path, override=override, encoding="latin-1")
```

**但同一个仓库里还有两份手写的 `.env` 解析器**(§6.1 详列)。本文件自己就有第三份——
一个只取 key 名的"快速行扫描器",理由是早期 bootstrap 阶段不想 import python-dotenv:

`hermes_cli/env_loader.py:86 @ 863e313`

```python
def _env_keys_defined_in_dotenv(path: Path) -> set[str]:
    """Return KEY names assigned in a dotenv file (including empty ``KEY=``).

    Uses a fast line scanner rather than full dotenv parsing so it works
    during early bootstrap without importing python-dotenv.  Ignores comment
    and blank lines.  Non-ASCII encoding errors fall back to ``latin-1``,
    matching ``_load_dotenv_with_fallback``.
    """
```

`hermes_cli/env_loader.py:102 @ 863e313`

```python
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key = line.split("=", 1)[0].strip()
        if key:
            keys.add(key)
```

**支持的语法**(以 python-dotenv 1.2.2 为准,主路径):`KEY=VALUE`、`export KEY=VALUE`、
单/双引号(双引号内支持 `\"` `\\` 转义与 `\n` 展开)、`#` 全行与未引用值的行内注释、
双引号内的多行值、以及 **python-dotenv 自己的 `${VAR}` POSIX 插值**(`interpolate=True` 是默认)。
写侧的转义约定由 `hermes_cli.config._parse_env_value` 定义:

`hermes_cli/config.py:3621 @ 863e313`

```python
def _parse_env_value(raw_value: str) -> str:
    """Parse the small .env value subset Hermes writes itself."""
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        quoted = value[1:-1]
        parsed: list[str] = []
        i = 0
        while i < len(quoted):
            ch = quoted[i]
            if ch == "\\" and i + 1 < len(quoted):
                next_ch = quoted[i + 1]
                if next_ch in {'"', "\\"}:
                    parsed.append(next_ch)
                    i += 2
                    continue
            parsed.append(ch)
            i += 1
        return "".join(parsed)
```

### 2.6 编码地雷区:BOM 嗅探与 NUL 剥离(读前预处理)

在交给 python-dotenv 之前,先按**字节**嗅 BOM。**顺序至关重要**:`BOM_UTF32_LE` 是 `FF FE 00 00`,
它 startswith `BOM_UTF16_LE`(`FF FE`),先判 UTF-16 会把 UTF-32-LE 判错并把文件搅烂。

`hermes_cli/env_loader.py:355 @ 863e313`

```python
def _sanitize_env_file_if_needed(path: Path) -> None:
    """Pre-sanitize a .env file before python-dotenv reads it.

    Strips embedded null bytes which crash ``os.environ[k] = v``
    with ``ValueError: embedded null byte`` — typically introduced by
    copy-pasting API keys from terminals or rich-text editors.

    Encoding: sniffs a leading BOM *before* any text decode. UTF-16
    (Notepad "Unicode") is decoded correctly and rewritten as clean
    UTF-8. UTF-32 is refused (left untouched) so we never fall through
    to the errors=replace corruption path. Order of BOM checks matters:
    UTF-32-LE's BOM starts with UTF-16-LE's FF FE.
```

`hermes_cli/env_loader.py:388 @ 863e313`

```python
    if raw.startswith(codecs.BOM_UTF32_LE) or raw.startswith(codecs.BOM_UTF32_BE):
```

UTF-32 是**拒绝处理**(留原文件不动,只警告一次,`_WARNED_UTF32_PATHS` 去重);
UTF-16 则解码后**重写成干净 UTF-8**。还有一道纵深防御:`errors="replace"` 会把不可解码字节
变成 U+FFFD,如果首行以 U+FFFD 开头就**放弃写**,免得把替换字符永久粘到第一个 key 名上
(`env_loader.py:431`)。重写本身是 mkstemp + fsync + `atomic_replace`(`env_loader.py:441-457`),
整段包在 `except Exception: pass` 里——"尽力而为,不许挡住网关启动"。

### 2.7 凭据的 ASCII 净化(与 `_CREDENTIAL_SUFFIXES` 的关系)

每次 dotenv 加载后都跑一遍。**只动名字以凭据后缀结尾的变量**——不能随便改用户的任意 env var,
但凭据必须是纯 ASCII(要当 HTTP header 值发出去)。

`hermes_cli/env_loader.py:20 @ 863e313`

```python
_CREDENTIAL_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET", "_KEY")
```

`hermes_cli/env_loader.py:298 @ 863e313`

```python
def _sanitize_loaded_credentials() -> None:
    """Strip non-ASCII characters from credential env vars in os.environ.

    Called after dotenv loads so the rest of the codebase never sees
    non-ASCII API keys.  Only touches env vars whose names end with
    known credential suffixes (``_API_KEY``, ``_TOKEN``, etc.).

    Emits a one-line warning to stderr when characters are stripped.
    Silent stripping would mask copy-paste corruption (Unicode lookalike
    glyphs from PDFs / rich-text editors, ZWSP from web pages) as opaque
    provider-side "invalid API key" errors (see #6843).
    """
```

**事故经过(#6843)**:用户从 PDF / 富文本编辑器 / 网页复制 API key,编辑器把 ASCII 字母换成了
Unicode 相似字形(如 `ʋ` U+028B 替 `v`),或塞进零宽空格。httpx 用 ASCII 编 header,
于是报的是 provider 侧的 "API key not valid"——**跟"你的 key 里有个看不见的字符"毫无关联**。
现在会明确告诉你剥了几个字符、是哪几个码点,并提示重新从 dashboard 复制。
`_WARNED_KEYS` 保证同一个 key 一个进程里只警告一次。

注意 `_CREDENTIAL_SUFFIXES` 的最后一项是 `"_KEY"`,它是 `"_API_KEY"` 的超集,
也会命中 `SOME_PUBLIC_KEY` 这类非凭据变量——**净化范围比字面意义上的"凭据"宽**。

### 2.8 与 `OPTIONAL_ENV_VARS` 的关系 —— 以及一段死代码

`OPTIONAL_ENV_VARS` 是"设置向导认识的 env 变量 + 元数据"(description / prompt / url / `password` 标志):

`hermes_cli/config_defaults.py:3130 @ 863e313`

```python
OPTIONAL_ENV_VARS = {
```

env_loader 里有个函数把它和 `_EXTRA_ENV_KEYS`(向导之外的 provider/平台键)并起来:

`hermes_cli/env_loader.py:55 @ 863e313`

```python
def _known_hermes_env_keys() -> set[str]:
    """Return the combined set of known Hermes env-var keys.

    Includes both ``OPTIONAL_ENV_VARS`` (setup-flow vars with metadata) and
    ``_EXTRA_ENV_KEYS`` (provider/platform keys managed outside the setup
    wizard).  Lazy-imported to avoid circular-dependency during early-bootstrap
    ``load_hermes_dotenv()`` calls.
    """
```

> **◇ 死代码**:`_known_hermes_env_keys` 在**全仓范围内零调用**
> (`grep -rn "_known_hermes_env_keys" --include=*.py .` 只命中它自己的定义行)。
> 清洗路径现在用的是窄集合 `_PROFILE_MANAGED_ENV_KEYS`(§2.4)。
> 从 §2.4 的注释("Clearing the full known-key set would delete user-exported credentials on every
> `hermes` invocation")可以推断:**这个函数就是当年那个"全量清洗"版本的遗留**,收窄后没删。
> 同一个"并集"逻辑现在活在 `hermes_cli/config.py:4095` 的 `reload_env()` 里:
>
> `hermes_cli/config.py:4095 @ 863e313`
>
> ```python
>     known_keys = set(OPTIONAL_ENV_VARS.keys()) | _EXTRA_ENV_KEYS
> ```
>
> 即:**同一个"Hermes 认识哪些 env 键"的集合,被算了两遍,一份还是死的。**

### 2.9 `${VAR}` 展开:**两套引擎**

- **引擎 A(.env 内部)**:python-dotenv 自带的 POSIX 插值,作用于 `.env` 文件内部的值。
- **引擎 B(config.yaml 内部)**:`hermes_cli.config._expand_env_vars`,支持 `${VAR}` 与 `${env:VAR}`,
  **未解析的引用原样保留**,好让调用方能检测出来:

  `hermes_cli/config.py:2546 @ 863e313`

  ```python
  def _expand_env_vars(obj):
      """Recursively expand ``${VAR}`` / ``${env:VAR}`` references in config
      values.

      Only string values are processed; dict keys, numbers, booleans, and
      None are left untouched.  Unresolved references (variable not in
      ``os.environ``) are kept verbatim so callers can detect them.
      """
  ```

引擎 B 只在 `.env` 已经进了 `os.environ` 之后才有意义 —— 这正是 §2.2(b) 那个 issue 的成因。
配套的 `_preserve_env_ref_templates`(`config.py:2609` 之后)负责在 save 回盘时把展开值**还原成模板**,
免得一次 `hermes config set` 就把用户的 `${OPENAI_API_KEY}` 固化成明文密钥。

### 2.10 外部密钥源与「一次一 home」缓存

`_apply_external_secret_sources` 跑在 dotenv 之后、其余代码读凭据之前;重活(源排序、
mapped 压 bulk、first-claim-wins、provenance)在 `agent.secret_sources.registry.apply_all` 里,
本 wrapper 只管四件事:一次一 home 的去重、事后 ASCII 净化、`_SECRET_SOURCES` 溯源表、启动状态行。

`hermes_cli/env_loader.py:591 @ 863e313`

```python
def _apply_external_secret_sources(home_path: Path) -> None:
    """Pull secrets from every enabled external source into env.

    Runs AFTER dotenv loads so .env values are visible (sources use them
    to locate bootstrap tokens) but BEFORE the rest of Hermes reads
    ``os.environ`` for credentials.  Any failure here is logged and
    swallowed — external secret sources must never block startup.
```

**去重标记的位置很讲究(#40597)**:`_APPLIED_HOMES.add()` 放在**真的发起过一次抓取之后**,
不是放在开头。所以"config.yaml 写坏了""secrets 段没配""所有源都禁用"这三种情形
**都不标记为已应用**——用户修好文件后,同进程的下一次 `load_hermes_dotenv()` 还能捡起来;
如果一进门就标记,一个坏配置会**永久**关掉该进程的密钥加载。

`hermes_cli/env_loader.py:653 @ 863e313`

```python
    _APPLIED_HOMES.add(home_key)
```

溯源表的用途是 UI 标注:没有它,"credentials detected ✓" 这行在 `.env` 直供和 Bitwarden 供给两种情况下
长得一模一样,用户不知道 key 从哪来:

`hermes_cli/env_loader.py:256 @ 863e313`

```python
def format_secret_source_suffix(env_var: str) -> str:
    """Return a human-readable suffix like ``" (from Bitwarden)"`` or ``""``.

    Use this when printing a detected credential so the user can see where
    it came from.  Empty string when the credential came from ``.env`` or
    the shell — those are the implicit / "default" cases users already
    understand.
    """
```

多路复用网关的补充路径 `hydrate_profile_secret_sources`:第一轮就路由到一个从未跑过进程级
dotenv 启动路径的次要 profile 时,**在私有 mapping 里**解析它的源,**不碰 `os.environ`**:

`hermes_cli/env_loader.py:169 @ 863e313`

```python
def hydrate_profile_secret_sources(
    hermes_home: str | os.PathLike,
) -> dict[str, str]:
    """Resolve one profile's configured sources without mutating ``os.environ``.

    Multiplex gateways can route a first turn to a secondary profile that has
    never run the process-global dotenv startup path.  Resolve that profile's
    sources against a private mapping seeded from its own ``.env`` and record
    the usual per-home snapshot for ``build_profile_secret_scope()``.
```

模块级注释点破了为什么要按 home 存快照而不是只看 `os.environ`:

`hermes_cli/env_loader.py:40 @ 863e313`

```python
# Applied values are immutable per-home snapshots.  ``os.environ`` is shared
# across profiles and may be overwritten by a later home's source apply.
```

### 2.11 只读 `secrets:` 段的独立解析器

为了"config.yaml 坏了不能把 dotenv 加载一起拖下水",`secrets:` 段有独立读法;
但如果是进程自己的 HERMES_HOME,则优先复用共享的 (mtime,size) 缓存,把一次启动的
config.yaml 解析次数从 3–4 次压到 1 次:

`hermes_cli/env_loader.py:709 @ 863e313`

```python
def _load_secrets_config(home_path: Path) -> dict:
    """Read just the ``secrets:`` section out of config.yaml.

    Imported lazily and isolated from the main config loader so a
    malformed config can't take down dotenv loading entirely.
    """
```

`hermes_cli/env_loader.py:725 @ 863e313`

```python
    if home_path == _process_hermes_home():
```

> **◇ 取舍记一笔**:这里用的是 `home_path == _process_hermes_home()`(Path 相等),
> 而 `_reapply_terminal_config_bridge` 用的是 `.resolve()` 后再比
> (`env_loader.py:550`)。同一个"是不是本进程的 home"判断,一处 resolve 一处不 resolve。
> 传入相对路径或经过 symlink 的 home 时两者会给出不同答案(前者判否 → 走独立解析,只是慢一点,
> 不影响正确性)。低危,但属于本轮"同语义两份实现"主题的一个小样本。

---

## 3. `hermes_cli/secret_prompt.py` —— 密钥怎么问

### 3.1 入口与三条分支

只有一个公开入口 `masked_secret_prompt(prompt, *, mask="*")`,内部三分支:

`hermes_cli/secret_prompt.py:56 @ 863e313`

```python
def masked_secret_prompt(prompt: str, *, mask: str = "*") -> str:
    """Prompt for a secret while showing masked typing feedback.

    Falls back to ``getpass.getpass`` when stdin/stdout are not interactive or
    when raw terminal handling is unavailable.
    """
    stdin = sys.stdin
    stdout = sys.stdout
```

**非 TTY(stdin 或 stdout 任一不是 tty)→ 直接 `getpass.getpass`**:

`hermes_cli/secret_prompt.py:65 @ 863e313`

```python
    if not _stream_is_tty(stdin) or not _stream_is_tty(stdout):
        return getpass.getpass(prompt)
```

Windows 走 `msvcrt`,POSIX 走 `termios`/`tty`;**两条都用 `except Exception: 回落 getpass`,
但显式放行 `KeyboardInterrupt` / `EOFError`**(它们是用户意图,不是"raw 模式不可用"):

`hermes_cli/secret_prompt.py:76 @ 863e313`

```python
    try:
        return _masked_secret_prompt_posix(prompt, mask=mask)
    except (KeyboardInterrupt, EOFError):
        raise
    except Exception:
        return getpass.getpass(prompt)
```

`_stream_is_tty` 连 `isatty()` 本身抛异常都当 False —— 对着被替换过 stdin 的宿主(IDE 插件、
测试 harness)是必要的:

`hermes_cli/secret_prompt.py:84 @ 863e313`

```python
def _stream_is_tty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False
```

### 3.2 输入是否回显

**不回显真值,回显掩码**。POSIX 分支把终端切进 raw 模式(关掉 ECHO 与 ICANON),
自己逐字符读、逐字符写 `*`:

`hermes_cli/secret_prompt.py:108 @ 863e313`

```python
def _masked_secret_prompt_posix(prompt: str, *, mask: str) -> str:
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
```

`hermes_cli/secret_prompt.py:122 @ 863e313`

```python
    try:
        tty.setraw(fd)
        return _collect_masked_input(read_char, write, prompt, mask=mask)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
```

`finally` + `TCSADRAIN` 保证**任何**退出路径(含 Ctrl-C)都把终端属性还回去 —— 少了这一手,
用户的 shell 会留在 raw 模式(打字看不见、回车不换行),是这类实现的经典坑。
注意 raw 模式下 `\n` 不再自动映射成 `\r\n`,所以 `_collect_masked_input` 每次结束都显式写 `"\r\n"`。

**为什么不直接用 `getpass`?** `getpass` 完全无回显,用户长密钥粘贴/输错时**一点反馈都没有**。
这个模块换来的是"能看见自己敲了几个字符"。代价见 §3.4。

**非 TTY 时的回显值得警惕**:`getpass.getpass` 在拿不到 `/dev/tty` 时会退化成
`sys.stdin.readline()` 并发 `GetPassWarning`,**此时输入是回显的**。也就是说
"管道里喂密钥"这条路上,掩码保证是不成立的(这是 CPython `getpass` 的行为,非本仓库代码)。

### 3.3 控制字符处理

`hermes_cli/secret_prompt.py:11 @ 863e313`

```python
_BACKSPACE_CHARS = {"\b", "\x7f"}
_ENTER_CHARS = {"\r", "\n"}
_EOF_CHARS = {"\x04", "\x1a"}
```

- `""`(read 返回空)→ 写 `\r\n` 后 `raise EOFError`
- `\r` / `\n` → 结束,返回
- `\x03`(Ctrl-C)→ `raise KeyboardInterrupt`(raw 模式关了 ISIG,信号不会自己来,必须手接)
- `\x04`(Ctrl-D)/ `\x1a`(Ctrl-Z)→ `EOFError`
- `\b` / `\x7f` → 退格,`write("\b \b")` 擦掉一个掩码字符

`hermes_cli/secret_prompt.py:41 @ 863e313`

```python
        if ch in _BACKSPACE_CHARS:
            if value:
                value.pop()
                write("\b \b")
            continue
```

### 3.4 ▲ 疑似 bug:ESC 序列只吞了 ESC 本身,`[A` 进了密钥

`hermes_cli/secret_prompt.py:46 @ 863e313`

```python
        if ch == "\x1b":
            # Ignore escape itself. Terminals commonly send escape-prefixed
            # navigation/delete sequences; they should not become secret text.
            continue

        value.append(ch)
```

注释说"这些导航/删除序列不该变成密钥文本",但代码**只 `continue` 掉了 `\x1b` 这一个字节**。
下一轮循环读到的 `[`、再下一轮的 `A`,都不在任何特殊集合里,于是双双 `value.append(ch)`。

**实测**(脚本见 §8):喂入 `a`、`b`、`ESC`、`[`、`A`(即一次上方向键)、`c`、回车:

```text
captured secret  = 'ab[Ac'
echoed to screen = 'pw: *****\r\n'
```

密钥被污染成 `ab[Ac`;屏幕上打了 5 个 `*` 而用户只觉得敲了 3 个字符——掩码计数是唯一(极弱)的提示。

**Windows 分支反而是对的**:它在 `read_char` 里把 `\x00`/`\xe0` 前缀的双字节序列**整个消费掉**
再返回一个 `\x1b`:

`hermes_cli/secret_prompt.py:94 @ 863e313`

```python
    def read_char() -> str:
        ch = msvcrt.getwch()
        if ch in {"\x00", "\xe0"}:
            msvcrt.getwch()
            return "\x1b"
        return ch
```

**为什么算 bug 而不是取舍**:同一个模块里两条分支对同一意图给出了不同结果,而 POSIX 分支的注释
陈述的是 Windows 分支的行为。**复核结论:确认。**
**影响面**:`masked_secret_prompt` 有 ~15 个调用点(`hermes_cli/setup.py:211`、
`model_setup_flows.py` 多处、`config.py:2290`/`2341`、`onepassword_secrets_cli.py:325`、
`memory_setup.py:95`、`cli_output.py:61`、`main.py` 4 处),都是往 `.env` 存 API key 的路径。
用户在输入密钥时按方向键(试图编辑)→ 存进 `.env` 的 key 多了 `[D` 之类的垃圾 → 表现为
provider 侧的 401 —— **与 §2.7 那个 #6843 事故的症状一模一样**,但净化那条路只管非 ASCII,`[A` 是纯 ASCII,
**兜不住**。
**测试覆盖**:`tests/hermes_cli/test_secret_prompt.py` 只有 3 个用例
(掩码回显 / KeyboardInterrupt / 非 TTY 回落 getpass),**没有任何一个覆盖 ESC 序列**。

### 3.5 值最终写到哪:**`~/.hermes/.env` 明文**,不是 keyring

`masked_secret_prompt` 只负责"问",不负责"存"。调用方拿到字符串后交给 `save_env_value`:

`hermes_cli/config.py:3865 @ 863e313`

```python
def save_env_value(key: str, value: str):
    """Save or update a value in ~/.hermes/.env."""
    if is_managed():
        managed_error(f"set {key}")
        return
```

即 **明文写 `~/.hermes/.env`**。全仓没有 keyring / Secret Service / macOS Keychain 的存储路径;
"更安全的存法"是**外部密钥源**(Bitwarden / 1Password,§2.10),但那是**读**侧的注入,
不改变 `save_env_value` 的写侧行为。写入前的处理:managed 键拒写、名字正则校验、
denylist 拒绝、剥换行符、非 ASCII 凭据剥除并告警(`config.py:3883-3888`),
落盘同样是 mkstemp + fsync + `atomic_replace` + 恢复原权限位(`config.py:3925-3943`)。

**config.yaml 里也可能有密钥**:fallback 条目支持内联 `api_key`(§4.2),
skill 声明的配置一律进 `skills.config.*` 明文(§5.3)。

### 3.6 会不会把密钥打进日志

**这个模块本身不会**:它只 `write(mask)`,从不打印 `value`。风险在调用侧——
`config.py:2297` 打的是 `✓ Saved {var['name']}`(只有名字),`skills_config` 之类的
skill 配置路径打的却是 `✓ Saved {var['key']} = {value}`(`config.py:2403`,见 §5.4)。
另有全局的 `agent.redact` 兜底(`security.redact_secrets` 默认开),对工具输出/日志/回复做脱敏。

---

## 4. `hermes_cli/fallback_config.py` —— **不是**配置兜底,是 provider 失败转移

### 4.1 ▲ 定位纠正(取证)

模块 docstring 一句话说完:

`hermes_cli/fallback_config.py:1 @ 863e313`

```python
"""Helpers for reading the effective fallback provider chain from config."""
```

它读的是 config.yaml 的 `fallback_providers` / `fallback_model` 两个键,产出一条
**"主 provider 挂了之后按序尝试哪些 provider/model"** 的链。触发条件是 429 / 529 / 503 / 连接失败
(`config.py` 生成的 config.yaml 注释块里写着 `Triggers on rate limits (429), overload (529),
service errors (503), or connection failures.`)。

调用方全部是**推理路径**,没有一个是配置加载路径:
`cli.py:4546`、`gateway/run.py:2629`/`8408`/`8459`、`cron/scheduler.py:3375`/`3486`、
`hermes_cli/oneshot.py:422`、`hermes_cli/fallback_cmd.py:39`、`agent/auxiliary_client.py:5306`、
`agent/agent_init.py:1264`、`agent/chat_completion_helpers.py:1843`。

### 4.2 `resolve_entry_api_key`:一个条目的密钥怎么来

`hermes_cli/fallback_config.py:14 @ 863e313`

```python
def resolve_entry_api_key(entry: dict[str, Any] | None) -> str | None:
    """API key for one fallback entry: inline ``api_key``, else ``key_env``.

    Mirrors the custom-provider convention (``key_env`` names the env var
    holding the key; ``api_key_env`` accepted as an alias). Returns None when
    neither yields a non-empty value, letting ``resolve_runtime_provider``
    fall through to the provider's standard credential resolution.

    ``key_env`` is resolved through ``agent.secret_scope.get_secret`` rather
    than a raw ``os.getenv`` — in a multiplexed gateway a bare env read would
    ignore the active profile's scope and can return another profile's
    credential. ``get_secret`` already implements the right fallback: it
    reads ``os.environ`` when there's no active multiplexed scope (matching
    prior single-profile behavior), and fails closed only when multiplexing
    is active with no scope installed.
    """
```

**优先级**:内联 `api_key` > `key_env`(别名 `api_key_env`)> None(交回 provider 的标准凭据解析)。

**这是本文件最值得记的一行**——它是"跨 profile 凭据隔离"的一个执行点:

`hermes_cli/fallback_config.py:37 @ 863e313`

```python
        from agent.secret_scope import get_secret

        return (get_secret(key_env) or "").strip() or None
```

与 §2.4 呼应:启动期**不**清洗凭据,凭据隔离全部靠**读时**的 `get_secret`。
本文件就是"读时"那一侧的一个实例。

### 4.3 `get_fallback_chain`:新旧两个键的归并

`hermes_cli/fallback_config.py:80 @ 863e313`

```python
def get_fallback_chain(config: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return the effective fallback chain merged across old and new config keys.

    ``fallback_providers`` remains the primary source of truth and keeps its
    order. Legacy ``fallback_model`` entries are appended afterwards unless
    they target the same provider/model/base_url route as an earlier entry.
    The returned list always contains fresh dict copies.
    """
```

`hermes_cli/fallback_config.py:93 @ 863e313`

```python
    for key in ("fallback_providers", "fallback_model"):
        for entry in _iter_fallback_entries(config.get(key)):
            identity = _entry_identity(entry)
            if identity in seen:
                continue
            seen.add(identity)
            chain.append(entry)
```

去重身份 = `(provider, model, base_url)` **全部 lower + base_url 去尾斜杠**:

`hermes_cli/fallback_config.py:72 @ 863e313`

```python
def _entry_identity(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(entry.get("provider") or "").strip().lower(),
        str(entry.get("model") or "").strip().lower(),
        _normalized_base_url(entry.get("base_url")).lower(),
    )
```

`_iter_fallback_entries` 同时接受 **dict(单条)和 list(链)** 两种形状,
并**丢弃缺 provider 或缺 model 的条目**:

`hermes_cli/fallback_config.py:43 @ 863e313`

```python
def _iter_fallback_entries(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        candidates = [raw]
    elif isinstance(raw, list):
        candidates = raw
    else:
        return []
```

这解释了为什么 `fallback_model` 在 `_EXTRA_KNOWN_ROOT_KEYS` 里被注为
`"optional single dict or chain list; omitted when disabled"`(`config.py:1856`)。

> **◇ 静默丢弃**:缺 provider/model 的条目**无声跳过**,没有 warning。用户写错一个字段
> (比如写成 `name:` 而不是 `model:`)时,fallback 链会静默变短,没有任何提示。
> 对照 `platform_toolsets` 的处理(`config.py:2261`):无效 toolset 名会显式告警,
> 理由正是"静默丢工具太难查(#38798)"。**同一类问题,两种处理规格。**

### 4.4 与 config.py 的 last-known-good:**两条完全不同的路**

任务书问"是不是同一条路"——**不是,而且没有任何调用关系**。取证:

**(a) last-known-good 在 `_load_config_impl` 的 YAML 解析异常分支里**,兜的是
"config.yaml 被改坏了,进程内还有上次成功加载的那份就继续用它":

`hermes_cli/config.py:3349 @ 863e313`

```python
                # Last-known-good fallback (port of openai/codex#31188's
                # invariant: a parse failure in a policy/config file must not
                # silently replace the effective policy with an empty/default
                # one). Falling through to DEFAULT_CONFIG here drops EVERY user
                # override — including security-critical ``approvals.deny``
                # rules, which are supposed to block commands even under yolo.
                # A long-running gateway whose user mid-edits config.yaml into
                # broken YAML would silently lose those rules on the next load.
                # Within a running process we still have the last successfully
                # loaded config — keep serving it until the file is fixed.
                # Fresh processes with no last-known-good keep the existing
                # DEFAULT_CONFIG fallback.
```

**(b) 冷进程没有 LKG 时兜的是 `DEFAULT_CONFIG`**,并把坏文件快照成 `.corrupt.<ts>.bak`(§1.8)。

**(c) `fallback_config.py` 全文没有 import `hermes_cli.config`**,不参与任何解析失败路径。

**两者唯一的交集是命名巧合 + 一处措辞**:LKG 的用户告警里把 `fallback chain` 列为"会被无视的用户覆盖"之一
(`config.py:145`的 `"(auxiliary providers, fallback chain, model settings) is being IGNORED"`)——
即 **config 兜底失败时,provider 兜底链会跟着一起失效**。这是两条路唯一的因果关联,方向是
"配置兜底 → 影响 provider 兜底",不是同一条路。

**归纳到本轮"同语义多份实现"主题**:配置面的"兜底"在这个仓库里其实有 **三**套互不相干的东西,
名字都叫 fallback:
1. `fallback_config.py` —— LLM provider 失败转移链;
2. `config.py` 的 last-known-good —— 配置解析失败的进程内保底;
3. `load_config()` 的 `DEFAULT_CONFIG` deep-merge —— 缺键时的读时保底(§1.7 那条不变式的地基)。

---

## 5. `hermes_cli/skills_config.py` —— **不是** schema,是开关菜单

### 5.1 ▲ 定位纠正 + 它管的 schema 形状

模块 docstring 把它自己的 schema 画出来了:

`hermes_cli/skills_config.py:1 @ 863e313`

```python
"""
Skills configuration for Hermes Agent.
`hermes skills` enters this module.

Toggle individual skills or categories on/off, globally or per-platform.
Config stored in ~/.hermes/config.yaml under:

  skills:
    disabled: [skill-a, skill-b]          # global disabled list
    platform_disabled:                    # per-platform overrides
      telegram: [skill-c]
      cli: []
"""
```

即它只管两个键:`skills.disabled`(全局禁用名单)与 `skills.platform_disabled.<platform>`(平台追加禁用)。

**语义是并集而非覆盖**——全局禁掉的在任何平台都禁着:

`hermes_cli/skills_config.py:44 @ 863e313`

```python
def get_disabled_skills(config: dict, platform: Optional[str] = None) -> Set[str]:
    """Return disabled skill names: the global list unioned with the
    platform-specific list when a platform is given.

    A globally-disabled skill stays disabled on every platform, so the
    platform list adds to the global list rather than replacing it. This
    mirrors ``agent.skill_utils.get_disabled_skill_names``.
    """
```

### 5.2 有没有校验

**有,但只是形状归一化,没有"这个 skill 存在吗"的校验**:

`hermes_cli/skills_config.py:27 @ 863e313`

```python
def _normalize_skill_names(values) -> Set[str]:
    """Normalize a config value into a set of skill names.

    Mirrors ``agent.skill_utils._normalize_string_set``: ``None`` (YAML null)
    means empty, a bare scalar (``disabled: my-skill``) means a single-item
    list — NOT a set of its characters (#13026).
    """
```

**事故 #13026**:`disabled: my-skill`(裸标量而非列表)被 `set(...)` 一包就变成
`{'m','y','-','s','k','i','l','l'}` —— 每个**字符**成了一个"skill 名"。修法是先把 str 包成单元素列表。

写侧只做排序落盘,不校验名字是否对应真实 skill:

`hermes_cli/skills_config.py:64 @ 863e313`

```python
def save_disabled_skills(config: dict, disabled: Set[str], platform: Optional[str] = None):
    """Persist disabled skill names to config."""
    config.setdefault("skills", {})
    if platform is None:
        config["skills"]["disabled"] = sorted(disabled)
    else:
        config["skills"].setdefault("platform_disabled", {})
        config["skills"]["platform_disabled"][platform] = sorted(disabled)
    save_config(config)
```

**敏感字段:无**。这两个键都只是 skill 名字符串,不涉及凭据。

### 5.3 真正的「skill 自带配置 schema」在哪(补齐任务书原意)

在 `agent/skill_utils.py`。skill 在 `SKILL.md` frontmatter 的 `metadata.hermes.config` 下声明:

`agent/skill_utils.py:701 @ 863e313`

```python
def extract_skill_config_vars(frontmatter: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract config variable declarations from parsed frontmatter.

    Skills declare config.yaml settings they need via::

        metadata:
          hermes:
            config:
              - key: wiki.path
                description: Path to the LLM Wiki knowledge base directory
                default: "~/wiki"
                prompt: Wiki directory path

    Returns a list of dicts with keys: ``key``, ``description``, ``default``,
    ``prompt``.  Invalid or incomplete entries are silently skipped.
    """
```

**校验**:`key` 与 `description` 二者缺一即静默跳过;同名 key 只留第一个;
`raw` 是 dict 时自动包成单元素 list(与 §5.2 同款容错);`prompt` 缺省用 `description` 顶上。
**没有类型/取值域校验,没有 `secret: true` 之类的敏感标记。**

`agent/skill_utils.py:743 @ 863e313`

```python
        entry: Dict[str, Any] = {
            "key": key,
            "description": desc,
        }
```

**存储位置**:一律加前缀落到 `skills.config.<logical_key>`:

`agent/skill_utils.py:802 @ 863e313`

```python
SKILL_CONFIG_PREFIX = "skills.config"
```

**谁来读**:`agent/skill_utils.py:817` 的 `resolve_skill_config_values`(运行时,给 skill 用),
以及 `hermes_cli/config.py:1217` 的 `get_missing_skill_config_vars`(迁移后交互补齐)。
运行时读的时候会对含 `~` 或 `${` 的字符串做 `expanduser` + `expandvars`。

### 5.4 ▲ 敏感字段的隐患:skill 配置的提示值会**明文回显 + 明文入 config.yaml**

`migrate_config` 尾部补 skill 配置时,用的是**裸 `input()` 而非 `masked_secret_prompt`**,
并且**把输入值原样打印**:

`hermes_cli/config.py:2396 @ 863e313`

```python
                value = input(f"  {var['prompt']}{default_hint}: ").strip()
                if not value and default:
                    value = str(default)
                if value:
                    storage_key = f"{SKILL_CONFIG_PREFIX}.{var['key']}"
                    _set_nested(config, storage_key, value)
                    results["config_added"].append(var["key"])
                    print(f"  ✓ Saved {var['key']} = {value}")
```

对比 §3.5 的 env 变量路径:那里靠 `OPTIONAL_ENV_VARS` 的 `password: True` 标志决定用
`masked_secret_prompt`(`config.py:2289-2290`),打印时也只打名字。
**skill 声明的配置项 schema 里根本没有 `password`/`secret` 这个字段可声明**(§5.3),
所以一个需要 API key 的 skill,其 key 必然:回显在屏幕上 → 明文打印一次 → 明文写进 `config.yaml`。
**判定:设计缺口,不是实现 bug。** 记一笔。

### 5.5 交互流与写盘的一处取舍

`hermes skills` 拿的是 `load_config()`(**默认值已 deep-merge、`${VAR}` 已展开、managed 已叠加**)
的完整 dict,改完再整份 `save_config`:

`hermes_cli/skills_config.py:154 @ 863e313`

```python
    config = load_config()
```

`hermes_cli/skills_config.py:200 @ 863e313`

```python
    save_disabled_skills(config, new_disabled, platform)
```

这正是 `_persist_migration` docstring 警告过的"整份 DEFAULT_CONFIG 回写"形状(§1.7)。
救它的是 `save_config` 自带的两道工序:`_strip_default_values` 剥默认、
`_preserve_env_ref_templates` 把展开值还原成 `${VAR}` 模板。
**能工作,但它依赖 save_config 的两个副作用,而不是自己走 `read_raw_config()` + 局部改。**
`hermes_cli/config.py:3505` 的 `save_config` docstring 对这类调用方的建议是用
`merge_existing=True`;这里既没用 `merge_existing`,也没用 `read_raw_config`。记为取舍存疑。

---

## 6. 「同一语义被实现了不止一份」清单(本轮统一主题)

### 6.1 `.env` 解析:**四份**(一份库 + 三份手写)

| # | 位置 | 用途 | `export ` 前缀 | 引号转义 | 行内注释 |
|---|---|---|---|---|---|
| A | `python-dotenv==1.2.2`(`env_loader.py:344` 调用) | 真正往 `os.environ` 灌值 | 支持 | 支持 | 剥除 |
| B | `hermes_cli/config.py:3621` `_parse_env_value` + `load_env()` | `get_env_value` / UI 读 `.env` | 支持 | 支持 | 由调用方剥 |
| C | `agent/secret_scope.py:226` `load_env_file` | 建 profile 密钥 scope(**不碰 `os.environ`**) | 支持 | **复用 B** | 剥除 |
| D | `hermes_cli/env_loader.py:86` `_env_keys_defined_in_dotenv` | 只取 key 名(bootstrap 期避免 import dotenv) | 支持 | N/A | N/A |
| E | `hermes_cli/managed_scope.py:180` `_parse_env` | managed `.env` 的**键集合**(`is_env_managed`) | **不支持** | **不支持** | **不剥** |

C 是**刻意**复用 B 的,注释写明了理由(不复用会腐蚀含 `"` 或 `\` 的凭据):

`agent/secret_scope.py:247 @ 863e313`

```python
    # Parse values with the canonical Hermes parser: save_env_value
    # escapes " and \ inside double quotes, and every other reader
    # (load_env, python-dotenv) reverses those escapes. Stripping only
    # the outer quotes here would corrupt credentials containing "
    # or \ — they work interactively but fail in scoped (cron /
    # multiplex) resolution.
    from hermes_cli.config import _parse_env_value
```

**E 没跟上这条约定**:

`hermes_cli/managed_scope.py:180 @ 863e313`

```python
def _parse_env(f) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip("\"'")
    return out
```

**三方实测对比**(同一份 `.env` 内容 `export FOO=bar` / `BAZ="a\"b"` / `QUX=val # note`,脚本见 §8):

```text
managed_scope._parse_env  -> {'export FOO': 'bar', 'BAZ': 'a\\"b', 'QUX': 'val # note'}
python-dotenv             -> {'FOO': 'bar', 'BAZ': 'a"b', 'QUX': 'val'}
secret_scope.load_env_file-> {'FOO': 'bar', 'BAZ': 'a"b', 'QUX': 'val'}
```

**具体后果**:**同一个 managed `.env` 文件在同一个进程里被两个不同的解析器读**——
python-dotenv 负责往 `os.environ` 灌(`env_loader.py:588`),`_parse_env` 负责回答
"这个键是不是 admin 钉的"(`managed_scope.py:133`)。管理员写了 `export OPENAI_API_KEY=...` 时:

- 灌值这一侧**正确**:`OPENAI_API_KEY` 以 `override=True` 落进 `os.environ`,admin 的钉子生效。
- 判定这一侧**错误**:`load_managed_env()` 返回的键是 `"export OPENAI_API_KEY"`,于是
  `is_env_managed("OPENAI_API_KEY")` → False。

由此:
1. `save_env_value("OPENAI_API_KEY", ...)` 的 managed 守卫**不触发**,用户能写进自己的 `.env`
   且不报错(`config.py:3874`);下次启动 managed 仍然覆盖它,所以**钉子没被绕过,但用户被误导**
   ——他会以为自己设成功了。
2. `hermes config` 的管理员提示会打印字面 `Managed env keys: export OPENAI_API_KEY`
   (`config.py:4279`)。
3. `hermes doctor` 的 managed 条目计数(`doctor.py:699`)偏差。

**复核结论:确认(低-中危,是 UX/一致性缺陷而非安全绕过)。** 修法是 E 直接复用 C/B。

### 6.2 skill 禁用名单:**两份**,而且**配置来源不同**

`hermes_cli/skills_config.py` 的两个函数 docstring 都自认"mirrors" `agent/skill_utils.py`:

`hermes_cli/skills_config.py:58 @ 863e313`

```python
    platform_disabled = cfg_get(skills_cfg, "platform_disabled", platform)
    if platform_disabled is None:
        return global_disabled
    return global_disabled | _normalize_skill_names(platform_disabled)
```

`agent/skill_utils.py:466 @ 863e313`

```python
        platform_disabled = (skills_cfg.get("platform_disabled") or {}).get(
            resolved_platform
        )
        if platform_disabled is not None:
            return global_disabled | _normalize_string_set(platform_disabled)
```

**三处实质差异**:

1. **配置来源不同(最重要)**。CLI 侧吃的是调用方传进来的、来自 `load_config()` 的 dict
   (默认值已 merge、`${VAR}` 已展开、**managed overlay 已叠加**);运行时侧走自己的裸 YAML 读:

   `agent/skill_utils.py:450 @ 863e313`

   ```python
   parsed = _load_raw_config()
   ```

   `agent/skill_utils.py:401 @ 863e313`

   ```python
   def _load_raw_config() -> Dict[str, Any]:
       """Read config.yaml with a shared mtime+size keyed cache.

       This module intentionally avoids importing ``hermes_cli.config`` on the
       skill prompt/build path. A tiny local cache gives the same repeated-read
       win without pulling the heavier CLI config stack into startup.
       """
   ```

   **推论**:管理员在 managed config 里钉 `skills.disabled`,`hermes skills` 菜单会显示它禁用了,
   **但运行时的 skill 加载器看不到**(它只读用户的 config.yaml)。同理 `skills.disabled` 里写
   `${SOME_VAR}` 这种引用,CLI 侧展开、运行时侧不展开。**判定:存疑偏确认**,
   我没有为 managed + skills 这一组合找到测试或文档;主线若要写进报告,建议标为"需再取证一次"。

2. **异常安全**。CLI 侧包了 `try/except TypeError`,运行时侧裸奔:

   `hermes_cli/skills_config.py:38 @ 863e313`

   ```python
       try:
           return {str(v).strip() for v in values if str(v).strip()}
       except TypeError:
           return set()
   ```

   `agent/skill_utils.py:474 @ 863e313`

   ```python
   def _normalize_string_set(values) -> Set[str]:
       if values is None:
           return set()
       if isinstance(values, str):
           values = [values]
       return {str(v).strip() for v in values if str(v).strip()}
   ```

   用户写 `skills: {disabled: 42}`(不可迭代)→ CLI 菜单当空集正常开;
   运行时 `get_disabled_skill_names()` **抛 `TypeError`**。

3. **平台解析**。CLI 侧要求调用方显式传 platform;运行时侧自己从 `HERMES_PLATFORM` /
   `HERMES_SESSION_PLATFORM` 解析(`skill_utils.py:458-463`),还要 import
   `gateway.session_context`。

### 6.3 「Hermes 认识哪些 env 键」:两份,一份是死的

见 §2.8:`env_loader.py:55`(死)与 `config.py:4095`(活)。

### 6.4 「这是不是本进程的 HERMES_HOME」:两份,一处 resolve 一处不 resolve

见 §2.11 末尾:`env_loader.py:725` vs `env_loader.py:550`,**同一个文件内**。

### 6.5 「fallback」这个词的三种互不相干的含义

见 §4.4。

---

## 7. 发现清单

> 格式:一句话症状 + 锚点 + 复核结论。

**F1 · 迁移报告"已添加"、磁盘上什么都没加(v15 / v23)**
`hermes_cli/config_migrations.py:231`(v15)、`hermes_cli/config_migrations.py:383`(v23)。
两条迁移写入的值**恰好等于 `DEFAULT_CONFIG`**,而 `_persist_migration`(`hermes_cli/config.py:2124`)
的不变式就是"只准写与默认不同的值",`_strip_default_values`(`config.py:2698`)把它们整段剥掉。
v23 自述的目的第 1、2 条("让用户在 config.yaml 里看得见/改得动 curator 设置")100% 落空。
**复核:确认(已实测,§1.7 有前后对比输出)。**

**F2 · 迁移跑完但 `_config_version` 不前进的可达窗口**
`hermes_cli/config.py:2283`(无 try/except 的 `input()`)与 `hermes_cli/config.py:2365`(版本 bump)。
bump 在两段交互式输入**之后**,用户 Ctrl-C 或管道 EOF → step 已落盘、版本停在旧值 → 下次全表重跑。
逐条核过:除 v15/v23 外所有 step 重跑都是 no-op;**F1 恰好让 v15/v23 的守卫永远为真**,
于是产生"每次启动都说加了、永远没加上"的复合现象。
**复核:确认(静态可达性推理 + F1 实测);单独看低危,与 F1 叠加才有可见症状。**

**F3 · POSIX 掩码输入把方向键的 `[A` 吞进密钥**
`hermes_cli/secret_prompt.py:46`。注释声称过滤 escape-prefixed 序列,代码只 `continue` 掉 `\x1b` 本身。
同文件 Windows 分支(`secret_prompt.py:94`)整段消费双字节序列,行为正确 → 两条分支不一致。
`tests/hermes_cli/test_secret_prompt.py` 三个用例均未覆盖。症状与 #6843 的非 ASCII 污染同形
(provider 侧 401),但 §2.7 的 ASCII 净化**兜不住**(`[A` 是纯 ASCII)。
**复核:确认(已实测:输入 `ab`+↑+`c` → 得到 `'ab[Ac'`)。**

**F4 · managed `.env` 被两个不同解析器读,`export`/引号/行内注释三种写法全部分叉**
`hermes_cli/managed_scope.py:180`(手写弱解析器,给 `is_env_managed`)vs
`hermes_cli/env_loader.py:588`(python-dotenv,给 `os.environ`)。
管理员写 `export KEY=v`:钉子在 env 层生效,但 `is_env_managed("KEY")` 返回 False,于是
`save_env_value`(`config.py:3874`)不报"管理员已锁定"、`hermes config`(`config.py:4279`)
打印字面 `export KEY`、`doctor.py:699` 计数偏差。
**复核:确认(三方解析器实测对比,§6.1)。低-中危:是 UX/一致性缺陷,不是权限绕过。**

**F5 · 注释与代码不符:floor 闸门位置**
`hermes_cli/config_migrations.py:653` 说闸门在 `run_migrations()` 里,实际在
`hermes_cli/config.py:2196`;`config.py:2181` 的注释说对了。同一件事两处注释互相矛盾。
**复核:确认(纯注释错误,无行为影响)。**

**F6 · 注释与代码不符:`verify_on_stop` 的"新默认值"**
`hermes_cli/config_migrations.py:539` 的注释写 "The new default is OFF",但
`hermes_cli/config_defaults.py:158` 至今是 `"verify_on_stop": "auto"`。
后果是**老用户被迁移写死 `false`,全新安装拿到 `"auto"`(交互式编码界面仍开启)**——
同一版本的两拨用户行为不同。§8 实测里 `verify_on_stop: false` 能落盘,正说明默认值确实还不是 false。
**复核:确认(行为分叉真实存在;是否"有意"无法从代码判定,但注释与默认值确实冲突)。**

**F7 · 死代码 `_known_hermes_env_keys`**
`hermes_cli/env_loader.py:55`,全仓零调用。同一"并集"逻辑活在 `hermes_cli/config.py:4095`。
从 `env_loader.py:114` 的注释可推断这是"全量清洗"版本收窄成 `_PROFILE_MANAGED_ENV_KEYS` 后的遗留。
**复核:确认(grep 全仓仅命中定义行)。无害,但属"同语义两份实现"样本。**

**F8 · skill 声明的配置项无法标记为密钥,必然明文回显 + 明文入 config.yaml**
schema 见 `agent/skill_utils.py:701`(只有 `key`/`description`/`default`/`prompt`,
**没有 `password`/`secret`**);交互补齐处 `hermes_cli/config.py:2396` 用裸 `input()`
且 `print(f"  ✓ Saved {var['key']} = {value}")` 原样回显。
对照 env 变量路径:`OPTIONAL_ENV_VARS` 有 `password: True`(`config_defaults.py:3144` 等),
走 `masked_secret_prompt`(`config.py:2290`)且只打名字。
**复核:确认(设计缺口,非实现 bug)。**

**F9 · skill 禁用名单两份实现,配置来源不同(managed / `${VAR}` 只对 CLI 生效)**
`hermes_cli/skills_config.py:44`(吃 `load_config()` 的结果:默认已 merge、`${VAR}` 已展开、
managed 已叠加)vs `agent/skill_utils.py:436` → `agent/skill_utils.py:401`(裸 YAML,三者皆无)。
另有异常安全差异:`skills_config.py:39` 有 `except TypeError`,`skill_utils.py:474` 没有,
`skills: {disabled: 42}` 会让运行时抛 `TypeError` 而 CLI 菜单正常。
**复核:异常安全差异 = 确认;managed/`${VAR}` 不生效 = 存疑(推理成立,未找到测试或文档佐证,
建议主线若采用则再取证一次)。**

**F10 · fallback 链条目静默丢弃,与 platform_toolsets 的处理规格不一致**
`hermes_cli/fallback_config.py:43`:缺 `provider` 或缺 `model` 的条目无声跳过,无 warning。
对照 `hermes_cli/config.py:2261`:无效 toolset 名会显式告警,理由正是"静默丢工具太难查(#38798)"。
**复核:确认(行为如此);是否算缺陷取决于产品判断,记为取舍。**

**F11 · config.yaml 解析失败时迁移被静默跳过**
`hermes_cli/config.py:1813` 的 `check_config_version()` 在 YAML 解析失败时返回 `(latest, latest)`,
于是 `run_migrations` 一步不跑、版本也不 bump,但**用户只看到"YAML 解析失败",看不到"迁移被跳过了"**。
**复核:确认(是 fail-safe 设计的必然结果,记为取舍而非 bug)。**

**F12 · 迁移无事务、无迁移前备份、每步各自落盘**
`hermes_cli/config_migrations.py:683` 的驱动逐条调用,每个 step 自己 `_persist_migration`;
`utils.py:335` 的 `atomic_yaml_write` 只保证**单次写**原子,不保证**整条链**原子。
全仓唯一的 `.bak` 是解析失败时的取证快照(`hermes_cli/config.py:45`),与迁移无关。
一条 12→33 的升级路径中途异常会停在半路,且没有回滚点。
**复核:确认(记为取舍:step 幂等性 + 读时 deep-merge 被当成了事务的替代品)。**

**F13 · `_CREDENTIAL_SUFFIXES` 的 `_KEY` 是超集,净化范围宽于"凭据"**
`hermes_cli/env_loader.py:20`。任何以 `_KEY` 结尾的 env var(如 `SOME_PUBLIC_KEY`、
`SORT_KEY`)都会被剥非 ASCII 并告警,而模块注释明确说"我们不能随便改用户的任意 env var"。
**复核:确认(极低危,范围与注释声明的克制原则有轻微出入)。**

**F14 · `hermes skills` 整份回写 `load_config()` 的结果**
`hermes_cli/skills_config.py:154` + `hermes_cli/skills_config.py:200` → `save_config(config)`。
这正是 `_persist_migration` docstring(`hermes_cli/config.py:2124`)警告过的
"整份 DEFAULT_CONFIG 回写"形状;靠 `save_config` 的 `_strip_default_values` +
`_preserve_env_ref_templates` 两个副作用救回来,而不是自己走 `read_raw_config()` + 局部改,
也没用 `save_config(..., merge_existing=True)`。
**复核:存疑(当前能工作,未观察到实际损坏;记为脆弱耦合)。**

---

## 8. 复现脚本(全部在临时目录跑,零写入基线)

**8.1 F1 / F6 的迁移落盘实测**

```python
# scratchpad/exp_mig.py
import os, sys, tempfile, pathlib, shutil
home = pathlib.Path(tempfile.mkdtemp(prefix="hh_"))
os.environ["HERMES_HOME"] = str(home)
(home / "config.yaml").write_text("_config_version: 14\nmodel:\n  default: openai/gpt-4o\n", encoding="utf-8")
(home / ".env").write_text("", encoding="utf-8")
sys.path.insert(0, "/home/user/hermes-agent")
from hermes_cli import config as C
res = C.migrate_config(interactive=False, quiet=True)
print(res["config_added"])
print((home / "config.yaml").read_text(encoding="utf-8"))
shutil.rmtree(home, ignore_errors=True)
```

运行:`cd /tmp && PYTHONDONTWRITEBYTECODE=1 /home/user/hermes-venv/bin/python <脚本>`。
输出见 §1.7。

**8.2 F3 的 ESC 序列实测**

```python
# scratchpad/exp_esc.py
import sys
sys.path.insert(0, "/home/user/hermes-agent")
from hermes_cli.secret_prompt import _collect_masked_input
seq = list("ab") + ["\x1b", "[", "A"] + ["c"] + ["\r"]
it = iter(seq); out = []
print(repr(_collect_masked_input(lambda: next(it), out.append, "pw: ")))
print(repr("".join(out)))
```

输出:`'ab[Ac'` / `'pw: *****\r\n'`。

**8.3 F4 的三方解析器对比**

```python
# scratchpad/exp_managed.py
import sys, io, tempfile, pathlib, dotenv
sys.path.insert(0, "/home/user/hermes-agent")
from hermes_cli.managed_scope import _parse_env
from agent.secret_scope import load_env_file
sample = 'export FOO=bar\nBAZ="a\\"b"\nQUX=val # note\n'
print(_parse_env(io.StringIO(sample)))
d = pathlib.Path(tempfile.mkdtemp()); (d/".env").write_text(sample, encoding="utf-8")
print(dict(dotenv.dotenv_values(d/".env")))
print(load_env_file(d/".env"))
```

输出见 §6.1。

**基线洁净性**:三次实验全程 `HERMES_HOME` 指向 `tempfile.mkdtemp()`,
只 import 基线代码不写入;每次实验后 `git -C /home/user/hermes-agent status --porcelain` 均为空。

---

## 9. 给成品章的素材提要

- **最好的"先场景后机制"开场**:§2.7 的 #6843(从 PDF 复制 API key,肉眼看不出的 Unicode 相似字形,
  报出来的是 provider 的 "invalid API key")——它一句话讲清了"为什么 env 加载器要管编码"。
- **第二好的场景**:§2.3 末尾的 #29186/#67323(config.yaml 改了 terminal 后端,长驻网关跑着跑着
  又翻回 `.env` 里的旧值)——它把"覆盖顺序"这件抽象事演成了故事。
- **最适合讲"设计原则"的一条**:§2.2 —— 加载顺序保证不了时,不要硬排顺序,
  而要把"我是在哪个环境下算出这个值的"一起缓存,让下游能自己发现读早了。
- **最适合讲"取舍"的一条**:§1.7 的写入不变式 —— "只写与默认不同的值"是个好规则
  (救了手写配置不被 DEFAULT_CONFIG 灌满),但它和"迁移要把新段落写出来给用户看"直接冲突,
  仓库选了前者且没人发现后者被吃掉了。
