# r11f-fix-90 · 可复算指标关卡的两条腿:写入腿的替换动作,校验腿的对应关系

> 底稿。求全求证。本轮不读基线新代码,读的是**本仓库自己的工具**
> —— 因此本文的锚点分两类:指向基线的写 `路径:行号 @ 863e313`,
> 指向本仓库自己的,引用**交付版**时写 `路径:行号 @ bdb82d5`(R11D 立的自引 commit 钉子),
> 引用**本轮修订版**时不写钉子 —— 那个 sha 在写下时还不存在,见 §8 `H-R11Ffix-c`。
> 被审对象是 R11F 收官提交 `bdb82d5` 的 `scripts/verify_derived_numbers.py`。

本文结清交付问题第 1、2 两项:

| 项 | 一句话 | 落点 |
|---|---|---|
| 1 | 写入腿的替换动作会命中非目标数字;「同声明内多键撞值」守卫**恒不触发** | §1 §2 |
| 2 | 校验腿在一条声明覆盖多键时,只判「这个数在不在」,判不了「哪个数是哪个键的」 | §3 |

两项**同源**:两条腿都用 `str.__contains__` / `str.replace` 的**子串**语义去问
「这个数在不在这段里」。所以修法也只有一份:两腿共用一个
`number_tokens()`,把区段切成**整数字 token**。

---

## 1. 写入腿缺陷 A:替换动作命中非目标数字

### 1.1 原实现

`scripts/verify_derived_numbers.py:187 @ bdb82d5`

```
        for body_start, body_end, key, old, new, hits in edits:
            done = 0
            for j in range(body_start, body_end):
                for f_old, f_new in ((f"{old:,}", f"{new:,}"), (str(old), str(new))):
                    while f_old in lines[j]:
                        lines[j] = lines[j].replace(f_old, f_new, 1)
                        done += 1
                        changes.append(f"  {rel}:{j + 1}  {key}  {f_old} -> {f_new}")
            assert done == hits, f"{key}: 预期换 {hits} 处,实换 {done} 处"
```

三个具体后果:

**(a) 更大数字里的一截会被改掉。** `f_old` 是裸子串,`12,586` 里含 `2,586`。
把 `2,586` 换成 `2,829`,那一格就变成 `12,829`。

**(b) 那句 `assert` 抓不到它。** `hits` 的来源是

`scripts/verify_derived_numbers.py:173 @ bdb82d5`

```
                hits = sum(region.count(f) for f in forms(old))
```

`str.count` 与 `str.replace` 是**同一套子串语义**,于是「预期换几处」与「实换几处」
在错误发生时**一起错、正好相等**。这个断言只能抓住「区段在两次读之间变了」,
抓不到「一开始就数错了」。*这与 R8C 记下的「只比首行的校验器对锚到隔壁同形状段落
完全无感」是同一物种:**用出错的那把尺子去量自己错没错**。*

**(c) 新值包含旧值时死循环。** `while f_old in lines[j]` 每换一次又造出一个 `f_old`
(`586` → `2,586`,里面还有 `586`),永不终止。

**(d) 锚点行号也在射程内。** 区段里若有 `notes/x.md:2586`,它的行号会被一并改写
—— 那是 `verify_citations.py` 的资产,改了就是当场造一处引用漂移。

### 1.2 改法

判据换成整数字 token,落笔按 token 的**字符跨度**改写,一次一处、不循环:

`scripts/verify_derived_numbers.py:127`

```
NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+|\d+)(?![\w,]|\.\d)")
# `路径.扩展名:行号` —— 锚点里的行号是 verify_citations.py 的资产,两条腿都整段排除。
ANCHOR = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_./\-]*\.[A-Za-z0-9]{1,6}:\d+(?:-\d+)?")
```

千分位形式写在**前面**是关键:正则的选择分支按顺序试,`\d{1,3}(?:,\d{3})+` 先匹配,
于是 `12,586` 整体成为一个 token。两侧的环视挡掉 `L1`、`R1-inventoried` 里的数字
(左边贴着字母)与 `81.1%` 的两截(小数点)。

