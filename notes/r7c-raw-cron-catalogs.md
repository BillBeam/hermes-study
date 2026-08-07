# r7c-raw-cron-catalogs · blueprint / suggestions / classify_items

> 底稿(证据层)。基线 `863e31318553cda8ad61df681d08175364d4164b`。
> 凡断言紧跟 `路径:行号 @ 863e313` + 代码原文。
> 本切片文件:`cron/blueprint_catalog.py`(713)、`cron/suggestions.py`(260)、
> `cron/suggestion_catalog.py`(154)、`cron/scripts/classify_items.py`(226)、
> `cron/scripts/__init__.py`(1),共 1354 行,全部逐段读完。

---

## 0. 一句话

这一簇是 cron 的"**内容层**":`blueprint_catalog.py` 是 14 条带类型槽位的参数化自动化模板(用户永不手写 cron 表达式),
`suggestions.py` + `suggestion_catalog.py` 是"系统提议 / 用户一键接受"的**同意优先(consent-first)**提议队列(4 条预置条目 + 上限 5 + 拒绝永久闩锁),
`cron/scripts/classify_items.py` 是唯一一个"随 cron 子系统发货、由 agent 在 job 运行时用终端子进程调起"的脚本(LLM 打紧急度分,低于阈值就静默);
三者都**只生产 `cron.jobs.create_job(**kwargs)` 的 kwargs**,没有第二套 job 引擎。

---

## 1. `cron/blueprint_catalog.py` —— Automation Blueprints

### 1.1 "蓝图"是什么

模块 docstring 自己定义(`cron/blueprint_catalog.py:1-22 @ 863e313`):

```python
"""Automation Blueprints — parameterized automation blueprints with typed slots.

A *blueprint* is a one-place definition of an automation that every surface
renders natively:

  * Dashboard / GUI app  -> a form (one field per slot)
  * CLI / TUI / messenger -> a pre-filled ``/blueprint`` slash command
  * Agent                 -> a seed prompt; it asks for any blank/ambiguous slot
  * Docs catalog          -> a copy-paste command + a ``hermes://`` deep-link
...
Design choice: users never type raw cron. A blueprint carries a fixed recurrence
in ``schedule_template`` and parameterizes only the human-friendly parts
(time-of-day, weekday set). Blueprints needing full flexibility expose a ``text``
slot named ``schedule`` that passes through verbatim.
"""
```

所以:**是预置的定时任务模板,但不止是模板** —— 它是"一份定义、四个渲染器"的单一真相源。
它本身不是 job;`fill_blueprint()` 把它翻译成 `create_job` 的 kwargs。

**解决的问题**:同一个"每天早上 8 点给我一份简报"的自动化,在 dashboard 要长成表单、在 Telegram 要长成一行命令、
在 agent 对话里要长成"我来问你几个问题"、在文档站要长成可复制卡片。若每个 surface 各写一份,四份会漂移。

**数据结构**(两个 frozen dataclass):

`cron/blueprint_catalog.py:60-80 @ 863e313`
```python
@dataclass(frozen=True)
class BlueprintSlot:
    """A single fillable field on a blueprint."""

    name: str
    type: str
    label: str
    default: Any = None
    options: tuple = ()       # for type="enum": allowed values
    optional: bool = False
    help: str = ""
    # When False, ``options`` are suggestions rather than a closed set —
    # any value is accepted (e.g. the deliver slot, where the real set of
    # valid platforms depends on the user's configured gateways and is
    # validated downstream by the cron scheduler).
    strict: bool = True

    def __post_init__(self) -> None:
        if self.type not in _SLOT_TYPES:
            raise ValueError(f"unknown slot type {self.type!r} (slot {self.name})")
```

槽位类型只有 4 种,`cron/blueprint_catalog.py:50 @ 863e313`:
```python
_SLOT_TYPES = frozenset({"time", "enum", "text", "weekdays"})
```

星期预设 `cron/blueprint_catalog.py:52-57 @ 863e313`:
```python
# Named weekday recurrences -> cron day-of-week field.
WEEKDAY_PRESETS: Dict[str, str] = {
    "everyday": "*",
    "weekdays": "1-5",
    "weekends": "0,6",
}
```

`cron/blueprint_catalog.py:82-99 @ 863e313`
```python
@dataclass(frozen=True)
class AutomationBlueprint:
    """A parameterized automation blueprint."""

    key: str
    title: str
    description: str
    category: str
    # Cron expression with ``{slot}`` placeholders, e.g. "{minute} {hour} * * {dow}".
    # Placeholders are filled from resolved slot values (time -> minute/hour,
    # weekdays -> dow). A literal cron string with no placeholders = fixed schedule.
    schedule_template: str
    # Seed instruction for the agent / the cron job prompt; may contain {slot}s.
    prompt_template: str
    slots: List[BlueprintSlot] = field(default_factory=list)
    deliver_default: str = "origin"
    skills: tuple = ()        # skills the job loads before running
    tags: tuple = ()
```

两个复用工厂 `cron/blueprint_catalog.py:106-117 @ 863e313`:
```python
_TIME = lambda default="08:00": BlueprintSlot(  # noqa: E731 - concise factory
    name="time", type="time", label="What time?", default=default,
    help="24h local time, e.g. 08:00",
)
_DELIVER = BlueprintSlot(
    name="deliver", type="enum", label="Where to deliver?",
    default="origin", options=("origin", "local", "telegram", "discord", "email"),
    optional=False, strict=False,
    help="origin = the chat you set this up from (or your configured home "
    "channel when created from the dashboard); local = save only, no message; "
    "or any connected platform name",
)
```

### 1.2 全部 14 条蓝图清单

`CATALOG` 定义于 `cron/blueprint_catalog.py:120-479 @ 863e313`。下表的"默认 cron"是我在基线上
实跑 `fill_blueprint(b, {})` 得到的结果(`PYTHONDONTWRITEBYTECODE=1 python3` 只读执行,`git status` 事后干净),
"人话档期"是 `blueprint_catalog_entry()["scheduleHuman"]` 的实际输出。

| # | key | 行号 | 作用(title / description 摘要) | schedule_template | 默认 cron | 人话档期 | 槽位(name:type=默认) |
|---|-----|------|------|------|------|------|------|
| 1 | `morning-brief` | 121-136 | 早间简报:今日日历+天气+紧急事项 | `{minute} {hour} * * *` | `0 8 * * *` | daily at 08:00 | time=08:00; deliver=origin |
| 2 | `important-mail` | 137-166 | 重要邮件监控,只在需要处理时才打扰 | `*/{interval_min} * * * *` | `*/30 * * * *` | every 30 minutes | interval_min∈{15,30,60}=30; criteria:text=默认长句; deliver |
| 3 | `weekly-review` | 167-189 | 周回顾:做完了什么/还开着什么/下周什么 | `{minute} {hour} * * {dow}` | `0 18 * * 0` | sunday at 18:00 | time=18:00; day∈{sunday,monday,friday,saturday}=sunday; deliver |
| 4 | `workday-start` | 190-203 | 工作日开工提醒 + 今日 1-3 件最高优先级 | `{minute} {hour} * * 1-5` | `0 9 * * 1-5` | weekdays at 09:00 | time=09:00; deliver |
| 5 | `custom-reminder` | 204-223 | 自由文本的循环提醒 | `{minute} {hour} * * {dow}` | `0 14 * * *` | everyday at 14:00 | what:text="take a break and stretch"; time=14:00; recurrence:weekdays=everyday; deliver |
| 6 | `evening-winddown` | 224-240 | 晚间收尾:明天日历 + 今晚该准备什么 | `{minute} {hour} * * *` | `0 21 * * *` | daily at 21:00 | time=21:00; deliver |
| 7 | `news-digest` | 241-274 | 主题新闻摘要,跨轮次去重,无新事就 `[SILENT]` | `{minute} {hour} * * {dow}` | `0 18 * * 1-5` | weekdays at 18:00 | topic:text="AI and technology"; time=18:00; recurrence=weekdays; count∈{3,5,8}=5; deliver |
| 8 | `bill-renewal-watch` | 275-301 | 账单/订阅续费前的可行动提醒 | `{minute} {hour} * * {dow}` | `0 10 * * *` | everyday at 10:00 | what:text="my streaming subscription renews soon"; time=10:00; recurrence=everyday; deliver |
| 9 | `habit-checkin` | 302-328 | 习惯打卡督促 + 温和回顾 | `{minute} {hour} * * {dow}` | `0 20 * * *` | everyday at 20:00 | habit:text="20 minutes of reading"; time=20:00; recurrence=everyday; deliver |
| 10 | `hydration-move` | 329-363 | 工作时段内定时提醒喝水/起身 | `0 {start_hour}-{end_hour}/{interval_hours} * * 1-5` | `0 9-17/1 * * 1-5` | weekdays, every hour | interval_hours∈{1,2,3}=1; start_hour∈{7,8,9,10}=9; end_hour∈{16,17,18,19}=17; deliver |
| 11 | `meal-plan` | 364-402 | 每周菜单 + 按货架分组的采购清单 | `{minute} {hour} * * {dow}` | `0 17 * * 0` | sunday at 17:00 | diet∈{no restrictions,vegetarian,vegan,high-protein,low-carb}; meals∈{dinner only,lunch and dinner,all three}; effort∈{quick,medium,ambitious}; time=17:00; day=sunday; deliver |
| 12 | `learn-daily` | 403-430 | 每日一课,渐进式,末尾一个检查问题 | `{minute} {hour} * * {dow}` | `30 8 * * 1-5` | weekdays at 08:30 | topic:text="Spanish vocabulary"; time=08:30; recurrence=weekdays; deliver |
| 13 | `gratitude-journal` | 431-454 | 晚间感恩/反思提示 | `{minute} {hour} * * {dow}` | `30 21 * * *` | everyday at 21:30 | time=21:30; recurrence=everyday; deliver |
| 14 | `on-this-day` | 455-478 | 每日冷知识(历史上的今天/每日一词/科学事实/名言) | `{minute} {hour} * * *` | `30 7 * * *` | daily at 07:30 | flavor∈{on this day in history,word of the day,science fact,quote of the day}; time=07:30; deliver |

