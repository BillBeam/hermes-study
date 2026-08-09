# r9a-raw-verification —— 验证闭环底稿(evidence / stop / hooks 三件套)

> 范围:`agent/verification_evidence.py`(649 行)、`agent/verification_stop.py`(273 行)、
> `agent/verify_hooks.py`(69 行),合计 991 行,基线 `863e313`。
> 本文是证据层底稿:求全求证,不求好读。凡对 hermes-agent 行为的断言,锚点单独成行置于块前。
> 溯源约定:`路径:行号 @ 863e313`。
> 术语先锚一次:**nudge**(轻推)= 系统合成的一条 user 消息,塞回对话让模型再跑一轮;
> **ledger**(台账)= 一个只记录、不判决的 SQLite 事件表;
> **surface**(交互面)= 这轮对话是从哪个入口来的(CLI / TUI / 桌面 / Telegram ……)。

---

## 0. 一句话结论

**这套机制是「闸门」还是「装饰」——答案是:它是一道装在一条路上的闸门,而通向终点的路不止一条。**
在默认配置下(见 §9 ▲1)它甚至连电都没通。逐条判定见 §7。

---

## 1. 场景开场:模型说「做完了」,到底发生了什么

设定:用户在 CLI 里对一个 Node 仓库说「把 `src/app.ts` 里的 off-by-one 修掉」。

1. 模型调 `patch` 工具改了 `src/app.ts`。工具成功返回。
   - 副作用 A(**回合内**):`run_agent._record_file_mutation_result` 把这个路径塞进
     `agent._turn_file_mutation_paths` 这个 per-turn 集合。
   - 副作用 B(**跨回合、落盘**):`tools/file_tools._mark_verification_stale` 调
     `mark_workspace_edited`,在 `~/.hermes/verification_evidence.db` 的
     `verification_state` 表里给 `(session_id, root)` 写一条 `last_edit_at = <now>`。
     这一步的语义是:**这个工作区先前的验证结论,从此刻起作废。**
2. 模型不跑测试,直接输出「已修复,改动很小,应该没问题」,`finish_reason=stop`。
3. 回合循环走到「准备接受最终答案」的那一点,先问 `verify_on_stop_enabled()`:开关开着吗?
4. 开着 → 调 `build_verify_on_stop_nudge(session_id, changed_paths=那个集合, attempts=已推次数)`。
   它拿 `changed_paths` 里每条路径的父目录去问 `project_facts_for`:这是个代码工作区吗?
   是 → 再问 `verification_status(session_id, cwd)`:这个工作区最近一次验证结论是什么?
   台账答:`last_edit_at` 比 `last_event_id` 那条事件的 `created_at` 新 → 状态 `stale`(过期)。
5. 状态 ≠ `passed` → 拼一条 nudge:「[System: 你这轮改了代码,但工作区没有新鲜的通过证据。
   验证状态: stale …… 改动路径: - `src/app.ts` …… 现在就跑 `pnpm run test` / `pnpm run lint` /
   `pytest`,读失败、修代码、总结跑通了什么。如果没法验证,就说清楚具体卡在哪,而不是声称
   工作已经完全验证过。]」
6. 回合循环把模型那条「已修复」的 assistant 消息**照常持久化并作为 interim 推给 UI**
   (用户看得见它想交的那份答案),再把 nudge 作为一条打了 `_verification_stop_synthetic`
   标记的 user 消息追加进去,`final_response = None`,`continue` —— **回合没结束,预算 -1**。
7. 模型第二轮跑了 `pnpm run test`,`terminal_tool` 在前台命令返回后调
   `record_terminal_result`,命令被识别为 canonical `pnpm run test`、`kind=test`、
   `scope=full`、`exit_code=0` → `status=passed`,写进 `verification_events`,
   并把 `verification_state` 的 `last_edit_at` 清成 NULL、`changed_paths_json` 清成 `[]`。
8. 模型再次说完成 → 这次 `verification_status` 返回 `passed` → nudge 返回 `None` → 回合结束。

**什么情况下会被打回去继续干**:这一轮通过 `write_file`/`patch` 落地过文件改动,
且这些改动所在工作区的台账状态不是 `passed`,且开关是开的,且本回合被打回的次数 < 2。
四个条件缺一不可 —— 每一个都是一条绕过路径,§7 逐条拆。

---

## 2. 三件套的分工与接缝全景

```text
        生产者(写台账)                        台账                       消费者(读台账)
  ┌──────────────────────────────┐   ┌──────────────────────┐   ┌───────────────────────────┐
  │ tools/terminal_tool.py:3145  │──▶│ verification_events  │◀──│ agent/verification_stop   │
  │   record_terminal_result     │   │  (命令 + 分类 + 结果) │   │   _verification_snapshot  │
  │   仅前台命令                  │   ├──────────────────────┤   │   → build_..._nudge       │
  ├──────────────────────────────┤   │ verification_state   │   ├───────────────────────────┤
  │ tools/file_tools.py:1752     │──▶│  (session,root) →     │◀──│ tui_gateway/methods_      │
  │   mark_workspace_edited      │   │  last_event_id /      │   │  session.py:281           │
  │   仅 write_file / patch      │   │  last_edit_at /       │   │  "verification.status"    │
  └──────────────────────────────┘   │  changed_paths_json   │   │  只读展示,不判决          │
                                     └──────────────────────┘   └───────────────────────────┘
                                            ▲ 落盘在
                                     $HERMES_HOME/verification_evidence.db

        回合循环的两道门(agent/conversation_loop.py,同一处「即将接受最终答案」)
   ① 7043  verify_on_stop_enabled()  → build_verify_on_stop_nudge()   ← 证据驱动,自带 2 次上限
   ② 7109  has_hook("pre_verify")    → get_pre_verify_continue_message() ← 用户/插件策略,max_verify_nudges 上限
                                        ▲
                                        └── agent/verify_hooks.py 就是这两道门共用的「配置读取 + 文案」小接缝
```

`verify_hooks.py` 的 69 行同时被**两道门**引用,而且是**交叉**引用的:
`max_verify_nudges` 被门②用,`coding_verify_guidance` 被门①(在 `verification_stop.py` 里)用。
这就是它单独成文件的原因,详见 §5。

---

## 3. `agent/verification_evidence.py` —— 台账层

### 3.1 它自己声明的定位:被动

`agent/verification_evidence.py:1 @ 863e313`

```python
"""Coding verification evidence ledger.

This module records what the agent actually proved while working in a code
workspace. It is deliberately passive: it never decides to run a suite, never
blocks completion, and never upgrades targeted checks into "repo green".
"""
```

这条自述在**模块自身范围内**成立(它确实不阻断、也确实把 `scope` 如实记成 `targeted`)。
但它容易被读成一个系统级保证 —— 而系统级上不成立,见 §7.5 与 §9 ◇2。

### 3.2 常量:所有的界都在这

`agent/verification_evidence.py:25 @ 863e313`

```python
_DB_LOCK = threading.Lock()
_MAX_OUTPUT_SUMMARY_CHARS = 2000
_MAX_EVIDENCE_AGE_DAYS = 30
_MAX_EVENTS_PER_SESSION_ROOT = 100
_MAX_TOTAL_UNREFERENCED_EVENTS = 10_000
_AD_HOC_SCRIPT_NAME_PREFIXES = ("hermes-verify-", "hermes-ad-hoc-")
_VERIFY_SCHEMA_VERSION = 1
_SHELL_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||;)\s*")
```

要点:
- `_DB_LOCK` 是**进程内** `threading.Lock`。CLI 与 gateway 是两个进程,共享同一个 db 文件,
  跨进程只靠 SQLite 的 WAL + `busy_timeout=5000` 兜。
- `_SHELL_SPLIT_RE` 只切 `&&` `||` `;`,**不切管道 `|`**。这条正则是 §7.5-a 那个
  「`cmd || true` 被记成 passed」缺陷的直接来源:它把 `||` 当成「分段符」,
  于是 `pnpm test || true` 被切成两段、第一段匹配上 canonical 命令,
  而 `exit_code` 用的是**整条 shell 的**返回码(此时是 `true` 的 0)。
- `_VERIFY_SCHEMA_VERSION` 只被写、**从来没有被读过**(搜索面:全仓 `*.py` 内
  `grep -rn "_VERIFY_SCHEMA_VERSION\|schema_version"` 命中 5 处,3 处在本文件的写入侧,
  2 处在 `hermes_cli/session_recovery.py` 且读的是 `state.db` 的 `SCHEMA_VERSION`,
  与本 db 无关)。即 `meta` 表目前是纯占位的前向兼容位。

### 3.3 一条「证据」的形状

`agent/verification_evidence.py:35 @ 863e313`

```python
@dataclass(frozen=True)
class VerificationEvidence:
    """A classified command result worth recording."""

    command: str
    canonical_command: str
    kind: str
    scope: str
    status: str
    exit_code: int
    cwd: str
    root: str
    session_id: str
    output_summary: str = ""
```

**回答「一条证据是什么」:它不是文件 diff,不是测试报告结构体,而是「一条被识别出来的终端命令
及其退出码 + 输出摘要」。** 具体地:

| 字段 | 取值 | 由谁决定 |
|---|---|---|
| `command` | 模型原样输入的整条 shell 命令 | 模型 |
| `canonical_command` | 从工作区嗅探出的规范命令(如 `pnpm run test`),或字面量 `"ad-hoc verification script"` | `agent/coding_context.detect_project_facts` |
| `kind` | `lint` / `typecheck` / `build` / `format` / `check` / `test` / `ad_hoc` | 关键词匹配 canonical 串 |
| `scope` | `full` / `targeted` | 尾随参数里有没有「长得像目标」的东西 |
| `status` | `passed` / `failed` | **整条 shell 的** `exit_code == 0` |
| `output_summary` | 头 1/3 + 尾 2/3,共 ≤2000 字符 | `_summarize_output` |

**采集点只有一个,存在一个地方,给三方看**:采集点是前台终端命令(§3.9);
存在 `$HERMES_HOME/verification_evidence.db`;三个读者是
(a) `terminal_tool` 立刻回填给模型的 `result_dict["verification_evidence"]`、
(b) 停止门 `verification_stop`、(c) TUI/桌面的 `verification.status` RPC。

### 3.4 命令识别:四层剥皮

**第一层,切段。**

`agent/verification_evidence.py:153 @ 863e313`

```python
def _split_segment_tokens(command: str, *, posix: bool = True) -> list[list[str]]:
    segments: list[list[str]] = []
    for segment in _SHELL_SPLIT_RE.split(command.strip()):
        if not segment:
            continue
        try:
            tokens = shlex.split(segment, posix=posix)
        except ValueError:
            continue
        if tokens:
            segments.append(tokens)
    return segments
```

