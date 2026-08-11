# r11f-fix-91 · 强制范围的单一落点,与清单可执行面的两条路径

> 底稿。求全求证。本文结清交付问题第 3、4 两项。
> 指向基线的锚点写 `路径:行号 @ 863e313`(基线固定 `863e31318`,只读);
> 指向本仓库的锚点不带 sha 时,指的是本轮收工树。

---

## 1. 第 4 项:引用关卡的执行范围与 CLAUDE.md 的强制范围口径不一致

### 1.1 现象

CLAUDE.md 把强制范围写成一段散文里的 shell:**`chapters/` 全部 + `reading/` 全部 +
本轮的 `notes/` 与 `reports/`**。R11F 收官报告 §11 记的却是:

`reports/round-11f-plugin-surface.md:463 @ bdb82d5`

> | `verify_citations.py`(定稿全量 = `chapters/` + 当轮 `notes/` + 本报告) | `citations=726 OK=589` **81.1%**;`table_anchors=428 OK=384`;**0 MISMATCH / 0 BLOCK-DRIFT / 0 TABLE-DRIFT / 0 TABLE-OUT-OF-RANGE** | 0 |

**`reading/` 那一段掉了。** 掉了之后:关卡照样绿、报告照样报数、退出码照样 0,
**没有任何东西会指出少跑了一段**。

这与 R10B 记下的「白名单外的锚点连分母都进不去」是**同一物种**:
少掉的那一段**不会让关卡变红,只会让分母变小**。而分母变小时,可校验比例通常还会**变好看**
—— `reading/02-principles.md` 那 6 条引用全是 UNCHECKED(它们是从
`chapters/r8a` / `chapters/r9c` 里**本来就写成散文内联**的锚点逐字派生来的),
所以漏掉 `reading/` 让 R11F 的合并比例从 80.5% 抬到了 81.1%。
**一次口径遗漏,恰好朝着"看起来更好"的方向偏。**

### 1.2 根因:范围只存在于作者当时敲进终端的那一行里

三道关卡里,`verify_reading_layer.py` 与 `verify_chapter_order.py` 自己知道该扫什么;
只有 `verify_citations.py` / `verify_evidence_commands.py` 靠**调用方传一串文件名**。
于是「本轮实际跑了哪些文件」这件事既不在关卡输出里,也不在任何检查面上
—— 这正是本项目反复栽的那类形状(不带锚点的东西不在任何检查面上)。

### 1.3 改法:单一落点 + 把范围印在读数上面

`scripts/mandatory_scope.py:42`

```
SEGMENTS = (
    ("chapters", "chapters/*.md"),          # 成品章全部
    ("reading", "reading/*.md"),            # 派生阅读层全部(R11E 并入)
    ("notes", "notes/r{round}-*.md"),       # 本轮底稿
    ("reports", "reports/round-{round}-*.md"),  # 本轮报告
)
```

两道关卡都加 `--round N` 从这里展开,并在读数**上面**印一行 `scope=`:

```verify
python3 scripts/mandatory_scope.py --round 11f | grep -o 'reading=[0-9]*'
```

```text
reading=3
```

*这里只钉 `reading=3` 这一段,不钉整行 `scope=…`:`chapters/` 与 `reading/` 会随 R12 增长,
把整行钉死就是又造一个「量之前的命令钉在会移动的引用上」—— 而那正是本轮
`notes/r11f-fix-90-derived-gate-both-legs.md` §7 在修的形状。本文写作时整行是
`scope=CLAUDE.md/mandatory round=11f  files=36  (chapters=22  reading=3  notes=9  reports=2)`
—— **这个数会变,所以不当结论钉**;不变的是「`reading` 这一段在范围里、且非空」。*

任一段解析出 0 个文件即 `EMPTY-SCOPE` **阻断**,不静默跳过。理由与 R11E 给阅读层关卡定的
`EMPTY-GATE` 一字不差:**一个什么都没扫的关卡也会打印绿字**。

