已完成全段精读与交叉核查,以下为底稿片段。

# r7 底稿片段 · gateway/run.py:1924-3670(模块级辅助·下)@ 863e313

> 本段为 `gateway/run.py` 模块级(类定义之前)的后半部分:多路复用 profile 作用域、config→env 桥、凭据解析、媒体判定、回合级看门狗、config 装载链、空响应归一、adapter 处置。第 3670 行起为 `class TurnRunner`(`gateway/run.py:3670 @ 863e313`),不在本段范围。行号均以 `@ 863e313` 为准。

## gateway/run.py:1924-2030 — 多路复用配置错误类与 profile 运行时作用域

### 机制 1:MultiplexConfigError / SecondaryPortBindingConfigError —— 配置错误与瞬态故障分类(1924-1935)

**场景/问题**:网关支持"多 profile 复用"(一个进程同时服务多套 `~/.hermes/profiles/<name>/` 配置)。secondary profile 启动失败有两类:配置写错(必须操作员修 config.yaml)与网络瞬断(可重试)。若混为一谈,配置错误会被重连循环无限重试、永不暴露。

**实现**:两个异常类作为类型标签,`MultiplexConfigError` 继承 `RuntimeError`,`SecondaryPortBindingConfigError` 再继承前者(端口绑定冲突子类)。

`gateway/run.py:1924-1934 @ 863e313`:
```python
class MultiplexConfigError(RuntimeError):
    """A profile multiplexer config is invalid.

    Distinct from a transient adapter-connect failure: a config error means the
    operator must fix config.yaml. Fatal configuration errors propagate to the
    startup guard instead of being treated as retryable adapter noise.
    """


class SecondaryPortBindingConfigError(MultiplexConfigError):
    """A secondary profile conflicts with the multiplexer's shared listener."""
```

**调用关系**:抛出点在 `_start_one_profile_adapters`:open policy 违例抛 `MultiplexConfigError`(`gateway/run.py:13278 @ 863e313`),secondary profile 配了端口绑定平台抛 `SecondaryPortBindingConfigError`(`gateway/run.py:13293-13300 @ 863e313`,错误文案明确说 default profile 独占共享 HTTP listener,secondary 经 `/p/<profile>/` URL 前缀服务)。捕获点:`gateway/run.py:13232`(先捕子类)、`13238`(再捕父类)、`11229 @ 863e313`(启动守卫)。

**设计理由与取舍**:用异常类型而非错误码字符串做分类,捕获侧可以先窄后宽两层 `except`;代价是异常类必须定义在使用点之前(所以放模块级辅助段)。

**重实现要点**:
1. 可重试与不可重试故障用不同异常类型区分,而不是靠错误消息文本匹配;
2. 配置错误必须逃逸到启动守卫使进程 fail-fast,不得进入重连退避循环;
3. 子类化(端口冲突 ⊂ 配置错误)让通用捕获自动覆盖新错误种类。

### 机制 2:_profile_runtime_scope —— 单进程内按 profile 切换 home 与凭据(1937-1971)

**场景/问题**:多路复用网关里,一条 Telegram 消息属于 profile A、下一条属于 profile B。两个 profile 各有自己的 `config.yaml`、skills、memory、`.env` 凭据。进程全局的 `os.environ` 只能装一套值,直接读它会把 A 的 API key 用到 B 的回合上。

**实现**:contextmanager 组合两个 contextvar 缝(seam):(1) `set_hermes_home_override` 重定向 `get_hermes_home()`;(2) `set_secret_scope` 把该 profile `.env` 构建的隔离 dict 装成权威凭据源。中间还调 `hydrate_profile_secret_sources` 预热该 profile 的 secret 源。

`gateway/run.py:1956-1971 @ 863e313`:
```python
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from agent.secret_scope import (
        build_profile_secret_scope,
        set_secret_scope,
        reset_secret_scope,
    )
    from hermes_cli.env_loader import hydrate_profile_secret_sources

    home_token = set_hermes_home_override(str(profile_home))
    hydrate_profile_secret_sources(Path(profile_home))
    secret_token = set_secret_scope(build_profile_secret_scope(Path(profile_home)))
    try:
        yield
    finally:
        reset_secret_scope(secret_token)
        reset_hermes_home_override(home_token)
```

docstring 三条关键约束(`gateway/run.py:1939-1955 @ 863e313`):contextvar 经 `copy_context()` 传进 agent worker 线程;单 profile 网关从不进入此作用域、行为不变;**不 mutate `os.environ`**——`build_profile_secret_scope` 返回隔离 dict,这是防止 MCP/kanban 子进程继承跨 profile 凭据的关键:

```python
    Only used on the multiplexed inbound path. Single-profile gateways never
    enter this scope, so their behavior is unchanged. Loading the profile's
    ``.env`` here does NOT mutate ``os.environ`` — ``build_profile_secret_scope``
    returns an isolated dict — which is what keeps subprocesses (MCP, kanban)
    from inheriting cross-profile secrets.
```

**调用关系**:被调方定义在 `hermes_constants.py:30/40 @ 863e313`(`set/reset_hermes_home_override`)、`agent/secret_scope.py:72/80/272 @ 863e313`(`set/reset_secret_scope`、`build_profile_secret_scope`)、`hermes_cli/env_loader.py:169 @ 863e313`(`hydrate_profile_secret_sources`)。调用方遍布 run.py:secondary profile adapter 启动(`gateway/run.py:13274、13316、13378、13434 @ 863e313`)、profile 消息处理(`13609、13620`)、入站事件(`16196、18311`)、整回合包裹(`24150`,注释见 `24132`:"run the whole turn inside `_profile_runtime_scope` so config/skills/…")。读凭据侧的配合:`gateway/config.py:234 @ 863e313` 的 `_getenv` 有 scope 就读 scope、否则回退 `os.environ`:
```python
    if current_secret_scope() is not None:
        scope_val = _get_secret(name, None)
        return scope_val if scope_val is not None else default
    env_val = os.environ.get(name)
```

**设计理由与取舍**:contextvar 而非线程局部/进程环境:异步任务和 `copy_context()` 派生线程都能继承,且单 profile 路径零开销。取舍:所有凭据读取必须经 `get_secret`/`_getenv` 这类 scope-aware 入口,任何直接 `os.getenv` 的旧代码在多路复用下会读错(见冲突候选 ▲3)。

**重实现要点**:
1. 多租户单进程 harness 的租户切换用 contextvar 双缝:数据目录重定向 + 凭据字典替换;
2. 绝不为切租户 mutate `os.environ`——子进程继承会造成跨租户凭据泄漏;
3. token-based reset(`finally` 里按 token 恢复)保证嵌套/异常路径都能正确还原;
4. 所有凭据读取收敛到一个 scope-aware 函数,禁止散落的 `os.getenv`。

### 机制 3:load_gateway_config_for_runner —— 多路复用下主 profile 配置的作用域重载(1974-2006,#64674)

**场景/问题**:#64674:开启多路复用后,平台 token 只放在 `profiles/<name>/.env` 里、不在进程 `os.environ`。主启动若直接 `load_gateway_config()`(无 scope),`_getenv` 落到 `os.environ` 找不到 `TELEGRAM_BOT_TOKEN`,主 profile 平台全部"无凭据"。

**实现**:先无 scope 加载;`multiplex_profiles` 关则原样返回(单 profile 路径零改动);开则在默认 profile 的 `_profile_runtime_scope` 内重载一次;重载失败降级回无 scope 结果并 debug 日志。

`gateway/run.py:1991-2006 @ 863e313`:
```python
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

**调用关系**:唯一调用点 `GatewayRunner.__init__`:`gateway/run.py:5879 @ 863e313` `self.config = config if config is not None else load_gateway_config_for_runner()`。docstring 明言与 secondary profile 的 `_start_one_profile_adapters` 用同一条 scoped 路径(`gateway/run.py:1981-1986 @ 863e313`)。

**设计理由与取舍**:"先探测开关、再 scoped 重载"意味着 config 加载两次——用一次冗余 IO 换取单 profile 完全不动。fail-open(重载失败用无 scope 结果)优先可用性。

**重实现要点**:
1. 新特性的配置读取路径改造,先读一次判断开关再走新路径,保旧路径字节级不变;
2. 主/从(default/secondary)租户共用同一条凭据解析路径,避免两套逻辑漂移;
3. fail-open + debug 级日志:配置加固失败不阻断启动。

### 机制 4:_platform_has_bot_credential —— 启动期凭据预检(2009-2026)

**场景/问题**:多路复用下,主进程只应启动持有凭据的平台;token 在某 secondary profile 里的平台应留给该 profile 自己在 scope 内启动,主进程若盲目启动会连不上并刷报警。

**实现**:非 token 认证平台(Signal 会话文件、端口绑定 HTTP adapter)一律返回 True 不跳过;token 平台查 `PlatformConfig.token`,再退查 `api_key`(部分 adapter 以 api_key 为主凭据)。

`gateway/run.py:2015-2026 @ 863e313`:
```python
    from gateway.config import PLATFORM_TOKEN_ENV_NAMES

    if platform not in PLATFORM_TOKEN_ENV_NAMES:
        return True
    token = getattr(platform_config, "token", None) or ""
    if isinstance(token, str) and token.strip():
        return True
    # Some adapters also accept api_key as the primary credential.
    api_key = getattr(platform_config, "api_key", None) or ""
    if isinstance(api_key, str) and api_key.strip():
        return True
    return False
```

**调用关系**:`PLATFORM_TOKEN_ENV_NAMES` 定义于 `gateway/config.py:583 @ 863e313`。两个调用点均在多路复用分支:`gateway/run.py:11063 @ 863e313`(`if _multiplex_on and not _platform_has_bot_credential(...)`,注释:secondary 会在自己的 scope 里启动这些 adapter)与 `12441`。

**重实现要点**:
1. "该平台是否 token 认证"用集中注册表(枚举→env 名映射)判定,不散落 if-else;
2. 凭据预检只做"有没有"、不做"对不对"——有效性留给连接时验证;
3. 多租户下"谁持有凭据谁启动",主进程跳过无凭据平台而非报错。

### 常量:_DOCKER_VOLUME_SPEC_RE / _DOCKER_MEDIA_OUTPUT_CONTAINER_PATHS(2029-2030)

样板级:Docker volume 规格 `host:container[:options]` 的解析正则与"媒体输出挂载点"集合 `{"/output", "/outputs"}`(`gateway/run.py:2029-2030 @ 863e313`)。唯一消费点是启动告警 `gateway/run.py:6318-6334 @ 863e313`:Docker 后端 + 消息平台启用但没有显式 host 可见输出挂载时,警告 MEDIA 文件投递可能失败(容器内路径 host 拿不到)。

## gateway/run.py:2032-2340 — 模块导入期 config.yaml → 环境变量桥

### 机制 5:presence-sensitive env 桥 + managed overlay(2032-2056)

**场景/问题**:大量下游代码(terminal 工具、agent 超时、FTS 开关……)历史上读环境变量。config.yaml 是文档化配置入口,必须在**任何 HTTP 客户端/下游模块创建之前**把 config 值灌进 env。难点一:若用带默认值合并的 loader,整个 `DEFAULT_CONFIG` 都会被导出成 env(用户没写的键也导出);难点二:管理员固定值(managed scope)必须在 env 层也生效。

**实现**:模块导入期直接执行(非函数)。用 `read_user_config_raw` 拿"用户真正写了的键",`_expand_env_vars` 展开 `${VAR}`,再叠 `managed_scope.apply_managed_overlay`。

`gateway/run.py:2036-2056 @ 863e313`:
```python
        # Presence-sensitive env bridge: raw read is deliberate — only keys the
        # user actually wrote may be bridged (a defaults merge would export the
        # whole DEFAULT_CONFIG into the env). Overlay + expansion applied below.
        from hermes_cli.config import _expand_env_vars, read_user_config_raw
        _cfg = read_user_config_raw(_config_path)
        # Expand ${ENV_VAR} references before bridging to env vars.
        _cfg = _expand_env_vars(_cfg)
        if not isinstance(_cfg, dict):
            _cfg = {}
        # Managed scope: overlay administrator-pinned values BEFORE bridging to
        # env vars, so a managed timezone / redact_secrets / max_turns / terminal
        # setting wins over the user's value at the env layer too. This bridge
        # reads config.yaml directly (not via load_config), so without the
        # overlay every HERMES_*/TERMINAL_* env var below would carry the user's
        # value even when an administrator pinned it. Fail-open via the helper.
        try:
            from hermes_cli import managed_scope
            _cfg = managed_scope.apply_managed_overlay(_cfg)
        except Exception:
            pass
