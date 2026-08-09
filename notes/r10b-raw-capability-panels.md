# r10b 片 H · 能力面板 —— 插件、技能、贡献、星图与命令面板(底稿)

> 层:**L2(结构级理解 —— 读接口面,不读实现体)**。
> 范围:`data/r10b/slices/H.txt` 列的 **66 文件 / 20,165 行**,全部在
> `/home/user/hermes-agent/apps/desktop/src/` 下。
> 溯源约定:凡对基线行为的断言,锚点写成 `路径:行号 @ 863e313`,**单独成行、置于代码块之前**。
> 本片以外的文件(`src/sdk/`、`src/store/`、`hermes_cli/`、`tools/`)只在追链时引用,不计入点名。

---

## 0. 本片范围与逐文件点名(判据 1)

66 个文件按**七簇**分组;组内逐个列全路径。

### 0.1 贡献框架内核 `src/contrib/`(12 文件 / 1,183 行)

桌面端的「插件 ABI」本体:一个按 area 分桶的注册表 + 一份插件作者契约 + 一条运行时加载管线。

| 全路径 | 行 | 一句话角色 |
|---|---|---|
| `apps/desktop/src/contrib/index.ts` | 6 | 公共出口桶,只导出 `Slot` / `useContributions` / `registry` / 两个类型 |
| `apps/desktop/src/contrib/types.ts` | 43 | `Contribution` 单一原语的字段定义(id / area / source / order / when / enabled / render / data) |
| `apps/desktop/src/contrib/registry.ts` | 162 | `ContributionRegistry` 单例:按 area 分桶、按 area 失效快照、两级订阅通道 |
| `apps/desktop/src/contrib/events.ts` | 45 | 插件面向网关事件流的旁路水龙头(`onGatewayEvent` / `emitGatewayEvent`),监听器互相隔离 |
| `apps/desktop/src/contrib/plugin.ts` | 180 | 插件作者契约:`HermesPlugin` 接口 + `createPluginContext`(命名空间化 id、盖 source 戳、storage/os/rest/socket/i18n) |
| `apps/desktop/src/contrib/plugins.ts` | 74 | **打包插件**发现:vite glob 扫 `src/plugins/*/plugin.{ts,tsx}`,一次性守卫,末尾启动磁盘门 |
| `apps/desktop/src/contrib/plugins-store.ts` | 124 | 插件清单 nanostore:记录表 + 用户显式启停决策(v2 键,含 v1 迁移)+ loader 交出的 activate/deactivate 句柄 |
| `apps/desktop/src/contrib/runtime-loader.ts` | 395 | **运行时插件**管线:integrity → 裸 specifier 重写 → blob `import()` → 校验默认导出 → register;外加 fs 监视的磁盘门与轮询兜底 |
| `apps/desktop/src/contrib/react/slot.tsx` | 26 | `<Slot area>`:把一个 area 的贡献按序内联渲染,每项包 `ContribBoundary` |
| `apps/desktop/src/contrib/react/use-contributions.ts` | 14 | `useSyncExternalStore` 订阅**单个** area,避免跨 area 重渲染 |
| `apps/desktop/src/contrib/react/contribute.tsx` | 51 | `<Contribute>`「反向 portal」:挂载期间把 children 投影进目标 area,卸载即注销 |
| `apps/desktop/src/contrib/react/boundary.tsx` | 59 | `ContribBoundary` 错误隔离墙:chip / pane 两种降级形态 |

### 0.2 应用外壳装配 `src/app/contrib/`(14 文件 / 3,443 行)

把上面的框架接到真实应用上:注册核心 pane/布局/命令,再把数据控制器与四张已接线表面发布下去。

| 全路径 | 行 | 一句话角色 |
|---|---|---|
| `apps/desktop/src/app/contrib/index.ts` | 7 | 目录出口:只公开 `ContribController`,其余内部 |
| `apps/desktop/src/app/contrib/types.ts` | 79 | `WiringActions`(控制器拥有的全部回调面)与 `WiringApi`(四张表面)的类型契约 |
| `apps/desktop/src/app/contrib/context.tsx` | 36 | `ContribWiringContext` + `WiredPane`(按 key 取回一张已接线表面,memo 在 `part` 上) |
| `apps/desktop/src/app/contrib/latest-actions.ts` | 73 | 稳定包装器:字段就地变更的 actions 包,调用时才解引用最新闭包;可选 handler 保持可选 |
| `apps/desktop/src/app/contrib/controller.tsx` | 768 | **应用根**:注册 5 个核心 pane、4 个布局预设、9 条命令面板行、1 条 keybind,调 `discoverBundledPlugins()`,渲染标题栏 slot + 布局树 + 状态栏 |
| `apps/desktop/src/app/contrib/wiring.tsx` | 1123 | 数据控制器:整条 hook 链、网关事件先喂插件后喂应用、标题栏工具贡献读取、DEV 演示安装 |
| `apps/desktop/src/app/contrib/surfaces.tsx` | 192 | 四张 memo 化表面(sidebar / chatRoutes / terminal / statusbar);路由表把 `routes` area 的贡献挂成真页面 |
| `apps/desktop/src/app/contrib/panes.tsx` | 179 | 真数据 pane(logs / files / review)+ 状态栏与标题栏工具贡献的收集器 + `registryGroupSetter` 页面桥 |
| `apps/desktop/src/app/contrib/hooks/use-background-sync.ts` | 407 | 网关开启期间的兜底轮询与 `sessions.changed` 重播(含 `rehydrateLiveSessionStatuses` 的收割逻辑) |
| `apps/desktop/src/app/contrib/hooks/use-desktop-integrations.ts` | 242 | 全部 Electron 主进程 / OS / 跨窗集成:更新轮询、⌘W、深链、通知点击、记忆路由恢复 |
| `apps/desktop/src/app/contrib/hooks/use-pet-bridge.ts` | 68 | 弹出宠物覆盖窗回接:提交、缩放、打开最近会话,以及「有会话在等你」的姿态镜像 |
| `apps/desktop/src/app/contrib/hooks/use-quick-entry-bridge.ts` | 128 | 全局热键速记窗双向桥:文本按 target 路由进正常提交管线,网关状态与近期会话推给该窗 |
| `apps/desktop/src/app/contrib/hooks/use-session-tile-delegate.ts` | 121 | 发布会话瓦片委托(resume/submit/interrupt/slash/archive/branch/delete),不动主视图 |
| `apps/desktop/src/app/contrib/dev/credits-notice-demo.ts` | 128 | **仅 DEV**:合成 `notification.show/clear` 事件走真分发器;装一条 ⌘K 行 + Ctrl+Shift+C + `window.__creditsDemo()` |

### 0.3 技能/能力面板 `src/app/skills/`(4 文件 / 2,987 行)

| 全路径 | 行 | 一句话角色 |
|---|---|---|
| `apps/desktop/src/app/skills/index.tsx` | 824 | Capabilities 页四个 tab 的壳:Skills / Toolsets 列表 + 单个与批量开关 + 学得技能的 SKILL.md 编辑与归档 |
| `apps/desktop/src/app/skills/hub.tsx` | 468 | Hub tab:多 hub 源并行搜索、结果按信任级去重、预览、按需安全扫描、安装/卸载/全量更新 + 动作日志尾巴 |
| `apps/desktop/src/app/skills/mcp-tab.tsx` | 1689 | MCP tab:`mcp.json` 文档编辑器 + 服务器整表替换保存、逐服务器与逐工具开关、探测、OAuth、目录安装、日志 |
| `apps/desktop/src/app/skills/store.ts` | 6 | 两个持久化排序方向 atom(skills / toolsets 各一) |

### 0.4 命令面板 `src/app/command-palette/`(4 文件 / 1,810 行)

| 全路径 | 行 | 一句话角色 |
|---|---|---|
| `apps/desktop/src/app/command-palette/contrib.ts` | 66 | `PALETTE_AREA` 常量 + `PaletteContribution` 载荷类型 + `paletteToggle()` 二态行工厂 |
| `apps/desktop/src/app/command-palette/index.tsx` | 1358 | ⌘K 本体:关闭态只订阅一个 store,打开才挂 body;自研打分排序、嵌套子页、修饰键变体 |
| `apps/desktop/src/app/command-palette/marketplace-theme-page.tsx` | 172 | 「安装主题…」子页:搜 VS Code Marketplace、逐行安装、装完即激活 |
| `apps/desktop/src/app/command-palette/pet-palette-page.tsx` | 214 | 「宠物…」子页 + 搜索行内开关,薄薄一层盖在 `store/pet-gallery` 上 |

### 0.5 指挥中心与子代理面板(3 文件 / 1,501 行)

| 全路径 | 行 | 一句话角色 |
|---|---|---|
| `apps/desktop/src/app/command-center/index.tsx` | 692 | 四段式覆盖层:sessions(搜/固定/导出/删)、system(状态+日志尾巴+重启/更新)、usage(用量图)、maintenance |
| `apps/desktop/src/app/command-center/maintenance.tsx` | 416 | `hermes doctor / security audit / backup / debug share / curator / memory` 的桌面等价面板,spawn 动作内联跟日志 |
| `apps/desktop/src/app/agents/index.tsx` | 393 | 子代理树只读面板:按委派分组、状态字形、流式行、读写文件清单、时长/token/成本汇总 |

### 0.6 星图 `src/app/starmap/`(14 文件 / 3,742 行)

一张「这个 profile 学到了什么」的径向时间盘,canvas 渲染 + d3-force 布局 + 可分享码。

| 全路径 | 行 | 一句话角色 |
|---|---|---|
| `apps/desktop/src/app/starmap/index.tsx` | 58 | 覆盖层外壳:拉 `$starmap*` atom,导入码优先于实时图 |
| `apps/desktop/src/app/starmap/star-map.tsx` | 980 | 交互主体:canvas、相机、播放扫描、命中测试、右键菜单、分享码编解码接线 |
| `apps/desktop/src/app/starmap/render.ts` | 864 | 纯绘制层:环、连线、球体节点、悬浮卡、环标签、打散动画 |
| `apps/desktop/src/app/starmap/simulation.ts` | 298 | d3-force 布局:半径由时间决定、同期节点按角度散开、环带内偏中放置 |
| `apps/desktop/src/app/starmap/timeline.tsx` | 289 | 底部时间轴洗涤器:分桶星点、播放/暂停、环锚点刻度 |
| `apps/desktop/src/app/starmap/node-context-menu.tsx` | 219 | 节点右键:编辑(`editLearningNode`)/删除(`deleteLearningNode`,技能走归档确认) |
| `apps/desktop/src/app/starmap/share-code.ts` | 188 | 「HML」分享码 body schema:节点 kind/时间位/半径输入/内插标签,边为定宽索引 |
| `apps/desktop/src/app/starmap/color.ts` | 138 | 主题色解析(1×1 canvas 光栅化拿真 sRGB)、混色、变暗、调色板计算 |
| `apps/desktop/src/app/starmap/geometry.ts` | 132 | clamp / FNV-1a hash / 节点半径 / recency→墨色 / 形状路径 / 适配缩放 |
| `apps/desktop/src/app/starmap/time-axis.ts` | 105 | 共享 recency 模型:布局半径与时间轴点火时刻用同一套比例 |
| `apps/desktop/src/app/starmap/types.ts` | 97 | SimNode/SimLink/Viewport/Ring/Palette 等本簇类型 |
| `apps/desktop/src/app/starmap/text.ts` | 90 | 日期格式化、悬浮卡徽章行、使用次数标签、省略与折行 |
| `apps/desktop/src/app/starmap/constants.ts` | 62 | 盘面几何常量、明暗两套线/环参数、节点字形映射 |
| `apps/desktop/src/app/starmap/share-controls.tsx` | 134 | 分享/导入对话框:一个 textarea + Load 按钮,错误内联 |

