# r8a-raw-migrations-env-secrets · config_migrations / env_loader / secret_prompt / skills_config / fallback_config / subcommands.config

> 底稿。求全求证,不求好读。所有断言溯源到 `路径:行号 @ 863e313`,路径相对
> `/home/user/hermes-agent`。本段精读六个文件全文:
> `hermes_cli/config_migrations.py`(685)、`hermes_cli/env_loader.py`(752)、
> `hermes_cli/secret_prompt.py`(126)、`hermes_cli/skills_config.py`(202)、
> `hermes_cli/fallback_config.py`(101)、`hermes_cli/subcommands/config.py`(68)。
> 为讲清机制,附带读了 `hermes_cli/config.py`、`hermes_cli/config_defaults.py`、
> `hermes_constants.py`、`agent/secret_scope.py`、`agent/secret_sources/registry.py`、
> `agent/verification_stop.py`、`hermes_cli/managed_scope.py`、`hermes_cli/update_cmd.py`
> 的相关片段。

---

## 0. 这一簇在系统里的位置

六个文件是「配置层的边角料」,但每一个都卡在启动路径上:

- `config_migrations.py` —— **磁盘 schema 演进**。config.yaml 有一个整数版本号,
  版本落后就跑一串升级函数。
- `env_loader.py` —— **进程启动时把 .env / 外部密钥库灌进 `os.environ`**。
  这是整个 harness 唯一的凭据入口。
- `secret_prompt.py` —— **交互式输密码**,给 setup / migrate 用。
- `skills_config.py` —— `hermes skills` 的开关持久化(config.yaml 的 `skills.*`)。
- `fallback_config.py` —— 把两代 fallback 配置键合并成一条链。
- `subcommands/config.py` —— `hermes config` 的 argparse 定义(纯声明,无逻辑)。

---

## 1. config_migrations.py —— 表驱动的 schema 迁移

### 1.1 解决什么问题

config.yaml 是用户手写 + 向导生成的混合物,长期演进中键名会改、语义会翻转、
旧键会废弃。作者选择了「**磁盘上刻一个整数 schema 版本号,每次破坏性变更 +1,
启动/更新时把落后的配置逐版本推到最新**」这条经典路线。

模块 docstring 明说了这份代码的来历:它原本是 `migrate_config` 里一段 768 行的
`if current_ver < N:` 阶梯,本次重构只是把每一块搬成函数,骨架(版本闸门 + 严格
升序)抽到 `run_migrations`。`hermes_cli/config_migrations.py:1-8 @ 863e313`

```python
"""Table-driven config migration registry.

This module holds the per-version migration steps that used to live as a
768-line ladder of ``if current_ver < N:`` blocks inside
``hermes_cli.config.migrate_config``. Each step is a function
``_migrate_to_N(results, quiet)`` whose body is copied verbatim from the
original block; only the shared skeleton (the version gate and the strict
ascending ordering) lives in the :func:`run_migrations` driver.
```

### 1.2 版本号存在哪个键里?当前最高版本是多少?

**键名是根级 `_config_version`**(下划线前缀 = 内部键)。最高版本由
`DEFAULT_CONFIG` 里的字面量给出,当前是 **33**。
`hermes_cli/config_defaults.py:3126 @ 863e313`

```python
    "_config_version": 33,
```

「磁盘上的当前版本」不能用 `load_config()` 读,因为 `load_config()` 会把
`DEFAULT_CONFIG` deep-merge 进去,一个**没有** `_config_version` 的旧文件会在内存里
凭空继承 33。所以有一个专门的原始读取函数。`hermes_cli/config.py:1813 @ 863e313`

```python
def check_config_version() -> Tuple[int, int]:
```

它先算 latest,再直接 `fast_safe_load` 原始文件。`hermes_cli/config.py:1825 @ 863e313`

```python
    latest = _coerce_config_version(DEFAULT_CONFIG.get("_config_version", 1)) or 1
```

**配置文件不存在时,直接返回 `(latest, latest)`** —— 即「全新安装不需要迁移」。
`hermes_cli/config.py:1827-1828 @ 863e313`

```python
    if not config_path.exists():
        return latest, latest
```

**YAML 解析失败也返回 `(latest, latest)`**,即坏文件不迁移、不重写,只在 stderr 告警。
`hermes_cli/config.py:1833-1837 @ 863e313`

```python
    except Exception as e:
        # Invalid YAML needs a parse warning, not an automatic schema rewrite
        # that could replace the user's broken file with defaults.
        _warn_config_parse_failure(config_path, e)
        return latest, latest
```

版本号的类型强制:非 int / bool / 负数都归零(= 远古配置)。
`hermes_cli/config.py:1783 @ 863e313`

```python
def _coerce_config_version(value: Any) -> int:
```

bool 被特判成 0。`hermes_cli/config.py:1785-1786 @ 863e313`

```python
    if isinstance(value, bool):
        return 0
```

> 注意 `bool` 特判的必要性:Python 里 `int(True) == 1`,不特判的话
> `_config_version: true` 会被当成 v1 而不是「非法」。

### 1.3 `support_floor_message`(:56)是干什么的

**它是「支持底线」政策的用户可见文案**。政策本身是一个常量:低于 v12 的配置
**不再自动迁移**。`hermes_cli/config_migrations.py:53 @ 863e313`

```python
SUPPORT_FLOOR_VERSION = 12
```

理由写在常量上方的注释里:v12 往前是大约两年的发行版,继续携带 <12 的迁移步骤
(以及它们消费的 env 桥,如 `HERMES_TOOL_PROGRESS*`)不值得;被拒的配置**字节不动**,
进程带着「读时 deep-merge 默认值」的配置继续跑。
`hermes_cli/config_migrations.py:43-52 @ 863e313`

```python
#: Auto-migration support floor. Configs whose on-disk ``_config_version`` is
#: below this are NOT auto-migrated any more (policy decision, July 2026):
#: v12 predates roughly two years of releases, and carrying the sub-v12
#: migration steps (plus the env bridges they consumed, e.g.
#: HERMES_TOOL_PROGRESS*) forever is not worth it. Below-floor configs are
#: left byte-for-byte untouched — the process continues with the config as-is
#: (defaults deep-merged at read time, matching the non-fatal posture used
#: for unparseable configs) and a clear message tells the user how to
#: proceed. The removed steps were the <12 targets: v4 (tool-progress .env →
#: config.yaml), v5 (timezone seed), v9 (clear ANTHROPIC_TOKEN).
```

文案函数本体:`hermes_cli/config_migrations.py:56 @ 863e313`

```python
def support_floor_message() -> str:
```

它 **lazy import** `display_hermes_home`,把当前 profile 的 home 路径显示成 `~/.hermes`
这种可读形式,并给出两条出路:备份 + `hermes setup` 重生成,或手工把
`_config_version` 改成 12。`hermes_cli/config_migrations.py:58-66 @ 863e313`

```python
    from hermes_constants import display_hermes_home

    return (
        f"This config predates version {SUPPORT_FLOOR_VERSION} (~2 years old) "
        "and can no longer be auto-migrated. Back up "
        f"{display_hermes_home()}/config.yaml and run `hermes setup` to "
        f"regenerate, or manually set _config_version: {SUPPORT_FLOOR_VERSION} "
        "after reviewing the changelog."
    )
```

**底线闸门不在这个模块里**,而在调用方 `migrate_config`。三个条件同时成立才拒绝:
配置里**显式**写了 `_config_version`、该值 < 12、且 < latest。
`hermes_cli/config.py:2196-2201 @ 863e313`

```python
    _explicit_version = _raw_config_has_explicit_version()
    floor_refused = (
        _explicit_version
        and current_ver < SUPPORT_FLOOR_VERSION
        and current_ver < latest_ver
    )
```

「显式」的判定单独走一次原始解析,只看键在不在。`hermes_cli/config.py:1794 @ 863e313`

```python
def _raw_config_has_explicit_version() -> bool:
```

判定的返回语句。`hermes_cli/config.py:1810 @ 863e313`

```python
    return isinstance(raw, dict) and "_config_version" in raw
```

**为什么要区分「显式旧版本」和「压根没有版本键」**:profile 克隆会写出只有几个键的
裸配置,用户也会手写两行的 config.yaml —— 这些是新配置而不是远古安装,不能被拒。
`hermes_cli/config.py:2184-2189 @ 863e313`

```python
    # A config with NO ``_config_version`` key at all is NOT floor-refused:
    # that shape is a fresh minimal config (profile clones write bare keys;
    # users hand-write two-line configs), not an ancient install. Those get
    # the normal ladder (the retired <12 steps were no-ops for configs
    # lacking the legacy keys they migrated) and a fresh version stamp —
    # the historical behavior.
```

被拒时的处理:写进 `results["warnings"]`、往 stderr 写一行(即使 quiet 也可见)、
非 quiet 再往 stdout 写一行,然后**跳过整条阶梯**。`hermes_cli/config.py:2202-2209 @ 863e313`

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

**推论(重要)**:因为「显式 v11 及以下」会被拒,`_migrate_to_12` 这一步**只对
「完全没有 `_config_version` 键」的配置生效**(那时 `current_ver == 0`)。
对任何显式标了 v1..v11 的真·旧配置,v12 迁移永远跑不到。这是底线政策的一个
未在注释里点破的副作用。

### 1.4 `run_migrations`(:671)怎么调度

驱动极简:遍历升序表,`current_ver < target` 就调。`hermes_cli/config_migrations.py:671 @ 863e313`

```python
def run_migrations(current_ver: int, results: Dict[str, Any], quiet: bool) -> None:
```

循环本体只有三行。`hermes_cli/config_migrations.py:683-685 @ 863e313`

```python
    for target_ver, migration_fn in MIGRATIONS:
        if current_ver < target_ver:
            migration_fn(results, quiet)
```

三个语义点,docstring 和注释都强调了:

**(a) `current_ver` 只算一次,阶梯运行期间不推进。** 每一步都跟同一个初值比,
完全复刻原来的顺序 `if` 块。`hermes_cli/config_migrations.py:672-681 @ 863e313`

```python
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

**(b) 步骤之间通过文件系统通信。** 每一步自己 `read_raw_config()`、自己
`_persist_migration()` 落盘,所以后一步能看到前一步的写入 —— 这就是为什么
严格升序是强制的。`hermes_cli/config_migrations.py:647-650 @ 863e313`

```python
#: Registry of (target_version, migration_fn), strictly ascending. The driver
#: applies every entry whose target version is greater than the on-disk
#: version captured before the ladder started. Order matters: later steps may
#: observe earlier steps' writes via read_raw_config() (filesystem state).
```

**(c) 反循环导入 + 可 monkeypatch。** 模块级**没有** `import hermes_cli.config`;
每个步骤在调用时通过 `_cfg()` 拿到活的模块对象再取属性。
`hermes_cli/config_migrations.py:69 @ 863e313`

```python
def _cfg():
```

函数体就是一次 lazy import。`hermes_cli/config_migrations.py:71-73 @ 863e313`

```python
    from hermes_cli import config

    return config
```

docstring 点明第二个动机:测试 `patch("hermes_cli.config.read_raw_config", ...)`
仍然生效,因为步骤走的是模块属性而不是早绑定的引用。
`hermes_cli/config_migrations.py:30-35 @ 863e313`

```python
:func:`_cfg`. There is deliberately NO module-level import of
``hermes_cli.config`` here, so no circular import can form — and, just as
importantly, tests that monkeypatch helpers on ``hermes_cli.config`` (e.g.
``patch("hermes_cli.config.read_raw_config", ...)``) keep working, because
the steps always go through the module attribute rather than a bound-early
reference.
```

调用方在 `migrate_config` 里也是 lazy import。`hermes_cli/config.py:2190-2194 @ 863e313`

```python
    from hermes_cli.config_migrations import (
        SUPPORT_FLOOR_VERSION,
        run_migrations,
        support_floor_message,
    )