`_DELIVER` 槽位对 14 条**全部**复用同一个实例(`cron/blueprint_catalog.py:110-117 @ 863e313`),所以每条都有 deliver。

分类只有 4 个值:`daily`(1/4/6/12/14)、`email`(2)、`weekly`(3/11)、`general`(5/7/8/9/10/13)。

### 1.3 蓝图怎么变成真 job:`fill_blueprint`

`cron/blueprint_catalog.py:661-713 @ 863e313`(核心):
```python
def fill_blueprint(
    blueprint: AutomationBlueprint,
    values: Dict[str, Any],
    *,
    origin: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate ``values`` and return ``cron.jobs.create_job`` kwargs.
    ...
    """
    known = {s.name for s in blueprint.slots}
    unknown = sorted(set(values) - known)
    if unknown:
        raise BlueprintFillError(
            f"unknown slot{'s' if len(unknown) > 1 else ''}: "
            f"{', '.join(unknown)} — valid: {', '.join(s.name for s in blueprint.slots)}"
        )
    resolved: Dict[str, Any] = {}
    for s in blueprint.slots:
        raw = values.get(s.name, s.default)
        if raw in (None, ""):
            if s.optional:
                continue
            raise BlueprintFillError(f"missing required value: {s.name} ({s.label})")
        if s.type == "enum" and s.strict and s.options and str(raw) not in {str(o) for o in s.options}:
            raise BlueprintFillError(
                f"{s.name}={raw!r} not allowed — one of {', '.join(map(str, s.options))}"
            )
        resolved[s.name] = raw

    schedule = _resolve_schedule(blueprint, resolved)
    ...
    spec: Dict[str, Any] = {
        "prompt": prompt,
        "schedule": schedule,
        "name": blueprint.title,
        "deliver": resolved.get("deliver", blueprint.deliver_default),
    }
    if blueprint.skills:
        spec["skills"] = list(blueprint.skills)
    if origin is not None:
        spec["origin"] = origin
    return spec
```

三层校验:**未知槽位名直接拒绝**(打错 `tiem=07:15` 不能静默用默认值建 job)、
**必填槽位缺失报名字**(表单可以红字定位)、**strict enum 才查白名单**(deliver 是 `strict=False`,放行任意平台名)。

档期解析 `cron/blueprint_catalog.py:603-658 @ 863e313`:
```python
def _resolve_schedule(blueprint: AutomationBlueprint, values: Dict[str, Any]) -> str:
    """Fill the schedule_template placeholders from resolved slot values."""
    sched = blueprint.schedule_template

    # A free-text `schedule` slot passes through verbatim (full flexibility).
    if "schedule" in values and values["schedule"]:
        return str(values["schedule"])

    repl: Dict[str, str] = {}

    # time -> minute/hour
    time_val = values.get("time")
    if "{minute}" in sched or "{hour}" in sched:
        if not time_val:
            raise BlueprintFillError("a time is required")
        m = _TIME_RE.match(str(time_val).strip())
        if not m:
            raise BlueprintFillError(f"invalid time {time_val!r} — use HH:MM (24h)")
        repl["hour"] = str(int(m.group(1)))
        repl["minute"] = str(int(m.group(2)))
    ...
    # Any remaining {slot} placeholders are filled verbatim from validated
    # enum/text slot values (e.g. an hour-range window). Enum options have
    # already been checked in fill_blueprint, so these are safe to interpolate.
    for name in re.findall(r"\{(\w+)\}", sched):
        if name not in repl and name in values:
            repl[name] = str(values[name])
```

时间正则与星期映射 `cron/blueprint_catalog.py:596-600 @ 863e313`:
```python
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_DAY_TO_DOW = {
    "sunday": "0", "monday": "1", "tuesday": "2", "wednesday": "3",
    "thursday": "4", "friday": "5", "saturday": "6",
}
```

注意最后那个"剩余 `{slot}` 逐字插值"的兜底(651-653)是有**安全前提**的:注释明说"enum options
have already been checked in fill_blueprint, so these are safe to interpolate"。
`hydration-move` 的 `start_hour/end_hour/interval_hours` 全是 strict enum,所以插值安全;
但如果将来有人给某个 **text** 槽位写进 `schedule_template`,这条路径就会把任意用户文本
直接拼进 cron 表达式 —— 这是一个**靠约定而非机制守住的不变量**。

### 1.4 四个渲染器

| 函数 | 行号 | 产出 | 消费方 |
|---|---|---|---|
| `blueprint_form_schema` | 492-513 | `{key,title,description,category,tags,fields[]}`,fields 含 name/type/label/default/options/optional/**strict**/help | dashboard 表单、desktop、docs |
| `blueprint_slash_command` | 516-534 | `/blueprint <key> slot=val …`(text 槽或含空格的值加引号) | 文档"复制即用"、dashboard 展示 |
| `blueprint_deeplink` | 537-548 | `hermes://blueprint/<key>?slot=val` | 文档站 "Send to App" → desktop 深链 |
| `blueprint_catalog_entry` | 578-589 | 上面三者合并 + `schedule` + `scheduleHuman` | `GET /api/cron/blueprints`、docs 生成器 |

`_humanize_schedule`(551-575)是纯展示用的启发式,分四支:`*/`(分钟步进)→"every N minutes";
`{interval_hours}` → "weekdays, every N hours";`* * 1-5` → "weekdays at HH:MM";`{dow}` → "<recurrence|day> at HH:MM"。

### 1.5 消费点(生产,非测试)

| 消费方 | 行号 | 用途 |
|---|---|---|
| `hermes_cli/blueprint_cmd.py:106` | `from cron.blueprint_catalog import CATALOG, get_blueprint` | `/blueprint` 名字模糊匹配 |
| `hermes_cli/blueprint_cmd.py:149` | `from cron.blueprint_catalog import _humanize_schedule as _h` | **跨模块导入私有函数** |
| `hermes_cli/blueprint_cmd.py:165` | `WEEKDAY_PRESETS` | 写进给 agent 的 seed 文本 |
| `hermes_cli/blueprint_cmd.py:204,226` | `CATALOG` | 列目录 / "你是不是想输入…" |
| `hermes_cli/blueprint_cmd.py:264` | `fill_blueprint, BlueprintFillError` | `/blueprint <name> slot=val` 直建 |
| `hermes_cli/web_routers/cron.py:192` | `CATALOG, blueprint_catalog_entry` | `GET /api/cron/blueprints` |
| `hermes_cli/web_routers/cron.py:221` | `fill_blueprint, get_blueprint, BlueprintFillError` | `POST /api/cron/blueprints/instantiate` |
| `website/scripts/extract-automation-blueprints.py:28` | `CATALOG, blueprint_catalog_entry` | 生成文档站 JSON |
| `hermes_cli/web_server.py:11752-11753` | re-export `list_cron_blueprints, instantiate_blueprint` | 路由挂载 |

三条实例化路径,**全部收敛到 `cron.jobs.create_job`**:

1. **表单路径**(dashboard/desktop)。`hermes_cli/web_routers/cron.py:218-241 @ 863e313`:
```python
async def instantiate_blueprint(body: AutomationBlueprintInstantiate, profile: str = "default"):
    """Fill a blueprint's slots and create the cron job (form-submit path)."""
    try:
        from cron.blueprint_catalog import fill_blueprint, get_blueprint, BlueprintFillError

        blueprint = get_blueprint(body.blueprint)
        if blueprint is None:
            raise HTTPException(status_code=404, detail=f"Unknown blueprint: {body.blueprint}")
        try:
            spec = fill_blueprint(blueprint, body.values)
        except BlueprintFillError as exc:
            # Field-level validation error — 422 so the form can show it inline.
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # Blueprint-created jobs deliver to the dashboard's configured target by
        # default; the form's deliver slot overrides via spec["deliver"].
        spec.pop("origin", None)
```
   注意 `spec.pop("origin", None)`(233):dashboard 建的 job **没有 origin**,落到 home channel。

2. **命令行直建**(power user)。`hermes_cli/blueprint_cmd.py:296-311 @ 863e313`:
```python
    # `<name> slot=val …` -> fill + create directly (deterministic shortcut).
    try:
        spec = fill_blueprint(blueprint, values, origin=_resolve_origin(origin))
    except BlueprintFillError as e:
        ...
    try:
        from cron.jobs import create_job

        job = create_job(**spec)
```

