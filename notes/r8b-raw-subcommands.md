# r8b-raw-subcommands —— profiles.py + subcommands/ 子命令树

> 底稿（证据层）。研究对象 `NousResearch/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`。
> 所有断言紧跟 `路径:行号 @ 863e313` + 逐字代码块。路径均相对 hermes-agent 仓库根。
> 本段范围：`hermes_cli/profiles.py`（2262 行）+ `hermes_cli/subcommands/` 全部 44 个 `.py`
> （其中 `subcommands/config.py`、`subcommands/pairing.py` 前轮已精读，本稿只把它们放进契约表，不展开）。

---

## 0. 自验记录

**三条前提全部实测，两条为假、一条为假中带真。这是本稿最重要的输出，先说结论：**

| # | 委托方给的前提 | 实测结论 | 证据位置 |
|---|---|---|---|
| P1 | "`subcommands/` 里每个文件都遵循同一套注册契约" | **部分为真**：函数签名层面高度统一（41/41 个 builder 同形），但"注册"这一环**根本不存在自动机制**——`subcommands/__init__.py` 不导出任何东西，注册是 main.py 里 44 行手写 import + 44 行手写调用。另有 9 类实质偏离。 | §3.1 / §3.3 |
| P2 | "`profiles.py` 只算路径，不改全局状态" | **为假**。它建目录、写文件、`chmod 0600`、拷贝 `.env`、`shutil.rmtree` 整棵树、`psutil` 扫进程表并 **SIGTERM/SIGKILL 其它进程**、`subprocess` 起子进程、往 stdout 打印、并且**直接改 `os.environ["HERMES_HOME"]`**。唯一符合该描述的是末尾的 `resolve_profile_env()`。 | §2.12 |
| P3 | "profile 名只在一个地方校验" | **为假**。profile 域内同一条正则在 **6 个 Python 位置**各写一遍（两种写法：有界 64 / 无界）+ **4 份前端 TS 副本**；另有 2 处 webhook 域用同形无界写法。并且存在**两个同名 `validate_profile_name()` 函数**（`hermes_cli/profiles.py` 与 `hermes_cli/service_manager.py`），规则不同（上限 64 vs 251、查/不查保留名）。已发现一处因此产生的用户可见行为偏差。 | §2.3 / §4-C1 |

**锚点复核**（委托要求至少抽验 15 条；实际做了全量机器复核）：

本稿共 **132** 条完整锚点（`路径:行号 @ 863e313` + 紧跟的逐字代码块），
另有 **212** 个去重后的 `路径:行号` 引用（含表格与行文中的短引用）。复核方式：

1. **全部 132 条**跑脚本比对——不只比首行，而是把代码块**逐行**与该文件从锚点行号起的
   连续行做去空白全等比对，任一行不符即报错。
2. **全部 212 个**去重引用另跑一遍：文件必须存在、行号必须在范围内、且该行**不得为空行**
   （防止锚点落在 docstring 之间的空行上，看似有效实则指向不到内容）。

结果：

- 行号漂移 **4 条**，全部为手抄偏移，已逐条修正：
  `AGENTS.md` 1211→1212、`hermes_cli/profiles.py` 82→80、713→714、1806→1805。
- 指向空行/不达意行 **2 条**，已改指真正承载断言的行：
  `hermes_cli/profiles.py` 273→274（原指 docstring 中的空行）、409→410（原指裸 `try:`）。
- 格式规范化 **160 处**（不算错误，但会让读者无法定位）：99 处 `` `profiles.py:N` ``
  补全为 `` `hermes_cli/profiles.py:N` ``、34 处其它未限定路径补全、
  27 处"代码块前只写了短引用"升级为完整锚点。
- 修正后：**132/132 锚点通过，212/212 引用通过。**
- 复核脚本：`<scratchpad>/verify_anchors.py`（一次性工具，未入库）。

**未做的事**：没有真实运行 hermes CLI（本轮无 venv、且 profiles.py 的写路径会污染 `~/.hermes`）。
所有行为断言来自代码 + 仓库自带测试（`tests/hermes_cli/test_profiles.py` 等）的交叉读。
凡属"我从代码推断、无测试背书"的，在 §4 里标了置信度。

---

## 1. 段内地图

### 1.1 本段两块东西是什么关系

一句话：**`subcommands/` 决定"用户敲的那行字变成哪个 handler"，`profiles.py` 决定"那个 handler 会去读哪一份配置"。**

二者在 `main.py` 里前后脚发生，但**顺序是反的**——profile 解析发生在 argparse **之前**，
甚至在绝大多数 hermes 模块被 import 之前：

`hermes_cli/main.py:690 @ 863e313`

```
_apply_profile_override()
```

这一行是模块级语句，不在任何函数里。它下面才是：

`hermes_cli/main.py:694 @ 863e313`

```
from hermes_cli.config import get_hermes_home
```

原因写在它上面的块注释里：

`hermes_cli/main.py:508 @ 863e313`

```
# ---------------------------------------------------------------------------
# Profile override — MUST happen before any hermes module import.
#
# Many modules cache HERMES_HOME at import time (module-level constants).
# We intercept --profile/-p from sys.argv here and set the env var so that
# every subsequent ``os.getenv("HERMES_HOME", ...)`` resolves correctly.
# The flag is stripped from sys.argv so argparse never sees it.
# Falls back to ~/.hermes/active_profile for sticky default.
# ---------------------------------------------------------------------------
```

**这就是整个多实例隔离机制的全部诡计**：不做依赖注入、不传 context，而是在进程最早期
把 `HERMES_HOME` 环境变量钉死，然后让全仓 100+ 个 `get_hermes_home()` 调用点自然读到正确的值。
代价是 `-p` 必须自己从 `sys.argv` 里手动扒出来（argparse 还没建），这就是 §4-C1 那个 bug 的土壤。

### 1.2 `subcommands/` 文件清单（44 个 .py，3543 行）

按角色分四类：

| 角色 | 文件 | 行数 |
|---|---|---|
| 包门面（**空**，无导出） | `__init__.py` | 18 |
| 共享 helper（**非 builder**） | `_shared.py` | 29 |
| 标准 builder（1 handler / 1 顶层命令） | 其余 40 个 | 各 18–316 |
| 多 handler / 多顶层命令 builder | `gateway.py`(355)、`dashboard.py`(214) | — |

按体量排（后续 §3.3 只讲偏离者，其余不逐个展开）：

```
gateway.py 355 | skills.py 316 | dashboard.py 214 | profile.py 203 | cron.py 195
mcp.py 126 | plugins.py 106 | debug.py 100 | sync.py 99 | auth.py 98 | tools.py 95
slack.py 93 | claw.py 92 | webhook.py 83 | logs.py 78 | login.py 78 | hooks.py 77
approvals.py 77 | update.py 76 | config.py 68 | setup.py 67 | gui.py 63 | security.py 62
model.py 62 | memory.py 53 | acp.py 52 | import_agent.py 49 | uninstall.py 46
pairing.py 40 | backup.py 38 | monitoring.py 36 | prompt_size.py 36 | doctor.py 35
import_cmd.py 31 | skin.py 30 | _shared.py 29 | status.py 28 | logout.py 28 | dump.py 28
insights.py 25 | whatsapp.py 22 | console.py 18 | version.py 18 | __init__.py 18
```

### 1.3 `profiles.py` 分区（2262 行，19 个公开函数 + 15 个私有）

| 行段 | 分区 | 内容 |
|---|---|---|
| 22–260 | 模块常量 | 名字正则、7 张目录/文件排除表、保留名 |
| 263–299 | 路径 helper | `_get_profiles_root` / `_get_default_hermes_home` / `_get_wrapper_dir` |
| 302–383 | 校验 | `normalize_profile_name` / `validate_profile_name` / `validate_alias_name` / `get_profile_dir` |
| 386–618 | alias 包装脚本 | 建/删/反查（`build_alias_map` 是性能事故的修复产物） |
| 621–798 | `ProfileInfo` + 读侧 | 分布式元数据、config 读取、网关存活探测、skill 计数缓存 |
| 801–878 | `profile.yaml` | 描述元数据的原子读写 |
| 881–1285 | CRUD | `list_profiles` / `profiles_to_serve` / `create_profile` / `seed_profile_skills` / `backfill_profile_envs` |
| 1288–1793 | 删除路径 | 进程猎杀、rmtree 重试、服务清理 |
| 1796–1864 | 活动 profile | 粘性文件 + 从 HERMES_HOME 反推 |
| 1867–2120 | 导出/导入 | 两套 ignore、GNU tar、安全解包 |
| 2123–2239 | 重命名 | 目录 + alias + Honcho host 迁移 |
| 2242–2262 | **`resolve_profile_env`** | 全模块唯一的"纯算路径"函数 |

---

## 2. profiles.py 逐机制精读

### 2.1 三层路径解析：为什么 `_get_profiles_root()` 不是 `~/.hermes/profiles`

`hermes_cli/profiles.py:267 @ 863e313`

```
def _get_profiles_root() -> Path:
    """Return the directory where named profiles are stored.

    Anchored to the hermes root, NOT to the current HERMES_HOME
    (which may itself be a profile).  This ensures ``coder profile list``
    can see all profiles.

    In Docker/custom deployments where HERMES_HOME points outside
    ``~/.hermes``, profiles live under ``HERMES_HOME/profiles/`` so
    they persist on the mounted volume.
    """
    return _get_default_hermes_home() / "profiles"
```

**没有它会坏什么**：如果 profiles 根锚在"当前 HERMES_HOME"上，那么在 profile `coder` 里跑
`hermes profile list` 就会去找 `~/.hermes/profiles/coder/profiles/`——空目录，用户看不到任何兄弟 profile，
也就无法 `hermes profile use` 切走。锚定"root"是让 profile 之间**互相可见但互相隔离**的关键。

`_get_default_hermes_home()` 只是转手：

`hermes_cli/profiles.py:281 @ 863e313`

```
def _get_default_hermes_home() -> Path:
    """Return the default (pre-profile) HERMES_HOME path.

    In standard deployments this is ``~/.hermes``.
    In Docker/custom deployments where HERMES_HOME is outside ``~/.hermes``
    (e.g. ``/opt/data``), returns HERMES_HOME directly.
    """
    from hermes_constants import get_default_hermes_root
    return get_default_hermes_root()
```

真正的三分支逻辑在 `hermes_constants` 里：

`hermes_constants.py:178 @ 863e313`

```
    native_home = _get_platform_default_hermes_home()
    env_home = os.environ.get("HERMES_HOME", "")
    if not env_home:
        return native_home
    env_path = Path(env_home)
    try:
        env_path.resolve().relative_to(native_home.resolve())
        # HERMES_HOME is under ~/.hermes (normal or profile mode)
        return native_home
    except ValueError:
        pass

    # Docker / custom deployment.
    # Check if this is a profile path: <root>/profiles/<name>
    # If the immediate parent dir is named "profiles", the root is
    # the grandparent — this covers Docker profiles correctly.
    if env_path.parent.name == "profiles":
        return env_path.parent.parent

    # Not a profile path — HERMES_HOME itself is the root
    return env_path
```

三种部署形态一条函数吃下：
1. `HERMES_HOME` 未设 → 平台原生默认（POSIX `~/.hermes`，Win `%LOCALAPPDATA%\hermes`）；
2. `HERMES_HOME` 在 `~/.hermes` 之下（含 profile 模式）→ 返回 `~/.hermes`；
3. `HERMES_HOME` 在别处（Docker `/opt/data`）→ 若父目录名是 `profiles` 就退两级，否则它自己就是 root。

分支 3 的"父目录名是 `profiles`"是个**字符串启发式**，不是结构判断。`/opt/data/profiles/coder` 与
`/home/u/junk/profiles/coder` 无法区分——但因为只用于推 root，代价可控。

最终落在 `get_profile_dir`：

`hermes_cli/profiles.py:370 @ 863e313`

```
def get_profile_dir(name: str) -> Path:
    """Resolve a profile name to its HERMES_HOME directory."""
    canon = normalize_profile_name(name)
    if canon == "default":
        return _get_default_hermes_home()
    return _get_profiles_root() / canon
```

注意 `default` 不是 `profiles/default/`，而是 root 本身。这是"零迁移向后兼容"的设计选择，
在文件头就声明了：

`hermes_cli/profiles.py:8 @ 863e313`

```
The "default" profile is ``~/.hermes`` itself — backward compatible,
zero migration needed.
```

代价是 `default` 这个名字在后面所有 CRUD 里都要特判：`create_profile` 拒绝它
（`hermes_cli/profiles.py:1042`）、`delete_profile` 拒绝它（`hermes_cli/profiles.py:1482`）、`rename_profile`
两头都拒绝（`hermes_cli/profiles.py:2197`、`hermes_cli/profiles.py:2199`）、`import_profile` 拒绝它
（`hermes_cli/profiles.py:2090`）、`export_profile` 要临时 stage 一份才能让归档里出现 `default/` 目录名
（`hermes_cli/profiles.py:1952`）。**一个"省掉迁移"的决定，换来了 5 处永久特判。**

### 2.2 `-p coder` 到底怎么变成 `HERMES_HOME`

走法（一次具体请求）：用户敲 `hermes -p coder gateway start`。

1. `main.py` 模块级执行 `_apply_profile_override()`（`hermes_cli/main.py:690`）。
2. 它线性扫 `sys.argv[1:]` 找 `-p` / `--profile` / `--profile=`：

`hermes_cli/main.py:589 @ 863e313`

```
        if arg in {"--profile", "-p"} and i + 1 < len(argv):
            profile_name = argv[i + 1]
            consume = 2
            profile_index = i
            break
```

   扫描是**全 argv 范围**的（不限于子命令前），因为历史上 `hermes chat -p coder` 也能用：

`hermes_cli/main.py:569 @ 863e313`

```
    # 1. Check for explicit -p / --profile flag. Historically this worked even
    # after the subcommand (`hermes chat -p coder`), so keep scanning broadly.
    # The exception is command-argv passthrough regions such as `mcp add --args`.
```

   全范围扫描带来两个必须打的补丁：
   - `value_flags` 集合（`hermes_cli/main.py:572`）用于跳过"带值的顶层 flag"，否则 `hermes -m gpt5 -p x` 里的值会被误当命令；
   - `_inside_mcp_add_args()`（`hermes_cli/main.py:524`）在遇到 `hermes mcp add ... --args` 后**停止扫描**，
     因为那之后的 argv 属于被托管的子进程（例如 Docker MCP Toolkit 自己就有 `--profile`）。

3. 拿到字符串后做正则闸：

`hermes_cli/main.py:611 @ 863e313`

```
    # 1b. Reject values that can't be valid profile names (e.g. pytest's
    # "-p no:xdist" would be misread as profile "no:xdist" otherwise).
    # Mirrors hermes_cli.profiles._PROFILE_ID_RE so we never call
    # resolve_profile_env() with a value it must reject + sys.exit on.
    if profile_name is not None and consume == 2:
        import re as _re

        if not _re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", profile_name):
            profile_name = None
            consume = 0
            profile_index = None
```

   这里就是 §4-C1 的 bug 现场：正则跑在**未 normalize** 的原始 argv 值上。

