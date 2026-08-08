# r8c-10 · H-17 定案 —— 无锁那半边的三条后果,全部实测复现

> 溯源约定:`路径:行号 @ 863e313` + 代码原文块,锚点置于块前。
> 实跑环境:venv `/home/user/hermes-venv`,**87 个包**(`pip list` 去表头计数,
> 与 `site-packages/*.dist-info` 计数一致),= `[dev]` extra + `aiohttp 3.14.1` + `brotlicffi 1.2.0.1`。
> 与 R8B 同环境。

## 0. 移交原文与本轮结论

R8A 移交、R8B 复核后改判、再移交本轮的 H-17,锚点是:

> `hermes_cli/env_loader.py:614-669`(无锁)vs `:184`(有 `_SECRET_SOURCE_CACHE_LOCK`)。
> 两条写同一批全局字典的路径只有一条加锁;子代理判为并发风险,**主线未复现**。
> 网关热重载线程与首轮路由线程并发时可能出现同一 home 双份 fetch,或缓存被空 dict 覆盖。
> **需要一个能触发热重载的实测场景才能定案。**

**本轮结论:H-17 成立,定案 ■-R8C-01。三条后果全部在 venv 里实跑复现。**
并且——**触发场景不是移交项猜的"网关热重载",而是 cron 并行池上的两个作业。**
热重载那条路(`gateway/run.py:1854`)在多档模式下**根本不走** `load_hermes_dotenv`,
移交项指的方向是错的;但结论本身比它猜的更重。

**后果比 R8B 收窄后的版本还要宽一层**:被撞的那个全局不是只喂 UI 标签的,
它喂的是**多档网关每一轮的权威凭据源**。

---

## 1. 两条路径,一把只有一边用的锁

锁本身在这里:

`hermes_cli/env_loader.py:52 @ 863e313`

```python
_SECRET_SOURCE_CACHE_LOCK = threading.RLock()
```

**加锁的那一半**——`hydrate_profile_secret_sources`,多档网关路由每轮入站走它:

`hermes_cli/env_loader.py:184 @ 863e313`

```python
    with _SECRET_SOURCE_CACHE_LOCK:
```

**不加锁的那一半**——`_apply_external_secret_sources`,`load_hermes_dotenv` 走它:

`hermes_cli/env_loader.py:512 @ 863e313`

```python
    _apply_external_secret_sources(home_path)
```

两半写的是同一批模块级全局:`_APPLIED_HOMES`、`_SECRET_SOURCES`、
`_SECRET_SOURCE_VALUES_BY_HOME`。**一把只有一边拿的锁,等于没有锁**——
这是本条定案最短的形式。

**第三个写者也不拿锁**,而且它是**清空**操作:

`hermes_cli/env_loader.py:251 @ 863e313`

```python
    _APPLIED_HOMES.clear()
```

---

## 2. 触发场景:cron 并行池,不是网关热重载

移交项猜的是"网关热重载线程"。**查下来那条路不成立**:多档模式下热重载显式短路,
`load_hermes_dotenv` 根本不执行(`gateway/run.py:1847-1853` 的 `is_multiplex_active()` 分支)。

真正的场景在 cron 调度器里。**每个 cron 作业运行前都清空并重建这三个全局**:

`cron/scheduler.py:3188 @ 863e313`

```python
        reset_secret_source_cache()
```

`cron/scheduler.py:3189 @ 863e313`

```python
        load_hermes_dotenv(hermes_home=_get_hermes_home())
```

而 cron 作业跑在**线程池**上:

`cron/scheduler.py:332 @ 863e313`

```python
_parallel_pool: Optional[concurrent.futures.ThreadPoolExecutor] = None
```

**作者自己知道这里是并发的。** 同一段注释里写着这个进程状态"shared with the worker's own
claim heartbeat …, the gateway's kanban watchers, and concurrent cron jobs on the parallel pool"
——它为 `TERMINAL_CWD` 那件事**特意换用了 ContextVar 来避开进程全局**,
**却在紧接着两行之后,对同样是进程全局的这三个字典做了无锁的 clear + 重建**。
同一段代码里,同一个危险被认出来一次、又漏掉一次。

### 2.1 并行是默认,串行才是 opt-in —— 这一条把严重性抬了一档

一个自然的怀疑是:"并行池的默认并发度会不会本来就是 1,于是这个场景需要用户特意去开?"
**恰恰相反。**

`cron/scheduler.py:4226 @ 863e313`

```python
        # Resolve max parallel workers: env var > config.yaml > unbounded.
```

`cron/scheduler.py:4228 @ 863e313`

```python
        _max_workers: Optional[int] = None
```

`_max_workers` 一路保持 `None` 就传给 `ThreadPoolExecutor(max_workers=None)`,
即 Python 自己的默认 `min(32, cpu_count + 4)`。紧跟的下一行注释把话说死了:

`cron/scheduler.py:4227 @ 863e313`

```python
        # Set HERMES_CRON_MAX_PARALLEL=1 to restore old serial behaviour.
```

**串行是需要显式设环境变量才能"恢复"的旧行为**,并行是现在的默认。

