# hermes-study — hermes-agent 系统学习项目

本仓库是学习产出仓库:研究对象是 NousResearch/hermes-agent,所有报告、台账、
脚本、笔记都 commit 到本仓库并 push 到远端。云端会话磁盘不持久:**未推送即视为不存在**。

## 基线(固定,不再移动)

```
repo:   https://github.com/NousResearch/hermes-agent
commit: 863e31318553cda8ad61df681d08175364d4164b
date:   2026-08-06 17:36:40 +0530
title:  fix: close simplify-pass findings — scheduler sibling site + home-unresolvable totality
```

## 会话恢复方式(每个新会话开工前)

```bash
# 1) 恢复学习对象(工作区若无基线源码,先重建;hermes-agent 只读!)
git clone https://github.com/NousResearch/hermes-agent /home/user/hermes-agent
git -C /home/user/hermes-agent checkout 863e31318553cda8ad61df681d08175364d4164b

# 2) 校验台账与基线一致
cd /home/user/hermes-study
python3 scripts/verify_ledger.py /home/user/hermes-agent data/ledger.tsv

# 3) 看进度:reports/ 下最新一轮报告 + data/ledger.tsv 的 status 列
```

## 最终目的(整个学习项目)

1. 能独立讲清 harness 的每一个核心机制:解决什么问题、怎么实现、为什么这么设计、有什么取舍;
2. 能据此独立设计并实现同级别的 agent harness;
3. 全仓每一个源文件都被明确交代(精读 / 结构级理解 / 知悉用途 / 有理由排除),没有黑洞。

## 验收标准(每一轮都要满足)

- **覆盖可校验**:`data/ledger.tsv` 把全仓 8530 个文件全部归层(L1 机制精读 /
  L2 结构级理解 / L3 知悉用途 / L4 有理由排除 / LT 测试=行为规格参照),
  各层行数加总 = 全仓总行数 2,608,452;用 `scripts/verify_ledger.py` 校验并在报告里报数。
  每轮结束把该轮覆盖文件的 `status` 列更新为可翻译成"已学到什么程度"的状态
  (如 `R2-deep-read`、`R3-structure`)。
