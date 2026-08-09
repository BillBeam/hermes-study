# r10b 片B · 会话列表、切换与会话视图 —— 底稿

> 层:**L2(结构级理解)**。原则:**可以不读实现体,但不能抽样接口面**。
> 溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于代码块之前。
> 围栏块 = 逐字源码摘录;```text / ```verify / ```console = 作者声明的非源码。
> 基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`。

---

## 0. 本片范围与逐文件点名

本片 **55 文件 / 18,761 行**,全部在 `apps/desktop/src/app/` 下。核数命令(可重跑):

```verify
cd /home/user/hermes-agent && n=0; t=0
while read -r f; do n=$((n+1)); t=$((t+$(wc -l < "$f"))); done \
  < /home/user/hermes-study/data/r10b/slices/B.txt
echo "$n / $t"     # -> 55 / 18761
```

下面按功能簇逐个点名(**每个文件一次全路径 + 一句话角色**)。同型薄文件归组,组内仍逐个列全路径。

### 0.1 侧栏根与会话列表骨架(6 文件)

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/app/chat/sidebar/index.tsx` | 侧栏根组件 `ChatSidebar`(1,532 行,本片最大):汇总 nav 行、搜索框、Pinned / Sessions(或 Projects)/ 每平台 messaging / Cron 五类分区,持有全部分组、排序、筛选、分页的**决策逻辑**;13 个回调 props 全部由外部注入。 |
| `apps/desktop/src/app/chat/sidebar/sessions-section.tsx` | 通用「会话分区」渲染器 `SidebarSessionsSection` + `VIRTUALIZE_THRESHOLD`:40 个 props 的一个组件,内部按 8 条互斥分支决定渲染骨架/项目内容/空态/项目总览/分组/虚拟列表/可拖拽平铺/静态平铺。 |
| `apps/desktop/src/app/chat/sidebar/session-row.tsx` | 单条会话行 `SidebarSessionRow`:标题、状态点、年龄、handoff 平台徽章、profile 标签,以及 8 种指针手势(见 §2.5);用自定义 `rowPropsEqual` memo 化,专门为「流式期间整列不重渲染」而写。 |
| `apps/desktop/src/app/chat/sidebar/virtual-session-list.tsx` | 长列表虚拟化 `VirtualSessionList`(TanStack Virtual),把日期分隔行与会话行混排进同一个虚拟窗口,并把 dnd-kit 的 `setNodeRef` 与虚拟器的 `measureElement` 合并到同一个 ref。 |
| `apps/desktop/src/app/chat/sidebar/load-more-row.tsx` | 分页「…」按钮 `SidebarLoadMoreRow`,recents / messaging / cron 三处共用同一个视觉与交互。 |
| `apps/desktop/src/app/chat/sidebar/section-states.tsx` | 三个空/骨架态:`SidebarSessionSkeletons`(加载骨架)、`SidebarBlankState`(全空 → 引导建项目)、`SidebarPinnedEmptyState`(Pinned 空 → 提示 ⇧-click)。 |

### 0.2 排序 / 索引 / 状态推导(3 个纯函数模块)

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/app/chat/sidebar/order.ts` | 手工拖拽顺序与实时集合的对账:`reconcileFreshFirst` / `resolveManualSessionOrderIds` / `orderByIds` / `reconcileOrderIds` / `sameIds`。**新出现的 id 一律置顶**,这是「新建会话不会沉底」的唯一保证。 |
| `apps/desktop/src/app/chat/sidebar/session-index.ts` | `buildSessionByAnyId`:把 recents / cron / messaging 三个独立切片按「活 id + lineage 根 id」双键索引,Pinned 分区靠它把一个 pin 解析回行。 |
| `apps/desktop/src/app/chat/sidebar/session-row-state.ts` | 行状态点的**优先级判定** `sessionDotState`(needs-input > working/stalled > background > unread > idle)与 `sessionShowsRunningArc`。 |

### 0.3 行/分区的公共 chrome 与交互原语(3 文件)

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/app/chat/sidebar/chrome.tsx` | 侧栏行几何的**唯一定义处**:`SidebarRowShell`(行高唯一所有者)/`RowBody`/`RowLead`/`RowLabel`/`RowGrab`/`RowCluster`/`RowStack`/`RowNest`/`SidebarDateDivider`/`SidebarSectionMeta`/`SidebarRowLeadGlyph`/`SidebarRowLink`/`SIDEBAR_LEAD_ICON_SIZE`(13 个导出)。 |
| `apps/desktop/src/app/chat/sidebar/reorderable-list.tsx` | 通用可重排列表原语 `ReorderableList` + `useSortableBindings`:每个列表自带 `DndContext`,所以嵌套列表的拖拽互不串扰;transform 只走 Y 轴。 |
| `apps/desktop/src/app/chat/sidebar/split-submenu.tsx` | 「Open in split ▸」子菜单 `SplitSubmenu` 与两套菜单件套 `DROPDOWN_SPLIT_KIT` / `CONTEXT_SPLIT_KIT`,让同一份方向菜单能挂进 dropdown 或右键菜单。 |

### 0.4 会话行动作面(1 文件)

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/app/chat/sidebar/session-actions-menu.tsx` | 会话的全部动作:`SessionActionsMenu`(⋯ 下拉)、`SessionContextMenu`(右键)、`renameSessionPreferringRpc`(重命名时优先走 `session.title` RPC、失败回落 REST),内含 Appearance 配色子菜单、Move-to-project 子菜单与 `RenameSessionDialog`。 |

### 0.5 侧栏里的「项目 / 工作树」子树(11 文件,`projects/`)

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/app/chat/sidebar/projects/index.ts` | 该子树对侧栏根暴露的公共面(barrel),15 个名字。 |
| `apps/desktop/src/app/chat/sidebar/projects/workspace-groups.ts` | **渲染契约与纯逻辑核心**:三层树接口 `SidebarProjectTree` / `SidebarWorkspaceTree` / `SidebarSessionGroup`,lane 排序、`mergeRepoWorktreeGroups`(纯视觉的 `git worktree list` 空 lane 注入)、`overlayRepoLanes` / `overlayLiveLanes` / `overlayLivePreviews`(实时会话乐观叠加)、`excludeProjectSessions`(把 pin 从项目树里摘走)。 |
| `apps/desktop/src/app/chat/sidebar/projects/model.ts` | 总览排序与展开态:`sortProjectsForOverview` / `orderProjectsByIds`(与 `orderByIds` 不同:新项目**不置顶**)/ `useRepoWorktreeMap`(并发上限 4 的 `git worktree list` 探测)/ `useWorkspaceNodeOpen` / `PROJECT_PREVIEW_COUNT` / `SIDEBAR_GROUP_PAGE`。 |
| `apps/desktop/src/app/chat/sidebar/projects/overview-row.tsx` | 项目总览的一行 `ProjectOverviewRow`(可拖拽、可展开预览 3 条最近会话)+ `ProjectBackRow`(返回总览)+ `projectIcon`。 |
| `apps/desktop/src/app/chat/sidebar/projects/entered-content.tsx` | 「已进入某项目」时的主体 `EnteredProjectContent` 与 `RepoFlatSection`:单 repo 不显示 repo 头、只有 linked worktree 才嵌套;并承载 worktree 删除的两级确认对话框(普通 / force)。 |
| `apps/desktop/src/app/chat/sidebar/projects/workspace-group.tsx` | 一条 lane(profile 组 / 分支 / worktree / kanban 聚合)`SidebarWorkspaceGroup`:折叠、分页显示、lane 内「+ 新会话」(main lane 会先 `switchBranchInRepo`)。 |
| `apps/desktop/src/app/chat/sidebar/projects/workspace-header.tsx` | lane/repo 头部与其动作:`WorkspaceHeader`(头部截断策略是**掐头留尾**,因为分支名前缀常常相同)、`WorkspaceAddButton`、`WorkspaceShowMoreButton`、`WorkspaceMenu`、`WorkspaceContextMenu`、`StartWorkButton`。 |
| `apps/desktop/src/app/chat/sidebar/projects/project-menu.tsx` | 项目的 kebab 菜单 `ProjectMenu` 与右键菜单 `ProjectContextMenu`(共用同一份 `useProjectActions`:改名 / 加文件夹 / 设为活动 / 外观 / reveal / copy path / 删除或从侧栏移除)。 |
| `apps/desktop/src/app/chat/sidebar/projects/project-appearance.tsx` | 项目外观选择器 `ProjectAppearancePicker` 与 28 个可选 codicon 常量 `PROJECT_ICONS`。 |
| `apps/desktop/src/app/chat/sidebar/projects/worktree-dialog.tsx` | 全应用**只挂载一次**的「新建 worktree」对话框 `WorktreeDialog`,由 `$worktreeDialog` atom 驱动(⌘⇧B / 侧栏 + / coding rail kebab 三个入口都只发意图,不各自挂 dialog)。 |
| `apps/desktop/src/app/chat/sidebar/projects/base-branch-picker.tsx` | 新 worktree 的基分支下拉 `BaseBranchPicker`:列本地 + 远端跟踪分支,默认 `origin/HEAD`,当前会话分支置顶。 |

### 0.6 项目对话框与 profile 轨(2 文件)

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/app/chat/sidebar/project-dialog.tsx` | 单例项目对话框 `ProjectDialog`,由 `$projectDialog` atom 驱动 create / rename / add-folder 三种模式;创建强制至少一个文件夹(项目按 cwd 前缀认领会话)。 |
| `apps/desktop/src/app/chat/sidebar/profile-switcher.tsx` | 侧栏底部的 profile 轨 `ProfileRail`(748 行):彩色方块条 + 拖拽重排 + 长按改色 + 「default↔all」切换 + Manage 溢出;超过 13 个 profile 折叠成下拉。内部另有 `EditSoulDialog` / `AddProfileButton` / `ImportProfileButton` / `ProfileDropdown` / `ProfileDropdownItem` / `ProfilePill` / `ProfileSquare`。 |

### 0.7 Cron 分区与 profile 预热(2 文件)

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/app/chat/sidebar/cron-jobs-section.tsx` | 侧栏 Cron 分区 `SidebarCronJobsSection`:按下次运行时间排序、行内展开最近 5 次 run(可直接点开那次 run 的会话)、暂停/恢复/删除直接打 `$cronJobs` atom。 |
| `apps/desktop/src/app/chat/sidebar/use-profile-prewarm.ts` | `useProfilePrewarm`:悬停 120ms 后预热该 profile 的后端进程,让跨 profile 点击少付一次冷启动。 |

### 0.8 「打开一个会话」这一道门与几个入口(4 文件)

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/app/open-session.ts` | **全应用唯一的「打开会话」入口** `openSession`,4 种 intent(`in-place` / `stack` / `tab` / `window`)+ `openSessionIntentFromModifiers` + `mainChatOccupied`;所有表面(侧栏、⌘K、通知、switcher、@session 引用、cron、artifacts)都走它。 |
| `apps/desktop/src/app/session-switcher.tsx` | ^Tab 会话切换 HUD `SessionSwitcher`:portal 到 body、无 Dialog(否则 Tab 会被抢),行上带 working/attention/unread 三色点与 ⌃1–9 序号。 |
| `apps/desktop/src/app/session-picker-overlay.tsx` | `/resume`、`/sessions`、`/switch` 打开的会话选择器挂载点 `SessionPickerOverlay`,gateway 未连通时直接不渲染。 |
| `apps/desktop/src/app/session/workspace-session-target.ts` | `startWorkspaceSession`:从某个 worktree/项目 lane 起一个新会话草稿,并用 `config.get{key:'project'}` 把 cwd/branch 规范化回来;用 `$newChatWorkspaceTargetGeneration` 做代际防竞态。 |