4. 没有显式 flag 时，两级回退：先信已设好的 `HERMES_HOME`（且它父目录名为 `profiles` 才信）：

`hermes_cli/main.py:632 @ 863e313`

```
    hermes_home_env = os.environ.get("HERMES_HOME", "")
    if profile_name is None and hermes_home_env:
        if Path(hermes_home_env).parent.name == "profiles":
            return
```

   再读粘性文件 `active_profile`，但 s6 监管子进程要排除：

`hermes_cli/main.py:649 @ 863e313`

```
    if profile_name is None and not os.environ.get("HERMES_S6_SUPERVISED_CHILD"):
```

   排除理由写在上面的注释里（`hermes_cli/main.py:639`）：容器里保留槽位 `gateway-default` 跑的是裸
   `hermes gateway run`，如果它也读 `active_profile`，用户在面板上切一次 profile 就会
   把"默认网关"整个重定向进那个 profile——结果是活动 profile 有两个网关、默认 profile 一个都没有。

5. 最后调 `profiles.resolve_profile_env()`，把返回值写进环境并从 argv 里剪掉 flag：

`hermes_cli/main.py:663 @ 863e313`

```
    if profile_name is not None:
        try:
            from hermes_cli.profiles import resolve_profile_env

            hermes_home = resolve_profile_env(profile_name)
        except FileNotFoundError as exc:
            hermes_home = _resolve_sudo_user_profile_env(profile_name)
            if not hermes_home:
                print(f"Error: {exc}", file=sys.stderr)
                sys.exit(1)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            # A bug in profiles.py must NEVER prevent hermes from starting
            print(
                f"Warning: profile override failed ({exc}), using default",
                file=sys.stderr,
            )
            return
        os.environ["HERMES_HOME"] = hermes_home
        # Strip the flag from argv so argparse doesn't choke
        if consume > 0 and profile_index is not None:
            start = profile_index + 1  # +1 because argv is sys.argv[1:]
            sys.argv = sys.argv[:start] + sys.argv[start + consume :]
```

   三条异常语义分层很清楚：**"profile 不存在"** 先试 sudo 回退（root 代跑时 profile 库属于
   `SUDO_USER`）再退出 1；**"名字非法"** 直接退出 1；**"其它任何异常"** 只警告不阻断——
   注释直说 "A bug in profiles.py must NEVER prevent hermes from starting"。这是可用性优先的
   刻意取舍：宁可跑在默认 profile 上，也不能因为一个 profile 模块的 bug 让 CLI 完全起不来。

6. `resolve_profile_env` 本体是全模块唯一的纯函数：

`hermes_cli/profiles.py:2246 @ 863e313`

```
def resolve_profile_env(profile_name: str) -> str:
    """Resolve a profile name to a HERMES_HOME path string.

    Called early in the CLI entry point, before any hermes modules
    are imported, to set the HERMES_HOME environment variable.
    """
    canon = normalize_profile_name(profile_name)
    validate_profile_name(canon)
    profile_dir = get_profile_dir(canon)

    if canon != "default" and not profile_dir.is_dir():
        raise FileNotFoundError(
            f"Profile '{canon}' does not exist. "
            f"Create it with: hermes profile create {canon}"
        )

    return str(profile_dir)
```

   **它 raise，不 `sys.exit`**——`sys.exit` 由调用方 main.py 做。这一点与 `hermes_cli/main.py:614` 那句
   注释 "so we never call resolve_profile_env() with a value it must reject + sys.exit on"
   的措辞略有出入（见 §5）。

**关键结构观察**：`-p` **没有注册在 argparse 上**。

`hermes_cli/_parser.py:16 @ 863e313`

```
# `--profile` / `-p` is consumed by ``main._apply_profile_override`` before
# argparse runs (it sets ``HERMES_HOME`` and strips itself from ``sys.argv``),
# so it isn't on the parser. Listed here so all "carry over on relaunch"
# metadata lives in one file.
PRE_ARGPARSE_INHERITED_FLAGS: list[tuple[str, bool]] = [
    ("--profile", True),
    ("-p", True),
]
```

因此**只要 `_apply_profile_override` 决定"不消费"这个 flag，argparse 一定会以
`unrecognized arguments` 报错**——没有兜底。这直接放大了 §4-C1 的后果。

### 2.3 命名校验：一条规则，八处实现（P3 实测）

正则的"权威副本"：

`hermes_cli/profiles.py:37 @ 863e313`

```
_PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
```

**normalize 与 validate 被刻意拆开**，这个拆分本身有故事：

`hermes_cli/profiles.py:306 @ 863e313`

```
def normalize_profile_name(name: str) -> str:
    """Return the canonical profile id used on disk and in CLI ``-p`` argv.

    Named profiles are stored lowercase under ``profiles/<id>/``. The special
    alias ``default`` is matched case-insensitively (``Default`` → ``default``).
    Dashboards and tools may pass title-cased display labels; normalize before
    validation, assignment, and subprocess spawn (see issue #18498).
    """
    if not isinstance(name, str):
        name = str(name)
    stripped = name.strip()
    if not stripped:
        raise ValueError("profile name cannot be empty")
    if stripped.casefold() == "default":
        return "default"
    return stripped.lower()
```

`hermes_cli/profiles.py:324 @ 863e313`

```
def validate_profile_name(name: str) -> None:
    """Raise ``ValueError`` if *name* is not a valid profile identifier.

    Validates the input as-given — strict lowercase match. Callers that accept
    mixed-case or title-cased input from users (dashboard UI, CLI args) should
    call :func:`normalize_profile_name` first. This separation keeps validate
    honest about what the on-disk directory name must look like, while
    ingress-point normalization handles UX flexibility (see #18498).

    Also rejects names in :data:`_RESERVED_NAMES` (``hermes``, ``test``,
    ``tmp``, ``root``, ``sudo``) that would create confusing on-disk
    collisions (a ``hermes`` profile inside ``~/.hermes/``) or get refused
    at alias-creation time anyway. ``default`` is a special pass-through —
    it's a valid alias for the built-in root profile.
    """
    if name == "default":
        return  # special alias for ~/.hermes
    if not _PROFILE_ID_RE.match(name):
        raise ValueError(
            f"Invalid profile name {name!r}. Must match "
            f"[a-z0-9][a-z0-9_-]{{0,63}}"
        )
    if name in _RESERVED_NAMES:
        raise ValueError(
            f"Profile name {name!r} is reserved — it collides with either "
            f"the Hermes installation itself or a common system binary.  "
            f"Pick a different name."
        )
```

设计意图明确写死了：**"validate 只描述磁盘目录名必须长什么样，UX 弹性由入口点的 normalize 负责"**。
问题是——CLI 这个入口点没照做（§4-C1）。

保留名两张表：

`hermes_cli/profiles.py:249 @ 863e313`

```
# Names that cannot be used as profile aliases
_RESERVED_NAMES = frozenset({
    "hermes", "default", "test", "tmp", "root", "sudo",
})

# Hermes subcommands that cannot be used as profile names/aliases
_HERMES_SUBCOMMANDS = frozenset({
    "chat", "model", "gateway", "setup", "whatsapp", "login", "logout",
    "status", "cron", "doctor", "dump", "config", "pairing", "skills", "tools",
    "mcp", "sessions", "insights", "version", "update", "uninstall",
    "profile", "plugins", "honcho", "acp",
})
```

**注意分工**：`validate_profile_name` 只查 `_RESERVED_NAMES`；`_HERMES_SUBCOMMANDS` 只在
`check_alias_collision` 里查（`hermes_cli/profiles.py:403`）。也就是说**可以创建名为 `gateway` 的 profile，
只是不给它建 alias**。这个分工是合理的（profile 名和 shell 命令名是两个命名空间），
但 `_HERMES_SUBCOMMANDS` 这张表已严重过期（§4-D3）。

**P3 实测：同一条规则的全仓副本**

| 位置 | 正则 | 长度上限 | 查保留名 |
|---|---|---|---|
| `hermes_cli/profiles.py:37` | `^[a-z0-9][a-z0-9_-]{0,63}$` | 64 | 是（`_RESERVED_NAMES`） |
| `hermes_cli/main.py:618` | 同上（内联字面量） | 64 | 否 |
| `hermes_cli/gateway.py:1774` | 同上（内联字面量） | 64 | 否 |
| `hermes_cli/gateway.py:1808` | 同上（内联字面量） | 64 | 否 |
| `gateway/platforms/base.py:1274` | `[a-z0-9][a-z0-9_-]{0,63}`（`fullmatch`） | 64 | 否 |
| `hermes_cli/service_manager.py:29` | **`^[a-z0-9][a-z0-9_-]*$`** | **251** | 否 |
| `hermes_cli/webhook.py:164` | `^[a-z0-9][a-z0-9_-]*$` | 无 | （webhook 名，不同域） |
| `hermes_cli/web_server.py:12457` | `^[a-z0-9][a-z0-9_-]*$` | 无 | （webhook 名，不同域） |

前端另有 4 份 TS 副本（`web/src/pages/ProfileBuilderPage.tsx:28`、`web/src/pages/ProfilesPage.tsx:50`、
`apps/desktop/electron/main.ts:620`、`apps/desktop/src/app/profiles/create-profile-dialog.tsx:23`），
其中一份自己承认是抄的：

`web/src/pages/ProfileBuilderPage.tsx:27 @ 863e313`

```
// Profile name rule mirrors the backend (`^[a-z0-9][a-z0-9_-]{0,63}$`).
const PROFILE_NAME_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;
```

最刺眼的是**第二个同名函数**：

`hermes_cli/service_manager.py:25 @ 863e313`

```
# Profile name → service directory mapping. Profile names must be safe
# as filesystem directory names because the s6 backend creates a service
# directory at ``<scandir>/gateway-<profile>/``. We reject anything that
# could traverse paths, span filesystems, or break s6's own naming rules.
_VALID_PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_MAX_PROFILE_LEN = 251  # s6-svscan default name_max
```

`hermes_cli/service_manager.py:33 @ 863e313`

```
def validate_profile_name(name: str) -> None:
    """Raise ValueError if ``name`` is not usable as a profile name.

    Profile names are used as s6 service directory names, so they must
    match a conservative subset of filesystem-safe characters. Reject
    empty strings, uppercase, paths-traversal sequences, and anything
    longer than s6's default ``name_max``.
    """
    if not name:
        raise ValueError("profile name must not be empty")
    if len(name) > _MAX_PROFILE_LEN:
        raise ValueError(
            f"profile name too long ({len(name)} > {_MAX_PROFILE_LEN})"
        )
    if not _VALID_PROFILE_RE.match(name):
        raise ValueError(
            f"profile name must match [a-z0-9][a-z0-9_-]*, got {name!r}"
        )
```

**两个 `validate_profile_name`，同名不同义**：字符集相同（所以不存在"一边放行路径穿越、
另一边拦"的安全洞），但长度上限 64 vs 251、保留名查 vs 不查。散度方向恰好是安全的
（`profiles` 更严，是唯一的写入闸口），**但这是运气不是设计**——没有任何测试或注释锁定
"`service_manager` 的规则必须 ⊇ `profiles` 的规则"这个不变量。

### 2.4 alias 包装脚本：一次 4.5 秒的性能事故

**场景**：用户在 `~/.local/bin` 里同时装了 ffmpeg / node 等大二进制，然后打开桌面端侧边栏。
侧边栏调 `list_profiles()`，转圈几秒后显示"全部智能体 0"。

原因是每个 profile 都要反查"哪个 wrapper 指向我"，而反查会把整个 wrapper 目录读一遍——
16 个 profile × 整目录 = O(N·M)，且把 ffmpeg 整个读进内存。修复留下了这段注释：

`hermes_cli/profiles.py:542 @ 863e313`

```
def find_alias_for_profile(profile_name: str) -> Optional[str]:
    """Return the alias name of the wrapper that activates *profile_name*, or None.

    A wrapper created by :func:`create_wrapper_script` is a file named after the
    alias whose body invokes ``hermes -p <profile>``. When the alias name equals
    the profile name this is trivial, but a custom alias (``hermes profile alias
    <profile> --name <custom>``) produces a differently-named file — so the
    display side cannot assume ``wrapper == profile`` and must reverse-look-up.

    A custom alias (name != profile) is preferred over the profile-named wrapper
    so ``profile list``/``show`` surface the command the user actually typed.
    Results are sorted for deterministic output when several aliases match.

    For listing ALL profiles at once, prefer :func:`build_alias_map` — calling
    this per-profile re-reads every wrapper file N times (O(N*M)); on a wrapper
    dir like ``~/.local/bin`` that also holds large unrelated binaries (ffmpeg
    etc.) that meant multi-second ``list_profiles`` latency and desktop timeouts.
    """
    return build_alias_map().get(normalize_profile_name(profile_name))
```

`hermes_cli/profiles.py:563 @ 863e313`

```
# Cap how much of a wrapper file we read when reverse-looking-up its profile.
# Real wrappers are a few hundred bytes of shell; the needle (``hermes -p X``)
# sits near the top. The wrapper dir (e.g. ``~/.local/bin``) commonly also holds
# large unrelated binaries (ffmpeg, node, …) — reading those whole, N times, was
# the dominant cost in ``list_profiles`` (~4.5s). Reading a small head slice and
# skipping NUL-bearing (binary) content keeps the scan to a single cheap pass.
_WRAPPER_READ_LIMIT = 8192
```

三层削减合起来把 O(N·M·filesize) 压到 O(M·8KB)：
① 单遍扫描建全量反向表；② 只读头部 8 KB；③ 用 `errors="strict"` 的 UTF-8 解码当"是不是二进制"的探测器。

`hermes_cli/profiles.py:588 @ 863e313`

```
    for entry in sorted(wrapper_dir.iterdir()):
        if not entry.is_file():
            continue
        # Only our own wrappers are named with the alias and (on Windows) .bat.
        if is_windows and entry.suffix != ".bat":
            continue
        if not is_windows and entry.suffix:
            continue
        try:
            with open(entry, "r", encoding="utf-8", errors="strict") as f:
                content = f.read(_WRAPPER_READ_LIMIT)
        except (OSError, UnicodeDecodeError):
            # UnicodeDecodeError = a binary on PATH (ffmpeg etc.) — not a wrapper.
            continue
```

**用 `UnicodeDecodeError` 当二进制探测器**是个便宜且鲁棒的技巧：不需要读 magic number、
不需要 `file(1)`，异常本身就是信号。副作用是一个纯 latin-1 的文本脚本也会被误判为二进制而跳过——
在这里无害（那不可能是我们生成的 wrapper）。

wrapper 本体只有一行 shell：

`hermes_cli/profiles.py:469 @ 863e313`

```
    else:
        wrapper_path = wrapper_dir / canon
        try:
            hermes_exe = shutil.which("hermes") or "hermes"
            wrapper_path.write_text(f'#!/bin/sh\nexec {shlex.quote(hermes_exe)} -p {profile} "$@"\n', encoding="utf-8")
            wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            return wrapper_path
        except OSError as e:
            print(f"⚠ Could not create wrapper at {wrapper_path}: {e}")
            return None
```

