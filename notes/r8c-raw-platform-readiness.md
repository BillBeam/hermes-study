# r8c 底稿 · 平台就绪判定的 8 份实现逐份对齐(结清 H-R8B-c / H-R8A-13)

> 溯源约定:所有对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` **单独成行、置于代码块之前**,
> 代码块为基线逐字原文。非源码块(shell 输出、我做的推演表)用 ```text / ```console / ```verify 声明。
> 记号:▲ 文档与代码矛盾;◇ 代码有文档无;■ 代码缺陷;◎ 文档成立但保守。

---

## 0. 结论摘要(先给答案)

1. **移交项里的一处定位是错的**:仓库根 `cli.py` 里被点名的那一份**不是**运行时真值,
   它是 `/gateway` 斜杠命令的打印函数,判据只有 `pconfig.enabled`,是全部 13 个判定点里**最弱**的一份。
   真正的运行时真值是 `gateway/config.py` 的 `get_connected_platforms()` →
   `_is_platform_connected()`。锚点与原文见 §2。
2. **原问的答案:除 `status` 外,移交项点名的 8 份里还有 2 份漏了 `is_connected`
   ——`hermes_cli/dump.py`、`hermes_cli/tools_config.py`。**
   若把移交项额外点名的第 9 份 `cli.py` 一并计入,则是 **3 份**。
   名单与判定见 §4。
3. **`hermes_cli/status.py` 的误判不是"理论上的"——本轮实跑复现了**:在**零凭据**的机器上,
   Hermes CLI 内 `/status` 会把 **7 个平台**打印成 `✓ configured`;SDK 装齐后**再多 4 个**,
   共 **11/23**。而且同一个平台被**打印两遍**、两遍**结论相反**。见 §7,附实测输出。
4. **没有任何测试钉住这 8 份的一致性。** 更糟:仓库里**存在**一个专为此写的回归守卫类
   `TestHomeTargetEnvVarRegistry`,但**类体只有 docstring、一个测试方法都没有**
   (全仓 6572 个 `Test*` 类里仅 14 个是空的,它是其中之一)。见 §8。
5. **平台清单彼此不一致,且不一致是常态**:9 份认识的平台数是
   23 / 19 / 6+ / 6+ / 31+ / 16 / 5 / 15+ / 4。新增一个平台要改的地方远不止 8 处。
   另外发现一处独立缺陷:`whatsapp_cloud` 在 `_HOME_TARGET_ENV_VARS` 里有 home 变量,
   却不在 `_KNOWN_DELIVERY_PLATFORMS` 里,于是**永远进不了 cron 投递下拉框**。见 §6。

---

## 1. 校验、环境、路径消歧

### 1.1 基线状态

```console
$ git -C /home/user/hermes-agent rev-parse HEAD
863e31318553cda8ad61df681d08175364d4164b
$ git -C /home/user/hermes-agent status --porcelain
(空)
```

本轮跑过 `scripts/run_tests.sh`,它会写 `test_durations.json`;该文件在
`.gitignore:35` 中,故 `git status --porcelain` 仍为空,基线未被污染:

```console
$ git -C /home/user/hermes-agent check-ignore -v test_durations.json
.gitignore:35:test_durations.json	test_durations.json
```

### 1.2 venv 环境(报测试数必须一并记)

```console
$ /home/user/hermes-venv/bin/pip list | tail -n +3 | wc -l
87
```

87 包,与 CLAUDE.md 记录的 R8B 环境一致(`[dev]` extra + `aiohttp 3.14.1` + `brotlicffi 1.2.0.1`)。
关键平台 SDK **均未安装**——这一点对 §7 的读数至关重要:

```console
$ /home/user/hermes-venv/bin/python -c "..."
telegram     importable=False
discord      importable=False
slack_sdk    importable=False
slack_bolt   importable=False
mautrix      importable=False
httpx        importable=True
aiohttp      importable=True
botbuilder   importable=False
```

### 1.3 同名文件消歧(移交项踩过的坑,先钉死)

基线里 `gateway.py` / `dump.py` / `status.py` / `setup.py` / `config.py` 都有多个同名候选。
本轮**全部核查**,确认平台就绪判定只在下表左列的文件里:

```console
$ git ls-files | grep -E "(^|/)(gateway|dump|status|setup|config|scheduler|web_server|tools_config)\.py$"
hermes_cli/gateway.py          hermes_cli/subcommands/gateway.py
hermes_cli/dump.py             hermes_cli/subcommands/dump.py
gateway/status.py              hermes_cli/status.py    hermes_cli/subcommands/status.py
hermes_cli/setup.py            hermes_cli/subcommands/setup.py    setup.py
                               skills/productivity/google-workspace/scripts/setup.py
gateway/config.py              hermes_cli/config.py    hermes_cli/subcommands/config.py
                               optional-skills/security/unbroker/scripts/config.py
cron/scheduler.py              hermes_cli/web_server.py           hermes_cli/tools_config.py
```

排除依据(逐个查过,**不是**靠文件名猜的):

```console
$ for f in hermes_cli/subcommands/{status,gateway,dump,setup}.py gateway/status.py setup.py; do ...
hermes_cli/subcommands/status.py       lines=28     TELEGRAM_BOT_TOKEN=0 is_connected=0
hermes_cli/subcommands/gateway.py      lines=355    TELEGRAM_BOT_TOKEN=0 is_connected=0
hermes_cli/subcommands/dump.py         lines=28     TELEGRAM_BOT_TOKEN=0 is_connected=0
hermes_cli/subcommands/setup.py        lines=67     TELEGRAM_BOT_TOKEN=0 is_connected=0
gateway/status.py                      lines=2260   TELEGRAM_BOT_TOKEN=0 is_connected=0
setup.py                               lines=74     TELEGRAM_BOT_TOKEN=0 is_connected=0
```

`hermes_cli/subcommands/*.py` 四份都是 **argparse 解析器**(god-file 拆分产物),不含判定;
`gateway/status.py` 是**运行时 PID/健康状态**读写,与"配没配好"无关;
仓库根 `setup.py` 是 setuptools 打包脚本。**以上 6 份均无平台就绪判定,予以排除。**

---

## 2. 运行时真值那一份(先纠正移交项)

### 2.1 `is_connected` 是什么

它是**平台插件注册表**上的一个可选钩子字段。一句话:回答"用户到底给这个平台配了凭据没有"。

`gateway/platform_registry.py:61 @ 863e313`

```python
    # Optional: given a PlatformConfig, is the platform connected/enabled?
    # Used by ``GatewayConfig.get_connected_platforms()`` and setup UI status.
    # If None, falls back to ``validate_config`` or ``check_fn``.
    is_connected: Optional[Callable[[Any], bool]] = None
```

注意注释自己写明了它的两个消费方:`get_connected_platforms()` 与 **setup UI status**。

### 2.2 真值:`gateway/config.py`

`gateway/config.py:963 @ 863e313`

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

判定是**两段式**:先 `enabled`(用户/配置说要开),再 `_is_platform_connected`(凭据真的在)。
后者是四级瀑布:

`gateway/config.py:980 @ 863e313`

```python
    def _is_platform_connected(self, platform: Platform, config: PlatformConfig) -> bool:
        """Check whether a single platform is sufficiently configured."""
        # Weixin requires both a token and an account_id (checked first so
        # the generic token branch doesn't let it through without account_id).
        if platform == Platform.WEIXIN:
            return bool(
                config.extra.get("account_id")
                and (config.token or config.extra.get("token"))
            )

        # Generic token/api_key auth covers Telegram, Discord, Slack, etc.
        if config.token or config.api_key:
            return True

        # Platform-specific check
        checker = _PLATFORM_CONNECTED_CHECKERS.get(platform)
        if checker is not None:
            return checker(config)
```

第四级才落到插件钩子——这就是全仓 `is_connected` 的**唯一权威消费点**:

`gateway/config.py:999 @ 863e313`

```python
        # Plugin-registered platforms.  Force plugin discovery first so this
        # works even when GatewayConfig is constructed directly (e.g. in tests
        # or callers that bypass load_gateway_config(), which is what triggers
        # discovery in the normal path).  discover_plugins() is idempotent.
        try:
            from gateway.platform_registry import platform_registry
            try:
                from hermes_cli.plugins import discover_plugins
                discover_plugins()
            except Exception:
                pass
            entry = platform_registry.get(platform.value)
            if entry:
                if entry.is_connected is not None:
                    return entry.is_connected(config)
                if entry.validate_config is not None:
                    return entry.validate_config(config)
                return True
        except Exception:
            pass  # Registry not yet initialised during early import

        return False
```

**记住这一句:它自己调了 `discover_plugins()`。** §7 会看到 `hermes_cli/status.py` 恰恰没调,
后果是灾难性的两面性。

### 2.3 ▲ 移交项定位纠正:仓库根 `cli.py` 那一份不是运行时真值