### 0.9 Quick Entry 迷你窗(2 文件)

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/app/quick-entry/quick-entry-root.tsx` | `mountQuickEntry`:`?win=quick` 走同一份 bundle,但只挂一个极简捕获面(无 app shell、无 gateway、无 router),并强制宿主层透明。 |
| `apps/desktop/src/app/quick-entry/quick-entry-app.tsx` | `QuickEntryApp`:一个输入框 + 目标会话下拉;**全部行为都在纯 reducer `quickComposerReducer` 里**,组件只负责把 `send` 交给 shell。它自己不连 gateway,连通性与最近会话由主渲染进程经 main 推过来。 |

### 0.10 会话视图的 hook 层(22 文件,`session/hooks/`)

这一层是 `apps/desktop/src/app/contrib/wiring.tsx` 组装出来的「会话视图」的全部行为。

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/app/session/hooks/use-session-state-cache.ts` | **本片的心脏**:按 runtime id 维护每会话 `ClientSessionState` 缓存 + stored→runtime 反向表,并决定「哪个会话的状态可以写进共享 `$messages` 视图」。含 RAF 合批、终局事件同步直刷、切换时丢弃待刷帧。 |
| `apps/desktop/src/app/session/hooks/use-session-actions/index.ts` | 会话生命周期动作(1,472 行):`resumeSession`(暖缓存快路径 + REST 预取与 RPC 并发的冷路径)、`startFreshSessionDraft`、`createBackendSessionForSend`、`openNewSessionTile`、`forkBranch` / `branchCurrentSession` / `branchStoredSession`、`removeSession`、`archiveSession`、自动压缩换 id 的路由跟随。 |
| `apps/desktop/src/app/session/hooks/use-session-actions/utils.ts` | 上者的纯逻辑与对账层(1,077 行):`reconcileResumeMessages`、`preserveLocalPendingTurnMessages`、`appendLiveSessionProjection`、`chatMessageArraysEquivalent` 系列结构比较、`resolveStoredSession` / `resolveSessionProfile` 跨 profile 定位、`applyRuntimeInfo`、`isSessionGoneError`。 |
| `apps/desktop/src/app/session/hooks/use-route-resume.ts` | 路由 → 恢复的驱动器:路由变化 / gateway 重连 / 「卡在某个路由会话上」三种触发,以及**有界指数退避自动重试**(最多 4 次,1s→8s)与 exhausted 闩锁。 |
| `apps/desktop/src/app/session/hooks/session-context-drift.ts` | `sessionContextDrift` / `routeTargetFromToken`:判定一次在途提交期间「上下文是否真的漂到别的会话」(route / selection / composer 三个探针),用于中止误投递。 |
| `apps/desktop/src/app/session/hooks/use-session-list-actions.ts` | 侧栏列表的取数与分页:`refreshSessions`(一次批量 RPC 拿 recents+cron+messaging 三片)、`loadMoreSessions`、`loadMoreSessionsForProfile`、`loadMoreMessagingForPlatform`、`refreshCronJobs`、`refreshMessagingSessions`,以及刷新时必须保留的行集合 `sessionsToKeep`。 |
| `apps/desktop/src/app/session/hooks/use-message-stream/index.ts` | 流式增量的合批与落库:`queueDelta` / `scheduleDeltaFlush`(**自适应节流**,以上一次 flush 实测代价的 3 倍为地板,上限 250ms)、`completeAssistantMessage`、`failAssistantMessage`、`finalizeInterimAssistantMessage`、`upsertToolCall`。 |
| `apps/desktop/src/app/session/hooks/use-message-stream/gateway-event.ts` | **gateway 事件总分派器**(1,237 行):47 种事件类型的 if/else 链,负责路由到会话、判定 `isActiveEvent`、并把每种事件落到对应 store。 |
| `apps/desktop/src/app/session/hooks/use-message-stream/utils.ts` | 上二者的纯工具:`sessionInfoStatePatch`(9 个字段)、`SUBAGENT_EVENT_TYPES`、`toTodoPayload`、`delegateTaskPayloads`、`completionErrorText`、`STREAM_DELTA_FLUSH_MS=33` / `MAX_STREAM_FLUSH_GAP_MS=250`。 |
| `apps/desktop/src/app/session/hooks/use-prompt-actions/index.ts` | 提示词动作总装(962 行):返回 11 个动作(`submitText` / `cancelRun` / `editMessage` / `reloadFromMessage` / `restoreToMessage` / `redirectPrompt`(别名 `steerPrompt`)/ `executeSlashCommand` / `handoffSession` / `handleThreadMessagesChange` / `transcribeVoiceAudio`),并含附件上传 `uploadComposerAttachment`。 |
| `apps/desktop/src/app/session/hooks/use-prompt-actions/submit.ts` | 提交管线 `useSubmitPrompt`:目标会话解析、漂移判定、乐观行、附件同步、`prompt.submit`,并用 scope 注入让 tile 提交不污染主视图的 `$busy`/`$messages`。 |
| `apps/desktop/src/app/session/hooks/use-prompt-actions/slash.ts` | 斜杠命令分派 `useSlashCommand`(1,087 行):picker / action / rpc / exec 四类落地,`/resume`·`/sessions`·`/switch` 在此打开会话选择器。 |
| `apps/desktop/src/app/session/hooks/use-prompt-actions/rewind.ts` | 回卷/中断的**纯**核心:`runRewindSubmit`、`finalizeInterruptedMessages`、`planReload` / `planRestore` / `planEdit`、`applyReloadOptimistic` / `applyRewindOptimistic` / `applyBranchVisibility`、`truncateSubmitParams`。主聊天与 tile 共用它以防两条路径漂移。 |
| `apps/desktop/src/app/session/hooks/use-prompt-actions/resolve-target-session.ts` | `resolveTargetSessionId`:提交/斜杠命令必须打到哪个 runtime 的**四级信任阶梯**(显式 id → 活 ref(路由不反对时)→ 在**拥有它的 profile** 上 `session.resume` → 仅当真是新草稿才 create)。 |
| `apps/desktop/src/app/session/hooks/use-prompt-actions/utils.ts` | 提示词侧的纯工具(410 行,26 个导出):错误分类(`isSessionBusyError` / `isGatewayTimeoutError` / `isSessionNotFoundError` / `isProviderSetupError`)、`withSessionBusyRetry`、每会话单飞闸 `_submitInFlight`、`isTargetSessionBusy`、附件读取、`renderRpcResult`、`SubmitTextOptions`。 |
| `apps/desktop/src/app/session/hooks/use-background-queue-drain.ts` | `useBackgroundQueueDrain`:把**不在屏幕上**的会话的排队提示词也排空(可见 ChatBar 只管当前会话),用 lineage 判同一会话,失败退避重试并在 N 次后弹「队列卡住」。 |
| `apps/desktop/src/app/session/hooks/use-context-suggestions.ts` | `useContextSuggestions`:活动会话 + cwd 变化时拉 `complete.path` 的 `@file:` 建议,带「会话+cwd 仍然是同一个」的竞态守卫。 |
| `apps/desktop/src/app/session/hooks/use-cwd-actions.ts` | `useCwdActions`:`changeSessionCwd`(有活会话走 `session.cwd.set`,没有则写新会话草稿目标)与 `refreshProjectBranch`;显式用 ref 而非 prop 取会话 id,防止改错会话的工作区。 |
| `apps/desktop/src/app/session/hooks/use-hermes-config.ts` | `useHermesConfig`:拉 `config.yaml` + defaults,回填人格/推理档位/service tier/语音/终端字体;用 epoch + composer selection generation 双计数器防止旧响应覆盖用户新选择。 |
| `apps/desktop/src/app/session/hooks/use-model-controls.ts` | `useModelControls`:`selectModel`(有会话走 `config.set --session`,无会话只是本地 sticky UI)、`refreshCurrentModel`、`applySavedMainModel`;所有回调都从 store `.get()` 读而不捕获 prop。 |
| `apps/desktop/src/app/session/hooks/use-preview-routing.ts` | `usePreviewRouting`:在基础事件处理器外再包三种 preview 事件(`preview.open` / `preview.restart.complete` / `preview.restart.progress`),并提供 `restartPreviewServer`。 |

---

## 1. 这一簇解决什么问题

一句话:**让「同时开着几十上百个会话」这件事在一个窗口里可用**。拆成四个子问题:

1. **有哪些会话** —— 后端有 N 个 profile、每个 profile 一个 `state.db`,会话还分 local / cron / messaging / kanban / subagent 五种来源。侧栏必须在**一次刷新**里拿到三片(recents / cron / messaging)、按 profile 作用域过滤、按「最近活动」排序、并叠加用户的手工拖拽顺序与 pin。
2. **怎么在它们之间切** —— 切换不是「改一个 id」:它要把 gateway 换到那个会话所属的 profile、要判断这个会话是不是已经作为 tile/主 tab 在屏幕上(是则跳过去而不是抢过来)、要在恢复失败时有界重试、还要在快速连点 A→B→C 时保证 A 的迟到响应不会把界面拽回 A。
3. **切过去看到什么** —— 冷会话要先出 loader、暖会话要立刻重绘缓存;转录既来自 REST(持久权威)又来自 gateway 的 runtime 投影(在途轮次权威),两者必须对账而不是二选一;后台会话仍在流式,它的更新只能进自己的缓存、绝不能进共享视图。
4. **不打断正在读的人** —— 流式增量合批、后台 tab 的 RAF 被 Electron 冻结时的兜底、滚动位置在切换与测量之间的保持。

这一片的**代码形状**因此高度一致:每一处异步都配一个「代际号 / 请求令牌 / ref 快照」,每一处缓存都配一个「这条缓存还属于它吗」的归属校验。

---

## 2. 接缝穷举

> 判据 2 是本片重心。每张表给**机械枚举命令**与条数;命令都能重跑。

### 2.1 `ChatSidebar` 的 props 契约(13 条,逐项列全)

```verify
cd /home/user/hermes-agent && awk '/^interface ChatSidebarProps/,/^}/' \
  apps/desktop/src/app/chat/sidebar/index.tsx | grep -cE '^  [a-zA-Z]'
# -> 13
```

`apps/desktop/src/app/chat/sidebar/index.tsx:227 @ 863e313`