CLAUDE.md 的两处命令块同步改为 `--round N`,并写明「报告里的读数必须用 `--round` 取」。

### 1.4 负控(S1..S4)

探针:`data/r11f-fix/probes/gate_scope_negative_control.py`。
S1/S2/S3 在 `mktemp -d` 造的临时 STUDY 里跑(只放一份 `scripts/mandatory_scope.py`,
它的 `STUDY = parents[1]` 于是指向临时目录);S4 在真仓库上比集合,只读。

```verify
cd /home/user/hermes-study && python3 data/r11f-fix/probes/gate_scope_negative_control.py | tail -2
```

```text
negative-control S1..S4   PASS=4/4
OK: 空段两种形态均实际触发阻断;--round 与 CLAUDE.md 的 glob 逐字同集
```

**触发时的完整输出**:

```text
==============================================================================
S1 · reading/ 段解析出 0 个文件 -> EMPTY-SCOPE 阻断
==============================================================================
exit=1
  FAIL [EMPTY-SCOPE]: 强制范围里有段解析出 0 个文件 —— reading (reading/*.md)
        少跑一段不会让关卡变红,只会让分母变小(R11F 就是这么丢掉 reading/ 的)。
        要么这一段真的不该在强制范围里(那就改 scripts/mandatory_scope.py 的 SEGMENTS,让它进 diff),要么轮次号写错了。
断言:PASS

==============================================================================
S2 · 轮次号写错 -> notes/reports 两段皆空,同样阻断
==============================================================================
exit=1
  FAIL [EMPTY-SCOPE]: 强制范围里有段解析出 0 个文件 —— notes (notes/rnosuch-*.md); reports (reports/round-nosuch-*.md)
        少跑一段不会让关卡变红,只会让分母变小(R11F 就是这么丢掉 reading/ 的)。
        要么这一段真的不该在强制范围里(那就改 scripts/mandatory_scope.py 的 SEGMENTS,让它进 diff),要么轮次号写错了。
断言:PASS

==============================================================================
S3 · 正控:四段齐全 -> 解析成功且逐段报数
==============================================================================
exit=0
  scope=CLAUDE.md/mandatory round=9z  files=4  (chapters=1  reading=1  notes=1  reports=1)
断言:PASS

==============================================================================
S4 · 真仓库:--round 展开 == CLAUDE.md 的 glob,差额即 R11F 少跑的那一段
==============================================================================
exit=0
  --round 11f 展开 33 个文件
  CLAUDE.md 那行 glob 展开 33 个文件
  两者相同 ? True
  R11F 报告 §11 记的范围(无 reading/)展开 30 个文件
  差额 3 个,逐个点名:
    - reading/01-quickread.md
    - reading/02-principles.md
    - reading/03-problem-index.md
断言:PASS

==============================================================================
negative-control S1..S4   PASS=4/4
OK: 空段两种形态均实际触发阻断;--round 与 CLAUDE.md 的 glob 逐字同集
```

*S4 的 33 / 30 是本文写作时的读数(本轮 `notes/` 与 `reports/` 尚未全部落库),
上面 §1.3 那个 `--round 11f` 块是收工树的读数。**同一个指标两次测量,口径不同,
按 CLAUDE.md「同一指标多次/多方法测量必须分别标注」分开写,不写成"读数相同"。**
两次之间不变的是差额 **3**,以及那 3 个文件的名字 —— 那才是这条负控要钉的东西。*

### 1.5 重新取得的引用读数

见本轮报告 §4。口径一律为 `--round 11f`(它同时覆盖 R11F 的 7 份 `notes/` 与
本轮新增的 2 份,因为 `notes/r11f-*.md` 这个模式把 `notes/r11f-fix-*.md` 也包了进来)。

---

## 2. 第 3 项:`chapters/r11f-plugin-surface.md` §3.4 的触发条件与执行方式

