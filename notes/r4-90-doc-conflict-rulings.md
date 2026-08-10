# R4-90 文档-代码冲突定案(R4 范围)

> 底稿。基线 `863e31318`。"文档"= README / website/docs(作者自绘地图),与代码冲突以代码为准。
> 本篇把 R4 范围内 R1 标记的 ▲/◇ 与本轮新发现逐条定案,每条附证据行号。判定用语:
> **证实**(文档对)、**证伪**(文档错)、**修正**(方向对、表述不准)、**补白**(代码有、文档无)。

## 定案 1 ★ tools.md:88 "容器关机即删"(R1 挂起的头号条目)——证伪(对默认态)

**文档**:`website/docs/user-guide/features/tools.md:88 @ 863e313`:
> The container is stopped and removed on shutdown.

**代码**:Docker 后端默认 `persist_across_processes=True`(tools/environments/docker.py:871),cleanup 在 persist 模式下
**对容器 no-op**(tools/environments/docker.py:1958-1966),容器跨 Hermes 进程存活,下次按 `(task,profile)` 标签复用;
只有孤儿回收器(exited 且 FinishedAt 早于 600s)或 `force_remove`/`persist=False` 才真删。这是
issue #20561 的契约(tools/environments/docker.py:1953-1957)。见 r4-02 §1。

**判定:证伪(默认态)。** ":88 关机即删" 默认不成立;默认是关机**不**删。
要让它成立,得设 **`terminal.docker_persist_across_processes: false`**(或走 `force_remove=True`)。

> **R8-fix 改判(review-1 阻断-6 / M-4c)**:原文此处写的是 ":88 只有在 `container_persistent=False`
> 时成立",并把该 flag 等同于代码里的 `persist_across_processes`。**这个等式不成立,是两个键。**
> 原判的**主结论(默认跨进程持久、关机不删)完全正确**,错的是"在什么条件下文档才对"——
> 而这恰恰是读者会照着去操作的那一句。改判如下。

**两个键,两个属性,两件事。** 它们在 `terminal_tool.py` 里就分道扬镳:

`tools/terminal_tool.py:1628 @ 863e313`

```python
    persistent = cc.get("container_persistent", True)
```

`tools/terminal_tool.py:1649 @ 863e313`

```python
            persistent_filesystem=persistent, task_id=task_id,
```

`tools/terminal_tool.py:1658 @ 863e313`

```python
            persist_across_processes=cc.get("docker_persist_across_processes", True),
```

`tools/environments/docker.py:877 @ 863e313`

```python
        self._persistent = persistent_filesystem
```

**"关机要不要 stop + rm"这个决定只看后者**,清理路径的三态分支写得很直白:

`tools/environments/docker.py:1958 @ 863e313`

```python
        if force_remove:
```

`tools/environments/docker.py:1961 @ 863e313`

```python
        elif self._persist_across_processes:
```

——命中这一支就 `self._container_id = None; return`,容器原样留着。
而 `self._persistent` 在整个清理路径里**只**决定要不要删 bind-mount 目录,还被 `should_remove` 前置:

`tools/environments/docker.py:2011 @ 863e313`

```python
        if should_remove and not self._persistent:
```

**所以把 `container_persistent` 设成 false 的后果是:容器照样在跑,只是 `/workspace` 与 `/root`
两个 bind-mount 目录被删了——比不动更糟。** 一个想要"退出即清理"的运维者按原判去操作会正好踩中这个。

**"同一页自打脸"这个定性也要撤。** `tools.md:88` 与 `:90` 讲的是**两个不同的开关**,
`:90` 对它自己那个开关(`container_persistent` 管 `/workspace` 与 `/root`)的描述是**准确的**。
而仓库自己的文档把这个区别说得很清楚,是本条原判把它们并了:

`website/docs/user-guide/configuration.md:315 @ 863e313`

> | `TERMINAL_CONTAINER_PERSISTENT` | `container_persistent` | `true` / `false` — controls the bind-mount workspace dirs, distinct from `docker_persist_across_processes` |

"distinct from" 是文档原话。同页 `:276` 更直说 `docker_persist_across_processes: false`
才是 "Every `cleanup()` does `stop` + `rm -f`"。