移交项给的 `cli.py:9789` 落在 `_show_gateway_status()`(`/gateway` 斜杠命令的打印函数)里,
正好是 `config = load_gateway_config()` 那一行。它下面的判定是:

`cli.py:9794 @ 863e313`

```python
            platform_status = {
                Platform.TELEGRAM: ("Telegram", "TELEGRAM_BOT_TOKEN"),
                Platform.DISCORD: ("Discord", "DISCORD_BOT_TOKEN"),
                Platform.SLACK: ("Slack", "SLACK_BOT_TOKEN"),
                Platform.WHATSAPP: ("WhatsApp", "WHATSAPP_ENABLED"),
            }
            
            for platform, (name, env_var) in platform_status.items():
                pconfig = config.platforms.get(platform)
                if pconfig and pconfig.enabled:
                    home = config.get_home_channel(platform)
                    home_str = f" → {home.name}" if home else ""
                    print(f"    ✓ {name:<12} Enabled{home_str}")
                else:
                    print(f"    ○ {name:<12} Not configured ({env_var})")
```

判据只有 `pconfig.enabled`,**既没有 `is_connected`,也没有 `_is_platform_connected`**,
而且平台表是**写死的 4 个**。全文件的客观计数:

```console
$ grep -c 'is_connected' cli.py           -> 0
$ grep -c 'TELEGRAM_BOT_TOKEN' cli.py     -> 2   (9795 与 9830,均在此函数内)
$ grep -c 'platform_registry' cli.py      -> 0
```

**结论:移交项写的"运行时真值那一份在仓库根 `cli.py`"应改为
"运行时真值在 `gateway/config.py` 的 `get_connected_platforms`/`_is_platform_connected`;
仓库根 `cli.py` 那一份是第 13 个、也是最弱的一个判定点"。**
后文一律以 §2.2 引的 `_is_platform_connected` 为对齐基准。

---

## 3. 逐份对齐表(13 个判定点)

移交项点名 8 个文件 + 运行时真值文件,共 9 个文件;其中 3 个文件各含 2 个判定点,
故判定点共 **13 个**。「达到 `is_connected`」= 该判定**直接调** `entry.is_connected`,
或**经由** `_is_platform_connected` / `get_connected_platforms` **间接调到**。
下表每行的 `文件:行号` 是该判定点的入口锚点;每一处的**代码原文**在 §2、§4、§5、§7 逐个给出。

| # | 文件:行号 | 函数 / 入口 | 判据用了什么 | 覆盖哪些平台 | 与 `gateway/config.py:980` 真值的差异 | 用户可见现象 | 判定 |
|---|---|---|---|---|---|---|---|
| 1 | `gateway/config.py:980` | `_is_platform_connected` | **weixin 特例 → token/api_key → `_PLATFORM_CONNECTED_CHECKERS` → `entry.is_connected` → `validate_config`** | Platform 枚举 23 个 + 插件动态成员(开集) | **基准本身** | — | 真值 |
| 2 | `gateway/config.py:2575` | `_apply_env_overrides` 插件自动启用闸门 | `entry.is_connected(probe_cfg)` **先**,`entry.check_fn()` **后** | 全部 `plugin_entries()`(23) | 无。用 `enabled=True` 的合成 cfg 探测,语义是"若启用它会算配好吗" | — | 有意(见 §5.1) |
| 3 | `cron/scheduler.py:1114` | `cron_delivery_targets()` | `get_connected_platforms()`(间接到 `is_connected`)**再与** `_is_known_delivery_platform` 取交集 | `_HOME_TARGET_ENV_VARS`(16)∪ 带 `cron_deliver_env_var` 的插件,**再交** `_KNOWN_DELIVERY_PLATFORMS`(19) | 更严:真值之上再叠"是不是合法投递目标" | `whatsapp_cloud` 被永久排除 ■(§6.2) | 有意 + 1 处 ■ |
| 4 | `cron/scheduler.py:1606` | `_deliver_result` 实际投递 | **仅** `pconfig.enabled` | 由 job 的 `deliver` 字段决定 | **漏 `is_connected`** | 见 §5.4 | 有意 |
| 5 | `hermes_cli/gateway.py:5431` | `_platform_status`(**已修的孪生**) | `entry.is_connected` 优先;**无钩子才**回落 `check_fn`;内置项按 `token_var` + 逐平台特例 | `_PLATFORMS`(6)+ 全部注册表条目(开集) | 用合成 `PlatformConfig(enabled=True)` 而非真实 cfg,故读不到 config.yaml 里的 token(见 §5.2) | 极少数场景低报 | 基本对齐 ◎ |
| 6 | `hermes_cli/setup.py:2195` | `setup_gateway` 段落 | **委托** `hermes_cli/gateway.py:5431` | 同 #5 | 同 #5 | 同 #5 | 委托,无独立差异 |
| 7 | `hermes_cli/web_server.py:8333` | `_messaging_platform_payload`(非 scoped) | **直接调** `gateway_config._is_platform_connected(...)` | `_PLATFORM_OVERRIDES`(31)+ 枚举 + 注册表 | **零差异**——唯一逐字复用真值函数的一份 | — | 对齐 |
| 8 | `hermes_cli/web_server.py:8315` | 同上(profile scoped 分支) | `all(env_on_disk.get(k) for k in required_env)` | 同上 | **漏 `is_connected`**,只看 profile 自己的 `.env` | 见 §5.3 | **有意** |
| 9 | `hermes_cli/dump.py:181` | `_configured_platforms()` | `os.getenv(env)` 单变量存在性,**16 个写死** | 写死 16 个,**闭集** | **漏 `is_connected`**;漏 config.yaml;漏多变量平台;漏全部插件专有平台 | 见 §5.5 | **■** |
| 10 | `hermes_cli/tools_config.py:2074` | `_get_enabled_platforms()` | `get_env_value(...)` 单变量,**5 个写死** | `cli` + 写死 5 个,**闭集** | **漏 `is_connected`**;且平台面最窄 | 见 §5.6 | **■** |
| 11 | `hermes_cli/status.py:487` | `show_status` 内置表 | `os.getenv(token_var)` 单变量,**15 个写死** | 写死 15 个 | 漏 `is_connected`;漏 config.yaml | 与插件块**打架**(§7) | ■(次要) |
| 12 | `hermes_cli/status.py:504` | `show_status` 插件块 | **`entry.check_fn()`** —— 依赖/SDK 探针,**不是**凭据探针 | `plugin_entries()`,但**没调 `discover_plugins()`** | **漏 `is_connected`,且用了明确被判为错的替身** | **7~11 个平台假阳性 + pip 副作用**(§7) | **■ 主缺陷** |
| 13 | `cli.py:9794` | `_show_gateway_status` | **仅** `pconfig.enabled` | 写死 4 个,**闭集** | **漏 `is_connected`**;平台面最窄;`enabled` 为真但无凭据时报 Enabled | 见 §5.7 | **■** |

---

## 4. 原问的确定答案:除 status 外还有几份漏了 `is_connected`

```verify
问:除 hermes_cli/status.py 外,还有几份同样漏了 is_connected?

按移交项点名的 8 份文件计:
  达到 is_connected 的 5 份 —— gateway/config.py, cron/scheduler.py,
                               hermes_cli/gateway.py, hermes_cli/setup.py,
                               hermes_cli/web_server.py
  漏掉的       3 份 —— hermes_cli/status.py (已定案)
                       hermes_cli/dump.py         ← 新增
                       hermes_cli/tools_config.py ← 新增

  ==> 除 status 外,答案是 2 份:dump.py 与 tools_config.py。

若把移交项额外点名的第 9 份 cli.py(被误标为"运行时真值")一并计入:
  ==> 3 份:dump.py、tools_config.py、cli.py。

按判定点(13 个)计,漏 is_connected 的点是 7 个(= §3 表里第 4/8/9/10/11/12/13 行):
  cron/scheduler.py:1606          有意 —— 投递时机,见 §5.4
  hermes_cli/web_server.py:8315   有意 —— profile 隔离,见 §5.3
  hermes_cli/dump.py:181          ■
  hermes_cli/tools_config.py:2074 ■
  hermes_cli/status.py:487        ■(次要:写死表)
  hermes_cli/status.py:504        ■(主缺陷:用 check_fn 当就绪判据)
  cli.py:9794                     ■
即:7 个判定点漏,其中 2 个有意、5 个判 ■。
```

**注意 `cron/scheduler.py` 与 `hermes_cli/setup.py` 这两份最容易判错:**

- `cron/scheduler.py` 全文件 `grep -c is_connected` = **0**,肉眼看像漏了。
  但 `cron_delivery_targets()` 调 `get_connected_platforms()`,**间接**走到了真值。
  只按 grep 判会误报。
- `hermes_cli/setup.py` 全文件 `grep -c is_connected` = **0**,同样像漏了。
  但它 `from hermes_cli.gateway import _all_platforms, _platform_status`,**委托**给已修的孪生。

`hermes_cli/setup.py:2156 @ 863e313`

