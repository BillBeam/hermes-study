# r10b 片D · 状态层 —— store、hooks、sdk 与内核接驳(底稿)

> 层:**L2(结构级理解 = 读接口面,不读实现体;但接口面不许抽样)**
> 范围:`data/r10b/slices/D.txt`,**97 文件 / 19,637 行**,全部在 `/home/user/hermes-agent/` 下。
> 溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于代码块之前。
> 基线自检:`git -C /home/user/hermes-agent status --porcelain` 为空,HEAD = `863e31318553cda8ad61df681d08175364d4164b`。

---

## 0. 本片范围与逐文件点名(判据 1)

先给一句话总纲:**桌面端渲染进程的全部客户端状态住在 `apps/desktop/src/store/` 的 86 个
nanostores 模块里,与内核(Python 网关)的唯一通道是 `apps/desktop/src/hermes.ts`;
`src/sdk/` 把其中一小撮只读原子和一扇 RPC 门转手给插件;`src/hooks/` 是 7 个与状态无关的
DOM/React 原语;`src/main.tsx` 是 React 挂载点,同时用 3 个 side-effect import 把三个
store 模块拉起来。**

术语先锚一次(目标读者可能没接触过):

| 术语 | 一句话中文锚定 |
|---|---|
| **nanostores** | 一个极小的响应式状态库。`atom(x)` 建一个可读可写的值容器,`.get()` 读、`.set()` 写、`.subscribe(fn)`/`.listen(fn)` 订阅;`computed(源, fn)` 建一个从别的原子推导出来的只读值,**只有推导结果真的变了才通知订阅者**。React 侧用 `useStore($atom)` 订阅。本仓库约定:**凡是原子,变量名一律 `$` 开头**(实测 86 个模块 259 个原子,无一例外,见 §2.1 的枚举命令)。 |
| **atom / computed / map** | 上一行三种构造器。`map` 是「对象型原子,可按 key 局部更新」,本片只有 1 处用到(`hub-actions.ts`)。 |
| **JSON-RPC** | 一种「一个请求配一个 id,回一个同 id 的响应」的远程调用格式。本项目网关用它跑在 WebSocket 上;没有 id 的帧就是**服务端主动推的事件**。 |
| **runtime id / stored id / lineage root** | 同一段对话的三种身份。**runtime id** 是网关这次跑起来的进程内会话号(重启即失效,流式事件按它归属);**stored id** 是落到 `state.db` 的持久号(路由、书签用它);**lineage root** 是自动压缩(auto-compaction)反复换 id 时那条不变的根 id(置顶、着色、草稿键用它)。三者混用是本仓库反复踩的坑,`store/session.ts` 专门有三个纯函数做换算。 |
| **profile** | 一套独立的 `HERMES_HOME`(配置、技能、会话库都独立)。桌面端可以同时挂多个 profile 的后端进程,每个一条 WebSocket。 |
| **primary / secondary gateway** | 窗口自己那条主 socket 叫 primary;为「别的 profile 还有活儿在跑」而额外开的后台 socket 叫 secondary。 |
| **soft switch(软切换)** | 换连接模式(本地↔远程)时**不重载窗口**,只把「绑定网关的那批 store」清空再重连。 |

### 0.1 逐文件点名 —— 非 store 的 11 个文件

| 全路径 | 行 | 角色(一句话) |
|---|---|---|
| `apps/desktop/src/hermes.ts` | 1820 | **渲染进程对内核的唯一门面**:133 个导出函数,其中 127 个是 REST 调用(经 Electron 桥 `window.hermesDesktop.api`)、1 个是插件用的 WebSocket 门、5 个是纯计算;另导出 `HermesGateway` 类(JSON-RPC 客户端的薄配置子类)与约 150 个类型再导出。 |
| `apps/desktop/src/main.tsx` | 82 | React 入口:先做 3 个 **side-effect import**(`store/active-work`、`store/power`、`store/translucency`)与 dev 计数器,再按 `?win=` 查询参数分岔挂载四种根(overlay / quick / wake / 主窗),主窗外套 7 层 Provider。 |
| `apps/desktop/src/sdk/index.ts` | 279 | `@hermes/plugin-sdk` 的**实体**:130 个导出名。核心是 `host` 对象(6 个只读状态原子 + `notify`/`logs`/`navigate`/`onEvent`/`restartGateway`/`status`/`request` 七扇门),其余是 UI 组件、贡献点常量、i18n、react-query 的再导出。 |
| `apps/desktop/src/sdk/runtime.ts` | 54 | 运行时加载的插件怎么拿到同一份 SDK:把 SDK/React/JSX 运行时挂到 `globalThis`,再用 `Blob` + `URL.createObjectURL` 造出「re-export 全局命名空间」的 shim ESM 模块,给加载器一张 `specifier → shim URL` 映射表。**导出名从命名空间自身取,所以列表不会漂**。 |
| `apps/desktop/src/hooks/use-delayed-true.ts` | 26 | `active` 连续为真超过 `delayMs`(默认 180ms)才返回 true —— 用来给骨架屏加门,快操作不闪骨架。 |
| `apps/desktop/src/hooks/use-grab-scroll.ts` | 77 | 拖背景平移溢出容器(看板、时间线、宽表)的共享原语;屏蔽 button/input/a/[draggable] 目标与滚动条槽 16px。也被 SDK 转出给插件。 |
| `apps/desktop/src/hooks/use-image-download.ts` | 85 | 存图:优先走 Electron IPC `saveImageFromUrl`,handler 缺失时回落浏览器 `<a download>`,两条路都失败才报错 toast。 |
| `apps/desktop/src/hooks/use-media-query.ts` | 24 | `window.matchMedia` 的 React 封装,外加一个可在渲染外调用的 `matchesQuery()`(`store/layout.ts`、`store/review.ts` 就是用后者在模块初始化时读断点的)。 |
| `apps/desktop/src/hooks/use-mobile.ts` | 3 | 一行:`useIsMobile = () => useMediaQuery('(max-width: 47.9375rem)')`。 |
| `apps/desktop/src/hooks/use-resize-observer.ts` | 134 | **全应用共用一个 `ResizeObserver`**,按 handler 分组派发。注释给了实测理由:5 个会话瓦片拖分隔条时,每实例一个 observer 会产生 2,600 次回调 / 40 次 pointermove(每帧 65 次、每次只带一条 entry)、977ms 脚本时间。 |
| `apps/desktop/src/hooks/use-theme-epoch.ts` | 32 | 主题重绘(`<html>` 上 class/style/data-hermes-* 变化)的单一 `MutationObserver`,给 canvas 类消费者一个「重新 `getComputedStyle`」的计数器与命令式订阅口。 |

### 0.2 逐文件点名 —— `apps/desktop/src/store/` 的 86 个模块

按职责归组;**组内逐个列全路径**。行数与导出面见 §2.1 的全表(那张表也是逐个列全的)。

**A. 与内核接驳 / 连接与会话身份(6)**
`apps/desktop/src/store/gateway.ts`(多 profile socket 注册表:primary + 每 profile 一条 secondary,含指数退避重连、空闲剪枝、HMR 存活)、
`apps/desktop/src/store/gateway-switch.ts`(软切换时「该清哪些 store」的清单函数 + `$gatewaySwitching` 标志)、
`apps/desktop/src/store/session.ts`(**全片最核心**:连接描述符、会话列表、消息数组、composer 粘性选择、三种会话身份的换算纯函数、按 profile 命名空间化的「上次会话/上次路由」记忆)、
`apps/desktop/src/store/session-states.ts`(按 runtime id 的**多会话视图状态**,含 8 分钟静默看门狗、30 秒结算宽限、会话瓦片的持久化与布局树接驳)、
`apps/desktop/src/store/session-sync.ts`(跨窗口 `BroadcastChannel`,一个窗口改了会话列表就 ping 其他窗口重拉)、
`apps/desktop/src/store/session-pin-sync.ts`(本地置顶集合 ↔ 后端 `sessions.pinned` 双向对账,启动时整集重推顺带迁移历史置顶)。

**B. profile / 项目 / 工作区(4)**
`apps/desktop/src/store/profile.ts`(profile 列表、rail 顺序与配色、**软切换编排** `ensureGatewayProfile`、悬停预热、快捷键位切换)、
`apps/desktop/src/store/profile-share.ts`(profile 导出/导入为 tar.gz + 一个桌面专属 `desktop.json` 外观外挂)、
`apps/desktop/src/store/projects.ts`(**全片最长 1,269 行**:项目/文件夹/仓库/worktree 的 CRUD、项目树、仓库发现策略、会话搬家与墓碑)、
`apps/desktop/src/store/coding-status.ts`(按 cwd 缓存 git 状态与 worktree 列表,派生「某路径改了没」)。

**C. 布局 / 窗格 / 窗口(8)**
`apps/desktop/src/store/layout.ts`(侧栏宽度与开合、右栏页签、置顶集合、侧栏各分组的排序与折叠、分页上限)、
`apps/desktop/src/store/panes.ts`(通用窗格注册表:open/宽/高覆盖)、
`apps/desktop/src/store/pane-focus.ts`(后端 `focus_pane` 工具 → 具体窗格揭示函数的映射表)、
`apps/desktop/src/store/route-tiles.ts`(把整页路由当瓦片停靠进布局树,按 path 持久化)、
`apps/desktop/src/store/windows.ts`(`?secondary` / watch 窗口判定,开新窗口的能力探测与调用)、
`apps/desktop/src/store/thread-scroll.ts`(线程是否停在底部,镜像给线程外的 composer/状态栈/跳转按钮)、
`apps/desktop/src/store/zoom.ts`(主进程持有缩放,渲染端只镜像百分比)、
`apps/desktop/src/store/translucency.ts`(窗口半透明 0–100,渲染端持有并镜像给主进程;`main.tsx` side-effect 导入)。

**D. Composer(输入区)一族(8)**
`apps/desktop/src/store/composer.ts`(附件模型 + 每会话草稿)、
`apps/desktop/src/store/composer-queue.ts`(排队待发的 prompt,按会话键)、
`apps/desktop/src/store/composer-actions.ts`(composer 顶部微操作徽章,核心不出货、纯贡献点)、
`apps/desktop/src/store/composer-input-history.ts`(↑/↓ 翻历史:**环本身从消息实时推导**,只持久化游标与草稿快照)、
`apps/desktop/src/store/composer-popout.ts`(浮动 composer 的按 zone 位置与开关,含从旧全局键的一次性播种)、
`apps/desktop/src/store/composer-status.ts`(composer 上方状态栈:后台进程、子代理、待办、目标合成为一组 `ComposerStatusItem`)、
`apps/desktop/src/store/quick-entry.ts`(独立的迷你输入窗;该窗**没有网关连接**,文字经主进程回递给主渲染进程走同一条 `submitText`)、
`apps/desktop/src/store/find-in-page.ts`(页内查找条状态)。

**E. 回合内的阻塞式交互(4)**
`apps/desktop/src/store/prompts.ts`(approval / sudo / secret 三种**阻塞代理线程**的请求,统一按会话键,附「本会话是否在等你」的派生)、
`apps/desktop/src/store/clarify.ts`(澄清提问,同样按会话键)、
`apps/desktop/src/store/approval-mode.ts`(`approvals.mode` 的按 profile 缓存 + 修订号防乱序)、
`apps/desktop/src/store/compaction.ts`(某会话是否正在自动压缩)。

**F. 工具行与产物(8)**
`apps/desktop/src/store/tool-view.ts`(product/technical 两种工具行视图 + 每行展开态,持久化上限 240 条)、
`apps/desktop/src/store/tool-dismiss.ts`(用户本地隐藏某工具行,故意只放内存)、
`apps/desktop/src/store/tool-diffs.ts`(工具产生的 inline diff,按 tool call id)、
`apps/desktop/src/store/tool-drafting.ts`(模型正在流式生成某工具参数时的「起草中」提示)、
`apps/desktop/src/store/artifacts.ts`(把长产物提升为带版本的 artifact 注册表,右栏页签只持引用)、
`apps/desktop/src/store/preview.ts`(右栏预览页签的唯一入口 `openPreview`,文件/URL/artifact 三类目标同一条路)、
`apps/desktop/src/store/preview-edit.ts`(哪些预览有未存改动,给页签打「已修改」点)、
`apps/desktop/src/store/preview-status.ts`(会话级「可预览产物」feed,渲染成 composer 状态栈里的紧凑链接,**不自动打开、不做内联大卡片**)。

**G. 通知与提醒(6)**
`apps/desktop/src/store/notifications.ts`(应用内 toast 栈)、
`apps/desktop/src/store/native-notifications.ts`(OS 级通知,7 个 kind 独立开关,含 approval 的动作按钮回递)、
`apps/desktop/src/store/notify-baseline.ts`(连接后 4 秒静默窗:socket 打开会重放既有状态,不能当成「刚发生」去弹 OS 通知)、
`apps/desktop/src/store/agent-notices.ts`(后端 `notification.show` 的线格式解析:剥掉文本自带的严重度字形,交给 toast 的图标)、
`apps/desktop/src/store/billing-block.ts`(计费墙:单一全局槽)、
`apps/desktop/src/store/ambient.ts`(跨窗口「谁来放这声提示音」的认领,由主进程仲裁;无桥时每个窗口都放)。

**H. 语音 / 声音 / 触感(6)**
`apps/desktop/src/store/wake-word.ts`(「Hey Hermes」唤醒词:后端才是真相源,本原子是它的缓存)、
`apps/desktop/src/store/voice-playback.ts`(当前朗读的 audio 元素与状态)、
`apps/desktop/src/store/voice-prefs.ts`(朗读回复等三个开关,镜像自 config,与 Settings 同源)、
`apps/desktop/src/store/completion-sound.ts`(完成音变体 id,故意用区间校验而不是成员校验以免和 lib 形成循环依赖)、
`apps/desktop/src/store/haptics.ts`(触感静音开关)、
`apps/desktop/src/store/reactions.ts`(消息 tapback 的网关往返)。

**I. 宠物(Petdex)一族(4)**
`apps/desktop/src/store/pet.ts`(精灵图信息 + 从会话活动派生的动画状态,刻意对齐 `agent/pet/state.py` 的优先级)、
`apps/desktop/src/store/pet-gallery.ts`(图鉴:缩略图、排序、领养、导出、改名)、
`apps/desktop/src/store/pet-generate.ts`(三步生成流程:`pet.generate` 出草稿 → 孵化 → 领养)、
`apps/desktop/src/store/pet-overlay.ts`(弹出成置顶透明小窗;**该窗无网关**,主渲染进程用 IPC 推状态给它)。

**J. 设置类小原子(11)**
`apps/desktop/src/store/backdrop.ts`(转录背后的雕像底图开关)、
`apps/desktop/src/store/statusbar-prefs.ts`(状态栏整体可见性 + 逐项隐藏)、
`apps/desktop/src/store/keybinds.ts`(用户改键的原样存储 + 与贡献点注册表联动的解析)、
`apps/desktop/src/store/keep-awake.ts`(阻止休眠;主进程持有真开关)、
`apps/desktop/src/store/power.ts`(AC/电池镜像,给兜底轮询降频用;`main.tsx` side-effect 导入)、
`apps/desktop/src/store/data-url-read-max.ts`(本地文件转 data URL 的大小上限镜像)、
`apps/desktop/src/store/embed-consent.ts`(内联嵌入的第三方请求同意闸,纯客户端不进 config)、
`apps/desktop/src/store/model-presets.ts`(按模型记住 reasoning/fast 预设)、
`apps/desktop/src/store/model-visibility.ts`(模型下拉里每个 provider 显示哪些模型)、
`apps/desktop/src/store/provider-collapse.ts`(模型选择器里折叠了哪些 provider;**故意不按当前目录剪枝**)、
`apps/desktop/src/store/reactions-enabled.ts`(tapback 总开关,默认关)。

