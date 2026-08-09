# r9a 底稿 · 结清 H-R8D-c / H-R8C-d —— `_SECRET_SOURCES` 的两条写路径与那把只有一边拿的锁

> 研究对象基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(只读)。
> 溯源约定:凡对代码行为的断言,**锚点单独成行、置于代码块之前**,格式 `路径:行号 @ 863e313`。
> 本文是底稿(证据层),求全求证、允许啰嗦。表格里的行号列不带 `路径:` 前缀,
> 是为了让引用校验器只对「锚点 + 紧跟的代码块」这一种形状计数;表格是索引,不是证据。
>
> **实跑环境**:venv `/home/user/hermes-venv`,**87 个包**
> (`pip list` 去表头计数 = 87,`site-packages/*.dist-info` 计数 = 87,两者一致),
> 即 `[dev]` extra + `aiohttp 3.14.1` + `brotlicffi 1.2.0.1`,与 R8B / R8C 同环境。
> 跑完实验后 `git -C /home/user/hermes-agent status --porcelain` 为空,基线未被污染。

---

## 0. 移交原文、锚点复核、本轮结论

### 0.1 移交原文

> **H-R8D-c**(移交 R9):锚点 `hermes_cli/env_loader.py:667` 无锁写 `_SECRET_SOURCES`,
> `:235` 有锁写。同一个全局变量有两条写路径、锁纪律不一致,后果**推定**轻于另外两个
> 已复现的同型问题,但**未验证**。

> **H-R8C-d**(R8D 裁定留 R9):理由是取证条件而非工作量 —— `env_loader.py` 当时不在 R8D 的
> 52 个文件里,且要验的「无锁写并发后果」与 R8C 已复现的两个全局同型,
> 判定「R9 有并发正题时一并做一次更完整的」。

R8C 原始移交表里对「更轻」给的理由是:

> `_SECRET_SOURCES` 同样被两路无锁/有锁地写,它喂的是 UI 的 "(from Bitwarden)" 标签,
> 后果应当更轻,但**未验证**。

### 0.2 锚点复核:R8D 给的两个行号**都差一行**

| R8D 移交写的 | 基线实际 | 那一行实际是什么 |
|---|---|---|
| `:667` 无锁写 | **666** | 667 是 `if name in os.environ:` |
| `:235` 有锁写 | **234** | 235 是 `values[name] = value` |

两处都是 +1 漂移,方向一致。**成因可查**:这两个行号写在 R8C 底稿 §8 的**移交表格**里,
表格行不带代码块,`scripts/verify_citations.py` 按「锚点 + 紧跟的块」配对,
表格里的行号从来不会被校验(这正是本文表格不写 `路径:` 前缀的原因)。
同一份 R8C 底稿里带代码块的锚点(`:669`、`:236`、`:615`、`:653`)本轮逐个复核,**全部正确**。
**结论:漂的不是作者的注意力,是那一类没有校验器覆盖的位置。**

### 0.3 本轮结论(先给)

**H-R8D-c:关闭,并加重。** 「后果更轻」这个推定的前提 —— 「它喂的是 UI 标签」—— **不成立**。
`_SECRET_SOURCES` 有三个消费者,其中一个是 **MCP stdio 子进程环境变量的准入白名单**
(`tools/mcp_tool.py` 的 `_build_safe_env`),即一道安全过滤器的判据,不是标签。
另一个把它写进 `auth.json` 的 `secret_source` 字段。定案两条:**■-R9A-01**(并发后果)、
**■-R9A-02**(结构性缺陷,不需要并发)。

**H-R8C-d:关闭。** 它要求的「R9 有并发正题时做一次更完整的」已在本文完成:
`env_loader.py` 的**全部** 5 个模块级可变全局的读写点已逐个枚举、锁纪律已判定、
后果已实测(三条复现 + 一条负结果)。

**一句话:**上一轮判「更轻」,是因为只读了 `_SECRET_SOURCES` 的**定义处注释**
(那段注释确实只讲 UI 标签),没有查它的**消费者**。定义处的注释是作者写它时的意图,
不是它现在的用途。

---

## 1. `env_loader.py` 的模块级可变全局:**全部** 5 个

搜索面(负结论必须写出搜索面):不靠肉眼扫,直接用 AST 枚举模块**顶层**的全部赋值语句
(`ast.Assign` + `ast.AnnAssign`,不进函数体、不进类体),全文 752 行共 **8 条**:

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python - <<'PY'
import ast
tree = ast.parse(open("hermes_cli/env_loader.py").read())
for n in tree.body:
    if isinstance(n, (ast.Assign, ast.AnnAssign)):
        t = n.targets[0] if isinstance(n, ast.Assign) else n.target
        print(f"{n.lineno:4d}  {getattr(t,'id','?')}")
