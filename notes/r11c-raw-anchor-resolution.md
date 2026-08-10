# R11C 片 D 底稿 · 锚点解析面的真实缺口

> 本片任务(见 `data/r11c/dispatch-brief.md` 「片 D」):
> 1. 报出**两个读数**并说明差异构成 —— 读数甲 = 关卡当前口径(`scripts/verify_citations.py`
>    实际报的 citations / OK / UNCHECKED),读数乙 = **从仓库根实际可解析**的数;
>    差异逐项拆开(裸文件名 / 同名歧义 / 扩展名不在白名单 / 真写错),每类给可重跑计数命令。
> 2. 能修的就修:裸文件名补全路径,**修前先确认全路径对**,消解不了的点名留下。
>
> 溯源约定:凡对 hermes-agent 的断言紧跟 `路径:行号 @ 863e313` + 代码原文块。
> 本片自身的读数(对**本学习仓库语料**的统计)按 CLAUDE.md「自校验读数不能写进 ```verify 块」
> 的同源理由处理:**扫描语料的命令可以写进 ```verify**(它不递归),
> 但凡命令的输出会随本底稿自身增长而变的,一律在正文里说明口径并按前缀剔除 `r11c-*` 报两个读数。
>
> **边界**:`chapters/` 一个字不改(本轮第八项只报不改);`data/r11c/slice-c-files.txt`
> 里那 31 个文件归片 C,本片不碰。

## 0. 结论(先写结论)

1. **关卡报的数不是「锚点数」,而是「判决数」;两者差 7,278。** 关卡对同一行上的多个锚点只出
   **一条**判决,对围栏块 / 引用块**内部**的锚点整段跳过。全语料 277 份 `.md`:
   关卡判决 **18,253**(+ 表格 3,760),而关卡那套正则在同一份语料上原理上能看见
   **25,531** 个锚点。**这 7,278 的差不是缺陷,是关卡的设计**(块内锚点不是断言),
   但它意味着「UNCHECKED=6,242」这个数**不能**被读成「6,242 个锚点没查」。
2. **真正的病灶是「解析不到」,共 3,080 处(占 12.1%),而关卡只报得出其中 3 处。**
   关卡只在锚点**紧跟围栏块**时才判 `MISSING-FILE`;写在散文里、表格里的裸文件名一律
   UNCHECKED / TABLE-UNCHECKED,**不是失败**。全语料 3,080 处解析不到里,
   关卡报出来的是 3 处 `MISSING-FILE`(还全是同一个第三方包 `mcp/client/auth/oauth2.py`)。
3. **3,080 处里 2,099 处(68.1%)是可机械补全的**:基线里**恰好一个**文件的路径以它结尾。
   最大的一块是 `run.py` **386 处 → `gateway/run.py`**(基线只有这一个 `run.py`)。
4. **934 处(30.3%)是真歧义,不许瞎猜**:`__init__.py` 156 处 / 基线 **171 个**候选,
   `base.py` 114 处 / **9 个**候选。另有一个 R11B 没点出的**系统性歧义**:
   `website/docs/**/*.md` 每一份在 `website/i18n/zh-Hans/…` 下都有镜像,
   于是**任何裸文档名恒有 ≥2 个候选**(`gateway-internals.md` 25 处、`cron-internals.md` 24 处)。
5. **扩展名白名单又漏了两个:`ps1` 与 `css`。** 全语料 **16 处**锚点**能从仓库根解析、
   却不被关卡当成锚点**(14 处 `scripts/install.ps1`、1 处 `apps/desktop/src/styles.css`、
   1 处自引 `data/ledger.tsv`)。这正是 CLAUDE.md 说的「连分母都进不去」那一档 —— 比 UNCHECKED 更隐蔽。
   新立 **H-R11C-D-a**。
6. **真写错的只有一小把(35 处 NOT-IN-TREE),但每一处都是「读者会去读错文件」的形态**,
   其中已确证并已修的有:`agent/run_agent.py:3710`(基线里是根上的 `run_agent.py`,多写了 `agent/`)、
   `env-variables.md:802`(基线里这份文档叫 `website/docs/reference/environment-variables.md`)、
   `compression-caching.md:396`(基线里叫 `website/docs/developer-guide/context-compression-and-caching.md`)。
7. **还有一类关卡永远看不见的错:锚点解析得到、但行号在文件尾之后。** 全语料 **4 处**,
   其中 `README.md:334-339`(根 README 只有 264 行)与 `setup.py:3535`(根 `setup.py` 只有 74 行)
   是**裸名碰巧解析到了根上另一个真文件** —— 这是 R11B 在 H-R11B-D-d 里点名担心的形态,
   本片给出了它的第二、第三个实例。
8. **本片最重的发现,不在任务书上:「解析成功」本身可以是假保证。** 全语料 **1,603 处**
   裸锚点解析到的是**仓库根上的同名文件**,而根上那 11 个名字在树的别处都还有同名
   (`cli.py` 1,344 处 / 根 18,555 行 / 别处 7 个)。**已确证并改正 60 处指错了文件**
   —— 例如 `notes/r6-30-…md:423` 讲 supermemory 的 `capture_mode`,锚点 `README.md:55`
   解析到的是**仓库根 README** 讲 MinGit 下载的那一行。**这一类任何现有关卡都发现不了**:
   路径存在、行号在范围内、校验器沉默,读者照着读完全不相干的一行还以为那就是证据。
   新立 **H-R11C-D-c**,§3.4。
9. **任务二总计改动 114 份 `notes/`、1,930 处锚点路径**:1,781 唯一候选 + 75 长度判据
   + 60 根遮蔽 + 14 逐条确证。不可解析从 **3,080(12.1%)降到 1,212(4.7%)**;
   R11B 那 41 份的口径从 **1,334(40.3%)降到 411(12.4%)**。
   **859 处真歧义一处没猜**,全部点名留下。

---

## 1. 三个读数与它们的口径

结论:**甲(关卡判决)18,253、甲′(关卡正则命中)25,531、乙(宽正则命中)25,558**;
甲→甲′ 的差是关卡**故意**不看的,甲′→乙 的差是关卡**看不见**的。

### 1.1 读数甲 —— 关卡当前口径

语料 = `chapters/*.md` + `notes/*.md` + `reports/*.md` + `reviews/*.md`,**剔除本轮 `r11c-*`**
(名单冻结在 `data/r11c/d-anchor-resolution-corpus.txt`,277 份)。跑关卡的输出冻结在
`data/r11c/d-anchor-resolution-gate-before.txt`,**本节所有数都从这份冻结件里取**
——因为本片任务二会去改语料,现跑的关卡此后必然给出不同的数。

```verify
cd /home/user/hermes-study && tail -5 data/r11c/d-anchor-resolution-gate-before.txt | head -4
```

```text
citations=18253  MISMATCH=3  MISSING-FILE=3  OK=12005  UNCHECKED=6242
可校验比例 OK/18253 = 65.8%  << 低于 70% 下限
BLOCK-DRIFT=1  (代码块首行之后的行与基线不符;**阻断**,见脚本 block_drift() 的说明)
table_anchors=3760  OK=1519  UNCHECKED=2241   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)
```

**那 7 条失败与本片无关,也不在本片可改范围内**:3 条 `MISSING-FILE` 全是
`notes/r6-60-mcp-oauth-cleanup.md` 指向 pip 包 `mcp/client/auth/oauth2.py`(已是 H-R11B-D-a);
其余 4 条(1 BLOCK-DRIFT + 3 MISMATCH)全在 `reviews/review-1-full-corpus.md`,
而 CLAUDE.md 规定 `reviews/` **原文不改**。**本轮强制范围(`chapters/` 全部 + 本轮 notes/reports)
不含这两处**,见 §5 自查。