**K. 事件驱动的刷新信号(2)**
`apps/desktop/src/store/live-sync.ts`(后端 `*.changed` 广播 → 5 个 tick 原子 + `$changeEventsAvailable` 兼容闸)、
`apps/desktop/src/store/workspace-events.ts`(`tool.complete` → 「工作树变了」tick,带变更目录集合以便局部重读)。

**L. 其余单点(18)**
`apps/desktop/src/store/active-work.ts`(**唯一一个零导出模块**:computed 出「几个对话在跑」推给主进程做退出拦截;`main.tsx` side-effect 导入)、
`apps/desktop/src/store/activity.ts`(右栏任务轨:桌面动作任务,历史上限 8、完成后 5 分钟过期)、
`apps/desktop/src/store/background-delegation.ts`(纯 computed:活动会话有几个后台子代理在跑 + 最新一行活动)、
`apps/desktop/src/store/boot.ts`(启动进度阶段与错误)、
`apps/desktop/src/store/command-palette.ts`(⌘K 面板开合与嵌套页)、
`apps/desktop/src/store/cron.ts`(定时任务列表,19 行)、
`apps/desktop/src/store/file-actions.ts`(文件树右键动作与共用的重命名/删除对话框)、
`apps/desktop/src/store/goals.ts`(每会话一条「当前目标」)、
`apps/desktop/src/store/hub-actions.ts`(技能市集安装/卸载/更新的长动作轮询,1.2s 一次)、
`apps/desktop/src/store/onboarding.ts`(**922 行**:首启与凭据向导,含 OAuth 设备码轮询、API key、本地端点、推荐模型确认)、
`apps/desktop/src/store/reactions-local.ts`(本窗口刚点的 tapback,乐观显示不等后端)、
`apps/desktop/src/store/review.ts`(**597 行**:git 审阅面板 —— 变更树、diff、暂存、还原、提交信息生成、push、开 PR)、
`apps/desktop/src/store/session-color.ts`(按 lineage 根 id 的会话配色覆盖,默认继承项目色)、
`apps/desktop/src/store/session-switcher.ts`(^Tab 会话切换器 HUD)、
`apps/desktop/src/store/starmap.ts`(技能星图的按需缓存,面板打开才拉)、
`apps/desktop/src/store/subagents.ts`(子代理树与流式条目)、
`apps/desktop/src/store/system-actions.ts`(网关重启的长动作,18 次 × 1.2s 轮询)、
`apps/desktop/src/store/todos.ts`(每会话待办)、
`apps/desktop/src/store/updates.ts`(**790 行**:桌面端自更新 + 后端更新的检查/应用/进度/轮询)。

**分组是全覆盖、不重不漏的**:A6 + B4 + C8 + D8 + E4 + F8 + G6 + H6 + I4 + J11 + K2 + L19 = **86**。
这不是手数的 —— 归组表与磁盘上的文件集做过集合比对(下面这条命令重跑会打印 `missing: []` / `extra: []`):

```verify
python3 /home/user/hermes-study/data/r10b/probes/probe_d_store_groups.py /home/user/hermes-agent
```

归组只作导读;**权威点名以 §2.1 的 86 行全表为准**(那张表由脚本生成,一行一个全路径)。
---

## 1. 这一簇解决什么问题

一句话:**把「一个 Python 内核里正在发生的事」变成「一个 Electron 渲染进程里可订阅、可持久、
可跨窗口、可跨 profile 并发的客户端状态」,并且要在 socket 会断、后端会换、id 会变、
窗口会有好几个的前提下不说谎。**

拆成四个具体难题:

1. **一个渲染进程,N 条后端。** 用户可以同时有多个 profile(各自独立 `HERMES_HOME` 与
   `state.db`),而且别的 profile 的会话可能正在跑。`store/gateway.ts` 因此不是「一个 socket」
   而是一张注册表:一条 primary(窗口自己的)+ 每个「有活儿」的 profile 一条 secondary,
   全部喂进**同一个** `handleGatewayEvent`,事件上盖 `profile` 戳。
2. **同一段对话有三个 id。** 自动压缩会给对话换 stored id,进程重启会换 runtime id。
   置顶、着色、草稿、队列必须挂在**不会变**的 lineage root 上,流式增量必须挂在 runtime id 上,
   路由挂在 stored id 上。`store/session.ts` 用 5 个纯函数把这三者的换算收在一处。
3. **同一份事实有多个缓存,谁是权威要说清楚。** 「这个会话在忙吗」在渲染进程里存在三处:
   `$busy`(前台单值)、`$sessionStates[runtimeId].busy`(每 runtime)、
   `$workingSessionIds`(前者的 computed 投影)。仓库自己的规矩写在 `apps/desktop/AGENTS.md`
   的「Decide state by authority」一节 —— 后端权威、渲染端只是缓存。
4. **高频写不能拖垮渲染。** 一次回合里 `$messages` 每秒被整体替换约 30 次,
   `$sessionStates` 每条增量都要 republish。所以本片到处是**降频派生**:
   `computed` 只在派生值真变了才通知、`stableArray` 在集合成员没变时复用旧数组引用、
   `useSessionSlice` 只订阅自己那个会话的切片。

---

## 2. 接缝穷举(判据 2)

本片的对外接缝有 6 张表。每张表都给**机械枚举命令**与条数,重跑即可核对。

### 2.1 表 A —— 86 个 store 模块的 state 形状与 action 面(**全表,不抽样**)

枚举命令(输出 TSV:`路径 / 行号 / 类别 / 名字`;类别为 `state|computed|action|type|const`):

```verify
python3 /home/user/hermes-study/data/r10b/probes/probe_d_store_surface.py /home/user/hermes-agent --tsv
```

**实测条数(该命令的 stderr):`state=231  computed=28  action=504  type=126  const=179  files=86`,
合计 1,068 个导出名。**

分类口径:`state` = `export const $X = atom|map|deepMap(...)`;`computed` = `export const $X = computed(...)`;
`action` = `export [async] function f(...)`;`type` = `export type|interface`;`const` = 其余 `export const`
(常量、纯函数式选择器工厂、如 `sessionPinId`)。下表只列前三类 —— 这三类就是「状态形状 + 动作面」。
`type`/`const` 两列在 TSV 里,篇幅原因不铺进正文。

一条值得记下来的**命名不变量**(实测,不是约定俗成的印象):
**每一个 atom/map/computed 的导出名都以 `$` 开头,反过来每一个 `$` 开头的导出也都是 atom/map/computed。**
搜索面 = `apps/desktop/src/store/*.ts` 的全部 86 个非测试文件,两条互补的 grep:

```verify
cd /home/user/hermes-agent && \
  grep -h "^export const \$" apps/desktop/src/store/*.ts | grep -vcP '=\s*(atom|map|computed|deepMap)\b' ; \
  awk -F'\t' '($3=="state"||$3=="computed") && $4 !~ /^\$/' \
    <(python3 /home/user/hermes-study/data/r10b/probes/probe_d_store_surface.py /home/user/hermes-agent --tsv) | wc -l
```

两个数都是 **0**。(注意第一条 grep 会把 `.test.ts` 也扫进去 —— 这里反而是加强:测试文件里也没有反例。)