- **证据格式(R8A 起为脚本可校验的定稿关卡,与台账校验并列)**:凡对 hermes-agent
  行为的断言,紧跟 `路径:行号 @ 863e313` 与代码原文块,使读报告本身即完成验证。
  **锚点一律置于代码块/引用块之前**(R8-fix 定,见下"排版"),不写在块后。
  **每轮 commit 前必须运行的范围(R8-fix 扩面,原为"本轮 notes + chapters"):**

  ```bash
  python3 scripts/verify_citations.py /home/user/hermes-agent \
      chapters/*.md notes/rN-*.md reports/round-N-*.md
  ```

  即 **`chapters/` 全部** + **本轮的 `notes/` 与 `reports/`**。
  *扩面理由(review-1 建议-3 / M-16 实测):原规则是"本轮 notes + chapters",于是
  `chapters/r4-*.md` 里一处无法解析的裸文件名从 R4 起**从未被跑到过**,一直红到 R8B。
  成品章是要装订进 R12 的东西,任何一轮改坏了都得当轮发现。*

  **跑到退出码 0、输出 `OK: every code-block-backed citation matches the baseline` 才算过关**,
  并在报告里报数(citations / OK / UNCHECKED)。`--fix` 只用于**无歧义**的行号漂移,
  用后**必须**不带 `--fix` 再跑一遍确认。三类块的判定规则(R8-fix 定稿):

  | 块 | 契约 | 不匹配时 |
  |---|---|---|
  | ```` ``` ```` 围栏 | **逐字源码摘录** | MISMATCH(失败),无论别处找不找得到 |
  | `>` 引用块 | 文档摘录**或**转述 | 只有在该文件邻近处**逐字找得到**才判 MISMATCH(证明是真摘录、只是锚点漂了);找不到记 UNCHECKED |
  | ```` ```text/console/verify/shell-session ```` | **作者声明这不是源码** | UNCHECKED |

  *引用块纳入校验的理由(review-1 建议-15 / M-16a 实测):此前只校验紧跟围栏块的引用,
  于是"文档-代码冲突"定案的**文档侧**——几乎总写成 `>` 引用块——**从未被任何自动校验覆盖**。
  评审位随手抽 5 条文档锚点,**5 条全漂**。代码侧有脚本兜着所以稳,文档侧只有人工约定所以漂;
  R7C 当初升格这个脚本的理由,原封不动地适用于文档侧。*
  *非源码围栏用显式语言标记而不是靠脚本"看着不像代码"来猜:一个猜出来的豁免会悄悄削弱关卡,
  而这是一个阻断性关卡最不能有的性质。*

  **单文件 UNCHECKED 比例提示(R8C 增,非阻断)**:任一文件的引用数 ≥5 且 UNCHECKED 占比
  **≥90%** 时,脚本打印「疑似锚点排版不合规」并点名该文件。**它不改退出码**——
  一份天然全是散文引用的成品章不该被逼着为了过关去造代码块。
  *为什么需要它(R8C 实测,可零成本复现):造一份 5 条引用**全部逐字正确、行号全对**、
  只是把锚点写在代码块**之后**并用散文隔开的文件,关卡输出
  `citations=5 UNCHECKED=5` + `OK: every code-block-backed citation matches the baseline`、
  **退出码 0**——一条都没校验,而关卡是绿的。锚点写在块后若与下一个块相邻会被判 MISMATCH
  (那是有声失败,已被兜住);**唯独"块后 + 散文隔开"这一种排版,是无声的**。
  这条提示就是补这个无声的口子。*
  **全块比对 BLOCK-DRIFT(R8C 增,暂不阻断)**:此前脚本**只比对代码块的第一行**,
  块内其余行**从来没有任何机制校验过**。现在首行匹配后会继续逐行比对(遇 `...` 省略号停),
  不符记 `BLOCK-DRIFT` 并打印首处差异。**暂不改退出码**——与引用校验自身当年的路径一致
  (R7C 新增 → R8A 升格阻断),等语料清干净再升格。
  *为什么必须有它(R8C 实测):(a) 全语料首轮扫出 **118 处**,R8C 自己占 3 处并已当轮修掉;
  (b) 最有说服力的一处是 `notes/r8c-raw-auth-py.md` 把一段注释锚到 `hermes_cli/auth.py:5249`,
  **真实位置是 `:5232`,差 17 行**——之所以能过关,是因为 `:5249` 和 `:5232` **首行都是
  那条 `# ----------` 横幅注释**。首行相同的行在大文件里遍地都是,**只比首行的校验器
  对"锚到了隔壁同形状的段落"这种错完全无感**;(c) 另一处是作者给块**凭空补了一个结尾
  `"""`** 让它看起来完整,基线那一行其实是空行。这两类错都长得像逐字引用。*
- **可校验比例必报(R8A 建议 → R8C 定为必报项,下限 70% 不变)**:报告里报
  `可校验比例 = OK / (citations - FIXED)`,**下限 70%**。脚本已直接打印该行,低于下限会加标记。
  *口径(R8C 明确,此前只写了数没写分母是谁):这个下限约束的是**当轮 notes** 那一堆证据层产出,
  不是 `chapters/`。成品章是"求读"的,大量引用天然是散文体的区域指路,
  R8C 实测 11 章合计只有 33.6%——拿 70% 去要求成品章,只会把它逼成底稿。
  跑全量关卡(chapters 全部 + 当轮 notes/reports)时打印的是**合并**比例,
  报告要报的是**当轮 notes 单独**那一个数。*
