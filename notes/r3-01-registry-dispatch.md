# R3-01 工具注册表、发现、分发:窄腰的三根柱子

> 底稿(求全求证)。基线 `863e31318`。范围:`tools/registry.py`(956)、`model_tools.py`(1569)、
> `toolsets.py`(1004)。AGENTS.md 称核心是"narrow waist"(窄腰):每个工具都在每次 API 调用被发送,
> 所以核心工具的门槛很高。这三个文件就是那道腰。

## 1. AST 自注册发现(registry.py:30-159)

**问题**:100+ 个工具文件,不想手工维护 import 清单。**机制**:每个 `tools/*.py` 在模块级调用
`registry.register()` 自注册;`discover_builtin_tools` 只导入那些"顶层有 registry.register() 调用"的模块。

判定用 AST 而非执行:`_module_registers_tools` 先文本预过滤(source 必须同时含 "registry" 和 "register"),
再 `ast.parse`,只看 `tree.body`(模块体语句)——helper 模块在函数**内**调 register 不算(43-64)。
判定谓词:`_is_registry_register_call` 精确匹配 `registry.register(...)` 的 Expr/Call/Attribute/Name 结构(30-40)。

`tools/registry.py:57-58 @ 863e313`:
```python
    if "registry" not in source or "register" not in source:
        return False
```

**磁盘缓存**:AST 扫描 ~100 文件 ~145ms,按 `(mtime_ns, size)` memoize 到磁盘;match 就信任、
mismatch 就重扫;写入 best-effort + 原子,并发进程无害竞争(67-119)。`mcp_tool.py` 被显式排除
(85 行,MCP 工具是动态注册,不走这条静态发现)。

**取舍**:AST 判定比"import 试错"安全(不执行副作用),比"维护清单"省事;代价是一层磁盘缓存的复杂度。
**重实现要点**:自注册 + AST 静态发现 + (mtime,size) 磁盘 memo,是"零维护工具清单"的干净解法。

## 2. check_fn 可用性:TTL 缓存 + 瞬断宽限(registry.py:192-372)

**场景**:一个工具的 `check_fn` 探测外部状态(Docker daemon 在不在、playwright 装没装)。这类探测昂贵
(subprocess 调用 + 超时),且会抖动——负载高时一次 `docker version` 超时返回 False,会让整个
terminal+file 工具集从正在构建的 agent(最常见是 delegate_task 子代理)schema 里消失,子代理随后报
"Tool read_file does not exist"。

**机制**:两层。① **30s TTL 缓存**(`_CHECK_FN_TTL_SECONDS = 30.0`,216):外部状态按人类时间尺度变,
每次 get_definitions 都重探纯浪费。② **60s 瞬断宽限**(`_CHECK_FN_FAILURE_GRACE_SECONDS = 60.0`,220):
记住每个 check_fn 上次返回 True 的时间;若一次新探测在上次成功的宽限窗口内失败,**返回 last-good True**
而非缓存这个失败——吸收 flake,但不会把"永久可用"钉死(真的宕机超过宽限窗就如实反映)。

`tools/registry.py:216-220 @ 863e313`:
```python
_CHECK_FN_TTL_SECONDS = 30.0
# How long after a successful check a subsequent transient failure is treated
# as a flake (last-good True is served) rather than a real outage. Kept short
# so a genuinely-down backend is reflected within a couple of turns.
_CHECK_FN_FAILURE_GRACE_SECONDS = 60.0
```

缓存按 **profile 维度隔离**(`check_fn_cache_scope`,246-268):多租户 gateway 每个 profile 回合装了
HERMES_HOME override,profile key 是稳定隔离边界;解析不出 profile 身份时 fail-closed 绕过两层缓存。
这条正是 R2 报告 §2.16 冲突 #19(tools-runtime.md 说"cached per-call",实际是 30s TTL + 60s 宽限)的实现。

**重实现要点**:昂贵的可用性探测要 TTL 缓存;更关键的是给"瞬断"设宽限,否则一次抖动会误删整个工具集。

## 3. 插件覆盖授权:绑定在 handler 的定义处(registry.py:472-604)

**场景**:一个插件想把内置 `browser` 工具换成自己的 headed-Chrome 后端(合法);但也可能一个恶意/失误
插件想悄悄替换 `read_file`。怎么区分?

**机制**:`register(override=True)` 是显式 opt-in。授权绑定在 **handler 被定义的模块**
(`handler.__globals__["__name__"]`)——这是定义时固定的,不随调用点/线程/时序漂移;lambda 和嵌套函数
继承定义模块的 globals,所以插件无法用回调"洗白"一个 override(481-503)。跨 toolset 的覆盖若来自插件
且未 operator opt-in(config 的 `allow_tool_override`),直接 `raise PermissionError`(548-562)。

`tools/registry.py:494 @ 863e313`:
```python
        mod = handler.__globals__.get("__name__", "")  # type: ignore[attr-defined]
```

`deregister` 没有 handler 参数可绑,只能用帧检查 `_caller_module`(505-519);受同一 opt-in 门控——
否则插件可以"先 deregister 掉别人的工具、再对空槽 register"绕过 override 门(612-620 注释)。

非 override 的跨 toolset 影子注册**一律拒绝**(包括 MCP-to-MCP 撞车);合法的 MCP 重连在同一 canonical
toolset 内重注册,允许(570-581)。

