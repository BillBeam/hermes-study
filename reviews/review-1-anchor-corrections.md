# review-1 锚点勘误附录(R11D)

> 本文件是 `reviews/review-1-full-corpus.md` 的**附录**。评审卷原文**一个字未改**,
> 本附录只做两件事:(1) 把它 20 处写成裸文件名的锚点给出可从仓库根解析的全路径;
> (2) 把它 4 处至今仍红的引用失败逐条查清、给出真实位置。
> 装订后读者拿着这一份就能把评审卷里的每一条引用读对。
>
> 溯源约定同全仓:基线锚点为 `路径:行号 @ 863e313`;指向本仓库自己的锚点带 commit 钉子
> (如 `@ 38b65bb`),否则读的是工作树最新版。

---

## 0. 为什么是附录,不是就地改

`CLAUDE.md`「历史产出的改法」下,R11D 新增了第四类改动:

> **锚点寻址修正是第四类改动,与「行号漂移」同级。** 一条锚点由**它指向谁**(结论)与
> **怎么写出这个地址**(寻址)两部分组成……凡是会改变「指向谁」的改动,一律不在本例外内。

据此,`reports/` 的 56 处同类锚点已**就地补全 + 文末勘误节点名**。
`reviews/` 走另一条:**原文仍不改**,理由不是改起来危险,而是**评审是另一方的话**
——自己动手改评审对自己的措辞,这件事本身就不该做。所以改为另立本附录,
这正是「仲裁与处置结果另立文件或附录」已经给好的机制。

---

## 1. 二十处裸文件名锚点的全路径

**判据只有一条**:基线 `863e313`(或本仓库)里**恰好一个**文件的路径以这个串结尾
(按目录边界匹配)。多候选的一律不给结论——`__init__.py` 有 171 个候选、`base.py` 有 9 个,
猜错比不修更糟,一个指向错文件的锚点看起来完全正常。
下表右列即读者应当使用的地址。

### 1.1 十五处散文位置(直接按右列取地址)

| 评审卷行 | 原锚点 | 应读作 |
|---:|---|---|
| 715 | `session_context.py:74-82` | `gateway/session_context.py:74-82` |
| 726 | `session_context.py:46` | `gateway/session_context.py:46` |
| 1031 | `ADDING_A_PLATFORM.md:135` | `gateway/platforms/ADDING_A_PLATFORM.md:135` |
| 1032 | `ADDING_A_PLATFORM.md:66-70` | `gateway/platforms/ADDING_A_PLATFORM.md:66-70` |
| 1033 | `tool.py:1330` | `tools/computer_use/tool.py:1330` |
| 1033 | `cua_backend.py:2050-2053` | `tools/computer_use/cua_backend.py:2050-2053` |
| 1187 | `ADDING_A_PLATFORM.md:103` | `gateway/platforms/ADDING_A_PLATFORM.md:103` |
| 1189 | `docker.py:1958-1969` | `tools/environments/docker.py:1958-1969` |
| 1193 | `models_dev.py:11` | `agent/models_dev.py:11` |
| 1193 | `tool_result_storage.py:172-178` | `tools/tool_result_storage.py:172-178` |
| 1195 | `session_context.py:74-128` | `gateway/session_context.py:74-128` |
| 1197 | `approval.py:3767-3775` | `tools/approval.py:3767-3775`(**行号另有 1 行漂移,见 §2.4**) |
| 1202 | `ADDING_A_PLATFORM.md:135` | `gateway/platforms/ADDING_A_PLATFORM.md:135` |
| 1202 | `cua_backend.py:2050-2053` | `tools/computer_use/cua_backend.py:2050-2053` |
| 1211 | `env_loader.py:669` | `hermes_cli/env_loader.py:669` |

### 1.2 四处**不是缺陷**——它们是校验器输出的逐字转录

| 评审卷行 | 原样 | 它指的是 |
|---:|---|---|
| 562 | `r4-execution-environments.md:112` | `chapters/r4-execution-environments.md:112` |
| 563 | `r7b-platform-integration.md:471` | `chapters/r7b-platform-integration.md:471` |
| 603 | `round-1-capabilities-full.md:342` | `reports/round-1-capabilities-full.md:342` |
| 604 | `round-1-capabilities-full.md:826` | `reports/round-1-capabilities-full.md:826` |

**这四处写在围栏块里,而块的内容是 `verify_citations.py` 打印的原始输出。**
校验器打的就是**文件基名**,不是全路径:

`scripts/verify_citations.py:584 @ df6d450`

```python
        tag = f"{note.name}:{lineno}"
```