---

## 2. 写入腿缺陷 B:「同声明内多键撞值」守卫恒不触发

### 2.1 原实现

`scripts/verify_derived_numbers.py:164 @ bdb82d5`

```
            sibling_truths = {old_vals.get(k) for k in keys} | {new_vals.get(k) for k in keys}
```

`scripts/verify_derived_numbers.py:178 @ bdb82d5`

```
                if sum(1 for v in sibling_truths if v == old) > 1:
```

`sibling_truths` 是**集合**。集合里等于某个值的元素**至多一个**,所以
`sum(...) > 1` **恒为假**。这条守卫从 R11F 落地起**一次都没有触发过**,
它在源码里的存在只是让读者以为这个风险被守住了。

*这与 R9B 记下的表格锚点是同一形状:一个**从不被执行**的判据,和一个不存在的判据,
在效果上没有区别 —— 差别只在于前者会让人停止追问。*

### 2.2 它本该拦住什么

同一条声明里两个键真值相同,而只有其中一个本轮要变。要变的那个键去数 `hits`,
会把**另一个键的那一格**也数进去,然后一起改掉。此时另一个键因为 `old == new`
在更早的分支就 `continue` 了,**没有第二组 edits 去撞那句 assert** —— 于是这是一次
**静默的**张冠李戴,输出还报 `synced=2 skipped=0`(即「全都对了」)。

### 2.3 改法

对**其它键**逐个点名比对,不经集合:

`scripts/verify_derived_numbers.py:317`

```
                rivals = [k for k in keys if k != key
                          and old in (old_vals.get(k), new_vals.get(k))]
```

---

## 3. 校验腿:一条声明覆盖多个键时,取值与键的对应关系必须可判

### 3.1 原实现

`scripts/verify_derived_numbers.py:271 @ bdb82d5`

```
                if any(f in body for f in forms(vals[key])):
                    ok += 1
```

逐键各问一次「这个数在不在区段里」。这是**集合成员关系**,而读者读的是
「L1 那一行的文件数」—— 是**对应关系**。两者的差距可以直接演出来:
把 `chapters/r1` 那张 6 行 12 格的表**整体重排**,每个数都还在区段里,
关卡照样 `declared=12 OK=12 STALE=0`、退出码 0。

它还有两处**子串假绿**,与写入腿的缺陷 A 同源:真值 `2586` 在 `12,586` 里
「找得到」;在锚点 `notes/x.md:2586` 的行号里也「找得到」。

### 3.2 改法:保序绑定

区段的数字 token 按出现顺序排好;声明里的键按**声明顺序**逐个认领**它之后的第一个**
等值 token。

`scripts/verify_derived_numbers.py:264`

```
def bind(keys, toks, vals):
    """保序绑定:键按声明顺序,各认领其后第一个等值 token。

    返回 [(key, tok_or_None, verdict)],verdict ∈ {OK, ORDER, STALE, UNKNOWN-KEY}。
    贪心最早匹配 —— 存在任何保序匹配时它必然成功,所以 ORDER 不会误报。
```

三件事因此成立:

1. **对应关系确定且可打印**。`--explain` 直接给出「键 = 真值 ↔ 文件:行:列 '原文'」。
2. **重排被抓住**。值在区段里有、但不在声明顺序上 → `ORDER`,阻断。
3. **不误报**。贪心最早匹配是子序列匹配的标准结论:只要存在**任何**一种保序匹配,
   贪心最早就一定能找到。所以 `ORDER` 只在真的对不上号时出现。