3. **对话式填槽**(chat)。`hermes_cli/blueprint_cmd.py:287-294 @ 863e313` 返回 `agent_seed`,
   gateway 在 `gateway/run.py:15214-15225 @ 863e313` 把 `event.text` 改写成 seed 后**落回 agent 主流程**:
```python
        if canonical == "blueprint":
            _blueprint_result = await self._handle_blueprint_command(event)
            _blueprint_seed = getattr(_blueprint_result, "agent_seed", None)
            if _blueprint_seed:
                # Blueprint matched — rewrite the turn to the seed and fall
                # through to _handle_message_with_agent so the agent asks the
                # user for each slot value conversationally and then calls the
                # cronjob tool (the /steer fall-through pattern). The seed
                # enters as a normal user turn, preserving role alternation.
```
   这条路径**不经过 `fill_blueprint`** —— agent 拿着 `schedule_template` 自己拼 cron,
   然后调 `cronjob` 工具。见 `hermes_cli/blueprint_cmd.py:189-199 @ 863e313`:
```python
    lines.append(
        "Once you have my answers, create the job by calling the cronjob tool "
        "with action='create'. Build the schedule as a cron expression from "
        f"this template: `{blueprint.schedule_template}` "
        "(fill {minute}/{hour} from the chosen time, {dow} from the weekday "
        f"choice using {dict(WEEKDAY_PRESETS)}, {{interval_min}} from any "
        "interval). Use this exact prompt for the job (substituting my "
        f"answers into any {{slot}} placeholders): \"{blueprint.prompt_template}\". "
        "Confirm the schedule and what it will do before you create it."
    )
```
   **取舍**:对话路径把"槽位 → cron"这一步交给 LLM 做,类型系统在这条路上退化成 prompt 里的自然语言约束。
   模块 docstring 声称 slot schema 是 "the single source of truth"(`cron/blueprint_catalog.py:11`),
   但对话路径只把它当**提示词素材**用,`_TIME_RE`/`WEEKDAY_PRESETS` 的确定性校验不生效。这是本簇最大的设计取舍。

4. **深链路径**。`hermes://blueprint/<key>?slot=val` 由 desktop 主进程接住
   (`apps/desktop/electron/main.ts:11736 @ 863e313`:`// hermes://blueprint/<key>?slot=val -> host="blueprint", path="/<key>"`),
   转成 composer 里一条**可复核的 `/blueprint` 命令**,不直接建 job
   (`apps/desktop/src/app/contrib/hooks/use-desktop-integrations.ts:190 @ 863e313`:
   `// hermes:// deep links -> a reviewable /blueprint command in the composer.`)。
   —— 深链不能静默建定时任务,这是有意的。

---

## 2. `cron/suggestions.py` + `cron/suggestion_catalog.py` —— 建议机制

### 2.1 是什么 / 解决什么问题

`cron/suggestions.py:1-26 @ 863e313`:
```python
"""Suggested cron jobs — proposed automations the user accepts with one tap.

A *suggestion* is a ready-to-run cron job spec that Hermes surfaces to the
user, who accepts it (creates the real cron job) or dismisses it (latched so
it is never re-offered). This is the single surface every automation proposal
flows through, regardless of where it came from:

  * ``catalog``  — a curated starter automation (daily briefing, important-mail
                   monitor, weekly digest, ...).
  * ``blueprint``   — the user installed a skill that carries a ``blueprint:`` block
                   (see ``tools/blueprints.py``); installing it registers a
                   suggestion instead of auto-scheduling.
  * ``usage``    — the background self-improvement review noticed a recurring
                   ask that a scheduled job would serve.
  * ``integration`` — the user connected an account (Gmail, GitHub, ...) and
                   the obvious automations for that surface are offered.

Accepting a suggestion just calls the existing ``cron.jobs.create_job`` with
the stored ``job_spec`` — there is NO second job engine. Suggestions never
auto-create jobs; acceptance is always explicit (consent-first). Dismissed
suggestions latch by a stable ``dedup_key`` so the same proposal is not
re-offered after the user says no.

Storage mirrors ``cron/jobs.py``: ``~/.hermes/cron/suggestions.json``, atomic
writes, an in-process lock, and 0600 perms.
"""
```

回答任务里的问题:

- **系统主动向用户推荐定时任务吗?** 是,但**只推荐,永不自动执行**。四个来源都只写 `status="pending"`。
- **触发条件是什么?** 目前只有两个来源在生产代码里真的触发(见 2.4 接线核查):
  1. `catalog` —— 用户**手动**跑 `/suggestions catalog`(`hermes_cli/suggestions_cmd.py:126-130`),不是系统自发。
  2. `blueprint` —— 用户 `hermes skills install` 了一个带 `blueprint:` 块的 skill
     (`hermes_cli/skills_hub.py:749-757`),安装动作即触发。
  `usage` 与 `integration` 在 `VALID_SOURCES` 里被接受,但**全仓无生产端产生**(只有测试构造)。

### 2.2 防骚扰的四道闸

`cron/suggestions.py:53-62 @ 863e313`:
```python
# In-process lock protecting load->modify->save cycles (the background review
# fork and the main agent can both write).
_suggestions_lock = threading.Lock()

# Cap pending suggestions so the list never becomes a nag wall. When full,
# new suggestions are dropped (the user should clear the backlog first).
MAX_PENDING = 5

VALID_SOURCES = frozenset({"catalog", "blueprint", "usage", "integration"})
_STATUS_PENDING = "pending"
_STATUS_ACCEPTED = "accepted"
_STATUS_DISMISSED = "dismissed"
```

`cron/suggestions.py:143-177 @ 863e313`:
```python
    if source not in VALID_SOURCES:
        raise ValueError(f"unknown suggestion source: {source!r}")
    if not title.strip() or not dedup_key.strip():
        raise ValueError("title and dedup_key are required")

    with _suggestions_lock:
        suggestions = _load_raw().get("suggestions", [])

        # Never re-offer something the user already saw and decided on, and
        # never duplicate a still-pending proposal.
        for existing in suggestions:
            if existing.get("dedup_key") == dedup_key:
                if existing.get("status") in (_STATUS_DISMISSED, _STATUS_ACCEPTED):
                    return None
                if existing.get("status") == _STATUS_PENDING:
                    return None

        pending_count = sum(1 for s in suggestions if s.get("status") == _STATUS_PENDING)
        if pending_count >= MAX_PENDING:
            logger.info("Suggestion backlog full (%d); dropping %r", MAX_PENDING, title)
            return None
```

四道闸:
1. **来源白名单**(唯一会抛异常的,其余都静默返回 `None`);
2. **已拒绝闩锁** —— dismissed 的 `dedup_key` 永久拒绝重推;
3. **已接受闩锁** —— accepted 也拒绝重推(docstring 只说 dismissed,代码两者都锁,见 §6);
4. **待办上限 5** —— 超了直接丢,只 `logger.info`,用户看不到。

**"永不自动建 job"** 由 `accept_suggestion` 的显式调用保证,`cron/suggestions.py:223-243 @ 863e313`:
```python
def accept_suggestion(ref: str, *, origin: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Accept a suggestion: create the real cron job from its ``job_spec``.
    ...
    """
    s = get_suggestion(ref)
    if not s or s.get("status") != _STATUS_PENDING:
        return None

    from cron.jobs import create_job

    spec = dict(s.get("job_spec") or {})
    if origin is not None and "origin" not in spec:
        spec["origin"] = origin

    job = create_job(**spec)
    _set_status(s["id"], _STATUS_ACCEPTED)
    return job
```

引用解析支持三种写法(id / 1-based pending 序号 / 精确标题),`cron/suggestions.py:180-197 @ 863e313`:
```python
def get_suggestion(ref: str) -> Optional[Dict[str, Any]]:
    """Resolve a suggestion by id, 1-based pending index, or title (exact)."""
```

清理只删 accepted,`cron/suggestions.py:246-260 @ 863e313`:
```python
def clear_resolved() -> int:
    """Drop accepted/dismissed records from disk. Returns the count removed.

    Pending suggestions and the dedup memory of dismissed ones are the only
    things that matter long-term, but dismissed records must be RETAINED for
    their dedup_key (so they aren't re-offered). This only prunes ACCEPTED
    records, which have served their purpose once the job exists.
    """
```
注意这里 docstring 首句 "Drop accepted/dismissed records" 与后文/实现(只删 accepted)**自相矛盾**,见 §6。

### 2.3 存储:per-profile + 原子写 + 0600

`cron/suggestions.py:45-49 @ 863e313`:
```python
# Per-profile by design (issue #4707): suggestions live alongside the active
# profile's cron store. Anchor on get_hermes_home() (profile home), not the
# shared default root. See cron/jobs.py for the full rationale.
CRON_DIR = get_hermes_home().resolve() / "cron"
SUGGESTIONS_FILE = CRON_DIR / "suggestions.json"
```

