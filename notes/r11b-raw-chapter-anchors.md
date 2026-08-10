# r11b 底稿 · 片 C —— 六章锚点排版清账(结清 H-R8D-g)

> 溯源约定:`路径:行号 @ 863e313` 指基线 commit `863e31318` 下 hermes-agent 仓库根的相对路径与行号。
> 本底稿记录的是**对本学习仓库六份成品章的改动**,以及改动**暴露出的基线引用缺陷**。

---

## 0. 一句话

六章锚点全部改成"单独成行、置于块前",**160 条从未被比对过的引用第一次进入校验,当场暴露 12 处真缺陷**。

---

## 1. 任务与前提

移交项 H-R8D-g 的原文:

`reports/round-8d-cli-completion.md:430`

> | **H-R8D-g** | R11B | `chapters/r2-*.md`、`r4-*`、`r5-*`、`r6-*`、`r7-*`、`r7b-*` 六章 | 校验器排版提示逐章点名:UNCHECKED 占比 ≥90%,拉低全量可校验比例到 68.5% |

派工书据此把病因描述为"锚点写在代码块之后并用散文隔开,于是每一条引用都配不上块、全部记 UNCHECKED"。
**这个描述只对六章中的一章成立**,详见 §2。

清理前读数已复现,与派工书给的数字**逐字一致**(复现命令与逐字输出见 §3——
清理前的数要用 `git show af60491:` 把旧版取到临时目录再跑,因为工作区已被本轮改过)。
> **R11B 主线更正**:这三条命令原本写的是 `git show HEAD:`。**片 C 收工时这是对的**
> (改动尚未提交,`HEAD` 就是清理前),但**本轮 commit 一落,`HEAD` 就变成了清理后**,
> 三条命令当场从"取旧版"变成"取新版",证据命令关卡随即判 `differing=3`。
> 已钉到 `af60491`(R11A 合入 main 的那条 commit,即本轮开工时的状态)。
> **这是本轮第三次撞上同一个物种:一条量"清理前"的命令,不能钉在一个会移动的引用上。**

---

## 2. 一处需要更正的前提:移交项对病因的描述只对了六分之一

**H-R8D-g 把六章一律描述成"锚点写在代码块之后"。实测:只有 `r7b` 是这个形态。**
另外五章记 UNCHECKED 的那些锚点是**散文里的括号内联引用**,后面跟的是下一段散文——
它们**压根没有配过源码块**,所以不存在"块被写在锚点前面"这回事
(这五章加起来只有 7 条引用原本就配好了块,见下面探针的"清理前 OK"一栏)。
两种形态在校验器眼里都记 UNCHECKED,但**修法完全不同**:

| 形态 | 哪几章 | 修法 | 工作量 |
|---|---|---|---|
| 块在前、锚点在后 | `r7b`(20 处) | **机械搬运**:把锚点行提到块前 | 一次脚本转换 |
| 无块,纯散文内联锚点 | `r2` `r4` `r5` `r6` `r7`(清理前合计 124 处 UNCHECKED) | **逐条判断**:该配摘录的回基线抄一段,该留散文的留散文 | 逐条回读基线 |

**用两个数一起看才说得清**:①「块后锚点」的处数(整行就是一个括号包着的锚点、紧跟在闭合围栏之后
——这正是我用脚本机械搬运的那个形状);②清理前该章**已经**配对成功(OK)的引用数。
`r7b` 的 20 处全在 ①;其余五章 ① 全是 0,而 ② 也只有个位数,说明它们的锚点根本没有块可配。

探针用 `chr(96)*3` 拼出围栏标记而不是直接写三个反引号——**直接写会把这个 `verify` 块自己截断**。
原因在配对正则里:命令体那一段 `NOFENCE` 明令不许出现围栏。

`scripts/verify_evidence_commands.py:102`

```python
PAIR = re.compile(r"```verify\n(?P<cmd>" + NOFENCE + r")```[ \t]*\n\s*```text\n"
```

(这个坑是本轮实测踩到的:初版探针直接写了三个反引号,heredoc 被截断,
探针**跑出了一组全 0 的假数字**,是 `verify_evidence_commands.py` 重跑比对时当场抓住的——
正是「shell 命令即证据」这条规矩存在的理由。)

```verify
cd /home/user/hermes-study && python3 - <<'PY'
import re, subprocess, sys
sys.path.insert(0,'scripts')
import verify_citations as vc
from pathlib import Path
FENCE=re.compile(r'^\s*' + re.escape(chr(96)*3))
BQ=chr(96)
# 整行 = （`路径:行号 @ sha`）——机械可搬运的那个形状
ANCHOR_ONLY=re.compile(r'^[（(]\s*' + BQ + r'[A-Za-z0-9_.][^' + BQ + r']*:\d+(?:-\d+)?'
                       r'(?:\s*@\s*[0-9a-f]{7,40})?' + BQ + r'\s*[)）]\s*$')