| 模块(全路径 / 行数) | state 原子 | computed 派生 | action(导出函数) |
|---|---|---|---|
| `apps/desktop/src/store/activity.ts`<br/>100 行 | `$desktopActionTasks` | — | `upsertDesktopActionTask` `buildRailTasks` |
| `apps/desktop/src/store/agent-notices.ts`<br/>206 行 | — | — | `stripGlyph` `usageFraction` `noticeAccent` `noticeToToast` `splitMeta` `showAgentNotice` `clearAgentNotice` `nativeNoticeInput` |
| `apps/desktop/src/store/ambient.ts`<br/>18 行 | — | — | `ownsAmbientCue` |
| `apps/desktop/src/store/approval-mode.ts`<br/>97 行 | `$approvalModes` | — | `approvalModeForProfile` `reconcileApprovalModeForProfile` `syncApprovalModeForProfile` `setApprovalModeForProfile` |
| `apps/desktop/src/store/artifacts.ts`<br/>227 行 | `$artifactRegistry` `$artifactVersionSelection` | — | `findArtifact` `getArtifact` `artifactsForSession` `upsertArtifact` `artifactPreviewTarget` `openArtifact` `selectArtifactVersion` `clearArtifactRegistry` |
| `apps/desktop/src/store/backdrop.ts`<br/>14 行 | `$backdrop` | — | `setBackdrop` |
| `apps/desktop/src/store/background-delegation.ts`<br/>48 行 | — | `$backgroundResume` | — |
| `apps/desktop/src/store/billing-block.ts`<br/>76 行 | `$billingBlock` `$billingSettingsRequest` | — | `setBillingBlock` `clearBillingBlock` `requestBillingSettings` `runBillingRecovery` `billingCtaLabel` |
| `apps/desktop/src/store/boot.ts`<br/>95 行 | `$desktopBoot` | — | `applyDesktopBootProgress` `setDesktopBootStep` `completeDesktopBoot` `failDesktopBoot` |
| `apps/desktop/src/store/clarify.ts`<br/>144 行 | `$clarifyRequests` | `$clarifyRequest` | `normalizeChoices` `warnDroppedChoices` `setClarifyRequest` `clearClarifyRequest` `skipClarifyRequest` |
| `apps/desktop/src/store/coding-status.ts`<br/>515 行 | `$repoStatusByCwd` `$repoWorktreesByCwd` `$repoStatusLoading` | `$repoStatus` `$repoWorktrees` `$repoChangeByPath` | `repoStatusForCwd` `isGitRepoPath` `repoWorktreesForCwd` `repoChangeKindForPath` `registerRepoStatusCwd` `refreshRepoStatus` `refreshAllRepoStatuses` `_resetCodingStatusForTests` `resolveWorktreeRepoPath` `openWorktreeDialog` |
| `apps/desktop/src/store/command-palette.ts`<br/>49 行 | `$commandPaletteOpen` `$commandPalettePage` | — | `openCommandPalette` `openCommandPalettePage` `closeCommandPalette` `setCommandPaletteOpen` `toggleCommandPalette` |
| `apps/desktop/src/store/compaction.ts`<br/>37 行 | `$compactingSessions` | — | `sessionCompacting` `setSessionCompacting` |
| `apps/desktop/src/store/completion-sound.ts`<br/>32 行 | `$completionSoundVariantId` | — | `resolveCompletionSoundVariantId` `setCompletionSoundVariantId` |
| `apps/desktop/src/store/composer-actions.ts`<br/>69 行 | `$composerActionsBySession` | — | `setComposerActions` |
| `apps/desktop/src/store/composer-input-history.ts`<br/>164 行 | `$perSessionBrowse(re-export)` | — | `deriveUserHistory` `browseBackward` `browseForward` `resetBrowseState` `isBrowsingHistory` |
| `apps/desktop/src/store/composer-popout.ts`<br/>255 行 | `$composerPopoutZones` | — | `readPopoutBounds` `clampPopoutPosition` `setComposerPoppedOut` `setComposerPopoutPosition` `pruneComposerPopoutZones` |
| `apps/desktop/src/store/composer-queue.ts`<br/>358 行 | `$queuedPromptsBySession` `$parkedQueueSessions` | — | — |
| `apps/desktop/src/store/composer-status.ts`<br/>447 行 | `$backgroundStatusBySession` | `$backgroundRunningSessionIds` `$statusItemsBySession` | `groupStatusItems` `reconcileBackgroundProcesses` `refreshBackgroundProcesses` `dismissBackgroundProcess` `stopBackgroundProcess` `resetSessionBackground` |
| `apps/desktop/src/store/composer.ts`<br/>386 行 | `$composerDraft` `$composerAttachments` `$composerTerminalSelections` `$voiceConversationStartRequest` | — | `createComposerAttachmentScope` `stashSessionDraft` `takeSessionDraft` `migrateSessionDraft` `setComposerDraft` `appendComposerDraft` `appendComposerInline` `clearComposerDraft` `setComposerTerminalSelection` `reconcileComposerTerminalSelections` `terminalContextBlocksFromDraft` `clearComposerTerminalSelections` |
| `apps/desktop/src/store/cron.ts`<br/>19 行 | `$cronJobs` `$cronFocusJobId` | — | — |
| `apps/desktop/src/store/data-url-read-max.ts`<br/>76 行 | `$dataUrlReadMaxMb` | — | `clampDataUrlReadMaxMb` `refreshDataUrlReadMaxMb` `setDataUrlReadMaxMb` |
| `apps/desktop/src/store/embed-consent.ts`<br/>37 行 | `$embedMode` `$embedAllowed` | — | `allowProvider` `setEmbedMode` `clearEmbedAllowed` |
| `apps/desktop/src/store/file-actions.ts`<br/>89 行 | `$fileActionDialog` `$renamingPath` | — | `requestFileDelete` `closeFileActionDialog` `beginInlineRename` `cancelInlineRename` `revealFile` `copyFilePath` `toRelativePath` `executeFileRename` `executeFileDelete` |
| `apps/desktop/src/store/find-in-page.ts`<br/>130 行 | `$findInPage` | — | `openFindBar` `closeFindBar` `setFindQuery` `findNext` `findPrevious` `updateFindResults` `initFindInPageListener` `findInPageListenerCount` `resetFindInPageListenerForTest` |
| `apps/desktop/src/store/gateway-switch.ts`<br/>74 行 | `$gatewaySwitching` | — | `wipeSessionListsForGatewaySwitch` |
| `apps/desktop/src/store/gateway.ts`<br/>385 行 | — | — | `configureGatewayRegistry` `emitLocalGatewayEvent` `setPrimaryGateway` `isActivePrimary` `activeGateway` `reportPrimaryGatewayState` `openGatewayForProfile` `ensureGatewayForProfile` `ensureActiveGatewayOpen` `reconnectSecondaryGateways` `touchSecondaryGateways` `pruneSecondaryGateways` `closeSecondaryGateways` |
| `apps/desktop/src/store/goals.ts`<br/>177 行 | `$goalsBySession` | — | `setSessionGoal` `clearSessionGoal` `applyGoalStatusText` `refreshSessionGoal` |
| `apps/desktop/src/store/haptics.ts`<br/>17 行 | `$hapticsMuted` | — | `setHapticsMuted` `toggleHapticsMuted` |
| `apps/desktop/src/store/hub-actions.ts`<br/>146 行 | `$hubActions` `$hubInstalledOverride` `$hubActiveLog` | — | `installHubSkill` `uninstallHubSkill` `updateHubSkills` `closeHubLog` |
| `apps/desktop/src/store/keep-awake.ts`<br/>29 行 | `$keepAwake` | — | `setKeepAwake` |
| `apps/desktop/src/store/keybinds.ts`<br/>143 行 | `$bindings` `$capture` | `$comboIndex` | `bindingsFor` `setBinding` `resetBinding` `resetAllBindings` `conflictsFor` `beginCapture` `endCapture` |
| `apps/desktop/src/store/layout.ts`<br/>439 行 | `$rightRailActiveTabId` `$pinnedSessionIds` `$sidebarSessionOrderIds` `$sidebarSessionOrderManual` `$sidebarWorkspaceOrderIds` `$sidebarWorkspaceParentOrderIds` `$sidebarProjectOrderIds` `$sidebarWorkspaceNodeOpen` `$dismissedAutoProjectIds` `$dismissedWorktreeIds` `$sidebarPinsOpen` `$sidebarRecentsOpen` `$sidebarCronOpen` `$sidebarMessagingOpenIds` `$sidebarAgentsGrouped` `$panesFlipped` `$isSidebarResizing` `$sessionsLimit` `$revealInTreeRequest` | `$sidebarOpen` `$fileBrowserOpen` `$sidebarWidth` | `workspaceNodeOpen` `setWorkspaceNodeOpen` `toggleWorkspaceNodeCollapsed` `dismissAutoProject` `filterVisibleProjects` `dismissWorktree` `restoreWorktree` `setSidebarWidth` `setSidebarOpen` `toggleSidebarOpen` `toggleFileBrowserOpen` `setFileBrowserOpen` `revealFileInTree` `requestSessionSearchFocus` `togglePanesFlipped` `selectRightRailTab` `setSidebarPinsOpen` `setSidebarRecentsOpen` `setSidebarCronOpen` `toggleSidebarMessagingOpen` `setSidebarAgentsGrouped` `setSidebarSessionOrderIds` `setSidebarSessionOrderManual` `setSidebarWorkspaceOrderIds` `setSidebarWorkspaceParentOrderIds` `setSidebarProjectOrderIds` `setSidebarResizing` `pinSession` `unpinSession` `setPinnedSessionOrder` `bumpSessionsLimit` `resetSessionsLimit` |
| `apps/desktop/src/store/live-sync.ts`<br/>65 行 | `$changeEventsAvailable` `$cronChangeTick` `$sessionsChangeTick` `$platformsChangeTick` `$pairingChangeTick` `$petChange` | — | `setChangeEventsAvailable` `notifyPetChanged` `notifyCronChanged` `notifySessionsChanged` `notifyPlatformsChanged` `notifyPairingChanged` `resetLiveSync` |
| `apps/desktop/src/store/model-presets.ts`<br/>98 行 | `$modelPresets` | — | `getModelPreset` `setModelPreset` `applyModelPreset` |
| `apps/desktop/src/store/model-visibility.ts`<br/>262 行 | `$visibleModels` `$modelVisibilityOpen` | — | `collapseModelFamilies` `setVisibleModels` `setModelVisibilityOpen` `defaultVisibleKeys` `resolveVisibleKeys` `effectiveVisibleKeys` `toggleModelVisibility` `setProviderVisibility` |
| `apps/desktop/src/store/native-notifications.ts`<br/>257 行 | `$nativeNotifyPrefs` | — | `setNativeNotifyEnabled` `setNativeNotifyKind` `dispatchNativeNotification` `dispatchPluginNativeNotification` `respondToApprovalAction` `sendTestNativeNotification` |
| `apps/desktop/src/store/notifications.ts`<br/>221 行 | `$notifications` | — | `isDiskFullErrorMessage` `notify` `notifyError` `dismissNotification` `clearNotifications` |
| `apps/desktop/src/store/notify-baseline.ts`<br/>30 行 | — | — | `markNativeNotifyBaseline` `withinNativeNotifyBaseline` `__resetNativeNotifyBaselineForTests` |
| `apps/desktop/src/store/onboarding.ts`<br/>922 行 | `$desktopOnboarding` | — | `requestDesktopOnboarding` `requestDesktopOnboardingForCredentialWarning` `startManualOnboarding` `startManualLocalEndpoint` `startManualProviderOAuth` `peekPendingProviderOAuth` `clearPendingProviderOAuth` `closeManualOnboarding` `completeDesktopOnboarding` `dismissFirstRunOnboarding` `setOnboardingMode` `refreshOnboarding` `startProviderOAuth` `setOnboardingCode` `submitOnboardingCode` `cancelOnboardingFlow` `copyDeviceCode` `copyExternalCommand` `recheckExternalSignin` `saveOnboardingApiKey` `saveOnboardingLocalEndpoint` `setOnboardingModel` `confirmOnboardingModel` |
| `apps/desktop/src/store/pane-focus.ts`<br/>30 行 | — | — | `revealDesktopPane` |
| `apps/desktop/src/store/panes.ts`<br/>183 行 | `$paneStates` | — | `ensurePaneRegistered` `setPaneOpen` `togglePane` `setPaneWidthOverride` `setPaneHeightOverride` `clearAllPaneSizeOverrides` |
| `apps/desktop/src/store/pet-gallery.ts`<br/>537 行 | `$petGallery` `$petGalleryStatus` `$petGalleryError` `$petBusy` | — | `resetPetGallery` `loadPetThumb` `loadPetGallery` `applyAdoptedPet` `rankedGalleryPets` `adoptPet` `setPetEnabled` `nextScaleFromWheel` `setPetScale` `exportPet` `renamePet` `removePet` |
| `apps/desktop/src/store/pet-generate.ts`<br/>652 行 | `$petGenStatus` `$petGenStage` `$petGenError` `$petGenAvailable` `$petGenProviders` `$petGenProvider` `$petGenRemixConfirmed` `$petGenerateOpen` `$petGenToken` `$petGenPrompt` `$petGenDrafts` `$petGenSelected` `$petGenPreview` `$petGenInput` `$petGenRefImage` `$petGenRefName` | — | `cleanPetName` `setPetGenProvider` `markRemixConfirmed` `checkPetGenAvailable` `openPetGenerate` `closePetGenerate` `resetPetGen` `cleanupPetGenOnClose` `cancelGenerate` `discardDrafts` `cancelHatch` `generateDrafts` `hatchSelected` `adoptHatched` `discardHatched` |
| `apps/desktop/src/store/pet-overlay.ts`<br/>306 行 | `$petOverlayActive` `$petReaction` | — | `overlayWindowSize` `popOutPet` `restorePetOverlay` `popInPet` `setPetOverlaySubmitHandler` `setPetOverlayOpenAppHandler` `setPetOverlayScaleHandler` `initPetOverlayBridge` |
| `apps/desktop/src/store/pet.ts`<br/>259 行 | `$petInfo` `$petActivity` `$petUnread` `$petRoam` `$petMotion` `$petRoamDir` | `$petActive` `$petAtRest` `$petState` | `hasPetSpriteForMeta` `mergePetInfoMeta` `derivePetState` `petProfile` |
| `apps/desktop/src/store/power.ts`<br/>30 行 | `$onBattery` | — | `batteryPollInterval` |
| `apps/desktop/src/store/preview-edit.ts`<br/>30 行 | `$dirtyPreviewUrls` | — | `setPreviewDirty` |
| `apps/desktop/src/store/preview-status.ts`<br/>79 行 | `$previewStatusBySession` | — | `recordPreviewArtifact` `dismissPreviewArtifact` `clearPreviewArtifacts` |
| `apps/desktop/src/store/preview.ts`<br/>326 行 | `$previewTabs` `$previewReloadRequest` `$previewServerRestart` | `$previewTarget` `$previewTabSources` `$previewServerRestartStatus` | `decodePreviewTabs` `previewTabId` `openPreview` `closeRightRailTab` `closePreviewForSource` `closeArtifactPreviewTabs` `closeRightRail` `requestPreviewReload` `beginPreviewServerRestart` `completePreviewServerRestart` `progressPreviewServerRestart` `failPreviewServerRestart` |
| `apps/desktop/src/store/profile-share.ts`<br/>218 行 | — | — | `buildDesktopOverlay` `exportProfileBundle` `applyDesktopOverlay` `importProfileBundle` `activeProfileKey` `runExportProfileFlow` `runImportProfileFlow` |
| `apps/desktop/src/store/profile.ts`<br/>442 行 | `$activeProfile` `$profiles` `$profileOrder` `$profileColors` `$activeGatewayProfile` `$newChatProfile` `$freshSessionRequest` `$gatewaySwapTarget` `$showAllProfiles` `$profileCreateRequest` | `$profileScope` | `normalizeProfileKey` `setActiveProfile` `refreshProfiles` `setProfileOrder` `sortByProfileOrder` `setProfileColor` `refreshActiveProfile` `switchProfile` `requestFreshSession` `prewarmProfileBackend` `ensureGatewayProfile` `selectProfile` `newSessionInProfile` `setShowAllProfiles` `toggleShowAllProfiles` `switchToDefaultProfile` `switchProfileToSlot` `cycleProfile` `requestProfileCreate` `touchActiveGatewayBackend` |
| `apps/desktop/src/store/projects.ts`<br/>1269 行 | `$projects` `$activeProjectId` `$projectTree` `$projectTreeLoading` `$projectsRpcAvailable` `$removedSessionIds` `$sessionMutationsInFlight` `$reposScanning` `$projectScope` `$projectDialog` `$worktreeRefreshToken` `$startWorkSessionRequest` `$worktreeDialog` | — | `tombstoneSessions` `untombstoneSessions` `enterProject` `exitProjectScope` `goToProject` `resolveNewSessionCwd` `projectIdForCwd` `projectNameForCwd` `followActiveSessionCwd` `refreshProjects` `refreshProjectTree` `fetchProjectSessions` `moveSessionToProject` `repoDiscoveryPolicyFromConfig` `repoDiscoveryPolicySignature` `scanAndRecordRepos` `generateProjectIdea` `createProject` `renameProject` `updateProject` `setProjectAppearance` `addProjectFolder` `deleteProject` `setActiveProject` `openProjectCreate` `openProjectRename` `openProjectAddFolder` `closeProjectDialog` `refreshWorktrees` `startWorkInRepo` `listRepoBranches` `listBaseBranches` `switchBranchInRepo` `closeWorktreeDialog` `requestStartWorkSession` `removeWorktreePath` `revealPath` `copyPath` `pickProjectFolder` `openFolderAsProject` |
| `apps/desktop/src/store/prompts.ts`<br/>176 行 | — | `$activeSessionAwaitingInput` | `registerApprovalInlineAnchor` `sessionAwaitingInput` `clearAllPrompts` |
| `apps/desktop/src/store/provider-collapse.ts`<br/>28 行 | `$collapsedProviders` | — | `toggleCollapsedProvider` |
| `apps/desktop/src/store/quick-entry.ts`<br/>310 行 | `$quickEntry` | — | `canUseQuickEntry` `loadQuickEntrySettings` `saveQuickEntrySettings` `quickComposerReducer` `setQuickEntrySubmitHandler` `initQuickEntryBridge` |
| `apps/desktop/src/store/reactions-enabled.ts`<br/>40 行 | `$reactionsEnabled` | — | `setReactionsEnabled` |
| `apps/desktop/src/store/reactions-local.ts`<br/>67 行 | `$localReactions` `$agentReactions` | — | `recordAgentReaction` `mergeReactions` `setLocalReaction` |
| `apps/desktop/src/store/reactions.ts`<br/>90 行 | — | — | `applyReaction` `toggleMessageReaction` |
| `apps/desktop/src/store/review.ts`<br/>597 行 | `$reviewOpen` `$reviewCommitDefault` `$reviewTreeMode` `$reviewFiles` `$reviewLoading` `$reviewIsRepo` `$reviewSelectedPath` `$reviewDiff` `$reviewDiffLoading` `$reviewShipInfo` `$reviewShipBusy` `$reviewCommitMsgBusy` `$reviewScopeCwd` `$reviewRevertTarget` | `$reviewMaxChurn` | `toggleReviewTreeMode` `refreshReview` `selectReviewFile` `clearReviewSelection` `refreshShipInfo` `openReview` `closeReview` `toggleReview` `revealReview` `openReviewForPath` `stageReviewFile` `unstageReviewFile` `revertReviewFile` `requestRevert` `cancelRevert` `confirmRevert` `commitChanges` `cancelCommitMessage` `generateCommitMessage` `pushChanges` `createOrOpenPr` |
| `apps/desktop/src/store/route-tiles.ts`<br/>50 行 | `$routeTiles` | — | `openRouteTile` `closeRouteTile` |
| `apps/desktop/src/store/session-color.ts`<br/>80 行 | `$sessionColorOverrides` | `$sessionColorById` | `setSessionColorOverride` `sessionColorFor` |
| `apps/desktop/src/store/session-pin-sync.ts`<br/>162 行 | — | — | `watchSessionPins` |
| `apps/desktop/src/store/session-states.ts`<br/>811 行 | `$sessionStates` `$stalledSessionIds` `$sessionTiles` | `$workingSessionIds` `$attentionSessionIds` `$focusedStoredSessionId` `$focusedRuntimeId` `$focusedSessionState` | `setSessionStalled` `getRecentlySettledSessionIds` `publishSessionState` `dropSessionState` `clearAllSessionStates` `patchSessionTile` `resetTileRuntimeBindings` `setSessionTileDelegate` `sessionTileDelegate` `orderTilesByTree` `openSessionTile` `nextSessionTileForWorkspace` `focusOpenSession` `focusedSessionNeedsRoute` `blankDraftTile` `reuseBlankDraftTile` `closeSessionTile` `discardSessionTile` `reopenLastClosedTile` `markSelectionRestore` |
| `apps/desktop/src/store/session-switcher.ts`<br/>127 行 | `$switcherOpen` `$switcherSessions` `$switcherIndex` | — | `onSwitcherTabDown` `onSwitcherTabUp` `openOrAdvanceSwitcher` `closeSwitcher` `commitOnCtrlUp` |
| `apps/desktop/src/store/session-sync.ts`<br/>25 行 | — | — | `broadcastSessionsChanged` `onSessionsChanged` |
| `apps/desktop/src/store/session.ts`<br/>663 行 | `$connection` `$gatewayState` `$sessions` `$cronSessions` `$messagingSessions` `$messagingPlatformTotals` `$messagingTruncated` `$sessionProfilesTruncated` `$sessionsLoading` `$activeSessionId` `$selectedStoredSessionId` `$activeSessionStoredIdRotation` `$messages` `$freshDraftReady` `$busy` `$awaitingResponse` `$resumeFailedSessionId` `$resumeExhaustedSessionId` `$currentModel` `$currentProvider` `$currentReasoningEffort` `$currentServiceTier` `$currentFastMode` `$yoloActive` `$currentCwd` `$newChatWorkspaceTarget` `$newChatWorkspaceTargetGeneration` `$currentBranch` `$currentUsage` `$sessionStartedAt` `$turnStartedAt` `$introPersonality` `$currentPersonality` `$availablePersonalities` `$introSeed` `$contextSuggestions` `$modelPickerOpen` `$sessionPickerOpen` `$unreadFinishedSessionIds` `$currentModelSource` `$defaultReasoningEffort` | `$messagesEmpty` `$lastVisibleMessageIsUser` | `_resetLegacyDiscardForTests` `getRememberedSessionId` `setRememberedSessionId` `sessionBelongsToProfile` `rememberedSessionProfile` `getRememberedRoute` `setRememberedRoute` `syncConfiguredDefaultProjectDir` `ensureDefaultWorkspaceCwd` `applyConfiguredDefaultProjectDir` `idsShareLineage` `shouldMigrateComposerScope` `resolveComposerSessionKey` `mergeSessionPage` `touchSessionActivity` |
| `apps/desktop/src/store/starmap.ts`<br/>65 行 | `$starmapGraph` `$starmapLoading` `$starmapError` | — | `loadStarmapGraph` `evictStarmapNode` `resetStarmapGraph` |
| `apps/desktop/src/store/statusbar-prefs.ts`<br/>54 行 | `$statusbarVisible` `$statusbarHiddenIds` | — | `toggleStatusbarVisible` `setStatusbarItemVisible` |
| `apps/desktop/src/store/subagents.ts`<br/>296 行 | `$subagentsBySession` | — | `clearSessionSubagents` `pruneFinishedSessionSubagents` `pruneDelegateFallbackSubagents` `upsertSubagent` `buildSubagentTree` |
| `apps/desktop/src/store/system-actions.ts`<br/>48 行 | `$gatewayRestarting` | — | `runGatewayRestart` |
| `apps/desktop/src/store/thread-scroll.ts`<br/>64 行 | `$threadScrolledUp` `$threadJumpButtonVisible` | — | — |
| `apps/desktop/src/store/todos.ts`<br/>90 行 | `$todosBySession` | — | `todosForHydration` `setSessionTodos` `clearSessionTodos` `clearActiveSessionTodos` |
| `apps/desktop/src/store/tool-diffs.ts`<br/>38 行 | — | — | `recordToolDiff` `getToolDiff` |
| `apps/desktop/src/store/tool-dismiss.ts`<br/>45 行 | `$dismissedToolRows` | — | `dismissToolRow` `clearDismissedToolRows` |
| `apps/desktop/src/store/tool-drafting.ts`<br/>45 行 | `$draftingToolSessions` | — | `sessionDraftingTool` `setSessionDraftingTool` |
| `apps/desktop/src/store/tool-view.ts`<br/>110 行 | `$toolViewMode` `$toolDisclosureStates` | — | `setToolViewMode` `setToolDisclosureOpen` |
| `apps/desktop/src/store/translucency.ts`<br/>38 行 | `$translucency` | — | `setTranslucency` |
| `apps/desktop/src/store/updates.ts`<br/>790 行 | `$desktopVersion` `$updateApply` `$updateChecking` `$updateOverlayOpen` `$updateStatus` `$backendUpdateStatus` `$backendUpdateApply` `$backendUpdateChecking` `$updateOverlayTarget` | — | `reportBackendContract` `reportInstallMethodWarning` `maybeNotifyUpdateAvailable` `openUpdatesWindow` `startActiveUpdate` `requestActiveUpdate` `refreshDesktopVersion` `checkBackendUpdates` `checkUpdates` `applyUpdates` `applyBackendUpdate` `startUpdatePoller` `stopUpdatePoller` |
| `apps/desktop/src/store/voice-playback.ts`<br/>24 行 | `$voicePlayback` | — | `setVoicePlaybackState` |
| `apps/desktop/src/store/voice-prefs.ts`<br/>74 行 | `$autoSpeakReplies` `$voiceStopPhrase` `$thinkingSoundEnabled` | — | `applyAutoSpeakFromConfig` `applyVoiceStopPhraseFromConfig` `applyThinkingSoundFromConfig` `setAutoSpeakReplies` |
| `apps/desktop/src/store/wake-word.ts`<br/>408 行 | `$wakeWord` | — | `stopClientCapture` `applyWakeStatus` `applyWakeStartResult` `applyWakeStopResult` `armWakeWord` `toggleWakeWord` `resumeWakeAfterVoice` `resetWakeWordState` |
| `apps/desktop/src/store/windows.ts`<br/>103 行 | — | — | `isSecondaryWindow` `isWatchWindow` `canOpenSessionWindow` `canOpenNewWindow` `openSessionInNewWindow` `openNewWindow` |
| `apps/desktop/src/store/workspace-events.ts`<br/>123 行 | `$workspaceChangeTick` | — | `consumeWorkspaceChange` `notifyWorkspaceChanged` `toolMayMutateFiles` `toolChangedPath` |
| `apps/desktop/src/store/zoom.ts`<br/>24 行 | `$zoomPercent` | — | `setZoomPercent` |