**改判后的真实缺口(降格为 ◇)**:`tools.md:88` **从不提** `docker_persist_across_processes`,
而它链接过去的 `configuration.md` 把这件事写对了——**这是"该页信息不全 + 未指向正确的键",
不是"自打脸"**。以代码为准的主结论不变:**默认跨进程持久,关机不删**。

## 定案 2 ◇ README:29 "serverless persistence"——数字证实、名单不全、触发时机修正

**文档**:`README.md:29 @ 863e313`:
> Seven terminal backends — local, Docker, SSH, Singularity, Modal, Daytona, and Vercel Sandbox.
> Daytona and Modal offer serverless persistence — your agent's environment hibernates when idle
> and wakes on demand …

三点定案(证据见 r4-20 §2、§5):

- **"Seven terminal backends" —— 证实**。工厂 `_create_environment` 的 `env_type` 分支恰好 7 个:
  local/docker/singularity/modal/daytona/vercel_sandbox/ssh(tools/terminal_tool.py:1633-1760)。managed Modal
  不是第 8 个后端,是 `modal` 这一 env_type 下的传输子模式,不改变数目。
- **持久化名单不全 —— 修正**。Vercel **同样**提供 snapshot 持久化(tools/environments/vercel_sandbox.py:448-475),文档
  `tools.md:68` "snapshot-backed filesystem persistence" 与 `:148` 亦承认,但 README 只点名 Daytona+Modal。
  应为 **Modal + Daytona + Vercel**。
- **"hibernates when idle" 触发时机 —— 修正**。Modal direct 是 **cleanup 拍快照 + terminate**(会话结束触发,
  非后台空闲探测);Daytona `auto_stop_interval=0`(tools/environments/daytona.py:125)**显式关掉**平台空闲自停,靠 cleanup
  主动 `stop()`。**只有 managed Modal** 有真 `idleTimeoutMs`(tools/environments/managed_modal.py:189)那种"服务端 idle 到点休眠"。
  即:README 的"idle 自动休眠"在 direct/Daytona 上其实是"会话结束即休眠"。

## 定案 3 ◇ tools.md:148 Vercel 快照语义——证实(且比 README 精确)

**文档**:`tools.md:148 @ 863e313`:
> Snapshots do not preserve live processes, PID space, or the same live sandbox identity.

**代码**:完全吻合——`snapshot()` + 重建时 `source=snapshot`,换沙箱身份,活进程/PID 不保
(tools/environments/vercel_sandbox.py:448-511)。**证实**,此处 docs 比 README 那句笼统的"hibernate"精确得多。

## 定案 4 ◇ browser `browser_state` vs `recent_dialogs`——证伪文档命名,以 `recent_dialogs` 为准

**文档**:两处用旧名 `browser_state`:
- `website/docs/developer-guide/browser-supervisor.md:89`:"fact via `browser_state` inside `browser_snapshot`";
- `website/docs/user-guide/features/browser.md:591`:"Agent still sees the dialog in `browser_state` history"。

但**同一 developer-guide 的别处**又用新名:`browser-supervisor.md:120,139` 的 JSON 示例与字段说明是
`recent_dialogs`;`website/docs/user-guide/configuration.md:2110` 也写 `browser_snapshot.recent_dialogs`。

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

**代码**:`tools/computer_use/vision_routing.py:1-20` docstring 明说 issue #24015 的回归正是"配了 `auxiliary.vision` 却被
**静默忽略**",截图仍走主模型、报 HTTP 404 no image input。这条 204 行的策略模块 + 9 个测试(见 r4-95)
就是修这个洞的。

**判定:修正子代理的 ▲。** 准确表述为:**vision 回退机制总体已文档化,但 `computer_use` 截图路径的
`auxiliary.vision` 路由未在其工具文档里点明**——是个窄口径缺口,与 #24015"配置被静默忽略"的回归性质吻合。
以代码为准:computer_use 的 `capture` 会经 `vision_routing` 做与 `vision_analyze` 同款的路由。

## 定案 6 ▲ computer_use 三平台 + cua-driver——证实

