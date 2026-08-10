# R11D 片 A 底稿 —— `reports/` 与 `reviews/` 坏锚点按裁定执行

> 底稿,求全求证。溯源约定:基线锚点 `路径:行号 @ 863e313`;指向本仓库自己的锚点带 commit
> 钉子(如 `@ df6d450`),不带钉子时校验器读的是工作树最新版。
> 本片只做寻址补全与定位查证,**不改任何一条结论**。

---

## 0. 结论(先给判断)

**1. `reports/` 补全 56 处、`reviews/` 补全 0 处,与派工书给的「50 + 20」都不等,两处差额都有据。**

| | 派工书 | 实测符合判据 | 实际落盘 | 差额原因 |
|---|---:|---:|---:|---|
| `reports/` | 50 | **57** | **56** | 判据同款重扫得 57(见 §2.1);其中 1 处是 use-mention,主动撤回(§2.3) |
| `reviews/` | 20 | **20** | **0** | 裁定明令原文不改,全部走附录(§3);且这 20 里有 4 处**根本不是缺陷**(§3.2) |

**2. 最值得记的一条不是补全本身,是补全时撞见的关卡缺陷:一句谈论围栏的散文会把整份文件
后半段从检查面上抹掉。** 全语料 3 处,合计 **931 行正文 / 68 处锚点**(钉本轮开工点 `df6d450`)
从不被 `verify_citations.py` 读到,而且**声明式非源码围栏在那些区域会反向失效**
——我的第一版勘误节就是这么被反噬的(§4)。同轮另一片独立撞上同一个缺陷,并案说明见 §5。

**3. `reviews/` 那 4 处历史失败已全部查清真实位置**,三处是**锚点比真实位置早一行**
(其中一处还缺 commit 钉子,于是报的是 `not found` 而不是漂移距离),
一处是「五处合成摘录撞上单起点契约」,内容全部为真(§3.3)。按裁定不就地改,
读者按 `reviews/review-1-anchor-corrections.md` §2 取正确地址。

**4. 关卡读数一个字没变。** `reports/*.md` 跑 `verify_citations.py`,改动前后输出**逐字相同**
(`citations=742 OK=204 UNCHECKED=538`)。这不是失败,是这项工作的真实性质:
**受益方是读者,不是关卡**——那些裸锚点本来就以 UNCHECKED 计入分母,补全既不增也不减(§2.5)。

---

## 1. 裁定与判据

### 1.1 执行范围来自哪条裁定

`CLAUDE.md:539 @ df6d450`

```
  **锚点寻址修正是第四类改动,与「行号漂移」同级(R11D 裁定,结清 H-R11C-D-f)。**
```

裁定的要点(逐条落到本片的动作上):

| 裁定 | 本片动作 |
|---|---|
| `reports/` 就地补全 + 文末勘误节点名 | 9 份报告各加一节 `## 勘误(R11D:锚点寻址补全)`,逐处点名(§2.4) |
| `reviews/` 原文不改,另立附录 | 新建 `reviews/review-1-anchor-corrections.md`(§3) |
| 两处都不得顺手改正文其他任何字 | `git diff` 逐行核过:50 行改动全部只是路径前缀(§2.2) |
| 判据 = 基线里恰好一个候选 | 多候选一律不动;`reports/` 剩 **87** 处、`reviews/` 剩 **17** 处 AMBIGUOUS(含块内,§2.1) |

### 1.2 判据只有一条,且实现与 R11C 片 D 同源

判据:**基线 `863e313` 里恰好一个文件的路径以这个串结尾(按目录边界匹配)**,
且该文件长到有这一行(行号越界即拒绝——那说明候选很可能不是它)。

实现脚本 `data/r11d/probes/anchor_completion_r11d.py`,从 `data/r11c/d-anchor-resolution-fix.py`
复制后改范围(`notes/` → `reports/` + `reviews/`),判据与两处「绝不改写」原样沿用:

- **围栏块内部不改**:契约是逐字源码摘录,改它就是让摘录与基线不符;若那是个
  verify 块,改写命令更会让它跑出别的输出。
- **引用块 `>` 内部不改**:可能是逐字文档摘录,同理。