`cron/suggestions.py:93-112 @ 863e313`(mkstemp → fsync → `atomic_replace` → chmod 0600):
```python
def _save_raw(suggestions: List[Dict[str, Any]]) -> None:
    _ensure_dir()
    fd, tmp_path = tempfile.mkstemp(dir=str(SUGGESTIONS_FILE.parent), suffix=".tmp", prefix=".sugg_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(
                {"suggestions": suggestions, "updated_at": _hermes_now().isoformat()},
                f,
                indent=2,
            )
            f.flush()
            os.fsync(f.fileno())
        atomic_replace(tmp_path, SUGGESTIONS_FILE)
        _secure_file(SUGGESTIONS_FILE)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

读侧对三种坏形态都兜底(不存在 / JSON 坏 / 顶层是裸 list 的旧格式),`cron/suggestions.py:76-90 @ 863e313`。

### 2.4 建议目录 `suggestion_catalog.py`:全部 4 条

`cron/suggestion_catalog.py:1-16 @ 863e313`:
```python
"""Curated catalog of starter cron-job suggestions.

These are the built-in automations Hermes can offer a new user out of the box —
the ``catalog`` source of the unified suggestion surface. Each entry is a
ready-to-run ``cron.jobs.create_job`` spec wrapped as a suggestion; the user
accepts via ``/suggestions``. Nothing here auto-schedules.

The "important-mail monitor" entry is where the old proactive-monitor engine
lives now: its ``classify_items.py`` (poll a source -> LLM-score urgency ->
surface only above-threshold) is ONE catalog automation, not a standalone
feature.
```

`CATALOG` 定义于 `cron/suggestion_catalog.py:43-121 @ 863e313`:

| # | key(= dedup_key) | 行号 | title | schedule | deliver | 作用 |
|---|---|---|---|---|---|---|
| 1 | `catalog:daily-briefing` | 44-62 | Daily briefing | `0 8 * * *` | origin | 早 8 点简报:日历+天气+紧急事项 |
| 2 | `catalog:important-mail-monitor` | 63-86 | Important-mail monitor | `every 30m` | origin | 轮询收件箱→分类器打分→只送高分,否则 `[SILENT]` |
| 3 | `catalog:weekly-review` | 87-103 | Weekly review | `0 18 * * 0` | origin | 周日晚周回顾 |
| 4 | `catalog:standup-reminder` | 104-120 | Workday start reminder | `0 9 * * 1-5` | origin | 工作日 9 点开工提醒 |

注意 #2 的 schedule 是 `"every 30m"` 这种**自然语言档期**(靠 `cron.jobs.parse_schedule` 解析),
而 #1/#3/#4 是标准 5 段 cron —— **同一个目录里两种档期语法混用**。

`CatalogEntry` 结构 `cron/suggestion_catalog.py:32-39 @ 863e313`:
```python
@dataclass(frozen=True)
class CatalogEntry:
    """A curated starter automation offered as a suggestion."""

    key: str                 # stable dedup key (never re-offered once dismissed)
    title: str
    description: str
    job_spec: Dict[str, Any]  # kwargs for cron.jobs.create_job
```

播种函数 `cron/suggestion_catalog.py:124-154 @ 863e313`:
```python
def seed_catalog_suggestions(
    *,
    add_fn: Optional[Callable[..., Optional[Dict[str, Any]]]] = None,
    keys: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Register catalog entries as pending suggestions.

    ``add_fn`` defaults to ``cron.suggestions.add_suggestion`` (injectable for
    tests). ``keys`` restricts to specific catalog entries; omit to seed all.
    Entries already dismissed/accepted (by dedup key) or beyond the pending cap
    are skipped by the store, so re-seeding is safe and idempotent. Returns the
    list of suggestion records actually created.
    """
```
`keys=` 参数**全仓无人使用**(生产与测试都只无参调用),是预留扩展点。

### 2.5 `/suggestions` 命令面

`hermes_cli/suggestions_cmd.py:7-12 @ 863e313`:
```
  /suggestions                 list pending suggestions (numbered)
  /suggestions accept <N|id>   create the cron job for that suggestion
  /suggestions dismiss <N|id>  dismiss it (latched, never re-offered)
  /suggestions catalog         seed the curated starter automations as pending
  /suggestions clear           drop accepted records (housekeeping)
```
别名容忍度:accept 也接受 `add`/`schedule`,dismiss 也接受 `no`/`reject`
(`hermes_cli/suggestions_cmd.py:97,116 @ 863e313`)。

---

## 3. `cron/scripts/classify_items.py`

### 3.1 谁执行它、怎么执行

**没有任何 Python 代码 import 或 subprocess 调它。** 全仓 grep `classify_items`(排除 `.pyc`)只有 5 个非自身命中:
`cron/suggestion_catalog.py:9,24,27,29,74`、`hermes_cli/config_defaults.py:1015`、
`hermes_agent.egg-info/SOURCES.txt:224`、`tests/cron/test_suggestions.py:136,143,144,145`。

它的唯一"调用者"是 **LLM**:catalog 里 #2 那条 job 的 prompt 用自然语言告诉 agent 去跑它。
`cron/suggestion_catalog.py:69-81 @ 863e313`:
```python
            "prompt": (
                "Check the user's inbox for new messages since the last run. "
                "For each candidate, judge urgency against this rule: surface "
                "only mail that needs a reply today, is from a manager/family "
                "member, or mentions a deadline. Pipe candidates through the "
                "urgency classifier (run `python3 -m cron.scripts.classify_items "
                "--threshold 7 --criteria ...` from the hermes-agent install — "
                "resolve the script path at run time, do not assume a fixed "
                "location) and deliver ONLY what it returns. If nothing "
                "clears the bar, respond with [SILENT] so the user is not "
                "pinged. Requires a connected mail source; if none is "
                "configured, explain how to connect one and stop."
            ),
```
所以执行方式是:**cron job 里的 agent 用终端工具起子进程 `python3 -m cron.scripts.classify_items`**。
这也解释了为什么必须是 `-m` 模块路径而不是绝对路径(见 §7 的事故经过)。

模块 docstring 也把这层"人/agent 触发"写清楚了,`cron/scripts/classify_items.py:21-28 @ 863e313`:
```python
Usage (standalone):
  cat items.json | python classify_items.py --threshold 7 \
    --criteria "Urgent if it needs a reply today or is from my manager/family"

Usage (wired to a watcher via cron, agent mode):
  Ask the agent: "Every 10 minutes, run watch_http_json.py for my inbox feed,
  pipe its JSON into classify_items.py with my urgency criteria, and deliver
  whatever it prints. Stay silent if it prints nothing."
```

### 3.2 分类的是什么 "items"

**任意 JSON 对象列表**,schema 是软的。`cron/scripts/classify_items.py:30-33 @ 863e313`:
```python
Item schema (flexible): each item is an object; the classifier sees the whole
object. A "title"/"subject"/"summary"/"text" field helps it judge. An "id"
field (any of id/guid/message_id/url) is echoed back so duplicates can be
deduped upstream.
```
输入解析 `cron/scripts/classify_items.py:48-71 @ 863e313`,支持 stdin 或 `--input-file`,
接受裸 list、`{"items":[...]}`、单个 object 三种形态;JSON 坏 → `sys.exit(2)`。

id 提取 `cron/scripts/classify_items.py:74-79 @ 863e313`:
```python
def _item_id(item: Dict[str, Any], index: int) -> str:
    for key in ("id", "guid", "message_id", "url", "link"):
        val = item.get(key)
        if val:
            return str(val)
    return f"item-{index}"
```

### 3.3 用不用 LLM / prompt 在哪

**用。** 系统指令 `cron/scripts/classify_items.py:82-90 @ 863e313`:
```python
_CLASSIFY_INSTRUCTIONS = (
    "You are an urgency classifier for a proactive assistant. You will be given "
    "a numbered list of items and the user's importance criteria. Score EACH "
    "item from 0 (ignore entirely) to 10 (interrupt the user now). Return ONLY a "
    'JSON array, one object per item, in the same order: '
    '[{"index": <int>, "score": <int 0-10>, "reason": "<short>"}]. '
    "No prose, no markdown fences. Be conservative: most items should score low. "
    "Only score high when the item clearly meets the user's criteria."
)
```

**⚠ 死代码:`_CLASSIFY_INSTRUCTIONS` 定义了却从未被使用。** `main()` 只发了 `_build_prompt()` 的结果:
`cron/scripts/classify_items.py:164-171 @ 863e313`:
```python
    prompt = _build_prompt(items, args.criteria)
    try:
        resp = call_llm(
            task="monitor",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0,
        )
```
没有 `system` 消息,`_CLASSIFY_INSTRUCTIONS` 也没拼进 `_build_prompt`。
`_build_prompt` 全文 `cron/scripts/classify_items.py:93-108 @ 863e313`:
```python
def _build_prompt(items: List[Dict[str, Any]], criteria: str) -> str:
    lines = [f"USER IMPORTANCE CRITERIA:\n{criteria}\n", "ITEMS:"]
    for i, item in enumerate(items):
        # Show a compact view; the model sees the salient fields.
        view = {
            k: item[k]
            for k in ("title", "subject", "summary", "text", "body", "from", "sender", "url")
            if k in item
        }
        if not view:
            view = item  # fall back to the whole object
        lines.append(f"[{i}] {json.dumps(view, ensure_ascii=False)[:1200]}")
    lines.append(
        "\nReturn the JSON array of scores now (one object per item, same order)."
    )
    return "\n".join(lines)
