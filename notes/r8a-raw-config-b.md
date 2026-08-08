# r8a-raw-config-b · config.py:1400-2800

底稿。研究对象 `NousResearch/hermes-agent` @ `863e313`,目标文件
`hermes_cli/config.py`(全文 5434 行),本篇负责 **1400-2800 行**。
所有断言后紧跟 `路径:行号 @ 863e313` 与原文块。为讲清上下文,少量引用落在
本段之外(`992-1150` 点分路径三件套、`2861+` 的 `is_provider_enabled`、
`3283-3620` 的 `_load_config_impl` / `save_config`),都会标注"段外·上下文"。

---

## 0. 这一段在文件里的位置

模块 docstring 把 `config.py` 定位成"`~/.hermes/` 下两个文件(config.yaml + .env)
的管理器 + `hermes config` 子命令的实现"。`hermes_cli/config.py:1-15 @ 863e313`

```python
"""
Configuration management for Hermes Agent.
```

1400-2800 这一段**不含**任何 `hermes config` 子命令入口(那些在 4248-5300),
它是三类东西的集合体:

| 区段 | 顶层函数 | 干什么 |
|---|---|---|
| 1400-1780 | `_normalize_custom_provider_entry` 尾段 / `_custom_provider_entry_to_provider_config` / `providers_dict_to_custom_providers` / `get_compatible_custom_providers` / `_coerce_ssl_verify` / `get_custom_provider_tls_settings` / `apply_custom_provider_tls_to_client_kwargs` / `normalize_extra_headers` / `get_custom_provider_extra_headers` / `apply_custom_provider_extra_headers_to_client_kwargs` / `get_custom_provider_context_length` | **自定义 provider 的 schema 归一化 + 按 base_url 的运行时旁路查询** |
| 1783-2121 | `_coerce_config_version` / `_raw_config_has_explicit_version` / `check_config_version` / `ConfigIssue` / `validate_config_structure` / `print_config_warnings` / `warn_deprecated_cwd_env_vars` | **版本判定与结构体检(只报警不改文件)** |
| 2124-2800 | `_persist_migration` / `migrate_config` / `_merge_partial_save` / `_deep_merge` / `_strip_dotted_keys` / `_env_expand_match` / `_env_ref_var_name` / `_expand_env_vars` / `_env_ref_snapshot` / `_items_by_unique_name` / `_preserve_env_ref_templates` / `_explicit_config_paths` / `_strip_default_values` / `_normalize_root_model_keys` / `_normalize_max_turns_config` | **迁移驱动 + 读写路径的纯函数工具箱**(`load_config`/`save_config` 的全部脏活) |

一句话:**这一段是 config 读写管线的"中间层"**——上面是命令入口,下面是
`load_config`/`save_config` 两个薄壳,真正决定"用户文件里的字节怎么变成运行时
dict、运行时 dict 怎么变回字节"的规则全在这 1400 行里。

---

## 1. 机制:自定义 provider 条目归一化(1400-1474,尾段)

### 解决什么问题

hermes 支持两套 provider 配置 schema:老的 `custom_providers:`(YAML 列表)和
v12 起的 `providers:`(YAML 字典,key 即 provider id)。运行时(agent、/model
选择器、fallback 链)只想看**一种**形状。归一化器把任意一条(两种 schema、
camelCase 手写、旧字段名)压成统一的 `{name, base_url, provider_key, ...}`。

函数从 1284 开始,本段接手的是 **字段抽取**部分。别名互认在 1402、1406:

`hermes_cli/config.py:1402 @ 863e313`

```python
    api_mode = entry.get("api_mode") or entry.get("transport")
```

`hermes_cli/config.py:1406 @ 863e313`

```python
    model_name = entry.get("model") or entry.get("default_model")
```

即:**legacy `api_mode` ≡ v12 `transport`;legacy `model` ≡ v12 `default_model`**,
归一化后统一叫 `api_mode` / `model`。(`api_mode` = 该 endpoint 说哪种 HTTP 协议方言:
`chat_completions` / `anthropic_messages` / `codex_responses`。)

### `models` 的三种写法都收

`models` 既可以是 dict(`{模型id: {元数据}}`),也可能被手写成列表:

`hermes_cli/config.py:1410 @ 863e313`

```python
    models = entry.get("models")
    if isinstance(models, dict) and models:
        # Shallow-copy: `entry` may alias a cached config sub-dict, and the
        # normalized entry escapes into long-lived runtime state
        # (agent._custom_providers) — don't share the cached models mapping.
        normalized["models"] = dict(models)
```

`hermes_cli/config.py:1416 @ 863e313`

```python
    elif isinstance(models, list) and models:
```

列表分支同时接受 `["id1","id2"]` 和 `[{id: ..., ...}]` / `[{name: ...}]` 两种行,
转成 dict 形状。注释直说不转就会"/model 显示该 provider 有 (0) 个模型"。
**为什么这么设计**:归一化后的 dict 会存进 `agent._custom_providers` 长期存活,
而入参 `entry` 可能是 `load_config_readonly()` 共享缓存里的子 dict——所以
`dict(models)` 的浅拷贝是缓存不可变契约的一部分,不是随手写的。

### 数值/布尔字段的类型闸门

`hermes_cli/config.py:1441 @ 863e313`

```python
    context_length = entry.get("context_length")
    if isinstance(context_length, int) and context_length > 0:
        normalized["context_length"] = context_length
```

`hermes_cli/config.py:1445 @ 863e313`

```python
    rate_limit_delay = entry.get("rate_limit_delay")
    if isinstance(rate_limit_delay, (int, float)) and rate_limit_delay >= 0:
        normalized["rate_limit_delay"] = rate_limit_delay
```

**这就是本段的"类型强制"全部形态:不转换、只筛选**。类型不对就静默丢弃该字段
(不报错、不警告),让下游拿默认值。代价见 §12 缺陷 D-6(Python `bool` 是 `int`
子类,`context_length: yes` 会被当成 `True` 收下——已实测)。

### header 与 TLS

`hermes_cli/config.py:1460 @ 863e313`

```python
    normalized_headers = normalize_extra_headers(entry.get("extra_headers"))
```

`hermes_cli/config.py:1468 @ 863e313`

```python
    ssl_verify = entry.get("ssl_verify")
    if isinstance(ssl_verify, bool):
        normalized["ssl_verify"] = ssl_verify
    elif isinstance(ssl_verify, str) and ssl_verify.strip():
        normalized["ssl_verify"] = ssl_verify.strip()
```

注意:归一化**保留字符串形态的 `ssl_verify`**,但下游读取者
`get_custom_provider_tls_settings` 只认布尔词(§3),差异见缺陷 D-4。

---

## 2. 机制:两套 schema 互转与"统一视图"(1477-1579)

### 2.1 反向转换:legacy → v12

`hermes_cli/config.py:1477 @ 863e313`

```python
def _custom_provider_entry_to_provider_config(
```

`hermes_cli/config.py:1490 @ 863e313`

```python
    provider_entry: Dict[str, Any] = {"api": normalized["base_url"]}
```

v12 形状用 `api` 作为 URL 键(不是 `base_url`)。字段名回改在 1508:

`hermes_cli/config.py:1508 @ 863e313`

```python
    if "model" in normalized:
        provider_entry["default_model"] = normalized["model"]
    if "api_mode" in normalized:
        provider_entry["transport"] = normalized["api_mode"]
```

**取舍**:这条路径先归一化再反归一化(先 legacy→canonical 再 canonical→v12),
多一次 dict 构造,但保证"迁移写出去的 v12 条目"和"运行时读进来的条目"经过同一
套别名规则,避免两处各写一遍别名表而漂移。

### 2.2 正向:`providers:` dict → legacy list

`hermes_cli/config.py:1516 @ 863e313`

```python
def providers_dict_to_custom_providers(providers_dict: Any) -> List[Dict[str, Any]]:
```

`hermes_cli/config.py:1522 @ 863e313`

```python
    for key, entry in providers_dict.items():
        if isinstance(entry, dict) and not is_provider_enabled(entry):
            continue
```

