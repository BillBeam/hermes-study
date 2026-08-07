# R4 报告:终端与执行环境

**一句话结论:执行环境学透,定案八条。**

- 基线:`863e31318`(只读,工作树零改动,校验一致)
- 本轮机制簇:终端与执行环境(R3 报告建议的 R4)
- 分支:`claude/hermes-agent-round-4-ogproh`(从合并后的 main 起);R3 已作 PR 合入 main
- 交付:底稿 6 篇 + 成品章 1 章 + 定案 8 条 + 测试 664 用例 + 台账 status 更新并重跑校验

---

## 1. 台账报数(三项校验全过)

`assign_layers.py` 的 R4 显式规则(R1 轮已加);`verify_ledger.py` 实测:

```
OK baseline=863e31318 files=8530 total_lines=2608452
  L1: files=412  lines=382,770
  L2: files=2282 lines=811,076
  L3: files=1895 lines=602,085
  L4: files=560  lines=55,902
  LT: files=3381 lines=756,619
  SUM == repo total: 2,608,452   ✓ (文件集一致 + 行数复算一致 + 分层加总 = 全仓总行数)
```

本轮 status 更新:**R4-deep-read 35 文件 / 24,418 行 + R4-structure 4 文件 / 7,755 行**,R4 覆盖
**39 文件 / 32,173 行**。R4-structure 四文件均据实标注(结构级而非逐行):`environments/local.py`(真
subprocess 后端概述)、`browser_tool.py`(5098 行主工具面,子代理深挖 supervisor/CDP/对话桥,主面结构级)、
`desktop_ui.py`(与本簇弱相关的桌面事件桥)、`agent/shell_hooks.py`(pre/post shell 钩子扩展点概述)。

累计已学:R2(118)+ R3(35)+ R4(39)= 192 文件,R1-inventoried 降至 8338。

**R4 范围说明**:显式覆盖环境抽象基类 base;本地/Docker/SSH/Singularity 四种真进程后端 + Modal/
Daytona/Vercel/代管 Modal 四种 SDK/网关后端;file_sync 事务同步;terminal_tool shell 语义;
process_registry / daemon_pool 后台进程;patch_parser(V4A)+ file_state(跨代理新鲜度);runtime_cwd /
shell_hooks;浏览器自动化栈(supervisor/CDP/camofox/dialog);computer_use 全簇(cua_backend/tool/
backend/browser_route/schema/vision_routing/permissions/doctor)+ interrupt / close_terminal / read_terminal。
`R3-R4`(64)与 `R3-R7`(115)等多轮桶里非本簇文件不动,留后续轮次。

## 2. 底稿与成品章清单

**底稿 `notes/`(6 篇,凡断言紧跟 `路径:行号 @ 863e313` + 代码原文)**:
- `r4-01-environment-abstraction.md` —— spawn-per-call 统一模型、会话快照原子写/mktemp 唯一名/函数按名过滤、
  `_wrap_command` 六段脚本、`ProcessHandle` 协议 + `_ThreadedProcessHandle` 线程适配、`_wait_for_process`
  select 非阻塞 drain / 增量 UTF-8 / 有界捕获 / 中断兜底、stdin pipe/heredoc 双模式。