### 0.7 打包插件 `src/plugins/`(15 文件 / 5,483 行)

| 全路径 | 行 | 一句话角色 |
|---|---|---|
| `apps/desktop/src/plugins/README.md` | 14 | 目录说明:怎么放一个打包插件 + 声称「目前无内置插件」(见 §5 ▲-H-1) |
| `apps/desktop/src/plugins/example/plugin.tsx` | 125 | 教学插件:状态栏点击计数器,一口气用满 storage/onEvent/palette/keybind/atom/haptic;`defaultEnabled: false` |
| `apps/desktop/src/plugins/gateway-pill/plugin.tsx` | 375 | 用纯 SDK 1:1 重建核心网关健康药丸(菜单面板、就绪判定、日志尾巴、平台列表);**未声明 `defaultEnabled`** |
| `apps/desktop/src/plugins/hello-runtime/plugin.runtime.js` | 38 | 运行时管线的示例插件源文本(纯 ESM + `jsx()` 调用);**全仓无任何引用**(见 §6 ■-H-2) |
| `apps/desktop/src/plugins/kanban/plugin.tsx` | 160 | kanban 插件入口:注册 `/kanban` 路由页、侧栏导航行、状态栏计数、2 条 ⌘K 行、1 条 keybind |
| `apps/desktop/src/plugins/kanban/api.ts` | 253 | 数据层:全部走 `ctx.rest` 打到 `/api/plugins/kanban/*`,查询键/socket 失效/选中看板 atom |
| `apps/desktop/src/plugins/kanban/types.ts` | 214 | 只声明 UI 真读的那部分 REST 契约,后端加字段不会破坏构建 |
| `apps/desktop/src/plugins/kanban/board.tsx` | 1430 | 看板页:列、拖拽移动(乐观 + 工作流校验)、⌘ 多选批量条、右键动作、抽屉 |
| `apps/desktop/src/plugins/kanban/drawer.tsx` | 958 | 任务详情抽屉:诊断面板、描述编辑、结果、依赖、评论、活动、运行历史、worker 日志尾巴 |
| `apps/desktop/src/plugins/kanban/i18n.ts` | 991 | 插件作用域 i18n 包(经 `ctx.i18n.register` 注册,不碰核心 `en.ts`) |
| `apps/desktop/src/plugins/kanban/ui.tsx` | 283 | 共享 UI 原子:格式化、身份头像、状态菜单、章节壳、遮罩滚动条 |
| `apps/desktop/src/plugins/kanban/board-switcher.tsx` | 243 | 标题栏看板切换器,经 `<Contribute>` 投进 `titleBar.center`,随页面挂载/卸载 |
| `apps/desktop/src/plugins/kanban/orchestration.tsx` | 183 | 调度器旋钮面板:orchestrator profile、默认受理人、自动分解、profile 描述 |
| `apps/desktop/src/plugins/kanban/model-override.tsx` | 170 | 逐任务模型覆盖:复用 SDK 的 `ModelCatalogMenu`,但值是游离的而非写活会话 |
| `apps/desktop/src/plugins/kanban/kanban.css` | 46 | 看板局部样式(唯一一个非 TS 源文件;扩展名不在校验器白名单内) |

**合计 12 + 14 + 4 + 4 + 3 + 14 + 15 = 66 文件。**

---

## 1. 这一簇解决什么问题

一句话:**桌面端要在不改核心代码的前提下,让「能力」既能被用户看见、也能被用户和 agent 增删改。**

它拆成两个方向,方向相反:

- **往里塞(贡献框架)**:任何一段 UI —— 核心自己的、内置插件的、用户/agent 写在磁盘上的
  —— 都通过**同一个原语**(`Contribution`)登记到**同一个注册表**(`registry`),再由 22 个
  **area(挂载点)** 之一消费。核心不特殊:控制器注册状态栏项用的是插件一模一样的调用。
- **往外露(能力面板)**:Capabilities 页(Skills / Toolsets / MCP / Hub)、⌘K 命令面板、
  指挥中心、星图、Settings ▸ Plugins —— 五个面板,各自暴露一组**对能力本体的动作**
  (开/关、编辑、归档、安装、卸载、扫描、重载)。

两个方向在 `PALETTE_AREA` / `ROUTES_AREA` / `SIDEBAR_NAV_AREA` 处交汇:kanban 插件注册的
`/kanban` 页面,和核心的 `/skills` 页面,在路由表里是同一等地位的两行。

---

## 2. 接缝穷举(判据 2)

### 2.1 表 A —— 贡献挂载点全表(22 个 area)

这是本片最重要的一张表:**桌面端允许插件往哪些位置塞东西**。
枚举脚本(不猜、不抽样:从常量定义处解析 `*_AREA(S)`,加上所有到达注册表的裸字面量,
再展开两个 `${side}` 模板消费点):

```verify
python3 /home/user/hermes-study/data/r10b/probes/probe_h_areas.py /home/user/hermes-agent
```

输出 **22 个 area**,其中 **19 个**在 `apps/desktop/src/sdk/index.ts` 里有导出名、**3 个**没有。

| # | area id | 载荷 | 消费点(锚点 + 摘录) |
|---|---|---|---|
| 1 | `panes` | `data` = pane 规格 + `render()` | `apps/desktop/src/components/pane-shell/tree/renderer/tree-group.tsx:177` 的 `const panes = useContributions('panes')` |
| 2 | `layouts` | `data` = 布局树 | `apps/desktop/src/components/pane-shell/tree/presets.ts:17`:`export const LAYOUTS_AREA = 'layouts'` |
| 3 | `titleBar.left` | `render()` | `apps/desktop/src/app/contrib/controller.tsx:674` 的 `const items = useContributions(area)` |
| 4 | `titleBar.center` | `render()` | 同上(`TitlebarSlot` 的 `area` prop 三选一) |
| 5 | `titleBar.right` | `render()` | 同上 |
| 6 | `titleBar.tools.left` | `data` = `TitlebarTool` | `apps/desktop/src/app/contrib/panes.tsx:143` 的 `` const items = useContributions(`titleBar.tools.${side}`) `` |
| 7 | `titleBar.tools.right` | `data` = `TitlebarTool` | 同上 |
| 8 | `statusBar.left` | `data` = `StatusbarItem` 或 `render()` | `apps/desktop/src/app/contrib/panes.tsx:123` 的 `` const items = useContributions(`statusBar.${side}`) `` |
| 9 | `statusBar.right` | 同上 | 同上 |
| 10 | `composer.top` | `render()` | `apps/desktop/src/app/chat/composer/index.tsx:1216`:`<ContribSlot area={COMPOSER_AREAS.top} />` |
| 11 | `composer.leading` | `render()` | `apps/desktop/src/app/chat/composer/index.tsx:1254`:`<ContribSlot area={COMPOSER_AREAS.leading} />` |
| 12 | `composer.actions` | `render()` | `apps/desktop/src/app/chat/composer/index.tsx:1258`:`<ContribSlot area={COMPOSER_AREAS.actions} />` |
| 13 | `composer.bottom` | `render()` | `apps/desktop/src/app/chat/composer/index.tsx:1262`:`<ContribSlot area={COMPOSER_AREAS.bottom} />` |
| 14 | `composer.underside` | `render()` | `apps/desktop/src/app/chat/composer/index.tsx:1272`:`<ContribSlot area={COMPOSER_AREAS.underside} />` |
| 15 | `composer.middleware` | `data` = `ComposerMiddleware` | `apps/desktop/src/app/chat/composer/contrib.ts:75` 的 `for (const contribution of registry.getArea(COMPOSER_AREAS.middleware)) {` |
| 16 | `composer.attachments` | `data` = `ComposerAttachmentProvider` | `apps/desktop/src/app/chat/composer/contrib.ts:100`:`return useContributions(COMPOSER_AREAS.attachments)` |
| 17 | `composer.microActions` | `data` = `ComposerMicroActionProvider` | `apps/desktop/src/app/chat/composer/contrib.ts:133` 的 `const contributions = useContributions(COMPOSER_AREAS.microActions)` |
| 18 | `palette` | `data` = `PaletteContribution` | `apps/desktop/src/app/command-palette/contrib.ts:35`:`return useContributions(PALETTE_AREA)` |
| 19 | `routes` | `data` = `RouteContribution` + `render()` | `apps/desktop/src/app/routes.ts:82`:`export const ROUTES_AREA = 'routes'` |
| 20 | `sidebar.nav` | `data` = `SidebarNavContribution` | `apps/desktop/src/app/chat/sidebar/index.tsx:264` 的 `const navContributions = useContributions(SIDEBAR_NAV_AREA)` |
| 21 | `keybinds` | `data` = `KeybindContribution` | `apps/desktop/src/lib/keybinds/actions.ts:167`:`export const KEYBINDS_AREA = 'keybinds'` |
| 22 | `themes` | `data` = 主题对象 | `apps/desktop/src/themes/user-themes.ts:153`:`export const THEMES_AREA = 'themes'` |

**这张表是完整的,不是抽样的**,理由是注册表只有三个读口(`getArea` / `subscribeArea` /
`useContributions`)与一个写口(`register(Many)` 的 `area` 字段),脚本把四个口都扫了。
唯一的**结构性缺口**要如实说:`area` 是 `string`(`apps/desktop/src/contrib/types.ts:21`
的 `area: string`),所以插件**可以注册到一个不存在的 area**,那只是永远没人渲染,不会报错。

### 2.2 表 B —— 插件能力面(`ctx.*` 与 `host.*`,共 24 项)

插件拿到两样东西:`register(ctx)` 的**作用域上下文**,和从 `@hermes/plugin-sdk` import 的
**全局 host**。合起来就是「插件能做什么」的完整清单。

`ctx`(`apps/desktop/src/contrib/plugin.ts`,13 项):

