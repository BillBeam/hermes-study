# R8D 底稿 · 簇 D —— 扩展、分发与生命周期挂载

> 基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(只读)。
> 溯源约定:凡对代码行为的断言,锚点 `` `路径:行号 @ 863e313` `` **单独成行、置于代码块之前**;
> 代码块内逐字照抄基线;非源码块用 ```text / ```console / ```verify 显式标注。
> 本簇 7 文件 / 7,573 行:`plugins.py` 2510、`skills_hub.py` 2036、`agent_import.py` 1024、
> `mcp_catalog.py` 831、`profile_distribution.py` 782、`middleware.py` 327、`lifecycle.py` 63。

---

## 0. 一句话总纲

**这一簇回答的是"外来代码怎么进到 Hermes 进程里"。答案是:进程内有 7 条互相独立的动态导入通道,
每条自带一套门禁,`plugins.enabled` 这个看起来像总开关的东西只管得住其中一条。**

术语先锚一次(目标读者不熟 Python 生态):

- **`exec_module`** —— Python 标准库 `importlib` 的函数,把一个 `.py` 文件当模块**执行**。
  文件顶层的任何语句(包括 `os.system(...)`)在这一刻就跑了。**"导入"在 Python 里等同于"执行"**,
  这是本簇所有安全推理的起点,和 Java 的 class-load 不同。
- **entry-point(入口点)** —— pip 包在自己的元数据里声明"我提供名为 X 的扩展",
  宿主程序扫描已安装包的元数据即可发现它,无需知道包名。
- **manifest(清单)** —— 描述扩展身份/能力的声明文件。本簇里有四种互不相同的清单:
  `plugin.yaml`(插件)、`distribution.yaml`(profile 分发)、`manifest.yaml`(MCP 目录)、
  `HOOK.yaml`(网关事件钩子)。
- **middleware(中间件)** —— 能**改写**请求或**包住**执行过程的回调,区别于只能旁观的 observer(观察者)。
- **MCP** —— Model Context Protocol,一种让外部进程以标准协议向 agent 提供工具的规范。
- **profile(配置档)** —— Hermes 的一整套用户状态目录(`~/.hermes` 或 `~/.hermes/profiles/<name>`),
  由环境变量 `HERMES_HOME` 指定。

---

## 1. 全景:进程内的 7 条动态导入通道

先把结论摆出来,后面逐条取证。下表每一行都是一个**独立的 `exec_module` / `ep.load()` 站点**,
即一条能把第三方 Python 代码执行进本进程的路径。

| # | 站点 | 扫描目录 | 门禁 | 受 `plugins.enabled` 管? | 受 `HERMES_SAFE_MODE` 管? |
|---|---|---|---|---|---|
| 1 | `hermes_cli/plugins.py:1889` | `<repo>/plugins/`、`$HERMES_HOME/plugins/`、`./.hermes/plugins/` | `plugins.enabled` 白名单(bundled backend/platform 例外) | **是** | **是** |
| 2 | `hermes_cli/plugins.py:1904`(entry-point) | 已装 pip 包的 `hermes_agent.plugins` 组 | 同上 | **是** | **是** |
| 3 | `providers/__init__.py:139` | `$HERMES_HOME/plugins/model-providers/` | **无** | **否** | **否** |
| 4 | `gateway/hooks.py:136` | `$HERMES_HOME/hooks/` | 只要求 `HOOK.yaml` 有 `name` + 非空 `events` | **否** | **否** |
| 5 | `hermes_cli/web_server.py:17301` | 仪表盘插件的 `dashboard/<api>.py` | 路径消毒 + 拒绝 project 源(GHSA 修复) | 独立 | 独立 |
| 6 | `plugins/memory/__init__.py:300` | `$HERMES_HOME/plugins/memory/` | `memory.provider` 配置键 | **否** | **否** |
| 7 | `plugins/context_engine/__init__.py:169`、`plugins/cron_providers/__init__.py:296` | 同构 | 各自的 `<category>.provider` 键 | **否** | **否** |

**搜索面(负结论的成本)**:上表声称"仅此 7 类站点"。搜索面 =
全仓 `*.py`,排除 `./tests`(测试)与 `./scripts`(开发脚本),模式为 `exec_module|spec_from_file_location`。
下面这条命令重跑可复现该清单:

```verify
cd /home/user/hermes-agent && grep -rn "exec_module\|spec_from_file_location" --include=*.py . \
  | grep -v "^./tests" | grep -v "^./scripts"
```

实测输出中除上表外,余下命中全部落在 `plugins/` 下的**随仓自带**插件自身(如
`plugins/platforms/buzz/adapter.py`、`plugins/memory/config_schema.py`)以及
`hermes_cli/setup.py` / `hermes_cli/claw.py` 两处一次性迁移脚本导入,
另有 `cli.py:875-886` 是给已有 loader 打补丁而非新站点。
**该搜索面不覆盖**:`eval` / `exec` 字面量、`__import__`、以及经由 `subprocess` 起的**子进程**
(MCP server、shell hook、kanban worker 都属此类,它们不进本进程,是另一个话题)。

### 1.1 为什么"7 条通道"是本簇最重要的一个事实

`hermes_cli/plugins.py` 的模块 docstring 把插件体系描述成一个统一的四来源系统:

`hermes_cli/plugins.py:5-20 @ 863e313`

```
Discovers, loads, and manages plugins from four sources:

1. **Bundled plugins** – ``<repo>/plugins/<name>/`` (shipped with hermes-agent;
   ``memory/`` and ``context_engine/`` subdirs are excluded — they have their
   own discovery paths)
2. **User plugins**   – ``~/.hermes/plugins/<name>/``
3. **Project plugins** – ``./.hermes/plugins/<name>/`` (opt-in via
   ``HERMES_ENABLE_PROJECT_PLUGINS``)
4. **Pip plugins**     – packages that expose the ``hermes_agent.plugins``
   entry-point group.

Later sources override earlier ones on name collision, so a user or project
plugin with the same name as a bundled plugin replaces it.

Each directory plugin must contain a ``plugin.yaml`` manifest **and** an
``__init__.py`` with a ``register(ctx)`` function.
```

这段是准确的——**对它自己管的那条通道而言**。它甚至诚实地写了"`memory/` 和 `context_engine/`
有自己的发现路径"。问题在于:一个读了这段就以为"关掉 `plugins.enabled` 就没有第三方代码进来"的运维,
会漏掉表中 #3/#4/#6/#7。下面 §2.4 会用代码证明 #3 完全无门禁。

---

## 2. `plugins.py` —— 主插件系统(2510 行)

### 2.1 发现:四来源 + 覆盖顺序

`hermes_cli/plugins.py:1356-1369 @ 863e313`

```
        repo_plugins = get_bundled_plugins_dir()
        logger.debug("Scanning bundled plugins: %s", repo_plugins)
        bundled = self._scan_directory(
            repo_plugins,
            source="bundled",
            skip_names={"memory", "context_engine", "platforms", "model-providers"},
        )
        logger.debug("  bundled (top-level): %d manifest(s)", len(bundled))
        manifests.extend(bundled)
        bundled_platforms = self._scan_directory(
            repo_plugins / "platforms", source="bundled"
        )
        logger.debug("  bundled/platforms: %d manifest(s)", len(bundled_platforms))
        manifests.extend(bundled_platforms)
```

注意 `skip_names` 里的 `model-providers` —— 随仓自带的模型提供方插件在**这里**被跳过,
交给 `providers/__init__.py`。这个跳过是**顶层目录名**级别的(`_scan_directory_level` 的
`depth == 0 and skip_names and child.name in skip_names`),只对 `<repo>/plugins/` 生效,
**不对 `$HERMES_HOME/plugins/` 生效** —— 用户目录调用 `_scan_directory(user_dir, source="user")`
时根本没传 `skip_names`。这就是 §2.4 那个双系统分歧的源头。

用户目录与项目目录:

`hermes_cli/plugins.py:1371-1388 @ 863e313`

```
        # 2. User plugins (~/.hermes/plugins/)
        user_dir = get_hermes_home() / "plugins"
        logger.debug("Scanning user plugins: %s", user_dir)
        user_manifests = self._scan_directory(user_dir, source="user")
        logger.debug("  user: %d manifest(s)", len(user_manifests))
        manifests.extend(user_manifests)

        # 3. Project plugins (./.hermes/plugins/)
        if _env_enabled("HERMES_ENABLE_PROJECT_PLUGINS"):
            project_dir = Path.cwd() / ".hermes" / "plugins"
            logger.debug("Scanning project plugins: %s", project_dir)
            project_manifests = self._scan_directory(project_dir, source="project")
            logger.debug("  project: %d manifest(s)", len(project_manifests))
            manifests.extend(project_manifests)
        else:
            logger.debug(
                "Project plugins disabled (set HERMES_ENABLE_PROJECT_PLUGINS=1 to enable)"
            )
```

**要点**:`user_dir = get_hermes_home() / "plugins"`。`get_hermes_home()` 解析顺序是
context-local 覆盖 → `HERMES_HOME` 环境变量 → 平台默认。这意味着**"用户插件目录"是随 profile 走的**:
跑 `hermes -p foo` 时它是 `~/.hermes/profiles/foo/plugins/`。这一点在 §4 的 profile 分发链条里是关键。

项目插件(第 3 源,CWD 里的 `.hermes/plugins/`)默认关闭,需要显式 `HERMES_ENABLE_PROJECT_PLUGINS`。
它读的是 `env_var_enabled` 而不是"非空即真"——这是一个真实事故的修复,见 §2.9。

**目录布局支持两级,且深度硬封顶**:

`hermes_cli/plugins.py:1538-1543 @ 863e313`

```
        """Recursive implementation of :meth:`_scan_directory`.

        ``prefix`` is the category path already accumulated ("" at root,
        "image_gen" one level in). ``depth`` is the recursion depth; we
        cap at 2 so ``<root>/a/b/c/`` is ignored.
        """
```

即 `plugins/disk-cleanup/plugin.yaml`(扁平)与 `plugins/image_gen/openai/plugin.yaml`(分类)都合法,
key 分别是 `disk-cleanup` 与 `image_gen/openai`。**深度封顶是必要的**:
没有它,一个深层嵌套的用户目录会让扫描退化成全盘遍历。而 key 带上分类前缀
则解决了"`tts/openai` 和 `image_gen/openai` 都叫 openai"的撞名问题——
**注册键从路径派生而不是从清单的 `name` 字段派生**,这是本系统一个很干净的决定。

插件作者的调试开关(env 在 import 期读一次,把发现日志 tee 到 stderr):

`hermes_cli/plugins.py:96-99 @ 863e313`

```
_PLUGINS_DEBUG = os.getenv("HERMES_PLUGINS_DEBUG", "").strip().lower() in {
    "1", "true", "yes", "on",
}
_DEBUG_HANDLER_INSTALLED = False
```

注意这里的真值判定集合 `{"1","true","yes","on"}` —— 与 `env_var_enabled` 同一套语义。
§2.9 那个事故的根因正是**另一个模块没用这套语义**。

### 2.2 门禁:opt-in 白名单

插件默认**全不加载**。这是一个 opt-in(选择性加入)模型,不是 opt-out。

`hermes_cli/plugins.py:246-259 @ 863e313`

```
def _get_enabled_plugins() -> Optional[set]:
    """Read the enabled-plugins allow-list from config.yaml.

    Plugins are opt-in by default — only plugins whose name appears in
    this set are loaded. Returns:

    * ``None`` — the key is missing or malformed. Callers should treat
      this as "nothing enabled yet" (the opt-in default); the first
      ``migrate_config`` run populates the key with a grandfathered set
      of currently-installed user plugins so existing setups don't
      break on upgrade.
    * ``set()`` — an empty list was explicitly set; nothing loads.
    * ``set(...)`` — the concrete allow-list.
    """
```

门本身:

`hermes_cli/plugins.py:1476-1491 @ 863e313`

```
            is_enabled = (
                enabled is not None
                and (lookup_key in enabled or manifest.name in enabled)
            )
            if not is_enabled:
                loaded = LoadedPlugin(manifest=manifest, enabled=False)
                loaded.error = (
                    "not enabled in config (run `hermes plugins enable {}` to activate)"
                    .format(lookup_key)
                )
                self._plugins[lookup_key] = loaded
                logger.debug(
                    "Skipping '%s' (not in plugins.enabled)", lookup_key
                )
                continue
            self._load_plugin(manifest)
```

设计取舍值得记:**未启用的插件仍然被记录进 `self._plugins`**(带 `error` 说明),
只是不 `_load_plugin`。所以 `hermes plugins list` 能列出"装了但没启用"的插件——
**可见性与可执行性被拆开了**。这是一个很好的 harness 设计模式:发现是廉价且全量的,
加载是昂贵且受控的,两者的产物都要能被内省。

还有一个**可重入守卫**,写法值得单独学:

`hermes_cli/plugins.py:1326-1337 @ 863e313`

```
        # Set the flag up front as a re-entrancy guard (a plugin's register()
        # can transitively trigger discovery again), but reset it if the sweep
        # raises so a failed scan is NOT cached as "discovered with an empty
        # registry" — callers swallow the exception and would otherwise be
        # permanently stranded on the early-return above (the "No web provider
        # configured" class of failures).
        self._discovered = True
        try:
            self._discover_and_load_inner()
        except BaseException:
            self._discovered = False
            raise
```

这是"幂等标志位"的两难:**先置位**才能挡住插件 `register()` 里递归触发的二次发现,
但先置位又会把一次失败的扫描缓存成"已发现且为空",于是整个进程余生都以为没有插件。
解法是 try/except 里回滚标志。注释还给出了这个 bug 的可观测形状——
"No web provider configured" 那一类莫名其妙的报错。**把失败的外在症状写进注释**,
下一个人搜到那句报错就能找到这里。

还有一个总闸:

`hermes_cli/plugins.py:1310-1313 @ 863e313`

```
        if env_var_enabled("HERMES_SAFE_MODE"):
            logger.info("HERMES_SAFE_MODE=1 — plugin discovery skipped")
            self._discovered = True
            return
```

### 2.3 kind 分流:四种绕过 `plugins.enabled` 的情形

`plugin.yaml` 的 `kind` 字段决定走哪条路。合法值:

`hermes_cli/plugins.py:280 @ 863e313`

```
_VALID_PLUGIN_KINDS: Set[str] = {"standalone", "backend", "exclusive", "platform", "model-provider"}
```

**(a) 随仓 backend 自动加载**(不看 `plugins.enabled`):

`hermes_cli/plugins.py:1453-1455 @ 863e313`

```
            if manifest.source == "bundled" and manifest.kind == "backend":
                self._load_plugin(manifest)
                continue
```

**(b) 随仓 platform 延迟加载**(注册一个 loader,首次用到才 import):

`hermes_cli/plugins.py:1748-1754 @ 863e313`

```
        def _loader(_manifest: PluginManifest = manifest) -> None:
            self._load_plugin(_manifest)

        try:
            from gateway.platform_registry import platform_registry

            platform_registry.register_deferred(platform_name, _loader)
```

这是一个纯粹的**启动延迟**优化,理由写得很清楚:约 20 个平台适配器各自 import 沉重的 SDK,
全量 eager 加载会给每次 `hermes chat` 加上好几秒。代价是"这个插件到底加载了没有"变成了时间函数——
`LoadedPlugin.deferred` 字段就是为了让内省能区分这两种"已启用"。

**(c) exclusive(记录不加载)** 与 **(d) model-provider(标记 enabled 但不加载)**:

`hermes_cli/plugins.py:1440-1447 @ 863e313`

```
            if manifest.kind == "model-provider":
                loaded = LoadedPlugin(manifest=manifest, enabled=True)
                self._plugins[lookup_key] = loaded
                logger.debug(
                    "Skipping '%s' (model-provider, handled by providers/ discovery)",
                    lookup_key,
                )
                continue