PY
  20  _CREDENTIAL_SUFFIXES
  25  _WARNED_KEYS
  31  _WARNED_UTF32_PATHS
  39  _SECRET_SOURCES
  42  _SECRET_SOURCE_VALUES_BY_HOME
  51  _APPLIED_HOMES
  52  _SECRET_SOURCE_CACHE_LOCK
  76  _PROFILE_MANAGED_ENV_KEYS
```

其中 3 条是不可变对象(`_CREDENTIAL_SUFFIXES` 元组、`_PROFILE_MANAGED_ENV_KEYS` frozenset、
`_SECRET_SOURCE_CACHE_LOCK` 锁对象本身),**可变全局恰好 5 个**,如下。

| 全局 | 定义行 | 类型 | 写点 | 读点 | 拿锁? |
|---|---|---|---|---|---|
| `_WARNED_KEYS` | 25 | `set[str]` | 322 | 320 | 否 |
| `_WARNED_UTF32_PATHS` | 31 | `set[str]` | 393 | 392 | 否 |
| `_SECRET_SOURCES` | 39 | `dict[str,str]` | **234**(有锁)/ **666**(无锁)/ 252(clear,无锁) | 158 | 三选一 |
| `_SECRET_SOURCE_VALUES_BY_HOME` | 42 | `dict[str,dict]` | 237(有锁)/ 669(无锁)/ 253(clear,无锁) | 166 | 三选一 |
| `_APPLIED_HOMES` | 51 | `set[str]` | 228(有锁)/ 653(无锁)/ 251(clear,无锁) | 191 / 615 | 三选一 |

后三个是同一簇 —— 它们由同一组函数一起读写,共享同一把(只有一条路径会拿的)锁。

### 1.1 三个凭据相关全局的定义处

`hermes_cli/env_loader.py:33-42 @ 863e313`

```python
# Map of env-var name → source label ("bitwarden", etc.) for credentials
# that were injected by an external secret source during load_hermes_dotenv().
# Used by setup / `hermes model` flows to label detected credentials so
# users understand WHERE a key came from when their .env doesn't contain it
# directly (otherwise the "credentials detected ✓" line looks identical to
# the .env case and they don't know Bitwarden is wired up).
_SECRET_SOURCES: dict[str, str] = {}
# Applied values are immutable per-home snapshots.  ``os.environ`` is shared
# across profiles and may be overwritten by a later home's source apply.
_SECRET_SOURCE_VALUES_BY_HOME: dict[str, dict[str, str]] = {}
```

**这段注释本身是本文最重要的一条证据,记住第 40-41 行那两句。** 作者明确知道
`os.environ` 是跨档位共享的、会被后一个 home 的 apply 覆盖 —— 「不可变的按 home 快照」
这个设计**就是为了修这件事**。§5.2 会看到:这个快照**自己的构造过程**踩的正是这个坑。

另外注意:`_SECRET_SOURCES` **没有 home 维度**,而它的孪生 `_SECRET_SOURCE_VALUES_BY_HOME`
有。这个不对称是 §5.1 那条缺陷的全部成因。

`hermes_cli/env_loader.py:51-52 @ 863e313`

```python
_APPLIED_HOMES: set[str] = set()
_SECRET_SOURCE_CACHE_LOCK = threading.RLock()
```

**锁是 `threading.RLock`**(可重入锁,同一线程可重复获取而不自锁;跨线程仍互斥),
不是 `threading.Lock`。选 RLock 的合理动机是 `hydrate_profile_secret_sources` 可能被
同一线程嵌套调用;但基线里没有实际嵌套点,所以这个选择目前只是保险。

### 1.2 另外两个全局(告警去重),锁纪律相同、后果可忽略

`hermes_cli/env_loader.py:319-322 @ 863e313`

```python
        os.environ[key] = cleaned
        if key in _WARNED_KEYS:
            continue
        _WARNED_KEYS.add(key)
```

`hermes_cli/env_loader.py:391-393 @ 863e313`

```python
        path_key = str(path.resolve())
        if path_key not in _WARNED_UTF32_PATHS:
            _WARNED_UTF32_PATHS.add(path_key)
```

两处都是无锁的 check-then-act,并发下守卫失效的**唯一**后果是同一条告警多打一遍。
**这两个才是真正「后果可忽略」的同型**,把它们和 `_SECRET_SOURCES` 放在一张表里对比,
正好说明为什么「同型」不能推出「同后果」——**后果取决于消费者,不取决于写法**。

---

## 2. 锁纪律:一把锁、一个持有者、临界区跨了一次网络往返

### 2.1 唯一一处 `with` —— 而且它包住了 vault 网络调用

`hermes_cli/env_loader.py:184-185 @ 863e313`

```python
    with _SECRET_SOURCE_CACHE_LOCK:
        return _hydrate_profile_secret_sources(Path(hermes_home))
```

临界区 = `_hydrate_profile_secret_sources` 的**全部函数体**,其中包含真正去 vault 拉取的那一步:

`hermes_cli/env_loader.py:220-221 @ 863e313`

```python
        local_env["HERMES_HOME"] = str(home)
        report = apply_all(cfg, home, environ=local_env)
