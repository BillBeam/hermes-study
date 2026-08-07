# r7c-raw-slash-a · `gateway/slash_commands.py` 第 1–2000 行

> 基线:`863e31318553cda8ad61df681d08175364d4164b`(全文 5693 行)。
> 本底稿只覆盖 **第 1–2000 行**。为讲清"命令怎么被注册/解析/分发/门控",
> 会引用切片外的 `hermes_cli/commands.py`、`gateway/platforms/base.py`、
> `gateway/run.py`、`gateway/slash_access.py` —— 这些引用同样给精确行号,
> 但不计入本切片的精读覆盖。
> 溯源约定:`路径:行号 @ 863e313`,行号已逐条用 Read/sed 复核。

---

## 0. 本切片一句话

**这个文件里没有命令注册表 —— 它只是一堆 `_handle_*_command` 协程方法组成的 mixin;
真正的"注册表 + 元数据(别名 / busy 策略 / CLI-or-gateway 可见性 / 共享执行器)"在
`hermes_cli/commands.py` 的 `COMMAND_REGISTRY`,真正的"解析"在
`gateway/platforms/base.py` 的 `MessageEvent.get_command()`,真正的"分发"是
`gateway/run.py` 里一条手写的 `if canonical == "..."` 长链。**

---

## 1. 结构总览

