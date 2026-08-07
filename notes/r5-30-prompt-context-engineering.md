# R5 底稿 · prompt 装配与上下文工程

结论:系统提示按缓存稳定性分三层装配;项目上下文文件"先到先得 + 动态截断 + 注入前威胁扫描";ContextEngine 以 select_context/on_turn_complete 双钩子终结"恒真 should_compress 蹭 compress 当回调"的滥用。

溯源约定:所有断言紧跟 `路径:行号 @ 863e313`(863e31318553cda8ad61df681d08175364d4164b),代码为逐字摘录(已实测行号)。hermes-agent 只读,本稿不修改任何源文件。

本簇 9 文件:`agent/prompt_builder.py`(2206 行,提示片段库+项目上下文加载)、`agent/system_prompt.py`(685 行,三层装配器)、`agent/context_engine.py`(489 行,可插拔上下文引擎 ABC)、`agent/context_references.py`(605 行,@ 引用展开)、`agent/coding_context.py`(916 行,编码姿态)、`agent/subdirectory_hints.py`(340 行,子目录上下文渐进发现)、`agent/message_sanitization.py`(852 行,消息/工具载荷清洗)、`agent/bounded_response.py`(148 行,流式错误体有界读取)、`agent/context_breakdown.py`(360 行,/context 用量拆解)。

---

## 1. 系统提示的三层装配(system_prompt.py + prompt_builder.py)

### 1.1 总体结构:每会话构建一次,按"变化概率"排三层

系统提示不是每轮重建,而是**每会话构建一次并缓存**,只有上下文压缩才触发重建——这是为了保住 provider 侧的 prefix cache(前缀缓存,provider 对逐字节相同的前缀免重复计费/免重算)。

`agent/system_prompt.py:1-24 @ 863e313`:
```python
"""System-prompt assembly for :class:`AIAgent`.

The agent's system prompt is built once per session and reused across all
turns — only context compression triggers a rebuild.  This keeps the
upstream prefix cache warm.  ...

Three tiers are joined with ``\n\n``:

* ``stable``   — identity (SOUL.md or DEFAULT_AGENT_IDENTITY), tool
  guidance, computer-use guidance, nous subscription block, tool-use
  enforcement guidance + per-model operational guidance,
  alibaba model-name workaround, environment hints, coding guidance,
  platform hints.
* ``context``  — caller-supplied ``system_message`` plus context files
  (AGENTS.md / .cursorrules / etc.) discovered under ``TERMINAL_CWD``,
  plus the session's coding-workspace snapshot.
* ``volatile`` — skills index, memory snapshot, USER.md profile, external
  memory provider block, timestamp/session/model/provider line.
"""
```

三层拼接与缓存点。`agent/system_prompt.py:578-586 @ 863e313`:
```python
    parts = build_system_prompt_parts(agent, system_message=system_message)
    joined = "\n\n".join(p for p in (parts["stable"], parts["context"], parts["volatile"]) if p)
    agent._cached_system_prompt_static = parts["stable"]

    # Surface context-file truncation warnings through the normal agent status
    # channel so gateway/CLI users see them in chat instead of only in logs.
    for warning in drain_truncation_warnings():
        agent._emit_status(warning)
```

排序哲学(变化最频繁的排最后,重建时未变前缀仍可复用):`agent/system_prompt.py:571-577 @ 863e313`:
```python
    Layers are ordered cache-friendly: stable identity/guidance first,
    then session-stable context files, then per-call volatile content
    (skills index, memory, USER profile, timestamp). For explicit
    cache_control backends the whole string is one cached block. For
    implicit longest-prefix backends the order is what matters: the
    content most likely to change is rendered last, ...
```

### 1.2 stable 层逐段(哪些来自 config/模型/环境)

按 `build_system_prompt_parts` 装配顺序:

1. **身份**:优先 `~/.hermes/SOUL.md`(用户自定义人格,经威胁扫描+截断,见 §2),否则硬编码 `DEFAULT_AGENT_IDENTITY`。`agent/system_prompt.py:192-201 @ 863e313`:
```python
    _soul_loaded = False
    if agent.load_soul_identity or not agent.skip_context_files:
        _soul_content = _r.load_soul_md(_ctx_len)
        if _soul_content:
            stable_parts.append(_soul_content)
            _soul_loaded = True

    if not _soul_loaded:
        # Fallback to hardcoded identity
        stable_parts.append(DEFAULT_AGENT_IDENTITY)
```
注意 `load_soul_identity` 让 cron 等模式在关闭项目上下文(`skip_context_files`)时仍保留 SOUL 人格(`agent/system_prompt.py:189-191` 注释)。

2. **自助文档指引** `HERMES_AGENT_HELP_GUIDANCE`(`prompt_builder.py:154-163`)。

3. **通用完成度/反造假指引** `TASK_COMPLETION_GUIDANCE`——对所有模型,由 `agent.task_completion_guidance` 配置门控(默认开),且仅在有工具时注入(`system_prompt.py:212-213`)。它源于两类真实失败:Opus 写 85 字节 stub 即停、DeepSeek 在 pip 被 PEP-668 挡住后**编造**房源数据(`prompt_builder.py:330-339` 注释)。

4. **通用并行工具调用指引** `PARALLEL_TOOL_CALL_GUIDANCE`(`prompt_builder.py:387-398`),移植自 cline#11514;运行时早已并发执行独立调用,缺的是"让模型一次发多个"这半边(`prompt_builder.py:370-378` 注释)。

5. **工具感知指引**:`memory` 工具在 → `MEMORY_GUIDANCE`;`session_search` 在 → `SESSION_SEARCH_GUIDANCE`;`skill_manage` 在 → `SKILLS_GUIDANCE`;kanban worker 由 `HERMES_KANBAN_TASK` 环境变量门控 → `KANBAN_GUIDANCE`。`agent/system_prompt.py:227-243 @ 863e313`:
```python
    tool_guidance = []
    if "memory" in agent.valid_tool_names:
        tool_guidance.append(MEMORY_GUIDANCE)
    if "session_search" in agent.valid_tool_names:
        tool_guidance.append(SESSION_SEARCH_GUIDANCE)
    if "skill_manage" in agent.valid_tool_names:
        tool_guidance.append(SKILLS_GUIDANCE)
```
MEMORY_GUIDANCE 值得单独记:它规定"记忆=陈述性事实,不是给自己的指令"("'User prefers concise responses' ✓ — 'Always respond concisely' ✗",`prompt_builder.py:180-183`),防止祈使句在后续会话被当成新指令重放。

