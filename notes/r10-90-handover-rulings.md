# r10-90 · 移交项定案 —— 主线独立取证

> 溯源约定:凡对 hermes-agent 的断言,锚点写作 `路径:行号 @ 863e313`,单独成行、置于代码块之前。
> 本文件是**主线**的取证记录,不转述子代理。子代理的取证在各片底稿里,对读结果写在各条内。

---

## 1. 先回答一个前置问题:R10 的「移交收件箱」里到底有什么

本轮开工时主线做了一次机械普查,而不是翻报告靠眼睛找。理由是历史上出过两次误判
(R7 有一条移交项因只留标题被下一轮判错定位,另一条被判宽了范围),而**移交项是唯一会被
下一轮当作起点直接使用的东西**。

普查脚本落库在 `data/r10/probes/handover_census.py`,重跑:

```verify
cd /home/user/hermes-study && python3 data/r10/probes/handover_census.py --open-only
```

它把每一条 `H-*` 的「立项轮 → 最后一次处置轮」列出来,判据是**最后一次出现是在移交表还是定案表**。

**一处必须交代的方法学坑,主线自己先踩了一次。** 初版脚本按**列序**取「去向」列(第 2 列),
于是把**定案表**的第 2 列(那是「来源」)读成了去向 —— 结果 `H-R8FIX-a` 被读成「未结清,去向 R8-fix」,
而它其实在 R8C 就已经定案了。各轮报告里有两种长得极像的表:

| 表 | 表头特征 | 行的含义 |
|---|---|---|
| 移交表 | 含「去向」或「建议轮次」 | 新立项,**未结清** |
| 定案表 | 含「处置结论」/「结论」/「复核结果」 | 对既有项的处置 |

改成**按表头名定位列**之后,数字才稳定。这也顺带说明为什么 R8-fix 那张表一开始整张漏掉了 ——
它的表头写的是「建议轮次」而不是「去向」,同义但不同名。

**普查结果:全部 52 条 H-*,其中 26 条未结清。**

**关键结论:26 条里,没有任何一条的「去向」写着 R10。** 去向分布是
R11A 7 条 / R11B 4 条 / R11 复盘 5 条 / R12 前置 1 条 / 已过期或未指定 9 条。
搜索面写清楚:对 `reports/*.md` 全部 19 份报告的**全部**表格行扫 `H-` 前缀 ID,
没有排除任何文件;另对全部 `reports/` + `notes/` + `chapters/` + `reviews/` 用
`grep -rno 'H-R8C-e...'` 逐 ID 复核过散文里的结清痕迹(见下 §1.2)。

### 1.1 那么本轮的移交责任是什么

**两类,共 4 条,R10 主动认领:**

**(a) 唯一一条「时间窗包含 R10」的:H-R8FIX-b。** 它的去向写的是
「任何一轮的空档(建议 R11 之前)」,而 R10 正是 R11 之前的最后一轮。见 §3。

**(b) 三条「去向已过期」的孤儿:H-R8C-e / f / g。** 它们的去向写的是 `R9`,
而 R9 被拆成了 R9A/R9B/R9C/R9D 四轮,**四轮都没有处置它们**。
R10 认领的理由不是「顺手」,而是**取证条件在本轮成熟**:三条讲的都是 dashboard 后端
(`hermes_cli/web_server.py`、`hermes_cli/web_routers/cron.py`,R8C 已精读的 L1),
而**本轮 G 片读的正是这套后端的前端**(`web/`)。「这个危险端点在 UI 上到底可不可达」
这一问,只有同时握着两侧的轮次才能回答。见 §2。

### 1.2 剩下 22 条的处置:逐条给出结论,不写「续转」了事

机械普查的 `OPEN` 判据是「未在报告的**定案表**里出现过」,这是一个**比"未结清"更弱的断言** ——
一条项目可能在底稿散文里被结清了。主线逐条复核了这 22 条:

**已在散文中结清、只是没进定案表的 3 条(账目问题,不是欠账)**:

| 移交项 | 结清处 | 主线复核 |
|---|---|---|
| **H-R9A-a** | `notes/r9c-90-handover-rulings.md`:`H-R9A-a 结清:网关 bearer 的判定用子串` | 结清痕迹在底稿散文里,报告定案表未收录 |
| **H-R9A-d** | `notes/r9b-90-rulings.md`:`H-R9A-d(结清,现象属实但两侧都要修正)` | 同上 |
| **H-R9A-h** | `notes/r9b-90-rulings.md`:`H-R9A-h 结清(本轮验收项 ①)` | 同上;`CLAUDE.md` 里也明写「表格行内锚点(R9B 定,结清 H-R9A-h)」 |

**处置结论:三条判为**「**已结清,账目未记**」。这不是把它们重新打开,而是指出
**移交台账的结清记录有两个存放地(报告定案表 / 底稿散文),机械普查只看得到前者**。
建议的制度修正见 §5。

**去向明确在未来轮次、本轮确认不属 R10 的 18 条**。对每一条,主线做了一件**比"续转"更实的事**:
**核对它的锚点在基线 `863e313` 上是否仍然解析得到**。移交项漂一行就是下一轮直接找错地方,
而这 18 条里有相当一部分的锚点从来没被任何机械校验读过(它们写在表格里,
`verify_citations.py` 在 R9B 之前对表格锚点恒记 UNCHECKED)。逐条见 §4。

**一条去向已过期但不属 R10 的:H-R8C-a。** 去向写 R8D。主线核实它**实质上已被执行**:
`CLAUDE.md` 明写「BLOCK-DRIFT ... R8C 增查、R8D 升格为阻断」且「R8D 实测,116 处」,
即 R8D 清了积压并把检查升格 —— 这正是 H-R8C-a 要求的「升格前需先清这 115 处」。
**处置结论:判为已执行、账目未记,与上面 3 条同类。**

**一条 H-R9B-d,去向 R9C(网关片),主线判为真孤儿但不属 R10。**
它的锚点是 `gateway/relay/media.py:94`,属网关而非界面层;而 R9C 从同一处代码另立了 H-R9C-d
(测试替身重抄被测谓词)。**处置结论:确认未结清,归 R11A**(与 H-R9C-d 同处代码,应同轮做),
不由 R10 认领 —— 本轮范围内没有它的取证条件。

---

## 2. H-R8C-e / f / g:三条孤儿的定案

### 2.1 H-R8C-e —— **维持 ■,并把机制补全到「为什么」这一层**

移交项原文的现象是:「`/api/cron/fire` 的 JWT 用**本进程**配置校验,却能触发**任意 profile** 的 job」。

**第一件事:锚点漂了 5 行,先改正。** 移交项写的是
`hermes_cli/web_routers/cron.py:143`(无 scope 的 `load_config()`),但 `:143` 是一行 import。

`hermes_cli/web_routers/cron.py:145 @ 863e313`

```python
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""

    cfg = load_config()
    claims = get_fire_verifier()(
        token=token,
        expected_audience=cfg_get(cfg, "cron", "chronos", "expected_audience", default=""),
        jwks_or_key=cfg_get(cfg, "cron", "chronos", "nas_jwks_url", default="") or None,
        issuer=cfg_get(cfg, "cron", "chronos", "portal_url", default="") or None,
    )
    if claims is None:
        return JSONResponse({"error": "invalid fire token"}, status_code=401)
```

`load_config()` 的真实位置是 **`:148`**。移交项的另一半 `:169` 是对的。

*这处漂移本身是一条证据*:H-R8C-e 的锚点写在**表格里且没有紧跟反引号摘录**,
所以从 R8C 到 R9D,`verify_citations.py` 对它一直记 UNCHECKED ——
**六个轮次的"引用关卡全绿"里,从来没有一次读过这个锚点**。这正是 `CLAUDE.md`
R9B 那条「移交表的锚点必须用声明式写法」要防的形状,而 R8C 立项时该规则还不存在。

**第二件事:现象成立,而且成因比移交项写的更干净。**
主线要补的是移交项没说的那一层:**`claims` 验完之后就再也没被用过**。

```verify
cd /home/user/hermes-agent && grep -n 'claims' hermes_cli/web_routers/cron.py
```

```text
132:    POSTs here at fire time, the agent verifies, claims the job (store CAS, so
149:    claims = get_fire_verifier()(
155:    if claims is None:
```

三处:一处是 docstring 里的英文单词 `claims`(动词,与变量无关)、一处赋值、一处判空。
**没有任何一处把 `claims` 里的声明(audience / subject / issuer)与"待触发的 job 属于哪个 profile"
做过比对。** 于是校验与授权之间是断开的:校验回答了"这个 token 是 NAS 签的吗",
**没有回答"这个 token 有权动这个 job 吗"**。

