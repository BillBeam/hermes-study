# r10b 片J · 桌面外壳其余 —— 覆盖层、小组件、宠物、cron/消息/webhook 面板与样式（底稿）

> 层:**L2**(读接口面,不读实现体,但接口面不抽样)。
> 溯源约定:凡对代码的断言,锚点写作 `路径:行号 @ 863e313`,单独成行、置于代码块之前。
> 本片全部文件在 `/home/user/hermes-agent/` 下,路径一律从仓库根写起。
> 片内文件数 / 行数:**86 / 18,766**(清单 `data/r10b/slices/J.txt`)。

**本片是切片脚本的声明式兜底桶**(`data/r10b/probes/make_slices.py` 最后一条规则):
桌面壳里没被 A–H / K 认领的部分。它不是一个"机制",而是**同一个外壳的若干条外缘**:
路由与覆盖层栈、启动/安装/更新/认证这条阻塞态链、一堆小组件、宠物(在窗内 + 弹出成独立 OS 窗口)、
四张面板页(cron / messaging / webhooks / artifacts),以及整个 renderer 的样式表。

---

## 0. 本片范围与逐文件点名(判据 1)

86 个文件按主题分 12 组(§0.1–§0.12,各组文件数 7 / 7 / 4 / 9 / 17 / 4 / 11 / 11 / 2 / 3 / 9 / 2 = 86)。
**每组内逐个列全路径 + 一句话角色。**

### 0.1 应用根与路由(7 个)

- `apps/desktop/src/app/index.tsx` — 6 行的门面:`export { ContribController as default } from './contrib'`,
  说明"应用根"这个名字下面其实什么都没有,一切由 contribution registry 驱动(片 A/B 的地盘)。
- `apps/desktop/src/app/routes.ts` — **路由的唯一真源**:11 条内建路由、`AppView` 判定、
  session-id 解析、贡献路由(`routes` area)、`OVERLAY_VIEWS` 集合、`$workspaceIsPage` 与 `syncWorkspaceRoute`。
- `apps/desktop/src/app/types.ts` — 桌面侧对 gateway RPC 响应体的 TS 形状集合
  (`SessionCompressResponse`、`CommandDispatchResponse` 联合、`ClientSessionState` 等),纯类型、无运行时。
- `apps/desktop/src/app/layout-constants.ts` — 4 个布局常量(页面横向 gutter、负 margin、最大宽、
  侧栏折叠断点),注释明确要求必须是**字面量字符串**否则 Tailwind 扫描不到。
- `apps/desktop/src/app/master-detail.tsx` — 页面级(非覆盖层)主从骨架 + 一批共享行/条控件
  (`MasterDetail`/`ListColumn`/`DetailColumn`/`DetailPane`/`ListStrip*`/`CapRow`/`ToolChip`/`ICON_BUTTON`)。
- `apps/desktop/src/app/page-search-shell.tsx` — 页面页眉外壳:左搜索 / 中 tabs / 右动作的三栏 grid,
  外加一条显式的"**不要**在这个 header 上加 `-webkit-app-region: drag`"的告诫。
- `apps/desktop/src/app/floating-hud.ts` — 命令面板与会话切换器共用的浮动 HUD class 常量
  (位置、表面、字号、行内距、分组标题、尾注两种变体),无组件、纯字符串。

### 0.2 通用 hooks(7 个,`apps/desktop/src/app/hooks/`)

- `apps/desktop/src/app/hooks/use-config-record.ts` — 整个 profile 配置记录(`GET /api/config`)的
  单一 react-query 缓存键 + 写缓存 + 失效三件套。
- `apps/desktop/src/app/hooks/use-debounced.ts` — 15 行的值防抖。
- `apps/desktop/src/app/hooks/use-keybinds.ts` — **全局唯一的 keydown 分发器**,71 个 action id 的
  handler 表 + 捕获(rebind)模式 + 会话切换器的 keyup 提交(详见 §2.3)。
- `apps/desktop/src/app/hooks/use-on-profile-switch.ts` — 活动 profile 变化时跑回调、首挂载不跑。
- `apps/desktop/src/app/hooks/use-refresh-hotkey.ts` — 裸 `r` 键刷新(带修饰键 / 可编辑焦点时忽略),
  四张面板页共用。
- `apps/desktop/src/app/hooks/use-route-enum-param.ts` — 枚举型 URL query 参数的读写(`?tab=`),
  永远 `replace` 导航,让 tab 选择在刷新后存活。
- `apps/desktop/src/app/hooks/use-route-overlay-active.ts` — "此刻有全屏路由覆盖层吗",
  供 portal 到 body 的 modal **主动让屏**用。

### 0.3 覆盖层基元(4 个,`apps/desktop/src/app/overlays/`)

- `apps/desktop/src/app/overlays/overlay-view.tsx` — 所有路由覆盖层的根:等距 inset 卡片、
  浮动关闭按钮、Esc 层级(`ESCAPE_PRIORITY.overlay`)、`data-overlay-surface` 标记、
  重新钉住真实 titlebar 高度。
- `apps/desktop/src/app/overlays/overlay-chrome.tsx` — 24 行,一个 `OverlayIconButton`
  (与关闭 X 同尺寸的 ghost 图标按钮)。
- `apps/desktop/src/app/overlays/overlay-split-layout.tsx` — 宽屏左导轨 / 窄屏下拉的双列覆盖层布局
  (`OverlaySplitLayout`/`OverlaySidebar`/`OverlayMain`/`OverlayNavItem`/`OverlayNav` + 两个类型)。
- `apps/desktop/src/app/overlays/panel.tsx` — 另一套覆盖层语汇:**无边框卡片 + 密集行**
  (17 个导出,见 §2.2),cron / webhooks / agents / profiles / skills / starmap 都用它。

### 0.4 阻塞态与覆盖层屏幕(9 个)

- `apps/desktop/src/app/model-picker-overlay.tsx` — 把全局 `$modelPickerOpen` 与聚焦 tile 的
  runtime/model/provider 绑到 `ModelPickerDialog`;gateway 未开则整体不渲染。
- `apps/desktop/src/app/model-visibility-overlay.tsx` — 同上,针对 `ModelVisibilityDialog`。
- `apps/desktop/src/app/updates-overlay.tsx` — 更新对话框,五个 phase
  (idle / applying / manual / guiSkew / error)× 客户端 or 后端两个 target。
- `apps/desktop/src/components/boot-failure-overlay.tsx` — **硬启动失败的恢复面**:重试 / 修复 /
  切本地 / 打开日志 / 内嵌 Gateway 设置 / 远程重新登录(§3 端到端链的终点)。
- `apps/desktop/src/components/boot-failure-reauth.ts` — 上面那个覆盖层的**纯函数侧**
  (远程判定、认证形状错误识别、SSH 错误措辞映射、登录按钮文案),刻意剥离出 `.tsx` 以便无 React 单测。
- `apps/desktop/src/components/desktop-install-overlay.tsx` — 首次启动的 bootstrap 安装进度面:
  事件流 reducer、阶段行、日志、取消、失败重试,外加 setup-choice / unsupported-platform 两个分支。
- `apps/desktop/src/components/first-run-remote-form.tsx` — 首启时"连到已有远程 gateway"的表单
  (URL 探测 → 认证形状判定 → OAuth 登录或 token → 测试 → 应用)。
- `apps/desktop/src/components/gateway-connecting-overlay.tsx` — 冷启动期间的全屏 `CONNECTING` 解码动画,
  含一次性闩锁(冷启动完成后永不复现)与多相退场编排。
- `apps/desktop/src/components/prompt-overlays.tsx` — **回合中的阻塞式提问**:sudo 密码与 skill secret,
  任何关闭路径都映射为拒绝(空串),绝不把沉默当同意。

### 0.5 小组件与对话框(17 个,`apps/desktop/src/components/` 及 `particles/`)

- `apps/desktop/src/components/Backdrop.tsx` — 可开关的全屏背景图层(2.5% 透明度 + mix-blend-difference)。
- `apps/desktop/src/components/billing-banner.tsx` — 单会话的计费墙提示行,只提供恢复入口、从不禁用 composer。
- `apps/desktop/src/components/brand-mark.tsx` — 白底圆角的 nous-girl 品牌方块。
- `apps/desktop/src/components/error-boundary.tsx` — class 组件错误边界 + 默认的全屏崩溃兜底
  (重试 / 重载窗口 / 打开日志),三个 window root 都用它包。
- `apps/desktop/src/components/find-bar.tsx` — ⌘F 页内查找条,驱动 Electron `webContents.findInPage`;
  自带捕获期监听抢下 ⌘G / Esc。
- `apps/desktop/src/components/haptics-provider.tsx` — 把 `web-haptics` 的 trigger 注册进全局,
  并在 idle 时预热一个 AudioContext(否则首个触感要卡 ~850ms)。
- `apps/desktop/src/components/idle-mount.tsx` — `requestIdleCallback` 后才挂载子树,把隐藏面板移出首屏关键路径。
- `apps/desktop/src/components/language-switcher.tsx` — 语言选择(宽屏 Popover / 移动端 Sheet),
  自己做子串过滤以保住 en→zh→zh-hant→ja 的策展顺序。
- `apps/desktop/src/components/model-picker.tsx` — 模型选择对话框本体(cmdk 列表 + 价格/tier 展示 +
  "添加 provider" 直通 onboarding)。
- `apps/desktop/src/components/model-visibility-dialog.tsx` — 模型可见性对话框:按 provider 折叠、
  三态勾选、family 折叠。
- `apps/desktop/src/components/notifications.tsx` — 通知栈:**两个 portal 到 body 的区域**
  (顶部居中可展开栈 + 右下环境栈)+ `InlineNotice`。
- `apps/desktop/src/components/page-loader.tsx` — 页面级居中 loader(rose-curve)。
- `apps/desktop/src/components/particles/particle-field.tsx` — 通用上浮粒子发射器
  (配置、emitter 句柄、生命周期与 CSS 变量注入)。
- `apps/desktop/src/components/particles/particle-field.css` — 上面那个发射器的关键帧
  (`particle-rise` / `particle-sway` / `particle-pop` + reduced-motion 分支)。
- `apps/desktop/src/components/remote-display-banner.tsx` — 检测到 RDP/VNC 远程显示时发一条常驻 toast;
  自身 `return null`。
- `apps/desktop/src/components/session-picker.tsx` — TUI `/resume` 的桌面等价物:会话过滤列表对话框。
- `apps/desktop/src/components/status-dot.tsx` — 四色状态圆点(good/muted/warn/bad),被 messaging 等复用。

### 0.6 首启引导(4 个,`apps/desktop/src/components/onboarding/`)

- `apps/desktop/src/components/onboarding/index.tsx` — 引导覆盖层主体:provider 选择器、
  API-key 表单(`ApiKeyForm`)、目录动态扩展(`useApiKeyCatalog`)、"稍后再选"、退场编排。
- `apps/desktop/src/components/onboarding/flow.tsx` — 登录流程的各个状态屏
  (starting / awaiting_user / polling / external_pending / success / confirming_model / error)。
- `apps/desktop/src/components/onboarding/glyph.tsx` — 解码/乱码文字特效
  (`GlyphText` / `useDecoded` / `useScramble` / `DecodedLabel` / `HackeryButton`),复刻 CONNECTING 覆盖层的调性。
- `apps/desktop/src/components/onboarding/providers.tsx` — provider 行的展示层:
  `PROVIDER_DISPLAY` 排序/改名表 + 四种行组件 + `sortProviders`(设置页也复用)。

### 0.7 宠物(11 个,`apps/desktop/src/components/pet/`)

- `apps/desktop/src/components/pet/floating-pet.tsx` — 窗内浮动吉祥物:拉取 `pet.info`、拖拽、
  Alt+滚轮缩放、shift-click 弹出、接入漫游循环。
