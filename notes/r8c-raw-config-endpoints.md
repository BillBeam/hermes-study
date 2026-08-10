# r8c · config schema 自动生成 与 config 读写端点(含 Raw YAML)

> 底稿。求全求证,不求好读。溯源约定:每条断言前一行给 `路径:行号 @ 863e313`,
> 紧跟基线逐字原文块。非源码块用 ```text / ```console / ```verify 声明。
> 取证范围:`hermes_cli/web_server.py` 的 821–1740(schema 生成)、6124–6144 与
> 6834–6929(config 读写)、13972–14006(Raw YAML),外加为定案 H-10 / H-11 所必需的
> `hermes_cli/config.py`、`hermes_cli/credential_lifecycle.py`、`gateway/pairing.py`、
> `gateway/run.py`。

---

## 0. 两条移交项的结论(先给结论)

| 移交项 | 结论 | 记号 | 是否运行时复现 |
|---|---|---|---|
| **H-10** | **能走到。** `PUT /api/config` 全程无任何 env 键过滤,API-key 形状的根键原样落进 `config.yaml`,`.env` 不被创建,凭据轮换/移除机制永远看不到它。更进一步:它还**绕开了 `.env` 写入器的 `_ENV_VAR_NAME_DENYLIST`**(`LD_PRELOAD`/`PYTHONPATH` 等),而 `gateway/run.py` 会把 config.yaml 的顶层标量桥接进 `os.environ`。 | ■ | **是**(TestClient,4 组) |
| **H-11** | **不是两套,是并存 8 套。** `_profile_scope` / `_config_profile_scope` 只是其中两套;另有 cron 双重覆写、`_cron_profile_home` 显式 `home=`、裸 `set_hermes_home_override` try/finally、`PairingStore(profile=)`、`_resolve_profile_dir()` 拼路径、OAuth 会话内存档、secret-scope contextvar、`-p <name>` 子进程 argv,合计 8 套。多数是**有意的**(各自解决一个 seam),但边界不一致处已取证 3 处。 | ◇ + ▲ | **是**(PairingStore 双 home 对照) |

**H-11 附带确认(第 3 问)**:**「不填 profile」与「填 `default`」确实指向不同的库** ——
仅当 dashboard 进程自身跑在具名 profile 的 HERMES_HOME 下时。已运行时复现,详见 §5.4。

---

## 1. 取证环境(报数用)

```console
$ git -C /home/user/hermes-agent rev-parse HEAD
863e31318553cda8ad61df681d08175364d4164b
$ git -C /home/user/hermes-agent status --porcelain
(空)
$ /home/user/hermes-venv/bin/pip list | tail -n +3 | wc -l
87
```

运行时复现全部在 `/tmp` 下的一次性 `HERMES_HOME` 中进行,脚本写在
`/tmp/claude-0/.../scratchpad/`,**基线仓库只被 import,未写入任何文件**。
所有 TestClient 调用都带 `X-Hermes-Session-Token`(见 §3.5 的鉴权边界说明)。

---

## 2. config schema 是怎么“从 DEFAULT_CONFIG 自动生成”的

### 2.1 一句话机制

模块导入时**递归遍历 `DEFAULT_CONFIG`**,把嵌套 dict 压平成 `a.b.c` 点路径 → 字段描述的
平表;每个叶子的 UI 类型由**值的 Python 类型**反推,再叠加一张手写覆盖表。

`hermes_cli/web_server.py:1117 @ 863e313`

```python
CONFIG_SCHEMA = _build_schema_from_config(DEFAULT_CONFIG)
```

### 2.2 递归与压平

`hermes_cli/web_server.py:1099 @ 863e313`

```python
        if isinstance(value, dict):
            # Recurse into nested dicts
            schema.update(_build_schema_from_config(value, full_key))
        else:
            entry: Dict[str, Any] = {
                "type": _infer_type(value),
                "description": full_key.replace(".", " → ").replace("_", " ").title(),
                "category": category,
            }
            # Apply manual overrides
            if full_key in _SCHEMA_OVERRIDES:
                entry.update(_SCHEMA_OVERRIDES[full_key])
            # Merge small categories
            entry["category"] = _CATEGORY_MERGE.get(entry["category"], entry["category"])
            schema[full_key] = entry
    return schema
```

三个要点:

1. **描述文案是机器生成的**:`full_key.replace(".", " → ").replace("_", " ").title()`。
   所以 `agent.max_turns` 的默认描述就是字符串 `"Agent → Max Turns"` —— 不是人写的解释,
   只是把键名美化。只有落在 `_SCHEMA_OVERRIDES` 里的 29 个键有真人写的说明。
2. **分类(UI 页签)取第一段路径**,顶层标量归 `general`,再过一遍 `_CATEGORY_MERGE`
   把小类并进大类。
3. **递归进 dict 意味着 dict 本身不产生字段。** 于是 `DEFAULT_CONFIG` 里的**空 dict**
   `{}` 递归后一个字段都不产生(见 §2.5)。

### 2.3 `_infer_type` —— 类型怎么推断

`hermes_cli/web_server.py:1062 @ 863e313`

```python
def _infer_type(value: Any) -> str:
    """Infer a UI field type from a Python value."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "number"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return "string"
```

三条值得记的性质:

- **`bool` 必须在 `int` 之前判**:Python 里 `bool` 是 `int` 的子类,顺序反了所有开关都会
  变成数字输入框。这行顺序是承重的。
- **`None` 落到最后一档 → `"string"`。** 实测 `DEFAULT_CONFIG` 里有 11 个 `None` 叶子
  (`database.wal_autocheckpoint`、`compression.threshold_tokens`、`max_concurrent_sessions`…),
  它们在 GUI 里全部渲染成**文本框**,而语义上多半是“数字或不设”。
- **`"object"` 这一支在 schema 生成里是死代码**:`_build_schema_from_config` 遇到 dict
  会走递归分支,永远不会调用 `_infer_type` 求出 `"object"`。实测 680 个字段里
  `type == "object"` 的数量是 0。

### 2.4 实测规模

**R11C 片 C 改:原块是「命令 + 它的输出」混排在一个 ```verify 围栏里,而且命令本身是省略的
(`python -c "from hermes_cli.web_server import CONFIG_SCHEMA; ..."` —— 那个 `...` 才是真正干活的部分)。
重跑它只会得到 `bash: line 13: 只在: command not found`:输出行被当成命令执行了。
下面把它拆成「可重跑命令 + 逐字输出」两块,命令是照原块每一行数字重建的,
重建后**每个数都与原块一致**(见下),原块的旁注移到块后正文。**未改任何结论。**

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_HOME=$(mktemp -d) \
  /home/user/hermes-venv/bin/python - <<'PY'
import collections
from hermes_cli.web_server import CONFIG_SCHEMA, _SCHEMA_OVERRIDES, _CATEGORY_MERGE, _CATEGORY_ORDER
from hermes_cli.config import DEFAULT_CONFIG
def leaves(d, prefix=""):
    for k, v in d.items():
        name = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            yield from leaves(v, name)   # 空 dict 递归后产出 0 个叶子,与 schema 生成同规则
        else:
            yield name
lv, sc = set(leaves(DEFAULT_CONFIG)), set(CONFIG_SCHEMA)
h = collections.Counter(f["type"] for f in CONFIG_SCHEMA.values())
print("CONFIG_SCHEMA fields   =", len(CONFIG_SCHEMA))
print("DEFAULT_CONFIG leaves  =", len(lv))
print("_SCHEMA_OVERRIDES      =", len(_SCHEMA_OVERRIDES))
print("_CATEGORY_MERGE        =", len(_CATEGORY_MERGE))
print("_CATEGORY_ORDER        =", len(_CATEGORY_ORDER))
print("type histogram         =", " / ".join(f"{k} {v}" for k, v in h.most_common()))
print("distinct categories    =", len({f["category"] for f in CONFIG_SCHEMA.values()}))
print("timezone options       =", len(CONFIG_SCHEMA["timezone"].get("options", [])))
print("leaves-only            =", sorted(lv - sc))
print("schema-only            =", sorted(sc - lv))
PY
```

```text
CONFIG_SCHEMA fields   = 680
DEFAULT_CONFIG leaves  = 680
_SCHEMA_OVERRIDES      = 29
_CATEGORY_MERGE        = 18
_CATEGORY_ORDER        = 15
type histogram         = string 261 / number 202 / boolean 169 / list 25 / select 23
distinct categories    = 40
timezone options       = 498
leaves-only            = ['_config_version']
schema-only            = ['model_context_length']
```

原块的旁注(现为正文):`CONFIG_SCHEMA fields` 与 `DEFAULT_CONFIG leaves` **完全对齐**(680 = 680);
`distinct categories = 40` 但 `_CATEGORY_ORDER` 只排了 15 个,**其余按字母序排在后面**;
`leaves-only = ['_config_version']` 是被显式跳过的;`schema-only = ['model_context_length']`
是虚拟字段(见 §2.6)。`memory.provider` 的 options 原块也列了,重建命令未打印它,
这里照抄原块:`['', 'byterover', 'hindsight', 'holographic', 'honcho', 'mem0', 'openviking',
'retaindb', 'supermemory']`(9 项,与 §2.3 select 类型的叙述一致)。

### 2.5 ◇ 39 个空 dict 段**在 GUI 里彻底不存在**

`DEFAULT_CONFIG` 里值为 `{}` 的段递归后产出 0 个字段,GUI 表单因此完全看不到它们。
实测清单(39 个):

```text
providers, credential_pool_strategies, agent.reasoning_overrides, terminal.docker_env,
compression.model_thresholds, auxiliary.<18 个 task>.extra_body, display.status_phrases,
honcho, slack.channel_prompts, discord.channel_prompts, whatsapp,
telegram.channel_prompts, mattermost.channel_prompts, quick_commands, platform_hints,
hooks, personalities, model_catalog.providers, monitoring.export.otlp.headers_env,
onboarding.seen, lsp.servers, secrets.onepassword.env
```

这正是 `PUT /api/config` 必须 deep-merge 而不能全量替换的根因(§3.2)。

### 2.6 虚拟字段 `model_context_length`

`DEFAULT_CONFIG` 里没有这个键,它是 normalize/denormalize 循环凭空造出来给前端的:
`model` 在磁盘上可能是字符串也可能是 dict,GUI 只认字符串,于是把 dict 里的
`context_length` 提出来做成一个平级字段。

`hermes_cli/web_server.py:4850 @ 863e313`

```python
def _normalize_config_for_web(config: Dict[str, Any]) -> Dict[str, Any]:
```

注入位置被刻意排在 `model` 之后,好让前端渲染时两者相邻。

`hermes_cli/web_server.py:1119-1128 @ 863e313`

```python
# Inject virtual fields that don't live in DEFAULT_CONFIG but are surfaced
# by the normalize/denormalize cycle.  Insert model_context_length right after
# the "model" key so it renders adjacent in the frontend.
_mcl_entry = _SCHEMA_OVERRIDES["model_context_length"]
_ordered_schema: Dict[str, Dict[str, Any]] = {}
for _k, _v in CONFIG_SCHEMA.items():
    _ordered_schema[_k] = _v
    if _k == "model":
        _ordered_schema["model_context_length"] = _mcl_entry
CONFIG_SCHEMA = _ordered_schema
```

### 2.7 动态选项:哪些字段的 options 是运行期算的

静态 `_SCHEMA_OVERRIDES` 在**导入时**冻结选项列表,所以服务器启动后才装的 provider
永远不会出现。`GET /api/config/schema` 因此走一层**每请求重算**的覆盖层。

`hermes_cli/web_server.py:6137 @ 863e313`

```python
@app.get("/api/config/schema")
async def get_schema(profile: Optional[str] = None):
    # Discovery-driven provider options (voice command providers + memory
    # provider plugins) are merged per-request so providers added after server
    # start still show up, scoped to the requested profile's config.
    with _config_profile_scope(profile):
        fields = _schema_with_dynamic_provider_options()
    return {"fields": fields, "category_order": _CATEGORY_ORDER}
```

三类动态选项,来源各不相同:

**(a) `timezone` —— 来自 stdlib `zoneinfo`,导入时算一次**

`hermes_cli/web_server.py:845 @ 863e313`

```python
def _timezone_options() -> List[str]:
    """Return sorted IANA timezone identifiers, cached at import time."""
    try:
        import zoneinfo
        return sorted(zoneinfo.available_timezones()) or ["UTC"]
    except Exception:  # pragma: no cover
        return ["UTC"]
```

实测 498 项;失败降级为 `["UTC"]`,**不是删掉字段**。注意它**不在**每请求重算的覆盖层里,
所以时区列表是进程生命周期内固定的(这没问题,zoneinfo 不会中途变)。

**(b) `memory.provider` —— 目录扫描,不 import provider**

`hermes_cli/web_server.py:824 @ 863e313`

```python
def _memory_provider_options() -> List[str]:
    """Discovered memory providers for the ``memory.provider`` select.

    Directory-scan only (no provider imports), so it's safe at module import