**声明顺序是作者的声明,不是脚本的猜测** —— 与 CLAUDE.md 给表格锚点、给 ```text 豁免、
给无扩展名文件定的是同一条原则。`chapters/r1` 那 12 个键的声明顺序,本来就是
表的行序 × 列序,一个字都不用改。

### 3.3 覆盖面要如实说

* 两个键真值**相同**时,谁认领哪个 token 由顺序决定,交换它们无法被区分。
  这是保序判据的固有边界,`--explain` 会在这两条后面标出来让它可见。
* 区段内**未被任何键认领**的数字 token 不受约束(那是正文里别的数)。
* 本关卡仍然只看**写了声明**的段落。没写声明的手抄件,和 R11D 那天一样发现不了。

---

## 4. 负控:写入腿(W1..W5)

**每条用例同时跑两版**:`git show bdb82d5:scripts/verify_derived_numbers.py` 取交付版,
工作树取修订版,把两边的真实行为逐条打印。判 PASS 的条件是
「**交付版确实翻车 且 修订版拦住**」,不是「修订版没报错」。

探针:`data/r11f-fix/probes/derived_write_negative_control.py`。
每个用例在 `mktemp -d` 里造一个**临时 git 仓库**(不碰本仓库,也不碰基线),
先提交「旧」台账,再改成「新」台账,然后端到端跑 `--sync --since HEAD`。

```verify
cd /home/user/hermes-study && python3 data/r11f-fix/probes/derived_write_negative_control.py | tail -3
```

```text
==============================================================================
negative-control W1..W5   PASS=5/5  (W1..W4 负控 + W5 正控)
OK: 四条负控的缺陷在交付版上均实际触发、在修订版上均被拦住;正控两版皆正常
```

下面是**触发时的完整输出**(上面那条命令去掉 `| tail -3`)。

```text
==============================================================================
W1 · 替换动作不得命中非目标数字(12,586 里的 2,586)
==============================================================================

--- R11F 交付版 ---
exit=0
  synced=2  skipped=0  (旧真值复算自 HEAD)
    fixture.md:5  ledger.L1.lines  2,586 -> 2,829
    fixture.md:6  ledger.L1.lines  2,586 -> 2,829
  fixture.md 落笔后(只打印区段行):
    | 指标 | 值 |
    |---|---:|
    | L1 行数 | 2,829 |
    | 另一个与本声明无关的数 | 12,829 |

--- R11F-fix 修订版 ---
exit=0
  synced=1  skipped=0  (旧真值复算自 HEAD)
    fixture.md:5  ledger.L1.lines  2,586 -> 2,829
  fixture.md 落笔后(只打印区段行):
    | 指标 | 值 |
    |---|---:|
    | L1 行数 | 2,829 |
    | 另一个与本声明无关的数 | 12,586 |

断言:交付版确实表现出该缺陷;修订版已拦住 —— PASS

==============================================================================
W2 · 同声明内多键撞值的守卫必须真的能被触发
==============================================================================

--- R11F 交付版 ---
exit=0
  synced=2  skipped=0  (旧真值复算自 HEAD)
    fixture.md:5  ledger.L1.lines  2,586 -> 2,829
    fixture.md:6  ledger.L1.lines  2,586 -> 2,829
  fixture.md 落笔后(只打印区段行):
    | 层 | 行数 |
    |---|---:|
    | L1 | 2,829 |
    | L2 | 2,829 |

--- R11F-fix 修订版 ---
exit=0
  [SKIP] fixture.md:1 ledger.L1.lines 旧真值 2,586 同时是同一条声明里 ledger.L2.lines 的真值,替换会张冠李戴
  synced=0  skipped=1  (旧真值复算自 HEAD)
  fixture.md 落笔后(只打印区段行):
    | 层 | 行数 |
    |---|---:|
    | L1 | 2,586 |
    | L2 | 2,586 |

断言:交付版确实表现出该缺陷;修订版已拦住 —— PASS

==============================================================================
W3 · 新值包含旧值时,替换必须终止
==============================================================================

--- R11F 交付版 ---
exit=TIMEOUT
  <未在 25s 内终止>
  fixture.md 落笔后(只打印区段行):
    | 指标 | 值 |
    |---|---:|
    | L1 行数 | 586 |

