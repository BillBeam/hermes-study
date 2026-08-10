# R11B 片 D 底稿 —— 历史 notes 引用积压清账(H-R8FIX-b)

> 求全求证底稿。本片是**清账**,不是内容轮:只更正记录,不改变任何已定案结论的实质。
> 凡发现旧结论**本身**可能错(不是引用漂了),一律不就地改结论,而是在 §6 单独立项、给证据、交主线定案。
> 基线 `863e31318553cda8ad61df681d08175364d4164b`,只读。
> 溯源约定:锚点 `路径:行号 @ 863e313` 单独成行、置于块之前;```verify 块贴可重跑命令,
> 紧跟的 ```text 块是它的逐字输出。

---

## 0. TL;DR

- 历史 notes 的引用积压 **314 处失败 → 3 处**,分布的 **41 个文件里 40 个清零**。
- 清理**新暴露**出 51 处 `BLOCK-DRIFT`(围栏块首行之后的行从来没被校验过),已全部按基线原文回抄。
- 这 41 个文件的 **OK 数 522 → 820**(+298),即真正被机器比对过的引用多了将近一倍。
- 剩下 3 处全在 `notes/r6-60-mcp-oauth-cleanup.md`,指向**第三方 `mcp` SDK**(不在基线里),
  关卡结构上够不到它们,**留而不改**,理由与修法建议见 §5.1。
- 一条要如实说的覆盖面:这 41 个文件里仍有 **1,334 / 3,314(40.3%)** 个锚点路径无法从仓库根解析。
  它们不是失败(没跟代码块,记 UNCHECKED),但"裸文件名"这个病灶远大于关卡报的那个数。见 §7。

---

## 1. 任务与范围

移交项 **H-R8FIX-b**(与 H-R8D-g 合并后归 R11B)。

`reports/round-10-client-interface-layer.md:528 @ 本仓库`

> | **H-R8FIX-b**(合并后续转) | R11B | 本报告 §4 的 **314 处**与按文件分解表 | 与 H-R8D-g 合并做,共用一次全量校验 |

成因是关卡的**强制范围**:`chapters/` 全部 + **本轮** notes/reports。已完成轮次的 notes
从来不在范围里,于是每一轮新写的漂移都没人查,攒了 314 处。

**本片范围**:`data/r11b/notes-citation-backlog.txt` 第一列的 **41 个历史 notes 文件**
(文件名不以 `r11b-` 开头者)。`notes/r11b-*.md` 是本轮其他片正在写入的文件,全程未碰;
所有校验器调用都**显式列出文件**,一次也没有用过 `notes/*.md` 通配符。

---

## 2. 读数:清理前 / 清理后

### 2.1 清理前(积压的分类,取自随本轮落库的明细文件)

```verify
cd /home/user/hermes-study && awk '{print $1}' data/r11b/notes-citation-backlog.txt | sort | uniq -c
```

```text
    125 [MISMATCH]
    189 [MISSING-FILE]
```

清理前全 notes 语料的合并读数(主线派工书给出、本片开工时已逐字复现):
`citations=16612 MISMATCH=125 MISSING-FILE=189 OK=10828 UNCHECKED=5470`,可校验比例 **65.2%**。

### 2.2 清理后(本片 41 个文件)

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent \
  $(awk '{split($2,a,":"); print "notes/" a[1]}' data/r11b/notes-citation-backlog.txt | sort -u) | tail -4
```

```text
citations=2300  MISSING-FILE=3  OK=820  UNCHECKED=1477
可校验比例 OK/2300 = 35.7%  << 低于 70% 下限
table_anchors=248  OK=3  UNCHECKED=245   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
FAIL: 3 citation(s) need fixing
```

同一条命令在清理前的读数(用 `git show HEAD:<file>` 还原这 41 个文件后跑,验证本片起点与派工书一致):
`citations=2285 MISMATCH=125 MISSING-FILE=189 OK=522 UNCHECKED=1449`,可校验比例 **22.8%**。

**这两个数放在一起才说明问题**:失败 314 → 3,而 **OK 从 522 涨到 820**。
后者才是本片真正的产出——多出来的 298 条引用从"根本没被比对过"变成"每次跑都被逐行比对"。

### 2.3 全语料快照(收工时点)

| 口径 | citations | OK | UNCHECKED | 失败 | 可校验比例 |
|---|---:|---:|---:|---:|---:|
| 全 notes(清理前) | 16,612 | 10,828 | 5,470 | **314** | 65.2% |
| 全 notes(清理后快照) | 16,627 | 11,126 | 5,498 | **3** | 66.9% |
| 本片 41 文件(清理前) | 2,285 | 522 | 1,449 | **314** | 22.8% |
| 本片 41 文件(清理后) | 2,300 | 820 | 1,477 | **3** | 35.7% |

全语料那两行**不钉输出**:本轮其他片也在改历史 `notes/`(本片作业期间观察到
`notes/r8d-raw-credentials-security.md`、`notes/r9a-raw-skills-sync.md`、
`notes/r9c-raw-secret-sources.md` 被另一片改动并由主线落库),合并读数会随之微动。
钉输出的只有本片独占的那 41 个文件。给读者复跑用的命令(**不配对,不钉数**):

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent \
  $(ls notes/*.md | grep -v '/r11b-') | tail -4
```