**重实现要点**:授权谓词要绑定在"代码定义处"这个不可伪造的锚点上,不能绑在调用栈(可伪造)。

## 4. get_definitions:动态 schema + 缓存(registry.py:676+ / model_tools.py:305-388)

`ToolEntry`(160-189)带 `dynamic_schema_overrides`:一个零参 callable,在每次 get_definitions 时求值,
把依赖运行时 config 的字段(如 delegate_task 描述里的 max_concurrent_children/max_spawn_depth 实际值)
浅合并到 base schema 上——否则模型被告知错误的限额。

`get_tool_definitions`(model_tools.py:305)是消费入口,带一个精心构造的 memo:cache_key 捕获
enabled/disabled toolsets、`registry._generation`(注册表变更计数,MCP 刷新/插件加载会 +1)、
config 文件的 `(mtime_ns, size)` 指纹(捕获影响动态 schema 的 config 编辑)、kanban/delegated/dispatcher
上下文、profile scope(346-358)。check_fn 结果在下一层 registry.get_definitions 里 TTL 缓存。

一个真实事故记在注释里(374-378):long-lived Gateway 进程跨多次 agent init 累积重复工具名,而
DeepSeek/Xiaomi MiMo/Moonshot Kimi 这些强制工具名唯一的 provider 会 HTTP 400 拒绝——所以缓存返回的是
**浅拷贝列表**(共享 dict 引用但列表独立),让下游 append(记忆/LCM schema)不污染缓存(#17335);
缓存本身 LRU 上限淘汰防无界增长(#19251)。

**重实现要点**:工具 schema 是每次请求都发的东西,memo 的 cache_key 要捕获所有影响它的输入(注册表
版本 + config 指纹 + 上下文),返回浅拷贝防下游污染。

## 5. handle_function_call:分发管线的固定顺序(model_tools.py:1123-1514)

一次工具调用流经的顺序是固定的,每一段有明确职责:

```
coerce_tool_args(参数纠偏 "42"→42)                                    # 1165
  → Tool Search 桥接分发(tool_search/describe 内联;tool_call 解包成真实工具)  # 1170-1249
  → _AGENT_LOOP_TOOLS 拦截(todo/memory 等由 run_agent 循环处理,这里报错)      # 1301-1302
  → pre_tool_call 插件 block 钩子(单次触发;block 或 approve-但人审拒绝→fail-closed) # 1315-1348
  → ACP/Zed edit approval(仅 ACP 会话经 ContextVar 绑定,CLI/gateway 不受影响)   # 1350-1358
  → middleware 包裹的 _dispatch(实际执行)                                # 1440-1455
  → post_tool_call 观察钩子                                             # 1464-1475
  → transform_tool_result 改写 seam(插件可替换结果字符串,fail-open,首个 str 胜) # 1485-1512
```

关键设计:**Tool Search 桥接把 tool_call 解包成真实工具名再下沉**(1170-1174 注释),让所有下游钩子
(pre/post、edit approval、guardrails)看到的是真实工具而不是桥接名。桥接的 catalog 用
`enabled_toolsets/disabled_toolsets` 限定作用域——受限会话(子代理、kanban worker、curated gateway)
不能通过桥接看到并调用整个进程注册表(1204-1216,防越权,详见子代理底稿 r3-30)。

`_AGENT_LOOP_TOOLS` 拦截是 AGENTS.md 说的"agent-level tools(todo/memory)由 run_agent 在
handle_function_call 之前拦截"的另一半:这里对它们返回错误,保证它们只能走循环内路径。

所有 handler 必须返回 JSON 字符串;错误统一经 `tool_error` + `_sanitize_tool_error`(710)包裹;
结果按 `max_result_size_chars` 限长(见 r3-20 三层输出)。

**重实现要点**:分发是一条固定顺序的管线,把"参数纠偏 / 渐进披露解包 / 循环级工具拦截 / 审批 / 中间件 /
观察钩子 / 结果改写"分成正交的段,每段单一职责;桥接工具要解包成真实工具让下游钩子无感。

## 6. toolsets.py:暴露面控制(toolsets.py:31-540)

`TOOLSETS` 是单个 dict,每个平台适配器选一个基础 toolset;`_HERMES_CORE_TOOLS`(31-100)是大多数平台
继承的默认核心集。工具**注册了但不等于暴露**——AST 发现导入并注册 schema,但工具只有名字出现在某个
toolset 里才对 agent 可见(AGENTS.md 明确:`_HERMES_CORE_TOOLS` 不是死代码,是每个平台基础 toolset
继承的默认包)。这是"窄腰"的策略层:注册(机制)与暴露(策略)分离,让同一批工具在 CLI/messaging/cron/
子代理各有不同的暴露面而无需改工具本身。

**重实现要点**:把"工具存在"与"工具对某个 agent 可见"拆成两层——注册表管前者,toolset 管后者;
新增能力优先进 toolset 而非核心集,守住"每次请求都发"的成本红线。

## 7. 边界与延伸

- R2 已覆盖工具**批次执行**(tool_executor.py 分段调度),本簇是它的上游:注册/发现/分发/暴露。
- 参数纠偏 `coerce_tool_args`(model_tools.py:730)细节、schema 清洗见 r3-20。
- 审批层(approval/url_safety/threat_patterns/tirith)见 r3-10。
- execute_code 与 MCP 客户端见 r3-30。
- 行为规格测试见 r3-95。