而哪些作业进并行池:

`cron/scheduler.py:4267 @ 863e313`

```python
        parallel_jobs = [j for j in due_jobs if not (j.get("workdir") or "").strip()]
```

**没配 workdir 的作业就是并行作业。** 所以触发条件是:
**两个没配 workdir 的 cron 作业在同一个 tick 上到期** —— 开箱即可,无需任何特殊配置。

---

## 3. 后果一:once-per-home 守卫在并发下完全失效

守卫是一个典型的 check-then-act,而且**中间隔着一次 vault 网络往返**:

`hermes_cli/env_loader.py:615 @ 863e313`

```python
    if home_key in _APPLIED_HOMES:
```

`hermes_cli/env_loader.py:653 @ 863e313`

```python
    _APPLIED_HOMES.add(home_key)
```

检查在 `:615`,置位在 `:653`,中间是 `apply_all(cfg, home_path)` 的真实拉取。
**四个线程同时进来,四个都看到"没标记过",四个都去拉。**

实跑(桩把 `apply_all` 换成记账 + `time.sleep(0.05)` 模拟 vault 往返):

```console
[自证] 桩有效:单次加载拉取 1 次,values = {'OPENAI_API_KEY': 'sk-from-vault'}
[场景1] 4 线程并发调 _apply_external_secret_sources(同一 home) → 实际拉取 4 次; 串行时守卫保证只拉 1 次
```

这个守卫存在的理由写在它自己的 docstring 里:`load_hermes_dotenv()` 每次 CLI 启动会被
3-5 个热模块在 import 期调到,不挡住就要打 3-5 遍状态行、拉 3-5 次密钥。
**并发下它一次也没挡住。**

---

## 4. 后果二:无锁那份无条件覆盖,加锁的孪生有守卫

这是 R8B 已经指出、本轮实测确认的那处不对称。

**加锁那份**,写回前有一道空判:

`hermes_cli/env_loader.py:236 @ 863e313`

```python
    if values:
```

**无锁那份**,同一个语义位置,**没有**:

`hermes_cli/env_loader.py:669 @ 863e313`

```python
        _SECRET_SOURCE_VALUES_BY_HOME[home_key] = values
```

于是:`report.provenance` 非空(所以进得了 `if report.applied_any:` 分支)、
但那些变量此刻不在 `os.environ` 里(多档 secret scope 下是常态,因为
`build_profile_secret_scope` 明确**不**把值写进进程全局环境),
`values` 就是空 dict,**并被无条件写回**,把上一次拉到的真实凭据快照抹掉。

```console
[场景2] 加载后 values = {'OPENAI_API_KEY': 'sk-from-vault'}
[场景2] 再走一次(provenance 有键、os.environ 无)→ values = {}  →  原值被空 dict 覆盖
```

**注意这一条本身不需要并发**,它是一处无条件覆盖。它的意义在于:
并发下的输家不只是"白拉一次",而是**能把赢家写好的快照清成空的**。

---

## 5. 后果三(最重):路由线程读到空凭据 —— 影响面比 R8B 收窄后的版本更宽

R8B 撤销了"后果比子代理报的窄"这个收窄。**撤销得对,而且还不够。**

被撞的 `_SECRET_SOURCE_VALUES_BY_HOME` 不是只喂 UI 标签的。**它只有一个消费者**,
就是多档网关每一轮的凭据作用域:

`agent/secret_scope.py:284 @ 863e313`

```python
        external_secrets = get_secret_source_values(home)
```

而这个函数的调用点,是每条入站消息进入档位作用域时:

`gateway/run.py:1965 @ 863e313`

```python
    hydrate_profile_secret_sources(Path(profile_home))
```

紧接着下一行就 `set_secret_scope(build_profile_secret_scope(Path(profile_home)))`,
把它的返回值装成**这一轮的权威凭据来源**——按 `gateway/run.py:1946-1949` 的说法,
装了它之后 `get_secret` "reads this profile's keys and never the process-global `os.environ`"。

**所以失效链是:**

```text
前提:多档网关 + 档位 P 的 API key 存在 Bitwarden/1Password,而不在 <home>/.env
 1. 稳态:_SECRET_SOURCE_VALUES_BY_HOME[P] = {"OPENAI_API_KEY": "sk-…"}
 2. cron 作业触发 → scheduler.py:3188 reset_secret_source_cache() 清空三个全局
 3. 同一作业 → :3189 load_hermes_dotenv → _apply_external_secret_sources
    → 去 vault 拉取(几十毫秒到几秒的网络往返),期间快照是空的
 4. 并发:档位 P 的一条入站消息进 gateway/run.py:1965 → 读快照 → 拿到 {}
 5. 该轮 build_profile_secret_scope 里没有那把 key
    → 这一轮以缺失/占位凭据跑 → 401 或"未配置 provider"
 6. 拉取返回、快照写回,下一轮又好了 —— 于是它表现为**偶发、不可复现的鉴权失败**
```

第 4 步实测:

```console
[场景3] 稳态 values = {'OPENAI_API_KEY': 'sk-from-vault'}
[场景3] 路由线程共读 150 次,其中读到**空凭据** 23 次  →  窗口存在(窗口 = reset 清空 到 vault 拉取返回后写回,长度就是一次 vault 往返)
```

**150 次读里 23 次读到空**,而桩里的"vault 往返"只有 50 毫秒。
真实的 Bitwarden CLI 往返远不止 50 毫秒,**窗口只会更宽**。

---

## 6. 为什么现有测试挡不住

`hermes_cli/env_loader.py` 的三个专门测试文件(`tests/test_env_loader_secret_sources.py`、
`tests/test_env_loader_applied_homes.py`、`tests/test_env_loader_op_bootstrap.py`)
本轮实跑 **27 个用例全部通过、0 失败**。它们**测的就是这个 once-per-home 守卫**,
而且测对了——**只是全部是单线程的**。

搜索面(负结论要写出来):在 `/home/user/hermes-agent/tests/` 下,
对 `test_env_loader_*.py` 与 `tests/secret_sources/*.py` 搜
`threading` / `ThreadPool` / `concurrent` 三个模式,**零命中**;
再对全 `tests/` 树搜 `_APPLIED_HOMES` 与 `_SECRET_SOURCE_VALUES_BY_HOME`,
命中的 `.py` 文件是 `tests/test_env_loader_secret_sources.py`、
`tests/agent/test_secret_scope.py`、`tests/test_env_loader_applied_homes.py`、
`tests/hermes_cli/test_xiaomi_provider.py` 四个,**逐个看过,没有一个起线程**。

**结论:这个缺陷不是"测试没覆盖到",而是"测试覆盖了单线程语义、
而危险只存在于多线程语义里"。** 一个把守卫测得很仔细的套件,
恰恰会让人相信这块已经稳了。

---

## 7. 定案 ■-R8C-01

**■-R8C-01**:`_apply_external_secret_sources`(`hermes_cli/env_loader.py:591`)与
`reset_secret_source_cache`(`:241`)在**不持** `_SECRET_SOURCE_CACHE_LOCK`(`:52`)的情况下
读写三个进程级全局,而孪生路径 `hydrate_profile_secret_sources`(`:184`)持锁。
cron 并行池(`cron/scheduler.py:332`)上的作业每次运行都执行
`reset_secret_source_cache()` + `load_hermes_dotenv()`(`:3188-3189`),
与多档网关的入站路由线程(`gateway/run.py:1965`)并发。
**三条后果全部实测复现**:守卫失效导致同一 home 重复拉取;`:669` 无条件写回
(孪生 `:236` 有 `if values:` 守卫)可把快照清空;路由线程在窗口内读到空凭据,
该轮以缺失凭据运行。**最小修法**:`_apply_external_secret_sources` 与
`reset_secret_source_cache` 一并纳入同一把 `RLock`,并把 `:669` 对齐成 `:236` 的 `if values:`。

**置信度**:高。三条后果各有一段可零成本重跑的实测;唯一没做的是在真实
Bitwarden/1Password 后端上跑(**无凭据,按项目边界不配置**),
桩替换的是 `agent.secret_sources.registry.apply_all`,即 `_apply_external_secret_sources`
的下游边界,**被测的锁与守卫逻辑本身是原样运行的**。

**复现脚本**:`/tmp` 下的临时脚本,未入库(它依赖 venv 与桩,不是产物)。
重建方法已在 §3-§5 逐段写明:桩掉 `env_loader._load_secrets_config` 与
`agent.secret_sources.registry.apply_all`,起 4 个线程调
`env_loader._apply_external_secret_sources(同一 home)`。
**注意 `ApplyReport` / `SourceReport` / `AppliedVar` / `FetchResult` 的字段必须给全**——
字段给不全会抛 `TypeError`,而它会被 `hermes_cli/env_loader.py:640` 的
`except Exception: return` **静默吞掉**,脚本于是打出一串看似成立、实则全假的结论。
本轮第一版复现就栽在这里,是靠脚本里那句自证断言(`assert base == {...}`)兜住的。

---

## 8. 本段未覆盖 / 存疑

| 项 | 锚点 | 一句话现象 |
|---|---|---|
| `_SECRET_SOURCES` 的并发后果未单独复现 | `hermes_cli/env_loader.py:667`(无锁写)vs `:235`(有锁写) | 本轮只复现了 `_APPLIED_HOMES` 与 `_SECRET_SOURCE_VALUES_BY_HOME` 两个全局;`_SECRET_SOURCES` 同样被两路无锁/有锁地写,它喂的是 UI 的 "(from Bitwarden)" 标签,后果应当更轻,但**未验证** |
| 真实后端未跑 | `agent/secret_sources/bitwarden.py:769`、`agent/secret_sources/onepassword.py:409` | 桩替换在 `apply_all` 这一层,真实后端的耗时与失败形态未观测;窗口宽度的真实值因此只有下界(50ms)没有实测值 |

*(原列在此处的「cron 并行池默认并发度未查」已在本轮查实,不再移交:默认无上限、
串行才是 opt-in、无 workdir 的作业即并行作业,见 §2.1。)*