```

每请求版本额外做一件事:**保住当前配置里那个值**,哪怕它已经从磁盘上消失。

`hermes_cli/web_server.py:1250 @ 863e313`

```python
def _memory_provider_schema_options(cfg: Dict[str, Any]) -> List[str]:
    """Discovered memory providers for a per-request schema merge.

```

**(c) `tts.provider` / `stt.provider` —— 三个来源合流,且不硬编码厂商名**

`hermes_cli/web_server.py:1153 @ 863e313`

```python
def _custom_provider_options(
    kind: str,
    builtin_names: List[str],
    cfg: Dict[str, Any],
) -> List[str]:
```

三个来源(见 1158–1187 的 docstring 与 1209–1245 的实现):
1. config.yaml 里 `<kind>.providers.<name>`(规范位置)+ `<kind>.<name>`(legacy 回退)
   声明的 **command 型 provider**,与运行时 `_get_named_provider_config` 的解析顺序一致;
   与运行时内建名**大小写不敏感地**排重。
2. 插件在 `agent.tts_registry` / `agent.transcription_registry` 注册的名字 —— 标注为
   “机会性的”:本进程未必调用过 `discover_plugins()`,注册表**合法地可能为空**。
3. **当前值保底**:`_add(cfg_get(cfg, kind, "provider"))`。

**覆盖层的写法值得记**:只有算出来的列表**和原列表不同**才进 overlay,且模块级
`CONFIG_SCHEMA` 永不被就地修改。

`hermes_cli/web_server.py:1293 @ 863e313`

```python
    def merge(key: str, options: List[str]) -> None:
        entry = CONFIG_SCHEMA.get(key)

        if isinstance(entry, dict) and isinstance(entry.get("options"), list) and options != entry["options"]:
            overlay[key] = {**entry, "options": options}
```

而且整个重算是 **fail-open** 的:配置读不出来就直接退回静态 schema,不让 schema 端点挂掉。

`hermes_cli/web_server.py:1286 @ 863e313`

```python
    try:
        cfg = load_config()
    except Exception:  # pragma: no cover - schema must survive config errors
        return CONFIG_SCHEMA
```

---

## 3. config 读写端点

### 3.1 读:`GET /api/config`

`hermes_cli/web_server.py:6124 @ 863e313`

```python
@app.get("/api/config")
async def get_config(profile: Optional[str] = None):
    with _profile_scope(profile):
        config = _normalize_config_for_web(load_config())
    # Strip internal keys that the frontend shouldn't see or send back
    return {k: v for k, v in config.items() if not k.startswith("_")}
```

唯一的过滤是**下划线前缀**。注意这里读的是 `load_config()`(合并了 DEFAULT_CONFIG),
而写的时候读的是 `read_raw_config()`(不合并)—— 两侧不对称是刻意的,否则每次保存
都会把全部默认值写死进用户文件。

### 3.2 写:`PUT /api/config` 的三行

`hermes_cli/web_server.py:6911 @ 863e313`

```python
@app.put("/api/config")
async def update_config(body: ConfigUpdate, profile: Optional[str] = None):
    try:
        with _profile_scope(body.profile or profile):
            # The dashboard form is schema-driven (see CONFIG_SCHEMA). Any root
            # key absent from the schema — most visibly ``custom_providers``, but
            # also ``agent.personalities``, ``terminal.lifetime_seconds``, etc. —
            # is not sent in the PUT body. A full-replace save would silently
            # drop those keys. Deep-merge incoming over what's on disk so the
            # frontend can only overwrite what it explicitly sends.
            existing = read_raw_config()
            incoming = _denormalize_config_from_web(body.config)
            save_config(_deep_merge(existing, incoming))
        return {"ok": True}
```

### 3.3 ▲ 上面这段注释举的两个例子有一个路径不对

注释说 “schema 之外的根键……还有 `agent.personalities`、`terminal.lifetime_seconds`”。
实测:

**R11C 片 C 改:原块是纯输出、没有命令,却写在 ```verify 围栏里**
(重跑得到 `bash: line 4: lifetime_seconds: command not found`)。补上产生它的命令并配对:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_HOME=$(mktemp -d) \
  /home/user/hermes-venv/bin/python - <<'PY'
from hermes_cli.config import DEFAULT_CONFIG
print("'custom_providers' in DEFAULT_CONFIG             =", 'custom_providers' in DEFAULT_CONFIG)
print("'personalities' in DEFAULT_CONFIG                =", 'personalities' in DEFAULT_CONFIG)
print("'personalities' in DEFAULT_CONFIG['agent']       =", 'personalities' in DEFAULT_CONFIG['agent'])
print("'lifetime_seconds' in DEFAULT_CONFIG['terminal'] =", 'lifetime_seconds' in DEFAULT_CONFIG['terminal'])
PY
```

```text
'custom_providers' in DEFAULT_CONFIG             = False
'personalities' in DEFAULT_CONFIG                = True
'personalities' in DEFAULT_CONFIG['agent']       = False
'lifetime_seconds' in DEFAULT_CONFIG['terminal'] = False
```

即:`custom_providers` 的例子成立;`personalities` 确实存在,但它在**顶层**、不是 `agent` 下;
`terminal.lifetime_seconds` 不存在。**四个真值与原块逐个一致,结论未变。**

`agent.personalities` 确实是运行时真键:

`gateway/slash_commands.py:2502 @ 863e313`

```python
            personalities = cfg_get(config, "agent", "personalities", default={})
```

`terminal.lifetime_seconds` 也是真键(桥接成 `TERMINAL_LIFETIME_SECONDS`,
见 `hermes_cli/config.py:3188` 的映射表)—— 但两者都**不在 `DEFAULT_CONFIG` 的对应路径下**,
而 `DEFAULT_CONFIG` 顶层另有一个从没人读的 `personalities: {}`。
注释想说的道理成立(schema 外的键必须活下来),举的路径不准。
这是**源码注释**与代码的出入,不是 README/website 文档,记 ▲ 但注明层级。

### 3.4 `_denormalize_config_from_web` 到底做了什么(H-10 的关键)

`hermes_cli/web_server.py:6846 @ 863e313`

```python
    config = dict(config)
    # Remove any _model_meta that might have leaked in (shouldn't happen
    # with the stripped GET response, but be defensive)
    config.pop("_model_meta", None)
```

读完 6834–6908 全段,它**只做三件事**:
1. `pop("_model_meta")`;
2. `pop("model_context_length")` 并转成 int;
3. 当 `model` 是非空字符串时,读磁盘 config 把 model 的子键(provider/base_url/api_mode…)
   补回来,必要时重新推断 provider。

**没有任何一处按键名做过滤、白名单、schema 校验。** 它对不认识的键**完全透明**。

Pydantic 那一层也不校验:

`hermes_cli/web_models.py:18 @ 863e313`

```python
class ConfigUpdate(BaseModel):
    config: dict
    profile: Optional[str] = None
```

`config: dict` —— 无 schema、无键约束。

### 3.5 鉴权边界(判定严重性时必须交代)

`/api/config` 不在公开路径表里,受全局中间件保护:环回绑定用一次性
`_SESSION_TOKEN`(注入进 SPA HTML),网关模式(`auth_required`)用 OAuth 会话 cookie。

`hermes_cli/web_server.py:665 @ 863e313`

```python
    if path.startswith("/api/") and path not in _PUBLIC_API_PATHS and not is_mcp_oauth_callback:
```

所以 H-10 **不是未认证可达**。它的意义在于:代码自己声明的不变式是
“**dashboard 的可写面不能借此提权**”——

`hermes_cli/config.py:194 @ 863e313`

```python
# This is enforced on *write* only — values already in ``.env`` (set
# by the operator out-of-band, or pre-existing) keep working. The
# point is that the dashboard's writable surface cannot escalate by
# planting them.
```

同一个可写面上的另一个端点把这条不变式绕过去了,这才是缺陷。

---

## 4. 移交项 H-10 —— 定案 ■

### 4.1 CLI 侧的对照:`_is_env_config_key` 干什么

`hermes_cli/config.py:1152 @ 863e313`

```python
def _is_env_config_key(key: str) -> bool:
    """Return whether `hermes config set` routes this key to .env."""
    if "." in key:
        return False
    key_upper = key.upper()
```

判定规则(1157–1172):单段键(不含 `.`),大写后落在 24 个硬编码名单里,
**或**以 `_API_KEY` / `_TOKEN` / `_SECRET` 结尾,**或**以 `TERMINAL_SSH` 开头。

命中后 CLI 改道:

`hermes_cli/config.py:4856 @ 863e313`

```python
    # Check if it's an API key (goes to .env)
    if _is_env_config_key(key):
        # Unified lifecycle: also rotates any config.yaml mirror of the old
        # value so a stale higher-precedence copy can't win (#62269).
        from hermes_cli.credential_lifecycle import save_provider_env_credential

        save_provider_env_credential(key.upper(), value)
        print(f"✓ Set {key} in {get_env_path()}")
        return
```

### 4.2 搜索面(证明 GUI 这条路上没有等价守卫)

在下列范围内检索 `_is_env_config_key`、`_ENV_VAR_NAME_DENYLIST`、`_reject_denylisted_env_var`、
`save_provider_env_credential`、`redact_key`、任何按键名过滤 body 的分支:

```text
搜索面                                     结果
hermes_cli/web_server.py 全文(17,732 行)  _is_env_config_key: 0 次
                                           _reject_denylisted_env_var: 0 次
                                           save_provider_env_credential: 只在 PUT /api/env(:7111)
hermes_cli/web_models.py  ConfigUpdate      config: dict,无 validator / 无 Field 约束
web_server.py:6834-6908 _denormalize_...    只 pop 2 个键 + 重建 model,无键名过滤
hermes_cli/config.py:2435 _deep_merge       纯递归合并,不看键名
hermes_cli/config.py:3505 save_config       只剥 managed 键 + DEFAULT_CONFIG 同值键
hermes_cli/web_routers/*.py                 无 /api/config 路由(config 端点全在 web_server.py)
```

**结论:挡不住。** 从 body 到磁盘,没有任何一环看键名。

### 4.3 运行时复现(TestClient,一次性 HERMES_HOME)

```console
# [T1] H-10: API-key-shaped root key through PUT /api/config
_is_env_config_key('OPENAI_API_KEY') = True
PUT /api/config -> 200 {'ok': True}
config.yaml head: OPENAI_API_KEY: sk-h10-planted; MY_CUSTOM_TOKEN: tok-h10; timezone: UTC
.env exists      : False
config.yaml mode : 0o600
GET /api/config OPENAI_API_KEY -> 'sk-h10-planted'
```

三点实测事实:
1. `.env` **根本没被创建**,凭据只在 config.yaml 里;
2. 文件权限是 0600(`save_config` 的 `_secure_file`),所以**不是**文件权限问题;
3. `GET /api/config` **原文回显**该密钥 —— 而 `GET /api/env` 走的是脱敏:

`hermes_cli/web_server.py:7053 @ 863e313`

```python
            "redacted_value": redact_key(value) if value else None,
```

   同一个 dashboard,同一份密钥,一个端点脱敏一个端点明文。

### 4.4 ■ 完整失效链

```text
[1] body        PUT /api/config  {"config": {"OPENAI_API_KEY": "sk-..."}}
      ↓  web_models.py:18   ConfigUpdate.config: dict —— 不校验键名
[2] handler     web_server.py:6914  with _profile_scope(...)
      ↓
[3] denorm      web_server.py:6922  _denormalize_config_from_web
                  只 pop _model_meta / model_context_length,其余键**原样透传**
      ↓
[4] merge       web_server.py:6923  _deep_merge(read_raw_config(), incoming)
                  config.py:2435 纯递归,任意根键存活
      ↓
[5] save        config.py:3505 save_config
                  剥 managed 键 → 归一 model/max_turns → 保 env-ref 模板
                  → _strip_default_values(只剥与 DEFAULT_CONFIG 同值的键;
                    OPENAI_API_KEY 不在 DEFAULT_CONFIG,原封不动)
      ↓  config.py:3611 atomic_yaml_write + _secure_file
[6] 落盘        ~/.hermes/config.yaml  顶层键 OPENAI_API_KEY: sk-...   (mode 0600)
```

**后果 A —— 它是活凭据,不是一份废数据。** 网关启动时把 config.yaml 的顶层标量
桥接进 `os.environ`:

`gateway/run.py:2057 @ 863e313`

```python
        # Top-level simple values (fallback only — don't override .env)
        for _key, _val in _cfg.items():
            if isinstance(_val, (str, int, float, bool)) and _key not in os.environ:
                os.environ[_key] = str(_val)
```

`.env` 已有同名键时它只做兜底;`.env` 没有时(正是本失效链造出的状态),**它就是生效的那份**。

**后果 B —— 轮换与删除永远碰不到它。** `PUT /api/env` 的
`save_provider_env_credential` 会去清理 config.yaml 里的“镜像”,但清理面是写死的三处:

`hermes_cli/credential_lifecycle.py:157 @ 863e313`

```python
    _fix(user_config.get("model"), "model")

    aux = user_config.get("auxiliary")
    if isinstance(aux, dict):
        for task, slot_cfg in aux.items():
            _fix(slot_cfg, f"auxiliary.{task}")

    custom = user_config.get("custom_providers")
    if isinstance(custom, list):
        for idx, entry in enumerate(custom):
```

`model.api_key` / `auxiliary.<task>.api_key` / `custom_providers[*].api_key` —— **不含顶层根键**。
所以用户之后从 GUI 正规轮换 `OPENAI_API_KEY`,新值写进 `.env`,而 config.yaml 里那份旧值
既不会被改也不会被删;`remove_provider_env_credential` 同理(它调同一个函数)。
这正是 #62269 想根除的“stale higher-precedence copy”,只是从另一个端点又造了一份。

**后果 C(提权,严重性主要来自这条)—— 绕过 `.env` 写入器的黑名单。**

`hermes_cli/config.py:198 @ 863e313`

```python
_ENV_VAR_NAME_DENYLIST: frozenset[str] = frozenset({
    # Loader / linker
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "LD_DEBUG",
```

实测两个端点对同一个名字给出相反答案:

```console
# [T2] H-10 escalation: .env writer denylist vs config writer
PUT /api/env    LD_PRELOAD -> 400 Environment variable 'LD_PRELOAD' is on the writer denylist....
PUT /api/config LD_PRELOAD -> 200 {'ok': True}
config.yaml has LD_PRELOAD : True
```

而 `gateway/run.py:2058-2060` 的桥接条件是 `_key not in os.environ` —— `LD_PRELOAD`
在常规环境里**恰恰不在** `os.environ` 里,于是会被导出。把该 config.yaml 喂给
桥接循环(逐字复刻 2058–2060)得到:

```console
bridge would export -> {'LD_PRELOAD': '/tmp/evil.so', 'PYTHONPATH': '/tmp/evil'}
```

**申报:后果 C 的“桥接”一段是复刻循环、不是真跑 `gateway/run.py`。**
`gateway/run.py` 的模块级代码含 venv 探测与 re-exec,在本容器里整体导入不安全,
故只做了逐字复刻。桥接代码本身是模块级、无条件执行的(2035 行 `if _config_path.exists():`
位于 0 缩进),这一点是读码结论。

### 4.5 缺陷定性与最小修法

定性:**同一可写面上两个端点对“凭据形状的键”执行两套不同策略**,弱的那套没有守卫。
最小修法(不改架构):在 `_denormalize_config_from_web` 之后、`_deep_merge` 之前,
对 `incoming` 的**根级标量键**跑一遍 `_is_env_config_key` 与 `_reject_denylisted_env_var`,
命中则 400 并提示改用 `PUT /api/env`。这样 CLI 与 GUI 共用同一个判定函数,
不会再各自漂移。

---

## 5. 移交项 H-11 —— dashboard 里的 profile 作用域机制全清点

### 5.1 十套?八套。先给机制表

移交项说的是“两套并存”。清点结果是 **8 套**(A–J,无 K)。前两套是移交项点名的,
其余 6 套此前未被记录。

| 代号 | 机制 | 定义处 | 覆写什么 | await 安全 |
|---|---|---|---|---|
| **A** | `_profile_scope(profile)` contextmanager | `hermes_cli/web_server.py:13574` | HERMES_HOME contextvar **+ 进程全局** `skills_tool.SKILLS_DIR` / `skill_manager_tool.SKILLS_DIR`(RLock 保护) | **否**(见 5.3) |
| **B** | `_config_profile_scope(profile)` contextmanager | `hermes_cli/web_server.py:13633` | 只覆写 HERMES_HOME contextvar | 是 |
| **C** | cron 双重覆写 | `hermes_cli/web_server.py:11685` | HERMES_HOME contextvar **+** `cron_jobs.use_cron_store(home)` | 否(同步调用) |
| **D** | `_cron_profile_home(profile) -> (name, home)`,显式传 `home=` / 拼路径 | `hermes_cli/web_server.py:11647` | 什么都不覆写,把 home 当参数传下去 | 是 |
| **E** | 裸 `set_hermes_home_override` + try/finally(非 contextmanager) | `hermes_cli/web_server.py:13422`、`:13448`、`:13495`、`:11962` | HERMES_HOME contextvar | 是 |
| **F** | `PairingStore(profile=...)` 构造参数 | `hermes_cli/web_server.py:12309` | 什么都不覆写,store 自己解析 home | 是 |
| **G** | `_resolve_profile_dir(name)` 拿目录直接拼路径 | `hermes_cli/web_server.py:13393` | 什么都不覆写 | 是 |
| **H** | OAuth 会话内存档 `_new_oauth_session(..., profile=)` + `_oauth_session_profile()` | `hermes_cli/web_server.py:10145` | 记在会话 dict 里,后续步骤回查 | 是 |
| **I** | secret-scope contextvar,叠加在 E 之上 | `hermes_cli/web_server.py:12190` | `agent.secret_scope` 的 contextvar | 是 |
| **J** | `-p <name>` 子进程 argv | `hermes_cli/web_server.py:13192` | 什么都不覆写,交给子进程的 `_apply_profile_override()` | 是 |

关键定义处逐一取证:

`hermes_cli/web_server.py:13573 @ 863e313`

```python
@contextmanager
def _profile_scope(profile: Optional[str]):
    """Scope config + skill-directory resolution to ``profile`` for one request.
