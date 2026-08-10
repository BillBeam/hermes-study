# r11c-B · 定案去重:R11B 未裁决的 82 簇逐簇裁决

> **本片任务**:R11B 的机械候选是 **92 簇**(判据:同一锚点文件、行号 ±30 内、被 ≥2 个案号、
> 跨 ≥2 轮声明),它只裁决了 **10 组**(M-1 … M-10),**其余 82 簇明确未裁决、未外推**。
> 本片逐簇裁决那 82 簇。
>
> **不许按比例外推。** R11B §2.4 写的「从抽样看……也有大量『同一文件邻近处的不同断言』」
> 是**待验证的预期**,不是可套用的结论。本片每一簇都读两边正文再判;确有一批簇因**同一个
> 结构性理由**可合并说明的,**点名是哪些簇、给可重跑判定命令**,不给比例。
>
> **溯源约定**:对 hermes-agent 的断言用 `路径:行号 @ 863e313` + 逐字围栏块,锚点单独成行、置于块前。
> **对本学习仓库自己的产出**(`reports/` `notes/` `chapters/`)一律用 `>` 引用块 —— 与 R11B 同理:
> 本轮片 C(改 55 块坏证据)与片 D(改锚点)正在同一棵工作树上改历史 `notes/` 的行号,
> 引用块的契约是「找不到只记 UNCHECKED,不判失败」,把「万一被改到」的后果从阻断降为一条 UNCHECKED。
>
> **语料快照**:沿用 R11B 探针写死的 `CORPUS_REV = 00f09bf`(R11B 派工那一条 commit),
> 不读工作区。理由同上 —— 与片 C / 片 D 并发,从工作区读会让本底稿每一个数随它们的进度漂移。
> 这也保证本片的簇编号与 R11B 报的 92 簇**逐簇可对齐**。

---

## 0. 结论速览

*(本节随裁决进度增量更新;最终读数见 §5。)*

1. **「82 簇」这个数本身就是口径问题,先说清。** R11B 报「92 簇,裁了 10 组,剩 82」——
   **它裁的单位是「组(实体)」,不是「簇」**。一个实体常常横跨好几簇(M-1 那个中继媒体
   bearer 就同时落在 `gateway/relay/media.py` 的两簇和 `gateway/relay/adapter.py` 一簇上),
   所以「92 − 10 = 82」是**把两种单位相减**。本片的做法是:**给全部 92 簇逐簇出裁决**,
   对每簇注明它是否已被 R11B 的 M-1…M-10 覆盖、覆盖到什么程度(§1.3 给机械判据与读数)。
2. **本片的簇号 C01…C92 与 R11B 的 92 簇逐簇对齐**:同一份探针、同一个语料快照 `00f09bf`、
   同一套参数(`--window 30 --min-rounds 2`),编号取探针输出顺序。
3. **探针的第一类系统误差:锚点归属漂移(BLED)。** R11B 探针把「声明位的正文块」里
   **所有**锚点算作该声明的锚点,而项目符号块的边界是「空行或 12 行」——于是**连续排布的
   兄弟条目**会被前一条吃掉锚点。全语料 **2,358 个自有锚点里另有 182 个是吃来的**;
   其中 **2 簇(C55、C92)完全由吃来的锚点造出来**,判据与读数见 §1.3。
4. **本片裁决 32 个合并组**,涉及 68 个案号、合并后剩 31 个实体(另 1 个号并入 R11B 的 M-7),
   **案号净减 37**,其中 **定案号(▲◇■◎)净减 22**、移交号净减 15。
   去重后总数:R11B 的 ≤997 → **≤975**(口径差见 §5)。
5. **48 簇纯判「不合并」**(另有 34 簇在合并之外还各有不合并的部分),绝大多数落在 R-5:
   同一处代码上的不同断言。
   **R11B §2.4 的抽样预期在逐簇读完之后成立** —— 但它是被验证出来的,不是被外推出来的:
   C17 那一簇(R11B 举的例子)本片逐条读过两边正文,`H-3` 讲鉴权层、`H-11` 讲 profile 作用域、
   `▲-2` 讲 docstring 确实是三件事;而**同一批 92 簇里另有 32 组是真重复**,
   按比例外推会把它们一起判掉。

---

## 1. 口径与工具

### 1.1 簇编号:C01…C92,与 R11B 的 92 簇逐簇对齐

**结论先行:本片的 C01…C92 就是 R11B 那 92 簇,只是给它们编了号。** 同一个探针
(`data/r11b/probes/rulings_census.py`)、同一个语料快照 `00f09bf`、同一组参数
(`--window 30 --min-rounds 2`),编号取探针输出顺序,不重新聚类。

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11b/probes/rulings_census.py --clusters --window 30 --min-rounds 2 --summary
```

```text
# 同一处代码(同文件 ±30 行)被 ≥2 个案号、跨 ≥2 轮声明:92 簇
```

索引表(簇号 / 锚点文件 / 行号集 / 案号数 / 轮次数 / 状态 / 案号清单)在
`data/r11c/b-dedup-82-index.tsv`,由 `data/r11c/b-dedup-82-index.py` 生成;
逐簇的声明位正文上下文在 `data/r11c/b-dedup-82-context.txt`(292 个唯一声明位,3,696 行)
—— **本片的每一条裁决都是读过这份上下文之后下的,不是从探针的 130 字截断猜的。**

### 1.2 「92 − 10 = 82」是把两种单位相减

**结论:R11B 裁的单位是「组(实体)」,92 的单位是「簇」;机械核对下来,
仍须裁决的是 84 簇,不是 82。** 差额 2 不是谁算错了,是这两个单位不可相减 ——
一个实体常横跨多簇(M-1 的中继媒体 bearer 同时落在 C01 / C05 / C23 三簇),
而一簇也常同时含 M 组内与 M 组外的案号(C01 除 M-1 的五个号外,还有 `H-R9A-h` 与 `H-R8D-e`)。

判定脚本把 R11B §2.3 那张表的十组案号写死,再按「簇内案号是否全落在某一个 M 组里」分三类;
`M-3/-4/-5/-6/-7/-8/-10` 的裸序号在别的文件里也叫同一个名字,所以额外按**声明所在文件**限定,
否则无关的 `■-1` / `▲3` 会被算成已覆盖。

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11c/b-dedup-82-coverage.py | head -6
```

```text
簇总数 92
  R11B 的 M 组**完整覆盖**的簇: 8  -> ['C05', 'C09', 'C23', 'C25', 'C26', 'C27', 'C59', 'C60']
  M 组**部分覆盖**的簇:        14  -> ['C01', 'C03', 'C06', 'C07', 'C13', 'C14', 'C16', 'C18', 'C19', 'C22', 'C33', 'C42', 'C78', 'C92']
  M 组**一个案号都不沾**的簇:  70
  本片仍须出裁决的簇 = 84(R11B 报的是 82)
```

**本片的做法是给全部 92 簇出裁决**(那 8 个全覆盖簇也逐簇写明「属哪个 M 组、本片无新增」),
这样 92 这个分母、84 这个待裁数、以及每一簇的去向,三个数字互相对得上。

### 1.3 探针的第一类系统误差:锚点归属漂移(BLED)

**结论:全语料 2,540 个锚点归属里有 182 个是「吃」邻居的,其中 2 簇(C55、C92)
完全由吃来的锚点造出来 —— 它们根本不是簇。** 判据机械、无解释空间。

R11B 探针给每个「声明位」取一个正文块(表格行 = 本行;标题 = 到下一个同级标题、≤25 行;
项目符号 / 加粗段首 = 到空行、≤12 行),块里**所有** `路径:行号` 都记成这条声明的锚点。
于是**连续排布、中间没有空行的兄弟条目**会让前一条把后面几条的锚点全吃进来。
本片的判据:在块内自上而下走,**遇到「是另一个案号的声明行」就把归属切给那个案号**;
归属不是本条时读到的锚点记 `BLED`。剔除 BLED 后不再满足「≥2 案号 且 ≥2 轮」的簇记 `BLEED-ONLY`。

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11c/b-dedup-82-index.py --summary
```

```text
full 聚类簇数: 92
剔除 BLED 锚点后仍成簇: 90
BLEED-ONLY(只由锚点归属漂移造出来的簇): 2
锚点归属:own=2358 bled=182
```

最典型的一处是 R7C 定案卷的连续 bullet 列表:`▲-17` 到 `▲-21` 五条挨着写、中间无空行,
只有 `▲-21` 真的引了那个锚点,另外四条(外加 `■-3`)的这一个全是吃来的。
它是 `▲-21` 讲的那句「因为它在 `GATEWAY_KNOWN_COMMANDS` 里,unknown-command 兜底不触发」:

`gateway/run.py:15615 @ 863e313`

```
                    if command.replace("_", "-") not in GATEWAY_KNOWN_COMMANDS:
```

逐条明细在 `data/r11c/b-dedup-82-bleed.txt`(462 行),含每条 BLED 锚点**真正属于哪个案号**。

**这类误差的方向要说清:它让候选簇偏多(假阳性),不会漏簇。** 对本片是好事
—— 探针的职责是不漏,判断由人做;但报数时不能把假阳性算进「同一处代码被多个案号声明」的战果。

### 1.4 沿用 R11B 的 7 条合并规则

R-1 别名保留不删 / R-2 现行号取最后一次给实质结论的 / R-3 定案号优先于移交号 /
R-4 候选·定案·成品章三层的号并成一条 / R-5 **同处代码但断言实质不同的不合并** /
R-6 一条定案的多个位点算一条 / R-7 片内铸号带片标识(见 `notes/r11b-raw-rulings-census.md` §2.6)。

**R-2 与 R-3 会打架,本片按 R11B 自己的先例判 R-2 优先。** 依据是 M-7:那一组里
`■1`(定案号)与 `H-R9D-a`(移交号)并存,R11B 保留的是**移交号** `H-R9D-a`,
理由写的是「R11A 已结清」—— 即「最后一次给实质结论」。本片在 B-01 / B-14 / B-17 / B-18 /
B-19 / B-28 / B-29 六组遇到同一形态,一律照此判,不另立规则。

---

## 2. 裁决结果之一:32 个合并组

**结论先行:在 92 簇上裁出 32 个合并组(它们散落在 34 个簇里),涉及 68 个案号,合并后剩 31 个实体
(另有 1 个号并入 R11B 的 M-7),案号净减 37 —— 定案号净减 22、移交号净减 15。**
按**铸号是否跨轮**分:**12 组是跨轮铸号**(真该修的那一类)、**3 组同轮铸号但跨轮才结清**(记 ↦)、
**17 组是同轮内多号**(定案 + 移交、底稿 + 定案卷、底稿 + 成品章,属制度设计的产物)。
「跨轮」这一列判的是**两个号是不是在不同轮次铸出来的**,不是「结清跨没跨轮」——
两者会给出不同的数(15 对 12),按 CLAUDE.md「同一指标多方法测量分别标注」这里写清用的是前者。

命名按 CLAUDE.md 的案号纪律带片标识:`B-01` … `B-32` 全称为 `M-R11C-B-01` … `M-R11C-B-32`,
不与 R11B 的 `M-1` … `M-10` 同域。**别名一个不删**(R-1)。

| 组 | 实体(一处代码 / 一条断言) | 涉及案号 | 号数 | 定案号 | 现行号 | 跨轮 | 簇 |
|---|---|---|---|---|---|---|---|
| **B-01** | 写前守卫只查文件**可读**、不查**可解析** | `H-7`(R8A)、`H-R8FIX-a`(R8-fix→R8C 结清) | 2 | 0 | `H-R8FIX-a` | ✔ | C02 C08 C68 |
| **B-02** | `atomic_config_write` 自称唯一收口,主写入路径绕过它 | `▲-10`(R8A)、`▲-3`(R8C 底稿) | 2 | 2 | `▲-10` | ✔ | C02 |
| **B-03** | 同一条 `◎-2` 在 R8C 三份文件各登记一次 | `◎-2`×3(auth-py 底稿 / r8c-11 / r8c-90) | 3 | 3 | `◎-2`@`r8c-90` | ✘ | C02 |
| **B-04** | `PUT /api/config` 把凭据写进不轮换的文件 | `H-10`(R8A)、`■-1`(R8C 底稿)、`■-R8C-05`(R8C 定案) | 3 | 2 | `■-R8C-05` | ✔ | C11 C39 |
| **B-05** | `/curator` 有注册有文档有菜单、网关侧无 handler | `▲-8`(R7C 底稿)、`▲-21`(R7C 定案卷) | 2 | 2 | `▲-21` | ✘ | C10 |
| **B-06** | `/footer on\|off\|status` 在网关侧恒 toggle | `▲-01`(R7C 底稿)、`▲-17`(R7C 定案卷) | 2 | 2 | `▲-17` | ✘ | C10 C49 |
| **B-07** | 裸名 `homeassistant` 解析不出投递目标 | `▲-7`(R7C 底稿)、`▲-11`(R7C 定案卷) | 2 | 2 | `▲-11` | ✘ | C12 |
| **B-08** | `AGENTS.md` 把 `background` 说成可选开关 | `▲1`(R9A 底稿)、`▲3`(r9a 成品章) | 2 | 2 | `▲1` | ✘ | C13 |
| **B-09** | LSP 冷启动 > 8s 走的是 M-7 同一条路 | `■2`(R9D 底稿)→ 并入 M-7 | 1 | 1 | `H-R9D-a` | ✘ | C14 |
| **B-10** | 快照路径漏传 `timeout=`,与同函数另一调用点不一致 | `■11`(R9D 底稿)、`H-R11A-b`(R11A) | 2 | 1 | `H-R11A-b` | ✔ | C14 |
| **B-11** | `HERMES_DESKTOP_HERMES` 跳过探针,与 README 的全称句冲突 | `▲-3`(R10 底稿)、`H-R10H-h`(R10 同底稿移交表) | 2 | 1 | `▲-3` | ✘ | C15 |
| **B-12** | 桌面 README 只列三种连接模式,代码四种 | `◎-1`(R10B)、`H-R10B-C-i`(R10B) | 2 | 1 | `◎-1` | ✘ | C15 |
| **B-13** | 删 bootstrap marker 强制干净首启:代码明确不这么做 | `▲-1`(R10 底稿)、`H-R10H-g`(R10 移交表) | 2 | 1 | `▲-1` | ✘ | C20 |
| **B-14** | `cli.py` 装载器用 `dict.update` 浅合并 | `■-3`(R8A 定案)、`H-2`(R8A→R8B 穷举结清) | 2 | 1 | `H-2` | ↦ | C21 |
| **B-15** | dashboard 的 `PairingStore()` 与 `PairingStore("default")` 不等价 | `H-11`(R8A)、`◇-R8C-a`(R8C 结清时新立) | 2 | 1 | `◇-R8C-a` | ✔ | C17 |
| **B-16** | `env_loader` 两条写全局的路径只有一条持锁 | `H-17`(R8A)、`■-R8C-01`(R8C 结清) | 2 | 1 | `■-R8C-01` | ✔ | C06 C22 C35 |
| **B-17** | `models.py` 的 Bearer 走裸 `urlopen`,`base_url` 可控 | `■2`(R8D 底稿)、`H-R8D-e`(R8D→R9A 关闭并加重) | 2 | 1 | `H-R8D-e` | ✘ | C75 |
| **B-18** | `PYTEST_CURRENT_TEST` 让受管层整层消失 | `■-3`(R8D 定案卷)、`H-R8D-f`(R8D→R9A 关闭) | 2 | 1 | `H-R8D-f` | ✘ | C74 |
| **B-19** | status 判插件平台用 `check_fn()`,孪生实现已修好 | `■-31`(R8A)、`H-13`(R8A→R8B) | 2 | 1 | `H-13` | ↦ | C71 |
| **B-20** | 看板收尸用 `waitpid(-1)` 替别人的子进程收尸 | `■-2`(R9A 底稿)、`H-R9A-b`(R9A→R9D 立 ■) | 2 | 1 | `H-R9A-b` | ↦ | C72 |
| **B-21** | 子代理生命周期的裸 `submit` 不带上下文传播 | `H-R9A-e`(R9A→R9D)、`H-R9D-e1`(R9D 片内号) | 2 | 0 | `H-R9A-e` | ✔ | C53 |
| **B-22** | Skills Hub 取自远端 JSON 的 URL 走裸 `httpx.get` | `H-R9A-f`(R9A→R9D)、`H-R9D-f1`(R9D 片内号) | 2 | 0 | `H-R9A-f` | ✔ | C83 |
| **B-23** | `resolve_portal_base_url` 不查主机白名单 | `H-R9C-1`(R9C 底稿片内号)、`H-R9C-a`(R9C 主线号) | 2 | 0 | `H-R9C-a` | ✘ | C65 C76 |
| **B-24** | `check_voice_requirements()` 的内置 STT 名单漏 `deepinfra` | `■-1`(R9B 底稿)、`H-R9B-1`(R9B 片内号)、`H-R9B-a`(R9B 主线号) | 3 | 1 | `H-R9B-a` | ✘ | C44 C45 |
| **B-25** | 白名单放行的资源属性键随后被无条件覆盖 | `■-16`(R8A)、`■-2`(R9C monitoring 底稿) | 2 | 2 | `■-2`@`r9c-raw-monitoring-egress` | ✔ | C51 |
| **B-26** | 内置 secret 源到底两个还是三个 | `▲1`(R8D 底稿)、`▲-1`(R9C secret-sources 底稿) | 2 | 2 | `▲-1`@`r9c-raw-secret-sources` | ✔ | C52 C91 |
| **B-27** | `DebugSession` 在模块 import 时定格 `get_hermes_home()` | `■-6`(R9D 底稿)、`H-R9D-F-h`(R9D 同底稿移交表) | 2 | 1 | `■-6` | ✘ | C41 |
| **B-28** | 托管网关信任闸门对主机名大小写敏感 | `■-3`(R9D 底稿)、`H-R9D-F-f`(R9D 移交表)、`H-R9D-d`(R9D 主线号) | 3 | 1 | `H-R9D-d` | ✘ | C43 |
| **B-29** | 网关重启后 TUI 订阅开关无复位路径 | `■-2`(R10 底稿)、`H-R10D-a`(R10 移交表)、`H-R10-f`(R10 主线号) | 3 | 1 | `H-R10-f` | ✘ | C47 |
| **B-30** | `send_message` 的「不给模型」禁令可经 `cronjob` 一跳绕过 | `■-1`(R9D 底稿)、`H-R9D-D-a`(R9D 同底稿移交表) | 2 | 1 | `■-1` | ✘ | C12 C29 |
| **B-31** | `clarify.timeout` 在两个面上相差 780 秒 | `■-11`(R8A 铸)、`■-11`(R8B 复述位) | 2 | 2 | `■-11`@R8A | ✔ | C56 |
| **B-32** | `approve` 还接受 request-id,文档只写 code | `◇1`(R7C)、`◇4`(R8A) | 2 | 2 | `◇1` | ✔ | C37 C85 |
| **合计** | **31 个新实体 + 1 个号并入 M-7** | | **68** | **40** | 其中 18 个是定案号 | **12 ✔ / 3 ↦** | |

### 2.1 跨轮的那一批(12 组 ✔ + 3 组 ↦):逐条给基线锚点

**这一批才是「该修」的那一类** —— R11B §2.7 已经指出「真正该修的是跨轮那 5 条,
而它们全都发生在没有别名表的地方」。R11B 的 5 条 + 本片按同一口径(**铸号跨轮**)的 12 条
= **17 条**;另有 3 条(B-14 / B-19 / B-20)两个号在同一轮铸出、**结清才跨了轮**,
按铸号口径不计入 12,但下面一并给锚点,因为它们的账面后果相同。

**B-01**:R8A 铸 `H-7`,R8B 声称关闭,R8-fix 作废该关闭并重铸为 `H-R8FIX-a`(加上 `auth.py` 那一半),
R8C 结清。**同一个守卫,两个号,横跨四轮。**

`hermes_cli/config.py:3065 @ 863e313`

```python
def require_readable_config_before_write(config_path: Optional[Path] = None) -> None:
```

**B-02**:R8A `▲-10` 与 R8C `▲-3` 判的是同一句 docstring 与同一组绕过者。

`hermes_cli/config.py:3092 @ 863e313`

```
    The single chokepoint every config-update path should use instead of
