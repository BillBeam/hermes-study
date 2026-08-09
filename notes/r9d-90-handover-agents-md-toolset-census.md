# r9d-90 · 移交项取证组 C —— H-R9A-g:`AGENTS.md` toolset 清单的文档缺口普查

> 基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(下称 `863e313`)。
> 本底稿只做一件事:把 R9A 留下的「AGENTS.md 的 toolset 键清单 vs 代码」这条移交项查到能定案。
> 术语锚定:**toolset(工具集)** = hermes-agent 里把若干个模型可调用工具(tool)打成一包的命名单元,
> 平台适配器与配置界面按「包」而不是按「单个工具」开关;**键(key)** 指这个包在字典里的名字,
> 如 `browser`、`hermes-telegram`。

---

## 0. 本轮结论速览

| 项 | R9A 的说法 | 本轮实测 | 处置 |
|---|---|---|---|
| 锚点 | AGENTS.md 的 971–974 行 | 清单实为 **971–975**(五行),归 `AGENTS.md:964` 的 `## Toolsets` 标题管 | 锚点**改述**(漏了末行) |
| 文档侧键数 | 30 | **30** ✅ | 维持 |
| 代码侧键数 | 58 | **58** ✅ | 维持 |
| 「文档有、代码无」 | 3 | **3**(`messaging` / `moa` / `rl`)✅ | 维持 |
| 「代码有、文档无」 | **28** | **31** ❌ | **改判**(R9A 用 58−30 直接相减,忘了那 30 里有 3 个已不在代码中;正确算式是 58−(30−3)=31) |
| 记号 | R9A 未对漏列项定号 | 漏列项 **拆成两类**:24 个 `hermes-*` 平台束 = **◇**;7 个能力 toolset = **▲** | 见 §5 |

**一句话**:R9A 报的「漏 28」既数错了(应为 31),也把两件性质完全不同的事混成了一件——
其中 **24 个是文档自己在上一段就分出去讲的平台束**,7 个才是真正的文档腐烂。

---

## 1. 原移交项复述

R9A 移交项 H-R9A-g:锚点写作「AGENTS.md 的 971–974 行」的 toolset 清单;现象是「文档列 30 个键、
代码有 58 个,文档还漏 28 个」;R9A 只判定了**文档有而代码无**的 3 个(`messaging`、`moa`、`rl`),
**漏列的那一半(28 个)未判**。本轮补齐该判定。

---

## 2. 锚点核对

### 2.1 清单的真实范围是 971–975,不是 971–974

`AGENTS.md:971 @ 863e313`

> Current toolset keys: `browser`, `clarify`, `code_execution`, `cronjob`,
> `debugging`, `delegation`, `discord`, `discord_admin`, `feishu_doc`,
> `feishu_drive`, `file`, `homeassistant`, `image_gen`, `kanban`, `memory`,
> `messaging`, `moa`, `rl`, `safe`, `search`, `session_search`, `skills`,
> `spotify`, `terminal`, `todo`, `tts`, `video`, `vision`, `web`, `yuanbao`.

第 975 行(`spotify` … `yuanbao`)是清单的**最后一行**,句号在此。R9A 的 `971-974`
**截掉了 6 个键**(`spotify`、`terminal`、`todo`、`tts`、`video`、`vision`、`web`、`yuanbao`
中落在第 975 行的那 8 个,减去 974 行末的部分),下一轮若照 `971-974` 去 `sed` 会少数出 8 个键。
本轮起锚点一律写 **`AGENTS.md:971-975`**。

### 2.2 这段清单归哪个标题管

`AGENTS.md:964 @ 863e313`

> ## Toolsets

节的完整边界:`AGENTS.md:964`(标题)到 `AGENTS.md:979`(最后一句正文),
`AGENTS.md:981` 是分隔线 `---`、`AGENTS.md:983` 是下一个标题 `## Delegation (\`delegate_task\`)`。
按本项目规矩(判定一条文档断言要把整段一并判定、并确认归哪个标题管),
`## Toolsets` 这一节**总共四段正文**,清单只是第二段。四段全判见 §5、§6。

节内前一段(第一段)是理解清单口径的关键:

`AGENTS.md:966 @ 863e313`

> All toolsets are defined in `toolsets.py` as a single `TOOLSETS` dict.
> Each platform's adapter picks a base toolset (e.g. Telegram uses
> `"messaging"`); `_HERMES_CORE_TOOLS` is the default bundle most
> platforms inherit from.

节内最后一段:

`AGENTS.md:977 @ 863e313`

> Enable/disable per platform via `hermes tools` (the curses UI) or the
> `tools.<platform>.enabled` / `tools.<platform>.disabled` lists in
> `config.yaml`.

---

## 3. 重数两边

### 3.1 代码侧的权威定义

权威定义是仓库根 `toolsets.py` 里的模块级字面量 `TOOLSETS`,**起于第 101 行、止于第 615 行**
(AST 的 `lineno` / `end_lineno`,不 import 不执行)。

`toolsets.py:101 @ 863e313`

```
TOOLSETS = {
    # Basic toolsets - individual tool categories
    "web": {
        "description": "Web research and content extraction tools",
        "tools": ["web_search", "web_extract"],
        "includes": []  # No other toolsets included
    },
```

