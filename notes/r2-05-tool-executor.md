# R2-05 工具批次执行:分段调度、启动顺序门、授权门

> 底稿。基线 `863e31318`。范围:`agent/tool_dispatch_helpers.py`(732,分段规划)、
> `agent/tool_executor.py`(2403,并发/顺序/分段三执行器)、`run_agent.py:7593-7635`(分派入口)。

## 0. 入口三分支(run_agent.py:7593-7635)

`_execute_tool_calls` 在 `_executing_tools=True` 保护下:
- **≤1 个调用** → `_execute_tool_calls_sequential`(7609-7612);
- 否则 `_plan_tool_batch_segments(tool_calls, execution_cwd)` 分段(7614-7617);
- **单段** → 按 kind 走 concurrent 或 sequential(7619-7627);
- **多段** → `execute_tool_calls_segmented`(7629-7633),按发出顺序逐段跑。

## 1. 分段规划(agent/tool_dispatch_helpers.py:116-235)

把批次切成有序 `(kind, calls)` 段,kind ∈ {parallel, sequential},**保持模型原始顺序**——
后一个调用永不越过前一个 barrier,故工具结果顺序与副作用边界和全顺序执行完全一致(117-127 docstring)。
逐调用安全规则:
- `_NEVER_PARALLEL_TOOLS`(仅 `clarify`,交互式)→ barrier(46-48);
- 参数不可解析 / 非 dict → barrier(173-193);
- **路径作用域工具**(`read_file`/`search_files` 读,`write_file`/`patch` 写):目标路径与本 run 已预留路径**不冲突**才加入并行 run;预留带 reader/writer 角色——reader↔reader 重叠无害(两读可交换)保持并行,任何涉及 writer 的重叠关闭 run(63-79 常量 + 规划体);`search_files` 预留搜索根(默认 `.`)为 reader——批在写之后的搜索被排到写后而非与之竞态;V4A `patch(mode="patch")` 预留的是 patch body 里的文件头而非可能过期的 `path=` 参数(128-140 docstring);
- 不在 `_PARALLEL_SAFE_TOOLS`(50-61)且非 opted-in MCP 工具 → barrier;
- **短于 2 的并行 run 降级为 sequential**(无并发收益,且顺序执行器有更丰富的内联分派),相邻 sequential 段合并(141-143 docstring)。

这是 R1 ▲ 定案(agent-loop.md:133 "多工具并发 via ThreadPoolExecutor")的精确反例:真实调度是分段的,不是无脑并发。

## 2. 并发执行器的两道门(agent/tool_executor.py:751-1170)

`execute_tool_calls_concurrent` 用 `DaemonThreadPoolExecutor`(1166-1167,daemon 线程,`shutdown(wait=False)`
后不阻塞进程退出)。两道有界门:

**(a) 启动顺序门 `_begin_in_order`(903-948)**:按提交序串行化 dispatch(让工具结果与顺序执行一致);
`start_condition.wait_for(next_start_order >= order or batch_abandoned)`。**有界**(`_START_ORDER_GATE_TIMEOUT_S`
或 batch_deadline/2 取小,898-901):一个卡在 dispatch 里的工具不能永久 park 后面所有 worker;超时则乱序继续
(最坏交错审批提示,强于永久饿死);`>=` 谓词让一次超时跳跃立即释放所有被跳过的 worker;`batch_abandoned`
短路让废弃批次毫秒级释放 parked worker(#79705/#79719 注释)。

**(b) 授权门 `_ConcurrentToolAuthorizationGate`(384-461)**:串行化审批提示(防并发提示在屏幕上交错);
acquire **有界**(卡在 pre_tool_call 插件或对端消失的审批往返里的 worker 不能永久 park 别人,超时则不串行化运行);
关键设计——**人审等待从批次 deadline 里扣除**是在人审的**源头**测量(`tools.approval.human_wait_seconds`:
CLI 提示与 gateway 审批轮询各自标记阻塞窗口),**不是**用门内驻留时间(#79719:卡死插件的驻留会 1:1 撑大
排除量,让 batch deadline 的 remaining 恒定永不触发、回合永挂;现在卡死插件对排除贡献为 0,批次正常超时,
而真正的人审等待仍全额排除,395-403 docstring)。

`batch_abandoned` Event(885-892):批次超时后 `_abandon_batch` 置位并 notify_all 释放所有 gate-parked worker,
使其不再在 abandon 后 dispatch——回合已合成该工具结果并继续。

## 3. 分段执行器(agent/tool_executor.py:2339+)

`execute_tool_calls_segmented` 按段:parallel 段走并发路径、sequential 段走顺序路径,
保持发出顺序、无调用越过前 barrier(2344-2347)。各段 `finalize=False` 调用,由 segmented 统一收尾。

## 4. 重实现要点

1. 混合批次不能一刀切并发或顺序:按只读性 + 文件目标重叠 + 交互性切段,保发出顺序与副作用边界。
2. 路径冲突判定要带 reader/writer 角色,reader↔reader 可并行;写工具预留真实目标(patch 读 body 头)。
3. 并发的每一道门都必须有界,超时降级为"乱序/不串行化"而非永久 park。
4. 把人审等待排除在批次超时之外,但要在人审源头测量,绝不用"门内驻留时间"(会被卡死代码撑爆)。
