# r9c 底稿 · 密钥来源(secret sources)与凭据文件透传

> 本文件是**证据层底稿**,面向"要凭它重实现同等机制的自己",不求好读。
> 溯源约定:凡对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` **单独成行、置于代码块之前**,
> 代码块为逐字摘录。非源码块用 `text` / `verify` / `console` 显式标注。
> 引用路径一律从基线仓库根写起(不写裸文件名)。
> 基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`。

---

## 0. 范围、方法与发现提要

### 0.1 覆盖的 8 个文件

| 文件 | 行数 | 角色 |
|---|---|---|
| `agent/secret_sources/bitwarden.py` | 1048 | Bitwarden Secrets Manager(`bws` CLI)+ 二进制自安装 + 加密缓存 |
| `agent/secret_sources/onepassword.py` | 682 | 1Password(`op` CLI)`op://` 引用解析 |
| `tools/credential_files.py` | 530 | 凭据**文件**向远端沙箱的透传/挂载注册表 |
| `agent/secret_sources/command.py` | 501 | 任意用户命令作为密钥来源(`/bin/sh -c`) |
| `agent/secret_sources/registry.py` | 470 | 注册表 + apply 编排器(优先级/超时/溯源) |
| `agent/secret_sources/base.py` | 336 | 抽象契约 SecretSource / FetchResult / ErrorKind |
| `agent/secret_sources/_cache.py` | 215 | 共享缓存底座(原子写 0600 + TTL) |
| `agent/secret_sources/__init__.py` | 41 | 包门面 + 再导出 |

### 0.2 一句话骨架

**密钥不落在 `config.yaml` 里,而是启动时从外部密钥管理器拉进 `os.environ`。**
时序固定:`~/.hermes/.env` 加载完 → 编排器 `apply_all()` 跑一遍所有启用的来源 →
其余 Hermes 代码才开始读 `os.environ` 取凭据。三个内置来源(Bitwarden / 1Password / command)
只负责"取",**写环境变量、优先级、冲突、溯源全部归编排器**。

### 0.3 发现提要

| 记号 | 位置 | 一句话 |
|---|---|---|
| ■-1 | `agent/file_safety.py:274-285` | 1Password 明文磁盘缓存 `cache/op_cache.json` 不在读禁清单里,于是它**可被 skill 挂进远端沙箱**;结构完全相同的 `cache/bws_cache.json` 被拒 |
| ■-2 | `tools/credential_files.py:191-208` | 配置侧 `terminal.credential_files` **完全没走** master-store 禁清单,`.env` / `auth.json` 可直接挂进沙箱;skill 侧同名声明会被拒 |
| ■-3 | `agent/secret_sources/base.py:305-314` | 插件指南力荐的 `run_secret_cli()` 从 `os.environ` 取 `allow_env`,**绕过** per-fetch 环境视图:多 profile 下本 profile 的 token 传不进去、兄弟 profile 的 token 反而漏进去 |
| ■-4 | `agent/secret_sources/command.py:48` | `command.py` 从 `bitwarden` 而非 `base` 导入 `FetchResult`,于是 bitwarden 导入失败会连带干掉 command 源——违反 `registry.py` 自己写的不变量 |
| ■-5 | `agent/secret_sources/onepassword.py:383-386` | `cache_ttl_seconds: 0` 时 1Password 仍把明文密钥写进进程级 `_CACHE`;Bitwarden 同场景不写,文档声称"读写都关" |
| ■-6 | `agent/secret_sources/registry.py:113` | 源名校验用 Unicode 感知的 `.isalnum()`,契约却写 `[a-z0-9_]+`;`café` / 全角 `ｖａｕｌｔ` 都能注册,可造同形异码来源 |
| ▲-1 | `website/docs/user-guide/secrets/index.md:50` | "Bitwarden and 1Password ship in-tree"——实际内置**三个**(含 command),同文件第 9 行自己就列了 command |
| ▲-2 | `website/docs/developer-guide/secret-source-plugin.md:109` | "both bundled sources default `True`"——内置源是三个,第三个 `command` 默认 `False` |
| ▲-3 | `website/docs/user-guide/secrets/onepassword.md:154` | "fully disabled — reads *and* writes — when `cache_ttl_seconds: 0`"——进程内那一层的**写**没关(即 ■-5 的文档面) |
| ◇-1 | `agent/secret_sources/base.py:54-70` | 整套 per-fetch 环境视图(多 profile 隔离机制)在插件指南里**一字未提**,示例反而教 `os.environ.get()` |
| ◇-2 | `hermes_cli/config_defaults.py:2875` | `secrets.command` / `preserve_existing` / `profile_alias` / `timeout_seconds` 都不在 `DEFAULT_CONFIG` 里 |
| ◇-3 | `agent/secret_sources/command.py:183-190` | helper 拿到的是 post-dotenv 环境的**逐字节副本**(所有凭据);`command.md` 的 "Security model" 一节没写 |
| ◇-4 | `agent/secret_sources/bitwarden.py:864` | `scheme = "bws"` 被占用登记,但全仓没有任何 `bws://` 引用语法的实现或文档 |

**没有 ◎。** 逐条核对的文档断言里没有出现"字面为真但显著保守"的形态;
按 CLAUDE.md 的记号定义,不为了凑齐记号而把别的东西记成 ◎。

---

## 1. 抽象契约:`base.py`

### 1.1 一个 secret source 要实现什么

只有一个抽象方法。

`agent/secret_sources/base.py:162-169`

```
    @abstractmethod
    def fetch(self, cfg: dict, home_path: Path) -> FetchResult:
        """Resolve this source's secrets. MUST NOT raise or prompt.

        ``cfg`` is the source's raw config section (``secrets.<name>``)
        from config.yaml — treat every field defensively, the section
        may be malformed.  ``home_path`` is the resolved HERMES_HOME.
        """
```

其余都是有默认实现的可选钩子:`is_enabled` / `override_existing` / `protected_env_vars` /
`fetch_timeout_seconds` / `config_schema` / `remediation`。

契约的四条边界写在模块 docstring 里,**每一条都对应一个具体的设计取舍**。

`agent/secret_sources/base.py:11-28`

```
* **Read-only.**  Sources resolve refs → values.  There is no write-back
  ("save this key to your vault"), no arbitrary secret objects, and no
  mid-session secret API.  If a future need for rotation/refresh appears
  it will arrive as a versioned optional hook — do not bolt it on.
* **Startup-time, synchronous.**  ``fetch()`` is called once per process
  (per HERMES_HOME) by the orchestrator in
  :mod:`agent.secret_sources.registry`, which enforces a wall-clock
  timeout around it.  Sources must not spawn background refreshers.
* **Never raises, never prompts.**  ``fetch()`` returns a
  :class:`FetchResult` — errors go in ``result.error`` with a
  machine-readable :class:`ErrorKind`.  Interactive auth belongs in the
  source's CLI ``setup`` flow, never on the startup path (non-TTY
  gateway/cron startup must never block on stdin).
* **Sources fetch; the orchestrator applies.**  A source returns the
  name→value mapping it *would* contribute.  Precedence (mapped-beats-bulk,
  first-wins, ``override_existing``, protected vars), conflict warnings,
  provenance tracking, and the actual ``os.environ`` writes are owned by
  the orchestrator so no backend can get them wrong.
```

**为什么这么设计**:这四条各自堵一类跨后端会被写错的坑。
"never raises" 的真正理由是启动路径——一个抛异常的后端会让整个 `hermes` 起不来;
"never prompts" 的理由是非 TTY(gateway / cron / Docker)下 `input()` 会永久挂起。
"sources fetch, orchestrator applies" 是最重要的一条:**它把安全敏感的判断从 N 个后端收敛到 1 处**,
后果是任何插件后端都不可能"不小心"覆盖别人的 bootstrap token。

启动侧的挂载点是 dotenv 加载器里的一个包装函数,它自己也把这条时序写死了。

`hermes_cli/env_loader.py:594-597`

```
    Runs AFTER dotenv loads so .env values are visible (sources use them
    to locate bootstrap tokens) but BEFORE the rest of Hermes reads
    ``os.environ`` for credentials.  Any failure here is logged and
    swallowed — external secret sources must never block startup.
```

配置只读 `secrets:` 一段,且单独解析、与主配置加载隔离,免得一个坏 config.yaml 拖垮 dotenv。

`hermes_cli/env_loader.py:715-717`

```
    config_path = home_path / "config.yaml"
    if not config_path.exists():
        return {}
```

### 1.2 失败分类学:`ErrorKind`

`agent/secret_sources/base.py:90-98`

```
    NOT_CONFIGURED = "not_configured"    # enabled but missing token/project/map
    BINARY_MISSING = "binary_missing"    # helper CLI not found / not installed
    AUTH_FAILED = "auth_failed"          # bad credentials
    AUTH_EXPIRED = "auth_expired"        # credentials were valid, aren't now
    REF_INVALID = "ref_invalid"          # a secret reference failed validation
    NETWORK = "network"                  # transport-level failure
    EMPTY_VALUE = "empty_value"          # backend returned nothing for a ref
    TIMEOUT = "timeout"                  # fetch exceeded its wall-clock budget
    INTERNAL = "internal"                # anything else (bug, unexpected shape)
```

固定词表的用途在 docstring 里说得很直白:让编排器可以实现 **kind 相关的策略**,且只实现一次。
Bitwarden 的陈旧缓存回退就是这条的兑现——只在 `NETWORK`/`TIMEOUT` 下回退,
`AUTH_FAILED` 绝不回退(见 §3.5)。

### 1.3 引用语法与 `scheme`:一个"预留但没实现"的接口

`agent/secret_sources/base.py:145-148`

```
        scheme: Optional URI scheme this source owns for secret
            references (``"op"`` for ``op://...``).  Must be unique
            across registered sources — refs may eventually appear
            outside the ``secrets:`` block (e.g. credential-pool
```

**解析发生在哪一层?** 关键结论:**不在通用层,而在各后端内部。**
`registry.py` 里没有任何按 `scheme://` 前缀分派引用字符串的代码;`scheme` 唯一的实际作用
是注册期的**唯一性占用**(见 §2.1)。1Password 的 `op://` 校验完全在自己模块里。

`agent/secret_sources/onepassword.py:165-172`

```
        cleaned = ref.strip()
        if not cleaned.startswith("op://"):
            warnings.append(
                f"Skipping {name!r}: {ref!r} is not an op:// secret reference"
            )
            continue
        valid[name] = cleaned
    return valid, warnings
```

**◇-4**:Bitwarden 声明了 `scheme = "bws"`,但全仓找不到任何 `bws://` 的解析实现或文档。
搜索面:对全仓 `*.py` / `*.md` / `*.ts` / `*.yaml` 搜字面量 `bws://`,零命中。

```verify
cd /home/user/hermes-agent && grep -rn "bws://" --include=*.py --include=*.md --include=*.ts --include=*.yaml . ; echo "exit=$?"
```

即:`scheme` 目前是一个**为未来预留、当前只用来防撞名**的字段。这是个值得学的设计——
用极小的成本(一个类属性 + 一次注册期检查)把"以后引用可能出现在 `secrets:` 块之外"
这个可能性保留住,而不是等到需要时再全局改名。

### 1.4 per-fetch 环境视图:多 profile 隔离的底座

这是本片最容易被忽略、但决定了多 profile 正确性的机制。

`agent/secret_sources/base.py:54-70`

```
_SOURCE_ENVIRONMENT: ContextVar[Optional[MutableMapping[str, str]]]
_SOURCE_ENVIRONMENT = ContextVar("hermes_secret_source_environment", default=None)


def set_source_environment(environ: MutableMapping[str, str]) -> Token:
    """Install a per-fetch environment view without changing ``os.environ``."""
    return _SOURCE_ENVIRONMENT.set(environ)


def reset_source_environment(token: Token) -> None:
    _SOURCE_ENVIRONMENT.reset(token)


def get_source_environment() -> MutableMapping[str, str]:
    """Return the active per-fetch environment, or the process environment."""
    environ = _SOURCE_ENVIRONMENT.get()
    return environ if environ is not None else os.environ
```

**解决什么问题**:多路复用(multiplex)网关里,一个进程要给多个 profile 分别解析密钥。
如果后端直接读 `os.environ`,profile B 的 fetch 就会读到 profile A(或进程全局)的 bootstrap token,
反过来 profile B 的 token 也进不了 `os.environ`。这个 ContextVar 让编排器可以塞进一个
**私有映射**,后端通过 `get_source_environment()` 读它,而 `os.environ` 一个字节都不动。

私有映射是这样拼出来的——只含"全局安全"的变量加该 profile 自己的 `.env`。

`hermes_cli/env_loader.py:205-210`

