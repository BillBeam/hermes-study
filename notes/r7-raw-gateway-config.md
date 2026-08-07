# R7 底稿 · gateway/config.py 全文件精读(2688 行 @ 863e313)

> 溯源约定:`gateway/config.py:行号 @ 863e313`;其他文件同格式。所有行号已用 Read 逐段核实。
> 本文件是 gateway 的**配置层单一权威**:定义 Platform 枚举、各级配置 dataclass、
> 三源装载(gateway.json → config.yaml → env)与全部平台的 env 发现逻辑。

## 0. 文件总览与调用地位

- 导出面:`gateway/__init__.py:12 @ 863e313` re-export `GatewayConfig, PlatformConfig, HomeChannel, load_gateway_config`。
- 主消费者:`gateway/run.py:5879 @ 863e313`(GatewayRunner 构造时 `load_gateway_config_for_runner()`)、
  `gateway/session.py:2096/2146/2197/2444`(reset 策略)、`cron/scheduler.py:1116-1118, 1501-1546`(投递目标解析)、
  `hermes_cli/web_server.py:9340-9342`(dashboard 写前校验)、`gateway/slash_commands.py:35, 3038`(/sethome 持久化)、
  `plugins/memory/honcho/cli.py:403-404`(已连接平台列表)。
- 注意:`gateway/run.py:3145 @ 863e313` 另有一个**同名不同物**的 `_load_gateway_config() -> dict`,
  它只是裸读 config.yaml 返回 dict(带 managed 覆盖),与本文件的 `load_gateway_config() -> GatewayConfig` 是两条路径。
  run.py 内 90+ 处 `_load_gateway_config()` 调用都是 dict 版;结构化版只在 Runner 构造、
  multiplex 二级 profile 启动(run.py:13272-13275)等处使用。

---

## 1. coerce 工具族(26-270)

**问题**:配置来自 YAML/JSON/env 三源,类型脏(YAML 1.1 的 `on/off` 解析成 bool、env 全是字符串、
用户手滑写错类型)。设计基调:**配置永不炸启动**——坏值降级为默认值 + warning,而非抛异常。

### 1.1 `_coerce_bool`(26-37)

`gateway/config.py:26-37 @ 863e313`
```python
def _coerce_bool(value: Any, default: bool = True) -> bool:
    """Coerce bool-ish config values, preserving a caller-provided default."""
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        return default
    return is_truthy_value(value, default=default)
```
要点:None 与"不认识的字符串"都回落 default(default 由调用方定,不是硬编码 True),
使 `enabled: "false"`(带引号)也能正确禁用(测试 `tests/gateway/test_config.py:75-77 @ 863e313`)。

### 1.2 multiplex 专用三态解析 `_env_multiplex_profiles_override`(40-74)

`gateway/config.py:48-66 @ 863e313`
```python
def _env_multiplex_profiles_override() -> "bool | None":
    """Resolve the GATEWAY_MULTIPLEX_PROFILES operator override.

    Returns ``True``/``False`` when the env var is set to a recognized truthy/
    falsy token, or ``None`` when it is unset, blank, or unrecognized — in which
    case the caller keeps the config.yaml value (env > config > default). Blank
    is deliberately ``None``, not ``False``: a provisioned-but-unpopulated Fly
    secret arrives as ``""`` and must NOT shadow a config.yaml opt-in.
    """
    raw = os.getenv("GATEWAY_MULTIPLEX_PROFILES")
    if raw is None:
        return None
    token = raw.strip().lower()
    if not token:
        return None
    if token in _MULTIPLEX_TRUTHY_STRINGS:
        return True
    if token in _MULTIPLEX_FALSY_STRINGS:
        return False
```
**问题**:托管部署(Fly)会"预置但未填值"的 secret,进程里表现为 `""`。若把 `""` 当 False,
就会覆盖用户 config.yaml 里的 opt-in——所谓"空 secret 陷阱"。
**实现**:三态返回 True/False/None;None(未设/空/不认识)让调用方回落 config.yaml,构成真 3 级链
env > config.yaml > 默认 False。不认识的值打 warning(67-73)后同样回落。
**取舍**:与 `_coerce_bool` 不同,这里必须区分"未设"与"设为假",所以单独造一个三态函数而非复用。

### 1.3 `_normalize_transport_token`(77-91)——YAML 1.1 `off` 陷阱

`gateway/config.py:87-91 @ 863e313`
```python
    if value is None:
        return "auto"
    if isinstance(value, bool):
        return "auto" if value else "off"
    return str(value).strip().lower() or "auto"
```
**问题**:YAML 1.1 把裸 `off` 解析成 Python `False`;直接 `str(False)` 得 `"false"` 而非 `"off"`,
于是 `mode: off` 会被当成未知 transport → 流式**被打开**而不是关闭(与用户意图相反)。
**实现**:bool True→"auto"、False→"off";其余字符串小写化。注释显式指向
`gateway/display_config.py` 的 `_normalise` 同类处理(79-81)。

### 1.4 数值族:`_coerce_float`(94-101)、`_coerce_int`(104-111)、`_coerce_optional_positive_int`(114-147)

第三个的语义:None/0/负数=禁用返回 None;bool 被显式拒绝(YAML `true` 是 int 子类,`int(True)==1` 会被误收),
坏值 warning+None(`gateway/config.py:122-128 @ 863e313`):
```python
    if isinstance(value, bool):
        logger.warning(
            "Ignoring invalid %s=%r (expected a positive integer; 0/null disables)",
            key,
            value,
        )
        return None
```
float 只收整数值(131-133),str 用 `int(value.strip(), 10)` 十进制严格解析(134-135)。

### 1.5 `coerce_systemd_watchdog_seconds`(150-190)——运行时/服务生成共用

`gateway/config.py:153-160 @ 863e313`
```python
def coerce_systemd_watchdog_seconds(
    value: Any, key: str = "gateway.systemd_watchdog_seconds"
) -> int:
    """Return a bounded positive watchdog interval or zero when disabled.

    Runtime and service generation share this normalization so a value can
    never enable ``Type=notify`` while disabling application heartbeats.
    """
```
**问题**:systemd watchdog 涉及两处消费——生成 unit 文件时决定 `Type=notify` 与 `WatchdogSec=`,
运行时决定是否发 sd_notify 心跳(`gateway/run.py:12637 @ 863e313` `if not self._running or self.config.systemd_watchdog_seconds <= 0`)。
若两处各自解析同一原始值且解析结果不一致(如一处收下 `"1e3"` 一处拒绝),会出现
"unit 要求心跳但应用不发心跳"→systemd 周期性杀进程。故规范化必须**唯一**(公开函数、无下划线前缀)。
**实现**:str 路径要求 `isascii() and isdecimal()`(170)——拒绝全角数字、负号、小数点;
上界 `_SYSTEMD_WATCHDOG_MAX_SECONDS = 2_147_483_647`(150,int32 上限,systemd usec 溢出防护);
任何非法值→0(=禁用,Type=simple)。
**重实现要点**:①危险开关(会导致 supervisor 杀进程的)必须共享同一个规范化函数;②非法值宁可禁用不可猜;
③字符串数字解析用 isdecimal 而非裸 int() 以拒科学计数法/下划线。

### 1.6 其余小工具

- `_coerce_dict`(193-195):非 dict 一律 `{}`。
- `_normalize_unauthorized_dm_behavior`(198-204):白名单 `{"pair","ignore"}`,否则 default。
- `_normalize_notice_delivery`(207-213):白名单 `{"public","private"}`。
- `_ensure_platform_extra_dict`(216-231):get-or-create `platforms_data[name]` 与其 `extra`,
  两层都做非 dict 矫正,返回 `(plat_data, extra)` 供原地写入——装载流程里被 shared-key 桥接、
  channel_overrides 桥接、plugin YAML hook 三处复用。

### 1.7 `_getenv` 三兄弟(234-264)——secret scope 感知的 env 读取

`gateway/config.py:234-249 @ 863e313`
```python
def _getenv(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read env vars through the active profile secret scope when present.

    ``load_gateway_config()`` runs in many contexts, including multiplexed
    profile startup where ``_profile_runtime_scope`` installs per-profile
    secrets. In that scope we must prefer the scoped value; outside it we keep
    legacy ``os.getenv`` behavior for single-profile callers and unscoped
    gateway reads.
    """
    if current_secret_scope() is not None:
        scope_val = _get_secret(name, None)
        return scope_val if scope_val is not None else default
    env_val = os.environ.get(name)
    if env_val is not None:
        return env_val
    return default
```
**问题**:多 profile 复用同一进程时,`os.environ` 是全局的,可能装着**另一个 profile** 的 token。
**实现**:若 `agent.secret_scope.current_secret_scope()` 已装(contextvar),则只从 scope 读,
**绝不**回落 `os.environ`(scope 内查无即用 default)——这是防跨 profile 凭据泄漏的关键:
scope 存在时 os.environ 完全不可见。单 profile 场景 scope 为 None,保持旧行为。
`_getenv_str`(252-254)/`_getenv_int`(257-264)是薄封装;`_apply_env_overrides` 全程用它们
(1817-1818 局部别名 `getenv = _getenv_str`),所以整个平台 env 发现天然 scope 感知。
**调用关系**:scope 由 `gateway/run.py:1938-1971 @ 863e313` `_profile_runtime_scope` 安装
(`set_hermes_home_override` + `set_secret_scope`);`run.py:2345-2348` 还把 `_getenv` 导入 run.py 使用。
**重实现要点**:①多租户进程的凭据读取必须走可插拔 scope 且 scope 存在时 fail-closed;
②scope 用 contextvar 使其能随 `copy_context()` 传进 worker 线程。