失败数 314 → 3 这一条**不依赖**上面那个快照:314 处失败**全部**落在这 41 个文件里
(§2.1 的明细文件就是按文件分解的),其余历史 notes 本来就是 0 失败;
41 个文件现在剩 3 处,所以全语料也是 3 处。

### 2.4 按文件的前后分解

「原失败」= 该文件在 `data/r11b/notes-citation-backlog.txt` 里的条数;
「现失败」= 清理后同一文件的失败数;「OK 数」= 被机器逐行比对通过的引用数。

| 文件 | 原 MISMATCH / MISSING-FILE | 原失败 | 现失败 | OK 数(前 → 后) |
|---|---:|---:|---:|---|
| `notes/r2-22-credential-pool.md` | 3 / 25 | 28 | 0 | 15 → 43 |
| `notes/r6-40-mem0-holographic.md` | 0 / 24 | 24 | 0 | 1 → 25 |
| `notes/r6-30-hindsight-supermemory-retaindb.md` | 0 / 23 | 23 | 0 | 7 → 30 |
| `notes/r3-20-schema-output-toolsearch.md` | 3 / 18 | 21 | 0 | 4 → 25 |
| `notes/r4-40-computer-use.md` | 0 / 20 | 20 | 0 | 2 → 22 |
| `notes/r6-10-honcho.md` | 5 / 15 | 20 | 0 | 13 → 33 |
| `notes/r3-30-execute-code-mcp-client.md` | 2 / 16 | 18 | 0 | 4 → 22 |
| `notes/r3-10-approval-security.md` | 0 / 15 | 15 | 0 | 0 → 0 |
| `notes/r5-02-hermes-state-sessiondb.md` | 12 / 0 | 12 | 0 | 24 → 36 |
| `notes/r4-30-browser-automation.md` | 11 / 0 | 11 | 0 | 57 → 68 |
| `notes/r4-20-remote-backends-serverless.md` | 0 / 10 | 10 | 0 | 0 → 10 |
| `notes/r5-30-prompt-context-engineering.md` | 5 / 3 | 8 | 0 | 20 → 28 |
| `notes/r5-40-checkpoint-memory.md` | 7 / 0 | 7 | 0 | 17 → 24 |
| `notes/r7-raw-run-03-turnrunner.md` | 5 / 2 | 7 | 0 | 35 → 42 |
| `notes/r7-raw-run-12-watch-lease-cache.md` | 7 / 0 | 7 | 0 | 17 → 24 |
| `notes/r6-60-mcp-oauth-cleanup.md` | 3 / 3 | 6 | **3** | 15 → 18 |
| `notes/r7-raw-run-05-gwr-queue-busy.md` | 6 / 0 | 6 | 0 | 22 → 28 |
| `notes/r7-raw-session-py.md` | 6 / 0 | 6 | 0 | 38 → 44 |
| `notes/r7b-10-base-adapter-contract.md` | 5 / 1 | 6 | 0 | 6 → 12 |
| `notes/r7b-30-base-media-and-egress.md` | 6 / 0 | 6 | 0 | 1 → 6 |
| `notes/r7b-50-builtin-adapters.md` | 6 / 0 | 6 | 0 | 0 → 6 |
| `notes/r7b-60-relay-tunnel.md` | 5 / 0 | 5 | 0 | 3 → 8 |
| `notes/r4-01-environment-abstraction.md` | 0 / 4 | 4 | 0 | 0 → 4 |
| `notes/r5-20-context-compression.md` | 4 / 0 | 4 | 0 | 22 → 26 |
| `notes/r7-raw-run-02-config-media-watchdog.md` | 4 / 0 | 4 | 0 | 39 → 43 |
| `notes/r7b-20-base-first-layer-guard.md` | 3 / 1 | 4 | 0 | 2 → 6 |
| `notes/r5-01-state-schema-portability.md` | 2 / 1 | 3 | 0 | 3 → 6 |
| `notes/r5-10-fts5-session-search.md` | 3 / 0 | 3 | 0 | 25 → 28 |
| `notes/r7b-40-api-server.md` | 3 / 0 | 3 | 0 | 2 → 5 |
| `notes/r4-02-docker-local-terminal-process.md` | 0 / 2 | 2 | 0 | 0 → 2 |
| `notes/r4-50-patch-parser-file-state.md` | 0 / 2 | 2 | 0 | 0 → 2 |
| `notes/r6-20-openviking-byterover.md` | 0 / 2 | 2 | 0 | 3 → 5 |
| `notes/r7-raw-run-07-start-watchers.md` | 2 / 0 | 2 | 0 | 17 → 19 |
| `notes/r8d-02-coverage-audit.md` | 2 / 0 | 2 | 0 | 0 → 2 |
| `notes/r2-20-adapters.md` | 1 / 0 | 1 | 0 | 5 → 9 |
| `notes/r2-23-classify-retry-fallback-cache.md` | 1 / 0 | 1 | 0 | 9 → 10 |
| `notes/r6-01-loader-query-rewrite-optimize.md` | 0 / 1 | 1 | 0 | 1 → 2 |
| `notes/r7-raw-run-08-stop-profiles-busycmd.md` | 1 / 0 | 1 | 0 | 19 → 20 |
| `notes/r7-raw-run-09-handle-message.md` | 0 / 1 | 1 | 0 | 25 → 26 |
| `notes/r7b-95-tests.md` | 1 / 0 | 1 | 0 | 0 → 1 |
| `notes/r7c-raw-status.md` | 1 / 0 | 1 | 0 | 49 → 50 |
| **合计** | 125 / 189 | **314** | **3** | **522 → 820** |