6. **/steer 信道说明** `STEER_CHANNEL_NOTE`(有工具才注入,`system_prompt.py:249-250`)。设计要点:中途转向消息只能附在 tool result 尾部(唯一不破坏角色交替的槽位),而这恰是注入防御训练最不信任的信道——裸的 "User guidance:" 会被模型当注入拒绝(实录)。所以用自描述的定界标记 + "只信这个标记"的白名单化说明,并定义"何时算新消息"防历史重放(`prompt_builder.py:655-697`)。

7. **computer_use 指引**:按宿主平台渲染(macOS/Windows/Linux 措辞不同),`system_prompt.py:256-258`、`prompt_builder.py:498-643`。

8. **Nous 订阅能力块**(`prompt_builder.py:1894-1957`):告诉模型哪些托管能力已激活,免得向用户要 API key。

9. **按模型族注入的执行纪律**,由 config `agent.tool_use_enforcement` 门控(auto/true/false/自定义子串列表)。`agent/system_prompt.py:281-297 @ 863e313`:
```python
        else:
            # "auto" or any unrecognised value — use hardcoded defaults
            model_lower = (agent.model or "").lower()
            _inject = any(p in model_lower for p in TOOL_USE_ENFORCEMENT_MODELS)
        if _inject:
            stable_parts.append(TOOL_USE_ENFORCEMENT_GUIDANCE)
            _model_lower = (agent.model or "").lower()
            ...
            if "gemini" in _model_lower or "gemma" in _model_lower:
                stable_parts.append(GOOGLE_MODEL_OPERATIONAL_GUIDANCE)
            ...
            if "gpt" in _model_lower or "codex" in _model_lower or "grok" in _model_lower:
                stable_parts.append(OPENAI_MODEL_EXECUTION_GUIDANCE)
```
`TOOL_USE_ENFORCEMENT_MODELS = ("gpt", "codex", "gemini", "gemma", "grok", "glm", "qwen", "deepseek")`(`prompt_builder.py:326`)。即:Claude 默认不吃这套"必须马上调工具"的鞭子,GPT/Gemini/国产开源模型吃。

10. **阿里 API bug 变通**:Alibaba Coding Plan 永远返回 "glm-4.7" 当模型名,所以把真实模型身份写进提示(`system_prompt.py:329-341`)。

11. **环境提示** `build_environment_hints()`:本地后端报宿主 OS/home/cwd(Windows 加"hostname≠username"与"terminal 是 bash 不是 PowerShell"两条),远程后端(docker/modal/ssh 等)**压制宿主信息**、改为在后端内跑一次探针(`uname/whoami/pwd`,4s 超时,进程内缓存)报告沙箱状态——"你的工具摸不到宿主机"(`prompt_builder.py:1173-1279`,探针 `prompt_builder.py:1040-1165`)。另支持嵌入方通过 `HERMES_ENVIRONMENT_HINT` env 或 config `agent.environment_hint` 追加环境描述(env 优先,`prompt_builder.py:1259-1277`)。

12. **编码姿态**(见 §3):brief 进 stable,workspace 快照后移到 context 层作缓存边界(`system_prompt.py:350-378`)。

13. **Python 工具链探针**(pip/uv/PEP-668 状态,只有异常才出一行,`system_prompt.py:387-395`)、**活动 profile 提示**(防跨 profile 误写,`system_prompt.py:404-429`)、**平台提示** `PLATFORM_HINTS[platform]`(20 个平台的渲染能力/MEDIA: 附件语法/限制说明,`prompt_builder.py:706-954`),支持 config `platform_hints.<platform>` 的 replace/append 覆写(`system_prompt.py:73-119`),Telegram 富文本扩展按 `platforms.telegram.extra.rich_messages` 追加(`system_prompt.py:451-459`)。

### 1.3 context 层与 volatile 层

context 层 = 编码 workspace 快照(若有)+ 调用方 `system_message` + 项目上下文文件(§2)。`ephemeral_system_prompt` 明确**不在**此处——它在 API 调用时注入,不进缓存的系统提示(`system_prompt.py:475-477` 注释)。

volatile 层的关键决策:**技能索引放 volatile 之首而不是 stable**。`agent/system_prompt.py:503-513 @ 863e313`:
```python
    # Skills are runtime-mutable: the agent adds and patches them across a
    # session (SKILLS_GUIDANCE tells it to patch a skill the moment it goes
    # stale). The built prompt is cached per session and only rebuilt on
    # compaction/restore (see build_system_prompt), so a skill change is not
    # byte-stable across rebuilds. With the index in the stable band, a rebuild
    # that picked up a skill change would bust the cached prefix from the index
    # down, taking the whole scaffold with it. Render it at the FRONT of the
    # volatile band instead, ahead of the turn-varying memory/timestamp tail:
    ...
    if skills_prompt:
        volatile_parts.append(skills_prompt)
```
之后是记忆快照(MEMORY.md)、USER.md 用户画像、外部 memory provider 块,最后是时间戳行——**只到日期精度**,让系统提示全天字节稳定。`agent/system_prompt.py:537-543 @ 863e313`:
```python
    # Date-only (not minute-precision) so the system prompt is byte-stable
    # for the full day.  Minute-precision changes invalidate prefix-cache KV
    # on every rebuild path ...
    timestamp_line = f"Conversation started: {now.strftime('%A, %B %d, %Y')}"
```

技能索引本身(`build_skills_system_prompt`,`prompt_builder.py:1602-1891`)是双层缓存:进程内 LRU(键含 skills 目录、工具集、平台、禁用列表、demote 类别)+ 磁盘快照(mtime/size manifest 校验,含组织镜像 `.active_org` 标记,换组织即失效,`prompt_builder.py:1388-1430`)。个人/组织技能同名时**双方都打 [name collision] 标记、都限定路径加载**,不允许任何一方静默赢(`prompt_builder.py:1705-1731`)。

### 1.4 失效与静态前缀重建

压缩后调 `invalidate_system_prompt`:清空缓存并从磁盘重载记忆(`system_prompt.py:590-599`)。会话恢复/压缩保留提示/中途 failover 到带缓存 provider 时,静态前缀(两块 `[static, volatile]` 缓存布局所需)未持久化,须重建;安全约束是**重建出的 stable 必须是存储提示的字面前缀**,否则放弃(绝不改写存储字节),且失败按 stored prompt 记忆化防热路径反复 I/O(`system_prompt.py:602-654`)。