```

### 1.5 为什么函数名里的版本号不连续(12,13,14,15,16,17,21,23,25,29,31,32,33)

**两个不同的原因,不要混为一谈:**

**原因 A:低于底线的步骤被删掉了。** 原来存在 v4 / v5 / v9 三步,随 v12 底线政策
一起移除(见 1.3 引用的 :43-52)。所以 12 以下整段消失。

**原因 B:很多版本号只是「默认值变了」,没有数据要搬。** 因为
`load_config()` 读时 deep-merge `DEFAULT_CONFIG`,新增一个默认键根本不需要写盘,
版本号 +1 只是为了让「N 个新选项可用」的提示能算出来。仓库里给出了一个**明写**的
例子:v29→v30 的 `curator.consolidate` 改默认,注释写了一整段解释为什么**没有**
注册表条目。`hermes_cli/config_migrations.py:528-536 @ 863e313`

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

缺的号码:18、19、20、22、24、26、27、28、30。除 30 之外,基线里**没有**留下解释
它们各自代表什么变更的注释 —— **未确证**:我在 `hermes_cli/` 全仓 grep 过
`_migrate_to_18` 等名字和 `Version 17 → 18` 之类注释,没有命中;
`ENV_VARS_BY_VERSION` 也只覆盖到 11。所以只能说「按 v30 的先例,它们是无迁移的
版本号跳变」,不能逐个坐实。

注册表本体:`hermes_cli/config_migrations.py:651 @ 863e313`

```python
MIGRATIONS: Tuple[Tuple[int, Callable[[Dict[str, Any], bool], None]], ...] = (
```

第一条目就是 v12。`hermes_cli/config_migrations.py:655 @ 863e313`

```python
    (12, _migrate_to_12),
```

注册表开头的注释再次强调「刚好 v12 的配置仍然跑下面所有步骤,只有 <12 被闸门拒」。
`hermes_cli/config_migrations.py:652-654 @ 863e313`

```python
    # v12 is the support floor: configs already AT v12 (or newer) still get
    # every remaining step below. Only configs BELOW 12 are refused by the
    # floor gate in run_migrations().
```

> **可疑之处**:这条注释说闸门 "in run_migrations()",但闸门实际在
> `hermes_cli/config.py:2197` 的 `migrate_config` 里,`run_migrations` 是一个不含
> 闸门的纯机制。`migrate_config` 自己的注释(config.py:2180-2182)反而说清了
> 「闸门放在 wrapper 里,让驱动保持纯机制」。注释与注释互相矛盾,以代码为准。

### 1.6 迁移失败会怎样?会不会备份?

**不备份。** `_persist_migration` 是 `save_config(config)` 的一层薄包装,没有任何
`.bak` / 快照动作。`hermes_cli/config.py:2124 @ 863e313`

```python
def _persist_migration(config: Dict[str, Any]) -> None:
```

函数体只有一行。`hermes_cli/config.py:2147 @ 863e313`

```python
    save_config(config)
```

它存在的唯一理由是**把「迁移写盘不变量」集中在一处**:迁移只能持久化与当前
schema 默认值**不同**的值,加上对用户数据的显式删除/改名;纯默认值绝不落盘。
`hermes_cli/config.py:2127-2135 @ 863e313`

```python
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

机制在 `save_config`:`strip_defaults` 默认 True,`preserve_keys` 里恒含
`_config_version`,再并入「用户原始文件里实际写过的路径」。
`hermes_cli/config.py:3580 @ 863e313`

```python
        effective_preserve_keys: Set[Tuple[str, ...]] = {("_config_version",)}
```

剥离默认值的开关。`hermes_cli/config.py:3586 @ 863e313`

```python
        if strip_defaults and effective_preserve_keys:
```

「用户实际写过的路径」由 `_explicit_config_paths` 从**原始** raw 配置算出。
`hermes_cli/config.py:2673 @ 863e313`

```python
def _explicit_config_paths(config: Dict[str, Any]) -> Set[Tuple[str, ...]]:
```

> **实践后果(重要且不直观)**:一个迁移写入的值,如果恰好等于当前默认值、
> 且用户原文件里没有该路径,**会被 strip 掉,等于没写**。见 1.7 里 v15/v23 的分析。

**失败会怎样:** `run_migrations` 没有 try/except,`migrate_config` 调它时也没有。
`hermes_cli/config.py:2218 @ 863e313`

```python
        run_migrations(current_ver, results, quiet)
```

后果链:

1. **版本号不会被打上** —— 版本戳在函数末尾、且要求 `not floor_refused`,
   抛异常就到不了。`hermes_cli/config.py:2365-2368 @ 863e313`

```python
    if current_ver < latest_ver and not floor_refused:
        config = read_raw_config()
        config["_config_version"] = latest_ver
        _persist_migration(config)
```

2. **但是已跑完的步骤已经各自落盘了**,配置处于「部分迁移 + 旧版本号」的状态。
   下次再跑会从同一个旧 `current_ver` 重头来一遍 —— 所以**每个步骤都必须幂等**。
   代码里确实到处是 `if "enabled" not in plugins_cfg` / `if "model" in raw_stt`
   这类前置存在性判断,就是为这个。

3. 调用方各自决定要不要吞。`hermes update` 的一条路径吞掉并提示重试:
   `hermes_cli/update_cmd.py:4485-4490 @ 863e313`

```python
            try:
                migrate_config(interactive=False, quiet=True)
                print("  ✓ Config format updated (no new settings to configure)")
            except Exception as _mig_err:
                print(f"  ⚠️  Config format update failed: {_mig_err}")
                print("     Run 'hermes config migrate' to retry.")
```

   profile 创建路径整体吞掉:`hermes_cli/profiles.py:535-539 @ 863e313`

```python
    except Exception:
        # Profile creation should not fail because an old copied config could
        # not be migrated. The next `hermes doctor --fix` can still surface the
        # detailed error in the target profile.
        pass
```

**唯一的"备份"来自 `hermes update`,不是迁移本身**:更新前有一个受
`updates.pre_update_backup`(默认 `"quick"`)控制的快照,快照里含 config。
`hermes_cli/update_cmd.py:2550 @ 863e313`

```python
def _run_pre_update_backup(args) -> Optional[str]:
```

默认值。`hermes_cli/config_defaults.py:2765 @ 863e313`

```python
        "pre_update_backup": "quick",
```

而且历史上确实出过「迁移把 cron/jobs.json 清空」的事故,以致于更新流程里加了
一个事后对比恢复的安全网。`hermes_cli/update_cmd.py:4575-4580 @ 863e313`

```python
        # Safety net: config-version migrations have been observed to leave
        # cron/jobs.json valid-but-empty, silently dropping every scheduled
        # job (issue #34600). The desktop scheduler can also overwrite with
        # its own small set, causing partial loss (issue #52144). If the
        # live file now has fewer jobs than the pre-update snapshot, restore
        # it and warn loudly.
```

### 1.7 逐个 `_migrate_to_NN`

以下每条:**改了什么键 / 为什么 / 值得注意的点**。

---

#### v11 → 12:`custom_providers`(list)→ `providers`(dict)

`hermes_cli/config_migrations.py:76 @ 863e313`

```python
def _migrate_to_12(results: Dict[str, Any], quiet: bool) -> None:
```

读旧 list,逐条生成 kebab-case 的 key。URL 取三个别名里第一个非空的
(`base_url` / `url` / `api`),没 URL 就跳过。
`hermes_cli/config_migrations.py:94 @ 863e313`

```python
            old_url = entry.get("base_url", "") or entry.get("url", "") or entry.get("api", "") or ""
```

key 生成:小写、空格→连字符、去括号、压缩连续连字符、去首尾连字符。
`hermes_cli/config_migrations.py:99 @ 863e313`

```python
            key = old_name.strip().lower().replace(" ", "-").replace("(", "").replace(")", "")
```

名字为空导致 key 为空时,回退到 URL 主机名(点→连字符),再失败就
`endpoint-<序号>`。`hermes_cli/config_migrations.py:104-111 @ 863e313`

```python
            if not key:
                # Fallback: derive from URL hostname
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(old_url)
                    key = (parsed.hostname or "endpoint").replace(".", "-")
                except Exception:
                    key = f"endpoint-{migrated_count}"
```

**防覆盖**:key 撞车就加数字后缀。`hermes_cli/config_migrations.py:116-118 @ 863e313`

```python
            while key in providers_dict:
                key = f"{base_key}-{suffix}"
                suffix += 1
```

形状转换委托给 config.py 的共享函数(`base_url` → `api`、`model` → `default_model`、
`api_mode` → `transport`)。`hermes_cli/config.py:1477 @ 863e313`

```python
def _custom_provider_entry_to_provider_config(
```

转换出的字典以 `api` 为主键。`hermes_cli/config.py:1490 @ 863e313`

```python
    provider_entry: Dict[str, Any] = {"api": normalized["base_url"]}
```

**占位 api_key 清洗**:`no-key` / `no-key-required` / 空串这三种「假密钥」被删掉,
免得后续把它们当真密钥发出去。`hermes_cli/config_migrations.py:128-129 @ 863e313`

```python
            if new_entry.get("api_key") in {"no-key", "no-key-required", ""}:
                new_entry.pop("api_key", None)
```

最后删掉旧 list,理由是运行期改走一个同时读两种形状的兼容视图。
`hermes_cli/config_migrations.py:136-137 @ 863e313`

```python
            # Remove the old list — runtime reads via get_compatible_custom_providers()
            config.pop("custom_providers", None)
```

该兼容视图确实存在且**不回写**。`hermes_cli/config.py:1532 @ 863e313`

```python
def get_compatible_custom_providers(
```

`custom_providers` 至今仍在合法根键白名单里(所以手写旧格式不会被当错误)。
`hermes_cli/config.py:1855 @ 863e313`

```python
    "custom_providers",  # legacy list form; modern equivalent is providers: {}
```

---

#### v12 → 13:清掉死掉的 `LLM_MODEL` / `OPENAI_MODEL`(改的是 .env,不是 config.yaml)

`hermes_cli/config_migrations.py:146 @ 863e313`

```python
def _migrate_to_13(results: Dict[str, Any], quiet: bool) -> None:
```

理由:老 setup 向导写过这两个 env,现在没人读了,留着造成困惑
(config.yaml 自 2026-03 起是唯一真相)。`hermes_cli/config_migrations.py:147-150 @ 863e313`

```python
    # ── Version 12 → 13: clear dead LLM_MODEL / OPENAI_MODEL from .env ──
    # These env vars were written by the old setup wizard but nothing reads
    # them anymore (config.yaml is the sole source of truth since March 2026).
    # Stale entries cause user confusion — see issue report.
```

两个死变量。`hermes_cli/config_migrations.py:155 @ 863e313`

```python
    for dead_var in ("LLM_MODEL", "OPENAI_MODEL"):
```

**"清除"= 写空串,不是删行**。`hermes_cli/config_migrations.py:159 @ 863e313`

```python
                save_env_value(dead_var, "")
```

`save_env_value` 找到同名行就原地替换成 `KEY=`,找不到就**追加**一行。
`hermes_cli/config.py:3912-3923 @ 863e313`

```python
    found = False
    for i, line in enumerate(lines):
        if _env_line_defines_key(line, key):
            lines[i] = f"{key}={serialized_value}\n"
            found = True
            break

    if not found:
        # Ensure there's a newline at the end of the file before appending
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"{key}={serialized_value}\n")
```

判断"旧值存在"用的是 `get_env_value`。`hermes_cli/config.py:4109 @ 863e313`

```python
def get_env_value(key: str) -> Optional[str]:
```

> **可疑缺陷 D-1**:`get_env_value` 先读 `os.environ`(经 secret scope)再读 .env。
> 所以如果用户只是在 shell 里 `export LLM_MODEL=foo`(.env 里根本没有),
> 这一步会往 .env **新增**一行 `LLM_MODEL=`。清理动作反而制造了一行垃圾。
> 而且下次进程启动 `.env` 里的空串会以 `override=True` 覆盖掉 shell 的导出值。

整个循环被静默 `except` 包住(managed scope 拒写时 `save_env_value`
是打印+return 而非抛错,所以这里主要吃的是 I/O 错误)。
`hermes_cli/config_migrations.py:162-163 @ 863e313`

```python
        except Exception:
            pass
```

---

#### v13 → 14:扁平 `stt.model` → provider 专属段

`hermes_cli/config_migrations.py:166 @ 863e313`

```python
def _migrate_to_14(results: Dict[str, Any], quiet: bool) -> None:
```

**真实故障驱动**:老配置(和示例文件)有一个 provider 无关的 `stt.model`;
当 provider 是 `local` 时,OpenAI 的模型名 `whisper-1` 被喂给 faster-whisper,
崩在 "Invalid model size"。`hermes_cli/config_migrations.py:167-172 @ 863e313`

```python
    # ── Version 13 → 14: migrate legacy flat stt.model to provider section ──
    # Old configs (and cli-config.yaml.example) had a flat `stt.model` key
    # that was provider-agnostic.  When the provider was "local" this caused
    # OpenAI model names (e.g. "whisper-1") to be fed to faster-whisper,
    # crashing with "Invalid model size".  Move the value into the correct
    # provider-specific section and remove the flat key.
```

只在 raw(用户真写过)里有 `stt.model` 时动手;provider 缺省 `"local"`。
`hermes_cli/config_migrations.py:181-182 @ 863e313`

```python
    if isinstance(raw_stt, dict) and "model" in raw_stt:
        legacy_model = raw_stt["model"]
```

本地分支:**只有当值在 faster-whisper 已知模型白名单里才搬**,否则直接丢弃
(因为那是个 OpenAI 名字,本地段默认 `base` 已经能用)。
`hermes_cli/config_migrations.py:190-199 @ 863e313`

```python
        if provider in {"local", "local_command"}:
            # Don't migrate an OpenAI model name into the local section
            _local_models = {
                "tiny.en", "tiny", "base.en", "base", "small.en", "small",
                "medium.en", "medium", "large-v1", "large-v2", "large-v3",
                "large", "distil-large-v2", "distil-medium.en",
                "distil-small.en", "distil-large-v3", "distil-large-v3.5",
                "large-v3-turbo", "turbo",
            }
            if legacy_model in _local_models:
```

云 provider 分支:搬进 `stt.<provider>.model`,前提是用户没在那儿写过。
`hermes_cli/config_migrations.py:211-214 @ 863e313`

```python
            raw_provider = raw_stt.get(provider, {})
            if not isinstance(raw_provider, dict) or "model" not in raw_provider:
                provider_cfg = stt.setdefault(provider, {})
                provider_cfg["model"] = legacy_model
```

> **设计取舍**:这是全部 13 个迁移里**唯一带"值白名单"的**。作者宁愿静默丢弃一个
> 不认识的值,也不愿把它搬到一个会崩的位置。代价是:用户如果本来就在用某个新出的
> faster-whisper 模型名(不在这个硬编码集合里),配置会被悄悄清掉。

---

#### v14 → 15:补 `display.interim_assistant_messages`

`hermes_cli/config_migrations.py:221 @ 863e313`

```python
def _migrate_to_15(results: Dict[str, Any], quiet: bool) -> None:
```

只在缺失时补 True。`hermes_cli/config_migrations.py:231-232 @ 863e313`

```python
    if "interim_assistant_messages" not in display:
        display["interim_assistant_messages"] = True
```

默认值本来就是 True。`hermes_cli/config_defaults.py:1193 @ 863e313`

```python
        "interim_assistant_messages": True,  # Gateway: send natural mid-turn assistant status messages. Desktop: keep mid-turn narration between tool calls instead of collapsing to the final message.
```

> **这一步实际上不会往盘上留下任何东西**:`DEFAULT_CONFIG` 里该键就是 `True`,
> 而用户原文件里没有该路径 ⇒ `save_config` 的 strip-defaults 会把它剥掉(见 1.6)。
> 唯一的可观察效果是 `results["config_added"]` 多一条、非 quiet 时多打一行。

---

#### v15 → 16:`display.tool_progress_overrides` → `display.platforms.<plat>.tool_progress`

`hermes_cli/config_migrations.py:240 @ 863e313`

```python
def _migrate_to_16(results: Dict[str, Any], quiet: bool) -> None:
```

读旧键。`hermes_cli/config_migrations.py:250 @ 863e313`

```python
    old_overrides = display.get("tool_progress_overrides")
```

逐平台搬,已存在的目标键不覆盖。`hermes_cli/config_migrations.py:255-259 @ 863e313`

```python
        for plat, mode in old_overrides.items():
            if plat not in platforms:
                platforms[plat] = {}
            if "tool_progress" not in platforms[plat]:
                platforms[plat]["tool_progress"] = mode
```

> **注意:旧键没有被删。** 代码只 `get` 不 `pop`,所以 `display.tool_progress_overrides`
> 会永久留在 config.yaml 里,而且因为该迁移有 `if ... not in platforms[plat]` 保护,
> 重跑幂等。这与 v12/v17/v29/v33 的「搬完就删」风格不一致 —— 是漏删还是刻意保留,
> 代码里没有说明,**未确证**。

---

#### v16 → 17:删 `compression.summary_*`,有值的搬到 `auxiliary.compression`

`hermes_cli/config_migrations.py:269 @ 863e313`

```python
def _migrate_to_17(results: Dict[str, Any], quiet: bool) -> None:
```

三个键一次性 pop 出来。`hermes_cli/config_migrations.py:278-280 @ 863e313`

```python
        s_model = comp.pop("summary_model", None)
        s_provider = comp.pop("summary_provider", None)
        s_base_url = comp.pop("summary_base_url", None)
```

搬运条件很讲究:`summary_provider` 的 `"auto"` 被当成「没设」;目标位置已经有非
`auto` 的值就不覆盖。`hermes_cli/config_migrations.py:289-294 @ 863e313`

```python
        if s_provider and str(s_provider).strip() not in {"", "auto"}:
            aux = config.setdefault("auxiliary", {})
            aux_comp = aux.setdefault("compression", {})
            if not aux_comp.get("provider") or aux_comp.get("provider") == "auto":
                aux_comp["provider"] = str(s_provider).strip()
                migrated_keys.append(f"provider={s_provider}")
```

落盘条件包含「三个键里任意一个原本存在」,这样纯删除(值为空)也会被持久化。
`hermes_cli/config_migrations.py:301 @ 863e313`

```python
        if migrated_keys or s_model is not None or s_provider is not None or s_base_url is not None:
```

---

#### v20 → 21:插件改成 opt-in,把已装的用户插件写进白名单

`hermes_cli/config_migrations.py:311 @ 863e313`

```python
def _migrate_to_21(results: Dict[str, Any], quiet: bool) -> None:
```

政策变更:loader 从「发现即加载(除非在 disabled 里)」改成「必须出现在
`plugins.enabled` 才加载」。为不打断存量用户,把当前已安装且未被 disable 的
**用户插件**灌进白名单;**仓库自带的 bundled 插件不 grandfather**,所有人都要显式开。
`hermes_cli/config_migrations.py:312-321 @ 863e313`

```python
    # ── Version 20 → 21: plugins are now opt-in; grandfather existing user plugins ──
    # The loader now requires plugins to appear in ``plugins.enabled`` before
    # loading. Existing installs had all discovered plugins loading by default
    # (minus anything in ``plugins.disabled``). To avoid silently breaking
    # those setups on upgrade, populate ``plugins.enabled`` with the set of
    # currently-installed user plugins that aren't already disabled.
    #
    # Bundled plugins (shipped in the repo itself) are NOT grandfathered —
    # they ship off for everyone, including existing users, so any user who
    # wants one has to opt in explicitly.
```

幂等闸门:只在 `enabled` 键**不存在**时动手(空 list 也算已设)。
`hermes_cli/config_migrations.py:333 @ 863e313`

```python
    if "enabled" not in plugins_cfg:
```

扫描 `$HERMES_HOME/plugins/` 的每个子目录,认 `plugin.yaml` 或 `plugin.yml`,
名字优先取 manifest 的 `name`,退化到目录名。
`hermes_cli/config_migrations.py:342-357 @ 863e313`

```python
            user_plugins_dir = get_hermes_home() / "plugins"
            if user_plugins_dir.is_dir():
                for child in sorted(user_plugins_dir.iterdir()):
                    if not child.is_dir():
                        continue
                    manifest_file = child / "plugin.yaml"
                    if not manifest_file.exists():
                        manifest_file = child / "plugin.yml"
                    if not manifest_file.exists():
                        continue
                    try:
                        with open(manifest_file, encoding="utf-8") as _mf:
                            manifest = fast_safe_load(_mf) or {}
                    except Exception:
                        manifest = {}
                    name = manifest.get("name") or child.name
```

整个扫描包在一个会把结果清空的 `except` 里。`hermes_cli/config_migrations.py:361-362 @ 863e313`

```python
        except Exception:
            grandfathered = []
```

> **可疑缺陷 D-2**:扫到一半(比如第 5 个插件目录权限出错)会把**前 4 个已收集的
> 名字全部丢掉**,然后照样写一个更短的白名单落盘并标记完成。下次再跑因为
> `enabled` 已存在而跳过 —— 用户的插件被静默关掉且不可自愈。

写入白名单。`hermes_cli/config_migrations.py:364 @ 863e313`

```python
        plugins_cfg["enabled"] = grandfathered
```

`plugins` 不在 `DEFAULT_CONFIG` 里(它在额外白名单),所以即使是空 list 也会真正写盘,
迁移因此是"一次性"的。`hermes_cli/config.py:1862 @ 863e313`

```python
    "plugins",           # plugin enable/disable lists (hermes_cli/plugins_cmd.py)
```

---

#### v22 → 23:补 curator 默认 + 建 `logs/curator/`

`hermes_cli/config_migrations.py:383 @ 863e313`

```python
def _migrate_to_23(results: Dict[str, Any], quiet: bool) -> None:
```

动机写得很完整:curator 靠读时 deep-merge **已经能工作**,但用户在自己的
config.yaml 里看不见、改不了。`hermes_cli/config_migrations.py:387-391 @ 863e313`

```python
    # unification under `auxiliary.curator`) never wrote the curator section
    # to disk. The runtime deep-merge in `load_config()` fills defaults at
    # read time, so the curator *functions*; but users can't see/edit the
    # settings in their `config.yaml`, and `hermes curator status` has no
    # stable logs dir to point at until the first run mkdir's it.
```

三件事的清单。`hermes_cli/config_migrations.py:393-402 @ 863e313`

```python
    # This migration:
    #   1. Writes the `curator` top-level section to config.yaml (enabled,
    #      interval_hours, min_idle_hours, stale_after_days, archive_after_days)
    #      — only keys the user hasn't already overridden.
    #   2. Writes the `auxiliary.curator` aux-task slot (provider, model,
    #      base_url, api_key, timeout, extra_body) — canonical slot for
    #      routing the curator fork to a cheaper aux model.
    #   3. Creates `~/.hermes/logs/curator/` if missing (belt-and-suspenders
    #      on top of ensure_hermes_home() — old profiles that predate this
    #      migration still benefit).
```

建目录那一段:`hermes_cli/config_migrations.py:409-413 @ 863e313`

```python
    try:
        curator_dir = get_hermes_home() / "logs" / "curator"
        curator_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        results["warnings"].append(f"Could not create {curator_dir}: {e}")
```

> **可疑缺陷 D-3(明确的 UnboundLocalError)**:`curator_dir` 在
> `get_hermes_home()` 抛异常时**没有被赋值**,而 `except` 分支的 f-string 引用了它。
> **怎么会踩到**:`get_hermes_home()` 里 `Path(val)` 对含 NUL 的
> `HERMES_HOME` 会抛 `ValueError`;profile fallback 分支还会读 `active_profile` 文件。
> 真出事时,异常处理器自己抛 `UnboundLocalError`,从 `run_migrations` 冒泡出去,
> 整个 `migrate_config` 挂掉 —— 本来只是「日志目录建不出来」的软失败变成硬失败。

从 `DEFAULT_CONFIG` 拷贝缺失键。`hermes_cli/config_migrations.py:419 @ 863e313`

```python
    _curator_defaults = DEFAULT_CONFIG.get("curator", {})
```

用 deepcopy,避免共享可变默认值。`hermes_cli/config_migrations.py:424-427 @ 863e313`

```python
    for k, v in _curator_defaults.items():
        if k not in raw_curator:
            raw_curator[k] = copy.deepcopy(v)
            added_curator.append(k)
```

`auxiliary.curator` 同理。`hermes_cli/config_migrations.py:433-435 @ 863e313`

```python
    _aux_curator_defaults = (
        DEFAULT_CONFIG.get("auxiliary", {}).get("curator", {})
    )
```

> 同 v15:这些拷进去的值**等于默认值**,而用户原文件里没这些路径,
> 所以 strip-defaults 会把它们剥掉。**注释里承诺的"用户能在 config.yaml 里
> 看到并编辑 curator 设置"这个目标,被 `_persist_migration` 的不变量抵消了。**
> 这是本段最实质的一处文档-代码冲突(见 §8 C-2)。

---

#### v24 → 25:`model_catalog.ttl_hours` 24 → 1

`hermes_cli/config_migrations.py:474 @ 863e313`

```python
def _migrate_to_25(results: Dict[str, Any], quiet: bool) -> None:
```

**只改恰好等于旧默认值 24 的**,绝不动用户自定义值。
`hermes_cli/config_migrations.py:486-487 @ 863e313`

```python
    if isinstance(raw_mc, dict) and raw_mc.get("ttl_hours") == 24:
        raw_mc["ttl_hours"] = 1
```

新默认值确实是 1。`hermes_cli/config_defaults.py:2397 @ 863e313`

```python
        "ttl_hours": 1,
```

> 这是「只重写旧默认值」这一惯用法的教科书例子:因为旧版本会把默认值材料化到盘上
> (`strip_defaults=False` 的年代),盘上出现 24 无法区分「用户设的」和「机器写的」,
> 作者选择了「等于旧默认就当机器写的」这个近似。v32 用的是同一套推理。

---

#### v28 → 29:`memory/skills.write_mode` → `write_approval`(三态→布尔)

`hermes_cli/config_migrations.py:495 @ 863e313`

```python
def _migrate_to_29(results: Dict[str, Any], quiet: bool) -> None:
```

映射规则:只有显式 `"approve"` 带有「要门禁」的意图 → True;其余(on/off/未设)→ False。
旧的 `off = 拦所有写` 这一档**被取消**,想彻底关记忆改用 `memory_enabled: false`。
`hermes_cli/config_migrations.py:496-503 @ 863e313`

```python
    # ── Version 28 → 29: rename memory/skills write_mode → write_approval ──
    # The tri-state write_mode (on|off|approve) was replaced by a clear boolean
    # write_approval (default false = gate off, writes flow freely; true =
    # require approval). Only an explicit "approve" carried gating intent, so
    # it maps to true; everything else (on/off/unset) → false. The old
    # "off = block all writes" mode is dropped — memory_enabled: false disables
    # memory entirely. Only rewrite a key the user actually persisted; never
    # invent one.
```

两个子系统各查一次。`hermes_cli/config_migrations.py:510 @ 863e313`

```python
    for subsystem in ("memory", "skills"):
```

映射本体。`hermes_cli/config_migrations.py:516 @ 863e313`

```python
        sub["write_approval"] = (old_norm == "approve")
```

> **语义降级的代价明写在注释里**:原来设了 `write_mode: off` 的用户,迁移后变成
> `write_approval: false`,也就是**写操作从"全拦"变成"畅通"**。这是一次
> 安全性单调变松的自动迁移,只靠一行 `results["config_added"]` 告知。

目标默认值确实是 False。`hermes_cli/config_defaults.py:1829 @ 863e313`

```python
        "write_approval": False,
```

---

#### v30 → 31 与 v31 → 32:两步把 `agent.verify_on_stop` 关掉

第一步只处理「缺失 / `"auto"` 哨兵」两种非承诺态,显式 bool 一律保留。
`hermes_cli/config_migrations.py:539 @ 863e313`

```python
def _migrate_to_31(results: Dict[str, Any], quiet: bool) -> None:
```

判定与闸门。`hermes_cli/config_migrations.py:557-561 @ 863e313`

```python
    is_auto_sentinel = (
        isinstance(cur, str) and cur.strip().lower() == "auto"
    )
    # Only flip the non-committal states; leave explicit bool/on/off alone.
    if cur is None or is_auto_sentinel:
```

第二步是为第一步收尾,注释是全文件最长、也最能说明「为什么迁移这么难写」的一段:
最早发 verify-on-stop 的那个版本把 `DEFAULT_CONFIG` 默认设成字面 `True`,而当年
`migrate_config` 用 `strip_defaults=False` 落盘,于是**所有升到 v30 的安装都在
config.yaml 里被写进了一个字面 `verify_on_stop: true`**;v31 的守卫「保留显式 bool」
恰好把这一整批人全跳过了。
`hermes_cli/config_migrations.py:575-586 @ 863e313`

```python
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

只认字面 `True`(`is True`,不接受 1 / "true")。`hermes_cli/config_migrations.py:593 @ 863e313`

```python
    if isinstance(raw_agent, dict) and raw_agent.get("verify_on_stop") is True:
```

> **两步的落盘结果不同,值得说清:**
> - v31 写 `False`,而当前 `DEFAULT_CONFIG` 的值是 `"auto"`(不是 `False`),
>   两者不等 ⇒ strip-defaults **不会**剥掉它 ⇒ 真的写进盘。
> - v32 的目标路径本来就在用户原文件里(那个字面 `true`),因此也在
>   `preserve_keys` 里 ⇒ 也真的写进盘。

**但是** `DEFAULT_CONFIG` 至今仍是 `"auto"`。`hermes_cli/config_defaults.py:158 @ 863e313`

```python
        "verify_on_stop": "auto",
```

而解析函数把 `"auto"` 和「缺失」都解释成「面向 surface 自适应」(CLI 上 = 开)。
`agent/verification_stop.py:127-130 @ 863e313`

```python
        if token == "auto":
            return not _session_is_messaging_surface()
    # Missing or unrecognized value -> surface-aware "auto" default.
    return not _session_is_messaging_surface()
```

> ⇒ **迁移注释说的"The new default is OFF"只对被迁移过的存量安装成立;
> 全新安装(config 一出生就是 v33,不跑任何迁移)拿到的仍然是 `"auto"` = CLI 上开。**
> 这是一处实打实的行为分叉,见 §8 C-3。

---

#### v32 → 33:合并 delegation 并发上限

`hermes_cli/config_migrations.py:607 @ 863e313`

```python
def _migrate_to_33(results: Dict[str, Any], quiet: bool) -> None:
```

`max_async_children` 废弃,`max_concurrent_children` 统一封顶「单批并行度」和
「后台委派单元并发」;取两者较大值,谁也不损失余量,然后删旧键。
`hermes_cli/config_migrations.py:608-613 @ 863e313`

```python
    # ── Version 32 → 33: unify delegation concurrency caps ──
    # delegation.max_async_children is deprecated: max_concurrent_children now
    # caps both a single batch's parallelism and concurrent background
    # delegation units. Fold a raised max_async_children into
    # max_concurrent_children (take the max so nobody loses headroom), then
    # drop the stale key.
```

只有超过 3 才考虑折叠。`hermes_cli/config_migrations.py:626 @ 863e313`

```python
        if old_async_i is not None and old_async_i > 3:
```

取较大值。`hermes_cli/config_migrations.py:631-632 @ 863e313`

```python
            if old_async_i > cur_children:
                raw_deleg["max_concurrent_children"] = old_async_i
```

> **可疑缺陷 D-4(硬编码 3)**:`> 3` 和 `int(raw_deleg.get("max_concurrent_children", 3))`
> 里的 3 是把 `DEFAULT_CONFIG` 当时的值写死了。一旦改默认,这段就悄悄错位:
> 比如默认改成 5,而用户有 `max_async_children: 4` 且没写 `max_concurrent_children`,
> `old_async_i > 3` 成立、`cur_children` 被当成 3、于是把上限**下调**成 4。

当前默认值。`hermes_cli/config_defaults.py:1709 @ 863e313`

```python
        "max_concurrent_children": 3,  # unified concurrency cap: max parallel children per batch
```

---

### 1.8 `migrate_config` 里除迁移阶梯外还干了什么(上下文,便于理解 results 结构)

顺序是:先无条件规范化 .env 行格式 → 版本检查 → 底线闸门 / 阶梯 →
MCP 可疑条目禁用 → `platform_toolsets` 校验 → 缺失 env 交互补录 →
版本戳 → 技能声明的配置项补录。

三个结果桶。`hermes_cli/config.py:2161 @ 863e313`

```python
    results = {"env_added": [], "config_added": [], "warnings": []}
```

无条件规范化 .env。`hermes_cli/config.py:2165 @ 863e313`

```python
        fixes = sanitize_env_file()
```

「本次更新新增了哪些 env」靠一张按版本索引的表算差集 —— 该表**只覆盖到版本 11**。
`hermes_cli/config.py:951 @ 863e313`

```python
ENV_VARS_BY_VERSION: Dict[int, List[str]] = {
```

差集计算。`hermes_cli/config.py:2313-2314 @ 863e313`

```python
    for ver in range(current_ver + 1, latest_ver + 1):
        new_var_names.update(ENV_VARS_BY_VERSION.get(ver, []))
```

> 也就是说:自 v11 之后新增的 env 变量都不会在迁移里被主动询问。**未确证**这是
> 有意为之还是遗漏 —— `tests/gateway/test_whatsapp_reply_prefix.py` 只断言
> `_config_version >= max(ENV_VARS_BY_VERSION)`,不要求表覆盖每个版本。

「缺失的 config 字段」只上报、不落盘。`hermes_cli/config.py:2354-2360 @ 863e313`

```python
    # Check for missing config fields.
    #
    # New default keys are NOT materialised to disk: load_config() deep-merges
    # DEFAULT_CONFIG at read time, so a missing key already takes effect with
    # its default (see _persist_migration's invariant). We surface the list for
    # the informational "N new config option(s) available" display in
    # `hermes update`, but only the version bump is persisted.
```

---

## 2. env_loader.py —— .env 与外部密钥的装载

### 2.1 解决什么问题

Hermes 的凭据可能来自四个地方:profile 的 `~/.hermes/.env`、仓库根的项目
`.env`(开发用)、shell 导出、外部密钥库(Bitwarden / 1Password / 自定义命令)。
还有一层机器级 managed scope。`load_hermes_dotenv` 负责把这些按一个**确定的
优先级**灌进 `os.environ`,并且在灌之前把文件本身洗干净。

### 2.2 加载顺序(user env vs project env vs .op.env vs managed)

入口:`hermes_cli/env_loader.py:462 @ 863e313`

```python
def load_hermes_dotenv(
```

docstring 声明的三条规则。`hermes_cli/env_loader.py:467-474 @ 863e313`

```python
    """Load Hermes environment files with user config taking precedence.

    Behavior:
    - `~/.hermes/.env` overrides stale shell-exported values when present.
    - project `.env` acts as a dev fallback and only fills missing values when
      the user env exists.
    - if no user env exists, the project `.env` also overrides stale shell vars.
    """
```

home 解析(**本文件最脆的一行,见 §9 D-5 / D-6**)。`hermes_cli/env_loader.py:477 @ 863e313`

```python
    home_path = Path(hermes_home or os.getenv("HERMES_HOME", Path.home() / ".hermes"))
```

装载顺序,逐行:

1. 两个文件先各自「预清洗」(BOM / NUL / 行尾),再交给 python-dotenv。
   `hermes_cli/env_loader.py:482-485 @ 863e313`

```python
    if user_env.exists():
        _sanitize_env_file_if_needed(user_env)
    if project_env_path and project_env_path.exists():
        _sanitize_env_file_if_needed(project_env_path)
```

2. **user env 以 `override=True` 装载** —— 即压过 shell 导出;随后清扫「本 profile
   的 .env 里没写、但从父进程继承来的行为路由键」。
   `hermes_cli/env_loader.py:487-492 @ 863e313`

```python
    if user_env.exists():
        _load_dotenv_with_fallback(user_env, override=True)
        loaded.append(user_env)
        # Mirror reload_env() known-key cleanup so inherited Hermes keys
        # absent from this profile's .env do not leak into the runtime.
        _clear_known_keys_missing_from_dotenv(user_env)
```

3. `.op.env` 的动机注释。`hermes_cli/env_loader.py:494-503 @ 863e313`

```python
    # Load .op.env AFTER .env so that .env values win, but the bootstrap
    # token (OP_SERVICE_ACCOUNT_TOKEN) becomes available for
    # apply_onepassword_secrets() even in cron / subprocess environments
    # that inherit no shell state (no systemd EnvironmentFile, no op run).
    # .op.env is gitignored — the service-account token never enters the
    # committed .env file.
    # Users on systemd can alternatively use:
    #   EnvironmentFile=-/path/to/.hermes/.op.env
    # in their gateway unit, which takes precedence (override=False below
    # ensures .op.env never clobbers a token already in the environment).
```

   **`.op.env` 在 `.env` 之后、以 `override=False` 装载**,而且环境里已有 token 就跳过。
   `hermes_cli/env_loader.py:504-506 @ 863e313`

```python
    op_env = home_path / ".op.env"
    if op_env.exists() and not os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"):
        _load_dotenv_with_fallback(op_env, override=False)
```

4. **project env 的 override 取决于 user env 在不在**:`override=not loaded`。
   user env 装过了 ⇒ `loaded` 非空 ⇒ `override=False` ⇒ project env 只补缺。
   `hermes_cli/env_loader.py:508-510 @ 863e313`

```python
    if project_env_path and project_env_path.exists():
        _load_dotenv_with_fallback(project_env_path, override=not loaded)
        loaded.append(project_env_path)
```

5. 外部密钥源 → managed scope。`hermes_cli/env_loader.py:512-513 @ 863e313`

```python
    _apply_external_secret_sources(home_path)
    _apply_managed_env()
```

6. 最后是 terminal 配置桥。`hermes_cli/env_loader.py:527 @ 863e313`

```python
    _reapply_terminal_config_bridge(home_path)
```

**最终优先级(从低到高)**:shell 导出 < project `.env` < `.op.env`(仅
`OP_SERVICE_ACCOUNT_TOKEN`,且只在环境里没有时) < user `.env` < 外部密钥源
(取决于 `override_existing`) < managed `.env` < config.yaml 的显式 `terminal.*`。

**managed scope 故意反转了常规的 env-over-config 优先级**,并且承认 v1 只靠
文件权限保证,不阻止 agent 后续在进程内改 `os.environ`。
`hermes_cli/env_loader.py:560-574 @ 863e313`

```python
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

    Fail-open: a missing managed dir or .env is the common case and a no-op; any
    error here is swallowed so managed scope can never block startup.
    """
```

managed 目录来自 `HERMES_MANAGED_DIR` 或 `/etc/hermes`。
`hermes_cli/managed_scope.py:65 @ 863e313`

```python
    override = os.environ.get("HERMES_MANAGED_DIR", "").strip()
```

**terminal 配置桥**是为一个具体故障加的:config.yaml 是 `terminal.*` 的文档级
真相源,但上面的 dotenv 用了 `override=True`,于是 `~/.hermes/.env` 里一条陈旧的
`TERMINAL_ENV=docker` 会在每次 reload 时重新赢回来;长驻进程(网关每轮 reload、
cron)反复调 `load_hermes_dotenv()`,会话中途把后端翻回旧值。
`hermes_cli/env_loader.py:515-526 @ 863e313`

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

桥只在「传入的 home == 进程 home」时执行,否则会把错的 profile 的 config 桥过去。
`hermes_cli/env_loader.py:550 @ 863e313`

```python
        if Path(home_path).resolve() != _process_hermes_home().resolve():
```

共享桥本体只让「用户在 config.yaml 里真写过的键」覆盖 env,合并进来的默认值只补缺。
`hermes_cli/config.py:3266 @ 863e313`

```python
    explicit_keys = terminal_cfg.keys() if config is not None else raw_terminal_cfg.keys()
```

写入条件。`hermes_cli/config.py:3278 @ 863e313`

```python
        if (should_override and cfg_key in explicit_keys) or env_var not in target:
```

映射表列出了全部被桥接的 env 名。`hermes_cli/config.py:3183 @ 863e313`

```python
TERMINAL_CONFIG_ENV_MAP = {
```

### 2.3 profile-managed 键的启动清扫(范围为什么这么窄)

`hermes_cli/env_loader.py:114 @ 863e313`

```python
def _clear_known_keys_missing_from_dotenv(path: Path) -> None:
```

只清扫一个 6 元素的冻结集合 —— 都是「父 Hermes 进程注入、会**静默改变走哪条
provider 路径**」的行为路由键。`hermes_cli/env_loader.py:76-83 @ 863e313`

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

**为什么不清 API key**:用户在 shell 里 `export OPENAI_API_KEY=…` 是文档化的用法,
启动清扫无法区分「shell 导出」和「父进程泄漏」;清全集会在每次 `hermes` 调用时
删掉用户导出的凭据。跨 profile 的凭据隔离改在**读时**由 secret scope 负责。
`hermes_cli/env_loader.py:122-135 @ 863e313`

```python
    Scope is deliberately NARROW: only ``_PROFILE_MANAGED_ENV_KEYS`` —
    behavioral routing keys (ACP auth method, copilot-ACP endpoints) that a
    parent Hermes process injects and that silently change *which provider
    path* a profile uses. Provider API keys (OPENAI_API_KEY, …) are
    intentionally excluded: users legitimately export those in their shell
    (``export OPENAI_API_KEY=…`` is a documented flow — see
    ``tests/hermes_cli/test_dump_env_visibility.py``), and a startup scrub
    cannot distinguish a shell export from parent-process leakage. Clearing
    the full known-key set would delete user-exported credentials on every
    ``hermes`` invocation.

    Cross-profile *credential* isolation is handled at read time by
    ``agent.secret_scope.get_secret`` (scope authoritative under
    multiplexing), not by mutating ``os.environ`` here.
```

`.env` 不存在时**不清扫**(裸 profile 语义)。`hermes_cli/env_loader.py:140-141 @ 863e313`

```python
    if not path.exists():
        return
```

判断「文件里定义了哪些键」用的是自己写的快速行扫描,不走 python-dotenv,
以便早期 bootstrap 也能用;空赋值 `KEY=` 也算定义。`hermes_cli/env_loader.py:86 @ 863e313`

```python
def _env_keys_defined_in_dotenv(path: Path) -> set[str]:
```

认 `export KEY=` 形式。`hermes_cli/env_loader.py:106-107 @ 863e313`

```python
        if line.startswith("export "):
            line = line[7:]
```

模块里还有一个合并已知键集合的函数。`hermes_cli/env_loader.py:55 @ 863e313`

```python
def _known_hermes_env_keys() -> set[str]:
```

> **可疑缺陷 D-7:它在本文件里没有任何调用点**(全文件 grep 只有定义处),
> 是窄化清扫范围那次改动的遗留。

### 2.4 凭据值的 ASCII 清洗:为什么必要

`hermes_cli/env_loader.py:20 @ 863e313`

```python
_CREDENTIAL_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET", "_KEY")
```

**必要性来自 HTTP 层**:API key 会成为 HTTP header 值,httpx 用 ASCII 编码 header。
从 PDF / 富文本编辑器 / 网页复制的 key 里常混进 Unicode 同形字(如 ʋ U+028B 代替 v)
或零宽空格,provider 侧只会返回一句不知所云的 "invalid API key"。
`hermes_cli/env_loader.py:17-19 @ 863e313`

```python
# only env vars whose values we sanitize on load — we must not silently
# alter arbitrary user env vars, but credentials are known to require
# pure ASCII (they become HTTP header values).
```

清洗函数:`hermes_cli/env_loader.py:298 @ 863e313`

```python
def _sanitize_loaded_credentials() -> None:
```

做法是「先试编码,失败才清洗」,避免对绝大多数纯 ASCII 值付出重建成本。
`hermes_cli/env_loader.py:310-318 @ 863e313`

```python
    for key, value in list(os.environ.items()):
        if not any(key.endswith(suffix) for suffix in _CREDENTIAL_SUFFIXES):
            continue
        try:
            value.encode("ascii")
            continue
        except UnicodeEncodeError:
            pass
        cleaned = value.encode("ascii", errors="ignore").decode("ascii")
```

**绝不静默**:每个键一生只警告一次。`hermes_cli/env_loader.py:320-322 @ 863e313`

```python
        if key in _WARNED_KEYS:
            continue
        _WARNED_KEYS.add(key)
```

警告里列出前 3 个越界码点的 `U+XXXX ('c')` 形式。`hermes_cli/env_loader.py:283 @ 863e313`

```python
def _format_offending_chars(value: str, limit: int = 3) -> str:
```

去重一次警告的动机写在集合定义处:同一进程里 `load_hermes_dotenv()` 会被调很多次。
`hermes_cli/env_loader.py:22-25 @ 863e313`

```python
# Names we've already warned about during this process, so repeated
# load_hermes_dotenv() calls (user env + project env, gateway hot-reload,
# tests) don't spam the same warning multiple times.
_WARNED_KEYS: set[str] = set()
```

调用点之一:每次 dotenv 装载后。`hermes_cli/env_loader.py:352 @ 863e313`

```python
    _sanitize_loaded_credentials()
```

调用点之二:外部密钥源应用之后(vault 里的值同样可能被复制粘贴污染)。
`hermes_cli/env_loader.py:659 @ 863e313`

```python
        _sanitize_loaded_credentials()
```

> **可疑缺陷 D-8(后缀过宽 + 扫全环境)**:
> (a) `_KEY` 已经包含 `_API_KEY`,元组前两项部分冗余;
> (b) `_KEY` 会命中**路径类**变量,例如 `TERMINAL_SSH_KEY`(SSH 私钥路径)、
>     `FEISHU_ENCRYPT_KEY`、`WECOM_CALLBACK_ENCODING_AES_KEY` —— 这些都在
>     `_EXTRA_ENV_KEYS` 里;一个位于非 ASCII 路径(中文用户名)下的 SSH key 路径
>     会被**静默改写**成一个不存在的路径,警告文案还会说"key 是从 PDF 复制的";
> (c) 循环遍历的是**整个 `os.environ`**,不只是刚装载的键。任何第三方
>     `SOMETHING_KEY` 环境变量都会被 Hermes 改写。

`TERMINAL_SSH_KEY` 确实在已知键集合里。`hermes_cli/config.py:294 @ 863e313`

```python
    "TERMINAL_ENV", "TERMINAL_SSH_KEY", "TERMINAL_SSH_PORT",
```

### 2.5 .env 文件的预清洗:BOM / NUL / UTF-32 拒绝改写

`hermes_cli/env_loader.py:355 @ 863e313`

```python
def _sanitize_env_file_if_needed(path: Path) -> None:
```

要解决的具体崩溃:值里嵌了 NUL 字节,`os.environ[k] = v` 抛
`ValueError: embedded null byte`。`hermes_cli/env_loader.py:356-361 @ 863e313`

```python
    """Pre-sanitize a .env file before python-dotenv reads it.

    Strips embedded null bytes which crash ``os.environ[k] = v``
    with ``ValueError: embedded null byte`` — typically introduced by
    copy-pasting API keys from terminals or rich-text editors.
```

**UTF-32 拒绝改写是什么故事**:这是一条「顺序敏感的 BOM 嗅探」教训。
UTF-32-LE 的 BOM 是 `FF FE 00 00`,而 UTF-16-LE 的 BOM 是 `FF FE` ——
前者以后者开头。如果先查 UTF-16,一个 UTF-32-LE 文件会被
**误判成 UTF-16-LE 并按 UTF-16 解码重写,文件当场毁掉**。所以代码强制先查 UTF-32,
命中就**原样不动**(既不解码也不重写),只打一条 warning。
`hermes_cli/env_loader.py:383-386 @ 863e313`

```python
    # Sniff leading BOM bytes BEFORE decoding. ORDER MATTERS:
    # codecs.BOM_UTF32_LE is FF FE 00 00, which startswith
    # codecs.BOM_UTF16_LE (FF FE). Checking UTF-16 first would
    # misdetect UTF-32-LE as UTF-16-LE and mangle the file.
```

UTF-32 分支。`hermes_cli/env_loader.py:388 @ 863e313`

```python
    if raw.startswith(codecs.BOM_UTF32_LE) or raw.startswith(codecs.BOM_UTF32_BE):
```

warning 每个路径只打一次,因为同一个文件会被 user env / project env / 热重载多次经过。
`hermes_cli/env_loader.py:27-31 @ 863e313`

```python
# Paths we've already emitted a UTF-32 refuse-to-mangle warning for.
# load_hermes_dotenv can call _sanitize_env_file_if_needed multiple times
# for the same file (user env + project env + hot-reload); once per path
# is enough.
_WARNED_UTF32_PATHS: set[str] = set()
```

去重逻辑。`hermes_cli/env_loader.py:391-393 @ 863e313`

```python
        path_key = str(path.resolve())
        if path_key not in _WARNED_UTF32_PATHS:
            _WARNED_UTF32_PATHS.add(path_key)
```

UTF-16(Notepad 的 "Unicode")则**能正确解码,并统一重写成干净的 UTF-8**。
用 `TextIOWrapper(newline=None)` 而不是 `splitlines()`,以便和 UTF-8 路径切出
同样的行(`splitlines()` 会额外在 U+2028 等处断行)。
`hermes_cli/env_loader.py:402-412 @ 863e313`

```python
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        # "utf-16" uses the BOM to select endianness and strips it.
        # TextIOWrapper + newline=None matches open()'s universal-newlines
        # line splitting (\\n/\\r\\n/\\r only — not splitlines()'s extra
        # Unicode boundaries like U+2028), so sanitize sees the same lines
        # as the UTF-8 path.
        try:
            with io.TextIOWrapper(
                io.BytesIO(raw), encoding="utf-16", newline=None
            ) as f:
                original = f.readlines()
```

默认路径用 `utf-8-sig` + `errors="replace"`,并加一道纵深防御:如果首行以 U+FFFD
开头(说明解码本来就坏了),**放弃不写** —— 否则替换字符会被永久粘到第一个键名上。
`hermes_cli/env_loader.py:426-432 @ 863e313`

```python
        # Defense-in-depth: errors=replace turns undecodable leading
        # bytes into U+FFFD. Persisting that glues replacement chars
        # onto the first key name and rewrites the file permanently
        # (the UTF-16-with-BOM corruption path before BOM sniffing).
        # Leave the file untouched rather than write the mangling.
        if original and original[0].startswith("\ufffd"):
            return
```

去 NUL 有个附带好处:**无 BOM 的 UTF-16(NUL 填充的 ASCII)会被顺手修成干净 UTF-8**。
`hermes_cli/env_loader.py:434-440 @ 863e313`

```python
    try:
        # Strip null bytes before _sanitize_env_lines so they never
        # reach python-dotenv (which passes them to os.environ and
        # crashes with ValueError). Also intentionally repairs
        # BOM-less UTF-16 (NUL-padded ASCII) into clean UTF-8.
        stripped = [line.replace("\x00", "") for line in original]
        sanitized = _sanitize_env_lines(stripped)
```

行规范化本身由 config.py 提供。`hermes_cli/config.py:3723 @ 863e313`

```python
def _sanitize_env_lines(lines: list) -> list:
```

它只动行尾,**第一个 `=` 之后一律当不透明数据**(否则值里出现的 `FOO=` 会被误当成
新赋值)。`hermes_cli/config.py:3724-3729 @ 863e313`

```python
    """Normalize .env line endings without changing assignment semantics.

    Content after the first ``=`` is opaque value data. A known variable name
    embedded in that value must never be reinterpreted as another assignment;
    concatenated assignments are ambiguous and therefore remain on one line.
    """
```

写盘走 mkstemp + fsync + `atomic_replace`,异常时删临时文件;最外层静默吞掉,
理由是不能挡住网关启动。`hermes_cli/env_loader.py:441-459 @ 863e313`

```python
        if sanitized != original or force_utf8_rewrite:
            import tempfile
            fd, tmp = tempfile.mkstemp(
                dir=str(path.parent), suffix=".tmp", prefix=".env_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.writelines(sanitized)
                    f.flush()
                    os.fsync(f.fileno())
                atomic_replace(tmp, path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
    except Exception:
        pass  # best-effort — don't block gateway startup
```

> **可疑缺陷 D-9**:重写不保留原文件权限。`save_env_value` 特意保存并恢复
> `original_mode`(为了 Docker volume mount),但这里没有。

`save_env_value` 里的权限恢复。`hermes_cli/config.py:3941-3943 @ 863e313`

```python
        if original_mode is not None:
            try:
                os.chmod(env_path, original_mode)
```

**dotenv 装载本身的编码回退**:先 UTF-8,`UnicodeDecodeError` 再 latin-1。
`hermes_cli/env_loader.py:342-346 @ 863e313`

```python
def _load_dotenv_with_fallback(path: Path, *, override: bool) -> None:
    try:
        load_dotenv(dotenv_path=path, override=override, encoding="utf-8")
    except UnicodeDecodeError:
        load_dotenv(dotenv_path=path, override=override, encoding="latin-1")
```

### 2.6 外部密钥源(Bitwarden 等)怎么注入

`hermes_cli/env_loader.py:591 @ 863e313`

```python
def _apply_external_secret_sources(home_path: Path) -> None:
```

**时序**:在 dotenv 之后(源要用 .env 里的 bootstrap token 定位自己),
在其余代码读 `os.environ` 取凭据之前。`hermes_cli/env_loader.py:592-597 @ 863e313`

```python
    """Pull secrets from every enabled external source into env.

    Runs AFTER dotenv loads so .env values are visible (sources use them
    to locate bootstrap tokens) but BEFORE the rest of Hermes reads
    ``os.environ`` for credentials.  Any failure here is logged and
    swallowed — external secret sources must never block startup.
```

分工写得很清楚。`hermes_cli/env_loader.py:599-604 @ 863e313`

```python
    The heavy lifting (source ordering, mapped-beats-bulk precedence,
    first-claim-wins conflict handling, override semantics, provenance)
    lives in ``agent.secret_sources.registry.apply_all``; this wrapper
    owns the once-per-HERMES_HOME guard, the post-apply ASCII
    sanitization sweep, the ``_SECRET_SOURCES`` provenance map that
    UI surfaces read, and the startup status lines.
```

**「一次守卫」的三段式退出策略是这个函数最精细的部分**,三种早退**都不标记已应用**,
只有真正发起过一次 fetch 才标记:

- 配置解析异常 → 不标记,否则用户修好 config.yaml 之后本进程永远不再加载。
  `hermes_cli/env_loader.py:620-624 @ 863e313`

```python
    except Exception:  # noqa: BLE001 — config errors must not block startup
        # Deliberately NOT marked applied: a malformed config.yaml would
        # otherwise permanently disable secret loading for this process
        # even after the user fixes the file (#40597).
        return
```

- 没有 `secrets:` 段 → 不标记,重解析很便宜,留着让进程下次能捡到配置变更。
  `hermes_cli/env_loader.py:625-630 @ 863e313`

```python
    if not cfg:
        # No secrets section (or everything disabled at parse level).  Not
        # marked applied either — the re-parse is a cheap fast_safe_load and
        # leaving the home unmarked lets a process pick up a config change
        # on its next load_hermes_dotenv() call instead of never.
        return
```

- 解析出来了但没有启用的源 → 同理不标记。
  `hermes_cli/env_loader.py:642-646 @ 863e313`

```python
    if not report.sources:
        # Config parsed but no source is enabled: keep retrying cheaply
        # (no fetch happens for disabled sources) so flipping a source on
        # mid-process takes effect on the next call.
        return
```

- 真发起过 fetch(成功**或**失败)→ 标记。
  `hermes_cli/env_loader.py:648-653 @ 863e313`

```python
    # A real fetch attempt happened (success OR error).  Mark the home now
    # so the 3-5 import-time load_hermes_dotenv() calls per startup don't
    # re-fetch / re-print — error retries within one process are opt-in via
    # reset_secret_source_cache().  Marking AFTER the attempt (not before,
    # see #40597) is what lets the earlier failure paths stay retryable.
    _APPLIED_HOMES.add(home_key)
```

守卫的动机(打印刷屏、重复解析、重复清洗)。`hermes_cli/env_loader.py:44-51 @ 863e313`

```python
# HERMES_HOME paths we've already pulled external secrets for during this
# process.  ``load_hermes_dotenv()`` is called at module-import time from
# several hot modules (cli.py, hermes_cli/main.py, run_agent.py,
# trajectory_compressor.py, gateway/run.py, ...), so without this guard the
# Bitwarden status line gets printed 3-5x per startup.  Bitwarden's own
# in-process cache prevents redundant network calls, but the print, the
# config re-parse, and the ASCII sanitization sweep still ran every time.
_APPLIED_HOMES: set[str] = set()
```

只读 `secrets:` 一段,与主配置加载器隔离。`hermes_cli/env_loader.py:709 @ 863e313`

```python
def _load_secrets_config(home_path: Path) -> dict:
```

优先复用共享的 (mtime,size) raw-config 缓存,只在 home == 进程 home 时才走共享读者。
`hermes_cli/env_loader.py:725 @ 863e313`

```python
    if home_path == _process_hermes_home():
```

> **可疑缺陷 D-10**:这里用 `==` 比较两个 `Path`,而同一函数族其他地方用
> `.resolve()` 后比较(`hermes_cli/env_loader.py:550`)。`Path("/home/u/.hermes/")`
> 与 `Path("/home/u/.hermes")` 在 `==` 下不相等,symlink / 相对路径同理。
> 后果只是「少复用一次缓存,走独立解析」,不影响正确性,但属于同一语义两种写法。

provenance 记账:`_SECRET_SOURCES` 记「变量 → 源标签」,给 UI 打
"(from Bitwarden)" 这类后缀用。`hermes_cli/env_loader.py:33-39 @ 863e313`

```python
# Map of env-var name → source label ("bitwarden", etc.) for credentials
# that were injected by an external secret source during load_hermes_dotenv().
# Used by setup / `hermes model` flows to label detected credentials so
# users understand WHERE a key came from when their .env doesn't contain it
# directly (otherwise the "credentials detected ✓" line looks identical to
# the .env case and they don't know Bitwarden is wired up).
_SECRET_SOURCES: dict[str, str] = {}
```

后缀渲染函数。`hermes_cli/env_loader.py:256 @ 863e313`

```python
def format_secret_source_suffix(env_var: str) -> str:
```

`"bitwarden"` 硬编码成 "(from Bitwarden)",其他源问注册表要 label,问不到就回落原名。
`hermes_cli/env_loader.py:267-280 @ 863e313`

```python
    if source == "bitwarden":
        return " (from Bitwarden)"
    # Ask the registry for the source's human label (e.g. "1Password").
    # Fall back to the raw source name for labels the registry doesn't
    # know (stale provenance from an uninstalled plugin, tests).
    try:
        from agent.secret_sources.registry import get_source

        registered = get_source(source)
        if registered is not None and registered.label:
            return f" (from {registered.label})"
    except Exception:  # noqa: BLE001 — label lookup must never raise
        pass
    return f" (from {source})"
```

**provenance 是元数据,不是授权** —— docstring 明确禁止把它当成「可以持久化明文」
的依据。`hermes_cli/env_loader.py:153-156 @ 863e313`

```python
    ``None`` for keys that came from ``.env``, the shell environment, or
    aren't tracked.  The returned label is metadata only: credential-pool
    persistence may store it to explain the origin of a borrowed secret, but
    must never treat it as authorization to persist the raw value.
```

状态行全部走 stderr(不污染 stdout 管道),含 applied 计数、error、
补救提示、warnings、冲突。`hermes_cli/env_loader.py:671-686 @ 863e313`

```python
    for src in report.sources:
        if src.applied:
            print(
                f"  {src.label}: applied {len(src.applied)} "
                f"secret{'s' if len(src.applied) != 1 else ''}",
                file=sys.stderr,
            )
        if src.result.error:
            print(f"  {src.label}: {src.result.error}", file=sys.stderr)
            hint = _remediation_hint(src.name, src.result.error_kind, cfg)
            if hint:
                print(f"  {src.label}: → {hint}", file=sys.stderr)
        for warn in src.result.warnings:
            print(f"  {src.label}: {warn}", file=sys.stderr)
    for conflict in report.conflicts:
        print(f"  Secret sources: {conflict}", file=sys.stderr)
```

补救提示本身也包了一层防御(插件源可能抛)。`hermes_cli/env_loader.py:689 @ 863e313`

```python
def _remediation_hint(source_name: str, error_kind, secrets_cfg: dict) -> str:
```

### 2.7 `_SECRET_SOURCE_VALUES_BY_HOME` 为什么要按 home 分桶

`hermes_cli/env_loader.py:40-42 @ 863e313`

```python
# Applied values are immutable per-home snapshots.  ``os.environ`` is shared
# across profiles and may be overwritten by a later home's source apply.
_SECRET_SOURCE_VALUES_BY_HOME: dict[str, dict[str, str]] = {}
```

**原因链**:多路复用网关(一个进程服务多个 profile)里,`os.environ` 是**全局共享**
的一份。profile A 的 Bitwarden 值写进 `os.environ["OPENAI_API_KEY"]`,随后
profile B 的源应用又把同一个键覆盖成 B 的值。此时若靠「读 `os.environ`」还原
A 的外部密钥,拿到的是 B 的。所以在**应用当时**就为该 home 拍一份不可变快照。

快照写入点。`hermes_cli/env_loader.py:664-669 @ 863e313`

```python
        values: dict[str, str] = {}
        for name, applied in report.provenance.items():
            _SECRET_SOURCES[name] = applied.source
            if name in os.environ:
                values[name] = os.environ[name]
        _SECRET_SOURCE_VALUES_BY_HOME[home_key] = values
```

桶的 key 是 `resolve()` 后的绝对路径。`hermes_cli/env_loader.py:614 @ 863e313`

```python
    home_key = str(Path(home_path).resolve())
```

读取接口:`hermes_cli/env_loader.py:161 @ 863e313`

```python
def get_secret_source_values(
```

返回拷贝,不泄露内部字典。`hermes_cli/env_loader.py:165-166 @ 863e313`

```python
    home_key = str(Path(hermes_home).resolve())
    return dict(_SECRET_SOURCE_VALUES_BY_HOME.get(home_key, {}))
```

**消费者**是每轮安装的 secret scope 构造器:profile 的 `.env` + 该 profile 的外部
密钥快照。`agent/secret_scope.py:272 @ 863e313`

```python
def build_profile_secret_scope(hermes_home: Path) -> Dict[str, str]:
```

它显式去取 per-home 快照。`agent/secret_scope.py:283-284 @ 863e313`

```python
        from hermes_cli.env_loader import get_secret_source_values
        external_secrets = get_secret_source_values(home)
```

**冷 profile 的补水路径**:多路复用网关可能把第一轮路由到一个从没跑过进程级
dotenv 启动路径的次级 profile。`hermes_cli/env_loader.py:169 @ 863e313`

```python
def hydrate_profile_secret_sources(
```

它解析该 profile 的源,**不碰 `os.environ`**,只把值放进一个私有映射并记录
per-home 快照。`hermes_cli/env_loader.py:172-182 @ 863e313`

```python
    """Resolve one profile's configured sources without mutating ``os.environ``.

    Multiplex gateways can route a first turn to a secondary profile that has
    never run the process-global dotenv startup path.  Resolve that profile's
    sources against a private mapping seeded from its own ``.env`` and record
    the usual per-home snapshot for ``build_profile_secret_scope()``.

    Fail-open and once-per-home semantics intentionally mirror
    ``_apply_external_secret_sources``.  The returned mapping contains only
    values actually contributed by external sources, never the profile's
    plaintext ``.env`` entries.
    """
```

私有 environ 的构造:全局 env + 该 profile 的 `.env` + `.op.env`(不覆盖) + `HERMES_HOME`。
`hermes_cli/env_loader.py:205-221 @ 863e313`

```python
        local_env = {
            name: value
            for name, value in os.environ.items()
            if _is_global_env(name)
        }
        local_env.update(load_env_file(home / ".env"))
        # Mirror load_hermes_dotenv()'s .op.env bootstrap: the 1Password
        # service-account token lives in <home>/.op.env (gitignored), not
        # .env. Without seeding it here a cold profile configured for the
        # supported .op.env flow fails 1Password hydration (sweeper review
        # on #74549). .env values win — never override an existing key.
        op_env = home / ".op.env"
        if op_env.exists():
            for _name, _value in load_env_file(op_env).items():
                local_env.setdefault(_name, _value)
        local_env["HERMES_HOME"] = str(home)
        report = apply_all(cfg, home, environ=local_env)
```

`apply_all` 的 `environ` 参数正是为此存在。`agent/secret_sources/registry.py:333-334 @ 863e313`

```python
def apply_all(secrets_cfg: dict, home_path: Path,
              environ: Optional[MutableMapping[str, str]] = None) -> ApplyReport:
```

**并发保护**:公开入口加了可重入锁,因为网关是多线程/多任务的。
`hermes_cli/env_loader.py:52 @ 863e313`

```python
_SECRET_SOURCE_CACHE_LOCK = threading.RLock()
```

持锁调用私有实现。`hermes_cli/env_loader.py:184-185 @ 863e313`

```python
    with _SECRET_SOURCE_CACHE_LOCK:
        return _hydrate_profile_secret_sources(Path(hermes_home))
```

而启动路径的同名守卫**完全没有加这把锁**。`hermes_cli/env_loader.py:614-616 @ 863e313`

```python
    home_key = str(Path(home_path).resolve())
    if home_key in _APPLIED_HOMES:
        return
```

> **可疑缺陷 D-11(锁覆盖不全)**:`_apply_external_secret_sources`(启动路径,
> 同样读写 `_APPLIED_HOMES` / `_SECRET_SOURCES` / `_SECRET_SOURCE_VALUES_BY_HOME`)
> 与 `reset_secret_source_cache()` 都没有加锁。于是「网关热重载线程调
> `load_hermes_dotenv()`」与「路由线程调 `hydrate_profile_secret_sources()`」
> 对同一 home 可以同时通过守卫,双份 fetch + 双份状态行;更糟的是 `_hydrate_*`
> 只在 `values` 非空时写快照,而 `_apply_external_*` 无条件写(可能写空 dict),
> 两者交错时后写者赢。

复位接口(测试 / 长驻进程配置变更后强制重拉)。`hermes_cli/env_loader.py:241 @ 863e313`

```python
def reset_secret_source_cache() -> None:
```

三个全局一起清。`hermes_cli/env_loader.py:251-253 @ 863e313`

```python
    _APPLIED_HOMES.clear()
    _SECRET_SOURCES.clear()
    _SECRET_SOURCE_VALUES_BY_HOME.clear()
```

---

## 3. secret_prompt.py —— 带掩码回显的密码输入

### 3.1 解决什么问题

`getpass.getpass` 完全不回显,用户敲了多少字符心里没数,粘贴长 API key 时
经常怀疑「是不是没输进去」。这个模块给出「每敲一个字符回显一个 `*`」的体验,
同时保证密文不进终端。

### 3.2 怎么实现

核心是一个**注入式**的字符收集循环:读字符和写字符都是传进来的回调,
所以 POSIX / Windows 两套底层只需实现两个小函数,循环本身可被纯 Python 测试。
`hermes_cli/secret_prompt.py:16-22 @ 863e313`

```python
def _collect_masked_input(
    read_char: Callable[[], str],
    write: Callable[[str], object],
    prompt: str,
    *,
    mask: str = "*",
) -> str:
```

控制字符表。`hermes_cli/secret_prompt.py:11-13 @ 863e313`

```python
_BACKSPACE_CHARS = {"\b", "\x7f"}
_ENTER_CHARS = {"\r", "\n"}
_EOF_CHARS = {"\x04", "\x1a"}
```

循环处理五类输入:空串(流结束)→ EOFError;回车 → 返回;Ctrl-C → KeyboardInterrupt;
Ctrl-D / Ctrl-Z → EOFError;退格 → 弹出一个字符并写 `"\b \b"`(退一格、盖空格、再退一格)。
`hermes_cli/secret_prompt.py:28-45 @ 863e313`

```python
        ch = read_char()
        if ch == "":
            write("\r\n")
            raise EOFError
        if ch in _ENTER_CHARS:
            write("\r\n")
            return "".join(value)
        if ch == "\x03":
            write("\r\n")
            raise KeyboardInterrupt
        if ch in _EOF_CHARS:
            write("\r\n")
            raise EOFError
        if ch in _BACKSPACE_CHARS:
            if value:
                value.pop()
                write("\b \b")
            continue
```

**ESC 被丢弃**,理由是终端把方向键/删除键发成 ESC 前缀序列,不能让它们变成密文。
`hermes_cli/secret_prompt.py:46-49 @ 863e313`

```python
        if ch == "\x1b":
            # Ignore escape itself. Terminals commonly send escape-prefixed
            # navigation/delete sequences; they should not become secret text.
            continue
```

普通字符入列并回显掩码。`hermes_cli/secret_prompt.py:51-53 @ 863e313`

```python
        value.append(ch)
        if mask:
            write(mask)
```

> **可疑缺陷 D-12**:只丢弃 ESC 本身,**不丢弃后续的序列体**。在 POSIX raw 模式下
> 按一次「上箭头」发的是 `ESC [ A`:ESC 被吃掉,`[` 和 `A` 会**作为密文字符进入
> value**,并回显两个 `*`。用户看到两个星号、以为是自己的输入,实际密钥被污染成
> `...[A...`,后续认证失败且现象无法解释。这与注释自称的目的("they should
> not become secret text")直接冲突 —— 见 §8 C-4。

### 3.3 无 TTY 怎么办

`hermes_cli/secret_prompt.py:56 @ 863e313`

```python
def masked_secret_prompt(prompt: str, *, mask: str = "*") -> str:
```

**stdin 或 stdout 任一不是 TTY,直接退回 `getpass.getpass`。**
`hermes_cli/secret_prompt.py:65-66 @ 863e313`

```python
    if not _stream_is_tty(stdin) or not _stream_is_tty(stdout):
        return getpass.getpass(prompt)
```

`isatty()` 本身也可能抛(被替换过的 stream 对象),包一层。
`hermes_cli/secret_prompt.py:84-88 @ 863e313`

```python
def _stream_is_tty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False
```

**双层降级**:平台实现里任何非 KeyboardInterrupt/EOFError 的异常(没有 termios、
不是真终端、msvcrt 缺失)也回退到 getpass;但用户的中断/EOF 必须原样上抛。
`hermes_cli/secret_prompt.py:68-81 @ 863e313`

```python
    if os.name == "nt":
        try:
            return _masked_secret_prompt_windows(prompt, mask=mask)
        except (KeyboardInterrupt, EOFError):
            raise
        except Exception:
            return getpass.getpass(prompt)

    try:
        return _masked_secret_prompt_posix(prompt, mask=mask)
    except (KeyboardInterrupt, EOFError):
        raise
    except Exception:
        return getpass.getpass(prompt)
```

POSIX 实现:进 raw 模式,`finally` 里用 `TCSADRAIN` 恢复 —— 这是关键,
否则异常退出会把用户终端留在 raw 模式(打字不回显、Ctrl-C 失效)。
`hermes_cli/secret_prompt.py:108-126 @ 863e313`

```python
def _masked_secret_prompt_posix(prompt: str, *, mask: str) -> str:
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)

    def read_char() -> str:
        return sys.stdin.read(1)

    def write(text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()

    try:
        tty.setraw(fd)
        return _collect_masked_input(read_char, write, prompt, mask=mask)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
```

Windows 实现用 `msvcrt.getwch()`,并把功能键的双字节前缀(`\x00` / `\xe0`)
读掉第二个字节后**统一伪装成 ESC**,复用 POSIX 那条丢弃分支。
`hermes_cli/secret_prompt.py:91-99 @ 863e313`

```python
def _masked_secret_prompt_windows(prompt: str, *, mask: str) -> str:
    import msvcrt

    def read_char() -> str:
        ch = msvcrt.getwch()
        if ch in {"\x00", "\xe0"}:
            msvcrt.getwch()
            return "\x1b"
        return ch
```

> 有意思:Windows 路径把功能键**完整**吃掉(前缀 + 扫描码),因此 D-12 的问题
> **只存在于 POSIX**。这反过来证明作者知道该吃整个序列,只是 POSIX 侧没做。

---

## 4. skills_config.py —— `hermes skills` 的开关持久化

### 4.1 管什么 / schema

模块 docstring 直接给出 schema。`hermes_cli/skills_config.py:1-13 @ 863e313`

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

`DEFAULT_CONFIG` 的 `skills` 段。`hermes_cli/config_defaults.py:1791 @ 863e313`

```python
    "skills": {
```

> **注意:`skills.disabled` 和 `skills.platform_disabled` 都不在 `DEFAULT_CONFIG`
> 的 `skills` 段里**(我逐行看过 `hermes_cli/config_defaults.py:1791-1830`,
> 只有 `external_dirs` / `template_vars` / `inline_shell` /
> `inline_shell_timeout` / `guard_agent_created` / `write_approval`)。
> 因此它们不会被 strip-defaults 剥掉,写进去就一直在。

### 4.2 与主 config 的关系

它是 `hermes_cli.config` 的纯客户端。`hermes_cli/skills_config.py:16 @ 863e313`

```python
from hermes_cli.config import cfg_get, load_config, save_config
```

平台清单是 `hermes_cli.platforms` 的向后兼容视图(`{key: label}`),
并**排除 `api_server`**。`hermes_cli/skills_config.py:23 @ 863e313`

```python
PLATFORMS = {k: info.label for k, info in _PLATFORMS.items() if k != "api_server"}
```

### 4.3 读取语义:平台列表是「加」不是「替」

`hermes_cli/skills_config.py:44 @ 863e313`

```python
def get_disabled_skills(config: dict, platform: Optional[str] = None) -> Set[str]:
```

docstring 说明并集语义。`hermes_cli/skills_config.py:45-51 @ 863e313`

```python
    """Return disabled skill names: the global list unioned with the
    platform-specific list when a platform is given.

    A globally-disabled skill stays disabled on every platform, so the
    platform list adds to the global list rather than replacing it. This
    mirrors ``agent.skill_utils.get_disabled_skill_names``.
    """
```

`skills:` 为 YAML null 时不炸(`or {}`),非 dict 时返回空集。
`hermes_cli/skills_config.py:52-54 @ 863e313`

```python
    skills_cfg = config.get("skills") or {}
    if not isinstance(skills_cfg, dict):
        return set()
```

平台键缺失时**只返回全局集**(注意:`cfg_get` 对显式 `None` 会原样返回 None,
所以 `platform_disabled: {cli: null}` 也走这条路)。
`hermes_cli/skills_config.py:58-61 @ 863e313`

```python
    platform_disabled = cfg_get(skills_cfg, "platform_disabled", platform)
    if platform_disabled is None:
        return global_disabled
    return global_disabled | _normalize_skill_names(platform_disabled)
```

**标量兼容(真实 issue #13026)**:用户写 `disabled: my-skill`(不是列表)时,
必须当成单元素列表,而不是「字符串的字符集合」。
`hermes_cli/skills_config.py:27-41 @ 863e313`

```python
def _normalize_skill_names(values) -> Set[str]:
    """Normalize a config value into a set of skill names.

    Mirrors ``agent.skill_utils._normalize_string_set``: ``None`` (YAML null)
    means empty, a bare scalar (``disabled: my-skill``) means a single-item
    list — NOT a set of its characters (#13026).
    """
    if values is None:
        return set()
    if isinstance(values, str):
        values = [values]
    try:
        return {str(v).strip() for v in values if str(v).strip()}
    except TypeError:
        return set()
```

### 4.4 写入

`hermes_cli/skills_config.py:64 @ 863e313`

```python
def save_disabled_skills(config: dict, disabled: Set[str], platform: Optional[str] = None):
```

排序后写,保证 config.yaml diff 稳定。`hermes_cli/skills_config.py:66-72 @ 863e313`

```python
    config.setdefault("skills", {})
    if platform is None:
        config["skills"]["disabled"] = sorted(disabled)
    else:
        config["skills"].setdefault("platform_disabled", {})
        config["skills"]["platform_disabled"][platform] = sorted(disabled)
    save_config(config)
```

### 4.5 交互流程

入口:`hermes_cli/skills_config.py:150 @ 863e313`

```python
def skills_command(args=None):
```

技能发现委托给 `tools.skills_tool`,失败返回空表。
`hermes_cli/skills_config.py:77-83 @ 863e313`

```python
def _list_all_skills() -> List[dict]:
    """Return all installed skills (ignoring disabled state)."""
    try:
        from tools.skills_tool import _find_all_skills
        return _find_all_skills(skip_disabled=True)
    except Exception:
        return []
```

> **可疑缺陷 D-13(docstring 与参数名互相矛盾)**:docstring 说
> "Return all installed skills (**ignoring disabled state**)",而传的是
> `skip_disabled=True`,字面读是「跳过被禁用的」。
> 我**没有**打开 `tools/skills_tool.py` 核实该参数的真实语义,所以
> **未确证**这是笔误还是参数名反直觉。但这一点很关键:如果参数真的是
> 「过滤掉已禁用的技能」,那么 `skills_command` 拿到的列表就不含已禁用项,
> 界面上永远无法把一个已禁用技能**重新勾选回来**。

平台标签的取法。`hermes_cli/skills_config.py:163 @ 863e313`

```python
    platform_label = PLATFORMS.get(platform, "All platforms") if platform else "All platforms"
```

> **可疑缺陷 D-15**:因为 `_select_platform` 只可能返回 `None` 或 `PLATFORMS` 里的
> key,`.get()` 的第二参数 `"All platforms"` 是**不可达的死分支**。

UI 约定是「勾选 = 启用」,取消勾选的一律进 disabled。
`hermes_cli/skills_config.py:187-194 @ 863e313`

```python
        # "selected" = enabled (not disabled) — matches the [✓] convention
        pre_selected = {i for i, s in enumerate(skills) if s["name"] not in disabled}
        chosen = curses_checklist(
            f"Skills for {platform_label}",
            labels, pre_selected, cancel_returns=pre_selected,
        )
        # Anything NOT chosen is disabled
        new_disabled = {skills[i]["name"] for i in range(len(skills)) if i not in chosen}
```

分类模式入口。`hermes_cli/skills_config.py:119 @ 863e313`

```python
def _toggle_by_category(skills: List[dict], disabled: Set[str]) -> Set[str]:
```

一个分类「已启用」的定义是**并非其下所有技能都被禁用**。
`hermes_cli/skills_config.py:127-131 @ 863e313`

```python
    for i, cat in enumerate(categories):
        cat_skills = [s["name"] for s in skills if (s["category"] or "uncategorized") == cat]
        cat_labels.append(f"{cat} ({len(cat_skills)} skills)")
        if not all(s in disabled for s in cat_skills):
            pre_selected.add(i)
```

取消(Ctrl-C / Esc)通过 `cancel_returns=pre_selected` 表达为「维持原状」,
再由判等短路,不写盘。`hermes_cli/skills_config.py:196-198 @ 863e313`

```python
    if new_disabled == disabled:
        print(color("  No changes.", Colors.DIM))
        return
```

平台选择器:`hermes_cli/skills_config.py:93 @ 863e313`

```python
def _select_platform() -> Optional[str]:
```

回车 / 非法输入 / 中断**全部落到 global(None)**。`hermes_cli/skills_config.py:103-104 @ 863e313`

```python
    except (KeyboardInterrupt, EOFError):
        return None
```

> **可疑缺陷 D-14**:把 Ctrl-C 解释成「选 global」而不是「取消」。用户在平台选择
> 这一步按 Ctrl-C,流程会继续走到技能勾选界面,并且作用域是**全局**。
> 后果:本想给 telegram 关一个技能,结果给所有平台关了。

---

## 5. fallback_config.py —— 两代 fallback 键的合并

### 5.1 管什么

当主 provider 失败时,harness 会沿一条「provider + model(+ base_url)」的链继续尝试。
配置里有两代键:新的 `fallback_providers`(列表)和旧的 `fallback_model`
(单 dict 或列表)。这个模块把两者合成一条去重后的链。

`hermes_cli/fallback_config.py:80 @ 863e313`

```python
def get_fallback_chain(config: dict[str, Any] | None) -> list[dict[str, Any]]:
```

docstring 定义合并规则。`hermes_cli/fallback_config.py:81-87 @ 863e313`

```python
    """Return the effective fallback chain merged across old and new config keys.

    ``fallback_providers`` remains the primary source of truth and keeps its
    order. Legacy ``fallback_model`` entries are appended afterwards unless
    they target the same provider/model/base_url route as an earlier entry.
    The returned list always contains fresh dict copies.
    """
```

顺序与去重:先新后旧,身份三元组重复即跳过。
`hermes_cli/fallback_config.py:93-99 @ 863e313`

```python
    for key in ("fallback_providers", "fallback_model"):
        for entry in _iter_fallback_entries(config.get(key)):
            identity = _entry_identity(entry)
            if identity in seen:
                continue
            seen.add(identity)
            chain.append(entry)
```

**条目合法性**:单 dict 会被包成单元素列表。`hermes_cli/fallback_config.py:43-49 @ 863e313`

```python
def _iter_fallback_entries(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        candidates = [raw]
    elif isinstance(raw, list):
        candidates = raw
    else:
        return []
```

`provider` 和 `model` 两者都非空才算数。`hermes_cli/fallback_config.py:55-58 @ 863e313`

```python
        provider = str(entry.get("provider") or "").strip()
        model = str(entry.get("model") or "").strip()
        if not provider or not model:
            continue
```

**归一化**:返回的是 `dict(entry)` 的浅拷贝,provider/model 去空白,
base_url 去尾斜杠(空则不写该键)。`hermes_cli/fallback_config.py:60-68 @ 863e313`

```python
        normalized = dict(entry)
        normalized["provider"] = provider
        normalized["model"] = model

        base_url = _normalized_base_url(entry.get("base_url"))
        if base_url:
            normalized["base_url"] = base_url

        entries.append(normalized)
```

身份用小写三元组,和归一化用的规则一致。`hermes_cli/fallback_config.py:72-77 @ 863e313`

```python
def _entry_identity(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(entry.get("provider") or "").strip().lower(),
        str(entry.get("model") or "").strip().lower(),
        _normalized_base_url(entry.get("base_url")).lower(),
    )
```

> **注意**:`dict(entry)` 是**浅**拷贝,`extra_body` 这类嵌套 dict 与原 config 共享。
> docstring 说 "always contains fresh dict copies" —— 对顶层成立,对嵌套不成立。

### 5.2 单条目的 API key 解析(这一段最重要的安全点)

`hermes_cli/fallback_config.py:14 @ 863e313`

```python
def resolve_entry_api_key(entry: dict[str, Any] | None) -> str | None:
```

优先级:内联 `api_key` → `key_env` / `api_key_env` 指名的环境变量 → None
(None 表示交给 provider 的标准凭据解析)。
`hermes_cli/fallback_config.py:32-40 @ 863e313`

```python
    inline = str(entry.get("api_key") or "").strip()
    if inline:
        return inline
    key_env = str(entry.get("key_env") or entry.get("api_key_env") or "").strip()
    if key_env:
        from agent.secret_scope import get_secret

        return (get_secret(key_env) or "").strip() or None
    return None
```

**为什么必须走 `get_secret` 而不是 `os.getenv`**:多路复用网关里裸读 env 会忽略
当前 profile 的 scope,可能返回**另一个 profile 的凭据**。
`hermes_cli/fallback_config.py:22-28 @ 863e313`

```python
    ``key_env`` is resolved through ``agent.secret_scope.get_secret`` rather
    than a raw ``os.getenv`` — in a multiplexed gateway a bare env read would
    ignore the active profile's scope and can return another profile's
    credential. ``get_secret`` already implements the right fallback: it
    reads ``os.environ`` when there's no active multiplexed scope (matching
    prior single-profile behavior), and fails closed only when multiplexing
    is active with no scope installed.
```

这条规则有专门的回归测试(见 §10)。

### 5.3 与主 config 的关系

`get_fallback_chain` 接收一个**已加载的 config dict**,自己不读盘。
消费者之一是 CLI。`cli.py:4546 @ 863e313`

```python
        self._fallback_model = get_fallback_chain(CLI_CONFIG)
```

`fallback_model` 是 `_EXTRA_KNOWN_ROOT_KEYS` 里的合法根键(可选单 dict 或链)。
`hermes_cli/config.py:1856 @ 863e313`

```python
    "fallback_model",    # optional single dict or chain list; omitted when disabled
```

---

## 6. subcommands/config.py —— `hermes config` 的 argparse 声明

纯声明,零逻辑;handler 由调用方注入以避免 import `main`。
`hermes_cli/subcommands/config.py:1-5 @ 863e313`

```python
"""``hermes config`` subcommand parser.

Extracted verbatim from ``hermes_cli/main.py:main()`` (god-file Phase 2).
Handler injected to avoid importing ``main``.
"""
```

唯一的公开函数。`hermes_cli/subcommands/config.py:12 @ 863e313`

```python
def build_config_parser(subparsers, *, cmd_config: Callable) -> None:
```

子命令 dest 是 `config_command`。`hermes_cli/subcommands/config.py:22 @ 863e313`

```python
    config_subparsers = config_parser.add_subparsers(dest="config_command")
```

九个子命令。`show`:`hermes_cli/subcommands/config.py:25 @ 863e313`

```python
    config_subparsers.add_parser("show", help="Show current configuration")
```

`edit`:`hermes_cli/subcommands/config.py:28 @ 863e313`

```python
    config_subparsers.add_parser("edit", help="Open config file in editor")
```

`get`:`hermes_cli/subcommands/config.py:31 @ 863e313`

```python
    config_get = config_subparsers.add_parser(
```

`get --json`:`hermes_cli/subcommands/config.py:35 @ 863e313`

```python
    config_get.add_argument("--json", action="store_true", help="Print value as JSON")
```

`set`:`hermes_cli/subcommands/config.py:38 @ 863e313`

```python
    config_set = config_subparsers.add_parser("set", help="Set a configuration value")
```

`set --force` 的帮助文案:`hermes_cli/subcommands/config.py:43-48 @ 863e313`

```python
    config_set.add_argument(
        "--force",
        action="store_true",
        help="Skip the unknown-key notice printed after writing a key the "
        "running version doesn't recognize (the value is saved either way).",
    )
```

`unset`:`hermes_cli/subcommands/config.py:51 @ 863e313`

```python
    config_unset = config_subparsers.add_parser(
```

`path`:`hermes_cli/subcommands/config.py:57 @ 863e313`

```python
    config_subparsers.add_parser("path", help="Print config file path")
```

`env-path`:`hermes_cli/subcommands/config.py:60 @ 863e313`

```python
    config_subparsers.add_parser("env-path", help="Print .env file path")
```

`check`:`hermes_cli/subcommands/config.py:63 @ 863e313`

```python
    config_subparsers.add_parser("check", help="Check for missing/outdated config")
```

`migrate`:`hermes_cli/subcommands/config.py:66 @ 863e313`

```python
    config_subparsers.add_parser("migrate", help="Update config with new options")
```

handler 注入点。`hermes_cli/subcommands/config.py:68 @ 863e313`

```python
    config_parser.set_defaults(func=cmd_config)
```

**所有 key / value 参数都是 `nargs="?"`**,缺参不由 argparse 报错,而是由
`config_command` 打印带例子的用法并 `sys.exit(1)`。`hermes_cli/config.py:5131 @ 863e313`

```python
def config_command(args):
```

`config migrate` 就是 `migrate_config(interactive=True, quiet=False)` 的包装。
`hermes_cli/config.py:5231 @ 863e313`

```python
        results = migrate_config(interactive=True, quiet=False)
```

`config check` 是非交互版,只报不改。`hermes_cli/config.py:5244 @ 863e313`

```python
    elif subcmd == "check":
```

---

## 7. 配置键与环境变量穷举(本段六个文件里出现的每一个)

### 7.1 config.yaml 键

| 键 | 默认值 | 读/写点(@863e313) | 说明 |
|---|---|---|---|
| `_config_version` | `33` | 读 `hermes_cli/config.py:1841`;写 `hermes_cli/config.py:2367` | schema 版本;默认在 `hermes_cli/config_defaults.py:3126` |
| `custom_providers` | 无(缺省不存在) | 读+删 `hermes_cli/config_migrations.py:84,137` | v11 遗留 list;仍是合法根键 |
| `providers` | 无 | 写 `hermes_cli/config_migrations.py:86,135` | v12 起的 keyed 形状 |
| `providers.<k>.api` | — | 生成 `config.py:1490` | 由旧 `base_url`/`url`/`api` 转来 |
| `providers.<k>.api_key` | — | 删占位 `hermes_cli/config_migrations.py:128` | `no-key`/`no-key-required`/`""` 被删 |
| `providers.<k>.name` | — | `hermes_cli/config_migrations.py:127` | 源条目无名字时删掉 |
| `stt.model` | 无 | 读+删 `hermes_cli/config_migrations.py:181,185` | v14 删除的扁平键 |
| `stt.provider` | `"local"`(此处的取值默认) | `hermes_cli/config_migrations.py:182` | 决定搬到哪个子段 |
| `stt.local.model` | 默认 `"base"`(见注释 :207) | 写 `hermes_cli/config_migrations.py:204-205` | 只接受白名单值 |
| `stt.<provider>.model` | — | 写 `hermes_cli/config_migrations.py:213-214` | 云 provider 分支 |
| `display.interim_assistant_messages` | `True` | 写 `hermes_cli/config_migrations.py:232`;默认 `hermes_cli/config_defaults.py:1193` | v15;实际会被 strip |
| `display.tool_progress_overrides` | 无 | 只读不删 `hermes_cli/config_migrations.py:250` | v16 遗留 |
| `display.platforms.<plat>.tool_progress` | 无 | 写 `hermes_cli/config_migrations.py:259` | v16 目标 |
| `compression.summary_model` | 无 | pop `hermes_cli/config_migrations.py:278` | v17 删除 |
| `compression.summary_provider` | 无 | pop `hermes_cli/config_migrations.py:279` | `"auto"` 视同未设 |
| `compression.summary_base_url` | 无 | pop `hermes_cli/config_migrations.py:280` | — |
| `auxiliary.compression.model/provider/base_url` | — | 写 `hermes_cli/config_migrations.py:287,293,299` | v17 目标 |
| `plugins.enabled` | 无(非默认根键) | 写 `hermes_cli/config_migrations.py:364` | v21 opt-in 白名单 |
| `plugins.disabled` | 无 | 读 `hermes_cli/config_migrations.py:334` | 排除项 |
| `curator.enabled` | `True` | `hermes_cli/config_migrations.py:424-427`;默认 `hermes_cli/config_defaults.py:1843` | v23 |
| `curator.interval_hours` | `24 * 7` | 同上;默认 `hermes_cli/config_defaults.py:1845` | |
| `curator.min_idle_hours` | `2` | 同上;默认 `hermes_cli/config_defaults.py:1847` | |
| `curator.stale_after_days` | `30` | 同上;默认 `hermes_cli/config_defaults.py:1849` | |
| `curator.archive_after_days` | `90` | 同上;默认 `hermes_cli/config_defaults.py:1852` | |
| `curator.consolidate` | `False` | 无迁移,仅注释 `hermes_cli/config_migrations.py:528-536` | v30 只改默认 |
| `auxiliary.curator.provider` | `"auto"` | `hermes_cli/config_migrations.py:443-445`;默认 `hermes_cli/config_defaults.py:1006` | |
| `auxiliary.curator.model` | `""` | 同上;`hermes_cli/config_defaults.py:1007` | |
| `auxiliary.curator.base_url` | `""` | 同上;`hermes_cli/config_defaults.py:1008` | |
| `auxiliary.curator.api_key` | `""` | 同上;`hermes_cli/config_defaults.py:1009` | |
| `auxiliary.curator.timeout` | `600` | 同上;`hermes_cli/config_defaults.py:1010` | |
| `auxiliary.curator.extra_body` | `{}` | 同上;`hermes_cli/config_defaults.py:1011` | |
| `auxiliary.curator.reasoning_effort` | `""` | 同上;`hermes_cli/config_defaults.py:1012` | 注释里未列,代码会拷 |
| `model_catalog.ttl_hours` | `1` | 改写 `hermes_cli/config_migrations.py:486-487`;默认 `hermes_cli/config_defaults.py:2397` | 只改 24 |
| `memory.write_mode` | 无 | pop `hermes_cli/config_migrations.py:514` | v29 删除 |
| `skills.write_mode` | 无 | pop `hermes_cli/config_migrations.py:514` | v29 删除 |
| `memory.write_approval` / `skills.write_approval` | `False` | 写 `hermes_cli/config_migrations.py:516`;默认 `hermes_cli/config_defaults.py:1829` | 只有 `"approve"` → True |
| `agent.verify_on_stop` | `"auto"` | 写 `hermes_cli/config_migrations.py:562,594`;默认 `hermes_cli/config_defaults.py:158` | 见 C-3 |
| `delegation.max_async_children` | 无 | pop `hermes_cli/config_migrations.py:621` | v33 删除 |
| `delegation.max_concurrent_children` | `3` | 写 `hermes_cli/config_migrations.py:632`;默认 `hermes_cli/config_defaults.py:1709` | 取 max |
| `secrets` | 见 `hermes_cli/config_defaults.py:2875` | 读 `hermes_cli/env_loader.py:730,742` | 只读这一段 |
| `secrets.sources` | 无(注释掉) | 读 `agent/secret_sources/registry.py:265` | 显式顺序 |
| `secrets.preserve_existing` | 无 | 读 `agent/secret_sources/registry.py:370` | 最高优先保留 |
| `secrets.profile_alias` | `True` | 读 `agent/secret_sources/registry.py:375` | profile 别名 |
| `secrets.bitwarden.enabled` | `False` | `hermes_cli/config_defaults.py:2889` | 总开关 |
| `secrets.bitwarden.access_token_env` | `"BWS_ACCESS_TOKEN"` | `hermes_cli/config_defaults.py:2893` | bootstrap env 名 |
| `secrets.bitwarden.project_id` | `""` | `hermes_cli/config_defaults.py:2895` | |
| `secrets.bitwarden.cache_ttl_seconds` | `300` | `hermes_cli/config_defaults.py:2898` | |
| `secrets.bitwarden.encrypted_cache.enabled` | `False` | `hermes_cli/config_defaults.py:2905` | |
| `secrets.bitwarden.encrypted_cache.max_stale_seconds` | `0` | `hermes_cli/config_defaults.py:2906` | |
| `secrets.bitwarden.override_existing` | `True` | `hermes_cli/config_defaults.py:2912` | 反转 env 优先 |
| `secrets.bitwarden.auto_install` | `True` | `hermes_cli/config_defaults.py:2916` | 自动下 bws |
| `secrets.bitwarden.server_url` | `""` | `hermes_cli/config_defaults.py:2924` | |
| `secrets.onepassword.enabled` | `False` | `hermes_cli/config_defaults.py:2929` | |
| `secrets.onepassword.env` | `{}` | `hermes_cli/config_defaults.py:2933` | VAR → `op://…` |
| `secrets.onepassword.account` | `""` | `hermes_cli/config_defaults.py:2936` | |
| `secrets.onepassword.service_account_token_env` | `"OP_SERVICE_ACCOUNT_TOKEN"` | `hermes_cli/config_defaults.py:2941` | |
| `secrets.onepassword.binary_path` | `""` | `hermes_cli/config_defaults.py:2945` | |
| `secrets.onepassword.cache_ttl_seconds` | `300` | `hermes_cli/config_defaults.py:2948` | |
| `secrets.onepassword.override_existing` | `True` | `hermes_cli/config_defaults.py:2952` | |
| `terminal.*`(19 个键) | 见 `config_defaults.py` terminal 段 | 桥接 `hermes_cli/env_loader.py:554` → `config.py:3183-3205` | 显式键覆盖 env |
| `skills.disabled` | 无(不在 DEFAULT_CONFIG) | 读 `hermes_cli/skills_config.py:55`;写 `hermes_cli/skills_config.py:68` | 全局禁用列表 |
| `skills.platform_disabled.<platform>` | 无 | 读 `hermes_cli/skills_config.py:58`;写 `hermes_cli/skills_config.py:71` | 与全局取并集 |
| `fallback_providers` | 无 | 读 `hermes_cli/fallback_config.py:93` | 新键,保序 |
| `fallback_model` | 无 | 读 `hermes_cli/fallback_config.py:93` | 旧键,追加去重 |
| `<fallback entry>.provider` / `.model` | — | `hermes_cli/fallback_config.py:55-56` | 两者必填 |
| `<fallback entry>.base_url` | — | `hermes_cli/fallback_config.py:64` | 去尾斜杠 |
| `<fallback entry>.api_key` | — | `hermes_cli/fallback_config.py:32` | 内联,最高优先 |
| `<fallback entry>.key_env` / `.api_key_env` | — | `hermes_cli/fallback_config.py:35` | 环境变量名,经 secret scope |
| `updates.pre_update_backup` | `"quick"` | `hermes_cli/update_cmd.py:2532`;默认 `hermes_cli/config_defaults.py:2765` | 迁移的唯一"备份"来源 |

### 7.2 环境变量

| 变量 | 默认/回退 | 读写点(@863e313) | 说明 |
|---|---|---|---|
| `HERMES_HOME` | `Path.home()/".hermes"`(**本文件自己的回退**) | `hermes_cli/env_loader.py:477` | 见 D-5/D-6:与 `hermes_constants.get_hermes_home()` 的回退链不一致 |
| `HERMES_HOME` | 平台默认 + ContextVar 覆盖 | `hermes_constants.py:71,132-139`,经 `hermes_cli/env_loader.py:748` | `_process_hermes_home()` 用的是这一条 |
| `HERMES_HOME`(写) | — | `hermes_cli/env_loader.py:220` | 冷 profile 补水时塞进私有 env |
| `OP_SERVICE_ACCOUNT_TOKEN` | 无 | `hermes_cli/env_loader.py:505` | 存在则跳过 `.op.env` 装载 |
| `HERMES_MANAGED_DIR` | `/etc/hermes` | `hermes_cli/managed_scope.py:65`,经 `hermes_cli/env_loader.py:579` | managed scope 目录 |
| `HERMES_ACP_AUTH_METHOD` | — | `hermes_cli/env_loader.py:77` | profile-managed,缺失即清 |
| `HERMES_ACP_AUTO_APPROVE` | — | `hermes_cli/env_loader.py:78` | 同上 |
| `HERMES_COPILOT_ACP_COMMAND` | — | `hermes_cli/env_loader.py:79` | 同上 |
| `HERMES_COPILOT_ACP_ARGS` | — | `hermes_cli/env_loader.py:80` | 同上 |
| `COPILOT_CLI_PATH` | — | `hermes_cli/env_loader.py:81` | 同上 |
| `COPILOT_ACP_BASE_URL` | — | `hermes_cli/env_loader.py:82` | 同上 |
| `*_API_KEY` / `*_TOKEN` / `*_SECRET` / `*_KEY` | — | `hermes_cli/env_loader.py:20,311` | 后缀匹配即 ASCII 清洗(全 `os.environ` 扫描) |
| `LLM_MODEL` | — | `hermes_cli/config_migrations.py:155-159` | v13 置空(死变量) |
| `OPENAI_MODEL` | — | `hermes_cli/config_migrations.py:155-159` | 同上 |
| `HERMES_TOOL_PROGRESS_MODE` | — | 提及 `hermes_cli/config_migrations.py:49`;白名单 `config.py:301` | 已弃用但运行期仍读 |
| `HERMES_TOOL_PROGRESS`(布尔版) | — | `config.py:298-300` 注释 | v12 底线后完全不支持 |
| `BWS_ACCESS_TOKEN` | — | 由 `secrets.bitwarden.access_token_env` 指名 | Bitwarden bootstrap |
| `TERMINAL_ENV` 等 19 个 `TERMINAL_*` | — | `hermes_cli/config.py:3184-3205`,桥自 `hermes_cli/env_loader.py:554` | config.yaml 显式键会覆盖 |
| `HERMES_VERIFY_ON_STOP` | 无 | `agent/verification_stop.py:107` | 优先于 `agent.verify_on_stop`(迁移目标键的 env 兄弟) |

---

## 8. 文档与代码的出入

**C-1 · 注释说闸门在 `run_migrations()`,实际在 `migrate_config`。**
`hermes_cli/config_migrations.py:653-654 @ 863e313`

```python
    # every remaining step below. Only configs BELOW 12 are refused by the
    # floor gate in run_migrations().
```

同文件另一处注释反而说对了。`hermes_cli/config.py:2180-2182 @ 863e313`

```python
    # crashes on an ancient config. The floor gate lives here in the wrapper
    # (not in run_migrations) so the registry driver stays a pure mechanism
    # that tests can exercise directly.
```

---

**C-2 · v23 承诺「用户能在 config.yaml 里看到并编辑 curator 设置」,但写入的纯默认值会被 strip 掉。**
`_persist_migration` 的不变量恰恰禁止落盘纯默认值。`hermes_cli/config.py:2129-2131 @ 863e313`

```python
    default, plus explicit removals/renames of user data. Pure schema defaults
    are never materialised to disk — ``load_config()``'s deep-merge supplies
    them at read time, so writing them adds nothing and actively shadows future
```

v15 的 `display.interim_assistant_messages=true` 也是同一情况。
`hermes_cli/config_migrations.py:234 @ 863e313`

```python
        results["config_added"].append("display.interim_assistant_messages=true (default)")
```

> 从代码看,**不变量赢**:这几步的实际净效果只是往 `results["config_added"]`
> 里塞条目和打印一行,盘上不会多出这些键。

---

**C-3 · v31 注释说 "The new default is OFF",但 `DEFAULT_CONFIG` 至今是 `"auto"`。**
`hermes_cli/config_migrations.py:543-544 @ 863e313`

```python
    # more noise than signal — it even fired on doc/markdown/skill edits with
    # nothing to verify. The new default is OFF. This migration switches
```

`DEFAULT_CONFIG` 的注释仍然在描述旧语义。`hermes_cli/config_defaults.py:151-156 @ 863e313`

```python
        # or the agent explains why it cannot run checks. The loop is bounded
        # and uses the passive verification ledger. Default is "auto" —
        # surface-aware: on for interactive coding surfaces (CLI, TUI, desktop)
        # and programmatic callers, off for conversational messaging surfaces
        # (Telegram, Discord, etc.) where the verification narrative would reach
        # a human as chat noise. Doc/markdown/skill-only edits never fire it.
```

结果:**升级用户 = OFF,全新安装 = auto(CLI 上 ON)**。

---

**C-4 · `secret_prompt` 注释说 escape 前缀序列「不该成为密文」,但只丢了 ESC 本身。**
`hermes_cli/secret_prompt.py:47-48 @ 863e313`

```python
            # Ignore escape itself. Terminals commonly send escape-prefixed
            # navigation/delete sequences; they should not become secret text.
```

序列体(`[`、`A` 等)照样走到追加分支。`hermes_cli/secret_prompt.py:51 @ 863e313`

```python
        value.append(ch)
```

---

**C-5 · `hermes config set --force` 的 argparse 帮助说「值反正会被保存」,实际不带 `--force` 会 `sys.exit(1)` 不保存。**
帮助文案:`hermes_cli/subcommands/config.py:46-47 @ 863e313`

```python
        help="Skip the unknown-key notice printed after writing a key the "
        "running version doesn't recognize (the value is saved either way).",
```

实际 `--force` 还有第二个作用。`hermes_cli/config.py:4950 @ 863e313`

```python
            elif not force:
```

不带它会直接退出,值不落盘。`hermes_cli/config.py:4981 @ 863e313`

```python
                sys.exit(1)
```

`config_command` 自己打印的用法反而写全了两条。`hermes_cli/config.py:5165-5166 @ 863e313`

```python
            print("  --force: skip the unknown-key notice for unrecognized keys,")
            print("           and allow a scalar to replace a whole mapping section")
```

---

**C-6 · `hermes config migrate` 打印「N 个新配置项将以默认值加入」,但迁移不写默认值。**
`hermes_cli/config.py:5207-5208 @ 863e313`

```python
        if missing_config:
            print(f"\n  {len(missing_config)} new config option(s) will be added with defaults")
```

`migrate_config` 里只上报不落盘。`hermes_cli/config.py:2361-2363 @ 863e313`

```python
    missing_config = get_missing_config_fields()
    if missing_config:
        results["config_added"].extend(field["key"] for field in missing_config)
```

---

**C-7 · `_list_all_skills` docstring 与参数取值相反。**
`hermes_cli/skills_config.py:78-81 @ 863e313`

```python
    """Return all installed skills (ignoring disabled state)."""
    try:
        from tools.skills_tool import _find_all_skills
        return _find_all_skills(skip_disabled=True)
```

(是否真的矛盾取决于 `_find_all_skills` 的参数语义,**未确证** —— 我没读那个文件。)

---

**C-8 · `get_fallback_chain` 说返回「fresh dict copies」,实际是浅拷贝。**
`hermes_cli/fallback_config.py:86 @ 863e313`

```python
    The returned list always contains fresh dict copies.
```

实现只做了顶层 `dict()`。`hermes_cli/fallback_config.py:60 @ 863e313`

```python
        normalized = dict(entry)
```

---

## 9. 可疑缺陷汇总(只记录不修)

| # | 位置 | 问题 | 怎么会踩到 |
|---|---|---|---|
| D-1 | `hermes_cli/config_migrations.py:155-159` | v13 用 `get_env_value`(先读 `os.environ`)判定「.env 里有旧值」,然后往 .env 写 `KEY=` | 用户只在 shell 里 `export LLM_MODEL=x` ⇒ .env 被凭空追加一行 `LLM_MODEL=`,且下次启动以 override 覆盖掉 shell 值 |
| D-2 | `hermes_cli/config_migrations.py:361-362` | v21 插件扫描的 `except` 把已收集的名字**全清空**,然后照样落盘并一次性完成 | 扫到第 N 个插件目录时 I/O 出错 ⇒ 前面 N-1 个已装插件被静默关掉,且因 `enabled` 已存在无法重试 |
| D-3 | `hermes_cli/config_migrations.py:409-413` | v23 `except` 分支引用可能未赋值的 `curator_dir` → `UnboundLocalError` | `get_hermes_home()` 抛异常(如 `HERMES_HOME` 含 NUL)⇒ 异常处理器自己抛,整个 `migrate_config` 挂掉 |
| D-4 | `hermes_cli/config_migrations.py:626,628` | v33 把 `max_concurrent_children` 的默认值 3 硬编码 | 将来改默认值(如 5)后,存量 `max_async_children: 4` 会把上限**下调**到 4 |
| D-5 | `hermes_cli/env_loader.py:477` | `os.getenv("HERMES_HOME", Path.home()/".hermes")` 未 `strip()`、未判空串 | `HERMES_HOME=""` ⇒ `Path("")` = `.` ⇒ 把 **当前工作目录的 `./.env`** 当成 user env 以 `override=True` 装载 |
| D-6 | `hermes_cli/env_loader.py:477` vs `hermes_constants.py:53-59` | 同上一行硬编码 `~/.hermes`,不走平台默认,也不认 ContextVar 覆盖 | Windows 上其余代码用 `%LOCALAPPDATA%/hermes`,`load_hermes_dotenv()` 却去 `~/.hermes` 找 .env ⇒ 凭据装不进来;同时 `_reapply_terminal_config_bridge` 的 home 比较必然不等 ⇒ terminal 桥被跳过 |
| D-7 | `hermes_cli/env_loader.py:55-66` | `_known_hermes_env_keys()` 定义了但**无调用点** | 死代码;读者会误以为清扫范围是「全部已知 Hermes 键」,实际只有 6 个 |
| D-8 | `hermes_cli/env_loader.py:20,310` | `_KEY` 后缀过宽 + 遍历整个 `os.environ` | 非 ASCII 路径下的 `TERMINAL_SSH_KEY` 被静默改写成不存在的路径,警告文案还误导为「从 PDF 复制」;第三方 `*_KEY` 变量也被改 |
| D-9 | `hermes_cli/env_loader.py:443-451` | 预清洗重写 .env 时不恢复原文件权限 | 0640 的 Docker volume mount .env 被清洗一次后变成 mkstemp 的 0600(`save_env_value` 有恢复逻辑,这里没有) |
| D-10 | `hermes_cli/env_loader.py:725` | `home_path == _process_hermes_home()` 用 `Path.__eq__`,同族其他处用 `.resolve()` | 传入带尾斜杠 / 相对 / symlink 路径时白白多解析一次 config.yaml(仅性能) |
| D-11 | `hermes_cli/env_loader.py:614-669` 无锁 vs `:184` 有锁 | 两条写同一批全局字典的路径只有一条加了 `_SECRET_SOURCE_CACHE_LOCK` | 网关热重载线程与首轮路由线程并发 ⇒ 同一 home 双份 fetch/状态行;`_SECRET_SOURCE_VALUES_BY_HOME` 交错写,可能被空 dict 覆盖 |
| D-12 | `hermes_cli/secret_prompt.py:46-51` | 只吞 ESC,不吞后续序列体(POSIX 侧;Windows 侧吞得完整) | 输密码时误按方向键 ⇒ `[A` 进入密钥、回显两个 `*`,认证失败且无法自查 |
| D-13 | `hermes_cli/skills_config.py:78-81` | docstring 与 `skip_disabled=True` 语义相反(**未确证**) | 若参数真是「过滤已禁用」,则已禁用技能不出现在勾选界面,**无法重新启用** |
| D-14 | `hermes_cli/skills_config.py:103-104` | 平台选择器把 Ctrl-C/EOF 当成「选 global」 | 想给单平台改设置的用户中途按 Ctrl-C,流程继续并作用于**全部平台** |
| D-15 | `hermes_cli/skills_config.py:163` | `PLATFORMS.get(platform, "All platforms")` 的默认分支不可达 | 死分支;`platform` 非 None 时必在 `PLATFORMS` 里 |
| D-16 | `hermes_cli/config_migrations.py:250-266` | v16 搬完不删 `display.tool_progress_overrides` | 旧键永久留在 config.yaml;与 v12/v17/v29/v33 的删除风格不一致(**是否有意未确证**) |
| D-17 | `hermes_cli/config_migrations.py:561-563` | v31 在 `agent` 不是 dict 时用 `{}` 替换整段 | 用户手写 `agent: some-string` ⇒ 该值被静默丢弃,换成 `{"verify_on_stop": False}` |

---

## 10. 配套测试(行为规格)

**config_migrations / migrate_config**
- `tests/hermes_cli/test_config.py` —— 含 `ENV_VARS_BY_VERSION` 与 migrate 相关断言
- `tests/hermes_cli/test_cmd_update.py`、`tests/hermes_cli/test_update_yes_flag.py`、
  `tests/hermes_cli/test_update_autostash.py` —— `hermes update` 里的迁移调用路径
- `tests/hermes_cli/test_mcp_security.py` —— migrate 后的 MCP 条目禁用
- `tests/gateway/test_display_config.py` —— display 段迁移结果
- `tests/tools/test_docker_config_migrate.py`、`tests/docker/test_config_migration.py` ——
  Docker 场景 + 底线拒绝(`scripts/docker_config_migrate.py:66` 注释提到 floor)
- `tests/gateway/test_whatsapp_reply_prefix.py:117-122` —— 版本号 ≥ `max(ENV_VARS_BY_VERSION)` 的回归守卫

**env_loader**
- `tests/hermes_cli/test_env_loader.py`(442 行,17 个用例)—— 本段的主规格:
  UTF-16 BOM 保留非 ASCII 值、UTF-32 原样不动 + 一次性警告、纯 UTF-8 回归、
  cp1252 不崩、profile-managed 键清扫的**范围**、空赋值保留、
  无 user env 时不清扫、`export KEY=` 形式被认、shell 导出的凭据存活、
  config.yaml 的 `terminal.backend` 覆盖陈旧 env / 陈旧 shell、
  无 terminal 段不动 env、别的 profile 的 home 不桥接本进程 config
- `tests/hermes_cli/test_env_sanitize_on_load.py` —— 装载时清洗
- `tests/hermes_cli/test_non_ascii_credential.py` —— ASCII 清洗
- `tests/test_env_loader_secret_sources.py`、`tests/test_env_loader_applied_homes.py`、
  `tests/test_env_loader_op_bootstrap.py` —— 外部源 / once-per-home / `.op.env`
- `tests/test_bitwarden_secrets.py`、`tests/test_command_secret_source.py`、
  `tests/secret_sources/test_error_remediation.py`
- `tests/gateway/test_multiplex_credential_isolation.py`、`tests/agent/test_secret_scope.py`、
  `tests/agent/test_credential_pool.py` —— per-home 快照的下游
- `tests/hermes_cli/test_managed_scope_env.py`、`tests/hermes_cli/test_managed_scope_regression.py`
- `tests/hermes_cli/test_dump_terminal_backend.py`、`tests/hermes_cli/test_env_export_prefix.py`、
  `tests/hermes_cli/test_env_load_cache.py`

**secret_prompt**
- `tests/hermes_cli/test_secret_prompt.py`(56 行)—— 掩码不泄露原文、Ctrl-C 上抛、
  非 TTY 回退 getpass。注意:**没有**覆盖 ESC 序列(D-12 因此没被抓到)
- `tests/hermes_cli/test_secrets_bitwarden_non_tty.py`

**skills_config**
- `tests/hermes_cli/test_skills_config.py`(174 行)—— 空 config、`skills: null`(#13026)、
  保存时排序、平台禁用与 `HERMES_PLATFORM` env

**fallback_config**
- `tests/hermes_cli/test_fallback_config.py`(39 行)—— 内联 key 优先、纯空白内联回退到
  `key_env`、**多路复用下 scope 值压过 `os.environ`(#74311)**、无 scope 时仍读 env
- `tests/hermes_cli/test_fallback_cmd.py`

**subcommands/config**
- `tests/hermes_cli/test_subcommands_batch.py:69,86` —— parser 挂载与 handler 路由

---

## 11. 重实现要点

如果要从零重写这一簇,以下八条是必须知道的:

1. **版本号只读一次,阶梯不推进。** 每个 `_migrate_to_N` 都跟同一个初始版本比较,
   而不是「跑完一步就 +1」。这让阶梯的行为等价于一串顺序 `if`,可以随意插入
   新步骤而不改动已有步骤的触发条件;代价是**每一步必须自己保证幂等**,因为
   中途失败后下次会从同一个起点重跑一遍。

2. **迁移写盘必须走一个唯一的 helper,并强制「只落非默认值」。**
   `_persist_migration` 存在的全部意义就是让「不材料化默认值」这条不变量无法被
   逐个迁移地退化。反面教训在代码里明写着:`strip_defaults=False` 的年代把
   `verify_on_stop: true` 写进了每一个用户的 config.yaml,后来要用两步迁移
   (v31 + v32)才擦干净。**但这条不变量也会吃掉「让用户看见默认值」这类诉求
   ——设计时必须在两者中明确选一个,不能两个注释各说各话(见 C-2)。**

3. **给自动迁移设一个支持底线,并把「显式旧版本」与「没有版本键」区分开。**
   底线以下不改一个字节,只给一条可操作的文案(备份 + 重生成 / 手改版本号)。
   区分那两种形状是关键:profile 克隆和手写的两行 config 是**新**配置,不能被拒。

4. **迁移不做备份 —— 备份是上层(`hermes update`)的职责。**
   如果你的迁移会删用户数据(本仓有 5 个步骤会 pop 键),要么自己写 `.bak`,
   要么像本仓这样在更新流程里做快照 + 事后对比恢复(cron/jobs.json 被清空过)。

5. **.env 装载的优先级要写成一张显式的表,并且允许 config 反压 env。**
   本仓最终的顺序是:shell < project .env < .op.env < user .env < 外部密钥源
   < managed .env < config.yaml 的显式 `terminal.*`。最后一条(config 压 env)
   是被两个真实 issue 逼出来的:长驻进程反复 reload dotenv,陈旧的
   `TERMINAL_ENV` 会在会话中途翻回去。

6. **凭据在进 `os.environ` 之前必须做两级清洗,而且都要出声。**
   文件级:BOM 嗅探必须先查 UTF-32 再查 UTF-16(前者的 BOM 以后者的 BOM 开头),
   查到无法安全处理的编码就**原样不动**而不是 `errors=replace` 重写;
   值级:凭据必须是纯 ASCII(要当 HTTP header),清洗后打印被剥掉的码点。
   **静默清洗等于把复制粘贴污染伪装成 provider 的 "invalid API key"。**
   同时注意后缀匹配的范围:`_KEY` 会误伤路径类变量。

7. **多 profile 共享一个 `os.environ` 时,外部密钥必须在应用当时拍不可变快照,按 home 分桶。**
   否则第二个 profile 的应用会覆盖第一个的值,而任何「事后从 `os.environ` 还原」
   的做法都会拿错。快照的消费者是每轮安装的 secret scope。
   守卫用「每个 home 一次」,但**只有真发起过 fetch 才标记**——配置解析失败、
   没有 secrets 段、没有启用的源,这三种情况都要保持可重试,否则用户改好配置后
   本进程永远加载不了。

8. **交互式密码输入:注入 read/write 回调,平台差异只写两个小函数。**
   POSIX 用 `tty.setraw` 且**必须**在 `finally` 里 `tcsetattr(TCSADRAIN)` 复位;
   任何非中断异常都回退 `getpass`;stdin/stdout 任一非 TTY 直接 `getpass`。
   转义序列要**整段**吃掉(读到 ESC 后继续读完序列体),只吃 ESC 会让
   `[A` 进入密文 —— 本仓 Windows 侧做对了,POSIX 侧没有。
