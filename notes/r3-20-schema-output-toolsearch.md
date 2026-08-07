# R3-20 Schema 清洗 + 工具输出经济 + 渐进式工具披露(子代理底稿)

> 由子代理精读产出,主线抽查关键行号与定案(三个 ◇:a 证实/b 修正/c 证伪)。基线 863e31318。
> 范围:schema_sanitizer(591)、tool_output_limits(110)、tool_result_storage(254)、
> tool_search(1078)、lazy_deps(1197)、fuzzy_match(1108)、ansi_strip(79)、binary_extensions(42)。

# R3 底稿 · Schema 清洗 + 工具输出经济 + 渐进式工具披露

> 溯源约定:凡对 hermes-agent 行为的断言,紧跟 `路径:行号 @ 863e313` + 逐字代码摘录。基线 commit `863e31318553cda8ad61df681d08175364d4164b`。本轮只读,未运行测试。
> 覆盖文件(wc -l 实测):`tools/schema_sanitizer.py`(591)、`tools/tool_output_limits.py`(110)、`tools/tool_result_storage.py`(254)、`tools/tool_search.py`(1078)、`tools/lazy_deps.py`(1197)、`tools/fuzzy_match.py`(1108)、`tools/ansi_strip.py`(79)、`tools/binary_extensions.py`(42);依赖旁证 `tools/budget_config.py`(115)、`model_tools.py`。加总 4459 行(不含旁证)。

---

## 0. 这一簇在 harness 里的位置(消费方接线)

三簇机制都挂在 `model_tools.py` 的两条主干上,先把接线钉死,后面每节只引用不重述。

**出站(装配模型可见工具数组)——`get_tool_definitions()` 的最后两步,顺序固定:**

`model_tools.py:570-572 @ 863e313`
```python
        from tools.schema_sanitizer import sanitize_tool_schemas
        filtered_tools = sanitize_tool_schemas(filtered_tools)
```
`model_tools.py:587-607 @ 863e313`
```python
        from tools.tool_search import assemble_tool_defs, load_config as _load_ts_config
        ts_cfg = _load_ts_config()
        if not skip_tool_search_assembly and ts_cfg.enabled != "off":
            context_length = _resolve_active_context_length()
            assembly = assemble_tool_defs(
                filtered_tools,
                context_length=context_length,
                config=ts_cfg,
            )
            ...
            filtered_tools = assembly.tool_defs
```
即:先清洗(schema_sanitizer),再渐进披露装配(tool_search)。清洗在前是有意的——注释 `model_tools.py:583-585` 说 "sanitization has already normalized schemas, and the assembly is idempotent"。

**入站(处理模型发来的 function_call)——`handle_function_call()` / `coerce_tool_args()`:**

- 参数纠偏 `coerce_tool_args()`(`model_tools.py:730`)在做类型 coercion 前,先把被清洗层重命名过的 property key 还原成注册表原始名:`model_tools.py:763-767 @ 863e313`
```python
        from tools.schema_sanitizer import unrename_tool_args
        args = unrename_tool_args(schema.get("parameters"), args)
```
`coerce_tool_args` 本身在 `handle_function_call` 内被调用于 `model_tools.py:1165`。
- 桥接工具分派 `model_tools.py:1220-1278`(见 §3)。
- 工具结果的三层限长/落盘/预算不在 model_tools,而在 `agent/tool_executor.py`(见 §2 消费方)。

---

## 1. 机制 A —— 工具 Schema 多后端兼容清洗层

### 1.1 问题(一次具体请求走法)

用户挂了 Cloudflare 的 flat-API MCP server。某个工具的参数 schema 里有一个 property key 叫 `issue_class~neq`,还有一个字段是 Pydantic 生成的 `{"anyOf": [{"type": "string"}, {"type": "null"}], "default": null}`。这份 schema 原样发给 Anthropic /messages,整个 tools 数组会被 400 掉——不是那一个工具失败,是**整条请求**失败,因为 Anthropic 校验 input_schema 的 property key 必须匹配 `^[a-zA-Z0-9_.-]{1,64}$`,而 `~` 不合法。同一份 schema 发给 llama.cpp 的 OAI server,又会撞上另一类错:它用 `json-schema-to-grammar` 把 schema 编译成 GBNF 语法,遇到裸 `{"type":"object"}`(无 properties)直接 `HTTP 400: Unable to generate parser ... Unrecognized schema: "object"`。

清洗层要解决的核心矛盾:**同一份工具 schema 要能同时喂给云端(Anthropic/OpenAI)和本地(llama.cpp)和一堆有各自怪癖的后端(Fireworks/Kimi、xAI Responses、Codex backend、Gemini OpenAI-compat 通道)**,而这些后端接受的 JSON Schema 子集互不相同、还都在"一个坏构造 400 整个请求"这种全或无语义下。

模块自陈的失败模式清单(逐字)——`tools/schema_sanitizer.py:12-30 @ 863e313`:
```python
The failure modes we've seen in the wild:

* ``{"type": "object"}`` with no ``properties`` — rejected as a node the
  grammar generator can't constrain.
* A schema value that is the bare string ``"object"`` instead of a dict
  ...
* ``"type": ["string", "null"]`` array types — many converters only accept
  single-string ``type``.
* ``anyOf`` / ``oneOf`` unions whose only purpose is to permit ``null`` ...
```

### 1.2 机制:一个主动 pass + 若干反应式 strip

**入口 `sanitize_tool_schemas(tools)`**(`tools/schema_sanitizer.py:120`)对每个 tool 深拷贝后跑 `_sanitize_single_tool`(138)。深拷贝是契约:`schema_sanitizer.py:125-127` 明说返回是 deep copy,调用方可安全 mutate,不影响 registry 原件。这点很关键——registry 里存的是"真名/原构造",清洗只作用于**发线**的副本。

`_sanitize_single_tool`(138-174)按序做:
1. 缺失/非 dict parameters → 补最小合法体 `{"type":"object","properties":{}}`(147-149)。
2. 递归 `_sanitize_node`(151)。
3. 顶层保证是 object 且有 properties(157-160)。
4. `strip_nullable_unions(..., keep_nullable_hint=True)`(166)——收尾折叠可空 union。
5. `_strip_top_level_combinators`(170)——剥离顶层 allOf/anyOf/oneOf/enum/not。
6. `_strip_ref_siblings`(173)——剥 `$ref` 同级的 `default`。

**剥离/改写的具体不兼容构造,逐条对号:**

**(i) 裸 object 补 properties**(llama.cpp GBNF 无法约束自由 object)——`schema_sanitizer.py:430-431 @ 863e313`:
```python
    if out.get("type") == "object" and not isinstance(out.get("properties"), dict):
        out["properties"] = {}
```

**(ii) schema 位置是裸字符串 `"object"`**(畸形 MCP 输出)→ 替换为 dict——`schema_sanitizer.py:319-329 @ 863e313`:
```python
    if isinstance(node, str):
        if node in {"object", "string", "number", "integer", "boolean", "array", "null"}:
            ...
            return {"type": node} if node != "object" else {
                "type": "object",
                "properties": {},
            }
```