```

也就是说,**这把进程级锁被持有的时长 = 一次 vault 往返**。这个时长有上界但相当宽:

`agent/secret_sources/base.py:75 @ 863e313`

```python
DEFAULT_FETCH_TIMEOUT_SECONDS = 120.0
```

`agent/secret_sources/registry.py:224-228 @ 863e313`

```python
        future = executor.submit(_fetch)
        try:
            result = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
```

预算是**每个源** 120 秒、逐源串行。多档网关每条入站消息的第一跳都要过
`hydrate_profile_secret_sources`,所以**档位 X 的 vault 卡住,会把其他所有档位的首轮一起堵住**,
最坏 120s × 源数。◇(代码有、文档无):`docs/` 下没有任何地方说明这把锁跨网络 I/O。
这条本身不是 H-R8D-c 的正题,但它是「为什么 §5.2 的有锁那半边是免疫的」的机制解释
(见 §5.2:有锁路径把两个档位**串行化**了),一并记下。

### 2.2 有锁的那一半:写 `_SECRET_SOURCES`,值取自**私有** dict

`hermes_cli/env_loader.py:228-238 @ 863e313`

```python
    _APPLIED_HOMES.add(home_key)
    values: dict[str, str] = {}
    for name, applied in report.provenance.items():
        value = local_env.get(name)
        if value is None:
            continue
        _SECRET_SOURCES[name] = applied.source
        values[name] = value
    if values:
        _SECRET_SOURCE_VALUES_BY_HOME[home_key] = values
    return dict(values)
```

**`:234` 是有锁写点(R8D 记成了 235)。** 注意 `:231` 的取值来源是 `local_env` ——
一个**函数内构造的私有 dict**,不是 `os.environ`。

### 2.3 无锁的那一半:同样的循环,值取自**进程共享**的 `os.environ`

`hermes_cli/env_loader.py:664-669 @ 863e313`

```python
        values: dict[str, str] = {}
        for name, applied in report.provenance.items():
            _SECRET_SOURCES[name] = applied.source
            if name in os.environ:
                values[name] = os.environ[name]
        _SECRET_SOURCE_VALUES_BY_HOME[home_key] = values
```

**`:666` 是无锁写点(R8D 记成了 667)。** 与 §2.2 逐行对照,同一段语义有**三处**不同:

1. **不持锁**;
2. 取值来自 `os.environ`(跨档位共享)而不是 `local_env`(私有);
3. `:669` 无条件写回,而孪生 `:236-237` 有 `if values:` 守卫(此条 R8C 已定案,不重复)。

### 2.4 第三个写者:`clear()`,同样不持锁

`hermes_cli/env_loader.py:250-253 @ 863e313`

```python
    """
    _APPLIED_HOMES.clear()
    _SECRET_SOURCES.clear()
    _SECRET_SOURCE_VALUES_BY_HOME.clear()
```

### 2.5 once-per-home 守卫的两半(无锁那边)

`hermes_cli/env_loader.py:614-616 @ 863e313`

```python
    home_key = str(Path(home_path).resolve())
    if home_key in _APPLIED_HOMES:
        return
```

`hermes_cli/env_loader.py:653 @ 863e313`

```python
    _APPLIED_HOMES.add(home_key)
```

### 2.6 负结论:**没有第四条写路径**

搜索面:`grep -rn "_SECRET_SOURCES" .`(**不限后缀**、排除 `.git/`)全仓命中 15 行,
按文件归并后是 `hermes_cli/env_loader.py`(7 行:定义 1、读 1、写 2、clear 1、docstring 提及 2)、
`tests/test_env_loader_secret_sources.py`、`tests/test_command_secret_source.py`、
`tests/tools/test_mcp_tool.py`(三者全部是测试对全局的直接置位/清空)。
另检了间接改写途径:`grep -rn "setattr(env_loader\|env_loader\.__dict__\|globals()\["`
在非测试代码里对 `env_loader` **零命中**。
**故:生产代码里写 `_SECRET_SOURCES` 的位置恰好 3 处(`:234`、`:666`、`:252`),读 1 处(`:158`)。**

---

## 3. 推翻「它只喂 UI 标签」:三个消费者,其中一个是安全过滤器

`_SECRET_SOURCES` 对外只经由 `:158` 这一个读点暴露:

`hermes_cli/env_loader.py:148-158 @ 863e313`

```python
def get_secret_source(env_var: str) -> str | None:
    """Return the label of the secret source that supplied ``env_var``, if any.

    Returns ``"bitwarden"`` for keys pulled from Bitwarden Secrets Manager
    during the current process's ``load_hermes_dotenv()`` call.  Returns
    ``None`` for keys that came from ``.env``, the shell environment, or
    aren't tracked.  The returned label is metadata only: credential-pool
    persistence may store it to explain the origin of a borrowed secret, but
    must never treat it as authorization to persist the raw value.
    """
    return _SECRET_SOURCES.get(env_var)
```

docstring 说「The returned label is metadata only」。**代码不是这么用的。** 三个消费者:

### 3.1 消费者甲(最重):MCP stdio 子进程的环境变量准入白名单

`tools/mcp_tool.py:460-473 @ 863e313`

```python
    """
    try:
        from hermes_cli.env_loader import get_secret_source
    except Exception:  # pragma: no cover — early bootstrap/import fallback
        get_secret_source = None
    env = {}
    for key, value in os.environ.items():
        if (
            key in _SAFE_ENV_KEYS
            or key.upper() in _SAFE_ENV_KEYS_CASE_INSENSITIVE
            or key.startswith("XDG_")
            or (get_secret_source is not None and get_secret_source(key))
        ):
            env[key] = value
