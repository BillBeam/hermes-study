# r8a-raw-config-a · config.py:1-1400

底稿。基线 `863e31318553cda8ad61df681d08175364d4164b`(下简写 `863e313`)。
负责段落:`hermes_cli/config.py` 第 1–1400 行(全文 5434 行)。
为了把"配置加载与解析链"讲完整,本稿也读并引用了 1400 行之后的
`_deep_merge` / `_expand_env_vars` / `read_raw_config` / `load_config` /
`_load_config_impl`,以及 `hermes_constants.py`、`hermes_cli/main.py`、
`hermes_cli/profiles.py`、`hermes_cli/managed_scope.py`、`hermes_cli/env_loader.py`
的相关片段;这些段落的**精读归属不在本稿**,这里只取"链路必需"的部分。

凡断言紧跟 `路径:行号 @ 863e313` 与原文代码块。

---

## 0. 这一段在系统里的位置

`hermes_cli/config.py` 是 Hermes 唯一的配置总线。1-1400 行里**没有** `load_config()`
本体(它在 3115 行),这一段装的是 `load_config()` 依赖的**全部前置设施**:

| 区段 | 内容 |
|---|---|
| 39–155 | 损坏 config.yaml 的告警去重 + 备份(`_CONFIG_PARSE_WARNED` / `_backup_corrupt_config` / `_warn_config_parse_failure`) |
| 157–233 | `.env` 写入器的变量名 denylist |
| 235–260 | 三张进程级缓存表 + 一把 `threading.RLock` |
| 263–327 | `_EXTRA_ENV_KEYS`(setup 向导之外被管理的 .env 键名全集) |
| 334–634 | managed 模式(NixOS)+ 安装方式检测/打戳 |
| 637–683 | container 模式元数据(`.container-mode`) |
| 686–704 | **config.yaml / .env / 安装目录的物理定位** |
| 706–936 | HERMES_HOME 目录骨架、权限、属主、SOUL.md 播种 |
| 939–989 | 默认值来源(`config_defaults`)、缺失键盘点 |
| 992–1186 | dotted-key 导航(set/get/unset)+ `hermes config set` 的 .env 路由判定 |
| 1189–1261 | 缺失配置项 / 缺失 skill 配置项盘点 |
| 1264–1474 | 自定义 provider 条目归一化 + 告警去重 |

一句话:**这 1400 行是"文件在哪、目录能不能用、坏了怎么办、缓存怎么失效"**,
真正的 merge/expand 在后半段。

---

## 1. 机制:config.yaml 与 .env 的物理位置

### 1.1 解决什么问题

Hermes 同时要满足:单用户 `~/.hermes`、Windows 原生路径、Docker 把状态目录挂到
`/opt/data`、多 profile(同一台机器上多套完全隔离的 home)、以及同一进程内不同任务
临时切 home(dashboard 的 `--open-profile`)。这些必须收敛到**一个**解析函数,否则
"配置读到 A、日志写到 B"。

### 1.2 怎么实现:一条四级 fallback 链

`config.py` 自己**不定义** home,它从 `hermes_constants` 重新导出。`hermes_cli/config.py:691 @ 863e313`

```python
from hermes_constants import get_hermes_home, get_process_hermes_home  # noqa: F811,E402
```

两个文件路径就是 home 拼常量,没有任何 env 覆盖。`hermes_cli/config.py:694-696 @ 863e313`

```python
def get_config_path() -> Path:
    """Get the main config file path."""
    return get_hermes_home() / "config.yaml"
```

`hermes_cli/config.py:698-700 @ 863e313`

```python
def get_env_path() -> Path:
    """Get the .env file path (for API keys)."""
    return get_hermes_home() / ".env"
```

注意第三个路径 `get_project_root()` 语义完全不同 —— 它是**跑着的代码**所在目录,
不是数据目录。`hermes_cli/config.py:702-704 @ 863e313`

```python
def get_project_root() -> Path:
    """Get the project installation directory."""
    return Path(__file__).parent.parent.resolve()
```

home 本身的解析顺序:**context-local override → `HERMES_HOME` env → 平台默认**。`hermes_constants.py:132 @ 863e313`

```python
    override = get_hermes_home_override()
```

`hermes_constants.py:62-74 @ 863e313`

```python
def _hermes_home_from_env() -> Path:
    """Resolve HERMES_HOME from the process environment only.

    Reads the ``HERMES_HOME`` env var, falling back to the platform-native
    default.  Deliberately ignores the context-local override installed by
    :func:`set_hermes_home_override`, so this reflects the process/launch
    scope rather than a per-task profile.  Shared by :func:`get_hermes_home`
    and :func:`get_process_hermes_home` so the two never drift.
    """
    val = os.environ.get("HERMES_HOME", "").strip()
    if val:
        return Path(val)
    return _get_platform_default_hermes_home()
```

平台默认在 Windows 上**不是** `~/.hermes`。`hermes_constants.py:53-59 @ 863e313`

```python
def _get_platform_default_hermes_home() -> Path:
    """Return the platform-native default Hermes home path."""
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
        return base / "hermes"
    return Path.home() / ".hermes"
```

### 1.3 profile 怎么进来的:在 argparse 之前改写 `os.environ`

关键设计:profile **不是**一个被 `config.py` 读的键,它是 CLI 入口在**任何 hermes 模块
被 import 之前**把 `HERMES_HOME` 改掉。`hermes_cli/main.py:517-518 @ 863e313`

```python
def _apply_profile_override() -> None:
    """Pre-parse --profile/-p and set HERMES_HOME before imports."""
```

`hermes_cli/main.py:683 @ 863e313`

```python
        os.environ["HERMES_HOME"] = hermes_home
```

这一句在模块顶层被调用(不是在 `main()` 里),所以它先于所有配置读发生。`hermes_cli/main.py:690 @ 863e313`

```python
_apply_profile_override()
```

profile 名 → 路径的翻译在 `profiles.py`,不存在的具名 profile 直接抛错(不会静默建目录)。`hermes_cli/profiles.py:2246-2247 @ 863e313`

```python
def resolve_profile_env(profile_name: str) -> str:
    """Resolve a profile name to a HERMES_HOME path string.
```

若既没有 `-p` 也没有 `HERMES_HOME`,会读 `<root>/active_profile` 这个"粘性"文件。`hermes_cli/main.py:653-658 @ 863e313`

```python
            active_path = get_default_hermes_root() / "active_profile"
            if active_path.exists():
                name = active_path.read_text(encoding="utf-8").strip()
                if name and name != "default":
                    profile_name = name
                    consume = 0  # don't strip anything from argv
```

反过来,如果 `HERMES_HOME` 已经指向 `.../profiles/<name>`(父目录名恰为 `profiles`),
就信任它、不再读 `active_profile`。`hermes_cli/main.py:632-635 @ 863e313`

```python
    hermes_home_env = os.environ.get("HERMES_HOME", "")
    if profile_name is None and hermes_home_env:
        if Path(hermes_home_env).parent.name == "profiles":
            return
```

`.env` 的**加载**(不是路径解析)另有一套次序:`$HERMES_HOME/.env` 以 `override=True`
压过 shell 导出,项目根 `.env` 只做开发兜底。`hermes_cli/main.py:697 @ 863e313`

```python
load_hermes_dotenv(project_env=PROJECT_ROOT / ".env")
```

`hermes_cli/env_loader.py:487-489 @ 863e313`

```python
    if user_env.exists():
        _load_dotenv_with_fallback(user_env, override=True)
        loaded.append(user_env)
```

### 1.4 为什么这么设计 / 取舍

- **为什么在 import 前改 env,而不是传参**:仓库里有几十个模块在 import 期就固化了
  home 派生路径(`AGENTS.md` 明确写了这条约束)。传参需要改动所有这些模块;改 env 是
  一处解决。
- 取舍:`sys.argv` 被**手工扫描**(不是 argparse),因此需要一堆特例来避免误吞
  `-p`(pytest 的 `-p no:xdist`、`mcp add --args` 之后的子命令 argv)。`hermes_cli/main.py:618 @ 863e313`

```python
        if not _re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", profile_name):
```

- 取舍:进程内切 home 只能用 contextvar override(`get_hermes_home()` 走它,
  `get_process_hermes_home()` 故意不走),于是出现了"哪些资产跟 profile 走、哪些跟进程走"
  这一层必须靠人记的区分。

**未确证**:`HERMES_CONFIG` / `HERMES_ENV` 两个环境变量出现在写入 denylist 与注释里
(见 §7),但我在全仓 `--include=*.py` 里**没有找到任何读取点**;`HERMES_PROFILE` 有读取点,
但读的是 kanban 作者名/ACP 作用域,不参与 home 解析。详见 §10 的"文档-代码出入"。

---

## 2. 机制:损坏 config.yaml 的三段式处理(本段核心)

### 2.1 解决什么问题

YAML 解析失败时 `load_config()` 会退回 `DEFAULT_CONFIG`,这意味着用户**所有**覆盖
(辅助 provider、fallback 链、乃至 `approvals.deny` 安全规则)静默消失。历史实现是
一行 `print(...)`,首次调用就滚出屏幕。三个子问题:①怎么让用户看见;②怎么不刷屏;
③怎么不让用户那份唯一的、还能救的破文件被后续写操作覆盖掉。

### 2.2 怎么实现

**(a) 去重键 = (路径, mtime_ns, size)**,存在一个模块级 set 里。`hermes_cli/config.py:42 @ 863e313`

```python
_CONFIG_PARSE_WARNED: set = set()
```

`hermes_cli/config.py:124-131 @ 863e313`

```python
    try:
        st = config_path.stat()
        key = (str(config_path), st.st_mtime_ns, st.st_size)
    except OSError:
        key = (str(config_path), 0, 0)
    if key in _CONFIG_PARSE_WARNED:
        return
    _CONFIG_PARSE_WARNED.add(key)
```

用户改了文件 → mtime/size 变 → 新键 → 再警告一次。这就是"编辑后能再看到下一次失败"。

**(b) 首次警告时顺手备份**。`hermes_cli/config.py:133 @ 863e313`

```python
    backup_path = _backup_corrupt_config(config_path)
```

备份函数本体:先拒符号链接(避免顺着恶意 symlink 写到别处)。`hermes_cli/config.py:67-68 @ 863e313`

```python
        if config_path.is_symlink():
            return None
```

空文件不备份。`hermes_cli/config.py:69-73 @ 863e313`

