# r8a-raw-config-c · config.py:2800-4200

底稿。求全求证,不求好读。基线 `863e313`,目标文件 `hermes_cli/config.py`(全文 5434 行),
本段负责 **2800-4200**。所有路径相对基线仓库根。

---

## 0. 本段的边界与读法

本段是 `hermes_cli/config.py` 的"**运行时读写层**":上游(1-2800)是常量、迁移、
校验、custom provider 归一化等**准备工作**,下游(4200-5434)是 `hermes config`
子命令的**人机界面**。本段夹在中间,是所有配置读写真正落地的地方,可以切成八块:

| 区间 | 内容 |
|---|---|
| 2800-2932 | 归一化尾巴(`_normalize_root_model_keys` 收尾、`_normalize_max_turns_config`)+ 两个通用小工具(`is_provider_enabled`、`cfg_get`) |
| 2933-3062 | **三个原始读取入口**:`read_raw_config` / `read_user_config_raw` / `read_raw_config_readonly` |
| 3065-3113 | **写前守卫**:`require_readable_config_before_write` + `atomic_config_write` |
| 3115-3180 | `load_config` / `load_config_readonly` 门面 + `write_platform_config_field` |
| 3183-3280 | **`terminal.*` → 环境变量桥** |
| 3283-3427 | **`_load_config_impl`**:合并优先级 + 双层缓存 + last-known-good。本段最核心 |
| 3430-3618 | **`save_config`**:写回优先级 + "不写默认值" + 注释块注入 |
| 3621-4200 | **`.env` 全生命周期**(解析/读/写/删/消毒)+ **凭据解析**(`get_env_value` 家族)+ **展示期脱敏** |

段尾 4200 落在 `_SECRET_CONFIG_KEYS` 这个 frozenset 内部(4199-4216),所以我把
`redact_config_value`(4219-4245)一并读完再收笔;`show_config`(4248-)属于下一段,
本底稿只在"文档-代码出入"里引用它的两处默认值分歧。

模块 docstring 给的自我定位是"配置管理 + 五个 `hermes config` 子命令"。`hermes_cli/config.py:1-15 @ 863e313`

```python
"""
Configuration management for Hermes Agent.
```

注意 docstring 只说了 `~/.hermes/config.yaml` 与 `~/.hermes/.env` 两个文件,**没有提
managed scope(`/etc/hermes`)这一层**,而本段的 `_load_config_impl` / `save_config` /
`save_env_value` / `remove_env_value` 全部为它让路。详见 §12 文档冲突 D1。

---

## 1. 结论先行:本段确立的四条优先级序列

这是本段最重要的交付物。四条链各自独立,不要混为一谈。

### 1.1 配置值(config.yaml)的有效值 —— 四层,managed 压顶

```
managed scope(/etc/hermes/config.yaml,叶子级)
   > 用户 ~/.hermes/config.yaml
      > DEFAULT_CONFIG(hermes_cli/config_defaults.py)
```

`${VAR}` / `${env:VAR}` 引用**不是**第四层优先级,它只是**字符串插值**:只有用户
(或 managed)在 YAML 里显式写了 `${...}`,os.environ 才参与;没写就完全不参与。

顺序在 `_load_config_impl` 里是硬编码的四步。第一步:以 `DEFAULT_CONFIG` 的深拷贝为底。`hermes_cli/config.py:3333 @ 863e313`

```python
        config = copy.deepcopy(DEFAULT_CONFIG)
```

第二步:用户文件深合并到底座之上(用户压默认)。`hermes_cli/config.py:3347 @ 863e313`

```python
                config = _deep_merge(config, user_config)
```

第三步:归一化后展开 `${VAR}`。`hermes_cli/config.py:3389-3390 @ 863e313`

```python
        normalized = _normalize_root_model_keys(_normalize_max_turns_config(config))
        expanded = _expand_env_vars(normalized)
```

第四步:managed 配置**在用户展开之后**再深合并上去,叶子级压顶。`hermes_cli/config.py:3396-3399 @ 863e313`

```python
        managed_config = managed_scope.load_managed_config()
        if managed_config:
            managed_expanded = _expand_env_vars(managed_config)
            expanded = _deep_merge(expanded, managed_expanded)
```

**"AFTER user expansion" 是有意为之的顺序**,注释写清了原因:managed 只对**进程环境**
展开,绝不对"用户 config 里定义的引用"展开,于是用户无法用一个 `${VAR}` 去遮蔽管理员
钉死的字面量。`hermes_cli/config.py:3391-3395 @ 863e313`

```python
        # Managed scope wins at the leaf. Applied AFTER user expansion so a user
        # ${VAR} cannot shadow a managed literal: managed values are expanded only
        # against the process environment, never against user-config-defined refs.
        # This deliberately inverts the usual env-over-config precedence for the
        # keys the managed layer pins — see docs/design/managed-scope.md §4.1.
```

managed 目录的解析优先级本身是:`$HERMES_MANAGED_DIR`(需目录存在)> `/etc/hermes`
(需目录存在,且 pytest 下被忽略)> 无。`hermes_cli/managed_scope.py:52 @ 863e313`

```python
def get_managed_dir() -> Optional[Path]:
```

**取舍**:managed 压顶意味着"环境变量压配置"这条业界惯例在 managed 键上被反转。代价是
管理员钉死的键无法用环境变量临时覆盖,好处是策略真的不可绕过。

### 1.2 `${...}` 引用的解析 —— 只认 env,两种写法

`_env_expand_match` 接受两种形状:`${env:VAR}`(Cursor 风格 SecretRef)与裸 `${VAR}`
(legacy)。`hermes_cli/config.py:2506-2512 @ 863e313`

```python
    if inner.startswith("env:"):
        name = inner[len("env:"):].strip()
        if not name:
            return raw
        val = os.environ.get(name)
        if val is not None:
            return val
```

裸名走 `os.environ.get(inner, raw)` —— **解析不到就原样保留字面量**,不是变空串。`hermes_cli/config.py:2531 @ 863e313`

```python
    return os.environ.get(inner, raw)
```

其它 SecretRef 源(`file:` / `vault:` / `bitwarden:`)**不解析**,只 warn 一次并保持
原文,理由是外部密钥后端在启动时把值注入环境,所以 config 里只需要 env 形状。`hermes_cli/config.py:2518 @ 863e313`

```python
    if ":" in inner and re.match(r"^[a-z][a-z0-9_-]*:", inner):
```

注意展开只作用于**字符串值**,dict 的键、数字、布尔、None 一律不动。`hermes_cli/config.py:2546 @ 863e313`

```python
def _expand_env_vars(obj):
```

### 1.3 凭据(.env / os.environ)的读取 —— 两条相反的链,按用途选

**链 A(默认):`get_env_value`** —— os.environ(经 secret scope)优先,`.env` 兜底。`hermes_cli/config.py:4133-4143 @ 863e313`

```python
        val = _get_secret(key)
    except UnscopedSecretError:
        raise
    except Exception:
        val = os.environ.get(key)
    if val is not None:
        return val

    # Then check .env file
    env_vars = load_env()
    return env_vars.get(key)
```

**链 B:`get_env_value_prefer_dotenv`** —— `.env` 文件优先(且必须**真值**),
os.environ(经 secret scope)兜底。`hermes_cli/config.py:4160-4163 @ 863e313`

```python
    env_vars = load_env()
    val = env_vars.get(key)
    if val:
        return val
```

链 B 的存在理由写在 docstring 里:Hermes 自己管理的凭据,用户在 `.env` 里的手工改动必须
压过从父 shell 继承来的陈旧值,否则会话中途轮换密钥后仍然打 401。`hermes_cli/config.py:4146 @ 863e313`

```python
def get_env_value_prefer_dotenv(key: str) -> Optional[str]:
```

**两条链的差别有真实后果**:链 A 里 `os.environ` 有个空串 `""` 也算命中(`val is not None`),
会**直接返回空串**并且不去查 `.env`;链 B 用 `if val:` 判真值,空串会继续往下走。
`save_anthropic_api_key` 恰好会把 `ANTHROPIC_TOKEN` 写成 `""` 并同步进 `os.environ`(见 §8.4),
所以两条链对"刚被清空的槽位"给出不同答案。

### 1.4 secret scope 的三态策略(链 A/B 共用的 `os.environ` 读法)

两条链的 `os.environ` 读都不是裸读,而是过 `agent.secret_scope.get_secret`。`agent/secret_scope.py:132 @ 863e313`

```python
def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
```

它的策略:全局变量直读 environ;装了 scope 就先读 scope(多路复用开启时 scope 是权威,
miss 即 None,不回落 environ;多路复用关闭时 scope 只是 `.env` 的 overlay,miss 回落
environ);没装 scope 且多路复用开启则 **fail closed** 抛 `UnscopedSecretError`。
本段两个 reader 都**原样重抛** `UnscopedSecretError`,只对其它异常做 environ 兜底。

### 1.5 `terminal.*` 配置 → 环境变量 —— 显式压环境,默认只回填

见 §6,单列。

---

## 2. 归一化尾巴与两个小工具(2800-2932)

### 2.1 `_normalize_root_model_keys` 收尾(2800-2827)

本段起点落在这个函数中段。它把根级 `provider` / `base_url` / `context_length` 搬进
`model` 段,且**只在 model 侧为空时**回填,搬完删掉根键。`hermes_cli/config.py:2802-2806 @ 863e313`

```python
    for key in ("provider", "base_url", "context_length"):
        root_val = config.get(key)
        if root_val and not model.get(key):
            model[key] = root_val
        config.pop(key, None)
```

`api_base` 是 `base_url` 的别名,**根级和 model 内两处都认**,合并后两处都删。`hermes_cli/config.py:2809-2813 @ 863e313`

```python
    for alias_val in (config.get("api_base"), model.get("api_base")):
        if alias_val and not model.get("base_url"):
            model["base_url"] = alias_val
    config.pop("api_base", None)
    model.pop("api_base", None)
```

模型 id 的规范键是 `model.default`;`model.model` 与 `model.name` 是末位别名,**仅当
`default` 为空时**才按这个顺序取用,取完即删,防止下次 load/save 再引入歧义。`hermes_cli/config.py:2818-2825 @ 863e313`

```python
    if not (model.get("default") or ""):
        alias = model.get("model") or model.get("name")
        if alias:
            model["default"] = alias
    if model.get("default"):
        # Drop the now-redundant aliases so config.yaml ends up canonical.
        model.pop("model", None)
        model.pop("name", None)
```

于是模型 id 的键优先级链是:`model.default` > `model.model` > `model.name`;
endpoint 的键优先级链是:`model.base_url` > 根 `base_url` > 根 `api_base` > `model.api_base`
(后两者按 2809 那行的元组顺序)。

### 2.2 `_normalize_max_turns_config`(2830-2858)

**解决什么问题**:历史上 `max_turns` 写在配置根级,新 schema 在 `agent.max_turns`。
既要迁移,又不能让"用户根本没设过"的默认值被写进 config.yaml 变成粘滞值(那样以后改
schema 默认值对老用户就永远失效)。

**怎么实现**:先算出"用户到底在哪儿设过",再决定是否注入默认。`hermes_cli/config.py:2842-2854 @ 863e313`

```python
    had_root = "max_turns" in config
    had_agent = "max_turns" in agent_config

    if had_root and not had_agent:
        agent_config["max_turns"] = config["max_turns"]

    # Only inject the default when the user explicitly set max_turns
    # (either root-level or under agent).  Otherwise leave it absent so
    # save_config can omit it and the schema default fills in at runtime.
    if not had_root and not had_agent:
        pass  # deliberately do not inject DEFAULT_CONFIG default
    elif "max_turns" not in agent_config:
        agent_config["max_turns"] = DEFAULT_CONFIG["agent"]["max_turns"]
```

无条件写回 `config["agent"]` 并删掉根键。`hermes_cli/config.py:2856-2857 @ 863e313`

