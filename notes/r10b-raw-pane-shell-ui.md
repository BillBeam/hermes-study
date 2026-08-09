# r10b 片G · 窗格外壳、通用 UI 原语与应用 shell —— 底稿

> 层:**L2**(读接口面,不读实现体;接口面**不抽样**)。
> 范围:`/home/user/hermes-study/data/r10b/slices/G.txt`,**100 文件 / 17,544 行**,
> 全部在 `apps/desktop/src/` 下。溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于块前。
> 基线自检:`git -C /home/user/hermes-agent status --porcelain` 空,HEAD = `863e313`。

---

## 0. 本片范围与逐文件点名(判据 1)

三个目录,职责各不相同:

| 目录 | 文件 | 行 | 一句话 |
|---|---|---|---|
| `apps/desktop/src/app/shell/` | 15 | 3,140 | 应用最外层 chrome:标题栏工具簇、状态栏、状态栏里的四个面板(网关 / 上下文 / 审批模式 / 模型目录) |
| `apps/desktop/src/components/pane-shell/` | 25 | 8,051 | 多窗格布局:一棵持久化的 split/group 树 + FancyZones 风格的拖放引擎 + 网格编辑器 |
| `apps/desktop/src/components/ui/` | 60 | 6,353 | 通用原语(shadcn/ui "new-york" 风格的本地副本 + 本项目自研原语) |

行数复核(可重跑):

```verify
cd /home/user/hermes-agent
awk '{print}' /home/user/hermes-study/data/r10b/slices/G.txt | xargs wc -l | tail -1
# → 17544 total
awk -F/ '{print $5}' /home/user/hermes-study/data/r10b/slices/G.txt | sort | uniq -c
# → 15 shell / 25 pane-shell(含 tree、tree/renderer)/ 60 ui  —— 见下逐目录清单
```

### 0.1 `apps/desktop/src/app/shell/`(15)

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/app/shell/titlebar.ts` | 标题栏的**纯常量层**:高度 34px、macOS 红绿灯尺寸/偏移、三个 className 串、`titlebarControlsPosition()`。无 React |
| `apps/desktop/src/app/shell/titlebar-controls.tsx` | 标题栏三个 fixed 工具簇(左:侧栏/翻转;中:pane 工具;右:布局/触感/键位/设置/右侧栏)。`TitlebarTool` 契约的宿主 |
| `apps/desktop/src/app/shell/statusbar-controls.tsx` | 底部状态栏:`StatusbarItem` 渲染器(4 种 variant)+ 右键"显示/隐藏哪几项"菜单 + `memo` 化的单项视图 |
| `apps/desktop/src/app/shell/hooks/use-statusbar-items.tsx` | 组装状态栏的**核心 9 项**(连接、命令中心、网关健康、工作区 cwd、子代理、cron、webhooks / 计时器、上下文、会话计时、审批模式、终端、版本×2) |
| `apps/desktop/src/app/shell/hooks/use-status-snapshot.ts` | 状态栏健康数据源:60s 轮询 `getStatus()` + `evaluateRuntimeReadiness()`,隐藏标签页跳过、`visibilitychange` 立刻补拉 |
| `apps/desktop/src/app/shell/hooks/use-overlay-routing.ts` | 覆盖层路由:settings / command-center / agents / starmap / cron / profiles / webhooks 的开关与"关闭后回到哪条路由" |
| `apps/desktop/src/app/shell/hooks/use-window-controls-overlay-width.ts` | 用 `navigator.windowControlsOverlay.getTitlebarAreaRect()` 实测 Windows/WSLg 原生窗口控件宽度,避免写死数字 |
| `apps/desktop/src/app/shell/gateway-menu-panel.tsx` | 网关健康弹层:连接/推理两行状态点 + 3s 轮询的日志尾巴(过滤 ws 噪音)+ 平台连接列表 + 重启按钮 |
| `apps/desktop/src/app/shell/context-usage-panel.tsx` | 上下文占用弹层:调 `session.context_breakdown`,画分段条 + 分类明细。**本片唯一直达 Python 内核的面板** |
| `apps/desktop/src/app/shell/approval-mode-menu.tsx` | 审批模式(manual/smart/off)的状态栏项 + 单选菜单,读写 `$approvalModes` |
| `apps/desktop/src/app/shell/model-catalog-menu.tsx` | **共享**模型目录菜单:搜索、按 provider 分组、`-fast` 家族折叠成一行、每行 hover 子菜单、cmdk 式键盘选择 |
| `apps/desktop/src/app/shell/model-menu-panel.tsx` | 把上面那个纯渲染菜单接到"当前会话"上的 controller:写 session、记全局 preset、失败回滚 |
| `apps/desktop/src/app/shell/model-edit-submenu.tsx` | 单行模型的编辑子菜单(thinking 开关 / fast / effort 单选)+ `resolveFastControl` 的 param-vs-variant 判定 |
| `apps/desktop/src/app/shell/sidebar-label.tsx` | 22 行:侧栏小节标题(小型大写 + dither 方点) |
| `apps/desktop/src/app/shell/group-setter.ts` | 6 行:`GroupSetter<T>` 类型定义,页面用它注册一组 statusbar/titlebar 贡献;实现在 `app/contrib/panes.tsx` |

### 0.2 `apps/desktop/src/components/pane-shell/`(25)

**顶层(4)**

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/components/pane-shell/index.ts` | 7 行:只导出一个跨界事件名 `PANE_TOGGLE_REVEAL_EVENT` |
| `apps/desktop/src/components/pane-shell/edit-mode.tsx` | `$layoutEditMode` 原子 + Escape 退出布局编辑模式(挂 escape-layer) |
| `apps/desktop/src/components/pane-shell/geometry.ts` | AABB 相交 → 原生窗口控件躲避;把 workspace 区的左右边缘发布成 `--workspace-left/right` CSS 变量;sash 拖拽期间抑制这些写入 |
| `apps/desktop/src/components/pane-shell/pane-visibility.ts` | keep-alive 可见性策略:`data-pane-hidden` 标记 + `queryVisible/queryAllVisible` + `PaneVisibleContext` / `PaneGroupContext` |

**树模型与状态(8)**

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/components/pane-shell/tree/model.ts` | **布局树的纯函数层**:`SplitNode`/`GroupNode` 类型、`normalize`、`removePane`/`insertAtGroup`/`movePane(s)`/`mergeZonesWithPane`、属性编辑、`mirrorTreeHorizontal`、`isLayoutNode` 校验 |
| `apps/desktop/src/components/pane-shell/tree/store.ts` | **1,670 行的状态与动作面**:18 个 nanostores 原子 + 61 个动作/查询;持久化、pane 采纳、关闭/隐藏/折叠语义、⌘W/⌘T/⌘1‑9/⌃Tab 的目标解析梯子 |
| `apps/desktop/src/components/pane-shell/tree/presets.ts` | 布局预设:核心预设与用户预设都是 `area: 'layouts'` 贡献;用户预设 round-trip 到 localStorage |
| `apps/desktop/src/components/pane-shell/tree/tab-selection.ts` | 标签页多选(Chrome 语法:⌥/Ctrl 点选切换、Shift 选区、普通点击收起) |
| `apps/desktop/src/components/pane-shell/tree/grid-model.ts` | **PowerToys FancyZones `GridLayoutModel.cs` + `GridData.cs` 的逐行移植**:cellChildMap、resizer、merge 闭包、split、模板 |
| `apps/desktop/src/components/pane-shell/tree/grid-to-tree.ts` | 网格 → 树的桥:递归 guillotine 切割;按 `placement` 语义给 zone 分配 pane;非 guillotine(风车)返回 null |
| `apps/desktop/src/components/pane-shell/tree/zones-engine.ts` | **PowerToys `FancyZonesLib` 运行时引擎的逐行移植**:`zonesFromPoint`、四种重叠消解算法、`getCombinedZoneRange`、`HighlightedZones` 状态机、动画/配色常量 |
| `apps/desktop/src/components/pane-shell/tree/zone-editor.tsx` | 全屏网格编辑器(`GridEditor.xaml.cs` 交互移植):跟随光标的分割线、橡皮筋框选 + Merge、共享边 resizer、四种模板、保存为用户预设 |

**渲染器(13)**

| 全路径 | 角色 |
|---|---|
| `apps/desktop/src/components/pane-shell/tree/renderer/index.tsx` | 树根 `LayoutTreeRoot`:递归节点 + 窄屏覆盖层 + 浮动 pane + 编辑面板 + 网格编辑器;两段全局 `<style>`(zone 淡入、"接缝归树所有"的边框中和) |
| `apps/desktop/src/components/pane-shell/tree/renderer/tree-node.tsx` | 33 行:split/group 分派点,传下 `parentAxis` / `railSide` / `root` / `rootRow` |
| `apps/desktop/src/components/pane-shell/tree/renderer/tree-split.tsx` | flex 行/列 + 1px 接缝即 sash:拖拽预览用内联样式、松手才写 store;双击复位;语义化左右侧折叠 |
| `apps/desktop/src/components/pane-shell/tree/renderer/tree-group.tsx` | 一个 zone:tab strip(含右键 ZoneMenu / 拖拽 / 多选 / "+")+ keep-alive 的 pane 内容层 + 编辑蒙版 + FancyZones 落点覆盖层 |
| `apps/desktop/src/components/pane-shell/tree/renderer/track-model.ts` | **轨道模型**:节点沿某轴是"固定轨道(解析成 CSS 长度)"还是"弹性轨道";`PaneChrome` 贡献契约;`rootChildSide` 语义侧判定 |
| `apps/desktop/src/components/pane-shell/tree/renderer/drag-session.ts` | **全应用通用的拖拽原语** `startDragSession` + pane/tab 的 resolver;阈值、rAF 合帧、ghost、Esc 中止、点击吞噬 |
| `apps/desktop/src/components/pane-shell/tree/renderer/floating-rect.ts` | 浮动 pane 的纯几何:视口内钳制、四角锚定、resize 跟边、CSS px 解析;`FLOATING_PLACEMENT = 'floating'` 常量 |
| `apps/desktop/src/components/pane-shell/tree/renderer/floating-panes.tsx` | `placement:'floating'` 的渲染器:树之上的 fixed 卡片,标题栏即拖拽把手,位置/折叠按 pane id 持久化 |
| `apps/desktop/src/components/pane-shell/tree/renderer/narrow-overlays.tsx` | 窄视口下 `collapsible` pane 离开网格,改成边缘 hover 条 / 事件唤出的浮层 |
| `apps/desktop/src/components/pane-shell/tree/renderer/layout-picker.tsx` | 预设卡片网格(缩略图是布局树的迷你渲染)+ "保存当前布局" + "新建网格布局" |
| `apps/desktop/src/components/pane-shell/tree/renderer/edit-bar.tsx` | 编辑模式的可拖动"Layouts"浮动面板(承载 layout-picker + 重置/完成) |
| `apps/desktop/src/components/pane-shell/tree/renderer/tab-strip-scroll.ts` | 纯函数 `tabStripScrollLeft` + `useActiveTabVisible`:保证激活标签(以及末尾的 "+")留在滚动窗内 |
| `apps/desktop/src/components/pane-shell/tree/renderer/lone-header.ts` | 35 行纯函数:单 pane 的 zone 什么时候**仍然**必须保留标题条(可关闭的 main tile / 工具面板) |

### 0.3 `apps/desktop/src/components/ui/`(60)

分四类点名。**每个文件都在下面出现一次全路径。**

**(A) shadcn/ui 近乎原样的 Radix 包装(19)** —— 逐个列全,见 §2.3 的 props 表:
`apps/desktop/src/components/ui/alert.tsx`(Alert/Title/Description)、
`apps/desktop/src/components/ui/badge.tsx`、
`apps/desktop/src/components/ui/button.tsx`(8 variant × 11 size 的 cva)、
`apps/desktop/src/components/ui/checkbox.tsx`、
`apps/desktop/src/components/ui/command.tsx`(cmdk 包装)、
`apps/desktop/src/components/ui/context-menu.tsx`、
`apps/desktop/src/components/ui/dropdown-menu.tsx`、
`apps/desktop/src/components/ui/pagination.tsx`、
`apps/desktop/src/components/ui/popover.tsx`、
`apps/desktop/src/components/ui/scroll-area.tsx`、
`apps/desktop/src/components/ui/select.tsx`、
`apps/desktop/src/components/ui/separator.tsx`、
`apps/desktop/src/components/ui/sheet.tsx`、
`apps/desktop/src/components/ui/sidebar.tsx`(24 导出,shadcn 里最大的一个组件)、
`apps/desktop/src/components/ui/skeleton.tsx`、
`apps/desktop/src/components/ui/switch.tsx`、
`apps/desktop/src/components/ui/tabs.tsx`、
`apps/desktop/src/components/ui/textarea.tsx`、
`apps/desktop/src/components/ui/tooltip.tsx`。

**(B) 表单/控件层(8)**:
`apps/desktop/src/components/ui/control.ts`(`controlVariants`,Input/Textarea/SelectTrigger 共用的外观基座)、
`apps/desktop/src/components/ui/input.tsx`(加了 prefix/suffix 装饰位)、
`apps/desktop/src/components/ui/sanitized-input.tsx`(每次击键跑 `sanitize`,永远只持有合法值)、
`apps/desktop/src/components/ui/search-field.tsx`(无框、聚焦才出下划线的唯一"页面级"搜索框)、
`apps/desktop/src/components/ui/segmented-control.tsx`(小型互斥选择)、
`apps/desktop/src/components/ui/field.tsx`(label + hint 包装)、
`apps/desktop/src/components/ui/color-swatches.tsx`(色板格 + 清除行)、
`apps/desktop/src/components/ui/split-button.tsx`(主操作 + 备选下拉,选过即成为新默认)。

**(C) 反馈/状态/排版(17)**:
`apps/desktop/src/components/ui/loader.tsx`(22 条数学曲线的粒子 loader)、
`apps/desktop/src/components/ui/glyph-spinner.tsx`(单字符 spinner,与 Ink TUI 同源)、
`apps/desktop/src/components/ui/status-pulse.tsx`(有间歇的有限脉冲,避免 CSS 无限动画吊住合成器)、
`apps/desktop/src/components/ui/progress.tsx`、
`apps/desktop/src/components/ui/skeleton.tsx` 的兄弟 `apps/desktop/src/components/ui/action-status.tsx`(idle→saving→done 的按钮文案/图标)、
`apps/desktop/src/components/ui/empty-state.tsx`、
`apps/desktop/src/components/ui/error-state.tsx`(ErrorIcon/ErrorBanner/ErrorState)、
`apps/desktop/src/components/ui/log-view.tsx`(19 行:全应用统一的原始日志外观)、
`apps/desktop/src/components/ui/decode-text.tsx`(乱码解码动画,CONNECTING 用)、
`apps/desktop/src/components/ui/fade-text.tsx`(溢出时 mask 渐隐而非省略号)、
`apps/desktop/src/components/ui/fade-scroll.tsx`(滚动容器上下边缘渐隐)、
`apps/desktop/src/components/ui/highlight-matches.tsx`(搜索命中高亮 `<mark>`)、
`apps/desktop/src/components/ui/diff-count.tsx`(`+A −B` 弹簧动画)、
`apps/desktop/src/components/ui/kbd.tsx`(Kbd/KbdGroup/KbdCombo)、
`apps/desktop/src/components/ui/codicon.tsx`(VS Code codicon 字体包装 + `codiconIcon()` 适配器)、
`apps/desktop/src/components/ui/tool-icon.tsx`(填充版工具图标,回落到 codicon 轮廓字体)、
`apps/desktop/src/components/ui/file-type-icon.tsx`(按 path/language 解析文件图标)。

**(D) 交互/结构/本项目自研(16)**:
`apps/desktop/src/components/ui/pane-tab.tsx`(**pane-shell 的标签条 shell**:PaneTab/Label/Strip/StripGlyph/`paneTabCloseItems`)、
`apps/desktop/src/components/ui/text-tab.tsx`(纯文字 tab + meta)、
`apps/desktop/src/components/ui/tab-dropdown.tsx`(窄屏把一排 tab 收成一个下拉)、
`apps/desktop/src/components/ui/actions-menu.tsx`(**MenuKit**:一份 items 同时产出 kebab 下拉与右键菜单)、
`apps/desktop/src/components/ui/title-menu-trigger.tsx`(紧凑 "Label ▾" 触发器)、
`apps/desktop/src/components/ui/dialog.tsx`(加了 banner / fitContent / 关闭按钮不自动聚焦)、
`apps/desktop/src/components/ui/dialog-portal-context.ts`(**对话框内 popover 的 portal 容器**,解决 DismissableLayer 误判"外部点击")、
`apps/desktop/src/components/ui/confirm-dialog.tsx`(带 ActionStatus 的确认对话框)、
`apps/desktop/src/components/ui/keyboard-first.ts`(`usePointerQuiet` 让停放的鼠标在 hover-select 列表里失效 + `releaseTypingFocus` 事件总线)、
`apps/desktop/src/components/ui/copy-button.tsx`(全应用统一的复制按钮,18 个 props)、
`apps/desktop/src/components/ui/generate-button.tsx`("AI 生成"闪光按钮,可中断)、
`apps/desktop/src/components/ui/row-button.tsx`(13 行:整行点击区,零样式)、
`apps/desktop/src/components/ui/disclosure-caret.tsx`(展开箭头)、
`apps/desktop/src/components/ui/drop-affordance.tsx`(11 行:全应用统一的虚线拖放面 class,pane-shell 的 zone 覆盖层也用它)、
`apps/desktop/src/components/ui/use-zoom-pan.ts`(headless 平移缩放变换)、
`apps/desktop/src/components/ui/zoomable.tsx`(点击展开 + 可缩放查看器)。

---

## 1. 这一簇解决什么问题

一句话:**把"一个 Electron 窗口里同时开好几个会话/工具面板"这件事,做成一棵可拖、可拆、可存、可分享的树。**

三层各自的问题:

- **`components/ui`** —— "同一个概念在应用里只有一种长相"。手段是把 shadcn/ui 抄进仓库(不是当依赖装),再在副本上做本地改动;`DESIGN.md` 把这些原语的名字列成"当前 API",要求改代码时同一提交更新文档。
- **`components/pane-shell`** —— "布局是数据,不是代码"。一棵 `split`/`group` 树是唯一真相:预设是树、用户拖出来的是树、网格编辑器产出的也是树;插件贡献一个 pane 就自动被"采纳"进树。拖放语义整体照抄 PowerToys FancyZones(连动画时长和敏感半径常量都照搬),网格编辑器照抄 FancyZones Editor。
- **`app/shell`** —— "窗口边框上的那一圈东西"。标题栏 / 状态栏都是**贡献点**,核心项和插件项走同一条渲染路径;状态栏项还能被用户右键逐个隐藏。

---

## 2. 接缝穷举(判据 2)

### 2.1 布局树的序列化模型与持久化字段(全表)

`apps/desktop/src/components/pane-shell/tree/model.ts:16 @ 863e313`

```ts
export type Orientation = 'row' | 'column'