```python
    from hermes_cli.gateway import _all_platforms, _platform_status, _configure_platform
```

`hermes_cli/setup.py:2183 @ 863e313`

```python
    # ── Gateway Service Setup ──
    # Count any platform (built-in or plugin) the user configured during this
    # setup pass — reuses ``_platform_status`` so plugin platforms like IRC
    # are picked up without another hard-coded env-var list.
    def _is_progress(status: str) -> bool:
        s = status.lower()
        return not (
            s == "not configured"
            or s.startswith("partially")
            or s.startswith("plugin disabled")
        )

    any_messaging = any(
        _is_progress(_platform_status(p)) for p in _all_platforms()
    )
```

注释里 "reuses `_platform_status` so plugin platforms like IRC are picked up
**without another hard-coded env-var list**" —— 作者是**明确意识到**"又一份写死清单"是病的。
`setup.py` 治好了,`dump.py` / `tools_config.py` / `status.py` / `cli.py` 没治。

`cron/scheduler.py:1114 @ 863e313`

```python
    targets: list[dict] = []
    try:
        from gateway.config import load_gateway_config

        gateway_config = load_gateway_config()
        connected = {p.value for p in gateway_config.get_connected_platforms()}
    except Exception:
        logger.debug("cron_delivery_targets: gateway config unavailable", exc_info=True)
        connected = set()

    for name in _iter_home_target_platforms():
        if name not in connected:
            continue
        if not _is_known_delivery_platform(name):
            continue
```

---

## 5. 逐处差异:■ 缺陷 还是 有意

### 5.1 `gateway/config.py` 插件启用闸门 —— **有意**,且是全仓最好的注释

`gateway/config.py:2522 @ 863e313`

```python
    # Enablement gate (#31116): when a plugin registers ``is_connected``
    # (the "has the user actually configured credentials for this?" check),
    # we MUST consult it before flipping ``enabled = True``.  Otherwise
    # ``check_fn`` alone — which for adapter plugins typically just
    # verifies the SDK is importable / lazy-installs it — silently enables
    # platforms the user never opted into, and the gateway then tries to
    # connect to Discord / Teams / Google Chat with no token and emits
    # noisy retry-forever errors.  ``_platform_status`` was already fixed
    # for the same bug class in commit 7849a3d73; this is the runtime
    # counterpart.
```

依据充分:这段注释**逐字定义**了 `check_fn` 与 `is_connected` 的语义差,
并**点名** `_platform_status` 是同一 bug class 的先例。
**这就是判定 §7 那一份为 ■ 的直接依据——它是这个 bug class 的第三例,没被修。**

`check_fn` 还有**副作用**,这一点是本条移交项的隐藏爆点:

`gateway/config.py:2625 @ 863e313`

```python
            # Verify dependencies LAST — only for platforms that are already
            # enabled or passed the credential gate above.  For adapter plugins
            # ``check_fn`` lazy-INSTALLS the platform SDK (pip) as a side
            # effect, so running it as an unconditional sweep over every
            # registered platform made ``load_gateway_config()`` pip-install
            # Discord/Telegram/Slack/Feishu/Dingtalk on every call — including
            # the desktop/dashboard readiness probe (``GET /api/status``, which
            # awaits this synchronously) — even when the user configured none
            # of them.  That blocked startup until every install finished and
            # caused the desktop app to time out and boot-loop (stuck at 94%).
            try:
                if not entry.check_fn():
                    continue
```

**"unconditional sweep over every registered platform" —— 这正是 §7.1 那段插件块
现在还在做的事。** 桌面端 boot-loop(卡在 94%)的病根被从 `load_gateway_config()` 里摘掉了,
但同一段代码形状在 `status.py` 里原封不动地留着。

### 5.2 `hermes_cli/gateway.py` 的 `_platform_status` —— **有意**,但有一处 ◎ 保守

`hermes_cli/gateway.py:5437 @ 863e313`

```python
    entry = platform.get("_registry_entry")
    if entry is not None:
        configured = False
        # Prefer is_connected (checks both env and config.yaml) over
        # check_fn (typically just dependency / env presence).
        if entry.is_connected is not None:
            try:
                from gateway.config import PlatformConfig

                synthetic = PlatformConfig(enabled=True)
                configured = bool(entry.is_connected(synthetic))
            except Exception:
                configured = False
        else:
            # No is_connected hook — fall back to check_fn as a coarse
            # "are deps present" gate. Don't fall back when is_connected
            # is defined and returned False; that would let "SDK is
            # installed" override "no token configured" and incorrectly
            # report the platform as ready.
            try:
                configured = bool(entry.check_fn())
            except Exception:
                configured = False
        return "configured" if configured else "not configured"
```

**这段注释就是本移交项的"标准答案"**:"Don't fall back when `is_connected` is defined and
returned False; that would let *SDK is installed* override *no token configured* and
incorrectly report the platform as ready."——把 §7 要复现的现象一字不差地预言了。

◎ 保守之处:它传的是 `PlatformConfig(enabled=True)` 这个**空的合成对象**,不是
`load_gateway_config()` 出来的真实 cfg。对**只在 config.yaml 里写了 token、没设环境变量**的平台,
`is_connected` 拿不到 `config.token`,只能回退去读环境变量。多数插件的 `is_connected` 都写了
"env 或 extra"双读(如 Telegram 见下),所以实际影响小;但语义上这是"用一个空壳去问会不会连上",
与真值路径读真实 cfg 不同。**这是 setup 场景的合理取舍**(setup 时 gateway 未必能加载),
不判 ■。

`plugins/platforms/telegram/adapter.py:9933 @ 863e313`

```python
def _is_connected(config) -> bool:
    """Telegram is connected when a bot token is configured.

    check_telegram_requirements() only verifies the python-telegram-bot SDK is
    importable, NOT that a token is set — so without this is_connected the
    registry-driven plugin-enable pass in gateway/config.py would enable
    Telegram on any machine that merely has the SDK installed. Gate on the
    token (env or PlatformConfig.token), matching the generic token check
    Telegram had as a built-in.
    """
    token = getattr(config, "token", None)
    if not token:
        import hermes_cli.gateway as gateway_mod
        token = gateway_mod.get_env_value("TELEGRAM_BOT_TOKEN") or ""
    return bool(str(token).strip())
```

### 5.3 `hermes_cli/web_server.py` 的 profile-scoped 分支 —— **有意**,依据是代码里写着的

`hermes_cli/web_server.py:8315 @ 863e313`

```python
    if scoped:
        # Profile-scoped view: derive enablement/configuration from the
        # profile's config.yaml + .env only. load_gateway_config()'s
        # env-override layer reads os.environ and would leak the root
        # install's tokens into the profile's reported state.
        try:
            cfg = load_config()
            platforms_cfg = cfg.get("platforms") or {}
            plat_cfg = platforms_cfg.get(platform_id)
            if not isinstance(plat_cfg, dict):
                plat_cfg = {}
            enabled = bool(plat_cfg.get("enabled"))
            hc = plat_cfg.get("home_channel")
            home_channel = hc if isinstance(hc, dict) else None
        except Exception:
            enabled = False
            home_channel = None
        configured = all(env_on_disk.get(key) for key in entry["required_env"])
```

**依据**:`_is_platform_connected` 会经 `load_gateway_config()` 的 env-override 层读 `os.environ`,
而 dashboard 进程的 `os.environ` 装的是**根安装**的 `.env`。对 profile 视图用真值函数会
**把根凭据当成 profile 的凭据报出来**。所以这里刻意降级为"只看这个 profile 磁盘上的 `.env`"。
**这是隔离要求压过一致性要求,判有意。** 同函数的非 scoped 分支就老老实实用真值:

`hermes_cli/web_server.py:8333 @ 863e313`

```python
    else:
        try:
            gateway_config, platform, platform_config = _gateway_platform_config(
                platform_id
            )
            enabled = bool(platform_config and platform_config.enabled)
            configured = bool(
                platform_config
                and gateway_config._is_platform_connected(platform, platform_config)
            )
```

`web_server.py` 是 8 份里**唯一**逐字复用真值函数的一份,应作为其余各份的改造范本。

### 5.4 `cron/scheduler.py` 的实际投递路径 —— **有意**

`cron/scheduler.py:1606 @ 863e313`

```python
        if not pconfig or not pconfig.enabled:
            msg = f"platform '{platform_name}' not configured/enabled"
            logger.warning("Job '%s': %s", job["id"], msg)
            delivery_errors.append(msg)
            continue
```

