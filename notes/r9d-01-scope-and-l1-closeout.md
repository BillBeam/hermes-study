# r9d-01 · 本轮范围核对 与 L1 收口报数

> 主线产出。溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于块前。
> 本篇不含 hermes-agent 行为断言,数据全部来自本仓库台账与产出语料,命令均可重跑。

---

## 1. 开工先核范围

任务书写 R9D 为 49 文件 / 26,434 行。台账实测一致:

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$5); if($5=="R9D"){n++; l+=$3}} \
    END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

```text
49 文件 / 26434 行
```

49 个**全部**是 `layer=L1`、`status=R1-inventoried`(从未开工),无一例外:

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$4); sub(/\r$/,"",$5); \
    sub(/\r$/,"",$6); if($5=="R9D"){c[$4"/"$6]++}} END{for(x in c) printf "%s\t%d\n", x, c[x]}' \
    data/ledger.tsv
```

```text
L1/R1-inventoried	49
```

### 1.1 主题与拆片

这一片的共同主线是**「agent 的手脚」**:前面各轮读的是回合怎么转(R2)、工具框架怎么搭(R3)、
在哪儿执行(R4)、状态怎么存(R5)、记忆(R6)、网关(R7 系)、CLI(R8 系)、能力组织与交付面(R9A/B/C);
剩下这 49 个是**具体那些手脚本身**——读写文件、管看板、发消息、查网页、接语言服务器。

按此拆六片派工(逐文件核过覆盖,无重无漏):

| 片 | 主题 | 文件 | 行数 | 底稿 |
|---|---|---|---|---|
| A | LSP 子系统(语言服务器接入全套) | 11 | 4,708 | `notes/r9d-raw-lsp.md` |
| B | 文件读写与安全(agent 碰磁盘的全部入口) | 7 | 6,488 | `notes/r9d-raw-file-io-safety.md` |
| C | 看板、待办与定时任务(自我任务管理) | 5 | 4,073 | `notes/r9d-raw-kanban-todo-cron.md` |
| D | 消息外发与平台工具(主动往外发) | 6 | 5,052 | `notes/r9d-raw-messaging-platform-tools.md` |
| E | 网络检索与浏览器供给(信息输入面) | 6 | 2,673 | `notes/r9d-raw-search-browser-supply.md` |
| F | 工具网关、澄清与回合杂项 | 14 | 3,440 | `notes/r9d-raw-gateway-clarify-turn-misc.md` |
| **合计** | | **49** | **26,434** | |

拆片的加总与台账逐行核对(命令按上表的文件归属重算,不是照抄):

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$5); if($5!="R9D") next; p=$1; l=$3;
  if(p ~ /^agent\/lsp\//) g="A";
  else if(p=="agent/file_safety.py"||p=="tools/file_operations.py"||p=="tools/file_tools.py"||p=="tools/read_extract.py"||p=="tools/working_diff.py"||p=="tools/read_preview_tool.py"||p=="tools/open_preview_tool.py") g="B";
  else if(p=="tools/kanban_tools.py"||p=="agent/kanban_stop.py"||p=="tools/todo_tool.py"||p=="tools/project_tools.py"||p=="tools/cronjob_tools.py") g="C";
  else if(p=="tools/send_message_tool.py"||p=="tools/discord_tool.py"||p=="tools/homeassistant_tool.py"||p=="tools/feishu_doc_tool.py"||p=="tools/feishu_drive_tool.py"||p=="tools/yuanbao_tools.py") g="D";
  else if(p=="tools/web_tools.py"||p=="tools/x_search_tool.py"||p=="agent/web_search_provider.py"||p=="agent/web_search_registry.py"||p=="agent/browser_provider.py"||p=="agent/browser_registry.py") g="E";
  else g="F";
  n[g]++; s[g]+=l; tn++; ts+=l}
END{for(k in n) printf "%s\t%d 文件\t%d 行\n", k, n[k], s[k]; printf "合计\t%d 文件\t%d 行\n", tn, ts}' \
  data/ledger.tsv | sort
```

```text
A	11 文件	4708 行
B	7 文件	6488 行
C	5 文件	4073 行
D	6 文件	5052 行
E	6 文件	2673 行
F	14 文件	3440 行
合计	49 文件	26434 行
```

移交项定案另立 `notes/r9d-91-handover-rulings.md`(主线独立复核,不转述子代理)。

### 1.2 开工杂项:惰性安装纪律(沿用 R9C)