**注意 `hermes_exe` 被 `shlex.quote` 了，`profile` 没有**。这是 §4-B2。

反查的解析同样是"取第一个空白分隔 token"：

`hermes_cli/profiles.py:602 @ 863e313`

```
        idx = content.find(prefix)
        if idx == -1:
            continue
        rest = content[idx + len(prefix):]
        # Profile id is the first whitespace-delimited token after the flag.
        canon = rest.split(None, 1)[0].strip() if rest.strip() else ""
```

删除侧的"确认这是我们的 wrapper"检查是子串匹配：

`hermes_cli/profiles.py:498 @ 863e313`

```
    for wrapper_path in candidates:
        if wrapper_path.exists():
            try:
                # Verify it's our wrapper before removing
                content = wrapper_path.read_text(encoding="utf-8")
                if "hermes -p" in content:
                    wrapper_path.unlink()
                    return True
            except Exception:
                pass
    return False
```

注意这里 `read_text()` **没有** 8 KB 上限——与 `build_alias_map` 的教训不一致（§4-D5）。

alias 名的路径穿越防护单独有个函数，理由写得很直白：

`hermes_cli/profiles.py:354 @ 863e313`

```
def validate_alias_name(name: str) -> None:
    """Raise ``ValueError`` if *name* is not a safe wrapper-alias identifier.

    The alias is used verbatim as a filename under :func:`_get_wrapper_dir`
    (``~/.local/bin``), so it must be a single safe command name with no path
    separators or traversal segments — otherwise a value like ``../../.bashrc``
    would escape the wrapper directory and clobber arbitrary user files. We
    reuse the profile id regex, which already forbids ``/``, ``.``, and ``..``.
    """
```

这条有测试背书：`tests/hermes_cli/test_profiles.py:472`（`test_create_wrapper_rejects_traversal`）、
`:480`（`test_create_wrapper_rejects_absolute_path`）、`:419`（`test_traversal_alias_rejected_before_path_lookup`）。

### 2.5 `create_profile`：三档克隆 + 两张排除表

三档语义（互斥性在函数第一行就拦）：

`hermes_cli/profiles.py:1034 @ 863e313`

```
    if no_skills and (clone_from is not None or clone_config or clone_all):
        raise ValueError(
            "--no-skills is mutually exclusive with --clone / --clone-from / --clone-all "
            "(cloning explicitly copies skills from the source profile)."
        )
```

- **裸创建**：建 10 个子目录（`_PROFILE_DIRS`，`hermes_cli/profiles.py:40`）+ 播种 `.env`/`SOUL.md`；
- **`--clone`**：另拷 3 个配置文件 + `skills/` 整树 + 2 个记忆文件；
- **`--clone-all`**：`shutil.copytree` 全量 + 两张排除表 + 事后剥离 3 个运行时文件。

排除表的分层是本文件设计最讲究的地方：

`hermes_cli/profiles.py:104 @ 863e313`

```
# Per-profile history artifacts excluded from --clone-all regardless of the
# source profile.  A new profile is a fresh workspace — inheriting the source
# profile's session history, backup archives, or quick-backup snapshots is
# never useful (restoring one inside the clone would resurrect the SOURCE
# profile's state) and can balloon the copy by tens of GB.  Unlike
# ``_CLONE_ALL_DEFAULT_EXCLUDE_ROOT`` this set is NOT gated on the default
# profile: named profiles accumulate the same artifacts.
```

`hermes_cli/profiles.py:80 @ 863e313`

```
# Infrastructure artifacts excluded from --clone-all when the source is the
# default profile (``~/.hermes``).  Named profiles never contain these
# directories at root, so the exclusion is gated to avoid silently dropping
# user data from a named-profile source.
```

**为什么必须分两张表**：`hermes-agent`（仓库 checkout，注释说 ~84 MB 源码 + ~3 GB venv）、
`profiles`（兄弟 profile，递归拷贝会爆炸）这类名字**只有默认 profile 的根目录才会有**。
如果无条件排除，那么一个命名 profile 里用户自己建的 `bin/` 目录就会被静默丢掉。
所以基础设施表要 gate 在"源确实是默认 profile"上；而 `state.db` / `sessions` / `backups`
这类每个 profile 都会长的历史产物，则无条件排除。

gate 的判定与 ignore 回调：

`hermes_cli/profiles.py:166 @ 863e313`

```
    source_resolved = source_dir.resolve()
    is_default_source = source_resolved == _get_default_hermes_home().resolve()

    def _ignore(directory: str, names: List[str]) -> List[str]:
        ignored: list[str] = []
        for entry in names:
            # Universal exclusions at any depth.
            if (
                entry == "__pycache__"
                or entry.endswith((".pyc", ".pyo", ".sock", ".tmp"))
            ):
                ignored.append(entry)
                continue
            try:
                at_root = Path(directory).resolve() == source_resolved
            except (OSError, ValueError):
                # ``resolve()`` can fail on unusual FS layouts (broken
                # symlinks, missing parents).  Fail open — better to
                # over-copy than silently drop user data.
                at_root = False
```

`resolve()` 失败时 **fail open（多拷）而非 fail closed（少拷）**——对"拷贝用户数据"这个动作，
这是对的方向：多拷了浪费磁盘，少拷了丢数据。

`.env` 权限收紧值得单独看：

`hermes_cli/profiles.py:1086 @ 863e313`

```
            for filename in _CLONE_CONFIG_FILES:
                src = source_dir / filename
                if src.exists():
                    dst = profile_dir / filename
                    shutil.copy2(src, dst)
                    # Tighten .env to owner-only after copy. shutil.copy2
                    # preserves source mode bits, but if the source's .env
                    # was loose (host umask 0o022 leaving 0o644), tighten
                    # explicitly so the clone doesn't inherit weak perms.
                    if filename == ".env":
                        try:
                            os.chmod(str(dst), 0o600)
                        except OSError:
                            pass
```

**`copy2` 保权限是把双刃剑**：它保住了 0600，但也会保住 0644。所以克隆是"提升安全基线"的机会点——
显式收紧，而不是继承。

播种空 `.env` 的动机是一次**真实的用户误解**：

`hermes_cli/profiles.py:1117 @ 863e313`

```
    # Seed an empty .env so the profile has its own credentials file from
    # day one. Without it, profile-scoped env writes (dashboard Channels /
    # Keys pages, `hermes -p <name> auth add`) had no file until first
    # write, and the profile silently inherited API keys from the shell
    # environment — users reasonably read that as "the new profile reads
    # the root .env". Skipped when --clone/--clone-all already copied one.
```

因果链：没有文件 → profile 作用域的写没有落点 → 进程仍然读到 shell 里 export 的 key →
用户看到"新 profile 居然有我的 key" → 以为 profile 会继承根 `.env`。**一个空文件就把语义讲清楚了。**

配置版本迁移的时机也是个 UX 决定：

`hermes_cli/profiles.py:1159 @ 863e313`

```
    # Cloned configs can be older than the running Hermes (or predate schema
    # tracking entirely). Migrate config-only clones immediately so
    # desktop/status surfaces don't warn that a just-created profile is
    # v0/outdated. Leave --clone-all snapshots byte-for-byte apart from the
    # explicit runtime/history stripping above.
    if not clone_all:
        _migrate_profile_config_if_outdated(profile_dir)
```

**`--clone-all` 刻意不迁移**——它的语义是"逐字节快照"，迁移会破坏这个承诺。

迁移函数本身展示了**正确的 HERMES_HOME 作用域切换姿势**（与 §2.7 的错误姿势对照）：

`hermes_cli/profiles.py:524 @ 863e313`

```
    try:
        from hermes_constants import reset_hermes_home_override, set_hermes_home_override
        from hermes_cli.config import check_config_version, migrate_config

        token = set_hermes_home_override(str(profile_dir))
        try:
            current_ver, latest_ver = check_config_version()
            if current_ver < latest_ver:
                migrate_config(interactive=False, quiet=True)
        finally:
            reset_hermes_home_override(token)
    except Exception:
```

`set_hermes_home_override` 是 contextvar（不是环境变量）：

`hermes_constants.py:30 @ 863e313`

```
def set_hermes_home_override(path: str | Path | None) -> Token:
    """Set a context-local Hermes home override and return its reset token.

    This is for in-process, per-task scoping.  It deliberately does not mutate
    ``os.environ`` because that is shared by every thread in the process.
    """
```

### 2.6 skill 计数：签名缓存

`hermes_cli/profiles.py:736 @ 863e313`

```
# In-process cache for skill counts. Walking ``skills_dir.rglob("SKILL.md")``
# recurses the entire skill tree (each skill carries references/scripts/assets
# sub-trees); the default profile alone has ~270 skills, and ``list_profiles``
# calls this for EVERY profile (16+), so an uncached scan costs ~6s — long
# enough that the desktop's per-request backend calls time out and the sidebar
# renders "全部智能体 0". We cache the count keyed by the skills dir, invalidated
# when the dir tree's signature (skills_dir + immediate category dirs mtimes)
# changes (catches skill add/remove) or after a short TTL (catches deep edits).
_SKILL_COUNT_CACHE: dict[str, tuple[float, float, int]] = {}
_SKILL_COUNT_TTL_SECONDS = 30.0
```

（注释里那句中文 "全部智能体 0" 是作者从桌面端截图里抄的 UI 文案，说明这个 bug 是从
中文用户报的 issue 追下来的。）

失效策略是**签名 + TTL 双保险**：

`hermes_cli/profiles.py:748 @ 863e313`

```
def _skills_dir_signature(skills_dir: Path) -> float:
    """Cheap change-signature for a skills tree.

    Max mtime of ``skills_dir`` and its immediate children (category dirs).
    Adding/removing a category bumps ``skills_dir``'s mtime; adding/removing a
    skill inside a category bumps that category dir's mtime. One ``scandir``
    (not a recursive walk) keeps this O(#categories), not O(#files).
    """
```

签名抓"增删"（目录 mtime 会变），TTL 抓"深层编辑"（改 SKILL.md 内容不改父目录 mtime）。
一次 `scandir` 换掉一次 `rglob`。

### 2.7 `delete_profile`：为什么要去进程表里猎杀

**场景**：用户在桌面端开着 profile `coder` 的会话，然后在另一个终端敲
`hermes profile delete coder --yes`。`rmtree` 走到一半，桌面后端还在往
`sessions/`、`state.db-wal`、`sandboxes/` 写文件，最后的 `rmdir` 撞 `ENOTEMPTY`——
删除失败，甚至（修复前）整棵树被"复活"。

`gateway.pid` 帮不上忙，它只记录消息网关：

`hermes_cli/profiles.py:1288 @ 863e313`

```
def _profile_bound_backend_pids(canon: str, profile_dir: Path) -> list[int]:
    """PIDs of running Hermes *backends* bound to this profile.

    The ``gateway.pid`` file only tracks the messaging gateway.  A Desktop app
    spawns a headless ``serve`` (or legacy ``dashboard --no-open``) backend per
    profile that holds the profile's SQLite connection open and keeps writing
    sessions/WAL/sandbox files — the writer that makes ``rmtree`` hit
    ``ENOTEMPTY`` (and, pre-fix, resurrected the tree).  ``gateway.pid`` never
    names it, so find it by inspection: a Hermes backend subcommand
    (``serve``/``dashboard``/``gateway``) that is bound to *this* profile either
    by a ``--profile <canon>`` / ``-p <canon>`` selector or by a ``HERMES_HOME``
    that resolves to ``profile_dir``.

    Best-effort and tightly scoped: current-user processes only, backend
    subcommands only (never an interactive ``chat``/``tui``), and never this
    process or its ancestors.  Returns an empty list if ``psutil`` can't
    inspect anything.
    """
```

四层收窄（每一层都是防止误杀）：

`hermes_cli/profiles.py:1316 @ 863e313`

```
    # Never terminate ourselves or a parent (e.g. `hermes -p <canon> profile
    # delete` runs under the very profile it's deleting).
    skip: set[int] = {os.getpid()}
```

`hermes_cli/profiles.py:1361 @ 863e313`

```
            # Restrict to backend subcommands so we never kill an interactive
            # session the user is deliberately running.
            tokens = {tok.lower() for tok in argv}
            if not (tokens & backend_tokens):
                continue
```

① 排除自己和全部祖先（因为删除命令自己很可能就跑在被删的 profile 里）；
② 只看同用户进程；③ argv 必须含 hermes 标记；④ argv 必须含 `serve`/`dashboard`/`gateway`
之一——绝不碰交互式 `chat`/`tui`。

绑定判定双通道：argv 里的 `-p` 选择器，或 `proc.environ()` 里的 `HERMES_HOME`。

`hermes_cli/profiles.py:1379 @ 863e313`

```
            # ...or by HERMES_HOME env pointing at this profile dir.
            if not bound:
                try:
                    env_home = (proc.environ() or {}).get("HERMES_HOME", "")
                    if env_home and Path(env_home).resolve() == resolved_dir:
                        bound = True
                except Exception:
                    # environ() can raise AccessDenied even same-user on some
                    # platforms; fall back to the argv signal only.
                    pass
```

杀完还要等，然后重试删除：

`hermes_cli/profiles.py:1441 @ 863e313`

```
def _rmtree_with_retry(profile_dir: Path, onexc_handler) -> None:
    """``shutil.rmtree`` with a short retry loop for transient races.

    Even after stopping the gateway and profile backends, a just-terminated
    process can leave in-flight writes (SQLite ``-wal``/``-shm`` checkpoints,
    sandbox temp files) that land after ``rmtree`` has walked past a directory,
    surfacing as ``ENOTEMPTY`` (POSIX) or a transient ``PermissionError``
    (Windows file lock still releasing).  A few spaced retries let those settle
    instead of failing the whole delete on a race the next attempt would win.
    """
    attempts = 3
    last_exc: OSError | None = None
    for attempt in range(attempts):
        try:
            # ``onexc`` was added in 3.12; fall back to ``onerror`` on 3.11.
            try:
                shutil.rmtree(profile_dir, onexc=onexc_handler)
            except TypeError:
                shutil.rmtree(profile_dir, onerror=onexc_handler)
            return
```

**`TypeError` 用作 Python 版本探测**：3.12 加了 `onexc`，3.11 只有 `onerror`。
不查 `sys.version_info`，直接试——参数名不对就是 `TypeError`。同样的双签名兼容在回调侧也做了一次：

`hermes_cli/profiles.py:1577 @ 863e313`

```
            # Normalise the two callback signatures:
            #   onexc(func, path, exc_instance)   — 3.12+
            #   onerror(func, path, exc_info_tuple) — 3.11
            if isinstance(exc, tuple):
                exc = exc[1]  # exc_info → actual exception object
