# r8c-12 · 定案 ■-R8C-02 —— 受管文件 API 锁了 root,隔壁的 `/api/fs/*` 没锁

> 溯源约定:`路径:行号 @ 863e313` + 代码原文块,锚点置于块前。
> 实跑环境同 `notes/r8c-10`(venv 87 包)。本条是**主线自查**发现,不在任何移交清单里。

## TL;DR

dashboard 有**两套**浏览文件的 HTTP 接口:`/api/files/*`(受管文件)与 `/api/fs/*`(文件系统)。
前者有 root 约束 + 敏感文件名单,后者**两样都没有**。
在运维**显式要求约束**的那两种部署里(设了 `HERMES_DASHBOARD_FILES_ROOT`、
或托管容器的 `/opt/data` 布局),约束只对前者生效。
同一把 dashboard 会话令牌,`/api/files/read` 拿 `.env` 得 403,
`/api/fs/read-text` 拿同一个 `.env` 得 **200 + 明文**。

而代码里**存在**一个专为这个区分而写的判据 `_local_dashboard_request`
(`hermes_cli/web_server.py:2096`),**全仓零调用点**。

---

## 1. 两套 API,一套守卫

### 1.1 受管文件这一套有什么

**root 约束**在 `_managed_files_policy`,两种部署下会把 `locked_root` 锁死:

`hermes_cli/web_server.py:2156 @ 863e313`

```python
def _managed_files_policy(request: Request, *, create_root: bool = True) -> ManagedFilesPolicy:
```

一是运维显式设了 `HERMES_DASHBOARD_FILES_ROOT`:

`hermes_cli/web_server.py:2159 @ 863e313`

```python
        root = _ensure_managed_root(raw_forced_root) if create_root else _canonical_path(Path(raw_forced_root))
```

二是托管容器布局(Hermes root 就是 `/opt/data`)。两支都返回
`ManagedFilesPolicy(default_path=root, locked_root=root, can_change_path=False)`——
**`can_change_path=False`,意思写得很清楚:这不是默认目录,是不许改的边界。**

约束在解析路径时兑现:

`hermes_cli/web_server.py:2207 @ 863e313`

```python
    if root is not None and not _path_is_under(root, resolved):
```

**敏感文件名单**是另一层,挡 `.env` / `config.yaml` / `auth.json` 一类:

`hermes_cli/web_server.py:1821 @ 863e313`

```python
def _is_sensitive_path(path: Path) -> bool:
```

它的 docstring 自己划了范围——**这句话是本条定案的起点**:

`hermes_cli/web_server.py:1833 @ 863e313`

```python
    Read-side only: this guards list/read/download (the #57505 exfil surface).
```

### 1.2 这层守卫实际用在哪:三处,全是 `/api/files/*` 的读端点

`hermes_cli/web_server.py:2361 @ 863e313`

```python
            if not _is_sensitive_path(child)
```

`hermes_cli/web_server.py:2388 @ 863e313`

```python
    if _is_sensitive_path(target):
```

`hermes_cli/web_server.py:2432 @ 863e313`

```python
    if _is_sensitive_path(target):
```

分别属于 `GET /api/files`(:2349)、`GET /api/files/read`(:2381)、
`GET /api/files/download`(:2416)。

**搜索面(负结论)**:在 `/home/user/hermes-agent` 下对全部 `*.py` 搜
`_is_sensitive_path|_is_sensitive_filename`,排除 `./tests/`,
命中 **8 行且全在 `hermes_cli/web_server.py`**:两处函数定义(`:1800`、`:1821`)、
三处 docstring 内的自引用(`:1813`、`:1824`)、一处函数体内互调(`:1838`),
以及上面这三处真正的调用点。**没有第四个调用点。**

### 1.3 `/api/fs/*` 这一套什么都没有

路径解析器接受**任意绝对路径**,不认识 policy,也不认识 root:

`hermes_cli/web_server.py:1906 @ 863e313`