`notes/r3-10-approval-security.md` 是唯一 OK 数没涨的文件(0 → 0),原因见 §4:
它的代码块整体不是逐字摘录,按制度改成了声明式非源码块,改用一次性逐行审计代替关卡。

---

## 3. 处置办法(按类)

### 3.1 MISSING-FILE(189 处):裸文件名补目录,**逐条以摘录内容确认目标文件**

189 处里绝大多数是裸文件名(`credential_pool.py:33`)。补目录不能"按最像的那个填"——
基线里 `__init__.py` 有 171 个候选、`base.py` 有 9 个。本片的判据是**内容**而不是相似度:

1. 取该锚点后面那个围栏块的首行;
2. 枚举基线里所有同基名的文件;
3. 只有**恰好一个**候选在**锚点那一行**(EXACT)、或在 ±40 行内(NEAR)出现该首行时,才自动改写。

按这条判据自动改写 **162 处**(EXACT-1 124 + NEAR-1 38)。NEAR-1 只改路径、**不动行号**,
把行号漂移留给下一步的 `--fix` 单独处理,两类改动因此各自可审。

判据判不出来的没有一条被"填最像的"。`base.py:374` 在 9 个同名候选里,只有下面这一个的邻近处有笔记那个块的首行:

`tools/environments/base.py:383-386 @ 863e313`

```python
    def __init__(
        self,
        exec_fn: Callable[[], tuple[str, int]],
        cancel_fn: Callable[[], None] | None = None,
```

同理 `__init__.py:1080` 在 171 个候选里只有 `plugins/memory/honcho/__init__.py` 命中。
剩下 27 处全部转人判,逐条见 §5。

### 3.2 MISMATCH(125 处):无歧义漂移交 `--fix`,其余人判

补完路径后重跑,`fixable`(邻近**恰好一处**命中)共 133 处,由 `--fix` 改写;
**改完立即不带 `--fix` 裸跑复核**,MISMATCH 从 163 降到 30。剩下 30 处人判,见 §3.4 与 §5。

`--fix` 的调用一律显式列出这 41 个文件,没有用过通配符——`--fix` 会写文件,
而本轮其他片正在写 `notes/r11b-*`。

### 3.3 BLOCK-DRIFT(51 处):清理**新暴露**出来的一类,全部按基线原文回抄

这是本片最值得写下来的一条。**清理前这 51 处一处都没报过**:
`BLOCK-DRIFT` 只在"块首行与锚点匹配之后"才计算,而这些块的锚点要么解析不到文件
(MISSING-FILE),要么首行就不匹配(MISMATCH)——**前一层失败把后一层检查挡住了**。
路径与行号一修好,它们立刻现形。

形态与 R8D 当年清 116 处时看到的一致:作者手抄代码时压行、截断、丢注释。样例:

`tools/code_execution_tool.py:1421-1428 @ 863e313`

```python
        rpc_thread = threading.Thread(
            target=propagate_context_to_thread(_rpc_server_loop),
            args=(
                server_sock, task_id, tool_call_log,
                tool_call_counter, max_tool_calls, sandbox_tools, stop_event, rpc_token,
            ),
            daemon=True,
        )
```

`notes/r3-30-execute-code-mcp-client.md` 原文把 `args=(` 那三行压成了两行
(`args=(server_sock, task_id, tool_call_log,` + 续行),读起来完全合理,但不是逐字。

修法是**对齐回抄**,不是整段替换:以锚点行为起点,逐行把笔记的块与基线对齐——
逐字命中就保留;笔记跳了段就补一个**独立成行**的 `...`(制度承认的声明式跳段标记);
笔记把多行压成一行、或截断了一行,就用基线那几行原文替换。
这样块的规模基本不变(51 块中最大 +6 行、最小 −4 行),而每一行都成了逐字。

### 3.4 人判的 30 处 MISMATCH:三种形态

| 形态 | 条数 | 例 | 处置 |
|---|---:|---|---|
| 锚点指**区域起点**,块实际起于区域中间 | 12 | `notes/r5-02-hermes-state-sessiondb.md` 写「`hermes_state.py:743-767`,节选」,块首行在 **747** | 保留区域说明,另起一行给块自己的锚点 `hermes_state.py:747-756` |
| 摘录**从半行开始**或截断半行 | 10 | 块首行 `` `firecrawl` is ``,而 `agent/browser_registry.py:19`:`   Browserbase as the older direct-credentials fallback). ``firecrawl`` is` | 按基线补齐整行 |
| 锚点**差一到几行** | 8 | `agent/prompt_builder.py:2187`:`    else:`(原写 2188,2188 是它下面那句注释) | 改行号 |

三类都**只动锚点或把摘录补回基线原文**,一次也没有反过来改摘录去迁就行号。

---