| 成员 | 锚点 + 摘录 |
|---|---|
| `ctx.source` | `apps/desktop/src/contrib/plugin.ts:61`:`readonly source: string` |
| `ctx.register` | `apps/desktop/src/contrib/plugin.ts:63`:`register: (c: PluginContribution) => () => void` |
| `ctx.registerMany` | `apps/desktop/src/contrib/plugin.ts:65`:`registerMany: (cs: PluginContribution[]) => () => void` |
| `ctx.onDispose` | `apps/desktop/src/contrib/plugin.ts:69`:`onDispose: (fn: () => void) => void` |
| `ctx.rest` | `apps/desktop/src/contrib/plugin.ts:74`:`rest: <T>(path: string, opts?: PluginRestOptions) => Promise<T>` |
| `ctx.socket` | `apps/desktop/src/contrib/plugin.ts:79`:`socket: (path: string, onMessage: (data: unknown) => void) => () => void` |
| `ctx.os` | `apps/desktop/src/contrib/plugin.ts:83`:`os: PluginOs` |
| `ctx.os.notify` | `apps/desktop/src/contrib/plugin.ts:48`:`notify: (input: PluginNativeNotificationInput) => void` |
| `ctx.os.openExternal` | `apps/desktop/src/contrib/plugin.ts:51`:`openExternal: (url: string) => Promise<boolean>` |
| `ctx.os.revealPath` | `apps/desktop/src/contrib/plugin.ts:54`:`revealPath: (path: string) => Promise<boolean>` |
| `ctx.os.writeClipboard` | `apps/desktop/src/contrib/plugin.ts:56`:`writeClipboard: (text: string) => Promise<boolean>` |
| `ctx.storage` | `apps/desktop/src/contrib/plugin.ts:85`:`storage: PluginStorage` |
| `ctx.i18n` | `apps/desktop/src/contrib/plugin.ts:88`:`i18n: PluginI18n` |

`host`(`apps/desktop/src/sdk/index.ts`,本片外但必须列全才算穷举,11 项):

| 成员 | 锚点 + 摘录 |
|---|---|
| `host.state.activeSessionId` | `apps/desktop/src/sdk/index.ts:61` 的 `activeSessionId: readonlyAtom<null \| string>($activeSessionId),` |
| `host.state.cwd` | `apps/desktop/src/sdk/index.ts:63` 的 `cwd: readonlyAtom<string>($currentCwd),` |
| `host.state.gateway` | `apps/desktop/src/sdk/index.ts:65` 的 `gateway: readonlyAtom<string>($gatewayState),` |
| `host.state.model` | `apps/desktop/src/sdk/index.ts:67` 的 `model: readonlyAtom<string>($currentModel),` |
| `host.state.profile` | `apps/desktop/src/sdk/index.ts:69` 的 `profile: readonlyAtom<string>($activeGatewayProfile),` |
| `host.state.viewport` | `apps/desktop/src/sdk/index.ts:71` 的 `viewport: readonlyAtom<ViewportRect>($viewport)` |
| `host.notify` / `host.notifyError` | `apps/desktop/src/sdk/index.ts:75` 的 `notify,` |
| `host.logs` | `apps/desktop/src/sdk/index.ts:83` 的 `logs: async (...args: Parameters<typeof getLogs>) => getLogs(...args),` |
| `host.navigate` | `apps/desktop/src/sdk/index.ts:86` 的 `navigate: (path: string) => {` |
| `host.onEvent` | `apps/desktop/src/sdk/index.ts:93`:`onEvent: onGatewayEvent,` |
| `host.restartGateway` | `apps/desktop/src/sdk/index.ts:96` 的 `restartGateway: async () => runGatewayRestart(),` |
| `host.status` | `apps/desktop/src/sdk/index.ts:99` 的 `status: async () => getStatus(),` |
| `host.request` | `apps/desktop/src/sdk/index.ts:103` 的 `request: async <T>(method: string, params: Record<string, unknown> = {}): Promise<T> => {` |

**最后一项 `host.request` 一个人就把上面所有「curated door」的意义抵消了** —— 它是不受限的
网关 JSON-RPC。这不是我的推断,是文件自己写的(见 §4.2)。

### 2.3 表 C —— ⌘K 命令面板的注册面

命令面板的行有**两个来源**:注册表贡献(插件与核心都走这条)和面板自己硬编的静态分组。
先枚举注册表那一半:

```verify
python3 /home/user/hermes-study/data/r10b/probes/probe_h_palette.py /home/user/hermes-agent
```

输出 **14 条 `PALETTE_AREA` 贡献**,逐条列全:

| # | 命令 id | 标签 | 注册处 |
|---|---|---|---|
| 1 | `layout.editMode` | Toggle layout edit mode | `apps/desktop/src/app/contrib/controller.tsx:245` 的 `paletteToggle({` |
| 2 | `plugins.reload` | Reload desktop plugins | `apps/desktop/src/app/contrib/controller.tsx:258`:`area: PALETTE_AREA,` |
| 3 | `layout.reset` | Reset layout | `apps/desktop/src/app/contrib/controller.tsx:268`:`area: PALETTE_AREA,` |
| 4 | `view.toggleStatusbar` | Toggle status bar | `apps/desktop/src/app/contrib/controller.tsx:279` 的 `paletteToggle({` |
| 5 | `keybinds.panel` | Keyboard shortcuts | `apps/desktop/src/app/contrib/controller.tsx:291`:`area: PALETTE_AREA,` |
| 6 | `profile.export` | Export profile… | `apps/desktop/src/app/contrib/controller.tsx:304`:`area: PALETTE_AREA,` |
| 7 | `profile.import` | Import profile… | `apps/desktop/src/app/contrib/controller.tsx:315`:`area: PALETTE_AREA,` |
| 8 | `view.showTerminal` | Toggle terminal | `apps/desktop/src/app/contrib/controller.tsx:557` 的 `paletteToggle({` |
| 9 | `logs.toggle` | Toggle logs | `apps/desktop/src/app/contrib/controller.tsx:624` 的 `paletteToggle({` |
| 10 | `session.yolo` | Toggle yolo | `apps/desktop/src/app/contrib/controller.tsx:643` 的 `paletteToggle({` |
| 11 | `dev.creditsNotice` | Dev: cycle credit notices | `apps/desktop/src/app/contrib/dev/credits-notice-demo.ts:111`:`area: PALETTE_AREA,` |
| 12 | `example.reset` | Example: Reset click counter | `apps/desktop/src/plugins/example/plugin.tsx:102`:`area: PALETTE_AREA,` |
| 13 | `kanban.open` | Kanban: Open board | `apps/desktop/src/plugins/kanban/plugin.tsx:126`:`area: PALETTE_AREA,` |
| 14 | `kanban.newTask` | (i18n `newTaskCommand`) | `apps/desktop/src/plugins/kanban/plugin.tsx:136`:`area: PALETTE_AREA,` |

再列**静态那一半**(`apps/desktop/src/app/command-palette/index.tsx` 内建,不经注册表)。
不列全就不算穷举,所以逐组列出,注明条数与来源:

| 组 | 条数 | 锚点 |
|---|---|---|
| Go to | 9 固定 + 1 条件(`session.newWindow`,仅 `canOpenNewWindow()`) | `apps/desktop/src/app/command-palette/index.tsx:749` 的 `heading: cc.goTo,` |
| Projects | 1 固定(Open folder…)+ N 个项目行 | `apps/desktop/src/app/command-palette/index.tsx:720` 的 `const projectGroup: PaletteGroup = {` |
| Commands | = 上表 14 条(仅当非空才建组) | `apps/desktop/src/app/command-palette/index.tsx:823` 的 `...(contributedItems.length > 0` |
| Command center | 5(sessions / system / usage / restart gateway / update hermes) | `apps/desktop/src/app/command-palette/index.tsx:844` 的 `heading: cc.commandCenter,` |
| Appearance | 4(theme→子页 / color-mode→子页 / pets→子页 / generate pet) | `apps/desktop/src/app/command-palette/index.tsx:888` 的 `heading: cc.appearance,` |
| Settings | 8 个 config section + 8 条 `NON_CONFIG_SETTINGS` | `apps/desktop/src/app/command-palette/index.tsx:396` 的 `const NON_CONFIG_SETTINGS: ReadonlyArray<{` |
| 仅搜索时出现:直达会话 id | 0 或 1,正则 `^\d{8}_\d{6}_[a-f0-9]{6}$` | `apps/desktop/src/app/command-palette/index.tsx:368`:`const SESSION_ID_RE = /^\d{8}_\d{6}_[a-f0-9]{6}$/` |
| 仅搜索:绝对路径开项目 | 0 或 1 | `apps/desktop/src/app/command-palette/index.tsx:374`:`const FOLDER_PATH_RE = /^(\/\|[A-Za-z]:[/\\]).+/` |
| 仅搜索:Capabilities 深链 | 3(skills / toolsets / mcp) | `apps/desktop/src/app/command-palette/index.tsx:1005` 的 `heading: capLabel,` |
| 仅搜索:主题 / 色彩模式 / 会话 / 设置字段 / MCP 服务器 / 归档会话 | 各 N | `apps/desktop/src/app/command-palette/index.tsx:958` 的 `const searchGroups = useMemo<PaletteGroup[]>(() => {` |
| 分支组(worktree) | N,排在所有组之后 | `apps/desktop/src/app/command-palette/index.tsx:687` 的 `const branchGroup = useMemo<PaletteGroup[]>(` |
| 嵌套子页 | 4(`theme` / `color-mode` / `pets` / `install-theme`) | `apps/desktop/src/app/command-palette/index.tsx:1161` 的 `const subPages = useMemo<Record<string, PalettePage>>(` |

固定条数合计:**9(+1) + 1 + 5 + 4 + 16 + 3 = 38(+1) 条静态行 + 14 条贡献行 = 52(+1)**,
其余按数据量伸缩。

### 2.4 表 D —— 技能管理面能对技能做的动作全表

「Capabilities」页 + 星图右键 + Settings ▸ Plugins,凡是**写**动作,逐条列全:

| # | 动作 | 入口 | 客户端函数 | 锚点 + 摘录 |
|---|---|---|---|---|
| 1 | 单个技能开/关 | Skills 行开关 | `setSkillEnabled` | `apps/desktop/src/app/skills/index.tsx:343` 的 `await setSkillEnabled(skill.name, enabled)` |
| 2 | 全体技能开/关 | ListStripMenu 主开关 | 同 1,串行循环 | `apps/desktop/src/app/skills/index.tsx:386` 的 `await setSkillEnabled(row.name, enabled)` |
| 3 | 关掉从未用过的技能 | 菜单「Disable unused」 | 同 1 | `apps/desktop/src/app/skills/index.tsx:421` 的 `const disableUnused = () =>` |
| 4 | 编辑 SKILL.md | 详情页 Edit → CodeEditor | `editLearningNode` | `apps/desktop/src/app/skills/index.tsx:506` 的 `await editLearningNode(skillEditor.name, skillDraft)` |
| 5 | 归档技能 | 详情页 Archive → 确认框 | `deleteLearningNode` | `apps/desktop/src/app/learning/archive-skill-confirm-dialog.tsx:13` 的 `const res = await deleteLearningNode(id)` |
| 6 | 单个 toolset 开/关 | Toolsets 行开关 | `setToolsetEnabled` | `apps/desktop/src/app/skills/index.tsx:362` 的 `await setToolsetEnabled(toolset.name, enabled)` |
| 7 | 全体 toolset 开/关 | 同 2 | 同 6 | `apps/desktop/src/app/skills/index.tsx:392` 的 `await setToolsetEnabled(row.name, enabled)` |
| 8 | toolset 凭据/配置写入 | 详情页配置面板 | `ToolsetConfigPanel` | `apps/desktop/src/app/skills/index.tsx:821` 的 `<ToolsetConfigPanel key={toolset.name} onConfiguredChange={onConfiguredChange} toolset={toolset.name} />` |
| 9 | Hub 安装 | Hub 行 / 预览框 Install | `installSkillFromHub` | `apps/desktop/src/store/hub-actions.ts:133` 的 `return runHubAction(identifier, 'install', () => installSkillFromHub(identifier))` |
| 10 | Hub 卸载 | Hub 行 Uninstall | `uninstallSkillFromHub` | `apps/desktop/src/store/hub-actions.ts:137` 的 `return runHubAction(identifier, 'uninstall', () => uninstallSkillFromHub(name))` |
| 11 | Hub 全量更新 | 「Update installed」 | `updateSkillsFromHub` | `apps/desktop/src/app/skills/hub.tsx:211` 的 `void updateHubSkills().catch(err => notifyError(err, h.actionFailed))` |
| 12 | Hub 按需安全扫描(只读) | 预览框 Scan | `scanSkillHub` | `apps/desktop/src/app/skills/hub.tsx:217` 的 `scanSkillHub(identifier)` |
| 13 | 星图节点编辑 | 右键 → 编辑 | `editLearningNode` | `apps/desktop/src/app/starmap/node-context-menu.tsx:8` 的 `import { deleteLearningNode, editLearningNode, getLearningNode } from '@/hermes'` |
| 14 | 星图节点删除 | 右键 → 删除 | `deleteLearningNode` | 同上 |
| 15 | MCP 服务器整表替换保存 | mcp.json 编辑器 Save | `saveMcpServers` | `apps/desktop/src/app/skills/mcp-tab.tsx:860` 的 `const saveDoc = async () => {` |
| 16 | MCP 单服务器开/关 | 行开关 | `saveMcpServers` | `apps/desktop/src/app/skills/mcp-tab.tsx:733` 的 `const setServerEnabled = async (serverName: string, enabled: boolean) => {` |
| 17 | MCP 逐工具开/关 | 工具列表开关 | `saveMcpServers` + `toggleToolInServer` | `apps/desktop/src/app/skills/mcp-tab.tsx:763` 的 `const toggleTool = async (serverName: string, toolName: string) => {` |
| 18 | MCP 删除服务器 | 行动作 | `saveMcpServers` | `apps/desktop/src/app/skills/mcp-tab.tsx:789` 的 `const removeServer = async (serverName: string) => {` |
| 19 | MCP 新增服务器(模板) | Add 按钮 | 本地 draft | `apps/desktop/src/app/skills/mcp-tab.tsx:825` 的 `const addServer = () => {` |
| 20 | MCP 目录安装 | Catalog 行 Install | `installMcpCatalogEntry` | `apps/desktop/src/app/skills/mcp-tab.tsx:1375` 的 `const res = await installMcpCatalogEntry(entry.name, draft)` |
| 21 | MCP OAuth 授权 | 行动作 | `authMcpServer` | `apps/desktop/src/app/skills/mcp-tab.tsx:578` 的 `const authenticate = async (serverName: string) => {` |
| 22 | MCP 探测(只读) | 自动 + 行动作 | `testMcpServer` | `apps/desktop/src/app/skills/mcp-tab.tsx:556` 的 `const result = await testMcpServer(serverName)` |
| 23 | 向活跃会话热重载 MCP | 上述每次写后自动 | `reload.mcp` RPC | `apps/desktop/src/app/skills/mcp-tab.tsx:668` 的 `const silentReload = async () => {` |
| 24 | 插件启/停 | Settings ▸ Plugins 开关 | `setPluginEnabled` | `apps/desktop/src/app/settings/plugins-settings.tsx:66` 的 `void setPluginEnabled(record.id, on)` |
| 25 | 重扫磁盘插件 | Settings ▸ Plugins / ⌘K | `discoverRuntimePlugins` | `apps/desktop/src/app/settings/plugins-settings.tsx:111` 的 `void discoverRuntimePlugins()` |
| 26 | 打开插件目录 | Settings ▸ Plugins | `openDir` IPC | `apps/desktop/src/app/settings/plugins-settings.tsx:36` 的 `const result = await window.hermesDesktop?.openDir?.(dir)` |
| 27 | 在文件管理器中定位插件 | 行动作 | `revealPath` IPC | `apps/desktop/src/app/settings/plugins-settings.tsx:19` 的 `void window.hermesDesktop?.revealPath?.(file)?.catch(() => undefined)` |

**Settings ▸ Plugins 只有 4 个动作(24–27),没有第 5 个。** 这是完整枚举而非抽样:
`apps/desktop/src/app/settings/plugins-settings.tsx` 全文 132 行,已逐行读过,
`PluginRow`(:46)与 `PluginsSettings`(:89)加起来只渲染这四个交互元素。
**没有安装、没有卸载、没有 URL 拉取、没有市场。**

### 2.5 表 E —— 三条「安装」路径的对照(直接回答派工书线索 1)

本片被点名要独立取证:**桌面端装插件走的是不是 ■-R10-01 那条 `shell=True`?**
答案:**不是,而且桌面端根本没有「装插件」这个动作。** 三条路径的完整对照:

| 路径 | 入口 | 是否有 manifest | 是否执行 shell | 是否有扫描闸 | 锚点 + 摘录 |
|---|---|---|---|---|---|
| **A. 桌面插件(本片)** | 把 `plugin.js` 写进 `<hermes home>/desktop-plugins/<name>/` | **无** | **无** | **无**(只有 `sha256` 完整性可选项) | `apps/desktop/src/contrib/runtime-loader.ts:40` 的 `integrity?: string` |
| **B. 技能 Hub(本片)** | Capabilities ▸ Hub ▸ Install | 有(hub bundle) | 有(spawn `hermes skills install <id> --yes`) | **有**,后端 `should_allow_install` | `hermes_cli/web_routers/skills.py:62` 的 `+ ["skills", "install", identifier, "--yes"],` |
| **C. 记忆 provider(■-R10-01,非本片)** | dashboard ▸ memory provider setup | 有 | **有,`shell=True` 无过滤** | 无 | `hermes_cli/web_server.py:5521` 的 `install = _run_setup_command(` |

**A 的完整搜索面(负结论,按制度写清)**:搜索命令与范围如下 ——

```verify
cd /home/user/hermes-agent && grep -rn "desktop-plugins\|desktopPluginsRoot" --include='*' . 2>/dev/null | grep -v node_modules | grep -v "^\./\.git/"
```

命中 **29 处**,分布在:`skills/autonomous-ai-agents/hermes-agent/`(文档与模板,4 处)、
`apps/desktop/src/contrib/`(plugins.ts / plugins-store.ts / runtime-loader.ts,共 6 处)、
`apps/desktop/src/contrib/runtime-loader.test.ts`(8 处)、`apps/desktop/src/global.d.ts`(2 处)、
`apps/desktop/src/app/contrib/controller.tsx`(1 处)、`apps/desktop/src/app/settings/plugins-settings.tsx`(经
`desktopPluginsRoot`,2 处)。**没有任何一处是下载、解包、npm/pip 安装或执行命令**;
读取只经 `desktop.readFileText(file)`(`apps/desktop/src/contrib/runtime-loader.ts:212`)。
另外单独搜过 manifest 字段:

```verify
cd /home/user/hermes-agent && grep -rn "external_dependencies\|externalDependencies" --include=*.ts --include=*.tsx --include=*.py apps/desktop hermes_cli tools gateway
```

命中 **9 处,全部在 `hermes_cli/`**(`memory_setup.py` 1 处、`web_server.py` 8 处),
**`apps/desktop/` 零命中** —— 桌面端不解析任何插件 manifest。

**B 的 `--yes` 到底是什么(容易看错,单独取证)**:`--yes` 映射到 `skip_confirm`,**不是** `force`:

`hermes_cli/skills_hub.py:1735` @ 863e313

```
        do_install(args.identifier, category=args.category, force=args.force,
                   skip_confirm=getattr(args, "yes", False),
                   name_override=getattr(args, "name", "") or "")
```

所以桌面 Install 按钮**不会**绕过扫描策略;它只是跳过交互式确认(dashboard/desktop 无 TTY)。
`should_allow_install` 仍然跑,`decision == "block"` 时安装终止。

**代价说清**:A 没有安装步骤,不代表 A 更安全 —— 它把 shell 换成了「渲染进程内的完整应用权限」,
见 §4.2。

---

## 3. 端到端链(判据 3)

**用户动作:在 ⌘K 里敲 "yolo",回车。**(选这条是因为它一路穿过注册表、面板、store、
网关 RPC,是本片最短的完整链。)

1. **注册(启动时)** —— 控制器把一个二态行注册进 `palette` area。
   `apps/desktop/src/app/contrib/controller.tsx:642` @ 863e313

```
registry.register(
  paletteToggle({
    id: 'session.yolo',
    label: 'Toggle yolo',
    icon: Zap,
    keywords: ['yolo', 'approvals', 'auto-approve', 'bypass', 'dangerous', 'commands'],
    get: () => $yoloActive.get(),
    set: enabled => void setYoloEnabled(enabled).catch(() => undefined)
  })
)
```

2. **工厂补齐载荷** —— `paletteToggle` 把 `get/set` 折成 `detail()` + `run()`,并强制 `keepOpen`。
   `apps/desktop/src/app/command-palette/contrib.ts:56` @ 863e313

```
  const data: PaletteContribution = {
    ...rest,
    detail: () => (get() ? 'on' : 'off'),
    detailVariant: 'state',
    keepOpen: true,
    keywords: [...keywords, 'on', 'off', 'enable', 'disable'],
    run: () => set(!get())
  }
```

3. **注册表落桶 + 失效该 area 的快照**(只影响 `palette`,不会重渲染状态栏)。
   `apps/desktop/src/contrib/registry.ts:62` @ 863e313

```
    const resolved: readonly Contribution[] =
      !raw || raw.length === 0
        ? EMPTY
        : raw
            .filter(c => c.enabled !== false && (c.when ? c.when() : true))
            .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
```

4. **面板读取** —— `usePaletteContributions()` 订阅 `palette`,拼出稳定 render key。
   `apps/desktop/src/app/command-palette/contrib.ts:34` @ 863e313

```
export function usePaletteContributions(): Array<PaletteContribution & { key: string }> {
  return useContributions(PALETTE_AREA)
    .map(c => ({ key: `${c.source ?? 'core'}:${c.id}`, ...(c.data as PaletteContribution) }))
    .filter(item => Boolean(item.label && item.run))
}
```