**重实现要点(§1)**
- 系统提示按"变化概率"分层排序,一次构建整会话复用;任何会中途变化的信息(时间、git 状态)要么降精度(date-only)、要么声明为"会话起点快照,用工具复查"。
- 模型行为指引按模型族条件注入,且给用户 config 开关;通用失败模式(stub 即停、编造输出)的指引对全模型开。
- 工具指引与工具在场绑定:没有该工具就不要花 token 讲它。
- 运行时可变的块(技能索引)放最后一层的最前面:最长前缀缓存下,未变仍命中,变了只重刷尾部。
- 带外用户消息进入不可信信道时,用自描述定界符+系统提示白名单声明+新鲜度规则三件套。

---

## 2. ▲ 定案:项目上下文文件注入(AGENTS.md/CLAUDE.md/.cursorrules 等)

R1 标记的三个问题逐一定案。

### 2.1 多约定并存选哪个:严格优先级,首中即停,只装一种

`agent/prompt_builder.py:2188-2196 @ 863e313`:
```python
    else:
        # Priority-based project context: first match wins
        project_context = (
            _load_hermes_md(cwd_path, context_length)
            or _load_agents_md(cwd_path, context_length)
            or _load_claude_md(cwd_path, context_length)
            or _load_cursorrules(cwd_path, context_length)
        )
    if project_context:
        sections.append(project_context)
```
优先级与搜索范围各不同:`.hermes.md`/`HERMES.md` 从 cwd 向上走到 git root(无 git root 时只查 cwd,防止捡到 /tmp、/home 里被埋的文件,`prompt_builder.py:108-110`);`AGENTS.md`/`agents.md` 仅 cwd 顶层(`prompt_builder.py:2061-2063`:`"""AGENTS.md — top-level only (no recursive walk)."""`);`CLAUDE.md`、`.cursorrules`+`.cursor/rules/*.mdc` 也仅 cwd。SOUL.md 独立于该优先级,永远单独加载(§1.2)。子目录里的同类文件不在启动时合并,而是会话中按导航惰性注入(§6)。