```

**B-04**:R8A 移交 `H-10`,R8C 底稿写成 `■-1(= H-10)`、定案卷改记 `■-R8C-05`。
三个号指的是同一条链:凭据写进 `config.yaml` 顶层,再被这段桥接成活的 `os.environ` 值。

`gateway/run.py:2058 @ 863e313`

```python
        for _key, _val in _cfg.items():
```

**B-10**:R9D 底稿的 `■11` 与 R11A 的 `H-R11A-b` 指同一行、同一条修法(补传 `timeout=`)。

`agent/lsp/manager.py:486 @ 863e313`

```python
            fresh = await client.wait_for_diagnostics(file_path, version, mode=self._wait_mode)
```

**B-14**:`■-3` 是缺陷本身,`H-2` 是「影响面未穷举」,R8B 穷举完毕给出实质结论。

`cli.py:599 @ 863e313`

```python
                        defaults[key].update(file_config[key])
```

**B-15**:`H-11` 问「有几套 profile 作用域」,R8C 结清时把答案落成 `◇-R8C-a`
——「不传」与「传 current」被合并成同一条路,而两者不等价。

`hermes_cli/web_server.py:12303 @ 863e313`

```python
    requested = (profile or "").strip()
```

**B-16**:`H-17`(R8A 铸)与 `■-R8C-01`(R8C 结清)是同一实体;
无锁的那一半是这个函数。

`hermes_cli/env_loader.py:591 @ 863e313`

```python
def _apply_external_secret_sources(home_path: Path) -> None:
```

**B-19**:`■-31` 与 `H-13` 都锚在这段「已修好的孪生实现」上。

`hermes_cli/gateway.py:5451 @ 863e313`

```python
            # No is_connected hook — fall back to check_fn as a coarse
```

**B-20**:R9A 底稿的 `■-2` 与主线 `H-R9A-b` 同一行,R9D 立 ■。

`hermes_cli/kanban_db.py:6941 @ 863e313`

```python
                    pid, status = os.waitpid(-1, os.WNOHANG)
```

**B-21 / B-22**:R9D 的取证片给同一条移交项**又铸了一个片内号**(`H-R9D-e1` / `H-R9D-f1`),
与主线号 `H-R9A-e` / `H-R9A-f` 指同一行。这是 R11B §2.5 亚种 (b) 的镜像:
那里是**主线与片各铸一套同名号**,这里是**片给已有号另起了一个名字**。

`agent/subagent_lifecycle.py:259 @ 863e313`

```python
        record.future = _EXECUTOR.submit(self._run, record, request.goal, parent)
```

`tools/skills_hub.py:3205 @ 863e313`

```python
            resp = httpx.get(md_url, timeout=20, follow_redirects=True)
```

**B-25**:R8A `■-16` 说的是 `service.name` 一个键,R9C `■-2` 说的是三个键,**后者是超集**
—— 按 R-2 取 R9C 那个号(同 R11B 处理 M-3 的方式)。

`agent/monitoring/gateway_health_export.py:85 @ 863e313`

```python
    attrs["service.name"] = "hermes-gateway"