5. **进入分组** —— 贡献行被塞进 "Commands" 组,`detail` 在这里被**求值一次**(每次 select 后重求)。
   `apps/desktop/src/app/command-palette/index.tsx:827` @ 863e313

```
              items: contributedItems.map(item => ({
                action: item.action,
                // Read on mount and after every select (the deps below), so a
                // row that reports state can't show the state it just left.
                detail: item.detail?.(),
                detailVariant: item.detailVariant,
                icon: item.icon ?? Zap,
                id: item.key,
                keepOpen: item.keepOpen,
                keywords: item.keywords,
                label: item.label,
                run: item.run
              }))
```

6. **打分选中** —— 输入 "yolo" 在 label `Toggle yolo` 里是整词,得 0.85;它同时命中名为
   `bb/yolo-*` 的 worktree 行(同样 0.85),平局由**组顺序**打破,而分支组被刻意排在最后。
   `apps/desktop/src/app/command-palette/index.tsx:1154` @ 863e313

```
  const groups = useMemo(
    () => [...baseGroups, ...searchGroups, ...branchGroup],
    [baseGroups, branchGroup, searchGroups]
  )
```

7. **执行** —— `handleSelect` 跑 `run()`;因为 `keepOpen`,面板不关,改为 bump `selectTick`
   让所有 `detail()` 重读。
   `apps/desktop/src/app/command-palette/index.tsx:1258` @ 863e313

```
    if (!item.keepOpen) {
      closeCommandPalette()

      return
    }
```

8. **内核** —— `run()` = `set(!get())` = `setYoloEnabled(...)`(`@/lib/yolo-session`,片外),
   最终改的是审批绕过开关;`$yoloActive` 翻转后,第 7 步重读的 `detail()` 立刻显示 `on`。
   同一个 store 函数还有另外两个门(状态栏闪电图标、`/yolo` 斜杠命令)—— 控制器的注释把这点
   写死了:「⌘K 是通向**同一个** store 函数的第三扇门」(`controller.tsx:639-641`)。

**这条链证明的设计**:核心自己的命令也走插件的路。第 1 步那个 `registry.register` 调用,
和 `apps/desktop/src/plugins/kanban/plugin.tsx:126` 里 kanban 注册 `kanban.open` 的调用,
是同一个函数、同一个 area、同一份载荷类型。

---

## 4. 逐机制/逐区域

### 4.1 贡献注册表:一个原语,两族载荷

`Contribution` 只有 8 个字段(`apps/desktop/src/contrib/types.ts:17-43`),但它承载两族东西:

- **Family A(UI 贡献)**:有 `render()`,由 `<Slot>` 或 pane 宿主渲染;
- **Family B(数据贡献)**:有 `data`,由某个引擎消费(布局树、主题、keybind、palette 行、
  composer 中间件……)。

区别不在类型系统里,而在**消费者怎么读**。`apps/desktop/src/app/contrib/panes.tsx:126-136`
的状态栏收集器把两族都接住了:有 `render` 就包一层 boundary 当 render-item,否则把 `data`
当 `StatusbarItem` 用。

三个值得记的设计取舍:

1. **快照按 area 缓存、按 area 失效**。`registry.ts:143-159` 的 `invalidate` 只清被动的 area
   并只通知该 area 的订阅者,全局通道另开。代价写在注释里:**`when()` 不是响应式的** ——
   它只在快照重建时求值,外部状态翻转不会自己重解析(`apps/desktop/src/contrib/types.ts:28-32`)。
   composer 的 microActions 因此不用 `when`,改用 `resolve(ctx)` 返回数组
   (`apps/desktop/src/app/chat/composer/contrib.ts:116` 的注释明说是为了绕开这一点)。
2. **同 id 覆盖 = 后写者赢**。`put()` 先 filter 掉同 id 再 push(`registry.ts:117`)。
   控制器据此把「打包插件在核心之后加载」变成一个特性:
   `apps/desktop/src/app/contrib/controller.tsx:392` @ 863e313

```
// Bundled plugins load AFTER core, so a same-id contribution from a plugin
// deliberately overrides the core default (last writer wins). Third-party
// runtime plugins will flow through the same discovery seam.
discoverBundledPlugins()
```

   注意这条只在 **id 相同**时成立;`gateway-pill` 插件用的是**不同 id**,所以它不是覆盖而是
   叠加 —— 见 §6 ■-H-1。
3. **错误隔离是唯一的隔离**。`ContribBoundary`(`react/boundary.tsx:28`)包住每一次
   `render()`;`emitGatewayEvent`(`events.ts:38-42`)对每个监听器 try/catch。
   两处的注释都反复强调这只是**错误**隔离。

### 4.2 插件加载的两条路,与「这不是能力边界」的自陈

**打包插件**靠一句 vite glob 发现,不需要任何 import 或注册表编辑:

`apps/desktop/src/contrib/plugins.ts:16` @ 863e313

```
const modules = import.meta.glob<{ default: HermesPlugin }>('../plugins/*/plugin.{ts,tsx}', { eager: true })
```

**运行时插件**走一条真管线:integrity → 裸 specifier 重写为 shim blob URL → blob `import()`
→ 校验默认导出 → `register(ctx)`。加载失败只 toast + log,坏插件不会带崩应用。

作者上下文由 `createPluginContext` 造,**provenance 与 id 命名空间由宿主盖章,作者写不了**:

`apps/desktop/src/contrib/plugin.ts:159` @ 863e313

```
export function createPluginContext(pluginId: string, onDispose?: (dispose: () => void) => void): PluginContext {
  const source = `plugin:${pluginId}`
  const scope = (c: PluginContribution): Contribution => ({ ...c, id: `${pluginId}:${c.id}`, source })
```

这看起来像一个能力系统的地基(有 provenance 戳、有命名空间、有 `PluginOs` 这种「curated OS door」)。
**文件自己否认了这个读法**,而且否认得非常明确:

`apps/desktop/src/contrib/runtime-loader.ts:16` @ 863e313

```
 *
 * SECURITY — this is NOT a capability boundary. A loaded plugin is evaluated
 * as ESM in the renderer realm with FULL app authority: the React singleton,
 * the whole SDK (`host.request` gateway RPC, `ctx.rest`, storage, `navigate`).
 * The isolation here is *error* isolation only (ContribBoundary, isolated
 * listeners) — a plugin can't crash the app, but it can do anything the app
 * can. That's acceptable for local sources (disk files can already run code),
 * and `integrity` only proves the bytes match a hash — it does NOT sandbox.
 * A remote source (https + allowlist) must NOT reuse this pipeline as-is:
 * it needs a real boundary (iframe/worker + CSP + capability gating) before
 * it can land. The `{ integrity }` option is the transport seam, not the
 * trust seam.
```

**这段自陈是本片最有价值的一条设计证据**,理由有三:

- 它把 `PluginOs` 的「每个门都返回结果而不抛异常」这类精心设计,**正确地降格为人机工程学**
  而非安全边界;
- 它给出了威胁模型的适用条件(「local sources — 磁盘文件本来就能跑代码」),
  也就把「什么时候这个理由失效」写死了(远程源);
- 它把 `integrity` 定位成**传输接缝**而非**信任接缝**,精确堵住了「有 sha256 所以安全」这个误读。

`types.ts:3-9` 的注释提到「later, the trust/capability gate(WoW 式 taint)」—— 那是**规划**,
基线里没有实现:`registry.getArea` 的 filter 只看 `enabled` 和 `when`
(见 §3 第 3 步代码块),**没有任何一行读 `source`**。

**启停生命周期**是两条路共有的:每个记录带 loader 交出的 activate/deactivate 句柄,
用户决策持久化在 `hermes.desktop.pluginDecisions.v2`,**缺席 ≠ 启用**(这正是
`defaultEnabled: false` 能生效的原因):

`apps/desktop/src/contrib/plugins.ts:66` @ 863e313

```
    if (pluginActive(plugin.id, plugin.defaultEnabled ?? true)) {
      activate()
    }
```

**磁盘门是自维护的**:每个 `plugin.js` 被 fs 监视(存盘即热重载),目录本身也被监视
(新文件夹自动加载、删除自动卸载),老 Electron 壳回落到 5 秒可见轮询。
一处值得记的边界处理:热编辑改了 `plugin.id` 时,`loadRuntimePlugin` 只会 dispose **新** id,
所以 `loadDiskPlugin` 得自己收拾旧化身(`runtime-loader.ts:215-221`),否则贡献与清单行都会成孤儿。

### 4.3 技能面板:四个 tab,三种「能力」,一套开关语义

`SkillsView` 的四个 tab 分别对着三种不同的东西:

- **Skills** —— agent 学到的/内置的 SKILL.md,有 `provenance`(`bundled` / `agent` / `hub`);
- **Toolsets** —— 内置工具组,靠 `isDesktopToolsetVisible` 过滤掉桌面无意义的;
- **MCP** —— 外部工具服务器(见 §4.4);
- **Hub** —— 尚未安装的、可搜索的远程技能。

**开关的写入语义是乐观 + 静默**:单个 toggle 立刻改缓存、成功不弹 toast、失败回滚并报错
(`index.tsx:339-353`)。批量 toggle 则**故意串行**,注释给了理由:

`apps/desktop/src/app/skills/index.tsx:373` @ 863e313

```
  // Sequential on purpose: each toggle is a config read-modify-write on the
  // backend; parallel calls would race the disabled-list save.
  async function bulkApply(skillTargets: SkillInfo[], toolsetTargets: ToolsetInfo[], enabled: boolean) {
```

**批量控制永远作用于整 tab、不作用于搜索结果**,这条也写进了注释(`index.tsx:291-293`):
「一个全 tab 控件如果悄悄缩到当前 query,就是在撒谎」。

**读写有没有经过审批闸?没有。** 这是派工书线索 2 的答案,取证如下:

- **UI 侧确有一个门,但它是外观门**:
  `apps/desktop/src/app/skills/index.tsx:731` @ 863e313

```
  // Only learned/local skills are the user's to rewrite or archive — bundled
  // and hub skills are managed by their sources.
  const editable = skill.provenance === 'agent'
```

  `editable` 为假时,Edit / Archive 两个按钮**不渲染**(`index.tsx:751`)。
- **API 侧没有对应的门**。`PUT /api/learning/node` 直接调 `edit_node`,不看 provenance:
  `hermes_cli/web_server.py:3568` @ 863e313

```
@app.put("/api/learning/node")
async def update_learning_node(body: LearningNodeEdit):
    """Rewrite a journey node's content (SKILL.md or memory chunk)."""
    from agent.learning_mutations import edit_node

    with _profile_scope(body.profile):
        res = edit_node(body.id, body.content)
```

  再往下 `tools/skill_manager_tool.py:977` 的 docstring 自己说是「**any** existing skill」,
  它的四道闸是 frontmatter 校验、体积校验、org-mirror 写保护、background-review 保护
  —— 都与 provenance 无关。