```
—— 唯一残留的格式约束是最后那句 "Return the JSON array of scores now",
"0-10 打分" / "保守评分" / "不要 markdown 围栏" 这些**关键指令全部没送给模型**。
配合"没有任何单测覆盖本文件"(见 §8),这是本切片最实质的一个缺陷。
`_parse_scores` 的容错(见下)正好在补这个洞。

分数解析的三级容错 `cron/scripts/classify_items.py:111-141 @ 863e313`:
```python
def _parse_scores(content: str, n_items: int) -> Dict[int, Dict[str, Any]]:
    text = (content or "").strip()
    # Tolerate accidental markdown fences.
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    try:
        arr = json.loads(text)
    except json.JSONDecodeError:
        # Last-ditch: find the first [...] block.
        start = text.find("[")
        end = text.rfind("]")
```
并且**按 `index` 字段回填而不是按顺序**(138-140),模型漏项/乱序都不会错配:
```python
            idx = obj.get("index")
            if isinstance(idx, int) and 0 <= idx < n_items:
                out[idx] = obj
```

### 3.4 静默 vs 报错的取舍(退出码语义)

| 情况 | 行号 | 行为 | 退出码 |
|---|---|---|---|
| 输入非法 JSON | 61-62, 70-71 | stderr + 退出 | 2 |
| 无 item(安静区间) | 152-155 | 空 stdout | 0 |
| 导不到 aux client | 158-162 | stderr | 3 |
| LLM 调用失败 | 175-179 | stderr | **4** |
| 全部低于阈值 | 189-191 | 空 stdout | 0 |

关键设计,`cron/scripts/classify_items.py:175-179 @ 863e313`:
```python
    except Exception as e:
        # Classification failure is NOT silent -- surface it so a broken monitor
        # doesn't quietly swallow important items. Non-zero exit -> cron alerts.
        _eprint(f"classify_items: classifier call failed: {e}")
        return 4