```python
    config["agent"] = agent_config
    config.pop("max_turns", None)
```

**注意副作用**:即使用户从没有 `agent:` 段,这个函数也会给 config 造出一个空 `agent: {}`。
在 `save_config` 里被 `_strip_default_values` 的"子树全空则整体删除"规则清掉,所以不落盘;
但任何直接吃它返回值的调用方会看到这个空段。

**在 load 路径上这段逻辑其实近乎空转**:`_load_config_impl` 传给它的是**已经和
DEFAULT_CONFIG 深合并过**的 config,`agent.max_turns` 必然存在(默认 500),`had_agent`
恒为 True。真正吃到"不注入默认"这条规则的是 `save_config`。`hermes_cli/config_defaults.py:32 @ 863e313`

```python
        "max_turns": 500,
```

顺带记全 `max_turns` 的运行时优先级(跨文件,便于对照本段的归一化):
CLI `--max-turns` > `agent.max_turns` > 根 `max_turns` > `HERMES_MAX_ITERATIONS` > 500。`cli.py:4449 @ 863e313`

```python
        elif os.getenv("HERMES_MAX_ITERATIONS"):
```

而 gateway 反向把 config 桥回环境变量(config 权威,env 只是跨进程载体)。`gateway/run.py:1888 @ 863e313`

```python
        os.environ["HERMES_MAX_ITERATIONS"] = str(agent_cfg["max_turns"])
```

### 2.3 `is_provider_enabled`(2861-2883)

**解决什么问题**:`providers.<name>.enabled` 需要一个"缺省即启用 + 容忍 YAML 把布尔写成
字符串 + 畸形条目不静默消失"的判定。

`enabled` 缺省 True。`hermes_cli/config.py:2877 @ 863e313`

```python
    flag = provider_cfg.get("enabled", True)
```

字符串按黑名单判假,注意 **`"off"` / `"no"` / `"0"` 也算 false**,这比 YAML 自身的布尔
解析更宽。`hermes_cli/config.py:2882 @ 863e313`

```python
        return flag.strip().lower() not in {"false", "0", "no", "off"}
```

非 dict(None / list / 字符串)一律返回 True,理由是"畸形条目不该静默消失,留给校验路径去报"。`hermes_cli/config.py:2875-2876 @ 863e313`

```python
    if not isinstance(provider_cfg, dict):
        return True
```

**取舍**:宽松解析让 provider 不会因为一个引号问题而在模型选择器里凭空消失,代价是
`enabled: maybe` 这种拼错值被当成启用(落到最后的 `bool(flag)`)。

### 2.4 `cfg_get`(2886-2929)

**解决什么问题**:全仓 50+ 处 `cfg.get("X", {}).get("Y", default)` 的三个坑——中间键缺失、
中间值不是 dict(用户在该写 section 的地方写了字符串)、`cfg is None`。

实现是逐级检查 + `key not in node` 判定,所以**显式 `None` 会原样返回**,只有键**不存在**
才给 default(与 `dict.get` 语义一致)。`hermes_cli/config.py:2920-2929 @ 863e313`

```python
    if not isinstance(cfg, dict):
        return default
    node: Any = cfg
    for key in keys:
        if not isinstance(node, dict):
            return default
        if key not in node:
            return default
        node = node[key]
    return node
```

命名理由也写在 docstring 里:不叫 `cfg_path` 是为了不遮蔽全仓遍布的
`cfg_path = _hermes_home / "config.yaml"` 局部变量。这是个值得学的小细节——
**通用 helper 的命名要避开调用方的高频局部名**。

---

## 3. 三个原始读取入口(2933-3062)

这三个函数加上 `load_config` / `load_config_readonly`,构成全仓**唯一合法**的
config.yaml 读取面。有一个 lint 测试专门守这条线(见 §13)。

### 3.1 `read_raw_config`(2933-2968)

不合并默认、不迁移、不做 managed overlay、不展开 `${}`,只读原文。缓存键是
`(mtime_ns, size)`,命中返回**深拷贝**(因为有调用方会改完再 `save_config`)。`hermes_cli/config.py:2945-2956 @ 863e313`

```python
    with _CONFIG_LOCK:
        try:
            config_path = get_config_path()
            st = config_path.stat()
            cache_key = (st.st_mtime_ns, st.st_size)
        except (FileNotFoundError, OSError):
            return {}

        path_key = str(config_path)
        cached = _RAW_CONFIG_CACHE.get(path_key)
        if cached is not None and cached[:2] == cache_key:
            return copy.deepcopy(cached[2])
```

解析失败 → 走统一告警 + 返回 `{}`(**吞异常**)。`hermes_cli/config.py:2961-2963 @ 863e313`

```python
        except Exception as e:
            _warn_config_parse_failure(config_path, e)
            return {}
```

miss 路径把深拷贝存进缓存、把**原对象**返回给调用方,双方互不影响。`hermes_cli/config.py:2967-2968 @ 863e313`

```python
        _RAW_CONFIG_CACHE[path_key] = (cache_key[0], cache_key[1], copy.deepcopy(data))
        return data
```

### 3.2 `read_user_config_raw`(2971-3017)

比 `read_raw_config` 更"生":**连缓存都没有**,而且**只吞 FileNotFoundError**,
YAML 解析失败会向上抛。`hermes_cli/config.py:3012-3017 @ 863e313`

```python
    try:
        with open(config_path, encoding="utf-8") as f:
            data = fast_safe_load(f) or {}
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}
```

docstring 列了**穷举的三类合法调用点**,这是本段最好的"设计意图文档",值得整段抄进蓝图:
写回往返(read → 改一个键 → save,合并默认会把几百个默认键写进用户文件)、
原始文件诊断(doctor / 弃用清扫,合并默认会产生假阳性)、
存在性敏感的 env 桥(只在用户显式设置时才导出,合并默认会把整个 DEFAULT_CONFIG 桥进环境)。`hermes_cli/config.py:2980-2994 @ 863e313`

```python
    Legal call sites, exhaustively:
```

第三类调用点被明确要求**自己内联做** `apply_managed_overlay` + `_expand_env_vars`
(gateway 的 `_bridge_max_turns_from_config` 就是这么写的,见 §2.2 引用)。
**这是一条脆弱的约定**:靠 docstring 而非类型/包装强制,新写的桥忘了就会静默丢掉 managed 覆盖。

### 3.3 `read_raw_config_readonly`(3020-3062)

`read_raw_config` 的无拷贝快路,给"每回合跑 2-3 次"的策略检查用(共享指标闸门)。
关键是**身份不变量**:第一次(miss)返回的对象必须与后续 hit 返回的是同一个,
所以 miss 路径存 `cached_copy` 并把**同一个对象**返回。`hermes_cli/config.py:3060-3062 @ 863e313`

```python
        cached_copy = copy.deepcopy(data)
        _RAW_CONFIG_CACHE[path_key] = (cache_key[0], cache_key[1], cached_copy)
        return cached_copy
```

**取舍**:安全性纯靠文档,不靠类型系统(没有返回 `MappingProxyType`,理由见
`load_config_readonly` 的 docstring:那会打断下游遍地的 `isinstance(x, dict)` 判断)。
改了返回值 = 污染全进程缓存。

---

## 4. 写前守卫与原子写(3065-3113)

### 4.1 `require_readable_config_before_write`

**解决什么问题**(根因写在 `atomic_config_write` 的 docstring 里):
`read_raw_config()` 对"文件不存在"和"文件存在但读不了(权限/挂载/瞬时 IO)"**返回同一个 `{}`**。
先读后覆写的调用方分不清这两种情况,于是一个读不了的 config 会被"只剩默认值 / 只剩被编辑的那一段"替换掉。`hermes_cli/config.py:3099-3104 @ 863e313`

```python
    Root cause this guards: ``read_raw_config()`` returns ``{}`` for BOTH an
    absent file and an unreadable-but-present file. Callers that read then
    overwrite can't tell the two apart, so an unreadable config would be
    replaced with only defaults or the single edited section. Routing every
    write through this helper enforces the invariant in one place rather than
```

实现:文件不存在 → 放行(新建合法);`stat` 失败 → 拒;能 stat 但**读不出 1 个字节** → 拒。`hermes_cli/config.py:3080-3086 @ 863e313`

```python
        with open(config_path, "rb") as f:
            f.read(1)
    except OSError as exc:
        raise RuntimeError(
            f"Refusing to overwrite {config_path}: existing config.yaml cannot be read "
            f"({exc}). Fix the file permissions or move it aside first."
        ) from exc
```

**盲区**:它守的是"**能不能读**",不是"**能不能解析**"。一个语法坏掉但权限正常的
config.yaml 照样放行覆写(缓解手段是 `_backup_corrupt_config` 的 `.bak` 快照,见 §13 缺陷 F4)。

### 4.2 `atomic_config_write`

薄封装:守卫 + `utils.atomic_yaml_write`,kwargs 原样转发。`hermes_cli/config.py:3109-3112 @ 863e313`

```python
    from utils import atomic_yaml_write

    require_readable_config_before_write(config_path)
    atomic_yaml_write(config_path, data, **kwargs)
```

它 docstring 自称"每条配置更新路径都该用它取代直接调 `atomic_yaml_write` 的单一收口点"。
实际用户是 gateway/slash_commands.py、doctor.py、tui_gateway/server.py、telegram adapter、
onboarding 等约 8 个模块。但 **`save_config` 自己没走它**(手工调守卫 + 直调
`atomic_yaml_write`),`set_config_value` / `unset_config_value` 也直调。见 §12 冲突 D2。

---

## 5. `load_config` 门面与 `write_platform_config_field`(3115-3180)

`load_config` / `load_config_readonly` 是同一个 impl 的两个开关。`hermes_cli/config.py:3129 @ 863e313`

```python
    return _load_config_impl(want_deepcopy=True)
```

`hermes_cli/config.py:3152 @ 863e313`

```python
    return _load_config_impl(want_deepcopy=False)
```

docstring 给了量化理由:cache-hit 约 265us/次,其中约 135us 是防御性 deepcopy;
agent loop 每次会话读配置 20-50 次。`hermes_cli/config.py:3142-3146 @ 863e313`

```python
    Why this exists: ``load_config()`` cache-hit cost is ~265us per call,
    half of which (~135us) is the defensive deepcopy. The agent loop calls
    into config reads (timeouts, thresholds, feature flags) ~20-50x per
    conversation; skipping deepcopy here removes a measurable allocation
    source and the GC pressure that comes with it.
```

`write_platform_config_field` 写 `platforms.<key>.<field>`,`raw=True` 走原始文件
(CLI setup 流程),`raw=False` 走 profile 感知的 `load_config`(dashboard 路由)。`hermes_cli/config.py:3168 @ 863e313`

```python
    config = read_raw_config() if raw else load_config()
```

对非 dict 的中间层做了**就地替换**(不是抛错)。`hermes_cli/config.py:3169-3177 @ 863e313`

```python
    platforms = config.setdefault("platforms", {})
    if not isinstance(platforms, dict):
        platforms = {}
        config["platforms"] = platforms

    platform_config = platforms.setdefault(platform_key, {})
    if not isinstance(platform_config, dict):
        platform_config = {}
        platforms[platform_key] = platform_config
```

**取舍**:用户把 `platforms: "oops"` 写坏时,这里会**静默丢弃**整个 platforms 段而不是报错。

---

## 6. `terminal.*` → 环境变量桥(3183-3280)

### 6.1 解决什么问题

`tools.terminal_tool` 是**环境变量驱动**的,因为它同时跑在 TUI / dashboard PTY /
gateway worker 等子进程里。这些子进程启动路径不能 import `cli.py`(启动副作用太重),
所以需要一个不依赖 CLI 的桥。`hermes_cli/config.py:3239-3242 @ 863e313`