```

`hermes_cli/web_server.py:13632 @ 863e313`

```python
@contextmanager
def _config_profile_scope(profile: Optional[str]):
    """Await-safe, config-only profile scope for handlers that ``await``.
```

`hermes_cli/web_server.py:11685 @ 863e313`

```python
    token = set_hermes_home_override(str(home))
    try:
        with cron_jobs.use_cron_store(home):
            result = getattr(cron_jobs, func_name)(*args, **kwargs)
    finally:
        reset_hermes_home_override(token)
```

`hermes_cli/web_server.py:11225 @ 863e313`

```python
    if profile:
        _name, home = _cron_profile_home(profile)
        db_path = Path(home) / "state.db"
    else:
        db_path = Path(_default_db_path())
```

`hermes_cli/web_server.py:12189 @ 863e313`

```python
        home_token = set_hermes_home_override(flow.hermes_home)
        secret_token = set_secret_scope(build_profile_secret_scope(Path(flow.hermes_home)))
```

`hermes_cli/web_server.py:13202 @ 863e313`

```python
    if not requested or requested.lower() in {"current", "default"}:
        return []
    from hermes_cli import profiles as profiles_mod
    _resolve_profile_dir(requested)
    return ["-p", profiles_mod.normalize_profile_name(requested)]
```

`hermes_cli/web_server.py:3888 @ 863e313`

```python
def _gateway_subcommand(profile: Optional[str], verb: str) -> List[str]:
    return _profile_cli_args(profile) + ["gateway", verb]
```

### 5.2 逐端点表(119 条 profile 相关路由)

下表由静态 AST 扫描 `hermes_cli/web_server.py` + `hermes_cli/web_routers/*.py` 生成
(委派解析深度 1:端点自身无机制时,取其调用的第一个带机制的模块级 helper)。
`qb` 列:`q` = 有 `?profile=` 查询参数,`b` = 有 `body.profile`。
机制代号见上表。**`hermes_cli/web_routers/` 下 6 个 router 已全部纳入**。

```text
# profile-aware routes: 119
文件:行号               路由                                                        qb  机制   经由
------------------------------------------------------------------------------------------------
cron.py:52             GET /api/cron/jobs                                         q.  C      _list_cron_jobs_sync
cron.py:57             GET /api/cron/jobs/{job_id}                                q.  C      _get_cron_job_sync
cron.py:62             GET /api/cron/jobs/{job_id}/runs                           q.  CD     _list_cron_job_runs_sync
cron.py:67             POST /api/cron/jobs                                        q.  CD     _create_cron_job_sync
cron.py:100            PUT /api/cron/jobs/{job_id}                                q.  CD     _update_cron_job_sync
cron.py:105            POST /api/cron/jobs/{job_id}/pause                         q.  C      _pause_cron_job_sync
cron.py:110            POST /api/cron/jobs/{job_id}/resume                        q.  C      _resume_cron_job_sync
cron.py:115            POST /api/cron/jobs/{job_id}/trigger                       q.  C      _trigger_cron_job_sync
cron.py:120            DELETE /api/cron/jobs/{job_id}                             q.  C      _delete_cron_job_sync
cron.py:125            POST /api/cron/fire                                        ..  C      _fire_cron_job_for_profile
cron.py:218            POST /api/cron/blueprints/instantiate                      q.  C      _call_cron_for_profile
mcp.py:59              GET /api/mcp/servers                                       q.  A
mcp.py:72              POST /api/mcp/servers                                      qb  A
mcp.py:108             PUT /api/mcp/servers                                       qb  A
mcp.py:127             DELETE /api/mcp/servers/{name}                             q.  A
mcp.py:138             POST /api/mcp/servers/{name}/test                          q.  AB
mcp.py:198             POST /api/mcp/servers/{name}/auth                          q.  A
mcp.py:319             PUT /api/mcp/servers/{name}/enabled                        qb  A
mcp.py:341             GET /api/mcp/catalog                                       q.  A
mcp.py:418             POST /api/mcp/catalog/install                              qb  AJ
profiles.py:60         GET /api/profiles/sessions                                 q.  DG
profiles.py:204        GET /api/profiles/sessions/sidebar                         ..  G
profiles.py:356        POST /api/profiles                                         ..  E      _write_profile_model
profiles.py:510        GET /api/profiles/{name}/setup-command                     ..  G      _profile_setup_command
profiles.py:515        POST /api/profiles/{name}/open-terminal                    ..  G      _profile_setup_command
profiles.py:602        GET /api/profiles/{name}/soul                              ..  G
profiles.py:613        PUT /api/profiles/{name}/soul                              ..  G
profiles.py:642        PUT /api/profiles/{name}/description                       ..  G
profiles.py:665        PUT /api/profiles/{name}/model                             ..  G
profiles.py:685        POST /api/profiles/{name}/describe-auto                    ..  G
profiles.py:801        GET /api/profiles/{name}/desktop-overlay                   ..  G
sessions.py:51         GET /api/sessions                                          q.  D
sessions.py:167        GET /api/sessions/search                                   q.  D
sessions.py:393        POST /api/sessions/bulk-delete                             .b  D
sessions.py:446        POST /api/sessions/import                                  .b  D
sessions.py:472        GET /api/sessions/empty/count                              q.  D
sessions.py:490        DELETE /api/sessions/empty                                 q.  D
sessions.py:521        GET /api/sessions/stats                                    q.  D
sessions.py:553        GET /api/sessions/{session_id}                             q.  D
sessions.py:576        GET /api/sessions/{session_id}/latest-descendant           q.  D
sessions.py:599        GET /api/sessions/{session_id}/messages                    q.  D
sessions.py:634        DELETE /api/sessions/{session_id}                          q.  D
sessions.py:662        PATCH /api/sessions/{session_id}                           .b  D
sessions.py:701        GET /api/sessions/{session_id}/export                      q.  D
sessions.py:718        POST /api/sessions/prune                                   ..  D      _prune_sessions
skills.py:55           POST /api/skills/hub/install                               qb  J      _profile_cli_args
skills.py:75           POST /api/skills/hub/uninstall                             qb  J      _profile_cli_args
skills.py:94           POST /api/skills/hub/update                                qb  J      _profile_cli_args
skills.py:111          GET /api/skills/hub/sources                                q.  B
skills.py:124(+3 处)    GET/PUT /api/skills/hub/*                                  q.  B
skills.py:404          GET /api/skills                                            q.  A
skills.py:429          PUT /api/skills/{name}/enabled                             qb  A
skills.py:445          GET /api/skills/{name}/content                             q.  A
skills.py:470          POST /api/skills                                           .b  A
skills.py:483          PUT /api/skills/{name}/content                             .b  A
tools.py:67…:704       /api/tools/* 共 9 条                                        q/b A(8 条)、J(1 条 computer-use/grant)
web_server.py:2318     GET /api/status                                            q.  A
web_server.py:3026     GET /api/gateway/topology                                  q.  AB
web_server.py:3996     POST /api/gateway/restart                                  q.  J      _spawn_gateway_restart
web_server.py:4358     POST /api/audio/transcribe                                 q.  B
web_server.py:4436     GET /api/voice/stt-status                                  q.  B
web_server.py:4528     POST /api/audio/tts                                        q.  B
web_server.py:4655     GET /api/voice/tts-status                                  q.  B
web_server.py:6041     GET /api/memory/providers                                  q.  A
web_server.py:6089     PUT /api/memory/providers/{name}/config                    q.  A
web_server.py:6124     GET /api/config                                            q.  A
web_server.py:6137     GET /api/config/schema                                     q.  B
web_server.py:6174     GET /api/model/info                                        q.  A
web_server.py:6299     GET /api/model/catalog                                     q.  A
web_server.py:6410     GET /api/model/providers                                   q.  A
web_server.py:6449     GET /api/model/aux                                         q.  A
web_server.py:6483     POST /api/model/set                                        qb  A
web_server.py:6581     POST /api/model/aux/set                                    qb  A
web_server.py:6911     PUT /api/config                                            qb  A
web_server.py:7041     GET /api/env                                               q.  A
web_server.py:7103     PUT /api/env                                               qb  A
web_server.py:7570     DELETE /api/env                                            qb  A
web_server.py:7598     POST /api/env/reveal                                       qb  A
web_server.py:8791     POST /api/messaging/whatsapp/onboarding/start              .b  B
web_server.py:8863     POST .../whatsapp/onboarding/{pairing_id}/apply            qb  B
web_server.py:9219     POST .../telegram/onboarding/{pairing_id}/apply            qb  A
web_server.py:9295     GET /api/messaging/platforms                               q.  A
web_server.py:9376     PUT /api/messaging/platforms/{platform_id}                 qb  A
web_server.py:9443     POST /api/messaging/platforms/{platform_id}/test           q.  A
web_server.py:9933     GET /api/providers/oauth                                   q.  A
web_server.py:9976     DELETE /api/providers/oauth/{provider_id}                  q.  A
web_server.py:10943    POST /api/providers/oauth/{provider_id}/start              q.  H
web_server.py:10981    POST /api/providers/oauth/{provider_id}/submit             q.  H
web_server.py:10997    GET /api/providers/oauth/{pid}/poll/{session_id}           q.  ?  ← 见 5.5
web_server.py:11023    DELETE /api/providers/oauth/sessions/{session_id}          q.  ?  ← 见 5.5
web_server.py:12313    GET /api/pairing                                           q.  F
web_server.py:12322    POST /api/pairing/approve                                  .b  F
web_server.py:12358    POST /api/pairing/revoke                                   .b  F
web_server.py:12372    POST /api/pairing/clear-pending                            q.  F
web_server.py:12541    POST /api/gateway/start                                    q.  J
web_server.py:12553    POST /api/gateway/stop                                     q.  J
web_server.py:13978    GET /api/config/raw                                        q.  A
web_server.py:13994    PUT /api/config/raw                                        qb  A
web_server.py:14195    GET /api/analytics/usage                                   q.  D
web_server.py:14383    GET /api/analytics/models                                  q.  D
web_server.py:15146    (skills 相关内部路由)                                        q.  A
web_server.py:15307    WEBSOCKET /api/console                                     ..  G
web_server.py:15657    WEBSOCKET /api/pty                                         ..  G

小计(按机制):A 50 / D 16-19 / G 12 / B 9 / C 8-11 / J 8 / F 4 / E 1 / H 2 / ? 2
(A+F、A+B、C+D 等组合按主要机制归并;完整逐行输出见脚本
 scratchpad/census_profiles2.py,重跑即可复现)
```

### 5.3 A 与 B 为什么必须并存 —— 这是**有意的设计**,依据在 docstring 里

B 的 docstring 把理由写死了:A 会换**进程全局**变量,而进程全局变量跨 `await` 会被
并发任务的 `finally` 还原,造成串档。

`hermes_cli/web_server.py:13637 @ 863e313`

```python
    ``set_hermes_home_override`` contextvar — it does NOT swap the
    process-global ``skills_tool``/``skill_manager`` module attributes.
    Those globals are shared across all event-loop tasks, so holding them
    across an ``await`` lets a concurrent skills request restore THIS
    request's profile dir on its ``finally`` (cross-contamination). The
    contextvar override is task-local and survives an ``await`` cleanly,
```

而 A 之所以非要换进程全局,是因为 `tools.skills_tool` 在**导入时**就把 `SKILLS_DIR`
绑定成了模块常量,contextvar 够不着它(`hermes_cli/web_server.py:13582-13586`)。

**判定:A/B 并存是有意的,不是历史遗留。** 分界线清楚 ——
“这个 handler 会不会 `await`”:会就用 B,不会就用 A。代码里 4 处注释显式写了这条
选择理由(`:3026-3034`、`:4358-4363`、`:4528-4532`、`hermes_cli/web_routers/mcp.py:158-168`),
例如:

`hermes_cli/web_server.py:3026 @ 863e313`

```python
    # Use the config-only (contextvar) scope, NOT _profile_scope: this handler
```

C/D/E/F/G/H/I/J 同理各有其解决的 seam:C 要额外锁住 cron 存储事务;D/G 是“根本不需要
覆写、直接把路径当参数传”的最干净形态;J 是唯一能穿透**子进程**里同样在导入期绑定的
`skills_hub.SKILLS_DIR` 的办法(`hermes_cli/web_server.py:13195-13199`)。

**真正的问题不是“为什么有多套”,而是“选哪套没有单一入口”** —— 8 套的选择规则
散落在各处注释里,没有一处集中说明,新端点作者只能靠抄邻居。这是 ◇。

### 5.4 ■/◇ 第 3 问:「不填 profile」与「填 `default`」指向不同的库

锚点两处。`_pairing_store` 的 docstring 断言 `default` 会“映射回全局 store”:

`hermes_cli/web_server.py:12296 @ 863e313`

```python
    ``PairingStore`` resolves the profile's home itself (``default`` maps back
    to the global store), so this only needs to validate the name — no
    ``_profile_scope`` needed, and nothing process-global is swapped across
    the ``await`` boundary.
```

而 `PairingStore.__init__` 的两条分支解析的**不是同一个 home**:

`gateway/pairing.py:421 @ 863e313`

```python
    def __init__(self, profile: Optional[str] = None):
        # Resolve storage directory lazily — tests use a temp HERMES_HOME
        # and PairingStore may be constructed before the env is set.
        if profile:
            root = get_default_hermes_root()
            profile_home = (
                root
                if profile == "default"
                else root / "profiles" / profile
            )
            self._dir = get_hermes_dir(
                "platforms/pairing",
                "pairing",
                home=profile_home,
            )
        else:
            self._dir = PAIRING_DIR
```

`profile=None` 走 `PAIRING_DIR`,那是**模块导入时**按当时的 `get_hermes_home()` 算出来的常量:

`gateway/pairing.py:59 @ 863e313`

```python
PAIRING_DIR = get_hermes_dir("platforms/pairing", "pairing")
```

`profile="default"` 走 `get_default_hermes_root()` —— 它读的是**进程 env 的 HERMES_HOME**
并做“若在 profiles 树下则回到根”的归一(`hermes_constants.py:161-192`)。
两者只有在 dashboard 自身跑在**根 home** 时才相等。运行时对照:

```console
# [T4] H-11: PairingStore no-profile vs profile='default'
-- dashboard HOME = <root>
  PAIRING_DIR                    = /tmp/r8c-root-xxxx/platforms/pairing
  PairingStore()._dir            = /tmp/r8c-root-xxxx/platforms/pairing
  PairingStore(profile='default')= /tmp/r8c-root-xxxx/platforms/pairing
  SAME? True
-- dashboard HOME = <root>/profiles/work
  PAIRING_DIR                    = /tmp/r8c-root-xxxx/profiles/work/platforms/pairing
  PairingStore()._dir            = /tmp/r8c-root-xxxx/profiles/work/platforms/pairing
  PairingStore(profile='default')= /tmp/r8c-root-xxxx/platforms/pairing
  SAME? False
```

**定性:是 ◇ 不是 ■,但 docstring 那句话具误导性(▲ 级)。**
理由:`PairingStore` 自己的类 docstring 把语义说对了 ——

`gateway/pairing.py:414 @ 863e313`

```python
    When constructed with ``profile="<name>"``, storage resolves from that
    profile's own HERMES_HOME using the same legacy/consolidated layout rules
    as ``hermes -p <name> pairing ...``. This keeps multiplex gateways and
    profile-scoped CLI approvals on one whitelist. Without a profile, storage
    is the global pairing directory for the current HERMES_HOME.
```

“without a profile → **current** HERMES_HOME”与“`default` → **root**”本来就是两件事,
只在 current == root 时重合。所以行为是有意的;错的是 `hermes_cli/web_server.py:12296` 那句
“`default` maps back to the global store”——在 dashboard 跑在具名 profile 下时它不成立。

**运维后果(必须记)**:同一个 dashboard 里,配对页 profile 下拉框选「当前/留空」与选
「default」是**两个白名单**。管理员在跑 `work` profile 的 dashboard 上选 `default` 批准
一个 Telegram 用户,批的是根 home 的名单;而这台 dashboard 自己的网关读的是
`work` 的名单。这与移交项担心的现象一致。

**负结论(一并记下,避免下一轮重查)**:`_resolve_profile_dir` → `profiles.get_profile_dir`
与 `PairingStore` 自己的解析**并未分叉**:前者 `default` → `_get_default_hermes_home()`,
而后者也是同一个函数 ——

`hermes_cli/profiles.py:288-289 @ 863e313`

```python
    from hermes_constants import get_default_hermes_root
    return get_default_hermes_root()
```

两条路一致,这一处没有 bug。

### 5.5 ◇ 两个端点声明了 `profile` 却从不使用

`hermes_cli/web_server.py:11023 @ 863e313`

```python
async def cancel_oauth_session(
    session_id: str,
    request: Request,
    profile: Optional[str] = None,
):
```

`:10997` 的 `poll_oauth_session` 与上面这个 `cancel_oauth_session` 签名里都有
`profile: Optional[str] = None`,函数体内
**再无任何 `profile` 引用**(逐行核对 10997–11022 与 11023–11060)。
profile 是在 `_new_oauth_session(..., profile=profile)` 建会话时存进会话 dict 的,
后续步骤靠 `_oauth_session_profile(session_id)` 回查。所以查询参数是残留的。
不影响正确性(会话自带 profile),但对着 API 写客户端的人会以为它有用。

### 5.6 有没有第三套?—— 搜索面

```text
搜索面                                            命中
grep -n "_profile_scope"           web_server.py  48 处使用 + 1 处定义(:13574)
grep -n "_config_profile_scope"    web_server.py  9 处使用 + 1 处定义(:13633)
grep -n "set_hermes_home_override" web_server.py  13 处(其中 4 处是 A/B 内部,其余为 C/E/I)
grep -rn 上述 3 个名字             web_routers/   mcp.py / skills.py / tools.py / sessions.py
                                                  / profiles.py / cron.py 全部覆盖(见 5.2 表)
grep -rn "PairingStore("           全仓非测试     8 处(gateway/run.py 2、yuanbao 1、
                                                  hermes_cli/pairing.py 1、web_server.py 2、
                                                  discord adapter 2)
grep -n "_cron_profile_home\|_open_session_db_for_profile\|_profile_cli_args\|
        _resolve_profile_dir\|_new_oauth_session\|set_secret_scope"          全部纳入上表
AST 扫描:web_server.py + web_routers/*.py 的全部路由装饰器,
          筛出带 profile 参数或带上述机制的函数                  119 条,无遗漏
```

**答:第三、四……第八套都有,已全部列出(A–J,共 8 套)。** 未发现第九套。
唯一没有被上述任何一套覆盖的 profile 相关代码是 **§5.5 那两个白声明的参数**。

---

## 6. GUI 改配置 vs CLI 改配置 —— 两条落盘路径,逐项对比

**结论先行:是两条路,不是一条。** 关键分叉点是:CLI 的 `set_config_value`
**根本不调 `save_config`**,它自己直接 `atomic_yaml_write`。

`hermes_cli/config.py:4992 @ 863e313`

```python
    # Write only user config back (not the full merged defaults)
    ensure_hermes_home()
    from utils import atomic_yaml_write
    atomic_yaml_write(config_path, user_config, sort_keys=False)
```

而 GUI 走 `save_config`,后者写完还多一步收权限:

`hermes_cli/config.py:3611 @ 863e313`

```python
        atomic_yaml_write(
            config_path,
            normalized,
            extra_content="".join(parts) if parts else None,
        )
        _secure_file(config_path)
        _RAW_CONFIG_CACHE.pop(str(config_path), None)
```

### 6.1 逐项差异表

```text
维度                         CLI: hermes config set              GUI: PUT /api/config
                             (config.py:4823 起)                  (web_server.py:6911 起)
---------------------------------------------------------------------------------------
入口守卫 is_managed()        有(:4837 直接 return)                有(在 save_config 内,:3527)
managed 单键硬拒             有(:4847 sys.exit(1),点名管理员)     无 —— save_config 只静默剥掉
                                                                  该键并打一行 stderr(:3538-3545)
API-key 形状键改道 .env      **有**(:4857 _is_env_config_key)      **无** ← 本轮 H-10
.env 写入器黑名单            间接享有(改道后由 save_env_value 拒)  **无**  ← 本轮 H-10 后果 C
未知键提示 / did-you-mean    有(:4873 _validate_config_key,
                             写完后再警告,不阻断)                  无
不可读文件保护               有(:4879)                            有(save_config :3550)
**不可解析 YAML**            **硬失败**:打印 YAML 错误 + 建议
                             `hermes config edit`,sys.exit(1)
                             (:4885-4893)                          **静默继续**(见 6.2)
类型强制                     有:按 _default_value_for_key 的类型
                             决定是否把 "true"/"3" 强转
                             (:4903-4913)                         无 —— body 是 JSON,类型由前端定
标量覆盖整个 section 的守卫  有(#74995,:4931-4981,bare model
                             重定向到 model.default,其余需 --force) 无 —— deep_merge 遇 dict vs 标量
                                                                  直接用标量覆盖(config.py:2458-2459)
list 下标路径(a.0.b)        有(_set_nested,#17876)              不适用(整棵子树 JSON 提交)
api_base → base_url 别名归一 有(:4987-4991)                       无(仅 save_config 内的
                                                                  _normalize_root_model_keys 覆盖 root 层)
剥默认值(不把 DEFAULT 写盘) **无** —— 直接写回读到的 user_config   **有**(save_config :3586-3594)
保留 ${ENV_VAR} 模板         **无**                                **有**(_preserve_env_ref_templates :3571)
写入注释块(security/fallback)**无**                               **有**(:3596-3610)
原子写                       有(atomic_yaml_write)                有(同一函数)
权限                         **保留**已有文件的 mode;
                             新文件继承 mkstemp 的 0600            **强制收紧到 0600**(_secure_file)
终端键同步到 .env            有(:4999-5001 TERMINAL_* 镜像)       无
display.skin 触发 mtime      有(:5008-5014)                       无
回显脱敏                     有(:5020-5026 对 credential 形状
                             的叶子键 mask_secret)                 不适用(不回显),但
                                                                  GET /api/config **明文回显**
cron 未固定模型告警          有(:5027)                            无
profile 作用域               靠进程 HERMES_HOME / `-p`             _profile_scope(A 套)
```

其中“回显脱敏”一项的 CLI 侧原文:

`hermes_cli/config.py:5020 @ 863e313`

```python
    _leaf_key = key.rsplit(".", 1)[-1].lower()
    if _leaf_key in _SECRET_CONFIG_KEYS and isinstance(value, str) and value:
        from agent.redact import mask_secret
        _display_value = mask_secret(value)
    else:
        _display_value = value
    print(f"✓ Set {key} = {_display_value} in {config_path}")
```

### 6.2 ◇ 配置文件语法坏掉时,两条路的行为相反

GUI 侧读盘用 `read_raw_config()`,它把**解析失败与文件不存在等同处理**,都返回 `{}`:

`hermes_cli/config.py:2958 @ 863e313`

```python
        try:
            with open(config_path, encoding="utf-8") as f:
                data = fast_safe_load(f) or {}
        except Exception as e:
            _warn_config_parse_failure(config_path, e)
            return {}
```

于是 `_deep_merge({}, incoming)` = `incoming`,`save_config` 再把它当成全量文档写下去。
实测:一个含 `custom_providers[0].api_key` 的坏 YAML,GUI 存一个无关字段后,
文件被截断成只剩该字段:

```console
--- config.yaml BEFORE (unparseable), bytes: 135
PUT /api/config -> 200 {"ok":true}
--- config.yaml AFTER, bytes: 1683
timezone: Asia/Shanghai
agent: {}
--- custom_providers still present? False
--- sibling files in HERMES_HOME: [..., 'config.yaml.corrupt.20260808-161721.bak', ...]
```

CLI 同场景下会打印 YAML 错误并 `sys.exit(1)`,一个字节都不动。

**为什么定 ◇ 而不是 ■**:`_warn_config_parse_failure` 在**首次**发现坏文件时会自动存一份
带时间戳的 `.bak`,内容可恢复:

`hermes_cli/config.py:113 @ 863e313`

```python
    mtime/size), so users editing the config see the next failure. On the
    first warning for a given broken file we also snapshot it to a
    timestamped ``.bak`` (best-effort) so the user's recoverable content
    survives any later rewrite of ``config.yaml`` by the setup wizard or
    ``hermes config set``.
```

上面的 console 输出里 `config.yaml.corrupt.20260808-161721.bak` 确实出现了,机制成立。
但备份是 **best-effort**、去重键是 `(path, mtime_ns, size)` 且缓存**是进程级**的 ——
坏文件在本进程第一次被读时才会留档。GUI 用户看到的是 200 OK,没有任何提示告诉他
“你的 custom_providers 刚被截掉了,备份在旁边那个 .bak 里”。

### 6.3 ◇ `atomic_config_write` 自称是唯一 chokepoint,但两条主路都不走它

`hermes_cli/config.py:3089 @ 863e313`

```python
def atomic_config_write(config_path: Path, data: Any, **kwargs: Any) -> None:
    """Fail-closed atomic write for ``config.yaml``.

    The single chokepoint every config-update path should use instead of
    calling :func:`utils.atomic_yaml_write` directly. It runs
