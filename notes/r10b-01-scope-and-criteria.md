# r10b · 范围核对、切片、L3 判据与关卡加固 —— 底稿

> 溯源约定:凡对 hermes-agent 行为的断言,锚点写作 `路径:行号 @ 863e313`,
> **单独成行、置于代码块之前**。本文件是证据层,求全求证。

## 1. 开工先核范围

任务书给的范围是 R10 的 REMAINDER,清单在 `data/r10/slices/REMAINDER.txt`,
标称 977 文件 / 214,245 行。核:

```verify
git show 884cb7f:data/ledger.tsv > /tmp/ledger-at-start.tsv && python3 - <<'EOF'
import csv, collections
rows = {}
with open('/tmp/ledger-at-start.tsv', newline='', encoding='utf-8') as f:
    for r in csv.DictReader(f, delimiter='\t'):
        rows[r['path'].strip()] = r
rem = [l.strip() for l in open('data/r10/slices/REMAINDER.txt', encoding='utf-8') if l.strip()]
by = collections.Counter(); ln = collections.Counter(); st = collections.Counter()
for p in rem:
    by[rows[p]['layer'].strip()] += 1
    ln[rows[p]['layer'].strip()] += int(rows[p]['lines'])
    st[rows[p]['status'].strip()] += 1
print(f"files={len(rem)} lines={sum(int(rows[p]['lines']) for p in rem)}")
print("layer:", {k: (v, ln[k]) for k, v in by.items()})
print("status:", dict(st))
EOF
```

```text
files=977 lines=214245
layer: {'L2': (964, 196867), 'L3': (13, 17378)}
status: {'R1-inventoried': 977}
```

*命令读的是 **`884cb7f` 那一版台账**(本轮改 `status` 之前的最后一版),不是当前工作区的。
开工读数必须在收工后仍可复现,而 `status` 列在本轮末尾会被改写——直接读当前台账的话,
**这段证据会被本轮自己的后续步骤作废**。*

**与任务书一致。** 三件事值得单独记:

1. **977 个文件的 `status` 开工时全部是 `R1-inventoried`** —— R10 说的「显式不吃下、
   未虚报」经核属实,没有任何一个被提前翻状态。
2. **13 个 L3 文件全部在 `apps/desktop/src/i18n/`** 下,不是散落的。这让「单独切一片取
   L3 单位成本」成为可能——如果它们散在十片里,L3 的成本就永远测不出来。
3. 目录构成高度集中:`apps/desktop` 930 个 / `apps/bootstrap-installer` 35 个 /
   `apps/shared` 12 个。**整个 R10B 就是「桌面端」这一个应用**。

台账守恒(开工):

```verify
cd /home/user/hermes-study && python3 scripts/verify_ledger.py /home/user/hermes-agent data/ledger.tsv
```

```text
OK baseline=863e31318 files=8530 total_lines=2608452
  L1: files=563 lines=522207
  L2: files=2131 lines=671639
  L3: files=1895 lines=602085
  L4: files=560 lines=55902
  LT: files=3381 lines=756619
  SUM == repo total: 2608452
```

`R1-inventoried` 剩余(开工):**7,180 文件 / 1,770,699 行**。

## 2. 切几片、依据是什么

**结论:切 11 片。** 依据是 R10 实测出来的容量单位——**「行/片」而不是「文件/片」**:
R8D 每片 20,838 行、R10 每片 22,145 行,相差 6.3%;而每片文件数差 2.2 倍
(31.3 → 69.3)。214,245 / 21,500 ≈ 10 片,再把 13 个 L3 单独摘出来成第 11 片。

```verify
cd /home/user/hermes-study && python3 data/r10b/probes/make_slices.py
```

