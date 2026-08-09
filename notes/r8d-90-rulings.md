# r8d-90 · 定案卷 —— R8C 移交项结清与本轮跨簇仲裁

> 溯源约定:凡对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` **单独成行、置于块前**。
> 基线 = `NousResearch/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`。

本卷记两类东西:(1) R8C 向 R8D 移交的三条未决项,**主线独立取证**后的结清;
(2) 本轮跨簇的仲裁与改判。子代理产出的簇内定案在各自 `notes/r8d-raw-*.md` 里。

---

## 1. H-R8C-b —— 结清:写路径**根本没有**敏感名守卫,不是"漏了两个端点"

**移交原文**:`hermes_cli/web_server.py:2488`(`upload-stream`)、`:2552`(`mkdir`)与 `:2453`
的 `upload` 同族、同样不调 `_is_sensitive_path`,**推定同样可写敏感名但未实测**。

**结清结论:推定成立,但移交项把问题说小了。** 这不是"三个端点忘了调守卫",
而是**整条写路径在设计上就不查敏感名**——而且代码自己写下了这个决定。

### 1.1 全仓调用点:3 个,全在读侧

```verify
cd /home/user/hermes-agent && grep -rn "_is_sensitive_path" . --include=*.py
```

搜索面:基线全仓 `*.py`(不限目录,含 `tests/`);模式为函数名全字面量,无通配。
实测 5 处命中——1 处定义(`:1821`)、1 处 docstring 提及(`:1813`)、3 处真调用:

`hermes_cli/web_server.py:2358-2361 @ 863e313`

```python
        entries = [
            _managed_file_entry(policy, child)
            for child in target.iterdir()
            if not _is_sensitive_path(child)
        ]
```

`hermes_cli/web_server.py:2388-2389 @ 863e313`

```python
    if _is_sensitive_path(target):
        raise HTTPException(status_code=403, detail="Access to sensitive files is not allowed")
```

`hermes_cli/web_server.py:2432-2433 @ 863e313`

```python
    if _is_sensitive_path(target):
        raise HTTPException(status_code=403, detail="Access to sensitive files is not allowed")
```

三处分别是**列目录**(过滤掉敏感项)、**读文件**、**下载文件**——全是读侧。
写侧(`upload` / `upload-stream` / `mkdir` / `delete`)一处也没有。

移交项点名的两个端点,连同它们的同族 `upload`,三条第一句话是同一句
——`_resolve_managed_path(..., for_write=True)`,此后再无守卫:

`hermes_cli/web_server.py:2452-2454 @ 863e313`

```python
@app.post("/api/files/upload")
async def upload_managed_file(payload: ManagedFileUpload, request: Request):
    policy, target, display_path = _resolve_managed_path(payload.path, request, for_write=True)
```

`hermes_cli/web_server.py:2487-2494 @ 863e313`

```python
@app.post("/api/files/upload-stream")
async def upload_managed_file_stream(
    request: Request,
    file: UploadFile = File(...),
    path: str = Form(...),
    overwrite: bool = Form(True),
):
    policy, target, display_path = _resolve_managed_path(path, request, for_write=True)
```

`hermes_cli/web_server.py:2551-2553 @ 863e313`

```python
@app.post("/api/files/mkdir")
async def create_managed_directory(payload: ManagedDirectoryCreate, request: Request):
    policy, target, display_path = _resolve_managed_path(payload.path, request, for_write=True)