- **报告格式**:报告 commit 进本仓库 `reports/`;会话最后一条消息给出报告全文。
  **首句结论口径(R8-fix 定,脚本可查)**:第一句 **≤20 字**,数法为——取首行散文
  (非标题、非引用、非表格行),**剥去 `一句话结论:` 之类的标签与 Markdown 强调符**,
  **句内标点计入**(读者要读它),**句末那个句号不计**(它是分隔符不是内容)。
  **纯数据附卷豁免结论句**(如 `round-1-capabilities-full.md`,它是主卷的数据附件)。
  *句末标点计不计不是细节:R7C / R8A / R8B 三份首句在"不计"下正好 20、在"计"下 21。
  选"不计",因为一个连必打的句号都要收费的 20 字上限,实际是 19 字上限,
  而规则没这么说。写在这里是为了让这个选择可见、可被有意推翻,而不是被人意外发现。*

  ```bash
  python3 scripts/verify_report_headline.py reports/*.md
  ```

  *理由(review-1 建议-11 / M-15):规则原本没定计数口径("一句话结论:"这六个字算不算),
  于是它无法被脚本判定、只能靠人看——而这正是 R8A 把引用校验升格为脚本关卡时给出的理由。
  豁免与历史例外都走脚本里的显式名单,不靠猜;历史名单已封闭,不得新增。*
- **每轮报告恢复必报项(R8-fix,review-1 建议-21 / M-25)**:除五层分层快照外,
  **必须报 `R1-inventoried` 的剩余文件数与行数**。
  *理由:分层快照几乎不动(L3/L4/LT 连续五轮一字未改),读者从报告里读不出"还剩多少没开工";
  而"全仓无黑洞"这个最终目的的**唯一可观测指标是台账的 `status` 列,不是分层列**。
  R7 起这条线索中断了五轮,期间实际仍有 8,122 个文件从未开工。*

  ```bash
  # 注意 sub(/\r$/,""):data/ledger.tsv 是 CRLF 行尾,不剥 CR 的话 $6 永远匹配不上,
  # 这条命令会安静地打出 0 —— 正是上面"shell 命令即证据"那条规矩要防的形状。
  awk -F'\t' 'NR>1{sub(/\r$/,"",$6); if($6=="R1-inventoried"){n++; l+=$3}} \
      END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
  ```
- **移交项格式(R8A 起)**:凡向后续轮移交的未决项,**必须附「锚点文件 + 一句话现象」**
  ——写清在哪个文件(最好带行号)、看到的具体现象是什么,而不只是一个标题。
  *理由(R7C 实测):R7 有一条移交项因只留标题被下一轮判错了定位,另一条被判宽了范围;
  R7B 更有一条只在"下一轮建议"里出现过标题、从未取证,却被当成已取证结论传了下去。
  没有锚点的移交项,下一轮要么重做、要么误传。*
- **文档-代码冲突**:README / 仓库根 AGENTS.md / website/docs 是作者自绘地图,
  与代码冲突时以代码为准,每处冲突记录进当轮报告(这本身是学习产出)。
  **判定一条文档断言时,必须把它所在的整句/整段一并判定,并确认它归哪个标题管**
  (R8-fix 定,review-1 阻断-1 + 阻断-4)。
  *两次实测教训:(a) `gateway-internals.md:86` 一句话讲了三件事,R7B 只点了中间那句,
  **最后一句被原样采信写进了 r7 章**——一句过时文档,一半被证伪、一半以"这里已经查过了"
  的名义活了下来;(b) r7b 的 ▲4 把三个方法挂在了**隔壁小节**的标题下,
  文档从没这么说,▲ 因此立不住还污染了跨轮 ▲ 计数。**文档的层级结构本身就是断言的一部分。***
- **记号(R8-fix 增补 ◎)**:▲ = 文档所述与代码**矛盾**;◇ = 代码有、文档无;
  ■ = 代码缺陷;**◎ = 文档成立但显著保守**(如"20+ 平台"而实为 24)。
  *理由(review-1 建议-13 / M-16e):▲ 条数是贯穿各轮、用来衡量"地图腐烂程度"的跨轮指标,
  把"保守但为真"计进 ▲ 会让它不可比。字面为真就不是 ▲。*