```text
slice  files    lines  L3f  L3lines  title
    A     84    18804    0        0  聊天输入区:composer、右栏与会话瓦片
    B     55    18761    0        0  会话列表、切换与会话视图
    C     77    19070    0        0  设置面、计费与 profile/网关设置
    D     97    19637    0        0  状态层:store、hooks、sdk 与内核接驳
    E    126    20540    0        0  运行时库、主题、调试与类型面
    F    124    21029    0        0  消息渲染:assistant-ui、聊天组件与右侧栏
    G    100    17544    0        0  窗格外壳、通用 UI 原语与应用 shell
    H     66    20165    0        0  能力面板:插件、技能、贡献、星图与命令面板
    I     13    17378   13    17378  apps/desktop 的 i18n 语言包(全部 13 个 L3 文件,单独成片以取 L3 单位成本)
    J     86    18766    0        0  桌面外壳其余:覆盖层、小组件、宠物、cron/消息/webhook 面板与样式
    K    149    22551    0        0  构建、打包、安装器与端到端测试
TOTAL    977   214245   13    17378

lines/slice: min=17378 max=22551 mean=19476  (R10 measured 22,145; R8D 20,838)
OK: slices partition R10 REMAINDER exactly (no overlap, no loss)
```

切片脚本自带三条断言(文件数相等、无重复、并集等于范围),不满足直接退出。
**规则是有序的、首条匹配生效,任何没被规则认领的文件是硬错误**——
「加一条规则」比「把兜底桶悄悄放宽」可审计。

**两处刻意的安排:**

- **片 I 单独装 13 个 L3 文件。** L3 到本轮为止零先例(1,895 文件 / 602,085 行,
  `status` 清一色 `R1-inventoried`),R11B 有 787 文件 / 263,763 行等着排期。
  把它们混进别的片,L3 的单位成本就测不出来——而那正是本轮被要求产出的东西。
- **规则里 B 排在 A 前面。** A 的最后一条前缀是整个 `app/chat/`,而
  `app/chat/sidebar/`(28 文件 / 7,877 行)讲的是会话列表,属于 B。
  不调顺序的话 A 是 26,681 行、B 是 10,884 行;调完是 18,804 / 18,761。

## 3. 开工杂项:H-R10-a 结清(关卡的扩展名盲区)

### 3.1 病灶

`scripts/verify_citations.py` 靠一条正则认出「这是个锚点」。改动前它的扩展名白名单是
`py|md|yaml|yml|toml|c|sh|json|ts|tsx|js`。**不在名单上的锚点不会记 UNCHECKED——
它根本不被当成锚点**,既不校验、也不进分母。UNCHECKED 至少出现在
`citations=` 里、会被「可校验比例」和「单文件 UNCHECKED ≥90% 提示」两道机制看见;
白名单外的锚点**连被看见的资格都没有**。

### 3.2 实测:漏了多少,以及漏的是什么

```verify
cd /home/user/hermes-study && python3 data/r10b/probes/cite_ext_scan.py /home/user/hermes-agent | sed -n '/^A\./,/^  newly captured/p'
```

```text
A. Anchors NEWLY captured by the widened whitelist (h/mjs/nix/rs)
========================================================================
  .h    x6   resolves     native/fts5_cjk/vendor/sqlite3.h
          in: r10-raw-native-vendor.md
  .h    x3   resolves     native/fts5_cjk/vendor/sqlite3ext.h
          in: r10-raw-native-vendor.md
  .h    x2   UNRESOLVABLE sqlite3.h
          in: r10-raw-native-vendor.md
  .h    x1   UNRESOLVABLE usr/include/sqlite3.h
          in: r10-raw-native-vendor.md
  .h    x1   UNRESOLVABLE vendor/sqlite3.h
          in: r10-raw-native-vendor.md
  .mdx  x4   resolves     website/docs/index.mdx
          in: round-1-capabilities-full.md, round-1-survey.md
  .mdx  x2   resolves     website/docs/reference/automation-blueprints-catalog.mdx
          in: r7c-raw-cron-catalogs.md
  .mjs  x2   resolves     ui-tui/scripts/build.mjs
          in: r10-raw-hermes-ink.md, r10-raw-ui-tui-components.md
  .nix  x1   resolves     nix/lib.nix
          in: r9a-raw-research-pipeline.md
  .nix  x1   resolves     nix/tui.nix
          in: r10-raw-ui-tui-components.md
  .txt  x1   resolves     hermes_agent.egg-info/SOURCES.txt
          in: r7c-raw-cron-catalogs.md

  newly captured anchor occurrences: 24   distinct paths: 11
```