```

`_hermes_home` 来自模块上文 `gateway/run.py:1822 @ 863e313`(`_hermes_home = get_hermes_home()`);被调方定义:`hermes_cli/config.py:2971`(`read_user_config_raw`)、`2546`(`_expand_env_vars`)@ 863e313。

**重实现要点**:
1. config→env 桥必须 presence-sensitive:只导出用户显式写的键,防止默认值污染 env 层;
2. 管理员覆盖(managed overlay)要在**每条**读 config 的路径上重放,包括绕过标准 loader 的快速路径;
3. `${VAR}` 展开先于桥接,env 里永远是最终值。

### 机制 6:三种优先级政策 —— fallback-only / config 权威 / env 优先(2057-2060, 2164-2221, 2258-2269;PR #18413、#19776)

**场景/问题**:PR #18413 的 60-vs-500 事故:老版 `hermes setup` 写下 `HERMES_MAX_ITERATIONS=60` 进 `.env`;后来用户在 config.yaml 改 `max_turns: 500`,但桥用了 `if X not in os.environ` 守卫,陈旧 `.env` 值静默压住新配置,用户实际被 60 轮截断。

**实现**:段内共存三种政策,逐段注释点名。(a) 顶层标量:fallback-only(`gateway/run.py:2057-2060 @ 863e313`):
```python
        # Top-level simple values (fallback only — don't override .env)
        for _key, _val in _cfg.items():
            if isinstance(_val, (str, int, float, bool)) and _key not in os.environ:
                os.environ[_key] = str(_val)
```
(b) agent.* 等:config 无条件权威(`gateway/run.py:2164-2177 @ 863e313`):
```python
        # config.yaml is the documented, authoritative source for these
        # settings — it unconditionally wins over .env values. Previously
        # the guards below read `if X not in os.environ` and let stale
        # .env entries (e.g. HERMES_MAX_ITERATIONS=60 written by an old
        # `hermes setup` run) silently shadow the user's current config.
        # See PR #18413 / the 60-vs-500 max_turns incident.
        _agent_cfg = _cfg.get("agent", {})
        if _agent_cfg and isinstance(_agent_cfg, dict):
            if "max_turns" in _agent_cfg:
                os.environ["HERMES_MAX_ITERATIONS"] = str(_agent_cfg["max_turns"])
            if "gateway_timeout" in _agent_cfg:
                os.environ["HERMES_AGENT_TIMEOUT"] = str(_agent_cfg["gateway_timeout"])
```
同政策还覆盖 `gateway_timeout_warning`/`gateway_notify_interval`/`session_stall_timeout`/`restart_drain_timeout`/`gateway_auto_continue_freshness`/`gateway_startup_restore_drain_timeout`(2176-2193)、sessions(`HERMES_CJK_FTS`、`HERMES_SEARCH_SLOW_MS`,2196-2203)、display busy_* 三项(2204-2211)、timezone(2222-2225)、security.redact_secrets(2227-2231)、gateway 媒体投递项(strict/allow_dirs/trust_recent,2232-2257)。(c) env 优先例外两处,注释都写明理由:`busy_steer_ack_enabled`("documented as an override for service managers",`gateway/run.py:2212-2221 @ 863e313`)与 `platform_connect_timeout`(#19776,`gateway/run.py:2258-2269 @ 863e313`):
```python
            # Bridge gateway.platform_connect_timeout → the internal env var the
            # connect path + Discord adapter ready-wait both read (#19776).
            # Unlike the agent.*/display.* bridges above (config-authoritative),
            # this env var is the manual-override escape hatch, so it WINS if
            # already set explicitly; otherwise config.yaml supplies the value.
            if (
                "platform_connect_timeout" in _gateway_cfg
                and not os.environ.get("HERMES_GATEWAY_PLATFORM_CONNECT_TIMEOUT", "").strip()
            ):
```

**设计理由与取舍**:同一个桥里三种政策看似不一致,实为按键分类:文档化主配置键 config 必胜(防陈旧 .env 事故);未归类顶层键保守 fallback;明文承诺给运维的 env 逃生口保 env 优先。代价是每个键的政策要靠注释维护,新增键容易选错政策。

**重实现要点**:
1. 每个配置键显式选择优先级政策并写下理由,禁止全桥一刀切 `if not in os.environ`;
2. "文档说 config.yaml 是配置入口"⇒ config 必须无条件赢过陈旧 env,否则会重演 60-vs-500 事故;
3. 给运维留 env 逃生口时,在注释与文档双侧标注"此键 env 优先"。

### 机制 7:terminal.* 桥与 cwd 特判(2061-2122)

**场景/问题**:terminal 配置是嵌套段,需映射到 `TERMINAL_*` env(30 余键,`gateway/run.py:2068-2099 @ 863e313` 的 `_terminal_env_map`)。cwd 有两个坑:占位符(`.`/`auto`/`cwd`)不该桥成字面值;`~/` 本地要展开、SSH 远端要保留(远端 shell 自己解释)。

**实现**:`gateway/run.py:2100-2122 @ 863e313`:
```python
            for _cfg_key, _env_var in _terminal_env_map.items():
                if _cfg_key in _terminal_cfg:
                    _val = _terminal_cfg[_cfg_key]
                    # Skip cwd placeholder values (".", "auto", "cwd") — the
                    # gateway resolves these to Path.home() later (line ~255).
                    # Writing the raw placeholder here would just be noise.
                    # Only bridge explicit absolute paths from config.yaml.
                    if _cfg_key == "cwd" and str(_val) in {".", "auto", "cwd"}:
                        continue
                    # Expand shell tilde in local/container cwd so subprocess.Popen
                    # never receives a literal "~/" which the kernel rejects.
                    # SSH cwd is interpreted by the remote shell, so preserve
                    # "~" / "~/..." for the SSH backend instead of expanding it
                    # to the Hermes host/container HOME (often /opt/data). Shared
                    # predicate with terminal_tool so the two sites can't drift.
                    if _cfg_key == "cwd" and isinstance(_val, str):
                        from tools.terminal_tool import _is_ssh_remote_tilde_cwd
                        if not _is_ssh_remote_tilde_cwd(_terminal_backend, _val.strip()):
                            _val = os.path.expanduser(_val)
                    if isinstance(_val, (list, dict)):
                        os.environ[_env_var] = json.dumps(_val)
                    else:
                        os.environ[_env_var] = str(_val)
```
list/dict 值 JSON 序列化(如 `docker_volumes`),消费侧再 `json.loads`(见 `gateway/run.py:6310 @ 863e313`)。SSH tilde 判定共享谓词 `tools/terminal_tool.py:1370 @ 863e313`,注释明言"Shared predicate … so the two sites can't drift"。

**重实现要点**:
1. 嵌套 config→env 用声明式映射表,新键加一行;
2. 复合值过 env 用 JSON 编码,两侧约定;
3. 占位符值不落 env,留给统一解析器;跨判定点(本地展开 vs 远端保留)抽共享谓词防漂移。

### 机制 8:auxiliary 任务桥 —— 插件可扩展的辅助模型配置(2123-2163)

**场景/问题**:vision/web_extract/approval 等辅助任务各可配 provider/model/base_url/api_key。硬编码三个任务名意味着插件注册的辅助任务享受不到 config→env 桥。

**实现**:内建集合 `{"vision", "web_extract", "approval"}` + `get_plugin_auxiliary_tasks()` 动态并集;每任务四键桥成 `AUXILIARY_<KEY_UPPER>_*`;provider 值 `auto` 视为未设。`gateway/run.py:2137-2163 @ 863e313`:
```python
            _aux_bridged_keys = {"vision", "web_extract", "approval"}
            try:
                from hermes_cli.plugins import get_plugin_auxiliary_tasks
                for _entry in get_plugin_auxiliary_tasks():
                    _aux_bridged_keys.add(_entry["key"])
            except Exception:
                # Plugin discovery failure must not break gateway startup;
                # built-in bridging stays intact.
                pass

            for _task_key in _aux_bridged_keys:
                _task_cfg = _auxiliary_cfg.get(_task_key, {})
                if not isinstance(_task_cfg, dict):
                    continue
                _prov = str(_task_cfg.get("provider", "")).strip()
                _model = str(_task_cfg.get("model", "")).strip()
                _base_url = str(_task_cfg.get("base_url", "")).strip()
                _api_key = str(_task_cfg.get("api_key", "")).strip()
                _upper = _task_key.upper()
                if _prov and _prov != "auto":
                    os.environ[f"AUXILIARY_{_upper}_PROVIDER"] = _prov
```
另有注释交代 compression 配置**不桥**(`gateway/run.py:2123-2124 @ 863e313`:run_agent.py 与 auxiliary_client.py 直读 config.yaml)。

**重实现要点**:
1. 内建清单 + 插件注册表取并集,核心不需要知道每个插件任务名;
2. 插件发现失败必须不影响内建路径(try/except 包插件枚举、不包主循环);
3. 命名规约(`AUXILIARY_<KEY>_*`)让新任务零胶水接入。

### 机制 9:桥失败从静默到 stderr 告警(2270-2287)

**场景/问题**:该桥曾是 `except Exception: pass`,部分失败被吞、.env 默默压住 config.yaml——正是 60-vs-500 类事故难排查的根因。且此时 `logger` 尚未定义(logger 在 2416 行才建),不能用日志。

**实现**:`gateway/run.py:2270-2287 @ 863e313`:
```python
    except Exception as _bridge_err:
        # Previously this was silent (`except Exception: pass`), which
        # hid partial bridge failures and let .env defaults shadow
        # config.yaml values — users observed max_turns=500 in config
        # but a 60-iteration cap in practice. Surface the failure to
        # stderr so operators see it even though `logger` is not yet
        # initialized at module-import time (logger is defined further
        # down this module).
        print(
            f"  Warning: config.yaml → env bridge failed: "
            f"{type(_bridge_err).__name__}: {_bridge_err}",
            file=sys.stderr,
        )
        print(
            "  Gateway will fall back to .env values, which may not match "
            "your current config.yaml. Run `hermes doctor` to investigate.",
            file=sys.stderr,
        )
```

**重实现要点**:
1. 模块导入期代码在 logger 初始化前失败,退到 stderr print,绝不静默;
2. 告警文案带后果说明("将回退到 .env")与自助诊断指引(`hermes doctor`);
3. fail-open(继续启动)但可见。

### 机制 10:启动杂项 —— IPv4 偏好、配置校验、quiet/exec-ask、TERMINAL_CWD 占位符解析(2289-2340)

**实现要点逐条**:(a) `network.force_ipv4` 在**任何 HTTP 客户端创建前**应用(`gateway/run.py:2289-2296 @ 863e313`,`apply_ipv4_preference(force=True)`;注意 `_cfg if '_cfg' in dir() else {}` 防 config 不存在时 NameError);(b) `print_config_warnings()`(2298-2303)与 `warn_deprecated_cwd_env_vars()`(2305-2310)各自 fail-open;(c) 网关模式硬设 `HERMES_QUIET=1`、`HERMES_EXEC_ASK=1`(2312-2316,消息平台上危险命令走交互审批);(d) TERMINAL_CWD 占位符解析(`gateway/run.py:2325-2340 @ 863e313`):
```python
_configured_cwd = os.environ.get("TERMINAL_CWD", "")
if not _configured_cwd or _configured_cwd in CWD_PLACEHOLDERS:
    _resolved_cwd = resolve_placeholder_terminal_cwd(
        configured_cwd=_configured_cwd,
        terminal_backend=os.environ.get("TERMINAL_ENV", ""),
        messaging_cwd=os.getenv("MESSAGING_CWD"),
        docker_mount_cwd_to_workspace=os.getenv(
            "TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE", "false"
        ).lower()
        in {"true", "1", "yes"},
        home_fallback=str(Path.home()),
    )
    if _resolved_cwd is None:
        os.environ.pop("TERMINAL_CWD", None)
    else:
        os.environ["TERMINAL_CWD"] = _resolved_cwd