```
**"没东西要报"和"我坏了"必须走不同出口** —— 前者空 stdout+0,后者非零退出。
否则一个坏掉的监控器和一个安静的收件箱在用户眼里长得一模一样。这是 proactive monitor 类机制的核心不变量。

### 3.5 模型配置

`task="monitor"` 走 `agent/auxiliary_client.call_llm`(签名 `agent/auxiliary_client.py:8562-8581 @ 863e313`),
配置项在 `hermes_cli/config_defaults.py:1014-1027 @ 863e313`:
```python
        # Monitor — urgency/importance classifier used by the important-mail
        # monitor catalog automation (cron/scripts/classify_items.py). Scores
        # candidate items 0-10 against the user's criteria so only above-
        # threshold items get delivered. "auto" = main chat model; override to
        # a cheap fast model (e.g. openrouter google/gemini-3-flash-preview,
        # haiku) since per-item scoring is high-volume and a small model is fine.
        "monitor": {
            "provider": "auto",
            "model": "",
            ...
            "timeout": 60,
```

### 3.6 `cron/scripts/__init__.py`

全文一行,`cron/scripts/__init__.py:1 @ 863e313`:
```python
"""Scripts shipped with the cron subsystem (runnable via ``python3 -m cron.scripts.<name>``)."""
```

**为什么只有一个脚本?** 因为这个包不是"脚本类 job 放这里"的通用约定,而是为一个具体需求补的:
让 `classify_items` 能被 `-m` 调起、并且**进 wheel**。证据:

1. 它是在 `e8b757845` "pre-release hardening" 里**后加**的,commit message 明说
   "cron/scripts is now a real package and ships in the wheel (pyproject packages.find)"。
2. `pyproject.toml:398-399 @ 863e313`:
```toml
[tool.setuptools.packages.find]
include = ["agent", "agent.*", "tools", "tools.*", "hermes_cli", "hermes_cli.*", "gateway", "gateway.*", "tui_gateway", "tui_gateway.*", "cron", "cron.*", "acp_adapter", "plugins", "plugins.*", "providers", "providers.*"]
```
   `cron.*` 只有在 `cron/scripts/` 是真包(有 `__init__.py`)时才会把它打进去。

**用户脚本放哪?** 不是这里 —— `cron/jobs.py:1285-1287 @ 863e313` 的 `create_job(script=...)` 文档说:
```
                ~/.hermes/scripts/; ``.sh`` / ``.bash`` files run via bash,
```
即用户脚本在 `~/.hermes/scripts/`,`cron/scripts/` 是**随发行版走的官方脚本**。两个位置、两种归属。

---

## 4. 与 `cron/jobs.py` / `cron/scheduler.py` 的关系

**单向依赖,零反向引用。** grep 求证:
```
$ grep -n "suggestion\|blueprint\|recipe" cron/jobs.py cron/scheduler.py cron/executions.py \
      cron/lifecycle_guard.py cron/scheduler_provider.py
(无输出)
```
`cron/__init__.py:19-30 @ 863e313` 的公开面也只导出 jobs + scheduler.tick,**不导出 blueprint/suggestion**:
```python
from cron.jobs import (
    create_job,
    get_job,
    ...
)
from cron.scheduler import tick
```

三个消费方向:

```
blueprint_catalog.fill_blueprint(…) ──┐
suggestions.accept_suggestion(…) ─────┼──> cron.jobs.create_job(**kwargs)
tools.blueprints.create_blueprint_job ┘
```

唯一一处反向"感知":`hermes_cli/web_routers/cron.py:196-199 @ 863e313` 用
`cron.scheduler.cron_delivery_targets()` 改写 deliver 槽位的 options:
```python
            from cron.scheduler import cron_delivery_targets

            platforms = [t["id"] for t in cron_delivery_targets() if t.get("id")]
            deliver_options = ["origin", "local", *platforms]
```
这是"表单不提供未连接的平台"的实现 —— 但它在**路由层**做,不在 catalog 层,所以 catalog 保持无状态、可离线渲染文档。

---

## 5. 接线核查表(生产调用点,排除 `tests/`)

| 文件 | 是否被生产代码调用 | 入口 | 备注 |
|---|---|---|---|
| `cron/blueprint_catalog.py` | ✅ | `/blueprint`(CLI/TUI/gateway)、`GET /api/cron/blueprints`、`POST /api/cron/blueprints/instantiate`、docs 生成器 | 4 个 surface 都活 |
| `cron/suggestions.py` | ✅ | `/suggestions`(CLI `hermes_cli/cli_commands_mixin.py:1747`、gateway `gateway/run.py:18617`) | |
| `cron/suggestion_catalog.py` | ✅ | 仅 `/suggestions catalog`(`hermes_cli/suggestions_cmd.py:128`) | |
| `cron/scripts/classify_items.py` | ⚠️ 仅 LLM 触发 | catalog 条目 #2 的 prompt 文本 | 无任何 Python 调用点 |
| `cron/scripts/__init__.py` | ✅(打包语义) | `pyproject.toml:399` `cron.*` | |

**函数级死代码**:

| 符号 | 行号 | 状况 |
|---|---|---|
| `_CLASSIFY_INSTRUCTIONS` | `cron/scripts/classify_items.py:82-90` | 定义未使用(见 §3.3) |
| `classify_items_script_path()` | `cron/suggestion_catalog.py:27-29` | 导出在 `__all__:24`,**生产零调用**,只有 `tests/cron/test_suggestions.py:136,144,145` 用它做"prompt 里不许出现绝对路径"的反向断言 |
| `seed_catalog_suggestions(keys=…)` | `cron/suggestion_catalog.py:127` | 参数全仓无人传 |
| `AutomationBlueprint.skills` | `cron/blueprint_catalog.py:98` | 14 条蓝图**无一**设置(grep `skills=` 在该文件零命中),因此 `fill_blueprint:709-710` 的 `spec["skills"]` 分支永不触发 |
| `BlueprintSlot.optional=True` | `cron/blueprint_catalog.py:70` | 14 条蓝图**无一**设置(grep `optional=` 只命中 `_DELIVER` 的 `optional=False`),因此 `blueprint_slash_command:527-528` 与 `fill_blueprint:686-687` 的 optional 分支在现货目录下不可达 |
| `_resolve_schedule` 的 `schedule` 直通 | `cron/blueprint_catalog.py:607-609` | docstring(19-21)承诺的"全灵活度逃生口",但**没有任何蓝图声明名为 `schedule` 的槽位**,而 `fill_blueprint:675-681` 又拒绝未知槽位名 —— 这条路径现货不可达 |
| `_load_raw` 裸 list 兼容 | `cron/suggestions.py:87-88` | 没有写侧会产生这种形态,纯防御 |

**命名漂移**:

- `hermes_cli/blueprint_cmd.py:149 @ 863e313` 跨模块 import 私有函数:
  ```python
      from cron.blueprint_catalog import _humanize_schedule as _h
  ```
  `_humanize_schedule` 带下划线前缀却是跨模块公共依赖,且没进 `__all__`(`cron/blueprint_catalog.py:30-42`)。
- `strict` 字段:`blueprint_form_schema:508` 输出它,`web/src/lib/api.ts:2243` 和
  `apps/desktop/src/types/hermes.ts:837` 都**声明了类型却从不读取** —— 两个前端都把 enum 一律渲染成闭合下拉
  (`web/src/components/AutomationBlueprints.tsx:38-47`)。`strict=False` 的实际效果完全靠
  `hermes_cli/web_routers/cron.py:203-209` 在服务端改写 options 来兜。

---

## 6. ▲ / ◇ 候选

### ▲-1 `meal-plan` prompt 里的重命名事故:"Keep blueprints simple and skimmable"

`cron/blueprint_catalog.py:371-376 @ 863e313`:
```python
        prompt_template=(
            "Build the user a meal plan for the coming week: {meals} per day, "
            "suited to a {diet} diet and roughly {effort} cooking effort. "
            "Include a consolidated grocery list grouped by aisle. Keep blueprints "
            "simple and skimmable."
        ),
```
在一条**菜谱**蓝图里说 "Keep blueprints simple" 显然不通。溯源确认是全局重命名误伤:
```
$ git show cb29e8a82 -- cron/recipe_catalog.py cron/blueprint_catalog.py
-            "Include a consolidated grocery list grouped by aisle. Keep recipes "
+            "Include a consolidated grocery list grouped by aisle. Keep blueprints "
```
commit `cb29e8a82` "refactor(cron): rebrand Cron Recipes -> Automation Blueprints",message 声称 "No behavior change" ——
但这是**送给 LLM 的 prompt 文本**,把 "recipes"(菜谱)改成 "blueprints"(蓝图)实打实改变了模型收到的指令。
**教训:重命名脚本必须把 prompt 字符串排除在外,或逐条人工过。**

### ▲-2 两个 catalog 里有四条重复的同名自动化,且行为不等价

| 自动化 | blueprint_catalog(参数化) | suggestion_catalog(固定) |
|---|---|---|
| 早间简报 | `morning-brief` (`:121-136`) | `catalog:daily-briefing` (`:44-62`) |
| 重要邮件 | `important-mail` (`:137-166`) | `catalog:important-mail-monitor` (`:63-86`) |
| 周回顾 | `weekly-review` (`:167-189`) | `catalog:weekly-review` (`:87-103`) |
| 开工提醒 | `workday-start` (`:190-203`) | `catalog:standup-reminder` (`:104-120`) |

prompt 文案高度雷同但**不是同一份**,且关键差异在重要邮件这条:

- suggestion 版**告诉 agent 怎么跑分类器**(`cron/suggestion_catalog.py:73-76`):
  ```python
                "urgency classifier (run `python3 -m cron.scripts.classify_items "
                "--threshold 7 --criteria ...` from the hermes-agent install — "
                "resolve the script path at run time, do not assume a fixed "
                "location) and deliver ONLY what it returns. If nothing "
  ```
- blueprint 版**只说"用紧急度分类器"**,没有任何调用方法(`cron/blueprint_catalog.py:144-150`):
  ```python
        prompt_template=(
            "Check the user's inbox for new messages since the last run. Surface "
            "ONLY mail matching: {criteria}. Score candidates with the urgency "
            "classifier and deliver only what clears the bar; if nothing does, "
            "respond with [SILENT]. Requires a connected mail source; if none is "
            "configured, explain how to connect one and stop."
        ),
```
  → 从 `/blueprint important-mail` 建的 job,agent 大概率**不会**去跑 `classify_items`,
  这条自动化退化成"让主模型自己判断紧急度"。这是两条路径的**实质行为差异**,不是文案差异。
  而且这个"分类器只被一句自然语言引用"的设计,让分类器的接线完全无法被静态检查。

同时也是"两个都叫 catalog、两个都叫 CATALOG、两个都叫 important-mail 监控"的**命名污染**。

### ▲-3 `blueprint` 一词在仓库里指两个不同的东西

| 概念 | 定义处 | 是什么 |
|---|---|---|
| Automation Blueprint | `cron/blueprint_catalog.py:1-22` | 带类型槽位的参数化 cron 模板,14 条内置 |
| blueprint(skill 的) | `tools/blueprints.py:1-30` | 一个普通 skill,frontmatter 里带 `metadata.hermes.blueprint` 块 |

`tools/blueprints.py:1-13 @ 863e313`:
```python
"""Blueprints: shareable plain-language automations layered on skills + cron.

A "blueprint" is NOT a new object type. It is an ordinary skill (a SKILL.md the
agent loads) that additionally declares an automation schedule in its
frontmatter:
```
`cron/suggestions.py:11-13 @ 863e313` 的 `blueprint` 来源指的是**后者**:
```python
  * ``blueprint``   — the user installed a skill that carries a ``blueprint:`` block
                   (see ``tools/blueprints.py``); installing it registers a
                   suggestion instead of auto-scheduling.
```
文档把两者混为一谈:`website/docs/reference/automation-blueprints-catalog.mdx:31-35 @ 863e313`:
```
A blueprint is just a skill with a `metadata.hermes.blueprint` block in its
`SKILL.md` frontmatter. See
[Creating Skills → Automation Blueprints](../developer-guide/creating-skills.md) for the
slot schema and how to publish one.
```
▲ **文档说"去 creating-skills 看 slot schema"——但 skill 的 blueprint 块根本没有 slot。**
`tools/blueprints.py:57-69 @ 863e313` 的 `BlueprintSpec` 字段是
`skill_name / schedule / deliver / prompt / no_agent / model / provider / enabled_toolsets / raw`,
没有 slots;而真正的 slot schema 在 `cron/blueprint_catalog.py:60-80`。
`website/docs/developer-guide/creating-skills.md:344-357 @ 863e313` 的 Blueprints 一节也确实**不含任何 slot 说明**。
读者按文档指引找 slot schema 会扑空。

### ▲-4 `clear_resolved` 的 docstring 首句与实现矛盾

`cron/suggestions.py:246-260 @ 863e313`:
```python
def clear_resolved() -> int:
    """Drop accepted/dismissed records from disk. Returns the count removed.
    ...
    dismissed records must be RETAINED for their dedup_key ...
    This only prunes ACCEPTED records ...
    """
    with _suggestions_lock:
        suggestions = _load_raw().get("suggestions", [])
        kept = [s for s in suggestions if s.get("status") != _STATUS_ACCEPTED]
```
首句说 "Drop accepted/**dismissed**",第 3 段和代码都说只删 accepted。首句是错的。

### ▲-5 文档只说"dismissed 会闩锁",代码里 accepted 同样闩锁

文档 `website/docs/developer-guide/creating-skills.md:396 @ 863e313`:
> Dismissed suggestions latch by a stable key so the same proposal is never re-offered.

代码 `cron/suggestions.py:153-158 @ 863e313` 两种状态都闩:
```python
        for existing in suggestions:
            if existing.get("dedup_key") == dedup_key:
                if existing.get("status") in (_STATUS_DISMISSED, _STATUS_ACCEPTED):
                    return None
```
`cron/suggestions.py:134-136` 的 docstring 是准确的("already dismissed **or accepted**"),只有对外文档漏了。

### ◇-1 `/suggestions clear` 会打掉 accepted 的去重记忆 → 可重复建同一个 job

`clear_resolved` 删掉 accepted 记录后,该 `dedup_key` 的闩锁随之消失,
`/suggestions catalog` 会**再次**推荐同一条,用户再接受一次就得到**第二个一模一样的 cron job**
(`cron/jobs.py:1246-1264 @ 863e313` 的 `create_job` 签名里没有任何去重参数,也没有同 prompt/schedule 冲突检测)。
docstring 只说 accepted "have served their purpose once the job exists"(`:252-253`),
没有意识到用户可能先删 job 再 clear、或者只是做个 housekeeping。

### ◇-2 `accept_suggestion` 的 check-then-act 不在锁内(TOCTOU)

`cron/suggestions.py:231-243 @ 863e313`:
```python
    s = get_suggestion(ref)                      # 无锁读
    if not s or s.get("status") != _STATUS_PENDING:
        return None
    ...
    job = create_job(**spec)                     # 锁外副作用
    _set_status(s["id"], _STATUS_ACCEPTED)       # 这里才拿锁
```
两个并发 accept(例如用户在 CLI 和 Telegram 同时点)会**各建一个 job**。

### ◇-3 `suggestions.json` 只有进程内锁,而 `cron/jobs.py` 已升级为跨进程 flock

`cron/suggestions.py:24-25 @ 863e313` 声称:
```
Storage mirrors ``cron/jobs.py``: ``~/.hermes/cron/suggestions.json``, atomic
writes, an in-process lock, and 0600 perms.
```
但 `cron/jobs.py:104-108 @ 863e313` 早已不止进程内锁:
```python
_jobs_file_lock = threading.RLock()
_jobs_lock_state = threading.local()

# Upper bound on waiting for the cross-process .jobs.lock flock (#60703).
```
`cron/jobs.py:325 @ 863e313` 用的是真 flock:
```python
                            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
```
suggestions 侧只有 `threading.Lock()`(`cron/suggestions.py:53`)。CLI 进程和 gateway 进程同时写
`suggestions.json` 会**整文件后写覆盖先写**(读-改-全量写模式)。"mirrors cron/jobs.py" 这句已经过期。

### ◇-4 `suggestion_catalog` 的档期语法两种混用

`catalog:important-mail-monitor` 用 `"every 30m"`(`cron/suggestion_catalog.py:82`),其余三条用 5 段 cron。
`cron/suggestion_catalog.py:42 @ 863e313` 的注释承认了这点:
```python
# The curated set. Schedules use the cron/interval syntax create_job accepts.
```
但目录里没有任何机制保证新条目的档期字符串合法 —— 要到 `create_job` 才会炸,而那已经是用户点了 accept 之后。

### ◇-5 上限溢出对用户不可见

`cron/suggestions.py:161-163 @ 863e313` 丢弃只写日志:
```python
        if pending_count >= MAX_PENDING:
            logger.info("Suggestion backlog full (%d); dropping %r", MAX_PENDING, title)
            return None
```
`/suggestions catalog` 的回执(`hermes_cli/suggestions_cmd.py:134-140`)只在**一条都没加成**时提示上限,
加成 3 条丢了 1 条时只说 "Added 3 suggestion(s)",不说丢了谁。
(skills install 那条路径反而做对了 —— `hermes_cli/skills_hub.py:766-775` 明确告诉用户被丢了。)

### ◇-6 文档把 `usage` / `integration` 列为可用来源,代码里无生产端产生

`website/docs/developer-guide/creating-skills.md:383-387 @ 863e313`:
```
| Source | Trigger |
|--------|---------|
| `catalog` | Curated starter automations (`/suggestions catalog`) ... |
| `blueprint` | You installed a skill carrying a `blueprint:` block |
| `usage` | The background review noticed a recurring ask a schedule would serve |
| `integration` | You connected an account (Gmail, GitHub, ...) and the obvious automations are offered |
```
全仓 grep `source="usage"` / `source="integration"`:生产代码零命中,只有
`tests/cron/test_suggestions.py:65-79` 构造了一个 `source="usage"` 的记录。
同一文档第 372 行倒是标了 "(later)":
> the same place curated starter automations and **(later)** usage-pattern and integration suggestions appear.
—— 表格没标,表格与正文自己也不一致。`VALID_SOURCES`(`cron/suggestions.py:59`)是**为未来预留的空槽**。

### ◇-7 蓝图目录 vs 文档:**无漂移风险(设计使然)**

逐条对表的结论是:**蓝图清单不可能漂移**,因为文档站的清单是构建期生成的。
`website/scripts/extract-automation-blueprints.py:27-30 @ 863e313`:
```python
def build_index() -> list:
    from cron.blueprint_catalog import CATALOG, blueprint_catalog_entry

    return [blueprint_catalog_entry(r) for r in CATALOG]
```
产物被 gitignore,`.gitignore:118-120 @ 863e313`:
```
# automation-blueprints-index.json is a build artifact emitted by
# website/scripts/extract-automation-blueprints.py during prebuild.
website/static/api/automation-blueprints-index.json
```
文档页只挂一个 React 组件 `<AutomationBlueprintsCatalog />`
(`website/docs/reference/automation-blueprints-catalog.mdx:28`),运行时 fetch 那份 JSON
(`website/src/components/AutomationBlueprintsCatalog/index.tsx:26`:`const INDEX_URL = "/docs/api/automation-blueprints-index.json";`)。
**这是本簇最值得抄的一条做法:用户可见的清单一律从代码生成,不手写。**

对照之下,建议目录(4 条)是**手写在文档里**的
(`website/docs/developer-guide/creating-skills.md:384`:"daily briefing, important-mail monitor, weekly review, workday-start reminder"),
逐条比对当前代码 4 条 —— 恰好一致,**暂无漂移**,但没有任何机制防止它漂。

### ◇-8 `/blueprint` 别名 `/bp` 在文档里,代码里也有

`website/docs/reference/slash-commands.md:110 @ 863e313` 写 "(alias: `/bp`)",
代码 `hermes_cli/commands.py:282 @ 863e313`:
```python
               "Tools & Skills", aliases=("bp",), args_hint="[name] [slot=value ...]"),
```
一致,不算冲突,记录备查。

### ◇-9 desktop 在代码注释里直说后端的 deliver 帮助文案是错的

`apps/desktop/src/app/cron/blueprints.tsx:39-42 @ 863e313`:
```typescript
// Help text to show under a slot control. The backend deliver help is
// origin/dashboard-centric and even contradicts desktop semantics ("local =
// save only" vs. This desktop), and the DeliverSelect is self-explanatory —
// skip it for the deliver slot.
```
后端文案在 `cron/blueprint_catalog.py:114-117`。desktop 的解法是**整个丢掉 help 文本**而不是改后端 —— 
说明"一份 catalog 服务所有 surface"的理想在文案层面已经破了。

---

## 7. issue 溯源

本切片正文里只有 **1 个** issue 编号。

### `#4707` —— cron/suggestions 存储必须按 profile 隔离

`cron/suggestions.py:45-48 @ 863e313`:
```python
# Per-profile by design (issue #4707): suggestions live alongside the active
# profile's cron store. Anchor on get_hermes_home() (profile home), not the
# shared default root. See cron/jobs.py for the full rationale.
CRON_DIR = get_hermes_home().resolve() / "cron"
```
完整因果在 `cron/jobs.py:68-79 @ 863e313`:
```python
# Cron is per-profile by design (issue #4707). Each profile owns its own cron
# store under its own HERMES_HOME, and a profile-scoped gateway runs that
# profile's jobs under that same HERMES_HOME — so a job authored in profile
# `coder` lives in `~/.hermes/profiles/coder/cron/jobs.json` and executes with
# `coder`'s `.env`, `config.yaml`, and skills. We deliberately anchor on
# `get_hermes_home()` (the active profile home), NOT `get_default_hermes_root()`
# (the shared root). Anchoring at the root would funnel every profile's jobs
# into one shared `jobs.json` and run them under whatever HERMES_HOME the
# ticker process happens to have — leaking config/credentials/skills across
# profiles (the security boundary #4707 was filed for). Do NOT change this to
# the default root: that re-breaks per-profile isolation. See also the dynamic
# `_get_hermes_home()` / `_get_lock_paths()` resolution in cron/scheduler.py.
```

**因果经过**(git log 复原,`cron/suggestions.py` 的历史):
1. 最初 per-profile。
2. `a5c09fd17` "fix(cron): anchor cron storage at the default root home (not the active profile)" —— 改到共享根。
3. `bb7ff7dc3` "revert(cron): return cron job storage to per-profile (reverts #32117 + #50993) (#51116)" —— 回退。
4. `d73078e7b` "fix(cron): make per-profile cron isolation intentional and tested (#4707) (#53570)" —— 定论 + 加注释 + 加测试。

**什么输入 → 什么现象**:profile `coder` 里建的定时任务,如果 store 落在共享根,会被
任意 profile 的 ticker 进程捡起来,用**那个 profile 的 `.env` 和凭据**执行 → 跨 profile 凭据/技能泄漏。
`#4707` 就是为这个安全边界开的单。教训:多 profile 产品里,"数据放哪"和"用谁的凭据跑"必须锁死在同一个 home。

### 其余相关 issue(在依赖文件里,溯源用)

- `#60703` —— `cron/jobs.py:107-109 @ 863e313`,cross-process `.jobs.lock` flock 的等待上限。
  这是 §6 ◇-3 的对照物:jobs 侧已经补了跨进程锁,suggestions 侧没跟上。
- `#16743` —— `utils.py:99 @ 863e313`,`atomic_replace` 保留 symlink 的原因
  (`os.replace` 会把托管部署里指向 dotfiles 仓库的软链换成普通文件)。suggestions 的原子写靠它。
- `#44470` —— commit `021ed6914` "docs: finish Automation Blueprints terminology rebrand (#44470)",
  §6 ▲-1 那次重命名的收尾。

### 无编号但有完整因果的两次修复(commit 级溯源)

**(a) `*/90` 静默退化成每小时** —— `cron/blueprint_catalog.py:335-338 @ 863e313`:
```python
        # NOTE: cron minute-field steps (*/90) wrap per hour — */90 and */120
        # both degrade to hourly. Use an hour-field step instead so the chosen
        # cadence is what actually fires.
        schedule_template="0 {start_hour}-{end_hour}/{interval_hours} * * 1-5",
```
commit `e8b757845` 的 message:
> hydration-move: */90 in the cron minute field silently wraps to hourly (croniter-verified) — 90/120-minute options never fired at their stated cadence. Replaced with an hour-field step (0 9-17/2 * * 1-5) and an interval_hours slot whose options (1/2/3h) all fire as labeled.

**因果**:分钟字段的 `*/N` 语义是"在 0-59 这个范围内每 N 步",`*/90` 里 90 > 59,
只剩 minute=0 一个匹配 → 变成每小时。用户在 UI 上选"每 90 分钟",实际每 60 分钟被打扰一次,而且没有任何报错。
修法是把步进搬到**小时字段**,并把选项收缩到 1/2/3 小时。
回归测试锁死了这个行为(`tests/cron/test_blueprint_catalog.py:94-107`,用 croniter 断言相邻两次触发间隔 7200 秒)。
**教训:cron 表达式的取值域约束不会报错,只会静默降级 —— 任何暴露给用户的 cadence 选项都必须用真调度器验算一遍。**

**(b) 分类器绝对路径被烤进 job prompt** —— commit `e8b757845` message:
> important-mail catalog entry: reference the urgency classifier by module path (python3 -m cron.scripts.classify_items) instead of baking an absolute host path into the job prompt — stale after relocation and nonexistent on remote terminal backends. cron/scripts is now a real package and ships in the wheel (pyproject packages.find).

**因果**:job prompt 里原本写死了 `/Users/xxx/hermes-agent/cron/scripts/classify_items.py`。
job 一旦创建就把这串路径持久化进 `jobs.json`,于是 (1) 用户挪了安装目录 → 路径失效;
(2) 终端后端跑在 Docker/Modal 里 → 宿主路径在容器里根本不存在。两种情况下监控器都静默失灵。
修法:prompt 只说模块路径,让运行时自己解析。测试把这条钉死了
(`tests/cron/test_suggestions.py:143-145`,断言 prompt 里**必须**有 `cron.scripts.classify_items`、
**必须没有** `classify_items_script_path()` 的绝对路径)。
**教训:任何要持久化的 prompt 都不许包含宿主机绝对路径。**

**(c) 竞品名清洗** —— commit `e976faac7` 把 classify_items docstring 里的
`mirroring Poke's email monitor` 改成 `the classic urgency-monitor pattern`。现文见
`cron/scripts/classify_items.py:8-9 @ 863e313`。

---

## 8. 测试

| 测试文件 | 覆盖对象 | 用例数 |
|---|---|---|
| `tests/cron/test_blueprint_catalog.py`(205 行) | `cron/blueprint_catalog.py` + `hermes_cli/blueprint_cmd.py` + docs 生成器 | 21 |
| `tests/cron/test_suggestions.py`(183 行) | `cron/suggestions.py` + `cron/suggestion_catalog.py` + `tools/blueprints.py` 桥 + `hermes_cli/suggestions_cmd.py` | 15 |
| `tests/hermes_cli/test_cron_dashboard_off_loop.py:58-79` | `POST /api/cron/blueprints/instantiate` 的 create_job 必须离开事件循环 | 1 |
| `tests/tools/test_blueprints.py` | `tools/blueprints.py`(skill blueprint,非本切片) | — |
| **`cron/scripts/classify_items.py`** | **无任何直接测试** | **0** |

基线实跑(2026-08-07,`/home/user/hermes-venv`,Python 3.11.15):
```
$ HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
      tests/cron/test_blueprint_catalog.py tests/cron/test_suggestions.py
=== Summary: 2 files, 36 tests passed, 0 failed (100% complete) in 1.2s (8 workers) ===
```
(事后 `git status --porcelain` 无输出,基线仓库未被改动。)

**几条值得当行为规格读的用例**:

- **打错槽位名必须炸**(`tests/cron/test_blueprint_catalog.py:89-92`):
```python
    def test_unknown_slot_name_rejected(self):
        # A typo'd slot must NOT silently create a job with the default value.
        with pytest.raises(BlueprintFillError, match="unknown slot"):
            fill_blueprint(get_blueprint("morning-brief"), {"tiem": "07:15"})
```
- **deliver 是开放集**(`tests/cron/test_blueprint_catalog.py:82-87`):`deliver="slack"` 不在 options 里也必须通过。
- **hydration 的 cadence 必须真按选的来**(`tests/cron/test_blueprint_catalog.py:94-107`,croniter 验算 7200s 间隔)。
- **拒绝后闩锁**(`tests/cron/test_suggestions.py:54-59`):
```python
    def test_dismiss_latches_against_redisplay(self, store):
        _add(store, key="latch")
        assert store.dismiss_suggestion("1") is True
        assert store.list_pending() == []
        # Re-adding the same key is refused (never re-offer a dismissed one).
        assert _add(store, key="latch") is None
```
- **clear 只删 accepted、dismissed 的闩锁必须留着**(`tests/cron/test_suggestions.py:114-123`)。
- **上限 5**(`tests/cron/test_suggestions.py:81-86`)。
- **分类器只准用模块路径**(`tests/cron/test_suggestions.py:135-145`,见 §7(b))。

**测试缺口**:

1. `cron/scripts/classify_items.py` 零覆盖 —— `_load_items` 的三种输入形态、`_parse_scores` 的
   markdown 围栏容错与 `[...]` 兜底、四种退出码语义、"空 stdout = 静默"这条最关键的不变量,**全都没测**。
   §3.3 的 `_CLASSIFY_INSTRUCTIONS` 未使用能活到今天,直接原因就是这里。
2. `tests/cron/test_suggestions.py:127-132` 的断言在 catalog 增长后会假失败:
```python
        created = seed_catalog_suggestions(add_fn=store.add_suggestion)
        assert len(created) == len(CATALOG)
        assert len(store.list_pending()) == min(len(CATALOG), store.MAX_PENDING)
```
   `len(created) == len(CATALOG)` 在 `len(CATALOG) > MAX_PENDING`(即第 6 条 catalog 条目加入)时必然失败 ——
   第二行已经想到了上限(用了 `min(...)`),第一行没有。目前 4 < 5 所以侥幸通过。
3. `_resolve_schedule` 的 `schedule` 直通口(`cron/blueprint_catalog.py:607-609`)与
   `optional=True` 槽位分支都没有测试,也没有现货蓝图触发 —— 无覆盖的死代码。

---

## 9. 重实现要点(造自己的 harness 时怎么抄)

1. **模板层与执行层严格单向**。目录只生产 `create_job(**kwargs)` 的 kwargs,永远不自己实现调度、
   不自己写 job store。`cron/jobs.py` 对本簇零引用(§4)是可 grep 验证的硬约束,值得当纪律执行。
2. **一份 slot schema,四个渲染器**。表单 / 命令行 / 深链 / 文档卡片全部从
   `BlueprintSlot` 派生(`cron/blueprint_catalog.py:492-589`)。但要**警惕第五个渲染器**:
   本仓的"对话式填槽"路径(§1.5 路径 3)绕开了 `fill_blueprint`,把校验退化成 prompt 文本 ——
   如果要抄,建议让 agent 也回调同一个 `fill_blueprint`(比如给它一个 `fill_blueprint` 工具),
   而不是让它自己拼 cron。
3. **用户可见的清单必须从代码生成**。`extract-automation-blueprints.py` + gitignore 产物 + 前端 fetch
   (§6 ◇-7)是本仓最干净的一处防漂移设计。反例就在隔壁:建议目录手写进 markdown,只是碰巧还没漂。
4. **提议 ≠ 执行**。四道闸(来源白名单 / 已决闩锁 / 待办上限 / 显式 accept)是"系统主动性"的最小安全套件。
   `skills install` 装了个带 schedule 的 skill **不会**自动排期,只会进待办队列
   (`hermes_cli/skills_hub.py:743-757`)—— 这条 consent-first 的边界要在架构层就画死,不能靠每个调用点自觉。
5. **闩锁要区分"拒绝"和"接受"**,而且**清理动作不能顺手清掉去重记忆**(§6 ◇-1 是反面教材)。
   更稳的做法:去重记忆单独一张表(只存 `dedup_key` + 决策 + 时间),记录本体随便清。
6. **静默机制必须能区分"没事"和"坏了"**。`classify_items` 的退出码分层
   (0 = 无事 / 2 = 输入坏 / 3 = 环境坏 / 4 = LLM 坏,`cron/scripts/classify_items.py:61,71,155,162,179,191`)
   是 proactive monitor 的生命线。抄这条时顺便把它测了 —— 本仓正是因为没测,
   才让 `_CLASSIFY_INSTRUCTIONS` 未使用这种缺陷活了下来。
7. **给 LLM 的 prompt 里禁止出现绝对路径**,用模块路径 + 运行时解析(§7(b))。
   并且用测试把这条钉死,而不是靠 review。
8. **cron 表达式的取值域必须用真调度器验算**。`*/90` 静默退化(§7(a))这种坑,
   代码 review 看不出来,只有 croniter 跑一遍才现形。凡是暴露给用户的 cadence 选项,都要有一条
   "选了 N,实际间隔就是 N" 的回归测试。
9. **重命名脚本要绕开 prompt 字符串**。§6 ▲-1 的 "Keep blueprints simple and skimmable" 说明
   "No behavior change" 的重构声明在 LLM 系统里是不成立的 —— prompt 就是行为。
10. **跨进程共享的 JSON store 要用文件锁,不是 threading.Lock**。
    `cron/jobs.py` 补了 flock(#60703),`cron/suggestions.py` 没跟上(§6 ◇-3)。
    "storage mirrors X" 这种注释会随 X 演进而过期,不如直接把存储层抽成一个共享模块。
11. **`check → 副作用 → 标记` 三步要在同一把锁里**(§6 ◇-2 的 `accept_suggestion`),
    否则并发 accept 会双开 job。