- `apps/desktop/src/components/pet/pet-bubble.tsx` — 只在弹出窗显示的说话气泡(按 `$petState` 选台词库并轮换)。
- `apps/desktop/src/components/pet/pet-egg-hatch.tsx` — 孵化中的蛋 + 进度条(`PetProgress`)。
- `apps/desktop/src/components/pet/pet-sprite.tsx` — **精灵图 canvas 渲染器**:行/帧解析、
  状态别名表、RAF 只在该换帧时唤醒、通过订阅而非 prop 读状态以免每 token 重渲染。
- `apps/desktop/src/components/pet/pet-star-shower.tsx` — 孵化揭晓的 canvas 庆祝特效(神光 + 星爆 + 上浮微粒)。
- `apps/desktop/src/components/pet/pet-thumb.tsx` — 单只宠物的 idle 帧缩略图(IntersectionObserver 懒加载)。
- `apps/desktop/src/components/pet/pixel-egg-sprite.tsx` — 12 帧像素蛋精灵,含亮度→奶油色 LUT 重着色
  与 bounce/hatch 两种模式。
- `apps/desktop/src/components/pet/roam-behavior.ts` — 漫游的**决策层**(纯函数):指数分布停留时长、
  休息/散步/跳跃三选一、散步目标点选取。
- `apps/desktop/src/components/pet/roam-geometry.ts` — 漫游的**几何层**:从活 DOM 量出可站立平台
  (窗底/状态栏顶/composer/profile rail),外加覆盖层专用单平台。
- `apps/desktop/src/components/pet/use-pet-roam.ts` — 漫游的**物理层**:pause/walk/fall/jump 状态机,
  直接写 `style.left/top`,只在落定时回灌 React。
- `apps/desktop/src/components/pet/use-pet-zoom-gesture.ts` — Alt+滚轮缩放手势的非 passive 监听封装。

### 0.8 宠物生成(11 个,`apps/desktop/src/app/pet-generate/`)

- `apps/desktop/src/app/pet-generate/pet-generate-overlay.tsx` — Dialog 外壳 + 按 phase 变宽 + 底部横幅文案。
- `apps/desktop/src/app/pet-generate/pet-generate-content.tsx` — generate → hatch → adopt 的控制器
  (store 是真源,这里只是薄视图)。
- `apps/desktop/src/app/pet-generate/components/draft-grid.tsx` — 2×2 草稿网格,未到的槽位是弹跳的蛋;
  支持流式到达即可选 + remix。
- `apps/desktop/src/app/pet-generate/components/empty-hint.tsx` — 6 个种子提示词 chip。
- `apps/desktop/src/app/pet-generate/components/generate-unavailable.tsx` — 无可用图像后端时的替代卡片
  (去设置 + 三个拿 key 的外链)。
- `apps/desktop/src/app/pet-generate/components/hatch-preview.tsx` — 蛋裂开 → 换成活宠物 →
  庆祝跳 → 轮播各状态行 → 命名并领养。
- `apps/desktop/src/app/pet-generate/components/hatching-view.tsx` — 孵化中的进度屏(row/compose/save 三阶段文案)。
- `apps/desktop/src/app/pet-generate/components/provider-picker.tsx` — 图像后端下拉,少于 2 个后端时隐藏。
- `apps/desktop/src/app/pet-generate/components/reference-chip.tsx` — 参考图附件 chip + lightbox。
- `apps/desktop/src/app/pet-generate/lib/frame-count.ts` — 行名 → 真实帧数的四级回退解析。
- `apps/desktop/src/app/pet-generate/lib/read-reference-image.ts` — 参考图读取:走 objectURL 解码后
  降采样再转 PNG dataURL,避免大文件先膨胀成 base64。

### 0.9 宠物弹出窗(2 个,`apps/desktop/src/app/pet-overlay/`)

- `apps/desktop/src/app/pet-overlay/overlay-root.tsx` — `?win=overlay` 这个 BrowserWindow 的挂载入口,
  额外注入一条强制透明的 style。
- `apps/desktop/src/app/pet-overlay/pet-overlay-app.tsx` — 弹出窗唯一视图:逐像素点击穿透、
  拖拽移动 OS 窗口、单击/双击/shift-click 语义、mini composer、缩放时重算窗口 bounds。

### 0.10 唤醒指示窗(3 个,`apps/desktop/src/app/wake-indicator/`)

- `apps/desktop/src/app/wake-indicator/wake-indicator-app.tsx` — `?win=wake` 窗口的视图:
  订阅 `hidden|detected|capturing` 三态并落到 `data-state`。
- `apps/desktop/src/app/wake-indicator/wake-indicator-root.tsx` — 该窗口的挂载入口(同样强制透明)。
- `apps/desktop/src/app/wake-indicator/wake-indicator.css` — 该窗口的全部样式(呼吸动画 + 两个状态分支
  + reduced-motion)。

### 0.11 面板页(9 个)

- `apps/desktop/src/app/cron/index.tsx` — Cron 覆盖层(1,225 行):主从列表、暂停/恢复/立即触发/删除、
  编辑对话框(手工 cron 或蓝图两套表单)、运行历史。
- `apps/desktop/src/app/cron/blueprints.tsx` — 自动化蓝图的桌面适配(把 `deliver=origin` 改写成 `local`)
  + 单个 slot 控件渲染 + 422 错误清洗。
- `apps/desktop/src/app/cron/cron-job-model.ts` — 纯模型层:script-only 判定、编辑器校验、更新载荷构造。
- `apps/desktop/src/app/cron/job-state.ts` — 状态色点表 + 有效状态推断 + 任务标题回退链
  (侧栏与 Cron 页共用,防漂移)。
- `apps/desktop/src/app/messaging/index.tsx` — 消息平台页(933 行):平台开关、env 字段编辑/清除、
  配对审批/撤销、事件驱动刷新。
- `apps/desktop/src/app/messaging/platform-icon.tsx` — 17 个平台的品牌图标/首字母兜底 avatar
  (含自绘 Photon logo、以及 forwardRef 以便 Tooltip 的 asChild 生效)。
- `apps/desktop/src/app/webhooks/index.tsx` — Webhooks 覆盖层(609 行):启用/重启、创建(URL + secret 一次性展示)、
  逐条订阅的配置详情、删除。
- `apps/desktop/src/app/artifacts/index.tsx` — 产物页:图片网格 + 文件表格、分页、按类型过滤、打开/定位。
- `apps/desktop/src/app/artifacts/artifact-utils.ts` — **从会话消息里挖产物**的纯逻辑
  (markdown/URL/路径三套正则 + 工具入参 JSON 递归 + 种类判定 + 远程模式取图)。

### 0.12 其余(2 个)

- `apps/desktop/src/app/learning/archive-skill-confirm-dialog.tsx` — 归档已学技能的共享确认框
  + 乐观更新回滚小工具 `fireOptimistic`。
- `apps/desktop/src/styles.css` — 整个 renderer 的样式表(2,266 行):Tailwind 入口、字体、
  `@theme inline` 令牌、`@layer base` 变量(含 **z-index 阶梯**)、引用/工具/思考块排版、
  composer 与 dock、代码卡片、宠物蛋动画。由 `apps/desktop/src/main.tsx:1` 单点 import。

**核对命令(点名覆盖率的机械口径):**

```verify
# 片内文件数
wc -l < /home/user/hermes-study/data/r10b/slices/J.txt          # -> 86
# 片内总行数
cd /home/user/hermes-agent && \
  awk '{print}' /home/user/hermes-study/data/r10b/slices/J.txt | \
  xargs wc -l | tail -1                                          # -> 18766 total
```

---

## 1. 这一簇解决什么问题

一个 agent harness 的桌面壳,除了"聊天"这条主线,还要回答四类问题:

1. **应用现在在哪?** —— 路由。但这个壳的路由不是"页面栈",而是三种东西挤在同一套 URL 上:
   会话(`/<sessionId>`)、**工作区整页**(skills / messaging / artifacts / 插件页)、
   **路由覆盖层**(settings / cron / webhooks / …,浮在聊天之上、关闭后回到原路由)。
   `apps/desktop/src/app/routes.ts` 就是这三类的判别器。
2. **应用起不来时怎么办?** —— 安装 → 连接 → 引导 → 启动失败 这条阻塞态链。
   每一态是一个占满屏幕的覆盖层,彼此靠 z 阶梯与互斥条件排队,**任何一态都必须提供出口**
   (重试 / 修复 / 改连接 / 重新登录 / 看日志),否则壳就是一块死屏。
3. **回合中途需要用户时怎么办?** —— `prompt-overlays.tsx`:sudo 密码与 skill secret。
   Python 侧会阻塞 agent 线程等 `*.respond`,所以渲染端**必须**把每一条关闭路径映射成显式拒绝。
4. **怎么让这些浮层不打架?** —— `styles.css` 里的 z 阶梯 + `OverlayView` 的 Esc 层级 +
   `useRouteOverlayActive()` 这种"主动让屏"的协议。

宠物那一簇是同一个壳的另一种极端:**一个可以离开窗口、变成独立 OS 窗口、并且必须逐像素点击穿透的 UI**。
它把"渲染进程里的一段状态"投影到操作系统层面,是这个仓库里对 Electron 多窗口能力用得最狠的地方。

---

## 2. 接缝穷举(判据 2)

### 2.1 路由表 —— `apps/desktop/src/app/routes.ts`

**内建路由 11 条,逐条列全**(id / path / view):

```verify
cd /home/user/hermes-agent/apps/desktop/src && sed -n '59,71p' app/routes.ts | grep -c "{ id:"   # -> 11
```

| # | id | path | view |
|---|---|---|---|
| 1 | `new` | `/` | `chat` |
| 2 | `settings` | `/settings` | `settings` |
| 3 | `command-center` | `/command-center` | `command-center` |
| 4 | `skills` | `/skills` | `skills` |
| 5 | `messaging` | `/messaging` | `messaging` |
| 6 | `webhooks` | `/webhooks` | `webhooks` |
| 7 | `artifacts` | `/artifacts` | `artifacts` |
| 8 | `cron` | `/cron` | `cron` |
| 9 | `profiles` | `/profiles` | `profiles` |
| 10 | `agents` | `/agents` | `agents` |
| 11 | `starmap` | `/starmap` | `starmap` |

`AppView` 联合有 **12** 项 = 上表 11 个 view 去重(`chat` 一次)后的 10 个 + `chat` + `extension`。
`extension` 没有对应的 `APP_ROUTES` 行,它是**贡献路由**的 view。

`apps/desktop/src/app/routes.ts:99 @ 863e313`

```
    .filter(route => Boolean(route.path.startsWith('/') && route.render) && !RESERVED_PATHS.has(route.path))
```

**第四类路径:会话路由。** 除保留路径与贡献路径外,任何单段 `/xxx` 都被解析成 session id:

`apps/desktop/src/app/routes.ts:155 @ 863e313`

```
export function routeSessionId(pathname: string): string | null {
  const path = routePathname(pathname)

  if (!path.startsWith(SESSION_ROUTE_PREFIX) || RESERVED_PATHS.has(path) || isContributedPath(path)) {
    return null
  }

  const id = path.slice(SESSION_ROUTE_PREFIX.length)

  return id && !id.includes('/') ? decodeURIComponent(id) : null
}
```

**覆盖层视图集合 7 项**(其余 view 落在工作区内):

`apps/desktop/src/app/routes.ts:125 @ 863e313`

```
export const OVERLAY_VIEWS: ReadonlySet<AppView> = new Set([
  'agents',
  'command-center',
  'cron',
  'profiles',
  'settings',
  'starmap',
  'webhooks'
])
```