*(写这一段本身要小心:表示围栏标记的四反引号转义**不能写在行首**,否则就会触发 §4 那条缺陷
——本底稿第一版把「```` ```verify ```` 块里改写命令」这句话起了一行,当场把自己变成第 4 个命中文件。)*

这两处正是 `verify_citations.py` 自己跳过的两处,所以「本脚本改的范围」= 「关卡会读的范围」。

### 1.3 判据之外还有一类,本片只报不改

**只在本仓库(hermes-study)里唯一**的裸文件名(如 `verify_citations.py` →
`scripts/verify_citations.py`)。裁定给的判据写的是基线;而自引锚点另有「commit 钉子」
那条规矩管着(它浮在一棵会动的树上),两件事不该在同一次改动里混做。
`reports/` 里这类为 **0**,`reviews/` 里 **4** 处——而那 4 处恰好还是不该动的(§3.2)。

---

## 2. `reports/`:57 处符合判据,落盘 56 处

### 2.1 前后读数(承载清单剔除与不剔除两个读数都报)

「某个串还在不在语料里」这类测量**对『报告它』这个动作不幂等**:勘误节与附录本身就要
逐字列出那些坏锚点,于是下一次普查会再数到它们。按 `CLAUDE.md`「搜过没有类测量必须报两个读数」,
两个读数如下。

**读数 A —— 改动之前(钉在本轮开工点 `df6d450`,不受后续提交影响)**:

```verify
cd /home/user/hermes-study && python3 data/r11d/probes/anchor_completion_r11d.py --census-only --rev df6d450
```

```text
== 普查(RESOLVED 不计;树=df6d450;承载清单未剔除) ==
  reports    86  AMBIGUOUS
  reports    57  BASELINE-ONE
  reports    10  NOT-IN-TREE
  reports     5  NOT-IN-TREE+IN-BLOCK
  reports     1  AMBIGUOUS+IN-BLOCK
  reviews    15  BASELINE-ONE
  reviews    14  AMBIGUOUS
  reviews     4  STUDY-ONE+IN-BLOCK
  reviews     3  AMBIGUOUS+IN-BLOCK
  reviews     1  BASELINE-ONE+IN-BLOCK
```

**读数 B —— 改动之后,剔除本轮承载清单**(剔除 = 跳过 `reviews/review-1-anchor-corrections.md`
整份 + 每份报告从 `## 勘误(R11D:锚点寻址补全)` 起的全部内容):

```verify
cd /home/user/hermes-study && python3 data/r11d/probes/anchor_completion_r11d.py --census-only --drop-carrier
```

```text
== 普查(RESOLVED 不计;树=工作树;承载清单已剔除) ==
  reports    86  AMBIGUOUS
  reports    10  NOT-IN-TREE
  reports     5  NOT-IN-TREE+IN-BLOCK
  reports     1  BASELINE-ONE
  reports     1  AMBIGUOUS+IN-BLOCK
  reviews    15  BASELINE-ONE
  reviews    14  AMBIGUOUS
  reviews     4  STUDY-ONE+IN-BLOCK
  reviews     3  AMBIGUOUS+IN-BLOCK
  reviews     1  BASELINE-ONE+IN-BLOCK
```

**读数 C —— 改动之后,不剔除承载清单(朴素读数)**:`reports` 的 `BASELINE-ONE` 从 57 掉到 1,
但多出 **56 处 `BASELINE-ONE+IN-BLOCK`** —— 那正是九份勘误节里逐字列出的「原锚点」列。
**朴素读数会让人以为一处都没修**(56 + 1 ≈ 57),这就是那条规矩要防的污染。

`reports` 的 `BASELINE-ONE` 由 **57 → 1**,剩下那 1 处是主动撤回的(§2.3)。
`reviews` 三个读数全程不变,因为按裁定一个字没改。

**与派工书「50 处」的差额**:派工书的 50 取自 R11C 移交,本片用同款判据重扫得 **57**。
两者口径差在哪没有留下可复算的记录,故不强行对账,只如实报本片实测数与复现命令。

### 2.2 落盘后逐行核对:改的只有路径前缀

改动明细落在 `data/r11d/anchor-completion-applied.tsv`(由 `--apply` 写出),按它复算:

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{n++; ln[$1"|"$2]=1; f[$1]=1} END{printf "补全 %d 处 / 改动 %d 行 / 涉及 %d 份报告\n", n, length(ln), length(f)}' data/r11d/anchor-completion-applied.tsv
```

```text
补全 56 处 / 改动 50 行 / 涉及 9 份报告
```

*为什么不用 `git diff -U0 -- reports/ | grep -c` 来数:那条命令的读数**会随本轮自己的产出变**
——勘误节一加进去,50 就变成 224。这与 §4.4 是同一条规矩(量「之前」的命令不许钉在会移动的引用上),
本片一轮里撞了两次,两次都是关卡判 `EVIDENCE-DIFF` 抓到的。*

50 行改动、56 处补全(有 6 行一行两处)。逐行读过一遍,每一行的改动都只是在原锚点前面
补了目录部分,**同一行其余字符逐字未动**。抽三条为例(左原样、右补全后,均为本仓库报告正文):

| 报告 | 原样 | 补全后 |
|---|---|---|
| `reports/round-1-survey.md:125` | `conversation_loop.py:122-201` | `agent/conversation_loop.py:122-201` |
| `reports/round-9c-external-interfaces.md:280` | `microsoft_graph_client.py:139` | `tools/microsoft_graph_client.py:139` |
| `reports/round-10-client-interface-layer.md:312` | `edit_approval.py:267` | `acp_adapter/edit_approval.py:267` |

### 2.3 撤回的那一处:use-mention,机械判据看不见

原文是:

`reports/round-10b-desktop-application.md:161 @ df6d450`

```
实测波及**恰好 1 处**真锚点(notes 里的裸 `build.sh:4-6`);
```

它符合判据(那个文件名在基线里只有 `native/fts5_cjk/` 下一个候选),脚本也确实改了。
**但这一处的锚点是被当作对象讨论的字符串,不是一个地址**:句子里那个「**裸**」字就是在
描述它的形态,下一句还写着「处置是把它补成全路径」。补全之后那半句变成
「notes 里的裸 <带全路径的锚点>」——**报告在自我否定**。

于是就地撤回,恢复原样。裁定说「凡是会改变『指向谁』的改动一律不在本例外内」;
这一处不改变指向谁,但它**改变了这句话在断言什么**,同属例外之外。

*这一条值得单记:判据是「候选唯一」,而 use-mention 与 use 在语法上完全一样。
机械判据抓形状,形状相同的东西里就是会有一类不该动的——这与 §3.2 那 4 处是同一个道理。*

**搜索面(负结论要交代)**:57 处补全逐处读过所在整行;另用
`git diff -U0 -- reports/ | grep -E '^\+[^+]' | grep -nE '裸|补成|补全|解析不到|无法解析|不能解析|同名|歧义|候选'`
扫一遍「讨论锚点形态」的词根,3 行命中,人工判定只有 `round-10b:161` 这一处是 use-mention
(另两处一处是能力点描述里的「候选答案保底」、一处是 M-8 定案行里的「全部候选引用」,
都与锚点形态无关)。**词根表只入复核队列、不自动改判**,沿用 R11C 那条。

### 2.4 九份报告的勘误节清单

每份报告文末新增一节 `## 勘误(R11D:锚点寻址补全)`,内含该报告逐处的「原样 → 补全后」对照。

| 报告 | 补全处数 | 该报告此前有无勘误节 |
|---|---:|---|
| `reports/round-1-capabilities-full.md` | 30 | 有(R8-fix) |
| `reports/round-1-survey.md` | 7 | 有(R8-fix) |
| `reports/round-8-fix-review-1.md` | 7 | 有(R8C) |
| `reports/round-9c-external-interfaces.md` | 5 | 无,本轮新建 |
| `reports/round-4-execution-environments.md` | 3 | 无,本轮新建 |
| `reports/round-10-client-interface-layer.md` | 1 | 有(R10B) |
| `reports/round-2-turn-loop.md` | 1 | 无,本轮新建 |
| `reports/round-8a-configuration-surface.md` | 1 | 有(R8-fix) |
| `reports/round-8b-cli-trunk-and-interaction.md` | 1 | 有(R8-fix / R8C) |

已有勘误节的五份**不动旧节**,在文末另起一节并列,理由与 `reports/` 正文不静默改写同源:
旧勘误节是当时那一轮的记录。

对照表用 ```` ```text ```` 声明式非源码块承载(八份)。第九份
`reports/round-8-fix-review-1.md` 改用引用块,理由见 §4——那一份的围栏奇偶是坏的。

### 2.5 关卡读数:一个字没变,而这正是应该发生的事

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent reports/*.md | tail -4
```

```text
citations=742  OK=204  UNCHECKED=538
可校验比例 OK/742 = 27.5%  << 低于 70% 下限
table_anchors=117  OK=46  UNCHECKED=71   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
OK: every code-block-backed citation matches the baseline
```

这一段输出与改动前**逐字相同**(改动前的存档在 `data/r11d/anchor-gate-reports-before.txt`)。
原因是 `verify_citations.py` 的解析器**不做后缀匹配**:

`scripts/verify_citations.py:713 @ df6d450`

```python
    def resolve(pth):
        t = repo / pth
        # A note may legitimately cite this study repo's own files (prior-round
        # reports, chapters). Resolve against the baseline first, then locally.
        if not t.is_file() and (STUDY_ROOT / pth).is_file():
            t = STUDY_ROOT / pth
        return t
```

裸 `conversation_loop.py` 解析成 `<基线>/conversation_loop.py`,不是文件;
但这些锚点**都不紧跟代码块**(它们在散文与表格里),于是无论解析得到与否都记 UNCHECKED,
补全前后落在同一格。**所以这项工作的受益方是读者,不是关卡**——
`CLAUDE.md` 硬标准 8 说得很直接——对那个「不看源码」的目标读者,一个裸文件名加行号
不是引用,是谜题:

`CLAUDE.md:480 @ df6d450`

```
   对那个"不看源码"的目标读者,`base.py:781-875` 不是引用,是谜题。
```

**唯一会改变关卡读数的一类是被 ccTLD 守卫挡住的锚点**(`sh` / `js` / `rs` 同时是国家域名后缀,
无目录部分且不可解析时不算锚点):§2.3 那个 `build.sh` 锚点补成全路径后会让它
从「连分母都进不去」变成一条真锚点,`citations` 742 → 743。而它恰好就是撤回的那一处,
所以本片实测没有发生。

### 2.6 落盘前的负控:待改写位置一处都不在真围栏里

宽口径(照抄关卡的 `^\s*```)会把散文误判成围栏,**漏判会少改(安全),误判才会改进摘录里
(伪造证据)**。所以落盘前用一条更严的围栏正则做断言:每一处待改写位置在严格口径下也必须在围栏外。

```verify
cd /home/user/hermes-study && python3 data/r11d/probes/anchor_completion_r11d.py --audit-fences
```

```text
== 负控:待改写位置 vs 严格围栏口径 ==
  落在严格围栏内部的待改写位置:0  (必须为 0)
  两种口径分歧的围栏行(宽口径认、严格口径不认):2
    reports/round-8-fix-review-1.md:414
    reviews/review-1-full-corpus.md:1313
```

0 处落在真围栏里,断言成立。**而它顺带点出的那 2 行,就是 §4 那条关卡缺陷的全部来源。**
(这条负控在 `--apply` 时是前置条件:不过就拒绝落盘。)

---

## 3. `reviews/`:一个字没改,20 处全部走附录

### 3.1 附录形态

新建 `reviews/review-1-anchor-corrections.md`,四节:

| 节 | 内容 |
|---|---|
| §1 | 20 处裸文件名 → 全路径对照(拆成三类:15 处散文 / 4 处校验器输出转录 / 1 处奇偶盲区) |
| §2 | 4 处至今仍红的引用失败逐条查清(锚点 / 现象 / 真实位置 / 为什么不就地改) |
| §3 | 围栏奇偶翻转这条关卡缺陷 |
| §4 | 未处理的部分(17 处多候选锚点,如实说明不给结论) |

裁定给的理由不是「改起来危险」,而是**评审是另一方的话**:自己动手改评审对自己的措辞,
这件事本身就不该做。装订后不误导读者的保证在于 `reviews/` 不进《设计蓝图》正文,
而附录与原文同目录并列。

### 3.2 20 处里有 4 处根本不是缺陷 —— 校验器打的就是基名

`reviews/review-1-full-corpus.md` 的 `:562` `:563` `:603` `:604` 四处裸文件名,**写在围栏块里,
而块的内容是 `verify_citations.py` 打印的原始输出**。校验器打的就是文件基名:

`scripts/verify_citations.py:584 @ df6d450`

```python
        tag = f"{note.name}:{lineno}"
```

`Path.name` 是基名。**于是任何一份逐字转录该脚本输出的文档,天生就带裸文件名**——
补它反而是把一段真实输出改成假的。所以 R11C 移交时报的「`reviews/` 20 处」,
**真正可动的是 16 处**,而 16 处按裁定也一处不动。

*这与 §2.3 的 use-mention 是同一个形状:机械判据抓的是形状,而形状相同的东西里
有一类是不该动的。**「可机械补全」不能直接当成待办清单。***

### 3.3 4 处历史失败的真实位置

四处全部查清,内容全部为真,失败原因全在「地址怎么写」:

| 评审卷位置 | 现象 | 真实位置 | 性质 |
|---|---|---|---|
| `reviews/review-1-full-corpus.md:281` 的 `gateway/platforms/base.py:3991` | BLOCK-DRIFT | 五行分别在 `:3991`/`:4062`/`:4205`/`:4232`/`:4305`,逐字为真 | 合成摘录撞上「单起点连续块」契约 |
| `reviews/review-1-full-corpus.md:577` 的 `chapters/r7b-platform-integration.md:473` | MISMATCH | `38b65bb` 那一版在 `:474`,块为 474-483 | 真漂移 1 行 |
| `reviews/review-1-full-corpus.md:643` 的 `scripts/verify_citations.py:141` | MISMATCH | `38b65bb` 那一版在 `:142-145`;工作树已移到 `:825` 一带 | 缺 commit 钉子 + 早一行 |
| `reviews/review-1-full-corpus.md:777` 的 `tools/approval.py:3767` | MISMATCH | 基线 `:3766`,块引六行 3766-3771 | 真漂移 1 行 |

第一处最值得展开。评审卷用的是一个**逗号串锚点**:

`reviews/review-1-full-corpus.md:281 @ df6d450`

> `gateway/platforms/base.py:3991,4062,4205,4232,4305 @ 863e313`

它挂着一个**五处各取一行**的合成块,而围栏块的契约是「块正文第 k 行对比基线
`起始行号-1+k` 行」,它假定块是一段**连续**源码。校验器只读第一个数,于是拿块的第 2 行去比 `:3992`:

`gateway/platforms/base.py:3992 @ 863e313`

```python
        self,
```

而块的第 2 行是 `async def send_voice(`,它的真实位置在:

`gateway/platforms/base.py:4062 @ 863e313`

```python
    async def send_voice(
```

**内容全对,形式不在契约内。** 正确写法就是拆成五个各自带锚点的块——
`CLAUDE.md` 早有明文:「摘录要跳段时,**优先拆成两个各自带锚点的块**,而不是打省略标记」。
附录 §2.1 已经按这个写法把五行各自钉好,五个块都受校验。

第三处顺带证实了 R11D commit 钉子那条裁定的必要性。评审卷那一条锚点写的是:

`reviews/review-1-full-corpus.md:643 @ df6d450`

> (`scripts/verify_citations.py:141-145`):

没有钉子,校验器只能读工作树最新版,而那句注释已随脚本大改移出六百多行,
`±40` 行的搜索窗口**原理上够不到**,于是报的是 `not found` 而不是「漂了几行」——
**一个测不出漂移距离的失败,读者无从判断它是漂了还是根本不存在。**

### 3.4 关卡读数(评审卷不变,附录新增)

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent reviews/review-1-full-corpus.md | tail -5
```

```text
citations=96  MISMATCH=3  OK=30  UNCHECKED=63
可校验比例 OK/96 = 31.2%  << 低于 70% 下限
BLOCK-DRIFT=1  (代码块首行之后的行与基线不符;**阻断**,见脚本 block_drift() 的说明)
table_anchors=31  UNCHECKED=31   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
FAIL: 4 citation(s) need fixing
```

**评审卷这一份仍然红着,且本轮有意不修**——这是裁定的直接代价,不是遗漏。
`reviews/` 不在每轮 commit 前的强制关卡范围内(强制范围是 `chapters/` 全部 + 当轮
`notes/` 与 `reports/`),所以它不阻断本轮。

新附录自己是绿的:

```verify
cd /home/user/hermes-study && python3 scripts/verify_citations.py /home/user/hermes-agent reviews/review-1-anchor-corrections.md | tail -4
```

```text
citations=17  OK=10  UNCHECKED=7
可校验比例 OK/17 = 58.8%  << 低于 70% 下限
table_anchors=40  UNCHECKED=40   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
OK: every code-block-backed citation matches the baseline
```

附录的 40 处 `table_anchors` 全部 UNCHECKED,是对照表两列各一个锚点、格内不带声明式摘录所致;
按 `CLAUDE.md`,表格锚点是**单独计数、不并入可校验比例**的一族,不稀释块级指标。

---

## 4. 副产物:一句散文能把半份文件从检查面上抹掉

### 4.1 现象

`verify_citations.py` 认围栏靠一条正则:

`scripts/verify_citations.py:318 @ df6d450`

```python
FENCE = re.compile(r"^\s*```(?P<lang>[A-Za-z0-9_+-]*)")
```

而本项目**自己在用**的标准写法是四反引号转义:一句散文里谈论 ```` ```verify ```` 块时,
那一行是「缩进 + 四个反引号 + 空格 + 三个反引号 + verify ...」。它命中了上面这条正则,
于是**被当成一个围栏开头**。没有配对的结尾,后果是从那一行到文件末尾,
关卡的主循环认为自己一直在围栏里,**一条锚点也不扫**:

`scripts/verify_citations.py:745 @ df6d450`

```python
        if FENCE.match(line):
            i += 1
            while i < len(lines) and not FENCE.match(lines[i]):
                i += 1
            i += 1
            continue
```

### 4.2 普查

判据用两条:宽口径 = 关卡自己的正则;命中 = 宽口径认、但这一行**明显是散文**
(行内含中日韩字符,或开头那串反引号之后还有一串反引号)。

*不用「整行只有反引号 + 语言标记」当严格口径:实测那样会把列表里缩进 4 格的正常围栏、
以及 `` ```356:365:/path/to.py `` 这种带行号信息串的正常围栏一并算成命中(22 处里 20 处是这么来的)。
**普查一旦把正常写法算成缺陷,读者就会开始忽略它**——与本项目「声明,不靠嗅探」同一条理由。*

读数**钉在本轮开工点 `df6d450`**,不是工作树——工作树里同轮其他片正在写文件,
一个「量之前」的数不能钉在会长出东西的引用上(`CLAUDE.md` R11C 那条,本片顺带又验了一次,
见 §4.4)。命中行的原文含三反引号,默认不打印(打印会把配对的 text 块当场截断,见 §4.3 同源的坑),
要看原文加 `--show-lines`。

```verify
cd /home/user/hermes-study && python3 data/r11d/probes/fence_parity_r11d.py --rev df6d450
```

```text
命中文件 3 份,散文误判为围栏的行 3 处;盲区正文行 931 行,其中锚点 68 处
notes/r7-raw-stream-consumer.md  触发行 121  盲区 624 行 / 锚点 34 处
reports/round-8-fix-review-1.md  触发行 414  盲区 15 行 / 锚点 1 处
reviews/review-1-full-corpus.md  触发行 1313  盲区 292 行 / 锚点 33 处
```

三处触发行的原文分别是:`notes/r7-raw-stream-consumer.md:121` 一句以三反引号开头的中文散文
(「…… 区域,避免代码块内部的 …… 污染计数。」);`reports/round-8-fix-review-1.md:414`
与 `reviews/review-1-full-corpus.md:1313` 分别是缩进后谈论 verify 围栏与 mermaid 围栏的一句话。

**这比 UNCHECKED 更隐蔽**:UNCHECKED 至少出现在分母里,这些行连分母都进不去——
与 R10B「白名单外的锚点连分母都进不去」是同一物种,与 R9B「表格里的锚点恒记 UNCHECKED、
从不被比对过」也是同一物种。三次了。

### 4.3 反噬:声明式豁免在盲区里会反向失效

**这一条是本片自己踩出来的,值得原样留着。**
九份勘误节的对照表,第一版全部写成 ```` ```text ````(声明式非源码,块内不该被扫)。
落盘后跑关卡,`reports/*.md` 的 `citations` 从 742 涨到 **749**,多出的 7 处全部来自
`reports/round-8-fix-review-1.md`。

原因:该文件 `:414` 起是幻影围栏,我那个 ```` ```text ```` 的**开头**反而**闭合**了它,
于是表内 7 行落在「围栏外」被当散文扫,7 个裸锚点被重新数了一遍。
**在奇偶已经坏掉的区域,一个声明式非源码块的作用是反的。**

改法:那一份的对照表改用引用块。`>` 在两种奇偶状态下都不被扫描——
关卡对引用块的处理是「整段跳过,不扫锚点」,与它在不在围栏内无关。改完读数回到 742,
与改动前逐字相同(§2.5)。

*为什么不去修 `:414` 那句散文:它是标准写法、markdown 本身完全正确,
问题在关卡的正则;而按裁定,「补全之外正文一个字不动」。修法属 `scripts/` 范围,
本片无权限,已作移交(§5 H-R11D-A-a)。*

### 4.4 工作树读数为什么不钉

同一条命令不加 `--rev` 跑工作树,读数会比 `df6d450` 大,而且**在本轮结束前一直在变**:

- 本片给 `reports/round-8-fix-review-1.md` 追加的勘误节**必然落在该文件的盲区里**
  (盲区一直延伸到文件末尾),这没法避开,只能说清楚——盲区从 15 行涨到 51 行、锚点 1 → 2;
- 更关键的是,**同轮其他片正在写的底稿也会进这个语料**:本片收工时工作树里已经
  出现了 `notes/r11d-raw-handover-disposition.md`(另一片的在途产出),它自己也有一处触发行。

所以这个数**不钉**,只钉 `--rev df6d450`。这正是 `CLAUDE.md`「量『之前』的命令不许钉在
会移动的引用上」那一条:R11C 已记过五次「没有一次是靠人看出来的」,本片这一次是靠
`verify_evidence_commands.py` 当场判 `EVIDENCE-DIFF` 才发现的——**机制抓住的,不是自觉**。

要看当下读数(不作为本片证据):

```verify
cd /home/user/hermes-study && python3 data/r11d/probes/fence_parity_r11d.py
```

---

## 5. 移交

| 案号 | 锚点 + 一句话现象 | 去向 |
|---|---|---|
| **H-R11D-A-a** | `scripts/verify_citations.py:745`:`if FENCE.match(line):` —— 主循环见围栏行即跳到下一个围栏行,而认围栏的正则(`:318`)会把一句缩进散文里提到的围栏标记也算上,于是**翻转其后整份文件的奇偶**;全语料 3 处、931 行正文 / 68 处锚点(钉 `df6d450`)从不进检查面,且声明式非源码块在盲区内作用相反(§4)。修法属 `scripts/`,本片无权限 | 下一轮 |
| **H-R11D-A-b** | `reviews/review-1-full-corpus.md:281` 的逗号串锚点,其合成块首行见 `reviews/review-1-full-corpus.md:284`:`async def send_animation(` —— 一个锚点挂五处各取一行的合成摘录,而 BLOCK-DRIFT 契约假定块是连续源码、只读第一个数;是该支持这种写法,还是该在关卡里显式判它「不是合法锚点形态」,未定 | 下一轮 |
| **H-R11D-A-c** | `reports/round-10b-desktop-application.md:161`(该行原文见 §2.3 的引用块)—— use-mention:锚点被当作对象讨论(原句用「裸」字修饰它),机械补全会让该句自我否定,本片撤回。判据「候选唯一」看不见 use 与 mention 的区别,后续同类批量作业须有人工复核环节。*本行的锚点无法写成声明式:该行唯一的反引号片段就是那个锚点本身,而关卡明令排除「摘录即锚点」,故它必记 TABLE-UNCHECKED* | 下一轮 |
| **H-R11D-A-d** | `reviews/review-1-full-corpus.md:646`:`# A prose line may carry several citations (the call site AND the callee).` —— 该摘录上方 `:643` 的自引锚点无 commit 钉子,校验器读工作树,±40 窗口原理上够不到,报 `not found` 而非漂移距离;评审卷按裁定不改,正确写法 `@ 38b65bb` 已记在附录 §2.3 | 下一轮 |
| **H-R11D-A-e** | `data/r11c/d-anchor-resolution-fix2.py:103`:`fit = [c for c in cands if len(src(c)) >= n]` —— R11C 片 D 第二遍的「长度判据」只跑过 `notes/`;`reports/` 与 `reviews/` 合计 **104 处**多候选裸锚点(`reports` 87 / `reviews` 17)本片一处未动,同样的两条判据(长度 + 内容)可以铺到这两个目录 | 下一轮 |

**H-R11D-A-a 可能与同轮另一片撞车,请主线并案。** 收工时工作树里已出现
`data/r11d/probes/fence_balance_check.py`(非本片产出,其所属底稿本片收工时尚未到货),
它查的是同一个缺陷。两者判据不同,**并案时要保留的是判据本身,不是其中一份**:

| 探针 | 判据 | 抓不到的形态 |
|---|---|---|
| `data/r11d/probes/fence_balance_check.py:8`:`本探针只回答一件事:每份文件的行首围栏标记是不是偶数个;不是的,点名。` | 整份文件行首围栏标记**个数为奇数** | 一份文件里有**两句**这样的散文时奇偶又变回偶数,但两句**之间**那一整段仍是反的 |
| `data/r11d/probes/fence_parity_r11d.py:43`:`def prosey(line: str) -> bool:` | 逐行判「宽口径认它是围栏、但它明显是散文」(含中日韩字符,或反引号串之后还有反引号串) | 一句纯英文、又不用四反引号转义的散文围栏行 |

本轮语料里每个命中文件恰好只有 1 处触发行,所以两条判据当前给出同一批文件;
**这是巧合,不是等价。** 案号按案号纪律带了片标识(`H-R11D-A-a`),
若另一片也铸了号,主线并成一个即可——一个案号只指一个实体。

**本片未做、也不该由本片做的**:`reviews/review-1-full-corpus.md` 那 4 处失败按裁定不修,
故 `python3 scripts/verify_citations.py /home/user/hermes-agent reviews/*.md` **退出码仍为 1**。
它不在每轮 commit 前的强制关卡范围内。

---

## 6. 收工自校验读数

*(以下是「跑校验器扫本底稿」的输出,按 `CLAUDE.md` 贴在 ```` ```text ```` 里、
**不写进 ```` ```verify ```` 块**——那会让关卡重跑一条扫自己的命令,无限递归。)*

**① 引用校验 · 本底稿**(`python3 scripts/verify_citations.py /home/user/hermes-agent notes/r11d-raw-anchor-completion.md`,退出码 0):

```text
citations=14  OK=11  UNCHECKED=3
可校验比例 OK/14 = 78.6%
table_anchors=20  OK=6  UNCHECKED=14   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
OK: every code-block-backed citation matches the baseline
```

**可校验比例 78.6%,过 70% 下限。** 分母口径:本片是**元工作片**(研究本仓库自己的语料与关卡),
按 `CLAUDE.md` 该形态仍用「当轮 notes 单独 / 下限 70% 不下调」,且自引锚点须带 commit 钉子才计分子
——本底稿 11 条 OK 里有 5 条是带 `@ df6d450` / `@ 38b65bb` 钉子的自引锚点,它们**因为钉子才进得了分子**。
表格锚点声明率 `table_anchors=20 OK=6` 单独报,不并入上面那个比例。
移交表 5 行里 4 行是声明式(TABLE-OK),第 5 行(H-R11D-A-c)在行内写明了它为什么写不成声明式;
另 2 条 TABLE-OK 来自 §5 那张并案对照表。

**② 证据命令校验 · 本底稿**(`python3 scripts/verify_evidence_commands.py notes/r11d-raw-anchor-completion.md`,退出码 0):

```text
verify-blocks paired=8  unpaired=1  differing=0  timedout=0
runnability   ran=1  runfail=0  skipped-mutating=0
OK: every paired ```verify command reproduces its pasted output
```

**③ 引用校验 · `reports/` 全量**(退出码 0,与改动前逐字相同):

```text
citations=742  OK=204  UNCHECKED=538
可校验比例 OK/742 = 27.5%  << 低于 70% 下限
table_anchors=117  OK=46  UNCHECKED=71   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
OK: every code-block-backed citation matches the baseline
```

**④ 引用校验 · `reports/` + `reviews/`**(退出码 **1**,4 处失败全部落在 `reviews/review-1-full-corpus.md`,按裁定不改):

```text
citations=855  MISMATCH=3  OK=244  UNCHECKED=608
可校验比例 OK/855 = 28.5%  << 低于 70% 下限
BLOCK-DRIFT=1  (代码块首行之后的行与基线不符;**阻断**,见脚本 block_drift() 的说明)
table_anchors=188  OK=46  UNCHECKED=142   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
FAIL: 4 citation(s) need fixing
```

**⑤ 回归 · `chapters/` 未受影响**(本片一个字没动 `chapters/`,退出码 0):

```text
citations=479  OK=386  UNCHECKED=93
可校验比例 OK/479 = 80.6%
table_anchors=33  OK=5  UNCHECKED=28   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
OK: every code-block-backed citation matches the baseline
```

**⑥ 基线只读**(`git -C /home/user/hermes-agent status --porcelain | wc -l`):

```text
0
```

### 6.1 一条如实申报:被改的 9 份报告里有 4 处历史 EVIDENCE-DIFF,不是本片造成的

对那 9 份跑 `verify_evidence_commands.py`,得 `paired=12 unpaired=2 differing=4`,退出码 1。
把同样 9 份的 **HEAD 版本**取出来跑,得到**完全相同的** `paired=12 unpaired=2 differing=4`
与同样 4 个点名文件(`round-10-client-interface-layer.md` × 3、`round-9c-external-interfaces.md` × 1)
——**改动前后一字不差,所以不是本片造成的**。

内容是各轮当时钉下的台账读数(如 `R1-inventoried` 剩余 `7785 文件 / 1988790 行`,
今日复算是 `5944 文件 / 1495470 行`)。这正是 `CLAUDE.md` 把强制范围限定为
「`chapters/` 全部 + **当轮** `notes/` 与 `reports/`」的原因:历史轮次的读数会随台账推进而变,
把它们纳入强制范围等于要求每一轮为历史读数返工。本片不动它们,只报出来。

---

## 7. 完成信号

片 A 三项产出全部到货:

1. `reports/` 9 份就地补全 56 处 + 各自文末勘误节;
2. `reviews/review-1-anchor-corrections.md` 附录(20 处对照 + 4 处失败定位 + 奇偶缺陷 + 未处理项);
3. 探针 `data/r11d/probes/anchor_completion_r11d.py`、`data/r11d/probes/fence_parity_r11d.py`,
   数据 `data/r11d/anchor-completion-applied.tsv`、`anchor-completion-before.tsv`、
   `anchor-completion-after.tsv`、`anchor-gate-reports-before.txt`、`anchor-gate-reports-after.txt`、
   `anchor-gate-reviews.txt`、`anchor-gate-final.txt`、`fence-parity-census.txt`。

`data/inflight/r11d-a-anchor-completion.claim` 由主线在收到本信号后关闭,本片不动它。