```python
        st = config_path.stat()
        if st.st_size == 0:
            # Empty file isn't worth preserving and yaml.safe_load returns {}
            # for it anyway (so it wouldn't reach here), but guard regardless.
            return None
```

备份名带**秒级**时间戳。`hermes_cli/config.py:74-75 @ 863e313`

```python
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup_path = config_path.with_name(f"{config_path.name}.corrupt.{ts}.bak")
```

去重靠"同目录下已存在同 size 的 .bak"。`hermes_cli/config.py:83-88 @ 863e313`

```python
        for existing in sibling_baks:
            try:
                if existing.stat().st_size == st.st_size:
                    # Same size as the current broken file — likely the same
                    # corruption already preserved. Avoid backup churn.
                    return None
```

`hermes_cli/config.py:91-94 @ 863e313`

```python
        if backup_path.exists():
            return None
        shutil.copy2(config_path, backup_path)
        return backup_path
```

整个函数吞掉一切异常 —— 备份失败绝不阻塞配置加载。`hermes_cli/config.py:95-96 @ 863e313`

```python
    except Exception:
        return None
```

**(c) 两套措辞:defaults vs last-known-good**。`hermes_cli/config.py:135-147 @ 863e313`

```python
    if fallback == "last-known-good":
        msg = (
            f"Failed to parse {config_path}: {exc}. "
            f"Keeping the previously loaded config for this process — "
            f"edits to config.yaml are being IGNORED until the YAML is fixed."
        )
    else:
        msg = (
            f"Failed to parse {config_path}: {exc}. "
            f"Falling back to default config — every user override "
            f"(auxiliary providers, fallback chain, model settings) is being IGNORED. "
            f"Fix the YAML and restart."
        )
```

**双通道输出**:`logger.warning`(进 `agent.log`/`errors.log`,`hermes logs` 能看到)+ 直写 stderr
(启动早期 `setup_logging()` 还没接上 file handler 时也可见),stderr 写失败被吞。`hermes_cli/config.py:150-155 @ 863e313`

```python
    logger.warning(msg)
    try:
        sys.stderr.write(f"⚠️  hermes config: {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass
```