- **shell 命令即证据(R8-fix,review-1 建议-16 / M-16d)**:凡把 shell 命令写进证据,
  **必须是重跑能复现该结论的那一条**,并用 ```` ```verify ```` 围栏标注。
  *理由:r4-90 写进定案的自检 grep 用 `iron` 匹配到了 `env`**`iron`**`ment`,
  重跑对每个文件都命中,与它声称的"零命中"相反。结论是对的,命令是错的——
  **一条重跑给出相反结果的命令比不写更糟**:读者要么以为结论错了,要么以为自己环境不对。*
- **负结论的成本(R8-fix,review-1 附录 A-1/A-2)**:"全仓没有 X""没有第三个调用方"
  这类**全称否定**,其可信度等于一次 grep 的完备性,**没有任何机制校验它**。
  写下一条负结论时**必须把搜索面写出来**(搜了什么、用什么模式、排除了什么),
  否则它只是"我没看见"的另一种说法。
  *理由:R8B 的 H-7 写"没有第三个读原始配置后落盘的调用方,H-7 关闭",
  漏掉的那个(`hermes_cli/auth.py:7270`)会在坏 YAML 下把用户的 `approvals.deny` 静默抹掉。
  **正结论错了会被下一个读者撞见;负结论错了会关闭调查。***
- **异步产出的完成判定(R8-fix)**:子代理 / 后台任务的完成,**只以完成信号为准**,
  **不以产物形态推断**。文件已存在、行数够多、看起来写完了——都不是完成。
  *理由:R8B 有一次把"正在写入中"的分段底稿判成了"到货但被截断",据此下了一个错判断,
  下一条 commit 又自我更正。没有信号就等信号,不要看产物猜。*

## 双产出制度(R2 起,对每一轮生效)

每轮产出**两类**文件,定位不同、都要有:

1. **底稿 `notes/rN-*.md`** —— 求全求证。面向"要凭它重实现同等机制"的自己:逐机制、逐文件,
   凡断言紧跟 `路径:行号 @ 863e313` + 代码原文块,配套测试作为行为规格运行/引用。允许啰嗦、允许
   罗列。底稿是证据层,不追求好读。
2. **成品章 `chapters/rN-<主题>.md`** —— 求读。全部成品章最终构成 R12《设计蓝图》正文,
   R12 只做装订与全局重构,不再从底稿从头合成。可读性标准见下(R3 修订,对本轮起所有章生效)。

### 成品章可读性标准(R3 定稿,后续沿用;修订须在当轮报告说明理由)

**目标读者画像**:一个有多年后端工程经验(如 Go / Java 背景)、**没读过本仓库**、**不熟 LLM
provider 生态与 Python 异步生态**的工程师。验收判定 = 该读者不查任何外部资料、不看源码,能顺畅读完
并向他人复述每个机制。写作时始终对着这个人。

**六条硬标准(逐条自检)**:
1. **术语锚定**:任何术语、缩写、项目内专名(prompt cache、prefill、tool_calls、FTS5、CDP、
   `api_mode`、toolset……)首次出现给一句话中文解释;业界通名可保留英文,同样要锚一次。
2. **先场景后机制**:每个机制以**一次具体请求或一次具体故障的走法**开场,把问题演出来,再讲实现。
   不许直接甩结论/甩类名。
3. **双读法**:每章同时支持"几分钟得到全貌与结论"的**快读路径**与**完整精读路径**,两条各自自洽。
   形式自定(如章首 TL;DR + 每节首句加粗要点 + 可选下钻)。
4. **事故讲成故事**:凡引用真实 issue 的教训,正文讲成读者能复述的**因果经过**(什么输入→什么现象
   →为什么→怎么修),issue 编号只作溯源尾注,不作解释本身。
5. **可读性不牺牲可验证性**:关键断言仍以 `路径:行号 @ 863e313` 溯源;**图必须 GitHub 页面直接渲染**
   (```mermaid 围栏,不用外链图片;节点标签内不用裸 `<` `>`,`<br/>` 除外)。
6. **独立可读**:不翻底稿、不看源码即可读懂本簇解决什么问题、怎么设计、有什么取舍;篇幅服务于讲清楚。
7. **锚点排版(R8-fix)**:`路径:行号 @ 863e313` **一律单独成行,置于代码块/引用块之前**,
   不放在块后、不塞进块里。这既是给读者的("先知道这段从哪来,再读它"),
   也是校验器的契约——它按"引用 → 紧跟的块"配对。
