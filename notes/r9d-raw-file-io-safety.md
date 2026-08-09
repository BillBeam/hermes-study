# r9d-B 片 · 文件读写与安全 —— agent 碰用户磁盘的全部入口

> **溯源约定**:凡对 hermes-agent 行为的断言,锚点写成 `路径:行号 @ 863e313`,**单独成行、置于代码块之前**。
> 三个反引号围栏 = 基线源码逐字摘录;`>` 引用块 = 文档摘录;```text/console/verify``` = 作者声明的非源码
> (命令、实验输出、示意代码)。
>
> **本片文件清单(7 文件 / 6,488 行,全部读完)**
>
> | 文件 | 行数 | 角色 |
> |---|---|---|
> | `agent/file_safety.py` | 693 | 准入判定层:写禁清单 / 读禁清单 / 跨 profile 与 sandbox 镜像软护栏 |
> | `tools/file_operations.py` | 2805 | **后端层**:把读/写/patch/search 全部表达成 shell 命令,跨 7 种终端后端 |
> | `tools/file_tools.py` | 2319 | **工具层**:路径解析、守卫编排、去重/循环检测/陈旧检测、JSON 结果、schema 注册 |
> | `tools/read_extract.py` | 346 | 结构化文档抽文本(.ipynb/.docx/.xlsx + 可选 anydoc 扩展) |
> | `tools/working_diff.py` | 130 | 工作区 git diff 采集(`/diff` 斜杠命令的共享实现) |
> | `tools/read_preview_tool.py` | 98 | 桌面 GUI 预览面板读取(纯 schema + 回调转发) |
> | `tools/open_preview_tool.py` | 97 | 桌面 GUI 预览面板打开(纯 schema + 事件发射) |
>
> 术语锚定(首次出现):
> **denylist(禁清单)** = 一张"永不允许"的路径表;
> **defense-in-depth(纵深防御)** = 不是边界、只是多加一道能被绕过的提示;
> **atomic write(原子写)** = 先写临时文件再 `mv` 覆盖,保证读者要么看到旧内容要么看到新内容,不会看到半截;
> **lost update(丢失更新)** = A 读了文件,B 改了文件,A 再写回,B 的改动被无声抹掉;
> **BOM** = UTF-8 文件开头那 3 个不可见字节 `EF BB BF`,Windows 编辑器常加;
> **V4A patch** = 一种 `*** Update File:` / `-旧行` / `+新行` 的多文件补丁文本格式。

---

## 1. 这一片解决什么问题(先场景)

一次具体的走法。用户说"把 `config/app.yaml` 里的超时从 30 改成 60"。模型发出:

```text
patch(mode="replace", path="config/app.yaml", old_string="timeout: 30", new_string="timeout: 60")
```

在这一次调用里,这一片要依次回答**七个互不相关的问题**:

1. `config/app.yaml` 这个相对路径,相对于**谁**?进程 cwd?终端 `cd` 后的 cwd?git worktree 的根?
   (答:`file_tools._resolve_base_dir`,四级回退,答案必须是绝对路径)
2. 这个路径允许写吗?(答:`agent/file_safety` 的写禁清单 + `file_tools._check_sensitive_path`)
3. 这是不是另一个 profile / 容器镜像目录的文件,写了等于写给别人?(答:三个软护栏)
4. 文件在磁盘上是 CRLF 吗?有 BOM 吗?模型给的是裸 LF、没 BOM —— 直接写会**静默改掉整个文件的字节签名**
5. `timeout: 30` 在文件里到底在哪?模型抄的缩进可能差两格(答:`fuzzy_match` 九种策略)
6. 写的时候崩了怎么办?(答:同目录 `mktemp` + `mv` 原子替换)
7. 从模型上次读到现在,别人改过这个文件吗?(答:`file_state.check_stale`,**只警告不阻断**)

`file_operations.py` 与 `file_tools.py` 的关系就是这七问的分工线,**它们不是两套重复实现**:

- `tools/file_tools.py` = **工具层**。负责第 1、2、3、7 问,以及一切"面向模型"的事情:
  把结果 JSON 化、脱敏、限长、去重、检测模型陷入重复读循环、注册 tool schema。
- `tools/file_operations.py` = **后端层**。负责第 4、5、6 问,以及一切"面向文件系统"的事情。
  它的核心洞见写在模块 docstring 里:所有文件操作都能表达成 shell 命令,于是只要终端后端
  有 `execute()`,同一套文件 API 就能同时服务 local / docker / ssh / singularity / modal /
  daytona / vercel_sandbox 七种后端。

`tools/file_tools.py:1249 @ 863e313`

```python
    file_ops = ShellFileOperations(terminal_env)
```

**全仓只有这一处构造 `ShellFileOperations`**(搜索面:`grep -rn "ShellFileOperations(" --include=*.py .`
覆盖基线全部 `.py`,含 `tests/`;命中 3 处,其中 `tools/file_operations.py:16` 是 docstring 用例、
`:803` 是 class 定义,唯一真实构造点是上面这一行)。所以工具层是后端层的**唯一入口**,
这一点是后面所有"守卫装在哪一层"讨论的前提。

---

## 2. 逐文件 / 逐机制精读

### 2.1 `agent/file_safety.py` —— 准入判定层

这个文件里其实有**五张互不相同的表**,分别管五件事。搞清楚"哪张表管哪件事"是理解这一片的钥匙。

#### 2.1.1 写禁清单:精确路径 + 目录前缀

`agent/file_safety.py:28 @ 863e313`

```python
def build_write_denied_paths(home: str) -> set[str]:
    """Return exact sensitive paths that must never be written."""
    hermes_home = _hermes_home_path()
    hermes_root = _hermes_root_path()
    return {
        os.path.realpath(p)
        for p in [
            os.path.join(home, ".ssh", "authorized_keys"),
            os.path.join(home, ".ssh", "id_rsa"),
            os.path.join(home, ".ssh", "id_ed25519"),
            os.path.join(home, ".ssh", "config"),
```

设计要点(为什么这么写):

- **`os.path.realpath` 归一化**:清单里存的是解析完符号链接的真路径,判定时
  (`agent/file_safety.py:104 @ 863e313`)也对入参做 `realpath`,所以
  "建一个 `notes.txt -> ~/.ssh/id_rsa` 的软链再写它"这条绕过口在写侧是堵死的。
- **profile 与 root 双写**:同一个逻辑文件要登记两次(`hermes_home / ".env"` 与 `hermes_root / ".env"`)。
  理由写在注释里 —— 在 profile 模式下 `HERMES_HOME` 指向 `<root>/profiles/<name>`,
  但顶层 `.env` 仍然被所有继承 root 的 profile 读到,只堵一个等于没堵。

`agent/file_safety.py:39 @ 863e313`

```python
            # Active profile .env (or top-level .env when not in profile mode).
            str(hermes_home / ".env"),
            # Top-level .env, even when running under a profile — overwriting it
            # leaks credentials across every profile that inherits from root (#15981).
            str(hermes_root / ".env"),
```

目录前缀表用 `os.sep` 结尾拼接,再用 `startswith` 判定:

`agent/file_safety.py:64 @ 863e313`

```python
def build_write_denied_prefixes(home: str) -> list[str]:
    """Return sensitive directory prefixes that must never be written."""
    return [
        os.path.realpath(p) + os.sep
```

`+ os.sep` 是关键细节:没有它,`~/.sshfoo/` 会被误判成 `~/.ssh` 的子路径。

#### 2.1.2 应用状态保护:会话与 state.db

写禁分类函数里有一段专门保护"应用自有状态",理由是**generic 文件工具改写 state.db 等于伪造对话历史**:

`agent/file_safety.py:123 @ 863e313`

```python
    for base_real in hermes_dirs:
        # Session transcripts are application-owned state.  Letting the agent's
        # generic file tools rewrite state.db or legacy JSON snapshots can
        # falsify conversation history and invalidate resume/compression state.
        try:
            if resolved == os.path.realpath(os.path.join(base_real, "state.db")):
                return True
            sessions_real = os.path.realpath(os.path.join(base_real, "sessions"))
            if resolved == sessions_real or resolved.startswith(sessions_real + os.sep):
                return True
```

**这里有一个类型缺陷(■-6,详见第 4 节)**:函数签名是 `-> Optional[str]`
(`agent/file_safety.py:101 @ 863e313`),只允许返回 `'credential'` / `'safe_root'` / `None`,
但这两个分支返回了 `True`。功能上 `is_write_denied` 仍为真(非 None),
但 `get_write_denied_error` 会走到最后一行,把 state.db 报成
"is a protected system/credential file" —— 措辞错位。实跑复现:

```console
_classify_write_denial(state.db) -> True
get_write_denied_error(state.db) -> Write denied: '<HH>/state.db' is a protected system/credential file.
```

#### 2.1.3 `HERMES_WRITE_SAFE_ROOT` 白名单沙箱

第三张表是"可选的写沙箱":设了这个环境变量后,**只有**变量列出的前缀下可写。

`agent/file_safety.py:148 @ 863e313`

```python
    safe_roots = get_safe_write_roots()
    if safe_roots:
        allowed = False
        for safe_root in safe_roots:
            if resolved == safe_root or resolved.startswith(safe_root + os.sep):
                allowed = True
                break
        if not allowed:
            return "safe_root"
```

**顺序是设计**:凭据清单在前(`:106`-`:110`),safe_root 在后。所以把 safe_root 指向 `$HOME`
也不能写 `~/.ssh/id_rsa` —— 凭据判定先返回了。实跑复现:

```verify
# 需要基线在 PYTHONPATH 上;HERMES_WRITE_SAFE_ROOT 指向一个临时目录 $WS
HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_WRITE_SAFE_ROOT="$WS" \
  /home/user/hermes-venv/bin/python -c '
import sys; sys.path.insert(0,"/home/user/hermes-agent")
from agent.file_safety import get_write_denied_error
print(get_write_denied_error("/tmp/x"))
print(get_write_denied_error(__import__("os").path.expanduser("~/.ssh/id_rsa")))'
```

输出(实跑):

```console
Write denied: '/tmp/x' is outside HERMES_WRITE_SAFE_ROOT (<WS>). Unset the variable or add this path's directory prefix.
Write denied: '/root/.ssh/id_rsa' is a protected system/credential file.
```

两条报错措辞不同,这是**给模型的可区分信号**:一条是"改环境变量或换目录",另一条是"别碰"。

#### 2.1.4 读禁清单 —— 与写禁清单**不是同一张表**