### 1.2 读数甲′ 与读数乙 —— 关卡正则命中 vs 宽正则命中

探针 `data/r11c/d-anchor-resolution-scan.py`。宽正则与关卡的 `CITE` 只差一处:
扩展名不限白名单,改为「1-6 位字母数字」。**下面这条命令跑的是活语料,所以它的读数会随
任务二的修改而变**;本节引用的是**修改前**的那一次运行,冻结在
`data/r11c/d-anchor-resolution-census.tsv`(明细)与 `-summary.txt`(汇总)。

```verify
cd /home/user/hermes-study && head -4 data/r11c/d-anchor-resolution-summary.txt
```

```text
语料:277 份 .md(chapters/notes/reports/reviews),剔除本轮 r11c-*
甲′ 关卡正则命中 = 25531
乙  宽正则命中   = 25558   (差 27 个 = 关卡看不见的)
乙 中不可解析 = 3080 / 25558 = 12.1%
```

**甲 18,253 → 甲′ 25,531,差 7,278。** 这个差**不是缺口**,是关卡三条设计决定的和:

| 差的来源 | 关卡的做法 | 是不是缺陷 |
|---|---|---|
| 一行多个锚点 | `scripts/verify_citations.py:693`:`m = cands[-1]  # default: the last citation is usually the one the block follows` —— 一行只出一条判决 | 不是。多余的锚点没有块可配,判决它们只会造出噪音 |
| 围栏块**内部**的锚点 | `scripts/verify_citations.py:666`:`if FENCE.match(line):` —— 整段跳过 | 不是。块里的 `路径:行号` 是摘录自己的文字,不是本文在断言 |
| 引用块**内部**的锚点 | `scripts/verify_citations.py:676`:`if QUOTE.match(line):` —— 整段跳过 | 不是。同上,那是被引文档在引代码 |

**甲′ 25,531 → 乙 25,558,差 27。** 这 27 个才是缺口:它们长得就是锚点、也确实是锚点,
但**关卡的正则认不出它们**,于是既不校验也不计数。逐个见 §2.3。

### 1.3 与 R11B 那个 40.3% 的口径差

R11B 报的是 **41 个文件里 1,334 / 3,314(40.3%)**;本片报的是 **277 个文件里 3,080 / 25,558(12.1%)**。
**这不是同一个测量,两个数都写在这里。** 差别**只在语料面**,判据完全一样(都用
`vc.citations()` 的解析结果问「这个路径是不是一个真文件」)。把 R11B 那 41 份的名单原样跑一遍,
数字**逐位复现**:

```verify
cd /home/user/hermes-study && python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
import verify_citations as vc
REPO = Path("/home/user/hermes-agent"); STUDY = Path("/home/user/hermes-study")
def resolve(p):
    t = REPO / p
    return t if t.is_file() or not (STUDY / p).is_file() else STUDY / p
files = sorted({"notes/" + l.split()[1].split(":")[0]
                for l in open("data/r11b/notes-citation-backlog.txt")})
tot = bad = 0
for f in files:
    for line in Path(f).read_text(encoding="utf-8").splitlines():
        for m in vc.citations(line, resolve):
            tot += 1
            bad += 0 if resolve(m.group("path")).is_file() else 1
print(f"R11B 口径复跑({len(files)} 份):anchors={tot} unresolvable={bad} ({bad*100.0/tot:.1f}%)")
PY
```

> 上面这条命令**在任务二改完之后会给出不同的数** —— 那 41 份正是本片要修的主战场。
> 它写在这里是为了记录**修改前**与 R11B 的一致性;修改后的读数在 §4.3。
> (本节这一条 ```verify 块因此**不配 ```text 块** —— 一个注定要变的读数不该被钉成契约。
> 关卡对未配对块只做可跑性检查,这条命令跑得通、退出码 0。)

**为什么百分比从 40.3% 掉到 12.1%,而绝对数从 1,334 涨到 3,080**:R11B 那 41 份是
**按「引用清理积压」挑出来的**,本来就是裸名最密集的一批;把语料铺到全部 277 份之后,
分母里多了大量本来就写全路径的文件。**比例变小不等于病灶变小** —— 绝对数是 2.3 倍。
这正是 CLAUDE.md「同一指标多次/多方法测量必须分别标注」要防的读法。

---

## 2. 差异构成:逐项拆开 + 每类的可重跑计数命令

结论:3,080 处解析不到 = **2,099 可机械补全 + 934 真歧义 + 35 不在树里 + 12 绝对路径被切**;
另有**与解析无关的第二条缝** —— 27 处关卡看不见的锚点、4 处解析得到但行号越界。

### 2.0 一条命令看全貌

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{c[$5]++} END{for(k in c) printf "%-30s %d\n", k, c[k]}' data/r11c/d-anchor-resolution-census.tsv | sort -k2 -rn
```

```text
UNIQUE-SUFFIX                  2099
AMBIGUOUS                      934
NOT-IN-TREE                    35
RESOLVED-BASELINE              15
ABSPATH                        12
RESOLVED-BASELINE-OUT-OF-RANGE 4
RESOLVED-STUDY                 1
```

(`RESOLVED-*` 那三行是**能解析**的,只因为它们「关卡看不见」或「行号越界」才进明细;
它们不计入 3,080。3,080 = 2099 + 934 + 35 + 12。)

### 2.1 裸文件名 / 半截路径,基线里唯一候选 —— 2,099 处

**这是可机械补全的那一类**:基线里**恰好一个**文件的路径以这个串结尾(按目录边界匹配,
所以「裸文件名」与「写了一半的路径」走同一条判据)。共 **297 个不同的串**。

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1 && $5=="UNIQUE-SUFFIX"{print $3" -> "$7}' data/r11c/d-anchor-resolution-census.tsv | LC_ALL=C sort | uniq -c | LC_ALL=C sort -k1,1nr -k2,2 | head -8
```

```text
    386 run.py -> gateway/run.py
     87 web_server.py -> hermes_cli/web_server.py
     73 slash_commands.py -> gateway/slash_commands.py
     70 config_defaults.py -> hermes_cli/config_defaults.py
     57 approval.py -> tools/approval.py
     56 conversation_loop.py -> agent/conversation_loop.py
     45 url_safety.py -> tools/url_safety.py
     37 config_migrations.py -> hermes_cli/config_migrations.py
```

**一条独立的旁证说明这批补全是对的:2,099 处里,被补全后行号越界的是 0 处。**
如果「唯一候选」经常猜错文件,行号越界应当随机出现;它一次都没出现。

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1 && $5=="UNIQUE-SUFFIX" && $7 ~ /越界/' data/r11c/d-anchor-resolution-census.tsv | wc -l
```

```text
0
```

### 2.2 同名歧义 —— 934 处,一处都不许猜

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1 && $5=="AMBIGUOUS"{print $3"  ("$7")"}' data/r11c/d-anchor-resolution-census.tsv | LC_ALL=C sort | uniq -c | LC_ALL=C sort -k1,1nr -k2,2 | head -10
```

