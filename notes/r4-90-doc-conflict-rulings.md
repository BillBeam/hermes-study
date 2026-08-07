# R4-90 文档-代码冲突定案(R4 范围)

> 底稿。基线 `863e31318`。"文档"= README / website/docs(作者自绘地图),与代码冲突以代码为准。
> 本篇把 R4 范围内 R1 标记的 ▲/◇ 与本轮新发现逐条定案,每条附证据行号。判定用语:
> **证实**(文档对)、**证伪**(文档错)、**修正**(方向对、表述不准)、**补白**(代码有、文档无)。

## 定案 1 ★ tools.md:88 "容器关机即删"(R1 挂起的头号条目)——证伪(对默认态)

**文档**:`website/docs/user-guide/features/tools.md:88 @ 863e313`:
> The container is stopped and removed on shutdown.

**代码**:Docker 后端默认 `persist_across_processes=True`(docker.py:871),cleanup 在 persist 模式下
**对容器 no-op**(docker.py:1958-1966),容器跨 Hermes 进程存活,下次按 `(task,profile)` 标签复用;
只有孤儿回收器(exited 且 FinishedAt 早于 600s)或 `force_remove`/`persist=False` 才真删。这是
issue #20561 的契约(docker.py:1953-1957)。见 r4-02 §1。

**判定:证伪(默认态)。** ":88 关机即删" 只有在 `container_persistent=False` 时成立;默认是关机**不**删。

**加重情节——文档自相矛盾**:同一段的下一句 `tools.md:90` 就说:
> the `container_persistent` flag that controls whether `/workspace` and `/root` survive across Hermes restarts.

:88 断言"关机即删",:90 又说有个 flag 让它跨重启存活——**同一页自打脸**。真相是:该 flag(代码里的
`persist_across_processes`)默认为 True,所以默认行为是 :90 描述的"存活",而非 :88 的"删除"。以代码为准:
**默认跨进程持久,关机不删**。

## 定案 2 ◇ README:29 "serverless persistence"——数字证实、名单不全、触发时机修正

**文档**:`README.md:29 @ 863e313`:
> Seven terminal backends — local, Docker, SSH, Singularity, Modal, Daytona, and Vercel Sandbox.
> Daytona and Modal offer serverless persistence — your agent's environment hibernates when idle
> and wakes on demand …

三点定案(证据见 r4-20 §2、§5):

- **"Seven terminal backends" —— 证实**。工厂 `_create_environment` 的 `env_type` 分支恰好 7 个:
  local/docker/singularity/modal/daytona/vercel_sandbox/ssh(terminal_tool.py:1633-1760)。managed Modal
  不是第 8 个后端,是 `modal` 这一 env_type 下的传输子模式,不改变数目。
- **持久化名单不全 —— 修正**。Vercel **同样**提供 snapshot 持久化(vercel_sandbox.py:448-475),文档
  `tools.md:68` "snapshot-backed filesystem persistence" 与 `:148` 亦承认,但 README 只点名 Daytona+Modal。
  应为 **Modal + Daytona + Vercel**。
- **"hibernates when idle" 触发时机 —— 修正**。Modal direct 是 **cleanup 拍快照 + terminate**(会话结束触发,
  非后台空闲探测);Daytona `auto_stop_interval=0`(daytona.py:125)**显式关掉**平台空闲自停,靠 cleanup
  主动 `stop()`。**只有 managed Modal** 有真 `idleTimeoutMs`(managed_modal.py:189)那种"服务端 idle 到点休眠"。
  即:README 的"idle 自动休眠"在 direct/Daytona 上其实是"会话结束即休眠"。

## 定案 3 ◇ tools.md:148 Vercel 快照语义——证实(且比 README 精确)

**文档**:`tools.md:148 @ 863e313`:
> Snapshots do not preserve live processes, PID space, or the same live sandbox identity.

**代码**:完全吻合——`snapshot()` + 重建时 `source=snapshot`,换沙箱身份,活进程/PID 不保
(vercel_sandbox.py:448-511)。**证实**,此处 docs 比 README 那句笼统的"hibernate"精确得多。

## 定案 4 ◇ browser `browser_state` vs `recent_dialogs`——证伪文档命名,以 `recent_dialogs` 为准

**文档**:两处用旧名 `browser_state`:
- `website/docs/developer-guide/browser-supervisor.md:89`:"fact via `browser_state` inside `browser_snapshot`";
- `website/docs/user-guide/features/browser.md:591`:"Agent still sees the dialog in `browser_state` history"。

但**同一 developer-guide 的别处**又用新名:`browser-supervisor.md:120,139` 的 JSON 示例与字段说明是
`recent_dialogs`;`configuration.md:2110` 也写 `browser_snapshot.recent_dialogs`。

**代码**:实际字段/键是 `recent_dialogs`(browser_supervisor.py,`recent_dialogs` ring buffer;`browser_state`
在代码中不作此字段名出现)。见 r4-30。

**判定:证伪文档的 `browser_state` 命名。** 权威名是 `recent_dialogs`;`browser_state` 是两处残留旧名
(文档内部自身已不一致)。以代码为准。

## 定案 5 ▲ computer_use 截图视觉路由(vision_routing.py / #24015)——修正为"窄口径文档缺口"