## 4. 单独一节:`notes/r3-10-approval-security.md` 的行号栏体例

这个文件 15 处失败全部同因,处置也与其它文件不同,单列。

### 4.1 现象

它的代码块是**带行号栏的摘要**:每行以自己的源码行号开头,块内跨段跳行。例如

`tools/approval.py:3754-3755 @ 863e313`

```python
    if _should_skip_container_guards(env_type, has_host_access=has_host_access):
        return {"approved": True, "message": None}
```

笔记里写成 `3754    if _should_skip_container_guards(...)` / `3755        return {...}`。
锚点又是裸文件名(`approval.py:3754`),于是 15 处全记 MISSING-FILE。

**补完路径并不能解决它**:补完之后块首行 `3754    if …` 与源码第 3754 行不相等,
MISSING-FILE 只会变成 MISMATCH——净失败数不变。所以必须对块本身表态。

### 4.2 表态前先做一次逐行审计(不靠印象)

把这些块的行号栏当作可校验的断言,逐行比对基线:

**R11C 片 C 改:脚本里原本写着字面的三反引号(`startswith('```')`),
而关卡识别 ```verify 块用的是 `NOFENCE = (?:(?!```).)*?` —— **正文里任何一个字面
三反引号都会被当成块的结尾**。于是这一块被截成半截脚本喂给 bash,报
`SyntaxError: unterminated string literal`;而它偏偏是一个「检查围栏块」的自查脚本,
非提到围栏不可。改法:不写字面反引号,改用 `chr(96) * 3` 构造,**语义完全相同**。
这是**关卡自身的形状缺陷**,不是作者写错 —— 见移交 `H-R11C-C-a`。**
*(本块下方本来就配了 ```text 块;正因为命令被截断,那次配对**从未成立过** ——
关卡把它记成一个未配对块,然后拿半截脚本去跑。改完之后它才第一次真的被比对。)*

```verify
cd /home/user/hermes-study && python3 - <<'PY'
import re
from pathlib import Path
REPO = Path("/home/user/hermes-agent")
GUT = re.compile(r"^(\d{1,6})\s+(.*)$")
FENCE = re.compile("^\\s*" + chr(96) * 3)   # R11C:不写字面围栏,见块前说明
note = Path("notes/r3-10-approval-security.md")
lines = note.read_text(encoding="utf-8").splitlines()
cur, tot, ok, diff = None, 0, 0, []
i = 0
while i < len(lines):
    if not FENCE.match(lines[i]):
        m = re.search(r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.py):\d+", lines[i])
        if m and (REPO / m.group(1)).is_file():
            cur = m.group(1)
        i += 1
        continue
    j = i + 1
    while j < len(lines) and not FENCE.match(lines[j]):
        g = GUT.match(lines[j])
        if g and cur:
            src = (REPO / cur).read_text(encoding="utf-8").splitlines()
            n = int(g.group(1))
            tot += 1
            if 1 <= n <= len(src) and " ".join(src[n-1].split()) == " ".join(g.group(2).split()):
                ok += 1
            else:
                diff.append(f"{cur}:{n}")
        j += 1
    i = j + 1
print(f"gutter-lines={tot} verbatim={ok} differing={len(diff)}")
print("differing:", " ".join(diff))
PY
```

```text
gutter-lines=103 verbatim=88 differing=15
differing: tools/approval.py:3224 tools/approval.py:3233 tools/approval.py:3258 tools/approval.py:2434 tools/url_safety.py:437 tools/url_safety.py:655 tools/url_safety.py:669 tools/url_safety.py:672 tools/threat_patterns.py:14 tools/threat_patterns.py:16 tools/threat_patterns.py:18 tools/write_approval.py:283 tools/write_approval.py:297 tools/write_approval.py:299 tools/write_approval.py:306
```

清理**前**这条命令给的是 `verbatim=87 differing=16`,多出的那一处是唯一一个**真错**(见 4.3)。

15 处剩余不一致按形态分类(逐条已核):

| 形态 | 条数 | 例 |
|---|---:|---|
| 行尾追加了中文旁注 | 4 | 笔记 `3224 if _is_cron_approval_context(): # cron_mode: deny/approve`,`tools/approval.py:3224`:`        if _is_cron_approval_context():` |
| 行内用 `…` 截断 | 3 | 笔记 `2434 "operation. Report the blocked operation to the user …"`,`tools/approval.py:2434`:`"operation. Report the blocked operation to the user and either "` |
| 多行调用压成一行 | 5 | 笔记 `655 def connect_tcp(self, host, port, ...):`,`tools/url_safety.py:655`:`    def connect_tcp(` |
| 英文 docstring 译成中文 | 3 | 笔记 `14 - "all" — 到处应用(经典注入 + exfil)`,`tools/threat_patterns.py:14`:`- ``"all"``  — applied everywhere (classic prompt injection, exfiltration)` |

**这 15 处全部是有意的渲染,不是抄错。** 行号栏本身 **102/103 准确**。

### 4.3 唯一的真错,已就地改正

`tools/url_safety.py:441-442 @ 863e313`

```python
        # Check the global toggle AFTER blocking metadata hostnames
        allow_all_private = _global_allow_private_urls()
```

笔记把 `allow_all_private = _global_allow_private_urls()` 标成了 **441**,实际在 **442**
(441 是它上面那句注释)。**原判**:该赋值在 441。**为什么撤**:与基线不符。
**依据**:上面的逐行审计 + 这段原文。已在 `notes/r3-10-approval-security.md` 就地改成 442。

### 4.4 处置与理由

1. **锚点补全路径**(15 处):`approval.py:3754` → `tools/approval.py:3754`。无争议,必须做。
2. **块改标 ```text**(15 块):按 CLAUDE.md 的三类块规则,```` ``` ```` 围栏的契约是
   "逐字源码摘录、**整块每一行**";带行号栏、带中文旁注、带压行与翻译的块**满足不了**这个契约。
   它**真的不是源码**,是源码的一种渲染,所以用**显式语言标记**声明(制度原话:
   "非源码围栏用显式语言标记而不是靠脚本'看着不像代码'来猜")。
3. 在文件开头写了「原判是什么、为什么撤、依据是什么」的更正节。

**为什么不选另外两条路**,写下来供主线推翻:

- **改写成逐字块**:这些块跨段取样,要合规就得拆成 40 个左右各自带锚点的子块,
  且必须删掉作者的中文旁注与中文译文——那是这份底稿主要的教学价值。代价远大于收益。
- **原样留着失败**:15 处失败会一直挂着,而它们并不是"证据不可信",
  逐行审计已经证明行号栏 102/103 准确。

**这不是"为了过关改成 ```text"**:改完它们进的是 UNCHECKED 桶,**计入分母、计入
「单文件 UNCHECKED ≥90%」提示**,不是无声通过;并且本片用一次性逐行审计
(103 行,而不是关卡原本只会比的 15 个块首行)把这个文件查得**比关卡更严**。
基线是钉死不动的,所以一次性审计与持续校验在效力上等价。
真正的修法建议见 §8 移交 **H-R11B-D-b**:让校验器认识行号栏这种块,
那样这个文件会从 15 条首行校验变成 103 行全校验。

---

## 5. 未决:剩下的 3 处,逐条点名

### 5.1 `notes/r6-60-mcp-oauth-cleanup.md`:3 处指向第三方 `mcp` SDK

| 锚点 | 现象 |
|---|---|
| `notes/r6-60-mcp-oauth-cleanup.md:58` 的 `mcp/client/auth/oauth2.py:66-69 @ mcp==1.28.1 site-packages` | 路径指向 pip 包 `mcp`,不在基线仓库里,校验器解析不到 → MISSING-FILE |
| `notes/r6-60-mcp-oauth-cleanup.md:67` 的 `mcp/client/auth/oauth2.py:337-345 @ mcp==1.28.1 site-packages` | 同上 |
| `notes/r6-60-mcp-oauth-cleanup.md:80` 的 `mcp/client/auth/oauth2.py:270-277 @ mcp==1.28.1 site-packages` | 同上 |

**留而不改的理由**:

1. **这三条引用是对的**。基线不 vendored 这个 SDK(`find . -type d -name mcp` 只找到
   `optional-skills/mcp` 与两处 `website/docs/.../skills/optional/mcp`,都不是 SDK)。
   本片拿测试 venv 里装着的 `mcp 1.28.1` 逐条核过:
   `/home/user/hermes-venv/lib/python3.11/site-packages/mcp/client/auth/oauth2.py`
   第 66-68 行是 PKCE 生成、第 337 行是 `state = secrets.token_urlsafe(32)`、
   第 270-277 行是 `_validate_resource_match` —— **与笔记里的摘录逐字一致**。
2. **关卡结构上够不到它**:`verify_citations.py` 的比对基准是钉死的基线仓库,
   没有"第三方依赖"这一档。
3. **能想到的三种绕法都是假声明**:标成 ```text 等于宣称"这不是源码"(它是);
   改成 `>` 引用块等于宣称"这是文档摘录或转述"(它不是);
   把路径写成解析不出锚点的形状,就掉进 CLAUDE.md 点名的那个"连分母都进不去"的状态,
   比 UNCHECKED 更隐蔽。

按制度"判不出来的宁可留着并点名",留下,并给出修法建议(§8 H-R11B-D-a):
笔记**已经**把 provenance 写在锚点后面了(`@ mcp==1.28.1 site-packages` 而不是 `@ 863e313`),
校验器只要读这个已经存在的声明即可 —— 与 `text/console/verify` 那一栏同一条原则:**声明,不靠嗅探**。

---

## 6. 改了但值得复核的 / 可能牵涉结论的,逐条点名

以下 5 条不是"行号漂了"那么简单,主线请复核。**本片一条结论都没有就地改写。**

### 6.1 ■ `notes/r4-01-environment-abstraction.md`:一段基线里不存在的 docstring 被当逐字摘录

**现象**:原文在 `base.py:374-382` 下贴了一段 docstring,开头是
`"""Adapt a blocking ``exec_fn() -> (stdout_text, returncode)`` into the`。
这段文字**在基线全仓不存在**。

搜索面:基线全部 `.py` 文件,模式 `Adapt a blocking`,无排除:

```verify
grep -rn "Adapt a blocking" --include=*.py /home/user/hermes-agent | wc -l
```

```text
0
```

真实的 docstring 是:

`tools/environments/base.py:374-381 @ 863e313`

```python
class _ThreadedProcessHandle:
    """Adapter for SDK backends (Modal, Daytona) that have no real subprocess.

    Wraps a blocking ``exec_fn() -> (output_str, exit_code)`` in a background
    thread and exposes a ProcessHandle-compatible interface.  An optional
    ``cancel_fn`` is invoked on ``kill()`` for backend-specific cancellation
    (e.g. Modal sandbox.terminate, Daytona sandbox.stop).
    """
```

**处置**:正文已按基线原文回抄,并就地写明原判/撤销理由/依据。
**结论实质不变**——真实 docstring 讲的是同一件事(把阻塞 `exec_fn` 包进后台线程、
暴露成 ProcessHandle 兼容接口、`cancel_fn` 挂到 `kill()`),该节叙述仍然成立。
**但这是证据完整性问题**:一段转述被当成逐字摘录贴了出来,正是 BLOCK-DRIFT 关卡要防的形态,
而它此前躲过关卡是因为锚点是裸文件名、先在 MISSING-FILE 那一层就失败了。

### 6.2 ▲ 归属改判 `notes/r4-30-browser-automation.md`:引文出自设计文档,不是模块 docstring

**现象**:原文写「supervisor 就是为堵这个洞而生:`tools/browser_supervisor.py:11`」,
其后的三行引文**逐字出自设计文档**,`.py` 侧一个字都没有。

搜索面:基线全部 `.py` 与 `.md`,模式 `Native JS dialogs`,无排除:

```verify
grep -rn "Native JS dialogs" --include=*.py --include=*.md /home/user/hermes-agent
```

```text
/home/user/hermes-agent/website/docs/developer-guide/browser-supervisor.md:11:1. **Native JS dialogs** (`alert`/`confirm`/`prompt`/`beforeunload`) block the
```

`.py` 与 `.md` 恰好都有第 11 行,是同号异文件的误锚。**处置**:锚点改为下面这一个,并就地写明。

`website/docs/developer-guide/browser-supervisor.md:11-13 @ 863e313`

```
1. **Native JS dialogs** (`alert`/`confirm`/`prompt`/`beforeunload`) block the
   page's JS thread. Without supervision, the agent has no way to know a
   dialog is open — subsequent tool calls hang or throw opaque errors.
```
**需要主线注意的实质**:这句话原本被当作**代码自述**采信;它其实是**作者自绘地图**的一部分,
按制度「文档与代码冲突以代码为准」,同一句话的证据等级不同。本片没有改动该节结论
(supervisor 的存在理由在代码行为上也成立),但把它当"代码说的"来引用是不对的。

### 6.3 ■ `notes/r6-10-honcho.md`:裸文件名**碰巧解析到了另一个真文件**

**现象**:锚点写 `cli.py:1113`,指的是 `plugins/memory/honcho/cli.py`;
而基线**仓库根真的有一个 `cli.py`**,于是校验器解析成了根上那个,报 MISMATCH 而不是 MISSING-FILE。

```verify
ls /home/user/hermes-agent/cli.py && grep -c 'h = f"{HOST}' /home/user/hermes-agent/cli.py
```

```text
/home/user/hermes-agent/cli.py
0
```

笔记要指的其实是下面这一行:

`plugins/memory/honcho/cli.py:1113-1114 @ 863e313`

```python
        h = f"{HOST}.{p.name}"
        results.append((p.name, h, hosts.get(h, {})))
```

**处置**:改成 `plugins/memory/honcho/cli.py:1113`。
**为什么单独点名**:这一条说明"裸文件名"的危害不止于"查不到"——它可以**查到错的那一个**,
而且报出来的失败类型会把人往错方向带。§7 的 1,334 个未解析锚点里,同型隐患无法用当前关卡发现。

### 6.4 `notes/r8d-02-coverage-audit.md`:引用的是**本学习仓库**的脚本,行号每轮都会漂

**现象**:该文引用 `scripts/assign_layers.py:162-163` / `:222-223`,而这个文件随各轮增补不断变长,
本轮实测同两条已经移到 `:307-308` / `:437-438`。基线是钉死的、本仓库的 `scripts/` 不是。

本轮实测这两行现在长这样:

`scripts/assign_layers.py:307-308`(**本学习仓库**,非基线)

```python
    ("agent/*.py", "L1", "UNCLAIMED"),
    ("agent/**/*.py", "L1", "UNCLAIMED"),
```

**处置**:改成当前行号,并在正文注明"该文件随各轮增补而移动,行号按 R11B 实测"。
**交主线定**:自引本仓库脚本的锚点要不要另立一套写法(例如只引符号不引行号)。见 §8 H-R11B-D-c。

### 6.5 `notes/r2-20-adapters.md`:一个压缩块被拆成了四个各自带锚点的块

**现象**:原文用**一个**块把 `determine_api_mode` 从 671 行到函数尾压成 13 行,
去掉了 docstring 与两段注释,行尾加了 `# 1. host 强制` 这类中文标注,
签名还被去掉了类型标注(写成 `def determine_api_mode(provider, base_url="", model="") -> str:`)。

**处置**:按制度「摘录要跳段时,优先拆成两个各自带锚点的块」拆成四块,每块逐字对齐基线;
中文的五级标注移到块外散文。**结论实质不变**——五级顺序本来就是该函数 docstring 自己写的:

`hermes_cli/providers.py:672-679 @ 863e313`

```python
    """Determine the API mode (wire protocol) for a provider/endpoint.

    Resolution order:
      1. Host-mandated mode (special endpoints that only accept one protocol).
      2. Nous Portal dual-wire (model-derived; overlay alone is openai_chat).
      3. Known provider → transport → TRANSPORT_TO_API_MODE.
      4. Direct provider checks (bedrock).
      5. Default: 'chat_completions'.
```
这是本片唯一一处**结构性重写**,
所以单独点名请主线过目。

### 6.6 「改了但不确定」清单(主线复核用)

先说一条能大幅缩小怀疑面的事实:清理后这 41 个文件 **`BLOCK-DRIFT=0`**,
即**每个围栏块的每一行**都逐字对上了基线。所以"锚点被我挪到了错的地方"这种错,
在多行块上是**不可能**悄悄留下的——挪错了整块就会 drift。
下面几处是**判断**而非机械改写,不受这条保护,请主线过目:

| # | 改动 | 不确定在哪 | 我的依据 |
|---|---|---|---|
| 1 | `notes/r3-10-approval-security.md` 15 个块由 ```python 改标 ```text(§4.4) | 这是全片最可能被推翻的一条:它把 15 条引用从"失败"移进 UNCHECKED,形式上像"为了过关" | 逐行审计 103 行、行号栏 102/103 准确(§4.2 可重跑);块确实不是逐字源码;并给出了让它变成 103 行全校验的修法(H-R11B-D-b) |
| 2 | `notes/r7b-30-base-media-and-egress.md:20` 的 `gateway/platforms/base.py:1451-1527` 下那张判定顺序表由 ``` 改标 ```text | 同上一类的小号版本 | 该块是中文步骤表 + 右侧 `base.py:NNNN` 位置标注,不是源码 |
| 3 | `notes/r2-20-adapters.md` 把一个压缩块拆成四个各自带锚点的块(§6.5) | 本片唯一一处**结构性重写**,改变了该节的排版形态 | 制度原话「摘录要跳段时,优先拆成两个各自带锚点的块」;拆后四块全部逐字通过 |
| 4 | `notes/r8d-02-coverage-audit.md` 的两处行号改到 `:307-308` / `:437-438`(§6.4) | 指向**本仓库**的 `scripts/assign_layers.py`,下一轮几乎必然再漂 | 本轮实测;已在正文注明会移动,并作为 H-R11B-D-c 交出 |
| 5 | `notes/r6-60-mcp-oauth-cleanup.md` 的 3 处**不改**(§5.1) | "留着"也是一个判断:代价是失败数停在 3 而不是 0 | 三条引用经 venv 内 `mcp 1.28.1` 逐字核过;三种绕法都是假声明 |

多候选行号的挑选(`try:`、`while True:`、`conn.execute(` 这类在文件里遍地都是的首行)共 9 处,
全部由**多行块整块比对**背书(最短的一处是 `hermes_state.py:2992-2994` 的 3 行,
而 `ON CONFLICT(id) DO UPDATE SET` 在该文件里只出现一次),不列入本表。

---

## 7. 要如实说的覆盖面:这 41 个文件里还有 1,334 个锚点解析不到

失败数降到 3,不代表"裸文件名"这个病治好了。当前关卡只在**锚点后紧跟围栏块**时才判 MISSING-FILE;
写在散文里、表格里的裸文件名一律记 UNCHECKED / TABLE-UNCHECKED,**不是失败**。

```verify
cd /home/user/hermes-study && python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
import verify_citations as vc
REPO = Path("/home/user/hermes-agent"); STUDY = Path("/home/user/hermes-study")
def resolve(p):
    t = REPO / p
    return t if t.is_file() or not (STUDY / p).is_file() else STUDY / p
files = sorted({"notes/" + l.split()[1].split(":")[0]
                for l in open("data/r11b/notes-citation-backlog.txt")})
tot = bad = 0
for f in files:
    for line in Path(f).read_text(encoding="utf-8").splitlines():
        for m in vc.citations(line, resolve):
            tot += 1
            bad += 0 if resolve(m.group("path")).is_file() else 1
print(f"anchors={tot} unresolvable={bad} ({bad*100.0/tot:.1f}%)")
PY
```

```text
anchors=3314 unresolvable=1334 (40.3%)
```

出现最多的裸名依次是 `run.py`(220)、`__init__.py`(150)、`base.py`(81)、`approval.py`(49)、
`url_safety.py`(43)。其中 `__init__.py` 在基线有 171 个同名候选、`base.py` 有 9 个
——对一个"不看源码"的读者,这些锚点不是引用,是谜题;§6.3 更证明它们还可能指错文件。

**本片没有动这 1,334 个**:它们不在 314 处积压里,批量改写又缺少"块首行"这种内容判据
(散文锚点没有块可以对),按"确认不了的不要瞎填"留下。交主线定优先级,见 §8 H-R11B-D-d。

---

## 8. 移交

| 编号 | 锚点 + 现象 | 建议去向 |
|---|---|---|
| **H-R11B-D-a** | `notes/r6-60-mcp-oauth-cleanup.md:58` 的 `mcp/client/auth/oauth2.py:66-69 @ mcp==1.28.1 site-packages`:锚点指向第三方 pip 包,基线里没有该文件,校验器恒记 MISSING-FILE(3 处)。笔记**已**用 ` @ mcp==1.28.1 site-packages` 声明了非基线出处,校验器不读它 | 给 `scripts/verify_citations.py` 加一档:锚点的 ` @ ` 后缀不是基线 sha 时记 `NON-BASELINE`(计入分母、不阻断),沿用「声明,不靠嗅探」 |
| **H-R11B-D-b** | `notes/r3-10-approval-security.md:56` 的 `tools/approval.py:3754`:该文 15 个块是「每行以自己的行号开头」的行号栏体例,校验器无法比对,本片改标 ```text;实测行号栏 **102/103 准确**(§4.2 可重跑) | 让校验器识别行号栏块(整块每行 `^\d+\s`),按每行自己声明的行号比对。落地后该文从"15 个块首行"变成"103 行全校验",是**净增**校验面 |
| **H-R11B-D-c** | `notes/r8d-02-coverage-audit.md:39` 的 `scripts/assign_layers.py:307-308`:自引**本仓库**脚本,该文件每轮增补都在变长,行号必然再漂(本轮已从 162 漂到 307) | 定一条自引写法(只引符号名不引行号,或把自引锚点排除出行号校验) |
| **H-R11B-D-d** | `notes/r7-raw-session-py.md` 等 41 个文件里仍有 **1,334 / 3,314(40.3%)** 个锚点路径无法从仓库根解析(`run.py` 220、`__init__.py` 150、`base.py` 81);`notes/r6-10-honcho.md:677` 的 `plugins/memory/honcho/cli.py:1113` 证明裸名还会**碰巧解析到根上另一个真文件** | 排优先级:先补"有同名歧义"的那批(`__init__.py`/`base.py`),散文锚点缺内容判据,需人工或按小节上下文批处理 |
| **H-R11B-D-e** | `notes/r4-01-environment-abstraction.md:38` 的 `tools/environments/base.py:374`:原文贴的 docstring **基线全仓不存在**(§6.1 负结论搜索面已给),是转述被当逐字摘录;`notes/r4-30-browser-automation.md` 另有一处把设计文档的话当成模块 docstring 引用 | 主线定案:是否作为"证据完整性"类发现单独记账(本片已按基线原文回抄,结论未动) |
| **H-R11B-D-f** | 本片清理**新暴露** 51 处 `BLOCK-DRIFT`,清理前一处都没报过——因为 MISSING-FILE / MISMATCH 在前一层就把它挡住了(§3.3) | 记录为关卡性质:**失败是分层的,修好上层会长出下层**。片 C 对 `chapters/` 做同样的事时应预期同一现象 |

---

## 9. 本底稿自身的可校验比例(如实说)

本文件的可校验比例低于 70% 下限,读数见下面这条命令。原因是结构性的,
写在这里而不是想办法凑高:

UNCHECKED 的绝大多数,是本文**当作"病灶样本"引用的那些坏锚点本身**(散见 §3.1、§4.1、
§6.1–6.4)。它们**按定义就解析不到、或指向错的文件**——那正是本文要讲的东西;
给一个"错的锚点"配一个能通过校验的代码块,在语义上是自相矛盾的。
其余几处是散文里"应该改成这个"的正确写法,其逐字块贴在同节别处、不与它相邻。

凡是有**正确**目标可指的地方,本文都补了逐字块(§3.1、§6.2、§6.3、§6.4、§6.5)。
这个数请按"一份讲坏锚点的底稿"来读,并入当轮 notes 合并统计时也请带上这条说明。

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent \
  notes/r11b-raw-notes-citation-cleanup.md | tail -4
```

```text
citations=21  OK=10  UNCHECKED=11
可校验比例 OK/21 = 47.6%  << 低于 70% 下限
table_anchors=17  OK=5  UNCHECKED=12   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
OK: every code-block-backed citation matches the baseline
```

凡是有**正确**目标可指的地方,本文都补了逐字块(§3.1、§6.2、§6.3、§6.4、§6.5),
所以 OK 数从 5 提到了 10。这个数请按"一份讲坏锚点的底稿"来读,
并入当轮 notes 合并统计时也请带上这条说明。

---

## 10. 边界与自查

- **基线只读**:全程未写基线。收工实测 `git -C /home/user/hermes-agent status --porcelain` 输出为空,
  `HEAD` 仍是 `863e31318553cda8ad61df681d08175364d4164b`。
- **未改 `scripts/`**,未装任何包(venv / apt / npm / pip 全未动)。
- **未碰 `notes/r11b-*.md`**;所有 `verify_citations.py` 调用(含 `--fix`)都显式列文件,
  未用过 `notes/*.md` 通配符。
- 本片修改的文件 = `data/r11b/notes-citation-backlog.txt` 里出现的那 41 个 + 本底稿,
  一个不多一个不少。收工时把 `git status` 里 `notes/` 下的改动清单与那 41 个求差,**差集为空**
  (`chapters/*` 的改动是片 C 的,不在本片名下)。