```

`get_secret_source(key)` 是这个 `or` 链的**第四个分支**:它为真,该环境变量就被放进
交给 MCP 服务器子进程的 env。这不是标签,这是**准入判据**。而且这道过滤器的存在理由
写在它自己 docstring 里:「This prevents accidentally leaking secrets like API keys,
tokens, or credentials to MCP server subprocesses.」

调用点(启动 stdio 传输、拼子进程 env 的那一步):

`tools/mcp_tool.py:2395-2396 @ 863e313`

```python
        safe_env = _build_safe_env(user_env)
        command, safe_env = _resolve_stdio_command(command, safe_env)
```

**它不是只在启动时跑一次** —— `_run_stdio` 挂在一个重连监督循环下,MCP 服务器每崩一次、
每被显式要求重连一次,就重新走一遍 `_build_safe_env`:

`tools/mcp_tool.py:3135-3141 @ 863e313`

```python
        while True:
            try:
                if self._is_http():
                    lifecycle_reason = await self._run_http(config)
                else:
                    lifecycle_reason = await self._run_stdio(config)
                # Transport returned cleanly. Two cases:
```

这一条决定了 §5.3 的窗口是「进程生命期内反复暴露」而不是「只在启动那一瞬」。

而且仓库里**有一个专门测试**把这个语义钉死了 —— 它证明这不是我的解读:

`tests/tools/test_mcp_tool.py:1101-1119 @ 863e313`

```python
    def test_secret_source_injected_vars_are_passed(self, monkeypatch):
        """Vars tagged by an external secret source (Bitwarden/1Password) are
        deliberately allowed for MCP stdio servers."""
        from hermes_cli import env_loader
        from tools.mcp_tool import _build_safe_env

        monkeypatch.setitem(env_loader._SECRET_SOURCES, "ALPACA_API_KEY", "bitwarden")
        monkeypatch.setitem(env_loader._SECRET_SOURCES, "NOTION_TOKEN", "onepassword")
        fake_env = {
            "PATH": "/usr/bin",
            "ALPACA_API_KEY": "from-bws-key",
            "NOTION_TOKEN": "from-op",
            "UNTRACKED_SECRET_KEY": "still-filtered",
        }
        with patch.dict("os.environ", fake_env, clear=True):
            result = _build_safe_env(None)

        assert result["PATH"] == "/usr/bin"
        assert result["ALPACA_API_KEY"] == "from-bws-key"
```

测试直接往 `env_loader._SECRET_SOURCES` 里塞两条,然后断言这两个变量**进了**子进程 env、
未被塞的 `UNTRACKED_SECRET_KEY` **没进**。**这个全局的取值就是这道过滤器的开关。**

### 3.2 消费者乙:写进 `auth.json` 的 `secret_source` 字段

`agent/credential_pool.py:2883-2889 @ 863e313`

```python
    def _secret_source_for_env(env_var: str) -> Optional[str]:
        try:
            from hermes_cli.env_loader import get_secret_source
            source_label = get_secret_source(env_var)
        except Exception:
            source_label = None
        return str(source_label).strip() if source_label else None
```

`agent/credential_pool.py:2906-2908 @ 863e313`

```python
        secret_source = _secret_source_for_env(env_var)
        if secret_source:
            payload["secret_source"] = secret_source
```

这个 `secret_source` 落到凭据池条目里,并被 `agent/credential_persistence.py` 列为
可以写进 `auth.json` 的「安全元数据」之一。它是**落盘的溯源记录**,不是屏幕上的一行字。

### 3.3 消费者丙:UI 标签(这才是 R8C 推定里说的那个)

`hermes_cli/main.py:4386`、`hermes_cli/web_server.py:9603`、
`hermes_cli/model_setup_flows.py:1795 / 2249 / 3059`,五处全部经由
`format_secret_source_suffix` 打印 `" (from Bitwarden)"`。**这一类确实后果轻。**
R8C 的推定错在:它只看了这一类。

---

## 4. 触发场景:cron 线程、MCP 事件循环线程、路由线程,同一个网关进程

R8C 已定案 cron 是触发方。本文只补两条本轮新查的、H-R8D-c 独有的证据。

cron 每个作业运行前 clear + 重建三个全局(R8C 已定案,此处复核锚点有效):

`cron/scheduler.py:3186-3189 @ 863e313`

```python
            reset_secret_source_cache,
        )
        reset_secret_source_cache()
        load_hermes_dotenv(hermes_home=_get_hermes_home())