---

## 2. Platform 枚举与动态成员(267-373)

**问题**:内置平台可以写死枚举成员,但插件平台(irc、googlechat、line……)在核心代码里没有成员;
`Platform("irc")` 直接抛 ValueError 会让插件平台无法进入以 `Platform` 为 key 的各种 dict。
反过来若 `_missing_` 对任意字符串都造成员,config 里的手误(`telgram:`)会静默变成"合法平台",
且枚举被垃圾成员污染(enum pollution)。

**实现**:两级白名单的动态成员工厂。

`gateway/config.py:267-269 @ 863e313`(缓存放模块级,避免变成枚举成员):
```python
# Module-level cache for bundled platform plugin names (lives outside the
# enum so it doesn't become an accidental enum member).
_Platform__bundled_plugin_names: Optional[set] = None
```
注意命名:`_Platform__bundled_plugin_names` 手写了 name-mangling 展开形式,类体内 `cls.__bundled...`
若写在类里会成为成员/触发 mangling,故直接放模块级并用 `global` 引用(322)。

内置成员 24 个(280-303):LOCAL/TELEGRAM/DISCORD/WHATSAPP/WHATSAPP_CLOUD/SLACK/SIGNAL/MATTERMOST/
MATRIX/HOMEASSISTANT/EMAIL/SMS/DINGTALK/API_SERVER/WEBHOOK/MSGRAPH_WEBHOOK/FEISHU/WECOM/
WECOM_CALLBACK/WEIXIN/BLUEBUBBLES/QQBOT/YUANBAO/RELAY(303 标注 EXPERIMENTAL)。

`gateway/config.py:304-331 @ 863e313`
```python
    @classmethod
    def _missing_(cls, value):
        """Accept unknown platform names only for known plugin adapters.

        Creates a pseudo-member cached in ``_value2member_map_`` so that
        ``Platform("irc") is Platform("irc")`` holds True (identity-stable).
        Arbitrary strings are rejected to prevent enum pollution.
        """
        if not isinstance(value, str) or not value.strip():
            return None
        # Normalise to lowercase to avoid case mismatches in config
        value = value.strip().lower()
        # Check cache first (another call may have created it already)
        if value in cls._value2member_map_:
            return cls._value2member_map_[value]

        # Only create pseudo-members for bundled plugin platforms (discovered
        # via filesystem scan) or runtime-registered plugin platforms.
        global _Platform__bundled_plugin_names
        if _Platform__bundled_plugin_names is None:
            _Platform__bundled_plugin_names = cls._scan_bundled_plugin_platforms()
        if value in _Platform__bundled_plugin_names:
            pseudo = object.__new__(cls)
            pseudo._value_ = value
            pseudo._name_ = value.upper().replace("-", "_").replace(" ", "_")
            cls._value2member_map_[value] = pseudo
            cls._member_map_[pseudo._name_] = pseudo
            return pseudo
```
第二级:运行时注册的插件(335-345)问 `gateway.platform_registry.platform_registry.is_registered(value)`,
同样造伪成员;import 失败静默 return None(早期 import 阶段 registry 未就绪)。

`_scan_bundled_plugin_platforms`(349-368):扫 `plugins/platforms/*/`,要求目录同时有
`__init__.py` **和** `plugin.yaml|plugin.yml` 才算平台插件(357-363),全小写收集,异常吞掉返回已收集集合。

**设计理由/取舍**:
- 伪成员用 `object.__new__(cls)` 绕过 Enum 的禁实例化,写入 `_value2member_map_` 与 `_member_map_`
  两张表,保证 `Platform("irc") is Platform("irc")`(身份稳定,dict key 可用)且 `Platform["IRC"]` 也命中。
- 白名单来源是**文件系统事实**(插件确实存在)而非配置声明,手误平台名不会被造出来——
  `GatewayConfig.from_dict` 里 `except ValueError: pass`(1095-1096)静默跳过未知平台。
- 代价:`_value2member_map_` 是 CPython enum 私有实现细节;bundled 扫描结果进程级缓存,
  运行中新装 bundled 插件不重扫(但 runtime-registered 分支可兜住)。

配套快照 `gateway/config.py:371-373 @ 863e313`:
```python
# Snapshot of built-in platform values before any dynamic _missing_ lookups.
# Used to distinguish real platforms from arbitrary strings.
_BUILTIN_PLATFORM_VALUES = frozenset(m.value for m in Platform.__members__.values())
```
在动态成员产生**之前**固化"真内置"集合;消费:`gateway/run.py:21886 @ 863e313`
(`if platform.value not in _BUILTIN_PLATFORM_VALUES:` 区分插件平台)、
测试 `tests/gateway/test_platform_connected_checkers.py:53`。
注意:必须在模块 import 时立即求值,晚了就会把伪成员也算进去(`__members__` 会被 `_member_map_` 写入污染)。

**重实现要点**:①动态枚举成员必须身份稳定(缓存进 value→member 表);②白名单来自可验证事实
(文件系统/注册表),拒绝任意字符串;③"内置集合"在任何动态查找前快照;④缓存放模块级避免
被 Enum 元类捕获;⑤大小写规范化放在 `_missing_` 入口。

---

## 3. PORT_BINDING_PLATFORM_VALUES 与条件模式(376-418)

**问题**:profile 多路复用(multiplex)模式下,默认 profile 拥有唯一共享 HTTP listener,
所有 profile 走 `/p/<profile>/` 前缀。二级 profile 若启用任何绑端口的平台,必然与共享 listener 撞端口。
需要一份"哪些平台绑端口"的清单,且**两处执法点**(gateway 启动 fail-fast、dashboard 写前校验)不能各抄一份漂移。

`gateway/config.py:376-394 @ 863e313`
```python
# Platforms that bind a host TCP port (HTTP/webhook listeners). In a profile
# multiplexer the default profile owns the single shared listener and serves
# every profile through the /p/<profile>/ URL prefix, so a SECONDARY profile
# enabling one of these is always a misconfiguration: it would try to bind a
# port already held by the default's listener. Single source of truth for
# both the gateway's fail-fast startup validation (gateway/run.py) and the
# dashboard's pre-write mutation validation (hermes_cli/web_server.py) so
# the two policies cannot drift. Stored as platform .value strings.
PORT_BINDING_PLATFORM_VALUES = frozenset({
    "webhook",
    "api_server",
    "msgraph_webhook",
    "feishu",
    "wecom_callback",
    "bluebubbles",
    "sms",
    "whatsapp_cloud",
    "line",
})
```
注意存的是 `.value` 字符串而非 Platform 成员——`"line"` 是插件平台,核心枚举里没有成员,
用字符串才能把插件平台也纳入清单。