```
三分支合同(本地 vs docker 不挂载 vs docker 挂载)外置到 `gateway/cwd_placeholder.py:19 @ 863e313`(`CWD_PLACEHOLDERS` 定义在其 12 行);`None` 表示"删掉 env 让下游用自身默认"。`MESSAGING_CWD` 是向后兼容回退。

**重实现要点**:
1. 网络栈偏好(IPv4)必须在首个 client 构造前生效——放模块导入期;
2. 占位符解析结果三态:具体路径 / None(删除让下游默认),单独文件承载合同便于测试;
3. 平台运行模式(quiet、exec 审批)在入口一次性硬设,不依赖用户配置。

## gateway/run.py:2342-2416 — 导入块(样板)

纯样板:从 `gateway.config`(2342-2350,含 `ChannelOverride`、`Platform`、`_getenv`)、`gateway.session`(2351-2363)、`gateway.delivery`(2364-2368)、`gateway.turn_lease`(2369)、`gateway.session_state`(2370-2375,含 `_SERVICE_TIER_UNSET`)、三个 Mixin(2376-2378:authz/kanban_watchers/slash_commands)、`gateway.turn_context`(2379)、`gateway.platforms.base`(2380-2390,含 `MessageEvent`、`MessageType`、`merge_pending_message_event`)、`gateway.shutdown_watchdog`(2391-2398)、`gateway.restart`(2399-2406)、`gateway.whatsapp_identity`(2409-2413)导入;`logger = logging.getLogger(__name__)` 在 `gateway/run.py:2416 @ 863e313`。这些名字标定了本文件与簇内其余文件的静态依赖面。

## gateway/run.py:2419-2508 — own_policy 启动违例与会话状态注册表常量

### 机制 11:_own_policy_open_startup_violation —— open 策略双重确认启动守卫(2419-2458)

**场景/问题**:WeCom/微信/元宝/QQ/WhatsApp 这类自有(own)平台若 `dm_policy`/`group_policy` 配成 `open`(任何人可用),等于把带工具执行能力的 agent 暴露给全网。必须强制显式 allow-all 双确认,否则拒绝启动。

**实现**:`_OWN_POLICY_OPEN_ENV` 表(`gateway/run.py:2419-2425 @ 863e313`)给每个平台三元组 `(dm_env, group_env, allow_all_env)`(QQBot 无 per-policy env,只有 `QQ_ALLOW_ALL_USERS`)。检查函数遍历启用平台,策略取 `extra` dict 优先、env 兜底(默认 `pairing`);任一策略为 `open` 时要求 `GATEWAY_ALLOW_ALL_USERS` 或平台专属 allow-all 至少一个开启,否则返回违例字符串。

`gateway/run.py:2437-2458 @ 863e313`:
```python
        extra = getattr(platform_config, "extra", None) or {}
        dm_policy = str(
            extra.get("dm_policy")
            or (_getenv(dm_env, "pairing") if dm_env else "pairing")
        ).strip().lower()
        group_policy = str(
            extra.get("group_policy")
            or (_getenv(group_env, "pairing") if group_env else "pairing")
        ).strip().lower()
        if dm_policy != "open" and group_policy != "open":
            continue
        gateway_allow_all = os.getenv(
            "GATEWAY_ALLOW_ALL_USERS", ""
        ).lower() in {"true", "1", "yes"}
        platform_opted_in = gateway_allow_all or (
            allow_all_env
            and _getenv(allow_all_env, "").lower() in {"true", "1", "yes"}
        )
        if platform_opted_in:
            continue
        return f"{platform.value}: open policy without allow-all opt-in"
    return None
```

**调用关系**:两个调用点。(1) 主启动守卫 `gateway/run.py:10893-10913 @ 863e313`:违例则 `write_runtime_status(gateway_state="startup_failed", ...)` + `self._request_clean_exit(reason)`,拒绝启动;(2) secondary profile 启动 `gateway/run.py:13274-13283 @ 863e313`,在 `_profile_runtime_scope` 内检查,违例升格为 `MultiplexConfigError`。

**设计理由与取舍**:返回值设计成"违例原因字符串或 None"而非布尔,调用侧可直接入日志/状态文件;原因串以 `platform.value:` 开头,主守卫借此反查 `_OWN_POLICY_OPEN_ENV` 拼出精准提示(10895-10900)。取舍:字符串协议脆弱(靠 `split(":", 1)`),但避免引入新数据类。

**重实现要点**:
1. "全开放"类危险配置用**双开关**(全局 + 平台级)确认,缺一即 fail-fast 拒绝启动;
2. 守卫返回可读原因串,同一函数服务单租户 fail-fast 与多租户异常升格两种消费方式;
3. 策略读取顺序 config extra → env → 安全默认(`pairing`),默认值必须是安全侧。

### 机制 12:_AGENT_PENDING_SENTINEL —— 关闭 async 窗口期的占位哨兵(2461-2465)

**场景/问题**:会话开始处理到真正创建 agent 之间有 await 间隙;第二条同会话消息若在此间隙到达,"already running" 守卫查 `_running_agents` 会误判空闲,并发起第二个 agent。

**实现**:`gateway/run.py:2461-2465 @ 863e313`:
```python
# Sentinel placed into _running_agents immediately when a session starts
# processing, *before* any await.  Prevents a second message for the same
# session from bypassing the "already running" guard during the async gap
# between the guard check and actual agent creation.
_AGENT_PENDING_SENTINEL = object()
```

**调用关系**:占位写入在 claim 点 `gateway/run.py:15685 @ 863e313`(`_claim_state.turn.agent = _AGENT_PENDING_SENTINEL`)与 resume 路径 `10559`;30+ 消费点全部形如 `agent is not _AGENT_PENDING_SENTINEL`(如 8502、8574、9245、14269 等)区分"占位中"与"真 agent 实例"。

**重实现要点**:
1. check-then-act 的 async 间隙用哨兵对象在**首个 await 之前**占坑;
2. 哨兵用 `object()` 单例 + `is` 判等,不用 None(None 已表示"无");
3. 所有读取方必须显式排除哨兵——这是该模式的维护成本,宜封装成谓词。

### 机制 13:_CONVERSATION_SCOPED_STATE + _UNSET —— 会话边界清理注册表(2467-2508;#48031 等)

**场景/问题**:历史上每个会话边界(/new、/resume、自动重置……)各自手抄一份"要 pop 的 per-session dict 清单",每加一个新 dict 就漂移一次——#48031、#58403、#10702、#35809 全是"边界 X 忘了清 dict Y"型 bug(如 /new 清了 /model override 却没清 --once 恢复快照)。

**实现**:状态本体已迁入 `SessionState.conversation`(`gateway/session_state.py`),边界经 `ConversationState.clear()` 结构化清理;此元组保留两个职责:(a) 尚未迁入的 plain-dict 存储(`_pending_model_notes`);(b) 测试公共契约。`gateway/run.py:2490-2505 @ 863e313`:
```python
_CONVERSATION_SCOPED_STATE: tuple = (
    "_session_model_overrides",
    "_pending_one_turn_model_restores",
    "_session_reasoning_overrides",
    "_session_service_tier_overrides",
    "_pending_model_notes",
    "_last_resolved_model",
    "_queued_events",
    # Stall-watchdog "already notified" latch (#72016). Cleared on /new so a
    # fresh conversation can warn again if it later stalls with pending inbound.
    "_session_stall_notified",
    # Staged-but-never-consumed sidecar notes (turn aborted between staging
    # and run_sync) must not leak into a future conversation's first user
    # message — session keys are source-derived and REUSED.
    "_pending_turn_sidecar_notes",
)
```
前置注释(2479-2489)显式列出**不在**清单里的四类状态及理由:turn-scoped 的 `_running_agents` 等归 `_release_running_agent_state`;`_session_run_generation` 单调递增按设计不清(清了会破坏 stale-run 检测,#28686);`_agent_cache` 有自己的驱逐路径;审批类状态归 `_clear_session_boundary_security_state`。消费点:唯一漏斗 `_clear_conversation_scope`(`gateway/run.py:22961-22964 @ 863e313`)遍历元组按 session_key pop,且 `isinstance(store, dict)` 守卫跳过已迁入 SessionState 的 MutableMapping 视图(22956-2960 注释)。`_UNSET = object()`(`gateway/run.py:2508 @ 863e313`)是"调用方没传 metadata"与"传了 None"的区分哨兵,消费点如 `21794/21817`。

**设计理由与取舍**:注册表 + 单漏斗把 O(边界数×dict 数) 的维护面压成 O(dict 数);"为什么不清"与"为什么清"同等重要,负清单写进注释即文档。留存元组是渐进迁移的中间态(结构化 clear 为主、元组为遗留兜底),两套机制并存有认知成本。

**重实现要点**:
1. 多生命周期状态(turn/conversation/session/monotonic)先分类,同生命周期状态集中一个注册表 + 单一清理漏斗;
2. "不清什么、为什么"显式写成负清单,防后人"顺手清理"引入回归;
3. 结构化状态对象的 `clear()` 优于字符串属性名清单——新字段自动纳入;
4. 语义区分"未传参"与"传 None"用模块级 `_UNSET = object()` 哨兵。

## gateway/run.py:2511-2666 — 运行时凭据解析与 fallback provider

### 机制 14:_resolve_runtime_agent_kwargs(+ per-provider 变体)—— 网关创建 AIAgent 的凭据解析(2511-2601;#32790)

**场景/问题**:网关为每回合构建 AIAgent 需要 provider 凭据字典(api_key/base_url/api_mode/credential_pool…)。主 provider 认证失败时应走 fallback 链;且 429 限流型 AuthError 不能误标为"认证失败"(#32790:凭据没问题,重登无用,日志误导运维)。

**实现**:主路径 `resolve_runtime_provider()`(`hermes_cli/runtime_provider.py:1665 @ 863e313`);`AuthError` 分类日志后尝试 `_try_resolve_fallback_provider()`,失败才抛 RuntimeError。`gateway/run.py:2531-2547 @ 863e313`:
```python
    try:
        runtime = resolve_runtime_provider()
    except AuthError as auth_exc:
        # Distinguish a transient rate-limit/quota cap (credentials are fine,
        # re-auth cannot help) from a genuine auth failure (expired/revoked
        # token). Both fall through to the fallback chain, but the log message
        # must not mislabel a quota exhaustion as an auth failure (#32790).
        if is_rate_limited_auth_error(auth_exc):
            logger.warning("Primary provider rate-limited (429): %s — trying fallback", auth_exc)
        else:
            logger.warning("Primary provider auth failed: %s — trying fallback", auth_exc)
        fb_config = _try_resolve_fallback_provider()
        if fb_config is not None:
            return fb_config
        raise RuntimeError(format_runtime_provider_error(auth_exc)) from auth_exc
    except Exception as exc:
        raise RuntimeError(format_runtime_provider_error(exc)) from exc