**文档**:`tools-reference.md:106`:"Background desktop control via cua-driver … macOS, Windows, and Linux."

**代码**:三平台硬编码,三处一致——
`tools/computer_use/permissions.py:35 @ 863e313`

```python
_RUNTIME_PLATFORMS = frozenset({"darwin", "win32", "linux"})
```

`tools/computer_use/tool.py:1333 @ 863e313`

```python
    if sys.platform not in ("darwin", "win32", "linux"):
```

`tools/computer_use/cua_backend.py:2058 @ 863e313`

```python
        if sys.platform not in ("darwin", "win32", "linux"):
```

后端唯一具体实现是 `CuaDriverBackend`,走 MCP over stdio 调 cua-driver 二进制
(`tools/computer_use/cua_backend.py:1-11 @ 863e313`)。**证实**。

细微补白:Linux 是最新加入的 runtime(X11 今天可用、Wayland 经 XWayland),docstring 有记——
`tools/computer_use/cua_backend.py:13 @ 863e313`

```
Linux is the most recent runtime (X11 today, Wayland via XWayland; pure-
```

文档未展开该 nuance,但不构成冲突。

> **R8-fix 修正锚点(review-1 建议-15 / M-16a)**:本条原来三个锚点都是**裸文件名 + 漂移行号**
> ——`tool.py:1330` 落在 docstring 里(真实判定在 `:1333`)、`cua_backend.py:2050-2053` 是
> **另一个方法**的 `finally:` 拆卸段(真实判定在 `:2058`)、`cua_backend.py:29-33` 是讲
> macOS 私有 SPI 的段落(Linux nuance 实际在 `:13-14`)。**三条实质断言全部成立**,漂的只是锚点。
> 这正是 M-16a 要治的那类失败:**一个照锚点去复核的读者会落在无关文字上,然后合理地怀疑整条定案。**

## 定案 7 补白 terminal_tool 描述低估持久化范围

**文档**:`terminal` 工具描述(terminal_tool.py 内 TERMINAL_TOOL_DESCRIPTION)说
"Filesystem, current working directory, and exported environment variables persist between calls"。

**代码**:会话快照实际还 dump 并重放 **shell 函数与 alias**(base.py:697-699 的 `declare -F`/`declare -f`、
`alias -p`),且用 mktemp+mv 原子写。描述只列了 fs/cwd/env 三样,漏了函数/alias。

**判定:补白(非冲突)。** 代码持久化的比描述说的多;不是错,是没说全。重实现者要知道"有状态 shell"
的假象覆盖到函数/alias。

## 定案 8 补白 iron-proxy egress 强制仅 Docker 后端(安全覆盖缺口)

**代码实测**(r4-20 §4):iron-proxy 出口凭据注入只接线在 **Docker** 后端
(`tools/environments/docker.py:393-531 @ 863e313` 的 `_egress_proxy_args_for_docker`);
对本簇其余后端文件**零命中**;egress 内部文档(egress-internals.md)的模块清单也只列 docker.py。

```verify
$ grep -rnE "iron[-_]proxy|IRON_|\begress\b|HTTPS_PROXY" tools/environments/*.py | grep -v docker.py ; echo "exit=$?"
exit=1                     # 零命中
```

> **R8-fix 修正(review-1 建议-16 / M-16d)**:原文写的自检命令是
> 对这些文件 grep **`iron|egress|HTTPS_PROXY`**「零命中」。**这条命令重跑不出零命中**——
> `iron` 是 `env`**`iron`**`ment` 的子串,于是每一个后端文件都命中(daytona 5、ssh 4、
> singularity 6、modal 5、managed_modal 4、vercel_sandbox 7),全部来自 "Environment" 一词。
> **结论本身仍然成立**(换成上面的词界写法复核,确为零命中),错的只是那条命令。
> 但 CLAUDE.md 的证据标准是"使读报告本身即完成验证",**一条重跑给出相反结果的命令比不写更糟**:
> 读者要么以为结论错了,要么以为自己环境不对。故立此规矩:
> **凡把 shell 命令写进证据,必须是重跑能复现该结论的那一条**;自检命令统一用 ```verify 围栏标注。

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