```

cron 调度器**跑在网关进程内的后台线程**里:

`gateway/run.py:26914-26921 @ 863e313`

```python
    cron_thread = threading.Thread(
        target=cron_provider.start,
        args=(cron_stop,),
        kwargs=cron_start_kwargs,
        daemon=True,
        name="cron-scheduler",
    )
    cron_thread.start()
```

MCP 也跑在**同一进程的另一个专属线程**上(自带事件循环):

`tools/mcp_tool.py:4392-4396 @ 863e313`

```python
        _mcp_thread = threading.Thread(
            target=_mcp_loop.run_forever,
            name="mcp-event-loop",
            daemon=True,
        )
```

多档路由每条入站消息走的那一跳(R8C 已定案,复核有效):

`gateway/run.py:1965 @ 863e313`

```python
    hydrate_profile_secret_sources(Path(profile_home))
```

**三个线程,一个进程,一份 `_SECRET_SOURCES`,一把只有 `hydrate_*` 会拿的锁。**

---

## 5. 实测

复现脚本在 `/tmp` 下(未入库:它依赖 venv 与桩,不是产物)。桩只替换两个**下游边界** ——
`env_loader._load_secrets_config` 与 `agent.secret_sources.registry.apply_all` ——
被测的锁、守卫、`os.environ` 读取逻辑**原样运行**。
每次跑都先跑一段自证,防 R8C §7 记过的那个陷阱(`ApplyReport` 字段给不全 → `TypeError`
→ 被 `:639` 的 `except Exception: return` 静默吞掉 → 脚本打出一串看似成立、实则全假的结论)。

跑法:

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python \
    /tmp/.../r9a_exp.py 2>/dev/null
```

(`2>/dev/null` 只滤掉被测代码自己往 stderr 打的 `Bitwarden: applied N secrets` 状态行。)

自证:

```verify
[自证] 桩生效:get_secret_source -> 'bitwarden';快照 -> {'SELFTEST_API_KEY': 'vault-value'}
```

### 5.1 场景 1 —— 跨档位打标放宽 MCP 白名单(**不需要并发,确定性复现**)

因为 `_SECRET_SOURCES` **没有 home 维度**,任何一个档位从 vault 拉到 `NOTION_TOKEN`,
就等于在**整个进程**范围内把「`NOTION_TOKEN` 允许进 MCP 子进程」这个开关打开了 ——
包括那些从没配过任何 secret source、`NOTION_TOKEN` 只是用户 shell 里 `export` 出来的档位。

```verify
[场景1] 只 hydrate 了 homeB;_SECRET_SOURCES = {'NOTION_TOKEN': 'bitwarden'}(没有 home 维度)
[场景1] MCP stdio 子进程 env = {'PATH': '/usr/bin', 'NOTION_TOKEN': 'shell-exported-token'}
[场景1] NOTION_TOKEN 进了子进程:True;同样是 shell 导出的 OTHER_API_KEY 仍被过滤:True
```

**读法**:两个变量在 `os.environ` 里的身份完全一样(都是 shell 导出、都不是 vault 注入),
唯一区别是 `NOTION_TOKEN` 这个**名字**碰巧被另一个档位的 vault 用过。
于是它被交给了第三方 MCP 服务器子进程,而 `OTHER_API_KEY` 没有。
**判据(输入→现象)**:多档网关,档位 B 的 `config.yaml` 配了 Bitwarden 且映射了
`NOTION_TOKEN`;用户在启动 shell 里 `export NOTION_TOKEN=<自己的私人 token>`;
档位 B 收到任意一条消息后,**任何**档位下启动的任何 stdio MCP 服务器的子进程环境里
都会出现这个私人 token。→ **■-R9A-02**。

### 5.2 场景 2 —— 双档位并发 apply:无锁路径的「不可变快照」捞到**别人档位**的值

按 §1.1 的注释,`_SECRET_SOURCE_VALUES_BY_HOME` 存在的**全部理由**就是
「`os.environ` 跨档位共享、会被后一个 home 的 apply 覆盖」。
而 `:667-668` 正是从 `os.environ` 逐键读出来构造这份快照的 —— **不持锁**。
两个档位的 vault 往返一旦重叠,后写 `os.environ` 的那个档位的值,
会被先返回的那个档位当成自己的快照存下去。

桩里两个档位的 vault 往返耗时不同(A 100ms / B 20ms,B 晚 30ms 起跑),
这是在模拟「两个档位配不同后端、快慢不同」这个再正常不过的情况;
**sleep 只在桩里,被测函数一行没动**。