**`enabled: false` 的过滤点在这里**,而 `is_provider_enabled` 定义在 2861(段外·
上下文),默认 True、字符串 `"false"/"0"/"no"/"off"` 也认:

`hermes_cli/config.py:2877 @ 863e313`(段外·上下文)

```python
    flag = provider_cfg.get("enabled", True)
```

### 2.3 去重合并视图 `get_compatible_custom_providers`

这是**全仓拿"自定义 provider 列表"的唯一正门**。两层去重键:

`hermes_cli/config.py:1549 @ 863e313`

```python
    def _append_if_new(entry: Optional[Dict[str, Any]]) -> None:
```

去重键 1 = `provider_key`(小写),去重键 2 = `(name, base_url去尾斜杠, model)` 三元组。
顺序上 **legacy `custom_providers` 先入、`providers` 后入**,所以同一个 provider 两
边都写时,legacy 那条赢:

`hermes_cli/config.py:1569 @ 863e313`

```python
    custom_providers = config.get("custom_providers")
    if custom_providers is not None:
        if not isinstance(custom_providers, list):
            return []
```

**这四行同时是缺陷 D-1**:`custom_providers` 写成 dict(YAML 缩进写错的最常见形态)
时直接 `return []`,连**合法的 `providers:` 块也一起消失**。已实测:
`get_compatible_custom_providers({'custom_providers':{...},'providers':{'p':{'api':...}}})` → `[]`。

**为什么这么设计**:docstring 明说不把兼容视图物化回 config.yaml(会让 UI 里出现
重复条目)——所以兼容层只活在内存里,每次调用重算。**取舍**:每个调用点都要付一次
归一化 + 去重的成本,换取磁盘 schema 干净。

---

## 3. 机制:按 base_url 的 per-provider 运行时旁路(1582-1780)

### 解决什么问题

OpenAI SDK 客户端是在 `agent_init` / `run_agent` 里造的,那里只知道**当前要打哪个
base_url**,不知道它对应 config 里哪条 provider。这一组函数就是"**用 URL 反查配置**"
的四个查询器:TLS、extra_headers、context_length,外加两个把结果拍进
`client_kwargs` 的 apply 函数。

匹配统一用 `normalize_route_base_url`(route identity,忽略尾斜杠等差异):

`hermes_cli/config.py:1610 @ 863e313`

```python
    target_url = normalize_route_base_url(base_url)
```

### 3.1 TLS

`hermes_cli/config.py:1582 @ 863e313`

```python
def _coerce_ssl_verify(value: Any) -> Optional[bool]:
```

只把 `false/0/no/off` 与 `true/1/yes/on` 折成布尔,**其它字符串一律 `None`(=丢弃)**。

`hermes_cli/config.py:1617 @ 863e313`

```python
        out: Dict[str, Any] = {}
        ca = entry.get("ssl_ca_cert")
        if isinstance(ca, str) and ca.strip():
            out["ssl_ca_cert"] = ca.strip()
        verify = _coerce_ssl_verify(entry.get("ssl_verify"))
        if verify is not None:
            out["ssl_verify"] = verify
        return out
```

注意最后那句 **`return out` 在循环体内、无条件返回**——第一个 URL 命中的条目就定案,
哪怕它一个 TLS 字段都没有。对照 §3.2 的 headers 版本,这是缺陷 D-2。

`hermes_cli/config.py:1713 @ 863e313`(apply 侧,headers 合并策略)

```python
    merged = dict(client_kwargs.get("default_headers") or {})
```

per-provider header **覆盖** SDK/provider 默认 header(最具体者胜)。

### 3.2 extra_headers:同一个 bug 修过一次

`hermes_cli/config.py:1642 @ 863e313`

```python
def normalize_extra_headers(extra_headers: Any) -> Dict[str, str]:
```

`hermes_cli/config.py:1654 @ 863e313`

```python
    if not isinstance(extra_headers, dict) or not extra_headers:
        return {}
    return {str(k): str(v) for k, v in extra_headers.items() if v is not None}
```

键值都 `str()` 化、`None` 值丢弃。docstring 反复强调这些值常带凭据(Cloudflare
Access token、代理认证),**任何下游不得日志打印**。

查询侧和 TLS 的差别就在这里:

`hermes_cli/config.py:1683 @ 863e313`

```python
    for entry in custom_providers:
```

`hermes_cli/config.py:1689 @ 863e313`

```python
        headers = normalize_extra_headers(entry.get("extra_headers"))
        if headers:
            return headers
    return {}
```

**命中 URL 但没 headers 就继续找下一条**——这正是 #74465 的修法,并有测试钉住:
`tests/hermes_cli/test_custom_provider_extra_headers.py:120 @ 863e313`

```python
def test_get_custom_provider_extra_headers_skips_alias_without_headers():
```

TLS 那边没有对应测试,也没有对应修法(D-2)。

### 3.3 per-model context_length 覆写

`hermes_cli/config.py:1759 @ 863e313`

```python
    for entry in custom_providers:
```

`hermes_cli/config.py:1771 @ 863e313`

```python
        raw_ctx = model_cfg.get("context_length")
        if raw_ctx is None:
            continue
        try:
            ctx = int(raw_ctx)
        except (TypeError, ValueError):
            continue
        if ctx > 0:
            return ctx
```

**这里是本段唯一做真正类型转换(`int(raw_ctx)`)而非纯筛选的地方**,所以
`context_length: "200000"`(字符串)在 per-model 层能用、在 provider 层(1442)
不能用。同一个键名两套类型规则,见缺陷 D-7。