--- R11F-fix 修订版 ---
exit=0
  synced=1  skipped=0  (旧真值复算自 HEAD)
    fixture.md:5  ledger.L1.lines  586 -> 2,586
  fixture.md 落笔后(只打印区段行):
    | 指标 | 值 |
    |---|---:|
    | L1 行数 | 2,586 |

断言:交付版确实表现出该缺陷;修订版已拦住 —— PASS

==============================================================================
W4 · 锚点里的行号不是可复算数,不许被改
==============================================================================

--- R11F 交付版 ---
exit=0
  synced=2  skipped=0  (旧真值复算自 HEAD)
    fixture.md:5  ledger.L1.lines  2,586 -> 2,829
    fixture.md:6  ledger.L1.lines  2586 -> 2829
  fixture.md 落笔后(只打印区段行):
    | 指标 | 值 |
    |---|---:|
    | L1 行数 | 2,829 |
    | 出处 | 见 `notes/x.md:2829` |

--- R11F-fix 修订版 ---
exit=0
  synced=1  skipped=0  (旧真值复算自 HEAD)
    fixture.md:5  ledger.L1.lines  2,586 -> 2,829
  fixture.md 落笔后(只打印区段行):
    | 指标 | 值 |
    |---|---:|
    | L1 行数 | 2,829 |
    | 出处 | 见 `notes/x.md:2586` |

断言:交付版确实表现出该缺陷;修订版已拦住 —— PASS

==============================================================================
W5 · 正控:一段里同一个旧值出现两次,两处都换,未声明的数不动
==============================================================================

--- R11F 交付版 ---
exit=0
  synced=3  skipped=0  (旧真值复算自 HEAD)
    fixture.md:3  ledger.L1.lines  1,000 -> 1,300
    fixture.md:3  ledger.L1.lines  1,000 -> 1,300
    fixture.md:3  ledger.total.lines  8,530 -> 8,830
  fixture.md 落笔后(只打印区段行):
    仍有 1,300 行属于 L1,即 8,830 − 1,300 = 7,530 行不属于它。

--- R11F-fix 修订版 ---
exit=0
  synced=3  skipped=0  (旧真值复算自 HEAD)
    fixture.md:3  ledger.L1.lines  1,000 -> 1,300
    fixture.md:3  ledger.total.lines  8,530 -> 8,830
    fixture.md:3  ledger.L1.lines  1,000 -> 1,300
  fixture.md 落笔后(只打印区段行):
    仍有 1,300 行属于 L1,即 8,830 − 1,300 = 7,530 行不属于它。

断言(正控):交付版正常;修订版正常 —— PASS

==============================================================================
negative-control W1..W5   PASS=5/5  (W1..W4 负控 + W5 正控)
OK: 四条负控的缺陷在交付版上均实际触发、在修订版上均被拦住;正控两版皆正常
```

---

## 5. 负控:校验腿(V1..V4)

同一套办法。探针:`data/r11f-fix/probes/derived_verify_negative_control.py`。
校验腿不需要 git,所以临时 STUDY 里只放一份脚本 + 一份造好的 `data/ledger.tsv` + 一份 fixture。

```verify
cd /home/user/hermes-study && python3 data/r11f-fix/probes/derived_verify_negative_control.py | tail -3
```

```text
==============================================================================
negative-control V1..V4   PASS=4/4
OK: 三种假绿在交付版上均实际发生,在修订版上均被判红;正控两版皆绿
```

**触发时的完整输出**:

```text
==============================================================================
V1 · 一条声明覆盖多个键:区段内的取值与键的对应关系必须可判
==============================================================================

fixture.md:
    <!-- derived: ledger.L1.lines ledger.L2.lines -->
    
    | 层 | 行数 |
    |---|---:|
    | L1 | 1,431 |
    | L2 | 2,586 |

--- R11F 交付版 ---  exit=0
  declared=2  OK=2  STALE=0
  OK: every declared derived number matches the ledger