```verify
[场景2/无锁 _apply_external_secret_sources] homeA 快照 = {'EXPB1_API_KEY': 'B-value', 'EXPB2_API_KEY': 'B-value', 'EXPB3_API_KEY': 'B-value'}
[场景2/无锁 _apply_external_secret_sources] homeA 快照被 homeB 的值污染:True
```

**homeA 的按 home 快照里,3 个键全部是 homeB 的值。** 这份快照的唯一消费者是
`agent/secret_scope.py` 的 `build_profile_secret_scope`(R8C §5 已定案),
即多档网关**每一轮的权威凭据来源**。也就是说:档位 A 的这一轮,拿着档位 B 的密钥去请求。

同一套时序,换成**有锁**的孪生函数,污染消失:

```verify
[场景2/有锁 hydrate_profile_secret_sources] homeA 快照 = {'EXPB1_API_KEY': 'A-value', 'EXPB2_API_KEY': 'A-value', 'EXPB3_API_KEY': 'A-value'}
[场景2/有锁 hydrate_profile_secret_sources] homeA 快照被 homeB 的值污染:False
```

**有锁那半边免疫有两个独立原因,缺一条也够**:(a) 锁把两个档位**串行化**了
(§2.1:临界区包住了 `apply_all`);(b) 它读的是私有的 `local_env`(§2.2 的 `:231`),
根本不碰 `os.environ`。**无锁那半边两条都没有。**
→ 这是 **■-R9A-01** 的第一条后果。

### 5.3 场景 3 —— cron 的 reset 窗口内,MCP 重连整批丢掉 vault 凭据

`reset_secret_source_cache()` 在 `:252` 清空 `_SECRET_SOURCES`,然后 `load_hermes_dotenv`
要花一次 vault 往返才把它填回来。**这段时间里 `get_secret_source()` 对所有键返回 `None`**,
于是 §3.1 那道过滤器认为「没有任何变量是 vault 注入的」,把它们全部挡在 MCP 子进程之外 ——
尽管这些凭据此刻**就在 `os.environ` 里**(reset 只清 provenance,不清环境变量)。

```verify
[场景3] 稳态自证:safe_env 含 ['EXPW1_API_KEY', 'EXPW2_API_KEY']
[场景3] 单次 cron 作业(vault 往返桩 50 ms):探针取 114 次 safe_env,vault 凭据缺席 39 次,缺席窗口宽度 49.3 ms
```

**窗口宽度 49.3 ms ≈ 桩里那次 vault 往返的 50 ms** —— 三次重跑分别是 49.3 / 48.8 / 49.3 ms,
探针次数与缺席次数因调度略有浮动(114~121 / 39~40),**窗口宽度稳定等于一次 vault 往返**。
真实 Bitwarden CLI / 1Password CLI 往返远不止 50 ms(§2.1 的预算上限是每源 120 秒),
**窗口只会更宽**。

**判据(输入→现象)**:多档网关 + 任一 cron 作业 + 一个把 API key 放在 vault 里的
stdio MCP 服务器。cron 作业启动的那一瞬间,若该 MCP 服务器恰好重连
(§3.1 的 `:3135` 监督循环:进程崩溃、OAuth 恢复、显式 reconnect 都会触发),
它拿到的子进程环境里**没有那把 key**,表现为 MCP 服务器起来了但一直 401 /
「未配置凭据」,而下一次重连又好了 —— **偶发、不可复现的 MCP 鉴权失败**。
这与 R8C 定案的「偶发鉴权失败」是同一个窗口的**另一个受害者**。
→ 这是 **■-R9A-01** 的第二条后果。

### 5.4 场景 4 —— 负结果:`clear()` 落进写循环内部,默认调度下**没跑出来**

理论上还有一种更糟的终态:`reset` 的三条 `clear()` 之间被抢占,
使得 `_APPLIED_HOMES` 留下了 home 标记(→ 守卫认为「已应用,别再拉了」)
而 `_SECRET_SOURCES` 被清空 —— 这会是**粘滞**的,进程生命期内不自愈。
我按最有利于复现的方式试了(3000 个 provenance 键把写循环拉长,两线程用 Barrier 对齐起跑):

```verify
[场景4] 300 轮 x 3000 键(reset ‖ apply,默认 GIL 切换间隔 0.005s):provenance 残缺 0 轮,粘滞 0 轮,最少剩 3000/3000
```

**900,000 次写入、300 轮对撞,0 命中。** 原因清楚:CPython 的 `dict.__setitem__` /
`dict.clear()` 在字符串键下是原子的,而 `reset` 的三条 `clear()` 是相邻语句,
默认 5 ms 的 GIL 切换间隔下极难恰好插在它们中间。
**所以这条不写进定案**,只作为已探明的边界记下:
**H-R8D-c 的真实后果是 §5.2 与 §5.3 两条(都不依赖字节码级交错),不是「字典被撕裂」。**
这也修正了「无锁写」这个说法容易引起的直觉 —— 危险不在单次写,在**写与写之间的那段时间**。

