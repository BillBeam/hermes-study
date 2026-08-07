# r8a-raw-config-d · config.py:4200-5434

底稿性质:证据层,求全求证,不求好读。所有断言均来自亲自读过的基线源码,
引用格式 `路径:行号 @ 863e313`,路径相对 `/home/user/hermes-agent` 根。
基线:`863e31318553cda8ad61df681d08175364d4164b`,`hermes_cli/config.py` 全文 5434 行。

本段覆盖 **4200-5434**(文件末尾),内容上恰好是一个自洽的簇:
**"config 值的展示面 + 写入面 + CLI 子命令分发 + 导入期的两次环境变量注入"**。
换句话说,这一段是 `hermes config` 这个子命令的**全部实现**,加上模块 import 时的两个副作用钩子。

---

## 0. 先建立上下文:模块 docstring 与它的"承诺"

模块头把自己定位为 `~/.hermes/` 下两个文件的管理者,并逐条列出它提供的子命令。`hermes_cli/config.py:8-14 @ 863e313`

```python
This module provides:
- hermes config          - Show current configuration
- hermes config edit     - Open config in editor
- hermes config get      - Print a resolved configuration value
- hermes config set      - Set a specific value
- hermes config unset    - Remove a user configuration value
- hermes config wizard   - Re-run setup wizard
```

**文档-代码出入 ①(docstring 列了不存在的子命令)**:docstring 说有 `hermes config wizard`,
但 `config_command` 的分发链里没有 `wizard` 分支——`show / edit / get / set / unset / path /
env-path / migrate / check`,其余一律落到 `else` 打印 "Unknown config command"。`hermes_cli/config.py:5282-5283 @ 863e313`

```python
    else:
        print(f"Unknown config command: {subcmd}")
```

反过来,docstring 又漏掉了实际存在的 `path` / `env-path` / `migrate` / `check` 四个子命令。`hermes_cli/config.py:5182-5186 @ 863e313`

```python
    elif subcmd == "path":
        print(get_config_path())
    
    elif subcmd == "env-path":
        print(get_env_path())
```

(`hermes setup` 才是跑向导的入口——`show_config` 尾部的提示行印证了这一点,见 §2.3(h) 对 4460-4462 的引用。)

---

## 1. 专题:第 943 行那个"不在文件顶部"的 import

任务书把它描述为"函数体内部的 import"。**实测不是**:它在模块顶层(零缩进),
只是位置在文件中部第 943 行,处在 `# Config loading/saving` 分节横幅之下。`hermes_cli/config.py:939-943 @ 863e313`

```python
# =============================================================================
# Config loading/saving
# =============================================================================

from hermes_cli.config_defaults import DEFAULT_CONFIG, OPTIONAL_ENV_VARS  # noqa: F401
```

### 1.1 它不是为了解决循环依赖

`hermes_cli/config_defaults.py` 是**纯数据叶子模块,一行 import 都没有**——
我对该文件跑过 `grep -nE "^\s*(import|from) "`,零命中;文件自己的 docstring 也把这条写成了硬约束。
`hermes_cli/config_defaults.py:1-5 @ 863e313`

```python
"""Default configuration data for Hermes Agent.

Pure-data leaf module: DEFAULT_CONFIG and OPTIONAL_ENV_VARS, extracted
verbatim from hermes_cli/config.py. Must not import from hermes_cli.config.
"""
```

既然被 import 的模块不 import 任何东西,就**不可能**构成循环。所以"循环依赖"这个假说被排除。

### 1.2 真正的原因:这是全文件通行的"分节内再导出"写法 + 机械拆分留下的位置

同一文件里至少还有三处同样风格的中部顶层 import,其中一处带着明写的解释性注释:
canonical 定义在别的模块,这里只是**再导出**,并且刻意放在它服务的那一节的开头。
`hermes_cli/config.py:686-692 @ 863e313`

```python
# =============================================================================
# Config paths
# =============================================================================

# Re-export from hermes_constants — canonical definition lives there.
from hermes_constants import get_hermes_home, get_process_hermes_home  # noqa: F811,E402
from utils import atomic_replace, fast_safe_load
```

另一处更朴素:`import yaml` 直接跟在一个巨型 `frozenset` 字面量后面。`hermes_cli/config.py:327-331 @ 863e313`

```python
})
import yaml

from hermes_cli.colors import Colors, color
from hermes_cli.default_soul import DEFAULT_SOUL_MD, is_legacy_template_soul
```

结论(**证据支持的推断,非猜测**):`DEFAULT_CONFIG` / `OPTIONAL_ENV_VARS` 原本就是**写在 config.py 第 943 行位置的字面量**
(config_defaults 的 docstring 自称 "extracted verbatim from hermes_cli/config.py"),
拆分成独立模块时,作者把 import **原地放在数据原本所在的行位**,从而保持了文件其余部分的行序与分节结构不动。
`# noqa: F401` 明示它是"导入但本模块不一定用得到"的**再导出垫片**。

### 1.3 这个再导出垫片服务于谁(为什么不能删)

全仓有大量调用点仍然从 `hermes_cli.config` 拿 `DEFAULT_CONFIG` / `OPTIONAL_ENV_VARS`,
而不是从 `config_defaults` 拿。我用 `grep -rn "from hermes_cli.config import" --include=*.py .` 过滤后统计,
生产代码侧至少有:`gateway/run.py:3220`、`gateway/restart.py:6`、`hermes_cli/dump.py:231`、
`hermes_cli/main.py:967`、`hermes_cli/doctor.py:1169`、`hermes_cli/mcp_startup.py:144`、
`hermes_cli/provider_catalog.py:110`、`hermes_cli/web_server.py:6956`;测试侧还有二十余处。
删掉第 943 行的再导出,这些站点全部 ImportError。

**代价(取舍)**:一个符号有两个合法来源(`hermes_cli.config.DEFAULT_CONFIG` 与
`hermes_cli.config_defaults.DEFAULT_CONFIG`),它们是**同一个对象**(import 只是绑名)。
这在本段末尾的两个注入器那里变成了 load-bearing 的副作用通道——见 §7。

---

## 2. 展示面:`redact_config_value` 与 `show_config`

### 2.1 问题:`print()` 绕过了日志脱敏器

Hermes 的日志层有正则式脱敏(`agent.redact`),但 `print` 不经过它;而且像 Cloudflare 的
`cfut_...` 这种不透明 token 根本匹配不上任何厂商前缀正则。于是作者补了一层**按 key 名的结构式脱敏**。
`hermes_cli/config.py:4194-4199 @ 863e313`

```python
# Key names (case-insensitive, exact match) whose VALUE is a credential and
# must be masked before printing any config dict to the terminal. Covers the
# fields a custom provider stuffs into the `model`/`custom_providers` blocks
# (`api_key`) plus the usual token/secret/password shapes. Exact-match only so
# benign keys like `token_count` or `secret_santa` don't get masked.
_SECRET_CONFIG_KEYS = frozenset({
```

集合成员(全 17 个):`api_key, apikey, key, token, access_token, refresh_token, id_token,
secret, client_secret, password, passwd, auth, authorization, private_key, bearer, jwt`。
`hermes_cli/config.py:4200-4216 @ 863e313`

```python
    "api_key",
```

### 2.2 实现:递归遍历 + 深度上限

`hermes_cli/config.py:4219 @ 863e313`

```python
def redact_config_value(value: Any, _depth: int = 0) -> Any:
```

递归深度硬上限 20 层,为病态/环状配置兜底(注意:这是**深度**上限,不是环检测——
真正的自引用 dict 靠 20 层截断而非 `id()` 记忆消解)。`hermes_cli/config.py:4232-4234 @ 863e313`

```python
    # Defensive bound on recursion depth for pathological/cyclic configs.
    if _depth > 20:
        return value
```

命中条件是四联与:key 是 str、小写后在集合内、value 是 str、value 非空。
非字符串值(比如 `api_key: 12345` 被 YAML 解析成 int)**不会被打码**。`hermes_cli/config.py:4238-4239 @ 863e313`

```python
            if isinstance(k, str) and k.lower() in _SECRET_CONFIG_KEYS and isinstance(v, str) and v:
                out[k] = mask_secret(v)
```

`from agent.redact import mask_secret` 是函数内 import(`hermes_cli/config.py:4230`),
理由是 hermes_cli 不想在 import 期把 agent 包拉进来。

**取舍**:精确匹配(而非子串)。好处是 `token_count`、`secret_santa` 不被误打码;
坏处是 `openrouter_key`、`my_api_key_2` 这类变体漏网。作者在注释里明说了这是自觉的取舍。

### 2.3 `show_config`:一屏配置体检

`hermes_cli/config.py:4248-4250 @ 863e313`

```python
def show_config():
    """Display current configuration."""
    config = load_config()
```

注意它用的是 `load_config()`——即 **DEFAULT_CONFIG 深拷贝为底、再叠加用户 config.yaml、
再叠加 managed 覆盖层**的合并结果。`hermes_cli/config.py:3333 @ 863e313`

```python
        config = copy.deepcopy(DEFAULT_CONFIG)
```

这一点在下面讲"死默认值"缺陷时是关键前提。

#### (a) 托管作用域横幅

先问 managed_scope 拿被管理员钉死的 key 集合与 env 集合,任一非空就打黄色横幅,
把"你 config.yaml 里的值可能不是生效值"这件事讲明白。`hermes_cli/config.py:4259-4264 @ 863e313`

```python
    from hermes_cli import managed_scope

    _managed_keys = managed_scope.managed_config_keys()
    _managed_env = managed_scope.load_managed_env()
    if _managed_keys or _managed_env:
        _managed_dir = managed_scope.get_managed_dir()
```

`managed_config_keys()` 返回的是**扁平化后的点分叶子键**。`hermes_cli/managed_scope.py:202-204 @ 863e313`

```python
def managed_config_keys() -> set:
    """Dotted leaf keys pinned by the managed config (e.g. {'model.default'})."""
    return _flatten_keys(load_managed_config())
```

托管目录的解析链(**环境变量 `HERMES_MANAGED_DIR` 优先,否则 `/etc/hermes`,pytest 下屏蔽第二档**):
`hermes_cli/managed_scope.py:65 @ 863e313`

```python
    override = os.environ.get("HERMES_MANAGED_DIR", "").strip()
```

#### (b) API key 面板

九个 env key 硬编码成表,逐个 `get_env_value` + `redact_key`。`hermes_cli/config.py:4294-4304 @ 863e313`