第 86 个模块 `apps/desktop/src/store/active-work.ts` 不在上表里,因为它**一个名字都不导出** ——
它是纯 side-effect 模块,`main.tsx` 靠 `import './store/active-work'` 把它拉起来。
它内部 computed 出 `{count, titles}` 并在**摘要真的变了**时才通过 `window.hermesDesktop.setActiveWork`
推给主进程,由 `electron/quit-guard.ts` 变成退出确认框。

### 2.2 表 B —— `apps/desktop/src/hermes.ts` 的对外方法面(**全表 133 项,不抽样**)

枚举命令(输出 `函数名 / 行号 / 类型 / 目标`):

```verify
python3 /home/user/hermes-study/data/r10b/probes/probe_d_hermes_api.py /home/user/hermes-agent --tsv
```

**实测:133 个导出函数。**脚本的粗分类是 `rest=125 / bridge=3 / pure=5`,**其中 3 条需要人工订正**
(脚本按「函数体里第一处 `path: '…'`」抓,这 3 个函数把 path 写成条件表达式,首个匹配落空):

| 函数 | 脚本判定 | 实际 | 依据(锚点 + 逐字摘录) |
|---|---|---|---|
| `getLogs` | bridge | REST `/api/logs`(有 query 时带 `?<suffix>`) | `apps/desktop/src/hermes.ts:681`:`export function getLogs(params: {` —— 真正的 path 在 `:714` |
| `getGlobalModelOptions` | bridge | REST `/api/model/options` | `apps/desktop/src/hermes.ts:1473`:`export function getGlobalModelOptions(opts?: {` —— 真正的 path 在 `:1494` |
| `pluginSocket` | bridge | **WebSocket**,不是 REST | `apps/desktop/src/hermes.ts:319`:`export function pluginSocket(pluginId: string, path: string, onMessage: (data: unknown) => void): () => void {` |

那两处条件式 path 的原文(锚点在块前):

`apps/desktop/src/hermes.ts:714 @ 863e313`

```ts
    path: suffix ? `/api/logs?${suffix}` : '/api/logs'
```

`apps/desktop/src/hermes.ts:1494 @ 863e313`

```ts
    path: params.size > 0 ? `/api/model/options?${params.toString()}` : '/api/model/options',
```

订正后的口径:**REST 127 / WebSocket 1 / 纯计算 5 = 133**;**REST 路径模板去重后 108 个**。
按一级命名空间统计(`/api/<ns>/…`):`providers` 11、`tools` 11、`cron` 10、`skills` 9、`profiles` 8、
`mcp` 7、`model` 6、`memory` 5、`sessions` 5、`ops` 4、`webhooks` 4、`audio`/`config`/`curator`/
`learning`/`messaging`/`pairing` 各 3、`env`/`hermes` 各 2、`actions`/`analytics`/`gateway`/`logs`/
`plugins`/`status` 各 1。

**这张表最重要的一条结论:`hermes.ts` 里 127/133 是 REST,而不是 JSON-RPC。**
桌面端与内核之间是**双通道**——
读写配置类的一切走 HTTP REST(经 Electron 主进程转发,主进程按 `request.profile` 挑后端进程),
流式与回合类的一切走 WebSocket JSON-RPC(`HermesGateway`)。
`hermes.ts` 只提供 RPC 的**类**,不提供 RPC 的**方法封装**:RPC 调用点散落在各 store 里
(`$gateway.get().request('pet.info', …)` 这种写法),没有集中方法表。

下表 `类型` 列为脚本原值(未订正,便于与命令输出逐行比对);`行` 是 `apps/desktop/src/hermes.ts` 的行号。

| 导出函数 | 行 | 类型 | 目标 |
|---|---|---|---|
| `audioSpeakRequestTimeoutMs` | 101 | pure | — |
| `audioTranscribeRequestTimeoutMs` | 119 | pure | — |
| `setApiRequestProfile` | 249 | pure | — |
| `getApiRequestProfile` | 262 | pure | — |
| `pluginRest` | 296 | rest | `/api/plugins/{}{}` |
| `pluginSocket` | 319 | ws | `/api/plugins/{}{}` |
| `listSessions` | 373 | rest | `/api/sessions?limit={}&offset=0&min_messages={}` |
| `listAllProfileSessions` | 406 | rest | `/api/profiles/sessions?limit={}&offset=0&min_messages={}` |
| `resetSidebarBatchCapability` | 490 | pure | — |
| `listSidebarSessions` | 541 | rest | `/api/profiles/sessions/sidebar?{}` |
| `setSessionArchived` | 591 | rest | `/api/sessions/{}` |
| `setSessionPinnedRemote` | 604 | rest | `/api/sessions/{}` |
| `searchSessions` | 613 | rest | `/api/sessions/search?q={}` |
| `getSession` | 623 | rest | `/api/sessions/{}{}` |
| `getSessionMessages` | 636 | rest | `/api/sessions/{}/messages{}` |
| `deleteSession` | 645 | rest | `/api/sessions/{}` |
| `renameSession` | 653 | rest | `/api/sessions/{}` |
| `getGlobalModelInfo` | 666 | rest | `/api/model/info` |
| `getStatus` | 674 | rest | `/api/status` |
| `getLogs` | 681 | rest | `/api/logs` |
| `getHermesConfig` | 718 | rest | `/api/config` |
| `getHermesConfigRecord` | 726 | rest | `/api/config` |
| `getHermesConfigDefaults` | 733 | rest | `/api/config/defaults` |
| `getHermesConfigSchema` | 741 | rest | `/api/config/schema` |
| `saveHermesConfig` | 748 | rest | `/api/config` |
| `getMemoryProviderConfig` | 758 | rest | `/api/memory/providers/{}/config?surface=declared` |
| `saveMemoryProviderConfig` | 765 | rest | `/api/memory/providers/{}/config?surface=declared` |
| `getEnvVars` | 774 | rest | `/api/env` |
| `setEnvVar` | 781 | rest | `/api/env` |
| `validateProviderCredential` | 790 | rest | `/api/providers/validate` |
| `getCustomEndpoints` | 803 | rest | `/api/providers/custom-endpoints` |
| `saveCustomEndpoint` | 809 | rest | `/api/providers/custom-endpoints` |
| `validateCustomEndpoint` | 817 | rest | `/api/providers/custom-endpoints/validate` |
| `activateCustomEndpoint` | 825 | rest | `/api/providers/custom-endpoints/{}/activate` |
| `deleteCustomEndpoint` | 832 | rest | `/api/providers/custom-endpoints/{}` |
| `deleteEnvVar` | 839 | rest | `/api/env` |
| `revealEnvVar` | 848 | rest | `/api/env/reveal` |
| `listOAuthProviders` | 857 | rest | `/api/providers/oauth` |
| `disconnectOAuthProvider` | 864 | rest | `/api/providers/oauth/{}` |
| `startOAuthLogin` | 872 | rest | `/api/providers/oauth/{}/start` |
| `submitOAuthCode` | 881 | rest | `/api/providers/oauth/{}/submit` |
| `pollOAuthSession` | 890 | rest | `/api/providers/oauth/{}/poll/{}` |
| `cancelOAuthSession` | 897 | rest | `/api/providers/oauth/sessions/{}` |
| `startMemoryProviderOAuth` | 907 | rest | `/api/memory/providers/{}/oauth/start` |
| `getMemoryProviderOAuthStatus` | 915 | rest | `/api/memory/providers/{}/oauth/status` |
| `getSkills` | 922 | rest | `/api/skills` |
| `getStarmapGraph` | 929 | rest | `/api/learning/graph` |
| `getLearningNode` | 945 | rest | `/api/learning/node?id={}` |
| `deleteLearningNode` | 952 | rest | `/api/learning/node` |
| `editLearningNode` | 961 | rest | `/api/learning/node` |
| `setSkillEnabled` | 970 | rest | `/api/skills/toggle` |
| `testMcpServer` | 1002 | rest | `/api/mcp/servers/{}/test` |
| `saveMcpServers` | 1014 | rest | `/api/mcp/servers` |
| `authMcpServer` | 1024 | rest | `/api/mcp/servers/{}/auth` |
| `getMcpOAuthFlow` | 1033 | rest | `/api/mcp/oauth/flows/{}` |
| `getToolsets` | 1040 | rest | `/api/tools/toolsets` |
| `setToolsetEnabled` | 1047 | rest | `/api/tools/toolsets/{}` |
| `getToolsetConfig` | 1059 | rest | `/api/tools/toolsets/{}/config` |
| `getToolsetModels` | 1066 | rest | `/api/tools/toolsets/{}/models{}` |
| `selectToolsetModel` | 1075 | rest | `/api/tools/toolsets/{}/model` |
| `selectToolsetProvider` | 1102 | rest | `/api/tools/toolsets/{}/provider` |
| `runToolsetPostSetup` | 1115 | rest | `/api/tools/toolsets/{}/post-setup` |
| `getTerminalBackends` | 1124 | rest | `/api/tools/terminal/backends` |
| `selectTerminalBackend` | 1131 | rest | `/api/tools/terminal/backend` |
| `getComputerUseStatus` | 1140 | rest | `/api/tools/computer-use/status` |
| `grantComputerUsePermissions` | 1147 | rest | `/api/tools/computer-use/permissions/grant` |
| `getMessagingPlatforms` | 1155 | rest | `/api/messaging/platforms` |
| `updateMessagingPlatform` | 1161 | rest | `/api/messaging/platforms/{}` |
| `testMessagingPlatform` | 1172 | rest | `/api/messaging/platforms/{}/test` |
| `getPairing` | 1186 | rest | `/api/pairing` |
| `approvePairing` | 1193 | rest | `/api/pairing/approve` |
| `revokePairing` | 1204 | rest | `/api/pairing/revoke` |
| `getWebhooks` | 1218 | rest | `/api/webhooks` |
| `enableWebhooks` | 1225 | rest | `/api/webhooks/enable` |
| `createWebhook` | 1233 | rest | `/api/webhooks` |
| `deleteWebhook` | 1242 | rest | `/api/webhooks/{}` |
| `setWebhookEnabled` | 1250 | rest | `/api/webhooks/{}/enabled` |
| `getCronJobs` | 1267 | rest | `/api/cron/jobs{}` |
| `getCronJob` | 1277 | rest | `/api/cron/jobs/{}` |
| `getCronJobRuns` | 1284 | rest | `/api/cron/jobs/{}/runs?limit={}` |
| `getCronDeliveryTargets` | 1296 | rest | `/api/cron/delivery-targets` |
| `createCronJob` | 1305 | rest | `/api/cron/jobs` |
| `updateCronJob` | 1314 | rest | `/api/cron/jobs/{}` |
| `pauseCronJob` | 1323 | rest | `/api/cron/jobs/{}/pause` |
| `resumeCronJob` | 1331 | rest | `/api/cron/jobs/{}/resume` |
| `triggerCronJob` | 1339 | rest | `/api/cron/jobs/{}/trigger` |
| `deleteCronJob` | 1347 | rest | `/api/cron/jobs/{}` |
| `getAutomationBlueprints` | 1366 | rest | `/api/cron/blueprints` |
| `instantiateAutomationBlueprint` | 1374 | rest | `/api/cron/blueprints/instantiate?profile={}` |
| `getProfiles` | 1386 | rest | `/api/profiles` |
| `createProfile` | 1393 | rest | `/api/profiles` |
| `renameProfile` | 1401 | rest | `/api/profiles/{}` |
| `deleteProfile` | 1409 | rest | `/api/profiles/{}` |
| `getProfileSoul` | 1416 | rest | `/api/profiles/{}/soul` |
| `updateProfileSoul` | 1422 | rest | `/api/profiles/{}/soul` |
| `getProfileSetupCommand` | 1430 | rest | `/api/profiles/{}/setup-command` |
| `exportProfileArchive` | 1439 | rest | `/api/profiles/{}/export` |
| `importProfileArchive` | 1454 | rest | `/api/profiles/import` |
| `getUsageAnalytics` | 1466 | rest | `/api/analytics/usage?days={}` |
| `getGlobalModelOptions` | 1473 | rest | `/api/model/options` |
| `getRecommendedDefaultModel` | 1509 | rest | `/api/model/recommended-default?provider={}` |
| `setGlobalModel` | 1516 | rest | `/api/model/set` |
| `getAuxiliaryModels` | 1532 | rest | `/api/model/auxiliary` |
| `getMoaModels` | 1539 | rest | `/api/model/moa` |
| `saveMoaModels` | 1546 | rest | `/api/model/moa` |
| `setModelAssignment` | 1555 | rest | `/api/model/set` |
| `restartGateway` | 1564 | rest | `/api/gateway/restart` |
| `updateHermes` | 1572 | rest | `/api/hermes/update` |
| `checkHermesUpdate` | 1583 | rest | `/api/hermes/update/check` |
| `getActionStatus` | 1590 | rest | `/api/actions/{}/status?lines={}` |
| `transcribeAudio` | 1597 | rest | `/api/audio/transcribe` |
| `speakText` | 1613 | rest | `/api/audio/speak` |
| `getElevenLabsVoices` | 1626 | rest | `/api/audio/elevenlabs/voices` |
| `getSkillHubSources` | 1641 | rest | `/api/skills/hub/sources` |
| `searchSkillsHub` | 1649 | rest | `/api/skills/hub/search?{}` |
| `previewSkillHub` | 1659 | rest | `/api/skills/hub/preview?identifier={}` |
| `scanSkillHub` | 1667 | rest | `/api/skills/hub/scan?identifier={}` |
| `installSkillFromHub` | 1675 | rest | `/api/skills/hub/install` |
| `uninstallSkillFromHub` | 1684 | rest | `/api/skills/hub/uninstall` |
| `updateSkillsFromHub` | 1693 | rest | `/api/skills/hub/update` |
| `listMcpServers` | 1708 | rest | `/api/mcp/servers` |
| `setMcpServerEnabled` | 1715 | rest | `/api/mcp/servers/{}/enabled` |
| `getMcpCatalog` | 1724 | rest | `/api/mcp/catalog` |
| `installMcpCatalogEntry` | 1731 | rest | `/api/mcp/catalog/install` |
| `getMemoryStatus` | 1748 | rest | `/api/memory` |
| `resetMemory` | 1755 | rest | `/api/memory/reset` |
| `getCuratorStatus` | 1764 | rest | `/api/curator` |
| `setCuratorPaused` | 1771 | rest | `/api/curator/paused` |
| `runCurator` | 1780 | rest | `/api/curator/run` |
| `runDoctor` | 1796 | rest | `/api/ops/doctor` |
| `runSecurityAudit` | 1800 | rest | `/api/ops/security-audit` |
| `runBackup` | 1804 | rest | `/api/ops/backup` |
| `runDebugShare` | 1812 | rest | `/api/ops/debug-share` |