```python
    ``tools.terminal_tool`` is intentionally environment-driven because it also
    runs in child processes (TUI, dashboard PTY, gateway workers).  This helper
    gives those child-process launch paths the same config bridge as classic
    CLI without importing ``cli.py`` and paying for its startup side effects.
```

### 6.2 映射表

一张 30 条的 `config key → env var` 表。`hermes_cli/config.py:3183-3184 @ 863e313`

```python
TERMINAL_CONFIG_ENV_MAP = {
    "backend": "TERMINAL_ENV",
```

命名不是机械前缀:`backend → TERMINAL_ENV`(历史名),其余基本是
`TERMINAL_<UPPER(key)>`。反查函数只认 `terminal.` 前缀。`hermes_cli/config.py:3225-3227 @ 863e313`

```python
    prefix = "terminal."
    if not key.startswith(prefix):
        return None
    return TERMINAL_CONFIG_ENV_MAP.get(key[len(prefix):])
```

值序列化:list / dict 走 JSON,其余 `str()`。`hermes_cli/config.py:3217-3220 @ 863e313`

```python
def _terminal_env_value(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)
```

**表与 DEFAULT_CONFIG 不是同一集合**(我逐个 grep 过 `hermes_cli/config_defaults.py`):
表里有 8 个键在 DEFAULT_CONFIG 的 `terminal` 段里**根本不存在** ——
`lifetime_seconds`、`ssh_host`、`ssh_user`、`ssh_port`、`ssh_key`、`sandbox_dir`、
`docker_persist_across_processes`、`docker_orphan_reaper`。这些只有用户显式写了才会被桥出去。
反过来,DEFAULT_CONFIG 里有而表里没有的:`font_family`、`daemon_term_grace_seconds`、
`env_passthrough`、`home_mode`、`shell_init_files`、`auto_source_bashrc`——这些不走 env 桥。

### 6.3 优先级规则(本段最微妙的一条)

```
用户 config.yaml 里显式写出的 terminal 键   >  已存在的环境变量(.env / 父 shell / 启动器)
已存在的环境变量                            >  DEFAULT_CONFIG 继承来的 terminal 键(只回填空位)
```

"显式"的判据来自**原始文件**而非合并后的 config。`hermes_cli/config.py:3250-3255 @ 863e313`

```python
    raw_config = read_raw_config()
    raw_terminal_cfg = raw_config.get("terminal")
    file_has_terminal_config = isinstance(raw_terminal_cfg, dict)
    if not file_has_terminal_config:
        raw_terminal_cfg = {}
    should_override = file_has_terminal_config if override is None else override
```

`hermes_cli/config.py:3266 @ 863e313`

```python
    explicit_keys = terminal_cfg.keys() if config is not None else raw_terminal_cfg.keys()
```

写入判定就是那一行布尔。`hermes_cli/config.py:3278-3279 @ 863e313`

```python
        if (should_override and cfg_key in explicit_keys) or env_var not in target:
            target[env_var] = _terminal_env_value(value)
```

`cwd` 有专门的旁路:`.` / `auto` / `cwd` 这三个哨兵值**不桥**(否则会把子进程钉死在
某个目录),字符串值做 `expanduser`。`hermes_cli/config.py:3272-3277 @ 863e313`

```python
        if cfg_key == "cwd":
            raw_cwd = str(value or "").strip()
            if raw_cwd in {".", "auto", "cwd"}:
                continue
            if isinstance(value, str):
                value = os.path.expanduser(value)
```

`env=None` 时**直接写 `os.environ`**(不是副本)。`hermes_cli/config.py:3248 @ 863e313`

```python
    target = os.environ if env is None else env
```

### 6.4 双向同步

反方向也有:`set_config_value` 改 `terminal.*` 时会顺手写 `.env`,`unset_config_value`
会顺手删——**`terminal.cwd` 被显式排除**(和 6.3 的哨兵旁路呼应)。`hermes_cli/config.py:4999-5001 @ 863e313`

```python
    env_var = terminal_config_env_var_for_key(key)
    if env_var and key != "terminal.cwd":
        save_env_value(env_var, _terminal_env_value(value))
```

**取舍**:一个配置项同时存在于 config.yaml 和 .env 两处,靠双向同步维持一致。代价是
用户手改任一侧都可能造成漂移(所以 doctor 里有专门的漂移检查),以及 `.env` 里会堆出
一堆 `TERMINAL_*` 噪音。

---

## 7. `_load_config_impl`:合并 + 双层缓存 + last-known-good(3283-3427)

### 7.1 缓存签名:用户文件 + managed 文件 + 环境快照

**解决什么问题**:光用文件 mtime 做缓存键,有两个漏网场景——
(a) 管理员改了 `/etc/hermes/config.yaml`,用户文件没动;
(b) 配置里的 `${VAR}` 引用值变了(`load_config()` 跑在 `load_hermes_dotenv()` 之前、
或者进程内轮换了密钥),文件一个字节没变。

(a) 靠把 managed 文件的 `(mtime_ns, size)` 折进签名解决。`hermes_cli/config.py:3300-3306 @ 863e313`

```python
        managed_dir = managed_scope.get_managed_dir()
        managed_cfg_path = (managed_dir / "config.yaml") if managed_dir else None
        try:
            mst = managed_cfg_path.stat() if managed_cfg_path else None
            managed_sig = (mst.st_mtime_ns, mst.st_size) if mst else (0, 0)
        except OSError:
            managed_sig = (0, 0)
```

四元签名的构造,含"用户文件不存在但有 managed 文件"的情况。`hermes_cli/config.py:3310-3320 @ 863e313`

```python
        if user_sig is not None:
            cache_sig: Optional[Tuple[int, int, int, int]] = (
                user_sig[0],
                user_sig[1],
                managed_sig[0],
                managed_sig[1],
            )
        elif managed_sig != (0, 0):
            cache_sig = (0, 0, managed_sig[0], managed_sig[1])
        else:
            cache_sig = None
```

(b) 靠**环境引用快照**解决:缓存元组第 6 位存 `{被引用的VAR: 当时的os.environ值}`,
命中时逐个复核。`hermes_cli/config.py:3323-3331 @ 863e313`

```python
        if cached is not None and cache_sig is not None and cached[:4] == cache_sig:
            # File signatures match, but the cached expansion is only valid if
            # every ${VAR} it was expanded against still has the same value.
            # Without this, a load_config() that ran before load_hermes_dotenv()
            # pins unexpanded literals (e.g. auxiliary.<task>.api_key) for the
            # life of the process (#58514).
            env_snapshot = cached[5] if len(cached) > 5 else {}
            if all(os.environ.get(k) == v for k, v in env_snapshot.items()):
                return copy.deepcopy(cached[4]) if want_deepcopy else cached[4]
```

快照在 miss 路径上从**归一化后、展开前**的 config 提取,managed 的引用也叠加进去。`hermes_cli/config.py:3410-3414 @ 863e313`

```python
            cached_copy = copy.deepcopy(expanded)
            env_snapshot = _env_ref_snapshot(normalized)
            if managed_config:
                _env_ref_snapshot(managed_config, env_snapshot)
            _LOAD_CONFIG_CACHE[path_key] = (*cache_sig, cached_copy, env_snapshot)
```

快照本身只登记**真的会读环境**的引用(非 env 源前缀的 ref 被排除)。`hermes_cli/config.py:2563 @ 863e313`

```python
def _env_ref_snapshot(obj, snapshot=None):
```

**没有引用 = 空快照 = `all([])` 恒真**,退化成纯 mtime 缓存,零开销。这个退化是对的。

缓存元组的形状与"为什么不需要显式失效钩子"写在模块级注释里(`atomic_yaml_write` 产生新
inode,mtime_ns 必变)。`hermes_cli/config.py:248 @ 863e313`

```python
_LOAD_CONFIG_CACHE: Dict[str, Tuple[int, int, int, int, Dict[str, Any], Dict[str, Optional[str]]]] = {}
```

缓存按 `str(config_path)` 分桶,所以 profile 切换(改 `HERMES_HOME`)不会串味。`hermes_cli/config.py:3287 @ 863e313`

```python
        path_key = str(config_path)
```

`get_config_path()` 的 profile 感知来自 `get_hermes_home()`:context-local override >
`HERMES_HOME` 环境变量 > 平台默认(POSIX `~/.hermes`,Windows `%LOCALAPPDATA%\hermes`)。`hermes_constants.py:114 @ 863e313`

```python
def get_hermes_home() -> Path:
```

### 7.2 last-known-good:解析失败不许静默降级到默认

**解决什么问题**:长跑的 gateway,用户中途把 config.yaml 编辑成坏 YAML。旧行为是
落到 `DEFAULT_CONFIG`,**连 `approvals.deny` 这种安全规则一起丢掉**——那些规则本该
连 yolo 模式都拦得住。注释直接点名这是 openai/codex#31188 的不变量移植。`hermes_cli/config.py:3349-3360 @ 863e313`

```python
                # Last-known-good fallback (port of openai/codex#31188's
                # invariant: a parse failure in a policy/config file must not
                # silently replace the effective policy with an empty/default
                # one). Falling through to DEFAULT_CONFIG here drops EVERY user
                # override — including security-critical ``approvals.deny``
                # rules, which are supposed to block commands even under yolo.
                # A long-running gateway whose user mid-edits config.yaml into
                # broken YAML would silently lose those rules on the next load.
                # Within a running process we still have the last successfully
                # loaded config — keep serving it until the file is fixed.
                # Fresh processes with no last-known-good keep the existing
                # DEFAULT_CONFIG fallback.
```

**怎么实现**:进程内保留 `_LAST_EXPANDED_CONFIG_BY_PATH`,失败时取出来防御性再展开一次。`hermes_cli/config.py:3361-3375 @ 863e313`

```python
                lkg = _LAST_EXPANDED_CONFIG_BY_PATH.get(path_key)
                _warn_config_parse_failure(
                    config_path,
                    e,
                    fallback="last-known-good" if lkg is not None else "defaults",
                )
                if lkg is not None:
                    # save_config() stores the pre-expansion normalized dict
                    # (env-ref templates preserved); the load path stores the
                    # expanded one. Expand defensively — idempotent when the
                    # stored value is already expanded.
                    from typing import cast as _cast
                    lkg_copy: Dict[str, Any] = _cast(
                        Dict[str, Any], _expand_env_vars(copy.deepcopy(lkg))
                    )
```

LKG 被缓存在**坏文件的签名**下,配空快照(空快照恒有效),这样重复 load 不会反复解析坏文件;
一旦文件被修好签名就变,自动正常重载。`hermes_cli/config.py:3381-3387 @ 863e313`

```python
                        _empty_env: Dict[str, Optional[str]] = {}
                        _LOAD_CONFIG_CACHE[path_key] = (
                            cache_sig[0], cache_sig[1],
                            cache_sig[2], cache_sig[3],
                            lkg_copy, _empty_env,
                        )
                    return copy.deepcopy(lkg_copy) if want_deepcopy else lkg_copy
```

**局限**(重要):LKG 是**进程内**的。新拉起的进程没有 LKG,仍然落到 DEFAULT_CONFIG,
安全规则照样丢。注释自己承认了这一点。

**双重要点**:load 路径存的是**展开后**的,save 路径存的是**展开前**的。`hermes_cli/config.py:3400 @ 863e313`

```python
        _LAST_EXPANDED_CONFIG_BY_PATH[path_key] = copy.deepcopy(expanded)
```

对照 save。`hermes_cli/config.py:3618 @ 863e313`

```python
        _LAST_EXPANDED_CONFIG_BY_PATH[str(config_path)] = copy.deepcopy(current_normalized)
```

所以 LKG 里可能混着两种形态,`_expand_env_vars` 的幂等性是这套东西成立的前提
(对已展开的值再展开一次是 no-op,因为里面已经没有 `${}`了——除非展开结果本身含 `${}`,
那是极端边角)。