`Path.name` 是基名。**于是任何一份逐字转录该脚本输出的文档,天生就带裸文件名**——
这不是作者写错,改它反而会把一段真实输出改成假的。列在这里只是给读者做地址换算。

*顺带一条给关卡的启示:这四处能被机械普查捞出来,恰恰说明「可机械补全」这个判据
**不能直接当成待办清单**——它抓的是形状,而形状相同的东西里有一类是不该动的。
R11C 移交时报的「`reviews/` 20 处」,真正可动的是 16 处。*

### 1.3 一处落在围栏奇偶盲区里

| 评审卷行 | 原锚点 | 应读作 |
|---:|---|---|
| 1606 | `config_defaults.py:2129` | `hermes_cli/config_defaults.py:2129` |

它在散文里,不在围栏里;但由于 §3 说的那条奇偶翻转,**校验器把它算在「围栏内部」而从不读它**。

---

## 2. 四处至今仍红的引用失败

评审卷现在跑 `verify_citations.py` 是 **3 处 MISMATCH + 1 处 BLOCK-DRIFT**,退出码非零。
这四处都是历史遗留,**按裁定不就地改**,逐条查清如下。

### 2.1 BLOCK-DRIFT · 评审卷 `:281` —— 合成摘录 vs 单起点契约

**锚点**:`gateway/platforms/base.py:3991,4062,4205,4232,4305 @ 863e313`
**现象**:`块内第 2 行与 3992 行不符(共 4 行不符)`。

**内容其实全对。** 那个块是**五处各取一行**的合成摘录,五行分别逐字命中它们各自的行号
(以下五个块每个都带自己的锚点,因此全都受校验):

`gateway/platforms/base.py:3991 @ 863e313`

```python
    async def send_animation(
```

`gateway/platforms/base.py:4062 @ 863e313`

```python
    async def send_voice(
```

`gateway/platforms/base.py:4205 @ 863e313`

```python
    async def send_video(
```

`gateway/platforms/base.py:4232 @ 863e313`

```python
    async def send_document(
```

`gateway/platforms/base.py:4305 @ 863e313`

```python
    async def send_image_file(
```

**为什么仍判失败**:围栏块的契约是「块正文第 k 行对比基线 `起始行号-1+k` 行」,
它假定块是**一段连续源码**。逗号串锚点不在这个契约里,校验器只读第一个数 `3991`,
于是拿块的第 2 行去比 `3992`(那是 `self,`)。
**正确写法就是上面这五个块**——`CLAUDE.md` 对此已有明文:「摘录要跳段时,
**优先拆成两个各自带锚点的块**,而不是打省略标记」。

**读者结论不受影响**:评审卷那一段要说的是「这五个媒体方法在基类里确实都有实现」,
五行逐字为真,判断成立。

### 2.2 MISMATCH · 评审卷 `:577` —— 全语料唯一手写 commit 钉子的锚点,漂了 1 行

**锚点**:`chapters/r7b-platform-integration.md:473-482@38b65bb`
**现象**:`-> actually at [474]`。
**真实位置**:在 `38b65bb` 那一版,块首行在 **474**,整块是 **474-483**。

`chapters/r7b-platform-integration.md:474 @ 38b65bb`

```
1. 清洗引号/尾标点
```

**这一条的经历值得单记。** 它是全语料**唯一**一条早在评审当时就手写了 commit 钉子的自引锚点,
而 R11D 之前的校验器不认钉子——`38b65bb` 被当成锚点后面的噪音丢掉,校验器去读工作树最新版,
自然「找不到」。R11D 让校验器用 `git show` 取钉住的那一版,它才从「找不到」变成
「实际在 474 行」:**一条真漂移被自己的正确写法藏了整整一轮**,因为工具还没跟上写法。

### 2.3 MISMATCH · 评审卷 `:643` —— 自引锚点没钉子,读的是一棵已经走远的树

**锚点**:`scripts/verify_citations.py:141-145`(无 commit 钉子)
**现象**:`-> not found within +/-40`。

**两个读数,口径不同,都要报**:

- **在被评审的那一版 `38b65bb`**:摘录的四行在 **142-145**,锚点写 `141-145`——早一行、且多算一行。

  `scripts/verify_citations.py:142 @ 38b65bb`

  ```python
        # A prose line may carry several citations (the call site AND the callee).
  ```

- **在当前工作树**:同一句注释已随脚本大改移到 `scripts/verify_citations.py:825` 一带,
  离 `:141` 六百多行——`±40` 行的搜索窗口原理上够不到,所以报的是 `not found`,不是「漂了几行」。