`hermes.ts` 还导出 6 个超时常量 + 2 个按内容长度算超时的纯函数,它们本身就是一份**设计说明**:

`apps/desktop/src/hermes.ts:85 @ 863e313`

```ts
export const STARTUP_REQUEST_TIMEOUT_MS = 60_000
const DEFAULT_GATEWAY_REQUEST_TIMEOUT_MS = 30_000
const SESSION_LIST_REQUEST_TIMEOUT_MS = 60_000
```

`apps/desktop/src/hermes.ts:96 @ 863e313`

```ts
export const PROMPT_SUBMIT_REQUEST_TIMEOUT_MS = 1_800_000
export const AUDIO_SPEAK_MIN_REQUEST_TIMEOUT_MS = 180_000
export const AUDIO_SPEAK_MAX_REQUEST_TIMEOUT_MS = 600_000
const AUDIO_SPEAK_TIMEOUT_MS_PER_CHAR = 35
```

读法:**超时不是一个数,是一族按「这次调用凭什么会慢」分层的数。**
启动那一波只读拉取给 60s(注释点名 `/api/profiles` 会递归遍历技能树);
`prompt.submit` 给 1,800s 并明确说「回合完成靠 stream/`message.complete` 事件通知,不靠 RPC 返回」,
数值对齐后端 `agent.gateway_timeout`;TTS/STT 按字符数线性估算再夹到 [180s, 600s]。
交互调用与 `/api/status` 存活探测留在 30s 默认,好让真死的后端仍被快速判死。

### 2.3 表 C —— 网关事件 → store 的落点表(**全表 42 个分支 / 47 个事件类型**)

枚举命令(切分 `gateway-event.ts` 的 if-else 链,再把分支体里出现的 `@/store/*` 导入符号映射回模块):

```verify
python3 /home/user/hermes-study/data/r10b/probes/probe_d_event_to_store.py /home/user/hermes-agent --tsv
```

**实测:42 个分支;分支条件里直接写出的事件类型 43 个;再并上 `SUBAGENT_EVENT_TYPES` 集合的 6 个
(其中 2 个与已列出的重合)得 **47 个事件类型**;分派器共引用 **26 个 store 模块的 68 个符号**。**

`SUBAGENT_EVENT_TYPES` 的定义(所以上表里那一行 `<SUBAGENT_EVENT_TYPES>` 展开成 6 个):

`apps/desktop/src/app/session/hooks/use-message-stream/utils.ts:90 @ 863e313`

```ts
export const SUBAGENT_EVENT_TYPES = new Set([
  'subagent.spawn_requested',
  'subagent.start',
  'subagent.thinking',
  'subagent.tool',
  'subagent.progress',
  'subagent.complete'
])
```

**注意分派器本身不在本片**(它在 `apps/desktop/src/app/session/hooks/use-message-stream/gateway-event.ts`,
1,237 行,归别的片)。之所以要把这张表做在本片,是因为**「哪些 store 是事件驱动的」这件事
只能从这里读出来**,而它直接决定了下面 §6 那条缺陷成不成立。行号列指的是该文件的分支区间。

| 事件类型 | 分支行区间 | 写入的 store 模块 |
|---|---|---|
| `gateway.ready` | 288–296 | `live-sync` |
| `skin.changed` | 297–308 | `profile` |
| `pet.changed` / `cron.changed` / `sessions.changed` / `platforms.changed` / `pairing.changed` | 309–322 | `profile` |
| `pet.changed` | 323–324 | `live-sync` |
| `cron.changed` | 325–326 | `live-sync` |
| `platforms.changed` | 327–328 | `live-sync` |
| `pairing.changed` | 329–336 | `live-sync` |
| `session.reclaimed` | 337–353 | `live-sync`, `session-states` |
| `session.info` | 354–536 | `approval-mode`, `onboarding`, `profile`, `projects`, `session`, `updates` |
| `message.start` | 537–580 | `billing-block`, `compaction`, `session`, `subagents` |
| `message.delta` | 581–584 | (无 store 写入,仅本地回调) |
| `message.interim` | 585–597 | (无 store 写入,仅本地回调) |
| `thinking.delta` | 598–602 | (无 store 写入,仅本地回调) |
| `reaction` | 603–608 | (无 store 写入,仅本地回调) |
| `reasoning.delta` | 609–616 | `pet` |
| `reasoning.available` | 617–624 | `pet` |
| `moa.reference` | 625–660 | `pet` |
| `moa.aggregating` | 661–666 | `pet` |
| `moa.progress` | 667–686 | `pet` |
| `moa.phase` | 687–698 | `pet` |
| `message.complete` | 699–772 | `clarify`, `compaction`, `pet`, `prompts`, `session`, `todos` |
| `session.title` | 773–780 | `session` |
| `tool.generating` | 781–799 | `pet`, `tool-drafting` |
| `tool.start` / `tool.progress` | 800–810 | `pet` |
| `tool.complete` | 811–849 | `composer-status`, `pet`, `tool-diffs`, `workspace-events` |
| `<SUBAGENT_EVENT_TYPES>` | 850–859 | `subagents` |
| `subagent.spawn_requested` / `subagent.start` | 860–863 | (无 store 写入,仅本地回调) |
| `clarify.request` | 864–916 | `clarify`, `native-notifications` |
| `approval.request` | 917–952 | `native-notifications`, `prompts` |
| `sudo.request` | 953–971 | `native-notifications`, `prompts` |
| `secret.request` | 972–998 | `native-notifications`, `prompts` |
| `terminal.read.request` | 999–1013 | (无 store 写入,仅本地回调) |
| `preview.read.request` | 1014–1029 | (无 store 写入,仅本地回调) |
| `agent.terminal.output` | 1030–1032 | (无 store 写入,仅本地回调) |
| `terminal.close` | 1033–1036 | (无 store 写入,仅本地回调) |
| `pane.reveal` | 1037–1044 | `pane-focus` |
| `message.reaction` | 1045–1091 | `reactions-local`, `session` |
| `status.update` | 1092–1105 | `compaction`, `composer-status`, `goals` |
| `review.summary` | 1106–1131 | (无 store 写入,仅本地回调) |
| `notification.show` | 1132–1157 | `agent-notices`, `native-notifications` |
| `notification.clear` | 1158–1162 | `agent-notices`, `notifications` |
| `error` | 1163–1237 | `clarify`, `compaction`, `native-notifications`, `notifications`, `onboarding`, `pet`, `prompts`, `session`, `todos` |

读这张表的三个观察:

- **`message.delta` / `message.interim` / `thinking.delta` / `reaction` / `terminal.*` / `preview.read.request` /
  `review.summary` 这 8 个分支一个 store 都不写** —— 它们要么直接进 hook 内部的 ref 缓存
  (增量太密,进原子会把整棵树重渲染),要么是**请求-应答型**(渲染进程读自己的 xterm/预览缓冲再回 RPC)。
  这是一条清晰的设计线:**高频与请求-应答不进全局 store。**
- **`error` 分支最宽,触达 9 个 store**(clarify、compaction、native-notifications、notifications、
  onboarding、pet、prompts、session、todos)—— 一个回合失败要同时收掉澄清、压缩标记、待办、
  阻塞提示、OS 通知,并可能触发凭据向导。
- **`session.info`(354–536,183 行)是最重的一条**,写 6 个 store:approval-mode、onboarding、
  profile、projects、session、updates。它是网关的心跳兼状态广播。

### 2.4 表 D —— `apps/desktop/src/sdk/index.ts` 的插件面(**130 个导出名**)

枚举命令:

```verify
cd /home/user/hermes-agent && python3 -c "
import re,pathlib,sys
t=pathlib.Path('apps/desktop/src/sdk/index.ts').read_text()
n=set()
for m in re.finditer(r'^export (?:type )?\{([^}]*)\}', t, re.M|re.S):
    for raw in m.group(1).split(','):
        x=raw.strip().removeprefix('type ').strip()
        if ' as ' in x: x=x.split(' as ')[-1].strip()
        if x: n.add(x)
for m in re.finditer(r'^export (?:const|interface|type|function) (\w+)', t, re.M): n.add(m.group(1))
for m in re.finditer(r'^export \* as (\w+)', t, re.M): n.add(m.group(1))
print(len(n))"
```

130 个名字按能力分四层(SDK 头部注释自称 WoW 式分层):

| 层 | 内容 | 条数 |
|---|---|---|
| `host.state.*` | **只读**状态原子:`activeSessionId` `cwd` `gateway` `model` `profile` `viewport` | 6 |
| `host.*` 动作门 | `notify` `notifyError` `logs` `navigate` `onEvent` `restartGateway` `status` `request` | 8 |
| 贡献点常量与类型 | `COMPOSER_AREAS` `PALETTE_AREA` `ROUTES_AREA` `SIDEBAR_NAV_AREA` `KEYBINDS_AREA` `THEMES_AREA` `PANES_AREA` `STATUSBAR_AREAS` `TITLEBAR_AREAS` `Contribute` `Contribution` `HermesPlugin` `PluginContext` …… | 约 30 |
| UI 与工具再导出 | Radix 系组件(Dialog/Popover/Select/Tabs/…)、`icons`、`useQuery`/`useMutation`/`queryClient`、`useI18n`/`usePluginI18n`、`atom`/`computed`/`useValue`、`cn`/`compactNumber`/`relativeTime`/`profileColor`、`useGrabScroll` | 其余 |

`host.state` 的六个原子直接引用本片的 store 原子,一个不多:

`apps/desktop/src/sdk/index.ts:58 @ 863e313`

```ts
export const host = {
  state: {
    /** Runtime id of the active chat session (null on a fresh draft). */
    activeSessionId: readonlyAtom<null | string>($activeSessionId),
    /** Active workspace cwd ('' when detached). */
    cwd: readonlyAtom<string>($currentCwd),
    /** Gateway socket state: 'idle' | 'connecting' | 'open' | …. */
    gateway: readonlyAtom<string>($gatewayState),
    /** Current main model slug. */
    model: readonlyAtom<string>($currentModel),
    /** Profile the live gateway is routed to. */
    profile: readonlyAtom<string>($activeGatewayProfile),
    /** Window geometry ({ width, height, narrow }). */
    viewport: readonlyAtom<ViewportRect>($viewport)
  },
```

值得记的取舍:`readonlyAtom` 只是**类型上**把 `WritableAtom` 窄成 `ReadableAtom`,
运行时仍是同一个对象 —— 插件拿到的是真原子,`.set()` 在 TS 层被挡,在 JS 层挡不住。
`host.request` 则是真正的权力口子,注释自己写明这是「未来做 per-plugin 能力授权的接缝」;
今天的边界靠**命名空间**:`pluginRest`/`pluginSocket` 把路径钉死在 `/api/plugins/<id>` 下并拒绝 `..`。

### 2.5 表 E —— 7 个 hook 的导出面(**11 个导出名,全列**)

| 文件 | 导出 |
|---|---|
| `apps/desktop/src/hooks/use-delayed-true.ts` | `useDelayedTrue` |
| `apps/desktop/src/hooks/use-grab-scroll.ts` | `GrabScroll`(interface)、`useGrabScroll` |
| `apps/desktop/src/hooks/use-image-download.ts` | `imageFilename`、`useImageDownload` |
| `apps/desktop/src/hooks/use-media-query.ts` | `matchesQuery`、`useMediaQuery` |
| `apps/desktop/src/hooks/use-mobile.ts` | `useIsMobile` |
| `apps/desktop/src/hooks/use-resize-observer.ts` | `useResizeObserver` |
| `apps/desktop/src/hooks/use-theme-epoch.ts` | `onThemeRepaint`、`useThemeEpoch` |

枚举命令:

```verify
cd /home/user/hermes-agent && grep -hoP '^export (?:const|function|interface|type) \w+' apps/desktop/src/hooks/*.ts | wc -l
```

**这 7 个 hook 里没有一个碰 store 或网关**,唯一的例外是 `use-image-download.ts` 会 `notify`/`notifyError`
(`apps/desktop/src/store/notifications.ts`)。**搜索面**:对 `apps/desktop/src/hooks/*.ts` 全部 7 个文件
grep `@/store|@/hermes|hermesDesktop`,命中只有 `use-image-download.ts`(`@/store/notifications` 与
`window.hermesDesktop?.saveImageFromUrl`):

```verify
cd /home/user/hermes-agent && grep -n "@/store\|@/hermes\|hermesDesktop" apps/desktop/src/hooks/*.ts
```

这条边界是有意义的:`src/hooks/` 是**通用 DOM/React 原语**,业务性 hook 全在 `src/app/*/hooks/` 下
(如 `app/gateway/hooks/use-gateway-boot.ts`、`app/session/hooks/use-message-stream/`),不在本片。

### 2.6 表 F —— 持久化面:store 用到的 localStorage 键(**64 个,全列**)