由此可以把 12 个 view 分成三类,**无遗漏**:
- 覆盖层(7):agents / command-center / cron / profiles / settings / starmap / webhooks
- 工作区整页(4):artifacts / messaging / skills / extension
- 聊天(1):chat

`apps/desktop/src/app/routes.ts:205 @ 863e313`

```
function isWorkspacePageRoute(to: string): boolean {
  const view = appViewForPath(to)

  return view !== 'chat' && !isOverlayView(view)
}
```

**routes.ts 的导出面(32 项)**,机械枚举:

```verify
cd /home/user/hermes-agent/apps/desktop/src && grep -c "^export " app/routes.ts   # -> 32
cd /home/user/hermes-agent/apps/desktop/src && grep -n "^export " app/routes.ts   # 逐条
```

逐条列全(32 = 12 + 5 + 5 + 10):

- **路径常量 12**:`SESSION_ROUTE_PREFIX` · `NEW_CHAT_ROUTE` · `SETTINGS_ROUTE` · `COMMAND_CENTER_ROUTE` ·
  `SKILLS_ROUTE` · `MESSAGING_ROUTE` · `WEBHOOKS_ROUTE` · `ARTIFACTS_ROUTE` · `CRON_ROUTE` ·
  `PROFILES_ROUTE` · `AGENTS_ROUTE` · `STARMAP_ROUTE`(`SESSION_ROUTE_PREFIX` 与 `NEW_CHAT_ROUTE` 同为 `'/'`)。
- **类型 5**:`AppView` · `AppRouteId` · `AppRoute` · `RouteContribution` · `SidebarNavContribution`。
- **数据/atom 5**:`APP_ROUTES` · `ROUTES_AREA` · `SIDEBAR_NAV_AREA` · `OVERLAY_VIEWS` · `$workspaceIsPage`。
- **函数 10**:`contributedRoutes` · `isOverlayView` · `routePathname` · `isNewChatRoute` ·
  `routeSessionId` · `primaryRouteSelectedSessionId` · `sessionRoute` · `appViewForPath` ·
  `syncWorkspaceRoute` · `navigateToWorkspacePage`。

### 2.2 覆盖层触发条件全表(片 J 专属的重点)

先给"路由 → 布尔量"这一跳的全表,它是 7 个路由覆盖层的**唯一**开关来源:

`apps/desktop/src/app/shell/hooks/use-overlay-routing.ts:20 @ 863e313`

```
  const currentView = appViewForPath(location.pathname)
  const settingsOpen = currentView === 'settings'
  const commandCenterOpen = currentView === 'command-center'
  const agentsOpen = currentView === 'agents'
  const starmapOpen = currentView === 'starmap'
  const cronOpen = currentView === 'cron'
  const profilesOpen = currentView === 'profiles'
  const webhooksOpen = currentView === 'webhooks'
  const chatOpen = currentView === 'chat'
  const overlayOpen = isOverlayView(currentView)
```

下面是 **`wiring.tsx` 挂载的全部浮层 + 本片其它常驻浮层**的触发/关闭表。
"常驻"= 始终挂载、靠自身条件返回 null;"路由门"= 由上表布尔量条件渲染。

| 浮层 | 触发条件(锚点 + 摘录) | 关闭方式 / 再弹条件 |
|---|---|---|
| RemoteDisplayBanner | `apps/desktop/src/components/remote-display-banner.tsx:12`:`void window.hermesDesktop?.getRemoteDisplayReason?.().then(reason => {` | 不是浮层,发一条 durationMs=0 的常驻 toast;每次启动一次 |
| DesktopInstallOverlay | `apps/desktop/src/components/desktop-install-overlay.tsx:367`:`const shouldShow = useMemo(() => {` | 无关闭键;active/error/unsupported/setupChoice 四者皆假才消失。失败态有"重载重试"(先 resetBootstrap) |
| FirstRunRemoteForm | `apps/desktop/src/components/desktop-install-overlay.tsx:395`:`if (remoteOpen) {` | 由安装覆盖层内部 state 切换,Back 返回 |
| DesktopOnboardingOverlay | `apps/desktop/src/components/onboarding/index.tsx:268`:`if (onboarding.configured === true && !onboarding.manual) {` | 首启:选完 provider → Begin;或"稍后再选"永久跳过。手动模式有 X 关闭 |
| ModelPickerOverlay | `apps/desktop/src/app/model-picker-overlay.tsx:45`:`if (!gatewayOpen) {` | Radix Dialog,Esc/点外/取消;`$modelPickerOpen` 置回 false |
| SessionPickerOverlay | `apps/desktop/src/components/session-picker.tsx:46`:`<DialogPrimitive.Root onOpenChange={onOpenChange} open={open}>` | 同上;选中即 resume 并关闭 |
| ModelVisibilityOverlay | `apps/desktop/src/app/model-visibility-overlay.tsx:19`:`if (!gatewayOpen) {` | Radix Dialog |
| UpdatesOverlay | `apps/desktop/src/app/updates-overlay.tsx:46`:`const open = useStore($updateOverlayOpen)` | applying 阶段**禁止关闭**(`showCloseButton={phase !== 'applying'}`);其余阶段关闭会 reset apply 态 |
| GatewayConnectingOverlay | `apps/desktop/src/components/gateway-connecting-overlay.tsx:68`:`const connecting =` | 无关闭键;连上后走三段退场。**冷启动完成过一次就永不再弹**(`coldBootDoneRef`) |
| BootFailureOverlay | `apps/desktop/src/components/boot-failure-overlay.tsx:62`:`const visible = Boolean(boot.error) && !boot.running` | 无关闭键;只能靠动作恢复。onboarding flow 非 idle/error 时被抑制 |
| CommandPalette / SessionSwitcher / FileActionDialogs / RemoteFolderPicker | 片 A/B 地盘,本片不展开 | — |
| FindBar | `apps/desktop/src/components/find-bar.tsx:124`:`if (!active) {` | Esc / X / **路由变化时 effect cleanup 强制关闭** |
| PetGenerateOverlay | `apps/desktop/src/app/pet-generate/pet-generate-overlay.tsx:44`:`if (useRouteOverlayActive()) {` | 关闭不打断后台生成;路由覆盖层打开时**主动让屏并在返回时复现** |
| 路由覆盖层 ×7(settings/command-center/agents/cron/webhooks/profiles/starmap) | `apps/desktop/src/app/contrib/wiring.tsx:1086`:`{cronOpen && (` | Esc(`OverlayView` 的 escape layer)、点背板、X;都调 `closeOverlayToPreviousRoute` 回到进入前的路由 |
| NotificationStack | `apps/desktop/src/components/notifications.tsx:82`:`{defaultStack.length > 0 && (` | 逐条 X / "Clear all";portal 到 body 的 `--z-over-modal` 上,所以能盖住对话框 |
| PromptOverlays(Sudo) | `apps/desktop/src/components/prompt-overlays.tsx:106`:`if (!request) {` | 任何关闭路径 = 发空串 = 拒绝 |
| PromptOverlays(Secret) | `apps/desktop/src/components/prompt-overlays.tsx:207`:`if (!request) {` | 同上 |
| FloatingPet | `apps/desktop/src/components/pet/floating-pet.tsx:428`:`if (!info.enabled || !info.spritesheetBase64 || overlayActive) {` | 不可关闭;由 `/pet` 开关 + 弹出状态决定 |
| 崩溃兜底 | `apps/desktop/src/components/error-boundary.tsx:43`:`if (!error) {` | Retry(重置 boundary)/ 重载窗口 / 打开日志 |

**互斥关系(这一片最容易踩的坑)**——三条,都在代码里显式写死:

1. `boot.error` 为真时 **connecting 覆盖层主动退场**,把屏交给 boot-failure:

`apps/desktop/src/components/gateway-connecting-overlay.tsx:123 @ 863e313`

```
  // Boot failed — BootFailureOverlay owns the screen; don't linger behind it.
  if (boot.error && !previewing) {
    return null
  }
```

2. onboarding flow 正在跑(非 idle / 非 error)时,**boot-failure 被抑制**:

`apps/desktop/src/components/boot-failure-overlay.tsx:63 @ 863e313`

```
  // While first-run onboarding owns the picker/flow we let it surface its own
  // progress; the recovery overlay is for hard failures, which it covers via a
  // higher z-index regardless of onboarding state.
  const suppressed = onboarding.flow.status !== 'idle' && onboarding.flow.status !== 'error'
```

3. 路由覆盖层打开时,**portal 到 body 的宠物生成对话框主动让屏**(store 保持 open,返回时重挂载并重新探测):

`apps/desktop/src/app/hooks/use-route-overlay-active.ts:15 @ 863e313`

```
export function useRouteOverlayActive(): boolean {
  const { pathname } = useLocation()

  return isOverlayView(appViewForPath(pathname))
}
```

**z 阶梯 12 级**(定义在 `apps/desktop/src/styles.css:215–229`;`.css` 不在引用校验器扩展名白名单上,
**此处锚点不受机械校验**,内容以 `sed -n '215,229p'` 复核):

```verify
cd /home/user/hermes-agent/apps/desktop/src && sed -n '215,229p' styles.css | grep -c -- "--z-"   # -> 12
```

12 条声明逐条列全:
`--z-modal-backdrop:120` → `--z-modal:130` → `--z-modal-popover:140` → `--z-over-modal:200` →
`--z-over-modal-content:210` → `--z-switcher-backdrop:219` → `--z-switcher:220` →
`--z-connecting:1200` → `--z-onboarding:1300` → `--z-onboarding-popover:1310` →
`--z-setup:1400` → `--z-crash:1500`。
最后五条构成"启动链":连接中 → 引导 →(引导内弹出的 popover)→ 安装/恢复 → 崩溃,
数值刻意稀疏,方便日后在两级之间插一层而不必全体重编号。

### 2.3 keybind action 面 —— `apps/desktop/src/app/hooks/use-keybinds.ts`

`handlersRef.current` 一共注册 **71** 个 action id:44 个字面量 + 18 个 `profile.switch.N` + 9 个 `session.slot.N`。

```verify
cd /home/user/hermes-agent/apps/desktop/src && \
  sed -n '173,269p' app/hooks/use-keybinds.ts | grep -cE "^    '[a-zA-Z.0-9]+'"          # -> 44
grep -n "PROFILE_SLOT_COUNT = \|SESSION_SLOT_COUNT = " /home/user/hermes-agent/apps/desktop/src/lib/keybinds/actions.ts
# -> PROFILE_SLOT_COUNT = 18 ; SESSION_SLOT_COUNT = 9   (44 + 18 + 9 = 71)
```

44 个字面量 id 逐个列全(按源码顺序):
`keybinds.openPanel` ·
`composer.focus` · `composer.modelPicker` · `composer.voice` ·
`nav.commandPalette` · `nav.commandCenter` · `nav.settings` · `nav.profiles` · `nav.skills` ·
`nav.messaging` · `nav.artifacts` · `nav.cron` · `nav.agents` ·
`session.new` · `session.newTab` · `session.newWindow` · `session.next` · `session.prev` ·
`session.focusSearch` · `session.togglePin` ·
`workspace.newWorktree` · `workspace.openFolder` ·
`view.toggleSidebar` · `view.toggleRightSidebar` · `view.toggleReview` · `view.toggleStatusbar` ·
`view.showFiles` · `view.showTerminal` · `view.newTerminal` · `view.nextTerminal` · `view.prevTerminal` ·
`view.closeTerminal` · `view.flipPanes` · `view.closeTab` · `view.reopenTab` · `view.findInPage` ·
`view.findNext` · `view.findPrevious` ·
`appearance.toggleMode` ·
`profile.default` · `profile.next` · `profile.prev` · `profile.toggleAll` · `profile.create`。