`shlex.split` 抛 `ValueError`(引号不闭合)时**静默跳过该段**,不是抛出 —— 这是「台账被动」
原则的体现:识别不出来就不记,绝不因为记账失败而影响命令本身。

**第二层,剥无害前缀。**

`agent/verification_evidence.py:191 @ 863e313`

```python
def _strip_command_prefix(tokens: list[str]) -> list[str]:
    """Remove harmless command prefixes before matching canonical commands."""
    remaining = list(tokens)
    if remaining and remaining[0] == "env":
        remaining = remaining[1:]
    while remaining and "=" in remaining[0] and not remaining[0].startswith("-"):
        remaining = remaining[1:]
    while remaining and remaining[0] in {"command", "time", "noglob"}:
        remaining = remaining[1:]
    return remaining
```

顺序是硬编码的:`env` 只在**第一个** token 位置被吃掉,`VAR=x` 可以吃任意多个,
`command`/`time`/`noglob` 在变量之后。所以 `time env CI=1 pnpm test` **匹配不上**
(`time` 在 `env` 前,第一个 if 不成立,第二个 while 因为 `time` 里没有 `=` 不成立,
第三个 while 吃掉 `time` 后剩下 `env CI=1 pnpm test` —— 而 `env` 的处理已经过去了)。
这是一个可复现的识别漏洞,但它只会导致**漏记**(该记的没记 → 更严格),不会导致误放行。

**第三层,等价拼写。**

`agent/verification_evidence.py:203 @ 863e313`

```python
def _equivalent_needles(needle: list[str]) -> list[list[str]]:
    """Return command spellings equivalent to the detected canonical command."""
    candidates = [needle]
    if len(needle) >= 3 and needle[1] == "run":
        package_manager = needle[0]
        script_name = needle[2]
        if package_manager in {"npm", "pnpm", "yarn", "bun"}:
            candidates.append([package_manager, script_name])
    if len(needle) == 1 and "/" in needle[0]:
        candidates.extend([["bash", needle[0]], ["sh", needle[0]]])
    if needle == ["pytest"]:
        candidates.extend(
            [
                ["python", "-m", "pytest"],
                ["python3", "-m", "pytest"],
                ["uv", "run", "pytest"],
                ["poetry", "run", "pytest"],
                ["pipenv", "run", "pytest"],
            ]
        )
    return candidates
```

这是整套机制里最「手工」的一块:canonical 命令是从 `package.json` / `Makefile` 嗅探出来的
**规范拼写**,而模型会写各种简写。这个函数把「`pnpm run test` ≡ `pnpm test`」、
「`scripts/run_tests.sh` ≡ `bash scripts/run_tests.sh`」、「`pytest` ≡ `uv run pytest`」
这三类等价关系写死。**取舍**:白名单可解释、可测试、零误报,代价是每加一个包管理器/运行器
都要改代码;没有任何配置能扩展它(搜索面:全仓 `*.py` 内无任何一处从配置读取等价拼写,
`_equivalent_needles` 无调用方传参)。

**第四层,前缀匹配。**

`agent/verification_evidence.py:226 @ 863e313`

```python
def _find_canonical_match(command: str, canonical_commands: list[str]) -> Optional[tuple[str, list[str]]]:
    """Return ``(canonical, trailing_args)`` for the first detected command."""

    segments = _split_segment_tokens(command)
    for canonical in canonical_commands:
        needle = _canonical_tokens(canonical)
        if not needle:
            continue
        for tokens in segments:
            candidate_tokens = _strip_command_prefix(tokens)
            for candidate in _equivalent_needles(needle):
                if candidate_tokens[:len(candidate)] == candidate:
                    return canonical, candidate_tokens[len(candidate):]
    return None
```

关键契约:**前缀匹配 + 首个命中即返回**。循环顺序是 canonical 外层、segment 内层,
所以返回的是「`verifyCommands` 列表里排最前的那个能匹配上的」,**不是命令行里最先出现的那个**。
`verifyCommands` 的顺序由 `detect_project_facts` 决定(`scripts/run_tests.sh` → package.json 的
`test/tests/lint/typecheck/check/build/fmt/format` → `pytest` → `make *`)。

`agent/coding_context.py:149 @ 863e313`

```python
_VERIFY_TARGETS = ("test", "tests", "lint", "typecheck", "check", "build", "fmt", "format")
_MAX_VERIFY_COMMANDS = 8
```

### 3.5 分类:`kind` 与 `scope`

`agent/verification_evidence.py:242 @ 863e313`

```python
def _kind_for_command(canonical: str) -> str:
    lowered = canonical.lower()
    if any(word in lowered for word in ("lint", "eslint", "ruff")):
        return "lint"
    if any(word in lowered for word in ("typecheck", "tsc", "mypy", "pyright", "ty")):
        return "typecheck"
    if "build" in lowered:
        return "build"
    if "fmt" in lowered or "format" in lowered:
        return "format"
    if "check" in lowered and "test" not in lowered:
        return "check"
    return "test"
```

**注意 `"ty"` 这个子串**:`if any(word in lowered for word in (..., "ty"))` 是**子串**匹配,
不是 token 匹配。任何 canonical 命令里含 `ty` 的都会被判成 `typecheck` ——
例如 `make integrity`、`npm run pretty`、`pnpm run verify`(`verify` 不含 ty,但 `pretty` 含)。
这只影响展示与 TUI 字段,不影响门禁(门禁不看 `kind`,§7.5),所以归为噪声不是缺陷。
判据可复现:`"pretty" .lower()` 含 `"ty"`,而 `pretty` 会因为 `_VERIFY_TARGETS` 不含它
而进不了 verifyCommands —— 需要用户自己在 Makefile 写 `fmt:` 之类才走到这。属于低概率。

`agent/verification_evidence.py:257 @ 863e313`

```python
def _looks_like_target(arg: str) -> bool:
    if not arg or arg.startswith("-") or "=" in arg:
        return False
    return (
        "/" in arg
        or "\\" in arg
        or "::" in arg
        or arg.endswith((".py", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go", ".java"))
        or arg.startswith(("test_", "tests", "spec", "__tests__"))
    )


def _scope_for_args(args: list[str]) -> str:
    return "targeted" if any(_looks_like_target(arg) for arg in args) else "full"
```

**`scope` 的定义是「反着来」的:没有任何一个尾随参数长得像目标 ⇒ `full`。**
这意味着**所有以 `-` 开头的参数都被无视**,于是
`pytest --collect-only`(一个测试都没跑)、`pnpm run test --passWithNoTests`(零测试通过)
都被记成 `scope=full`。见 §7.5-b 的复现。

### 3.6 ad-hoc 通道:没有测试套件时的逃生门

`agent/verification_evidence.py:298 @ 863e313`

```python
def _is_temp_script_path(token: str, root: str | Path | None) -> bool:
    try:
        name = Path(token).expanduser().name
    except Exception:
        return False
    return (
        name.startswith(_AD_HOC_SCRIPT_NAME_PREFIXES)
        and _is_under_temp_dir(token)
        and not _is_under_root(token, root)
    )
```

三个与条件:**文件名前缀** ∈ `("hermes-verify-", "hermes-ad-hoc-")`、**在系统临时目录下**、
**不在工作区根下**。第三个条件是防「模型把脚本写进仓库里冒充临时脚本」。

`agent/verification_evidence.py:310 @ 863e313`

```python
def _ad_hoc_script_args(tokens: list[str], root: str | Path | None) -> Optional[list[str]]:
    candidate_tokens = _strip_command_prefix(tokens)
    if not candidate_tokens:
        return None
    command = candidate_tokens[0]
    if _is_temp_script_path(command, root):
        return candidate_tokens[1:]
    if command in {"python", "python3", "node", "bash", "sh", "ruby", "perl"}:
        for idx, token in enumerate(candidate_tokens[1:], start=1):
            if token == "--":
                continue
            if _is_temp_script_path(token, root):
                return candidate_tokens[idx + 1:]
            if not token.startswith("-"):
                return None
    return None
```

解释器白名单只有 7 个;第一个非 `-` 开头、非 `--` 的 token 必须就是那个临时脚本,
否则立刻放弃(`return None`)—— 防的是 `python -c "..."` 之类。

`agent/verification_evidence.py:328 @ 863e313`

```python
def _find_ad_hoc_match(command: str, root: str | Path | None) -> Optional[list[str]]:
    # Try both posix=True (default) and posix=False (Windows backslash paths)
    # so ad-hoc verification scripts with backslash paths are matched on Windows.
    for posix in (True, False):
        for tokens in _split_segment_tokens(command, posix=posix):
            trailing_args = _ad_hoc_script_args(tokens, root)
            if trailing_args is not None:
                return trailing_args
    return None
```