**移交项点名了 4 种扩展名,实测还有 2 种它没点到:`mdx`(6 处)与 `txt`(1 处)。**
`.rs` 当前语料 0 处,但本轮范围里有 `apps/bootstrap-installer/src-tauri/src/*.rs`
8 个文件 4,395 行,片 K 会用到它。

**`.mdx` 那 6 处是本节最重的发现。** CLAUDE.md 把 `README / 仓库根 AGENTS.md /
website/docs` 列为「作者自绘地图」,与代码冲突时以代码为准,每处冲突记 ▲。
也就是说 **`website/docs` 是每一条 ▲ 的文档侧**。R8-fix 当年把 `>` 引用块纳入校验,
理由原话是「代码侧有脚本兜着所以稳,文档侧只有人工约定所以漂」——
而 `.mdx` 这个口子把那次扩面在 `website/docs` 上**整个抵消掉了**:
引用块规则管得着 `>` 块,管不着一条根本没被识别成锚点的引用。

### 3.3 为什么不干脆放宽成「任意扩展名」

移交项警告过:`sqlite.org:443` 和 `路径:行号` 是同一个形状。实测这不是假想:

```verify
cd /home/user/hermes-study && python3 data/r10b/probes/cite_ext_scan.py /home/user/hermes-agent | sed -n '/^C\./,/still-excluded/p'
```

```text
C. Every distinct still-excluded token, with resolvability
========================================================================
  not-a-path   x1   1.2
  not-a-path   x1   10.0.0.5
  not-a-path   x31  127.0.0.1
  not-a-path   x2   192.168.10.42
  not-a-path   x1   192.168.x.x
  not-a-path   x2   api.openai.com
  not-a-path   x1   example.com
  not-a-path   x2   homeassistant.local
  not-a-path   x1   n.lineno
  not-a-path   x4   sqlite.org
  not-a-path   x1   tool-gateway.nousresearch.com
  not-a-path   x2   x.test
  ---- still-excluded occurrences: 49  (resolvable=0, host:port-or-not-a-path=49)
```

全语料 **49 处** host:port 形状的 token,**没有一处**的后缀落在白名单里,
而且——这是比「没吃错」更强的一句——**`resolvable=0`,即白名单外没有留下任何一个真锚点**。
所以白名单是一条**有效且完备**的分界,不是偷懒。连 `n.lineno:4`(一次属性访问)
都长成这个形状,可见「任意扩展名」不只会吃主机名,还会吃普通代码片段。

**这个测量对「报告它」不幂等,两个读数必须分开报。** 探针扫的是
`chapters/ notes/ reports/ reviews/`,而**本轮的写作本身**要把
`sqlite.org:443`、`127.0.0.1:18789` 这些例子写进 notes 与报告里——
于是普查会数到写作自己的散文。故探针按**前缀**(`r10b-`、`round-10b-`)剔除本轮写作:

| 读数 | 新纳入锚点 | 仍在白名单外 |
|---|---|---|
| **剔除本轮写作**(报告采用) | **24** | **49**(resolvable=0) |
| 不剔除(`--no-exclude`) | 31 | 56(resolvable=0) |

**两个数不同,不能说成「读数相同」。** 差额 7 处正是本轮写作自己引入的示例字符串。
*用前缀而不是文件名清单来剔除,是因为清单要靠人记得维护——初版就是个清单,
而它已经漏掉了 `notes/r10b-90-handover-rulings.md`(它引用移交项原文时带了一次
`sqlite.org:443`),把 host:port 普查虚高了 1。这与 R10 版移交普查那张手工报告清单
是同一个失效形态,同一轮里犯了两次。*

**但 `sh` / `js` / `rs` 同时是国家域名后缀**(圣赫勒拿 / 泽西 / 塞尔维亚),
所以对这三种额外要求一点「像路径」的证据:有 `/`、有 `_`、或能解析。
实测波及**恰好 1 处**真锚点:`notes/r10-raw-native-vendor.md` 里的裸 `native/fts5_cjk/build.sh:4-6`。
**处置是把它补成 `native/fts5_cjk/build.sh:4-6`,而不是让守卫把它藏起来**——
藏起来就等于在治好这个病的同时,又在别处种下同一个病。