```
        local_env = {
            name: value
            for name, value in os.environ.items()
            if _is_global_env(name)
        }
        local_env.update(load_env_file(home / ".env"))
```

三个内置源都老实用了 `get_source_environment()`(bitwarden 两处、onepassword 三处、command 一处)。

### 1.5 ■-3:`run_secret_cli()` 绕过 per-fetch 环境视图

`base.py` 给插件后端提供了一个"官方安全姿势"的子进程助手,插件指南把它当必用件推荐。
它的 docstring 承诺得非常明确。

`agent/secret_sources/base.py:285-294`

```
    """Run a secret-manager helper CLI with a minimal, allowlisted env.

    Security posture shared by every subprocess-driven backend:

    * argv list only — never ``shell=True``.  Callers pass user-supplied
      reference strings AFTER a ``--`` option terminator in their argv.
    * The child gets ``PATH``/``HOME``/locale basics plus only the env
      vars named in ``allow_env`` (auth/session vars) and ``extra_env``
      — never a copy of the full post-dotenv ``os.environ``, which by
      this point holds every credential Hermes knows about.
```

但实现取值时用的是 `os.environ`,**不是** `get_source_environment()`。

`agent/secret_sources/base.py:305-314`

```
    base_keep = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TMPDIR", "TEMP",
                 "LANG", "LC_ALL", "XDG_CONFIG_HOME", "XDG_DATA_HOME")
    env: Dict[str, str] = {}
    for key in (*base_keep, *allow_env):
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    if extra_env:
        env.update(extra_env)
    env.setdefault("NO_COLOR", "1")
```

**后果是双向的**:在编排器已经装好私有映射的情况下,
(a) 本 profile 的 bootstrap token 只存在于私有映射里 → **传不进子进程**,该插件源直接 fetch 失败;
(b) 进程全局 `os.environ` 里兄弟 profile 的同名 token → **反而被传进子进程**,
正是私有映射要防的跨 profile 凭据渗漏。

实跑复现(不接触基线,脚本在 scratchpad):

> **R11B 更正**:本块的脚本只存在于当轮会话的 scratchpad(原路径含会话标识,已抹去)、**从未落库**,重跑无法复现,因此它不是「shell 命令即证据」意义上的可重跑证据 —— 由 ```verify 改标 ```console。**结论本身不变**,依据仍是块内输出与同节的行号锚点。

```console
cd <scratchpad> && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python repro_run_secret_cli.py
```

```console
get_source_environment() sees: {'MYVAULT_TOKEN': 'PROFILE-LOCAL-token'}
child *_TOKEN env: {'SIBLING_PROFILE_TOKEN': 'GLOBAL-SECRET-must-not-leak'}
PROFILE-LOCAL token reached child?  False
GLOBAL sibling token leaked?       True
```

**为什么没被测试抓到**:`run_secret_cli` 在生产代码里**一个调用点都没有**。
搜索面是全仓 `*.py`,排除 `tests/` 与函数定义行本身,唯一剩余命中是一行注释、不是调用:

```verify
cd /home/user/hermes-agent && grep -rn "run_secret_cli(" --include=*.py . | grep -v "^./tests/" | grep -v "def run_secret_cli"
```

唯一的用例在 `tests/secret_sources/test_secret_source_registry.py` 的
`test_run_secret_cli_minimal_env`,只断言"父进程里带 `_API_KEY`/`_TOKEN`/`_SECRET` 后缀的变量没漏过去"
——而 pytest 进程环境里本来就没有这些,所以它在任何实现下都会绿。也就是说:
**这个助手是给插件用的、被文档大力推荐的、却既无生产调用点也无有效用例的一段代码**,
而多 profile 隔离机制是在它写好之后才加的。

**可迁移的教训**:当你事后给系统加一层"环境视图"抽象,必须把**所有**读原始环境的点一起改;
只改用到的、漏掉只有外部扩展会用的那个,等于给扩展作者埋了一个只在生产多租户下才现形的坑。

### 1.6 ANSI 清洗:一处刻意的"不复用"

`agent/secret_sources/base.py:259-265`

```
# ANSI CSI/OSC escape sequences — helper-CLI stderr often carries color
# codes that must not reach Hermes' own startup output.
# NOTE: intentionally NOT migrated to tools.ansi_strip.strip_ansi — the
# optional terminator here (``(?:\x07|\x1b\\)?``) also strips *unterminated*
# OSC sequences (common when a CLI is killed mid-write), which strip_ansi
# leaves untouched. strip_ansi is not a superset of this regex.
_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?)")
```

值得记:**"为什么没复用共享工具"被写成了注释**。被杀在半途的 CLI 会留下未终止的 OSC 序列,
共享的 `strip_ansi` 不管这种;而未终止 OSC 恰恰是最危险的一种(它会吞掉后续输出)。
注意 1Password 侧走的是**另一条路**——它的 `_scrub` 用 `strip_ansi` 再补一刀
`replace("\x1b", "")`。两个后端对同一个威胁给了两种解法,这本身是一处不必要的分叉。

---

## 2. 注册与选择:`registry.py` / `__init__.py`

### 2.1 怎么注册:六道校验,全部只 log 不抛

`register_source()` 依次拒绝:非 `SecretSource` 子类、名字非法、API 版本不符、
`shape` 非法、重名(除非 `replace=True`)、scheme 撞车。

名字校验:

`agent/secret_sources/registry.py:112-115`

```
    name = getattr(source, "name", "") or ""
    if not name or not name.replace("_", "").isalnum() or name != name.lower():
        logger.warning("Ignoring secret source with invalid name %r", name)
        return False
```

scheme 唯一性(这是 `scheme` 字段目前的**全部**实际作用):

`agent/secret_sources/registry.py:132-141`

```
    scheme = getattr(source, "scheme", None)
    if scheme:
        for other_name, other in _SOURCES.items():
            if other_name != name and getattr(other, "scheme", None) == scheme:
                logger.warning(
                    "Ignoring secret source '%s': scheme '%s://' is already "
                    "owned by source '%s'",
                    name, scheme, other_name,
                )
                return False
```

**为什么全部只 log**:注册发生在插件加载期,一个坏插件不得拖垮启动。这是贯穿全文件的姿态。

#### ■-6:名字校验与契约不一致(Unicode)

契约写的是 ASCII 子集:

`agent/secret_sources/base.py:134-136`

```
        name: Config-section key under ``secrets:`` in config.yaml.
            Lowercase ``[a-z0-9_]+``.  Also the provenance label stored
            for every var this source supplies.
```

但 `str.isalnum()` 在 Python 里是 **Unicode 感知**的,`café`、全角 `ｖａｕｌｔ` 都返回 `True`,
且它们的 `.lower()` 等于自身,于是全部通过校验:

> **R11B 更正**:本块的脚本只存在于当轮会话的 scratchpad(原路径含会话标识,已抹去)、**从未落库**,重跑无法复现,因此它不是「shell 命令即证据」意义上的可重跑证据 —— 由 ```verify 改标 ```console。**结论本身不变**,依据仍是块内输出与同节的行号锚点。

```console
cd <scratchpad> && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python repro_name_validation.py
```

```console
'ok_name'    accepted=True
'café'       accepted=True
'ｖａｕｌｔ'      accepted=True
'Ünter'      accepted=False
'my-vault'   accepted=False
'MyVault'    accepted=False
'vault2'     accepted=True
registry keys: ['ok_name', 'café', 'ｖａｕｌｔ', 'vault2']
```

严重度不高但具体:源名同时是 **config 段键**和**溯源标签**(`(from X)` 那个 X 的来源),
全角 `ｖａｕｌｔ` 与 ASCII `vault` 在重名检查里不冲突、在终端里几乎无法区分——
一个同形异码来源可以在"这个 key 来自哪"的展示上冒充另一个。修法是一行正则,
与 `is_valid_env_name` 的纯 ASCII 口径对齐即可。

`agent/secret_sources/base.py:257`

```
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
```

### 2.2 内置源的惰性注册,与它自己违背的不变量

`agent/secret_sources/registry.py:156-165`

```
def _ensure_builtin_sources() -> None:
    """Idempotently register the bundled sources.

    Lazy so importing this module stays cheap and so a broken bundled
    source can never break registration of the others.
    """
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    _BUILTINS_LOADED = True
```

三段各自 try/except 的注册,command 是第三个:

`agent/secret_sources/registry.py:180-186`

```
    try:
        from agent.secret_sources.command import CommandSource

        register_source(CommandSource())
    except Exception:  # noqa: BLE001 — never block startup
        logger.warning("Failed to register bundled command secret source",
                       exc_info=True)
```

#### ■-4:`command` 通过 `bitwarden` 导入,把两者绑死

`agent/secret_sources/command.py:46-48`

```
from agent.secret_sources.base import ErrorKind, SecretSource
from agent.secret_sources.base import get_source_environment
from agent.secret_sources.bitwarden import FetchResult
```

`FetchResult` 的**规范定义在 `base.py`**,上面两行已经在从 `base` 导入了。
第三行绕道 `bitwarden`,而 `bitwarden.py` 顶层有硬第三方导入:

`agent/secret_sources/bitwarden.py:50-52`

```
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
```

于是 bitwarden 模块任何导入期失败都会**连带**让 command 源注册失败,
直接违反上面 docstring 的 "a broken bundled source can never break registration of the others"。
实跑(拦掉 `cryptography` 的导入):

> **R11B 更正**:本块的脚本只存在于当轮会话的 scratchpad(原路径含会话标识,已抹去)、**从未落库**,重跑无法复现,因此它不是「shell 命令即证据」意义上的可重跑证据 —— 由 ```verify 改标 ```console。**结论本身不变**,依据仍是块内输出与同节的行号锚点。

```console
cd <scratchpad> && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python repro_import_coupling.py
```

```console
LOG agent.secret_sources.registry: Failed to register bundled Bitwarden secret source
...
LOG agent.secret_sources.registry: Failed to register bundled command secret source
...
  File "/home/user/hermes-agent/agent/secret_sources/command.py", line 48, in <module>
    from agent.secret_sources.bitwarden import FetchResult
...
registered sources: ['onepassword']
```

**范围说明(不夸大)**:`cryptography` 在 `pyproject.toml` 里是**核心固定依赖**、不是可选 extra,
所以"缺 cryptography"在正常安装里不会发生。缺陷的实质不是这个具体诱因,
而是**隔离结构被一行 import 打穿**:任何未来在 `bitwarden.py` 顶层出现的平台相关导入、
语法错误或坏合并,都会静默拖走一个完全无关的来源,而 try/except 的分段设计本来就是为防这个。
修法零成本:把 `FetchResult` 改从 `base` 导入。

### 2.3 怎么选:顺序 + 启用;未知来源怎么办

`_ordered_enabled_sources()` 的规则:`secrets.sources` 显式列表优先,
没列到的按**注册顺序**补齐;再逐个问源自己的 `is_enabled(cfg)`,抛异常就跳过并 log。

未知名字只 warning、不失败、不阻断:

`agent/secret_sources/registry.py:271-277`

```
        unknown = [e for e in explicit
                   if isinstance(e, str) and e not in _SOURCES]
        if unknown:
            logger.warning(
                "secrets.sources names unknown source(s): %s (known: %s)",
                ", ".join(unknown), ", ".join(_SOURCES) or "none",
            )
```

配合 `secrets` 属于开放字典配置键(见 ◇-2),结论是:**`secrets.` 下任何子键都被配置校验接受**,
拼错一个来源名(`secrets.commmand`)既不会报错也不会生效,只在 `secrets.sources` 里
显式点名时才有这一条 warning。

### 2.4 优先级阶梯:`apply_all()`

形状优先于顺序:

`agent/secret_sources/registry.py:378-381`

```
    # Mapped sources outrank bulk sources regardless of list order:
    # an explicit VAR→ref binding is stronger intent than a project dump.
    ordered = ([s for s in enabled if s.shape == "mapped"]
               + [s for s in enabled if s.shape == "bulk"])
```

**取 phase 与 应用 phase 是分开的**:先把所有源都 fetch 一遍,顺便收集全部
`protected_env_vars` 到一张全局表,**然后**才顺序应用。

`agent/secret_sources/registry.py:386-395`

```
    for source in ordered:
        cfg = secrets_cfg.get(source.name)
        cfg = cfg if isinstance(cfg, dict) else {}
        result = _fetch_with_timeout(source, cfg, home_path, env)
        fetches.append((source, cfg, result))
        try:
            for var in source.protected_env_vars(cfg):
                protected.setdefault(var, source.name)
        except Exception:  # noqa: BLE001
            pass
```

这一步很关键——protected 表是"取"完才完整的,所以保护是**跨源生效**的:
即使 A 源先被应用,B 源声明的 bootstrap token 也已经在表里,A 不可能覆盖它。