基线的可选依赖是**惰性安装**的:导入某后端时若缺包,它会联网 pip 安装到当前 venv(默认开启)。
R9C 已把关掉它定为开工杂项。本轮同样**实测**开关有效,而不是照 R9C 的结论假定:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c \
  "from tools.lazy_deps import _allow_lazy_installs, _lazy_install_target; \
   print('_lazy_install_target()      =', _lazy_install_target()); \
   print('_allow_lazy_installs()      =', _allow_lazy_installs())"
```

```text
_lazy_install_target()      = None
_allow_lazy_installs()      = False
```

不设该变量时的对照:

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python -c \
  "from tools.lazy_deps import _allow_lazy_installs; print('_allow_lazy_installs()      =', _allow_lazy_installs())"
```

```text
_allow_lazy_installs()      = True
```

*一处与 R9C 报告的差异,如实记下*:R9C 报告 §1.1 把这个开关写在 `hermes_cli.lazy_install`,
本轮按该路径 import **失败**(`ModuleNotFoundError: No module named 'hermes_cli.lazy_install'`),
实际模块是 `tools/lazy_deps.py`。R9C 报告正文不静默改写,此处留痕即可;
R9C 的**结论**(开关有效)成立,只是模块路径写错了。

此后所有跑基线代码的命令一律带 `HERMES_DISABLE_LAZY_INSTALLS=1`,并写进六份派工书与四份取证书。

---

## 2. 恢复必报项:`R1-inventoried` 剩余

CLAUDE.md 要求每轮报告必报此项(理由:分层快照几乎不动,读者从分层列读不出"还剩多少没开工")。

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$6); if($6=="R1-inventoried"){n++; l+=$3}} \
    END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

R9D 开工时:**7,785 文件 / 1,988,790 行**。
本轮 49 个转 `R9D-deep-read` 后应为 **7,736 文件 / 1,962,356 行**(收工复核见报告)。

---

## 3. L1 收口:R9C §3.2 六项的报数底稿

R9C 报告 §3.2 定了六项收口条件。本节按项取证,报告照此报数。

### 3.1 第 1 项 · 台账归零

开工时 L1 内的 `status` 分布(514 个已 deep-read + 49 个未开工 = 563):

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$4); sub(/\r$/,"",$6); \
    if($4=="L1"){c[$6]++; l[$6]+=$3}} END{for(x in c) printf "%s\t%d 文件\t%d 行\n", x, c[x], l[x]}' \
    data/ledger.tsv | sort
```

```text
R1-inventoried	49 文件	26434 行
R2-deep-read	46 文件	68645 行
R3-deep-read	32 文件	29234 行
R4-deep-read	35 文件	24418 行
R5-deep-read	28 文件	45809 行
R6-deep-read	27 文件	24423 行
R7-deep-read	16 文件	38343 行
R7B-deep-read	36 文件	43411 行
R7C-deep-read	47 文件	28282 行
R8A-deep-read	15 文件	21893 行
R8B-deep-read	50 文件	43539 行
R8D-deep-read	52 文件	42284 行
R9A-deep-read	37 文件	38893 行
R9B-deep-read	46 文件	27325 行
R9C-deep-read	47 文件	19274 行
```

**注意 L1 里没有 `R8C-deep-read` 这一档**:R8C(仪表盘与 Web)那一轮覆盖的文件不在 L1。
这不是漏,是那一轮的范围本就落在别层——写在这里,免得下一个读者把它当成缺口。

### 3.2 第 2 项 · 分层未被搬动(逐行 diff)

R9C 定这一项的理由值得原样记住:

> 达成"L1 全读完"最省力的办法不是去读,而是把读不动的文件降层到 L2;
> 只报 status 列的话,这种搬动完全不可见。

因此比对的是**文件集合本身**,不是计数。基准取自 **R9C 合入 main 的那个 commit 的台账**
(`75e0261`),不是取自本地工作区——否则"基准"会跟着我一起变:

```verify
cd /home/user/hermes-study && git show 75e0261:data/ledger.tsv | \
    awk -F'\t' 'NR>1{sub(/\r$/,"",$4); if($4=="L1") print $1}' | sort \
    > /tmp/l1-at-r9c-close.txt && wc -l < /tmp/l1-at-r9c-close.txt
