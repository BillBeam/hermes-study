# r10-web-dashboard —— dashboard 前端(React + Vite):131 个文件的结构级测绘

> 溯源约定:凡对 hermes-agent 的断言,锚点写作 `路径:行号 @ 863e313`,**单独成行、置于代码块之前**。
> ` ``` ` 围栏块一律是逐字源码摘录(整块逐行比对);` ```verify ` / ` ```text ` 是声明式非源码。
> 本片范围 = `/home/user/hermes-study/data/r10/slices/G.txt` 列出的 **131 个文件 / 49,274 行**。
> 本轮是 **L2 结构级理解**:读接口面、生命周期与协作方式,不逐个读实现体。

---

## §0 交付摘要(先给数)

```text
片名                G · web 仪表盘前端
片内文件            131 个 / 49,274 行
底稿里点名(全路径) 131 个(§2 逐个列全)
接缝穷举
  HTTP 端点         166 条(web/src/lib/api.ts)+ 5 条(api.ts 之外)= 全前端 171 条
  WebSocket 端点    4 条
  路由表            19 条内置路由 + 1 条 `*` 兜底 + 插件动态路由
  侧栏导航表        17 条(嵌入式 chat 开启时 18 条)
  api 客户端方法    166 个
  插件插槽          声明 30 / 实渲染 31 / 文档 28(三者互不相等,见 §7)
  插件 SDK 导出面   6 个顶层能力 + 16 个组件 + 3 个 util + 1 个 hook
  i18n 语言         17 种
  内置主题 / 字体   8 / 14
  profile 作用域前缀 17 条
记号                ■ 4 条、▲ 3 条、◇ 3 条、◎ 1 条
```

---

## §1 这一片是什么

`web/` 是 **hermes dashboard 的浏览器前端**:一个 React 19 + Vite 8 的单页应用(SPA,
single-page application —— 整站只加载一次 HTML,之后由 JavaScript 在客户端切换"页面")。
它编译成静态文件后由 Python 后端(`hermes_cli/web_server.py` + `hermes_cli/web_routers/`,
R8C 已精读)原样吐出;运行时前后端只通过 **HTTP + WebSocket** 说话,没有服务端渲染。

给不熟前端的读者三句话锚定:

- **Vite** = 前端构建工具,开发时起一个带热更新(HMR,改代码不刷新页面就生效)的本地服务器,
  生产时把 TypeScript/JSX 打包成浏览器能跑的 JS。
- **React 组件 / hook** = 组件是一个返回界面描述的函数;`useState` / `useEffect` 之类的
  `useXxx` 函数叫 hook,负责在这个函数里挂状态和副作用。`Context` 是 React 内置的
  "跨层级传值"机制,等价于一个作用域受限的依赖注入容器。
- **PTY** = pseudo-terminal,伪终端。dashboard 的 Chat 页把真实的 `hermes --tui`
  终端程序跑在服务端,通过 WebSocket 把键盘字节和屏幕字节来回搬,浏览器里用 xterm.js 渲染。

这一片的边界很清楚:**它自己不含任何业务逻辑的真身**。所有配置、会话、cron、技能、
MCP、凭据都在 Python 侧;前端是一个**大而薄的控制台**。所以本片的价值集中在三处:
① 后端 API 面到底有多大(端点表就是那张地图);② 认证/多 profile/反向代理前缀
这三条横切关注点在客户端是怎么落地的;③ 危险动作在界面上到底可不可达(§6)。

---

## §2 文件清单(131 个,逐个全路径)

分 11 组。组是为了好读,**组内逐个列全路径**,不省略。

### 2.1 入口与外壳(3)

| 全路径 | 行 | 角色 |
|---|---|---|
| `web/index.html` | 16 | Vite 的 HTML 模板;生产环境由 Python 后端二次加工,注入 `window.__HERMES_SESSION_TOKEN__` / `__HERMES_BASE_PATH__` / `__HERMES_AUTH_REQUIRED__` 三个全局量 |
| `web/src/main.tsx` | 25 | React 挂载点;先 `exposePluginSDK()` 再渲染,Provider 嵌套顺序 Router → I18n → Theme → SystemActions → App |
| `web/src/App.tsx` | 1388 | 应用外壳:路由表、侧栏导航、顶栏、移动端抽屉、插件路由合并、常驻 Chat 宿主 |

### 2.2 页面(19)

| 全路径 | 行 | 一句话职责 |
|---|---|---|
| `web/src/pages/SessionsPage.tsx` | 2200 | 会话列表/搜索/重命名/导出/导入/批量删除/按天清理 + 会话消息预览 |
| `web/src/pages/ChatPage.tsx` | 1643 | 嵌入式终端:xterm.js ↔ `/api/pty` WebSocket,承载 `hermes --tui` 子进程 |
| `web/src/pages/SkillsPage.tsx` | 1634 | 技能开关、SKILL.md 编辑、技能 hub 搜索/预览/扫描/安装/更新 |
| `web/src/pages/SystemPage.tsx` | 1540 | 运维台:状态、系统指标、凭据池、hooks、检查点、curator、portal、**备份/恢复**、诊断、网关与自更新 |
| `web/src/pages/ChannelsPage.tsx` | 1446 | 消息平台(Telegram/WhatsApp/…)配置、连通性测试、引导式 onboarding |
| `web/src/pages/ProfilesPage.tsx` | 1425 | profile 增删改、激活、模型指派、描述与 soul 文本 |
| `web/src/pages/ModelsPage.tsx` | 1367 | 主模型/辅助模型/MoA 槽位的选择与保存 + 模型用量分析 |
| `web/src/pages/CronPage.tsx` | 1135 | 定时任务:列表(可跨 profile)、创建/编辑、暂停/恢复/**立即触发**/删除、蓝图实例化 |
| `web/src/pages/PluginsPage.tsx` | 1124 | dashboard 插件与 agent 插件的安装/启停/可见性 + **记忆 provider 选择与依赖安装** |
| `web/src/pages/EnvPage.tsx` | 1114 | 环境变量(API key)增删改与"显形"(reveal) |
| `web/src/pages/McpPage.tsx` | 902 | MCP 服务器增删、启停、连通性测试、OAuth 授权、目录安装 |
| `web/src/pages/ProfileBuilderPage.tsx` | 833 | `/profiles/new` 的向导式建档页(选模型、选技能) |
| `web/src/pages/ConfigPage.tsx` | 679 | 由后端 schema 驱动的配置编辑器 + 原始 YAML 编辑 |
| `web/src/pages/WebhooksPage.tsx` | 613 | webhook 订阅的增删启停(改完需重启网关) |
| `web/src/pages/AnalyticsPage.tsx` | 604 | token 用量与技能命中的图表页(可被 `analytics.enabled` 关掉) |
| `web/src/pages/FilesPage.tsx` | 525 | HERMES_HOME 文件管理器:列目录、读文件、上传、建目录、删除 |
| `web/src/pages/PairingPage.tsx` | 273 | 平台配对请求的批准/撤销/清空待批 |
| `web/src/pages/LogsPage.tsx` | 237 | 日志尾随 + 级别/组件过滤 |
| `web/src/pages/DocsPage.tsx` | 69 | 把官网文档站塞进一个 `<iframe>`(跨源、带 sandbox) |

### 2.3 组件(26)

| 全路径 | 行 | 角色 |
|---|---|---|
| `web/src/components/ModelPickerDialog.tsx` | 680 | 两栏(provider × model)模糊搜索选择器,Chat 侧栏与 Models 页共用 |
| `web/src/components/HermesConsoleModal.tsx` | 537 | "打开控制台"弹窗:另一个 xterm,接 `/api/console` WebSocket |
| `web/src/components/ChatSidebar.tsx` | 535 | Chat 页右侧结构化事件面板;两条 socket(JSON-RPC 探针 + `/api/events` 订阅) |
| `web/src/components/ToolsetConfigDrawer.tsx` | 460 | 工具集(toolset)的 provider 选择、env 填写、post-setup 执行抽屉 |
| `web/src/components/OAuthLoginModal.tsx` | 395 | 模型 provider 的 OAuth 登录弹窗(开窗、轮询、手工贴 code) |
| `web/src/components/Markdown.tsx` | 383 | 轻量 markdown 渲染器,面向 LLM 输出,非完整 CommonMark |
| `web/src/components/ThemeSwitcher.tsx` | 358 | 主题 + 字体选择器(桌面下拉 / 移动端 BottomSheet) |
| `web/src/components/OAuthProvidersCard.tsx` | 287 | 已连接 OAuth provider 卡片:状态、断开、CLI 等价命令 |
| `web/src/components/ScheduleBuilder.tsx` | 273 | cron 调度的可视化构造器(模式 × 间隔 × 星期) |
| `web/src/components/ChatSessionList.tsx` | 260 | Chat 页左侧会话切换列表,选中即 `/chat?resume=<id>` |
| `web/src/components/AutomationBlueprints.tsx` | 225 | 参数化自动化蓝图选择与实例化(落成 cron job) |
| `web/src/components/SkillEditorDialog.tsx` | 215 | 新建/编辑 SKILL.md 的对话框 |
| `web/src/components/AutoField.tsx` | 206 | 由 JSON schema 片段推断控件类型(Switch / Select / Input)的通用字段 |
| `web/src/components/LanguageSwitcher.tsx` | 185 | 语言选择器,显示各语言的自称名(endonym) |
| `web/src/components/SlashPopover.tsx` | 171 | Chat 输入框上方的斜杠命令自动补全浮层 |
| `web/src/components/AuthWidget.tsx` | 160 | 侧栏"已登录为…"+ 登出;仅在 gated 模式渲染 |
| `web/src/components/ReasoningPicker.tsx` | 125 | 推理强度(reasoning effort)选择,写 `agent.reasoning_effort` |
| `web/src/components/ConfirmDialog.tsx` | 122 | **本地**确认对话框实现(仅 3 处使用,见 §7 ◇-G-02) |
| `web/src/components/ModelInfoCard.tsx` | 112 | 当前模型的上下文窗口/能力徽章卡片 |
| `web/src/components/PlatformsCard.tsx` | 108 | 平台连接状态徽章卡片(纯展示) |
| `web/src/components/ProfileSwitcher.tsx` | 85 | 侧栏顶部的"管理目标 profile"下拉,全站唯一写目标选择器 |
| `web/src/components/SidebarStatusStrip.tsx` | 72 | 侧栏里的网关 + 会话摘要条 |
| `web/src/components/SidebarFooter.tsx` | 41 | 侧栏页脚:版本号 + Nous 外链 |
| `web/src/components/ModelReloadConfirm.tsx` | 40 | 换模型后"要不要整页重载以让新会话生效"的确认 |
| `web/src/components/DeleteConfirmDialog.tsx` | 40 | 删除确认的 i18n 包装(转调设计系统的 ConfirmDialog) |
| `web/src/components/ProfileScopeBanner.tsx` | 30 | 当管理目标 ≠ 本进程 profile 时的全局琥珀色横幅 |

### 2.4 lib · 网络与协议(4)

| 全路径 | 行 | 角色 |
|---|---|---|
| `web/src/lib/api.ts` | 2609 | **唯一的 HTTP 客户端**:`fetchJSON` / `authedFetch` / `buildWsUrl` + 166 个方法的 `api` 对象 |
| `web/src/lib/gatewayClient.ts` | 63 | `/api/ws` 上的 JSON-RPC 客户端(继承 `@hermes/shared` 的 `JsonRpcGatewayClient`) |
| `web/src/lib/dashboard-auth-reload.ts` | 69 | loopback 模式下 session token 轮换后的"只重载一次"守卫 |
| `web/src/lib/chatImagePaste.ts` | 164 | 粘贴/拖入图片 → `POST /api/chat/image-upload`,含 MIME 白名单与 25MB 上限 |

### 2.5 lib · PTY / Chat(7)

| 全路径 | 行 | 角色 |
|---|---|---|
| `web/src/lib/pty-resume-sanitizer.ts` | 128 | 清洗 Ink 两遍虚拟滚动在 resume 时吐出的病态 ANSI 序列(跨帧、CRLF 语义) |
| `web/src/lib/pty-mobile-input.ts` | 136 | 移动端输入法(IME)整行替换的启发式还原为增删键序列 |
| `web/src/lib/pty-reconnect.ts` | 86 | PTY socket 重连状态机与"卡在 CONNECTING"预算 |
| `web/src/lib/pty-resume-loading.ts` | 47 | resume 等待遮罩的显示判据与 30s 硬上限 |
| `web/src/lib/slashExec.ts` | 163 | 斜杠命令流水线:`slash.exec` 失败回落 `command.dispatch` 的五种指令 |
| `web/src/lib/chat-activation.ts` | 17 | "chat 标签页是否曾被激活"的粘滞闩锁,防止未访问就 spawn PTY |
| `web/src/lib/chat-title.ts` | 15 | 会话标题的规范化与从 `session.info` 载荷里取值 |

### 2.6 lib · 纯逻辑与格式(14)

| 全路径 | 行 | 角色 |
|---|---|---|
| `web/src/lib/schedule.ts` | 465 | 调度字符串(时长/间隔/cron/ISO)与结构化 picker 状态的双向转换 |
| `web/src/lib/fuzzy.ts` | 192 | 子序列模糊打分器,给模型/命令 picker 排序 |
| `web/src/lib/cron-job.ts` | 95 | cron 表单状态 ↔ `CronJobMutation` 载荷的映射与列表拆分 |
| `web/src/lib/events-reconnect.ts` | 82 | `/api/events` 的指数退避重连策略(1s→30s,15 次,认证类关闭码不重试) |
| `web/src/lib/mcp-server-create.ts` | 78 | MCP 新建表单草稿 → `McpServerCreate` 载荷 |
| `web/src/lib/mcp-dashboard-oauth.ts` | 66 | MCP OAuth 授权流的开窗 + 轮询编排 |
| `web/src/lib/resolve-page-title.ts` | 57 | 路径 → 页面标题(内置表 + 插件标签回落) |
| `web/src/lib/clipboard.ts` | 56 | 剪贴板写入,非安全上下文回落到隐藏 textarea + execCommand |
| `web/src/lib/session-import.ts` | 46 | 导入 JSON 的形状归一化(裸数组 / `{sessions:[]}` / 单对象) |
| `web/src/lib/reasoning-effort.ts` | 38 | 推理强度选项表与解析(镜像 `hermes_constants.VALID_REASONING_EFFORTS` 加 `none`) |
| `web/src/lib/log-classify.ts` | 36 | 日志行级别判定,优先结构化 token,避免 `errors.log` 被判成 error |
| `web/src/lib/utils.ts` | 35 | `cn()`(clsx + tailwind-merge)与三个字体 class 常量 |
| `web/src/lib/model-search-text.ts` | 28 | 模型搜索的别名扩展(如 `k3` → `kimi-k3`),不改 wire id |
| `web/src/lib/session-refresh.ts` | 26 | 概览轮询发现新会话时是否要重拉分页列表的判据 |

### 2.7 lib · 小常量与工具(4)

| 全路径 | 行 | 角色 |
|---|---|---|
| `web/src/lib/dashboard-modal-shell.ts` | 29 | 弹窗遮罩/面板的共享 class 串(z-index 分层约定) |
| `web/src/lib/dashboard-flags.ts` | 24 | `isDashboardEmbeddedChatEnabled()`——现在恒 `true`,保留为稳定接缝 |
| `web/src/lib/nested.ts` | 23 | `a.b.c` 点路径的 get/set(配置编辑器用) |
| `web/src/lib/model-picker-filter.ts` | 23 | "查到了 provider 但没查到 model"这一种空态的判定 |
| `web/src/lib/format.ts` | 9 | token 数的人读格式化(1M / 128K / 4096) |

> 注:本小节 5 行,与 2.6 的 14 行合计 19 个 `lib/` 纯逻辑文件;加 2.4 的 4 个和 2.5 的 7 个,
> `web/src/lib/` 共 **30** 个非测试文件。

### 2.8 contexts 与 hooks(11)

| 全路径 | 行 | 角色 |
|---|---|---|
| `web/src/contexts/PageHeaderProvider.tsx` | 138 | 页面标题与页头右侧插槽的 Provider(页面用 `usePageHeader` 往里塞节点) |
| `web/src/contexts/ProfileProvider.tsx` | 137 | 管理目标 profile 的唯一真源;把选择同步进 URL `?profile=` 与 api 模块 |
| `web/src/contexts/SystemActions.tsx` | 136 | 长动作(网关重启 / 自更新)的全局进度与日志尾随 Provider |
| `web/src/contexts/page-header-context.ts` | 12 | 上面那个 Provider 的 Context 对象与类型 |
| `web/src/contexts/profile-context.ts` | 19 | profile Context 对象与默认值 |
| `web/src/contexts/system-actions-context.ts` | 18 | 系统动作 Context 对象与 `SystemAction` 联合类型 |
| `web/src/contexts/usePageHeader.ts` | 10 | 取 PageHeader Context,未包裹时抛错 |
| `web/src/contexts/useProfileScope.ts` | 6 | 取 profile Context(有默认值,故不抛错) |
| `web/src/contexts/useSystemActions.ts` | 15 | 取系统动作 Context,未包裹时抛错 |
| `web/src/hooks/useModalBehavior.ts` | 44 | 弹窗通用行为:Esc 关闭、锁 body 滚动、关闭时还焦点 |
| `web/src/hooks/useSidebarStatus.ts` | 27 | 侧栏用的 10s 状态轮询 |

> 拆成 `xxx-context.ts` + `useXxx.ts` + `XxxProvider.tsx` 三个文件是为了满足
> `eslint-plugin-react-refresh` 的 `only-export-components`——同一文件同时导出组件和非组件
> 会让热更新失效(`web/eslint.config.js` 里对此有豁免注释,但目录结构仍按拆分走)。

### 2.9 i18n(21)

翻译目录组。`types.ts` 定义键的形状(651 个叶子字符串键),`en.ts` 是基准,
`context.tsx` 提供 Provider 与 `LOCALE_META`,`define-locale.ts` 允许**部分翻译**并回落英文
(全仓仅 `ar.ts` 用它),`index.ts` 是两行再导出。

| 全路径 | 行 | 角色 |
|---|---|---|
| `web/src/i18n/types.ts` | 857 | `Translations` 接口 + `Locale` 联合类型(17 个) |
| `web/src/i18n/en.ts` | 858 | 英文基准,全量 |
| `web/src/i18n/ga.ts` | 779 | 爱尔兰语 |
| `web/src/i18n/uk.ts` | 772 | 乌克兰语 |
| `web/src/i18n/pt.ts` | 772 | 葡萄牙语 |
| `web/src/i18n/tr.ts` | 771 | 土耳其语 |
| `web/src/i18n/ru.ts` | 771 | 俄语 |
| `web/src/i18n/hu.ts` | 771 | 匈牙利语 |
| `web/src/i18n/fr.ts` | 771 | 法语 |
| `web/src/i18n/es.ts` | 771 | 西班牙语 |
| `web/src/i18n/af.ts` | 771 | 南非荷兰语 |
| `web/src/i18n/zh-hant.ts` | 770 | 繁体中文 |
| `web/src/i18n/ko.ts` | 770 | 韩语 |
| `web/src/i18n/ja.ts` | 770 | 日语 |
| `web/src/i18n/it.ts` | 770 | 意大利语 |
| `web/src/i18n/de.ts` | 770 | 德语 |
| `web/src/i18n/zh.ts` | 766 | 简体中文 |
| `web/src/i18n/ar.ts` | 707 | 阿拉伯语,**唯一**用 `defineLocale` 的部分翻译;RTL |
| `web/src/i18n/context.tsx` | 136 | `I18nProvider` / `useI18n` / `LOCALE_META` / RTL 方向设置 / localStorage 持久化 |
| `web/src/i18n/define-locale.ts` | 46 | 部分翻译的深合并助手 |
| `web/src/i18n/index.ts` | 2 | 再导出 |

### 2.10 plugins(7)与 themes(5)

| 全路径 | 行 | 角色 |
|---|---|---|
| `web/src/plugins/slots.ts` | 200 | 插槽注册表 + `<PluginSlot>` 组件 + `KNOWN_SLOT_NAMES`(30 个) |
| `web/src/plugins/usePlugins.ts` | 192 | 插件发现与加载:拉 manifest → 注入 CSS `<link>` → 注入 JS `<script>`(可选 SRI) |
| `web/src/plugins/registry.ts` | 168 | `exposePluginSDK()`:把 React / 组件 / api / utils 挂到 `window.__HERMES_PLUGIN_SDK__` |
| `web/src/plugins/sdk.d.ts` | 160 | 手写的 SDK 公共类型契约(声明为 spike),含 `sdkVersion` |
| `web/src/plugins/PluginPage.tsx` | 64 | 插件页宿主,用 `useSyncExternalStore` 订阅注册事件避免竞态 |
| `web/src/plugins/types.ts` | 37 | `PluginManifest` / `RegisteredPlugin` 类型(含 `tab.override` / `tab.hidden` / `integrity`) |
| `web/src/plugins/index.ts` | 6 | 再导出 |
| `web/src/themes/context.tsx` | 615 | 主题引擎:CSS 变量批量写入、`customCSS` `<style>` 注入、字体表注入、布局变体、服务端持久化 |
| `web/src/themes/presets.ts` | 240 | 8 个内置主题的完整定义 |
| `web/src/themes/types.ts` | 208 | 主题类型:调色板、层、资产、布局变体、字体 |
| `web/src/themes/fonts.ts` | 160 | 14 个字体选项(3 个系统栈 + 11 个可下载) |
| `web/src/themes/index.ts` | 10 | 再导出 |

### 2.11 构建与工程配置(8)

| 全路径 | 行 | 角色 |
|---|---|---|
| `web/vite.config.ts` | 147 | 别名、dedupe、产物切分组、开发代理、**开发期 session token 抓取插件** |
| `web/package.json` | 54 | 依赖与脚本(`dev`/`build`/`lint`/`typecheck`/`test`/`check`) |
| `web/eslint.config.js` | 36 | flat config;react-hooks v7 的四条规则暂设为 warn 并留了 TODO |
| `web/tsconfig.app.json` | 34 | 应用侧 TS 配置(strict + noUnusedLocals + bundler 解析),include = `src` 与 `../apps/shared/src` |
| `web/tsconfig.node.json` | 26 | 构建脚本侧 TS 配置,include 只有 `vite.config.ts` |
| `web/tsconfig.json` | 7 | solution 风格,`files: []` + 两个 references |
| `web/vitest.config.ts` | 16 | 测试运行器配置,`environment: "node"`,匹配 `src/**/*.test.{ts,tsx}` |
| `web/README.md` | 104 | 前端 README:栈、开发/构建流程、目录结构、排版与对比度规约 |
| `web/src/index.css` | 255 | Tailwind 入口 + 设计系统样式导入 + JetBrains Mono 字体注册 |

> 本小节 9 行(含 `web/src/index.css`)。**合计点名:3+19+26+4+7+14+5+11+21+12+9 = 131**,与清单一致。

---

## §3 接缝穷举

### 3.1 HTTP 端点(166 条,全部来自 `web/src/lib/api.ts`)

**机械枚举命令**(探针落库在本仓库,换台机器可原样重跑):

```verify
cd /home/user/hermes-agent && \
  python3 /home/user/hermes-study/data/r10/probes/web_endpoints.py web/src/lib/api.ts | tail -4