```

**B-26**:R8D `▲1` 与 R9C `▲-1` 判的是同一句 —— 模块 docstring 说 command 是「可能的未来例外」,
而它已经在树里、已被注册为内建。

`agent/secret_sources/__init__.py:29 @ 863e313`

```
package.  A generic ``command`` source is a possible future exception;
```

**B-31**:R8B `notes/r8b-90-handover-rulings.md:359` 那处是**引用 R8A 的 `■-11` 做对照**,
不是新铸;因 `L` 家族按文件定作用域,探针把它算成第二个号。
**这一类不是重复登记,是计数口径的产物 —— 但它确实让「定案号总数」多了 1,所以照样要并。**

`tools/clarify_gateway.py:388 @ 863e313`

```
    Single source of truth shared by every surface (messaging gateway, CLI,
```

**B-32**:R7C `◇1` 与 R8A `◇4` 是同一句文档、同一条代码事实。R7C 那条还带完整搜索面
(`grep -rn "request_id\|request-id" website/docs/` 零命中)。

`website/docs/reference/cli-commands.md:1119 @ 863e313`

> | `approve <platform> <code>` | Approve a pairing code. |

### 2.2 十七条同轮内多号:形态分三种,都不是错误

**结论:同轮内的多号不是失误,是制度设计的产物;但它们照样让「定案号总数」虚高,
所以要建别名表。** 三种形态各给一个样本(其余同型,见 §3 逐簇表):

1. **底稿号 + 定案卷号**(B-05 / B-06 / B-07):片底稿先用 `▲-01`,主线登记卷统成 `▲-17`。
   R11B 的 M-6 就是这一形态,本片再找到 3 条。
2. **定案号 + 同底稿移交表号**(B-11 / B-12 / B-13 / B-27 / B-30):
   一份底稿在正文立 `▲-3`,又在文末移交表给同一条铸 `H-R10H-h`。
   **这是 R8A 起「移交项必须带锚点」这条规矩的副作用**:移交表要求锚点,
   于是每条移交都长得像一次独立铸号。
3. **底稿号 + 片内号 + 主线号三层**(B-24 / B-28 / B-29):
   `■-1`(底稿)→ `H-R9B-1`(片内)→ `H-R9B-a`(主线)。

`tools/voice_mode.py:2193 @ 863e313`

```python
    native_stt_available = stt_provider in {
```

`tools/managed_tool_gateway.py:298 @ 863e313`

```python
    return bool(actual.scheme) and (actual.scheme, actual.netloc) == (expected.scheme, expected.netloc)
```

`ui-tui/src/gatewayClient.ts:221 @ 863e313`

```ts
    this.subscribed = false
```

`apps/desktop/electron/backend-probes.ts:190 @ 863e313`

```ts
  return typeof hermesOverride === 'string' && hermesOverride.trim().length > 0
```

`apps/desktop/electron/main.ts:3912 @ 863e313`

```ts
    if (!activeRuntime.hasValidMarker) {
```

`tools/debug_helpers.py:47 @ 863e313`

```python
        self.log_dir = get_hermes_home() / "logs"
```

`hermes_cli/managed_scope.py:49 @ 863e313`

```python
    return "PYTEST_CURRENT_TEST" in os.environ
```

`hermes_cli/models.py:4612 @ 863e313`

```python
        with urllib.request.urlopen(req, timeout=timeout) as resp:
```

`hermes_cli/nous_billing.py:179 @ 863e313`

```python
    env = os.getenv("HERMES_PORTAL_BASE_URL") or os.getenv("NOUS_PORTAL_BASE_URL")
```

`cron/scheduler.py:1233 @ 863e313`

```python
    chat_id = _get_home_target_chat_id(platform_name)
```

`AGENTS.md:986 @ 863e313`

> context + terminal session. By default the parent waits for the

`apps/desktop/README.md:133 @ 863e313`

> Desktop supports a managed local backend, explicit remote gateways, and Hermes

`website/docs/reference/slash-commands.md:266 @ 863e313`

> | `/footer [on\|off\|status]` | Toggle the runtime-metadata footer on final replies (shows model, context %, and cwd). |

---

## 3. 逐簇裁决表(全部 92 簇)

**结论先行:34 簇含合并裁决(共 32 个合并组,见 §2),48 簇纯判不合并,
8 簇属 R11B 的 M 组已完整覆盖,2 簇判不成簇。四类加总 = 92。**
「裁决」列的取值只有四种:`合并`(给出组号)、`不合并`(给出 R-5 之类的依据)、
`R11B 已覆盖`(注明属哪个 M 组)、`不成簇`(BLEED-ONLY,探针假阳性)。
**锚点列写在独立单元格、后面不跟反引号摘录**,故按 R9B 规则记 TABLE-UNCHECKED —— 它是索引不是证据,
证据在 §2 的基线摘录与 `data/r11c/b-dedup-82-context.txt`。

| 簇 | 锚点(文件:行) | 涉及案号(轮次) | 裁决 | 依据 |
|---|---|---|---|---|
| C01 | gateway/relay/media.py:80,92,94 | H-R9A-a(R9A/B/C)、■-01(R9A)、H-R9B-d(R9B/R10/R10B/R11A)、■-R11A-01、H-R11A-a(R11A);另 H-R9A-h(R9B)、H-R8D-e(R9A) | 主体 R11B M-1 已覆盖;**新增 2 条不合并** | H-R9A-h 是「表格锚点恒 UNCHECKED」的制度条,标题块吃到本文件锚点;H-R8D-e 是「带凭据裸 urlopen」普查,把本行当样本之一。两条都不是 bearer 子串判定 → R-5 |
| C02 | hermes_cli/config.py:3065,3089,3092 | H-7(R8A/R8B)、H-R8FIX-a(R8B/R8C/R8-fix)、◎-2×3(R8C)、▲-10(R8A)、▲-1/▲-2/▲-3(R8C) | **合并 B-01 / B-02 / B-03** | 见 §2.1;▲-1、▲-2 的本文件锚点是 BLED(真属 ▲-3) |
| C03 | gateway/pairing.py:414,421,424,437 | ▲-1/▲-2(R8C)、◇3(R7C)、H-11、■-39(R8A) | **不合并**(▲-1 锚点 BLED) | ▲-2 判 dashboard 的 docstring 错、◇3 判频道目录无 profile 隔离、H-11 问「有几套 profile 机制」、■-39 判两个 UI 元素写不同库 —— 四件事 → R-5 |
| C04 | cli.py:477,479,481 | ■-12、■-10(R8A)、◇-2(R10B)、H-1(R8B) | **不合并** | 四条是「cli.py 有第二棵默认树」的不同后果;H-1 是伞(28 键未逐一确证),■-10 / ■-12 是它已证的两个实例 —— **包含关系不是重复** |
| C05 | gateway/relay/media.py:154,162,164,169 | H-R9A-a、H-R9B-d、■-R11A-01 | **R11B M-1 已覆盖**,本片无新增 | 全部案号落在 M-1 内;它是「一个实体横跨多簇」的样本 |
| C06 | hermes_cli/env_loader.py:640,666,667 | H-R8C-d、H-R8D-c(→M-2)、■-R8C-01(R8C) | M-2 覆盖前两号;**■-R8C-01 不合并**(另见 B-16) | R8C 自陈「■-R8C-01 只复现了另外两个全局」,`_SECRET_SOURCES` 是第三个 → R-5 |
| C07 | hermes_constants.py:274,278,280 | ▲3(R7C)、◇3(R8A)(→M-4)、■-2(R9B) | M-4 覆盖前两号;**■-2 不合并** | ■-2 讲视频缓存目录两处解析不一致,与配对存储路径无关 → R-5 |
| C08 | hermes_cli/auth.py:7329 | H-R8FIX-a(R8B/R8C/R8-fix)、■-R8B-12(R8C) | **合并 B-01**;■-R8B-12 **不合并** | 一个是守卫判据不足,一个是「静默消失」定性被推翻;R8C §5.4 已互相点名 |
| C09 | hermes_cli/web_server.py:5519,5521,5524 | ■-R10-01(R10/R10B)、H-R10-d(R10/R10B/R11A) | **R11B M-9 已覆盖** | 全部案号落在 M-9 内 |
| C10 | gateway/run.py:15595,15615 | ▲-21、▲-8、▲-6、■-3、▲-17…▲-20(R7C)、▲-2(R9A) | **合并 B-05**;▲-6 与 R9A ▲-2 不合并;■-3/▲-17/▲-18/▲-19/▲-20 的锚点 BLED | 见 §1.3;▲-6 讲前缀匹配、R9A ▲-2 讲 bundle 集中派发 → R-5 |
| C11 | gateway/run.py:2057,2058 | H-10(R8C)、■-1(R8C)、■-R8C-05(R8C)、◇-1c(R8A)、◇-1/◇-1b(R8A,BLED) | **合并 B-04**;◇-1c **不合并** | ◇-1c 是「这条桥零文档」,B-04 是「凭据经这条桥泄漏」—— 机制与后果,互相点名 → R-5 |
| C12 | cron/scheduler.py:1210,1231,1233 | ▲-7、▲-11(R7C)、◇-1(R7C)、■-1(R9D)、▲-9/▲-10(BLED) | **合并 B-07**;■-1 参见 B-30;◇-1 **不合并** | ◇-1 讲 `whatsapp_cloud` 死配置,与 HA 裸名解析无关 → R-5 |
| C13 | AGENTS.md:964,966,971,986 | H-R9A-g(R9A/R9D)、▲-3(R9A)、▲4(章)(→M-10);▲1(R9A)、▲3(章) | M-10 覆盖前三号;**合并 B-08** | ▲1(底稿)与 ▲3(成品章)是同一条 `background` 断言 → R-4 |
| C14 | agent/lsp/manager.py:480,486 | ■1、■2、■11(R9D)、H-R9D-a、H-R11A-b(R11A) | **合并 B-09 / B-10** | `■1`@:1816 是探针从 `■11` 里切出的幽灵号(`is_decl` 做子串匹配),不计入 |
| C15 | apps/desktop/README.md:114,131,133 | ▲-3、H-R10H-h(R10)、◎-1、H-R10B-C-i、▲1(R10B) | **合并 B-11 / B-12**;▲1 **不合并** | ▲1 讲换 profile 软切换 vs 冷启,与探针跳过、连接模式数目无关 → R-5 |
| C16 | hermes_cli/pairing.py:81,96,97 | ▲3(R7C)、◇6(R8A)(→M-4);■-6、■-8、■-24(R8A) | M-4 覆盖前两号;**三条 ■ 不合并** | ■-6 捅穿封装、■-8 两把钥匙不一致;**■-24 的前半与 ◇6 同**(硬编码新版路径),后半是 GUI 无恢复提示 —— 断言不等价,按 R-5 不并、互相点名 |
| C17 | hermes_cli/web_server.py:12296,12303,12309,12320,12321 | H-11(R8A/R8C)、H-3(R8A/R8C)、▲-2(R8C)、◇-R8C-a(R8C)、▲-1(BLED) | **合并 B-15**;H-3 与 ▲-2 **不合并** | **R11B §2.4 拿这一簇举例说「三件事」,本片逐条读后确认成立**:H-3 是鉴权层、▲-2 是 docstring、B-15 是构造语义 → R-5 |
| C18 | website/docs/developer-guide/gateway-internals.md:59,86 | ▲21(R7)、▲-B-1(R7B)、▲1(章)(→M-5);▲-B-2(R7B) | M-5 覆盖前三号;**▲-B-2 不合并** | ▲-B-2 判 `:59` 的「`/stop` `/approve` 走同一条 inline 路」,是另一句 → R-5 |
| C19 | agent/file_safety.py:274,278,284 | ■-1(R9C)、■-2、H-R9D-B-b(R9D)(→M-3);H-R9C-b(R9D) | M-3 覆盖前三号;**H-R9C-b 不合并** | H-R9C-b 判的是 `secrets_cli` 落盘卫生与 `.env` 是否在禁读清单,不是 `op_cache.json` → R-5 |
| C20 | apps/desktop/README.md:155,156,183,184 | ▲-1、H-R10H-g(R10)、▲1、◎2(R10B) | **合并 B-13**;▲1、◎2 **不合并** | 三条断言分别是 marker、软切换、nanostores 清理范围 → R-5 |
| C21 | cli.py:598,599,624 | ■-3、H-2、H-4(R8A)、H-1/H-2(R8B) | **合并 B-14**;H-4 **不合并**;H-1@:1/:10 锚点 BLED | H-4 是「`managed_scope` 本体未读」,只在此处顺带提到 `cli.py:624` → R-5 |
| C22 | cron/scheduler.py:332,334 | ▲-1×2(R7C 两底稿)、▲-4(R7C 定案卷)(→M-6);■-R8C-01(R8C) | M-6 覆盖前三号;**■-R8C-01 不合并**(另见 B-16) | ■-R8C-01 引 `:332` 只为说明 cron 并行池是触发场景,不是关于 `running` 幽灵状态 → R-5 |
| C23 | gateway/relay/adapter.py:461,471 | ■-01、H-R11A-a、H-R9B-d、■-R11A-01 | **R11B M-1 已覆盖** | 同 C05,是 M-1 的第三个位点(R-6) |
| C24 | hermes_cli/web_server.py:12330,12337,12346,12347 | ◇1、▲1(R7C)、■-8、■-24(R8A) | **不合并** | 四条:request-id 路径无文档 / DM 配对方向写反 / 两把钥匙不一致 / 恢复提示只有 CLI → R-5 |
| C25 | agent/agent_runtime_helpers.py:59,78,79 | H-R9D-c、■-4、H-R9D-F-b | **R11B M-8 已覆盖** | 全部案号落在 M-8 内 |
| C26 | agent/lsp/manager.py:313 | H-R9D-A-a、H-R9D-a、■1 | **R11B M-7 已覆盖** | 全部案号落在 M-7 内 |
| C27 | agent/think_scrubber.py:79,89 | ■-4、H-R9D-F-b、H-R9D-c | **R11B M-8 已覆盖** | 同 C25,M-8 的第二个位点 |
| C28 | apps/desktop/electron/preload.ts:103,126 | ▲1、◇1(R10B)、H-R10H-j(R10) | **不合并** | ▲1 与 ◇1 在**同一行标题**(`### ◇1 …(即 ▲1 的另一面)`)—— ▲1 在此是引用不是铸号;H-R10H-j 讲 `webUtils` 直调,另一件事 → R-5 |
| C29 | cron/scheduler.py:1158,1177 | ◇-1(R7C)、■-1、H-R9D-D-a(R9D) | **合并 B-30**;◇-1 **不合并** | ■-1 与 H-R9D-D-a 是同一条(NOTE 声称模型不能发 vs 经 cronjob 绕过);◇-1 是死配置 → R-5 |
| C30 | cron/scheduler.py:2638,2643,2663 | ◇-5、▲-2(R9A)、◇-5(R7C) | **不合并** | 三条不同;**点名**:R9A `◇-5`(预处理两份实现)与 R7C `◇-5`(组装后二次扫描无文档)是**同号不同实体**,属 R11B 第二物种 |
| C31 | gateway/platforms/base.py:3758,3766,3780 | ◇-08、◇-09(R7C)、■-1(R9D) | **不合并** | ◇-08 判 `_resolve_slash_confirm` 是幽灵 API、◇-09 判 docstring 的调用方清单过时 —— 同段 docstring 两条断言;■-1 判 webhook 会话留着 `clarify` → R-5 |
| C32 | gateway/run.py:14455,14479 | ▲1(R7C)、▲-6(R8A 底稿 + 成品章) | **不合并** | ▲-6 两处是同号同实体(R-4 已并,不额外计);▲1 判 DM 配对方向写反,▲-6 判 FAQ 把配对讲成先到先得 → R-5 |
| C33 | hermes_cli/backup.py:1099,1112,1116 | ◇2(R7C)、◇3(R9A)、▲3(R7C→M-4) | M-4 覆盖 ▲3;**◇2、◇3 不合并** | ◇2 讲 `channel_aliases.json` 零文档、◇3 讲台账进备份白名单 → R-5 |
| C34 | hermes_cli/dashboard_auth/public_paths.py:39,48,51 | ◎-1、◎-2(R8C)、◇-G-03(R10) | **不合并** | 三条各针对一个公开端点:`/api/status` 面偏宽、`/api/model/info` 理由不符、前端登录前拉两个端点 → R-5 |
| C35 | hermes_cli/env_loader.py:588,591,614 | H-17(R8A/R8C)、■-R8C-01(R8C)、■-27(R8A) | **合并 B-16**;■-27 **不合并** | ■-27 讲同一个 managed `.env` 被两个解析器读,与锁无关 → R-5 |
| C36 | hermes_cli/pairing.py:15,18,42 | ■-39、■-37(R8A)、◇1(R7C) | **不合并** | 三条:两个 UI 元素写不同库 / 失败路径全 exit 0 / request-id 路径无文档 → R-5 |
| C37 | hermes_cli/pairing.py:49,71,72 | ◇4(R8A)、◇1、▲1(R7C) | **合并 B-32**(◇1+◇4);▲1 **不合并** | 见 §2.1;▲1 是 DM 配对方向 → R-5 |
| C38 | hermes_cli/subcommands/pairing.py:16,31,39 | ▲6、◇1(R7C)、■-23(R8A) | **不合并** | ▲6 命名漂移 / ◇1 request-id / ■-23 `clear-pending` 清所有平台 → R-5 |
| C39 | hermes_cli/web_server.py:6917,6921,6923 | H-10(R8A/R8C)、▲-1(R8C)、■-51(R8A) | **合并 B-04**(H-10 两处);▲-1、■-51 **不合并** | ▲-1 判注释举例的键路径不准、■-51 判 `_deep_merge` 只浅拷贝 → R-5 |
| C40 | hermes_constants.py:114,132 | ◇-4(R7C)、■-6(R9D)、◇3(R7C kanban) | **不合并**,但**点名为 R12 装订时的一族** | 三条是**同一形态**(模块 import 期定格 `get_hermes_home()`)在三个子系统的独立定案(sticker_cache / DebugSession / HOOKS_DIR)。R-6 只管「一条定案的多个位点」,这里是三条定案 → 不并;但 R12 应合成一节讲 |
| C41 | tools/debug_helpers.py:43,47 | ▲-4(R9B)、■-6、H-R9D-F-h(R9D) | **合并 B-27**;▲-4 **不合并** | ▲-4 判文档说日志在 `./logs/` 与代码不符,是文档冲突;B-27 是 profile 定格缺陷 → R-5 |
| C42 | tools/lazy_deps.py:532,554 | H-R8C-g、■-R10-01(R10)(→M-9);H-R9B-g(R11A) | M-9 覆盖前两号;**H-R9B-g 不合并** | H-R9B-g 是「惰性安装纪律入册」的制度条,锚 `:532` 的开关;M-9 是 `install_specs` 的守卫缺口 → R-5 |
| C43 | tools/managed_tool_gateway.py:298 | ■-3、H-R9D-F-f(R9D)、H-R9D-d(R9D/R11A) | **合并 B-28** | 三号同一行同一条;R11A「两半都成立」中的大小写敏感那一半就是 ■-3 |
| C44 | tools/transcription_tools.py:336,341 | H-R9B-a(R9C)、H-R9B-1、■-1(R9B) | **合并 B-24** | 权威名单在本文件,漂掉的副本在 `voice_mode.py`;三号同一条 |
| C45 | tools/voice_mode.py:2193 | H-R9B-1、■-1、H-R9B-a(R9B/R9C) | **合并 B-24** | 同上,B-24 的第二个位点(R-6) |
| C46 | tools/xai_http.py:301,317,324 | ◇-1、■-7(R9C)、■-7(R9D) | **不合并** | ◇-1 判 `HERMES_XAI_BASE_URL` 只在 OAuth 生效、■-7(R9C)判 API-key 路径不校验、■-7(R9D)判 `x_search` 异常穿出工具边界;**点名**:两个 `■-7` 同号不同实体(第二物种) |
| C47 | ui-tui/src/gatewayClient.ts:213,221 | ■-2、H-R10D-a、H-R10-f(R10/R10B) | **合并 B-29** | 三号同一条:`subscribed` 只有一处置真、一处置假 |
| C48 | website/docs/reference/slash-commands.md:47,65,68,70 | ◇-10、▲-6(R7C)、▲2(R9A) | **不合并** | `/compress` 参数缺席 / `/agents` 作用域 / `/journey` 写两次 → R-5 |
| C49 | website/docs/reference/slash-commands.md:266,267,288 | ▲-01、▲-8(R7C)、◇2(R10B) | **合并 B-06**(▲-01);▲-8 属 B-05;◇2 **不合并** | ◇2 讲唤醒指示窗在桌面文档缺条目 → R-5 |
| C50 | agent/conversation_loop.py:2291,2312 | ◇-3(R8D)、■-2(R9A) | **不合并** | `VALID_HOOKS` 四成员无文档 vs `moa.presets.max_tokens` 死键 → R-5 |
| C51 | agent/monitoring/gateway_health_export.py:85 | ■-16(R8A)、■-2(R9C) | **合并 B-25** | 同一行、同一缺陷,R9C 是超集(3 个键) |
| C52 | agent/secret_sources/__init__.py:16,25 | ▲1(R8D)、▲-1(R9C) | **合并 B-26** | 同一句 docstring 的同一条断言 |
| C53 | agent/subagent_lifecycle.py:255,259 | H-R9A-e(R9A/R9D)、H-R9D-e1(R9D) | **合并 B-21** | R9D 的取证片给已有移交号又铸了一个片内号 |
| C54 | cli.py:31,53 | ■-41(R8A)、H-18(R8B) | **不合并** | H-18 是「约 50 条未复核候选」的伞,锚点来自它点名的 11 份底稿;■-41 是 `status --deep` 探错端口 → R-5 |
| C55 | cli.py:441 | H-1(R8A/R8B)、H-2(R8B) | **不成簇(BLEED-ONLY)** | 唯一的第二个案号 H-2,其 `cli.py:441` 锚点来自 H-1 的段落;剔除后只剩一个案号 |
| C56 | cli.py:523 | ■-11(R8A)、■-11(R8B) | **合并 B-31** | R8B 那处是引用 R8A 做对照,不是新铸;`L` 家族按文件定作用域才算成两个号 |
| C57 | cli.py:650,653 | ◇5(R7C)、■-R8B-10(R8B) | **不合并** | cwd 占位符三处复刻 vs `hermes -w` 隔离中途解除 → R-5 |
| C58 | gateway/authz_mixin.py:583,585 | ▲6(R7C)、■-36(R8A) | **不合并** | 注释里的命令名漂移 vs `revoke` 吞异常导致仍被放行 → R-5 |
| C59 | gateway/pairing.py:18 | ▲3(R7C)、◇3(R8A) | **R11B M-4 已覆盖** | M-4 的一个位点 |
| C60 | gateway/pairing.py:59 | ▲3(R7C)、◇3(R8A) | **R11B M-4 已覆盖** | M-4 的另一个位点(R-6) |
| C61 | gateway/pairing.py:733,735 | ■-38(R8A)、◇1(R7C) | **不合并** | 形状判别把手抄错的 request-id 记成暴力破解 vs request-id 路径无文档 → R-5 |
| C62 | gateway/run.py:3137,3145,3148 | ◇-06(R7C)、■-12(R8A) | **不合并** | 多 profile 作用域只覆盖 3 个命令 vs 14 个人格网关侧不存在 → R-5 |
| C63 | gateway/run.py:15489,15506 | ▲-7(R7C)、▲-2(R9A) | **不合并** | 非 admin 命令闸门 vs bundle 集中派发 → R-5 |
| C64 | gateway/slash_commands.py:2502,2507 | ▲-1(R10B)、■-12(R8A) | **不合并**,互相点名 | 同一键 `agent.personalities`:▲-1 判文档教用户写在顶层,■-12 判默认值只在 CLI 侧 → R-5 |
| C65 | hermes_cli/auth.py:5900 | H-R9C-1(R9C)、H-R9C-a(R9C/R9D) | **合并 B-23** | 片内号与主线号指同一条 |
| C66 | hermes_cli/backup.py:928,934 | H-R8C-f(R11A)、◇-2(R8D) | **不合并** | import 来源校验是否只查 basename(已证伪)vs backup zip 未加密 → R-5 |
| C67 | hermes_cli/config.py:1850,1873 | ◇-1b(R8A)、◇-1(R7C) | **不合并** | `DEFAULT_CONFIG` 非全部合法键 vs `filter_silence_narration` 零文档 → R-5 |
| C68 | hermes_cli/config.py:2127,2142,2147 | ■-25(R8A)、H-7(R8B) | **不合并**(H-7 另见 B-01) | ■-25 判迁移写的值等于默认值被剥掉;H-7 在此的锚点来自它 §1.9 复述迁移流水线 → R-5 |
| C69 | hermes_cli/config_defaults.py:2436,2463 | ■-2(R9C)、◇-5(R7C) | **不合并** | 资源属性键被覆盖 vs `delivery_obligations` 表无存储文档 → R-5 |
| C70 | hermes_cli/config_migrations.py:250,258 | H-16(R8A)、■-11(R8B) | **不合并** | H-16 判 v16 搬完不删旧键;■-11@R8B 是复述位(对照表里「做对」的那一列) → R-5 |
| C71 | hermes_cli/gateway.py:5451 | H-13(R8A/R8B)、■-31(R8A) | **合并 B-19** | 同一行,定案 + 移交成对 |
| C72 | hermes_cli/kanban_db.py:6930,6936,6937,6941 | ■-2(R9A)、H-R9A-b(R9A/R9D) | **合并 B-20** | 同一行 `waitpid(-1)`,R9A 自陈「H-R9A-b(■-2 的范围确认)」 |
| C73 | hermes_cli/main.py:11601 | H-18(R8B)、▲6(R7C) | **不合并** | 同 C54,H-18 是伞;▲6 判 `hermes gateway pairing` 子命令不存在 → R-5 |
| C74 | hermes_cli/managed_scope.py:41,44,49 | ■-3(R8D)、H-R8D-f(R8D/R9A) | **合并 B-18** | H-R8D-f@:1283 的 `:49` 锚点是 BLED(真属 H-R9A-d),不影响本判 |
| C75 | hermes_cli/models.py:4612 | ■2(R8D)、H-R8D-e(R8D/R9A) | **合并 B-17** | 同一行,定案 + 移交成对 |
| C76 | hermes_cli/nous_billing.py:173,179 | H-R9C-1(R9C)、H-R9C-a(R9C/R9D) | **合并 B-23** | B-23 的第二个位点(R-6) |
| C77 | hermes_cli/providers.py:91,92,107 | ■-R9C-6(R9C 两处同文件)、■-35(R8A) | **不合并** | `copilot-acp` 三处 api_mode 不一致 vs 6 家 provider 同屏出现两次 → R-5 |
| C78 | hermes_cli/web_server.py:639,640,665 | H-R8C-g(R10→M-9)、▲-1(R8C) | M-9 覆盖 H-R8C-g;**▲-1 不合并** | ▲-1 判注释写的中间件顺序与实际相反 → R-5 |
| C79 | pyproject.toml:157,167 | H-R8D-j、H-R9B-e(R9D 同一表格行)、H-R9B-e(R9B) | **不合并** | R9D 把两号写在同一行,但 H-R8D-j 是「跑通全套要哪些 extra」、H-R9B-e 是「缺 extra 表现为断言失败而非 ImportError」,R11A 也分别给了结论 → R-5 |
| C80 | tools/clarify_gateway.py:364,388 | ◇-1(R9D)、■-11(R8A) | **不合并** | `clear_session` 连带取消整会话 vs `clarify.timeout` 780 秒漂移 → R-5 |
| C81 | tools/managed_tool_gateway.py:147,153 | ◇-7(R9D)、H-R9D-d(R11A) | **不合并** | `TOOL_GATEWAY_SCHEME=http` 让 bearer 走明文 vs 主机比对大小写敏感 → R-5 |
| C82 | tools/skills_hub.py:302 | ■-4(R9A)、H-R9A-f(R9D) | **不合并** | 两者都以 `:302` 的守卫为参照:■-4 说 `browse.sh` 适配器绕过它,H-R9A-f 说 `md_url` 那一跳没过它 → R-5 |
| C83 | tools/skills_hub.py:3201,3205 | H-R9A-f(R9A/R9D)、H-R9D-f1(R9D) | **合并 B-22** | 同 B-21 形态 |
| C84 | tools/working_diff.py:70 | H-R9A-c ◇(R9D)、◇-12(R7C) | **不合并** | 验证门从不调 `collect_working_diff` vs `/diff <path>` 在网关被静默忽略 → R-5 |
| C85 | website/docs/reference/cli-commands.md:1119 | ◇1(R7C)、◇4(R8A) | **合并 B-32** | 同一句文档、同一条代码事实,跨轮 |
| C86 | website/docs/reference/environment-variables.md:112,128 | ◎-1(R9B)、H-R9C-a(R9D) | **不合并** | `HERMES_LOCAL_STT_LANGUAGE` 作用范围写窄 vs Portal 基址白名单(H-R9C-a 在此只是引了同一份文档表) → R-5 |
| C87 | website/docs/user-guide/features/hooks.md:670,689 | ▲3(R9A)、H-R9A-c ▲(R9D) | **不合并** | **同一行、两条 ▲ 的干净样本**:R9A 判「同页 `:670` 与 `:705` 自相矛盾」(文档内部),R9D 判「文档说 edited code、实为 write_file/patch」(文档 vs 代码) → R-5 |
| C88 | website/docs/user-guide/features/kanban.md:64,69 | ◇2(R7C)、▲-1(R9A) | **不合并** | 评论 mid-run steer 文档写旧流程 vs 熔断器只数 spawn 失败 → R-5 |
| C89 | website/docs/user-guide/features/pets.md:118,120,122,147 | ◎-1(R9B)、◎2(R10B) | **不合并** | 参考图后端清单少一个 vs Alt+wheel 缩放只记在弹出窗名下 → R-5 |
| C90 | website/docs/user-guide/features/web-dashboard.md:964,970 | ▲-3(R8C)、◇-1(R7C) | **不合并** | 登录页 provider 清单 vs 整个关停/排水子系统文档缺席 → R-5 |
| C91 | website/docs/user-guide/secrets/index.md:49,50 | ▲1(R8D)、▲-1(R9C) | **合并 B-26** | B-26 的文档侧位点(R-6) |
| C92 | website/docs/user-guide/secrets/onepassword.md:130,149,154 | ▲-3(R9C 两处同文件)、■-2(R9D) | **不成簇(BLEED-ONLY)** | ■-2 的 `:149` 锚点真属 ■-1;剩下两处是同一个 ▲-3(同文件同号,算一个案号) |

四类清点可机械重跑(判据只看「裁决」那一格,优先级 不成簇 > 合并 > 已覆盖 > 纯不合并):

```verify
cd "$(git rev-parse --show-toplevel)" && python3 data/r11c/b-dedup-82-tally.py
```

```text
逐簇裁决表行数 92
  合并: 34
  纯不合并: 48
  R11B 已覆盖: 8
  不成簇: 2
  合计 92
合并组表行数 32
  涉及案号 68;其中定案号 40
  跨轮铸号 12;同轮铸号跨轮结清 3
```

---

## 4. 关于「不裁决」与「批量说明」的交代

### 4.1 没有一簇被跳过,也没有一批被外推

**结论:92 簇全部逐簇出了裁决,没有「其余按比例推定」这一类。**
派工书允许「确有一批簇因同一个结构性理由不必逐簇读的,可以合并说明,但要点名是哪些簇、
给可重跑的判定命令」。本片**只用了一次这个额度**,而且用在**最保守的方向上**:

- **BLEED-ONLY 的 2 簇(C55、C92)**:它们不是「读了正文判为不合并」,而是
  **在探针口径下根本不该成簇** —— 唯一那个「第二案号」的锚点是从邻居条目吃来的。
  判定命令:`python3 data/r11c/b-dedup-82-index.py --bleed --clean`(只打 BLEED-ONLY 簇)。
  **即便如此,这两簇的正文本片也读了**(见 `data/r11c/b-dedup-82-context.txt` 对应段落),
  裁决栏写的是「不成簇」而不是「未裁决」。

其余 90 簇逐簇给出了「涉及案号 + 裁决 + 依据」三列,依据全部落在 R11B 的七条规则之一上。

### 4.2 R11B 的抽样预期:成立,但它是被验证的,不是被外推的

R11B §2.4 说「也有大量『同一文件邻近处的不同断言』」并举了 `hermes_cli/web_server.py:12296-12321`
那一簇(本片 C17)。**本片逐条读过两边正文后确认这条抽样判断成立** ——
`H-3` 判鉴权层由哪一层保证、`H-11` 判 dashboard 里有几套 profile 作用域、
`▲-2` 判 `:12296-12297` 那句 docstring 在具名 profile 下不成立,确实是三件事。

**但同一批 92 簇里另有 32 组是真重复。** 如果按 C17 这个样本外推,这 32 组会被一起判掉;
反过来若按 C02(一簇里三个合并组)外推,48 簇不同断言会被误并。
**两个方向的外推都会造出一个看起来合理、实际错误的数** —— 这正是不许外推的理由。

### 4.3 顺带发现的三件事(不属本片任务,记下来交出去)

1. **探针把 `■1` 从 `■11` 里切了出来。** `is_decl()` 判「本行是不是这个案号的声明位」时用的是
   **子串匹配**(`cid in cell`),于是 `notes/r9d-raw-lsp.md:1816` 那一行
   (`| ■11 | agent/lsp/manager.py:486 … |`)同时被记成 `■11` 与 `■1` 两个声明位。
   **后果方向是让案号总数偏高**,与第一物种同向,不与第二物种抵消。
2. **两处「同号不同实体」(R11B 的第二物种),本片顺带撞见,属片 A 范围**:
   R9A `◇-5`(预处理逻辑两处各写一遍)与 R7C `◇-5`(组装后 prompt 二次扫描无文档);
   R9C `■-7`(`xai_http` API-key 路径不校验 `XAI_BASE_URL`)与 R9D `■-7`
   (`x_search` 凭据解析异常穿出工具边界)。两组都锚在同一个文件的邻近处,所以进了本片的簇。
3. **C40 是一族而不是一条。** `hermes_constants.py:114` 附近被三条独立定案引用
   —— R7C `◇-4`(`sticker_cache` 模块级冻结)、R9D `■-6`(`DebugSession` 模块级冻结)、
   R7C `◇3`(`HOOKS_DIR` 模块级冻结)。三条**不是重复**(R-6 管的是一条定案的多个位点,
   这里是三条各自成立的定案),但它们是**同一个形态在三个子系统各犯一次**。
   R12 装订时应合成一节讲「模块 import 期定格 `get_hermes_home()`」这个族,而不是散在三章。

`hermes_constants.py:114 @ 863e313`

```python
def get_hermes_home() -> Path:
```

---

## 5. 收尾读数与口径差

### 5.1 裁决前后的定案号总数

**结论:去重前 ≈1,006 → R11B 后 ≤997 → 本片后 ≤975。**

| 阶段 | 定案号总数 | 该阶段的净减 | 口径 |
|---|---|---|---|
| 去重前 | ≈**1,006** | — | **语料自报口径**:17 轮报告自己声称的定案数之和(852)+ 4 轮无自报值的机械补数(154) |
| R11B 裁决后 | ≤**997** | 定案号净减 **9** | R11B 10 个合并组,32 个案号 → 10 个实体 |
| 本片裁决后 | ≤**975** | 定案号净减 **22** | 本片 32 个合并组,68 个案号 → 31 个实体 + 1 号并入 M-7 |

**与 R11B 的口径差,四条,逐条写清:**

1. **「定案号」只数 ▲◇■◎,不数移交号** —— 沿用 R11B §2.3 表头那一列的口径。
   本片 68 个案号里 **40 个是定案号**,合并后作为现行号留下的定案号是 **18** 个,故定案号净减 **22**。
   **移交号另净减 15**,这个数 R11B 没报,本片单独报出来,**不并入 1,006 那条线**
   (1,006 是定案数,移交项是另一本账)。
2. **「≈1,006」是语料自报口径,不是探针口径。** 探针口径的「案号(作用域后)总数 1,449」
   是另一个数,两者不可混用 —— 前者是各轮报告自己数的,后者含 L 家族按文件分作用域后的裸序号。
   **同一个名字的指标有两个读数时不得写成「读数相同」**,所以这里把两个口径都点名。
3. **「≤」仍然是「≤」,而且理由与 R11B 不同。** R11B 写「≤」是因为**还有 82 簇没裁**;
   本片 92 簇全裁完了,「≤」的理由换成了**判据本身的覆盖上限**:
   (a) 簇的判据是「同一锚点文件 ±30 行」,同一实体锚在**不同文件**的重复,
   只有在每个文件上各自成簇时才看得见;(b) 探针只认**基线里真实存在**的锚点,
   于是锚点指向本学习仓库 `scripts/` / `data/` 的定案一条都不进候选;
   (c) 完全不带锚点的定案(R1–R4 的无记号编号表是整批)一条都不进候选。
4. **本片的 32 组里有 3 组严格说是「计数口径的产物」而非重复登记**(B-03、B-31,以及
   B-09 那个并入项)。它们照样计进净减,**因为 1,006 这条线本身就是按 (文件, 案号) 机械数出来的**
   —— 口径要一致:既然分子按这个口径数,分母也得按这个口径减。

### 5.2 本片自校验读数

引用关卡(退出码 0):

```text
citations=35  OK=30  UNCHECKED=5
可校验比例 OK/35 = 85.7%
table_anchors=100  OK=6  UNCHECKED=94
OK: every code-block-backed citation matches the baseline
```

**必报两行(CLAUDE.md R11B 定)**:
- **块级可校验比例 = 30/35 = 85.7%**(下限 70%,当轮底稿口径)。
  5 条 UNCHECKED 全是**散文区域指路** —— 指向 `notes/r11b-raw-rulings-census.md` 的规则出处、
  以及 §4 里点名探针文件的那几句;它们不是「这段代码逐字长这样」的断言,
  造一个块去迎合关卡才是错的。
- **表格锚点声明率 = 6/100**。分子那 6 条是**移交表**的锚点 —— 按 CLAUDE.md
  「移交表的锚点必须用声明式写法」逐条配了反引号摘录,六条全部 TABLE-OK。
  分母里另外 94 条几乎全是 §3 那 92 个逐簇索引锚点,它们**有意**写成独立单元格、
  后面不跟摘录:它们回答的是「这一簇挂在哪个文件的哪几行」,不是摘录断言;
  给它们造一个摘录去迎合关卡,正是 R9B 定这条规则时点名要防的
  「猜作者指的是哪一次出现」。**这一项如实报,不粉饰。**

证据命令关卡的读数只能写成散文(`verify_evidence_commands.py` 会重跑块里的命令,
而「跑校验器扫本文件」会无限递归 —— R11B §5 已记过这个坑):本片
**`paired=4  unpaired=0  differing=0`**、`runnability ran=0 runfail=0`,退出码 0。

---

## 移交

| 移交项 | 去向 | 锚点 | 一句话现象 |
|---|---|---|---|
| **H-R11C-B-a** | R12 装订 | `hermes_constants.py:114`:`def get_hermes_home() -> Path:` | C40 那一族:`sticker_cache`(R7C ◇-4)、`DebugSession`(R9D ■-6)、`HOOKS_DIR`(R7C ◇3)三条独立定案是**同一形态在三个子系统各犯一次**,R12 应合成一节而不是散在三章 |
| **H-R11C-B-b** | 片 A / R11 复盘 | `cron/scheduler.py:2663`:`def _scan_assembled_cron_prompt(` | 第二物种漏网一例:R9A `◇-5` 与 R7C `◇-5` 同号不同实体,两者锚点都落在本文件邻近处 |
| **H-R11C-B-c** | 片 A / R11 复盘 | `tools/xai_http.py:324`:`base_url = str(get_env_value("XAI_BASE_URL") or "https://api.x.ai/v1").strip().rstrip("/")` | 第二物种漏网二例:R9C `■-7`(本行不校验)与 R9D `■-7`(`x_search` 异常穿出工具边界)同号不同实体 |
| **H-R11C-B-d** | 改探针的那一轮 | `agent/lsp/manager.py:486`:`fresh = await client.wait_for_diagnostics(file_path, version, mode=self._wait_mode)` | `rulings_census.py` 的 `is_decl()` 用子串匹配判声明位,于是 `| ■11 | … |` 这一行同时被记成 `■11` 与 `■1`;方向是让案号总数偏高 |
| **H-R11C-B-e** | R12 装订 | `hermes_cli/pairing.py:96`:`"  To reset sooner, delete the '_lockout:{0}' entry from "` | C16 的 `■-24` 与 M-4 的 `◇6` **前半重合、后半不重合**(◇6 只说硬编码新版路径,■-24 还说 GUI 无恢复提示);本片按 R-5 判不合并,但这是 32 组之外**唯一一处需要人再看一眼**的边界情形 |
| **H-R11C-B-f** | 定别名表的那一轮 | `hermes_cli/config.py:3065`:`def require_readable_config_before_write(config_path: Optional[Path] = None) -> None:` | 本片 32 组的别名表**尚未落成一份可查的索引文件**;B-01 这种「四轮两号」的实体,下一次有人拿着 `H-7` 去查,仍然走不到 `H-R8FIX-a` 的卷宗 |

---

## 6. 产出与一条自查记录

本片产出:

| 文件 | 是什么 |
|---|---|
| `notes/r11c-raw-dedup-82.md` | 本底稿 |
| `data/r11c/b-dedup-82-index.py` | 92 簇结构化索引 + 锚点归属(BLED)判定;`--bleed` / `--clean` / `--summary` |
| `data/r11c/b-dedup-82-index.tsv` | 索引表(簇号 / 锚点文件 / 行号集 / 案号数 / 轮次数 / 状态 / 案号清单) |
| `data/r11c/b-dedup-82-bleed.txt` | 逐条锚点归属明细,含每条 BLED 锚点真正属于哪个案号 |
| `data/r11c/b-dedup-82-context.py` | 为 92 簇的每个声明位导出正文上下文(裁决用的一手材料) |
| `data/r11c/b-dedup-82-context.txt` | 292 个唯一声明位 × 上下文,3,696 行 |
| `data/r11c/b-dedup-82-coverage.py` | 「92 − 10 = 82」的口径核对(R11B 的 M 组覆盖到哪些簇) |
| `data/r11c/b-dedup-82-coverage.txt` | 上者的输出 |
| `data/r11c/b-dedup-82-clusters-raw.txt` | R11B 探针 `--clusters` 的原始输出(92 簇) |
| `data/r11c/b-dedup-82-tally.py` | 从 §3 表机械清点四类裁决,防止正文的数与表脱节 |

**一条自查记录(硬约束 6 的实拦)**:上下文导出脚本第一版把语料原样转录,
于是历史底稿里那几处**会话专属 scratchpad 路径**(正是 R11B 记的 `H-R9D-f`)被又抄进了仓库,
**实测 3 处**。修法不是事后 `sed`(重跑会再抄一遍),而是在**写盘之前**抹除:
`data/r11c/b-dedup-82-context.py` 的 `scrub()`,输出里现在是 `<会话路径已抹除>`。
*脚本自身留有 `/tmp/claude-\d+/` 这条正则 —— 它是检出器,不是泄漏的路径,不带任何具体会话标识。*

## 完成信号

**片 B 完成。** 任务是「逐簇裁决 R11B 未裁决的 82 簇,或给出不裁决的理由」,已完成:
**92 簇全部逐簇出裁决**(34 簇含合并、48 簇纯不合并、8 簇 R11B 已覆盖、2 簇不成簇),
**未按比例外推、未抽样后推广**;裁出 **32 个合并组**、涉及 **68 个案号**,
**定案号净减 22**(移交号另净减 15),去重后总数 **≤975**,与 R11B 口径差见 §5.1。

产出文件 10 个,清单见 §6:`notes/r11c-raw-dedup-82.md` +
`data/r11c/b-dedup-82-{index,context,coverage,tally}.py` +
`data/r11c/b-dedup-82-{index.tsv,bleed.txt,context.txt,coverage.txt,clusters-raw.txt}`。

两条关卡自跑均退出码 0:
`verify_citations.py` → `citations=35 OK=30 UNCHECKED=5`、可校验比例 **85.7%**、
`table_anchors=100 OK=6`、**0 MISMATCH / 0 BLOCK-DRIFT / 0 TABLE-DRIFT / 0 TABLE-OUT-OF-RANGE**;
`verify_evidence_commands.py` → `paired=4 unpaired=0 differing=0`、`runnability ran=0 runfail=0`。

基线 `git -C /home/user/hermes-agent status --porcelain` 为空;本片未改任何历史 `notes/`、
未改 `chapters/`、未改 `scripts/`、未动 venv、未 commit / push;`data/inflight/r11c-b-dedup-82.claim`
**保持 `signal: OPEN`,由主线关闭**(批次二纪律 15)。