**(iii) `type` 数组归一**:单非空类型→单字符串(+`nullable:true`);多非空类型→`anyOf`,**不丢分支**;全 null→`type:"null"`。移植自 anomalyco/opencode#31877。`schema_sanitizer.py:370-387 @ 863e313`:
```python
        if key == "type" and isinstance(value, list):
            has_null = "null" in value
            non_null = [t for t in value if isinstance(t, str) and t != "null"]
            if len(non_null) == 1:
                out["type"] = non_null[0]
                if has_null:
                    out.setdefault("nullable", True)
                continue
            if len(non_null) >= 2:
                out["anyOf"] = [{"type": t} for t in non_null]
```
设计取舍点:多类型不是取第一个(会静默丢分支),而是保留全部为 anyOf——注释 366-368 明说 "EVERY branch survives instead of silently dropping all but the first"。

**(iv) 可空 union 折叠**:`{"anyOf":[{string},{null}]}` → `string` + `nullable:true`。只在"确实丢了 null 分支且恰剩一个非空分支"时折叠(否则 union 有意义,保留)。`schema_sanitizer.py:284-301 @ 863e313`:
```python
        non_null = [
            item for item in variants
            if not (isinstance(item, dict) and item.get("type") == "null")
        ]
        if len(non_null) == 1 and len(non_null) != len(variants):
            replacement = dict(non_null[0]) if isinstance(non_null[0], dict) else {}
            if keep_nullable_hint:
                replacement.setdefault("nullable", True)
```
`nullable:true` 这个 hint 是刻意留的——注释 163-165 说要让运行期 `model_tools._schema_allows_null` 能把模型吐的字符串 `"null"` 映射回 Python `None`。

**(v) `$ref` 同级 `default` 剥离**(Fireworks/Kimi、draft-07 严格校验器拒绝 `$ref` 同级关键字)——`schema_sanitizer.py:178, 198-202 @ 863e313`:
```python
_REF_FORBIDDEN_SIBLINGS = frozenset({"default"})
...
    if "$ref" in out:
        for key in _REF_FORBIDDEN_SIBLINGS:
            if key in out:
                out.pop(key, None)
```

**(vi) 顶层 combinator 剥离**(OpenAI Codex backend `chatgpt.com/backend-api/codex` 比公开 Functions API 更严,顶层不许 oneOf/anyOf/allOf/enum/not)——`schema_sanitizer.py:205, 229-236 @ 863e313`。注释 218-220 强调:这些通常是 conditional-required 提示,剥掉不改变哪些**值**合法,因为"the tool handler always re-validates required fields"。且只剥顶层,property 内嵌 combinator 保留(223-224)。

**(vii) 非-schema 兄弟关键字的护栏**:`required`/`enum`/`examples`/`dependentRequired` 的值是字面量(property 名字符串、任意 JSON),不是 schema,不能递归清洗(否则 `"path"` 会被误当裸 string schema 替换成 dict)。`schema_sanitizer.py:409-424`。测试 `test_dependent_required_preserved_through_public_api` 正是这条的规格。

**(viii) `required` 裁剪到实际存在的 properties**(防畸形 MCP)——`schema_sanitizer.py:436-442`。

### 1.3 property-key 重命名往返(无损的关键)

这是本层最精巧处。Cloudflare flat API MCP 出 61 个非法 key(`issue_class~neq`、`meta.<field>[<operator>]`),一个坏 key 400 整条请求(注释 `schema_sanitizer.py:47-51`)。清洗层不能直接删——那会丢参数;要**重命名成合法 key 发给模型**,再在分派时**还原回原始 wire 名**。

无损靠的是"两侧独立地、确定性地算出同一张映射表",而非把映射存在某处传来传去。

**去程(装配时)**——`_rename_property_keys`(62-87)对不匹配 `_PROP_KEY_RE`(52:`^[a-zA-Z0-9_.-]{1,64}$`)的 key 用 `sanitize_property_key`(56-59,坏字符→`_`,截 64,空→`param`)算候选名,冲突加数字后缀去重。确定性来自:按插入序处理、`taken` 集合先装所有已合法 key。`schema_sanitizer.py:70-82 @ 863e313`:
```python
    renames: dict[str, str] = {}
    taken = {k for k in props if _PROP_KEY_RE.match(k)}
    for key in props:
        if _PROP_KEY_RE.match(key):
            continue
        base = sanitize_property_key(key)
        candidate, i = base, 2
        while candidate in taken:
            suffix = f"_{i}"
            candidate = base[: 64 - len(suffix)] + suffix
            i += 1
        taken.add(candidate)
        renames[key] = candidate
```

**回程(分派时)**——`unrename_tool_args(params_schema, args)`(90-117)拿 registry 的**原始**(未清洗)schema,**独立重算**同一张 `_rename_property_keys`,取逆表,把模型吐的 sanitized key 换回原名;递归进 object 值与 array items。`schema_sanitizer.py:102-105 @ 863e313`:
```python
    reverse = {v: k for k, v in _rename_property_keys(props, "<unrename>").items()}
    out = {}
    for key, value in args.items():
        orig = reverse.get(key, key)
        subschema = props.get(orig)
```
**无损保证的本质**:去程与回程都从同一份 props、用同一确定性算法算 rename 表;注释 63-69 点破——"the model-visible schema AND the dispatch-time reverse map (computed independently from the registry's original schema) always agree"。所以不需要任何 side-channel 存映射,天然抗 catalog 漂移。未知 key 原样透传(105 `reverse.get(key, key)`)。

### 1.4 反应式 strip(只在后端已拒绝时才动)

云端把 `pattern`/`format`/`enum` 当 prompting hint 接受;llama.cpp 的 regex 引擎只支持 ECMAScript 子集(拒 `\d\w\s`),xAI Responses 的 grammar 拒 enum 值含 `/`。所以默认 schema 保留这些,只在收到 400 时反应式剥。

- `strip_pattern_and_format(tools)`(454-528):**只**剥 `type`/`anyOf`/`oneOf`/`allOf` 的兄弟位(`is_schema_node`,492),因此名叫 `pattern` 的 property(如 `search_files.pattern`)不受伤——注释 485-491。返回 `(tools, stripped_count)`,原地 mutate。
- `strip_slash_enum(tools)`(531-591):剥字符串值含 `/` 的 enum(HuggingFace ID 如 `Qwen/Qwen3.5-0.8B`)。

**消费方(反应式触发点)**——不同后端在 catch 到 grammar 错误后各自调用:
- `agent/conversation_loop.py:4162-4163`(llama.cpp 恢复)`strip_pattern_and_format(agent.tools)`
- `agent/codex_responses_adapter.py:1134-1135` `strip_slash_enum`
- `agent/auxiliary_client.py:1288-1289`、`agent/chat_completion_helpers.py:1245-1246` 两者都调
- `agent/anthropic_adapter.py:1739-1741` 用 `strip_nullable_unions(schema, keep_nullable_hint=False)`(注意 Anthropic 侧不留 nullable hint)
- `tools/mcp_tool.py:5442-5444` MCP 摄入期就先 `strip_nullable_unions(..., keep_nullable_hint=True)`