**分发器的让路顺序**(同一个 window keydown 上有四个竞争者,顺序写死在一个函数里):
capture 模式吞掉一切 → 会话切换器开着时 Esc 归它 → **查找条开着时 ⌘G/⌘⇧G/Esc 归它** →
未绑定的可打印键走 type-to-focus → 可编辑焦点里非白名单组合直接放行 →
软 `/`/Enter 需过闸 → 内建 handler → 贡献 handler。

`apps/desktop/src/app/hooks/use-keybinds.ts:339 @ 863e313`

```
      if ($findInPage.get().active && findBarClaimsCombo(combo)) {
        return
      }
```

### 2.4 `apps/desktop/src/app/overlays/panel.tsx` 导出面(17 项)

```verify
cd /home/user/hermes-agent/apps/desktop/src && grep -c "^export " app/overlays/panel.tsx   # -> 17
```

组件 14 个:`Panel` · `PanelHeader` · `PanelBody` · `PanelList` · `PanelListRow` · `PanelRowMenu` ·
`PanelDetail` · `PanelEmpty` · `PanelSectionLabel` · `PanelMeta` · `PanelBlock` · `PanelPill` ·
`PanelAddButton` · `PanelAction`;类型 3 个:`PanelMenuItem` · `PanelMetaRow` · `PanelPillTone`。

**使用方 8 个文件**(不抽样,逐个列):

```verify
cd /home/user/hermes-agent/apps/desktop/src && grep -rl "overlays/panel'" --include=*.tsx . | sort
```

`./app/agents/index.tsx` · `./app/cron/index.tsx` · `./app/profiles/index.tsx` ·
`./app/settings/config-settings.tsx` · `./app/skills/index.tsx` · `./app/skills/mcp-tab.tsx` ·
`./app/starmap/index.tsx` · `./app/webhooks/index.tsx`。

### 2.5 `apps/desktop/src/app/overlays/overlay-split-layout.tsx` 导出面(7 项)与使用方(2 个)

导出:`OverlaySplitLayout` · `OverlaySidebar` · `OverlayMain` · `OverlayNavItem` · `OverlayNav` +
类型 `OverlayNavLink` · `OverlayNavGroup`。

```verify
cd /home/user/hermes-agent/apps/desktop/src && \
  grep -rl "overlays/overlay-split-layout'" --include=*.tsx . | sort
# -> ./app/command-center/index.tsx
#    ./app/settings/index.tsx
```

**只有 command-center 与 settings 用它**(证据面:`apps/desktop/src/` 全目录、`*.tsx`/`*.ts`、
按导入路径字符串 `overlays/overlay-split-layout'` 匹配,排除该文件自身)。这条负结论直接推翻一处文档断言,见 §5 ▲1。

### 2.6 宠物弹出窗的控制消息面(7 种)

渲染端 → 主进程的控制通道是一个 7 分支的判别联合,**7 种全部在弹出窗里被发出**:

`apps/desktop/src/store/pet-overlay.ts:53 @ 863e313`

```
export type PetOverlayControl =
  | { type: 'pop-in' }
  | { type: 'ready' }
  | { type: 'submit'; text: string }
  | { type: 'bounds'; bounds: PetOverlayBounds }
  | { type: 'open-app' }
  | { type: 'toggle-app' }
  | { type: 'scale'; scale: number }
```

```verify
# 7 种消息(联合分支数)
cd /home/user/hermes-agent/apps/desktop && sed -n '54,60p' src/store/pet-overlay.ts | grep -c "type: '"
# 8 处发送点(bounds 发两次:拖拽落定一次、缩放改窗一次)
cd /home/user/hermes-agent/apps/desktop && grep -c "petOverlay?.control(" src/app/pet-overlay/pet-overlay-app.tsx
```

逐条对应(发送点行号):
`ready`(挂载完成,`:115`)· `bounds`(拖拽落点持久化,`:256`;缩放改窗后再发一次,`:361`)·
`pop-in`(shift-click,`:266`)· `toggle-app`(双击,`:276`)· `submit`(mini composer 回车,`:291`)·
`open-app`(邮件图标,`:301`)· `scale`(Alt+滚轮,`:311`)。**7 种消息、8 处发送点。**

**主进程 → 弹出窗**只有一条 `onState`,载荷是 `PetOverlayStatePayload`
(`info` / `activity` / `busy` / `awaiting` / `unread` / `reaction`,共 6 个字段)。

`apps/desktop/src/store/pet-overlay.ts:42 @ 863e313`

```
export interface PetOverlayStatePayload {
  info: PetInfo
  activity: PetActivity
  busy: boolean
  awaiting: boolean
  /** Drives the overlay's mail icon: a finish landed while you were away. */
  unread: boolean
  /** Latest reaction — bumping its id forwards a burst to the overlay. */
  reaction: PetReaction | null
}
```

预加载桥自身的方法面(9 个):`open` · `close` · `setBounds` · `setIgnoreMouse` · `setFocusable` ·
`pushState` · `control` · `onState` · `onControl`(`apps/desktop/src/global.d.ts:54–64`)。

### 2.7 宠物窗内的对外动作面

| 手势 / 输入 | 处理位置(锚点 + 摘录) | 结果 |
|---|---|---|
| 拖拽(窗内) | `apps/desktop/src/components/pet/floating-pet.tsx:329`:`const onPointerMove = useCallback(` | 直接改 DOM style,不触发 React 重渲染;松手才提交并持久化 |
| Shift+按下(窗内) | `apps/desktop/src/components/pet/floating-pet.tsx:318`:`if (e.shiftKey && !isSecondaryWindow()) {` | 弹出成独立 OS 窗口 |
| Alt+滚轮(两处通用) | `apps/desktop/src/components/pet/use-pet-zoom-gesture.ts:42`:`const onWheel = (event: WheelEvent) => {` | 向光标缩放并持久化 scale |
| 窗口 focus | `apps/desktop/src/components/pet/floating-pet.tsx:263`:`const onFocus = () => clearPetUnread()` | 清"有新消息"提示 |
| profile 切换 | `apps/desktop/src/components/pet/floating-pet.tsx:240`:`useOnProfileSwitch(() => {` | 丢弃上一个 profile 的宠物与画廊缓存 |
| 漫游开关 | `apps/desktop/src/store/pet.ts:218`:`export const $petRoam = atom<boolean>(storedBoolean(ROAM_KEY, false))` | 默认关;持久化 |
| 弹出窗单击 | `apps/desktop/src/app/pet-overlay/pet-overlay-app.tsx:281`:`clickTimerRef.current = setTimeout(() => {` | 延迟 250ms 开 mini composer(被双击取消) |
| 弹出窗双击 | `apps/desktop/src/app/pet-overlay/pet-overlay-app.tsx:276`:`window.hermesDesktop?.petOverlay?.control({ type: 'toggle-app' })` | 最小化 ↔ 还原主窗 |
| 弹出窗 shift-click | `apps/desktop/src/app/pet-overlay/pet-overlay-app.tsx:266`:`window.hermesDesktop?.petOverlay?.control({ type: 'pop-in' })` | 收回窗内 |
| 弹出窗鼠标移动 | `apps/desktop/src/app/pet-overlay/pet-overlay-app.tsx:167`:`const onMove = (ev: MouseEvent) => {` | 逐像素 alpha 采样决定是否点击穿透 |

### 2.8 四张面板页的后端调用面(逐条列全,不抽样)

**Cron**(`apps/desktop/src/app/cron/index.tsx:29–45` 的 import 即完整清单):
`getCronJobs` · `createCronJob` · `updateCronJob` · `deleteCronJob` · `pauseCronJob` · `resumeCronJob` ·
`triggerCronJob` · `getCronJobRuns` · `getCronDeliveryTargets` · `getAutomationBlueprints` ·
`instantiateAutomationBlueprint` —— **11 个**。

**Messaging**(`apps/desktop/src/app/messaging/index.tsx:14–23`):
`getMessagingPlatforms` · `updateMessagingPlatform` · `getPairing` · `approvePairing` · `revokePairing`
—— **5 个**,外加 `runGatewayRestart`。

**Webhooks**(`apps/desktop/src/app/webhooks/index.tsx:23–31`):
`getWebhooks` · `createWebhook` · `deleteWebhook` · `enableWebhooks` · `setWebhookEnabled` —— **5 个**,
外加 `runGatewayRestart`。

**Artifacts**:没有自己的后端端点 —— 它**从会话消息里现挖**:
`listAllProfileSessions(30, 1)` + 每个会话一次 `getSessionMessages`,再跑 `collectArtifactsForSession`。

`apps/desktop/src/app/artifacts/index.tsx:132 @ 863e313`

```
      const sessions = (await listAllProfileSessions(30, 1)).sessions
      const results = await Promise.allSettled(sessions.map(session => getSessionMessages(session.id, session.profile)))
```

面板页的其它固定枚举:cron 的 `SCHEDULE_OPTIONS` **7** 项、`STATE_DOT` **7** 个状态、
webhooks 的 `DELIVER_OPTIONS` **6** 项、messaging 的 `PLATFORM_ICONS` **17** 个平台、
artifacts 的 `ARTIFACT_FILTERS` **4** 项与 `ARTIFACT_COLUMNS` **3** 列。

```verify
cd /home/user/hermes-agent/apps/desktop/src && \
  echo -n "SCHEDULE_OPTIONS="; sed -n '89,97p' app/cron/index.tsx | grep -c "value:"; \
  echo -n "STATE_DOT="; sed -n '6,12p' app/cron/job-state.ts | grep -c ":"; \
  echo -n "PLATFORM_ICONS="; sed -n '55,72p' app/messaging/platform-icon.tsx | grep -c ": {"; \
  echo -n "ARTIFACT_COLUMNS="; sed -n '622,647p' app/artifacts/index.tsx | grep -c "id: '"
# -> SCHEDULE_OPTIONS=7 / STATE_DOT=7 / PLATFORM_ICONS=17 / ARTIFACT_COLUMNS=3
```

### 2.9 `apps/desktop/src/app/hooks/` 导出面(11 项 / 7 文件)

```verify
cd /home/user/hermes-agent/apps/desktop/src && grep -c "^export " app/hooks/*.ts | paste -sd' '
# use-config-record.ts:4  use-debounced.ts:1  use-keybinds.ts:2  use-on-profile-switch.ts:1
# use-refresh-hotkey.ts:1  use-route-enum-param.ts:1  use-route-overlay-active.ts:1   (合计 11)
```

`use-config-record.ts` 是唯一导出 >1 的:`HERMES_CONFIG_KEY` · `useHermesConfigRecord` ·
`setHermesConfigCache` · `invalidateHermesConfig`;`use-keybinds.ts` 导出 `KeybindRuntimeDeps` + `useKeybinds`。

### 2.10 三个 window root 的分派(片 J 占其中两个)

`apps/desktop/src/main.tsx:40 @ 863e313`

```
const winParam = new URLSearchParams(window.location.search).get('win')

if (winParam === 'overlay') {
  void import('./app/pet-overlay/overlay-root').then(({ mountPetOverlay }) => mountPetOverlay())
} else if (winParam === 'quick') {
  void import('./app/quick-entry/quick-entry-root').then(({ mountQuickEntry }) => mountQuickEntry())
} else if (winParam === 'wake') {
  void import('./app/wake-indicator/wake-indicator-root').then(({ mountWakeIndicator }) => mountWakeIndicator())
} else {
```

`?win=overlay` → 本片的宠物弹出窗;`?win=wake` → 本片的唤醒指示窗;`?win=quick` → 别的片;
无参数 → 完整应用。**三个副窗都用同一份 bundle 与同一份 `styles.css`**,靠一条后注入的
`html,body,#root{background:transparent !important;}` 覆掉 index.html 里为防闪烁而画的不透明底。

---

## 3. 端到端链:启动失败 → 状态置位 → 弹哪个覆盖层 → 用户能做什么(判据 3)