枚举命令:

```verify
cd /home/user/hermes-agent && ls apps/desktop/src/store/*.ts | grep -v '\.test\.ts$' \
  | xargs grep -hoP "'hermes\.desktop\.[^']*'" | sort -u | wc -l
```

**64 个。**注意其中 `'hermes.desktop.gatewayRegistryState'` **不是 localStorage 键** ——
它是 `Symbol.for()` 的注册名,用来把 HMR 期间的活 socket 挂在 `globalThis` 上(见 §4.1)。

按「作用域怎么声明的」分四类,这正是 `apps/desktop/AGENTS.md` 要求的那件事:

| 作用域 | 声明方式 | 例子(键名 → 定义处) |
|---|---|---|
| **全局** | 键名里没有任何范围段 | `hermes.desktop.hapticsMuted` → `apps/desktop/src/store/haptics.ts:5`:`const HAPTICS_MUTED_STORAGE_KEY = 'hermes.desktop.hapticsMuted'` |
| **按 profile** | 键名后缀 `.profile.<encodeURIComponent(名)>` | `hermes.desktop.lastSessionId` / `hermes.desktop.lastRoute`,由 `apps/desktop/src/store/session.ts:39`:`function profileNavigationKey(base: string, profile: string): string {` 生成 |
| **按连接** | 远程模式下键名带 `.remote.<baseUrl>.<profile>` | `hermes.desktop.workspace-cwd`,定义在 `apps/desktop/src/store/session.ts:14`:`const WORKSPACE_CWD_KEY = 'hermes.desktop.workspace-cwd'`,远程后缀由 `:156` 的 `workspaceCwdKey` 拼出 |
| **值内分片** | 键是全局的,但值是 `Record<profile, …>` | `hermes.desktop.sessionTiles.v2`,见 `apps/desktop/src/store/session-states.ts:346`:`function loadTilesByProfile(): Record<string, StoredTile[]> {` |

还有一类**显式声明为「故意全局」**的:composer 的模型/推理档/fast 五个键
(`hermes.desktop.composer.*`),`store/session.ts` 的注释直接写明这是刻意的 ——
新对话跟随你上次的选择,而不是弹回 profile 默认值;profile 切换时另有强制重播种的路径。

三个键带 `.v1`/`.v2` 版本段,并且各自有一次性迁移逻辑:
`hermes.desktop.sessionTiles.v1 → .v2`(读完就把 v1 写 null 退役)、
`hermes.desktop.composerPopout.enabled|position → .zones.v1`(旧值只在第一次触碰某 zone 时播种)。

---

## 3. 端到端链(判据 3):一条 `session.info` 从 socket 到重渲染

场景:用户在 profile `work` 里开着一个长回合,自己却切到 profile `default` 看别的。
`work` 的后端每秒推一条 `session.info` 心跳。**它怎么变成侧栏那颗转动的状态点?**
逐跳带锚点,共 9 跳。

**跳 1 —— WebSocket 收帧,判断这是事件不是响应。**
帧解析不在 `hermes.ts` 里,而在共享包 `apps/shared/src/json-rpc-gateway.ts` 的
`private handleMessage`:带 `id` 的是某次 `request()` 的响应,不带 `id` 而 `method === 'event'` 的才是推送。

`apps/shared/src/json-rpc-gateway.ts:382 @ 863e313`

```ts
    if (frame.method === 'event' && frame.params?.type) {
      this.dispatchEvent(frame.params)
    }
```

**跳 2 —— `HermesGateway` 只是这个客户端的一层配置。**本片的 `hermes.ts` 对事件解析零贡献:

`apps/desktop/src/hermes.ts:229 @ 863e313`

```ts
export class HermesGateway extends JsonRpcGatewayClient {
  constructor() {
    super({
      closedErrorMessage: 'Hermes gateway connection closed',
      connectErrorMessage: 'Could not connect to Hermes gateway',
      createRequestId: nextId => nextId,
      notConnectedErrorMessage: 'Hermes gateway is not connected',
      requestTimeoutMs: DEFAULT_GATEWAY_REQUEST_TIMEOUT_MS
    })
  }
}
```

(派工书把这一跳描述为「`hermes.ts` 解析」——**实测不是**:`hermes.ts` 里没有任何事件解析代码,
解析在 `apps/shared/src/json-rpc-gateway.ts`,`hermes.ts` 只贡献 5 条错误文案 + 30s 默认超时。)

**跳 3 —— secondary socket 给事件盖 profile 戳,喂进全局注册表。**
`work` 不是当前 profile,所以它是一条 secondary;`createSecondary` 在建它时就挂上了转发:

`apps/desktop/src/store/gateway.ts:233 @ 863e313`

```ts
  entry.offEvent = gateway.onEvent(event => g.config?.onEvent({ ...event, profile }))
```

**跳 4 —— 注册表把事件交给渲染层唯一的分派器。**`g.config` 由 `configureGatewayRegistry` 注入,
注入点在 `apps/desktop/src/app/gateway/hooks/use-gateway-boot.ts:385`,值是
`{ onEvent: event => callbacksRef.current.handleGatewayEvent(event) }`。
于是 primary 与 N 条 secondary 的事件汇成一股。

**跳 5 —— 分派器路由到 `session.info` 分支。**
`apps/desktop/src/app/session/hooks/use-message-stream/gateway-event.ts:354`(分支到 536 行结束)。
分支内先用 `resolveGatewayEventSessionId`(`apps/desktop/src/lib/gateway-events.ts:79`:`export function resolveGatewayEventSessionId({`)定 runtime id:
显式 `session_id` 优先,没有则落到「`message.start` 钉住的那个流会话」,再没有才落到当前活动会话。

**跳 6 —— 状态发布到本片的 `$sessionStates`。**这是**从内核世界进入 store 世界的那一步**:

`apps/desktop/src/store/session-states.ts:198 @ 863e313`

```ts
export function publishSessionState(runtimeId: string, state: ClientSessionState) {
  const current = $sessionStates.get()
  const prev = current[runtimeId] ?? null

  if (prev === state) {
    return
  }

  $sessionStates.set({ ...current, [runtimeId]: state })
  handleTransition(prev, state, runtimeId)
}
```

两个设计点都写在它上面的注释里:(a) **同引用即跳过** —— 心跳每秒一条却常常毫无变化,
不跳过就每秒制造一个新 Record,把下游 computed 全部叫醒;(b) **过渡副作用自动触发**,
调用方永远不需要手动调 transition —— 看门狗上/下弦、结算宽限、未读标记、压缩 id 轮换
全在 `handleTransition` 里按 prev/next 差分算出来。

**跳 7 —— computed 投影,并用 `stableArray` 掐掉无意义通知。**

`apps/desktop/src/store/session-states.ts:257 @ 863e313`

```ts
let workingIds: readonly string[] = []
export const $workingSessionIds = computed(
  $sessionStates,
  states =>
    (workingIds = stableArray(
      workingIds,
      storedIds(states, s => s.busy)
    ))
)
```

注释给了理由:`$sessionStates` 在一次回合里每秒被 republish 几十次,但「谁在忙」这个集合
只在 busy/needsInput 的**边沿**才变。`stableArray` 在成员未变时把**旧数组引用**还回去,
`computed` 于是判定值没变、不通知 —— 否则每来一个 token,整条侧栏和每一行都要重渲染。

**跳 8 —— 谁订阅了它。**全仓订阅 `$workingSessionIds` / `$attentionSessionIds` 的
非测试消费者共 8 处(搜索面:`apps/desktop/src` 全树 `--include=*.ts --include=*.tsx`,
排除 `.test.`;命令见下),其中**渲染型** 4 处、**逻辑型** 4 处:

```verify
cd /home/user/hermes-agent && grep -rln '\$workingSessionIds\|\$attentionSessionIds' \
  apps/desktop/src --include=*.ts --include=*.tsx | grep -v '\.test\.'
```

| 消费者 | 性质 | 它因此做什么 |
|---|---|---|
| `apps/desktop/src/app/chat/session-status-dot.tsx:131`:`const isWorking = useStoreSelector($workingSessionIds, ids => ids.includes(storedSessionId))` | 渲染 | 侧栏那颗状态点转起来(**这就是本场景的可见结果**) |
| `apps/desktop/src/app/chat/sidebar/index.tsx:306`:`const workingSessionIds = useStore($workingSessionIds)` | 渲染 | 侧栏分组的合并保留集 |
| `apps/desktop/src/app/chat/sidebar/session-row.tsx:91`:`const needsInput = useStore($attentionSessionIds).includes(session.id)` | 渲染 | 行上的「需要你」徽章 |
| `apps/desktop/src/app/session-switcher.tsx:21`:`const working = useStore($workingSessionIds)` | 渲染 | ^Tab 切换器 HUD 里的忙碌标记 |
| `apps/desktop/src/store/active-work.ts:18`:`const $activeWork = computed([$workingSessionIds, $sessions], (workingIds, sessions): HermesActiveWork => {` | 逻辑 | 推给主进程做**退出拦截** |
| `apps/desktop/src/app/gateway/hooks/use-gateway-boot.ts:460`:`const offWorking = $workingSessionIds.subscribe(() => recomputeKeptGateways())` | 逻辑 | 重算「哪些 profile 的 secondary socket 还要留着」 |
| `apps/desktop/src/app/session/hooks/use-background-queue-drain.ts:49`:`const workingSessionIds = useStore($workingSessionIds)` | 逻辑 | 后台会话空闲了就把排队的 prompt 放出去 |
| `apps/desktop/src/app/contrib/hooks/use-pet-bridge.ts:66`:`return $attentionSessionIds.listen(sync)` | 逻辑 | 宠物切到「等你输入」的动画 |

**跳 9 —— 回路闭合。**注意跳 8 的第 6 行:这条 computed 反过来决定 `work` 这条 secondary socket
留不留(`pruneSecondaryGateways`)。也就是说 —— **事件养活了它自己的 socket**:
只要 `work` 还有会话在 `$workingSessionIds` 里,它的后台 socket 就不会被剪掉;
一旦回合结束、集合变空,socket 被 dispose,后端交给空闲回收。

一条链看完,本片的定位就清楚了:**store 不是「顺手放变量的地方」,它是把内核的推送
降频、去重、按身份归位之后交给 React 的那一层;它同时还是资源调度的输入。**

---

## 4. 逐机制(结构级)

### 4.1 `store/gateway.ts` —— 多 profile socket 注册表,与它的 HMR 求生术

结构:一个 `GatewayRegistryState` 容器,装 `config`(事件出口)、`primaryGateway`、`primaryProfile`、
`activeKey`、`secondaries: Map<profile, Secondary>`、`$gateway` 原子。
`Secondary` 一条 = { profile, gateway, offEvent, offState, reconnectTimer, reconnectAttempt, reconnecting, wantOpen }。

导出面 13 个函数 + 1 个原子,可以按「谁调它」分成三组:

| 组 | 函数 | 调用方 |
|---|---|---|
| 生命周期(boot 专用) | `configureGatewayRegistry` `setPrimaryGateway` `reportPrimaryGatewayState` `closeSecondaryGateways` `pruneSecondaryGateways` `reconnectSecondaryGateways` `touchSecondaryGateways` | 只有 `app/gateway/hooks/use-gateway-boot.ts` |
| 激活与取用 | `ensureGatewayForProfile` `openGatewayForProfile` `activeGateway` `ensureActiveGatewayOpen` `isActivePrimary` `$gateway` | `store/profile.ts`、`store/projects.ts`、`store/reactions.ts`、`store/reactions-enabled.ts`、`app/gateway/hooks/use-gateway-request.ts`、`app/chat/sidebar/session-actions-menu.tsx`、`sdk/index.ts` |
| 开发期 | `emitLocalGatewayEvent` | 只有 `app/contrib/dev/credits-notice-demo.ts` |

**HMR 求生术**值得单独记:这个模块被到处 import,又没有 HMR 边界接住,所以改它(或改任何扇出到它的东西)
会触发 Vite **整页重载** —— 那会杀掉所有活 socket,把正在跑的 agent 会话断掉。
做法是把全部可变单例装进一个容器,**开发期**挂在 `globalThis[Symbol.for('hermes.desktop.gatewayRegistryState')]`,
模块底部 `import.meta.hot.accept()` 自接受;**生产期** `import.meta.hot` 是 undefined,
整个 globalThis 分支被 Vite 死代码消除,退化成普通模块级单例。

`apps/desktop/src/store/gateway.ts:102 @ 863e313`

```ts
export const $gateway = g.$gateway
```

这一行的注释解释了为什么不能每次热重载都新建原子:订阅者已经连在旧原子上了,新建就等于把它们全部孤立。

**重连策略**:secondary 断开 → `scheduleReconnect` → `reconnectBackoffDelayMs(attempt)`(full jitter 指数退避)。
`wantOpen` 是「主动关闭」与「意外断开」的区分位:`disposeSecondary` 先把它置 false,
这样一次刻意的 close 不会启动退避循环。**悬停预热**(`openGatewayForProfile`)刻意**不**在失败时排重连
—— 一次 hover 是推测性的,真正的切换才拥有重试与错误 UX。

### 4.2 `store/profile.ts` —— 软切换的编排者

`ensureGatewayProfile` 是全片并发控制最讲究的一段。三层防护:

`apps/desktop/src/store/profile.ts:275 @ 863e313`

```ts
  if (normalizeProfileKey($activeGatewayProfile.get()) === target && $gateway.get()) {
    return
  }

  // Serialize concurrent activations so two rapid session switches don't race
  // the active pointer.
  if (gatewaySwitch) {
    await gatewaySwitch.catch(() => undefined)

    if (normalizeProfileKey($activeGatewayProfile.get()) === target && $gateway.get()) {
      return
    }
  }
```

(a) 已经在目标 profile 且有活网关 → 直接返回;
(b) 有切换在飞 → **等它落地再重新判断**(双重检查,避免两次快速会话切换抢活动指针);
(c) 传 null/空(「没有明确 profile」)也要先等在飞的切换落地,否则新对话可能在半开的 socket 上
`session.create` 落到错误后端。