```python
def _fs_path(raw_path: str) -> Path:
```

`hermes_cli/web_server.py:1918 @ 863e313`

```python
        candidate = Path(raw).expanduser()
```

读端点直接用它,连 `Request` 都不收(所以它**在结构上就不可能**做任何按请求的判定):

`hermes_cli/web_server.py:2624 @ 863e313`

```python
async def fs_read_text(path: str):
```

全族 6 个端点:`/api/fs/list`(:2597)、`/api/fs/read-text`(:2623)、
`/api/fs/write-text`(:2647)、`/api/fs/read-data-url`(:2694)、
`/api/fs/git-root`(:2708)、`/api/fs/default-cwd`(:2719)。

---

## 2. 实测:同一部署、同一把令牌,两套 API 的可达面

设 `HERMES_DASHBOARD_FILES_ROOT` 指向一个临时 root(内含 `note.txt` 与 `.env`),
起真实的 `hermes_cli.web_server.app`,带 `X-Hermes-Session-Token` 请求:

```console
A) /api/files/*(受管 API,声明锁在 root 内)
  read root 内普通文件            -> 200  {"name":"note.txt",...
  read root 内的 .env(敏感名单)   -> 403  {"detail":"Access to sensitive files is not allowed"}
  read root 外 /etc/hostname      -> 403  {"detail":"Path outside managed files root"}

B) /api/fs/*(同一个 dashboard、同一把 token)
  read-text root 内普通文件        -> 200
  read-text root 内的 .env         -> 200  {"binary":false,"byteSize":31,...   ← 明文返回
  read-text root 外 /etc/hostname  -> 200
  list root 外 /etc                -> 200  {"entries":[{"name":".java",...

C) 无 token 时(确认两者都在鉴权之后)
  /api/files/read?...  -> 401
  /api/fs/read-text?... -> 401
```

**A 段三行证明约束确实在工作;B 段三行证明它被隔壁绕开;
C 段两行是本条定性的关键——这是鉴权之后的事,不是未认证暴露。**

---

## 3. 为这个区分写好的判据,一次都没被调用

代码里有一个函数,内容正是"这个请求算不算本机 dashboard":

`hermes_cli/web_server.py:2096 @ 863e313`

```python
def _local_dashboard_request(request: Request) -> bool:
```

它第一句就是"鉴权门开着就不算本机",随后比对回环主机名——
**这正是区分「桌面版本机使用」与「托管远程访问」所需要的那个判据。**

**搜索面(负结论)**:在 `/home/user/hermes-agent` 下对全部 `*.py` 搜
`_local_dashboard_request`(不排除 tests),**全仓命中 1 行,就是上面这行定义**。
**零调用点,零测试。**

而 `/api/fs/*` 的 6 个端点**没有一个收 `Request`**,所以即便有人想调它也调不了——
得先改签名。**这不是"忘了加判断",是"判断写好了、接线没做"。**

---

## 4. 这是缺陷,还是有意的?

**要为"有意"辩护是可能的**,必须把它写出来再驳:
`/api/fs/*` 是**桌面版编码轨**的文件树——同段里还有 `_fs_find_git_root`(:1962)、
`_fs_git_branch`(:1990)、`/api/fs/default-cwd`(:2719),
它服务的是"在浏览器里编辑本机项目"。对一个跑在自己机器上的桌面应用,
不设约束是**恰当的**:用户本来就能读自己所有文件。

**驳:问题不在 `/api/fs/*` 无约束,而在没有任何东西区分这两种部署。**

- 运维设 `HERMES_DASHBOARD_FILES_ROOT` 是一个**明确的意思表示**:把文件面关进这个目录。
  代码接受了这个表示,并且**只兑现了一半**。
- 托管布局那一支更明显:`_default_hermes_root_is_opt_data()` 为真时自动上锁,
  说明作者认得"这是托管环境,得关起来"这件事——但只在 `/api/files/*` 上认。
