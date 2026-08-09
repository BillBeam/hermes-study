# r9a 底稿 · 90 —— 文档-代码定案(主线独立取证)

> 研究对象基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(只读)。
> 溯源约定:凡对代码行为的断言,**锚点单独成行、置于代码块/引用块之前**,格式 `路径:行号 @ 863e313`。
>
> 记号(CLAUDE.md):▲ = 文档所述与代码**矛盾**;◇ = 代码有、文档无;■ = 代码缺陷;
> **◎ = 文档成立但显著保守**。字面为真就不是 ▲。
>
> **本文是主线自己取证的部分**,不是子代理产出的转录。子代理的定案候选另见各自底稿,
> 经主线复核后并入本文 §3。

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

## 3. 一份**没有腐烂**的文档:`subagent-lifecycle-api.md`

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

## 3. 子代理定案候选(主线复核后并入)

*本节在各子代理底稿到货并经主线独立复核后填写。未经主线复核的条目不进本节。*