**(d) last-known-good 保留(codex#31188 的移植)**:同一进程里若之前成功加载过,解析失败时
继续供上一份,而不是退回默认。`hermes_cli/config.py:3361-3366 @ 863e313`

```python
                lkg = _LAST_EXPANDED_CONFIG_BY_PATH.get(path_key)
                _warn_config_parse_failure(
                    config_path,
                    e,
                    fallback="last-known-good" if lkg is not None else "defaults",
                )
```

`_LAST_EXPANDED_CONFIG_BY_PATH` 就在本段声明。`hermes_cli/config.py:235 @ 863e313`

```python
_LAST_EXPANDED_CONFIG_BY_PATH: Dict[str, Any] = {}
```

### 2.3 为什么这么设计

- **不重置用户文件**:注释里明确对比了 Gemini CLI 的 policy-file recovery(把线上文件重置成
  干净状态),Hermes 选择只备份不动原文件 —— 用户手改好之后下一次加载就自动生效。`hermes_cli/config.py:51-55 @ 863e313`

```python
    they re-run the setup wizard or ``hermes config set`` (which rewrites
    ``config.yaml``), the broken-but-recoverable content is gone for good.

    This snapshots the corrupted file to ``config.yaml.corrupt.<ts>.bak`` so
    the user can diff/repair it. Unlike Gemini CLI's policy-file recovery
```

- **为什么 last-known-good 是安全问题而不是体验问题**:`approvals.deny` 是拒绝规则,
  退回默认等于把这些规则从长跑网关里摘掉。注释写得很直白。`hermes_cli/config.py:3352-3354 @ 863e313`

```python
                # one). Falling through to DEFAULT_CONFIG here drops EVERY user
                # override — including security-critical ``approvals.deny``
                # rules, which are supposed to block commands even under yolo.
```

### 2.4 取舍与坑

- 去重集**只增不减**(见 §11 缺陷 D1),注释里的"Cleared automatically"是措辞不准。
- 备份用"同 size"判重,同 size 的**不同**损坏内容不会被备份(§11 D2)。
- 秒级时间戳 + `backup_path.exists()`:同一秒内两次不同 size 的损坏,第二次不备份(§11 D3)。
- `.bak` 文件永不清理,长期累积(§11 D4)。
- 备份是在持有 `_CONFIG_LOCK` 的情况下做的(调用点在 `_load_config_impl` 内),磁盘慢时
  会阻塞所有配置读。

---

## 3. 机制:缓存 / mtime 失效 / 线程锁

### 3.1 解决什么问题

`load_config()` 一次完整解析约 13 ms(yaml 解析 + 深合并 + 归一化 + env 展开),而 agent
循环里每轮都要读若干配置(超时、阈值、feature flag)。同时,多线程工具(approval、browser_tool、
setup 流)会从不同线程同时读写配置,而 libyaml 的 C 扩展对同文件并发 `safe_load()` 不是线程安全的。

### 3.2 怎么实现:三张表 + 一把 RLock

**表 1**:`load_config()` 的合并后结果缓存,key 是路径字符串,value 是 6 元组。`hermes_cli/config.py:248 @ 863e313`

```python
_LOAD_CONFIG_CACHE: Dict[str, Tuple[int, int, int, int, Dict[str, Any], Dict[str, Optional[str]]]] = {}
```

**表 2**:`read_raw_config()` 的原始 YAML 缓存(不合并默认值)。`hermes_cli/config.py:252 @ 863e313`

```python
_RAW_CONFIG_CACHE: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}
```

**表 3**:上一节的 last-known-good(`_LAST_EXPANDED_CONFIG_BY_PATH`,235 行)。

**锁**:RLock 而非 Lock,因为 `save_config()` 内部会调 `read_raw_config()`(可重入)。`hermes_cli/config.py:253-260 @ 863e313`

```python
# Serializes all config read/write paths. libyaml's C extension is not
# thread-safe for concurrent safe_load() on the same file, and multiple
# tool threads (approval.py, browser_tool.py, setup flows) hit
# load_config / read_raw_config / save_config from different threads
# during long agent runs. RLock (not Lock) because save_config internally
# calls read_raw_config. Also covers mutation of the module-level cache
# dicts above.
_CONFIG_LOCK = threading.RLock()
```

### 3.3 失效条件:三重签名

缓存命中要同时满足 **用户文件 (mtime_ns, size)** + **managed 文件 (mtime_ns, size)** + **env 快照**。
签名比较:`hermes_cli/config.py:3322-3323 @ 863e313`

```python
        cached = _LOAD_CONFIG_CACHE.get(path_key)
        if cached is not None and cache_sig is not None and cached[:4] == cache_sig:
```

env 快照校验 —— 这是为了解决"第一次 `load_config()` 跑在 `load_hermes_dotenv()` 之前,
把 `${VAR}` 的未展开字面量钉死一整个进程"这个 bug(#58514)。`hermes_cli/config.py:3329-3331 @ 863e313`

```python
            env_snapshot = cached[5] if len(cached) > 5 else {}
            if all(os.environ.get(k) == v for k, v in env_snapshot.items()):
                return copy.deepcopy(cached[4]) if want_deepcopy else cached[4]
```

**没有显式失效钩子**:写路径走原子写(新 inode → 新 mtime_ns),下一次 stat 自然失配。`hermes_cli/config.py:240-242 @ 863e313`

```python
# save_config() + migrate_config() write via atomic_yaml_write which
# produces a fresh inode, so stat() sees a new mtime_ns and the next
# load repopulates automatically — no explicit invalidation hook.
```

### 3.4 deepcopy 的双通道

`load_config()` 返回深拷贝(调用方普遍会改再存),`load_config_readonly()` 直接返回缓存对象。`hermes_cli/config.py:3115 @ 863e313`

```python
def load_config() -> Dict[str, Any]:
```

`hermes_cli/config.py:3132-3133 @ 863e313`

```python
def load_config_readonly() -> Dict[str, Any]:
    """Fast-path variant of ``load_config()`` for callers that ONLY READ.
```

只读通道的安全性**只靠文档,不靠语言**(返回的是普通 dict,不是 MappingProxyType)。`hermes_cli/config.py:3148-3150 @ 863e313`

```python
    Note: this returns a plain ``dict`` (not ``MappingProxyType``) so
    existing ``isinstance(x, dict)`` guards downstream keep working. The
    safety guarantee is purely documented, not enforced — be careful.
```

`read_raw_config_readonly()` 同理,并额外维持"两次只读调用返回同一对象"的 identity 不变式。`hermes_cli/config.py:3057-3062 @ 863e313`

```python
        # Store and return THE SAME object (identity invariant): the first
        # caller must see the exact dict later cache hits return, so a test
        # asserting ``ro1 is ro2`` holds from the very first call.
        cached_copy = copy.deepcopy(data)
        _RAW_CONFIG_CACHE[path_key] = (cache_key[0], cache_key[1], cached_copy)
        return cached_copy
```

### 3.5 取舍

- key 用 `str(config_path)` 而非 inode:profile 切换换路径 → 自动不撞车;但同路径不同挂载
  (容器重挂)不会被识别。
- `(mtime_ns, size)` 在 mtime 粒度为 1 秒的文件系统上(部分网络盘/老 FS)可能漏检"同秒同 size 的两次编辑"。
- 只读通道把"别写返回值"变成了纯约定,一旦有人改了就污染全进程缓存,且**无法在崩溃现场定位**。

---

## 4. 机制:`load_config()` 的完整解析链

按执行顺序(全部在 `_CONFIG_LOCK` 内)。`hermes_cli/config.py:3283-3285 @ 863e313`

```python
def _load_config_impl(*, want_deepcopy: bool) -> Dict[str, Any]:
    with _CONFIG_LOCK:
        ensure_hermes_home()
```

1. **保证目录骨架**(§5)。
2. **stat 用户文件 + managed 文件**,组合缓存签名;命中且 env 快照未漂移则直接返回(§3.3)。
   managed 目录来自 `HERMES_MANAGED_DIR` 或 `/etc/hermes`。`hermes_cli/managed_scope.py:65 @ 863e313`

```python
    override = os.environ.get("HERMES_MANAGED_DIR", "").strip()
```

3. **默认值 = `DEFAULT_CONFIG` 的深拷贝**,来源是独立模块 `config_defaults.py`。`hermes_cli/config.py:943 @ 863e313`

```python
from hermes_cli.config_defaults import DEFAULT_CONFIG, OPTIONAL_ENV_VARS  # noqa: F401
```

`hermes_cli/config_defaults.py:7 @ 863e313`

```python
DEFAULT_CONFIG = {
```

`hermes_cli/config.py:3333 @ 863e313`

```python
        config = copy.deepcopy(DEFAULT_CONFIG)
```

4. **读用户 YAML**(用 `utils.fast_safe_load`,不是裸 `yaml.safe_load`)。`hermes_cli/config.py:692 @ 863e313`

```python
from utils import atomic_replace, fast_safe_load
```

`hermes_cli/config.py:3337-3338 @ 863e313`

```python
                with open(config_path, encoding="utf-8") as f:
                    user_config = fast_safe_load(f) or {}
```

5. **根级 `max_turns` 提升到 `agent.max_turns`**(合并之前做,否则根键会被当成未知键留在树上)。`hermes_cli/config.py:3340-3345 @ 863e313`

```python
                if "max_turns" in user_config:
                    agent_user_config = dict(user_config.get("agent") or {})
                    if agent_user_config.get("max_turns") is None:
                        agent_user_config["max_turns"] = user_config["max_turns"]
                    user_config["agent"] = agent_user_config
                    user_config.pop("max_turns", None)
```

6. **深合并,不是浅合并**。`hermes_cli/config.py:3347 @ 863e313`

```python
                config = _deep_merge(config, user_config)
```

`_deep_merge` 的语义:两边都是 dict 才递归;`override` 里的 `None` 若对应默认值是 dict,
**忽略**(空 section `terminal:` 在 YAML 里解析成 `None`,直接覆盖会让下游全崩,#58277)。`hermes_cli/config.py:2448-2459 @ 863e313`

```python
    result = base.copy()
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        elif key in result and isinstance(result[key], dict) and value is None:
            continue
        else:
            result[key] = value
```

注意 `result = base.copy()` 是**浅**拷贝 —— 递归时每层重新 copy,但**列表值是共享的**。
调用方传进来的是 `DEFAULT_CONFIG` 的深拷贝,所以不会污染全局默认;但这依赖第 3 步。

7. **解析失败 → last-known-good / 默认**(§2.2d)。
8. **归一化**:根级 model 键 + max_turns。`hermes_cli/config.py:3389 @ 863e313`

```python
        normalized = _normalize_root_model_keys(_normalize_max_turns_config(config))
```

9. **`${VAR}` 展开**(只处理字符串值,dict 的 key 不动;未解析的引用保留字面量)。`hermes_cli/config.py:3390 @ 863e313`

```python
        expanded = _expand_env_vars(normalized)
```

`hermes_cli/config.py:2554-2555 @ 863e313`

```python
    if isinstance(obj, str):
        return re.sub(r"\${([^}]+)}", _env_expand_match, obj)
```

支持两种写法 `${VAR}` 与 `${env:VAR}`;其他 SecretRef 前缀(`file:` / `bitwarden:` / `vault:`)
不在这里解析,只警告并保留原样。`hermes_cli/config.py:2518-2522 @ 863e313`

```python
    if ":" in inner and re.match(r"^[a-z][a-z0-9_-]*:", inner):
        # Looks like a SecretRef with a non-env source.  Values from vault
        # backends arrive via the secrets: block as env vars — point there
        # instead of silently treating "bitwarden:FOO" as a var named
        # "bitwarden:FOO".
```

10. **managed 层最后覆盖**(故意反转"env 压 config"的常规优先级:managed 只对进程环境展开,
    用户的 `${VAR}` 不能遮住管理员钉死的字面量)。`hermes_cli/config.py:3396-3399 @ 863e313`

```python
        managed_config = managed_scope.load_managed_config()
        if managed_config:
            managed_expanded = _expand_env_vars(managed_config)
            expanded = _deep_merge(expanded, managed_expanded)
```

11. **写 last-known-good + 写缓存(含 env 快照)**。`hermes_cli/config.py:3400 @ 863e313`

```python
        _LAST_EXPANDED_CONFIG_BY_PATH[path_key] = copy.deepcopy(expanded)
```

`hermes_cli/config.py:3414 @ 863e313`

```python
            _LOAD_CONFIG_CACHE[path_key] = (*cache_sig, cached_copy, env_snapshot)
```

**旁路读法**共三条,语义各不相同,别混用:

- `read_raw_config()` —— 原始 YAML + 缓存 + 深拷贝;解析失败返回 `{}` 并走同一个告警器。`hermes_cli/config.py:2933 @ 863e313`

```python
def read_raw_config() -> Dict[str, Any]:
```

- `read_user_config_raw()` —— **完全不缓存、不合并、不展开**,只给写回round-trip 和诊断用;
  解析失败**抛异常**(与前者相反)。`hermes_cli/config.py:2971-2975 @ 863e313`

```python
def read_user_config_raw(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Read a user ``config.yaml`` EXACTLY as written on disk.

    No DEFAULT_CONFIG merge, no managed-scope overlay, no ``${ENV_VAR}``
    expansion, no migration, no root-model normalization, no caching.
```

- 写侧的守门员:一个存在但读不出来的 config.yaml 绝不允许被整文件替换。`hermes_cli/config.py:3065-3066 @ 863e313`

```python
def require_readable_config_before_write(config_path: Optional[Path] = None) -> None:
    """Refuse to replace an existing config.yaml that cannot be read."""
```

`hermes_cli/config.py:3089-3090 @ 863e313`

```python
def atomic_config_write(config_path: Path, data: Any, **kwargs: Any) -> None:
    """Fail-closed atomic write for ``config.yaml``.
```

**根因说明**(值得记):`read_raw_config()` 对"文件不存在"和"文件存在但读不了"都返回 `{}`,
读-改-写的调用方无法区分,于是不可读的配置会被默认值整文件顶掉。`hermes_cli/config.py:3099-3101 @ 863e313`

```python
    Root cause this guards: ``read_raw_config()`` returns ``{}`` for BOTH an
    absent file and an unreadable-but-present file. Callers that read then
    overwrite can't tell the two apart, so an unreadable config would be
```

---

## 5. 机制:HERMES_HOME 骨架、权限与属主

### 5.1 记忆化的 `ensure_hermes_home()`

它跑在**每次** `load_config()` 里,约 14 次 mkdir/chmod syscall,曾是热读路径的主要成本。
现在按 home 路径记忆化。`hermes_cli/config.py:864 @ 863e313`

```python
_HERMES_HOME_ENSURED: set = set()
```

`hermes_cli/config.py:885-886 @ 863e313`

```python
    if key in _HERMES_HOME_ENSURED and home.is_dir():
        return
```

具名 profile 的 home 缺失时**抛错而不是 mkdir**(否则被删掉的 profile 会因为残留进程复活)。`hermes_cli/config.py:891-895 @ 863e313`

```python
    if home.parent.name == "profiles" and not home.exists():
        raise FileNotFoundError(
            f"Named profile home does not exist: {home}. "
            "Create the profile explicitly before using it."
        )
```

非 managed 分支建的目录清单(固定 10 个)。`hermes_cli/config.py:903-912 @ 863e313`

```python
        home.mkdir(parents=True, exist_ok=True)
        _secure_dir(home)
        for subdir in (
            "cron", "sessions", "logs", "logs/curator", "memories",
            "pairing", "hooks", "image_cache", "audio_cache", "skills",
        ):
            d = home / subdir
            d.mkdir(parents=True, exist_ok=True)
            _secure_dir(d)
        _ensure_default_soul_md(home)
```

只有**成功**的那一趟才记账(managed 分支可能抛 RuntimeError)。`hermes_cli/config.py:914 @ 863e313`

```python
    _HERMES_HOME_ENSURED.add(key)
```

managed 分支只**校验**目录存在(NixOS activation script 负责建),缺了就要求 `nixos-rebuild switch`。`hermes_cli/config.py:919-923 @ 863e313`

```python
    if not home.is_dir():
        raise RuntimeError(
            f"HERMES_HOME {home} does not exist. "
            "Run 'sudo nixos-rebuild switch' first."
        )
```

managed 分支下临时把 umask 设成 `0o007`,让新建文件(SOUL.md)是组可写 0660。`hermes_cli/config.py:896-901 @ 863e313`

```python
    if is_managed():
        old_umask = os.umask(0o007)
        try:
            _ensure_hermes_home_managed(home)
        finally:
            os.umask(old_umask)
```

**取舍**:记忆化后只再检查 home 根目录是否存在 —— 删掉 `sessions/` 不会被补回来。这是
显式接受的行为,配套测试直接断言了它(见 §12)。

### 5.2 目录权限:`HERMES_HOME_MODE`

默认 0700;可用八进制环境变量放宽(典型场景:nginx 需要穿过 HERMES_HOME 去服务某个子目录,
只给 execute 位即可 cd-through 而不暴露列目录)。`hermes_cli/config.py:785-789 @ 863e313`

```python
    try:
        mode_str = os.environ.get("HERMES_HOME_MODE", "").strip()
        mode = int(mode_str, 8) if mode_str else 0o700
    except ValueError:
        mode = 0o700
```

managed 模式整体跳过(NixOS 模块自己设 0750 给 hermes 组)。`hermes_cli/config.py:783-784 @ 863e313`

```python
    if is_managed():
        return
```

### 5.3 文件权限:`_secure_file` 与容器豁免

`hermes_cli/config.py:831-836 @ 863e313`

```python
    if is_managed() or _is_container():
        return
    try:
        if os.path.exists(str(path)):
            os.chmod(path, 0o600)
```

容器判定用的是**本文件自己的** `_is_container()`,带两个显式 opt-out。`hermes_cli/config.py:806-807 @ 863e313`

```python
    if os.environ.get("HERMES_CONTAINER") or os.environ.get("HERMES_SKIP_CHMOD"):
        return True
```

`hermes_cli/config.py:812-816 @ 863e313`

```python
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8") as f:
            cgroup_content = f.read()
        if "docker" in cgroup_content or "lxc" in cgroup_content or "kubepods" in cgroup_content:
            return True
```

### 5.4 属主:`HERMES_UID` / `HERMES_GID`

Docker 部署把容器内用户映射到宿主用户;entrypoint 只 chown 顶层一次,运行时新建的
`profiles/<name>/` 子目录会落成 root:root 并把后续 uid 映射的 worker 卡在 EACCES(#34107)。`hermes_cli/config.py:721-733 @ 863e313`

```python
    if sys.platform == "win32":
        return None, None
    uid_str = os.environ.get("HERMES_UID", "").strip()
    gid_str = os.environ.get("HERMES_GID", "").strip()
    try:
        uid = int(uid_str) if uid_str else None
    except ValueError:
        uid = None
    try:
        gid = int(gid_str) if gid_str else None
    except ValueError:
        gid = None
    return uid, gid
```

`hermes_cli/config.py:748-757 @ 863e313`

```python
    uid, gid = _resolve_hermes_uid_gid()
    if uid is None and gid is None:
        return
    try:
        # os.chown with -1 means "don't change" for that field.
        os.chown(
            path,
            uid if uid is not None else -1,
            gid if gid is not None else -1,
        )
```

失败静默(非 root 时 EPERM 是常态,entrypoint 下次重启的 `chown -R` 会补上)。

### 5.5 SOUL.md 播种与"legacy 模板升级"

`hermes_cli/config.py:849-858 @ 863e313`

```python
    if soul_path.exists():
        try:
            existing = soul_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        if not is_legacy_template_soul(existing):
            return
        # Legacy empty template -> upgrade to the real default in place.
    soul_path.write_text(DEFAULT_SOUL_MD, encoding="utf-8")
    _secure_file(soul_path)
```

这是**唯一**一处 Hermes 会原地改写用户 home 里已有文件的地方,前提是内容被判定为"老安装
脚本塞进来的空注释脚手架"。

---

## 6. 机制:managed 模式(NixOS)与安装方式检测

### 6.1 managed 判定

两个信号:环境变量或 home 下的 `.managed` 标记文件。`hermes_cli/config.py:357-369 @ 863e313`

```python
    raw = os.getenv("HERMES_MANAGED", "").strip()
    if raw:
        normalized = raw.lower()
        if normalized in _IGNORED_MANAGED_VALUES:
            return None
        if normalized in _MANAGED_TRUE_VALUES:
            return "NixOS"
        return _MANAGED_SYSTEM_NAMES.get(normalized, raw)

    managed_marker = get_hermes_home() / ".managed"
    if managed_marker.exists():
        return "NixOS"
    return None
```

真值表与"已废弃的 Homebrew 值"白名单在同一段声明。`hermes_cli/config.py:338 @ 863e313`

```python
_MANAGED_TRUE_VALUES = ("true", "1", "yes")
```

`hermes_cli/config.py:352 @ 863e313`

```python
_IGNORED_MANAGED_VALUES = frozenset({"brew", "homebrew"})
```

managed 的影响面(本段内):跳过 `_secure_dir`/`_secure_file`、`ensure_hermes_home` 改成
校验模式、`managed_error()` 打印引导用户去改 `configuration.nix`。`hermes_cli/config.py:616-625 @ 863e313`

```python
    raw = os.getenv("HERMES_MANAGED", "").strip().lower()

    if managed_system == "NixOS":
        env_hint = "true" if raw in _MANAGED_TRUE_VALUES else raw or "true"
        return (
            f"Cannot {action}: this Hermes installation is managed by NixOS "
            f"(HERMES_MANAGED={env_hint}).\n"
            "Edit services.hermes-agent.settings in your configuration.nix and run:\n"
            "  sudo nixos-rebuild switch"
        )
```

注意 `is_managed()`(本段,`HERMES_MANAGED`)与 `managed_scope`(`/etc/hermes` 管理员覆盖层)
是**两套完全不同的东西**,`managed_scope.py` 开头就特意声明了这一点。

### 6.2 安装方式检测:为什么戳记要绑代码而不是绑 home

问题场景很值得记:Docker 文档鼓励把 `~/.hermes` bind-mount 进容器,于是宿主的 git 安装
和容器里的镜像安装共享同一个数据目录。旧实现把 `.install_method` 写在 home 里 —— 容器每次
启动写 `docker`,宿主 `hermes update` 读到 `docker` 就拒绝更新。`hermes_cli/config.py:427-434 @ 863e313`

```python
    ``$HERMES_HOME`` is a shared DATA directory — the Docker docs deliberately
    bind-mount it (``~/.hermes:/opt/data``) so config/sessions/memory persist
    and can be shared with a host-side Desktop/CLI install. When a
    containerised gateway and a host install share one ``$HERMES_HOME``, a
    home-scoped stamp is a single slot describing two different installs:
    the container stamps ``docker`` on every boot, the host install then reads
    ``docker`` and ``hermes update`` refuses to run ("doesn't apply inside the
    Docker container") even though the host binary is a perfectly updatable
```

修法:戳记落在**代码树**(`hermes_cli/` 的父目录),它是解释器属性而非 home 属性。`hermes_cli/config.py:396-397 @ 863e313`

```python
def _install_method_project_root(project_root: Optional[Path] = None) -> Path:
    """Resolve the directory that holds the *running code* (the install tree).
```

六级解析顺序:代码戳 → home 旧戳(带自愈)→ managed → `/nix/store` → `.git` → unknown。`hermes_cli/config.py:454-463 @ 863e313`

```python
    root = _install_method_project_root(project_root)
    supported_methods = {"docker", "nix", "nixos", "git", "unknown"}

    # 1. Code-scoped stamp — authoritative, immune to shared $HERMES_HOME.
    try:
        method = (root / ".install_method").read_text(encoding="utf-8").strip().lower()
        if method in supported_methods:
            return method
    except OSError:
        pass
```

**自愈条款**:旧 home 戳里的 `docker` 只在真的在容器里时才认。`hermes_cli/config.py:476 @ 863e313`

```python
        if method in supported_methods and not (method == "docker" and not _running_in_container()):
```

`/nix/store` 判定用 `parents` 包含关系,并排除"根目录本身"。`hermes_cli/config.py:490-492 @ 863e313`

```python
        resolved = root.resolve()
        if resolved != _NIX_STORE and _NIX_STORE in resolved.parents:
            return "nix"
```

git worktree 的 `.git` 是文件不是目录,单独处理。`hermes_cli/config.py:502-506 @ 863e313`

```python
    if git_path.is_file():
        try:
            content = git_path.read_text(encoding="utf-8").strip()
            if content.startswith("gitdir:"):
                return "git"
```

写戳是 best-effort,只读安装树(镜像里的 `/opt/hermes`)静默 no-op。`hermes_cli/config.py:536-540 @ 863e313`

```python
    try:
        root.mkdir(parents=True, exist_ok=True)
        (root / ".install_method").write_text(method + "\n", encoding="utf-8")
    except OSError:
        pass
```

更新命令映射。`hermes_cli/config.py:545-549 @ 863e313`

```python
    if method in {"nix", "nixos"}:
        return _NIX_UPDATE_MSG
    if method == "docker":
        return "docker pull nousresearch/hermes-agent:latest"
    return "hermes update"
```

### 6.3 container 模式元数据(NixOS container.enable)

`.container-mode` 是个 `key=value` 文本文件,告诉宿主 CLI"别本地跑,exec 进容器"。`hermes_cli/config.py:659 @ 863e313`

```python
    container_mode_file = get_hermes_home() / ".container-mode"
```

三个提前返回:`HERMES_DEV=1`、已经在容器里、文件不存在。`hermes_cli/config.py:652-657 @ 863e313`

```python
    if os.environ.get("HERMES_DEV") == "1":
        return None

    from hermes_constants import is_container
    if is_container():
        return None
```

**其余异常一律上抛**(显式注释),这是刻意的 fail-loud。`hermes_cli/config.py:669-671 @ 863e313`

```python
    except FileNotFoundError:
        return None
    # All other exceptions (PermissionError, malformed data, etc.) propagate
```

四个字段的默认值。`hermes_cli/config.py:673-676 @ 863e313`

```python
    backend = info.get("backend", "docker")
    container_name = info.get("container_name", "hermes-agent")
    exec_user = info.get("exec_user", "hermes")
    hermes_bin = info.get("hermes_bin", "/data/current-package/bin/hermes")
```

---

## 7. 机制:`.env` 写入器的变量名 denylist

### 7.1 解决什么问题

Dashboard 允许操作员从 Web UI 往 `~/.hermes/.env` 写键值。若不设防,写一个
`LD_PRELOAD=/tmp/evil.so` 就等于在下一次 `subprocess.run()` 时拿到 RCE —— 这是从
"配置写入权限"提权到"代码执行"。

### 7.2 怎么实现

名字级(不是前缀级)黑名单。`hermes_cli/config.py:198-201 @ 863e313`

```python
_ENV_VAR_NAME_DENYLIST: frozenset[str] = frozenset({
    # Loader / linker
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "LD_DEBUG",
    "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
```

覆盖:loader(LD_*/DYLD_*)、Python 解释器初始化、Node、`PATH`/`SHELL`/`EDITOR` 等隐式被调用的命令、
git 改写钩子,以及 Hermes 自身的运行时定位变量。`hermes_cli/config.py:215 @ 863e313`

```python
    "HERMES_HOME", "HERMES_PROFILE", "HERMES_CONFIG", "HERMES_ENV",
```

关键设计声明:**`HERMES_*` 整体不封禁**,因为大量集成凭据用这个前缀。`hermes_cli/config.py:188-192 @ 863e313`

```python
# IMPORTANT: ``HERMES_*`` overall is NOT blocked. Many legitimate
# integration credentials follow that prefix (HERMES_LANGFUSE_PUBLIC_KEY,
# HERMES_SPOTIFY_CLIENT_ID, ...). The
# denylist is name-by-name on purpose so the gate stays narrow and
# doesn't accidentally break provider setup wizards.
```

**只在写时拦**,已经在 `.env` 里的值照常生效。`hermes_cli/config.py:194-197 @ 863e313`

```python
# This is enforced on *write* only — values already in ``.env`` (set
# by the operator out-of-band, or pre-existing) keep working. The
# point is that the dashboard's writable surface cannot escalate by
# planting them.
```

统一的抛错点(普通写与 secure 写共用)。`hermes_cli/config.py:225-233 @ 863e313`

```python
    if key in _ENV_VAR_NAME_DENYLIST:
        raise ValueError(
            f"Environment variable {key!r} is on the writer denylist. "
            "Names that influence subprocess execution (LD_PRELOAD, "
            "PYTHONPATH, PATH, EDITOR, ...) or Hermes runtime location "
            "(HERMES_HOME, HERMES_PROFILE, ...) cannot be persisted via "
            "the env writer. If you really need this, edit "
            "~/.hermes/.env directly."
        )
```

配套的名字合法性正则(在本段声明,在 3883 行被 `save_env_value` 用)。`hermes_cli/config.py:158 @ 863e313`

```python
_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
```

### 7.3 `_EXTRA_ENV_KEYS`:.env 的"已知键"全集

`OPTIONAL_ENV_VARS` 之外、由 setup/provider 流程直接管理的键名集合;`reload_env()` 用它
决定"哪些 os.environ 的键归 Hermes 管、可以被 .env 清掉"。`hermes_cli/config.py:263 @ 863e313`

```python
_EXTRA_ENV_KEYS = frozenset({
```

它被 `env_loader` 反向 import 来构造"已知 Hermes env 键"。`hermes_cli/env_loader.py:63-66 @ 863e313`

```python
    from hermes_cli.config import _EXTRA_ENV_KEYS
    from hermes_cli.config_defaults import OPTIONAL_ENV_VARS

    return set(OPTIONAL_ENV_VARS.keys()) | set(_EXTRA_ENV_KEYS)
```

其中一条注释记录了一个"已废弃但仍必须保留"的键 —— `HERMES_TOOL_PROGRESS_MODE`。`hermes_cli/config.py:295-301 @ 863e313`

```python
    # HERMES_TOOL_PROGRESS_MODE is deprecated (replaced by display.tool_progress
    # in config.yaml) but STILL READ at runtime by the gateway as a back-compat
    # fallback, so it must stay known to reload/compat paths. The boolean
    # HERMES_TOOL_PROGRESS variant is fully unsupported since the v12 config
    # support floor retired its only consumer (the v3→4 migration): it is no
    # longer listed here and doctor flags it as ignored.
    "HERMES_TOOL_PROGRESS_MODE",
```

---

## 8. 机制:dotted-key 导航与 `hermes config set` 的路由

### 8.1 `_set_nested`:支持 list 索引,且不再毁掉 list

`hermes_cli/config.py:1014-1016 @ 863e313`

```python
    parts = dotted_key.split(".")
    current = config
    for part in parts[:-1]:
```

修复点(#17876):旧实现把任何非 dict 中间值(包括 list)无条件换成 `{}`,于是
`custom_providers.0.api_key` 这种写法会静默毁掉整个 list。现在只有"缺失或标量"才替换。`hermes_cli/config.py:1027-1031 @ 863e313`

```python
            existing = current.get(part)
            # Preserve dicts and lists; replace missing/scalar with a fresh dict.
            if part not in current or not isinstance(existing, (dict, list)):
                current[part] = {}
            current = current[part]
```

末段写入对 list 不做保护(非数字段或越界会抛)。`hermes_cli/config.py:1036-1040 @ 863e313`

```python
    last = parts[-1]
    if isinstance(current, list):
        current[int(last)] = value
    else:
        current[last] = value
```

### 8.2 `_get_nested`:用哨兵对象区分"不存在"与"值是 None"

`hermes_cli/config.py:1070 @ 863e313`

```python
_MISSING = object()
```

`hermes_cli/config.py:1076-1087 @ 863e313`

```python
    for part in dotted_key.split("."):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (TypeError, ValueError, IndexError):
                return _MISSING
        elif isinstance(current, dict):
            if part not in current:
                return _MISSING
            current = current[part]
        else:
            return _MISSING
```

### 8.3 `_unset_nested`:删完之后回收空 dict 容器

删除后自底向上回收变空的 dict,但**保留用户手写的空 list**。`hermes_cli/config.py:1129-1133 @ 863e313`

```python
    # Drop empty dict containers left behind by the deletion while preserving
    # user-authored empty lists and non-empty sibling branches.
    for parent, part in reversed(parents):
        if current != {}:
            break
```

### 8.4 `_is_env_config_key`:`hermes config set X Y` 到底写哪儿

判定规则:含 `.` 一律走 config.yaml;否则大写后匹配硬编码清单、或三种后缀、或 `TERMINAL_SSH` 前缀。`hermes_cli/config.py:1154-1155 @ 863e313`

```python
    if "." in key:
        return False
    key_upper = key.upper()
```

`hermes_cli/config.py:1168-1172 @ 863e313`

```python
    return (
        key_upper in api_keys
        or key_upper.endswith(('_API_KEY', '_TOKEN', '_SECRET'))
        or key_upper.startswith('TERMINAL_SSH')
    )
```

硬编码清单里混着非机密项(`FIRECRAWL_API_URL`、`TOOL_GATEWAY_DOMAIN`、`TOOL_GATEWAY_SCHEME`),
它们同样被路由进 `.env`。`hermes_cli/config.py:1157-1161 @ 863e313`

```python
    api_keys = [
        'OPENROUTER_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'VOICE_TOOLS_OPENAI_KEY',
        'EXA_API_KEY', 'PARALLEL_API_KEY', 'FIRECRAWL_API_KEY', 'FIRECRAWL_API_URL',
        'FIRECRAWL_GATEWAY_URL', 'TOOL_GATEWAY_DOMAIN', 'TOOL_GATEWAY_SCHEME',
        'TOOL_GATEWAY_USER_TOKEN', 'TAVILY_API_KEY',
```

**取舍**:这是纯启发式。任何未来新增的、名字以 `_TOKEN` 结尾的顶层 **config.yaml** 键
都会被误路由到 `.env`。当前 `DEFAULT_CONFIG` 顶层没有这种键,所以还没踩到。

### 8.5 `_format_config_get_value`

`hermes config get` 的输出格式:JSON 模式走 `json.dumps`;bool 打 `true/false`;
dict/list 打 YAML。`hermes_cli/config.py:1180-1186 @ 863e313`

```python
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return yaml.safe_dump(value, sort_keys=False).rstrip()
    return str(value)
```

---

## 9. 机制:缺失项盘点 + 自定义 provider 归一化

### 9.1 缺失配置项(递归对比 DEFAULT_CONFIG)

`hermes_cli/config.py:1199-1211 @ 863e313`

```python
    def _check(defaults: dict, current: dict, prefix: str = ""):
        for key, default_value in defaults.items():
            if key.startswith('_'):
                continue
            full_key = key if not prefix else f"{prefix}.{key}"
            if key not in current:
                missing.append({
                    "key": full_key,
                    "default": default_value,
                    "description": f"New config option: {full_key}",
                })
            elif isinstance(default_value, dict) and isinstance(current.get(key), dict):
                _check(default_value, current[key], full_key)
```

注意它比较的是 `load_config()` 的结果(已经合并过默认值),所以正常情况下永远为空 ——
只有当用户配置把某个 dict 默认值整段换成标量/None 时才会报出缺失。这是**行为上的
微妙点**,不是明显的 bug。

### 9.2 缺失的 skill 配置变量

存储路径是 `skills.config.<logical_key>`。`hermes_cli/config.py:1246-1247 @ 863e313`

```python
        # Skill config is stored under skills.config.<logical_key>
        storage_key = f"{SKILL_CONFIG_PREFIX}.{var['key']}"
```

"缺失"的定义包含空字符串。`hermes_cli/config.py:1258-1260 @ 863e313`

```python
        # Missing = key doesn't exist or is empty string
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(var)
```

整个函数对 skill 发现失败**完全 fail-open**(返回 `[]` 并只 debug 日志),理由写在注释里:
skill 配置提示是 `hermes update` 的锦上添花,不能变成阻塞项。`hermes_cli/config.py:1232-1234 @ 863e313`

```python
        # A malformed SKILL.md, unreadable external skill dir, or similar
        # should never break `hermes update`.  Skill-config prompting is a
        # post-migration nicety, not a blocker.
```

### 9.3 自定义 provider 条目归一化

**为什么要有告警去重**:`_normalize_custom_provider_entry` 每次打开 picker 都跑一遍,
对同一份静态配置会反复告警;Windows 上重复告警会在 `concurrent-log-handler` 的跨进程
轮转锁上打满一个核,拖死 gateway 事件循环。`hermes_cli/config.py:1264-1270 @ 863e313`

```python
# ``_normalize_custom_provider_entry`` runs on every ``load_picker_context()``
# call (i.e. per interactive picker/inventory request), so any warning it emits
# fires repeatedly for the same static config. Deduplicate per (provider,
# signature): on Windows a repeated-warning storm contends on
# ``concurrent-log-handler``'s cross-process rotation lock and can peg a core /
# stall the gateway/serve event loop. The cache lives for the process lifetime.
_PROVIDER_NORMALIZE_WARNED: set = set()
```

**为什么先浅拷贝**:传进来的可能是 `load_config_readonly()` 共享缓存里的活 sub-dict,
就地写 alias 会同时污染缓存并让 alias 键在下次 `save_config(load_config())` 时回灌到 config.yaml。`hermes_cli/config.py:1293-1300 @ 863e313`

```python
    # Shallow-copy before the alias normalization below writes into the
    # entry: callers (get_compatible_custom_providers,
    # providers_dict_to_custom_providers) pass live sub-dicts from
    # load_config_readonly()'s shared cache, and mutating those both
    # violates the cache's no-mutation contract and leaks duplicated
    # alias keys back into config.yaml through any later
    # save_config(load_config()) round-trip.
    entry = dict(entry)
```

camelCase 别名表(手写配置兼容)。`hermes_cli/config.py:1303-1312 @ 863e313`

```python
    _CAMEL_ALIASES: Dict[str, str] = {
        "apiKey": "api_key",
        "baseUrl": "base_url",
        "apiMode": "api_mode",
        "keyEnv": "key_env",
        "apiKeyEnv": "key_env",  # alias — OpenClaw-compatible + docs variant
        "defaultModel": "default_model",
        "contextLength": "context_length",
        "rateLimitDelay": "rate_limit_delay",
    }
```

`api_key_env` 是文档里写过的 snake_case 别名,提前规范化。`hermes_cli/config.py:1316-1317 @ 863e313`

```python
    if "api_key_env" in entry and "key_env" not in entry:
        entry["key_env"] = entry["api_key_env"]
```

已知键白名单(含一个"我们自己历史上写出去过、所以别报警"的 `provider` 键)。`hermes_cli/config.py:1318-1330 @ 863e313`

```python
    _KNOWN_KEYS = {
        # ``provider`` duplicates the ``providers.<name>`` mapping key and is
        # unused here, but Hermes' own config writer has historically emitted it
        # into provider entries. Accept it silently so those (self-written)
        # configs don't warn on every load.
        "provider",
        "name", "api", "url", "base_url", "api_key", "key_env", "api_key_env",
        "api_mode", "transport", "model", "default_model", "models",
        "context_length", "rate_limit_delay",
        "request_timeout_seconds", "stale_timeout_seconds",
        "discover_models", "extra_body", "extra_headers",
        "ssl_ca_cert", "ssl_verify",
    }
```

base_url 三选一,且**带占位符的 URL 跳过校验**(否则未展开的 raw 配置会让 provider 被静默丢弃,#14457)。`hermes_cli/config.py:1351-1362 @ 863e313`

```python
    for url_key in ("base_url", "url", "api"):
        raw_url = entry.get(url_key)
        if isinstance(raw_url, str) and raw_url.strip():
            candidate = raw_url.strip()
            # Accept URLs containing unresolved placeholder tokens — both
            # ``${ENV_VAR}`` env-refs and bare ``{region}``-style templates —
            # without URL validation. They are expanded at runtime, so a
            # caller reaching this normalizer with raw (un-expanded) config
            # would otherwise see the provider silently dropped (#14457).
            if re.search(r"\{[^}]+\}", candidate):
                base_url = candidate
                break
```

没有可用 base_url 或没有 name → 整条丢弃(返回 None)。`hermes_cli/config.py:1373-1374 @ 863e313`

```python
    if not base_url:
        return None
```

`api_mode` 接受 `transport` 作为同义词;`model` 接受 `default_model`。`hermes_cli/config.py:1402-1408 @ 863e313`

```python
    api_mode = entry.get("api_mode") or entry.get("transport")
    if isinstance(api_mode, str) and api_mode.strip():
        normalized["api_mode"] = api_mode.strip()

    model_name = entry.get("model") or entry.get("default_model")
    if isinstance(model_name, str) and model_name.strip():
        normalized["model"] = model_name.strip()
```

`models` 同时接受 dict 和 list(list 里可以是字符串 id 或 `{id: ...}` 行),否则 `/model`
会显示该 provider 有 0 个模型。`hermes_cli/config.py:1416-1421 @ 863e313`

```python
    elif isinstance(models, list) and models:
        # Hand-edited configs (and older Hermes versions) may write
        # ``models`` as a plain list of ids or as ``[{id: ...}]`` rows.
        # Preserve both by converting to the dict shape downstream code
        # expects; otherwise normalize silently drops the list and /model
        # shows the provider with (0) models.
```

### 9.4 `clear_model_endpoint_credentials`

切换离开自定义端点时,把 `model.api_key` / `model.api` / `model.api_mode` 清掉,
避免密钥留在 config.yaml 里并污染后续自定义解析。`hermes_cli/config.py:1060-1066 @ 863e313`

```python
    if clear_api_key:
        model_cfg.pop("api_key", None)
        model_cfg.pop("api", None)
    if clear_api_mode:
        model_cfg.pop("api_mode", None)
    if clear_base_url:
        model_cfg.pop("base_url", None)
```

注意 `clear_base_url` 默认 **False** —— 默认不清 base_url。`hermes_cli/config.py:1043-1049 @ 863e313`

```python
def clear_model_endpoint_credentials(
    model_cfg: Dict[str, Any],
    *,
    clear_api_key: bool = True,
    clear_api_mode: bool = True,
    clear_base_url: bool = False,
) -> Dict[str, Any]:
```

---

## 10. 配置键与环境变量(本段专项交付物)

### 10.1 环境变量(本段读到的)

| 变量 | 默认 | 读取点 @ 863e313 | 读它的函数 | 语义 / fallback |
|---|---|---|---|---|
| `HERMES_HOME` | 平台默认(`~/.hermes`;win32 `%LOCALAPPDATA%\hermes`) | `hermes_constants.py:71` | `_hermes_home_from_env` | config.yaml/.env 的目录。链:contextvar override → env → 平台默认 |
| `LOCALAPPDATA` | `~/AppData/Local` | `hermes_constants.py:56` | `_get_platform_default_hermes_home` | 仅 win32 |
| `HERMES_MANAGED` | `""` | `hermes_cli/config.py:357` | `get_managed_system` | 非空即 managed;`true/1/yes`→NixOS;`brew/homebrew` 被忽略;其他值原样返回。fallback:`$HERMES_HOME/.managed` 标记文件 |
| `HERMES_MANAGED` | `""` | `hermes_cli/config.py:616` | `format_managed_message` | 只用于错误文案 |
| `HERMES_MANAGED_DIR` | `""`(→`/etc/hermes`) | `hermes_cli/managed_scope.py:65` | `get_managed_dir` | 管理员覆盖层目录;与 `HERMES_MANAGED` 是**两套机制** |
| `HERMES_DEV` | 未设 | `hermes_cli/config.py:652` | `get_container_exec_info` | `=="1"` 时禁用 container-exec 转发 |
| `HERMES_UID` | 未设 | `hermes_cli/config.py:723` | `_resolve_hermes_uid_gid` | 非整数→None;Windows 直接 `(None, None)` |
| `HERMES_GID` | 未设 | `hermes_cli/config.py:724` | `_resolve_hermes_uid_gid` | 同上 |
| `HERMES_HOME_MODE` | `0o700` | `hermes_cli/config.py:786` | `_secure_dir` | 八进制字符串;解析失败回落 0700;managed 模式整段跳过 |
| `HERMES_CONTAINER` | 未设 | `hermes_cli/config.py:806` | `_is_container` | 任意真值 → 视为容器 → 跳过 chmod 0600 |
| `HERMES_SKIP_CHMOD` | 未设 | `hermes_cli/config.py:806` | `_is_container` | 同上 |
| `HERMES_S6_SUPERVISED_CHILD` | 未设 | `hermes_cli/main.py:649` | `_apply_profile_override` | 设了就不读 `active_profile` |
| `SUDO_USER` | `""` | `hermes_cli/main.py:550` | `_resolve_sudo_user_profile_env` | `sudo hermes -p x` 时到调用者 home 找 profile |
| `KUBERNETES_SERVICE_HOST` | 未设 | `hermes_constants.py:1263` | `is_container` | 只在 `hermes_constants` 版检测里用 |

**写入被禁的环境变量名**(不是"读"点,是 `save_env_value` 的拦截名单):
`hermes_cli/config.py:198-216` 全表 —— `LD_PRELOAD`、`LD_LIBRARY_PATH`、`LD_AUDIT`、`LD_DEBUG`、
`DYLD_INSERT_LIBRARIES`、`DYLD_LIBRARY_PATH`、`DYLD_FRAMEWORK_PATH`、`DYLD_FALLBACK_LIBRARY_PATH`、
`DYLD_FALLBACK_FRAMEWORK_PATH`、`PYTHONPATH`、`PYTHONHOME`、`PYTHONSTARTUP`、`PYTHONUSERBASE`、
`PYTHONEXECUTABLE`、`PYTHONNOUSERSITE`、`NODE_OPTIONS`、`NODE_PATH`、`PATH`、`SHELL`、`BROWSER`、
`EDITOR`、`VISUAL`、`PAGER`、`GIT_SSH_COMMAND`、`GIT_EXEC_PATH`、`GIT_SHELL`、`HERMES_HOME`、
`HERMES_PROFILE`、`HERMES_CONFIG`、`HERMES_ENV`。

### 10.2 config.yaml 键(本段涉及的)

| 键 | 默认 | 读/写点 @ 863e313 | 说明 |
|---|---|---|---|
| 全树默认 | `DEFAULT_CONFIG` | `hermes_cli/config.py:943` 导入 / `hermes_cli/config_defaults.py:7` 定义 | 默认值的唯一来源 |
| `max_turns`(根级) | — | `hermes_cli/config.py:3340` | 合并前被提升到 `agent.max_turns`,且仅当后者为 None |
| `agent.max_turns` | `500` | `hermes_cli/config_defaults.py:32` | 提升目标 |
| `skills.config.<key>` | — | `hermes_cli/config.py:1247` | skill 声明的配置变量存储位置(`SKILL_CONFIG_PREFIX="skills.config"`) |
| `model.api_key` / `model.api` | — | `hermes_cli/config.py:1061` | 切离自定义端点时被清除 |
| `model.api_mode` | — | `hermes_cli/config.py:1064` | 同上 |
| `model.base_url` | — | `hermes_cli/config.py:1066` | 同上,**默认不清** |
| `providers.<k>.base_url` / `.url` / `.api` | — | `hermes_cli/config.py:1351` | 三选一,首个合法者胜 |
| `providers.<k>.name` | 回落 `<k>` | `hermes_cli/config.py:1377` | 都没有则整条丢弃 |
| `providers.<k>.api_key` | — | `hermes_cli/config.py:1394` | 内联密钥 |
| `providers.<k>.key_env` / `.api_key_env` | — | `hermes_cli/config.py:1398` | 密钥所在的 env 变量名 |
| `providers.<k>.api_mode` / `.transport` | — | `hermes_cli/config.py:1402` | `transport` 是同义词 |
| `providers.<k>.model` / `.default_model` | — | `hermes_cli/config.py:1406` | 同义词 |
| `providers.<k>.models` | — | `hermes_cli/config.py:1410` | dict 或 list 都接受 |
| `providers.<k>.context_length` | — | `hermes_cli/config.py:1441` | 必须是 `>0` 的 int |
| `providers.<k>.rate_limit_delay` | — | `hermes_cli/config.py:1445` | int/float 且 `>=0` |
| `providers.<k>.discover_models` | — | `hermes_cli/config.py:1449` | 必须是 bool |
| `providers.<k>.extra_body` | — | `hermes_cli/config.py:1453` | 必须是 dict |
| `providers.<k>.extra_headers` | — | `hermes_cli/config.py:1460` | 可能带凭据,禁止下游日志 |
| `providers.<k>.ssl_ca_cert` | — | `hermes_cli/config.py:1464` | 非空字符串 |
| `providers.<k>.ssl_verify` | — | `hermes_cli/config.py:1468` | bool 或非空字符串 |

`ENV_VARS_BY_VERSION` 记录"每个配置版本新引入了哪些 env 变量",迁移时只提示新增的。`hermes_cli/config.py:951-958 @ 863e313`

```python
ENV_VARS_BY_VERSION: Dict[int, List[str]] = {
    3: ["FIRECRAWL_API_KEY", "BROWSERBASE_API_KEY", "BROWSERBASE_PROJECT_ID", "FAL_KEY"],
    4: ["VOICE_TOOLS_OPENAI_KEY", "ELEVENLABS_API_KEY"],
    5: ["WHATSAPP_ENABLED", "WHATSAPP_MODE", "WHATSAPP_ALLOWED_USERS",
        "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_ALLOWED_USERS"],
    10: ["TAVILY_API_KEY"],
    11: ["TERMINAL_MODAL_MODE"],
}
```

`REQUIRED_ENV_VARS` 是**空 dict** —— provider 选择在 setup 向导里做,没有普适必填项。`hermes_cli/config.py:964 @ 863e313`

```python
REQUIRED_ENV_VARS = {}
```

推论:`get_missing_env_vars(required_only=True)` **恒返回空列表**。`hermes_cli/config.py:979-981 @ 863e313`

```python
    for var_name, info in REQUIRED_ENV_VARS.items():
        if not get_env_value(var_name):
            missing.append({"name": var_name, **info, "is_required": True})
```

---

## 11. 可疑缺陷(只记录,不修)

**D1 · 告警去重集只增不减,注释说反了。**
注释声称"文件变了会自动清除",实际上从未 `discard`/`clear`,只是新增一个键。`hermes_cli/config.py:39-42 @ 863e313`

```python
# Track which (config_path, mtime_ns, size) tuples we've already warned about
# so concurrent CLI/gateway loads of a broken config.yaml don't spam stderr
# every time. Cleared automatically when the file changes (different mtime).
_CONFIG_PARSE_WARNED: set = set()
```

怎么踩到:长跑网关 + 用户反复保存坏 YAML,集合按编辑次数线性增长。单条元组很小,
实际是"极慢的泄漏"而非可用性问题;但如果有人依赖"文件修好后集合会缩回去",会被误导。

**D2 · 备份的 size 判重会漏掉同样大小的另一种损坏。**
`hermes_cli/config.py:85-88 @ 863e313`

```python
                if existing.stat().st_size == st.st_size:
                    # Same size as the current broken file — likely the same
                    # corruption already preserved. Avoid backup churn.
                    return None
```

怎么踩到:第一次损坏 100 字节 → 备份;用户改好;后来又坏成**另一份**恰好 100 字节的内容
→ 因为同目录已有 100 字节的 `.bak`,这次不备份。随后 `hermes config set` 重写 config.yaml,
这份内容永久丢失 —— 正是这个函数要防的场景。

**D3 · 秒级时间戳导致同一秒内的第二次备份被跳过。**
`hermes_cli/config.py:74-75 @ 863e313`

```python
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup_path = config_path.with_name(f"{config_path.name}.corrupt.{ts}.bak")
```

怎么踩到:脚本化编辑(编辑器 autosave、CI)在同一秒内产生两次不同 size 的损坏,
第二次 `backup_path.exists()` 为真 → 返回 None。

**D4 · `.bak` 永不清理。**
没有任何一处删除 `config.yaml.corrupt.*.bak`。全仓 grep 只有 `_backup_corrupt_config`
里的 glob 与测试。怎么踩到:反复损坏 → home 目录里堆积任意多份备份,且每份都可能含密钥
(config.yaml 允许内联 `api_key`),权限继承自 `copy2` 而非重新 `_secure_file`。

**D5 · `_IS_WINDOWS` 是死代码。**
`hermes_cli/config.py:157 @ 863e313`

```python
_IS_WINDOWS = platform.system() == "Windows"
```

全仓 grep 显示 `hermes_cli/config.py` 内无第二处引用,其他模块各自定义了同名常量
(`gateway/status.py:40`、`hermes_bootstrap.py:55`、`hermes_cli/kanban_db.py:161`,
且都用 `sys.platform == "win32"` 而不是 `platform.system()`)。风险:后续有人以为
`config._IS_WINDOWS` 在被使用,或复制这份 `platform.system()` 写法(在 Cygwin/MSYS
下与 `sys.platform` 判定不一致)。

**D6 · `HERMES_HOME_MODE=0` 会把 home 权限设成 000。**
`hermes_cli/config.py:786-787 @ 863e313`

```python
        mode_str = os.environ.get("HERMES_HOME_MODE", "").strip()
        mode = int(mode_str, 8) if mode_str else 0o700
```

怎么踩到:`mode_str = "0"` 是**真值**字符串,`int("0", 8) == 0`,于是 `os.chmod(path, 0)`。
非 root 用户随即读不了自己的 HERMES_HOME。没有任何下界校验。

**D7 · 任意 `HERMES_MANAGED` 值会把安装伪装成 managed 并可能硬失败启动。**
`hermes_cli/config.py:364 @ 863e313`

```python
        return _MANAGED_SYSTEM_NAMES.get(normalized, raw)
```

怎么踩到:操作员为了别的用途设了 `HERMES_MANAGED=apt`(或误设 `HERMES_MANAGED=false`
—— 注意 `"false"` 非空,**照样**被当成 managed)。后果:`is_managed()` 为真 →
`ensure_hermes_home()` 走校验分支 → 若 `cron/sessions/logs/memories` 任一缺失就 `RuntimeError`
并要求跑 `nixos-rebuild`。`hermes_cli/config.py:924-930 @ 863e313`

```python
    for subdir in ("cron", "sessions", "logs", "memories"):
        d = home / subdir
        if not d.is_dir():
            raise RuntimeError(
                f"{d} does not exist. "
                "Run 'sudo nixos-rebuild switch' first."
            )
```

**D8 · `detect_install_method` 可以返回文档之外的值。**
`hermes_cli/config.py:481-483 @ 863e313`

```python
    managed = get_managed_system()
    if managed:
        return managed.lower().replace(" ", "-")
```

docstring 承诺返回 `'docker' | 'nix' | 'nixos' | 'git' | 'unknown'`,但接上 D7,
`HERMES_MANAGED=apt` 会让它返回 `"apt"`。下游 `recommended_update_command_for_method`
的兜底是 `"hermes update"`,不会崩,但任何 `method in {...}` 式的判定会静默走错分支。

**D9 · `_format_config_get_value` 里重复 import json。**
模块顶部已 `import json`(第 18 行),函数内又局部 import。`hermes_cli/config.py:1177-1179 @ 863e313`

```python
    if as_json:
        import json
        return json.dumps(value, ensure_ascii=False)
```

无功能影响,但局部 import 会遮蔽模块级名字,是"看起来像有意为之"的噪音。

**D10 · 两套容器检测,能力不同。**
`config._is_container()` 只认 `/.dockerenv` 与 cgroup v1 里的 docker/lxc/kubepods,
不认 podman 的 `/run/.containerenv`、不认 `KUBERNETES_SERVICE_HOST`、不认 cgroup v2。`hermes_cli/config.py:809-816 @ 863e313`

```python
    if os.path.exists("/.dockerenv"):
        return True
    # LXC / cgroup-based detection
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8") as f:
            cgroup_content = f.read()
        if "docker" in cgroup_content or "lxc" in cgroup_content or "kubepods" in cgroup_content:
            return True
```

而 `hermes_constants.is_container()` 全都认,且**缓存结果**。`hermes_constants.py:1256-1265 @ 863e313`

```python
    if os.path.exists("/.dockerenv"):
        _container_detected = True
        return True
    if os.path.exists("/run/.containerenv"):
        _container_detected = True
        return True
    # Kubernetes always injects this into pod containers; absent on hosts.
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        _container_detected = True
        return True
```

怎么踩到:cgroup v2 的 podman/containerd 环境里,`_secure_file()` 会照常 `chmod 0600`,
在 volume 挂载且 gateway/dashboard 跑在不同 UID 的部署里正是它想避免的破坏。同一文件里
`_running_in_container()`(512 行)走的是 constants 版 —— 于是**同一进程内两个"在不在容器里"
的答案可以不同**。另外 `_is_container()` 每次调用都重开 `/proc/1/cgroup`,而它被
`_secure_file()` 逐文件调用。

**D11 · `_HERMES_HOME_ENSURED` 在锁外被修改。**
`ensure_hermes_home()` 在 `_load_config_impl` 内是持锁的,但也被 `agent/prompt_builder.py:2013`
与 `hermes_cli/setup.py:2954` 直接调用(不持 `_CONFIG_LOCK`)。`hermes_cli/config.py:914 @ 863e313`

```python
    _HERMES_HOME_ENSURED.add(key)
```

评估:set 的 add/in 在 CPython 下是原子的,最坏后果是重复执行一次目录walk,**不会**损坏状态。
记录在此是因为"看起来像竞态"而实际不是,值得写明避免以后误判。

**D12 · `_set_nested` 末段对 list 无保护。**
`hermes_cli/config.py:1037-1038 @ 863e313`

```python
    if isinstance(current, list):
        current[int(last)] = value
```

怎么踩到:`hermes config set custom_providers.abc value` 或索引越界 → `ValueError`/`IndexError`
直接冒到 CLI(中间段有明确的 `TypeError` 友好信息,末段没有)。

---

## 12. 文档与代码的出入

**C1 · 模块 docstring 说配置在 `~/.hermes/`,Windows 上不是。**
`hermes_cli/config.py:4-6 @ 863e313`

```python
Config files are stored in ~/.hermes/ for easy access:
- ~/.hermes/config.yaml  - All settings (model, toolsets, terminal, etc.)
- ~/.hermes/.env         - API keys and secrets
```

实际路径见 `hermes_constants.py:55-58`(win32 → `%LOCALAPPDATA%\hermes`)。README 自己
写对了(README.md:59 明确区分原生 Windows 与 WSL2),是 docstring 落后。

**C2 · 模块 docstring 宣称有 `hermes config wizard`,子命令不存在。**
`hermes_cli/config.py:14 @ 863e313`

```python
- hermes config wizard   - Re-run setup wizard
```

`config_command()` 没有 `wizard` 分支(5135–5290 只有 show/edit/get/set/unset/path/env-path/migrate/check),
argparse 也没注册它。`hermes_cli/subcommands/config.py:22 @ 863e313`

```python
    config_subparsers = config_parser.add_subparsers(dest="config_command")
```

后果:`hermes config wizard` 被 argparse 以 "invalid choice" 拒掉(连 `config_command()`
的 "Unknown config command" 分支都到不了)。反过来,docstring 也**没提** `path` / `env-path` /
`check` / `migrate` 这四个真实存在的子命令。

**C3 · `_LOAD_CONFIG_CACHE` 上方注释自相矛盾。**
第 236 行说 key 是 `(path, mtime_ns, size)`,而第 243–247 行(以及类型注解)说 key 是 path、
value 才是 6 元组。`hermes_cli/config.py:236-237 @ 863e313`

```python
# (path, mtime_ns, size) -> cached expanded config dict.
# load_config() returns a deepcopy of the cached value when the file
```

以代码为准:`hermes_cli/config.py:248` 的注解是 `Dict[str, Tuple[...]]`,`path_key = str(config_path)`。

**C4 · 注释说跳过的是 `yaml.safe_load`,代码用的是 `fast_safe_load`。**
`hermes_cli/config.py:238-239 @ 863e313`

```python
# hasn't changed since the last load, skipping yaml.safe_load +
# _deep_merge + _normalize_* + _expand_env_vars (~13 ms/call).
```

实际读取走 `utils.fast_safe_load`(`hermes_cli/config.py:3338`)。语义等价,措辞过时。

**C5 · `load_config()` docstring 说缓存键是"config 文件的 (mtime_ns, size)",实际是四元签名 + env 快照。**
`hermes_cli/config.py:3118-3119 @ 863e313`

```python
    Cached on the config file's (mtime_ns, size). Returns a deepcopy of
    the cached value when unchanged, since most call sites mutate the
```

实际还折进了 managed 文件签名(3311–3316)与 `${VAR}` 环境快照(3330)。

**C6 · denylist 注释把 `HERMES_CONFIG` / `HERMES_ENV` 说成"Hermes 运行时定位标志",
但代码里没有任何读取点。**
`hermes_cli/config.py:183-186 @ 863e313`

```python
# * ``HERMES_HOME`` / ``HERMES_PROFILE`` / ``HERMES_CONFIG`` /
#   ``HERMES_ENV`` — Hermes runtime location flags. Writing these into
#   ``.env`` would relocate state in ways the user did not request from
#   the dashboard. ``config.yaml`` is the supported surface for these.
```

我在全仓 `--include=*.py` grep `HERMES_CONFIG\b|HERMES_ENV\b`,除本文件的注释/denylist 外,
只剩 `tools/code_execution_tool.py` 的子进程放行名单(同样只是"放行",不是读)。`tools/code_execution_tool.py:168-174 @ 863e313`

```python
_HERMES_CHILD_ALLOWED = frozenset({
    "HERMES_HOME",
    "HERMES_PROFILE",
    "HERMES_CONFIG",
    "HERMES_ENV",
    "HERMES_DELEGATED_CHILD_CONTEXT",
})
```

同样,`HERMES_PROFILE` 有读取点但**不参与 home 解析**(kanban 作者名、ACP 作用域):
profile → HERMES_HOME 的翻译走的是 `--profile` 参数 + `active_profile` 文件,不是 `HERMES_PROFILE`。
注释里"配置这些会 relocate state"对 `HERMES_HOME` 成立,对 `HERMES_CONFIG`/`HERMES_ENV` 不成立
—— 它们目前是纯占位。**未确证**部分:是否有非 Python(shell/nix)消费者读它们,我未逐一排查。

**C7 · `_backup_corrupt_config` docstring 说"mirrors the Gemini #21541 lstat guard",
代码用的是 `Path.is_symlink()`。**
`hermes_cli/config.py:62-64 @ 863e313`

```python
    Returns the backup path on success, else ``None``. Symlinks are not
    followed/copied (mirrors the Gemini #21541 lstat guard) to avoid
    clobbering whatever a malicious/misconfigured symlink points at.
```

语义上 `is_symlink()` 确实基于 lstat,不算冲突,但"lstat guard"的措辞会让读者去找
`os.lstat` 调用;记录以免下次白找。

---

## 13. 配套测试(本段的行为规格)

跑法(第一轮已验证可用):

```bash
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/hermes_cli/test_config.py
```

- `tests/hermes_cli/test_config.py` —— 损坏配置的三条规格:告警去重 + 双通道输出、
  `.bak` 备份且**不重置原文件**、last-known-good 保留。它直接操作 `_CONFIG_PARSE_WARNED`
  说明该 set 是测试可见的全局状态。
- `tests/hermes_cli/test_ensure_hermes_home_memo.py` —— 记忆化规格:**删子目录不恢复、
  删 home 恢复、换 home 路径重新建骨架**。这是 §5.1 那个取舍的成文断言。
- `tests/hermes_cli/test_ensure_hermes_home_uid_34107.py` —— `HERMES_UID`/`HERMES_GID` chown。
- `tests/hermes_cli/test_managed_installs.py` —— managed 模式判定与拦截。
- `tests/hermes_cli/test_container_aware_cli.py` —— `.container-mode` / `get_container_exec_info`。
- `tests/hermes_cli/test_provider_config_validation.py` —— `_normalize_custom_provider_entry`
  的告警去重(直接 clear `_PROVIDER_NORMALIZE_WARNED`)。
- `tests/hermes_cli/test_custom_provider_normalize_no_mutate.py` —— "不得就地改缓存 sub-dict"。
- `tests/hermes_cli/test_cmd_update.py` / `test_cmd_update_docker.py` / `test_pip_install_detection.py`
  / `tests/test_install_sh_install_method_stamp.py` —— 安装方式检测与打戳。
- `tests/hermes_cli/test_set_config_value.py`、`test_config_read_guard.py`、
  `test_read_raw_config_readonly.py`、`test_config_env_expansion.py`、`test_config_env_refs.py`、
  `test_config_loader_e2e.py`、`test_managed_scope_config.py` —— 解析链其余部分(超出本段,
  但是同一条链的规格)。
- `tests/docker/test_puid_pgid_remap.py`、`tests/cron/test_file_permissions.py` —— 权限/属主侧。
- `tests/conftest.py` 的 `_isolate_hermes_home` autouse fixture 把 `HERMES_HOME` 指向
  临时目录 —— 这条 fixture 本身就是"所有路径必须过 `get_hermes_home()`"这条纪律的执行者。

---

## 14. 重实现要点

如果从零重写这一层,以下八条是必须知道的:

1. **home 解析必须是一个函数,且必须在任何模块 import 之前定住。**
   Hermes 的做法是 CLI 入口手工扫 `sys.argv` 拿 `--profile`,翻译成路径写回
   `os.environ["HERMES_HOME"]`,然后才 import 业务模块。代价是要给 argv 扫描加一堆特例
   (`--` 之后、`mcp add --args` 之后、`-p no:xdist` 之类的非法名)。如果你的语言/框架允许
   显式传递配置根,**优先传参**,不要学这个;但如果你已经有大量 import-time 常量,这是唯一
   低成本的补救。同时保留一个 context-local override 给"同进程内临时切 home",并明确区分
   "跟 profile 走的资产"与"跟进程走的资产"。

2. **默认值放在独立模块,合并必须是深合并,并且要处理 YAML 的空 section = None。**
   `terminal:` 这种空键在 YAML 里是 `None`,浅合并/朴素深合并都会把整个默认 dict 干掉。
   规则:`override` 的 `None` 遇上 dict 默认值 → 当作"该键不存在"。这条规则救的是
   "用户只是想留个占位注释"这一类最常见的手写错误。

3. **配置损坏是安全事件,不只是体验事件。**
   必须有三件套:(a) 去重的、双通道(日志 + stderr)的告警;(b) 首次告警时把坏文件快照下来
   (因为后续任何 `config set`/wizard 都会覆盖它);(c) **进程内 last-known-good** ——
   解析失败时继续供上一次成功的配置,而不是退回默认。第三条是因为拒绝规则(deny list)
   放在配置里:退回默认 = 静默解除防护。备份要防 symlink、防同秒重名、并且要考虑清理策略
   (Hermes 没做清理,是个已知缺口)。

4. **缓存签名必须包含"所有输入源",不只是主文件的 mtime。**
   Hermes 的签名 = 用户文件 (mtime_ns,size) + 管理员覆盖文件 (mtime_ns,size) + **本次展开
   所依赖的每个环境变量的当时取值**。第三项是被真实 bug 逼出来的:第一次 `load_config()`
   若跑在 `.env` 加载之前,未展开的 `${VAR}` 字面量会被钉死一整个进程。如果你的配置支持
   env 插值,这条几乎一定会咬你。

5. **读接口要分层,并且把"能不能改返回值"写进函数名。**
   Hermes 给了四个:`load_config()`(合并+展开+深拷贝)、`load_config_readonly()`(共享对象)、
   `read_raw_config()`(原始+缓存+拷贝)、`read_user_config_raw()`(原始+无缓存+失败抛异常,
   专供读-改-写)。第四个的存在理由很硬:写回时若合并了默认值,会把几百个默认键固化进用户文件。
   缺点是只读契约靠文档不靠类型,建议用不可变视图强制。

6. **写路径要 fail-closed。**
   "文件不存在"与"文件存在但读不出来"都返回 `{}` 是个陷阱 —— 读-改-写的调用方会把不可读的
   配置整文件顶掉。解法是所有整文件写都过同一个 `atomic_config_write()`,它先做
   "能不能读出第一个字节"的探测,读不出就拒绝写。加上原子替换(新 inode)让 mtime 缓存自动失效。

7. **锁的粒度选可重入锁,并且要覆盖缓存字典本身。**
   理由有二:YAML 的 C 后端对同文件并发 `safe_load` 不安全;写路径内部会调读路径。
   代价是备份大文件、慢盘 chmod 这类 I/O 都在锁内,会阻塞所有配置读 —— 值得把慢操作挪出去。

8. **"每次加载都保证目录存在"要记忆化,但要说清记忆化的边界。**
   `ensure_hermes_home()` 原本在每次 `load_config()` 里做 ~14 次 syscall。记忆化后只在
   home 根消失时重跑 —— 于是"删掉 sessions/ 不会自动恢复"成为**被测试固定下来的行为**。
   另外:具名 profile 的目录**不能**被静默 mkdir(否则被删的 profile 会因为残留进程复活),
   必须抛错。权限/属主要可配(容器场景 `chmod 0600` 会直接破坏多 UID 部署),但配置项要有
   下界校验 —— Hermes 的 `HERMES_HOME_MODE` 没有,`=0` 就能把自己锁在门外。

---

## 15. 未确证清单

- `HERMES_CONFIG` / `HERMES_ENV` 是否有非 Python(shell / nix / Dockerfile)消费者:
  我只 grep 了 `--include=*.py`,未逐一排查 `scripts/`、`nix/`、`Dockerfile`。
- `_backup_corrupt_config` 产生的 `.bak` 是否有任何清理路径:我 grep 了
  `config.yaml.corrupt` 与 `.corrupt.` 在全仓的出现,只见到本函数与测试;但我没有
  排查 doctor / uninstall 之类可能按 glob 清理 home 的代码。
- `_normalize_custom_provider_entry` 之后的消费链(1477 行之后的
  `_custom_provider_entry_to_provider_config` / `get_compatible_custom_providers`)
  不在本段,只读到函数签名。
- `fast_safe_load` 与 `yaml.safe_load` 的行为差异(是否只是选 CLoader)未验证。