```

实际调用它的是 `gateway/slash_commands.py`(7 处)、`agent/onboarding.py`、`doctor.py`、
`tui_gateway/server.py`、telegram/yuanbao adapter —— 而**流量最大的两条路
(`save_config` 与 `set_config_value`)都直接调 `atomic_yaml_write`**,各自手写
`require_readable_config_before_write`。结果等价,但“单一 chokepoint”的说法与代码不符。

---

## 7. Raw YAML 端点(`:13977` / `:13993`)

### 7.1 它是什么

`hermes_cli/web_server.py:13993 @ 863e313`

```python
@app.put("/api/config/raw")
async def update_config_raw(body: RawConfigUpdate, profile: Optional[str] = None):
    try:
        parsed = yaml.safe_load(body.yaml_text)
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="YAML must be a mapping")
        with _profile_scope(body.profile or profile):
            # Full-document replacement: the editor owns the whole file; do not
            # merge omitted sections back from disk (#62723).
            save_config(parsed, merge_existing=False)
        return {"ok": True}
```

读侧 `GET /api/config/raw`(:13977)直接 `path.read_text()` 返回**文件全文**。

### 7.2 它绕过了什么(与 `PUT /api/config` 对照)

```text
保护                                    PUT /api/config     PUT /api/config/raw
--------------------------------------------------------------------------------
CONFIG_SCHEMA / 字段类型                 前端受其约束(后端不校验) 完全无关
_normalize/_denormalize 的 model 归一    有(会重推 provider、
                                         写回 context_length)     **无**