docstring 列出了五个调用点,并交代历史:以前只有 `run_agent.py` 启动路径有这段
查找,`/model` 中途切模型的路径没有,于是切完模型 context 掉回 128K 默认(#15779)。
**这是"把重复逻辑收敛成单一真相源"的典型动机记录**。

---

## 4. 机制:配置版本判定(1783-1842)

### 4.1 三个函数各管一件事

`hermes_cli/config.py:1783 @ 863e313`

```python
def _coerce_config_version(value: Any) -> int:
```

`hermes_cli/config.py:1785 @ 863e313`

```python
    if isinstance(value, bool):
        return 0
```

**显式挡掉 bool**(`_config_version: true` 不能变成版本 1)。同一个 bool/int 陷阱在
1442 的 `context_length` 那里没挡——同文件内两种态度,见 D-6。

`hermes_cli/config.py:1794 @ 863e313`

```python
def _raw_config_has_explicit_version() -> bool:
```

区分"**显式写了旧版本号的老配置**"和"**根本没有版本号的新手/克隆配置**"。前者被
v12 支持下限拒绝,后者走正常迁移梯。

`hermes_cli/config.py:1825 @ 863e313`

```python
    latest = _coerce_config_version(DEFAULT_CONFIG.get("_config_version", 1)) or 1
```

`_config_version` 的当前值 = 33:`hermes_cli/config_defaults.py:3126 @ 863e313`

```python
    "_config_version": 33,
```

### 4.2 为什么不能用 `load_config()` 判版本

`hermes_cli/config.py:1827 @ 863e313`

```python
    if not config_path.exists():
        return latest, latest
```

`hermes_cli/config.py:1841 @ 863e313`

```python
    current = _coerce_config_version(config.get("_config_version"))
```

docstring 说得很清楚:`load_config()` 从 `DEFAULT_CONFIG` 起步深合并,于是**任何
文件读出来都"自带" `_config_version: 33`**,拿它判版本永远等于最新版、迁移永不触发。
所以 `check_config_version` 必须自己开文件读 raw。

**文件不存在 → 返回 `(latest, latest)`**:全新安装不跑迁移。
**YAML 坏掉 → 也返回 `(latest, latest)`** 并只发一次解析告警,绝不因为解析失败就
把用户文件重写成默认值(fail-safe 姿态)。

---

## 5. 机制:结构体检 `validate_config_structure`(1845-2074)

### 解决什么问题

YAML 缩进写错不会报错,只会让运行时抛出莫名其妙的 "Unknown provider"。这个函数把
一批**已知的常见写错**翻译成人话 + 修改建议(`ConfigIssue(severity, message, hint)`)。

`hermes_cli/config.py:1897 @ 863e313`

```python
@dataclass
class ConfigIssue:
```

### 5.1 根键白名单是**派生**的

`hermes_cli/config.py:1854 @ 863e313`

```python
_EXTRA_KNOWN_ROOT_KEYS = {
```

`hermes_cli/config.py:1881 @ 863e313`

```python
_KNOWN_ROOT_KEYS = frozenset(DEFAULT_CONFIG.keys()) | _EXTRA_KNOWN_ROOT_KEYS
```

**设计要点**:白名单 = `DEFAULT_CONFIG` 的键 ∪ 一张"故意不在默认里的合法根键"手工表
(legacy `custom_providers`、`mcp_servers`、`image_gen`、gateway 的一堆顶层便捷形式……)。
新增默认键自动被接受,不用改两处。测试钉死了这个派生关系:
`tests/hermes_cli/test_config_validation.py:104 @ 863e313`

```python
    def test_known_root_keys_derived_from_default_config(self):
```

### 5.2 有意的"开放世界"

`hermes_cli/config.py:2042 @ 863e313`

```python
    for key in config:
        if key.startswith("_"):
            continue
```

`hermes_cli/config.py:2045 @ 863e313`

```python
        if key not in _KNOWN_ROOT_KEYS and key in _CUSTOM_PROVIDER_LIKE_FIELDS:
```

**未知根键一律不警告**,只对"长得像 provider 字段"的四个键(`base_url`/`api_key`/
`rate_limit_delay`/`api_mode`)提示位置放错了。理由写在 2036-2041 的注释里:顶层
标量会被桥接进 `os.environ` 给 skills 和外部 app 用,封闭白名单不可能穷举。

`hermes_cli/config.py:1894 @ 863e313`

```python
_CUSTOM_PROVIDER_LIKE_FIELDS = {"base_url", "api_key", "rate_limit_delay", "api_mode"}
```

但**其中 `base_url` 这一路在生产调用点上是死代码**(D-3):所有真实调用点都
`validate_config_structure()` 不传参 → 走 `load_config()`:

`hermes_cli/config.py:1914 @ 863e313`

```python
    if config is None:
        try:
            config = load_config()
```

而 `load_config()` 里 `_normalize_root_model_keys` 已经把根 `base_url` 搬进
`model.base_url` 并 `pop` 掉了(§9.1)。实测:传 raw dict 有警告,传归一化后的
dict 没警告;而唯一覆盖它的测试恰恰是直接传 dict 的:
`tests/hermes_cli/test_config_validation.py:110 @ 863e313`

```python
    def test_provider_like_unknown_root_keeps_misplaced_message(self):
```

### 5.3 启动告警与弃用告警

`hermes_cli/config.py:2055 @ 863e313`

```python
def print_config_warnings(config: Optional[Dict[str, Any]] = None) -> None:
```

`hermes_cli/config.py:2069 @ 863e313`

```python
    lines = ["\033[33m⚠ Config issues detected in config.yaml:\033[0m"]
```

写 stderr,末尾指向 `hermes doctor`。整个函数被 `try/except: return` 包住——
**体检本身绝不能挡住启动**。

`hermes_cli/config.py:2077 @ 863e313`

```python
def warn_deprecated_cwd_env_vars(config: Optional[Dict[str, Any]] = None) -> None:
```

`hermes_cli/config.py:2083 @ 863e313`

```python
    messaging_cwd = os.environ.get("MESSAGING_CWD")
    terminal_cwd_env = os.environ.get("TERMINAL_CWD")
```

`hermes_cli/config.py:2095 @ 863e313`

```python
    config_has_explicit_cwd = config_cwd not in {".", "auto", "cwd", ""}
```

**这里有个精妙的自洽点**:`TERMINAL_CWD` 既可能来自用户 `.env`(弃用),也可能是
hermes 自己从 `terminal.cwd` 桥接出去的。桥接器跳过的哨兵值集合与这里的判据一致:
`hermes_cli/config.py:3274 @ 863e313`(段外·上下文)

```python
            if raw_cwd in {".", "auto", "cwd"}:
```

所以只有"配置里没写显式路径、但环境里有 TERMINAL_CWD"才警告。**残留误报**:用户
在 shell 里 `export TERMINAL_CWD=...`(不是 .env)也会被说成 "found in .env"。

---

## 6. 机制:迁移驱动 `migrate_config`(2124-2413)

### 6.1 写不变式:`_persist_migration`

`hermes_cli/config.py:2124 @ 863e313`

```python
def _persist_migration(config: Dict[str, Any]) -> None:
```

`hermes_cli/config.py:2147 @ 863e313`

```python
    save_config(config)
```

函数体只有一行,**价值全在 docstring 立的不变式**:

> a migration may only persist values that DIFFER from the current schema
> default, plus explicit removals/renames of user data.

历史事故写在注释里:每次版本 bump 都把 `DEFAULT_CONFIG` 物化到磁盘,导致
"hermes update 之后我的 config 被写成一坨默认值"。为什么不能物化默认值?因为
`load_config()` 读时深合并已经供给了默认值,写下去只会**遮蔽未来的默认值变更**。

**设计手法值得抄**:把不变式钉在一个一行的包装函数上,让"每个迁移步骤都必须走这
个门",而不是靠 13 个迁移函数各自记得。

### 6.2 主流程七段

`hermes_cli/config.py:2150 @ 863e313`

```python
def migrate_config(interactive: bool = True, quiet: bool = False) -> Dict[str, Any]:
```

1. **无条件**先规整 `.env` 行格式:`hermes_cli/config.py:2165 @ 863e313`

```python
        fixes = sanitize_env_file()
```

2. 取版本:`hermes_cli/config.py:2172 @ 863e313`

```python
    current_ver, latest_ver = check_config_version()
```

3. **支持下限闸门**:`hermes_cli/config.py:2196 @ 863e313`

```python
    _explicit_version = _raw_config_has_explicit_version()
    floor_refused = (
        _explicit_version
        and current_ver < SUPPORT_FLOOR_VERSION
        and current_ver < latest_ver
    )
```

`hermes_cli/config.py:2202 @ 863e313`

```python
    if floor_refused:
```

下限 = 12:`hermes_cli/config_migrations.py:53 @ 863e313`

```python
SUPPORT_FLOOR_VERSION = 12
```

**为什么闸门放在这个包装里而不是驱动里**:注释明说"让 registry driver 保持纯机制,
测试可以直接驱动它"。

4. 否则跑表驱动迁移梯:`hermes_cli/config.py:2218 @ 863e313`

```python
        run_migrations(current_ver, results, quiet)
```

驱动的语义(段外·上下文):`hermes_cli/config_migrations.py:683 @ 863e313`

```python
    for target_ver, migration_fn in MIGRATIONS:
        if current_ver < target_ver:
            migration_fn(results, quiet)
```

**`current_ver` 全程不推进**——每一步都拿同一个初始版本比较,精确复刻原来那串
`if current_ver < N:` 顺序 if 块的语义(包括"跳号"版本 18/19/20/22 等根本不存在的
情况)。这是"重构不许改行为"的教科书写法:注册表 = 顺序 if 块的机械等价物。

5. **迁移后安全清扫**:`hermes_cli/config.py:2224 @ 863e313`

```python
    config = read_raw_config()
```

`hermes_cli/config.py:2239 @ 863e313`

```python
                entry["enabled"] = False
```

对每个 `mcp_servers.<name>` 跑 `validate_mcp_server_entry`,像外泄的 stdio 条目**保留
但禁用**(保住可审计性,#45620)。

`hermes_cli/config.py:2248 @ 863e313`

```python
            if mcp_touched:
                config["mcp_servers"] = raw_mcp_servers
                _persist_migration(config)
```

6. **toolset 名校验**:`hermes_cli/config.py:2261 @ 863e313`

```python
        ts_warnings = validate_platform_toolsets(
```

动机注释很值得记:`resolve_toolset()` 对未知名字返回 `[]`,于是配置里一个错别字会
**静默地让 agent 少一批工具**,没有任何报错(#38798)。

7. **版本戳与"新键不物化"**:`hermes_cli/config.py:2361 @ 863e313`

```python
    missing_config = get_missing_config_fields()
```

`hermes_cli/config.py:2365 @ 863e313`

```python
    if current_ver < latest_ver and not floor_refused:
        config = read_raw_config()
        config["_config_version"] = latest_ver
        _persist_migration(config)
```

**只写版本号,不写新增默认键**;缺失键列表只用于 `hermes update` 的
"N new config option(s) available" 提示。

### 6.3 交互式补全:三条独立的问答流

- 必填 env:`hermes_cli/config.py:2276 @ 863e313`

```python
    missing_env = get_missing_env_vars(required_only=True)
```

  (`REQUIRED_ENV_VARS = {}` 是空的,所以这条流实际上是死的——provider key 由 setup
  向导负责。)
- **只问"自上次版本以来新增"的可选 env**:`hermes_cli/config.py:2313 @ 863e313`

```python
    for ver in range(current_ver + 1, latest_ver + 1):
        new_var_names.update(ENV_VARS_BY_VERSION.get(ver, []))
```

  这是个好设计:版本区间 → 新键集合,老用户升级不会被从头问一遍所有 key。
- skill 声明的 config 变量:`hermes_cli/config.py:2374 @ 863e313`

```python
    missing_skill_config = get_missing_skill_config_vars()
```

  写入前缀由 `agent.skill_utils.SKILL_CONFIG_PREFIX` 决定,取不到时兜底常量
  `"skills.config"`:`hermes_cli/config.py:2400 @ 863e313`

```python
                    storage_key = f"{SKILL_CONFIG_PREFIX}.{var['key']}"
```

  写入用 `_set_nested`(段外·上下文,§10.2),然后 `_persist_migration`。

---

## 7. 机制:写路径的合并/剥离四件套(2416-2483, 2673-2743)

这四个纯函数是 `save_config` 的全部"不丢用户数据"保障。

### 7.1 `_merge_partial_save`:局部保存不丢兄弟段

`hermes_cli/config.py:2416 @ 863e313`

```python
def _merge_partial_save(raw: dict, override: dict) -> dict:
```

`hermes_cli/config.py:2426 @ 863e313`

```python
    result = copy.deepcopy(override)
    for key, value in raw.items():
        if key not in result:
            result[key] = copy.deepcopy(value)
        elif isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(value, result[key])
```

只在 `save_config(..., merge_existing=True)` 时启用。**明确不支持"删除"**——想删键
必须走 `_persist_migration` + 完整 `read_raw_config()`。

### 7.2 `_deep_merge`:读路径的地基

`hermes_cli/config.py:2435 @ 863e313`

```python
def _deep_merge(base: dict, override: dict) -> dict:
```

`hermes_cli/config.py:2448 @ 863e313`

```python
    result = base.copy()
```

`hermes_cli/config.py:2456 @ 863e313`

```python
        elif key in result and isinstance(result[key], dict) and value is None:
            continue
```

**这一句 `continue` 是 #58277 的修复**:`config.yaml` 里写了 `terminal:` 却没写内容,
YAML 解析成 `None`;当成 override 会把整个默认 dict 换成 `None`,下游所有
`cfg["terminal"]["backend"]` 全崩。现在 `None` 覆盖 dict 默认 = 视作没写。

注意 `result = base.copy()` 是**浅拷贝**:返回值与 `base` 共享未被覆盖的子 dict。
实测 `m = _deep_merge({'a':{'b':1}}, {'c':2}); m['a']['b']=99` 会改到入参。
读路径安全(base 是 `copy.deepcopy(DEFAULT_CONFIG)`),但这是个隐式契约(D-8)。

### 7.3 `_strip_dotted_keys`:managed 层的机械保险

`hermes_cli/config.py:2463 @ 863e313`

```python
def _strip_dotted_keys(cfg: dict, dotted_keys: set) -> Tuple[dict, set]:
```

给 `save_config` 用:管理员在 `/etc/hermes/config.yaml` 钉住的叶子键,在批量写时
被摘掉并打印告知,免得写下去、下次加载又输给 managed 层(用户看到"设置没生效")。
键集合来自 `hermes_cli/managed_scope.py:202 @ 863e313`(段外·上下文)

```python
def managed_config_keys() -> set:
```

### 7.4 `_explicit_config_paths` + `_strip_default_values`:默认值不落盘

`hermes_cli/config.py:2673 @ 863e313`

```python
def _explicit_config_paths(config: Dict[str, Any]) -> Set[Tuple[str, ...]]:
```

`hermes_cli/config.py:2686 @ 863e313`

```python
    def _walk(value: Any, path: Tuple[str, ...]) -> None:
```

在**未归一化的 raw config** 上算,得到"用户真的自己写过的叶子路径"集合。必须用 raw:
归一化会注入 `agent.max_turns` 之类的默认值,用归一化后的算就分不清谁是用户写的。

`hermes_cli/config.py:2698 @ 863e313`

```python
def _strip_default_values(
```

`hermes_cli/config.py:2714 @ 863e313`

```python
    preserve_keys = {("_config_version",)} | set(preserve_keys or ())
```

`hermes_cli/config.py:2716 @ 863e313`

```python
    def _strip(value: Any, default: Any, path: Tuple[str, ...]) -> Any:
        if path in preserve_keys:
            return copy.deepcopy(value)
```

`hermes_cli/config.py:2733 @ 863e313`

```python
        if value == default:
            return None
```

**这是"用 `None` 当哨兵表示已剥离"的实现**,直接导致 D-5:值本身为 `None` 的键
无法与"已剥离"区分,**即使在 preserve_keys 里也会被丢掉**(已实测)。

`hermes_cli/config.py:2738 @ 863e313`

```python
    result: Dict[str, Any] = {}
    for key, value in config.items():
        stripped = _strip(value, defaults.get(key), (key,))
        if stripped is not None:
            result[key] = stripped
```

子树全被剥离时整段删除(2730-2731 的 `return None`),所以 `gateway:` 这种用户
完全没意见的段不会污染 config.yaml。

---

## 8. 机制:`${VAR}` 展开与缓存环境快照(2486-2591, 2609-2670)

### 8.1 两种引用形态

`hermes_cli/config.py:2486 @ 863e313`

```python
def _env_expand_match(m: re.Match) -> str:
```

`hermes_cli/config.py:2504 @ 863e313`

```python
    raw = m.group(0)
    inner = m.group(1).strip()
    if inner.startswith("env:"):
```

- `${VAR}` —— 旧式裸名,查 `os.environ`
- `${env:VAR}` —— Cursor 风格 SecretRef,剥前缀后同样查 `os.environ`

`hermes_cli/config.py:2518 @ 863e313`

```python
    if ":" in inner and re.match(r"^[a-z][a-z0-9_-]*:", inner):
```

`vault:` / `bitwarden:` / `file:` 这类**非 env 源不解析**,只 warn 一次并原样保留,
理由:外部密钥后端在启动时通过 `secrets:` 块把值注入环境,配置里只需引用 env 形态。

`hermes_cli/config.py:2531 @ 863e313`

```python
    return os.environ.get(inner, raw)
```

**未解析就保留字面量**(不是替空),这样调用方能检测到"这个 ref 没生效"。

`hermes_cli/config.py:2546 @ 863e313`

```python
def _expand_env_vars(obj):
```

`hermes_cli/config.py:2555 @ 863e313`

```python
        return re.sub(r"\${([^}]+)}", _env_expand_match, obj)
```

只处理字符串值;**dict 的键不展开**,数字/布尔/None 原样。

### 8.2 缓存新鲜度的第三个维度

`hermes_cli/config.py:2563 @ 863e313`

```python
def _env_ref_snapshot(obj, snapshot=None):
```

`hermes_cli/config.py:2581 @ 863e313`

```python
        for raw in re.findall(r"\${([^}]+)}", obj):
```

**解决什么问题**:`load_config()` 缓存键是 `(mtime_ns, size)`。如果第一次
`load_config()` 发生在 `load_hermes_dotenv()` 之前,`${OPENAI_API_KEY}` 展开成
字面量并被缓存,**整个进程生命周期都拿不到真 key**(#58514)。文件签名看不见这件事。
于是缓存条目额外存一份"当时这些 env 名各自的值",命中时逐个比对:

`hermes_cli/config.py:3330 @ 863e313`(段外·上下文)

```python
            if all(os.environ.get(k) == v for k, v in env_snapshot.items()):
```

`_env_ref_var_name`(2534)保证 `${env:FOO}` 记在真名 `FOO` 下,非 env 源不进快照
(它们本来就不读环境)。测试:`tests/hermes_cli/test_config_env_ref_parity.py:44 @ 863e313`

```python
def test_snapshot_detects_rotation_for_env_prefixed(monkeypatch):
```

### 8.3 回写时把明文换回模板 `_preserve_env_ref_templates`

`hermes_cli/config.py:2609 @ 863e313`

```python
def _preserve_env_ref_templates(current, raw, loaded_expanded=None):
```

**解决什么问题**:`load_config()` 展开了 `${OPENROUTER_API_KEY}`;某个调用方改了
一个无关设置就 `save_config(cfg)` —— 如果直接写,**用户的 API key 明文就被写进
config.yaml 了**。

`hermes_cli/config.py:2623 @ 863e313`

```python
    if isinstance(current, str) and isinstance(raw, str) and re.search(r"\${[^}]+}", raw):
```

三条"判定为未改动、还原模板"的规则:① `current == raw`(压根没展开);
② `current == loaded_expanded`(等于本进程上次 load 出来的展开值,可容忍 env 轮换);
③ `_expand_env_vars(raw) == current`(等于当前环境下的展开值)。都不满足 → 认为
调用方真的改了这个值,写 `current`。

`hermes_cli/config.py:2647 @ 863e313`

```python
        current_by_name = _items_by_unique_name(current)
```

列表(如 `custom_providers`)优先按 `name` 配对,**避免重排顺序导致模板被写成明文**;
名字重复时退回按下标配对(`_items_by_unique_name` 见 2594,重名即返回 `None`)。

---

## 9. 机制:读写共用的两个归一化器(2746-2858)

`load_config` 与 `save_config` 都调用同一对函数,顺序也一样:

`hermes_cli/config.py:3389 @ 863e313`(段外·上下文,读路径)

```python
        normalized = _normalize_root_model_keys(_normalize_max_turns_config(config))
```

`hermes_cli/config.py:3563 @ 863e313`(段外·上下文,写路径)

```python
        current_normalized = _normalize_root_model_keys(_normalize_max_turns_config(config))
```

**这就是"单一收敛点"设计**:任何别名/旧位置只在这一对函数里处理一次,读的人看到
的永远是规范形态,写的人顺手把磁盘也规范化掉。

### 9.1 `_normalize_root_model_keys`:三个历史包袱一起收

`hermes_cli/config.py:2746 @ 863e313`

```python
def _normalize_root_model_keys(config: Dict[str, Any]) -> Dict[str, Any]:
```

① 根级 `provider` / `base_url` / `context_length` 搬进 `model.*`(仅当 `model.*` 为空,
   fallback-only,不覆盖):

`hermes_cli/config.py:2802 @ 863e313`

```python
    for key in ("provider", "base_url", "context_length"):
        root_val = config.get(key)
        if root_val and not model.get(key):
            model[key] = root_val
        config.pop(key, None)
```

② `api_base` → `base_url` 别名(#8919)。事故经过写在 docstring 里:`api_base` 是
   OpenAI-SDK/LiteLLM 用户的直觉名字,而 `hermes config set` **对任意点分键照单全收**,
   于是 `model.api_base` 被写进去、被确认成功、再被运行时解析器(只读 `model.base_url`)
   彻底无视,请求悄悄回落到 OpenRouter。

`hermes_cli/config.py:2809 @ 863e313`

```python
    for alias_val in (config.get("api_base"), model.get("api_base")):
```

③ 模型 id 规范到 `model.default`(#34500),优先级 `default > model > name`:

`hermes_cli/config.py:2818 @ 863e313`

```python
    if not (model.get("default") or ""):
        alias = model.get("model") or model.get("name")
```

   事故经过:`model: {name: <id>, provider: <custom>}` 解析出空模型名,请求带
   `model=` 发出去被 400;而 `hermes status` / `dump` 读的是 `name`,**显示一切正常**,
   故障因此"静默"。

短路守卫在 2788,没有任何可迁移内容时原样返回(避免每次读都构造新 dict):

`hermes_cli/config.py:2788 @ 863e313`

```python
    has_root = any(
```

### 9.2 `_normalize_max_turns_config`:默认值绝不"粘住"

`hermes_cli/config.py:2830 @ 863e313`

```python
def _normalize_max_turns_config(config: Dict[str, Any]) -> Dict[str, Any]:
```

`hermes_cli/config.py:2842 @ 863e313`

```python
    had_root = "max_turns" in config
    had_agent = "max_turns" in agent_config
```

`hermes_cli/config.py:2851 @ 863e313`

```python
    if not had_root and not had_agent:
        pass  # deliberately do not inject DEFAULT_CONFIG default
```

**核心取舍**:根级 `max_turns` 是 legacy 位置,要搬到 `agent.max_turns`;但如果用户
两处都没写,**绝不能**顺手注入 `DEFAULT_CONFIG["agent"]["max_turns"]`(=500,见
`hermes_cli/config_defaults.py:32 @ 863e313`)

```python
        "max_turns": 500,
```

否则一次 `load_config()` → `save_config()` 往返就把 500 钉死在用户文件里,以后官方
改默认值对这个用户永久失效。

`hermes_cli/config.py:2856 @ 863e313`

```python
    config["agent"] = agent_config
```

但这一行是**无条件**的:原本没有 `agent` 段的配置会被塞进一个空 `agent: {}`,而
`_strip_default_values` 保留空 dict(实测),于是磁盘上多出一行 `agent: {}`(D-9,
无行为影响,纯噪声)。

---

## 10. 写路径全景:原子性与"不丢用户数据"

任务点名要问的是 set/unset/edit 的原子性。**命令入口本身在我这段之外**,但保障机制
的实现全在这段里。完整链路(★=本段代码):

```
hermes config set k v
  └─ set_config_value(4823)            # 段外:键校验 + 类型解析 + managed 拒绝
       ├─ _validate_config_key(4727)   # 段外:未知键 → 建议最近键
       ├─ read_raw_config(2933)        # 只读用户文件,不合默认
       ├─ _set_nested(992)             # 段外:点分路径写入
       └─ save_config(3505)
            ├─ is_managed() → 拒写
            ├─ ★_strip_dotted_keys(2463)          # 摘掉 managed 钉住的叶子
            ├─ require_readable_config_before_write(3065)
            ├─ read_raw_config → ★_explicit_config_paths(2673)
            ├─ [merge_existing] ★_merge_partial_save(2416)
            ├─ ★_normalize_max_turns_config(2830) → ★_normalize_root_model_keys(2746)
            ├─ ★_preserve_env_ref_templates(2609)  # 明文换回 ${VAR}
            ├─ ★_strip_default_values(2698)        # 默认值不落盘
            └─ atomic_yaml_write(utils.py:335)     # 临时文件 + fsync + os.replace
```

### 10.1 原子性的三道保险

**① 物理原子:临时文件 + rename。** `utils.py:335 @ 863e313`

```python
def atomic_yaml_write(
```

`utils.py:346 @ 863e313`

```python
    Uses temp file + fsync + os.replace to ensure the target file is never
```

**② 语义 fail-closed:不可读就不许覆盖。** `hermes_cli/config.py:3065 @ 863e313`(段外)

```python
def require_readable_config_before_write(config_path: Optional[Path] = None) -> None:
```

`hermes_cli/config.py:3089 @ 863e313`(段外)

```python
def atomic_config_write(config_path: Path, data: Any, **kwargs: Any) -> None:
```

根因写得很清楚:`read_raw_config()` 对"文件不存在"和"文件存在但读不了(权限、
挂载断了)"**都返回 `{}`**,调用方分不清,于是会把一个读不了的配置覆盖成默认值。
所以在写之前主动 `stat` + 读 1 字节验证。

**③ 内容层不丢:** §7 的默认值剥离 + explicit-paths 保留 + §8.3 的模板还原。

`save_config` 自己不调 `atomic_config_write`,而是先手动
`require_readable_config_before_write`(3550)再直接 `atomic_yaml_write`(3611)——
等价,但**绕过了那个"唯一收口"的设计意图**(D-10,风格问题非功能问题)。

### 10.2 点分路径怎么走(段外·上下文,本段只用不定义)

三件套都在 992-1150:

`hermes_cli/config.py:992 @ 863e313`

```python
def _set_nested(config, dotted_key: str, value):
```

`hermes_cli/config.py:1073 @ 863e313`

```python
def _get_nested(config, dotted_key: str):
```

`hermes_cli/config.py:1091 @ 863e313`

```python
def _unset_nested(config, dotted_key: str) -> bool:
```

规则:`key.split(".")` 逐段下钻;**数字段 = 列表下标**(`custom_providers.0.api_key`);
中间层缺失时 `_set_nested` 按需造 dict,但**遇到已有 list/dict 绝不替换**
(#17876:以前无脑把非 dict 换成 `{}`,一个带下标的路径就能把 `custom_providers`
整个列表抹掉);列表不自动扩容。`_unset_nested` 删完还会**回溯清理留下的空 dict**,
但保留用户手写的空 list。

### 10.3 明确的取舍与残留风险

- **注释和格式在保存时全丢**:落盘走 PyYAML `yaml.dump`,不是 round-trip 解析器
  (全仓只有 `hermes_cli/xai_retirement.py:191` 为一次定点改写用了 ruamel)。
  `save_config` 用 `extra_content` 追加几段固定的注释模板(security / fallback_model)
  来部分补偿,但用户自己写的注释一次 `hermes config set` 就没了。
- **跨进程无锁**:`_CONFIG_LOCK` 是 `threading.RLock`(进程内)。gateway 与 CLI
  同时写 config.yaml 时,单次写是原子的(不会写坏),但**丢更新**是可能的
  (读-改-写窗口无保护)。
- 写完只清 raw 缓存,不清 `_LOAD_CONFIG_CACHE`:
  `hermes_cli/config.py:3617 @ 863e313`(段外·上下文)

```python
        _RAW_CONFIG_CACHE.pop(str(config_path), None)
```

  靠 mtime/size 变化自然失效;同时把"未展开的规范化 dict"存进
  `_LAST_EXPANDED_CONFIG_BY_PATH`,供下一次 `_preserve_env_ref_templates` 与
  last-known-good 兜底用:`hermes_cli/config.py:3618 @ 863e313`

```python
        _LAST_EXPANDED_CONFIG_BY_PATH[str(config_path)] = copy.deepcopy(current_normalized)
```

---

## 11. 类型强制/校验发生在哪(汇总)

本段里**没有 schema 校验器**(没有 pydantic / jsonschema)。类型处理分四层:

| 层 | 位置 | 做法 |
|---|---|---|
| provider 字段筛选 | 1394-1472 | `isinstance` 通过才收,不通过**静默丢弃** |
| 数值真转换 | 1774-1779(per-model ctx)/ 1787-1791(版本号) | `int(...)` + try/except |
| 布尔宽容解析 | 1582-1593(`ssl_verify`)、2877-2883(`enabled`) | 认 `true/1/yes/on` 与 `false/0/no/off` 字符串 |
| 结构体检 | 1906-2052 | 只产出 `ConfigIssue` 文本,**从不修改配置** |

真正的"键名合法性校验 + 值类型解析"在 `_validate_config_key`(4727)与
`set_config_value`(4823)——段外,属另一段任务。本段的态度是:
**读路径尽量宽容,写路径尽量保守,校验只报警不动手。**

---

## 12. 可疑缺陷清单(只记录,不修改)

**D-1 `custom_providers` 写成 dict 会连带隐藏所有 `providers:` 条目。**
`hermes_cli/config.py:1569-1572 @ 863e313`

```python
    custom_providers = config.get("custom_providers")
```
怎么踩到:用户把 legacy 列表少写了 `-` 缩进(`validate_config_structure` 恰恰把这个
列为 error 的头号场景),于是**新格式 `providers:` 里完全正确的条目也一起消失**,
现象是"我明明配了 provider,/model 里一个都没有"。实测确认返回 `[]`。

**D-2 TLS 查询"首个 URL 命中即定案",与 extra_headers 的修法不一致。**
`hermes_cli/config.py:1617-1624 @ 863e313`

```python
        out: Dict[str, Any] = {}
```
怎么踩到:同一个 base_url 配了两条(一条裸的别名 + 一条带 `ssl_ca_cert` 的),
顺序不巧就拿到空 TLS 设置,自签证书握手失败。extra_headers 的同型 bug 是 #74465,
已修并有测试;TLS 这条没修也没测试。实测:`[{无TLS},{有ssl_ca_cert}]` → `{}`。

**D-3 根级 `base_url` 的 "looks misplaced" 警告在生产调用点是死代码。**
`hermes_cli/config.py:2045 @ 863e313`

```python
        if key not in _KNOWN_ROOT_KEYS and key in _CUSTOM_PROVIDER_LIKE_FIELDS:
```
怎么踩到:doctor/auth/model_switch 三个调用点都不传参 → `load_config()` →
`_normalize_root_model_keys` 已把根 `base_url`/`context_length`/`api_base` 搬走并 pop。
所以用户永远看不到这条针对 `base_url` 的提示(`api_key`/`rate_limit_delay`/`api_mode`
仍可触发)。唯一的测试直接传 dict,绕过了这个前提。

**D-4 provider 条目里 `ssl_verify: <CA路径>` 被静默丢弃。**
`hermes_cli/config.py:1582-1593 @ 863e313`

```python
def _coerce_ssl_verify(value: Any) -> Optional[bool]:
```
怎么踩到:MCP server 配置文档明写 `ssl_verify` 可以是"bool 或 CA bundle 路径"
(`website/docs/reference/mcp-config-reference.md:53`),用户照抄到 provider 条目里;
归一化器(1471)保留了这个字符串,查询器却把它 coerce 成 `None` 丢掉,**证书不生效
且无任何提示**。provider 侧的正确字段是 `ssl_ca_cert`。实测返回 `{}`。

**D-5 值为 `null` 的配置项在保存时被丢弃,即使在 preserve_keys 里。**
`hermes_cli/config.py:2733 @ 863e313`

```python
        if value == default:
```
怎么踩到:`_strip` 用 `None` 作"已剥离"哨兵,父层用 `if stripped_child is not None`
过滤;于是用户显式写的 `max_live_sessions: null`(语义=禁用 LRU 上限)在任何一次
`save_config` 后消失,下次加载回落到默认 16。实测:
`_strip_default_values({'max_live_sessions': None}, DEFAULT_CONFIG, preserve_keys={('max_live_sessions',)})` → `{}`。

**D-6 `bool` 被当作 `int` 收进 `context_length` / `rate_limit_delay`。**
`hermes_cli/config.py:1441-1443 @ 863e313`

```python
    context_length = entry.get("context_length")
```
怎么踩到:YAML `context_length: yes` 解析成 `True`,`isinstance(True, int)` 为真且
`True > 0`,于是 `context_length=True`(等价 1)进入运行时。同文件 1785 的
`_coerce_config_version` 专门挡了 bool,说明作者知道这个坑,只是没在这里挡。
实测输出 `{'context_length': True, 'rate_limit_delay': False}`。

**D-7 `context_length` 在两个层级有两套类型规则。**
provider 级(1442)只收 `int`;per-model 级(1774)走 `int(raw_ctx)` 转换。
怎么踩到:`context_length: "200000"` 写在 provider 上无效、写在
`models.<id>.context_length` 上有效,用户无从预期。

**D-8 `_deep_merge` 浅拷贝 base,返回值与入参共享嵌套对象。**
`hermes_cli/config.py:2448 @ 863e313`

```python
    result = base.copy()
```
怎么踩到:目前两个调用点都传"自己的 deepcopy"所以安全,但
`hermes_cli/web_server.py:6923` 的 `save_config(_deep_merge(existing, incoming))`
若 `existing` 来自 `load_config_readonly()` 的共享缓存,后续对结果的原地修改会污染
进程内缓存。属"隐式契约无守卫"。

**D-9 无 `agent:` 段的配置在每次保存后多出一行 `agent: {}`。**
`hermes_cli/config.py:2856 @ 863e313`

```python
    config["agent"] = agent_config
```
怎么踩到:`_normalize_max_turns_config` 无条件写回 `agent` 键;空 dict 不等于
`DEFAULT_CONFIG["agent"]`,`_strip_default_values` 于是保留它。实测
`_strip_default_values(_normalize_max_turns_config({'model':{'default':'x'}}), ...)`
→ `{'model': {...}, 'agent': {}}`。无行为影响(读时深合并回默认),纯文件噪声。

**D-10 `save_config` 绕过了 `atomic_config_write` 这个"唯一收口"。**
`hermes_cli/config.py:3611 @ 863e313`(段外·上下文)

```python
        atomic_yaml_write(
```
`atomic_config_write` 的 docstring 自称是"every config-update path should use 的单一
收口",而全仓最主要的写入者 `save_config` 自己手动拼了守卫 + 裸 `atomic_yaml_write`。
当前等价,但守卫顺序若被改动就会静默失去保护。

**D-11 `_VALID_CUSTOM_PROVIDER_FIELDS` 是纯装饰性常量,且已过时。**
`hermes_cli/config.py:1884 @ 863e313`

```python
_VALID_CUSTOM_PROVIDER_FIELDS = {
```
生产代码零引用(只有 `tests/hermes_cli/test_runtime_provider_resolution.py` 断言它
包含某些键)。集合里没有 `extra_headers`、`discover_models`、`enabled`,而这三个都
是归一化器/文档承认的字段。"用于描述支持的 schema"的自述因此不成立。

**D-12 交互式补全里两处 `input()` 未捕获 EOF。**
`hermes_cli/config.py:2292` 与 `hermes_cli/config.py:2396` 的 `input(...)` 没有像
2328/2382 那样包 `except (EOFError, KeyboardInterrupt)`。怎么踩到:非 tty 环境
(CI、`hermes ... < /dev/null`)在这两处会抛 `EOFError` 打断迁移。前者因
`REQUIRED_ENV_VARS = {}` 实际不可达,后者需先在 2382 答 `y`。

---

## 13. 文档—代码冲突

**C-1 `save_config` docstring 说迁移步骤靠 `merge_existing=True` 保护,实际不是。**
`hermes_cli/config.py:3520 @ 863e313`(段外·上下文)

```python
    When ``merge_existing`` is True, the on-disk raw config is deep-merged
```
括号里点名 "(migration steps via `_persist_migration`)"。但 `_persist_migration`
自己的 docstring 与实现都明说**不用** `merge_existing`:
`hermes_cli/config.py:2139 @ 863e313`

```python
    ``save_config(config)`` (default-stripping ON, no ``merge_existing``);
```
以代码为准:`_persist_migration` 走 `merge_existing=False`,靠"调用方必须传
完整 `read_raw_config()`"来保证不丢段(这样迁移里的**删除**才能生效)。
`save_config` 的 docstring 该改。

**C-2 支持下限的注释说"文件 byte-for-byte 不动",但同一函数后面仍可能重写它。**
`hermes_cli/config.py:2176-2177 @ 863e313`

```python
    # NOT auto-migrated and NOT rewritten: we surface a clear, actionable
```
而 floor 分支之后是无条件执行的 MCP 安全清扫,命中即 `_persist_migration(config)`
(2248-2250),以及交互式 skill 配置写入(2409)。即:一个 v9 的老配置若含可疑
mcp_servers 条目,文件**会**被以 v33 的 `DEFAULT_CONFIG` 为基准做默认值剥离后重写
(用户显式键因 explicit-paths 保留,但注释/格式/字节全变)。

**C-3 文档承认 `providers.<key>.enabled`,归一化器把它当未知键警告。**
`website/docs/integrations/providers.md:1274 @ 863e313`

```
Each entry accepts: `api` (the endpoint base URL — `base_url`/`url` are accepted aliases), `name` (optional display name; defaults to the dict key), `key_env` or inline `api_key`, `transport` (`chat_completions` / `anthropic_messages` / `codex_responses`), `default_model`, `models`, `context_length`, `discover_models`, `extra_body`, `extra_headers`, `ssl_ca_cert` / `ssl_verify`, and `enabled: false` to hide an entry without deleting it.
```
`_KNOWN_KEYS` 里没有 `enabled`:`hermes_cli/config.py:1318 @ 863e313`

```python
    _KNOWN_KEYS = {
```
`hermes_cli/config.py:1340 @ 863e313`

```python
    unknown = set(entry.keys()) - _KNOWN_KEYS - set(_CAMEL_ALIASES.keys())
```
实测日志:`providers.p: unknown config keys ignored: enabled`。而
`is_provider_enabled`(2861)确确实实读这个键——**警告说"已忽略",实际生效**,
是最误导人的一类不一致。

**C-4 `_KNOWN_KEYS` 收下 `request_timeout_seconds` / `stale_timeout_seconds`,
归一化器却不搬运它们。** `hermes_cli/config.py:1327 @ 863e313`

```python
        "request_timeout_seconds", "stale_timeout_seconds",
```
归一化后的条目(1385-1474)没有这两个字段。查证后属**设计如此**而非缺陷:它们由
`hermes_cli/timeouts.py:40 @ 863e313` 直接从 raw provider dict 读

```python
    return _coerce_timeout(provider_config.get("request_timeout_seconds"))
```
但这意味着"归一化条目"并非 provider 配置的完整表示,任何只拿归一化结果的下游都看
不到超时设置——重实现时要显式记住这条边界。

---

## 14. 这一段涉及的配置键与环境变量(尽量穷举)

### 14.1 环境变量(本段直接读取)

| 变量 | 读取点 | 语义 / fallback |
|---|---|---|
| `MESSAGING_CWD` | 2083 `warn_deprecated_cwd_env_vars` | 已弃用,仅用于告警;规范位置是 `terminal.cwd` |
| `TERMINAL_CWD` | 2084 同上 | 已弃用;仅当 `terminal.cwd` 不是显式路径时才告警(桥接器自己也会导出它) |
| 任意 `${NAME}` / `${env:NAME}` | 2510 / 2531(`os.environ.get`)、2584(快照) | 配置值里的引用;**未设置则保留字面量**,不置空 |

`ENV_VARS_BY_VERSION`(定义在 951,段外)在 2314 被消费,决定"这次升级新增了哪些
可选 key 值得问用户":v3 `FIRECRAWL_API_KEY`/`BROWSERBASE_API_KEY`/
`BROWSERBASE_PROJECT_ID`/`FAL_KEY`,v4 `VOICE_TOOLS_OPENAI_KEY`/`ELEVENLABS_API_KEY`,
v5 WhatsApp+Slack 六个,v10 `TAVILY_API_KEY`,v11 `TERMINAL_MODAL_MODE`。

### 14.2 config.yaml 键

**provider 相关(`providers.<key>.*` 与 `custom_providers[i].*` 共用一套归一化)**

| 键 | 默认 | 读取点 | 说明 |
|---|---|---|---|
| `base_url` / `url` / `api` | 无 | 1351(段前)| 三选一,首个合法 URL 胜;缺失整条丢弃 |
| `name` | provider_key | 1377(段前)| 空则用字典 key |
| `api_key` | 无 | 1394 | 内联明文;支持 `${VAR}` |
| `key_env`(别名 `api_key_env`/`keyEnv`/`apiKeyEnv`)| 无 | 1398 | 从哪个 env 变量取 key |
| `api_mode` / `transport` | 无 | 1402 | 协议方言 |
| `model` / `default_model` | 无 | 1406 | 该 provider 的默认模型 |
| `models` | 无 | 1410 | dict 或 list,归一成 dict |
| `models.<id>.context_length` | 无 | 1771 | per-model 上下文覆写,`int()` 转换 |
| `context_length` | 无 | 1441 | 只收正 `int`(bool 漏网) |
| `rate_limit_delay` | 无 | 1445 | 只收 ≥0 的 int/float |
| `discover_models` | 无 | 1449 | 只收 bool |
| `extra_body` | 无 | 1453 | 浅拷贝进请求体 |
| `extra_headers` | 无 | 1460 → 1642 | 键值 `str()` 化;**含凭据,禁止日志** |
| `ssl_ca_cert` | 无 | 1464 / 1618 | CA bundle 路径 |
| `ssl_verify` | 无(=True)| 1468 / 1621 | 归一化留字符串,查询器只认 bool 词 |
| `enabled` | `True` | 1523 → 2877 | 仅 `false/0/no/off` 关闭;**归一化器会报"未知键"** |
| `request_timeout_seconds` / `stale_timeout_seconds` | 无 | 1327 白名单 | 本段接受但不搬运,由 `hermes_cli/timeouts.py` 直读 |

**顶层与 model 段**

| 键 | 默认 | 读取点 | 说明 |
|---|---|---|---|
| `_config_version` | 33 | 1810 / 1825 / 1841 / 2367 | 唯一无条件保留的 preserve key(2714)|
| `model.default` | 无 | 2818 | 规范模型 id;别名链 `default > model > name` |
| `model.provider` / `model.base_url` / `model.context_length` | 无 | 2802 | 根级同名键 fallback-only 搬入 |
| `model.api_base` / 根 `api_base` | 无 | 2809 | `base_url` 的别名,迁移后删除 |
| 根 `provider` / `base_url` / `context_length` | 无 | 2788-2806 | 读到即搬入 `model.*` 并从根删除 |
| `agent.max_turns` | 500 | 2842-2854 | 只有用户显式设过才落盘 |
| 根 `max_turns` | 无 | 2842 | legacy 位置,搬进 `agent.max_turns` |
| `terminal.cwd` | `"."` | 2092-2095 | 哨兵值 `.`/`auto`/`cwd`/`""` 视为"未显式设置" |
| `custom_providers` | 无 | 1569 / 1923 | legacy 列表;非 list 即整体失效(D-1)|
| `providers` | 无 | 1576 | v12 字典形态 |
| `fallback_model[.provider/.model]` | 无 | 1968-2013 | 单 dict 或链式 list,缺 provider/model 只告警 |
| `mcp_servers.<name>` / `.enabled` | 无 | 2225 / 2239 | 迁移后安全扫描,可疑条目置 `enabled: false` |
| `platform_toolsets` | 无 | 2262 | 迁移后校验 toolset 名 |
| `skills.config.<key>` | 无 | 2400(写)| 前缀取自 `SKILL_CONFIG_PREFIX`,兜底 `"skills.config"` |
| `security.redact_secrets` | `True` | 3600(段外)| 为空时 `save_config` 追加注释模板 |
| `_EXTRA_KNOWN_ROOT_KEYS` 列出的 20 个根键 | — | 1854-1880 | 合法但不在 `DEFAULT_CONFIG` 里(`image_gen`/`video_gen`/`plugins`/`signal`/`platforms`/…)|

---

## 15. 配套测试(行为规格)

- `tests/hermes_cli/test_config_validation.py` —— `validate_config_structure` 的
  全部规格:dict-instead-of-list、misplaced 字段、`_KNOWN_ROOT_KEYS` 的派生关系、
  "未知顶层键不得警告"。
- `tests/hermes_cli/test_custom_provider_extra_headers.py` —— `normalize_extra_headers`
  与 URL 匹配查询,含 #74465 的两条 shadowing 回归。
- `tests/hermes_cli/test_custom_provider_tls.py` —— TLS 只有两条 happy path,
  **无 shadowing 用例**(D-2 无保护)。
- `tests/hermes_cli/test_custom_provider_context_length.py` —— 尾斜杠不敏感匹配、
  与默认 fallback 的优先级。
- `tests/hermes_cli/test_custom_provider_normalize_no_mutate.py` —— 归一化器不得
  修改入参、不得与缓存共享 `models` 映射(对应 1300 / 1415 的浅拷贝)。
- `tests/hermes_cli/test_config_env_expansion.py` —— `${VAR}` 展开、
  **缓存的环境快照失效**(#58514)、未解析保留字面量。
- `tests/hermes_cli/test_config_env_ref_parity.py` —— `${env:VAR}` 与含冒号的普通值
  的区分、轮换检测。
- `tests/hermes_cli/test_config.py` —— `TestLoadConfigDefaults`(根级 max_turns 迁移)、
  `TestEmptyConfigSections`(`terminal:` 空段 → #58277)、`TestSaveAndLoadRoundtrip`
  (含"拒绝覆盖不可读文件")、`TestSaveConfigAtomicity`(崩溃无半写、无残留临时文件)。
- `tests/hermes_cli/test_config_validation.py` + `tests/hermes_cli/test_runtime_provider_resolution.py`
  —— 后者是 `_VALID_CUSTOM_PROVIDER_FIELDS` 的唯一引用者。
- `tests/tools/test_docker_config_migrate.py`、`tests/hermes_cli/test_cmd_update.py`
  —— `migrate_config` 的端到端使用。

---

## 16. 重实现要点(从零重写这一段必须知道的)

1. **"默认值永不落盘"是整个配置系统的支点。** 读时 `deepcopy(DEFAULT) + deep_merge(user)`,
   写时 `strip_default_values(preserve=用户raw里真实存在的路径)`。少了后半句,一次
   读-写往返就把当时的全部默认值钉死在用户文件里,官方以后改默认值对老用户永久失效。
   要实现它,你必须在**归一化之前**就把"用户到底显式写了哪些叶子路径"算出来
   (`_explicit_config_paths` on raw),因为归一化本身会注入默认值。
2. **哨兵值不能用 `None`,除非你确定配置里不会出现合法的 `null`。** hermes 用
   `None` 表示"已被剥离",于是所有显式 `null` 配置项在保存时消失(D-5)。用一个
   私有 sentinel 对象(文件里 1070 行的 `_MISSING` 就是现成的)可以避免。
3. **展开与回写必须成对设计。** 读时展开 `${VAR}` 是为了运行时好用,但只要有任何
   "读整个配置 → 改一个键 → 写回"的调用方,你就必须有 `_preserve_env_ref_templates`
   这种"值没被改动就还原模板"的机制,否则第一次 `config set` 就把用户所有密钥明文
   写进磁盘。判定"没改动"要同时容忍 env 轮换(三条规则:等于模板 / 等于上次展开值 /
   等于当前展开值)。
4. **缓存键不能只有 (mtime, size)。** 只要配置值依赖进程环境,缓存就必须额外记录
   "这次展开是在哪些 env 值下做的",命中时逐个比对。hermes 为此付出的代价是
   #58514:早于 `.env` 加载的一次 `load_config()` 污染了整个进程。
5. **别名归一化必须只有一个收敛点,而且读写共用。** `_normalize_root_model_keys` 与
   `_normalize_max_turns_config` 同时挂在 `load_config` 和 `save_config` 上:读的人
   永远看到规范形态,写的人顺手把磁盘也治好。否则就会出现 #34500 那种"显示路径读
   `name`、请求路径读 `default`,于是故障静默"的分裂。
6. **迁移梯要表驱动 + 初始版本不推进 + 单一写入口。** `(target_version, fn)` 注册表
   逐条比较**同一个**初始 `current_ver`(不是逐步推进),才能与原来的顺序 if 块字节
   等价;所有步骤只许通过一个 `_persist_migration` 落盘,不变式才守得住。再加一条
   支持下限(拒绝 + 明确提示,不崩溃、不改文件)来给"两年前的配置"一个体面的出口。
7. **写入是三层保障,缺一不可**:物理原子(tmp+fsync+rename)、语义 fail-closed
   (存在但读不了 → 拒绝覆盖,因为读函数把"不存在"和"读不了"都返回 `{}`)、
   内容不丢(默认值剥离 + 显式路径保留 + 模板还原 + managed 叶子摘除)。
8. **想清楚"用 URL 反查配置"这条旁路。** 客户端构造点只有 base_url,所以 TLS、
   extra_headers、context_length 都得能按 route identity 反查。这类查询器要统一
   "同 URL 多条目"的语义(**继续找直到有值**,而不是首个命中即定案),否则就会出现
   本段 TLS 与 headers 两套行为(D-2)。