`toolsets.py:610 @ 863e313`

```
    "hermes-gateway": {
        "description": "Gateway toolset - union of all messaging platform tools",
        "tools": [],
        "includes": ["hermes-telegram", "hermes-discord", "hermes-whatsapp", "hermes-slack", "hermes-signal", "hermes-bluebubbles", "hermes-homeassistant", "hermes-email", "hermes-sms", "hermes-mattermost", "hermes-matrix", "hermes-dingtalk", "hermes-feishu", "hermes-wecom", "hermes-wecom-callback", "hermes-weixin", "hermes-qqbot", "hermes-webhook", "hermes-yuanbao"]
    }
}
```

**注意**:`TOOLSETS` 并非「所有 toolset 的全集」——运行期还有两条注入路径,详见 §6.1。
但**文档那句话说的就是这个字典**,所以拿它做对照面是正确的对照。

### 3.2 可重跑的双侧提取 + 差集(一条命令给出全部四个数)

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'PY'
import ast, re
tree = ast.parse(open('toolsets.py').read())
code = next([k.value for k in n.value.keys]
            for n in tree.body
            if isinstance(n, ast.Assign)
            and any(getattr(t, 'id', None) == 'TOOLSETS' for t in n.targets))
doc = re.findall(r'`([a-z0-9_-]+)`',
                 ' '.join(open('AGENTS.md').read().split('\n')[970:975]))
print('doc =', len(doc), '| code =', len(code))
print('doc-only =', sorted(set(doc) - set(code)))
miss = [k for k in code if k not in doc]
print('code-only =', len(miss))
print('  platform bundles:', [k for k in miss if k.startswith('hermes-')])
print('  capability keys :', [k for k in miss if not k.startswith('hermes-')])
PY
```

实跑输出(本容器,`863e313`):

```text
doc = 30 | code = 58
doc-only = ['messaging', 'moa', 'rl']
code-only = 31
  platform bundles: ['hermes-acp', 'hermes-api-server', 'hermes-cli', 'hermes-cron', 'hermes-telegram', 'hermes-discord', 'hermes-whatsapp', 'hermes-slack', 'hermes-signal', 'hermes-bluebubbles', 'hermes-homeassistant', 'hermes-email', 'hermes-mattermost', 'hermes-matrix', 'hermes-dingtalk', 'hermes-feishu', 'hermes-weixin', 'hermes-qqbot', 'hermes-wecom', 'hermes-wecom-callback', 'hermes-yuanbao', 'hermes-sms', 'hermes-webhook', 'hermes-gateway']
  capability keys : ['x_search', 'video_gen', 'bfl', 'computer_use', 'context_engine', 'project', 'coding']
```

不想跑 Python 的纯 shell 复核(只核文档侧 30):

```verify
cd /home/user/hermes-agent && sed -n '971,975p' AGENTS.md | grep -o '`[a-z0-9_-]*`' | tr -d '`' | sort | wc -l
```

> 提取式的正则**特意写成 `[a-z0-9_-]+` 而不是 `[a-z_]+`**:代码侧 24 个键名带连字符
> (`hermes-cli`),若用不含 `-` 的模式去扫文档,会因「文档里本来就一个带连字符的反引号词都没有」
> 而给出**同样是 30** 的结果,看不出差别。实测两种模式在文档侧输出完全一致(`diff` 无差),
> 这个一致本身就是证据:**文档那 30 个键里,一个 `hermes-*` 都没有。**

### 3.3 文档侧 30 个键(逐个列出)

`browser`、`clarify`、`code_execution`、`cronjob`、`debugging`、`delegation`、`discord`、
`discord_admin`、`feishu_doc`、`feishu_drive`、`file`、`homeassistant`、`image_gen`、`kanban`、
`memory`、`messaging`、`moa`、`rl`、`safe`、`search`、`session_search`、`skills`、`spotify`、
`terminal`、`todo`、`tts`、`video`、`vision`、`web`、`yuanbao`。(字母序,与文档一致)

### 3.4 代码侧 58 个键(逐个列出,按源码出现序 + 行号)

**能力 toolset(34 个,`toolsets.py:103–380`)**:
`web`(103)、`search`(109)、`x_search`(115)、`vision`(128)、`video`(134)、`image_gen`(140)、
`video_gen`(146)、`bfl`(158)、`computer_use`(177)、`terminal`(187)、`skills`(193)、
`browser`(199)、`cronjob`(211)、`file`(218)、`tts`(224)、`todo`(230)、`memory`(236)、
`context_engine`(242)、`session_search`(248)、`project`(254)、`clarify`(260)、
`code_execution`(266)、`delegation`(272)、`homeassistant`(281)、`kanban`(287)、`discord`(307)、
`discord_admin`(313)、`yuanbao`(319)、`feishu_doc`(331)、`feishu_drive`(337)、`spotify`(346)、
`debugging`(358)、`safe`(364)、`coding`(374)。

**平台束(24 个,`toolsets.py:407–610`)**:
`hermes-acp`(407)、`hermes-api-server`(426)、`hermes-cli`(463)、`hermes-cron`(469)、
`hermes-telegram`(480)、`hermes-discord`(486)、`hermes-whatsapp`(495)、`hermes-slack`(501)、
`hermes-signal`(507)、`hermes-bluebubbles`(513)、`hermes-homeassistant`(519)、`hermes-email`(525)、
`hermes-mattermost`(531)、`hermes-matrix`(537)、`hermes-dingtalk`(543)、`hermes-feishu`(549)、
`hermes-weixin`(561)、`hermes-qqbot`(567)、`hermes-wecom`(573)、`hermes-wecom-callback`(579)、
`hermes-yuanbao`(585)、`hermes-sms`(598)、`hermes-webhook`(604)、`hermes-gateway`(610)。

34 + 24 = 58。✅

### 3.5 三个数的核对结论

- 文档 30 ✅、代码 58 ✅ —— R9A 无误。
- **漏列 28 ❌,实为 31。** R9A 的算式显然是 `58 − 30 = 28`,但那 30 里有 3 个
  (`messaging`/`moa`/`rl`)**已不在代码中**,不能抵扣。正确算式:
  两侧交集 27,`58 − 27 = 31`。
  这是个安静的错——它比真值小,**方向是"少报缺口"**,所以复核者不会因为「怎么这么多」而起疑。

---

## 4. 逐个判定那 31 个漏列项(按类归并)

31 个漏列项**干净地分成两类,没有第三类**(分类依据:键名是否以 `hermes-` 开头;
上面 §3.2 的命令直接按这个谓词打印两组,两组之和 = 31,可复核)。

### 4.1 A 类:24 个平台束 `hermes-*` —— 文档写作时就已存在,是**有意不列**

代表:`hermes-telegram`。

`toolsets.py:480 @ 863e313`

```
    "hermes-telegram": {
        "description": "Telegram bot toolset - full access for personal use (terminal has safety checks)",
        "tools": _HERMES_CORE_TOOLS,
        "includes": []
    },