### 2.1 原文错在哪

原 §3.4 先说「消费侧用 `shlex.split` 跑 `check`,用 `shell=True` + `/bin/bash` 跑 `install`」,
紧接着说「关键在**触发条件**……触发**它**的是 `GET /api/memory` 这类只读端点」,
最后收尾为「**往插件目录放一个文件,就能让一个只读请求执行任意 shell**」。

「它」指代不明,而收尾那句把两条路径的**最坏面**拼到了一起:
只读端点确实会执行清单里的命令,但**执行的是 `check`,而且是 argv 形式、不经 shell**;
`shell=True` + `/bin/bash` 的那一条是 `install`,它由**另一个写侧端点**触发。
按字面读,原文既**高估**了只读那条路(它不解释 shell 元字符),
也**低估**了它(它确实以网关进程身份执行了一个由插件目录自带清单点名的程序)。

*这与 CLAUDE.md 记下的 `gateway-internals.md:86`「一句话讲了三件事,只点了中间那句」
是同一形状,只是这次发生在**我们自己的成品章**里,不是在被研究项目的文档里。*

### 2.2 逐段核实(全部落在基线 `863e31318`)

**路径一 · 只读端点 → `check` → argv**

| 跳 | 锚点 + 摘录 |
|---|---|
| 1 | `hermes_cli/web_server.py:12739`:`@app.get("/api/memory")` |
| 2 | `hermes_cli/web_server.py:12756`:`"providers": _discover_memory_provider_statuses(),` |
| 3 | `hermes_cli/web_server.py:5941`:`setup = _memory_provider_setup_info(name)` |
| 4 | `hermes_cli/web_server.py:5277`:`setup["dependencies_installed"] = _memory_provider_dependencies_installed(setup)` |
| 5 | `hermes_cli/web_server.py:5395`:`shlex.split(check_cmd),` |
| 6 | `hermes_cli/web_server.py:5365`:`executable="/bin/bash" if shell else None,` |

第 5 跳所在的调用没有传 `shell`,而 `_run_setup_command` 的签名默认为假:

`hermes_cli/web_server.py:5355 @ 863e313`

```
def _run_setup_command(
    command: Any,
    *,
    display: str,
    shell: bool = False,
    timeout: int = 180,
) -> subprocess.CompletedProcess:
```

所以第 6 跳的 `executable` 取 `None`,`subprocess.run` 收到的是一个 argv 列表。
**这条路上 `install` 只被读、不被执行**:

`hermes_cli/web_server.py:5387 @ 863e313`

```
        check_cmd = str(dep.get("check") or "").strip()
        install_cmd = str(dep.get("install") or "").strip()
        if not check_cmd:
            if install_cmd:
                external_ok = False
            continue
```

`install_cmd` 在这一段的**唯一**用途是决定「连 `check` 都没写时该不该判为未安装」。

**路径二 · 写侧端点 → `install` → 整串 `/bin/bash`**

| 跳 | 锚点 + 摘录 |
|---|---|
| 1 | `hermes_cli/web_server.py:6059`:`@app.post("/api/memory/providers/{name}/setup")` |
| 2 | `hermes_cli/web_server.py:6078`:`return _install_memory_provider_setup(name)` |
| 3 | `hermes_cli/web_server.py:5589`:`_install_memory_provider_external_dependencies(setup["external_dependencies"])` |
| 4 | `hermes_cli/web_server.py:5495`:`if check.returncode == 0:` |
| 5 | `hermes_cli/web_server.py:5524`:`shell=True,` |
| 6(装完验收) | `hermes_cli/web_server.py:5552`:`shlex.split(check_cmd),` |

第 4 跳是这条路上的**短路**:`check` 成功就 `continue`,`install` 不跑。

`hermes_cli/web_server.py:5516 @ 863e313`