```python
    keys = [
        ("OPENROUTER_API_KEY", "OpenRouter"),
        ("VOICE_TOOLS_OPENAI_KEY", "OpenAI (STT/TTS)"),
        ("EXA_API_KEY", "Exa"),
        ("PARALLEL_API_KEY", "Parallel"),
        ("FIRECRAWL_API_KEY", "Firecrawl"),
        ("TAVILY_API_KEY", "Tavily"),
        ("BROWSERBASE_API_KEY", "Browserbase"),
        ("BROWSER_USE_API_KEY", "Browser Use"),
        ("FAL_KEY", "FAL"),
    ]
```

Anthropic 单独走 `hermes_cli.auth.get_anthropic_key()`,因为它有三级 fallback 链。`hermes_cli/config.py:4309-4311 @ 863e313`

```python
    from hermes_cli.auth import get_anthropic_key
    anthropic_value = get_anthropic_key()
    print(f"  {'Anthropic':<14} {redact_key(anthropic_value)}")
```

链条本身写在 auth 的 docstring 里:`ANTHROPIC_API_KEY -> ANTHROPIC_TOKEN -> CLAUDE_CODE_OAUTH_TOKEN`,
且**偏好 `.env` 文件而非 shell 导出**(避免旧的 shell export 遮蔽刚轮换的 key)。`hermes_cli/auth.py:557 @ 863e313`

```python
        ANTHROPIC_API_KEY -> ANTHROPIC_TOKEN -> CLAUDE_CODE_OAUTH_TOKEN
```

`redact_key` 只是 `mask_secret` 的薄包装,空值时打印 dim 的 `(not set)`。`hermes_cli/config.py:4184 @ 863e313`

```python
def redact_key(key: str) -> str:
```

#### (c) Model 段 + `.env` 幽灵告警(issue #17534)

`hermes_cli/config.py:4316-4318 @ 863e313`

```python
    print(f"  Model:        {redact_config_value(config.get('model', 'not set'))}")
    _cfg_max_turns = config.get('agent', {}).get('max_turns', DEFAULT_CONFIG['agent']['max_turns'])
    print(f"  Max turns:    {_cfg_max_turns}")
```

`model` 走 `redact_config_value` 是必要的:`model` 既可以是裸字符串,也可以是带 `api_key` 的 dict。

紧接着是一段很有教学价值的**遗留环境变量幽灵检测**:直接读 `.env` 文件(不是 `os.environ`),
比对它里面残留的 `HERMES_MAX_ITERATIONS` 与 config.yaml 的 `agent.max_turns` 是否一致。
之所以读文件而不读环境,注释写得很清楚——gateway bridge 可能已经把 `os.environ` 改写过了,
读环境就看不见这个幽灵。`hermes_cli/config.py:4322-4324 @ 863e313`

```python
    try:
        _env_ghost = load_env().get("HERMES_MAX_ITERATIONS")
        if _env_ghost is not None and str(_env_ghost).strip() != str(_cfg_max_turns).strip():
```

告警文案直接给出修复命令。`hermes_cli/config.py:4325-4329 @ 863e313`

```python
            print(color(
                f"                ⚠ .env has stale HERMES_MAX_ITERATIONS={_env_ghost} "
                f"(run 'hermes doctor --fix' to remove)",
                Colors.YELLOW,
            ))
```

**整段被 `except Exception: pass` 包住**——静默吞异常。`hermes_cli/config.py:4330-4331 @ 863e313`

```python
    except Exception:
        pass
```

怎么会踩到:如果 `.env` 文件损坏导致 `load_env()` 抛异常,用户既看不到幽灵告警,也看不到"你的 .env 读不出来"。
不过这是**展示路径**,不影响行为,风险等级低。

#### (d) Terminal 段:按 backend 分支展示

`hermes_cli/config.py:4348-4351 @ 863e313`

```python
    terminal = config.get('terminal', {})
    print(f"  Backend:      {terminal.get('backend', 'local')}")
    print(f"  Working dir:  {terminal.get('cwd', '.')}")
    print(f"  Timeout:      {terminal.get('timeout', 60)}s")
```

Vercel 分支的凭据判定是"OIDC token 或 (TOKEN 且 PROJECT_ID 且 TEAM_ID)"三元组齐全。
`hermes_cli/config.py:4367 @ 863e313`

```python
        print(f"  Vercel auth:    {'configured' if get_env_value('VERCEL_OIDC_TOKEN') or (get_env_value('VERCEL_TOKEN') and get_env_value('VERCEL_PROJECT_ID') and get_env_value('VERCEL_TEAM_ID')) else '(not set)'}")
```

#### (e) 压缩段

`hermes_cli/config.py:4386-4390 @ 863e313`

```python
    compression = config.get('compression', {})
    enabled = compression.get('enabled', True)
    print(f"  Enabled:      {'yes' if enabled else 'no'}")
    if enabled:
        print(f"  Threshold:    {compression.get('threshold', 0.50) * 100:.0f}%")
```

`threshold_tokens` 是可选的**绝对 token 上限**,与比例阈值取更低者;非法值静默忽略。
`hermes_cli/config.py:4391-4398 @ 863e313`

```python
        _tt = compression.get('threshold_tokens')
        if _tt is not None:
            try:
                _tt = int(_tt)
                if _tt > 0:
                    print(f"  Token cap:    {_tt:,} tokens (takes lower of ratio vs absolute)")
            except (TypeError, ValueError):
                pass
```

#### (f) 辅助模型段:只在有覆盖时才打印

`hermes_cli/config.py:4415-4419 @ 863e313`

```python
    has_overrides = any(
        t.get('provider', 'auto') != 'auto' or t.get('model', '')
        for t in aux_tasks.values()
    )
    if has_overrides:
```

**注意 `aux_tasks` 只含 Vision 与 Web extract 两项**(`hermes_cli/config.py:4411-4414`),
而 `DEFAULT_CONFIG["auxiliary"]` 实际有 20 个任务槽(compression / skills_hub / approval / mcp /
title_generation / memory_query_rewrite / tts_audio_tags / triage_specifier / kanban_decomposer /
profile_describer / goal_judge / curator / monitor / background_review / moa_reference / moa_aggregator …)。
`hermes config` 因此**看不见**用户对其余 18 个槽的覆盖(compression 单独在压缩段里展示了)。
这是展示面的不完备,不是行为缺陷,但用户会被误导成"我没设过 auxiliary 覆盖"。

#### (g) Skill 设置段——**疑似明文泄露点**

`hermes_cli/config.py:4442-4446 @ 863e313`

```python
    try:
        from agent.skill_utils import discover_all_skill_config_vars, resolve_skill_config_values
        skill_vars = discover_all_skill_config_vars()
        if skill_vars:
            resolved = resolve_skill_config_values(skill_vars)
```

打印时**没有任何脱敏**:`hermes_cli/config.py:4453 @ 863e313`

```python
                display_val = str(value) if value else color("(not set)", Colors.DIM)
```

