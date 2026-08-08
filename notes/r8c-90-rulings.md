# r8c-90 · R8C 定案卷 —— 移交项结清、主线复核、跨段仲裁

> 溯源约定:`路径:行号 @ 863e313` + 代码原文块,锚点置于块前。
> 本卷只放**定案**与**主线复核结论**;取证过程在各底稿 `notes/r8c-raw-*.md` 与
> `notes/r8c-1x-*.md` 里。
> **主线复核的口径**:凡子代理给出的 ■ 级断言,主线**独立重跑或重读**;
> 复核结论与子代理不一致时,以本卷为准并写明分歧点。

---

## 1. 移交项结清总表

| 移交项 | 来源轮 | 锚点 | 本轮结论 | 证据在哪 |
|---|---|---|---|---|
| **H-3** | R8A | `hermes_cli/web_server.py:12321`(`approve_pairing`;R8A 原写 `:12320`,那是空行,本轮更正) | **结清,负结论**:四种绑定形态 + 畸形 host 值,**没有任何组合**能让未认证请求打到该路由。全部保护来自中间件链,路由本体零鉴权 | `notes/r8c-raw-boot-authchain.md` §2 |
| **H-10** | R8A | `hermes_cli/web_server.py:6921` 一带(`PUT /api/config` 写入路径) | **结清,定 ■-R8C-05**:挡不住,**能走到**。主线独立复现 | 本卷 §2 |
| **H-11** | R8A | `hermes_cli/web_server.py:12296` vs `:6914` | **结清**:不是两套,是**并存多套**;A/B 两套并存**是有意设计**(分界线=handler 会不会 `await`),真正的问题是"选哪套"没有单一入口 | `notes/r8c-raw-config-endpoints.md` |
| **H-13 / H-R8B-c** | R8A→R8B | 平台就绪判定 8 份实现 | 见 `notes/r8c-raw-platform-readiness.md` | 同左 |
| **H-17** | R8A→R8B | `hermes_cli/env_loader.py:614-669`(无锁)vs `:184`(有锁) | **结清,定 ■-R8C-01**:成立,三条后果全部实测复现;**触发场景不是移交项猜的网关热重载,是 cron 并行池** | `notes/r8c-10-h17-env-loader-race.md` |
| **H-R8FIX-a** | R8-fix | `hermes_cli/config.py:3065` + `hermes_cli/auth.py:7329` | **结清(设计判断)**:补解析检查**不**破坏全新安装/空文件;但只查"抛不抛"**不够** | `notes/r8c-11-hr8fixa-guard-parse-check.md` |

---

## 2. ■-R8C-05(H-10 结清)—— 主线独立复现

**子代理判 ■ 并做了复现;主线不采信转述,自己重跑了一遍。** 结论一致,且主线补上了
子代理**自己申报没跑**的那一跳(config→env 桥接),改为**读码逐字确认**。

### 2.1 主线实跑

设 `HERMES_HOME` 到一个临时目录,起真实的 `hermes_cli.web_server.app`,带会话令牌:

```console
== 1. PUT /api/config 写 API-key 形状的键 ==
   状态 200
   config.yaml 里有该键: True  明文值在里面: True
   .env 被创建: False

== 2. 对照:PUT /api/env 走正确请求体(key/value)==
   PUT /api/env OPENAI_API_KEY   -> 200 {"ok":true,"key":"OPENAI_API_KEY","config_updates":[]}
   PUT /api/env LD_PRELOAD       -> 400 {"detail":"Environment variable 'LD_PRELOAD' is on the writer denylist. Names th

== 3. 对照:PUT /api/config 写 LD_PRELOAD ==
   状态 200   config.yaml 里有 LD_PRELOAD: True
```

**第 2 段与第 3 段并排读,就是这条定案的全部**:同一个进程、同一把令牌、同一个变量名,
`/api/env` 拿名单挡下(400),`/api/config` 一声不吭收下(200)。

> **主线自查记一笔**:第一次跑对照时我把 `/api/env` 的请求体写成了 `{"env": {...}}`,
> 拿到 422 "Field required"。**那是我自己写错请求体,不是被测代码的行为**——
> 正确形状是 `{"key": ..., "value": ...}`(`hermes_cli/web_models.py:23` 的 `EnvVarUpdate`)。
> 按 CLAUDE.md「shell 命令即证据」那条,一个自己出错的探针比不写更糟,故重跑并只保留正确的那次。

### 2.2 承重的那一跳:config.yaml 顶层标量**确实**变成环境变量

子代理如实申报这一跳"逐字复刻了循环、未真跑 `gateway/run.py`"(该文件模块级有 venv re-exec,
整体导入在本容器不安全)。**主线改用读码确认**:

`gateway/run.py:2058 @ 863e313`

```python
        for _key, _val in _cfg.items():
```

`gateway/run.py:2059 @ 863e313`

```python
            if isinstance(_val, (str, int, float, bool)) and _key not in os.environ:
```

`gateway/run.py:2060 @ 863e313`

```python
                os.environ[_key] = str(_val)
```

**而且它在模块作用域**——往上找到的第一个零缩进行是:

`gateway/run.py:2035 @ 863e313`

```python
if _config_path.exists():
```

**即 `import gateway.run` 就会执行。** 所以不需要额外触发条件:网关每次启动都过一遍,
而 dashboard 自己也有 `_warm_gateway_module`(`hermes_cli/web_server.py:171`)会导入它。