for f in ['r2-turn-loop-and-model-access','r4-execution-environments',
          'r5-session-state-and-persistence','r6-memory-provider-ecosystem',
          'r7-gateway-session-core','r7b-platform-integration']:
    src=subprocess.run(['git','show','af60491:chapters/%s.md'%f],capture_output=True,text=True).stdout
    lines=src.splitlines(); i=0; n=0
    while i<len(lines):
        if FENCE.match(lines[i]):
            j=i+1
            while j<len(lines) and not FENCE.match(lines[j]): j+=1
            k=j+1
            while k<len(lines) and not lines[k].strip(): k+=1
            if k<len(lines) and ANCHOR_ONLY.match(lines[k]): n+=1
            i=j+1; continue
        i+=1
    tmp=Path('/tmp/_r11bc_%s.md'%f); tmp.write_text(src)
    ok=sum(1 for st,_ in vc.check_note(Path('/home/user/hermes-agent'), tmp) if st=='OK')
    tmp.unlink()
    print('%-34s 块后锚点 %2d 处   清理前 OK %d' % (f, n, ok))
PY
```

```text
r2-turn-loop-and-model-access      块后锚点  0 处   清理前 OK 0
r4-execution-environments          块后锚点  0 处   清理前 OK 4
r5-session-state-and-persistence   块后锚点  0 处   清理前 OK 0
r6-memory-provider-ecosystem       块后锚点  0 处   清理前 OK 1
r7-gateway-session-core            块后锚点  0 处   清理前 OK 2
r7b-platform-integration           块后锚点 20 处   清理前 OK 3
```

**这条更正对下一轮有实际价值**:H-R8D-g 的标题("锚点排版")会让人以为这是一次机械搬运;
真实工作量的六分之五是"给一条没有摘录的断言补一段逐字摘录",那需要逐条回读基线。
派工书里"必然暴露真漂移"那句判断因此**低估了**:纯散文锚点从来没有摘录可比,
所以它们暴露的不是"块和行号对不上",而是"这条断言到底指向哪一行"——只能靠人核。

---

## 3. 逐章前后读数

**清理前**(用 `git show af60491:` 取六章旧版,单独跑一遍):

```verify
cd /home/user/hermes-study && D=$(mktemp -d) && mkdir -p "$D/chapters" && \
for f in r2-turn-loop-and-model-access r4-execution-environments \
         r5-session-state-and-persistence r6-memory-provider-ecosystem \
         r7-gateway-session-core r7b-platform-integration; do \
  git show af60491:chapters/$f.md > "$D/chapters/$f.md"; done && \