而 job 的归属是**跨全部 profile 搜出来的**:

`hermes_cli/web_routers/cron.py:166 @ 863e313`

```python
    # _find_cron_job_profile walks every profile and lists its jobs (file
    # I/O per profile) — run it off the event loop like the other cron
    # dashboard endpoints.
    profile = await _run_cron_dashboard_io(_find_cron_job_profile, job_id)
    if not profile:
        # Job is gone (cancelled / completed) — nothing to fire. 200 so NAS
        # does not retry a fire that is intentionally absent.
        return JSONResponse({"status": "gone", "job_id": job_id}, status_code=200)

    # Run in the background; the store CAS claim inside fire_due de-dupes a
    # NAS/scheduler retry that arrives while this is in flight.
    asyncio.create_task(
        asyncio.to_thread(_fire_cron_job_for_profile, profile, job_id)
    )
    return JSONResponse({"status": "accepted", "job_id": job_id}, status_code=202)
```

`hermes_cli/web_server.py:11699 @ 863e313`

```python
def _find_cron_job_profile(job_id: str) -> Optional[str]:
    for profile in _cron_profile_dicts():
        name = str(profile.get("name") or "")
        if not name:
            continue
        jobs = _call_cron_for_profile(name, "list_jobs", True)
        if any(j.get("id") == job_id or j.get("name") == job_id for j in jobs):
            return name
    return None
```

**合起来的判定**:JWT 用**活动 profile** 的 `cron.chronos.*` 配置校验(`:148` 的 `load_config()` 无 scope 参数),
job 则在**每一个** profile 里找,找到就在那个 profile 下执行。
所以一个只为活动 profile 配了 chronos 的部署,其 fire token 可以触发**任何 profile** 的 job ——
包括根本没配 chronos、因而其所有者从未同意过被 NAS 触发的 profile。

**记号:■(维持)。** 定性收窄一句:这**不是**认证缺失(JWT 是真的在验),
而是**认证与授权之间缺一次绑定** —— 验的是"谁在敲门",没验"他能开哪扇门"。

**未取证部分**:主线**没有**端到端跑一次真实 fire(需要 NAS 侧 JWT 签发者与 chronos 配置,
项目边界明写不配置凭据)。上面是静态全链对读,不是运行时复现。

### 2.2 H-R8C-f —— **确认「无签名无出处」,但把「来源校验」那半句改述**

移交项现象:「backup 打包整个 HERMES_HOME(含 `.env`/`auth.json`),import 覆盖凭据与配置,
**来源校验仅"zip 里出现过某个 basename"**,无签名无出处」。

Operations 簇的位置先核一下 —— 移交项写 `:12801`,那一行落在簇的横幅注释里
(横幅起于 `:12799`),簇的第一个端点在 `:12812`。**锚点不算错,但指的是注释而不是代码。**

全簇端点逐条列全(这是 L2 要求的"接缝穷举",不抽样):

```verify
cd /home/user/hermes-agent && grep -nE '"/api/ops/[^"]*"' hermes_cli/web_server.py
```

```text
3643:@app.post("/api/ops/prompt-size")
3652:@app.post("/api/ops/dump")
3661:@app.post("/api/ops/config-migrate")
3670:@app.post("/api/ops/debug-share")
12812:@app.post("/api/ops/doctor")
12822:@app.post("/api/ops/security-audit")
12841:@app.post("/api/ops/backup")
12869:@app.get("/api/ops/backup/download")
12892:@app.post("/api/ops/import")
12920:@app.post("/api/ops/import-upload")
12998:@app.get("/api/ops/hooks")
13046:@app.post("/api/ops/hooks")
13103:@app.delete("/api/ops/hooks")
13140:@app.get("/api/ops/checkpoints")
13172:@app.post("/api/ops/checkpoints/prune")
```

**15 个 `/api/ops/*` 端点,分两簇**:`:3643`–`:3670` 四个是诊断/导出,
`:12812` 起十一个才是移交项说的 Operations 簇。移交项说的"`:12801` 起的 Operations 簇"
**漏掉了前面那四个同前缀端点** —— 它们不在同一处代码,但在同一个 URL 命名空间下,
对"这个面有多大"这个问题是要一起数的。