```

回调本身处理 NixOS 只读拷贝：

`hermes_cli/profiles.py:1563 @ 863e313`

```
        def _make_writable(func, path, exc):
            """onexc/onerror handler: add +w on PermissionError so rmtree can proceed.

            Handles two cases on NixOS (and other systems with read-only
            copies from immutable stores):
            1. The path itself isn't writable (e.g. a file with mode 0444)
            2. The *parent* directory isn't writable (e.g. mode 0555)
```

删除全流程的顺序也是有讲究的（先禁服务，再停进程，最后删目录）：

`hermes_cli/profiles.py:1537 @ 863e313`

```
    # 1. Disable service (prevents auto-restart)
    _cleanup_gateway_service(canon, profile_dir)
```

**先禁 systemd/launchd 服务再杀进程**，否则 `Restart=on-failure` 会立刻把网关拉起来，
刚删掉的目录又被重建。

**`_cleanup_gateway_service` 是本模块唯一直接改环境变量的地方**：

`hermes_cli/profiles.py:1709 @ 863e313`

```
def _cleanup_gateway_service(name: str, profile_dir: Path) -> None:
    """Disable and remove systemd/launchd service for a profile."""
    import platform as _platform

    # Derive service name for this profile
    # Temporarily set HERMES_HOME so _profile_suffix resolves correctly
    old_home = os.environ.get("HERMES_HOME")
    try:
        os.environ["HERMES_HOME"] = str(profile_dir)
        from hermes_cli.gateway import get_service_name, get_launchd_plist_path
```

`hermes_cli/profiles.py:1750 @ 863e313`

```
    finally:
        if old_home is not None:
            os.environ["HERMES_HOME"] = old_home
        elif "HERMES_HOME" in os.environ:
            del os.environ["HERMES_HOME"]
```

**恢复逻辑本身是对的**（区分了"原来没有"和"原来有"），但选错了原语——见 §4-A1。
对照组就在同文件里：`_check_gateway_running` 的 docstring 特意声明自己**不**这么干：

`hermes_cli/profiles.py:714 @ 863e313`

```
    agree.  Parameterized by ``profile_dir`` so it never mutates ``HERMES_HOME``.
    """
```

### 2.8 两个"当前 profile"

模块里有三个名字相近、语义不同的函数，读的人极易混：

| 函数 | 数据源 | 返回值域 | 行号 |
|---|---|---|---|
| `get_active_profile()` | 粘性文件 `<root>/active_profile` | 文件里的**原始字符串**，或 `"default"` | `hermes_cli/profiles.py:1800` |
| `set_active_profile(name)` | 写该文件 | — | `hermes_cli/profiles.py:1815` |
| `get_active_profile_name()` | **当前 `HERMES_HOME`** 反推 | `"default"` / profile 名 / `"custom"` | `hermes_cli/profiles.py:1840` |

`hermes_cli/profiles.py:1800 @ 863e313`

```
def get_active_profile() -> str:
    """Read the sticky active profile name.

    Returns ``"default"`` if no active_profile file exists or it's empty.
    """
    path = _get_active_profile_path()
    try:
        name = path.read_text(encoding="utf-8").strip()
        if not name:
            return "default"
        return name
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        return "default"
```

**读侧不做 normalize/validate**——手工编辑过的 `active_profile` 内容原样返回。
写侧则严格：

`hermes_cli/profiles.py:1815 @ 863e313`

```
def set_active_profile(name: str) -> None:
    """Set the sticky active profile.

    Writes to ``~/.hermes/active_profile``. Use ``"default"`` to clear.
    """
    canon = normalize_profile_name(name)
    validate_profile_name(canon)
    if canon != "default" and not profile_exists(canon):
        raise FileNotFoundError(
            f"Profile '{canon}' does not exist. "
            f"Create it with: hermes profile create {canon}"
        )

    path = _get_active_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if canon == "default":
        # Remove the file to indicate default
        path.unlink(missing_ok=True)
    else:
        # Atomic write
        tmp = path.with_suffix(".tmp")
        tmp.write_text(canon + "\n", encoding="utf-8")
        tmp.replace(path)
```

**"default 用删除文件表示"** 而不是写 `"default"` 字符串——省掉了"文件存在但内容为 default"
这个中间态。缺点是无法区分"从未设置"和"显式设回默认"，这里无所谓。

`hermes_cli/profiles.py:1840 @ 863e313`

```
def get_active_profile_name() -> str:
    """Infer the current profile name from HERMES_HOME.

    Returns ``"default"`` if HERMES_HOME is not set or points to ``~/.hermes``.
    Returns the profile name if HERMES_HOME points into ``~/.hermes/profiles/<name>``.
    Returns ``"custom"`` if HERMES_HOME is set to an unrecognized path.
    """
```

写侧 canon 化、读侧不 canon 化，在 `delete_profile` 收尾时形成一个小坑（§4-D4）：

`hermes_cli/profiles.py:1606 @ 863e313`

```
    # 5. Clear active_profile if it pointed to this profile
    try:
        active = get_active_profile()
        if active == canon:
            set_active_profile("default")
            print("✓ Active profile reset to default")
    except Exception:
        pass