- **审批系统(`tools/approval.py`)管的是 agent 的工具调用,不管桌面用户的直接 REST 写**。
  搜索面:在 `apps/desktop/src/app/skills/` 与 `apps/desktop/src/app/starmap/` 全目录搜
  `approv`(大小写不敏感)零命中;`apps/desktop/src/hermes.ts` 的
  `getLearningNode` / `deleteLearningNode` / `editLearningNode`(:945/:952/:961)三个函数体
  合计 24 行,全部只是 `window.hermesDesktop.api({...})`,没有任何前置调用。

所以:**桌面端对技能的读写,只有「UI 不给你按钮」这一层软约束,没有硬闸。**
这在本地单用户桌面语境下是合理的(和 §4.2 那句 "disk files can already run code" 同源),
但要注意 `provenance` 这个字段在 UI 里读起来像一条规则,在 API 层不是。

**星图是同一批端点的第二扇门**:`apps/desktop/src/app/starmap/node-context-menu.tsx:8`
import 的正是 `deleteLearningNode, editLearningNode, getLearningNode`,右键即可编辑/删除
—— 而星图**不显示 provenance**,所以那条 UI 软约束在星图这条路上根本不存在。

**Hub 的扫描是「按需 + 建议」,不是闸**。UI 侧的 Install 按钮不看扫描结论:

`apps/desktop/src/app/skills/hub.tsx:454` @ 863e313

```
                <Button
                  disabled={actions[detail.identifier]?.running || isInstalled(detail.identifier)}
                  onClick={() => install(detail.identifier, detail.name)}
                  size="sm"
                >
                  {isInstalled(detail.identifier) ? h.installed : h.install}
                </Button>
```

`disabled` 里只有「正在跑」和「已安装」,**没有 `scan.policy === 'block'`**。
真正的闸在后端(§2.5 表 E 的 B 行已取证),所以这不是安全漏洞,只是
**UI 允许用户按下一个后端注定拒绝的按钮**,失败以动作日志里的
`Installation blocked: …` 呈现。信任等级(`builtin` / `trusted` / `community`)在 UI 上
是彩色徽章 + 去重排序权重(`hub.tsx:47` 的 `TRUST_RANK`),同样只是呈现。

### 4.4 MCP tab:桌面端真正的「任意执行」门

MCP tab 把 `config.yaml` 的 `mcp_servers` 映射成生态通用的 `mcp.json` 文档,给用户一个
JSON 编辑器。默认模板本身就说明了这扇门有多宽:

`apps/desktop/src/app/skills/mcp-tab.tsx:63` @ 863e313

```
const STARTER_ENTRY = { command: 'npx', args: ['-y', '@modelcontextprotocol/server-filesystem', '/path/to/dir'] }
```

保存是**整表替换**(不是深合并),这样才删得掉服务器、去得掉字段;写完立刻热推到活跃会话:

`apps/desktop/src/app/skills/mcp-tab.tsx:686` @ 863e313

```
  const persist = async (nextServers: McpServers): Promise<boolean> => {
    const epoch = profileEpoch.current
    await saveMcpServers(nextServers)

    if (profileEpoch.current !== epoch) {
      return false
    }

    setConfig(current => ({ ...current, mcp_servers: nextServers }))
    void silentReload()

    return true
  }
```

`silentReload` 发的是 `reload.mcp` RPC(`mcp-tab.tsx:673`)。合起来:
**在文本框里敲一个 `command`,按 Save,几百毫秒后 agent 就会 spawn 它。**
没有扫描、没有确认框、没有审批。

要把这条结论摆正:这**是 MCP 协议的设计本意**(MCP server 就是本地进程),不是缺陷;
但它意味着**桌面端「装东西」的真实高危面是 MCP tab,不是插件门**。二者的对照是:
插件门给的是渲染进程内的应用权限(§4.2),MCP tab 给的是后端主机上的进程权限。

一个设计细节值得记:`normalizeEntry`(`mcp-tab.tsx:73`)把 Cursor/Claude 写的 `type` 字段
改写成 Hermes 读的 `transport`,`parseServersDoc`(`mcp-tab.tsx:84`)同时接受
`{"mcpServers": {...}}` 与裸 name→config 映射 —— 目标是让任何 README 里的
「把这段加进你的 mcp.json」原样粘贴就能用。这是**兼容生态的粘贴面**,不是安全面。

### 4.5 命令面板:关闭态的成本被压到一个订阅

⌘K 的性能设计值得单独记,因为它是一个可迁移的模式:
**面板拆成 `CommandPalette`(常驻)与 `CommandPaletteBody`(仅打开时存在)两层**。
常驻层只订阅一个 store;十几个 store 订阅、三个服务端查询、几百行的分组构建全在 body 里。
注释给了改之前的病症(`index.tsx:474-479`):一次进行中的更新会按进度行重写 `$updateApply`,
于是**为一个没人看得见的面板**重建整个行集。

三个配套细节:

- `mounted` **滞后于** `open`,由内容自己的 `animationend` 退休(`index.tsx:1284-1288`),
  所以关闭动画时长由 CSS 拥有,不是硬编计时器;另有 1000ms 兜底给 jsdom 这种不跑动画的环境。
- `openCount` 作为 key **每次打开都重挂 body**,于是搜索词/子页状态自动清零,不需要 close effect。
- 排序**不用 cmdk 自己的**:`shouldFilter={false}`,自研 `scoreItem`(七档:精确 > 前缀 >
  整词 > 词前缀 > 子串 > 散词 > 仅关键词)+ `rankGroups`。注释里记了 cmdk 分组重排为什么
  静默失效(它按内部 id 查组,而那个 id 永远匹配不上它自己写进 `data-value` 的标题文本)。

### 4.6 wiring:插件先听流,应用后分发

网关事件先过插件水龙头,再走应用分发:

`apps/desktop/src/app/contrib/wiring.tsx:683` @ 863e313

```
  // Plugins hear the stream FIRST (isolated fan-out in contrib/events), then
  // the app dispatches as before — a plugin listener can't affect app flow.
  const handleGatewayEventWithPlugins = useCallback(
    (event: Parameters<typeof handleDesktopGatewayEvent>[0]) => {
      emitGatewayEvent(event)
```

「先听」+「不能影响」这两件事同时成立的原因是 `emitGatewayEvent` 只是 fan-out,
不看返回值也不 await(`contrib/events.ts:31-45`);监听器抛异常只 `console.error`。
零监听时直接 return,所以无插件时是零成本。

`wiring.tsx` 还是 DEV 演示的安装点,动态 import 放在 DEV 守卫**内部**,
让模块在生产构建里被摇掉(`wiring.tsx:302-314`)。

### 4.7 星图:一个只读可视化 + 两个写动作 + 一个分享码

星图本体是纯呈现:`simulation.ts` 用 d3-force 按**时间**决定半径(同期节点按角度散开,
所以一次爆发读起来是一整圈而不是一个点),`render.ts` 是纯 canvas 绘制,
`color.ts` 用 1×1 canvas 光栅化来拿真 sRGB(因为主题 token 走 `color-mix()`/`oklch`,
`getComputedStyle` 返回的不是 `rgb()`,朴素字符串解析会静默变黑)。

**它的写动作只有两个**,都在右键菜单里,都打 `/api/learning/node`(§4.3 已述)。

**分享码**(`share-code.ts`)是本簇最独立的一块:自定义 bitstream + DEFLATE + base64url,
前缀 `HML`。它编码的是**地图渲染需要的东西**,不是原始数据 —— 时间被量化成 12 bit 的
**区间内位置**(不是绝对 epoch),记忆正文被丢弃、标签被内插并截断到 64 字符。
`share-controls.tsx` 是它唯一的 UI:一个 textarea + 一个 Load 按钮。

### 4.8 kanban:一个插件能走多远

kanban 是「插件能力上限」的实测样本 —— 4,731 行,注册 **6 个贡献、跨 5 个 area**:

| 贡献 | area | 效果 |
|---|---|---|
| `page` | `routes` | `/kanban` 成为工作区里的一等页面 |
| `nav` | `sidebar.nav` | 侧栏多一行导航 |
| `count` | `statusBar.right` | 活跃任务数药丸 |
| `open` | `palette` | ⌘K「Kanban: Open board」 |
| `new-task` | `palette` | ⌘K「新建任务」,hotkey 提示跟随实时绑定 |
| `new-task` | `keybinds` | `mod+alt+n`,可在键位面板改绑 |

它另外用了三个非-area 接缝:`ctx.rest` 打自己的 `/api/plugins/kanban/*`(复用既有的
`plugins/kanban/dashboard/plugin_api.py`,**没有新后端**)、`ctx.socket` 做失效推送、
`ctx.i18n.register` 挂插件作用域的语言包(991 行,不碰核心 `en.ts`)。
标题栏切换器走的是**第四种**接缝 —— `<Contribute>` 反向 portal,把菜单投进
`titleBar.center` 并随页面卸载自动注销(`board-switcher.tsx:1-6` 的 docstring)。

`plugin.tsx:95-99` 有一段值得记的**命名空间礼仪**:核心占了 `mod+n`(`session.new`)与
`mod+shift+n`(`session.newWindow`),核心只在 `mod+alt+1…9` 用 alt 且从不配字母,
所以 `⌘⌥<字母>` 被认定为**插件命令的天然命名空间**。这类约定在代码里写下来,
比放在文档里更可能被遵守。

---

## 5. 文档与代码的出入

### ▲-H-1 —— `apps/desktop/AGENTS.md` 说注册表「不是公开插件 ABI」,基线里它是

标题 `## Keep the waist narrow, grow at the edges`(`apps/desktop/AGENTS.md:145`)下的整段:

`apps/desktop/AGENTS.md:147` @ 863e313

> The root contribution rubric governs here too. New capability should arrive at
> the smallest surface that solves it: extend what exists, add a feature locally,
> lean on an existing seam — before you invent a framework. The shell's internal
> registries are composition seams, not a public plugin ABI; do not build a
> universal extension system, a manifest, or a plugin adapter for a single
> consumer.

**先把整段判完,再说 ▲ 落在哪。** 这段有四个断言 + 一串祈使句:

1. 「新能力应落在最小接缝上」—— 规范性指令,不可证伪,**不判**;
2. 「shell 的内部注册表是组合接缝」—— **成立**(§4.1);
3. 「**不是**公开插件 ABI」—— **不成立**,见下;
4. 「不要造 manifest」—— **在桌面端成立**(§2.5 已取证:`apps/desktop/` 对
   `external_dependencies` 零命中,磁盘门只读一个 `plugin.js`);
5. 「"Plugin" 在 Hermes 里指若干互不相干的东西,别假设一个表面的扩展模型能跑在另一个上」
   —— **成立,而且被本片证实**(§2.5 表 E 三条路径互不相同)。

**▲ 只落在断言 3。** 依据:基线里存在一个具名的、有版本意图的公开作者契约 ——
`apps/desktop/src/contrib/plugin.ts` 的文件级 docstring 第一句就是
「The plugin authoring contract」;`apps/desktop/src/sdk/index.ts` 导出 **19 个 area 常量 +
一个 `host` 门面 + 30 余个 UI 组件**供插件 import;`runtime-loader.ts` 加载**第三方磁盘 ESM**;
`plugins-store.ts` 维护带启停开关的插件清单;仓库里还有一个专门教 agent 写这类插件的技能
(`skills/autonomous-ai-agents/hermes-agent/references/desktop-plugins.md` +
`templates/plugin.js`)。这些合起来就是「公开插件 ABI」的定义。