```tsx
interface ChatSidebarProps extends React.ComponentProps<typeof Sidebar> {
  currentView: AppView
  onNavigate: (item: SidebarNavItem) => void
  onLoadMoreSessions: () => Promise<void> | void
  onLoadMoreProfileSessions?: (profile: string) => Promise<void> | void
  onLoadMoreMessaging?: (platform: string) => Promise<void> | void
  onResumeSession: (sessionId: string) => void
  onDeleteSession: (sessionId: string) => void
  onArchiveSession: (sessionId: string) => void
  onBranchSession: (sessionId: string) => void
  onNewSessionInWorkspace: (path: null | string) => void
  /** Create a brand-new session and open it as a tile on `dir`. */
  onNewSessionSplit: (dir: SplitDir) => void
  onManageCronJob: (jobId: string) => void
  onTriggerCronJob: (jobId: string) => void
}
```

其中 12 个(除 `currentView`)被显式重新声明为 `SidebarActions` 类型并逐名转发:

`apps/desktop/src/app/contrib/types.ts:11 @ 863e313`

```ts
/** The ChatSidebar handlers the controller owns — forwarded verbatim. */
export type SidebarActions = Pick<
  ComponentProps<typeof ChatSidebar>,
  | 'onArchiveSession'
  | 'onBranchSession'
  | 'onDeleteSession'
  | 'onLoadMoreMessaging'
  | 'onLoadMoreProfileSessions'
  | 'onLoadMoreSessions'
  | 'onManageCronJob'
  | 'onNavigate'
  | 'onNewSessionInWorkspace'
  | 'onNewSessionSplit'
  | 'onResumeSession'
  | 'onTriggerCronJob'
>
```

### 2.2 `SidebarSessionsSection` 的 props 契约(40 条)与 8 条渲染分支

```verify
cd /home/user/hermes-agent && awk '/^interface SidebarSessionsSectionProps/,/^}/' \
  apps/desktop/src/app/chat/sidebar/sessions-section.tsx | grep -cE '^  [a-zA-Z]'
# -> 40
```

40 个名字(全列,来源同上命令去掉 `-c`):

```text
label open onToggle sessions activeSessionId workingSessionIdSet onResumeSession
onDeleteSession onArchiveSession onBranchSession onTogglePin onNewSessionInWorkspace
pinned rootClassName contentClassName emptyState forceEmptyState headerAction footer
groups tree projectOverview projectOverviewPreviews projectsLoading onEnterProject
projectContent projectRepoWorktrees liveSessions removedSessionIds activeProjectId
labelMeta labelIcon collapsible sortable onReorderSessions onReorderProjects
projectBackRow dndSensors showProfileTags dateGrouped
```

**同一个组件被侧栏根实例化 4 次**(搜索结果 / Pinned / Sessions-or-Projects / 每个 messaging 平台一份),靠上面这些开关拼出四种形态。

渲染分支(互斥 if/else 链,8 条):

```verify
cd /home/user/hermes-agent && awk 'NR>=316 && NR<=427' \
  apps/desktop/src/app/chat/sidebar/sessions-section.tsx | grep -cE "^  (if \(|\} else)"
# -> 8
```

| # | 条件 | 渲染 |
|---|---|---|
| 1 | `showProjectsSkeleton` | 项目树首帧骨架 |
| 2 | `projectContent` | 已进入项目:back row + `EnteredProjectContent` 或空态 |
| 3 | `showEmptyState` | 调用方给的空态节点 |
| 4 | `projectOverview?.length` | 项目总览(Home 固定首位、其余可拖拽) |
| 5 | `groups?.length` | profile/source 分组(静态,不可拖) |
| 6 | `flatVirtualized` | `VirtualSessionList`(阈值 25 行) |
| 7 | `sessionsDraggable && onReorderSessions` | 可拖拽平铺 |
| 8 | else | 静态平铺 |

### 2.3 侧栏读写的 store 面

**(a) `@/store/layout` 里被侧栏根直接引用的 29 个符号**(全列):

```verify
cd /home/user/hermes-agent && awk '/^import \{$/{start=NR} {L[NR]=$0} \
  /^\} from .@\/store\/layout.$/{for(i=start+1;i<NR;i++) print L[i]}' \
  apps/desktop/src/app/chat/sidebar/index.tsx | grep -cE '^  [A-Za-z$]'
# -> 29
```

```text
$dismissedAutoProjectIds  $panesFlipped  $pinnedSessionIds  $sidebarAgentsGrouped
$sidebarCronOpen  $sidebarMessagingOpenIds  $sidebarPinsOpen  $sidebarProjectOrderIds
$sidebarRecentsOpen  $sidebarSessionOrderIds  $sidebarSessionOrderManual
$sidebarWorkspaceOrderIds  $sidebarWorkspaceParentOrderIds  filterVisibleProjects
pinSession  SESSION_SEARCH_FOCUS_EVENT  setPinnedSessionOrder  setSidebarAgentsGrouped
setSidebarCronOpen  setSidebarPinsOpen  setSidebarProjectOrderIds  setSidebarRecentsOpen
setSidebarSessionOrderIds  setSidebarSessionOrderManual  setSidebarWorkspaceOrderIds
setSidebarWorkspaceParentOrderIds  SIDEBAR_SESSIONS_PAGE_SIZE
toggleSidebarMessagingOpen  unpinSession
```

**(b) 会话列表视图状态的持久化面 —— 13 个 localStorage 键**(全列):

```verify
cd /home/user/hermes-agent && grep -nE "^const SIDEBAR_[A-Z_]*_STORAGE_KEY = " \
  apps/desktop/src/store/layout.ts | wc -l
# -> 13
```

| 键 | 存什么 |
|---|---|
| `hermes.desktop.pinnedSessions` | Pinned 会话(按**lineage 根 id**) |
| `hermes.desktop.agentsGroupedByWorkspace` | Sessions 分区处于 flat 还是 Projects 模式 |
| `hermes.desktop.sidebarCronOpen` | Cron 分区折叠态 |
| `hermes.desktop.sidebarMessagingOpen` | 各 messaging 平台分区折叠态 |
| `hermes.desktop.sessionOrder` | 手工拖拽的会话顺序 |
| `hermes.desktop.sessionOrder.manual` | 是否处于手工排序模式 |
| `hermes.desktop.workspaceOrder` | worktree lane 顺序 |
| `hermes.desktop.workspaceParentOrder` | repo 顺序 |
| `hermes.desktop.projectOrder` | 项目总览顺序 |
| `hermes.desktop.workspaceCollapsed` | (旧)折叠态 |
| `hermes.desktop.workspaceNodeOpen` | 每个 repo/lane 节点的**已解析布尔**展开态 |
| `hermes.desktop.dismissedAutoProjects` | 用户从侧栏隐藏的自动项目 |
| `hermes.desktop.dismissedWorktrees` | 用户从侧栏隐藏的 worktree lane |

`workspaceNodeOpen` 存「已解析的布尔」而不是「与默认值的差异」,是为了在 lane 的 `defaultOpen` 翻转时(空 lane 默认折叠 → 有会话后默认展开)不把用户的显式选择重新解释掉。

`apps/desktop/src/app/chat/sidebar/projects/model.ts:173 @ 863e313`

```ts
export function useWorkspaceNodeOpen(id: string, defaultOpen = true): [boolean, () => void] {
  const state = useStore($sidebarWorkspaceNodeOpen)

  return [state[id] ?? defaultOpen, () => toggleWorkspaceNodeCollapsed(id, defaultOpen)]
}
```

**(c) 侧栏根订阅的会话/项目/profile atom**:除 layout 外还有 `@/store/session` 13 个、`@/store/projects` 15 个、`@/store/profile` 5 个、`@/store/session-states` 3 个、`@/store/cron` 1 个、`@/store/keybinds` 1 个、`@/store/route-tiles` 1 个 —— 见 `apps/desktop/src/app/chat/sidebar/index.tsx` 的 import 头(第 33–99 行)。

### 2.4 「打开一个会话」的 intent 面(4 种,逐项列全)

`apps/desktop/src/app/open-session.ts:1 @ 863e313`

```ts
/**
 * One door for "open this session" — every surface (sidebar, ⌘K, notifications,
 * session switcher, refs, cron/artifacts) goes through here so a chat that's
 * already a tile (or the main tab) is JUMPED TO instead of yanked into main.
 *
 * Intents:
 *   - `in-place` (sidebar click / Enter) — focus existing tile/main if on
 *     screen; else load into main (same as the left sessions sidebar).
 *   - `stack` (⌘K, notifications — anything that opens a chat from outside the
 *     workspace) — like `tab`, but may spend main or an open blank draft tab
 *     when either is empty.
 *   - `tab` (⌘/⌃-click / ⌘-Enter / session refs) — focus if already on screen,
 *     else open as a stacked session tab (never steals main from under you).
 *   - `window` (⇧⌘-click) — pop into its own window; falls back to `tab` when
 *     the bridge has no session-window support.
 */
```

`tab` 分支的三级回落(已在屏 → 花掉空白草稿 tab → 新开 tile):

`apps/desktop/src/app/open-session.ts:105 @ 863e313`

```ts
  if (resolved === 'tab') {
    // Already on screen? Front it. openSessionTile would no-op on main without
    // focusing, or try to relocate an existing tile — neither is right for a
    // soft "open beside" link.
    if (focusOpenSession(storedSessionId)) {
      return
    }

    // Nothing to jump to, but an open tab may still be an empty "New session" —
    // that's the tab the user would have typed into, so spend it rather than
    // stacking a second blank one beside it.
    if (spendBlankDraft && reuseBlankDraftTile(storedSessionId)) {
      return
    }

    openSessionTile(storedSessionId, 'center')

    return
  }
```

### 2.5 会话行的手势面(8 种,逐项列全)

来源 `apps/desktop/src/app/chat/sidebar/session-row.tsx`(第 94–247 行)。

| # | 手势 | 行为 | 代码位置(行号) |
|---|---|---|---|
| 1 | 右键 | `SessionContextMenu`(与 ⋯ 菜单同一份动作) | 94 |
| 2 | `pointerdown`(非 handle / 非 actions 区) | `startSessionDrag` — 指针拖拽,非 HTML5 DnD | 143–156 |
| 3 | `pointerenter` / `pointerleave` | profile 预热(悬停 120ms) | 161–162 |
| 4 | 中键点击 | `openSession(id, noop, 'tab')` | 173–176 |
| 5 | ⇧⌘/⇧⌃ + 左键 | `openSession(id, noop, 'window')` | 180–188 |
| 6 | ⌘/⌃ + 左键 | `openSession(id, noop, 'tab')` | 190–198 |
| 7 | ⇧ + 左键 | `onPin()` | 200–208 |
| 8 | 普通左键 | `onResume()` | 210 |

第 2 项与 8 项共用同一个 `<button>`:低于阈值的释放仍然是普通点击,所以拖拽源与点击目标能重叠。

### 2.6 会话动作菜单面(逐项列全)

`apps/desktop/src/app/chat/sidebar/session-actions-menu.tsx` 的 `useSessionActions` 按 5 组 + 3 个子面构造:

| 组 | 项 | 出现条件 |
|---|---|---|
| OPEN | `openInNewTab` | `surface === 'row'` 且尚未作为 tab 打开 |
| OPEN | `newWindow` | `canOpenSessionWindow()` |
| IDENTITY | `rename`(弹 `RenameSessionDialog`) | 恒有 |
| IDENTITY | `pin` / `unpin` | 恒有(`onPin` 缺失则 disabled) |
| 子面 | Appearance ▸ `SessionColorSwatches` | 恒有;按**durable id** 写颜色覆盖 |
| 子面 | `CopyButton`(copy id) | 恒有 |
| WORK | `branchFrom` | `onBranch` 存在 |
| WORK | `export` | 恒有 |
| 子面 | Move to project ▸ `MoveToProjectItems` | 恒有;排除当前项目与无文件夹项目 |
| TAB | `reload` / `close` / `closeOthers` / `closeToRight` / `closeAll` | 仅 `surface === 'tab'`,且 3 个 close* 需要 `tabPaneId` |
| DANGER | `archive`、`delete`(destructive) | 恒有 |
| 尾 | `hideTabBar` | 仅传入 `onHideTabBar` 时(主 tab) |

两个子面(配色、移动到项目)各自是**独立组件**,目的明确写在注释里:只有子菜单**打开时**才订阅相关 store,否则列表里每一行的菜单都会订阅 `$sessions`/`$projectTree`。

### 2.7 会话视图订阅的 gateway 事件表(47 + 3 = 50 种)

```verify
cd /home/user/hermes-agent && { \
  grep -oE "event\.type === '[a-zA-Z._]+'" \
    apps/desktop/src/app/session/hooks/use-message-stream/gateway-event.ts \
    | sed "s/.*'\(.*\)'/\1/"; \
  awk '/^export const SUBAGENT_EVENT_TYPES/,/\]\)/' \
    apps/desktop/src/app/session/hooks/use-message-stream/utils.ts \
    | grep -oE "'[a-z._]+'" | tr -d "'"; } | sort -u | wc -l
# -> 47
cd /home/user/hermes-agent && grep -oE "event\.type === '[a-z.]+'" \
  apps/desktop/src/app/session/hooks/use-preview-routing.ts | sort -u | wc -l
# -> 3
```

分派器的入口(先路由到会话,再判定是否活动会话):

`apps/desktop/src/app/session/hooks/use-message-stream/gateway-event.ts:255 @ 863e313`

```ts
  return useCallback(
    (event: RpcEvent) => {
      const payload = event.payload as GatewayEventPayload | undefined
      const explicitSid = event.session_id || ''

      const route = resolveGatewayEventSessionId({
        activeSessionId: activeSessionIdRef.current,
        eventType: event.type,
        explicitSessionId: explicitSid,
        unscopedStreamSessionId: unscopedStreamSessionIdRef.current
      })

      unscopedStreamSessionIdRef.current = route.nextUnscopedStreamSessionId

      if (route.drop) {
        return
      }

      const sessionId = route.sessionId
      const isActiveEvent = !!sessionId && sessionId === activeSessionIdRef.current
```

47 种(全列,按类归组):

| 类 | 事件 |
|---|---|
| 连接/广播 | `gateway.ready`、`skin.changed`、`pet.changed`、`cron.changed`、`sessions.changed`、`platforms.changed`、`pairing.changed`、`session.reclaimed` |
| 会话元信息 | `session.info`、`session.title` |
| 助手消息流 | `message.start`、`message.delta`、`message.interim`、`message.complete`、`message.reaction` |
| 思考/推理 | `thinking.delta`(**故意忽略**)、`reasoning.delta`、`reasoning.available` |
| MoA | `moa.reference`、`moa.aggregating`、`moa.progress`、`moa.phase` |
| 工具 | `tool.generating`、`tool.start`、`tool.progress`、`tool.complete` |
| 子代理 | `subagent.spawn_requested`、`subagent.start`、`subagent.thinking`、`subagent.tool`、`subagent.progress`、`subagent.complete` |
| 阻塞式请求 | `clarify.request`、`approval.request`、`sudo.request`、`secret.request`、`terminal.read.request`、`preview.read.request` |
| 桌面专属回灌 | `agent.terminal.output`、`terminal.close`、`pane.reveal` |
| 状态/通知 | `status.update`(4 个子 kind:`compacting`/`compacted`/`process`/`goal`)、`review.summary`、`notification.show`、`notification.clear`、`reaction`、`error` |
| (装饰器另加 3 种) | `preview.open`、`preview.restart.complete`、`preview.restart.progress` |

三条贯穿全表的路由规则:

1. **`isActiveEvent` 只门控「视图副作用」**(pet 动画、`setTurnStartedAt`、`setCurrentCwd`、`revealDesktopPane`),不门控 per-session 状态写入 —— 后台会话的 busy 位必须更新,否则侧栏的转圈点不会亮。
2. **阻塞式请求一律按会话停放**(`clarify` / `approval` / `sudo` / `secret` 都 `setNeedsInput`),因为它们是一次性事件:丢掉一次,那个后台会话就会永远卡在 Python 侧的 `_block`。
3. **profile 广播只认活动 profile**(`normalizeProfileKey(event.profile) === normalizeProfileKey($activeGatewayProfile.get())`)。

`session.info` 的字段面(9 个)在 `sessionInfoStatePatch` 里穷举:`model`、`provider`、`cwd`、`branch`、`personality`、`reasoning_effort`、`service_tier`、`fast`、`yolo`(`apps/desktop/src/app/session/hooks/use-message-stream/utils.ts` 第 13–53 行)。

### 2.8 会话视图 hook 层的返回面(6 个 hook,共 43 个导出动作)

```verify
cd /home/user/hermes-agent && grep -cE \
  "^import \{[^}]*\} from '\.\./session/(hooks/|workspace-session-target)" \
  apps/desktop/src/app/contrib/wiring.tsx
# -> 13   (12 个 hook + startWorkspaceSession)
```

| hook | 返回名(逐项列全) | 条数 |
|---|---|---|
| `useSessionStateCache` | `activeSessionIdRef` `ensureSessionState` `getRuntimeIdForStoredSession` `resetViewSync` `runtimeIdByStoredSessionIdRef` `selectedStoredSessionIdRef` `sessionStateByRuntimeIdRef` `syncSessionStateToView` `updateSessionState` | 9 |
| `useSessionActions` | `archiveSession` `branchCurrentSession` `branchStoredSession` `closeSettings` `createBackendSessionForSend` `openNewSessionTile` `openSettings` `removeSession` `resumeSession` `selectSidebarItem` `startFreshSessionDraft` | 11 |
| `useSessionListActions` | `loadMoreMessagingForPlatform` `loadMoreSessions` `loadMoreSessionsForProfile` `refreshCronJobs` `refreshMessagingSessions` `refreshSessions` | 6 |
| `useMessageStream` | `appendAssistantDelta` `appendReasoningDelta` `completeAssistantMessage` `handleGatewayEvent` `finalizeInterimAssistantMessage` `upsertToolCall` | 6 |
| `usePromptActions` | `cancelRun` `editMessage` `executeSlashCommand` `handleThreadMessagesChange` `handoffSession` `reloadFromMessage` `restoreToMessage` `redirectPrompt` `steerPrompt`(= `redirectPrompt` 的别名) `submitText` `transcribeVoiceAudio` | 11 |
| `useModelControls` | `applySavedMainModel` `refreshCurrentModel` `selectModel` | 3 |

另外 6 个 hook 无返回值或只返回小 bag:`useRouteResume`(void)、`useContextSuggestions`(void)、`useBackgroundQueueDrain`(void)、`useCwdActions`(`changeSessionCwd` / `refreshProjectBranch`)、`useHermesConfig`(`refreshHermesConfig` / `sttEnabled` / `voiceMaxRecordingSeconds`)、`usePreviewRouting`(`handleDesktopGatewayEvent` / `restartPreviewServer`)。

### 2.9 本片对外导出总面(192 条 export 语句)

```verify
cd /home/user/hermes-agent && while read -r f; do \
  grep -cE "^export (async )?(function|const|type|interface|class) |^export \{|^export \*" "$f"; \
done < /home/user/hermes-study/data/r10b/slices/B.txt | paste -sd+ | bc
# -> 192
```

导出最密集的 5 个文件即本片的「工具带」:`use-prompt-actions/utils.ts`(26)、`use-session-actions/utils.ts`(19)、`projects/workspace-groups.ts`(18)、`use-prompt-actions/rewind.ts`(13)、`sidebar/chrome.tsx`(13)。

### 2.10 `projects/` 子树对侧栏根的公共面(15 个名字,barrel 全列)

`apps/desktop/src/app/chat/sidebar/projects/index.ts:1 @ 863e313`

```ts
// Public surface of the project/worktree sidebar, consumed by the sidebar root.
export { EnteredProjectContent } from './entered-content'
export {
  orderProjectsByIds,
  PROJECT_PREVIEW_COUNT,
  projectTreeCwd,
  sortProjectsForOverview,
  useRepoWorktreeMap
} from './model'
export { ProjectBackRow, ProjectOverviewRow } from './overview-row'
export { ProjectMenu } from './project-menu'
export { SidebarWorkspaceGroup } from './workspace-group'
export {
  excludeProjectSessions,
  overlayLiveLanes,
  overlayLivePreviews,
  sessionRecency,
  type SidebarProjectTree,
  type SidebarSessionGroup,
  type SidebarWorkspaceTree
} from './workspace-groups'
export { StartWorkButton } from './workspace-header'
```

### 2.11 未穷举/穷举不足的部分(据实报)

- `apps/desktop/src/app/chat/sidebar/profile-switcher.tsx`(748 行):只读了前 200 行 + 内部组件清单(8 个),**未逐项穷举 profile 轨的动作面**(重命名/删除/导入/导出/SOUL 编辑)。
- `apps/desktop/src/app/session/hooks/use-prompt-actions/slash.ts`(1,087 行):只读了 import 头、常量与 picker 分支,**未穷举斜杠命令表**(该表本身在 `apps/desktop/src/lib/desktop-slash-commands.ts`,不在本片)。
- `apps/desktop/src/app/session/hooks/use-prompt-actions/submit.ts`(747 行)与 `index.ts`(962 行):读了依赖面与返回面,**未逐行读提交管线实现体**(符合 L2,但提交管线的错误分支面没有穷举)。
- 综合自评:接缝穷举**做到约 8 成**。

---

## 3. 端到端链:点一条会话 → 切换 → 拉历史 → 渲染

### 3.1 逐跳

**跳 1 · 行上的点击**
`apps/desktop/src/app/chat/sidebar/session-row.tsx:177`(`onClick`)—— 无修饰键落到 `onResume()`,`onResume` 由分区注入。

**跳 2 · 分区把行 id 绑进回调**
`apps/desktop/src/app/chat/sidebar/sessions-section.tsx:228` 的 `renderRow` 里,`onResume: () => onResumeSession(session.id)`。

**跳 3 · 侧栏根把回调原样透传**
`apps/desktop/src/app/chat/sidebar/index.tsx:1256`,`onResumeSession={onResumeSession}`(三个分区实例都传同一个)。

**跳 4 · 控制器把它接到那道唯一的门**
`apps/desktop/src/app/contrib/wiring.tsx:896 @ 863e313`

```tsx
    onResumeSession: sessionId => openSession(sessionId, navigate),
```

**跳 5 · `openSession` 决定「跳过去」还是「装进主区」**
`apps/desktop/src/app/open-session.ts:129 @ 863e313`