**本轮对这一条的处置:确认现象方向成立,但判定权交回给证据面。**
主线**没有**在本轮完成 `/api/ops/import` 的解包与覆盖逻辑精读(那是 `hermes_cli/web_server.py`
的 L1 领地,R8C 的范围,不在 R10 的 556 个文件里),因此**不改述也不加重它的严重度**。
本轮的贡献是另一面:**前端可达性**,由 G 片取证,结论并入 G 片底稿与本轮报告。

**记号:不新立。** 处置结论:**H-R8C-f 的后端半边判为"仍需一次精读",归 R11A**
(与其余 `web_server.py` 欠账同轮);**前端半边由本轮 G 片结清**。
*说清楚为什么不硬结清:这一条的核心断言是"来源校验仅 basename",
要证成或证伪它必须读 import 的解包实现。我没读,就不能给它盖章 —— 一个盖错的章
比一条挂着的移交项更贵。*

### 2.3 H-R8C-g —— **结清,并把「pip install 任意依赖」改述为一条更准的话**

移交项现象:「dashboard 会 **pip install 任意依赖**,是该面第二个"改本机"的入口,
且**不在动作台账里**」。原始出处是 `notes/r8c-raw-status-actions.md` §11 第 2 条,
当时明写"授权与限制路径尚未查"。本轮把这两条都查了。

**授权路径:有闸。** 端点是 `POST /api/memory/providers/{name}/setup`
(`hermes_cli/web_server.py:6059`),`name` 先过一道字符集白名单
`_require_valid_memory_provider_name`(`:6024`,docstring 自陈是为了挡路径穿越),
且该路径**不在** `PUBLIC_API_PATHS` 里,因而受 dashboard 认证中间件管辖
(`hermes_cli/web_server.py:665` 的 `if path.startswith("/api/") and path not in _PUBLIC_API_PATHS`)。
**所以它不是未认证入口** —— 这一点移交项没说,补上之后严重度明显低于字面读法。

**限制路径:有,而且比"任意"严得多。** pip spec **不来自请求体**,来自 provider 目录里
`plugin.yaml` 的 `pip_dependencies`(`hermes_cli/web_server.py:5269`),再经
`tools/lazy_deps.install_specs`,每个 spec 必须过 `_spec_is_safe`:

`tools/lazy_deps.py:554 @ 863e313`

```python
def _spec_is_safe(spec: str) -> bool:
    """Reject pip specs that contain URLs, paths, or shell metacharacters."""
    if not spec or len(spec) > 200:
        return False
    if any(ch in spec for ch in (";", "|", "&", "`", "$", "\n", "\r", "\t", "\\")):
        return False
    if spec.startswith(("-", "/", ".")) or "://" in spec or "@" in spec:
        return False
    return bool(_SAFE_SPEC.match(spec))
```

**所以"任意依赖"要改述为:「任意 PyPI 包名 + 版本范围」**——不能是 URL、不能是本地路径、
不能带 shell 元字符、不能是 `-e` 之类的 pip 开关。这挡掉了直接的命令注入与任意 URL 拉取,
**但没有挡包名本身**:`install_specs` 的 docstring 自陈
"Unlike :func:`ensure`, unknown packages are permitted — the caller owns manifest trust;
this function owns spec hygiene and environment routing."

**动作台账:移交项说得对,确认不在。**

```verify
cd /home/user/hermes-agent && sed -n '3722,3740p' hermes_cli/web_server.py | grep -c '":'
```

```text
17
```

`_ACTION_LOG_FILES`(`hermes_cli/web_server.py:3722`)有 17 个条目,含
`skills-install` / `tools-post-setup` 这类同样"改本机"的动作,**但没有 memory-provider setup**。
搜索面:该字典字面量全部 17 行逐个看过,无一条与 memory provider 相关。

**真正的问题落在 "the caller owns manifest trust" 这句话上。** manifest 从哪来:

`plugins/memory/__init__.py:124 @ 863e313`

```python
def find_provider_dir(name: str) -> Optional[Path]:
    """Resolve a provider name to its directory.

    Checks bundled first, then user-installed.
    """
    # Bundled
    bundled = _MEMORY_PLUGINS_DIR / name
    if bundled.is_dir() and (bundled / "__init__.py").exists():
        return bundled
    # User-installed
    user_dir = _get_user_plugins_dir()
    if user_dir:
        user = user_dir / name
        if user.is_dir() and _is_memory_provider_dir(user):
            return user
    return None