```

### 2.9 `profiles_to_serve`：网关多路复用的唯一枚举口

`hermes_cli/profiles.py:957 @ 863e313`

```
def profiles_to_serve(multiplex: bool) -> List[Tuple[str, Path]]:
    """Return the ``(profile_name, hermes_home)`` pairs a gateway should serve.

    This is the single chokepoint for "which profiles does the inbound gateway
    handle" so later multiplexing phases never re-derive the set.

    - ``multiplex=False`` (default): returns exactly one entry for the *active*
      profile — byte-for-byte the single-profile behavior the gateway has
      always had. The name is ``"default"`` for the default profile or the
      active named profile's id.
    - ``multiplex=True``: returns the default profile plus every valid named
      profile under ``profiles/``, each paired with its own HERMES_HOME.
```

`hermes_cli/profiles.py:970 @ 863e313`

```
    Intentionally lightweight (a directory scan + name validation only): no
    per-profile config reads, gateway-running probes, or skill counts like
    :func:`list_profiles`. It runs on gateway startup and must stay cheap.

    The returned ``hermes_home`` is the path to pass to
    ``set_hermes_home_override`` when scoping a turn to that profile.
```

**"single chokepoint" 这个设计声明有实据**：全仓 5 个消费点全部走它，无一处自己重推
`profiles/` 目录列表——`gateway/run.py:13225`、`gateway/run.py:26893`、
`gateway/platforms/webhook.py:555`、`gateway/platforms/api_server.py:1924`、
`hermes_cli/web_server.py:2903`。

它与 `list_profiles()` 是刻意的"重/轻"双胞胎：`list_profiles` 每个 profile 要读 config.yaml、
探网关 PID、数 skill、读 distribution.yaml、读 profile.yaml（`hermes_cli/profiles.py:927`–`951`）；
`profiles_to_serve` 只做 `iterdir` + 正则。**因为一个跑在人眼前（面板），一个跑在网关启动路径上。**

### 2.10 导出/导入：白名单代替黑名单

导出侧最有价值的一段是"为什么改用白名单"：

`hermes_cli/profiles.py:227 @ 863e313`

```
# Allow-list for ``export_profile("default")``: when HERMES_HOME equals the
# cwd (Docker/custom deployments), the default profile home is the working
# directory and contains arbitrary user files that should NOT be bundled
# into the export. The set below identifies the *known Hermes profile
# artifacts* at the root of HERMES_HOME; everything else is excluded.
# Sensitive runtime infrastructure (``state.db``, ``logs/``, ``auth.*``,
# other profiles) is intentionally *not* in this list so the export stays
# a portable, credential-free snapshot of the user-facing surface
# (#58394). Add new artifacts here when introduced in ``hermes_constants``.
```

`hermes_cli/profiles.py:1871 @ 863e313`

```
def _default_export_ignore(root_dir: Path):
    """Return an *ignore* callable for :func:`shutil.copytree`.

    Two-tier filtering:

    * **Root-level allow-list** — only entries whose name appears in
      ``_DEFAULT_EXPORT_INCLUDE_ROOT`` survive. Everything else (such as
      an unrelated ``x11-dev/`` directory in a Docker deployment where
      HERMES_HOME equals the cwd) is excluded. Blacklisting was tried
      first and proved unable to anticipate every non-Hermes file the
      user may have lying alongside HERMES_HOME (#58394).
```

**事故经过**：Docker 部署里 `HERMES_HOME` 就是工作目录，用户的 `x11-dev/` 之类东西和
profile 产物混在同一层。原来的黑名单只能列举已知要排除的东西，列不全用户可能放的任意文件——
于是导出的归档里带上了不该带的内容。改成白名单后，语义从"排除我知道的坏东西"变成
"只带我认识的好东西"，未知项默认落在安全侧。**代价写在注释末尾：新增产物必须记得往这张表里加。**

归档格式的选择也是踩出来的：

`hermes_cli/profiles.py:1908 @ 863e313`

```
def _make_profile_archive(base: str, root_dir: str, base_dir: str) -> str:
    """Create ``<base>.tar.gz`` of ``root_dir/base_dir`` — GNU tar format.

    Not :func:`shutil.make_archive`: that writes PAX (Python's tarfile default
    since 3.8), whose fractional-mtime records macOS Archive Utility rejects —
    double-clicking an exported profile threw "Error 94 - Bad message." GNU
    format keeps long paths working (longlink extensions) and stays integer-
    mtime, so Finder, bsdtar, and gnutar all extract it.
    """
```

因果链：Python 3.8 起 `tarfile` 默认 PAX → PAX 记录小数秒 mtime → macOS Archive Utility
不认小数秒 → 用户双击导出的 profile 得到 "Error 94 - Bad message"。选 GNU_FORMAT 既避开小数秒，
又保住长路径（longlink 扩展）。

命名 profile 的导出是硬编码剔除凭据：

`hermes_cli/profiles.py:1968 @ 863e313`

```
    # Named profiles — stage a filtered copy to exclude credentials
    with tempfile.TemporaryDirectory() as tmpdir:
        staged = Path(tmpdir) / canon
        _CREDENTIAL_FILES = {"auth.json", ".env"}
        shutil.copytree(
            profile_dir,
            staged,
            symlinks=True,
            ignore=lambda d, contents: _CREDENTIAL_FILES & set(contents),
        )
```

**注意这个 lambda 不区分层级**——任何深度下名为 `auth.json` / `.env` 的都被剔除。
对凭据来说 over-exclude 是正确方向。

导入侧是完整的"安全解包"三件套：

`hermes_cli/profiles.py:1983 @ 863e313`

```
def _normalize_profile_archive_parts(member_name: str) -> List[str]:
    """Return safe path parts for a profile archive member."""
    normalized_name = member_name.replace("\\", "/")
    posix_path = PurePosixPath(normalized_name)
    windows_path = PureWindowsPath(member_name)

    if (
        not normalized_name
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
    ):
        raise ValueError(f"Unsafe archive member path: {member_name}")

    parts = [part for part in posix_path.parts if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"Unsafe archive member path: {member_name}")
    return parts
```

**同时按 POSIX 和 Windows 两套语义判绝对路径**（`C:` 盘符在 POSIX 下不是绝对路径，
但在 Windows 上解包就会跑到别的盘），这是跨平台解包容易漏的一点。

`hermes_cli/profiles.py:2016 @ 863e313`

```
            if not member.isfile():
                raise ValueError(
                    f"Unsupported archive member type: {member.name}"
                )
```

**只允许目录和普通文件**——符号链接、硬链接、设备文件一律拒绝（tar 符号链接是经典的
解包逃逸载体）。而且是 `raise` 不是 `skip`：宁可整个导入失败，也不静默丢内容。

`hermes_cli/profiles.py:2103 @ 863e313`

```
    with tempfile.TemporaryDirectory(prefix="hermes_profile_import_") as tmpdir:
        staging_root = Path(tmpdir)
        _safe_extract_profile_archive(archive, staging_root)

        extracted = staging_root / archive_root
        if not extracted.is_dir():
            raise ValueError(
                f"Profile archive root is missing or invalid: {archive_root}"
            )

        final_source = extracted
        if archive_root != canon:
            final_source = staging_root / canon
            extracted.rename(final_source)

        shutil.move(str(final_source), str(profile_dir))
```

**先在临时目录里落地并改名，最后一次 `move` 就位**——不是"先建目标目录再往里解"。
这样解包失败不会留下半成品 profile。（`shutil.move` 跨文件系统时会退化成 copy+rm，
不是原子的；但至少目标目录要么整体出现要么不出现。）

### 2.11 rename：目录之外还有三样东西要跟着改

`hermes_cli/profiles.py:2210 @ 863e313`

```
    # 1. Stop gateway if running
    if _check_gateway_running(old_dir):
        _cleanup_gateway_service(old_canon, old_dir)
        _stop_gateway_process(old_dir)

    # 2. Rename directory
    old_dir.rename(new_dir)
    print(f"✓ Renamed {old_dir.name} → {new_dir.name}")

    # 3. Update profile-scoped Honcho host blocks, preserving aiPeer identity
    _migrate_honcho_profile_host(old_canon, new_canon, new_dir)

    # 4. Update wrapper script
    remove_wrapper_script(old_canon)
    collision = check_alias_collision(new_canon)
    if not collision:
        create_wrapper_script(new_canon)
        print(f"✓ Alias updated: {new_canon}")
    else:
        print(f"⚠ Cannot create alias '{new_canon}' — {collision}")
```

Honcho 迁移那一步值得单看，因为它揭示了"profile 名泄漏到外部系统"的耦合：

`hermes_cli/profiles.py:2127 @ 863e313`

```
def _migrate_honcho_profile_host(old_name: str, new_name: str, new_dir: Path) -> None:
    """Rename Honcho host blocks for a renamed profile without changing peers."""
    old_host = f"hermes_{old_name}"
    legacy_old_host = f"hermes.{old_name}"
    new_host = f"hermes_{new_name}"
```

profile 名被拼进外部记忆服务（Honcho）的 host key。改名时必须同步改 host key，
但**不能改 `aiPeer`**——那是记忆归属的身份，改了等于换了个 agent。所以还要给旧格式补一个显式 `aiPeer`：

`hermes_cli/profiles.py:2165 @ 863e313`

```
        block = hosts[source_host]
        if isinstance(block, dict) and "aiPeer" not in block:
            if source_host.startswith("hermes_"):
                bare = source_host.split("_", 1)[1]
            else:
                bare = source_host.split(".", 1)[1] if "." in source_host else source_host
            block["aiPeer"] = bare
        hosts[new_host] = hosts.pop(source_host)
```

**教训（可迁移）**：一旦把"实例标识"拼进外部系统的 key，改名就不再是本地操作。
更稳的做法是给 profile 一个不可变 UUID，把可变的名字只当显示标签。

### 2.12 副作用总账（P2 实测）

委托方给的前提是"profiles.py 只算路径，不改全局状态"。逐项实测：

| 副作用类别 | 实际发生 | 锚点 |
|---|---|---|
| 建目录 | `profile_dir.mkdir` + 10 个子目录 | `hermes_cli/profiles.py:1080` |
| 写文件 | `.env` / `SOUL.md` / `.no-bundled-skills` / `profile.yaml` / `active_profile` / wrapper 脚本 | `hermes_cli/profiles.py:1126`、`1142`、`1150`、`878`、`1836`、`473` |
| 改权限 | `os.chmod(..., 0o600)` ×3；wrapper 加执行位 | `hermes_cli/profiles.py:1097`、`1132`、`1279`、`474` |
| 删文件/树 | `shutil.rmtree` 整棵 profile；`unlink` wrapper / 运行时文件 | `hermes_cli/profiles.py:1600`、`504`、`1077` |
| **改 `os.environ`** | `os.environ["HERMES_HOME"] = ...` + `del` | `hermes_cli/profiles.py:1717`、`1752`、`1754` |
| 起子进程 | `subprocess.run(["which"/"where", ...])`、`systemctl`、`launchctl`、`sys.executable -c` | `hermes_cli/profiles.py:410`、`1724`、`1742`、`1211` |
| **杀进程** | `terminate_pid()` 优雅 + `force=True` 强杀 | `hermes_cli/profiles.py:1420`、`1434`、`1776`、`1786` |
| 打印 stdout | 30+ 处 `print()`（含 `input()` 交互确认） | `hermes_cli/profiles.py:1498`、`1529` |
| 进程内缓存 | `_SKILL_COUNT_CACHE` 模块级 dict | `hermes_cli/profiles.py:744` |
| 注册/注销系统服务 | s6 `register_profile_gateway` / `unregister_profile_gateway` | `hermes_cli/profiles.py:1672`、`1704` |

`hermes_cli/profiles.py:1211 @ 863e313`

```
        result = subprocess.run(
            [sys.executable, "-c",
             "import json; from tools.skills_sync import sync_skills; "
             "r = sync_skills(quiet=True); print(json.dumps(r))"],
            env={**os.environ, "HERMES_HOME": str(profile_dir)},
            cwd=str(project_root),
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60,
        )
```

这段是"为什么必须起子进程"的活证据：

`hermes_cli/profiles.py:1191 @ 863e313`

```
def seed_profile_skills(profile_dir: Path, quiet: bool = False) -> Optional[dict]:
    """Seed bundled skills into a profile via subprocess.

    Uses subprocess because sync_skills() caches HERMES_HOME at module level.
    Returns the sync result dict, or None on failure.
```

**`HERMES_HOME` 在模块级被缓存 → 进程内没法改 → 只能开新进程。**
这是"环境变量式全局配置"这条路线最直接的账单：本来一次函数调用的事，
变成 60 秒超时 + JSON 序列化跨进程往返。

**结论**：P2 为假。`profiles.py` 是一个**重副作用的 CRUD + 运维模块**，
只有末尾 17 行的 `resolve_profile_env()` 符合"只算路径"的描述。
把它当"纯路径解析器"来读会严重低估风险面。

---

## 3. subcommands/ 的共同契约与偏离清单

### 3.1 共同契约（六条）

包的自我说明写得很清楚，它是"上帝文件拆解 Phase 2"的产物：

`hermes_cli/subcommands/__init__.py:1 @ 863e313`

```
"""CLI subcommand parser builders for ``hermes <subcommand>``.

``hermes_cli/main.py:main()`` historically built the entire argparse tree
inline — 179 ``add_parser`` calls across ~26 subcommand groups, all wedged
into one 3,300-line function. This package breaks that tree apart: each
subcommand group owns a ``build_<group>_parser(subparsers, ...)`` function in
its own module, and ``main()`` calls those builders instead of inlining the
argument definitions.

Handlers (the ``cmd_*`` functions) still live in ``main.py`` for now and are
dependency-injected into the builders so these modules never import ``main``
(which would create a cycle). Shared parser helpers live in
``_shared.py``.

Part of the god-file decomposition plan (Phase 2).
"""

from __future__ import annotations
```

**契约六条**（我从 41 个 builder 归纳，逐条给了反例检验）：

**C-1 · 导出一个 `build_<group>_parser` 函数。** 42 个非 `__init__` 模块里，
40 个恰好导出一个同名 builder，`gateway.py` / `dashboard.py` 各多一个私有 helper，
`_shared.py` 不导出 builder。

**C-2 · 签名固定为 `(subparsers, *, cmd_<x>: Callable) -> None`。** `subparsers` 位置传入，
handler **只能关键字传**，返回 `None`（parser 对象不回传）。示例：

`hermes_cli/subcommands/version.py:12 @ 863e313`

```
def build_version_parser(subparsers, *, cmd_version: Callable) -> None:
    """Attach the ``version`` subcommand to ``subparsers``."""
    # =========================================================================
    # version command
    # =========================================================================
    version_parser = subparsers.add_parser("version", help="Show version information")
    version_parser.set_defaults(func=cmd_version)
```

**"返回 None"是有代价的取舍**：main.py 拿不到 parser 对象，所以任何"建完再补一刀"的需求
（例如给某个子命令追加 flag）都必须回到模块里改。好处是调用点整齐划一、不可能出现
"main.py 又往里塞了两个参数"的散装状态。

**C-3 · 严禁 `import hermes_cli.main`。** 这是整个拆解能成立的前提——handler 住在 main.py，
builder 若反向 import 就成环。实测：42 个模块里只有 4 个有 `from hermes_cli...` 导入
（`hermes_cli/subcommands/acp.py:11`、`hermes_cli/subcommands/cron.py:12`、`hermes_cli/subcommands/gateway.py:14`、`hermes_cli/subcommands/mcp.py:12`），且全部只导 `._shared`。
**零个模块 import main。契约 100% 守住。**

**C-4 · 用 `set_defaults(func=...)` 把 handler 绑在 parser 上。** 这是 argparse 的标准
"命令模式"落法：解析完 `args.func` 就是要调的函数。

**C-5 · 子动作用 `add_subparsers(dest=...)` 挂二级 parser，dest 命名带命令名前缀。**
避免与顶层的 `dest="command"` 撞车。`mcp.py` 里有一段注释把这个坑讲透了：

`hermes_cli/subcommands/mcp.py:46 @ 863e313`

```
    # dest="mcp_command" so this flag does not clobber the top-level
    # subparser's args.command attribute, which the dispatcher reads to
    # route to cmd_mcp.  Without an explicit dest, argparse derives
    # dest="command" from the flag name and sets it to None when the
    # flag is omitted, causing `hermes mcp add ...` to fall through to
    # interactive chat.
    mcp_add_p.add_argument(
        "--command", dest="mcp_command", help="Stdio command (e.g. npx)"
    )
```

**因果**：`--command` 不显式给 dest → argparse 推出 `dest="command"` → 覆盖顶层子命令名 →
`args.command` 变 `None` → 分发器认为"用户没给子命令" → `hermes mcp add ...` 掉进交互式聊天。
一个 flag 名字撞了框架的推导规则，把整条命令路由废掉。

**C-6 · 跨模块共享的 flag 走 `_shared.py`。** 目前只有一个：

`hermes_cli/subcommands/_shared.py:15 @ 863e313`

```
def add_accept_hooks_flag(parser: argparse.ArgumentParser) -> None:
    """Attach the ``--accept-hooks`` flag.

    Shared across every agent subparser so the flag works regardless of CLI
    position.
    """
    parser.add_argument(
        "--accept-hooks",
        action="store_true",
        default=argparse.SUPPRESS,
        help=(
            "Auto-approve unseen shell hooks without a TTY prompt "
            "(equivalent to HERMES_ACCEPT_HOOKS=1 / hooks_auto_accept: true)."
        ),
    )
```

**`default=argparse.SUPPRESS` 是这里的关键**：它让"没传 flag"时 namespace 里**根本不出现**
`accept_hooks` 属性，而不是出现 `False`。因为同一个 flag 被挂在父 parser 和多个子 parser 上
（`cron.py` 挂了 3 次：`cron_run`、`cron_tick`、`cron_parser`），若默认值是 `False`，
子 parser 的默认 `False` 会**覆盖**父 parser 上用户真正传入的 `True`。用 SUPPRESS 就没有覆盖源。

`hermes_cli/subcommands/cron.py:192 @ 863e313`

```
    cron_tick = cron_subparsers.add_parser("tick", help="Run due jobs once and exit")
    add_accept_hooks_flag(cron_tick)
    add_accept_hooks_flag(cron_parser)
    cron_parser.set_defaults(func=cmd_cron)
```

`_shared.py` 存在的理由（消除 import 环）在它自己的头部：

`hermes_cli/subcommands/_shared.py:1 @ 863e313`

```
"""Shared parser helpers used across multiple CLI subcommand builders.

These were module-level helpers in ``hermes_cli/main.py``. They are pulled
into a neutral module so both ``main.py`` and every
``hermes_cli/subcommands/<group>.py`` builder can import them without an
import cycle. ``main.py`` re-exports them for backwards compatibility, so
existing references keep working.
"""
```

### 3.2 注册与分发的完整链路（**没有任何自动发现**）

**这是 P1 里最该被点破的一点：`subcommands/__init__.py` 没有任何注册表、
没有 `__all__`、没有 `pkgutil.iter_modules` 扫描。整个 18 行文件除了 docstring 就一句
`from __future__ import annotations`（见 §3.1 引用）。**

注册全靠 main.py 里两段手写清单。第一段是 44 行 import：

`hermes_cli/main.py:440 @ 863e313`

```
from hermes_cli.subcommands._shared import add_accept_hooks_flag as _add_accept_hooks_flag
from hermes_cli.subcommands.cron import build_cron_parser
from hermes_cli.subcommands.sync import build_sync_parser
from hermes_cli.subcommands.gateway import build_gateway_parser
from hermes_cli.subcommands.profile import build_profile_parser
from hermes_cli.subcommands.model import build_model_parser
from hermes_cli.subcommands.setup import build_setup_parser
```

第二段是散布在 `main()` 里的 44 处调用（`hermes_cli/main.py:11239` 到 `hermes_cli/main.py:12455`），
每处上面还配一条注释指回模块：

`hermes_cli/main.py:11484 @ 863e313`

```
    # cron command  (parser built in hermes_cli/subcommands/cron.py)
    # =========================================================================
    build_cron_parser(subparsers, cmd_cron=cmd_cron)
    build_sync_parser(subparsers, cmd_sync=cmd_sync)
```

分发终点只有一处：

`hermes_cli/main.py:12585 @ 863e313`

```
    # Execute the command.  Propagate the handler's return code as the
    # process exit code so subcommands that signal failure (e.g.
    # ``hermes egress start`` refusing when credential_source=bitwarden
    # is misconfigured) actually exit non-zero.  Handlers that return
    # None are treated as success (exit 0).
    if hasattr(args, "func"):
        rc = args.func(args)
        if isinstance(rc, int) and rc != 0:
            sys.exit(rc)
    else:
        parser.print_help()
```

**handler 返回 int 才当退出码，返回 None 当成功**——这让 40 多个既有 handler 不用改签名就能接入。

还有一张与 argparse 树**并行维护的名单**，用于跳过昂贵的插件发现：

`hermes_cli/main.py:10595 @ 863e313`

```
# Top-level subcommands that argparse knows about WITHOUT running plugin
# discovery.  Used to short-circuit eager plugin imports (which can take
# 500ms+ pulling in google.cloud.pubsub_v1, aiohttp, grpc, etc.) when the
# user's invocation clearly doesn't need any plugin-registered subcommand.
#
# Keep this in sync with the ``subparsers.add_parser("NAME", ...)`` calls
# below in ``main()``. Missing an entry here only costs a one-time
# discovery; extra entries here would let a plugin command silently fail
# to parse.
_BUILTIN_SUBCOMMANDS = frozenset(
```

**"漏一个只是白跑一次发现，多一个会让插件命令静默解析失败"**——这句注释把失效不对称性讲清楚了，
是很好的工程写法。但它意味着**又一张必须手工同步的清单**（§4-D3）。

**这套"手写注册"的取舍**：
- 好处：① 顺序可控（argparse 的 `--help` 按注册顺序列，自动发现就得另外排序）；
  ② 无 import 副作用，不会因为放了个文件进目录就多出一条命令；
  ③ 静态可读——`grep build_.*_parser main.py` 就是全量命令表；
  ④ 与"handler 仍住在 main.py"的现状兼容（自动发现拿不到 handler）。
- 代价：新增一个子命令要改 3 个地方（新建模块、加 import、加调用），
  再加 `_BUILTIN_SUBCOMMANDS` 就是 4 个。漏加 import 是 `NameError`（会炸，安全）；
  漏加调用是"命令静默消失"（不炸，危险）。

### 3.3 偏离清单（P1 实测结果）

**41 个 builder 的签名 100% 同形**（`build_X(subparsers, *, cmd_Y: Callable) -> None`，
其中 `gateway`/`dashboard` 多几个 `cmd_*`）。偏离都发生在**语义层**，共 9 类：

| # | 模块 | 偏离内容 | 是否有正当理由 |
|---|---|---|---|
| V1 | `__init__.py` | 不导出任何东西，不是注册表 | ✔ 有（见 §3.2 取舍） |
| V2 | `_shared.py` | 不是 builder，是 flag helper | ✔ 有（消除 import 环） |
| V3 | `gateway.py` | 3 个 handler、注册 **2 个顶层命令**（`gateway` + `proxy`） | ✔ 有（原本就是一个内联块） |
| V4 | `dashboard.py` | 2 个 handler、注册 **2 个顶层命令**（`dashboard` + `serve`）、`set_defaults` 传非 func 值 | ✔ 有（共用同一个 `start_server`） |
| V5 | `gui.py` | 模块名 `gui`、builder 名 `build_gui_parser`，但注册的命令叫 **`desktop`**，`gui` 只是 alias | ✔ 有（改名过渡期），但命名已误导 |
| V6 | `login.py` | `add_parser` **不传 `help=`**，刻意从 `--help` 隐藏 | ✔ 有（规避 Py3.12 的 SUPPRESS 泄漏） |
| V7 | `security.py`、`approvals.py` | 父 parser 和唯一子 parser **都** `set_defaults(func=...)` | ✔ 有（裸命令也要能分发），但冗余 |
| V8 | `import_cmd.py` | 模块名 ≠ 命令名 ≠ handler 关键字名（`import_cmd` / `import` / `cmd_import`） | ✔ 有（`import` 是 Python 关键字） |
| V9 | 全体 | `add_subparsers(dest=...)` 命名三分：`_command`(11) / `_action`(11) / `_subcommand`(1) | ✘ 无，纯历史遗留 |

逐条给证据：

**V3 · `gateway.py` 一模块两命令**

`hermes_cli/subcommands/gateway.py:32 @ 863e313`

```
def build_gateway_parser(
    subparsers, *, cmd_gateway: Callable, cmd_proxy: Callable, cmd_gateway_enroll: Callable
) -> None:
    """Attach the ``gateway`` and ``proxy`` subcommands to ``subparsers``."""
```

理由写在模块头：

`hermes_cli/subcommands/gateway.py:1 @ 863e313`

```
"""``hermes gateway`` and ``hermes proxy`` subcommand parsers.

Extracted verbatim from ``hermes_cli/main.py:main()`` (god-file Phase 2).
Both parsers are built together because they shared one inline block (the
``gateway`` section also defined ``proxy``). Handlers injected to avoid
importing ``main``.
"""
```

**"因为原来就在一个内联块里"是提取阶段的诚实做法**——先做等价搬迁，不在搬迁时顺手重构。
但语义上 `proxy` 与 `gateway` 完全无关，注释自己都要澄清方向相反：

`hermes_cli/main.py:11342 @ 863e313`

```
    # NOTE: this is the OUTBOUND egress firewall (ironsh/iron-proxy).
    # `hermes proxy` (defined elsewhere in this file) is a separate INBOUND
    # OAuth-aggregator reverse proxy.  Different direction, different purpose.
```

`gateway.py` 里还有第三种偏离：**嵌套 parser 覆盖父级的 `func`**。

`hermes_cli/subcommands/gateway.py:308 @ 863e313`

```
    gateway_enroll.set_defaults(func=cmd_gateway_enroll)
```

`hermes_cli/subcommands/gateway.py:354 @ 863e313`

```
    proxy_parser.set_defaults(func=cmd_proxy)
    gateway_parser.set_defaults(func=cmd_gateway)
```

argparse 的语义是子 parser 的 `set_defaults` 后写入 namespace，因此
`hermes gateway enroll` 拿到 `cmd_gateway_enroll`，`hermes gateway start` 拿到 `cmd_gateway`。
有测试锁定：`tests/hermes_cli/test_subcommands_profile_gateway.py:66`
（`test_gateway_enroll_dispatch`，断言 `ns.func is _h_gateway_enroll`）。

**V4 · `dashboard.py` 一模块两命令 + 非 func 默认值**

`hermes_cli/subcommands/dashboard.py:87 @ 863e313`

```
def build_dashboard_parser(
    subparsers, *, cmd_dashboard: Callable, cmd_dashboard_register: Callable
) -> None:
```

`hermes_cli/subcommands/dashboard.py:166 @ 863e313`

```
    # `headless_backend` marks the lean path: desktop/remote clients speak pure
    # JSON-RPC/WS, so `serve` skips the web UI build AND never serves the SPA
    # (cmd_dashboard exports HERMES_SERVE_HEADLESS=1). `dashboard` leaves it
    # unset and serves the browser UI as before.
    serve_parser.set_defaults(func=cmd_dashboard, no_open=True, headless_backend=True)
```

**这是全 44 个模块里唯一用 `set_defaults` 传"非 func 配置值"的地方**：
`serve` 和 `dashboard` 共用同一个 handler，靠 namespace 上的两个预置布尔量区分行为。
`no_open` 同时也是一个真实存在的 flag（`hermes_cli/subcommands/dashboard.py:149`），argparse 的
`set_defaults` 会连带把该 Action 的 `.default` 改成 `True`——所以 `hermes serve` 不传
`--no-open` 也是 `True`。这是刻意的"接受但冗余"：

`hermes_cli/subcommands/dashboard.py:146 @ 863e313`

```
    # Accepted but redundant: `serve` is always headless (see set_defaults
    # below). Kept so callers that pass the legacy `--no-open` flag (e.g. the
    # desktop backend spawn) don't trip "unrecognized arguments".
```

`dashboard.py` 里还藏着两段"向后兼容型 argparse"的范例：

`hermes_cli/subcommands/dashboard.py:110 @ 863e313`

```
    # Backward-compat shim: older Hermes desktop app shells (<= 0.15.x) spawn the
    # backend as `hermes dashboard --no-open --tui --host ... --port ...`. The
    # `--tui` flag was removed from this subcommand in cae6b5486 (embedded chat is
    # always on now). When a user's CLI updates past that commit but their desktop
    # app binary has not, argparse used to hard-error with "unrecognized arguments:
    # --tui" and exit(2) — the backend died before becoming ready and the GUI just
    # showed "Hermes couldn't start" with no actionable cause. Accept and silently
    # ignore the flag so an old app + new CLI degrades gracefully instead of
    # bricking. Hidden from --help; safe to delete once the floor app version is
    # well past 0.16.0.
```

**事故经过**：用户升级了 CLI 但没升桌面 app → 老 app 用 `--tui` 拉后端 →
argparse `exit(2)` → 后端还没 ready 就死 → GUI 只显示 "Hermes couldn't start"，
用户完全看不出原因。**修法是"接受并忽略"，代价是一条永远没人用的死 flag**——
注释还贴心地写了删除条件（"floor app version 过了 0.16.0"）。

同类的还有 `gateway.py` 的 `--platform` 兼容 flag：

`hermes_cli/subcommands/gateway.py:17 @ 863e313`

```
def _add_compat_platform_flag(parser: argparse.ArgumentParser) -> None:
    """Accept stale `gateway <verb> --platform X` docs without advertising it.

    Gateway service lifecycle commands operate on the gateway process, not a
    single messaging adapter.  Photon briefly printed a per-platform start
    command during setup; keep that command parseable so users following the
    old hint don't get blocked by argparse before the gateway can start.
    """
    parser.add_argument(
        "--platform",
        dest="platform",
        help=argparse.SUPPRESS,
    )
```

**可迁移原则**：CLI 的 flag 一旦印进过任何文档/提示/第三方脚本，删掉它就是在破坏别人的
自动化。低成本做法是保留为 `help=argparse.SUPPRESS` 的 no-op，让老调用降级而不是硬失败。

**V5 · `gui.py` 模块名与命令名脱节**

`hermes_cli/subcommands/gui.py:12 @ 863e313`

```
def build_gui_parser(subparsers, *, cmd_gui: Callable) -> None:
    """Attach the ``gui`` subcommand to ``subparsers``."""
    # =========================================================================
    gui_parser = subparsers.add_parser(
        "desktop",
        aliases=["gui"],
        help="Build and launch the native desktop app",
```

docstring 说 "Attach the ``gui`` subcommand"，实际注册的主名是 `desktop`。
main.py 的注释块把真相写在调用点上：

`hermes_cli/main.py:12434 @ 863e313`

```
    # =========================================================================
    # desktop (a.k.a. gui) command
    #
    # The canonical name is "desktop"; "gui" is kept as a deprecated alias
    # for one release. The Hermes-Setup.exe success screen tells users to
    # run `hermes desktop` from a terminal, so the canonical name needs
    # to be the one that appears in --help (argparse promotes the primary
    # name; aliases stay hidden).
    # =========================================================================
```

**argparse 的 alias 语义被当作"改名过渡"的工具**：主名进 `--help`，别名隐藏但可用。
理由具体到"安装器成功页印的是 `hermes desktop`"。合理；但模块名/函数名/docstring
三处仍停在旧名，是纯粹的债。

**V6 · `login.py` 故意不给 `help=`**

`hermes_cli/subcommands/login.py:13 @ 863e313`

```
    """Attach the deprecated ``login`` subcommand to ``subparsers``.

    ``hermes login`` was removed in favor of ``hermes auth`` / ``hermes model``
    (the runtime handler in ``hermes_cli/auth.py::login_command`` just prints a
    deprecation message and exits).  The subparser is kept registered so that
    old scripts/aliases invoking ``hermes login [--flags]`` still receive the
    actionable deprecation message rather than an argparse ``invalid choice:
    'login'`` error — but:

    - The subparser is registered WITHOUT a ``help=`` kwarg so the row is
      omitted from ``hermes --help`` (argparse only lists subcommands that
      have a help string).  This hides a command that no longer works (#24756)
      without the ``help=argparse.SUPPRESS`` ``==SUPPRESS==`` leak that
      argparse emits for a top-level subparser on Python 3.12+.
    - ``--provider`` accepts ANY value (no ``choices=``) so that, e.g.,
      ``hermes login --provider anthropic`` reaches the deprecation handler and
      gets pointed at ``hermes model`` instead of crashing in argparse with
      ``invalid choice: 'anthropic'`` before the handler can run.
    """
```

**两个 argparse 细节都是踩出来的**：
① 顶层子命令用 `help=argparse.SUPPRESS` 在 Py3.12+ 会把字面量 `==SUPPRESS==` 印进帮助；
正确做法是**根本不传 `help=`**（argparse 只列有 help 的子命令）。
② 弃用命令的参数**必须放宽而不是收紧**——`--provider anthropic` 若被 `choices=` 拦掉，
用户得到的是 argparse 的 `invalid choice`，而不是"请改用 hermes model"的友好提示。
两条都有测试：`tests/hermes_cli/test_subcommands_batch.py:122`（`test_login_subparser_help_is_suppressed`，
断言 `"==SUPPRESS==" not in help_text`）。

**V7 · 父子双 `set_defaults`**

`hermes_cli/subcommands/approvals.py:72 @ 863e313`

```
    suggest_parser.add_argument(
        "--db",
        help="Path to an alternate session database (default: ~/.hermes/state.db)",
    )
    suggest_parser.set_defaults(func=cmd_approvals)
    approvals_parser.set_defaults(func=cmd_approvals)
```

同形的还有 `hermes_cli/subcommands/security.py:61`–`62`。功能上冗余（父级的 default 已经足够，子级不覆盖成别的函数），
但它把"裸 `hermes approvals` 也要走同一个 handler"这个意图写进了代码。
其余 38 个模块只在父级设一次。

**V9 · dest 命名三分**

| 后缀 | 模块 |
|---|---|
| `_command` | approvals, config, cron, debug, gateway(×2: `gateway_command`/`proxy_command`), memory, security, skin, slack, sync |
| `_action` | auth, claw, hooks, mcp, monitoring, pairing, plugins, profile, skills(+`snapshot_action`/`tap_action`), tools, webhook |
| `_subcommand` | dashboard |

`hermes_cli/subcommands/dashboard.py:176 @ 863e313`

```
    dashboard_subparsers = dashboard_parser.add_subparsers(
        dest="dashboard_subcommand"
    )
```

**这条没有任何正当理由**——纯粹是从 main.py 里逐字搬过来时把历史不一致一起搬了。
后果不严重（每个 dest 只被自己的 handler 读），但它让"读一个新子命令要先猜 dest 叫什么"
成为常态。

**非偏离但值得记的两点**：
- `hermes_cli/subcommands/import_agent.py:15` 和 `hermes_cli/subcommands/monitoring.py:18` 用了泛化局部变量名（`parser` / `p`）而非
  `<name>_parser`，纯风格。
- `sync.py` 是唯一在模块 docstring 里把完整 CLI 表面画出来的 builder，可读性最好：

`hermes_cli/subcommands/sync.py:1 @ 863e313`

```
"""``hermes sync`` subcommand parser — Skill Sync.

Cloned from ``hermes_cli/subcommands/cron.py`` — same injected-handler shape
(``func=cmd_sync``) so this module does not import ``main`` (cycle avoidance).

Skill Sync covers two surfaces, both under this one command for launch:
```

### 3.4 包外还有两套并行的注册契约

本段之外（但在同一个 `main()` 里）还活着两种不同的模块↔子命令契约，
说明"subcommands 契约"并没有覆盖全部子命令：

**契约 B：`register_cli(parser)`** —— 模块拿到**已建好的 parser**，自己往里加东西，
handler 也自己绑：

`hermes_cli/main.py:11319 @ 863e313`

```
    # Lazy import — only pays for itself when this subcommand is actually used.
    from hermes_cli import secrets_cli as _secrets_cli
    from hermes_cli import onepassword_secrets_cli as _op_secrets_cli

    _secrets_cli.register_cli(secrets_bw)
    _op_secrets_cli.register_cli(secrets_op)
```

**契约 C：`register_subparser(subparsers)`** —— 模块拿到 subparsers action，自己 `add_parser`，
且**注册失败允许被吞**：

`hermes_cli/main.py:11418 @ 863e313`

```
    try:
        from agent.lsp.cli import register_subparser as _lsp_register
        _lsp_register(subparsers)
    except Exception as _lsp_err:  # noqa: BLE001
        # LSP is optional infrastructure — never let a registration
        # failure break the CLI overall.
        logger.debug("LSP CLI registration failed: %s", _lsp_err)
```

三套契约的分工逻辑（我的判读）：
- **A（`build_*_parser` + 注入 handler）**：handler 还锁在 main.py 里的历史存量；
- **B（`register_cli`）**：handler 已经搬进独立模块的，模块自治；
- **C（`register_subparser` + try/except）**：可选组件，缺了也要能启动。

**这三套没有任何文档统一说明，`subcommands/__init__.py` 的 docstring 只讲了 A。**

---

## 4. 可疑缺陷清单

> 分组：A=正确性/并发，B=安全，C=用户可见行为，D=可维护性/测试。
> 每条给：现象 / 锚点 / 为什么可疑 / 触发条件 / 置信度。

### A1 · `_cleanup_gateway_service` 改的是 `os.environ`，而 `get_hermes_home()` 优先读 contextvar

**现象**：为了让 `get_service_name()` 算出正确的服务名，`_cleanup_gateway_service` 临时把
`os.environ["HERMES_HOME"]` 指向目标 profile。但 `get_hermes_home()` 的解析顺序是
**contextvar override → 环境变量 → 平台默认**。若调用时上下文里已有 override（例如网关
多路复用的一个 turn 里、或任何 `set_hermes_home_override` 作用域内），这次环境变量赋值
**完全无效**，`get_service_name()` 会算出**当前上下文 profile** 的服务名。

**锚点** `hermes_cli/profiles.py:1715 @ 863e313`

```
    old_home = os.environ.get("HERMES_HOME")
    try:
        os.environ["HERMES_HOME"] = str(profile_dir)
        from hermes_cli.gateway import get_service_name, get_launchd_plist_path
```

对照，`hermes_constants.py:132 @ 863e313`：

```
    override = get_hermes_home_override()
    if override:
        return Path(override)

    if not os.environ.get("HERMES_HOME", "").strip():
        _warn_profile_fallback_once()

    return _hermes_home_from_env()
```

同文件里正确的写法（`hermes_cli/profiles.py:528 @ 863e313`）：

```
        token = set_hermes_home_override(str(profile_dir))
```

**为什么可疑**：① 语义错（override 赢）；② 线程不安全——`hermes_constants.py:33` 的
docstring 明说 "It deliberately does not mutate ``os.environ`` because that is shared by
every thread in the process"，这里正是它警告的那件事；③ `get_process_hermes_home()`
的 docstring（`hermes_constants.py:148`）也埋了同一个前提 "as long as nothing mutates
``os.environ`` in-process"。**后果**：删/改名一个 profile 时，去 disable 的可能是**另一个
profile 的 systemd unit**，或反过来漏删目标 unit（漏删则 `Restart=` 把网关拉起来，
刚删的目录被重建）。

**触发条件**：`delete_profile()` / `rename_profile()` 在一个已经设置了 contextvar override
的上下文里被调用——最现实的是 web 面板（`hermes_cli/web_routers/profiles.py`）在多路复用
网关进程内处理删除请求时。纯 CLI 单进程路径不会触发。

**置信度：中**（机制确凿；"面板路径确实带 override" 我没有逐层追到调用栈，未实跑验证）。

### A2 · `delete_profile` 不清理自定义 alias，删完留下指向已消失 profile 的可执行文件

**现象**：`hermes profile alias coder --name c1` 会在 `~/.local/bin/c1` 生成 wrapper。
随后 `hermes profile delete coder` **只查 / 只删 `~/.local/bin/coder`**，`c1` 原样留下。
用户之后敲 `c1` 得到 `Error: Profile 'coder' does not exist.`（来自 `resolve_profile_env`）。

**锚点** `hermes_cli/profiles.py:1513 @ 863e313`

```
    # Check for service
    wrapper_path = _get_wrapper_dir() / canon
    has_wrapper = wrapper_path.exists()
    if has_wrapper:
        items.append(f"Command alias ({wrapper_path})")
```

`hermes_cli/profiles.py:1555 @ 863e313`：

```
    # 3. Remove wrapper script
    if has_wrapper:
        if remove_wrapper_script(canon):
            print(f"✓ Removed {wrapper_path}")
```

`remove_wrapper_script` 的候选集只有 profile 同名文件（`hermes_cli/profiles.py:493 @ 863e313`）：

```
    # Check both the extensionless path (POSIX) and .bat (Windows)
    candidates = [wrapper_dir / canon]
    if is_windows:
        candidates.insert(0, wrapper_dir / f"{canon}.bat")
```

**为什么可疑**：模块里**已经有**做反向查找的现成函数 `build_alias_map()`
（`hermes_cli/profiles.py:572`），`list_profiles` 也确实用它显示自定义 alias
（`hermes_cli/profiles.py:918`），唯独删除路径没用。而且删除前的"将永久删除"清单
（`hermes_cli/profiles.py:1509`）也因此漏报自定义 alias——用户在确认提示里看不到它会被留下。

**同一问题在 `rename_profile` 上更糟**（`hermes_cli/profiles.py:2222 @ 863e313`）：

```
    # 4. Update wrapper script
    remove_wrapper_script(old_canon)
```

改名后自定义 alias `c1` 仍写着 `hermes -p coder`，而 `coder` 已不存在——alias 直接失效且无提示。

**触发条件**：使用过 `hermes profile alias <p> --name <custom>` 后再 delete/rename。

**置信度：高**（三个函数的代码路径都读全了；无测试覆盖此场景——`test_profiles.py` 里
`TestFindAliasForProfile` 只测显示侧，`TestRenameProfile` 只测目录和 Honcho）。

### B1 · `_default_export_ignore` 用白名单，但唯一的"凭据不外泄"单元断言测的是一张**死常量**

**现象**：`_DEFAULT_EXPORT_EXCLUDE_ROOT`（`hermes_cli/profiles.py:203`，23 项）在生产代码里
**没有任何引用**——`_default_export_ignore` 只用 `_DEFAULT_EXPORT_INCLUDE_ROOT`。
全仓引用它的只有注释和一条测试。

**锚点** `hermes_cli/profiles.py:1897 @ 863e313`

```
        # Root-level allow-list: drop everything that isn't a known
        # Hermes profile artifact.
        if Path(directory) == root_dir:
            ignored.update(
                entry for entry in contents if entry not in _DEFAULT_EXPORT_INCLUDE_ROOT
            )
        return ignored
```

`tests/hermes_cli/test_profile_export_credentials.py:15 @ 863e313`：

```
    def test_auth_json_in_default_exclude_set(self):
        """auth.json must be in the default export exclusion set."""
        assert "auth.json" in _DEFAULT_EXPORT_EXCLUDE_ROOT
```

**为什么可疑**：这条测试的名字和 docstring 承诺的是"默认 profile 导出不含凭据"，
实际断言的只是"某个不再被使用的 frozenset 里有这个字符串"。**把 `_DEFAULT_EXPORT_INCLUDE_ROOT`
里误加一项 `"auth.json"`，这条测试照样绿。** 同文件第二条测试
（`test_named_profile_export_excludes_auth`，`:20`）测的是**命名** profile 的路径，
走的是另一条 lambda（`hermes_cli/profiles.py:1976`），**默认 profile 的导出路径没有任何行为级测试**。

**当前行为其实是安全的**（`auth.json` / `.env` 不在 include 表里所以被排除），
所以这不是活的漏洞，而是**一层假的护栏**。

**触发条件**：任何人往 `_DEFAULT_EXPORT_INCLUDE_ROOT` 里加敏感项，或把 include 逻辑改回黑名单。

**置信度：高**（引用面已全仓 grep 确认）。

### B2 · `create_wrapper_script` 校验 alias 名，但不校验被插进 shell 脚本的 `target`

**现象**：wrapper 内容由 f-string 拼装，`hermes_exe` 走了 `shlex.quote`，
**`profile` 变量没有**。而 `profile` 来自 `target` 参数，只经过 `normalize_profile_name`
（仅 `strip()` + `lower()`，不过滤任何字符），`validate_alias_name` 校验的是 `canon`（alias），
**不是 `profile`**。

**锚点** `hermes_cli/profiles.py:448 @ 863e313`

```
    canon = normalize_profile_name(name)
    profile = normalize_profile_name(target) if target else canon
    # The alias is used verbatim as a filename under the wrapper dir; reject
    # any value that isn't a single safe identifier so it can't traverse out.
    validate_alias_name(canon)
```

`hermes_cli/profiles.py:473 @ 863e313`：

```
            wrapper_path.write_text(f'#!/bin/sh\nexec {shlex.quote(hermes_exe)} -p {profile} "$@"\n', encoding="utf-8")
```

Windows 分支同样（`hermes_cli/profiles.py:464 @ 863e313`）：

```
            wrapper_path.write_text(f"@echo off\r\nhermes -p {profile} %*\r\n", encoding="utf-8")
```

**为什么可疑**：同一行里对一个变量做了引用转义、对另一个没有，说明是**遗漏而非有意**。
`target` 若含空格或 `;`，写出的是可执行的多命令 shell 脚本。次生影响：`build_alias_map`
反查时 `rest.split(None, 1)[0]`（`hermes_cli/profiles.py:607`）只取第一个 token，反向表也会错。

**触发条件（当前不可达，需要串两步）**：唯一传 `target` 的调用点是
`hermes_cli/main.py:9642`，其 `name` 先过了 `profile_exists(name)`（`hermes_cli/main.py:9620`）——
即磁盘上必须真有同名目录。而 `create_profile` 的写入闸口会拒绝非法名。所以要利用必须
**手工在 `~/.hermes/profiles/` 下建一个含 shell 元字符的目录**（或由别的写入方建）。
这已属于"本地已有写权限"的场景，收益有限。

**置信度：中**（缺陷本身确凿：函数级契约不完整、公开函数无输入校验；可利用性低）。

### C1 · `hermes -p Coder` 不是"按 coder 跑"，而是 argparse 硬报错

**现象**：`normalize_profile_name` 的存在意义就是接住大小写混写的输入
（docstring 明写 "Dashboards and tools may pass title-cased display labels; normalize
before validation, assignment, and subprocess spawn (see issue #18498)"，`hermes_cli/profiles.py:311`）。
但 CLI 入口的正则闸**跑在 normalize 之前、跑在原始 argv 值上**。

**锚点** `hermes_cli/main.py:615 @ 863e313`

```
    if profile_name is not None and consume == 2:
        import re as _re

        if not _re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", profile_name):
            profile_name = None
            consume = 0
            profile_index = None
```

**为什么可疑**：`"Coder"` 不匹配 `^[a-z0-9]...`，于是 `profile_name` 被清空、
`consume=0`、`profile_index=None`。三个后果连锁：
① profile 覆盖不发生（可能改为落到粘性 `active_profile` 上——**静默切到别的 profile**）；
② `-p Coder` **不会从 `sys.argv` 里剪掉**（剪切以 `consume > 0` 为条件，`hermes_cli/main.py:685`）；
③ `-p` 根本不在顶层 parser 上（`hermes_cli/_parser.py:16` 明写 "so it isn't on the parser"），
argparse 必然报 `unrecognized arguments: -p Coder`。

也就是说，一个在**面板里合法、在 `hermes profile create` 时被 normalize 接受**的名字写法，
在 CLI 上得到的是一条与 profile 完全无关的 argparse 错误。修法是把 `.lower()`/normalize
提到正则之前（注意不能直接调 `normalize_profile_name`，因为该函数在 profiles.py 里，
而这段代码刻意跑在 hermes 模块 import 之前——这正是重复正则存在的根因）。

**触发条件**：`hermes -p Coder ...` / `hermes --profile Coder ...`，即用户按面板上显示的
Title-Case 标签去敲 CLI。

**置信度：高**（三段代码路径都读全了；`tests/hermes_cli/test_apply_profile_override.py`
只覆盖 HERMES_HOME 守卫，无大小写用例）。

### C2 · `delete_profile` 的 active_profile 清理用未规范化的字符串比较

**现象**：`get_active_profile()` 原样返回文件内容（不 normalize、不 validate），
而比较对象 `canon` 是规范化过的。

**锚点** `hermes_cli/profiles.py:1606 @ 863e313`

```
    # 5. Clear active_profile if it pointed to this profile
    try:
        active = get_active_profile()
        if active == canon:
            set_active_profile("default")
            print("✓ Active profile reset to default")
    except Exception:
        pass
```

`hermes_cli/profiles.py:1805 @ 863e313`：

```
    path = _get_active_profile_path()
    try:
        name = path.read_text(encoding="utf-8").strip()
        if not name:
            return "default"
        return name
```

**为什么可疑**：`set_active_profile` 永远写规范化后的值（`hermes_cli/profiles.py:1820`），所以
Hermes 自己写出来的文件不会触发。但该文件是纯文本、路径公开（`<root>/active_profile`），
文档也教用户 `hermes profile use`——手工编辑/脚本写入完全可能出现 `Coder\n`。
此时删除 `coder` 后 `active_profile` 仍指向它，下一次裸 `hermes` 会走到
`resolve_profile_env` 的 `FileNotFoundError` 分支，被 `hermes_cli/main.py:671` 打印后 `sys.exit(1)`
——**CLI 完全起不来，且错误信息不提示"去删 active_profile"**。

**触发条件**：`active_profile` 文件被非 Hermes 手段写入非规范值 + 删除该 profile。

**置信度：中**（代码路径确凿；触发前提需要外部写入）。

### D1 · `subcommands` 的"批量冒烟测试"整张用例表是死代码

**现象**：`tests/hermes_cli/test_subcommands_batch.py` 定义了 23 条
`(命令, builder, handler 关键字, argv)` 用例，但**没有任何 `@pytest.mark.parametrize`
消费它**。同文件的 `import pytest` 和 helper `_login_parser()` 也无人使用。

**锚点** `tests/hermes_cli/test_subcommands_batch.py:50 @ 863e313`

```
# (subcommand_name, builder, handler_kwargs, sample_argv)
SINGLE_HANDLER_CASES = [
    ("model", build_model_parser, "cmd_model", ["model"]),
    ("setup", build_setup_parser, "cmd_setup", ["setup"]),
```

`tests/hermes_cli/test_subcommands_batch.py:113 @ 863e313`：

```
def _login_parser():
    parser = argparse.ArgumentParser(prog="hermes")
    sub = parser.add_subparsers(dest="command")
    build_login_parser(sub, cmd_login=_h("login"))
    return parser
```

**同样的情况在 `test_subcommands_profile_gateway.py`**：`_profile_parser()` 定义后无人调用，
于是 `build_profile_parser` 的 23 个子动作**一条也没被解析测试覆盖**：

`tests/hermes_cli/test_subcommands_profile_gateway.py:31 @ 863e313`

```
def _profile_parser():
    p = argparse.ArgumentParser(prog="hermes")
    sub = p.add_subparsers(dest="command")
    build_profile_parser(sub, cmd_profile=_h_profile)
    return p
```

**为什么可疑**：这不是随机腐坏，是一次批量删测留下的残渣——两个文件的最近一次提交是
`39975613b "test: prune wave 2 + speed fixes — 28,106 → 19,757 test functions"`。
剪枝把 `@parametrize` 装饰的测试函数删了，却把它喂的数据表和 helper 留下了。
后果：`subcommands/` 现存 23 个模块的"能 import、builder 不抛、func 绑对"这条最基本的
保障**名义上存在、实际不跑**。而这恰恰是该包唯一的保护网——docstring 自己说
"the byte-identical ``--help`` verification done at extraction time is the real behavioral
guarantee; this just guards against a module failing to import or a builder raising"
（`tests/hermes_cli/test_subcommands_batch.py:1`）——提取时的人工比对是一次性的，长期靠的就是这层冒烟。

**触发条件**：任何人往 `subcommands/` 里改坏一个 builder，CI 不会红。

**置信度：高**（grep 已确认无 parametrize 消费，git log 已确认剪枝提交）。

### D2 · `remove_wrapper_script` 对候选文件做无上限 `read_text()`

**现象**：`build_alias_map` 因为读大二进制拖慢 `list_profiles` 到 ~4.5 秒，专门加了
8 KB 上限 + UnicodeDecodeError 过滤（`hermes_cli/profiles.py:563`–`601`）。删除侧没跟进。

**锚点** `hermes_cli/profiles.py:498 @ 863e313`

```
    for wrapper_path in candidates:
        if wrapper_path.exists():
            try:
                # Verify it's our wrapper before removing
                content = wrapper_path.read_text(encoding="utf-8")
                if "hermes -p" in content:
                    wrapper_path.unlink()
                    return True
            except Exception:
                pass
    return False
```

**为什么可疑**：候选路径是 `~/.local/bin/<profile 名>`。若 `~/.local/bin` 里恰好有一个同名的
大二进制（profile 叫 `node`、`ffmpeg`、`uv`……都合法，因为 `_HERMES_SUBCOMMANDS`
不含这些名字），这一行会把整个二进制读进内存。影响是内存尖峰/卡顿，不是正确性——
`except Exception` 会吃掉 `UnicodeDecodeError` 并返回 False，行为仍正确。

**触发条件**：profile 名与 `~/.local/bin` 里某个大文件同名，且执行 delete / rename。

**置信度：中**（代码确凿；实际影响取决于用户环境，规模远小于原来的 O(N·M)）。

### D3 · 三张"子命令名"清单各自为政，`_HERMES_SUBCOMMANDS` 已过期约 40 项

**现象**：仓库里有三张需要手工同步的子命令名单：
① `profiles._HERMES_SUBCOMMANDS`（25 项，用于 alias 冲突检查）；
② `main._BUILTIN_SUBCOMMANDS`（约 68 项，用于跳过插件发现）；
③ main.py 里实际的 `add_parser(...)` 调用（唯一真相）。

**锚点** `hermes_cli/profiles.py:254 @ 863e313`

```
# Hermes subcommands that cannot be used as profile names/aliases
_HERMES_SUBCOMMANDS = frozenset({
    "chat", "model", "gateway", "setup", "whatsapp", "login", "logout",
    "status", "cron", "doctor", "dump", "config", "pairing", "skills", "tools",
    "mcp", "sessions", "insights", "version", "update", "uninstall",
    "profile", "plugins", "honcho", "acp",
})
```

`hermes_cli/main.py:10604 @ 863e313`：

```
_BUILTIN_SUBCOMMANDS = frozenset(
    {
        "acp", "approvals", "auth", "backup", "bundles", "checkpoints", "claw", "completion",
        "computer-use",
        "config", "console", "cron", "curator", "dashboard", "serve", "debug", "doctor",
        "dump", "egress", "fallback", "gateway", "hooks", "import", "import-agent", "insights",
        "gui", "desktop", "kanban", "login", "logout", "logs", "lsp", "mcp", "memory", "migrate", "moa",
        "journey", "memory-graph", "learning",
        "model", "monitoring", "pairing", "pets", "plugins", "portal", "profile",
        "project", "proxy",
        "prompt-size",
        "send", "sessions", "setup",
        "skin", "skills", "slack", "status", "sync", "tools", "uninstall", "update",
        "version", "webhook", "whatsapp", "whatsapp-cloud", "chat", "secrets", "security",
```

**为什么可疑**：① 表 ① 缺了 `auth`、`backup`、`console`、`dashboard`、`serve`、`debug`、
`desktop`、`hooks`、`import`、`logs`、`memory`、`security`、`skin`、`slack`、`sync`、
`webhook` 等 40 余个现存命令——这些名字都能被拿去当 alias；
② 表 ① 含 `honcho`，而它**不在**表 ② 里（插件命令），说明两表演化脱节；
③ 表 ② 自己的注释（`hermes_cli/main.py:10600`）承认它必须手工与 `add_parser` 保持同步。

**实际影响很轻**：alias 是 `~/.local/bin/<name>` 里的独立可执行文件，
名叫 `logs` 不会遮蔽 `hermes logs`；而真正会撞 PATH 里已有二进制的情况，
`check_alias_collision` 的 `which/where` 探测（`hermes_cli/profiles.py:410`）已经能挡。
所以这是 UX 一致性 + 可维护性问题，不是功能缺陷。

**触发条件**：`hermes profile create serve` 之类。

**置信度：高**（两表已逐项比对）。

### D4 · `login.py` 的 `--provider` 无 `choices=`，`logout.py` 的有——同一批 provider 名两处硬编码

**现象**：弃用的 `login` 刻意放开 `--provider`（有充分理由，见 V6），而仍在用的
`logout` 把 provider 名硬编码进 `choices=`。

**锚点** `hermes_cli/subcommands/logout.py:22 @ 863e313`

```
    logout_parser.add_argument(
        "--provider",
        choices=["nous", "openai-codex", "xai-oauth", "spotify"],
        default=None,
        help="Provider to log out from (default: active provider)",
    )
```

对比 main.py 里顶层 `--provider` 的做法（从注册表动态生成 + 静态兜底）：

`hermes_cli/main.py:10580 @ 863e313`

```
    """Build the --provider choices list from CANONICAL_PROVIDERS + 'auto'."""
    try:
        from hermes_cli.models import CANONICAL_PROVIDERS as _cp
        return ["auto"] + [p.slug for p in _cp]
    except Exception:
        # Fallback: static list guarantees the CLI always works
```

**为什么可疑**：`auth.py` 的 `auth logout <provider>`（`hermes_cli/subcommands/auth.py:69`）是自由字符串，
`logout --provider` 是 4 选 1，两条路径能登出的 provider 集合不同。新增一个 OAuth provider
时，`logout` 会以 `invalid choice` 拒绝——**正是 `login.py` 的 docstring 花整段解释要避免的
那种失败**（`hermes_cli/subcommands/login.py:28`）。

**触发条件**：`hermes logout --provider anthropic`（或任何不在这 4 个里的 provider）。

**置信度：中**（行为确凿；是否算缺陷取决于"logout 是否本就只支持这 4 个"——
我没有读 `auth.py::logout_command` 的实现来确认）。

### D5 · `_default_export_ignore` 用未 resolve 的路径判"是否根层"，与 clone 侧写法不一致

**现象**：两个 copytree ignore 回调判"当前目录是不是源根"的方式不同。

**锚点** `hermes_cli/profiles.py:1899 @ 863e313`

```
        if Path(directory) == root_dir:
```

对比 `hermes_cli/profiles.py:179 @ 863e313`：

```
            try:
                at_root = Path(directory).resolve() == source_resolved
            except (OSError, ValueError):
```

**为什么可疑**：`copytree` 传给 ignore 的 `directory` 是它自己拼出来的路径，与传入的
`src` 同源，所以在当前调用方式下相等成立。但一旦 `export_profile` 改成传
`profile_dir.resolve()` 或传字符串，`Path(directory) == root_dir` 就会**静默变成永远 False**
——白名单失效，整个 HERMES_HOME 根层的东西全被打包进导出档（含 `auth.json`、`.env`、
`state.db`）。**失效方式是静默的、方向是不安全的**，而它保护的正是 §B1 那条唯一的凭据边界。

**触发条件**：改动 `export_profile` 里传给 `copytree` 的 `src` 表达式（`hermes_cli/profiles.py:1958`）。

**置信度：中**（当前无 bug；属于"脆弱不变量 + 无测试锁定"）。

---

## 5. 与文档/注释的出入

> 依 CLAUDE.md 约定：README / 根 AGENTS.md / website/docs 与代码冲突时以代码为准。

### ▲ 冲突 1 · AGENTS.md 说 profiles 根锚在 `Path.home()`，代码锚在 `get_default_hermes_root()`

`AGENTS.md:1212 @ 863e313`

```
6. **Profile operations are HOME-anchored, not HERMES_HOME-anchored** — `_get_profiles_root()`
   returns `Path.home() / ".hermes" / "profiles"`, NOT `get_hermes_home() / "profiles"`.
   This is intentional — it lets `hermes -p coder profile list` see all profiles regardless
   of which one is active.
```

代码（`hermes_cli/profiles.py:278 @ 863e313`）：

```
    return _get_default_hermes_home() / "profiles"
```

**定案：以代码为准。** 文档的**结论**（不锚在当前 HERMES_HOME）是对的，
**机制描述**是错的——不是 `Path.home()`，而是 `get_default_hermes_root()`，后者在
Docker/自定义部署下会返回 `HERMES_HOME` 本身（`hermes_constants.py:178`）。
按文档写代码会在 Docker 里把 profiles 放到宿主家目录而不是挂载卷上，**profile 全部不持久**。
`hermes_cli/profiles.py:274` 的 docstring 反而是对的（"In Docker/custom deployments where HERMES_HOME
points outside ``~/.hermes``, profiles live under ``HERMES_HOME/profiles/`` so they persist
on the mounted volume."），所以这是 AGENTS.md 单点过期。

### ▲ 冲突 2 · 用户文档说 wrapper 脚本设置 `HERMES_HOME`，实际它只传 `-p`

`website/docs/user-guide/profiles.md:276 @ 863e313`

```
Profiles use the `HERMES_HOME` environment variable. When you run `coder chat`, the wrapper script sets `HERMES_HOME=~/.hermes/profiles/coder` before launching hermes. Since 119+ files in the codebase resolve paths via `get_hermes_home()`, Hermes state automatically scopes to the profile's directory — config, sessions, memory, skills, state database, gateway PID, logs, and cron jobs.
```

代码（`hermes_cli/profiles.py:473 @ 863e313`）：

```
            wrapper_path.write_text(f'#!/bin/sh\nexec {shlex.quote(hermes_exe)} -p {profile} "$@"\n', encoding="utf-8")
```

**定案：以代码为准。** wrapper 只写 `exec hermes -p <profile> "$@"`，**不设任何环境变量**。
`HERMES_HOME` 是进程内由 `_apply_profile_override()` 设的（`hermes_cli/main.py:683`）。
差别不是文字游戏：按文档理解，`coder` 这个命令对子进程也会导出 `HERMES_HOME`；
按代码，只有 hermes 自己的进程会设，而且是在 Python 启动之后。这直接决定了
"能不能靠 wrapper 给非 hermes 子进程传 profile 上下文"——不能。

### ◇ 出入 3 · "每个 profile 自动获得 alias" 是有条件的

`website/docs/user-guide/profiles.md:87 @ 863e313`

```
Every profile automatically gets a command alias at `~/.local/bin/<name>`:
```

代码里创建 alias 有三道闸：`--no-alias` 显式跳过（`hermes_cli/subcommands/profile.py:50`）、
`check_alias_collision` 非空则跳过（`hermes_cli/main.py:9413`）、`create_wrapper_script` 自身
`OSError` 时返回 None（`hermes_cli/profiles.py:456`）。**定案：文档过度承诺**，实际是"默认尝试创建"。

### ◇ 出入 4 · "删除会移除命令 alias" 只对同名 alias 成立

`website/docs/user-guide/profiles.md:254 @ 863e313`

```
This stops the gateway, removes the systemd/launchd service, removes the command alias, and deletes all profile data. You'll be asked to type the profile name to confirm.
```

见 §4-A2：自定义 alias 不会被移除。**定案：以代码为准，文档需补"自定义 alias 需手工清理"。**

### ◇ 出入 5 · 参考手册对 profile 名的规则描述不全

`website/docs/reference/profile-commands.md:82 @ 863e313`

```
| `<name>` | Name for the new profile. Must be a valid directory name (alphanumeric, hyphens, underscores). |
```

实际规则（`hermes_cli/profiles.py:341`、`:346`）还包含：**必须小写**、**必须以 `[a-z0-9]` 开头**、
**总长 ≤ 64**、**不得为 `hermes`/`default`/`test`/`tmp`/`root`/`sudo`**。
**定案：文档不完整**，用户按文档取名 `My_Bot` 会被拒且（在 CLI 上）拿到的是 argparse 错误（§4-C1）。

### ◇ 出入 6 · `main.py` 注释把 `resolve_profile_env` 说成会 `sys.exit`

`hermes_cli/main.py:611 @ 863e313`

```
    # 1b. Reject values that can't be valid profile names (e.g. pytest's
    # "-p no:xdist" would be misread as profile "no:xdist" otherwise).
    # Mirrors hermes_cli.profiles._PROFILE_ID_RE so we never call
    # resolve_profile_env() with a value it must reject + sys.exit on.
```

`resolve_profile_env` 只 `raise ValueError`（`hermes_cli/profiles.py:2253` 调 `validate_profile_name`），
`sys.exit(1)` 发生在 main.py 自己的 `except ValueError` 分支（`hermes_cli/main.py:675`）。
**定案：注释措辞不精确**（"reject + sys.exit on" 描述的是合成效果），无功能影响。
但它同时暴露了"为什么要重复正则"的真实原因：这段代码跑在 hermes 模块 import 之前，
**不能** import `profiles`。这条理由值得写进注释而现在没写。

### ◇ 出入 7 · `subcommands/__init__.py` 只描述了三套注册契约里的一套

见 §3.4。包 docstring 声称 "each subcommand group owns a
``build_<group>_parser(subparsers, ...)`` function in its own module"，
但 `secrets` / `egress` 走 `register_cli(parser)`、`lsp` 走 `register_subparser(subparsers)`。
**定案：文档以偏概全**，读者若照它推断"所有子命令都在 subcommands/ 下"会漏掉这几支。

### ◇ 出入 8 · `gui.py` 的 docstring/函数名与实际注册的命令名不符

`hermes_cli/subcommands/gui.py:1 @ 863e313`

```
"""``hermes gui`` subcommand parser.
```

实际注册主名为 `desktop`（`hermes_cli/subcommands/gui.py:16`），`gui` 降为 alias。**定案：模块内文档滞后于实现**，
权威说明反而在 main.py 的调用点注释里（`hermes_cli/main.py:12434`）。

---

## 6. 移交

### 6.1 本段最该进成品章的四件事

1. **"进程最早期钉死环境变量"这一招的完整账单**（§1.1 / §2.2 / §2.12）。
   它是 hermes 多实例隔离的全部机制：不传 context、不做依赖注入，靠 `HERMES_HOME` 一个变量
   让 100+ 个调用点自然对齐。收益是**零侵入**（新代码只要用 `get_hermes_home()` 就自动 profile 安全）；
   代价清单很长：`-p` 必须手工从 argv 里扒（→ §4-C1）、模块级缓存导致 skill 播种必须开子进程
   （`hermes_cli/profiles.py:1194`）、进程内切作用域需要第二套 contextvar 机制（→ §4-A1 的混用）。
   **成品章应该把"零侵入"和这张代价清单并排放。**

2. **"提取而不重构"的纪律**（§3.1–§3.3）。179 个 `add_parser` 从 3300 行函数里搬出来，
   靠的是三条硬约束：签名固定、**禁止 import main**、handler 依赖注入。
   `gateway.py` 明知 `proxy` 与 `gateway` 无关也照搬在一起，并把理由写进 docstring——
   这是正确的重构节奏（先等价搬迁，再谈拆分）。**同时要讲清代价：拆完仍是手写注册，
   一个新命令要改 3–4 个地方，且"漏加调用"是静默失败。**

3. **argparse 的三个真实陷阱**，都在本段有事故证据：
   - `dest` 推导撞车让整条命令掉进聊天（`hermes_cli/subcommands/mcp.py:46`）；
   - `help=argparse.SUPPRESS` 在 Py3.12+ 泄漏 `==SUPPRESS==`，正解是不传 `help=`（`hermes_cli/subcommands/login.py:20`）；
   - 弃用命令的参数要**放宽**不要收紧，否则用户拿到 `invalid choice` 而不是迁移提示（`hermes_cli/subcommands/login.py:27`）；
   - 附加：`default=argparse.SUPPRESS` 是同一个 flag 挂多层 parser 时不被子级默认值覆盖的唯一解（`hermes_cli/subcommands/_shared.py:24`）。

4. **白名单 vs 黑名单的一次真实翻转**（§2.10）。Docker 部署让 `HERMES_HOME` == cwd，
   黑名单永远列不全用户放在旁边的任意文件，于是导出改成"只带我认识的"。
   翻转的代价（新产物必须记得加表）写在注释里，而**护栏测的却是那张被废弃的黑名单**（§4-B1）。
   这是"安全边界改了、测试没跟上"的教科书案例。

### 6.2 建议纳入 R8B 报告的定案候选

- **P1 → 修正表述**：契约统一的是**函数形状**，不是**注册机制**；注册是全手写的。
- **P2 → 推翻**：`profiles.py` 是重副作用运维模块，不是路径计算器。
- **P3 → 推翻**：8 处 Python 副本 + 4 处 TS 副本 + 两个同名 `validate_profile_name`。
- 缺陷清单里建议优先写进报告的三条：**A2（alias 孤儿，高置信、无测试）**、
  **C1（`-p Coder` 直接报错，高置信、用户可见）**、**D1（冒烟测试整表死掉，高置信、影响 CI 护栏）**。
- 文档冲突建议记两条 ▲：**AGENTS.md:1211 的 `Path.home()`**、
  **profiles.md:276 的 "wrapper sets HERMES_HOME"**——两条都会误导按文档实现的人。

### 6.3 本段未覆盖 / 留给后续

- `subcommands/config.py`、`subcommands/pairing.py` 前轮已精读，本稿只放进契约表。
- `main.py` 里 44 个 `cmd_*` handler 的**实现**不在本段（只追到 `args.func` 这一跳）。
- `hermes_cli/profile_distribution.py`（782 行，`hermes profile install/update/info` 的实际逻辑）
  与 `hermes_cli/profile_describer.py`（288 行）本段未读——它们是 `subcommands/profile.py`
  声明的子动作的落地方，属同一簇，建议同轮补齐。
- `hermes_cli/web_routers/profiles.py` 是 profiles.py 的第二大消费方（面板侧），
  §4-A1 的触发条件判定需要读它才能从"中"升到"高"。
- s6 容器路径（`_maybe_register_gateway_service` / `service_manager.py` 的 S6 backend）
  只做了结构级理解，未验证。