这是本片最重要的结构发现。读侧的表是另一份,写在 `get_read_block_error` 里:

`agent/file_safety.py:274 @ 863e313`

```python
    credential_file_names = (
        "auth.json",
        "auth.lock",
        ".anthropic_oauth.json",
        ".env",
        "webhook_subscriptions.json",
        os.path.join("auth", "google_oauth.json"),
```

`agent/file_safety.py:281 @ 863e313`

```python
        # Bitwarden Secrets Manager disk cache: stores plaintext secret values
        # to avoid re-fetching across back-to-back CLI invocations. The file
        # was introduced by #31968 but not added to this guard.
        os.path.join("cache", "bws_cache.json"),
    )
```

外加三类:`skills/.hub`(prompt 注入载体)、`mcp-tokens/` 目录前缀、
以及**任意位置**的项目级 `.env` 家族按 basename 匹配:

`agent/file_safety.py:329 @ 863e313`

```python
    if resolved.name.lower() in _BLOCKED_PROJECT_ENV_BASENAMES:
```

读侧同样先 `resolve()`,所以软链会被穿透:

`agent/file_safety.py:239 @ 863e313`

```python
    resolved = Path(path).expanduser().resolve()
```

**模块自己把定位说得很清楚 —— 这不是安全边界**:

`agent/file_safety.py:217 @ 863e313`

```python
    **This is NOT a security boundary.** The terminal tool runs as the
    same OS user with shell access; the agent can still ``cat auth.json``
    or ``cat ~/.hermes/.env`` and exfiltrate the file. The read-deny exists
    as defense-in-depth that:
```

这一段是整片的定调,后面所有 ■ 都要放在这个语境里读:它们不是"边界被攻破",
而是"这道纵深防御在自己声明的范围内漏了"。

#### 2.1.5 两张表的实测对照(本片最核心的一张表)

读禁与写禁**完全不是同一张表**,而且交集小得出乎意料。下面是实跑结果(方法见第 3.2 节),
`HERMES_HOME = HERMES_ROOT = 临时目录`:

| 文件(相对 HERMES_HOME) | 读被挡? | 写被挡? | 说明 |
|---|---|---|---|
| `auth.json` | ✅ | ❌ | **主凭据库,可写不可读**(■-1) |
| `auth.lock` | ✅ | ❌ | 同上 |
| `webhook_subscriptions.json` | ✅ | ❌ | HMAC 密钥 |
| `auth/google_oauth.json` | ✅ | ❌ | |
| `cache/bws_cache.json` | ✅ | ❌ | Bitwarden **明文**缓存 |
| `cache/bws_cache.enc.json` | ❌ | ✅ | Bitwarden **加密**缓存,与上一行**正好相反** |
| `cache/op_cache.json` | ❌ | ❌ | 1Password **明文**缓存,**两侧都没有**(■-2) |
| `.env` | ✅ | ✅ | 唯一两侧都挡的凭据文件 |
| `.anthropic_oauth.json` | ✅ | ✅ | |
| `mcp-tokens/x.json` | ✅ | ✅ | |
| `state.db` / `sessions/*` / `pairing/*` | ❌ | ✅ | 应用状态:可读不可写 |
| `config.yaml` / `credentials` / `google_token.json` | ❌ | ❌ | 见下 |
| `~/.ssh/id_rsa`、`~/.netrc`、`~/.git-credentials`、`~/.aws/*`、`~/.npmrc` | ❌ | ✅ | **OS 凭据:可读不可写** |

值得单独说的两点:

1. `bws_cache.json`(明文)只在读侧,`bws_cache.enc.json`(加密)只在写侧 —— 呈交叉形。
   把"明文缓存"写进读禁、把"加密缓存"写进写禁,各自都讲得通,但合起来的效果是:
   **加密文件的内容可以被模型直接读出来,明文文件可以被模型覆盖掉**。
2. `~/.ssh/id_rsa` 这一类 OS 凭据全部**只在写侧**。也就是说 `read_file ~/.ssh/id_rsa`
   是允许的(内容只经过 `redact_sensitive_text` 脱敏)。这在"terminal 反正能 `cat`"的框架下
   自洽,但和 `website/docs/user-guide/security.md` 把 `~/.ssh/` 列在
   "Protected paths"表里的读者印象不一致 —— 那张表明确只讲 write,所以**不算 ▲**,
   只是读者容易误读的地方。

#### 2.1.6 第四、五张表:跨 profile 与 sandbox 镜像软护栏

这两张表挡的不是"安全",而是"写错地方"。

**跨 profile**:profile 是 `<root>/profiles/<name>/` 下的独立 HERMES_HOME,
每个有自己的 `skills/ plugins/ cron/ memories/`。在 A profile 下写 B profile 的 skills,
影响的是用户在另一个 shell 里的会话。

`agent/file_safety.py:389 @ 863e313`

```python
PROFILE_SCOPED_AREAS = ("skills", "plugins", "cron", "memories")
```

注释里记了这条护栏的来历(2026 年 5 月的事故):

`agent/file_safety.py:380 @ 863e313`

```python
# Reference: May 2026 incident where a hermes-security profile session
# edited skills under both ``~/.hermes/profiles/hermes-security/skills/``
# AND ``~/.hermes/skills/`` (the default profile's skills) without realizing
# the second path belonged to a different profile.
```