8. **引用必须能从仓库根解析(R8-fix,review-1 建议-1 / M-5)**:成品章里不写裸文件名,
   除非该文件真的就在基线仓库根(如 `hermes_state.py`)。
   *理由:R8-fix 前 11 章 326 处引用里有 99 处(30.4%)无法从仓库根解析,其中 39 处在基线里
   真有同名歧义——`__init__.py` **171 个**候选、`base.py` 9 个、`setup.py` 4 个。
   对那个"不看源码"的目标读者,`base.py:781-875` 不是引用,是谜题。
   r3 / r7c / r8a 三章当时 0 处违反,证明这不是工作量问题。*

**推荐骨架(可调,以达成上述标准为准)**:
```
# rN · <主题> —— <一句话副标题>
> 读者定位 + 溯源约定(路径:行号 @ 863e313)
## TL;DR(快读路径:5 句话讲清这一簇是什么、解决什么、最重要的三五个设计)
## 1. 从一个场景说起          # 一次具体请求/故障的走法,把问题演出来
## 2. 全景                    # Mermaid 图 + 几句话讲清机制如何协作
## 3. 逐机制                  # 每节:场景开场→设计→取舍;关键断言溯源;事故讲成故事
## 4. 可迁移的设计原则        # 造自己的 harness 怎么做,与具体代码解耦
## 5. 地图与代码的出入        # 本簇 ▲/◇ 定案融进叙述
## 6. 延伸                    # 指向底稿 notes/rN-*
```

## 边界

- hermes-agent 仓库**只读**:不修改任何文件,绝不向其远端推送。
  **R8A 起由脚本强制**:`scripts/verify_ledger.py` 第一项检查除了核对 HEAD,
  还要求 `git status --porcelain` **为空**——基线不干净时直接 FAIL 并给出恢复命令。
  *理由(R8A 实测)*:本轮有子代理在基线里跑了 npm 相关操作,重写了 `package-lock.json`
  (npm 重解析依赖,给约 30 个条目盖了 `"peer": true`)。它**恰好**被行数复核撞见;
  若被改的文件行数不变,就会静默通过,而此后所有 `路径:行号 @ 863e313` 引用**全部失去意义**。
  基线是整个项目的引用基准,"它还干净吗"必须**直接断言**,不能靠间接推断。
  恢复:`git -C /home/user/hermes-agent checkout -- . && git -C /home/user/hermes-agent clean -fd`。
- 本仓库分支策略:每轮工作在 **`claude/hermes-r<轮次>-<主题>`** 分支推进并 push
  (R8-fix 统一命名;历史分支不重命名)。轮次完成后经 PR 合入 main。
  任何新会话仅凭远端即可恢复全部产出与进度。
- **语言:会话回复与全部产出一律中文**(R8-fix)。必要的技术术语可保留英文,
  但**首次出现给一句话中文锚定**(与成品章硬标准 1 同源)。
  代码、路径、命令、引用的原文块照抄不译。
- **历史产出的改法(R8-fix)**:
  - `chapters/` 与 `notes/` —— **直接改正文**(它们是要被反复读的现役产出),
    改判处就地写明"原判是什么、为什么撤、依据是什么"。
  - `reports/` —— **正文不静默改写**,修正一律以**文末勘误节**呈现
    (报告是某一轮的历史记录)。唯一例外是引用行号:漂移必须就地改正,
    否则校验器过不了——但**每一处都要在勘误节里点名**。
  - `reviews/` —— 评审报告原文**不改**(历史记录);仲裁与处置结果另立文件或附录。
- 不配置任何付费凭据;真实跑通所需的配置项列在报告里等待提供,不自行猜测或伪造。
- 网络/权限拦截不得绕过:记录被拦域名与所需放行项,写进报告等待提供。
- 常规动作(clone、装依赖、写脚本、本仓库 git 操作、试运行)直接推进,不中途请示。

## 仓库布局