```

### 1.2 代码自己声明了这个决定

移交项推定"漏调";实际是**明写的范围划定**。守卫的 docstring 结尾:

`hermes_cli/web_server.py:1833-1836 @ 863e313`

```python
    Read-side only: this guards list/read/download (the #57505 exfil surface).
    The write endpoints (upload/mkdir/delete) are a separate threat class
    handled by the write-path checks; extending this guard to them is out of
    scope for this fix.
```

于是真正该问的不是"为什么没调守卫",而是**"the write-path checks" 到底是什么**。

### 1.3 ■-R8D-01:写路径的检查只有穿越与根包含,**没有任何敏感名检查**

三个写端点走的是同一个解析器 `_resolve_managed_path(..., for_write=True)`。
它全文只有两类拒绝:`..` 路径穿越,以及"解析结果必须在受管根之下"。

`hermes_cli/web_server.py:2198-2200 @ 863e313`

```python
    if ".." in candidate.parts:
        raise HTTPException(status_code=400, detail="Path cannot contain '..'")
```

`hermes_cli/web_server.py:2207-2208 @ 863e313`

```python
    if root is not None and not _path_is_under(root, resolved):
        raise HTTPException(status_code=403, detail="Path outside managed files root")
```

`for_write=True` 唯一改变的是**规范化方式**(允许目标尚不存在),不引入任何额外校验:

`hermes_cli/web_server.py:2201-2206 @ 863e313`

```python
    if for_write and not candidate.exists():
        parent = _canonical_path(candidate.parent)
        resolved = parent / candidate.name
    else:
        resolved = _canonical_path(candidate, require_exists=not for_write)
```

**所以 docstring 里那句 "handled by the write-path checks" 指向的东西不存在。**
按本项目记号这是 ■(代码缺陷)而非 ▲——▲ 留给 README / AGENTS.md / website/docs
这类作者自绘地图,而这是代码内注释。但它比一般注释腐烂更值钱:
**它会让下一个维护者以为这里已经有人管了**,从而不去加检查。

### 1.4 实测:五个敏感目标全部通过写路径解析

不靠推理。直接调被测函数(临时目录,不碰基线):

```console
[H-R8C-b] 写路径解析 '.env'                   -> 通过, 目标='.env', _is_sensitive_path=True
[H-R8C-b] 写路径解析 'auth.json'              -> 通过, 目标='auth.json', _is_sensitive_path=True
[H-R8C-b] 写路径解析 'config.yaml'            -> 通过, 目标='config.yaml', _is_sensitive_path=True
[H-R8C-b] 写路径解析 'mcp-tokens/tok.json'    -> 通过, 目标='tok.json', _is_sensitive_path=True
[H-R8C-b] 写路径解析 'pairing/p.json'         -> 通过, 目标='p.json', _is_sensitive_path=True
```

右边一列是关键:**同一个守卫对这五个目标全部返回 True**——
守卫认得它们,只是写路径不问它。`mcp-tokens/tok.json` 尤其说明问题:
目标 basename 是无害的 `tok.json`,守卫仍判 True,因为它查的是**路径分量**:

`hermes_cli/web_server.py:1838-1840 @ 863e313`

```python
    if _is_sensitive_filename(path.name):
        return True
    return any(part.lower() in _SENSITIVE_MANAGED_DIR_NAMES for part in path.parts)
```

**H-R8C-b 关闭。** 结论比移交项更强:不是两个端点的疏漏,是整条写路径的空白,
且守卫本身完全够用——差的只是一次调用。

---

## 2. H-R8C-c —— 结清:写进去的策略**真的即时生效**,■-R8C-03 应加重

**移交原文**:■-R8C-03 只证明**文件被改**,**没有**接着跑一次 agent 验证
`approvals.deny` 真的松了;中间可能有缓存或重载条件。

**结清结论:没有那个"中间层"。配置缓存以 (mtime, size) 为键,覆盖写立即生效。**
而且——这是本条最值得记的部分——**代码库自己早就知道**,并且正是**因为**知道
才在别处加了防线。

### 2.1 实测:同进程内覆盖 config.yaml,deny 表当场清空

```console
[H-R8C-c] 写入前 approvals.deny = ['rm -rf *', 'curl *']
[H-R8C-c] 覆盖后 approvals.deny = []
[H-R8C-c] 结论:策略是否即时松开 = True
```

两次 `load_config_readonly()` 之间只做了一件事:把 `~/.hermes/config.yaml`
覆盖成 `deny: []`——正是 `/api/files/upload` 对受管文件做的事。

### 2.2 机制:缓存键是 (mtime_ns, size),不是进程生命周期

`hermes_cli/config.py:3291 @ 863e313`

```python
            user_sig: Optional[Tuple[int, int]] = (st.st_mtime_ns, st.st_size)
```

审批侧读的就是这份缓存,并且明写"调用方拿到的是 LIVE 子字典":

`tools/approval.py:2921-2926 @ 863e313`

```python
def _get_approval_config() -> dict:
    """Read the approvals config block. Returns a dict with 'mode', 'timeout', etc.

    Returns the LIVE config-cache sub-dict (load_config_readonly contract) —
    callers must not mutate it or any nested structure.
    """
```

### 2.3 代码库知道这件事,并因此在**终端侧**建了防线

这条最有教学价值。`tools/approval.py` 把 `~/.hermes/config.yaml` 当作
**安全策略本身**来防护,理由写得毫不含糊:

`tools/approval.py:279-286 @ 863e313`

```python
# ~/.hermes/config.yaml IS the security policy: approvals.mode, yolo, and the
# permanent-approval allowlist live here, and the config cache is mtime-keyed
# so a write takes effect mid-session (the agent could flip approvals.mode=off
# and immediately bypass the gate). Pair the write_file/patch deny (file_tools
# _check_sensitive_path) with terminal-side coverage so `sed -i`, `tee`, `>`,
# `cp`, etc. targeting it are gated too — otherwise the deny is unpaired
# theater. Mirrors _HERMES_ENV_PATH; matches the HERMES_HOME override form as
# well as ~/.hermes/.
```

把这段和 §1 并排读,本轮最重要的一条结论就出来了:

> **同一个威胁,`tools/` 侧堵了两条路(工具写 + 终端写),
> `web_server` 侧的受管文件写端点是没堵的第三条。**
> approval 的注释甚至提前给出了判据——"otherwise the deny is unpaired theater"
> (不配对的 deny 就是演戏)。dashboard 这条路正好构成那个不配对的缺口。

**H-R8C-c 关闭,并把 ■-R8C-03 加重为 ■-R8D-02:**
后果不是"配置文件可被改写",而是**dashboard 的文件管理器是一条通往审批闸门的提权路径**——
写一次 `config.yaml`,运行中的 agent 立刻按新策略执行。

### 2.4 一处必须说明的边界(不夸大)

缓存键是 `(mtime_ns, size)` 而非内容哈希,所以理论上"同 mtime_ns 同 size 的改写"不会被感知。
`mtime_ns` 是纳秒级,实际写入几乎不可能撞上;**这一条不削弱上面的结论,写出来是为了不把话说满**。

---

## 3. H-R8C-d —— 归属澄清:本轮不结清,理由是范围

**移交原文**:`hermes_cli/env_loader.py:667`(无锁写 `_SECRET_SOURCES`)vs `:235`(有锁写);
■-R8C-01 只复现了另外两个全局,`_SECRET_SOURCES` 同样两路无锁/有锁地写,
**后果推定更轻但未验证**。

`env_loader.py` 是 **R8A 的 L1 文件**(`assign_layers.py` 规则 `hermes_cli/env_loader.py → L1/R8A`),
不在 R8D 的 52 个 L1 文件里。移交单把它标成 "R8D / R9" 两可。

**本轮裁定:留 R9,不在 R8D 结清。** 理由不是工作量,是**取证条件**:
这条要验的是"无锁写在并发下的可观测后果",而 R8C 已复现的另外两个全局
(■-R8C-01)给出的正是同型证据;再补一个同型复现,增量是确认而非发现。
R9 计划里有并发/竞态的正题,届时与那两个一并做**一次**验证更省也更完整。

**移交给 R9(带锚点,按制度)**:`hermes_cli/env_loader.py:667` 无锁写 `_SECRET_SOURCES`,
与 `:235` 的有锁写并存;现象是同一全局两条写路径锁纪律不一致,后果推定轻于 ■-R8C-01
已复现的两个全局,**未验证**。

---

## 4. 本轮对历史产出的就地改正(制度要求点名)

`chapters/` 与 `notes/` 直接改正文;`reports/` 正文不静默改写、走文末勘误节。
本节只记**主线**做的改判;子代理在自己文件内的逐字修正见 §5 汇总。

### 4.1 两处锚点区间放宽(摘录补全后超出原声明区间)

- `notes/r7c-raw-cron-sched-b.md`:`gateway/run.py:26910-26911` → `:26910-26913`。
  原区间只有 2 行,逐字恢复后块尾悬空在 `lambda: not (`,读者读不到 lambda 的条件本体。
- `notes/r5-02-hermes-state-sessiondb.md`:`hermes_state.py:1737-1747` → `:1737-1748`。
  第 1747 行断在 `Pass ``force=True`` only for offline`,下半句在 1748。

两处都**只动结束行号**,起始行与文件路径未变,结论未变。

### 4.2 一处陈旧括注删除

`notes/r7-raw-run-09-handle-message.md` 的 `gateway/run.py:15721-15743` 锚点原带括注
"(注释压缩节选)"。该块经本轮修正后已是全区间逐字,括注成了错误描述,删去。

---

## 5. BLOCK-DRIFT 历史积压清理:116 处的形态学

R8C 给校验器补上全块比对后扫出 115 处历史积压(R8C 自己的 3 处已修),
本轮实测 **116 处**(差 1 见下),分五组并行清完。**值得记的是形态分布,不是数字**:

| 形态 | 占比 | 说明 |
|---|---|---|
| 行尾被截短 | 最多 | 摘录把基线某行砍掉后半句,后续每行错位 |
| 多行调用被压成一行 | 次之 | `foo(a, b, ...)` 这种"看起来更清爽"的改写 |
| 无效的行内省略号 | 少数 | `# ... 之类`、`[中略]`、`...))` —— 都不匹配 ELISION 正则,既不逐字也不算声明跳段 |
| 中段整段省略但没留标记 | 少数 | 漏抄了几行注释/docstring |
| **摘录作了个假声明** | **1 处** | 见下 |

**唯一一处"假声明"**:`notes/r7c-raw-kanban.md` 有一块在第 11 行凭空补了 `"""` 收尾,
暗示 `gateway/platform_registry.py` 的模块 docstring 到第 10 行结束;
基线第 11 行是空行,docstring 实际到第 29 行(中间还有整段 Usage 示例)。
**没有结论依赖这个收尾**,已换成裸 `...`。

其余 115 处**全部靠回抄基线原文解决**,五组子代理合计只用了 1 次"补省略标记"、
0 次"改标 ```text"。这个分布本身是结论:

> **历史积压不是"作者把非源码塞进了代码块",而是"作者抄源码时手抖"。**
> 前者需要判断力去甄别,后者只需要一台机器去比对——
> 而这台机器 R7C 就该有了,R8C 才把它补全。

**为什么是 116 而不是 115**:R8C 报告的 115 是它当时的全语料读数;
本轮开工前重跑得 116。差的 1 处在 `chapters/r8a-configuration-surface.md`,
R8C 自己的报告 §2.2 里也记了"全量跑 BLOCK-DRIFT=4"(chapters 侧),
与"115 处历史积压"是两次不同口径的统计。**两个数都不错,是口径差**,
本轮统一按"全语料 = chapters + notes + reports 一次跑出的数"记,即 116。

### 5.1 一个基线自身的错字(不是我们的)

`hermes_cli/tools_config.py:5291 @ 863e313`

```python
        # Drop any legacy exclude block — we\'re include-mode now.
```

基线注释里字面就有一个多余反斜杠(`od -c` 已确认是 ASCII `\` + `'`)。
`chapters/r8a-configuration-surface.md` 原先"顺手改干净"成了 `we're`,
按逐字契约已还原。**读起来像错字,但那是基线的错字。**
逐字契约的价值正在这里:它不允许"善意的清理"。