守卫链(前半:名字 / 保护 / 已被占):

`agent/secret_sources/registry.py:421-436`

```
        def _try_apply(var: str, value: str, *, is_alias: bool = False) -> bool:
            """Apply one var through the shared guard chain. True = applied."""
            if not is_valid_env_name(var):
                sr.skipped_invalid.append(var)
                return False
            if var in protected:
                sr.skipped_protected.append(var)
                return False
            if var in claimed:
                sr.skipped_claimed.append(var)
                report.conflicts.append(
                    f"{var}: kept value from {claimed[var]}; "
                    f"{source.name} also supplies it (first source wins — "
                    "remove one binding or reorder secrets.sources)"
                )
                return False
```

后半(preserve / 既有值 / 落笔):

`agent/secret_sources/registry.py:437-446`

```
            existed = bool(env.get(var))
            if existed and var in preserve:
                sr.skipped_existing.append(var)
                return False
            if existed and not override:
                sr.skipped_existing.append(var)
                return False
            env[var] = value
            claimed[var] = source.name
            sr.applied.append(var)
```

注意 **`protected` 命中是静默的**——它只进 `sr.skipped_protected`,不进 `report.conflicts`,
而 `env_loader` 的打印循环只打 `applied` / `error` / `warnings` / `conflicts`。
所以"把 `BWS_ACCESS_TOKEN` 也存进 BSM 项目里"这件事会被无声跳过,
文档如实记了这一点(见 §7 对 `bitwarden.md` 的核对),属文档与代码一致。

**取舍**:静默是对的还是错的?好处是不给一个正常配置(把 token 也放进 vault 便于备份)
制造每次启动的噪音;坏处是用户改了 vault 里的 token 值却发现没生效时,没有任何线索。
若要重做,我会把它降为一次性 debug 级日志而不是完全无声。

### 2.5 超时:一次性线程 + ContextVar 的正确用法

`agent/secret_sources/registry.py:213-224`

```
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix=f"secret-src-{source.name}"
    )
    try:
        def _fetch() -> FetchResult:
            token = set_source_environment(environ)
            try:
                return source.fetch(cfg, home_path)
            finally:
                reset_source_environment(token)

        future = executor.submit(_fetch)
```

**细节值得学**:`set_source_environment` 是在 **worker 线程内部**调用的,不是提交前。
`ThreadPoolExecutor` 不会把提交方的 contextvars 复制进 worker,所以只能在里面设——
这是一个很容易写反的地方。

预算超了怎么办:

`agent/secret_sources/registry.py:204-210`

```
    """Run source.fetch() under a wall-clock budget; never raises.

    The budget is enforced with a daemon worker thread: a source that
    blows its budget is reported as ``TIMEOUT`` and its (eventual)
    result is discarded.  The thread itself may linger until process
    exit — acceptable for a startup-only path, and strictly better than
    an unbounded hang on every ``hermes`` invocation.
    """
```

外层预算的默认值与读取口径:

`agent/secret_sources/base.py:195-201`

```
    def fetch_timeout_seconds(self, cfg: dict) -> float:
        """Wall-clock budget the orchestrator enforces around fetch()."""
        try:
            val = float((cfg or {}).get("timeout_seconds", DEFAULT_FETCH_TIMEOUT_SECONDS))
        except (TypeError, ValueError):
            return DEFAULT_FETCH_TIMEOUT_SECONDS
        return val if val > 0 else DEFAULT_FETCH_TIMEOUT_SECONDS
```

默认 120 秒之所以这么宽,是因为首跑可能要下载并校验一个 CLI 二进制:

`agent/secret_sources/base.py:72-75`

```
# Timeout the orchestrator enforces around fetch() when the source's
# config section doesn't override it.  Generous because a first run may
# include a one-time CLI binary auto-install (e.g. bws download+verify).
DEFAULT_FETCH_TIMEOUT_SECONDS = 120.0
```

**未取证的推定**:docstring 说"结果被丢弃",但被丢弃的只是**返回值**;
残留线程若继续跑完 `fetch_bitwarden_secrets`,其内部的磁盘缓存写入
仍会在 `apply_all` 返回之后把密钥落盘。我**没有实跑验证**这条时序,列为推定(见 §9)。

### 2.6 profile 别名

`agent/secret_sources/registry.py:313-315`

```
# Only credential-shaped names get auto-aliased — a random profile-suffixed
# var should not silently hydrate an unsuffixed name.
_ALIAS_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET", "_KEY", "_PASSWORD")
```

profile 名解析:

`agent/secret_sources/registry.py:302-310`

```
    if home_path is not None:
        resolved = Path(home_path)
        if resolved.parent.name == "profiles" and resolved.name:
            return resolved.name
    for env_name in ("HERMES_PROFILE_NAME", "HERMES_PROFILE"):
        value = os.environ.get(env_name, "").strip()
        if value and value != "default":
            return value
    return ""
```

`TELEGRAM_BOT_TOKEN_MILLA` 在 profile `milla` 下同时兑现成 `TELEGRAM_BOT_TOKEN`。
别名走同一条 `_try_apply` 守卫链,且额外要求"任何源直接供给了同名 var"时别名不得遮蔽它。

`agent/secret_sources/registry.py:462-464`

```
            alias = _profile_alias_target(var, profile)
            if alias and alias not in supplied_directly and alias not in claimed:
                if _try_apply(alias, value, is_alias=True):
```

行为规格在 `tests/secret_sources/test_profile_secrets.py` 的
`test_profile_suffixed_var_hydrates_canonical` 与 `test_hyphenated_profile_name_matches_underscore_suffix`。

**小瑕疵**:`_active_profile_name` 的回退分支读 `os.environ` 而不是传入的 `environ`。
在多 profile 水合路径下 `home_path` 必然是 `.../profiles/<name>`,第一分支就返回了,
所以目前打不到。属于同一类"事后加环境视图没改全"的残留,不单列记号。

---

## 3. 缓存:`_cache.py`

### 3.1 缓存键是什么

**两个后端的键形状不同,但共同点是:auth 材料一律先指纹化再进键。**

`agent/secret_sources/bitwarden.py:86-87`

```
_CacheKey = Tuple[str, str, str]  # (access_token_fingerprint, project_id, server_url)
_CACHE: Dict[_CacheKey, _CachedFetch] = {}
```

`agent/secret_sources/onepassword.py:111-116`

```
# In-process cache.  The key folds in str(home_path) so a HERMES_HOME switch
# inside one long-lived process (e.g. the gateway) can't return another
# profile's secrets from L1.  The disk layer omits home from its serialized
# key because the file already lives under the home dir (see _disk_key_str).
_CacheKey = Tuple[str, str, str, str]  # (auth_fp, account, home, refs_fp)
_CACHE: Dict[_CacheKey, CachedFetch] = {}
```

1Password 的 auth 指纹把**所有** `OP_SESSION_*` 一起折进去:

`agent/secret_sources/onepassword.py:186-197`

```
    source_env = get_source_environment()
    parts: List[str] = [
        f"token={source_env.get(token_env, '')}",
        f"account={source_env.get('OP_ACCOUNT', '')}",
        f"connect_host={source_env.get('OP_CONNECT_HOST', '')}",
        f"connect_token={source_env.get('OP_CONNECT_TOKEN', '')}",
    ]
    for key in sorted(source_env):
        if key.startswith("OP_SESSION_"):
            parts.append(f"{key}={source_env[key]}")
    material = "\n".join(parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
```

**为什么这么设计**:换身份必须换键。否则 `op signout` + 换账号登录后,
上一个身份缓存的值会被当成新身份的值发出去——这是最糟的一类缓存 bug
(不是性能问题,是**串号**)。把身份材料指纹化进键,让"失效"变成"键不匹配"这件本来就会发生的事,
比显式失效逻辑可靠得多。

磁盘层则省略 home 维度——因为文件本来就住在 home 底下,路径已经提供了这个维度:

`agent/secret_sources/onepassword.py:121-129`

```
def _disk_key_str(cache_key: _CacheKey) -> str:
    """Serialize a cache key for on-disk storage, omitting home_path.

    The disk file is already partitioned by home (it lives under
    ``<home>/cache/``), so the path provides the home dimension; folding it
    into the key string too would be redundant.
    """
    auth_fp, account, _home, refs_fp = cache_key
    return f"{auth_fp}|{account}|{refs_fp}"
```

### 3.2 缓存会把密钥留在哪:内存 + 磁盘,明文

**会,而且默认就会。** 磁盘层的自我描述:

`agent/secret_sources/_cache.py:97-104`

```
    One JSON object per backend lives at ``<hermes_home>/cache/<basename>``::

        {"key": "<serialized cache key>", "secrets": {...}, "fetched_at": 1.0}

    The file holds only secret *values* keyed by the serialized cache key —
    never raw auth material.  Backends are responsible for fingerprinting
    tokens/sessions *before* they reach ``key_serializer`` so the token can't
    land in the key.
```

**内容是解析后的密钥明文值**,权限 0600,目录 0700。Bitwarden 侧对此有一段很坦白的解释:

`agent/secret_sources/bitwarden.py:94-99`

```
# Layout: one JSON object per cache key, written atomically with mode 0600 in
# <hermes_home>/cache/bws_cache.json. The file holds only the secret VALUES,
# never the access token. It's plaintext-equivalent to ~/.hermes/.env (which
# we already accept) but kept out of the .env file so users editing it won't
# accidentally commit BSM-sourced secrets. The atomic-write/0600/TTL mechanics
# live in agent.secret_sources._cache.DiskCache, shared with the other backends.
```

两个文件名:

`agent/secret_sources/bitwarden.py:100-101`

```
_DISK_CACHE_BASENAME = "bws_cache.json"
_ENCRYPTED_CACHE_BASENAME = "bws_cache.enc.json"
```

`agent/secret_sources/onepassword.py:118`

```
_DISK_CACHE_BASENAME = "op_cache.json"
```

**进程间共享**:磁盘层就是进程间共享——这正是它存在的理由。

`agent/secret_sources/bitwarden.py:89-92`

```
# Disk-persisted cache so back-to-back CLI invocations (e.g. `hermes chat -q ...`
# called from scripts, cron, the gateway forking new agents) don't each pay the
# ~380ms `bws secret list` tax. The in-process _CACHE above only saves repeated
# fetches WITHIN one process; this saves repeated fetches ACROSS processes.
```

内存层 `_CACHE` 是模块级全局 dict,只在进程内共享。

### 3.3 原子写与权限位

`agent/secret_sources/_cache.py:191-200`

```
            # Write to a sibling temp file and atomic-rename.  tempfile honours
            # os.umask, so we explicitly chmod 0600 before the rename.
            fd, tmp = tempfile.mkstemp(
                prefix=self._tmp_prefix, suffix=".tmp", dir=str(cache_dir)
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f)
                os.chmod(tmp, 0o600)
                os.replace(tmp, path)
```

四个细节都是对的,值得逐条记:
1. **`mkstemp` 在目标目录同级**(`dir=str(cache_dir)`)→ `os.replace` 不跨文件系统,保证原子;
2. **先 `chmod 0600` 再 `replace`** → 密钥文件从不曾以宽松权限存在于最终路径;
3. **`mkstemp` 本身就是 0600 创建**,`chmod` 是对 umask 的补刀;
4. 目录 `chmod 0700` 单独做,注释点明 `mkdir` 的 mode 受 umask 影响、不可靠。

`agent/secret_sources/_cache.py:178-185`

```
            cache_dir = path.parent
            cache_dir.mkdir(parents=True, exist_ok=True)
            # mkdir's mode is umask-subject; chmod the dir to 0700 so cache
            # metadata isn't exposed if HERMES_HOME is ever made traversable.
            try:
                os.chmod(cache_dir, 0o700)
            except OSError:
                pass
```

失败处理:整个 `write` 包在 `except OSError: pass` 里,临时文件在任何异常下都被 unlink。
"缓存问题绝不阻断启动"是全模块的姿态:

`agent/secret_sources/_cache.py:16-18`

```
Nothing in this module ever raises out to the caller's hot path: the disk
layer is strictly best-effort (a miss just triggers a refetch), because a
cache problem must never block Hermes startup.
```

### 3.4 TTL 与"关掉缓存"的语义 —— ■-5 / ▲-3

底座的承诺:

`agent/secret_sources/_cache.py:106-111`

```
    Writes are atomic (``mkstemp`` → ``chmod 0600`` → ``os.replace``) and the
    containing ``cache/`` directory is forced to ``0700`` — ``mkdir``'s mode is
    umask-subject, so the chmod is the reliable form.  Both ``read`` and
    ``write`` short-circuit when ``ttl_seconds <= 0``, so setting the TTL to
    zero disables *both* cache layers symmetrically: a user opting out never
    gets secret values written to disk at all.
```