```ts
  if (focusedSessionNeedsRoute(focusOpenSession(storedSessionId), $workspaceIsPage.get())) {
    navigate(sessionRoute(storedSessionId))
  }
```

`focusOpenSession` 命中 tile 或主会话就只是 front 它(`apps/desktop/src/store/session-states.ts:604`);未命中(或命中主会话但工作区正显示整页)才真的改路由。

**跳 6 · 路由变化驱动恢复**
`apps/desktop/src/app/session/hooks/use-route-resume.ts:145 @ 863e313`

```ts
      const stuckOnRoutedSession = routedSessionId !== selectedStoredSessionIdRef.current && !freshDraftReady

      // Resume when the route meaningfully changed, the gateway just opened, or
      // we're stranded on a routed session that never loaded. The first two
      // guard against a transient /:sid re-resume during "new chat" state clears
      // before the pathname updates from /:sid -> /.
      const shouldResume = pathnameChanged || gatewayBecameOpen || stuckOnRoutedSession
```

**跳 7 · `resumeSession` 开一个请求令牌,并同步「先把点击画出来」**
`apps/desktop/src/app/session/hooks/use-session-actions/index.ts:540 @ 863e313`

```ts
  const resumeSession = useCallback(
    async (storedSessionId: string, replaceRoute = false) => {
      const requestId = resumeRequestRef.current + 1
      resumeRequestRef.current = requestId
      const resumedSameSelectedSession = selectedStoredSessionIdRef.current === storedSessionId
      const resumeStartMessages = resumedSameSelectedSession ? $messages.get() : []

      const isCurrentResume = () =>
        resumeRequestRef.current === requestId && selectedStoredSessionIdRef.current === storedSessionId
```

紧接着 `setSelectedStoredSessionId` + `selectedStoredSessionIdRef.current = ...` 同步落地(第 561–562 行),这样侧栏高亮**在任何 await 之前**就跟上了。

**跳 8 · 暖缓存的归属校验(否则会画错会话)**
`apps/desktop/src/app/session/hooks/use-session-actions/index.ts:596 @ 863e313`

```ts
      const takeWarmCache = (): { runtimeId: string; state: ClientSessionState } | null => {
        const runtimeId = runtimeIdByStoredSessionIdRef.current.get(storedSessionId)
        const state = runtimeId ? sessionStateByRuntimeIdRef.current.get(runtimeId) : undefined

        if (!runtimeId || !state) {
          return null
        }

        if (state.storedSessionId !== storedSessionId) {
          runtimeIdByStoredSessionIdRef.current.delete(storedSessionId)
          sessionStateByRuntimeIdRef.current.delete(runtimeId)
          dropSessionState(runtimeId)

          return null
        }

        return { runtimeId, state }
      }
```

**跳 9 · 换 profile,再并发拉历史**
先 `resolveStoredSession(storedSessionId)` 找到这条会话属于哪个 profile,`await ensureGatewayProfile(sessionProfile)` 把唯一的活 gateway 换过去(第 628–635 行);冷路径把 REST 预取与 RPC 恢复**并发**发出:

`apps/desktop/src/app/session/hooks/use-session-actions/index.ts:864 @ 863e313`

```ts
        const prefetchPromise = watchWindow ? null : getSessionMessages(storedSessionId, sessionProfile)

        const resumePromise = requestGateway<SessionResumeResponse>('session.resume', {
          session_id: storedSessionId,
          cols: 96,
          source: 'desktop',
          // REST is the transcript authority for Desktop. Avoid duplicating a
          // potentially huge compression lineage in the WebSocket response.
          // Watch windows attach lazily (live mirror). Every other cold resume
          // gets the gateway's default deferred build: the RPC returns the
          // transcript immediately instead of blocking the switch on _make_agent
          // (MCP discovery / prompt build), and the agent pre-warms in the
          // background while the prefetch above paints the transcript.
          ...(watchWindow ? { lazy: true } : { omit_messages: true }),
          ...(sessionProfile ? { profile: sessionProfile } : {})
        })
```

注意:**并发发出,但不并发上屏** —— REST 结果先存 `prefetchedResult`,等 RPC 也 settle 后再合成一次,避免大转录被构建两遍(第 885–939 行)。

**跳 10 · 写进 per-session 缓存,由缓存决定能不能上共享视图**
`updateSessionState(resumed.session_id, …, storedSessionId)`(第 985 行)→ `useSessionStateCache.updateSessionState` → `publishSessionState` + `syncSessionStateToView`。

`apps/desktop/src/app/session/hooks/use-session-state-cache.ts:210 @ 863e313`

```ts
  const syncSessionStateToView = useCallback(
    (sessionId: string, state: ClientSessionState) => {
      // Only the currently-viewed session may stage into the shared `$messages`
      // view. A background session (e.g. one still busy and emitting stream /
      // error updates after the user toggled away) must update its own cache
      // entry but never the view — otherwise its messages clobber the
      // foreground transcript and appear to "bleed" into every other session.
      // The flush below also re-checks the active id, but staging here is what
      // prevents a background write from overwriting an already-pending
      // foreground write within the same animation frame (only one RAF is
      // scheduled, so the last `pendingViewStateRef` writer would otherwise win).
      if (sessionId !== activeSessionIdRef.current) {
        return
      }
```

**跳 11 · 渲染** —— `$messages` 被 ChatView / assistant-ui runtime 消费(该段在本片之外)。

### 3.2 这条链上的竞态清单(本片的核心难点)