---

## 6. 与 R8C 已复现的两个同型问题的对比

| | R8C ■-R8C-01(`_APPLIED_HOMES`) | R8C ■-R8C-01(`_SECRET_SOURCE_VALUES_BY_HOME`) | **本轮(`_SECRET_SOURCES`)** |
|---|---|---|---|
| 同型在哪 | 同一把 `RLock`,同一对有锁/无锁孪生函数,同一个 `reset` 清空者 | 同上 | 同上 |
| 危险的形状 | check-then-act 守卫跨一次 vault 往返 | 无条件写回(`:669` 缺 `:236` 的 `if values:`)+ reset 窗口 | (a) 无 home 维度;(b) 从共享 `os.environ` 取值;(c) reset 窗口 |
| 消费者 | 只有它自己(守卫) | `build_profile_secret_scope` → 每轮权威凭据 | **MCP 子进程 env 白名单** + `auth.json` 的 `secret_source` + UI 标签 |
| 后果 | 重复拉取、重复打状态行 | 该轮以缺失凭据运行 → 偶发 401 | 私人凭据泄进第三方 MCP 子进程(§5.1);档位 A 用档位 B 的密钥(§5.2);MCP 偶发丢凭据(§5.3) |
| 需要并发吗 | 是 | 是 | §5.1 **否**;§5.2 / §5.3 是 |
| 相对轻重 | 最轻(只浪费) | 重(功能失效) | **不轻于它** —— §5.2 与它是同一条链上的同一次失效,§5.1 还多一个泄露方向 |

**结论**:R8C 推定的「更轻」不成立。准确的说法是:
- **失效方向多一个**。另两个全局只会「少给凭据」(功能失效);`_SECRET_SOURCES` 因为是
  一道**过滤器的判据**,既能「少给」(§5.3 → MCP 起不来),也能「多给」
  (§5.1 → 不该看见的进程看见了凭据)。**多给的那一半是另两个全局没有的。**
- **有一条根本不需要并发**(§5.1)。它是纯结构缺陷:一个有 home 维度的孪生,
  一个没有 home 维度的自己。锁修不了它 —— §5.2 的有锁版跑出来
  `_SECRET_SOURCES` 里 A 的标签**照样**被 B 覆盖成了 `onepassword`。
  **这条必须和锁分开修,否则加了锁会给人「已经修好了」的错觉。**

---

## 7. 为什么现有测试挡不住

本轮实跑 4 个相关测试文件:

```verify
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/test_env_loader_secret_sources.py \
  tests/test_env_loader_applied_homes.py tests/test_command_secret_source.py \
  tests/tools/test_mcp_tool.py
=== Summary: 4 files, 124 tests passed, 0 failed (100% complete) in 3.1s (8 workers) ===
```

**124 个用例全过、0 失败**(venv 87 包)。其中 `tests/tools/test_mcp_tool.py` 里那个
`test_secret_source_injected_vars_are_passed`(§3.1 引用)**测的正是这个白名单语义,
而且测对了** —— 它只是:

1. **单线程**(与 R8C §6 的结论一致,不重复搜索面);
2. **单 home** —— 它 `monkeypatch.setitem` 直接往全局里塞两条,从来没有出现过
   「两个档位」这个概念,所以 §5.1 那条**结构性**缺陷根本不在这套测试的语义空间里。

第 2 点是本轮新增的:R8C 说的是「测试覆盖了单线程语义、危险只存在于多线程语义里」;
到了 `_SECRET_SOURCES` 这里还要再加一句 —— **危险还存在于「多档位」语义里,
而那和线程无关**。一个把白名单钉得很死的测试,恰恰会让人相信这块已经稳了。

---

## 8. 定案

### ■-R9A-01(并发;H-R8D-c 的正题)

`_apply_external_secret_sources`(`hermes_cli/env_loader.py` 第 591 行起)在**不持**
`_SECRET_SOURCE_CACHE_LOCK`(第 52 行)的情况下,于第 666 行写 `_SECRET_SOURCES`、
第 667-668 行从**进程共享的** `os.environ` 逐键读值构造按 home 快照;
而其有锁孪生 `_hydrate_profile_secret_sources` 在第 234 行写同一个全局、
第 231 行从**私有** `local_env` 取值。第三个写者 `reset_secret_source_cache`
(第 252 行)也不持锁。**两条后果实测复现**:

- 双档位并发 apply 时,无锁路径的按 home 快照整批捞到另一档位的值(§5.2),
  而这份快照恰恰是为「`os.environ` 跨档位共享」这件事而设计的(第 40-41 行注释);
  有锁孪生在同一时序下免疫。
- cron 的 `reset` 到 vault 返回之间,`get_secret_source()` 对所有键返回 `None`,
  `_build_safe_env` 因此把全部 vault 凭据挡在 MCP stdio 子进程之外(§5.3),
  窗口宽度实测 ≈ 一次 vault 往返(桩 50 ms → 实测 49.3 ms;真实后端更宽,预算上限每源 120 s)。