```
max_tokens 解析三级:`HERMES_MAX_TOKENS` env → `model.max_tokens`(config)→ per-provider `max_output_tokens`(`gateway/run.py:2550-2567 @ 863e313`,注释强调全局键必须赢过 per-provider 上限)。返回九键 dict(2569-2579),含 `credential_pool`(多 key 轮换池)与 `command`/`args`(CLI 型 provider)。变体 `_resolve_runtime_agent_kwargs_for_provider(provider)`(2582-2601)带 `requested=provider` 定向解析、**不含 max_tokens 键**,服务 channel override 场景。

**调用关系**:主消费点 `gateway/run.py:7002 @ 863e313`(会话模型解析,优先级 session /model → channel_overrides → 全局,docstring 见 6940-6944)与 `18361`;per-provider 变体消费点 `7034`(channel override 指定 provider)与 `22725`。7003 行 `runtime_kwargs.pop("model", None)` 承接 fallback 路径附带的 `model` 键。

**设计理由与取舍**:docstring 宣称 provider 读 config.yaml 单一事实源、"the gateway does not consult environment variables for behavioral config"(2514-2519),但 max_tokens 实际 env 优先(见冲突候选 ▲1)。凭据解析每回合执行(非缓存),换新鲜度(token 轮换、pool 状态)。

**重实现要点**:
1. 认证异常分"凭据坏了"与"配额限流"两类,日志文案区分——运维排障路径完全不同;
2. 主 provider 失败先走 fallback 链再报错,报错用统一格式化器给可读指引;
3. 输出上限解析定序:显式 env > 全局 config > per-provider 默认,并写明"全局必须赢";
4. 凭据解析结果用扁平 dict 契约传给 agent 构造器,新增键(如 credential_pool)向后兼容。

### 机制 15:_credential_pool_for_provider —— override 场景补配凭据池(2604-2618)

**场景/问题**:session `/model` override 存了 api_key 但没存 credential_pool(多 key 轮换池对象不可序列化进会话状态),回合恢复时需按 provider id 重新拿活的 pool。

**实现**:`gateway/run.py:2606-2618 @ 863e313`:
```python
    if not provider or not str(provider).strip():
        return None
    try:
        return _resolve_runtime_agent_kwargs_for_provider(str(provider).strip()).get(
            "credential_pool"
        )
    except Exception:
        logger.debug(
            "Failed to resolve credential pool for provider=%s",
            provider,
            exc_info=True,
        )
        return None
```

**调用关系**:`gateway/run.py:6976 @ 863e313`(session override 有 api_key 而 pool 为 None 时补配)与 `22768`。

**重实现要点**:
1. 不可序列化的运行时对象(连接池、凭据池)不入持久状态,恢复时按 id 重解析;
2. 辅助解析失败返回 None 降级单 key 模式,debug 级日志不刷屏。

### 机制 16:_try_resolve_fallback_provider —— fallback 链逐项试解析(2621-2666;#32790)

**场景/问题**:config.yaml 的 `fallback_model`/`fallback_providers` 链在主 provider 不可用时逐项尝试。两个历史坑:(a) 曾用 raw read 加载 config,漏掉管理员固定的 fallback_providers;(b) 日志曾打印**解析后**的 runtime 类别——Ollama 走 OpenAI 兼容路径会被打成 "openrouter",与运维配置矛盾(#32790)。

**实现**:`gateway/run.py:2624-2649 @ 863e313`:
```python
    try:
        # Canonical gateway loader: managed overlay + ${VAR} expansion +
        # root-model normalization now reach the fallback chain too (a raw
        # read here used to miss administrator-pinned fallback_providers).
        cfg = _load_gateway_runtime_config()
        fb_list = get_fallback_chain(cfg)
        if not fb_list:
            return None
        for entry in fb_list:
            try:
                from hermes_cli.fallback_config import resolve_entry_api_key

                runtime = resolve_runtime_provider(
                    requested=entry.get("provider"),
                    explicit_base_url=entry.get("base_url"),
                    explicit_api_key=resolve_entry_api_key(entry),
                )
                # Log the literal `provider` key from config, not the resolved
                # runtime category — an Ollama fallback resolves through the
                # OpenAI-compatible path and would otherwise be logged as
                # "openrouter", contradicting the operator's config (#32790).
                logger.info(
                    "Fallback provider resolved: %s model=%s",
                    entry.get("provider") or runtime.get("provider"),
                    entry.get("model"),
                )
```
成功即返回带 `"model": entry.get("model")` 的 dict(2650-2660);单项失败 debug 日志后 continue(2661-2663);外层 `except Exception: pass` 整体 fail-open 返回 None。

**调用关系**:`get_fallback_chain` 定义 `hermes_cli/fallback_config.py:80 @ 863e313`、`resolve_entry_api_key` 同文件 14 行;唯一调用点 `gateway/run.py:2542 @ 863e313`。网关内另有直接用 `get_fallback_chain` 的兄弟站点(`8408`、`8459`)。

**重实现要点**:
1. fallback 链配置必须过与主配置同一条规范化管线(overlay/展开/归一),raw read 是伏笔;
2. 日志打印**操作员写的** provider 名,不打运行时解析类别——日志是给配置者看的;
3. 链式尝试:单项失败静默 continue,全链失败返回 None 让上层决定报错文案;
4. fallback 命中要附带 model 覆盖,上游用 `pop("model")` 承接。

## gateway/run.py:2669-2830 — 媒体类型判定、占位符与音频探测

### 机制 17:per-attachment MIME 优先的媒体类型判定(2669-2718)

**场景/问题**:一条消息可带多附件;部分平台只给消息级类型(如 PHOTO)不给逐附件 MIME。若按消息级类型路由,与图片同发的 PDF 会被当图片 base64 进 vision 内容块,provider 直接 400("Could not process image")。

**实现**:四个谓词共用取值器 `_event_media_type_at`(`gateway/run.py:2669-2676 @ 863e313`,越界/缺失返回空串)。判定次序:逐附件 MIME 存在则前缀匹配,否则才回退消息级类型。`gateway/run.py:2679-2691 @ 863e313`:
```python
def _event_media_is_image(event, index: int) -> bool:
    """True if the attachment at *index* is an image.

    Trust the per-attachment MIME when present. Only fall back to the
    message-level ``PHOTO`` type when this attachment's MIME is unknown --
    otherwise a document (or any non-image) uploaded alongside an image in
    the same message gets mis-routed as an image, base64'd into a vision
    content part, and the provider 400s ("Could not process image").
    """
    mtype = _event_media_type_at(event, index)
    if mtype:
        return mtype.startswith("image/")
    return getattr(event, "message_type", None) == MessageType.PHOTO