```

```text
literal call sites : 167
distinct endpoints : 166
not-a-path strings : 1
```

那 1 条 `not-a-path` 是 `web/src/lib/api.ts:208` 的错误信息文案
`` `/api/auth/ws-ticket: HTTP ${res.status}` ``,不是端点。

**为什么不是一条 grep**:`api.ts` 里的 URL 是模板字符串,而 `${...}` 里可以再嵌引号。
按引号配对的正则会在内层 `"` 上截断,例如
`` `/api/hermes/update/check${force ? "?force=true" : ""}` `` 会被读成
`/api/hermes/update/check${force`。探针因此写了一个跟踪 `${` 花括号深度的最小分词器。
路径参数 `${id}` 归一化为 `{}`;紧贴段尾、前面不是 `/` 的插值(如
`` `/api/skills${profileQuery(profile)}` ``)判为 query 后缀并剥掉。

下面 **166 条逐条列全**,按 URL 家族分组。`{}` = 路径参数。

**/api/actions**(1 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/actions/{}/status` | 953 |

**/api/analytics**(2 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/analytics/models` | 506 |
| 2 | `GET` | `/api/analytics/usage` | 502 |

**/api/auth**(2 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/auth/me` | 358 |
| 2 | `POST` | `/api/auth/ws-ticket` | 203 |

**/api/config**(6 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/config` | 509 |
| 2 | `PUT` | `/api/config` | 558 |
| 3 | `GET` | `/api/config/defaults` | 510 |
| 4 | `GET` | `/api/config/raw` | 565 |
| 5 | `PUT` | `/api/config/raw` | 568 |
| 6 | `GET` | `/api/config/schema` | 511 |

**/api/credentials**(3 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/credentials/pool` | 1139 |
| 2 | `POST` | `/api/credentials/pool` | 1146 |
| 3 | `DELETE` | `/api/credentials/pool/{}/{}` | 1155 |

**/api/cron**(10 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/cron/blueprints` | 628 |
| 2 | `POST` | `/api/cron/blueprints/instantiate` | 633 |
| 3 | `GET` | `/api/cron/delivery-targets` | 597 |
| 4 | `GET` | `/api/cron/jobs` | 595 |
| 5 | `POST` | `/api/cron/jobs` | 599 |
| 6 | `DELETE` | `/api/cron/jobs/{}` | 624 |
| 7 | `PUT` | `/api/cron/jobs/{}` | 612 |
| 8 | `POST` | `/api/cron/jobs/{}/pause` | 605 |
| 9 | `POST` | `/api/cron/jobs/{}/resume` | 620 |
| 10 | `POST` | `/api/cron/jobs/{}/trigger` | 622 |

**/api/curator**(3 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/curator` | 1251 |
| 2 | `PUT` | `/api/curator/paused` | 1253 |
| 3 | `POST` | `/api/curator/run` | 1259 |

**/api/dashboard**(14 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `POST` | `/api/dashboard/agent-plugins/install` | 965 |
| 2 | `DELETE` | `/api/dashboard/agent-plugins/{}` | 991 |
| 3 | `POST` | `/api/dashboard/agent-plugins/{}/disable` | 979 |
| 4 | `POST` | `/api/dashboard/agent-plugins/{}/enable` | 973 |
| 5 | `POST` | `/api/dashboard/agent-plugins/{}/update` | 985 |
| 6 | `GET` | `/api/dashboard/font` | 1022 |
| 7 | `PUT` | `/api/dashboard/font` | 1024 |
| 8 | `PUT` | `/api/dashboard/plugin-providers` | 996 |
| 9 | `GET` | `/api/dashboard/plugins` | 958 |
| 10 | `GET` | `/api/dashboard/plugins/hub` | 962 |
| 11 | `GET` | `/api/dashboard/plugins/rescan` | 960 |
| 12 | `POST` | `/api/dashboard/plugins/{}/visibility` | 1004 |
| 13 | `PUT` | `/api/dashboard/theme` | 1016 |
| 14 | `GET` | `/api/dashboard/themes` | 1014 |

**/api/env**(4 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `DELETE` | `/api/env` | 581 |
| 2 | `GET` | `/api/env` | 573 |
| 3 | `PUT` | `/api/env` | 575 |
| 4 | `POST` | `/api/env/reveal` | 587 |

**/api/files**(5 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `DELETE` | `/api/files` | 487 |
| 2 | `GET` | `/api/files` | 459 |
| 3 | `POST` | `/api/files/mkdir` | 481 |
| 4 | `GET` | `/api/files/read` | 463 |
| 5 | `POST` | `/api/files/upload-stream` | 475 |

**/api/gateway**(3 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `POST` | `/api/gateway/restart` | 944 |
| 2 | `POST` | `/api/gateway/start` | 1198 |
| 3 | `POST` | `/api/gateway/stop` | 1200 |

**/api/hermes**(2 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `POST` | `/api/hermes/update` | 946 |
| 2 | `GET` | `/api/hermes/update/check` | 949 |

**/api/logs**(1 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/logs` | 498 |

**/api/mcp**(9 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/mcp/catalog` | 1067 |
| 2 | `POST` | `/api/mcp/catalog/install` | 1075 |
| 3 | `GET` | `/api/mcp/oauth/flows/{}` | 1045 |
| 4 | `GET` | `/api/mcp/servers` | 1031 |
| 5 | `POST` | `/api/mcp/servers` | 1033 |
| 6 | `DELETE` | `/api/mcp/servers/{}` | 1048 |
| 7 | `POST` | `/api/mcp/servers/{}/auth` | 1040 |
| 8 | `PUT` | `/api/mcp/servers/{}/enabled` | 1058 |
| 9 | `POST` | `/api/mcp/servers/{}/test` | 1053 |

**/api/memory**(6 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/memory` | 1160 |
| 2 | `PUT` | `/api/memory/provider` | 1184 |
| 3 | `GET` | `/api/memory/providers/{}/config` | 1163 |
| 4 | `PUT` | `/api/memory/providers/{}/config` | 1167 |
| 5 | `POST` | `/api/memory/providers/{}/setup` | 1176 |
| 6 | `POST` | `/api/memory/reset` | 1190 |

**/api/messaging**(11 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/messaging/platforms` | 863 |
| 2 | `PUT` | `/api/messaging/platforms/{}` | 866 |
| 3 | `POST` | `/api/messaging/platforms/{}/test` | 875 |
| 4 | `POST` | `/api/messaging/telegram/onboarding/start` | 880 |
| 5 | `DELETE` | `/api/messaging/telegram/onboarding/{}` | 905 |
| 6 | `GET` | `/api/messaging/telegram/onboarding/{}` | 889 |
| 7 | `POST` | `/api/messaging/telegram/onboarding/{}/apply` | 896 |
| 8 | `POST` | `/api/messaging/whatsapp/onboarding/start` | 913 |
| 9 | `DELETE` | `/api/messaging/whatsapp/onboarding/{}` | 938 |
| 10 | `GET` | `/api/messaging/whatsapp/onboarding/{}` | 922 |
| 11 | `POST` | `/api/messaging/whatsapp/onboarding/{}/apply` | 929 |

**/api/model**(6 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/model/auxiliary` | 536 |
| 2 | `GET` | `/api/model/info` | 513 |
| 3 | `GET` | `/api/model/moa` | 538 |
| 4 | `PUT` | `/api/model/moa` | 540 |
| 5 | `GET` | `/api/model/options` | 532 |
| 6 | `POST` | `/api/model/set` | 550 |

**/api/ops**(15 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `POST` | `/api/ops/backup` | 1208 |
| 2 | `GET` | `/api/ops/backup/download` | 1215 |
| 3 | `GET` | `/api/ops/checkpoints` | 1281 |
| 4 | `POST` | `/api/ops/checkpoints/prune` | 1283 |
| 5 | `POST` | `/api/ops/config-migrate` | 1269 |
| 6 | `POST` | `/api/ops/debug-share` | 1271 |
| 7 | `POST` | `/api/ops/doctor` | 1204 |
| 8 | `POST` | `/api/ops/dump` | 1267 |
| 9 | `DELETE` | `/api/ops/hooks` | 1243 |
| 10 | `GET` | `/api/ops/hooks` | 1232 |
| 11 | `POST` | `/api/ops/hooks` | 1235 |
| 12 | `POST` | `/api/ops/import` | 1218 |
| 13 | `POST` | `/api/ops/import-upload` | 1227 |
| 14 | `POST` | `/api/ops/prompt-size` | 1266 |
| 15 | `POST` | `/api/ops/security-audit` | 1206 |

**/api/pairing**(4 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/pairing` | 1087 |
| 2 | `POST` | `/api/pairing/approve` | 1089 |
| 3 | `POST` | `/api/pairing/clear-pending` | 1109 |
| 4 | `POST` | `/api/pairing/revoke` | 1099 |

**/api/portal**(1 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/portal` | 1262 |

**/api/profiles**(12 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/profiles` | 641 |
| 2 | `POST` | `/api/profiles` | 671 |
| 3 | `GET` | `/api/profiles/active` | 643 |
| 4 | `POST` | `/api/profiles/active` | 645 |
| 5 | `DELETE` | `/api/profiles/{}` | 714 |
| 6 | `PATCH` | `/api/profiles/{}` | 705 |
| 7 | `POST` | `/api/profiles/{}/describe-auto` | 687 |
| 8 | `PUT` | `/api/profiles/{}/description` | 678 |
| 9 | `PUT` | `/api/profiles/{}/model` | 696 |
| 10 | `GET` | `/api/profiles/{}/setup-command` | 719 |
| 11 | `GET` | `/api/profiles/{}/soul` | 723 |
| 12 | `PUT` | `/api/profiles/{}/soul` | 727 |

**/api/providers**(6 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/providers/oauth` | 823 |
| 2 | `DELETE` | `/api/providers/oauth/sessions/{}` | 855 |
| 3 | `DELETE` | `/api/providers/oauth/{}` | 826 |
| 4 | `GET` | `/api/providers/oauth/{}/poll/{}` | 851 |
| 5 | `POST` | `/api/providers/oauth/{}/start` | 833 |
| 6 | `POST` | `/api/providers/oauth/{}/submit` | 842 |

**/api/sessions**(14 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/sessions` | 381 |
| 2 | `POST` | `/api/sessions/bulk-delete` | 420 |
| 3 | `DELETE` | `/api/sessions/empty` | 414 |
| 4 | `GET` | `/api/sessions/empty/count` | 410 |
| 5 | `POST` | `/api/sessions/import` | 442 |
| 6 | `POST` | `/api/sessions/prune` | 452 |
| 7 | `GET` | `/api/sessions/search` | 815 |
| 8 | `GET` | `/api/sessions/stats` | 435 |
| 9 | `DELETE` | `/api/sessions/{}` | 403 |
| 10 | `GET` | `/api/sessions/{}` | 392 |
| 11 | `PATCH` | `/api/sessions/{}` | 427 |
| 12 | `GET` | `/api/sessions/{}/export` | 437 |
| 13 | `GET` | `/api/sessions/{}/latest-descendant` | 397 |
| 14 | `GET` | `/api/sessions/{}/messages` | 388 |

**/api/skills**(12 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/skills` | 741 |
| 2 | `POST` | `/api/skills` | 753 |
| 3 | `GET` | `/api/skills/content` | 750 |
| 4 | `PUT` | `/api/skills/content` | 759 |
| 5 | `POST` | `/api/skills/hub/install` | 1289 |
| 6 | `GET` | `/api/skills/hub/preview` | 1316 |
| 7 | `GET` | `/api/skills/hub/scan` | 1320 |
| 8 | `GET` | `/api/skills/hub/search` | 1308 |
| 9 | `GET` | `/api/skills/hub/sources` | 1312 |
| 10 | `POST` | `/api/skills/hub/uninstall` | 1295 |
| 11 | `POST` | `/api/skills/hub/update` | 1301 |
| 12 | `PUT` | `/api/skills/toggle` | 743 |

**/api/status**(1 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/status` | 339 |

**/api/system**(1 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/system/stats` | 1248 |

**/api/tools**(6 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/tools/toolsets` | 765 |
| 2 | `PUT` | `/api/tools/toolsets/{}` | 768 |
| 3 | `GET` | `/api/tools/toolsets/{}/config` | 777 |
| 4 | `PUT` | `/api/tools/toolsets/{}/env` | 790 |
| 5 | `POST` | `/api/tools/toolsets/{}/post-setup` | 799 |
| 6 | `PUT` | `/api/tools/toolsets/{}/provider` | 781 |

**/api/webhooks**(5 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `GET` | `/api/webhooks` | 1114 |
| 2 | `POST` | `/api/webhooks` | 1118 |
| 3 | `POST` | `/api/webhooks/enable` | 1116 |
| 4 | `DELETE` | `/api/webhooks/{}` | 1124 |
| 5 | `PUT` | `/api/webhooks/{}/enabled` | 1129 |

**/auth(非 /api)**(1 条)

| # | 方法 | 路径 | api.ts 行号 |
|---|---|---|---|
| 1 | `POST` | `/auth/logout` | 362 |

小计:1+2+2+6+3+10+3+14+4+5+3+2+1+9+6+11+6+15+4+1+12+6+14+12+1+1+6+5+1 = **166**。

### 3.2 `api.ts` 之外的 5 条(4 个 WebSocket + 1 个上传)

```verify
cd /home/user/hermes-agent && \
  python3 /home/user/hermes-study/data/r10/probes/web_endpoints.py \
    $(find web/src -name '*.ts' -o -name '*.tsx' | grep -v '\.test\.' | sort | tr '\n' ' ') | tail -3
```

```text
literal call sites : 172
distinct endpoints : 171
not-a-path strings : 1
```

171 − 166 = 5:

| # | 协议 | 路径 | 调用处 | 用途 |
|---|---|---|---|---|
| 1 | WS | `/api/pty` | `web/src/pages/ChatPage.tsx:982`:`      const url = await api.buildWsUrl("/api/pty", params);` | 嵌入式终端的字节双向管道 |
| 2 | WS | `/api/console` | `web/src/components/HermesConsoleModal.tsx:403`:`        const url = await api.buildWsUrl("/api/console", params);` | 运维控制台弹窗 |
| 3 | WS | `/api/events` | `web/src/components/ChatSidebar.tsx:303`:`      const url = await buildWsUrl("/api/events", { channel });` | Chat 侧栏的结构化事件订阅 |
| 4 | WS | `/api/ws` | `web/src/lib/gatewayClient.ts:59`:`        path: "/api/ws",` | JSON-RPC 网关(连接态徽章、凭据告警、slash 命令) |
| 5 | POST | `/api/chat/image-upload` | `web/src/lib/chatImagePaste.ts:145`:`  const res = await authedFetch(\`/api/chat/image-upload${qs}\`, {` | 粘贴图片上传 |

**「SPA 的网络出口只有这几处」是一条负结论,搜索面写出来**:对 `web/src/` 下**全部**
非测试 `.ts`/`.tsx` 扫每一个建连原语的出现,不排除任何文件。

```verify
cd /home/user/hermes-agent && grep -rnoE '\b(fetch|fetchJSON|authedFetch)\(|new WebSocket' \
  web/src/ --include='*.ts' --include='*.tsx' | grep -v '\.test\.' \
  | sed 's/:[0-9]*:/ /' | sort | uniq -c | sort -rn
```

```text
      5 web/src/lib/api.ts fetch(
      2 web/src/lib/api.ts authedFetch(
      1 web/src/pages/SessionsPage.tsx fetch(
      1 web/src/pages/ChatPage.tsx new WebSocket
      1 web/src/lib/chatImagePaste.ts authedFetch(
      1 web/src/components/HermesConsoleModal.tsx new WebSocket
      1 web/src/components/ChatSidebar.tsx new WebSocket
```

读法:`api.ts` 的 5 处 `fetch(` 里有 1 处在注释里(`:367` 的
"letting fetch() opaquely consume the redirect"),真正建连的是 `:114` / `:203` / `:253` / `:362`。
`api.ts` 之外只有两处:`web/src/lib/chatImagePaste.ts` 的 `authedFetch(`(合规,走 api.ts)
与 `web/src/pages/SessionsPage.tsx` 的裸 `fetch(`(**不合规**,见 §7 ■-G-01)。
`new WebSocket` 3 处,加上 `gatewayClient` 经 `@hermes/shared` 的
`JsonRpcGatewayClient` 建连,共 4 条 WS。

**唯一的开放口子是插件 SDK**——它把裸 `fetchJSON` 原样交给插件:

`web/src/plugins/registry.ts:129 @ 863e313`

```ts
    fetchJSON,
    // Authenticated fetch for non-JSON endpoints (uploads / blob downloads).
    // Handles loopback-token vs gated-cookie auth so plugins never read
    // window.__HERMES_SESSION_TOKEN__ directly.
    authedFetch,
    // Build a ws(s):// URL with the correct auth param for the active mode
```

所以"SPA 自己只打这 171 条"成立,"跑在 dashboard 里的代码只打这 171 条"不成立。

### 3.3 路由表(19 条内置 + 1 条兜底)

`web/src/App.tsx:155 @ 863e313`

```tsx
const BUILTIN_ROUTES_CORE: Record<string, ComponentType> = {
  "/": RootRedirect,
  "/sessions": SessionsPage,
  "/files": FilesPage,
  "/analytics": AnalyticsPage,
  "/models": ModelsPage,
  "/logs": LogsPage,
  "/cron": CronPage,
  "/skills": SkillsPage,
  "/plugins": PluginsPage,
  "/mcp": McpPage,
  "/pairing": PairingPage,
  "/channels": ChannelsPage,
  "/webhooks": WebhooksPage,
  "/system": SystemPage,
  "/profiles": ProfilesPage,
  "/profiles/new": ProfileBuilderPage,
  "/config": ConfigPage,
  "/env": EnvPage,
  "/docs": DocsPage,
```

18 条 + 闭合;第 19 条是 `/chat`,它**不在**这张表里,而是在 `web/src/App.tsx:450`
处按 `embeddedChat` 条件合并进来,元素是一个**返回 `null` 的占位组件**:

`web/src/App.tsx:181 @ 863e313`

```tsx
function ChatRouteSink() {
  return null;
}
```

真正的 ChatPage 渲染在 `<Routes>` **之外**,用 `display:none` 隐藏,
这样切标签页时 PTY 子进程、WebSocket、xterm 实例都不被卸载;
`ChatRouteSink` 只是"占住这个路径,别让 `*` 兜底重定向抢走"。
兜底本身在 `web/src/App.tsx:775` 的 `path="*"`。

**路由合并分三轮**,入口是:

`web/src/App.tsx:306 @ 863e313`

```tsx
function buildRoutes(
  builtinRoutes: Record<string, ComponentType>,
  manifests: PluginManifest[],
): Array<{
  key: string;
  path: string;
  element: ReactNode;
}> {
```

① 内置路径逐个检查有没有插件声明 `tab.override` 要顶替;
② 未 override 的插件按 `tab.path` 追加(跳过 `hidden` 与 `/plugins`);
③ `hidden` 插件也注册路由但不进导航。

### 3.4 侧栏导航表(17 条,`BUILTIN_NAV_REST`)

`web/src/App.tsx:185 @ 863e313`

```tsx
const BUILTIN_NAV_REST: NavItem[] = [
  {
    path: "/sessions",
    labelKey: "sessions",
    label: "Sessions",
    icon: MessageSquare,
```

顺序即渲染顺序:`/sessions`、`/files`、`/analytics`、`/models`、`/logs`、`/cron`、
`/skills`、`/plugins`、`/mcp`、`/channels`、`/webhooks`、`/pairing`、`/profiles`、
`/config`、`/env`、`/system`、`/docs`。

与 3.3 的差集,**两条路由有页面但不在导航里**:`/profiles/new`(从 `/profiles` 内部进)
和 `/`(重定向)。`/chat` 由一个单独的导航项在嵌入式 chat 开启时插到最前:

`web/src/App.tsx:137 @ 863e313`

```tsx
const CHAT_NAV_ITEM: NavItem = {
  path: "/chat",
  labelKey: "chat",
  label: "Chat",
  icon: Terminal,
};
```

故实际 18 条;`/analytics` 在 `showTokenAnalytics` 为假时被过滤掉。

### 3.5 api 客户端方法表(166 个)与页面映射

`export const api = {...}` 顶层键 **166 个**。这个数和端点数 166 只是巧合:
`buildWsUrl` 与 `exportSessionUrl` 不发请求(前者拼 WS URL、后者只拼路径),
而 `getSessions` 一个方法覆盖 `GET /api/sessions` 的多种 query 组合。

页面 → 调用的 api 方法(机械枚举,处理了 `api\n  .method(` 这种换行写法):

```verify
cd /home/user/hermes-agent && python3 - <<'PY'
import re, glob
CALL = re.compile(r"\bapi\s*\.\s*([A-Za-z0-9_]+)")
for p in sorted(glob.glob("web/src/pages/*.tsx")):
    if ".test." in p: continue
    n = sorted(set(CALL.findall(open(p, encoding="utf-8").read())) - {"example"})
    print(f"{p}\t{len(n)}")
PY
```

```text
web/src/pages/AnalyticsPage.tsx	2
web/src/pages/ChannelsPage.tsx	13
web/src/pages/ChatPage.tsx	3
web/src/pages/ConfigPage.tsx	7
web/src/pages/CronPage.tsx	12
web/src/pages/DocsPage.tsx	0
web/src/pages/EnvPage.tsx	4
web/src/pages/FilesPage.tsx	5
web/src/pages/LogsPage.tsx	1
web/src/pages/McpPage.tsx	9
web/src/pages/ModelsPage.tsx	7
web/src/pages/PairingPage.tsx	4
web/src/pages/PluginsPage.tsx	13
web/src/pages/ProfileBuilderPage.tsx	4
web/src/pages/ProfilesPage.tsx	13
web/src/pages/SessionsPage.tsx	13
web/src/pages/SkillsPage.tsx	10
web/src/pages/SystemPage.tsx	33
web/src/pages/WebhooksPage.tsx	7
```

读法:`SystemPage` 一页调 33 个方法,是第二名的 2.5 倍——**运维面全堆在一页**,
这也是 §6 三条移交项里有两条落在它身上的结构原因。`DocsPage` 为 0(纯 iframe)。

**恰好 1 个 api 方法在 SPA 里没有调用方**:

`web/src/lib/api.ts:1294 @ 863e313`

```ts
  uninstallSkillFromHub: (name: string, profile?: string) =>
    fetchJSON<ActionResponse>("/api/skills/hub/uninstall", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, profile: profile || undefined }),
    }),
```

技能页有安装/更新/扫描/预览/搜索,**没有卸载按钮**。搜索面:

```verify
cd /home/user/hermes-agent && grep -rni 'uninstall' web/src/
```

```text
web/src/lib/api.ts:1286:  // ``profile`` scopes install/uninstall/update and the installed-state
web/src/lib/api.ts:1294:  uninstallSkillFromHub: (name: string, profile?: string) =>
web/src/lib/api.ts:1295:    fetchJSON<ActionResponse>("/api/skills/hub/uninstall", {
web/src/pages/McpPage.tsx:245:  const runInstall = useCallback(
web/src/pages/McpPage.tsx:276:      void runInstall(entry, {});
web/src/pages/McpPage.tsx:293:    void runInstall(installEntry, envMap);
```

全部命中只有 `api.ts` 的定义与注释、以及 `McpPage.tsx` 里三处名为 `runInstall`
的无关标识符(它们因子串 `nInstall` 被 `-i` 匹配到,与 hub 卸载无关)。
同名能力在桌面端另有一份独立实现(`apps/desktop/src/hermes.ts:1684`)。
它经 `SDK.api` 仍对插件可达,不是死代码,但**是一条界面上到不了的端点**。

### 3.6 插件插槽表(声明 30 / 实渲染 31 / 文档 28)

```verify
cd /home/user/hermes-agent && python3 /home/user/hermes-study/data/r10/probes/web_plugin_slots.py
```

```text
KNOWN_SLOT_NAMES declared : 30
rendered slot names       : 31
dynamic <PluginSlot name={...}> sites : 0 []

declared but NEVER rendered:
  - footer-left
  - footer-right
  - sidebar
rendered but NOT declared:
  - files:bottom   web/src/pages/FilesPage.tsx:458
  - files:top   web/src/pages/FilesPage.tsx:266
  - models:bottom   web/src/pages/ModelsPage.tsx:1364
  - models:top   web/src/pages/ModelsPage.tsx:1244

website/docs slot catalogue : 28
documented but NEVER rendered: ['footer-left', 'footer-right', 'sidebar']
rendered but NOT documented : ['files:bottom', 'files:top', 'models:bottom', 'models:top', 'plugins:bottom', 'plugins:top']
```

"渲染面完备"这条负结论的搜索面:全 `web/src/**/*.ts*`(排除 `*.test.*` 与
`web/src/plugins/slots.ts` 自身的 docstring 示例)扫 `<PluginSlot name="…"`,
并同时扫 `<PluginSlot name={` 这种动态名——**0 处**,所以静态枚举就是全集。

**声明面 30 个**:

`web/src/plugins/slots.ts:61 @ 863e313`

```ts
export const KNOWN_SLOT_NAMES = [
  // Shell-wide
  "backdrop",
```

壳层 10 个
`backdrop` / `header-left` / `header-right` / `header-banner` / `sidebar` /
`pre-main` / `post-main` / `footer-left` / `footer-right` / `overlay`;
页面级 20 个 = `sessions` / `analytics` / `logs` / `cron` / `skills` / `plugins` /
`config` / `env` / `docs` / `chat` 各一对 `:top` / `:bottom`。
**实渲染多出来的 4 个**是 `files` 与 `models` 两对。三面互不相等的定案见 §7。

### 3.7 插件 SDK 导出面

`window.__HERMES_PLUGIN_SDK__`(`web/src/plugins/registry.ts` 的 `exposePluginSDK`)。
顶层能力 6 个:`React`、`hooks`(8 个)、`api`、`fetchJSON`、`authedFetch`、
`buildWsUrl`、`buildWsAuthParam`;`components` 16 个:`Card` / `CardHeader` / `CardTitle` /
`CardContent` / `Badge` / `Button` / `Checkbox` / `Input` / `Label` / `Select` /
`SelectOption` / `Separator` / `Tabs` / `TabsList` / `TabsTrigger` / `PluginSlot`;
`utils` 3 个:`cn` / `timeAgo` / `isoTimeAgo`;hook 1 个:`useI18n`。
另有 `window.__HERMES_PLUGINS__` 承载 `register` / `registerSlot`。
类型契约手写在 `web/src/plugins/sdk.d.ts`,自陈是 spike,并解释了为什么**不**用
`typeof window.__HERMES_PLUGIN_SDK__` 推导(避免把内部模块路径泄进公共契约)。

### 3.8 i18n 语言表(17 种)

`en`、`zh`、`zh-hant`、`ja`、`de`、`es`、`fr`、`tr`、`uk`、`af`、`ko`、`it`、`ga`、
`pt`、`ru`、`hu`、`ar`。RTL 集合只有 `ar`。
`Translations` 接口有 **651** 个叶子字符串键(`web/src/i18n/en.ts` 里形如 `key: "…"` 的行数)。
17 个语言文件里 **只有 `web/src/i18n/ar.ts` 走 `defineLocale` 的部分翻译回落**,
其余 16 个都是完整的 `Translations` 字面量——也就是说,`web/src/i18n/define-locale.ts`
这套"新语言可以只翻一半"的机制目前只有一个消费者。

### 3.9 主题与字体表

内置主题 **8** 个:

`web/src/themes/presets.ts:231 @ 863e313`

```ts
export const BUILTIN_THEMES: Record<string, DashboardTheme> = {
  default: defaultTheme,
  "default-large": defaultLargeTheme,
  "nous-blue": nousBlueTheme,
  midnight: midnightTheme,
  ember: emberTheme,
  mono: monoTheme,
  cyberpunk: cyberpunkTheme,
  rose: roseTheme,
```

字体选项 **14** 个(`web/src/themes/fonts.ts`):3 个系统栈
(`system-sans` / `system-serif` / `system-mono`)+ 11 个可下载
(`inter`、`ibm-plex-sans`、`work-sans`、`atkinson-hyperlegible`、`dm-sans`、
`spectral`、`fraunces`、`source-serif`、`jetbrains-mono`、`ibm-plex-mono`、`space-mono`)。
布局变体 3 种:

`web/src/themes/types.ts:71 @ 863e313`

```ts
/** Overall layout variant the shell renders. `standard` = default single-
 *  column page layout. `cockpit` = reserves a left sidebar rail for a
 *  plugin slot (intended for HUD-style themes with persistent status panels).
 *  `tiled` = relaxes the main content max-width so pages can use the full
 *  viewport width. Themes set this; plugins react via CSS vars /
 *  `[data-layout-variant="..."]` selectors. */
export type ThemeLayoutVariant = "standard" | "cockpit" | "tiled";
```

### 3.10 profile 作用域前缀表(17 条)

`web/src/lib/api.ts:70 @ 863e313`

```ts
const PROFILE_SCOPED_PREFIXES = [
  "/api/status",
  "/api/gateway",
  "/api/analytics",
  "/api/skills",
  "/api/tools/toolsets",
  "/api/config",
  "/api/env",
  "/api/mcp",
  "/api/messaging/platforms",
  "/api/messaging/telegram/onboarding",
  "/api/messaging/whatsapp/onboarding",
  "/api/model/info",
  "/api/model/set",
  "/api/model/auxiliary",
  "/api/model/moa",
  "/api/model/options",
  // A named profile keeps its own pairing whitelist, and its gateway only
  // consults that one — approving into the global store would grant access
  // the running gateway never sees.
  "/api/pairing",
];
```

---

## §4 端到端链:Cron 页的「立即触发」

选它的理由:它跨了本片的全部横切件(profile 作用域、认证头、base path),
并且正好是 §6 里 H-R8C-e 那条移交项的**前端对照物**。逐跳带锚点。

**跳 1 · 用户点按钮。** Cron 页每行任务右侧有一个闪电图标按钮,**无二次确认**:

`web/src/pages/CronPage.tsx:1094 @ 863e313`

```tsx
                  <Button
                    ghost
                    size="icon"
                    title={t.cron.triggerNow}
                    aria-label={t.cron.triggerNow}
                    onClick={() => handleTrigger(job)}
                  >
```

**跳 2 · 页面处理器取出这条 job 自己的 profile。**

`web/src/pages/CronPage.tsx:711 @ 863e313`

```tsx
  const handleTrigger = async (job: CronJob) => {
    try {
      await api.triggerCronJob(job.id, getJobProfile(job));
      showToast(
        `${t.cron.triggerNow}: "${truncateText(getJobTitle(job), 30)}"`,
        "success",
      );
      loadJobs();
```

传进去的 profile 从 job 载荷里读,取不到则回落 `"default"`:

`web/src/pages/CronPage.tsx:485 @ 863e313`

```tsx
function getJobProfile(job: CronJob): string {
  return asText(job.profile) || asText(job.profile_name) || "default";
}
```

**注意这里传的是 job 自己的 profile,不是界面上选中的过滤器**——
过滤器还可以选 `"all"`:

`web/src/pages/CronPage.tsx:969 @ 863e313`

```tsx
              <SelectOption value="all">All profiles</SelectOption>
```

此时列表里同时躺着多个 profile 的任务,每一行按自己的归属触发。

**跳 3 · 客户端把 profile 拼成显式 query。**

`web/src/lib/api.ts:621 @ 863e313`

```ts
  triggerCronJob: (id: string, profile = "default") =>
    fetchJSON<CronJob>(`/api/cron/jobs/${encodeURIComponent(id)}/trigger?profile=${encodeURIComponent(profile)}`, { method: "POST" }),
```

**跳 4 · `fetchJSON` 的两件横切事:profile 注入与 token 注入。**

`web/src/lib/api.ts:93 @ 863e313`

```ts
function withManagementProfile(url: string): string {
  if (!_managementProfile) return url;
  if (url.includes("profile=")) return url; // explicit param wins
  const path = url.split("?")[0];
  if (!PROFILE_SCOPED_PREFIXES.some((p) => path.startsWith(p))) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}profile=${encodeURIComponent(_managementProfile)}`;
```

这一跳有两道各自独立的"不改写"闸:`/api/cron` **不在** `PROFILE_SCOPED_PREFIXES` 里
(§3.10 的表,17 条无 cron),而且 URL 里已经有 `profile=`,显式参数优先。
两道闸任一成立都不改写——这是有意为之,`web/src/lib/api.ts:66` 的注释明写
"cron (which has its own per-job profile params)"。

`web/src/lib/api.ts:102 @ 863e313`

```ts
export async function fetchJSON<T>(
  url: string,
  init?: RequestInit,
  options?: FetchJSONOptions,
): Promise<T> {
  url = withManagementProfile(url);
  // Inject the session token into all /api/ requests.
  const headers = new Headers(init?.headers);
  const token = window.__HERMES_SESSION_TOKEN__;
  if (token) {
    setSessionHeader(headers, token);
  }
  const res = await fetch(`${BASE}${url}`, {
```

`${BASE}` 就是反向代理前缀(§5.2)。到这里请求形如
`POST <BASE>/api/cron/jobs/<id>/trigger?profile=<name>`,带 `X-Hermes-Session-Token` 头,
并且 `credentials: "include"` 让 gated 模式的 cookie 一并带上。

**跳 5 · 后端认证中间件放行。**

`hermes_cli/web_server.py:664 @ 863e313`

```python
    is_mcp_oauth_callback = path.startswith("/api/mcp/oauth/callback/")
    if path.startswith("/api/") and path not in _PUBLIC_API_PATHS and not is_mcp_oauth_callback:
        if not _has_valid_session_token(request) and not _has_valid_query_token(request, path):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized"},
            )
```

`/api/cron/jobs/{id}/trigger` **不在** `PUBLIC_API_PATHS` 里,所以这条链是被 dashboard
会话认证管着的。(对照:`/api/cron/fire` 在里面——见 §6.1。)

**跳 6 · 路由。**

`hermes_cli/web_routers/cron.py:114 @ 863e313`

```python
@router.post("/api/cron/jobs/{job_id}/trigger")
async def trigger_cron_job(job_id: str, profile: Optional[str] = None):
    return await _run_cron_dashboard_io(_trigger_cron_job_sync, job_id, profile)
```

**跳 7 · 内核执行。**

`hermes_cli/web_server.py:11918 @ 863e313`

```python
def _trigger_cron_job_sync(job_id: str, profile: Optional[str] = None):
    selected = profile or _find_cron_job_profile(job_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _call_cron_for_profile(selected, "trigger_job", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
```

**跳 8 · 回到界面。** 成功则 `showToast(...)` 弹一条 toast,并调 `loadJobs()` 重新拉列表:

`web/src/pages/CronPage.tsx:579 @ 863e313`

```tsx
  const loadJobs = useCallback(() => {
    api
      .getCronJobs(selectedProfile)
      .then(setJobs)
      .catch(() => showToast(t.common.loading, "error"))
      .finally(() => setLoading(false));
  }, [selectedProfile, showToast, t.common.loading]);
```

注意它拉的是**过滤器**的 profile(可能是 `"all"`),不是刚触发那条 job 的 profile。
失败时 `fetchJSON` 抛 `Error("<status>: <body>")`,页面 catch 后弹红 toast。
**没有乐观更新、没有轮询任务执行状态**——用户只知道"请求被接受了",
任务真正跑成什么样要去 Logs 页看。

---

## §5 逐机制结构笔记

### 5.1 两种认证模式,一个客户端

后端有两套 dashboard 认证:**loopback 模式**(绑 127.0.0.1)用一个每次进程启动都会轮换的
临时 session token,由服务端注入进 HTML;**gated 模式**(公网绑定)用 OAuth cookie。
前端把这两套的差异全压在 `api.ts` 里:

- 所有 REST 请求都同时带 `X-Hermes-Session-Token` 头(有就带)与 `credentials: "include"`
  (cookie 自动跟)。哪一套生效由服务端决定,客户端不判断。
- **401 有三条分支**(`web/src/lib/api.ts:123` 起):
  ① 响应体是 `{error: "unauthenticated"|"session_expired", login_url}` → 存下当前位置到
  `sessionStorage["hermes.lastLocation"]`,整页跳 `login_url`,并返回一个**永不 resolve 的 Promise**
  (页面正在卸载,不能让调用方以为失败);
  ② loopback 模式且调用方没声明 `allowUnauthorized` → 认为是 token 轮换了,
  触发**一次性**整页重载(`web/src/lib/dashboard-auth-reload.ts` 的 sessionStorage 闩锁);
  ③ 其余当普通错误抛出。
  任何 2xx 都会清掉那个一次性闩锁,理由写在 `web/src/lib/api.ts:172`:一次成功证明当前 token 有效,
  下一次 401 应该被允许再走一轮重载。
- **`/api/auth/me` 必须声明 `allowUnauthorized: true`**,否则在 loopback 模式下它按设计 401,
  而"其他请求都成功 → 闩锁被清 → 这个 401 又触发重载"会构成无限重载环。
  这是一段值得抄走的设计:**一个全局的"401 就重载"策略必须给"预期内的 401"留豁免口**。
- **WebSocket 的认证是另一条路**。浏览器无法给 WS 升级请求设 `Authorization` 头,
  gated 模式下后端又拒绝 `?token=`。于是用已认证的 REST 通道换一张**单次、30 秒**的 ticket:

`web/src/lib/api.ts:202 @ 863e313`

```ts
export async function getWsTicket(): Promise<{ ticket: string; ttl_seconds: number }> {
  const res = await fetch(`${BASE}/api/auth/ws-ticket`, {
    method: "POST",
    credentials: "include",
  });
```

  `buildWsAuthParam()` 按模式返回 `["ticket", …]` 或 `["token", …]`。**每次连接都要新取一张**。

### 5.2 反向代理前缀(base path)

dashboard 可能被挂在 `https://host/hermes/` 这种子路径下。后端读 `X-Forwarded-Prefix`
把前缀注入成 `window.__HERMES_BASE_PATH__`,前端归一化后存成模块级常量:

`web/src/lib/api.ts:10 @ 863e313`

```ts
function readBasePath(): string {
  if (typeof window === "undefined") return "";
  const raw = window.__HERMES_BASE_PATH__ ?? "";
  if (!raw) return "";
  // Normalise: ensure leading slash, strip trailing slash.
  const withLead = raw.startsWith("/") ? raw : `/${raw}`;
  return withLead.replace(/\/+$/, "");
}
```

这个 `BASE` 在三处使用:
`fetchJSON` / `authedFetch` 拼 URL、`buildWsUrl` 传给 `buildHermesWebSocketUrl`、
`main.tsx` 传给 `<BrowserRouter basename>`。**绕过 `BASE` 的网络调用会在这种部署下 404**
——全仓恰有一处,见 §7 ■-G-01。

### 5.3 管理目标 profile:一个开关,全站生效

hermes 支持多 profile(同一台机器上多套 HERMES_HOME)。dashboard 的设计选择是
**一个全局开关而不是每页一个**:侧栏的 `ProfileSwitcher` 写
`ProfileProvider`(`web/src/contexts/ProfileProvider.tsx`)的 React state,
Provider 再把值镜像进 api 模块(`setManagementProfile`)与 URL(`?profile=`)。
React state 是唯一真源,URL 只是它的投影,这样深链接能落到正确 profile、刷新也不丢。

改写只发生在 §3.10 那 17 个前缀上,且**显式参数永远优先**。三类端点被有意排除:
`ops`(机器级)、`cron`(自带 per-job profile)、`profiles` 自身。
当目标 ≠ 本进程 profile 时,`ProfileScopeBanner` 会在全站顶部挂一条琥珀色横幅
——这是把"你正在改别人的家"这件事做成了**持续可见**而不是一次性提示。

### 5.4 插件加载:三步 + 一个竞态守卫

`web/src/plugins/usePlugins.ts`:① `GET /api/dashboard/plugins` 取 manifest 列表
(并用 `sessionStorage` 缓存,键 `hermes:plugin-manifests`);② 为声明了 `css` 的插件注入
`<link>`;③ 注入 `<script src=/dashboard-plugins/<name>/<entry>>`,等插件自己调
`window.__HERMES_PLUGINS__.register(name, Component)`。

两处值得抄的细节:

- **`PluginPage` 用 `useSyncExternalStore` 而不是 `useEffect` 订阅注册事件**,
  注释直说了原因——脚本可能在 effect 跑之前就执行完并 `register()`:

`web/src/plugins/PluginPage.tsx:15 @ 863e313`

```tsx
  // Subscribe in render (via useSyncExternalStore) so we never miss
  // `register()` if the script loads before a useEffect would run.
  const Component = useSyncExternalStore(
    (onChange) => onPluginRegistered(onChange),
    () => getPluginComponent(name) ?? null,
    () => null,
  );
```

- **缓存不能无条件用来提前结束 loading**。`canSeedLoadedFromCache` 只在缓存里
  没有任何插件声明 `tab.override === "/chat"` 时才允许 `loading=false` 起步。
  否则常驻 ChatPage 宿主会先挂载、spawn 一个 PTY,再被插件顶掉——用户的会话在绘制中途被杀。

**SRI(Subresource Integrity,子资源完整性:给 `<script>` 标注哈希,浏览器校验不过就不执行)是可选的**:

`web/src/plugins/usePlugins.ts:130 @ 863e313`

```ts
      // SRI integrity verification — defense against compromised plugin
      // delivery. Plugin manifests can declare an integrity hash
      // (e.g. "sha384-...") which the browser verifies before executing.
      // Without this, a man-in-the-middle or compromised plugin server
      // can substitute the JS bundle silently. Opt-in: when no integrity
      // is declared in the manifest, behavior is unchanged.
      if (manifest.integrity && typeof manifest.integrity === "string") {
        script.integrity = manifest.integrity;
        script.crossOrigin = "anonymous";
```

见 §7 ■-G-04 对这段注释所声称威胁模型的判定。

### 5.5 主题引擎

`web/src/themes/context.tsx` 做四件事:把主题对象摊平成 CSS 自定义属性写到
`document.documentElement`(并记住上一轮写过哪些键,切主题时清理陈旧变量);
按需注入字体表 `<link>`;把主题的 `customCSS` 塞进一个**复用的** `<style id="hermes-theme-custom-css">`,
用 `el.textContent = css` 赋值(不是 `innerHTML`,所以 `</style>` 无法闭合逃逸);
把 `layoutVariant` 写成 `data-layout-variant` 属性供 CSS 选择器与插件消费。
主题选择本地存 `localStorage` 保证首屏不闪,同时 `PUT /api/dashboard/theme` 落服务端。

一个结构观察:`layoutVariant: "cockpit"` 的文档语义是"预留一条左侧栏给插件插槽",
但代码里 `layoutVariant` 只被写成一个 data 属性,**没有任何地方渲染那条栏**(§7 ▲-G-01)。

### 5.6 Chat / PTY

`ChatPage` 是全片最重的一块。要点:

- **常驻宿主**:它渲染在 `<Routes>` 之外,靠 `display:none` 隐藏。理由写在路由表上方:

`web/src/App.tsx:144 @ 863e313`

```tsx
/**
 * Built-in routes except /chat.  Chat is rendered persistently (outside
 * <Routes>) when embedded — see the persistent chat host block rendered
 * inline near the bottom of this file — so the PTY child, WebSocket,
 * and xterm instance survive when the user visits another tab and comes
 * back.  A `display:none` toggle hides the terminal without unmounting.
```

  但宿主本身要等第一次访问 `/chat` 才挂载(`latchChatActivation` 粘滞闩锁),
  否则打开 dashboard 任意页面都会 spawn 一个 TUI 并触发 `npm install`。
- **连接身份由四个 query 参数决定**:`channel`、`resume`(续接哪个会话)、`fresh`、
  `attach`(keep-alive 令牌,让刷新后重挂同一个活着的 PTY),外加 `profile`。
- **移动端韧性**占了不小篇幅:`pty-reconnect.ts` 处理"socket 卡在 CONNECTING 从不 onclose"
  (移动网络切换),`pty-mobile-input.ts` 处理输入法整行替换,
  `pty-resume-sanitizer.ts` 处理 Ink 两遍渲染吐出的病态 ANSI(且注释明确指出 PTY 是
  cooked 模式,所以要匹配 `\r\n` 而非 `\n`——一条"按真实管道而不是按想象写过滤器"的记录)。
- **Chat 侧栏另开两条 socket**:`GatewayClient` 走 `/api/ws`(JSON-RPC,只用于连接态与凭据告警),
  `/api/events` 走结构化事件订阅。模型徽章**不**从这两条来,而是走 REST `/api/model/info`。

### 5.7 i18n

`Translations` 是一个 651 键的嵌套接口,`en.ts` 是基准。非英语文件有两种写法:
完整字面量(16 个)与 `defineLocale(部分覆盖)`(1 个)。后者的类型体操
(`TranslationOverride<T>`)让**缺键合法、错键仍然编译失败**——这正是"部分翻译"
这个需求应该有的类型形状。语言选择存 `localStorage["hermes-locale"]`,
`ar` 触发 `dir="rtl"` 以便 Tailwind 的逻辑方向工具类翻转。

### 5.8 构建与开发环路

`npm run build` = `tsc -b && vite build`,产物直接落到
`../hermes_cli/web_dist/`(`web/vite.config.ts:88`),再由 pyproject 的 package-data 打进 Python 包。
产物按 7 组切分(react-vendor / xterm / three / plot / motion / ui / vendor),
配合 `App.tsx` 里 19 个 `lazy()` 页面形成路由级代码分割。

开发环路里有一处很实用的设计:**Vite dev server 会去抓生产服务器的 token**。

`web/vite.config.ts:18 @ 863e313`

```ts
function hermesDevToken(): Plugin {
  const TOKEN_RE = /window\.__HERMES_SESSION_TOKEN__\s*=\s*"([^"]+)"/;
  const EMBEDDED_RE =
    /window\.__HERMES_DASHBOARD_EMBEDDED_CHAT__\s*=\s*(true|false)/;
```

这个插件在每次 dev 页面加载时 fetch `http://127.0.0.1:9119` 的 HTML,
正则抠出 `window.__HERMES_SESSION_TOKEN__` 再注回 dev HTML。
没有它,dev server 自己的 `index.html` 不含 token,所有 `/api/*` 都 401。
`server.proxy` 把 `/api`(含 `ws: true`)与 `/dashboard-plugins` 都代理到后端。

---

## §6 移交取证:H-R8C-e/f/g 的前端可达性

三条移交项由 R8C 立项、去向写 `R9`,R9A/R9B/R9C/R9D 四轮均未处置,R10 认领。
**后端侧已由主线取证**(见 `/home/user/hermes-study/notes/r10-90-handover-rulings.md` §2)。
本节只回答**前端这一面**:这些危险动作在界面上到底可不可达、点几下、有没有警告。

### 6.1 H-R8C-e —— `/api/cron/fire` 在前端**完全不存在**

**结论:前端未暴露,只能通过裸 API 到达;而且按设计就该如此。**

**负结论的搜索面(三层,互相独立)**:

① 字面量搜索,全 `web/` 目录、不排除任何文件类型:

```verify
cd /home/user/hermes-agent && grep -rn 'cron/fire' web/ | wc -l
```

```text
0
```

② 词级搜索。`grep -rniI 'fire' web/` 共 26 处命中,**逐条看过,全部是英文散文**:
`AuthWidget.tsx:49` "Don't fire the request"、`ChatSidebar.tsx:323` "fires a close event"、
`ChatSessionList.tsx:39` "callback fired after a row is picked"、
`App.tsx:180` "fire when the user navigates to /chat"、
`ProfileProvider.tsx:49` "fetches fired by child effects"、
`SystemPage.tsx:465` "fire-and-forget ops"、`SystemPage.tsx:791` "grant consent so it fires"、
`SystemPage.tsx:1347` "not a fire-and-forget log tail"、
`WebhooksPage.tsx:440` "when this webhook fires"、
`chatImagePaste.test.ts:62` "Safari/Firefox",以及 `ChatPage.tsx` / `pty-*.ts` /
`ToolsetConfigDrawer.tsx` / `SkillsPage.tsx` 里若干 "fires"/"fire" 注释。
**没有一处是端点路径。**

③ 结构化搜索。§3.2 的探针枚举了全 `web/src` 里 **171** 条端点字面量,其中无 `/api/cron/fire`。
探针不依赖 `grep` 的模式,而是把每个字符串/模板字面量都取出来判前缀,所以它能覆盖
"路径被拆成几段拼起来"以外的所有写法。**拼接式构造这一种残余可能**在本片可以排除:
§3.2 已证明 SPA 里除 `api.ts` 与 `chatImagePaste.ts` 外没有别的 fetch 调用点,
而这两个文件里的 URL 全是字面量。

**为什么"就该如此"**:这个端点在后端的公开白名单里,它的调用方是 NAS 而不是浏览器。

`hermes_cli/dashboard_auth/public_paths.py:54 @ 863e313`

```python
    # Chronos managed-cron fire webhook (NAS -> agent). NOT cookie-gated: it
    # carries its own short-lived NAS-minted JWT (purpose=cron_fire), which the
    # handler verifies as the real auth. Must bypass the dashboard auth gate so
    # the NAS relay's bearer-only callback reaches the verifier instead of a
    # 401 no_cookie. The JWT — not this allowlist — is the security boundary.
    "/api/cron/fire",
```

即便一个 dashboard 插件用 `SDK.fetchJSON("/api/cron/fire", …)` 去打它也没用:
`fetchJSON` 只会加 `X-Hermes-Session-Token` 头和 cookie,不会加 `Authorization: Bearer`,
而这个端点唯一认的就是那个 bearer JWT。

**前端的对应能力是另一条端点,而且它带 profile。** 界面上"触发一个 cron 任务"走的是
§4 那条链:`POST /api/cron/jobs/{id}/trigger?profile=<job 自己的 profile>`。
回答派工书的三问:

| 问 | 答 |
|---|---|
| 哪个页面/按钮打 `/api/cron/fire`? | **没有**。界面上最接近的是 `/cron` 页每行的闪电按钮,它打 `/api/cron/jobs/{id}/trigger` |
| 带不带 profile 参数? | **带,且必带**。`web/src/lib/api.ts:621`:`  triggerCronJob: (id: string, profile = "default") =>` 的 profile 有默认值 `"default"`,URL 里恒有 `?profile=` |
| 用户能不能选? | **不能直接选**,profile 由 job 自身携带(`web/src/pages/CronPage.tsx:485`:`function getJobProfile(job: CronJob): string {`)。但用户能把过滤器切到 `"all"` 从而在**一个列表里**看到并逐个触发**任意 profile** 的任务 |

**这一面的判定**:H-R8C-e 描述的"认证与授权之间缺一次绑定"是 `/api/cron/fire` 独有的,
**前端不参与、也无法参与**。前端那条 `/trigger` 链虽然同样能跨 profile 触发,
但它受 dashboard 会话认证管辖(§4 跳 5),而 dashboard 会话本来就是机器级管理身份
——能开 dashboard 的人本来就能改任意 profile 的配置。**所以跨 profile 在 `/trigger` 上
不是缺陷,在 `/fire` 上才是**:区别在于 `/fire` 的凭据是 per-profile 配置签发的,
却能作用于所有 profile。这条区分是本节对 H-R8C-e 的实质贡献。

### 6.2 H-R8C-f —— backup/import 在 `/system` 页,**import 有二次确认、backup 一次点击零警告**

**页面**:`web/src/pages/SystemPage.tsx`,路由 `/system`,侧栏标签 "System"(`web/src/App.tsx:214`)。
四个入口都在 "Operations" 分区的第二张卡里。

**(a) 创建备份:一次点击,无确认,无任何关于内容物的说明。**

`web/src/pages/SystemPage.tsx:1233 @ 863e313`

```tsx
                <Label>Full backup</Label>
                <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
                  <Button
                    size="sm"
                    ghost
                    prefix={<Database className="h-3.5 w-3.5" />}
                    onClick={() => void runDashboardBackup()}
                  >
                    Create backup
                  </Button>
```

`runDashboardBackup`(`web/src/pages/SystemPage.tsx:393`)直接 `await api.runBackup()`,
成功弹 "Backup started"。**没有 ConfirmDialog,没有一句话说这个 zip 里有什么。**

**(b) 下载备份:同样一次点击,无警告。** `web/src/pages/SystemPage.tsx:1254` 的
"Download backup" 按钮 → `downloadBackup()` → `api.downloadBackup(archive)` →
`GET /api/ops/backup/download`,拿到 blob 后用一个临时 `<a download>` 触发浏览器保存。
于是**从打开 dashboard 到把包含全部凭据的归档存进本机 Downloads,总共两次点击、零次确认**。

归档确实含凭据:`hermes_cli/backup.py:128` 的
`_SECRET_FILE_NAMES = {".env", "auth.json", "state.db"}` 在恢复时被特判 `chmod 0600`,
即被代码自己当作机密对待。

**(c) 恢复:有二次确认,但措辞里没有"凭据"。**

`web/src/pages/SystemPage.tsx:1328 @ 863e313`

```tsx
            <ConfirmDialog
              open={!!importConfirmTarget}
              title="Restore full Hermes backup?"
              description={`This will overwrite your current Hermes configuration, skills, sessions, and data with the contents of ${backupImportLabel(importConfirmTarget)}. This cannot be undone.`}
              destructive
              confirmLabel="Restore"
              cancelLabel="Cancel"
              onCancel={() => setImportConfirmTarget(null)}
```

对照派工书的三问:

| 问 | 答 |
|---|---|
| 哪个页面暴露 backup/import? | `web/src/pages/SystemPage.tsx`(路由 `/system`)的 Operations 分区,4 个入口:创建备份、下载备份、上传恢复、按路径恢复 |
| 有没有二次确认? | **恢复有**(一个 `destructive` 的 ConfirmDialog,两条恢复入口共用);**创建备份和下载备份都没有** |
| UI 上有没有告知「这会覆盖你的凭据」? | **没有**。确认文案枚举了四类("configuration, skills, sessions, and data"),**不含凭据/API key/`.env`/`auth.json`** 中的任何一个词。搜索面:`grep -rni 'credential|\.env\b|auth\.json|api key' web/src/pages/SystemPage.tsx` 的全部命中都落在另一张"Credential pool"卡(`:341`–`:371`、`:1145`–`:1190`),备份/恢复那张卡(`:1228`–`:1341`)里一处都没有 |

**两处附带发现**:

1. **`force=true` 是硬编码的**。`web/src/pages/SystemPage.tsx:452` 无条件传 `true`。
   这是**有意**的,而且注释交代得很清楚(`web/src/pages/SystemPage.tsx:226`:
   "the spawned `hermes import` runs non-interactively (stdin is /dev/null), so its CLI
   'Continue? [y/N]' prompt would auto-abort. The dashboard owns the consent")。
   也就是说:**CLI 那道"目标目录已有配置,确定覆盖?"的闸被前端这个对话框顶替了**
   ——顶替本身合理,但顶替物的措辞比被顶替者更弱(CLI 的原话是
   `hermes_cli/backup.py:894`:`            print("Warning: Target directory already has Hermes configuration.")`)。
2. **"按路径恢复"是一个自由文本框**。`web/src/pages/SystemPage.tsx:1307` 的
   `<Input id="import-path" …>` 只有一个 placeholder 提示,不限制目录;
   后端 `hermes_cli/web_server.py:12893`:`async def run_import(body: ImportRequest):` 也只检查
   `os.path.isfile(archive)`,不做目录约束——**与下载端点形成对照**,后者用
   `_path_is_under` 把范围锁死在 dashboard 备份目录内。

**本条的处置**:按主线定案,H-R8C-f 的后端半边(import 解包实现的"来源校验仅 basename"
那句断言)仍需一次精读、归 R11A;**前端半边由本节结清**,结论是
"入口在 `/system`;恢复有确认但文案不提凭据;创建与下载零确认零警告"。

### 6.3 H-R8C-g —— 在 `/plugins` 页,**一次点击,无确认;pip 包名可见,但不说"这改的是服务器"**

**页面**:`web/src/pages/PluginsPage.tsx`,路由 `/plugins`,侧栏标签 "Plugins"。
入口是 `MemoryProviderSetupHint` 组件(`web/src/pages/PluginsPage.tsx:150`)里的单个按钮:

`web/src/pages/PluginsPage.tsx:198 @ 863e313`

```tsx
      {needsDependencySetup ? (
        <Button
          className="w-fit uppercase"
          disabled={installing}
          onClick={onInstall}
          size="sm"
        >
          <span className="inline-flex items-center gap-2">
            {installing ? <Spinner /> : null}
            {installing ? "Installing provider dependencies" : "Install provider dependencies"}
          </span>
        </Button>
```

`onInstall` 即 `onSetupMemoryProvider()`(`web/src/pages/PluginsPage.tsx:458`)→
`api.setupMemoryProvider(provider, currentVisibleMemoryValues())` →
`POST /api/memory/providers/{name}/setup`。**没有 ConfirmDialog。**

对照派工书的三问:

| 问 | 答 |
|---|---|
| 哪个页面触发它? | `web/src/pages/PluginsPage.tsx`(路由 `/plugins`)的记忆 provider 区块;按钮文案 "Install provider dependencies" |
| 有没有二次确认? | **没有**,单次点击直接发起 |
| UI 有没有把「这会改你本机的 Python 环境」说清楚? | **部分。说了装什么,没说装到哪、也没说是谁的机器。** |

**"部分"的具体成色,这是本节要给准的**:

- **装什么:说了。** 按钮上方会把 manifest 声明的 pip 包逐个渲染成代码片
  (`web/src/pages/PluginsPage.tsx:242` 起的 "Python dependencies" 区块),
  外部依赖的 `install` / `check` 命令也以**可复制的命令块**呈现
  (`SetupCommandBlock`,`web/src/pages/PluginsPage.tsx:82`)。执行后每一步的
  `result.command` 与 stdout/stderr 都回显(`MemoryProviderSetupResults`,`:110`)。
- **装到哪:没说。** 全部说明性文案只有一句
  `web/src/pages/PluginsPage.tsx:194`:`          ? "Finish these setup steps before Hermes can activate this provider."`,
  和加载态的 "Running provider setup. This may take a minute…"。
  **没有任何一句提到 Python 环境、site-packages、或"服务器"。**
- **谁的机器:没说,而这一点在 dashboard 场景下不是措辞洁癖。** dashboard 可以被远程访问
  (`--host` 非 loopback 是被支持的部署形态),此时"本机"是**服务端**,不是浏览器所在的机器。
  界面把这些命令渲染成"你可以复制去跑"的样子(旁边就是 `CopyButton`),
  会让人读成"这是给我抄的",而按钮的实际语义是"让服务器去跑"。

**一处比移交项原文更重的发现(后端,超出本片范围,如实标注)**:移交项与主线定案都把这条
描述成"跑 pip 安装",而 `_install_memory_provider_setup`(`hermes_cli/web_server.py:5579`)
在 pip 之后还会跑 `_install_memory_provider_external_dependencies`(`:5468`),
后者对 manifest 里的 `check` / `install` **字符串**做 `shlex.split()` 后交给
`_run_setup_command`(`:5355`,`shell=False`)执行。
`shell=False` 挡掉了 shell 元字符注入,**但没有挡住 argv 本身**——manifest 可以直接写
`bash -c "..."`。也就是说这条端点执行的**不只是 pip**,而是 manifest 声明的任意 argv。
主线的 ■-R10-01 定性("install_specs 把信任推给了 manifest,而这条面上的 manifest 是可写的")
方向不变,但**严重度的上界比"任意 PyPI 包名 + 版本范围"高**:
`_spec_is_safe` 那套仔细的卫生检查只作用在 pip 那一半。
**这一段是我在追前端可达性时顺带读到的后端代码,不属于 G 片的 L2 范围,
本轮没有为它做完整取证(没有读 `_command_result` 的全部分支,也没有实跑),
建议 R11A 在给 ■-R10-01 定级时把它纳入。**

---

## §7 发现清单

### ■-G-01 —— 会话导出是全 SPA 唯一一处手搓认证、且丢掉了反向代理前缀

`web/src/pages/SessionsPage.tsx:1470 @ 863e313`

```tsx
        const res = await fetch(api.exportSessionUrl(id), {
          credentials: "include",
          headers: {
            "X-Hermes-Session-Token":
              (window as unknown as { __HERMES_SESSION_TOKEN__?: string })
                .__HERMES_SESSION_TOKEN__ ?? "",
          },
        });
```

`api.ts` 专门为"非 JSON 响应(上传 / blob 下载)"提供了 `authedFetch`
(`web/src/lib/api.ts:246` 起的 docstring 明写这个用途),而且 `authedFetch` 会
`fetch(\`${BASE}${url}\`, …)` 加上 base path。这里绕开了它:

1. **base path 丢失**。`api.exportSessionUrl` 只返回 `/api/sessions/<id>/export`(相对根),
   没有 `${BASE}`。dashboard 挂在 `https://host/hermes/` 这类前缀下时,
   这个请求会打到 `https://host/api/sessions/...`,而不是 `https://host/hermes/api/...`。
   这个部署形态是被明确支持并在 `web/src/lib/api.ts:3` 的注释里详细描述过的。
2. **手抄了 token 逻辑**。`web/src/plugins/registry.ts:131` 的注释把
   "plugins never read window.__HERMES_SESSION_TOKEN__ directly" 当成一条纪律,
   而 SPA 自己这里破了它。

对照组:同一批"下载 blob"的需求里,`web/src/pages/SystemPage.tsx:424` 的备份下载
走的就是 `api.downloadBackup(archive)` → `authedFetch`,是正确写法。
**这不是风格问题,是一个在特定部署形态下必然 404 的 bug。**
(未实跑复现——需要起一个带 `X-Forwarded-Prefix` 的反向代理;本条是静态对读。)

### ■-G-02 —— `web/src/lib/fuzzy.ts` 的注释声称本包没有测试运行器,而它有

`web/src/lib/fuzzy.ts:14 @ 863e313`

```ts
// This is a logically identical copy of ui-tui/src/lib/fuzzy.ts (only prettier
// formatting differs); keep the two in sync. The TUI copy carries the vitest
// suite (this `web` package has no test runner), so behavioural changes should
// be validated there.
```

`web/package.json` 有 `"test": "vitest run"` 与 `"check": "npm run typecheck && npm run test && npm run lint"`,
`web/vitest.config.ts` 存在,`web/src/` 下有 **27 个** `*.test.ts(x)`:

```verify
cd /home/user/hermes-agent && find web/src -name '*.test.ts*' | wc -l
```

```text
27
```

危害不在于注释过时,而在于它给出的**行动指令**基于一个假前提:
"behavioural changes should be validated there(在 TUI 包里验)"。
一个改 `fuzzy.ts` 的人照做,就会跳过本包已经存在的测试基建。

### ■-G-03 —— 插槽注册表的三张名单两两不等

三面的差集见 §3.6 的探针输出。归纳:

| | 声明(`slots.ts`) | 实渲染 | 文档(`extending-the-dashboard.md`) |
|---|---|---|---|
| 数量 | 30 | 31 | 28 |
| `sidebar` / `footer-left` / `footer-right` | 有 | **无** | 有 |
| `files:*` / `models:*` | **无** | 有 | 无 |
| `plugins:*` | 有 | 有 | **无** |

`web/src/plugins/slots.ts:60` 的那句 `/** Slot locations the built-in shell renders.` 是一条断言,
而 `sidebar` / `footer-left` / `footer-right` 三个名字下面**没有任何 `<PluginSlot>`**:
`web/src/components/SidebarFooter.tsx` 全文 41 行没有 `PluginSlot`;
`layoutVariant`(含 `"cockpit"`)在 `web/src/App.tsx:486` 之后只被写成一个
`data-layout-variant` 属性,没有条件渲染任何侧栏。
一个照文档写 `registerSlot("x", "footer-left", C)` 的插件作者,拿到的是**静默无效果**。

### ■-G-04 —— SRI 注释声称的威胁模型("compromised plugin server")不被它实现的机制覆盖

见 §5.4 引用的 `web/src/plugins/usePlugins.ts:130` 那段注释。
`integrity` 哈希来自 **manifest**,manifest 来自 `GET /api/dashboard/plugins`;
bundle 来自 `<BASE>/dashboard-plugins/<name>/<entry>`。
两者**同源、同一个 dashboard 服务器**(`manifest.entry` 被插值进路径中段,
写成绝对 URL 也逃不出这个前缀)。因此一个"compromised plugin server"可以同时改哈希和包体,
SRI 拦不住;它实际能防的是**能篡改 bundle 响应但改不了 manifest 响应**的攻击者
——在同一条 TLS 连接、同一个 host 的前提下,这个攻击者模型很难成立。
**判定**:机制本身无害(可选加固,不影响未声明时的行为),但注释把它的保护范围说宽了。
标 ■ 而不是 ▲,因为出错的是源码注释而不是仓库地图。
(本条是静态推理,未构造 PoC。)

### ▲-G-01 —— `website/docs` 的插槽目录与"only renders"那句话与代码矛盾

`website/docs/user-guide/features/extending-the-dashboard.md:621 @ 863e313`

> The shell only renders `<PluginSlot name="..." />` for the slots above. Additional names are accepted by the registry for nested plugin UIs — a plugin can expose its own slots via `SDK.components.PluginSlot`.

按 CLAUDE.md 的"整句/整段一并判定"要求,这句话管的是它上面那两张表(28 个名字)。
代码实渲染 31 个,其中 **6 个不在表里**(`files:top`、`files:bottom`、
`models:top`、`models:bottom`、`plugins:top`、`plugins:bottom`)——所以
"only renders … for the slots above" 字面为假。同一节的 Shell-wide 表还把
`sidebar` / `footer-left` / `footer-right` 列为会渲染的位置,而代码一个都不渲染。
**两个方向都错,记一条 ▲。**

### ▲-G-02 —— `web/README.md` 的目录结构块描述的是一个不存在的代码库

`web/README.md:41 @ 863e313`

```
src/
├── components/ui/   # Reusable UI primitives (Card, Badge, Button, Input, etc.)
├── lib/
│   ├── api.ts       # API client — typed fetch wrappers for all backend endpoints
│   └── utils.ts     # cn() helper for Tailwind class merging
├── pages/
│   ├── StatusPage   # Agent status, active/recent sessions
│   ├── ConfigPage   # Dynamic config editor (reads schema from backend)
│   └── EnvPage      # API key management with save/clear
```

三处与代码矛盾:① `web/src/components/ui/` **不存在**(`ls` 报 No such file or directory),
UI 原语现在从外部包 `@nous-research/ui` 导入;② `StatusPage` **在全 `web/` 里零命中**
(`grep -rn 'StatusPage' web/ --include='*.ts*'` 无输出);
③ 实际有 19 个页面,这里列了 3 个。

### ▲-G-03 —— `web/README.md` 给出的开发命令用了一个不存在的子命令

`web/README.md:14 @ 863e313`

```
# Start the backend API server
cd ../
python -m hermes_cli.main web --no-open
```

CLI 没有 `web` 子命令。**负结论的搜索面**:对全仓 `*.py` 抽取
`add_parser(` 的第一个字符串字面量(含"名字写在下一行"的多行写法)与全部
`aliases=` 列表,得到约 400 个子命令名,其中**没有 `web`**;
浏览器 UI 的子命令是 `dashboard`,无浏览器的是 `serve`,两者定义在
`hermes_cli/subcommands/dashboard.py:101` 与 `:136`,共享
`_add_server_runtime_args`。README 后文用的又是正确的 `hermes dashboard`,
所以这是一处遗留而非全篇失准。

### ◇-G-01 —— 前端有一条界面到不了的端点:技能 hub 卸载

见 §3.5 末段。`POST /api/skills/hub/uninstall` 在客户端有方法
(`web/src/lib/api.ts:1294`),在 SPA 里**没有任何调用方**,技能页也没有卸载按钮。
文档与界面都没提"dashboard 能卸载 hub 技能",而这条能力在客户端里躺着,
且经 `SDK.api` 对插件可达。

### ◇-G-02 —— 仓库里并存两个 `ConfirmDialog`,只有 3 处用本地那个

`web/src/components/ConfirmDialog.tsx`(122 行,本地实现,默认按钮文案硬编码英文
"Cancel"/"Confirm",不接 i18n)只被 3 个文件导入:
`web/src/components/ModelReloadConfirm.tsx:1`、`web/src/components/ModelPickerDialog.tsx:7`、
`web/src/pages/ModelsPage.tsx:38`。其余 8 处(`App.tsx`、`ConfigPage`、`SystemPage`、
`PluginsPage`、`OAuthProvidersCard`,以及经 `DeleteConfirmDialog` 转调的 7 个页面)
用的是设计系统的 `@nous-research/ui/ui/components/confirm-dialog`。
后果是**同一个 dashboard 里两种确认框的行为与本地化不一致**;
"换模型"这条路径上的确认框恰好是不走 i18n 的那一个。

### ◇-G-03 —— 前端认的公开端点里有两个会在登录前就被拉取

`usePlugins` 与 `ThemeProvider` 在应用挂载时就分别打 `GET /api/dashboard/plugins`
与 `GET /api/dashboard/themes`,而这两条都在 `PUBLIC_API_PATHS` 里
(`hermes_cli/dashboard_auth/public_paths.py:51`–`:52`)。这是**前端设计与后端白名单的一处耦合**:
SPA 需要在拿到会话之前就完成插件与主题的引导。代价是未认证的访问者能读到
"这台 agent 装了哪些 dashboard 插件"。白名单的 docstring 自陈标准是
"safe to expose to … anyone who happens to `curl` the hostname",
插件清单是否满足这条标准,本轮不下判断——记为代码有、文档未讨论。

### ◎-G-01 —— 文档的图标清单成立但少列 3 个

`website/docs/user-guide/features/extending-the-dashboard.md:491` 写
"Currently mapped: " 后面列了 20 个 Lucide 图标名。代码的 `ICON_MAP`
(`web/src/App.tsx:224`)有 **23** 个;列出的 20 个**全部为真**,
缺的是 `Cpu`、`FolderOpen`、`Users`。字面为真,故记 ◎ 不记 ▲。

---

## §8 未取证与推定(明确列出没验的东西)

1. **一次运行时验证都没做。** 本片全部结论来自静态阅读。派工书禁止 `npm install` / `vitest`,
   容器里也没有已安装的 `web/node_modules`,所以既没跑过 dev server,也没跑过 27 个前端测试。
   ■-G-01 的"反向代理下会 404"、■-G-04 的"SRI 拦不住"都属于**静态推理,无复现**。
2. **`web/src/pages/` 的 19 个页面只读到了接口面**:api 调用集合、路由挂载、
   关键交互处的 handler。**渲染细节、状态机分支、表单校验没有逐个读**——这是 L2 的设定,
   但要说清楚:例如 `SessionsPage`(2200 行)我只读了它的 api 调用面与导出那一段。
3. **`web/src/i18n/` 的 17 个翻译文件没有逐键比对。** 我验证了文件数、`Locale` 联合、
   `LOCALE_META`、`defineLocale` 的唯一消费者、以及 `en.ts` 的叶子键数(651),
   **没有**检查 16 个完整语言文件是否真的键键齐全(TypeScript 的 `Translations` 类型
   会强制这一点,所以我推定齐全,但这是**推定**,依据是类型而不是实测)。
4. **`web/src/themes/context.tsx`(615 行)只读了四条主线**(CSS 变量、customCSS、
   字体注入、布局变体),调色板摊平的具体键名映射没有逐条核。
5. **`web/src/index.css`(255 行)只读了前 40 行**(导入顺序与字体注册),其余是样式规则,
   按 L2 判为不必逐行读。
6. **一处怀疑但没能验证**:`web/package.json` 的 `"typecheck": "tsc -p . --noEmit"`
   指向 `web/tsconfig.json`,而后者是 `files: []` + `references` 的 solution 风格配置。
   `tsc -p`(不带 `-b`)对这种配置是否真的会检查被引用的项目,我**没有条件实测**
   (不能装依赖、不能跑 tsc)。若不会,则 `npm run typecheck` 与 `npm run check` 中的
   typecheck 段是空转,而 `npm run build` 用的是正确的 `tsc -b`。
   **本条不计入 §7 的记号,因为它没被验证过。** 留给能跑 npm 的一轮。
   另注:`web/vitest.config.ts` 不在任何一个 tsconfig 的 `include` 里
   (`tsconfig.app.json` 收 `src`,`tsconfig.node.json` 只收 `vite.config.ts`),
   所以它无论如何都不被类型检查——这一点是确定的。
7. **后端只在为回答 §6 而必要时读了**(`web_routers/cron.py`、`public_paths.py`、
   `web_server.py` 的 backup/import/memory-setup 几段、`backup.py` 的两处常量)。
   没有系统读后端,§6.3 末尾那条 external-dependencies 发现因此标注为"顺带读到、未完整取证"。
8. **`git status --porcelain` 在交付前复核为空**,基线未被修改;本轮**没有安装任何包**。

---

## §9 L2 判据自评

| 判据 | 自评 | 说明 |
|---|---|---|
| 1. 点名到位 | **做到** | §2 逐个列出 131 个全路径 + 一句话角色,分 11 组,组内不省略;末尾按组求和 = 131,与 `G.txt` 一致 |
| 2. 接缝穷举 | **做到** | 10 个接缝全部逐项列全:HTTP 端点 166(+5)、WS 4、路由 19+1、导航 17、api 方法 166、插槽 30/31/28、SDK 导出面、语言 17、主题 8 / 字体 14、profile 前缀 17。其中 4 个给了可重跑的 ` ```verify ` 命令(两个落库成 `data/r10/probes/` 下的探针) |
| 3. 一条端到端链走通 | **做到** | §4:Cron「立即触发」8 跳,从按钮 JSX → 页面 handler → api 客户端 → `withManagementProfile` → `fetchJSON` 头注入 → FastAPI 认证中间件 → 路由 → `_trigger_cron_job_sync` → 回到 toast 与列表刷新,逐跳带锚点,跨到了 Python 内核 |
| 4. 两处以上逐字取证 | **做到** | 15 个围栏块是逐字源码摘录(api.ts 4、App.tsx 1、CronPage 1、SystemPage 2、PluginsPage 1、SessionsPage 1、fuzzy.ts 1、usePlugins 1、README 2、Python 侧 4) |
| 5. 至少一条记号 | **做到** | ■ 4、▲ 3、◇ 3、◎ 1,共 11 条,逐条带锚点 |

**没做到的部分,如实说**:判据 2 里"api 方法 166 个"我给了总数与页面映射的机械枚举,
但**没有把 166 个方法名逐个抄进表**——它们与 §3.1 的 166 条端点一一对应度很高,
逐个再列一遍是同一信息的第二份拷贝;判据 2 的字面要求是"逐项列全",
所以这里记一条**部分满足**:端点面列全了,方法名面只给了枚举命令和差集分析(1 个无调用方)。

---

## §10 移交

| ID | 锚点 + 摘录 | 一句话现象 | 建议去向 |
|---|---|---|---|
| **H-R10G-a** | `web/src/pages/SessionsPage.tsx:1470`:`        const res = await fetch(api.exportSessionUrl(id), {` | 全 SPA 唯一一处绕过 `authedFetch` 的网络调用,丢掉了 `${BASE}` 反向代理前缀,在 URL-prefix 部署下导出会 404;需要一次带 `X-Forwarded-Prefix` 的运行时复现来定级 | R11A(与 dashboard 后端欠账同轮) |
| **H-R10G-b** | `hermes_cli/web_server.py:5468`:`def _install_memory_provider_external_dependencies(` | `/api/memory/providers/{name}/setup` 除 pip 外还会 `shlex.split()` 执行 manifest 的 `check`/`install` 命令(`shell=False`,但 argv 可为 `bash -c …`),`_spec_is_safe` 的卫生检查只覆盖 pip 那一半;主线 ■-R10-01 定级时应纳入 | R11A |
| **H-R10G-c** | `web/package.json:12`:`    "typecheck": "tsc -p . --noEmit",` | 指向 `files: []` + references 的 solution tsconfig,疑为空转(`build` 用的是正确的 `tsc -b`);本轮无法实测,需要一个能跑 npm 的轮次确认 | 任何能跑前端工具链的一轮 |
| **H-R10G-d** | `web/src/plugins/slots.ts:60`:` *  these in their manifest's \`slots\` field get wired in automatically.` | 插槽三张名单(声明 30 / 实渲染 31 / 文档 28)两两不等,`sidebar`/`footer-left`/`footer-right` 三个名字文档与声明都有、代码零渲染 | R11 复盘(与 ▲ 计数一起处理) |
