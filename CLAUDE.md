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
scripts/assign_layers.py   # 分层规则(首条匹配生效;不匹配即报错,保证全覆盖)
scripts/verify_ledger.py   # 台账校验(文件集一致 + 行数复核 + 分层加总 = 全仓总行数)
scripts/render_capabilities.py   # JSON → 附卷渲染
scripts/render_main_report.py    # JSON → 主卷能力点章节渲染(--compact 出会话消息版)
notes/                     # 后续轮次的机制笔记(按机制组织)
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