```

user 目录是 `$HERMES_HOME/plugins/`(`plugins/memory/__init__.py:64`,
docstring 一句话:``Return ``$HERMES_HOME/plugins/`` or None if unavailable.``)。
**而 R8D 已定案 ■-R8D-02:dashboard 的文件管理器能往 HERMES_HOME 里写。**
两条拼起来:能用 dashboard 文件管理器的人,可以自己在 `$HERMES_HOME/plugins/<名字>/` 下
放一个 `plugin.yaml`,写上他选的 `pip_dependencies`,再调这个 setup 端点,
让服务端把那些包装进 agent 的运行环境。**"caller owns manifest trust" 这个前提,
在这条面上是不成立的**——manifest 的写入方与调用方是同一个身份。

**记号:■(新立,记为 ■-R10-01),H-R8C-g 结清。**
定性:**不是**"dashboard 能 pip install 任意东西"(那过强),而是
**"install_specs 把信任推给了 manifest,而这条面上的 manifest 是可写的"** ——
又一次"守卫装在了错的一层":spec 卫生检查装得很仔细,而它检查的那个列表的**来源**没人管。

**未取证部分(必须交代)**:主线**没有**实跑这条链(需要起 dashboard、过认证、造 plugin 目录)。
上面是三段已取证事实的静态拼接:(a) manifest 读取路径含 user 目录 —— 本轮取证;
(b) spec 只做卫生检查、允许未知包 —— 本轮取证;(c) 文件管理器可写 HERMES_HOME ——
**引用 R8D 的 ■-R8D-02,本轮未复现**。第 (c) 段是这条链最重的一环,而它是**转述**,不是本轮实测。
若 R11A 要给 ■-R10-01 定严重度,应当先把 (c) 重跑一次。

---

## 3. H-R8FIX-b:**不结清,判归 R11B,但带一次新测量**

移交项:`notes/` 下历史底稿有大量引用校验失败,去向「任何一轮的空档(建议 R11 之前)」。
R8FIX 当时的读数是 **312 处失败(123 MISMATCH + 189 MISSING-FILE)**,分布在 40 份文件里。

**本轮重测(当前脚本,全部 `notes/`)**:

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent notes/*.md 2>&1 | tail -4
```

```text
citations=15003  MISMATCH=125  MISSING-FILE=189  OK=9620  UNCHECKED=5069
可校验比例 OK/15003 = 64.1%  << 低于 70% 下限
table_anchors=2230  OK=531  UNCHECKED=1699   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
FAIL: 314 citation(s) need fixing
```

**读数:314 处(125 MISMATCH + 189 MISSING-FILE)。**
与 R8FIX 的 312 **不是同一次测量,不可直接相减**:R8FIX 之后又有 R8B–R9D 六轮往 `notes/` 里加了文件,
而校验器本身也在这期间长出了 BLOCK-DRIFT 全块比对与表格锚点两项新检查。
两个数摆在一起只能说明**这笔欠账基本原样躺着**,不能说明"只多了 2 处"。

**处置结论:判归 R11B,与 H-R8D-g 合并做。** 三条理由:

1. **它与 H-R8D-g 是同一件活。** H-R8D-g 是 `chapters/` 六章 UNCHECKED ≥90%(锚点排版不合规),
   H-R8FIX-b 是 `notes/` 314 处失败;两者都是"回头补证据",同一轮做可以共用一次全量校验。
   R9D 报告 §12 建议 2 已经这么提过,本轮同意并把它落成决定。
2. **它不该由一个正在读新代码的轮次顺手做。** 189 处 MISSING-FILE 是裸文件名缺目录,
   而基线里 `__init__.py` 有 171 个候选、`base.py` 9 个 —— 每一处都要判"作者当时指的是哪一个"。
   这是需要**读原轮次上下文**的判断,不是机械替换。R10 没有 R2/R6 的上下文。
3. **本轮至少保证不加重它。** R10 自己的 `notes/r10-*.md` 受定稿关卡约束,零 MISMATCH。