**已探明的边界(负结果)**:`clear()` 落进写循环内部的字节码级交错,
默认调度下 300 轮 × 3000 键 **0 命中**(§5.4)。危险在写与写之间的时间窗,不在单次写。

**最小修法**:把 `_apply_external_secret_sources` 与 `reset_secret_source_cache`
一并纳入同一把 `_SECRET_SOURCE_CACHE_LOCK`(与 R8C ■-R8C-01 的修法合并,是同一处修改);
并把第 667-668 行的取值来源从 `os.environ` 换成 `apply_all` 返回的 `report` 自身携带的值,
与有锁孪生的 `local_env` 语义对齐。

### ■-R9A-02(结构性,**不需要并发**;本轮新发现,不在任何移交项里)

`_SECRET_SOURCES`(第 39 行)**没有 home 维度**,而它的孪生
`_SECRET_SOURCE_VALUES_BY_HOME`(第 42 行)有。`get_secret_source()`(第 158 行)
是 `tools/mcp_tool.py` 中 `_build_safe_env`(第 460-473 行)的准入判据,
判据语义因此是「这个变量名被**任何**档位标记过」而不是「被**当前**档位标记过」。

**判据(输入→现象)**:多档网关;档位 B 配了 Bitwarden 并映射 `NOTION_TOKEN`;
用户在启动 shell 里 `export NOTION_TOKEN=<私人 token>`(该变量名在档位 A 从未来自 vault)。
档位 B 收到任意一条消息后,**任何**档位下启动的任何 stdio MCP 服务器,
其子进程环境里都会出现这个私人 token —— 而 `_build_safe_env` 的全部存在理由
就是不让这种事发生。§5.1 确定性复现,**加锁修不了**。

**最小修法**:把 `_SECRET_SOURCES` 改成 `dict[home_key, dict[name, label]]`
(与 `_SECRET_SOURCE_VALUES_BY_HOME` 同构),`get_secret_source` 增加 home 形参,
`_build_safe_env` 传入当前档位的 home。**代价**:`get_secret_source` 的 3 类调用方
(§3.1/3.2/3.3)都要拿到当前 home;§3.3 的 UI 调用方在 CLI 语境下就是进程 home,
成本不高。若不改结构,退而求其次是在 `_build_safe_env` 里
用 `get_secret_source_values(当前 home)` 的**键集**替代 `get_secret_source(key)` 做判据 ——
那个全局本来就是按 home 分的。

### 移交项结清

| 移交项 | 处置 | 依据 |
|---|---|---|
| **H-R8D-c** | **关闭并加重** | 锚点更正为 666 / 234(§0.2);「后果更轻」的前提被推翻(§3);后果实测两条(§5.2/§5.3)+ 一条负结果(§5.4);定案 ■-R9A-01 |
| **H-R8C-d** | **关闭** | 它要求的「更完整的一次」= `env_loader.py` 全部 5 个可变全局的读写点枚举(§1)+ 锁纪律判定(§2)+ 后果实测(§5),本文全部完成 |

---

## 9. 本段未覆盖 / 存疑(移交格式:锚点文件 + 一句话现象)

| 项 | 锚点 | 一句话现象 |
|---|---|---|
| 锁跨网络 I/O 的排队后果未实测 | `hermes_cli/env_loader.py` 第 184-185 行 + `agent/secret_sources/base.py` 第 75 行 | `hydrate_profile_secret_sources` 持进程级 `RLock` 跨越 `apply_all` 的 vault 往返,预算上界每源 120 s;多档网关下一个档位的 vault 卡住会把其他档位的首轮一并堵住,**本轮只做了机制判定,没有实测排队时延** |
| `■-R9A-02` 的真实后端未跑 | `agent/secret_sources/bitwarden.py` 第 769 行、`agent/secret_sources/onepassword.py` 第 409 行 | 与 R8C 同 —— 桩替换在 `apply_all` 边界,真实 vault 的耗时与失败形态未观测;§5.3 的窗口宽度因此只有下界(≈50 ms)没有真实值 |
| `auth.json` 里 `secret_source` 缺失/错值的下游后果未查 | `agent/credential_pool.py` 第 2906-2908 行、`agent/credential_persistence.py` 第 28-30 行 | reset 窗口内 seed 出来的凭据条目会缺 `secret_source` 字段,或(跨档位时)带上**别的档位**的来源标签;该字段落盘后被谁读、缺了会怎样,**本轮未追** |
| `_SECRET_SOURCES` 的 TS/前端侧是否有镜像 | —— | 全仓不限后缀搜 `_SECRET_SOURCES` 只命中 `.py`(§2.6),但**没有搜过语义等价的前端概念**(如 web UI 是否另有一份 secret-source 标签缓存),该负结论的搜索面仅覆盖同名符号 |