- `_is_sensitive_path` 的 docstring 说自己是 read-side、写侧"由 write-path checks 处理"。
  **本轮查证:写侧(`POST /api/files/upload` :2453、`DELETE /api/files` :2573)
  确实不调这层守卫**,它们只经 `_resolve_managed_path` 拿到 root 约束——
  root 约束是**容器**检查,不是**敏感性**检查。所以那句 "handled by the write-path checks"
  在"敏感性"这个意义上**没有对应实现**;它大概指的是 root 约束,但那句话读起来不是这个意思。
- 最重的一条:**`_local_dashboard_request` 的存在本身就是反驳**。
  如果无约束是有意的,不会有人去写一个"这是不是本机 dashboard"的判据。
  它写了,没接上,**这是未完成,不是决定**。

**配套测试也不支持"有意"。** `tests/hermes_cli/test_web_server_fs.py` 全文 69 行、3 个用例
(本轮实跑 **3 通过 / 0 失败**),分别测排序与噪声目录隐藏、大小上限、以及"要鉴权"。
**没有任何一个用例断言 `/api/fs/*` 应当不受 root 约束或应当能读敏感文件。**
搜索面:对 `tests/` 全树搜 `api/fs/`,只命中这一个文件。

---

## 5. 定案 ■-R8C-02

**■-R8C-02**(中置信,后果需部署前提):
`hermes_cli/web_server.py` 里 `/api/fs/*` 六个端点(`:2597`–`:2725`)经
`_fs_path`(`:1906`)接受任意绝对路径,**既不经 `_managed_files_policy`(`:2156`)的
`locked_root` 约束,也不经 `_is_sensitive_path`(`:1821`)的敏感文件名单**,
而同一 dashboard 的 `/api/files/*` 两样都有(`:2207` / `:2361`、`:2388`、`:2432`)。
**后果**:在运维显式设了 `HERMES_DASHBOARD_FILES_ROOT` 或使用 `/opt/data` 托管布局的部署里,
任何持有 dashboard 会话的主体都能经 `/api/fs/read-text` 读到 root 之外的任意文件、
以及 root 之内被敏感名单挡掉的 `.env` / `config.yaml` / `auth.json`,
并能经 `/api/fs/write-text`(`:2647`)写任意路径。
**为这个区分写的判据 `_local_dashboard_request`(`:2096`)全仓零调用。**

**定性边界(必须一起读)**:这是**认证之后**的约束绕过,**不是**未认证暴露——
两套 API 都被 `auth_middleware` 挡在 401 之后(已实测)。
它削弱的是"运维划的那条线",不是"进门那把锁"。
在桌面单机部署里(`locked_root=None`),两套 API 本就等价,**此条无影响**。

**最小修法**:给 `/api/fs/*` 六个端点加 `request: Request` 参数,
接上已经写好的 `_local_dashboard_request`;或者更简单——
让 `_fs_path` 在 `locked_root is not None` 时复用 `_resolve_managed_path` 的约束与敏感判定。

---

## 6. 定案 ■-R8C-03 —— 同一个文件:读不到,却能改写

上面 §4 提到写侧不调敏感判定。**本轮把这条链跑完了,它比读侧那条更利。**

### 6.1 受管 root 在托管布局下**就是 Hermes home**

这一步是全条的支点。托管布局的锁定 root 是个常量:

`hermes_cli/web_server.py:1733 @ 863e313`

```python
_HOSTED_MANAGED_FILES_ROOT = Path("/opt/data")
```

而 `/opt/data` 在这种部署里正是 Hermes 自己的根目录:

`hermes_constants.py:167 @ 863e313`

```python
    In Docker or custom deployments where ``HERMES_HOME`` points outside
```

`hermes_constants.py:169 @ 863e313`

```python
    — that IS the root.
```

**所以锁定的受管 root 里装的就是真的 `config.yaml`、`auth.json`、`.env`、
`mcp-tokens/`、`pairing/`** ——这也正是敏感文件名单里列的那几个名字。
名单不是随手写的,它是照着这个目录的内容写的。