```
CLAUDE.md                  # 本文件:目标、验收、边界、恢复方式
reports/round-1-survey.md  # 第一轮主卷:测绘 + 能力点(目录+精选详述)+ 学习方案 + 建议
reports/round-1-capabilities-full.md  # 第一轮附卷:170 条能力点全字段 + 代码摘录
data/inventory.tsv         # 全仓文件盘点(path/kind/lines/bytes),inventory.py 生成
data/ledger.tsv            # 覆盖台账(path/kind/lines/layer/round/status)
data/capability-mining.json# 14 路子系统挖掘的结构化原始产出(能力点的数据源)
data/r8a-config-keys.tsv   # R8A 资产:856 个配置键(默认值/定义处/py 与 ts 读取点/文档覆盖)
data/r8a-env-vars.tsv      # R8A 资产:151 条静态环境变量(运行时会涨到 308,见脚本说明)
data/r8a-extra-root-keys.tsv # R8A 资产:23 个不在 DEFAULT_CONFIG 里但合法的根键
data/r8a-config-keys-summary.md # R8A 资产:上面三张表里“该先读哪几片”(脚本生成,勿手改)
scripts/inventory.py       # 盘点脚本(行数规则的唯一权威定义)
scripts/assign_layers.py   # 分层规则(首条匹配生效;不匹配即报错;重生成保留 status 列)
scripts/verify_ledger.py   # 台账校验(基线 HEAD + **基线工作区干净** + 文件集一致 +
                           # 行数复核 + 分层加总 = 全仓总行数)
scripts/verify_citations.py# 引用校验(R7C 新增,R8A 起为定稿关卡,R8-fix 扩面到引用块):
                           # `路径:行号` 后的代码块 / `>` 引用块与基线比对;
                           # ```text|console|verify|shell-session 为声明式非源码豁免;
                           # MISMATCH 会列出该行全部候选引用;--fix 修无歧义漂移,用后必须裸跑复核;
                           # R8C 增:打印可校验比例(70% 下限)+ 单文件 UNCHECKED ≥90% 的
                           # 「疑似锚点排版不合规」提示(非阻断)
scripts/verify_report_headline.py # R8-fix 新增:报告首句 ≤20 字口径的脚本化判定
                           # (剥标签与强调、中文标点计入;纯数据附卷豁免、历史例外显式列名)
scripts/config_table.py    # R8A 新增:从 DEFAULT_CONFIG / OPTIONAL_ENV_VARS 字面量 AST
                           # 抽取配置项全表(不 import 不执行);用前先读它开头的三条告诫
scripts/render_capabilities.py   # JSON → 附卷渲染
scripts/render_main_report.py    # JSON → 主卷能力点章节渲染(--compact 出会话消息版)
notes/                     # 底稿:每轮机制笔记(rN-*,求全求证,带行号证据)
chapters/                  # 成品章:每轮 rN-<主题>.md(求读,构成 R12 设计蓝图正文)
reports/round-N-*.md       # 每轮报告(结论 + 台账报数 + 定案 + 下轮建议 + 文末勘误节)
reviews/                   # 独立评审位的评审报告(历史记录,原文不改)
```

## 测试环境(可选,恢复后按需重建)

```bash
# 1) 建 venv + 装 dev extra
python3 -m venv /home/user/hermes-venv
/home/user/hermes-venv/bin/pip install -e "/home/user/hermes-agent[dev]"

# 2) 必补:aiohttp 不在 [dev] extra 里(R7B 定位,见下)
/home/user/hermes-venv/bin/pip install "aiohttp==3.14.1" "brotlicffi==1.2.0.1"

# 3) 跑测试
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/agent/<file>