### 3.4 顺带修的第三处:前导点

原正则的路径必须以 `[A-Za-z0-9_]` 开头,于是 `.github/workflows/ci.yml:12` 被解析成
`github/workflows/ci.yml:12`,**永远解析不到**。全语料实测 2 处,加上可选前导点后
两处都从不可解析变为可解析,**没有任何一处的解析结果变坏**。

### 3.5 前后对比:失败集合逐行相同

同一个 `STUDY_ROOT` 下跑改动前后两版(这一点很要紧:`STUDY_ROOT` 是脚本按
自身位置算出来的,把旧版拷到别处跑会让它认不出本仓库自己的文件,
**第一次对比就是这么被污染的**,读出 5 条假的新增 MISMATCH):

| 范围:`chapters/*` + `notes/*` + `reports/*` + `reviews/*` | 改动前 | 改动后 |
|---|---|---|
| citations | 16,907 | **16,923**(+16) |
| OK | 10,534 | **10,545**(+11) |
| UNCHECKED | 6,056 | **6,061**(+5) |
| MISMATCH | 128 | 128 |
| MISSING-FILE | 189 | 189 |
| BLOCK-DRIFT | 1 | 1 |
| table_anchors | 3,056 | **3,058**(+2) |
| **FAIL 总数** | **318** | **318** |
| 失败明细逐行 diff | — | **完全相同,零新增、零消失** |

*(上表的 318 条失败是 H-R8FIX-b / H-R8D-g 记在案、去向 R11B 的历史积压,不是本轮造成的。)*

**新纳入校验的锚点:24 处**(gate 口径,已排除围栏块与引用块内部),
分布 `.h` 13 / `.mdx` 6 / `.mjs` 2 / `.nix` 2 / `.txt` 1。

**24 与 +16 / +2 的关系必须说清楚,它们是三个不同的数**:`citations=` 计的是
**带引用的行数**(一行上有几个锚点只记一条结果),`table_anchors=` 计的是
**带锚点的表格单元格数**。24 处锚点落在 16 个此前不带任何锚点的行 + 2 个表格单元格上。

```verify
cd /home/user/hermes-study && python3 data/r10b/probes/cite_ext_scan.py /home/user/hermes-agent | sed -n '/^D\./,$p' | tail -10
```

```text
  block-level (counts into `citations=`):
      .h    11
      .mdx  6
      .mjs  2
      .nix  2
      .txt  1
      TOTAL 22
  table-row (counts into `table_anchors=`):
      .h    2
      TOTAL 2
```

*一处口径差,不是错误*:R10 报告 §11.8 报「白名单外的真锚点 16 处(`.h` 13 / `.mjs` 2 /
`.nix` 1)」,本轮全语料重扫得 **17 处**(`.h` 13 / `.mjs` 2 / `.nix` 2)。
差的 1 处是 `notes/r9a-raw-research-pipeline.md` 的 `nix/lib.nix`——R10 扫的是
chapters + 当轮 notes,本轮扫的是 chapters + notes + reports + reviews 全部。
**两个数都对,分母不同。** 而这两个数(17)与上面的 24,又差 7 处 `.mdx`/`.txt`,
因为 R10 只找了它点名的那 4 种扩展名。**三个读数,三个口径,不合并。**

### 3.6 负控:证明关卡真拦得住

一个开始识别新锚点、然后一律放行的关卡毫无价值。探针自造漂移锚点,
覆盖三种失败形态,并反向断言主机名不被吞:

```verify
cd /home/user/hermes-study && python3 data/r10b/probes/cite_ext_negative_control.py /home/user/hermes-agent | tail -16
```

