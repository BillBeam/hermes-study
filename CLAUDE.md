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
- **证据格式**:凡对 hermes-agent 行为的断言,紧跟 `路径:行号 @ 863e313` 与代码原文块,
  使读报告本身即完成验证。
- **报告格式**:第一句 ≤20 字结论;报告 commit 进本仓库 `reports/`;
  会话最后一条消息给出报告全文。
- **文档-代码冲突**:README / 仓库根 AGENTS.md / website/docs 是作者自绘地图,
  与代码冲突时以代码为准,每处冲突记录进当轮报告(这本身是学习产出)。

## 双产出制度(R2 起,对每一轮生效)

每轮产出**两类**文件,定位不同、都要有:

1. **底稿 `notes/rN-*.md`** —— 求全求证。面向"要凭它重实现同等机制"的自己:逐机制、逐文件,
   凡断言紧跟 `路径:行号 @ 863e313` + 代码原文块,配套测试作为行为规格运行/引用。允许啰嗦、允许
   罗列。底稿是证据层,不追求好读。
2. **成品章 `chapters/rN-<主题>.md`** —— 求读。面向**没读过这份代码的合格工程师**:不翻底稿、
   不看源码即可独立读懂本轮机制簇解决什么问题、怎么设计、有什么取舍。全部成品章最终构成
   R12《设计蓝图》正文,R12 只做装订与全局重构,不再从底稿从头合成。

**成品章结构模板(R2 定,后续沿用;发现更优结构在当轮报告说明理由后可修订):**

```
# rN · <主题> —— <一句话副标题>
> 读者定位:一句话说明读完能独立讲清/实现什么;末尾附"溯源约定"(路径:行号 @ 863e313)。
## 1. 这一簇解决什么问题        # 从 harness 需求出发,不预设读者懂代码
## 2. 全景                      # 一张 Mermaid 图 + 三五句话讲清机制如何协作
## 3. 逐机制                    # 每个机制一节:问题→设计→取舍;关键断言溯源;能画则配 Mermaid
## 4. 可迁移的设计原则          # 提炼成"造自己的 harness 时怎么做",与具体代码解耦
## 5. 地图与territory的出入     # 把本簇 ▲/◇ 定案融进正文叙述,不另起流水账
## 6. 延伸                      # 指向对应底稿 notes/rN-*,供要证据的人下钻
```

要求:成品章独立可读,篇幅服务于讲清楚、不设上下限;可读性不牺牲可验证性,关键断言仍以
`路径:行号 @ 863e313` 溯源;**图必须在 GitHub 页面直接渲染(用 ```mermaid 围栏,不用外链图片)**。

## 边界

- hermes-agent 仓库**只读**:不修改任何文件,绝不向其远端推送。
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
scripts/inventory.py       # 盘点脚本(行数规则的唯一权威定义)
scripts/assign_layers.py   # 分层规则(首条匹配生效;不匹配即报错;重生成保留 status 列)
scripts/verify_ledger.py   # 台账校验(文件集一致 + 行数复核 + 分层加总 = 全仓总行数)
scripts/render_capabilities.py   # JSON → 附卷渲染
scripts/render_main_report.py    # JSON → 主卷能力点章节渲染(--compact 出会话消息版)
notes/                     # 底稿:每轮机制笔记(rN-*,求全求证,带行号证据)
chapters/                  # 成品章:每轮 rN-<主题>.md(求读,构成 R12 设计蓝图正文)
reports/round-N-*.md       # 每轮报告(结论 + 台账报数 + 定案 + 下轮建议)
```

## 测试环境(可选,恢复后按需重建)

```bash
python3 -m venv /home/user/hermes-venv && /home/user/hermes-venv/bin/pip install -e "/home/user/hermes-agent[dev]"
cd /home/user/hermes-agent && HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/agent/<file> 
# 已验证可用(第一轮);模型凭据不需要,也不得自行配置。
```

## 学习方案索引

完整方案(分层定义、轮次划分、每轮产出形态与理由)见
`reports/round-1-survey.md` 的"学习方案"一节;台账中每个文件的 `round` 列
标注其计划轮次。后续会话按该方案推进,如需修订,在当轮报告里写明修订与理由,
并同步更新台账。