```
`_event_media_is_audio`(2694-2699)、`_event_media_is_video`(2713-2718)同构。`_event_media_is_stt_input`(2702-2710)另加一层:`AUDIO`/`DOCUMENT` 消息类型显式**排除**自动语音转写(用户发音频文件≠语音留言),只有 `VOICE` 或 MIME `audio/*` 进 STT 管线:
```python
    message_type = getattr(event, "message_type", None)
    if message_type in {MessageType.AUDIO, MessageType.DOCUMENT}:
        return False
    return (
        message_type == MessageType.VOICE
        or _event_media_type_at(event, index).startswith("audio/")
    )
```

**调用关系**:消费点在附件预处理主循环 `gateway/run.py:15863/15869/16012-16014 @ 863e313`、STT 路径 `21711`、占位符构建 2732-2737。

**重实现要点**:
1. 附件路由以逐附件 MIME 为第一优先,消息级类型只作该槽位 MIME 缺失时的回退;
2. "语音留言"与"音频文件"是不同意图,用消息类型显式区分,避免把播客文件塞进 STT;
3. 类型判定收敛为纯谓词函数(event, index),预处理循环与占位符构建复用同一套。

### 机制 18:_build_media_placeholder —— 无文字媒体消息的占位文本(2721-2740)

**场景/问题**:agent 忙时到达的照片/文件被排队,稍后 dequeue 只取 `.text`;无 caption 的媒体会被静默丢失。

**实现**:按逐附件类型生成 `[User sent an image: {url}]` 等行,`\n` 连接(`gateway/run.py:2729-2740 @ 863e313`)。docstring 言明该占位符会被 vision 富化管线替换为真实描述(2726-2728)。

**调用关系**:6 个消费点,全部是"排队/中断事件转下一用户回合"的路径:`gateway/run.py:9021、14952、24947、25229、25331、25517、25519 @ 863e313`。

**重实现要点**:
1. 排队通道若只保文本,媒体必须先物化为带 URL 的占位文本,后续管线可再富化;
2. 占位格式统一(`[User sent X: url]`),下游富化按模式识别替换。

### 机制 19:_build_document_context_note —— 文档附件的行为引导注记(2743-2767)

**场景/问题**:早期文案让 agent"问用户想对文件做什么",模型照做把问题踢回用户——用户观感是"附的 PDF/DOCX agent 读不了",尽管它有 terminal/OCR 工具能读。提示词措辞直接决定行为。

**实现**:`text/*` 文档(内容已由 adapter 上游内联)只确认+记路径;二进制文档明确指示"自己抽取文本再回答,不要让用户粘贴"。`gateway/run.py:2755-2767 @ 863e313`:
```python
    if mtype.startswith("text/"):
        return (
            f"[The user sent a text document: '{display_name}'. "
            f"Its content has been included below. "
            f"The file is also saved at: {agent_path}]"
        )
    return (
        f"[The user sent a document: '{display_name}'. It is saved at: {agent_path}. "
        f"Its text is not inlined here (it's a binary format such as PDF or DOCX). "
        f"To read it, extract the document's text yourself — for example with the "
        f"terminal tool or the ocr-and-documents skill — before answering, instead "
        f"of asking the user to paste the contents.]"
    )
```

**调用关系**:唯一消费点 `gateway/run.py:16042 @ 863e313`(附件预处理)。

**重实现要点**:
1. 注入 prompt 的系统注记要写**行动指令**("先抽取再回答")而非开放式建议("问问用户")——后者会诱导模型punt;
2. 注记里给出具体工具/技能名,缩短模型的工具选择路径;
3. 文本可内联与二进制不可内联走不同文案,并总是附上落盘路径。

### 机制 20:_format_duration / _probe_audio_duration —— 三级降级的音频时长探测(2770-2820)

**场景/问题**:STT 关闭时,语音留言要显示成 `[voice message: path (duration: M:SS)]`,时长探测不能拖死事件循环、不能因缺依赖失败。

**实现**:三级降级,全部 best-effort:.wav 用标准库 `wave`(经 `asyncio.to_thread`);.ogg/.opus/.oga 用 `mutagen.oggopus`;兜底 `ffprobe` 子进程,`wait_for(..., timeout=5.0)`。`gateway/run.py:2808-2820 @ 863e313`:
```python
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0:
            return _format_duration(float(stdout.decode().strip()))
    except Exception:
        pass

    return None
```
`_format_duration`(2770-2778)负数钳 0,`H:MM:SS`/`M:SS` 两态。

**调用关系**:唯一消费点 `gateway/run.py:21594 @ 863e313`(STT 禁用分支,拿到时长拼注记,拿不到就省略)。

**重实现要点**:
1. 媒体元数据探测按"标准库 → 可选依赖 → 外部命令"降级,每级独立 try 静默落下一级;
2. 同步阻塞库调用一律 `to_thread`,外部命令必须带超时;
3. 返回 Optional,调用方把"无时长"设计成合法展示态。

### 机制 21:_dequeue_pending_event —— 排队跟进消息取整事件(2823-2830)

**场景/问题**:早期 dequeue 把排队消息缩成文本串,媒体元数据丢失,无法重走图片/STT/文档预处理。

**实现**:一行包装,消费并返回**完整** `MessageEvent`(`gateway/run.py:2823-2830 @ 863e313`):
```python
def _dequeue_pending_event(adapter, session_key: str) -> MessageEvent | None:
    """Consume and return the full pending event for a session.

    Queued follow-ups must preserve their media metadata so they can re-enter
    the normal image/STT/document preprocessing path instead of being reduced
    to a placeholder string.
    """
    return adapter.get_pending_message(session_key)
```

**调用关系**:被调方 `gateway/platforms/base.py:6577-6579 @ 863e313`(`self._pending_messages.pop(session_key, None)`,取即清);调用点 `gateway/run.py:25480 @ 863e313`(回合后 drain),取出后先经 `_promote_queued_event` 补位溢出队列(25487,保 FIFO),音频先转写(25507-25517)再进递归回合,文本兜底 `_build_media_placeholder`(25519)。

**重实现要点**:
1. 队列元素保持全保真事件对象直到最后一刻,文本化是消费端的降级手段不是存储格式;
2. "取即清"语义(pop)由存储方法保证,包装层只负责命名与文档化意图。

## gateway/run.py:2833-3005 — 回合放弃、进程收割与回合级不活跃看门狗

### 机制 22:中断理由常量与 _is_control_interrupt_message(2833-2838, 2988-3005)

**场景/问题**:agent 被中断时 `interrupt_message` 会作为"下一条用户消息"进入 drain 递归。但 `/stop`、超时、网关重启这类**控制流**中断的理由串不是用户话语,若被当用户消息重新喂给模型,会出现"用户说:Gateway shutting down"的荒谬回合。

**实现**:六个理由常量(`gateway/run.py:2833-2838 @ 863e313`:Stop/Reset/Timeout/SSE disconnect/Shutdown/Restart)统一定义;`_CONTROL_INTERRUPT_MESSAGES` 为其小写 frozenset(2988-2997);判定函数做空白归一后集合匹配:

`gateway/run.py:3000-3005 @ 863e313`:
```python
def _is_control_interrupt_message(message: Optional[str]) -> bool:
    """Return True when an interrupt message is internal control flow."""
    if not message:
        return False
    normalized = " ".join(str(message).strip().split()).lower()
    return normalized in _CONTROL_INTERRUPT_MESSAGES
```

**调用关系**:常量的生产端:`_abandon_timed_out_gateway_turn` 用 `_INTERRUPT_REASON_TIMEOUT`(2931)、异步超时路径 `25372`、interrupt 下发 `9248/23082`(经 `request_hard_interrupt`,定义于 `agent/interrupt_compat.py:9 @ 863e313`,新 ABI `hard_interrupt` 优先、`inspect.getattr_static` 防 MagicMock 假阳性、退老 ABI `interrupt`)。消费端:drain 判定 `gateway/run.py:25488-25497 @ 863e313`:
```python
                if result.get("interrupted") and not pending_event and result.get("interrupt_message"):
                    interrupt_message = result.get("interrupt_message")
                    if _is_control_interrupt_message(interrupt_message):
                        logger.info(
                            "Ignoring control interrupt message for session %s: %s",
                            session_key or "?",
                            interrupt_message,
                        )
                    else:
                        pending = interrupt_message
```

**设计理由与取舍**:用理由串本身当协议(生产端与判定端共享常量)而非在 result 里加 `is_control` 布尔——胜在无需改 agent result 契约;弱点是第三方若碰巧用相同文案会被误吞(集合封闭、大小写归一,风险可控)。

**重实现要点**:
1. 中断理由分两类:用户话语(应转下一回合)与控制流(应丢弃),生产/判定共享同一组常量;
2. 判定做空白折叠+小写归一,容忍传输层格式扰动;
3. 丢弃控制中断时打 info 日志留痕,静默丢弃不可接受。

### 机制 23:_reap_gateway_turn_processes —— 基线差分的孤儿进程收割(2841-2909;#76115)

**场景/问题**:回合可spawn后台进程(`background=true` 的进程**有意**跨回合存活)。回合被放弃(超时/中断)时只应杀**这个回合新建的**进程。难点:`task_id == session_id` 是会话级不是回合级,收割进行中若新回合已在同一会话开跑并spawn了自己的进程,盲杀会误伤新回合(#76115 review)。

**实现**:基线差分 + 时效闭包双保险。空 task_id 直接返回(空串会匹配所有 sessionless 进程);`is_still_current`(对开始/中断时刻 run_generation 的闭包)为假则整体跳过——新回合有自己独立快照的基线,跳过不会造成永久失收。

`gateway/run.py:2859-2873 @ 863e313`:
```python
    if not task_id:
        # ProcessSession.task_id defaults to "" for sessionless callers, so a
        # blank id would match (and kill) every unrelated empty-task process
        # instead of this turn's own. Nothing session-scoped to reap.
        return 0
    if is_still_current is not None:
        try:
            if not is_still_current():
                logger.debug(
                    "Skipping reap for turn %s (%s): a newer turn already "
                    "claimed this session; it owns its own baseline.",
                    task_id,
                    source,
                )
                return 0
```
实杀委托 `process_registry.kill_started_since(task_id, baseline, source=...)`(2885-2889);被调方 `tools/process_registry.py:1971-1989 @ 863e313`,`kill_all(exclude_ids=frozenset(baseline))` 且 `consume_output=True` 强制吞输出("abandoned-turn output must not enqueue a synthetic follow-up that revives work the timeout deliberately stopped")。异常吞掉走 logger(2890-2901,注释:跑在 detached daemon 线程上,未捕获异常只会进 `threading.excepthook` 绕过应用日志)。

**调用关系**:基线快照在回合启动处 `gateway/run.py:25132-25135 @ 863e313`(`process_registry.snapshot_running_ids(_turn_task_id)`);`_turn_is_current` 闭包构造在 `25144-25149`(封 `self._is_session_run_current(session_key, run_generation)`);调用点:`_abandon_timed_out_gateway_turn`(2936)与中断路径 fire-and-forget 线程(`23101`)。

**设计理由与取舍**:基线差分(快照豁免集)而非"给进程打回合标签"——进程注册表无需感知回合概念。时效闭包是对"task_id 粒度太粗"的补丁而非重构(把 task_id 改成回合级才是根治,取舍是兼容成本)。跳过语义安全的前提被显式论证:新回合的基线包含旧回合残留进程吗?不——新回合快照时旧进程仍在,故也在新基线的豁免集内,永远不会被新回合的收割杀掉;而旧回合跳过后这些进程确实无人收,注释的"skipping here does not leave anything permanently unreaped"指的是**新回合自己的进程**不会失管(见冲突候选 ▲6)。

**重实现要点**:
1. "杀这个回合的进程"用启动前快照 + kill-started-since 差分,不给进程打标签;
2. 清理例程必须校验自己是否仍是资源当前属主(generation 闭包),失主即弃权;
3. 空 id 匹配一切是隐形地雷——收割入口对空 id 硬拒;
4. 杀被放弃回合的进程要同时吞其输出,防"完成通知复活已死回合";
5. 跑在 daemon 线程的清理逻辑自吞异常入应用日志,不裸抛。

### 机制 24:_abandon_timed_out_gateway_turn —— 幂等的超时回合放弃(2912-2948)

**场景/问题**:同一回合的超时可能被两个独立探测器同时发现(asyncio 轮询与 daemon 线程看门狗),且可能与回合正常完成竞速。放弃动作(硬中断 + 收割)必须恰好执行一次,且不得在回合已完成后执行。

**实现**:锁内双事件检查-置位,构成一次性闸门;闸门后先 `request_hard_interrupt(agent, _INTERRUPT_REASON_TIMEOUT)` 再收割,两步各自 try 隔离。

`gateway/run.py:2921-2948 @ 863e313`:
```python
) -> bool:
    """Interrupt one timed-out turn and reap only processes it created."""
    with cleanup_lock:
        if worker_done.is_set() or timeout_fired.is_set():
            return False
        timeout_fired.set()

    agent = agent_holder[0] if agent_holder else None
    if agent is not None:
        try:
            request_hard_interrupt(agent, _INTERRUPT_REASON_TIMEOUT)
        except Exception:
            logger.debug("Timed-out agent interrupt failed", exc_info=True)

    try:
        _reap_gateway_turn_processes(
            task_id,
            process_baseline,
            source="gateway_turn_timeout",
            is_still_current=is_still_current,
        )
    except Exception:
        logger.warning(
            "Failed to reap background processes for timed-out turn %s",
            task_id,
            exc_info=True,
        )
    return True
```

**调用关系**:两条触发路径:(1) 线程看门狗 `_watch_gateway_turn_inactivity` 内联调用(2976-2985);(2) asyncio 轮询路径超时后 spawn daemon 线程执行(`gateway/run.py:25295-25308 @ 863e313`,线程名 `gateway-turn-reaper-<id>`)。`worker_done` 由 `_run_sync_with_timeout_lifecycle` 的 finally 置位(`25151-25155`),同处并清空 agent 上的属主标记(`_gateway_turn_process_task_id = ""` / `baseline = frozenset()`,25167-25170,#76115:关闭"完成后 /stop 误收割回合有意留下的后台工作"的窗口)。

**重实现要点**:
1. 多触发源的一次性清理:锁 + "完成事件/已触发事件"双检查,先到先得;
2. `worker_done` 优先于 `timeout_fired` 检查——完成先到则放弃动作彻底不执行;
3. 中断与收割分别 try,前者失败不阻断后者;
4. 返回布尔告知调用方"本次是否真的执行了放弃"。

### 机制 25:_watch_gateway_turn_inactivity —— 抗事件循环饿死的线程级回合看门狗(2951-2985;#76115、#4815)【重点】

**场景/问题**:回合超时本有 asyncio 轮询检测(`gateway/run.py:25200 起 @ 863e313`)。但 #76115:cgroup 内存回收可以把整个事件循环饿死——恰恰在最需要超时清理的时刻,负责超时的协程自己也不跑了。超时语义还必须是**不活跃**超时而非墙钟超时(#4815,`25109-25117` 注释:agent 活跃调工具可跑几小时,卡死的 API 调用/工具无活动才该杀)。

**实现**:独立 daemon **线程**(不依赖事件循环),`worker_done.wait(poll_interval)` 兼作退出条件与节拍;每拍读 `agent.get_activity_summary()["seconds_since_activity"]`,达到阈值即调 `_abandon_timed_out_gateway_turn` 并退出。

`gateway/run.py:2951-2985 @ 863e313`(全函数):
```python
def _watch_gateway_turn_inactivity(
    *,
    agent_holder,
    task_id: str,
    process_baseline,
    timeout: float,
    worker_done: threading.Event,
    timeout_fired: threading.Event,
    cleanup_lock: threading.Lock,
    poll_interval: float = 5.0,
    is_still_current: Optional[Callable[[], bool]] = None,
) -> None:
    """Thread watchdog that remains runnable when gateway asyncio is starved."""
    while not worker_done.wait(max(0.01, poll_interval)):
        agent = agent_holder[0] if agent_holder else None
        if agent is None or not hasattr(agent, "get_activity_summary"):
            continue
        try:
            idle_seconds = float(
                agent.get_activity_summary().get("seconds_since_activity", 0.0)
            )
        except Exception:
            continue
        if idle_seconds < timeout:
            continue
        _abandon_timed_out_gateway_turn(
            agent_holder=agent_holder,
            task_id=task_id,
            process_baseline=process_baseline,
            worker_done=worker_done,
            timeout_fired=timeout_fired,
            cleanup_lock=cleanup_lock,
            is_still_current=is_still_current,
        )
        return
```
细节:(a) `agent_holder` 是单元素 list——线程启动时 agent 可能尚未构造,持引用容器而非引用本体,`agent_holder[0]` 为 None 时静默跳拍;(b) 活动源 `get_activity_summary` 定义于 `run_agent.py:4001 @ 863e313`(共享活动观测契约 `last_activity_at`/`seconds_since_activity`/…);(c) 双探测器共存:本线程 + asyncio 轮询(后者在 `25293` 判 `_idle_secs >= _agent_timeout` 后也 spawn 放弃线程),幂等由机制 24 的闸门保证;(d) 启动点 `gateway/run.py:25172-25188 @ 863e313`,仅 `_agent_timeout is not None`(非 0)时启动,线程名 `gateway-turn-watchdog-<task_id[:12]>`,daemon=True;启动前注释(`25124-25129`)点明与 asyncio 的独立性:"The daemon watchdog is independent of asyncio: cgroup memory reclaim may starve the event loop that runs the normal timeout poll, but it need not also postpone cleanup until the loop recovers (#76115)"。asyncio 侧另负责用户可见部分:预警消息(`25283-25290`,"No activity for X min …")与超时诊断(`25345-25389`,读活动摘要拼 last_activity/iteration/tool 诊断行)。

**设计理由与取舍**:清理面(线程,永远可跑)与通知面(asyncio,需要 adapter/网络)分离:事件循环饿死时用户消息发不出(反正也发不出),但进程收割与 agent 中断照常执行,资源不悬挂。取舍:双探测器双倍心跳开销(每 5s 各一拍)、依赖 `Event` 的跨线程可见性;`worker_done.wait()` 兼作 sleep 使正常完成时线程即刻退出、零残留。

**重实现要点**:
1. 超时清理路径不得依赖它要拯救的执行环境——事件循环监护事件循环是自指陷阱,清理下沉到 OS 线程;
2. 超时口径用"距最后活动秒数"不用墙钟,活动打点由 agent 侧统一契约暴露;
3. 看门狗读共享可变引用用单元素容器(holder),容忍"被监护对象晚于监护者出生";
4. 通知(需网络/循环)与清理(只需线程)分面实现,故障时保清理弃通知;
5. `Event.wait(interval)` 兼作节拍与退出信号,正常完成路径零延迟回收看门狗。

## gateway/run.py:3008-3120 — skill slug 与不可用技能提示

### 机制 26:_skill_slug_from_frontmatter / _check_unavailable_skill —— 未知 /command 的可诊断降级(3008-3120)

**场景/问题**:用户敲 `/stable-diffusion-image-generation` 而该 skill 被禁用或未安装时,应回"已装但禁用,`hermes skills config` 启用"或"可装未装,`hermes skills install …`",而非笼统 "unknown command"。历史 bug:slug 曾取**目录名**,而 /command 实际按 frontmatter `name:` 归一生成——目录名与 frontmatter 名漂移的 skill(标准安装有 19 个,2026-05 统计,docstring 3018-3021)全部匹配失败,静默退化成 "unknown command"。

**实现**:`_skill_slug_from_frontmatter` 精确复刻 `agent.skill_commands.scan_skill_commands` 的归一化:frontmatter 取 `name:`(容忍 BOM、YAML 引号),`lower → 空格/下划线→连字符 → 删非[a-z0-9-] → 连字符折叠 → 去首尾`。`gateway/run.py:3049-3056 @ 863e313`:
```python
    slug = declared_name.lower().replace(" ", "-").replace("_", "-")
    # Mirror _SKILL_INVALID_CHARS and _SKILL_MULTI_HYPHEN from skill_commands
    import re as _re
    slug = _re.sub(r"[^a-z0-9-]", "", slug)
    slug = _re.sub(r"-{2,}", "-", slug).strip("-")
    if not slug:
        return None, declared_name
    return slug, declared_name
```
对照源:`agent/skill_commands.py:427-429 @ 863e313`(`cmd_name = name.lower().replace(' ', '-').replace('_', '-')` + 同两正则,常量定义 26-27 行)。`_check_unavailable_skill` 两段扫描:(1) 全部 skills 目录 rglob `SKILL.md`,slug 命中且 `declared_name in disabled`(禁用表按 frontmatter 名存,3090-3092 注释)→"已装但禁用";(2) `optional-skills` 目录命中 →"可装未装"并拼 `official/<category>/<name>` 安装路径(`gateway/run.py:3110-3117 @ 863e313`)。整体 `except Exception: pass` fail-open 返回 None。

**调用关系**:唯一调用点 `gateway/run.py:15604-15606 @ 863e313`(slash 命令处理,非活跃 skill 分支),返回消息直接作为回复;不命中再落到"genuinely unrecognized /command"警告(15607-15611 注释:不静默转发给 LLM,防模型瞎编 delegate_task)。依赖:`tools/skills_tool._get_disabled_skill_names`、`agent/skill_utils.get_all_skills_dirs/is_excluded_skill_path`、`hermes_constants.get_optional_skills_dir`(3076-3101)。

**设计理由与取舍**:选择"镜像归一化逻辑"而非"从 scan_skill_commands 导出共享函数"——两处注释互相点名(3050、3068-3071)对冲漂移风险,但复制仍是复制(见冲突候选 ▲7:无名 frontmatter 时两者行为已有分叉)。rglob 全盘扫描每次未知命令都执行,冷路径可接受。

**重实现要点**:
1. "unknown command" 前先查"存在但不可用",给出**带具体命令**的启用/安装指引——可诊断性是 UX;
2. slug 归一化必须与命令生成端逐字符一致,做不到共享函数就双向注释互指并加测试;
3. 禁用表用声明名、匹配用归一 slug——两个键空间的映射要在一处讲清楚;
4. 未识别命令拦下来警告,绝不静默转发给模型(模型会即兴发挥)。

## gateway/run.py:3123-3349 — gateway config 装载链与模型/override 解析

### 机制 27:_load_gateway_config 装载链(3123-3204;#34500)

**场景/问题**:网关为速度绕过 `load_config()` 直读 raw YAML,但 `load_config()` 附带的三样东西不能丢:mtime 缓存、managed overlay、model 键归一化。#34500:`model: {name: <id>}` 写法经 `load_config()` 正常、经网关 raw 读解析出空模型——CLI 与网关对同一份 config 行为分裂。

**实现**:辅助三件套:`_platform_config_key`(3123-3125,LOCAL→"cli" 的枚举→config 键映射)、`_teams_pipeline_plugin_enabled`(3128-3134,查 `plugins.enabled` 列表,兼容下划线/连字符两种写法)、`_gateway_config_home`(3137-3142,优先 `get_hermes_home_override()`——多路复用 scope 下自动指向 profile home,否则模块级 `_hermes_home`)。主函数三步:(1) 路径与规范位置一致则走 `read_raw_config()` 共享 mtime 缓存,否则直读(保 monkeypatch `_hermes_home` 的测试夹具);(2) 叠 managed overlay(两条路径都要,`gateway/run.py:3182-3190 @ 863e313`);(3) 重放模型键归一化:

`gateway/run.py:3193-3204 @ 863e313`:
```python
    # Canonicalize model-id aliases (model.name / model.model → model.default)
    # and migrate stale root-level provider/base_url into the model section.
    # The gateway bypasses load_config() (it reads raw YAML for speed), so the
    # normalization that load_config() applies must be replayed here or the
    # gateway would resolve an empty model for ``model: {name: <id>}`` configs
    # while the CLI resolves it correctly. See issue #34500. Fail-open.
    try:
        from hermes_cli.config import _normalize_root_model_keys
        raw = _normalize_root_model_keys(raw)
    except Exception:
        pass
    return raw
```
被调方:`hermes_cli/config.py:2933`(`read_raw_config`)、`694`(`get_config_path`)、`2746`(`_normalize_root_model_keys`)@ 863e313。

**调用关系**:run.py 内 50+ 消费点(经本函数或其包装 `_load_gateway_runtime_config`),如 `3130`、`3263`、`8012-8459` 一组运行时读取。

**设计理由与取舍**:快速路径绕过规范 loader 的代价是必须手工重放其语义(overlay、归一化)——本函数就是"重放清单"。每处重放 fail-open,坏 config 不炸网关。

**重实现要点**:
1. 性能捷径绕过规范 loader 时,列一张"规范 loader 附带语义清单"逐项重放,并在注释里挂对应事故号;
2. 缓存复用以"路径一致"为前提判定,保测试可注入;
3. 管理员覆盖必须出现在**每一条** config 读取路径上,一条漏掉就是特权绕过。

### 机制 28:_checkpoint_agent_kwargs —— checkpoint 配置翻译(3207-3233)

**场景/问题**:网关直读 raw YAML 拿不到 `load_config()` 的默认值合并;且遗留写法 `checkpoints: true`(布尔)要兼容。

**实现**:布尔升格为 `{"enabled": bool}`,非 dict 归空;逐键 `cp_cfg.get(k, DEFAULT_CONFIG["checkpoints"][k])` 落到 AIAgent 构造参数(`checkpoints_enabled`/`checkpoint_max_snapshots`/`checkpoint_max_total_size_mb`/`checkpoint_max_file_size_mb`,`gateway/run.py:3214-3233 @ 863e313`)。

**调用关系**:消费点 `gateway/run.py:4797 @ 863e313`(TurnRunner 内 `**_checkpoint_agent_kwargs(ctx.user_config)`)与 `19555`。

**重实现要点**:
1. raw 读路径的默认值显式引用 `DEFAULT_CONFIG`,与规范 loader 同源不另抄一份;
2. 配置形态演进(bool→dict)在翻译层升格兼容,下游只见 dict。

### 机制 29:_load_gateway_runtime_config —— ${VAR} 展开且不吞错(3236-3253)

**场景/问题**:运行时读取(fallback 链等)要享受文档化的 `${VAR}` 模板展开;而展开失败若被静默吞掉,返回未展开 dict 正是本函数要修的 bug 本身。

**实现**:`gateway/run.py:3246-3253 @ 863e313`:
```python
    cfg = _load_gateway_config()
    if not isinstance(cfg, dict) or not cfg:
        return {}
    from hermes_cli.config import _expand_env_vars

    expanded = _expand_env_vars(cfg)
    return expanded if isinstance(expanded, dict) else {}
```
docstring 明言:"Expansion failures are intentionally NOT swallowed — silently returning the unexpanded dict would mask the very bug this helper exists to fix"(3244-3245)。与本文件普遍 fail-open 风格刻意相反。

**调用关系**:消费点 14 处:`2628`(fallback 链)、`8012/8045/8127/8257/8271/8282/8304/8319/8340/8368/8390/8407` @ 863e313。

**重实现要点**:
1. fail-open 不是教条:当"吞错的结果恰好复现待修 bug"时必须让异常传播,并写明这是故意的;
2. 展开层叠在基础 loader 之上而非并列实现,保两者行为对齐。

### 机制 30:_resolve_gateway_model —— 模型单一事实源(3256-3269)

**场景/问题**:临时 AIAgent(如 /compress)若落到硬编码默认模型,在 openai-codex 等 provider 下直接失败——模型必须从 config.yaml 解析。

**实现**:`gateway/run.py:3263-3269 @ 863e313`:
```python
    cfg = config if config is not None else _load_gateway_config()
    model_cfg = cfg.get("model", {})
    if isinstance(model_cfg, str):
        return model_cfg
    elif isinstance(model_cfg, dict):
        return model_cfg.get("default") or model_cfg.get("model") or ""
    return ""
```
容忍 `model:` 为字符串或 dict 两形态;dict 下 `default` 优先、`model` 兜底(`name` 别名已被机制 27 的 `_normalize_root_model_keys` 归一到 `default`)。

**调用关系**:消费点 `6953`(会话模型解析首步)、`8082`、`17960`、`18324`、`25420` @ 863e313。

**重实现要点**:
1. 模型 id 全链路禁止硬编码默认值,统一过一个解析函数;
2. 解析函数可注入已加载 config 避免重复 IO,也可自加载。

### 机制 31:channel override 查找 —— chat→thread→parent 三级继承(3272-3322)

**场景/问题**:Discord 论坛线程/子频道应继承父频道的 `channel_overrides` 配置(模型、provider、prompt),精确 id 未配置时不能直接落空。

**实现**:`_channel_override_lookup_keys` 生成有序去重键列 `[chat_id, thread_id, parent_id]`(`gateway/run.py:3283-3293 @ 863e313`,docstring 注明与 `resolve_channel_prompt` 语义一致);`_get_channel_override` 按序首命中返回:

`gateway/run.py:3309-3322 @ 863e313`:
```python
    platforms = getattr(config, "platforms", None)
    if not platforms:
        return None
    platform_config = platforms.get(platform)
    if not platform_config or not platform_config.channel_overrides:
        return None
    overrides = platform_config.channel_overrides
    for key in _channel_override_lookup_keys(
        chat_id, thread_id=thread_id, parent_id=parent_id
    ):
        ov = overrides.get(key)
        if ov is not None:
            return ov
    return None
```

**调用关系**:消费点 `gateway/run.py:7023-7029 @ 863e313`(会话模型解析:命中则覆盖 model,`ch.provider` 存在再走 `_resolve_runtime_agent_kwargs_for_provider`,7030-7036)、`8072`、`8102`。

**重实现要点**:
1. 层级实体(线程⊂频道⊂论坛)的配置查找用显式键序列表达继承链,首命中即停;
2. 键序生成与查找分离,同一键序函数可被 prompt/model 等多种 override 消费,保语义一致;
3. 有序去重(chat_id 与 thread_id 可能相同)防重复查找。

### 机制 32:_resolve_hermes_bin —— 自更新命令解析(3325-3349)

**场景/问题**:网关引导用户跑 `hermes update` 时,venv/模块方式运行的实例 PATH 上可能没有 `hermes` shim。

**实现**:`shutil.which("hermes")` → `importlib.util.find_spec("hermes_cli")` 存在则 `[sys.executable, "-m", "hermes_cli.main"]` → None(`gateway/run.py:3337-3349 @ 863e313`)。返回 argv parts 列表便于调用方安全引号拼接。消费点 `gateway/run.py:9799 @ 863e313`。

**重实现要点**:
1. 自引用命令解析:PATH shim → `python -m` 包回退 → None,三态由调用方兜底;
2. 返回 argv 数组不返回拼好的字符串,把 shell 引号问题留给唯一拼接点。

## gateway/run.py:3352-3442 — session key 解析与 watch 事件路由

### 机制 33:_parse_session_key —— 会话键反解析与 thread_id 歧义防护(3352-3375)

**场景/问题**:后台事件(async delegation 完成)只带 session_key,要反解析出 platform/chat_id 才能路由回平台。坑:键第 6 段在 group/channel 会话里可能是 user_id(per-user 隔离)而非 thread_id,当 thread_id 用会错投线程。

**实现**:`gateway/run.py:3365-3375 @ 863e313`:
```python
    parts = session_key.split(":")
    if len(parts) >= 5 and parts[0] == "agent" and parts[1] == "main":
        result = {
            "platform": parts[2],
            "chat_type": parts[3],
            "chat_id": parts[4],
        }
        if len(parts) > 5 and parts[3] in {"dm", "thread"}:
            result["thread_id"] = parts[5]
        return result
    return None
```
只有 `dm`/`thread` 两种 chat_type 下第 6 段无歧义才回填 `thread_id`;其余宁缺毋滥(docstring 3360-3363:"we leave thread_id out to avoid mis-routing")。

**调用关系**:消费点:`9297`、`21862`、`21933`(校验键形态)、`22238` @ 863e313——最后者是 `_enrich_async_delegation_routing`:async 委托完成事件回填 platform/chat_type/chat_id/thread_id 供 `_build_process_event_source` 构造投递源(22226-22245;CLI 起源空键 best-effort 放弃路由)。另注意 `6050` 的注释承认有键形态 `_parse_session_key` 无法恢复 thread_id。

**重实现要点**:
1. 复合键反解析对歧义段"宁可不填,不可错填"——错投比缺参更糟;
2. 键格式(`agent:main:platform:chat_type:chat_id[:extra]`)的构造与解析两端都写进 docstring,歧义规则显式列举;
3. 解析失败返回 None,调用方一律按"不可路由"降级。

### 机制 34:watch 事件格式化与选择性 drain(3378-3435)

**场景/问题**:进程注册表的 `completion_queue` 是三类事件共用的:进程完成(per-process watcher 任务负责)、watch 模式命中(回合后网关 drain 负责)、async 委托完成(启动时的 `_async_delegation_watcher` 负责)。网关 drain 只该消费自己那类;若把不属于自己的事件在 `while not queue.empty()` 里直接 requeue,队列永不空,死循环。

**实现**:`_format_gateway_process_notification`(3378-3407)把 watch 事件渲染成 `[IMPORTANT: …]` 注入文本:`watch_disabled` 直传消息;`watch_match` 拼 pattern/command/输出并附限流抑制计数;`async_delegation` 委托共享格式化器 `tools.process_registry.format_process_notification`。drain 函数先整批 detach、后 requeue:

`gateway/run.py:3421-3435 @ 863e313`:
```python
    requeue: list[dict] = []
    while not completion_queue.empty():
        try:
            evt = completion_queue.get_nowait()
        except Exception:
            break
        evt_type = evt.get("type", "completion")
        if evt_type in {"watch_match", "watch_disabled"}:
            watch_events.append(evt)
        elif evt_type == "async_delegation":
            requeue.append(evt)
        # else: process completion events are handled by the watcher task
    for evt in requeue:
        completion_queue.put(evt)
    return watch_events
```
注意:普通 completion 事件被本 drain **丢弃**(不 requeue)——注释断言它们由 per-process watcher 任务负责,此处见到即为已被消费过的冗余。

**调用关系**:消费点 `gateway/run.py:17817-17826 @ 863e313`(回合后 drain,注释 17813-17816 解释 async 事件留队给专属 watcher)与 `22283`(`_format_gateway_process_notification` 在 async watcher 内复用)。

**设计理由与取舍**:多消费者共享一条队列靠 type 字段分工——胜在生产端(进程注册表)无需知道消费者拓扑;弱点是"谁负责哪类"契约散在注释里,新增事件类型要同时改多个 drain 点。detach-then-requeue 是共享队列选择性消费的标准解法。

**重实现要点**:
1. 共享队列的选择性消费必须"整批取出→分拣→归还非己方事件",绝不在 empty() 循环内 requeue;
2. 每类事件的属主(哪个任务消费)写成显式契约,drain 处注释点名其他属主;
3. 注入模型的通知统一 `[IMPORTANT: …]` 包裹格式,带限流抑制计数保信息不失真。

### 机制 35:_gateway_runner_ref —— 模块级弱引用出口(3438-3442)

**实现**:`gateway/run.py:3438-3442 @ 863e313`:
```python
# Module-level weak reference to the active GatewayRunner instance.
# Used by tools (e.g. send_message) that need to route through a live
# adapter for plugin platforms.  Set in GatewayRunner.__init__().
import weakref as _weakref
_gateway_runner_ref: _weakref.ref = lambda: None
```
初值是**返回 None 的 lambda**(鸭子类型模拟死弱引用),`GatewayRunner.__init__` 里置真弱引用(`gateway/run.py:5874/5897 @ 863e313`:`global _gateway_runner_ref` + `_gateway_runner_ref = _weakref.ref(self)`)。工具(send_message 等)借此拿到活 runner 的 adapter 路由插件平台消息,弱引用不阻碍 runner 回收。

**重实现要点**:
1. 工具层反向触达宿主用模块级弱引用,避免强引用循环与生命周期锁死;
2. "未设置"哨兵用同签名可调用(`lambda: None`),消费方无需判 None-vs-ref 两型。

## gateway/run.py:3445-3603 — 空响应归一与回合收尾判定

### 机制 36:_normalize_empty_agent_response —— 空响应归一为用户可见错误(3445-3527;#18765、#31884、#44212)

**场景/问题**:agent 回合结束响应为空有六种成因,静默不回消息是消息平台最差体验:(1) 失败(context 溢出 vs 其他);(2) 中断且 0 次 API 调用——#44212:`/stop` 残留的中断旗把下一条真实用户消息在工具循环顶部杀掉,纯静默吞消息;(3) 中断且有 API 调用——用户主动 stop/steer 的 drain,静默是**故意的**;(4) 做了工作但无文本(#18765);(5) partial;(6) 0 API 调用且无任何标志——#31884:/stop 后 generation 竞态,消息被静默丢弃。

**实现**:优先级级联。失败分支先嗅探 context 溢出(关键词 + "400 且历史>50 条"启发)给 /compact 指引,否则截断错误文本 + /reset 指引(3466-3482)。中断分支(`gateway/run.py:3484-3499 @ 863e313`):
```python
    api_calls = int(agent_result.get("api_calls", 0) or 0)
    if agent_result.get("interrupted"):
        # An interrupted run that did work (api_calls > 0) is the drain of a
        # run the user deliberately stopped or steered — its silence is
        # intentional, and any queued/interrupting message is delivered by
        # the recursive drain inside _run_agent before this result is seen.
        # An interrupted run with ZERO api_calls never processed the user's
        # message at all: it was killed at the top of the tool loop by an
        # interrupt flag left over from a recent /stop (#44212).  Pure
        # silence there swallows a real user message, so surface it.
        if api_calls == 0:
            return (
                "⚠️ Your message was interrupted before processing started "
                "(likely by a recent /stop). Please send it again."
            )
        return response
```
`api_calls > 0` 分支:hidden-reasoning 未完成回合返回空串(合法静默,见机制 37);partial 报"Processing stopped";否则报"completed but no response"(3500-3509)。末段 `api_calls == 0` 无标志 → "previous turn was still being cleaned up, send again"(3516-3525;其中 `not interrupted`/`not failed` 条件在该位置恒真,见冲突候选 ▲5)。

**调用关系**:两个消费点:TurnRunner 内 `gateway/run.py:5575-5578 @ 863e313` 与回合收尾 `17667-17671`(`_intentional_silence` 时跳过;归一后再过 `_sanitize_gateway_final_response`)。

**设计理由与取舍**:核心判据是 `api_calls` 计数——它把"中断"二分为"用户止住了正在跑的活(静默合法)"与"消息根本没被处理(必须告知)"。所有文案自带下一步动作(/compact、/reset、重发)。取舍:关键词嗅探 context 溢出有误报面(注释 17857-17859 显示持久化侧用了更严的多词短语,两处口径不同)。

**重实现要点**:
1. 消息平台上"空响应"是一等错误态,枚举全部成因逐一给用户可执行文案,禁止静默;
2. 用 `api_calls`(或等价的"做过工作"计数)区分"故意静默的中断"与"消息被吞的中断";
3. context 溢出专属文案指向压缩/重置,一般错误指向重试,不混用;
4. 归一化做成纯函数(result dict → 文本),两个调用面共享。

### 机制 37:_is_gateway_hidden_reasoning_incomplete_turn —— 重试耗尽哨兵回合判定(3530-3551)

**场景/问题**:Codex 类 provider 的隐藏推理回合重试耗尽时,conversation loop 把哨兵文案("Codex response remained incomplete after 3 continuation attempts")**同时**放进 `final_response` 与 `error`——`final_response` 非空不代表模型给了可见答案,直接投递会把内部哨兵当回复发给用户。

**实现**:`gateway/run.py:3541-3551 @ 863e313`:
```python
    if not isinstance(agent_result, dict):
        return False
    if agent_result.get("failed") or agent_result.get("interrupted"):
        return False
    if not agent_result.get("partial"):
        return False
    error_text = str(agent_result.get("error", "") or "").strip()
    if "remained incomplete after" not in error_text.lower():
        return False
    final_response = str(agent_result.get("final_response") or "").strip()
    return not final_response or final_response == error_text
```
四重门:非 failed/interrupted、是 partial、error 含哨兵短语、final_response 为空或恰等于哨兵——"any genuinely different final text means the model DID answer and must be delivered"(3538-3539)。

**调用关系**:消费点三处:`3501`(机制 36 内:命中则返回空串,即合法静默)、`17609`、`17853 @ 863e313`(影响转录持久化分类)。

**重实现要点**:
1. 下游用"error 与 final_response 相等"识别哨兵回填,任何真实差异一律按真答案投递——宁误发不误吞;
2. 内部重试耗尽哨兵不该发给用户,但判定必须多重收窄(partial + 短语 + 相等),防误伤;
3. 根治法是让 loop 不要把哨兵塞进 final_response;下游判定是兼容性补丁,注释要写明来源契约。

### 机制 38:_should_clear_resume_pending_after_turn —— 重启恢复标记的保守清除(3554-3571)

**场景/问题**:网关重启 drain 时给被打断会话打 `resume_pending` 持久标记,启动自动恢复据此调度。软中断可以以"语法正常、final 为空"的 result 冒出——若据此清标记,恢复信号丢失,启动恢复无事可做。

**实现**:白名单式判定,任何异常迹象都不清。`gateway/run.py:3563-3571 @ 863e313`:
```python
    if not isinstance(agent_result, dict):
        return False
    if agent_result.get("interrupted"):
        return False
    if agent_result.get("failed") or agent_result.get("partial") or agent_result.get("error"):
        return False
    if agent_result.get("completed") is False:
        return False
    return True
```
注意 `completed is False`:显式 False 才拒绝,缺键(旧契约)放行。

**调用关系**:唯一消费点 `gateway/run.py:17655-17663 @ 863e313`:通过则清 restart 失败计数 + `async_session_store.clear_resume_pending(session_key)`(清除本身 fail-open)。

**重实现要点**:
1. 持久恢复标记的清除条件用严格白名单("确证成功"),存疑一律保留——多恢复一次代价远小于丢恢复;
2. 布尔契约演进用三值判定(`is False`)兼容缺键旧结果;
3. 标记清除失败不影响回合结果(fail-open + debug 日志)。

### 机制 39:_preserve_queued_followup_history_offset —— 排队跟进链的转录偏移保持(3574-3603)

**场景/问题**:`_process_message_background()` 只在**整条**排队跟进链返回后持久化转录一次;每层递归 `_run_agent()` 把 `history_offset` 推进到它收到的历史长度。不修正的话,最外层持久化只把**最后一个**排队回合看作"新内容",链中较早的回合从转录里静默丢失。

**实现**:取最外(最早)偏移:`gateway/run.py:3589-3603 @ 863e313`:
```python
    if not isinstance(followup_result, dict):
        return followup_result
    if not isinstance(current_result, dict):
        return followup_result

    current_offset = current_result.get("history_offset")
    followup_offset = followup_result.get("history_offset")
    if not isinstance(current_offset, int):
        return followup_result
    if isinstance(followup_offset, int) and followup_offset <= current_offset:
        return followup_result

    merged = dict(followup_result)
    merged["history_offset"] = current_offset
    return merged
```
只在内层偏移**更大**时才覆盖(内层更小/相等说明已是最外),且拷贝 dict 不改内层结果原件。

**调用关系**:唯一消费点递归返回处 `gateway/run.py:25765-25778 @ 863e313`(`return _preserve_queued_followup_history_offset(result, followup_result)`)。

**重实现要点**:
1. "递归执行、最外层一次性持久化"模式下,增量游标必须沿递归向外传播取最小值;
2. 修正函数纯化(不 mutate 输入,copy-on-write),类型守卫齐全兼容异常形态 result;
3. 持久化切片语义("offset 之后是新内容")要在推进游标的每个点位被审视。

## gateway/run.py:3606-3670 — adapter 处置与重连退避

### 机制 40:_dispose_unused_adapter —— 未安装 adapter 的 fd 泄漏防治(3606-3657;#37011)

**场景/问题**:#37011:重连 watcher 每次重试都**新构造** adapter;connect 失败(不可重试错/可重试错/异常)时 adapter 被丢弃、从未装上 `self.adapters`,无人调它的 `disconnect()`。`APIServerAdapter.__init__` 打开 SQLite `ResponseStore`(db + WAL 共 2 fd);asyncio 绑定的原生句柄对象循环 GC 回收不及时。300s 退避封顶下 2 fd/次 ≈ 12 fd/时,默认 2560 fd ulimit 约 12 小时耗尽,之后网关任何 open() 都 `OSError: [Errno 24]`,变僵尸。

**实现**:集中化"吞异常的 dispose",三个失败路径共用;`None` 容忍(watcher 在 try 前初始化 `adapter = None`,`_create_adapter()` 返回 None 时也走到这)。`gateway/run.py:3635-3657 @ 863e313`:
```python
    if adapter is None:
        return
    try:
        await adapter.disconnect()
    except Exception:
        # Half-constructed adapters (e.g. APIServerAdapter that
        # crashed during aiohttp app setup) can raise from
        # disconnect() on objects that never finished initializing.
        # We must not let that escape and abort the watcher loop.
        #
        # On Python 3.8+, ``asyncio.CancelledError`` inherits from
        # ``BaseException`` (not ``Exception``), so this ``except
        # Exception`` does not swallow task cancellation. We don't
        # re-raise explicitly because the watcher loop intentionally
        # treats dispose failures as best-effort: a failed ``disconnect``
        # call should not take down the reconnect watcher that
        # itself is what's keeping the gateway alive during a partial
        # outage.
        logger.debug(
            "Adapter dispose raised on unowned adapter %r",
            getattr(adapter, "name", type(adapter).__name__),
            exc_info=True,
        )
```

**调用关系**:三个调用点全在 `_platform_reconnect_watcher`:不可重试分支 `gateway/run.py:12539 @ 863e313`(注释 12531-12538 复述 fd 账目)、可重试分支 `12562`(注释 12555-12560)、异常分支 `12579`(注释 12572-12578)。

**重实现要点**:
1. "构造了但没安装"的对象是资源泄漏高发区——每条丢弃路径显式 dispose,不赌 GC;
2. 半构造对象的 dispose 本身会抛,集中一个吞异常的处置函数,防止清理失败杀死救火的 watcher;
3. `except Exception` 而非 `BaseException`,让 CancelledError 穿透保 asyncio 取消语义;
4. 泄漏分析写进注释要带算术(fd/次 × 频率 → 耗尽时限),给后人量化直觉。

### 机制 41:_reconnect_backoff —— 共享指数退避(3660-3667)

**实现**:`gateway/run.py:3660-3667 @ 863e313`:
```python
# Max seconds between platform reconnect retries (primary watcher and
# secondary-profile reconnects share this policy — tune in one place).
_RECONNECT_BACKOFF_CAP = 300


def _reconnect_backoff(attempt: int) -> int:
    """Exponential reconnect backoff: 30s, 60s, 120s, ... capped at 5 min."""
    return min(30 * (2 ** (attempt - 1)), _RECONNECT_BACKOFF_CAP)
```
序列 30/60/120/240/300(封顶)。消费点:主 watcher `12548/12586`、secondary profile 重连 `13499` @ 863e313——注释点名"tune in one place"。配合机制 40 的可重试分支语义:可重试故障在封顶节奏下**无限**重试自愈,绝不自动暂停(12563-12570 注释:瞬时断网不得要求手工 `/platform resume`)。

**重实现要点**:
1. 退避策略(基数/封顶)单点定义,所有重连面共享;
2. 可重试故障封顶后无限重试,不引入"重试次数上限→人工恢复"——瞬断必须自愈;
3. attempt 从 1 计,公式与 docstring 的数列示例保持可对拍。

## 文档-代码冲突候选(▲=倾向判冲突,◇=待裁决/观察)

1. **▲ `_resolve_runtime_agent_kwargs` docstring vs. HERMES_MAX_TOKENS env 优先**:docstring 称"the gateway does not consult environment variables for behavioral config — config.yaml is authoritative"(`gateway/run.py:2516-2519 @ 863e313`),但函数体 `os.environ.get("HERMES_MAX_TOKENS")` 优先于 `model_cfg.get("max_tokens")`(`gateway/run.py:2551-2560 @ 863e313`),且 `model.max_tokens` 是嵌套键、不会被机制 5 的顶层标量桥导出——env 值确实能压过 config.yaml 的行为配置。docstring 断言与 max_tokens 解析顺序直接矛盾。
2. **▲ 陈旧行号注释 "line ~255"**:terminal cwd 桥注释称占位符"the gateway resolves these to Path.home() later (line ~255)"(`gateway/run.py:2103-2104 @ 863e313`),实际解析在 `gateway/run.py:2325-2340 @ 863e313`,且并非一律 `Path.home()` 而是 `resolve_placeholder_terminal_cwd` 的三分支合同(`gateway/cwd_placeholder.py:19 @ 863e313`),`Path.home()` 只是 `home_fallback` 参数。行号漂移 + 语义简化双重失真。
3. **◇ `GATEWAY_ALLOW_ALL_USERS` 绕过 secret scope**:`_own_policy_open_startup_violation` 中平台级 allow-all 用 scope-aware 的 `_getenv`(`gateway/run.py:2453 @ 863e313`;`gateway/config.py:234-249 @ 863e313`),而全局开关用裸 `os.getenv("GATEWAY_ALLOW_ALL_USERS")`(`gateway/run.py:2448-2450 @ 863e313`)。该函数被 `_profile_runtime_scope` 内调用(`gateway/run.py:13276 @ 863e313`),而 scope 不 mutate `os.environ`(1952-1954)——secondary profile 的 `.env` 里单独设 `GATEWAY_ALLOW_ALL_USERS` 不会被本检查看到,平台级旗则会。是故意(全局开关必须进程级)还是遗漏,段内无注释交代,待与 secret_scope 精读会话合裁。
4. **◇ `_normalize_empty_agent_response` 末段死条件与 partial+0-calls 静默**:`gateway/run.py:3516-3521 @ 863e313` 的 `not agent_result.get("interrupted")`/`not agent_result.get("failed")` 在该位置恒真(3466 与 3485 已提前 return),唯一起效的是 `not partial`;后果:`partial=True 且 api_calls==0` 的回合落到 3527 行 `return response` 返回空串——一个既没跑 API 又标记 partial 的回合仍然纯静默,与 docstring "adds a catch-all"(3452-3454)的意图有缝隙。死条件本身也提示这段是补丁叠补丁的产物。
5. **◇ context 溢出嗅探口径分裂**:机制 36 用宽松单词集 `("context", "token", "too large", …)` + `400 且 history>50`(`gateway/run.py:3469-3472 @ 863e313`);转录持久化分类处注释明言改用"specific multi-word phrases (not bare 'exceed' or 'token') to avoid false positives"(`gateway/run.py:17857-17859 @ 863e313`)。同一失败在"给用户的文案"与"是否持久化用户消息"两个判定上可能得出不同分类(如 "rate limit exceeded" 会被 3469 误判为 context 溢出文案)。行为不一致是否有意,待裁决。
6. **◇ `_reap_gateway_turn_processes` docstring 的"nothing permanently unreaped"**:`gateway/run.py:2854-2857 @ 863e313` 称跳过收割不会造成永久失收("The newer turn snapshots its own baseline independently, so skipping here does not leave anything permanently unreaped")。严格说:旧回合的残留进程在新回合快照**之前**已在运行,因此在新回合基线的豁免集内,新回合的收割也不会杀它们——被跳过的旧进程实际无人再收,只能等进程自然退出或整会话级清理。docstring 的表述只对"新回合自己的进程"成立,对"旧回合残留"是模糊的。需结合 process_registry 的会话级清理路径裁决。
7. **◇ `_skill_slug_from_frontmatter` 与 `scan_skill_commands` 的镜像缺口**:前者 docstring 称"Matches the exact normalization"(`gateway/run.py:3011-3013 @ 863e313`),归一化步骤确实逐字一致(3049-3053 vs `agent/skill_commands.py:427-429 @ 863e313`);但 `scan_skill_commands` 在 frontmatter 无 `name:` 时回退目录名 `frontmatter.get('name', skill_md.parent.name)`(`agent/skill_commands.py:410 @ 863e313`),而 `_skill_slug_from_frontmatter` 无名直接返回 `(None, None)`(`gateway/run.py:3047-3048 @ 863e313`)——无名 skill 会有 /command 却永远匹配不上 `_check_unavailable_skill`,被禁用时退化回 generic "unknown command",正是该函数要修的症状在边角的复发。
8. **◇ `logger` 未初始化的窗口**:`_load_gateway_config` 的 except 分支用 `logger.debug`(`gateway/run.py:3179 @ 863e313`),logger 定义在 2416 行,函数定义顺序上无问题(调用必在模块导入完成后);但机制 9 注释(2275-2277)强调桥段不能用 logger——两段离得很近、政策相反,属易误改点,记为观察项而非冲突。

## 段界与续接

- 本段起点 1924 行承接上半段模块辅助(1841 行附近的 secret-scope worker 注释引用了本段的 `_profile_runtime_scope`,`gateway/run.py:1841 @ 863e313`);终点 3670 行为 `class TurnRunner:` 定义起始,TurnRunner/GatewayRunner 类体(3670-27146)归后续段落。
- 本段全部为模块级:2 个异常类、1 个 contextmanager、约 40 个模块函数、9 组常量、1 段模块导入期副作用代码(config→env 桥 + 启动杂项)。除标注"样板"的导入块与 Docker 常量外,均已逐机制交代。