### 7.3 root max_turns 的第二处提升

merge **之前**在 `user_config` 上又做了一次 root→agent 提升,与 `_normalize_max_turns_config`
重复但语义不同:这里用 `is None` 判断(而非 `in`),而且发生在与默认合并之前,
所以能真正区分"用户在 agent 段写了 max_turns"和"没写"。`hermes_cli/config.py:3340-3345 @ 863e313`

```python
                if "max_turns" in user_config:
                    agent_user_config = dict(user_config.get("agent") or {})
                    if agent_user_config.get("max_turns") is None:
                        agent_user_config["max_turns"] = user_config["max_turns"]
                    user_config["agent"] = agent_user_config
                    user_config.pop("max_turns", None)
```

### 7.4 返回对象的身份约定

三条路径,都写清了返回的是不是缓存对象:
- 命中且 `want_deepcopy=False`:返回缓存对象本身;
- miss 且 `want_deepcopy=False` 且有 cache_sig:返回**存进缓存的那个对象**(保证
  "两次 readonly 返回同一对象"的不变量)。`hermes_cli/config.py:3418-3419 @ 863e313`

```python
            if not want_deepcopy:
                return cached_copy
```

- 无 cache_sig(文件不存在且无 managed):清缓存并返回新建对象。`hermes_cli/config.py:3420-3421 @ 863e313`

```python
        else:
            _LOAD_CONFIG_CACHE.pop(path_key, None)
```

### 7.5 并发

整个函数在 `_CONFIG_LOCK` 里。`hermes_cli/config.py:3284 @ 863e313`

```python
    with _CONFIG_LOCK:
```

用 RLock 而非 Lock 的两个理由写在定义处:libyaml 的 C 扩展对同一文件的并发
`safe_load()` 非线程安全;`save_config` 内部会调 `read_raw_config`(重入)。`hermes_cli/config.py:260 @ 863e313`

```python
_CONFIG_LOCK = threading.RLock()
```

---

## 8. `save_config`:写回路径(3430-3618)

### 8.1 五道闸门,顺序固定

1. **managed 写锁**(`HERMES_MANAGED`,粗粒度包管理器锁)—— 直接 return,不报错不抛异常。`hermes_cli/config.py:3527-3529 @ 863e313`

```python
        if is_managed():
            managed_error("save configuration")
            return
```

2. **managed scope 叶子剥离** —— 批量写时把管理员钉死的叶子**剥掉再写**,让"其余部分仍能落盘",
   并在 stderr 打一条说明。单键 `config set` 则是硬拒绝(在 `set_config_value` 里)。`hermes_cli/config.py:3537-3545 @ 863e313`

```python
        managed_keys = managed_scope.managed_config_keys()
        if managed_keys:
            config, _stripped = _strip_dotted_keys(copy.deepcopy(config), managed_keys)
            if _stripped:
                print(
                    f"Note: {len(_stripped)} managed setting(s) were not saved "
                    f"(managed by your administrator): {', '.join(sorted(_stripped))}",
                    file=sys.stderr,
                )
```

3. **可读性守卫**。`hermes_cli/config.py:3550 @ 863e313`

```python
        require_readable_config_before_write(config_path)
```

4. **"用户显式写过哪些叶子"** —— 必须在任何归一化**之前**从**原始文件**算,
   否则 `_normalize_max_turns_config` 注入的 `agent.max_turns` 会被误判成用户设的。`hermes_cli/config.py:3555-3558 @ 863e313`

```python
        _raw_for_paths = read_raw_config()
        explicit_raw_paths: Optional[Set[Tuple[str, ...]]] = (
            _explicit_config_paths(_raw_for_paths) if _raw_for_paths else None
        )
```

5. **可选的局部合并**(`merge_existing=True`)。`hermes_cli/config.py:3559-3560 @ 863e313`

```python
        if merge_existing and _raw_for_paths:
            config = _merge_partial_save(_raw_for_paths, config)
```

`merge_existing` 的语义边界在 docstring 里划得很清:部分写(迁移步骤)必须开,
**全文档替换**(dashboard 原始 YAML 编辑器)必须关,否则用户的**删除操作会被复活**。`hermes_cli/config.py:3520-3524 @ 863e313`

```python
    When ``merge_existing`` is True, the on-disk raw config is deep-merged
    under *config* before writing so partial callers (migration steps via
    ``_persist_migration``) cannot drop unrelated sections the caller omitted.
    Full-document replacement callers (dashboard raw YAML editor, callers that
    already deep-merge) must leave this False so intentional deletions survive.
```

### 8.2 写回时的"不写默认值"

**解决什么问题**:如果每次 save 都把合并后的整棵树写盘,config.yaml 会被几百个 schema
默认值污染,之后**改默认值对老用户永远失效**(他们的文件里钉死了旧默认)。

保留集 = `_config_version` ∪ 用户原始文件里的显式叶子 ∪ 调用方指定的 `preserve_keys`。`hermes_cli/config.py:3580-3584 @ 863e313`

```python
        effective_preserve_keys: Set[Tuple[str, ...]] = {("_config_version",)}
        if explicit_raw_paths:
            effective_preserve_keys.update(explicit_raw_paths)
        if preserve_keys:
            effective_preserve_keys.update(preserve_keys)
```

然后剥默认。`hermes_cli/config.py:3590-3594 @ 863e313`

```python
            normalized = _strip_default_values(
                normalized,  # type: ignore[arg-type]
                DEFAULT_CONFIG,
                preserve_keys=effective_preserve_keys,
            )
```

`_strip_default_values` 的两条规则:命中 preserve 集就整枝保留;子树被剥空则整段删除
(避免 `gateway:` 这种"用户毫无意见"的段落白占地方)。`hermes_cli/config.py:2698 @ 863e313`

```python
def _strip_default_values(
```

### 8.3 `${VAR}` 模板保护:不把展开后的明文密钥写回盘

**解决什么问题**:`load_config()` 会把 `api_key: ${OPENROUTER_API_KEY}` 展开成明文。
调用方改了别的设置再 save,如果直写就会把**明文密钥落盘**。

`hermes_cli/config.py:3570-3575 @ 863e313`

```python
        if raw_existing:
            normalized = _preserve_env_ref_templates(
                normalized,
                raw_existing,
                _LAST_EXPANDED_CONFIG_BY_PATH.get(str(config_path)),
            )
```

判定逻辑有三个"算作未改动"的条件:值等于原始模板;值等于**上次 load 返回过的展开值**
(处理 load 与 save 之间发生的密钥轮换);值等于**当前环境下对模板的展开**。三者皆不满足
才认为是调用方的真实编辑,写字面量。`hermes_cli/config.py:2623-2630 @ 863e313`

```python
    if isinstance(current, str) and isinstance(raw, str) and re.search(r"\${[^}]+}", raw):
        if current == raw:
            return raw
        if isinstance(loaded_expanded, str) and current == loaded_expanded:
            return raw
        if _expand_env_vars(raw) == current:
            return raw
        return current
```

列表比对优先按 `name` 字段配对(custom_providers 重排不会丢模板),名字重复则退回按位置。`hermes_cli/config.py:2647-2650 @ 863e313`

```python
        current_by_name = _items_by_unique_name(current)
        raw_by_name = _items_by_unique_name(raw)
        loaded_by_name = _items_by_unique_name(loaded_expanded)
        if current_by_name is not None and raw_by_name is not None:
```

**取舍**:这是启发式,不是保证。"用户把 `${A}` 改成 `${A}suffix`"这类混合编辑一旦渲染值
分叉,就按调用方所有权处理——可能写出明文。

### 8.4 注释块注入

两个 heredoc 常量,在对应功能"未显式配置"时追加到 YAML 末尾,当作内联文档。`hermes_cli/config.py:3599-3609 @ 863e313`

```python
        sec = normalized.get("security", {})
        if not sec or sec.get("redact_secrets") is None:
            parts.append(_SECURITY_COMMENT)
        fb = normalized.get("fallback_model", {})
        fb_is_valid = False
        if isinstance(fb, list):
            fb_is_valid = any(isinstance(e, dict) and e.get("provider") and e.get("model") for e in fb)
        elif isinstance(fb, dict):
            fb_is_valid = bool(fb.get("provider") and fb.get("model"))
        if not fb_is_valid:
            parts.append(_FALLBACK_COMMENT)
```

`_FALLBACK_COMMENT` 是本段唯一一处**列举 provider ↔ 环境变量对应关系**的地方,
对本轮"凭据/路由"专题很有价值(我逐个 grep 确认这些变量名在代码里真实存在)。`hermes_cli/config.py:3454-3463 @ 863e313`

```python
# Supported providers:
#   openrouter   (OPENROUTER_API_KEY)  — routes to any model
#   openai-codex (OAuth — hermes auth) — OpenAI Codex
#   nous         (OAuth — hermes auth) — Nous Portal
#   zai          (ZAI_API_KEY)         — Z.AI / GLM
#   kimi-coding  (KIMI_API_KEY)        — Kimi / Moonshot
#   kimi-coding-cn (KIMI_CN_API_KEY)   — Kimi / Moonshot (China)
#   minimax      (MINIMAX_API_KEY)     — MiniMax
#   minimax-cn   (MINIMAX_CN_API_KEY)  — MiniMax (China)
#   bedrock      (AWS IAM / boto3)     — AWS Bedrock (Converse API)
```

`_SECURITY_COMMENT` 则给出 tirith 的 config 键与 env 覆盖对。`hermes_cli/config.py:3436-3438 @ 863e313`

```python
# tirith pre-exec scanning is enabled by default when the tirith binary
# is available. Configure via security.tirith_* keys or env vars
# (TIRITH_ENABLED, TIRITH_BIN, TIRITH_TIMEOUT, TIRITH_FAIL_OPEN).
```

这四个 env 在 tirith 侧确实是 **env 压 config 压默认**(与 §1.1 的 managed 反转正相反)。`tools/tirith_security.py:84 @ 863e313`

```python
        "tirith_path": os.getenv("TIRITH_BIN", cfg.get("tirith_path", defaults["tirith_path"])),
```

### 8.5 落盘与缓存后处理

`hermes_cli/config.py:3611-3618 @ 863e313`

```python
        atomic_yaml_write(
            config_path,
            normalized,
            extra_content="".join(parts) if parts else None,
        )
        _secure_file(config_path)
        _RAW_CONFIG_CACHE.pop(str(config_path), None)
        _LAST_EXPANDED_CONFIG_BY_PATH[str(config_path)] = copy.deepcopy(current_normalized)
```

注意:显式清了 `_RAW_CONFIG_CACHE`,**没有清 `_LOAD_CONFIG_CACHE`**(靠新 inode 的
mtime 变化自然失效),并且落盘的是**剥了默认值的 `normalized`**,而 LKG 存的是
**剥之前的 `current_normalized`**(完整树)。这个不对称是对的:LKG 要能当"有效配置"用。

---

## 9. `.env` 全生命周期(3621-4048)

### 9.1 值解析 `_parse_env_value`

只支持 Hermes 自己写出的那个小子集:双引号(认 `\"` 和 `\\` 转义)、单引号(原样)、裸值。`hermes_cli/config.py:3624-3641 @ 863e313`

```python
    if len(value) >= 2 and value[0] == value[-1] == '"':
        quoted = value[1:-1]
        parsed: list[str] = []
        i = 0
        while i < len(quoted):
            ch = quoted[i]
            if ch == "\\" and i + 1 < len(quoted):
                next_ch = quoted[i + 1]
                if next_ch in {'"', "\\"}:
                    parsed.append(next_ch)
                    i += 2
                    continue
            parsed.append(ch)
            i += 1
        return "".join(parsed)
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1]
    return value
```