**背景**:子代理底稿把 vision_routing.py 判为"未文档化机制"(▲ documentation gap)。主线复核后**修正该判定**——
不是整个机制没文档,而是**独缺 computer_use 这条路径的说明**。

**已文档化的部分**(vision routing 作为通用机制):
- `plugin-llm-access.md:409-410`:"Vision routing. When image input is supplied and the user's active text
  model is text-only, the host falls back to the configured vision model automatically."
- `fallback-providers.md:194,221-236`:`auxiliary.vision` 分层发现链,明确列 "browser screenshots" 为用途。
- `tools-reference.md:190`(`vision_analyze`):"On text-only main models, falls back to an auxiliary vision
  model that describes the image …"
- `tools-reference.md:30`(`browser_vision`):"On native-vision models the screenshot is attached directly;
  otherwise falls back to an auxiliary vision model."

**未文档化的部分**(本机制的缺口):`tools-reference.md:106` 的 `computer_use` 条目列了 "screenshots
(SOM / vision / AX)",但**从未说**这些截图在 text-only 主模型上会回退到 `auxiliary.vision`。也就是说,
`vision_analyze`/`browser_vision` 的同类回退都写了,唯独 `computer_use` 的 `capture` 路径没写。

**代码**:`vision_routing.py:1-20` docstring 明说 issue #24015 的回归正是"配了 `auxiliary.vision` 却被
**静默忽略**",截图仍走主模型、报 HTTP 404 no image input。这条 204 行的策略模块 + 9 个测试(见 r4-95)
就是修这个洞的。

**判定:修正子代理的 ▲。** 准确表述为:**vision 回退机制总体已文档化,但 `computer_use` 截图路径的
`auxiliary.vision` 路由未在其工具文档里点明**——是个窄口径缺口,与 #24015"配置被静默忽略"的回归性质吻合。
以代码为准:computer_use 的 `capture` 会经 `vision_routing` 做与 `vision_analyze` 同款的路由。

## 定案 6 ▲ computer_use 三平台 + cua-driver——证实

**文档**:`tools-reference.md:106`:"Background desktop control via cua-driver … macOS, Windows, and Linux."

**代码**:三平台以 frozenset 硬编码,三处一致(permissions.py:34-35 `_RUNTIME_PLATFORMS =
frozenset({"darwin","win32","linux"})`;tool.py:1330;cua_backend.py:2050-2053);后端唯一具体实现是
`CuaDriverBackend`,走 MCP over stdio 调 cua-driver 二进制(cua_backend.py:1-11)。**证实**。

细微补白:Linux 是最新加入的 runtime(X11 今天可用、Wayland 经 XWayland),docstring 有记
(cua_backend.py:29-33),文档未展开该 nuance,但不构成冲突。

## 定案 7 补白 terminal_tool 描述低估持久化范围

**文档**:`terminal` 工具描述(terminal_tool.py 内 TERMINAL_TOOL_DESCRIPTION)说
"Filesystem, current working directory, and exported environment variables persist between calls"。

**代码**:会话快照实际还 dump 并重放 **shell 函数与 alias**(base.py:697-699 的 `declare -F`/`declare -f`、
`alias -p`),且用 mktemp+mv 原子写。描述只列了 fs/cwd/env 三样,漏了函数/alias。

**判定:补白(非冲突)。** 代码持久化的比描述说的多;不是错,是没说全。重实现者要知道"有状态 shell"
的假象覆盖到函数/alias。

## 定案 8 补白 iron-proxy egress 强制仅 Docker 后端(安全覆盖缺口)

**代码实测**(r4-20 §4):iron-proxy 出口凭据注入只接线在 **Docker** 后端
(`_egress_proxy_args_for_docker`,docker.py:393-531);对本簇 7 个远端/其他后端文件 grep
`iron|egress|HTTPS_PROXY` **零命中**;egress 内部文档(egress-internals.md)的模块清单也只列 docker.py。

**判定:补白 + 安全提示。** 远端后端(SSH/Modal/Daytona/Vercel)与 Singularity 的出口流量**不经**
iron-proxy 强制。egress 强制与执行后端是**正交**维度,需各后端单独接线;"选了远端后端"不等于"有出口管控"。
文档未把这一覆盖边界讲清,记为学习产出。

## 小结

| # | 条目 | R1 标记 | 判定 |
|---|---|---|---|
| 1 | tools.md:88 容器关机即删 | ▲(挂起) | **证伪**(默认跨进程持久;且 :88 与 :90 自相矛盾) |
| 2 | README:29 serverless 持久化 | ◇ | 数字**证实**;名单**修正**(补 Vercel);触发时机**修正**(会话结束非 idle) |
| 3 | tools.md:148 Vercel 快照语义 | ◇ | **证实**(比 README 精确) |
| 4 | browser `browser_state` 命名 | ◇ | **证伪**命名,以 `recent_dialogs` 为准(文档内部亦不一致) |
| 5 | computer_use 截图视觉路由 #24015 | ▲ | **修正**子代理判定→窄口径文档缺口 |
| 6 | computer_use 三平台 + cua-driver | ▲ | **证实** |
| 7 | terminal 描述持久化范围 | 新发现 | **补白**(漏函数/alias) |
| 8 | iron-proxy egress 仅 Docker | 新发现 | **补白 + 安全提示** |

无一条被推翻为"文档完全正确无出入"。
