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
`browser.allow_private_urls`(遗留)。`tools/url_safety.py:251 @ 863e313`

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
`hermes_cli/config.py:3231 @ 863e313`

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
`hermes_cli/config.py:4810 @ 863e313`

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
`hermes_cli/config.py:3340 @ 863e313`

```python
                if "max_turns" in user_config:
```

**怎么会踩到**:不会直接踩到(save 路径上该函数拿到的是 raw config,分支有效)。
但一个只读了 load 路径的人会以为归一化在这里做,改动 pre-merge 那段时不会意识到它才是唯一生效点。

**D-3 `_strip_default_values` 把"该键被剥掉"和"该键的值就是 `None`"混为一谈。**
内部递归函数用 `return None` 表示"与默认相同,剥掉",而叶子分支在值 ≠ 默认时
`return copy.deepcopy(value)`——如果 `value` 本身是 `None`,返回的还是 `None`。
`hermes_cli/config.py:2733 @ 863e313`

```python
        if value == default:
            return None
```

`hermes_cli/config.py:2736 @ 863e313`

```python
        return copy.deepcopy(value)
```

调用方只认 `is not None`:`hermes_cli/config.py:2726 @ 863e313`

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
`tools/url_safety.py:282 @ 863e313`

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

| 行 | 键(点分路径) | 默认值 | 注释(源码原文,压成一行) |
|---|---|---|---|
| 8 | `model` | `''` |  |
| 9 | `providers` | `{}` |  |
| 10 | `fallback_providers` | `[]` |  |
| 11 | `credential_pool_strategies` | `{}` |  |
| 12 | `toolsets` | `['hermes-cli']` |  |
| 16 | `database` | `{ … }` | SQLite journal mode used by every Hermes database opener. WAL is the normal default; set DELETE for weak-fsync/shared filesystems where WAL is not crash-safe (for example macOS virtiofs, NFS, or SMB). |
| 17 | `database.journal_mode` | `'wal'` |  |
| 20 | `database.wal_autocheckpoint` | `None` | Optional WAL sizing pragmas, applied when set to integers. None = SQLite defaults (autocheckpoint 1000 pages, no size limit). |
| 21 | `database.journal_size_limit` | `None` |  |
| 25 | `max_concurrent_sessions` | `None` | Global active chat session cap across CLI, TUI/dashboard, and messaging. None/0 = unbounded. |
| 30 | `max_live_sessions` | `16` | Soft LRU cap on in-memory TUI/desktop/dashboard sessions. When more than this many are live, the gateway evicts the least-recently-active DETACHED sessions (no live client) so accumulated agents don't pile up under memory pressure. Reopening one re-resumes it from disk. 0/null disables. |
| 31 | `agent` | `{ … }` |  |
| 32 | `agent.max_turns` | `500` |  |
| 37 | `agent.gateway_timeout` | `1800` | Inactivity timeout for gateway agent execution (seconds). The agent can run indefinitely as long as it's actively calling tools or receiving API responses. Only fires when the agent has been completely idle for this duration. 0 = unlimited. |
| 47 | `agent.restart_drain_timeout` | `0` | Force-interrupt budget once gateway stop()/drain has begun (seconds). Applies to SIGTERM/external stop and to the final phase of in-band restart after any after-turn wait. 0 = interrupt immediately (the default). Keep this short and under systemd TimeoutStopSec — a long value here invites SIGKILL-mid-cleanup. For in-band restart (/restart, SIGUSR1), prefer restart_after_turn_timeout below so active turns finish *befo … |
| 54 | `agent.restart_after_turn_timeout` | `21600` | In-band restart wait for active turns to finish before stop() (seconds). /restart and SIGUSR1 refuse new work, then wait up to this cap for in-flight agents/cron/api runs to complete naturally so the requesting turn is not amputated by restart_drain_timeout. 0 = legacy behaviour (enter stop()/drain immediately). Default 6h is a safety valve for wedged agents, not a target latency. |
| 62 | `agent.build_wait_timeout` | `600` | Upper bound (seconds) a submitted prompt waits for the deferred agent build (MCP discovery, model metadata, skills scan) before failing with a visible error (#63078). The gateway's wait is patient — the prompt is delivered the moment the build completes and a progress notice is emitted past 30s — so this cap only fires on a genuinely hung build. Raise it for deployments with many slow or unreachable MCP servers. |
| 71 | `agent.api_max_retries` | `3` | Max app-level retry attempts for API errors (connection drops, provider timeouts, 5xx, etc.) before the agent surfaces the failure. The OpenAI SDK already does its own low-level retries (max_retries=2 default) for transient network errors; this is the Hermes-level retry loop that wraps the whole call. Lower this to 1 if you use fallback providers and want fast failover on flaky primaries; raise it if you prefer to to … |
| 72 | `agent.service_tier` | `''` |  |
| 78 | `agent.tool_use_enforcement` | `'auto'` | Tool-use enforcement: injects system prompt guidance that tells the model to actually call tools instead of describing intended actions. Values: "auto" (default — applies to gpt/codex models), true/false (force on/off for all models), or a list of model-name substrings to match (e.g. ["gpt", "codex", "gemini", "qwen"]). |
| 88 | `agent.intent_ack_continuation` | `'auto'` | Intent-ack continuation: when the model opens a turn by narrating an action it will take ("I'll go check the logs...") but emits no tool call, intercept the turn-end, inject a "continue now, execute the tools" nudge, and loop instead of ending the turn (capped at 2 nudges per turn). This is the corrective sibling of tool_use_enforcement (the preventive prompt-side guard). Values: "auto" (default — fires only on the c … |
| 94 | `agent.task_completion_guidance` | `True` | Universal "finish the job" guidance — short prompt block applied to all models that targets two cross-family failure modes: (1) stopping after a stub instead of finishing the artifact, (2) fabricating plausible-looking output when a real path is blocked. Costs ~80 tokens in the cached system prompt. Set False to disable globally. |
| 103 | `agent.parallel_tool_call_guidance` | `True` | Universal parallel-tool-call guidance — short prompt block applied to all models that tells the model to batch independent tool calls (reads, searches, web fetches, read-only commands) into one turn instead of one call per turn. The runtime already runs independent calls concurrently, so this just steers the model to produce the batch — cutting round-trips and the resent-context cost that compounds over a long conver … |
| 111 | `agent.environment_probe` | `True` | Local-environment toolchain probe — surfaces Python/pip/uv/PEP-668 state in the system prompt when something non-default is detected (e.g. python3 has no pip module, pip→python version mismatch, PEP 668 enforcement without uv). Costs zero tokens when the env is clean (probe emits nothing). Skipped for remote terminal backends (docker/modal/ssh — they have their own probe). Set False to disable entirely. |
| 118 | `agent.environment_hint` | `''` | Embedder-supplied environment description appended to the system prompt's environment-hints block. Lets a host that wraps Hermes (sandbox runner, managed platform) explain the runtime environment — proxy, credential handling, mount layout — without editing the identity slot (SOUL.md). Empty by default. The HERMES_ENVIRONMENT_HINT env var overrides this (build-time/container mechanism). |
| 133 | `agent.coding_context` | `'auto'` | Coding posture — on interactive coding surfaces (CLI, TUI, desktop app, ACP) in a code workspace, Hermes adds a coding operating brief + a live git/workspace snapshot to the system prompt. See agent/coding_context.py. "auto" (default) — prompt-only posture when the surface is interactive AND cwd is a code workspace. Toolsets are never touched; messaging platforms unaffected. "focus" — auto + collapse the toolset to t … |
| 140 | `agent.coding_instructions` | `''` | Standing operator instructions for the coding posture. A string (or list of strings) appended to the coding brief as an extra stable system block — pin project-wide workflow rules here instead of editing the shipped brief, e.g. "For UI work, don't run tsc/lint until I approve. Clean the diff before you commit and push." Cache-safe: takes effect next session. Empty by default. |
| 145 | `agent.verify_guidance` | `True` | When verify-on-stop finds edited code without fresh verification evidence, append guidance for creative UI work (avoid broad tsc/lint/test before visual approval) and clean-diff expectations. Set false to keep the evidence nudge terse. |
| 148 | `agent.max_verify_nudges` | `3` | Upper bound on consecutive `pre_verify` "continue" nudges in a single turn, so a user/plugin hook can never trap the loop. |
| 158 | `agent.verify_on_stop` | `'auto'` | Verification closure: after the agent edits files in a code workspace, do not accept a final answer until fresh verification evidence exists or the agent explains why it cannot run checks. The loop is bounded and uses the passive verification ledger. Default is "auto" — surface-aware: on for interactive coding surfaces (CLI, TUI, desktop) and programmatic callers, off for conversational messaging surfaces (Telegram, … |
| 162 | `agent.gateway_timeout_warning` | `900` | Staged inactivity warning: send a warning to the user at this threshold before escalating to a full timeout. The warning fires once per run and does not interrupt the agent. 0 = disable warning. |
| 174 | `agent.clarify_timeout` | `3600` | Maximum time (seconds) the gateway will block an agent waiting for a clarify-tool response from the user. Hit this and the agent unblocks with "[user did not respond within Xm]" so it can adapt rather than pinning the running-agent guard forever. CLI clarify blocks indefinitely (input() is synchronous) and ignores this. Default 3600 (1h): real users step away (meetings, AFK) and the old 600s default evicted the entry … |
| 182 | `agent.gateway_notify_interval` | `180` | Periodic "still working" notification interval (seconds). Sends a status message every N seconds so the user knows the agent hasn't died during long tasks. 0 = disable notifications. Lower values mean faster feedback on slow tasks but more chat noise; 180s is a compromise that catches spinning weak-model runs (60+ tool iterations with tiny output) before users assume the bot is dead and /restart. |
| 193 | `agent.session_stall_timeout` | `300` | Session stall watchdog (seconds). Scope (#76354): this is a RECOVERY notifier for an in-process AIAgent that has an adapter-queued follow-up (pending inbound / queued event) while its activity clock is stale — NOT a general gateway/session stall detector. It does not observe startup restoration, build sentinels, turn leases, debounce state, or work owned by another process; the scan cadence is per AIAgent instance, n … |
| 207 | `agent.gateway_auto_continue_freshness` | `3600` | Freshness window for the gateway auto-continue note (seconds). After a gateway crash/restart/SIGTERM mid-run, the next user message gets a "[System note: your previous turn was interrupted — process the unfinished tool result(s) first]" prepended so the model picks up where it left off. That's the right behaviour while the interruption is fresh, but stale markers (transcript last touched hours or days ago) can revive … |
| 219 | `agent.gateway_startup_restore_drain_timeout` | `30` | Max seconds the gateway waits for boot auto-resume turns to finish before it releases the startup-restore inbound gate. While startup restore is in progress the gateway QUEUES every inbound message instead of replying, so no channel gets an answer until this gate opens. Without a bound, one pathologically long resumed turn holds the gate shut and every channel's inbound piles up unanswered for as long as that turn ru … |
| 226 | `agent.local_stream_stale_timeout` | `900` | Stale-stream ceiling for local providers (Ollama, oMLX, llama-cpp) in seconds. When the base stale timeout is at its default (180s) and a local endpoint is detected, this finite ceiling replaces the former infinite disable so a wedged local server eventually trips the detector instead of hanging forever. The env var ``HERMES_LOCAL_STREAM_STALE_TIMEOUT`` overrides for escape-hatch use. |
| 240 | `agent.image_input_mode` | `'auto'` | How user-attached images are presented to the main model on each turn. "auto" — attach natively when the active model reports supports_vision=True AND the user hasn't explicitly configured auxiliary.vision.provider. Otherwise fall back to text (vision_analyze pre-analysis). "native" — always attach natively; non-vision models will either error at the provider or get a last-chance text fallback (see run_agent._prepare … |
| 241 | `agent.disabled_toolsets` | `[]` |  |
| 248 | `agent.reasoning_overrides` | `{}` | Per-model reasoning effort overrides (spelling-tolerant). Dict mapping model names (any reasonable spelling) to effort levels. Takes precedence over agent.reasoning_effort when the current model matches a key in this dict. Edit directly in config.yaml (no CLI support due to dots in keys). |
| 251 | `terminal` | `{ … }` |  |
| 252 | `terminal.backend` | `'local'` |  |
| 253 | `terminal.modal_mode` | `'auto'` |  |
| 254 | `terminal.cwd` | `'.'` | Use current directory |
| 262 | `terminal.font_family` | `''` | Terminal font family for the desktop app's embedded xterm.js terminal. When set (e.g. "'CaskaydiaCoveNerdFont', 'JetBrains Mono', monospace"), the desktop terminal uses this as the CSS font-family value, with the built-in default ("'JetBrains Mono', 'Cascadia Code', 'SF Mono', Menlo, Consolas, monospace") as fallback when the field is empty or unset. This lets users install a Nerd Font (or any custom font) and config … |
| 263 | `terminal.timeout` | `180` |  |
| 269 | `terminal.daemon_term_grace_seconds` | `2.0` | Bounded grace period (seconds) between SIGTERM and an escalated SIGKILL when terminating a host process tree (browser daemons, etc.). A daemon that stalls in its SIGTERM handler is force-killed after this window so it can't leak indefinitely. 0 disables escalation (SIGTERM only — the historical behavior). Floored internally at 0. |
| 273 | `terminal.env_passthrough` | `[]` | Environment variables to pass through to sandboxed execution (terminal and execute_code). Skill-declared required_environment_variables are passed through automatically; this list is for non-skill use cases. |
| 280 | `terminal.home_mode` | `'auto'` | HOME handling for host tool subprocesses: auto — host keeps the real OS-user HOME; containers use HERMES_HOME/home for persistent state (default) real — force the real OS-user HOME profile — force HERMES_HOME/home when it exists (old strict per-profile CLI config isolation) |
| 293 | `terminal.shell_init_files` | `[]` | Extra files to source in the login shell when building the per-session environment snapshot. Use this when tools like nvm, pyenv, asdf, or custom PATH entries are registered by files that a bash login shell would skip — most commonly ``~/.bashrc`` (bash doesn't source bashrc in non-interactive login mode) or zsh-specific files like ``~/.zshrc`` / ``~/.zprofile``. Paths support ``~`` / ``${VAR}``. Missing files are si … |
| 306 | `terminal.auto_source_bashrc` | `True` | When true (default), Hermes sources the user's shell rc files (``~/.profile``, ``~/.bash_profile``, ``~/.bashrc``) in the login shell used to build the environment snapshot. This captures PATH additions, shell functions, and aliases — which a plain ``bash -l -c`` would otherwise miss because bash skips bashrc in non-interactive login mode, and because a default Debian/Ubuntu ``~/.bashrc`` short-circuits on non-intera … |
| 307 | `terminal.docker_image` | `'nikolaik/python-nodejs:python3.11-nodejs20'` |  |
| 308 | `terminal.docker_forward_env` | `[]` |  |
| 314 | `terminal.docker_env` | `{}` | Explicit environment variables to set inside Docker containers. Unlike docker_forward_env (which reads values from the host process), docker_env lets you specify exact key-value pairs — useful when Hermes runs as a systemd service without access to the user's shell environment. Example: {"SSH_AUTH_SOCK": "/run/user/1000/ssh-agent.sock"} |
| 315 | `terminal.singularity_image` | `'docker://nikolaik/python-nodejs:python3.11-nodejs20'` |  |
| 316 | `terminal.modal_image` | `'nikolaik/python-nodejs:python3.11-nodejs20'` |  |
| 317 | `terminal.daytona_image` | `'nikolaik/python-nodejs:python3.11-nodejs20'` |  |
| 320 | `terminal.vercel_runtime` | `'node24'` | Vercel Sandbox runtime (vercel_sandbox backend only). Supported: node24, node22, python3.13. |
| 322 | `terminal.container_cpu` | `1` | Container resource limits (docker, singularity, modal, daytona, vercel_sandbox — ignored for local/ssh) |
| 323 | `terminal.container_memory` | `5120` | MB (default 5GB) |
| 324 | `terminal.container_disk` | `51200` | MB (default 50GB) |
| 325 | `terminal.container_persistent` | `True` | Persist filesystem across sessions |
| 333 | `terminal.docker_volumes` | `[]` | Docker volume mounts — share host directories with the container. Each entry is "host_path:container_path" (standard Docker -v syntax). Example: ["/home/user/projects:/workspace/projects", "/home/user/.hermes/cache/documents:/output"] For gateway MEDIA delivery, write inside Docker to /output/... and emit the host-visible path in MEDIA:, not the container path. |
| 336 | `terminal.docker_mount_cwd_to_workspace` | `False` | Explicit opt-in: mount the host cwd into /workspace for Docker sessions. Default off because passing host directories into a sandbox weakens isolation. |
| 339 | `terminal.docker_network` | `True` | Opt-in egress lockdown for Docker terminal sessions. When false, Docker runs with --network=none so commands cannot reach the network. |
| 340 | `terminal.docker_extra_args` | `[]` | Extra flags passed verbatim to docker run |
| 345 | `terminal.docker_shm_size` | `'1g'` | /dev/shm size for the Docker sandbox. Docker's 64 MB default silently breaks Chromium/Playwright and PyTorch DataLoader workers; tmpfs is lazily allocated so the higher ceiling costs nothing until used. Set to "" (or "0") to omit the flag and use Docker's default. |
| 356 | `terminal.docker_run_as_host_user` | `False` | Explicit opt-in: run the Docker container as the host user's uid:gid (via `--user`). When enabled, files written into bind-mounted dirs (docker_volumes, the persistent workspace, or the auto-mounted cwd) are owned by your host user instead of root, which avoids needing `sudo chown` after container runs. Default off to preserve behavior for images whose entrypoints expect to start as root (e.g. the bundled Hermes imag … |
| 361 | `terminal.persistent_shell` | `True` | Persistent shell — keep a long-lived bash shell across execute() calls so cwd/env vars/shell variables survive between commands. Enabled by default for non-local backends (SSH); local is always opt-in via TERMINAL_LOCAL_PERSISTENT env var. |
| 364 | `web` | `{ … }` |  |
| 365 | `web.backend` | `''` | shared fallback — applies to both search and extract |
| 366 | `web.search_backend` | `''` | per-capability override for web_search (e.g. "searxng") |
| 367 | `web.extract_backend` | `''` | per-capability override for web_extract (e.g. "native") |
| 368 | `web.extract_char_limit` | `15000` | per-page char budget for web_extract; larger pages truncate + store full text in cache/web |
| 371 | `browser` | `{ … }` |  |
| 372 | `browser.inactivity_timeout` | `120` |  |
| 373 | `browser.command_timeout` | `30` | Timeout for browser commands in seconds (screenshot, navigate, etc.) |
| 374 | `browser.record_sessions` | `False` | Auto-record browser sessions as WebM videos |
| 375 | `browser.headed` | `False` | Local mode: launch Chromium with a visible window (also skips per-turn cleanup so the window persists between turns; idle reaper still applies) |
| 376 | `browser.allow_private_urls` | `False` | Allow navigating to private/internal IPs (localhost, 192.168.x.x, etc.) |
| 383 | `browser.engine` | `'auto'` | Browser engine for local mode. Passed as ``--engine <value>`` to agent-browser v0.25.3+. "auto" — use Chrome (default, don't pass --engine at all) "lightpanda" — use Lightpanda (1.3-5.8x faster navigation, no screenshots) "chrome" — explicitly request Chrome Also settable via AGENT_BROWSER_ENGINE env var. |
| 384 | `browser.auto_local_for_private_urls` | `True` | When a cloud provider is set, auto-spawn local Chromium for LAN/localhost URLs instead of sending them to the cloud |
| 385 | `browser.cdp_url` | `''` | Optional persistent CDP endpoint for attaching to an existing Chromium/Chrome |
| 386 | `browser.allow_unsafe_evaluate` | `False` | Legacy override: when true, browser_console(expression=...) bypasses the restrict_evaluate denylist entirely |
| 387 | `browser.restrict_evaluate` | `False` | Opt-in denylist blocking sensitive JS primitives (cookies/storage/clipboard/network/form values) in browser_console(expression=...) |
| 392 | `browser.dialog_policy` | `'must_respond'` | must_respond \| auto_dismiss \| auto_accept |
| 393 | `browser.dialog_timeout_s` | `300` | Safety auto-dismiss after N seconds under must_respond |
| 394 | `browser.camofox` | `{ … }` |  |
| 398 | `browser.camofox.managed_persistence` | `False` | When true, Hermes sends a stable profile-scoped userId to Camofox so the server maps it to a persistent Firefox profile automatically. When false (default), each session gets a random userId (ephemeral). |
| 401 | `browser.camofox.user_id` | `''` | Optional externally managed Camofox identity. Useful when another app owns the visible browser and Hermes should operate in it. |
| 402 | `browser.camofox.session_key` | `''` |  |
| 404 | `browser.camofox.adopt_existing_tab` | `False` | Rehydrate tab_id from Camofox before creating a new tab. |
| 408 | `browser.camofox.rewrite_loopback_urls` | `False` | Docker Camofox opens page URLs from inside the container. Enable this to rewrite loopback page URLs (localhost/127.0.0.1/::1) to a host alias while leaving CAMOFOX_URL itself unchanged. |
| 409 | `browser.camofox.loopback_host_alias` | `'host.docker.internal'` |  |
| 423 | `checkpoints` | `{ … }` | Filesystem checkpoints — automatic snapshots before destructive file ops. When enabled, the agent takes a snapshot of the working directory once per conversation turn (on first write_file/patch call). Use /rollback to restore. Defaults changed in v2 (single shared shadow store, real pruning): - enabled: True -> False (opt-in; most users never use /rollback) - max_snapshots: 50 -> 20 (now actually enforced via ref rew … |
| 424 | `checkpoints.enabled` | `False` |  |
| 428 | `checkpoints.max_snapshots` | `20` | Max checkpoints to keep per working directory. Pre-v2 this only limited the `/rollback` listing; v2 actually rewrites the ref and garbage-collects older commits. |
| 433 | `checkpoints.max_total_size_mb` | `500` | Hard ceiling on total ``~/.hermes/checkpoints/`` size (MB). When exceeded, the oldest checkpoint per project is dropped in a round-robin pass until total size falls under the cap. 0 disables the size cap. |
| 437 | `checkpoints.max_file_size_mb` | `10` | Skip any single file larger than this when staging a checkpoint. Prevents accidental snapshotting of datasets, model weights, and other large generated assets. 0 disables the filter. |
| 454 | `checkpoints.auto_prune` | `True` | Auto-maintenance: hermes sweeps the checkpoint base at startup (at most once per ``min_interval_hours``) and: * deletes project entries whose last_touch is older than ``retention_days`` * GCs the single shared store to reclaim unreachable objects * enforces ``max_total_size_mb`` across remaining projects * deletes ``legacy-*`` archives older than ``retention_days`` NOTE: this automatic sweep never deletes "orphan" en … |
| 455 | `checkpoints.retention_days` | `7` |  |
| 456 | `checkpoints.min_interval_hours` | `24` |  |
| 465 | `context_file_max_chars` | `None` | Hard cap (chars) for a single automatic context file such as SOUL.md, AGENTS.md, CLAUDE.md, .hermes.md, or .cursorrules before Hermes applies head/tail truncation. ``null`` (the default) lets the cap scale with the model's context window (floor 20K, ceiling 500K) so large-context models rarely truncate a project doc. Set a positive integer to pin a fixed cap and override the dynamic behavior. Separate from read_file … |
| 470 | `file_read_max_chars` | `100000` | Maximum characters returned by a single read_file call. Reads that exceed this are rejected with guidance to use offset+limit. 100K chars ≈ 25–35K tokens across typical tokenisers. |
| 485 | `mcp_discovery_timeout` | `1.5` | Seconds to wait at agent-build time for in-flight MCP server discovery to finish before the agent snapshots its tool list. MCP discovery runs in a background thread so a slow/dead server can't freeze startup; this bounds how long the first agent build blocks on it. The wait returns the INSTANT discovery completes, so users with no MCP servers (the common case) or fast servers pay ~0s regardless of this value — the bo … |
| 495 | `mcp_single_query_discovery_timeout` | `15.0` | Single-query (``hermes -q/-z "..."``) variant of mcp_discovery_timeout. In one-shot mode there is only ONE turn, so the between-turns late-binding refresh never runs: a server that misses the small interactive bound is invisible to the LLM for the whole session. This larger bound gives slow cold-start servers (npx, uvx, remote HTTP) a chance to land in the one tool snapshot. ``thread.join(timeout)`` returns the insta … |
| 499 | `mcp` | `{ … }` | MCP runtime behavior (distinct from the per-server definitions in mcp_servers: and from the auxiliary.mcp side-LLM task settings). |
| 508 | `mcp.auto_reload_on_config_change` | `True` | Auto-reload MCP connections when config.yaml's mcp_servers section changes at runtime (CLI file watcher, default on). Set to false to stop the automatic reload: every automatic reload rebuilds the agent tool surface and INVALIDATES the provider prompt cache (the next message re-sends the full input prefix), which is expensive on long-context / high-reasoning models. When disabled, the watcher still detects the change … |
| 525 | `tool_output` | `{ … }` | Tool-output truncation thresholds. When terminal output or a single read_file page exceeds these limits, Hermes truncates the payload sent to the model (keeping head + tail for terminal, enforcing pagination for read_file). Tuning these trades context footprint against how much raw output the model can see in one shot. Ported from anomalyco/opencode PR #23770. - max_bytes: terminal_tool output cap, in chars (default … |
| 526 | `tool_output.max_bytes` | `50000` |  |
| 527 | `tool_output.max_lines` | `2000` |  |
| 528 | `tool_output.max_line_length` | `2000` |  |
| 534 | `tool_loop_guardrails` | `{ … }` | Tool loop guardrails nudge models when they repeat failed or non-progressing tool calls. Soft warnings are always-on by default; hard stops are opt-in so interactive CLI/TUI sessions keep flowing. |
| 535 | `tool_loop_guardrails.warnings_enabled` | `True` |  |
| 536 | `tool_loop_guardrails.hard_stop_enabled` | `False` |  |
| 537 | `tool_loop_guardrails.warn_after` | `{ … }` |  |
| 538 | `tool_loop_guardrails.warn_after.exact_failure` | `2` |  |
| 539 | `tool_loop_guardrails.warn_after.same_tool_failure` | `3` |  |
| 540 | `tool_loop_guardrails.warn_after.idempotent_no_progress` | `2` |  |
| 542 | `tool_loop_guardrails.hard_stop_after` | `{ … }` |  |
| 543 | `tool_loop_guardrails.hard_stop_after.exact_failure` | `5` |  |
| 544 | `tool_loop_guardrails.hard_stop_after.same_tool_failure` | `8` |  |
| 545 | `tool_loop_guardrails.hard_stop_after.idempotent_no_progress` | `5` |  |
| 555 | `tool_loop_guardrails.loop_caps` | `{ … }` | Per-turn runaway-loop caps (inspired by Claude Code v2.1.212, Week 29, July 2026). Hard ceilings on how many times a runaway-prone tool may be called within a SINGLE agent loop (turn); the counters reset at the start of every turn, so a legitimate multi-turn session is never starved. They are always-on and fire regardless of the warn/hard-stop thresholds above. A single turn issuing dozens of web searches or spawning … |
| 556 | `tool_loop_guardrails.loop_caps.max_web_searches` | `50` | max web_search calls per turn (0 = unlimited) |
| 557 | `tool_loop_guardrails.loop_caps.max_subagents` | `50` | max subagents spawned per turn (0 = unlimited) |
| 561 | `compression` | `{ … }` |  |
| 562 | `compression.enabled` | `True` |  |
| 563 | `compression.progress_notices` | `False` | opt-in (#52995): when True, routine compression progress statuses (compacting/preflight/pre-API/ idle/retry) are delivered to chat gateway platforms instead of being suppressed by the gateway noise filter. Default False keeps routine compression silent-by-design on chat surfaces (server-side logging only). Failure notices and manual /compress feedback are always visible regardless of this setting. |
| 572 | `compression.threshold` | `0.5` | compress when context usage exceeds this ratio. Models with context windows below 512K are floored at 0.75 (raise-only) so compaction doesn't fire with half the window still free; set this above 0.75 to override the floor. |
| 577 | `compression.threshold_tokens` | `None` | absolute token cap — when set, compression triggers at the lower of the ratio-based threshold and this token count. Clamped to the model's context length at apply-time. |
| 581 | `compression.target_ratio` | `0.2` | fraction of threshold to preserve as recent tail |
| 582 | `compression.protect_last_n` | `20` | minimum recent messages to keep uncompressed |
| 583 | `compression.min_tail_user_messages` | `1` | REAL (actionable) user messages guaranteed to survive in the uncompressed tail. 1 = existing single last-user anchor (default, behavior- preserving); raise to e.g. 3 to keep the last 3 real user turns verbatim when bulky tool outputs fill the tail token budget. |
| 589 | `compression.max_attempts` | `3` | compression retry rounds before a turn gives up with "max compression attempts reached". Raise (e.g. 6) for tool-schema-heavy sessions where 3 rounds cannot clear the request estimate. Validated >= 1, hard-capped at 10. |
| 594 | `compression.proactive_prune_tokens` | `0` | opt-in trigger (tokens) for the deterministic, no-LLM tool-result prune, run independently of `threshold` above. On large-window models `threshold` (≈50% of the window) rarely fires, so old tool output otherwise rides in history and is re-sent every turn; a low value like 48000 reclaims it early. 0 = off. Recent tail protected by `protect_last_n`. Built-in compressor only (other engines inherit a no-op). NOTE: each c … |
| 607 | `compression.proactive_prune_min_result_chars` | `8000` | the prune's summarize pass only |
| 611 | `compression.proactive_prune_min_reclaim_tokens` | `4096` | a proactive prune only commits |
| 617 | `compression.micro_compact` | `False` | opt-in: after each completed turn, fold the oldest un-absorbed exchange into a rolling summary, amortizing compression cost instead of paying it in one batch stall. Default False because a pass rewrites already-sent history and so breaks the provider prompt-cache prefix EVERY turn — the per-turn cache break that `proactive_prune_min_reclaim_tokens` above exists to avoid. Enable only when you have measured that the am … |
| 629 | `compression.micro_compact_every_n_turns` | `1` | cadence: run a pass every Nth completed |
| 636 | `compression.micro_compact_defrag_threshold_tokens` | `2000` | once the rolling summary |
| 640 | `compression.hygiene_hard_message_limit` | `5000` | gateway session-hygiene force-compress threshold by message count |
| 641 | `compression.hygiene_timeout_seconds` | `30` | max seconds gateway waits for pre-agent hygiene compression WITHOUT forward progress. The summary call streams, so this is an inactivity budget: a slow model still producing tokens keeps extending the wait; only a silent/hung call is cut off. |
| 646 | `compression.hygiene_total_ceiling_seconds` | `600` | absolute cap on the hygiene compression wait even |
| 649 | `compression.hygiene_failure_cooldown_seconds` | `300` | skip repeated failed hygiene attempts for this session |
| 650 | `compression.context_timeout_seconds` | `120` | inactivity budget for in-agent compress_context |
| 657 | `compression.context_total_ceiling_seconds` | `600` | absolute cap on the *pre-commit* |
| 671 | `compression.protect_first_n` | `3` | non-system head messages always preserved verbatim, in ADDITION to the system prompt (which is always implicitly protected). Set to 0 for long-running rolling-compaction sessions where you want nothing pinned except the system prompt + rolling summary + recent tail. |
| 677 | `compression.abort_on_summary_failure` | `False` | When True, auto-compression that fails |
| 688 | `compression.codex_gpt55_autoraise` | `True` | Historical key name kept for compatibility. When True, gpt-5.4 / gpt-5.5 / gpt-5.6 on the ChatGPT Codex OAuth route raise their compaction trigger to 85% (vs the global `threshold` above). Codex hard-caps these families at a 272K window, so the default 50% would compact at ~136K and waste half the usable context. Set to False to opt back down to the global threshold (e.g. 0.50) for those Codex sessions. Only this exa … |
| 700 | `compression.codex_gpt55_autoraise_notice` | `True` | Display the one-time Codex gpt-5.4/5.5/5.6 |
| 704 | `compression.codex_app_server_auto` | `'native'` | Codex app-server (codex CLI runtime) thread |
| 712 | `compression.in_place` | `True` | When True, compaction rewrites the message list and rebuilds the system prompt WITHOUT rotating the session id — the conversation keeps one durable id for its whole life (no parent_session_id chain, no `name #N` renumbering). Eliminates the session-rotation bug cluster (#33618 /goal loss, #14238 lost response, #33907 orphans, #45117 search gaps, #42228 null cwd) — see #38763. Non-destructive: the live context is comp … |
| 728 | `compression.model_thresholds` | `{}` | Per-model threshold overrides. Keys are substring-matched against the model name (longest match wins); values replace the global `threshold` for that model, e.g. model_thresholds: "glm-5.2": 0.40 "claude-sonnet": 0.35 The small-context floor (0.75 for <512K models) still applies on top of overrides (raise-only: an override above the floor wins; one below it is raised to the floor). |
| 739 | `compression.idle_compact_after_seconds` | `0` | Opt-in idle compaction (0 = disabled). |
| 760 | `prompt_caching` | `{ … }` | Anthropic prompt caching (Claude via OpenRouter or native Anthropic API). cache_ttl: "5m" or "1h" (Anthropic-supported tiers). Other non-falsy values are silently ignored. Falsy values (false, null, "off", "disabled", "no", "none") disable prompt caching entirely. |
| 761 | `prompt_caching.cache_ttl` | `'5m'` |  |
| 779 | `openrouter` | `{ … }` | OpenRouter-specific settings. response_cache: enable OpenRouter response caching (X-OpenRouter-Cache header). When enabled, identical requests return cached responses for free (zero billing). This is separate from Anthropic prompt caching and works alongside it. See: https://openrouter.ai/docs/guides/features/response-caching response_cache_ttl: how long cached responses remain valid, in seconds (1-86400). Default 30 … |
| 780 | `openrouter.response_cache` | `True` |  |
| 781 | `openrouter.response_cache_ttl` | `300` |  |
| 782 | `openrouter.min_coding_score` | `0.65` |  |
| 787 | `bedrock` | `{ … }` | AWS Bedrock provider configuration. Only used when model.provider is "bedrock". |
| 788 | `bedrock.region` | `''` | AWS region for Bedrock API calls (empty = AWS_REGION env var → us-east-1) |
| 789 | `bedrock.discovery` | `{ … }` |  |
| 790 | `bedrock.discovery.enabled` | `True` | Auto-discover models via ListFoundationModels |
| 791 | `bedrock.discovery.provider_filter` | `[]` | Only show models from these providers (e.g. ["anthropic", "amazon"]) |
| 792 | `bedrock.discovery.refresh_interval` | `3600` | Cache discovery results for this many seconds |
| 794 | `bedrock.guardrail` | `{ … }` |  |
| 798 | `bedrock.guardrail.guardrail_identifier` | `''` | e.g. "abc123def456" |
| 799 | `bedrock.guardrail.guardrail_version` | `''` | e.g. "1" or "DRAFT" |
| 800 | `bedrock.guardrail.stream_processing_mode` | `'async'` | "sync" or "async" |
| 801 | `bedrock.guardrail.trace` | `'disabled'` | "enabled", "disabled", or "enabled_full" |
| 831 | `auxiliary` | `{ … }` | Auxiliary model config — provider:model for each side task. Format: provider is the provider name, model is the model slug. "auto" for provider = auto-detect best available provider. Empty model = use provider's default auxiliary model. All tasks fall back to openrouter:google/gemini-3-flash-preview if the configured provider is unavailable. extra_body: forwarded verbatim as request body fields on every aux call for … |
| 838 | `auxiliary.transient_retries` | `2` | Same-provider retries for a transient transport blip (connection reset / timeout / 5xx / 408) on ANY auxiliary call before falling back. Default 2 (→ 3 total attempts), clamped [0,6]. Matters most for pinned calls like MoA reference advisors, where provider fallback is not a meaningful recovery, so an unretried blip silently loses the call. |
| 846 | `auxiliary.free_only` | `False` | Restrict the auxiliary auto-chain's OpenRouter fallback to free (:free) SKUs. When true, the OpenRouter step is skipped entirely unless the resolved fallback model ends in ":free" — a PAID lane is never engaged for background auxiliary traffic (compression, title generation, session search, vision, web extract) even when OPENROUTER_API_KEY is present. Default false keeps the historical paid fallback for users who wan … |
| 852 | `auxiliary.openrouter_model` | `''` | Override the auxiliary auto-chain's OpenRouter fallback model (default: google/gemini-3.6-flash, a PAID model). Set e.g. "nvidia/nemotron-3-ultra-550b-a55b:free" together with free_only: true to keep auxiliary traffic free-only. A one-time WARNING is logged whenever a non-":free" model is engaged. |
| 859 | `auxiliary.stream_only_base_urls` | `[]` | Endpoints that reject NON-streaming chat requests outright (e.g. Tencent Copilot returns HTTP 400 "Non-stream chat request is currently not supported"). Auxiliary calls to a matching endpoint are sent with stream=True and aggregated client-side. Entries are case-insensitive substrings matched against the endpoint URL; copilot.tencent.com is always treated as stream-only. |
| 860 | `auxiliary.vision` | `{ … }` |  |
| 861 | `auxiliary.vision.provider` | `'auto'` | auto \| openrouter \| nous \| codex \| custom |
| 862 | `auxiliary.vision.model` | `''` | e.g. "google/gemini-2.5-flash", "gpt-4o" |
| 863 | `auxiliary.vision.base_url` | `''` | direct OpenAI-compatible endpoint (takes precedence over provider) |
| 864 | `auxiliary.vision.api_key` | `''` | API key for base_url (falls back to OPENAI_API_KEY) |
| 865 | `auxiliary.vision.timeout` | `120` | seconds — LLM API call timeout; vision payloads need generous timeout |
| 866 | `auxiliary.vision.extra_body` | `{}` | OpenAI-compatible provider-specific request fields |
| 867 | `auxiliary.vision.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 868 | `auxiliary.vision.download_timeout` | `30` | seconds — image HTTP download timeout; increase for slow connections |
| 870 | `auxiliary.web_extract` | `{ … }` |  |
| 871 | `auxiliary.web_extract.provider` | `'auto'` |  |
| 872 | `auxiliary.web_extract.model` | `''` |  |
| 873 | `auxiliary.web_extract.base_url` | `''` |  |
| 874 | `auxiliary.web_extract.api_key` | `''` |  |
| 875 | `auxiliary.web_extract.timeout` | `360` | seconds (6min) — per-attempt LLM summarization timeout; increase for slow local models |
| 876 | `auxiliary.web_extract.extra_body` | `{}` |  |
| 877 | `auxiliary.web_extract.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 879 | `auxiliary.compression` | `{ … }` |  |
| 880 | `auxiliary.compression.provider` | `'auto'` |  |
| 881 | `auxiliary.compression.model` | `''` |  |
| 882 | `auxiliary.compression.base_url` | `''` |  |
| 883 | `auxiliary.compression.api_key` | `''` |  |
| 884 | `auxiliary.compression.timeout` | `120` | seconds — compression summarises large contexts; increase for local models |
| 885 | `auxiliary.compression.extra_body` | `{}` |  |
| 886 | `auxiliary.compression.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 892 | `auxiliary.skills_hub` | `{ … }` | Note: session_search no longer uses an auxiliary LLM (PR #27590 — single-shape tool returns DB content directly). The old ``auxiliary.session_search.*`` block was removed here. Existing values in user config.yaml files are harmless leftovers and ignored. |
| 893 | `auxiliary.skills_hub.provider` | `'auto'` |  |
| 894 | `auxiliary.skills_hub.model` | `''` |  |
| 895 | `auxiliary.skills_hub.base_url` | `''` |  |
| 896 | `auxiliary.skills_hub.api_key` | `''` |  |
| 897 | `auxiliary.skills_hub.timeout` | `30` |  |
| 898 | `auxiliary.skills_hub.extra_body` | `{}` |  |
| 899 | `auxiliary.skills_hub.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 901 | `auxiliary.approval` | `{ … }` |  |
| 902 | `auxiliary.approval.provider` | `'auto'` |  |
| 903 | `auxiliary.approval.model` | `''` | fast/cheap model recommended (e.g. gemini-flash, haiku) |
| 904 | `auxiliary.approval.base_url` | `''` |  |
| 905 | `auxiliary.approval.api_key` | `''` |  |
| 906 | `auxiliary.approval.timeout` | `30` |  |
| 907 | `auxiliary.approval.extra_body` | `{}` |  |
| 908 | `auxiliary.approval.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 910 | `auxiliary.mcp` | `{ … }` |  |
| 911 | `auxiliary.mcp.provider` | `'auto'` |  |
| 912 | `auxiliary.mcp.model` | `''` |  |
| 913 | `auxiliary.mcp.base_url` | `''` |  |
| 914 | `auxiliary.mcp.api_key` | `''` |  |
| 915 | `auxiliary.mcp.timeout` | `30` |  |
| 916 | `auxiliary.mcp.extra_body` | `{}` |  |
| 917 | `auxiliary.mcp.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 919 | `auxiliary.title_generation` | `{ … }` |  |
| 920 | `auxiliary.title_generation.enabled` | `True` |  |
| 921 | `auxiliary.title_generation.provider` | `'auto'` |  |
| 922 | `auxiliary.title_generation.model` | `''` |  |
| 923 | `auxiliary.title_generation.base_url` | `''` |  |
| 924 | `auxiliary.title_generation.api_key` | `''` |  |
| 925 | `auxiliary.title_generation.timeout` | `30` |  |
| 926 | `auxiliary.title_generation.extra_body` | `{}` |  |
| 927 | `auxiliary.title_generation.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 928 | `auxiliary.title_generation.language` | `''` |  |
| 930 | `auxiliary.memory_query_rewrite` | `{ … }` |  |
| 931 | `auxiliary.memory_query_rewrite.provider` | `'auto'` |  |
| 932 | `auxiliary.memory_query_rewrite.model` | `''` |  |
| 933 | `auxiliary.memory_query_rewrite.base_url` | `''` |  |
| 934 | `auxiliary.memory_query_rewrite.api_key` | `''` |  |
| 935 | `auxiliary.memory_query_rewrite.timeout` | `8` |  |
| 936 | `auxiliary.memory_query_rewrite.extra_body` | `{}` |  |
| 938 | `auxiliary.tts_audio_tags` | `{ … }` |  |
| 939 | `auxiliary.tts_audio_tags.provider` | `'auto'` |  |
| 940 | `auxiliary.tts_audio_tags.model` | `''` |  |
| 941 | `auxiliary.tts_audio_tags.base_url` | `''` |  |
| 942 | `auxiliary.tts_audio_tags.api_key` | `''` |  |
| 943 | `auxiliary.tts_audio_tags.timeout` | `30` |  |
| 944 | `auxiliary.tts_audio_tags.extra_body` | `{}` |  |
| 945 | `auxiliary.tts_audio_tags.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 952 | `auxiliary.triage_specifier` | `{ … }` | Triage specifier — flesh out a rough one-liner in the Kanban Triage column into a concrete spec, then promote it to ``todo``. Invoked by ``hermes kanban specify`` (single id or --all). Set a cheap, capable model here (gemini-flash works well); the main model is overkill for short spec expansion. |
| 953 | `auxiliary.triage_specifier.provider` | `'auto'` |  |
| 954 | `auxiliary.triage_specifier.model` | `''` |  |
| 955 | `auxiliary.triage_specifier.base_url` | `''` |  |
| 956 | `auxiliary.triage_specifier.api_key` | `''` |  |
| 957 | `auxiliary.triage_specifier.timeout` | `120` |  |
| 958 | `auxiliary.triage_specifier.extra_body` | `{}` |  |
| 959 | `auxiliary.triage_specifier.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 966 | `auxiliary.kanban_decomposer` | `{ … }` | Kanban decomposer — decomposes a triage task into a graph of child tasks routed to specialist profiles by description. Invoked by ``hermes kanban decompose`` and the kanban auto-decompose dispatcher tick. Returns a JSON task graph; uses more tokens than the specifier so allow more headroom. |
| 967 | `auxiliary.kanban_decomposer.provider` | `'auto'` |  |
| 968 | `auxiliary.kanban_decomposer.model` | `''` |  |
| 969 | `auxiliary.kanban_decomposer.base_url` | `''` |  |
| 970 | `auxiliary.kanban_decomposer.api_key` | `''` |  |
| 971 | `auxiliary.kanban_decomposer.timeout` | `180` |  |
| 972 | `auxiliary.kanban_decomposer.extra_body` | `{}` |  |
| 973 | `auxiliary.kanban_decomposer.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 979 | `auxiliary.profile_describer` | `{ … }` | Profile describer — auto-generates a 1-2 sentence description of what a profile is good at. Invoked by ``hermes profile describe <name> --auto`` and the dashboard's auto-generate button. Short, cheap call. |
| 980 | `auxiliary.profile_describer.provider` | `'auto'` |  |
| 981 | `auxiliary.profile_describer.model` | `''` |  |
| 982 | `auxiliary.profile_describer.base_url` | `''` |  |
| 983 | `auxiliary.profile_describer.api_key` | `''` |  |
| 984 | `auxiliary.profile_describer.timeout` | `60` |  |
| 985 | `auxiliary.profile_describer.extra_body` | `{}` |  |
| 986 | `auxiliary.profile_describer.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 991 | `auxiliary.goal_judge` | `{ … }` | Goal judge — evaluates whether a /goal run's latest response satisfies the goal/contract, and drafts goal contracts. Short structured-JSON calls; a fast cheap model is fine. |
| 992 | `auxiliary.goal_judge.provider` | `'auto'` |  |
| 993 | `auxiliary.goal_judge.model` | `''` |  |
| 994 | `auxiliary.goal_judge.base_url` | `''` |  |
| 995 | `auxiliary.goal_judge.api_key` | `''` |  |
| 996 | `auxiliary.goal_judge.timeout` | `60` |  |
| 997 | `auxiliary.goal_judge.extra_body` | `{}` |  |
| 998 | `auxiliary.goal_judge.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 1005 | `auxiliary.curator` | `{ … }` | Curator — skill-usage review fork. Timeout is generous because the review pass can take several minutes on reasoning models (umbrella building over hundreds of candidate skills). "auto" = use main chat model; override via `hermes model` → auxiliary → Curator to route to a cheaper aux model (e.g. openrouter google/gemini-3-flash-preview). |
| 1006 | `auxiliary.curator.provider` | `'auto'` |  |
| 1007 | `auxiliary.curator.model` | `''` |  |
| 1008 | `auxiliary.curator.base_url` | `''` |  |
| 1009 | `auxiliary.curator.api_key` | `''` |  |
| 1010 | `auxiliary.curator.timeout` | `600` |  |
| 1011 | `auxiliary.curator.extra_body` | `{}` |  |
| 1012 | `auxiliary.curator.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 1020 | `auxiliary.monitor` | `{ … }` | Monitor — urgency/importance classifier used by the important-mail monitor catalog automation (cron/scripts/classify_items.py). Scores candidate items 0-10 against the user's criteria so only above- threshold items get delivered. "auto" = main chat model; override to a cheap fast model (e.g. openrouter google/gemini-3-flash-preview, haiku) since per-item scoring is high-volume and a small model is fine. |
| 1021 | `auxiliary.monitor.provider` | `'auto'` |  |
| 1022 | `auxiliary.monitor.model` | `''` |  |
| 1023 | `auxiliary.monitor.base_url` | `''` |  |
| 1024 | `auxiliary.monitor.api_key` | `''` |  |
| 1025 | `auxiliary.monitor.timeout` | `60` |  |
| 1026 | `auxiliary.monitor.extra_body` | `{}` |  |
| 1027 | `auxiliary.monitor.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 1040 | `auxiliary.background_review` | `{ … }` | Background review — the post-turn self-improvement fork that decides whether to save a memory / patch a skill. "auto" (default) = run on the main chat model, replaying the full conversation, which is already warm in the prompt cache (cheap cache reads) — unchanged, optimal. Set provider/model to a cheaper model (e.g. openrouter google/gemini-3-flash-preview) to run the review there for ~3-5x lower cost. A different m … |
| 1041 | `auxiliary.background_review.provider` | `'auto'` |  |
| 1042 | `auxiliary.background_review.model` | `''` |  |
| 1043 | `auxiliary.background_review.base_url` | `''` |  |
| 1044 | `auxiliary.background_review.api_key` | `''` |  |
| 1045 | `auxiliary.background_review.timeout` | `120` |  |
| 1046 | `auxiliary.background_review.extra_body` | `{}` |  |
| 1047 | `auxiliary.background_review.reasoning_effort` | `''` | per-task thinking level: none\|minimal\|low\|medium\|high\|xhigh\|max\|ultra (empty = provider default) |
| 1049 | `auxiliary.moa_reference` | `{ … }` |  |
| 1050 | `auxiliary.moa_reference.provider` | `'auto'` |  |
| 1051 | `auxiliary.moa_reference.model` | `''` |  |
| 1052 | `auxiliary.moa_reference.base_url` | `''` |  |
| 1053 | `auxiliary.moa_reference.api_key` | `''` |  |
| 1054 | `auxiliary.moa_reference.timeout` | `900` |  |
| 1055 | `auxiliary.moa_reference.extra_body` | `{}` |  |
| 1061 | `auxiliary.moa_aggregator` | `{ … }` |  |
| 1062 | `auxiliary.moa_aggregator.provider` | `'auto'` |  |
| 1063 | `auxiliary.moa_aggregator.model` | `''` |  |
| 1064 | `auxiliary.moa_aggregator.base_url` | `''` |  |
| 1065 | `auxiliary.moa_aggregator.api_key` | `''` |  |
| 1066 | `auxiliary.moa_aggregator.timeout` | `900` |  |
| 1067 | `auxiliary.moa_aggregator.extra_body` | `{}` |  |
| 1072 | `display` | `{ … }` |  |
| 1073 | `display.compact` | `False` |  |
| 1074 | `display.personality` | `''` |  |
| 1075 | `display.resume_display` | `'full'` |  |
| 1079 | `display.resume_exchanges` | `10` | max user+assistant pairs to show |
| 1080 | `display.resume_max_user_chars` | `300` | truncate user message text |
| 1081 | `display.resume_max_assistant_chars` | `200` | truncate non-last assistant text |
| 1082 | `display.resume_max_assistant_lines` | `3` | truncate non-last assistant lines |
| 1088 | `display.resume_skip_tool_only` | `True` | When True (default), assistant entries that are *only* tool calls (no visible text) are skipped in the recap. This prevents the recap from being dominated by `[2 tool calls: terminal, read_file]` lines when an exchange was tool-heavy. Set False to restore the legacy behavior of showing tool-call summaries inline. |
| 1089 | `display.busy_input_mode` | `'interrupt'` | interrupt \| queue \| steer |
| 1093 | `display.busy_steer_ack_enabled` | `True` | When busy_input_mode="steer", suppress only the visible "Steered into current run" confirmation bubble by setting this false. The mid-turn steering itself still happens. |
| 1099 | `display.interface` | `'cli'` | Which interface bare `hermes` (and `hermes chat`) launches by default: "cli" — the classic prompt_toolkit REPL (default, preserves prior behavior) "tui" — the modern Ink TUI (same as passing `--tui`) Explicit flags always win over this setting: `--cli` forces the classic REPL and `--tui` (or HERMES_TUI=1) forces the TUI regardless of config. |
| 1104 | `display.tui_auto_resume_recent` | `False` | When true, `hermes --tui` auto-resumes the most recent human- facing session on launch instead of forging a fresh one. Mirrors `hermes -c` muscle memory. Default off so existing users aren't surprised. HERMES_TUI_RESUME=<id> always wins. |
| 1109 | `display.tui_agents_nudge` | `True` | When true (default), `hermes --tui` drops a one-time hint ("subagents working · /agents to watch live") the first time a turn starts delegating, nudging the user toward the live spawn-tree dashboard. Set false to suppress the hint. |
| 1110 | `display.bell_on_complete` | `False` |  |
| 1115 | `display.show_reasoning` | `True` | Stream the model's reasoning/thinking live before the response. Default ON: on thinking models the reasoning phase can run tens of seconds, and with this off the user stares at a spinner the whole time even though tokens are streaming. Set false for quiet output. |
| 1119 | `display.reasoning_full` | `False` | When reasoning display is on, the post-response "Reasoning" recap box collapses long thinking to the first 10 lines. Set true to print the complete thinking text uncollapsed (live streaming is always full). |
| 1125 | `display.memory_notifications` | `'on'` | Background self-improvement review notifications surfaced in chat. "off" — no chat notification (the review still runs and writes) "on" — generic "💾 Memory updated" line (default) "verbose" — include a compact content preview of what changed Per-platform overrides via display.platforms.<platform>.memory_notifications. |
| 1126 | `display.streaming` | `False` |  |
| 1127 | `display.timestamps` | `False` | Show timestamp on user and assistant labels |
| 1128 | `display.timestamp_format` | `'%H:%M'` | strftime format for timestamps (e.g. "%b-%d %H:%M") |
| 1129 | `display.final_response_markdown` | `'strip'` | render \| strip \| raw |
| 1133 | `display.persistent_output` | `True` | Preserve recent classic CLI output across Ctrl+L, /redraw, and terminal resize full-screen clears. Disable if a terminal emulator behaves badly with replayed scrollback. |
| 1134 | `display.persistent_output_max_lines` | `200` |  |
| 1138 | `display.persist_prompts` | `True` | Print a one-line summary of resolved modal prompts (approval / clarify) into scrollback so the question and decision survive the panel repaint. Set false to keep scrollback untouched. |
| 1139 | `display.inline_diffs` | `True` | Show inline diff previews for write actions (write_file, patch, skill_manage) |
| 1147 | `display.file_mutation_verifier` | `True` | File-mutation verifier footer. When true (default), the agent appends a one-line advisory to its final response whenever a write_file / patch call failed during the turn and was never superseded by a successful write to the same path. This catches the "batch of parallel patches, half fail, model claims success" class of over-claim that otherwise forces users to run `git status` to verify edits landed. Set false to su … |
| 1152 | `display.credits_notices` | `True` | Nous credits status-bar notices (usage bands, grant-spent, depleted / restored). When false, no credits notices are emitted — balance data is still captured and /usage keeps working. Off switch for sub + top-up users who find the gauge noisy. |
| 1159 | `display.turn_completion_explainer` | `True` | Turn-completion explainer. When true (default), the agent appends a one-line explanation to its final response whenever a turn ends abnormally with no usable reply — empty content after retries, a partial/truncated stream, a still-pending tool result, or an iteration/budget limit. Replaces the bare "(empty)" sentinel so the failure isn't silent from the UI's perspective. Set false to suppress. |
| 1160 | `display.show_cost` | `False` | Show $ cost in the status bar (off by default) |
| 1163 | `display.battery` | `False` | Show a color-coded battery read-out as the first status-bar element in the CLI/TUI (off by default). No-op on machines without a battery. |
| 1170 | `display.focus_view` | `False` | Focus view (/focus): display-only reduced-output mode. When true the CLI/TUI pins tool_progress to "off" (reusing the existing suppression path), reports a per-turn hidden-line count with a recovery hint, and pins a "focus" segment in the status bar. focus_saved_tool_progress holds the mode /focus off restores. Never affects what is sent to the model — see hermes_cli/focus_view.py. |
| 1171 | `display.focus_saved_tool_progress` | `'all'` |  |
| 1172 | `display.skin` | `'default'` |  |
| 1177 | `display.language` | `'en'` | UI language for static user-facing messages (approval prompts, a handful of gateway slash-command replies). Does NOT affect agent responses, log lines, tool outputs, or slash-command descriptions. Supported: en, zh, ja, de, es, fr, tr, uk. Unknown values fall back to en. |
| 1180 | `display.tui_status_indicator` | `'kaomoji'` | TUI busy indicator style: kaomoji (default), emoji, unicode (braille spinner), or ascii. Live-swappable via `/indicator <style>`. |
| 1188 | `display.cli_refresh_interval` | `1.0` | Seconds between prompt_toolkit redraws in the classic CLI when idle. Default 1.0 keeps the wall-clock status-bar read-outs (idle-since- last-turn) ticking and keeps the bottom chrome alive during idle — without it prompt_toolkit stops repainting the status bar after a turn and it can go stale/disappear (#45592). Set 0 to disable the background refresh if it fights terminal auto-scroll in non-fullscreen mode on some e … |
| 1189 | `display.user_message_preview` | `{ … }` | CLI: how many submitted user-message lines to echo back in scrollback |
| 1190 | `display.user_message_preview.first_lines` | `2` |  |
| 1191 | `display.user_message_preview.last_lines` | `2` |  |
| 1193 | `display.interim_assistant_messages` | `True` | Gateway: send natural mid-turn assistant status messages. Desktop: keep mid-turn narration between tool calls instead of collapsing to the final message. |
| 1199 | `display.show_commentary` | `True` | Codex Responses models narrate progress in a dedicated commentary channel. When true (default), completed commentary messages are delivered as visible mid-turn updates via the interim message path. When false, commentary falls back to the reasoning channel and is only visible when show_reasoning is enabled. |
| 1200 | `display.tool_progress_command` | `False` | Enable /verbose command in messaging gateway |
| 1205 | `display.tool_preview_length` | `0` | Max chars for tool call previews (0 = no limit, show full paths/commands) |
| 1210 | `display.friendly_tool_labels` | `True` | Human-phrased tool status labels for built-in tools: "Searching the web for ...", "Reading <file>", "Browsing <url>" instead of the raw tool name. Applies to CLI spinner + gateway/desktop tool-progress. Custom/plugin/MCP tools always fall back to the raw preview. |
| 1216 | `display.turn_summary` | `True` | CLI-only post-turn accounting line printed after each interactive turn: "⋯ 12.4s · edited 2 files +18 -3 · read 4 files · ran 3 commands". Observed from the tool-progress feed the CLI already receives; never printed in quiet/non-interactive paths or in gateway/messaging surfaces (those have their own runtime footer). |
| 1220 | `display.spinner_token_flow` | `True` | CLI-only: append cumulative turn output tokens to the live spinner timer ("⚡ Reading file ( 2.3s · ↓ 1.2k tok)"). Updates as each API call in the turn reports usage. |
| 1226 | `display.tool_progress_grouping` | `'accumulate'` | How gateway tool-progress is grouped on platforms that support message editing: "accumulate" (default) edits one bubble in place; "separate" sends one message per tool (the pre-v0.9 behavior, noisier). Only applies where tool_progress is already enabled. Per-platform override via display.platforms.<platform>.tool_progress_grouping. |
| 1235 | `display.status_phrases` | `{}` | Optional custom phrases for generic long-running status messages. Built-in defaults live in gateway/assets/status_phrases.yaml. Users can set `path`/`paths` to HERMES_HOME-relative YAML files/directories (or rely on conventional status_phrases.yaml / status_phrases/*.yaml). Keys: status, generic. Use mode: "append" (default) to add phrases, or "replace" to fully replace configured surfaces. Per-platform overrides liv … |
| 1241 | `display.reasoning_style` | `'code'` | How a reasoning/thinking summary renders when show_reasoning is on. "code" (default) = 💭 fenced code block; "blockquote" = "> " lines; "subtext" = "-# " lines (Discord small grey metadata text). Discord defaults to "subtext"; override per-platform via display.platforms.<platform>.reasoning_style. |
| 1249 | `display.ephemeral_system_ttl` | `0` | Auto-delete system-notice replies (e.g. "✨ New session started!", "♻ Restarting gateway…", "⚡ Stopped…") after N seconds on platforms that support message deletion (currently Telegram; other platforms ignore and leave the message in place). Only affects slash-command replies wrapped with gateway.platforms.base.EphemeralReply — agent responses and content messages are never touched. Default 0 (disabled) preserves prio … |
| 1267 | `display.platforms` | `{ … }` | Per-platform display/streaming overrides. Each key is a gateway platform ("telegram", "discord", "slack", …) mapping to a dict of display settings that override the global value for that platform only. A setting left unset here falls through to the global default. Shipped defaults encode the streaming experience that works best per platform: - Telegram has native animated draft streaming (sendMessageDraft), which is … |
| 1268 | `display.platforms.telegram` | `{ … }` |  |
| 1268 | `display.platforms.telegram.streaming` | `True` |  |
| 1269 | `display.platforms.discord` | `{ … }` |  |
| 1269 | `display.platforms.discord.streaming` | `False` |  |
| 1270 | `display.platforms.slack` | `{ … }` |  |
| 1270 | `display.platforms.slack.streaming` | `False` |  |
| 1276 | `display.runtime_footer` | `{ … }` | Gateway runtime-metadata footer appended to the FINAL message of a turn (disabled by default to keep replies minimal). When enabled, renders e.g. `model · 68% · ~/projects/hermes`. Per-platform overrides go under display.platforms.<platform>.runtime_footer. |
| 1277 | `display.runtime_footer.enabled` | `False` |  |
| 1278 | `display.runtime_footer.fields` | `['model', 'context_pct', 'cwd']` | Order shown; drop any to hide |
| 1280 | `display.copy_shortcut` | `'auto'` | "auto" (platform default) \| "ctrl_c" \| "ctrl_shift_c" \| "disabled" |
| 1286 | `display.pet` | `{ … }` | Petdex animated mascot (https://github.com/crafter-station/petdex). A purely cosmetic sprite that reacts to agent activity across the CLI, TUI, and desktop app. Manage with `hermes pets`. Disabled until a pet is installed + selected (no effect on prompt caching — this is a display concern only). |
| 1287 | `display.pet.enabled` | `False` |  |
| 1290 | `display.pet.slug` | `''` | Active pet slug; resolved against installed pets in get_hermes_home()/pets/. Empty → first installed pet. |
| 1294 | `display.pet.render_mode` | `'auto'` | Terminal render protocol for CLI/TUI: auto — detect kitty/iTerm2/sixel, else unicode half-blocks kitty \| iterm \| sixel \| unicode \| off |
| 1300 | `display.pet.scale` | `0.33` | Master size scalar (relative to native 192×208 frames). One knob shrinks every surface: the desktop canvas scales its pixels by it and the CLI/TUI derive their terminal column width from it. The half-block fallback clamps to a legibility floor (it can't shrink as far as true-pixel kitty/GUI without turning to mush). |
| 1304 | `display.pet.unicode_cols` | `0` | Hard override for terminal column width. 0 = auto (derive from scale); set a positive int only to pin the half-block/kitty width independently of scale. |
| 1309 | `dashboard` | `{ … }` | Web dashboard settings |
| 1310 | `dashboard.theme` | `'default'` | Dashboard visual theme: "default", "midnight", "ember", "mono", "cyberpunk", "rose" |
| 1313 | `dashboard.turn_isolation` | `False` | Process-isolation rollout controls. Runtime reads these through the raw config loader, so tui_gateway.server also owns explicit defaults. |
| 1314 | `dashboard.compute_host_heartbeat_secs` | `15` |  |
| 1315 | `dashboard.compute_host_respawn_max` | `3` |  |
| 1330 | `dashboard.show_token_analytics` | `False` | Hide the token/cost analytics surfaces (Analytics page, token bars and cost figures on the Models page) by default. The numbers shown there are a local debug estimate: they only count successful main-agent responses with a usable ``response.usage``, and silently exclude every auxiliary call (context compression, title generation, vision, session search, web extract, smart approval, MCP routing, plugin LLM access) plu … |
| 1344 | `dashboard.oauth` | `{ … }` | OAuth gate configuration (engaged when ``--host`` is set and ``--insecure`` is not). The bundled Nous Portal plugin reads both keys at startup; they are the canonical surface for these settings. Each can be overridden by an environment variable — ``HERMES_DASHBOARD_OAUTH_CLIENT_ID`` and ``HERMES_DASHBOARD_PORTAL_URL`` respectively — and the env var wins when set to a non-empty value. The override path is what Fly.io' … |
| 1345 | `dashboard.oauth.client_id` | `''` | agent:{instance_id} — Portal provisions this |
| 1346 | `dashboard.oauth.portal_url` | `''` | blank → use plugin default (production Portal) |
| 1369 | `dashboard.basic_auth` | `{ … }` | Username/password gate configuration — read by the bundled ``dashboard_auth/basic`` plugin (a self-hosted "just put a password on my dashboard" provider that needs no OAuth IDP). The plugin registers a password provider when ``username`` plus either ``password_hash`` (preferred — no plaintext at rest) or ``password`` (plaintext, hashed in-memory at load) are set. Each key is overridable by an env var (``HERMES_DASHBO … |
| 1370 | `dashboard.basic_auth.username` | `''` | blank → plugin no-op (no password provider) |
| 1371 | `dashboard.basic_auth.password_hash` | `''` | scrypt$... (preferred — no plaintext at rest) |
| 1372 | `dashboard.basic_auth.password` | `''` | plaintext fallback (hashed in-memory at load) |
| 1373 | `dashboard.basic_auth.secret` | `''` | token-signing key; blank → random per-process |
| 1374 | `dashboard.basic_auth.session_ttl_seconds` | `0` | 0 → plugin default (12h) |
| 1388 | `dashboard.drain_auth` | `{ … }` | Drain-control service-credential configuration — read by the bundled ``dashboard_auth/drain`` plugin (the first consumer of the generic non-interactive token-auth capability). The SECRET itself is a credential and is NOT configured here: it is provisioned by nous-account-service at deploy time via the ``HERMES_DASHBOARD_DRAIN_SECRET`` env var (the .env-is-for-secrets rule). These are the behavioural knobs only. The p … |
| 1389 | `dashboard.drain_auth.scope` | `'drain'` |  |
| 1390 | `dashboard.drain_auth.min_secret_chars` | `43` |  |
| 1412 | `dashboard.public_url` | `''` | Public URL override (env: ``HERMES_DASHBOARD_PUBLIC_URL``). When set, this is the complete authority — scheme + host + optional path prefix (e.g. ``https://example.com/hermes``) — the OAuth ``redirect_uri`` is built from. Set this for deploys behind reverse proxies that don't reliably forward ``X-Forwarded-Host`` / ``X-Forwarded-Proto`` / ``X-Forwarded-Prefix`` (manual nginx setups, on-prem ingresses, custom-domain F … |
| 1416 | `privacy` | `{ … }` | Privacy settings |
| 1417 | `privacy.redact_pii` | `False` | When True, hash user IDs and strip phone numbers from LLM context |
| 1425 | `tts` | `{ … }` | Text-to-speech configuration Each provider supports an optional `max_text_length:` override for the per-request input-character cap. Omit it to use the provider's documented limit (OpenAI 4096, xAI 15000, MiniMax 10000, ElevenLabs 5k-40k model-aware, Gemini 32000, Edge 5000, Mistral 4000, NeuTTS/KittenTTS 2000). |
| 1428 | `tts.provider` | `'edge'` | Set explicitly to pin a backend: "edge" (free) \| "elevenlabs" (premium) \| "openai" \| "xai" \| "minimax" \| "mistral" \| "gemini" \| "deepinfra" \| "neutts" (local) \| "kittentts" (local) \| "piper" (local) |
| 1429 | `tts.edge` | `{ … }` |  |
| 1430 | `tts.edge.voice` | `'en-US-AriaNeural'` |  |
| 1433 | `tts.elevenlabs` | `{ … }` |  |
| 1434 | `tts.elevenlabs.voice_id` | `'pNInz6obpgDQGcFmaJgB'` | Adam |
| 1435 | `tts.elevenlabs.model_id` | `'eleven_multilingual_v2'` |  |
| 1437 | `tts.openai` | `{ … }` |  |
| 1438 | `tts.openai.model` | `'gpt-4o-mini-tts'` |  |
| 1439 | `tts.openai.voice` | `'alloy'` |  |
| 1444 | `tts.gemini` | `{ … }` |  |
| 1445 | `tts.gemini.model` | `'gemini-2.5-flash-preview-tts'` |  |
| 1446 | `tts.gemini.voice` | `'Kore'` |  |
| 1450 | `tts.gemini.audio_tags` | `False` | When true, Gemini 3.1 TTS uses a hidden auxiliary-model rewrite pass to insert freeform square-bracket audio tags into the TTS script. Visible chat replies are unchanged. |
| 1455 | `tts.gemini.persona_prompt_file` | `''` | Optional local Markdown/text file with Gemini TTS performance direction. It may include AUDIO PROFILE, SCENE, DIRECTOR'S NOTES, SAMPLE CONTEXT, and either a `{transcript}` placeholder or no transcript section; Hermes appends the live transcript when absent. |
| 1457 | `tts.xai` | `{ … }` |  |
| 1458 | `tts.xai.voice_id` | `'eve'` | or custom voice ID — see https://docs.x.ai/developers/model-capabilities/audio/custom-voices |
| 1459 | `tts.xai.language` | `'en'` | BCP-47 code ("en", "pt-BR") or "auto" |
| 1460 | `tts.xai.speed` | `1.0` | 0.7–1.5, playback speed |
| 1461 | `tts.xai.auto_speech_tags` | `False` | insert expressive audio tags via LLM rewrite |
| 1462 | `tts.xai.optimize_streaming_latency` | `0` | 0–2, trades quality for lower latency |
| 1463 | `tts.xai.sample_rate` | `24000` | 22050 / 24000 / 44100 / 48000 |
| 1464 | `tts.xai.bit_rate` | `128000` | MP3 bitrate; only applies when codec=mp3 |
| 1466 | `tts.mistral` | `{ … }` |  |
| 1467 | `tts.mistral.model` | `'voxtral-mini-tts-2603'` |  |
| 1468 | `tts.mistral.voice_id` | `'c69964a6-ab8b-4f8a-9465-ec0925096ec8'` | Paul - Neutral |
| 1470 | `tts.minimax` | `{ … }` |  |
| 1471 | `tts.minimax.model` | `'speech-02-hd'` |  |
| 1472 | `tts.minimax.voice_id` | `'English_expressive_narrator'` |  |
| 1474 | `tts.kittentts` | `{ … }` |  |
| 1475 | `tts.kittentts.model` | `'KittenML/kitten-tts-nano-0.8-int8'` | nano 25MB; micro 41MB; mini 80MB |
| 1476 | `tts.kittentts.voice` | `'Jasper'` |  |
| 1478 | `tts.neutts` | `{ … }` |  |
| 1479 | `tts.neutts.ref_audio` | `''` | Path to reference voice audio (empty = bundled default) |
| 1480 | `tts.neutts.ref_text` | `''` | Path to reference voice transcript (empty = bundled default) |
| 1481 | `tts.neutts.model` | `'neuphonic/neutts-air-q4-gguf'` | HuggingFace model repo |
| 1482 | `tts.neutts.device` | `'cpu'` | cpu, cuda, or mps |
| 1484 | `tts.piper` | `{ … }` |  |
| 1488 | `tts.piper.voice` | `'en_US-lessac-medium'` | Voice name (e.g. "en_US-lessac-medium") downloaded on first use, OR an absolute path to a pre-downloaded .onnx file. Full voice list: https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md |
| 1497 | `tts.deepinfra` | `{ … }` |  |
| 1498 | `tts.deepinfra.model` | `''` | empty = first tts-tagged model from the live catalog |
| 1499 | `tts.deepinfra.voice` | `'default'` |  |
| 1504 | `stt` | `{ … }` |  |
| 1505 | `stt.enabled` | `True` |  |
| 1509 | `stt.echo_transcripts` | `True` | When true, gateway voice messages are transcribed for the agent and the raw transcript is also echoed back to the user as a 🎙️ message. Set false to keep STT for the agent while suppressing that user-facing echo. |
| 1510 | `stt.provider` | `'local'` | "local" (free, faster-whisper) \| "groq" \| "openai" (Whisper API) \| "mistral" (Voxtral Transcribe) \| "elevenlabs" (Scribe) \| "deepinfra" |
| 1516 | `stt.language` | `'en'` | Global language hint applied to EVERY provider unless a per-provider language overrides it. Defaults to "en" — Whisper auto-detection frequently misidentifies short/accented clips, which reads as "STT transcribed the wrong language". Set to "" to restore auto-detect, or to your language code ("es", "zh", "uk", ...). |
| 1517 | `stt.local` | `{ … }` |  |
| 1518 | `stt.local.model` | `'base'` | tiny, base, small, medium, large-v3 |
| 1519 | `stt.local.language` | `''` | auto-detect by default; set to "en", "es", "fr", etc. to force |
| 1520 | `stt.local.initial_prompt` | `''` |  |
| 1523 | `stt.local.vad` | `True` | Silero VAD filter — silence never reaches whisper. false = old raw behavior (music/ambient). |
| 1524 | `stt.local.vad_min_silence_ms` | `500` | min silence (ms) that splits speech chunks when vad is on |
| 1525 | `stt.local.no_speech_prob_threshold` | `0.6` | drop a segment only if no_speech_prob is ABOVE this... |
| 1526 | `stt.local.logprob_threshold` | `-1.0` | ...AND its avg_logprob is BELOW this (both must hit) |
| 1528 | `stt.groq` | `{ … }` |  |
| 1529 | `stt.groq.model` | `'whisper-large-v3-turbo'` | whisper-large-v3, whisper-large-v3-turbo, distil-whisper-large-v3-en |
| 1530 | `stt.groq.language` | `''` | auto-detect by default; set to "en", "es", "fr", etc. to force |
| 1532 | `stt.openai` | `{ … }` |  |
| 1533 | `stt.openai.model` | `'whisper-1'` | whisper-1, gpt-4o-mini-transcribe, gpt-4o-transcribe, gpt-transcribe |
| 1534 | `stt.openai.language` | `''` | auto-detect by default; set to "en", "es", "fr", etc. to force |
| 1536 | `stt.mistral` | `{ … }` |  |
| 1537 | `stt.mistral.model` | `'voxtral-mini-latest'` | voxtral-mini-latest, voxtral-mini-2602 |
| 1538 | `stt.mistral.language` | `''` | auto-detect by default; set to "en", "es", "fr", etc. to force |
| 1540 | `stt.xai` | `{ … }` |  |
| 1541 | `stt.xai.language` | `''` | auto-detect by default; set to "en", "es", "fr", etc. to force |
| 1543 | `stt.elevenlabs` | `{ … }` |  |
| 1544 | `stt.elevenlabs.model_id` | `'scribe_v2'` | scribe_v2, scribe_v1 |
| 1545 | `stt.elevenlabs.language_code` | `''` | auto-detect by default; set to "eng", "spa", "fra", etc. to force |
| 1546 | `stt.elevenlabs.tag_audio_events` | `False` |  |
| 1547 | `stt.elevenlabs.diarize` | `False` |  |
| 1549 | `stt.deepinfra` | `{ … }` |  |
| 1550 | `stt.deepinfra.model` | `''` | empty = first stt-tagged model from the live catalog |
| 1555 | `voice` | `{ … }` |  |
| 1556 | `voice.record_key` | `'ctrl+b'` |  |
| 1557 | `voice.max_recording_seconds` | `120` |  |
| 1558 | `voice.auto_tts` | `False` |  |
| 1559 | `voice.beep_enabled` | `True` | Play record start/stop beeps in CLI voice mode |
| 1560 | `voice.beep_volume` | `0.3` | Beep amplitude multiplier (0.0-1.0, default keeps prior hardcoded value) |
| 1561 | `voice.thinking_sound` | `True` | Calm ambient bubble sound while the agent works in voice chat (volume follows beep_volume) |
| 1562 | `voice.silence_threshold` | `200` | RMS below this = silence (0-32767) |
| 1563 | `voice.silence_duration` | `3.0` | Seconds of silence before auto-stop |
| 1564 | `voice.barge_in` | `True` | Interrupt the agent / stop TTS when the user starts talking |
| 1565 | `voice.barge_in_grace_seconds` | `0.5` | Trip suppression right after TTS playback starts (onset transient); the mic itself is live for the whole turn |
| 1566 | `voice.barge_in_threshold_multiplier` | `3.0` | Speech trigger = quiet-room floor x this (floor is calibrated BEFORE playback, never against speaker bleed) |
| 1570 | `voice.stop_phrases` | `['stop']` | Saying EXACTLY one of these phrases (and nothing else) ends the voice chat instead of being sent to the agent. Case-insensitive, surrounding punctuation ignored. Set [] to disable. |
| 1576 | `wake_word` | `{ … }` | "Hey Hermes" hands-free wake word. Always-on, on-device hotword detection that starts a fresh voice session — the "Hey Siri" pattern. Off by default; toggle with /wake or `wake_word.enabled: true`. |
| 1577 | `wake_word.enabled` | `False` |  |
| 1578 | `wake_word.surface` | `'auto'` | eligible surface: "auto" (first claimant) \| "cli" \| "tui" \| "gui" |
| 1579 | `wake_word.input_device` | `None` | PortAudio input device index/name; null uses the process default |
| 1580 | `wake_word.capture` | `'auto'` | auto \| local \| client — where PCM is captured (client = desktop streams mic via wake.feed) |
| 1581 | `wake_word.provider` | `'openwakeword'` | "openwakeword" (free, local) \| "sherpa" (free, ANY phrase, no training) \| "porcupine" (premium; needs PORCUPINE_ACCESS_KEY) |
| 1582 | `wake_word.phrase` | `'hey hermes'` | for "sherpa" this IS the detected phrase (any text works); for other engines it's a cosmetic label — detection is keyed by the model/keyword below |
| 1583 | `wake_word.sensitivity` | `0.6` | 0.0-1.0 detection threshold, consistent across engines (higher = stricter, fewer false triggers) |
| 1584 | `wake_word.confirmation_frames` | `3` | openWakeWord only: consecutive over-threshold frames required to fire (higher = fewer false triggers on ambient speech, slightly more latency; 1 = old single-frame behavior) |
| 1585 | `wake_word.start_new_session` | `True` | start a fresh session on wake vs. continue the current one |
| 1586 | `wake_word.profile_routing` | `True` | sherpa only: also listen for every wake-enabled profile's phrase and route the wake to the matching profile |
| 1587 | `wake_word.openwakeword` | `{ … }` |  |
| 1592 | `wake_word.openwakeword.model` | `'hey_hermes'` | "hey_hermes" (the bundled, works-out-of-the-box default) OR a built-in openWakeWord name ("hey_jarvis", "alexa", "hey_mycroft", ...) OR a path to a custom .onnx/.tflite model for another phrase. See the wake-word docs for the custom-model training guide. |
| 1597 | `wake_word.openwakeword.inference_framework` | `''` | "" (auto — tflite on macOS ARM64, onnx elsewhere) \| "onnx" \| "tflite". openWakeWord's onnx backend scores near-zero on macOS ARM64 (dscripka/openWakeWord#336), so auto avoids a listener that arms but never fires. Set explicitly only to override that choice. |
| 1599 | `wake_word.sherpa` | `{ … }` |  |
| 1602 | `wake_word.sherpa.model_dir` | `''` | Optional path to a sherpa-onnx KWS model directory. Empty = auto-download the small English zipformer model on first use. |
| 1604 | `wake_word.porcupine` | `{ … }` |  |
| 1607 | `wake_word.porcupine.keyword` | `'jarvis'` | Built-in keyword ("jarvis", "computer", "bumblebee", ...) or a path to a custom .ppn from the Picovoice Console. |
| 1611 | `human_delay` | `{ … }` |  |
| 1612 | `human_delay.mode` | `'off'` |  |
| 1613 | `human_delay.min_ms` | `800` |  |
| 1614 | `human_delay.max_ms` | `2500` |  |
| 1623 | `context` | `{ … }` | Context engine -- controls how the context window is managed when approaching the model's token limit. "compressor" = built-in lossy summarization (default). Set to a plugin name to activate an alternative engine (e.g. "lcm" for Lossless Context Management). The engine must be installed as a plugin in plugins/context_engine/<name>/ or ~/.hermes/plugins/. |
| 1624 | `context.engine` | `'compressor'` |  |
| 1627 | `context.memory_trim` | `{ … }` | Return freed glibc allocator pages after long-running agent/TUI cleanup boundaries. Unsupported platforms are safe no-ops. |
| 1628 | `context.memory_trim.enabled` | `True` |  |
| 1629 | `context.memory_trim.cooldown_seconds` | `60.0` |  |
| 1632 | `context.memory_trim.log_every_n` | `1` | Successful trim calls are INFO logged every Nth periodic call; force paths always log so process-close behavior is visible. |
| 1635 | `context.memory_trim.info_log_min_delta_mb` | `0.0` | Suppress INFO logs only when a readable RSS change is smaller. 0 reports every successful configured trim. |
| 1640 | `memory` | `{ … }` | Persistent memory -- bounded curated memory injected into system prompt |
| 1641 | `memory.memory_enabled` | `True` |  |
| 1642 | `memory.user_profile_enabled` | `True` |  |
| 1655 | `memory.write_approval` | `False` | Approval gate for memory writes (add/replace/remove), applied to BOTH foreground agent turns and the background self-improvement review fork (the source of unprompted "wrong assumption" saves users reported). false (default) — write freely; the gate is off (pre-gate behaviour) true — require approval: foreground writes prompt inline (entries are small enough to review in a chat bubble); background-review writes are s … |
| 1656 | `memory.memory_char_limit` | `2200` | ~800 tokens at 2.75 chars/token |
| 1657 | `memory.user_char_limit` | `1375` | ~500 tokens at 2.75 chars/token |
| 1662 | `memory.provider` | `''` | External memory provider plugin (empty = built-in only). Set to a provider name to activate: "openviking", "mem0", "hindsight", "holographic", "retaindb", "byterover". Only ONE external provider is allowed at a time. |
| 1669 | `delegation` | `{ … }` | Subagent delegation — override the provider:model used by delegate_task so child agents can run on a different (cheaper/faster) provider and model. Uses the same runtime provider resolution as CLI/gateway startup, so all configured providers (OpenRouter, Nous, Z.ai, Kimi, etc.) are supported. |
| 1670 | `delegation.model` | `''` | e.g. "google/gemini-3-flash-preview" (empty = inherit parent model) |
| 1671 | `delegation.provider` | `''` | e.g. "openrouter" (empty = inherit parent provider + credentials) |
| 1672 | `delegation.base_url` | `''` | direct OpenAI-compatible endpoint for subagents |
| 1673 | `delegation.api_key` | `''` | API key for delegation.base_url (falls back to OPENAI_API_KEY) |
| 1674 | `delegation.api_mode` | `''` | wire protocol for delegation.base_url: "chat_completions", "codex_responses", or "anthropic_messages". Empty = auto-detect from URL (e.g. /anthropic suffix → anthropic_messages). Set this explicitly for non-standard endpoints the heuristic can't detect. |
| 1683 | `delegation.inherit_mcp_toolsets` | `True` | "codex_responses", or "anthropic_messages". Empty = auto-detect from URL (e.g. /anthropic suffix → anthropic_messages). Set this explicitly for non-standard endpoints the heuristic can't detect. When delegate_task narrows child toolsets explicitly, preserve any MCP toolsets the parent already has enabled. On by default so narrowing (e.g. toolsets=["web","browser"]) expresses "I want these extras" without silently str … |
| 1684 | `delegation.max_iterations` | `50` | per-subagent iteration cap (each subagent gets its own budget, independent of the parent's max_iterations) |
| 1700 | `delegation.max_summary_chars` | `24000` | independent of the parent's max_iterations) Subagent summaries return to the parent's context verbatim. A batch fan-out (N children) returns N summaries at once, which can exceed the parent's context window and trigger a compression/429 death spiral. delegate_task sizes each summary against the parent's remaining context headroom (split across the batch); when it must trim, the full text is spilled to ~/.hermes/cache … |
| 1702 | `delegation.child_timeout_seconds` | `0` | optional wall-clock cap per child agent. 0 (default) = no timeout: children fail only from real errors (API, tools, iteration budget), never a delegation stopwatch. Set a positive number of seconds (floor 30s) to enforce a hard cap. |
| 1707 | `delegation.reasoning_effort` | `''` | subagent effort: "ultra", "max", "xhigh", "high", "medium", "low", "minimal", "none" (empty = inherit) |
| 1709 | `delegation.max_concurrent_children` | `3` | unified concurrency cap: max parallel children per batch AND max concurrent background (background=true) delegation units. New async dispatches beyond the cap fall back to synchronous execution. Floor of 1, no ceiling. (Replaces the deprecated max_async_children.) |
| 1717 | `delegation.max_spawn_depth` | `1` | depth (1 = flat [default], 2 = orchestrator→leaf, 3+ = deeper) |
| 1718 | `delegation.orchestrator_enabled` | `True` | kill switch for role="orchestrator" |
| 1727 | `delegation.subagent_auto_approve` | `False` | When a subagent hits a dangerous-command approval prompt, the parent's prompt_toolkit TUI owns stdin — a thread-local input() call from the subagent worker would deadlock the parent UI. To avoid the deadlock, subagent threads ALWAYS resolve approvals non-interactively: false (default) → auto-deny with a logger.warning audit line (safe) true → auto-approve "once" with a logger.warning audit line Flip to true only if y … |
| 1733 | `prefill_messages_file` | `''` | Ephemeral prefill messages file — JSON list of {role, content} dicts injected at the start of every API call for few-shot priming. Never saved to sessions, logs, or trajectories. |
| 1743 | `goals` | `{ … }` | Goals — persistent cross-turn goals (Ralph-style loop). After every turn, a lightweight judge call asks the auxiliary model whether the active /goal is satisfied by the assistant's last response. If not, Hermes feeds a continuation prompt back into the same session and keeps working until the goal is done, the turn budget is exhausted, or the user pauses/clears it. Judge failures fail OPEN (continue) so a flaky judge … |
| 1748 | `goals.max_turns` | `20` | Max continuation turns before Hermes auto-pauses the goal and asks the user to /goal resume. Protects against judge false negatives (goal actually done but judge says continue) and unbounded model spend on fuzzy / unachievable goals. |
| 1754 | `moa` | `{ … }` | Mixture of Agents — named presets used by /moa. A preset is an execution mode around the main model, not a provider/model itself: references + aggregator synthesize private guidance before each main-model iteration. |
| 1755 | `moa.default_preset` | `'default'` |  |
| 1756 | `moa.active_preset` | `''` |  |
| 1763 | `moa.save_traces` | `False` | When true, every MoA turn that runs the reference fan-out writes the FULL turn (each reference's exact input messages + output + usage/cost, and the aggregator's exact input + output) to a JSONL file at <hermes_home>/moa-traces/<session_id>.jsonl. Off by default — turn it on to audit / improve MoA behavior from real runs. Set trace_dir to override the output directory. |
| 1764 | `moa.trace_dir` | `''` |  |
| 1774 | `moa.privacy_filter` | `''` | Privacy redaction filter for advisor (reference) outputs. Advisors can echo PII from the conversation (emails, formatted phone numbers) and credential shapes into reference blocks, traces, and the aggregator prompt. Modes ('' = off, the default): "display" — redact user-visible surfaces only (reference blocks shown in the UI + saved MoA trace records); the aggregator still sees raw advisor text. "full" — additionally … |
| 1775 | `moa.presets` | `{ … }` |  |
| 1776 | `moa.presets.default` | `{ … }` |  |
| 1777 | `moa.presets.default.reference_models` | `[{'provider': 'openai-codex', 'model': 'gpt-5.5'}, {'provider': 'openrouter', 'model': 'deepseek/deepseek-v4-pro'}]` |  |
| 1781 | `moa.presets.default.aggregator` | `{ … }` |  |
| 1781 | `moa.presets.default.aggregator.provider` | `'openrouter'` |  |
| 1781 | `moa.presets.default.aggregator.model` | `'anthropic/claude-opus-4.8'` |  |
| 1782 | `moa.presets.default.max_tokens` | `4096` |  |
| 1783 | `moa.presets.default.enabled` | `True` |  |
| 1791 | `skills` | `{ … }` | Skills — external skill directories for sharing skills across tools/agents. Each path is expanded (~, ${VAR}) and resolved. Read-only — skill creation always goes to ~/.hermes/skills/. |
| 1792 | `skills.external_dirs` | `[]` | e.g. ["~/.agents/skills", "/shared/team-skills"] |
| 1797 | `skills.template_vars` | `True` | Substitute ${HERMES_SKILL_DIR} and ${HERMES_SESSION_ID} in SKILL.md content with the absolute skill directory and the active session id before the agent sees it. Lets skill authors reference bundled scripts without the agent having to join paths. |
| 1804 | `skills.inline_shell` | `False` | Pre-execute inline shell snippets written as !`cmd` in SKILL.md body. Their stdout is inlined into the skill message before the agent reads it, so skills can inject dynamic context (dates, git state, detected tool versions, …). Off by default because any content from the skill author runs on the host without approval; only enable for skill sources you trust. |
| 1806 | `skills.inline_shell_timeout` | `10` | Timeout (seconds) for each !`cmd` snippet when inline_shell is on. |
| 1817 | `skills.guard_agent_created` | `False` | Run the keyword/pattern security scanner on skills the agent writes via skill_manage (create/edit/patch). Off by default because the agent can already execute the same code paths via terminal() with no gate, so the scan adds friction (blocks skills that mention risky keywords in prose) without meaningful security. Turn on if you want the belt-and-suspenders — a dangerous verdict will then surface as a tool error to t … |
| 1829 | `skills.write_approval` | `False` | Approval gate for skill_manage (create/edit/patch/write_file/delete/ remove_file), applied to BOTH foreground agent turns and the background self-improvement review fork. false (default) — write freely; the gate is off (pre-gate behaviour) true — require approval: stage the write for review instead of committing (a SKILL.md is too large to review inline, so skills always stage rather than prompt). List with /skills p … |
| 1842 | `curator` | `{ … }` | Curator — background skill maintenance. Periodically reviews AGENT-CREATED skills (never bundled or hub-installed) and keeps the collection tidy: marks long-unused skills as stale, archives genuinely obsolete ones (archive only, never deletes), and spawns a forked aux-model agent to consolidate overlaps and patch drift. Runs inactivity-triggered from session start — no cron daemon. See `hermes curator status` for the … |
| 1843 | `curator.enabled` | `True` |  |
| 1845 | `curator.interval_hours` | `24 * 7` | How long to wait between curator runs (hours). Default: 7 days. |
| 1847 | `curator.min_idle_hours` | `2` | Only run when the agent has been idle at least this long (hours). |
| 1849 | `curator.stale_after_days` | `30` | Mark a skill as "stale" after this many days without use. |
| 1852 | `curator.archive_after_days` | `90` | Archive a skill (move to skills/.archive/) after this many days without use. Archived skills are recoverable — no auto-deletion. |
| 1860 | `curator.consolidate` | `False` | Run the LLM consolidation (umbrella-building) pass. OFF by default. When off, a curator run does ONLY the deterministic inactivity prune (mark stale / archive long-unused skills) and skips the forked aux-model review entirely — no umbrella-building, no aux-model cost. Set to true to opt back into merging overlapping skills into class-level umbrellas. `hermes curator run --consolidate` overrides this for a single invo … |
| 1871 | `curator.prune_builtins` | `True` | Also prune (archive) bundled built-in skills after the inactivity period, not just agent-created ones. ON by default. Built-ins are normally restored on every `hermes update`, so pruning them only sticks because a suppression list tells the re-seeder to leave them archived. Hub-installed skills are NEVER pruned here — they have an external upstream owner. Built-ins accrue usage telemetry and their inactivity clock st … |
| 1876 | `curator.backup` | `{ … }` | Pre-run backup: before every real curator pass (dry-run is skipped), snapshot ~/.hermes/skills/ into ~/.hermes/skills/.curator_backups/<utc-iso>/skills.tar.gz so the user can roll back with `hermes curator rollback`. |
| 1877 | `curator.backup.enabled` | `True` |  |
| 1878 | `curator.backup.keep` | `5` | retain last N regular snapshots |
| 1885 | `honcho` | `{}` | Honcho AI-native memory -- reads ~/.honcho/config.json as single source of truth. This section is only needed for hermes-specific overrides; everything else (apiKey, workspace, peerName, sessions, enabled) comes from the global config. |
| 1889 | `timezone` | `''` | IANA timezone (e.g. "Asia/Kolkata", "America/New_York"). Empty string means use server-local time. |
| 1892 | `slack` | `{ … }` | Slack platform settings (gateway mode) |
| 1893 | `slack.require_mention` | `True` | Require @mention to respond in channels |
| 1894 | `slack.free_response_channels` | `''` | Comma-separated channel IDs where bot responds without mention |
| 1895 | `slack.allowed_channels` | `''` | If set, bot ONLY responds in these channel IDs (whitelist) |
| 1898 | `slack.require_mention_channels` | `''` | Channel IDs where @mention is ALWAYS required, even when require_mention is false globally (per-channel force-mention override). |
| 1902 | `slack.ignore_other_user_mentions` | `False` | Ignore a channel/thread message addressed to another user (first token @mentions someone other than the bot) unless the bot is also mentioned. Opt-in; default off keeps existing behaviour. Env: SLACK_IGNORE_OTHER_USER_MENTIONS. |
| 1904 | `slack.thread_require_mention` | `False` | If True, require @mention in Slack thread replies too. |
| 1905 | `slack.channel_prompts` | `{}` | Per-channel ephemeral system prompts |
| 1909 | `discord` | `{ … }` | Discord platform settings (gateway mode) |
| 1910 | `discord.require_mention` | `True` | Require @mention to respond in server channels |
| 1911 | `discord.free_response_channels` | `''` | Comma-separated channel IDs where bot responds without mention |
| 1912 | `discord.allowed_channels` | `''` | If set, bot ONLY responds in these channel IDs (whitelist) |
| 1913 | `discord.auto_thread` | `True` | Auto-create threads on @mention in channels (like Slack) |
| 1914 | `discord.thread_require_mention` | `False` | If True, require @mention in threads too (multi-bot threads) |
| 1915 | `discord.bots_require_inline_mention` | `False` | Multi-bot rooms: if True, another bot must type @thisbot in its message to trigger a reply; a Discord reply/quote alone won't. Prevents two bots auto-replying to each other forever. Does not affect humans. |
| 1916 | `discord.history_backfill` | `True` | If True, prepend recent channel scrollback when bot is triggered (recovers messages missed while require_mention gated them out) |
| 1917 | `discord.history_backfill_limit` | `50` | Max number of recent messages to scan when assembling the backfill block |
| 1918 | `discord.missed_message_backfill` | `{ … }` |  |
| 1919 | `discord.missed_message_backfill.enabled` | `False` | Replay missed Discord messages after reconnect/startup |
| 1920 | `discord.missed_message_backfill.channels` | `''` | Comma-separated channel IDs; empty uses free_response_channels |
| 1921 | `discord.missed_message_backfill.window_seconds` | `21600` | Only inspect messages from the last 6 hours |
| 1922 | `discord.missed_message_backfill.limit` | `100` | Global cap on messages scanned per reconnect |
| 1923 | `discord.missed_message_backfill.max_dispatches` | `10` | Cap on recovered messages dispatched per reconnect |
| 1925 | `discord.reactions` | `True` | Add 👀/✅/❌ reactions to messages during processing |
| 1930 | `discord.websocket_liveness_interval_seconds` | `15` | Discord Gateway transport health. These settings inspect the active WebSocket's ready/open/heartbeat state; they never use Discord REST as proof that Gateway events are still arriving. Set any value to 0 to disable this compatibility-safe probe during a rollback. |
| 1931 | `discord.websocket_liveness_failure_threshold` | `2` |  |
| 1932 | `discord.websocket_heartbeat_ack_max_age_seconds` | `60` |  |
| 1933 | `discord.websocket_max_latency_seconds` | `30` |  |
| 1934 | `discord.channel_prompts` | `{}` | Per-channel ephemeral system prompts (forum parents apply to child threads) |
| 1940 | `discord.dm_role_auth_guild` | `''` | Opt-in DM role-based auth (#12136). By default, DISCORD_ALLOWED_ROLES authorizes only guild messages in the role's own guild — DMs require DISCORD_ALLOWED_USERS. Set dm_role_auth_guild to a guild ID to also authorize DMs from members of that one trusted guild holding the allowed role. Unset / empty / 0 = secure default (DM role-auth off). |
| 1948 | `discord.server_actions` | `''` | discord / discord_admin tools: restrict which actions the agent may call. Default (empty) = all actions allowed (subject to bot privileged intents). Accepts comma-separated string ("list_guilds,list_channels,fetch_messages") or YAML list. Unknown names are dropped with a warning at load time. Actions: list_guilds, server_info, list_channels, channel_info, list_roles, member_info, search_members, fetch_messages, list_ … |
| 1954 | `discord.allow_any_attachment` | `False` | DEPRECATED / no-op. Any uploaded file is now always cached and surfaced to the agent regardless of file type — authorization to message the agent is the gate, not the extension. Kept so existing configs that set it do not error. Env override: DISCORD_ALLOW_ANY_ATTACHMENT. |
| 1959 | `discord.max_attachment_bytes` | `33554432` | Maximum bytes per attachment the gateway will cache. The whole file is held in memory while being written, so unlimited uploads carry a real memory cost. Default 32 MiB matches the historical hardcoded cap. Set to 0 for no cap. Env override: DISCORD_MAX_ATTACHMENT_BYTES. |
| 1964 | `discord.approval_mentions` | `False` | When True, Discord approval prompts mention numeric allowed users so owners notice approval requests in shared channels/threads. Env override: DISCORD_APPROVAL_MENTIONS. Default false avoids surprise pings. |
| 1967 | `discord.voice_channel_inactivity_timeout_seconds` | `300` | Discord voice-channel inactivity timeout, in seconds. Set to 0 to keep the bot in VC until an explicit `/voice leave` / disconnect. |
| 1971 | `discord.voice_playback_timeout_seconds` | `120` | Minimum seconds to wait for a VC playback before force-stopping it. The adapter also probes clip duration and extends this floor by a padding window, so long TTS readbacks are not cut at exactly 120s. |
| 1978 | `discord.voice_fx` | `{ … }` | Voice-channel audio effects (the continuous mixer). OFF by default. When enabled, the bot installs a software mixer on the outgoing voice stream so a low ambient "thinking" bed, verbal acknowledgements, and TTS replies can OVERLAP (ducking the ambient under speech) instead of stop-and-swap — the Grok-voice-mode feel. discord.py ships no mixer; this is implemented in plugins/platforms/discord/voice_mixer.py. |
| 1979 | `discord.voice_fx.enabled` | `False` | master switch for the mixer subsystem |
| 1980 | `discord.voice_fx.ambient_enabled` | `True` | play the idle "thinking" bed while tools run |
| 1981 | `discord.voice_fx.ambient_path` | `''` | custom loop audio file; "" = synthesised pad |
| 1982 | `discord.voice_fx.ambient_gain` | `0.18` | idle bed loudness, 0.0–1.0 |
| 1983 | `discord.voice_fx.duck_gain` | `0.06` | ambient loudness while speech plays |
| 1984 | `discord.voice_fx.speech_gain` | `1.0` | TTS / ack loudness, 0.0–1.0 |
| 1985 | `discord.voice_fx.ack_enabled` | `True` | speak a short phrase before the first tool call |
| 1986 | `discord.voice_fx.ack_phrases` | `['Let me look into that.', 'One moment.', 'Checking on that now.', 'Give me a sec.', 'On it.']` | picked at random; set [] to disable phrases |
| 1997 | `whatsapp` | `{}` | WhatsApp platform settings (gateway mode) |
| 2005 | `telegram` | `{ … }` | Telegram platform settings (gateway mode) |
| 2006 | `telegram.reactions` | `False` | Add 👀/✅/❌ reactions to messages during processing |
| 2007 | `telegram.channel_prompts` | `{}` | Per-chat/topic ephemeral system prompts (topics inherit from parent group) |
| 2008 | `telegram.allowed_chats` | `''` | If set, bot ONLY responds in these group/supergroup chat IDs (whitelist) |
| 2009 | `telegram.extra` | `{ … }` |  |
| 2010 | `telegram.extra.rich_messages` | `False` | Bot API 10.1 rich messages (tables/task lists/details/math) render natively; set True to opt in. Default stays legacy MarkdownV2 because rich messages can be hard to copy as plain text in Telegram clients. |
| 2011 | `telegram.extra.rich_drafts` | `False` | Experimental Bot API 10.1 rich draft previews during Telegram DM streaming. Default off because Telegram Desktop/macOS can visually overlay rich draft frames until the chat redraws. |
| 2016 | `mattermost` | `{ … }` | Mattermost platform settings (gateway mode) |
| 2017 | `mattermost.require_mention` | `True` | Require @mention to respond in channels |
| 2018 | `mattermost.free_response_channels` | `''` | Comma-separated channel IDs where bot responds without mention |
| 2019 | `mattermost.allowed_channels` | `''` | If set, bot ONLY responds in these channel IDs (whitelist) |
| 2020 | `mattermost.channel_prompts` | `{}` | Per-channel ephemeral system prompts |
| 2024 | `matrix` | `{ … }` | Matrix platform settings (gateway mode) |
| 2025 | `matrix.require_mention` | `True` | Require @mention to respond in rooms |
| 2026 | `matrix.free_response_rooms` | `''` | Comma-separated room IDs where bot responds without mention |
| 2027 | `matrix.allowed_rooms` | `''` | If set, bot ONLY responds in these room IDs (whitelist) |
| 2044 | `approvals` | `{ … }` | Approval mode for dangerous commands: manual — always prompt the user smart — use auxiliary LLM to auto-approve low-risk commands (default) off — skip all approval prompts (equivalent to --yolo) cron_mode — what to do when a cron job hits a dangerous command: deny — block the command and let the agent find another way (default, safe) approve — auto-approve all dangerous commands in cron jobs timeout — seconds to wait … |
| 2045 | `approvals.mode` | `'smart'` |  |
| 2046 | `approvals.timeout` | `300` |  |
| 2047 | `approvals.cron_mode` | `'deny'` |  |
| 2054 | `approvals.smart_policy` | `''` | Operator-customizable policy text for smart approvals. When non-empty, this is appended to the smart-approval guardian's SYSTEM prompt (trusted channel) as additional rules — e.g. "Always ESCALATE commands touching /etc" or "APPROVE docker compose restarts under ~/deploys". Inspired by ChatGPT Work's customizable auto-review guardian policy. |
| 2061 | `approvals.denial_breaker_threshold` | `3` | Consecutive-denial circuit breaker for smart approvals: after this many guardian DENY verdicts in a row within one session, the deny message returned to the model escalates to a hard-stop instruction (report to the user / ask for manual run or /approve) instead of a plain "Do NOT retry". Any approval resets the count. 0 disables. Inspired by ChatGPT Work's auto-review circuit breaker. |
| 2071 | `approvals.deny` | `[]` | User-defined deny rules: fnmatch globs matched against terminal commands. A match blocks the command unconditionally — BEFORE the --yolo / /yolo / mode=off bypass — making this the user-editable counterpart to the code-shipped hardline blocklist. Patterns are case-insensitive and must be quoted in YAML when they start with * or contain {}/!/: sequences. Example: deny: - "git push --force*" - "*curl*\|*sh*" |
| 2079 | `approvals.mcp_reload_confirm` | `True` | When true, /reload-mcp asks the user to confirm before rebuilding the MCP tool set for the active session. Reloading invalidates the provider prompt cache (tool schemas are baked into the system prompt), so the next message re-sends full input tokens — this can be expensive on long-context or high-reasoning models. Users click "Always Approve" to silence the prompt permanently; that flips this key to false. |
| 2088 | `approvals.destructive_slash_confirm` | `True` | When true, destructive session slash commands (/clear, /new, /reset, /undo) ask the user to confirm before discarding conversation state. Three-option prompt (Approve Once / Always Approve / Cancel) routed through tools.slash_confirm — native yes/no buttons on Telegram, Discord, and Slack; text fallback elsewhere. Users click "Always Approve" to silence the prompt permanently; that flips this key to false. TUI has it … |
| 2092 | `command_allowlist` | `[]` | Permanently allowed dangerous command patterns (added via "always" approval) |
| 2094 | `quick_commands` | `{}` | User-defined quick commands that bypass the agent loop (type: exec only) |
| 2110 | `platform_hints` | `{}` | Per-platform system-prompt hint overrides. Lets an admin append to or replace Hermes' built-in platform hint for a single messaging platform (WhatsApp, Slack, Telegram, ...) without affecting other platforms. Useful for enterprise/managed profiles that ship platform-aware skills. Each key is a platform name; the value is either: { "append": "extra text" } — keep the default hint, append text { "replace": "full text" … |
| 2119 | `hooks` | `{}` | Shell-script hooks — declarative bridge that invokes shell scripts on plugin-hook events (pre_tool_call, post_tool_call, pre_llm_call, subagent_stop, etc.). Each entry maps an event name to a list of {matcher, command, timeout} dicts. First registration of a new command prompts the user for consent; subsequent runs reuse the stored approval from ~/.hermes/shell-hooks-allowlist.json. See `website/docs/user-guide/featu … |
| 2125 | `hooks_auto_accept` | `False` | Auto-accept shell-hook registrations without a TTY prompt. Also toggleable per-invocation via --accept-hooks or HERMES_ACCEPT_HOOKS=1. Gateway / cron / non-interactive runs need this (or one of the other channels) to pick up newly-added hooks. |
| 2129 | `personalities` | `{}` | Custom personalities — add your own entries here Supports string format: {"name": "system prompt"} Or dict format: {"name": {"description": "...", "system_prompt": "...", "tone": "...", "style": "..."}} |
| 2132 | `security` | `{ … }` | Pre-exec security scanning via tirith |
| 2133 | `security.allow_private_urls` | `False` | Allow requests to private/internal IPs (for OpenWrt, proxies, VPNs) |
| 2134 | `security.redact_secrets` | `True` |  |
| 2135 | `security.tirith_enabled` | `True` |  |
| 2136 | `security.tirith_path` | `'tirith'` |  |
| 2137 | `security.tirith_timeout` | `5` |  |
| 2138 | `security.tirith_fail_open` | `True` |  |
| 2139 | `security.website_blocklist` | `{ … }` |  |
| 2140 | `security.website_blocklist.enabled` | `False` |  |
| 2141 | `security.website_blocklist.domains` | `[]` |  |
| 2142 | `security.website_blocklist.shared_files` | `[]` |  |
| 2150 | `security.acked_advisories` | `[]` | Acknowledged supply-chain security advisories. Each entry is the ID of an advisory the user has read and acted on (uninstalled the compromised package, rotated credentials). Acked advisories no longer trigger the startup banner. Add via `hermes doctor --ack <id>`; remove by editing the list directly. See ``hermes_cli/security_advisories.py`` for the catalog. |
| 2158 | `security.allow_lazy_installs` | `True` | Allow Hermes to lazy-install opt-in backend packages from PyPI the first time the user enables a backend that needs them (e.g. installing ``elevenlabs`` when the user picks ElevenLabs as their TTS provider). Set to false to require explicit ``pip install`` for everything beyond the base set — appropriate for restricted networks, audited environments, or air-gapped systems where any runtime install is unacceptable. |
| 2161 | `cron` | `{ … }` |  |
| 2166 | `cron.model_drift_guard` | `True` | Fail closed when an unpinned job's current global model/provider differs from its creation-time snapshot. This prevents unattended jobs from silently inheriting a paid default. Set to false only when jobs should deliberately track changing global inference defaults. |
| 2173 | `cron.model` | `''` | Default inference model for cron jobs (Axis A — WHAT model an agent job runs on). Resolution at fire time: per-job user pin > cron.model > global model.default. When set, unpinned jobs follow this deliberately, so the #44585 model-drift fail-closed guard does not engage for the model axis — cron spend no longer shadows chat `/model` switches. Empty string = fall through to model.default. |
| 2176 | `cron.model_provider` | `''` | Inference provider paired with cron.model (NOT the scheduler provider below). Empty string = resolve from global config. |
| 2184 | `cron.provider` | `''` | Active cron SCHEDULER provider (Axis B — the trigger that decides WHEN a due job fires). Empty string = the built-in in-process 60s ticker (default). Name an installed provider (plugins/cron_providers/<name>/ or $HERMES_HOME/plugins/<name>/) to relocate the trigger — e.g. "chronos", the NAS-mediated managed-cron provider for scale-to-zero deployments. An unknown or unavailable provider falls back to the built-in, so … |
| 2190 | `cron.chronos` | `{ … }` | Chronos (NAS-mediated managed cron) settings. Only consulted when provider == "chronos". All non-secret (URLs + the JWT audience): the agent holds NO external-scheduler credentials. For hosted agents, NAS sets these at provision time. The outbound provision call reuses the agent's existing Nous Portal token — there is no token key here. |
| 2193 | `cron.chronos.portal_url` | `'https://portal.nousresearch.com'` | NAS / portal base URL the agent calls to arm/cancel one-shots and that mints the inbound fire JWT (used as the expected issuer). |
| 2197 | `cron.chronos.callback_url` | `''` | The agent's OWN publicly-reachable base URL for NAS→agent fires (NAS POSTs {callback_url}/api/cron/fire). Empty → Chronos is unavailable and the resolver falls back to the built-in ticker. |
| 2199 | `cron.chronos.expected_audience` | `''` | This agent's expected JWT audience (e.g. "agent:{instance_id}"). |

<!-- rows=683 -->

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