```
            if not install_cmd:
                continue

        if install_cmd:
            try:
                install = _run_setup_command(
                    install_cmd,
                    display=install_cmd,
                    shell=True,
                    timeout=300,
                )
```

**执行清单命令的地方一处不多、一处不少**(搜索面 = `hermes_cli/web_server.py` 全文,
模式 `shell=True` 与 `shlex.split`,无排除):`shell=True` 只有 `:5524`;
`shlex.split` 恰好三处 —— `:5395`(只读端点)、`:5480`(写侧装之前)、
`:5552`(写侧装之后的验收)。所以 `check` 在路径二上最多跑两次,`install` 最多一次。

注意第一个参数是 `install_cmd` **本身**(一个字符串),不是 `shlex.split(install_cmd)`
—— 整串交给 `/bin/bash`。byterover 清单里那行 `curl … | sh` 是一个**管道**,
它要成立正需要这条路;放在路径一上,`|` 只会是 `brv` 的一个普通参数。

**两条路共同的前置:发现靠文本嗅探,不经 `plugins.enabled`**

`plugins/memory/__init__.py:84 @ 863e313`

```
        source = init_file.read_text(errors="replace", encoding="utf-8")[:8192]
        return "register_memory_provider" in source or "MemoryProvider" in source
```

而路径一的循环走的是 `discovered`,不是配置:

`hermes_cli/web_server.py:5938 @ 863e313`

```
    for name in sorted(discovered):
        row = discovered[name]
        provider = None if row["missing"] else _load_memory_provider(name)
        setup = _memory_provider_setup_info(name)
```

### 2.3 改法

§3.4 拆成三块:路径一(只读 → `check` → argv)、路径二(`POST …/setup` → `install` →
`shell=True` + `/bin/bash`)、一张并排对照表(端点/字段/执行方式/超时/作用范围/锚点),
结论按路径分开写。**设计教训那句保留**,并补一句限定:
「挂上去的是 argv 还是整串 shell,决定的是后果有多大,不是这道开关还在不在。」

**同一处混淆在本章另外两个位置也有,一并改**(不改会让同一章自相矛盾):

* TL;DR 第二个结论(`chapters/r11f-plugin-surface.md:18`);
* 全景图里那条虚线边(原为一条边指向「被只读端点触发执行」,改为两条边分指两条路径)。

这两处**超出「§3.4」的字面范围**,如实记在这里,并在报告 §3.3 贴完整 diff。

### 2.4 与本簇 ■ 计数的关系

**不变。** 本轮改的是**机制描述的精度**,不是缺陷的成立与否:
`H-R11F-F-a`(把执行挂在发现上、绕过 `plugins.enabled`)两条路径都成立,
成品章 §5 的 `■ 12` 一个字不动。

---

## 3. 移交

| 案号 | 现象(带锚点) | 去向(条件式收件人) |
|---|---|---|
| `H-R11Ffix-d` | `--round` 只覆盖 CLAUDE.md 那四段;`reviews/`、历史轮次 `notes/` 仍在强制范围之外(这是 R11A 有意定的,理由是环境漂移),但**没有任何机制记录"这一轮自愿多跑了哪些"** —— `scripts/mandatory_scope.py:34`:`SEGMENTS = (` | **任何一轮想把某段纳入强制范围时**,改的是 `SEGMENTS` 这张表(它会进 diff、可被评审),不许在命令行上临时补 glob |
| `H-R11Ffix-e` | 路径一实际执行的是 `check` 指定的程序,`_memory_provider_setup_env()` 还会把四个目录**前插**进 `PATH`(`hermes_cli/web_server.py:5322`:`extra_bins = [`),其中 `~/.brv-cli/bin` 是 byterover 自己的安装位置 —— 本轮只核实"执行方式",**未展开这条 PATH 前插对利用面的影响** | **代码缺陷复核轮**(不属本轮:本轮边界是不新开内容轮范围) |