**条件模式(#52563)**:Feishu 默认 websocket 长连接(出站,不绑端口),只有 webhook 模式才绑。
若无条件把 feishu 算绑端口,multiplex 二级 profile 的 websocket-Feishu 会被误杀。

`gateway/config.py:400-417 @ 863e313`
```python
PORT_BINDING_CONDITIONAL_MODES: dict[str, str] = {
    "feishu": "webhook",
}


def platform_binds_port(platform_value: str, extra: Optional[dict] = None) -> bool:
    """Return True when *platform_value* actually binds a port for *extra* config.

    Mode-conditional platforms (Feishu) only bind in their listener mode;
    everything else in ``PORT_BINDING_PLATFORM_VALUES`` always binds.
    """
    if platform_value not in PORT_BINDING_PLATFORM_VALUES:
        return False
    expected_mode = PORT_BINDING_CONDITIONAL_MODES.get(platform_value)
    if expected_mode is not None:
        actual = str((extra or {}).get("connection_mode", "websocket")).strip().lower()
        return actual == expected_mode
    return True
```

**两处执法点**:
1. `gateway/run.py:1919-1920 @ 863e313` import 后,`run.py:13285-13300` 在
   `_start_one_profile_adapters` 里对二级 profile 扫描 `enabled and _platform_binds_port(...)`,
   命中即抛 `SecondaryPortBindingConfigError`(run.py:1933 定义,MultiplexConfigError 子类),
   错误文案直接给修复指令("Remove these platform entries … or configure them only on the default profile")。
2. `hermes_cli/web_server.py:9340-9342 @ 863e313`:dashboard 在**写入配置前**校验
   (`if platform_id not in PORT_BINDING_PLATFORM_VALUES: return None`),
   其上方注释(9335-9339)记录事故:dashboard 曾放行非法配置持久化,共享 gateway 下次启动即
   `MultiplexConfigError` 全体 profile 齐死;修复原则是**只拦启用、放行禁用/清除**,让用户能修复已坏配置。

**重实现要点**:①策略数据(哪些平台绑端口)与策略执法(启动校验/写前校验)分离,数据单点;
②条件性策略用"平台→触发模式"小表而非在数据集合里塞逻辑;③写前校验只拦"变得更坏"的方向;
④用 value 字符串而非枚举成员使插件平台可纳入。

---

## 4. HomeChannel 与 persist_home_channel(420-483)

**问题**:cron 任务写 `deliver="telegram"` 不带 chat id 时投到哪?每平台需要一个"默认目的地"。
线程化平台(Telegram topic、Slack thread)还要能把裸平台目标精确路由到 `/sethome` 所在的会话。

`gateway/config.py:420-438 @ 863e313`
```python
@dataclass
class HomeChannel:
    """
    Default destination for a platform.
    
    When a cron job specifies deliver="telegram" without a specific chat ID,
    messages are sent to this home channel. Thread-aware platforms may also
    store a thread/topic ID so the bare platform target routes to the exact
    conversation where /sethome was run.
    """
    platform: Platform
    chat_id: str
    name: str  # Human-readable name for display
    thread_id: Optional[str] = None
    # Authenticated logical-target provenance observed by a platform adapter.
    # Relay egress re-attaches these values, but the connector remains the
    # authorization boundary and resolves them against its authoritative stores.
    user_id: Optional[str] = None
    scope_id: Optional[str] = None
```
- `user_id/scope_id`:Relay(connector 前置的通用中继)出站时重挂的**已认证逻辑目标来源**;
  注释强调授权边界在 connector 侧,这两个字段只是 provenance,不是授权凭据。
- `to_dict`(440-452)只写非空可选字段;`from_dict`(454-463)对所有 id 做 `str(...)` 强转
  (YAML 数字 chat id → 字符串,统一比较语义)。

`persist_home_channel`(466-482)——写回 config.yaml 的唯一入口:
`gateway/config.py:466-482 @ 863e313`
```python
def persist_home_channel(home: HomeChannel, *, enabled_if_new: bool = False) -> None:
    """Persist a logical home without falsely enabling a Relay-fronted adapter."""
    from hermes_cli.config import load_config, save_config

    config = load_config()
    platforms = config.setdefault("platforms", {})
    if not isinstance(platforms, dict):
        platforms = {}
        config["platforms"] = platforms
    platform_config = platforms.setdefault(home.platform.value, {})
    if not isinstance(platform_config, dict):
        platform_config = {}
        platforms[home.platform.value] = platform_config
    if enabled_if_new:
        platform_config.setdefault("enabled", True)
    platform_config["home_channel"] = home.to_dict()
    save_config(config)
```
关键是 `enabled_if_new` 关键字:调用点 `gateway/slash_commands.py:3038 @ 863e313`
`persist_home_channel(home, enabled_if_new=not via_relay)`——经 Relay 收到的 `/sethome`
**不能**顺手把本地对应平台适配器 enabled=True(平台实际由远端 connector 服务,本地 enable 会起一个
没凭据的适配器);直连平台才 `setdefault("enabled", True)`(且是 setdefault,不覆盖显式 false)。

env 侧对应:`_apply_env_overrides` 里每个平台都有 `<PLAT>_HOME_CHANNEL(_NAME/_THREAD_ID)` 三件套
(如 telegram 1858-1865)。Slack 特殊(1990-2005):env 换 home 时,仅当 chat_id 与旧值相同才保留
`user_id/scope_id`(1997, 2003-2004)——换了目的地,旧 provenance 即失效。

**重实现要点**:①默认投递目标含 thread 维度;②写回用 setdefault 语义尊重既有显式配置;
③中继场景下"记录 home"与"启用适配器"必须解耦;④provenance 字段随目标变更失效。

---

## 5. SessionResetPolicy(485-542)

**问题**:会话上下文何时清空?常驻 bot 的会话若永不重置,上下文靠压缩管理;若定时/闲时重置,
用户第二天回来是"新对话"。2026-07 前默认 `both`(24h idle + 每日 4 点),用户抱怨对话莫名消失,遂改默认 `none`。

`gateway/config.py:485-511 @ 863e313`
```python
@dataclass
class SessionResetPolicy:
    """
    Controls when sessions reset (lose context).
    
    Modes:
    - "daily": Reset at a specific hour each day
    - "idle": Reset after N minutes of inactivity
    - "both": Whichever triggers first (daily boundary OR idle timeout)
    - "none": Never auto-reset (context managed only by compression)

    Default is "none" — sessions never auto-reset unless the user opts in
    via the `session_reset` section in config.yaml (or gateway.json
    overrides). Changed July 2026 from "both" (24h idle + daily 4am), which
    surprised users who expected their conversations to persist.
    """
    mode: str = "none"  # "daily", "idle", "both", or "none"
    at_hour: int = 4  # Hour for daily reset (0-23, local time)
    idle_minutes: int = 1440  # Minutes of inactivity before reset (24 hours)
    notify: bool = True  # Send a notification to the user when auto-reset occurs
    notify_exclude_platforms: tuple = ("api_server", "webhook")  # Platforms that don't get reset notifications
    # A background process this many hours old (or older) no longer blocks
    # session idle/daily reset. A forgotten preview server should not keep a
    # session alive forever (#29177). The process is NOT killed — only ignored
    # by the reset guard. Raise this if you run legitimate multi-day jobs whose
    # liveness should pin the conversation open.
    bg_process_max_age_hours: int = 24
```
- `notify_exclude_platforms` 默认排除 api_server/webhook(程序化平台没有"用户"可通知);
  消费:`gateway/run.py:16491 @ 863e313` `and platform_name not in policy.notify_exclude_platforms`。
- `bg_process_max_age_hours`(#29177):活着的后台进程会**阻止**重置(有活干说明会话还在用);
  但被遗忘的 preview server 会把会话钉死永不重置。方案:超过 24h 的后台进程**不再阻止**重置
  (进程不杀,只是 reset guard 忽略它)。消费:`gateway/run.py:5915-5920 @ 863e313`。
- `from_dict`(523-540):逐字段"missing 或显式 null 都用默认"(`x if x is not None else 默认`),
  因 YAML `at_hour:`(空值)解析为 None;`notify` 走 `_coerce_bool`,`exclude` 强转 tuple。
- 数值合法性(at_hour 0-23、idle_minutes>0)**不在这里**校验,统一放 `_validate_gateway_config`(1761-1772)。

**重实现要点**:①重置默认保守(none),破坏性行为必须 opt-in;②"活跃工作阻止重置"要配年龄上限
防钉死;③YAML null 与缺 key 同义;④通知排除表按平台声明。

---

## 6. ChannelOverride(543-574)

**问题**:同一 gateway 服务多个频道(Discord #daily 与 #dev),想用不同模型/人格,
不想为此跑多个 gateway 实例。

`gateway/config.py:543-554 @ 863e313`
```python
@dataclass
class ChannelOverride:
    """
    Per-channel override for model, provider, and system prompt.

    Used in config under platforms.<name>.channel_overrides[channel_id].
    Enables different channels (e.g. Discord #daily vs #dev) to use different
    models and personas without running separate gateway instances.
    """
    model: Optional[str] = None
    provider: Optional[str] = None
    system_prompt: Optional[str] = None
```
三字段全可选;`to_dict`(556-564)只写非 None,`from_dict`(566-574)容 None 输入。
装载侧:PlatformConfig.from_dict 里 `channel_overrides` key 全部 `str(cid)`(689-694,YAML 数字频道 id 统一成字符串);
load_gateway_config 的 shared-key 循环里 channel_overrides 从平台 YAML 块桥接进 plat_data(1617-1628)。
消费:`gateway/run.py:2343-2344` import ChannelOverride 后在 agent 构建处按 channel 查表。

---

## 7. PLATFORM_TOKEN_ENV_NAMES(577-590)与 PlatformConfig(593-707)

### 7.1 token-认证平台清单(#64674)

`gateway/config.py:577-590 @ 863e313`
```python
# Canonical map of platforms whose primary credential is ``PlatformConfig.token``
# and the env var it loads from. Used for empty-token warnings at config
# validation and by the multiplex primary-startup credential gate in
# ``gateway.run`` (#64674). Platforms absent from this map authenticate some
# other way (session files, port-bound webhooks, api_key-only) and must never
# be skipped for a missing token.
PLATFORM_TOKEN_ENV_NAMES: dict["Platform", str] = {
    Platform.TELEGRAM: "TELEGRAM_BOT_TOKEN",
    Platform.DISCORD: "DISCORD_BOT_TOKEN",
    Platform.SLACK: "SLACK_BOT_TOKEN",
    Platform.MATTERMOST: "MATTERMOST_TOKEN",
    Platform.MATRIX: "MATRIX_ACCESS_TOKEN",
    Platform.WEIXIN: "WEIXIN_TOKEN",
}
```
两个消费点:①`_validate_gateway_config` 的空 token 警告与占位 token 拒启(1776-1812);
②`gateway/run.py:2009-2026 @ 863e313` `_platform_has_bot_credential`——multiplex 主启动时,
只有**在此表中且无 token/api_key** 的平台才被跳过;不在表中的平台(Signal 走 session 文件、
webhook 类走端口)**永不**因缺 token 被跳(2017-2018 `if platform not in PLATFORM_TOKEN_ENV_NAMES: return True`)。
这是"缺凭据跳过"逻辑的反向白名单:宁可让平台自己连接失败,也不误杀非 token 认证平台。

### 7.2 PlatformConfig 全字段(593-636)

`gateway/config.py:593-599 @ 863e313`
```python
@dataclass
class PlatformConfig:
    """Configuration for a single messaging platform."""
    enabled: bool = False
    token: Optional[str] = None  # Bot token (Telegram, Discord)
    api_key: Optional[str] = None  # API key if different from token
    home_channel: Optional[HomeChannel] = None
```
- `reply_to_mode`(605)`"off"/"first"/"all"`:多段回复是否/如何 reply-thread 到用户消息,默认 first
  (只有首段挂回复,后续段独立——首段给上下文,全挂会刷屏)。
- `gateway_restart_notification`(612):是否允许 "♻️ Gateway online" 生命周期通知;默认 True 保旧行为,
  面向最终用户的平台(Slack)可关(运维味的重启 ping 是噪音)。
- `typing_indicator`(621):处理期间的"typing…"指示;默认 True。Slack 的
  `assistant.threads.setStatus` "is thinking…" 会**禁用输入框**,故有人要关(614-620 注释)。
  驱动 `gateway/platforms/base.py` 的 `_keep_typing` 刷新循环。
- `typing_status_text`(630):文本型指示器(Slack setStatus 行、Google Chat 可见标记消息)的自定义文案;
  None 用各平台内置默认;无文本指示器的平台(Discord/Telegram/Matrix)忽略。
- `channel_overrides`(633):`Dict[str, ChannelOverride]`。
- `extra`(636):`Dict[str, Any]` 平台私有配置的**垃圾抽屉**——所有非通用字段(url、app_id、
  policy、allow_from……)都进这里,adapters 自取。这是"核心 schema 稳定 + 平台差异外置"的关键取舍。

### 7.3 from_dict 的"双路取值"(660-707)

`gateway/config.py:667-687 @ 863e313`
```python
        # gateway_restart_notification may be bridged into extra via the
        # shared-key loop in load_gateway_config(); check both top-level
        # and extra so YAML ``discord: gateway_restart_notification: false``
        # works without needing a separate platforms: block.
        extra = _coerce_dict(data.get("extra", {}))
        _grn = data.get("gateway_restart_notification")
        if _grn is None:
            _grn = extra.get("gateway_restart_notification")

        # typing_indicator mirrors gateway_restart_notification: it may arrive
        # top-level or bridged into extra by the shared-key loop in
        # load_gateway_config(), so check both.
        _typing = data.get("typing_indicator")
        if _typing is None:
            _typing = extra.get("typing_indicator")

        # typing_status_text takes the same two routes (top-level or bridged
        # into extra); string passthrough, no coercion.
        _typing_text = data.get("typing_status_text")
        if _typing_text is None:
            _typing_text = extra.get("typing_status_text")
```
原因:用户写顶层 `discord: {gateway_restart_notification: false}` 时,shared-key 循环把它桥进 extra;
用户写 `platforms.discord.gateway_restart_notification` 时它在顶层。两路都认,dataclass 字段才总能取到。
坏 home_channel(非 dict,如 `"telegram:123"`)被忽略而非炸(663-665;
测试 `tests/gateway/test_config.py:128-140 @ 863e313` 行为规格:enabled 保留、home_channel=None、extra={})。

**重实现要点**:①平台配置=少量通用字段+extra 抽屉;②通用字段允许"顶层或 extra"双路到达;
③enabled 默认 False(平台必须显式或经发现启用);④坏子结构丢弃不炸。

---

## 8. StreamingConfig 与 DEFAULT_STREAMING_* 常量(710-812)

### 8.1 常量单一权威(710-717)

`gateway/config.py:710-717 @ 863e313`
```python
# Streaming defaults — single source of truth so both StreamingConfig and
# StreamConsumerConfig agree on the out-of-the-box edit rhythm.  Tuned for
# Telegram's ~1 edit/s flood envelope: a touch under 1s lets the cadence
# breathe without bumping into rate limits, and a smaller buffer threshold
# makes short replies feel near-instant in DMs.
DEFAULT_STREAMING_EDIT_INTERVAL: float = 0.8
DEFAULT_STREAMING_BUFFER_THRESHOLD: int = 24
DEFAULT_STREAMING_CURSOR: str = " ▉"
```
与 stream_consumer 的关系:`gateway/stream_consumer.py:31-33 @ 863e313` 直接
`from gateway.config import DEFAULT_STREAMING_* as _DEFAULT_...`,其
`StreamConsumerConfig`(stream_consumer.py:128-132)的默认值就是这三个常量。
即:**配置对象(StreamingConfig,用户面)与执行对象(StreamConsumerConfig,消费 token 流的机器)
共享同一组默认值常量**,任何一侧单改默认会破坏"未配置=一致节奏"的不变量。
运行时桥接在 `gateway/run.py:23759-23826 @ 863e313` `_build_stream_consumer_config`:
从 `config.streaming`(scfg)读 edit_interval/buffer_threshold/cursor/transport/fresh_final_after_seconds,
再叠平台修正(不支持编辑的平台去 cursor 或直接拒绝流式;Matrix 抑制 cursor 走 buffer_only;
fresh_final 仅 Telegram 生效)后构造 StreamConsumerConfig。
数值直觉:0.8s 编辑间隔贴着 Telegram ~1 edit/s 的 flood 包络留余量;24 字符缓冲阈值让 DM 短回复几乎即时。

### 8.2 StreamingConfig 字段(720-751)

- `enabled: bool = False`(723)——**总开关默认关**。
- `transport: str = "auto"`(740):`auto|draft|edit|off` 四值(724-731 注释)。
  `auto` 敢做全局默认的理由(733-739):不支持 draft 的适配器 `supports_draft_streaming()==False`
  自动落回 edit 路径,auto 只会升级能渲染原生 draft 的会话(Telegram Bot API 9.5+ sendMessageDraft),
  不会回归其他平台。
- `edit_interval/buffer_threshold/cursor`(741-743)= 上述常量。
- `fresh_final_after_seconds: float = 0.0`(751,自 openclaw/openclaw#72038 移植):>0 时,
  预览消息已可见超过该秒数的长回复,最终版以**新消息**发出(平台时间戳=完成时刻而非首 token 时刻);
  仅 Telegram 应用;默认 0 关闭。

### 8.3 from_dict 的 `mode` 别名语义(763-797)

`gateway/config.py:768-797 @ 863e313`(节选)
```python
        # ``mode`` is an ergonomic alias for the transport that ALSO implies
        # ``enabled``.  A config like ``streaming: {mode: auto}`` reads as
        # "turn streaming on, transport=auto" — matching the natural intent
        # of someone enabling streaming without also spelling out
        # ``enabled: true``.  Without this, ``mode`` was silently ignored and
        # streaming stayed disabled (``enabled`` defaults to False), which is
        # a surprising footgun: the whole reply buffers and sends at once.
        # ``mode: off`` disables streaming; an explicit ``enabled`` key always
        # wins so callers can force either state.
        #
        # ``transport`` alone does NOT imply ``enabled``: ``streaming.enabled``
        # is the documented master switch (see website/docs/user-guide/
        # configuration.md), so a bare ``transport`` only selects HOW to stream
        # once streaming is on. Only the ``mode`` alias flips ``enabled``.
        raw_transport = data.get("transport")
        raw_mode = data.get("mode")
        picked = raw_transport if raw_transport is not None else raw_mode
        transport = _normalize_transport_token(picked)

        if "enabled" in data:
            enabled = _coerce_bool(data.get("enabled"), False)
        elif raw_mode is not None:
            enabled = _normalize_transport_token(raw_mode) != "off"
        else:
            enabled = False
```
三层优先级:显式 `enabled` > `mode` 推断(off→False,其余→True)> 默认 False;
`transport` 与 `mode` 同在时 transport 赢(787);两者都经 `_normalize_transport_token`
吃掉 YAML `off`→False 陷阱(见 1.3)。空/非 dict 输入直接默认实例(765-766)。

**重实现要点**:①用户友好别名(mode)可以隐含开关,但正式字段(transport)不隐含,
显式开关永远最高;②配置对象与执行对象共享默认常量;③平台节流包络决定默认节奏数值;
④YAML 1.1 布尔陷阱要在所有 token 入口统一规范化。

---

## 9. 连接判定:_has_usable_api_server_key 与 _PLATFORM_CONNECTED_CHECKERS(815-869)

**问题**:"enabled"≠"能连"。平台开了但凭据不全,启动适配器只会 retry-forever 刷错误日志。
需要每平台的"配置充分性"判定,供 `get_connected_platforms()`(prompt 渲染、状态页)与启动决策使用。

`gateway/config.py:822-835 @ 863e313`
```python
def _has_usable_api_server_key(key: object) -> bool:
    """True when API_SERVER_KEY is present and strong enough to be usable.

    Mirrors the startup guard in ``gateway/platforms/api_server.py``
    (``has_usable_secret`` with ``min_length=16``) so the platform is only
    enrolled at load time when the adapter would actually agree to start.
    """
    if not key:
        return False
    try:
        from hermes_cli.auth import has_usable_secret
    except ImportError:
        return len(str(key).strip()) >= 16
    return has_usable_secret(key, min_length=16)
```
要点:load 时的判定与 adapter 启动守卫**同一强度标准**(min_length=16,拒占位符),
否则出现"config 层认为已连,adapter 拒启,reconnect watcher 空转"的撕裂;ImportError 时退化为长度检查。

`_PLATFORM_CONNECTED_CHECKERS`(838-869):`dict[Platform, Callable[[PlatformConfig], bool]]`,
仅收不走"generic token/api_key"路径的平台:
- WEIXIN:`account_id and (token or extra.token)`(839-841)
- WHATSAPP_CLOUD:`phone_number_id and access_token`(842-844)
- SIGNAL:`http_url`(845)
- API_SERVER:`_has_usable_api_server_key(extra["key"])`(846-848)
- WEBHOOK:恒 True(849,无凭据概念,开了就算连)
- MSGRAPH_WEBHOOK:`client_state` 非空白(850-852)
- BLUEBUBBLES:`server_url and password`;QQBOT:`app_id and client_secret`;YUANBAO:`app_id and app_secret`
- RELAY(862-868):`relay_url or url` 即连——出站拨号,能力描述符握手时协商,URL 是实验阶段唯一配置级信号。

---

## 10. GatewayConfig(872-1247)

### 10.1 字段逐一交代(879-956)

| 字段(行号) | 默认 | 含义/理由 |
|---|---|---|
| `platforms`(880) | `{}` | `Dict[Platform, PlatformConfig]` |
| `default_reset_policy`(883) | SessionResetPolicy() | 见 §5 |
| `reset_by_type`(884) | `{}` | 按会话类型(dm/group/thread)覆盖 |
| `reset_by_platform`(885) | `{}` | 按平台覆盖 |
| `reset_triggers`(888) | `["/new","/reset"]` | 触发重置的斜杠命令 |
| `quick_commands`(891) | `{}` | 用户自定义、**绕过 agent 循环**的斜杠命令;消费 run.py:14979-14983, 15408-15424 |
| `sessions_dir`(894) | `~/.hermes/sessions` | 会话存储路径 |
| `write_sessions_json`(901) | True | 是否继续写 legacy sessions.json 镜像;主副本在 state.db gateway_routing 表(#9006);默认 True 为外部工具/降级兼容;消费 session.py:1251-1253, 1532, 1563 |
| `always_log_local`(904) | True | cron 输出总是落本地文件 |
| `filter_silence_narration`(911) | True | 出站丢弃"沉默叙述"(`*(silent)*`、🔇、裸`.`)——模型无话可说时的幻觉产物;bot 对 bot 频道里会互相镜像烧 token;基底级守卫,不依赖 SOUL.md/prompt 不漂移 |
| `stt_enabled`(914) | True | 入站语音自动转写 |
| `stt_echo_transcripts`(915) | True | 把 STT 原文回显给用户 |
| `group_sessions_per_user`(918) | True | 群聊按参与者隔离会话(有 user id 时) |
| `thread_sessions_per_user`(919) | False | 线程默认全员共享 |
| `max_concurrent_sessions`(920) | None | 正整数=并发活跃会话上限 |
| `multiplex_profiles`(927) | False | 多 profile 复用开关;开=默认 profile 的 gateway 服务全主机 profile(session key 打 profile 戳、按 profile 解析凭据);关=严格旧行为 |
| `systemd_watchdog_seconds`(931) | 0 | 0=Type=simple、不发 sd_notify;见 §1.5 |
| `loop_watchdog`(938) | True | 进程内事件循环活性看门狗(#69089):daemon 线程 call_soon_threadsafe 探测,连续失败即 dump 全线程栈并以 service-restart 码硬退,供 supervisor 拉起;消费 run.py:10627-10631 |
| `unauthorized_dm_behavior`(941) | "pair" | 未授权 DM:发配对流程 or 无视 |
| `streaming`(944) | StreamingConfig() | 见 §8 |
| `session_store_max_age_days`(951) | 90 | SessionEntry 超龄剪枝(内存 dict+sessions.json);0=关;用户无感——回来即如 reset 后新会话(946-950 注释) |
| `profile_routes`(956) | `[]` | 特定 guild/channel/thread → profile 的路由规则,见 gateway/profile_routing.py |

`__post_init__`(958-961):对直接构造(绕过 from_dict)的实例也跑 `coerce_systemd_watchdog_seconds`,
保证该字段无论何路进来都已规范化。

### 10.2 get_connected_platforms / _is_platform_connected(963-1020)

`gateway/config.py:963-978 @ 863e313`
```python
    def get_connected_platforms(self) -> List[Platform]:
        """Return list of platforms that are enabled and configured.

        Sorted by platform value so the rendered "Connected Platforms" list
        (and the home-channel blocks derived from it) is byte-stable across
        gateway restarts and mid-process platform registration — dict
        insertion order is not a stable contract and a reorder busts the
        prompt cache without any semantic change.
        """
        connected = []
        for platform, config in self.platforms.items():
            if not config.enabled:
                continue
            if self._is_platform_connected(platform, config):
                connected.append(platform)
        return sorted(connected, key=lambda p: str(p.value))
```
**排序的理由是 prompt cache**:该列表被渲染进 system prompt("Connected Platforms" 块),
dict 插入序不稳定,重启/中途注册导致重排 → 前缀字节变化 → prompt cache 全失效,而语义没变。
按 value 排序换字节稳定。

`_is_platform_connected`(980-1020)四级判定:
1. WEIXIN 特判**先于** generic(984-988)——否则"有 token 无 account_id"会被 generic 放行;
2. generic:`token or api_key` 即连(991-992,覆盖 Telegram/Discord/Slack/Matrix/Mattermost/HASS);
3. `_PLATFORM_CONNECTED_CHECKERS` 查表(995-997);
4. 插件平台(999-1018):先强制 `discover_plugins()`(幂等)——直接构造 GatewayConfig 的测试/调用方
   没走 load_gateway_config 也能判;registry entry 依次用 `is_connected` → `validate_config` → 恒 True;
   全程 try/except 吞(早期 import 时 registry 未初始化)。

### 10.3 get_home_channel(1022-1027)/ get_reset_policy(1029-1047)

`gateway/config.py:1029-1047 @ 863e313`
```python
    def get_reset_policy(
        self, 
        platform: Optional[Platform] = None,
        session_type: Optional[str] = None
    ) -> SessionResetPolicy:
        """
        Get the appropriate reset policy for a session.
        
        Priority: platform override > type override > default
        """
        # Platform-specific override takes precedence
        if platform and platform in self.reset_by_platform:
            return self.reset_by_platform[platform]
        
        # Type-specific override (dm, group, thread)
        if session_type and session_type in self.reset_by_type:
            return self.reset_by_type[session_type]
        
        return self.default_reset_policy
```
分辨率:platform > session_type > default,**首个命中即返回整个策略对象**(不做字段级合并)。
消费:`gateway/session.py:2096, 2146, 2197, 2444 @ 863e313`(idle/daily 判定与 GC),
`gateway/run.py:16478`。get_home_channel 消费:run.py:9402, 11752, 17406。

### 10.4 to_dict / from_dict(1049-1217)

to_dict(1049-1082):全字段序列化;`profile_routes` 元素若是 dataclass 用 `asdict`(1078-1081,
`is_dataclass(r) and not isinstance(r, type)` 防传入类本身)。
from_dict 要点(按行):
- 平台解析(1088-1096):非 dict 块跳过;`Platform(platform_name)` 失败(非白名单)静默跳过。
- reset_by_type/reset_by_platform(1098-1108)同样容错。
- `sessions_dir`(1114-1116)缺省 `get_hermes_home()/sessions`。
- STT 双路(1122-1131):顶层 `stt_enabled` 或嵌套 `stt: {enabled: ...}`。
- **嵌套 gateway 段回落**(1136-1176):`systemd_watchdog_seconds`、`loop_watchdog`、
  `max_concurrent_sessions`、`multiplex_profiles` 都接受 `gateway.<key>` 形式
  (`hermes config set gateway.x` 天然产生该形状);顶层 key **存在**即赢(按 `in` 判存在而非真值)。
- multiplex 三级链(1155-1166):
`gateway/config.py:1164-1166 @ 863e313`
```python
        env_multiplex = _env_multiplex_profiles_override()
        if env_multiplex is not None:
            multiplex_profiles = env_multiplex
```
  配注释(1155-1163):托管部署(Nous Portal/Fly)在容器上钉 `GATEWAY_MULTIPLEX_PROFILES`,
  connector 的 per-profile relay 路由**依赖**单一 multiplex gateway,必须每次 boot 强制开启,
  不管镜像内 config.yaml 写什么;自托管用户继续用 config.yaml。
- `session_store_max_age_days`(1182-1186):int 化+`max(x,0)`,坏值回 90。
- `profile_routes`(1188-1190):委托 `gateway.profile_routing.parse_profile_routes` 校验。
- 组装(1192-1217):所有 bool 走 `_coerce_bool` 并给出各自默认。

### 10.5 get_unauthorized_dm_behavior(1219-1235)/ get_notice_delivery(1237-1246)

`gateway/config.py:1219-1235 @ 863e313`
```python
    def get_unauthorized_dm_behavior(self, platform: Optional[Platform] = None) -> str:
        """Return the effective unauthorized-DM behavior for a platform.

        Email is inbox-shaped, not chat-shaped, so it defaults to ``"ignore"``
        unless ``platforms.email.unauthorized_dm_behavior`` explicitly opts
        into pairing. A global default does not opt email into pairing.
        """
        if platform:
            platform_cfg = self.platforms.get(platform)
            if platform_cfg and "unauthorized_dm_behavior" in platform_cfg.extra:
                return _normalize_unauthorized_dm_behavior(
                    platform_cfg.extra.get("unauthorized_dm_behavior"),
                    self.unauthorized_dm_behavior,
                )
            if platform == Platform.EMAIL:
                return "ignore"
        return self.unauthorized_dm_behavior
```
分辨率:平台 extra 显式值 > EMAIL 特判 "ignore" > 全局。EMAIL 特判的理由:邮箱是收件箱形态,
陌生来信是常态(垃圾邮件),对每封未授权邮件发"配对邀请"等于给 spammer 自动回执;
**全局 default 不能把 email 拉进 pair**,只有 email 平台块显式写了才行。
get_notice_delivery(1237-1246):平台 extra 显式值 > "public",无全局字段(公告默认公开发)。
消费:run.py:14460(_get_unauthorized_dm_behavior 包装)、run.py:13905-13906、
`gateway/authz_mixin.py`、telegram adapter。

**重实现要点(GatewayConfig 层)**:①渲染进 prompt 的任何列表必须字节稳定(排序);
②策略查找用"整对象替换"而非字段合并,语义简单可预测;③形态特殊的平台(email)在 getter 里
硬编码安全默认,不靠用户记得配置;④from_dict 对每个来源形状(顶层/嵌套/别名)显式写优先级。

---

## 11. load_gateway_config 装载全流程(1249-1750)

声明的优先级(docstring 1253-1257):env > config.yaml > gateway.json(legacy)> 内置默认。
实际流程八步:

**① gateway.json 底层**(1262-1274):存在则 json.load 进 `gw_data`,打 info 提示迁移;失败 warning 继续。

**② config.yaml + managed 覆盖**(1276-1290):
`gateway/config.py:1284-1290 @ 863e313`
```python
            # Managed scope: overlay administrator-pinned values so the gateway
            # honors them too. This loader builds its own dict instead of going
            # through hermes_cli.config.load_config, so without this a managed
            # session_reset / quick_commands / stt / model would be ignored by
            # the messaging gateway. Fail-open via the shared helper.
            from hermes_cli import managed_scope
            yaml_cfg = managed_scope.apply_managed_overlay(yaml_cfg)
```
本 loader 自建 dict、不走 `hermes_cli.config.load_config`,所以管理员钉值(managed scope)要单独 overlay,
否则 gateway 会无视托管配置。fail-open(overlay 失败不拦启动)。

**③ 顶层/嵌套 gateway.* 双路 key 逐个搬运**(1292-1419):
`gateway/config.py:1300-1305 @ 863e313`
```python
            # Map config.yaml keys → GatewayConfig.from_dict() schema.
            # Each key overwrites whatever gateway.json may have set.
            # Precedence contract: key-presence at the TOP LEVEL wins; the
            # nested gateway.* form is consulted only when the top-level key
            # is absent (not merely falsy/mistyped), so a present-but-empty
            # top-level value is never silently replaced by the nested one.
```
覆盖 session_reset、quick_commands(非 dict 打 warning 丢弃,1316-1323)、stt、stt_echo_transcripts、
group/thread_sessions_per_user、multiplex_profiles、profile_routes、max_concurrent_sessions、
systemd_watchdog_seconds、streaming、reset_triggers、always_log_local、write_sessions_json、
filter_silence_narration、unauthorized_dm_behavior——每个都是"顶层 `in` 存在即赢,否则查
`gateway_section`"的同构模板。判**存在**而非真值:顶层写了空值也不被嵌套值顶掉。

**④ 平台 map 合并 `_merge_platform_map`**(1421-1450):
`gateway/config.py:1431-1447 @ 863e313`
```python
            def _merge_platform_map(source_platforms: Any) -> None:
                if not isinstance(source_platforms, dict):
                    return
                for plat_name, plat_block in source_platforms.items():
                    if not isinstance(plat_block, dict):
                        continue
                    existing = platforms_data.get(plat_name, {})
                    if not isinstance(existing, dict):
                        existing = {}
                    # Deep-merge extra dicts so gateway.json defaults survive
                    merged_extra = {**existing.get("extra", {}), **plat_block.get("extra", {})}
                    if "enabled" in plat_block:
                        merged_extra["_enabled_explicit"] = True
                    merged = {**existing, **plat_block}
                    if merged_extra:
                        merged["extra"] = merged_extra
                    platforms_data[plat_name] = merged
```
调用顺序:先 `gateway.platforms` 后顶层 `platforms`(1449-1450)——后合并者赢,即顶层优先。
extra 单独深合并一层(gateway.json 的 extra 默认值存活)。**`_enabled_explicit` 哨兵**在此诞生:
只要用户在任一块里写了 `enabled` key(无论 true/false),就在 extra 里打标,后续
`_apply_env_overrides` 据此区分"用户显式禁用"与"默认禁用"(#41112,见 §13)。
1452-1469:再扫 `gateway.*` 下直接的平台名子段(如 `gateway.api_server`),用 `Platform(_k)` 白名单
过滤后并入(动态成员机制让插件平台名也能被识别)。

**⑤ api_server 顶层键桥接**(1471-1484):`port/key/host/cors_origins/model_name` 从平台块顶层
pop 进 extra(adapter 只读 extra)——YAML 路径复刻 env 路径 `_apply_env_overrides` 的行为。

**⑥ shared-key 桥接大循环**(1486-1641):
先 `discover_plugins()`(幂等,1490-1496)并把 registry 的插件平台追加进遍历目标
`_shared_loop_targets`(1498-1506,#24836 插件作者享受同等桥接)。
对每平台(跳过 LOCAL,1509-1510):取顶层 `yaml_cfg[plat.value]` 块;没有则回落
`platforms`/`gateway.platforms` 块(1524-1530,注释引 #44f3e51:与 apply_yaml_config_fn 派发的
回落一致;`enabled` 不从回落块重写,因 `_merge_platform_map` 已按正确优先级并过,1520-1523)。
把一长串通用 key 桥进 extra(1533-1598):`unauthorized_dm_behavior, notice_delivery, reply_prefix,
reply_in_thread, cron_continuable_surface, require_mention, send_read_receipts, free_response_channels,
mention_patterns, exclusive_bot_mentions, dm_policy, allow_from, allow_admin_from, user_allowed_commands,
group_policy, group_allow_from, group_allow_admin_from, group_user_allowed_commands, channel_prompts,
gateway_restart_notification, typing_indicator, typing_status_text`;Telegram 限定
`allowed_chats/group_allowed_chats/allowed_topics/observe_unmentioned_group_messages`
(1555-1560, 1567-1568),Discord/Slack 限定 `channel_skill_bindings`(1585-1586)。
webhook/msgraph_webhook 桥 `port/host/secret`、api_server 桥 `port/host`(1599-1616,注释说明:
不桥则 YAML `platforms.webhook.port: 8649` 静默落回硬编码 DEFAULT_PORT)。
channel_overrides 桥接(1617-1628)。收尾(1629-1641):
`gateway/config.py:1629-1641 @ 863e313`
```python
                enabled_was_explicit = _cfg_toplevel and "enabled" in platform_cfg
                if not bridged and not enabled_was_explicit and not has_channel_overrides:
                    continue
                plat_data, extra = _ensure_platform_extra_dict(platforms_data, plat.value)
                if enabled_was_explicit:
                    plat_data["enabled"] = platform_cfg["enabled"]
                    # Mark the explicit enable/disable so the registry-driven
                    # plugin-enable pass in _apply_env_overrides honors an
                    # explicit ``enabled: false`` for migrated plugin platforms
                    # (slack, telegram, matrix, dingtalk, whatsapp, feishu …)
                    # instead of re-enabling them on token/SDK presence. #41112.
                    extra["_enabled_explicit"] = True
                extra.update(bridged)
```

**⑦ 插件 YAML→env 桥接派发**(1643-1678,#24836):
对每个 registry entry 调 `entry.apply_yaml_config_fn(yaml_cfg, platform_cfg)`
(契约见 `gateway/platform_registry.py:124-137 @ 863e313`:允许 mutate os.environ,须用
`not os.getenv(...)` 守卫保 env>YAML 优先;返回 dict 并入 extra;异常 debug 级吞)。
顺序注释(1645-1647):shared-key 循环 → 本派发 → 遗留硬编码块(hook 已设 env 时是 no-op)→
`_apply_env_overrides`。历史上核心里每平台一段的硬编码桥(slack/telegram/whatsapp/dingtalk/
mattermost/matrix/feishu)已全部迁入各插件 adapter 的 hook(1680-1732 只剩注释墓碑,引
#41112/#3823/#25443);仅剩两个留守:
- 顶层 `require_mention` → Telegram(1685-1703,#3979):用户常把它和 group_sessions_per_user
  并排写顶层;它不在 telegram: 块里,telegram 插件的 hook(只在 telegram 块存在时运行)覆盖不到,
  必须留核心;同时桥 env `TELEGRAM_REQUIRE_MENTION`(带 not os.getenv 守卫)。
- signal.require_mention → `SIGNAL_REQUIRE_MENTION`(1713-1717,signal 尚未插件化)。

**⑧ 收尾**(1734-1750):整个 config.yaml 处理包在一个大 try 里,任何异常 warning
"falling back to .env / gateway.json values"(1734-1740)——配置解析永不拦启动。然后:
```python
    config = GatewayConfig.from_dict(gw_data)
    _apply_env_overrides(config)
    _validate_gateway_config(config)
    return config
```
(1742-1750)。

**重实现要点(装载器)**:①分层装载 = 底层 dict 合并(legacy→yaml)+ 对象化 + env 覆盖 + 校验,
每层职责单一;②"顶层 vs 嵌套"用 key-presence 判优先,不用真值;③平台通用 key 的桥接白名单
集中一处,平台私有 key 交插件 hook;④显式 enabled 打哨兵标,供后续自动启用 pass 尊重用户禁用;
⑤全程 fail-open,坏配置降级+日志,永不阻断启动。

---

## 12. _validate_gateway_config(1753-1812)

三项校验(全部**修复式**,不抛):
1. `at_hour` 出 0-23 → warning + 回 4(1761-1765);`idle_minutes` 非正 → warning + 回 1440(1767-1772)。
2. 空 token 警告(1774-1786):enabled 且 token 为空白字符串的 token-平台
   (查 `PLATFORM_TOKEN_ENV_NAMES`)打 warning 指出 env 名——"adapter will likely fail to connect",
   没有这行日志用户很难定位。
3. **占位 token 拒启**(1788-1812,自 openclaw/openclaw#64586 移植):
`gateway/config.py:1804-1812 @ 863e313`
```python
            token = pconfig.token
            if token and token.strip() and not has_usable_secret(token, min_length=4):
                logger.error(
                    "%s is enabled but %s is set to a placeholder value ('%s'). "
                    "Set a real bot token before starting the gateway. "
                    "The adapter will NOT be started.",
                    platform.value, env_name, token.strip()[:6] + "...",
                )
                pconfig.enabled = False
```
事故背景:用户照抄 `.env.example` 不改占位值,得到的是平台 API 一句迷惑的 "auth failed";
现在启动期识别已知弱占位(`has_usable_secret`)、log error(token 只露前 6 字符)并**就地禁用**
该平台(改 config 对象,不改文件)。`has_usable_secret` import 失败则跳过本项(1792-1795)。

---

## 13. _apply_env_overrides(1815-2688)——env 发现与自动启用

结构:内置平台逐段硬编码(1837-2512)→ session env(2499-2512)→ registry 驱动的插件平台
启用 pass(2514-2666)→ Relay(2668-2685)→ 哨兵清理(2687-2688)。全程用 `_getenv_str/_getenv_int`
(scope 感知,§1.7)。

### 13.1 `_enable_from_env` 与 `_enabled_explicit` 协议(1820-1835)

`gateway/config.py:1820-1835 @ 863e313`
```python
    def _enable_from_env(platform: Platform) -> PlatformConfig:
        if platform not in config.platforms:
            config.platforms[platform] = PlatformConfig(enabled=True)
            return config.platforms[platform]

        platform_config = config.platforms[platform]
        # Read (don't pop) the explicit-enable marker: the registry-driven
        # plugin-enable pass later in this function also needs it to avoid
        # re-enabling a platform the user explicitly disabled (migrated plugin
        # platforms — telegram, matrix — flow through here too, #41112). The
        # flag is cleared once for all platforms in the final cleanup at the
        # end of _apply_env_overrides.
        enabled_was_explicit = bool(platform_config.extra.get("_enabled_explicit", False))
        if not platform_config.enabled and not enabled_was_explicit:
            platform_config.enabled = True
        return platform_config
```
协议:env 里发现凭据 → 平台不存在则创建并启用;已存在且 `enabled=False` 时,只有**非**显式禁用
才自动启用——`telegram.enabled: false` + `TELEGRAM_BOT_TOKEN` 共存时尊重禁用(#41112)。
标记**读不 pop**(后面的插件 pass 还要用),统一在函数末尾清:
`gateway/config.py:2687-2688 @ 863e313`
```python
    for platform_config in config.platforms.values():
        platform_config.extra.pop("_enabled_explicit", None)
```
(哨兵是内部协议,不能漏进 to_dict/adapter 可见的 extra。)

### 13.2 内置平台逐段(选讲差异点;全部模式为"凭据齐→enable+填 extra;HOME_CHANNEL 三件套")

- **Telegram**(1837-1865):token→enable;`TELEGRAM_REPLY_TO_MODE`(off/first/all)与
  `TELEGRAM_FALLBACK_IPS`(逗号列表)即使平台未启用也写入(创建 disabled 的 PlatformConfig)。
- **Discord**(1867-1887):同构。
- **WhatsApp**(1889-1909):无凭据可探(Baileys 扫码会话),用 `WHATSAPP_ENABLED` 布尔;
  显式 false/0/no → 强制禁用,truthy → 启用,其他 → 保持 YAML(1890-1899 三态)。
- **WhatsApp Cloud**(1911-1964):官方 Meta Business API,与 Baileys 桥**可并行**跑不同号码
  (1912-1914 注释);需 phone_number_id+access_token 双全;可选 app_id/app_secret(签名校验)、
  waba_id、verify_token、webhook host/port/path、api_version。
- **Slack**(1966-2005):token 存在时,若 YAML 显式禁用则**只存 token 不启用**——
  "Token is still stored so skills that send Slack messages can use it without activating the
  gateway adapter"(1986-1988);顶层 Slack 设置(channel prompts)不该让 env-token 安装变禁用
  (1982-1984)。home channel 更换时 provenance 保留规则见 §4。
- **Signal**(2007-2024):`SIGNAL_HTTP_URL`+`SIGNAL_ACCOUNT` 双全;`ignore_stories` 默认 true。
- **Mattermost**(2026-2042):token→enable,URL 缺失打 warning(仍启用,让 adapter 报具体错)。
- **Matrix**(2044-2078):token **或** password 任一触发;e2ee 模式解析
  (`required/require/optional/prefer/preferred` 或 `MATRIX_ENCRYPTION` truthy → encryption=True)。
- **HASS/Email/SMS**(2080-2128):HASS token;Email 四件套 `all([...])` 才启用(地址/密码/IMAP/SMTP);
  SMS 用 `TWILIO_ACCOUNT_SID` 触发、auth token 存 `api_key`(注意:Email 的密码**不**存进 extra,
  只存 address/imap_host/smtp_host,2100-2104——密码留在 env 由 adapter 自取)。
- **API Server**(2130-2171):详见下。
- **Webhook**(2173-2187):`WEBHOOK_ENABLED` truthy 触发;port int 化失败静默丢。
- **MSGraph webhook**(2189-2239):触发条件宽——enabled **或平台已在配置** 或任一相关 env 在
  (2197-2204),因为 client_state/resources/cidrs 可能要在 YAML-enabled 的平台上补充。
- **DingTalk**(2241-2259)、**Feishu**(2261-2287,connection_mode 默认 websocket——联动 §3 条件端口)、
  **WeCom**(2289-2310)、**WeCom callback**(2312-2330):后者 host 显式无默认——
  `gateway/config.py:2325-2329 @ 863e313`
```python
            # No default here: an unset WECOM_CALLBACK_HOST leaves extra.host
            # falsy so the adapter's dual-stack DEFAULT_HOST=None applies
            # (binds IPv4 + IPv6; "0.0.0.0" was IPv4-only, NS-603).
            "host": getenv("WECOM_CALLBACK_HOST", ""),
            "port": getenv_int("WECOM_CALLBACK_PORT", 8645),
```
  (NS-603:曾默认 "0.0.0.0" 导致 IPv6-only 环境收不到回调。)
- **Weixin**(2332-2372):token **或** account_id 任一即启用(连接判定仍要求双全,§9);
  base_url/cdn_base_url 去尾斜杠;dm/group policy、allow_from 等全进 extra。
- **BlueBubbles**(2374-2412):server_url+password;`mention_patterns` 先试 JSON 解析,
  失败落回逗号/换行分隔(2396-2403)。
- **QQBot**(2414-2454):`QQ_HOME_CHANNEL` 更名 `QQBOT_HOME_CHANNEL` 的向后兼容+弃用 warning
  (2434-2443)。
- **Yuanbao**(2456-2497):`YUANBAO_APP_ID` 优先、`YUANBAO_APP_KEY` 兼容(2457)。

### 13.3 API Server 段与 multiplex 二级 profile 守卫(2130-2171)

`gateway/config.py:2135-2155 @ 863e313`
```python
    # Require a usable key: API_SERVER_ENABLED alone would load an
    # unauthenticated platform whose adapter refuses to start at connect()
    # anyway (startup guard in gateway/platforms/api_server.py), leaving the
    # reconnect watcher spinning and logging errors forever. Same strength
    # bar as the startup guard (has_usable_secret, min_length=16).
    if _has_usable_api_server_key(api_server_key):
        if Platform.API_SERVER not in config.platforms:
            config.platforms[Platform.API_SERVER] = PlatformConfig()
        # Respect an explicit ``enabled: false`` in config.yaml (flagged by
        # ``_enabled_explicit``). In multiplex mode a secondary profile's
        # config.yaml pins ``platforms.api_server.enabled: false`` so it shares
        # the default profile's listener instead of binding its own port. That
        # profile still inherits the process-level env (including
        # ``API_SERVER_KEY``); without this guard the env-var presence would
        # force-enable the listener and trip the MultiplexConfigError check.
        # Pop (don't read) the marker — the api_server branch is terminal (no
        # later registry pass re-enables it), so this both consumes the flag and
        # avoids reading it twice, matching the pop convention used elsewhere.
        api_server_explicit = config.platforms[Platform.API_SERVER].extra.pop("_enabled_explicit", False)
        if not api_server_explicit or config.platforms[Platform.API_SERVER].enabled:
            config.platforms[Platform.API_SERVER].enabled = True
```
两层因果:①仅 `API_SERVER_ENABLED` 无 key → adapter connect() 拒启 → reconnect watcher 永转,
所以 enable 门槛=可用 key(与启动守卫同强度,§9);②multiplex 下二级 profile 继承进程级 env
(含 API_SERVER_KEY),若 env 强制启用会撞 §3 的 SecondaryPortBindingConfigError——
显式 `enabled: false` 必须赢过 env key 存在。此处 pop(而非读)标记:api_server 分支是终端分支,
后续 registry pass 不会再碰它。

### 13.4 registry 驱动的插件平台启用 pass(2514-2666)

**问题演化(三个事故叠出来的形状)**:
1. 初版:对每个注册插件平台跑 `check_fn()`(SDK 可导入?),True 即 enable。
   → 事故 #31116:adapter 插件的 check_fn 只验 SDK 可装,不验用户配了凭据;于是 Discord/Teams/
   Google Chat 在用户从未 opt-in 的情况下被静默启用,无 token 连接、retry-forever 刷错。
   修复:先问 `is_connected`(凭据配好了吗),过了才 enable(`_platform_status` 曾修过同类 bug,
   commit 7849a3d73,这是运行时对应面)。
2. 事故(desktop 卡 94% boot-loop,2625-2634 注释):check_fn 对 adapter 插件会**顺手 pip 安装** SDK;
   把它无条件扫全部平台,`load_gateway_config()` 每次调用都 pip 装 Discord/Telegram/Slack/Feishu/
   Dingtalk——包括 dashboard 就绪探针 `GET /api/status` 的同步等待路径,装完前 desktop 超时循环重启。
   修复:check_fn 挪到**最后**,只对已启用或已过凭据门的平台跑(2625-2640)。
3. Google Chat 的凭据在 env 而 `is_connected` 读 `config.extra` → env-only 安装过不了门。
   修复:先调 `env_enablement_fn()` 拿 seed,叠在 probe 配置上再问 is_connected(2556-2610)。

关键代码,探针配置构造(2579-2611):
`gateway/config.py:2579-2597 @ 863e313`
```python
            if existing_cfg is None or not existing_cfg.enabled:
                if entry.is_connected is not None:
                    try:
                        # Probe with ``enabled=True`` since we're asking
                        # "would this plugin BE configured if we enabled
                        # it?" not "is it currently enabled?". Google
                        # Chat's ``_is_connected`` short-circuits on
                        # ``config.enabled`` being False, which on the
                        # default ``PlatformConfig()`` would fail the
                        # gate even with proper env vars set.
                        if existing_cfg is not None:
                            probe_cfg = existing_cfg
                            if not probe_cfg.enabled:
                                probe_cfg = PlatformConfig(
                                    enabled=True,
                                    extra=dict(probe_cfg.extra or {}),
                                )
                        else:
                            probe_cfg = PlatformConfig(enabled=True)
```
探针必须 `enabled=True`(问的是"若启用会不会配置齐",不是"现在启用没");seed 以 `setdefault`
叠加且**不 mutate** existing_cfg(2598-2610);`home_channel` 不进 probe extra(2604-2605)。
显式禁用直接 continue(2550-2555,查 `_enabled_explicit`)。最终顺序:显式禁用检查 →
env_enablement_fn(seed)→ is_connected(凭据门)→ check_fn(依赖/SDK,可能 pip 装)→
enable + seed 落盘(2641-2664,home_channel dict 转正为 HomeChannel dataclass)。
整个 pass 包 try/except debug(2665-2666)。

**重实现要点(自动启用)**:①"能装 SDK"≠"用户配置了"≠"已启用",三个谓词分开;
②有副作用的检查(pip install)必须放在所有零副作用门之后;③探针配置与真实配置分离,
探针按"假设已启用"构造;④用户显式禁用是最高优先级,任何自动化不得翻转;
⑤seed 数据一次求值多处复用(probe 与 commit 用同一份,2644-2646)。

### 13.5 Relay(2668-2685)与收尾

`GATEWAY_RELAY_URL`(env,注意这里用裸 `os.getenv`,2677——Relay 是进程级 ingress,
**刻意**不走 profile scope)或已有 extra.relay_url(YAML 经 from_dict 进来的);任一存在即
`_enable_from_env(Platform.RELAY)` 并把 URL(去尾斜杠)镜像进 `extra["relay_url"]`
(连接判定 §9 键着它)。2668-2676 注释:adapter 由 gateway 启动时注册进 registry
(gateway.relay.register_relay_adapter),出站拨号无入站端口,只需 present+enabled 即可被
start_gateway() 的连接循环拉起。

### 13.6 session env(2499-2512)

`SESSION_IDLE_MINUTES`/`SESSION_RESET_HOUR` 覆盖 default_reset_policy 对应字段,int 化失败静默。
注意顺序:发生在 `_validate_gateway_config` **之前**(load_gateway_config 1745-1748),
所以 env 给的坏值(如 25 点)也会被校验修复。

---

## 14. 与 gateway/run.py load_gateway_config_for_runner 的关系(run.py:1974-2006)

`gateway/run.py:1974-2006 @ 863e313`
```python
def load_gateway_config_for_runner() -> "GatewayConfig":
    """Load gateway config for the process-level GatewayRunner.

    When ``gateway.multiplex_profiles`` is off, this is identical to
    ``load_gateway_config()`` (legacy single-profile path).

    When multiplexing is on, reload under the default/active profile's
    ``_profile_runtime_scope`` so platform tokens in that profile's ``.env``
    resolve through the secret scope — the same path secondary profiles use
    in ``_start_one_profile_adapters``. Without this, primary startup calls
    ``load_gateway_config()`` unscoped: ``_getenv`` falls through to
    ``os.environ``, which often has no ``TELEGRAM_BOT_TOKEN`` once the token
    lives only under ``profiles/<name>/.env`` (#64674).
    """
    cfg = load_gateway_config()
    if not getattr(cfg, "multiplex_profiles", False):
        return cfg
    try:
        home = get_hermes_home()
    except Exception:
        return cfg
    try:
        with _profile_runtime_scope(Path(home)):
            return load_gateway_config()
    except Exception:
        logger.debug(
            "multiplex default-scope config reload failed; using unscoped load",
            exc_info=True,
        )
        return cfg
```
**两阶段装载**:第一遍无 scope 装载,只为读出 `multiplex_profiles` 开关(开关本身在 config.yaml/
进程 env,不需要 scope);若开,则进 `_profile_runtime_scope`(run.py:1937-1971:
`set_hermes_home_override` + `hydrate_profile_secret_sources` + `set_secret_scope`,见 §1.7)
**重装一遍**——这次 `_getenv` 走 profile 的 `.env` secret scope,主 profile 的 bot token 才解析得到
(#64674:token 只在 `profiles/<name>/.env` 时,unscoped 装载读 os.environ 落空,平台被
credential gate 跳过)。失败任何一步都回落第一遍结果(fail-open)。
消费点:`gateway/run.py:5879 @ 863e313`
```python
        self.config = config if config is not None else load_gateway_config_for_runner()
```
测试注入 `config=` 时完全绕过。随后 5886 `set_multiplex_active(...)` 把进程标成 multiplexer,
使 `agent.secret_scope.get_secret` 对**无 scope 的凭据读取 fail-closed**(漏迁移的读法大声崩,
不静默跨 profile 泄漏)。二级 profile 的对称路径:run.py:13272-13275
(`_start_one_profile_adapters` 在各自 `_profile_runtime_scope(profile_home)` 里调
`load_gateway_config()`)。
**设计理由**:config.py 保持"scope 在则用 scope"的被动感知,**由调用方决定 scope**;
runner 包装函数补上"主 profile 也要 scope"这一环,而不把 profile 概念倒灌进 config.py。

---

## 15. 文档-代码冲突候选(▲=冲突,◇=文档缺失/含糊)

1. ◇ **transport 取值文档不全**:`website/docs/user-guide/configuration.md:1914 @ 863e313`
   写 `transport: auto — "auto" (default) | "edit" (progressive message editing) | "off"`,
   未列代码支持的 `"draft"`(`gateway/config.py:728-729`);`mode` 别名(768-797,隐含 enabled 的
   人机工学入口)在该文档亦无记载。以代码为准:四值 + mode 别名。
2. ▲ **装载优先级 docstring 过度简化**:`gateway/config.py:1253-1257` 声明
   "1. Environment variables 2. config.yaml 3. gateway.json 4. defaults",但**启用位**存在反例:
   config.yaml 显式 `enabled: false` 赢过 env 凭据存在(telegram/slack:1833, 1980-1985;
   api_server:2153-2155;插件 pass:2550-2555)。准确表述:值覆盖上 env 最高,
   而**启用决策**上"用户显式禁用"最高。
3. ◇ **module docstring**(1-9)仍以平台列表+四要点概括,未提 multiplex、streaming、
   插件桥接等本文件近半数内容;仅作导览,不构成行为断言。
4. ◇ `SessionResetPolicy` 文档侧(website/docs/user-guide/sessions.md:655、messaging/index.md:258)
   与代码一致(需 opt-in),无冲突;但 2026-07 前的旧默认 "both" 只留在代码注释(497-499),
   升级用户如遇行为变化,文档无迁移说明。
5. ◇ `PORT_BINDING_PLATFORM_VALUES` 含 `"line"`(393)——LINE 是插件平台,清单本身在核心;
   插件新增绑端口平台时需要**手改核心清单**,`ADDING_A_PLATFORM.md` 未提及此步(检查
   `gateway/platforms/ADDING_A_PLATFORM.md:30` 一带只讲 apply_yaml_config_fn)。潜在漂移点。

---

## 16. 全文件重实现要点总表(跨机制)

1. **配置永不炸启动**:所有解析 fail-open(coerce 降级、大 try 包 YAML、插件 hook 吞异常),
   校验是修复式的(改值/禁平台+日志),唯一 fail-fast 留给 multiplex 端口冲突这种"必然事故"。
2. **三态区分是纲**:未设/空/非法 vs 显式假,在 env 覆盖(multiplex 空 secret)、启用位
   (`_enabled_explicit` 哨兵)、YAML null(reset policy)三处反复出现;bool 化前先问"这里需要三态吗"。
3. **单一权威数据**:端口清单、token-env 映射、streaming 默认、watchdog 规范化——凡有两个消费点的
   策略数据/函数,一律上提为模块级公共定义,注释写明双方。
4. **判定强度对齐**:load 期的"已连接"判定必须与 adapter 启动守卫同一函数/同一阈值
   (api_server min_length=16),否则状态撕裂。
5. **自动启用的谓词分层**:显式禁用 > 凭据齐(is_connected,零副作用)> 依赖可用(check_fn,
   可能 pip 装,放最后)>启用;探针配置与真实配置分离。
6. **多租户凭据**:env 读取抽象成 scope 感知函数,scope 在则 os.environ 不可见;
   主 profile 用两阶段装载补 scope;进程打 multiplex 标后无 scope 读取 fail-closed。
7. **prompt cache 友好**:进 prompt 的派生列表(connected platforms)排序保字节稳定。
8. **内部哨兵要清场**:`_enabled_explicit` 在流程末尾统一 pop,不泄漏到运行期 extra。