--- R11F-fix 修订版 ---  exit=1
  declared=2  OK=1  STALE=0  ORDER=1  UNKNOWN-KEY=0
  [ORDER] fixture.md:1  ledger.L2.lines 复算真值 1,431 在区段内出现于 5:8,但**不在声明顺序上** —— 这一段的数与键对不上号(值被重排或串行了)
  FAIL: 1 个已声明的可复算指标与台账真值对不上

断言:交付版确实假绿;修订版已判红 —— PASS

==============================================================================
V2 · 子串假绿:12,586 里的 2,586 不是 2,586
==============================================================================

fixture.md:
    <!-- derived: ledger.L1.lines -->
    
    L1 相关的那个数写错了,这里印的是 12,586。

--- R11F 交付版 ---  exit=0
  declared=1  OK=1  STALE=0
  OK: every declared derived number matches the ledger

--- R11F-fix 修订版 ---  exit=1
  declared=1  OK=0  STALE=1  ORDER=0  UNKNOWN-KEY=0
  [STALE] fixture.md:1  ledger.L1.lines 复算真值 2,586,但紧跟其后的段落里没有这个数字 token —— 更大数字的一截(12,586 里的 2,586)、锚点行号(x.md:2586)、围栏块内的源码摘录,三者都不算
  FAIL: 1 个已声明的可复算指标与台账真值对不上

断言:交付版确实假绿;修订版已判红 —— PASS

==============================================================================
V3 · 锚点假绿:notes/x.md:2586 的行号不是本键的真值
==============================================================================

fixture.md:
    <!-- derived: ledger.L1.lines -->
    
    L1 的行数见 `notes/x.md:2586`,正文没有印它。

--- R11F 交付版 ---  exit=0
  declared=1  OK=1  STALE=0
  OK: every declared derived number matches the ledger

--- R11F-fix 修订版 ---  exit=1
  declared=1  OK=0  STALE=1  ORDER=0  UNKNOWN-KEY=0
  [STALE] fixture.md:1  ledger.L1.lines 复算真值 2,586,但紧跟其后的段落里没有这个数字 token —— 更大数字的一截(12,586 里的 2,586)、锚点行号(x.md:2586)、围栏块内的源码摘录,三者都不算
  FAIL: 1 个已声明的可复算指标与台账真值对不上

断言:交付版确实假绿;修订版已判红 —— PASS

==============================================================================
V4 · 正控:表写对时两版都绿,修订版还打得出键 ↔ token 的绑定
==============================================================================

fixture.md:
    <!-- derived: ledger.L1.lines ledger.L2.lines -->
    
    | 层 | 行数 |
    |---|---:|
    | L1 | 2,586 |
    | L2 | 1,431 |

--- R11F 交付版 ---  exit=0
  declared=2  OK=2  STALE=0
  OK: every declared derived number matches the ledger

--- R11F-fix 修订版 ---  exit=0
  fixture.md:1  ledger.L1.lines = 2,586 ↔ fixture.md:5:8 '2,586'
    fixture.md:1  ledger.L2.lines = 1,431 ↔ fixture.md:6:8 '1,431'
  declared=2  OK=2  STALE=0  ORDER=0  UNKNOWN-KEY=0
  OK: every declared derived number matches the ledger, in declared order

断言(正控):交付版绿;修订版绿 —— PASS

==============================================================================
negative-control V1..V4   PASS=4/4
OK: 三种假绿在交付版上均实际发生,在修订版上均被判红;正控两版皆绿
```

---

## 6. 关卡在真语料上的读数

收紧判据**没有**靠放宽任何东西换来绿色 —— `chapters/` 上的 18 条声明全部通过,
且现在每一条都能说出自己绑到了哪一个 token:

```verify
cd /home/user/hermes-study && python3 scripts/verify_derived_numbers.py --explain | tail -7
```

```text
  chapters/r1-what-is-hermes-agent.md:128  ledger.inventoried.lines = 1,379,392 ↔ chapters/r1-what-is-hermes-agent.md:131:54 '1,379,392'
  chapters/r1-what-is-hermes-agent.md:128  ledger.total.files = 8,530 ↔ chapters/r1-what-is-hermes-agent.md:132:35 '8,530'
  chapters/r1-what-is-hermes-agent.md:128  ledger.processed.files = 2,829 ↔ chapters/r1-what-is-hermes-agent.md:132:53 '2,829'
  chapters/r1-what-is-hermes-agent.md:144  ledger.LT.lines = 756,619 ↔ chapters/r1-what-is-hermes-agent.md:146:15 '756,619'
  chapters/r1-what-is-hermes-agent.md:144  ledger.L1.lines = 522,207 ↔ chapters/r1-what-is-hermes-agent.md:146:31 '522,207'
