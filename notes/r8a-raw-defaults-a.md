# r8a-raw-defaults-a · config_defaults.py:1-2200

> 底稿(求全求证)。研究对象:`NousResearch/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(下称 863e313)。
> 本篇负责 `hermes_cli/config_defaults.py` 的 **第 1-2200 行**(全文 4313 行)。
> 溯源约定:凡对 hermes-agent 行为的断言,行尾给 `路径:行号 @ 863e313`,紧跟原文代码块。
> 所有相对路径以基线仓库根为准。

---

## 0. 段落边界、方法与自验

### 0.1 边界

本文件只有两个模块级对象:`DEFAULT_CONFIG`(第 7-3127 行)与 `OPTIONAL_ENV_VARS`(第 3130-4313 行)。
我这一段 1-2200 完整覆盖 `DEFAULT_CONFIG` 的前约 2/3,**不含** `OPTIONAL_ENV_VARS`。

文件以 docstring 声明自己是"纯数据叶子模块"。`hermes_cli/config_defaults.py:1 @ 863e313`

```python
"""Default configuration data for Hermes Agent.

Pure-data leaf module: DEFAULT_CONFIG and OPTIONAL_ENV_VARS, extracted
verbatim from hermes_cli/config.py. Must not import from hermes_cli.config.
"""
```

`DEFAULT_CONFIG` 是一个字面量 dict,第 7 行开始。`hermes_cli/config_defaults.py:7 @ 863e313`

```python
DEFAULT_CONFIG = {
```

我这一段的**最后一个键**是 `cron.chronos.expected_audience`(第 2199 行);
`cron.chronos.nas_jwks_url`(2202)、`cron.wrap_response`(2206)、`kanban.*`(2251 起)已越界,归下一段。
`hermes_cli/config_defaults.py:2199 @ 863e313`

```python
            "expected_audience": "",
```

### 0.2 方法

- 用 `ast` 解析 `DEFAULT_CONFIG` 字面量,机械枚举 1-2200 行内的**每一个**键(含嵌套),
  得到 **683 行**(其中 102 行是"容器键"即值为非空 dict 的中间节点,581 行是叶子键)。
  全表见第 10 节。
- 注释归属规则:同一物理行的行尾注释优先;否则取紧邻上方的连续整行注释块;
  行尾注释后与之对齐的续行注释视为同一段注释。少数键(如 `agent.max_turns`)源码**没有任何注释**,
  表中该列留空——这本身是发现。
- 为了回答"这个键谁读、有没有 fallback 链",我越界读了 `hermes_cli/config.py`、`hermes_state.py`、
  `tools/url_safety.py`、`tools/terminal_tool.py`、`agent/context_compressor.py` 等消费侧,
  凡越界处均已标注文件名。

### 0.3 一句话结论(5 条)

1. `DEFAULT_CONFIG` 不是"默认值表",它同时是**四种东西**:合并基座、迁移清单、写回裁剪基准、
   `hermes config set` 的路径校验 schema。改动它会同时影响这四条链路。
2. 这份默认值的**注释密度极高**(2200 行里 683 个键,大量键的注释比代码长十倍),
   注释里普遍写了"为什么是这个值"和"调大/调小的后果",实际上是一份 ADR(架构决策记录)集合。
3. 默认值的总体姿态:**安全性与隔离默认保守(全部 opt-in),可用性与自动纠错默认激进(全部 opt-out)**,
   花钱的东西默认最保守(`curator.consolidate=False`、`compression.micro_compact=False`、
   `delegation.max_spawn_depth=1`)。
4. `DEFAULT_CONFIG` **不是**已识别配置键的全集:`agent.reasoning_effort`、`terminal.ssh_host`、
   `whatsapp.reply_prefix` 等是真实被读取的键却不在表里,导致 `hermes config set` 给出**误导性**的
   "did you mean" 建议(见第 8 节)。
5. 大量消费侧**不走**合并后的配置,而是 `read_raw_config()` + 自带字面量默认(如 `tools/url_safety.py`),
   或经由 `TERMINAL_CONFIG_ENV_MAP` 把 `terminal.*` 投影成 `TERMINAL_*` 环境变量再读;
   于是同一个默认值在仓库里被写了两遍甚至三遍。

---

## 1. 机制一:纯数据叶子模块

**解决什么问题。** `hermes_cli/config.py` 是一个 4900+ 行的巨型模块(加载、迁移、校验、写回、env 桥接
全在里面)。任何想读默认值的模块(gateway、cron、plugins)若 `import hermes_cli.config`,
就会拖进整条依赖链和它的启动副作用。

**怎么实现。** 把两个纯字面量抽到一个**不 import 任何仓库内模块**的叶子文件,再由 `config.py`
重新导出,保持旧的 `from hermes_cli.config import DEFAULT_CONFIG` 导入路径不破。
`hermes_cli/config.py:943 @ 863e313`

```python
from hermes_cli.config_defaults import DEFAULT_CONFIG, OPTIONAL_ENV_VARS  # noqa: F401
```

**为什么这么设计。** docstring 明写 "Must not import from hermes_cli.config",这是一条**手写的
依赖方向约束**(没有 lint 强制,见第 8 节)。

**取舍。** 好处是任何人都能零成本读默认值;代价是默认值与它的读取/校验逻辑物理分离,
"这个键谁读"必须靠全仓 grep,文件本身不提供任何索引。

---

## 2. 机制二:DEFAULT_CONFIG 的四重身份

这是理解这份文件的关键——它不只是"缺省值"。

### 2.1 身份 A:深合并基座(load_config)

加载时先深拷贝 `DEFAULT_CONFIG`,再把用户 YAML 合并上去。`hermes_cli/config.py:3333 @ 863e313`

```python
        config = copy.deepcopy(DEFAULT_CONFIG)
```

合并是**递归的**,用户只覆盖 `tts.elevenlabs.voice_id` 不会丢掉同级的 `model_id`;
并且把"空 section"(YAML 里写 `terminal:` 不给值 → `None`)当作"没写",避免整段默认被 `None` 覆盖。
`hermes_cli/config.py:2435 @ 863e313`

```python
def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, preserving nested defaults.

    Keys in *override* take precedence. If both values are dicts the merge
    recurses, so a user who overrides only ``tts.elevenlabs.voice_id`` will
    keep the default ``tts.elevenlabs.model_id`` intact.
```

这条规则直接决定了 `display.platforms` 那种"补空型默认"能成立(见 §5.7)。

**失败模式是"最后一次成功值"而非"回落默认"。** 用户把 config.yaml 改成非法 YAML 时,
若进程内有上次成功加载的配置,就继续用它,而不是掉回 `DEFAULT_CONFIG`——
因为掉回默认会**丢掉 `approvals.deny` 这类安全规则**。`hermes_cli/config.py:3347 @ 863e313`

```python
                config = _deep_merge(config, user_config)
```

### 2.2 身份 B:迁移清单(get_missing_config_fields)

`hermes update` 靠递归比对 `DEFAULT_CONFIG` 树与用户配置,报出"新增了哪些配置项"。
`hermes_cli/config.py:1189 @ 863e313`

```python
def get_missing_config_fields() -> List[Dict[str, Any]]:
```

### 2.3 身份 C:写回裁剪基准(_strip_default_values)

`save_config` 会把与默认相同的值全部剥掉,让 config.yaml 只留用户真正说过的话。
`hermes_cli/config.py:2698 @ 863e313`

```python
def _strip_default_values(
    config: Dict[str, Any],
    defaults: Dict[str, Any] = DEFAULT_CONFIG,
    preserve_keys: Optional[Set[Tuple[str, ...]]] = None,
) -> Dict[str, Any]:
```

这条链路有一个真实缺陷(把"被剥掉"和"值就是 None"混为一谈),见第 8 节 D-3。

### 2.4 身份 D:`hermes config set` 的路径校验 schema

`DEFAULT_CONFIG.keys()` 加上几个"开放 dict"白名单构成合法顶层键集合。
`hermes_cli/config.py:4698 @ 863e313`

```python
def _known_top_level_keys() -> set[str]:
```

再沿着用户给的点分路径走 `DEFAULT_CONFIG`,走不通就用 `difflib` 给"你是不是想写 X"。
`hermes_cli/config.py:4727 @ 863e313`

```python
def _validate_config_key(key: str) -> tuple[bool, Optional[str]]:
```

有三类顶层键被豁免深度校验:用户自定义内层键的开放 dict(`providers` / `hooks` / `goals` / …)、
平台配置这类"部分 schema + 动态 extras"(`discord` / `telegram` / `whatsapp` / `checkpoints` / `sessions`)、
以及位置索引的 `custom_providers`。`hermes_cli/config.py:4654 @ 863e313`

```python
_OPEN_DICT_TOP_LEVEL_KEYS = frozenset({
```

`hermes_cli/config.py:4673 @ 863e313`

```python
_SCHEMA_DEFINED_DICT_KEYS = frozenset({
```

**取舍。** 未知键**仍然写入**,只是打印一条 warning + 建议——设计者宁可放行也不阻塞
(注释里点名 #34067:`gateway.discord.gateway_restart_notification` 被静默写入却毫无效果)。
代价见第 8 节 D-1。

---

## 3. 机制三:同一个默认值被写了几遍(读取路径的分岔)

这是本段最容易被低估的复杂度来源。至少有 **4 条**不同的读取路径,它们对"默认值"的来源不一致。

### 3.1 路径一:合并后配置(最正统)

`load_config()` / `load_config_readonly()` 返回的 dict 已经含默认,消费方直接 `cfg["agent"]["max_turns"]`。

### 3.2 路径二:`read_raw_config()` + 消费方自己的字面量默认

典型是私网 URL 开关。它读**原始用户文件**(不含默认),因此必须自带 `default=False`,
于是 `security.allow_private_urls: False` 这个默认值在仓库里存在两份。
`tools/url_safety.py:248 @ 863e313`

```python
def _resolve_allow_private_urls() -> bool:
```

同一函数里还藏着一条**三级 fallback 链**:环境变量 > `security.allow_private_urls` >
`browser.allow_private_urls`(遗留)。`tools/url_safety.py:252 @ 863e313`

```python
    # 1. Env var override (highest priority)
    env_val = os.getenv("HERMES_ALLOW_PRIVATE_URLS", "").strip().lower()
```

`tools/url_safety.py:269 @ 863e313`

```python
        # browser.allow_private_urls (legacy fallback)
```

注意 `config_defaults.py` 里这两个键的注释**都没说**谁是首选、谁是遗留(见第 7 节 ▲2)。

### 3.3 路径三:config → 环境变量桥(terminal 专用)

`terminal.*` 的消费方是 `tools/terminal_tool.py`,它**只读环境变量**,因为同一份工具要在 TUI /
dashboard PTY / gateway worker 等子进程里跑。于是 `config.py` 提供一张显式映射表把配置投影成 env。
`hermes_cli/config.py:3183 @ 863e313`

```python
TERMINAL_CONFIG_ENV_MAP = {
    "backend": "TERMINAL_ENV",
```

桥接函数的语义:**用户文件里显式写过的 terminal 键覆盖 env;仅来自默认的值只回填缺失的 env**。
`hermes_cli/config.py:3232 @ 863e313`

```python
def apply_terminal_config_to_env(
```

`tools/terminal_tool.py` 那一侧再写一遍默认字面量:`tools/terminal_tool.py:1561 @ 863e313`

```python
        "local_persistent": os.getenv("TERMINAL_LOCAL_PERSISTENT", "false").lower() in {"true", "1", "yes"},
```

这就解释了 `terminal.persistent_shell: True` 的注释为何说"非 local 后端默认开,local 永远 opt-in":
配置键 `persistent_shell` 映射到 `TERMINAL_PERSISTENT_SHELL`,只被 SSH 分支消费,
local 分支读的是另一个 env `TERMINAL_LOCAL_PERSISTENT`(默认 `"false"`,与配置无关)。
`hermes_cli/config_defaults.py:361 @ 863e313`

```python
        "persistent_shell": True,
```

**桥表与 DEFAULT_CONFIG 并不同构**:桥表里有 8 个键在 `DEFAULT_CONFIG["terminal"]` 中不存在
(`lifetime_seconds`、`ssh_host`、`ssh_user`、`ssh_port`、`ssh_key`、
`docker_persist_across_processes`、`docker_orphan_reaper`、`sandbox_dir`);
反过来 `font_family`、`daemon_term_grace_seconds`、`env_passthrough`、`home_mode`、
`shell_init_files`、`auto_source_bashrc`、`docker_volumes`… 有的在桥表里,有的不在。

### 3.4 路径四:纯环境变量(不经过配置)

例如 embedder 环境描述:配置键 `agent.environment_hint` 与 env 二选一,env 赢。
`agent/prompt_builder.py:1266 @ 863e313`

```python
    extra = (os.getenv("HERMES_ENVIRONMENT_HINT") or "").strip()
```

---

## 4. 默认值的整体设计取舍(这份文件真正的知识)

把 683 个键横过来看,能读出几条一致的编码风格:

**(a) 安全/隔离一律 opt-in(默认关)。**
`terminal.docker_mount_cwd_to_workspace=False`(注释:把宿主目录塞进沙箱"weakens isolation")、
`browser.allow_private_urls=False`、`security.allow_private_urls=False`、
`skills.inline_shell=False`(注释:skill 作者的内容会**无审批**在宿主上执行)、
`delegation.subagent_auto_approve=False`(注释:子 agent 线程永远非交互式解审批,默认自动拒绝)、
`privacy.redact_pii=False`(这是个例外:隐私增强项也默认关,因为它改动送进模型的内容)。

`hermes_cli/config_defaults.py:336 @ 863e313`

```python
        "docker_mount_cwd_to_workspace": False,
```

`hermes_cli/config_defaults.py:1804 @ 863e313`

```python
        "inline_shell": False,
```

`hermes_cli/config_defaults.py:1727 @ 863e313`

```python
        "subagent_auto_approve": False,
```

**(b) 自动纠错/护栏一律 opt-out(默认开),且注释标了 token 成本。**
`agent.task_completion_guidance=True`("Costs ~80 tokens in the cached system prompt")、
`agent.parallel_tool_call_guidance=True`("~70 tokens")、`agent.environment_probe=True`
("Costs zero tokens when the env is clean")、`tool_loop_guardrails.warnings_enabled=True`。

`hermes_cli/config_defaults.py:94 @ 863e313`

```python
        "task_completion_guidance": True,
```

`hermes_cli/config_defaults.py:103 @ 863e313`

```python
        "parallel_tool_call_guidance": True,
```

**软告警默认开、硬停默认关**——交互式会话不能被护栏卡死。
`hermes_cli/config_defaults.py:535 @ 863e313`

```python
        "warnings_enabled": True,
        "hard_stop_enabled": False,
```

**(c) 花钱的东西默认最保守。**
`curator.consolidate=False`(关掉 LLM 合并 pass,只做确定性归档)、
`compression.micro_compact=False`(每轮一次 prompt-cache 断裂)、
`compression.proactive_prune_tokens=0`、`delegation.max_spawn_depth=1`
(注释:"raise deliberately, each level multiplies API cost")、
`auxiliary.free_only=False` 是反例(保持历史付费 fallback)。

`hermes_cli/config_defaults.py:1860 @ 863e313`

```python
        "consolidate": False,
```

`hermes_cli/config_defaults.py:1717 @ 863e313`

```python
        "max_spawn_depth": 1,        # depth (1 = flat [default], 2 = orchestrator→leaf, 3+ = deeper)
```

**(d) 明确写了"不要调大"的键(带理由),共 4 处值得记住:**

1. `agent.restart_drain_timeout=0` —— "Keep this short and under systemd TimeoutStopSec —
   a long value here invites SIGKILL-mid-cleanup"。调大 = 清理到一半被 SIGKILL。
   `hermes_cli/config_defaults.py:47 @ 863e313`

   ```python
        "restart_drain_timeout": 0,
   ```

2. `mcp_discovery_timeout=1.5` —— "Keep it small so a slow/dead server adds little to
   first-response latency";并且明说 **正确性不依赖它**(错过窗口的 server 下一轮会被补上)。
   `hermes_cli/config_defaults.py:485 @ 863e313`

   ```python
    "mcp_discovery_timeout": 1.5,
   ```

3. `agent.clarify_timeout=3600` —— 反向告诫:调**大**会更久地占住 gateway 的 running-agent 守卫。
   `hermes_cli/config_defaults.py:174 @ 863e313`

   ```python
        "clarify_timeout": 3600,
   ```

4. `agent.gateway_notify_interval=180` —— 调小=反馈快但聊天噪音大,180 是折中,
   目标是"在用户以为 bot 死了并 /restart 之前"发出心跳。
   `hermes_cli/config_defaults.py:182 @ 863e313`

   ```python
        "gateway_notify_interval": 180,
   ```

**(e) 明确写了"不要调小/建议调大"的键:**
`agent.api_max_retries=3`(用 fallback provider 的人可降到 1 换快速切换)、
`compression.max_attempts=3`(tool-schema 很重的会话建议提到 6,"Validated >= 1, hard-capped at 10")、
`agent.build_wait_timeout=600`(MCP server 多且慢的部署要调大)。

`hermes_cli/config_defaults.py:589 @ 863e313`

```python
        "max_attempts": 3,            # compression retry rounds before a turn gives up
```

**(f) 三态字符串 "auto" 是这份配置里最常见的类型。**
`agent.tool_use_enforcement`、`agent.intent_ack_continuation`、`agent.coding_context`、
`agent.verify_on_stop`、`agent.image_input_mode`、`terminal.modal_mode`、`terminal.home_mode`、
`browser.engine`、`auxiliary.*.provider`、`display.copy_shortcut`、`display.pet.render_mode`、
`wake_word.surface`、`wake_word.capture`。其中两个还接受**布尔或字符串列表**
(`tool_use_enforcement` / `intent_ack_continuation` 可以是 `"auto"` / `True` / `False` /
`["gpt","codex"]`),即**一个键四种类型**。
`hermes_cli/config_defaults.py:78 @ 863e313`

```python
        "tool_use_enforcement": "auto",
```

`hermes_cli/config_defaults.py:88 @ 863e313`

```python
        "intent_ack_continuation": "auto",
```

**(g) 数值默认几乎全部附带"0/None = 关闭或无限"的哨兵约定**,而且**不统一**:
`0` 表示"无限/禁用"的有 `agent.gateway_timeout`、`agent.restart_drain_timeout`、
`checkpoints.max_total_size_mb`、`delegation.child_timeout_seconds`、`display.tool_preview_length`、
`cron.output_retention`("0 or negative")、`tool_loop_guardrails.loop_caps.*`;
`None`(YAML `null`)表示"无限/用上游默认"的有 `max_concurrent_sessions`、
`context_file_max_chars`、`database.wal_autocheckpoint`、`compression.threshold_tokens`、
`cron.max_parallel_jobs`、`kanban.max_in_progress_per_profile`、`wake_word.input_device`;
`max_live_sessions` 注释写 "0/null disables" —— **两者都接受**。

---

## 5. 逐簇精读

### 5.1 顶层与 `database`(第 8-30 行)

前 5 个键没有任何注释,是最古老的核心键:`model`(空串)、`providers`、`fallback_providers`、
`credential_pool_strategies`、`toolsets`。`hermes_cli/config_defaults.py:12 @ 863e313`

```python
    "toolsets": ["hermes-cli"],
```

注意 `model` 默认是空字符串而不是某个具体模型,`hermes_cli/main.py:969` 用它作 `_DEFAULT_MODEL`
判断"用户是否配过模型"。

`database.journal_mode` 默认 `wal`,注释给出反向场景:弱 fsync / 共享文件系统(macOS virtiofs、
NFS、SMB)上 WAL 不 crash-safe,应设 `DELETE`。`hermes_cli/config_defaults.py:17 @ 863e313`

```python
        "journal_mode": "wal",
```

**读取点在别的文件**,而且带自己的兜底:`hermes_state.py:614 @ 863e313`

```python
def resolve_journal_mode() -> str:
```

`hermes_state.py:630 @ 863e313`

```python
        raw = database.get("journal_mode", "wal")
```

非法值、非字符串、异常一律回落 `"wal"`,只接受 `wal`/`delete` 两个值。

**这里有一处"配置说了不算"**:即便配置是 `wal`,只要 SQLite 运行时被判定含 WAL-reset 缺陷
(issue #69784),就强制走 DELETE。`hermes_state.py:714 @ 863e313`

```python
    if is_sqlite_wal_reset_vulnerable():
```

`database.wal_autocheckpoint` / `journal_size_limit` 默认 `None` = 用 SQLite 自己的默认
(autocheckpoint 1000 页,无大小上限)。`hermes_cli/config_defaults.py:20 @ 863e313`

```python
        "wal_autocheckpoint": None,
```

### 5.2 会话上限(第 25-30 行)

`max_concurrent_sessions=None`(全局活跃会话硬上限,None/0 = 无限)与
`max_live_sessions=16`(内存中 TUI/desktop/dashboard 会话的**软** LRU 上限,
超出时驱逐"最久未活跃且无活客户端"的 DETACHED 会话,重新打开会从磁盘恢复)是两个不同层次的量。
`hermes_cli/config_defaults.py:30 @ 863e313`

```python
    "max_live_sessions": 16,
```

### 5.3 `agent`(第 31-249 行,29 个键)

这是全段信息密度最高的簇。分四类:

**(1) 超时家族——一共 9 个,语义各不相同,极易混淆:**

| 键 | 默认 | 语义 |
|---|---|---|
| `agent.gateway_timeout` | 1800 | **不活动**超时(不是墙钟)。只在完全空闲这么久才触发 |
| `agent.gateway_timeout_warning` | 900 | 升级为超时前的分级预警,每次运行只发一次,不打断 agent |
| `agent.gateway_notify_interval` | 180 | "还在干活"心跳 |
| `agent.session_stall_timeout` | 300 | 停滞看门狗,**仅通知**(建议 /new),作用域被注释显式收窄 |
| `agent.clarify_timeout` | 3600 | 等用户回答 clarify 工具的上限;CLI 不受此限(`input()` 同步阻塞) |
| `agent.build_wait_timeout` | 600 | 提交的 prompt 等待延迟 agent 构建(MCP 发现/模型元数据/skills 扫描)的上限 |
| `agent.restart_drain_timeout` | 0 | stop()/drain 开始后的强制打断预算,**默认立即打断** |
| `agent.restart_after_turn_timeout` | 21600 | 带内重启(/restart、SIGUSR1)先等在飞轮次自然结束的上限,6h |
| `agent.gateway_startup_restore_drain_timeout` | 30 | 启动恢复期间入站门闸的上限 |

`gateway_timeout` 的"不活动"语义是关键,注释写得很明确。`hermes_cli/config_defaults.py:37 @ 863e313`

```python
        "gateway_timeout": 1800,
```

`restart_after_turn_timeout` 与 `restart_drain_timeout` 是一对:先等轮次跑完(6h 上限),
再进 drain(立即打断)。注释点名 #77184:没有前者时,发起 /restart 的那一轮会被自己截肢。
`hermes_cli/config_defaults.py:54 @ 863e313`

```python
        "restart_after_turn_timeout": 21600,
```

`session_stall_timeout` 的注释是全文最"防御性"的一段——它花了 8 行说明这个看门狗**不**做什么
(不观察启动恢复、构建哨兵、轮次租约、去抖状态、跨进程工作;扫描节奏按 AIAgent 实例而非按持久会话)。
`hermes_cli/config_defaults.py:193 @ 863e313`

```python
        "session_stall_timeout": 300,
```

`gateway_auto_continue_freshness=3600` 是一个**新鲜度窗口**而非超时:gateway 崩溃/重启后,
下一条用户消息会被前置"[System note: 上一轮被打断,先处理未完成的工具结果]",
但如果最后一条持久化 transcript 已经是几小时前的,这个标记会"复活"一个无关的老任务,
所以用最后一行的年龄来卡。`hermes_cli/config_defaults.py:207 @ 863e313`

```python
        "gateway_auto_continue_freshness": 3600,
```

**(2) 提示词注入开关——5 个,全部默认开或 auto:**
`tool_use_enforcement`(预防式:告诉模型真去调工具而不是描述打算)与
`intent_ack_continuation`(纠正式:模型说了"我这就去看日志"却没发工具调用时,
拦截 turn-end、注入"现在就执行"、继续循环,每轮最多 2 次)是一对**同一失效模式的两面**,
默认都是 `"auto"`。

`task_completion_guidance` / `parallel_tool_call_guidance` / `environment_probe` 默认 True,
注释都标了 token 成本。`environment_probe` 在远程 terminal 后端(docker/modal/ssh)被跳过。
`hermes_cli/config_defaults.py:111 @ 863e313`

```python
        "environment_probe": True,
```

**(3) 编码姿态与验证闭环——`coding_context` / `coding_instructions` / `verify_on_stop` /
`verify_guidance` / `max_verify_nudges`:**

`coding_context` 有四态:`auto`(交互式表面 + 代码工作区时仅加提示词)、
`focus`(再加上把工具集收窄到精简编码集 + 把非编码 skill 类目降级为仅名字)、`on`、`off`。
`hermes_cli/config_defaults.py:133 @ 863e313`

```python
        "coding_context": "auto",
```

`verify_on_stop="auto"` 是**表面感知**的:交互式编码表面(CLI/TUI/desktop)与程序化调用方开,
对话式消息平台(Telegram/Discord)关——因为验证叙事到了人眼里就是聊天噪音;
纯文档/markdown/skill 编辑永不触发。`hermes_cli/config_defaults.py:158 @ 863e313`

```python
        "verify_on_stop": "auto",
```

`max_verify_nudges=3` 的存在理由写得很直白:"so a user/plugin hook can never trap the loop"。
`hermes_cli/config_defaults.py:148 @ 863e313`

```python
        "max_verify_nudges": 3,
```

**(4) 其他:**
`api_max_retries=3` 明确区分 **Hermes 层重试** 与 **OpenAI SDK 自带的 max_retries=2**;
`image_input_mode="auto"` 的 auto 条件是"模型报告 supports_vision **且** 用户没显式配
`auxiliary.vision.provider`";`local_stream_stale_timeout=900` 是本地 provider 的有限天花板,
替代了以前的"无限禁用",可被 `HERMES_LOCAL_STREAM_STALE_TIMEOUT` 覆盖;
`reasoning_overrides={}` 注释说"Edit directly in config.yaml (no CLI support due to dots in keys)"——
即模型名里的点会与点分路径冲突。
`hermes_cli/config_defaults.py:248 @ 863e313`

```python
        "reasoning_overrides": {},
```

`agent.service_tier=""` 是全簇唯一**完全没有注释**的键(它上方的注释块属于下一个键
`tool_use_enforcement`)。`hermes_cli/config_defaults.py:72 @ 863e313`

```python
        "service_tier": "",
```

`agent.max_turns=500` 同样没有注释。`hermes_cli/config_defaults.py:32 @ 863e313`

```python
        "max_turns": 500,
```

它有一条**遗留键归一化**:老配置写在根级的 `max_turns` 会被搬进 `agent.max_turns`。
`hermes_cli/config.py:2830 @ 863e313`

```python
def _normalize_max_turns_config(config: Dict[str, Any]) -> Dict[str, Any]:
```

### 5.4 `terminal`(第 251-362 行,29 个键)

后端选择 `backend="local"`、`modal_mode="auto"`、`cwd="."`。
`hermes_cli/config_defaults.py:252 @ 863e313`

```python
        "backend": "local",
```

容器资源默认 1 CPU / 5 GB 内存 / 50 GB 磁盘 / 跨会话持久化。
`hermes_cli/config_defaults.py:322 @ 863e313`

```python
        "container_cpu": 1,
```

`hermes_cli/config_defaults.py:323 @ 863e313`

```python
        "container_memory": 5120,       # MB (default 5GB)
```

四个镜像键指向**同一个镜像**(docker / singularity / modal / daytona):
`nikolaik/python-nodejs:python3.11-nodejs20`。`hermes_cli/config_defaults.py:307 @ 863e313`

```python
        "docker_image": "nikolaik/python-nodejs:python3.11-nodejs20",
```

`docker_shm_size="1g"` 是一条很典型的"踩过坑"默认:Docker 默认 64 MB 会**静默**弄坏
Chromium/Playwright 和 PyTorch DataLoader;tmpfs 惰性分配所以抬高上限不花钱。
`hermes_cli/config_defaults.py:345 @ 863e313`

```python
        "docker_shm_size": "1g",
```

`docker_network=True` 的注释措辞值得注意:标题写 "Opt-in egress lockdown",但**默认是 True 即联网**,
"opt-in" 指的是"设 false 才锁网"。`hermes_cli/config_defaults.py:339 @ 863e313`

```python
        "docker_network": True,
```

`docker_run_as_host_user=False` 默认关的理由很具体:官方镜像的 entrypoint 期待以 root 启动
(用 s6-setuidgid 降权到 `hermes` 用户);开启时容器会省略 SETUID/SETGID 能力。
`hermes_cli/config_defaults.py:356 @ 863e313`

```python
        "docker_run_as_host_user": False,
```

`shell_init_files=[]` + `auto_source_bashrc=True` 是一对:空列表时自动 source
`~/.profile` → `~/.bash_profile` → `~/.bashrc`,顺序有理由(nvm/n/asdf 安装器通常把 PATH 导出
写进前两者且没有交互性守卫;Debian/Ubuntu 默认 `~/.bashrc` 在非交互 source 时会短路)。
`hermes_cli/config_defaults.py:306 @ 863e313`

```python
        "auto_source_bashrc": True,
```

`daemon_term_grace_seconds=2.0` 是 SIGTERM→SIGKILL 的升级窗口,"Floored internally at 0"。
`hermes_cli/config_defaults.py:269 @ 863e313`

```python
        "daemon_term_grace_seconds": 2.0,
```

### 5.5 `web` / `browser`(第 364-411 行,25 个键)

`web` 只有 4 个键,设计是"共享 fallback + 每能力覆盖":`backend` 空串是两者共用的兜底,
`search_backend` / `extract_backend` 是 per-capability 覆盖。
`extract_char_limit=15000` 是每页字符预算,超出截断并把全文存进 `cache/web`。
`hermes_cli/config_defaults.py:368 @ 863e313`

```python
        "extract_char_limit": 15000,  # per-page char budget for web_extract; larger pages truncate + store full text in cache/web
```

`browser` 侧:`inactivity_timeout=120`、`command_timeout=30`、`record_sessions=False`、`headed=False`
(注释:headed 还会跳过每轮清理,让窗口跨轮存活,但空闲回收器仍然生效)。

**两个 evaluate 安全键的关系是反直觉的**:`restrict_evaluate=False` 是 opt-in 的**拒绝名单**
(默认不启用),而 `allow_unsafe_evaluate=False` 是"遗留总开关",为 true 时**完全绕过**该拒绝名单。
即默认状态下 `browser_console(expression=...)` 是**不受限**的。
`hermes_cli/config_defaults.py:386 @ 863e313`

```python
        "allow_unsafe_evaluate": False,  # Legacy override: when true, browser_console(expression=...) bypasses the restrict_evaluate denylist entirely
```

`hermes_cli/config_defaults.py:387 @ 863e313`

```python
        "restrict_evaluate": False,  # Opt-in denylist blocking sensitive JS primitives (cookies/storage/clipboard/network/form values) in browser_console(expression=...)
```

CDP(Chrome DevTools Protocol,浏览器远程调试协议)监督器的对话框策略默认
`must_respond` + 300 秒安全自动关闭。`hermes_cli/config_defaults.py:392 @ 863e313`

```python
        "dialog_policy": "must_respond",  # must_respond | auto_dismiss | auto_accept
```

`engine="auto"` 可被 `AGENT_BROWSER_ENGINE` 覆盖,读取点:`tools/browser_tool.py:942 @ 863e313`

```python
        env_val = os.environ.get("AGENT_BROWSER_ENGINE", "").strip().lower()
```

`browser.camofox.*` 5 个键管理外部托管的 Camofox 浏览器身份;
`rewrite_loopback_urls=False` + `loopback_host_alias="host.docker.internal"` 解决
"容器内 Camofox 打开 localhost 页面"的经典问题。

### 5.6 `checkpoints`(第 413-457 行)

**注释里写了 v2 的默认值变更史**,这是理解设计取舍最直接的材料:
`enabled: True → False`(改成 opt-in,因为大多数用户从不用 /rollback)、
`max_snapshots: 50 → 20`(v2 起真的通过 ref 重写强制执行)、
`auto_prune: False → True`。`hermes_cli/config_defaults.py:424 @ 863e313`

```python
        "enabled": False,
```

`hermes_cli/config_defaults.py:428 @ 863e313`

```python
        "max_snapshots": 20,
```

自动清扫的边界写得很清楚:**永远不删"孤儿"条目**(工作目录已不在磁盘上),
因为缺失的工作目录是**歧义**的——可能是项目被删,也可能是外部卷/网络共享/VPN 还没挂载;
这个清扫无人值守,所以不能猜。孤儿清理只在人看着输出的 `hermes checkpoints prune` 里做。
`hermes_cli/config_defaults.py:454 @ 863e313`

```python
        "auto_prune": True,
```

### 5.7 上下文与工具输出的硬上限(第 459-559 行)

`context_file_max_chars=None` —— **null 是"动态"而不是"无限"**:上限随模型上下文窗口缩放
(下限 20K,上限 500K);给正整数才是固定上限。
`hermes_cli/config_defaults.py:465 @ 863e313`

```python
    "context_file_max_chars": None,
```

`file_read_max_chars=100_000` 附了换算:"100K chars ≈ 25–35K tokens across typical tokenisers"。
`hermes_cli/config_defaults.py:470 @ 863e313`

```python
    "file_read_max_chars": 100_000,
```

MCP 发现有两个超时,交互式 1.5s、单次查询(`hermes -q/-z`)15.0s。理由是单次查询模式**只有一轮**,
轮间的延迟绑定刷新永远不会跑,错过窗口的 server 对 LLM 就整场不可见。
`hermes_cli/config_defaults.py:495 @ 863e313`

```python
    "mcp_single_query_discovery_timeout": 15.0,
```

`mcp.auto_reload_on_config_change=True` 的注释解释了关掉它的动机:每次自动重载都重建工具面
并**作废 provider 提示缓存**(下一条消息要重发完整输入前缀)。
`hermes_cli/config_defaults.py:508 @ 863e313`

```python
        "auto_reload_on_config_change": True,
```

`tool_output` 三个上限(50_000 字符 / 2000 行 / 每行 2000 字符)注明是从
`anomalyco/opencode PR #23770` 移植的。`hermes_cli/config_defaults.py:526 @ 863e313`

```python
        "max_bytes": 50_000,
```

`tool_loop_guardrails.loop_caps` 是**每轮**的失控上限(轮首归零),与 warn/hard-stop 阈值无关、
永远生效:每轮最多 50 次 web_search、50 个子 agent。
`hermes_cli/config_defaults.py:556 @ 863e313`

```python
            "max_web_searches": 50,   # max web_search calls per turn (0 = unlimited)
```

### 5.8 `compression`(第 561-754 行,29 个键)

**触发条件有三条独立的线**:
比例 `threshold=0.50`、绝对 `threshold_tokens=None`(设了就取两者较小)、
时间 `idle_compact_after_seconds=0`(opt-in)。
`hermes_cli/config_defaults.py:572 @ 863e313`

```python
        "threshold": 0.50,            # compress when context usage exceeds this ratio.
```

比例上有一条**只升不降的地板**:窗口 < 512K 的模型被抬到 0.75。
配置注释说的地板在代码里是两个常量。`agent/context_compressor.py:664 @ 863e313`

```python
_SMALL_CTX_WINDOW_LIMIT = 512_000
_SMALL_CTX_THRESHOLD_PERCENT = 0.75
```

`model_thresholds={}` 是子串匹配(最长匹配胜出),地板仍然叠加在覆盖之上。
`hermes_cli/config_defaults.py:728 @ 863e313`

```python
        "model_thresholds": {},       # Per-model threshold overrides. Keys are
```

**保留策略**:`target_ratio=0.20`(压缩后保留 threshold 的 20% 作近尾)、`protect_last_n=20`、
`protect_first_n=3`(除系统提示外的头部消息)、`min_tail_user_messages=1`
(保证有多少条**真实**用户消息活在未压缩尾部)。

**主动裁剪(deterministic prune,不用 LLM)** 是一组三键,注释里给出了完整因果:
大窗口模型上 `threshold`(≈窗口 50%)很少触发,老工具输出于是一直骑在历史里、每轮重发;
`proactive_prune_tokens` 给一个低触发点(例如 48000)提早回收;
但**每次提交的裁剪都会重写已发送历史、打断 provider 提示缓存前缀**,
所以用 `proactive_prune_min_reclaim_tokens=4096` 这个"最小收益门"把断裂变成偶发而非每轮。
`hermes_cli/config_defaults.py:594 @ 863e313`

```python
        "proactive_prune_tokens": 0,  # opt-in trigger (tokens) for the deterministic,
```

`hermes_cli/config_defaults.py:611 @ 863e313`

```python
        "proactive_prune_min_reclaim_tokens": 4096,  # a proactive prune only commits
```

`micro_compact=False` 是同一权衡的极端:它**每轮**都打断缓存前缀,注释直说
"Enable only when you have measured that the amortized stall is worth more to you
than the cached-prefix discount"。`hermes_cli/config_defaults.py:617 @ 863e313`

```python
        "micro_compact": False,       # opt-in: after each completed turn, fold the
```

**超时是"进度感知"的**,这是个很值得抄的设计:`hygiene_timeout_seconds=30` /
`context_timeout_seconds=120` 是**不活动**预算——摘要调用是流式的,只要还在吐 token 就一直延长等待,
只有静默/挂死才被砍;再用 `hygiene_total_ceiling_seconds=600` /
`context_total_ceiling_seconds=600` 作绝对天花板,防止"涓流"退化。
并且明确保证:天花板只约束**摘要/流阶段**,已经开始的 SessionDB 提交永不被半途放弃
(超出就 WARNING→ERROR 记录并通过警告通道告知用户,宿主继续分片等待)。

`in_place=True`(2107b86024 起)是一个 bug 簇的总解:压缩就地重写消息列表并重建系统提示,
**不轮换 session id**,消灭了 #33618(/goal 丢失)、#14238(丢响应)、#33907(孤儿)、
#45117(搜索缺口)、#42228(cwd 为 null)。旧轮次被软归档在同一 id 下
(`active=0, compacted=1`),仍可被 `session_search` 搜到。
`hermes_cli/config_defaults.py:712 @ 863e313`

```python
        "in_place": True,             # When True, compaction rewrites the message
```

`codex_gpt55_autoraise=True` 是**键名与语义已经脱节**的历史遗留(注释首句就是
"Historical key name kept for compatibility"):它现在管的是 gpt-5.4/5.5/5.6 在
ChatGPT Codex OAuth 路由上把压缩触发点抬到 85%,因为 Codex 把这些家族硬限在 272K 窗口,
50% 会在 ~136K 就压缩、浪费一半可用上下文。
`hermes_cli/config_defaults.py:688 @ 863e313`

```python
        "codex_gpt55_autoraise": True,  # Historical key name kept for compatibility.
```

`abort_on_summary_failure=False`:aux 模型出错时默认丢中段并塞占位("summary unavailable"),
设 True 则整体中止、会话"冻结"在当前大小直到用户 /compress(绕过失败冷却)或 /new。

### 5.9 `prompt_caching` / `openrouter` / `bedrock`(第 756-803 行)

`prompt_caching.cache_ttl="5m"`:只认 `"5m"` / `"1h"`,**其它非假值被静默忽略**,
假值(false/null/"off"/"disabled"/"no"/"none")关闭提示缓存。
`hermes_cli/config_defaults.py:761 @ 863e313`

```python
        "cache_ttl": "5m",
```

`openrouter.response_cache=True`(相同请求命中缓存零计费)、`response_cache_ttl=300`(1-86400)、
`min_coding_score=0.65`(**仅当** model.model 是 `openrouter/pareto-code` 时生效;空串= 让
OpenRouter 自己挑最强 coder)。`hermes_cli/config_defaults.py:780 @ 863e313`

```python
        "response_cache": True,
```

`bedrock.region=""` 的 fallback 链写在注释里:空 → `AWS_REGION` 环境变量 → `us-east-1`。
`hermes_cli/config_defaults.py:788 @ 863e313`

```python
        "region": "",  # AWS region for Bedrock API calls (empty = AWS_REGION env var → us-east-1)
```

`bedrock.discovery.refresh_interval=3600`、`bedrock.guardrail.*` 4 键(默认全空 = 不启用护栏)。

### 5.10 `auxiliary`(第 805-1070 行,149 行表项 —— 全段最大的簇)

**结构是"4 个全局键 + 17 个任务块"**,每个任务块形状一致:
`provider` / `model` / `base_url` / `api_key` / `timeout` / `extra_body` / `reasoning_effort`
(`moa_reference` / `moa_aggregator` 两块**故意不含** `reasoning_effort`,
因为 MoA 的推理深度按槽位配在 preset 里;`memory_query_rewrite` 也没有该字段)。

17 个任务:`vision`、`web_extract`、`compression`、`skills_hub`、`approval`、`mcp`、
`title_generation`(多一个 `enabled` 和 `language`)、`memory_query_rewrite`、`tts_audio_tags`、
`triage_specifier`、`kanban_decomposer`、`profile_describer`、`goal_judge`、`curator`、
`monitor`、`background_review`、`moa_reference`、`moa_aggregator`。

**唯一真正因任务而异的默认值是 `timeout`**,它把每个副任务的成本画像写了出来:

| 任务 | timeout | 注释给的理由 |
|---|---|---|
| `memory_query_rewrite` | 8 | 最短,查询改写 |
| `skills_hub` / `approval` / `mcp` / `title_generation` / `tts_audio_tags` | 30 | 短结构化调用 |
| `profile_describer` / `goal_judge` / `monitor` | 60 | 短但略重 |
| `vision` / `compression` / `triage_specifier` / `background_review` | 120 | vision 载荷大;压缩要读大上下文 |
| `kanban_decomposer` | 180 | 返回 JSON 任务图,token 多 |
| `web_extract` | 360 | 每次尝试的摘要超时,本地模型要更久 |
| `curator` | 600 | 在数百候选 skill 上建"伞",推理模型要几分钟 |
| `moa_reference` / `moa_aggregator` | 900 | 最长 |

`hermes_cli/config_defaults.py:1010 @ 863e313`

```python
            "timeout": 600,
```

`hermes_cli/config_defaults.py:1054 @ 863e313`

```python
            "timeout": 900,
```

**4 个全局键:**
`transient_retries=2`(→ 共 3 次尝试,clamp 到 [0,6];对 MoA 参考顾问这种"钉死 provider"的调用最要紧,
因为 provider fallback 对它不构成恢复);
`free_only=False`(true 时 OpenRouter fallback 只走 `:free` SKU,后台副任务永不进付费通道);
`openrouter_model=""`(默认 fallback 是 `google/gemini-3.6-flash`,**付费**;
用非 `:free` 模型时会打一次 WARNING);
`stream_only_base_urls=[]`(某些端点拒绝非流式请求,如腾讯 Copilot 返回 HTTP 400;
`copilot.tencent.com` 永远被当作 stream-only)。

`hermes_cli/config_defaults.py:838 @ 863e313`

```python
        "transient_retries": 2,
```

`hermes_cli/config_defaults.py:846 @ 863e313`

```python
        "free_only": False,
```

**设计原则(注释显式声明)**:每个 aux 任务彼此独立,主 agent 的 `provider_routing` 和
`openrouter.min_coding_score` **不会**传播到 aux 调用;要设 provider 专有旋钮就用该任务的 `extra_body`。

`auxiliary.background_review` 的注释解释了一个很聪明的实现:默认 `auto` = 跑在主聊天模型上,
**复用已经热的提示缓存**(便宜的 cache read);一旦路由到别的模型,缓存无论如何用不上,
于是 fork 自动改为重放**紧凑摘要**而非完整 transcript。

注释还记录了一次**删除**:`auxiliary.session_search.*` 已在 PR #27590 移除
(单形状工具直接返回 DB 内容),用户配置里的残留值"harmless leftovers and ignored"。
`hermes_cli/config_defaults.py:888 @ 863e313`

```python
        # Note: session_search no longer uses an auxiliary LLM (PR #27590 —
```

### 5.11 `display`(第 1072-1306 行,68 个键)

最大的"人机界面"簇。几个值得记的:

`interface="cli"` 决定裸 `hermes` 启动经典 REPL 还是 Ink TUI;显式 flag 永远赢过配置。
`hermes_cli/config_defaults.py:1099 @ 863e313`

```python
        "interface": "cli",
```

`show_reasoning=True` 默认开,理由是思考模型的推理阶段可能几十秒,关掉的话用户全程盯着 spinner。
`hermes_cli/config_defaults.py:1115 @ 863e313`

```python
        "show_reasoning": True,
```

`streaming=False`(全局)但 `display.platforms` 给了**按平台的补空默认**:
Telegram 有原生动画草稿流(sendMessageDraft)所以开,Discord/Slack 只有编辑式流(反复 editMessage)
会闪烁所以关。注释明说这些是 gap-filler,用户显式设置会赢(靠 §2.1 的深合并)。
`hermes_cli/config_defaults.py:1267 @ 863e313`

```python
        "platforms": {
            "telegram": {"streaming": True},
```

`cli_refresh_interval=1.0` 记录了一对相反的 issue:不刷新的话 prompt_toolkit 轮次后停止重绘、
状态栏变陈旧甚至消失(#45592);但在某些终端非全屏模式下它又会和自动滚动打架(#48309),
所以给了 0 = 关闭。`hermes_cli/config_defaults.py:1188 @ 863e313`

```python
        "cli_refresh_interval": 1.0,
```

一组"过度声称/静默失败"的补丁默认全开:
`file_mutation_verifier=True`(一轮里 write_file/patch 失败且没被后续成功写覆盖时,
在最终回复后追加一行告示,专治"并行 patch 一半失败、模型宣称成功");
`turn_completion_explainer=True`(轮次异常结束且无可用回复时给一行解释,替代裸 `(empty)`);
`friendly_tool_labels=True`;`turn_summary=True`;`spinner_token_flow=True`。
`hermes_cli/config_defaults.py:1147 @ 863e313`

```python
        "file_mutation_verifier": True,
```

`final_response_markdown="strip"`(render | strip | raw)、
`memory_notifications="on"`(off | on | verbose)、
`busy_input_mode="interrupt"`(interrupt | queue | steer)、
`tool_progress_grouping="accumulate"`、`reasoning_style="code"`(Discord 默认 `subtext`)、
`language="en"`(支持 en/zh/ja/de/es/fr/tr/uk,未知值回落 en,且**只影响静态用户可见文案**,
不影响 agent 回复/日志/工具输出/斜杠命令描述)。

`display.tool_progress_overrides` 是一个**已废弃且不再 seed** 的键,注释保留说明它仍被运行时兼容读取,
并由 v15→16 迁移折叠进 `display.platforms`——这是"文件里没有该键但代码仍认"的显式记录。
`hermes_cli/config_defaults.py:1201 @ 863e313`

```python
        # NOTE: display.tool_progress_overrides is deprecated and no longer
```

`display.pet.*` 5 键是一个纯装饰的动画吉祥物(Petdex),注释特意声明"no effect on prompt caching"。

### 5.12 `dashboard`(第 1308-1413 行)

`show_token_analytics=False` 的注释是全文最长的"为什么默认隐藏"论证:本地统计**只**计入
带可用 `response.usage` 的成功主 agent 响应,**静默排除**全部辅助调用(压缩、标题、视觉、
会话搜索、web extract、smart approval、MCP 路由、插件 LLM)、provider 侧重试、fallback 尝试,
以及缓存写入;在辅助流量重的模型上本地合计可能比账单低 10x-100x——
"看起来精确到可以拿去和 provider 对账"才是最糟的。
`hermes_cli/config_defaults.py:1330 @ 863e313`

```python
        "show_token_analytics": False,
```

三组认证配置都遵循同一模式:**配置键给行为旋钮,密钥走环境变量**。
`dashboard.oauth.{client_id,portal_url}` 各有 env 覆盖且 env 赢
(`HERMES_DASHBOARD_OAUTH_CLIENT_ID` / `HERMES_DASHBOARD_PORTAL_URL`),
这条覆盖路径正是 Fly.io 平台密钥注入用的。
`dashboard.basic_auth.*` 5 键(username 空 = 插件 no-op;`password_hash` 优先于明文 `password`;
`secret` 空 = 每进程随机密钥,会话不跨重启/多 worker)。
`dashboard.drain_auth` **只有**行为旋钮 `scope="drain"` 与 `min_secret_chars=43`(≈256 位),
密钥本身由 `HERMES_DASHBOARD_DRAIN_SECRET` 在部署时注入,弱密钥在注册时被拒(fail-closed)。
`hermes_cli/config_defaults.py:1390 @ 863e313`

```python
            "min_secret_chars": 43,
```

`dashboard.public_url=""` 的校验规则写在注释里:拒绝无 `http(s)://` scheme 或无 host 的值,
拒绝含引号/尖括号/空白/控制字符的字符串;**畸形值静默回落**到请求重建而不是打断登录流程。
设置后 `X-Forwarded-Prefix` 在 OAuth 路径上被**忽略**(避免双前缀)。
`hermes_cli/config_defaults.py:1412 @ 863e313`

```python
        "public_url": "",
```

### 5.13 `tts` / `stt` / `voice` / `wake_word`(第 1420-1609 行,104 个键)

`tts.provider="edge"`——默认选**免费**后端。11 个 provider 子块各自钉死了具体 voice/model id。
`hermes_cli/config_defaults.py:1428 @ 863e313`

```python
        "provider": "edge",
```

`tts.piper` 里有 6 个**被注释掉**的键(`voices_dir` / `use_cuda` / `length_scale` /
`noise_scale` / `noise_w_scale` / `volume` / `normalize_audio`),`tts.deepinfra.base_url` 同样被注释掉——
它们是"文档化但不 seed"的键,`ast` 枚举不到,`get_missing_config_fields` 也不会提示。

`stt.provider="local"`(免费 faster-whisper)。`stt.language="en"` 是一个**有意与直觉相反**的默认:
注释说 Whisper 自动检测在短/带口音片段上经常认错,表现为"STT 转写成了错的语言",
所以全局钉死 en,想要自动检测请显式设空串。`hermes_cli/config_defaults.py:1516 @ 863e313`

```python
        "language": "en",
```

`stt.local` 的四个反幻觉键是一组**联合条件**:`vad=True`(Silero VAD,静音永远到不了 whisper)、
`vad_min_silence_ms=500`,以及 `no_speech_prob_threshold=0.6` **与** `logprob_threshold=-1.0`
必须**同时**命中才丢弃片段。`hermes_cli/config_defaults.py:1525 @ 863e313`

```python
            "no_speech_prob_threshold": 0.6,  # drop a segment only if no_speech_prob is ABOVE this...
```

`voice.barge_in=True` 三键的注释透露了实现细节:抢话阈值 = **播放前**标定的安静房间底噪 × 3.0
(绝不拿扬声器串音去标定),`barge_in_grace_seconds=0.5` 只抑制播放起始的瞬态,
麦克风整轮都是活的。`hermes_cli/config_defaults.py:1564 @ 863e313`

```python
        "barge_in": True,             # Interrupt the agent / stop TTS when the user starts talking
```

`wake_word.enabled=False`,provider 默认 `openwakeword`;`sensitivity=0.6` 被刻意做成**跨引擎一致**;
`confirmation_frames=3` 仅 openWakeWord 有效(要求连续 3 帧过阈值,1 = 旧的单帧行为);
`openwakeword.inference_framework=""` 的 auto 逻辑有具体依据:onnx 后端在 macOS ARM64 上评分近零
(dscripka/openWakeWord#336),所以 auto 在那里选 tflite。
`hermes_cli/config_defaults.py:1583 @ 863e313`

```python
        "sensitivity": 0.6,           # 0.0-1.0 detection threshold, consistent across engines (higher = stricter, fewer false triggers)
```

### 5.14 `context` / `memory` / `delegation` / `goals` / `moa`(第 1617-1786 行)

`context.engine="compressor"`(可换成插件名如 `lcm`)。
`context.memory_trim.*` 4 键管 glibc 分配器页归还,`cooldown_seconds=60.0`,
`info_log_min_delta_mb=0.0`(0 = 每次成功的配置化 trim 都记)。

`memory.memory_char_limit=2200` / `user_char_limit=1375` 都附了 token 换算
(2.75 chars/token → ~800 / ~500 tokens),这是"预算按字符卡、按 token 说明"的做法。
`hermes_cli/config_defaults.py:1656 @ 863e313`

```python
        "memory_char_limit": 2200,   # ~800 tokens at 2.75 chars/token
```

`memory.write_approval=False` 的注释区分了两条写入路径的不同处理:开启后前台写入**内联提示**
(条目小到能在聊天气泡里审),后台自省 fork 的写入**改为暂存**(守护线程不能阻塞在提示上)。
`skills.write_approval=False` 是同一模式的另一半,但 SKILL.md 太大不能内联,**总是暂存**。
`hermes_cli/config_defaults.py:1655 @ 863e313`

```python
        "write_approval": False,
```

`delegation` 15 键。`max_iterations=50` 是**每个子 agent 独立**的预算,与父的预算无关;
`max_concurrent_children=3` 是统一并发上限(每批并行子 + 后台委派单元),超出的异步派发**回落为同步执行**;
`max_summary_chars=24000` 是叠在动态预算之上的硬上限——真正的机制是按父的剩余上下文余量分摊,
超出部分溢写到 `~/.hermes/cache/delegation/` 并在上下文里留 head+tail 窗口 + 精确 read_file offset。
`hermes_cli/config_defaults.py:1700 @ 863e313`

```python
        "max_summary_chars": 24000,
```

`delegation.api_mode=""` 的自动探测规则写在注释里:从 URL 猜(如 `/anthropic` 后缀 → `anthropic_messages`),
非标准端点要显式写。`hermes_cli/config_defaults.py:1674 @ 863e313`

```python
        "api_mode": "",    # wire protocol for delegation.base_url: "chat_completions",
```

`goals.max_turns=20` 是 Ralph 式循环的护栏。注释里有一条重要的失败语义:
**判官失败 fail OPEN(继续)**,所以真正的兜底是轮次预算。
`hermes_cli/config_defaults.py:1748 @ 863e313`

```python
        "max_turns": 20,
```

`moa` 的默认 preset 钉了 3 个具体模型(2 个 reference + 1 个 aggregator),`max_tokens=4096`。
`hermes_cli/config_defaults.py:1778 @ 863e313`

```python
                    {"provider": "openai-codex", "model": "gpt-5.5"},
```

`moa.privacy_filter=""` 三态(off / `display` / `full`):顾问输出可能把 PII 和凭据形状
回显进 reference 块、trace 和 aggregator 提示;`display` 只脱敏用户可见面,`full` 连
aggregator 提示也脱敏(#59959)。`hermes_cli/config_defaults.py:1774 @ 863e313`

```python
        "privacy_filter": "",
```

### 5.15 `skills` / `curator`(第 1788-1880 行)

`skills.template_vars=True`(在 SKILL.md 里替换 `${HERMES_SKILL_DIR}` / `${HERMES_SESSION_ID}`)。
`skills.guard_agent_created=False` 的关闭理由很坦率:agent 本来就能用 `terminal()` 无门槛跑同样的代码,
所以扫描"增加摩擦而没有实质安全"(会因为散文里提到危险关键词就拦下 skill);
但**外部 hub 安装永远扫描**。`hermes_cli/config_defaults.py:1817 @ 863e313`

```python
        "guard_agent_created": False,
```

`curator.interval_hours` 是全表唯一一个**表达式而非字面量**的默认值(`24 * 7` = 168)。
`hermes_cli/config_defaults.py:1845 @ 863e313`

```python
        "interval_hours": 24 * 7,
```

`curator.prune_builtins=True` 附了一条防"首轮大清洗"的机制:内建 skill 的不活跃时钟
**从 curator 第一次看到它时才起算**,所以只有真正 90 天不用才归档。
`hermes_cli/config_defaults.py:1871 @ 863e313`

```python
        "prune_builtins": True,
```

`curator.backup.{enabled=True, keep=5}`:每次真实 curator pass 前把 `~/.hermes/skills/` 打包快照。

### 5.16 平台簇(第 1891-2028 行)

`slack` / `discord` / `mattermost` / `matrix` 共享同一套骨架:
`require_mention=True`(默认必须 @)、`free_response_channels=""`、`allowed_channels=""`(白名单)、
`channel_prompts={}`。全部是**逗号分隔字符串**而不是 YAML 列表,这是个一致但不常见的选择。
`hermes_cli/config_defaults.py:1893 @ 863e313`

```python
        "require_mention": True,       # Require @mention to respond in channels
```

`discord` 37 项最多。几个有意思的:
`bots_require_inline_mention=False`(多 bot 房间防"两个 bot 互相回复到天荒地老");
`history_backfill=True` + `history_backfill_limit=50`(补回被 require_mention 挡掉的上下文);
`missed_message_backfill` 5 键默认关(重连后重放,6 小时窗口、扫 100 条、最多派发 10 条);
4 个 websocket 健康键(15s 间隔 / 2 次失败阈值 / 60s heartbeat ack 最大年龄 / 30s 最大延迟),
注释强调这些**只看 WebSocket 自身状态,绝不拿 Discord REST 当作"Gateway 事件仍在到达"的证据**;
`dm_role_auth_guild=""`(空 = 安全默认,DM 角色鉴权关闭);
`max_attachment_bytes=33554432`(32 MiB,整份文件在写入时驻留内存);
`allow_any_attachment=False` 已是 **DEPRECATED / no-op**,保留只为不让老配置报错。
`hermes_cli/config_defaults.py:1954 @ 863e313`

```python
        "allow_any_attachment": False,
```

`hermes_cli/config_defaults.py:1959 @ 863e313`

```python
        "max_attachment_bytes": 33554432,
```

`discord.voice_fx` 是一个 7 键的软件混音器(discord.py 不带混音器,自实现在
`plugins/platforms/discord/voice_mixer.py`),默认关;开启后"思考"环境音、口头确认、TTS 可以**重叠**
(说话时把环境音压到 `duck_gain=0.06`)而不是停-换。

`telegram.extra.rich_messages=False` / `rich_drafts=False` 都是 Bot API 10.1 新能力**默认不开**,
理由分别是"富消息在 Telegram 客户端里难以复制成纯文本"和"Telegram Desktop/macOS 会把富草稿帧
叠画到聊天重绘为止"。`hermes_cli/config_defaults.py:2010 @ 863e313`

```python
            "rich_messages": False,     # Bot API 10.1 rich messages (tables/task lists/details/math) render natively; set True to opt in. Default stays legacy MarkdownV2 because rich messages can be hard to copy as plain text in Telegram clients.
```

`whatsapp` 是**空 dict**,只有 4 行注释描述一个未 seed 的 reply-prefix 键(见第 7 节 ▲1)。
`hermes_cli/config_defaults.py:1997 @ 863e313`

```python
    "whatsapp": {
```

### 5.17 `approvals` / `security`(第 2030-2159 行)

`approvals.mode="smart"`(manual / smart / off),`timeout=300`——默认从 60 提到 300 的理由写死在注释里:
消息平台上审批是推送通知,用户走到手机前 60 秒就过期了。**超时 fail closed(拒绝)**。
`hermes_cli/config_defaults.py:2045 @ 863e313`

```python
        "mode": "smart",
```

`hermes_cli/config_defaults.py:2046 @ 863e313`

```python
        "timeout": 300,
```

`cron_mode="deny"`:cron 作业撞到危险命令默认**阻断**并让 agent 另想办法。

`approvals.deny=[]` 是**唯一一条排在 `--yolo` 前面**的规则:fnmatch glob 匹配终端命令,
命中就无条件阻断,**先于** `--yolo` / `/yolo` / `mode=off` 的绕过。
`hermes_cli/config_defaults.py:2071 @ 863e313`

```python
        "deny": [],
```

`denial_breaker_threshold=3` 是连续拒绝熔断器(灵感来自 ChatGPT Work),
`smart_policy=""` 是可追加进守卫 SYSTEM 提示的运营策略文本。

`mcp_reload_confirm=True` 与 `destructive_slash_confirm=True` 共享一个有趣的机制:
用户点 "Always Approve" 会**把这个键本身翻成 false**——配置项即持久化的用户决定。
`hermes_cli/config_defaults.py:2079 @ 863e313`

```python
        "mcp_reload_confirm": True,
```

`security` 13 键。`tirith_enabled=True` + `tirith_timeout=5` + `tirith_fail_open=True`:
预执行安全扫描默认开,但**失败放行**——可用性优先于拦截。
`hermes_cli/config_defaults.py:2138 @ 863e313`

```python
        "tirith_fail_open": True,
```

`redact_secrets=True` 默认开(注意 §5.8 提到压缩摘要边界会 `force=True` **覆盖**这个 opt-out)。
`allow_lazy_installs=True`:第一次启用需要额外包的后端时允许从 PyPI 惰性安装;
注释点名了该关掉的场景(受限网络、审计环境、气隙系统)。
`hermes_cli/config_defaults.py:2158 @ 863e313`

```python
        "allow_lazy_installs": True,
```

`acked_advisories=[]` 是"已知悉的供应链安全公告 ID"列表,加进来就不再弹启动横幅。

### 5.18 `cron`(第 2161-2199 行,本段末尾)

`model_drift_guard=True`:未钉住的作业若当前全局模型/provider 与创建时快照不符就**失败关闭**,
防无人值守作业悄悄继承一个付费默认。`hermes_cli/config_defaults.py:2166 @ 863e313`

```python
        "model_drift_guard": True,
```

注释把 cron 的两个"provider"拆成两个轴,这是很容易搞混的地方:
**轴 A** `cron.model` / `cron.model_provider` = 推理模型(解析顺序:每作业用户钉住 > `cron.model` >
全局 `model.default`);**轴 B** `cron.provider` = **调度器** provider(决定"何时"触发),
空串 = 内建 60 秒进程内 ticker,未知/不可用的 provider 回落内建,"so cron never loses its trigger"。
`hermes_cli/config_defaults.py:2184 @ 863e313`

```python
        "provider": "",
```

`cron.chronos.*`(portal_url / callback_url / expected_audience / nas_jwks_url)全部**非机密**,
注释明说 agent **不持有**任何外部调度器凭据;`nas_jwks_url` 为空时 fire 端点**拒绝所有 token**
(不做无签名解码)——又一个 fail-closed。
`hermes_cli/config_defaults.py:2193 @ 863e313`

```python
            "portal_url": "https://portal.nousresearch.com",
```

---

## 6. 本段涉及的环境变量(注释提到 + 我验证过读取点)

| 环境变量 | 关联配置键 | 读取点(已验证) |
|---|---|---|
| `HERMES_ENVIRONMENT_HINT` | `agent.environment_hint`(env 赢) | `agent/prompt_builder.py:1266` |
| `HERMES_LOCAL_STREAM_STALE_TIMEOUT` | `agent.local_stream_stale_timeout` | `agent/chat_completion_helpers.py:4088` |
| `TERMINAL_LOCAL_PERSISTENT` | (local 后端专用,与 `terminal.persistent_shell` **不是**同一个) | `tools/terminal_tool.py:1561` |
| `TERMINAL_PERSISTENT_SHELL` | `terminal.persistent_shell` 的桥目标 | `hermes_cli/config.py:3213` |
| `AGENT_BROWSER_ENGINE` | `browser.engine` | `tools/browser_tool.py:942` |
| `HERMES_ALLOW_PRIVATE_URLS` | `security.allow_private_urls` / `browser.allow_private_urls` 之上 | `tools/url_safety.py:252` |
| `HERMES_CRON_MAX_PARALLEL` | `cron.max_parallel_jobs`(在我段外,2232 行) | `cron/scheduler.py:4230` |
| `HERMES_CRON_SESSION_DB_TIMEOUT` | `cron.session_db_timeout_seconds`(段外) | `cron/scheduler.py:2933` |
| `DISCORD_MAX_ATTACHMENT_BYTES` | `discord.max_attachment_bytes` | `plugins/platforms/discord/adapter.py:6166` |
| `DISCORD_APPROVAL_MENTIONS` | `discord.approval_mentions` | `plugins/platforms/discord/adapter.py:7035` |
| `DISCORD_ALLOW_ANY_ATTACHMENT` | `discord.allow_any_attachment`(已 no-op) | `plugins/platforms/discord/adapter.py:6155` |
| `SLACK_IGNORE_OTHER_USER_MENTIONS` | `slack.ignore_other_user_mentions` | `plugins/platforms/slack/adapter.py:8285` |
| `HERMES_ACCEPT_HOOKS` | `hooks_auto_accept` | `cli.py:1019` |
| `HERMES_TUI_NO_CONFIRM` | `approvals.destructive_slash_confirm`(TUI 侧) | `ui-tui/src/config/env.ts:52`(TS,非 Python) |
| `HERMES_TUI_RESUME` | `display.tui_auto_resume_recent`("always wins") | `hermes_cli/main.py:2396` |
| `HERMES_DASHBOARD_OAUTH_CLIENT_ID` / `HERMES_DASHBOARD_PORTAL_URL` | `dashboard.oauth.*`(env 非空则赢) | 注释声明;插件侧 `plugins/` |
| `HERMES_DASHBOARD_BASIC_AUTH_USERNAME` / `_PASSWORD_HASH` / `_PASSWORD` / `_SECRET` / `_TTL_SECONDS` | `dashboard.basic_auth.*` | 注释声明 |
| `HERMES_DASHBOARD_DRAIN_SECRET` | (**只有** env,配置里故意不放密钥) | `plugins/dashboard_auth/drain/__init__.py:42` |
| `HERMES_DASHBOARD_PUBLIC_URL` | `dashboard.public_url` | 注释声明 |
| `PORCUPINE_ACCESS_KEY` | `wake_word.provider="porcupine"` 需要 | 注释声明 |
| `OPENROUTER_API_KEY` | `auxiliary.free_only` 语境 | 注释声明 |
| `OPENAI_API_KEY` | `auxiliary.*.api_key` / `delegation.api_key` 的 fallback | 注释声明 |
| `DEEPINFRA_BASE_URL` | `tts.deepinfra.base_url` / `stt.deepinfra.base_url`(两者都被注释掉) | 注释声明 |
| `AWS_REGION` | `bedrock.region` 空时的 fallback | 注释声明 |
| `HERMES_TUI` | `display.interface`("=1 forces the TUI regardless of config") | 注释声明 |
| `HERMES_HOME` | 多处路径基点(`terminal.home_mode`、状态短语路径、pets 目录) | 注释声明 |
| `TERMINAL_*`(27 个) | 由 `TERMINAL_CONFIG_ENV_MAP` 从 `terminal.*` 投影 | `hermes_cli/config.py:3183` |

`hermes_cli/config.py:3213 @ 863e313`

```python
    "persistent_shell": "TERMINAL_PERSISTENT_SHELL",
```

`agent/chat_completion_helpers.py:4088 @ 863e313`

```python
        _stream_stale_timeout = env_float("HERMES_LOCAL_STREAM_STALE_TIMEOUT", _local_default)
```

`cron/scheduler.py:4230 @ 863e313`

```python
            _env_par = os.getenv("HERMES_CRON_MAX_PARALLEL", "").strip()
```

`plugins/platforms/discord/adapter.py:6166 @ 863e313`

```python
            configured = os.getenv("DISCORD_MAX_ATTACHMENT_BYTES")
```

**未确证**:`HERMES_DASHBOARD_BASIC_AUTH_*` 与 `HERMES_DASHBOARD_OAUTH_*` 系列我只验证了它们
在仓库里出现,没有逐个读到"env 非空则覆盖配置"的那行判断代码(它们在 `plugins/dashboard_auth/`
和 Nous Portal 插件里)。这一段是照注释记录的,读者请勿当作已验证。

---

## 7. 文档 / 注释与代码的出入

**▲1 `whatsapp` 段的注释描述了一个不存在于 DEFAULT_CONFIG 的键。**
注释讲"Reply prefix prepended to every outgoing WhatsApp message. Default (None) …",
但块内**一个键都没有**;真实键名 `whatsapp.reply_prefix` 只出现在 gateway 侧。
`hermes_cli/config_defaults.py:1997 @ 863e313`

```python
    "whatsapp": {
```

`gateway/config.py:1545 @ 863e313`

```python
                if "reply_prefix" in platform_cfg:
```

后果:`get_missing_config_fields()` 永远不会提示这个键;读注释的人也拿不到确切键名。
(能写进去是因为 `whatsapp` 在 `_SCHEMA_DEFINED_DICT_KEYS` 白名单里,校验放行。)

**▲2 两个 `allow_private_urls` 的注释都没说明主次。**
`browser.allow_private_urls`(376)与 `security.allow_private_urls`(2133)在注释里是平级的,
但代码里 `security.*` 是**首选**、`browser.*` 是**遗留兼容**,且两者之上还有环境变量。
`hermes_cli/config_defaults.py:376 @ 863e313`

```python
        "allow_private_urls": False,  # Allow navigating to private/internal IPs (localhost, 192.168.x.x, etc.)
```

`tools/url_safety.py:226 @ 863e313`

```python
    3. ``browser.allow_private_urls`` in config.yaml  (legacy / backward compat)
```

**▲3 `database.journal_mode: "wal"` 不保证真的用 WAL。**
注释把 wal 说成"the normal default",但运行时若判定 SQLite 含 WAL-reset 缺陷,
新库/非 WAL 库被强制走 DELETE(即便配置写着 wal)。这不是 bug(是刻意保留的门),
但配置注释里没有提示。`hermes_state.py:674 @ 863e313`

```python
    (issue #69784), refuse to enable WAL on fresh / non-WAL databases
```

**▲4 `agent.reasoning_effort` 被本文件的注释引用,却不在 DEFAULT_CONFIG 里。**
`hermes_cli/config_defaults.py:245 @ 863e313`

```python
        # Takes precedence over agent.reasoning_effort when the current model
```

我用 `ast` 枚举确认 `DEFAULT_CONFIG["agent"]` 的 29 个键里没有 `reasoning_effort`,
而它在 `gateway/slash_commands.py:3406`、`hermes_cli/cli_commands_mixin.py:3260` 被写、
`hermes_constants.py:1108` 描述其解析优先级。见第 8 节 D-1 的后果。

**▲5 `compression.codex_gpt55_autoraise` 的键名与语义不符(作者自己承认)。**
键名说 gpt5.5,实际作用于 gpt-5.4/5.5/5.6,且只在 ChatGPT Codex OAuth 路由上生效。
注释首句已声明这是兼容性保留,记录在此作为"命名债"的样本。

**▲6 `terminal.docker_network` 的注释首句与默认值方向相反。**
"Opt-in egress lockdown for Docker terminal sessions." 读起来像"默认锁网",
实际 `True` = 联网,要 `false` 才锁。注释第二句才澄清。

**▲7 被注释掉的键不会出现在任何机械枚举里。**
`tts.piper` 有 7 个、`tts.deepinfra` 有 1 个、`stt.deepinfra` 有 1 个被 `#` 注释掉的键。
它们是**文档**,不是默认值:`_strip_default_values` 无从比较,`get_missing_config_fields` 不提示,
`_validate_config_key` 会把它们判为未知键。
`hermes_cli/config_defaults.py:1489 @ 863e313`

```python
            # "voices_dir": "",        # Override voice cache dir; default = ~/.hermes/cache/piper-voices/
```

---

## 8. 可疑缺陷(只记录,不修)

**D-1 `hermes config set agent.reasoning_effort <v>` 会给出误导性的"你是不是想写"建议。**
`agent.reasoning_effort` 是真实被支持的键,但不在 `DEFAULT_CONFIG["agent"]` 里,于是
`_validate_config_key` 走到"未知子键"分支,用 `difflib.get_close_matches(cutoff=0.6)` 在同级里找近似。
`hermes_cli/config.py:4812 @ 863e313`

```python
            sibling_suggestion = _suggest_closest_key(seg, set(node.keys()))
```

我用同样的算法在 `DEFAULT_CONFIG["agent"]` 的键集上跑 `reasoning_effort`,得到 `reasoning_overrides`。
**怎么会踩到**:用户 `hermes config set agent.reasoning_effort high` → 值**确实写入了**
(未知键仍然写),但同时打印"did you mean agent.reasoning_overrides"。用户按建议改写成
`agent.reasoning_overrides: high`,那是个**期待 dict 的键**,行为静默失效。
同理 `agent.max_iterations` 会被建议成 `agent.max_turns`(这个恰好是对的,但纯属巧合)。

**D-2 `hermes_cli/config.py` 里的 `_normalize_max_turns_config` 在 load 路径上是死分支。**
它的 `had_agent` 判断在 load 路径里恒为 True,因为它被调用时 `config` 已经是
`_deep_merge(DEFAULT_CONFIG, user_config)` 的结果,而 `DEFAULT_CONFIG["agent"]["max_turns"]` 恒存在。
`hermes_cli/config.py:3389 @ 863e313`

```python
        normalized = _normalize_root_model_keys(_normalize_max_turns_config(config))
```

于是函数在 load 路径上只剩 `config.pop("max_turns", None)` 一句有效——
真正的遗留键搬迁发生在合并**之前**的一段独立代码里。
`hermes_cli/config.py:3341 @ 863e313`

```python
                if "max_turns" in user_config:
```

**怎么会踩到**:不会直接踩到(save 路径上该函数拿到的是 raw config,分支有效)。
但一个只读了 load 路径的人会以为归一化在这里做,改动 pre-merge 那段时不会意识到它才是唯一生效点。

**D-3 `_strip_default_values` 把"该键被剥掉"和"该键的值就是 `None`"混为一谈。**
内部递归函数用 `return None` 表示"与默认相同,剥掉",而叶子分支在值 ≠ 默认时
`return copy.deepcopy(value)`——如果 `value` 本身是 `None`,返回的还是 `None`。
`hermes_cli/config.py:2735 @ 863e313`

```python
        if value == default:
            return None
```

`hermes_cli/config.py:2737 @ 863e313`

```python
        return copy.deepcopy(value)
```

调用方只认 `is not None`:`hermes_cli/config.py:2725 @ 863e313`

```python
                if stripped_child is not None:
```

**怎么会踩到**:用户在 config.yaml 里把一个**默认非 None** 的键显式设为 `null`
(例如 `agent: {max_turns: null}`,或任何"用 null 表达无限/未设"的意图),
下一次 `save_config()` 会把这个键**静默丢掉**,该键回落到默认值。
连 `preserve_keys` 也救不了:preserve 分支返回的同样是 `copy.deepcopy(None)` → `None` → 被丢。
影响面窄(需要"默认非 None + 用户写 null"这一组合),但故障是静默的。

**D-4 `_resolve_allow_private_urls` 的进程级缓存与"配置热更新"冲突。**
单 profile 情况下结果被缓存到进程生命周期结束。`tools/url_safety.py:216 @ 863e313`

```python
_allow_private_resolved = False
```

**怎么会踩到**:长跑的 gateway 进程里,用户改了 `security.allow_private_urls` 并期待
(像 MCP 那样)被文件监视器热应用——不会,必须重启。代码里唯一的重置入口写明"only for tests"。
`tools/url_safety.py:281 @ 863e313`

```python
def _reset_allow_private_cache() -> None:
```

**D-5 `config_defaults.py` 的"不得 import config.py"约束只是 docstring,无强制。**
我没有找到任何 lint / 测试来守这条约束(grep `config_defaults` 的测试文件里没有 import-方向断言)。
**怎么会踩到**:某天有人为了复用一个 helper 在这里 `from hermes_cli.config import ...`,
会造成循环导入,而且只在某些导入顺序下暴露。**未确证**:我只做了 grep,没有穷尽所有
lint 配置(`pyproject.toml` / `ruff.toml` 的自定义规则我没读)。

**D-6 `terminal` 的默认值在三处各写一遍,彼此可以漂移。**
`DEFAULT_CONFIG["terminal"]`(本文件)、`TERMINAL_CONFIG_ENV_MAP`(config.py,只列 27 个键)、
`tools/terminal_tool.py` 的 `os.getenv(name, "<literal default>")`。
**怎么会踩到**:改 `DEFAULT_CONFIG["terminal"]["container_persistent"]` 而忘了
`tools/terminal_tool.py:1567` 的 `os.getenv("TERMINAL_CONTAINER_PERSISTENT", "true")`,
在**没有走 config→env 桥**的子进程里(直接被 exec 的 worker)默认就不一致了。
`tools/terminal_tool.py:1567 @ 863e313`

```python
        "container_persistent": os.getenv("TERMINAL_CONTAINER_PERSISTENT", "true").lower() in {"true", "1", "yes"},
```

---

## 9. 配套测试(行为规格参照)

我实跑了 3 个与本段直接相关的文件,全绿(28 tests, 3.4s):

```
HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
  tests/test_journal_mode_config.py \
  tests/tools/test_terminal_config_env_sync.py \
  tests/gateway/test_per_platform_streaming_defaults.py
# === Summary: 3 files, 28 tests passed, 0 failed (100% complete) in 3.4s (8 workers) ===
```

全仓有 **59 个** `.py` 测试文件引用 `DEFAULT_CONFIG` 或 `config_defaults`。与本段(1-2200)对应的:

| 配置簇 | 行为规格文件 |
|---|---|
| 加载/合并/迁移/写回 | `tests/hermes_cli/test_config.py`、`tests/hermes_cli/test_config_loader_e2e.py` |
| `config set` 路径校验 | `tests/hermes_cli/test_config_validation.py`、`tests/hermes_cli/test_set_config_value.py` |
| `database.journal_mode` | `tests/test_journal_mode_config.py` |
| `terminal.*` → env 桥 | `tests/tools/test_terminal_config_env_sync.py`、`tests/tools/test_docker_config_migrate.py` |
| `tool_output.*` | `tests/tools/test_tool_output_limits.py` |
| `compression.*` | `tests/agent/test_context_compressor.py`、`tests/run_agent/test_in_place_compaction.py`、`tests/run_agent/test_per_model_threshold_init_ordering.py` |
| `auxiliary.*` | `tests/agent/test_auxiliary_config_bridge.py`、`tests/hermes_cli/test_aux_config.py` |
| `openrouter.*` | `tests/agent/test_openrouter_response_cache.py` |
| `agent.verify_on_stop` | `tests/agent/test_verification_stop.py` |
| `agent.session_stall_timeout` | `tests/gateway/test_session_stall_watchdog.py` |
| `agent.reasoning_overrides` / `agent.reasoning_effort` | `tests/gateway/test_reasoning_config_per_model.py`、`tests/test_hermes_constants.py`、`tests/cli/test_reasoning_command.py`、`tests/hermes_cli/test_reasoning_full_command.py` |
| `display.platforms.*` | `tests/gateway/test_per_platform_streaming_defaults.py` |
| `display.interface` | `tests/hermes_cli/test_default_interface_resolution.py` |
| `display.resume_*` | `tests/cli/test_resume_display.py` |
| `whatsapp.reply_prefix` | `tests/gateway/test_whatsapp_reply_prefix.py` |
| `discord.missed_message_backfill` | `tests/gateway/test_discord_missed_message_backfill.py` |
| `approvals.mcp_reload_confirm` | `tests/hermes_cli/test_mcp_reload_confirm_gate.py` |
| `approvals.destructive_slash_confirm` | `tests/hermes_cli/test_destructive_slash_confirm_gate.py` |
| `mcp_discovery_timeout` / `mcp_single_query_discovery_timeout` | `tests/hermes_cli/test_mcp_discovery_timing.py` |
| `context.memory_trim.*` | `tests/hermes_cli/test_mem_trim.py` |
| `curator.*` | `tests/agent/test_curator.py` |
| `wake_word.*` | `tests/tools/test_wake_word.py` |
| `stt.language` | `tests/tools/test_stt_default_language.py` |
| `browser.engine` / `browser.restrict_evaluate` / `browser.camofox` | `tests/tools/test_browser_lightpanda.py`、`tests/tools/test_browser_console.py`、`tests/tools/test_browser_hardening.py`、`tests/tools/test_browser_camofox_state.py` |
| `security.allow_private_urls` / `website_blocklist` | `tests/tools/test_website_policy.py`、`tests/tools/test_command_guards.py` |
| `web.*` | `tests/tools/test_web_providers.py` |
| `cron.provider` / `cron.chronos` | `tests/cron/test_scheduler_provider.py` |
| `dashboard.*` | `tests/hermes_cli/test_web_server.py`、`tests/test_tui_gateway_server.py` |

`tests/hermes_cli/test_config_validation.py:4 @ 863e313`

```python
from hermes_cli.config import (
```

---

## 10. 全键表(1-2200 行,683 项,机械枚举)

**本表所有"行"列均指 `hermes_cli/config_defaults.py` @ 863e313 的行号。**
值为 `{ … }` 表示该键是容器(非空嵌套 dict),其子键在紧随其后的行里逐条列出。
注释列是源码注释原文压成一行(超长截断至 420 字符),空白表示**该键在源码里没有任何注释**。

<!-- TABLE -->

---

## 11. 重实现要点

如果要从零写一个同级别 harness 的配置层,这一段给出的必须知道的东西:

1. **默认值表要同时服务四种消费者,一开始就想清楚**:深合并基座、"新增了哪些项"的迁移清单、
   写回时的裁剪基准、以及 `config set` 的路径校验 schema。Hermes 用一个 dict 全包了,
   代价是"不在表里的合法键"(`agent.reasoning_effort`)会被第 4 种用途误判。
   要么保证表是全集,要么给第 4 种用途一份独立的 known-keys 清单。

2. **深合并必须处理 YAML 空 section**:`terminal:` 不给值解析成 `None`,若当作覆盖会把整段默认打成 `None`,
   下游每个期待 mapping 的消费者都会崩。规则是"dict 默认 + None 覆盖 = 忽略"。

3. **配置解析失败不能回落默认值**,要回落"上一次成功加载的配置"。理由是安全键
   (`approvals.deny`)必须在用户把 YAML 改坏的窗口里继续生效。

4. **"剥离默认值再写回"这条链路要用哨兵而不是 `None` 表示"已剥离"**,否则用户显式写的 `null`
   会被静默吞掉(本段 D-3)。

5. **给每个数值默认写清"0 / null 表示什么"**,并且**在整个配置里统一**。Hermes 这里 0 和 null
   混用(有的键两者都接受),是可读性上的净损失。

6. **超时要区分"不活动预算"与"绝对天花板"**,并让流式输出能延长前者。
   Hermes 的 `hygiene_timeout_seconds` / `hygiene_total_ceiling_seconds` 是可以直接抄的形状:
   进度感知的空闲预算 + 绝对上限 + "已开始的持久化提交永不半途放弃"。

7. **凡是会打断 provider 提示缓存前缀的机制,都要给一个"最小收益门"**,把缓存断裂从每轮变成偶发
   (`proactive_prune_min_reclaim_tokens`)。这是 Hermes 压缩簇里最值钱的一条设计。

8. **默认值注释就是 ADR**:写清楚"为什么是这个数""调大会怎样""调小会怎样""踩过哪个 issue"。
   本段的注释密度让人能在不读消费侧代码的情况下理解 80% 的机制取舍——这是这份文件真正的价值,
   也是最该抄的工程习惯。