```

注意这里 `enabled=True` 是**无条件**的——既没查 `plugins.enabled`,也没查 `plugins.disabled`
(`disabled` 的检查在更上面的 1412 行,确实先于此,所以 `disabled` 在**本系统内**是拦得住的)。
但 PluginManager 本身不加载它,真正的加载在 `providers/__init__.py`。下一节。

### 2.4 ■-1:模型提供方插件绕过全部门禁

`providers/_discover_providers()` 无条件 import `$HERMES_HOME/plugins/model-providers/` 下的每个目录:

`providers/__init__.py:170-179 @ 863e313`

```
    # 2. User plugins — under $HERMES_HOME/plugins/model-providers/<name>/.
    #    These can override any bundled profile of the same name (last-writer-wins
    #    in register_provider()).
    user_dir = _user_plugins_dir()
    if user_dir is not None:
        for child in sorted(user_dir.iterdir()):
            if not child.is_dir() or child.name.startswith(("_", ".")):
                continue
            _import_plugin_dir(child, "user")
```

`_import_plugin_dir` 就是 `exec_module`:

`providers/__init__.py:132-139 @ 863e313`

```
        spec = importlib.util.spec_from_file_location(
            module_name, init_file, submodule_search_locations=[str(plugin_dir)]
        )
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
```

**负结论 + 搜索面**:`providers/__init__.py` 全文 198 行,**没有任何**配置门禁。
搜索面 = 该文件全文,模式为 `enabled|disabled|SAFE_MODE|load_config|cfg_get|allow|plugins\.|config\.yaml`
(大小写不敏感)。重跑:

```verify
cd /home/user/hermes-agent && grep -n -i "enabled\|disabled\|SAFE_MODE\|load_config\|cfg_get\|allow\|plugins\.\|config\.yaml" providers/__init__.py
```

实测仅 2 条命中,均为注释与模块命名字符串(`118:` 的 docstring 注释、`124:` 的
`module_name = f"plugins.model_providers.{safe_name}"`),**零个真实门禁**。

于是三件事同时成立:

1. `~/.hermes/plugins/model-providers/<x>/__init__.py` 在首次 `get_provider_profile()` 时被执行;
2. `plugins.enabled` 不管它,`plugins.disabled` 不管它;
3. `HERMES_SAFE_MODE=1` 也不管它——`HERMES_SAFE_MODE` 只在 `PluginManager.discover_and_load` 里被查
   (`plugins.py:1310`),而这条路径根本不经过 PluginManager。

**更微妙的一层**:PluginManager 判定 `kind` 时,对没写 `kind:` 的清单用一个**读前 8192 字节找子串**的启发式:

`hermes_cli/plugins.py:1622-1649 @ 863e313`

```
            if kind == "standalone" and "kind" not in data:
                init_file = plugin_dir / "__init__.py"
                if init_file.exists():
                    try:
                        source_text = init_file.read_text(errors="replace", encoding="utf-8")[:8192]
                        if (
                            "register_memory_provider" in source_text
                            or "MemoryProvider" in source_text
                        ):
                            kind = "exclusive"
                            logger.debug(
                                "Plugin %s: detected memory provider, "
                                "treating as kind='exclusive'",
                                key,
                            )
                        elif (
                            "register_provider" in source_text
                            and "ProviderProfile" in source_text
                        ):
                            # Model provider plugin (calls register_provider()
                            # from ``providers`` with a ProviderProfile). Route
                            # to providers/__init__.py discovery.
                            kind = "model-provider"
                            logger.debug(
                                "Plugin %s: detected model provider, "
                                "treating as kind='model-provider'",
                                key,
                            )
                    except Exception:
                        pass