```text
  OK   gate exits 1 on the drifted fixture
  OK   MISMATCH reported for native/fts5_cjk/vendor/sqlite3.h:107
  OK   MISMATCH reported for ui-tui/scripts/build.mjs:23
  OK   MISMATCH reported for nix/tui.nix:16
  OK   MISMATCH reported for apps/bootstrap-installer/src-tauri/build.rs:35
  OK   MISMATCH reported for website/docs/index.mdx:57
  OK   TABLE-DRIFT reported for drifted table anchors
  OK   OUT-OF-RANGE reported for past-EOF anchors
  OK   sqlite.org:443 was NOT read as an anchor
  OK   127.0.0.1:18789 was NOT read as an anchor
  OK   api.openai.com:443 was NOT read as an anchor
  OK   homeassistant.local:8123 was NOT read as an anchor
  OK   example.rs:443 was NOT read as an anchor
  OK   citations=7 equals the 5 drifted fences + 2 past-EOF (no host:port leaked in)

NEGATIVE CONTROL PASSED: the widened gate blocks what it claims to block
```

**最后一条断言是这个负控里最有价值的一条**:它不只检查主机名没出现在告警里,
还检查 `citations=` 的**总数**正好等于故意造的 7 条——如果哪个主机名被当成锚点,
它可能安静地记成 UNCHECKED 而不产生任何告警文本,**只有对总数下断言才抓得住**。

**负控自己也修过一次。** 初版把取样行号写死,在 `nix/tui.nix:10` 上抽到一个**空行**;
空块被记 UNCHECKED,那一条于是**什么都没证明,但看起来证明了**。改为要求取样行
非空、长度 ≥25 字符、且在文件中唯一。*这正是负控存在的理由的一个微缩版:
没有对「关卡确实报了失败」下断言之前,「跑完了」不等于「验过了」。*

## 4. L3 交付判据(本轮定义)

完整定义与理由见 `data/r10b/l3-criteria.md`,此处只放判据表本身:

| # | 判据 | 可复核方式 |
|---|---|---|
| **L3-1 用途到位** | 每个文件至少一次**全路径** + 一句话「它是什么、谁读它」 | `named_coverage.py` 的全路径 / 裸文件名两个零命中数,均须为 0 |
| **L3-2 形态账** | 按**形态**分组,每组给**机械可复算的规模数**与**得出它的命令**;不要求穷举接口面 | 重跑命令核数字 |
| **L3-3 一条真链** | 至少一条「被谁读 → 在哪装配 → 缺了会怎样」的链,逐跳带锚点 | 顺锚点走一遍 |
| **L3-4 逐字取证下限** | ≥2 个逐字围栏块,**且钉在 L3-3 那条链的关键跳上** | BLOCK-DRIFT + 人工看是不是链上的跳 |
| **L3-5 记号或有搜索面的负结论** | ≥1 条 ■/▲/◇/◎;**或**「本簇未发现」+ 搜索面 | 抽验证据 / 看搜索面写没写 |

**为什么不是 L2 五条的削弱版。** L2 判据 2 要求「接缝穷举、不抽样」,理由是
「L2 可以不读实现,但不能抽样接口」——接口抽样了,「结构级理解」就退化成「看过几个文件」。
L3 没有这个风险,因为**L3 本来就不承诺理解接口**。L3 会退化成的样子是另一种:
**「我列了个目录」**。挡住这一种的不是穷举,是**规模数与算它的命令**——
目录谁都能列,「`en.ts` 有多少个叶子键、命令是什么」列不出来就是没打开过。

## 5. 环境与共享资源(开工读数)

| 资源 | 开工 | 备注 |
|---|---|---|
| Python 共享 venv | **87 包**(`pip list` 去表头 87,`dist-info` 87,两法一致) | 容器是全新的,venv 由本轮按 CLAUDE.md 的步骤重建;87 与 R9B–R10 报的 87 相同 |
| Python | 3.11.15 | |
| node 环境 | **1,186 包**,装在 `/home/user/r10b-ts/hermes-agent`(基线之外) | `git archive` 从基线导出的副本;**在派发子代理之前一次装好** |

node 环境用 `data/r10b/probes/ts_test_env.sh` 建,脚本开头先断言基线在
`863e31318` 且工作区干净,不满足直接退出——**npm 绝不能在基线里跑**,
R8A 记过一次 npm 重写 `package-lock.json` 的事故。