declared=18  OK=18  STALE=0  ORDER=0  UNKNOWN-KEY=0
OK: every declared derived number matches the ledger, in declared order
```

---

## 7. 顺带修掉的第三处:`--since` 取不到台账时抛栈

`ledger_at()` 原用 `check=True`,于是一个取不到的 rev 直接抛
`CalledProcessError` 的 traceback。R11F 收官报告 §5.1 的 ```verify 块钉的正是
`--sync --since main`,而**本仓库的 `main` 上没有 `data/ledger.tsv`**
(它停在 `Initial commit`,树里只有 `README.md`),于是那个块在新容器里重跑
产出的是一段 traceback,`verify_evidence_commands.py` 判 `EVIDENCE-DIFF`。

这是 CLAUDE.md「**量『之前』的命令不许钉在会移动的引用上**」的又一次重演
—— 而且这次比之前几次更彻底:`main` 不只是会移动,它**在别的容器里根本解析不到那份文件**。

两处都改了:

* 脚本改为报清楚、不抛栈(`scripts/verify_derived_numbers.py:241`:`def ledger_at(rev):`);
* R11F 报告那个块的 rev 由 `main` 改为固定 sha `5861435`(R11E 合并点 = R11F 开工点),
  逐处点名写在该报告文末勘误节 `E-1`。

同一形状在 `notes/r11f-90-handover-rulings.md` 还有一处(`git diff main...HEAD`),
一并改为 `5861435 bdb82d5` 两端钉死,就地写明原判不撤、只换参照点。

---

## 8. 移交

| 案号 | 现象(带锚点) | 去向(条件式收件人) |
|---|---|---|
| `H-R11Ffix-a` | 保序绑定对「同声明内两个键真值相同」这一形态判不出对调 —— `scripts/verify_derived_numbers.py:276`:`hit = next((i for i in range(pos, len(toks)) if toks[i].val == want), None)`,两个 want 相同的键只能按先后各领一个 | **任何一轮给某条 `<!-- derived: -->` 声明添加第 N 个键、且新键与既有键真值可能相等时**,必须同批判断这条边界是否已被踩上;若踩上,改法是把该声明拆成两条(区段各自独立),而不是放宽判据 |
| `H-R11Ffix-b` | 区段边界仍是「跳过空行后紧跟的一段连续非空行」(`scripts/verify_derived_numbers.py:163`:`def declarations(lines):`),表格中间若插入空行,后半张表就不在区段内 —— 本轮三条声明都没踩上,故未处理 | **任何一轮改动 `chapters/r1-what-is-hermes-agent.md` 的三张派生表排版时**,先跑 `--explain` 确认绑定数仍为 18 |
| `H-R11Ffix-c` | 自引锚点的 commit 钉子(R11D 立)要求 `路径:行号 @ <sha>`,而引用**本轮刚写的**代码时那个 sha 还不存在 —— 本文的处理是:引用交付版写 `@ bdb82d5`(已存在的提交),引用修订版**不写钉子**(默认解析工作树),`scripts/verify_citations.py:179`:`CITE_EXTS = "py` | **任何一轮在底稿里引用「本轮刚写的本仓库代码」时**,都会遇到同一个先有鸡还是先有蛋;当前处理方式是收工提交后回填并复跑 `verify_citations.py`,若某轮认为该自动化,改的是 `scripts/verify_citations.py` 的自引解析 |