附带的一个安全定案:cwd 是**回退解析**且落在 Hermes 安装树内时,直接放弃项目上下文发现——否则桌面端后台进程会把本仓库贡献者的 AGENTS.md 当权威项目上下文注入(事故 #64590);显式配置的 cwd 或 cli/tui(launch dir 就是用户 shell cwd)则放行(`prompt_builder.py:2165-2186`,`system_prompt.py:487-494`)。

### 2.2 大文件对小上下文模型怎么截断:动态 cap + 70/20 头尾保留 + 中缝标记 + 状态信道告警

cap 解析三级:config 显式值 > 按模型窗口动态推导 > 20K 兜底。`agent/prompt_builder.py:1292-1309 @ 863e313`:
```python
_CONTEXT_FILE_CHARS_PER_TOKEN = 4
_CONTEXT_FILE_WINDOW_FRACTION = 0.06
_CONTEXT_FILE_DYNAMIC_CEILING = 500_000


def _dynamic_context_file_max_chars(context_length: Optional[int]) -> int:
    ...
    if not isinstance(context_length, int) or context_length <= 0:
        return CONTEXT_FILE_MAX_CHARS
    budget = int(
        context_length * _CONTEXT_FILE_CHARS_PER_TOKEN * _CONTEXT_FILE_WINDOW_FRACTION
    )
    return max(CONTEXT_FILE_MAX_CHARS, min(budget, _CONTEXT_FILE_DYNAMIC_CEILING))
```
即:窗口的 6%(按 4 字符/token 折算),下限 20,000 字符、上限 500,000。128K 模型 ≈ 30.7K 字符;8K 小模型落在 20K 地板。`context_length` 从 `agent.context_compressor.context_length` 取(`system_prompt.py:179-184`)。

超限时保头 70%、尾 20%,中间放可执行的恢复指引。`agent/prompt_builder.py:1991-2001 @ 863e313`:
```python
    head_chars = int(max_chars * CONTEXT_TRUNCATE_HEAD_RATIO)
    tail_chars = int(max_chars * CONTEXT_TRUNCATE_TAIL_RATIO)
    head = content[:head_chars]
    tail = content[-tail_chars:]
    marker = (
        f"\n\n[...truncated {filename}: kept {head_chars}+{tail_chars} of "
        f"{len(content)} chars. The middle is omitted — if you need the full "
        f"instructions, read the complete file with the read_file tool: "
        f"{target}]\n\n"
    )
    return head + marker + tail
```
同时 `_record_truncation_warning` 记入 **ContextVar**(按线程/异步任务隔离,防并发网关会话互相排空对方告警,`prompt_builder.py:1332-1358`),由 `build_system_prompt` 排空经 `agent._emit_status` 送到聊天界面(§1.1 引文),告警文案直接指向 `context_file_max_chars` 配置键(测试 `tests/agent/test_prompt_builder.py:115` 锁定)。

### 2.3 注入前是否过威胁扫描:过,"context" 域,命中即整体拦截换占位符

`agent/prompt_builder.py:71-79 @ 863e313`:
```python
    if content.startswith("\ufeff"):
        content = content[1:]

    findings = _scan_for_threats(content, scope="context")
    if findings:
        logger.warning("Context file %s blocked: %s", filename, ", ".join(findings))
        return f"[BLOCKED: {filename} contained potential prompt injection ({', '.join(findings)}). Content not loaded.]"

    return content
```
要点:(a) 先剥 UTF-8 BOM——Windows 编辑器产物,不是注入,否则整个 SOUL.md 被误杀(`prompt_builder.py:66-70` 注释);(b) 拦截语义是 **block-with-placeholder**:原文完全不进系统提示,只留一句说明;(c) 为什么这层敢 block:"the file would otherwise enter the system prompt verbatim and the user has no chance to intervene"(`prompt_builder.py:62-64`)。

模式库单一权威在 `tools/threat_patterns.py`,三个 scope 分层:`"all"`(经典注入+外传,处处适用)⊂ `"context"`(加 promptware/C2/角色劫持,用于上下文文件、记忆、工具结果)⊂ `"strict"`(加 SSH 后门/持久化/外传 URL,只用于记忆写入与技能安装这类用户可介入路径)。`tools/threat_patterns.py:14-24 @ 863e313`:
```python
- ``"all"``  — applied everywhere (classic prompt injection, exfiltration)
- ``"context"`` — applied to context files + memory + tool results
  (promptware / C2 / behavioral hijack; broader detection)
- ``"strict"`` — applied to memory writes + skill installs only
  (aggressive checks acceptable for user-curated content but too noisy
  for tool results)
```
context 文件**不用** strict 域的理由写在 `prompt_builder.py:60-64`:克隆下来的安全研究/基础设施仓库里 `authorized_keys`、`~/.ssh` 这类词太常见,strict 会把合法仓库整体拦死。扫描细节:输入截断到 65,536 字符防 ReDoS;关键词间允许 ≤8 个填充词(防"ignore all prior instructions"式绕过);先在**原始**文本上查 17 个不可见/双向 Unicode 码点,再做 NFKC 归一化折叠全角变体(`ｃａｔ`→`cat`)后跑正则;明确承认不防跨文字系统混淆字(西里尔 а)(`threat_patterns.py:53-59, 229-245`)。

**▲ 定案**:多约定并存时按 `.hermes.md/HERMES.md → AGENTS.md → CLAUDE.md → .cursorrules(+.cursor/rules/*.mdc)` 首中即停,只注入一种;超长文件按"config 显式值 > 窗口 6%(20K 地板/500K 顶)"截断,保 70% 头 + 20% 尾,中缝标记指引 read_file 取全文,并向用户状态信道发告警;注入前全部经 `scope="context"` 威胁扫描(注入+promptware+角色劫持,不含 strict 的 SSH/持久化模式),命中即整文件替换为 [BLOCKED] 占位符,BOM 预剥离防误杀。R1 的三个疑问全部证实为"已实现且有明确设计理由"。

**重实现要点(§2)**
- 多约定文件用严格优先级而非合并:合并会把互相冲突的三家规范同时塞给模型;选一种、其余靠模型自己用工具读。
- 截断 cap 跟模型窗口成比例并给地板/天花板;截断必须留"如何恢复全文"的可执行指引,并把事件推到用户可见信道,不能只进日志。
- 进系统提示的文本 = 用户无法中途拦截的文本,扫描策略应比工具结果(warn)更严(block),但比用户主动写入(strict)更宽;模式库跨扫描点共享单一权威。
- 回退推导出的 cwd 不应获得系统提示级权威(安装树防御)。

---

## 3. coding_context.py — 编码姿态:一个 seam,多个消费者

**解决的问题**:用户在代码仓库里跑 Hermes 时,应自动获得"结对高级工程师"的操作简报 + git/项目快照,但不能让检测逻辑散落各处、不能破坏提示缓存、不能误伤"给笔记仓库 git init"的非编码用户。

姿态建模为不可变 `RuntimeMode` + 声明式 `ContextProfile` 注册表(coding/general),全部消费方读同一个解析结果(`coding_context.py:9-29` 模块注释)。激活模式 `agent.coding_context`:`auto`(默认,仅提示层)/`focus`(另收敛工具集为 coding+MCP、非编码技能类目降为 names-only)/`on`/`off`(`coding_context.py:39-50`)。

检测(`_detect_profile_name`,`coding_context.py:434-468`):交互面(cli/tui/acp/desktop)∧ 代码工作区。工作区 = 识别到项目根标记(manifest/AGENTS.md 等,向上最多 6 级,跳过 $HOME 与共享 /tmp 根,`coding_context.py:405-431`)或 git 仓库;两个防误伤 guard 直接摘录:
`agent/coding_context.py:461-467 @ 863e313`:
```python
    git_root = _git_root(cwd)
    if git_root is not None and git_root == _home():
        git_root = None  # dotfiles repo at $HOME — not a code workspace
    # A bare git repo only counts when it actually holds code, so `git init` on a
    # notes/writing/research folder stays in the general posture.
    if git_root is not None and _has_code_files(git_root):
        return CODING_PROFILE.name
```
`_has_code_files` 是顶两层、≤500 次 stat 的有界扫描(`coding_context.py:110-139`)。

产出三段(`system_prompt_parts`,`coding_context.py:523-553`):(a) 操作简报 `CODING_AGENT_GUIDANCE`(先读后改、批量独立查询、禁止发明符号、用 patch/write_file 而非贴代码块、终端状态跨调用持久、修根因不修症状、3 次 lint 循环即止、快照要复查,`coding_context.py:217-265`)+ 按模型族追加**编辑格式引导**——GPT/Codex 推 V4A diff(其第一方 harness 只教过 apply_patch),Claude/开源模型推 str_replace(`coding_context.py:160-187` 长注释);(b) workspace 快照(git 分支/领先落后/脏计数/近 3 commit/linked worktree 标注 + 项目事实:manifest、锁文件推包管理器、从 package.json scripts/Makefile targets/pytest 配置嗅探 verify 命令,`coding_context.py:865-916`、`detect_project_facts` `coding_context.py:780-816`);(c) config `agent.coding_instructions` 操作员常备指令独立成块保 brief 字节稳定(`coding_context.py:549-552`)。git 探针用 `bounded_git_probe` 防 Windows 上被杀 git 的悬挂子进程占管道死锁(事故 #66037,`coding_context.py:719-727`)。

缓存契约:快照会话起点构建一次,绝不逐轮重探;`/coding` 翻转下会话生效(`coding_context.py:30-37`)。`focus` 下技能类目**降级不隐藏**——早期版本整类剪掉造成过真实工作流的静默能力丢失(agent 自建技能=项目记忆,模型不会主动 `skills_list` 重发现),names-only 保住按名回忆(`coding_context.py:574-584`)。

**重实现要点(§3)**
- "当前处于什么姿态"做成单点解析的不可变对象,提示/工具集/路由/记忆策略都读它,别让各处自嗅。
- 检测要防三类误伤:$HOME dotfiles 仓、共享 /tmp 下的野 manifest、无代码的 git 笔记仓;全部用有界 stat/scandir,别全树遍历。
- 给模型的"项目事实"(verify 命令、包管理器)一次检测、双消费(提示+UI),避免两处嗅探漂移。
- 从索引里删信息=静默能力损失;要瘦身就降级(names-only),永远保留可按名召回的锚。

---

## 4. ◇ 定案:可插拔 ContextEngine 抽象与每轮上下文选择钩子

### 4.1 ABC 形态

`agent/context_engine.py:1-26 @ 863e313`(节选):
```python
"""Abstract base class for pluggable context engines.

A context engine controls how conversation context is managed when
approaching the model's token limit. The built-in ContextCompressor
is the default implementation. Third-party engines (e.g. LCM) can
replace it via the plugin system or by being placed in the
``plugins/context_engine/<name>/`` directory.

Selection is config-driven: ``context.engine`` in config.yaml.
Default is ``"compressor"`` (the built-in). Only one engine is active.
```
必须实现:`name`、`update_from_response(usage)`、`should_compress()`、`compress(messages, current_tokens, focus_topic, force, memory_context)`;必须维护 token 状态字段(`last_prompt_tokens` 等)与压缩参数(`threshold_percent=0.75, protect_first_n=3, protect_last_n=6`,`context_engine.py:103-129`)。可选钩子:`prune_tool_results_only`(无 LLM 的工具结果裁剪,默认安全 no-op 防旧引擎 AttributeError,`context_engine.py:194-211`)、`should_compress_info`(带 reason,为静默溢出告警 #62625 加的向后兼容包装,`context_engine.py:149-160`)、preflight 对、生命周期(`on_session_start/end/reset`)、引擎自带工具(`get_tool_schemas/handle_tool_call`)、`update_model`(含每模型阈值覆写解析,快照首次 config 值防连续切换叠加,`context_engine.py:456-489`)。

### 4.2 事故与钩子设计:selection ≠ compression

**事故经过(讲成故事)**:第三方引擎(LCM 类检索/路由引擎)需要每轮看到消息列表以决定"这轮该用哪份上下文"。ABC 里唯一每轮必经的可写入口是 `compress()`,但它只在 `should_compress()` 为真时才被调。于是引擎被迫让 `should_compress()` **恒返回 True**,把 `compress()` 蹭成每轮回调——后果:选择与压缩两个语义被搅在一起,宿主以为"每轮都在压缩"(状态、告警、计数全被污染),而且引擎后端一旦不可用,这条被劫持的压缩路径直接劣化整个会话。这段历史写在钩子 docstring 里。`agent/context_engine.py:236-241 @ 863e313`:
```python
        Without this hook, engines that need per-turn access to the message
        list have to force ``should_compress()`` to return ``True`` so that
        ``compress()`` is invoked every turn purely as a callback — which
        conflates selection with compression and degrades behaviour when the
        engine's backend is unavailable. ``select_context()`` removes the need
        for that workaround.
```
引入该钩子的 commit 佐证:`dec464c35 "feat(context-engine): add select_context() per-turn selection hook"`("removing the need to abuse should_compress()=True as a per-turn callback… Consolidates the per-turn request-assembly surface proposed across #41918… Related: #36765 #41918 #24949 #47109 #50053 …",git log @ 基线祖先)。

**现在的设计**:两个正交动词。`agent/context_engine.py:229-235 @ 863e313`:
```python
          - ``compress()``      : context is too long  -> make it shorter.
          - ``select_context()``: this turn belongs to a different context
                                  -> use that one instead.
```
`select_context(request_messages, *, conversation_messages, incoming_message, budget_tokens)`(`context_engine.py:215-279`)契约五条:
1. **request-only**:返回列表只替换本次 provider 请求,持久转录一律不动("MUST NOT be treated as persisted transcript state",`context_engine.py:243-247`);返回 `None` 即不动。
2. **排序/缓存契约**:钩子跑在 prompt cache-control 与所有请求 sanitizer **之前**,所以替换结果仍过全套校验、畸形替换到不了 provider;默认 no-op 字节不变,缓存行为对内置压缩器零影响;真替换的引擎自己承担前缀变化,cache 断点在选出的列表上重推导(`context_engine.py:252-262`)。
3. 每次 provider 请求都评估(轮内重试也重跑,`context_engine.py:265-266`)。
4. 与 `pre_llm_call` 插件钩子的分工:后者按文档设计只追加、永不改写列表(保缓存前缀);唯一能"换消息"的动词是 select_context(`context_engine.py:249-251`)。
5. 观察半边由 `on_turn_complete(messages, usage, **kwargs)` 补齐(`context_engine.py:281-328`):轮完成后送最终转录浅拷贝 + 本轮规范 usage(interrupt 时为 None),供引擎摄取/索引以指导下一轮 select;文档如实声明覆盖是 best-effort(内容策略拦截、provider 终态失败等提前 return 路径暂不触发)。

**宿主侧防御性落地**(`conversation_loop.py`):
- 恒等检查跳过 ABC 默认实现,非实现引擎零成本(hasattr 不够,因为 ABC 给每个引擎都定义了默认 `select_context`)。`agent/conversation_loop.py:1133-1138 @ 863e313`:
```python
    try:
        from agent.context_engine import ContextEngine as _CE
        if getattr(engine.select_context, "__func__", None) is _CE.select_context:
            return api_messages
    except Exception:
        pass
```
- 只读输入送浅拷贝,强制而非仅文档化 request-only 契约(`conversation_loop.py:1141-1150`)。
- fail-open:异常、None、非列表、**空列表**都回退原请求——空列表单独防,因为 `all([])` 为 True,`[]` 会把合法请求换成 sanitizer 救不回的空请求(`conversation_loop.py:1169-1175`)。
- 调用点在请求组装后、`_sanitize_api_messages` 等一切 sanitizer 前(`conversation_loop.py:1773-1791`);`on_turn_complete` 从 `turn_finalizer` 统一收尾缝发出,携 `_last_turn_usage` 与 turn_id/interrupted/failed/turn_exit_reason 元数据(`turn_finalizer.py:586-610`)。

**◇ 定案**:事故根因是 ABC 只有"压缩"一个每轮入口,选择型引擎被迫恒真 should_compress 蹭 compress 当回调;现设计将 selection(请求前,可替换本请求消息)与 observation(轮后,只读摄取)拆成两个 no-op 默认、fail-open、恒等检查跳过基类实现的钩子,替换结果仍走全部 sanitizer,且持久历史被拷贝隔离——把"换上下文"从"缩上下文"里干净剥离,同时对不实现的引擎(含内置压缩器)保证字节级零影响。

**重实现要点(§4)**
- 插件 ABC 里"每轮必经"的入口必须独立于任何条件触发的入口,否则条件必被插件劫持恒真。
- 钩子三件套:no-op 默认 + 宿主 fail-open + 恒等检查跳过基类默认(hasattr 判不出"继承默认"vs"实现了")。
- 可替换请求的钩子要放在全部校验/缓存标记之前,让替换结果与原生请求走同一后处理管线。
- 空列表、非法类型这类"看似合法"的返回值要显式防(`all([])` 陷阱)。
- 契约用拷贝强制执行(只读输入给浅拷贝),不能只靠 docstring。

---

## 5. context_references.py — 用户消息里的 @ 引用展开

**解决的问题**:让用户在消息里写 `@file:src/main.py:10-40`、`@folder:src`、`@diff`、`@staged`、`@git:3`、`@url:...`,由 CLI/TUI/gateway 在送模型前展开成附加上下文块(`cli.py:13827`、`tui_gateway/server.py:9473`、`gateway/run.py:16164` 调用)。

语法:正则 `REFERENCE_PATTERN` 支持引号包裹含空格路径与 `:行-行` 区间(`context_references.py:17-20`);展开后 @ 记号**留在原句**(记号即引用,客户端渲染为 chip;早期剥掉造成"review and ship"句子破洞,`context_references.py:220-225` 注释)。多引用 `asyncio.gather` 并发展开(`context_references.py:171-187`)。

预算:注入 token 超窗口 50% 硬拒(整条消息不展开,`blocked=True`),超 25% 软警。`agent/context_references.py:195-209 @ 863e313`:
```python
    hard_limit = max(1, int(context_length * 0.50))
    soft_limit = max(1, int(context_length * 0.25))
    if injected_tokens > hard_limit:
        warnings.append(
            f"@ context injection refused: {injected_tokens} tokens exceeds the 50% hard limit ({hard_limit})."
        )
        return ContextReferenceResult(
            ...
            blocked=True,
        )
```

安全:路径默认锁在 cwd 工作区内(`allowed_root` 默认=cwd,`context_references.py:163-166`);再过两道敏感路径拦截——本地窄名单(.ssh/.aws/.netrc/shell rc 等,`context_references.py:23-39`)+ 锚定到 `agent/file_safety.get_read_block_error` 的规范读拒绝名单,并且该查询失败时**fail closed**,因为 gateway 会把不可信远端消息喂进展开器,`@file:~/.hermes/auth.json` 探测否则能直接把操作员密钥拉进上下文(`context_references.py:404-433`)。二进制文件不硬拒:返回"在磁盘上的路径+类型+大小+用工具处理"的可行动块,修掉了模型见 warning 即放弃的死胡同(`context_references.py:280-288, 566-578`)。folder 列表优先 `rg --files`(尊重 .gitignore),回退 os.walk,200 条上限(`context_references.py:490-554`)。

**重实现要点(§5)**:用户级引用注入要有独立于压缩的预算闸(硬/软双限);展开器一旦暴露给远端输入,读路径必须挂接全局凭据拒绝名单且失败关闭;不可展开 ≠ 失败,给模型可行动的降级块。

---

## 6. subdirectory_hints.py — 子目录上下文的渐进发现

**解决的问题**:启动只装 cwd 一份项目上下文(§2),但 monorepo 里 `backend/AGENTS.md` 的规则在模型第一次碰 `backend/` 时才相关。方案(借鉴 Block/goose):追踪工具调用参数里出现的目录,首次访问时加载该目录的上下文文件,**附加到工具结果**而非改系统提示——不破坏提示缓存(`subdirectory_hints.py:1-14` 模块注释)。注入点:`tool_executor.py:1471-1478 @ 863e313`:
```python
        subdir_hints = agent._subdirectory_hints.check_tool_call(name, args)
        if subdir_hints:
            if _is_multimodal_tool_result(function_result):
                _append_subdir_hint_to_multimodal(function_result, subdir_hints)
            else:
                function_result += subdir_hints
```

机制要点:路径来源=路径参数键(path/file_path/workdir)+ terminal 命令 shlex 分词嗅探(跳过 flag/URL,`subdirectory_hints.py:140-207`);从命中目录向上最多走 5 级祖先,使读 `project/src/main.py` 也能发现 `project/AGENTS.md`(`subdirectory_hints.py:160-186`);**工作区边界硬约束**——工作树外一律拒绝,防 `~/.codex/AGENTS.md`、`~/.claude/CLAUDE.md` 跨 agent 污染(`subdirectory_hints.py:209-238`,PR #32103);排除 node_modules/vendor/backups 等"只存副本不存上下文"的目录(`subdirectory_hints.py:49-59`);SHA-256 内容去重(symlink/硬链/备份副本同内容只注入一次,并预植 cwd 文件摘要防启动已装内容二次注入,`subdirectory_hints.py:86-114, 288-302`);每目录内 first-match-wins(同 §2 优先级,但**注意**其名单 `_HINT_FILENAMES` 不含 `.hermes.md`,`subdirectory_hints.py:30-34`);内容过同一 `_scan_context_content` 威胁扫描,单文件 8K 截断(`subdirectory_hints.py:303-309`)。

**重实现要点(§6)**:会话中新增上下文一律走对话流(工具结果尾部),永不回写系统提示;渐进发现三防线=工作区边界+目录黑名单+内容摘要去重;与启动注入共用同一威胁扫描与优先级约定。

---

## 7. message_sanitization.py — 清洗什么、何时调用、防什么

纯函数库,从 run_agent 抽出。四组职责:

1. **代理对(surrogate)清洗**:U+D800–DFFF 孤立代理对会让 OpenAI SDK 内的 `json.dumps` 崩溃;来源是字节级推理模型(xiaomi/mimo、kimi、glm 经 Ollama)。覆盖 content/name/tool_calls/arguments 以及 reasoning_content 等任意嵌套字段(`message_sanitization.py:76-141`)。调用时机:每次请求发出前主动清一遍(`conversation_loop.py:1823-1827`:"Proactively strip any surrogate characters before the API call… prevents the 3-retry cycle"),报错重试路径再兜底清 messages/api_messages/prefill 三份(`conversation_loop.py:3555-3563`)。
2. **非 ASCII 剥离**(最后手段):LANG=C 的 Chromebook/最小容器上编码报错时整链降级为 ASCII(`message_sanitization.py:324-380`,调用于 `conversation_loop.py:3593-3604`)。
3. **工具调用参数 JSON 修复** `_repair_tool_call_arguments`:GLM/llama.cpp 会吐截断 JSON、尾逗号、Python `None`、字面控制符;修复链=strict=False 重解析→去尾逗号→补/删括号(50 次上限)→字符级转义控制符→最终兜底 `"{}"`("better than crashing the session"),全程 WARNING 日志(`message_sanitization.py:186-280`;调用于流式解析 `conversation_loop.py:824` 与 `chat_completion_helpers.py:3430`)。
4. **协议不变量修复**:
   - `close_interrupted_tool_sequence`:/stop 打断后转录若以 tool 消息结尾,补一条 "Operation interrupted." 的 assistant 轮——否则 `tool → user` 违反角色交替,Gemini/Claude 会幻觉续写用户消息、表现为"丢上下文"(事故 #48879,`message_sanitization.py:283-312`)。
   - `_strip_images_from_messages`:服务器声明不支持图片时剥 image 部件,但 tool 消息**换占位文本而非删除**,保 tool_call_id 配对否则 400(`message_sanitization.py:388-433`;调用于 `conversation_loop.py:3772-3774`)。
   - **call_id 策略单一权威**(F4 整合):`deterministic_call_id` 内容哈希合成(硬不变量:"must stay deterministic (never uuid4)… these ids feed prompt-cache prefixes",`message_sanitization.py:508-521`);`coalesce_tool_call_id`(Responses 的 call_id vs Chat 的 id);`uniquify_tool_call_ids` 给同轮重复 id 加确定性 `_d<n>` 后缀——重复 id 会让 pre-API sanitizer 只留首对 call/result,后者结果静默消失(#58327),严格 provider 直接拒(`message_sanitization.py:536-612`)。
   - **reasoning_content 回传策略单一权威**:规则表定义 require 侧(kimi/deepseek/mimo:不回传即 400,空串也拒 → 单空格垫片 #17341)vs strict 侧(Mistral/Cerebras/Groq/SambaNova:出现该键即 400/422 → 剥除 #45655);`apply_reasoning_content_policy` 管重建路径(含跨 provider 污染史 #15748 的防思维链泄漏垫片),`reapply_reasoning_echo` 管 mid-turn failover 后对已建 api_messages 的幂等重校(`message_sanitization.py:615-836`;调用于 `conversation_loop.py:2201`)。策略集中、语法留在各 adapter(如 anthropic_adapter 把 reasoning_content 映射成 thinking block)是有意分界(`message_sanitization.py:839-853`)。

**重实现要点(§7)**:把"策略"(哪个 provider 方向如何处理)从"语法"(wire 格式映射)剥离并单点持有;一切修复必须确定性(禁 uuid4/时间戳)以保缓存前缀;修复消息列表时的第一不变量是角色交替与 call/result 配对,宁可注占位符不可删消息;劣质模型输出的兜底原则是"降级可用 > 会话崩溃",且全部留痕日志。

---

## 8. bounded_response.py — 流式错误体的有界读取

**解决的问题**:provider 对流式请求返回非 200 时要读 body 做诊断,裸 `response.read()` 有两个无界:体积可任意大;服务器可开流后停滞。诊断文本反正只展示几百字符,读兆级/永久阻塞毫无收益(`bounded_response.py:1-22`)。上限 64KB + 10s 硬墙钟(`bounded_response.py:49-53`)。关键实现细节:`agent/bounded_response.py:23-31 @ 863e313`:
```python
A subtlety the implementation must respect: ``httpx``'s ``iter_bytes()`` blocks
*inside* the C/socket read while waiting for the next chunk. A wall-clock check
placed only between yielded chunks cannot interrupt a server that opens the
body and then stalls mid-chunk — control never returns to Python until httpx's
own (often 30s+) read timeout fires. To guarantee a bounded stop regardless of
socket behavior, the read runs on a daemon worker thread and the caller waits
on it with a hard deadline; on timeout we close the response (which unblocks /
cancels the read) and return whatever partial bytes were collected.
```
错误路径永不抛(部分字节即最好结果,`bounded_response.py:63-72`)。移植自 openclaw#95108,覆盖 Gemini 原生/Cloud Code/Antigravity 三个流式错误点(`bounded_response.py:32-35`)。

**重实现要点(§8)**:错误路径的读取要同时限字节与限墙钟;chunk 间检查拦不住 chunk 内停滞——必须 daemon 线程 + 关连接解锁;错误处理代码自己绝不能成为新错误源(吞异常、收部分字节)。

---

## 9. context_breakdown.py — /context 的用量拆解

**解决的问题**:给用户 Cursor/Claude Code 式的"上下文都花在哪"视图(CLI 字符网格、gateway 表格、桌面 popover)。复用 `build_system_prompt_parts` 的三层产物拆类别:从 stable 用 `<available_skills>` 正则抠出技能索引单列,memory/USER 块从 volatile 扣除,工具按名字分内置/MCP(`mcp_` 前缀)/子代理(delegate_task)(`context_breakdown.py:89-126`);统一 chars/4 粗估,与压缩阈值同一口径(`context_breakdown.py:31-34`);总量优先用压缩器记录的真实 `last_prompt_tokens`,无则用估算(`context_breakdown.py:130-133`)。`/context all` 复用 `hermes prompt-size` 的归因(每技能索引行字节、每工具集 schema 字节,PR #66656,`context_breakdown.py:190-229`)。网格渲染保证非零类别至少 1 格不隐形(`context_breakdown.py:246-248`)。

**重实现要点(§9)**:可观测性视图必须复用生产装配函数(同一 `build_system_prompt_parts`)拆解,不允许平行实现;估算与压缩触发用同一启发式,数字才互相可比;有真实计量时优先真实值。

---

## 10. 文档-代码出入(website/docs 对照,带双方证据)

1. **技能索引所在层**。文档:`website/docs/developer-guide/prompt-assembly.md:31 @ 863e313`:
```
1. **stable** — identity (`SOUL.md` or fallback), tool/model guidance, skills prompt, environment hints, platform hints
```
代码:技能索引在 **volatile** 层之首(`system_prompt.py:503-513`,§1.3 引文:"Render it at the FRONT of the volatile band instead")。文档 39 行 "skills are part of the **stable** tier" 同误。以代码为准:这是有意的缓存优化迁移,文档未跟上。

2. **示例装配顺序**。文档示例把 Skills index(Layer 7)排在 Context files(Layer 8)之前、Timestamp(Layer 9)在 Platform hint(Layer 10)之前(`prompt-assembly.md:88-117`)。代码顺序是 context 层(含 context files)先于 volatile 层(skills→memory→timestamp),platform hint 在 stable/context 内、先于 skills 与 timestamp(`system_prompt.py:461-465, 512-552`)。

3. **时间戳精度**。文档示例:`prompt-assembly.md:111`:
```
Current time: 2026-03-30T14:30:00-07:00
```
代码:date-only,且措辞是 "Conversation started:"(`system_prompt.py:543`,§1.3 引文;PR #20451 专为保缓存改的)。

4. **skip_context_files 与 SOUL**。文档:`prompt-assembly.md:42`:
```
When `skip_context_files` is set (e.g., subagent delegation), SOUL.md is not loaded and the hardcoded `DEFAULT_AGENT_IDENTITY` is used instead.
```
代码:`if agent.load_soul_identity or not agent.skip_context_files:`(`system_prompt.py:193`)——cron 等模式可在 skip_context_files 下仍装 SOUL。文档漏掉 `load_soul_identity` 这条腿。

5. **AGENTS.md 递归/合并**。文档:`website/docs/user-guide/configuration.md:2303,2311 @ 863e313`:
```
| `AGENTS.md` | Project-specific instructions, coding conventions | Recursive directory walk |
- **AGENTS.md** is hierarchical: if subdirectories also have AGENTS.md, all are combined.
```
代码:启动仅 cwd 顶层(`prompt_builder.py:2062`:"AGENTS.md — top-level only (no recursive walk)"),子目录版本是**会话中按导航惰性附加到工具结果**,不合并进系统提示(§6)。developer-guide 的 prompt-assembly.md:260 表述("CWD at startup; subdirectories discovered progressively… via agent/subdirectory_hints.py")是对的,user-guide 这两句是错的/过时的。

6. **context-engine-plugin.md 与代码一致性**:核查 select_context/on_turn_complete 契约五条、fail-open、恒等检查、缓存影响与 "stable selections when nothing has changed" 建议(`context-engine-plugin.md:100-160`)与 `context_engine.py:215-328`、`conversation_loop.py:1103-1230` 全部相符,无出入——该页可作为 ◇ 机制的可信文档。

---

## 11. 配套测试清单 + 2 个行为规格

清单(均在 `tests/` 下,@ 863e313):
- prompt 装配:`tests/agent/test_prompt_builder.py`(扫描/截断/动态 cap/技能索引缓存与降级/安装树防御)、`test_system_prompt.py`、`test_system_prompt_restore.py`(静态前缀重建)、`test_prompt_caching.py`、`tests/cli/test_cli_context_warning.py`
- context engine:`tests/agent/test_context_engine.py`(ABC 契约)、`test_context_engine_host_contract.py`、`test_context_engine_select_context.py`、`test_context_engine_on_turn_complete_usage.py`
- 各小件:`test_context_references.py`、`test_context_refs_concurrent.py`、`tests/cli/test_cli_codex_context_reference.py`、`tests/gateway/test_context_ref_expansion_runtime.py`;`test_subdirectory_hints.py`、`test_subdirectory_hints_tilde.py`;`test_message_sanitization_policy.py`、`tests/cli/test_surrogate_sanitization.py`;`test_bounded_response.py`;`test_context_breakdown.py`;`test_coding_context.py`

行为规格 A——**select_context 空列表必须 fail-open**。`tests/agent/test_context_engine_select_context.py:114-135 @ 863e313`:
```python
def test_empty_list_keeps_original_request():
    """An empty list must fall open to the original request.

    ``all([])`` is ``True``, so without an emptiness check a ``[]`` returned by
    a failing/buggy engine would replace a valid assembled request with an
    empty message list the downstream sanitizers cannot restore ...
    """
    class _Engine(_MinimalEngine):
        def select_context(self, request_messages, **kwargs):
            return []
    ...
    assert out is REQUEST
    assert logger.warning.called
```
同文件 `test_base_noop_select_context_is_short_circuited_not_called`(:72)把基类默认实现 patch 成 raise,断言宿主恒等检查根本不调它——把"非实现引擎零成本"钉成规格。

行为规格 B——**截断告警的可行动性与并发隔离**。`tests/agent/test_prompt_builder.py:115-127 @ 863e313`:
```python
    def test_truncation_warning_points_to_config_key(self, monkeypatch):
        def fake_load_config():
            return {"context_file_max_chars": 120}
        ...
        _truncate_content("x" * 180, "warning.md")

        warnings = drain_truncation_warnings()
        assert len(warnings) == 1
        assert "context_file_max_chars" in warnings[0]
        assert "CONTEXT_FILE_MAX_CHARS" not in warnings[0]
```
规格含义:告警必须指向用户能改的 config 键名,而非 Python 常量名;相邻的 `test_warnings_isolated_across_contexts`(:129)在子 contextvars 上下文里制造截断,断言父上下文排空不到——锁定 §2.2 的 ContextVar 跨会话隔离设计。另 `test_prompt_injection_blocked`(:69)锁定 ▲ 的 block-with-placeholder 语义("BLOCKED" + pattern id 出现在替换文本里)。

---

## 12. 全簇可迁移设计原则(汇总)

1. **缓存稳定性是提示工程的第一约束**:分层按变化概率、时间降精度、确定性 id、快照一次构建、可变块沉底——所有九个文件都在为同一不变量服务。
2. **进系统提示的内容 = 用户无法中途拦截的内容**,其安全策略(block)必须严于对话流内容(warn/append);威胁模式库单一权威、多 scope 分层复用。
3. **每个"注入"都要有预算、有降级、有用户可见的告警**:context 文件动态 cap、@ 引用 25%/50% 双限、子目录 hint 8K、memory context 6K(`context_engine.py:34-53`)。
4. **插件 seam 的铁律**:no-op 默认、fail-open、恒等检查、拷贝隔离、替换结果走原生管线。
5. **策略与语法分离**:provider 方向性差异(reasoning 回传、call_id、图片剥离)集中单点,wire 映射留在 adapter。

(底稿完。对应台账文件:agent/prompt_builder.py、agent/system_prompt.py、agent/context_engine.py、agent/context_references.py、agent/coding_context.py、agent/subdirectory_hints.py、agent/message_sanitization.py、agent/bounded_response.py、agent/context_breakdown.py → L1;引用的 tools/threat_patterns.py、agent/conversation_loop.py、agent/turn_finalizer.py、agent/tool_executor.py 片段为本簇取证所需的邻接阅读,不改变其原有归层。)