```

```text
563
```

收口时的比对命令与输出见报告(收工时跑)。基准文件已 commit 进本仓库
`data/r9d/l1-fileset-at-r9c-close.txt`,sha256 `feeaee3b02ab10e5142ee27cb01cca367bc16bc6da6bdf817e35a56b7b9c2f23`,
供任何后续轮次原样复核。

### 3.3 第 4 项 · 点名覆盖率(历史积压逐个点名)

R9C §3.1 立了这个测量:把已标 `*-deep-read` 的 L1 文件路径,拿去产出语料里做**精确子串**搜索。
路径零命中意味着该文件上**没有任何一条可溯源断言**(本项目的证据格式要求断言紧跟 `路径:行号`)。

本轮用独立重写的脚本复测,**先复现 R9C 的两行读数**以确认口径一致
(脚本在 scratchpad,不进 `scripts/` —— 子代理运行期间不改共享资源):

| 语料 | 被测文件数 | 全路径零命中 | 连裸文件名也零命中 |
|---|---|---|---|
| `notes/` + `chapters/` | 514 | 42 文件 / 8,234 行 | 14 文件 / 5,150 行 |
| `notes/` + `chapters/` + `reports/` | 514 | **40 文件 / 7,811 行** | **11 文件 / 2,820 行** |

**口径必须说清的一点**:R9C 报这两行时被测集合是 **467** 个(它自己的 47 个当时尚未落账),
本轮复测时被测集合是 **514** 个(含 R9C 的 47)。**被测集合不同,零命中数却完全相同**
——这不是巧合也不是同一次测量,而是一条独立结论:**R9C 那 47 个文件全部有全路径点名,新增零命中为 0。**

**这 40 个是历史积压,逐个点名如下**,按其原属轮次归并(第三列是台账里的 `round` 列):

| 原属轮 | 文件数 | 行数 | 文件 |
|---|---|---|---|
| R2 | 4 | 564 | `agent/jiter_preload.py`(39,**裸名也零命中**)、`agent/oneshot.py`(158)、`agent/reasoning_timeouts.py`(231,**裸名也零命中**)、`agent/thinking_timeout_guidance.py`(136,**裸名也零命中**) |
| R4 | 4 | 222 | `tools/close_terminal_tool.py`(70,**裸名也零命中**)、`tools/computer_use/__init__.py`(45)、`tools/environments/__init__.py`(14)、`tools/read_terminal_tool.py`(93,**裸名也零命中**) |
| R6 | 2 | 980 | `plugins/memory/honcho/config_schema.py`(324)、`plugins/memory/honcho/oauth_flow.py`(656) |
| R7B | 12 | 4,960 | `gateway/platforms/media_cache.py`(202,**裸名**)、`gateway/platforms/msgraph_webhook.py`(453)、`gateway/platforms/qqbot/__init__.py`(91)、`gateway/platforms/qqbot/chunked_upload.py`(602)、`gateway/platforms/qqbot/constants.py`(74)、`gateway/platforms/qqbot/keyboards.py`(461,**裸名**)、`gateway/platforms/qqbot/onboard.py`(220,**裸名**)、`gateway/platforms/qqbot/utils.py`(71)、`gateway/platforms/yuanbao_media.py`(665,**裸名**)、`gateway/platforms/yuanbao_proto.py`(1418)、`gateway/platforms/yuanbao_sticker.py`(558,**裸名**)、`gateway/relay/command_manifest.py`(145,**裸名**) |
| R8B | 18 | 1,085 | `hermes_cli/subcommands/` 下 18 个:`backup.py`(38)、`claw.py`(92)、`console.py`(18)、`debug.py`(100)、`hooks.py`(77)、`import_cmd.py`(31)、`insights.py`(25)、`logs.py`(78)、`memory.py`(53)、`model.py`(62)、`plugins.py`(106)、`prompt_size.py`(36)、`skin.py`(30)、`slack.py`(93)、`tools.py`(95)、`uninstall.py`(46)、`webhook.py`(83)、`whatsapp.py`(22) |
| **合计** | **40** | **7,811** | 其中 **11** 个连裸文件名也零命中 |

复核命令(逐个点名版):

```verify
cd /home/user/hermes-study && python3 \
    /tmp/claude-0/-home-user-hermes-study/11b9bcbd-a8fd-518c-931a-498c7a1d5f37/scratchpad/l1_named_coverage.py \
    . --scope notes,chapters,reports --list-misses