# 4) 报测试数时,同时记下环境(R8A 新增,理由见下)
ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l
```

**报测试通过数时必须一并记环境(R8A 实测催生)**:用例数是**环境的函数**,不是代码的函数。
R8A 同一套 170 个测试文件先后报出 **3,183** 与 **3,190** 两个数,**两次都 0 失败**,
差别完全来自"有子代理往共享 venv 里装了平台 extra,于是 7 个被可选依赖门控 skip 的用例真跑了"。
**不记环境,下一轮拿到不同的数就无从判断是代码变了还是环境变了。**
查证方法与"基线是否干净"同理——**直接断言,不要间接推断**:
去看 `site-packages/*.dist-info` 的时间戳,而不是猜。
(注:venv 是可选、可重建的便利设施,**不是引用基准**;它漂移不影响
`路径:行号 @ 863e313` 的有效性,但会改变报告里的数,所以必须交代。)

**为什么第 2 步是必需的(R7B 定位,R7C 并入本文件)**:`aiohttp` **不在 `[dev]` extra**,
而在 `messaging` / `slack` / `matrix` / `teams` / `homeassistant` / `sms` 等**平台 extra** 里
(`pyproject.toml:176 @ 863e313`),但 `gateway/platforms/api_server.py`、`webhook.py`、
`whatsapp_cloud.py` 都**直接 import 它**。只装 `[dev]` 会让 `tests/gateway/test_api_server*.py`
等约 20 个文件在**收集阶段**就失败(表现为 ImportError,不是断言失败,容易误判成"测试挂了")。
补装后这些文件全部转为通过。

**已知环境限制(非代码缺陷,勿误判)**:本类云端容器**无 IPv6 协议族**
(`bind('::')` → `EAFNOSUPPORT`,`/proc/net/if_inet6` 不存在),故
`tests/gateway/test_webhook_adapter.py::TestDualStackBind::test_default_bind_serves_both_families`
必然失败。被测代码 `DEFAULT_HOST = None`(`gateway/platforms/webhook.py:129 @ 863e313`)的语义是
"按解析出的每个地址族各建一个套接字",只解析出 IPv4 时只建 IPv4 **是正确行为**。

**R8B 补充:容器还有另外两条环境性质,合计已知会让 5 个用例必然失败(全部非代码缺陷)。**
每条都已逐个查到机制,勿再重复排查:

| 用例 | 根因 | 机制(已核) |
|---|---|---|
| `tests/hermes_cli/test_browser_connect_dual_stack.py::TestFindFreeDebugPort::test_skips_occupied_successor` | **无 IPv6** | `find_free_debug_port` 要求端口在 `127.0.0.1` **与** `::1` **两族都可绑**;无 IPv6 时每个候选都失败,函数走它自己文档化的兜底 `return preferred + 1`,于是"跳过被占端口"这个断言必然不成立 |
| `tests/hermes_cli/test_migrate_xai.py::TestUnreadableExistingConfig::test_apply_refuses_to_overwrite_unreadable_config` | **以 root 运行**(`id -u` = 0) | root 无视 `chmod 000`,读得到,于是不抛 `PermissionError` |
| `tests/hermes_cli/test_gateway_service.py`(systemd 单元生成) | **以 root 运行** | 被测代码自己拒绝:`Refusing to install the gateway system service as root; pass --run-as-user root to override` |
| `tests/hermes_cli/test_approvals_suggest.py::test_normalize_folds_home_prefix` | **以 root 运行**(`HOME=/root`) | `_home_prefix_fold_regex`(`tools/approval.py:1072 @ 863e313`)对"根下不足两段"的路径**故意返回 `None`**,防止畸形 HOME 改写无关前缀;`/root` 只有一段,于是不折叠 |
| `tests/hermes_cli/test_xai_provider_labels.py` | **无 models.dev 目录**(离线) | `get_label` 命中不了覆盖表就回落 models.dev 目录取 `pdef.name`;本容器目录条目数实测 **0**、无本地缓存文件,于是返回原始 id `'xai'` 而非 `'xAI'` |

**报测试通过数时一并记 venv 包数**(R8A 立):`pip list` 去掉两行表头后的条目数。
R8B 实测 **87 个包**(`[dev]` extra + `aiohttp 3.14.1` + `brotlicffi 1.2.0.1`)。

模型凭据不需要,也不得自行配置。

## 学习方案索引

完整方案(分层定义、轮次划分、每轮产出形态与理由)见
`reports/round-1-survey.md` 的"学习方案"一节;台账中每个文件的 `round` 列
标注其计划轮次。后续会话按该方案推进,如需修订,在当轮报告里写明修订与理由,
并同步更新台账。