export interface SplitNode {
  type: 'split'
  id: string
  orientation: Orientation
  children: LayoutNode[]
  /** Parallel to children; relative flex weights. */
  weights: number[]
}
```

`apps/desktop/src/components/pane-shell/tree/model.ts:27 @ 863e313`

```ts
export interface GroupNode {
  type: 'group'
  id: string
  /** Pane ids stacked in this group (rendered as tabs when > 1). */
  panes: string[]
  /** The visible pane. */
  active: string
  /** Collapsed to header strip (chevron restores). */
  minimized?: boolean
  /**
   * Header hidden entirely (double-click the header to hide, double-click the
   * zone's top edge to bring it back). Minimize always shows the header —
   * a minimized group IS its header.
   */
  headerHidden?: boolean
}
```

**只有两种节点、合计 9 个字段**,这就是整棵树的序列化面(没有版本号字段——版本走 storage key,见 2.2):

| 节点 | 字段 | 必填 | 校验规则(`isLayoutNode`) |
|---|---|---|---|
| split | `type` | 是 | 字面量 `'split'` |
| split | `id` | 是 | string |
| split | `orientation` | 是 | `'row'` \| `'column'` |
| split | `children` | 是 | 非空数组,每项递归合法 |
| split | `weights` | 是 | 数组,长度 == children,每项**有限且 > 0** |
| group | `type` | 是 | 字面量 `'group'` |
| group | `id` | 是 | string |
| group | `panes` | 是 | string[](**允许空数组** —— 编辑器产出的空 zone) |
| group | `active` | 是 | string(不要求 ∈ panes;`normalize` 负责纠正) |
| group | `minimized` | 否 | **不校验**(未在 `isLayoutNode` 中出现) |
| group | `headerHidden` | 否 | **不校验**(同上) |

`apps/desktop/src/components/pane-shell/tree/model.ts:554 @ 863e313`

```ts
export function isLayoutNode(value: unknown): value is LayoutNode {
  if (!value || typeof value !== 'object') {
    return false
  }

  const n = value as Record<string, unknown>

  if (n.type === 'group') {
    return (
      typeof n.id === 'string' &&
      Array.isArray(n.panes) &&
      n.panes.every(p => typeof p === 'string') &&
      typeof n.active === 'string'
    )
  }
```

> 两个可选布尔不被校验,意味着一个手改过的 localStorage 里 `minimized: "yes"` 会原样进入树,
> 后面全靠 `Boolean(node.minimized)` 兜住。**不是缺陷**(布尔真值化处处都做了),
> 但它说明校验器的契约是"结构合法",不是"字段类型完备"。

### 2.2 持久化键全表(8 个,机械枚举)

```verify
cd /home/user/hermes-agent
grep -rn "'hermes\.\|'sidebar_state'" $(cat /home/user/hermes-study/data/r10b/slices/G.txt)
# → 10 命中 / 8 个不同的键(其中 2 个是"退役即清空"的 v1)
```

| 键 | 写在哪 | 内容 | 备注 |
|---|---|---|---|
| `hermes.desktop.layoutTree.v2` | `apps/desktop/src/components/pane-shell/tree/store.ts:46`:`const STORAGE_KEY = 'hermes.desktop.layoutTree.v2'` | 当前布局树(JSON) | 副窗口(pop-out)**只读不写** |
| `hermes.desktop.layoutTree.v1` | `apps/desktop/src/components/pane-shell/tree/store.ts:48`:`writeKey('hermes.desktop.layoutTree.v1', null)` | —— | 模块加载即清空(整体退役) |
| `hermes.desktop.layoutPreset.active` | `apps/desktop/src/components/pane-shell/tree/store.ts:79`:`export const $activePresetId = atom<string>(readKey('hermes.desktop.layoutPreset.active') ?? 'default')` | 当前预设 id 或 `'custom'` | 驱动 picker 高亮 |
| `hermes.desktop.dismissedPanes.v1` | `apps/desktop/src/components/pane-shell/tree/store.ts:178`:`const DISMISSED_KEY = 'hermes.desktop.dismissedPanes.v1'` | 被"关掉且记住"的 pane id 列表 | 空集时写 null |
| `hermes.desktop.userPlacedPanes.v1` | `apps/desktop/src/components/pane-shell/tree/store.ts:1151`:`const USER_PLACED_KEY = 'hermes.desktop.userPlacedPanes.v1'` | 用户亲手拖过的 pane id | 自动 dock 从此绕开它们 |
| `hermes.desktop.layoutPresets.v2` | `apps/desktop/src/components/pane-shell/tree/presets.ts:20`:`const USER_KEY = 'hermes.desktop.layoutPresets.v2'` | 用户保存的命名预设 `{id: {name, tree}}` | 模块加载时逐个注册成贡献 |
| `hermes.desktop.layoutPresets.v1` | `apps/desktop/src/components/pane-shell/tree/presets.ts:22`:`writeKey('hermes.desktop.layoutPresets.v1', null)` | —— | 同样退役即清空 |
| `hermes.desktop.floatingPanes.v1` | `apps/desktop/src/components/pane-shell/tree/renderer/floating-panes.tsx:36`:`const POSITIONS_KEY = 'hermes.desktop.floatingPanes.v1'` | 浮动卡片的 `{x,y,collapsed}` | 按 pane id |
| **cookie** `sidebar_state` | `apps/desktop/src/components/ui/sidebar.tsx:18`:`const SIDEBAR_COOKIE_NAME = 'sidebar_state'` | shadcn 上游遗留 | **只写不读**,见 ■-2 |

**片外但相邻**:zone 的像素尺寸覆盖走 `hermes.desktop.paneStates.v1`(`apps/desktop/src/store/panes.ts`,`$paneStates.subscribe(persist)` 自动落盘)。这条在 ■-1 里是关键。

`apps/desktop/src/components/pane-shell/tree/store.ts:44 @ 863e313`

```ts
// v2: v1 trees were saved against placeholder panes with index-order zone
// assignment (chat could land in a corner cell). Retire them wholesale.
const STORAGE_KEY = 'hermes.desktop.layoutTree.v2'

writeKey('hermes.desktop.layoutTree.v1', null)
```

### 2.3 `components/ui` 的导出面与 props 契约(60 文件,215 导出名,179 个函数签名)

**机械枚举命令**(探针脚本随本轮 commit 进仓库,任何人可重跑):

```verify
cd /home/user/hermes-study
python3 data/r10b/probes/probe_g_ui_surface.py /home/user/hermes-agent | tail -1
# → FILES=60 EXPORTED_NAMES=215 EXPORTED_COMPONENTS=179
python3 data/r10b/probes/probe_g_ui_surface.py /home/user/hermes-agent --tsv \
  | awk -F'\t' 'NF>2{print $3}' | sort | uniq -c | sort -rn
# → 116 passthrough / 38 named / 11 inline / 10 mixed / 4 none
```

props 契约的**四类**(这是本片对"组件 props 契约"这条接缝的分类口径):

| 类 | 数 | 含义 |
|---|---|---|
| `passthrough` | 116 | 注解是 `React.ComponentProps<'tag'>` 或 `ComponentProps<typeof Primitive>`(可再 `& {...}` 扩几个自有键)。**契约 = 宿主元素/Radix 原语的全部 props + 列出的扩展键** |
| `named` | 38 | 具名 `interface`/`type`,字段可逐个枚举(下表给全) |
| `inline` | 11 | 内联对象字面量,字段即注解本身 |
| `mixed` | 10 | 多参函数 / 泛型 / 非组件辅助函数(`renderActionItem`、`scrollEdges`、`codiconIcon`…) |
| `none` | 4 | 无参:三个 hook(`usePointerQuiet`、`useSidebar`、`useZoomPan`)+ `releaseTypingFocus` |

**全表**(60 文件 × 导出名 × 每个函数签名的 props 注解;`<extends …>` 是继承子句,`<= …>` 是类型别名的右值):

```text
action-status.tsx  [exports 1 / fn 1]
   exports: ActionStatus
     ActionStatus [inline] { state: 'done' | 'idle' | 'saving' idle: string busy: string done: string idleIcon?: ReactNode }

actions-menu.tsx  [exports 7 / fn 3]
   exports: ActionItemSpec, ActionsContextMenu, ActionsMenu, CONTEXT_KIT, DROPDOWN_KIT, MenuKit, renderActionItem
     renderActionItem [mixed] MenuKit, { className, disabled, icon, iconNode, key, label, onSelect, variant }: ActionItemSpec
     ActionsMenu [named] ActionsMenuProps | fields: children, items, ariaLabel?, contentClassName?, open?, onOpenChange?, <extends Pick< React.ComponentProps<typeof DropdownMenuContent>, 'align' | 'side' | 'sideOffset' >>
     ActionsContextMenu [named] ActionsContextMenuProps | fields: children, items, ariaLabel?, contentClassName?, disabled?

alert.tsx  [exports 3 / fn 3]
   exports: Alert, AlertDescription, AlertTitle
     Alert [passthrough] React.ComponentProps<'div'> & VariantProps<typeof alertVariants>
     AlertTitle [passthrough] React.ComponentProps<'div'>
     AlertDescription [passthrough] React.ComponentProps<'div'>

badge.tsx  [exports 3 / fn 1]
   exports: Badge, BadgeProps, badgeVariants
     Badge [named] BadgeProps | fields: asChild?, <extends React.ComponentProps<'span'>, VariantProps<typeof badgeVariants>>

button.tsx  [exports 2 / fn 1]
   exports: Button, buttonVariants
     Button [passthrough] React.ComponentProps<'button'> & VariantProps<typeof buttonVariants> & { asChild?: boolean }

checkbox.tsx  [exports 1 / fn 1]
   exports: Checkbox
     Checkbox [passthrough] React.ComponentProps<typeof CheckboxPrimitive.Root>

codicon.tsx  [exports 3 / fn 2]
   exports: Codicon, CodiconProps, codiconIcon
     Codicon [named] CodiconProps | fields: name, size?, spinning?, <extends React.HTMLAttributes<HTMLElement>>
     codiconIcon [mixed] string

color-swatches.tsx  [exports 1 / fn 1]
   exports: ColorSwatches
     ColorSwatches [named] ColorSwatchesProps | fields: swatches, value, onChange, clearLabel, clearIcon?, swatchLabel?

command.tsx  [exports 8 / fn 8]
   exports: Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator, CommandShortcut
     Command [passthrough] React.ComponentProps<typeof CommandPrimitive>
     CommandInput [named] CommandInputProps | fields: right?, <extends React.ComponentProps<typeof CommandPrimitive.Input>>
     CommandList [passthrough] React.ComponentProps<typeof CommandPrimitive.List>
     CommandEmpty [passthrough] React.ComponentProps<typeof CommandPrimitive.Empty>
     CommandGroup [passthrough] React.ComponentProps<typeof CommandPrimitive.Group>
     CommandSeparator [passthrough] React.ComponentProps<typeof CommandPrimitive.Separator>
     CommandItem [passthrough] React.ComponentProps<typeof CommandPrimitive.Item>
     CommandShortcut [passthrough] React.ComponentProps<'span'>

confirm-dialog.tsx  [exports 1 / fn 1]
   exports: ConfirmDialog
     ConfirmDialog [named] ConfirmDialogProps | fields: open, onClose, onConfirm, title, description?, confirmLabel?, busyLabel?, doneLabel?, cancelLabel?, destructive?, dismissOnConfirm?

context-menu.tsx  [exports 12 / fn 12]
   exports: ContextMenu, ContextMenuCheckboxItem, ContextMenuContent, ContextMenuGroup, ContextMenuItem, ContextMenuLabel, ContextMenuPortal, ContextMenuSeparator, ContextMenuSub, ContextMenuSubContent, ContextMenuSubTrigger, ContextMenuTrigger
     ContextMenu [passthrough] React.ComponentProps<typeof ContextMenuPrimitive.Root>
     ContextMenuPortal [passthrough] React.ComponentProps<typeof ContextMenuPrimitive.Portal>
     ContextMenuTrigger [passthrough] React.ComponentProps<typeof ContextMenuPrimitive.Trigger>
     ContextMenuGroup [passthrough] React.ComponentProps<typeof ContextMenuPrimitive.Group>
     ContextMenuContent [passthrough] React.ComponentProps<typeof ContextMenuPrimitive.Content>
     ContextMenuItem [passthrough] React.ComponentProps<typeof ContextMenuPrimitive.Item> & { inset?: boolean variant?: 'default' | 'destructive' }
     ContextMenuCheckboxItem [passthrough] React.ComponentProps<typeof ContextMenuPrimitive.CheckboxItem>
     ContextMenuLabel [passthrough] React.ComponentProps<typeof ContextMenuPrimitive.Label> & { inset?: boolean }
     ContextMenuSeparator [passthrough] React.ComponentProps<typeof ContextMenuPrimitive.Separator>
     ContextMenuSub [passthrough] React.ComponentProps<typeof ContextMenuPrimitive.Sub>
     ContextMenuSubTrigger [passthrough] React.ComponentProps<typeof ContextMenuPrimitive.SubTrigger> & { inset?: boolean }
     ContextMenuSubContent [passthrough] React.ComponentProps<typeof ContextMenuPrimitive.SubContent>

control.ts  [exports 2 / fn 0]
   exports: ControlVariantProps, controlVariants

copy-button.tsx  [exports 2 / fn 1]
   exports: CopyButton, CopyButtonProps
     CopyButton [named] CopyButtonProps | fields: appearance?, buttonSize?, buttonVariant?, children?, className?, disabled?, errorMessage?, haptic?, iconClassName?, label?, onCopied?, onCopyError?, preventDefault?, showLabel?, side?, stopPropagation?, text, title?

decode-text.tsx  [exports 3 / fn 1]
   exports: DECODE_SCRAMBLE_CHARS, DecodeText, DecodeTextProps
     DecodeText [named] DecodeTextProps | fields: text, prefix?, active?, loop?, cursor?, <extends Omit<ComponentProps<'span'>, 'prefix'>>

dialog-portal-context.ts  [exports 2 / fn 1]
   exports: DialogPortalContainerContext, usePopoverPortalContainer
     usePopoverPortalContainer [mixed] HTMLElement | null

dialog.tsx  [exports 11 / fn 11]
   exports: Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogOverlay, DialogPortal, DialogTitle, DialogTrigger, preventCloseButtonAutoFocus
     Dialog [passthrough] React.ComponentProps<typeof DialogPrimitive.Root>
     DialogTrigger [passthrough] React.ComponentProps<typeof DialogPrimitive.Trigger>
     DialogPortal [passthrough] React.ComponentProps<typeof DialogPrimitive.Portal>
     DialogClose [passthrough] React.ComponentProps<typeof DialogPrimitive.Close>
     DialogOverlay [passthrough] React.ComponentProps<typeof DialogPrimitive.Overlay>
     preventCloseButtonAutoFocus [named] Event
     DialogContent [passthrough] React.ComponentProps<typeof DialogPrimitive.Content> & { showCloseButton?: boolean fitContent?: boolean bodyClassName?: string banner?: React.ReactNode bannerTone?: DialogBannerTone }
     DialogHeader [passthrough] React.ComponentProps<'div'>
     DialogFooter [passthrough] React.ComponentProps<'div'>
     DialogTitle [passthrough] React.ComponentProps<typeof DialogPrimitive.Title> & { icon?: React.ComponentType<{ className?: string }> }
     DialogDescription [passthrough] React.ComponentProps<typeof DialogPrimitive.Description>

diff-count.tsx  [exports 1 / fn 1]
   exports: DiffCount
     DiffCount [named] DiffCountProps | fields: added, removed, className?

disclosure-caret.tsx  [exports 1 / fn 1]
   exports: DisclosureCaret
     DisclosureCaret [named] DisclosureCaretProps | fields: open, <extends Omit<CodiconProps, 'name'>>

drop-affordance.tsx  [exports 2 / fn 0]
   exports: DROP_SHEET_BLUR_CLASS, DROP_SHEET_CLASS

dropdown-menu.tsx  [exports 18 / fn 16]
   exports: DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuPortal, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSearch, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger, dropdownMenuRow, dropdownMenuSectionLabel
     DropdownMenu [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.Root>
     DropdownMenuPortal [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.Portal>
     DropdownMenuTrigger [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.Trigger>
     DropdownMenuSearch [passthrough] Omit<React.ComponentProps<'input'>, 'type'> & { onValueChange?: (value: string) => void }
     DropdownMenuContent [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.Content>
     DropdownMenuGroup [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.Group>
     DropdownMenuItem [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.Item> & { inset?: boolean variant?: 'default' | 'destructive' }
     DropdownMenuCheckboxItem [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.CheckboxItem>
     DropdownMenuRadioGroup [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.RadioGroup>
     DropdownMenuRadioItem [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.RadioItem>
     DropdownMenuLabel [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.Label> & { inset?: boolean }
     DropdownMenuSeparator [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.Separator>
     DropdownMenuShortcut [passthrough] React.ComponentProps<'span'>
     DropdownMenuSub [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.Sub>
     DropdownMenuSubTrigger [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.SubTrigger> & { inset?: boolean hideChevron?: boolean }
     DropdownMenuSubContent [passthrough] React.ComponentProps<typeof DropdownMenuPrimitive.SubContent>

empty-state.tsx  [exports 1 / fn 1]
   exports: EmptyState
     EmptyState [inline] { title: string description?: string className?: string }

error-state.tsx  [exports 4 / fn 3]
   exports: ErrorBanner, ErrorIcon, ErrorState, ErrorStateProps
     ErrorIcon [inline] { className?: string; size?: string }
     ErrorBanner [inline] { children: ReactNode; className?: string }
     ErrorState [named] ErrorStateProps | fields: children?, className?, description?, icon?, title

fade-scroll.tsx  [exports 4 / fn 3]
   exports: FadeEdges, FadeScroll, edgeMask, scrollEdges
     edgeMask [named] FadeEdges | fields: above, below
     scrollEdges [mixed] Pick<HTMLElement, 'clientHeight' | 'scrollHeight' | 'scrollTop'>
     FadeScroll [inline] { children: ReactNode className?: string deps?: unknown maxHeight?: string }

fade-text.tsx  [exports 1 / fn 1]
   exports: FadeText
     FadeText [named] FadeTextProps | fields: children, fadeWidth?, <extends Omit<ComponentProps<'span'>, 'children'>>

field.tsx  [exports 2 / fn 2]
   exports: Field, FieldHint
     Field [inline] { children: ReactNode htmlFor?: string label: ReactNode optional?: boolean optionalLabel?: string }
     FieldHint [inline] { children: ReactNode; error?: boolean }

file-type-icon.tsx  [exports 2 / fn 1]
   exports: FileTypeIcon, FileTypeIconProps
     FileTypeIcon [named] FileTypeIconProps | fields: language?, path?, <extends Omit<ToolIconProps, 'name'>>

generate-button.tsx  [exports 1 / fn 1]
   exports: GenerateButton
     GenerateButton [named] GenerateButtonProps | fields: generating, onGenerate, onCancel?, label, generatingLabel?, iconSize?, <extends Omit<React.ComponentProps<typeof Button>, 'children' | 'onClick'>>

glyph-spinner.tsx  [exports 1 / fn 1]
   exports: GlyphSpinner
     GlyphSpinner [named] GlyphSpinnerProps | fields: ariaLabel?, className?, spinner?

highlight-matches.tsx  [exports 1 / fn 1]
   exports: HighlightMatches
     HighlightMatches [inline] { className?: string query: string | string[] text: string }

input.tsx  [exports 1 / fn 1]
   exports: Input
     Input [named] InputProps | fields: prefix?, suffix?, containerClassName?, <= Omit<React.ComponentProps<'input'>, 'size' | 'prefix' | 'suffix'> & ControlVariantProps & {…}>

kbd.tsx  [exports 4 / fn 3]
   exports: Kbd, KbdCombo, KbdGroup, kbdVariants
     Kbd [named] KbdProps | fields: <extends React.ComponentProps<'kbd'>, VariantProps<typeof kbdVariants>>
     KbdGroup [named] KbdGroupProps | fields: keys, <extends Omit<React.ComponentProps<'span'>, 'children'>, VariantProps<typeof kbdVariants>>
     KbdCombo [named] KbdComboProps | fields: combo, <extends Omit<KbdGroupProps, 'keys'>>

keyboard-first.ts  [exports 3 / fn 3]
   exports: onReleaseTypingFocus, releaseTypingFocus, usePointerQuiet
     usePointerQuiet [none]
     releaseTypingFocus [none]
     onReleaseTypingFocus [mixed] () => void

loader.tsx  [exports 3 / fn 1]
   exports: LOADER_TYPES, Loader, LoaderType
     Loader [named] LoaderProps | fields: label?, pathSteps?, strokeScale?, type?, <extends Omit<ComponentProps<'div'>, 'children'>>

log-view.tsx  [exports 1 / fn 1]
   exports: LogView
     LogView [passthrough] ComponentProps<'div'>

pagination.tsx  [exports 7 / fn 7]
   exports: Pagination, PaginationButton, PaginationContent, PaginationEllipsis, PaginationItem, PaginationNext, PaginationPrevious
     Pagination [passthrough] React.ComponentProps<'nav'>
     PaginationContent [passthrough] React.ComponentProps<'ul'>
     PaginationItem [passthrough] React.ComponentProps<'li'>
     PaginationButton [named] PaginationButtonProps | fields: isActive?, <extends React.ComponentProps<'button'>>
     PaginationPrevious [passthrough] React.ComponentProps<'button'>
     PaginationNext [passthrough] React.ComponentProps<'button'>
     PaginationEllipsis [passthrough] React.ComponentProps<'span'>

pane-tab.tsx  [exports 9 / fn 5]
   exports: PANE_TAB_STRIP_LINE_LEFT, PANE_TAB_STRIP_LINE_RIGHT, PaneStripGlyph, PaneStripTool, PaneTab, PaneTabCloseCounts, PaneTabLabel, PaneTabStrip, paneTabCloseItems
     PaneTab [named] PaneTabProps | fields: active?, dirty?, onClose?, selected?, vertical?, side?, <extends React.ComponentProps<'div'>>
     PaneTabLabel [named] PaneTabLabelProps | fields: as?, <extends React.ComponentProps<'button'>>
     PaneTabStrip [named] PaneTabStripProps | fields: children, listRef?, trailing?, <extends React.ComponentProps<'div'>>
     PaneStripGlyph [mixed] Omit<PaneStripTool, 'id'>
     paneTabCloseItems [mixed] MenuKit, { counts, onClose, onCloseAll, onCloseOthers, onCloseToRight }: PaneTabCloseItemsOptions

popover.tsx  [exports 4 / fn 4]
   exports: Popover, PopoverAnchor, PopoverContent, PopoverTrigger
     Popover [passthrough] React.ComponentProps<typeof PopoverPrimitive.Root>
     PopoverTrigger [passthrough] React.ComponentProps<typeof PopoverPrimitive.Trigger>
     PopoverAnchor [passthrough] React.ComponentProps<typeof PopoverPrimitive.Anchor>
     PopoverContent [passthrough] React.ComponentProps<typeof PopoverPrimitive.Content>

progress.tsx  [exports 2 / fn 1]
   exports: Progress, ProgressProps
     Progress [named] ProgressProps | fields: value?, indeterminate?, animated?, destructive?, size?, fillClassName?, fillStyle?, children?, <extends Omit<React.ComponentProps<'div'>, 'children'>>

row-button.tsx  [exports 1 / fn 1]
   exports: RowButton
     RowButton [passthrough] React.ComponentProps<'button'>

sanitized-input.tsx  [exports 1 / fn 1]
   exports: SanitizedInput
     SanitizedInput [named] SanitizedInputProps | fields: value, onValueChange, sanitize, <extends Omit<React.ComponentProps<typeof Input>, 'onChange' | 'value'>>

scroll-area.tsx  [exports 2 / fn 2]
   exports: ScrollArea, ScrollBar
     ScrollArea [passthrough] React.ComponentProps<typeof ScrollAreaPrimitive.Root>
     ScrollBar [passthrough] React.ComponentProps<typeof ScrollAreaPrimitive.ScrollAreaScrollbar>

search-field.tsx  [exports 1 / fn 1]
   exports: SearchField
     SearchField [named] SearchFieldProps | fields: placeholder, value, onChange, hints?, containerClassName?, inputClassName?, loading?, onClear?, inputRef?, trailingAction?

segmented-control.tsx  [exports 2 / fn 1]
   exports: SegmentedControl, SegmentedControlOption
     SegmentedControl [mixed] SegmentedControlProps<T>

select.tsx  [exports 7 / fn 7]
   exports: Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue
     Select [passthrough] React.ComponentProps<typeof SelectPrimitive.Root>
     SelectTrigger [passthrough] React.ComponentProps<typeof SelectPrimitive.Trigger> & ControlVariantProps
     SelectValue [passthrough] React.ComponentProps<typeof SelectPrimitive.Value>
     SelectContent [passthrough] React.ComponentProps<typeof SelectPrimitive.Content>
     SelectGroup [passthrough] React.ComponentProps<typeof SelectPrimitive.Group>
     SelectLabel [passthrough] React.ComponentProps<typeof SelectPrimitive.Label>
     SelectItem [passthrough] React.ComponentProps<typeof SelectPrimitive.Item>

separator.tsx  [exports 1 / fn 1]
   exports: Separator
     Separator [passthrough] React.ComponentProps<typeof SeparatorPrimitive.Root>

sheet.tsx  [exports 8 / fn 8]
   exports: Sheet, SheetClose, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle, SheetTrigger
     Sheet [passthrough] React.ComponentProps<typeof SheetPrimitive.Root>
     SheetTrigger [passthrough] React.ComponentProps<typeof SheetPrimitive.Trigger>
     SheetClose [passthrough] React.ComponentProps<typeof SheetPrimitive.Close>
     SheetContent [passthrough] React.ComponentProps<typeof SheetPrimitive.Content> & { side?: 'top' | 'right' | 'bottom' | 'left' showCloseButton?: boolean }
     SheetHeader [passthrough] React.ComponentProps<'div'>
     SheetFooter [passthrough] React.ComponentProps<'div'>
     SheetTitle [passthrough] React.ComponentProps<typeof SheetPrimitive.Title>
     SheetDescription [passthrough] React.ComponentProps<typeof SheetPrimitive.Description>

sidebar.tsx  [exports 24 / fn 24]
   exports: Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupAction, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarInput, SidebarInset, SidebarMenu, SidebarMenuAction, SidebarMenuBadge, SidebarMenuButton, SidebarMenuItem, SidebarMenuSkeleton, SidebarMenuSub, SidebarMenuSubButton, SidebarMenuSubItem, SidebarProvider, SidebarRail, SidebarSeparator, SidebarTrigger, useSidebar
     useSidebar [none]
     SidebarProvider [passthrough] React.ComponentProps<'div'> & { defaultOpen?: boolean open?: boolean onOpenChange?: (open: boolean) => void }
     Sidebar [passthrough] React.ComponentProps<'div'> & { side?: 'left' | 'right' variant?: 'sidebar' | 'floating' | 'inset' collapsible?: 'offcanvas' | 'icon' | 'none' }
     SidebarTrigger [passthrough] React.ComponentProps<typeof Button>
     SidebarRail [passthrough] React.ComponentProps<'button'>
     SidebarInset [passthrough] React.ComponentProps<'main'>
     SidebarInput [passthrough] React.ComponentProps<typeof Input>
     SidebarHeader [passthrough] React.ComponentProps<'div'>
     SidebarFooter [passthrough] React.ComponentProps<'div'>
     SidebarSeparator [passthrough] React.ComponentProps<typeof Separator>
     SidebarContent [passthrough] React.ComponentProps<'div'>
     SidebarGroup [passthrough] React.ComponentProps<'div'>
     SidebarGroupLabel [passthrough] React.ComponentProps<'div'> & { asChild?: boolean }
     SidebarGroupAction [passthrough] React.ComponentProps<'button'> & { asChild?: boolean }
     SidebarGroupContent [passthrough] React.ComponentProps<'div'>
     SidebarMenu [passthrough] React.ComponentProps<'ul'>
     SidebarMenuItem [passthrough] React.ComponentProps<'li'>
     SidebarMenuButton [passthrough] React.ComponentProps<'button'> & { asChild?: boolean isActive?: boolean tooltip?: string | React.ComponentProps<typeof TooltipContent> } & VariantProps<typeof sidebarMenuButtonVariants>
     SidebarMenuAction [passthrough] React.ComponentProps<'button'> & { asChild?: boolean showOnHover?: boolean }
     SidebarMenuBadge [passthrough] React.ComponentProps<'div'>
     SidebarMenuSkeleton [passthrough] React.ComponentProps<'div'> & { showIcon?: boolean }
     SidebarMenuSub [passthrough] React.ComponentProps<'ul'>
     SidebarMenuSubItem [passthrough] React.ComponentProps<'li'>
     SidebarMenuSubButton [passthrough] React.ComponentProps<'a'> & { asChild?: boolean size?: 'sm' | 'md' isActive?: boolean }

skeleton.tsx  [exports 2 / fn 2]
   exports: CountSkeleton, Skeleton
     Skeleton [passthrough] React.ComponentProps<'div'>
     CountSkeleton [passthrough] React.ComponentProps<'span'>

split-button.tsx  [exports 2 / fn 1]
   exports: SplitButton, SplitButtonAction
     SplitButton [named] SplitButtonProps | fields: actions, value, onValueChange, onTrigger, disabled?, className?, primaryIcon?, variant?, size?

status-pulse.tsx  [exports 2 / fn 1]
   exports: StatusPulse, StatusPulseProps
     StatusPulse [named] StatusPulseProps | fields: kind, opacity?, <extends Omit<ComponentProps<'span'>, 'children' | 'ref'>>

switch.tsx  [exports 1 / fn 1]
   exports: Switch
     Switch [passthrough] React.ComponentProps<typeof SwitchPrimitive.Root> & VariantProps<typeof switchVariants>

tab-dropdown.tsx  [exports 6 / fn 3]
   exports: ResponsiveTab, ResponsiveTabs, TabDropdown, TabDropdownItem, TabMeta, tabMetaContent
     tabMetaContent [mixed] number | string | null
     TabDropdown [inline] { align?: 'center' | 'end' | 'start' className?: string items: TabDropdownItem[] }
     ResponsiveTabs [inline] { align?: 'center' | 'end' | 'start' onChange: (id: string) => void tabs: ResponsiveTab[] value: string wideClassName?: string }

tabs.tsx  [exports 3 / fn 3]
   exports: Tabs, TabsList, TabsTrigger
     Tabs [passthrough] React.ComponentProps<typeof TabsPrimitive.Root>
     TabsList [passthrough] React.ComponentProps<typeof TabsPrimitive.List>
     TabsTrigger [passthrough] React.ComponentProps<typeof TabsPrimitive.Trigger>

text-tab.tsx  [exports 2 / fn 2]
   exports: TextTab, TextTabMeta
     TextTabMeta [passthrough] React.ComponentProps<'span'>
     TextTab [named] TextTabProps | fields: active?, <extends React.ComponentProps<'button'>>

textarea.tsx  [exports 1 / fn 1]
   exports: Textarea
     Textarea [passthrough] React.ComponentProps<'textarea'> & ControlVariantProps

title-menu-trigger.tsx  [exports 1 / fn 1]
   exports: TitleMenuTrigger
     TitleMenuTrigger [passthrough] Omit<React.ComponentProps<typeof Button>, 'children' | 'size' | 'variant'> & { children: React.ReactNode }

tool-icon.tsx  [exports 2 / fn 1]
   exports: ToolIcon, ToolIconProps
     ToolIcon [named] ToolIconProps | fields: className?, name, size?

tooltip.tsx  [exports 9 / fn 9]
   exports: RootTooltipProvider, Tip, TipHintLabel, TipKeybindLabel, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger, suppressNonKeyboardFocusOpen
     TooltipProvider [passthrough] React.ComponentProps<typeof TooltipPrimitive.Provider>
     Tooltip [passthrough] React.ComponentProps<typeof TooltipPrimitive.Root>
     suppressNonKeyboardFocusOpen [mixed] React.FocusEvent<HTMLElement>, modality: InputModality = lastInputModality()
     TooltipTrigger [passthrough] React.ComponentProps<typeof TooltipPrimitive.Trigger>
     TooltipContent [passthrough] React.ComponentProps<typeof TooltipPrimitive.Content>
     Tip [named] TipProps | fields: label, children, delayDuration?, <extends Omit<React.ComponentProps<typeof TooltipPrimitive.Content>, 'content'>>
     RootTooltipProvider [inline] { children: React.ReactNode }
     TipHintLabel [named] TipHintLabelProps | fields: text, hint?
     TipKeybindLabel [named] TipKeybindLabelProps | fields: actionId, text?

use-zoom-pan.ts  [exports 1 / fn 1]
   exports: useZoomPan
     useZoomPan [none]

zoomable.tsx  [exports 1 / fn 1]
   exports: Zoomable
     Zoomable [named] ZoomableProps | fields: children, overlay?, onCopy?, label?, className?
```

**自评达成度:导出名 215/215(100%)已列全;props 契约 179/179 的注解已列全。**
未达成的部分要如实说:`passthrough` 的 116 个,我给出的是**注解本身**(即"= 该 DOM 标签 / 该 Radix 原语的全部 props + 扩展键"),
**没有把 Radix 原语的 props 逐个展开**——那要读 `radix-ui@1.6.7` 的类型,已经越过基线仓库的边界。
按"本仓库内可枚举的接口面"这个口径,这一条是 **100% 覆盖**;按"读者拿到就能不查文档写调用"的口径,大约 **65%**(63/179 的字段是逐个列出的)。

### 2.4 `tree/store.ts` 的动作面(79 个导出,全表)

```verify
cd /home/user/hermes-agent
grep -cE "^export (const|function|type|interface) " \
  apps/desktop/src/components/pane-shell/tree/store.ts
# → 79
```

**18 个原子 / computed**(读):`$activePresetId` `$activeTreeGroup` `$collapsedTreeSides` `$dismissedPanes` `$dropHint` `$hiddenTreePanes` `$hoveredTreeGroup` `$layoutTree` `$narrowViewport` `$newSessionTabAction` `$paneVisible(id)` `$panesWithCloser` `$sessionTileDragging` `$sessionTileEdgeHover` `$stripToolsRevision` `$treeDragging` `$treePaneEpochs` `$userPlacedPanes`

**3 个类型/常量**:`DropHint` `TreeSide` `SESSION_TILE_DRAG`

**58 个函数**,按语义分组:

| 组 | 成员 |
|---|---|
| 结构编辑 | `moveTreePane` `moveTreePanes` `mergeTreeZones` `reorderTreePanes` `removeTreePane` `dockPaneBeside` `mirrorLayoutTree` `setTreeSplitWeights` |
| 激活 / 标签页 | `activateTreePane` `activateTreeTabSlot` `cycleTreeTabInFocusedZone` `focusedSessionTabAnchor` `treeTabCloseTargets` |
| 关闭语义(五条不同路径) | `closeTabPane` `closeTreePane` `closeToolPane` `dismissTreePane` `closeAllTreeTabs` `closeOtherTreeTabs` `closeTreeTabsToRight` `closeFocusedSessionTab` `closeFocusedToolTab` |
| 可见 / 折叠 | `setTreePaneHidden` `revealTreePane` `restoreTreePane` `togglePaneVisible` `isPaneVisible` `setPaneCollapsed` `collapseTreePane` `setTreeGroupMinimized` `setTreeGroupHeaderHidden` `setTreeSideCollapsed` `layoutHasRootSide` |
| 绑定(应用 store ⇄ 树) | `bindPaneVisibility` `bindToolPaneCollapse` `bindTreeSideVisibility` `registerPaneCloser` `registerPaneOpener` `registerLayoutResetHandler` `markCollapsePane` `isCollapsePane` |
| 采纳 / 预设 / 重置 | `declareDefaultTree` `watchContributedPanes` `applyTree` `markActivePreset` `presetSplitWeights` `resetLayoutTree` `persistTree` |
| 焦点追踪 | `trackActiveTreeGroup` `noteActiveTreeGroup` `noteHoveredTreeGroup` |
| 查询 / 谓词 | `paneRootSide` `treeSideOfPane` `treePanesWithPrefix` `isSessionStripPane` `isMainStripPane` |
| 其它 | `reloadTreePane` `invalidateStripTools` |

### 2.5 pane 贡献契约 `PaneChrome`(16 键 + 2 键在别处读)

这是**插件与核心共用**的 pane 声明面,定义在 `apps/desktop/src/components/pane-shell/tree/renderer/track-model.ts`:

| 键 | 类型 | 作用 |
|---|---|---|
| `width` / `height` | `string` | 声明了就是**固定轨道**(侧栏语义),没声明就按 weight 分剩余空间 |
| `minWidth` / `maxWidth` / `minHeight` / `maxHeight` | `string` | 沿所在 split 轴生效的钳制 |
| `collapsible` | `boolean` | 窄视口下离开网格,改为边缘浮层 |
| `revealAliases` | `string[]` | 接受 `PANE_TOGGLE_REVEAL_EVENT` 的额外 id |
| `placement` | `string` | 语义角色;**含非平铺值 `'floating'`**(见 ▲-1) |
| `anchor` | `FloatingAnchor` | floating 的初始角落,默认 `'top-right'` |
| `uncloseable` | `boolean` | 标签菜单里不出现 Close(只有主 workspace) |
| `tabWrap` | `(tab) => ReactNode` | 用领域右键菜单包住这个 pane 的**标签** |
| `tabDrag` | `(e, onTap, double) => boolean` | 接管本 pane 标签的拖拽;返回 false 回落到通用 pane move |
| `headerVeto` | `boolean` | 该 pane 激活时压掉整条标题条(整页视图) |
| `tabLead` | `() => ReactNode` | 标签文字前的自订节点(会话状态点) |
| `stripTools` | `() => readonly PaneStripTool[]` | 该 pane 激活时贡献到标签条尾部的字形按钮 |
| **`dock`**(不在 `PaneChrome` 里) | `{pane, pos, before?}` | 采纳时的落点手势,类型 `PaneDockHint` 定义在 `apps/desktop/src/components/pane-shell/tree/store.ts` |
| **`revealOnPreset`**(同上) | `boolean` | 应用预设时通过 opener 打开该 pane |

`apps/desktop/src/components/pane-shell/tree/renderer/track-model.ts:54 @ 863e313`

```ts
  /** Tiling role in the tree, or `'floating'` — the one NON-tiling placement:
   *  the pane is excluded from the tree entirely and rendered as a fixed card
   *  above it (see renderer/floating-panes.tsx). A floating pane takes no
   *  space from any zone, has no tab, and can't be docked or split. */
  placement?: string
  /** Spawn corner for `placement: 'floating'` (default `'top-right'`). The
   *  pane also TRACKS that corner's edges when the window resizes. */
```

`apps/desktop/src/components/pane-shell/tree/store.ts:1073 @ 863e313`

```ts
  // `placement: 'floating'` opts OUT of the tree entirely — those panes render
  // as fixed cards above it (renderer/floating-panes.tsx). Adopting one would
  // turn it into a track that steals width from a zone, which is the whole
  // thing floating exists to avoid.
  const missing = panes.filter(
    c => !inTree.has(c.id) && !dismissed.has(c.id) && placementOf(c.id) !== FLOATING_PLACEMENT
  )
```

### 2.6 DOM 契约(data-* 属性全表)

pane-shell 里 JS 与 CSS 通过 DOM 属性通信,这是它的"事件表"。机械枚举:

```verify
cd /home/user/hermes-agent
grep -rhoE "data-[a-z0-9-]+" $(sed 's|^|/home/user/hermes-agent/|' \
  /home/user/hermes-study/data/r10b/slices/G.txt | grep pane-shell) | sort | uniq -c | sort -rn
```

| 属性 | 写在 | 谁读 | 语义 |
|---|---|---|---|
| `data-tree-group="<groupId>"` | tree-group 根 div | `snapshotZones()`、`trackActiveTreeGroup`、sash 找 zone 元素 | zone 的身份 + 拖拽命中矩形来源 |
| `data-tree-tab="<paneId>"` | 每个 PaneTab | `stripSlots()`、`StripDropCaret`、`useActiveTabVisible`、右键定位 | 标签的身份 |
| `data-zone-tabstrip="<groupId>"` | PaneTabStrip | `snapshotStrips()` | "落在这里 = 入栈到某个槽位",压过径向的 top 边判定 |
| `data-tree-split="<splitId>"` | TreeSplit 容器 | (仅调试/样式) | split 身份 |
| `data-pane-hidden` | 非激活标签的内容层 | `queryVisible/queryAllVisible` | keep-alive 隐藏层的标记,全文档查找必须跳过它 |
| `data-zone-header` | tree-group 根 div | `styles.css` 的 `[data-pane-self-label]` | 告诉 pane"你已经有标题条了,别自己再画名字" |
| `data-session-anchor="workspace"` | (片外,chat 侧) | `publishWorkspaceGeometry` | 量 workspace 边缘 → `--workspace-left/right` |
| `data-floating-pane="<paneId>"` | 浮动卡片 | (测试) | 浮动 pane 身份 |
| `data-floating-no-drag` | 浮动卡片头里的按钮 | `onPointerDown` 早退 | 头部是拖拽把手,这个子树不是 |
| `data-resizer="<i>"` | 网格编辑器的 resizer | `onCanvasPointerDown` 早退 | 画布空白 vs resizer 的区分 |

跨界事件(非 DOM 属性):`hermes:pane-toggle-reveal`(`apps/desktop/src/components/pane-shell/index.ts` 定义,narrow-overlays 监听),`hermes:release-typing-focus`(`apps/desktop/src/components/ui/keyboard-first.ts`)。

### 2.7 状态栏 / 标题栏贡献契约

`StatusbarItem`(20 键,`apps/desktop/src/app/shell/statusbar-controls.tsx`):
`id` `render` `label` `detail` `icon` `className` `disabled` `hidden` `href` `menuAlign` `menuClassName` `menuContent` `menuItems` `onSelect` `actionId` `title` `to` `variant`('action'|'link'|'menu'|'text') `toggleLabel` `lockedVisible`。
`StatusbarMenuItem`(9 键):`id` `icon` `label` `className` `disabled` `hidden` `href` `onSelect` `title` `to`。

`TitlebarTool`(11 键,`apps/desktop/src/app/shell/titlebar-controls.tsx`):
`id` `label` `active` `className` `disabled` `hidden` `href` `icon` `onSelect` `actionId` `title` `to`。

两个契约的对称设计值得记:**`toggleLabel` 是"可被用户隐藏"的开关**——没有 `toggleLabel` 的项永远显示且不出现在右键菜单里(插件贡献的安全默认);`lockedVisible` 则是"列在菜单里但不可关"(命令中心图标、版本更新提示——把它藏了用户就再也找不到取消隐藏的入口)。

### 2.8 标题栏几何常量(13 个导出,全表)

`apps/desktop/src/app/shell/titlebar.ts:3 @ 863e313`

```ts
export const TITLEBAR_HEIGHT = 34
export const MACOS_TRAFFIC_LIGHTS_HEIGHT = 14
export const TITLEBAR_ICON_SIZE = 12
export const TITLEBAR_CONTROL_OFFSET_X = 74
export const TITLEBAR_CONTROL_HEIGHT = 22
export const TITLEBAR_CONTROLS_TOP = (TITLEBAR_HEIGHT - TITLEBAR_CONTROL_HEIGHT) / 2
export const TITLEBAR_FALLBACK_WINDOW_BUTTON_X = 24
// Edge inset used when no left-side native controls take up that space —
// Windows/Linux (native overlay is on the right) and macOS fullscreen
// (traffic lights are hidden). Matches the right-cluster's 0.75rem padding.
export const TITLEBAR_EDGE_INSET = 14
```

余下 5 个是 className 串与 `titlebarControlsPosition()`。

### 2.9 插件 SDK 暴露的 UI 子集(29 / 60)

```verify
cd /home/user/hermes-agent
grep -o "components/ui/[a-z-]*'" apps/desktop/src/sdk/index.ts | sort -u | wc -l
# → 29
```

`badge button checkbox codicon confirm-dialog context-menu copy-button decode-text dialog dropdown-menu empty-state error-state fade-scroll glyph-spinner input kbd loader log-view popover scroll-area search-field segmented-control select separator skeleton switch tabs textarea tooltip`

即 **60 个原语里 29 个是插件公开面**;`pane-tab` / `sidebar` / `command` / `pagination` / `sheet` / `zoomable` 等 31 个是应用内部原语。pane-shell 只向 SDK 导出一个类型(`FloatingAnchor`)。

---

## 3. 端到端链(判据 3):状态栏"上下文占用"→ Python 内核

用户动作:**点状态栏右侧的 "ctx 42%" 项** → 弹出上下文分解面板。

**① 组件层 —— 项是怎么被组装出来的**

`apps/desktop/src/app/shell/hooks/use-statusbar-items.tsx:527 @ 863e313`

```tsx
      {
        detail: contextBar || undefined,
        hidden: !contextUsage,
        id: 'context-usage',
        label: contextUsage,
        menuAlign: 'end',
        menuClassName: 'w-auto border-(--ui-stroke-secondary) p-0',
        menuContent: (
          <ContextUsagePanel
            currentUsage={currentUsage}
            onUsageSnapshot={publishContextUsage}
            requestGateway={requestGateway}
            sessionId={activeSessionId}
          />
        ),
        toggleLabel: copy.toggleContextUsage,
        variant: 'menu'
      },
```

**② 渲染层 —— `variant: 'menu'` 走 DropdownMenu 分支**
`apps/desktop/src/app/shell/statusbar-controls.tsx:225` 起:`item.variant === 'menu' && (item.menuContent || …)` → `DropdownMenuTrigger asChild` 包一个 `<button>`,内容进 `DropdownMenuContent side="top"`。**菜单内容只在打开时才挂载**(Radix Presence),所以下面那次 RPC 是"点开才发"。

**③ 状态层 —— `requestGateway` 从哪来**

`apps/desktop/src/app/contrib/surfaces.tsx:85 @ 863e313`

```tsx
  const { leftStatusbarItems, statusbarItems } = useStatusbarItems({
    agentsOpen,
    chatOpen,
    commandCenterOpen,
    extraLeftItems,
    extraRightItems,
    freshDraftReady,
    gatewayState,
    inferenceStatus,
    openAgents: actions.openAgents,
    openCommandCenterSection: actions.openCommandCenterSection,
    requestGateway: actions.requestGateway,
    statusSnapshot,
    toggleCommandCenter: actions.toggleCommandCenter
```

`actions.requestGateway` 来自 `apps/desktop/src/app/gateway/hooks/use-gateway-request.ts:10` 的 `useGatewayRequest()`——它持一个 `gatewayRef`(始终指向**当前激活 profile** 的 socket),身份稳定、断线自动重连后重发。

**④ 协议层 —— 面板挂载时发一次 JSON-RPC**

`apps/desktop/src/app/shell/context-usage-panel.tsx:36 @ 863e313`

```ts
    let cancelled = false
    setLoading(true)

    void requestGateway<ContextBreakdown>('session.context_breakdown', { session_id: sessionId })
      .then(data => {
        if (!cancelled) {
          setBreakdown(data)
          onUsageSnapshotRef.current?.({
            context_max: data.context_max,
            context_percent: data.context_percent,
            context_used: data.context_used
          })
        }
```

**⑤ 内核层 —— Python 侧的方法注册**

`tui_gateway/methods_session.py:1296 @ 863e313`

```python
@method("session.context_breakdown")
def _(rid, params: dict) -> dict:
    session, err = _sess_nowait(params, rid)
    if err:
        return err
    agent = session.get("agent")
```

`tui_gateway/methods_session.py:1315 @ 863e313`

```python
    with session["history_lock"]:
        history = list(session.get("history", []))
    try:
        from agent.context_breakdown import compute_session_context_breakdown

        payload = compute_session_context_breakdown(agent, history)
    except Exception as exc:
        return _err(rid, 5000, f"Could not compute context breakdown: {exc}")
```

真正算账的是 `agent/context_breakdown.py:89` 的 `compute_session_context_breakdown`,它调 `build_system_prompt_parts(agent)` 把系统提示拆成 stable/context/volatile 三段再逐类估 token。

**⑥ 回流** —— 面板把 `context_max/percent/used` 通过 `onUsageSnapshot` 写回 `setCurrentUsage`,于是**状态栏那一行的百分比标签本身也被这次弹层刷新了**。这是链条闭环的地方:一个"只读弹层"顺手校正了它的触发器。

链条中的关键设计:**状态栏项是数据(`StatusbarItem` 对象),不是组件**。`StatusbarItemView` 被 `memo` 包住,注释里给了实测数字——五标签流式跑一轮 2,174 次渲染里 1,446 次是浪费的(`apps/desktop/src/app/shell/statusbar-controls.tsx:195-200`)。

---

## 4. 逐机制 / 逐区域

### 4.1 布局树:一棵树替掉了"rails/bands 语法"

`model.ts` 的文件头把设计说得很清楚:老的语法要给"右栏顶部横跨一行"这种事写特例,树里它就是"一个列 split";span 从树的位置里自然掉出来。所有操作**纯函数、返回新树**,`normalize` 保证规范形式:

1. 空 group 被**剪掉**(拖走最后一个 pane 就关闭这个 zone,兄弟吸收空间 —— VS Code 语义);
2. 单孩子 split 解包;
3. 同向嵌套 split 摊平,权重按内部比例缩放进父槽位。

`normalize` 里有一段值得抄的注释:`headerHidden` **故意不动**。原来的实现会在 zone 只剩一个 pane 时丢掉这个标志,结果用户"藏起标题条"的选择在下次有 pane 加回来时就复活了。同理 `false` 也是黏的——一个 zone 一旦长过标签条,它就永远保留。

**无操作守卫**很有意思:`movePane` 用 `shapeSignature`(只含 pane 栈 + split 方向的字符串)比较前后两棵树,"看起来一样"就返回原树。否则"把已经独占下半区的 pane 再往下半区拖一次"会重建一个新 id 的同形结构,视觉无变化但 zone id 全变了(所有 keyed 状态被重置)。

### 4.2 拖放:一个通用会话 + 每种拖拽一个 resolver

`apps/desktop/src/components/pane-shell/tree/renderer/drag-session.ts:42 @ 863e313`

```ts
const DRAG_THRESHOLD_PX = 4

/** Normalized radius of the elliptical CENTER region (stack/link). Outside it
 *  the drop targets the dominant-axis edge — the boundary curves with the
 *  zone's aspect ratio instead of snapping at a rigid pixel band, and corners
 *  ease into their nearest edge along the quadrant diagonals. */
const CENTER_RADIUS = 0.62
```

`DragSessionSpec` 是这一层的全部接口(6 个成员):`onEngage` / `resolveMove` / `onCommit` / `onEnd?` / `onTap?` / `double?` / `ghost?`。机制归会话,语义归 resolver。目前两个 resolver:pane/tab 拖拽(本片)与侧栏会话拖拽(`app/chat/session-drag.ts`,片外)。

**性能契约写死在文件头**:布局在拖拽期间**不重构**,所以 zone 与 tab strip 的矩形在 drag start 各快照一次,之后每次 pointermove 是纯数学;移动合并到每帧一次;松手时**同步 flush** 待处理的 move,保证落点是最终指针位置而不是最后一帧。

`startPaneDrag` 有两种模式:`reorder`(在自己的 strip 内,显示插入分隔线)和 `zone`(整个树亮起)。离开 strip 超过 `TEAR_OFF_SLACK_PX = 18` 就从 reorder 转成 zone —— 浏览器标签"撕下来"的手感。**全程 placement-on-release**:没有任何实时重排,被拖的标签只是变半透明(`opacity 0.45`)。

### 4.3 FancyZones 的两次移植

两个文件都在头注释里点名了上游、文件名与许可:

`apps/desktop/src/components/pane-shell/tree/grid-model.ts:1 @ 863e313`

```
/**
 * FancyZones grid model — a faithful port of PowerToys'
 * `FancyZonesEditor/Models/GridLayoutModel.cs` + `FancyZonesEditor/GridData.cs`
 * (microsoft/PowerToys, MIT). Function/field names, algorithms, and invariants
 * follow the C# sources so behavior matches the original editor:
 *
 *  - A layout is rows x columns with percent tracks summing to MULTIPLIER
 *    (10000) and a cellChildMap assigning each cell to a zone; a zone spanning
 *    multiple cells appears as the same index in adjacent cells.
 *  - Zones are rectangles in the 0..10000 coordinate space (prefix sums).
 *  - Resizers are the shared edges between zones, derived from cellChildMap
 *    discontinuities; dragging one moves every zone touching that edge.
 *  - Merging computes the rectangular CLOSURE of the selection (extending it
 *    until no zone is partially cut) — the signature FancyZones merge feel.
 */
```

`apps/desktop/src/components/pane-shell/tree/zones-engine.ts:22 @ 863e313`

```ts
export const FADE_IN_DURATION_MILLIS = 200
export const FLASH_ZONES_DURATION_MILLIS = 700
/** LayoutDefaultSettings::DefaultSensitivityRadius. */
export const DEFAULT_SENSITIVITY_RADIUS = 20
/** ZoneSelectionAlgorithms::OVERLAPPING_CENTERS_SENSITIVITY. */
const OVERLAPPING_CENTERS_SENSITIVITY = 75
```

**移植到什么程度**:连 `zonesFromPoint` 里"只捕获到一个 zone 但没有严格捕获就当没捕获"这条 C++ 里的怪规则、`HighlightedZones` 的初始 zone 闩锁状态机、四种重叠消解算法(Smallest / Largest / Positional / ClosestCenter),都是逐行搬过来的。**唯一有意的偏离**在覆盖层动画:

> 覆盖层入场淡入。FancyZones 出厂是 200ms(zones-engine 里的 `FADE_IN_DURATION_MILLIS`);
> 在光标底下起手的拖拽里那条斜坡读起来像卡顿,所以这里的 sheet 快得多 —— 同样的柔化,即时的手感。

(`OVERLAY_FADE_MS = 80`,`apps/desktop/src/components/pane-shell/tree/renderer/tree-group.tsx:737`)

**网格 → 树的桥是有损的**:`grid-to-tree.ts` 只能表达 guillotine(整刀切)布局;互锁的"风车"排列返回 null,编辑器就把 Save 禁掉并给出解释(`treeExpressible` → `t.zones.notExpressible`)。这是一个诚实的能力边界:**FancyZones 的模型比这棵树能表达的更宽**。

### 4.4 轨道模型:什么时候是"固定侧栏",什么时候是"分剩余空间"

`track-model.ts` 的核心是一句:节点沿某轴**解析得出 CSS 长度就是固定轨道,解析不出就是弹性轨道**。规则:

- **zone**:它**显示中的**那些 pane 声明的 `width`/`height` 的 `max()`(不是激活标签的!)。这样切标签、拖入一个 pane 都不会让 zone 尺寸跳变。sash 拖出来的 px 覆盖只**细化**已声明尺寸的 pane;给一个本来弹性的 pane 硬塞覆盖会把 main 变成固定轨道并把整片剩余空间交给吸收者。
- **沿轴的 split**:所有可见子项之和 —— **只要有一个弹性子项,整条就是弹性的**。
- **跨轴的 split**:可见固定子项的 max()。

一个专门的边界情形:**全固定的一排填不满容器**(终端 + 日志各 38vh 而上面的栏收起来了)。`allFixedAbsorberIndex` 让**最后一个没有上限的**固定轨道吸收剩余;有 `maxWidth` 的侧栏(review/files)绝不当吸收者——注释说,把它们提成 grow-1 会让 ⌘G/⌘J 打开半个窗口宽的栏。

### 4.5 keep-alive 与"隐藏但仍有布局盒"的代价

`apps/desktop/src/components/pane-shell/pane-visibility.ts:15 @ 863e313`

```ts
/** Marks a mounted-but-hidden pane layer (an inactive tab in a stack). */
export const PANE_HIDDEN_ATTR = 'data-pane-hidden'

const HIDDEN_PANE = `[${PANE_HIDDEN_ATTR}]`

/** Spread onto a kept pane layer so the lookups below can skip it. */
export const hiddenPaneProps = (hidden: boolean): Record<string, string> => (hidden ? { [PANE_HIDDEN_ATTR]: '' } : {})
```

用 `visibility: hidden` 而不是 `display: none`,是为了保住布局盒 → 滚动位置在切标签往返后还在。**代价**:隐藏层的 `getBoundingClientRect()` 与可见层**一模一样**,所以任何"从文档里找 composer / 找 viewport"的查询都会拿错标签的元素。这就是 `queryVisible` / `queryAllVisible` 存在的全部理由 —— 一条策略,一处强制。

配套两个 context:`PaneVisibleContext`(默认 `true`,让 keep-alive 的聊天面在自己不可见时关掉流式高频订阅)与 `PaneGroupContext`(zone 身份,给"按 zone 而非按窗口/按标签"的状态用,如 composer pop-out)。

### 4.6 "关闭"有五种语义

这是 store 里最容易被低估的复杂度。同一个 ✕,落在不同 pane 上做的事完全不同:

| pane 类 | 关闭走哪 | 结果 |
|---|---|---|
| 注册了 closer 的核心 pane(review/terminal/preview/sessions) | `closeTreePane` → `paneClosers[id]()` | 走它自己的可见性 store,标题栏/状态栏开关保持诚实 |
| 工具面板(terminal/logs) | `closeToolPane` = `dismissTreePane` **然后** closer | 先移出树再通知 store,否则 store 的监听器会去折叠一个共享 zone 里幸存的兄弟 |
| 插件 pane | `closeTreePane` 检出 `source.startsWith('plugin:')` | **禁用插件**(等价于 Settings→Plugins 的开关)+ 通知;pane id 留在树里,重新启用就回到原位 |
| 其它(未绑定的核心 pane) | `dismissTreePane` | 移出树 + 记进 `$dismissedPanes`,采纳不会再把它加回来 |
| `uncloseable`(主 workspace) | 不提供 Close | 但它的**标签**仍可被"关闭手势"清空成新草稿(靠 `$panesWithCloser` 而非 `uncloseable` 判定) |

再叠一层:`togglePaneVisible` 统一了所有开关(⌃`、⌘G、状态栏按钮、⌘K 行)。它的注释讲了一条通用教训——**开关不要问自己的布尔,要问屏幕**:

> A free-floating `!$open.get()` diverges from the tree the moment anything
> else moves the pane — stacked behind a sibling tab, minimized from the zone
> menu, closed with ⌘W — and then the toggle spends its press re-asserting a
> value the store already held, which reads as a dead key.

### 4.7 键盘目标解析:一条"资格阶梯"

`tabTargetGroup(eligible)` 依次试:**悬停的 zone → 聚焦的 zone → workspace 所在 zone**,每一级都要通过调用方给的 `eligible` 谓词才算数。四个键族共用它,所以 ⌘1…⌘9、⌃Tab、⌘W、⌘T **永远不会对"哪个 zone 是那个 zone"产生分歧**。

各自的谓词不同,这正是它们的语义差别:

| 键 | eligible | 为什么 |
|---|---|---|
| ⌘1…⌘9 | `shownPanesInGroup(g).length >= 2` | 只有真的是标签条才编号 |
| ⌃Tab | 同上 **且** 有 `isMainStripPane` | 只在 main 类 tile 之间循环 |
| ⌘W(会话/页面) | `g.panes.some(isMainStripPane)` | 曾经用会话前缀判定,导致 ⌘W 在 Browser/page zone 上是死键 |
| ⌘W(工具面板) | `g.panes.some(isCollapsePane)` | 终端和日志的标签曾经是全应用唯一关不掉的 |
| ⌘T / "+" | `g.panes.some(isSessionStripPane)` | 只有聊天条能停靠会话;停在文件树上不能把会话塞进去 |

而 `shownPanesInGroup` 存在的理由是**编号必须索引"画出来的"标签**:chrome 隐藏的、未注册的、窄屏折叠的 pane 仍在 `group.panes` 里但不是 chip;直接走原数组会产生经典的"⌘W 之后偏一位"。

### 4.8 sash:拖拽期间不写 store

`tree-split.tsx` 里有本片最详细的一段性能注释(268-287 行)。要点:

- `setTreeSplitWeights` / `setPaneWidthOverride` 每次都造新对象,提交会走遍所有挂载的 pane。实测:58 帧的拖拽里 31 次提交、20.7fps,`TreeNode` 490ms、markdown 重解析 620ms。
- 所以**拖拽期间只改内联样式**(改 React 自己写的那两个 wrapper),松手时**一次**写 store。
- 预览规则分三种形状:固定侧只改 `flex-basis`(grow/shrink 留给 React,弹性伙伴不动,不会开缝);弹性对弹性两边都钉成 `0 1 <px>`;清理时,真拖拽靠 React 重渲染改写 `flex` 简写(简写会重置长写),零位移点击则恢复捕获的 `style` 属性原文。
- 另有 `beginSashDrag()/endSashDrag()`(`geometry.ts`)在拖拽期间抑制 `:root` 自定义属性写入 —— 实测 14fps → 51fps。

### 4.9 `components/ui` 是 shadcn/ui 的本地副本

证据链(不是推断):

1. `apps/desktop/components.json` 存在,`$schema` 指向 `https://ui.shadcn.com/schema.json`,`"style": "new-york"`,`"rsc": false`,`aliases.ui = "@/components/ui"` —— 这就是 shadcn CLI 的项目配置文件。
2. 60 个文件里 **24 个**带 `data-slot="…"`(共 144 处)—— shadcn 2025 版模板的标志性写法。
3. 依赖是统一包 `radix-ui: 1.6.7` + `cmdk: 1.1.1` + `class-variance-authority: 0.7.1`(`apps/desktop/package.json`),与 shadcn 新版模板一致。
4. `sidebar.tsx` 与 `zoomable.tsx` 顶部有 `'use client'` —— Next.js RSC 指令,而 `components.json` 明写 `"rsc": false`,项目是 Vite + Electron renderer。这是**从上游整文件复制**留下的指纹(全 `apps/desktop/src` 共 29 个文件带这条指令)。

**本地改动是真的存在的**,不是原样照抄。举证三处:
- `dropdown-menu.tsx` 加了上游没有的 `DropdownMenuSearch` + `dropdownMenuRow` / `dropdownMenuSectionLabel` 两个共享 class token;
- `tooltip.tsx` 把 Radix 的 `skipDelayDuration` 归零、`disableHoverableContent` 默认打开,并加了 `suppressNonKeyboardFocusOpen`(用 `lastInputModality()` 而不是 `:focus-visible` 判断"是不是键盘焦点");
- `sidebar.tsx` 把上游的 Cmd/Ctrl+B 快捷键 effect **删掉**,换成一条注释指向本项目的 keybind 运行时。

---

## 5. 文档与代码的出入

### ▲-1 `desktop-plugin-sdk.md` 把 `placement` 的合法值列成 5 个,实际是 6 个

文档(`website/docs/developer-guide/desktop-plugin-sdk.md:227`):

> `placement` is `'main' | 'left' | 'right' | 'top' | 'bottom'`. To land on a
> specific **edge** instead of stacking, add a `dock` gesture — the same thing as
> dragging onto a pane's drop chip:

整句判定:这是一个**穷举式枚举**("is A | B | C | D | E"),不是举例;它归在 `### Panes` 小节下,该小节讲的正是插件怎么注册 pane。代码里存在第六个合法值 `'floating'`,且它是**语义上最不同的一个**(整个退出布局树):

`apps/desktop/src/components/pane-shell/tree/renderer/floating-rect.ts:33 @ 863e313`

```ts
/** The one non-tiling placement — see renderer/floating-panes.tsx. */
export const FLOATING_PLACEMENT = 'floating'
```

它被两个测试文件当行为规格钉住(`apps/desktop/src/components/pane-shell/tree/floating-adoption.test.ts`、`apps/desktop/src/components/pane-shell/tree/renderer/floating-panes.test.tsx`),渲染路径见 §2.5 的两段引用。

**同一件事的 SDK 侧是对的**:`apps/desktop/src/sdk/index.ts:140-145` 的注释专门讲了 `'floating'` 是"唯一的非平铺值",要配 `anchor` + `width`/`height`。所以这不是"功能没写文档",是**同一份 API 的两处文档互相矛盾,网站那一处是错的**。

> 附带的 ◇:同一小节的 pane `data` 载荷写成 `{ placement, dock?, width?, height? }`(第 201 行的表格),
> 而代码里的 `PaneChrome` 有 16 键、另有 `dock` 与 `revealOnPreset` 两键在 store 侧读取(见 §2.5)。
> `minWidth/maxWidth/minHeight/maxHeight` `collapsible` `revealAliases` `anchor` `uncloseable`
> `tabWrap` `tabDrag` `headerVeto` `tabLead` `stripTools` `revealOnPreset` 共 **14 键无文档**。

### ▲-2 `DESIGN.md` 说 `SearchField` 是"唯一的搜索输入框",同目录里还有两个

文档(`apps/desktop/DESIGN.md:157`,在 `## Form controls` 标题下):

> - **`SearchField`** — borderless, underline-on-focus, auto-width. The only
>   search input. Don't build boxed search bars; don't wrap it in a bordered tile.
>   Empty lists hide their search field.

整条判定:三句话——"唯一的搜索输入框" / "别造带框的搜索栏" / "空列表隐藏搜索框"。前两句都被同目录的代码证伪:

```verify
cd /home/user/hermes-agent
grep -n "function SearchField\|function DropdownMenuSearch\|function CommandInput" \
  apps/desktop/src/components/ui/search-field.tsx \
  apps/desktop/src/components/ui/dropdown-menu.tsx \
  apps/desktop/src/components/ui/command.tsx
# 三个文件各命中一个:同一个 components/ui 目录里有三个搜索输入框
grep -rln "CommandInput" apps/desktop/src --include=*.tsx | grep -v ui/command.tsx | wc -l
# → 12(会话选择器、语言切换、模型选择器、⌘K 命令面板、worktree/分支选择器、设置里的可搜索下拉…)
```

- `DropdownMenuSearch`(`apps/desktop/src/components/ui/dropdown-menu.tsx:35`)是第二个,本片的模型目录菜单就在用它;
- `CommandInput`(`apps/desktop/src/components/ui/command.tsx:26`)是第三个,而且它**恰恰是一条"带框的搜索栏"**:外层 `div` 是 `flex h-11 items-center gap-2 border-b border-border px-3`。

宽容读法是"唯一的**页面/面板级**搜索输入框",但文档没这么写,而 `DESIGN.md` 开头(第 17-20 行)自己规定:命名契约"与代码一同维护,这个文件里一个过时的名字就是 bug,和过时的类型一样"。按它自己的标准,这条要改。

### ◇-1 FancyZones 移植有署名注释,但仓库没有第三方许可清单

`grid-model.ts` / `zones-engine.ts` / `zone-editor.tsx` 三个文件头都写了 `(microsoft/PowerToys, MIT)`,这比 R10 在 `hermes-ink` 上查到的"fork 后零许可声明"好得多。但:

```verify
cd /home/user/hermes-agent
git ls-files | grep -iE "licen[cs]e|notice|third.?party" | grep -v -E "^(plugins|skills|optional-skills|tests|scripts|agent|apps/desktop/src)/"
# → 只有一行:LICENSE(MIT, Copyright (c) 2025 Nous Research)
grep -rn -i "powertoys" --include=LICENSE --include=NOTICE --include="*.md" . 2>/dev/null | grep -v node_modules | grep -v "apps/desktop/src" | wc -l
# → 0
```

**搜索面**:`git ls-files` 全仓文件名匹配 `licen[cs]e|notice|third.?party|attribution|credits`(不区分大小写),排除 `plugins/`、`skills/`、`optional-skills/`(它们各自带自己的 LICENSE)与测试/脚本;再对全仓 `*.md` + `LICENSE` 搜 `powertoys`(不区分大小写),排除 `node_modules` 与 `apps/desktop/src`(源码内注释已计入)。结论:**仓库根 LICENSE 是 MIT / Nous Research 2025,没有任何文件列出 PowerToys 的版权行或 MIT 全文**。

同理 shadcn/ui:`components.json` 证明用了 shadcn 的分发方式,60 个原语里没有一个带上游署名(`grep -rn -i "shadcn|copyright|license" apps/desktop/src/components/ui/` **零命中**)。shadcn 的定位是"复制进你的项目",与 fork 一份库不同,但**文档侧对此完全沉默**:`apps/desktop/DESIGN.md` 与 `apps/desktop/AGENTS.md` 通篇没有 "shadcn" 字样;唯一承认这件事的是**另一个应用**的 README(`web/README.md:9`,说的是 web dashboard 而非桌面端,而且措辞是 "hand-rolled, no CLI dependency" —— 桌面端恰恰有 CLI 配置文件)。

这是一条 ◇(代码有、文档无),不是法律结论。

### ◇-2 `window.__HERMES_LAYOUT_TREE__` 自动化钩子

`apps/desktop/src/components/pane-shell/tree/store.ts:1660-1670` 在 `import.meta.env.DEV || VITE_PERF_PROBE === '1'` 时往 window 上挂 7 个入口(`close` `dismissed` `get` `move` `registry` `reset` `reveal`)。E2E 与性能探针靠它驱动布局。任何文档都没提。

### ◎-1 `DESIGN.md` 关于 `Button` 的"命名契约"完全准确

反向验证(这条是**正结论**,值得记):DESIGN.md:110-119 列的 8 个 variant(`default destructive secondary outline ghost link text textStrong`)与 11 个 size(`default xs sm lg inline micro icon icon-xs icon-sm icon-lg icon-titlebar`)和 `apps/desktop/src/components/ui/button.tsx:17-54` 的 cva 定义**逐字一致,无多无少**。同样准确的还有:`controlVariants` 确由 Input / Textarea / SelectTrigger 三者消费;`no-native-title.test.ts` 这个被文档点名的测试文件**确实存在**(`apps/desktop/src/components/ui/__tests__/no-native-title.test.ts`);`Loader` 的 `lemniscate-bloom` 确在 `LOADER_TYPES` 的 22 个值里。

记 ◎ 而不是"无事":`Loader` 的文档只说"animated math/ascii curves",实际是 **22 条具名曲线**的可选集(`LOADER_TYPES`),文档字面为真但显著保守。

---

## 6. 缺陷

### ■-1 双击 sash"恢复默认尺寸"后,弹性权重不落盘

**现象**:双击两个 zone 之间的接缝,尺寸在屏幕上复位了;此时重载窗口(⌘R / 重启),**弹性 zone 的比例回到复位前**。固定侧栏那一半会正确复位(它走另一条持久化)。

**机制**。写权重的函数只改内存原子:

`apps/desktop/src/components/pane-shell/tree/store.ts:1579 @ 863e313`

```ts
export function setTreeSplitWeights(splitId: string, weights: number[]) {
  const tree = $layoutTree.get()

  if (tree) {
    // Weight drags are high-frequency: update live, persist on the trailing edge.
    $layoutTree.set(setSplitWeightsOp(tree, splitId, weights))
  }
}
```

注释里的 "persist on the trailing edge" 指的是拖拽路径:`startSash` 的 `cleanup()` 在 `pointerup` 时调 `persistTree()`(`apps/desktop/src/components/pane-shell/tree/renderer/tree-split.tsx:382`)。但双击复位走的是另一条路,它的最后一行就是 `setTreeSplitWeights`,之后什么都没有:

`apps/desktop/src/components/pane-shell/tree/renderer/tree-split.tsx:460 @ 863e313`

```tsx
          weights[i] = (px * others) / (totalPx - px)
          pinned = true
        }
      }

      setTreeSplitWeights(node.id, !preset && !pinned ? weights.map(() => 1) : weights)
    },
```

**事件顺序让它更糟**:DOM 规定 `pointerup` → `click` → `dblclick`。所以第二次点击的 `cleanup()` 先跑,`persistTree()` 把**复位前**的权重写进 localStorage,`dblclick` 才触发 `resetBoundary` 把新权重只写进内存。

**验证(可重跑)**:

```verify
cd /home/user/hermes-agent
# (a) resetBoundary 函数体(tree-split.tsx:401-469)内 persist 出现次数
sed -n '401,469p' apps/desktop/src/components/pane-shell/tree/renderer/tree-split.tsx | grep -c persist
# → 0
# (b) 全 apps/desktop 只有两个 persistTree() 调用点,都不在这条路径上
grep -rn "persistTree()" apps/desktop/src --include=*.ts --include=*.tsx
# → tree-split.tsx:382(sash 拖拽 cleanup)/ store.ts:1630(定义)/ store/profile-share.ts:131
# (c) resetBoundary 的唯一调用点是 onDoubleClick
grep -rn "resetBoundary" apps/desktop/src --include=*.tsx
# → tree-split.tsx:401(定义)、tree-split.tsx:595(onDoubleClick)
```

**搜索面**(负结论部分):在 `apps/desktop/src` 全树、扩展名 `.ts`/`.tsx`、模式 `persistTree()` 与 `resetBoundary`,无排除。第三个调用点 `store/profile-share.ts:131` 属于 profile 分享导入流程,与 sash 无关。

**影响范围有界**:损失窗口是"到下一次任何提交树的操作为止"——之后的任意 sash 拖拽 / 移动 pane / 切标签都会把已复位的权重顺带写进去。所以症状是"偶尔复位不生效",这类最难被用户报告。
**修法一行**:`resetBoundary` 末尾加 `persistTree()`。

### ■-2 `sidebar.tsx` 每次开合都写一个从没人读的 cookie

`apps/desktop/src/components/ui/sidebar.tsx:78 @ 863e313`

```tsx
  )

  React.useEffect(() => {
    document.cookie = `${SIDEBAR_COOKIE_NAME}=${open}; path=/; max-age=${SIDEBAR_COOKIE_MAX_AGE}`
  }, [open])
```

上游 shadcn 用这条 cookie 做 Next.js 服务端渲染时的初值,本项目没有服务端。

```verify
cd /home/user/hermes-agent
grep -rn "sidebar_state" . 2>/dev/null | grep -v node_modules
# → 只有一行:apps/desktop/src/components/ui/sidebar.tsx:18 的常量定义本身
```

**搜索面**:仓库全树(`grep -rn`),字面量 `sidebar_state`,只排除 `node_modules`。**零读取点**——写进去的值没有任何代码取出来过。真正的持久化是 `$sidebarOpen`(`apps/desktop/src/store/layout.ts`),`SidebarProvider` 被受控使用(`apps/desktop/src/app/contrib/controller.tsx:692-696` 传 `open`/`onOpenChange`)。

**为什么算缺陷而不是"无害的死代码"**:(a) 它是每次侧栏开合都会跑的一次副作用;(b) 它在 Electron renderer 的 origin 上种了一个 7 天有效期的 cookie,这个 origin 还托管远程网关的内容;(c) 它是"vendored 副本没有随宿主环境裁剪"的活样本 —— 和 `'use client'` 同源。**严重度低**,但它是本片里唯一一处"上游代码在这个宿主里语义为零却仍在执行"的地方。

### ■-3(轻)`FloatingPane` 在 state updater 里做持久化副作用

`apps/desktop/src/components/pane-shell/tree/renderer/floating-panes.tsx:133-137`:`onPointerUp` 里写
`setRect(current => { persist(current, collapsed); return current })` —— 用 updater 当"读当前值"的手段,但 updater 必须是纯函数。React StrictMode 会双调用 updater,于是每次松手写两遍 localStorage。不改变结果,只是多一次写。同一个文件的 `toggleCollapsed` 也是这个形状。归为轻微,列出来是因为它是这一片里**唯一**违反"直接操纵先画、持久化后对账"那条 DESIGN.md 原则的实现细节(它是"持久化混进渲染路径")。

---

## 7. 测试(行为规格)

范围:片内三个目录下的**全部** 40 个测试文件(它们本身属 LT 层,不计入本片 100 文件)。

```verify
cd /home/user/r10b-ts/hermes-agent/apps/desktop
npx vitest run --project ui src/components/pane-shell src/components/ui src/app/shell
```

```console
 Test Files  40 passed (40)
      Tests  202 passed (202)
   Duration  87.54s
```

**passed 202 / failed 0 / skipped 0**(JSON reporter 复核:`numPassedTests=202  numFailedTests=0  numPendingTests=0  numTodoTests=0`,`numTotalTestSuites=98`)。

**零执行点名:无。** 40 个文件全部至少执行了 1 个用例(JSON reporter 里 `assertionResults` 为空的文件数 = 0)。跳过标记也没有:

```verify
cd /home/user/hermes-agent
grep -rn "\.skip\|\.todo\|\.only\|skipIf\|runIf" \
  $(git ls-files | grep -E "^apps/desktop/src/(components/(pane-shell|ui)|app/shell)/.*\.test\.(ts|tsx)$")
# → 无输出(退出码 1)
```

用例数最多的六个文件:`model-menu-panel.test.tsx` 19、`multi-tab-drag.test.ts` 12、`floating-rect.test.ts` 11、`fade-scroll.test.ts` 8、`tool-pane-toggle.test.ts` 8、`floating-panes.test.tsx` 8。

**几条把设计钉死的规格**(这些是读代码时的"作者承诺"):
- `floating-adoption.test.ts` —— `placement:'floating'` 的 pane **永远不得进入布局树**,即使采纳被反复触发;
- `focus-tab-hijack.test.ts` / `hovered-zone-tabs.test.ts` —— §4.7 那条资格阶梯的行为;
- `track-model-absorber.test.ts` —— 全固定一排里"有 max 的不当吸收者";
- `tool-panel-close.test.tsx` —— 工具面板 Close 必须**先 dismiss 再通知 store**;
- `lone-header.test.ts` / `tab-strip-scroll.test.ts` / `floating-rect.test.ts` —— 三个纯函数模块被单独测,这是它们被从渲染器里抽出来的直接原因。

环境说明:`/home/user/r10b-ts/hermes-agent` 是主线用 `git archive` 导出的基线副本,**基线本身未被触碰**(本片全程未在 `/home/user/hermes-agent` 内执行任何写操作;完成时 `git status --porcelain` 仍为空)。未安装任何包。

---

## 8. 判据自查

| # | 判据 | 自评 | 说明 |
|---|---|---|---|
| 1 | 点名到位 | **达成** | §0.1/0.2/0.3 逐个列出 100 个全路径 + 一句话角色;`components/ui` 归成 4 组但**组内逐个列全路径** |
| 2 | 接缝穷举 | **大部分达成,一处部分达成** | 全列:布局树 9 字段 + 校验规则、8 个持久化键、`tree/store.ts` 79 导出、`PaneChrome` 16+2 键、10 个 data-* 契约、`StatusbarItem` 20 键 / `StatusbarMenuItem` 9 键 / `TitlebarTool` 11 键、`titlebar.ts` 13 常量、SDK 暴露的 29/60、`components/ui` 215 导出名与 179 个 props 注解(全表在 §2.3)。**部分达成的一处**:116 个 `passthrough` 组件我给的是注解本身,没有展开 Radix 原语的 props 全集(那在 `radix-ui@1.6.7` 包里,越过基线边界)。按"仓库内可枚举"口径 100%,按"逐字段列全"口径约 65%(63/179) |
| 3 | 端到端链 | **达成** | §3:点状态栏 → `use-statusbar-items` 组项 → `statusbar-controls` 的 menu 分支 → `surfaces.tsx` 注入 `requestGateway` → `context-usage-panel` 发 `session.context_breakdown` → `tui_gateway/methods_session.py:1296` → `agent/context_breakdown.py:89`,逐跳带锚点 |
| 4 | 逐字取证 | **达成** | 14 个逐字源码围栏块(model.ts×3、store.ts×3、track-model、floating-rect、drag-session、zones-engine、grid-model、pane-visibility、titlebar、tree-split、sidebar、use-statusbar-items、surfaces、context-usage-panel、methods_session×2) |
| 5 | 记号 | **达成** | ▲×2、◇×2、◎×1、■×3,每条带锚点;两条全称否定(◇-1、■-2)都写了搜索面 |

**未做到 / 主动缩范围的地方**(如实记):
- `components/ui` 我读的是**接口面 + 顶部设计注释**,只对 `button` / `sidebar` / `tooltip` / `pane-tab` / `dialog-portal-context` / `keyboard-first` / `actions-menu` / `loader` / `command` / `dropdown-menu` / `search-field` / `switch` 这 12 个读了实现体;其余 48 个是签名 + 文档注释级。这符合 L2 定义,但要说清楚。
- `loader.tsx` 的 22 条曲线数学、`decode-text` 的动画时序、`status-pulse` 的 rAF 循环,只记了"是什么",没验算。
- `zone-editor.tsx` 的交互我读全了,但**没有对着 PowerToys 的 `GridEditor.xaml.cs` 原文逐条比对**移植保真度(上游不在本容器里)。作者声称"逐行移植"这一点**未经独立验证**,只验证了它自称的上游文件名与常量名是自洽的。

---

## 9. 移交项

| 编号 | 锚点 + 摘录 | 一句话现象 | 建议接手方 |
|---|---|---|---|
| H-G-a | `apps/desktop/src/components/pane-shell/tree/renderer/tree-split.tsx:465`:`setTreeSplitWeights(node.id, !preset && !pinned ? weights.map(() => 1) : weights)` | ■-1:双击 sash 复位后没有任何 persist,重载即丢;修法是这一行后面补 `persistTree()` | 需要给上游报 issue / 写进"我自己的 harness 要避开的坑" |
| H-G-b | `apps/desktop/src/components/ui/sidebar.tsx:81`:`document.cookie = ` | ■-2:vendored shadcn 组件在 Electron 里种一个全仓零读取的 cookie;`grep -rn sidebar_state` 全仓只命中常量定义 | 与"vendored 副本如何随宿主裁剪"这个主题一起讲 |
| H-G-c | `website/docs/developer-guide/desktop-plugin-sdk.md:227` 的 `placement` | ▲-1:网站文档把 pane placement 穷举成 5 个值,代码与 SDK 注释都有第 6 个 `'floating'`;同小节表格把 `data` 载荷写成 4 键,实为 16+2 键 | R12 装订"插件贡献面"一章时要用代码侧口径 |
| H-G-d | `apps/desktop/DESIGN.md:157` 的 `SearchField` | ▲-2:"唯一的搜索输入框",同目录另有 `DropdownMenuSearch` 与 `CommandInput`,后者恰是一条带边框的搜索栏 | 同上 |
| H-G-e | `apps/desktop/src/components/pane-shell/tree/grid-model.ts:2`:`* FancyZones grid model — a faithful port of PowerToys'` | ◇-1:三个文件声明逐行移植自 PowerToys(MIT),仓库无第三方许可清单;`components/ui` 是 shadcn 副本但桌面端文档零提及 | 与 R10 在 `hermes-ink` 上的同型判定合并成"外部代码引入的三种形态"一节 |
| H-G-f | `apps/desktop/src/components/pane-shell/tree/store.ts:1661`:`;(window as unknown as Record<string, unknown>).__HERMES_LAYOUT_TREE__ = {` | ◇-2:DEV / `VITE_PERF_PROBE=1` 下挂 7 个布局操作到 window,供 E2E 与性能探针驱动;无文档 | 讲"harness 怎么给自己留自动化把手"时可用 |
| H-G-g | `apps/desktop/src/components/pane-shell/tree/grid-to-tree.ts:80`:`  // No full-length cut exists on either axis: non-guillotine (pinwheel).` | 能力边界:FancyZones 网格能表达的比这棵树多,风车布局保存不了(Save 被禁用);后续若要讲"为什么选 guillotine 树"这是关键取舍点 | R12 布局章 |
| H-G-h | `apps/desktop/src/components/pane-shell/tree/model.ts:561`:`  if (n.type === 'group') {` | `isLayoutNode` 不校验 `minimized` / `headerHidden` 两个可选布尔,持久化里的脏值会原样进树(靠下游 `Boolean()` 兜住)。不是缺陷,但若要抄这套"不可信持久化"的校验思路要知道它的边界在哪 | 谁写 harness 的持久化校验 |

---

## 10. 本片成本自报

```text
片号            : G
层              : L2
文件数 / 行数   : 100 / 17,544
实际打开的文件数: 46          (完整读过内容的;另有 54 个只读了头部 20~40 行的
                              导出/props/文档注释 —— 那 54 个通过探针脚本拿到
                              了完整的导出面与 props 注解,不是"只看了路径")
实际读过的行数  : ~9,500      (估法:完整读过的 46 个文件行数合计约 8,100
                              [pane-shell 25 个 8,051 行里读全了 22 个约 7,700,
                               app/shell 15 个里读全了 13 个约 2,900,
                               components/ui 60 个里读全了 11 个约 2,400 —— 
                               去重后约 8,100],加上片外追链读的
                               surfaces.tsx / use-gateway-request.ts /
                               methods_session.py / sdk/index.ts / DESIGN.md /
                               desktop-plugin-sdk.md 约 1,400 行)
底稿字节数      : (主线自测)
主观耗费        : 中偏高。瓶颈是**两头分化**:pane-shell 一侧是"单文件极长 +
                  概念密度高"(store.ts 1,670 行、79 个导出,而且关闭/隐藏/
                  折叠三套语义互相缠绕,不通读完整个文件就说不清任何一个动作
                  的边界);components/ui 一侧是"文件多但每个都短",逐个人读
                  性价比极低——这一半是靠写一个 AST-lite 探针脚本
                  (data/r10b/probes/probe_g_ui_surface.py)一次性把 60 文件的
                  215 个导出与 179 个 props 注解全抽出来才做到"不抽样"的。
                  跨文件追链(状态栏项 → 网关 → Python)反而是最省的一段。
```