### 跳 1:gateway 引导抛错 → `failDesktopBoot(message)`

`apps/desktop/src/app/gateway/hooks/use-gateway-boot.ts:325 @ 863e313`

```
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : String(err)
          failDesktopBoot(message)
          notifyError(err, translateNow('boot.errors.desktopBootFailed'))
          setSessionsLoading(false)
        }
      } finally {
```

(同一文件另有 5 处 `failDesktopBoot` 调用点:`:104` 桥不可用、`:212` 连接丢失、`:478` 后端启动中退出、
`:551`;搜索面 = `apps/desktop/src/` 全目录 `*.ts`/`*.tsx`,排除 `*.test.*`。)

### 跳 2:store 置位 —— `error` + `running:false` + `visible:true`

`apps/desktop/src/store/boot.ts:83 @ 863e313`

```
export function failDesktopBoot(message: string) {
  const current = $desktopBoot.get()
  $desktopBoot.set({
    ...current,
    error: message,
    message: translateNow('boot.desktopBootFailedWithMessage', message),
    phase: 'renderer.error',
    progress: clampProgress(current.progress),
    running: false,
    timestamp: Date.now(),
    visible: true
  })
}
```

### 跳 3a:CONNECTING 覆盖层让屏

`apps/desktop/src/components/gateway-connecting-overlay.tsx:66 @ 863e313`

```
  const initialBootActive = boot.visible || boot.running || boot.progress < 100

  const connecting =
    !coldBootDoneRef.current && !gatewaySwitching && gatewayState !== 'open' && !boot.error && initialBootActive
```

`!boot.error` 直接把 `connecting` 打成 false,再加上 `:124` 的提前 `return null`,连正在退场的动画都不留。

### 跳 3b:BootFailureOverlay 上屏

`apps/desktop/src/components/boot-failure-overlay.tsx:62 @ 863e313`

```
  const visible = Boolean(boot.error) && !boot.running
```

### 跳 4:判定这是不是"远程会话过期",决定给哪三个按钮

`apps/desktop/src/components/boot-failure-reauth.ts:121 @ 863e313`

```
export function isRemoteReauthFailure(
  config: DesktopConnectionConfig | null | undefined,
  error?: string | null
): boolean {
  return (
    isRemoteConfig(config) &&
    config!.remoteAuthMode === 'oauth' &&
    (!config!.remoteOauthConnected || isRemoteReauthError(error))
  )
}
```

这里有一处**值得学的设计**:判定不只看连接状态,还要看错误文本。注释解释了为什么:

`apps/desktop/src/components/boot-failure-reauth.ts:47 @ 863e313`

```
// True when a boot error is auth-shaped — the refresh token was rejected or the
// remote couldn't mint a websocket ticket. The Settings indicator can still read
// "connected" (a stale RT cookie exists), so the error text is part of the
// signal; without it a connected-but-expired session drops into the local-only
// recovery buttons for a problem only reauth can fix.
```

### 跳 5:按失败种类换掉整组动作(三套,互斥)

`apps/desktop/src/components/boot-failure-overlay.tsx:251 @ 863e313`

```
  if (remoteReauth) {
    actions = [
      {
        key: 'signin',
        label: copy.signOutAndSignIn,
        onClick: () => void signInRemote(),
        icon: <LogIn />,
        busy: 'signin'
      },
      { ...settingsAction, variant: 'secondary' },
      localAction
    ]
    hint = copy.remoteSignInHint(label)
  } else if (remoteFailure) {
    actions = [settingsAction, { ...retryAction, variant: 'secondary' }, localAction]
    hint = copy.remoteFailureHint
  } else {
```

三条恢复路径与它们打到的 IPC:

| 动作 | 出现在 | IPC(锚点 + 摘录) |
|---|---|---|
| Sign out & sign in | 远程 reauth | `apps/desktop/src/components/boot-failure-overlay.tsx:179`:`await window.hermesDesktop?.oauthLogoutConnectionConfig?.()` |
| Gateway settings | 三种都有 | `apps/desktop/src/components/boot-failure-overlay.tsx:301`:`<GatewaySettings embedded />` |
| Retry | 远程非 reauth / 本地 | `apps/desktop/src/components/boot-failure-overlay.tsx:148`:`await window.hermesDesktop?.resetBootstrap().catch(() => undefined)` |
| Repair install | 仅本地 | `apps/desktop/src/components/boot-failure-overlay.tsx:154`:`await window.hermesDesktop?.repairBootstrap().catch(() => undefined)` |
| Use local gateway | 远程两种 | `apps/desktop/src/components/boot-failure-overlay.tsx:161`:`await window.hermesDesktop?.applyConnectionConfig({ mode: 'local' }).catch(() => undefined)` |
| Open logs | 全部 | `apps/desktop/src/components/boot-failure-overlay.tsx:201`:`const openLogs = () => void window.hermesDesktop?.revealLogs().catch(() => undefined)` |

**这条链的设计要点(可迁移)**:
- "本地失败"与"远程失败"的恢复动作是**不相交的**——本地的 Retry/Repair 对着一个死掉的远程毫无意义,
  所以代码不是把六个按钮都摆出来再灰掉,而是**换掉整组**并配一句针对性的 hint。
- 恢复面自己**内嵌**真正的设置面板(`<GatewaySettings embedded />`),不是再画一份连接表单。
  注释明确写了理由:"identical URL/auth/test/save controls — no parallel form to drift"。
- 连接设置是 `lazy()` 的,不进常驻覆盖层的首包。

---

## 4. 逐区域要点

### 4.1 路由的三态判别是这一片的地基

`appViewForPath` 的判定顺序是:新聊天 or 会话 id → `chat`;贡献路径 → `extension`;
查表 → 对应 view;查不到 → **回落 `chat`**。这个"回落 chat"曾经是个坑,注释里留了案底:

`apps/desktop/src/app/routes.ts:28 @ 863e313`

```
  // A contributed (plugin) full page at its own route — NOT chat. Without this
  // distinction contributed paths fell through appViewForPath's 'chat' default,
  // so the sidebar kept a session highlighted and the titlebar kept the
  // session-title dropdown while a plugin page was showing.
```

另一处同源的教训:`routePathname` 必须先剥 query,否则 `/skills?tab=mcp` 会被 session-id 解析器
读成一个叫 `skills?tab=mcp` 的会话。

### 4.2 两套覆盖层语汇,不是重复而是分工

| | `OverlaySplitLayout` | `Panel` |
|---|---|---|
| 形态 | 左导轨 + 右主区(窄屏塌成下拉条) | 无边框卡片 + 密集单行列表 + 详情 |
| 使用方 | settings、command-center | cron、webhooks、agents、profiles、skills、starmap、config-settings |
| 共同底座 | 都套在 `OverlayView` 里 | 同左(`Panel` 直接 `return <OverlayView …>`) |

`Panel` 的注释把它的取舍写死了:"**NO container borders** (rows separate via the row-hover/active bg
vars + gaps)"。这解释了为什么 `PanelListRow` 是一个 `<div>` 容器而不是 `<button>`:
行里要同时放"选中"点击目标和一个 kebab 菜单,嵌套交互元素不可接受。

`apps/desktop/src/app/overlays/panel.tsx:166 @ 863e313`

```
// A row is a container (not a <button>) so it can host both the select target
// and a kebab menu without nesting interactive elements. Hover/active bg lives
// on the wrapper so the whole row highlights as one. When `menuItems` is passed,
// the whole row also answers right-click with the same actions as its kebab.
```

### 4.3 `OverlayView` 的三个非显然细节

1. **Esc 走层级栈而不是各管各的**:`pushEscapeLayer(ESCAPE_PRIORITY.overlay)` +
   `isTopEscapeLayer(...)`,所以在 settings 里开一个 Radix 对话框,Esc 先关对话框。
2. **`data-overlay-surface` 是给 composer 看的**:覆盖层盖住聊天时 composer 仍然挂载,
   这个标记让全局 type-to-focus / 软 `/` / Enter 全部让位,免得按键漏进看不见的输入框。
3. **重新钉住 `--titlebar-height`**:contrib 外壳会把内容区的这个变量清零(面板在自己的行内标题栏之下),
   而 CSS 变量沿 DOM 继承,所以一个挂在 zone 里的 fixed 覆盖层会读到 0 并溢出到边缘。

### 4.4 宠物漫游:三层切分是这一片最值得抄的结构

- **几何层** `roam-geometry.ts`:每一拍现场量 DOM,回答"哪儿能站"。可站立面 = 窗底(或状态栏顶)
  + `[data-slot="composer-surface"]` + `[data-slot="profile-rail"]`。想加游乐设施就加一个 `data-slot`。

`apps/desktop/src/components/pet/roam-geometry.ts:91 @ 863e313`

```
export function snapshotLedges(petW: number, petH: number): Ledge[] {
  const width = vw()
  const height = vh()
  const ledges: Ledge[] = [{ left: 0, right: Math.max(0, width - petW), y: floorY(width, height, petH) }]
```

- **决策层** `roam-behavior.ts`:每一拍决定干什么。全部函数接受可注入 `rng`,所以节奏可单测。
  核心取舍写在文件头:"Loaf, don't pace"(`REST_CHANCE = 0.62`)+ "Memoryless dwell times"(指数分布)。

`apps/desktop/src/components/pet/roam-behavior.ts:68 @ 863e313`

```
export function chooseMove(canHop: boolean, rng: Rng = Math.random): RoamMove {
  if (rng() < REST_CHANCE) {
    return 'rest'
  }

  return canHop && rng() < HOP_CHANCE ? 'hop' : 'stroll'
}
```

- **物理层** `use-pet-roam.ts`:pause / walk / fall / jump 四态机,直接写 DOM style。
  两条工程性细节值得抄:(a) `MAX_DT_S = 0.05` 封顶 dt,防止后台标签页恢复时宠物瞬移;
  (b) pause 阶段用 `setTimeout(min(delay, 250ms))` 而不是 60Hz RAF 空转。

覆盖层打开时,可站立面被**整体替换**成覆盖层卡片的底边一条:

`apps/desktop/src/components/pet/use-pet-roam.ts:236 @ 863e313`

```
    const planNext = (now: number) => {
      // An open overlay swaps the surface set to just its bottom edge, so the pet
      // patrols along it; closing it restores the normal surfaces (and the pet
      // drops to whatever's below).
      const ledges = overlayOpen ? [overlayLedge(petW)] : snapshotLedges(petW, petH)
      curLedge = resolveLedge(ledges, cur.x, cur.y, petH)
```

而 `overlayLedge` **不测量 DOM**,它按 `OverlayView` 的等距 inset 公式反推 —— 两个文件之间靠一条注释约定耦合。
这是本片里唯一一处"两个模块用同一个魔法常量但不共享代码"的地方,记为移交项 H-R10B-J-g。

漫游总开关:`enabled: roamEnabled && active && !overlayActive && atRest`。

`apps/desktop/src/components/pet/floating-pet.tsx:411 @ 863e313`

```
  usePetRoam({
    commit: commitRoamPosition,
    containerRef,
    enabled: roamEnabled && active && !overlayActive && atRest,
    isInteracting: isDragging,
    loopMs: info.loopMs ?? 1100,
    overlayOpen: routeOverlayOpen,
    petH,
    petW
  })
```

### 4.5 弹出窗:逐像素点击穿透

弹出窗是个完整矩形,但绝大部分透明。它靠"ignore + forward"模式:默认让鼠标穿透,
同时仍然收 mousemove,于是每次移动都用 `elementFromPoint` + canvas alpha 采样重新判断是否该抢回鼠标。

`apps/desktop/src/app/pet-overlay/pet-overlay-app.tsx:159 @ 863e313`

```
      try {
        return ctx.getImageData(px, py, 1, 1).data[3] >= ALPHA_HIT_THRESHOLD
      } catch {
        // Tainted/zero-size read — fail open so the pet stays grabbable.
        return true
      }
```