| # | 竞态 | 防线 | 位置 |
|---|---|---|---|
| 1 | 快速 A→B→C,A 的迟到响应回写 | 请求令牌 `resumeRequestRef` + `isCurrentResume()` 在**每个 await 之后**复查 | `apps/desktop/src/app/session/hooks/use-session-actions/index.ts:547` 的 `isCurrentResume` |
| 2 | runtime id 被后端回收后复用,暖缓存指向另一条活会话 | `takeWarmCache` 的 `state.storedSessionId !== storedSessionId` 归属校验 + 双向清表 | 见跳 8 |
| 3 | 后台会话仍在流,写进共享 `$messages` | `syncSessionStateToView` 的 active id 门 + `flushPendingViewState` 再查一遍 | 见跳 10 |
| 4 | 切换瞬间还有一帧 RAF 待刷,刷下去就把新会话覆盖成旧的 | `resetViewSync()`:清 `pendingViewStateRef`、清 `viewSessionIdRef`、`cancelAnimationFrame` | `apps/desktop/src/app/session/hooks/use-session-state-cache.ts:150` 的 `resetViewSync` |
| 5 | 切线程时把上一条线程的本地错误行「嫁接」到新线程 | `viewSessionIdRef.current === pending.sessionId` 时才 `preserveLocalAssistantErrors` | `apps/desktop/src/app/session/hooks/use-session-state-cache.ts:189` 的 `const nextMessages =` |
| 6 | prop → ref 的镜像滞后一次 commit(#59305) | 在 **render 期间**用「prop 自身变了吗」的守卫同步镜像,而不是 `useEffect` | `apps/desktop/src/app/session/hooks/use-session-state-cache.ts:72` 的 `if (activeSessionIdPropRef.current !== activeSessionId) {` |
| 7 | 冷启动的首次 resume 被当成一次「导航」,把焦点/tab 归位到 workspace,踩掉持久化布局(⌘R 总是落回 main) | 一次性 `bootResumeRef` → `markSelectionRestore()` | `apps/desktop/src/app/session/hooks/use-route-resume.ts:163` 的 `if (bootResumeRef.current) {` |
| 8 | resume 终局失败后界面永久卡 loader | 有界退避重试(4 次,1s→8s)+ exhausted 闩锁 + 「点火时才计次」 | `apps/desktop/src/app/session/hooks/use-route-resume.ts:290` 的 `retryAttemptRef.current += 1` |
| 9 | `session.create` 往返几秒期间用户切走,新会话变孤儿 / 或误判为漂移 | `sessionContextDrift` 三探针(route / selection / composer),且**故意不把 active runtime ref 当探针** | `apps/desktop/src/app/session/hooks/session-context-drift.ts:73` 的 `export function sessionContextDrift({` |
| 10 | 自动压缩换了 stored id,路由/选择/草稿都要跟着走,但 A→B→C 期间 A 的迟到 `session.info` 不能把界面拽回 A | 消费式一次性事件 + 三重身份校验(runtime / selection / route)后才 `navigate(..., {replace:true})` | `apps/desktop/src/app/session/hooks/use-session-actions/index.ts:236` 的 `setActiveSessionStoredIdRotation(current => (current === storedIdRotation ? null : current))`(三重校验紧随其后,第 241–245 行) |
| 11 | 一条会话同时是主 tab 又是 tile,两个 pane 抢同一个 runtime | resume 入口处若发现它是 tile,先 `closeSessionTile` | `apps/desktop/src/app/session/hooks/use-session-actions/index.ts:573` 的 `if ($sessionTiles.get().some(t => t.storedSessionId === storedSessionId)) {` |
| 12 | 列表刷新把刚创建/刚 pin/刚结束的行冲掉 | `sessionsToKeep()` + `mergeSessionPage` + 乐观 tombstone | `apps/desktop/src/app/session/hooks/use-session-list-actions.ts:49` 的 `function sessionsToKeep(scope?: string): Set<string> {` |

### 3.3 滚动位置的保持

这一片对滚动位置的处理分三处,**都不是「记住 scrollTop 再还原」,而是「不要无谓地重排」**:

**(a) 心跳不重绘。** `session.info` 大约每秒一次,若无条件 publish,`$messages` 每次都换新引用,虚拟器重测量、视图跳动。所以 flush 前做**深度**内容等价比较(不是引用比较,因为暖恢复路径的 `reconcileAuthoritativeMessages` 必然生成新对象):

`apps/desktop/src/app/session/hooks/use-session-state-cache.ts:170 @ 863e313`

```ts
    // `preserveLocalAssistantErrors` always returns a fresh array, so publishing
    // it unconditionally puts a new `$messages` reference on the store every
    // flush — including the periodic `session.info` heartbeats that don't touch
    // the transcript. That churns ChatView → runtimeMessageRepository → the
    // assistant-ui runtime → the virtualizer, which re-measures and visibly
    // jerks the scroll position while the user is reading. Skip the publish when
    // the merged result is content-equivalent to what's already on screen.
```

**(b) 流式增量合批 + 自适应地板。** `STREAM_DELTA_FLUSH_MS = 33`,并按上一次 flush 的实测代价 ×3 抬高地板、上限 250ms(`apps/desktop/src/app/session/hooks/use-message-stream/index.ts` 第 265–270 行)。**关键细节**:代价必须包含 RAF 里那一帧的提交成本,否则地板会永远塌回 33ms(第 280–309 行)。

**(c) 侧栏自身的虚拟化。** 25 行以上才虚拟化,行高估计 28px、overscan 12;`getItemKey` 用「分隔行 key / 会话 id」而不是 index,这样插入一行不会让整窗错位:

`apps/desktop/src/app/chat/sidebar/virtual-session-list.tsx:66 @ 863e313`

```tsx
  const virtualizer = useVirtualizer({
    count: listRows.length,
    estimateSize: () => ROW_ESTIMATE_PX,
    getItemKey: index => {
      const row = listRows[index]

      return row ? (row.kind === 'divider' ? row.key : row.entry.session.id) : index
    },
    getScrollElement: () => scrollerRef.current,
    // jsdom-friendly default; the real rect takes over on first observe.
    initialRect: { height: 600, width: 240 },
    overscan: OVERSCAN_ROWS
  })
```

**旁证(本片之外,但正是本片被咬过的证据)**:仓库里有 8 个围着「切换 / 滚动 / 抖动」的 CDP 诊断脚本(`apps/desktop/scripts/diag-switch-autopsy.mjs`、`diag-switch-trace.mjs`、`diag-scroll-reset.mjs`、`diag-jump.mjs`、`diag-drag-churn.mjs`、`diag-drag-trace.mjs`、`diag-overlay-churn.mjs`、`click-session.mjs`)。其中 `diag-scroll-reset.mjs` 的头注释把「读旧消息时滚轮把视图甩走」定位成 **TanStack 测量补偿与浏览器原生 scroll anchoring 双重修正**,并给出 `overflow-anchor: none` 的验证方案:

`apps/desktop/scripts/diag-scroll-reset.mjs:1 @ 863e313`

```mjs
// Reproduce + diagnose the "scroll wheel resets position while reading" bug.
//
// The complaint (Windows, mouse wheel): scrolling UP through a chat to re-read
// older content randomly yanks the view to a different position, so you have to
// fight the scrollbar. Mac users on trackpads don't see it.
```

> 这 8 个脚本在 `apps/desktop/scripts/` 下,**不属于本片文件清单**,此处只作为「作者被这个问题咬过」的旁证引用。

---

## 4. 逐机制/逐区域

### 4.1 会话列表的取数:一次请求三片,签名门控换引用

`refreshSessions` 用**一次** `listSidebarSessions` 拿 recents / cron / messaging 三片(以前是三次 `listAllProfileSessions`,每次都把每个 profile 的 DB 重开一遍并重新 COUNT):

`apps/desktop/src/app/session/hooks/use-session-list-actions.ts:167 @ 863e313`

```ts
      const sessionProfile = profileScope === ALL_PROFILES ? 'all' : profileScope

      // Batched: one request opens each profile DB once and returns all three
      // source-scoped slices, instead of three separate listAllProfileSessions
      // calls that each reopened + re-counted every profile DB per refresh.
      const result = await listSidebarSessions({
        recentsProfile: sessionProfile,
        recentsLimit: limit,
        recentsExclude: SIDEBAR_EXCLUDED_SOURCES,
        cronLimit: CRON_SECTION_LIMIT,
        messagingLimit: MESSAGING_SECTION_LIMIT,
        messagingExclude: MESSAGING_EXCLUDED_SOURCES
      })
```

三处设计值得抄:

- **来源分流是两个互补的排除表**:recents 排除 `cron / kanban / subagent / tool` + 所有 messaging 源;messaging 片反过来排除 `cron` + 所有 local 源。两张表在同一个文件顶部相邻定义(第 38、41 行),所以「谁在哪」是一眼可读的。
- **`sessionsToKeep()` 是刷新的免死金牌**:在途首轮(`message_count` 为 0)、pinned、当前选中、刚刚结算的会话都必须保留 —— 否则聚合器一句「这一页里没有」就能把用户眼前的行删掉。
- **签名门控**:`sameCronSignature(prev, next) ? prev : next` —— 内容没变就**保持数组引用不变**,否则侧栏里每一个 `useMemo` 都会因为 `$sessions` 换引用而重算,整列每轮重渲染一次。

分页也是 scope-aware 的:`hasMoreSessions` 在 ALL 模式看「有没有任一 profile 被截断」,在具体 scope 下只看那个 profile 的截断位 —— 否则一个巨大的 default profile 会让你在小 profile 里永远看到「Load more」。

`onLoadMoreRecents` 还有一层:因为 recents 会被前端二次过滤(项目内会话不进 flat 列表),后端一页 50 条可能只多出 3 条可见行,所以它**最多循环 6 次**直到真的多出一页可见行、或后端窗口不再增长(`apps/desktop/src/app/chat/sidebar/index.tsx` 第 1006–1042 行)。

### 4.2 排序:三层叠加,新东西的位置是刻意设计过的

flat 会话列表的顺序 = `recency 排序` → `pin 摘除` → `手工顺序覆盖`。手工顺序覆盖的关键是「持久顺序里没有的 id 放哪」:

`apps/desktop/src/app/chat/sidebar/order.ts:26 @ 863e313`

```ts
export function orderByIds<T>(items: T[], getId: (item: T) => string, orderIds: string[]): T[] {
  if (!orderIds.length) {
    return items
  }

  const byId = new Map(items.map(item => [getId(item), item]))
  const seen = new Set<string>()
  const ordered: T[] = []

  for (const id of orderIds) {
    const item = byId.get(id)

    if (item) {
      ordered.push(item)
      seen.add(id)
    }
  }

  // Items missing from the persisted order are new since it was last
  // reconciled. Callers pass recency-sorted lists (newest first), so surface
  // these at the TOP instead of burying them beneath the saved order —
  // otherwise a brand-new session sinks to the bottom of the sidebar and reads
  // as "my latest session never showed up".
  const fresh = items.filter(item => !seen.has(getId(item)))

  return fresh.length ? [...fresh, ...ordered] : ordered
}
```

而**项目总览用的是另一套**,故意不置顶:

`apps/desktop/src/app/chat/sidebar/projects/model.ts:87 @ 863e313`

```ts
// Layer the user's manual drag-order over the deterministic sort.
//
// This can't just be `orderByIds`: that surfaces every id missing from the saved
// order at the TOP, which is right for sessions (a new chat should not sink) but
// wrong here. The overview also lists repos found by the disk scan that have
// zero Hermes sessions, and those arrive continuously — so once the user dragged
// anything, every freshly-scanned checkout jumped above the projects they
// actually work in.
```

**同一个「持久顺序 + 新元素」问题,两个数据源给出相反的答案**,并且都在注释里写清了理由。这是本片最值得抄的一处设计纪律。

### 4.3 pin 的身份问题

pin 存的是 **lineage 根 id**(自动压缩会把会话轮到新的 stored id),但列表行拿的是活 id。于是三处都要翻译:

- 索引:`buildSessionByAnyId` 把每条会话同时挂在活 id 与 lineage 根下,并让 recents **最后写入、赢得直接 id 冲突**。
- 判定「这条会话被 pin 了吗」:活 id 与 `sessionPinId(session)` 两边都查(`apps/desktop/src/app/chat/sidebar/index.tsx` 第 429–432 行)。
- 重排 pin:先把行上的活 id 翻译回 `sessionPinId` 再落盘(第 1106–1113 行)。

漏掉索引不只是「行错位」,而是**会话从侧栏彻底消失** —— 因为被 pin 的会话已经从它自己的分区里过滤掉了:

`apps/desktop/src/app/chat/sidebar/session-index.ts:3 @ 863e313`

```ts
/**
 * Index sessions by every id a pin might be stored under.
 *
 * The sidebar fetches three independent slices — recents, cron, and messaging
 * — and renders the latter two in self-managed sections. Any of them can be
 * pinned, so all three must be indexed here or the Pinned section can't
 * resolve the pin to a row. A pinned session is also filtered out of its own
 * section, so failing to index it doesn't merely misplace the row: it removes
 * the session from the sidebar entirely.
 *
 * Each session is keyed under both its live id and its lineage root, so a pin
 * stored before an auto-compression still resolves to the live continuation
 * tip. Recents are indexed last and win a direct id collision.
 */
```

### 4.4 项目树:后端算归属,前端只做视觉叠加

三条边界被反复写死在注释里:

1. **membership 永远是后端 `projects.tree` 的**;前端只叠加本地视图态(dismiss、顺序、总览排序)。
2. **`git worktree list` 只是视觉增强器**:注入**空** lane,让一个还没有 Hermes 会话的分支也出现;绝不增删会话行(`mergeRepoWorktreeGroups`)。
3. **实时叠加是 additive-only 的乐观层**(Apollo 风格),下一次快照刷新会把它对账掉(`overlayRepoLanes` / `overlayLiveLanes` / `overlayLivePreviews`)。

刷新时机也被刻意收窄:**只在结构性边缘刷**(进入分组视图 / 切 profile / gateway 重连 / 窗口重新聚焦,加上每次运行一次的磁盘扫描,窗口聚焦扫描节流 30s),因为一轮对话结束不该触发一次 `list_sessions_rich` 重扫(`apps/desktop/src/app/chat/sidebar/index.tsx` 第 537–592 行)。

lane 排序有 4 个层级(`laneRank`):home(repo 主检出,按**实时分支**命名)→ trunk(`main`/`master`/`trunk`/`develop`)→ 普通分支/worktree → kanban 聚合桶。kanban 任务 worktree(`<repo>/.worktrees/t_<hex>`)全部折叠进一个 lane —— 注释直说,把 `git worktree list` 的每一项都列出来「正是把侧栏炸到几百个空行的原因」。

### 4.5 一个 `session.title` 重命名为什么要绕过 REST

`renameSessionPreferringRpc` 是本片里「身份不是小事」的一个浓缩案例:

- 刚 branch 出来的(以及任何全新的)会话**只存在于 gateway 的内存 map 里**,按 runtime id 索引;首轮之前 `state.db` 没有行。
- `PATCH /api/sessions/{id}` 按 stored 表解析 → 对这些会话 404。
- `session.title` RPC 能解析活 runtime **并按需落盘**,所以它成功。
- 但 RPC 只用于**当前选中的**那一行(runtime id 已知、且它就在活 gateway 上,没有 profile 路由歧义);其它行、以及「清空标题」(RPC 拒绝空标题)一律走 REST。

### 4.6 Quick Entry:一个没有 gateway 的渲染进程

`quick-entry-app.tsx` 的形状值得单独记:整个窗口**不连 gateway、不装 router、不挂 app shell**;它对后端真相的全部认知(连没连上、最近有哪些会话)由主渲染进程经 main 推进来(`onState`),文本也顺原路回到主渲染进程的正常提交路径。所有行为都在纯 reducer `quickComposerReducer` 里,组件只负责执行副作用。

这是「把一个 UI 表面从 harness 里剥出来单测」的最干净示范:空提交既不发送也不隐藏窗口、Escape 与失焦只关不发、gateway 挂了输入框直接禁用 —— 三条都是 reducer 的返回值,不需要 Electron。

---

## 5. 文档与代码的出入

### ◎ 1 —— 「Search sessions by id」显著保守

文档来源:`website/docs/user-guide/desktop.md`,H2 **「## What's in the app」**(第 35 行)下的 H3 **「### Sessions & profiles」**(第 163 行),整条 bullet 是:

`website/docs/user-guide/desktop.md:166 @ 863e313`

> - **Search sessions by id** — find a specific session directly by its id.

**字面为真,所以不是 ▲**。但侧栏搜索框实际做两件事:

(a) 已加载会话的**客户端多字段匹配** —— id、lineage 根、标题、preview、cwd、git 分支、来源别名:

`apps/desktop/src/lib/session-search.ts:7 @ 863e313`

```ts
export function sessionMatchesSearch(session: SessionInfo, query: string): boolean {
  const needle = normalize(query)

  if (!needle) {
    return true
  }

  return [
    session.id,
    session._lineage_root_id ?? '',
    sessionTitle(session),
    session.preview ?? '',
    session.cwd ?? '',
    session.git_branch ?? '',
    ...sessionSourceSearchTerms(session.source)
  ].some(value => value.toLowerCase().includes(needle))
}
```

(b) 200ms 防抖后的**服务端 FTS5 全文检索**(检索的是消息正文),结果合并在客户端命中之后:

`apps/desktop/src/app/chat/sidebar/index.tsx:470 @ 863e313`

```tsx
  const searchResults = useMemo(() => {
    if (!trimmedQuery) {
      return []
    }

    const out = new Map<string, SessionInfo>()

    for (const s of sortedSessions) {
      if (sessionMatchesSearch(s, trimmedQuery)) {
        out.set(s.id, s)
      }
    }

    for (const match of serverMatches) {
      if (out.has(match.session_id)) {
        continue
      }

      const loaded = sessionByAnyId.get(match.session_id)
      out.set(match.session_id, loaded ?? searchResultToSession(match))
    }

    return [...out.values()]
  }, [trimmedQuery, sortedSessions, serverMatches, sessionByAnyId])
```

即:文档说的是「按 id 找」,实现是「按 id、标题、预览、cwd、分支、来源 **以及全文消息内容** 找」。记 **◎**。

### ◇ 2 —— 侧栏行与 nav 行的「Open in split」在任何文档里都没有

代码:侧栏的每个内置 nav 行(new-session、Skills、Messaging、Artifacts)与**每个插件贡献的 nav 行**都被包进右键 `ContextMenu` + `SplitSubmenu`,右键可把该页/新会话开成方向分屏(`apps/desktop/src/app/chat/sidebar/index.tsx` 第 1196–1214 行);会话行本身也有 `CONTEXT_SPLIT_KIT` 这一路(`split-submenu.tsx` 第 33–38 行,4 个方向:right / bottom / left / top,默认 right)。

**搜索面(负结论的成本)**:在派工书 §4 声明的全部文档来源上跑

```verify
cd /home/user/hermes-agent && grep -rniE "split" README.md AGENTS.md \
  apps/desktop/AGENTS.md apps/desktop/DESIGN.md apps/desktop/README.md website/docs/ \
  | grep -viE "split(ting)? (the|a|out|into|up|by|on)|\.split\(|splitlines"
```

24 条命中全部是无关语义(消息分片、上下文压缩边界、prompt 组装的 head/tail 切分、PDF split 技能、`HSplit` 布局控件、slash 权限的 admin/user split、`OverlaySplitLayout`)。**没有任何一条描述会话行/nav 行的方向分屏**。桌面用户指南的「Windows, tabs & panes」一节(`website/docs/user-guide/desktop.md:99-101`)只讲了 tab、window、以及 `Cmd/Ctrl+B` / `+J` / `+\` 三个侧栏开关,没有分屏。记 **◇**。

*(说明:插件 SDK 文档 `website/docs/developer-guide/desktop-plugin-sdk.md` 第 203 行与 245–270 行详述了 `SIDEBAR_NAV_AREA` 的 `data: { path, label, codicon }` 契约,与代码一致(`codicon` 缺省回落 `'plug'`),但同样没提贡献的 nav 行会自动获得分屏右键菜单。)*

---

## 6. 缺陷

### ■ 1 —— 「All profiles」视图下的会话搜索是静默半覆盖

**现象。** 侧栏搜索框在 ALL-profiles 作用域下,客户端一半覆盖**所有** profile(列表本身就是 `recentsProfile: 'all'` 拉来的,见 §4.1),服务端 FTS 一半只覆盖**活动 gateway 那一个 profile**。落在另一个 profile 上、且不在已加载页里的会话,搜不到 —— 而 UI 给出的是一个确定的「no match」空态(`apps/desktop/src/app/chat/sidebar/index.tsx` 第 1247–1249 行)。

**证据链。** 桌面侧调用不带任何 profile / limit 参数:

`apps/desktop/src/hermes.ts:613 @ 863e313`

```ts
export function searchSessions(query: string): Promise<SessionSearchResponse> {
  return window.hermesDesktop.api<SessionSearchResponse>({
    path: `/api/sessions/search?q=${encodeURIComponent(query)}`
  })
}
```

后端端点**支持** `profile` 与 `limit`(默认 20、上限 100):

`hermes_cli/web_routers/sessions.py:166 @ 863e313`

```py
@search_router.get("/api/sessions/search")
async def search_sessions(
    q: str = "",
    limit: int = 20,
    profile: Optional[str] = None,
    source: str = None,
    sources: str = None,
    exclude_sources: str = None,
):
```

而 `profile` 为空时打开的是**本进程自己的** `state.db`,并且这个函数没有 `'all'` 模式 —— 它按构造只能开一个库:

`hermes_cli/web_server.py:11225 @ 863e313`

```py
    if profile:
        _name, home = _cron_profile_home(profile)
        db_path = Path(home) / "state.db"
    else:
        db_path = Path(_default_db_path())
```

**为什么说这是缺陷而不是设计。** 同一段代码把搜索结果分区渲染成 `showProfileTags={showAllProfiles}`(`apps/desktop/src/app/chat/sidebar/index.tsx:1263`)—— 即作者明确预期 ALL 视图下的搜索结果**是跨 profile 混合的**,才需要给每行标 profile。否则那个标签恒等于当前 profile,没有信息量。

**附带的第二个口径问题。** 不传 `limit` ⇒ 服务端默认 20 条。而这段代码的注释写的是「Full-text search across *all* sessions (not just the loaded page) so 699 sessions stay findable」(第 434–436 行)。20 条上限本身不与「不止当前页」矛盾,但在 699 条量级下,一个常见词的 FTS 命中会被截到 20 条且**没有任何截断提示**。

**搜索面。** `grep -rn "sessions/search"` 全仓(排除 `node_modules`)共 7 处命中:`web/src/lib/api.ts:815`(Web 面板,同样不传 profile)、`hermes_cli/web_routers/sessions.py`(定义 + 日志)、`hermes_cli/web_server.py:11142`(注释)、`tests/hermes_cli/test_web_server_session_search.py`、`apps/desktop/src/hermes.ts:615`。**桌面端没有第二个调用点。**

### ■ 2 —— `resumeSession` 的第二个位置参数是死参数,且接缝两侧对它的命名相反

`resumeSession` 声明了 `replaceRoute = false`:

`apps/desktop/src/app/session/hooks/use-session-actions/index.ts:540 @ 863e313`

```ts
  const resumeSession = useCallback(
    async (storedSessionId: string, replaceRoute = false) => {
```

但函数体**从不读它** —— `resumeSession` 根本不调用 `navigate`。全文件里 `replaceRoute` 只出现 5 次,其中 4 次属于**另一个**函数 `startFreshSessionDraft` 的选项:

```verify
cd /home/user/hermes-agent && grep -n "replaceRoute" \
  apps/desktop/src/app/session/hooks/use-session-actions/index.ts
# 190:  replaceRoute?: boolean                       <- FreshSessionDraftOptions
# 283:  const draftOptions = ...                     <- startFreshSessionDraft
# 285:  const replaceRoute = draftOptions.replaceRoute ?? false
# 307:  navigate(NEW_CHAT_ROUTE, { replace: replaceRoute })
# 541:  async (storedSessionId: string, replaceRoute = false) => {   <- 声明后未再出现
```

更糟的是接缝**另一侧**给同一个位置参数起了完全不同的名字:

`apps/desktop/src/app/session/hooks/use-route-resume.ts:13 @ 863e313`

```ts
  gatewayState: string | undefined
  locationPathname: string
  resumeSession: (sessionId: string, focus: boolean) => Promise<unknown>
```

三个调用点都传 `true`,各自按自己那侧的名字理解它:

```verify
cd /home/user/hermes-agent && grep -rn "resumeSession(" apps/desktop/src \
  --include=*.ts --include=*.tsx | grep -v "\.test\." | grep -v resumeStoredSession
# apps/desktop/src/app/contrib/wiring.tsx:897:    onRetryResume: sessionId => void resumeSession(sessionId, true),
# apps/desktop/src/app/session/hooks/use-route-resume.ts:168:        void resumeSession(routedSessionId, true)
# apps/desktop/src/app/session/hooks/use-route-resume.ts:291:      void resumeSession(sessionId, true)
```

**影响**:目前无功能后果(恢复本来就不导航),但这是一个「看起来控制历史栈行为、实际什么都不控制」的 API。任何以后想让恢复 `replace` 路由的人,会以为已经接好了。

**搜索面**:上面两条 grep 覆盖 `apps/desktop/src` 全部 `.ts`/`.tsx`,排除了 `*.test.*` 与同名不同义的 `resumeStoredSession`;`resumeSession` 未被跨包导出(`use-session-actions/index.ts` 只导出 `useSessionActions` 这一个符号)。

---

## 7. 测试(行为规格)

本片相关的 vitest 文件 20 个(19 个在片内目录下 + `src/store/session-switcher.test.ts`),全部在 `ui` project(jsdom):

```console
$ cd /home/user/r10b-ts/hermes-agent/apps/desktop && npx vitest run --project ui \
    src/app/chat/sidebar/*.test.*      # 9 files
 Test Files  9 passed (9)
      Tests  34 passed (34)

$ npx vitest run --project ui src/app/session/hooks/*.test.* src/store/session-switcher.test.ts
 Test Files  11 passed (11)
      Tests  140 passed (140)
```

**合计 passed=174 / failed=0 / skipped=0。**

**零执行核对(逐文件点名)。** 无 `describe.skip` / `it.skip` / `test.skip` / `.todo(`;每个文件的 `it(`/`test(` 声明数与执行数逐一相等,合计正好 174,故**没有任何文件被静默跳过或零执行**:

```verify
cd /home/user/hermes-agent/apps/desktop && \
  grep -rn "describe\.skip\|it\.skip\|test\.skip\|\.todo(" \
  src/app/chat/sidebar/*.test.* src/app/session/hooks/*.test.* src/store/session-switcher.test.ts
# (无输出)
cd /home/user/hermes-agent/apps/desktop && for f in src/app/chat/sidebar/*.test.* \
  src/app/session/hooks/*.test.* src/store/session-switcher.test.ts; do \
  grep -cE "^\s*(it|test)\(" "$f"; done | paste -sd+ | bc
# -> 174
```

逐文件用例数:

| 文件 | 用例 | 文件 | 用例 |
|---|---|---|---|
| `sidebar/load-more-row.test.tsx` | 4 | `hooks/preview-open.test.tsx` | 9 |
| `sidebar/order.test.ts` | 10 | `hooks/session-context-drift.test.ts` | 16 |
| `sidebar/project-dialog.test.tsx` | 2 | `hooks/use-background-queue-drain.test.tsx` | 8 |
| `sidebar/session-actions-menu.test.ts` | 5 | `hooks/use-cwd-actions.test.tsx` | 1 |
| `sidebar/session-actions-menu.test.tsx` | 1 | `hooks/use-hermes-config.test.ts` | 7 |
| `sidebar/session-index.test.ts` | 4 | `hooks/use-model-controls.test.tsx` | 19 |
| `sidebar/session-row-state.test.ts` | 3 | `hooks/use-route-resume.test.tsx` | 13 |
| `sidebar/session-row.test.tsx` | 3 | `hooks/use-session-actions.test.tsx` | 40 |
| `sidebar/sessions-section.test.tsx` | 2 | `hooks/use-session-list-actions.test.tsx` | 8 |
| — | — | `hooks/use-session-state-cache.test.tsx` | 12 |
| — | — | `store/session-switcher.test.ts` | 7 |

**测试覆盖的形状说明了什么。** 174 个用例里,`use-session-actions`(40)+ `use-model-controls`(19)+ `session-context-drift`(16)+ `use-route-resume`(13)+ `use-session-state-cache`(12)= **100 个,占 57%**,全部集中在「切换 / 竞态 / 身份」这一小撮文件上;而侧栏那 28 个视图文件加起来只有 34 个用例、且几乎全是纯函数(`order` 10、`session-actions-menu` 5+1、`session-index` 4、`session-row-state` 3)。**作者把测试预算压在了竞态与身份上,视图基本靠人眼**——这与 §3.2 的竞态清单、以及 §3.3 提到的 8 个 CDP 诊断脚本是同一个判断的两面。

**未跑的部分(据实报)**:`e2e/` 的 Playwright spec 需要真 Electron,本次未跑;`apps/desktop/scripts/diag-*.mjs` 需要一个开着远程调试端口的运行中桌面应用,本次未跑。

---

## 8. 判据自查

| # | 判据 | 自评 | 说明 |
|---|---|---|---|
| **1 点名到位** | 每个文件至少一次全路径 + 一句话角色 | **达标** | §0 分 10 组共 55 行,全部写全路径。两处导航性占位行已在紧邻处显式说明所指(0.3 表首行、0.10 表中段)。 |
| **2 接缝穷举** | 每个对外接缝逐项列全 + 机械枚举命令 + 条数 | **约 8 成** | 已穷举:sidebar props 13、section props 40 + 8 分支、layout store 面 29 / 持久键 13、openSession intent 4、行手势 8、动作菜单全项、gateway 事件 47+3、hook 返回面 6 张表、slice 导出 192、projects barrel 15。**未穷举**:profile 轨动作面、slash 命令表、submit 管线错误分支(已在 §2.11 列名)。 |
| **3 端到端链** | 至少一条链逐跳带锚点 | **达标** | §3.1 共 11 跳,跨 6 个文件 + 2 个 store;§3.2 另附 12 条竞态与其防线锚点。 |
| **4 逐字取证** | ≥2 个围栏块是逐字源码 | **达标** | 逐字源码围栏块 19 个(tsx/ts 16、py 2、mjs 1),另有 8 个 ```verify / ```console / ```text 声明式非源码块。 |
| **5 记号** | ≥1 条 ■/▲/◇/◎ 带锚点 | **达标** | ◎ 1(桌面用户指南的「按 id 搜索」bullet 对比实际的多字段 + FTS 实现)、◇ 1(分屏菜单无文档,附 grep 搜索面)、■ 2(ALL 视图搜索半覆盖;`replaceRoute` 死参数 + 接缝两侧命名相反)。 |

**未达标处不粉饰**:判据 2 的三处缺口如上;此外 `profile-switcher.tsx`(748 行)、`slash.ts`(1,087 行)、`submit.ts`(747 行)、`use-prompt-actions/index.ts`(962 行)四个文件只读到**接口面 + 依赖面**,未读实现体(这符合 L2,但意味着它们的内部分支面没有被枚举)。

---

## 9. 移交项

| 编号 | 锚点 + 摘录 | 一句话现象 |
|---|---|---|
| H-R10B-B-a | `apps/desktop/src/hermes.ts:613`:`export function searchSessions(query: string): Promise<SessionSearchResponse> {` | 桌面 FTS 搜索不传 `profile` 也不传 `limit`,于是 ALL-profiles 视图下只搜活动 profile、且被服务端默认 20 条截断而无提示(见 ■1)。需要确认:后端有没有可用的跨 profile 搜索路径,还是必须前端 fan-out。 |
| H-R10B-B-b | `apps/desktop/src/app/session/hooks/use-session-actions/index.ts:541`:`async (storedSessionId: string, replaceRoute = false) => {` | 第二个位置参数声明后从未被读;接缝另一侧把它叫 `focus`(`apps/desktop/src/app/session/hooks/use-route-resume.ts:15`:`resumeSession: (sessionId: string, focus: boolean) => Promise<unknown>`)。三个调用点都传 `true`(见 ■2)。 |
| H-R10B-B-c | `apps/desktop/src/app/session/hooks/use-session-list-actions.ts:59`:`const session = scope ? $sessions.get().find(s => s.id === active) : null` | `sessionsToKeep(scope)` 用严格 `s.id === active` 定位当前选中行,而本片其它地方一律用 `sessionMatchesStoredId`(兼容 lineage 根)。**未验证**:压缩换 id 后这里会不会漏保护当前行。 |
| H-R10B-B-d | `apps/desktop/src/app/chat/sidebar/index.tsx:204`:`function searchResultToSession(result: SessionSearchResult): SessionInfo {` | 合成的搜索结果行不带 `profile` 字段(`SessionSearchResult` 类型里也没有),而搜索分区在 ALL 视图下传 `showProfileTags`。**未验证**:这类行的 `ProfileTag` 渲染成什么。 |
| H-R10B-B-e | `apps/desktop/src/app/chat/sidebar/sessions-section.tsx:454`:`interface SortableSessionRowProps {` | 该接口比 `renderRow` 实际展开的 `rowProps` 窄(缺 `branchStem` / `onBranch` / `reorderable` / `showProfile`),靠 JSX spread 绕过多余属性检查。当前无功能后果,但接口不再描述真实契约。 |
| H-R10B-B-f | `apps/desktop/src/app/session/hooks/use-prompt-actions/slash.ts:153`:`export function useSlashCommand(deps: SlashCommandDeps) {` | 本片对该文件(1,087 行)只做了接口面阅读,**斜杠命令表未穷举**;命令表本体在 `apps/desktop/src/lib/desktop-slash-commands.ts`(不在本片清单里),需要由覆盖该文件的片或后续轮次接手。 |
| H-R10B-B-g | `apps/desktop/scripts/diag-scroll-reset.mjs:1`:`// Reproduce + diagnose the "scroll wheel resets position while reading" bug.` | 8 个围绕「切换/滚动/抖动」的 CDP 诊断脚本在 `apps/desktop/scripts/` 下,**不属于本片清单**,但它们记录的正是本片机制被咬过的真实事故;建议覆盖 `scripts/` 的片把这 8 个脚本的结论并回会话视图这一簇。 |

---

## 10. 本片成本自报

```text
片号            : B
层              : L2
文件数 / 行数   : 55 / 18,761
实际打开的文件数: 46
                  (完整读:38;部分读 4 —— profile-switcher.tsx 前 200 行、
                   worktree-dialog.tsx 前 120 行、slash.ts 前 70 行、
                   use-prompt-actions/index.ts 约 200 行;
                   仅按符号面 grep 未逐行读:submit.ts;
                   另有 8 个薄文件通过一次性批量读覆盖。
                   9 个文件只读到导出/结构层:profile-switcher 的 7 个内部组件、
                   worktree-dialog 的对话框主体等。)
实际读过的行数  : 约 13,500
                  (估法:完整读的 38 个文件按其行数加总 ≈ 11,900;
                   4 个部分读文件按实读区间加总 ≈ 600;
                   片外为追链读的 wiring.tsx / session-states.ts / routes.ts /
                   store/layout.ts / store/profile.ts / hermes.ts /
                   web_routers/sessions.py / web_server.py 片段 ≈ 1,000。)
底稿字节数      : (主线自测)
主观耗费        : 中偏高。瓶颈是**跨文件追链 + 概念密度**,不是行数:
                  55 个文件里真正难的只有 6 个(use-session-actions/index.ts、
                  同目录 utils.ts、use-session-state-cache.ts、use-route-resume.ts、
                  gateway-event.ts、sidebar/index.tsx),但这 6 个互相咬合,
                  一条 resume 链要在它们之间来回跳 11 次才能读通;
                  且每一处异步都带一个自己的代际号/令牌/ref 快照,
                  必须逐个确认「这个守卫防的是哪一种交错」才敢下判断。
                  剩下 49 个文件多为薄视图件,单位成本很低。
```

---

## 附:本片用到的全部核对命令汇总

```verify
cd /home/user/hermes-agent
# 片规模
n=0; t=0; while read -r f; do n=$((n+1)); t=$((t+$(wc -l < "$f"))); done \
  < /home/user/hermes-study/data/r10b/slices/B.txt; echo "$n / $t"          # 55 / 18761
# ChatSidebar props
awk '/^interface ChatSidebarProps/,/^}/' apps/desktop/src/app/chat/sidebar/index.tsx \
  | grep -cE '^  [a-zA-Z]'                                                  # 13
# SidebarSessionsSection props
awk '/^interface SidebarSessionsSectionProps/,/^}/' \
  apps/desktop/src/app/chat/sidebar/sessions-section.tsx | grep -cE '^  [a-zA-Z]'   # 40
# sessions-section 渲染分支
awk 'NR>=316 && NR<=427' apps/desktop/src/app/chat/sidebar/sessions-section.tsx \
  | grep -cE "^  (if \(|\} else)"                                           # 8
# 侧栏消费的 layout store 面
awk '/^import \{$/{start=NR} {L[NR]=$0} /^\} from .@\/store\/layout.$/{for(i=start+1;i<NR;i++) print L[i]}' \
  apps/desktop/src/app/chat/sidebar/index.tsx | grep -cE '^  [A-Za-z$]'     # 29
# 持久化键
grep -cE "^const SIDEBAR_[A-Z_]*_STORAGE_KEY = " apps/desktop/src/store/layout.ts   # 13
# gateway 事件表
{ grep -oE "event\.type === '[a-zA-Z._]+'" \
    apps/desktop/src/app/session/hooks/use-message-stream/gateway-event.ts \
    | sed "s/.*'\(.*\)'/\1/"; \
  awk '/^export const SUBAGENT_EVENT_TYPES/,/\]\)/' \
    apps/desktop/src/app/session/hooks/use-message-stream/utils.ts \
    | grep -oE "'[a-z._]+'" | tr -d "'"; } | sort -u | wc -l                # 47
grep -oE "event\.type === '[a-z.]+'" \
  apps/desktop/src/app/session/hooks/use-preview-routing.ts | sort -u | wc -l       # 3
# 本片导出总面
while read -r f; do \
  grep -cE "^export (async )?(function|const|type|interface|class) |^export \{|^export \*" "$f"; \
done < /home/user/hermes-study/data/r10b/slices/B.txt | paste -sd+ | bc     # 192
# wiring.tsx 里接进来的本片 hook
grep -cE "^import \{[^}]*\} from '\.\./session/(hooks/|workspace-session-target)" \
  apps/desktop/src/app/contrib/wiring.tsx                                   # 13
```