```

**完整名单**:`hermes-acp`、`hermes-api-server`、`hermes-cli`、`hermes-cron`、`hermes-telegram`、
`hermes-discord`、`hermes-whatsapp`、`hermes-slack`、`hermes-signal`、`hermes-bluebubbles`、
`hermes-homeassistant`、`hermes-email`、`hermes-mattermost`、`hermes-matrix`、`hermes-dingtalk`、
`hermes-feishu`、`hermes-weixin`、`hermes-qqbot`、`hermes-wecom`、`hermes-wecom-callback`、
`hermes-yuanbao`、`hermes-sms`、`hermes-webhook`、`hermes-gateway`。

**用途**:它们不是「能力」,而是**每个平台的默认工具包**——平台适配器启动时按平台名查到一个
默认 toolset,再由 `hermes tools` 的保存结果去收窄。绝大多数直接复用 `_HERMES_CORE_TOOLS`
(见上面 `"tools": _HERMES_CORE_TOOLS`),少数在其上加平台原生工具(如 `hermes-discord`
额外加 `discord`、`discord_admin`)。`hermes-gateway` 是它们的并集(§3.1 的 `includes` 长列表)。

**为什么没写进清单——不是遗漏,是分类**。证据是历史快照:
文档这一段最后一次改动是 `b7bd17710`(2026-05-05,`docs(AGENTS.md): add curator/cron/delegation/toolsets, fix plugin tree (#20226)`)。
把那一刻的 `toolsets.py` 取出来重数:

```verify
cd /home/user/hermes-agent && git log -L 971,975:AGENTS.md --format='%h %ad %s' --date=short 2>/dev/null | grep -E '^[0-9a-f]{7,} ' | head -3
```

```verify
cd /home/user/hermes-agent && git show b7bd17710:toolsets.py > /tmp/ts_old.py && \
HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'PY'
import ast, re
def keys(p):
    t = ast.parse(open(p).read())
    for n in t.body:
        if isinstance(n, ast.Assign) and any(getattr(x, 'id', None) == 'TOOLSETS' for x in n.targets):
            return [k.value for k in n.value.keys]
old = keys('/tmp/ts_old.py')
doc = re.findall(r'`([a-z0-9_-]+)`',
                 ' '.join(open('/home/user/hermes-agent/AGENTS.md').read().split('\n')[970:975]))
print('keys at b7bd17710 =', len(old))
print('non-hermes-* keys then =', len([k for k in old if not k.startswith('hermes-')]))
print('doc set == non-hermes set at that commit?',
      sorted(doc) == sorted(k for k in old if not k.startswith('hermes-')))
PY
```

实跑输出:

```text
keys at b7bd17710 = 54
non-hermes-* keys then = 30
doc set == non-hermes set at that commit? True
```

也就是说:**文档写下的那 30 个键,恰好等于当时 `TOOLSETS` 里全部非 `hermes-*` 的键,一个不多一个不少。**
作者不是随手列了一部分——他做了一次**完整枚举**,枚举的对象是「能力 toolset」这个子类,
而 `hermes-*` 平台束被有意排除在外(它们由紧邻的上一段"Each platform's adapter picks a base toolset"负责交代)。
这条证据决定了 A 类的记号:**不是 ▲,是 ◇**(见 §5)。

### 4.2 B 类:7 个能力 toolset —— **文档写完之后才加进代码的,是真正的腐烂**

**完整名单与加入时间**(`git log -S'"<key>": {' -- toolsets.py`,取最早一条):

| 键 | 加入日期 | 引入 commit(标题节选) | 用途一句话 | 声明式锚点 |
|---|---|---|---|---|
| `video_gen` | 2026-05-13 | `feat(video_gen): unified video_generate tool ...` (#25126) | 统一的视频生成工具集 | `toolsets.py:154` 的 `"tools": ["video_generate", "xai_video_edit", "xai_video_extend"],` |
| `x_search` | 2026-05-16 | `feat(x_search): gated X (Twitter) search tool ...` (#26763) | 用 xAI 内建 `x_search` 只读检索 X(Twitter)帖子 | `toolsets.py:124`:`"tools": ["x_search"],` |
| `context_engine` | 2026-05-23 | `fix: expose context engine tools with saved toolsets` | 由当前 context engine 在运行期注入工具的**空壳** toolset | `toolsets.py:243` 的 `"description": "Runtime tools exposed by the active context engine",` |
| `coding` | 2026-06-10 | `feat(agent): coding-context posture ...` (#43316) | 面向写代码的姿态包(文件/终端/搜索/文档/skills/todo/delegate/vision/browser) | `toolsets.py:374`:`"coding": {` |
| `project` | 2026-06-25 | `feat(tools): add project workspace tools` | 桌面版命名工作区的创建/切换(**仅 GUI 会话**) | `toolsets.py:256` 的 `"tools": ["project_list", "project_create", "project_switch"],` |
| `bfl` | 2026-07-30 | `nous portal video gen` (#74963) | Black Forest Labs FLUX 3 视频生成(提交返回 job id,模型轮询取结果) | `toolsets.py:166` 的 `"tools": [` |
| `computer_use` | 2026-04-23 加 → 04-28 回滚 → 之后再加 | `feat(computer-use): cua-driver backend ...` / `revert: ...(#16927)` | 经 cua-driver 的后台桌面控制(截屏/鼠标/键盘) | `toolsets.py:183`:`"tools": ["computer_use"],` |

复核加入时间的命令:

```verify
cd /home/user/hermes-agent && for k in x_search video_gen bfl computer_use context_engine project coding; do \
  printf '%-16s ' "$k"; git log --format='%h %ad %s' --date=short -S"\"$k\": {" -- toolsets.py | tail -1; done
```

**`computer_use` 是这七个里唯一需要单独解释的**:它的最早引入(2026-04-23)**早于**文档写作
(2026-05-05),但 2026-04-28 的 revert 把它从 `TOOLSETS` 里摘掉了,所以 2026-05-05 那一刻
它确实**不在**字典里(上面 §4.1 的快照脚本已经用集合相等证明了这一点:文档那 30 个 = 当时
全部非 `hermes-*` 键,若 `computer_use` 当时在,等式就不成立)。它是**回滚后重新落地、文档没跟上**,
性质与另外六个一致,不构成"写作时就漏"。

代表性摘录(空壳型 toolset,最容易让读者误判为"没用的键"):

`toolsets.py:242 @ 863e313`

```
    "context_engine": {
        "description": "Runtime tools exposed by the active context engine",
        "tools": [],
        "includes": []
    },
```

`toolsets.py:254 @ 863e313`

```
    "project": {
        "description": "Desktop Projects — create/switch named workspaces (GUI sessions only)",
        "tools": ["project_list", "project_create", "project_switch"],
        "includes": []
    },
```

**没有一个是"内部键"或"已废弃"**。判定依据:这 7 个里有 6 个同时出现在
`hermes_cli/tools_config.py` 的 `CONFIGURABLE_TOOLSETS`(即 `hermes tools` 那个 curses 界面
逐行列出来给用户勾选的清单)里,是**面向用户的一等能力**;唯一不在其中的是 `coding`,
它是"姿态包"(由 CLI/TUI/desktop/ACP 的 coding-context 选用),同样不是内部实现细节。

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "
import ast
t = ast.parse(open('hermes_cli/tools_config.py').read())
for n in t.body:
    if isinstance(n, ast.Assign) and any(getattr(x,'id',None)=='CONFIGURABLE_TOOLSETS' for x in n.targets):
        keys = [e.elts[0].value for e in n.value.elts]
        print('CONFIGURABLE_TOOLSETS =', len(keys), 'at line', n.lineno)
        for k in ['x_search','video_gen','bfl','computer_use','context_engine','project','coding']:
            print(' ', k, k in keys)
"
```

实跑输出:

```text
CONFIGURABLE_TOOLSETS = 27 at line 96
  x_search True
  video_gen True
  bfl True
  computer_use True
  context_engine True
  project False
  coding False
```

> 修正上一段的措辞:实测是 **5 个**在 `CONFIGURABLE_TOOLSETS` 里(`x_search`、`video_gen`、
> `bfl`、`computer_use`、`context_engine`),`project` 与 `coding` 不在。
> `project` 不在的原因代码里写了——它只对 GUI 会话有意义(见上面 `(GUI sessions only)` 的
> description,以及 `toolsets.py:60-64` 那段解释为什么 project 工具**故意**不进 `_HERMES_CORE_TOOLS`)。
> 结论不变:**没有一个是废弃键或内部占位键**,7 个全是真实在用的能力。

`toolsets.py:60 @ 863e313`

```
    # NOTE: the desktop Project tools (project_list/create/switch) are
    # deliberately NOT here. They only make sense where a GUI can follow the
    # move, so they live in the `project` toolset and are enabled solely by the
    # GUI gateway (tui_gateway/server.py::_load_enabled_toolsets) — keeping them
    # off every CLI/messaging/cron schema (narrow waist).
```

---

## 5. 记号判定:整体不是一条 ▲,而是「1 条 ◇ + 1 条 ▲」

本项目规矩:**字面为真就不是 ▲**。所以关键在于 `AGENTS.md:971` 那句话的**措辞**。

原文起手四个字是 **`Current toolset keys:`** ——不是 `e.g.`、不是 `including`、不是 `some of`。
`Current` 是一个**关于当下状态的完整性声明**:它承诺"这就是现在的键"。
再加上 §4.1 证明的历史事实(写作当刻它**确实是**某个明确子类的完整枚举),
可以判定:**作者把这句写成了枚举,不是举例**。因此凡是让这个枚举不再成立的差异,都构成矛盾。

但差异有两类,措辞对它们的约束强度不同:

### 5.1 A 类(24 个 `hermes-*`)—— **◇,不是 ▲**

理由:文档在**紧邻的上一段**(`AGENTS.md:967-969`)已经把"平台适配器各挑一个 base toolset"
单独讲了一遍,清单那句的隐含论域因此是"能力 toolset"。§4.1 用集合相等证明了这个隐含论域
**在写作时被严格执行**(30 = 全部非 `hermes-*` 键)。也就是说:
文档**没有**声称 `hermes-telegram` 不存在,也**没有**给出与代码矛盾的内容;
它只是**没有把这套命名规则写出来**。

按本项目定义,「代码有、文档无」= **◇**。

> 但这条 ◇ 有实际代价,值得写进成品章:**读者无从知道 `hermes-*` 这套键的存在与命名规则**。
> 一个照着 AGENTS.md 去配置的人,在 `config.yaml` 里看到 `platform_toolsets: {cli: [hermes-cli]}`
> 时,会在文档里**一个字都查不到** `hermes-cli` 是什么。

### 5.2 B 类(7 个能力 toolset)—— **▲**

理由:这 7 个**就在文档自己划定的论域内**(它们是能力 toolset,不是平台束),
而 `Current toolset keys:` 声称枚举完整。少了它们,这句话**字面为假**。
腐烂的机制也清楚:文档 2026-05-05 定稿后**再没被碰过**,而代码在此后三个月里加了 7 个键。

**这是同一条句子上的第二个 ▲**——R9A 已判的 `messaging`/`moa`/`rl` 是"文档列了、代码删了"
(反向腐烂),本条是"代码加了、文档没跟"(正向腐烂)。两者可以合并计为**同一处 ▲**
(同一句话、同一次失效),也可以分别计。**本底稿建议计为 1 条 ▲**,理由是跨轮 ▲ 计数的
语义是"地图上有几处指错路",这句话指错的是同一处。若主线倾向按"错误方向"分计,
请在报告里显式说明口径,避免与 R9A 的计数重复。

### 5.3 为什么不是 ◎

◎ 的定义是"文档成立但显著保守"(如"20+ 平台"而实为 24)。这里文档写的是**确定列表**,
不是带下限的模糊量词,不存在"保守但为真"的读法。**排除 ◎。**

---

## 6. 同节其余三段的连带判定(规矩要求整段判定)

R9A 只判了清单那一句。按本项目规矩(「判定一条文档断言时,必须把它所在的整句/整段一并判定」),
`## Toolsets` 节余下三段也须落判,否则它们会以"这里已经查过了"的名义活下来。

### 6.1 ▲ —— "All toolsets are defined in `toolsets.py` as a single `TOOLSETS` dict"(`AGENTS.md:966`)

**不成立。** 代码自己有两条把 `TOOLSETS` 之外的 toolset 算进来的路径:

(a) 运行期可以直接往字典里塞:

`toolsets.py:930 @ 863e313`

```
    TOOLSETS[name] = {
        "description": description,
        "tools": tools or [],
        "includes": includes or []
    }
```

(b) 插件注册的 toolset **根本不在**这个字典里,代码明说了:

`toolsets.py:822 @ 863e313`

```
    """Return toolset names registered by plugins (from the tool registry).

    These are toolsets that exist in the registry but not in the static
    ``TOOLSETS`` dict — i.e. they were added by plugins at load time.
    """
```

而"有哪些 toolset"这个问题的**权威回答者**是 `get_toolset_names()`,它明确把三样东西并起来:

`toolsets.py:881 @ 863e313`

```
    names = set(TOOLSETS.keys())
    aliases = _get_registry_toolset_aliases()
    for ts_name in _get_plugin_toolset_names():
        for alias, canonical in aliases.items():
            if canonical == ts_name and alias not in TOOLSETS:
                names.add(alias)
                break
        else:
            names.add(ts_name)
```

即:静态 `TOOLSETS` + 插件注册的 toolset + MCP 服务器的 toolset 别名。
所以 "**All** toolsets are defined in `toolsets.py`" 字面为假 → **▲**。
(顺带解释了为什么 58 这个数只是"静态键数",不是"用户能看到的 toolset 数"。)

### 6.2 ▲ —— "e.g. Telegram uses `\"messaging\"`"(`AGENTS.md:967-968`)

**不成立,而且从写下那天起就不成立。** 平台默认 toolset 由一张表定死:

`hermes_cli/platforms.py:23 @ 863e313`

```
    ("telegram",       PlatformInfo(label="📱 Telegram",        default_toolset="hermes-telegram")),
```

Telegram 的 base toolset 是 `hermes-telegram`(§4.1 已给出其定义:`"tools": _HERMES_CORE_TOOLS`),
**不是** `messaging`,且 `hermes-telegram` 的 `includes` 是空列表,不经由 `messaging` 间接引用。

历史复核(取文档定稿那一刻的同一张表):

```verify
cd /home/user/hermes-agent && git show b7bd17710:hermes_cli/platforms.py | grep -n '"telegram"' | head -2
```

输出仍是 `default_toolset="hermes-telegram"` —— **文档写作当刻这句就是错的**,
不是后来腐烂的。这是一条独立的 ▲(与 §5.2 那条不是同一处:一个指错了机制,一个漏了枚举项)。

> 这条 ▲ 与 §5.1 那条 ◇ 互为因果:正因为文档在这里把平台束的名字写错成了 `messaging`,
> 读者**既不知道 `hermes-*` 存在**(◇),**又被给了一个错的替代品**(▲)。
> 单看清单会以为"平台束只是没写";把这一段一起判,才看得出文档对这套机制的描述整体失真。

### 6.3 ▲ —— "`tools.<platform>.enabled` / `tools.<platform>.disabled` lists in `config.yaml`"(`AGENTS.md:978`)

**配置路径不存在。** 真实路径是根键 `platform_toolsets`,值是**一个平铺的 toolset 名字列表**,
没有 `enabled` / `disabled` 两个子键:

`hermes_cli/tools_config.py:8 @ 863e313`

```
Saves per-platform tool configuration to ~/.hermes/config.yaml under
the `platform_toolsets` key.
```

`hermes_cli/tools_config.py:2232 @ 863e313`

```
    platform_toolsets = config.get("platform_toolsets") or {}
    toolset_names = platform_toolsets.get(platform)
```

**负结论的搜索面**(按项目规矩写明):
- 在 `hermes_cli/config_defaults.py` 的 `DEFAULT_CONFIG` 字面量里 AST 取根键,
  存在 `tools`(第 2339 行)但**不存在** `platform_toolsets`;`tools` 这个根键的内容是
  `tool_search`(工具搜索/延迟披露)的参数,与 per-platform 无关(实读 2339–2375 行)。
- 全仓 `grep -rn 'get("tools"' --include=*.py .`(排除 `tests/`、`__pycache__`)共 20 余处,
  逐条看过,全部是**模型请求体里的 `tools` 数组**或 **MCP server 配置的 `tools` 子表**,
  没有一处是"按平台名去 `tools` 下取 enabled/disabled"。
- 全仓 `grep -rn "tools\.<platform>\|platform_toolsets" --include=*.md --include=*.mdx .`
  只有 `AGENTS.md:978` 一处用 `tools.<platform>` 措辞;`website/docs/` 侧
  (`user-guide/configuration.md:740`、`getting-started/quickstart.md:105`、
  `user-guide/features/acp.md:275`)一律写 `platform_toolsets`。
  **即作者自绘地图内部也不自洽:官网文档写对了,AGENTS.md 写错了。**

```verify
cd /home/user/hermes-agent && grep -rn "tools\.<platform>\|platform_toolsets" --include=*.md --include=*.mdx . | head
```

`platform_toolsets` **之后**还有一层全局关闭开关 `agent.disabled_toolsets`
(`hermes_cli/config_defaults.py:241`,默认 `[]`),这也是 AGENTS.md 未提的(→ 归入 §5.1 同一条 ◇)。

### 6.4 成立 —— "`_HERMES_CORE_TOOLS` is the default bundle most platforms inherit from"

字面为真。24 个平台束里绝大多数直接 `"tools": _HERMES_CORE_TOOLS`
(`hermes-cli`/`hermes-cron`/`hermes-telegram`/`hermes-whatsapp` 等),
少数在其上做加法(`hermes-discord`)或另起一套(`hermes-acp`、`hermes-api-server`、`hermes-webhook`)。
"most" 字面成立,**不判 ▲、不判 ◎**(它没有给出可被超越的数量下限)。

---

## 7. 旁证:同一份"toolset 缺省关闭集"在代码内部也已腐烂(◇ 之外的额外发现)

不属于本移交项,但取证过程中撞见,记下以免下一轮重查。

`cron/scheduler.py` 的 docstring 声称缺省关闭集是 `{moa, homeassistant, rl}`:

`cron/scheduler.py:235 @ 863e313`

```
    _DEFAULT_OFF_TOOLSETS ({moa, homeassistant, rl}) are removed by
    ``_get_platform_tools`` for unconfigured platforms, so fresh installs
    get cron WITHOUT ``moa`` by default (issue reported by Norbert —
    surprise $4.63 run).
```

而真实定义里 `moa` 和 `rl` **都不在**(它们已连 toolset 都不是了,见 §3.2 的 `doc-only`):

`hermes_cli/tools_config.py:156 @ 863e313`

```
_DEFAULT_OFF_TOOLSETS = {"homeassistant", "spotify", "discord", "discord_admin", "video", "video_gen", "x_search", "a2a"}
```

**性质**:代码内注释与代码矛盾(不是 README/AGENTS.md/website/docs,故按本项目定义**不计入 ▲**,
▲ 专指作者自绘地图那三处)。但它与 H-R9A-g 同源——`moa`/`rl` 被删除时,
**AGENTS.md 和这条 docstring 都没跟上**,说明删除那两个 toolset 的 PR 没有做引用面清理。
另注:`a2a` 出现在 `_DEFAULT_OFF_TOOLSETS` 里但**不是** `TOOLSETS` 的键(§3.4 名单无 `a2a`),
这一项本底稿**未取证**其来源(见 §9)。

---

## 8. 测试作为行为规格

`tests/test_toolsets.py` 是 toolset 机制的行为规格。实跑:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/test_toolsets.py
```

```text
Discovered 1 test files (~22 tests) under ['tests/test_toolsets.py']; running with -j 8
[100.0% |    22/~22 | ✓22 | ✗ 0] ✓ tests/test_toolsets.py (22✓, 1.5s)

=== Summary: 1 files, 22 tests passed, 0 failed (100% complete) in 1.5s (8 workers) ===
```

**1 个文件,22 passed,0 failed**,无跳过、无环境限制命中。

**关键的负结论:仓库里没有任何测试校验 AGENTS.md 的清单与 `TOOLSETS` 一致。**
搜索面:
- `grep -rl "AGENTS.md" tests/ --include=*.py` 得到 20 余个文件,再对这批文件
  `xargs grep -l "TOOLSETS\|get_toolset_names"` —— **零命中**。
  (那批文件里的 `AGENTS.md` 全部指"把项目里的 AGENTS.md 作为上下文文件喂给 agent"这个功能,
  与 toolset 清单无关。)
- `grep -rn "Current toolset keys\|toolset keys" --include=*.md --include=*.mdx .` 全仓
  **只有 `AGENTS.md:971` 一处**,即这份清单没有第二份副本需要一起维护。

```verify
cd /home/user/hermes-agent && grep -rl "AGENTS.md" tests/ --include=*.py | xargs grep -l "TOOLSETS\|get_toolset_names" 2>/dev/null; echo "exit=$? (无输出=无同步测试)"
```

这解释了腐烂为什么能持续三个月:**清单只有人工约定兜着,没有任何机器关卡**
——与本学习项目自己给引用校验升格为脚本关卡时给出的理由完全同构。

---

## 9. 未取证 / 推定

按强度如实标注。

| # | 事项 | 强度 | 锚点 / 说明 |
|---|---|---|---|
| U1 | `a2a` 出现在 `_DEFAULT_OFF_TOOLSETS` 但不是 `TOOLSETS` 的键,它是插件注册的 toolset 还是残留 | **未取证** | `hermes_cli/tools_config.py:156`:`_DEFAULT_OFF_TOOLSETS = {"homeassistant", "spotify", "discord", "discord_admin", "video", "video_gen", "x_search", "a2a"}` —— 本轮未追它的注册处 |
| U2 | 「A 类是有意排除而非遗漏」 | **静态对读 + 历史快照推出**,非作者自述 | 依据是集合相等(30 = 写作时全部非 `hermes-*` 键),这是很强的间接证据,但作者从未在文中写出"本清单不含平台束"这句话;若主线要求更强,只能去查 PR #20226 的描述(本容器离线,未做) |
| U3 | 运行期 `get_toolset_names()` 的实际返回数(含插件/MCP 别名) | **未实跑** | 需要加载插件与 MCP registry,本容器无 MCP 服务器配置;§6.1 的结论只依赖**静态代码路径**(`toolsets.py:881-889`),不依赖运行期数字 |
| U4 | `computer_use` 在 2026-04-28 revert 与再次落地之间的确切 commit | **部分取证** | `git log -S` 只取了最早一条;§4.2 的结论依赖的是"2026-05-05 那一刻它不在字典里",这一点已由 §4.1 的集合相等**直接证明**,不依赖 U4 |
| U5 | ▲ 计数口径(§5.2 建议合并计 1 条) | **待主线裁定** | 不是取证问题,是计数约定问题 |

---

## 10. 处置结论(可直接进移交/结论表)

**H-R9A-g:关闭并改述。**

1. **锚点改正**:`AGENTS.md:971-974` → **`AGENTS.md:971-975`**,归 `## Toolsets`(`AGENTS.md:964`)。
2. **数字改判**:「漏 28」→ **漏 31**(R9A 用 `58−30` 相减,未扣除 30 里已被代码删除的 3 个)。
3. **31 个漏列项判定完毕,分两类**:
   - **24 个 `hermes-*` 平台束 = ◇**(代码有、文档无)。有历史快照证明是**有意的分类排除**
     而非遗漏:文档定稿时 30 个键 == 当时全部非 `hermes-*` 键,集合相等。
   - **7 个能力 toolset = ▲**(`x_search`/`video_gen`/`bfl`/`computer_use`/`context_engine`/
     `project`/`coding`)。全部在文档定稿(2026-05-05)之后加入代码,落在文档自己划定的论域内,
     使 `Current toolset keys:` 字面为假。**没有一个是内部键或废弃键。**
4. **连带落判(本轮新增,原移交项未覆盖)**:同节另有 **3 条 ▲**——
   "All toolsets are defined in `toolsets.py`"(有插件与运行期注入路径)、
   "Telegram uses `messaging`"(实为 `hermes-telegram`,**写下当天即错**)、
   "`tools.<platform>.enabled`/`.disabled`"(实为 `platform_toolsets.<platform>` 平铺列表)。
   另 1 条成立不判(`_HERMES_CORE_TOOLS` … most platforms)。
5. **根因**:没有任何测试或脚本校验该清单与 `TOOLSETS` 的一致性(搜索面见 §8),
   全仓也只有这一份清单副本。

### 声明式锚点(供移交表/结论表直接引用)

| 事项 | 锚点 + 摘录 |
|---|---|
| 文档清单本体(971–975) | `AGENTS.md:971` 的 `Current toolset keys:` |
| 归属标题 | `AGENTS.md:964` 的 `## Toolsets` |
| 代码侧权威定义 | `toolsets.py:101`:`TOOLSETS = {` |
| 字典末尾(证明 58 的边界) | `toolsets.py:610` 的 `"hermes-gateway": {` |
| A 类代表(平台束) | `toolsets.py:480` 的 `"hermes-telegram": {` |
| B 类代表(文档后新增) | `toolsets.py:242` 的 `"context_engine": {` |
| §6.1 ▲ 的反证(插件 toolset 不在字典里) | `toolsets.py:881`:`names = set(TOOLSETS.keys())` |
| §6.2 ▲ 的反证(Telegram 真实 base) | `hermes_cli/platforms.py:23` 的 `default_toolset="hermes-telegram"` |
| §6.3 ▲ 的反证(真实配置键) | `hermes_cli/tools_config.py:2232`:`platform_toolsets = config.get("platform_toolsets") or {}` |
| §7 旁证(过期 docstring) | `cron/scheduler.py:235` 的 `_DEFAULT_OFF_TOOLSETS ({moa, homeassistant, rl}) are removed by` |
| §7 真实缺省关闭集 | `hermes_cli/tools_config.py:156`:`_DEFAULT_OFF_TOOLSETS = {"homeassistant", "spotify", "discord", "discord_admin", "video", "video_gen", "x_search", "a2a"}` |

### 主线可独立重跑的复核(三条,依次)

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'PY'
import ast, re
tree = ast.parse(open('toolsets.py').read())
code = next([k.value for k in n.value.keys]
            for n in tree.body
            if isinstance(n, ast.Assign)
            and any(getattr(t, 'id', None) == 'TOOLSETS' for t in n.targets))
doc = re.findall(r'`([a-z0-9_-]+)`',
                 ' '.join(open('AGENTS.md').read().split('\n')[970:975]))
assert len(doc) == 30 and len(code) == 58
miss = [k for k in code if k not in doc]
assert len(miss) == 31
assert len([k for k in miss if k.startswith('hermes-')]) == 24
assert len([k for k in miss if not k.startswith('hermes-')]) == 7
assert sorted(set(doc) - set(code)) == ['messaging', 'moa', 'rl']
print('OK 30/58/31 = 24 platform + 7 capability; doc-only = messaging/moa/rl')
PY
```

```verify
cd /home/user/hermes-agent && git show b7bd17710:toolsets.py > /tmp/ts_old.py && \
HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python - <<'PY'
import ast, re
t = ast.parse(open('/tmp/ts_old.py').read())
old = next([k.value for k in n.value.keys] for n in t.body
           if isinstance(n, ast.Assign) and any(getattr(x,'id',None)=='TOOLSETS' for x in n.targets))
doc = re.findall(r'`([a-z0-9_-]+)`',
                 ' '.join(open('/home/user/hermes-agent/AGENTS.md').read().split('\n')[970:975]))
assert sorted(doc) == sorted(k for k in old if not k.startswith('hermes-'))
print('OK doc set == non-hermes-* keys at doc-write commit b7bd17710 (2026-05-05)')
PY
```

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/test_toolsets.py && git status --porcelain && echo "BASELINE-CLEAN"
```

---

## 11. 基线只读确认

本节全部工作只用了读操作(`sed`/`awk`/`grep`/`ast.parse`/`git log`/`git show`),
未在基线执行任何写操作(无 commit / checkout / clean / stash,无 pip / npm)。
唯一有副作用的动作是跑测试,它写了 `test_durations.json`,而该文件被 `.gitignore:35` 忽略。

```verify
cd /home/user/hermes-agent && git log -1 --format=%H && git status --porcelain && echo "STATUS-EMPTY-ABOVE"
```

实跑输出:

```text
863e31318553cda8ad61df681d08175364d4164b
STATUS-EMPTY-ABOVE
```

`git status --porcelain` 输出为空,基线工作区干净。
