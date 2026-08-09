# r9a 底稿 · 学习闭环的策展侧 —— curator / insights / curator_backup

> 研究对象基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(只读)。
> 溯源约定:凡对代码行为的断言,**锚点单独成行、置于代码块之前**,格式 `路径:行号 @ 863e313`。
> 本文是底稿(证据层),求全求证、允许啰嗦。表格是索引不是证据,表格里的行号不带冒号。

**本轮范围 3 个文件 / 3,938 行(`wc -l` 实测):**

| 文件 | 行数 | 一句话职责 | 是否属于"学习闭环" |
|---|---|---|---|
| `agent/curator.py` | 2019 | 技能库的**后台园丁**:老化状态机 + 一次 LLM 合并 pass + 逐次运行报告 | 是,闭环的**回收/收敛**侧 |
| `agent/curator_backup.py` | 757 | 园丁动手前的 tar.gz 快照与回滚(含 cron 引用回填) | 是,闭环的**可撤销**保障 |
| `agent/insights.py` | 1162 | `/insights`、`hermes insights`、Dashboard 的**用量分析报表** | **否**(见 §0) |

---

## 0. 先纠正一个命名陷阱:`agent/insights.py` 不是"学习洞察"

这是本簇最容易被名字骗到的地方,先定死,后面不再反复。

`agent/insights.py:1 @ 863e313`
```python
"""
Session Insights Engine for Hermes Agent.

Analyzes historical session data from the SQLite state database to produce
comprehensive usage insights — token consumption, cost estimates, tool usage
patterns, activity trends, model/platform breakdowns, and session metrics.
```

它产出的是 token 数、花了多少美元、哪个工具被调得最多、哪天最忙 —— 是**账单与活动报表**,
不是"上一次会话学到了什么"。作者自己的地图也这么归类:

`README.md:154 @ 863e313`
> | Compress context / check usage | `/compress`, `/usage`, `/insights [--days N]` | `/compress`, `/usage`, `/insights [days]`                                        |

`website/docs/reference/cli-commands.md:90 @ 863e313`
> | `hermes insights` | Show token/cost/activity analytics. |

**判定**:`agent/insights.py` 与 curator **没有任何代码耦合**。
搜索面:对 `agent/insights.py` 全文 grep 了 `curator`、`skills/`、`.usage.json`、`hermes_home`
四个模式,**零命中**;反向对 `agent/curator.py` + `agent/curator_backup.py` 全文 grep
`hermes_state|SessionDB|state\.db|sqlite|checkpoint|memory|session_id|Checkpoint`,
只命中 3 行,全部是给 fork 传的 `skip_memory=True` / `_memory_nudge_interval` /
`_memory_write_origin` 这类**关掉**记忆的参数(见 §6.3)。命令与输出见下。

```verify
# 在 /home/user/hermes-agent 下重跑,应得到与本文一致的结果
grep -c "curator\|skills/\|\.usage\.json\|hermes_home" agent/insights.py          # → 0
grep -n "hermes_state\|SessionDB\|state\.db\|sqlite\|checkpoint\|memory\|session_id\|Checkpoint" \
     agent/curator.py agent/curator_backup.py                                     # → 仅 1936/1939/1948 三行
```

两者唯一的**概念**重叠是"技能使用次数",而且两边**统计的根本不是同一件事**(§8.2)。

---

## 1. 闭环到底闭在哪 —— 用一次具体会话把环走一遍

先说结论:**Hermes 的学习闭环不是"会话结束 → 提炼 insight → 存库 → 下次读回"**。
它是**"会话结束 → 后台 fork 决定要不要写一个 SKILL.md → 技能落在 `~/.hermes/skills/` →
下次会话的系统提示词里带着技能索引 → 用到了就给这个技能的计数器 +1 → 计数器决定它被留、被并、还是被归档"**。

**被提炼出来的东西是一个目录(skill package),不是一条记录;存储介质是文件系统,不是数据库。**
curator 是这条环上**最后一段**:它不生产知识,它**回收知识**。

### 1.1 一次具体会话的走法(七步)

假设用户 8 月 1 日让 agent 排查一个 `hermes gateway` 起不来的问题,折腾了 40 分钟解决了。

**第 1 步 —— 会话中,写入侧。** 回合结束后主循环可以 fork 一个后台评审 agent:

`agent/background_review.py:1 @ 863e313`
```python
"""Background memory/skill review — fork the agent to evaluate the turn.

After every turn, ``AIAgent.run_conversation`` may call
:func:`spawn_background_review` to fire off a daemon thread that replays
the conversation snapshot in a forked :class:`AIAgent` and asks itself
"should any skill/memory be saved or updated?".  Writes go straight to
the memory + skill stores.  Main conversation and prompt cache are never
touched.
```

它可能写出 `~/.hermes/skills/gateway-startup-debug/SKILL.md`。用户也可以显式走 `/learn`:

`agent/learn_prompt.py:2 @ 863e313`
```python
"""``/learn`` — build the standards-guided prompt that turns whatever the user
described into a reusable skill.
```

**第 2 步 —— 落盘 + 建台账行。** 技能目录落在 `~/.hermes/skills/<name>/`,同时
`tools/skill_usage.py` 在 `~/.hermes/skills/.usage.json` 里给它建一条记录
(`record_created` / `mark_agent_created`)。**这条记录是"我归 curator 管"的入场券**:

`tools/skill_usage.py:386 @ 863e313`
```python
        # Agent-authored (or local-manual) skills must opt in via their record.
        if not _is_curator_managed_record(usage.get(name)):
            continue
        names.append(name)
```

**第 3 步 —— 下一次会话,读回侧。** 技能不是被"检索"回来的,是**整个索引进系统提示词**。
curator 的提示词自己交代了这个读回通道的关键约束:

`agent/curator.py:422 @ 863e313`
```python
    "INSTRUCTIONS AND EXPERIENTIAL KNOWLEDGE. A collection of hundreds of "
    "narrow skills where each one captures one session's specific bug is "
    "a FAILURE of the library — not a feature. An agent searching skills "
    "matches on descriptions, not on exact names (note: long descriptions "
    "are truncated to 57 chars in the system prompt skill index — keep the "
    "trigger class in that window). One broad umbrella "
```

**这 57 个字符就是闭环的带宽瓶颈**,也是 curator 存在的根本理由:系统提示词里每个技能只有
一行 57 字的描述,技能越多,每一条被匹配中的概率越低,而 token 成本线性上涨。

**第 4 步 —— 用到了就计数。** 技能真被加载进对话时 `bump_use()` 给 `use_count` +1
(调用方在 `agent/skill_commands.py`、`agent/skill_bundles.py`、`tools/skills_tool.py`、
`cron/scheduler.py`);agent 主动 `skill_view` 则 `bump_view()`。

**第 5 步 —— 8 天后某次 CLI 启动。** `should_run_now()` 发现距上次 curator 运行超过
`interval_hours`(默认 168 小时),放行(§2)。

**第 6 步 —— 先备份,再纯函数老化。** 先 tar 一份 `skills/`(§7),再跑
`apply_automatic_transitions()`:30 天没动 → `stale`,90 天没动 → 移进
`~/.hermes/skills/.archive/`(§4)。这一步**不调 LLM**。

**第 7 步 —— 可选的 LLM 合并 pass。** 若 `curator.consolidate: true`,fork 一个
只带 `skills` + `terminal` 两个工具集的 AIAgent,把候选清单甩给它,让它把
`gateway-startup-debug`、`gateway-tls-debug`、`gateway-port-conflict` 三个窄技能
合并成一个 `gateway-troubleshooting` 伞技能(§5)。**默认关**。

环就闭在这里:**第 4 步的计数器,决定了第 6 步谁被淘汰;第 7 步的合并,决定了第 3 步
系统提示词里那一行 57 字讲的是"一个 bug"还是"一类问题"。**

### 1.2 三个存储介质,三种寿命

| 介质 | 路径 | 写者 | 寿命 |
|---|---|---|---|
| 技能包(知识本体) | `~/.hermes/skills/<name>/` | agent / `/learn` / curator | 永久,归档不删除 |
| 使用台账(计数器) | `~/.hermes/skills/.usage.json` | `tools/skill_usage.py` | 随技能;归档保留 |
| 调度器状态 | `~/.hermes/skills/.curator_state` | `agent/curator.py` | 单文件,7 个字段 |
| 逐次运行报告 | `~/.hermes/logs/curator/<stamp>/` | `agent/curator.py` | 无上限清理(§10 ■-5) |
| 快照 | `~/.hermes/skills/.curator_backups/<utc-id>/` | `agent/curator_backup.py` | 默认留最近 5 份 |