```text
    156 __init__.py  (171 个候选)
    114 base.py  (9 个候选)
     40 config.py  (4 个候选)
     40 pairing.py  (3 个候选)
     38 session.py  (3 个候选)
     28 client.py  (4 个候选)
     25 gateway-internals.md  (2 个候选)
     24 auth.py  (5 个候选)
     24 cron-internals.md  (2 个候选)
     21 status.py  (3 个候选)
```

**R11B 没点出的那一条:所有 `website/docs/**` 文档名都恒有 2 个候选。** 因为每一份英文文档
在 `website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/` 下都有一份同名镜像。
于是**任何裸文档名在机械判据下永远是歧义**,哪怕作者心里想的一定是英文那份
——而文档侧正是每一条 ▲ 定案的一半(CLAUDE.md:「▲ = 文档所述与代码矛盾」,
地图指 `website/docs`)。这一类共 **264 处 / 50 个不同文档名**,单列为 **H-R11C-D-b**,处置见 §3.3。

```verify
cd /home/user/hermes-study && python3 - <<'EOF'
import csv, subprocess
from collections import defaultdict
paths = subprocess.run(["git", "ls-files"], cwd="/home/user/hermes-agent",
                       capture_output=True, text=True).stdout.split()
idx = defaultdict(set)
for p in paths:
    parts = p.split("/")
    for k in range(len(parts)):
        idx["/".join(parts[k:])].add(p)
n, names = 0, set()
for r in csv.DictReader(open("data/r11c/d-anchor-resolution-census.tsv", encoding="utf-8"),
                        delimiter="\t"):
    if r["class"] != "AMBIGUOUS":
        continue
    c = idx.get(r["path"], set())
    if c and all(x.startswith("website/") for x in c):
        n += 1
        names.add(r["path"])
print(f"website/ 镜像型歧义 = {n} 处 / {len(names)} 个不同文档名")
EOF
```

```text
website/ 镜像型歧义 = 264 处 / 50 个不同文档名
```

### 2.3 扩展名不在白名单 —— 27 处「连分母都进不去」

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1 && $6=="GATE-BLIND"{n=split($3,p,"."); printf "%-8s %s\n", p[n], $5}' data/r11c/d-anchor-resolution-census.tsv | LC_ALL=C sort | uniq -c | LC_ALL=C sort -k1,1nr -k2,2
```

```text
     14 ps1      RESOLVED-BASELINE
      3 lineno   NOT-IN-TREE
      3 sh       UNIQUE-SUFFIX
      2 rs       NOT-IN-TREE
      1 2        NOT-IN-TREE
      1 5        NOT-IN-TREE
      1 css      RESOLVED-BASELINE
      1 tsv      RESOLVED-STUDY
      1 x        ABSPATH
```

三档,性质完全不同:

| 档 | 数 | 是什么 | 判定 |
|---|---|---|---|
| **真缺口** | 16 | 14 处 `scripts/install.ps1`(Windows 安装器,基线真文件 4,262 行)、1 处 `apps/desktop/src/styles.css`、1 处自引 `data/ledger.tsv` | **白名单该补 `ps1` / `css` / `tsv`** → H-R11C-D-a |
| **被 ccTLD 守卫挡下的真锚点** | 3 | `build.sh:4-6` ×2、`node-bootstrap.sh:50`;三个都是**裸文件名**,既无 `/` 又无 `_`,又不在仓库根,于是 `is_path_citation` 判它更像 Saint-Helena 域名 | **守卫没错,错在锚点是裸名**;补成全路径后自动可见,已在任务二修掉(§3.1) |
| **守卫正确挡下的非锚点** | 8 | `n.lineno:4` ×3、`example.rs:443` ×2、`192.168.x.x:9119`、`4.5:1`、`1.2:87` —— 属性访问、散文举例、IP、版本号 | **不动**。这 8 个正是 CLAUDE.md 说白名单「是有效的分界,不是懒惰」的那一类 |

`scripts/verify_citations.py:201 @ 863e313`(本仓库脚本,非基线)

```
TLD_LIKE_EXTS = {"sh", "js", "rs"}
```

### 2.4 真写错了 —— 35 处 NOT-IN-TREE,逐条见 §3.3

### 2.5 绝对路径被正则切了一刀 —— 12 处

关卡的 `CITE` 没有左侧 lookbehind,于是 `/home/user/hermes-venv/.../applications.py:4723`
会被解析成 `home/user/hermes-venv/.../applications.py` —— **在统计里长得跟一个写错的相对路径一模一样**。
12 处里 10 处指向 venv 里的第三方包或 `/usr/include/sqlite3.h`(作者**有意**引非基线文件),
1 处是散文举例(`/Users/ironin/file.md:45`),1 处是 IP 段(`192.168.x.x:9119`)。
**都不是错**,单列出来是为了不让它们混进「真写错」那一格。

### 2.6 关卡永远看不见的第二类错:解析得到,但行号在文件尾之后 —— 4 处

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1 && $5 ~ /OUT-OF-RANGE/{print $1":"$2"  "$3":"$4"  "$7}' data/r11c/d-anchor-resolution-census.tsv
```

```text
notes/r6-90-doc-conflict-rulings.md:26  README.md:334  行号越界(文件 264 行)
notes/r8a-raw-defaults-b.md:1563  setup.py:3535  行号越界(文件 74 行)
notes/r8a-raw-defaults-b.md:1568  setup.py:3558  行号越界(文件 74 行)
reports/round-9b-multimodal-delivery.md:93  hermes_cli/env_loader.py:999999  行号越界(文件 752 行)
```

前三处是 **R11B 在 H-R11B-D-d 里担心的那个形态的第二、第三个实例**:裸名**碰巧解析到了
仓库根上另一个真文件**,于是「解析成功」这件事本身变成了假保证。第四处是
`reports/round-9b` 里**故意**造的越界锚点(用来自测 TABLE-OUT-OF-RANGE),不动。
前三处已在 §3.3 修掉。

---

## 3. 任务二:能修的就修

结论:**改了 1,930 处锚点路径**,涉及 **114 份 `notes/`**,分四批,判据从强到弱各自声明:

| 批 | 判据 | 处数 | 节 |
|---|---|---|---|
| 一 | 基线里**恰好一个**文件以它结尾(结构) | 1,781 | §3.1 |
| 二 | 逐条人工取证(机械判据够不到的) | 14 | §3.3 |
| 三 | 小节标题定归属 + 内容判据(根同名遮蔽) | 60 | §3.4 |
| 四 | 候选**必须长到有这一行** + 内容判据 | 75 | §3.5 |

另有 **2 处**表格锚点改写成声明式排版(§3.2,改的是排版不是路径)。
**一处都没猜**:859 处真歧义、622 处判据不过的,全部原样留下并逐条点名(§5.3)。
关卡在改完之后回到与改之前**一模一样的 7 条历史失败**,没有新增。

### 3.1 机械补全:1,781 处,判据只有一条

判据:基线 863e313 里**恰好一个**文件的路径以这个串结尾(按目录边界匹配)。
脚本 `data/r11c/d-anchor-resolution-fix.py`,干跑/落盘两态。