```

两个系统对"这是什么插件"的判定标准不同:PluginManager 看**清单 + 前 8 KB 源码子串**,
`providers/` 看**目录位置**(在不在 `plugins/model-providers/` 下)。
所以一个放在 `plugins/model-providers/` 下、但前 8 KB 里不出现 `ProviderProfile`
(比如把 import 写在 8 KB 之后,或用 `getattr` 拼字符串)的目录,
会被 PluginManager 判成 `standalone` 从而**受 `plugins.enabled` 管**,
同时被 `providers/` **无条件执行**。两个系统给出相反答案时,**不设防的那个赢**,
因为它不需要另一个同意。

**判定为 ■ 而非 ▲**:这是代码缺陷(门禁不完备),不是文档与代码矛盾——
`plugins.py:1434-1439` 的注释如实写了"由 providers/__init__.py 加载",没有说谎。

### 2.5 装载:`exec_module` 与命名空间

`hermes_cli/plugins.py:1877-1889 @ 863e313`

```
        spec = importlib.util.spec_from_file_location(
            module_name,
            init_file,
            submodule_search_locations=[str(plugin_dir)],
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {init_file}")

        module = importlib.util.module_from_spec(spec)
        module.__package__ = module_name
        module.__path__ = [str(plugin_dir)]  # type: ignore[attr-defined]
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
```

模块名是 `hermes_plugins.<slug>`,slug 由 `manifest.key` 派生
(`key.replace("/", "__").replace("-", "_")`),这样 `image_gen/openai` 与将来的 `tts/openai`
不会撞车。父命名空间包 `hermes_plugins` 是运行时**凭空造出来**的
(`types.ModuleType(_NS_PARENT)` + `__path__ = []`),不落磁盘。

**这行 `exec_module` 是本系统里"第三方代码开始运行"的确切时刻。** 在它之前,
插件目录只是被 `read_text` 过(读清单、读前 8 KB 做启发式),没有执行。

紧接着调用约定的入口:

`hermes_cli/plugins.py:1794-1799 @ 863e313`

```
            register_fn = getattr(module, "register", None)
            if register_fn is None:
                loaded.error = "no register() function"
                logger.warning("Plugin '%s' has no register() function", manifest.name)
            else:
                ctx = PluginContext(manifest, self)
```

注意先后:`exec_module` 在前,查 `register` 在后。**一个没有 `register()` 的"插件"照样被完整执行了一遍**,
只是之后被记为 `error`。这是 Python 导入语义的直接后果,不是疏忽,但设计同级 harness 时必须意识到:
**在 Python 里没有"只加载不执行"的中间态**;要做到那个,必须先静态解析(AST)或起沙箱子进程。

### 2.6 装的时候执行不执行任意代码?—— 分开回答

这是任务书的要害问题之一,必须把"安装"和"加载"分开。

**安装(`hermes plugins install owner/repo`)不执行插件代码。** 它只做 `git clone --depth 1`:

`hermes_cli/plugins_cmd.py:473-480 @ 863e313`

```
            result = subprocess.run(
                [git_exe, "clone", "--depth", "1", git_url, str(tmp_clone)],
                capture_output=True,
                text=True, encoding='utf-8', errors='replace',
                timeout=60,
                stdin=subprocess.DEVNULL,
                env=noninteractive_git_env(),
            )
```

然后读清单、消毒名字、`shutil.move` 到 `~/.hermes/plugins/<name>`。

**负结论 + 搜索面**:`hermes_cli/plugins_cmd.py` 全文中,能执行代码的原语只有 `subprocess.run`
两处(`473` 的 clone、`2005` 的 update 拉取),没有 `exec_module` / `eval` / `exec` /
`__import__` / `pip install` / `npm`。搜索面 = 该单文件全文,模式如下,重跑:

```verify
cd /home/user/hermes-agent && grep -n "subprocess\.\|exec_module\|importlib\|eval(\|exec(\|__import__\|pip install\|npm " hermes_cli/plugins_cmd.py
```

唯一的 `importlib` 命中是 `13: import importlib.metadata` 与 `1087: eps = importlib.metadata.entry_points()`
—— 读已装 pip 包的元数据,不执行插件目录里的代码。
**该搜索面不覆盖**:`_copy_example_files` 内部若调别的模块(实测它只 `shutil.copy`),
以及 git 自身的钩子(`git clone` 不执行被克隆仓库的 hooks,但会执行本机 `~/.gitconfig` 里配置的
`core.fsmonitor` 之类——这属于 git 的攻击面,不是 Hermes 的)。

**装完之后会不会立刻变成"能执行"?** 会,但要用户按一次回车:

`hermes_cli/plugins_cmd.py:605-616 @ 863e313`

```
    should_enable = enable
    if should_enable is None:
        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                answer = input(
                    f"  Enable '{installed_name}' now? [y/N]: ",
                ).strip().lower()
                should_enable = answer in {"y", "yes"}
            except (EOFError, KeyboardInterrupt):
                should_enable = False
        else:
            should_enable = False
```

默认 `[y/N]` 是 N,非 TTY 环境直接 False。**fail-closed,写得对。**

**所以完整结论**:装 = 只落盘;启用 = 写 `plugins.enabled`;执行 = 下一次进程启动时的 discovery。
三步分离,每步都可观测。这是本簇设计得最好的一块。

### 2.7 `PluginContext` —— 插件能碰到什么

`register(ctx)` 收到的 `ctx` 是**唯一**的官方能力面。全部注册方法(从 `plugins.py` 结构提取):

| 方法 | 行号 | 影响面 |
|---|---|---|
| `register_tool` | 413 | 向全局工具注册表加工具(模型可见) |
| `register_cli_command` | 526 | 加 `hermes <sub>` 终端子命令 |
| `register_command` | 551 | 加会话内 `/斜杠命令` |
| `register_hook` | 1180 | 挂 24 个生命周期钩子之一 |
| `register_middleware` | 1199 | 挂 4 类中间件(可改写请求 / 包住执行) |
| `register_skill` | 1220 | 注册只读 skill(需显式加载,不进系统提示索引) |
| `register_context_engine` | 638 | **替换**内建上下文压缩器(全局唯一) |
| `register_secret_source` | 824 | 注册外部密钥后端,启动时供给凭据 |
| `register_platform` | 953 | 加网关消息平台适配器 |
| `register_image_gen_provider` | 670 | 图像生成后端 |
| `register_video_gen_provider` | 737 | 视频生成后端 |
| `register_tts_provider` | 871 | 语音合成后端 |
| `register_transcription_provider` | 909 | 语音识别后端 |
| `register_web_search_provider` | 764 | 联网搜索/抓取后端 |
| `register_browser_provider` | 792 | 云浏览器后端 |
| `register_dashboard_auth_provider` | 697 | 仪表盘 OAuth 认证提供方 |
| `register_slack_action_handler` | 1009 | Slack 按钮回调 |
| `register_auxiliary_task` | 1069 | 注册辅助 LLM 任务类型 |
| `dispatch_tool` | 607 | 主动调用任意已注册工具 |
| `inject_message` | 498 | 向活动会话注入一条消息(可打断进行中的回合) |
| `ctx.llm`(属性) | 355 | 用**宿主的**模型与凭据跑补全 |
| `ctx.subagent_lifecycle`(属性) | 372 | 启动/观察子 agent |
| `ctx.profile_name`(属性) | 392 | 当前 profile 名 |

这个面**非常宽**。几个值得单独说的:

**`ctx.llm` —— 插件借宿主的账号打模型。**

`hermes_cli/plugins.py:355-364 @ 863e313`

```
    def llm(self) -> Any:
        """Return the plugin's :class:`agent.plugin_llm.PluginLlm` facade.

        Lets trusted plugins run host-owned chat or structured completions
        against the user's active model and auth without bringing their
        own provider keys. Override capability (model, agent id, auth
        profile) is fail-closed by default and gated through
        ``plugins.entries.<plugin_id>.llm.*`` config keys.

        See :mod:`agent.plugin_llm` for the full surface."""
```

设计取舍很清楚:插件不用自带 key(好,减少凭据扩散),代价是**插件花的是用户的钱、
用的是用户的额度**。覆盖模型/身份的能力单独再上一道配置门。

**`inject_message` —— 插件能打断正在进行的回合并塞话进去。**

`hermes_cli/plugins.py:509-522 @ 863e313`

```
        cli = self._manager._cli_ref
        if cli is None:
            logger.warning("inject_message: no CLI reference (not available in gateway mode)")
            return False

        msg = content if role == "user" else f"[{role}] {content}"

        if getattr(cli, "_agent_running", False):
            # Agent is mid-turn — interrupt with the message
            cli._interrupt_queue.put(msg)
        else:
            # Agent is idle — queue as next input
            cli._pending_input.put(msg)
        return True
```

**`register_skill` —— 插件带的技能刻意不进系统提示。**

`hermes_cli/plugins.py:1226-1237 @ 863e313`

```
        """Register a read-only skill provided by this plugin.

        The skill becomes resolvable as ``'<plugin_name>:<name>'`` via
        ``skill_view()``.  It does **not** enter the flat
        ``~/.hermes/skills/`` tree and is **not** listed in the system
        prompt's ``<available_skills>`` index — plugin skills are
        opt-in explicit loads only.

        Raises:
            ValueError: if *name* contains ``':'`` or invalid characters.
            FileNotFoundError: if *path* does not exist.
        """
```

两个刻意的收窄:(a) **不进扁平 skills 树**,所以插件卸载后不留孤儿文件;
(b) **不进系统提示索引**,所以插件不能靠装一个技能就往每一次请求的系统提示里塞内容。
(b) 尤其重要——系统提示是提示缓存(prompt cache)的前缀,任何人往里塞东西都会
让全体用户的缓存失效并涨 token。**"能注册"和"能进系统提示"必须分开授权**,
这条对任何有技能/插件机制的 harness 都适用。

**`register_auxiliary_task` —— 插件可以定义新的辅助 LLM 任务类型。**

`hermes_cli/plugins.py:1069-1082 @ 863e313`

```
    def register_auxiliary_task(
        self,
        key: str,
        *,
        display_name: str,
        description: str,
        defaults: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a plugin-defined auxiliary LLM task.

        Auxiliary tasks are LLM-backed side jobs (vision analysis, web extraction,
        compression, smart-approval, etc.) that route through ``auxiliary_client.py``.
        Each task has its own ``auxiliary.<key>`` config block where users can
        pin a provider/model independent of the main chat model.
```

"辅助任务"是指不面向用户、由 harness 自己发起的后台 LLM 调用(压缩上下文、看图、智能审批)。
插件注册一个新 key 之后,用户就能在 `auxiliary.<key>` 下单独指定便宜模型。
**把"哪些后台调用存在"做成可扩展的注册表,而不是硬编码枚举**,
是让成本控制粒度跟着功能一起长的做法。

**`register_slack_action_handler` —— 平台专属回调也走同一套注册表。**

`hermes_cli/plugins.py:1009-1020 @ 863e313`

```
    def register_slack_action_handler(
        self,
        action_id: Any,
        callback: Callable,
    ) -> None:
        """Register a Slack Block Kit action handler from a plugin.

        Hermes' Slack adapter wires registered handlers into its
        ``slack_bolt.AsyncApp`` at connect time. The callback is invoked
        when a user clicks a button (or interacts with another Block Kit
        action element) whose ``action_id`` matches.

```

这是唯一一个**平台专属**的注册点(其他都是平台无关的)。它的存在说明一件事:
通用抽象覆盖不了的地方,与其硬造一个"通用交互元素"抽象,不如老实开一个平台专属口子。
代价是这个口子对非 Slack 用户是死重量,收益是 Slack 插件不用 fork 适配器。

回到 `inject_message`:注意 `role != "user"` 时只是加个 `[role]` 前缀塞进**同一个用户输入队列**——
也就是说插件无法真正伪造 assistant/system 消息,只能以用户身份说话并自称是别人。
这是个正确的收窄。另注意它在网关模式下直接失效(`_cli_ref is None`),
所以这是一个 **CLI-only** 的能力,插件作者必须处理返回 `False`。

### 2.8 内建工具覆盖的信任门

插件可以用 `override=True` 顶替内建工具(比如换掉 `browser_navigate`)。这需要显式授权:

`hermes_cli/plugins.py:441-448 @ 863e313`

```
        if override and not self._tool_override_allowed(name):
            plugin_id = self.manifest.key or self.manifest.name
            raise PluginToolOverrideError(
                f"Plugin {self.manifest.name!r} cannot override built-in tool "
                f"{name!r}. Set "
                f"plugins.entries.{plugin_id}.allow_tool_override: true "
                f"in config.yaml to allow this plugin to replace built-in tools."
            )
```

`hermes_cli/plugins.py:481-494 @ 863e313`

```
        source = getattr(self.manifest, "source", "") or ""
        if source == "bundled":
            return True
        try:
            from hermes_cli.config import load_config
            cfg = load_config() or {}
        except Exception:
            # If we can't load config, fail closed — better to break the
            # override than silently grant it.
            return False
        plugin_id = self.manifest.key or self.manifest.name
        entries = (cfg.get("plugins") or {}).get("entries") or {}
        entry = entries.get(plugin_id) or {}
        return bool(entry.get("allow_tool_override", False))
```

三点值得学:

1. **威胁模型写进了注释**(`plugins.py:436-439`):"任何已启用的插件都能悄悄替换掉
   `shell_exec` 或 `write_file` 并把经过它的一切外泄"。把"为什么要这道门"写在门旁边,
   下一个人就不会以"多余的复杂度"为由删掉它。
2. **配置读失败 → 拒绝**,注释明说 "fail closed"。
3. **bundled 无条件放行**——随仓插件是维护者自己的代码,不是第三方。信任边界划在"谁能改这个目录",
   而不是"这段代码看起来危不危险"。

但这道门有个前提:插件必须**自己**传 `override=True` 才会触发。若插件直接
`from tools.registry import registry; registry.register(..., override=True)`,
就绕过了 `PluginContext`。代码对此有防备——加载前先向注册表登记本插件的策略:

`hermes_cli/plugins.py:1778-1784 @ 863e313`

```
        from tools.registry import registry as _registry
        _plugin_id = manifest.key or manifest.name
        _slug = _plugin_id.replace("/", "__").replace("-", "_")
        _registry.register_plugin_override_policy(
            f"{_NS_PARENT}.{_slug}",
            PluginContext(manifest, self)._tool_override_allowed(""),
        )
```

即注册表按**调用方模块名**(`hermes_plugins.<slug>`)自己判定,而不是信任 `PluginContext` 这一层。
这是"不要把安全检查放在可被绕过的门面上"的正确做法。

### 2.9 project 插件的真实事故(GHSA-5qr3-c538-wm9j / #29156)

这是本簇唯一有编号的真实安全事故,值得完整讲成故事。

**输入**:一个恶意 git 仓库,根目录带 `.hermes/plugins/evil/dashboard/manifest.json`,
内容一行 `{"api": "/tmp/payload.py"}`。用户 clone 下来,在里面开 Hermes 仪表盘。

**现象**:`/tmp/payload.py` 被当模块执行。

**为什么**:两个缺陷串成一条链。

`tests/hermes_cli/test_project_plugin_rce_bypass.py:5-19 @ 863e313`

> Two primitives combined into the original advisory chain:
>
> 1. ``hermes_cli.web_server._discover_dashboard_plugins`` opted into
>    the untrusted ``./.hermes/plugins/`` source via
>    ``os.environ.get("HERMES_ENABLE_PROJECT_PLUGINS")`` — truthy for
>    any non-empty string, so ``=0`` / ``=false`` / ``=no`` (all of
>    which the agent loader treats as off, and which operators set to
>    *disable* project plugins) silently *enabled* the source.
> 2. ``hermes_cli.web_server._mount_plugin_api_routes`` then imported
>    each plugin's manifest ``api`` field as a Python module via
>    ``importlib.util.spec_from_file_location``.  The field was used
>    raw, with no path-traversal check, so a single manifest line
>    ``{"api": "/tmp/payload.py"}`` was enough to redirect the
>    importer at any Python file on disk (``Path('safe') / '/abs'``
>    resolves to ``/abs`` in Python).

第一个缺陷的形状特别值得记:**同一个环境变量,两个模块用了两种真值语义。**
agent 侧用 `env_var_enabled`(只认 `1/true/yes/on`),仪表盘侧用 `os.environ.get`(非空即真)。
于是运维写 `HERMES_ENABLE_PROJECT_PLUGINS=0` 想**关掉**它,agent 侧确实关了,
仪表盘侧却**打开了**。一个用来关闭功能的值把功能打开了——这是最坏的一类 bug,
因为它让防御动作变成攻击面。

第二个缺陷是 Python 路径语义的经典坑:`Path('safe') / '/abs'` == `Path('/abs')`。
拼接一个绝对路径会**丢弃**前缀。

**怎么修的**:五层防御,测试逐层钉死。真值语义统一;`_safe_plugin_api_relpath` 拒绝绝对路径与 `..`;
发现阶段就把 `_api_file` 洗掉;挂载阶段**再**验一次并直接拒绝 project 源;端到端 PoC 回归。

`tests/hermes_cli/test_project_plugin_rce_bypass.py:230-238 @ 863e313`

```
    def test_project_source_api_is_not_imported(self, tmp_path):
        plugin = self._payload_plugin(tmp_path, source="project")
        web_server._dashboard_plugins_cache = [plugin]
        with patch("importlib.util.spec_from_file_location") as spec:
            web_server._mount_plugin_api_routes()
        assert spec.call_count == 0, (
            "project-source plugin's api file was imported — "
            "GHSA-5qr3-c538-wm9j defence-in-depth regression"
        )
```

**可迁移教训**:(1) 一个 env 开关的真值语义必须只有一处定义;
(2) 任何"用清单里的字符串拼路径再 import"的地方都要在**拼接后**验证结果仍在允许的根之下;
(3) 同一个安全判断在发现和使用两处各做一遍,不算冗余,算防御纵深。

### 2.10 钩子:24 个挂载点

`hermes_cli/plugins.py:135-140 @ 863e313`

```
VALID_HOOKS: Set[str] = {
    "pre_tool_call",
    "post_tool_call",
    "transform_terminal_output",
    "transform_tool_result",
    # Transform LLM output before it's returned to the user.
```

完整 24 个(按代码顺序):`pre_tool_call`、`post_tool_call`、`transform_terminal_output`、
`transform_tool_result`、`transform_llm_output`、`pre_llm_call`、`post_llm_call`、`pre_verify`、
`pre_api_request`、`post_api_request`、`api_request_error`、`on_session_start`、`on_session_end`、
`on_session_finalize`、`on_session_reset`、`on_skill_lifecycle`、`subagent_start`、`subagent_stop`、
`pre_gateway_dispatch`、`pre_approval_request`、`post_approval_response`、`kanban_task_claimed`、
`kanban_task_completed`、`kanban_task_blocked`。

按"能不能改变行为"分三档,这是理解整个扩展模型的关键切分:

**档 1 —— 纯观察者(返回值被丢弃)。** 代码里明说的有审批与看板两组:

`hermes_cli/plugins.py:177-182 @ 863e313`

```
    # Approval lifecycle hooks. Fired by tools/approval.py when a dangerous
    # command needs an approval decision -- fires for CLI-interactive prompts,
    # gateway/ACP approvals, and smart-mode auxiliary-LLM decisions.
    # Observers only: return values are ignored. Plugins cannot veto or
    # pre-answer an approval from these hooks (use pre_tool_call to block
    # a tool before it reaches approval).
```

这条注释是本文件里最好的一句设计说明:**它同时说了"不能做什么"和"要做那件事该用哪个钩子"。**
审批钩子故意做成只读,因为让插件能自动应答审批等于取消审批。

**档 2 —— 能否决/改写(返回值被消费)。** `pre_tool_call`(block/approve)、
`pre_llm_call`(注入上下文)、`pre_verify`(让 agent 继续跑)、`pre_gateway_dispatch`(丢弃/改写消息)、
三个 `transform_*`(替换文本)。

**档 3 —— 中间件**(不在 `VALID_HOOKS` 里,见 §3)。

**钩子隔离**:每个回调各自 try/except,一个插件崩了不影响别人也不影响 agent:

`hermes_cli/plugins.py:1937-1948 @ 863e313`

```
        for cb in callbacks:
            try:
                ret = cb(**kwargs)
                if ret is not None:
                    results.append(ret)
            except Exception as exc:
                logger.warning(
                    "Hook '%s' callback %s raised: %s",
                    hook_name,
                    getattr(cb, "__name__", repr(cb)),
                    exc,
                )
        return results
```

**未知钩子名照收**(前向兼容):

`hermes_cli/plugins.py:1186-1194 @ 863e313`

```
        if hook_name not in VALID_HOOKS:
            logger.warning(
                "Plugin '%s' registered unknown hook '%s' "
                "(valid: %s)",
                self.manifest.name,
                hook_name,
                ", ".join(sorted(VALID_HOOKS)),
            )
        self._manager._hooks.setdefault(hook_name, []).append(callback)
```

取舍:警告但仍然存。好处是新版 Hermes 加了钩子后老插件不用改;坏处是**拼错的钩子名永远不会被触发,
只在日志里留一行 WARNING**。对插件作者不友好,所以才有了 `HERMES_PLUGINS_DEBUG=1` 把这些日志
tee 到 stderr(`plugins.py:96-129`)。

### 2.11 `pre_tool_call` 的 block / approve 与 fail-closed

插件否决工具调用的完整语义:

`hermes_cli/plugins.py:2144-2154 @ 863e313`

```
    - ``block`` vetoes the tool call outright (the message becomes the tool
      result the model sees).
    - ``approve`` ESCALATES to the existing human-approval gate
      (``prompt_dangerous_approval`` on CLI, the approval callback on the
      gateway) — the same mechanism Tier-2 dangerous shell patterns use.
      This lets a plugin require a human ``[o]nce/[s]ession/[a]lways/[d]eny``
      decision on ANY tool, not just terminal command strings. The caller is
      responsible for invoking the gate (see
      :func:`tools.approval.request_tool_approval`).
    - ``rule_key`` is optional and only honored for ``approve`` directives. It
      lets plugins choose the allowlist grain for `[a]lways` approvals.
```

`block` 必须带 message(因为 message 就是模型看到的工具结果),`approve` 的 message 可选:

`hermes_cli/plugins.py:2189-2197 @ 863e313`

```
        # A block directive requires a message (it becomes the tool result);
        # an approve directive can carry an optional reason.
        if action == "block" and not message:
            continue
        rule_key = result.get("rule_key") if action == "approve" else None
        rule_key = rule_key.strip() if isinstance(rule_key, str) else None
        if not rule_key:
            rule_key = None
        return _PreToolCallDirective(action=action, message=message, rule_key=rule_key)
```

**集中化 + fail-closed** 是这里最好的设计:

`hermes_cli/plugins.py:2270-2274 @ 863e313`

```
    Centralizing this keeps the security-critical fail-closed logic in ONE
    place instead of copy-pasted across the concurrent/sequential/helper
    dispatch paths: an ``approve`` directive whose gate errors, denies, or
    times out is fail-closed to a block; ``block`` blocks with its message;
    anything else proceeds.
```

`hermes_cli/plugins.py:2311-2319 @ 863e313`

```
        except Exception:
            # Fail-closed: if the gate itself errors, block rather than
            # silently execute an action a plugin flagged for approval.
            return f"BLOCKED: plugin approval gate failed for {tool_name}"
        if not result.get("approved"):
            return str(
                result.get("message")
                or f"BLOCKED: plugin approval required for {tool_name}"
            )
    return None
```

顺带:线程级工具白名单在**钩子之前**生效,是更硬的一道:

`hermes_cli/plugins.py:2159-2165 @ 863e313`

```
    allowed = getattr(_thread_tool_whitelist, "allowed", None)
    if allowed is not None and tool_name not in allowed:
        fmt = getattr(_thread_tool_whitelist, "fmt", "Tool '{tool_name}' denied")
        return _PreToolCallDirective(
            action="block",
            message=fmt.format(tool_name=tool_name),
        )
```

---

## 3. `lifecycle.py`(63 行)—— 分发点

63 行,但它是**所有**钩子调用的正门。核心设计:**一等公民先行,插件在后**。

`hermes_cli/lifecycle.py:11-22 @ 863e313`

```
def invoke_hook(hook_name: str, **kwargs: Any) -> List[Any]:
    """Notify first-party observers, then invoke compatibility plugin hooks."""
    try:
        from hermes_cli.observability import observe_lifecycle

        observe_lifecycle(hook_name, **kwargs)
    except Exception:
        logger.warning("Built-in observability hook failed", exc_info=True)

    from hermes_cli import plugins

    return plugins.invoke_hook(hook_name, **kwargs)
```

三个设计点:

1. **内建可观测性不走插件系统。** Hermes 自己的遥测是 `hermes_cli.observability`,
   与插件钩子并列而不是伪装成插件。好处:关掉全部插件后遥测仍在;
   插件的 `plugins.enabled` 门不会误伤自家指标。
2. **内建先跑,且失败被吞。** 内建挂了只记 WARNING,插件照跑。顺序意味着遥测拿到的是**未经插件改写**的原始事实。
3. **返回值只来自插件。** `observe_lifecycle` 的返回被丢弃——内建观察者**不能**改变行为,
   只有插件能。这是一条清晰的分权。

`has_hook` 同构,用于"有没有人关心这个事件"的**短路优化**——
昂贵的 payload(比如整段对话历史)只在真有消费者时才构造:

`hermes_cli/lifecycle.py:25-37 @ 863e313`

```
def has_hook(hook_name: str) -> bool:
    """Return whether a first-party observer or plugin consumes a hook."""
    try:
        from hermes_cli.observability import handles_hook

        if handles_hook(hook_name):
            return True
    except Exception:
        logger.warning("Unable to inspect built-in observability hooks", exc_info=True)

    from hermes_cli import plugins

    return plugins.has_hook(hook_name)
```

`finalize_session` 是唯一的特例——它在通知之外还**硬关**一个核心自有的 Relay 会话:

`hermes_cli/lifecycle.py:40-63 @ 863e313`

```
def finalize_session(**kwargs: Any) -> List[Any]:
    """Notify observers and hard-close one core-owned Relay conversation."""
    try:
        from hermes_cli.observability import observe_lifecycle

        observe_lifecycle("on_session_finalize", **kwargs)
    except Exception:
        logger.warning("Built-in observability hook failed", exc_info=True)

    session_id = str(kwargs.get("session_id") or "")
    if session_id:
        try:
            from agent import relay_runtime

            relay_runtime.SESSION_COORDINATOR.finalize_conversation(
                profile_key=relay_runtime.current_profile_key(),
                session_id=session_id,
            )
        except Exception:
            logger.warning("Core Relay session finalization failed", exc_info=True)

    from hermes_cli import plugins

    return plugins.invoke_hook("on_session_finalize", **kwargs)
```

**要注意的隐患**:`finalize_session` 与 `invoke_hook("on_session_finalize")` 是两个不同的函数,
后者**不做** Relay 关闭。任何调用方若图省事写成 `invoke_hook("on_session_finalize")`,
观察者和插件照常收到事件,但 Relay 会话泄漏,而且**没有任何报错**。
全仓非测试调用点(搜索面 = 全仓 `*.py` 排除 `./tests`,模式 `"on_session_finalize"`)显示
`cli.py`、`tui_gateway/server.py` 走的是各自的 `_notify_session_boundary`,
需要下一轮确认它们内部落到哪个函数。**这是本簇留给后续轮的第一条移交项(见 §10)。**

全部导入都是**函数内延迟导入**(`from ... import` 写在函数体里)。这不是风格问题:
`lifecycle` 被 `plugins`、`agent`、`gateway`、`tools` 同时依赖,模块级导入必然成环。
延迟导入是 Python 里打破循环依赖的标准手法,代价是每次调用一次 `sys.modules` 查表(已缓存,很便宜)。

---

## 4. `middleware.py`(327 行)—— contract 是什么形状

### 4.1 定位:observer 报告发生了什么,middleware 改变发生什么

`hermes_cli/middleware.py:1-6 @ 863e313`

```
"""Hermes middleware contract helpers.

Observer hooks report what happened. Middleware can change what happens by
rewriting a request or wrapping the actual execution callback. Keep the small
contract helpers here so agent-loop call sites and plugins share one vocabulary.
"""
```

四类中间件,两个维度(工具/LLM × 请求改写/执行包裹):

`hermes_cli/middleware.py:17-34 @ 863e313`

```
OBSERVER_SCHEMA_VERSION = "hermes.observer.v1"
MIDDLEWARE_SCHEMA_VERSION = "hermes.middleware.v1"

TOOL_REQUEST_MIDDLEWARE = "tool_request"
TOOL_EXECUTION_MIDDLEWARE = "tool_execution"
LLM_REQUEST_MIDDLEWARE = "llm_request"
LLM_EXECUTION_MIDDLEWARE = "llm_execution"

# Back-compat aliases for older PoC branches that used API terminology.
API_REQUEST_MIDDLEWARE = LLM_REQUEST_MIDDLEWARE
API_EXECUTION_MIDDLEWARE = LLM_EXECUTION_MIDDLEWARE

VALID_MIDDLEWARE: set[str] = {
    TOOL_REQUEST_MIDDLEWARE,
    TOOL_EXECUTION_MIDDLEWARE,
    LLM_REQUEST_MIDDLEWARE,
    LLM_EXECUTION_MIDDLEWARE,
}
```

**契约版本化**是个细节但很重要:

`hermes_cli/middleware.py:47-55 @ 863e313`

```
def observer_payload(**kwargs: Any) -> Dict[str, Any]:
    kwargs.setdefault("telemetry_schema_version", OBSERVER_SCHEMA_VERSION)
    return kwargs


def middleware_payload(**kwargs: Any) -> Dict[str, Any]:
    kwargs.setdefault("telemetry_schema_version", OBSERVER_SCHEMA_VERSION)
    kwargs.setdefault("middleware_schema_version", MIDDLEWARE_SCHEMA_VERSION)
    return kwargs
```

observer 的 payload 只带**一个**版本号,middleware 的带**两个**——
因为中间件同时是观察者(能看到全部遥测字段)又是改写者(多一层自己的契约)。
用 `setdefault` 而不是直接赋值,意味着**调用方可以覆盖版本号**(测试与兼容层需要),
但默认永远有值。插件因此可以写 `if kwargs.get("middleware_schema_version") == "hermes.middleware.v1": ...`
而不必担心 KeyError。

### 4.2 能改写请求吗?能 —— 而且是发给 provider 之前的最终 kwargs

`hermes_cli/middleware.py:81-85 @ 863e313`

```
    """Apply registered LLM request middleware.

    Middleware may return ``{"request": {...}}`` to replace the effective
    provider kwargs before Hermes sends them.
    """
```

`hermes_cli/middleware.py:104-110 @ 863e313`

```
        if not isinstance(result, dict):
            continue
        next_request = result.get("request")
        if not isinstance(next_request, dict):
            continue
        current_request = _safe_copy(next_request)
        trace.append(_trace_entry(result))
```

**这是本簇最强的一个能力**:`request` 就是要发给模型提供方的完整 kwargs——
`messages`、`system`、`tools`、`model`、`temperature` 全在里面。
一个 `llm_request` 中间件可以改系统提示、删掉工具定义、把对话历史换掉、把模型换成别的。
链式:多个中间件按注册顺序串联,后一个看到前一个的结果。

工具侧同理,且时机说得很精确:

`hermes_cli/middleware.py:125-128 @ 863e313`

```
    """Apply registered tool request middleware.

    Middleware may return ``{"args": {...}}`` to replace the effective tool
    arguments before hooks, guardrails, approvals, and execution see them.
    """
```

**"before hooks, guardrails, approvals, and execution see them"** —— 这一句是安全上的关键:
工具请求中间件跑在**审批之前**。所以一个中间件把 `rm -rf /tmp/x` 改成 `rm -rf /`,
审批环节看到的是改后的命令(好:审批看到真实将执行的东西)。反过来,
它也可以把危险命令改成看着无害的形式**然后**在执行中间件里换回去——这是中间件天生的权力,
只能靠"谁能注册中间件"来控制,不能靠链内检查。

一个一等公民的拦截器和插件中间件共用这条管道:

`hermes_cli/middleware.py:134-146 @ 863e313`

```
    session_id = str(context.get("session_id") or "")
    skip_relay = bool(context.pop("skip_relay", False))
    if session_id and not skip_relay:
        from agent import relay_runtime

        relay_args = relay_runtime.apply_tool_request_intercepts(
            session_id=session_id,
            tool_name=tool_name,
            args=current_args,
        )
        if relay_args != current_args:
            current_args = _safe_copy(relay_args)
            trace.append({"source": "nemo_relay"})
```

注意它在 `_has_middleware(TOOL_REQUEST_MIDDLEWARE)` 检查**之前**,所以即使一个插件中间件都没注册,
Relay 拦截照跑。`trace` 里用 `{"source": "nemo_relay"}` 标记来源,
使"这次调用的参数被谁改过"可审计。**可追溯性是中间件设计的必需品**,否则一次被改写的调用无从解释。

### 4.3 能包住执行吗?能 —— 而且可以不执行

`_run_execution_chain` 是本文件的核心。逐段看。

`hermes_cli/middleware.py:267-275 @ 863e313`

```
    def call_at(index: int, payload: Any) -> Any:
        if index >= len(callbacks):
            return terminal_call(payload)

        callback = callbacks[index]
        next_called = False
        next_succeeded = False
        next_result: Any = None
```

递归下降,末端是真正的 provider 调用 / 工具执行。中间件收到一个 `next_call`,
**可以不调用它** —— 那样真实执行就永远不发生,中间件返回什么就是什么。
换句话说:一个 `llm_execution` 中间件可以**凭空编造一个模型回复**,
一个 `tool_execution` 中间件可以**编造工具结果**。这是缓存、录制回放、离线 mock 的实现基础,
也是这个扩展点最危险的地方。

`next_call` 是**一次性**的:

`hermes_cli/middleware.py:276-294 @ 863e313`

```
        def next_call(next_payload: Any = None) -> Any:
            nonlocal next_called, next_succeeded, next_result
            # ``next_call`` is single-use per middleware frame. Calling it more
            # than once would re-run the downstream provider/tool, so a second
            # invocation is a contract violation rather than a retry. Surface it
            # instead of silently executing the terminal call twice.
            if next_called:
                raise RuntimeError(
                    f"Middleware '{kind}' callback "
                    f"{getattr(callback, '__name__', repr(callback))} called "
                    "next_call() more than once; downstream execution is single-use"
                )
            next_called = True
            try:
                next_result = call_at(index + 1, payload if next_payload is None else next_payload)
                next_succeeded = True
                return next_result
            except Exception as exc:
                raise _DownstreamExecutionError(exc) from exc
```

理由写得很好:第二次调用**不是重试,是契约违规**。因为下游是真实副作用
(真花钱调模型、真删文件),偷偷跑两遍比报错糟糕得多。

错误处理的三分支是本文件最精妙的一段:

`hermes_cli/middleware.py:299-314 @ 863e313`

```
        try:
            return callback(**call_kwargs)
        except _DownstreamExecutionError as exc:
            raise exc.original
        except Exception as exc:
            logger.warning(
                "Middleware '%s' callback %s raised: %s",
                kind,
                getattr(callback, "__name__", repr(callback)),
                exc,
            )
            if next_succeeded:
                return next_result
            if next_called:
                raise
            return call_at(index + 1, payload)
```

逐条翻译:

- **下游炸的**(`_DownstreamExecutionError`)→ 原样抛出。用私有异常类型包一层再解包,
  是为了区分"是我下游炸的"和"是这个中间件自己炸的"——否则中间件里一个笔误会被误当成 provider 故障。
- **中间件自己炸了,但下游已经成功**(`next_succeeded`)→ **返回下游结果**。
  模型已经调过了、钱已经花了,不能因为一个后置装饰逻辑出错就丢掉结果。
- **中间件炸了,下游调过但没成功**(`next_called`)→ 抛。
- **中间件炸了,压根没调下游** → **跳过它,继续下一个中间件**。

最后一条是**可用性优先于完整性**的明确选择:一个崩掉的中间件被静默跳过,链继续。
如果有人用中间件做安全策略(比如"拦截所有含密钥的请求"),
**它崩了等于不设防,而且只有一行 WARNING**。这个取舍必须写进设计蓝图:
**中间件不是安全边界,是功能扩展点。** 要做安全,用 `pre_tool_call` 的 block(那条是 fail-closed 的)。

### 4.4 深拷贝的容错

`hermes_cli/middleware.py:59-74 @ 863e313`

```
    """Deep-copy a request payload, tolerating non-deepcopyable members.

    Request payloads are normally plain JSON-shaped dicts, but an LLM request
    can occasionally carry non-deepcopyable objects (clients, callbacks, file
    handles). A hard ``deepcopy`` failure there would otherwise abort the whole
    request-middleware pass. Fall back to a shallow ``dict`` copy so middleware
    still runs and the original nested objects are shared by reference rather
    than corrupting the live payload.
    """
    try:
        return deepcopy(payload)
    except Exception as exc:  # pragma: no cover - exercised via fallback test
        logger.debug("deepcopy failed for request payload (%s); using shallow copy", exc)
        if isinstance(payload, dict):
            return dict(payload)
        return payload
```

深拷贝的目的是**给中间件一个可以随便改的副本**,同时保住 `original_request` 做对照。
浅拷贝兜底时嵌套对象是共享引用——注释诚实地说了这一点。

### 4.5 一处耦合味道

`hermes_cli/middleware.py:248-251 @ 863e313`

```
def _get_middleware_callbacks(kind: str) -> List[Callable]:
    from hermes_cli.plugins import get_plugin_manager

    return list(get_plugin_manager()._middleware.get(kind, []))
```

`middleware.py` 直接伸手拿 `PluginManager` 的**私有属性** `_middleware`。
`invoke_middleware` / `has_middleware` 都有公开函数,唯独取回调列表没有。
不是缺陷,但如果要重构 PluginManager 的内部存储,这里会静默地跟着坏。

---

## 5. `profile_distribution.py`(782 行)—— git 分发 profile

### 5.1 它是什么

`hermes_cli/profile_distribution.py:1-13 @ 863e313`

```
"""Profile distributions — shareable, packaged Hermes profiles via git.

A distribution is a Hermes profile published as a git repository (or
installed from a local directory for development). Install with one command
from a git URL, update in place, and keep your local memories / sessions /
credentials untouched.

Where this fits relative to the existing pieces:

* ``hermes profile export/import`` — local backup / restore for a profile
  on your own machine. NOT a distribution format. Stays as-is.
* ``hermes skills install <url>`` — the URL install pattern we're mirroring,
  but at the profile granularity.
```

### 5.2 拉一个别人的 profile,里面能带什么?

这是任务书的要害问题。答案由两条规则共同决定:**排除表**与**拷贝分支**。

排除表(用户自有、永不覆盖):

`hermes_cli/profile_distribution.py:97-120 @ 863e313`

```
# Paths that are NEVER part of a distribution. These are user-owned and are
# protected on update. Must stay consistent with
# ``profiles.py::_DEFAULT_EXPORT_EXCLUDE_ROOT`` plus the ``local/``
# convention for user customizations.
USER_OWNED_EXCLUDE: frozenset = frozenset({
    # Credentials & runtime secrets
    "auth.json", ".env",
    # Databases & runtime state
    "state.db", "state.db-shm", "state.db-wal",
    "hermes_state.db", "response_store.db",
    "response_store.db-shm", "response_store.db-wal",
    "gateway.pid", "gateway_state.json", "processes.json",
    "auth.lock", "active_profile", ".update_check",
    "errors.log", ".hermes_history",
    # User data
    "memories", "sessions", "logs", "plans", "workspace", "home",
    "image_cache", "audio_cache", "document_cache",
    "browser_screenshots", "checkpoints", "sandboxes",
    "backups", "cache",
    # Infrastructure
    "hermes-agent", ".worktrees", "profiles", "bin", "node_modules",
    # User customization namespace
    "local",
})
```

拷贝分支(**清单没声明 `distribution_owned` 时**走这条,注释明说是为了兼容既有分发):

`hermes_cli/profile_distribution.py:626-643 @ 863e313`

```
    else:
        # Legacy behaviour: no explicit allowlist means the whole staged
        # payload (minus USER_OWNED_EXCLUDE) is distribution-owned.  Do NOT
        # narrow to DEFAULT_DIST_OWNED here — existing distributions ship
        # arbitrary extra top-level paths without declaring them.
        for entry in staged.iterdir():
            name = entry.name

            if name in USER_OWNED_EXCLUDE:
                continue
            if name == ENV_TEMPLATE_FILENAME:
                shutil.copy2(entry, target / ENV_EXAMPLE_FILENAME)
                continue
            if name == "config.yaml" and preserve_config and (target / "config.yaml").exists():
                # Leave user's config.yaml alone on update
                continue

            _copy_entry(entry, target / name)
```

**关键推论**:这是一个**黑名单**,不是白名单。凡是不在 `USER_OWNED_EXCLUDE` 里的顶层条目,
都会被原样拷进 profile 目录。用 AST 直接读常量核对(不 import、不执行):

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python -c "
import ast
t=ast.parse(open('hermes_cli/profile_distribution.py').read())
for n in ast.walk(t):
    if isinstance(n,ast.AnnAssign) and getattr(n.target,'id','')=='USER_OWNED_EXCLUDE':
        v=ast.literal_eval(n.value.args[0]); print('size',len(v))
        for p in ('plugins','hooks','config.yaml','skills','cron','local','.env'):
            print(f'  {p!r:14} excluded? {p in v}')"
```

实测输出:

```console
size 37
  'plugins'      excluded? False
  'hooks'        excluded? False
  'config.yaml'  excluded? False
  'skills'       excluded? False
  'cron'         excluded? False
  'local'        excluded? True
  '.env'         excluded? True
```

`plugins` 与 `hooks` **都不在排除表里**。

### 5.3 完整链条:git 仓库 → 进程内执行

把 §2、§5.2 和 §1 表里的 #4 拼起来,一条端到端路径成立:

1. 一个 distribution 仓库根目录放 `plugins/evil/{plugin.yaml,__init__.py}` 和 `config.yaml`。
2. 用户跑 `hermes profile install github.com/x/y --name z`。
3. `install_distribution` → `_copy_dist_payload(..., preserve_config=False)`。
   **全新安装时 `preserve_config=False`**,所以分发方的 `config.yaml` 原样落地:

`hermes_cli/profile_distribution.py:688-695 @ 863e313`

```
        # Fresh install: config.yaml comes from the distribution.
        _bootstrap_user_dirs(plan.target_dir)
        _copy_dist_payload(
            plan.staged_dir,
            plan.target_dir,
            plan.manifest,
            preserve_config=False,
        )
```

4. `plugins/` 落到 `~/.hermes/profiles/z/plugins/`,而 `get_hermes_home()` 在
   `hermes -p z` 下正是这个目录,即 §2.1 的 **user 源**。
5. 分发方的 `config.yaml` 里写 `plugins.enabled: [evil]`,§2.2 的门就开了。
6. 用户第一次 `hermes -p z chat` → discovery → `exec_module`。

同理 `hooks/` 落到 `~/.hermes/profiles/z/hooks/`,由 `gateway/hooks.py` 无条件执行
(§1 表 #4,门禁只要求 HOOK.yaml 有 `name` 和非空 `events`):

`gateway/hooks.py:96-104 @ 863e313`

```
        for hook_dir in sorted(HOOKS_DIR.iterdir()):
            if not hook_dir.is_dir():
                continue

            manifest_path = hook_dir / "HOOK.yaml"
            handler_path = hook_dir / "handler.py"

            if not manifest_path.exists() or not handler_path.exists():
                continue
```

`gateway/hooks.py:133-139 @ 863e313`

```
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                try:
                    spec.loader.exec_module(module)
                except Exception:
                    sys.modules.pop(module_name, None)
                    raise
```

**注:本轮未实际执行该链条**(铁律:不真的装任何插件)。以上是逐行代码走查的结论,
每一步都有锚点。要落实到可执行 PoC,需要在隔离容器里造一个假 distribution,留给后续轮决定是否值得做。

### 5.4 有没有信任校验?没有 —— 搜索面在此

**负结论**:`profile_distribution.py` 全文没有任何签名、校验和、指纹或来源白名单。
搜索面 = 本簇 7 个文件全文,模式(大小写不敏感)
`signature|gpg|sigstore|checksum|sha256|verify_|trusted|allowlist|attest`。重跑:

```verify
cd /home/user/hermes-agent && grep -n -i "signature\|gpg\|sigstore\|checksum\|sha256\|verify_\|trusted\|allowlist\|attest" hermes_cli/profile_distribution.py
```

实测在 `profile_distribution.py` 上的全部命中只有 3 条,且都是**注释里的 "allowlist" 一词**
(278/605/627 行,指 `distribution_owned` 这个路径白名单),没有任何加密学校验。
**该搜索面不覆盖**:git 自身的 commit 签名(`git clone` 不验签,`--depth 1` 也不带 tag 签名校验)、
以及 HTTPS 传输层(那只保证"从这个域名拿到的",不保证"作者签过的")。

文档自己承认了这一点,而且承认得很坦率:

`website/docs/user-guide/profile-distributions.md:619-628 @ 863e313`

> ## Security and trust
>
> Profile distributions are unsigned by default. You're trusting:
>
> - **The git host** (GitHub / GitLab / wherever) to serve the bytes the author pushed.
> - **The author** to not ship a malicious SOUL, skills, or cron jobs.
>
> Cron jobs from a distribution are **not auto-scheduled** — the installer prints `hermes -p <name> cron list` and you enable them explicitly. SOUL.md and skills ARE active as soon as you start chatting with the profile, so read them before your first run if you're installing from someone you don't know.
>
> Rough analogy: installing a distribution is like installing a browser extension or a VS Code extension. Low friction, high power, trust the source. For internal company distributions, use a private repo and your normal git auth — nothing new to configure.

这段把风险面枚举为 **SOUL / skills / cron 三样**,并逐一说明其激活时机。
`plugins/`(进程内任意 Python)、`hooks/`(进程内任意 Python)、
`config.yaml`(可改 `plugins.enabled`、`mcp_servers`、`command_allowlist`、`approvals.deny`)
**一个都没提**。字面无假话,但对读者构建的心智模型明显不足 → 记 **◇-2**(见 §9)。

### 5.5 做对了的部分

**符号链接一律拒绝**(读文件之前就拒):

`hermes_cli/profile_distribution.py:453-464 @ 863e313`

```
def _reject_distribution_symlinks(staged: Path) -> None:
    """Reject symlinks before reading or copying distribution files."""
    for entry in staged.rglob("*"):
        if not entry.is_symlink():
            continue
        try:
            rel = entry.relative_to(staged)
        except ValueError:
            rel = entry
        raise DistributionError(
            f"Profile distributions cannot contain symlinks: {rel}"
        )
```

这挡住了"仓库里放一个指向 `~/.ssh/id_rsa` 的符号链接,拷贝时把内容带出来"的经典手法。
注意时序:`plan_install` 里 `_stage_source` 之后**立刻** `_reject_distribution_symlinks`,
在 `read_manifest` 之前。

显式 `distribution_owned` 白名单分支里的路径消毒:

`hermes_cli/profile_distribution.py:604-614 @ 863e313`

```
    if explicit_owned:
        # Path-aware allowlist: copy exactly the declared paths.
        for rel in explicit_owned:
            rel_parts = PurePosixPath(rel).parts
            if not rel_parts or rel_parts[0] in USER_OWNED_EXCLUDE:
                continue
            if ".." in rel_parts or PurePosixPath(rel).is_absolute():
                continue
            src = staged.joinpath(*rel_parts)
            if not src.exists():
                continue
```

`..` 与绝对路径都拒。这正是 §2.9 那个 GHSA 缺陷的同类防御,写在了正确的位置。

克隆用非交互 git 环境,防止挂在凭据提示上:

`hermes_cli/profile_distribution.py:395-402 @ 863e313`

```
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest)],
            check=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            env=noninteractive_git_env(),
        )
```

`.git` 克隆后立刻删掉,避免把 remote / 凭据缓存带进 profile:

`hermes_cli/profile_distribution.py:425-435 @ 863e313`

```
    if _looks_like_git_url(src_str):
        cloned = workdir / "clone"
        _git_clone(src_str, cloned)
        # Remove .git to keep the staged tree clean
        shutil.rmtree(cloned / ".git", ignore_errors=True)
        if not (cloned / MANIFEST_FILENAME).is_file():
            raise DistributionError(
                f"No {MANIFEST_FILENAME} at the root of {src_str!r}. "
                "This repository is not a Hermes profile distribution."
            )
        return cloned, src_str
```

版本兼容检查**前置**,失败得早(在拷贝任何文件之前):

`hermes_cli/profile_distribution.py:315-321 @ 863e313`

```
def check_hermes_requires(spec: str, current_version: str) -> None:
    """Raise DistributionError if ``current_version`` does not satisfy ``spec``.

    ``spec`` accepts a single comparator (``>=0.12.0``, ``==0.12.0``, etc.).
    Empty or blank spec is a no-op — no requirement.
    """
    if not spec or not spec.strip():
```

它在 `plan_install` 里紧跟 `read_manifest` 之后被调用:

`hermes_cli/profile_distribution.py:527-528 @ 863e313`

```
    # Version check up-front so we fail fast
    check_hermes_requires(manifest.hermes_requires, hermes_version)
```

**"计划阶段就把能查的都查掉"是这个模块的一贯风格**——符号链接、版本、profile 名冲突
全在 `plan_install` 里判完,`install_distribution` 只负责执行。
这也是为什么 `InstallPlan` 能被单独拿去给用户看(`hermes profile install` 的预览)。

拒绝安装成 `default`(不许覆盖根 profile):

`hermes_cli/profile_distribution.py:534-539 @ 863e313`

```
    if canon == "default":
        raise DistributionError(
            "Cannot install a distribution as 'default' — that is the built-in "
            "root profile (~/.hermes).  Pass --name <name> to install under a "
            "new profile."
        )
```

### 5.6 ▲-1:`#<ref>` 固定版本,文档有、代码无

模块 docstring 明确承诺可以用 `#<ref>` 钉住 tag / 分支 / commit SHA:

`hermes_cli/profile_distribution.py:21-28 @ 863e313`

```
``<source>`` is one of:

* A git URL (``github.com/user/repo``, ``https://github.com/...``, ``git@...``,
  ``ssh://``, ``git://``), optionally with ``#<ref>`` to pin a tag / branch /
  commit SHA.
* A local directory that already contains ``distribution.yaml`` — used
  during profile development before the first push.
```

但 `_stage_source` 把整个字符串原样交给 `_git_clone`,`_git_clone` 只做 GitHub 简写归一化,
**从不切分 `#`**,也从不传 `--branch` / 后续 `checkout`:

`hermes_cli/profile_distribution.py:391-402 @ 863e313`

```
def _git_clone(url: str, dest: Path) -> None:
    # Normalize github.com/user/repo shorthand
    if re.match(r"^github\.com/[\w.-]+/[\w.-]+/?$", url):
        url = f"https://{url.rstrip('/')}"
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest)],
            check=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            env=noninteractive_git_env(),
        )
```

**搜索面**:全文件搜 `#` 的解析。重跑:

```verify
cd /home/user/hermes-agent && grep -n 'split("#")\|rsplit\|partition\|fragment\|#<ref>' hermes_cli/profile_distribution.py
```

实测唯一命中是 docstring 第 24 行那句 `#<ref>` 本身,**没有任何解析代码**。

**后果不是"功能缺失"那么轻**:用户写 `hermes profile install github.com/x/y#v1.0`,
`_looks_like_git_url` 因为 `startswith("http")` 不成立、也不匹配那条严格的 GitHub 简写正则
(`^github\.com/[\w.-]+/[\w.-]+/?$` 里 `#` 不属于 `[\w.-]`),于是**整条路径落到"本地目录"分支**,
最终报 `Cannot resolve distribution source`。也就是说照文档写会直接失败,不会静默拉到错误版本——
失败模式是安全的,但文档是错的。而且 `update_distribution` 复用 `manifest.source`
再走一次 `plan_install`,**每次 update 都拉默认分支的最新 HEAD**,没有任何版本锁定。
文档末尾其实自己承认了:"Future versions may add signing, a lockfile
(`.distribution-lock.yaml`) with a resolved commit SHA ... None of those are shipping yet."
—— 但这与前面 docstring 的 `#<ref>` 承诺互相矛盾。**记 ▲-1。**

### 5.7 ▲-2:`*_cache/` 通配符,代码里只有三个具名目录

`website/docs/user-guide/profile-distributions.md:597-611 @ 863e313`

> ## What's NOT in a distribution (ever)
>
> The installer hard-excludes these paths even if an author accidentally ships them. No config option lets you override this — the safety guard is a regression-tested invariant:
>
> - `auth.json` — OAuth tokens, platform credentials
> - `.env` — API keys, secrets
> - `memories/` — conversation memory
> - `sessions/` — conversation history
> - `state.db`, `state.db-shm`, `state.db-wal` — session metadata
> - `logs/` — agent and error logs
> - `workspace/` — generated working files
> - `plans/` — scratch plans
> - `home/` — user's home mount in Docker backends
> - `*_cache/` — image / audio / document caches
> - `local/` — user-reserved customization namespace

代码里的匹配是 `if name in USER_OWNED_EXCLUDE` —— **精确字符串成员判断,没有任何 glob**。
`USER_OWNED_EXCLUDE` 里的缓存条目只有三个具名项 `image_cache` / `audio_cache` / `document_cache`
(外加一个裸 `cache`),见 §5.2 的常量原文。所以文档写的 `*_cache/` 是错的:
一个分发若带 `embedding_cache/` 或 `video_cache/`,**会被照常拷进用户 profile**。
后半句"image / audio / document caches"倒是准确列出了实际的三个。**记 ▲-2**(小,但具体可查)。

---

## 6. `mcp_catalog.py`(831 行)—— "Nous-approved" 体现在哪一步

### 6.1 答案:approve 是一个**流程**,不是一段代码

`hermes_cli/mcp_catalog.py:9-19 @ 863e313`

```
Catalog policy:
- Entries are added only by merging a PR into hermes-agent. Presence in the
  ``optional-mcps/`` directory = Nous approval. No community tier, no trust
  signals beyond "it's in the catalog".
- Manifests pin transport details (commands, args, refs). Pins follow the
  same supply-chain rules as pyproject dependencies: exact versions for
  package launchers (``uvx pkg==X``, ``npx pkg@X``), full commit SHAs for
  git installs, and the pinned release should be at least 2 weeks old at
  pin time. MCPs are never
  auto-updated; users explicitly re-run ``hermes mcp install <name>`` to
  pull a new manifest version after a repo update.
```

这段自己讲得很清楚:**"在 `optional-mcps/` 目录里"就是批准的全部含义。**
代码里没有签名验证、没有发布者白名单、没有 trust level 字段
(对比 `skills_hub` 有 `builtin/trusted/community` 三档)。批准发生在 GitHub 的 PR review 环节,
运行时只是**读目录**:

`hermes_cli/mcp_catalog.py:305-315 @ 863e313`

```
    root = _catalog_root()
    if not root.exists():
        return []
    entries: List[CatalogEntry] = []
    _CATALOG_DIAGNOSTICS.clear()
    for child in sorted(root.iterdir()):
        manifest = child / "manifest.yaml"
        if not manifest.is_file():
            continue
        try:
            entries.append(_parse_manifest(manifest))
```

**这不是缺陷,是一个诚实的设计选择**,而且文档-代码一致(所以不是 ▲)。
把"批准"外包给版本控制系统的 code review,好处是零运行时密码学、零密钥管理;
代价是**目录本身的完整性就是全部安全性**。

于是要问:那个目录能被谁改?

`hermes_constants.py:215-228 @ 863e313`

```
def get_optional_mcps_dir(default: Path | None = None) -> Path:
    """Return the optional-mcps directory, honoring package-manager wrappers.

    Mirrors :func:`get_optional_skills_dir` for the MCP catalog (Nous-approved
    Model Context Protocol servers shipped with the repo but disabled by
    default). Packaged installs may ship ``optional-mcps`` outside the Python
    package tree and expose it via ``HERMES_OPTIONAL_MCPS``.
    """
    override = os.getenv("HERMES_OPTIONAL_MCPS", "").strip()
    if override:
        return Path(override)
    if default is not None:
        return default
    return get_hermes_home() / "optional-mcps"
```

有一个环境变量能整体换掉目录。所以"Nous-approved"的实际信任根是
**「安装目录的文件系统权限」+「`HERMES_OPTIONAL_MCPS` 没被改」**。
代码自己也意识到目录可被本地改动:

`hermes_cli/mcp_catalog.py:333-343 @ 863e313`

```
def catalog_diagnostics() -> List[tuple]:
    """Diagnostics from the most recent :func:`list_catalog` call.

    Returns a list of ``(entry_name, kind, message)`` tuples where ``kind``
    is one of:
      - ``future_manifest`` — manifest_version is newer than this Hermes
        understands. Update Hermes to install this entry.
      - ``invalid`` — manifest is malformed in some other way (caught by
        CI for shipped manifests; user-modified manifests can hit this).
    """
```

### 6.2 装一个目录条目会执行任意 shell

`hermes_cli/mcp_catalog.py:391-403 @ 863e313`

```
def _run_bootstrap(cwd: Path, commands: List[str]) -> None:
    """Execute bootstrap commands in *cwd*. Raise CatalogError on first failure.

    Each command runs through the shell (so `&&` etc. work). The output is
    streamed to the user's terminal for visibility.
    """
    for cmd in commands:
        print(color(f"  $ {cmd}", Colors.DIM))
        proc = subprocess.run(cmd, cwd=str(cwd), shell=True)
        if proc.returncode != 0:
            raise CatalogError(
                f"bootstrap step failed (exit {proc.returncode}): {cmd}"
            )
```

`shell=True` + 清单里的字符串 = 任意命令。缓解措施是**回显**(`print(f"  $ {cmd}")`),
让用户能看见跑了什么。清单校验只检查 `bootstrap` 是个 list,不检查内容:

`hermes_cli/mcp_catalog.py:274-282 @ 863e313`

```
        bootstrap = install_raw.get("bootstrap") or []
        if not isinstance(bootstrap, list):
            raise CatalogError(f"{path}: install.bootstrap must be a list")
        install = InstallSpec(
            type=i_type,
            url=url,
            ref=ref,
            bootstrap=[str(c) for c in bootstrap],
        )
```

克隆策略里两个值得记的细节。其一,**每次安装都是全新检出**:

`hermes_cli/mcp_catalog.py:417-421 @ 863e313`

```
    if dest.exists():
        # Fresh checkout each install — manifest version is the source of truth,
        # so wipe + re-clone for determinism.
        print(color(f"  Removing existing install at {dest}", Colors.DIM))
        shutil.rmtree(dest)
```

"清空重来"而不是 `git pull`,理由是**确定性**:清单里的 ref 是唯一真相,
不允许本地状态(未提交改动、分支漂移)影响结果。代价是每次重装都要重下。
对供应链敏感的东西,这个取舍选得对。

其二,**SHA 型 ref 走不同的克隆路径**:

`hermes_cli/mcp_catalog.py:425-429 @ 863e313`

```
    # `git clone --branch` only accepts branches and tags, NOT commit SHAs.
    # Detecting SHA-shaped refs upfront avoids a guaranteed stderr leak on
    # the fast path (the --branch attempt would always fail noisily for a
    # SHA ref before we fall back to full-clone-then-checkout).
    is_sha_ref = bool(re.fullmatch(r"[0-9a-f]{7,40}", install.ref))
```

`git clone --branch` 不接受 commit SHA,所以 SHA 要走"全量克隆 + checkout"。
预先判断只是为了不让用户看到一条必然失败的 git 报错。
**注意这里 MCP 目录是真的支持 ref 固定的**,而且 `ref` 是必填项:

`hermes_cli/mcp_catalog.py:270-273 @ 863e313`

```
        url = install_raw.get("url") or ""
        ref = install_raw.get("ref") or ""
        if not url or not ref:
            raise CatalogError(f"{path}: install.url and install.ref are required")
```

与 §5.6 的 profile 分发形成对比——**同一个仓库里,一个分发通道强制钉版本,另一个连解析 ref 的代码都没有。**
这个不一致本身就是 R12 该讨论的东西:两条通道拉的都是任意 git 仓库,
危险程度相当,供应链纪律却相差一整个数量级。

这与 §2.6 的插件安装形成鲜明对比:**插件安装只 clone 不执行,MCP 目录安装会执行 shell。**
两个"安装"在同一个 CLI 下,风险等级完全不同。设计同级 harness 时,
这种"名字一样、危险程度不一样"的动词最容易让用户建立错误直觉。

### 6.3 ■-2:供应链检查跑在任意 shell **之后**

`install_entry` 的顺序:

`hermes_cli/mcp_catalog.py:747-749 @ 863e313`

```
    install_dir: Optional[Path] = None
    if entry.install is not None:
        install_dir = _do_git_install(entry)
```

`hermes_cli/mcp_catalog.py:783-791 @ 863e313`

```
    server_cfg = _build_server_config(entry, install_dir)
    server_cfg["enabled"] = enable

    from hermes_cli.mcp_config import _save_mcp_server

    if not _save_mcp_server(entry.name, server_cfg):
        raise CatalogError(
            f"catalog entry '{entry.name}' rejected: suspicious command/args configuration"
        )
```

`_save_mcp_server` 是那道"可疑命令"闸:

`hermes_cli/mcp_config.py:88-100 @ 863e313`

```
def _save_mcp_server(name: str, server_config: dict) -> bool:
    """Add or update a server entry in config.yaml.

    Returns False when a high-signal exfiltration-shaped stdio command is
    rejected. MCP stdio servers are user-chosen local commands, so this blocks
    shell+egress payloads rather than whitelisting command families.
    """
    issues = validate_mcp_server_entry(name, server_config)
    if issues:
        for issue in issues:
            _warning(issue)
        _warning(f"Server '{name}' was NOT saved due to suspicious configuration.")
        return False
```

**问题**:`_do_git_install`(含 `_run_bootstrap` 的任意 shell)在第 749 行,
可疑命令检查在第 788 行。一个 `transport.command` 会被拒的清单,
它的 `install.bootstrap` **已经跑完了**。检查拦住的只是"把这条命令写进 config.yaml",
拦不住"这次安装执行了什么"。

对随仓目录来说这不是活跃风险(条目经 PR review),但对
`HERMES_OPTIONAL_MCPS` 指向别处、或用户手改了 `optional-mcps/` 的情形,
这个顺序意味着**唯一的自动化闸门站在马已经跑了之后**。**记 ■-2。**
修法很自然:先 `_build_server_config` + `validate_mcp_server_entry`(纯函数,不落盘),
通过了再 `_do_git_install`。

### 6.4 凭据处理

`hermes_cli/mcp_catalog.py:483-504 @ 863e313`

```
def _prompt_env_vars(specs: List[EnvVarSpec]) -> Dict[str, str]:
    """Walk the env spec list, prompting the user for each. Writes secrets and
    non-secrets alike to ~/.hermes/.env via save_env_value()."""
    collected: Dict[str, str] = {}
    for spec in specs:
        existing = get_env_value(spec.name)
        if existing:
            print(color(f"  ✓ {spec.name} already set in .env", Colors.GREEN))
            collected[spec.name] = existing
            continue
        value = _prompt_input(
            spec.prompt,
            default=spec.default or None,
            password=spec.secret,
        )
        if not value:
            if spec.required:
                raise CatalogError(f"{spec.name} is required but no value was provided")
            continue
        save_env_value(spec.name, value)
        collected[spec.name] = value
```

规矩很正:**密钥只进 `.env`,不进 `config.yaml`**(`.env` 是唯一凭据存放处),
非密钥也一起放 `.env` 以保持"一个凭据仓库"。已存在的值不覆盖。
`transport.env` 那个静态 env 字典明确注明"NOT for secrets"
(`hermes_cli/mcp_catalog.py:85-88`),两条通道分得干净。

还有一处很好的**解析期契约检查**:

`hermes_cli/mcp_catalog.py:233-247 @ 863e313`

```
    if t_type == "http" and a_type == "api_key":
        # _build_server_config emits an Authorization header referencing
        # ${MCP_<NAME>_API_KEY} (via _bearer_auth_headers), but install_entry
        # only persists the env vars DECLARED in auth.env. Enforce the naming
        # contract at parse time, or a manifest declaring e.g. N8N_API_KEY
        # would install cleanly yet send a literal-placeholder header (401)
        # at connect time.
        from hermes_cli.mcp_config import _env_key_for_server

        _required_key = _env_key_for_server(name)
        if not any(spec.name == _required_key for spec in env_list):
            raise CatalogError(
                f"{path}: http + api_key auth requires auth.env to declare "
                f"'{_required_key}' (the key the Authorization header references)"
            )
```

**把"安装成功但运行时 401"这种延迟故障提前到解析期报错**,是很值得抄的模式。

---

## 7. `agent_import.py`(1024 行)—— 从 Claude Code / Codex 导入

### 7.1 导入哪些字段

`hermes_cli/agent_import.py:18-31 @ 863e313`

```
Mappings
--------
claude-code (~/.claude):
    CLAUDE.md                       → memory entries in HERMES_HOME/memories/MEMORY.md
    settings.json permissions.allow → config.yaml command_allowlist (Bash(...) rules)
    settings.json permissions.deny  → config.yaml approvals.deny (Bash(...) rules)
    mcpServers (~/.claude.json or settings.json) → config.yaml mcp_servers
    skills/<name>/SKILL.md          → HERMES_HOME/skills/claude-code-imports/<name>/

codex (~/.codex):
    AGENTS.md                       → memory entries in HERMES_HOME/memories/MEMORY.md
    config.toml [mcp_servers.*]     → config.yaml mcp_servers
    memories/*.md                   → memory entries in HERMES_HOME/memories/MEMORY.md
    skills/<name>/SKILL.md          → HERMES_HOME/skills/codex-imports/<name>/
```

**权限规则也被导入**——这是本文件里安全影响最大的一项映射。
`permissions.allow` 进 `command_allowlist`(放宽),`permissions.deny` 进 `approvals.deny`(收紧):

`hermes_cli/agent_import.py:636-646 @ 863e313`

```
    def import_permission_allowlist(self, settings: Dict[str, Any]) -> None:
        """settings.json permissions.allow → config.yaml command_allowlist."""
        destination = self.target_root / "config.yaml"
        permissions = settings.get("permissions")
        allow = permissions.get("allow") if isinstance(permissions, dict) else None
        if not isinstance(allow, list) or not allow:
            self.record("command-allowlist", None, destination, "skipped",
                        "No permissions.allow rules found")
            return

        patterns: List[str] = []
```

值得停一下:**导入别的 agent 的配置,等于导入别的 agent 的信任决策。**
用户当初在 Claude Code 里批准 `Bash(rm:*)`,是在那个工具的沙箱/工作区语境下批的;
搬到 Hermes 后语境变了(不同的工作目录、不同的工具集、可能还接了网关和定时任务),
同一条规则的实际风险不同。代码这里做得已经算克制——它是**合并**而不是替换,且每一条都进 report 让用户在 `--dry-run` 里先看见:

`hermes_cli/agent_import.py:667-681 @ 863e313`

```
        current = config.get("command_allowlist", [])
        if not isinstance(current, list):
            current = []
        merged = sorted(dict.fromkeys(list(current) + patterns))
        added = [p for p in merged if p not in current]
        if not added:
            self.record("command-allowlist", "settings.json permissions.allow",
                        destination, "skipped", "All patterns already present")
            return
        details: Dict[str, Any] = {"added_patterns": added}
        if skipped_rules:
            details["unmapped_rules"] = skipped_rules
        if self.execute:
            config["command_allowlist"] = merged
            dump_yaml_file(destination, config)
```

三个细节都对:`dict.fromkeys` 去重且保序后再排序;`added` 只记**新增**的那些
(不把用户已有的规则重复报一遍);`unmapped_rules` 把"Claude 有但 Hermes 没有对应概念"
的规则单独列出来,而不是静默丢弃。**迁移工具必须报告它没能搬过来的东西**,
否则用户会以为迁移是完整的。
但"预览里列出 40 条 Bash 规则"和"用户真的逐条重新评估过"是两回事。
这属于设计取舍而非缺陷,记在这里供 R12 讨论。

整体架构是 **detect → parse → map → apply,带强制预览阶段**,
每一项记 imported / skipped / conflict / error,`--dry-run` 一个字节都不写。
这是迁移类工具的正确骨架:**先算出完整计划再问,而不是边做边问。**

### 7.2 会不会把别人的凭据搬进来?—— 部分会

模块 docstring 的承诺:

`hermes_cli/agent_import.py:33-36 @ 863e313`

```
Secrets are NEVER imported: credential files (.credentials.json, auth.json)
are ignored, and MCP server env vars with secret-looking names (KEY, TOKEN,
SECRET, PASSWORD, ...) are stripped and reported so the user can re-add them
deliberately via ``hermes setup`` or config.yaml.
```

机制是**基于名字的正则**:

`hermes_cli/agent_import.py:74-87 @ 863e313`

```
# Env var names that look like credentials — never copied into config.yaml.
_SECRET_KEY_RE = re.compile(
    r"(?:^|_)(?:API[_-]?KEY|APIKEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIALS?|"
    r"AUTH|PRIVATE[_-]?KEY|ACCESS[_-]?KEY)(?:_|$)|KEY$",
    re.IGNORECASE,
)

# Files inside the source tree that hold credentials — never read.
_CREDENTIAL_FILENAMES = (".credentials.json", "auth.json", "credentials.json")


def is_secret_key(key: str) -> bool:
    """Return True when an env-var name looks like a credential."""
    return bool(_SECRET_KEY_RE.search(key or ""))
```

`hermes_cli/agent_import.py:367-378 @ 863e313`

```
def sanitize_mcp_env(env: Any) -> Tuple[Dict[str, str], List[str]]:
    """Split an MCP server env dict into (kept, stripped-secret-names)."""
    kept: Dict[str, str] = {}
    stripped: List[str] = []
    if not isinstance(env, dict):
        return kept, stripped
    for key, value in env.items():
        if is_secret_key(str(key)):
            stripped.append(str(key))
        else:
            kept[str(key)] = value
    return kept, stripped
```

**这是名字启发式,不是值检测。** 一个叫 `MY_SERVICE_CRED` 或 `GH_PAT` 的环境变量
不匹配这条正则,会被原样搬进 `config.yaml`。被剥掉的会记录到 `stripped_secrets` 并报给用户,
这是正确的补偿(告诉用户"你得手动补这几个"),但不改变覆盖率是启发式的事实。

HTTP header 侧多了一层特判,连大小写变体的 `authorization` 都拦:

`hermes_cli/agent_import.py:779-792 @ 863e313`

```
                headers = srv.get("headers")
                if isinstance(headers, dict):
                    kept_headers = {
                        k: v for k, v in headers.items()
                        if not is_secret_key(str(k))
                        and "authorization" not in str(k).lower()
                    }
                    if kept_headers:
                        hermes_srv["headers"] = kept_headers
                    for k in headers:
                        if k not in kept_headers:
                            self.stripped_secrets.append(
                                f"mcp_servers.{name}.headers.{k}"
                            )
```

### 7.3 ■-3:`_CREDENTIAL_FILENAMES` 是死常量,而 skill 拷贝正好需要它

`_CREDENTIAL_FILENAMES` 在**全仓只出现一次**——它自己的定义处。

**搜索面**:全仓 `*.py`(含测试),模式 `_CREDENTIAL_FILENAMES`。重跑:

```verify
cd /home/user/hermes-agent && grep -rn "_CREDENTIAL_FILENAMES" --include=*.py .
```

实测唯一命中:`./hermes_cli/agent_import.py:82`(定义行本身)。**零个使用点。**

文档说"credential files (.credentials.json, auth.json) are ignored" —— 字面为真
(导入器确实从不主动去读这几个文件),**所以不是 ▲**。但有一条路径正好会把它们搬过来:

`hermes_cli/agent_import.py:823-834 @ 863e313`

```
        for skill_dir in skill_dirs:
            destination = destination_root / skill_dir.name
            if destination.exists() and not self.overwrite:
                self.record("skill", skill_dir, destination, "conflict",
                            "Destination skill already exists")
                continue
            if self.execute:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(skill_dir, destination)
                self.record("skill", skill_dir, destination, "imported")
            else:
                self.record("skill", skill_dir, destination, "imported",
                            "Would copy skill directory")
```

`shutil.copytree(skill_dir, destination)` **没有 `ignore=` 参数**——整个 skill 目录原样复制。
若 `~/.claude/skills/foo/` 里有 `credentials.json`(用户放的、或某个 skill 自己写的缓存),
它会被复制到 `~/.hermes/skills/claude-code-imports/foo/credentials.json`,
而 skills 目录是 agent 会去读、会在提示里索引的地方。
`_CREDENTIAL_FILENAMES` 这个常量**恰好列出了正确的三个文件名**,
只要接到 `copytree(..., ignore=shutil.ignore_patterns(*_CREDENTIAL_FILENAMES))` 就能堵上。
**一个存在、命名正确、却从未接线的守卫** —— 记 **■-3**。

同一处还有第二个问题:`copytree` 默认 `symlinks=False`,即**跟随符号链接并复制其内容**。
对比 §5.5 里 `profile_distribution` 专门写了 `_reject_distribution_symlinks`。
同一个仓库里,一条导入路径防了符号链接,另一条没防。
不过要注意范围:`~/.claude/` 是**本机用户自己的目录**,不是远程内容,
威胁模型比 profile 分发弱得多,所以这一条只记为设计不一致,不单列 ■。

### 7.4 读-改-写的正确姿势

一个值得抄的小设计:配置文件"不存在"与"读不出来"必须分开:

`hermes_cli/agent_import.py:107-118 @ 863e313`

```
def load_yaml_file(path: Path) -> Dict[str, Any]:
    """Load a YAML mapping, distinguishing "absent" from "unreadable".

    Callers read ``config.yaml``, merge a section in, and write the whole
    mapping back — so collapsing a present-but-unreadable file to ``{}``
    would replace every existing setting with just the merged keys.

    - Absent, or present but empty  -> ``{}``; first-time creation still works.
    - Present but unreadable, unparseable, or not a mapping -> raise
      :class:`ConfigReadError` so the caller refuses and leaves the file
      byte-identical.
    """
```

`hermes_cli/agent_import.py:98-104 @ 863e313`

```
class ConfigReadError(RuntimeError):
    """An existing config file is present but cannot be read or parsed.

    Signals that a read-modify-write round trip must be abandoned: the caller
    has no idea what the file holds, so writing a merged result back would
    replace real settings with only the keys it merged.
    """
```

这正是 CLAUDE.md 里 R8B 的 H-7 移交项描述的那类事故(坏 YAML 下把用户的
`approvals.deny` 静默抹掉)的**正确解法**,而且就写在同一个仓库里。
`agent_import.py` 做对了,说明这个模式在本仓库是已知的——那么没做对的地方就是遗漏而非无知。

---

## 8. `skills_hub.py`(2036 行)—— 技能分发的 CLI 前台

### 8.1 定位

`hermes_cli/skills_hub.py:2-11 @ 863e313`

```
"""
Skills Hub CLI — Unified interface for the Hermes Skills Hub.

Powers both:
  - `hermes skills <subcommand>` (CLI argparse entry point)
  - `/skills <subcommand>` (slash command in the interactive chat)

All logic lives in shared do_* functions. The CLI entry point and slash command
handler are thin wrappers that parse args and delegate.
"""
```

真正的抓取 / 隔离 / 扫描实现在 `tools/skills_hub.py` 与 `tools/skills_guard.py`(**不属本簇**),
本文件是编排层。但编排层决定了**策略怎么被应用**,所以安全语义主要由它定。

### 8.2 安装流水线:抓取 → 隔离 → 扫描 → 策略 → 确认 → 安装

`hermes_cli/skills_hub.py:495 @ 863e313`

```
    """Fetch, quarantine, scan, confirm, and install a skill.
```

**隔离(quarantine)在扫描之前**——先把 bundle 落到一个隔离目录,扫那个目录,
过了才 `install_from_quarantine` 进真正的 skills 树。任何一步失败都 `shutil.rmtree(q_path)`。
这是处理不可信内容的标准两阶段落地,值得抄。

`hermes_cli/skills_hub.py:639-648 @ 863e313`

```
    # Quarantine the bundle
    try:
        q_path = quarantine_bundle(bundle)
    except ValueError as exc:
        c.print(f"[bold red]Installation blocked:[/] {exc}\n")
        from tools.skills_hub import append_audit_log
        append_audit_log("BLOCKED", bundle.name, bundle.source,
                         bundle.trust_level, "invalid_path", str(exc))
        return
    c.print(f"[dim]Quarantined to {q_path.relative_to(q_path.parent.parent.parent)}[/]")
```

注意 `quarantine_bundle` 抛的是 `ValueError`,审计日志记的原因是 `"invalid_path"`
—— 说明隔离阶段本身就在做路径消毒(bundle 里的相对路径不许逃出隔离目录)。
**落盘之前先验路径**,和 §5.5 的 `_reject_distribution_symlinks`、
§2.9 的 `_safe_plugin_api_relpath` 是同一个防御模式在第三处出现。

同样的路径校验在**真正落地那一步再做一次**:

`hermes_cli/skills_hub.py:729-738 @ 863e313`

```
    # Install
    try:
        install_dir = install_from_quarantine(q_path, bundle.name, category, bundle, result)
    except ValueError as exc:
        c.print(f"[bold red]Installation blocked:[/] {exc}\n")
        shutil.rmtree(q_path, ignore_errors=True)
        from tools.skills_hub import append_audit_log
        append_audit_log("BLOCKED", bundle.name, bundle.source,
                         bundle.trust_level, "invalid_path", str(exc))
        return
```

两处都记 `"invalid_path"`,即**隔离时验一次、出隔离时再验一次**。
这与 §2.9 GHSA 修复里"发现阶段洗一次、挂载阶段再验一次"是同一条纵深原则。

扫描结果带**溯源信息**(新扫还是命中缓存、扫描器版本、bundle 哈希、规则集):

`hermes_cli/skills_hub.py:667-677 @ 863e313`

```
    c.print(format_scan_report(result))
    freshness = "fresh" if scan_provenance["fresh"] else "cached"
    c.print(
        f"[dim]Scan provenance: {freshness}; scanner "
        f"{scan_provenance['scanner_version']}; hash {scan_provenance['bundle_hash']}[/]"
    )
    rules = ", ".join(scan_provenance["rules"]) or "none"
    c.print(
        f"[dim]Source: {scan_provenance['source_url']}; scanned "
        f"{scan_provenance['scanned_at']}; rules: {rules}[/]"
    )
```

**"扫过了"不是一个布尔值,是一条带版本和哈希的记录。** 这样用户能判断
"这个 pass 是三个月前的旧规则给的还是刚扫的"。设计同级 harness 时这条必须抄。

### 8.3 `--force` 是一个三合一的开关

`hermes_cli/skills_hub.py:679-689 @ 863e313`

```
    # Check install policy
    allowed, reason = should_allow_install(result, force=force)
    if not allowed:
        c.print(f"\n[bold red]Installation blocked:[/] {reason}")
        # Clean up quarantine
        shutil.rmtree(q_path, ignore_errors=True)
        from tools.skills_hub import append_audit_log
        append_audit_log("BLOCKED", bundle.name, bundle.source,
                         bundle.trust_level, result.verdict,
                         f"{len(result.findings)}_findings")
        return
```

`hermes_cli/skills_hub.py:696-699 @ 863e313`

```
    # Confirm with user — show appropriate warning based on source
    # skip_confirm bypasses the prompt (needed in TUI mode where input() hangs)
    if not force and not skip_confirm:
        c.print()
```

同一个 `force` 参数在这个函数里干了**三件事**:

1. §8.2 之前的"已安装则拒绝"→ 允许覆盖重装(`skills_hub.py:630-634`);
2. 传给 `should_allow_install(result, force=force)` → **推翻扫描器的 block 判决**;
3. `if not force and not skip_confirm` → **跳过人工确认面板**。

第 2 项的实际威力(策略表在 `tools/skills_guard.py`,非本簇,仅作参照):

`tools/skills_guard.py:789-796 @ 863e313`

```
    if decision == "allow":
        return True, f"Allowed ({result.trust_level} source, {result.verdict} verdict)"

    if force and not (result.verdict == "dangerous" and result.trust_level in ("community", "trusted")):
        return True, (
            f"Force-installed despite {result.verdict} verdict "
            f"({len(result.findings)} findings)"
        )
```

`tools/skills_guard.py:55-67 @ 863e313`

```
INSTALL_POLICY = {
    #                  safe      caution    dangerous
    "builtin":       ("allow",  "allow",   "allow"),
    "trusted":       ("allow",  "allow",   "block"),
    "community":     ("allow",  "block",   "block"),
    # Agent-created: "ask" on dangerous surfaces as an error to the agent,
    # which can retry without the flagged content. This gate only runs when
    # skills.guard_agent_created is enabled (off by default) — see
    # tools/skill_manager_tool.py::_guard_agent_created_enabled.
    "agent-created": ("allow",  "allow",   "ask"),
}
```

即 `--force` 把 community + **caution** 从 block 翻成 allow;
只有 community/trusted + **dangerous** 这一格是 `--force` 也翻不动的硬底线(设计得对)。

**取舍评价**:一个 flag 同时管"覆盖重装"和"无视安全判决"是有代价的——
用户为了第 1 个目的敲 `--force`,顺手拿到了第 2、3 个。
更好的形状是 `--reinstall` / `--ignore-scan` / `--yes` 三个正交 flag。
这一条在 §10 作为设计原则记下。

### 8.4 `ask` 档在 CLI 侧收敛成了硬 block

`should_allow_install` 用返回 `None` 表示"需要人来定":

`tools/skills_guard.py:798-803 @ 863e313`

```
    if decision == "ask":
        # Return None to signal "needs user confirmation"
        return None, (
            f"Requires confirmation ({result.trust_level} source + {result.verdict} verdict, "
            f"{len(result.findings)} findings)"
        )
```

但 `do_install` 的调用点写的是 `if not allowed:` —— Python 里 `not None` 为 True,
于是 `ask` 走进了 block 分支(见 §8.3 第一段代码)。
方向是**安全的**(fail-closed),但设计意图丢了:那个"让用户确认"的第三态在这条路径上不可达。
目前 `ask` 只可能出现在 `agent-created` + `dangerous` 组合,而 agent 自建技能走的是
`tools/skill_manager_tool.py` 而非 `do_install`,所以**当前不是活跃 bug**。
记为设计不一致,列入 §10 移交,不单列 ■。

### 8.5 快照导入:静默加第三方源 + `force` 全局传播

`hermes_cli/skills_hub.py:1691-1699 @ 863e313`

```
    # Restore taps first
    taps = snapshot.get("taps", [])
    if taps:
        mgr = TapsManager()
        for tap in taps:
            repo = tap.get("repo", "")
            if repo:
                mgr.add(repo, tap.get("path", "skills/"))
        c.print(f"[dim]Restored {len(taps)} tap(s)[/]")
```

`hermes_cli/skills_hub.py:1707-1716 @ 863e313`

```
    c.print(f"[bold]Importing {len(skills)} skill(s) from snapshot...[/]\n")
    for entry in skills:
        identifier = entry.get("identifier", "")
        category = entry.get("category", "")
        if not identifier:
            c.print(f"[yellow]Skipping entry with no identifier: {entry.get('name', '?')}[/]")
            continue

        c.print(f"[bold]--- {entry.get('name', identifier)} ---[/]")
        do_install(identifier, category=category, force=force, console=c)
```

**"tap"是自定义 GitHub 技能源**(相当于给包管理器加一个第三方仓库)。
一个快照 JSON 能**无确认地**往 `TapsManager` 里加任意 repo,然后从那些 repo 装技能。
再叠上 `force=force` 一路传下去,`hermes skills snapshot import x.json --force`
= 加任意源 + 无视扫描 + 无确认,批量。

而且这里**没有传 `source_id`**,而 `do_install` 自己的 docstring 专门警告过这件事:

`hermes_cli/skills_hub.py:504-509 @ 863e313`

```
    ``source_id`` pins resolution to a single source adapter (e.g. ``clawhub``).
    Callers that already know a skill's provenance -- notably ``do_update``,
    which reads it from the lockfile -- should pass it so a bare, slash-less
    identifier cannot be fuzzy-resolved to a same-named skill in a different
    registry. Skill names are not namespaced across registries, so an
    unconstrained resolve can silently change a skill's provenance.
```

快照里**存了** `identifier`,但没存/没传 source。按这段 docstring 自己的标准,
快照导入正属于"已知 provenance 却不传"的情形。记入 §10 移交(需要先确认快照格式里到底有没有 source 字段)。

### 8.6 TUI 路径:静音安装

`tui_gateway/methods_tools.py:1739-1743 @ 863e313`

```
            class _Q:
                def print(self, *a, **k):
                    pass

            do_install(query, skip_confirm=True, console=_Q())
```

`_Q` 是一个**什么都不打印**的假 console。后果:扫描仍然跑、block 仍然拦(`force` 没传,默认 False),
但**扫描报告、溯源信息、第三方风险免责声明全部被吞掉**。
用户在 TUI 里看到的只有最终成败。这是"非交互面必须自己承担告知义务"的典型漏点——
把 UI 输出和策略执行耦合在同一个函数里,静音 UI 就等于静音了知情。
**可迁移原则:策略判定要返回结构化结果,而不是直接 print;呈现由调用方负责。**

---

## 9. 本簇 ▲ / ◇ / ■ / ◎ 定案

### ▲(文档所述与代码矛盾)—— 3 条

**▲-1 · `#<ref>` 版本固定不存在。**
锚点:`hermes_cli/profile_distribution.py:24`(docstring 承诺)vs `hermes_cli/profile_distribution.py:391-402`(`_git_clone` 从不切分 `#`)。
现象:文档说 `<source>` 可带 `#<ref>` 钉 tag/分支/SHA;代码把整串原样交给 `git clone --depth 1`,
全文无任何 `#` 解析。照文档写会落到"本地目录"分支并报 `Cannot resolve distribution source`。详见 §5.6。

**▲-2 · `*_cache/` 通配符不存在。**
锚点:`website/docs/user-guide/profile-distributions.md:610` 与 `:249`(文档**两处**都写 `*_cache/`)
vs `hermes_cli/profile_distribution.py:113`(只有 `image_cache`/`audio_cache`/`document_cache` 三个具名项)
+ `hermes_cli/profile_distribution.py:634`(`if name in USER_OWNED_EXCLUDE`,精确成员判断,无 glob)。

`hermes_cli/profile_distribution.py:113 @ 863e313`

```
    "image_cache", "audio_cache", "document_cache",
```

`hermes_cli/profile_distribution.py:634 @ 863e313`

```
            if name in USER_OWNED_EXCLUDE:
```

现象:分发带 `embedding_cache/` 会被拷进用户 profile,而文档承诺 `*_cache/` 一律排除。
文档在 249 行的"谁拥有什么"总表里又重复了一次同样的通配符写法,所以这不是笔误而是一致的误述。详见 §5.7。

**▲-3 · `requires_env` 不 gate 插件加载。**
锚点:`website/docs/developer-guide/plugins/index.md:446`
vs `hermes_cli/plugins.py:1662`(只解析进 manifest)与 `hermes_cli/plugins.py:1785-1814`(加载路径不查它)。
文档原文(归属标题 `### Gate on environment variables`):

`website/docs/developer-guide/plugins/index.md:446 @ 863e313`

> If `WEATHER_API_KEY` isn't set, the plugin is disabled with a clear message. No crash, no error in the agent — just "Plugin weather disabled (missing: WEATHER_API_KEY)".

同一文件 80-81 行的清单示例注释重复了同样的断言:

`website/docs/developer-guide/plugins/index.md:80-81 @ 863e313`

> requires_env:          # gate loading on env vars; prompted during install
>   - SOME_API_KEY       # simple format — plugin disabled if missing


代码里 `PluginManifest.requires_env` 被解析后**再无读取**:

`hermes_cli/plugins.py:1657-1669 @ 863e313`

```
            return PluginManifest(
                name=name,
                version=str(data.get("version", "")),
                description=data.get("description", ""),
                author=data.get("author", ""),
                requires_env=data.get("requires_env", []),
                provides_tools=data.get("provides_tools", []),
                provides_hooks=data.get("provides_hooks", []),
                source=source,
                path=str(plugin_dir),
                kind=kind,
                key=key,
            )
```

**搜索面**:全仓 `*.py` 排除 `./tests` 与 `./plugins`,模式 `requires_env`;以及全仓搜那句错误提示的形状。重跑:

```verify
cd /home/user/hermes-agent && grep -rn "requires_env" --include=*.py . | grep -v "^./tests" | grep -v "^./plugins/"
cd /home/user/hermes-agent && grep -rn "disabled (missing" --include=*.py .
```

实测:`requires_env` 在非测试代码里的用途只有三类——
(a) `hermes_cli/plugins_cmd.py:300-360` **安装时提示补环境变量**;
(b) `hermes_cli/config.py:5397`、`hermes_cli/web_server.py:5271` **UI 展示**;
(c) `tools/registry.py` 的**同名但不同来源**的 `register_tool(requires_env=...)` 参数,
它 gate 的是**单个工具**在工具集里的可用性,不是插件加载。
第二条命令零命中——"Plugin weather disabled (missing: ...)"这句话在全仓不存在。
文档把 (c) 的语义安到了 (a) 的字段上。**该搜索面不覆盖**:插件自己在 `register()` 里手动查环境变量
然后 `return`(那是插件作者的行为,不是 harness 的 gate)。

### ◇(代码有、文档无)—— 3 条

**◇-1 · 整个 middleware 契约在用户/开发者文档中完全缺席。**
锚点:`hermes_cli/middleware.py:20-23`(四类中间件常量)与
`hermes_cli/plugins.py:1199-1216`(`ctx.register_middleware`)。
**搜索面**:整个 `website/docs/` 目录树,模式 `register_middleware|tool_execution|llm_execution`。重跑:

```verify
cd /home/user/hermes-agent && grep -rln "register_middleware\|tool_execution\|llm_execution" website/docs/ ; echo "exit=$?"
```

实测 **0 个文件命中**。而 `website/docs/developer-guide/plugins/index.md` 是那份 1314 行的
"插件能做什么"权威指南,`website/docs/user-guide/features/hooks.md` 是钩子权威参考,
两者都只讲 observer 钩子。**插件最强的能力(改写发给模型的完整请求、包住并替换真实执行)
在面向插件作者的文档里一个字都没有。** 详见 §4。

**◇-2 · profile 分发的信任模型不含 `plugins/` / `hooks/` / `config.yaml`。**
锚点:`website/docs/user-guide/profile-distributions.md:624`(枚举为 "malicious SOUL, skills, or cron jobs")
vs §5.2 的 `USER_OWNED_EXCLUDE` 常量(`plugins`、`hooks`、`config.yaml` 均不在排除表)。
字面无假话,故不记 ▲;但它构建的心智模型漏掉了本簇最重的两条通道。详见 §5.4。

**◇-3 · 4 个 `VALID_HOOKS` 成员在英文文档中无参考条目。**
`api_request_error` 与 `on_skill_lifecycle` 在 `website/docs/` **零命中**;
`pre_api_request` / `post_api_request` 只出现在 `website/docs/user-guide/features/built-in-plugins.md`,
不在钩子参考里。四个在代码中都是活的
(`agent/conversation_loop.py:2291`、`agent/conversation_loop.py:5735`、
`run_agent.py:2855`、`tools/skill_usage.py:829`)。
**搜索面**:`website/docs/` 全树逐名搜。重跑:

```verify
cd /home/user/hermes-agent && for h in pre_api_request post_api_request api_request_error on_skill_lifecycle; do echo "$h -> $(grep -rl "$h" website/docs/ 2>/dev/null | wc -l) file(s)"; done
```

### ■(代码缺陷)—— 3 条

**■-1 · 模型提供方插件绕过 `plugins.enabled` / `plugins.disabled` / `HERMES_SAFE_MODE`。**
锚点:`providers/__init__.py:167-176`(无条件遍历 `$HERMES_HOME/plugins/model-providers/`)
+ `providers/__init__.py:139`(`exec_module`)+ 全文件零门禁(搜索面见 §2.4)。
放大器:`hermes_cli/plugins.py:1622-1649` 的 8 KB 子串启发式可能把同一个目录判成 `standalone`,
造成两个系统结论相反,而不设防的一方胜出。详见 §2.4。

**■-2 · MCP 目录安装的可疑命令闸门跑在任意 shell 之后。**
锚点:`hermes_cli/mcp_catalog.py:747-749`(`_do_git_install` → `_run_bootstrap`,`shell=True`)
先于 `hermes_cli/mcp_catalog.py:788`(`_save_mcp_server` 的 `validate_mcp_server_entry`)。
现象:一个 `transport.command` 会被判定为可疑而拒绝落盘的清单,其 `install.bootstrap` 已经执行完毕。详见 §6.3。

**■-3 · `_CREDENTIAL_FILENAMES` 是死常量,而 skill 目录拷贝正好缺这个 ignore。**
锚点:`hermes_cli/agent_import.py:82`(定义,全仓唯一出现)
+ `hermes_cli/agent_import.py:833`(`shutil.copytree(skill_dir, destination)`,无 `ignore=`)。
现象:`~/.claude/skills/<name>/credentials.json` 会被原样复制进 Hermes 的 skills 树。详见 §7.3。

### ◎(文档成立但显著保守)—— 1 条

**◎-1 · 插件指南的钩子表列 11 项,`VALID_HOOKS` 有 24 项。**
锚点:`website/docs/developer-guide/plugins/index.md:604-616`(表格 11 行)
vs `hermes_cli/plugins.py:135-218`(24 个成员)。
该表自称 "Here's the summary" 并指向完整参考,**字面为真**,故按记号规则记 ◎ 而非 ▲。
真正的完整参考 `hooks.md` 覆盖 20/24,缺的 4 个已单列为 ◇-3。

### 一条**存疑、不定案**的候选(留给评审位)

`website/docs/user-guide/features/hooks.md:386` 在 **"General rules for all hooks:"** 这个
明确以 "all hooks" 为范围的项目符号下写:

`website/docs/user-guide/features/hooks.md:386 @ 863e313`

> - Two hooks' return values affect behavior: [`pre_tool_call`](#pre_tool_call) can **block** the tool, and [`pre_llm_call`](#pre_llm_call) can **inject context** into the LLM call. All other hooks are fire-and-forget observers.

而**同一文件**往下 5 行的 "### Quick reference" 表里,至少 5 个钩子的 Returns 列不是 "ignored":
`pre_verify`(`{"action": "continue", "message": str}`)、`pre_gateway_dispatch`
(`{"action": "skip" | "rewrite" | "allow", ...}`)、`transform_tool_result` / `transform_terminal_output`
/ `transform_llm_output`(返回 `str` 替换内容)。代码侧同样支持(§2.10 档 2)。

**为什么不定案**:这句话的字面范围("all hooks")与它所在文档的自证材料直接冲突,
按理是干净的 ▲;但它也可能被读成"承前指上面代码示例里那 9 个钩子"。
按 CLAUDE.md 的规矩(判定必须确认归哪个标题管、整段一并判),我倾向判 ▲,
但**本轮不单方面定案**,列为 §10 移交项 T-1,由下一轮或评审位裁决。
如果定为 ▲,本簇 ▲ 计数变 4。

---

## 10. 移交项(每条带锚点文件 + 一句话现象)

| 编号 | 锚点 | 一句话现象 | 建议动作 |
|---|---|---|---|
| **T-1** | `website/docs/user-guide/features/hooks.md:386` | 项目符号自称 "General rules for **all** hooks",称只有 `pre_tool_call` / `pre_llm_call` 的返回值影响行为,但同文件 391-411 行的 Quick reference 表里 `pre_verify` / `pre_gateway_dispatch` / 三个 `transform_*` 的 Returns 列都不是 "ignored" | 裁决记 ▲ 还是"范围限定于上文示例";影响本簇 ▲ 计数 |
| **T-2** | `hermes_cli/lifecycle.py:40`(`finalize_session`)vs `cli.py:8131`、`tui_gateway/server.py:729`(均调 `_notify_session_boundary("on_session_finalize", ...)`) | `invoke_hook("on_session_finalize")` 不做 Relay 会话硬关闭,只有 `finalize_session()` 做;需确认这两个 `_notify_session_boundary` 内部落到哪个函数 | 若落到 `invoke_hook`,则存在静默的 Relay 会话泄漏(无报错) |
| **T-3** | `hermes_cli/skills_hub.py:1716`(`do_install(identifier, category=category, force=force, console=c)`) | 快照导入不传 `source_id`,而 `do_install` 自己 504-509 行的 docstring 专门警告"已知 provenance 的调用方应当传,否则同名技能可能被解析到另一个 registry" | 先确认快照 JSON 格式里是否存了 source 字段;存了却不传即为 ■ |
| **T-4** | `hermes_cli/skills_hub.py:1694`(`mgr = TapsManager()` 后循环 `mgr.add(repo, ...)`) | 快照导入**无确认地**把 JSON 里的任意 GitHub repo 加成技能源(tap),随后从中安装 | 评估是否应当对新增 tap 单独确认;需读 `tools/skills_hub.py::TapsManager`(非本簇) |
| **T-5** | `plugins/memory/__init__.py:181`(`provider = _load_provider_from_dir(child)` 在遍历中) | `discover_memory_providers` 为了调 `is_available()` 似乎会 import **每一个** memory provider 目录,而不只是 `memory.provider` 选中的那个;若属实则 §1 表 #6 的门禁比记录的更弱 | 需读该文件确认调用链与触发时机(非本簇) |
| **T-6** | `hermes_cli/mcp_catalog.py:141`(`get_optional_mcps_dir(...)`)+ `hermes_constants.py:223`(`HERMES_OPTIONAL_MCPS` 覆盖) | "Nous-approved"的信任根实际是"目录内容 + 该环境变量未被篡改";尚未核查有没有别的写入方会往 `optional-mcps/` 里加条目 | 搜索 `optional-mcps` 的全部写入点 |

---

## 11. 测试(作为行为规格)

全部通过。环境:`/home/user/hermes-venv`,**87 个包**(`[dev]` extra + `aiohttp 3.14.1` + `brotlicffi 1.2.0.1`),
以 root 运行、无 IPv6、离线(本轮所跑的 10 个文件均不受这三条已知环境限制影响)。

```console
=== Summary: 5 files, 161 tests passed, 0 failed (100% complete) in 3.6s (8 workers) ===
```

第一批(5 文件 / 161 用例):

| 文件 | 用例数 |
|---|---|
| `tests/hermes_cli/test_plugins.py` | 38 |
| `tests/hermes_cli/test_profile_distribution.py` | 52 |
| `tests/hermes_cli/test_agent_import.py` | 47 |
| `tests/hermes_cli/test_mcp_catalog.py` | 21 |
| `tests/hermes_cli/test_lifecycle.py` | 3 |

```console
=== Summary: 5 files, 45 tests passed, 0 failed (100% complete) in 2.3s (8 workers) ===
```

第二批(5 文件 / 45 用例):

| 文件 | 用例数 |
|---|---|
| `tests/hermes_cli/test_plugin_scanner_recursion.py` | 12 |
| `tests/hermes_cli/test_project_plugin_rce_bypass.py` | 23 |
| `tests/hermes_cli/test_plugin_runtime_disable_gate.py` | 5 |
| `tests/hermes_cli/test_startup_plugin_gating.py` | 2 |
| `tests/hermes_cli/test_skills_hub.py` | 3 |

**合计 10 文件 / 206 用例 / 0 失败。** 重跑命令:

```verify
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/hermes_cli/test_plugins.py tests/hermes_cli/test_lifecycle.py tests/hermes_cli/test_profile_distribution.py tests/hermes_cli/test_mcp_catalog.py tests/hermes_cli/test_agent_import.py
```

**基线洁净性**:两批测试跑完后 `git -C /home/user/hermes-agent status --porcelain` 输出为空。
`scripts/run_tests.sh` 会写 `test_durations.json`,但该文件被 `.gitignore:35` 忽略,不污染基线。

```verify
cd /home/user/hermes-agent && git status --porcelain && git check-ignore -v test_durations.json
```

**一条观察**:`tests/hermes_cli/test_lifecycle.py` 只有 3 个用例,而 `lifecycle.py` 是**全仓所有钩子的
唯一分发点**(§3 列出 20+ 个非测试调用点)。覆盖密度与结构重要性严重不匹配。
尤其是 T-2 那个 `finalize_session` vs `invoke_hook` 的分岔,没有任何测试钉住它。

---

## 12. 可迁移的设计原则(给"自己造一个同级 harness"用)

1. **"装"和"跑"必须是两个动作,而且中间那一步要写进配置、可审计。**
   Hermes 的 install → `plugins.enabled` → discovery 三段式是对的(§2.6)。
   反例在同一个仓库里:MCP 目录的 `install` 直接执行 shell(§6.2),两个 `install` 语义不一致。

2. **在 Python 里没有"只加载不执行"。** `exec_module` 即执行(§2.5)。
   任何"我先导进来看看它长什么样"的想法都是错的。要预检,只能 AST 静态解析或子进程沙箱。
   Hermes 的 8 KB 子串启发式(§2.4)正是"想在不执行的前提下知道它是什么"的产物,
   而它的不可靠正好制造了 ■-1。

3. **一个 env 开关的真值语义只能有一处定义。** GHSA-5qr3-c538-wm9j 的第一环
   就是同一个变量在两个模块里两种真值判定,导致"设成 0 反而打开"(§2.9)。

4. **拼路径之后必须重新验证结果仍在允许的根之下。** `Path('safe') / '/abs' == Path('/abs')`。
   `hermes_cli/profile_distribution.py:610` 做对了,`web_server` 曾经做错(§2.9 / §5.5)。

5. **观察者和改写者要在类型上分开。** Hermes 用 hook vs middleware 分开(§4.1),
   并把审批钩子明确定义为只读且在注释里说明"要否决请用 pre_tool_call"(§2.10)。
   **能力面的边界要写在能力旁边**,不要只写在设计文档里。

6. **"能改写"就必须"可追溯"。** 每次改写记一条 trace 条目并标 source(§4.2)。
   否则一次被中间件改过的调用事后无法解释。

7. **中间件不是安全边界。** 崩掉的中间件被静默跳过、链继续(§4.3)。
   要做安全,用 fail-closed 的那条路径(§2.11 的 `resolve_pre_tool_block`)。
   **把"这个扩展点崩了会怎样"写进契约文档**,否则用户会拿它当防线。

8. **策略判定返回结构化结果,呈现交给调用方。** `do_install` 把 `print` 和策略混在一起,
   于是 TUI 传一个静音 console 就同时静音了知情(§8.6)。

9. **一个 flag 只做一件事。** `--force` 同时管重装、无视扫描、跳过确认(§8.3)。

10. **"扫过了"要带版本和哈希,不能是布尔。** `scan_provenance` 的做法值得抄(§8.2)。

11. **黑名单式的"永不拷贝"清单会随着新目录的出现自然失效。**
    `USER_OWNED_EXCLUDE` 漏了 `plugins` / `hooks`(§5.2)。白名单更安全,
    但 Hermes 出于兼容既有分发选了黑名单,并在注释里写明了理由——
    **取舍要写下来,但写下来不等于风险消失。**

12. **读-改-写配置时,"文件不存在"与"文件读不出来"必须分开处理。**
    `agent_import.py` 的 `ConfigReadError`(§7.4)是本仓库里这个模式的正确样板。

13. **发现是廉价全量的,加载是昂贵受控的,两者的产物都要能内省。**
    未启用的插件仍进 `self._plugins` 并带 `error` 说明(§2.2);
    延迟加载的平台插件带 `deferred` 标记(§2.3)。

---

## 13. 本簇未覆盖 / 覆盖较浅的部分(诚实交代)

- `skills_hub.py` 2036 行中,`do_browse` / `do_list` / `do_audit` / `do_reset` / `do_diff` /
  `do_opt_in` / `do_opt_out` / `do_repair_official` / `do_publish` / `_github_publish` /
  `handle_skills_slash` / `_print_skills_help` 只做了结构级浏览,未逐行精读。
  本簇聚焦"外来代码怎么进来",所以重点给了 `do_install` / `do_snapshot_import` / `do_tap`。
- `plugins.py` 中 `register_auxiliary_task`(1069-1179)、`register_slack_action_handler`(1009-1068)
  只读了签名与 docstring,未追其消费端。
- `mcp_catalog.py` 的 `_apply_tool_selection` / `uninstall_entry` / 交互式 picker 未精读。
- `agent_import.py` 的记忆条目合并算法(`extract_markdown_entries` / `merge_entries`,
  168-331 行)未精读——它是文本处理,与本簇主题正交。
- 真正的技能抓取/扫描实现在 `tools/skills_hub.py` 与 `tools/skills_guard.py`,**不属本簇**,
  本底稿只在解释 `do_install` 语义时最小限度地引用了 `INSTALL_POLICY` 与 `should_allow_install`。