### 1.5 取舍

- **保守优先**:只改后端本来就用不了的构造(模块 docstring 33-34 "intentionally conservative")。well-formed schema 原样返回(测试 `test_well_formed_schema_unchanged` 是规格)。
- **主动 vs 反应式的分工**:能提前判定的(裸 object、type 数组、非法 key、nullable union、顶层 combinator)在装配期主动清;云端仍接受的 hint(pattern/format/enum)留着,只在真挨 400 时才反应式剥——避免无谓削弱云端的 prompting 质量。
- **深拷贝成本**:每次装配深拷贝整个 tools 数组;换来 registry 原件不被污染、`unrename` 能靠原件独立重算。

### 1.6 重实现要点

1. 清洗只作用于发线副本,registry 保留原构造;还原靠"两侧独立确定性重算映射",不存 side-channel。
2. 后端差异按"全或无 400"处理:一个坏 key/构造能废整条请求,所以清洗必须遍历所有工具、所有嵌套层。
3. type 多分支归一走 anyOf 而非取首,信息不丢。
4. 折叠可空 union 时留 `nullable` hint 供运行期 `"null"`→`None` 复原。
5. 把"云端接受但本地拒绝"的关键字(pattern/format/enum)设计成反应式、按后端错误码触发,别默认全剥。
6. 非-schema 字面量位(required/enum/examples/dependentRequired)必须有护栏,别递归误改。

---

## 2. 机制 B —— 三层工具输出限长与结果持久化

### 2.1 问题(一次具体请求走法)

模型让 agent `grep -r foo /big-repo`,终端工具吐回 2 MB 文本。若原样塞进对话,一次就撑爆上下文窗口;直接截断又会丢掉模型可能真要读的后半段。更阴险的是:单个结果都没超阈值(比如 6 个各 42 KB 的结果),但一个 assistant turn 里加总 252 KB,合起来照样溢出。需要一个既保住"全量可回取"、又能在单结果和整轮两个粒度上限流的方案。

### 2.2 机制:三层,自陈架构

`tools/tool_result_storage.py:1-23 @ 863e313`(模块 docstring 逐字给出三层定义):
```python
1. **Per-tool output cap** (inside each tool): Tools like search_files
   pre-truncate their own output before returning. ...
2. **Per-result persistence** (maybe_persist_tool_result): After a tool
   returns, if its output exceeds the tool's registered threshold ...
   the full output is written INTO THE SANDBOX temp dir ...
   The in-context content is replaced with a preview + file path reference.
3. **Per-turn aggregate budget** (enforce_turn_budget): After all tool
   results in a single assistant turn are collected, if the total exceeds
   MAX_TURN_BUDGET_CHARS (200K), the largest non-persisted results are
   spilled to disk until the aggregate is under budget.
```

**第一层——per-tool cap(工具作者控制,唯一权威定义在 `tool_output_limits.py`)。** 集中三个可配值,来源 config.yaml `tool_output` 段,读失败一律回退默认。默认值刻意等于历史硬编码,加此模块行为不变(docstring `tool_output_limits.py:16-18`)。`tool_output_limits.py:39-41 @ 863e313`:
```python
DEFAULT_MAX_BYTES = 50_000       # terminal_tool.MAX_OUTPUT_CHARS
DEFAULT_MAX_LINES = 2000         # file_operations.MAX_LINES
DEFAULT_MAX_LINE_LENGTH = 2000   # file_operations.MAX_LINE_LENGTH
```
读取器防御性(任何异常回退默认,永不抛)——`get_tool_output_limits()`(59-89),进程级缓存(71-72),`_coerce_positive_int`(48-56)拒非正数。移植自 anomalyco/opencode PR #23770(docstring 3-4)。