**给 R11B 的一份分解**(让它不用重做一次统计):

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent notes/*.md 2>&1 \
  | grep -E '^\[(MISMATCH|MISSING-FILE)\]' | sed 's/^\[\([A-Z-]*\)\] \([^:]*\):.*/\1 \2/' \
  | sort | uniq -c | sort -rn | head -12
```

```text
     29 MISSING-FILE r2-22-credential-pool.md
     24 MISSING-FILE r6-40-mem0-holographic.md
     23 MISSING-FILE r6-30-hindsight-supermemory-retaindb.md
     20 MISSING-FILE r4-40-computer-use.md
     18 MISSING-FILE r3-20-schema-output-toolsearch.md
     14 MISSING-FILE r6-20-openviking-byterover.md
     13 MISSING-FILE r5-20-context-compression.md
     11 MISMATCH r7-raw-run-03-turnrunner.md
      9 MISSING-FILE r2-13-turn-finalizer.md
      8 MISSING-FILE r6-01-loader-query-rewrite-optimize.md
      7 MISMATCH r7-raw-run-10-agent-turn.md
      7 MISSING-FILE r7-raw-session-b.md
```

---

## 4. 18 条「去向在未来轮次」的锚点体检

对每一条,主线核对其锚点在基线上是否仍解析得到。**这不是重做它们的取证**,
而是保证下一轮拿到的起点是对的。判据:锚点所指行的内容与移交项描述是否吻合。

（逐条读数见本轮报告 §4 的表;此处只记方法与两处异常。）

**两处异常,已在本文件点名:**

1. **H-R8C-e 的 `cron.py:143` 漂 5 行**(真实位置 `:148`),见 §2.1。
2. **H-R8C-f 的 `web_server.py:12801` 指向注释而非代码**(簇首个端点在 `:12812`),见 §2.2。

两处都是**写在表格里且没有紧跟反引号摘录**的锚点,因而 `verify_citations.py`
在 R9B 引入表格锚点检查之前对它们恒记 UNCHECKED,之后也因为"未声明摘录"继续记 UNCHECKED。
**这正是 `CLAUDE.md` 那条规则的原始动机在历史数据上的又一次命中**:
R8D 传下来的两条锚点漂一行,是同一个形态;这两条漂 5 行和指到注释,是同一个形态。

---

## 5. 一条制度建议(给 R11 复盘,不在本轮擅自改 CLAUDE.md)

**现象**:移交项的结清记录有两个存放地 —— 报告的**定案表**、底稿的**散文**。
机械普查只看得到前者,于是 4 条已结清的项目(H-R9A-a / d / h、H-R8C-a)
在普查里显示为 `OPEN`,而 3 条真正的孤儿(H-R8C-e / f / g)混在同一堆里,
**看起来和它们一样**。

**这不是记录懒惰的问题,是"未结清"这个状态无法被机械判定的问题。**
本项目已经为同一个理由把引用校验升格成脚本关卡(R8A 的理由:
"规则原本没定计数口径,于是它无法被脚本判定、只能靠人看")。移交台账现在处在升格前的状态。

**建议**:每轮报告的定案表必须收录**本轮处置过的全部** H-* 项,
哪怕处置结论只有"已在底稿 §X 结清";底稿散文可以详述,但**账要记在表里**。
判据可以就是 `data/r10/probes/handover_census.py` 的输出:
**一条项目不应该在普查里长期显示 OPEN 而实际早已结清**。

---

## 6. 本文件的自我限制

1. §2.2(H-R8C-f)**没有结清后端半边**,理由写在该节:没读 import 的解包实现就不盖章。
2. §2.3 的 ■-R10-01 是**三段拼接**,其中最重的一段(文件管理器可写 HERMES_HOME)是
   **转述 R8D,本轮未复现**。已在该节显著标注。
3. §2.1 / §2.3 均为**静态全链对读,无运行时复现**;运行时复现需要真实凭据或起服务,
   项目边界明写不配置。
4. §1 的普查脚本判据是"最后一次出现在移交表还是定案表",它**证明不了**"这条项目没被处置过",
   只能证明"报告的定案表里没有它"。§1.2 的散文复核就是为了补这个缺口,
   而散文复核是 `grep` + 人读,**其完备性等于那次 grep 的完备性**:
   搜索面是 `reports/` + `notes/` + `chapters/` + `reviews/` 全部 `.md`,模式是每个 ID 的字面量,
   未排除任何文件。