cd "$D" && python3 /home/user/hermes-study/scripts/verify_citations.py \
  /home/user/hermes-agent chapters/*.md 2>&1 | grep -E 'UNCHECKED [0-9]+/|^citations|^可校验'
```

```text
      - chapters/r2-turn-loop-and-model-access.md: UNCHECKED 21/21 = 100.0%
      - chapters/r4-execution-environments.md: UNCHECKED 36/40 = 90.0%
      - chapters/r5-session-state-and-persistence.md: UNCHECKED 23/23 = 100.0%
      - chapters/r6-memory-provider-ecosystem.md: UNCHECKED 13/14 = 92.9%
      - chapters/r7-gateway-session-core.md: UNCHECKED 31/33 = 93.9%
      - chapters/r7b-platform-integration.md: UNCHECKED 36/39 = 92.3%
citations=170  OK=10  UNCHECKED=160
可校验比例 OK/170 = 5.9%  << 低于 70% 下限
```

**清理后**:

```verify
cd /home/user/hermes-study && python3 - <<'PY'
import sys; sys.path.insert(0,'scripts')
import verify_citations as vc
from pathlib import Path
for f in ['r2-turn-loop-and-model-access','r4-execution-environments',
          'r5-session-state-and-persistence','r6-memory-provider-ecosystem',
          'r7-gateway-session-core','r7b-platform-integration']:
    c={}
    for st,_ in vc.check_note(Path('/home/user/hermes-agent'), Path('chapters/%s.md'%f)):
        if st.startswith('TABLE-') or st=='BLOCK-DRIFT': continue
        c[st]=c.get(st,0)+1
    n=sum(c.values()); u=c.get('UNCHECKED',0)
    print('%-49s UNCHECKED %2d/%-3d = %5.1f%%' % (f+'.md', u, n, u/n*100))
PY
```

```text
r2-turn-loop-and-model-access.md                  UNCHECKED  1/28  =   3.6%
r4-execution-environments.md                      UNCHECKED 12/47  =  25.5%
r5-session-state-and-persistence.md               UNCHECKED  7/30  =  23.3%
r6-memory-provider-ecosystem.md                   UNCHECKED  4/18  =  22.2%
r7-gateway-session-core.md                        UNCHECKED 13/40  =  32.5%
r7b-platform-integration.md                       UNCHECKED  9/40  =  22.5%
```

汇总成表(读数栏 = UNCHECKED / citations):

| 章 | 清理前 | 清理后 | 该章 OK 从 → 到 |
|---|---|---|---|
| `chapters/r2-turn-loop-and-model-access.md` | 21/21 = 100.0% | 1/28 = 3.6% | 0 → 27 |
| `chapters/r4-execution-environments.md` | 36/40 = 90.0% | 12/47 = 25.5% | 4 → 35 |
| `chapters/r5-session-state-and-persistence.md` | 23/23 = 100.0% | 7/30 = 23.3% | 0 → 23 |
| `chapters/r6-memory-provider-ecosystem.md` | 13/14 = 92.9% | 4/18 = 22.2% | 1 → 14 |
| `chapters/r7-gateway-session-core.md` | 31/33 = 93.9% | 13/40 = 32.5% | 2 → 27 |
| `chapters/r7b-platform-integration.md` | 36/39 = 92.3% | 9/40 = 22.5% | 3 → 31 |
| **六章合计** | **160/170 = 94.1%** | **46/203 = 22.7%** | **10 → 157** |

**全 `chapters/` 合并可校验比例**:

清理前(派工书给的起点,与我复现一致):`citations=441 OK=234 UNCHECKED=207`,**53.1%**。
清理后(本片收工时刻实测):`citations=479 OK=386 UNCHECKED=93`,**80.6%**——**+27.5 个百分点**。
六章全部退出「疑似锚点排版不合规」名单,该次运行**不再打印那条 HINT**。

命令如下。**它故意不配 ```text 块**(记 unpaired,按规则不失败):

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py \
  /home/user/hermes-agent chapters/*.md 2>&1 | tail -4
```

*为什么这一条不钉输出:`chapters/*.md` 是**通配符**,而本轮其它片正在并发往 `chapters/` 里加章
——我写完这一段之后主线就新增了 `chapters/r11b-the-unwritten-layer.md`(5 条引用),
全量数当场从 474 变成 479。**钉一个会被别人合法改动弄错的数,等于给下一次关卡运行埋一颗雷**;
按 CLAUDE.md 的原话,"一条重跑给出相反结果的命令比不写更糟"。
六章自己的数不受这个影响(只有本片改那六个文件),所以上面逐章那两条是钉了输出的。*

*为什么 citations 会从 441 涨到 479:一部分断言原先只有一个锚点、现在拆成"整段区域指路 + 逐字摘录"
两个锚点,分母因此变大;另有 5 条来自并发新增的那一章。这一点必须说清,
否则 OK 的涨幅会被误读成纯增益。*

---

## 4. 本次暴露的真缺陷:12 处,全在 `r7b`

**关键事实:12 处缺陷全部来自 `r7b` —— 也就是唯一"块已经在、只是锚点放错位置"的那一章。**
另外五章原本无块,新配的摘录是本轮现抄的,所以不可能"暴露"旧缺陷。
**这正好说明这类缺陷的分布规律:有块而不被校验的地方才会积压错误;没有块的地方积压的是"没有证据"。**

### 4.1 六处纯行号漂移(`--fix` 处理,已裸跑复核)

下表**左栏是章里原来写错的行号**(故意不带摘录,免得校验器拿错的行号去比对),
**右栏是改正后的锚点 + 它那一行的逐字原文**(这一栏受 R9B 表格锚点校验管辖):

| # | 章内原写 | 改正后(锚点 + 逐字摘录) |
|---|---|---|
| 1 | base.py 第 6324 行 | `gateway/platforms/base.py:6323`:`# Spawn a fresh task for the pending message instead of` |
| 2 | base.py 第 6309 行 | `gateway/platforms/base.py:6310`:`# Keep the _active_sessions entry live across the turn chain` |
| 3 | base.py 第 6497 行 | `gateway/platforms/base.py:6498`:`Release-then-conditional-delete is the #48300 fix: when a concurrent` |
| 4 | api_server.py 第 1269 行 | `gateway/platforms/api_server.py:1268`:`"""Derive a stable session ID from the conversation's first user message.` |
| 5 | api_server.py 第 6991 行 | `gateway/platforms/api_server.py:6992`:`# transient blip — the key will not become valid on its own. A` |
| 6 | base.py 第 1154 行 | `gateway/platforms/base.py:1155`:`# Off by default — symmetric with inbound (we accept any document type the` |

**六处全是差一行,而且有三处(#3 #4 #6)原锚点正好落在一个空行上。**
"起始行是空行"是一个**零成本的漂移嗅探信号**——我在动手改排版**之前**就用它扫过全语料六章,
当时命中 4 处,其中 3 处在这里被校验器独立确认。第 4 处不是漂移——`r4` 引的
`tools/computer_use/backend.py:73-80`,它的 `:73` 确实是 docstring 首行之后的那个空行:

`tools/computer_use/backend.py:72-74 @ 863e313`

```python
    """Result of any action (click / type / scroll / drag / key / wait).

    Beyond the transport-level ``ok`` flag, this carries cua-driver's
```

正文引的是这段 docstring 的**正文**,所以章里改成 `:74-80` 并配了逐字摘录。

复现这个嗅探(对**清理前**的六章跑):

```verify
cd /home/user/hermes-study && D=$(mktemp -d) && mkdir -p "$D/chapters" && \
for f in r2-turn-loop-and-model-access r4-execution-environments \
         r5-session-state-and-persistence r6-memory-provider-ecosystem \
         r7-gateway-session-core r7b-platform-integration; do \
  git show af60491:chapters/$f.md > "$D/chapters/$f.md"; done && \
python3 - "$D" <<'PY'
import re, sys
sys.path.insert(0,'/home/user/hermes-study/scripts')
import verify_citations as vc
from pathlib import Path
REPO=Path('/home/user/hermes-agent'); D=Path(sys.argv[1])
TRIVIAL=re.compile(r"^[\s)\]},:'\"]*$")
def resolve(p):
    t=REPO/p
    return t if t.is_file() else Path('/home/user/hermes-study')/p
for f in sorted((D/'chapters').glob('*.md')):
    lines=f.read_text().splitlines(); i=0
    while i<len(lines):
        line=lines[i]
        if vc.FENCE.match(line):
            i+=1
            while i<len(lines) and not vc.FENCE.match(lines[i]): i+=1
            i+=1; continue
        if vc.QUOTE.match(line):
            while i<len(lines) and vc.QUOTE.match(lines[i]): i+=1
            continue
        if vc.is_table_row(line): i+=1; continue
        for m in vc.citations(line, resolve):
            t=resolve(m.group('path'))
            if not t.is_file(): continue
            src=vc.source_lines(t); s=int(m.group('start'))
            if s<=len(src) and TRIVIAL.match(src[s-1]):
                print('%s:%d  %s  起始行无内容' % (f.name, i+1, m.group(0)))
        i+=1
PY
```

```text
r4-execution-environments.md:414  tools/computer_use/backend.py:73-80  起始行无内容
r5-session-state-and-persistence.md:333  tools/checkpoint_manager.py:1-12  起始行无内容
r7b-platform-integration.md:332  gateway/platforms/base.py:6497-6506  起始行无内容
r7b-platform-integration.md:380  gateway/platforms/api_server.py:1269-1279  起始行无内容
```

`r5` 的那条同理,不是漂移——`tools/checkpoint_manager.py:1-12` 的 `:1` 是模块 docstring 的那行裸引号:

`tools/checkpoint_manager.py:1-3 @ 863e313`

```python
"""
Checkpoint Manager — Transparent filesystem snapshots via a single shared
shadow git store.
```

章里改成了引 `:2-11` 的正文段。

### 4.2 六处摘录与基线**实质不符**(不是行号漂,是抄错/抄漏)

这一类是本次清理最重要的产出:**它们全部长得像逐字引用,而且此前全部"关卡绿灯"**。
逐条点名,写清原文、基线、以及为什么判为抄错而非漂移。

---

**(a) `gateway/platforms/base.py` 的 `utf16_len` docstring —— 凭空补了一个 `"""`,对源码作了假声明**

- **原文**(章里的摘录,末三行):
  ```text
      though Python's ``len()`` counts them as one.
      """
      return len(s.encode("utf-16-le")) // 2
  ```
- **基线**:`though Python's ``len()`` counts them as one.` 之后是**空行**,
  docstring 还有一段 `Ported from nearai/ironclaw#2304 …` 才收尾。

`gateway/platforms/base.py:197-202 @ 863e313`

```python
    though Python's ``len()`` counts them as one.

    Ported from nearai/ironclaw#2304 which discovered the same discrepancy in
    Rust's ``chars().count()``.
    """
    return len(s.encode("utf-16-le")) // 2
```

- **为什么是抄错不是漂移**:整块的**首行和末行都在正确位置**(`:190` 和 `:202`),
  只有中间少了两行正文、并把 `"""` 提前。行号一个都没错,**错的是内容**。
  漂移会让整块整体偏移,这里没有偏移。
- **判为"假声明"**:被删掉的正是"这段实现是从 nearai/ironclaw#2304 移植来的"这一句——
  它恰好是本章讲"UTF-16 码元"那个故事的**出处**。摘录读起来像完整 docstring,
  实际抹掉了它的来源。这与 R8D 清理时发现的那**唯一 1 处**假声明是同一形态。
- **处置**:按基线补回两行正文,`"""` 归位。

---

**(b) `gateway/platforms/base.py` 的 drain 注释 —— `# ... Two agents on one`,带前后缀的伪省略标记**

- **原文**:
  ```text
                  # and only CLEAR the interrupt Event — do NOT delete the entry.
                  # ... Two agents on one
                  # session_key = duplicate responses, duplicate tool calls.
  ```
- **基线** `:6312-6315` 是四行完整因果说明,`Two agents on one` 只是第四行的行尾。

`gateway/platforms/base.py:6312-6316 @ 863e313`

```python
                # If we deleted here, a concurrent inbound message arriving
                # during the awaits below would pass the Level-1 guard, spawn
                # its own _process_message_background, and run simultaneously
                # with the recursive drain below.  Two agents on one
                # session_key = duplicate responses, duplicate tool calls.
```

- **为什么是抄错不是漂移**:`# ... Two agents on one` 这一行**在基线里根本不存在**——
  它是作者把 `...` 当省略号、又把下一段的行尾接在后面**拼出来的一行**。
  CLAUDE.md 明写这类"带前后缀的省略标记"是"历史积压里最隐蔽的一类":
  它既不逐字,也**不是**合法的跳段声明(`ELISION` 只认**整行**是 `...`),
  于是 BLOCK-DRIFT 会从这一行开始一路报错——但在锚点写在块后的排版下,**它一次都没被读到过**。
- **处置**:按基线补全 `:6312-6316`,并把锚点区间同步改成 `:6310-6317`。

---

**(c) `gateway/platforms/base.py` 的 `_cleanup_finished_session_task` docstring —— 句子被从中间截断**

- **原文**末行:`never be healed — a permanent session deadlock.`(句号收尾,读起来是完整的)
- **基线**同一行:`never be healed — a permanent session deadlock. Keeping the done-task`,
  其后还有两行讲**修法**,再加一个 `"""`。

`gateway/platforms/base.py:6504-6507 @ 863e313`

```python
        never be healed — a permanent session deadlock. Keeping the done-task
        entry when the guard survives lets the on-entry self-heal detect the
        stale lock and clear it on the next inbound message.
        """
```

- **为什么是抄错不是漂移**:摘录**在一行中间停住并自己补了句号**,
  于是把"问题描述 + 修法"截成只剩"问题描述"。行号对(修完 4.1 的差一行之后),内容缺半段。
  这一处最能说明为什么 BLOCK-DRIFT 必须**逐行**比对:被删掉的恰好是这段注释的**结论**。
- **处置**:按基线补全到 `:6507`。

---

**(d) `gateway/platforms/api_server.py` 的 chokepoint docstring —— 同型截断,删掉的是断言的后半句**

- **原文**末行:`` ``async_delivery`` parameter to get wrong ``
- **基线**:`` ``async_delivery`` parameter to get wrong; the stateless HTTP path can `` + 下一行
  `never wake the agent after the turn ends, on ANY route.`

`gateway/platforms/api_server.py:5938-5939 @ 863e313`

```python
        ``async_delivery`` parameter to get wrong; the stateless HTTP path can
        never wake the agent after the turn ends, on ANY route.
```

- **为什么是抄错不是漂移**:与 (c) 同形——半行截断。被删掉的 "on ANY route" 正是
  "让错误状态不可表达"这条原则的**强度声明**,章里的可迁移原则依赖它。
- **处置**:补全,锚点区间同步为 `:5933-5939`。

---

**(e) `gateway/platforms/api_server.py` 的 #38803 注释 —— 同型截断**

- **原文**末行:`# the whole gateway down).`
- **基线**:`# the whole gateway down). Non-retryable drops it from the` + 后续三行
  (讲它和端口冲突守卫同待遇、以及守卫已在上面记过日志)。
- **为什么是抄错不是漂移**:同 (c)(d)。摘录停在括号收尾处,看起来是完整句。
- **处置**:补全到 `:7001`,锚点区间同步。

---

**(f) 三处"从一行中间开始抄"(`not found within ±40`,校验器判不出位置)**

这三处的首行在基线里**根本不是一整行**,而是某一行的后半段,所以 `±40` 窗口内怎么找都找不到:

| 章内锚点(原) | 摘录首行(原) | 基线真实那一行 | 真实位置 |
|---|---|---|---|
| `gateway/relay/ws_transport.py:833` | `# Accumulate them keyed by the descriptor's own platform so` | `gateway/relay/ws_transport.py:833`:`# identity. Accumulate them keyed by the descriptor's own platform so` | 少抄了行首 `# identity. ` |
| `gateway/relay/descriptor.py:107` | `# A connector may advertise max_message_length 0 ("no limit"), and a` | `gateway/relay/descriptor.py:109`:`# Normalize the chunking bound at the trust boundary. A connector may` | 整段被**重新折行**过,与基线任何一行都不逐字相同 |
| `gateway/relay/ws_transport.py:877` | `# forwarded passthrough-plane request (Discord` | `gateway/relay/ws_transport.py:878`:`# Phase 5 §5.1: a forwarded passthrough-plane request (Discord` | 少抄了行首 `# Phase 5 §5.1: a ` |

- **为什么是抄错不是漂移**:漂移的特征是"整块在别处逐字找得到";这三处**在整个文件里逐字都找不到**,
  因为它们是作者手工重排版后的产物(去掉行首、重新折行)。
  `descriptor.py` 那处尤其典型:四行摘录**没有一行**和基线逐字相同,
  但读起来完全通顺——**人工评审几乎不可能抓到这一类**。
- **处置**(路径一律写全,基线里 `ws_transport.py` / `descriptor.py` 这类基名不唯一):
  - `gateway/relay/ws_transport.py` 那处 → 拆成两个各自带锚点的块(`:832-836` 与 `:839-844`),
    因为原块中间打了一个 `...`,而 CLAUDE.md 要求跳段时优先拆块(省略标记之后的内容会失去校验)。
  - `gateway/relay/descriptor.py` 那处 → 重新锚到 `:109-115` 并按基线逐字重抄。
  - `gateway/relay/ws_transport.py` 的 passthrough 那处 → 重新锚到 `:877-882`,
    把 `elif ftype == "passthrough_forward":` 这一行也抄进来(它是这段注释的语境)。

---

### 4.3 一处指错位置的锚点(`r2`,不属上面两类)

`chapters/r2-turn-loop-and-model-access.md` 讲 Anthropic 身份伪装时,句子是
"为什么改工具名?因为 Anthropic 的计费分类器把单下划线的 `mcp_` 前缀当成第三方应用的指纹,会拒绝",
锚点却指在这一行 —— 那是**改产品名**那段,不是**改工具名**那段:

`agent/anthropic_adapter.py:2903 @ 863e313`

```python
                text = text.replace("Hermes Agent", "Claude Code")
```

计费分类器的说明在 6 行之后:

`agent/anthropic_adapter.py:2909-2913 @ 863e313`

```python
        # 3. Normalize tool names so NOTHING goes on the OAuth wire with a
        #    single-underscore ``mcp_`` prefix.  Anthropic's subscription/OAuth
        #    billing classifier treats a single-underscore ``mcp_`` tool name as
        #    a third-party-app fingerprint and rejects the request with HTTP 400
        #    "Third-party apps now draw from extra usage, not plan limits"
```

**这一处校验器抓不到**(它只能判"锚点 → 紧跟的块",判不了"锚点 → 它所在句子的语义")。
它是我逐条回读基线时人工发现的。处置:拆成两个锚点两个块,
`:2898-2906` backs 改产品名,`:2909-2913` backs 改工具名。
**记下来是因为它划出了这道关卡的边界:关卡保证"块和行号对得上",不保证"锚点钉的是这句话说的那件事"。**

### 4.4 三处排版硬伤(非引用缺陷,顺手修)

均在 `r2`,是折行时把锚点弄坏了,渲染出来就是错的:

| 位置 | 现象 |
|---|---|
| `run_agent.py:6277` 处 | `@ 863e313` 被写了两遍,第二遍换行到下一行开头 |
| `agent/error_classifier.py:88` 处 | 同上,`@ 863e313` 重复 |
| `agent/codex_responses_adapter.py:89` 处 | 路径被折成 `` `agent/ `` + 换行 + `agent/codex_responses_adapter.py:89`,渲染成 `agent/ agent/…` |
| `agent/turn_finalizer.py:308` 处 | 同上,`agent/` + 换行 + `agent/turn_finalizer.py:308` |

---

## 5. 剩余 46 处 UNCHECKED:全部是正当散文指路

六章清理后剩 46 处 UNCHECKED。**逐条看过,没有一条是"该配摘录而没配"**,分两类:

| 类 | 条数 | 形态 | 为什么保持散文 |
|---|---|---|---|
| **区间指路** | **35** | `路径:起-止`,跨几十到上百行,正文用自己的话概括整段 | 摘录只能抄它的头几行,而正文讲的是整段的**结构**;硬配一段头行不增加信息,只把行文切碎 |
| **单点指路** | **11** | `路径:行号`,指一个定义处或调用点 | 正文说的是"这件事发生在这里",不是"这一行写着什么";已在同章别处带块校验过的交叉引用也归此类 |

其中 **21 条是"整段见 X"式的伴生锚点**:同一段里已经有一个带逐字摘录、已被校验的锚点,
这一条只是补充指出"完整实现在这个区间"。**这是本轮刻意采用的写法**——
它同时满足"关键断言可机械校验"和"读者知道去哪读全貌",代价是分母变大(见 §3 的说明)。

复现分类:

```verify
cd /home/user/hermes-study && python3 - <<'PY'
import sys, re
sys.path.insert(0,'scripts')
import verify_citations as vc
from pathlib import Path
rng=single=0
for f in ['r2-turn-loop-and-model-access','r4-execution-environments',
          'r5-session-state-and-persistence','r6-memory-provider-ecosystem',
          'r7-gateway-session-core','r7b-platform-integration']:
    for st,det in vc.check_note(Path('/home/user/hermes-agent'), Path('chapters/%s.md'%f)):
        if st!='UNCHECKED': continue
        m=re.search(r':(\d+)(-(\d+))?$', det.split()[-1])
        if m and m.group(3): rng+=1
        else: single+=1
print('区间指路 %d / 单点指路 %d / 合计 %d' % (rng, single, rng+single))
PY
```

```text
区间指路 35 / 单点指路 11 / 合计 46
```

---

## 6. 可读性没有倒退

改法遵守的三条自律:

1. **每一个新块都由一句中文引出**,并说清"接下来这段代码证明的是什么"
   (如"这个理由就写在开关旁边:""三态分支长这样:")。目标读者不用猜块和上文的关系。
2. **不删任何一条既有引用**、不把源码块改成 ```text 骗豁免。分母只增不减。
3. **块尽量短**(多数 2–10 行),长块只在它本身就是叙述主体时保留。全篇最长的一块是回合租约的
   那段事故因果链,它本来就是 `r7` §1 要讲的故事,开头一句话就把 issue 号和根因点明:

   `gateway/turn_lease.py:3-4 @ 863e313`

   ```python
   Why this exists (#64934): the gateway's busy guards are keyed by ROUTING KEY
   (``_active_sessions`` in the adapter, ``_running_agents`` in the runner), but
   ```

两处顺带改善的地方,记下来备查:

- `r2` 的两个 `>` 提示框(代码化石 / 流式注释抄错)改成了正文 + 锚点 + 块。
  **理由不是审美**:主循环遇到引用块会整段跳过,里面的锚点连扫都不扫——

  `scripts/verify_citations.py:676-679 @ 25c612f`

  ```python
        if QUOTE.match(line):
            while i < len(lines) and QUOTE.match(lines[i]):
                i += 1
            continue
  ```

  (脚本自己的注释说明了理由:被引用的文档也会引用代码,那是**引文的文本**,不是本笔记在断言什么。
  代价是写在提示框里的**真**锚点**连 UNCHECKED 都不记**。)`r2` 原有 3 条锚点活在这个盲区里:
  `agent/agent_init.py:892`、`agent/conversation_loop.py:1445`、`agent/chat_completion_helpers.py:4063`。
- `r2` 那条"全仓库没有任何代码把它打开"是一条**全称否定**,原文没写搜索面。
  按 CLAUDE.md「负结论的成本」补上了:`grep -rn "_budget_grace_call" --include=*.py`,全仓不排除任何目录,
  四处命中逐一说明(1 读 + 1 初始化 + 2 消费,`tests/` 另有一处只断言其为 `False`)。

---

## 7. 收工校验

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py \
  /home/user/hermes-agent chapters/*.md >/dev/null 2>&1; echo "chapters 退出码=$?"; \
  git -C /home/user/hermes-agent status --porcelain | wc -l
```

```text
chapters 退出码=0
0
```

即:全 `chapters/` 引用校验退出码 0,基线工作区 `git status --porcelain` 零行(未被碰过)。

**本底稿自身的读数**(制度要求单报"当轮 notes"那一个数,下限 70%):

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py \
  /home/user/hermes-agent notes/r11b-raw-chapter-anchors.md 2>&1 | grep -E '^citations|^可校验'
```

```text
citations=16  OK=13  UNCHECKED=3
可校验比例 OK/16 = 81.2%
```

表格行内锚点单列(不并入上面的比例):`table_anchors=23 OK=13 UNCHECKED=10`,0 DRIFT / 0 OUT-OF-RANGE。

`verify_evidence_commands.py` 那一侧的数是 **paired=7 / unpaired=1 / differing=0**
(那个 unpaired 就是上面 §3 里故意不钉输出的全量 `chapters/*.md` 命令)。

**这个数本身不能写进 `verify` 块**——检查器会真的把块里的命令跑起来:

*(R11C 只改行号:该语句原在 `:97`,R11C 落地可跑性检查后,同一条语句移到 `:205`;
`--fix` 找不到它是因为文件里现在有**两处**同样的 `subprocess.run`——`:180` 是新增的
可跑性腿,`:205` 才是本条原本指的比对腿。原判不动。)*

`scripts/verify_evidence_commands.py:205`

```python
            r = subprocess.run(["bash", "-c", cmd], cwd=ROOT, capture_output=True,
```

于是"在本文件里跑本文件的检查器"是**无限递归**,本轮实测跑到 120 秒超时才被掐掉。
**这是这道关卡的一个使用禁忌,记下来免得下一轮重踩。**

剩下几条 UNCHECKED 是"提一下当时那个锚点长什么样"的散文提及(见 §4.1 与 §6 那几处),
不是对某一行内容的断言,故不配块。

---

## 移交

| 编号 | 锚点 + 现象 |
|---|---|
| **H-R11B-C-a** | `chapters/r3-tool-infrastructure.md` 的 UNCHECKED 占比实测 **15/17 = 88.2%**,**只差 1.8 个百分点就触发关卡的排版提示**,却因为在阈值下方从未被点名。它与本轮六章是同一病因(散文内联锚点、无摘录),不在 H-R8D-g 的名单里纯属阈值巧合。第一条无块引用在该章第 103 行,指 `tools/registry.py:43`:`def _module_registers_tools(module_path: Path) -> bool:`;15 条全是这个形态。 |
| **H-R11B-C-b** | `scripts/verify_citations.py:676`:`if QUOTE.match(line):` —— 主循环**整段跳过 `>` 引用块内部**,于是写在提示框/引用框里的锚点**连 UNCHECKED 都不记**(比 UNCHECKED 更隐蔽,与 H-R10-a 点名的扩展名盲区同型)。本轮在 `r2` 一章就发现 3 条锚点活在这个盲区里。全语料规模未测,建议下一轮先普查再决定是否改脚本。 |
| **H-R11B-C-c** | `chapters/r7-gateway-session-core.md` 第 687 行那格标注的 `gateway/session.py:1103`:`if source.chat_type == "dm":` —— 该章 §6 的对照表有 2 个表格锚点记 TABLE-UNCHECKED(另一个在第 689 行,指 `gateway/run.py:14493-14500`,连声明式摘录都没写)。非阻断,但按 R9B 的规矩它们一次都不会被比对。 |
| **H-R11B-C-d** | `reports/round-8d-cli-completion.md:430`:`| **H-R8D-g** | R11B |` —— 该移交项对病因的描述("锚点写在代码块之后")**只适用于六章中的 `r7b` 一章**,另外五章是"根本没有源码块"。见本底稿 §2。建议主线在 R11B 报告里点名更正,以免下一轮把同类问题当成机械搬运估工。 |
| **H-R11B-C-e** | `scripts/verify_evidence_commands.py:97`:`r = subprocess.run(["bash", "-c", cmd], cwd=ROOT, capture_output=True,` —— 关卡会真的执行 `verify` 块里的命令,所以**在某文件里写"跑本文件的 `verify_evidence_commands.py`"会无限递归**(本轮实测跑到 120 秒超时)。同理,任何钉了输出、而输出取决于 `chapters/*.md` / `notes/*.md` 通配符的 `verify` 块,会被**别的片的合法新增**弄成 differing——本轮实测:主线新增一章后全量数从 474 跳到 479。建议把这两条禁忌写进下一轮派工书。 |