**正确写法**是 `scripts/verify_citations.py:142-145 @ 38b65bb`:钉子既保住原始证据
(不把过去改写成对的),又让它重新可校验。

### 2.4 MISMATCH · 评审卷 `:777` —— 纯 1 行漂移

**锚点**:`tools/approval.py:3767-3775 @ 863e313`
**现象**:`-> actually at [3766]`。
**真实位置**:块首行在基线 **3766**,块引的六行是 **3766-3771**
(`3772-3775` 是该守卫的其余部分,块里并未引用)。

`tools/approval.py:3766 @ 863e313`

```python
    # == Sudo stdin guard ==
```

**评审结论不受影响**:那一条讲的是「两道地板之间还有第三道(sudo stdin guard)」,
守卫存在、注释自称 unconditional、位置在 hardline 之后 yolo 之前,全部为真。

### 2.5 为什么这四处都不就地改

行号漂移本来是 `reports/` 那条「唯一例外」允许就地改的;`reviews/` 不共享这条例外,
理由与 §0 相同:**评审是另一方的话**。代价是评审卷这一份会**一直红着**——
这是有意接受的代价,不是遗漏。要机械核验,请用本附录 §2 里那些带锚点的块,它们受校验。

---

## 3. 一句散文翻掉了后半份文件的围栏奇偶

`reviews/review-1-full-corpus.md:1313` 是一句**散文**:缩进三格,开头是三个反引号紧跟 `mermaid`,
之后直接接中文(「……围栏(围栏语言标记全部正确),其中 224 个节点标签,剥去 `<br/>` 后」)。
本附录不把这一行照抄进引用块,因为照抄进去会在渲染时**真的开一个围栏**,
把附录后半段吞掉——这句话的破坏性正是它自己的例证。

而校验器认围栏的判据是**「行首(可带空白)三个反引号」**这一条正则:

`scripts/verify_citations.py:318 @ df6d450`

```python
FENCE = re.compile(r"^\s*```(?P<lang>[A-Za-z0-9_+-]*)")
```

于是**这句散文被当成了一个围栏开头**。它没有配对的结尾,后果是从 `:1313` 到文件末尾,
校验器认为自己一直在围栏内部,**一条锚点也不扫**——§1.3 那一处就是这样活下来的。

**这不是一份文件的偶发问题。** 全语料同形状 **3 处**(见
`data/r11d/probes/fence_parity_r11d.py`),合计 **931 行正文 / 68 处锚点**从不进检查面
(读数钉在 R11D 开工点 `df6d450`;工作树读数会随本轮自己的产出变,故不钉):

| 文件 | 触发行 | 盲区(钉 `df6d450`) |
|---|---|---|
| `notes/r7-raw-stream-consumer.md` | `:121` | 624 行 / 34 处锚点 |
| `reviews/review-1-full-corpus.md` | `:1313` | 292 行 / 33 处锚点 |
| `reports/round-8-fix-review-1.md` | `:414` | 15 行 / 1 处锚点 |

**它比 UNCHECKED 更隐蔽**:UNCHECKED 至少出现在分母里,这些行连分母都进不去——
与 R10B「白名单外的锚点连分母都进不去」是同一物种。
更难看的一面是**声明式豁免在这里会反向失效**:`reports/round-8-fix-review-1.md` 的 R11D 勘误节
首版把对照表写成 ```` ```text ````(声明式非源码),而那个结尾反而**闭合**了 `:414` 起的幻影围栏,
块内 7 行被当散文扫,关卡 `citations` 当场 742 → 749。改用引用块才躲开——
`>` 在两种奇偶状态下都不被扫描。

已作为移交项 **H-R11D-A-a** 交出(见 `notes/r11d-raw-anchor-completion.md` §5),
处置属 `scripts/` 范围,不在本片权限内。

---

## 4. 未处理的部分(如实说明)

- **多候选锚点一处未动**:评审卷里另有 **17 处**裸文件名是多候选,按出现次数计为
  `tools.md` 3、`tools-runtime.md` 3、`base.py` 3、`prompt-assembly.md` 2、
  `gateway-internals.md` 2、`memory_manager.py` / `configuration.md` / `config.py` /
  `__init__.py` 各 1。基线里 `__init__.py` 有 171 个候选、`base.py` 9 个、
  `config.py` 与 `configuration.md` 各 4 个。**判据给不出唯一答案就不给答案**——
  一个指向错文件的锚点看起来完全正常,猜错比不修更糟。
- **本附录不改评审卷的任何结论**,只处理地址与失败定位。
- **底稿**:取证过程、前后读数、探针见 `notes/r11d-raw-anchor-completion.md`。