切换完成后必须做的第三件事是 `syncConnectionToActiveProfile` —— 把 `$connection` 也换成新后端的描述符。
注释里的事故很值得复述:本地 primary + 远程 pool profile 激活时,`$connection` 仍描述 primary,
`mode` 是 local,于是图片附件走了基于路径的 `image.attach` 而不是 `image.attach_bytes`,
把一个客户端本地路径丢给远程网关,报 `image not found: C:\…`;同时 `/api/fs/*` 与 `/api/media`
打到了错误的机器(issue #46651)。这正是 `apps/desktop/AGENTS.md` 那句
「After any swap, the active socket, active profile, and connection atoms must agree」的来历。

### 4.3 `store/session.ts` —— 三种会话身份的换算中心

5 个纯函数把 §1 说的身份问题收在一处(全部可单测,`store/session.test.ts` 里就是这么测的):

| 函数 | 行 | 回答的问题 |
|---|---|---|
| `sessionPinId` | 243 | 置顶/着色该挂哪个 id → lineage root,没有就用 live id |
| `sessionMatchesStoredId` | 249 | 某个 stored id 是不是指这一行会话(live id 或 lineage root 命中即可) |
| `idsShareLineage` | 255 | 两个 id 是不是同一段对话(跨压缩) |
| `shouldMigrateComposerScope` | 275 | 草稿/队列能不能从 A 键迁到 B 键 —— **只允许同 lineage**,否则会把 A 的排队 prompt 灌进 B |
| `resolveComposerSessionKey` | 298 | composer 该用哪个 key —— 优先 lineage root,免得压缩换 id 时草稿在打字中途被清空 |

第 6 个是 `mergeSessionPage`(行 334),它的 docstring 是本片最好的一段设计文档,讲清了
**为什么服务端返回的一页不能直接替换本地列表**:
(1) 新会话的第一条用户消息在回合落库前不进 SessionDB,`min_messages=1` 会漏掉正在首答的会话,
而每个 `message.complete` 都会触发全量刷新 —— 硬替换会让并发的新对话在任意一个完成的瞬间集体消失;
(2) 侧栏只列最近一页,长期没动的置顶会话掉出这一页,硬替换会把它从内存列表里悄悄清掉,
而置顶区正是拿这个列表来解析置顶的,表现为「置顶消失,刷新才回来」。
所以 `keepIds` 同时携带**在跑集合**与**置顶集合**,并且按 lineage 去重(修 #43483:压缩换 tip 后
新旧两行都会活下来变成两个侧栏条目)。

### 4.4 `store/session-states.ts` —— 看门狗、结算宽限、瓦片

三个时间常量构成本片唯一的「时间语义」:

| 常量 | 值 | 含义 |
|---|---|---|
| `SESSION_WATCHDOG_TIMEOUT_MS`(行 71) | 8 分钟 | busy 会话连续这么久没有状态发布 → 标为 `$stalledSessionIds`。**只是展示提示,绝不改后端派生的 busy 状态** —— 注释原话是「silence is not completion」,长工具调用本来就可以安静很久。 |
| `SESSION_SETTLE_GRACE_MS`(行 104) | 30 秒 | 刚结束的会话在这段时间里仍留在侧栏合并保留集里,免得回合一完行就被挤掉。 |
| `stableArray` 的作用 | — | 见 §3 跳 7。 |

`$sessionTiles`(把别的会话并排开成布局树里的窗格)按 **gateway profile** 持久化,不是按 `$activeProfile`。
注释点名了原因:rail 上的 profile 切换是软切换,`$activeProfile` 镜像的是窗口的 primary 后端、
在软切换时**根本不动**,按它做键会让上一个 profile 的瓦片继续注册着(表现为幽灵「Session」页签)。
运行时 id 永不信任持久化值 —— 存的是 runtime-less 的瓦片,live 原子从存储 hydrate。

### 4.5 `store/prompts.ts` —— 用一个工厂造三种阻塞式提示

`keyedPromptStore<T>()` 是本片抽象得最干净的一处:一个泛型工厂,产出
`{ $all, $active, set, clear, reset }`。approval / sudo / secret 三种提示各要一份。
两个细节:

- `$active` 是 `computed([$all, $activeSessionId], (all, activeId) => all[keyFor(activeId)] ?? null)`
  —— **后台会话的提示不会劫持前台**,它就停在自己的 key 上等你切过去(侧栏「需要你」徽章负责喊)。
- `clear(sessionId, requestId)` 里那个 request-id 不匹配就 no-op 的判断,是防「过期的 resolve 抹掉更新的提示」。

approval 与 sudo/secret 的**后端契约不同**,注释写明了:approval 在后端按会话键
(一个会话同时只有一个在飞的 approval,用 `approval.respond {choice, session_id}` 回),
没有 request_id;sudo/secret 是 `_block()` 式的请求/响应,有 request_id。
渲染端因此对前者只按 sessionId 清、对后两者可以按 requestId 精确清。

### 4.6 `main.tsx` —— 三个 side-effect import 与四种根

`apps/desktop/src/main.tsx` 的前 15 行全是 side-effect import,顺序是**有语义**的:

`apps/desktop/src/main.tsx:1 @ 863e313`

```tsx
import './styles.css'
// Side-effect: reports in-flight turns to the main process for the quit guard.
import './store/active-work'
// Side-effect: mirrors the machine's AC/battery state for poll demotion.
import './store/power'
// Side-effect: applies the persisted window translucency on load.
import './store/translucency'
```

紧跟其后的 `import '@/debug/dev-only'` 必须排在 `react-dom` 之前 —— 注释说 react-dom 在模块初始化时
就把 devtools hook 抓走了,晚装 bippy 会报 `renderers=0, commits=0`。
按 `?win=` 分四种根:`overlay`(宠物浮窗)、`quick`(快速输入)、`wake`(唤醒指示)、以及主窗。
前三种都是**无网关连接**的轻窗,状态靠主进程 IPC 从主渲染进程推过去 —— 这与
`store/pet-overlay.ts` / `store/quick-entry.ts` 的注释是一致的。
主窗外层 7 个 Provider,其中 `RootTooltipProvider` 的注释给了实测数:
原本每个 `Tip` 自带 provider,约 107 个调用点,一次拖分隔条产生 **52,784 次 TooltipProvider 渲染**。
`HashRouter useTransitions={false}` 也带实测理由:react-router v7 默认把每次路由更新包进
`startTransition`,而 React 19 并发渲染器会让非紧急更新被流式 token / 网关事件 / store 更新反复打断,
路由提交被饿死,侧栏高亮和主面板卡住几秒。

---

## 5. 文档与代码的出入

文档来源限定为派工书列的六处;本片实际比对了 `apps/desktop/AGENTS.md`、`apps/desktop/README.md`、
`apps/desktop/DESIGN.md` 三处与状态层有关的段落(`website/docs/**` 与仓库根 `AGENTS.md`、`README.md`
对桌面 store 层没有具体断言,grep `nanostore|src/store|atom` 零命中于状态层主张 ——
搜索面:`grep -rn -i 'nanostore\|src/store' README.md AGENTS.md website/docs/`)。

### ▲1 —— README 说「换 profile 是软切换,不是冷启」;代码里换 profile 有两条路,其中一条就是冷启

文档(标题层级也是断言的一部分:这句在 `### Connections, projects, and switching` 之下,
`apps/desktop/README.md:131` 是该标题行):

`apps/desktop/README.md:155 @ 863e313`

> Changing profiles or connection modes is a soft workspace switch, not another
> cold boot. The shell and current management overlay remain mounted while

(被判定的那一句到 `cold boot.` 为止;同一行后半截属于下一句,单独在 ◎2 里判。)
这一句只说了一件事,所以整句可判。代码里换 profile 有两条互不相同的路:

- **软路** `selectProfile` → `ensureGatewayProfile`(`apps/desktop/src/store/profile.ts:260`),
  开/复用目标 profile 的 socket 再把活动指针挪过去,窗口不重载 —— 与文档相符;
- **硬路** `switchProfile`(`apps/desktop/src/store/profile.ts:134`),它的**自带注释就说是重载**:

`apps/desktop/src/store/profile.ts:130 @ 863e313`

```ts
// Persist the choice and relaunch the backend under the new HERMES_HOME. The
// main process reloads the window, so this normally never returns to the caller
// (the renderer is torn down). We optimistically reflect the selection first so
// the pill updates instantly if the reload is delayed.
export async function switchProfile(name: string): Promise<void> {
```

主进程侧确实 `mainWindow?.reload()`(`apps/desktop/electron/main.ts:9997`)。

**为什么记 ▲ 而不是 ◎**:同一仓库的 `apps/desktop/AGENTS.md:92` 明确列出三种切换形态,
其中第二种就是 README 否认的那一种 ——

`apps/desktop/AGENTS.md:92 @ 863e313`

> - A **runtime home change** (switching the underlying `HERMES_HOME` profile) is
>   a hard re-home: the window legitimately reloads and state resets by remount.

README 那句把三形态压成两形态,并且把被压掉的那一形态**明确否认**了。对着 README 学的人
会以为「切 profile 永远不重载窗口」,而仓库自己的架构文档说不是。

### ◇1 —— 那条硬路今天在渲染层**没有任何调用方**(即 ▲1 的另一面)

**负结论,先写搜索面**:在 `apps/desktop/` 全树(`--include=*.ts --include=*.tsx --include=*.md
--include=*.json`,排除 `node_modules`)搜 `switchProfile`,命中 4 条 ——
2 条是 `switchProfileToSlot`(不同的名字),另 2 条是 `switchProfile` 的**定义行本身**与其上的注释块。
再对 `profile.set(` 搜同一范围,唯一命中在 `switchProfile` 函数体内。

```verify
cd /home/user/hermes-agent && grep -rn "switchProfile" apps/desktop/ \
  --include=*.ts --include=*.tsx --include=*.md --include=*.json | grep -v node_modules
cd /home/user/hermes-agent && grep -rn "profile\.set(" apps/desktop/src apps/desktop/electron \
  --include=*.ts --include=*.tsx
```

也就是说:preload 暴露了 `hermesDesktop.profile.set`(`apps/desktop/electron/preload.ts:105`),
主进程实现了 `hermes:profile:set` 并在其中 reload 窗口(`apps/desktop/electron/main.ts:9990`),
渲染端有 `switchProfile` 去调它 —— **但没有任何 UI 或 hook 去调 `switchProfile`**。
rail 上的 profile 方块、⌘1–⌘N 快捷键、all-profiles 视图里的「+」,走的全是软路
(`selectProfile` / `newSessionInProfile` / `switchProfileToSlot`)。
这不是缺陷(能力仍在、给未来留门),但**文档描述的三形态里,第二形态在今天的桌面 UI 上不可达**,
这一点两份文档都没说。

### ◎1 —— DESIGN.md 说「共享原子放 `src/store`」,字面为真但显著保守

`apps/desktop/DESIGN.md:296 @ 863e313`

> - Shared/cross-component state → small **nanostores**, not prop-drilling.
>   Each feature owns its atoms; shared atoms live in `src/store`.

字面为真,所以不是 ▲。但「small」这个形容与实测差得很远:`src/store` 里有
`projects.ts` 1,269 行、`onboarding.ts` 922 行、`session-states.ts` 811 行、`updates.ts` 790 行、
`session.ts` 663 行、`review.ts` 597 行 —— 6 个模块超过 500 行,合计 5,052 行,占 store 目录的近三分之一。
这些模块里装的不是「原子」而是**整块业务流程**(项目 CRUD + git worktree 编排、OAuth 设备码轮询、
git 审阅面板的暂存/还原/提交/推送/开 PR)。读者按 DESIGN.md 的描述去找,会以为 `src/store` 是一堆
十几行的小文件。

### ◎2 —— README 说「gateway-bound nanostores are wiped」,清的是**一部分**

`apps/desktop/README.md:156 @ 863e313`

> cold boot. The shell and current management overlay remain mounted while
> gateway-bound nanostores are wiped, query-backed data is invalidated, and the
> new connection repopulates skeletons.

**逐句判定**(不把整句记 ▲):「shell 与管理浮层保持挂载」为真(`softSwitch` 不 navigate,
`beforeConnectionSwitch` 明确 `preserveRoute: true`);「query-backed data is invalidated」为真
(`invalidateProfileScopedQueries()`);「repopulates skeletons」为真(`setSessionsLoading(true)`)。
只有 **「gateway-bound nanostores are wiped」这一小句**在字面上过宽 —— 详见下面 ■1,
那里给了「哪些被清、哪些没被清」的完整清单。因为它是一句多断言里的一个分句、
且被清的确实是**最主要**的那批(会话列表、会话状态、artifact、live-sync 闸),
按本项目的记号规矩,记 **◎(成立但显著保守/过宽)**,不记 ▲。

---

## 6. 缺陷(■)

### ■1 —— 软切换只清了 5 个 store,另有 12 个「纯事件驱动」的 store 没清;`$billingBlock` 因此变成不可清除的悬挂状态

**现象与锚点。**软切换的清单函数只清 5 个模块的状态:

`apps/desktop/src/store/gateway-switch.ts:42 @ 863e313`

```ts
export function wipeSessionListsForGatewaySwitch(): void {
  // The next backend is a different runtime — don't carry the old one's
  // "batched sidebar endpoint missing" capability verdict across the switch.
  resetSidebarBatchCapability()
  setSessions([])
  setSessionProfilesTruncated({})
  setCronSessions([])
  setMessagingSessions([])
  setMessagingPlatformTotals({})
  setMessagingTruncated(false)
```

而 §2.3 的事件表说明**有 26 个 store 模块是被网关事件写的**。两个集合相减,
**12 个纯事件驱动的模块在软切换时不被清**:`prompts`、`clarify`、`compaction`、`todos`、
`subagents`、`goals`、`tool-drafting`、`tool-diffs`、`billing-block`、`agent-notices`、
`reactions-local`、`approval-mode`。

其中大多数按 runtime id 归键,而 runtime id 是 UUID、跨后端不会撞,所以后果只是内存里的死条目。
**唯一会被用户看见的是 `billing-block`,因为它是单一全局槽,而且它的两条清除路径在切换后都失效:**

`apps/desktop/src/store/billing-block.ts:32 @ 863e313`

```ts
export function clearBillingBlock(sessionId?: string): void {
  const current = $billingBlock.get()

  if (!current) {
    return
  }

  // A scoped clear (new turn on session X) must not wipe a block raised by a
  // different session's provider.
  if (sessionId && current.sessionId !== sessionId) {
    return
  }

  $billingBlock.set(null)
}
```

- 路径 A(自动):`message.start` 时 `clearBillingBlock(sessionId)`
  (`apps/desktop/src/app/session/hooks/use-message-stream/gateway-event.ts:549`)。
  切换后新后端的 runtime id 与旧 block 的 `sessionId` 永远不等 → **第 41 行的 early return 命中,永不清除**。
- 路径 B(手动):横幅上的 × 按钮。但横幅自身按会话过滤 ——
  `apps/desktop/src/components/billing-banner.tsx:27`:`if (!active || !sessionId || active.sessionId !== sessionId) {`
  返回 null → **横幅根本不渲染,× 按钮不存在**。

于是切换后 `$billingBlock` 是一个**永远非 null、永远不可清除**的原子,直到窗口重载。
今天的可见影响有限(横幅与状态栈都按会话过滤),但这是一个**只增不减的错误状态**:
任何未来订阅 `$billingBlock` 而不做会话过滤的消费者(它是个全局槽,天然会被这么用)
都会显示一个来自已经不存在的后端的计费墙。

**负结论的搜索面**:`clearBillingBlock` 的全部调用点 = `apps/desktop/src` 全树
`--include=*.ts --include=*.tsx`、排除 `.test.`,共 3 处(定义 1 + gateway-event 1 + banner 1);
`wipeSessionListsForGatewaySwitch` 的调用点唯一,在 `use-gateway-boot.ts:295`;
`beforeConnectionSwitch` 的实现唯一,在 `app/contrib/wiring.tsx:729`,它做 4 件事
(`startFreshSessionDraft` / `resetOverlayReturnRoute` / `resetProjectTreeState` / `closeAllTerminals`),
不含任何 billing/prompt 清理。命令:

```verify
cd /home/user/hermes-agent && grep -rn "clearBillingBlock\|wipeSessionListsForGatewaySwitch\|beforeConnectionSwitch" \
  apps/desktop/src --include=*.ts --include=*.tsx | grep -v '\.test\.'
```

同一族的第二个观察:**`clearAllPrompts()` 的无参形态(全局重置)在生产代码里从无调用方**。
搜索面 = `apps/desktop/src` 全树 `--include=*.ts --include=*.tsx`,命中 13 处:
定义 1 处(`apps/desktop/src/store/prompts.ts:163`),
**生产调用 4 处且全部传了 sessionId**(`app/chat/session-tile-actions.ts:263`、
`app/session/hooks/use-message-stream/gateway-event.ts:708` 与 `:1171`、
`app/session/hooks/use-prompt-actions/index.ts:626`),
其余 8 处无参调用全在 `.test.tsx` / `.test.ts` 里。也就是说 approval/sudo/secret
三种阻塞提示**没有任何「换后端了,全丢掉」的路径**。

```verify
cd /home/user/hermes-agent && grep -rn "clearAllPrompts(" apps/desktop/src --include=*.ts --include=*.tsx
```

### ■2 —— `store/tool-diffs.ts` 的两处缓存都是**只增不减**,且没有任何清除路径

`apps/desktop/src/store/tool-diffs.ts:29 @ 863e313`

```ts
export function $toolInlineDiff(toolCallId: string): ReadableAtom<string> {
  let cached = inlineDiffCache.get(toolCallId)

  if (!cached) {
    cached = computed($toolDiffs, diffs => (toolCallId ? diffs[toolCallId] || '' : ''))
    inlineDiffCache.set(toolCallId, cached)
  }

  return cached
}
```

`$toolDiffs`(一个 `Record<toolCallId, diffText>`)与 `inlineDiffCache`(一个
`Map<toolCallId, ReadableAtom>`)都随每一次带 `inline_diff` 的 `tool.complete` 增长,
**整个模块 38 行里没有 `delete` / `clear` / `reset` 任何一个词**,也没有上限。
写入点唯一:`apps/desktop/src/app/session/hooks/use-message-stream/gateway-event.ts:841`。

对照组说明这不是「本仓库不在乎」:隔壁 `store/tool-view.ts` 对同形状的
`$toolDisclosureStates` 定了 `MAX_DISCLOSURE_STATES = 240` 并在读写两侧都 `.slice(-240)`;
`store/tool-dismiss.ts` 的注释**明确声明**「刻意留在模块内存里、随应用会话存活」并给了理由
(线程虚拟化,组件会反复卸载重挂)。`tool-diffs.ts` 既没有上限,也没有这样一句声明,
而它存的是**整段 diff 文本**(一个 45KB 的 `write_file` 的 inline diff 就是几十 KB),
在一个「专门用来长时间跑改文件的 agent」的桌面端里,这是一条随使用时长单调增长的内存曲线。

**负结论的搜索面**:`apps/desktop/src` 全树 `--include=*.ts --include=*.tsx`,
搜 `recordToolDiff|getToolDiff|toolInlineDiff|toolDiffs`,非测试命中 4 处(定义 3 + 消费 1);
模块内部 `delete|clear|reset` 命中 0。

```verify
cd /home/user/hermes-agent && grep -rn "recordToolDiff\|getToolDiff\|toolInlineDiff\|toolDiffs" \
  apps/desktop/src --include=*.ts --include=*.tsx | grep -v '\.test\.'
cd /home/user/hermes-agent && grep -c "delete\|clear\|reset" apps/desktop/src/store/tool-diffs.ts
```

### ■3(**较弱,标为待确认**)—— `approvalModeForProfile` 的「不知道」默认值比「解析失败」默认值更宽松

`apps/desktop/src/store/approval-mode.ts:23 @ 863e313`

```ts
function normalizeApprovalMode(value: unknown): ApprovalMode {
  const normalized = String(value ?? '')
    .trim()
    .toLowerCase() as ApprovalMode

  return APPROVAL_MODES.has(normalized) ? normalized : 'manual'
}

export function approvalModeForProfile(profile: string): ApprovalMode {
  return $approvalModes.get()[profileKey(profile)] ?? 'smart'
}
```

后端回了一个无法解析的值 → 落到 `'manual'`(最严);缓存里**根本还没有这个 profile 的条目**
(尚未 reconcile、或软切换后新后端还没报过)→ 落到 `'smart'`(较宽松)。
两个 fallback 方向相反。语义上可以辩护(「后端说了但我看不懂」vs「我还没问过」),
但这是一个审批相关的默认值,方向不一致值得被显式记录。**本片按 L2 只读了接口面,
没有追到 `approvalModeForProfile` 的每个消费点去判断这个差异是否真的会放宽某次审批,
所以标为待确认,列入移交项。**

---

## 7. 测试(行为规格)

跑的是主线在基线之外准备的副本(`/home/user/r10b-ts/hermes-agent`,`git archive` 导出,不污染基线)。

**环境(报数必须带):** node `v22.22.2` / npm `10.9.7` / vitest `4.1.10`;
`ls /home/user/r10b-ts/hermes-agent/node_modules | wc -l` = **736**(含 `.bin` 与 `@scope` 目录);
未安装任何新包。

| 命令 | Test Files | passed | failed | skipped |
|---|---|---|---|---|
| `npx vitest run --project ui src/store` | 53 | **642** | **0** | **0** |
| `npx vitest run --project ui src/hermes.test.ts src/hermes-parity.test.ts src/hermes-profile-scope.test.ts src/hermes-cron-scope.test.ts src/pairing-scope.test.ts src/webhooks-rest.test.ts` | 6 | **44** | **0** | **0** |

复现:

```verify
cd /home/user/r10b-ts/hermes-agent/apps/desktop && npx vitest run --project ui src/store
```

**零执行 / 整文件跳过的点名:0 处。**搜索面 = `apps/desktop/src/store/*.test.ts` 全部 53 个文件,
grep `describe.skip|it.skip|test.skip|.todo(`,零命中:

```verify
cd /home/user/hermes-agent && grep -rn "describe\.skip\|it\.skip\|test\.skip\|\.todo(" apps/desktop/src/store/*.test.ts
```

**覆盖缺口(这才是有信息量的部分)**:53 个测试文件对 86 个 store 模块 —— **33 个模块没有同名测试文件**。
`src/hooks/` 下 **7 个 hook 一个测试都没有**(`ls apps/desktop/src/hooks/*.test.* | wc -l` = 0);
`src/sdk/` 下 2 个文件也没有直接测试。

值得当规格读的两个:

- `apps/desktop/src/hermes-parity.test.ts` 是一份**REST 契约表**:逐个断言路径拼接、
  method、body 形状与超时值,例如「hub sources 用 45s 的网络容忍超时」「MCP server 名要 URL 编码
  (`file system` → `file%20system`)且用 60s 的启动容忍超时」。
  §2.2 那张 133 行的方法表,行为侧的锚就在这里。
- `apps/desktop/src/store/tool-diffs.test.ts` 只有 5 条断言,全部是「同 id 返回同一个 computed 引用」
  「不同 id 返回不同引用」「同值重写不通知」——**恰好一条都没测到清除**,
  与 ■2「压根没有清除路径」互相印证。

---

## 8. 判据自查

| # | 判据 | 自评 | 依据 / 缺口 |
|---|---|---|---|
| **1 点名到位** | 片内每个文件全路径 + 一句话角色 | **达标** | §0.1 给 11 个非 store 文件逐个;§0.2 把 86 个 store 归 12 组、组内逐个列全路径,并用 `probe_d_store_groups.py` 机械校验「不重不漏」(输出 `missing: []` / `extra: []` / `OK`)。此外 §2.1 的 85 行全表 + `active-work.ts` 的零导出说明,是第二重全覆盖点名。 |
| **2 接缝穷举** | 每个对外接缝逐项列全 + 机械枚举命令 + 条数 | **达标(6 张表全给了命令与条数)** | 表 A store 面 1,068 项 / 表 B `hermes.ts` 133 项 / 表 C 事件 47 型 42 分支 / 表 D SDK 130 名 / 表 E hooks 11 名 / 表 F 持久化键 64 个。**唯一的抽样残留**:表 A 只铺了 state/computed/action 三列,`type`(126)与 `const`(179)两列留在 TSV 里没进正文 —— 命令能打出来,正文没铺。 |
| **3 端到端链** | 一条链逐跳带锚点 | **达标** | §3 共 9 跳,跳 1→9 每跳一个锚点,跳 8 把 8 个订阅方逐个列出(不抽样)。 |
| **4 逐字取证** | ≥2 个围栏块是逐字源码 | **达标** | 共 15 个 `ts`/`tsx` 围栏块全部逐字摘录;非源码块一律 ```` ```verify ```` 标注。 |
| **5 记号** | ≥1 条 ■/▲/◇/◎ 带锚点 | **达标** | ▲1、◇1、◎1、◎2、■1、■2、■3(标为待确认),共 7 条,每条带锚点与搜索面。 |

**未达标 / 打折的地方,如实说:**

1. **表 A 的 `type` / `const` 两列没进正文**(见上)。按判据 2 的字面要求「导出面逐项列全」,
   这 305 个名字只在脚本输出里,正文里没有。占全部导出名的 28.6%。
2. **§4 的「逐机制」只覆盖了 6 个模块**(gateway / profile / session / session-states / prompts / main)。
   L2 的定义是「读接口面不读实现体」,接口面我做到了不抽样;但**机制叙述这一层是抽样的** ——
   `projects.ts`(1,269 行)、`onboarding.ts`(922)、`updates.ts`(790)、`review.ts`(597)
   四个大模块只有一句话角色 + 导出面全表,没有机制段落。按行数算,这 4 个模块 3,578 行
   (占本片 18.2%)只做到了「知悉用途 + 导出面枚举」的深度。
3. **■3 只到「看见方向不一致」为止**,没有追消费点确认可利用性,已按待确认处理并列入移交。
4. **`store/*.test.ts` 的 53 个文件我只跑没读**(它们不在本片清单里,属 LT 层)。
   §7 里那两条「当规格读」的引用是读过的,其余 51 个只有通过数。

---

## 9. 移交项

每条:锚点 + 紧跟的反引号摘录 + 一句话现象。

| 编号 | 锚点 + 摘录 | 现象 / 下一轮该做什么 |
|---|---|---|
| **H-R10B-D-a** | `apps/desktop/src/store/billing-block.ts:32`:`export function clearBillingBlock(sessionId?: string): void {` | 软切换后 `$billingBlock` 的两条清除路径同时失效(自动路径被 sessionId 早退挡住,手动路径的横幅按 sessionId 过滤而不渲染),成为不可清除的悬挂状态。需确认是否真会被用户看见,或只是内存里的死值。 |
| **H-R10B-D-b** | `apps/desktop/src/store/gateway-switch.ts:42`:`export function wipeSessionListsForGatewaySwitch(): void {` | 该函数清 5 个模块,而事件表显示有 26 个模块被网关事件写。差集 12 个模块(prompts / clarify / compaction / todos / subagents / goals / tool-drafting / tool-diffs / billing-block / agent-notices / reactions-local / approval-mode)在软切换后保留旧后端的条目。需逐个判断哪些是无害的死键、哪些会被 `''`(sessionId 为 null)这个兜底键暴露到新后端的空白草稿上。 |
| **H-R10B-D-c** | `apps/desktop/src/store/tool-diffs.ts:9`:`const inlineDiffCache = new Map<string, ReadableAtom<string>>()` | 该 Map 与它旁边的 `$toolDiffs` Record 都只增不减、无上限、无清除路径,存的是整段 diff 文本。需要量一下真实增长(一次典型编码会话产生多少 KB),再判断是缺陷还是可接受。 |
| **H-R10B-D-d** | `apps/desktop/src/store/approval-mode.ts:31`:`export function approvalModeForProfile(profile: string): ApprovalMode {` | 「缓存里没有这个 profile」落到 `'smart'`,而「后端值解析失败」落到 `'manual'` —— 两个 fallback 方向相反。需追这个函数的全部消费点,确认是否存在「软切换后短暂读到 smart」而导致某次审批被跳过的窗口。 |
| **H-R10B-D-e** | `apps/desktop/src/app/gateway/hooks/use-gateway-boot.ts:448`:`const live = new Set([...$workingSessionIds.get(), ...$attentionSessionIds.get()])` | secondary socket 的保留集是这样算的:先取「在忙/待输入」的 **stored id** 集合,再去 `$sessions` 里按 `session.id` 反查它属于哪个 profile。而 `apps/desktop/src/store/session.ts:334` 的 `mergeSessionPage` 自己的 docstring 说明**首答中的新会话可能根本不在 `$sessions` 里**。若如此,该 profile 不进 `keep`,`pruneSecondaryGateways` 会在它正忙时关掉它的 socket。本片没有验证这条路径是否真的可达(需要模拟一个后台 profile 的首答),**不作为已证实缺陷,只作为线索移交**。 |
| **H-R10B-D-f** | `apps/desktop/src/store/session.ts:39`:`function profileNavigationKey(base: string, profile: string): string {` | 「上次会话 / 上次路由」按 profile 命名空间化,而 composer 的模型选择(`hermes.desktop.composer.*` 五个键)刻意全局。两种作用域选择都有注释辩护,但 §2.6 那张四类作用域表里还有一批键**没有任何作用域段也没有注释说明为什么可以全局**(如 `hermes.desktop.visible-models`、`hermes.desktop.model-presets`、`hermes.desktop.collapsed-providers` —— 后者有注释,前两者没有)。`apps/desktop/AGENTS.md:44` 要求「Persisted state must declare its scope in its own key」,可以逐键对这条要求做一次核查。 |
| **H-R10B-D-g** | `apps/desktop/src/store/tool-diffs.test.ts:7`:`expect($toolInlineDiff('a')).toBe($toolInlineDiff('a'))` | 53 个 store 测试文件对 86 个模块 —— 33 个模块没有同名测试;`src/hooks/` 7 个文件、`src/sdk/` 2 个文件零测试。若要做「测试即规格」的覆盖图,这 42 个文件是空白区。 |

---

## 10. 本片成本自报

```text
片号            : D
层              : L2
文件数 / 行数   : 97 / 19,637
实际打开的文件数: 41
    明细:store 24 个(完整读 11:gateway / gateway-switch / profile / session /
    session-states(前 400 行) / prompts / live-sync / tool-diffs / tool-view / billing-block /
    approval-mode;头部 14 行 + 导出面读 86 个中的其余 13 个有引用需要的),
    hooks 7 个(全部完整读,总共才 381 行),sdk 2 个(全部完整读),
    hermes.ts(读约 500 行 + 脚本抽全量签名),main.tsx(完整),
    另加 7 个片外文件用于接链取证(gateway-event.ts / utils.ts / gateway-events.ts /
    use-gateway-boot.ts / wiring.tsx / json-rpc-gateway.ts / billing-banner.tsx)
实际读过的行数  : 约 6,800
    估法:完整读的 21 个片内文件按其真实行数加总(约 4,900),
    hermes.ts 计 500,片外 7 个文件按实际 sed 区间计约 900,
    其余 62 个 store 只读头部 14 行 + 脚本产出的导出面,计 62×14 ≈ 870。
    即 全片 19,637 行里约 35% 被人眼过过,其余 65% 由脚本枚举导出面覆盖 —— 这正是 L2 的形状。
底稿字节数      : (主线自测,不填)
主观耗费        : 中
    瓶颈在「文件多但每个都短」+「跨文件追链」两者叠加:86 个 store 里 40 个不到 100 行,
    人眼逐个读性价比极低,所以先写了 3 个探针(surface / hermes-api / event-to-store)
    把导出面机械枚举出来,再把人力全押在 6 个真正有机制的大模块与那条 9 跳链上。
    真正费时的是判据 3 那条链:它跨 7 个文件、其中 4 个不在本片,
    每一跳都要先确认「下一跳到底在哪」再取证。
    L3 的推断:如果 L3 只要求「知悉用途」,本片这种「头部 14 行 + 脚本导出面」的做法
    单文件成本约 1–2 分钟,一轮 787 文件是可行的;但前提是**先有探针**——
    没有探针时,86 个文件的导出面靠人抄,光这一张表就会吃掉本片一半时间。
```