---

## 2. 触发时机 —— 异步,而且"空闲判据"在真实调用路径上是死的

### 2.1 三层门

`agent/curator.py:2001 @ 863e313`
```python
def maybe_run_curator(
    *,
    idle_for_seconds: Optional[float] = None,
    on_summary: Optional[Callable[[str], None]] = None,
) -> Optional[Dict[str, Any]]:
    """Best-effort: run a curator pass if all gates pass. Returns the result
    dict if a pass was started, else None. Never raises."""
    try:
        if not should_run_now():
            return None
        # Idle gating: only enforce when the caller provided a measurement.
        if idle_for_seconds is not None:
            min_idle_s = get_min_idle_hours() * 3600.0
            if idle_for_seconds < min_idle_s:
                return None
        return run_curator_review(on_summary=on_summary)
```

静态门在 `should_run_now()` 里:

`agent/curator.py:254 @ 863e313`
```python
    if not is_enabled():
        return False
    if is_paused():
        return False

    state = load_state()
    last = _parse_iso(state.get("last_run_at"))
    if last is None:
```

**首跑不跑**——这是个值得抄的设计:第一次见到没有 `last_run_at` 时,不是立刻跑,而是把
"现在"写进去,把第一次真跑推迟整整一个 interval:

`agent/curator.py:268 @ 863e313`
```python
            state["last_run_at"] = now.isoformat()
            state["last_run_summary"] = (
                "deferred first run — curator seeded, will run after one "
                "interval; use `hermes curator run --dry-run` to preview now"
            )
```

理由(注释自陈):`hermes update` 之后的第一个 gateway tick 不该立刻动用户的技能库。
**代价是"从不启动 CLI 超过一周"的用户永远跑不到**,不过那种用户也没在攒技能。

### 2.2 ▲-1:`min_idle_hours` 在两个真实调用点上都被短路

全仓 `idle_for_seconds` 只有 5 处命中(搜索面:`grep -rn "idle_for_seconds" --include=*.py .`,
含 tests),其中调用点只有两个,**都传 `float("inf")`**:

`cli.py:15126 @ 863e313`
```python
            from agent.curator import maybe_run_curator
            maybe_run_curator(
                idle_for_seconds=float("inf"),  # CLI startup = fully idle
                on_summary=lambda msg: self._console_print(
                    f"[dim #6b7684]💾 {msg}[/]"
                ),
            )
```

`gateway/run.py:26219 @ 863e313`
```python
        if tick_count % CURATOR_EVERY == 0:
            try:
                from agent.curator import maybe_run_curator
                maybe_run_curator(
                    idle_for_seconds=float("inf"),
                    on_summary=lambda msg: logger.info("curator: %s", msg),
                )
```

`gateway/run.py:26157 @ 863e313`
```python
    CURATOR_EVERY = 60       # ticks — poll hourly (inner gate handles the real cadence)
```

CLI 侧还能勉强自圆其说(启动瞬间确实没在跑 agent);**gateway 侧不能**——那是一个
每 60 tick 转一圈的常驻管家循环,gateway 此刻可能正在处理 Telegram 消息,却无条件声明"完全空闲"。

于是文档这一段整段不成立(整段判定,含它归的标题 `## How it runs`):

`website/docs/user-guide/features/curator.md:19 @ 863e313`
> The curator is triggered by an inactivity check, not a cron daemon. On CLI session start, and on a recurring tick inside the gateway's cron-ticker thread, Hermes checks whether:

`website/docs/user-guide/features/curator.md:22 @ 863e313`
> 2. The agent has been idle long enough (`min_idle_hours`, default **2 hours**).

`website/docs/user-guide/features/curator.md:351 @ 863e313`
> The curator also refuses to run if `min_idle_hours` hasn't elapsed, so on an active dev machine it naturally only runs during quiet stretches.

判据(零成本复现,不需要装依赖):

```verify
python3 -c "print(float('inf') < 2*3600.0)"    # → False,即 idle 门永远放行
```

`config.yaml` 里 `curator.min_idle_hours` 依然被 `hermes_cli/config_defaults.py 行 1847` 写默认值 2、
被 `hermes_cli/web_server.py 行 3503` 回给 Dashboard、被 `web/src/lib/api.ts 行 1796` 和
`apps/desktop/src/types/hermes.ts 行 1386` 声明成前端类型 —— **一个用户可配、UI 可见、
但对行为零影响的旋钮**。tests 里也只断言了 getter 的默认值(`tests/agent/test_curator.py 行 78`),
没有任何用例覆盖调用点。

### 2.3 同步还是异步:两段式

`run_curator_review()` 是**半同步**的:纯函数老化在调用线程里跑完(所以 `hermes curator run`
能立刻打印 `auto: checked=... stale=...`),LLM pass 才丢进线程:

`agent/curator.py:1747 @ 863e313`
```python
    if synchronous:
        _llm_pass()
    else:
        t = threading.Thread(target=_llm_pass, daemon=True, name="curator-review")
        t.start()
```

`hermes curator run` 默认走同步(`synchronous = ... or not background`,`hermes_cli/curator.py 行 225`);
`maybe_run_curator()` 走默认异步。

### 2.4 失败了谁知道 —— 四条通道 + 一个黑洞

`_run_llm_review()` **从不抛异常**,失败被结构化成 `error` 字段:

`agent/curator.py:1985 @ 863e313`
```python
    except Exception as e:
        result_meta["error"] = f"error: {e}"
        result_meta["summary"] = result_meta["error"]
```

四条可见通道:
1. `on_summary` 回调 —— CLI 打 `💾 curator: ...`,gateway 打 `logger.info("curator: %s")`;
2. `.curator_state.last_run_summary` —— `hermes curator status` 读它;
3. `REPORT.md` 顶部一行 `> ⚠ LLM pass error:`(`agent/curator.py 行 1306`);
4. `run.json` 的 `llm_error` 字段。

**黑洞(■-1)**:异步路径用的是 **daemon 线程**,而 `last_run_at` 在起线程**之前**就已落盘:

`agent/curator.py:1577 @ 863e313`
```python
    state = load_state()
    if not dry_run:
        state["last_run_at"] = start.isoformat()
        state["run_count"] = int(state.get("run_count", 0)) + 1
    prefix = "dry-run auto: " if dry_run else "auto: "
    state["last_run_summary"] = f"{prefix}{auto_summary}"
    save_state(state)
```

后果:CLI 启动触发的合并 pass 要跑 50~100 次 API 调用(见 §6.1),而用户随时会 Ctrl-D 退出。
进程一退,daemon 线程被直接杀掉 —— **技能库可能已经被改了一半(几个技能进了 `.archive/`、
伞技能只 patch 了一节),但 `REPORT.md` 和 `run.json` 永远不会被写**,
`last_run_summary` 停在 `auto: ...` 那半句,`last_run_at` 却已经推进,下一次要等满一个 interval。
兜底只剩 §7 的 pre-run 快照 —— 而用户不会知道自己需要回滚,因为**没有任何东西告诉他刚才发生了什么**。
注释自陈这个 save 是"防崩溃中途不重复触发"(1572-1576 行),它确实做到了;
但它同时也**把"中断"变成了静默**。

**■-2(次级)**:`hermes curator run` 在同步模式下 LLM pass 失败也**返回 0**
(`hermes_cli/curator.py 行 274` 无条件 `return 0`),错误只在 stdout 文本里。CI/脚本无法据退出码判定。

---

## 3. 数据形状 —— `.curator_state` 只有 7 个字段

`agent/curator.py:85 @ 863e313`
```python
def _state_file() -> Path:
    return get_hermes_home() / "skills" / ".curator_state"


def _default_state() -> Dict[str, Any]:
    return {
        "last_run_at": None,
        "last_run_duration_seconds": None,
        "last_run_summary": None,
        "last_run_summary_shown_at": None,
        "last_report_path": None,
        "paused": False,
        "run_count": 0,
    }
```

写是原子的:

`agent/curator.py:116 @ 863e313`
```python
def save_state(data: Dict[str, Any]) -> None:
    path = _state_file()
    try:
        atomic_json_write(path, data, indent=2, sort_keys=True)
    except Exception as e:
        logger.debug("Failed to save curator state: %s", e, exc_info=True)
```

读是**白名单合并**——只吸收 `_default_state()` 里已有的键,加上下划线开头的私有键:

`agent/curator.py:106 @ 863e313`
```python
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            base = _default_state()
            base.update({k: v for k, v in data.items() if k in base or k.startswith("_")})
            return base
```

这是个好模式:**旧版本写的未知键被静默丢弃,新版本加的键自动有默认值**,降级/升级都不炸。
代价是回写会**永久删除**降级时无法识别的键(下一次 `save_state` 就写不回去了)——
所以下划线私有键那个 `or k.startswith("_")` 逃生口是必要的。

`last_run_summary_shown_at` 是"只提示一次"的标记,唯一使用方是
`hermes_cli/update_cmd.py 行 513`(`hermes update` 之后把上一轮 curator 结论展示一次)。

**配置项全表**(`_load_config()` 读 `config.yaml` 的 `curator:` 段,缺文件容错):

| 键 | 默认 | 读取处 | 备注 |
|---|---|---|---|
| `enabled` | `True` | curator.py 157 | 缺省 ON |
| `interval_hours` | 168 | curator.py 163 | |
| `min_idle_hours` | 2 | curator.py 171 | **实际无效**(§2.2) |
| `stale_after_days` | 30 | curator.py 179 | |
| `archive_after_days` | 90 | curator.py 187 | |
| `prune_builtins` | `True` | curator.py 201 | 内置技能也进候选 |
| `consolidate` | `False` | curator.py 217 | LLM pass 开关 |
| `backup.enabled` | `True` | curator_backup.py 166 | |
| `backup.keep` | 5 | curator_backup.py 175 | `max(1, n)` |

所有 getter 都是 `try/except (TypeError, ValueError)` 回落默认值,**没有一处会因为配置写错而抛**。

`agent/curator.py:204 @ 863e313`
```python
def get_consolidate() -> bool:
    """Whether the curator runs its LLM consolidation (umbrella-building) pass.

    OFF by default. When off, a curator run does ONLY the deterministic
    inactivity prune (mark stale / archive long-unused skills) and skips the
    forked aux-model review entirely — no consolidation, no umbrella-building,
    no aux-model cost. Set ``curator.consolidate: true`` to opt back into the
    LLM pass that merges overlapping skills into class-level umbrellas.
```

---

## 4. 纯函数老化机 —— `apply_automatic_transitions()`

这是 curator 的**默认全部行为**(consolidate 默认关)。一个 `for` 循环,三档判定,零 LLM。

`agent/curator.py:326 @ 863e313`
```python
    counts = {"marked_stale": 0, "archived": 0, "reactivated": 0, "checked": 0, "seeded": 0}

    for row in _u.curated_report():
        counts["checked"] += 1
        name = row["name"]
        if row.get("pinned"):
            continue
```

**豁免 1:pin。** **豁免 2:被任何 cron job 引用的技能**(含暂停/禁用的 job):

`agent/curator.py:340 @ 863e313`
```python
        if name in cron_referenced:
            continue

        # First sight of a curation-eligible skill with no persisted record
        # (e.g. a newly-eligible built-in): anchor its clock to now and defer.
        if not row.get("_persisted", True):
            _u.seed_record_if_missing(name)
            counts["seeded"] += 1
            continue
```

cron 豁免的理由写在 333-339 行的注释里,值得原样记住:**调度器只在 job 真正 fire 时才 bump 使用计数,
所以"每季度跑一次的 job"和"暂停中的 job"引用的技能会在两次 fire 之间被判成 90 天没用而归档,
下次 fire 时找不到技能。** 这是"活跃度计数器"这类设计的通病:**计数器只记录"被使用",
不记录"被依赖"**,而依赖是静态的、不会自己产生事件。解法就是把静态引用图接进来当第二信号源。

`_persisted` 那一段是 `prune_builtins` 打开时的**时钟锚定**:内置技能从来没有 `.usage.json` 记录,
如果直接按"最后活动时间 = 无"处理,开关一打开就会整片归档。所以第一次见到只播种、不判决。

三档判定:

`agent/curator.py:363 @ 863e313`
```python
        never_used = int(row.get("use_count", 0) or 0) == 0
        if never_used and anchor > stale_cutoff:
            # Younger than the stale window — leave it alone entirely.
            if current == _u.STATE_STALE:
                _u.set_state(name, _u.STATE_ACTIVE)
                counts["reactivated"] += 1
            continue

        if anchor <= archive_cutoff and current != _u.STATE_ARCHIVED:
            ok, _msg = _u.archive_skill(name)
            if ok:
                counts["archived"] += 1
        elif anchor <= stale_cutoff and current == _u.STATE_ACTIVE:
            _u.set_state(name, _u.STATE_STALE)
            counts["marked_stale"] += 1
        elif anchor > stale_cutoff and current == _u.STATE_STALE:
            # Skill got used again after being marked stale — reactivate.
            _u.set_state(name, _u.STATE_ACTIVE)
            counts["reactivated"] += 1
```

**`use_count == 0` 的宽限地板**是这段里最值得抄的判断:一个从没被用过的技能,
它的 0 是"证据缺失"而不是"无用的证据"——刚创建的技能可能只是触发条件还没出现。
所以 use=0 的技能在 `stale_after_days` 内**完全不碰**。同一条原则在 LLM 提示词里
以硬规则 #4 又写了一遍(`agent/curator.py 行 452-459`),**两个执行体各自独立地被约束了一次**。

**◇-1:`seeded` 计数被算了但没被展示。** `counts["seeded"]` 进了 `run.json` 的
`auto_transitions`,但 `REPORT.md` 的"Auto-transitions"小节只印四项:

`agent/curator.py:1311 @ 863e313`
```python
    lines.append(f"- checked: {auto.get('checked', 0)}")
    lines.append(f"- marked stale: {auto.get('marked_stale', 0)}")
    lines.append(f"- archived (no LLM, pure time-based staleness): {auto.get('archived', 0)}")
    lines.append(f"- reactivated: {auto.get('reactivated', 0)}")
```

后果很轻但真实:`prune_builtins` 首次打开那一轮,几十个内置技能被播种、报告上却是全零,
用户会以为 curator 什么都没干。

---

## 5. LLM 合并 pass —— 一段 154 行的提示词 + 三路证据归一

### 5.1 提示词本身就是设计文档

`CURATOR_REVIEW_PROMPT`(`agent/curator.py 行 417-570`)是全仓最长的单条提示词之一。
它反复防的是同一个失败模式:**模型倾向于"每个技能都有独特触发条件,所以都该保留"**。

`agent/curator.py:460 @ 863e313`
```python
    "5. DO NOT reject consolidation on the grounds that 'each skill has "
    "a distinct trigger'. Pairwise distinctness is the wrong bar. The "
    "right bar is: 'would a human maintainer write this as N separate "
    "skills, or as one skill with N labeled subsections?' When the "
    "answer is the latter, merge.\n\n"
```

以及一条**量化的完成度下限**——这是很反直觉但很有效的一招:

`agent/curator.py:545 @ 863e313`
```python
    "Expected output: real umbrella-ification. Process every obvious "
    "cluster. If you end the pass with fewer than 10 archives, you "
    "stopped too early — go back and look at the clusters you left "
    "alone.\n\n"
```