### 6.2 实测:读 403,写 200

`hermes_cli/web_server.py:2453 @ 863e313`

```python
async def upload_managed_file(payload: ManagedFileUpload, request: Request):
```

`hermes_cli/web_server.py:2573 @ 863e313`

```python
async def delete_managed_file(payload: ManagedFileDelete, request: Request):
```

两者都只经 `_resolve_managed_path`(root 约束),**不经 `_is_sensitive_path`**。实跑:

```console
改写前 config.yaml: 'approvals:\n  deny: [rm -rf]\n'
POST /api/files/upload (config.yaml, overwrite) -> 200
改写后 config.yaml: 'approvals:\n  deny: []\n'
DELETE /api/files (auth.json) -> 200   auth.json 还在吗: False
对照 —— 同一个文件走读端点 GET /api/files/read -> 403 {"detail":"Access to sensitive files is not allowed"}
```

**最后那一行是整条定案的形状**:同一个 `config.yaml`,读端点说"敏感,不给",
写端点一声不吭地让它被整个替换掉——而被替换掉的内容是 `approvals.deny`,
**agent 的工具审批黑名单**。

### 6.3 定案

**■-R8C-03**(中置信,后果需部署前提):
`POST /api/files/upload`(`hermes_cli/web_server.py:2453`)与
`DELETE /api/files`(`:2573`)不经 `_is_sensitive_path`(`:1821`),
而同名文件的读端点经过并返回 403。在托管布局下受管 root 即 Hermes home
(`:1733` = `/opt/data`,`hermes_constants.py:169`),
于是**持有 dashboard 会话者可以覆盖或删除 `config.yaml` / `auth.json` / `.env`
这些他读不到的文件**。覆盖 `config.yaml` 可清空 `approvals.deny`,
即**用一个文件管理器端点改掉 agent 的审批策略**;删除 `auth.json` 可清掉凭据存储。

**这不是 ■-R8C-02 的重复**:R8C-02 说的是"隔壁 API 没有这道守卫",
本条说的是"**同一个 API 家族内部,读有写没有**",
而且它的 docstring(`:1833` "Read-side only … handled by the write-path checks")
**声称写侧另有处理**——本轮查证那句话在"敏感性"这个意义上没有对应实现,
写侧只有 root 容器约束。所以本条同时是一处 ▲(注释所述与代码不符)。

**定性边界**:同样是**认证之后**的问题(两个写端点也在 401 之后)。
桌面单机部署下 `locked_root=None`、用户本就拥有这些文件,**此条无影响**。

---

## 7. 本段未覆盖 / 存疑

| 项 | 锚点 | 一句话现象 |
|---|---|---|
| `POST /api/files/upload-stream`(`:2488`)与 `mkdir`(`:2552`)未实测 | `hermes_cli/web_server.py:2488`、`:2552` | 与 `upload` 同族、同样不调 `_is_sensitive_path`(§1.2 的搜索面已证明全仓只有三个调用点),**推定同样可写敏感名**,但没跑 |
| 改掉 `approvals.deny` 后 agent 是否真的立刻放宽 | `hermes_cli/web_server.py:2453` 写入的是磁盘文件;读取方在 `tools/approval.py` | 本轮只证明**文件被改**,**没有**接着跑一次 agent 去验证审批策略真的松了;中间可能有缓存或重载条件 |
| SPA 前端是否真会在托管部署下调 `/api/fs/*` 未查 | `hermes_cli/web_server.py:2719`(`/api/fs/default-cwd`) | 本条只证明 HTTP 接口可达;**前端在托管模式下是否隐藏编码轨入口没查**。即便隐藏,接口仍可直连,不影响定案,但影响"用户会不会无意中撞见" |
| `/api/fs/read-data-url`(`:2694`)未实测 | `hermes_cli/web_server.py:2694` | 与 `read-text` 同族同解析器,推定同样无约束,**但没跑** |