**依据**:这是**投递时刻**,不是**列举时刻**。上游 `cron_delivery_targets()`(#3)已用真值筛过一遍;
到这里再跑一次 `is_connected` 只会重复代价,而真正的失败(token 过期、被踢出频道)`is_connected`
本来也测不出来——它只看"配没配",不看"连没连"。真实失败由 adapter 在 send 时抛出并进
`delivery_errors`。**"列举用严判据、执行让它响亮地失败"是合理分工,判有意。**
唯一瑕疵是错误文案 `not configured/enabled` 把两件事混说,但那是文案问题。

### 5.5 `hermes_cli/dump.py` 的 `_configured_platforms` —— ■

`hermes_cli/dump.py:181 @ 863e313`

```python
def _configured_platforms() -> list[str]:
    """Return list of configured messaging platform names."""
    checks = {
        "telegram": "TELEGRAM_BOT_TOKEN",
        "discord": "DISCORD_BOT_TOKEN",
        "slack": "SLACK_BOT_TOKEN",
        "whatsapp": "WHATSAPP_ENABLED",
        "signal": "SIGNAL_HTTP_URL",
        "email": "EMAIL_ADDRESS",
        "sms": "TWILIO_ACCOUNT_SID",
        "matrix": "MATRIX_HOMESERVER_URL",
        "mattermost": "MATTERMOST_URL",
        "homeassistant": "HASS_TOKEN",
        "dingtalk": "DINGTALK_CLIENT_ID",
        "feishu": "FEISHU_APP_ID",
        "wecom": "WECOM_BOT_ID",
        "wecom_callback": "WECOM_CALLBACK_CORP_ID",
        "weixin": "WEIXIN_ACCOUNT_ID",
        "qqbot": "QQ_APP_ID",
    }
    return [name for name, env in checks.items() if os.getenv(env)]
```

**失效链**(用户可见现象,从输入到后果):

1. 用户只在 `~/.hermes/config.yaml` 里配 `platforms.telegram.token`(**这是被支持的配置法**——
   真值瀑布第二级 `if config.token or config.api_key: return True` 就是为它准备的),
   不设 `TELEGRAM_BOT_TOKEN` 环境变量。
2. gateway 正常跑,Telegram 正常收发消息。
3. 用户去开 issue,按文档跑 `hermes dump` 附诊断信息。
4. `_configured_platforms()` 只 `os.getenv("TELEGRAM_BOT_TOKEN")` → 空 → 该平台**不出现在 dump 里**。
5. dump 输出 `platforms:          none`。
6. **维护者拿到一份写着"没配任何平台"的诊断报告,去排查一个 Telegram 的 bug。**
   诊断工具撒谎,比没有诊断工具更坏——这是判 ■ 而非 ◎ 的理由。

另外三处从属缺陷:
- 单变量判定对多变量平台是错的:`weixin` 真值要求 `account_id` **且** token(§2.2 瀑布第一级),
  这里只查 `WEIXIN_ACCOUNT_ID`。
- `matrix` 查的是 `MATRIX_HOMESERVER_URL`,而已修的孪生查的是 `MATRIX_HOMESERVER`,
  **两份对同一个平台用了不同的变量名**:

`hermes_cli/gateway.py:5489 @ 863e313`

```python
    if platform.get("key") == "matrix":
        homeserver = get_env_value("MATRIX_HOMESERVER")
        password = get_env_value("MATRIX_PASSWORD")
        if (val or password) and homeserver:
```

- 闭集,漏 `bluebubbles` / `yuanbao` / `whatsapp_cloud` / `webhook` / `api_server` /
  `msgraph_webhook` / `relay`,以及全部插件专有平台(irc / teams / ntfy / google_chat /
  line / photon / raft / simplex / buzz / a2a)。

### 5.6 `hermes_cli/tools_config.py` 的 `_get_enabled_platforms` —— ■

`hermes_cli/tools_config.py:2074 @ 863e313`

```python
def _get_enabled_platforms() -> List[str]:
    """Return platform keys that are configured (have tokens or are CLI)."""
    enabled = ["cli"]
    if get_env_value("TELEGRAM_BOT_TOKEN"):
        enabled.append("telegram")
    if get_env_value("DISCORD_BOT_TOKEN"):
        enabled.append("discord")
    if get_env_value("SLACK_BOT_TOKEN"):
        enabled.append("slack")
    if get_env_value("WHATSAPP_ENABLED"):
        enabled.append("whatsapp")
    if get_env_value("QQ_APP_ID"):
        enabled.append("qqbot")
    return enabled
```

**这份最窄:5 个平台。** 它比 dump 更危险,因为它不只是"显示",它**决定 `hermes tools` 给哪些平台
配工具集**。

**失效链**:

1. 用户用 IRC(插件平台,配好了、gateway 里能用)。
2. 跑 `hermes tools`,想给 IRC 单独收紧工具集。
3. `_get_enabled_platforms()` 里根本没有 `irc` 分支,`_platform_toolset_summary` 因此不给它建条目:

`hermes_cli/tools_config.py:2097 @ 863e313`

```python
    if platforms is None:
        platforms = _get_enabled_platforms()

    summary: Dict[str, Set[str]] = {}
    for pkey in platforms:
        summary[pkey] = _get_platform_tools(config, pkey)
    return summary
```

4. **用户在 UI 里看不到 IRC,无法为它配置逐平台工具集**;IRC 会话继续吃默认工具集。
5. 现象是"功能对某些平台不存在",而非报错——用户只会以为自己不会用。

同一失效对 signal / matrix / mattermost / email / sms / feishu / wecom / weixin /
bluebubbles / yuanbao / dingtalk / homeassistant 以及全部插件平台成立(共 18 个,见 §6.1)。

### 5.7 仓库根 `cli.py` 的 `_show_gateway_status` —— ■(轻,但语义是错的)

判据只有 `pconfig.enabled`(原文见 §2.3)。**`enabled` 与 "configured" 不是一回事**——真值函数存在的全部理由
就是这两者要分开。用户在 config.yaml 里写了 `platforms.discord.enabled: true` 但没给 token 时:

- `/gateway` 打印 `✓ Discord      Enabled`
- `get_connected_platforms()` **不含** Discord,gateway 不会为它建 adapter
- 用户看着"✓ Enabled"却收不到任何消息,且**这个界面不给任何线索**

而 `else` 分支打印的 `Not configured (TELEGRAM_BOT_TOKEN)` 又暗示"判据是这个环境变量",
与实际判据(`enabled` 标志)不符,进一步误导。

### 5.8 `hermes_cli/status.py` —— ■ 主缺陷,见 §7

---

## 6. 平台清单本身是否一致

### 6.1 九份各自认识的平台集合(AST 静态抽取)

```text
gateway/config.py (Platform 枚举,除 local)        n= 23   ← 基准
cron/scheduler.py _KNOWN_DELIVERY_PLATFORMS       n= 19
cron/scheduler.py _HOME_TARGET_ENV_VARS           n= 16
hermes_cli/gateway.py _PLATFORMS                  n=  6   (+ 注册表,开集)
hermes_cli/web_server.py _PLATFORM_OVERRIDES      n= 31   (+ 枚举 + 注册表,开集)
hermes_cli/dump.py _configured_platforms          n= 16   闭集
hermes_cli/tools_config.py _get_enabled_platforms n=  5   闭集
hermes_cli/status.py platforms{}                  n= 15   (+ 注册表,但见 §7)
cli.py _show_gateway_status                       n=  4   闭集

=== 相对 Platform 枚举(23)缺了谁 ===
_KNOWN_DELIVERY_PLATFORMS   missing = api_server, msgraph_webhook, relay, whatsapp_cloud
_HOME_TARGET_ENV_VARS       missing = api_server, homeassistant, msgraph_webhook, relay,
                                      webhook, wecom_callback, yuanbao
hermes_cli/gateway.py       missing = api_server, dingtalk, discord, email, feishu,
                                      homeassistant, matrix, msgraph_webhook, relay, slack,
                                      sms, telegram, webhook, wecom, wecom_callback,
                                      whatsapp, whatsapp_cloud      [多数由注册表补回]
hermes_cli/web_server.py    missing = (无)
hermes_cli/dump.py          missing = api_server, bluebubbles, msgraph_webhook, relay,
                                      webhook, whatsapp_cloud, yuanbao
hermes_cli/tools_config.py  missing = api_server, bluebubbles, dingtalk, email, feishu,
                                      homeassistant, matrix, mattermost, msgraph_webhook,
                                      relay, signal, sms, webhook, wecom, wecom_callback,
                                      weixin, whatsapp_cloud, yuanbao      (18 个)
hermes_cli/status.py        missing = api_server, homeassistant, matrix, mattermost,
                                      msgraph_webhook, relay, webhook, whatsapp_cloud
cli.py                      missing = api_server, bluebubbles, dingtalk, email, feishu,
                                      homeassistant, matrix, mattermost, msgraph_webhook,
                                      qqbot, relay, signal, sms, webhook, wecom,
                                      wecom_callback, weixin, whatsapp_cloud, yuanbao (19 个)
```

**没有任何两份的平台集合相同。** 「新增一个平台要改 8 处」是保守说法——
`_PLATFORM_OVERRIDES` 一份就是 31 条,加上 `_KNOWN_DELIVERY_PLATFORMS`、
`_HOME_TARGET_ENV_VARS`、四份闭集写死表,新增一个内置平台要动的字面量表**至少 7 张**。

**注册表(`platform_registry`)本来是为解掉这个问题引入的**——`hermes_cli/gateway.py` 与
`hermes_cli/web_server.py` 已经迁过去了(开集),`hermes_cli/status.py` 迁了一半(见 §7),
`dump.py` / `tools_config.py` / `cli.py` 完全没迁。客观计数:

```console
$ for f in ...; do grep -c 'platform_registry' $f; grep -c 'discover_plugins' $f; done
gateway/config.py              platform_registry=8 discover_plugins=7
cron/scheduler.py              platform_registry=4 discover_plugins=4
hermes_cli/gateway.py          platform_registry=3 discover_plugins=2
hermes_cli/setup.py            platform_registry=0 discover_plugins=0   ← 委托,合理
hermes_cli/web_server.py       platform_registry=3 discover_plugins=3
hermes_cli/dump.py             platform_registry=0 discover_plugins=0   ← 闭集
hermes_cli/tools_config.py     platform_registry=0 discover_plugins=4   ← 用于工具,不用于平台
hermes_cli/status.py           platform_registry=2 discover_plugins=0   ← ★ 只查不发现
cli.py                         platform_registry=0 discover_plugins=2   ← 不用于平台
```

`hermes_cli/status.py` 那行 `platform_registry=2 discover_plugins=0` 是整张表里最反常的一行,
§7 会看到它的后果。

### 6.2 ■ `whatsapp_cloud` 永远进不了 cron 投递下拉框

`cron/scheduler.py:276 @ 863e313`

```python
    "weixin": "WEIXIN_HOME_CHANNEL",
    "bluebubbles": "BLUEBUBBLES_HOME_CHANNEL",
    "qqbot": "QQBOT_HOME_CHANNEL",
    "whatsapp": "WHATSAPP_HOME_CHANNEL",
    "whatsapp_cloud": "WHATSAPP_CLOUD_HOME_CHANNEL",
}
```

`whatsapp_cloud` **在** `_HOME_TARGET_ENV_VARS` 里。但:

`cron/scheduler.py:253 @ 863e313`

```python
# Valid delivery platforms — used to validate user-supplied platform names
# in cron delivery targets, preventing env var enumeration via crafted names.
_KNOWN_DELIVERY_PLATFORMS = frozenset({
    "telegram", "discord", "slack", "whatsapp", "signal",
    "matrix", "mattermost", "homeassistant", "dingtalk", "feishu",
    "wecom", "wecom_callback", "weixin", "sms", "email", "webhook", "bluebubbles",
    "qqbot", "yuanbao",
})
```

**不在**。而插件补救路径也不通——`whatsapp_cloud` 不是插件(`plugins/platforms/` 下无此目录,
它是 `gateway/platforms/whatsapp_cloud.py` 内置适配器),没有 `PlatformEntry`,
故 `cron_deliver_env_var` 为空:

`cron/scheduler.py:1017 @ 863e313`

```python
def _is_known_delivery_platform(platform_name: str) -> bool:
    """Whether ``platform_name`` is a valid cron delivery target.

    Hardcoded built-ins in ``_KNOWN_DELIVERY_PLATFORMS`` are checked first;
    plugin platforms registered via ``PlatformEntry`` are accepted if they
    provide a ``cron_deliver_env_var``.
    """
    name = platform_name.lower()
    if name in _KNOWN_DELIVERY_PLATFORMS:
        return True
    return bool(_plugin_cron_env_var(name))
```

实测(基线只读探针,脚本在 `/tmp/probe_r8c.py`):

```console
$ python probe.py
_HOME_TARGET_ENV_VARS keys not in _KNOWN_DELIVERY_PLATFORMS:
   'whatsapp_cloud': plugin_cron_env_var='' -> _is_known_delivery_platform=False

_KNOWN_DELIVERY_PLATFORMS size: 19
_HOME_TARGET_ENV_VARS size: 16

delivery platforms with NO home env var (can be named but never resolve a home target):
   'homeassistant' -> plugin_cron_env_var=''
   'webhook' -> plugin_cron_env_var=''
   'wecom_callback' -> plugin_cron_env_var=''
   'yuanbao' -> plugin_cron_env_var=''
```

**失效链**:用户设了 `WHATSAPP_CLOUD_HOME_CHANNEL`(这个变量名存在、被 `_resolve_home_env_var`
认识)→ 期望 cron 能投到 WhatsApp Cloud → `cron_delivery_targets()` 的过滤(§4 已引那段的末两行
`if not _is_known_delivery_platform(name): continue`)把它拦掉 → dashboard 下拉框里**没有这个选项**。显式指定 `deliver=whatsapp_cloud` 也一样:

`cron/scheduler.py:1231 @ 863e313`

```python
    if not _is_known_delivery_platform(platform_name):
        return None
    chat_id = _get_home_target_chat_id(platform_name)
    if not chat_id:
        return None
```

→ 返回 `None`,**投递静默落空**(当作 local 处理)。
修法是一行:把 `"whatsapp_cloud"` 加进 `_KNOWN_DELIVERY_PLATFORMS`。

反向的 4 个(`homeassistant` / `webhook` / `wecom_callback` / `yuanbao`)是**合法投递名但无 home 变量**,
只影响 `deliver=origin` 的 home 回退,不影响显式 `platform:chat_id`,危害小得多,记 ◇ 不记 ■。

---

## 7. `hermes_cli/status.py` 的失效链 —— 实测复现

### 7.1 代码

`hermes_cli/status.py:469 @ 863e313`

```python
    platforms = {
        "Telegram": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_HOME_CHANNEL"),
        "Discord": ("DISCORD_BOT_TOKEN", "DISCORD_HOME_CHANNEL"),
        "WhatsApp": ("WHATSAPP_ENABLED", None),
        "Signal": ("SIGNAL_HTTP_URL", "SIGNAL_HOME_CHANNEL"),
        "Slack": ("SLACK_BOT_TOKEN", None),
        "Email": ("EMAIL_ADDRESS", "EMAIL_HOME_ADDRESS"),
        "SMS": ("TWILIO_ACCOUNT_SID", "SMS_HOME_CHANNEL"),
        "DingTalk": ("DINGTALK_CLIENT_ID", None),
        "Feishu": ("FEISHU_APP_ID", "FEISHU_HOME_CHANNEL"),
        "WeCom": ("WECOM_BOT_ID", "WECOM_HOME_CHANNEL"),
        "WeCom Callback": ("WECOM_CALLBACK_CORP_ID", None),
        "Weixin": ("WEIXIN_ACCOUNT_ID", "WEIXIN_HOME_CHANNEL"),
        "BlueBubbles": ("BLUEBUBBLES_SERVER_URL", "BLUEBUBBLES_HOME_CHANNEL"),
        "QQBot": ("QQ_APP_ID", "QQ_HOME_CHANNEL"),
        "Yuanbao": ("YUANBAO_APP_ID", "YUANBAO_HOME_CHANNEL"),
    }
```

`hermes_cli/status.py:504 @ 863e313`

```python
    # Plugin-registered platforms
    try:
        from gateway.platform_registry import platform_registry
        for entry in platform_registry.plugin_entries():
            configured = entry.check_fn()
            status_str = "configured" if configured else "not configured"
            label = entry.label
            print(f"  {label:<12}  {check_mark(configured)} {status_str} (plugin)")
    except Exception:
        pass
```

三个问题叠在一起:

- **(a)** 用 `entry.check_fn()` 而不是 `entry.is_connected` —— 就是 §5.1 注释点名的 bug class;
- **(b)** 对**每一个**注册平台**无条件**调 `check_fn()` —— 就是 §5.1 第二段注释点名的
  "unconditional sweep",对 adapter 插件会**触发 pip 安装**;
- **(c)** 从不调 `discover_plugins()` —— 于是这段代码**要么完全不执行,要么全错**,取决于进程。

### 7.2 (c) 的两面性:同一段代码,两个进程,两种表现

实测 A —— `hermes status` 子命令。它对 `show_status` 是懒导入,别的什么都没导:

`hermes_cli/main.py:4574 @ 863e313`

```python
def cmd_status(args):
    """Show status of all components."""
    from hermes_cli.status import show_status

    show_status(args)
```


```console
$ python -c "import hermes_cli.main; import hermes_cli.status; <count plugin_entries>"
plugin_entries() after `import hermes_cli.main` + `import hermes_cli.status`: 0
$ <run show_status(), lazy_deps.ensure neutered>
--- Messaging Platforms section as `hermes status` prints it ---
Telegram      ✗ not configured
  ... (共 15 行,全部来自写死表)
  Yuanbao       ✗ not configured
--- (plugin) lines: 0 ---
plugin_entries() after show_status ran: 0
```

**插件块一行都没打印**——因为没人替它跑发现。所以在 `hermes status` 里,(a)(b) 是**哑弹**,
真正的现象是 **◇ 缺失**:15 个写死平台之外的全部平台(matrix、mattermost、homeassistant、
irc、teams、ntfy、google_chat、line、photon、raft、simplex、buzz、a2a……)在
`hermes status` 里**根本不出现**,哪怕配好了、正在收发消息。

实测 B —— CLI / agent 进程内的 `/status`,走的是同一个 `show_status`:

`hermes_cli/console_engine.py:1273 @ 863e313`

```python
def _status(_engine: HermesConsoleEngine, args: list[str]) -> str:
    _expect_no_args(args, "status")
    from types import SimpleNamespace

    from hermes_cli.status import show_status

    output = _capture_output(lambda: show_status(SimpleNamespace(all=False, deep=False)))
    return _strip_console_status_footer(output)
```

差别只在于:这个进程导入了 `model_tools`,而 `model_tools` 在模块顶层就跑了发现:

`model_tools.py:229 @ 863e313`

```python
# Plugin tool discovery (user/project/pip plugins)
try:
    from hermes_cli.plugins import discover_plugins
    discover_plugins()
```


```console
$ python -c "import model_tools; <count>; then run show_status()"
plugin_entries() after `import model_tools`: 23
--- Messaging Platforms section (in-process WITH discovery done) ---
Telegram      ✗ not configured
  Discord       ✗ not configured
  WhatsApp      ✗ not configured
  Signal        ✗ not configured
  Slack         ✗ not configured
  Email         ✗ not configured
  SMS           ✗ not configured
  DingTalk      ✗ not configured
  Feishu        ✗ not configured
  WeCom         ✗ not configured
  WeCom Callback  ✗ not configured
  Weixin        ✗ not configured
  BlueBubbles   ✗ not configured
  QQBot         ✗ not configured
  Yuanbao       ✗ not configured
  A2A           ✓ configured (plugin)          ← 假阳性
  Buzz          ✗ not configured (plugin)
  DingTalk      ✗ not configured (plugin)      ← 与上面第 8 行重复
  Discord       ✗ not configured (plugin)      ← 与上面第 2 行重复
  Email         ✗ not configured (plugin)      ← 重复
  Feishu / Lark  ✓ configured (plugin)         ← 假阳性,且与第 9 行相反
  Google Chat   ✗ not configured (plugin)
  Home Assistant  ✓ configured (plugin)        ← 假阳性
  IRC           ✗ not configured (plugin)
  LINE          ✗ not configured (plugin)
  Matrix        ✗ not configured (plugin)
  Mattermost    ✓ configured (plugin)          ← 假阳性
  ntfy          ✗ not configured (plugin)
  iMessage via Photon  ✓ configured (plugin)   ← 假阳性
  Raft          ✗ not configured (plugin)
  SimpleX Chat  ✗ not configured (plugin)
  Slack         ✗ not configured (plugin)      ← 重复
  SMS (Twilio)  ✗ not configured (plugin)      ← 重复
  Microsoft Teams  ✗ not configured (plugin)
  Telegram      ✗ not configured (plugin)      ← 重复
  WeCom (Enterprise WeChat)  ✓ configured (plugin)  ← 假阳性,与第 10 行相反
  WeCom Callback (self-built apps)  ✗ not configured (plugin)  ← 重复
  WhatsApp      ✓ configured (plugin)          ← 假阳性,与第 3 行相反
--- (plugin) lines: 23 ---
```

**这台机器上一个消息平台凭据都没有。** 环境自查(排除"其实配了"的可能):

```console
relevant env vars present: {'MAX_THINKING_TOKENS': …, 'CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR': …,
 'GH_TOKEN': …, 'GITHUB_TOKEN': …, 'CLOUDSDK_AUTH_ACCESS_TOKEN': …, 'AWS_SECRET_ACCESS_KEY': …,
 'CLAUDE_SESSION_INGRESS_TOKEN_FILE': …}
```

全是 Claude / GitHub / AWS 的,**无一个 messaging 平台变量**;`HERMES_HOME` 指向空目录 `/tmp/r8c-home`。

### 7.3 假阳性的精确规模

逐个 plugin 对比 `check_fn()`(status.py 用的)与 `is_connected()`(真值用的):

```console
plugin                  check_fn()  is_connected()   verdict
a2a                           True           False   <== FALSE POSITIVE in hermes status
buzz                         False           False
dingtalk                     False           False
discord                      False           False
email                        False           False
feishu                        True           False   <== FALSE POSITIVE
google_chat                  False           False
homeassistant                 True           False   <== FALSE POSITIVE
irc                          False           False
line                         False           False
matrix                       False           False
mattermost                    True           False   <== FALSE POSITIVE
ntfy                         False           False
photon                        True           False   <== FALSE POSITIVE
raft                         False           False
simplex                      False           False
slack                        False           False
sms                          False           False
teams                        False           False
telegram                     False           False
wecom                         True           False   <== FALSE POSITIVE
wecom_callback               False           False
whatsapp                      True           False   <== FALSE POSITIVE

plugins where status.py says configured but is_connected says NOT: 7
```

**23 个插件平台全部注册了 `is_connected` 钩子**(上表 `is_connected()` 列无一为 `None`)——
也就是说 `status.py` 每一次用 `check_fn` 都是在**覆盖一个现成的、更准确的信号**,
从来不是 §5.2 那段注释里说的"没有钩子只好回落"的情形。

`discord` / `telegram` / `slack` / `teams` 这 4 个之所以现在是 False,只因本容器**没装它们的 SDK**
(§1.2)。把 SDK 标志置为可用后:

```console
entry.check_fn.__module__ = hermes_plugins.telegram_platform.adapter
module file = /home/user/hermes-agent/plugins/platforms/telegram/adapter.py
TELEGRAM_AVAILABLE (before) = False
check_fn() with SDK 'installed' = True
is_connected() (no token)       = False
discord   flags=['DISCORD_AVAILABLE'] -> check_fn()=True   is_connected()=False
slack     flags=['SLACK_AVAILABLE'] -> check_fn()=True   is_connected()=False
teams     flags=['AIOHTTP_AVAILABLE', 'TEAMS_SDK_AVAILABLE'] -> check_fn()=True   is_connected()=False
matrix    flags=[] -> check_fn()=False  is_connected()=False
```

**装齐 SDK 的常规机器上,假阳性从 7 涨到 11 / 23。**
(注:插件在 `hermes_plugins.<name>_platform.adapter` 这个**独立模块命名空间**下加载,
不是 `plugins.platforms.<name>.adapter`;直接 patch 后者不会生效——这一点值得记下,
写针对插件的测试时容易踩。)

Teams 的 `check_fn` 是最干净的反例——**纯依赖探针,一个凭据都不看**:

`plugins/platforms/teams/adapter.py:419 @ 863e313`

```python
def check_requirements() -> bool:
    """Return True when all Teams dependencies and credentials are present."""
    return TEAMS_SDK_AVAILABLE and AIOHTTP_AVAILABLE
```

▲ **文档与代码矛盾(就在同一行)**:docstring 写 "all Teams dependencies **and credentials**",
函数体只查两个 SDK 可用性标志,**一个凭据都没查**。凭据检查在同文件 `validate_config` /
`is_connected` 里。

### 7.4 两份实现同题不同解(端到端对拍)

```console
A) Teams, SDK installed, ZERO credentials configured:
   check_fn()     = True
   is_connected() = False

B) Same PlatformEntry, same env (no credentials):
   hermes_cli/status.py:508  (entry.check_fn())      -> 'configured'
   hermes_cli/gateway.py:5442(entry.is_connected())  -> 'not configured'
   DIVERGE: True
```

### 7.5 ■ 第二重:pip 副作用

§7.1 那段插件块里的 `entry.check_fn()` 无条件扫描,对 adapter 插件会**触发 pip 安装**
(§5.1 引的那段注释逐字描述了这个副作用与它造成的桌面端 boot-loop)。
本轮所有探针都把 `tools.lazy_deps.ensure` 换成了 no-op,**故意没有让它真的装**——
所以上表 `check_fn()` 那一列对 SDK 未装的平台读到 False。
在真实用户机器上,`/status` 会为**每一个**未装 SDK 的平台尝试 pip 安装。

**失效链**:用户在 CLI 里敲 `/status` 想看一眼状态 → 进程对 23 个插件逐个 `check_fn()` →
Discord / Telegram / Slack / Feishu / Dingtalk 的 `check_fn` 走 `lazy_deps.ensure(...)` →
**一条状态查询命令开始从 PyPI 装包**,阻塞到全部装完 → 装完后这些平台又因 SDK 就位而
被报成 `✓ configured`,尽管用户从未配过它们。

---

## 8. 配套测试:实跑与"没有测试钉住一致性"

### 8.1 实跑结果(环境见 §1.2:87 包)

```console
$ HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
    tests/gateway/test_platform_connected_checkers.py tests/gateway/test_platform_registry.py \
    tests/hermes_cli/test_setup_irc.py tests/gateway/test_config.py
=== Summary: 4 files, 80 tests passed, 0 failed (100% complete) in 12.5s (8 workers) ===

$ HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
    tests/cron/test_scheduler.py tests/hermes_cli/test_status.py \
    tests/hermes_cli/test_tools_config.py tests/gateway/test_google_chat.py
=== Summary: 4 files, 166 tests passed, 0 failed (100% complete) in 3.8s (8 workers) ===
```

**合计 8 个文件、246 个用例、0 失败。**(venv 87 包;未触及 §CLAUDE.md 已知的 5 个环境性必然失败用例。)

### 8.2 现有测试钉住了什么

| 测试 | 钉住了 | 没钉住 |
|---|---|---|
| `test_startup_no_eager_platform_install.py` | `_apply_env_overrides` 必须先问 `is_connected` 再跑会装包的 `check_fn` | **只覆盖 `gateway/config.py` 一处**;§7.1 的同形代码不在射程内 |
| `test_setup_irc.py` | `_platform_status` 对插件平台的 configured 判定 | 只验 IRC 一个平台;不与其他 7 份对拍 |
| `test_platform_connected_checkers.py` | 每个内置平台要么有 checker 要么走通用 token 路径 | 只管 `gateway/config.py` 内部 |
| `test_scheduler.py::TestCronDeliveryTargets` | `cron_delivery_targets` 用 `get_connected_platforms` 筛选 | 只喂 matrix/telegram 两个;不覆盖 `whatsapp_cloud` 缺口 |

三份钉住判定的测试逐字如下,可见射程之窄:

`tests/hermes_cli/test_setup_irc.py:82 @ 863e313`

```python
    def test_irc_status_configured_when_env_set(self, monkeypatch):
        """After the user sets IRC_SERVER and IRC_CHANNEL, status is 'configured'."""
        import hermes_cli.gateway as gateway_mod

        plat = _register_irc_platform()
        try:
            monkeypatch.setenv("IRC_SERVER", "irc.libera.chat")
            monkeypatch.setenv("IRC_CHANNEL", "#hermes")
            monkeypatch.setenv("IRC_NICKNAME", "hermes-bot")

            status = gateway_mod._platform_status(plat)
            assert status == "configured"
```

`tests/gateway/test_platform_connected_checkers.py:14 @ 863e313`

```python
def test_all_builtins_have_checker_or_generic_token_path():
    """Every built-in Platform member must be reachable by either:

    1. The generic ``config.token or config.api_key`` check, OR
    2. A platform-specific entry in ``_PLATFORM_CONNECTED_CHECKERS``.
```

`tests/cron/test_scheduler.py:1592 @ 863e313`

```python
    def test_lists_configured_platforms_flagging_missing_home_channel(self, monkeypatch):
        from cron.scheduler import cron_delivery_targets

        self._patch_connected(monkeypatch, ["matrix", "telegram"])
        monkeypatch.delenv("MATRIX_HOME_ROOM", raising=False)
        monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)

        targets = {t["id"]: t for t in cron_delivery_targets()}

        assert set(targets) == {"matrix", "telegram"}
```


`tests/gateway/test_startup_no_eager_platform_install.py:1 @ 863e313`

```python
"""Regression tests: ``_apply_env_overrides`` must not lazy-install platform
SDKs for platforms the user has not configured.
```

射程写死在标题里:`_apply_env_overrides`。

### 8.3 ■ 没有任何测试钉住这 8 份的一致性 —— 而且守卫类是空的

**全仓没有一个测试断言"这 N 份就绪判定给出同样的答案"。** 搜索面见 §9.3。

更值得记的是:仓库里**存在**一个专为这类一致性写的回归守卫类,**类体只有 docstring**:

`tests/cron/test_scheduler.py:1608 @ 863e313`

```python
class TestHomeTargetEnvVarRegistry:
    """Regression: ``_HOME_TARGET_ENV_VARS`` must include every gateway
    platform that supports cron-driven outbound delivery. Missing an
    entry means ``hermes cron create --deliver=<platform>`` silently
    fails to route through the platform's home channel."""
```

AST 复核(不是靠肉眼):

```console
TestCronDeliveryTargets @ line 1569: non-docstring body items = 2; test methods = ['_patch_connected', 'test_lists_configured_platforms_flagging_missing_home_channel']
TestHomeTargetEnvVarRegistry @ line 1608: non-docstring body items = 0; test methods = []

Test* classes total=6572, docstring-only(empty)=14
   ('tests/cron/test_cron_workdir.py', 'TestTickWorkdirPartition', 140)
   ('tests/cron/test_scheduler.py', 'TestHomeTargetEnvVarRegistry', 1608)
   ('tests/hermes_cli/test_detect_api_mode_for_url.py', 'TestAnthropicMessagesDetection', 52)
   ('tests/hermes_cli/test_model_normalize.py', 'TestAggregatorProviders', 75)
   ('tests/hermes_cli/test_model_normalize.py', 'TestAnthropicDotToHyphen', 39)
   ('tests/hermes_cli/test_model_normalize.py', 'TestCopilotDotPreservation', 51)
   ('tests/hermes_cli/test_model_normalize.py', 'TestCustomProviderIsNotAVendorIdentity', 79)
   ('tests/hermes_cli/test_model_normalize.py', 'TestOpenCodeZenModelNormalization', 45)
   ('tests/hermes_cli/test_ollama_cloud_auth.py', 'TestCLIStateUpdate', 346)
   ('tests/hermes_cli/test_update_yes_flag.py', 'TestUpdateYesStashRestore', 135)
   ('tests/plugins/web/test_web_search_provider_plugins.py', 'TestAsyncExtractDispatch', 302)
   ('tests/plugins/web/test_web_search_provider_plugins.py', 'TestErrorResponseShapes', 311)
   ('tests/tools/test_approval_plugin_hooks.py', 'TestGatewayPathFiresHooks', 147)
   ('tests/tools/test_browser_chromium_check.py', 'TestRunBrowserCommandChromiumGuard', 80)
```

6572 个 `Test*` 类里只有 14 个是空的(0.2%),所以这**不是**该仓库的普遍写法,
而是一个**被写下标题、没写正文**的守卫。它承诺检查的正是 §6.2 那个缺口
(`_HOME_TARGET_ENV_VARS` vs 投递平台集),而那个缺口**至今存在**——
守卫是空的,所以缺口没被拦住。**这是"移交项只留标题、没留证据"这一失败模式在被研究仓库自身的实例。**

---

## 9. 搜索面(负结论的支撑)

### 9.1 "只有这 13 个判定点" 的依据

**R11C 片 C 改:围栏由 ```verify 改为 ```text —— 块里是「搜索面 + 逐条判读」的说明,
不是一条可以整块喂给 bash 的命令**(原样跑到第 5 行就报
`bash: -c: line 5: '· gateway/config.py ...'`)。块里逐条列出的 `grep` 模式本身仍可单跑,
它们是这条负结论的搜索面声明,按 CLAUDE.md「负结论必须给搜索面」保留原样。内容一字未动。

```text
搜索范围:基线仓库根,全部 *.py,排除 __pycache__。
模式 1:  grep -rn 'is_connected'          --include=*.py .
         → 命中 93 处。归类:
           · gateway/platform_registry.py:64        字段定义                      1
           · gateway/config.py                      真值 + 启用闸门(13 行)      13
           · hermes_cli/gateway.py:5440-5457        已修孪生                      5
           · plugins/platforms/*/adapter.py         钩子实现 + register 传参      66
           · gateway/platforms/{base,yuanbao,qqbot}.py, plugins/.../discord
                                                    适配器实例属性(同名不同物)  8
         → 8 份实现之外无遗漏消费点。
模式 2:  grep -rn 'get_connected_platforms\|_is_platform_connected' --include=*.py .
         → 非测试消费方共 8 处:gateway/run.py:6301, gateway/session.py:3465,
           cron/scheduler.py:1119, hermes_cli/commands.py:1999,
           hermes_cli/web_server.py:2997 与 :8341, hermes_cli/send_cmd.py:177,
           plugins/memory/honcho/cli.py:404。
           其中 gateway/run.py / session.py / commands.py / send_cmd.py / honcho
           是"用结果"而非"做判定",不计入 8 份;已核。
模式 3:  对 9 个目标文件逐个 grep 'TELEGRAM_BOT_TOKEN|DISCORD_BOT_TOKEN|SLACK_BOT_TOKEN'
         → 命中处逐个读上下文,区分"判定"与"配置向导/正则校验/保存"。
           hermes_cli/setup.py 的 5 处:1866/1870/1920/1969 是 Telegram token 格式
           正则与写盘,非判定;2205 是 home channel 缺失提醒,非就绪判定。
           hermes_cli/web_server.py 的 5 处:3897/3908/3925 是写入校验,9259 是保存,
           7638/7639 是元数据表;判定在 8315/8333。
模式 4:  对 9 个目标文件逐个 grep 'platform_registry|discover_plugins'(计数见 §6.1)
模式 5:  同名文件全枚举 git ls-files,逐个查 TELEGRAM_BOT_TOKEN / is_connected 计数(§1.3)
排除:   tests/ 下的实现不计入"实现份数";*.pyc 一律排除;
         website/docs、README 未纳入本段(本段是代码对齐,非文档对齐)。
```

### 9.2 "23 个插件全都注册了 is_connected" 的依据

不是静态推断,是运行时逐个取值(§7.3 表格 `is_connected()` 列,23 行无一为 `None`)。
静态旁证:`grep -rn 'is_connected=' plugins/platforms/*/adapter.py plugins/platforms/a2a/__init__.py`
命中 23 个 `register` 调用点。

### 9.3 "没有任何测试钉住 8 份一致性" 的依据

**R11C 片 C 改:围栏由 ```verify 改为 ```text,理由同 §9.1 —— 这是搜索面声明,不是命令。**
内容一字未动。

```text
搜索范围:tests/ 全树,*.py。
模式 1: grep -rl 'is_connected' tests/                  → 13 个文件
        逐个查看:全部是单平台适配器测试(discord/google_chat/msgraph/ntfy/raft/
        simplex/slack/voice)或注册表/接口测试;无一做跨实现对拍。
模式 2: grep -rl '_platform_status|_configured_platforms|_get_enabled_platforms|
        _show_gateway_status|_is_platform_connected|get_connected_platforms' tests/
        → 15 个文件。逐个查看:
          test_setup_irc.py       → 只验 IRC 单平台的 _platform_status
          test_tools_config.py:236→ 把 _get_enabled_platforms **mock 掉**,不验它本身
          test_scheduler.py:1592  → 只验 cron_delivery_targets 用了真值,喂 2 个平台
          test_config.py / test_platform_*.py → 只管 gateway/config.py 内部
          其余为 send_cmd / commands / web_server / weixin / yuanbao 的单点测试
模式 3: grep -rn '_KNOWN_DELIVERY_PLATFORMS|_HOME_TARGET_ENV_VARS|cron_delivery_targets' tests/
        → 唯一直接冲着一致性去的是 TestHomeTargetEnvVarRegistry,**类体为空**(§8.3)
模式 4: grep -rn '_configured_platforms' tests/          → 0 命中(dump.py 那份完全无测试)
        ls tests/hermes_cli/ | grep -i dump              → test_dump_env_visibility.py /
                                                            test_dump_git_commit.py /
                                                            test_dump_terminal_backend.py
                                                            三份都不碰平台清单
模式 5: cli.py 的 _show_gateway_status                    → grep -rn 全 tests/ = 0 命中
结论:  hermes_cli/dump.py:_configured_platforms 与 cli.py:_show_gateway_status
        这两处判定,**测试覆盖为零**。
```

---

## 10. 可迁移的教训(给自建 harness)

1. **"配没配好"必须是一个函数,不是一种写法。** 本仓库有 13 个判定点、9 套平台清单,
   根因是每个消费方都**自己写了一遍**,而不是调同一个函数。
   §5.3 里 dashboard 非 scoped 分支直接调 `_is_platform_connected`,是唯一正确的范式。
2. **区分"依赖装了吗"和"凭据配了吗",并且不要让前者能覆盖后者。**
   `check_fn` / `is_connected` 的分裂在本仓库造成了至少 3 次同类事故
   (`_platform_status` 修于 7849a3d73、`_apply_env_overrides` 修于 #31116、
   `status.py` **至今未修**)。同一 bug class 修了两次还有第三处,说明**只修站点不修形状**是不够的——
   应该让 `check_fn` 根本不可能被当成就绪判据(例如改名 `check_deps`,或让注册表只暴露
   一个合成后的 `readiness()`)。
3. **探针不要有副作用。** `check_fn` 兼任 pip 安装器,导致"查看状态"变成"安装软件"。
   探针必须是纯读的;安装应是显式动作。
4. **依赖隐式初始化顺序的代码会在不同进程里给出不同答案。**
   `status.py` 读注册表却不触发发现,于是同一段代码在 `hermes status` 里是死码、
   在 CLI `/status` 里全错。**要读注册表,就自己负责把它填好**——真值那一份(§2.2 末段的
   插件回落块)和 dashboard 都这么做了,后者还把理由写在注释里:

`hermes_cli/web_server.py:8065 @ 863e313`

```python
    try:
        # Plugin discovery only runs as a side effect of importing
        # model_tools; this server process doesn't do that, so trigger it
        # explicitly (idempotent) or plugin_entries() is empty here and
        # every plugin platform renders nameless.
        from hermes_cli.plugins import discover_plugins

        discover_plugins()
        from gateway.platform_registry import platform_registry
```

5. **写下了标题的回归守卫,如果没有正文,比没有更坏。**
   `TestHomeTargetEnvVarRegistry` 让人以为该不变量被守着,而它守的那个缺口
   (`whatsapp_cloud`)现在就是破的。

---

## 11. 本段未覆盖 / 存疑(锚点文件 + 行号 + 一句话现象)

1. **`hermes_cli/gateway.py` 用合成 `PlatformConfig(enabled=True)` 探测,真实影响面未量化。**
   现象:§5.2 引的那段里 `synthetic = PlatformConfig(enabled=True)` 是个空壳,对"只写 config.yaml
   token、不设环境变量"的平台可能低报为 not configured;我核了 telegram / ntfy / teams 三个
   `is_connected` 都做了 env 双读所以不受影响,**其余 20 个插件未逐个核**。

2. **`hermes_cli/status.py` 的 QQBot back-compat 分支是死代码。**
   现象:分支条件要求 `home_var == "QQBOT_HOME_CHANNEL"`,但同文件 §7.1 引的写死表里给 QQBot 配的
   `home_var` 是 `"QQ_HOME_CHANNEL"`,两者永不相等,该分支恒不成立。

`hermes_cli/status.py:494 @ 863e313`

```python
        # Back-compat: QQBot home channel was renamed from QQ_HOME_CHANNEL to QQBOT_HOME_CHANNEL
        if not home_channel and home_var == "QQBOT_HOME_CHANNEL":
            home_channel = os.getenv("QQ_HOME_CHANNEL", "")
```

   方向还与 cron 那边相反(cron 以 `QQBOT_` 为主、`QQ_` 为 legacy):

`cron/scheduler.py:283 @ 863e313`

```python
# Legacy env var names kept for back-compat.  Each entry is the current
# primary env var → the previous name.  _get_home_target_chat_id falls
# back to the legacy name if the primary is unset, so users who set the
# old name before the rename keep working until they migrate.
_LEGACY_HOME_TARGET_ENV_VARS = {
    "QQBOT_HOME_CHANNEL": "QQ_HOME_CHANNEL",
}
```

   未展开判定是 ■ 还是无害(取决于 QQBot 用户实际设的是哪个名字)。

3. **`Platform.WEBHOOK` 的 connected-checker 恒为 True。**
   现象:webhook 平台只要 `enabled` 就永远算 connected,凭据一概不看。

`gateway/config.py:849 @ 863e313`

```python
    Platform.WEBHOOK: lambda cfg: True,
```

   未核这是否会让 `get_connected_platforms()` 把未配置的 webhook 也列进"已连接平台",
   进而进入系统提示词——该结果被 `gateway/session.py` 消费:

`gateway/session.py:3465 @ 863e313`

```python
    connected = config.get_connected_platforms()
```

4. **`/api/status` 把"平台条目数"当成"已配置数"上报。**
   现象:健康摘要里的 `"configured"` 取的是 `len(gateway_platforms)`,与本段 13 个判定点用的
   语义都不同;未核该字段的实际来源与用户可见面。

`hermes_cli/web_server.py:3275 @ 863e313`

```python
        components["platforms"] = {
            "status": "ok" if platforms_ok else "degraded",
            "configured": len(gateway_platforms),
            "connected": sum(
                1 for state in platform_states if state in {"connected", "running", "ok"}
            ),
        }
```

5. **cron 执行记录里有一个 `not_configured` 结局码,与 §5.4 的 `enabled`-only 判定关系未核。**
   现象:它的触发条件是 `unresolved_origin`(解析不出投递目标),而不是"平台没配好",
   未核它是否会把"配好但发送失败"或"平台名不在 `_KNOWN_DELIVERY_PLATFORMS`"(§6.2)误记为"没配"。

`cron/scheduler.py:4085 @ 863e313`

```python
            delivery_outcome = "failed"
        elif should_deliver and unresolved_origin:
            delivery_outcome = "not_configured"
        elif should_deliver and normalized_deliver != "local":
```

6. **未覆盖 TS/前端侧。** 现象:`web/` 与 `tests-js/` 下可能另有一份平台就绪判定
   (dashboard 前端很可能自己也判一次 state),本段搜索面(§9.1)只含 `*.py`,
   未对 `web/` 做任何 grep,这是一条**明确的未搜索面**,不是负结论。