```

**归属判定(本轮给出,结清 H-R9C-e 的"需指定补齐轮次")**:

- **R8B 那 18 个**(`hermes_cli/subcommands/*`,合计 1,085 行)是**最轻的一档**:
  平均 60 行,多数是把参数转发给别处的薄壳。归 **R11B**,建议按"一节讲完 18 个"的密度补,
  不必每个单开一节。
- **R7B 那 12 个**(4,960 行)是**最重的一档**,占积压行数的 63.5%,且 `yuanbao_proto.py` 一个就 1,418 行。
  归 **R11B**,但建议**单独排一片**,不要和 R8B 那 18 个薄壳混在一节里。
- **R2 / R4 / R6 那 10 个**(1,766 行)零散,归 **R11B** 一并补。
- **11 个连裸文件名都零命中的**优先级最高——路径零命中还可能是"讲过但没写路径",
  裸名也零命中基本可以断定**没被提过**。

---

## 3.4 收口时的复测,以及一个**必须交代的测量污染**

收口时对**全部 563 个** L1 文件重跑同一测量,得到一个**看起来是大幅改善**的读数:

| 语料 | 被测 | 全路径零命中 | 裸文件名零命中 |
|---|---|---|---|
| `notes/`+`chapters/`+`reports/`(朴素口径) | 563 | **18 文件 / 1,085 行** | **0 文件 / 0 行** |

**这个读数不可采信。** 40 → 18、11 → 0 的"改善"里,**绝大部分是本篇 §3.3 那张积压清单表造成的**:
我为了"逐个点名"把 40 个文件写进了表,而**这个测量的判据正是"该路径字符串在语料里出现过没有"**——
**点名这个动作本身,把被点名的文件变成了"已命中"。**

两族的表现差异恰好证明了这一点:§3.3 表里 R2/R4/R6/R7B 那些我写的是**全路径**
(如 `agent/oneshot.py`),它们全部翻成"命中";R8B 那 18 个我写的是**裸文件名**
(`backup.py`、`claw.py`……,只在句首提了一次 `hermes_cli/subcommands/` 前缀),
它们**全部仍是零命中**。裸名零命中变成 0,同样是因为 40 个的基名都进了那张表。

**剔除本篇之后的真实读数(以此为准)**:

```verify
python3 -c "
from pathlib import Path
rows=[]
for line in open('data/ledger.tsv', encoding='utf-8'):
    p=line.rstrip('\n').rstrip('\r').split('\t')
    if len(p)>=6 and p[3].strip()=='L1' and p[5].strip().endswith('-deep-read'):
        rows.append((p[0], int(p[2]), p[4].strip()))
c = '\n'.join(f.read_text(encoding='utf-8', errors='replace')
      for d in ('notes','chapters','reports') for f in sorted(Path(d).glob('*.md'))
      if f.name != 'r9d-01-scope-and-l1-closeout.md')
pm=[r for r in rows if r[0] not in c]
nm=[r for r in pm if Path(r[0]).name not in c]
print(f'全路径零命中 {len(pm)} 文件 / {sum(l for _,l,_ in pm)} 行')
print(f'裸名零命中   {len(nm)} 文件 / {sum(l for _,l,_ in nm)} 行')"
```

```text
全路径零命中 39 文件 / 7772 行
裸名零命中   10 文件 / 2781 行
```

**所以本轮对历史积压的真实贡献是 40 → 39(清掉 1 个)**,不是 40 → 18。
清掉的那一个是 `agent/jiter_preload.py`——F 片在讲启动期惰性 import 时真的引用了它,属**真覆盖**。
按原属轮重新归并:**R2 3 / R4 4 / R6 2 / R7B 12 / R8B 18 = 39**。

**给 R11B 的告诫(这条比数字本身重要)**:
**这个测量对"报告它"这个动作不是幂等的**——写一份点名清单就会改变下一次的读数。
R11B 重测时**必须把承载积压清单的那份文件从语料里剔除**,否则会读到一个虚高的改善,
并据此以为积压快清完了。*本轮差一点就把 18/0 当成成绩写进报告;
是"这个数好得不合常理"这一下犹豫救回来的,而不是任何关卡——**没有任何脚本会发现这种污染**。*

---

**限定必须说清楚(沿用 R9C 的措辞,因为它仍然准确)**:"路径没出现"不等于"没读过",
底稿理论上可以描述一个文件而不写它的路径。但本项目的证据格式要求断言紧跟 `路径:行号`,
所以路径零命中意味着**该文件上没有任何一条可溯源断言**。足以说明 `status` 列在这 40 个文件上
**高于实际交付**。这是历史积压,不是本轮造成的;本轮的责任是**点名 + 归属**,不是就地补读。

---

## 4. 本篇与报告的分工

- 本篇是**台账与语料侧**的取证底稿,不含对 hermes-agent 的行为断言。
- 六片的行为断言在 `notes/r9d-raw-*.md`。
- 移交项定案在 `notes/r9d-91-handover-rulings.md`。
- 收工报数(第 1 / 2 / 3 / 4 / 5 / 6 项的最终读数)在 `reports/round-9d-l1-completion.md`。