安全侧的硬规则:不删只归档(#2)、不碰 pin(#3)、不碰受保护内置(#3b)、不碰 cron 引用(#3c)、
不拿 use_count 当合并/裁剪理由(#4)。还有一整节 "Package integrity" 讲
**不许只把 `SKILL.md` 拍平成别人的 `references/<old>.md`**——因为技能是一个目录包,
`SKILL.md` 里可能有指向 `scripts/`、`templates/` 的相对链接,拍平之后链接全断。

### 5.2 dry-run 是提示词前缀,不是代码分支

`agent/curator.py:390 @ 863e313`
```python
CURATOR_DRY_RUN_BANNER = (
    "═══════════════════════════════════════════════════════════════\n"
    "DRY-RUN — REPORT ONLY. DO NOT MUTATE THE SKILL LIBRARY.\n"
    "═══════════════════════════════════════════════════════════════\n"
```

**取舍要看清楚**:dry-run 的"不改动"是**靠提示词请求模型自律**,不是靠工具层禁写。
提示词自己承认这一点:

`agent/curator.py:411 @ 863e313`
```python
    "If you accidentally take a mutating action, say so explicitly in "
    "the summary so the reviewer can revert it.\n"
```

代码层面 dry-run 确实做了两件真事:跳过 `apply_automatic_transitions`、不推进 `last_run_at`
(`agent/curator.py 行 1533-1544`、`1578`)。但 fork 拿到的工具集**与实跑完全相同**。
一个不听话的模型在 dry-run 里照样能 `mv` 目录。**同时**,dry-run 还跳过了 pre-run 快照
(§7,`if dry_run:` 分支里没有 `snapshot_skills`)——**风险最低的模式反而没有安全网**。

### 5.3 归档结果的三路证据归一(本簇最精巧的一段)

一次合并跑完,代码要回答一个问题:"消失的这 12 个技能,哪些是**被并进伞技能**(内容还在),
哪些是**被单纯裁掉**(内容没了)?"——这直接决定给用户看的是 `a → b` 还是 `a — pruned`。

三个信号源,按可信度排序:

1. **模型在 delete 调用上自报的 `absorbed_into`**(最权威,`_extract_absorbed_into_declarations`);
2. **模型最终回复里的 YAML 结构块**(`_parse_structured_summary`);
3. **对本轮全部 `skill_manage` 工具调用做子串审计**(`_classify_removed_skills`,ground truth)。

`agent/curator.py:883 @ 863e313`
```python
    Rules (evaluated in order; first match wins):
    - **Model-declared `absorbed_into` at delete time is authoritative.** Any
      entry in ``absorbed_declarations`` beats every other signal. This is
      the model telling us directly, at the moment of deletion, what it did.
      ``into != ""`` and target exists → consolidated. ``into == ""`` →
      pruned. ``into != ""`` but target doesn't exist → hallucination; fall
      through to the usual signals.
```

**幻觉检测是这套设计的核心**:模型可能声称并进了一个**运行结束后不存在**的伞技能。
代码用"运行后仍存在的技能名 ∪ 本轮新建的技能名"当 `destinations` 集合做存在性校验:

`agent/curator.py:964 @ 863e313`
```python
        if mc and mc.get("into") not in destinations:
            if hc:
                consolidated.append({
                    "name": name,
                    "into": hc["into"],
                    "source": "tool-call audit (model named missing umbrella)",
                    "reason": "",
                    "evidence": hc.get("evidence", ""),
                    "model_claimed_into": mc["into"],
                })
```

而且这个降级**对用户可见**,不是默默替换:

`agent/curator.py:1357 @ 863e313`
```python
            if entry.get("model_claimed_into"):
                lines.append(
                    f"  ⚠ The curator's summary named `{entry['model_claimed_into']}` "
                    "as the umbrella but that skill doesn't exist post-run; "
                    "showing the tool-call audit's finding instead."
                )
```

子串审计侧也做了防误报:文件路径按**完整路径段**匹配(`api` 不该命中
`references/api-design.md`),内容字段按**词边界正则**匹配(`test` 不该命中 `latest`):

`agent/curator.py:711 @ 863e313`
```python
                    if key == "file_path":
                        matched = _needle_in_path_component(needle, hay)
                    else:
                        matched = bool(
                            re.search(rf'\b{re.escape(needle)}\b', hay)
                        )
```

**■-3(潜在)**:`re.escape(needle)` 之后用 `\b` 包夹。技能名里常有连字符
(`pr-triage-salvage`),而 `-` 在正则里是非单词字符,`\b` 在 `-` 两侧的行为依赖相邻字符,
`needles` 集合里还刻意放了 `name.replace("-", "_")` 这种变体。这段没有对
"以非单词字符开头/结尾的技能名"做用例(如 `_tmp` / `2fa-setup`),边界匹配可能漏。
**未取证到真实误判**,只作为读代码时的疑点移交。

### 5.4 合并要连 cron 一起改

技能被并进伞技能后,引用旧名字的 cron job 会在下次 fire 时加载失败。所以报告写入路径里
顺手改写了 cron 引用:

`agent/curator.py:1209 @ 863e313`
```python
        if consolidated_map or pruned_names:
            from cron.jobs import rewrite_skill_refs as _rewrite_cron_refs
            cron_rewrites = _rewrite_cron_refs(
                consolidated=consolidated_map,
                pruned=pruned_names,
            )
```

**结构上的怪味道**:这是**副作用**,却挂在一个名叫 `_write_run_report()` 的函数里。
一个"写报告"的函数会修改 `~/.hermes/cron/jobs.json`。若报告写入路径将来被加条件跳过
(比如"无变更就不写报告"),cron 改写会跟着一起消失。记为 ◇-2。

---

## 6. 模型调用 —— 谁付费、跑多久、失败怎么退化

### 6.1 fork 的形状

`agent/curator.py:1917 @ 863e313`
```python
        review_agent = AIAgent(
            model=_model_name,
            provider=_resolved_provider,
            api_key=_api_key,
            base_url=_base_url,
            api_mode=_api_mode,
            credential_pool=_credential_pool,
            request_overrides=_request_overrides,
            **_agent_kwargs,
            enabled_toolsets=["skills", "terminal"],
```

`agent/curator.py:1932 @ 863e313`
```python
            max_iterations=9999,
            quiet_mode=True,
            platform="curator",
            skip_context_files=True,
            skip_memory=True,
        )
```

`max_iterations=9999` 是全仓最高的迭代上限之一,注释解释是一次扫库要 50~100 次 API 调用。
**没有 token 预算上限、没有墙钟超时**——只有模型自己决定何时停。

### 6.2 谁付费:用户自己,默认是主模型

三级优先级:

`agent/curator.py:1777 @ 863e313`
```python
    if _task_provider and _task_provider != "auto" and _task_model:
        return _ReviewRuntimeBinding(
            _task_provider,
            _task_model,
            _strip_aux_credential(_cur_task.get("api_key")),
            _strip_aux_credential(_cur_task.get("base_url")),
            _merge_request_overrides({}, _cur_task.get("extra_body")),
        )
```

1. `auxiliary.curator.{provider,model}`(规范辅助任务槽);
2. `curator.auxiliary.{provider,model}`(遗留 schema,命中会打一条 deprecation info 日志);
3. 落到主 chat 模型 `model.{provider, default|model}`。

**▲-2:`auxiliary.curator.timeout` 是个不生效的键。** 文档教用户配它:

`website/docs/user-guide/features/curator.md:78 @ 863e313`
> auxiliary:
>   curator:
>     provider: openrouter
>     model: google/gemini-3-flash-preview
>     timeout: 600               # generous — reviews can take several minutes

代码侧 `_resolve_review_runtime()` 只取 `provider / model / api_key / base_url / extra_body`
五项,**没有 timeout**;而读 `auxiliary.{task}.timeout` 的唯一函数
`agent/auxiliary_client.py 行 7561` 的 `_get_task_timeout` 只被 `auxiliary_client.py` 自己调用
(搜索面:`grep -rn "_get_task_timeout" --include=*.py .`,4 处命中全在 `auxiliary_client.py`
与其测试里),而 curator 走的是 `run_agent.AIAgent` 这条主链路,不经过 `auxiliary_client`。
`config_defaults.py 行 1010` 还给它写了 `"timeout": 600` 和一段"因为审阅要跑几分钟所以给得宽松"的注释。
**结论:配了不报错,也不起作用。** 同一条断言也适用于 `agent/curator.py 行 1813` 那句自陈
(把 `timeout` 列进"已接通的 aux 槽字段")。

### 6.3 fork 的隔离面(四个开关)

- `skip_context_files=True` / `skip_memory=True` —— 不加载用户的上下文文件与长期记忆;
- `quiet_mode=True` + stdout/stderr 重定向到 `/dev/null`;
- 递归自锁:

`agent/curator.py:1938 @ 863e313`
```python
        # Disable recursive nudges — the curator must never spawn its own review.
        review_agent._memory_nudge_interval = 0
        review_agent._skill_nudge_interval = 0
```

- **写来源打标**,这条最关键:

`agent/curator.py:1948 @ 863e313`
```python
        review_agent._memory_write_origin = "background_review"
```

它让 `tools/skill_manager_tool.py` 里那道**只对自主写生效**的硬闸打开。那道闸比前台严格:

`tools/skill_manager_tool.py:328 @ 863e313`
```python
        if skill_usage.get_record(name).get("pinned"):
            return {
                "success": False,
                "error": (
                    f"Refusing background curator {action} for pinned skill "
                    f"'{name}': pinned skills are off-limits to autonomous "
                    "maintenance. Ask the user to run "
                    f"`hermes curator unpin {name}` if they want it changed."
                ),
            }
```

**这是全簇最值得抄的一条**:同一个工具,**根据"有没有人在回路里"给出不同的权限**。
前台 `_pinned_guard` 只挡 delete(用户可以自己改 pin 住的技能),后台一律挡死
(没人能对这次编辑表示同意)。

**但是 —— pin 的保护面有个缺口(■-4)。** fork 的工具集是 `["skills", "terminal"]`,
提示词明确教它用 `terminal` 的 `mv` 把技能目录搬进 `.archive/`
(`agent/curator.py 行 496-498`)。`terminal` 路径上**没有** pin 检查,pin 完全靠提示词规则 #3。
而且候选清单**并没有把 pin 过滤掉**,是原样喂给模型的:

`agent/curator.py:1481 @ 863e313`
```python
        lines.append(
            f"- {r['name']}  "
            f"provenance={r.get('provenance', 'agent')}  "
            f"state={r['state']}  "
            f"pinned={'yes' if r.get('pinned') else 'no'}  "
```

对比:受保护内置(`plan`)是在 `tools/skill_usage.py 行 377` 的
`list_agent_created_skill_names()` 里**真的被过滤掉**的。所以 AGENTS.md 那句话半真半假:

`AGENTS.md:1038 @ 863e313`
> - Pinned skills are exempt from every auto-transition and from the
>   LLM review pass.

"exempt from every auto-transition" **成立**(curator.py 行 331);
"exempt from the LLM review pass" **不成立**——pin 的技能出现在候选清单里,
`skill_manage` 那条路被硬闸挡住,`terminal mv` 那条路只有提示词。记 ▲-3。

### 6.4 失败退化:全放弃,不降级

没有任何模型级 fallback。provider 解析失败只记 debug 日志、留空,然后 `AIAgent` 用空
provider/model 构造,大概率直接失败:

`agent/curator.py:1903 @ 863e313`
```python
    except Exception as e:
        logger.debug("Curator provider resolution failed: %s", e, exc_info=True)
```

整个 LLM pass 是**尽力而为的增量**:失败了,前面那步纯函数老化的结果已经落盘且有效。
**这个分层是对的**——"必须发生的"(老化)不依赖"最好能发生的"(合并)。

### 6.5 ■-5 / ▲-4:无候选时仍然会真花一次模型钱

`agent/curator.py:1473 @ 863e313`
```python
def _render_candidate_list() -> str:
    """Human/agent-readable list of curator-managed skills with usage stats."""
    rows = skill_usage.curated_report()
    if not rows:
        return "No curator-managed skills to review."
```

`agent/curator.py:1643 @ 863e313`
```python
            candidate_list = _render_candidate_list()
            if "No agent-created skills" in candidate_list:
                final_summary = f"{prefix}{auto_summary}; llm: skipped (no candidates)"
                llm_meta = {
                    "final": "",
                    "summary": "skipped (no candidates)",
                    "model": "",
                    "provider": "",
                    "tool_calls": [],
                    "error": None,
                }
```

**两个字符串对不上**。判据(零成本复现):

```verify
python3 -c "print('No agent-created skills' in 'No curator-managed skills to review.')"   # → False
```

`"No agent-created skills"` 这个字面量在**全仓只出现这一处**(搜索面:
`grep -rn "No agent-created skills" --include=*.py --include=*.md --include=*.ts --include=*.tsx .`,
1 处命中,即该 `if` 本身),说明生产方的返回串曾被改名(`agent-created` → `curator-managed`),
消费方没跟着改。

后果:当 `consolidate: true` 且技能库为空时,代码走 else 分支,把
`"No curator-managed skills to review."` 当候选清单**真的发给模型**,
带着 `max_iterations=9999` 的 fork 跑一趟。花的是真钱,产出为零。

对应文档整段作废(它归 `## Per-run reports` 标题下的 `:::note` 块):

`website/docs/user-guide/features/curator.md:321 @ 863e313`
> :::note No candidates? Report shows `(not resolved)`
> When the curator has **no agent-created skills** to review, the LLM review pass
> is skipped entirely. The report header will show

文档描述的现象(`Model: (not resolved) via (not resolved)`、`Duration: 0s`)在
`consolidate: true` 时**不会出现**——模型被解析了、被调用了、耗时不是 0。
(在默认 `consolidate: false` 下报告确实显示 `(not resolved)`,但那是被 1598 行的
consolidation 门挡住的,**跟有没有候选无关** —— 文档把两个不同的原因写成了一个。)

`tests/agent/test_curator.py` / `test_curator_reports.py` / `test_curator_run.py`
里对 `no candidates`、`No curator-managed`、`No agent-created` 三个模式**零命中**,
即这条分支从未被测试覆盖。

---

## 7. `curator_backup.py` —— 757 行专门做备份,它防的是什么

### 7.1 它防的不是"文件损坏",是"一次不可撤销的自主批量改写"

`agent/curator_backup.py:1 @ 863e313`
```python
"""Curator snapshot + rollback.

A pre-run snapshot of ``~/.hermes/skills/`` (excluding ``.curator_backups/``
itself) is taken before any mutating curator pass. Snapshots are tar.gz
files under ``~/.hermes/skills/.curator_backups/<utc-iso>/`` with a
companion ``manifest.json`` describing the snapshot (reason, time, size,
counted skill files). Rollback picks a snapshot, moves the current
``skills/`` tree aside into another snapshot so even the rollback itself
is undoable, then extracts the chosen snapshot into place.
```

被坑过的形状很具体,从"包含什么"的清单能倒推出来 —— 每一项都是一次"回滚完发现还是不对":

`agent/curator_backup.py:18 @ 863e313`
```python
  - ``.usage.json`` (usage telemetry — needed to rehydrate state cleanly)
  - ``.archive/`` (so rollback restores previously-archived skills too)
  - ``.curator_state`` (so rolling back also restores the last-run-at
    pointer — otherwise the curator would immediately re-fire on the next
    tick)
  - ``.bundled_manifest`` (so protection markers stay consistent)
  - ``.curator_suppressed`` (so rollback restores the set of pruned built-ins
    the re-seeder must leave archived)
```

`.curator_state` 那条尤其像**被咬过一口**:回滚了技能树却没回滚 `last_run_at`,
下一个 tick 立刻又跑一遍 curator,把刚恢复的东西再合并一次。

第五类坑是**跨文件的引用一致性**:

`agent/curator_backup.py:30 @ 863e313`
```python
curator's consolidation pass rewrites those in place via
``cron.jobs.rewrite_skill_refs()``. Without capturing the pre-run state,
rolling back the skills tree would leave cron jobs pointing at the
umbrella skills even though the narrow skills they were originally
configured with have been restored. We store the whole jobs.json for
fidelity but rollback only touches the ``skills``/``skill`` fields — the
rest (schedule, next_run_at, enabled, prompt, etc.) is live state and
we leave it alone.
```

**"全量备份、外科式恢复"** —— 备份存整个 `jobs.json`(保真),恢复只动 `skills`/`skill`
两个字段(因为 `next_run_at`、`enabled` 是快照之后被调度器和用户改过的活状态)。
这是备份设计里非常成熟的一手:**备份的粒度和恢复的粒度不必相同**。

### 7.2 排除清单只有两项,理由都写了

`agent/curator_backup.py:59 @ 863e313`
```python
# Entries under skills/ that should NEVER be rolled up into a snapshot.
# .hub/ is managed by the skills hub; rolling it back would break lockfile
# invariants. .curator_backups is the backup dir itself — recursion bomb.
_EXCLUDE_TOP_LEVEL = {".curator_backups", ".hub"}
```

### 7.3 回滚的三段式

`agent/curator_backup.py:608 @ 863e313`
```python
    try:
        # Protect the target from this snapshot's prune step: at the steady
        # keep limit, pruning the oldest snapshot would otherwise delete the
        # very snapshot we are about to extract from.
        snapshot_skills(
            reason=f"pre-rollback to {target.name}",
            protect_ids={target.name},
        )
```

`protect_ids` 这个细节值得单独记:回滚前的安全快照会触发 `_prune_old`,
在 keep=5 的稳态下**恰好会删掉最老的一份 —— 而那可能正是你要恢复的那份**。
这是"清理策略与使用者在同一次调用里打架"的经典 bug,作者显式挡掉了。

`agent/curator_backup.py:293 @ 863e313`
```python
def _prune_old(keep: int, protect: Optional[Set[str]] = None) -> List[str]:
    """Delete regular snapshots beyond the newest *keep*. Returns deleted
    ids. Snapshot ids in *protect* are never deleted even when they fall
    outside the keep window — rollback() uses this so the mandatory
    pre-rollback safety snapshot can never evict the very snapshot being
    restored. Staging dirs (``.rollback-staging-*``) are implementation
    detail and pruned independently on every call."""
```

解包前把现有内容整体 move 进 staging,失败再 move 回来;而 `_unstage` 处理了
`shutil.move` 的一个真实陷阱:

`agent/curator_backup.py:547 @ 863e313`
```python
    ``shutil.move`` moves *into* an existing destination directory rather than
    replacing it, so a partially-completed extract leaves debris that would
    otherwise bury the user's real skill one level deeper
    (``skills/foo/foo/``) while the tree still looks populated. Clear whatever
    the failed extract created at each original path first. The staged copy is
    authoritative, and the pre-rollback safety snapshot is the undo handle for
    the extract's own output.
```

而且**恢复失败会如实上报**,不谎称成功:

`agent/curator_backup.py:679 @ 863e313`
```python
        if unrestored:
            # Do not claim a clean restore we did not achieve, and keep the
            # staging dir so the entries can be recovered by hand.
            return (
```

解包做了路径穿越防护(先扫全部 member 拒绝 `/` 开头与 `..`,再优先用 Py3.12 的 `filter="data"`):

`agent/curator_backup.py:652 @ 863e313`
```python
            for member in tf.getmembers():
                name = member.name
                if name.startswith("/") or ".." in Path(name).parts:
                    raise tarfile.TarError(
                        f"refusing to extract unsafe path: {name!r}"
                    )
```

### 7.4 它自己有没有同样的坑 —— 有三个

**■-6:快照发布不是原子的。** curator 自己的状态文件用 `atomic_json_write`(§3),
但快照的两个产物都是**就地直写**:

`agent/curator_backup.py:261 @ 863e313`
```python
    archive = dest / "skills.tar.gz"
    try:
        # Stream into the tarball — no tempdir copy needed.
        with tarfile.open(archive, "w:gz", compresslevel=6) as tf:
```

`agent/curator_backup.py:211 @ 863e313`
```python
    (dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
```

清理只挂在 `except (OSError, tarfile.TarError)` 上(279-286 行),**SIGKILL / 断电 / OOM
不会走到那里**。而 `_resolve_backup(None)` 挑"最新的、有 `skills.tar.gz` 的目录":

`agent/curator_backup.py:394 @ 863e313`
```python
    candidates = [
        c for c in sorted(backups.iterdir(), reverse=True)
        if c.is_dir() and _ID_RE.match(c.name) and (c / "skills.tar.gz").exists()
    ]
    return candidates[0] if candidates else None
```

**存在性检查而非完整性检查**:一个被截断的 tar.gz 照样"存在",于是
`hermes curator rollback`(不带 id)会选中它。好消息是解包失败有 staging 兜底,
用户不会丢数据;坏消息是**默认回滚目标是一份坏档,用户得自己发现并显式指定上一份**。
标准解法(写 `skills.tar.gz.partial` → `os.replace`)成本极低,这里没做。
`manifest.json` 同理:半截 JSON → `_read_manifest` 返回 `{}` → `list_backups` 照列不误,
只是 reason/size 字段变默认值。

**■-7:备份与被备份对象同盘同目录。** `.curator_backups/` 就在 `~/.hermes/skills/` 里面。
磁盘满、误删 `~/.hermes/skills`、文件系统损坏 —— 一次全没。它防的是"逻辑改写",
**完全不防"介质故障"**,而模块名叫 backup 容易让人以为它防后者。

**■-8:快照失败静默继续。** 这个是**有意为之**且写了理由,但代价必须记清楚:

`agent/curator.py:1546 @ 863e313`
```python
        # Pre-mutation snapshot — best-effort, never blocks the run. A
        # failed snapshot logs at debug and continues (the alternative is
        # that a transient disk issue silently disables curator forever,
        # which is worse). Users who want to require snapshots can disable
        # curator entirely until they can fix disk space.
```

`snapshot_skills()` 返回 `None` 有四种原因:配置关了、`skills/` 不存在、建目录失败、tar 失败。
调用方只看 `snap is not None` 来决定要不要打一行提示,**四种情况一视同仁**;
日志级别是 `debug`,默认不可见。于是"磁盘满导致备份失败"和"用户主动关了备份"在运维视角上**长得一模一样**,
而前者紧接着就是一次**没有安全网的自主批量改写**。

**docstring 漂移(非 ▲,不计入文档冲突指标)**:`rollback()` 的 docstring 说安全快照落在
`.curator_backups/pre-rollback-<ts>/`:

`agent/curator_backup.py:576 @ 863e313`
```python
      2. Take a safety snapshot of the CURRENT skills tree under
         ``.curator_backups/pre-rollback-<ts>/`` so the rollback itself is
         undoable.
```

实际上 `snapshot_skills()` 的目录名恒为 `_utc_id()`(`dest = backups / snap_id`,第 254 行),
`pre-rollback to <id>` 只是写进 `manifest.json` 的 `reason` 字段。目录名规则:

`agent/curator_backup.py:137 @ 863e313`
```python
def _utc_id(now: Optional[datetime] = None) -> str:
    """UTC ISO-ish filesystem-safe timestamp: ``2026-05-01T13-05-42Z``."""
```

对运维有实质影响:按 docstring 去 `ls .curator_backups/pre-rollback-*` 会一无所获。

---

## 8. `agent/insights.py` —— 一个只读报表引擎

### 8.1 形状:无状态、无存储、纯查询

`agent/insights.py:93 @ 863e313`
```python
    def __init__(self, db):
        """
        Initialize with a SessionDB instance.

        Args:
            db: A SessionDB instance (from hermes_state.py)
        """
        self.db = db
        self._conn = db._conn
```

**它不写任何东西**(除了 `generate()` 开头 drain 一次 SessionDB 的异步计数队列):

`agent/insights.py:141 @ 863e313`
```python
        # Token/cost totals may still sit on the SessionDB's async
        # accounting queue; drain so the report reflects exact counters.
        # (self.db may be a raw sqlite3 connection in tests — guard.)
        flush = getattr(self.db, "flush_token_counts", None)
        if callable(flush):
            flush()
```

产出是一个 dict(`days / overview / models / platforms / tools / skills / activity / top_sessions`),
两个渲染器:`format_terminal()`(CLI,带 `█` 条形图)与 `format_gateway()`(聊天平台,更短)。
四个调用方:`cli.py 行 11503`、`hermes_cli/main.py 行 11090`、`gateway/slash_commands.py 行 5161`、
`hermes_cli/web_server.py 行 14123`。**没有去重、没有老化、没有增长** —— 因为它根本不存东西,
每次都从 `sessions` / `messages` / `session_model_usage` 三张表现算,窗口由 `days` 参数给。

### 8.2 ◇-3:两套"技能使用统计",口径不同、来源不同、名字一样

| | curator 用的 | `/insights` 用的 |
|---|---|---|
| 来源 | `~/.hermes/skills/.usage.json` | `state.db` 的 `messages.tool_calls` |
| "使用"的定义 | `bump_use()`:技能**被加载进提示词** | `skill_view` **工具调用**次数 |
| 字段名 | `use_count` / `view_count` / `patch_count` | `view_count` / `manage_count` |
| 报表里叫 | `use` / `view` | `total_skill_loads` / `total_skill_edits` |

`agent/insights.py:400 @ 863e313`
```python
                if tool_name not in {"skill_view", "skill_manage"}:
                    continue
```

`agent/insights.py:828 @ 863e313`
```python
        return {
            "summary": {
                "total_skill_loads": total_skill_loads,
                "total_skill_edits": total_skill_edits,
```

而 `total_skill_loads` 累加的是 `view_count`(`insights.py 行 800`),也就是 `skill_view` 调用数。
**后果:一个被 `skill_bundles` 自动加载进提示词、agent 从没显式 `skill_view` 过的技能,
在 `/insights` 的 "Top Skills" 里是 0 次"loads",但在 `hermes curator status` 里 `use_count` 可能很高。**
两个界面对同一个技能会给出互相矛盾的"用得多不多"。这不是 bug(两个系统各自自洽),
是**同名不同义**;要重实现的话,这两套计数应该合成一套或明确改名。

### 8.3 一段值得抄的防御:`INDEXED BY` 的硬依赖与探测回退

`agent/insights.py:245 @ 863e313`
```python
    # The pin is a HARD dependency: SQLite raises ``no such index`` when the
    # named index is absent. That happens in practice — the web dashboard's
    # usage analytics open the DB ``read_only=True`` (skipping
    # ``_init_schema``), so a state.db created by an older writer has no
    # partial index yet. ``__init__`` probes for the index once and falls
    # back to the unpinned (still-correct, just optimizer-chosen) variants.
```

`agent/insights.py:115 @ 863e313`
```python
        if not self._has_assistant_calls_index:
            _strip = f" INDEXED BY {self._MESSAGES_ASSISTANT_CALLS_INDEX}"
            # Loop over every pinned statement so adding a new one can't
            # forget its strip line (which would be a hard `no such index`
            # crash on read-only DBs — the exact bug this fallback prevents).
            for _attr in (
                "_GET_TOOL_CALLS_WITH_SOURCE",
                "_GET_TOOL_CALLS_ALL",
                "_GET_SKILL_CALLS_WITH_SOURCE",
                "_GET_SKILL_CALLS_ALL",
            ):
                setattr(self, _attr, getattr(self, _attr).replace(_strip, ""))
```

三个可迁移点:(a) 为了**查询计划确定性**(新库还没 ANALYZE 过)显式 pin 索引;
(b) 承认 pin 是硬依赖,启动时**探测一次**而不是每次 try/except;
(c) **遍历属性名列表**做 strip,而不是逐条写 —— 新增一条 pin 语句时忘记加 strip 会变成硬崩溃,
用循环把"忘记"这件事从可能变成不可能。这一条把"防御写法"和"防御的可维护性"分开处理了,是好范式。

SQL 全部是**类定义期就求值好的常量串**,注释显式点出了为什么:

`agent/insights.py:225 @ 863e313`
```python
    # Pre-computed query strings — f-string evaluated once at class definition,
    # not at runtime, so no user-controlled value can alter the query structure.
```

`source` 这类用户可控值一律走占位符(`self._conn.execute(stmt, (cutoff, source))`)。

### 8.4 两处口径修正,都留了 issue 号

`agent/insights.py:512 @ 863e313`
```python
            # Token totals likewise: the per-model breakdown includes
            # auxiliary usage rows (vision/compression/titles — task
            # dimension in session_model_usage, #23270) plus reconciled
            # residuals, while the sessions counters carry main-loop usage
            # only. Summing the breakdown keeps overview totals consistent
            # with the per-model table and stops `hermes insights`
            # undercounting aux spend (#58592, #9979).
```

即:总览的 token/花费**不从 `sessions` 表加总**,而从 per-model 明细加总 —— 因为
辅助模型(视觉、压缩、起标题)的开销记在 `session_model_usage` 而不在会话主计数器上。
**这正是 curator 那次 fork 的花费会被算进去的地方**(它是一次独立 AIAgent,不是 aux 客户端调用,
是否落进 `session_model_usage` 取决于 fork 自己的记账,超出本轮范围,移交)。

`agent/insights.py:611 @ 863e313`
```python
        Tokens and cost are attributed per model from session_model_usage, so a
        session that switched models mid-flight (via ``/model``) splits across
        every model it used instead of dumping everything on the initial model
        (issue #51607). Sessions without per-model rows — e.g. data written
        before this table existed and not yet backfilled — fall back to their
        single recorded (model, billing_provider) aggregate so nothing is lost.
```

---

## 9. 与 R5 记忆 / 检查点体系的边界 —— 明确判定:**两套并行,零共享**

这是本簇最容易含糊的地方,所以给硬判据。

| 维度 | curator 簇 | R5 已精读的状态/检查点簇 |
|---|---|---|
| 存储 | 文件系统:`~/.hermes/skills/**` + `~/.hermes/logs/curator/**` | SQLite:`state.db`(`sessions` / `messages` / FTS5) + checkpoint 文件 |
| 单位 | **技能包(目录)** | **会话 / 消息 / 检查点** |
| 时间尺度 | 天~月(30/90 天老化) | 回合~会话 |
| 读回方式 | 系统提示词里的技能索引(每条 57 字描述) | 上下文压缩、FTS5 检索、检查点恢复 |
| 谁触发 | interval 到期的后台 tick | 回合内 / 会话生命周期 |
| 撤销机制 | `.curator_backups/` tar.gz + `.archive/` | 会话库自身的恢复路径(R5) |

**代码级判据(负结论,给出搜索面)**:
`agent/curator.py` + `agent/curator_backup.py` 两文件全文对
`hermes_state|SessionDB|state\.db|sqlite|checkpoint|memory|session_id|Checkpoint`
八个模式做 grep,**命中 3 行,全部在 fork 构造处**(1936 `skip_memory=True`、
1939 `_memory_nudge_interval = 0`、1948 `_memory_write_origin`),
且这三行的语义全部是**关闭**记忆参与,不是读写。curator 的全部 import 是:

`agent/curator.py:33 @ 863e313`
```python
from hermes_constants import get_hermes_home
from tools import skill_usage
from utils import atomic_json_write
```

加上 6 个函数内延迟 import:`hermes_cli.config`、`cron.jobs`、`agent.curator_backup`、
`run_agent.AIAgent`、`hermes_cli.runtime_provider`、`yaml`。**`hermes_state` 一次都没有。**

**唯一的间接交点**是 `insights.py`(它读 `state.db`)对 skill 工具调用的统计(§8.2),
而那是一个**观测**关系,不是数据流关系:insights 从不写 `.usage.json`,curator 从不读 `state.db`。

**因此:curator 不是"记忆体系的一部分",它是一个平行的、以文件系统为真相源的知识库园丁。**
真正把两者串起来的是 `agent/background_review.py`(它同时写 memory 与 skill),
那是"生产侧";curator 是"回收侧"。二者共用的只有**技能目录这一块地**,不共用任何状态。

---

## 10. 记号台账

### ▲ 文档与代码矛盾(4 条)

| 编号 | 文档位置(含所归标题) | 文档说 | 代码是 | 判据 |
|---|---|---|---|---|
| ▲-1 | `website/docs/user-guide/features/curator.md 行 19-22`(`## How it runs`)、`:351`(`## Disabling per environment`) | 两个门:interval + `min_idle_hours` 空闲判定 | 两个调用点都传 `float("inf")`,空闲门恒放行;gateway 侧尤其不成立 | §2.2 的 `verify` 块;`grep -rn "idle_for_seconds" --include=*.py .` 全仓 5 处 |
| ▲-2 | `website/docs/user-guide/features/curator.md 行 82`(`### Running the review on a cheaper aux model`) | `auxiliary.curator.timeout: 600` 是有效配置 | `_resolve_review_runtime` 不取 timeout;`_get_task_timeout` 仅被 `auxiliary_client` 自用,curator 走 AIAgent 主链路 | §6.2 |
| ▲-3 | `AGENTS.md 行 1038-1039`(`## Curator (skill lifecycle)` → `Invariants`) | pin 的技能"exempt from ... the LLM review pass" | pin 技能**在候选清单里**;`skill_manage` 有硬闸,`terminal mv` 只有提示词规则 | §6.3;对比 `tools/skill_usage.py 行 377` 对受保护内置的真过滤 |
| ▲-4 | `website/docs/user-guide/features/curator.md 行 320-326`(`## Per-run reports` 下的 `:::note`) | 无候选时"LLM review pass is skipped entirely",报告显示 `(not resolved)` | 该分支字符串对不上,永不命中;`consolidate:true` 时会真发一次请求。默认下的 `(not resolved)` 来自 consolidation 门,与候选数无关 | §6.5 的 `verify` 块 |

### ◎ 文档成立但显著保守(1 条)

- **◎-1** `AGENTS.md 行 1026-1028` 列 `hermes curator` 的 verb 为 11 个
  (`status/run/pause/resume/pin/unpin/archive/restore/prune/backup/rollback`),
  实际 `subs.add_parser(` 有 **15** 个,漏掉 `usage`、`list-unmanaged`、`adopt`、`list-archived`。
  字面为真(列出的都存在),但 "verbs are:" 读起来是穷举。判据:
  `grep -c 'subs.add_parser(' hermes_cli/curator.py` → 15。

### ◇ 代码有、文档无(3 条)

- **◇-1** `apply_automatic_transitions` 的 `seeded` 计数进了 `run.json` 但不进 `REPORT.md`(§4)。
- **◇-2** cron 技能引用改写(`rewrite_skill_refs`)是 `_write_run_report()` 的**副作用**;
  一个叫"写报告"的函数会改 `~/.hermes/cron/jobs.json`(§5.4)。
- **◇-3** 两套语义不同、命名相撞的技能使用统计(§8.2)。

### ■ 代码缺陷(8 条,按影响排序)

| 编号 | 位置 | 现象 | 可复现判据 |
|---|---|---|---|
| ■-1 | `agent/curator.py 行 1577` + `:1750` | `last_run_at` 在起 daemon 线程**之前**落盘;CLI 退出杀线程 → 技能库改了一半、无 REPORT、无 run.json、下次还要等满一个 interval | 读码即得:1577-1583 先 `save_state`,1750 才 `Thread(daemon=True)` |
| ■-5 | `agent/curator.py 行 1644` vs `:1477` | 无候选短路分支的字符串与生产方对不上,永不命中;`consolidate:true` 时空库也会真花一次模型钱 | §6.5 `verify` 块;`"No agent-created skills"` 全仓仅 1 处命中 |
| ■-4 | `agent/curator.py 行 1926` + `:1481` | fork 带 `terminal`,提示词教它 `mv` 归档;pin 技能未从候选清单过滤,`terminal` 路径无 pin 硬闸 | §6.3;对比 `tools/skill_manager_tool.py 行 328` 只覆盖 `skill_manage` |
| ■-6 | `agent/curator_backup.py 行 264`、`:211` | `skills.tar.gz` 与 `manifest.json` 就地直写,非原子;`_resolve_backup` 只查存在性 → 默认回滚目标可能是被截断的档 | 读码即得;对比同仓 `atomic_json_write`(`agent/curator.py 行 119`) |
| ■-8 | `agent/curator.py 行 1551`、`agent/curator_backup.py 行 228` | 快照失败(含磁盘满)与"用户关了备份"在调用方看来完全一样,日志 `debug` 级不可见,随后照常做自主批量改写 | 读码即得:`snapshot_skills` 四种失败都 `return None`,调用方只判 `is not None` |
| ■-2 | `hermes_cli/curator.py 行 274` | 同步模式下 LLM pass 失败,`hermes curator run` 仍 `return 0` | 读码即得 |
| ■-7 | `agent/curator_backup.py 行 71` | 备份目录在被备份目录内部,同盘;只防逻辑改写不防介质故障,而名字叫 backup | 读码即得 |
| ■-3 | `agent/curator.py 行 715` | `\b{re.escape(needle)}\b`:技能名以非单词字符开头/结尾时词边界行为可疑(**未取证到真实误判**,仅疑点) | 需构造 `_tmp` / `2fa-x` 类技能名验证 |

另有一处纯冗余(不计缺陷):`agent/curator.py 行 762` 在函数内 `import re`,而模块顶部第 27 行已 import。

---

## 11. 可迁移的设计原则(要凭这份底稿重实现时的清单)

1. **闭环的读回带宽是设计约束,不是实现细节。** 系统提示词里每个技能只有 57 字描述
   (`agent/curator.py 行 426`),这一个数字决定了"技能必须是类级别的"这个全部产品判断。
   自己造 harness 时,先定读回通道的带宽,再定知识的粒度,最后才写策展逻辑。
2. **把"必须发生的"和"最好能发生的"分层。** 老化(纯函数)总是跑;合并(LLM)默认关、
   失败不影响前者。任何"要花模型钱的自动化"都该有一个不花钱的确定性子集。
3. **默认关掉有主张的自动化。** `consolidate: False`(`agent/curator.py 行 78`)—— 会重排用户
   知识库结构的操作,默认不做,理由写在常量旁边。
4. **计数器不记录依赖,要把静态引用图接进来。** cron 引用豁免(`agent/curator.py 行 340`)是
   这条的范例:"最近没被用"和"没有人依赖"是两回事。
5. **`use=0` 是证据缺失,不是无用的证据。** 给从未使用的对象一个宽限地板
   (`agent/curator.py 行 363`),并且**在代码和提示词里各写一遍**,因为执行体有两个。
6. **自主执行体要有独立于前台的权限面。** `_memory_write_origin = "background_review"`
   → 后台一律不许写 pin(`tools/skill_manager_tool.py 行 328`),而前台只挡删除。
   判据是"有没有人在回路里能同意",不是"这个操作危不危险"。
7. **让模型自报意图,但独立审计它。** `absorbed_into` 在删除那一刻自报最权威,
   同时用工具调用做 ground-truth 审计,**幻觉降级要对用户可见**(`agent/curator.py 行 1357`)。
8. **备份的粒度可以大于恢复的粒度。** 存整个 `jobs.json`,只恢复两个字段。
9. **清理策略必须知道谁正在使用。** `protect_ids`(`agent/curator_backup.py 行 612`)。
10. **别把"最好能有的东西"做成静默失败。** ■-8 是反例:安全网失效与安全网被关闭,
    在日志上应该长得不一样。
11. **状态文件读用白名单合并、写用原子替换。** `agent/curator.py 行 109` + `:119` 是正例;
    同仓 `curator_backup.py` 的两个直写是反例 —— **同一个项目里两种标准,就是漂移的开始**。

---

## 12. 移交项(每条带锚点文件 + 一句话现象)

1. **curator fork 的花费落到哪张账上?**
   锚点:`agent/curator.py:1917`(`AIAgent(... platform="curator")`)。
   现象:它是一次独立 `AIAgent`,不走 `auxiliary_client`,而 `agent/insights.py:512` 的注释
   声称总览已把 aux 开销纳入。**这次 fork 的 token 是否写进 `session_model_usage`、
   `platform="curator"` 会不会新建一条 session 行,本轮未取证。** 影响:用户看到的
   `/insights` 总花费可能不含 curator。建议下一轮连 `agent/aux_accounting.py` 一起读。
2. **`hermes_cli/curator.py`(约 850 行)本轮未精读。**
   锚点:`hermes_cli/curator.py:444` `_cmd_prune`、`:344` `_cmd_adopt`。
   现象:`adopt`(把未纳管技能收编)与 `prune`(按闲置天数交互式裁剪)是**用户侧**改写
   `.usage.json` 的入口,与 curator 自动路径共用同一份台账,本轮只看了调用关系没看实现。
3. **`~/.hermes/logs/curator/` 无清理策略。**
   锚点:`agent/curator.py:1117-1123`(`run_dir = root / stamp`,同秒冲突加后缀)。
   现象:每次 curator 运行新建一个目录,`run.json` 里含完整 `llm_final` 与全部工具调用参数;
   全仓未找到对该目录的任何 prune/rotate(搜索面:`grep -rn "logs.*curator\|_reports_root" --include=*.py .`)。
   与快照的 `keep=5` 形成对比。**本条是"未找到"级别的负结论,下一轮应扩到
   `hermes_cli/` 的日志轮转逻辑再确认。**
4. **dry-run 不做快照。**
   锚点:`agent/curator.py:1533`(`if dry_run:` 分支内无 `snapshot_skills`)。
   现象:dry-run 的"不改动"仅由提示词保证(`agent/curator.py:411` 自陈模型可能误操作),
   而**恰恰是这个模式没有安全网**。建议成品章把它写成一条明确取舍。
5. **`_classify_removed_skills` 的词边界问题(■-3)需构造用例证伪或证实。**
   锚点:`agent/curator.py:715`。
   现象:`\b` 包夹一个可能以 `-`/`_`/数字开头的技能名,行为依赖相邻字符;
   `needles` 集合里同时放了连字符与下划线两种变体,说明作者已意识到命名变体问题,但没处理边界。