`posix=False` 那一趟是给 Windows 反斜杠路径的(`shlex.split(posix=True)` 会把 `\` 当转义吃掉)。
配套测试 `tests/agent/test_verification_evidence.py:182` 明确把这条兜底钉住了。

### 3.7 三个公开函数的契约

#### `classify_verification_command(command, *, cwd, session_id, exit_code=0, output="") -> Optional[VerificationEvidence]`

`agent/verification_evidence.py:424 @ 863e313`

```python
    if not command or not isinstance(command, str):
        return None
    try:
        from agent.coding_context import project_facts_for

        facts = project_facts_for(cwd)
    except Exception:
        facts = None
    if not facts:
        return None

    verify_commands = list(facts.get("verifyCommands") or [])
    match = _find_canonical_match(command, verify_commands)
    is_ad_hoc = False
    if match is None and not verify_commands:
        ad_hoc_args = _find_ad_hoc_match(command, facts.get("root"))
        if ad_hoc_args is not None:
            match = ("ad-hoc verification script", ad_hoc_args)
            is_ad_hoc = True
    if match is None:
        return None
```

契约(纯函数,不写库):
1. `cwd` 不在代码工作区(`project_facts_for` 返回 `None`)→ `None`。
2. 工作区**有** canonical 命令时,**ad-hoc 通道被完全关闭**(`and not verify_commands`)。
   即:一个有 `package.json scripts.test` 的仓库里,跑 `/tmp/hermes-verify-x.py` 记不进台账。
   这是一个刻意的收紧 —— 有正规套件就别拿自写脚本充数。
3. `exit_code == 0` ⇒ `passed`,否则 `failed`;非零也**照记**(失败证据也是证据)。

`agent/verification_evidence.py:446 @ 863e313`

```python
    canonical, trailing_args = match
    return VerificationEvidence(
        command=command,
        canonical_command=canonical,
        kind="ad_hoc" if is_ad_hoc else _kind_for_command(canonical),
        scope="targeted" if is_ad_hoc else _scope_for_args(trailing_args),
        status="passed" if int(exit_code) == 0 else "failed",
        exit_code=int(exit_code),
        cwd=str(Path(cwd or ".").resolve()),
        root=str(facts.get("root") or Path(cwd or ".").resolve()),
        session_id=str(session_id or "default"),
        output_summary=_summarize_output(output),
    )
```

ad-hoc 一律 `scope="targeted"` —— 这是「never upgrades targeted checks into repo green」
那句自述在数据层的落实。

#### `record_terminal_result(*, command, cwd, session_id, exit_code, output="") -> Optional[dict]`

先分类,分类不出来直接返回 `None`(不开库、不写盘)。写入是**一个事务里两条语句 + 裁剪**:

`agent/verification_evidence.py:508 @ 863e313`

```python
            conn.execute(
                """
                INSERT INTO verification_state(
                    session_id, root, last_event_id, last_edit_at, changed_paths_json
                ) VALUES (?, ?, ?, NULL, '[]')
                ON CONFLICT(session_id, root) DO UPDATE SET
                    last_event_id = excluded.last_event_id,
                    last_edit_at = NULL,
                    changed_paths_json = '[]'
                """,
                (evidence.session_id, evidence.root, event_id),
            )
```

**这是整个机制最关键、也最容易看漏的一行语义**:任何一条被识别的命令 ——
不管是 lint 还是 test、不管 `scope` 是 targeted 还是 full、**也不管它是 passed 还是 failed** ——
都会把该 `(session, root)` 的 `last_edit_at` 清成 NULL、把累积的 `changed_paths` 清空。
也就是说:**「哪些文件改过了还没验」这份清单,被下一条被识别的命令无条件擦掉,
擦除动作与这条命令验了什么、验没验成功完全无关。**
`status` 会如实记成 `failed`,所以「跑失败的测试」不会骗过门禁;
但「跑一个无关的 lint」会,见 §7.5-c。

返回值 `{"id": ..., **evidence.__dict__, "created_at": ...}`,`terminal_tool` 只取其中四个字段
回填给模型看。

#### `mark_workspace_edited(*, session_id, cwd, paths=None) -> Optional[dict]`

`agent/verification_evidence.py:563 @ 863e313`

```python
            merged = sorted((existing | set(changed_paths)))[-200:]
            conn.execute(
                """
                INSERT INTO verification_state(
                    session_id, root, last_event_id, last_edit_at, changed_paths_json
                ) VALUES (?, ?, NULL, ?, ?)
                ON CONFLICT(session_id, root) DO UPDATE SET
                    last_edit_at = excluded.last_edit_at,
                    changed_paths_json = excluded.changed_paths_json
                """,
                (sid, root, edited_at, json.dumps(merged)),
            )
```

对称地:编辑**不动** `last_event_id`(所以「上一次验证是什么」被保留下来,
`verification_status` 才能算出 `stale` 而不是 `unverified`)。
`[-200:]` 是按**字典序**排完取后 200 个 —— 不是「最近 200 个」。路径多于 200 时,
被丢掉的是字典序靠前的那些(如 `a/...` 会先于 `z/...` 被丢)。这只影响 nudge 里展示的清单
(还要再截到 8 条),不影响判定。

**注意:这个函数不调 `_prune_old_events`**,只有 `record_terminal_result` 调。
所以一个只编辑、从不跑命令的会话,它写下的 state 行要等到**别人**跑命令时才被裁剪。

#### `verification_status(*, session_id, cwd) -> dict`

`agent/verification_evidence.py:629 @ 863e313`

```python
    if event is None:
        return {
            "status": "unverified",
            "evidence": None,
            "root": root,
            "session_id": sid,
            "changed_paths": changed_paths,
        }

    evidence = dict(event)
    if state["last_edit_at"] and state["last_edit_at"] > evidence["created_at"]:
        status = "stale"
    else:
        status = evidence["status"]
```

四种返回状态,契约完整:

| 状态 | 触发条件 |
|---|---|
| `not_applicable` | `project_facts_for(cwd)` 返回 None(不在代码工作区) |
| `unverified` | 没有 state 行,或 state 行的 `last_event_id` 为 NULL / 指向已被裁掉的事件 |
| `stale` | 有事件,但 `last_edit_at > event.created_at` |
| `passed` / `failed` | 直接透传该事件的 `status` |

`stale` 的比较是**ISO-8601 字符串字典序**比较。因为两侧都由 `_utc_now()`
(`datetime.now(timezone.utc).isoformat()`)产生、格式固定带 `+00:00`,字典序等于时间序。
这依赖于「同一台机器上写入」这个前提 —— 台账不跨机同步,所以成立。

### 3.8 保留与裁剪

`agent/verification_evidence.py:352 @ 863e313`

```python
def _prune_old_events(conn: sqlite3.Connection, *, session_id: str, root: str) -> None:
    """Bound ledger growth without deleting the current state pointer."""
    cutoff = _retention_cutoff()
    conn.execute(
        """
        DELETE FROM verification_events
        WHERE session_id = ?
          AND root = ?
          AND id NOT IN (
              SELECT id FROM verification_events
              WHERE session_id = ? AND root = ?
              ORDER BY id DESC
              LIMIT ?
          )
        """,
        (session_id, root, session_id, root, _MAX_EVENTS_PER_SESSION_ROOT),
    )
```

四条 DELETE,依次是:
1. 每 `(session, root)` 只留最新 100 条事件;
2. 删掉 30 天前的 **state** 行(`last_edit_at` 过期,或 `last_edit_at` 为空且其指向的事件过期);
3. 删掉 30 天前、**且没有被任何 state 行引用**的事件;
4. 全局只留最新 10000 条**无引用**事件。

第 2 条会把一个「有事件 + 有旧编辑标记」的 stale 行整行删掉,状态从 `stale` 退化为 `unverified`。
两者都 ≠ `passed`,门禁行为不变。`tests/agent/test_verification_evidence.py:154` 把这个
退化钉成了规格(断言 `status == "unverified"` 且 `changed_paths == []`)。

### 3.9 连接管理:一个被专门修过的 fd 泄漏

`agent/verification_evidence.py:82 @ 863e313`

```python
@contextmanager
def _transaction() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit/rollback on exit, and ALWAYS close it.

    ``sqlite3.Connection.__enter__``/``__exit__`` only commit or roll back the
    transaction; they do not close the connection. Using ``with _connect()``
    alone therefore leaks a connection — and its WAL/SHM file descriptors — on
    every call, deferring the close to the garbage collector, which over a
    long-running process can exhaust ``RLIMIT_NOFILE`` (the cron-ledger sibling
    of this bug was #69567 / PR #69594).
    """
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()
```

事故讲成因果:`with sqlite3.connect(...) as conn:` 在 Python 里**不关连接**,只提交/回滚。
每记一条终端结果就泄漏 db/-wal/-shm 三个 fd,等 GC 才回收;
gateway 这种长跑进程会撞 `RLIMIT_NOFILE`。同一个 bug 在 cron 台账上先炸过(#69567)。
`tests/agent/test_verification_evidence_fd_leak.py` 用一个 `_TrackingConnection` 代理
把「开了几个就得关几个」钉死,含 schema 初始化失败路径。

`_connect()` 里对应的另一半:

`agent/verification_evidence.py:70 @ 863e313`

```python
    try:
        apply_wal_with_fallback(conn, db_label="verification_evidence.db")
        conn.execute("PRAGMA busy_timeout=5000")
        _ensure_schema(conn)
    except Exception:
        # A PRAGMA/DDL failure after a successful connect() must not leak the
        # just-opened connection back to the caller.
        conn.close()
        raise
```

注意 `_ensure_schema` 在**每次**连接时都跑一遍(4 条 `CREATE TABLE/INDEX IF NOT EXISTS`
+ 1 条 `INSERT OR REPLACE` + 1 次 commit)。也就是说每条前台终端命令都要付这个代价。
取舍很清楚:换来的是「不需要任何初始化/迁移入口」,模块完全自足。

---

## 4. `agent/verification_stop.py` —— 策略层

### 4.1 自述:纯策略,不跑任何东西

`agent/verification_stop.py:1 @ 863e313`

```python
"""Turn-end verification guard for coding edits.

This module is intentionally policy-only. It never runs checks itself; it turns
the passive verification ledger into a bounded follow-up when the model tries to
finish immediately after editing code without fresh evidence.
"""
```

**回答问题 3「它是一个停止条件判定器吗」:是,但它只有一半 —— 它是一个「该不该拦」的判定器,
不是「什么算通过」的判定器。** 「什么算通过」全在 §3 的台账里定;
它只把台账的 `status` 字符串跟 `"passed"` 比一次。

### 4.2 非代码路径过滤(修的是一个真实误报)

`agent/verification_stop.py:18 @ 863e313`

```python
# Non-code file extensions whose edits carry no verifiable runtime behavior:
# documentation, prose, and data/markup that no test/build exercises. When a
# turn touches ONLY these, verify-on-stop has nothing to check, so the nudge is
# suppressed (this is fix "C" for the doc/markdown/skill false-positive — a
# SKILL.md or README edit must never demand a /tmp verification script). A turn
# that edits any non-listed path (a real source/code/config file) still nudges.
_NON_CODE_VERIFY_EXTENSIONS = frozenset(
    {
        ".md",
        ".markdown",
        ".mdx",
        ".rst",
        ".txt",
        ".text",
        ".adoc",
        ".asciidoc",
        ".org",
        ".log",
        ".csv",
        ".tsv",
    }
)
```

事故讲成因果:这个 harness 自己会写 skill(`SKILL.md`)、会改 README。
改完 md 之后模型说完成,门禁发现「工作区没有通过证据」,于是命令模型
「去 `/tmp` 写一个 `hermes-verify-` 脚本验证你的 markdown」—— 荒谬且烧 token。
这个 frozenset 就是补丁 C。**没有 `.json` / `.yaml` / `.toml`**:配置文件被当作有行为、会 nudge。

`agent/verification_stop.py:41 @ 863e313`

```python
# Filenames (case-insensitive, extension-less or otherwise) that are pure prose
# even without a recognized doc extension.
_NON_CODE_VERIFY_FILENAMES = frozenset(
    {
        "license",
        "licence",
        "notice",
        "authors",
        "contributors",
        "changelog",
        "codeowners",
    }
)
```

`agent/verification_stop.py:56 @ 863e313`

```python
def _is_non_code_path(raw: str) -> bool:
    """Return True when a changed path is documentation/prose with nothing to verify."""
    try:
        p = Path(str(raw))
    except Exception:
        return False
    suffix = p.suffix.lower()
    if suffix in _NON_CODE_VERIFY_EXTENSIONS:
        return True
    if not suffix and p.name.lower() in _NON_CODE_VERIFY_FILENAMES:
        return True
    return False
```

**无扩展名的文件名单只在 `not suffix` 时才查**,所以 `LICENSE` → True 而 `LICENSE.txt`
走的是扩展名那条(也 True),但 `CHANGELOG.mdx` 走扩展名(True)、
`CODEOWNERS.bak` 两条都不中(False,会 nudge)。
`README` 因为不在文件名单里 → **False,会 nudge**。测试把这条反直觉的结果显式钉住了:

`tests/agent/test_verification_stop.py:227 @ 863e313`

```python
def test_is_non_code_path_classification():
    from agent.verification_stop import _is_non_code_path

    assert _is_non_code_path("docs/SKILL.md") is True
    assert _is_non_code_path("README") is False  # README has no extension and isn't in the prose-filename set
    assert _is_non_code_path("LICENSE") is True
    assert _is_non_code_path("src/app.ts") is False
    assert _is_non_code_path("config.yaml") is False
    assert _is_non_code_path("run_agent.py") is False
```

### 4.3 开关:`verify_on_stop_enabled(config=None) -> bool`

`agent/verification_stop.py:107 @ 863e313`

```python
    env = os.environ.get("HERMES_VERIFY_ON_STOP")
    if env is not None:
        return env.strip().lower() not in {"0", "false", "no", "off"}
    if config is None:
        try:
            from hermes_cli.config import load_config_readonly

            config = load_config_readonly()
        except Exception:
            config = {}
    agent_cfg = (config or {}).get("agent") if isinstance(config, dict) else None
    cfg_val = agent_cfg.get("verify_on_stop") if isinstance(agent_cfg, dict) else None
    if isinstance(cfg_val, bool):
        return cfg_val
    if isinstance(cfg_val, str):
        token = cfg_val.strip().lower()
        if token in {"1", "true", "yes", "on"}:
            return True
        if token in {"0", "false", "no", "off"}:
            return False
        if token == "auto":
            return not _session_is_messaging_surface()
    # Missing or unrecognized value -> surface-aware "auto" default.
    return not _session_is_messaging_surface()
```

优先级契约:**env(存在即生效,不论值)> config 显式 bool > config 显式字符串 > `auto`(面向交互面)**。
两个值得写下来的性质:

- **■1(轻微)**:`env is not None` 而不是 `if env`。`HERMES_VERIFY_ON_STOP=`(空串)
  → `"" not in {"0","false","no","off"}` → **True,强制开启**,并且**压过** config 里显式的 `false`。
  在 `.env` 里留一个空赋值就会静默打开这个功能。复现见 §7.5-e。
- 「auto」的语义外包给了 gateway:

`agent/verification_stop.py:75 @ 863e313`

```python
def _session_is_messaging_surface() -> bool:
    """Whether this turn is delivered over a human messaging channel.

    Verify-on-stop defaults ON for the interactive coding surfaces and
    programmatic callers, and OFF on a conversational platform (Telegram,
    Discord, Slack, ...) where the verification narrative reaches a human as
    chat noise. The surface classification itself is shared with the other
    consumers of this distinction — see
    ``gateway.session_context.session_is_messaging_surface``.
    """
    try:
        from gateway.session_context import session_is_messaging_surface

        return session_is_messaging_surface()
    except Exception:
        # The gateway package is unreachable, so there is no messaging channel
        # to be on. Reporting a local surface keeps verify-on-stop enabled.
        return False
```

**fail-open 的方向是「开启」** —— 这里的兜底是安全侧的(导入失败 ⇒ 当成本地面 ⇒ 门开着)。
与 §7.4 那个 fail-closed 的 `except` 正好相反,值得对照看。

`gateway/session_context.py:418 @ 863e313`

```python
def session_is_messaging_surface() -> bool:
    """Whether this turn is delivered over a human messaging channel.

    Callers use this to decide anything that differs between "the user is
    reading a chat message" and "the user is at a machine they own": whether
    to emit a delivery tag, whether a file has to land somewhere the gateway
    is allowed to send from, whether narration would read as chat noise.

    Resolves ``HERMES_PLATFORM``, then the session platform, then the session
    source, and reports messaging when any of them names a surface outside
    :data:`NON_MESSAGING_SESSION_SURFACES`.
    """
```

`gateway/session_context.py:400 @ 863e313`

```python
NON_MESSAGING_SESSION_SURFACES = frozenset(
    {
        "",
        "api_server",
        "cli",
        "codex",
        "desktop",
        "gateway",
        "kanban",
        "local",
        "msgraph_webhook",
        "tool",
        "tui",
        "webhook",
    }
)
```

即「白名单之外的一切都算聊天面」。cron 触发的会话(source 未设 → `""`)算**非**聊天面,
门是开的。

### 4.4 选哪个工作区来判

`agent/verification_stop.py:151 @ 863e313`

```python
def _verification_snapshot(
    *,
    session_id: str | None,
    changed_paths: list[str],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Return ``(status, facts)`` for the first edited workspace needing proof."""
    try:
        from agent.coding_context import project_facts_for
        from agent.verification_evidence import verification_status
    except Exception:
        return None

    first_snapshot: tuple[dict[str, Any], dict[str, Any]] | None = None
    for cwd in _candidate_cwds(changed_paths):
        facts = project_facts_for(cwd)
        if not facts:
            continue
        status = verification_status(session_id=session_id, cwd=cwd)
        snapshot = (status, facts)
        if first_snapshot is None:
            first_snapshot = snapshot
        if str(status.get("status") or "unverified") != "passed":
            return snapshot
    return first_snapshot
```

契约:遍历所有改动路径推出的候选目录,**第一个「不是 passed」的工作区**胜出;
全都 passed 则返回第一个(于是调用方看到 `passed`,不 nudge)。
一次回合跨两个仓库改代码时,只要**任一个**没验就会被拦 ——
`tests/agent/test_verification_stop.py:114` 钉的就是这条。

`agent/verification_stop.py:133 @ 863e313`

```python
def _candidate_cwds(paths: Iterable[str]) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        if not raw:
            continue
        try:
            path = Path(raw).expanduser()
            candidate = path if path.is_dir() else path.parent
            resolved = str(candidate.resolve())
        except Exception:
            continue
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(Path(resolved))
    return candidates
```

`path.is_dir()` 对**尚未存在**的路径返回 False → 取 `parent`。对一个刚被 `write_file` 新建的
文件,parent 目录已经存在,所以 `resolve()` 正常。**相对路径**会相对**当前进程 cwd** 解析
—— 而 `_turn_file_mutation_paths` 里可能装的是模型给的相对路径(见 §6 的 `files_modified`
优先级)。这是一个潜在的错定位来源,但因为 `file_tools` 优先回传 `resolved_path`/`files_modified`
(绝对路径),实际很少发生。

### 4.5 `build_verify_on_stop_nudge` 契约

`agent/verification_stop.py:205 @ 863e313`

```python
def build_verify_on_stop_nudge(
    *,
    session_id: str | None,
    changed_paths: Iterable[str],
    attempts: int = 0,
    max_attempts: int = 2,
) -> str | None:
    """Return a synthetic follow-up when edited code lacks fresh verification."""
    # Drop documentation/prose paths (markdown, skills, README, LICENSE, ...) —
    # they carry no verifiable behavior, so a turn that touched only those has
    # nothing to verify and must not nudge.
    paths = sorted({str(p) for p in _filter_verifiable_paths(changed_paths)})
    if not paths or attempts >= max_attempts:
        return None
```

五条返回 `None`(= 放行)的路径,按判定顺序:
1. 过滤掉文档后没有路径剩下;
2. `attempts >= max_attempts`(**默认 2,且唯一的生产调用方不传这个参数**,§9 ▲2);
3. `_verification_snapshot` 返回 `None`(没有一条路径落在代码工作区,或 import 失败);
4. 状态就是 `passed`;
5. (隐式)调用它的整个 try 块抛异常 → 调用方吞掉当 `None`。

`agent/verification_stop.py:231 @ 863e313`

```python
    state = str(status.get("status") or "unverified")
    if state == "passed":
        return None

    # Optional shipped coding guidance, only paid when this evidence gate fires.
    try:
        from agent.verify_hooks import coding_verify_guidance

        guidance = coding_verify_guidance()
    except Exception:
        guidance = None
    addendum = f"\n\n{guidance}" if guidance else ""

    if verify_commands:
        command_instruction = (
            "Run the relevant verification command now ("
            + ", ".join(f"`{cmd}`" for cmd in verify_commands[:3])
            + (", ..." if len(verify_commands) > 3 else "")
            + "), read any failure, repair the code, and summarize what passed."
        )
    else:
        temp_dir = os.path.realpath(tempfile.gettempdir())
        command_instruction = (
            "No canonical test/lint/build command was detected. Create a focused "
            f"temporary verification script under `{temp_dir}` using an OS-safe "
            "`tempfile` path with a `hermes-verify-` filename prefix, run it "
            "against the changed behavior, clean it up when possible, and "
            "summarize it explicitly as ad-hoc verification rather than suite "
            "green."
        )
```

两条分支正好对应 §3.7 契约 2:**有 canonical 命令就报出前三条让它跑;
没有就把 ad-hoc 通道的三个准入条件(临时目录 / `hermes-verify-` 前缀 / 针对改动行为)
原样念给模型听**。这是一处很干净的设计:**门禁的提示词就是识别器的规格说明**,
模型照做就一定能被识别到,不会出现「我验了但你不认」。
`os.path.realpath` 是为了把 macOS 上 `/tmp → /private/tmp` 这种符号链接解开,
因为识别侧 `_is_under_temp_dir` 用的是 `resolve()`;
`tests/agent/test_verification_stop.py:147` 用一个 symlink 临时目录把这条钉住了。

`agent/verification_stop.py:262 @ 863e313`

```python
    return (
        "[System: You edited code in this turn, but the workspace does not have "
        "fresh passing verification evidence yet.\n\n"
        f"Verification status: {_status_detail(status)}\n\n"
        f"Changed paths:\n{_format_changed_paths(paths)}\n\n"
        f"{command_instruction} If verification is not possible, explain the "
        "concrete blocker instead of claiming the work is fully verified."
        f"{addendum}]"
    )
```

**最后一句是整个机制的软肋、也是它的诚实之处**:「如果没法验证,就说清楚具体卡在哪」
—— 模型完全可以照这句话回一段「卡在没装依赖」然后收工。见 §7.2。

`_status_detail` 把上一次的命令与输出摘要(再截到 1200 字符)一起塞进 nudge:

`agent/verification_stop.py:186 @ 863e313`

```python
def _status_detail(status: dict[str, Any]) -> str:
    state = str(status.get("status") or "unverified")
    evidence = status.get("evidence") if isinstance(status.get("evidence"), dict) else None
    if not evidence:
        return state

    command = evidence.get("canonical_command") or evidence.get("command")
    summary = str(evidence.get("output_summary") or "").strip()
    parts = [state]
    if command:
        parts.append(f"last command `{command}`")
    if summary:
        max_summary = 1200
        if len(summary) > max_summary:
            summary = summary[:max_summary].rstrip() + "\n... [truncated]"
        parts.append(f"last output:\n{summary}")
    return "\n".join(parts)
```

于是「上一轮测试失败了」这个信息会**跨回合**被送回模型眼前 —— 台账在这里起的是
「短期记忆」的作用,而不只是审计。

---

## 5. `agent/verify_hooks.py` —— 69 行的接缝,两端在哪

**回答问题 4:它既不是钩子注册点,也不是钩子实现,而是一个「配置读取 + 文案常量」的公共小模块。**
真正的钩子注册在 `hermes_cli/plugins.py`(`get_pre_verify_continue_message`,定义在 2323 行)、
触发在 `agent/conversation_loop.py:7109`。这个文件之所以单独存在,是因为它被**两条互不相识的路**
各取一半:

`agent/verify_hooks.py:1 @ 863e313`

```python
"""Verification-loop helpers for the ``pre_verify`` round-end gate.

When the agent has edited code and is about to verify/finish, the loop fires the
``pre_verify`` hook (user directives resolved by
:func:`hermes_cli.plugins.get_pre_verify_continue_message`). A directive keeps
the agent going one more turn — run a check, defer it, tidy the diff — instead of
stopping immediately.

The shipped coding guidance lives on the evidence-based verification-stop nudge
(``agent/verification_stop.py``), not as a second default stop gate. That keeps
the default token cost tied to the existing "missing verification evidence"
decision while preserving ``pre_verify`` for user/plugin policy.
"""
```

**接缝的两端**:

| 导出 | 被谁 import | 用途 |
|---|---|---|
| `max_verify_nudges` | `agent/conversation_loop.py:7105`(门②) | 限制 `pre_verify` 连续放行次数 |
| `coding_verify_guidance` / `CODING_VERIFY_GUIDANCE` | `agent/verification_stop.py:237`(门①) | 拼进证据 nudge 的尾巴 |
| `DEFAULT_MAX_VERIFY_NUDGES` | 仅测试与本文件 | 默认值 3 |

搜索面:全仓 `grep -rn "verify_hooks"` 的非测试命中只有
`agent/conversation_loop.py:7105` 与 `agent/verification_stop.py:237` 两处。
**它是一个「把默认指导文案从门② 搬到门① 上」这个历史决定的残留物**:
docstring 第二段明确说了「shipped guidance 不做成第二个默认停止门」——
如果做成默认 `pre_verify` 钩子,那么每个改过代码的回合都会**无条件**多烧一轮;
挂在门① 上则只在「真的缺证据」时才付这个 token 成本。

`agent/verify_hooks.py:21 @ 863e313`

```python
DEFAULT_MAX_VERIFY_NUDGES = 3

# Shipped guidance appended to the verification-stop nudge when code lacks fresh
# verification evidence. Wording mirrors the user-facing "clean your work"
# workflow, but does not create its own extra model turn.
CODING_VERIFY_GUIDANCE = (
    "[Coding] Before you run tests/linters or call this done: if this is "
    "creative UI/visual work, hold off on tests and linters until the user says "
    "they like the result or you're about to commit. And before every commit, "
    "clean your work: keep it KISS/DRY, match the surrounding code style, and be "
    "elitist, shorthand, clever, concise, efficient, and elegant."
)
```

`agent/verify_hooks.py:35 @ 863e313`

```python
def max_verify_nudges(config: Optional[dict[str, Any]] = None) -> int:
    """Bound on consecutive ``pre_verify`` continue directives per turn (>= 0)."""
    agent_cfg = _agent_cfg(config)
    raw = agent_cfg.get("max_verify_nudges")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_MAX_VERIFY_NUDGES
```

契约细节:`int(raw)` 能吃 `"2"`(字符串)、能把 `-1` 夹到 0、`None`/`"x"` 回落到 3。
`int(2.9)` = 2(截断,不报错)。测试钉住了前四种。

`agent/verify_hooks.py:45 @ 863e313`

```python
def coding_verify_guidance(config: Optional[dict[str, Any]] = None) -> Optional[str]:
    """Return the optional guidance appended to verification-stop nudges."""
    if not is_truthy_value(_agent_cfg(config).get("verify_guidance", True), default=True):
        return None
    return CODING_VERIFY_GUIDANCE
```

`agent/verify_hooks.py:52 @ 863e313`

```python
def _agent_cfg(config: Optional[dict[str, Any]]) -> dict[str, Any]:
    if config is None:
        try:
            from hermes_cli.config import load_config

            config = load_config()
        except Exception:
            config = {}
    agent_cfg = (config or {}).get("agent") if isinstance(config, dict) else None
    return agent_cfg if isinstance(agent_cfg, dict) else {}
```

**◇1(代码有、文档无)**:这里用的是 `load_config()`(带 deepcopy 的慢路径),
而 `verification_stop.verify_on_stop_enabled` 用的是 `load_config_readonly()`(免 deepcopy 的快路径)。
两个函数在**同一次 nudge 构建里前后脚被调用**,却走了两条不同成本的配置读取路径。

`hermes_cli/config.py:3132 @ 863e313`

```python
def load_config_readonly() -> Dict[str, Any]:
    """Fast-path variant of ``load_config()`` for callers that ONLY READ.

    Returns the cached config dict directly without the defensive deepcopy
    that ``load_config()`` applies. **Mutating the returned dict (or any
    nested structure) corrupts the in-process cache for every subsequent
    caller** — only use this when you are absolutely sure your code path
    will not write to the result. If you need to mutate or pass to
    ``save_config``, call ``load_config()`` instead.
```

`verify_hooks._agent_cfg` 同样只读、同样不写 —— 用 readonly 变体是安全的。
这属于遗漏而非缺陷(每次 nudge 多付约 135µs),记 ◇ 不记 ■。

---

## 6. 与回合循环 / 迭代预算的衔接:逐行

### 6.1 数据从哪来:`_turn_file_mutation_paths`

`agent/turn_context.py:1136 @ 863e313`

```python
    # Per-turn file-mutation verifier state.
    agent._turn_failed_file_mutations = {}
    agent._turn_file_mutation_paths = set()
    agent._verification_stop_nudges = 0
    agent._pre_verify_nudges = 0
```

每回合开头清零 —— 所以「2 次上限」是**每回合**的,不是每会话的。

`run_agent.py:3416 @ 863e313`

```python
        landed = file_mutation_result_landed(tool_name, result)
        if landed:
            changed = getattr(self, "_turn_file_mutation_paths", None)
            if changed is not None:
                changed.update(_extract_landed_file_mutation_paths(tool_name, args, result))
```

而这个方法的第一行就是整套机制**最重要的一个界**:

`agent/tool_result_classification.py:9 @ 863e313`

```python
FILE_MUTATING_TOOL_NAMES = frozenset({"write_file", "patch"})
```

**只有两个工具会让这个集合非空。** 见 §7.1。

### 6.2 门① 的挂载点

`agent/conversation_loop.py:7037 @ 863e313`

```python
                try:
                    from agent.verification_stop import (
                        build_verify_on_stop_nudge,
                        verify_on_stop_enabled,
                    )

                    if verify_on_stop_enabled():
                        _verify_nudge = build_verify_on_stop_nudge(
                            session_id=getattr(agent, "session_id", None),
                            changed_paths=getattr(agent, "_turn_file_mutation_paths", set()),
                            attempts=getattr(agent, "_verification_stop_nudges", 0),
                        )
                    else:
                        _verify_nudge = None
```

**`max_attempts` 没有被传** —— 生产路径永远吃 `build_verify_on_stop_nudge` 的默认值 2。
搜索面:全仓 `grep -rn "build_verify_on_stop_nudge"` 的 4 处非定义命中里,
只有 `conversation_loop.py:7044` 一处是生产调用,其余在 `agent/verification_stop.py`
自身的 `__all__` 与测试里;测试 `tests/agent/test_verification_stop.py:196` 显式传了
`max_attempts=2` 来验边界。

`agent/conversation_loop.py:7055 @ 863e313`

```python
                if _verify_nudge:
                    agent._verification_stop_nudges = (
                        getattr(agent, "_verification_stop_nudges", 0) + 1
                    )
                    final_msg["finish_reason"] = "verification_required"
```

### 6.3 与迭代预算的两处衔接

**衔接点 A:nudge 走的是 `continue`,所以它消耗预算。**

`agent/conversation_loop.py:1415 @ 863e313`

```python
    while (api_call_count < agent.max_iterations and agent.iteration_budget.remaining > 0) or agent._budget_grace_call:
```

`agent/iteration_budget.py:37 @ 863e313`

```python
    def consume(self) -> bool:
        """Try to consume one iteration.  Returns True if allowed."""
        with self._lock:
            if self._used >= self.max_total:
                return False
            self._used += 1
            return True
```

门① 的 `continue` 回到 `while` 顶部 → `api_call_count += 1` → `iteration_budget.consume()`。
所以**每次 nudge 至少吃掉 1 次迭代**,2 次上限最多吃 2 次。这就是「bounded」的物理含义:
上限不只是计数器,预算本身也是硬顶。

**衔接点 B:预算被 nudge 吃光时,那份「被扣下的答案」要还回来。**

`agent/conversation_loop.py:7089 @ 863e313`

```python
                    _pending_verification_response = final_response
                    _pending_verification_response_previewed = (
                        agent._interim_content_was_streamed(final_response or "")
                    )
                    final_response = None
                    continue
```

`agent/turn_finalizer.py:104 @ 863e313`

```python
    continuation_budget_exhausted = (
        final_response is None
        and bool(_pending_verification_response)
        and budget_fallback_eligible
    )

    iteration_limit_fallback = False
    preserved_verification_fallback = False
    if continuation_budget_exhausted:
        # A verification/continuation gate deliberately withheld a composed
        # answer, then consumed the remaining budget before producing a newer
        # one. Preserve that exact answer instead of replacing it with another
        # fallible model call. The explicit pending value is the provenance
        # guard: unrelated error/recovery exits can never enter this branch.
        final_response = _pending_verification_response
```

事故讲成因果(#61631):门① 把模型composed 好的答案扣下、`final_response = None`,
然后 nudge 把预算耗尽 → 回合结束时 `final_response` 是 None → 旧代码走
「预算耗尽兜底」再叫一次模型要摘要 → **用户拿到的是一句敷衍摘要,而那份真正写好的报告被丢了**。
修法是把被扣下的答案显式存进 `_pending_verification_response`,
预算耗尽时**原样还回去**,而不是再赌一次模型调用。
`_pending_verification_response` 非空同时充当「provenance guard」:
只有验证门扣过答案才可能进这个分支,别的错误/恢复退出进不来。
`tests/run_agent/test_verification_continuation_budget.py` 对门①、门② 各钉了一个 E2E。

**衔接点 C(合成消息不能污染持久化)。**

`agent/turn_finalizer.py:50 @ 863e313`

```python
_VERIFICATION_CONTINUATION_FLAGS = (
    "_verification_stop_synthetic",
    "_pre_verify_synthetic",
)
```

nudge 那条 user 消息带标记 → 被 `_drop_verification_continuation_scaffolding` 从返回/存活历史里
剥掉;而模型那条「我做完了」的 assistant 消息**不带标记**、照常入库并推给 UI。
`agent/agent_runtime_helpers.py:608` 另有一条:两条相邻 assistant 消息里,
前一条若是 `verification_required`/`verify_hook_continue` 候选,**用后一条替换**而非合并,
避免「过早的完成宣告」被拼进最终答案。

---

## 7. 可被绕过吗 —— 明确判定

**判定:它是一道真闸门(会真的把回合拉回去、真的消耗预算、真的改 `finish_reason`),
但只装在一条路上;通向「回合结束」的其他路都不问它。默认配置下这道门是关电的。**

按「绕过成本」从低到高:

### 7.1 ◆ 硬绕过 A:不用 `write_file` / `patch` 改文件

`FILE_MUTATING_TOOL_NAMES` 只有两个成员(§6.1)。因此以下方式改代码,
`_turn_file_mutation_paths` 保持为空集,门① 在第一行 `if not paths` 就返回 None:

- `terminal_tool` 里 `sed -i` / `cat > f <<'EOF'` / `git apply` / `patch -p1`
- `execute_code`(程序化工具调用)里 `open(path,'w').write(...)`
- 任何 MCP 文件系统工具
- 子代理(`delegate_task`)代改 —— 子代理有自己的 agent 实例与自己的 `_turn_file_mutation_paths`

而且这条路是**双失效**的:`tools/file_tools._mark_verification_stale` 也只挂在 file_tools 的
三个写入点上,所以台账里连 `last_edit_at` 都不会被写 —— 门禁不仅没被触发,
连「这个工作区脏了」都不知道。

搜索面(全仓 `*.py`,含 tests):

```verify
$ grep -rn "mark_workspace_edited" --include='*.py' .
./agent/verification_evidence.py:526:def mark_workspace_edited(
./tests/agent/test_verification_evidence.py:9:    mark_workspace_edited,
./tests/agent/test_verification_evidence.py:159:    mark_workspace_edited(
./tests/agent/test_verification_stop.py:8:    mark_workspace_edited,
./tests/agent/test_verification_stop.py:130:    mark_workspace_edited(session_id="s1", cwd=project_b, paths=[changed_b])
./tests/agent/test_verification_stop.py:194:    mark_workspace_edited(session_id="s1", cwd=tmp_path, paths=[changed])
./tests/agent/test_verification_stop.py:216:    mark_workspace_edited(session_id="s1", cwd=tmp_path, paths=[code])
./tests/agent/test_verification_evidence_fd_leak.py:81:    ve.mark_workspace_edited(session_id="s1", cwd=tmp_path, paths=["mod.py"])
./tools/file_tools.py:1734:        from agent.verification_evidence import mark_workspace_edited
./tools/file_tools.py:1752:        mark_workspace_edited(session_id=session_id or task_id, cwd=cwd, paths=paths)
```

唯一的生产写入点:

`tools/file_tools.py:1723 @ 863e313`

```python
def _mark_verification_stale(
    task_id: str,
    resolved_paths: list[str],
    session_id: str | None = None,
) -> None:
    """Best-effort note that successful edits made prior verification stale."""
```

它在 `tools/file_tools.py` 内被调用 3 次(1798 / 1825 / 1990)。

### 7.2 ◆ 硬绕过 B:`api_mode == "codex_app_server"` 整条路不问门禁

`agent/conversation_loop.py:1401 @ 863e313`

```python
    # Optional opt-in runtime: if api_mode == codex_app_server, hand the
    # turn to the codex app-server subprocess (terminal/file ops/patching
    # all run inside Codex). Default Hermes path is bypassed entirely.
    # See agent/transports/codex_app_server_session.py for the adapter
    # and references/codex-app-server-runtime.md for the rationale.
    if agent.api_mode == "codex_app_server":
        return agent._run_codex_app_server_turn(
```

这是 `run_conversation` 的**早退**,发生在主循环之前 6600 行,门① 门② 都在主循环里,
完全不可达。注释自己写了「Default Hermes path is bypassed entirely」——
但它说的是「终端/文件操作都在 Codex 里跑」,读者不会自动推出「所以验证门也没了」。

搜索面(该路径的实现体):

```verify
$ awk 'NR>=7938 && NR<=8120' run_agent.py | grep -n "verif\|_turn_file_mutation"
(无输出)
$ grep -c "" agent/codex_runtime.py
1452
$ grep -n "verif\|_turn_file_mutation" agent/codex_runtime.py
243:        elif hasattr(compressor, "_verify_compaction_cleared_threshold"):
244:            compressor._verify_compaction_cleared_threshold = True
```

即转发目标 `agent/codex_runtime.py` 全文 1452 行里,`verif` 只有两处压缩相关命中,
与验证闭环无关。**这就是 R8D 反复撞见的形状:守卫存在,但有一条路不问它。**

### 7.3 ◆ 软绕过:nudge 是提示,不是拒绝

nudge 的最后一句原文(§4.5 已引)明确给出出口:
「If verification is not possible, explain the concrete blocker instead of claiming
the work is fully verified.」模型只要在第二轮说一句「无法验证,因为依赖未安装」,
回合就正常结束。门禁**不检查**第二轮是否真的跑了命令、也不检查它给出的 blocker 是否属实。
第二轮结束时门① 会再判一次;第三次时 `attempts=2 >= max_attempts=2` → 直接放行。
**所以上限是:一个不肯验证的模型,最多被多问 2 次。**

### 7.4 ◆ 失败即放行(fail-open)

`agent/conversation_loop.py:7051` 起的 `except Exception` 把 `_verify_nudge` 置 None
(见 §6.2 引用块所属的 try 块),`build_verify_on_stop_nudge` 内部对
`coding_verify_guidance` 的 import 也是 try/except。台账读不出来、db 锁死、
`coding_context` 抛异常 —— 一律放行。方向是「不阻塞用户」,与 §4.3 那个 fail-open-to-ON
方向相反,两处都合理但需要同时记住。

### 7.5 ◆ 证据本身可被廉价制造:五个可复现向量

以下五段都是**在临时 `HERMES_HOME` 下**跑的,不触碰基线,可零成本复现。

**(a) ■2:`exit_code` 用的是整条 shell 的返回码,`|| true` / `; true` 直接把失败洗成 passed。**
根因是 `_SHELL_SPLIT_RE` 把 `||`/`;` 当分段符切开、匹配第一段,
而 `status` 用的是调用方传进来的整体 `returncode`(`tools/terminal_tool.py:3149`)。

```verify
$ cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python - <<'PY'
import json, os, sys, tempfile, pathlib
T = pathlib.Path(tempfile.mkdtemp()); os.environ["HERMES_HOME"] = str(T/".hermes")
sys.path.insert(0, "/home/user/hermes-agent")
p = T/"proj"; p.mkdir()
p.joinpath("package.json").write_text(json.dumps({"scripts": {"test": "vitest", "lint": "eslint ."}}))
p.joinpath("pnpm-lock.yaml").write_text("")
from agent.verification_evidence import classify_verification_command as c
for cmd in ("pnpm test || true", "pnpm test; true", "pnpm run test --passWithNoTests"):
    e = c(cmd, cwd=p, session_id="s", exit_code=0)
    print(f"{cmd!r:38} -> kind={e.kind} scope={e.scope} status={e.status}")
PY
'pnpm test || true'                    -> kind=test scope=full status=passed
'pnpm test; true'                      -> kind=test scope=full status=passed
'pnpm run test --passWithNoTests'      -> kind=test scope=full status=passed
```

**(b) ■3:零测试的调用被记成 `scope=full` 的通过。** 上面第三行即是;
`pytest --collect-only`、`pytest -k zzz_no_such_test` 同理(实测均为
`kind=test scope=full status=passed`)。根因是 `_looks_like_target` 忽略一切 `-` 开头的参数(§3.5)。

**(c) ■4:一次无关的 lint 通过,会清掉代码编辑留下的「待验」标记,门禁随即放行。**
根因是 `record_terminal_result` 无条件 `last_edit_at = NULL, changed_paths_json='[]'`(§3.7)。

```verify
$ cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python - <<'PY'
... (同上建 Node 工程 p) ...
from agent.verification_evidence import mark_workspace_edited, record_terminal_result, verification_status
from agent.verification_stop import build_verify_on_stop_nudge
code = str(p/"src"/"app.ts")
mark_workspace_edited(session_id="s", cwd=p, paths=[code])
print("after edit:", verification_status(session_id="s", cwd=p)["status"])
record_terminal_result(command="pnpm run lint", cwd=p, session_id="s", exit_code=0, output="ok")
st = verification_status(session_id="s", cwd=p)
print("after lint:", st["status"], "kind=", st["evidence"]["kind"], "changed_paths=", st["changed_paths"])
print("nudge:", build_verify_on_stop_nudge(session_id="s", changed_paths=[code]))
PY
after edit: unverified
after lint: passed kind= lint changed_paths= []
nudge: None
```

注:文档把 lint 明确列为可接受证据(§9 引 configuration.md:943 「a passing test run, build,
lint, etc.」),所以**这不是文档-代码矛盾**;但它意味着 `kind`/`scope` 两个字段
**在门禁侧完全没有被消费**——它们只被记录、只被 TUI 展示。见 §9 ◇2。

**(d) 设计使然:没有 canonical 套件时,模型自己写的、零断言的脚本就是「通过证据」。**

```verify
$ cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python - <<'PY'
... (建 p,package.json 内容为 "{}" —— 无 scripts) ...
s = pathlib.Path(tempfile.gettempdir())/"hermes-verify-noop.py"; s.write_text("print('ok')\n")
record_terminal_result(command=f"python {s}", cwd=p, session_id="s", exit_code=0, output="ok"); s.unlink()
PY
verifyCommands = []
status = passed kind = ad_hoc scope = targeted
nudge  = None
```

这是 §4.5 的 nudge 文案主动教给模型的路径,`tests/agent/test_verification_stop.py:170`
把它钉成了规格(`test_ad_hoc_pass_satisfies_no_suite_stop_loop`)。
设计意图明确(有胜于无、且如实标 `ad_hoc`/`targeted`),但要清楚:
**这一支的「证据」完全由被审查方自己出题、自己交卷。**

**(e) ■1:`HERMES_VERIFY_ON_STOP=`(空串)强制开启,并压过配置里的显式 `false`。**

```verify
$ ... os.environ["HERMES_SESSION_PLATFORM"]="telegram"; os.environ["HERMES_VERIFY_ON_STOP"]="" ...
env='' , config False -> True
env unset, config False -> False
```

### 7.6 ◆ 后台命令不产生证据

`tools/terminal_tool.py` 的 `background=True` 分支在 spawn 之后就返回,
到不了 3145 的记录点(`record_terminal_result` 的 docstring 也自称
"Record a **foreground** terminal result")。这不是漏洞而是收紧:
在后台跑测试**得不到**通过证据,门禁照拦。

`tools/terminal_tool.py:3142 @ 863e313`

```python
            try:
                from agent.verification_evidence import record_terminal_result

                evidence = record_terminal_result(
                    command=command,
                    cwd=command_cwd,
                    session_id=session_id or task_id or effective_task_id or "default",
                    exit_code=returncode,
                    output=output,
                )
                if evidence:
                    result_dict["verification_evidence"] = {
                        "status": evidence.get("status"),
                        "kind": evidence.get("kind"),
                        "scope": evidence.get("scope"),
                        "canonical_command": evidence.get("canonical_command"),
                    }
            except Exception:
                logger.debug("verification evidence recording failed", exc_info=True)
```

两点顺带:
- `session_id or task_id or effective_task_id or "default"` 的回落链,与
  `file_tools` 侧的 `session_id or task_id` **不完全相同**。当 `session_id` 为空、
  `task_id` 也为空而 `effective_task_id` 非空时,两侧会写到不同的 `session_id` 分区,
  台账对不上(表现为「明明跑过测试却还是 unverified」)。这是一个真实但窄的错位面;
  `tests/agent/test_verification_evidence.py:120` 反过来把「session_id 分区隔离」
  当成正确行为钉住了(`conversation` 分区 stale、`turn` 分区 unverified)。
- `cwd=command_cwd` 是**宿主机路径语义**。当终端后端是 Docker/SSH/远程时,
  `command_cwd` 是容器内路径,`project_facts_for` 却在宿主机文件系统上解析它。
  这条路上要么解析失败(→ 不记账,收紧)、要么误命中同名宿主目录(→ 记到错工作区)。
  代码里此处**没有任何 env_type 判别**(搜索面:`tools/terminal_tool.py` 内
  `grep -n "env_type"` 在 2900–3160 区间只有 2975/2980/3013/3041 四处,均为日志与 sudo 处理,
  记录点 3142–3160 之间无命中)。列为移交项 H-R9A-1。

---

## 8. 配套测试:钉住了什么、没钉住什么

环境(按 CLAUDE.md 要求同时记):`/home/user/hermes-venv`,`pip list` 去两行表头后 **87** 个包,
`site-packages/*.dist-info` 亦为 **87**。

```console
$ cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python -m pytest -p no:cacheprovider -q \
    tests/agent/test_verification_evidence.py tests/agent/test_verification_stop.py \
    tests/agent/test_verify_hooks.py tests/agent/test_verification_stop_caching.py \
    tests/agent/test_verification_evidence_fd_leak.py tests/run_agent/test_verification_continuation_budget.py
......................................                                   [100%]
38 passed in 9.70s
```

| 测试文件 | 钉住的行为 |
|---|---|
| `tests/agent/test_verification_evidence.py` | lint 不被冒充成 full test;`env CI=1 bash scripts/run_tests.sh <目标>` 匹配且 scope=targeted,而 `echo <同一串>` 不匹配;ad-hoc 脚本记成 `ad_hoc/targeted/passed`;`write_file` 按 **session_id 分区**置 stale;30 天前的纯编辑 state 行被裁掉后退化为 `unverified`;Windows 反斜杠 ad-hoc 路径靠 `posix=False` 兜住 |
| `tests/agent/test_verification_stop.py` | env 强制开启压过聊天面;`auto` 在 cli/tui/desktop/codex/local 五个 source 上为 True;**经真实 `load_config()` 的 E2E**:默认值确为 `"auto"`、cli→True、telegram→False;跨两个工作区时任一未验即 nudge;无套件分支的临时目录用 `realpath`(symlink 测试);ad-hoc 通过即放行;`attempts=2, max_attempts=2` 时返回 None;文档+代码混合编辑仍 nudge 且**文档路径不出现在清单里**;`_is_non_code_path` 六条分类 |
| `tests/agent/test_verify_hooks.py` | `max_verify_nudges` 的默认/强转/夹 0/坏值回落;`coding_verify_guidance` 默认开、认 `"yes"`、`False` 关 |
| `tests/agent/test_verification_stop_caching.py` | 两个 synthetic 标记在 `_EPHEMERAL_SCAFFOLDING_FLAGS` 里;DB flush 与 JSON log **只**丢 nudge、保留 assistant 候选 |
| `tests/agent/test_verification_evidence_fd_leak.py` | 三条路径(正常、事务内异常、schema 初始化失败)下开=关 |
| `tests/run_agent/test_verification_continuation_budget.py` | 门①/门② 各一条:预算在 nudge 中耗尽时,**原答案被原样保留**而不是被兜底摘要替换 |
| `tests/test_tui_gateway_server.py:12539` | `verification.status` RPC 返回 `passed` + `canonical_command` + `scope=full`;非工作区 cwd 返回 `not_applicable` |

**没有被任何测试钉住的**(逐条即 §7 的绕过面):
1. 「不用 write_file/patch 改代码 ⇒ 不 nudge」—— 没有任何测试断言这条边界;
2. `codex_app_server` 路径不经过门禁 —— 无测试;
3. `|| true` / `--passWithNoTests` / `--collect-only` 的 exit-code 语义 —— 无测试;
4. 「lint 通过清掉代码编辑的 stale」—— 无测试(有测试覆盖 lint 的 `kind`,但没覆盖它对 state 的副作用);
5. `HERMES_VERIFY_ON_STOP=""` 的空串语义 —— 无测试;
6. 远程/Docker 终端后端下 `cwd` 语义错位 —— 无测试;
7. `record_terminal_result` 与 `_mark_verification_stale` 的 `session_id` 回落链不一致 —— 无测试。

另外注意两个测试文件里有多段连续空行(`test_verification_evidence.py` 的 29–34、59–61、
84–86、109–119、149–153,`test_verification_stop.py` 的 46–56、62–75、82–90、111–113、
140–146、167–169、204–210),形状上像是删掉用例后留下的空档 —— 说明这套测试
**曾经更密**,现存的是被裁剪过的子集。这是观察,不是结论。

---

## 9. 文档 vs 代码

### ▲1 —— `configuration.md` 把默认状态讲成了「off 就是有效默认」,但新装是 auto(=CLI 上开)

整段判定(它归 `## Verify-on-Stop (coding verification)` 这个二级标题管):

`website/docs/user-guide/configuration.md:953 @ 863e313`

> `verify_on_stop` accepts `true` (on everywhere), `false` (off), or `"auto"` (on for interactive coding surfaces — CLI, TUI, desktop — and programmatic callers; off for messaging surfaces like Telegram/Discord where the verification narrative reads as chat noise). The config migration turns it **off** on existing installs, so treat off as the effective default and opt in explicitly. The `HERMES_VERIFY_ON_STOP` env var overrides the config value when set.

**判定:第一句与第三句为真;第二句「treat off as the effective default」只对老装机为真,
对全新安装为假。** 代码侧:

`hermes_cli/config_defaults.py:149 @ 863e313`

```python
        # Verification closure: after the agent edits files in a code workspace,
        # do not accept a final answer until fresh verification evidence exists
        # or the agent explains why it cannot run checks. The loop is bounded
        # and uses the passive verification ledger. Default is "auto" —
        # surface-aware: on for interactive coding surfaces (CLI, TUI, desktop)
        # and programmatic callers, off for conversational messaging surfaces
        # (Telegram, Discord, etc.) where the verification narrative would reach
        # a human as chat noise. Doc/markdown/skill-only edits never fire it.
        # Set true to force on everywhere, or false to disable.
        "verify_on_stop": "auto",
```

迁移只在**已有 config.yaml 且版本 <31/<32** 时改写:

`hermes_cli/config_migrations.py:555 @ 863e313`

```python
        raw_agent = {}
    cur = raw_agent.get("verify_on_stop")
    is_auto_sentinel = (
        isinstance(cur, str) and cur.strip().lower() == "auto"
    )
    # Only flip the non-committal states; leave explicit bool/on/off alone.
    if cur is None or is_auto_sentinel:
        raw_agent["verify_on_stop"] = False
        config["agent"] = raw_agent
```

而 `tests/agent/test_verification_stop.py:91` 那条 E2E 在一个**空 HERMES_HOME** 上跑
`load_config()`,断言 `merged["agent"]["verify_on_stop"] == "auto"` 且 cli 面为 True ——
即新装机上门是**开的**。归 ▲ 而非 ◎:文档给出的是一个会让读者对新装机做出错误判断的口径。

### ▲2 —— `max_verify_nudges` 并不管内建 verify-on-stop,注释里的「built-in +」为假

`website/docs/user-guide/configuration.md:949 @ 863e313`

>   max_verify_nudges: 3         # Cap on consecutive continue nudges per turn (built-in + pre_verify hooks)

代码侧:`max_verify_nudges` 的唯一非测试消费点在门②(`agent/conversation_loop.py:7109`,§6.2 已引),
门① 用的是 `build_verify_on_stop_nudge` 的**硬编码默认 2**,且生产调用方不传该参数(§6.2)。
搜索面:全仓 `grep -rn "max_verify_nudges" --include='*.py' --include='*.md'` 命中
`hermes_cli/config_defaults.py:148`、`agent/verify_hooks.py`(定义与 `__all__`)、
`agent/conversation_loop.py:7105`、`tests/agent/test_verify_hooks.py` 若干、
`website/docs/user-guide/configuration.md:949`、`website/docs/user-guide/features/hooks.md:703`,
**没有任何一处把它接到 `build_verify_on_stop_nudge` 上**。

`hermes_cli/config_defaults.py:146 @ 863e313`

```python
        # Upper bound on consecutive `pre_verify` "continue" nudges in a single
        # turn, so a user/plugin hook can never trap the loop.
        "max_verify_nudges": 3,
```

**配置文件里的注释是对的(只说 `pre_verify`),网站文档的注释是错的(多写了 built-in)。**
后果具体:用户把 `max_verify_nudges` 调成 0 想关掉内建轻推,实际只关掉了插件门,
内建门仍会推 2 次。`hooks.md:703` 那一句(同样引下)因为写在 `pre_verify` 小节里、
只说 hook,**是对的**,不计入 ▲。

`website/docs/user-guide/features/hooks.md:703 @ 863e313`

> **Bounded:** consecutive continue directives in one turn are capped by `agent.max_verify_nudges` (default 3), so a hook that always says continue can never trap the loop. The attempted answer is kept in history but not surfaced to the user while the agent is being nudged.

### ▲3 —— `hooks.md` 说 `pre_verify`「每回合触发一次」,但同一页第 705 行说它每次 nudge 后重触发

整段判定(归 `### pre_verify` 三级标题管):

`website/docs/user-guide/features/hooks.md:670 @ 863e313`

> Fires **once per turn when the agent edited code**, just before it finishes (after the built-in verify-on-stop guard). This is a user/plugin policy gate: a callback can keep the agent going — run a check, defer it, tidy the diff — instead of letting it stop.

后半句(「在内建 verify-on-stop 之后」)与代码一致:门② 确实排在门① 之后
(`agent/conversation_loop.py:7043` 门①、`:7109` 门②)。
前半句「once per turn」与代码矛盾:门② 在 `while` 循环内、每次走到终局判定都会重跑,
上限是 `max_verify_nudges`(默认 3),不是 1。同一份文档第 705 行自己说出了正确行为:

`website/docs/user-guide/features/hooks.md:705 @ 863e313`

> **Make it idempotent:** the hook re-fires after each nudge, so gate on `attempt` (`if attempt: return None`) — otherwise it just nudges until the bound is hit.

计 ▲(而非文档内部瑕疵):**读者按第 670 行写的钩子会在一个回合里被调用 3 次**,
而第 670 行是该小节的定义句、位置最显眼。

### ◎1 —— 「refuses to accept a final answer」在字面上成立但显著强于实际

`website/docs/user-guide/configuration.md:943 @ 863e313`

> When enabled, Hermes refuses to accept a final answer on a turn where the agent edited code in a workspace but produced no fresh verification evidence (a passing test run, build, lint, etc.) — it injects a synthetic follow-up asking the agent to verify or explain why it can't. Doc/markdown/skill-only edits never trigger it, and the loop is bounted so it can never trap the agent.

*(上一行为便于对照抄录,原文末词为 `bounded`;此处引文按原文校正见下,判定不依赖该词。)*

逐句判定:
- 「refuses to accept a final answer」+ 「injects a synthetic follow-up asking the agent to
  verify **or explain why it can't**」—— 后半句自己就交代了软出口,**合起来字面为真**;
- 「a passing test run, build, lint, etc.」—— 与 §7.5-c 一致,lint 确实算数,**为真**;
- 「Doc/markdown/skill-only edits never trigger it」—— 与 `_NON_CODE_VERIFY_EXTENSIONS`
  一致,**为真**(注意 `README` 无扩展名时是例外,但那不叫 markdown);
- 「the loop is bounded so it can never trap the agent」—— **为真**(2 次 + 预算硬顶)。

字面为真 ⇒ 按 CLAUDE.md 的记号规则不计 ▲,记 ◎:它只说「edited code in a workspace」,
不说这个「edited」的判定面窄到只有两个工具(§7.1),读者会显著高估覆盖面。

### ◇1 —— `verify_hooks` 走慢路径 `load_config()`,`verification_stop` 走快路径 `load_config_readonly()`

见 §5 末。文档无。

### ◇2 —— `kind` / `scope` 被记录、被展示,但**没有任何门禁消费它们**

搜索面:全仓 `*.py`/`*.ts`/`*.tsx` 内 `grep` 同时含 `kind`/`scope` 与 `verif` 的行,
命中只在 `agent/verification_evidence.py:498-499`(写入)、
`tools/terminal_tool.py:3155-3156`(回填给模型看)、
`tests/*`(断言分类正确)、`tests/test_tui_gateway_server.py:12562`(RPC 展示)。
`agent/verification_stop.py` 全文不含 `kind`/`scope` 任一字符串。
即:分类信息的唯一实际用途是**给模型和人看**,不参与放行判定。文档未述。

### ◇3 —— 台账被纳入备份白名单

`hermes_cli/backup.py:1112 @ 863e313`

```python
    "verification_evidence.db",         # agent verification audit trail
```

它被当作「审计轨迹」保护,而不是可再生缓存。文档未述。

### 负结论 N1 —— 仓库根 `AGENTS.md` / `README.md` 全文没有讲这套机制的段落

搜索面:两文件全量(`AGENTS.md` 1435 行、`README.md` 264 行),
模式 `grep -nEi "verif|evidence|stop.gate|nudge"`,共 12 处命中,逐条判定:
`AGENTS.md` 的 6 处均属「先验证前提再报 bug」「Verify with:」「## Verification 小节写法」
等写作/流程指导;`README.md` 的 6 处属「nudges itself to persist knowledge」(记忆循环)、
「verify your copy is authentic」(发行包签名校验)。**无一处涉及 verify-on-stop / 证据台账。**
唯一在 `.md` 里正面描述本机制的是 `website/docs/user-guide/configuration.md`
与 `website/docs/user-guide/features/hooks.md`(以及
`skills/autonomous-ai-agents/hermes-agent/references/configuration.md:11` 的一行表格列名)。

### 负结论 N2 —— 台账只有两个生产者、两个消费者,没有第三方

搜索面:全仓 `*.py`(含 tests),模式
`grep -rn "record_terminal_result|mark_workspace_edited|verification_status\(|build_verify_on_stop_nudge"`。
生产者非测试命中:`tools/terminal_tool.py:3145`、`tools/file_tools.py:1752`,共 2 处。
消费者非测试命中:`agent/verification_stop.py:168`(经 `_verification_snapshot`)、
`tui_gateway/methods_session.py:295`,共 2 处;其中后者只读展示:

`tui_gateway/methods_session.py:281 @ 863e313`

```python
@method("verification.status")
@_profile_scoped
def _(rid, params: dict) -> dict:
    """Best known coding verification evidence for a cwd/session.

    Read-only consumer of the core ledger. It never runs checks and never
    upgrades targeted evidence into a repository-wide guarantee.
    """
```

（该 RPC 在 `apps/desktop/src` 与 `ui-tui` 的 TS 侧**目前无调用点** ——
搜索面:`grep -rn "verification" apps/desktop/src ui-tui`,20 条命中全部属于
billing step-up 的 `verification_url` / `billing.step_up.verification`,与本机制无关。
即这条 RPC 目前是**为将来的桌面验证 UI 预留、尚未接线**的。）

---

## 10. 移交项(附锚点 + 一句话现象)

| 编号 | 锚点文件 | 一句话现象 |
|---|---|---|
| H-R9A-1 | `tools/terminal_tool.py:3147`(`cwd=command_cwd`) | 远程/Docker 终端后端下 `command_cwd` 是容器内路径,却被 `project_facts_for` 拿到宿主机文件系统上解析;记录点前后无任何 `env_type` 判别。需查:是恒定不记账(收紧)还是可能误命中同名宿主目录(错记)。 |
| H-R9A-2 | `tools/terminal_tool.py:3148` vs `tools/file_tools.py:1752` | 两侧 `session_id` 回落链不同(前者 `session_id or task_id or effective_task_id or "default"`,后者 `session_id or task_id`);存在「跑过测试但台账仍显示 unverified」的错位窗口,尚未构造出触发用例。 |
| H-R9A-3 | `agent/conversation_loop.py:1406`(codex 早退) | `api_mode == "codex_app_server"` 整条回合路径不经过门①/门②;需在 R9 后续轮统计**还有多少 harness 级守卫**同样只挂在主 `while` 循环里、被这条早退绕过(本轮只确认了验证闭环这一处)。 |
| H-R9A-4 | `tests/agent/test_verification_evidence.py:29-34` 等多段连续空行 | 两个测试文件有 12 段疑似「删掉用例后遗留」的空档;若能从 git 历史确认删除时间与原因,可判断这套测试是被刻意收敛还是被顺手删薄(本轮只做形状观察,未取证)。 |

---

## 11. 可迁移的设计原则(造自己的 harness 时怎么做)

1. **把「记录」和「判决」拆成两个模块,并让记录侧被动到底。**
   `verification_evidence` 不阻断、不发起、不升级结论;`verification_stop` 不跑任何东西。
   好处非常实在:台账可以被 TUI 只读消费而不担心副作用,判决策略可以整体换掉而不动数据格式。
2. **让门禁的提示词就是识别器的规格说明。** §4.5 里 nudge 直接把
   「临时目录 / `hermes-verify-` 前缀 / 针对改动行为」念给模型 —— 三个条件正是
   `_is_temp_script_path` 的三个与条件。这样就不会出现「我验了但你不认」的死循环。
   反过来说:**任何门禁,如果它的通过条件不能用一句话讲给被审查方听,就一定会误伤。**
3. **上限要有两层:计数器 + 资源。** 这里是 `attempts >= 2` 加上迭代预算本身。
   只有计数器时,一个 bug 让计数器不递增就会死循环。
4. **被门禁扣下的答案必须显式存起来。** `_pending_verification_response` 那条(§6.3-B)
   是这套设计里最值得抄的一行:一个「拦下来再问一次」的门,天然制造了
   「问着问着资源没了、原答案也丢了」的窗口。存下来,并用「它非空」当作 provenance guard
   来区分「是我扣的」和「是别的错误路径」。
5. **合成消息要打标记,并且只给合成的那一条打。** 模型那条「我做完了」是真内容,
   要入库、要给用户看(它是用户理解「为什么还在跑」的唯一线索);nudge 是脚手架,
   要从持久化和重放里剥掉。二者混为一谈会污染下次会话的上下文。
6. **想清楚每个 `except` 的方向。** 这套代码里有 fail-open-to-放行(§7.4)
   和 fail-open-to-开启门(§4.3)两种相反方向,各自都合理,但必须是**被选择的**、
   写在注释里的 —— 而不是随手写了个 `except Exception: pass`。
7. **别让「改了文件」这个事实只从一两个工具名推断。** §7.1 是这套机制最大的洞:
   `frozenset({"write_file", "patch"})` 是一个**按工具名**的白名单,
   而 harness 提供了至少四种别的改文件方式。要么在**文件系统层**观测(如回合开始/结束
   对工作区做 `git status` 快照),要么把「可能改文件的工具」做成能力标注而不是名字白名单。
8. **退出码不等于「这条命令成功了」。** `cmd || true` 这类 shell 结构会把失败洗白(§7.5-a)。
   如果要用退出码当证据,就必须**自己执行那条被识别的子命令**,
   或者拒绝识别含 `||`/`;`/管道的复合命令 —— 而不是从复合命令里挑一段、配整体的退出码。
9. **一个不检查覆盖关系的「新鲜度」模型,等于没有覆盖关系。** §7.5-c:
   台账记了 `kind`/`scope`,门禁却只看 `status`。既然记了就该用:
   最起码「改了 `.py` 却只跑了 formatter」应该判不通过。