`DiskCache` 自己确实做到了(`read` 与 `write` 开头各一处 `ttl_seconds <= 0` 短路)。
新鲜度判断本身也把 `ttl<=0` 当作"永不新鲜":

`agent/secret_sources/_cache.py:64-67`

```
    def is_fresh(self, ttl_seconds: float) -> bool:
        if ttl_seconds <= 0:
            return False
        return (time.time() - self.fetched_at) < ttl_seconds
```

问题在**内存层由各后端自己管**,而两个后端管法不同。Bitwarden 把 L1 写也用 TTL 门控住了:

`agent/secret_sources/bitwarden.py:615-618`

```
    entry = _CachedFetch(secrets=secrets, fetched_at=time.time())
    if use_cache:
        if cache_ttl_seconds > 0:
            _CACHE[cache_key] = entry
```

1Password 没有:

`agent/secret_sources/onepassword.py:383-386`

```
    if use_cache and not read_errors and secrets:
        entry = CachedFetch(secrets=dict(secrets), fetched_at=time.time())
        _CACHE[cache_key] = entry
        _DISK_CACHE.write(cache_key, entry, cache_ttl_seconds, home_path)
```

实跑对照(同一 `cache_ttl_seconds=0`):

> **R11B 更正**:本块的脚本只存在于当轮会话的 scratchpad(原路径含会话标识,已抹去)、**从未落库**,重跑无法复现,因此它不是「shell 命令即证据」意义上的可重跑证据 —— 由 ```verify 改标 ```console。**结论本身不变**,依据仍是块内输出与同节的行号锚点。

```console
cd <scratchpad> && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python repro_op_ttl0.py
```

```console
op  secrets: {'OPENAI_API_KEY': 'op-secret-value'}
op  L1 _CACHE after ttl=0 fetch: {('c68f975a77821a44', '', '/tmp/hermes-home-tuqd5sog', 'f90eb6f9d420230b'): CachedFetch(secrets={'OPENAI_API_KEY': 'op-secret-value'}, fetched_at=1786254273.1539896)}
op  disk cache file exists: False
bws secrets: {'OPENAI_API_KEY': 'bws-secret-value'}
bws L1 _CACHE after ttl=0 fetch: {}
bws disk cache file exists: False
```

**影响的准确边界(不夸大)**:该条目**不会被取用**,因为读路径永远经过 `is_fresh(ttl)`,
`ttl<=0` 时恒 `False`。实际后果只有两条:
(a) 用户明确关掉缓存后,明文密钥仍被留在一个进程级全局 dict 里直到进程退出;
(b) 与 Bitwarden 行为不一致,同一份文档说辞对两个后端不同真。
理论上"另一个调用方用非 0 TTL 命中同一个键"会真的取到,但在树内不成立:
`fetch_onepassword_secrets` 的树内调用方只有 `onepassword.py` 自身两处与
`hermes_cli/onepassword_secrets_cli.py` 一处,其中 CLI 的 `--apply` 分支硬编码
`cache_ttl_seconds=0` 且不传 `home_path`(键的 home 分量为 `""`),与启动路径的键必然不同。

`hermes_cli/onepassword_secrets_cli.py:396-398`

```
            override_existing=bool(op_cfg.get("override_existing", True)),
            cache_ttl_seconds=0,  # an explicit sync always resolves fresh
        )
```

▲-3 是它的文档面,见 §7。

### 3.5 Bitwarden 的加密缓存(第二套磁盘层)

`bitwarden.py` 另起了一套**不走 `DiskCache`** 的加密缓存:
HKDF-SHA256 从 access token 派生 32 字节密钥,随机 salt/nonce,AES-GCM,
**序列化后的缓存键当 AAD**。

`agent/secret_sources/bitwarden.py:406-416`

```
        salt = os.urandom(16)
        nonce = os.urandom(12)
        serialized_key = _cache_key_str(cache_key)
        key = _derive_encrypted_cache_key(access_token, salt)
        plaintext = json.dumps(
            {"secrets": entry.secrets, "fetched_at": entry.fetched_at},
            separators=(",", ":"),
        ).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(
            nonce, plaintext, serialized_key.encode("utf-8")
        )
```

**设计要点与取舍**:

- 密钥材料就是 bootstrap token 本身 → 没有引入第二个"要存哪"的问题,但也意味着
  **拿到 token 的人本来就能直接查 vault**,加密缓存挡的是"只拿到磁盘、拿不到 token"的场景
  (备份泄露、旧盘、快照)。这是一个诚实且有意义的威胁模型。
- AAD 绑定缓存键 → 把一个 profile/项目的密文挪到另一个位置会解密失败,不是静默串号。
- 写成功后**删掉旧的明文缓存**,即迁移是自动完成的:

`agent/secret_sources/bitwarden.py:432-437`

```
            # A successful encrypted write completes migration; remove the
            # legacy plaintext cache so stale secrets cannot remain on disk.
            try:
                _disk_cache_path(home_path).unlink()
            except FileNotFoundError:
                pass
```

- 代价:`serialized_key` 以**明文**存在 JSON 里,其中含 token 的 64-bit 指纹 + project_id + server_url:

`agent/secret_sources/bitwarden.py:417-423`

```
        payload = {
            "version": _ENCRYPTED_CACHE_VERSION,
            "key": serialized_key,
            "salt": _b64e(salt),
            "nonce": _b64e(nonce),
            "ciphertext": _b64e(ciphertext),
        }
```

  对高熵 token 而言这不构成实际风险,但它确实是一个可离线校验 token 猜测的 oracle,
  值得在重实现时明确知道自己在付这个代价。

陈旧回退只对传输类失败开门:

`agent/secret_sources/bitwarden.py:589-590`

```
        kind = _classify_bws_error(str(exc))
        if use_cache and kind in (ErrorKind.NETWORK, ErrorKind.TIMEOUT):
```

**为什么这条门很重要**:

`agent/secret_sources/bitwarden.py:569-575`

```
        # Live fetch failed. Fall back to a stale disk cache ONLY for
        # transport-level failures (network down, DNS error, transient BWS
        # outage / timeout) — never for AUTH_FAILED or a malformed-output
        # INTERNAL error, where serving old secrets would mask a real
        # config/credential problem the caller needs to see.  Without this
        # fallback a fleet of bots sharing one BWS project all stop working
        # on a single network blip.
```

即:`AUTH_FAILED` 下回退陈旧密钥会**掩盖真实的凭据问题**——用户以为撤销生效了,
实际机器还在用旧 key;而网络抖动下不回退会让"共享一个 BSM 项目的一队机器"同时停摆。
这是 §1.2 那张 `ErrorKind` 词表唯一存在理由的兑现。

---

## 4. 三个来源

### 4.1 Bitwarden(bulk)

#### 4.1.1 鉴权

一个 bootstrap 密钥:`BWS_ACCESS_TOKEN`(名字可由 `access_token_env` 改),
从 per-fetch 环境读,以子进程 env 传给 `bws`。源把它自己钉进 protected 表:

`agent/secret_sources/bitwarden.py:873-877`

```
    def protected_env_vars(self, cfg: dict):
        token_env = "BWS_ACCESS_TOKEN"
        if isinstance(cfg, dict):
            token_env = str(cfg.get("access_token_env") or token_env)
        return frozenset({token_env})
```

于是 vault 里即使存了同名 secret 也覆盖不了它(见 §2.4 的 protected 守卫)。

#### 4.1.2 二进制自安装:本片安全设计做得最好的一段

版本固定、不追 latest:

`agent/secret_sources/bitwarden.py:70-73`

```
# Pinned upstream version.  Bump in a follow-up PR — never auto-resolve
# "latest" because upstream release shape (asset names, CLI flags) is
# allowed to change between majors and we want updates to be deliberate.
_BWS_VERSION = "2.0.0"
```

下载后校验 SHA-256:

`agent/secret_sources/bitwarden.py:247-253`

```
        expected = _expected_sha256(checksum_path, asset_name)
        actual = _sha256_file(zip_path)
        if expected.lower() != actual.lower():
            raise RuntimeError(
                f"Checksum mismatch for {asset_name}: "
                f"expected {expected}, got {actual}"
            )
```

zip-slip 防护(`ZipFile.extract` 本身**不**校验 member 名不逃逸):

`agent/secret_sources/bitwarden.py:341-354`

```
    dest_root = os.path.realpath(dest_dir)
    target = os.path.realpath(os.path.join(dest_root, member))
    # ``commonpath`` raises ValueError for e.g. different drives on
    # Windows; treat that as an escape too.
    try:
        contained = os.path.commonpath([dest_root, target]) == dest_root
    except ValueError:
        contained = False
    if not contained or target == dest_root:
        raise RuntimeError(
            f"Refusing to extract unsafe archive member {member!r}: "
            f"it escapes the extraction directory"
        )
    zf.extract(member, dest_root)
```

落位也是原子的:

`agent/secret_sources/bitwarden.py:263-274`

```
        # Move into place atomically.  We write to a sibling tempfile in
        # the final directory so the rename can't cross filesystems.
        fd, staged = tempfile.mkstemp(dir=str(bin_dir), prefix=".bws_")
        os.close(fd)
        shutil.copy2(extracted, staged)
        os.chmod(
            staged,
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
            | stat.S_IRGRP | stat.S_IXGRP
            | stat.S_IROTH | stat.S_IXOTH,
        )
        os.replace(staged, target)
```

**取舍要看清**:checksum 文件与资产**来自同一个 Release**(同源),
所以这层校验防的是**传输/CDN 损坏与半截下载**,不防"上游 Release 被篡改"。
文档在这点上是诚实的(见 §7 对 `bitwarden.md` 的核对)。
真要防后者需要独立信任锚(仓库内固定 hash 或签名),项目选择了不做——
版本是 PR 里手工 bump 的,等于把信任锚换成了"人工评审 + 固定版本"。

#### 4.1.3 子进程调用

`agent/secret_sources/bitwarden.py:673-682`

```
    source_env = get_source_environment()
    if source_env is os.environ:
        from tools.environments.local import build_subprocess_env

        env = build_subprocess_env(scrub_secrets=False, inherit_profile_home=False)
    else:
        env = dict(source_env)
    env["BWS_ACCESS_TOKEN"] = access_token
    # Make sure we're not echoing telemetry / colour codes into json.
    env.setdefault("NO_COLOR", "1")
```

argv 列表、无 shell、`stdin=DEVNULL`、30 秒超时。stderr 是 Rust color-eyre 的报告块,
`_summarize_bws_stderr` 只留编号的 cause 行、砍掉 `Location:` 之后的噪音,再截 200 字符。

注意 **legacy 单 profile 路径拿的是全环境副本**(`scrub_secrets=False`),
即 `bws` 子进程能看到所有凭据。这与 §1.5 那段 `run_secret_cli` 的承诺是**相反的姿态**,
且是有意为之(注释见上一行的 671-672)。

#### 4.1.4 输出解析

`bws secret list <project> --output json` → 列表,逐项取 `key`/`value`,非法 env 名跳过并 warning:

`agent/secret_sources/bitwarden.py:736-744`

```
        key = item.get("key")
        value = item.get("value")
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if not _is_valid_env_name(key):
            warnings.append(
                f"Skipping secret {key!r}: not a valid env-var name"
            )
            continue
```

即 **BSM 的 secret Name 直接就是环境变量名**——这是 bulk 形状的定义。

### 4.2 1Password(mapped)

#### 4.2.1 鉴权:Hermes 完全不碰

`agent/secret_sources/onepassword.py:23-27`

```
* Authentication is whatever the user's ``op`` CLI already uses — a
  service-account token (``OP_SERVICE_ACCOUNT_TOKEN``) for headless boxes,
  or a desktop/interactive session (``OP_SESSION_*``).  Hermes never
  authenticates on the user's behalf; it shells out to an already-trusted,
  already-authenticated CLI.
```

这是与 Bitwarden 的核心分野:Bitwarden 那边 Hermes 管到了二进制安装与 token 存储,
1Password 这边 Hermes 只做引用解析。

#### 4.2.2 子进程 env:真正的最小白名单

`agent/secret_sources/onepassword.py:81-89`

```
# Env vars the `op` child actually needs.  We build a minimal allowlisted env
# rather than copying all of os.environ (which, post-dotenv, holds every
# provider credential) into the child — tighter blast radius if `op` or
# anything it execs ever misbehaves.  OP_SESSION_* and the token are added
# dynamically in _op_child_env().
_OP_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "USERPROFILE",
```

白名单里还包含 1Password Connect 的两个变量和一个"跳过桌面探测"的开关:

`agent/secret_sources/onepassword.py:99-103`

```
    "OP_CONNECT_HOST",
    "OP_CONNECT_TOKEN",
    # Lets a user skip op's desktop-app integration probe (which can hang with
    # no timeout on a wedged desktop container) and go straight to token auth.
    "OP_LOAD_DESKTOP_APP_SETTINGS",
```

`_op_child_env` 在白名单之外动态加所有 `OP_SESSION_*`,
并把用户配置的 token 变量名**归一化**成 `op` 真正认的名字:

`agent/secret_sources/onepassword.py:249-257`

```
    # Desktop / interactive session credentials.
    for key, val in source_env.items():
        if key.startswith("OP_SESSION_"):
            env[key] = val
    # `op` reads OP_SERVICE_ACCOUNT_TOKEN regardless of which env var the user
    # configured Hermes to source it from, so normalize to that name here.
    if token_value:
        env["OP_SERVICE_ACCOUNT_TOKEN"] = token_value
    env["NO_COLOR"] = "1"
```

`--` 选项终止符:

`agent/secret_sources/onepassword.py:274-279`

```
    cmd: List[str] = [str(op), "read"]
    if account:
        cmd += ["--account", account]
    # `--` terminates option parsing so a reference can never be mis-parsed as
    # an `op` flag even if validation is ever loosened.
    cmd += ["--", reference]
```

注释里 "even if validation is ever loosened" 是这段的精髓:**纵深防御要假设上游校验将来会松**。

#### 4.2.3 空值即失败

`agent/secret_sources/onepassword.py:310-313`

```
    value = (proc.stdout or "").rstrip("\r\n")
    if not value.strip():
        raise RuntimeError(f"op read returned an empty value for {reference!r}")
    return value
```

**为什么值得单列**:`returncode == 0` + 空输出如果被当成成功,会把一个好的 `.env` 凭据
用 `""` 静默覆盖掉,现象是"密钥突然失效但配置看起来全对"。
同一个判断在 command 源里以另一种形式出现:

`agent/secret_sources/command.py:120-123`

```
            # Whitespace-only (e.g. a quoted `K="  "` placeholder) is "no
            # value": it would otherwise flow into an Authorization header
            # → guaranteed 401.
            return value if value.strip() != "" else None
```

这条规则在本簇里被重复了三次(1Password 的空值、command 的空白值、command 的 dotenv 空白值),
可以抽象成设计原则:**"取到空"必须是错误,不能是成功。**

#### 4.2.4 只缓存完整成功的拉取

`fetch_onepassword_secrets` 的写缓存条件里有 `not read_errors`:任一引用失败就整批不缓存。

`agent/secret_sources/onepassword.py:339-340`

```
    Only a complete, error-free pull is cached, so a transient auth failure
    isn't frozen in for the whole TTL window.
```

#### 4.2.5 binary 固定不回落

`agent/secret_sources/onepassword.py:211-223`

```
def find_op(binary_path: str = "") -> Optional[Path]:
    """Resolve a usable ``op`` binary, or None.

    When ``binary_path`` is set it is used verbatim and PATH is NOT consulted
    — pinning an absolute path is a way to avoid trusting whatever ``op`` shows
    up first on ``PATH``.  A pinned-but-missing path returns None (the caller
    surfaces a clear error) rather than silently falling back.
    """
    if binary_path:
        pinned = Path(binary_path)
        if pinned.exists() and os.access(pinned, os.X_OK):
            return pinned
        return None
```

"固定但不存在时返回 None 而不是回落 PATH"——回落会把一个安全加固变成安全降级。

### 4.3 command —— 注入面与信任边界

这是本片被要求重点取证的一段。

#### 4.3.1 它执行什么、由谁提供

`agent/secret_sources/command.py:4-8`

```
``CommandSecretsProvider`` (hermes-desktop ``src/main/secrets/commandProvider.ts``)
to the Python agent.  The helper command (e.g. ``keepassxc-cli``,
``secret-tool``, or a script that cats a tmpfs env file) comes from
``secrets.command`` in ``config.yaml`` — NEVER from ``.env``, which holds
only secret values.
```

命令串的唯一来源是 `config.yaml` 的 `secrets.command.command`:

`agent/secret_sources/command.py:442-453`

```
    def fetch(self, cfg: dict, home_path: Path) -> FetchResult:
        cfg = cfg if isinstance(cfg, dict) else {}
        result = FetchResult()

        command = str(cfg.get("command") or "").strip()
        if not command:
            result.error = (
                "secrets.command.enabled is true but secrets.command.command "
                "is empty.  Set the helper command in config.yaml."
            )
            result.error_kind = ErrorKind.NOT_CONFIGURED
            return result
```

而 `cfg` 是编排器从 `secrets.<name>` 段传下来的(见 §2.4 的 fetch phase),
`secrets` 段由 `env_loader` 的 `_load_secrets_config` 从 `<home>/config.yaml` 读出(见 §1.1)。
**没有环境变量入口、没有远端入口。**

#### 4.3.2 声明的信任模型

`agent/secret_sources/command.py:10-16`

```
Security model (mirrors the TS provider line-for-line where it matters):

* The command string is the USER'S OWN configuration (same trust level as
  the ``.env`` file they control), so it is run via ``/bin/sh -c <command>``.
* The requested key is passed to the child ONLY via the ``HERMES_SECRET_KEY``
  environment variable — it is NEVER interpolated into the shell string, so
  a hostile key name (e.g. ``"; rm -rf ~``) is inert data, not code.
```

`agent/secret_sources/command.py:199-206`

```
        proc = subprocess.Popen(  # noqa: S602 — command is the user's own config
            ["/bin/sh", "-c", command],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # captured and DISCARDED — never inherited
            start_new_session=True,  # so the hard timeout can kill the whole group
        )
```

**"key 只走环境变量、绝不插值进 shell 串"是这段最重要的一条**,而且是可验证的:
命令串是配置的字面量,`HERMES_SECRET_KEY` 是唯一的数据通道,
所以 key 名里的 `;` `$()` `` ` `` 都是惰性数据。
`start_new_session=True` 加上超时时 `killpg`,保证 fork 出子进程的 helper 不会把管道吊着不放:

`agent/secret_sources/command.py:218-225`

```
        # Hard timeout: kill the whole process group (a helper script may
        # have forked children that would otherwise keep the pipe open).
        # POSIX-only by construction: _run_helper early-returns on Windows
        # before ever spawning, so this line can't execute there.
        try:
            os.killpg(os.getpgid(proc.pid), _signal.SIGKILL)  # windows-footgun: ok
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()
```

#### 4.3.3 helper 拿到的环境 —— ◇-3

`agent/secret_sources/command.py:183-196`

```
    # User-configured secret-helper command: runs with the user's full shell
    # env by design (it may need any credential to resolve the secret).
    source_env = get_source_environment()
    if source_env is os.environ:
        # Legacy single-profile startup intentionally preserves the existing
        # helper contract, which may rely on the user's full environment.
        from tools.environments.local import build_subprocess_env
        env = build_subprocess_env(scrub_secrets=False, inherit_profile_home=False)
    else:
        # A multiplex profile must never inherit sibling secrets from the
        # process-global environment.  hydrate_profile_secret_sources seeds
        # only global-safe values plus this profile's own .env.
        env = dict(source_env)
    env["HERMES_SECRET_KEY"] = secret_key
```

`build_subprocess_env(scrub_secrets=False, ...)` 的语义由工厂自己定义:

`tools/environments/local.py:688-692`

```
    * ``scrub_secrets=False`` — preserve the base env content byte-for-byte
      (no key is removed).  Use for children that intentionally receive
      secrets (git credential flows, ``bws``/``op`` secret CLIs) or where
      scrubbing could change behavior.  The site is still a win: it becomes
      grep-able and future-fixable.
```

即**post-dotenv 环境的逐字节副本 —— 每一个 provider 凭据**。

所以 command 源的真实信任边界是:**能写 `config.yaml` 的人 = 能以 Hermes 进程身份
执行任意 shell + 读走全部凭据**。这在"config 是用户自己的"前提下成立;
但它与 §1.5 那段 `run_secret_cli` 明确要防的东西完全相反,而用户文档的 "Security model" 一节
**一条都没提这件事**:

`website/docs/user-guide/secrets/command.md:32-36`

> - The helper command string is YOUR configuration — same trust level as the `.env` file you control.
> - Output is hard-capped at 1 MiB; a runaway helper can't wedge startup (process group killed on timeout).
> - The helper's **stderr is discarded** — vault CLI diagnostics can carry secret material, so they never reach Hermes' output. Failures log structured fields only (exit code / signal / errno), never the command string.
> - Whitespace-only values are treated as "no value" — a placeholder entry never flows into an Authorization header.
> - POSIX-only (needs `/bin/sh`). On Windows the source reports itself unconfigured and startup continues.

五条里最接近的是第一条,但"same trust level as the `.env` file"说的是**命令串的可信度**,
不是"helper 会拿到 `.env` 的全部内容"。这是 ◇-3。

#### 4.3.4 谁能写 `config.yaml`:一处纵深防御的不对称

我按"取凭据这一端有没有约束"的口径查了写入面。**`~/.hermes/config.yaml` 不在 agent 的写禁清单里**,
而 `.env` 与 Bitwarden 的**加密**缓存在:

`agent/file_safety.py:39-43`

```
            # Active profile .env (or top-level .env when not in profile mode).
            str(hermes_home / ".env"),
            # Top-level .env, even when running under a profile — overwriting it
            # leaks credentials across every profile that inherits from root (#15981).
            str(hermes_root / ".env"),
```

`agent/file_safety.py:49-51`

```
            # Bitwarden Secrets Manager encrypted disk cache.
            str(hermes_home / "cache" / "bws_cache.enc.json"),
            str(hermes_root / "cache" / "bws_cache.enc.json"),
```

实跑逐个问 `get_write_denied_error`:

> **R11B 更正**:本块的脚本只存在于当轮会话的 scratchpad(原路径含会话标识,已抹去)、**从未落库**,重跑无法复现,因此它不是「shell 命令即证据」意义上的可重跑证据 —— 由 ```verify 改标 ```console。**结论本身不变**,依据仍是块内输出与同节的行号锚点。

```console
cd <scratchpad> && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python repro_write_deny.py
```

```console
.env                         -> DENIED
.anthropic_oauth.json        -> DENIED
cache/bws_cache.enc.json     -> DENIED
config.yaml                  -> ALLOWED
cache/bws_cache.json         -> ALLOWED
cache/op_cache.json          -> ALLOWED
```

三处不对称,全部指向同一个方向:

1. **`config.yaml` 可写而 `.env` 不可写** —— 但 `config.yaml` 里的 `secrets.command.command`
   会在**下一次启动**被 `/bin/sh -c` 执行,且拿到 `.env` 里的全部内容。
   即"写 config" 是一个延迟兑现的、比"写 .env"更强的原语。
2. **加密缓存写禁、明文缓存不写禁** —— 两个明文缓存装的是同一批密钥的明文。
3. 读侧同样不对称,见 §5.3 的 ■-1。

**必须说清的限定**:守卫自己声明这不是安全边界。

`agent/file_safety.py:217-220`

```
    **This is NOT a security boundary.** The terminal tool runs as the
    same OS user with shell access; the agent can still ``cat auth.json``
    or ``cat ~/.hermes/.env`` and exfiltrate the file. The read-deny exists
    as defense-in-depth that:
```

所以上述三条是**纵深防御层内部的不一致**,不是边界被打穿。
但第 1 条的性质仍值得单独记:防注入的写禁清单保护了"值"(`.env`),却没保护
"下次启动会被当代码跑的那份配置",这在威胁模型上是反的。

**远端能不能写 config?负结论及其搜索面。**
我对全仓 `*.py`(排除 `tests/`)搜 `save_config(` 的全部调用点并逐个看了写入的键路径:
`gateway/config.py`、`gateway/slash_commands.py` 两处(都是 `/model` 切换,只写 `model.*` 子键)、
`hermes_cli/web_routers/tools.py` 四处(写 `<toolset>.enabled`)、
`hermes_cli/main.py` / `memory_setup.py` / `onepassword_secrets_cli.py` / `secrets_cli.py` /
`moa_cmd.py` / `fallback_cmd.py` / `security_advisories.py` 等 CLI 向导、
`agent/monitoring/policy.py`,以及 `tools/approval.py` 一处(只写 `command_allowlist`)。
**没有发现接受任意键路径的写入点**,因此我未能构造"聊天消息 → 设置 `secrets.command.command`"的链路。
搜索面的局限:我只搜了 `save_config(`,没有搜可能存在的其它写 YAML 路径
(如直接调 `atomic_yaml_write`、或插件自带的配置写入),也没有审 `gateway/` 全量。
**按 CLAUDE.md 的负结论规矩,这条只能记为"在上述搜索面内未发现",不作为"不存在"结论。**

#### 4.3.5 输出解析:S2 跨 key 误投防护

这是 `command.py` 里最值得学的一段。helper 的 stdout 支持两种形状(裸值 / dotenv 块),
歧义就出在"一个单独的、key 不匹配的 env 形状行"上。

`agent/secret_sources/command.py:142-158`

```
    # SECURITY (S2): a single env-shaped line for a DIFFERENT key must not
    # be returned as the wanted secret.  A sloppy helper (e.g. `head -1
    # env-file`, or a grep that matched the wrong line) emitting
    # `OTHER_KEY=realvalue` would otherwise flow — key name, '=' and the
    # OTHER key's value — into an Authorization header sent to the WANTED
    # key's endpoint: cross-provider credential leakage, not just a 401.
    # Disambiguation from a bare base64 secret: base64 padding only ever
    # produces an env-shaped line whose "value" part is empty or all '='
    # (`dGVzdA==` → key `dGVzdA`, value `=`), so a non-trivial value part
    # after a non-matching key means a misrouted dotenv entry → None.
    env_shaped = _ENV_LINE.match(value)
    if (
        env_shaped
        and env_shaped.group(1) != wanted_key
        and re.fullmatch(r"=*", env_shaped.group(2).strip()) is None
    ):
        return None
```

**这是本片唯一一处代码里显式写出"密钥会被发去哪"的推理**:
把 A provider 的 key 当成 B provider 的 key 发出去,不是 401,是**跨 provider 凭据泄漏**。
用 base64 padding 只会产出"value 部分全是 `=`"这一事实来消歧,是个漂亮的解法——
它不需要知道密钥格式,只需要知道 `=` 的分布。

配套的"多 key dump 里没有想要的 key 就返回 None"分支同样是防误投:

`agent/secret_sources/command.py:125-133`

```
    # 2. The output is a multi-key dotenv dump that does NOT contain the
    #    wanted key → None, rather than mis-returning an unrelated line as
    #    a bare value.  Only >=2 env-shaped lines count as a dump: a SINGLE
    #    non-matching env-shaped line falls through to the bare-value
    #    branch, because a bare secret can itself match the KEY=VALUE shape
    #    (e.g. base64 with '=' padding, "dGVzdA==") and must not be
    #    misclassified as a dump.
    if len(dotenv_lines) > 1:
        return None
```

#### 4.3.6 两层预算

helper 自己 3 秒、输出上限 1 MiB:

`agent/secret_sources/command.py:59-66`

```
# Hard cap so a hung helper can never wedge startup.  Kept deliberately
# TIGHT (3s) — a configured helper MUST be fast and NON-INTERACTIVE
# (e.g. `keepassxc-cli` against an already-unlocked DB, `secret-tool
# lookup`, or `cat`-ing a tmpfs env file), NOT something that prompts
# for a touch/PIN.
_COMMAND_TIMEOUT_SECONDS = 3.0
# Defensive cap on helper output (1 MiB) — a misbehaving command can't OOM us.
_MAX_OUTPUT_BYTES = 1024 * 1024
```

外层还有编排器的 `timeout_seconds`(默认 120 秒,见 §2.5)。两层预算的键名不同:

`agent/secret_sources/command.py:432-439`

```
            "helper_timeout_seconds": {
                "description": "Hard timeout for one helper run",
                "default": _COMMAND_TIMEOUT_SECONDS,
            },
            "override_existing": {
                "description": "Helper values overwrite .env/shell values",
                "default": False,
            },
```

内层是 `secrets.command.helper_timeout_seconds`,外层是 `secrets.<name>.timeout_seconds`;
用户文档的配置表只列了内层。

注意这里也是 ▲-2 的证据:`CommandSource` **没有**重写 `override_existing`,用的是基类默认。

`agent/secret_sources/base.py:184`

```
        return bool(isinstance(cfg, dict) and cfg.get("override_existing", False))
```

#### 4.3.7 legacy shim:两个已死却仍自称在用的入口

`command.py` 与 `bitwarden.py` 都有 "Public entry point — called from hermes_cli.env_loader"
的章节标题,后者的 docstring 更明写:

`agent/secret_sources/bitwarden.py:767-771`

```
    """Pull secrets from BSM and set them on ``os.environ``.

    This is the function ``load_hermes_dotenv()`` calls after the .env
    files have loaded.  It is intentionally defensive — any failure
    returns a :class:`FetchResult` with ``error`` set; it never raises.
```

实际零调用。搜索面:全仓 `*.py`,排除 `tests/` 与定义所在的 `agent/secret_sources/` 自身:

```verify
cd /home/user/hermes-agent && grep -rn "apply_command_secrets(\|apply_bitwarden_secrets(" --include=*.py . | grep -v "^./tests/" | grep -v "^./agent/secret_sources/"; echo "exit=$?"
```

`apply_onepassword_secrets` 则还活着,调用点在 `hermes_cli/onepassword_secrets_cli.py` 的 `--apply` 分支。

**为什么这不只是"死代码"**:这三个 shim **自己直接写 `os.environ`**,
完全绕开编排器的 protected / claimed / preserve / provenance 全链条;
`apply_bitwarden_secrets` 还用 `os.environ.get` 而不是 per-fetch 视图,即它是 profile 不感知的:

`agent/secret_sources/bitwarden.py:785`

```
    access_token = os.environ.get(access_token_env, "").strip()
```

它们标称"env_loader 在用",谁照着这个标称去"恢复"它们,就会拿到一套无编排的旧语义。

---

## 5. `tools/credential_files.py`:凭据**文件**的透传

### 5.1 它其实不是"凭据落盘那一侧"

**先纠正一个定位。** 本片任务书把它描述为"凭据落盘那一侧",但读完全文件后,
它一行落盘代码都没有——它是**远端沙箱的文件透传注册表**:

`tools/credential_files.py:1-6`

```
"""File passthrough registry for remote terminal backends.

Remote backends (Docker, Modal, SSH) create sandboxes with no host files.
This module ensures that credential files, skill directories, and host-side
cache directories (documents, images, audio, screenshots) are mounted or
synced into those sandboxes so the agent can access them.
```

真正做"凭据落盘 + 权限位 + 原子写"的是 §3.3 的 `_cache.py`。
本文件的安全语义是**另一个方向**:决定哪些宿主机文件可以被搬进沙箱。
它有两个喂入口:skill frontmatter 的 `required_credential_files`,和配置的
`terminal.credential_files`;两者最后合并进同一个 `get_credential_file_mounts()`。

消费者(即"搬到哪去")分布在 `tools/environments/` 下的 `docker.py`(只读 bind mount)、
`modal.py`、`managed_modal.py`、`singularity.py`、`file_sync.py`。
**Modal / Daytona 这类是把文件上传到第三方云**,不是本机 bind mount。

### 5.2 skill 侧的三道闸,以及闸后面的那句话

`tools/credential_files.py:71-83`

```
    Security: rejects absolute paths and path traversal sequences (``..``).
    The resolved host path must remain inside HERMES_HOME so that a malicious
    skill cannot declare ``required_credential_files: ['../../.ssh/id_rsa']``
    and exfiltrate sensitive host files into a container sandbox.

    Containment alone is not sufficient, because HERMES_HOME is exactly where
    the MASTER credential stores live. A skill legitimately needs its own
    service token (``google_token.json``); it never needs ``.env`` (every
    provider key), ``auth.json`` (all provider tokens and OAuth grants),
    ``mcp-tokens/`` or the Bitwarden plaintext cache. Those are refused via
    the canonical read deny-list (``agent.file_safety.get_read_block_error``)
    — the same guard that stops the agent reading them with ``read_file``, so
    the mount surface cannot hand a skill what the read surface denies it.
```

三道闸:绝对路径拒、`validate_within_dir` 包含性、读禁清单且**失败关闭**。第三道的实现:

`tools/credential_files.py:129-143`

```
    try:
        denied = get_read_block_error(str(resolved))
    except Exception:
        logger.exception(
            "credential_files: refusing %r — read guard raised", relative_path
        )
        return False
    if denied:
        logger.warning(
            "credential_files: refused %r — it is a credential store the agent "
            "is denied from reading; a skill may mount its own service token, "
            "not the master key files",
            relative_path,
        )
        return False
```

关键那句话是:**"the mount surface cannot hand a skill what the read surface denies it"**——
即挂载面的判据完全外包给读禁清单。这个设计很聪明(单一判据、不重复维护),
但它把挂载面的安全性**完全绑定在读禁清单的完备性上**。下面两条 ■ 都是这个绑定的代价。

### 5.3 ■-1:`op_cache.json` 不在读禁清单里,于是可被挂进沙箱

读禁清单的凭据文件名列表:

`agent/file_safety.py:274-285`

```
    credential_file_names = (
        "auth.json",
        "auth.lock",
        ".anthropic_oauth.json",
        ".env",
        "webhook_subscriptions.json",
        os.path.join("auth", "google_oauth.json"),
        # Bitwarden Secrets Manager disk cache: stores plaintext secret values
        # to avoid re-fetching across back-to-back CLI invocations. The file
        # was introduced by #31968 but not added to this guard.
        os.path.join("cache", "bws_cache.json"),
    )
```

**`cache/op_cache.json` 不在里面。** 而它与 `bws_cache.json` 是同一个 `DiskCache` 类写出的、
同一种 JSON 形状、同样装解析后密钥明文的文件,默认 `cache_ttl_seconds: 300` 即默认会被写出。

后果有两层,第二层才是重点:

> **R11B 更正**:本块的脚本只存在于当轮会话的 scratchpad(原路径含会话标识,已抹去)、**从未落库**,重跑无法复现,因此它不是「shell 命令即证据」意义上的可重跑证据 —— 由 ```verify 改标 ```console。**结论本身不变**,依据仍是块内输出与同节的行号锚点。

```console
cd <scratchpad> && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python repro_op_cache_guard.py
```

```console
credential_files: refused 'cache/bws_cache.json' — it is a credential store the agent is denied from reading; a skill may mount its own service token, not the master key files
cache/bws_cache.json       read_blocked=True  skill_mountable=False
cache/op_cache.json        read_blocked=False skill_mountable=True
mounts: [{'host_path': '/tmp/hermes-home-vgq_s2m_/.hermes/cache/op_cache.json', 'container_path': '/root/.hermes/cache/op_cache.json'}]
```

(a) agent 可以直接 `read_file ~/.hermes/cache/op_cache.json` 读走全部 1Password 解析出的 provider key;
(b) 更重要的是,**一条 skill frontmatter `required_credential_files: [cache/op_cache.json]`
就能把它挂进远端沙箱**——正是 §5.2 那段 docstring 与其用例宣称要挡住的东西。
用例文件 `tests/tools/test_credential_files.py` 的 `TestMasterCredentialStores` 类
把 `cache/bws_cache.json` 参数化进去了,但没有 `op_cache.json`,所以这个洞是绿的。

**这个洞的形状本身就是证据**:上面那段清单里白纸黑字写着
"The file was introduced by #31968 but **not added to this guard**"——
Bitwarden 缓存当年犯过一模一样的错、修了、还留了注释;1Password 缓存后来加进来时,
**同一个错误原样重演了一遍**。一个"新增缓存文件要同步进禁清单"的约定,
如果只靠人记住,就会按这个周期复发。

### 5.4 ■-2:配置侧完全没走禁清单

`tools/credential_files.py:191-208`

```
            for item in cred_files:
                if isinstance(item, str) and item.strip():
                    rel = item.strip()
                    if os.path.isabs(rel):
                        logger.warning(
                            "credential_files: rejected absolute config path %r", rel,
                        )
                        continue
                    host_path = hermes_home / rel
                    containment_error = validate_within_dir(host_path, hermes_home)
                    if containment_error:
                        logger.warning(
                            "credential_files: rejected config path traversal %r (%s)",
                            rel, containment_error,
                        )
                        continue
                    resolved_path = host_path.resolve()
                    if resolved_path.is_file():
```

绝对路径 ✓、穿越 ✓、**禁清单 ✗**。而 `get_credential_file_mounts()` 把两条来源合并成同一张挂载表:

`tools/credential_files.py:227-239`

```
    mounts: Dict[str, str] = {}

    # Skill-registered files
    for container_path, host_path in _get_registered().items():
        # Re-check existence (file may have been deleted since registration)
        if Path(host_path).is_file():
            mounts[container_path] = host_path

    # Config-based files
    for entry in _load_config_files():
        cp = entry["container_path"]
        if cp not in mounts and Path(entry["host_path"]).is_file():
            mounts[cp] = entry["host_path"]
```

实跑对照:

> **R11B 更正**:本块的脚本只存在于当轮会话的 scratchpad(原路径含会话标识,已抹去)、**从未落库**,重跑无法复现,因此它不是「shell 命令即证据」意义上的可重跑证据 —— 由 ```verify 改标 ```console。**结论本身不变**,依据仍是块内输出与同节的行号锚点。

```console
cd <scratchpad> && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python repro_credfiles.py
```

```console
--- skill path (register_credential_file) ---
credential_files: refused '.env' — it is a credential store the agent is denied from reading; a skill may mount its own service token, not the master key files
  register_credential_file('.env') -> False
credential_files: refused 'auth.json' — it is a credential store the agent is denied from reading; a skill may mount its own service token, not the master key files
  register_credential_file('auth.json') -> False
--- config path (terminal.credential_files) ---
  MOUNTED: {'host_path': '/tmp/hermes-home-71y5d2y7/.hermes/.env', 'container_path': '/root/.hermes/.env'}
  MOUNTED: {'host_path': '/tmp/hermes-home-71y5d2y7/.hermes/auth.json', 'container_path': '/root/.hermes/auth.json'}
```

**同一个 `.env`,同一张挂载表,一条路拒、一条路过,而且过的那条没有任何提示。**

**要不要判成缺陷?我的判断是要,理由三条,但也把反面写出来:**
反面理由是"配置是用户自己的意图",与 command 源的信任模型一致。但:

1. 用户文档介绍 `terminal.credential_files` 时**没有任何**"这条路绕过 master-store 守卫"的提示:

`website/docs/user-guide/security.md:569`

> Paths are relative to `~/.hermes/`. Files are mounted to `/root/.hermes/` inside the container. This list is read by `tools/credential_files.py` (`terminal.credential_files`) — it lives under the `terminal:` block but is loaded by the credential-files module, not the core terminal backend, so it isn't part of the bundled `DEFAULT_CONFIG` snapshot.

2. 用例只覆盖了配置侧的穿越与绝对路径(`tests/tools/test_credential_files.py` 的
   `TestConfigCredentialFiles`),禁清单一条都没有,说明这不是"权衡后放行",
   更像是"加守卫时只改了一处";
3. 目的地包含 **Modal / Daytona 这类第三方云**,把 `.env` 静默上传上去的后果
   与 bind mount 到本机容器不是一个量级。

### 5.5 其余机制(记要)

会话级注册表用 `ContextVar`,理由是防网关流水线里的跨会话串数据:

`tools/credential_files.py:38-50`

```
# Session-scoped list of credential files to mount.
# Backed by ContextVar to prevent cross-session data bleed in the gateway pipeline.
_registered_files_var: ContextVar[Dict[str, str]] = ContextVar("_registered_files")


def _get_registered() -> Dict[str, str]:
    """Get or create the registered credential files dict for the current context/session."""
    try:
        return _registered_files_var.get()
    except LookupError:
        val: Dict[str, str] = {}
        _registered_files_var.set(val)
        return val
```

而配置侧是**进程级只加载一次**的模块全局:

`tools/credential_files.py:53-54`

```
# Cache for config-based file list (loaded once per process).
_config_files: List[Dict[str, str]] | None = None
```

**两种生命周期共存在一个文件里,是个容易踩的坑**:改了 config.yaml 不重启不生效,
而 skill 注册表却是会话级刷新的。

symlink 处理:bind mount 会跟随符号链接,所以检测到 skills 树里有 symlink 时**整树复制**
到临时目录(只复制常规文件),没有 symlink 时零开销直接返回原目录——
"常见路径零成本、危险路径付成本"的好例子:

`tools/credential_files.py:295-301`

```
def _safe_skills_path(skills_dir: Path) -> str:
    """Return *skills_dir* if symlink-free, else a sanitized temp copy."""
    global _safe_skills_tempdir

    symlinks = [p for p in skills_dir.rglob("*") if p.is_symlink()]
    if not symlinks:
        return str(skills_dir)
```

路径翻译只在 Docker 后端做,其余后端原样返回:

`tools/credential_files.py:488-493`

```
    # Only Docker backend requires translation at this time.  Other backends
    # (Modal, Daytona, Vercel) use different mount semantics and will be
    # addressed separately if needed.  Backend is identified by TERMINAL_ENV
    # (same env var tools/terminal_tool.py reads in _get_environment_config).
    if os.environ.get("TERMINAL_ENV", "local") != "docker":
        return host_path
```

---

## 6. 核心问题:取回的密钥,有没有对"发往何处"的约束?

### 6.1 结论

**没有。secret source 层对"这个密钥会被发去哪"零约束,而且它在结构上无法有。**

三条证据。

**(1) 这 8 个文件里不存在任何 URL / 主机校验。**
搜索面:对 `agent/secret_sources/*.py` 加 `tools/credential_files.py` 搜
`https?://` / `urlparse` / `hostname` / `netloc` / `allowed_hosts`(忽略大小写),
再排除掉文档链接(`docs.`、`github.com`、`1password.com`、`bitwarden.com|eu`)后**零命中**:

```verify
cd /home/user/hermes-agent && grep -rniE 'https?://|urlparse|hostname|netloc|allowed_hosts' agent/secret_sources/*.py tools/credential_files.py | grep -viE 'docs?\.|github\.com|1password\.com|bitwarden\.(com|eu)' | wc -l
```

对照 R9B 红线里 `hermes_cli/auth.py` 的 `_NOUS_PORTAL_ALLOWED_HOSTS`,本簇里**没有任何同类结构**。

**(2) 结构上做不到。** 契约的产物是一个环境变量名到值的映射:

`agent/secret_sources/base.py:112-117`

```
    secrets: Dict[str, str] = field(default_factory=dict)
    applied: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None
    error_kind: Optional[ErrorKind] = None
```

密钥一旦进了 `os.environ`,它与"该发给哪个 endpoint"的关联就彻底断了:
`OPENAI_API_KEY` 会被谁读、发往哪个 `base_url`,是 provider / credential_pool 层的事,
本簇既不知道也无从表达。**这是 mapped 与 bulk 两种形状共同的语义天花板:
它们绑定的是 `ENV_VAR ← ref`,不是 `ENV_VAR → endpoint`。**

**(3) 唯一一处涉及"发往何处"的代码,是把 bootstrap 凭据往外发,且完全不校验。**
Bitwarden 的 `server_url` 从配置逐字进子进程环境:

`agent/secret_sources/bitwarden.py:683-689`

```
    # Region / self-hosted support.  bws defaults to https://vault.bitwarden.com
    # (US Cloud); EU Cloud users need https://vault.bitwarden.eu, and
    # self-hosted users need their own URL.  When unset, fall back to whatever
    # BWS_SERVER_URL the caller already had in their shell env (preserved by
    # the copy above) so manual overrides keep working too.
    if server_url:
        env["BWS_SERVER_URL"] = server_url
```

来源链上没有任何 scheme 或主机校验。适配器侧只做 `strip()`:

`agent/secret_sources/bitwarden.py:965`

```
                server_url=str(cfg.get("server_url", "") or "").strip(),
```

向导侧的四条取值路径(`--server-url` 旗标 → `BWS_SERVER_URL` 环境变量 → 已有配置值 → 交互菜单)
同样一处都不校验:

`hermes_cli/secrets_cli.py:687-695`

```
    if args.server_url and args.server_url.strip():
        return args.server_url.strip()

    env_url = os.environ.get("BWS_SERVER_URL", "").strip()
    if env_url:
        console.print(
            f"  Detected [cyan]BWS_SERVER_URL[/cyan]={env_url} in your shell — using it."
        )
        return env_url
```

也就是说 `server_url: http://attacker.example` 会让 `BWS_ACCESS_TOKEN`
(能读走整个 BSM 项目的 bearer)以明文 HTTP 发到该主机。

### 6.2 与 R9B 那两条 ■ 的同异 —— 我认为这是不同型,不应并案

R9B 的形状是:凭据被发往一个**未经主机校验的 URL**,而 URL 的来源不是用户直接书写的配置。
本簇这条的形状是:URL 就是用户在向导里亲手选/填的自建服务器地址,**配置即意图**。
两者的差别不在"有没有校验",而在"URL 由谁提供"。

我仍然认为值得记一笔,理由只有一条,且是可辩驳的:
**同一仓库已经建立了"凭据出站前查主机白名单"的模式,而这里连最低成本的
`scheme == "https"` 提示都没有。** 自建 Bitwarden 用 `http://` 是合法需求,所以白名单不合适;
但"非 https 时打一行 warning"是零风险的,而现在连这个都没有——
用户把 `https` 敲成 `http` 不会得到任何提示。
我把它记为**设计缺口而非 ■**,因为它需要产品判断,不是明确的实现错误。

### 6.3 1Password 侧的对照

1Password 完全没有这个面:endpoint 由用户已认证的 `op` CLI 自己决定,
Hermes 只透传 `OP_CONNECT_HOST` / `OP_CONNECT_TOKEN`,而且是**从环境变量透传,不从 config.yaml 取**
(见 §4.2.2 的白名单)。这实际上是一个更好的姿态:
Hermes 不成为"密钥发往何处"这个决定的持有者。

---

## 7. 文档与代码的出入

### ▲-1:内置源到底是两个还是三个

`website/docs/user-guide/secrets/index.md:50`

> The bundled set is deliberately closed (same policy as memory providers): Bitwarden and 1Password ship in-tree. Everything else — Infisical, Proton Pass, HashiCorp Vault, AWS Secrets Manager, OS keystores — belongs in plugin repos; share them in the Nous Research Discord (`#plugins-skills-and-skins`).

代码里内置注册的是**三个**(见 §2.2 的第三段注册),`CommandSource` 是完整的一等来源。
**同一份文档第 9 行自己就把 command 列为 supported**:

`website/docs/user-guide/secrets/index.md:9`

> - [Command helper](./command) — any CLI vault (`keepassxc-cli`, `secret-tool`, `pass`, custom scripts) via a user-configured helper that prints `KEY=VALUE` lines.

开发者指南也说对了三个:

`website/docs/developer-guide/secret-source-plugin.md:9`

> Secret sources resolve provider credentials from an external secret manager (a vault, a password manager, an OS keystore, a custom script) into environment variables at process startup — after `~/.hermes/.env` loads, before Hermes reads credentials. Bitwarden, 1Password, and a generic command-helper source ship in-tree; **every other backend is a plugin**. This guide covers building one.

按 CLAUDE.md 的规矩,我把这条断言**连同整句**一起判:该句讲的是"内置集合封闭 + 内置成员是谁",
前半成立、后半("Bitwarden and 1Password")与代码矛盾。判 ▲。

同一处腐烂在包门面的 docstring 里更严重——它把 command 说成"未来可能的例外":

`agent/secret_sources/__init__.py:25-30`

```
The bundled set is deliberately closed (policy mirrors memory
providers): new third-party secret managers ship as standalone plugin
repos that subclass ``SecretSource`` and register through
``PluginContext.register_secret_source()`` — they are NOT added to this
package.  A generic ``command`` source is a possible future exception;
OS keystores (Keychain/DPAPI/libsecret) are under discussion.
```

`registry.py` 的模块 docstring 也停留在更早的时点("1Password once it lands"):

`agent/secret_sources/registry.py:22-25`

```
:func:`_ensure_builtin_sources` — the set of bundled sources is
deliberately closed (Bitwarden, and 1Password once it lands); new
third-party backends ship as standalone plugin repos implementing
:class:`agent.secret_sources.base.SecretSource`.
```

这两处是模块 docstring 不是 website/docs,按项目记号定义不计入 ▲ 计数,
但它们证明这是**同一处腐烂的三个站点**,且腐烂方向一致:command 源加进来时没人回头改说明。

### ▲-2:"both bundled sources default `True`"

`website/docs/developer-guide/secret-source-plugin.md:109`

> | `override_existing(cfg)` | `cfg.get("override_existing", False)` | You want a different default (both bundled sources default `True` for rotation) |

同一份文档第 9 行说内置有三个。第三个 `CommandSource` **没有**重写 `override_existing`,
因此用基类默认 `False`(见 §4.3.6 的两个证据块),用户文档也如实写了 `false`。
所以 "both bundled sources default True" 在它自己的口径下就不成立。判 ▲。

### ▲-3:1Password 缓存"读写都关"

`website/docs/user-guide/secrets/onepassword.md:154`

> - is fully disabled — reads *and* writes — when `cache_ttl_seconds: 0`.

§3.4 已实跑证明:`cache_ttl_seconds=0` 时磁盘层读写确实都关,但**进程内层的写没关**,
明文密钥仍进模块级 `_CACHE`。该节开头明确把缓存定义为 in-process 加 on-disk 两层:

`website/docs/user-guide/secrets/onepassword.md:149`

> Successful, complete pulls are cached in-process and on disk under `<hermes_home>/cache/op_cache.json` (written atomically, mode `0600`), so back-to-back short-lived `hermes` invocations don't re-shell `op` for every reference. The cache:

所以那句"reads *and* writes"涵盖两层。判 ▲。

注意同文件配置表那一行是**对的**,不要一起判:

`website/docs/user-guide/secrets/onepassword.md:130`

> | `cache_ttl_seconds` | `300` | How long resolved values are reused (in-process and on disk). Set to `0` to disable **both** cache layers — no values are written to disk at all. |

它的 "written" 只落在 disk 上,字面为真。

### ◇-1:多 profile 环境视图,插件指南只字未提

`get_source_environment()` 是插件后端读 bootstrap token 的**唯一正确方式**(§1.4),
三个内置源都用了它。但 `secret-source-plugin.md` 全文没有出现过这个名字,
它的示例反而教读者读 `os.environ`:

`website/docs/developer-guide/secret-source-plugin.md:61`

> `        token = os.environ.get("MYVAULT_TOKEN", "").strip()`

同一份指南把 `run_secret_cli()` 立为必用件:

`website/docs/developer-guide/secret-source-plugin.md:117`

> If your backend shells out to a CLI, use the shared helper instead of `subprocess.run` directly. It gives you the audited posture for free: argv-only (no `shell=True`), a **minimal allowlisted child environment** (by the time sources run, `os.environ` holds every credential Hermes knows — never hand that to a child process), `NO_COLOR` + ANSI-scrubbed stderr, stdin closed, timeout → clean `RuntimeError`. Pass user-supplied reference strings after a `--` terminator in your argv so they can never parse as flags.

后果:照这份指南写出来的插件在 multiplex profile 下会读错 profile(或读不到)。
配合 ■-3(推荐的 `run_secret_cli` 自己也读 `os.environ`),**指南给出的两条路径都是错的**。

### ◇-2:`secrets` 段有四个键不在 `DEFAULT_CONFIG` 里

`DEFAULT_CONFIG["secrets"]` 只有 `bitwarden` 与 `onepassword` 两个子段,`sources` 是注释掉的:

`hermes_cli/config_defaults.py:2883-2885`

```
        # Example: sources: [onepassword, bitwarden]
        # "sources": [],
        "bitwarden": {
```

而代码/文档里在用的还有 `secrets.command.*`、`secrets.preserve_existing`、
`secrets.profile_alias`、`secrets.<name>.timeout_seconds`。用脚本确认 `secrets` 段只有两个子段:

```verify
cd /home/user/hermes-agent && awk 'NR>=2875 && NR<=2954' hermes_cli/config_defaults.py | grep -nE '^\s{8}"[a-z_]+": \{'
```

它们能用,是因为 `secrets` 被登记为开放字典键:

`hermes_cli/config.py:4654-4667`

```
_OPEN_DICT_TOP_LEVEL_KEYS = frozenset({
    "providers",
    "credential_pool_strategies",
    "mcp_servers",
    "hooks",
    "quick_commands",
    "personalities",
    "command_allowlist",
    "model_catalog",
    "channel_prompts",
    "server_actions",
    "secrets",
    "goals",
})
```

**取舍**:开放字典是为了让插件源不必改核心就能有配置段——这个目的成立。
代价是 `secrets.` 下的**任何**拼写错误都被静默接受,包括
`secrets.commmand.command`(源永远不启用、零提示)。

### ◇-3 / ◇-4

见 §4.3.3 与 §1.3。

### 关于 `bitwarden.md` 与 `command.md` 的一致性核对(无出入)

两处容易出错的地方核下来都**与代码一致**,记在这里以免后续轮次重复怀疑:

`website/docs/user-guide/secrets/bitwarden.md:145`

> - Hermes will refuse to let Bitwarden overwrite the bootstrap token itself, even with `override_existing: true`. If you store `BWS_ACCESS_TOKEN` as a secret inside the project, it's silently skipped during apply.

"silently skipped" 与 §2.4 的 protected 静默路径完全对上。

`website/docs/user-guide/secrets/bitwarden.md:146`

> - The `bws` binary download is verified against the published SHA-256 checksum from the same GitHub release. Mismatch aborts the install.

"from the same GitHub release" 如实交代了同源校验的局限,不夸大成"防篡改"。

### 没有 ◎

我逐条核了 `index.md` / `bitwarden.md` / `onepassword.md` / `command.md` /
`secret-source-plugin.md` 里可量化的断言(内置源数量、别名后缀 5 个、输出上限 1 MiB、
pin 的 bws 版本 2.0.0、protected 是否静默、`--` 终止符、空值不应用、
checksum 同源、`binary_path` 不回落 PATH),要么与代码一致,要么已列入 ▲。
**没有出现"字面为真但显著保守"的形态,故本片 ◎ 为 0。**

---

## 8. 测试:作为行为规格

### 8.1 环境

- venv:`/home/user/hermes-venv`,`site-packages/*.dist-info` 计数 **87**
  (与 CLAUDE.md 记录的 R8B 基线一致,本片**未安装任何包**)。
- 所有命令带 `HERMES_DISABLE_LAZY_INSTALLS=1`。
- 容器:root 运行、无 IPv6、离线。

```verify
ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l
```

### 8.2 读数

| 批次 | 文件数 | passed | failed |
|---|---|---|---|
| `tests/secret_sources/` 全目录 | 3 | 42 | 0 |
| bitwarden / onepassword / command / credential_file_permissions / env_loader_secret_sources | 5 | 64 | 0 |
| `tests/tools/test_credential_files.py` 与 `tests/skills/test_google_workspace_credential_files.py` | 2 | 39 | 0 |
| **合计** | **10** | **145** | **0** |

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/secret_sources/
```

**零失败,故无需逐条诊断根因。** 特别记一条与容器限制有关的预期:
`tests/test_credential_file_permissions.py` 在 root 下**通过**——它断言的是写出文件的
**mode 位**(`0600`),而不是 root 能否读被 `chmod 000` 的文件,所以不受 root 影响。
(会被 root 打败的是"拒绝读不可读文件"这类断言,本片测试里没有。)

### 8.3 值得当规格读的几个用例

**`tests/secret_sources/conformance.py`** —— 给插件作者的一致性套件,它的选取原则值得抄:

`tests/secret_sources/conformance.py:15-18`

```
The checks encode the parts of the contract that break OTHER people
when violated: never raising, never prompting (stdin closed), respecting
disabled config, valid identity attributes, and orchestrator
compatibility.
```

具体检查里最有代表性的是拿 5 种畸形 cfg 灌进去:

`tests/secret_sources/conformance.py:69-77`

```
    def test_fetch_never_raises_on_malformed_config(self, source, tmp_path):
        """Every degenerate config shape must produce a FetchResult, not a raise."""
        for cfg in ({}, {"enabled": True}, {"enabled": True, "env": "not-a-dict"},
                    {"enabled": True, "cache_ttl_seconds": "bogus"}, None):
            result = source.fetch(cfg if isinstance(cfg, dict) else {}, tmp_path)
            assert isinstance(result, FetchResult), (
                f"fetch() returned {type(result).__name__} for cfg={cfg!r}"
            )
```

**`tests/secret_sources/test_profile_secrets.py`** —— 断言注入空环境时
`get_source_environment()` 看不到进程全局的 canary:

`tests/secret_sources/test_profile_secrets.py:157-173`

```
def test_empty_injected_environment_does_not_fall_back_to_process(monkeypatch, tmp_path):
    from agent.secret_sources.base import get_source_environment

    class _CanarySource(SecretSource):
        name = "canary"
        shape = "mapped"

        def fetch(self, cfg, home_path):
            result = FetchResult()
            assert get_source_environment().get("LEAK_CANARY") is None
            return result

    registry.register_source(_CanarySource())
    monkeypatch.setenv("LEAK_CANARY", "global-secret")
    registry.apply_all(
        {"canary": {"enabled": True}}, tmp_path, environ={}
    )
```

**这正是 ■-3 绕过的那条不变量**,只是它测的是 `fetch()` 内部,
没测 `run_secret_cli` 起出来的子进程。

**`tests/tools/test_credential_files.py`** —— master-store 拒绝的参数化清单,是 ■-1 的直接对照:

`tests/tools/test_credential_files.py:496-506`

```
    @pytest.mark.parametrize(
        "rel_path",
        [
            ".env",
            "auth.json",
            ".anthropic_oauth.json",
            "webhook_subscriptions.json",
            "cache/bws_cache.json",
            "mcp-tokens/srv.json",
        ],
    )
```

缺 `cache/op_cache.json`。

### 8.4 基线洁净

跑完全部测试后确认工作区干净(`test_durations.json` 被 `.gitignore` 忽略):

```verify
cd /home/user/hermes-agent && git status --porcelain; echo "exit=$?"; git rev-parse HEAD
```

---

## 9. 未取证 / 推定 / 留给后续

按 CLAUDE.md 的移交项格式,每条给**锚点文件 + 一句话现象**。

1. **【推定,未实跑】超时残留线程仍会落盘。**
   锚点:`agent/secret_sources/registry.py:204-210` 的 docstring 说超时后
   "its (eventual) result is discarded"。现象:被丢弃的只是返回值;残留线程若跑完
   `fetch_bitwarden_secrets`,其内部的 `_DISK_CACHE.write` 仍会在 `apply_all` 返回之后
   把密钥写进磁盘缓存。我**没有构造慢 fetch 实跑验证**这条时序。

2. **【未取证】`run_secret_cli` 的 `SYSTEMROOT` 大小写。**
   锚点:`agent/secret_sources/base.py:305` 用 `"SYSTEMROOT"`,
   `agent/secret_sources/onepassword.py:94` 用 `"SystemRoot"`。
   现象:Windows 的 `os.environ` 大小写不敏感,但 per-fetch 视图是普通 `dict`、大小写敏感,
   两处取法在多 profile Windows 下可能行为不同。本容器是 Linux,**未验证**。

3. **【未取证】`_get_registered()` 的 ContextVar 语义。**
   锚点:`tools/credential_files.py:43-50` —— `_registered_files_var.set(val)`
   写在惰性初始化里。现象:在一个已退出的 context 里首次调用会把 dict 设进那个 context,
   外层看不到;是否在网关实际调用序列里发生,**未追**。

4. **【未取证】`terminal.credential_files` 的进程级缓存何时失效。**
   锚点:`tools/credential_files.py:53-54` —— `_config_files` 只加载一次。
   现象:长活网关里改 config.yaml 后新挂载不生效,需重启;是否有别处主动重置它,**未搜**。

5. **【搜索面有限的负结论】没有找到接受任意键路径的 config 写入点。**
   见 §4.3.4 末尾,搜索面与局限已写在那里。**不作为"不存在"结论。**

6. **【未审】`hermes_cli/secrets_cli.py` 与 `hermes_cli/onepassword_secrets_cli.py` 全文。**
   本片只按需读了 Bitwarden 的 `server_url` 解析与 1Password `--apply` 的 TTL。
   这两个文件不在本片 8 文件内,其 token 落盘逻辑(写 `.env` 的权限位、原子性)**未审**
   ——那才是真正的"凭据落盘那一侧",建议后续轮次单独覆盖。

7. **【建议主线实跑复核】** 排在最前的两条:
   - **■-1**(`repro_op_cache_guard.py`):它同时打穿读面与挂载面,且目的地可能是第三方云;
     复核成本 5 秒。
   - **■-3**(`repro_run_secret_cli.py`):它是"官方推荐给所有插件作者的安全助手"本身出错,
     影响面随插件生态放大,且现有用例结构上抓不到。

---

## 10. 自校验读数

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent notes/r9c-raw-secret-sources.md
```

实测输出(交付时,逐字):

```console
citations=127  OK=121  UNCHECKED=6
可校验比例 OK/127 = 95.3%
table_anchors=13  UNCHECKED=13   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
OK: every code-block-backed citation matches the baseline
```

| 指标 | 值 |
|---|---|
| citations | 127 |
| OK | 121 |
| UNCHECKED | 6 |
| 可校验比例 | **95.3%**(下限 70%) |
| MISMATCH | 0 |
| BLOCK-DRIFT | 0 |
| TABLE-DRIFT | 0 |
| TABLE-OUT-OF-RANGE | 0 |
| MISSING-FILE | 0 |
| 退出码 | **0** |

(脚本对计数为 0 的阻断类别不打印行,故上面四类在输出里不出现即为 0;
`table_anchors=13` 全部是 UNCHECKED,不是 DRIFT/OUT-OF-RANGE,不阻断。)