**sandbox 镜像**(#32049)分两种形态,所以有两个检测器:

- **宿主侧**:路径里还带着完整的 `…/sandboxes/<backend>/<task>/home/.hermes/…` 前缀,
  纯形状匹配即可:

`agent/file_safety.py:540 @ 863e313`

```python
    for i, part in enumerate(parts):
        if part != "sandboxes":
            continue
        # Need at least: sandboxes / <backend> / <task> / home / .hermes / <thing>
        if i + 5 >= len(parts):
            continue
        if parts[i + 3] == "home" and parts[i + 4] == ".hermes":
            return i + 4
```

- **容器内侧**:bind mount 把前缀吃掉了,agent 看到的是干净的 `/root/.hermes/…`,
  形状检测无能为力,只能由调用方把镜像前缀**声明**进来:

`agent/file_safety.py:651 @ 863e313`

```python
    if not mirror_prefix:
        return None
```

声明方在工具层:

`tools/file_tools.py:734 @ 863e313`

```python
    if config.get("env_type") == "docker" and config.get("container_persistent", True):
        return "/root/.hermes"
```

这个设计值得记:**当"路径形状"这个纯函数式信号被环境抹掉时,只能让上层把上下文注入下来**;
两个检测器共用一个 bypass kwarg(`cross_profile=True`),避免给模型两套逃生口令。

设计上这两张表都是**软**护栏 —— 返回一个警告字符串,调用方决定是拒绝还是放行。
工具层选择的是**拒绝**(返回 `tool_error`),要求模型显式带 `cross_profile=True` 重试:

`tools/file_tools.py:1771 @ 863e313`

```python
    if not cross_profile:
        cross_warning = _check_cross_profile_path(path, task_id)
        if cross_warning:
            return tool_error(cross_warning)
```

### 2.2 `tools/file_tools.py` —— 工具层

#### 2.2.1 路径解析:四级回退,结果必须绝对

这是全文件最费笔墨的一段,因为它修的是一个真实的、隐蔽的事故类:
**git worktree 会话里的相对路径落到了主 checkout**。

`tools/file_tools.py:333 @ 863e313`

```python
    root = _authoritative_workspace_root(task_id)
    if container_paths is None:
        container_paths = _uses_container_paths(task_id)
    if root:
        base_text = _expand_tilde(root)
    else:
        base_text = os.getcwd()
```

回退顺序(`_authoritative_workspace_root`,`tools/file_tools.py:272 @ 863e313`):
① 会话自己的 cwd 记录(每条终端命令跑完都会写) → ② 注册的 task/session cwd override
(TUI/Desktop/ACP 在任何工具跑之前登记) → ③ 哨兵过滤后的绝对 `$TERMINAL_CWD` → ④ 进程 cwd。

**哨兵集合是这段设计的精髓**:

`tools/file_tools.py:166 @ 863e313`

```python
_TERMINAL_CWD_SENTINELS = frozenset({"", ".", "./", "auto", "cwd"})
```

一份过时的 `.env` 里留着字面量 `"."`,如果当成真的相对基准,`Path.resolve()` 就会
悄悄把它锚到**进程** cwd —— 这正是 worktree 事故的形状。所以代码选择**直接拒绝**
哨兵与相对值,宁可退到进程 cwd(至少是确定性的),也不接受一个含义取决于运行时的锚。

`tools/file_tools.py:225 @ 863e313`

```python
def _sentinel_free_abs_cwd(raw: str | None) -> str | None:
```

容器后端走另一条分支:**不能 `resolve()`**,因为宿主侧的 `/workspace` 可能是个符号链接,
解析后送进 Docker 就变成了容器里不存在的路径:

`tools/file_tools.py:215 @ 863e313`

```python
def _normalize_without_host_deref(path: str | Path | PurePosixPath) -> PurePosixPath:
    """Normalize path syntax without following host symlinks.

    Container backends use paths that are meaningful inside the sandbox. Calling
    ``Path.resolve()`` on the host can dereference a host-side symlink such as
    ``/workspace`` and rewrite the path before Docker sees it.
    """
    return PurePosixPath(posixpath.normpath(str(path)))
```

**这里有一个可推导的后果(未实测,见第 5 节)**:容器后端下路径不做符号链接解析,
而读禁判定(`get_read_block_error`)自己会 `resolve()` —— 在宿主进程里解析容器路径,
两边指的不是同一个文件系统。软链绕过读禁在容器模式下**大概率成立**,但我没有 Docker 环境实测。

解析不出问题时还会额外给一条"工作区发散"警告:

`tools/file_tools.py:430 @ 863e313`

```python
        except ValueError:
            return (
                f"Relative path {filepath!r} resolved to {str(resolved)!r}, which is "
                f"OUTSIDE the active workspace ({str(root)!r}). The edit will land in "
                f"a different directory than the terminal's cwd. If this is not "
                f"intended (e.g. a git-worktree session writing into the main "
                f"checkout), pass an absolute path under the workspace instead."
            )
```

#### 2.2.2 设备路径守卫:纯路径判定 + 逐跳软链检查

读一个 `/dev/urandom` 会永远读不到 EOF,读 `/dev/stdin` 会阻塞。所以有一张设备黑名单,
**先查字面路径**(这样 `/dev/stdin` 在它被解析成 tty 具体路径之前就被拦),再逐跳查软链,
最后查 realpath:

`tools/file_tools.py:551 @ 863e313`

```python
def _is_blocked_device(filepath: str, base_dir: str | Path | None = None) -> bool:
    """Return True if the path would hang the process (infinite output or blocking input).

    Check the literal path first so aliases like /dev/stdin are caught before
    they resolve to terminal-specific paths. Then check each symlink hop before
    the final resolved path so aliases to devices cannot bypass the guard.
    """
```

`tools/file_tools.py:565 @ 863e313`

```python
    seen: set[str] = set()
    current = normalized
    for _ in range(20):
        try:
            target = os.readlink(current)
        except OSError:
            break
```

20 跳上限 + `seen` 集合 = 防软链环。这张表还顺手承担了一部分**信息泄露**防护:

`tools/file_tools.py:525 @ 863e313`

```python
    # /proc/*/environ, /proc/*/cmdline, /proc/*/maps (and the maps variants
    # smaps, smaps_rollup, numa_maps) can leak secrets, command-line args, and
    # memory layout (ASLR bypass) from the host process (issue #4427).
```

实跑确认(见第 3.2 节 exp2):`/dev/urandom` 与 `/proc/self/environ` 都返回
`Cannot read '...': this is a device file that would block or produce infinite output.`
—— 注意 `/proc/self/environ` 其实不是"会阻塞",报错措辞与真实原因(防泄露)不符,属措辞复用。

#### 2.2.3 读路径的守卫顺序 —— 顺序本身是设计

`read_file_tool` 的守卫顺序是:**设备守卫 → 路径解析 → 结构化文档抽取 → 二进制扩展名守卫 →
读禁清单 → 负结果缓存 → 去重 → 真正读**。

`tools/file_tools.py:1356 @ 863e313`

```python
        block_error = get_read_block_error(str(_resolved))
        if block_error:
            return tool_error(block_error)
```

**为什么抽取要排在二进制守卫前面**:`.docx` / `.xlsx` 本身就在 `BINARY_EXTENSIONS` 里
(`tools/binary_extensions.py:20 @ 863e313`):

```python
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
```

如果二进制守卫先跑,Word/Excel 永远读不了。所以抽取必须抢在它前面。

**但这也把抽取排到了读禁清单前面** —— 一个 `.hub` 缓存目录下的、或任何禁清单覆盖的
`.ipynb/.docx/.xlsx/.pdf` 会**先被完整读进内存并抽成文本**,再被禁清单拦下。
当前禁清单里的具体条目都不是可抽取扩展名,所以现在不可利用;但这是一个**排序上的隐患**
(◇-3,见第 4 节)。

传给禁清单的是**已解析的绝对路径**,注释解释了为什么必须这样:

`tools/file_tools.py:1352 @ 863e313`

```python
        # already-resolved path so a relative-path read against
        # TERMINAL_CWD == HERMES_HOME (e.g. "auth.json") still hits the
        # denylist — get_read_block_error's own resolve() runs against
        # the Python process cwd, which can differ.
```

同一条约定在 `file_safety` 侧也写了一遍(`agent/file_safety.py:232 @ 863e313`),
两边呼应 —— 这是"同一判据两处实现"时**唯一正确**的做法:把契约写在两边都能看见的地方。

#### 2.2.4 大文件:三层截断,各管各的

1. **行数**:`limit`,上限来自 `tool_output.max_lines` 配置,默认 `MAX_LINES = 2000`
2. **单行长度**:`get_max_line_length()`,超长行截断并追加 `... [truncated]`
3. **总字符预算**:`_get_max_read_chars()`,默认 100,000 字符

第 3 层是后加的,理由写得很好:早先的做法是**硬拒绝**整次读,模型只能猜一个更小的 `limit`
再来一轮,那一轮什么都没换到。现在改成"截到最后一个完整行 + 给出 `next_offset`":

`tools/file_tools.py:87 @ 863e313`

```python
def _truncate_to_char_budget(content: str, max_chars: int) -> tuple[str, int, bool]:
    """Trim line-numbered ``read_file`` content to fit a char budget.

    Ported in spirit from nearai/ironclaw#5029 (dual line/byte cap on
    ``read_file``). Where hermes previously hard-rejected an oversized read
    (forcing the model to guess a smaller ``limit`` and burn a round-trip
    returning nothing), this trims the content to the last *complete line*
    that fits within ``max_chars`` and reports how many lines were kept so
    the caller can offer a ``next_offset`` continuation.
```

还有一个诚实的边界处理:如果**第一行**就超预算,就在码点边界切,并且明确告诉模型
"这一行剩下的部分用 offset 取不回来":

`tools/file_tools.py:1480 @ 863e313`

```python
            if len(trimmed.split("\n", 1)[0]) >= max_chars:
                result_dict["hint"] += (
                    " Note: the first line alone exceeded the budget and was "
                    "clamped mid-line; its remainder is not retrievable via "
                    "offset."
                )
```

实跑验证(240 KB / 3000 行文件):返回 `truncated_by: "bytes"`, `next_offset: 1176`。

**第四层是死的**:后端层还有一个 `MAX_FILE_SIZE = 50 * 1024`,但分支体是 `pass`:

`tools/file_operations.py:1174 @ 863e313`

```python
        # Check if file is too large
        if file_size > MAX_FILE_SIZE:
            # Still try to read, but warn
            pass
```

注释说"warn",代码里没有任何 warn(■-7)。

#### 2.2.5 重复读检测:三重机制

模型陷入"反复读同一段"的循环是真实存在的失败模式,这里叠了三层:

1. **内容去重**:`(resolved_path, offset, limit) → mtime`,mtime 没变就返回一个不含内容的存根
2. **存根循环计数**:同一个 key 连续吃到 2 次存根后**硬阻断**
3. **连续调用计数**:同一次调用连续 4 次直接阻断,3 次给警告;任何**别的**工具调用都会清零

`tools/file_tools.py:1603 @ 863e313`

```python
def notify_other_tool_call(task_id: str = "default"):
    """Reset consecutive read/search counter for a task.

    Called by the tool dispatcher (model_tools.py) whenever a tool OTHER
    than read_file / search_files is executed.  This ensures we only warn
    or block on *truly consecutive* repeated reads — if the agent does
    anything else in between (write, patch, terminal, etc.) the counter
    resets and the next read is treated as fresh.
    """
```

配套的一个**反污染**守卫很有意思:去重存根的那句提示文字如果被模型回抄进 `write_file`,
就会把用户的文件写成一句状态文本。于是写侧专门认这个形状:

`tools/file_tools.py:1031 @ 863e313`

```python
    if stripped == _READ_DEDUP_STATUS_MESSAGE:
        return True
    if _READ_DEDUP_STATUS_MESSAGE in stripped and \
            len(stripped) <= 2 * len(_READ_DEDUP_STATUS_MESSAGE):
        return True
```

同源的还有"模型把带行号的 `34|foo` 显示格式回写进文件"这一类:

`tools/file_tools.py:1039 @ 863e313`

```python
def _looks_like_read_file_line_numbered_content(content: str) -> bool:
    """Return True for content dominated by read_file's ``LINE_NUM|CONTENT`` display.

    ``read_file`` intentionally returns line-numbered text to the model. If
    that display format is echoed into ``write_file``, config/source files are
    silently corrupted with prefixes like `` 1|``.  We reject writes where the
    non-empty lines are mostly consecutive read_file-style numbered lines, while
    allowing sparse literal pipe content such as a single ``1|value`` line.
    """
```

判据是"≥60% 的非空行是编号行 **且** 编号基本连续",避免误伤合法的 `1|value` 单行数据。
**这是一条很值得抄的设计原则**:凡是工具向模型输出的"显示格式",都要在输入侧准备一条
"这不是文件内容"的识别器 —— 因为模型一定会有某次把它当成内容回传。

#### 2.2.6 陈旧检测与并发

三个信号,优先级明确:

`tools/file_tools.py:1805 @ 863e313`

```python
        with file_state.lock_path(_resolved):
            # Cross-agent staleness wins over per-task warning when both
            # fire — its message names the sibling subagent.
            cross_warning = file_state.check_stale(task_id, _resolved)
            stale_warning = _check_file_staleness(path, task_id)
```

- `file_state.check_stale`(跨 agent,能点名是哪个兄弟子代理写的)
- `_check_file_staleness`(本 task 的 mtime 比对)
- `_path_resolution_warning`(工作区发散)

锁是**每路径一把**、只在进程内(`tools/file_state.py` 的 `FileStateRegistry`),
包住 read→modify→write 临界区。

**关键的设计取舍:检测到陈旧不阻断,只警告,而且警告是贴在写完之后的结果里。**
实跑证据(exp3 E/F):

```console
E) write after external edit -> _warning = <ws>/race.txt was modified since you last read it on disk (external edit or unrecorded writer). Re-rea
   disk now = 'v3-AGENT\n'          # 外部写入的 'v2-EXTERNAL' 已被抹掉
F) patch after external edit -> warning = <ws>/race2.txt was modified since you last read it on disk ...
   disk now = 'ALPHA\nEXTERNAL\n'   # patch 命中的是新内容,外部改动保住了
```

即:**`write_file` 会丢失更新,`patch` 不会**。原因是 patch 的"锚"是 `old_string` 的内容匹配,
天然是一次乐观并发检查;而 `write_file` 是整文件覆盖,没有任何版本条件。
这直接回答了任务问的第 (e) 问:**编辑工具的契约不是"先读后写"的强制,而是
"内容锚定(patch)+ 事后告知(write_file)"**。想要真正的 lost-update 防护,
必须自己走 patch,或者把 `check_stale` 的返回值改成阻断。

并发覆盖实测(6 线程同时 `write_file` 同一路径,各写 2000 行):

```console
D) concurrent 6 writers -> errors: []
   file homogeneous? True  distinct: ['5']
```

**没有撕裂**(原子 rename 生效),**最后一个写者赢**(无隔离)。这是 `_atomic_write` 的准确
语义:保证原子性,不保证串行化。

### 2.3 `tools/file_operations.py` —— 后端层

#### 2.3.1 原子写:一段被反复加固的 shell 脚本

这是全片最精巧、也最脆的一段。整个写操作被压缩成**一条** shell 脚本、内容走 stdin:

`tools/file_operations.py:999 @ 863e313`

```python
    def _atomic_write(self, path: str, content: str) -> "ExecuteResult":
        """Write ``content`` to ``path`` atomically via temp-file + rename.

        Streams ``content`` over stdin into a temp file in the SAME
        directory as ``path`` (so the final ``mv`` is a real rename on the
        same filesystem, not a non-atomic cross-device copy), preserves the
        existing file's mode if it exists, then renames over the target.
```

脚本里塞进了六件事,每一件都对应一个真实的坑:

1. **软链跟随**:目标是软链时改软链指向的文件,而不是用普通文件替换掉软链本身:

`tools/file_operations.py:1058 @ 863e313`

```python
            'if [ -L "$t" ]; then '
            'rt="$(readlink -f "$t" 2>/dev/null || realpath "$t" 2>/dev/null || true)"; '
            '[ -n "$rt" ] && { t="$rt"; d="$(dirname "$t")"; }; '
            "fi; "
```

   并且**重算 `d`**,否则 `mv` 会跨文件系统,退化成 copy+unlink,不再原子。

2. **`mkdir -p` 折进同一个子进程**:省一次 exec
3. **`mktemp -p "$d"`**:临时文件落在目标同目录,保证 `mv` 是真 rename;三级回退到 PID 命名
4. **权限保留**:`chmod --reference` 是 GNU 专有,所以改成 `stat -c%a`(GNU)/ `stat -f%Lp`(BSD)读八进制再 `chmod`
5. **新文件用 `chmod "=rw"`**:POSIX 的 who-less 符号形式,等于 `rw` 减 umask。
   注释里专门说明了为什么**不**用 `$(umask)` 做算术:

`tools/file_operations.py:1038 @ 863e313`

```python
        #    0644 under umask 022) instead of mktemp's hardcoded 0600
        #    (#70856).  Deliberately NOT shell arithmetic on `$(umask)`:
        #    zsh (reachable via _find_bash's $SHELL fallback) parses
        #    leading-zero constants as decimal and silently computes a
        #    garbage mode, while `chmod "=rw"` is spec-identical in
        #    bash/dash/ash/zsh and degrades to 0600 (pre-fix behavior)
        #    if an exotic chmod rejects it.
```

6. **`trap ... EXIT` 清理临时文件** —— **这一条是坏的(■-4)**:

`tools/file_operations.py:1071 @ 863e313`

```python
            "trap 'rm -f \\\"$tmp\\\"' EXIT; "
```

这个 Python 字面量生成的 shell 文本是 `trap 'rm -f \"$tmp\"' EXIT;`。
单引号里 `\"` 是两个字面字符,所以 trap 触发时执行的是 `rm -f \"$tmp\"`,
shell 把 `\"` 解成一个字面双引号字符,于是 `rm` 去删一个**名字里带引号**的文件,
必然不存在,`rm -f` 静默返回 0,**真正的临时文件留在原地**。最小复现:

```verify
# 本行(codebase 的写法):文件残留
bash -c 'set -e; tmp=/tmp/tstfile.$$; : > "$tmp"; trap '"'"'rm -f \"$tmp\"'"'"' EXIT; false'; ls -l /tmp/tstfile.*
# 对照(正确写法):文件被删
bash -c 'tmp=/tmp/tstok.$$; : > "$tmp"; trap "rm -f \"\$tmp\"" EXIT; false'; ls -l /tmp/tstok.*
```

实跑输出:

```console
-rw-r--r-- 1 root root 0 Aug  9 08:37 /tmp/tstfile.31830      # 残留
ls: cannot access '/tmp/tstok.*': No such file or directory   # 已清理
```

而 docstring 明确承诺过相反的事:

`tools/file_operations.py:1006 @ 863e313`

```python
        On any failure the temp file is removed so we never leak a partial
        ``.hermes-tmp`` file next to the user's data, and the original file
        is left untouched. Content rides stdin so there is no ARG_MAX limit.
```

顺带一提,`set -e` 让大多数失败路径根本走不到 `mv`,而 `cat > "$tmp"` 之后失败的窗口很窄,
所以这个缺陷在日常使用中不容易被撞见 —— 但它确实让整段 trap 变成了装饰。

#### 2.3.2 写后校验:sha256 对拍,但**失败即放行**

`tools/file_operations.py:1608 @ 863e313`

```python
        content_verified: Optional[bool] = None
        try:
            hash_cmd = f"sha256sum {self._escape_shell_arg(path)} 2>/dev/null"
            hash_result = self._exec(hash_cmd)
            if hash_result.exit_code == 0 and hash_result.stdout.strip():
                disk_sha = hash_result.stdout.strip().split()[0]
                expected_sha = hashlib.sha256(content_bytes).hexdigest()
                content_verified = disk_sha == expected_sha
```

动机写得很有说服力:生产数据里 40 万条消息窗口内有 154 次"写完立刻再读一遍确认",
一个显式的 `verified: true` 就能省掉这一轮。

但注意 `if hash_result.exit_code == 0` —— **`sha256sum` 跑不起来或失败时,
`content_verified` 停在 `None`,写照样报成功**。这正是下面 ■-5 能成立的原因。

#### 2.3.3 写目录 = 无声成功 + 垃圾文件(■-5)

把 `write_file` 的目标指向一个**已存在的目录**:

- `_atomic_write` 里 `mv -f "$tmp" "$t"` 把临时文件**移进了目录**,退出码 0
- `sha256sum <目录>` 失败 → `content_verified` 保持 `None` → 校验层放行
- 返回 `bytes_written: 12`,`files_modified: [<目录>]`,**没有 error**

实跑复现:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'PY'
import os, sys, tempfile
TMP=tempfile.mkdtemp(); WS=os.path.join(TMP,"ws"); os.makedirs(WS)
os.environ.update(HERMES_HOME=os.path.join(TMP,"hh"), TERMINAL_CWD=WS)
os.makedirs(os.environ["HERMES_HOME"]); os.chdir(WS)
sys.path.insert(0,"/home/user/hermes-agent")
from tools import file_tools as ft
d=os.path.join(WS,"mydir"); os.makedirs(d)
print(ft.write_file_tool(d, "hello world\n"))
print(os.listdir(d))
PY
```

实跑输出:

```console
{"bytes_written": 12, "dirs_created": true, "lint": {"status": "skipped", "message": "No linter for  files"}, "resolved_path": "<ws>/mydir", "files_modified": ["<ws>/mydir"]}
['.hermes-tmp.7S1USf']
```

模型被告知"写成功了 12 字节",报告的路径上什么都没有,内容躺在目录里一个隐藏的
`.hermes-tmp.XXXXXX` 里 —— 正是 docstring 承诺"绝不会发生"的那个形状。
`patch` 走的是另一条路(先 `cat`,目录 cat 失败),所以它正确报错
`Failed to read file: <dir>`。

#### 2.3.4 行尾与 BOM:检测在磁盘、保留跨编辑

模型给的工具参数几乎总是裸 LF、无 BOM。如果照写,一个 Windows 换行的文件会被静默归一化。
所以两个属性都"读时剥离、写时恢复":

`tools/file_operations.py:78 @ 863e313`

```python
def _detect_line_ending(sample: str) -> Optional[str]:
    """Return the dominant line ending in ``sample`` or None if undetermined.

    Looks at the first few line breaks and picks ``\\r\\n`` if any are
    present (Windows / DOS), otherwise ``\\n`` (Unix).  Returns ``None``
    for empty / single-line content where we can't tell.  Used to
    preserve the file's original line endings across write_file and
    patch operations — without this the agent's bare-LF tool args
    silently normalize Windows-line-ending files, and patch produces
    mixed endings when only a substituted region changes.
    """
```

BOM 检测有一条**不能信任 `pre_content`** 的硬规则,理由很微妙:

`tools/file_operations.py:1108 @ 863e313`

```python
    def _file_has_bom(self, path: str, pre_content: Optional[str] = None) -> bool:
        """Whether the file on disk starts with a UTF-8 BOM.

        Always probes the first 3 bytes on disk — do NOT trust
        ``pre_content`` for BOM detection because the most common
        provider (``read_file_raw``) deliberately strips BOMs so the
        agent never sees U+FEFF glyphs.  Passing BOM-stripped content
        through ``pre_content`` would cause a false-negative and
        silently remove the marker on rewrite.
```

即:同一个变量在不同消费者眼里语义不同(lint 基线可以用剥了 BOM 的,BOM 检测不行),
于是宁可多花一次 `head -c 3`。实跑验证 round-trip:

```console
G) read CRLF+BOM content = '1|a\r\n2|b\r\n3|'
   after write bytes = b'\xef\xbb\xbfa\r\nb\r\nc\r\n'      # 写入 "a\nb\nc\n",BOM 与 CRLF 都被恢复
```

#### 2.3.5 二进制判定:扩展名 + 内容 + **U+FFFD 特判**

`tools/file_operations.py:906 @ 863e313`

```python
            if "\ufffd" in content_sample[:1000]:
                return True
            non_printable = sum(1 for c in content_sample[:1000]
                               if ord(c) < 32 and c not in '\n\r\t')
            return non_printable / min(len(content_sample), 1000) > 0.30
```

U+FFFD 那一条是全片最见功力的一处防御,理由写在上面几行:终端后端用
`errors="replace"` 解码 stdout,任何非 UTF-8 字节到这里已经变成了 U+FFFD(可打印字符,
非打印比例抓不到)。如果放行,一次 read→edit→write 往返就会**把原始字节永久换成乱码**。

**取舍是真实的**:任何合法的非 UTF-8 文本文件(latin-1 等)在 hermes 的文件工具里
一律读不了。实跑确认:

```console
H2) read latin-1 text -> {'content': '', 'file_size': 33, 'is_binary': True, 'error': 'Binary file - cannot display as text. ...'}
```

**这是一个正确的取舍**(宁可读不了,不可写坏),但要写进设计蓝图:
自己造 harness 时如果想支持非 UTF-8,就必须在读写两侧都用字节而非字符串,不能靠事后补救。

#### 2.3.6 search:诊断行与匹配行按**形状**分离

`_exec` 把 stderr 并进 stdout,于是 `rg: <file>: Permission denied` 会和真匹配混在一起。
分离策略不是"按错误前缀",而是**按输出形状**:

`tools/file_operations.py:363 @ 863e313`

```python
def _split_tool_diagnostics(output: str) -> tuple[str, str]:
    """Separate rg/grep diagnostic lines from real match output.

    ``_exec`` runs commands with ``stderr=subprocess.STDOUT``, so error and
    warning text from ``rg``/``grep`` is interleaved with match lines in a
    single stream. Diagnostics must not be parsed as matches, and on a hard
    failure they are the error message to surface.
```

这样 exit code 2 就能被分成两类:**纯失败**(没有可用 payload → 报错)与
**部分失败**(有些文件匹配了,一个文件读不了 → 保留匹配)。

`tools/file_operations.py:2600 @ 863e313`

```python
        if result.exit_code == 2 and not payload.strip():
```

另有一个很实用的"零结果引导":13.9% 的生产内容搜索返回零匹配,零匹配等于一个死回合。
于是零匹配时最多再跑两次 `rg --count-matches` 探针,分别探"大小写"、"隐藏/被 gitignore 的文件"、
"正则元字符没转义":

`tools/file_operations.py:2330 @ 863e313`

```python
        # Hidden/ignored probe: rg skips dotdirs and .gitignore'd files by
        # default. When the pattern exists only there, say so instead of
        # returning a bare zero (bench case: match in .hidden/ silently
        # missing from results).
```

实跑见到过这条(exp7 最后一行):搜索 `supersecret` 在可见文件里 0 命中,
但提示"1 match(es) in 1 hidden or gitignored file(s)"。

#### 2.3.7 lint:三层,只有结构化格式**写前 fail-closed**

- **写前闸门**:`.json/.yaml/.yml/.toml` 内容解析不过 → **拒绝写**,一个字节都不落盘
- **写后 delta**:其余走"写后 lint,并减去写前就存在的错误"
- **LSP 层**:语义诊断走独立字段 `lsp_diagnostics`,只在本地后端跑

`tools/file_operations.py:704 @ 863e313`

```python
# Subset of LINTERS_INPROC that the pre-write fail-closed gate in
# ``write_file`` (see below) refuses on, rather than merely reporting.
# Deliberately excludes ``.py``: unlike JSON/YAML/TOML (atomic structured
# data blobs where "doesn't parse" always means "corrupt"), ``.py`` is
# used throughout this codebase's own test fixtures as a generic
# stand-in extension for arbitrary non-Python text content (e.g.
```

`.py` 被显式排除的理由是"本仓库自己的测试拿 `.py` 当任意文本的占位扩展名" ——
一个**很坦白的、把既有习惯当约束**的决定。

YAML linter 用 `yaml.parse`(纯语法)而不是 `safe_load`,理由同样是 fail-closed 的代价:

`tools/file_operations.py:635 @ 863e313`

```python
    Deliberately a *syntax-only* scan (``yaml.parse``), not ``safe_load``:
    loading rejects perfectly valid YAML that merely isn't a single plain
    document — multi-document streams (``---``-separated Kubernetes
    manifests raise ``ComposerError``) and application-defined tags
    (CloudFormation ``!Sub``/``!Ref``, Ansible ``!vault`` raise
    ``ConstructorError``).  Those are content conventions for whatever
    consumes the file, not syntax errors, and this linter's verdict is
    used as a fail-closed WRITE gate in ``write_file`` — a false positive
    here refuses a legitimate write outright.  ``yaml.parse`` still
```

**原则**:一个判据要升格成"阻断",它的**假阳性代价**必须先被压到接近零。

#### 2.3.8 patch:九种模糊匹配 + "已经打过了"识别

`patch_replace` 的匹配交给 `tools/fuzzy_match.py`,九种策略依次是
exact / line_trimmed / whitespace_normalized / indentation_flexible / escape_normalized /
trimmed_boundary / unicode_normalized / block_anchor / context_aware
(`tools/fuzzy_match.py:520`-`:793` 的九个 `_strategy_*` 函数)。

最值得抄的是"已经打过了"的识别:生产里最常见的 patch 失败是**重发一个已经落地的编辑**:

`tools/file_operations.py:1704 @ 863e313`

```python
        if error or match_count == 0:
            # Already-applied detection: the most common patch failure in
            # production is a re-send of an edit that has already landed
            # (identical old/new strings, or old_string gone while
            # new_string is present verbatim). Surface that as an explicit
            # success-shaped no-op so the model moves on instead of
            # burning turns on re-reads and re-patches.
```

配套地,工具层还按 `(task_id, resolved_path)` 记连续失败次数,第 3 次起换成升级版提示,
明确给三条出路(重读 / 加长 old_string / 改用 write_file):

`tools/file_tools.py:2023 @ 863e313`

```python
                result_dict["_hint"] = (
                    f"This is failure #{failure_count} patching {path!r}. "
                    "Stop retrying with variations of the same old_string. "
                    "Either: (1) re-read the file fresh to verify current "
                    "content, (2) use a longer / more unique old_string with "
                    "surrounding context lines, or (3) use write_file to "
                    "replace the entire file if the targeted region is hard "
                    "to anchor."
                )
```

#### 2.3.9 V4A patch:路径来自**内容**,所以判据更严

普通 `patch` 的 `path=` 是模型直接给的参数;V4A 的路径写在 patch **正文**里,
而正文可能来自 skill 内容、网页抽取、prompt 注入。于是 V4A header 里**禁止 `..`**,
而 `path=` 参数不禁:

`tools/file_tools.py:1861 @ 863e313`

```python
            # in V4A headers: a legitimate multi-file patch from a single cwd
            # can always emit absolute paths or paths relative to the agent's
            # cwd without ``..``. The explicit ``path=`` arg is unchanged
            # because the agent uses relative ``..`` paths legitimately
            # (e.g. ``patch path="../other_module/x.py"`` from a worktree).
```

**这是一条很干净的威胁模型推理**:同一个语法特征(`..`),在"参数"通道是合法用法、
在"内容"通道是攻击面,所以判据按**通道**分,不按语法分。

正则用 `\s*` 而不是 `\s+`,专门对齐 parser 的宽松度 —— 否则 `***Update File:`(无空格)
能被 parser 接受却跳过这道检查:

`tools/file_tools.py:1875 @ 863e313`

```python
        # ``\s*`` (not ``\s+``) after ``***`` matches patch_parser leniency:
        # it accepts ``***Update File:`` with no space after the asterisks
        # (patch_parser.py uses ``\*\*\*\s*Update\s+File:``). Requiring a space
        # here let a no-space header parse + apply while skipping this check.
```

`*** Move File: src -> dst` 两个端点都要过检查 —— 注释说这条曾经漏过
(`Move` 到 `/etc/crontab` 会跳过敏感路径预检)。

多文件 V4A 的锁按**排序后**获取,防止两个并发调用交叉持锁死锁:

`tools/file_tools.py:1917 @ 863e313`

```python
        _resolved_paths.sort()
```

### 2.4 `tools/read_extract.py` —— 结构化文档抽文本

三种格式用 stdlib 直接解(zipfile + ElementTree),不引硬依赖;可选的 `anydoc`
(Rust 内核)把覆盖面扩到 PDF / 老 Office / ODF / RTF / EPUB。

`tools/read_extract.py:28 @ 863e313`

```python
EXTRACTABLE_EXTENSIONS = frozenset({".ipynb", ".docx", ".xlsx"})
```

**stdlib 三种是权威的**,即使装了 anydoc 也走 stdlib 路径,理由是"装不装 anydoc 行为一致"
(`tools/read_extract.py:7-8`)。这是一条好规则:可选依赖只能**扩展**能力,不能改变已有行为。

anydoc 的懒加载有一条节流:失败后 300 秒内不再重试,因为加载会 shell 出去装包:

`tools/read_extract.py:67 @ 863e313`

```python
# After a failed first load, wait this long before trying again. The attempt
# can shell out to pip, so retrying on every call would hammer the network
# in environments where the install can never succeed.
ANYDOC_RETRY_SECONDS = 300.0
```

并且 `prompt=False`,`read_file` 绝不能因为一个安装提示而卡住(`:95`)。

**大小限制只对 anydoc 生效**:

`tools/read_extract.py:132 @ 863e313`

```python
    if size > MAX_ANYDOC_BYTES:
        raise ExtractionError(
            f"Document too large to convert ({size:,} bytes, limit is {MAX_ANYDOC_BYTES:,})"
        )
```

而给 xlsx 准备的那个常量**从未被使用**(■-8):

`tools/read_extract.py:37 @ 863e313`

```python
MAX_XLSX_BYTES = 50 * 1024 * 1024
```

搜索面:`grep -rn "MAX_XLSX_BYTES" --include=*.py .`,覆盖基线全部 `.py`(含 `tests/`),
**仅 1 处命中,即上面这行定义**。xlsx 路径实际靠的是行/列上限
(`_MAX_XLSX_ROWS_PER_SHEET = 5000`,`_MAX_XLSX_COLS = 256`)兜底,
以及 `zipfile` 的按需读取 —— 所以不是完全没护栏,但声明的字节上限确实是死的。

xlsx 抽取的一些细节值得记:隐藏/极隐藏 sheet 跳过(`state in {"hidden", "veryHidden"}`),
单个 sheet 的 XML 解析失败只跳过该 sheet 而不是整本失败(`except ET.ParseError: continue`),
尾部全空行被裁掉。都是"局部坏了不要拖垮整体"的写法。

### 2.5 `tools/working_diff.py` —— 工作区 diff

小而干净。三个模式 working / staged / all,未跟踪文件通过
`git diff --no-index /dev/null <file>` 折进来,否则新建文件在 diff 里是隐形的。

`tools/working_diff.py:49 @ 863e313`

```python
def _untracked_diff(cwd: str, files: List[str]) -> str:
    """Render untracked files as new-file diffs via ``git diff --no-index``."""
    chunks: List[str] = []
    for rel in files[:_MAX_UNTRACKED_FILES]:
        try:
            # --no-index exits 1 when the files differ — that's the success
            # path here, so ignore the return code and keep the output.
```

三个防炸措施:`-c core.quotePath=false`(非 ASCII 文件名不被转义)、
`_MAX_UNTRACKED_FILES = 50`(注释直说是防 `node_modules` 爆炸)、
diff 本身给双倍超时(`timeout=_GIT_TIMEOUT * 2`)。

`_run` 的契约是"git 失败绝不抛异常,返回 (returncode, stdout)" —— 这让所有调用点都能
用同一种方式处理失败,不必到处 try。

注意:**未跟踪文件只在没有 `paths` 限定时才收集**(`tools/working_diff.py:108`),
因为 `--no-index` 不吃 pathspec。

### 2.6 两个 preview 工具 —— 纯桥接

`read_preview_tool.py` / `open_preview_tool.py` 几乎没有逻辑,是"schema + 一层薄派发"。
两者都用同一个门禁:

`tools/read_preview_tool.py:52 @ 863e313`

```python
def check_read_preview_requirements() -> bool:
    """Desktop GUI only — HERMES_DESKTOP is set on the gateway the app spawns."""
    return env_var_enabled("HERMES_DESKTOP")
```

`read_preview` 走的是**阻塞式提示桥**:tui_gateway 发 `preview.read.request`,
渲染进程序列化当前 tab 再回 `preview.read.respond`。工具层只做一件有意义的事 ——
把回调结果稳定成 JSON:

`tools/read_preview_tool.py:45 @ 863e313`

```python
    # Desktop answers with a JSON object; pass it through, else wrap the raw text.
    try:
        return json.dumps(json.loads(raw), ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps({"text": str(raw)}, ensure_ascii=False)
```

`open_preview` 唯一的逻辑是把裸域名补成 URL:

`tools/open_preview_tool.py:26 @ 863e313`

```python
    if not v or "://" in v or v.startswith(("/", "./", "../", "~", "file:")):
        return v
    if re.match(r"^(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(:\d+)?(/|$)", v, re.I):
        return "http://" + v
```

localhost 补 `http://`,其余域名补 `https://`,路径与已有 scheme 原样透传。
**这两个工具不做任何文件安全判定** —— `open_preview` 接受任意文件路径并交给渲染进程显示。
读禁清单在这条路径上**没有装**(◇-4)。

---

## 3. 测试作为行为规格

### 3.1 跑了什么

环境:`/home/user/hermes-venv`,**87 个包**(与 CLAUDE.md 记录的 R8B 环境一致,本次未装任何包);
基线 HEAD `863e313`,工作区 `git status --porcelain` 为空。

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh \
  tests/agent/test_file_safety.py tests/agent/test_file_safety_container_mirror.py \
  tests/agent/test_file_safety_credentials.py tests/agent/test_file_safety_cross_profile.py \
  tests/agent/test_file_safety_sandbox_mirror.py tests/agent/test_file_safety_session_state.py \
  tests/tools/test_file_operations.py tests/tools/test_file_operations_edge_cases.py \
  tests/tools/test_file_ops_cwd_tracking.py tests/tools/test_file_tools.py \
  tests/tools/test_file_tools_container_config.py tests/tools/test_file_tools_cwd_resolution.py \
  tests/tools/test_file_tools_live.py tests/tools/test_file_tools_tilde_profile.py \
  tests/tools/test_read_extract.py tests/tools/test_working_diff.py \
  tests/tools/test_read_preview_tool.py tests/tools/test_open_preview_tool.py \
  tests/tools/test_credential_files.py tests/tools/test_file_state_registry.py
```

结果:

```console
=== Summary: 20 files, 285 tests passed, 0 failed (100% complete) in 10.5s (8 workers) ===
```

**20 文件 / 285 passed / 0 failed。** 无失败,故无失败诊断。

**静默跳过(必须记)**:用 pytest 直接跑并加 `-rs` 查跳过原因:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -m pytest -q \
  tests/tools/test_credential_files.py tests/agent/test_file_safety_credentials.py \
  tests/tools/test_read_extract.py -p no:randomly -rs
```

```console
SKIPPED [3] ../hermes-venv/lib/python3.11/site-packages/_pytest/unittest.py:523: firecrawl-anydoc not installed
68 passed, 3 skipped in 1.34s
```

即 **`_extract_anydoc` 这条路径(PDF / 老 Office / ODF / RTF / EPUB)在本环境完全未被测试覆盖**,
包括那个 `MAX_ANYDOC_BYTES` 上限。这不是代码缺陷,是环境限制,但它意味着
"anydoc 分支的行为规格在本轮没有被验证过"。

### 3.2 测试给出的行为规格里最值得记的一条

`tests/tools/test_credential_files.py` 把"可挂载凭据文件"的判据**直接绑定到读禁清单**:

`tests/tools/test_credential_files.py:476 @ 863e313`

```python
    The bar is the canonical read deny-list: whatever the agent is forbidden to
    ``read_file`` must not be mountable either, so the mount surface can't
    grant what the read surface denies.
    """
```

实现侧确实是这么写的,而且是 **fail-closed**(导入不到守卫就拒绝挂载):

`tools/credential_files.py:122 @ 863e313`

```python
    if get_read_block_error is None:
        logger.error(
            "credential_files: refusing %r — agent.file_safety could not be "
            "imported, so the master-store deny-list cannot be consulted",
            relative_path,
        )
        return False
```

**这条设计是对的,但它把读禁清单的每一个缺口都放大了一倍** —— 见 ■-2。

### 3.3 我自己跑的复现实验(共 7 组)

脚本放在会话临时目录,均只读基线、只写 `tempfile.mkdtemp()`。要点已在第 2 节各处引用,
汇总:

| 实验 | 结论 |
|---|---|
| exp1 | 读禁/写禁两张表逐项对照(第 2.1.5 节的表) |
| exp2 | 端到端:`auth.json` 可写不可读;`op_cache.json` 两侧全通;软链被穿透拦下;**硬链绕过**;`/dev/urandom`、`/proc/self/environ` 被拦 |
| exp3 | 无尾换行文件末行丢失;并发外部编辑下 `write_file` 丢失更新、`patch` 不丢;BOM+CRLF 往返保留;latin-1 被判二进制 |
| exp4 | 3 行无尾换行文件报 `total_lines=2`;240 KB 文件字符预算截断正常;safe_root 生效;6 线程并发写无撕裂但最后写者赢;schema 默认值与 handler 默认值不一致 |
| exp5 | `op_cache.json` **可被 skill 声明式 bind-mount 进沙箱** |
| exp6 | `write_file` 指向已存在目录 → 无声"成功" + 垃圾临时文件 |
| exp7 | **`patch` 完全绕过读禁清单,且返回未脱敏的 unified diff** |

---

## 4. 发现清单

### ■-1 `auth.json` 可写:文档承诺"always blocked",代码没有(同时也是 ▲-1)

**强度:实跑复现。**

写禁清单里**没有** `auth.json`。清单全文见 `agent/file_safety.py:28`-`:61`,
其中 HERMES_HOME 下的条目只有 `.env`、`.anthropic_oauth.json`、`cache/bws_cache.enc.json`;
`_classify_write_denial` 的额外分支只覆盖 `state.db` / `sessions/` / `mcp-tokens/` / `pairing/`。
工具层 `_check_sensitive_path` 只额外挡 `config.yaml`:

`tools/file_tools.py:691 @ 863e313`

```python
    # Prevent agents from modifying the Hermes config file directly.
    # approvals.mode and other security settings live here; a malicious or
    # prompt-injected agent could silently disable exec approval by writing to
    # this file.
```

实跑(exp2):

```console
--- WRITE auth.json
{"bytes_written": 11, "dirs_created": true, "verified": true, "lint": {"status": "ok", "output": ""}, "resolved_path": "<HH>/auth.json", "files_modified": ["<HH>/auth.json"]}

auth.json now = {"pwned":1}
```

**影响**:`auth.json` 存的是各 provider 的 API key / OAuth 授权。可写意味着一次 prompt 注入
就能把它整体替换(拒绝服务),或改写其中的 provider 端点把后续流量与凭据导向别处。
读禁清单挡住了"读出来外传",却没挡住"改掉"。

### ▲-1 文档与代码矛盾:`website/docs/user-guide/security.md:288`

**强度:实跑复现。**

按 CLAUDE.md 的判定要求,先定位它归哪个标题管、整段说了什么。

`website/docs/user-guide/security.md:281 @ 863e313`

> ### Protected paths (always blocked)

`website/docs/user-guide/security.md:283 @ 863e313`

> These categories are always denied, even when `HERMES_WRITE_SAFE_ROOT` is unset:

`website/docs/user-guide/security.md:288 @ 863e313`

> | Hermes credential stores | `auth.json`, `.env`, `.anthropic_oauth.json`, `mcp-tokens/`, `pairing/` under HERMES_HOME (active profile and global root) |

这一节的引子(`:279`)明确限定语境是"Before `write_file` or `patch` touches disk",
所以这一行断言的是**写**被拦。整行五个条目逐个判定:

| 条目 | 代码事实 |
|---|---|
| `auth.json` | ❌ **写不被拦**(实跑覆盖成功) |
| `.env` | ✅ 被拦 |
| `.anthropic_oauth.json` | ✅ 被拦 |
| `mcp-tokens/` | ✅ 被拦 |
| `pairing/` | ✅ 被拦 |

五分之一为假 → **▲**。同节其余断言经查为真:`:287` 行的 OS 凭据(`~/.ssh/`、`~/.aws/`、
`~/.kube/`、`/etc/sudoers`、`~/.netrc`)全部在清单里;`:291` 的
"pointing `HERMES_WRITE_SAFE_ROOT` at `$HOME` does not allow writing `~/.ssh/id_rsa`" 为真
(凭据判定排在 safe_root 判定之前);`:293` 的两条报错措辞与代码逐字一致。

### ■-2 `op_cache.json`(1Password 明文缓存)在**所有**守卫表里都不存在,并且可被挂进沙箱

**强度:实跑复现。**(这条结清 R9C D 片 ■-1 在本片的部分)

上游文件自己声明它装的是明文 secret **值**:

`agent/secret_sources/onepassword.py:34 @ 863e313`

```python
are cached in-process and on disk under ``<hermes_home>/cache/op_cache.json``
so back-to-back short-lived ``hermes`` invocations don't re-shell ``op`` for
every reference.  The disk file holds only resolved secret *values*; auth
material is fingerprinted, never stored.
```

同类的 Bitwarden 明文缓存(`cache/bws_cache.json`)在读禁清单里有,
`op_cache.json` 没有。**搜索面**:`grep -rn "op_cache" . --exclude-dir=.git`,
覆盖基线**全部文件类型**(不限 `.py`),命中 **3 处**:
`agent/secret_sources/onepassword.py:34`(docstring)、`:118`(basename 常量)、
`website/docs/user-guide/secrets/onepassword.md:149`(文档)。
**没有任何一处是守卫表。**四张相关表逐一核对:

| 守卫表 | 位置 | 含 `bws_cache.json`? | 含 `op_cache.json`? |
|---|---|---|---|
| 读禁清单 | `agent/file_safety.py:284`:`os.path.join("cache", "bws_cache.json"),` | ✅ | ❌ |
| 写禁清单 | `agent/file_safety.py:50`:`str(hermes_home / "cache" / "bws_cache.enc.json"),` | ❌(只有 enc) | ❌ |
| 媒体投递禁清单 | `gateway/platforms/base.py:1369`:`os.path.join("cache", "bws_cache.json"),` | ✅ | ❌ |
| 面板文件 API 禁清单 | `hermes_cli/web_server.py:1779`:`"bws_cache.json",` | ✅ | ❌ |

实跑(exp2)读侧:

```console
--- READ op_cache.json
{"content": "1|{\"op://vault/item\":\"PLAINTEXT-1P-SECRET\"}", "total_lines": 0, "file_size": 41, ...}
```

**放大**:因为 `tools/credential_files.py` 的挂载判据就是读禁清单(见 3.2),
一个 skill 只要在 `required_credential_files` 里写一行 `cache/op_cache.json`,
就能把 1Password 的明文密值 bind-mount 进它自己代码运行的沙箱。实跑(exp5):

```console
credential_files: refused 'auth.json' — it is a credential store the agent is denied from reading; ...
register_credential_file('auth.json') -> False
credential_files: refused 'cache/bws_cache.json' — ...
register_credential_file('cache/bws_cache.json') -> False
register_credential_file('cache/op_cache.json') -> True
mounts: [{'host_path': '<HH>/cache/op_cache.json', 'container_path': '/root/.hermes/cache/op_cache.json'}]
```

这正是那份测试文档字符串说要防的事(`tests/tools/test_credential_files.py:475`):
"whatever the agent is forbidden to `read_file` must not be mountable either"。
判据绑对了,只是**表本身缺一行**。

### ■-3 `patch` 完全绕过读禁清单,并把未脱敏的 unified diff 交给模型

**强度:实跑复现。这是本片最强的一条。**

读禁清单只装在两个地方:`read_file_tool`(`tools/file_tools.py:1356`)与
`search_tool`(`tools/file_tools.py:2086`)。`patch_tool` 里**没有**。
**搜索面**:`grep -rn "get_read_block_error\|raise_if_read_blocked" --include=*.py .`
覆盖基线全部 `.py`;`tools/file_tools.py` 内命中 `:602`、`:603`、`:1356`、`:2086` 四处,
分别属于搜索结果过滤、read、search;`patch_tool`(`:1840`-`:2039`)与
`write_file_tool`(`:1757`-`:1837`)区间内**零命中**。

后端层的 `patch_replace` 只做写侧判定,随即无条件 `cat`:

`tools/file_operations.py:1674 @ 863e313`

```python
        # Block writes to sensitive paths
        denied = get_write_denied_error(path)
        if denied:
            return PatchResult(error=denied)

        # Read current content
        read_cmd = f"cat {self._escape_shell_arg(path)} 2>/dev/null"
        read_result = self._exec(read_cmd)
```

然后把新旧内容做成 unified diff 返回:

`tools/file_operations.py:1782 @ 863e313`

```python
        # Generate diff
        diff = self._unified_diff(content, new_content, path)
```

而脱敏只装在读侧三处(`grep -n "redact_sensitive_text" tools/file_tools.py` →
`:21` import、`:1337` 文档抽取、`:1490` read、`:2112` search 匹配行);
`tools/file_operations.py` 与 `tools/patch_parser.py` 内 `grep -rn "redact"` **零命中**。

实跑(exp7),`read_file` 被拒的同一个文件,`patch` 把密钥原样吐了出来:

```console
read_file(auth.json) -> {"error": "Access denied: <HH>/auth.json is a Hermes credential store and cannot be read directly. Pro

patch(auth.json) success= True error= None
DIFF RETURNED TO MODEL:
 --- a/<HH>/auth.json
 +++ b/<HH>/auth.json
 @@ -1,4 +1,4 @@
  {
 -  "openai": {"api_key": "sk-SECRET-OPENAI-123"},
 +  "openai2": {"api_key": "sk-SECRET-OPENAI-123"},
    "anthropic": {"api_key": "sk-ant-SECRET-456"}
  }
```

项目级 `.env` 同样:

```console
patch(.env) success= True  diff:
 -API_KEY=supersecret
 +API_KEY2=supersecret
  DB_PASS=hunter2
```

**这就是本项目历轮反复撞见的"防线只装了一处"形态的教科书样本**:
读禁清单被当成"读工具的守卫"来安装,而不是"任何会把文件内容返回给模型的路径的守卫"。
`patch` 天生必须读文件(要算 diff),于是它天然是第二条读通道 —— 但没人给它装门。
`.env` 这一条尤其现实:项目 `.env` 是**全盘任意位置**按 basename 拦的,
说明作者确实想挡住"帮用户调项目时顺手把 `.env` 读出来";而模型只要发一个
`patch(path=".env", old_string="A", new_string="A ")` 就能拿到全文。

### ■-4 `_atomic_write` 的 `trap` 清理从不生效

**强度:实跑复现(最小 bash 复现 + 真实调用留下的残留文件)。**

`tools/file_operations.py:1071 @ 863e313`

```python
            "trap 'rm -f \\\"$tmp\\\"' EXIT; "
```

生成的 shell 文本是 `trap 'rm -f \"$tmp\"' EXIT;`;单引号内 `\"` 是字面量,
trap 触发时 `rm` 收到的是一个名字带引号的路径,恒不存在。复现命令与输出见第 2.3.1 节。
与 docstring(`tools/file_operations.py:1006`)的承诺相反。

严重性有限(`set -e` 让绝大多数失败发生在 trap 设置之前),但它是**一个看起来存在、
实际不存在的清理机制**,而 ■-5 恰好就是它本该兜住的形状之一。

### ■-5 `write_file` 指向已存在目录 → 报告成功,内容落进目录里的隐藏临时文件

**强度:实跑复现。** 复现与输出见第 2.3.3 节。

三层防线同时失效:
- `_atomic_write` 的 `mv -f "$tmp" "$t"`,`$t` 是目录时语义变成"移进目录",退出码 0
- sha256 写后校验:`sha256sum <目录>` 非零退出 → `content_verified` 停在 `None` → **fail-open**
  (`tools/file_operations.py:1612 @ 863e313`)

```python
            if hash_result.exit_code == 0 and hash_result.stdout.strip():
```

- trap 清理:见 ■-4,本来就不生效

结果:返回体里 `bytes_written: 12`、`files_modified: [<目录>]`、**无 error**、
**无 `verified` 字段**(因为是 `None`,`to_dict` 会滤掉)。模型读到的是"写成功了"。

**设计教训**:一个"验证层"如果把"验证不了"和"验证通过"合并成同一种输出(都不报错),
它在最需要它的场景里恰好是哑的。正确做法是把 `verified: null` 也当成需要向模型明说的状态。

### ■-6 `_classify_write_denial` 返回类型违约,导致 state.db 的拒绝理由错位

**强度:实跑复现。** 见第 2.1.2 节。签名 `-> Optional[str]`(`agent/file_safety.py:101`),
两处返回 `True`(`:129`、`:132`)。功能不受影响(`is_write_denied` 只判非 None),
但 `get_write_denied_error` 把会话状态文件报成 "protected system/credential file"。
这是**给模型的错误信号**:模型会以为自己碰了凭据,而不是"这是应用自有状态,请走 session API"。

### ■-7 无尾换行的文件:末行被静默丢弃,`total_lines` 少 1,`truncated` 为假

**强度:实跑复现。**

`tools/file_operations.py:1217 @ 863e313`

```python
        # Get total line count
        wc_cmd = f"wc -l < {self._escape_shell_arg(path)}"
        wc_result = self._exec(wc_cmd)
        wc_output = _strip_terminal_fence_leaks(wc_result.stdout)
        try:
            total_lines = int(wc_output.strip())
        except ValueError:
            total_lines = 0

        # Check if truncated
        truncated = total_lines > end_line
```

`wc -l` 数的是**换行符个数**。文件没有尾换行时,它比真实行数少 1。后果有两层:

1. `total_lines` 报少 1(轻)
2. `truncated = total_lines > end_line` 因此**在边界上判假**(重):
   一个 2001 行、无尾换行的文件用默认 `limit=2000` 读,`wc -l` = 2000,
   `truncated = 2000 > 2000` = False,`hint` 为 None,而 `sed -n '1,2000p'` 只吐了前 2000 行。
   **第 2001 行既没被返回,也没有任何标志告诉模型还有内容。**

实跑(exp3 A / exp4 A):

```console
A) 2001 lines, no trailing NL:
   total_lines = 2000  truncated = False  hint = None
   -> line2001 present in output? False

A) 3 lines no NL, limit=2: {'total_lines': 2, 'truncated': False, 'hint': None}
   content = '1|a\n2|b\n3|'
   full read content = '1|a\n2|b\n3|c' total_lines= 2
```

顺带暴露第二个小问题:`sed` 的输出带尾换行,`_add_line_numbers` 按 `\n` split 后
会多出一个空元素,于是**永远多渲染一个空的行号**(上面的 `3|`)。
模型看到 `3|` 会以为第 3 行是空行。

对照:同样 2001 行**有**尾换行时 `total_lines = 2001`、`truncated = True`(exp3 B),
所以这确实是"无尾换行"这一个条件触发的。

### ■-8 `MAX_XLSX_BYTES` 定义后从未使用

**强度:静态对读 + 全仓搜索。** 见第 2.4 节。搜索面已写明。

### ■-9 `read_file` 的 schema 默认值(2000)与实际 handler 默认值(500)不一致

**强度:实跑复现。**

`tools/file_tools.py:2262 @ 863e313`

```python
def _handle_read_file(args, **kw):
    tid = kw.get("task_id") or "default"
    return read_file_tool(path=args.get("path", ""), offset=args.get("offset", 1), limit=args.get("limit", 500), task_id=tid)
```

而 schema 告诉模型的是 2000:

`tools/file_tools.py:2167 @ 863e313`

```python
            "limit": {"type": "integer", "description": "Maximum number of lines to read (default: 2000, max: 2000). Reads are additionally capped at a ~100K-character budget with a next_offset continuation.", "default": 2000, "maximum": 2000}
```

实跑:

```console
E) schema limit default = 2000
   handler: ['return read_file_tool(path=args.get("path", ""), offset=args.get("offset", 1), limit=args.get("limit", 500), task_id=tid)']
```

**为什么这是缺陷而不是无害**:schema 是**给模型的契约**。模型省略 `limit` 时以为拿到 2000 行,
实际只拿到 500 行,而 `truncated`/`hint` 会按 500 计算 —— 结果是正确的,
但模型对"我已经读完了吗"的推理基于一个错误的先验。同一文件里另一个方向也不一致:
`read_file_tool` 的 Python 默认值本身是 2000(`tools/file_tools.py:1264`)。

### ■-10 `MAX_FILE_SIZE` 分支为空,注释承诺的 warn 不存在

**强度:静态对读。** 见第 2.2.4 节末。

### ◇-1 硬链接绕过读禁清单

**强度:实跑复现。** 读禁判定基于 `Path.resolve()`,能穿透符号链接,但硬链接在
文件系统层就是同一个 inode 的第二个名字,`realpath` 无从分辨。实跑(exp2):

```console
--- READ symlink notes.txt -> auth.json
{"error": "Access denied: <HH>/auth.json is a Hermes credential store ..."}

--- READ hardlink copy.json -> bws_cache.json
{"content": "1|{\"k\":\"BWS-SECRET\"}", "total_lines": 0, "file_size": 18, ...}
```

**这不是"漏了一个 case",而是路径级禁清单的固有上限**:任何按路径判定的守卫都挡不住硬链接。
记在这里是因为设计蓝图必须诚实说明:**要真正挡住,判据得是 inode(`st_dev`+`st_ino`)而不是路径**,
而那会带来"文件不存在时无法预判"的新问题。当前代码选择路径判定 + 明说"这不是边界",
是一致的;只是这个具体的绕过口在文档里没提。

### ◇-2 写禁清单在 `tools/file_operations.py` 有一份**从未被使用**的模块级快照

**强度:静态对读 + 全仓搜索。**

`tools/file_operations.py:52 @ 863e313`

```python
WRITE_DENIED_PATHS = build_write_denied_paths(_HOME)

WRITE_DENIED_PREFIXES = build_write_denied_prefixes(_HOME)
```

**搜索面**:`grep -rn "WRITE_DENIED_PATHS\|WRITE_DENIED_PREFIXES" --include=*.py .`,
覆盖基线全部 `.py`(含 `tests/`),**只有上面这两行定义,零消费者**。

危险在于它是个**看起来公开可用**的常量,而且:
- `_HOME = str(Path.home())`(`:50`)在 **import 时**求值,不认 `HERMES_HOME`、不认 profile;
- 真正的判定路径 `get_write_denied_error → _classify_write_denial` 每次调用都重算。

任何人 import 这两个常量都会拿到一份 import 时冻结、profile 无感知的表。

### ◇-3 结构化文档抽取排在读禁清单**之前**

**强度:静态对读。** 见第 2.2.3 节。当前禁清单条目没有可抽取扩展名,所以不可利用,
但顺序上"先把整个文件读进来抽成文本、再判能不能读"是反的。
一旦禁清单将来加进一个 `.xlsx`/`.pdf` 之类,这道门就是开的。

### ◇-4 `open_preview` 不做任何文件安全判定

**强度:静态对读。** `open_preview_tool.py` 全文 97 行,除了 URL 规范化没有任何路径判定,
`~`、`/`、`./`、`../`、`file:` 开头一律原样透传给渲染进程
(`tools/open_preview_tool.py:26`)。也就是说
`open_preview(url="~/.hermes/auth.json")` 会让桌面 GUI 把凭据文件显示在预览面板里。
它是"给人看"的通道而不是"给模型看"的通道(内容不回到 context,除非再调 `read_preview`,
而 `read_preview` 对文件 tab 只返回身份不返回内容 —— 见其 schema
`tools/read_preview_tool.py:66`),所以危害等级低;但这条路径上确实没有守卫。

### ◎-1 读禁清单的自我描述比它实际做的**保守**

**强度:静态对读。** docstring 说自己是 defense-in-depth、"terminal 能绕过"
(`agent/file_safety.py:217`-`:230`),这是**字面为真且偏保守**的表述:
它实际上还是 `tools/credential_files.py` 挂载判据的唯一来源(见 3.2),
即它同时承担了一个**不是 defense-in-depth 而是真判据**的角色。
按 CLAUDE.md 的记号规则,字面为真 → 不是 ▲,记 ◎。
这个错配本身有设计意义:**一张自称"只是提示"的表,被另一个模块当成了"权威边界"。**

---

## 5. 未取证 / 推定

1. **容器后端下的软链绕过读禁**(推定,未取证)。
   `tools/file_tools.py:374`-`:380` 在容器后端走 `_normalize_without_host_deref`,
   **不做** `Path.resolve()`;而 `get_read_block_error` 自己在宿主进程里 `resolve()`
   (`agent/file_safety.py:239`)。容器内的软链在宿主上不存在或指向别处,
   两边解析的不是同一棵文件树。推定"容器内建一个指向 `/root/.hermes/auth.json` 的软链
   即可绕过读禁",但本容器无 Docker,**未实测**。

2. **`_expand_path` 的 `~username` 注入面**(推定安全,未做对抗测试)。
   `tools/file_operations.py:971` 用 `re.fullmatch(r'[a-zA-Z0-9._-]+', username)`
   限制用户名后才 `echo ~{username}`,后缀不参与 shell 展开。静态看是安全的,
   但我没有构造对抗输入实测。

3. **`_atomic_write` 在真实失败路径上的临时文件残留频率**(部分取证)。
   trap 失效已实测;但"哪些真实失败会走到 trap 之后"没有穷举 —— 我只构造出了
   "目标是已存在目录"这一种(且那一种 `mv` 其实成功了)。`cat > "$tmp"` 失败
   (磁盘满 / 配额)这一类未实测。

4. **`patch` 泄露路径上 `redact_sensitive_text` 若被接上是否足够**(未取证)。
   实验里 `sk-SECRET-OPENAI-123` 不是真实格式的 key,所以我无法判断脱敏器
   对真 key 的召回率。`API_KEY=supersecret` / `DB_PASS=hunter2` 确实原样透出,
   但那是"没有任何脱敏"而不是"脱敏器漏了"。

5. **`anydoc` 分支的全部行为**(环境限制,未覆盖)。
   `firecrawl-anydoc` 未装,3 个用例静默跳过;`_extract_anydoc`、`MAX_ANYDOC_BYTES`、
   300 秒重试节流,本轮均未实际执行过。

6. **LSP 层**(`_maybe_lsp_diagnostics` / `_snapshot_lsp_baseline` / `agent/lsp/*`)
   只做了静态对读。它只在 `LocalEnvironment` 下启用,本轮未搭 LSP server 实测。

7. **`tools/fuzzy_match.py` 九种策略的具体判据**只清点了函数名,未逐个精读
   (该文件 1108 行,不在本片清单内)。

---

## 6. 本片移交项

| 编号 | 锚点 + 摘录 | 一句话现象 | 建议轮次 |
|---|---|---|---|
| H-R9D-B-a | `tools/file_operations.py:1782`:`diff = self._unified_diff(content, new_content, path)` | `patch` 无读禁、无脱敏,返回的 unified diff 把 `auth.json` / 项目 `.env` 的明文密钥原样交给模型(实跑复现,见 ■-3) | 下一轮安全面复核 |
| H-R9D-B-b | `agent/file_safety.py:284`:`os.path.join("cache", "bws_cache.json"),` | 同类的 `cache/op_cache.json`(1Password 明文值)不在任何守卫表里,且因此可被 skill 声明式挂进沙箱(实跑复现,见 ■-2) | 与 R9C D 片 ■-1 合并结案 |
| H-R9D-B-c | `agent/file_safety.py:50`:`str(hermes_home / "cache" / "bws_cache.enc.json"),` | 写禁清单里没有 `auth.json`,`write_file` 可整体覆盖主凭据库;而 `website/docs/user-guide/security.md` 的 “Protected paths (always blocked)” 表把它列为永远拦截(▲-1,文档侧锚点见第 4 节 ▲-1) | 下一轮文档-代码冲突汇总 |
| H-R9D-B-d | `tools/file_operations.py:1071`:`"trap 'rm -f \\\"$tmp\\\"' EXIT; "` | 单引号内的 `\"` 是字面量,trap 触发时 `rm` 删的是一个名字带引号的路径,临时文件从不被清理(最小 bash 复现见 ■-4) | 可与 ■-5 合并 |
| H-R9D-B-e | `tools/file_operations.py:1612`:`if hash_result.exit_code == 0 and hash_result.stdout.strip():` | sha256 写后校验"验证不了"与"验证通过"输出相同,于是 `write_file` 指向已存在目录时报成功、内容落进目录里的隐藏 `.hermes-tmp.*`(实跑复现,见 ■-5) | 下一轮写路径复核 |
| H-R9D-B-f | `tools/file_operations.py:1227`:`truncated = total_lines > end_line` | `total_lines` 来自 `wc -l`(数换行符),无尾换行文件少 1,于是边界情形下末行被静默丢弃且 `truncated=False`(实跑复现,见 ■-7) | 下一轮读路径复核 |
| H-R9D-B-g | `tools/file_tools.py:374`:`container_paths = _uses_container_paths(task_id)` | 容器后端不做 `resolve()` 而读禁判定在宿主 `resolve()`,推定容器内软链可绕过读禁 —— **未取证**,需要 Docker 环境 | 有容器环境的轮次 |
| H-R9D-B-h | `tools/file_operations.py:52`:`WRITE_DENIED_PATHS = build_write_denied_paths(_HOME)` | 模块级写禁快照零消费者,且 `_HOME` 在 import 时求值、不认 HERMES_HOME/profile(全仓搜索见 ◇-2) | 清理面轮次 |

---

## 7. 交付自检

- **基线只读**:全程未在 `/home/user/hermes-agent` 下做任何写操作、git 写操作、包安装。
  交付前实跑:

```verify
git -C /home/user/hermes-agent status --porcelain && echo "GIT-STATUS-EMPTY-OK" && git -C /home/user/hermes-agent rev-parse HEAD
```

  输出:

```console
GIT-STATUS-EMPTY-OK
863e31318553cda8ad61df681d08175364d4164b
```

  (`--porcelain` 无任何输出 = 工作区干净;HEAD 仍是基线 commit。)

- **未装任何包**:所有实验脚本写在会话临时目录,只 `sys.path.insert` 基线路径。
  交付前 venv 包数复核:

```verify
/home/user/hermes-venv/bin/pip list 2>/dev/null | tail -n +3 | wc -l
```

  输出 `87`,与本轮开工时一致(也与 CLAUDE.md 记录的 R8B 环境一致)。
  所有跑基线代码的命令均带 `HERMES_DISABLE_LAZY_INSTALLS=1`。

- **未改 `scripts/`**:本轮只写了 `/home/user/hermes-study/notes/r9d-raw-file-io-safety.md` 一个文件。

- **临时产物**:实验脚本与临时目录全部在 `tempfile.mkdtemp()` 或会话 scratchpad 下,
  未写入 `/home/user/hermes-agent` 或 `/home/user/hermes-study` 的任何其它位置。