与磁盘 deep-merge(保住 schema 外的键)   **有**(:6923)            **无 —— 全量替换**(刻意,#62723)
_is_env_config_key 改道                  无(H-10)                 无
.env 写入器黑名单                        无(H-10)                 无
save_config 的全部保护                   有                        **有**(同一函数)
  ├ managed 键剥离                       ✓                        ✓
  ├ require_readable_config_before_write ✓                        ✓
  ├ 剥 DEFAULT 同值键                    ✓                        ✓
  ├ ${ENV_VAR} 模板保留                  ✓                        ✓
  ├ 原子写 + _secure_file(0600)         ✓                        ✓
下划线内部键屏蔽                         读侧有(:6129 剥 `_*`)     **无 —— 读写都暴露 `_config_version`**
异常兜底                                 except Exception → 500
                                         (:6927-6929)             **只 catch YAMLError**
```

### 7.3 它自己的守卫(有,但只有三道)

1. **必须是 mapping**:`yaml.safe_load` 出来不是 dict 就 400 `"YAML must be a mapping"`;
2. **YAML 语法**:`except yaml.YAMLError` → 400 附解析器原文;
3. **`safe_load`**(不是 `load`),所以没有任意 Python 对象构造。

实测:

```console
# [T3] Raw YAML endpoint: full replace + _config_version writable
PUT /api/config/raw -> 200 {'ok': True}
_config_version kept: True | OPENAI_API_KEY survived full-replace: False
PUT raw with a LIST  -> 400 {'detail': 'YAML must be a mapping'}
PUT raw with bad YAML-> 400 {'detail': 'Invalid YAML: while parsing a flow sequence...'}
```

第二行两个事实:
- `_config_version: 999` **写得进去**(`save_config` 的 `preserve_keys` 里就有
  `("_config_version",)`,:3580)。而版本号是迁移阶梯的开关:

`hermes_cli/config.py:2172 @ 863e313`

```python
    current_ver, latest_ver = check_config_version()
```

  加上 2196–2202 的 floor 判定,把它写高等于**跳过未来的所有迁移**。
  `GET /api/config` 会剥 `_*` 前缀:

`hermes_cli/web_server.py:6129 @ 863e313`

```python
    return {k: v for k, v in config.items() if not k.startswith("_")}
```

  Raw 编辑器则原样呈现 —— 同一个 dashboard,两个端点对内部键的态度相反。**记 ◇。**
- 全量替换生效:前一步 T1 种进去的 `OPENAI_API_KEY` 被这次 raw PUT 抹掉了。
  这是**符合设计**的(#62723 明确要求“编辑器拥有整个文件”),但它与
  `PUT /api/config` 的 deep-merge 语义相反 —— 前端如果先 GET raw、编辑、再 PUT raw,
  期间任何别的写入都会被覆盖(无版本号 / ETag / mtime 校验)。**记 ◇(丢失更新)。**

### 7.4 ◇ 异常兜底不对称

`hermes_cli/web_server.py:6927-6929 @ 863e313`

```python
    except Exception:
        _log.exception("PUT /api/config failed")
        raise HTTPException(status_code=500, detail="Internal server error")
```

`update_config` 有上面这层兜底,`update_config_raw` **只有** `except yaml.YAMLError`。
`save_config` 里 `require_readable_config_before_write` 抛的是 `RuntimeError`,
会以未捕获异常形式冒到 FastAPI,变成裸 500 且信息进 dashboard 健康计数器
(`DashboardHealth` 统计 5xx)。行为差异小,但是同一对端点的不一致。

---

## 8. 记号汇总

### ■ 代码缺陷

**■-1(= H-10)`PUT /api/config` 把凭据写进不参与轮换的文件,并绕过 `.env` 写入器黑名单。**
失效链见 §4.4。三条后果:
- 凭据落在 config.yaml 顶层,`.env` 不被创建;
- `gateway/run.py:2058-2060` 把它桥接成活的 `os.environ` 值;
- `credential_lifecycle._scrub_config_yaml_mirrors`(:157-171)只扫
  `model` / `auxiliary.*` / `custom_providers[*]` 的 `api_key`,**不扫顶层根键**,
  所以轮换和删除都碰不到它;
- 附带:`GET /api/config` 明文回显该值(`GET /api/env` 走 `redact_key`)。
- 提权面:`LD_PRELOAD` / `PYTHONPATH` / `PATH` / `EDITOR` 等 `_ENV_VAR_NAME_DENYLIST`
  上的名字,`PUT /api/env` 400 拒绝,`PUT /api/config` 200 接受。
  这直接违反 `hermes_cli/config.py:194-197` 自己声明的不变式。
- 修法见 §4.5。

### ▲ 文档/注释与代码矛盾

- **▲-1** `hermes_cli/web_server.py:6917` 的注释举例 `agent.personalities` / `terminal.lifetime_seconds`,
  这两个路径都不在 `DEFAULT_CONFIG` 里(`personalities` 在顶层,`terminal.lifetime_seconds`
  压根没有)。注释论点成立,例子路径不准。(源码注释层级,非 README)
- **▲-2** `hermes_cli/web_server.py:12296-12297` “`default` maps back to the global store” 在
  dashboard 自身跑在具名 profile 下时**不成立**;`gateway/pairing.py:414-418`
  的类 docstring 反而说对了。§5.4 已运行时复现。
- **▲-3** `hermes_cli/config.py:3092-3093` 称 `atomic_config_write` 是 “the single chokepoint
  every config-update path should use”,但 `save_config` 与 `set_config_value`
  这两条主路都直接调 `atomic_yaml_write`。(§6.3)

### ◇ 代码有、文档无

- **◇-1** `DEFAULT_CONFIG` 里 39 个空 dict 段在 GUI schema 中产出 0 个字段,
  完全不可见(§2.5);这正是 `PUT /api/config` 必须 deep-merge 的根因。
- **◇-2** `_infer_type` 的 `"object"` 分支在 schema 生成路径上是死代码;
  11 个 `None` 默认值被渲染成文本框(§2.3)。
- **◇-3** dashboard 里并存 **8 套** profile 作用域机制(§5.1),选择规则散落在
  各处注释里,无集中说明。
- **◇-4** `poll_oauth_session`(:10997)与 `cancel_oauth_session`(:11023)声明了
  `profile` 参数却从不使用(§5.5)。
- **◇-5** 配置文件不可解析时,GUI 静默截断+留 `.bak`,CLI 硬拒退出(§6.2)。
- **◇-6** Raw 编辑器可写 `_config_version`,等于可关掉迁移阶梯;
  而 `GET /api/config` 会剥 `_*`(§7.3)。
- **◇-7** Raw 编辑器全量替换无并发保护(无 ETag / mtime),存在丢失更新(§7.3)。
- **◇-8** `update_config` 有 `except Exception` 兜底,`update_config_raw` 没有(§7.4)。
- **◇-9** CLI 写盘保留原文件权限,GUI 强制收紧到 0600(§6.1)—— 结果 GUI 更安全,
  但两条路对同一文件的权限策略不同,文档未提。

### ◎ 文档成立但显著保守

- **◎-1** `_custom_provider_options` 的 docstring(:1171-1177)自陈插件注册表
  “opportunistic only … may legitimately be empty here”。实测本进程中 tts/stt
  注册表确实为空,该说明比实际情况**更谨慎地**描述了不确定性,是好的写法。
- **◎-2** `_schema_with_dynamic_provider_options` 的 “The module-level
  ``CONFIG_SCHEMA`` is never mutated”(:1283-1284)与实现完全一致
  (`merge` 只往 overlay 里放浅拷贝,:1293-1297),断言成立且保守。

---

## 9. 本段未覆盖 / 存疑(每条带锚点 + 一句话现象)

1. **`_SCHEMA_OVERRIDES` 里 8 个 select 的选项列表与运行时真值的一致性未逐一核对。**
   锚点与现象:

`hermes_cli/web_server.py:885 @ 863e313`

```python
        "options": ["node24", "node22", "python3.13"],  # sync with _SUPPORTED_VERCEL_RUNTIMES in terminal_tool.py
```

   —— 注释自己说“要与 terminal_tool.py 同步”,本轮只核了 tts/stt 用了运行时集合
   (`:1195-1198` 从 `BUILTIN_TTS_PROVIDERS` / `BUILTIN_STT_PROVIDERS` 导入),
   `terminal.backend`(:880)、`terminal.vercel_runtime`(:885)、`terminal.modal_mode`(:890)、
   `stt.local.model`(:926)等仍是**手写常量**,是否已漂移未验证。

2. **`stt.provider` 选项里 `mistral` 被临时移除的注释是否已过期。**
   锚点与现象:

`hermes_cli/web_server.py:919-921 @ 863e313`

```python
        # "mistral" temporarily removed — mistralai PyPI package quarantined
        # (malicious 2.4.6 release on 2026-05-12). Restore once available.
        "options": ["local", "groq", "openai", "xai", "elevenlabs"],
```

   —— 未核实 `pyproject.toml` 里 mistralai 的当前状态,也未核实 tts 侧
   (`:914` 的 tts options 仍含 `"mistral"`)为何没做同样处理。这处 tts/stt 不对称可能是缺陷。

3. **H-10 后果 C 的“网关桥接”只做了逐字复刻,未真跑 `gateway/run.py`。**
   锚点与现象:下面这行位于模块 0 缩进,即导入 `gateway.run` 就会执行到桥接循环 ——

`gateway/run.py:2035 @ 863e313`

```python
if _config_path.exists():
```

   但同文件 `:409-443` 有 venv 探测与 `os.environ["PYTHONPATH"]` 改写,整体导入在本容器
   不安全。**结论未变**(桥接是无条件模块级代码),但“端到端跑通”这一步没做。

4. **`_deep_merge` 用标量覆盖 dict section 时无守卫,GUI 侧是否真能触发未验证。**
   锚点与现象:合并的兜底分支不看类型,标量直接盖掉 dict ——

`hermes_cli/config.py:2458-2459 @ 863e313`

```python
        else:
            result[key] = value
```

   —— CLI 侧有 #74995 的守卫(`hermes_cli/config.py:4931-4981`)拦住“标量盖 section”,
   GUI 侧 `_deep_merge` 直接赋值。本轮只确认了代码路径,没构造
   `{"config": {"terminal": "hello"}}` 这类 body 实测破坏效果。

5. **`save_config` 的 managed-scope 静默剥离与 CLI 的硬拒不对称,后果未评估。**
   锚点与现象:命中 managed 键后只剥掉并打一行 stderr,不报错 ——

`hermes_cli/config.py:3538 @ 863e313`

```python
        if managed_keys:
```

   —— dashboard 进程的 stderr 通常没人看,管理员托管的键被 GUI 提交后会**静默不生效**,
   前端拿到的仍是 `{"ok": true}`。是否有前端提示未查。

6. **`GET /api/config` 明文回显 config.yaml 内容,是否有别的脱敏层未查。**
   锚点与现象:返回前唯一的过滤就是下划线前缀,没有任何值级脱敏 ——

`hermes_cli/web_server.py:6129 @ 863e313`

```python
    return {k: v for k, v in config.items() if not k.startswith("_")}
```

   —— 本轮实测 `GITHUB_TOKEN` / `OPENAI_API_KEY` 原文返回。`model.api_key`、
   `custom_providers[*].api_key` 这类**正规位置**的密钥想必也一样原文返回,
   前端是否自己做遮罩(如 `apps/desktop` / dashboard SPA)未查。

7. **119 条 profile 路由表是 depth-1 委派解析的结果,少数行的“经由”可能标浅。**
   锚点与现象:端点先经线程池再进 sync helper,机制在第二跳才出现 ——

`hermes_cli/web_routers/cron.py:52-53 @ 863e313`

```python
async def list_cron_jobs(profile: str = "all"):
    return await _run_cron_dashboard_io(_list_cron_jobs_sync, profile)
```

   —— 脚本对这类“端点 → 线程池 → sync helper → `_call_cron_for_profile`”的两跳委派
   需要人工补一跳(表中已手工修正为 C)。其余行未逐条人工复核。

8. **`_profile_scope` 的 RLock 在同一线程里嵌套获取的行为未验证。**
   锚点与现象:进程全局的 SKILLS_DIR 覆写发生在这把可重入锁内 ——

`hermes_cli/web_server.py:13612 @ 863e313`

```python
    with _SKILLS_PROFILE_LOCK:
```

   —— 若某 handler 在 `_profile_scope` 内又调用了另一个用 `_profile_scope` 的 helper
   (RLock 可重入,不会死锁),内层退出时会把 `SKILLS_DIR` 还原成**外层设置的值**还是
   **最初的值**?读码看是外层值(保存的是进入时的当前值),但没跑测试确认。