| 行区间 | 内容 |
|---|---|
| 1–14 | 模块 docstring:声明这是从 `gateway/run.py` 拆出来的 mixin,并解释"延迟 import 破循环依赖"的约定 |
| 16–48 | import(注意:`shlex`/`inspect`/`re`/`sys`/`Path`/`datetime` 等在切片内基本没用到,属全文件共用) |
| 50 | `logger = logging.getLogger("gateway.run")` —— **logger 名与模块名不符**(见 §4) |
| 52–56 | `_RESET_CLEANUP_TIMEOUT_S = 30.0`(#35994) |
| 59–61 | `_clean_str` 模块级 |
| 64–69 | `_int_value` 模块级 |
| 72–98 | `_model_switch_skew_guard()` —— 换模型前的"代码漂移"闸门 |
| 101–104 | `class GatewaySlashCommandsMixin`,唯一类属性注解 `async_session_store: AsyncSessionStore` |
| 106–117 | `_typed_command_prefix_for()` —— 决定提示文案里写 `/` 还是 `!` |
| 119–326 | `_handle_reset_command`(`/new`、`/reset`)—— 本切片最复杂的一个,208 行 |
| 328–379 | `_handle_profile_command` |
| 381–430 | `_handle_whoami_command` |
| 432–538 | `_handle_kanban_command` |
| 540–713 | `_handle_status_command` |
| 715–720 | `_redact_matrix_session_key`(staticmethod) |
| 722–910 | `_handle_context_command` |
| 912–925 | `_gateway_session_origin_for_id` |
| 927–943 | `_same_matrix_room`(staticmethod) |
| 945–1009 | `_same_origin_chat` |
| 1011–1028 | `_resume_caller_is_admin` |
| 1030–1171 | `_resume_target_allowed` —— `/resume` 的 IDOR 防线,141 行几乎全是注释 |
| 1173–1195 | `_resume_row_visible` |
| 1197–1346 | `_handle_agents_command` |
| 1348–1429 | `_handle_stop_command` |
| 1431–1522 | `_handle_platform_command` |
| 1524–1632 | `_handle_restart_command` |
| 1634–1638 | `_handle_version_command` |
| 1640–1649 | `_handle_help_command` |
| 1651–1669 | `_handle_commands_command` |
| 1671–2000+ | `_handle_model_command`(跨过切片边界,2000 行处正停在 picker 回调 `_on_model_selected_scoped` 的"持久化到 config.yaml"分支中间) |

切片内共 **17 个 `_handle_*_command`**,另有 9 个非 handler 的辅助方法/静态方法。
全文件 `async def _handle_*_command` 共 **52 个**(`grep -c` 实测)。

---

## 2. 逐机制

### 2.1 命令是怎么"注册"的 —— 一个不在本文件里的注册表

**问题**:一条 `/model gpt-5 --global` 从 Telegram 进来,系统怎么知道
(a) 这是不是一个合法命令,(b) `/reset` 是 `/new` 的别名,(c) agent 正忙时它该不该跑,
(d) CLI 有没有这个命令?

**实现**:本文件**没有**装饰器、没有 `@command("model")`、没有字典注册。
唯一的真源是一个 frozen dataclass 列表:

`hermes_cli/commands.py:46-58 @ 863e313`
```python
@dataclass(frozen=True)
class CommandDef:
    """Definition of a single slash command."""

    name: str                          # canonical name without slash: "background"
    description: str                   # human-readable description
    category: str                      # "Session", "Configuration", etc.
    aliases: tuple[str, ...] = ()      # alternative names: ("bg",)
    args_hint: str = ""                # argument placeholder: "<prompt>", "[name]"
    subcommands: tuple[str, ...] = ()  # tab-completable subcommands
    cli_only: bool = False             # only available in CLI
    gateway_only: bool = False         # only available in gateway/messaging
    gateway_config_gate: str | None = None  # config dotpath; when truthy, overrides cli_only for gateway
```
同一个 dataclass 还带三个关键元数据字段:

`hermes_cli/commands.py:75-89 @ 863e313`
```python
    busy_policy: str = "reject"
    # Optional key of a special mid-run handler in the Guard-2 handler table
    # (gateway/run.py) for commands whose busy behavior differs from their
    # normal handler (e.g. /goal's control-verb whitelist, /queue's FIFO
    # enqueue, /model's custom busy-reject text).
    busy_handler: str | None = None
    # Registry-owned shared execution (thin slice, informational commands).
    # Names a key in ``hermes_cli.slash_exec.EXECUTORS`` — a pure formatter
    # producing the canonical, surface-independent core text.  Surfaces
    # resolve it via ``hermes_cli.slash_exec.run_execute`` and apply only
    # their own decoration (Rich markup, emoji/markdown, telegramize).  A
    # string key (not a callable) keeps this module import-light: the
    # gateway can import commands.py without prompt_toolkit and without
    # pulling in executor dependencies.
    execute: str | None = None
```

别名解析是纯字典 exact-match,**没有前缀匹配**:

`hermes_cli/commands.py:362-367 @ 863e313`
```python
def resolve_command(name: str) -> CommandDef | None:
    """Resolve a command name or alias to its CommandDef.

    Accepts names with or without the leading slash.
    """
    return _COMMAND_LOOKUP.get(name.lower().lstrip("/"))
```

网关可识别集合是从 registry 派生的,注意 `cli_only` 的例外规则:

`hermes_cli/commands.py:422-427 @ 863e313`
```python
GATEWAY_KNOWN_COMMANDS: frozenset[str] = frozenset(
    name
    for cmd in COMMAND_REGISTRY
    if not cmd.cli_only or cmd.gateway_config_gate
    for name in (cmd.name, *cmd.aliases)
)
```

**设计理由**:注册表放在 `hermes_cli` 而不是 `gateway`,是为了让 CLI(REPL 补全、
`/help` 表格)和网关(dispatch、hook 名、busy 策略)共用一份真源;`execute` 字段
故意存 **字符串 key 而非 callable**,注释明说是为了"keep this module import-light"
(`hermes_cli/commands.py:84-88`)—— 网关 import `commands.py` 时不会被拖进
prompt_toolkit 和各 executor 的依赖树。

**取舍**:
- 元数据集中了,但**分发没有集中**。`busy_policy`/`busy_handler` 被 registry 驱动了
  (见 §2.5),而"冷路径"分发仍是 `gateway/run.py` 里一条手写 `if canonical == ...` 长链
  (`gateway/run.py:15060` 起,一直到 15000 多行往后)。加一条命令要改两处:
  registry 加 `CommandDef`,run.py 加一个 `if`。
- `CommandDef` 里**没有权限字段**。没有 `owner_only=True`、没有 `dm_only=True`。
  权限完全由 `gateway/slash_access.py` 的运营方配置(命令名白名单)决定,
  见 §2.4。这意味着"哪些命令天然危险"这个知识不在代码里,靠运营方自己写
  `user_allowed_commands`。

---

### 2.2 输入文本 → 命令 + 参数

**场景**:Telegram 群里有人发 `  /Status@HermesBot   还有第二行\n第三行`。

**实现**(全部在 `MessageEvent` 上,不在本文件):

`gateway/platforms/base.py:2130-2158 @ 863e313`
```python
    def is_command(self) -> bool:
        """Check if this is a command message (e.g., /new, /reset)."""
        return (self.text or "").lstrip().startswith("/")
    
    def get_command(self) -> Optional[str]:
        """Extract command name if this is a command message."""
        if not self.is_command():
            return None
        # Split on space and get first word, strip the /
        command_text = (self.text or "").lstrip()
        parts = command_text.split(maxsplit=1)
        raw = parts[0][1:].lower() if parts else None
        if raw and "@" in raw:
            raw = raw.split("@", 1)[0]
        # Reject file paths: valid command names never contain /
        if raw and "/" in raw:
            return None
        return raw
    
    def get_command_args(self) -> str:
        """Get the arguments after a command."""
        if not self.is_command():
            return self.text
        command_text = (self.text or "").lstrip()
        parts = command_text.split(maxsplit=1)
        args = parts[1] if len(parts) > 1 else ""
        # iOS auto-corrects -- to — (em dash) and - to – (en dash)
        args = args.replace("\u2014\u2014", "--").replace("\u2014", "--").replace("\u2013", "-")
        return args
```

逐条对上题目问的:
- **前缀字符**:硬编码 `/`(`base.py:2132`)。`!` 前缀不是在这里处理的 —— Slack/Matrix
  适配器在**收包时**就把 `!command` 改写成 `/command`,只留一个能力位供文案使用:
  `gateway/platforms/base.py:2710` `typed_command_prefix: str = "/"`;
  `plugins/platforms/slack/adapter.py:881` 与 `plugins/platforms/matrix/adapter.py:1051`
  各自 `typed_command_prefix = "!"`。本切片的 `_typed_command_prefix_for`
  (`gateway/slash_commands.py:106-117`)只负责**渲染提示文案**时选对前缀:
  ```python
    def _typed_command_prefix_for(self, platform) -> str:
        """Return the prefix users can always type to reach Hermes commands.
        ...
        """
        adapter = self.adapters.get(platform) if getattr(self, "adapters", None) else None
        return getattr(adapter, "typed_command_prefix", "/") if adapter is not None else "/"
  ```
- **大小写**:命令名 `.lower()`(`base.py:2141`),参数**原样保留大小写**。
- **`@botname` 后缀**:只在 `get_command()` 里被切掉(`base.py:2142-2143`)。
  `event.text` **不改**。所以任何自己重新解析 `event.text` 的 handler 会看到 `@bot` —— 见 §4 的 kanban 缺陷。
- **多行**:`split(maxsplit=1)` 按任意空白切,`\n` 也算。所以 `/new\nMy title` 的
  title 是 `"My title"`。
- **引号**:`get_command_args()` **不做**引号处理,返回原始剩余串。需要引号语义的
  handler 自己上 `shlex`,例如 `gateway/slash_commands.py:458`
  `tokens = shlex.split(text) if text else []`。
- **反直觉的一条**:`raw` 里含 `/` 直接返回 `None`(`base.py:2144-2146`)。
  这是为了让 `/home/user/x.txt` 这种粘贴的路径不被当成命令。
- **iOS 破折号纠正**:`base.py:2156-2157` 把 `——`/`—` 还原成 `--`、`–` 还原成 `-`。
  这是个纯 UX 补丁,直接决定了 `/model x —global` 也能工作。

**取舍**:解析逻辑放在 dataclass 方法上(而非独立 parser),导致每个 handler 都可以
"绕过它自己解析 `event.text`",一致性只靠自觉 —— 本切片里 `_handle_kanban_command`
和 `_handle_platform_command` 就都自己解析了,两个都出了问题(§4)。

---

### 2.3 分发:三道门 + 一条 if 链

**场景**:同一条 `/status`,在"没有 agent 在跑"和"agent 正在跑"两种情况下走完全不同的路。

**Guard 1(适配器层,`gateway/platforms/base.py`)**:
session 已有活跃 handler 时,先决定"这条命令是插队还是排队":

`gateway/platforms/base.py:5604-5625 @ 863e313`
```python
            cmd = event.get_command()
            from hermes_cli.commands import (
                is_interrupt_then_dispatch,
                should_bypass_active_session,
            )

            if should_bypass_active_session(cmd):
                # /stop, /new, /reset must cancel the in-flight adapter task
                # and preserve ordering of queued follow-ups.  Route those
                # through the dedicated handoff path that serializes
                # cancellation + runner response + pending drain.
                # (Registry-derived: busy_policy == "interrupt_then_dispatch".)
                if cmd and is_interrupt_then_dispatch(cmd):
                    self._discard_text_debounce(session_key)
                    try:
                        await self._dispatch_active_session_command(event, session_key, cmd)
```
`should_bypass_active_session` 的语义比名字更宽 —— **任何能解析出来的命令都旁路**:

`hermes_cli/commands.py:476-496 @ 863e313`
```python
def should_bypass_active_session(command_name: str | None) -> bool:
    """Return True for any resolvable slash command.
    [中略]
    Queueing is always wrong for a recognized slash command because the
    safety net in gateway.run discards any command text that reaches
    the pending queue — which meant a mid-run /model (or /reasoning,
    /voice, /insights, /title, /resume, /retry, /undo, /compress,
    /usage, /reload-mcp, /sethome, /reset) would silently
    interrupt the agent AND get discarded, producing a zero-char
    response. See issue #5057 / PRs #6252, #10370, #4665.
    [中略]
    """
    return resolve_command(command_name) is not None if command_name else False
```

**Guard 2(runner 层,`gateway/run.py:14098`,`_dispatch_busy_slash_command`)**:
旁路进来之后,由 `busy_policy` / `busy_handler` 三段式决定怎么跑
(`gateway/run.py:14117-14170`):`busy_handler` 特判表(14120-14134)→
`busy_policy in ("dispatch", "interrupt_then_dispatch")` 的普通 handler 表
(14136-14158)→ 兜底拒绝文案(14164-14170)。

**冷路径(没有 agent 在跑)**:`gateway/run.py:15060` 起的手写 if 链,例如
`gateway/run.py:15093-15096 @ 863e313`
```python
        if canonical == "whoami":
            return await self._handle_whoami_command(event)

        if canonical == "status":
            return await self._handle_status_command(event)
```

**返回值协议**(本切片能完整看清):
- 所有 handler 都是 `async def`。签名统一 `(self, event: MessageEvent)`。
- 返回 `str` → 正常回复。
- 返回 `EphemeralReply`(`gateway/platforms/base.py:2375` `class EphemeralReply(str)`)
  → 仍是 str 子类,发出去后按 TTL 自动删除;不支持 `delete_message` 的平台自动降级
  (`gateway/platforms/base.py:5009-5010`)。切片里 `/new`、`/stop`、`/restart` 用它。
- 返回 `""` → 明确的"不回复"。`_handle_restart_command` 检测到重投递时
  `gateway/slash_commands.py:1545` `return ""`。
- 返回 `None` → 也不回复;`_handle_model_command` 的返回类型是 `Optional[str]`
  (`gateway/slash_commands.py:1671`),picker 路径靠回调异步回话,主协程返回 None。
- 拆包逻辑 `gateway/platforms/base.py:4992-5012`,`_unwrap_ephemeral` 接受
  `str | None | EphemeralReply`,返回 `(text, ttl)`。

**设计理由**:`EphemeralReply` 做成 `str` 子类而不是新类型,是为了向后兼容 ——
docstring 明说"existing tests use `in` / `startswith` / equality"
(`gateway/platforms/base.py:2382-2384`)。这是典型的"用继承换零成本迁移"。

**取舍**:代价是类型系统里 `str` 和 `EphemeralReply` 无法区分,只能 `isinstance` 兜住;
而且一旦某个中间层做了 `text + suffix`,ephemeral 属性就静默丢了 ——
`gateway/run.py:20570-20574` 里就明确避开了这一点(`always` 分支只给 `str` 追加提示,
`EphemeralReply` 原样返回)。

---

### 2.4 权限与门控

切片内**没有**任何 `owner_only` / `dm_only` 判定。命令级鉴权只有一处,而且在切片外:

`gateway/run.py:18453-18457 @ 863e313`
```python
        if not canonical_cmd:
            return None
        policy = _policy_for_source(self.config, source)
        if not policy.enabled or policy.can_run(source.user_id, canonical_cmd):
            return None
```

策略本身:

`gateway/slash_access.py:79-88 @ 863e313`
```python
    def can_run(self, user_id: Optional[str], canonical_cmd: str) -> bool:
        if not self.enabled:
            return True
        if self.is_admin(user_id):
            return True
        if not canonical_cmd:
            return False
        if canonical_cmd in _ALWAYS_ALLOWED_FOR_USERS:
            return True
        return canonical_cmd in self.user_allowed_commands
```
`_ALWAYS_ALLOWED_FOR_USERS` 只有两项:

`gateway/slash_access.py:50-53 @ 863e313`
```python
_ALWAYS_ALLOWED_FOR_USERS: FrozenSet[str] = frozenset({
    "help",
    "whoami",
})
```

**默认全开**:`enabled = bool(admin_ids)`(`gateway/slash_access.py:188`)——
运营方没配 `allow_admin_from` 就等于关掉门禁,`is_admin()` 对所有人返回 True
(`gateway/slash_access.py:69-74`)。

切片内唯一"自己再收紧一次"的地方是跨 origin 数据访问,它**故意不信任** `is_admin()`:

`gateway/slash_commands.py:1011-1028 @ 863e313`
```python
    def _resume_caller_is_admin(self, source: SessionSource) -> bool:
        """Whether *source* is an EXPLICITLY-configured admin allowed to make a
        cross-origin /resume or /sessions listing.

        Deliberately stricter than ``SlashAccessPolicy.is_admin()``: that returns
        True for every allowed caller when slash gating is DISABLED (so commands
        stay runnable by default), but cross-ORIGIN DATA ACCESS must require a
        real, configured admin. Otherwise the default (no admin list) config
        would treat every gateway caller as cross-origin-capable and re-open the
        enumeration IDOR.
        """
        try:
            from gateway.slash_access import policy_for_source
            policy = policy_for_source(self.config, source)
            uid = getattr(source, "user_id", None)
            return bool(policy.enabled and uid and policy.is_admin(uid))
        except Exception:
            return False
```
注意 `policy.enabled and ...` —— 这一个词就是"默认全开"与"跨会话枚举 IDOR"之间的隔离带。

**`/resume` 的 IDOR 防线**(`gateway/slash_commands.py:1030-1171`,141 行,
其中约 90 行是注释)。它的骨架是四层 fail-closed:
1. admin `--all` 显式覆盖(1043-1044);
2. 目标会话**活着** → 用活的 origin 比对(1048-1053 → `_same_origin_chat`);
3. 目标只在 DB 里 → 用 `source`/`user_id`/`chat_id`/`thread_id` 四元组比对
   (1055-1162),任何一项证明不了就拒;
4. 调用者没有身份 → 直接拒(1163-1171)。

其中最微妙的一条是 `user_id_alt` 的"证据缺口":

`gateway/slash_commands.py:1078-1091 @ 863e313`
```python
        # build_session_key keys the participant on ``user_id_alt or user_id``
        # (Signal/Feishu carry the canonical participant in user_id_alt), but the
        # sessions table only ever stored user_id — it has no user_id_alt column.
        # So when the caller carries a user_id_alt, the row CANNOT prove the
        # canonical participant that the live session key is built from: two
        # members sharing one user_id but different user_id_alt map to DIFFERENT
        # session keys, yet the persisted row's user_id would match both. The
        # live-origin guard (_same_origin_chat) compares user_id_alt correctly;
        # the persisted fallback cannot, so any per-user comparison that would
        # otherwise rely on row_uid == caller_uid must fail closed here to stay
        # in lock-step with the key boundary (CWE-639). Shared group/thread
        # sessions are unaffected (they don't scope by participant at all), and
        # an admin --all override still bypasses this above.
        caller_keys_on_alt = bool(str(getattr(source, "user_id_alt", "") or ""))
```

**设计理由(可迁移)**:守卫的判定口径必须与 **session key 的构造口径**
逐字段对齐。`_same_origin_chat` 的 docstring 把这条写成了明规矩:

`gateway/slash_commands.py:964-970 @ 863e313`
```python
        # thread_id is part of the session key for every chat type when present
        # (build_session_key appends it unconditionally), so a session in one
        # thread is a DIFFERENT session from another thread of the same parent
        # chat. is_shared_multi_user_session only decides participant sharing
        # WITHIN a thread, never across threads — require thread equality before
        # any sharing logic so a live origin in thread A cannot match a caller in
        # thread B of the same parent chat.
```
`is_shared_multi_user_session` 是这条对齐关系的**唯一函数化载体**
(`gateway/slash_commands.py:994-998`、`1149-1153` 各调一次),它的存在就是为了
"守卫不用重抄 key 规则"。

**取舍**:守卫写得极保守(遗留 NULL 行一律不可 resume),换来的是 legacy 数据的可用性
损失,注释里已经明说要靠 live session 或 admin override 兜底
(`gateway/slash_commands.py:1103-1105`)。

---

### 2.5 与 busy 会话的交互

`is_interrupt_then_dispatch` 的定义是纯 registry 派生:

`hermes_cli/commands.py:461-473 @ 863e313`
```python
def is_interrupt_then_dispatch(command_name: str | None) -> bool:
    """Return True when *command_name* must interrupt a running agent first.

    Derived from the registry: commands whose ``busy_policy`` is
    "interrupt_then_dispatch" (the /stop, /new, /reset class).  Guard 1
    (gateway/platforms/base.py) routes these through the cancel-handoff
    path that serializes cancellation + runner response + pending drain.
    Accepts aliases (e.g. "reset" resolves to "new").
    """
    if not command_name:
        return False
    cmd = resolve_command(command_name)
    return cmd is not None and cmd.busy_policy == "interrupt_then_dispatch"
```

切片内命令的 busy 归类(元数据在 `hermes_cli/commands.py`):

| 命令 | `busy_policy` | `busy_handler` | 出处 |
|---|---|---|---|
| `new`(别名 `reset`) | `interrupt_then_dispatch` | `new` | `hermes_cli/commands.py:106-108` |
| `stop` | `interrupt_then_dispatch` | `stop` | `hermes_cli/commands.py:140-141` |
| `status` | `dispatch` | — | `hermes_cli/commands.py:172-173` |
| `context`(别名 `ctx`) | `dispatch` | — | `hermes_cli/commands.py:178-180` |
| `agents`(别名 `tasks`) | `dispatch` | — | `hermes_cli/commands.py:148-149` |
| `profile` | `dispatch` | — | `hermes_cli/commands.py:182-183` |
| `kanban` | `dispatch` | — | `hermes_cli/commands.py:286-294` |
| `help` | `dispatch` | — | `hermes_cli/commands.py:311-312` |
| `commands` | `dispatch` | — | `hermes_cli/commands.py:308-310` |
| `restart` | `dispatch` | — | `hermes_cli/commands.py:313-314` |
| `version`(别名 `v`) | `dispatch` | — | `hermes_cli/commands.py:334-335` |
| `model` | `reject` | `model`(自定义拒绝文案) | `hermes_cli/commands.py:195-197` |
| `whoami` | 默认 `reject` | — | `hermes_cli/commands.py:181` |
| `platform` | 默认 `reject` | — | `hermes_cli/commands.py:324-325` |

**注意 `whoami`**:它在 `_ALWAYS_ALLOWED_FOR_USERS` 里(任何人可运行),但
`busy_policy` 走默认 `reject`(agent 忙时不可运行)。这两个维度**正交**,
容易混淆 —— 权限维度和并发维度是两套独立的元数据。

`busy_handler` 的特判表(Guard-2)在 `gateway/run.py:14120-14134`,
`dispatch` 类的普通 handler 表在 `gateway/run.py:14137-14156`,兜底文案在
`gateway/run.py:14164-14170`。`busy_policy` 声明了 `dispatch` 却不在表里的命令
会打 warning 然后降级为拒绝(`gateway/run.py:14159-14162`)——
这是防"registry 和 handler 表脱节"的自检。

---

### 2.6 `/new` `/reset`:一次会话边界要清多少东西

**场景**:用户在 Telegram DM topic 里点了确认按钮的 "Approve Once",触发 `/new`。

`_handle_reset_command`(`gateway/slash_commands.py:119-326`)按顺序做了 **11 件事**:

1. **失效 run generation + 收回 running-agent 槽位**(123-131)
   ```python
        session_key = self._session_key_for_source(source)
        self._invalidate_session_run_generation(session_key, reason="session_reset")
        # Evict the running-agent slot now that the generation is bumped. The
        # in-flight run's own guarded release (run_generation=old) will return
        # False and leave its dead agent behind; clearing here keeps the slot
        # from becoming a zombie that silently drops all later messages (#28686).
        # Idempotent, so the run's finally calling it again is harmless.
        self._release_running_agent_state(session_key)
   ```
2. **快照旧 entry**(135)`old_entry = self.session_store._entries.get(session_key)`
   —— 直接摸私有 `_entries`,为的是在 `reset_session()` 轮换 id 之前拿到旧 session_id。
3. **卸工具资源,但必须离开事件循环**(139–177)。见 §5 的 #35994。
4. `self._evict_cached_agent(session_key)`(178)
5. **一次性清所有 conversation-scoped 状态**(180-184):
   ```python
        # Conversation boundary: clear ALL conversation-scoped per-session
        # state (model/reasoning overrides, one-turn restores, model notes,
        # last-resolved cache, /queue overflow) + security state in one
        # funnel call. See _CONVERSATION_SCOPED_STATE in gateway/run.py.
        self._clear_conversation_scope(session_key, reason="session_reset")
   ```
   这是个很值得学的收口:把"会话边界要清什么"做成一张表 + 一个 funnel,
   而不是散落在 handler 里逐个 `.pop()`。
6. **中断本会话派生的异步 delegation**(186-202,#55578)。
7. `clear_env_passthrough()` / `clear_credential_files()`(204-214),
   两个都是 `try/except: pass`。
8. `reset_session()` 真正轮换 session id(217)。
9. **三处生命周期钩子**:插件 `finalize_session`(226-235)、
   `session:end` hook(238-242)、`session:reset` hook(245-249),
   之后再 `on_session_reset`(303-315)。四个钩子,三种机制,顺序敏感 ——
   注释 302 明写 "new session guaranteed to exist"。
10. **`/new <title>`**(268-289):
    ```python
        _title_arg = event.get_command_args().strip()
        _title_note = ""
        if _title_arg and self._session_db and new_entry:
            from hermes_state import SessionDB
            try:
                sanitized = SessionDB.sanitize_title(_title_arg)
    ```
11. **Telegram topic 重绑定**(291-300)—— 不做的话下一条消息会被 binding 拉回旧 session:
    ```python
        # When /new runs inside a Telegram DM topic lane, rewrite the
        # (chat_id, thread_id) → session_id binding so the next message
        # uses the freshly-created session. Without this, the binding
        # still points at the old session and the binding-lookup at the
        # top of _handle_message_with_agent would switch right back.
    ```

**取舍**:第 7、9、11 步全是 `except Exception: pass` / `except: logger.debug`。
即"会话重置永远成功",宁可漏清一点状态也不让用户卡死。代价是清理失败**静默**
(第 7 步连 debug log 都没有)。

---

### 2.7 `/status` 与 `/context`:两级"上下文视图"与级联回退

`/status` 一行摘要,`/context` 是深视图 —— 这个分工在 `_handle_context_command`
的 docstring 里写死了(`gateway/slash_commands.py:723-737`)。

两者共享同一套**四级回退**取数策略(`/context` 的注释最清楚):

`gateway/slash_commands.py:762-765 @ 863e313`
```python
        # Resolve current-context size + window with cascading fallbacks.
        #   used  : compressor.last_prompt_tokens → SessionStore.last_prompt_tokens
        #   model : agent.model → SessionDB row model
        #   window: compressor.context_length → get_model_context_length(model)
```
顺序是:**在跑的 agent → 缓存的 agent → SessionDB 行 → 配置 → 转录估算**。
`/status` 里的对应实现在 602-651,`/context` 在 745-793,最后兜底是
`estimate_messages_tokens_rough`(`gateway/slash_commands.py:887-909`)。

一个值得记的"数据源真源"决策:

`gateway/slash_commands.py:571-576 @ 863e313`
```python
        # Pull token totals from the SQLite session DB rather than the
        # in-memory SessionStore.  The agent's per-turn token deltas are
        # persisted into sessions_db (run_agent.py), not into SessionEntry,
        # so session_entry.total_tokens is always 0.  SessionDB is the
        # single source of truth; reading it here keeps /status accurate
        # without duplicating token writes into two stores.
```

`/context` 的进度条是手搓的(`gateway/slash_commands.py:799-801`):
```python
            BAR_WIDTH = 24
            filled = int(round(pct / 100 * BAR_WIDTH))
            bar = "█" * max(0, filled) + "░" * max(0, BAR_WIDTH - filled)
```
docstring 解释了为什么不用 CLI 的字形网格:`gateway/slash_commands.py:874-876`
"plain text (no glyph grid — monospace isn't guaranteed on messaging platforms)"。

`/status` 对 Matrix 有特判:共享房间里直接打印 session_key 会泄露成员标识,
所以做了指纹化(`gateway/slash_commands.py:715-720`):
```python
    @staticmethod
    def _redact_matrix_session_key(session_key: str) -> str:
        """Return a stable Matrix session-key fingerprint for shared room status."""
        text = str(session_key or "")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        return f"sha256:{digest}"
```

---

### 2.8 `/model`:切片里最重的一个,以及"换模型前先看代码有没有漂移"

`_handle_model_command`(1671–2000+)的参数解析全部外包给共享 parser:

`gateway/slash_commands.py:1700-1717 @ 863e313`
```python
        # Parse --provider, --global, --session, --once, and --refresh flags
        # via the shared single-owner parser (hermes_cli.model_switch).
        request = parse_model_switch_args(raw_args)
        model_input = request.target
        explicit_provider = request.explicit_provider
        is_global_flag = request.is_global
        force_refresh = request.force_refresh
        is_session = request.is_session
        one_turn = request.is_once
        if request.errors:
            # Gateway decoration: "❌ " prefix over the canonical error copy.
            return f"❌ {request.error_messages()[0]}"
        persist_global = resolve_persist_behavior(
            is_global_flag,
            is_session,
            is_once=one_turn,
            explicit_provider=explicit_provider,
        )
```
这是全仓反复出现的模式:**core 出 canonical 文案,surface 只加装饰**(这里就是一个 `❌ `)。

**最有意思的机制:`_model_switch_skew_guard`**(72-98)。

`gateway/slash_commands.py:72-98 @ 863e313`
```python
def _model_switch_skew_guard() -> Optional[str]:
    """Refuse a model switch when the gateway is running stale code.

    A long-lived gateway holds its modules in memory from boot. If the checkout
    changed underneath it (e.g. a manual ``git pull``), switching models can hit
    a first-time lazy import on a new code path and crash on a stale cached
    dependency — the cryptic ``cannot import name 'env_float' from 'utils'``.
    Detect the drift and tell the user to restart instead.

    Intentionally scoped to model switching — the known, highest-risk trigger.
    Any first-time lazy import on a stale process is technically exposed; we
    don't guard every import site, only this one.
    """
    from gateway.code_skew import detect_code_skew

    skew = detect_code_skew()
    if not skew:
        return None
```
**故事**:全仓大量用"延迟 import"(本文件顶部 docstring 就把它当成破环手段,
`gateway/slash_commands.py:10-13`)。延迟 import 的代价是:进程启动后你 `git pull`,
已加载的模块是旧的,而**没加载过的**模块会从新磁盘文件加载 —— 新旧混用,
报出来的错("cannot import name 'env_float' from 'utils'")完全指不到根因。
这个 guard 就是把"最可能第一次触发懒加载的路径"(换模型)挡住,给一句人话。
docstring 第二段还诚实承认这是**点状修补而非系统修复**。

**事件循环卫生**:整个 `/model` 路径把所有可能同步发 HTTP 的调用都 `to_thread` 了:
- `list_picker_providers`(1787-1797,`# See #41289`)
- `switch_model`(1823-1834,`# See #20525, #41289`)
- `enrich_model_switch_warnings_for_gateway`(1846-1854)
- `get_model_context_length`(790,在 `/context` 里)
- `_reset_notice_session_info`、`_telegram_topic_new_header`、`_is_telegram_topic_lane`
  (255、262、296,在 `/new` 里)
- `_normalize_source_for_session_key`(1761)
- `run_slash`(480,在 `/kanban` 里)
- `_context_breakdown_block`(878,在 `/context` 里)

**这是本切片最强的一条可迁移原则:handler 里凡是"可能 IO"的同步调用一律 offload。**

**失败必须是 no-op**(#50163):

`gateway/slash_commands.py:1874-1893 @ 863e313`
```python
                            except Exception as exc:
                                # The in-place swap rolled the agent back to the
                                # OLD working model/client and re-raised.  Abort
                                # the rest of the commit: do NOT persist the
                                # failed model to the DB, do NOT set a session
                                # override pointing at the broken model, and do
                                # NOT evict the working cached agent.  Otherwise
                                # the next message rebuilds a dead agent from the
                                # broken override and the conversation is lost
                                # (#50163).  A failed switch must be a no-op.
```

**三层写入**(picker 成功路径,1858-2007):
1. 就地改缓存 agent(`switch_model()`,1867-1873);
2. 写 SessionDB(`update_session_model`,1903-1905,#34850,给 dashboard 看);
3. 写内存 override + 写穿到 session store(1925-1945,注释明说 `api_key is never persisted`);
4. 淘汰缓存 agent(1950);
5. 可选写 config.yaml(1955-2009)。

第 3、4 步并存是刻意的:注释 1947-1949 说 "Evict cached agent so the next turn creates
a fresh agent from the override rather than relying on the stale cache signature"。

---

### 2.9 `/restart`:自我重启的两个坑

**坑一,重投递自激循环**(`gateway/slash_commands.py:1527-1545`):

```python
        # Defensive idempotency check: if the previous gateway process
        # recorded this same /restart (same platform + update_id) and the new
        # process is seeing it *again*, this is a re-delivery caused by PTB's
        # graceful-shutdown `get_updates` ACK failing on the way out ("Error
        # while calling `get_updates` one more time to mark all fetched
        # updates. Suppressing error to ensure graceful shutdown. When
        # polling for updates is restarted, updates may be received twice."
        # in gateway.log).  Ignoring the stale redelivery prevents a
        # self-perpetuating restart loop where every fresh gateway
        # re-processes the same /restart command and immediately restarts
        # again.
```
**因果**:`/restart` → 网关关机 → PTB 收尾时那次 ACK 用的 `get_updates` 失败 →
Telegram 不知道这条 update 被消费了 → 新网关起来重新拉到同一条 `/restart` → 无限重启。
修法:两个文件。`.restart_notify.json`(1581-1585,新网关回话后会删)
和 `.restart_last_processed.json`(1601-1605,**不删**,专供去重)。
分成两个文件正是因为前者会被删掉,没法当去重标记(注释 1589-1593 明说)。

**坑二,重启方式取决于运行环境**(1610-1629):
```python
        # When running under a service manager (systemd/launchd) or inside a
        # Docker/Podman container, use the service restart path: exit with
        # code 75 so the service manager / container restart policy restarts
        # us.  The detached subprocess approach (setsid + bash) doesn't work
        # under systemd (KillMode=mixed kills the cgroup) or Docker (tini
        # exits when the gateway dies, taking the detached helper with it).
```
`request_restart(detached=False, via_service=True)` vs
`request_restart(detached=True, via_service=False)`(1627/1629)。

---

### 2.10 三个"薄"命令:registry-owned 共享执行器

`/version`、`/help`、`/commands`、`/profile` 走的是同一个模式:

`gateway/slash_commands.py:1634-1638 @ 863e313`
```python
    async def _handle_version_command(self, event: MessageEvent) -> str:
        """Handle /version — show the running Hermes Agent version."""
        from hermes_cli.slash_exec import CommandContext, execute_command

        return execute_command("version", CommandContext(surface="gateway")).text
```
`CommandContext`/`CommandReply` 契约在 `hermes_cli/slash_exec.py:41-58`:
`text`(surface 无关的核心文案)+ `data`(结构化值,surface 可自渲染)+
`format`(渲染提示,注释明说 "hint, not a contract")。

`/profile` 就用了 `data` 通道(`gateway/slash_commands.py:374-377`):
```python
        lines = [
            t("gateway.profile.header", profile=reply.data["profile"]),
            t("gateway.profile.home", home=reply.data["home"]),
        ]
```
即:core 算值,gateway 用自己的 i18n 键重排 —— 不复用 core 的 `text`。

`/help` 和 `/commands` 加了一层 Telegram 专用清洗
(`gateway/slash_commands.py:1646-1649`、`1666-1669`),因为 Telegram 的命令名
只允许小写字母/数字/下划线(`gateway/run.py:866-872`)。
`/commands` 还把"页大小"当作 surface 参数下推(`gateway/slash_commands.py:1656-1663`):
```python
        # Page size is a surface parameter (Telegram messages are shorter).
        page_size = 15 if event.source.platform == Platform.TELEGRAM else 20
```

**可迁移原则**:core 只出"canonical 值 + canonical 文案",surface 出"分页大小 /
markdown 方言 / emoji / i18n"。`execute` 字段存字符串 key 而非 callable
是这套分层能保持 import 轻量的关键。

---

### 2.11 `/kanban`:唯一一个"命令即 CLI 透传"的

`gateway/slash_commands.py:451-458 @ 863e313`
```python
        text = (event.text or "").strip()
        # Strip the leading "/kanban" (with or without slash), leaving args.
        if text.startswith("/"):
            text = text.lstrip("/")
        if text.startswith("kanban"):
            text = text[len("kanban"):].lstrip()

        tokens = shlex.split(text) if text else []
```
然后整串丢给 `run_slash(text)`(480)。

有两个附加行为值得记:
- **create 自动订阅**(484-532):正则 `r"Created\s+(t_[0-9a-f]+)\b"` 从 CLI 的成功行
  里抠 task id,然后把当前 (platform, chat, thread) 写进 kanban 的通知订阅表。
  注释 486-487 说 `--json` 时不订阅,因为"they're clearly scripting"。
  **这是"从子系统的人类可读输出里正则抠 id"—— 脆弱耦合**,CLI 改一句文案就断。
- **长度截断**(534-537):`if len(output) > 3800:`,硬编码。

---

## 3. 命令清单(本切片内定义的 handler)

| 命令 | handler | 行号 | 一句话作用 | 返回类型 |
|---|---|---|---|---|
| `/new`,`/reset` | `_handle_reset_command` | 119–326 | 轮换 session id,清 11 类会话状态,可带 title | `str \| EphemeralReply` |
| `/profile` | `_handle_profile_command` | 328–379 | 报当前 profile 名 + home 目录(多路复用时按 source 解析) | `str` |
| `/whoami` | `_handle_whoami_command` | 381–430 | 报平台/scope/权限层级/可运行命令列表 | `str` |
| `/kanban` | `_handle_kanban_command` | 432–538 | 透传给 `hermes_cli.kanban.run_slash`,create 时自动订阅通知 | `str` |
| `/status` | `_handle_status_command` | 540–713 | session id/title/时间/模型/上下文/token/是否在跑/队列深度/平台列表 | `str` |
| `/context`,`/ctx` | `_handle_context_command` | 722–910 | 上下文深视图:进度条 + 压缩阈值 + 压缩统计 + 吞吐;`all` 展开分类明细 | `str` |
| `/agents`,`/tasks` | `_handle_agents_command` | 1197–1346 | 列**全网关**在跑的 agent、进程、后台任务、异步 delegation | `str` |
| `/stop` | `_handle_stop_command` | 1348–1429 | 中断本 session(或授权后中断同 thread 的 sibling),清 typing 指示 | `str \| EphemeralReply` |
| `/platform` | `_handle_platform_command` | 1431–1522 | list / pause / resume 失败平台的重连队列(**pause/resume 实际不可达**,见 §4) | `str` |
| `/restart` | `_handle_restart_command` | 1524–1632 | 去重后 drain 并重启网关,写两个 marker 文件 | `str \| EphemeralReply` |
| `/version`,`/v` | `_handle_version_command` | 1634–1638 | 转发共享执行器 `version` | `str` |
| `/help` | `_handle_help_command` | 1640–1649 | 转发共享执行器 `gateway_help` + Telegram 命令名清洗 | `str` |
| `/commands` | `_handle_commands_command` | 1651–1669 | 转发共享执行器 `gateway_commands`,页大小按平台 | `str` |
| `/model` | `_handle_model_command` | 1671–2000+ | 换模型 / 换 provider / picker;`--once/--session/--global/--provider/--refresh` | `Optional[str]` |

辅助方法(非命令):`_typed_command_prefix_for`(106)、`_redact_matrix_session_key`(715)、
`_gateway_session_origin_for_id`(912)、`_same_matrix_room`(927)、`_same_origin_chat`(945)、
`_resume_caller_is_admin`(1011)、`_resume_target_allowed`(1030)、`_resume_row_visible`(1173)。
后五个服务的是 `/resume` 和 `/sessions` —— 那两个 handler 在切片外。

---

## 4. ▲/◇ 候选

### ▲-1 `/platform pause|resume` 在真实网关里**不可达**(代码自身 bug,不是文档问题,但由文档暴露)

- 代码侧:`gateway/slash_commands.py:1440-1446 @ 863e313`
  ```python
        text = (getattr(event, "content", "") or "").strip()
        # Strip the leading "/platform" (or "/PLATFORM") token if present
        parts = text.split(maxsplit=2)
        if parts and parts[0].lower().lstrip("/").startswith("platform"):
            parts = parts[1:]
        action = (parts[0] if parts else "list").lower()
        target = parts[1].lower() if len(parts) > 1 else ""
  ```
- `MessageEvent` **没有 `content` 字段**。AST 枚举全部字段:`text`(2061)、
  `message_type`(2062)、`source`(2065)、`raw_message`(2068)、`message_id`(2069)、
  `platform_update_id`(2078)、`media_urls`(2082)、`media_types`(2083)、
  `reply_to_*`(2086–2090)、`prompt_response`(2100)、`auto_skill`(2104)、
  `channel_prompt`(2108)、`channel_context`(2114)、`internal`(2118)、
  `metadata`(2125)、`timestamp`(2128)。全仓也没有任何地方给 event 赋 `.content`
  (只有测试里赋)。
- 后果:真实事件走进来 `text=""` → `parts=[]` → `action="list"`。
  **`/platform pause whatsapp` 永远只打印列表。**
- **测试掩盖了它**:`tests/gateway/test_platform_reconnect.py:406-408 @ 863e313`
  ```python
    def _make_event(self, content: str):
        ev = MagicMock()
        ev.content = content
        return ev
  ```
  用 MagicMock 自造了一个不存在的字段,于是 `test_pause_command_pauses_queued_platform`
  (同文件 429)绿灯通过。
- 文档侧:`website/docs/reference/slash-commands.md:273 @ 863e313`
  "`/platform pause <name>` stops dispatching new messages to that adapter without
  unloading it; `/platform resume <name>` re-enables it and clears a tripped circuit
  breaker once the upstream is healthy."
  —— **双重错误**:(a) 功能不可达;(b) 即使可达,代码操作的是
  `self._failed_platforms`(重连队列,`gateway/slash_commands.py:1464`、`1488`),
  对已连接的平台会直接回 "is not in the retry queue (it's either connected or not
  enabled)."(`gateway/slash_commands.py:1491-1494`),根本不是"停止向该适配器投递消息"。

### ▲-2 消息平台上 `/reset now` 不会跳过确认,反而会把 "now" 当标题

- 文档侧:`website/docs/reference/slash-commands.md:226 @ 863e313`(位于
  `## Messaging slash commands` 段,标题在 216 行)
  "Append `now`, `--yes`, or `-y` to skip the confirmation modal — e.g. `/reset now`,
  `/new --yes my-experiment`."
- 代码侧 A:inline-skip 只在 CLI 里实现。`cli.py:11629 @ 863e313`
  `_DESTRUCTIVE_SKIP_TOKENS = frozenset({"now", "--yes", "-y"})`,
  剥离逻辑 `cli.py:11632-11660`(`_split_destructive_skip`),
  CLI `/new` 分支在取 title 前先剥离:`cli.py:10021-10025`。
- 代码侧 B:网关确认闸门 `gateway/run.py:20483-20518` 只看
  `approvals.destructive_slash_confirm` 配置,**没有任何 token 解析**。
- 代码侧 C:网关 `/new` 取 title 时**不剥离** —— `gateway/slash_commands.py:269 @ 863e313`
  ```python
        _title_arg = event.get_command_args().strip()
  ```
  所以确认之后 `/reset now` 会新建一个标题叫 `now` 的会话。

### ▲-3 `/status` 文档承诺的 "Session recap" 从未实现(且实现代码是死代码)

- 文档侧:`website/docs/reference/slash-commands.md:227 @ 863e313`(messaging 段)
  "`/status` | Show session info, followed by a local **Session recap** block
  (recent turn counts, top tools used, files touched, latest prompt + reply)."
  CLI 段同样承诺(同文件 :63)。
- 代码侧:`_handle_status_command`(`gateway/slash_commands.py:540-713`)拼的
  `lines` 里没有 recap —— 只有 header / session_id / title / created / last_activity /
  model / context / tokens / agent_running / queued / Matrix scope / platforms
  (671–711)。
- **`build_recap` 是死代码**:全仓 grep `build_recap` 只命中
  `hermes_cli/session_recap.py:244`(定义)、`:322`(`__all__`)、
  `tests/hermes_cli/test_session_recap.py:7,43,57`。**没有任何 production 调用点。**
- 而它自己的模块 docstring 还在宣称两边都在用:
  `hermes_cli/session_recap.py:13-16 @ 863e313`
  ```
      - Works unchanged on CLI and every gateway platform (Telegram,
        Discord, Slack, …) because both call into the same ``build_recap``
        helper. Claude Code only shows this on the CLI.
  ```

### ▲-4 `gateway-internals.md` 的 busy-guard 代码片段是被淘汰的写法

- 文档侧:`website/docs/developer-guide/gateway-internals.md:127-131 @ 863e313`
  ```python
  if _quick_key in self._running_agents:
      if canonical == "model":
          return "⏳ Agent is running — wait for it to finish or /stop first."
  ```
  紧接的一句(:132)"Bypass commands (`/stop`, `/new`, `/approve`, `/deny`, `/queue`,
  `/status`) have special handling."
- 代码侧:`hermes_cli/commands.py:59-62 @ 863e313` 明说这套 if 链已被替换:
  ```
      # Mid-run (agent busy) gateway behavior.  Drives the Guard-2 dispatcher
      # in gateway/run.py (_dispatch_busy_slash_command) instead of a
      # hand-written per-command if-chain.
  ```
  且旁路集合不是那 6 条,而是**所有可解析命令**:
  `hermes_cli/commands.py:496` `return resolve_command(command_name) is not None if command_name else False`。

### ▲-5 `gateway-internals.md` 说 `resolve_command()` 做前缀匹配 —— 它不做

- 文档侧:`website/docs/developer-guide/gateway-internals.md:117 @ 863e313`
  "`resolve_command()` from `hermes_cli/commands.py` maps input to canonical name
  (handles aliases, prefix matching)"
- 代码侧:`hermes_cli/commands.py:367 @ 863e313`
  `return _COMMAND_LOOKUP.get(name.lower().lstrip("/"))` —— 纯 exact dict lookup。
  前缀匹配是 CLI REPL 侧的能力(`hermes_cli/tips.py:259` 也只把它当 CLI 提示宣传),
  网关没有。

### ▲-6 `/agents` 文档说"当前会话",代码是全网关

- 文档侧:`website/docs/reference/slash-commands.md:65 @ 863e313`
  "`/agents` (alias: `/tasks`) | Show active agents and running tasks across the
  current session."
- 代码侧:`gateway/slash_commands.py:1205-1209 @ 863e313`
  ```python
        running_agents: dict = getattr(self, "_running_agents", {}) or {}
        running_started: dict = getattr(self, "_running_agents_ts", {}) or {}

        agent_rows: list[dict] = []
        for session_key, agent in running_agents.items():
  ```
  遍历的是全 runner 的 `_running_agents`,**当前会话只是被打个 "this chat" 标记**
  (`gateway/slash_commands.py:1247`)。这在共享/多用户网关上是跨会话信息暴露面。

### ▲-7 本文件自己的 docstring 数字已过期

- `gateway/slash_commands.py:4 @ 863e313`
  ```
  the in-session slash commands (/model, /reset, /usage, /compress, ...) the
  gateway dispatches from ``_handle_message``. There are 42 of them (~3,200 LOC);
  ```
- 实测:`grep -c "    async def _handle_.*_command"` = **52**;`wc -l` = **5693**。

### ▲-8 `slash_access.py` 的注释把 `/status` 算进"永远可用"集合,代码里没有

- `gateway/slash_access.py:42-45 @ 863e313`
  ```
  # slash gating is enabled and the user has no commands listed. Without this
  # carve-out, a non-admin user has no way to discover what they can or
  # can't do (``/help``, ``/whoami``) and no way to see what state the agent
  # is in (``/status``). These mirror the smallest set of read-only commands
  ```
- 但集合只有两项(`gateway/slash_access.py:50-53`,已在 §2.4 引用)。
  本文件里 `/whoami` 的镜像也是两项:`gateway/slash_commands.py:415 @ 863e313`
  ```python
        floor = ["help", "whoami"]  # mirrors slash_access._ALWAYS_ALLOWED_FOR_USERS
  ```
  即代码一致、注释多写了一个。

### ◇-1 `gateway/slash_commands.py` 这个模块在开发者文档里根本不存在

`website/docs/developer-guide/gateway-internals.md:13-26 @ 863e313` 的 "Key Files"
表列了 `run.py`/`session.py`/`delivery.py`/`pairing.py`/`channel_directory.py`/
`hooks.py`/`mirror.py`/`status.py`/`builtin_hooks/`/`platform_registry.py`/
`plugins/platforms/`/`gateway/platforms/`,**没有 `slash_commands.py`**;
而且 :15 仍把 slash commands 归给 `gateway/run.py`。这是 5693 行代码的黑洞。

### ◇-2 `execute` 字段(registry-owned 共享执行器)全无文档

`CommandDef.execute`(`hermes_cli/commands.py:80-89`)+ `hermes_cli/slash_exec.py`
的 `CommandContext`/`CommandReply`/`EXECUTORS`(:41、:51、:234)是一套完整的
"core 出文案、surface 出装饰"分层契约,`website/docs/developer-guide/extending-the-cli.md`
和 `gateway-internals.md` 都没提。

### ◇-3 `_model_switch_skew_guard`(代码漂移闸门)全无文档

`gateway/slash_commands.py:72-98` + `gateway/code_skew.py`。文档里没有任何
"长跑网关 + `git pull` 会导致换模型崩溃"的说明,而这是运维会真实撞上的。

### ◇-4 `EphemeralReply` 的自动删除语义全无文档

`gateway/platforms/base.py:2375-2394`。用户看到 `/new`、`/stop`、`/restart`
的回复过一会儿消失,文档不解释;也没写 `display.ephemeral_system_ttl` 这个开关。

### ◇-5 跨 origin `/resume` 的 IDOR 防线全无文档

`gateway/slash_commands.py:1011-1195` 这 185 行安全逻辑(含 CWE-639 标注)在
`website/docs/user-guide/security.md` 里没有对应说明,运营方不会知道
"legacy NULL-owner 行不可 resume,要用 admin `--all`"。

### 死代码 / 命名不符

- **`logger` 名与模块不符**:`gateway/slash_commands.py:50 @ 863e313`
  ```python
  logger = logging.getLogger("gateway.run")
  ```
  看起来是为了让既有的 `gateway.run` 日志过滤/等级配置继续覆盖这些 handler,
  但代价是日志里再也分不出是 run.py 还是 slash_commands.py 打的。
- **`_clean_str` / `_int_value` 各定义两遍**:模块级 59–69,
  `_handle_status_command` 内部又定义一遍 560–567(逐字相同)。
  内层遮蔽外层;模块级那份被 `_handle_context_command` 用(772、775、781、789)。
  应是 god-file 拆分时的搬运残留。
- **`_gateway_session_origin_for_id` 的 fallback 分支**(`gateway/slash_commands.py:919-925`)
  注释说是给 "Test doubles and older stores" 用的,直接线性扫 `_entries` 私有字典。
- **`build_recap`** 见 ▲-3。
- **`_handle_platform_command` 的 pause/resume 分支**(1482–1515)在生产不可达,见 ▲-1。

---

## 5. issue 溯源(切片内注释里出现的编号)

| # | 行号 | 注释原文(节选) | 因果 |
|---|---|---|---|
| **#35994** | 55、146、169、175 | "This handler runs ON the event loop when a Telegram/Discord/Slack confirm-button click resolves the slash-confirm (see `_request_slash_confirm`), so an inline call wedges the whole loop and the bot goes silent until restart (#35994)." | **输入**:用户点 `/new` 确认弹窗的按钮。**现象**:整个网关静默,所有平台都不回话,直到重启。**为什么**:`_cleanup_agent_resources` 是同步的,里面做 `agent.close()`(子进程 teardown)和 `shutdown_memory_provider()`(可能网络 IO);按钮回调是在事件循环上 resolve 的,于是同步调用把 loop 整个卡死。**怎么修**:`gateway/slash_commands.py:156-161` 改成 `await asyncio.wait_for(self._run_in_executor_with_context(self._cleanup_agent_resources, _old_agent), timeout=_RESET_CLEANUP_TIMEOUT_S)`,30 秒超时。超时后**不取消线程**(取消不了),只打 warning 让 reset 继续 —— `gateway/slash_commands.py:163-171` 诚实写明 "the worker thread is left to finish on its own"。 |
| **#28686** | 129 | "clearing here keeps the slot from becoming a zombie that silently drops all later messages (#28686)" | **输入**:重置一个正在跑的会话。**现象**:此后该会话的所有消息都被静默丢弃。**为什么**:reset 把 run generation 加一,在飞的那次 run 在 `finally` 里调用带 generation 守卫的释放,守卫发现 generation 已变就返回 False → 死 agent 永远占着 `_running_agents` 槽 → 后续消息全被 busy 守卫挡掉。**怎么修**:reset 自己先 `self._release_running_agent_state(session_key)`(`gateway/slash_commands.py:131`),幂等,所以在飞的 run 再调一次无害。 |
| **#55578** | 187 | "The old conversation's in-flight async delegations end WITH it (#55578): after the reset rotates the session id, their completions would have no live owner — a dangling subagent can only burn tokens and park an orphaned payload on the shared queue." | **输入**:发起了后台 delegation 之后 `/new`。**现象**:子 agent 继续烧 token,完成后把结果丢进共享队列没人认领。**为什么**:delegation 绑在旧 session id 上,reset 轮换了 id。**怎么修**:`gateway/slash_commands.py:194-200` 调 `interrupt_for_session(session_key=..., parent_session_id=<旧 session_id>, reason="session_reset")` —— 同时按 durable session id **和** routing key 两个维度中断(注释 190-192 说后者是给老记录兜底)。 |
| **#59003** | 253、337 | "scoped to the profile serving this source so a multiplexed /reset //new banner reports the profile's model, not the base config's (#59003)" | **输入**:多路复用网关(一个进程服务多个 profile)里在某个 profile 的房间发 `/reset` 或 `/profile`。**现象**:banner 报的是 base config 的模型 / `default` profile,不是这个房间实际的 profile。**为什么**:进程级 active profile 永远是多路复用器自己的。**怎么修**:`/reset` 走 `self._reset_notice_session_info(source)`(255-257),`/profile` 走 `_profile_runtime_scope(profile_home)` 上下文管理器(`gateway/slash_commands.py:356-360`)。注意 `gateway/slash_commands.py:338-341` 明写:多路复用**关掉**时这个 stamp 被忽略,行为 byte-identical 于改动前。 |
| **#51690** | 1284 | "Live per-child activity comes from the registry's progress sampler (#51690): api calls, current tool, seconds since last activity." | `/agents` 里 background delegation 的 per-child 活动采样。仅此一处引用,**注释未描述故障现象**,只说数据来源。 |
| **#32295** | 1412 | "A platform status indicator can still be stuck — e.g. Slack's persistent `assistant.threads.setStatus` survives a gateway restart or a turn that died without a final send (#32295)." | **输入**:一次 turn 崩了 / 网关重启,之后发 `/stop`。**现象**:Slack 里 "is thinking..." 幽灵状态一直挂着。**为什么**:Slack 的 `assistant.threads.setStatus` 是持久状态,不随进程死亡清除。**怎么修**:`gateway/slash_commands.py:1414-1427` 在"没有任何在跑 agent"这条分支上,仍然 best-effort 调 `adapter._stop_typing_with_metadata(...)`,让 `/stop` 至少总能消掉幽灵指示。 |
| **#30479** | 1760 | "Normalize the source the same way a normal message turn does (Telegram DM topic recovery) before deriving the override key, so the override is stored under the key the next message turn reads (#30479)." | **输入**:在 Telegram DM topic 里 `/model X`。**现象**:下一条消息还是用旧模型。**为什么**:`/model` 用未归一化的 source 算 session_key,而正常消息 turn 会先做 topic 归一化 —— 两个 key 不一样,override 写在了读不到的地方。**怎么修**:`gateway/slash_commands.py:1761` `source = await asyncio.to_thread(self._normalize_source_for_session_key, source)`。 |
| **#41289** | 1786、1822 | "Offload blocking provider-listing (can fall through to a synchronous urllib HTTP fetch on a stale cache) off the event loop so the gateway doesn't freeze. See #41289." | **输入**:缓存过期时发 `/model`(无参,走 picker)。**现象**:整个网关冻结十几秒。**为什么**:`list_picker_providers` 冷缓存会同步 urllib 取 provider 列表,跑在事件循环上。**怎么修**:`asyncio.to_thread`。 |
| **#20525** | 1822 | "switch_model() can fall through to a synchronous models.dev HTTP fetch (requests.get, 15s timeout) on a cold/expired cache, which freezes the gateway otherwise. See #20525, #41289." | 同上,受害函数是 `switch_model`,超时 15 秒。 |
| **#50163** | 1883 | "A failed switch must be a no-op. (#50163)" | **输入**:picker 里点了一个坏模型(如凭据失效)。**现象**:不但换不过去,**整个对话丢失** —— 下一条消息重建 agent 时按坏 override 建,建不起来。**为什么**:原实现即使 `switch_model()` 抛异常,后面仍然继续写 SessionDB、写 session override、淘汰缓存 agent。**怎么修**:`gateway/slash_commands.py:1874-1893` 捕获异常后**立即 return**,提交序列的后三步全部不执行,并回一句 "staying on {旧模型}"。 |
| **#34850** | 1896 | "Persist the new model to the session DB so the dashboard shows the updated model (#34850)." | 换模型后 dashboard 显示旧模型 —— 因为 override 只在内存,DB 没更新。修法:`update_session_model`(1903-1905)。 |
| **#49066** | 1954 | "Persist to config (default) unless --session opted out, mirroring the text /model command path above so a picked model survives across sessions like a typed one (#49066)." | **输入**:用 picker 点选模型 vs 打字 `/model X`。**现象**:两条路径持久化行为不一致 —— 打字的会写 config.yaml,点选的不会,新会话回退旧模型。**怎么修**:picker 回调里加上同样的 `if persist_global:` 分支(1955-2009)。 |
| **#25107** | 1993 | "the previous lone `if result.base_url:` left a stale base_url behind when switching to a custom provider whose resolver returned an empty base_url (#25107)" | **输入**:从某个自定义 provider 切到另一个 base_url 解析为空的自定义 provider。**现象**:config.yaml 里留着**上一个** provider 的 base_url(和 api_mode),下次启动连错端点。**为什么**:原代码只有 `if result.base_url: 写入`,没有 else 清除;命名 provider 每次都从注册表重解析所以不受影响,自定义 provider 没有注册表可重解析。**怎么修**:`gateway/slash_commands.py:1994-2005` 引入 `_is_custom_target`,自定义目标显式 set-or-clear `base_url`/`api_mode`,非自定义走 `clear_model_endpoint_credentials(..., clear_base_url=True)` 无条件清。 |
| `#bernard-thread-stop` | 1390 | "Authorized users should still be able to /stop it (#bernard-thread-stop)." | **非数字 issue 标记**,像是内部/人名标签。**输入**:`thread_sessions_per_user=True` 的共享 thread 里,A 起了一次 run,B 发 `/stop`。**现象**:B 的 session_key 下没有 run,`/stop` 说"没有活跃 agent"。**怎么修**:`gateway/slash_commands.py:1392-1407` 找同 thread 的 sibling key,在 `self._is_user_authorized(source)` 通过后逐个中断。 |

---

## 6. 测试(钉住本切片行为的文件)

| 测试文件 | 钉住什么 |
|---|---|
| `tests/gateway/test_35994_reset_button_deadlock.py` | `test_reset_does_not_block_event_loop_during_cleanup`(:93)、`test_reset_completes_when_cleanup_raises`(:148)、`test_reset_completes_when_cleanup_times_out`(:178)。三条直接钉 `_RESET_CLEANUP_TIMEOUT_S` 语义。 |
| `tests/gateway/test_title_command.py` | `/new <title>` 全链:重名冲突(:62)、控制字符 sanitize(:79)、Telegram topic 改名(:94)、`test_reset_command_duplicate_title_surfaces_warning`(:160,直接调 `runner._handle_reset_command`,:213)。 |
| `tests/gateway/test_session_model_reset.py` | `test_new_command_only_clears_own_session`(:70)—— `/new` 不得清别的会话的 model override。 |
| `tests/gateway/test_async_delegation_session_binding.py` | `test_reset_command_calls_interrupt_for_session`(:212)。做法特别:`inspect.getsource(slash_commands.GatewaySlashCommandsMixin._handle_reset_command)`(:217)—— **源码文本断言**,脆但能钉住 #55578 那段不被删掉。 |
| `tests/gateway/test_status_command.py` | `test_status_command_reads_token_totals_from_session_db`(:78)、`test_status_command_includes_live_agent_model_and_context`(:107)、`test_agents_command_reports_active_agents_and_processes`(:145)、`test_tasks_alias_routes_to_agents_command`(:189)、`test_status_command_bypasses_active_session_guard`(:327)、`test_profile_command_reports_source_stamped_profile`(:384,#59003)、`test_context_all_appends_expanded_listings`(:441)。**一个文件覆盖了 status/agents/profile/context 四个命令。** |
| `tests/gateway/test_agents_command_delegations.py` | `test_agents_command_marks_stalling_delegation`(:48)。 |
| `tests/gateway/test_resume_command.py` | `TestSameOriginChatGroupScoping`(:662)钉 `_same_origin_chat`:`test_dm_cross_user_blocked_without_chat_id`(:675)、`test_allows_same_thread_shared_participants`(:702)、`test_blocks_thread_vs_no_thread`(:711);`TestResumeRowVisibleMatrixAllScoping`(:721);`TestSameMatrixRoomThreadScoping`(:743)含 `test_cross_thread_same_room_blocked`(:762)。**这是本切片安全逻辑的行为规格。** |
| `tests/gateway/test_stop_thread_sibling.py` | `test_sibling_returns_empty_for_non_thread_source`(:44)等,钉 `/stop` 的 thread sibling 路径。 |
| `tests/gateway/test_platform_reconnect.py` | `TestPlatformSlashCommand`(:403)。**但用 MagicMock + 假 `.content` 字段(:406-408),掩盖了 ▲-1。** |
| `tests/gateway/test_restart_redelivery_dedup.py` | 五条:旧 update_id 被忽略(:30)、marker 超 5 分钟不再拦(:55)、无 update_id 时绕过(:79)、跨平台绕过(:103)、marker 丢失但 booted-from-restart 仍忽略(:142)。 |
| `tests/gateway/test_restart_service_detection.py` / `test_restart_notification.py` / `restart_test_helpers.py` | `/restart` 的 systemd/容器分支与重启后回话。 |
| `tests/gateway/test_slash_access_dispatch.py` | `/whoami` 的输出与门控:`test_whoami_non_admin_lists_runnable_commands`(:121)、`test_non_admin_with_empty_user_commands_gets_floor_only`(:142)、`test_group_only_gating_leaves_dm_unrestricted`(:174)、`test_running_agent_fastpath_allows_admin_command`(:249,钉"busy 路径也要过鉴权")、`test_gating_isolated_per_platform`(:297)。 |
| `tests/gateway/test_version_command.py` | `test_gateway_version_command_returns_release_line`(:8)。写法值得注意:`GatewayRunner._handle_version_command(None, None)`(:11)—— **unbound 调用,self 和 event 都传 None**,反证这个 handler 完全无状态。 |
| `tests/gateway/test_gateway_command_help.py` | `/help`(:30)与 `/commands`(:51)的 Telegram 命令名清洗。 |
| `tests/test_code_skew.py` | `TestModelSwitchSkewGuard`(:48):`test_guard_returns_none_without_skew`(:49)、`test_guard_message_names_revs_and_restart`(:55)。 |
| `tests/gateway/test_model_command_async_offload.py` | `test_picker_path_offloads_list_picker_providers`(:107)—— #41289。 |
| `tests/gateway/test_model_command_context_offload.py` | `test_context_resolution_runs_off_the_loop_thread`(:96)、`test_warning_enrichment_is_offloaded`(:125)。 |
| `tests/gateway/test_model_picker_persist.py` | `test_picker_tap_global_flag_persists`(:181)、`test_multiplex_picker_global_persists_only_named_profile`(:205)—— #49066。 |
| `tests/gateway/test_25107_stale_base_url_api_mode.py` | `test_typed_switch_to_custom_clears_stale_base_url_and_api_mode`(:124)、`test_picker_tap_to_custom_clears_stale_base_url_and_api_mode`(:159)。 |
| `tests/gateway/test_model_command_custom_providers.py` / `test_model_command_expensive_confirm.py` / `test_model_command_flat_string_config.py` / `test_model_switch_persistence.py` | `/model` 的自定义 provider、贵模型二次确认、config 里 `model:` 写成字符串的兼容、持久化。 |
| `tests/gateway/test_destructive_slash_always_persist_report.py` | `/new` 确认弹窗 "Always Approve" 的持久化成败上报(:82/:96/:107/:120/:128)。fixture 里 `obj._typed_command_prefix_for = lambda platform: "/"`(:35)—— 说明这个 helper 是确认文案的必需依赖。 |
| `tests/gateway/test_matrix_project_context_isolation.py` | `:291` 用 `/status` 验证 Matrix 跨房间隔离。 |
| `tests/gateway/test_max_concurrent_sessions.py` / `tests/e2e/test_platform_commands.py` / `tests/gateway/test_update_streaming.py` | 把 handler mock 掉,钉的是**分发是否到达**(如 `runner._handle_reset_command.assert_awaited_once_with(event)`,test_update_streaming.py:358)。 |
| `tests/gateway/test_unknown_command.py` | `:126` 注释说明未知命令的兜底路径。 |
| `tests/hermes_cli/test_kanban_notify.py` | `/kanban create` 自动订阅。 |

---

## 7. 重实现要点(造自己的 harness 必须复刻什么)

1. **注册表与 handler 分离,元数据下沉到注册表**。至少要有:canonical name、
   aliases、surface 可见性(CLI-only / gateway-only / config-gated)、
   **并发策略**(busy_policy)。别把这些写成 handler 上的装饰器 —— 因为 CLI 补全、
   `/help` 渲染、网关 dispatch 三个消费者都要在**不 import handler** 的前提下读到它们。
2. **并发策略必须是一等元数据,而不是 handler 里的 `if agent_running`**。
   三个值就够:`dispatch`(照跑)/ `reject`(拒绝)/ `interrupt_then_dispatch`(先杀再跑)。
   并且要有"声明了 dispatch 但没登记 handler"的自检 warning
   (`gateway/run.py:14158-14161`)。
3. **"任何可识别命令都不得进入排队"**。hermes 的血泪教训写在
   `hermes_cli/commands.py:485-491`:命令文本一旦进了 pending queue 会被安全网丢弃,
   结果是"打断了 agent 又什么都没回",零字符响应。
4. **权限维度与并发维度正交**,不要合并。hermes 的 `/whoami` 是
   "谁都能用 + 忙时不能用",`/status` 是"要授权 + 忙时能用"。
5. **返回值协议要能表达"不回复"**。`""` 和 `None` 都要被上层理解为静默。
   ephemeral(自动删除)可以用 str 子类做零成本迁移,但要在拼接点小心属性丢失。
6. **handler 里所有可能 IO 的同步调用一律 offload**,并给带超时的兜底。
   这是本切片出现频率最高的模式(至少 10 处 `asyncio.to_thread`)。
   尤其注意:**按钮回调也跑在事件循环上**,不是只有消息路径要担心(#35994)。
7. **会话边界要做成一张显式清单 + 一个 funnel 函数**,不要在 reset handler 里散写 pop。
   参考 `_clear_conversation_scope` / `_CONVERSATION_SCOPED_STATE`
   (`gateway/slash_commands.py:180-184`)。
8. **任何"按 id 恢复/枚举会话"的命令都是 IDOR 面**。守卫的比较字段必须与
   session key 的构造字段**逐个对齐**,并把对齐关系函数化
   (`is_shared_multi_user_session`),证明不了归属就 fail closed。
9. **命令解析要有单一入口,并禁止 handler 自己重解析 `event.text`**。
   本切片两个自己解析的 handler(kanban、platform)一个漏了 `@botname`、
   一个读了不存在的字段。
10. **"core 出 canonical 文案 + 结构化 data,surface 只加装饰"**。
    并把 executor 用**字符串 key** 挂在注册表上,保持注册表 import 轻量。
11. **长跑进程 + 延迟 import = 代码漂移风险**。要么禁止延迟 import,
    要么像 `_model_switch_skew_guard` 一样在最危险的入口挡一道并给人话。
12. **自我重启必须去重**,而且去重标记要与"重启后通知"标记**分开存**
    (后者会被消费删除,不能当去重依据)。重启方式还要按 systemd / 容器 /
    裸进程分支(退出码 75 vs detached setsid)。