**我不主张的部分**:断言 4、5 成立,断言 1 是规范不是事实。整段不记 ▲,只记断言 3。

### ▲-H-2 —— `src/plugins/README.md` 说「目前没有内置插件」,实际有三个

`apps/desktop/src/plugins/README.md:7` @ 863e313

> None ship in-tree today — reference/demo plugins (the counter example, the
> gateway-pill 1:1 rebuild, the runtime-loader hello world) live in the companion
> [`hermes-example-plugins`](https://github.com/NousResearch/hermes-example-plugins)
> repo so the shipped app stays uncluttered.

`ls apps/desktop/src/plugins/` 有四个子目录:`example/`、`gateway-pill/`、`hello-runtime/`、
`kanban/`。其中三个**正好就是这段话点名的那三个**,而且前两个 + kanban 都匹配同一份 README
上一段描述的那句 glob(`../plugins/*/plugin.{ts,tsx}`,见 §4.2 代码块),**会在启动时自动注册**。

```verify
cd /home/user/hermes-agent && ls -d apps/desktop/src/plugins/*/ && ls apps/desktop/src/plugins/*/plugin.tsx
```

**判定边界**:该段还断言「它们住在 companion 仓库里」。那个仓库在本容器不可达(无网络),
**这半句我无法证伪,也不主张证伪** —— 同名插件完全可能两边都有。
▲ 只落在「None ship in-tree today」这半句。

**注意来源等级**:`apps/desktop/src/plugins/README.md` **不在**派工书 §4 列的文档来源清单
(README.md / 根 AGENTS.md / apps/desktop/AGENTS.md / DESIGN.md / apps/desktop/README.md /
website/docs/**)里。它是一份紧贴代码的目录 README。如实标注,由主线决定是否计入跨轮 ▲ 计数。

### ◇-H-1 —— 22 个 area 里有 3 个没有 SDK 导出名

`layouts`、`titleBar.tools.left`、`titleBar.tools.right` 是活的挂载点(§2.1 表 A 的 2/6/7 行),
但 `apps/desktop/src/sdk/index.ts` 里搜不到它们:

```verify
cd /home/user/hermes-agent/apps/desktop/src && grep -c "LAYOUTS_AREA" sdk/index.ts; grep -c "titleBar.tools\|TITLEBAR_TOOL" sdk/index.ts
```

两条都输出 `0`。因为 `Contribution.area` 是裸 `string`,插件**照样能**注册进去
(手写 `area: 'layouts'` 即可,布局选择器会照读),只是 SDK 没给名字、没给载荷类型,
作者只能靠读核心源码发现它们。对比:另外 19 个 area 都有 `PANES_AREA` / `STATUSBAR_AREAS`
这样的具名导出。**代码有、SDK 面没有 → ◇。**

### ◎-H-1 —— 「curated OS door」的措辞保守但字面为真

`apps/desktop/src/contrib/plugin.ts:38-42` 把 `PluginOs` 描述为
「every way a plugin reaches outside the app window, in one attributed namespace
instead of the raw `window.hermesDesktop` bridge」。字面**为真**:`PluginOs` 确实是四个
带归属的门。但同一份 SDK 里的 `host.request`(§2.2)是无限制网关 RPC,`ctx.rest` 是
命名空间内 REST —— 「reaches outside the app window」的实际总面比这四个门大得多。
`runtime-loader.ts` 的 SECURITY 段已经把这点说清楚了,所以这不是矛盾,是**同一份代码里
一处保守措辞** → ◎,不是 ▲。

---

## 6. 缺陷

### ■-H-1 —— `gateway-pill` 插件默认开启,与核心状态栏项**同时**渲染两个网关药丸

**现象**:全新安装、无任何用户决策时,状态栏左簇有核心的 `gateway-health`,右簇有插件的
`gateway-pill`,两者内容一致(同一套就绪判定、同一个菜单面板)。

**证据链(四步,每步一个锚点)**:

1. 插件被 glob 发现 —— `apps/desktop/src/contrib/plugins.ts:16`(§4.2 代码块),
   `src/plugins/gateway-pill/plugin.tsx` 匹配 `../plugins/*/plugin.{ts,tsx}`。
2. 它**没有**声明 `defaultEnabled`,而另外两个内置插件都声明了 `false`:

   `apps/desktop/src/plugins/gateway-pill/plugin.tsx:350` @ 863e313

```
const plugin: HermesPlugin = {
  id: 'gateway-pill',
  name: 'Gateway Pill',
  register(ctx) {
```

   对照 `apps/desktop/src/plugins/example/plugin.tsx:75` 的 `defaultEnabled: false,`
   与 `apps/desktop/src/plugins/kanban/plugin.tsx:83` 的 `defaultEnabled: false,`。
   机械核对:

```verify
cd /home/user/hermes-agent/apps/desktop/src && grep -rn "defaultEnabled" plugins/*/plugin.tsx
```

   只有 example 与 kanban 两行命中。
3. 无用户决策时 `pluginActive(id, undefined ?? true)` → `true` → `activate()`
   (`apps/desktop/src/contrib/plugins.ts:66`,§4.2 代码块)。
4. 状态栏**不去重**:核心项与贡献项直接拼接。

   `apps/desktop/src/app/shell/hooks/use-statusbar-items.tsx:592` @ 863e313

```
  const leftStatusbarItems = useMemo(
    () => [...coreLeftStatusbarItems, ...extraLeftItems],
    [coreLeftStatusbarItems, extraLeftItems]
  )

  const statusbarItems = useMemo(
    () => [...extraRightItems, ...coreRightStatusbarItems],
    [coreRightStatusbarItems, extraRightItems]
  )
```

   核心的 `gateway-health` 在 `coreLeftStatusbarItems` 里
   (`use-statusbar-items.tsx:407` 的 `id: 'gateway-health',`),插件注册进 `statusBar.right`
   (`gateway-pill/plugin.tsx:359` 的 `area: 'statusBar.right',`)。**id 不同**,
   所以 §4.1 那条「同 id 后写者赢」的覆盖机制**不生效** —— 那正是这个插件本想利用的机制。

**这个 app 根确实是出货根**,不是实验分支:

```verify
cd /home/user/hermes-agent/apps/desktop/src && cat app/index.tsx
```

输出含 `export { ContribController as default } from './contrib'`;全仓 grep
`DesktopController` 只剩注释,无实现。

**严重度**:UI 重复,不影响正确性。**我未运行 Electron 验证渲染结果**(容器无 Electron 二进制,
`e2e/` 需要真 Electron),结论是静态追链得出的;若作者另有运行期抑制,应在 `use-statusbar-items`
或 `panes.tsx:122-139` 之外的地方,而这两处我已逐行读过、没有。

### ■-H-2 —— `hello-runtime/plugin.runtime.js` 是死文件,而加载器 docstring 仍把它当活的来源

`apps/desktop/src/contrib/runtime-loader.ts:13` @ 863e313

> Sources today: the in-repo runtime example (`?raw`, proves the pipeline)
> and `<hermes home>/desktop-plugins/<name>/plugin.js` on disk — the door the
> agent writes through.

全仓搜索该文件的任何引用(**搜索面:整仓所有文件,不限扩展名,排除 `node_modules` 与 `.git`**):

```verify
cd /home/user/hermes-agent && grep -rn "hello-runtime\|plugin\.runtime" --include='*' . 2>/dev/null | grep -v node_modules | grep -v "^\./\.git/"
```

**唯一命中是文件自己的第 28 行**(`id: 'hello-runtime',`)。另外单独查过 `?raw` import:

```verify
cd /home/user/hermes-agent/apps/desktop/src && grep -rn "?raw" --include=*.ts --include=*.tsx .
```

两处命中:`components/chat/intro.tsx:5`(引的是 `intro-copy.jsonl`)与
`contrib/runtime-loader.ts:13`(就是上面这句 docstring 本身)。

**双重死亡**:(a) 没有 `?raw` import,所以它不走运行时管线;(b) 文件名是
`plugin.runtime.js`,**不匹配** glob `plugin.{ts,tsx}`,所以也不会被当打包插件注册。
它在基线里 100% 不可达。docstring 的 "Sources today" 因此少了一个来源、多了一个不存在的来源。

关联:▲-H-2 的 README 把它称作「the runtime-loader hello world」并说它住在 companion 仓库
—— 这一半可能是**真的意图**(挪走了),只是 38 行的文件和 docstring 没跟着删。

### ■-H-3(弱,记为待判)—— `should_allow_install` 的三值返回被调用方当二值用

`tools/skills_guard.py:774` 的 docstring 与实现明确用 `None` 表示「需要用户确认」:

`tools/skills_guard.py:798` @ 863e313

```
    if decision == "ask":
        # Return None to signal "needs user confirmation"
        return None, (
            f"Requires confirmation ({result.trust_level} source + {result.verdict} verdict, "
            f"{len(result.findings)} findings)"
        )
```

调用方用 `if not allowed:` 判定,`None` 落进 falsy 分支,于是「ask」被当成「block」:

`hermes_cli/skills_hub.py:680` @ 863e313

```
    allowed, reason = should_allow_install(result, force=force)
    if not allowed:
        c.print(f"\n[bold red]Installation blocked:[/] {reason}")
```

方向是 fail-closed(保守),不是安全洞;但用户看到的是「Installation blocked」而不是一个确认提示,
与被调函数的契约不符。**这条在本片外**(后端),我只在追 §2.5 表 E 的 B 行时撞见,
未验证 `tools/skill_manager_tool.py:136` 那个调用方是否同病 —— 交给后续轮。

---

## 7. 测试(行为规格)

环境:主线备好的基线副本 `/home/user/r10b-ts/hermes-agent/apps/desktop`,**未装任何包**。

```verify
cd /home/user/r10b-ts/hermes-agent/apps/desktop && npx vitest run --project ui src/contrib src/plugins src/app/contrib src/app/skills src/app/starmap
```

**结果:12 文件 / 67 用例,passed 67 / failed 0 / skipped 0。**

**必须如实交代的一次抖动**:同一条命令的**第一次**运行报
`Test Files 1 failed | 11 passed`、`Tests 4 failed | 63 passed`,4 个失败全在
`src/app/skills/index.test.tsx`,形态是 `findByRole`/`findByText` 超时、DOM 为空
(`<body><div /></body>`)。该次运行 `Duration 61.15s`、其中 `import 63.06s`,
即并行导入把单用例挤过了 testing-library 的默认等待窗。单独重跑该文件两次:

```verify
cd /home/user/r10b-ts/hermes-agent/apps/desktop && npx vitest run --project ui src/app/skills/index.test.tsx
```

两次都 `Tests 4 passed (4)`、`Duration` 8.8s / 9.4s。全量第二次运行也 67/67 通过。
**判定:环境抖动(冷启动导入压力),非代码缺陷。** 记在这里是因为下一轮拿到 63 或 67
都可能,不写就无从判断。

**零执行/跳过点名**:本片 12 个测试文件中 `.skip` / `.todo` / `.only` 命中数为 **0**:

```verify
cd /home/user/hermes-agent/apps/desktop && grep -rn "\.skip\|\.todo\|\.only" src/contrib/*.test.ts src/app/contrib/*.test.* src/app/contrib/hooks/*.test.* src/app/skills/*.test.* src/app/starmap/*.test.* src/plugins/kanban/*.test.*
```

无输出。**没有整文件跳过、没有收集错误、没有掩盖的用例。**

**测试覆盖的真实形状(66 源文件 : 12 测试文件)** —— 逐个点名有测试的与没测试的:

| 源文件 | 测试 |
|---|---|
| `apps/desktop/src/contrib/plugin.ts` | `src/contrib/plugin.test.ts` |
| `apps/desktop/src/contrib/runtime-loader.ts` | `src/contrib/runtime-loader.test.ts`(含 #66899 的远程根回归) |
| `apps/desktop/src/app/contrib/latest-actions.ts` | `src/app/contrib/latest-actions.test.ts` |
| `apps/desktop/src/app/contrib/hooks/use-background-sync.ts` | 3 个文件:`use-background-sync.test.ts`、`live-status-reap.test.ts`、`live-status-spinner.test.ts` |
| `apps/desktop/src/app/contrib/hooks/use-desktop-integrations.ts` | `use-desktop-integrations.test.tsx` |
| `apps/desktop/src/app/contrib/hooks/use-session-tile-delegate.ts` | `use-session-tile-delegate.test.ts` |
| `apps/desktop/src/app/skills/index.tsx` | `src/app/skills/index.test.tsx` |
| `apps/desktop/src/app/starmap/share-code.ts` | `src/app/starmap/share-code.test.ts` |
| `apps/desktop/src/app/starmap/share-controls.tsx` | `src/app/starmap/share-controls.test.tsx` |
| `apps/desktop/src/plugins/kanban/model-override.tsx` | `src/plugins/kanban/model-override.test.tsx` |

**片内 56 个源文件没有自己的测试文件。** 其中值得点名的空白:

- `apps/desktop/src/contrib/registry.ts`(注册表本体)—— **无直接测试**,但被片外 14 个测试文件
  间接驱动:

```verify
cd /home/user/hermes-agent/apps/desktop && grep -rln "contrib/registry\|ContributionRegistry\|emitGatewayEvent\|plugins-store\|discoverBundledPlugins\|useContributions" src --include=*.test.ts --include=*.test.tsx
```

  输出 14 个路径,含 `src/app/chat/composer/contrib.test.ts`、
  `src/lib/keybinds/contributed-actions.test.ts`、`src/components/pane-shell/tree/*` 共 8 个。
- `apps/desktop/src/contrib/events.ts`、`plugins.ts`、`plugins-store.ts`、`react/*`(4 个)
  —— 上面那条命令的输出里没有针对它们的文件,即**只有间接覆盖**。
- **`src/app/command-palette/` 四个文件(1,810 行)—— 零测试文件**;
  `src/app/command-center/` 两个(1,108 行)—— 零;`src/app/agents/index.tsx`(393 行)—— 零。
  三处合计 3,311 行、占本片 16.4%,且都是纯 UI/交互逻辑,`e2e/` 的 19 个 Playwright spec
  里也没有 palette / command-center / agents 相关的文件名(`ls e2e/*.spec.ts` 已列全,
  最接近的是 `right-pane.spec.ts` 与 `sidebar-states.spec.ts`)。

---

## 8. 判据自查

| # | 判据 | 自评 | 说明 |
|---|---|---|---|
| **1 点名到位** | 66/66 全路径 + 一句话角色 | **达标** | §0 七张表,合计 12+14+4+4+3+14+15 = 66 |
| **2 接缝穷举** | 5 张表全列、3 张给机械枚举命令 | **达标(有一处如实标注的边界)** | 表 A(22 area)与表 C(14 palette 贡献)各有一个可重跑的 probe;表 B(24 项能力面)、表 D(27 个动作)、表 E(3 条安装路径)逐条列全并逐条带锚点。**边界**:表 A 只能穷举「被消费的 area」;因为 `area: string`,插件理论上可注册到任意字符串,该情形永远无人渲染,不构成挂载点 |
| **3 端到端链** | ⌘K "yolo" 八跳全带锚点 | **达标** | §3:注册 → 工厂 → 注册表 → 面板订阅 → 分组 → 打分 → 执行 → store,第 8 跳出片(`@/lib/yolo-session`)已注明 |
| **4 逐字取证** | 18 个围栏块是逐字源码摘录 | **达标** | 分布在 §2.5 / §3(6 块)/ §4 / §5 / §6 |
| **5 记号** | 2 ▲ + 1 ◇ + 1 ◎ + 3 ■ | **达标** | ▲-H-1(AGENTS.md,已按整段判定并写明只判第 3 个断言)、▲-H-2(plugins/README.md,已标注来源等级)、◇-H-1、◎-H-1、■-H-1/2/3 |

**未达标/打折的地方,如实写:**

- **■-H-1 未做运行期验证**。容器无 Electron 二进制,`e2e/` 跑不起来;结论是四步静态追链。
- **`board.tsx`(1,430)/ `drawer.tsx`(958)/ `i18n.ts`(991)/ `render.ts`(864)/
  `star-map.tsx`(980)五个大文件只读了 docstring + 导入面 + 导出面**,没有逐段读实现。
  这符合 L2「读接口面不读实现体」,但要说明:这五个文件合计 5,223 行,占本片 26%。
- **`host` 那半张表(表 B 后 11 项)取自片外的 `src/sdk/index.ts`**。不列它接缝就不完整,
  但它不在本片清单里,主线归并时请注意别重复计入片外的覆盖。

---

## 9. 移交项

| id | 锚点 + 摘录 | 一句话现象 | 建议接手 |
|---|---|---|---|
| **H-R10B-a** | `apps/desktop/src/plugins/gateway-pill/plugin.tsx:350`:`const plugin: HermesPlugin = {` | 该插件未声明 `defaultEnabled`,默认开启,与核心 `gateway-health` 同时渲染两个网关药丸(§6 ■-H-1);**未经运行期验证** | 有 Electron 的轮次跑一次 `e2e/boot.spec.ts` 变体截图核实 |
| **H-R10B-b** | `apps/desktop/src/plugins/hello-runtime/plugin.runtime.js:28`:`id: 'hello-runtime',` | 全仓无任何引用,双重不可达;`contrib/runtime-loader.ts:13` 的 "Sources today" 仍把它列为活来源(§6 ■-H-2) | 台账里该文件应归 **L4(有理由排除:死代码)**,而不是 L2 |
| **H-R10B-c** | `hermes_cli/skills_hub.py:680`:`allowed, reason = should_allow_install(result, force=force)` | 被调函数用 `None` 表示「需确认」,此处 `if not allowed` 把它当 block;方向保守但违反契约(§6 ■-H-3) | 后端片(hermes_cli/tools)轮次;同时查 `tools/skill_manager_tool.py:136` 的 `allowed, reason = should_allow_install(result)` 是否同病 |
| **H-R10B-d** | `apps/desktop/src/contrib/types.ts:21`:`export type ContributionSource = 'core' \| (string & {})` | `source` 字段的注释说它「drives precedence and, later, the trust/capability gate」;基线里 `registry.getArea` 的 filter 完全不读 `source`,precedence 只由 `order` 决定(§4.2) | 若后续轮做「插件信任模型」章,这是唯一的现存挂钩点 |
| **H-R10B-e** | `apps/desktop/src/app/skills/index.tsx:733`:`const editable = skill.provenance === 'agent'` | UI 侧的 provenance 门无 API 侧对应物;星图右键(`node-context-menu.tsx`)是同批端点的第二扇门且完全不看 provenance(§4.3) | 值得在成品章里作为「看起来像规则的外观约束」的例子 |
| **H-R10B-f** | `apps/desktop/src/sdk/index.ts:250`:`export const PANES_AREA = 'panes'` | 22 个 area 中 `layouts` / `titleBar.tools.left` / `titleBar.tools.right` 三个没有 SDK 导出名(§5 ◇-H-1);此锚点是「有名字」的那一类的样本,便于对照 | 若后续做 SDK 面完整性检查,probe_h_areas.py 可直接复用 |
| **H-R10B-g** | `apps/desktop/src/app/command-palette/index.tsx:488`:`export function CommandPalette() {` | 该文件 1,358 行 + 同目录三个文件,合计 1,810 行,**零测试文件、零 e2e**(§7) | 若排 L1 精读,palette 是本片最大的无测试面 |

---

## 10. 本片成本自报

```text
片号            : H
层              : L2
文件数 / 行数   : 66 / 20,165
实际打开的文件数: 62
                  (真读过内容的。未打开正文的 4 个:kanban/board.tsx、kanban/drawer.tsx、
                   kanban/i18n.ts、starmap/render.ts —— 只读了 docstring + 导入/导出面,
                   算「打开了接口面、没打开实现体」;为不虚报,这 4 个不计入「打开」)
实际读过的行数  : 约 11,400
                  (估法:逐行全读的文件按其总行数计 —— contrib/ 12 个 1,183 + app/contrib/
                   14 个中 11 个全读约 2,320 + wiring.tsx 取 4 段约 150 + skills/index.tsx 824
                   + skills/hub.tsx 468 + skills/store.ts 6 + mcp-tab.tsx 取 6 段约 400
                   + command-palette 4 个 1,810 + command-center 2 个 1,108 + agents 393
                   + starmap 14 个中 8 个小文件全读约 870、6 个大文件各读头 30–45 行约 230
                   + plugins/ 中 README 14 + example 125 + hello-runtime 38 + kanban/plugin 160
                   + gateway-pill 取 2 段约 130 + 其余 kanban 8 个各读头 30 行约 240;
                   另加片外追链约 500 行:sdk/index.ts、hub-actions.ts、plugins-settings.tsx、
                   use-statusbar-items.tsx、composer/contrib.ts、web_server.py、
                   skills_hub.py、skills_guard.py、web_routers/skills.py)
底稿字节数      : (主线自测)
主观耗费        : 中偏高。瓶颈是**跨文件追链**,不是文件多也不是单文件长:
                  本片真正的产出(表 A 22 个 area、表 B 24 项能力面、表 E 三条安装路径对照、
                  ■-H-1 的四步链)每一条都要求同时读「注册处 + 消费处 + 后端处」三个位置,
                  且其中至少一个在片外。相比之下 starmap 14 个文件虽占 3,742 行,
                  但它自成闭环、L2 深度下半小时就摸清了。
                  一个可复用的观察:**L2 的成本 ≈ 接缝数 × 每个接缝的跨文件跨度**,
                  与行数只弱相关。
```