**第二层——per-result 沙箱落盘 `maybe_persist_tool_result`(144-200)。** 阈值优先级由 `budget_config.BudgetConfig.resolve_threshold`(`budget_config.py:37-57`)决定:pinned > overrides > registry per-tool(封顶到 default)> default。`read_file` 被 pin 成 `inf`,防 persist→read→persist 死循环——`budget_config.py:11-13 @ 863e313`:
```python
PINNED_THRESHOLDS: Dict[str, float] = {
    "read_file": float("inf"),
}
```
超阈值则写入沙箱 temp 目录,in-context 内容换成 preview+路径块。落盘走 `env.execute()` 且**内容走 stdin 而非命令串**,因为 Linux `MAX_ARG_STRLEN` 把单个 argv 元素卡在 128 KB(#22906),而落盘要处理的恰恰是 >128 KB 的大结果——`tool_result_storage.py:113-116 @ 863e313`:
```python
    storage_dir = os.path.dirname(remote_path)
    cmd = f"mkdir -p {shlex.quote(storage_dir)} && cat > {shlex.quote(remote_path)}"
    result = env.execute(cmd, timeout=30, stdin_data=content)
    return result.get("returncode", 1) == 0
```
路径用 `shlex.quote` 防注入;文件名经 `_safe_result_filename`(64-79)清洗(坏字符→`_`,超长/改动过则加 sha256 前 12 位),防 `tool_use_id` 逃逸 storage 目录。替换块 `<persisted-output>`(119-141)告诉模型"用 read_file offset/limit 取全量"。存储目录按环境解析(Termux 用 `$TMPDIR`),默认 `/tmp/hermes-results`——`tool_result_storage.py:41`、`_resolve_storage_dir`(48-61)。落盘失败或无 env 时回退 inline 截断(196-200)。

**第三层——per-turn 聚合预算 `enforce_turn_budget`(203-254)。** 收齐一个 turn 的所有 tool 结果,加总超 `turn_budget`(默认 200K,`budget_config.py:18`)则按大小降序把最大的未落盘结果逐个 spill(threshold=0 强制落盘)直到低于预算。`tool_result_storage.py:228-244 @ 863e313`:
```python
    candidates.sort(key=lambda x: x[1], reverse=True)
    for idx, size in candidates:
        if total_size <= config.turn_budget:
            break
        ...
        replacement = maybe_persist_tool_result(
            content=content, tool_name=_BUDGET_TOOL_NAME,
            tool_use_id=tool_use_id, env=env, config=config, threshold=0,
        )
```
第三层复用第二层的落盘原语,只是把阈值压到 0。

**上下文自适应缩放(横切三层)**——小模型的窗口装不下固定 100K/200K。`budget_for_context_window`(`budget_config.py:84-114`)按窗口比例缩放(单结果 15%、整轮 30%),对大模型 clamp 到历史默认(字节级不变),对小模型按窗口缩、留 floor(#23767)。`budget_config.py:75-81`。

### 2.3 消费方接线(在 tool_executor)

三层不在 model_tools,而在 `agent/tool_executor.py`:
- 导入 `agent/tool_executor.py:48-51`(`maybe_persist_tool_result`、`enforce_turn_budget`、`budget_for_context_window`)。
- 预算按上下文缩放:`tool_executor.py:89` `budget_for_context_window(int(ctx)) if ctx else DEFAULT_BUDGET`。
- 单结果落盘调用点 `tool_executor.py:1463`、`2221`。
- 整轮预算调用点 `tool_executor.py:1565`、`2328`、`2391`(串行/并行/子序列三处)。

### 2.4 取舍

- **保住全量 vs 省上下文**:不硬截断,而是落盘+preview+路径,模型仍能 read_file 回取全量;代价是多一次工具往返、依赖沙箱可写。
- **落盘走 env.execute**:任何后端(local/docker/ssh/modal/daytona)一致可达,代价是走一次子进程;stdin 传内容绕过 128 KB argv 上限。
- **read_file 必须 pin inf**:否则 persist 的 preview 本身又触发 persist,死循环。
- **registry 值封顶到 default**:防小模型下 per-tool 注册的大 max_result_size 把缩放后的预算又顶回窗口之外(`budget_config.py:44-47`)。
- **三层分工**:第一层是工具作者的第一道防线(唯一它能控);第二层兜住单个巨结果;第三层兜住"很多中等结果加总溢出"这个第一二层都漏的场景。

### 2.5 重实现要点

1. 分三粒度:工具内预截断(可配)/单结果落盘(阈值分优先级、read_file pin inf)/整轮预算(复用落盘、阈值压 0)。
2. 落盘换成"preview + 沙箱路径 + 读回指令",而非丢弃;大内容走 stdin。
3. 文件名/路径做注入与逃逸清洗(shlex.quote + sha256 兜底名)。
4. 阈值随上下文窗口缩放,大模型 clamp 到历史值保证字节不变,小模型留 floor。
5. 整轮预算按"最大者先落盘"贪心,只动未落盘的。

---

## 3. 机制 C —— Tool Search 渐进式工具披露

### 3.1 问题(一次具体请求走法)

用户同时挂了 GitHub、Linear、Cloudflare 三个 MCP server。Cloudflare flat API 一家就 ~3300 个工具,光工具名 token 就 ~32K。若每轮把所有工具 schema 都塞进请求,单是工具数组就吃掉一大截窗口,而用户这一句"给我建个 GitHub issue"只用得上一个工具。要在"模型知道有哪些能力可用"和"不为每轮请求付全量 schema 成本"之间取平衡。

模块 docstring 的设计约束(逐字)——`tools/tool_search.py:1-35`,核心四条:核心工具永不 defer;tiered disclosure;catalog 每次重建无跨轮状态;桥接调用与直调走同一 `handle_function_call`。

### 3.2 机制:3 桥接工具 + 分层披露

激活时,MCP/plugin 工具从可见数组里撤下,换成三个桥接工具。名字被保留、注册表拒绝同名工具——`tool_search.py:55-59 @ 863e313`:
```python
TOOL_SEARCH_NAME = "tool_search"
TOOL_DESCRIBE_NAME = "tool_describe"
TOOL_CALL_NAME = "tool_call"
BRIDGE_TOOL_NAMES = frozenset({TOOL_SEARCH_NAME, TOOL_DESCRIBE_NAME, TOOL_CALL_NAME})
```
三工具语义:`tool_search(query, limit?)` 检索 catalog;`tool_describe(name)` 加载单个工具全 schema;`tool_call(name, arguments)` 调用被 defer 的工具。schema 定义在 `bridge_tool_schemas`(628-747)。

**分类:核心永不 defer。** `is_deferrable_tool_name`(204-227):桥接名不 defer、`_HERMES_CORE_TOOLS` 不 defer、MCP 前缀(`mcp-`)可 defer、非核非 MCP 的 plugin 也可 defer。`tool_search.py:212-225 @ 863e313`:
```python
    if name in BRIDGE_TOOL_NAMES:
        return False
    if name in _core_tool_names():
        return False
    ...
        if entry.toolset.startswith("mcp-"):
            return True
        return True
```
无法解析到 registry entry 的工具**不**声称可 defer(221-222 `entry is None → return False`),`classify_tools`(230-250)把不可分类者留在 visible——防 OpenClaw #84141 那类"cron 静默丢工具"。

**tiered disclosure(2026-07 方案):任何可 defer 工具存在就激活桥接;随 catalog 规模变化的是 listing 深度,不是激活决策。** `should_activate`(275-295):off 不激活,否则只要有 ≥1 可 defer 工具就激活——`tool_search.py:291-295`。threshold_pct 不再 gate 激活,改为 gate listing 预算(`listing_token_budget`,298-312:`min(listing_max_tokens, threshold_pct% of context)`,无窗口时回退 10K)。

三档(`assemble_tool_defs` 尾部定 tier,824-825):
- **Tier 0**:无可 defer 工具 → 纯透传(799 `if not deferrable: return ...activated=False`)。
- **Tier 1**:catalog listing 放得下 → 桥接 + skills 式清单(name+短描述,放不下降级 names-only)。
- **Tier 2**:names-only 都超预算 → 裸桥接 + 每 server 一行汇总(server 名+工具数),单个工具只能靠 `tool_search` 发现。

**listing 逐 server 降级(不是全局)**——`build_catalog_listing_with_form`(545-625)。关键取舍:一个巨型 server(Cloudflare 3320)不能拖累小 server(Linear 24)的 listing。贪心、最小 render 组先保、确定性(byte-stable → prompt 前缀可缓存)。`tool_search.py:614-622 @ 863e313`:
```python
    by_size = sorted(groups, key=lambda lbl: (-len(render_group(lbl, "names")), lbl))
    for lbl in by_size:
        modes[lbl] = "summary"
        if fits(assemble(modes)):
            form = "groups" if all(m == "summary" for m in modes.values()) else "mixed"
            return assemble(modes), form
```
form 有 full/names/mixed/groups/none 五种;tier = 1 if form∈{full,names,mixed} else 2(824-825)。

**为什么要 listing**:没有它,被 defer 的能力对模型"不可见",实测模型会拿可见的核心工具替代(在终端跑 `gh` 而不去搜 GitHub 工具),或直接宣称能力不存在。listing 把 skills 模式套到工具上——名字始终可见,full schema 仍 defer。`bridge_tool_schemas` 把 listing 嵌进 `tool_search` 描述,并按 form 给不同措辞(groups 型强制"先搜再说别替代",`tool_search.py:655-662`)。

### 3.3 BM25 检索 + substring 兜底

`search_catalog`(432-472)对 catalog 跑标准 BM25(`_bm25_score`,401-429,k1=1.5/b=0.75,内联实现不加依赖)。索引文本 `_entry_search_text`(343-358):工具名(下划线/点/连字符打散成词)+ 描述 + 顶层参数名;**不索引 schema 体**(注释 348-350:加噪不提召回)。

**substring 兜底**处理 BM25 退化:query 与所有文档只共享一个在每篇都出现的词(zero-IDF)时 BM25 全 0。`tool_search.py:464-469 @ 863e313`:
```python
    if not scored:
        ql = query.lower()
        for entry in catalog:
            if ql in entry.name.lower():
                scored.append((0.1, entry))
```
搜不到还会回 `available_sources` 汇总 + hint,让模型别把一次词法 miss 当成"能力不存在"(`dispatch_tool_search`,909-916;`_available_source_summary`,864-881)。

**catalog 无跨轮状态**:`build_catalog`(375-398)每次从当前 tool-defs 重建。注释 26-29 点明这是 OpenClaw cron 回归(#84141)的教训:session-keyed catalog 会与 live registry 漂移,产生静默 tool dropout。

### 3.4 会话范围防越权(双闸)

**闸一(catalog scoping)**:桥接分派时,`current_defs` 用**会话自己的** enabled/disabled toolsets 重新装配(`skip_tool_search_assembly=True`),而非全局 registry。`model_tools.py:1213-1217 @ 863e313`:
```python
            current_defs = get_tool_definitions(
                enabled_toolsets=enabled_toolsets,
                disabled_toolsets=disabled_toolsets,
                quiet_mode=True, skip_tool_search_assembly=True,
            ) or []
```
`dispatch_tool_search`/`dispatch_tool_describe` 都只在 `current_defs` 上搜(901、932),受限会话搜不到越界工具。

**闸二(invoke gate,defense in depth)**:`tool_call` 解析出 underlying 名后,再用 `scoped_deferrable_names(current_defs)` 校验它在会话可达集内。`model_tools.py:1246-1253 @ 863e313`:
```python
            _scoped_deferrable = _ts_mod.scoped_deferrable_names(current_defs)
            if underlying_name not in _scoped_deferrable:
                return _return_bridge_result(
                    tool_error(
                        f"'{underlying_name}' is not available in this session. "
                        ...))
```
`scoped_deferrable_names`(946-963)返回 tool-defs 中可 defer 的名集,注释 951-956 说这是"会话能通过 tool_call 合法触达的宇宙"。tool_executor 侧也有对称 unwrap 闸(`tool_executor.py:365`)。原 bug:两处 unwrap 读全局 registry,受限会话能搜/调整个进程注册表(测试 `TestRegression_ToolsetScoping` 是规格)。

**桥接透明**:`tool_call` 命中后**递归**调 `handle_function_call(function_name=underlying_name, ...)`(`model_tools.py:1262-1278`),所有 hook/guardrail/approval/截断都对**真名**触发,桥接对 hook 不可见(注释 1260-1261)。另有 blind-call 探针:缺 required 参数时返回 schema 而非盲派(`validate_deferred_call_args`,966-1016,port 自 nearai/ironclaw#5149)。

### 3.5 取舍(部分来自 prompt-cache 完整性不变量)

- 冷工具多 1 次(describe→call)往返;tier 1 有 listing 时通常省掉发现那跳(模型直接 describe)。
- deferred schema 拿不到 system-prompt cache 前缀收益。
- 依赖模型会写检索 query(小模型差;文档引 Anthropic 数 49%→74%)。
- 工具增删改 mid-session 会变桥接描述(含 deferred 计数)→ 使 prompt cache 失效——与任何 toolset 编辑同代价。
- 不做 JS sandbox code-mode(面积大),只用 structured tools(文档 §Implementation details)。

### 3.6 重实现要点

1. 三桥接工具(search/describe/call),核心工具白名单永不 defer,不可分类者留 visible。
2. 激活门槛降为"存在可 defer 工具即激活",token 预算改 gate listing 深度。
3. listing 逐 server 降级、确定性排序(byte-stable 保 cache),别让巨 server 拖垮小 server。
4. BM25 索引 name+desc+参数名(不含 schema 体)+ substring 兜底 zero-IDF。
5. catalog 每轮无状态重建,别用 session-keyed map。
6. 双闸防越权:catalog 按会话 toolset 装配 + invoke 时再校验 scoped set;桥接命中后递归真名让所有 hook 正常触发。

---

## 4. 机制 D —— lazy_deps 懒依赖安装

### 4.1 问题(一次具体请求走法)

用户第一次让 agent 用 ElevenLabs TTS。`elevenlabs` 这个包不是每个用户都需要,历史做法把它塞进 `[all]` extra 开箱全装——但只要 `[all]` 里任一传递依赖在 PyPI 被隔离/yank(比如 mistralai 2.4.6 恶意版本),整个 `[all]` resolve 就失败,新装机静默掉到裁剪档,一次丢十几个不相关 extra;且只跟一个 provider 说话的用户被迫拉几百个永不 import 的包(docstring `lazy_deps.py:9-17`)。懒装要在"按需装"和"绝不让一个坏后端包 brick 掉 agent 核心"之间给出安全模型。

### 4.2 机制

**允许清单 `LAZY_DEPS`**(97-323):dot 分隔 feature 名 → pip spec 元组,与 pyproject extra 对应。只有清单里的 spec 能走这条路(docstring 48-50)。spec 全 pin 精确版本,注释里标 CVE/隔离历史(如 `mistralai==2.4.8`,101、140,附 PyPI 2026-05-12 隔离说明)。

**入口 `ensure(feature, prompt=True)`**(834-964):不在清单→抛 `FeatureUnavailable`;算 `feature_missing`(829-831);平台不支持则抛(如 Windows 上 matrix,538-551);包管理器安装(NixOS 等只读 store)快速失败(872-886);每个 spec 过安全正则;查开关;TTY 且非 prompt_toolkit 才交互确认;跑 `_venv_pip_install`;失败带真实 pip stderr 抛出;装后清 importlib.metadata 缓存复核。

**安全模型(docstring 25-58 逐条)**:

- **默认 venv-scoped**:装进 `sys.executable` 的 venv,不碰系统 Python。
- **durable-target(不可变镜像)**:镜像封 venv(`HERMES_DISABLE_LAZY_INSTALLS=1` + `/opt/hermes` 只读)时,`HERMES_LAZY_INSTALL_TARGET` 把装机重定向到可写数据卷。该目录**追加到 sys.path 末尾**,绝不前插、绝不经 PYTHONPATH 导出——`lazy_deps.py:453-472`,核心 `_activate_target_on_syspath`。结构保证:懒装包只能**新增**模块,永不能 shadow/降级/破坏核心已发的模块。docstring `lazy_deps.py:40-44 @ 863e313`:
```python
  can only ADD new importable modules; it can never shadow, downgrade, or break
  a module the core already ships. The worst a bad/incompatible backend
  package can do is fail to import and report itself unavailable — the agent
  core stays healthy. This is the structural guarantee that a lazily
  installed package cannot brick Hermes ...
```
- **仅按包名从 PyPI**:不支持 `--index-url`/`git+https`/file:/`@`。`_spec_is_safe`(554-562)拒 URL、路径、shell 元字符;`_SAFE_SPEC` 正则(329-334)。
- **开关**:`security.allow_lazy_installs: false` 在两种模式都禁。`_allow_lazy_installs`(500-535):config kill switch 全局赢;`HERMES_DISABLE_LAZY_INSTALLS=1` 只在无 durable target 时拦(有 target 则重定向仍允许)。`lazy_deps.py:532-535 @ 863e313`:
```python
    if os.environ.get("HERMES_DISABLE_LAZY_INSTALLS") == "1":
        return _lazy_install_target() is not None
    return True
```
- **离线检测**:装失败(离线、镜像挂、404/隔离)直接 `FeatureUnavailable` 带真实 stderr,无静默重试、不缓存坏状态。

**ABI stamp**:durable target 写 `.python-abi` 戳(`_python_abi_tag`,387-396,X.Y + EXT_SUFFIX)。镜像重建换解释器时,旧编译 wheel(.so)ABI 不兼容,`_ensure_target_ready`(411-450)检测 stamp 不符则清空重装,防导入陈旧 .so。

**durable 装机加 core 约束**:`_core_constraints_file`(653-698)把核心 env 每个已装包 pin 成 `==` 约束传 `--constraint`,让共享传递依赖(httpx/pydantic/aiohttp)解析到核心已有版本;冲突后端在装期就响亮失败,而非静默装个永远赢不了 sys.path 的 shadow 副本。安装走 uv→pip→ensurepip 三级(`_venv_pip_install`,701-814)。

**其他 API**:`install_specs`(1000-1078,来自 manifest 的任意 validated spec,允许清单外包但仍过 hygiene);`active_features`(1081-1099,靠 anchor 包 `specs[0]` 存在判定,不拿共享 helper 当证据);`refresh_active_features`(1102-1144,`hermes update` 用,pin 移动时刷新);`ensure_and_bind`(1147-1197,装后回填 caller globals)。

### 4.3 取舍与重实现要点

- **追加 sys.path 而非前插**是"懒装不能 brick 核心"的结构性根基——这才敢封 venv。重实现时这条不可让步。
- 允许清单 + 安全正则双保险,拒一切非纯包名输入。
- 精确 pin + core 约束,防隔离传染与 shadow 降级。
- ABI stamp 让 durable store 跨镜像重建自愈。
- 失败带真实 stderr、不静默回退,可诊断。
- 两个 kill switch(config 全局 + 镜像封 venv 有 target 例外)语义要分清。

---

## 5. 机制 E —— fuzzy_match 工具参数/编辑模糊匹配

### 5.1 问题(一次具体请求走法)

模型发 `patch`:`old_string` 是它记忆里的一段代码,但缩进用了 2 空格而文件是 4 空格,还把文件里的 em-dash 当成了 ASCII `--`,tool-call 传输层又给某个撇号前加了根多余反斜杠。精确匹配会失败;可若无脑放松匹配,又会改错区域、或把文件的 Unicode/缩进冲掉。要在"容忍 LLM 生成代码的常见变形"和"绝不静默改错/毁坏文件"之间给出多策略链。

### 5.2 机制:9 策略链,精确→相似,逐级放松

`fuzzy_find_and_replace`(119-253)按序试 9 策略——`fuzzy_match.py:149-159 @ 863e313`:
```python
    strategies: List[Tuple[str, Callable]] = [
        ("exact", _strategy_exact),
        ("line_trimmed", _strategy_line_trimmed),
        ("whitespace_normalized", _strategy_whitespace_normalized),
        ("indentation_flexible", _strategy_indentation_flexible),
        ("escape_normalized", _strategy_escape_normalized),
        ("trimmed_boundary", _strategy_trimmed_boundary),
        ("unicode_normalized", _strategy_unicode_normalized),
        ("block_anchor", _strategy_block_anchor),
        ("context_aware", _strategy_context_aware),
    ]
```
前置拒绝:空 old_string、纯空白 old_string(不是有意义锚点,135-143)、old==new(145-147)。

**安全护栏(把"能匹配"和"敢写"分开):**

- **相似度策略不许 replace_all**:`block_anchor`/`context_aware` 是近似匹配,单点唯一替换安全,但 replace_all 会把不含 old_string 的区域也改掉——`fuzzy_match.py:166, 185-191`。
- **多匹配非 replace_all → 报错并列位置**:`_format_match_locations`(94-116)给出 `L<line>: snippet`,让模型一次消歧(加 context 或 replace_all),不用重读文件。
- **escape-drift 护栏**:非 exact 匹配时,若 new_string 含 `\'`/`\"` 而匹配区域没有,判定为 tool-call 序列化漂移(撇号/引号被加了多余反斜杠),拦下报错——`_detect_escape_drift`(256-293)。
- **条件 unescape `\t`/`\r`**:只在匹配区域真含对应控制字符时才 unescape(`_maybe_unescape_new_string`,380-413);`\n` 刻意排除(注释 398-400)。
- **Unicode 保留**:`unicode_normalized` 命中时,文件有 em-dash/smart quote 而 LLM 发 ASCII 等价,直接写 new_string 会毁 Unicode。`_preserve_unicode_in_replacement`(416-481)用 SequenceMatcher diff `norm_old→new`,只把真实编辑落到文件原文,未改部分保留原 Unicode。位置映射靠 `_build_orig_to_norm_map`(656-674,因 em-dash→`--` 会扩展,须逐字符建映射)。
- **重缩进**:非 exact 匹配时 `_reindent_replacement`(315-377)按 LLM base 缩进与文件 base 缩进的差,平移 new_string 每行,保 LLM 的相对嵌套、锚到文件实际缩进风格(注 356-360 引 Roo Code)。

**阈值收紧的历史**:`block_anchor` 用 0.50(唯一候选)/0.70(多候选)——注释 769-772 说旧值 0.10/0.30"危险地松,10% 中段相似就能匹配无关块";`context_aware` 要求首尾锚 ≥0.80 且**每条**非空行 ≥0.80——注释 800-804 说旧的"50% 行阈值"会接受半垃圾并毁掉不匹配行。

**辅助**:`is_already_applied`(67-91,最常见 patch 失败是重发已落地编辑,转成成功 no-op,保守:new 非平凡≥8 字符、精确出现、old 已消失);`find_closest_lines`(1012-1087,"did you mean" + 可视化空白差 `→`=tab `·`=space);`format_no_match_hint`(1090-1108,仅对真 no-match 触发)。

### 5.3 取舍与重实现要点

- 策略按"精确→相似"排,越靠后越危险,故越靠后护栏越多。
- "能匹配"≠"敢写":相似度匹配禁 replace_all;escape/unicode/缩进都在替换前对齐文件实际内容。
- 传输层伪影(多余反斜杠、`\t`/`\r` 字面化)靠"匹配区域是否真含对应字符"这个 region-based 启发式区分真假。
- 阈值宁紧勿松:错改一次比多报一次错代价大得多。

---

## 6. 两个支撑小机制

**`tools/ansi_strip.py`(79)** —— 剥 ANSI 转义,防转义码进模型上下文(根因是模型会把转义码抄进文件写入,docstring 3-6)。`strip_ansi`(46-55)覆盖全 ECMA-48(CSI/OSC/DCS/nF/8-bit C1,正则 16-29),快路径先查有无 ESC/C1(53)。`sanitize_display_text`(58-79)另剥裸控制字符、CR 归一为 LF,用于把持久化/不可信文本回显到终端 UI(防 `\r` 覆写伪造、清屏、改标题;镜像 openai/codex#31494)。被 terminal_tool/code_execution_tool/process_registry 消费。

**`tools/binary_extensions.py`(42)** —— 纯字符串扩展名判定,给文本类操作跳过二进制文件。`has_binary_extension`(37-42)`rfind(".")` 后查 frozenset,无 I/O。刻意排除 `.pdf`(注释 19:文本类,agent 可能想读)。移植自 free-code。

这两个是本簇的"输出卫生"边角,不涉决策逻辑,属知悉用途级即可。

---

## 7. 定案任务(逐条查 website/docs 对照)

### (a) ◇ 工具 Schema 多后端兼容清洗层(含 property-key 重命名往返)未见于文档 → **证实(细化:文档仅有一句 Gemini-adapter 侧模糊提及,不覆盖本层)**

`tools/schema_sanitizer.py` 作为独立机制在整个 `website/docs/` 中**零引用**:grep `schema_sanitizer`/`sanitize_tool_schema`/property-key rename 全空。开发者文档 `tools-runtime.md` 讲了 registry/dispatch/check_fn,但只字未提发线前的 schema 清洗、property-key 重命名往返、`strip_pattern_and_format`/`strip_slash_enum`、顶层 combinator 剥离。

唯一沾边的一句在 `website/docs/guides/google-gemini.md:247 @ 863e313`:
> "The native Gemini adapter sanitizes tool schemas for Gemini's stricter function-declaration format ..."

——那是 agent 侧 **Gemini adapter** 的行为,不是这个跨后端通用清洗层(它服务 llama.cpp/Anthropic/Fireworks/xAI/Codex 等),更没提本机制最核心的 property-key 重命名往返。故原 ◇ 判定成立:**多后端清洗层 + property-key 往返未见于文档**;修正处仅在于文档存在一句 Gemini-adapter 侧的、范围不同的 sanitize 提及,不构成对本层的覆盖。

### (b) ◇ 三层工具输出限长与结果持久化未见于文档 → **修正(第一层已文档化;第二、三层未见于文档)**

- **第一层(per-tool 截断上限)其实有文档**:`website/docs/user-guide/configuration.md:699-726 @ 863e313` §"Tool Output Truncation Limits" 记录 `tool_output.{max_bytes,max_lines,max_line_length}`,连默认值和缩放示例都有;`configuration.md:679-697` §"File Read Safety" 记录 `file_read_max_chars`。`reference/tools-reference.md:89` 也提 read_file "Reads exceeding ~100K characters are truncated on a line boundary and return a next_offset"。
- **第二层(`maybe_persist_tool_result` 沙箱落盘 `<persisted-output>` preview+路径)和第三层(`enforce_turn_budget` 200K per-turn 聚合预算)未见于文档**:grep `maybe_persist`/`tool_result_storage`/`persisted-output`/`hermes-results`/工具 turn budget 全空。文档里唯一 "spill" 命中是 `developer-guide/plugins/index.md:643` 的 `output_spill`(那是 `hook_output_spill.py`,hook 输出溢出,是**另一个**机制);"turn budget" 命中全是 `/goal` 的 20 轮预算(又是另一回事)。

故修正原 ◇:三层里**第一层(工具内截断上限)已作为用户配置文档化**,而真正的"结果持久化"架构——**第二层沙箱落盘 + 第三层 per-turn 聚合预算**——**未见于文档**。

### (c) ◇ Tool Search 渐进式工具披露(3 桥接工具 + BM25 + 分层 listing + 会话范围防越权)—— **证伪(有专门文档,且相当详尽)**

`website/docs/user-guide/features/tool-search.md` 是一整页专门文档,覆盖到位:
- 3 桥接工具签名与典型交互序列(`tool-search.md:32-47`)。
- tiered disclosure 的 tier 0/1/2 表 + 逐 server 降级(`tool-search.md:58-71`),连 Cloudflare 3300 工具/32K token 的例子都对得上代码。
- BM25 + substring 兜底(`tool-search.md:151-155`),zero-IDF 退化解释与代码一致。
- catalog 无跨轮状态(`tool-search.md:156-159`)。
- **会话范围防越权**(`tool-search.md:160-166 @ 863e313`):"The catalog is scoped to the session's toolsets ... cannot use the bridge to discover or call a tool outside that subset"。
- 桥接透明(hook 对真名触发,`tool-search.md:49-54`)、trade-offs(`tool-search.md:126-147`)、不做 JS sandbox(`tool-search.md:167-170`)。

故 ◇"未见于文档"**证伪**:此机制簇已充分文档化,文档甚至比代码注释更系统地列了 trade-off。

**唯一 territory 出入(map≠code)**:`model_tools.py:579 @ 863e313` 内联注释仍写 "when the deferrable surface exceeds the configured threshold (default 10% of context window)",但代码真实默认 `threshold_pct=5.0`(`tool_search.py:111,130`),且 tiered 方案下 threshold **已不再 gate 激活**(改 gate listing 预算,`should_activate` 291-295 只看"有无可 defer 工具")。这是模型侧内联注释的双重陈旧——tool-search.md 正文是对的(`threshold_pct: 5`、"no longer gates activation")。

**附带发现(fuzzy_match 的 in-code map≠code)**:`fuzzy_match.py:9-18` 模块 docstring 自称 "9-strategy chain" 却只编号列了 8 条(1-8),漏掉了 `unicode_normalized`;而实际 `strategies` 列表(149-159)是 9 条、`unicode_normalized` 作为第 7 位插在 `block_anchor` 前。docstring 的编号清单陈旧,与代码差一条。非 website/docs 冲突,但属本簇 territory 记录。

---

## 8. 本簇对应测试文件清单 + 3 个行为规格详述

`find tests -name '*schema*'/'*tool_search*'/'*tool_result*'/'*output_limit*'/'*fuzzy*'/'*lazy*'/'*ansi*'` 命中的、直接对应本簇的:

| 测试文件 | 行数 | 对应机制 |
|---|---|---|
| `tests/tools/test_schema_sanitizer.py` | 348 | A schema 清洗 |
| `tests/tools/test_tool_search.py` | 618 | C tool_search |
| `tests/tools/test_tool_search_context_provider.py` | 119 | C(上下文 provider) |
| `tests/tools/test_tool_result_storage.py` | 322 | B 三层落盘 |
| `tests/tools/test_tool_output_limits.py` | 141 | B 第一层配置 |
| `tests/tools/test_fuzzy_match.py` | 610 | E fuzzy |
| `tests/tools/test_lazy_deps.py` | 416 | D lazy_deps |
| `tests/tools/test_lazy_deps_managed.py` / `test_lazy_deps_durable_target.py` | — | D(durable/managed) |
| `tests/tools/test_ansi_strip.py` | — | ansi_strip |
| `tests/tools/test_mcp_schema_cache.py` / `test_memory_tool_schema.py` / `test_video_generation_dynamic_schema.py` | — | 邻接 schema |
| `tests/agent/test_gemini_schema.py` / `test_moonshot_schema.py` | — | adapter 侧 schema |

**挑 3 个最像"行为规格"的(与三个 ◇ 一一对应):**

### 规格 1 —— `tests/tools/test_schema_sanitizer.py`(机制 A)

读代码所断言的行为(不运行):
- 裸 `{"type":"object"}` → 补 `properties:{}`,嵌套同理并保留 description(`test_object_without_properties_gets_empty_properties` 23-26、`test_nested_..._gets_empty_properties` 29-42)。
- property 值是裸字符串 `"object"`(llama.cpp `Unrecognized schema:"object"` 的确切形状)→ 替成 dict(45-58)。
- `type:["string","null"]` → `type:"string"` + `nullable:true`(61-71);`["number","string"]` → `anyOf` **两分支都保**、`nullable` 不设、description 存活(74-91,port opencode#31877);`["null"]`→`type:"null"`(94-104);`["string"]`→`string`(106-116)。
- 缺失/非 dict parameters → 补最小 object(137-146);`required` 裁到实际存在的 property(149-156);well-formed 原样不变(159-170)。
- `additionalProperties`/`items` 内的裸 object 也被清洗(173-200)。
- 反应式:`strip_pattern_and_format` 同时处理 OpenAI-format 与 Responses-format,剥 pattern+format 各一、结构保留(210-254)。
- property-key:`sanitize_property_key("~~~")=="___"`、`("")=="param"`(276-278)。
- `dependentRequired` 值是字面 property 名,清洗后原样、且不 mutate 输入(286-329);`dependentSchemas`(真 schema)仍被递归清洗(332-348)。
> 缺口备注:未见 rename→unrename 完整往返的端到端断言(仅测了 `sanitize_property_key` 与 `dependentRequired` 保留);往返无损主要靠"两侧独立重算"的代码结构保证,测试覆盖偏薄——可作后续补测建议。

### 规格 2 —— `tests/tools/test_tool_result_storage.py`(机制 B)

- 文件头逐字自陈 "3-layer tool result persistence"(第 1 行),与代码 docstring 三层对齐。
- 落盘走 stdin 不进命令串:普通内容(`test_success` 61-73,断言 `"hello world" not in cmd` 且 `stdin_data=="hello world"`)、200 KB 大内容(`test_large_content_via_stdin` 76-85,断言 `len(cmd)<1000`——即命令只是 `mkdir -p X && cat > Y`)。这是 #22906(128 KB argv 上限)的回归规格。
- 路径注入中和:空格、`$(whoami)`、`;` 都被 `shlex.quote` 包住(88-114);`tool_use_id` 逃逸被 `_safe_result_filename` 拦(219-239,断言 target 不含 `/../`、`$(whoami)`、`;`)。
- 阈值语义:低于阈值原样(172-181);高于阈值 + 有 env → `<persisted-output>` + `{id}.txt` 且结果更短(183-197);内容逐字落盘不做 JSON 抽取(199-216);threshold=0 强制落盘(242-254)。
- **第三层规格 `test_medium_result_regression`(270-284)**:6 个各 42K(共 252K),每个都低于 100K 单结果阈值但加总超 200K,断言 `persisted_count>=2`——正是"多中等结果加总溢出"这个第一二层都漏的场景。
- per-tool 阈值 registry 接线:`read_file` cap 必须是 100_000 而非 `inf`(302-313,注释明说 inf 会关掉第二层护栏)。
> 版本小噪:`test_tool_use_id_cannot_escape_storage_dir`(219-239)用 `cmd.split(" <<", 1)` 解析 heredoc 边界,但现实现已改 stdin(命令里无 ` <<`),split 无匹配返回全余串——断言仍通过,但解析逻辑与当前 `_write_to_sandbox` 的 stdin 路径略脱节。属可注意的测试陈旧,不影响机制结论。

### 规格 3 —— `tests/tools/test_tool_search.py`(机制 C)

- **硬不变量:核心工具永不 defer**——`test_core_tools_never_defer`(71-81)遍历 terminal/read_file/.../send_message 断言全不可 defer;桥接名不可 defer(83-86);未解析工具不声称可 defer(88-93);不可分类者留 visible(`test_classify_keeps_unknown_in_visible` 95-107,标注 OpenClaw #84141 回归)。
- 门控:off 永不激活(116-119);token 估算与 schema 大小成比(122-130)。
- 检索:`"create a github issue"` 命中首位 `github_create_issue`(163-167);limit 生效(170-173);空搜仍让 connected sources 可发现(`test_empty_search_keeps_connected_sources_discoverable` 234-258,断言返回 `available_sources` + hint "remain available"/"before concluding")。
- 装配:纯核心透传不加桥接(182-192);桥接已在则幂等剥离(209-220);`tool_call` 不能递归调 `tool_call`(271-279)。
- **会话范围防越权 `TestRegression_ToolsetScoping`(394-461)**:注册 12 个 `mcp-scoped-gh` + 1 个越界 plugin,`tool_search` 限 `enabled_toolsets=["mcp-scoped-gh"]` 时断言 `total_available==12` 且越界 plugin 不在命中里(425-445)——正是防越权的行为规格。
- listing:默认 manifest token 不回涨到旧 20K(479-509,断言 `description_tokens<4500`、form∈{names,groups,mixed});`_short_desc` 取首句截 60(511-518);`listing:off` 回退无清单描述(536-547)。
- blind-call 探针(port ironclaw#5149):缺 required 参数返回 schema 而非盲派(587-597);未知工具不拦(600-604);合法调用照常分派(607-618)。
- 端到端:`tool_search` 经真 `handle_function_call` 恰好触发一次 `post_tool_call` 终态 hook(300-340)——印证"桥接对 hook 透明、走完整生命周期"。

---

## 9. 一句话结论

本簇是 harness 的"工具基础设施经济层":schema_sanitizer 用发线副本 + 两侧独立重算的 property-key 往返做到多后端无损兼容;三层输出限长把"保住全量可回取"和"单结果/整轮双粒度限流"分层解耦;tool_search 用"永不 defer 核心 + tiered listing + BM25 + 双闸 scoping"在能力可见性与每轮 token 成本间取平衡;lazy_deps 用"sys.path 末尾追加"的结构性保证让懒装包永不 brick 核心;fuzzy_match 用"能匹配≠敢写"的护栏链容忍 LLM 变形而不毁文件。三个 ◇ 定案:(a) 证实(未见于文档,仅 Gemini-adapter 侧一句模糊提及);(b) 修正(第一层已文档化,第二三层未见于文档);(c) 证伪(有专门且详尽的 tool-search.md)。