为此 `PetSprite` 的 canvas 必须用 `willReadFrequently: true` 开 CPU 回读路径
(`apps/desktop/src/components/pet/pet-sprite.tsx:173`),否则每次采样都要把 GPU 纹理读回来。
**这是一条跨文件的隐式契约**:采样在 `pet-overlay-app.tsx`,开关在 `pet-sprite.tsx`,注释在两边都写了。

### 4.6 两个"事件驱动 vs 轮询"的双模式

本片有三处同一形态:后端支持变更广播时用事件,否则回落到定时轮询。

| 位置 | 事件源 | 有事件时 | 无事件时 |
|---|---|---|---|
| 宠物信息 | `$petChange` | 无定时器 | 无宠物 3s / 有宠物 15s |
| cron 运行历史 | `$cronChangeTick` | 60s 兜底 | 8s |
| messaging | `$platformsChangeTick` / `$pairingChangeTick` | 无定时器 | 6s |

`apps/desktop/src/components/pet/floating-pet.tsx:216 @ 863e313`

```
    const timer = changeEventsAvailable
      ? null
      : window.setInterval(
          () => {
            if (document.visibilityState === 'visible') {
              void pull()
            }
          },
          active ? PET_ACTIVE_REFRESH_MS : PET_POLL_MS
        )
```

注意最后那句注释交代的动机:"users with no pet especially (this used to poll hardest for them)" ——
**没有宠物的用户轮询得最凶**,因为快轮询是为了"用户刚 `/pet boba` 完要几秒内出现"。事件化后这条成本归零。

### 4.7 面板页共享的四条约定

1. **裸 `r` 刷新**:cron / messaging / webhooks / artifacts 四张页都挂 `useRefreshHotkey`。
2. **`?tab=` 存活刷新**:messaging 用 `useRouteEnumParam('platform', …)`,artifacts 用
   `useRouteEnumParam('tab', ARTIFACT_FILTERS, 'all')`。
3. **乐观更新 + 快照回滚**:messaging 的批准/撤销先本地移行,失败恢复快照。
4. **profile scope 参与查询键**:cron 按 `$profileScope` 取任务,webhooks 把 scope 放进 react-query key。

`apps/desktop/src/app/cron/index.tsx:312 @ 863e313`

```
  const refresh = useCallback(async () => {
    try {
      setCronJobs(await getCronJobs(profileScope === ALL_PROFILES ? 'all' : profileScope))
    } catch (err) {
      notifyError(err, c.failedLoad)
    } finally {
      setLoading(false)
    }
  }, [c, profileScope])
```

其中 cron 的"写"路径要把 `all` 折叠成 `default`,因为 `all` 不是可写目标:

`apps/desktop/src/app/cron/index.tsx:457 @ 863e313`

```
  async function handleBlueprintCreate(blueprint: AutomationBlueprint, values: Record<string, string>) {
    const profile = profileScope === ALL_PROFILES ? 'default' : profileScope
    const job = await instantiateAutomationBlueprint({ blueprint: blueprint.key, values }, profile)
```

### 4.8 cron 的纯模型层:script-only 任务这个特例

`apps/desktop/src/app/cron/cron-job-model.ts:18 @ 863e313`

```
export function validateCronEditor(input: CronEditorValidationInput): CronEditorValidationError | null {
  const trimmedPrompt = input.prompt.trim()
  const trimmedSchedule = input.schedule.trim()

  if (!trimmedSchedule && !trimmedPrompt && !input.scriptOnlyJob) {
    return 'prompt_and_schedule'
  }

  if (!trimmedSchedule) {
    return 'schedule'
  }

  if (!input.scriptOnlyJob && !trimmedPrompt) {
    return 'prompt'
  }

  return null
}
```

配套的写入侧刻意**不写** model/provider,因为 script-only 任务根本不跑 agent:

`apps/desktop/src/app/cron/cron-job-model.ts:62 @ 863e313`

```
  // Script-only jobs never run an agent, so the scheduler ignores model
  // overrides — leave whatever is stored untouched. For agent jobs, always
  // write both axes so resetting to "default" clears a previous pin (the
  // backend normalizes null/'' to "no override").
  if (!options.scriptOnlyJob) {
    updates.model = values.model.trim() || null
    updates.provider = values.provider.trim() || null
  }
```

模型覆盖用 `${providerSlug}:${model}` 编码,解码时**只切第一个冒号**,因为 openrouter 的 model id
自己带冒号(`anthropic/claude-sonnet-4:beta`)。

### 4.9 artifacts:没有后端端点的"页面"

`collectArtifactsForSession` 从三处挖:markdown 图片/链接、裸 URL/路径正则、
**工具调用入参 JSON 的递归展开**(键名命中 `path|file|url|image|artifact|output|download|result|target` 才收)。

`apps/desktop/src/app/artifacts/artifact-utils.ts:61 @ 863e313`

```
function looksLikeArtifact(value: string): boolean {
  if (/^(?:https?:\/\/|data:image\/)/.test(value)) {
    return true
  }

  if (looksLikePathOrUrl(value) && (IMAGE_EXT_RE.test(value) || FILE_EXT_RE.test(value))) {
    return true
  }

  return value.startsWith('/') && value.includes('.')
}
```

代价直接写在刷新函数里:一次刷新 = 1 次会话列表 + **最多 30 次** `getSessionMessages`,
用 `Promise.allSettled` 容忍部分失败。这是一个"用客户端算力换后端零改动"的取舍,值得记住。

### 4.10 通知栈:为什么必须 portal 到 body

`apps/desktop/src/components/notifications.tsx:99 @ 863e313`

```
// Primary stack: top-center, collapsed to the latest toast with a "+N more"
// expander + clear-all — the noisy/important surface (errors, warnings,
// action toasts). Without the portal it lives inside the React root subtree,
// which any body-level dialog/overlay portal paints over — so a toast fired
// while a dialog is open was invisible.
```

两个栈的分工:顶部居中(默认)= 吵闹/重要,折叠 + "+N more" + 清空;右下 = 环境确认,全展开、无 chrome。

### 4.11 引导:API-key 目录是"策展 + 动态扩展"

curated 6 项(Fireworks / OpenRouter / OpenAI / Gemini / xAI / 本地端点)固定置顶,
再从后端 model options 里把所有 `auth_type === 'api_key'` 且有 `key_env` 的 provider 追加、按名排序。

`apps/desktop/src/components/onboarding/index.tsx:146 @ 863e313`

```
    for (const row of rows) {
      // Only api_key providers can be activated with a pasted key. Skip OAuth /
      // external / managed flows and anything missing an env var to write to.
      if (row.auth_type && row.auth_type !== 'api_key') {
        continue
      }
```

`providers.tsx` 的 `PROVIDER_DISPLAY` 还兼了**改名**职责,其中一条把产品限制写进了标题本身:
`'claude-code': { order: 6, title: 'Anthropic OAuth: Required Extra Usage Credits to Use Subscription' }`。

### 4.12 `styles.css`(2,266 行)是怎么组织的

按出现顺序:Tailwind/插件/KaTeX/codicon 导入 → 全局 reduced-motion 一刀切 → 4 个 `@font-face` →
`@theme inline`(第 60 行起,Tailwind v4 的令牌桥)→ `@layer base`(第 135 行起,含 §2.2 的 z 阶梯)→
引用/`.ref` 配色 → hover-reveal 抑制 → 焦点环全局清零 → 输入框共享 chrome →
`@layer components` → 会话 prose 排版与 RTL/bidi → composer 与 dock → 代码卡片/diff/shiki →
消息动作条与 reaction → 宠物蛋动画(第 2,008 行起)。

**它不受引用校验器保护**(`.css` 不在扩展名白名单上),所以本底稿对它的断言一律配 `verify` 命令,
或落在读取它的 `.ts/.tsx` 上。它的唯一 import 点是 `apps/desktop/src/main.tsx:1`。

---

## 5. 文档与代码的出入

### ▲1 —— DESIGN.md 说 cron / profiles 走 `OverlaySplitLayout`,实际它们走 `Panel`

`apps/desktop/DESIGN.md:171 @ 863e313`

> - **Master/detail overlays:** `OverlaySplitLayout` + `OverlaySidebar` /
>   `OverlayMain`. Cron, profiles, etc. ride this — don't rebuild a titlebar
>   shell.

这条 bullet 在 `## Layout` 标题之下,包含三个断言:(a) 主从覆盖层用 `OverlaySplitLayout`;
(b) **cron、profiles 就是这么做的**;(c) 别自己重画 titlebar 外壳。

(b) **与代码矛盾**。`OverlaySplitLayout` 全仓只有两个使用方,cron 与 profiles 都不在其中;
它俩用的是 `apps/desktop/src/app/overlays/panel.tsx` 那一套。

`apps/desktop/src/app/cron/index.tsx:56 @ 863e313`

```
import {
  Panel,
  PanelAction,
  PanelAddButton,
  PanelBlock,
  PanelBody,
  PanelDetail,
  PanelEmpty,
  PanelHeader,
  PanelList,
  PanelListRow,
  type PanelMenuItem,
  PanelMeta,
  PanelPill,
  type PanelPillTone,
  PanelSectionLabel
} from '../overlays/panel'
```

```verify
cd /home/user/hermes-agent/apps/desktop/src && \
  grep -rl "overlays/overlay-split-layout'" --include=*.tsx . | sort
# -> ./app/command-center/index.tsx  ./app/settings/index.tsx    (cron / profiles 均不在其中)
grep -l "overlays/panel'" /home/user/hermes-agent/apps/desktop/src/app/cron/index.tsx \
  /home/user/hermes-agent/apps/desktop/src/app/profiles/index.tsx
```

(a) 对 settings / command-center 成立,(c) 是建议 —— 所以 ▲ 只钉在第二句。
**影响**:一个照文档办事的贡献者会把新覆盖层建在错误的基元上,而两套基元的行距、边框策略、
窄屏塌陷阈值都不同(`Panel` 无边框密集行 vs `OverlaySplitLayout` 导轨+主区)。

### ▲2 —— DESIGN.md 说路由覆盖层不得用 ad-hoc z-index 字面量,而所有路由覆盖层的根就是 `z-50`

`apps/desktop/DESIGN.md:213 @ 863e313`

> - Respect `AppShell` overlay ownership. Persistent terminal/content layers,
>   route overlays, dialogs, and boot surfaces must not compete through ad-hoc
>   z-index literals. Pick a rung of the ladder in `styles.css` instead —

整段接着列举了阶梯的各个 rung,并以一句豁免收尾:"Plain `z-10`/`z-20` are still right for stacking
*within* one component."

四个断言里,dialogs(`--z-modal`)、boot surfaces(`--z-connecting`/`--z-onboarding`/`--z-setup`/`--z-crash`)
都成立;**route overlays 不成立**——七个路由覆盖层共用的根 `OverlayView` 硬编码 `z-50`,
既不是阶梯 rung,也不落在 `z-10`/`z-20` 的豁免里:

`apps/desktop/src/app/overlays/overlay-view.tsx:66 @ 863e313`

```
    <div
      className={cn(
        'fixed inset-0 z-50 bg-black/22 backdrop-blur-[0.125rem]',
        // Equidistant inset on every side. The top value is driven by the
        // titlebar height so the card clears the OS traffic-lights vertically;
        // since the card top already sits below them, the left needs no extra
        // inset — keeping all sides equal so the card is ~full-width at any size.
        'p-[calc(var(--titlebar-height)+0.625rem)]',
        'sm:p-[calc(var(--titlebar-height)+0.875rem)]'
      )}
```

同一片里还有两处同形:`apps/desktop/src/components/find-bar.tsx:162` 的 `z-50`,
`apps/desktop/src/components/pet/floating-pet.tsx:446` 的 `zIndex: 60`。