**两处绝不改写,因为改了就是在伪造证据**:围栏块内部(````` ``` `````,契约是逐字源码摘录;
基线源码本身就有带 `foo.py:123` 字样的行,改写它等于让摘录与基线不符)与引用块内部
(`>`,可能是逐字文档摘录)。这两处**正是关卡自己跳过的两处**(§1.2 那张表),
所以「脚本改的范围」= 「关卡会读的范围」。**因此故意跳过 105 处。**

范围只到 `notes/`:`chapters/` 本轮只报不改;`reports/` 按 CLAUDE.md 正文不静默改写;
`reviews/` 原文不改;`data/r11c/slice-c-files.txt` 里 31 个文件归片 C(实测跳过 136 处)。

```verify
cd /home/user/hermes-study && tail -19 data/r11c/d-anchor-resolution-fix-log.txt
```

```text
已改写 1781 处,涉及 109 份 notes/
因位于围栏块 / 引用块内部而**故意跳过** 105 处(改了就是伪造摘录)

改写最多的 15 个串:
   370  run.py -> gateway/run.py
    73  slash_commands.py -> gateway/slash_commands.py
    66  config_defaults.py -> hermes_cli/config_defaults.py
    52  approval.py -> tools/approval.py
    37  conversation_loop.py -> agent/conversation_loop.py
    37  tools_config.py -> hermes_cli/tools_config.py
    36  config_migrations.py -> hermes_cli/config_migrations.py
    30  url_safety.py -> tools/url_safety.py
    29  prompt_builder.py -> agent/prompt_builder.py
    29  authz_mixin.py -> gateway/authz_mixin.py
    25  cua_backend.py -> tools/computer_use/cua_backend.py
    25  tool.py -> tools/computer_use/tool.py
    25  local.py -> tools/environments/local.py
    25  env_loader.py -> hermes_cli/env_loader.py
    24  system_prompt.py -> agent/system_prompt.py
```

最大的一块是 `run.py` → `gateway/run.py`。基线里 `run.py` **只有这一个**:

```verify
cd /home/user/hermes-agent && git ls-files | grep -E '(^|/)run\.py$'
```

```text
gateway/run.py
```

#### 3.1.1 改写前的独立内容校核(不是「唯一候选」这条结构判据的同义反复)

「唯一候选」是**结构**判据,它有一种整类错法:作者当年心里想的文件基线里根本不存在,
而恰好只有一个同名文件,判据照样给出唯一候选。所以在动手前先拿一条**内容**判据对一遍
——`data/r11c/d-anchor-resolution-validate.py`:取锚点所在行里锚点**之外**的反引号片段当探针,
问它出不出现在候选文件里。

```verify
cd /home/user/hermes-study && python3 data/r11c/d-anchor-resolution-validate.py --band 100000 2>&1 | head -3
```

**两个读数分别标注,不是同一个测量**:`band=±12`(既查文件也查行号)命中 **913/1286 = 71.0%**;
`band=整份文件`(只查文件对不对)命中 **1118/1286 = 86.9%**。另有 **495 处(27.8%)行内
没有任何可用探针**,给不出判据 —— 这个数必须跟命中率一起报,否则命中率是被挑选过的。

上面两条命令的输出会随本片改写而变(改完之后这批锚点已经能解析,`collect()` 就不再收它们),
所以它们**不配 ```text 块**;改写前那一次运行的读数抄录在此,并声明**不可重跑**:

```text
待补全总数 = 1781
有内容探针的 = 1286   无探针(NO-PROBE) = 495  (27.8%)
band=+/-12 命中 = 913   未命中 = 373   命中率 = 71.0%
band=+/-100000 命中 = 1118   未命中 = 168   命中率 = 86.9%
```

**未命中的 168 处逐条看过样例,没有一条是「补错了文件」**,全是探针本身不合用:
笔记用点号写配置键(`auxiliary.curator.timeout`),而代码里是嵌套字典;
或者探针是公式、是 HTTP 路由描述、是省略了参数的签名。抽三条钉死:

`hermes_cli/providers.py:652 @ 863e313`

```
def nous_api_mode(model: str = "") -> str:
```

`plugins/memory/holographic/retrieval.py:28 @ 863e313`

```
        temporal_decay_half_life: int = 0,  # days, 0 = disabled
```

`hermes_cli/config_defaults.py:1010 @ 863e313`

```
            "timeout": 600,
```

三处的**文件与行号都对**,探针没命中只因为笔记里写的是 `nous_api_mode()`(带括号)、
`0.5^(age_days/half_life)`(公式)、`auxiliary.curator.timeout`(点号路径)。

### 3.2 补全把两条以前看不见的错顶了出来(H-R11B-D-f 的第二个实例)

R11B 记过一条「失败是分层的,修好上层会长出下层」。本片当场又中一次:补全之后,
关卡第一次报出 **2 处 `TABLE-DRIFT`**,而它们在补全前**一次都没被报过** ——
因为路径解析不到,`check_table_row` 在 `if not target.is_file(): continue` 那一步就跳过了。

两处都在 `notes/r7-raw-run-08-stop-profiles-busycmd.md`,而且**锚点本身是对的**:
表格格子写成「`符号`(路径:行号)」,即**摘录在锚点之前**,而关卡的配对规则是
「锚点 → **紧跟其后**的反引号片段」,于是它拿到的是格子里**下一个**符号名。
按 CLAUDE.md 规定的声明式写法改成「`路径:行号`:`符号`」后两处都判 TABLE-OK:

- `gateway/run.py:1938`:`def _profile_runtime_scope(profile_home: "Path"):`
- `gateway/run.py:22043`:`async def _classify_completion_target(self, parent_session_id: str) -> str:`

**净效果**:表格锚点 `OK` 从 1,519 升到 **1,529**(+10),`UNCHECKED` 从 2,241 降到 **2,231**(−10)
—— 10 个此前从未被比对过的表格锚点变成了真的被比对过,其中 8 个一次就对,2 个是上面这种排版。

### 3.3 逐条确证的写错:14 条

结论:机械判据够不到的这 14 条,每一条都单独取证过,脚本
`data/r11c/d-anchor-resolution-manual-fixes.py` 只负责精确替换 + 出现次数断言。

| # | 文件 | 原锚点 | 改成 | 凭什么 |
|---|---|---|---|---|
| 1-2 | `notes/r7c-90-doc-conflict-rulings.md`(2 处) | `agent/run_agent.py:3710` | `run_agent.py:3710` | 基线里 `run_agent.py` 在**仓库根**,`agent/` 下没有它;`run_agent.py:3710`:`inject_new_comments_from_env(self)` 正是笔记讲的「kanban 评论 steer 调用点」 |
| 3-4 | `notes/r2-03-streaming.md`、`notes/r2-23-classify-retry-fallback-cache.md` | `env-variables.md:802-803` | `website/docs/reference/environment-variables.md:802-803` | 基线无 `env-variables.md`;`:802` 与 `:803` 恰是笔记断言「与文档一致」的那两个默认值(读超时 120 / stale 180) |
| 5 | `notes/r2-90-doc-conflict-rulings.md` | `compression-caching.md:396` | `website/docs/developer-guide/context-compression-and-caching.md:396`:`### Strategy: system_and_3` | 基线里这份文档叫全名;`:396` 就是笔记引的那个小节标题 |
| 6 | `notes/r8a-90-doc-conflict-rulings.md` | `raw-config-b.md:1227` | `notes/r8a-raw-config-b.md:1227` | 本仓库自引,同一句里其余锚点都写了 `notes/r8a-` 前缀,只这处漏了 |
| 7 | `notes/r6-90-doc-conflict-rulings.md` | `README.md:334-339` | `plugins/memory/honcho/README.md:334-339` | 根 README 只有 264 行(**行号越界**露的馅);honcho README `:334` = `### Hardcoded Limits`、`:339` = `\| Peer card fetch tokens \| 200 \|`,正是笔记引的那句 |
| 8-9 | `notes/r8a-raw-defaults-b.md` | `setup.py:3535`、`setup.py:3558` | `hermes_cli/setup.py:3535`、`:3558` | 根 `setup.py` 只有 74 行(**行号越界**);`hermes_cli/setup.py:3535`:`value = prompt(f"  {var.get('prompt', var['name'])}")` 与表格那行讲的 `prompt` key 一致 |
| 10-14 | 5 份底稿 | 作者用 `...` 省略了中段路径 | 补回全路径 | 见下 |

省略中段的 5 条(`...` 是作者有意的缩写,不是笔误,但它同样让锚点解析不到):

| 原锚点 | 补成 | 目标那一行 |
|---|---|---|
| `website/i18n/zh-Hans/.../gateway-internals.md:86` | `website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/developer-guide/gateway-internals.md:86` | 含 `_pending_messages`,与笔记引文一致 |
| `website/i18n/.../webhooks.md:452-460`、`website/i18n/zh-Hans/.../messaging/webhooks.md:452-460` | `website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/user-guide/messaging/webhooks.md:452-460` | `:452` = `### HMAC 签名验证` |
| `tests/gateway/test_48031_...py:77-87` | `tests/gateway/test_48031_model_switch_after_auto_reset.py:77-87` | 基线里 `48031` 只有这一个测试文件 |
| `website/i18n/zh-Hans/.../configuration.md:1255` | `website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/user-guide/configuration.md:1255` | 语言取值表那一行 |
| `website/docs/.../lsp.md:284` | `website/docs/user-guide/features/lsp.md:284` | `:284` 含 `[agent.lsp.client]`,与笔记断言逐字一致 |

`run_agent.py:3710 @ 863e313`

```
                inject_new_comments_from_env(self)
```

`plugins/memory/honcho/README.md:339 @ 863e313`

```
| Peer card fetch tokens | 200 |
```

`hermes_cli/setup.py:3535 @ 863e313`

```
                value = prompt(f"  {var.get('prompt', var['name'])}")
```

**没改的 3 类**(点名留下,见 §5 移交):

- **第三方包锚点 11 处**(`mcp/client/auth/oauth2.py` 等):笔记已用 ` @ mcp==1.28.1 site-packages`
  声明了非基线出处,不是错;要治的是校验器缺一档 `NON-BASELINE`(已是 H-R11B-D-a)。
- **绝对路径 12 处**:见 §2.5,作者有意引 venv / `/usr/include` 里的文件。
- **`notes/r9a-h-r8d-ef-surveys.md` 里 3 处省略路径**:它们在一个 ```` ```text ```` 围栏里,
  是作者手工列宽对齐的调查表。**围栏内一律不改**是本片的硬规矩(§3.1),
  即便这个围栏是声明式非源码 —— 例外一旦开口,下一次就要靠判断力而不是规矩。

### 3.4 本片最重的一个发现:「解析成功」本身可以是假保证

**结论:1,603 处裸锚点解析到的是仓库根上的同名文件,而其中至少 60 处作者说的是别处那一个
——已改正 60 处,点名留下 19 处。这一类任何现有关卡都发现不了。**

R11B 在 H-R11B-D-d 里担心过一次(`notes/r6-10-honcho.md:677` 的
`plugins/memory/honcho/cli.py:1113`)。本片把它量化了。判据:锚点路径里没有 `/`
∧ 它在基线**仓库根**是真文件(于是解析成功、关卡满意)∧ 同名文件在树的别处**还有 ≥1 个**。

```verify
cd /home/user/hermes-study && python3 data/r11c/d-anchor-resolution-rootshadow.py 2>&1 | head -3
```

改写前的读数(此后会随本片改写而变,故声明**不可重跑**):

```text
基线仓库根文件 59 个,其中 11 个在树的别处还有同名:
  .gitignore  .npmrc  AGENTS.md  LICENSE  README.md  cli.py  docker-compose.yml  package-lock.json  package.json  setup.py  utils.py

语料里用了这些名字的裸锚点 = 1603 处(剔除本轮 r11c-*)
  1344  cli.py  (根 18555 行;别处还有 7 个:agent/lsp/cli.py, hermes_cli/proxy/cli.py, plugins/google_meet/cli.py …)
   142  AGENTS.md  (根 1435 行;别处还有 1 个:apps/desktop/AGENTS.md)
    90  README.md  (根 264 行;别处还有 46 个:apps/desktop/README.md, apps/desktop/scripts/perf/README.md, apps/desktop/src/debug/README.md …)
    22  utils.py  (根 666 行;别处还有 1 个:gateway/platforms/qqbot/utils.py)
     3  docker-compose.yml  (根 76 行;别处还有 1 个:tests/e2e/matrix_xsign_bootstrap/docker-compose.yml)
     1  package.json  (根 69 行;别处还有 10 个:apps/bootstrap-installer/package.json, apps/desktop/package.json, apps/shared/package.json …)
     1  setup.py  (根 74 行;别处还有 3 个:hermes_cli/setup.py, hermes_cli/subcommands/setup.py, skills/productivity/google-workspace/scripts/setup.py)
```

**为什么这一类比裸文件名更危险**:一个解析不到的锚点至少**看得出**有问题(校验器可能报
MISSING-FILE,读者点开也找不到);一个解析到**错文件**的锚点,路径存在、行号在范围内、
校验器沉默,读者会照着读**完全不相干的一行**并以为那就是证据。R11B 的行号越界只是它
**偶尔**露的马脚 —— 全语料只露了 3 处(§2.6),而实际错的至少 60 处。

**怎么定的错**:两条判据同时成立才改(脚本 `data/r11c/d-anchor-resolution-shadow-fix.py`)。
一是**归属**:这些底稿的小节标题就叫「## 十三、byterover README vs 代码对照(逐条)」
「### 2.7 README vs 代码对照(supermemory)」,归属由标题定死、不靠猜;
二是**内容**,两档任一 —— T1 逐字(引文/符号在目标那一段里逐字找得到,**51 处**),
T2 比较(笔记那句的实词在**目标**段里命中数**严格多于**在**根**段里,**9 处**)。
两档都不过的 **19 处点名留下**。

样例(改前 / 改后 / 根上那一行长什么样):

| 笔记 | 原锚点 → 改成 | 根上那一行(即读者原本会读到的) |
|---|---|---|
| `notes/r6-30-…md:423` supermemory `capture_mode` | `README.md:55` → `plugins/memory/supermemory/README.md:55` | 根 README:55 讲的是 MinGit 下载,与 `capture_mode` 毫无关系 |
| `notes/r6-40-…md:384` mem0 `user_id` | `README.md:30` → `plugins/memory/mem0/README.md:30` | 根 README:30 是 "Research-ready … Batch trajectory generation" |
| `notes/r6-10-honcho.md:674` `cmd_setup` | `cli.py:536` → `plugins/memory/honcho/cli.py:536` | 根 `cli.py:536` 是 `"web_extract": {` |

`plugins/memory/supermemory/README.md:55 @ 863e313`

```
| `capture_mode` | `all` | Skip tiny or trivial turns by default |
```

`plugins/memory/honcho/cli.py:536 @ 863e313`

```
def cmd_setup(args) -> None:
```

**两条判据挡下了真的假阳性,这是它值得的证据**:同一个探针脚本
(`data/r11c/d-anchor-resolution-rootshadow-judge.py`,只按内容不看归属)首轮给出 35 条候选,
逐条读下来 **2 条是假阳性**,而且两条都是「根上那个才对」:

- `notes/r4-20-remote-backends-serverless.md:408` 的 `README.md:29` —— 根 README:29 确实写着
  "Daytona and Modal … hibernates when idle",正是笔记引的那句;探针 `timeout=3600`
  是**同一行里另一个锚点**的摘录,被误当成了它的。
- `notes/r8b-raw-mixins.md:166` 的 `cli.py:231` —— 根 `cli.py:231`:`load_hermes_dotenv(hermes_home=_hermes_home, project_env=_project_env)`,
  正是笔记说的那句;该文另有 `cli.py:17589` 这样的行号,**只有 18,555 行的根 `cli.py` 容得下**
  (honcho 那个只有 1,967 行),全篇归属明确。

**这两条正是「不许瞎猜」要防的东西**:一个纯内容判据会把它们改到错的地方,
而它们改完之后**看起来完全正常**。

### 3.5 第二遍:行号本身也是判据 —— 又定下 75 处

**结论:934 处同名歧义里,283 处在「候选必须长到有这一行」这一条下只剩一个候选;
其中 75 处同时过了内容判据,已改;其余点名留下。**

第一遍的判据是「基线里恰好一个文件以它结尾」。`base.py:5584` 过不了那一关(9 个候选),
但这 9 个里**只有一个**长到有第 5,584 行:

| 候选 | 行数 | 有第 5584 行吗 |
|---|---|---|
| `gateway/platforms/base.py` | 6,861 | 有 |
| `tools/environments/base.py` | 1,370 | 没有 |
| `skills/productivity/docx/scripts/office/validators/base.py` | 875 | 没有 |
| 其余 6 个(`agent/secret_sources/base.py` 等) | ≤ 336 | 没有 |

**行号本身携带信息,而第一遍没用它。** 脚本 `data/r11c/d-anchor-resolution-fix2.py`
要求两条同时成立:长度过滤后只剩一个候选 **且** 该行的反引号片段在候选的
[N-12, N+12] 里逐字找得到。283 处过长度关,其中 **75 处**同时过内容关(已改),
**103 处**长度可定但内容判据不过、**519 处**长度也定不了 —— **全部点名留下**,
明细在 `data/r11c/d-anchor-resolution-fix2-left.tsv`。

```verify
tail -13 data/r11c/d-anchor-resolution-fix2-log.txt
```

```text
已改写 75 处;点名留下 622 处 {'长度判据不唯一': 519, '内容判据不过': 103}

改写最多的 10 个串:
    19  base.py -> gateway/platforms/base.py
    19  pairing.py -> gateway/pairing.py
     7  auth.py -> hermes_cli/auth.py
     6  webhook.py -> gateway/platforms/webhook.py
     5  session.py -> gateway/session.py
     3  config.py -> hermes_cli/config.py
     2  computer-use.md -> website/docs/user-guide/features/computer-use.md
     2  client.py -> plugins/memory/honcho/client.py
     2  cron-internals.md -> website/docs/developer-guide/cron-internals.md
     2  slash-commands.md -> website/docs/reference/slash-commands.md
```

**同一条长度判据也能替 `chapters/` 定案(本轮只报不改)。** 成品章里 10 处锚点违反
CLAUDE.md 成品章硬标准 8(「不写裸文件名」),其中 9 处在长度判据下是确定的:

| 成品章 | 锚点 | 长度判据下唯一的候选 |
|---|---|---|
| `chapters/r7b-platform-integration.md:226`(及 229-235,共 8 处) | `base.py:5584`…`base.py:5746` | `gateway/platforms/base.py`(6,861 行,9 个候选里唯一够长) |
| `chapters/r8b-cli-trunk-and-interaction.md:197` | `server.py:5811` | `tui_gateway/server.py`(14,006 行,4 个候选里唯一够长) |
| `chapters/r9a-capability-organization.md:430` | `creating-skills.md:178` | **定不了**:`website/docs/developer-guide/creating-skills.md`(438 行)与
`website/i18n/zh-Hans/…/creating-skills.md`(374 行)**都够长** —— 就是 §2.2 那个镜像歧义 |

**这 10 处本片一个字没改**(本轮第八项只报不改),交 R12 装订时按上表处理 —— 见 §5 移交 H-R11C-D-e。

---

## 4. 改完之后的读数

结论:**不可解析从 3,080 降到 1,212(12.1% → 4.7%)**;残余 1,212 里
**859 是不许猜的真歧义**,318 是本片边界外或块内不许改的,剩下 35 见 §3.3 的「没改的 3 类」。

### 4.1 三个读数的前后对照

| 读数 | 改前 | 改后 | 说明 |
|---|---|---|---|
| 甲 关卡判决(块级) | 18,253 | 18,255 | +2:3 处裸 `.sh` 补成全路径后,ccTLD 守卫不再挡它们,关卡第一次看见 |
| 甲 表格锚点 OK | 1,519 | **1,542** | **+23**:23 个此前从未被比对过的表格锚点变成真的被比对过 |
| 甲 表格锚点 UNCHECKED | 2,241 | 2,218 | −23,同上 |
| 甲′ 关卡正则命中 | 25,531 | 25,533 | 同 +2 |
| 乙 宽正则命中 | 25,558 | 25,558 | 不变(改的是路径,不是锚点数) |
| **乙 中不可解析** | **3,080(12.1%)** | **1,212(4.7%)** | −1,868 |
| 其中 UNIQUE-SUFFIX | 2,099 | 318 | −1,781 |
| 其中 AMBIGUOUS | 934 | 859 | −75:第二遍用「候选必须长到有这一行」+ 内容判据定下来的(§3.5)。**剩下 859 一处没猜** |
| 其中 NOT-IN-TREE | 35 | 23 | −12 |
| 其中 行号越界 | 4 | 1 | 剩下那 1 处是 `reports/round-9b` **故意**造的自测锚点 |

```verify
awk -F'\t' 'NR>1{c[$5]++} END{for(k in c) printf "%-30s %d\n", k, c[k]}' data/r11c/d-anchor-resolution-census-after.tsv | sort -k2 -rn
```

```text
AMBIGUOUS                      859
UNIQUE-SUFFIX                  318
NOT-IN-TREE                    23
RESOLVED-BASELINE              15
ABSPATH                        12
RESOLVED-STUDY                 1
RESOLVED-BASELINE-OUT-OF-RANGE 1
```

### 4.2 残余 318 处 UNIQUE-SUFFIX 全部落在四个已声明的边界内

**没有一处是「本该改而漏了」**:

```verify
cd /home/user/hermes-study && python3 - <<'PY'
import csv, re
from pathlib import Path
from collections import Counter
skip = {l.strip() for l in open("data/r11c/slice-c-files.txt") if l.strip()}
FENCE = re.compile("^\\s*" + chr(96) * 3)   # 反引号不能字面写在 verify 块里
QUOTE = re.compile(r"^\s*>")
cache = {}
def ctx(f, n):
    if f not in cache:
        lines = Path(f).read_text(encoding="utf-8", errors="replace").splitlines()
        st, infence = {}, False
        for i, l in enumerate(lines, 1):
            if FENCE.match(l):
                infence = not infence
                st[i] = "fence"
                continue
            st[i] = "fence" if infence else ("quote" if QUOTE.match(l) else "prose")
        cache[f] = st
    return cache[f].get(n, "?")
c = Counter()
for r in csv.DictReader(open("data/r11c/d-anchor-resolution-census-after.tsv", encoding="utf-8"),
                        delimiter="\t"):
    if r["class"] != "UNIQUE-SUFFIX":
        continue
    f = r["file"]
    top = f.split("/")[0]
    if f in skip:
        c["片C 的 31 份(硬边界,不许碰)"] += 1
    elif top != "notes":
        c[f"{top}/(本片范围外)"] += 1
    else:
        c["notes/ · " + ctx(f, int(r["line"]))] += 1
for k, v in c.most_common():
    print(f"  {v:>4}  {k}")
print(f"  ---- 合计 {sum(c.values())}")
PY
```

```text
   143  片C 的 31 份(硬边界,不许碰)
    89  notes/ · fence
    50  reports/(本片范围外)
    20  reviews/(本片范围外)
    16  notes/ · quote
  ---- 合计 318
```

### 4.3 R11B 那个 40.3% 现在是多少

同一份 41 文件名单、同一条判据:**1,334 → 411(40.3% → 12.4%)**。
剩下的 439 = 那 41 份里的同名歧义 + 归片 C 的文件 + 块内不许改的。

```verify
cd /home/user/hermes-study && python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
import verify_citations as vc
REPO = Path("/home/user/hermes-agent"); STUDY = Path("/home/user/hermes-study")
def resolve(p):
    t = REPO / p
    return t if t.is_file() or not (STUDY / p).is_file() else STUDY / p
files = sorted({"notes/" + l.split()[1].split(":")[0]
                for l in open("data/r11b/notes-citation-backlog.txt")})
tot = bad = 0
for f in files:
    for line in Path(f).read_text(encoding="utf-8").splitlines():
        for m in vc.citations(line, resolve):
            tot += 1
            bad += 0 if resolve(m.group("path")).is_file() else 1
print(f"R11B 口径({len(files)} 份):anchors={tot} unresolvable={bad} ({bad*100.0/tot:.1f}%)")
PY
```

```text
R11B 口径(41 份):anchors=3314 unresolvable=411 (12.4%)
```

### 4.4 剔除与不剔除两个读数(硬约束 10)

上面所有读数都是**剔除本轮 `r11c-*`** 的。不剔除的读数**在原理上不可钉**:
本底稿正文里写满了 `run.py:220`、`__init__.py`、`README.md:55` 这类字样当例子,
探针会把它们数进去,而**每往底稿里多写一句就改变一次读数** ——
这正是 CLAUDE.md「『搜过没有』类测量对报告它这个动作不幂等」说的那件事。
所以不剔除的读数只能作为**快照**给出,不进 ```verify:

```text
$ python3 data/r11c/d-anchor-resolution-scan.py /home/user/hermes-agent --no-exclude | head -4
语料:284 份 .md(chapters/notes/reports/reviews),不剔除本轮(--no-exclude)
甲′ 关卡正则命中 = 26085
乙  宽正则命中   = 26119   (差 34 个 = 关卡看不见的)
乙 中不可解析 = 1316 / 26119 = 5.0%
```

**两个读数都在这里:剔除本轮 1,212 / 25,558(4.7%),不剔除快照 1,316 / 26,119(5.0%)。**
(不剔除那个快照取于第二遍改写**之前**,因此比剔除读数高;它本来就是不可重跑的快照,
重取一次只会得到又一个不同的数 —— 这正是这条规矩要展示的性质。)
差额 561 个锚点、其中 29 个不可解析,来自本轮**七份** `r11c-*` 底稿
(取快照时 284 = 277 + 7:`r11c-90-handover-rulings`、`raw-anchor-resolution`(本文件)、
`raw-bad-evidence`、`raw-dedup-82`、`raw-id-collisions`、`raw-pre-binding-inventory`、
`raw-reversal-propagation`;其中多份仍在写,本文件也还会再长)。
那 29 个不可解析的绝大多数是本底稿散文里举的例子
(`run.py:220`、`README.md:55` 之类),它们是**被讨论的字符串**,不是要读者去跟的锚点
—— 这正是「报告它这个动作会改变读数」的具体形状。

---

## 5. 自查、移交、产出

### 5.1 关卡读数(本片)

```text
$ python3 scripts/verify_citations.py /home/user/hermes-agent chapters/*.md notes/r11c-raw-anchor-resolution.md
citations=506  OK=395  UNCHECKED=111
可校验比例 OK/506 = 78.1%
table_anchors=75  OK=13  UNCHECKED=62
OK: every code-block-backed citation matches the baseline     (退出码 0)

$ python3 scripts/verify_citations.py /home/user/hermes-agent notes/r11c-raw-anchor-resolution.md
citations=27  OK=9  UNCHECKED=18
可校验比例 OK/27 = 33.3%
table_anchors=42  OK=8  UNCHECKED=34
OK: every code-block-backed citation matches the baseline     (退出码 0)

$ python3 scripts/verify_evidence_commands.py notes/r11c-raw-anchor-resolution.md
verify-blocks paired=15  unpaired=3  differing=0  timedout=0
runnability   ran=3  runfail=0  skipped-mutating=0
OK: every paired ```verify command reproduces its pasted output   (退出码 0)

$ python3 data/r11c/probes/runnability_census.py   (确认片 C 的 bad=0 没被本片改回去)
readonly_unpaired=541 exit0=513 silent_exit1=28 bad=0 skipped_mutating=155
bad_by_kind=(none)
baseline_porcelain_changed=False

$ git -C /home/user/hermes-agent status --porcelain   ->  空(基线只读,未被触碰)
```

**本片底稿单独口径 33.3%,低于 70% 下限,如实说明原因**:本片研究的对象是**本学习仓库
的语料本身**(锚点解析面),不是 hermes-agent 的某个机制;它的证据主体是**对语料的普查读数**,
按 CLAUDE.md 只能贴在 ```` ```verify ```` / ```` ```text ```` 里(声明式非源码),
一律记 UNCHECKED。本片对基线的断言只有 9 条,**9 条全 OK**。
把这一片逼到 70%,只能靠往里塞与结论无关的基线代码块。
`chapters/` 合并口径 **78.1%**,过线。
*(这两个读数会随本节自己被写进去而再动一两位 —— 这正是 §4.4 那条不幂等性的又一个实例;
上面抄的是本底稿定稿时的那一次运行。)*

### 5.2 收工前三条边界的自查

| 边界 | 自查 | 结果 |
|---|---|---|
| `chapters/` 一个字不改 | `git status --porcelain chapters/` | 空 |
| 片 C 的 31 份不许碰 | `git status --porcelain $(cat data/r11c/slice-c-files.txt)` | 空 |
| 片 B / 片 E 的底稿不许碰 | `git status --porcelain notes/r11c-raw-dedup-82.md notes/r11c-raw-reversal-propagation.md` | 空(它们是未跟踪的新文件,本片没写过) |
| 基线只读 | `git -C /home/user/hermes-agent status --porcelain` | 空 |
| 片 C 的 `bad=0` 没被改回去 | 重跑 `runnability_census.py` | `bad=0` |

### 5.3 移交

| 编号 | 锚点 + 一句话现象 | 建议去向 |
|---|---|---|
| **H-R11C-D-a** | 扩展名白名单漏了 `ps1` / `css` / `tsv`:全语料 **16 处**锚点能从仓库根解析却**不被关卡当成锚点**(14 处 `scripts/install.ps1`、1 处 `apps/desktop/src/styles.css`、1 处自引 `data/ledger.tsv`)。白名单在 `scripts/verify_citations.py:169`:`CITE_EXTS = "py|mdx|md|yaml|yml|toml|c|h|sh|json|tsx|ts|mjs|js|nix|rs|txt"` | 按 R10B 立的规矩加:**连同一次全语料前后对比一起加**。`ps1` / `css` / `tsv` 都不是 ccTLD,不需要额外守卫 |
| **H-R11C-D-b** | **镜像型歧义**:`website/docs/**` 每份文档在 `website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/` 下都有同名镜像,于是**任何裸文档名恒有 ≥2 个候选**,机械判据永远定不了。全语料 **264 处 / 50 个文档名**;而文档侧正是每条 ▲ 定案的一半 | 定一条**写法**而不是加一条猜法:引 `website/docs` 一律写全路径;引中文镜像时**显式**写 `website/i18n/zh-Hans/…` 全路径(本片已按此改了 5 处省略中段的) |
| **H-R11C-D-c** | **「解析成功」是假保证**:1,543 处裸锚点解析到仓库根上的同名文件,而根上那 11 个名字在树的别处都还有同名(`cli.py` 1,344 处 / 根 18,555 行 / 别处 7 个)。本片改正 60 处、点名留下 19 处;**任何现有关卡都发现不了这一类**。留下的 19 处见 `data/r11c/d-anchor-resolution-shadow-fix.py` 干跑输出 | 给关卡加一档**非阻断提示**:裸文件名锚点若其 basename 在基线里 >1 个,打印「疑似根遮蔽」。判据现成,见 `data/r11c/d-anchor-resolution-rootshadow.py` |
| **H-R11C-D-d** | **859 处同名歧义一处没猜**:`__init__.py` 156 处 / 基线 **171 个**候选、`base.py` 剩余 95 处 / 9 个候选。其中 **103 处**用「候选必须长到有这一行」已能定到唯一候选、只差内容判据没过,**519 处**长度也定不了。逐条明细:`data/r11c/d-anchor-resolution-fix2-left.tsv:1`:`file	line	anchor	reason` | 那 103 处值得人工过一遍(长度已定,只欠一眼确认);519 处需按小节上下文批处理,不要机械改 |
| **H-R11C-D-e** | **成品章 10 处违反硬标准 8**(不写裸文件名):`chapters/r7b-platform-integration.md:226`:`gateway/platforms/base.py` 起 8 处 `base.py:5584`…`:5746`、`chapters/r8b-cli-trunk-and-interaction.md:197` 的 `server.py:5811`、`chapters/r9a-capability-organization.md:430` 的 `creating-skills.md:178`。**本轮只报不改** | 前 9 处的目标已由长度判据定死(§3.5 那张表),R12 装订时照抄即可;第 10 处是 H-R11C-D-b 那个镜像歧义,需作者判 |
| **H-R11C-D-f** | **本片范围外的 70 处可机械补全锚点**:`reports/` 50 处、`reviews/` 20 处。`reports/` 按 CLAUDE.md「正文不静默改写」,`reviews/` 原文不改 —— 于是这 70 处**在现行制度下无人可改** | 主线定策:是否给「锚点补全」开一个与「行号漂移」同级的例外(行号漂移已是就地改 + 勘误节点名) |
| **H-R11C-D-g** | **片 C 的 31 份里还有 143 处**可机械补全锚点(硬边界,本片一处没碰);另有 `notes/` 里 **89 处在围栏块内、16 处在引用块内**,本片按「块内不改」的规矩一律没动 | 31 份那批下一轮直接跑 `data/r11c/d-anchor-resolution-fix.py`(判据与本片相同);块内那 105 处需逐块判「这是逐字摘录还是笔记自己的话」,不可批处理 |
| **H-R11C-D-h** | `notes/r9a-h-r8d-ef-surveys.md:408`:`skills/.../google-workspace/scripts/gws_bridge.py:54` —— 3 处省略中段的路径写在一个 ```` ```text ```` 手工列宽对齐表里,补全会破坏对齐;真实路径已查明(`skills/productivity/google-workspace/scripts/gws_bridge.py` 等) | 连同该表整体重排一次,或改为表格 |
| **H-R11C-D-i** | **`vc.citations()` 无左侧 lookbehind**,于是绝对路径被从中间切一刀:`notes/r8c-raw-boot-authchain.md:60` 的 `/home/user/hermes-venv/.../applications.py:4723` 被解析成 `home/user/…`,在统计里与「写错的相对路径」无法区分(全语料 12 处) | 给 `CITE` 加一条与 `CITE_EXTLESS` 同款的 lookbehind,并对以 `/` 开头的锚点单列一档 `ABSOLUTE`(计入分母、不阻断),与 H-R11B-D-a 的 `NON-BASELINE` 一档同源 |

### 5.4 产出清单

| 文件 | 是什么 |
|---|---|
| `notes/r11c-raw-anchor-resolution.md` | 本底稿 |
| `data/r11c/d-anchor-resolution-scan.py` | 三口径普查探针(甲′/乙 + 七分类) |
| `data/r11c/d-anchor-resolution-census.tsv` / `-summary.txt` | **改写前**冻结快照(本底稿 §1–§2 所有数的出处) |
| `data/r11c/d-anchor-resolution-census-after.tsv` / `-summary-after.txt` | 改写后快照(§4) |
| `data/r11c/d-anchor-resolution-corpus.txt` | 冻结的 277 份语料名单 |
| `data/r11c/d-anchor-resolution-gate-before.txt` / `-gate-after.txt` | 关卡全语料输出,改写前 / 后 |
| `data/r11c/d-anchor-resolution-validate.py` | 改写前的独立内容校核(§3.1.1) |
| `data/r11c/d-anchor-resolution-fix.py` / `-fix-log.txt` | 第一遍:唯一候选补全,1,781 处 |
| `data/r11c/d-anchor-resolution-manual-fixes.py` | 逐条确证的 14 条改正(§3.3) |
| `data/r11c/d-anchor-resolution-rootshadow.py` | 根同名遮蔽面的量化(§3.4) |
| `data/r11c/d-anchor-resolution-rootshadow-judge.py` / `-rootshadow.tsv` / `-rootshadow-review.txt` | 遮蔽锚点的内容判定 + 35 条候选的逐条并排复核 |
| `data/r11c/d-anchor-resolution-shadow-fix.py` | 归属 + 内容两档判据,改正 60 处指错文件的锚点 |
| `data/r11c/d-anchor-resolution-readme-attrib.txt` | 裸 README 锚点按小节标题归属的逐条证据 |
| `data/r11c/d-anchor-resolution-fix2.py` / `-fix2-log.txt` / `-fix2-left.tsv` | 第二遍:长度判据 + 内容判据,75 处;点名留下 622 处 |
| `data/r11c/d-anchor-resolution-runnability-after.txt` | 重跑片 C 的可跑性普查,`bad=0` |

**改动的历史文件:114 份 `notes/`,共 1,930 处锚点路径**
(1,781 唯一候选 + 75 长度判据 + 60 根遮蔽 + 14 逐条确证),
另有 2 处表格锚点改写成声明式(§3.2,改的是排版不是路径)。
`chapters/` / `reports/` / `reviews/` / 片 C 的 31 份 / 基线:**一个字未改**。

## 完成信号

片 D 完成。产出如 §5.4 那张表(1 份底稿 + 15 个 `data/r11c/d-anchor-resolution-*` 产物),
改动 114 份历史 `notes/`(1,930 处锚点路径 + 2 处表格锚点排版)。三条关卡命令均退出码 0(§5.1),基线 porcelain 为空。
**claim 由主线关,本片不动 `data/inflight/r11c-d-anchor-resolution.claim`。**