**它不剥行内注释**。而 `agent/secret_scope.py` 里另有一个 `_strip_inline_comment`
"mirrors python-dotenv (1.2.2) semantics"。所以 `KEY=abc # note` 经 `load_env()` 得到
`"abc # note"`,经 python-dotenv 路径得到 `"abc"`。见 §13 缺陷 F6。

### 9.2 `load_env` 与 mtime 记忆

**解决什么问题**:`get_env_value()` 在一次交互菜单渲染里被调几十到几百次
(`hermes tools` / `hermes setup` / 状态面板),重复解析烧掉约 300ms CPU。

缓存键是 `(path, st_mtime, st_size)`——注意是**秒级浮点 `st_mtime`**,不是 `st_mtime_ns`。`hermes_cli/config.py:3662-3666 @ 863e313`

```python
        mtime = env_path.stat().st_mtime
        size = env_path.stat().st_size
        cache_key = (str(env_path), mtime, size)
    except FileNotFoundError:
        cache_key = (str(env_path), None, None)
```

正因为粒度粗,才需要一个显式失效钮给写方用。`hermes_cli/config.py:3711 @ 863e313`

```python
def invalidate_env_cache() -> None:
```

解析:UTF-8-sig(容忍记事本 BOM)+ `errors="replace"`;跳空行和 `#` 行;
**认 bash 的 `export ` 前缀**(#6659,否则键名会变成 `"export API_KEY"`)。`hermes_cli/config.py:3692-3695 @ 863e313`

```python
                if line.startswith('export '):
                    line = line[7:]
                key, _, value = line.partition('=')
                env_vars[key.strip()] = _parse_env_value(value)
```

### 9.3 `_sanitize_env_lines`:只规整,不改语义

**解决什么问题**:CRLF / 前后空白导致的解析怪象要修,但**第一个 `=` 之后的内容是不透明的
值数据**,里面出现的 `KEY=` 绝不能被重新解释成第二条赋值(拼接赋值语义有歧义,故保持一行)。`hermes_cli/config.py:3726-3729 @ 863e313`

```python
    Content after the first ``=`` is opaque value data. A known variable name
    embedded in that value must never be reinterpreted as another assignment;
    concatenated assignments are ambiguous and therefore remain on one line.
```

实现上**一行进一行出**,空行/注释保留原样(只补 `\n`),其余 strip 后补 `\n`。`hermes_cli/config.py:3736-3740 @ 863e313`

```python
        if not stripped or stripped.startswith("#"):
            sanitized.append(raw + "\n")
            continue

        sanitized.append(stripped + "\n")
```

这个"一进一出"性质直接决定了 `sanitize_env_file` 的计数逻辑里有一段死代码(§13 F1)。

### 9.4 写入 `save_env_value`(3865-3956)

顺序即是安全策略,逐条:

managed 写锁 → managed scope env 键拒绝 → 变量名正则 → 执行影响面denylist → 剥换行 → 剥非 ASCII。

`hermes_cli/config.py:3874 @ 863e313`

```python
    if managed_scope.is_env_managed(key):
```

`hermes_cli/config.py:3883-3888 @ 863e313`

```python
    if not _ENV_VAR_NAME_RE.match(key):
        raise ValueError(f"Invalid environment variable name: {key!r}")
    _reject_denylisted_env_var(key)
    value = value.replace("\n", "").replace("\r", "")
    # API keys / tokens must be ASCII — strip non-ASCII with a warning.
    value = _check_non_ascii_credential(key, value)
```

变量名正则不许数字开头。`hermes_cli/config.py:158 @ 863e313`

```python
_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
```

denylist 是**逐名列举**而非前缀通配,注释说明了原因:`HERMES_*` 整体不能封,因为大量合法
集成凭据(`HERMES_LANGFUSE_PUBLIC_KEY` 等)用这个前缀。封的是能影响下一个子进程执行的名字
(loader / 解释器 / shell / 编辑器)+ Hermes 运行时定位(`HERMES_HOME` 等)。`hermes_cli/config.py:198-205 @ 863e313`

```python
_ENV_VAR_NAME_DENYLIST: frozenset[str] = frozenset({
    # Loader / linker
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "LD_DEBUG",
    "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FALLBACK_FRAMEWORK_PATH",
    # Python
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE",
```

**关键限定**:注释明说这个门只在**写**的时候生效,已经在 `.env` 里的值照常工作——
"重点是 dashboard 的可写面不能用来提权"。`hermes_cli/config.py:194-197 @ 863e313`

```python
# This is enforced on *write* only — values already in ``.env`` (set
# by the operator out-of-band, or pre-existing) keep working. The
# point is that the dashboard's writable surface cannot escalate by
# planting them.
```

非 ASCII 处理是**告警 + 静默剥除**(不是拒绝),理由是从 PDF/富文本复制来的相似字形会让
httpx 在请求时抛 `UnicodeEncodeError`。`hermes_cli/config.py:3814 @ 863e313`

```python
    sanitized = value.encode("ascii", errors="ignore").decode("ascii")
```

**取舍**:自动剥除意味着一个含全角字符的 key 会变成一个"看着像但其实错"的 key,
最终表现为 401 而不是 500——所以告警文案里专门写了"若认证失败请重新复制"。

引号策略:含 `#` / 引号 / 首尾空白 / **任何内部空白**都要加引号,理由是
`set -a; . file` 的分词会打断 macOS "Application Support" 这类路径。`hermes_cli/config.py:3838-3848 @ 863e313`

```python
    needs_quoting = (
        "#" in value
        or '"' in value
        or "'" in value
        or value != value.strip()
        or any(c.isspace() for c in value)
    )
    if not needs_quoting:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
```

行匹配同时认 `KEY=` 和 `export KEY=`,#40041 的教训写在 docstring 里:
写方不认 export 行 → save 追加出第二行 → 后续 delete 删掉新行 → **旧的 exported 值复活**。`hermes_cli/config.py:3851-3862 @ 863e313`

```python
def _env_line_defines_key(line: str, key: str) -> bool:
    """True when a .env line assigns ``key`` — plain or ``export``-prefixed.

    ``load_env()`` accepts the bash-compatible ``export KEY=value`` form
    (#6659), so the writers must recognise the same shape. Otherwise a
    hand-added ``export`` line is invisible to save (duplicate appended) and
    remove (line survives → the value resurrects on the next load, #40041).
    """
    stripped = line.strip()
    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()
    return stripped.startswith(f"{key}=")
```

**注意 replace 会把 `export KEY=...` 重写成 `KEY=...`**(3915 行无条件写成裸形式),
即写入行为顺带做了格式归一。

落盘:`mkstemp` 同目录 + `fsync` + `atomic_replace`,失败时清理临时文件后重抛。
权限处理有讲究:**存在原文件就恢复原 mode**(保住 Docker volume 挂载常见的 0640),
只有新建文件才收紧到 0600。`hermes_cli/config.py:3941-3947 @ 863e313`

```python
        if original_mode is not None:
            try:
                os.chmod(env_path, original_mode)
            except OSError:
                pass
        else:
            _secure_file(env_path)
```

最后同步进程环境并失效缓存。`hermes_cli/config.py:3955-3956 @ 863e313`

```python
    os.environ[key] = value
    invalidate_env_cache()
```

### 9.5 删除 `remove_env_value`(3978-4048)

对称的闸门(managed 锁、managed scope、名字正则),但**没有 denylist 检查**——删除不构成
提权,合理。文件不存在时仍然清进程环境并返回 False。`hermes_cli/config.py:4001-4003 @ 863e313`

```python
    if not env_path.exists():
        os.environ.pop(key, None)
        return False
```

删除按同一个 `_env_line_defines_key` 过滤,**删掉所有匹配行**(不像 save 只改第一行)。`hermes_cli/config.py:4012-4013 @ 863e313`

```python
    new_lines = [line for line in lines if not _env_line_defines_key(line, key)]
    found = len(new_lines) < len(lines)
```

`os.environ.pop` 与 `invalidate_env_cache()` **无论 found 与否都执行**。`hermes_cli/config.py:4046-4048 @ 863e313`

```python
    os.environ.pop(key, None)
    invalidate_env_cache()
    return found
```

### 9.6 `sanitize_env_file`(3745-3787)

读 → 消毒 → 若无变化返回 0 → 否则原子写 + `_secure_file` + 失效缓存,返回被规整的行数。
注意这里**无条件 `_secure_file`**(收紧到 0600),与 `save_env_value` 的"保留原 mode"不一致。`hermes_cli/config.py:3785-3787 @ 863e313`

```python
    _secure_file(env_path)
    invalidate_env_cache()
    return fixes
```

### 9.7 `reload_env`(4087-4106)

**解决什么问题**:进程运行中 `.env` 改了,要把变化推进 `os.environ`,包括**删除**。

新增/更新:`.env` 里的**每一个**键都推进 environ(无过滤)。`hermes_cli/config.py:4097-4100 @ 863e313`

```python
    for key, value in env_vars.items():
        if os.environ.get(key) != value:
            os.environ[key] = value
            count += 1
```

删除:只删 **Hermes 已知**的键(`OPTIONAL_ENV_VARS` ∪ `_EXTRA_ENV_KEYS`),避免误伤无关环境。`hermes_cli/config.py:4095 @ 863e313`

```python
    known_keys = set(OPTIONAL_ENV_VARS.keys()) | _EXTRA_ENV_KEYS
```

`_EXTRA_ENV_KEYS` 是"由 setup/provider 流程直接管理、不在 `OPTIONAL_ENV_VARS` 里"的名单,
约 90 个,主体是各 IM 平台凭据 + 三个 `TERMINAL_*` + Langfuse + ACP。`hermes_cli/config.py:263-266 @ 863e313`

```python
_EXTRA_ENV_KEYS = frozenset({
    "OPENAI_API_KEY", "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN",
    "DISCORD_HOME_CHANNEL", "DISCORD_HOME_CHANNEL_NAME",
```

**不对称是真实存在的**:推入无过滤、删除有过滤。见 §13 F2。

---

## 10. 凭据专项(3959-3975、4051-4177)

### 10.1 自定义 endpoint 的 key 槽位命名

**解决什么问题**:同一台主机上两个 endpoint(`127.0.0.1:8000` 和 `:8001`)必须有各自的
凭据槽位,否则第二次保存会覆盖第一次;而且 IP 打头的 slug 是数字开头,
`save_env_value` 的正则会直接拒绝。

固定前缀 `HERMES_CUSTOM_` 一箭双雕。`hermes_cli/config.py:3974-3975 @ 863e313`

```python
    slug = re.sub(r"[^A-Z0-9]+", "_", str(identity or "").upper()).strip("_")
    return f"HERMES_CUSTOM_{slug}_API_KEY" if slug else "HERMES_CUSTOM_API_KEY"
```

`127.0.0.1:8000` → `HERMES_CUSTOM_127_0_0_1_8000_API_KEY`。空 identity 有兜底名。

### 10.2 Anthropic 的两个互斥槽位

三个函数构成一个小状态机:`ANTHROPIC_TOKEN`(OAuth / setup token)与
`ANTHROPIC_API_KEY`(API key)**互斥**,设一个必清另一个;两个都清 = 改用 Claude Code
自己的凭据文件。`hermes_cli/config.py:4051-4062 @ 863e313`

```python
def save_anthropic_oauth_token(value: str, save_fn=None):
    """Persist an Anthropic OAuth/setup token and clear the API-key slot."""
    writer = save_fn or save_env_value
    writer("ANTHROPIC_TOKEN", value)
    writer("ANTHROPIC_API_KEY", "")


def use_anthropic_claude_code_credentials(save_fn=None):
    """Use Claude Code's own credential files instead of persisting env tokens."""
    writer = save_fn or save_env_value
    writer("ANTHROPIC_TOKEN", "")
    writer("ANTHROPIC_API_KEY", "")
```

`hermes_cli/config.py:4065-4069 @ 863e313`

```python
def save_anthropic_api_key(value: str, save_fn=None):
    """Persist an Anthropic API key and clear the OAuth/setup-token slot."""
    writer = save_fn or save_env_value
    writer("ANTHROPIC_API_KEY", value)
    writer("ANTHROPIC_TOKEN", "")
```

`save_fn` 注入是为了可测(以及让上层用别的写入器)。
"清空"的实现是**写空串**而非删除键,所以 `.env` 里会留下 `ANTHROPIC_TOKEN=` 这样的行,
`os.environ` 里也会留下空串条目(见 §1.3 关于两条读链对空串处理不同的说明)。

### 10.3 `save_env_value_secure`:统一凭据生命周期

**解决什么问题**(#62269 家族):只写 `.env` 不够——config.yaml 里可能还镜像着**旧值**
(`model.api_key` 等),旧镜像优先级更高会遮蔽这次轮换;而且之前从 UI 删除凭据时可能
"抑制"了 `env:<VAR>` 这个池来源,重新添加必须解除抑制。`hermes_cli/config.py:4073-4078 @ 863e313`

```python
    # Route through the unified credential lifecycle so a rotation via the
    # secret-capture path also refreshes any config.yaml mirror of the old
    # value and lifts a prior env-source suppression (#62269 fix family).
    from hermes_cli.credential_lifecycle import save_provider_env_credential

    save_provider_env_credential(key, value)
```

下游三步:写 `.env` → 用旧值去 config.yaml 里找镜像并替换成新值 → 解除该 env 源的抑制。`hermes_cli/credential_lifecycle.py:213 @ 863e313`

```python
def save_provider_env_credential(env_var: str, value: str) -> Dict[str, Any]:
```

返回值 `{"success": True, "stored_as": key, "validated": False}` —— `validated` 恒为 False,
即**这条路径不做凭据有效性验证**。`hermes_cli/config.py:4079-4083 @ 863e313`

```python
    return {
        "success": True,
        "stored_as": key,
        "validated": False,
    }
```

### 10.4 `get_env_value` 的 import 兜底

`agent.secret_scope` import 失败(循环导入 / 裁剪安装)时,退化成"environ 优先、.env 兜底"的
legacy 行为。`hermes_cli/config.py:4128-4130 @ 863e313`

```python
        if key in os.environ:
            return os.environ[key]
        return load_env().get(key)
```

注意 legacy 分支用 `key in os.environ`,主分支用 `val is not None`——两者对空串行为一致
(都算命中),但对"键存在且值为 None"不可能出现,所以等价。

docstring 记了一条历史:`get_env_value_prefer_dotenv` 和 `gateway.config._getenv`
早就走 scope 了,这个函数是三兄弟里**最后一个 scope-blind 的读取器**(#67027)。`hermes_cli/config.py:4118-4120 @ 863e313`

```python
    legacy ``os.environ`` read. Its siblings ``get_env_value_prefer_dotenv``
    and ``gateway.config._getenv`` already work this way — this was the last
    scope-blind reader of the trio (#67027).
```

---

## 11. 展示期脱敏(4184-4245)

### 11.1 `redact_key`

薄封装 `agent.redact.mask_secret`,只保留 "(not set)" 的暗色占位。`hermes_cli/config.py:4190-4191 @ 863e313`

```python
    from agent.redact import mask_secret
    return mask_secret(key, empty=color("(not set)", Colors.DIM))
```

**参数名 `key` 是误导性的**:传进来的其实是**密钥的值**(`show_config` 里
`redact_key(get_env_value(env_key))`)。`mask_secret` 的形参才叫 `value`。

### 11.2 `redact_config_value`:按键名做结构化打码

**解决什么问题**:`print` 绕过日志脱敏器;而且不透明 token(如 Cloudflare `cfut_...`)
不匹配任何厂商前缀正则。所以必须按**键名**打码而不是按值的形状。`hermes_cli/config.py:4223-4227 @ 863e313`

```python
    ``_SECRET_CONFIG_KEYS`` (case-insensitive) with a masked form via
    :func:`agent.redact.mask_secret`. Non-secret keys and scalar values pass
    through unchanged. Use this before ``print``-ing any config sub-tree that
    might carry a custom-provider ``api_key`` — ``print`` bypasses the logging
    redactor, and opaque tokens (e.g. Cloudflare ``cfut_...``) don't match the
```

名单是 **精确匹配**(不是子串),注释说明理由:免得 `token_count` / `secret_santa`
这类良性键被误打码。`hermes_cli/config.py:4199-4203 @ 863e313`

```python
_SECRET_CONFIG_KEYS = frozenset({
    "api_key",
    "apikey",
    "key",
    "token",
```

判定条件有三个 and:键是 str 且小写在名单里、**值是 str**、值非空。`hermes_cli/config.py:4238-4239 @ 863e313`

```python
            if isinstance(k, str) and k.lower() in _SECRET_CONFIG_KEYS and isinstance(v, str) and v:
                out[k] = mask_secret(v)
```

递归深度上限 20,超了**原样返回**。`hermes_cli/config.py:4233-4234 @ 863e313`

```python
    if _depth > 20:
        return value
```

**取舍与漏洞**:精确匹配意味着 `openrouter_api_key`、`apiKey2`、`x-api-key` 这类键名
**不会被打码**;非字符串值(比如密钥被 YAML 解析成 int)不打码;深度 >20 的子树不打码
(fail-open 而非 fail-closed)。见 §13 F5。

---

## 12. 文档 / 注释 与代码的出入

**D1 · 模块 docstring 漏了 managed scope。**
docstring 说"配置文件存在 `~/.hermes/` 便于取用",只列了 config.yaml 与 .env。`hermes_cli/config.py:4-6 @ 863e313`

```python
Config files are stored in ~/.hermes/ for easy access:
- ~/.hermes/config.yaml  - All settings (model, toolsets, terminal, etc.)
- ~/.hermes/.env         - API keys and secrets
```

实际本段有第三个来源 `/etc/hermes`(或 `$HERMES_MANAGED_DIR`),而且它**压过**这两个。
读 docstring 会得到错误的优先级心智模型。

**D2 · `atomic_config_write` 自称"单一收口点",但最大的写入者不走它。**
docstring 断言。`hermes_cli/config.py:3092-3094 @ 863e313`

```python
    The single chokepoint every config-update path should use instead of
    calling :func:`utils.atomic_yaml_write` directly. It runs
    :func:`require_readable_config_before_write` first, so a full-file
```

而 `save_config` 自己 `from utils import atomic_yaml_write` 并直调,守卫是手工补的。`hermes_cli/config.py:3546 @ 863e313`

```python
        from utils import atomic_yaml_write
```

`set_config_value`(4994-4995)与 `unset_config_value`(5122-5123)也直调 `atomic_yaml_write`,
**且没有前置守卫**。功能上目前无 bug(它们各自读过文件),但"单一收口点"是不成立的表述,
而且新写的路径照着 set_config_value 抄就会漏掉守卫。

**D3 · `show_config` 里的显示默认值与 DEFAULT_CONFIG 不一致。**
展示层写死 60 秒。`hermes_cli/config.py:4351 @ 863e313`

```python
    print(f"  Timeout:      {terminal.get('timeout', 60)}s")
```

schema 默认是 180。`hermes_cli/config_defaults.py:263 @ 863e313`

```python
        "timeout": 180,
```

因为 `show_config` 用的是 `load_config()`(已合并默认),`terminal.timeout` 必然存在,
这个 `60` 是**够不到的死默认值**;但它同时是一份会误导读者的"文档"。

**D4 · `read_user_config_raw` 的 docstring 承诺与实现的错位(措辞层面)。**
docstring 说"unparseable YAML / other I/O errors → raises"。`hermes_cli/config.py:3001-3003 @ 863e313`

```python
      * unparseable YAML / other I/O errors → raises (callers that want
        fail-open already wrap in try/except; callers with last-known-good
        or warn semantics rely on the exception)
```

实现只 `except FileNotFoundError`,所以确实会抛——**但也包括 PermissionError**,
而 docstring 上一行说"missing file → `{}`"容易让人以为"文件问题都不抛"。
属于表述不够精确而非行为不符,记录备查。

**D5 · `_COMMENTED_SECTIONS` 是一份与实际注入内容并存的、无人引用的副本。**
见 §13 F3。它与 `_SECURITY_COMMENT` + `_FALLBACK_COMMENT` 内容近似但**不完全相同**
(前者的 Security 段没有 tirith 那几行),是典型的"注释漂移源"。

---

## 13. 可疑缺陷(只记录不修)

**F1 · `sanitize_env_file` 的行数差分支是死代码。**`hermes_cli/config.py:3766-3770 @ 863e313`

```python
    # Count lines whose normalized representation differs.
    fixes = abs(len(sanitized) - len(original_lines))
    if fixes == 0:
        fixes = sum(1 for a, b in zip(original_lines, sanitized) if a != b)
        fixes += abs(len(sanitized) - len(original_lines))
```

`_sanitize_env_lines` 严格一行进一行出(§9.3 的实现),所以 `len(sanitized) == len(original_lines)` 恒成立
→ 第一个 `fixes` 恒为 0 → `if fixes == 0` 恒真 → 末尾 `+= abs(...)` 恒加 0。
**怎么会踩到**:不会造成错误结果,但任何人想改 `_sanitize_env_lines` 让它能增删行时,
会以为这里已经处理好了行数差——实际两条路径会重复计数(`abs(差)` 被算两次)。

**F2 · `reload_env` 会把 `.env` 里的任意变量推进 `os.environ`,绕开写入 denylist。**`hermes_cli/config.py:4097-4099 @ 863e313`

```python
    for key, value in env_vars.items():
        if os.environ.get(key) != value:
            os.environ[key] = value
```

**怎么会踩到**:`save_env_value` 拒写 `LD_PRELOAD` / `PYTHONPATH` / `PATH` / `EDITOR`,
但只要这些名字**已经在 `.env` 文件里**(用户手改、旧版本写入、被挂载进来的 .env、
被别的路径写入),`reload_env()` 就会无差别推进进程环境,之后所有 `subprocess` 继承。
denylist 的注释自己承认了"只在写时生效"(§9.4 引用),所以这是**已知取舍**而非疏漏;
但 `reload_env` 是把"文件里的历史值"主动激活成"当前进程环境"的那一步,
风险面比"值已经在 .env 里躺着"要大一档,值得单独标注。

**F3 · `_COMMENTED_SECTIONS` 是死代码。**`hermes_cli/config.py:3473 @ 863e313`

```python
_COMMENTED_SECTIONS = """
```

我在全仓 grep `_COMMENTED_SECTIONS`,除定义处外**零引用**。
**怎么会踩到**:维护者更新 provider 列表时可能改到这份不生效的副本,以为改好了。

**F4 · 写前守卫检查"可读"而非"可解析",坏 YAML 仍可被覆写。**
`require_readable_config_before_write` 只 `f.read(1)`(§4.1 引用),语法坏掉的文件照样放行。
而 `read_raw_config()` 对坏 YAML 返回 `{}`(§3.1 引用)。
**怎么会踩到**:用户把 config.yaml 改坏 → 跑 `hermes config set X Y`(或任何
read-modify-write 路径)→ `_raw_for_paths = {}` → `explicit_raw_paths = None` →
写出一个只含少量键的新文件,用户的其余配置从文件里消失。
**缓解**:`_warn_config_parse_failure` 在首次告警时做 `.bak` 快照(`hermes_cli/config.py:133 @ 863e313`)

```python
    backup_path = _backup_corrupt_config(config_path)
```

但该快照是 best-effort、吞所有异常,且**同尺寸的已有 .bak 会让它跳过**
(`hermes_cli/config.py:85-88 @ 863e313`)

```python
                if existing.stat().st_size == st.st_size:
                    # Same size as the current broken file — likely the same
                    # corruption already preserved. Avoid backup churn.
                    return None
```

即"第二次以不同方式改坏但字节数恰好相同"时没有新备份。

**F5 · `redact_config_value` 的漏网面。**
精确键名匹配 + 仅 str 值 + 深度 20 fail-open(§11.2 三处引用)。
**怎么会踩到**:custom provider 用 `openrouter_api_key:` / `x-api-key:` 之类键名
(`extra_headers` 里的 `Authorization` 倒是在名单里,但 `X-Api-Key` 不在)——
`hermes config` 一打印就是明文;或者深层嵌套的 MCP 服务器配置超过 20 层(极罕见)。

**F6 · `load_env` 不剥行内注释,与 python-dotenv 语义分叉。**
§9.1 引用的 `_parse_env_value` 没有注释处理,而 `agent/secret_scope.py` 里另有一个
`_strip_inline_comment` 自称镜像 python-dotenv 1.2.2 行为。
**怎么会踩到**:用户在 `.env` 写 `OPENROUTER_API_KEY=sk-xxx  # 主账号`。
经 `load_env()`(`hermes config` 显示、`get_env_value_prefer_dotenv` 的第一跳)拿到的值
带着 `  # 主账号` 尾巴 → 401;经 python-dotenv 那条路装载进 `os.environ` 的值是干净的
→ 同一个进程里两条链拿到不同凭据,现象是"有时候好使有时候 401"。

**F7 · `apply_terminal_config_to_env` 用 `read_raw_config()` 判"显式",漏掉 managed scope。**`hermes_cli/config.py:3250-3255 @ 863e313`

```python
    raw_config = read_raw_config()
    raw_terminal_cfg = raw_config.get("terminal")
    file_has_terminal_config = isinstance(raw_terminal_cfg, dict)
    if not file_has_terminal_config:
        raw_terminal_cfg = {}
    should_override = file_has_terminal_config if override is None else override
```

`read_raw_config()` **不做 managed overlay**(§3.1),而 `cfg` 那一侧走的是
`load_config_readonly()`(§7,含 managed)。
**怎么会踩到**:管理员在 `/etc/hermes/config.yaml` 钉死 `terminal.backend: docker`,
而用户的 `~/.hermes/config.yaml` 里**根本没有 `terminal:` 段** →
`file_has_terminal_config = False` → `should_override = False` →
`terminal.backend` 只会在 `TERMINAL_ENV` **不存在**时回填;若父 shell 或 `.env` 里有
一个陈旧的 `TERMINAL_ENV=local`,管理员钉死的 docker 后端就被环境变量压过去了。
这与 §1.1 "managed 压顶"的设计意图相矛盾。

**F8 · `apply_terminal_config_to_env(config=...)` 时,`should_override` 仍取决于用户文件。**
同上两行:`explicit_keys` 在 `config is not None` 时改用调用方的 config,
但 `should_override` 只在 `override is not None` 时才脱离 `file_has_terminal_config`。
**怎么会踩到**:调用方显式传了一个自造的 config(比如 TUI 用 profile 覆盖构造的),
而用户主文件没有 `terminal:` 段 → 调用方的 config **一个键都覆盖不了已有环境变量**,
只能回填空位。docstring 说"A caller-supplied config is its own source of explicit keys",
但这句话只对 `explicit_keys` 成立,对 `should_override` 不成立。

**F9 · `save_config` 对非 dict 的 `security` 段会抛 AttributeError。**`hermes_cli/config.py:3599-3600 @ 863e313`

```python
        sec = normalized.get("security", {})
        if not sec or sec.get("redact_secrets") is None:
```

**怎么会踩到**:用户把 `security: hello` 写进 config.yaml。`_deep_merge` 的规则是
"override 是非 dict 就整个替换"(只有 `None` 被特判跳过),所以合并后 `security` 是字符串
`"hello"`;走到 3600 时 `not sec` 为 False(非空串),`sec.get` → `AttributeError: 'str' object has no attribute 'get'`。
下一行的 `fallback_model` 反而做了 `isinstance` 三分支保护,对照之下更像遗漏。
`_deep_merge` 的 None 特判:`hermes_cli/config.py:2456-2457 @ 863e313`

```python
        elif key in result and isinstance(result[key], dict) and value is None:
            continue
```

**F10 · `write_platform_config_field` 静默丢弃畸形的 `platforms` 段。**
§5 引用的两处 `if not isinstance(...)` 直接用 `{}` 替换。
**怎么会踩到**:用户误写 `platforms: some-string`,某个平台 setup 流程跑一次
`write_platform_config_field` 之后,原值被无声替换成 `{<platform>: {<field>: value}}`,
没有任何提示。

**F11(低)· `load_env` 的缓存键用秒级 `st_mtime`。**§9.2 引用。
**怎么会踩到**:同一秒内两次写 `.env` 且**文件尺寸恰好相同**(例如把一个 32 字符的 key
换成另一个 32 字符的 key),而写入方没有调 `invalidate_env_cache()`(例如用户在外部编辑器里改的)
→ 本进程继续用旧值。模块内的写方都调了失效钮,所以只影响外部写入者。

---

## 14. 配套测试(行为规格)

我按"本段函数名"grep `tests/`,以下文件是本段的行为规格:

| 测试文件 | 覆盖本段的什么 |
|---|---|
| `tests/hermes_cli/test_config.py` | `load_config` / `save_config` 主干 |
| `tests/hermes_cli/test_config_loader_e2e.py` | 加载链端到端 |
| `tests/hermes_cli/test_read_raw_config_readonly.py` | §3.3 的四条契约:身份不变量(含首次 miss)、mtime 新鲜度、与 `read_raw_config` 内容一致、缺失/损坏退化为 `{}` |
| `tests/hermes_cli/test_config_read_guard.py` | lint 守卫:除白名单外禁止新增裸 `yaml.safe_load(config.yaml)`。白名单即 §3 说的"唯一合法读取面" |
| `tests/hermes_cli/test_config_env_expansion.py` | §1.2 `${VAR}` 展开 |
| `tests/hermes_cli/test_config_env_refs.py` | §8.3 模板保护 / §7.1 env 快照 |
| `tests/hermes_cli/test_env_load_cache.py` | §9.2 `load_env` 的 mtime 记忆 |
| `tests/hermes_cli/test_env_loader.py` | `.env` 解析 |
| `tests/hermes_cli/test_env_sanitize_on_load.py` | §9.3 消毒 |
| `tests/hermes_cli/test_env_export_line_lifecycle.py` | §9.4/9.5 的 `export KEY=` 全生命周期(#6659 + #40041) |
| `tests/hermes_cli/test_get_env_value_scope.py` | §1.3/1.4 secret scope 读取策略 |
| `tests/hermes_cli/test_managed_scope_config.py`、`test_managed_scope_loaders.py`、`test_managed_scope_writeguard.py`、`test_managed_scope_regression.py`、`test_managed_scope_cli_config.py` | §1.1 managed 压顶、§8.1 剥离与写拒绝 |
| `tests/tools/test_terminal_env_bridge.py` | §6.3 桥的优先级(显式压环境 / 默认只回填) |
| `tests/hermes_cli/test_secrets_token_rotation.py` | §10.3 轮换 + config.yaml 镜像清洗 |
| `tests/hermes_cli/test_prompt_api_key.py`、`tests/cli/test_cli_secret_capture.py` | §10 凭据捕获路径 |
| `tests/hermes_cli/test_anthropic_oauth_flow.py`、`test_anthropic_model_flow_stale_oauth.py` | §10.2 两槽位互斥 |
| `tests/cron/test_file_permissions.py` | §9.4 `.env` 权限保留 |
| `tests/hermes_cli/test_set_config_value.py` | §6.4 双向同步与 §12 D2 的直写路径 |

`tests/tools/test_terminal_env_bridge.py` 的模块 docstring 就是 §6.3 那条优先级的散文版:
"必须让显式配置的 terminal 键覆盖陈旧的 launcher/.env 值,同时为 config.yaml 里省略的键保留环境值"。

---

## 15. 本段出现的全部配置键与环境变量

### 15.1 config.yaml 键

| 键 | 默认值 | 读取点(路径:行 @ 863e313) | 语义 / fallback 链 |
|---|---|---|---|
| `model.default` | 无 | `hermes_cli/config.py:2818` | 模型 id 规范键;空则取 `model.model` → `model.name`,取后删别名 |
| `model.model` | 无 | `hermes_cli/config.py:2819` | `default` 的一级别名 |
| `model.name` | 无 | `hermes_cli/config.py:2819` | `default` 的二级别名 |
| `model.provider` | 无 | `hermes_cli/config.py:2802-2805` | 根级 `provider` 仅在此键为空时回填 |
| `model.base_url` | 无 | `hermes_cli/config.py:2802-2811` | 回填链:根 `base_url` → 根 `api_base` → `model.api_base` |
| `model.context_length` | 无 | `hermes_cli/config.py:2802-2805` | 同上模式 |
| `model.api_base` | 无 | `hermes_cli/config.py:2809` | `base_url` 别名,归一化后删除 |
| 根 `provider` / `base_url` / `context_length` / `api_base` | 无 | `hermes_cli/config.py:2788-2790` | 遗留位置;归一化后从根删除 |
| `agent.max_turns` | 500 | `hermes_cli/config.py:2854`、`3342` | 链:CLI `--max-turns` > 本键 > 根 `max_turns` > `HERMES_MAX_ITERATIONS` > 500 |
| 根 `max_turns` | 无 | `hermes_cli/config.py:2842`、`3340` | 遗留位置,归一化时提升进 `agent` 并删除 |
| `_config_version` | — | `hermes_cli/config.py:3580` | 永远在 save 的 preserve 集里,不会被当默认值剥掉 |
| `providers.<name>.enabled` | True | `hermes_cli/config.py:2877` | 只有显式 false / "false"/"0"/"no"/"off" 才禁用;非 dict 视为启用 |
| `security.redact_secrets` | True | `hermes_cli/config.py:3600`(save 侧判定) | 为 None(未设)时向 config.yaml 追加 `_SECURITY_COMMENT` |
| `security.tirith_enabled` | True | `tools/tirith_security.py:83` | env `TIRITH_ENABLED` 压本键 |
| `security.tirith_path` | `"tirith"` | `tools/tirith_security.py:84` | env `TIRITH_BIN` 压本键 |
| `security.tirith_timeout` | 5 | `tools/tirith_security.py:85` | env `TIRITH_TIMEOUT` 压本键 |
| `security.tirith_fail_open` | True | `tools/tirith_security.py:86` | env `TIRITH_FAIL_OPEN` 压本键 |
| `fallback_model` | 无 | `hermes_cli/config.py:3602-3607` | 可以是 dict 或 list;仅当含 `provider`+`model` 才算有效,否则追加 `_FALLBACK_COMMENT` |
| `platforms.<platform>.<field>` | 无 | `hermes_cli/config.py:3169-3179` | 由 `write_platform_config_field` 写;中间层非 dict 时被静默替换 |
| `terminal`(整段) | 见下 | `hermes_cli/config.py:3251`、`3258` | 桥的数据源;raw 侧判"显式",merged 侧取值 |
| `terminal.backend` | `"local"` | `hermes_cli/config.py:3268`(遍历) | → `TERMINAL_ENV` |
| `terminal.modal_mode` | `"auto"` | 同上 | → `TERMINAL_MODAL_MODE` |
| `terminal.cwd` | `"."` | `hermes_cli/config.py:3272-3277` | → `TERMINAL_CWD`;`.`/`auto`/`cwd` 不桥;做 expanduser;set/unset 时**不**同步 .env |
| `terminal.timeout` | 180 | 同上 | → `TERMINAL_TIMEOUT`(`show_config` 里的展示默认是 60,见 D3) |
| `terminal.lifetime_seconds` | **无默认** | 同上 | → `TERMINAL_LIFETIME_SECONDS`;DEFAULT_CONFIG 里不存在 |
| `terminal.docker_image` | `nikolaik/python-nodejs:python3.11-nodejs20` | 同上 | → `TERMINAL_DOCKER_IMAGE` |
| `terminal.docker_forward_env` | `[]` | 同上 | → `TERMINAL_DOCKER_FORWARD_ENV`(list → JSON) |
| `terminal.singularity_image` | `docker://nikolaik/...` | 同上 | → `TERMINAL_SINGULARITY_IMAGE` |
| `terminal.modal_image` | `nikolaik/...` | 同上 | → `TERMINAL_MODAL_IMAGE` |
| `terminal.daytona_image` | `nikolaik/...` | 同上 | → `TERMINAL_DAYTONA_IMAGE` |
| `terminal.vercel_runtime` | `"node24"` | 同上 | → `TERMINAL_VERCEL_RUNTIME` |
| `terminal.ssh_host` / `ssh_user` / `ssh_port` / `ssh_key` | **无默认** | 同上 | → `TERMINAL_SSH_HOST` / `_USER` / `_PORT` / `_KEY` |
| `terminal.container_cpu` | 1 | 同上 | → `TERMINAL_CONTAINER_CPU` |
| `terminal.container_memory` | 5120 | 同上 | → `TERMINAL_CONTAINER_MEMORY`(MB) |
| `terminal.container_disk` | 51200 | 同上 | → `TERMINAL_CONTAINER_DISK`(MB) |
| `terminal.container_persistent` | True | 同上 | → `TERMINAL_CONTAINER_PERSISTENT` |
| `terminal.docker_volumes` | `[]` | 同上 | → `TERMINAL_DOCKER_VOLUMES`(JSON) |
| `terminal.docker_env` | `{}` | 同上 | → `TERMINAL_DOCKER_ENV`(JSON) |
| `terminal.docker_mount_cwd_to_workspace` | False | 同上 | → `TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE` |
| `terminal.docker_network` | True | 同上 | → `TERMINAL_DOCKER_NETWORK` |
| `terminal.docker_extra_args` | `[]` | 同上 | → `TERMINAL_DOCKER_EXTRA_ARGS`(JSON) |
| `terminal.docker_shm_size` | `"1g"` | 同上 | → `TERMINAL_DOCKER_SHM_SIZE` |
| `terminal.docker_run_as_host_user` | False | 同上 | → `TERMINAL_DOCKER_RUN_AS_HOST_USER` |
| `terminal.docker_persist_across_processes` | **无默认** | 同上 | → `TERMINAL_DOCKER_PERSIST_ACROSS_PROCESSES` |
| `terminal.docker_orphan_reaper` | **无默认** | 同上 | → `TERMINAL_DOCKER_ORPHAN_REAPER` |
| `terminal.sandbox_dir` | **无默认** | 同上 | → `TERMINAL_SANDBOX_DIR` |
| `terminal.persistent_shell` | True | 同上 | → `TERMINAL_PERSISTENT_SHELL` |
| `display.personality` / `show_reasoning` / `bell_on_complete` / `user_message_preview.first_lines` / `.last_lines` | `""` / True / False / 2 / 2 | `hermes_cli/config.py:4337-4342`(下一段) | 本段只在 `show_config` 边界处出现,展示默认与 schema 默认一致 |

### 15.2 环境变量

| 变量 | 读/写点 | 语义 |
|---|---|---|
| `HERMES_HOME` | `hermes_constants.py:71`(经 `get_config_path` / `get_env_path`) | 决定 config.yaml 与 .env 的位置;**在 `save_env_value` 的 denylist 上,不可通过 env 写入器写入** |
| `HERMES_PROFILE` / `HERMES_CONFIG` / `HERMES_ENV` | denylist:`hermes_cli/config.py:215` | 同上,只能改 config.yaml |
| `HERMES_MANAGED_DIR` | `hermes_cli/managed_scope.py:66` | managed scope 目录覆盖;需目录存在;绝不持久化到任何 .env |
| `HERMES_MANAGED` | `hermes_cli/config.py:357` | 粗粒度包管理器写锁;真值使 `save_config` / `save_env_value` / `remove_env_value` 直接 return |
| `HERMES_MAX_ITERATIONS` | 写:`gateway/run.py:1888`;读:`cli.py:4449`;告警:`hermes_cli/config.py:4323` | `agent.max_turns` 的跨进程载体;config 权威,.env 里的陈旧值会被 `show_config` 标黄 |
| `TERMINAL_ENV` 等 30 个 `TERMINAL_*` | `hermes_cli/config.py:3183-3214`(映射表)、`3279`(写) | 见 §15.1 右列;`terminal.backend` 对应的是 `TERMINAL_ENV` 而非 `TERMINAL_BACKEND` |
| `TIRITH_ENABLED` / `TIRITH_BIN` / `TIRITH_TIMEOUT` / `TIRITH_FAIL_OPEN` | 文档:`hermes_cli/config.py:3438`;实读:`tools/tirith_security.py:83-86` | env 压 config 压默认 |
| `ANTHROPIC_TOKEN` / `ANTHROPIC_API_KEY` | `hermes_cli/config.py:4054-4055`、`4061-4062`、`4068-4069` | 互斥双槽;清空 = 写空串(不是删键) |
| `OPENROUTER_API_KEY` / `ZAI_API_KEY` / `KIMI_API_KEY` / `KIMI_CN_API_KEY` / `MINIMAX_API_KEY` / `MINIMAX_CN_API_KEY` | `hermes_cli/config.py:3455-3462`(注释模板) | fallback provider 的 key 变量名(逐个 grep 确认代码中真实存在) |
| `HERMES_CUSTOM_<SLUG>_API_KEY` | `hermes_cli/config.py:3975` | 自定义 endpoint 的凭据槽;slug 由 endpoint identity 生成 |
| `HERMES_CUSTOM_API_KEY` | `hermes_cli/config.py:3975` | slug 为空时的兜底槽 |
| `VOICE_TOOLS_OPENAI_KEY` / `EXA_API_KEY` / `PARALLEL_API_KEY` / `FIRECRAWL_API_KEY` / `TAVILY_API_KEY` / `BROWSERBASE_API_KEY` / `BROWSER_USE_API_KEY` / `FAL_KEY` | `hermes_cli/config.py:4295-4303`(`show_config` 名单,段边界外) | `hermes config` 展示的固定 API key 清单 |
| `_ENV_VAR_NAME_DENYLIST` 全体(`LD_PRELOAD`、`LD_LIBRARY_PATH`、`LD_AUDIT`、`LD_DEBUG`、`DYLD_*`×5、`PYTHONPATH`、`PYTHONHOME`、`PYTHONSTARTUP`、`PYTHONUSERBASE`、`PYTHONEXECUTABLE`、`PYTHONNOUSERSITE`、`NODE_OPTIONS`、`NODE_PATH`、`PATH`、`SHELL`、`BROWSER`、`EDITOR`、`VISUAL`、`PAGER`、`GIT_SSH_COMMAND`、`GIT_EXEC_PATH`、`GIT_SHELL`、`HERMES_HOME`、`HERMES_PROFILE`、`HERMES_CONFIG`、`HERMES_ENV`) | `hermes_cli/config.py:198-216`;强制点 `hermes_cli/config.py:225` | **仅写入侧**拒绝;已存在的值照常生效并会被 `reload_env` 推进环境(F2) |
| `_EXTRA_ENV_KEYS` 全体(约 90 个:各 IM 平台凭据、`OPENAI_API_KEY`/`OPENAI_BASE_URL`、`TERMINAL_ENV`/`TERMINAL_SSH_KEY`/`TERMINAL_SSH_PORT`、`HERMES_TOOL_PROGRESS_MODE`、Langfuse 六项、ACP 五项) | `hermes_cli/config.py:263-327`;使用点 `hermes_cli/config.py:4095` | `reload_env` 的"可删除"白名单;不在此集合也不在 `OPTIONAL_ENV_VARS` 的键,从 .env 删掉后**不会**从 `os.environ` 移除 |
| `OPTIONAL_ENV_VARS`(动态,运行时由 provider profile 与平台插件 manifest 注入) | `hermes_cli/config.py:4095` | 同上 |
| `PYTEST_CURRENT_TEST` | `hermes_cli/managed_scope.py:49` | 存在时忽略 `/etc/hermes` 默认目录,防止开发机的真实 managed scope 泄进测试 |

---

## 16. 重实现要点

如果要从零重写这一段,以下八条是必须知道的:

1. **优先级要一句话说得清,并且写在代码注释里,而不是散在各处。**
   本段的四层(managed > 用户文件 > 默认;`${}` 只是插值)之所以能站住,是因为
   `_load_config_impl` 把四步写成了连续的四行,顺序即语义。任何"某处再补一次覆盖"的实现
   都会在半年后无人能讲清。特别注意 **managed 必须在用户展开之后合并**,否则用户能用
   `${VAR}` 劫持管理员值。

2. **"读"要分成五个入口,并且用 lint 守住。**
   合并读(`load_config`)/ 合并读免拷贝(`load_config_readonly`)/ 原始读带缓存
   (`read_raw_config`)/ 原始读免拷贝(`read_raw_config_readonly`)/ 原始读无缓存无吞异常
   (`read_user_config_raw`)。三类合法用途(写回往返、原始诊断、存在性敏感的 env 桥)
   必须写进 docstring 并配一个禁止裸 `yaml.safe_load` 的 lint 测试,否则每加一个配置特性
   就要做一次 N 处清扫。

3. **写回必须"只写用户显式设过的东西"。**
   关键是**在任何归一化之前**从原始文件算出显式叶子集合,拿它当 `_strip_default_values`
   的 preserve 集。做不到这一点,schema 默认值会被钉进用户文件,以后改默认值对老用户永远失效。

4. **展开后的值绝不能原样写回。**
   必须有 `_preserve_env_ref_templates` 这类"值没实质变化就还原模板"的机制,并且它需要
   三个判据(等于模板、等于上次 load 的展开值、等于当前环境下的展开值)才能扛住
   load 与 save 之间的密钥轮换。列表要按 name 配对而非位置。

5. **缓存签名必须覆盖"所有能改变结果的输入"。**
   本段的教训是 mtime 不够:managed 文件也要折进签名,被引用的环境变量的**当时取值**
   也要存快照并在命中时复核(否则一个跑在 `.env` 装载之前的 `load_config()` 会把未展开的
   字面量钉死整个进程生命周期)。无引用时快照为空,`all([])` 恒真,零成本退化。

6. **配置文件解析失败不许静默降级到默认值。**
   进程内保留 last-known-good 并继续服务,同时把坏文件按签名缓存起来避免反复解析,
   并且**首次告警时给坏文件拍一份 .bak**。注意这个方案只在进程内有效,新进程仍会退化——
   如果配置里有安全关键规则(deny 列表),这个残留缺口要显式设计,不能装作不存在。

7. **凭据有两条相反的解析链,必须显式选择,不能"随手写一个"。**
   默认链(environ 优先)服务于部署注入(systemd `Environment=`、`op run` 包装);
   `.env` 优先链服务于"用户手工轮换密钥必须立刻生效"。**两条链对空串的处理不同**
   (`is not None` vs 真值判断),而"清空槽位"的实现又是写空串——这三者必须一起设计。
   同时所有 environ 读都要过 secret scope,多路复用下 fail closed。

8. **`.env` 的写入器要防提权,而且要意识到防线只在写入侧。**
   变量名正则(不许数字开头)+ 逐名 denylist(不要用 `HERMES_*` 前缀通配,会误伤集成凭据)
   + 剥换行 + 剥非 ASCII + 原子写 + **保留原文件 mode**(不要无脑 0600,会打断 Docker
   volume 挂载)。同时记住:`reload_env` 会把文件里已有的任意变量推进 `os.environ`,
   denylist 拦不住它——要么给 reload 也加过滤,要么把这个取舍明确写下来。
