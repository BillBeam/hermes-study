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
  **每轮 commit 前必须对本轮全部 `notes/` 与 `chapters/` 全量运行**

  ```bash
  python3 scripts/verify_citations.py /home/user/hermes-agent notes/rN-*.md chapters/rN-*.md
  ```

  **跑到退出码 0、输出 `OK: every code-block-backed citation matches the baseline` 才算过关**,
  并在报告里报数(citations / OK / UNCHECKED)。带代码块的引用逐字比对基线,不匹配即失败;
  只写散文不带代码块的引用记 UNCHECKED,不算失败。`--fix` 只用于**无歧义**的行号漂移,
  用后**必须**不带 `--fix` 再跑一遍确认。
  *升格理由(R7C 实测):该脚本在 R7C 的 2,531 条引用里抓出约 60 处行号漂移、3 处非原文引用、
  5 处缺路径引用,其中 3 处出自主线本人——人工约定这一层已被证明兜不住。*
- **报告格式**:第一句 ≤20 字结论;报告 commit 进本仓库 `reports/`;
  会话最后一条消息给出报告全文。
- **移交项格式(R8A 起)**:凡向后续轮移交的未决项,**必须附「锚点文件 + 一句话现象」**
  ——写清在哪个文件(最好带行号)、看到的具体现象是什么,而不只是一个标题。
  *理由(R7C 实测):R7 有一条移交项因只留标题被下一轮判错了定位,另一条被判宽了范围;
  R7B 更有一条只在"下一轮建议"里出现过标题、从未取证,却被当成已取证结论传了下去。
  没有锚点的移交项,下一轮要么重做、要么误传。*
- **文档-代码冲突**:README / 仓库根 AGENTS.md / website/docs 是作者自绘地图,
  与代码冲突时以代码为准,每处冲突记录进当轮报告(这本身是学习产出)。

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
- 本仓库分支策略:每轮工作在 `claude/hermes-agent-round-<N>-*` 分支推进并 push;
  轮次完成后可合入 main。任何新会话仅凭远端即可恢复全部产出与进度。
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
scripts/verify_citations.py# 引用校验(R7C 新增,R8A 起为定稿关卡):`路径:行号` 后的代码块
                           # 与基线逐字比对;--fix 修无歧义漂移,用后必须裸跑复核
scripts/config_table.py    # R8A 新增:从 DEFAULT_CONFIG / OPTIONAL_ENV_VARS 字面量 AST
                           # 抽取配置项全表(不 import 不执行);用前先读它开头的三条告诫
scripts/render_capabilities.py   # JSON → 附卷渲染
scripts/render_main_report.py    # JSON → 主卷能力点章节渲染(--compact 出会话消息版)
notes/                     # 底稿:每轮机制笔记(rN-*,求全求证,带行号证据)
chapters/                  # 成品章:每轮 rN-<主题>.md(求读,构成 R12 设计蓝图正文)
reports/round-N-*.md       # 每轮报告(结论 + 台账报数 + 定案 + 下轮建议)
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
```

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

模型凭据不需要,也不得自行配置。

## 学习方案索引

完整方案(分层定义、轮次划分、每轮产出形态与理由)见
`reports/round-1-survey.md` 的"学习方案"一节;台账中每个文件的 `round` 列
标注其计划轮次。后续会话按该方案推进,如需修订,在当轮报告里写明修订与理由,
并同步更新台账。