skill 的 config 值存在 `skills.config.<key>` 下(`agent/skill_utils.py:817` 的
`resolve_skill_config_values` docstring 明写 "Skill config is stored under
``skills.config.<key>`` in config.yaml"),而 SKILL.md frontmatter 声明的 config var
**没有 secret/password 标记位**。`agent/skill_utils.py:817-819 @ 863e313`

```python
def resolve_skill_config_values(
    config_vars: List[Dict[str, Any]],
) -> Dict[str, Any]:
```

怎么会踩到:任何 skill 声明一个形如 `MYSKILL_API_KEY` 的 config var,用户
`hermes config set skills.config.MYSKILL_API_KEY sk-...` 之后,`hermes config` 会把它**原文打印到终端**
(而同一份值如果写在 `.env` 里就会被 `redact_key` 打码)。整段同样被 `except Exception: pass` 兜住
(`hermes_cli/config.py:4455-4456`),所以 skill 目录异常时这一节会静默消失。

#### (h) 页脚

`hermes_cli/config.py:4460-4462 @ 863e313`

```python
    print(color("  hermes config edit     # Edit config file", Colors.DIM))
    print(color("  hermes config set <key> <value>", Colors.DIM))
    print(color("  hermes setup           # Run setup wizard", Colors.DIM))
```

——这行印证了 §0 的判断:向导入口是 `hermes setup`,不是 docstring 里写的 `hermes config wizard`。

---

## 3. `edit_config`:编辑器解析的平台感知回退链

**问题**:headless 服务器上没有 `code`,Windows 上没有 `nano`;硬编码单一编辑器会把用户卡死。

`hermes_cli/config.py:4466-4476 @ 863e313`

```python
def edit_config():
    """Open config file in user's editor."""
    if is_managed():
        managed_error("edit configuration")
        return
    config_path = get_config_path()
    
    # Ensure config exists
    if not config_path.exists():
        save_config(DEFAULT_CONFIG, strip_defaults=False)
        print(f"Created {config_path}")
```

**fallback 链**:`$EDITOR` → `$VISUAL` → 平台候选列表。`hermes_cli/config.py:4479 @ 863e313`

```python
    editor = os.getenv('EDITOR') or os.getenv('VISUAL')
```

(顺带记一笔:POSIX 惯例通常是 `VISUAL` 优先于 `EDITOR`,这里是反的。属于小的惯例偏离,无害。)

平台候选列表,注释解释了排序理由。`hermes_cli/config.py:4488-4491 @ 863e313`

```python
        if _sys.platform == "win32":
            candidates = ['notepad', 'code', 'vim', 'vi', 'nano']
        else:
            candidates = ['nano', 'vim', 'vi', 'code', 'notepad']
```

最后 `subprocess.run([editor, str(config_path)])`——**不检查返回码**,编辑器崩了也当成功。
`hermes_cli/config.py:4503 @ 863e313`

```python
    subprocess.run([editor, str(config_path)])
```

注意 `import shutil` / `import sys as _sys` 是函数内 import(`hermes_cli/config.py:4486-4487`),
而两者在模块顶部 **已经 import 过**(`hermes_cli/config.py:23,26`)。这是冗余但无害的死 import。

---

## 4. cron 模型漂移守卫:写配置时的"预警"机制

这是本段最有设计密度的一簇,解决的是一个**跨子系统的花钱安全问题**。

### 4.1 问题场景

cron 里有一批"未钉死模型/provider"的 agent 定时任务。它们在创建时对当时的全局 model/provider
拍了个快照(`model_snapshot` / `provider_snapshot`)。cron 调度器**故意 fail-closed**:
如果开火时全局值与快照不一致,任务直接失败而不是偷偷用新模型跑
(否则用户把全局模型从便宜的换成贵的,几十个定时任务会在夜里静默烧钱)。

**痛点**:用户执行 `hermes config set model <new>` 时不会有任何提示,
第一次知道出事是在下一次 tick 失败的时候。这一簇就是把那个信号**提前到写配置的瞬间**。

`hermes_cli/config.py:4578-4588 @ 863e313`

```python
def warn_unpinned_cron_jobs_after_model_config_change(
    key: str,
    value: Any,
    config: Optional[Dict[str, Any]] = None,
) -> None:
    """Warn when a global model/provider change will trip cron's drift guard.

    Cron intentionally fails closed when an unpinned agent job's current global
    model/provider differs from its creation-time snapshot. Surface that outcome
    when the operator changes the global axis instead of letting the next tick
    be the first visible signal.
    """
```

### 4.2 四段式实现

**第一段:key → 轴映射。** 把多种 key 拼写归一到两根"轴"。`hermes_cli/config.py:4506-4513 @ 863e313`

```python
def _cron_model_drift_axis_for_config_key(key: str) -> Optional[str]:
    """Return the cron drift guard axis affected by a config key, if any."""
    normalized = str(key or "").strip().lower()
    if normalized in {"model", "model.default", "model.model", "model.name"}:
        return "model"
    if normalized in {"model.provider", "provider"}:
        return "provider"
    return None
```

注意 `model.model` / `model.name` 也被认成 model 轴——这与 `_normalize_root_model_keys`
处理的历史别名集一致(见 §5.4)。

**第二段:守卫开关。只有字面量 `false` 能关掉它。** `hermes_cli/config.py:4516-4536 @ 863e313`

```python
def cron_model_drift_guard_enabled(
    config: Optional[Dict[str, Any]] = None,
) -> bool:
```

`hermes_cli/config.py:4536 @ 863e313`

```python
    return cron_config.get("model_drift_guard", True) is not False
```

`is not False` 而不是 truthiness:`0`、`""`、`"no"`、`null` 全部保持 fail-closed。
只有 YAML 里写 `model_drift_guard: false` 解析成 Python `False` 才关。
`DEFAULT_CONFIG["cron"]["model_drift_guard"]` 也是 `True`(我 exec 了 config_defaults 确认)。
配置缺失/非 dict 时也返回 True(`hermes_cli/config.py:4530-4535`)。

**第三段:cron 车队默认值是否已覆盖该轴。** 如果用户设了 `cron.model` / `cron.model_provider`,
未钉死的任务就不再跟随全局值,守卫压根不会触发,此时告警是误报。`hermes_cli/config.py:4539-4548 @ 863e313`

```python
def _cron_fleet_default_covers_axis(
    axis: str,
    config: Optional[Dict[str, Any]] = None,
) -> bool:
    """True when cron.model / cron.model_provider covers *axis*.

    An axis covered by the explicit cron-fleet default no longer follows the
    global model/provider at fire time, so the drift guard never engages for
    it and switch-time warnings would be false alarms.
    """
```

`hermes_cli/config.py:4559-4561 @ 863e313`

```python
    key = "model" if axis == "model" else "model_provider"
    value = cron_config.get(key)
    return isinstance(value, str) and bool(value.strip())
```

**注意轴名与配置键名不对称**:轴叫 `provider`,配置键叫 `cron.model_provider`
(`DEFAULT_CONFIG["cron"]` 里同时存在 `provider` 和 `model_provider` 两个键,
这里只查 `model_provider`)。这是个**容易踩的坑**:用户如果设了 `cron.provider` 而非
`cron.model_provider`,本函数返回 False,于是会收到一条其实是误报的告警。

**第四段:读 cron 任务库并计数。** 委托 `cron.jobs.load_jobs` 以复用它的 BOM 处理/损坏修复/
上下文局部 store 解析;任何失败一律回退空列表,**保证写配置永远不会因为 cron 库坏了而失败**。
`hermes_cli/config.py:4564-4575 @ 863e313`

```python
def _load_cron_jobs_for_config_warning() -> List[Dict[str, Any]]:
    """Best-effort read of the active profile's cron jobs database.

    Delegates to ``cron.jobs.load_jobs`` to reuse its BOM handling, corruption
    repair, and context-local store resolution (tests, embedders). Falls back
    to an empty list on any failure so config writes never break.
    """
    try:
        from cron.jobs import load_jobs
        return load_jobs()
    except Exception:
        return []
```

筛选逻辑:跳过 disabled、跳过 `no_agent`、跳过已钉死该轴的、只数快照与新值不同的。
`hermes_cli/config.py:4609-4618 @ 863e313`

```python
    for job in _load_cron_jobs_for_config_warning():
        if not job.get("enabled", True):
            continue
        if job.get("no_agent"):
            continue
        if str(job.get(pinned_field) or "").strip():
            continue
        snapshot = str(job.get(snapshot_field) or "").strip().lower()
        if snapshot and snapshot != new_value:
            affected += 1
```

告警文案自带修复命令。`hermes_cli/config.py:4625-4632 @ 863e313`

```python
    print(
        f"⚠️  {affected} enabled unpinned cron {noun} {verb} stored "
        f"{snapshot_field} values that differ from the new global {axis}. "
        "They will fail closed on their next run instead of silently using the "
        "changed model/provider. Inspect with `hermes cron list`, then pin the "
        "intended values with `cronjob action=update job_id=<job_id> "
        "provider=<provider> model=<model>`."
    )
```

### 4.3 取舍与两个可疑点

**取舍**:告警是"尽力而为"的——所有失败路径都 fail-open 成"不告警",绝不阻塞配置写入。
这是正确的优先级(配置写入是用户主动行为,不能被诊断逻辑劫持),但意味着告警可能静默缺失。

**可疑点 ①(告警传入的是 raw user_config,不是 merged config)**:唯一调用点在
`set_config_value` 末尾,传的是刚写盘的**原始用户 config**。`hermes_cli/config.py:5027 @ 863e313`

```python
    warn_unpinned_cron_jobs_after_model_config_change(key, value, user_config)
```

后果:如果用户从未在 config.yaml 写过 `cron:` 段,`_cron_fleet_default_covers_axis` 拿不到
`DEFAULT_CONFIG["cron"]["model"]`。所幸默认值是空串 `''`,覆盖判定本来也是 False,
所以当前**行为上等价**。但这是个脆弱的巧合:如果哪天 `DEFAULT_CONFIG["cron"]["model"]` 被填上非空默认值,
这里就会开始误报。而 `cron_model_drift_guard_enabled(user_config)` 同理——
raw config 缺 `cron` 段时返回 True,恰好与 DEFAULT 一致。

**可疑点 ②(unset 路径没有对称的告警)**:`unset_config_value` 从头到尾**不调用**这个告警函数
(我通读了 5062-5124 全段)。`hermes config unset model` 会把全局模型抹回默认空串,
同样会让未钉死的 cron 任务在下次 tick fail-closed,但用户拿不到任何提示。
这是 set/unset 之间的**功能不对称**。

---

## 5. 写入面:`set_config_value` —— 本段的主函数

签名与 `--force` 的双重语义(既跳过未知键提示,又授权用标量覆盖整个映射段)。
`hermes_cli/config.py:4823-4835 @ 863e313`

```python
def set_config_value(key: str, value: str, force: bool = False):
    """Set a configuration value.

    Args:
        key: Dotted config path (e.g. ``terminal.backend``).
        value: String value (auto-coerced to bool/int/float when matching).
        force: When True, skip the unknown-key warning — useful for scripted
            writes of keys the running version doesn't recognize yet — AND
            authorize destructive replacement of a mapping section by a
            scalar (e.g. ``--force model gpt-x`` replaces the whole ``model:``
            mapping). Without --force, scalar writes over mapping sections are
            refused (bare ``model`` is redirected to ``model.default``). The
            CLI exposes this via ``hermes config set --force``.
    """
```

它是一条很长的流水线,我按执行顺序拆:

### 5.1 两道管理闸门(注意它们是**两种不同**的"managed")

**闸门 A:`is_managed()`** —— 包管理器写锁(NixOS 声明式安装),整个配置文件不可写。
`hermes_cli/config.py:4837-4839 @ 863e313`

```python
    if is_managed():
        managed_error("set configuration values")
        return
```

注意这里是 `return`(退出码 0),不是 `sys.exit(1)`。

**闸门 B:managed scope(D2)** —— 管理员在 `/etc/hermes/config.yaml` 里钉死了**某个具体 key**。
`hermes_cli/config.py:4840-4845 @ 863e313`

```python
    # Managed scope guard (D2): a key pinned by the managed layer cannot be set by
    # the user — the next load would override it anyway. Hard-reject and name the
    # source. Distinct from is_managed() above (the package-manager write-lock).
    # Env-shaped keys (API keys / tokens) route to save_env_value below, which has
    # its own managed-env-key guard; this catches the config.yaml keys.
    from hermes_cli import managed_scope
```

`hermes_cli/config.py:4847-4855 @ 863e313`

```python
    if managed_scope.is_key_managed(key):
        managed_dir = managed_scope.get_managed_dir()
        src = (managed_dir / "config.yaml") if managed_dir else "the managed scope"
        print(
            f"Cannot set '{key}': it is managed by your administrator ({src}) "
            f"and cannot be changed. Contact your administrator to modify it.",
            file=sys.stderr,
        )
        sys.exit(1)
```

判定是**精确点分键匹配**,不是前缀匹配。`hermes_cli/managed_scope.py:207-209 @ 863e313`

```python
def is_key_managed(dotted_key: str) -> bool:
    """True if the exact dotted config key is pinned by the managed layer."""
    return dotted_key in managed_config_keys()
```

**可疑点**:精确叶子匹配意味着管理员钉死 `model.default` 后,用户仍可执行
`hermes config set model foo`(裸 `model` 不在扁平叶子集合里)——虽然那条路会被 §5.6 的
"裸 model 重定向"改写成 `model.default` **在闸门之后**,于是最终写进用户 config.yaml 的正是被托管的键。
下一次 `load_config` 时 managed 覆盖层会再把它盖回去,所以**行为无害但用户会收到一条误导性的 `✓ Set` 成功回显**。

### 5.2 env 键分流

`hermes_cli/config.py:4857-4864 @ 863e313`

```python
    if _is_env_config_key(key):
        # Unified lifecycle: also rotates any config.yaml mirror of the old
        # value so a stale higher-precedence copy can't win (#62269).
        from hermes_cli.credential_lifecycle import save_provider_env_credential

        save_provider_env_credential(key.upper(), value)
        print(f"✓ Set {key} in {get_env_path()}")
        return