### 2.3 定案

**■-R8C-05**:`PUT /api/config`(`hermes_cli/web_server.py` 的 config 写入路径)对 body 里的键名
**不做任何名单校验**,而同一 dashboard 的 `PUT /api/env`(`:7102`)有写入名单
(`LD_PRELOAD` 实测 400)。config.yaml 的顶层标量会在 `import gateway.run` 时被无条件桥接进
`os.environ`(`gateway/run.py:2058-2060`,模块作用域)。**后果两条**:
(a) **凭据落错文件**——API-key 形状的键被写进 `config.yaml` 而不是 `.env`,
于是**不参与凭据轮换**,且 `GET /api/config` 明文回显(而 `/api/env` 走脱敏);
(b) **名单被绕过**——`/api/env` 拒绝的变量名可以经 `/api/config` 落盘并最终进环境。

**定性边界**:同样是**认证之后**的问题。它削弱的是 dashboard 可写面自己声明的不变式,
不是进门那把锁。

---

## 3. 跨段仲裁:`_GATE_PUBLIC_PREFIXES` 的前缀匹配

**两个底稿对同一处给了不同标签**,主线仲裁:

- `notes/r8c-raw-boot-authchain.md` §5 记为 **◇-4**(理由:当前无碰撞)
- `notes/r8c-raw-dashboard-auth.md` §9 记为 **■-1**(理由:实测确认能绕过闸门)

**两边的事实完全一致,分歧只在标签。** 主线自查了双方各自的承重部分:

判定函数是纯 `startswith`,没有边界检查:

`hermes_cli/dashboard_auth/middleware.py:84 @ 863e313`

```python
        path == prefix or path.startswith(prefix)
```

主线实测(枚举**全部 123 条已注册路由** × 10 条不带尾斜杠的前缀):

```console
名单共 15 条,其中不带尾斜杠 10 条
已注册路由共 123 条。逐条问:它是否被某个不带尾斜杠的前缀**意外**吞掉?
   零命中 —— 今天没有任何已注册路由被意外吞掉

但前缀匹配本身确实成立(不需要路由存在也能免闸门):
   _path_is_public('/loginXYZ') = True
   _path_is_public('/login/../api/config') = True
   _path_is_public('/api/auth/providersXYZ') = True

对照 —— 精确匹配的那张表不受影响:
   _path_is_public('/api/statusXYZ') = False
   _path_is_public('/api/status/secret') = False
```

**裁定:采用 ■ 的标签、◇ 的严重性边界,记 ■-R8C-04(潜伏,当前零暴露)。**

- **标签取 ■**:项目记号里 ◇ 是"代码有、文档无",而这里根本不是文档问题——
  是一道鉴权豁免判据的边界写法。**◇ 是错的标签。**
- **严重性取"零暴露"**:123 条路由全查过,今天没有一条被意外吞掉,**这个边界必须写进定案**,
  否则下一轮会按"有洞"去处置一个没洞的东西。
- **决定性的一条,双方都没点破**:**同一个函数**对另一张表用的是精确匹配,
  而且它的 docstring 就在上面几行,把这个危险讲得清清楚楚——
  "Matched exactly (no prefix expansion) so adding ``/api/status`` doesn't accidentally
  expose ``/api/status/secret-extension``"(`hermes_cli/dashboard_auth/middleware.py:75-76`)。
  **作者为一张表推理过这个危险,为另一张表没有。** 这不是"没想到",是"想到了一半"——
  所以它是缺陷而不是未记录的特性。

**为什么今天不成立**(负结论,写出搜索面):`/login/../api/config` 让判据返回 True,
但 Starlette 的路由匹配**不做路径归一**,该路径落到 SPA catch-all 而不是 `/api/config`;
进程内在鉴权判定之后**没有任何一层会把 `..` 归一掉**(搜索面:
`hermes_cli/web_server.py` + `hermes_cli/dashboard_auth/**` 全部 `*.py`,
搜 `normpath|os.path.normalize|posixpath|resolve()` 用于请求 path 的调用点,
零命中;`_fs_path` 的 `resolve()` 只作用于**查询参数里的文件路径**,不作用于 URL path)。
**危险的是反过来**:若将来在鉴权判定之后引入一层会归一化的转发,这条就立刻成立。

---

## 4. 本轮新立定案索引

| 编号 | 一句话 | 置信度 | 证据 |
|---|---|---|---|
| ■-R8C-01 | `env_loader` 三个进程全局只有一半路径持锁,cron 并行池上并发即失效,路由线程会读到空凭据 | 高(三条后果各有实测) | `notes/r8c-10-*` |
| ■-R8C-02 | `/api/fs/*` 六个端点既无 root 约束也无敏感文件名单,而隔壁 `/api/files/*` 两样都有 | 高(实测) | `notes/r8c-12-*` §5 |
| ■-R8C-03 | 同一个 `config.yaml`:读端点 403,写端点 200 —— 读不到却能改写 `approvals.deny` | 高(实测) | `notes/r8c-12-*` §6 |
| ■-R8C-04 | 鉴权豁免前缀名单 10 条无边界检查,同一函数对另一张表却做了精确匹配 | 中(潜伏,当前零暴露) | 本卷 §3 |
| ■-R8C-05 | `PUT /api/config` 无键名名单,`PUT /api/env` 有;且 config 顶层标量在 import 时进环境变量 | 高(主线独立复现) | 本卷 §2 |