```verify
cd /home/user/hermes-agent/apps/desktop/src && \
  grep -rn "z-50\|zIndex: 60" app/overlays/overlay-view.tsx components/find-bar.tsx components/pet/floating-pet.tsx
```

**这不是纯洁癖**:`z-50` < `--z-modal-backdrop: 120`,意味着"路由覆盖层永远在 Radix 对话框之下"
这个实际正确的层序,是靠一个**没有名字的数字**维持的。任何人把 `OverlayView` 改成 `z-[130]`
都不会触发任何检查,而所有嵌套对话框会瞬间被盖住。

**搜索面**:`apps/desktop/src/` 下 `*.tsx`,匹配 `z-50` 与 `zIndex: 60` 两个字面量;
只在本片三个文件里核对,不声称全仓只有这三处。

### ◎1 —— DESIGN.md 的路由覆盖层清单少列了 webhooks

`apps/desktop/DESIGN.md:53 @ 863e313`

> - **Route overlays are short tasks.** Settings, Command Center, Cron, Profiles,
>   Agents, and Starmap render as `OverlayView` cards and return to the previous
>   route on close. Model/session pickers and dialogs layer above the current
>   surface; they are not navigation stacks.

列了 6 个,`OVERLAY_VIEWS` 里是 **7** 个 —— 少了 `webhooks`(见 §2.1 的逐字块)。
字面所述的六个全部为真,只是不完整,按记号约定这是 **◎ 而非 ▲**。

### ◎2 —— pets.md 只把"向光标缩放"记在弹出窗名下,窗内也是这么做的

`website/docs/user-guide/features/pets.md:147 @ 863e313`

> ### Alt+wheel resizing
>
> Hold **Alt** and scroll the mouse wheel over the pet to resize it in place —
> in the app window and on the popped-out overlay alike. The overlay zooms
> toward the cursor position and the resulting scale is persisted, so it
> survives restarts and stays in sync with the in-app pet.

"in the app window and on the popped-out overlay alike" 为真;"The overlay zooms toward the cursor
position" 也为真。但窗内的宠物**同样**向光标缩放:

`apps/desktop/src/components/pet/floating-pet.tsx:376 @ 863e313`

```
  const onScale = useCallback(
    (next: number, { clientX, clientY, ratio }: PetZoomAnchor) => {
      setPetScale(requestGateway, next)
      setPosition(prev => {
        const at = clampPoint(
          clientX - (clientX - prev.x) * ratio,
          clientY - (clientY - prev.y) * ratio,
          (info.frameW ?? 192) * next,
          (info.frameH ?? 208) * next
        )
```

字面无误、只是保守,记 ◎。

### ◇1 —— 漫游的"覆盖层平台"行为无文档

pets.md 的 Roaming 一节准确描述了"仅在窗内 / 活跃 / agent 空闲时漫游",但没有提:
**全屏路由覆盖层打开时,宠物会改为沿覆盖层卡片底边巡逻**(§4.4)。这是代码有、文档无。

### ◇2 —— 唤醒指示窗(`?win=wake`)在桌面文档里没有条目

`apps/desktop/README.md` / `AGENTS.md` / `DESIGN.md` 三份文档里没有 `wake` 窗口的任何描述。
**搜索面**:`grep -rn -i "wake" apps/desktop/*.md`,零命中;`website/docs` 里 `/wake` 只作为
CLI-only 斜杠命令出现在 `website/docs/reference/slash-commands.md:288`,与这个桌面窗口无关联说明。

```verify
grep -rn -i "wake" /home/user/hermes-agent/apps/desktop/README.md \
  /home/user/hermes-agent/apps/desktop/AGENTS.md /home/user/hermes-agent/apps/desktop/DESIGN.md ; echo "rc=$?"
# 无输出、rc=1(grep 无命中)
```

---

## 6. 缺陷(■)

### ■1 —— `profile.switch.10…18`(⌘⌥1…⌘⌥9)会被"第 10…18 个 tab"静默劫持

注释只声称 ⌘1…⌘9 会先尝试切 tab,但循环跑满 `PROFILE_SLOT_COUNT = 18`:

`apps/desktop/src/app/hooks/use-keybinds.ts:118 @ 863e313`

```
  for (let slot = 1; slot <= PROFILE_SLOT_COUNT; slot += 1) {
    // ⌘1…⌘9 switch the FOCUSED zone's tab when it's a real tab strip; only a
    // single-pane (or unfocused) layout falls through to the profile switch.
    profileSwitchHandlers[`profile.switch.${slot}`] = () => {
      const pane = activateTreeTabSlot(slot)

      if (pane) {
        leavePageForWorkspaceChat(pane)
      } else {
        switchProfileToSlot(slot)
      }
    }
  }
```

而 `activateTreeTabSlot` 对 slot 不设 9 的上限,只要该 zone 的可见 tab 数 ≥ slot 就命中:

`apps/desktop/src/components/pane-shell/tree/store.ts:582 @ 863e313`

```
export function activateTreeTabSlot(slot: number): null | string {
  const group = tabTargetGroup(candidate => shownPanesInGroup(candidate).length >= 2)
  const panes = group ? shownPanesInGroup(group) : []

  if (!group || slot < 1 || slot > panes.length) {
    return null
  }

  activateTreePane(group.id, panes[slot - 1])

  return panes[slot - 1]
}
```

**现象**:某个 zone 摊开 10 个以上 tab 时,`⌘⌥1`(= `profile.switch.10`,默认组合 `mod+alt+1`,
见 `apps/desktop/src/lib/keybinds/actions.ts:36` 的 `comboForSlot`)会激活第 10 个 tab,
而不是切到第 10 个 profile —— 且没有任何反馈说明它没切 profile。
严重性低(要 ≥10 个 tab),但它是**注释与代码不一致**导致的:注释说 ⌘1…⌘9,代码是 1…18。

### ■2 —— `ApiKeyForm` 的初值不防空目录,而它自己的 effect 明说目录可能变空

初值直接取 `options[0]`,没有空数组保护;类型标注为 `ApiKeyOption`(非 optional):

`apps/desktop/src/components/onboarding/index.tsx:556 @ 863e313`

```
  const [option, setOption] = useState<ApiKeyOption>(() => options.find(o => o.envKey === initialEnvKey) ?? options[0])
```

紧接着的 effect 却**显式**处理了空目录:

`apps/desktop/src/components/onboarding/index.tsx:564 @ 863e313`

```
  // `options` can change at runtime when callers filter the catalog (e.g. the
  // Providers page wiring its search into this grid). Keep the selection valid
  // by snapping back to the first remaining option when the current one drops.
  useEffect(() => {
    if (options.length > 0 && !options.some(o => o.envKey === option.envKey)) {
      setOption(options[0])
      setValue('')
      setLocalKey('')
      setError(null)
    }
  }, [option.envKey, options])
```

若 `options` 为空,`option` 为 `undefined`,而首渲染就会读 `option.envKey`
(`apps/desktop/src/components/onboarding/index.tsx:591` 的 `const isLocal = option.envKey === 'OPENAI_BASE_URL'`)
→ TypeError,整个引导覆盖层被 ErrorBoundary 接住变成崩溃页。

**当前不可触发**,因为唯一调用方(引导的 `Picker`)传的目录必然含 6 条 curated 项。
注释里假设的那个调用方("the Providers page wiring its search into this grid")在基线里**不存在**:

```verify
cd /home/user/hermes-agent/apps/desktop/src && grep -rn "ApiKeyForm" --include=*.tsx --include=*.ts .
# -> 只有 components/onboarding/index.tsx 的定义(:533)与自用(:447),
#    以及 app/settings/model-settings.tsx:209 的一句注释(非调用)
```

**搜索面**:`apps/desktop/src/` 全目录、`*.ts`/`*.tsx`,按标识符 `ApiKeyForm` 匹配,不排除测试。
定级为**潜伏缺陷**:注释已经把未来的调用形态写出来了,而初值路径没跟上。

### ■3 —— 蛋精灵的模块级 sheet 缓存一旦失败就永久毒化,且是未处理 rejection

`apps/desktop/src/components/pet/pixel-egg-sprite.tsx:60 @ 863e313`

```
function loadSheet(): Promise<HTMLImageElement> {
  if (_sheet?.complete) {
    return Promise.resolve(_sheet)
  }

  if (!_sheetLoading) {
    _sheetLoading = new Promise((resolve, reject) => {
      const img = new Image()

      img.onload = () => {
        _sheet = img
        resolve(img)
      }

      img.onerror = reject
      img.src = eggSheetUrl
    })
  }

  return _sheetLoading
}
```

`_sheetLoading` 在 reject 后**不会被清空**,所以此后每一个蛋都拿到同一个 rejected promise;
而调用点没有 `.catch`:

`apps/desktop/src/components/pet/pixel-egg-sprite.tsx:130 @ 863e313`

```
    let sheet: HTMLImageElement | null = null
    void loadSheet().then(img => {
      sheet = img
    })
```

**现象**:一次加载失败(离线/资源 404)之后,草稿网格的四个孵化位与孵化预览页会永远画不出蛋
(RAF 每帧因 `if (!sheet) return` 空转),并且每个挂载都产生一条 unhandled promise rejection。
纯装饰性,不影响生成流程本身,记为低危 ■。

### ■4(轻)—— `boot-failure-reauth.ts` 有一段错位的函数注释

`apps/desktop/src/components/boot-failure-reauth.ts:63 @ 863e313`

```
// A remote, gated (oauth-bucket) gateway is a remote-reauth boot failure when the
// session isn't connected OR the boot error is auth-shaped (connected-but-expired
// — see isRemoteReauthError). Only re-establishing the remote session fixes it;
// the local Retry/Repair buttons can't. 'cloud' counts as remote (it resolves to
// a remote oauth backend), so a lapsed cloud session is the same failure.
export function sshFailureMessage(
```

这段注释描述的是 `isRemoteReauthFailure`(定义在 `:121`),却挂在 `sshFailureMessage` 头上,
而后者干的是"把 SSH 错误文本映射成本地化措辞"。读注释找函数会找错人。文档性缺陷,零运行时影响。

---

## 7. 测试(行为规格)

环境:主线在基线之外准备的 `git archive` 副本 `/home/user/r10b-ts/hermes-agent/apps/desktop`,
`vitest --project ui`(jsdom)。**未安装任何新包。**

命令(可复现):

```verify
cd /home/user/r10b-ts/hermes-agent/apps/desktop && npx vitest run --project ui \
  src/app/artifacts/index.test.ts src/app/cron/blueprints.test.ts src/app/cron/cron-job-model.test.ts \
  src/app/messaging/index.test.tsx src/app/overlays/panel.test.tsx src/components/onboarding/index.test.tsx \
  src/components/pet/pet-sprite.test.tsx src/components/pet/roam-behavior.test.ts \
  src/components/pet/roam-geometry.test.ts src/components/pet/use-pet-roam.test.tsx \
  src/app/routes.test.ts src/app/routes.workspace-reveal.test.ts \
  src/components/boot-failure-overlay.test.tsx src/components/boot-failure-reauth.test.ts \
  src/components/desktop-install-overlay.test.tsx src/components/find-bar.test.tsx \
  src/components/gateway-connecting-overlay.test.tsx src/components/idle-mount.test.tsx \
  src/components/language-switcher.test.tsx src/components/prompt-overlays.test.tsx
```

结果:

```text
 Test Files  20 passed (20)
      Tests  179 passed (179)
   Duration  77.65s
```

**passed = 179 / failed = 0 / skipped = 0。**

**零执行点名**:无。这 20 个文件里没有 `describe.skip` / `it.skip` / `test.skip` / `.todo` /
条件跳过,机械核对:

```verify
cd /home/user/hermes-agent/apps/desktop/src && grep -rn "describe\.skip\|it\.skip\|test\.skip\|\.todo\|skipIf" \
  app/artifacts/index.test.ts app/cron/*.test.* app/messaging/index.test.tsx app/overlays/panel.test.tsx \
  components/onboarding/index.test.tsx components/pet/*.test.* app/routes*.test.ts \
  components/boot-failure*.test.* components/desktop-install-overlay.test.tsx components/find-bar.test.tsx \
  components/gateway-connecting-overlay.test.tsx components/idle-mount.test.tsx \
  components/language-switcher.test.tsx components/prompt-overlays.test.tsx ; echo "rc=$?"
# 无输出、rc=1
```

**这些测试钉住的行为(即作者承诺的规格)**,挑本片最关键的几条:

- `apps/desktop/src/components/gateway-connecting-overlay.test.tsx:15 @ 863e313`

```
// hatch — BootFailureOverlay, which has "Use local gateway" / "Sign in" /
```

该文件把 connecting 与 boot-failure **同时挂载**,逐场景断言"同一时刻只有一个占屏"——
正是 §2.2 那三条互斥关系的行为规格。

- `apps/desktop/src/components/pet/roam-behavior.test.ts`、`roam-geometry.test.ts`:
  漫游的决策层与几何层是纯函数,所以"节奏"和"哪儿能站"都是可回归的规格,不必起 Electron。
  这是三层切分带来的直接收益。

- `apps/desktop/src/app/cron/cron-job-model.test.ts`:script-only 任务的校验与载荷构造被单独钉住,
  说明"script-only 不写 model/provider"是承诺行为而非实现细节。

**未覆盖的空白(如实说)**:上面那 20 个测试文件对应的是本片 86 个文件里的一部分,
**片内几个最长的文件反而没有伴生测试**:`app/cron/index.tsx`(1,225 行)、
`app/webhooks/index.tsx`(609 行)、`app/pet-overlay/pet-overlay-app.tsx`(481 行)、
`app/updates-overlay.tsx`(470 行)、`app/master-detail.tsx`(406 行)、
`components/model-picker.tsx`(351 行)、`components/first-run-remote-form.tsx`(346 行)、
`components/notifications.tsx`(301 行)。
(`app/messaging/index.tsx` 933 行**有**测试,已计入上面的 20 个。)
弹出窗那 481 行(点击穿透、拖拽、双击判定)尤其难测——它全靠真实 OS 窗口与 `elementFromPoint`。

```verify
cd /home/user/hermes-agent/apps/desktop/src && for f in app/cron/index.tsx app/messaging/index.tsx \
  app/webhooks/index.tsx app/updates-overlay.tsx app/pet-overlay/pet-overlay-app.tsx \
  components/notifications.tsx components/model-picker.tsx components/first-run-remote-form.tsx \
  app/master-detail.tsx; do
  b="${f%.tsx}"
  if [ -f "$b.test.tsx" ] || [ -f "$b.test.ts" ]; then echo "HAS test: $f"; else echo "NO  test: $f"; fi
done
# -> 只有 app/messaging/index.tsx 是 HAS,其余 8 个都是 NO
```

---

## 8. 判据自查

| # | 判据 | 自评 |
|---|---|---|
| 1 点名到位 | 每个文件全路径 + 一句话角色 | **达标**。§0 分 12 组共 86 条,组内逐个列全路径,合计与清单一致(7+7+4+9+17+4+11+11+2+3+9+2 = 86)。 |
| 2 接缝穷举 | 逐项列全 + 机械枚举命令 + 条数 | **基本达标(约 9 成)**。已穷举:路由表 11、AppView 12、OVERLAY_VIEWS 7、routes.ts 导出 21、覆盖层触发表 19 行、z 阶梯 12、keybind action 71(44 逐个列出 + 两组各 N)、panel.tsx 导出 17 + 使用方 8、overlay-split-layout 导出 7 + 使用方 2、pet-overlay 控制消息 7 + 桥方法 9 + state 载荷 6、宠物动作面 10、四张面板页后端调用 11/5/5/0、hooks 导出 11。**未穷举**:`app/master-detail.tsx` 与 `styles.css` 的导出/选择器面只做了分区概述,没有逐项列全(前者 13 个导出已在 §0.1 概括但未逐条列;后者 2,266 行的选择器面本轮判定为不值得逐条)。这两处是缺口,如实记下。 |
| 3 端到端链 | 逐跳带锚点 | **达标**。§3 五跳:`use-gateway-boot.ts:325` → `store/boot.ts:83` → `gateway-connecting-overlay.tsx:66` 让屏 → `boot-failure-overlay.tsx:62` 上屏 → `boot-failure-reauth.ts:121` 分支 → `boot-failure-overlay.tsx:251` 三套动作 → 6 条 IPC 各带锚点。 |
| 4 逐字取证 | ≥2 个围栏块是逐字源码 | **达标**。无语言标记的 ``` 围栏(= 逐字源码摘录)共 **46** 个,**每一个前面都紧邻一条 `路径:行号 @ 863e313` 锚点**(机械核对见下),分布在 routes / overlays / boot / pet / cron / artifacts / notifications / onboarding / keybinds / main.tsx / pane-shell tree store;另有 18 个 ```` ```verify ```` 与 2 个 ```` ```text ```` 的声明式非源码块。 |
| 5 记号 | ≥1 条带锚点 | **达标**。▲2、◎2、◇2、■4,共 10 条,每条带锚点与代码/文档原文。 |

围栏块与锚点配对的机械核对(0 = 没有任何一个逐字块是"块后放锚点"或干脆无锚点):

```verify
cd /home/user/hermes-study && python3 - <<'PY'
import re
FENCE = chr(96) * 3
lines = open('notes/r10b-raw-shell-overlays.md', encoding='utf-8').read().split('\n')
anchor = re.compile(r'`[^`]*?\.(?:ts|tsx|md|css)(?::\d+(?:-\d+)?)?\s*@\s*863e313`')
inb = False; plain = 0; bad = 0
for i, ln in enumerate(lines):
    if not ln.startswith(FENCE):
        continue
    if inb:
        inb = False; continue
    inb = True
    if ln[3:].strip():
        continue
    plain += 1
    j = i - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    if j < 0 or not anchor.search(lines[j]):
        bad += 1
print('plain fences =', plain, ' without preceding anchor =', bad)
PY
# -> plain fences = 46  without preceding anchor = 0
```

---

## 9. 移交项

| id | 锚点 + 摘录 | 一句话现象 |
|---|---|---|
| H-R10B-J-a | `apps/desktop/src/app/hooks/use-keybinds.ts:118`:`for (let slot = 1; slot <= PROFILE_SLOT_COUNT; slot += 1) {` | 循环跑满 18 而注释只说 ⌘1…⌘9,导致 profile 槽 10–18 在 ≥10 个 tab 的 zone 里被 tab 激活静默劫持(■1)。 |
| H-R10B-J-b | `apps/desktop/src/components/onboarding/index.tsx:556`:`const [option, setOption] = useState<ApiKeyOption>(() => options.find(o => o.envKey === initialEnvKey) ?? options[0])` | 空 `options` 时 `option` 为 undefined,首渲染读 `option.envKey` 会抛;同文件 `:567` 的 effect 已显式假设目录可能变空(■2)。 |
| H-R10B-J-c | `apps/desktop/src/components/pet/pixel-egg-sprite.tsx:131`:`void loadSheet().then(img => {` | 模块级 `_sheetLoading` 失败后不清空且无 catch,一次加载失败让所有蛋永久不渲染并产生未处理 rejection(■3)。 |
| H-R10B-J-d | `apps/desktop/src/app/overlays/overlay-view.tsx:68`:`'fixed inset-0 z-50 bg-black/22 backdrop-blur-[0.125rem]',` | 七个路由覆盖层共用的根用裸 `z-50`,与 DESIGN.md:213 的"路由覆盖层不得用 ad-hoc z 字面量"直接矛盾(▲2)。 |
| H-R10B-J-e | `apps/desktop/src/components/boot-failure-reauth.ts:63`:`// A remote, gated (oauth-bucket) gateway is a remote-reauth boot failure when the` | 这段注释描述的是 `:121` 的 `isRemoteReauthFailure`,却挂在 `sshFailureMessage` 头上(■4)。 |
| H-R10B-J-f | `apps/desktop/DESIGN.md:171`:`- **Master/detail overlays:** `OverlaySplitLayout` + `OverlaySidebar` /` | 文档点名 cron / profiles 走 `OverlaySplitLayout`,实测两者都走 `overlays/panel.tsx`,该基元全仓只有 settings 与 command-center 两个使用方(▲1)。 |
| H-R10B-J-g | `apps/desktop/src/components/pet/roam-geometry.ts:125`:`export function overlayLedge(petW: number): Ledge {` | 该函数按 `OverlayView` 的等距 inset 公式**反推**覆盖层底边而不测量 DOM,与 `overlay-view.tsx:73` 的 `p-[calc(var(--titlebar-height)+0.625rem)]` 靠注释约定耦合;改一边不会让另一边报错。 |
| H-R10B-J-h | `apps/desktop/src/app/artifacts/index.tsx:132`:`const sessions = (await listAllProfileSessions(30, 1)).sessions` | Artifacts 页没有后端端点,每次刷新拉最多 30 个会话的全部消息在前端现挖产物;`r` 热键可无节流重复触发。成本模型值得下一轮量一量。 |
| H-R10B-J-i | 本片 8 个大文件无伴生测试(见 §7 末尾的 `verify` 命令) | `app/cron/index.tsx`(1,225)、`app/webhooks/index.tsx`(609)、`app/pet-overlay/pet-overlay-app.tsx`(481)、`app/updates-overlay.tsx`(470)、`app/master-detail.tsx`(406)、`components/model-picker.tsx`(351)、`components/first-run-remote-form.tsx`(346)、`components/notifications.tsx`(301)零测试文件;`app/messaging/index.tsx`(933)**有**测试。 |

---

## 10. 本片成本自报

```text
片号            : J
层              : L2
文件数 / 行数   : 86 / 18,766
实际打开的文件数: 71          (86 个片内文件中真读过内容的;另读了 8 个片外文件取证:
                              app/contrib/wiring.tsx、app/shell/hooks/use-overlay-routing.ts、
                              store/boot.ts、store/pet-overlay.ts、store/pet.ts、global.d.ts、
                              lib/keybinds/actions.ts、components/pane-shell/tree/store.ts、
                              app/gateway/hooks/use-gateway-boot.ts;
                              未逐行打开的 15 个:styles.css(只读了 3 个区段 + 结构 grep)、
                              两个组件 css(只读结构 grep)、以及 cron/messaging/webhooks/artifacts
                              四个大文件的部分尾段、model-picker.tsx 的 ModelResults 之后、
                              first-run-remote-form.tsx 的表单 JSX 之后)
实际读过的行数  : ~11,500     (估法:完整读过的 71 个文件按其真实行数累加约 9,900;
                              4 个大面板页各读 40–100% 不等约 1,400;styles.css 只读约 120 行;
                              两个组件 css 各读结构约 20 行)
底稿字节数      : (主线自测)
主观耗费        : 中偏高。瓶颈在**文件多且异质**——86 个文件横跨路由、启动态机、
                  canvas 动画、Electron 多窗口、四张 CRUD 面板与一张 2,266 行样式表,
                  没有一条主线能把它们串起来,判据 1 的"逐个点名"本身就要 12 组分类;
                  其次是**跨文件追链**:覆盖层触发条件散在 wiring.tsx / use-overlay-routing.ts /
                  各组件自身三处,穷举触发表需要来回对照。单文件长度不是瓶颈
                  (最长的 cron/index.tsx 1,225 行结构清晰)。
```