```

分流规则:**含 `.` 一律不是 env 键**;否则大写后命中显式白名单,或以 `_API_KEY`/`_TOKEN`/`_SECRET`
结尾,或以 `TERMINAL_SSH` 开头。`hermes_cli/config.py:1152-1156 @ 863e313`

```python
def _is_env_config_key(key: str) -> bool:
    """Return whether `hermes config set` routes this key to .env."""
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

**设计要点**:走的是 `credential_lifecycle.save_provider_env_credential` 而不是裸 `save_env_value`
——它顺带清理 config.yaml 里同值的镜像副本,防止"优先级更高的陈旧拷贝"赢回去(#62269)。
`hermes_cli/credential_lifecycle.py:213 @ 863e313`

```python
def save_provider_env_credential(env_var: str, value: str) -> Dict[str, Any]:
```

### 5.3 schema 校验(**先算,后用**)

`hermes_cli/config.py:4866-4873 @ 863e313`

```python
    # Unknown-key notice (#34067): the key is still written (arbitrary keys
    # are supported — top-level scalars are bridged into os.environ for
    # skills and external apps), but a plausible-but-wrong dotted path like
    # ``gateway.discord.gateway_restart_notification`` previously reported
    # bare success and left the user debugging behavior that never changed.
    # Warn after the write so the user gets immediate feedback plus a
    # "did you mean" hint, without blocking legitimate unknown keys.
    is_known, suggestion = _validate_config_key(key)
```

校验器本身:`hermes_cli/config.py:4727-4743 @ 863e313`

```python
def _validate_config_key(key: str) -> tuple[bool, Optional[str]]:
    """Validate a dotted config-key path against the known schema.

    Returns ``(is_known, suggested_alternative_or_None)``.  Known keys
    return ``(True, None)``.  Unknown keys return ``(False, <suggestion>)``
    where ``<suggestion>`` may be ``None`` if no close match was found.

    Validates as deep as DEFAULT_CONFIG can be safely walked, then stops
    at any segment that hits an open-dict container (mcp_servers,
    providers, hooks, etc.) where users define the inner keys themselves.

    Headline case from #34067: ``gateway.discord.gateway_restart_notification``
    was silently written, even though ``gateway`` only has 4 known sub-keys
    (``strict``, ``media_delivery_allow_dirs``, ``trust_recent_files``,
    ``trust_recent_files_seconds``). The correct path is
    ``discord.gateway_restart_notification`` (platform configs live at the
    top level, not under a ``platforms`` namespace).
    """
```

它把 key 空间切成五类:

**(1) 下划线开头的首段 = 内部/测试标记,直接放行。** `hermes_cli/config.py:4761-4762 @ 863e313`

```python
    if top.startswith("_"):
        return True, None
```

注释明说只检首段,所以真正的错字 `agent._max_turns` 仍会在子键层被抓到
(`hermes_cli/config.py:4759-4760`)。测试 `TestValidateConfigKey::test_underscore_only_first_segment_escapes` 是这条的行为规格。

**(2) `platforms` 容器,下面全放行。** `hermes_cli/config.py:4695 @ 863e313`

```python
_PLATFORM_CONTAINER_KEYS = frozenset({"platforms"})
```

`hermes_cli/config.py:4770-4771 @ 863e313`

```python
    if top in _PLATFORM_CONTAINER_KEYS:
        return True, None
```

**(3) 开放字典顶层键**——schema 声明容器、用户填内部键。`hermes_cli/config.py:4654-4667 @ 863e313`

```python
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

**(4) 半 schema 化的字典**(PlatformConfig dataclass + 动态 extras)。`hermes_cli/config.py:4673-4680 @ 863e313`

```python
_SCHEMA_DEFINED_DICT_KEYS = frozenset({
    # Platform configs — PlatformConfig dataclass + dynamic extras
    "discord", "telegram", "slack", "whatsapp", "signal", "mattermost",
    "matrix", "feishu", "wecom", "weixin", "bluebubbles", "qqbot", "yuanbao",
    "email", "sms", "dingtalk",
    # MCP server template / dynamic auth dicts
    "sessions", "checkpoints",
})
```

**(5) 动态顶层键**(当前只有一个 list 形状的)。`hermes_cli/config.py:4684-4686 @ 863e313`

```python
_DYNAMIC_TOP_LEVEL_KEYS = frozenset({
    "custom_providers",  # list-shaped, but indexed by position
})
```

已知顶层键 = DEFAULT_CONFIG 的键 ∪ 上述三类。`hermes_cli/config.py:4706-4710 @ 863e313`

```python
    keys = set(DEFAULT_CONFIG.keys())
    keys.update(_OPEN_DICT_TOP_LEVEL_KEYS)
    keys.update(_DYNAMIC_TOP_LEVEL_KEYS)
    keys.update(_SCHEMA_DEFINED_DICT_KEYS)
    return keys
```

**"你是不是想写"** 用 `difflib.get_close_matches`,cutoff 0.6,注释解释了保守取舍
("宁可不说,也不要把人指向一个相似但错误的键")。`hermes_cli/config.py:4722-4724 @ 863e313`

```python
    import difflib
    matches = difflib.get_close_matches(key, sorted(candidates), n=1, cutoff=cutoff)
    return matches[0] if matches else None
```

**深层遍历**:命中三类开放容器就整段放行;否则沿 DEFAULT_CONFIG 走,遇标量叶子放行,
遇未知子键返回同层的相近兄弟。`hermes_cli/config.py:4788-4792 @ 863e313`

```python
    if top in _OPEN_DICT_TOP_LEVEL_KEYS or top in _DYNAMIC_TOP_LEVEL_KEYS or top in _SCHEMA_DEFINED_DICT_KEYS:
        # Any path below these is accepted — the user defines the inner
        # shape themselves (mcp_servers.<name>.command, discord.<extras>,
        # providers.<name>.api_key, etc.).
        return True, None
```

`hermes_cli/config.py:4808-4814 @ 863e313`

```python
        if seg not in node:
            # Suggest the closest sibling at this depth.
            sibling_suggestion = _suggest_closest_key(seg, set(node.keys()))
            if sibling_suggestion is not None:
                fixed_path = ".".join(consumed + [sibling_suggestion])
                return False, fixed_path
            return False, None
```

**取舍**:这是**提示器不是拦截器**——未知键照写不误,只在写完之后打一条黄色提示(§5.9)。
理由写在 4866-4872 的注释里:任意顶层标量键会被桥接进 `os.environ` 给 skill / 外部工具用,
拦截会破坏这个合法用法。

### 5.4 读取原始 config + 不可读即拒写

`hermes_cli/config.py:4878-4879 @ 863e313`

```python
    config_path = get_config_path()
    require_readable_config_before_write(config_path)
```

这个守卫解决的问题非常具体:`read_raw_config()` 对"文件不存在"和"文件存在但读不了"
都返回 `{}`,调用方分不清,于是可能把一个读不出来的 config.yaml 覆盖成只剩本次编辑的那一段。
`hermes_cli/config.py:3065-3066 @ 863e313`

```python
def require_readable_config_before_write(config_path: Optional[Path] = None) -> None:
    """Refuse to replace an existing config.yaml that cannot be read."""
```

它做两级检查:`stat()`(FileNotFoundError 放行,其他 OSError 抛)与"实际读 1 字节"。
`hermes_cli/config.py:3079-3086 @ 863e313`

```python
    try:
        with open(config_path, "rb") as f:
            f.read(1)
    except OSError as exc:
        raise RuntimeError(
            f"Refusing to overwrite {config_path}: existing config.yaml cannot be read "
            f"({exc}). Fix the file permissions or move it aside first."
        ) from exc
```

**文档-代码出入 ②**:`atomic_config_write` 的 docstring 自称是"每条配置更新路径都应该用的**唯一**闸口,
不要直接调 `utils.atomic_yaml_write`"。`hermes_cli/config.py:3089-3094 @ 863e313`

```python
def atomic_config_write(config_path: Path, data: Any, **kwargs: Any) -> None:
    """Fail-closed atomic write for ``config.yaml``.

    The single chokepoint every config-update path should use instead of
    calling :func:`utils.atomic_yaml_write` directly. It runs
    :func:`require_readable_config_before_write` first, so a full-file
```

但本段的两条写路径(`set_config_value` / `unset_config_value`)**都绕过了这个闸口**,
各自手工调守卫再直接调 `atomic_yaml_write`。`hermes_cli/config.py:4993-4995 @ 863e313`

```python
    ensure_hermes_home()
    from utils import atomic_yaml_write
    atomic_yaml_write(config_path, user_config, sort_keys=False)
```

行为上等价(守卫在 4879 已经跑过),但 "single chokepoint" 的说法与代码不符,
且这种复制粘贴式的不变量维护正是该 docstring 想消灭的东西。

YAML 解析失败时**硬失败退出 1**,并给出可执行的修复指引——不像 `load_config()` 那样静默退回默认值。
这是有意的:写路径必须 fail-closed,否则用户的整份 config.yaml 会被"defaults + 这一次编辑"替换掉。
`hermes_cli/config.py:4885-4893 @ 863e313`

```python
        except Exception as exc:
            print(
                f"✗ Cannot parse {config_path}: {exc}\n"
                f"  The file contains a YAML syntax error. Fix the error\n"
                f"  in your config file first, then retry.\n"
                f"  (hermes config edit will open it in your editor.)",
                file=sys.stderr,
            )
            sys.exit(1)
```

行为规格:`TestMalformedYAMLConfigPreservation::test_set_config_value_refuses_broken_yaml`
与 `..._unset_config_value_refuses_broken_yaml`(`tests/hermes_cli/test_set_config_value.py:700,713`)。

### 5.5 类型强制:由 DEFAULT_CONFIG 的叶子类型反查

**问题**:CLI 传进来的永远是字符串。`approvals.mode=off` 如果被当成布尔,枚举成员就毁了。

`hermes_cli/config.py:4900-4912 @ 863e313`

```python
    # Preserve values for string-typed settings.  In particular, enum members
    # such as approvals.mode="off" must not become YAML booleans.  Unknown keys
    # retain the historical best-effort coercion behavior.
    coerced_value: Any = value
    if not isinstance(_default_value_for_key(key), str):
        if value.lower() in {'true', 'yes', 'on'}:
            coerced_value = True
        elif value.lower() in {'false', 'no', 'off'}:
            coerced_value = False
        elif value.isdigit():
            coerced_value = int(value)
        elif value.replace('.', '', 1).isdigit():
            coerced_value = float(value)
```

判定依据来自 DEFAULT_CONFIG 的叶子值类型:`hermes_cli/config.py:4635-4646 @ 863e313`

```python
def _default_value_for_key(dotted_key: str):
    """Return the leaf value declared for *dotted_key* in ``DEFAULT_CONFIG``.

    Unknown keys and non-leaf paths return ``None`` so they retain the legacy
    best-effort coercion used by ``config set``.
    """
    node = DEFAULT_CONFIG
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if not isinstance(node, dict) else None
```

**可疑点(未知键的数字强制是个脚枪)**:`providers.*`、`mcp_servers.*` 在 DEFAULT_CONFIG 里
是空 dict(`DEFAULT_CONFIG["providers"] = {}`,我 exec 确认),所以任何
`providers.<name>.api_key` 都拿不到 str 类型的默认值 → 走强制分支。
于是 `hermes config set providers.foo.api_key 12345678` 会把一个**纯数字 API key 写成 YAML int**,
后续读出来是 `int`,并且**连 `redact_config_value` 都不会给它打码**(§2.2 要求 `isinstance(v, str)`)。
同理 `mcp_servers.x.command 123`、`model.default 4` 都会被转成数字。
行为规格里 `TestStringTypedConfigValues::test_unknown_keys_keep_existing_coercion`
(`tests/hermes_cli/test_set_config_value.py:378`)**把这条当成"保留历史行为"钉住了**,
说明作者知道并接受这个后果。

### 5.6 三道"别把用户的东西弄没了"的结构守卫

**守卫 A:标量 `model` 被写 `model.*` 子键时先升格成 dict。** 否则 `_set_nested`
会把字符串换成空 dict,model id 永久丢失。`hermes_cli/config.py:4920-4924 @ 863e313`

```python
    _model_key = key.strip().lower()
    if _model_key.startswith("model."):
        _model_val = user_config.get("model")
        if isinstance(_model_val, str) and _model_val:
            user_config["model"] = {"default": _model_val}
```

行为规格:`TestScalarModelSubKeyPreservation`(`tests/hermes_cli/test_set_config_value.py:663`)。

**守卫 B:单段键覆盖既有映射段(#74995)。** 裸 `model` 是**有文档的简写**,重定向到 `model.default`;
其他映射段一律拒绝,除非 `--force`。`hermes_cli/config.py:4925-4934 @ 863e313`

```python
    # Guard against #74995: a single-segment key that names an existing
    # mapping would silently overwrite the entire section with a scalar
    # (e.g. ``hermes config set model gpt-5.6-sol`` when model already
    # contains default/provider/context_length).  Bare ``model`` is a
    # documented shorthand — redirect to ``model.default`` and preserve
    # siblings.  All other mapping sections are rejected unless --force.
    if "." not in key:
        _existing = user_config.get(key)
        if isinstance(_existing, dict):
            if key == "model":
```

`hermes_cli/config.py:4944-4948 @ 863e313`

```python
                    key = "model.default"
                    print(
                        f"✓ Redirecting bare 'model' to 'model.default' "
                        f"(preserving {len(_existing)} existing model sub-key(s))"
                    )
```

拒绝分支的报错信息很用心:列出前 8 个子键、给出点分路径写法、给出 `--force` 写法。
`hermes_cli/config.py:4950-4959 @ 863e313`

```python
            elif not force:
                _sub = [k for k in _existing if isinstance(k, str)]
                print(
                    f"✗ Cannot set '{key}' to a scalar — '{key}' is a "
                    f"configuration section with {len(_sub)} sub-key(s).",
                    file=sys.stderr,
                )
                if _sub:
                    _sub_list = ", ".join(_sub[:8])
                    print(f"  Sub-keys: {_sub_list}", file=sys.stderr)
```

**注意**:守卫 B 只在**用户 config.yaml 里已经写成 dict** 时才触发(读的是 raw `user_config`,
不是 merged config)。这是对的——否则每个 DEFAULT_CONFIG 里是 dict 的顶层键都会被误拦。
行为规格:`TestMappingGuard` 六个用例(`tests/hermes_cli/test_set_config_value.py:574`)。

**守卫 C:`_set_nested` 保护 list 类型(#17876)。** `hermes_cli/config.py:4982 @ 863e313`

```python
    _set_nested(user_config, key, value)
```

`_set_nested` 的 docstring 记录了这条:修复前它无条件把任何非 dict 值(包括 list)替换成 `{}`,
用户的 `custom_providers` 列表会在任何一次带索引路径的写入中被静默摧毁。`hermes_cli/config.py:1009-1012 @ 863e313`

```python
    Guards against #17876: before this fix the code unconditionally
    replaced any non-dict value (including lists) with ``{}``, silently
    destroying list-typed config like ``custom_providers`` whenever a
    caller used an indexed path.
```

行为规格:`TestListNavigation` 三个用例(`tests/hermes_cli/test_set_config_value.py:198`)。

### 5.7 `api_base` 别名归一(issue #8919)

`hermes_cli/config.py:4983-4991 @ 863e313`

```python
    # Normalize the api_base → base_url alias at set-time too (issue #8919),
    # so a fresh `hermes config set model.api_base ...` lands on the canonical
    # key the runtime resolver actually reads, instead of being silently
    # ignored. Mirrors the load-time migration in _normalize_root_model_keys.
    _alias_norm = key.strip().lower()
    if _alias_norm in ("model.api_base", "api_base"):
        user_config = _normalize_root_model_keys(user_config)
        key = "model.base_url"
        print("  (note: 'api_base' is an alias — saved as model.base_url)")
```

对应的 load 期迁移函数把三件事一起做了(根级键下沉、`api_base`→`base_url`、model id 归一到
`model.default`)。`hermes_cli/config.py:2756-2762 @ 863e313`

```python
    Also aliases ``api_base`` → ``base_url`` (issue #8919). ``api_base`` is the
    intuitive name OpenAI-SDK / LiteLLM users reach for, and ``hermes config set``
    blindly accepts any dotted key — so ``model.api_base`` got written, confirmed,
    and then silently ignored by the runtime resolver (which reads only
    ``model.base_url``), causing requests to fall back to OpenRouter. We migrate
    the alias to the canonical key (fallback-only — never override an explicit
    ``base_url``) and drop the alias so it can't confuse later loads.
```

`model.name` 的教训更狠:显示路径(`hermes status` / `dump`)读 `name` 所以**看得见模型**,
但请求路径读 `default` 所以发出去的是空 model → HTTP 400,失败完全静默。
`hermes_cli/config.py:2764-2775 @ 863e313`

```python
    Finally, canonicalizes the model-id key to ``model.default`` (issue #34500).
    The runtime resolver and ~14 other readers select the chat model via
    ``model.default``; ``model.model`` was already aliased inline at some sites
    but ``model.name`` was not, so a custom-provider config like
    ``model: {name: <id>, provider: <custom>}`` resolved to an empty model and
    the API request went out with ``model=`` (HTTP 400 from OpenAI-compatible
    backends) — while display paths (``hermes status``/``dump``) read ``name``
    and *showed* the model, making the failure silent. Normalizing here (the
    single load/save chokepoint) means every reader, present and future, sees a
    populated ``default`` and the stale alias is migrated out of config.yaml on
    the next save. Precedence: ``default`` > ``model`` > ``name`` (never
    overrides an explicit ``default``, so existing configs are unaffected).
```

### 5.8 写盘后的三个副作用

**副作用 1:`terminal.*` 镜像进 `.env`。** 原因:`tools.terminal_tool` 是环境变量驱动的
(它也跑在 TUI / dashboard PTY / gateway worker 这些子进程里)。`hermes_cli/config.py:4997-5001 @ 863e313`

```python
    # Keep .env in sync for keys that terminal_tool reads directly from env vars.
    # config.yaml is authoritative, but terminal_tool only reads TERMINAL_ENV etc.
    env_var = terminal_config_env_var_for_key(key)
    if env_var and key != "terminal.cwd":
        save_env_value(env_var, _terminal_env_value(value))
```

映射表以 `terminal.` 前缀去掉后的子键为索引。`hermes_cli/config.py:3223-3228 @ 863e313`

```python
def terminal_config_env_var_for_key(key: str) -> Optional[str]:
    """Return the env var mirrored by a ``terminal.*`` config key."""
    prefix = "terminal."
    if not key.startswith(prefix):
        return None
    return TERMINAL_CONFIG_ENV_MAP.get(key[len(prefix):])
```

表本身从 `hermes_cli/config.py:3183` 开始。`hermes_cli/config.py:3183-3184 @ 863e313`

```python
TERMINAL_CONFIG_ENV_MAP = {
    "backend": "TERMINAL_ENV",
```

list/dict 值以 JSON 序列化后塞进 env。`hermes_cli/config.py:3217-3220 @ 863e313`

```python
def _terminal_env_value(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)
```

`terminal.cwd` 被**显式排除**(4999-5000 与 unset 路径的 5114 都排除),说明工作目录不走 env 桥。

**副作用 2:`display.skin` 的 mtime 触碰。** gateway 的皮肤 watcher 用 `(name, mtime)` 做签名,
所以"重新确认同一个皮肤"必须让 mtime 动一下,否则 watcher 认为无变化。
`hermes_cli/config.py:5003-5014 @ 863e313`

```python
    # Setting display.skin is an explicit "apply NOW" — bump the skin file's
    # mtime so the gateway watcher's (name, mtime) signature moves even when the
    # name is unchanged (re-affirming the active skin after a surface missed the
    # original activation). Built-ins have no file; a name switch already moves
    # their signature.
    if key == "display.skin" and isinstance(value, str) and value:
        try:
            skin_file = get_hermes_home() / "skins" / f"{value}.yaml"
            if skin_file.exists():
                skin_file.touch()
        except Exception:
            pass  # best-effort: the config write above already succeeded
```

行为规格:`TestDisplaySkinTouch` 三个用例(`tests/hermes_cli/test_set_config_value.py:528`)。

**副作用 3:回显打码。** 走 config.yaml 的小写 key(如 `model.api_key`)不会被 §5.2 的
`.env` 白名单捕获,所以这里按**叶子段**再判一次。`hermes_cli/config.py:5020-5026 @ 863e313`

```python
    _leaf_key = key.rsplit(".", 1)[-1].lower()
    if _leaf_key in _SECRET_CONFIG_KEYS and isinstance(value, str) and value:
        from agent.redact import mask_secret
        _display_value = mask_secret(value)
    else:
        _display_value = value
    print(f"✓ Set {key} = {_display_value} in {config_path}")
```

行为规格:`TestSecretRedactionInDisplay`(`tests/hermes_cli/test_set_config_value.py:392`)。

### 5.9 未知键的事后提示

`hermes_cli/config.py:5029-5038 @ 863e313`

```python
    # Post-write unknown-key notice (#34067): value IS saved, but tell the
    # user the runtime may never read it and suggest the likely-intended path.
    if not is_known and not force:
        print(color(
            f"⚠ '{key}' is not a recognized config key — it was saved anyway, "
            "but Hermes may not read it.",
            Colors.YELLOW,
        ))
        if suggestion:
            print(color(f"  Did you mean: {suggestion}", Colors.YELLOW))
```

**注意提示里用的 `key` 是可能已被重写过的**(裸 model→`model.default`,`api_base`→`model.base_url`),
而 `is_known`/`suggestion` 是用**原始 key** 算的。理论上会出现"提示说 `model.base_url` 不被识别"
的错配;实际上这两条重写路径的原始 key(`model` / `model.api_base`)都会验证为 known,
所以 `is_known` 为 True、分支不进入。**当前无害,但耦合是脆的。**

### 5.10 并发写:无锁

`set_config_value` 读 config.yaml → 改 → `atomic_yaml_write`。`atomic_yaml_write` 保证
**单次写是原子的**(临时文件 + rename),但**读-改-写整体没有加锁**。
两个并发的 `hermes config set`(比如脚本里并行跑)会互相丢失一次写。
本段代码中我没有找到任何跨进程文件锁(对照:`_load_config_impl` 用的 `_CONFIG_LOCK`
是**进程内** threading 锁,`hermes_cli/config.py:3284`)。

```python
    with _CONFIG_LOCK:
```

---

## 6. `get_config_value` / `unset_config_value`

### 6.1 get:**不打码**

`hermes_cli/config.py:5047-5059 @ 863e313`

```python
def get_config_value(key: str, *, as_json: bool = False):
    """Print a resolved configuration value."""
    if _is_env_config_key(key):
        env_value = get_env_value(key.upper())
        value = _MISSING if env_value is None else env_value
    else:
        value = _get_nested(load_config(), key)

    if value is _MISSING:
        print(f"Config key not set: {key}", file=sys.stderr)
        sys.exit(1)

    print(_format_config_get_value(value, as_json=as_json))
```

三点:
1. `_MISSING` 哨兵(`hermes_cli/config.py:1070` 的 `_MISSING = object()`)把"键不存在"与"值是 None"区分开——
   `hermes config get some.null_key` 会打印 `null` 并退出 0,而不存在的键退出 1。
2. `hermes config get OPENROUTER_API_KEY` **原样打印密钥,不脱敏**。与 `set` 的回显打码(§5.8)
   形成明显不对称。合理解释:`get` 是脚本取值接口,打码会让它没法用。但这是个需要知道的事实。
3. 读的是 `load_config()`(合并默认值 + managed 覆盖),所以 `hermes config get agent.max_turns`
   即使用户没写过也会返回 500。

格式化规则:`hermes_cli/config.py:1175-1186 @ 863e313`

```python
def _format_config_get_value(value, *, as_json: bool) -> str:
    """Format a config value for command-line output."""
    if as_json:
        import json
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return yaml.safe_dump(value, sort_keys=False).rstrip()
    return str(value)
```

### 6.2 unset:与 set 镜像,但少三样

`hermes_cli/config.py:5062-5066 @ 863e313`

```python
def unset_config_value(key: str):
    """Remove a user-set configuration or .env value."""
    if is_managed():
        managed_error("unset configuration values")
        return
```

managed scope 闸门与 set 完全对称(`hermes_cli/config.py:5071-5079`)。
env 键走 `credential_lifecycle.remove_provider_env_credential`,它比裸删 `.env` 多做两件事:
清理 env 播种的 credential_pool 条目、清理 model-cache 行,避免 provider "复活"。
`hermes_cli/config.py:5081-5091 @ 863e313`

```python
    if _is_env_config_key(key):
        # Unified lifecycle: prune env-seeded credential_pool entries and
        # model-cache rows too, so `hermes config unset <KEY>` fully removes
        # the provider instead of leaving it resurrectable (#51071 family).
        from hermes_cli.credential_lifecycle import remove_provider_env_credential

        if not remove_provider_env_credential(key.upper()).get("found"):
            print(f"Config key not set: {key}", file=sys.stderr)
            sys.exit(1)
        print(f"✓ Unset {key} from {get_env_path()}")
        return
```

`hermes_cli/credential_lifecycle.py:245 @ 863e313`

```python
def remove_provider_env_credential(env_var: str) -> Dict[str, Any]:
```

删除本体 + env 镜像同步,任一成功即算 removed。`hermes_cli/config.py:5110-5119 @ 863e313`

```python
    removed = _unset_nested(user_config, key)

    # Keep .env in sync for keys that terminal_tool reads directly from env vars.
    env_var = terminal_config_env_var_for_key(key)
    if env_var and key != "terminal.cwd":
        removed = remove_env_value(env_var) or removed

    if not removed:
        print(f"Config key not set: {key}", file=sys.stderr)
        sys.exit(1)
```

`_unset_nested` 会**顺手清掉删除后残留的空 dict 容器**,但保留用户自己写的空 list。
`hermes_cli/config.py:1129-1131 @ 863e313`

```python
    # Drop empty dict containers left behind by the deletion while preserving
    # user-authored empty lists and non-empty sibling branches.
    for parent, part in reversed(parents):
        if current != {}:
```

**unset 相对 set 缺失的三样**(逐条对照 5062-5124 全文确认):
1. 无 cron 漂移告警(§4.3 可疑点 ②);
2. 无 `_validate_config_key` 未知键提示——`hermes config unset gateway.discord.foo` 静默报
   "Config key not set" 退 1,不给"你是不是想写"提示;
3. 无 `api_base` 别名归一——`hermes config unset model.api_base` 只会删掉别名键本身,
   如果 load 期已经把它迁成 `model.base_url` 并落盘,这条命令会报"未设置"。

---

## 7. 导出面 / 导入期钩子:两个 `OPTIONAL_ENV_VARS` 注入器

这是"文件末尾往往是导出面/兼容垫片/迁移钩子"的典型样本。它们**不是函数被谁调用**的问题——
它们在模块 import 时就跑,**副作用是修改一个别的模块拥有的字典对象**。

### 7.1 注入器 ①:provider profile

`hermes_cli/config.py:5298-5303 @ 863e313`

```python
# ── Profile-driven env var injection ─────────────────────────────────────────
# Any provider registered in providers/ with auth_type="api_key" automatically
# gets its env_vars exposed in OPTIONAL_ENV_VARS without editing this file.
# Runs once at import time.

_profile_env_vars_injected = False
```

幂等靠模块级布尔旗标。`hermes_cli/config.py:5311-5314 @ 863e313`

```python
    global _profile_env_vars_injected
    if _profile_env_vars_injected:
        return
    _profile_env_vars_injected = True
```

只吃 `auth_type == "api_key"` 的 provider;已存在的条目不覆盖(硬编码优先);
用后缀 `_BASE_URL`/`_URL` 反推"这不是密钥,是 base URL 覆盖"。`hermes_cli/config.py:5316-5331 @ 863e313`

```python
        from providers import list_providers
        for _pp in list_providers():
            if _pp.auth_type not in {"api_key",}:
                continue
            for _var in _pp.env_vars:
                if _var in OPTIONAL_ENV_VARS:
                    continue
                _is_key = not _var.endswith("_BASE_URL") and not _var.endswith("_URL")
                OPTIONAL_ENV_VARS[_var] = {
                    "description": f"{_pp.display_name or _pp.name} {'API key' if _is_key else 'base URL override'}",
                    "prompt": f"{_pp.display_name or _pp.name} {'API key' if _is_key else 'base URL (leave empty for default)'}",
                    "url": _pp.signup_url or None,
                    "password": _is_key,
                    "category": "provider",
                    "advanced": True,
                }
```

模块级立即调用:`hermes_cli/config.py:5336-5337 @ 863e313`

```python
# Eagerly inject so that OPTIONAL_ENV_VARS is fully populated at import time.
_inject_profile_env_vars()
```

### 7.2 注入器 ②:平台插件清单

解决的是"核心仓库不必知道 Teams / IRC / Google Chat 存在"。`hermes_cli/config.py:5340-5346 @ 863e313`

```python
# ── Platform-plugin env var injection ────────────────────────────────────────
# Bundled platform plugins under ``plugins/platforms/*/plugin.yaml`` declare
# their required env vars via ``requires_env``.  This mirror of
# ``_inject_profile_env_vars`` surfaces them in ``hermes config`` UI so users
# can configure Teams / IRC / Google Chat without the core repo ever needing
# to know they exist.
```

清单目录从 `__file__` 反推仓库根,与 CWD 无关。`hermes_cli/config.py:5376-5381 @ 863e313`

```python
        # Resolve the bundled plugins dir from this file's location so the
        # injector works regardless of CWD.
        repo_root = Path(__file__).resolve().parents[1]
        platforms_dir = repo_root / "plugins" / "platforms"
        if not platforms_dir.is_dir():
            return
```

`plugin.yaml` 与 `plugin.yml` 两种扩展名都试。`hermes_cli/config.py:5385-5389 @ 863e313`

```python
            manifest_path = child / "plugin.yaml"
            if not manifest_path.exists():
                manifest_path = child / "plugin.yml"
            if not manifest_path.exists():
                continue
```

`requires_env` 与 `optional_env` 合并成同一份条目列表;条目可以是裸字符串或富 dict。
`hermes_cli/config.py:5396-5407 @ 863e313`

```python
            # Merge required + optional env var declarations.
            entries = list(manifest.get("requires_env") or [])
            entries.extend(manifest.get("optional_env") or [])
            for entry in entries:
                if isinstance(entry, str):
                    name = entry
                    meta: dict = {}
                elif isinstance(entry, dict) and entry.get("name"):
                    name = entry["name"]
                    meta = entry
                else:
                    continue
```

密码字段的启发式判定:`hermes_cli/config.py:5410-5418 @ 863e313`

```python
                # Heuristic: anything named *TOKEN, *SECRET, *KEY, *PASSWORD
                # is a password field unless explicitly overridden.
                name_upper = name.upper()
                is_secret = bool(meta.get("password") or meta.get("secret"))
                if not is_secret and not meta.get("password") is False:
                    is_secret = any(
                        name_upper.endswith(suf)
                        for suf in ("_TOKEN", "_SECRET", "_KEY", "_PASSWORD", "_JSON")
                    )
```

**我一开始怀疑第 5414 行是运算符优先级笔误(以为它解析成 `(not X) is False`),
实测证伪**:Python 里比较运算符优先级**高于** `not`,所以 `not X is False` == `not (X is False)`,
等价于 `X is not False`。我跑了 `python3 -c 'print(not None is False, not False is False)'`
得到 `True False`——语义正确,只是写法触犯 flake8 E714(应写成 `is not`)。**记为风格问题,不是缺陷。**

### 7.3 两个注入器之间的一处**真实不一致**

注入器 ① 给每条记录加了 `"advanced": True`(`hermes_cli/config.py:5330`),注入器 ② **没有**。
`hermes_cli/config.py:5419-5428 @ 863e313`

```python
                OPTIONAL_ENV_VARS[name] = {
                    "description": (
                        meta.get("description")
                        or f"{label} configuration"
                    ),
                    "prompt": meta.get("prompt") or name,
                    "url": meta.get("url") or None,
                    "password": is_secret,
                    "category": meta.get("category") or "messaging",
                }
```

`advanced` 是 `hermes config migrate` 用来过滤"别把一屏高级选项糊到用户脸上"的旗标。
`hermes_cli/config.py:5211-5214 @ 863e313`

```python
        optional_missing = [
            v for v in missing_env
            if not v.get("is_required") and not v.get("advanced")
        ]
```

后果:**每装一个平台插件,`hermes config migrate` 的"未配置的可选 API key"清单就多几行**,
而 provider profile 注入的几十个 key 一条都不显示。这个不对称大概率是无意的。

### 7.4 注入器的**隐式耦合**(重实现时最容易踩)

`OPTIONAL_ENV_VARS` 这个 dict 对象的**所有者是 `hermes_cli/config_defaults.py`**;
`hermes_cli/config.py:943` 只是绑了个名。两个注入器 `OPTIONAL_ENV_VARS[name] = {...}`
**原地修改**那个对象。于是:

- 任何模块直接 `from hermes_cli.config_defaults import OPTIONAL_ENV_VARS`,
  **只有在 `hermes_cli.config` 已被 import 过之后**,才看得到注入结果。
- `hermes_cli/env_loader.py` 正好是这种消费者,它同时 import 了两处,靠先 import `hermes_cli.config`
  触发注入。`hermes_cli/env_loader.py:63-64 @ 863e313`

```python
    from hermes_cli.config import _EXTRA_ENV_KEYS
    from hermes_cli.config_defaults import OPTIONAL_ENV_VARS
```

(它的 docstring 明说这两个 import 是**懒加载以避开早期 bootstrap 的循环依赖**。
`hermes_cli/env_loader.py:55-62` 的函数 `_known_hermes_env_keys` 是 `.env` 清扫的键集来源。)

这就是 §1.3 提到的代价:同一符号两个来源 + import 期原地变异 = **导入顺序变成语义的一部分**。

### 7.5 平台插件注入器里的一处死 import

`hermes_cli/config.py:5374 @ 863e313`

```python
        import yaml  # type: ignore
```

函数里再没有用过 `yaml`,清单解析用的是 `fast_safe_load`(`hermes_cli/config.py:5392`),
而 `yaml` 在模块顶层第 328 行已经 import 过。这是重构残留的死代码。

**两个注入器都被 `except Exception: pass` 整体包住**(`hermes_cli/config.py:5332-5333` 与
`5429-5430`)。设计意图明写在 docstring 里:一个畸形的 `plugin.yaml` 不能把 CLI 的 import 搞崩。
`hermes_cli/config.py:5364-5368 @ 863e313`

```python
    """Populate OPTIONAL_ENV_VARS from bundled platform plugin manifests.

    Called once at module load time. Idempotent — repeated calls are no-ops.
    Failures are swallowed so a malformed plugin.yaml can't break CLI import.
    """
```

**取舍**:换来的是"一个坏插件让它的 env var 悄悄消失,用户在向导里根本看不见它"——
没有任何日志。调试起来会很痛。

---

## 8. `config_command`:CLI 分发

`hermes_cli/config.py:5131-5136 @ 863e313`

```python
def config_command(args):
    """Handle config subcommands."""
    subcmd = getattr(args, 'config_command', None)
    
    if subcmd is None or subcmd == "show":
        show_config()
```

全部用 `getattr(args, ..., None)` 取参,对 argparse namespace 的形状容错。

`set` 分支的空值判定是 `value is None` 而非 falsy,所以**空串是合法值**。
`hermes_cli/config.py:5153-5157 @ 863e313`

```python
    elif subcmd == "set":
        key = getattr(args, 'key', None)
        value = getattr(args, 'value', None)
        force = bool(getattr(args, 'force', False))
        if not key or value is None:
```

行为规格:`TestFalsyValues::test_config_command_accepts_empty_string`
(`tests/hermes_cli/test_set_config_value.py:139`)。

### 8.1 `migrate` 分支

`hermes_cli/config.py:5193-5196 @ 863e313`

```python
        # Check what's missing
        missing_env = get_missing_env_vars(required_only=False)
        missing_config = get_missing_config_fields()
        current_ver, latest_ver = check_config_version()
```

三件事都齐全才算 up to date。`hermes_cli/config.py:5198-5201 @ 863e313`

```python
        if not missing_env and not missing_config and current_ver >= latest_ver:
            print(color("✓ Configuration is up to date!", Colors.GREEN))
            print()
            return
```

### 8.2 `check` 分支——**"Required" 段恒为空**

`hermes_cli/config.py:5257-5262 @ 863e313`

```python
        print(color("  Required:", Colors.BOLD))
        for var_name in REQUIRED_ENV_VARS:
            if get_env_value(var_name):
                print(f"    ✓ {var_name}")
            else:
                print(color(f"    ✗ {var_name} (missing)", Colors.RED))
```

而 `REQUIRED_ENV_VARS` 是**空 dict**,并且有意为之。`hermes_cli/config.py:960-964 @ 863e313`

```python
# Required environment variables with metadata for migration prompts.
# LLM provider is required but handled in the setup wizard's provider
# selection step (Nous Portal / OpenRouter / Custom endpoint), so this
# dict is intentionally empty — no single env var is universally required.
REQUIRED_ENV_VARS = {}
```

后果:`hermes config check` 永远打印一个**空的 "Required:" 标题**,
`get_missing_env_vars(required_only=True)` 永远返回 `[]`。`hermes_cli/config.py:978-981 @ 863e313`

```python
    # Check required vars
    for var_name, info in REQUIRED_ENV_VARS.items():
        if not get_env_value(var_name):
            missing.append({"name": var_name, **info, "is_required": True})
```

`migrate` 分支里的 `required_missing` 分支(`hermes_cli/config.py:5216-5219`)因此也是**不可达代码**。

`Optional` 段遍历 `OPTIONAL_ENV_VARS`(注入之后共 151 条硬编码 + N 条注入;
硬编码部分我用 exec 数了是 151)。`hermes_cli/config.py:5266-5272 @ 863e313`

```python
        for var_name, info in OPTIONAL_ENV_VARS.items():
            if get_env_value(var_name):
                print(f"    ✓ {var_name}")
            else:
                tools = info.get("tools", [])
                tools_str = f" → {', '.join(tools[:2])}" if tools else ""
                print(color(f"    ○ {var_name}{tools_str}", Colors.DIM))
```

`check` 分支会把 151+ 行全打出来,**没有分页也没有折叠**——可用性上够呛,但不是正确性问题。

---

## 9. 本段的配置键与环境变量全表

### 9.1 config.yaml 键(点分路径)

| 键 | 默认值(DEFAULT_CONFIG) | 读/写点 | 说明 |
|---|---|---|---|
| `model` | `''` | 4316 读 / 4922、4932 写 | 可为 str 也可为 dict;裸写触发重定向 |
| `model.default` | —(model 是 str) | 4944 | 裸 `model` 的重定向目标;运行时解析器唯一读的模型 id |
| `model.provider` | — | 4509 轴映射 | cron 漂移轴 `provider` |
| `model.model` / `model.name` | — | 4509 | 历史别名,归一到 `default` |
| `model.api_base` / 根 `api_base` | — | 4988 | 别名 → `model.base_url` |
| `model.base_url` | — | 4990 | 规范键 |
| `model.api_key` | — | 5020-5023 | 回显打码目标 |
| `agent.max_turns` | `500` | 4317 | 与 `.env` 的 `HERMES_MAX_ITERATIONS` 幽灵比对 |
| `display.personality` | `''` | 4337 | 空 → 打印 `none` |
| `display.show_reasoning` | `True` | 4338 | 内联默认 True |
| `display.bell_on_complete` | `False` | 4339 | |
| `display.user_message_preview.first_lines` | `2` | 4341 | |
| `display.user_message_preview.last_lines` | `2` | 4342 | |
| `display.skin` | `'default'` | 5008 | 写入后 touch `~/.hermes/skins/<v>.yaml` |
| `terminal.backend` | `'local'` | 4349 | |
| `terminal.cwd` | `'.'` | 4350 | **显式排除**出 env 镜像(5000、5114) |
| `terminal.timeout` | `180` | 4351 | ⚠ show_config 内联回退写的是 `60` |
| `terminal.docker_image` | `'nikolaik/python-nodejs:python3.11-nodejs20'` | 4354 | |
| `terminal.singularity_image` | `'docker://nikolaik/python-nodejs:python3.11-nodejs20'` | 4356 | |
| `terminal.modal_image` | 同上(无 docker:// 前缀) | 4358 | |
| `terminal.daytona_image` | 同上 | 4362 | |
| `terminal.vercel_runtime` | `'node24'` | 4366 | |
| `terminal.<子键>`(29 个) | 见 `TERMINAL_CONFIG_ENV_MAP` 3183-3214 | 4999、5113 | 写/删时镜像进对应 `TERMINAL_*` env |
| `timezone` | `''` | 4377 | 空 → `(server-local)` |
| `compression.enabled` | `True` | 4387 | |
| `compression.threshold` | `0.5` | 4390 | 比例阈值 |
| `compression.threshold_tokens` | `None` | 4391 | 绝对上限,与比例取更低 |
| `compression.target_ratio` | `0.2` | 4399 | |
| `compression.protect_last_n` | `20` | 4400 | |
| `compression.protect_first_n` | `3` | 4401 | |
| `auxiliary.compression.model` | `''` | 4403 | 空 → `(auto)` |
| `auxiliary.compression.provider` | `'auto'` | 4405 | |
| `auxiliary.vision.{provider,model}` | `'auto'` / `''` | 4412、4423-4424 | |
| `auxiliary.web_extract.{provider,model}` | `'auto'` / `''` | 4413 | |
| `cron.model_drift_guard` | `True` | 4536 | **只有字面 `false` 能关** |
| `cron.model` | `''` | 4559-4560 | 车队默认,覆盖 model 轴 |
| `cron.model_provider` | `''` | 4559-4560 | 覆盖 provider 轴;注意不是 `cron.provider` |
| `skills.config.<key>` | 由 SKILL.md 声明 | 4446、4451 | **明文打印,无脱敏** |
| `_*`(任意下划线开头顶层) | — | 4761 | 内部/测试标记,跳过 schema 校验 |
| `platforms.<name>.<field>` | — | 4695、4770、4800 | 平台容器,下面全放行 |
| 12 个开放字典顶层键 | — | 4654-4667 | providers / mcp_servers / hooks / … |
| 18 个半 schema 字典顶层键 | — | 4673-4680 | discord / telegram / … / sessions / checkpoints |
| `custom_providers` | — | 4684-4686 | list 形状,按下标索引 |

### 9.2 环境变量

| 变量 | 读取点 | 读它的函数 | fallback / 说明 |
|---|---|---|---|
| `EDITOR` | 4479 | `edit_config` | → `VISUAL` → 平台候选表(4488-4491) |
| `VISUAL` | 4479 | `edit_config` | 次于 `EDITOR`(与 POSIX 惯例相反) |
| `OPENROUTER_API_KEY` | 4295 | `show_config`→`get_env_value` | `os.environ`(经 secret_scope)→ `.env` |
| `VOICE_TOOLS_OPENAI_KEY` | 4296 | 同上 | |
| `EXA_API_KEY` | 4297 | 同上 | |
| `PARALLEL_API_KEY` | 4298 | 同上 | |
| `FIRECRAWL_API_KEY` | 4299 | 同上 | |
| `TAVILY_API_KEY` | 4300 | 同上 | |
| `BROWSERBASE_API_KEY` | 4301 | 同上 | |
| `BROWSER_USE_API_KEY` | 4302 | 同上 | |
| `FAL_KEY` | 4303 | 同上 | |
| `ANTHROPIC_API_KEY` | 4310 | `auth.get_anthropic_key` | → `ANTHROPIC_TOKEN` → `CLAUDE_CODE_OAUTH_TOKEN`;**偏好 `.env` 胜过 shell** |
| `ANTHROPIC_TOKEN` | 4310 | 同上 | 第二档 |
| `CLAUDE_CODE_OAUTH_TOKEN` | 4310 | 同上 | 第三档 |
| `HERMES_MAX_ITERATIONS` | 4323 | `show_config`→`load_env()` | **遗留幽灵**;直接读 `.env` 文件绕过 os.environ |
| `MODAL_TOKEN_ID` | 4359 | `show_config` | 仅显示"是否配置" |
| `DAYTONA_API_KEY` | 4363 | `show_config` | |
| `VERCEL_OIDC_TOKEN` | 4367 | `show_config` | 或三元组 |
| `VERCEL_TOKEN` | 4367 | `show_config` | 需与后两者同时存在 |
| `VERCEL_PROJECT_ID` | 4367 | `show_config` | |
| `VERCEL_TEAM_ID` | 4367 | `show_config` | |
| `TERMINAL_SSH_HOST` | 4369 | `show_config` | 也在 `_is_env_config_key` 前缀白名单(1171) |
| `TERMINAL_SSH_USER` | 4370 | `show_config` | 同上 |
| `TELEGRAM_BOT_TOKEN` | 4435 | `show_config` | |
| `DISCORD_BOT_TOKEN` | 4436 | `show_config` | |
| `TERMINAL_ENV` 等 29 个 `TERMINAL_*` | 4999、5113 | `terminal_config_env_var_for_key` | 由 `terminal.*` 配置键镜像写入/删除 |
| `HERMES_MANAGED_DIR` | 间接(4264、4848、5072) | `managed_scope.get_managed_dir` | → `/etc/hermes`;pytest 下屏蔽第二档 |
| `OPTIONAL_ENV_VARS` 全体(151+ 注入) | 5266 | `config_command` check 分支 | |

---

## 10. 配套测试(行为规格)

已实跑:`HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh
tests/hermes_cli/test_set_config_value.py` → **82 passed, 0 failed, 1.4s**。

- `tests/hermes_cli/test_set_config_value.py`(725 行,本段的**主行为规格**):
  `TestExplicitAllowlist` / `TestCatchAllPatterns`(env 分流)、`TestConfigYamlRouting`、
  `TestFalsyValues`(空串合法)、`TestConfigGetUnset`、`TestListNavigation`(#17876)、
  `TestCronModelDriftConfigWarning`(含 `test_only_literal_false_disables_guard`)、
  `TestStringTypedConfigValues`(强制转型三态)、`TestSecretRedactionInDisplay`、
  `TestSchemaValidation` / `TestValidateConfigKey`(#34067)、`TestDisplaySkinTouch`、
  `TestMappingGuard`(#74995,6 例)、`TestScalarModelSubKeyPreservation`、
  `TestMalformedYAMLConfigPreservation`。
- `tests/hermes_cli/test_managed_scope_writeguard.py`:`test_config_set_managed_key_rejected`
  (§5.1 闸门 B)、`test_save_env_value_managed_key_rejected`。
- `tests/hermes_cli/test_managed_scope_surfacing.py`:`show_config` 的托管横幅
  (`test_config_show_no_managed_scope_silent` 反向断言"无托管时不许出现")。
- `tests/cli/test_cli_save_config_value.py:55`:对
  `hermes_cli.config.warn_unpinned_cron_jobs_after_model_config_change` 打桩,
  说明 CLI 另一条保存路径也接了这个告警。
- `tests/tools/test_terminal_config_env_sync.py`:`terminal.*` ↔ `TERMINAL_*` 镜像。
- `tests/hermes_cli/test_config.py`、`tests/hermes_cli/test_subcommands_batch.py`、
  `tests/hermes_cli/test_placeholder_usage.py`:`config_command` 分发面。

**未找到配套测试的函数**(grep `tests/` 零命中):`_inject_profile_env_vars`、
`_inject_platform_plugin_env_vars`、`get_config_value`(仅被 `TestConfigGetUnset` 间接覆盖)、
`_default_value_for_key`、`_suggest_closest_key`、`edit_config`。
两个 import 期注入器完全没有直接测试,这与它们"静默吞掉一切异常"叠加,是本段最大的观测盲区。

---

## 11. 重实现要点(从零重写这一簇必须知道的)

1. **展示、读取、写入必须用不同的配置视图。** 展示与 `get` 用**合并后**的配置
   (defaults ⊕ user ⊕ managed);写入必须用**原始用户文件**,否则一次 `config set`
   会把几百个默认键和管理员钉死的值全部落盘进用户的 config.yaml。本段 `set`/`unset`
   都是 `fast_safe_load(open(config_path))` 直读原文件(4884、5099),这不是优化,是正确性。

2. **"读不出来" ≠ "不存在",写之前必须区分。** 一个权限错误或坏挂载会让 raw 读退化成 `{}`,
   接着的整文件覆盖就把用户配置抹平了。`require_readable_config_before_write` 的两级检查
   (stat + 实读 1 字节)是最小可行方案(3065-3086)。**并且要把它做成唯一闸口**——
   本仓库自己都没做到(§5.4 出入 ②)。

3. **CLI 传进来永远是字符串,类型强制要有"类型来源"。** 用 schema 默认值的类型反查
   (`_default_value_for_key`)比正则猜类型可靠得多;但要清楚:**schema 里没有的键会退回猜测**,
   于是纯数字的 API key / 端口号 / 命令参数会变成 int。要么给开放字典也标类型,
   要么提供 `--string` 之类的显式开关。

4. **未知键要提示不要拦截,但提示必须在写盘之后。** 顶层任意键是被支持的用法
   (会桥进 `os.environ` 给 skill/外部工具),硬拦会破坏它;但静默成功会让用户
   debug 一个永远不生效的配置。写完再给"你是不是想写 X"(difflib,cutoff 0.6,宁缺毋滥)
   是本段给出的答案。

5. **单段键覆盖映射段是最经典的数据毁灭路径,必须显式设计。** `config set model <id>`
   在 `model:` 已是映射时会吃掉 provider/base_url/context_length。本段的处理值得抄:
   **有文档的简写重定向(model→model.default),其余一律拒绝并列出子键,`--force` 才放行**。
   同理 `_set_nested` 必须能穿过 list 而不是把 list 换成 dict。

6. **配置写入是跨子系统事件,要有"副作用出口"。** 本段有三条:
   (a) `terminal.*` 镜像进 `.env`(因为工具在子进程里只读 env);
   (b) `display.skin` touch 文件 mtime(因为 watcher 的签名是 (name, mtime));
   (c) 全局 model/provider 变更时预警 cron 的 fail-closed 漂移守卫。
   设计自己的 harness 时要预留这个 hook 点,并且**让每条副作用都 fail-open**,绝不阻塞主写入。
   同时**保证 set 与 unset 对称**——本段的 unset 就漏了 (c)。

7. **凭据要"结构脱敏"而不只是"正则脱敏"。** 不透明 token(`cfut_...`)匹配不上任何厂商正则,
   只能靠 key 名。精确匹配 + 递归 + 深度上限是可用的最小实现;但要注意
   **非字符串值和第三方声明的配置项(skill config)会漏网**(§2.3(g))。
   并且要想清楚 `get` 要不要脱敏——本段选择不脱敏(脚本可用性优先),那就得在文档里说清楚。

8. **import 期副作用注入 = 导入顺序变成语义。** 两个注入器原地修改
   `config_defaults.OPTIONAL_ENV_VARS`,任何绕过 `hermes_cli.config` 直接 import
   `config_defaults` 的消费者会看到未注入的字典。如果要复刻这种"插件自描述 env var"的能力,
   更稳的做法是**做成显式的 `get_optional_env_vars()` 函数(惰性 + 缓存)**,
   而不是模块级可变字典 + import 副作用。另外注入器之间的元数据字段
   (如 `advanced`)必须对齐,否则下游过滤器行为分裂(§7.3)。