- `r4-02-docker-local-terminal-process.md` —— Docker persist no-op(#20561)/ 标签复用 / 孤儿回收三约束、
  local + runtime_cwd 概述、terminal shell 语义(`A && B &` 重写 / `sudo -S`)、process_registry
  检查点崩溃恢复 / PID 复用防误杀 / watch strike 熔断、daemon_pool、shell_hooks 概述。
- `r4-20-remote-backends-serverless.md`(子代理) —— 两种执行范式、五后端持久化四机制、FileSyncManager
  事务同步 + 四层护栏、iron-proxy 仅 Docker 负面发现、定案 a/b。
- `r4-30-browser-automation.md`(子代理) —— browser supervisor / CDP / camofox / 对话桥(注入 XHR+Fetch
  拦截)、`recent_dialogs` 环形缓冲、`DIALOG_BRIDGE_HOST` 隔离标识、FileSyncManager 复用。
- `r4-40-computer-use.md`(子代理) —— cua-driver MCP over stdio、三平台 frozenset 硬编码、SOM/vision/AX
  三模式、`ok` 非语义裁决的 verify→escalate 阶梯、vision_routing(#24015)、每 spawn 剥密钥。
- `r4-90-doc-conflict-rulings.md` + `r4-95-tests.md`(定案 + 测试记录)。

其中 3 篇由子代理并行深挖(远端后端 / 浏览器 / computer_use),主线逐条抽查关键行号(permissions.py:34-35、
cua_backend.py:1-11、schema.py:14-16、vision_routing.py:1-20、base.py 快照段、docker.py persist no-op 等
均逐字命中);r4-01/r4-02/r4-50 与全部定案由主线亲自精读复核。

**成品章 `chapters/r4-execution-environments.md`**(新可读性标准,GitHub 可渲染 Mermaid):三个同心圈——
统一假象(spawn-per-call + 快照)、后端真实差异(两范式 / 四持久化 / 事务同步)、两个 GUI 执行面(浏览器 /
computer_use);场景开场、术语锚定、事故讲成故事、地图与代码出入融进叙述。

## 3. 行为规格测试(664 用例全过)

官方 `scripts/run_tests.sh`(密封环境、per-file 子进程隔离、8 workers)本会话三批全绿:

- **核心后端 + 终端 + 进程 + patch + file(23 文件 / 343)**:base/docker/ssh/singularity/modal(含 snapshot
  隔离 + legacy 迁移)/managed_modal/daytona(stop-resume)/vercel(快照+自愈)环境、file_sync/file_sync_back/
  file_state、process_registry、patch_parser、terminal(compound_background/exit/cwd_echo/truncation_spill)、
  runtime_cwd。
- **浏览器(10 文件 / 122)**:supervisor/healthcheck/cdp_tool/cdp_override/camofox/hardening/secret_exfil/
  ssrf_local/orphan_reaper/type_redaction。
- **computer_use(16 文件 / 199)**:computer_use(73)/vision_routing(18)/delivery_ladder(17)/approval_isolation/
  capture_routing/cua_0_9(37)/cua_0_10_permissions/backend_linux/null_pid_windows + cua spawn 密钥洗净/
  no_overlay/atexit_teardown/perf_knobs/telemetry/cli_fallback/wsl_manifest。

**合计 49 文件 / 664 passed / 0 failed。** hermes-agent 保持基线、零改动。为让远端后端测试从 skip 转真跑,
补装 `daytona==0.155.0` / `modal==1.3.4` / `openssh-client`(沿用 R2/R3 记录的"测试宿主缺可选依赖、非代码
缺陷"模式,详见 `notes/r4-95`)。真跑模型仍需 provider 凭据,本簇纯执行环境测试不依赖它,未配置。

## 4. 文档-代码冲突定案(R4 范围,8 条)

逐条定案(证据见 `notes/r4-90`),无一条被推翻为"文档完全正确":

- **★ 证伪 `tools.md:88` "容器关机即删"**(R1 挂起头号条目):默认 `persist_across_processes=True`、清理对
  容器 no-op、容器跨进程存活(#20561);且 :88 与下一句 :90 的 `container_persistent` 开关**同页自相矛盾**。
  以代码为准:默认跨进程持久、关机不删。
- **修正 README:29 serverless 持久化**:七后端数字**证实**;但"空闲休眠"对直连 Modal / Daytona 实为"会话
  结束即休眠"(清理触发,非后台 idle 探测),只有代管 Modal 有真 `idleTimeoutMs`;且 **Vercel 同样提供
  快照持久化,README 漏列**。
- **证实 `tools.md:148` Vercel 快照语义**(比 README 精确)。
- **证伪 browser `browser_state` 命名**:权威字段是 `recent_dialogs`,`browser_state` 是文档两处残留旧名
  (文档内部亦不一致)。
- **修正 computer_use 视觉路由(#24015)为窄口径缺口**:通用视觉回退有文档(`vision_analyze`/`browser_vision`),
  独 computer_use 的 capture 路径未点明——修正子代理"整个机制未文档化"的初判。
- **证实 computer_use 三平台 + cua-driver**。
- **补白**:terminal 描述漏了"函数/别名也持久";**iron-proxy 出口管控仅 Docker 后端**,远端后端与 Singularity
  不享有(出口管控与执行后端正交,选远端不等于有管控)。

L1 完成标准自评:对簇内每个机制,能讲清问题/实现/设计理由/取舍(成品章即证),能凭底稿重实现(底稿每节
末列"重实现要点"),达标。本轮主线亲自复核了子代理的一处过判(vision_routing ▲ → 窄口径缺口),体现
"抽查不轻信"。

## 5. 下一轮建议

**下一轮做 R5:会话状态与持久化**(会话/对话的落盘与恢复、检查点、`session_search`/FTS5 全文检索、
`/new` `/reset` 语义、跨会话记忆的存储侧、历史压缩/摘要的持久化)。理由:R2 学了回合主循环的"运行时"、
R4 学了执行环境的"进程与文件持久化",R5 自然上升到"一整个会话怎么被保存、检索、恢复、跨会话延续"——
这是把前四轮的运行时/工具/执行拼成"一个能跨天记忆的 agent"的黏合层。台账中 `round=R5` 现有 17 文件,
开轮时按 R4 打法先钉死范围(可能吸纳 `R3-R7` 桶里 checkpoint/session 相关文件)再更新 status。

打法沿用 R3/R4:主线精读会话存储核心与 FTS5 检索,压缩/记忆存储侧用子代理并行深挖;产出底稿
`notes/r5-*` + 成品章 `chapters/r5-*`(新标准)+ 测试作规格 + 定案 R5 范围 ▲/◇ + 更新台账 status 为
`R5-*` 并重跑校验报数。

无阻塞事项。真跑模型仍需任一 provider 凭据(见 R1 报告 §1.5),纯代码学习与测试不依赖它;本轮
venv + `.[dev]` + daytona/modal/ssh 下测试全绿。
