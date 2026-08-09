# r10b 片A · 聊天输入区 —— composer、右栏与会话瓦片(底稿)

> 层:**L2(结构级理解 = 读接口面,不读实现体;但接口面不许抽样)**
> 范围:`data/r10b/slices/A.txt`,**84 文件 / 18,804 行**,全部在
> `/home/user/hermes-agent/apps/desktop/src/app/chat/` 下。
> 溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于代码块之前。
> 术语先锚一次:**composer** = 聊天输入区那一整块(输入框 + 附件 + 控件 + 状态栈);
> **chip / 药丸** = contentEditable 里那一颗不可编辑的引用块(`@file:…`、`/skill`);
> **trigger / 触发** = 敲 `@` `/` `:` 后弹出的补全气泡;**tile / 瓦片** = 把另一个会话
> 当成一个"窗格"贴在主聊天旁边;**nanostores atom** = 该项目用的极小状态容器,
> `$` 前缀是它的命名约定;**assistant-ui(AUI)** = 上游聊天 UI 库,本仓库在它之上定制。

---

## 0. 本片范围与逐文件点名(判据 1)

### 0.0 机械口径

```verify
cd /home/user/hermes-agent
wc -l $(cat /home/user/hermes-study/data/r10b/slices/A.txt) | tail -1
# => 18804 total
python3 /home/user/hermes-study/data/r10b/probes/probe_a_seams.py \
    /home/user/hermes-agent /home/user/hermes-study/data/r10b/slices/A.txt
```

探针实测输出(本轮):

```text
slice files            : 84
slice lines            : 18804
top-level `export` decls: 250
ChatBarProps fields    : 22
COMPOSER_AREAS keys    : 8
focus-bus event names  : 6
SessionView fields     : 13
PaneMirror<T> fields   : 15
data-slot values       : 13
gateway RPC methods    : 8
store modules imported : 40
store symbols imported : 180
composer hook modules  : 24
```

### 0.1 `composer/` 顶层(26 文件)—— 输入区本体

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/src/app/chat/composer/index.tsx` | **协调器 `ChatBar`**(1,310 行):把下面 24 个 hook 串成一个输入区,自己只留 DOM 事件桥接与布局 |
| `apps/desktop/src/app/chat/composer/types.ts` | 对外 props 契约:`ChatBarProps`(22 字段)、`ChatBarState`、`VoiceActivityState` |
| `apps/desktop/src/app/chat/composer/contrib.ts` | 插件贡献面:`COMPOSER_AREAS`(8 个)+ middleware / attachment / microAction 三种数据贡献 |
| `apps/desktop/src/app/chat/composer/scope.tsx` | `ComposerScope` —— "这一个 ChatBar 是谁"(主聊天 vs 某个瓦片),React context |
| `apps/desktop/src/app/chat/composer/focus.ts` | **外部 → composer 的事件总线**:聚焦 / 插入文本 / 插入 chip / 代提交 / 语音开关 / 模型菜单,共 6 个 window 自定义事件 |
| `apps/desktop/src/app/chat/composer/text-utils.ts` | 触发检测(`@` `/` `:` 四条正则)+ 剪贴板图片抽取 + `openDirectiveScope` |
| `apps/desktop/src/app/chat/composer/rich-editor.ts` | contentEditable 的序列化层:chip DOM ↔ `@kind:value` 纯文本、caret 定位、Range 编辑原语(774 行) |
| `apps/desktop/src/app/chat/composer/slash-refs.ts` | 对"整段到货的文本"(粘贴/恢复草稿/撤销)识别 `/command`,让水化出的药丸与打字路径一致 |
| `apps/desktop/src/app/chat/composer/path-refs.ts` | 裸 `@a/b` → 定型 `@file:`/`@folder:`(打空格时、提交时各一次) |
| `apps/desktop/src/app/chat/composer/url-refs.ts` | 裸链接 → `@url:` chip;句末标点与不配对右括号会被剥出来留在正文 |
| `apps/desktop/src/app/chat/composer/inline-refs.ts` | 往编辑器里插入一批 chip(拖放文件、拖会话生成 `@session:`),并算好前后空格 |
| `apps/desktop/src/app/chat/composer/undo-history.ts` | 自有撤销栈(纯文本 + caret 偏移的快照环),含 ⌘Z/⌘⇧Z/Ctrl+Y 判定 |
| `apps/desktop/src/app/chat/composer/composer-utils.ts` | 常量与纯函数:断点像素、草稿落盘防抖、补全接受规则、`QueueEditState`、跨会话落盘守卫 |
| `apps/desktop/src/app/chat/composer/attachments.tsx` | 附件药丸列表 + 单个药丸(图片走 lightbox,其它走预览栏) |
| `apps/desktop/src/app/chat/composer/completion-drawer.tsx` | 补全抽屉的外壳样式与空态(`COMPLETION_DRAWER_CLASS`),被帮助抽屉复用 |
| `apps/desktop/src/app/chat/composer/context-menu.tsx` | "+" 附加菜单:文件/文件夹/图片/粘贴图片/加 URL/提示片段 + `composer.attachments` 贡献行 |
| `apps/desktop/src/app/chat/composer/controls.tsx` | 右侧控件行:模型药丸 → 听写 → 自动朗读 → 唤醒词 → (排队) → 发送/语音主按钮;语音会话时整行换成 `ConversationPill` |
| `apps/desktop/src/app/chat/composer/directive-actions.tsx` | 悬停某个 chip 时浮出的动作药丸(打开链接/打开会话),动作表与已发消息共用 |
| `apps/desktop/src/app/chat/composer/drop-affordance.ts` | 2 行:拖放高亮的两个 class 常量 |
| `apps/desktop/src/app/chat/composer/help-hint.tsx` | 输入 `?` 时的快捷键小抄抽屉(6 个常用命令 + 8 行热键) |
| `apps/desktop/src/app/chat/composer/micro-actions.tsx` | 贡献出来的"微动作"药丸条(输入区上方悬浮),自己带 in-flight 锁 |
| `apps/desktop/src/app/chat/composer/model-pill.tsx` | 模型选择药丸;按本 surface 的 `SessionView` 显示,支持 `composer.modelPicker` 热键 |
| `apps/desktop/src/app/chat/composer/queue-panel.tsx` | 排队消息面板(展开/折叠、恢复、发送、编辑、删除);被"停"过就强制展开 |
| `apps/desktop/src/app/chat/composer/trigger-popover.tsx` | 补全列表本体:`@` `/` 共用一种行,`:` emoji 单独一种 |
| `apps/desktop/src/app/chat/composer/url-dialog.tsx` | "Add URL" 对话框 |
| `apps/desktop/src/app/chat/composer/voice-activity.tsx` | 录音活动条(计时 + 电平柱)与播放活动条 |

### 0.2 `composer/status-stack/`(4 文件)—— 输入区上方的状态栈

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/src/app/chat/composer/status-stack/index.tsx` | 状态栈容器:按类型分组渲染子代理 / 后台进程 / 预览 / 队列,空则整块消失 |
| `apps/desktop/src/app/chat/composer/status-stack/coding-row.tsx` | 常驻的 git 上下文行(分支、±、ahead/behind)+ worktree/分支切换入口 |
| `apps/desktop/src/app/chat/composer/status-stack/status-row.tsx` | 单条状态行(子代理 / 后台任务)的渲染与停止/清除动作 |
| `apps/desktop/src/app/chat/composer/status-stack/preview-row.tsx` | 单条"检测到的可预览产物"行,开/关预览标签页 |

### 0.3 `composer/hooks/`(24 文件)—— 被拆出来的引擎

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/src/app/chat/composer/hooks/use-composer-draft.ts` | **草稿引擎**:DOM+`draftRef` 为真源、AUI 只看粗粒度边沿;含按会话 stash/restore、防抖落盘、pagehide 兜底 |
| `apps/desktop/src/app/chat/composer/hooks/use-composer-submit.ts` | **提交引擎**:一棵决策树(存队列编辑 / busy 下的斜杠直发 / steer / 排队 / 排空 / 发送 / 停止)+ 失败回填原语 |
| `apps/desktop/src/app/chat/composer/hooks/use-composer-queue.ts` | **队列引擎**:每会话队列、就地编辑、排空锁、手动发送、有界自动排空 |
| `apps/desktop/src/app/chat/composer/hooks/use-composer-trigger.ts` | **补全引擎**:触发检测 → 适配器取项 → 选中态 → 把选中项落成 chip;含 Tab 下钻 / Backspace 上钻 |
| `apps/desktop/src/app/chat/composer/hooks/use-at-completions.ts` | `@` 补全:走网关 `complete.path`,带 cwd+session 的缓存键;无网关时退化为 6 个 starter 行 |
| `apps/desktop/src/app/chat/composer/hooks/use-slash-completions.ts` | `/` 补全:`commands.catalog` + `complete.slash`;`/skin` 与 `/resume` 由客户端就地作答 |
| `apps/desktop/src/app/chat/composer/hooks/use-emoji-completions.ts` | `:shortcode` 补全,离线 emojibase 索引,首次触发才 lazy-load |
| `apps/desktop/src/app/chat/composer/hooks/use-live-completion-adapter.ts` | 三个补全源共用的取数壳:60ms 防抖、命中缓存跳过防抖与 loading、token 防乱序、epoch 失效 |
| `apps/desktop/src/app/chat/composer/hooks/use-composer-undo.ts` | 撤销栈的 React 侧:记录点、应用快照、认领 document 级 `beforeinput` 的 historyUndo/Redo |
| `apps/desktop/src/app/chat/composer/hooks/use-composer-drop.ts` | 拖放到输入区:按来源二分(应用内 → inline ref / OS 拖入 → 上传通道) |
| `apps/desktop/src/app/chat/composer/hooks/use-composer-metrics.ts` | 尺寸引擎:堆叠 vs 单行布局判定 + 把实测高度以 8px 分桶写进本 surface 的 CSS 变量 |
| `apps/desktop/src/app/chat/composer/hooks/use-composer-popout.ts` | 弹出引擎:按布局 zone 存"停靠/浮动"意图,按各自 rect 夹取位置 |
| `apps/desktop/src/app/chat/composer/hooks/use-popout-drag.ts` | 弹出的指针手势:向上撕出、长按拖动、底部中央释放回停靠、停靠接近度 |
| `apps/desktop/src/app/chat/composer/hooks/use-composer-voice.ts` | 语音引擎总入口:按住说话的听写、完整语音会话、自动朗读三者的编排 |
| `apps/desktop/src/app/chat/composer/hooks/use-voice-conversation.ts` | 语音会话状态机(idle/listening/transcribing/thinking/speaking)+ 打断结算 |
| `apps/desktop/src/app/chat/composer/hooks/use-voice-recorder.ts` | 一次性听写:录 → 转写 → 把文本插进草稿 |
| `apps/desktop/src/app/chat/composer/hooks/use-mic-recorder.ts` | 底层麦克风句柄:start/stop/cancel + 电平 + 7 种失败文案 |
| `apps/desktop/src/app/chat/composer/hooks/use-auto-speak-replies.ts` | 纯 TTS 自动朗读:只读最新一条已完成回复,和播放态互斥,多窗口靠 `ownsAmbientCue` 抢一次 |
| `apps/desktop/src/app/chat/composer/hooks/use-composer-branch.ts` | 分支 / worktree 交接:草稿随新会话走 |
| `apps/desktop/src/app/chat/composer/hooks/use-composer-esc-cancel.ts` | 焦点不在输入框时的全局 Esc 停止(只有 active 的那个 composer 响应) |
| `apps/desktop/src/app/chat/composer/hooks/use-composer-placeholder.ts` | 占位文案:静息 / 重连中 / 启动中,只在真正换会话时重掷 |
| `apps/desktop/src/app/chat/composer/hooks/use-composer-popout.ts` 之外的 `apps/desktop/src/app/chat/composer/hooks/use-composer-url-dialog.ts` | Add URL 对话框的开合与提交 |
| `apps/desktop/src/app/chat/composer/hooks/use-micro-actions.ts` | 把注册的微动作 provider 解析成本会话的药丸集合并发布到 store |
| `apps/desktop/src/app/chat/composer/hooks/use-status-presence.ts` | 三个按会话的 feed 合成一个布尔"有没有状态栈",避免逐条变更重渲染 ChatBar |

### 0.4 `chat/` 根(19 文件)—— 聊天 surface 与瓦片

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/src/app/chat/index.tsx` | `ChatView`:一个完整聊天 surface(头部 + 提示浮层 + 运行时边界 + Thread + ChatBar);主会话与瓦片共用 |
| `apps/desktop/src/app/chat/session-view.tsx` | `SessionView`:一个 surface 从 store 的哪一片读(13 个 atom),主会话是"第一个 tab"而非特权体 |
| `apps/desktop/src/app/chat/session-tile.tsx` | 会话瓦片:构造 tile 的 `SessionView` + `ComposerScope`,挂同一棵 `ChatView`;含关闭确认、tab 菜单、布局重置收拢 |
| `apps/desktop/src/app/chat/session-tile-actions.ts` | 瓦片的动作集(submit/slash/cancel/steer/edit/reload/restore),写回 wiring 缓存而非全局 atom |
| `apps/desktop/src/app/chat/session-drag.ts` | 会话拖拽的**解析器**:tab 栏 → 堆叠 / 边缘 → 分屏 / 中央或输入区 → 插 `@session` chip |
| `apps/desktop/src/app/chat/pane-mirror.ts` | 把一个响应式 tile 列表镜像成布局树窗格贡献;会话/路由/预览三种瓦片共用这套记账 |
| `apps/desktop/src/app/chat/route-tile.tsx` | 整页视图当窗格(Capabilities / Messaging / Artifacts + 插件页) |
| `apps/desktop/src/app/chat/preview-tile.tsx` | 每个预览标签页当窗格;并让 store 选中态与布局树的 active 窗格互相跟随 |
| `apps/desktop/src/app/chat/close-tab.ts` | ⌘W 的四级优先:终端 → 聚焦聊天 zone 的 tab → 工具面板 tab → 主 tab(清空为新草稿) |
| `apps/desktop/src/app/chat/runtime-repository.ts` | `ChatMessage[]` → AUI 消息仓库,WeakMap 身份缓存 + 工具消息合并缓存 |
| `apps/desktop/src/app/chat/transcript-window.ts` | 交给 AUI 的转录**窗口**上限,按渲染权重(非条数)计budget,并对齐分支组边界 |
| `apps/desktop/src/app/chat/thread-loading.ts` | 两个纯函数:最后一条可见消息是否用户发的、加载态取 `session`/`response`/无 |
| `apps/desktop/src/app/chat/surface-vars.ts` | 把实测高度写到**本 surface 根元素**而不是 `:root`(多 surface 同屏时的正确性前提) |
| `apps/desktop/src/app/chat/scroll-to-bottom-button.tsx` | 浮动"回到底部";有审批待处理时变成"需要审批"药丸 |
| `apps/desktop/src/app/chat/session-status-dot.tsx` | 会话状态点(需输入/工作中/停滞/后台/未读),与侧边栏行共用同一原语 |
| `apps/desktop/src/app/chat/profile-tag.tsx` | 归属 profile 的小色块(多 profile 时才显示) |
| `apps/desktop/src/app/chat/chat-drop-overlay.tsx` | 文件/会话拖到聊天区时的全幅提示层(纯视觉,`pointer-events-none`) |
| `apps/desktop/src/app/chat/chat-swap-overlay.tsx` | 网关切换 profile 时盖在会话上的盲文 spinner 层 |
| `apps/desktop/src/app/chat/perf-probe.tsx` | 开发用性能探针:React Profiler 采样 + `window.__PERF_DRIVE__` 合成流/转录/右栏场景 |

### 0.5 `chat/hooks/`(2 文件)

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/src/app/chat/hooks/use-composer-actions.ts` | 附件动作总集:选文件/文件夹/图片、粘贴图片、拖入落地、上传、`image.detach`;`DroppedFile` 与 `HERMES_PATHS_MIME` 也定义在这里 |
| `apps/desktop/src/app/chat/hooks/use-file-drop-zone.ts` | "整片区域都能放"的原生 DnD 区:深度计数 + Esc 中止 + 吞掉被中止的 drop |

### 0.6 `chat/right-rail/`(9 文件)—— 预览栏

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/src/app/chat/right-rail/index.ts` | 1 行:re-export `PreviewTilePane` |
| `apps/desktop/src/app/chat/right-rail/preview.tsx` | 预览窗格薄壳:从 `$previewTabs` 取 target,交给 `PreviewPane` |
| `apps/desktop/src/app/chat/right-rail/preview-pane.tsx` | 预览主体:`<webview>` 生命周期、加载错误态、控制台高度、DevTools 句柄注册、页面读取器注册 |
| `apps/desktop/src/app/chat/right-rail/preview-file.tsx` | 本地文件预览:渲染/源码/diff 三态切换、Shiki 高亮、定行窗口、就地编辑与保存 |
| `apps/desktop/src/app/chat/right-rail/preview-artifact.tsx` | artifact 预览:从注册表实时读内容,带版本步进 |
| `apps/desktop/src/app/chat/right-rail/preview-console.tsx` | 预览控制台面板 + 4 个可测纯函数(压缩 URL、格式化日志行、贴底判定、高度夹取) |
| `apps/desktop/src/app/chat/right-rail/preview-console-state.ts` | 每个预览标签页一份的控制台状态工厂(200 条环形日志、选中集、高度、开合) |
| `apps/desktop/src/app/chat/right-rail/preview-strip-tools.tsx` | 预览的 tab 栏字形按钮(控制台 / DevTools)与它们的跨渲染状态 |
| `apps/desktop/src/app/chat/right-rail/preview-reader.ts` | `read_preview` 工具的取数窗口:按 tabId 注册页面读取器,给模型的文本上限 24,000 字符 |

**点名完成度:26 + 4 + 24 + 19 + 2 + 9 = 84,与清单一致。**

---

## 1. 这一簇解决什么问题

一个 agent harness 的桌面输入区,表面上是"一个多行文本框加一个发送键"。这一片 18,804 行
在解决的,其实是四类**别处解决不了**的问题:

1. **打字必须便宜。** 一次会话的转录可能几千条消息,流式增量每秒约 30 次替换
   `$messages`。如果输入框的每次按键都进 React state,整个聊天外壳(头部、状态栈、
   控件行)就会跟着重渲染。这一片的答案是**分离真源**:文字活在 contentEditable 的
   DOM 与一个 `draftRef` 里,React 只订阅"空↔非空"这类粗粒度边沿。
2. **引用必须是结构化的,而不是一串路径文本。** 用户敲 `@src/`、拖一个文件、粘一个
   链接、选一个 `/skill` —— 最终交给网关的必须是 `@file:\`路径\`` 这种可解析的定型引用。
   于是有了 chip(不可编辑的 span,`data-ref-text` 携带原文)与三条"定型"通道
   (打空格时、粘贴时、提交时)。
3. **消息不能丢。** 会话切换、网关拒绝、重载、崩溃、把队列条目改到一半 —— 每一条路径
   都要能把用户已经打出来的字还回去。
4. **同屏可以有 N 个聊天。** 主聊天 + 若干会话瓦片,各自有自己的附件、焦点、Esc 语义、
   模型、cwd。任何"全局单例"的写法(全局附件 atom、`:root` 上的 CSS 变量、全局
   `$busy`)在 N>1 时都会串台。

---

## 2. 接缝穷举(判据 2)

> 本节每张表都给出机械枚举命令与条数。**未抽样**。

### 2.1 顶层导出面 —— 250 条

```verify
cd /home/user/hermes-agent
while read -r f; do grep -nE '^export ' "$f"; done \
    < /home/user/hermes-study/data/r10b/slices/A.txt | wc -l
# => 250
```

按文件的完整清单可用同一条命令去掉 `| wc -l` 得到(每行形如
`路径:行号:export …`)。**250 条是这一片对仓库其余部分的全部静态导出面。**

### 2.2 `ChatBarProps` —— composer 的对外契约,22 个字段

`apps/desktop/src/app/chat/composer/types.ts:34 @ 863e313`

```ts
export interface ChatBarProps {
  busy: boolean
  disabled: boolean
  focusKey?: string | null
  maxRecordingSeconds?: number
  state: ChatBarState
  gateway?: HermesGateway | null
  queueSessionKey?: string | null
  sessionId?: string | null
  cwd?: string | null
  onCancel: () => Promise<void> | void
  onAddContextRef?: (refText: string, label?: string, detail?: string) => void
  onAddUrl?: (url: string) => void
  onAttachImageBlob?: (blob: Blob) => Promise<boolean | void> | boolean | void
  onAttachDroppedItems?: (candidates: DroppedFile[]) => Promise<boolean | void> | boolean | void
  onPasteClipboardImage?: (opts?: { silent?: boolean }) => Promise<boolean> | void
  onPickFiles?: () => void
  onPickFolders?: () => void
  onPickImages?: () => void
  onRemoveAttachment?: (id: string) => void
  onSteer?: (text: string) => Promise<boolean> | boolean
  onSubmit: (value: string, options?: SubmitTextOptions) => Promise<boolean> | boolean
  onTranscribeAudio?: (audio: Blob) => Promise<string>
}
```

**只有 4 个是必填**(`busy` / `disabled` / `state` / `onCancel` / `onSubmit` —— 五个,
其余 17 个可选)。可选的那 17 个全是"宿主能不能提供这个能力"的开关:没有
`onPickFiles`,"+"菜单里那一行就 disabled;没有 `onSteer`,busy 时打字就只能排队不能
改向。**这是这一片最重要的设计取舍:能力由宿主注入,composer 自己不去猜。**

`ChatBarProps.onSubmit` 的第二参 `SubmitTextOptions` 有 6 个字段(定义在片外
`apps/desktop/src/app/session/hooks/use-prompt-actions/utils.ts:387`):
`attachments` / `composerScope` / `displayText` / `fromQueue` / `sessionId` /
`storedSessionId`。

```verify
cd /home/user/hermes-agent/apps/desktop/src
awk '/^export interface SubmitTextOptions \{/,/^\}/' \
    app/session/hooks/use-prompt-actions/utils.ts | grep -cE '^  [a-zA-Z]+\??:'
# => 6
```

### 2.3 插件贡献面 `COMPOSER_AREAS` —— 8 个,不是 6 个

`apps/desktop/src/app/chat/composer/contrib.ts:31 @ 863e313`

```ts
export const COMPOSER_AREAS = {
  top: 'composer.top',
  bottom: 'composer.bottom',
  underside: 'composer.underside',
  leading: 'composer.leading',
  actions: 'composer.actions',
  middleware: 'composer.middleware',
  attachments: 'composer.attachments',
  microActions: 'composer.microActions'
} as const
```

前 5 个是**渲染槽**(`<ContribSlot area={…}>`),后 3 个是**数据贡献**:

| area | 类型 | 载荷 | 语义 |
|---|---|---|---|
| `composer.top` | render | ReactNode | 输入框上方横幅带 |
| `composer.bottom` | render | ReactNode | 输入网格下方一行 |
| `composer.underside` | render | ReactNode | 整个 composer **下方**的无边框浮条 |
| `composer.leading` | render | ReactNode | "+"菜单之后的内联位 |
| `composer.actions` | render | ReactNode | 模型药丸之前的内联位 |
| `composer.middleware` | data | `ComposerMiddleware` | 提交前的有序异步链:改写 / 放行 / 返回 `null` 取消 |
| `composer.attachments` | data | `ComposerAttachmentProvider` | 给"+"菜单加一行 |
| `composer.microActions` | data | `ComposerMicroActionProvider` | 输入区上方药丸条,按 `{busy, sessionId, todos}` 现算 |

中间件链的容错是显式的:抛异常按**放行**处理(`apps/desktop/src/app/chat/composer/contrib.ts:90-92`),所以一个坏插件
吞不掉用户的消息。

### 2.4 焦点/插入事件总线 —— 6 个事件,6 对 request/on

`apps/desktop/src/app/chat/composer/focus.ts:41 @ 863e313`

```ts
const FOCUS_EVENT = 'hermes:composer-focus'
const INSERT_EVENT = 'hermes:composer-insert'
const INSERT_REFS_EVENT = 'hermes:composer-insert-refs'
const SUBMIT_EVENT = 'hermes:composer-submit'
const VOICE_TOGGLE_EVENT = 'hermes:composer-voice-toggle'
const MODEL_MENU_EVENT = 'hermes:composer-model-menu'
```

| 事件 | 发起 API | 订阅 API | 谁在用(片外调用点,已穷举) |
|---|---|---|---|
| focus | `requestComposerFocus` | `onComposerFocusRequest` | `app/hooks/use-keybinds.ts`、`app/contrib/hooks/use-desktop-integrations.ts`、`components/assistant-ui/clarify-tool.tsx`、`right-rail/preview-file.tsx`、`hooks/use-composer-actions.ts` |
| insert(纯文本) | `requestComposerInsert` | `onComposerInsertRequest` | `app/contrib/wiring.tsx`、`app/contrib/hooks/use-desktop-integrations.ts`、`components/assistant-ui/clarify-tool.tsx`、`right-rail/preview-console.tsx`、`chat/index.tsx`、`hooks/use-composer-actions.ts` |
| insert-refs(chip) | `requestComposerInsertRefs` | `onComposerInsertRefsRequest` | `chat/session-drag.ts`、`right-rail/preview-file.tsx`、`hooks/use-composer-actions.ts` |
| submit(代提交) | `requestComposerSubmit` | `onComposerSubmitRequest` | `app/right-sidebar/review/ship-bar.tsx`(唯一) |
| voice-toggle | `requestVoiceToggle` | `onComposerVoiceToggleRequest` | `app/hooks/use-keybinds.ts`(唯一) |
| model-menu | `requestModelMenuToggle` | `onComposerModelMenuRequest` | `app/hooks/use-keybinds.ts`(唯一) |

**这张"谁在用"的枚举面**(负结论的搜索面已写出):

```verify
cd /home/user/hermes-agent/apps/desktop/src
grep -rn "requestComposerFocus\|requestComposerInsert\b\|requestComposerInsertRefs\|requestComposerSubmit\|requestVoiceToggle\|requestModelMenuToggle\|markActiveComposer\|releaseActiveComposer\|getActiveComposer\|blurComposerInput" \
    --include=*.ts --include=*.tsx \
  | grep -v "app/chat/composer/focus.ts" | grep -v "\.test\."
```
排除的是:`focus.ts` 自身的定义行,以及 `*.test.ts(x)`。上面 24 行命中里,
`app/chat/**` 内的 13 行属本片,片外 11 行(`use-keybinds`×3、`use-desktop-integrations`×2、
`wiring.tsx`、`ship-bar.tsx`、`clarify-tool.tsx`×2、`user-edit-composer.tsx`×2)。
路由键还有 4 个:`markActiveComposer` / `releaseActiveComposer` / `getActiveComposer` /
`blurComposerInput`,构成"哪一个 composer 是 active"的所有权协议。

`ComposerTarget` 只有三种取值形态:`'main'`、`'edit'`(消息就地编辑框)、`'tile:<storedId>'`
(`apps/desktop/src/app/chat/composer/focus.ts:21`,类型上是 `'edit' | 'main' | (string & {})`,后者靠 `apps/desktop/src/app/chat/session-tile.tsx:138`
`target: \`tile:${storedSessionId}\`` 生成)。

### 2.5 `ComposerScope` —— 一个 ChatBar 是谁,4 个字段

`apps/desktop/src/app/chat/composer/scope.tsx:34 @ 863e313`

```ts
export const MAIN_COMPOSER_SCOPE: ComposerScope = {
  $awaitingInput: $activeSessionAwaitingInput,
  $messages,
  attachments: mainComposerScope,
  target: 'main'
}
```

四个字段各自解决一个"N 个 composer 同屏"的串台点:
`$awaitingInput` 决定 Esc 该不该打断(轮次停在用户身上时不该);`$messages` 是本
scope 的转录(输入历史上翻、自动朗读都读它);`attachments` 是本 scope 的附件集;
`target` 是事件总线的路由键。**草稿文本不需要 scope** —— 它本来就在各自的
contentEditable 里,并按会话键 stash(`apps/desktop/src/app/chat/composer/scope.tsx:17-20` 的注释就是这么讲的)。

### 2.6 `SessionView` —— 一个 surface 从 store 的哪一片读,13 个 atom

`apps/desktop/src/app/chat/session-view.tsx:42 @ 863e313`

```ts
export interface SessionView {
  kind: 'primary' | 'tile'
  $runtimeId: ReadableAtom<string | null>
  $storedId: ReadableAtom<string | null>
  $messages: ReadableAtom<ChatMessage[]>
  $busy: ReadableAtom<boolean>
  $awaitingResponse: ReadableAtom<boolean>
  $messagesEmpty: ReadableAtom<boolean>
  $lastVisibleIsUser: ReadableAtom<boolean>
  $cwd: ReadableAtom<string>
  $model: ReadableAtom<string>
  $provider: ReadableAtom<string>
  $fast: ReadableAtom<boolean>
  $reasoningEffort: ReadableAtom<string>
}
```

全是 atom 而不是值 —— 因为订阅粒度是这一片的命脉:`ChatView` 只订阅粗粒度边沿,
`$messages` 只在 `ChatRuntimeBoundary` 里订阅(`apps/desktop/src/app/chat/index.tsx:227`),流式增量的
重渲染就被关在那一个组件里。

### 2.7 `PaneMirror<T>` —— 三种瓦片共用的窗格镜像配置,15 个字段

`apps/desktop/src/app/chat/pane-mirror.ts:18` 起。字段:`source`、`also`、`key`、
`prefix`、`dir`、`anchor`、`before`、`minWidth`、`title`、`tabLead`、`stripTools`、
`render`、`tabWrap`、`tabDrag`、`close`。

```verify
cd /home/user/hermes-agent/apps/desktop/src
awk '/^export interface PaneMirror<T> \{/,/^\}/' app/chat/pane-mirror.ts \
  | grep -cE '^  [a-zA-Z]+\??[:(]'
# => 15
```

三个使用点(全片枚举,搜索面 = 本片 84 文件 `grep -l "paneMirror"`):
`apps/desktop/src/app/chat/session-tile.tsx:571`(会话瓦片,用满 `tabLead`/`tabWrap`/`tabDrag`)、
`apps/desktop/src/app/chat/route-tile.tsx:81`(整页瓦片,只用 6 个字段)、
`preview-tile.tsx`(预览瓦片,用 `stripTools`)。

### 2.8 触发(补全)接缝

**四条正则,三种 trigger kind。**

`apps/desktop/src/app/chat/composer/text-utils.ts:65 @ 863e313`

```ts
const AT_TRIGGER_RE = /(?:^|[\s\uFFFC])(@)([^\s@\uFFFC]*)$/
const SLASH_COMMAND_TRIGGER_RE = /^(\/)((?:[a-zA-Z][\w-]*(?:\s+\S*)*)?)$/
const SLASH_INLINE_TRIGGER_RE = /[\s\uFFFC](\/)([a-zA-Z][\w-]*)?$/
// `:joy` → emoji completions, Slack-style. Boundary-anchored so a mid-word
// colon (`localhost:8080`, `note:`) never fires; two chars minimum so a bare
// `:` or `:D` smiley doesn't open a popover the user didn't ask for.
const EMOJI_TRIGGER_RE = /(?:^|[\s\uFFFC])(:)([a-zA-Z0-9_+-]{2,})$/
```

`￼`(object replacement character)是把 chip 当成 token 边界的机制:
`serializeTextBefore` 让每个 chip 只贡献这一个占位符,于是"药丸后面紧跟 `@`"照样开气泡,
而药丸的 label 文字不会泄漏进正则。

**`@` 的 6 个 browse scope**(`apps/desktop/src/app/chat/composer/text-utils.ts:21` `DIRECTIVE_SCOPES`):
`file` / `folder` / `url` / `image` / `tool` / `git`。`apps/desktop/src/app/chat/composer/hooks/use-at-completions.ts:13`
的 `REF_STARTERS` 是同一组 6 个,`:15` 的 `STARTER_META` 给每个一句说明。

**补全适配器三选一**(`apps/desktop/src/app/chat/composer/hooks/use-composer-trigger.ts:177-184`):`@`→`at.adapter`、
`/`→`slash.adapter`、`:`→`emoji.adapter`。

**接受键规则**(整块逐字):

`apps/desktop/src/app/chat/composer/composer-utils.ts:86 @ 863e313`

```ts
export function acceptsTriggerCompletion({
  activeExplicit,
  freeTextArgStage,
  key,
  kind,
  query
}: TriggerAcceptInput): boolean {
  if (key === 'Tab') {
    return true
  }

  if (key === 'Enter') {
    return !freeTextArgStage || activeExplicit
  }

  // Space is slash-only (an `@` mention takes a literal space) and gated to a
  // non-empty query so a bare `/ ` still types a space.
  return key === ' ' && kind === '/' && Boolean(query.trim()) && !freeTextArgStage
}
```

### 2.9 键盘绑定表 —— `handleEditorKeyDown` 的 20 个分支(按判定顺序穷举)

全部在 `apps/desktop/src/app/chat/composer/index.tsx:504-835`。顺序即优先级。

| # | 行号 | 条件 | 动作 |
|---|---|---|---|
| 1 | `:510` | IME 组字中(`composingRef` 或 `isComposing`) | 直接 return,不做任何处理 |
| 2 | `:517` | `isUndoShortcut`(⌘Z / Ctrl+Z) | `undo()` |
| 3 | `:524` | `isRedoShortcut`(⌘⇧Z / Ctrl+Y) | `redo()` |
| 4 | `:534` | 无修饰 Backspace 且光标前是 chip | 连同 chip 自动补的尾空格一起删 |
| 5 | `:549` | Backspace/Delete 且选区非塌陷 | 自己删选区(绕开原生 O(n²)) |
| 6 | `:561` | 空格且光标前是完整链接 | 定型成 `@url:` chip |
| 7 | `:571` | 空格且光标前是裸 `@path` | 定型成 `@file:`/`@folder:` chip |
| 8 | `:580` | ⌘/Ctrl+Shift+K | 不 busy 时排空下一条队列消息 |
| 9 | `:594` | 气泡开着但项在飞、按 Tab | 吞掉(不让焦点跳出输入框) |
| 10 | `:602` | 气泡有项 + ↓ | 高亮下移 |
| 11 | `:610` | 气泡有项 + ↑ | 高亮上移 |
| 12 | `:621` | 气泡有项 + `acceptsTriggerCompletion` 为真 | 落 chip;Tab 表示"进目录",Enter 表示"就要它" |
| 13 | `:646` | 气泡有项 + Backspace 且在 `@` 路径里 | 上钻一级(`a/b/`→`a/`,再退掉 `folder:` 前缀) |
| 14 | `:653` | 气泡有项 + Escape | 关气泡 |
| 15 | `:666` | `/` 且已进参数段、无候选、按空格或 Tab | 把手打的 `/cmd arg` 直接落成 chip |
| 16 | `:684` | ↑ | 三选一:走到更旧的队列条目 / 打开最新队列条目编辑 / 上翻已发历史 |
| 17 | `:725` | ↓ | 走到更新的队列条目 / 历史下翻回草稿 |
| 18 | `:753` | ⌘/Ctrl+Enter | busy 时把草稿排队(先从 DOM 重读一次) |
| 19 | `:772` | Enter(无 Shift) | 决策:空+有队列→排空;busy+空→把队首提前发;否则 `submitDraft()` |
| 20 | `:817` | Escape | 编辑队列条目中→取消编辑;否则 busy 且非"等用户输入"→显式停止(并 park 队列) |

同一个编辑器上的其余 8 个 DOM 事件(`apps/desktop/src/app/chat/composer/index.tsx:956-985`):
`onBeforeInput`(记撤销点)、`onBlur`(80ms 后关气泡)、`onCompositionEnd`(IME 提交后
强制 flush)、`onCompositionStart`(清空态标记)、`onDragOver`/`onDrop`(输入框上的
拖放)、`onFocus`(`markActiveComposer`)、`onInput`(rAF 合并 flush)、`onKeyUp`
(刷新触发,除非 keydown 已消费)、`onMouseUp`(刷新触发)、`onPaste`。

编辑器之外还有两处键盘认领:
`apps/desktop/src/app/chat/composer/hooks/use-composer-undo.ts:113` 在 **document 捕获阶段**认领 `beforeinput` 的
`historyUndo`/`historyRedo`(macOS 菜单栏的 Edit→Undo 加速键会先于网页拿到按键);
`apps/desktop/src/app/chat/composer/hooks/use-composer-esc-cancel.ts:59` 在 window 上监听 Escape,处理"焦点在转录区而非输入框"
时的停止。

### 2.10 网关 RPC —— 本片直接发起 8 个

```verify
cd /home/user/hermes-agent
grep -rnoE "request(Gateway)?(<[^>]*>)?\(\s*'[a-z][a-z_]*\.[a-z_]+'" \
    $(cat /home/user/hermes-study/data/r10b/slices/A.txt) | sort -u
```

| 方法 | 发起处 | 用途 |
|---|---|---|
| `complete.path` | `apps/desktop/src/app/chat/composer/hooks/use-at-completions.ts:125` | `@` 路径补全 |
| `complete.slash` | `apps/desktop/src/app/chat/composer/hooks/use-slash-completions.ts:187` | `/` 命令与参数补全 |
| `commands.catalog` | `apps/desktop/src/app/chat/composer/hooks/use-slash-completions.ts:146` | 空 `/` 时的命令目录(带分类与技能用量) |
| `wake.pause` | `apps/desktop/src/app/chat/composer/hooks/use-composer-voice.ts:222` | 语音会话期间暂停唤醒词 |
| `image.detach` | `apps/desktop/src/app/chat/hooks/use-composer-actions.ts:638` | 移除已附加到会话的图片 |
| `session.interrupt` | `apps/desktop/src/app/chat/session-tile-actions.ts:267` | 瓦片的停止 |
| `session.redirect` | `apps/desktop/src/app/chat/session-tile-actions.ts:325` | 瓦片的 steer(改向);返回 `redirected` 或 `queued` |
| `prompt.submit` | `apps/desktop/src/app/chat/session-tile-actions.ts:381` | 瓦片的"重新生成"(带 truncate 参数) |

**主聊天与瓦片的普通发送都不在这张表里** —— 它们经 `useSubmitPrompt`
(`app/session/hooks/use-prompt-actions/submit.ts`,片外)发 `prompt.submit`。
这正是 composer 的边界:它只负责把文字变成一次 `onSubmit(text, options)` 调用。

### 2.11 DOM 契约(`data-slot` / `data-*` 属性)—— 13 个 slot

`aui_edit-composer-root`(片外挂的,`apps/desktop/src/app/chat/composer/focus.ts:49` 只读它)、`chat-drop-overlay`、
`coding-status-cwd`、`composer-attachments`、`composer-bounds`、
`composer-completion-drawer`、`composer-directive-action`、`composer-dock`、
`composer-drag-region`、`composer-fade`、`composer-rich-input`、`composer-root`、
`composer-surface`。

其中 4 个是**跨模块被查询**的真接缝,不只是样式钩子:

| 属性/值 | 定义处 | 谁查它 |
|---|---|---|
| `data-slot="composer-rich-input"` | `apps/desktop/src/app/chat/composer/rich-editor.ts:22` 的 `RICH_INPUT_SLOT` | `apps/desktop/src/app/chat/composer/focus.ts:331` 的 `blurComposerInput`;外部性能脚本 `scripts/perf/lib/cdp.mjs` |
| `data-composer-target` | `apps/desktop/src/app/chat/index.tsx:511` | `apps/desktop/src/app/chat/composer/focus.ts:80/102/109/274/287`(路由解析)、`apps/desktop/src/app/chat/session-drag.ts:76`(拖放落点) |
| `data-session-anchor` | `apps/desktop/src/app/chat/index.tsx:512` | `apps/desktop/src/app/chat/session-drag.ts:76`(分屏时贴哪个窗格) |
| `data-slot="composer-root"` | `apps/desktop/src/app/chat/composer/index.tsx:1123`、`ChatBarFallback` `:1296` | `apps/desktop/src/app/chat/session-drag.ts:135`(判断指针是否在输入区上 → 走"链接"而非"分屏") |
| `data-chat-surface` | `apps/desktop/src/app/chat/index.tsx:510` | `apps/desktop/src/app/chat/surface-vars.ts:39` 的 `chatSurfaceRoot`(CSS 变量往哪写) |

### 2.12 store 面 —— 40 个 store 模块 / 180 个符号

完整逐模块清单由探针打印(见 §0.0 命令),此处给按用量的分布:
`session`(30)、`composer`(13)、`composer-queue`(13)、`session-states`(13)、
`composer-popout`(12)、`composer-status`(9)、`preview`(9)、`layout`(6)、
`profile`(6)、`coding-status`(5)、`composer-input-history`(5)、`projects`(5)、
`artifacts`(4)、`preview-status`(4)、`prompts`(4)、其余 25 个模块各 1–3 个。

**composer 自己拥有 5 个 store**(名字以 `composer` 开头):`composer`(附件 + 草稿
stash)、`composer-queue`(排队消息)、`composer-input-history`(上下翻历史的浏览态)、
`composer-actions`(微动作)、`composer-status`(状态栈)、`composer-popout`(弹出位置)。
—— 6 个。这是"输入区状态不放在组件里"的直接体现:composer 卸载重挂不丢东西。

### 2.13 内部拆分接缝 —— 24 个 hook 的输入/输出

`ChatBar` 自己不持有几乎任何状态,它持有的是 **hook 之间的显式握手**。最能说明设计的
是 `queueEditRef`:草稿引擎要知道"正在编辑某条队列消息"以便**抑制** stash,队列引擎
是这个状态的所有者。`ChatBar` 不让两者互相引用,而是自己造一个 ref 分别传给两边
(`apps/desktop/src/app/chat/composer/index.tsx:188` 的注释原话:"an explicit shared handle, not a back-reference")。

`useComposerDraft` 返回 16 个成员(`apps/desktop/src/app/chat/composer/hooks/use-composer-draft.ts:419-436`):
`activeQueueSessionKeyRef`、`clearDraft`、`draftRef`、`editorRef`、`focusInput`、
`hasText`、`insertInlineRefs`、`insertText`、`isHelpHint`、`isSteerableText`、
`loadIntoComposer`、`requestMainFocus`、`sessionIdRef`、`setComposerText`、`stashAt`、
`syncDraftFromEditor`。

`useComposerQueue` 返回 10 个(`apps/desktop/src/app/chat/composer/hooks/use-composer-queue.ts:371-382`):
`beginQueuedEdit`、`drainNextQueued`、`editingQueuedPrompt`、`exitQueuedEdit`、
`queueCurrentDraft`、`queueEdit`、`queueParked`、`queuedPrompts`、`sendQueuedNow`、
`stepQueuedEdit`。

`useComposerTrigger` 返回 15 个(`apps/desktop/src/app/chat/composer/hooks/use-composer-trigger.ts:441-457`):
`argStageEmpty`、`ascendTriggerPath`、`closeTrigger`、`commitTypedSlashDirective`、
`moveTriggerActive`、`refreshTrigger`、`replaceTriggerWithChip`、`setTriggerActive`、
`slashFreeTextArgStage`、`trigger`、`triggerActive`、`triggerActiveExplicit`、
`triggerItems`、`triggerKeyConsumedRef`、`triggerLoading`。

`useComposerSubmit` 返回 4 个:`dispatchSubmit`、`queueDraft`、`steerDraft`、`submitDraft`。
`useComposerVoice` 返回 8 个;`useComposerPopout` 返回 7 个;`useComposerDrop` 返回 7 个;
`useComposerUndo` 返回 5 个;`useComposerBranch` 返回 5 个;`useComposerMetrics` 返回 2 个;
`useComposerUrlDialog` 返回 7 个;`useComposerDraft` 之外的其余 hook 返回 1–3 个或无返回。

---

## 3. 端到端链:一次键入如何变成一次 `prompt.submit`(判据 3)

场景:用户在**会话瓦片**里敲 `帮我看看 @src/main.ts`,按 Enter。

### 跳 1 — 按键落到 contentEditable

`apps/desktop/src/app/chat/composer/index.tsx:981` 的 `onInput={handleEditorInput}`;
IME 组字期间跳过(`:418-427`),其余走 rAF 合并。

### 跳 2 — 合并后的 flush 把 DOM 写进 `draftRef` + AUI state

`apps/desktop/src/app/chat/composer/index.tsx:377 @ 863e313`

```ts
  const flushEditorToDraft = (editor: HTMLDivElement) => {
    if (flushRafRef.current !== undefined) {
      window.cancelAnimationFrame(flushRafRef.current)
      flushRafRef.current = undefined
    }

    normalizeComposerEditorDom(editor)

    const nextDraft = sanitizeComposerInput(composerPlainText(editor))

    if (nextDraft !== draftRef.current) {
      draftRef.current = nextDraft
      setComposerText(nextDraft)
    }

    window.setTimeout(refreshTrigger, 0)
  }
```

合并的理由写在 `:370-374`:`composerPlainText` 是 O(n) 的全编辑器序列化,按住一个键
或连续粘贴时逐事件跑就是整段 O(n²)。

### 跳 3 — Enter 进入决策树

`apps/desktop/src/app/chat/composer/index.tsx:772` 的 Enter 分支先从 DOM 现读一次(`:781`,理由:AUI state 落后一帧),
判定有 payload 后调 `submitDraft()`(`:812`)。

### 跳 4 — `submitDraft` 定型引用并选路

`apps/desktop/src/app/chat/composer/hooks/use-composer-submit.ts:132-141` 再从 DOM 同步一次;`:146`
`const text = pathifyRefs(draftRef.current)` 把没来得及打空格的裸 `@src/main.ts`
升格成 `@file:\`src/main.ts\``;`:160` 若本会话有 clarify 卡片则先 skip;
`:195-201` 走"发送"分支:`triggerHaptic('submit')` → `resetBrowseState` →
`clearDraft()` → `scope.attachments.clear()` → `dispatchSubmit(text, submittedAttachments)`。

### 跳 5 — `dispatchSubmit`:带回滚的发送原语

`apps/desktop/src/app/chat/composer/hooks/use-composer-submit.ts:81 @ 863e313`

```ts
  const dispatchSubmit = (text: string, attachments?: ComposerAttachment[]) => {
    const submittedScope = activeQueueSessionKeyRef.current
    const submittedAttachments = attachments ?? []

    const restore = () => {
      loadIntoComposer(text, submittedAttachments)
      // Use the scope captured at dispatch, not whatever session is focused
      // now — the gateway can reject well after the user has switched away,
      // and re-stashing into the currently-focused session would overwrite
      // its draft with the rejected text from a different session (#54527).
      stashAt(submittedScope, text, submittedAttachments)
    }

    void Promise.resolve(
      attachments
        ? onSubmit(text, { attachments, composerScope: submittedScope })
        : onSubmit(text, { composerScope: submittedScope })
    )
      .then(accepted => void (accepted === false ? restore() : clearSessionDraft(submittedScope)))
      .catch(restore)
  }
```

**`accepted === false` 是唯一的"没发出去"信号**,`onSubmit` 的返回类型
`Promise<boolean> | boolean` 就是为它存在的。回填时用的是**发起时捕获的 scope**,
不是当前聚焦的会话 —— 这是 #54527 的修法。

### 跳 6 — ChatBar 的 `onSubmit` 包装:语音停止词 + 中间件链

`apps/desktop/src/app/chat/composer/index.tsx:112 @ 863e313`

```ts
  const onSubmit = useCallback<ChatBarProps['onSubmit']>(
    async (value, options) => {
      // Bare stop phrase typed while the voice conversation is live: end the
      // conversation (mic off, pill dismissed) instead of sending "stop" to
      // the agent. Spoken transcripts are already stop-checked inside
      // use-voice-conversation, so this only catches typed/queued sends.
      // Outside a voice conversation, typed "stop" is a normal message.
      const voiceStop = voiceStopRef.current

      if (interceptsTypedVoiceStop(voiceStop.active, value, options?.attachments?.length ?? 0)) {
        voiceStop.end()

        // Consumed (not rejected): report accepted so the submit engine
        // clears the draft instead of restoring "stop" into the composer.
        return true
      }

      const draft = await runComposerMiddleware({ text: value, attachments: options?.attachments })

      if (!draft) {
        return false
      }

      return onSubmitProp(draft.text, { ...options, attachments: draft.attachments })
    },
    [onSubmitProp]
  )
```

### 跳 7 — `onSubmitProp` = `ChatView` 收到的 `onSubmit` prop

`apps/desktop/src/app/chat/index.tsx:619` 把它原样透传给 `ChatBar`。瓦片场景下这个 prop 来自
`apps/desktop/src/app/chat/session-tile.tsx:215` `onSubmit={actions.submitText}`。

### 跳 8 — 瓦片的 `submitText`:斜杠命令分流

`apps/desktop/src/app/chat/session-tile-actions.ts:226-243`:若无附件且文本匹配 `SLASH_COMMAND_RE`,
交给 `sessionTileDelegate()?.executeSlash(...)` 并 `return true`(**不走网关提交**);
否则 `return await submitPromptText(rawText, options)`。

### 跳 9 — `useSubmitPrompt` 组装网关参数

`apps/desktop/src/app/session/hooks/use-prompt-actions/submit.ts:606 @ 863e313`

```ts
        const submitParams = (targetId: string) => ({
          session_id: targetId,
          text,
          ...(interrupted && { interrupted }),
          // A queue drain is a "run after" message, never a live-turn
          // correction. The flag tells the gateway's busy path to hold it for
          // the next turn untouched — without it, losing the settle race
          // (client saw idle, server still unwinding) redirects or interrupts
          // the live turn with text the user explicitly queued.
          ...(options?.fromQueue && { queued: true })
        })
```

### 跳 10 — 打到网关

`apps/desktop/src/app/session/hooks/use-prompt-actions/submit.ts:623 @ 863e313`

```ts
        try {
          await withSessionBusyRetry(() =>
            requestGateway('prompt.submit', submitParams(sessionId), PROMPT_SUBMIT_REQUEST_TIMEOUT_MS)
          )
        } catch (firstErr) {
```

失败时(session not found / timeout)`:630` 起会 `session.resume` 换一个新 runtime id
重试一次。

**链路完整:用户按键 → contentEditable DOM → rAF flush → `draftRef` → Enter 决策树
→ `pathifyRefs` 定型 → `dispatchSubmit`(带回滚)→ 语音停止词拦截 → 中间件链
→ `ChatView.onSubmit` prop → 瓦片斜杠分流 → `useSubmitPrompt` → `prompt.submit`。
拒绝路径原路返回:`accepted===false` → `loadIntoComposer` + `stashAt(发起时的 scope)`。**

---

## 4. 逐区域

### 4.1 草稿引擎:为什么真源不在 React 里

`apps/desktop/src/app/chat/composer/hooks/use-composer-draft.ts:43-52` 的文档注释把设计意图写得很直白:文字活在
contentEditable + `draftRef`,React 只看**粗粒度选择器**。实际只订阅了三个:

- `hasText` —— 空↔非空(`:67`)
- `isHelpHint` —— 文本恰好等于 `?`(`:68`)
- `isSteerableText` —— 非空且不是斜杠命令(`:70-74`)

代价是要自己接上四条**同步回路**:

1. `composerRuntime.subscribe(sync)`(`:307`)—— AUI 侧变了就镜像回 `draftRef`,
   并且只在**编辑器没有焦点**时才重绘 DOM(`:280`,焦点在时 DOM 才是真源)。
2. 防抖 400ms 的按会话落盘(`apps/desktop/src/app/chat/composer/composer-utils.ts:27` `DRAFT_PERSIST_DEBOUNCE_MS`)。
3. `useLayoutEffect` 的会话切换 stash/restore(`:370`)。**必须是 layout effect**:
   它换的是模块级 `$attachments` atom,passive effect 要等浏览器绘制后才跑,
   那一帧里 DOM 已经是会话 B 而附件还是会话 A(#59305)。
4. `pagehide` 兜底(`:397-417`)—— Cmd+R 时 React 不跑 effect cleanup。

**跨会话落盘的守卫是双层的**:`draftScopeRef`(`:102`,只在切换 effect 里写,所以永远
指向"编辑器里装的是谁的文本")负责让每次捕获天生正确;`isPendingDraftPersistCurrent`
(`apps/desktop/src/app/chat/composer/composer-utils.ts:131`)负责在提交前再核一次 pending 记录还是不是自己那条。
后者的 docstring 明说它是 defense-in-depth,是给"未来某个改动重新引入实时 ref 读"
准备的。

### 4.2 提交决策树:七条出口

`apps/desktop/src/app/chat/composer/hooks/use-composer-submit.ts:164-202`。按判定顺序:

| 条件 | 出口 |
|---|---|
| `queueEdit` 非空 | `exitQueuedEdit('save')` —— Enter 是"存回队列",不是发送 |
| busy + 无附件 + 是斜杠命令 | 立刻 `dispatchSubmit`(斜杠命令是客户端操作或自足 RPC,排队会让它等一整轮) |
| busy + 非压缩中 + 无附件 + 有文本 | `steerDraft()` —— Cursor 式"停下并改向" |
| busy + 有 payload | `queueCurrentDraft()` —— 有附件只能排队(工具结果不能载图) |
| busy + 无 payload | `onCancel()` —— 这里只可能是点了 Stop 键(空 Enter 在 keydown 已短路) |
| 不 busy + 无 payload + 队列非空 | `drainNextQueued()` |
| 不 busy + 有 payload | 正常发送 |

`steerDraft`(`:210-227`)的守卫读的是**实时编辑器状态**而不是渲染滞后的 `canSteer`;
若网关回 `accepted=false`,文本转入队列(`:222-226`),不丢。

### 4.3 队列:一把锁、一个 park 标志、有界重试

- **一把排空锁**:`drainingQueueRef`,所有排空路径共用 `runDrain(pickEntry)`
  (`apps/desktop/src/app/chat/composer/hooks/use-composer-queue.ts:198`),`pickEntry` 让调用方选队首 / 指定 id / 跳过正在编辑的那条。
- **park(暂停)是显式停止的语义**:`haltRun`(`apps/desktop/src/app/chat/composer/index.tsx:282-286`)先
  `parkQueuedPrompts` 再 `onCancel()`。Stop 键、Esc、语音打断、转录区的停止
  (`apps/desktop/src/app/chat/index.tsx:380-384`)都走它;而"发送这条队列消息"引发的打断走**原始**
  `onCancel`(`apps/desktop/src/app/chat/composer/hooks/use-composer-queue.ts:273`),因为那次打断的目的正是让队列流起来。
- **成功排空自动解 park**:

`apps/desktop/src/app/chat/composer/hooks/use-composer-queue.ts:229 @ 863e313`

```ts
        drainFailuresRef.current.delete(entry.id)
        removeQueuedPrompt(drainQueueSessionKey, entry.id)
        resetBrowseState(drainRuntimeSessionId)
        // A successful drain means the queue is flowing again — lift any park
        // so the remaining entries follow. Manual drains (Enter on an empty
        // composer, the per-row send arrow) are exactly the resume gestures a
        // parked queue waits for; the auto path only reaches here unparked.
        unparkQueuedPrompts(drainQueueSessionKey)

        return true
```

- **跳过正在编辑的那条**:

`apps/desktop/src/app/chat/composer/hooks/use-composer-queue.ts:246 @ 863e313`

```ts
  const pickDrainHead = useCallback(
    (entries: QueuedPromptEntry[]) => {
      const skip = queueEditRef.current?.entryId

      return skip ? entries.find(e => e.id !== skip) : entries[0]
    },
    [queueEditRef] // reads the edit id off a ref so the lock-holder always sees the latest
  )
```

- **自动排空是边沿无关的**(`:344-348`):只要"不 busy + 未 park + 队列非空"就跑,
  失败计数到 `MAX_AUTO_DRAIN_ATTEMPTS` 就发通知并停手。作者的理由写在 `:341-343`:
  依赖 busy→false 这一个边沿的话,漏掉一次边沿就把消息永久搁浅。

### 4.4 chip:三条定型通道 + 一条水化通道

| 通道 | 触发时机 | 入口 |
|---|---|---|
| 打空格定型 | keydown 空格 | `apps/desktop/src/app/chat/composer/url-refs.ts:65` `chipTypedUrlOnSpace` / `apps/desktop/src/app/chat/composer/path-refs.ts:70` `chipTypedPathOnSpace` |
| 粘贴定型 | onPaste | `apps/desktop/src/app/chat/composer/index.tsx:500` `insertComposerContentsAtCaret(…, pathifyRefs(linkifyUrls(pastedText)), scope)` |
| 提交定型 | submitDraft | `apps/desktop/src/app/chat/composer/hooks/use-composer-submit.ts:146` `pathifyRefs(draftRef.current)` |
| 水化 | 任何"整段到货"的文本(粘贴、恢复草稿、撤销步、重建行) | `apps/desktop/src/app/chat/composer/rich-editor.ts:199` `appendComposerContents` → `chipSpans` → `slashCommandMatches` |

水化通道最容易被忽视,却是"打字路径与非打字路径必须给出同一结果"的那一半。
`apps/desktop/src/app/chat/composer/slash-refs.ts:32-47` 的两个选项就是为此存在:`boundaryBefore`(粘贴落在词中间时,
index 0 的 token 不算命令)与 `trailingCommitted`(惰性文本里结尾的 `/clean` 是完整命令,
而正在打字时结尾的 `/wor` 是半个查询,归气泡管)。

`apps/desktop/src/app/chat/composer/path-refs.ts:22` 的 `BARE_PATH_RE` 要求 token 里**必须有 `/`**,理由写在 `:17-21`:
`@teknium1` 是一个人名,`@diff` 是一个简单引用,猜错就把人名变成文件引用。

### 4.5 撤销栈:为什么必须整个自己拿

`apps/desktop/src/app/chat/composer/undo-history.ts:1-19` 给的因果链很完整:富编辑器为了躲开 Chromium 的 O(n²) 编辑管线
(#45812)改用 `Range` 直接改 DOM,代价是这些改动**不进 Chromium 的撤销栈**,于是
⌘Z 会跳过粘贴、撤掉粘贴之前的那次编辑。半拿(只记自己的)会和 Chromium 自己的打字条目
交错、乱序撤销,所以只能整个拿。

快照是"纯文本 + caret 偏移"而非 DOM,因为编辑器本来就能通过
`composerPlainText`/`renderComposerContents` 无损往返。
连续打字用 600ms 窗口合并成一条(`COALESCE_WINDOW_MS`),上限 200 条。

`withUndoPoint`(`apps/desktop/src/app/chat/composer/hooks/use-composer-undo.ts:66-78`)这个原语值得单独一提:它先取快照、再跑
条件编辑、**只有真跑了才记账**。因为"快照必须在编辑前取"和"不能每次 Backspace 都清空
redo 栈"这两个要求是冲突的。

### 4.6 弹出(pop-out):状态归 zone,夹取归 surface

`apps/desktop/src/app/chat/composer/hooks/use-composer-popout.ts:24-37` 讲清了一个 N-surface 的坑:一个布局 zone 为整个 tab
栈存**一个**意图,但每个 surface 的 rect 不同,所以夹取必须在各 surface 本地做。
若把夹取结果写回 store,每个 keep-alive 挂着的后台 tab 都会用**它自己的**几何去覆盖,
最后写者获胜 —— 这就是"在一个 tab 里拖动,到另一个 tab 就丢了"的成因。

手势(`use-popout-drag.ts`)的常量表:长按 360ms、容忍 10px、向上撕出 16px、
停靠带高 72px、中央容差 150px、垂直/水平衰减 260/220px。停靠接近度是对**本 surface 的
区域**算的而不是窗口(`:75-79`):分屏时窗口的底部中央根本不是那个 composer 的停靠点。

### 4.7 会话瓦片:同一棵树,换两个 Provider

`apps/desktop/src/app/chat/session-tile.tsx:192-222` 是全片最能说明架构的 30 行:瓦片就是
`<SessionViewProvider value={view}><ComposerScopeProvider value={scope}><ChatView …/>`。
`buildTileView`(`:77-105`)把 `$sessionTiles` + `$sessionStates` 计算成与主会话
**同形**的 13 个 atom;`scope`(`:133-141`)给它一份自己的附件集与 `tile:<id>` 路由键。

`ChatView` 是 `memo()` 的(`apps/desktop/src/app/chat/index.tsx:274`),所以瓦片必须把每个回调 prop 都
`useCallback` 稳住 —— `apps/desktop/src/app/chat/session-tile.tsx:154-158` 的注释与 `:107-112` 的模块级常量
(`noop`、`tileTranscribeAudio`)都是为这一条。

### 4.8 会话拖拽:一套指针会话,四种落点

`apps/desktop/src/app/chat/session-drag.ts:1-26` 记录了一次**技术选型的撤退**:原来用原生 HTML5 DnD,代价是
macOS 的取消回弹动画、被动画卡住的 `dragend`、页面根本收不到的 Esc、以及要防着
react-dnd/dnd-kit 的窗口级装甲。改成指针会话后这些全没了,已知代价是"不能再把会话拖进
另一个 BrowserWindow"。

落点四选一(`:149-192`):tab 栏 → 堆叠;边缘带 → 分屏;聊天 zone 中央或输入区 → 链接;
非聊天 zone 的中央 → 也堆叠(那里没有 composer 可链接)。提交:

`apps/desktop/src/app/chat/session-drag.ts:194 @ 863e313`

```ts
    onCommit() {
      if (split) {
        openSessionTile(payload.id, split.pos, split.anchor, split.before)
        // A tile for this session may already exist (openSessionTile is
        // idempotent — e.g. persisted from an earlier run): a drop must never
        // feel dead, so front/unhide/un-dismiss it either way.
        revealTreePane(`session-tile:${payload.id}`)
      } else if (link) {
        // The "link to chat" drop: an @session chip in that surface's composer.
        requestComposerInsertRefs([sessionInlineRef(payload)], { target: link })
      }
    }
  })
```

### 4.9 右栏预览:三种 target,一个 reader 注册表

`PreviewTarget.kind` 有 `url` / `file` / `artifact` 三种,分别由
`preview-pane.tsx`(`<webview>`)、`preview-file.tsx`、`preview-artifact.tsx` 渲染。
`preview-reader.ts` 是给 **agent 的 `read_preview` 工具**用的窗口:按 tabId 注册页面
读取器,没有 reader 的 tab(文件/artifact/还在加载)也会返回一个"身份 + 提示"的答案,
告诉模型该用哪个工具直接读(`:106-121`)。单次读取硬上限
`PREVIEW_READ_MAX_CHARS = 24_000`(`:48`),理由写在 `:46-47`:页面 innerText 可以是
几 MB,而这东西要穿过网关进模型上下文。

---

## 5. 文档与代码的出入

### ◎-A-1 插件 SDK 文档列了 6 个 composer 贡献区,实际 8 个

`website/docs/developer-guide/desktop-plugin-sdk.md:336 @ 863e313`

> `COMPOSER_AREAS` (`top`, `bottom`, `leading`, `actions`, `attachments`,
> `middleware`) let a plugin add controls around the message composer, provide an
> attachment source, or transform a draft before it is sent (`ComposerMiddleware`
> with a `handler(draft) => draft | null`).

代码里是 8 个(见 §2.3 的逐字块,`apps/desktop/src/app/chat/composer/contrib.ts:31-40`):文档漏了 **`underside`**
(整个 composer 下方的无边框浮条,`apps/desktop/src/app/chat/composer/index.tsx:1271-1273` 在渲染它)与
**`microActions`**(输入区上方的药丸条,`apps/desktop/src/app/chat/composer/index.tsx:1080` 的 `<ActionBadges>`
+ `use-micro-actions.ts` 的发布路径)。

**判为 ◎ 而不是 ▲**:文档点名的那 6 个逐个都成立,句子的谓语("让插件在 composer 周围
加控件 / 提供附件源 / 在发送前改写草稿")对这 6 个也成立;它只是把一个 8 项的集合
写成了 6 项的同位语,属"成立但显著保守"。按 CLAUDE.md 的记号约定,字面为真就不是 ▲。
*(判定时连整段一起看过:该段落归 `### Composer extensions` 这个标题管,全段只有这
一句,没有"among others"之类的开口措辞 —— 所以它读起来确实像完整清单,这正是它值得
记 ◎ 而不是忽略的原因。)*

### ◇-A-1 `composer.underside` 与 `composer.microActions`:代码有、SDK 文档无

同上一条的另一面。补充证据:这两个区在 `desktop-plugin-sdk.md` 的两张汇总表
(`:209` 的 area 总览、`:619-620` 的 API 清单)里也只以 `COMPOSER_AREAS.*` /
`ComposerMiddleware`、`ComposerAttachmentProvider` 的形式出现 ——
`ComposerMicroActionProvider` 这个类型名**在整份文档里一次都没有出现**。

搜索面(负结论口径):

```verify
cd /home/user/hermes-agent
grep -rn "ComposerMicroActionProvider\|composer.microActions\|composer.underside" website/ README.md AGENTS.md apps/desktop/*.md
# 无输出 = 这三个标识符在作者自绘的地图(website/**、两份 AGENTS.md、README、
# apps/desktop 下三份 md)里零命中
```
排除范围:未搜 `apps/desktop/src/**`(那是代码侧)与 `.claude/`。

### ◇-A-2 `SessionView` 这一层抽象在文档里没有对应词

`apps/desktop/DESIGN.md` 只有三处提到 composer(`:48`、`:196`、`:198`),内容是
"聊天是主界面"与"不要 fork 第二套 markdown/message/tool-call 组件"。而本片最关键的
架构决定 —— **主会话不是特权体,它只是第一个 tab,和瓦片读同一形状的 13 个 atom**
(`apps/desktop/src/app/chat/session-view.tsx:22-41` 的注释就是这么讲的)—— 在任何文档里都没有对应描述。
`website/docs/user-guide/desktop.md` 讲了 tab / 分屏的**用户可见行为**,没讲这层模型。

### 文档成立的几处(记录以免下一轮重复排查)

- `website/docs/user-guide/desktop.md:80` "模型选择器就在 composer 里,麦克风左边" ——
  成立:`apps/desktop/src/app/chat/composer/controls.tsx:94-95` 的顺序正是 `<ModelPill>` 紧接 `<DictationButton>`。
- `website/docs/user-guide/desktop.md:47` "按 Stop(或 Esc)会暂停队列并把它展开在 composer 上方" —— 成立:
  `apps/desktop/src/app/chat/composer/index.tsx:282` `haltRun` 先 `parkQueuedPrompts`;`apps/desktop/src/app/chat/composer/queue-panel.tsx:65-67`
  `defaultCollapsed={!parked}` 且 `key={parked ? 'parked' : 'flowing'}`(靠换 key 重挂
  来强制展开)。
- `website/docs/user-guide/skills/bundled/software-development/software-development-inspecting-hermes-desktop-dom.md:103` 用
  `[data-slot="composer-rich-input"]` 判定 composer 是否存在 —— 与
  `apps/desktop/src/app/chat/composer/rich-editor.ts:22` 的 `RICH_INPUT_SLOT` 一致。

---

## 6. 缺陷(■)

### ■-A-1 全片 4 处 `react-hooks/exhaustive-deps` 缺依赖(可复现,0 error / 4 warning)

在**基线之外**的导出副本上跑(不污染基线、不装包):

```verify
cd /home/user/r10b-ts/hermes-agent/apps/desktop
npx eslint $(sed 's|^apps/desktop/||' /home/user/hermes-study/data/r10b/slices/A.txt | tr '\n' ' ')
```

实测输出:

```text
/…/src/app/chat/composer/hooks/use-composer-branch.ts
  33:5  warning  React Hook useCallback has a missing dependency: 'scope.attachments'. …
/…/src/app/chat/composer/hooks/use-composer-draft.ts
  313:6  warning  React Hook useEffect has a missing dependency: 'stashAt'. …
  417:6  warning  React Hook useEffect has a missing dependency: 'stashAt'. …
/…/src/app/chat/session-tile-actions.ts
  193:5  warning  React Hook useCallback has a missing dependency: 'readState'. …
✖ 4 problems (0 errors, 4 warnings)
```

最清楚的一处:

`apps/desktop/src/app/chat/composer/hooks/use-composer-branch.ts:26 @ 863e313`

```ts
  const openInWorktree = useCallback(
    (path: string) => {
      const text = draftRef.current
      clearDraft()
      scope.attachments.clear()
      requestStartWorkSession(path, text)
    },
    [clearDraft, draftRef]
  )
```

`scope` 用了但不在依赖数组里,也**没有**像本仓库另外两处那样写
`// eslint-disable-line react-hooks/exhaustive-deps` + 理由注释
(对比 `apps/desktop/src/app/chat/composer/hooks/use-composer-draft.ts:392` 与 `apps/desktop/src/app/chat/composer/hooks/use-composer-queue.ts:369` 的写法)。
实际影响很小(`scope` 来自 context,在一个 surface 的生命周期内稳定),但它是
**未被声明的**违规:本仓库对这条规则的纪律是"要么修,要么就地写明为什么豁免",
这 4 处两样都没做。规则等级是 `warn`(`eslint.config.shared.mjs:92`),所以 CI 不拦。

### ■-A-2 排队按钮不像排队快捷键那样先从 DOM 重读草稿

键盘路径(⌘/Ctrl+Enter)显式先把 DOM 现读一遍再排队,注释说明了原因
(`apps/desktop/src/app/chat/composer/index.tsx:757-758`:"source the just-typed content from the DOM so a fast
keypress cannot queue a stale draft"):

`apps/desktop/src/app/chat/composer/index.tsx:753 @ 863e313`

```ts
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey) && !event.shiftKey) {
      event.preventDefault()

      if (busy && !disabled) {
        // As with plain Enter, source the just-typed content from the DOM so a
        // fast keypress cannot queue a stale draft.
        const editorText = editorRef.current ? composerPlainText(editorRef.current) : draftRef.current

        if (editorText !== draftRef.current) {
          draftRef.current = editorText
          setComposerText(editorText)
        }

        queueDraft()
      }

      return
    }
```

按钮路径(controls 里的 Layers3 排队键,`apps/desktop/src/app/chat/composer/index.tsx:933`
`onQueue={queueDraft}`)直接调同一个 `queueDraft`,而它不重读:

`apps/desktop/src/app/chat/composer/hooks/use-composer-submit.ts:229 @ 863e313`

```ts
  const queueDraft = () => {
    if (disabled || !busy) {
      return
    }

    queueCurrentDraft()
    focusInput()
  }
```

`queueCurrentDraft` 读的是 `draftRef.current`(`apps/desktop/src/app/chat/composer/hooks/use-composer-queue.ts:179`),
而 `draftRef` 的更新被 rAF 合并(`apps/desktop/src/app/chat/composer/index.tsx:398-407`)。
**暴露窗口很窄**(要在最后一次按键与点击之间不足一帧),我没有构造出实际复现;
把它记为 ■ 的依据是**同一危险在键盘路径上被显式挡了、在按钮路径上没有**,
而 `submitDraft` 的对应分支(`apps/desktop/src/app/chat/composer/hooks/use-composer-submit.ts:186` 的 `queueCurrentDraft()`)
之所以安全,只是因为它上游 `:132-141` 已经同步过一次。三条进入 `queueCurrentDraft`
的路径里,两条有保护、一条没有。

### ■-A-3(观察,非确证)`handlePaste` 里 `scope` 遮蔽了外层的 `ComposerScope`

`apps/desktop/src/app/chat/composer/index.tsx:142` `const scope = useComposerScope()` 是整个组件的
scope;`:497` `const scope = openDirectiveScope(event.currentTarget)` 在 `handlePaste`
里用同名局部变量遮蔽了它(值是一个 number)。当前 `handlePaste` 体内没有用到外层
`scope`,所以没有行为缺陷 —— 但这是本片里语义最重的一个变量名,遮蔽它是一个
真实的"下一次编辑会踩"的形状。**不是缺陷,是隐患**,如实记在这里。

---

## 7. 测试(行为规格)

### 7.1 本片相关测试的运行结果

命令(在基线之外的导出副本上跑,未装任何包):

```verify
cd /home/user/r10b-ts/hermes-agent/apps/desktop
npx vitest run --project ui src/app/chat/composer src/app/chat/right-rail \
  src/app/chat/hooks src/app/chat/close-tab.test.ts src/app/chat/index.test.tsx \
  src/app/chat/profile-tag.test.tsx src/app/chat/runtime-repository.test.ts \
  src/app/chat/scroll-to-bottom-button.test.tsx src/app/chat/session-drag.test.ts \
  src/app/chat/session-tile-row.test.ts src/app/chat/session-view.test.ts \
  src/app/chat/surface-vars.test.ts src/app/chat/thread-loading.test.ts \
  src/app/chat/transcript-window.test.ts
```

实测:

```text
 Test Files  52 passed (52)
      Tests  389 passed (389)
   Duration  198.08s
```

**passed 389 / failed 0 / skipped 0。**

参照:整个 `src/app/chat`(含不属本片的 `sidebar/`)是
`Test Files 66 passed (66) / Tests 496 passed (496)`,同样 0 failed / 0 skipped。

### 7.2 零执行/整文件跳过的点名

**零处。** 搜索面:

```verify
cd /home/user/hermes-agent/apps/desktop/src/app/chat
grep -rn "describe\.skip\|it\.skip\|test\.skip\|\.todo\|describe\.skipIf\|it\.skipIf" \
    --include=*.test.ts --include=*.test.tsx .
# 无输出
```
排除的:未搜 `xit` / `xdescribe`(该仓库用 vitest,不提供这两个别名)与
`test.each` 的空表(逐个看过 52 个文件的顶层 describe,没有空表驱动)。
52 个文件全部产出了用例(verbose reporter 逐条打印过,无 `0 test` 文件)。

### 7.3 这些测试钉住的行为(选取最能当规格用的几条)

| 测试文件 | 钉住的规格 |
|---|---|
| `composer/enter-submit-dom-race.test.tsx` | Enter 必须从 DOM 现读,而不是从落后一帧的 AUI state —— §3 跳 3 的那条约束 |
| `composer/ime-composition-dom-repro.test.tsx` | IME 组字期间 Enter 不提交;`compositionend` 必须 flush(#39614) |
| `composer/at-folder-navigation.test.tsx` | Tab 进目录 / Backspace 出目录,以及 browse scope 要随路径带下去 |
| `composer/composer-text-guard.test.tsx` | 提交/排队路径不得把陈旧草稿发出去 |
| `composer/focus.test.ts` | `'active'` 的解析与自愈:claim 指向被埋掉的后台 composer 时要落到可见的那个 |
| `composer/hooks/use-composer-queue.test.tsx` | 排空锁、park/unpark、跳过正在编辑的条目、有界重试 |
| `composer/hooks/use-composer-draft.test.tsx` | 会话切换的 stash/restore、防抖落盘的 scope 正确性(#54527) |
| `composer/undo-history.test.ts` | 合并窗口、no-op 编辑不入栈、traversal 结束打字 burst |
| `composer/contrib.test.ts` | 中间件链:空链逐字放行、按注册序改写、`null` 取消、抛异常按放行 |
| `session-view.test.ts` | 主视图读自己的 session slice,后台会话继续流式不得污染 |
| `surface-vars.test.ts` | 测量值只能写到本 surface 的根,写 `:root` 会给每个 thread 垫一个全局底 |
| `transcript-window.test.ts` | 按渲染权重(非条数)开窗,且切口要对齐分支组 |

---

## 8. 判据自查

| # | 判据 | 自评 |
|---|---|---|
| 1 | 点名到位 | **达标**。84 个文件全部以全路径出现在 §0.1–§0.6,各带一句角色。同型薄文件(status-stack 四件、chat 根的两个 overlay)也逐个列了全路径。 |
| 2 | 接缝穷举 | **基本达标,有一处自报不足**。已穷举并给出机械命令+条数的:导出面 250、`ChatBarProps` 22、`SubmitTextOptions` 6、`COMPOSER_AREAS` 8、focus 总线 6 事件 + 6 对 API + 片外 11 个调用点、`ComposerScope` 4、`SessionView` 13、`PaneMirror` 15、触发正则 4 + scope 6 + kind 3、键盘分支 20 + 编辑器事件 10 + 片外 2 处认领、网关 RPC 8、`data-slot` 13(含 5 个跨模块查询点)、store 40 模块/180 符号、24 个 hook 的返回面。**不足**:`preview-pane.tsx`(725 行)的 `<webview>` 事件面(`did-fail-load`/`console-message`/`dom-ready` 等)我只读了组件的 props 契约与注册接口(`registerPreviewPageReader` / `registerPreviewDevTools`),**没有逐项列全 webview 事件表**;`use-voice-conversation.ts`(736 行)的状态机迁移表同理只到 5 个状态名与返回面,没有列全迁移边。这两处约占本片接缝面的一成,记为**九成达标**。 |
| 3 | 端到端链 | **达标**。§3 给了 10 跳,每跳带锚点,含拒绝回滚路径。 |
| 4 | 逐字取证 | **达标**。逐字围栏块 13 个(contrib 8 键、focus 6 事件、`ChatBarProps`、四条触发正则、`MAIN_COMPOSER_SCOPE`、`acceptsTriggerCompletion`、`flushEditorToDraft`、`dispatchSubmit`、ChatBar 的 `onSubmit` 包装、`submitParams`、`prompt.submit` 调用、队列解 park、`pickDrainHead`、`SessionView`、`session-drag` 的 `onCommit`、`openInWorktree`、`queueDraft`、⌘Enter 分支)—— 实为 19 个,远超 2 个下限。 |
| 5 | 记号 | **达标**。◎ 1 条(SDK 文档 6 vs 8)、◇ 2 条、■ 2 条 + 1 条隐患,均带锚点与可复现命令。 |

---

## 9. 移交项

| id | 锚点 + 摘录 | 一句话现象 |
|---|---|---|
| H-A-a | `apps/desktop/src/app/chat/composer/hooks/use-composer-branch.ts:33`:`[clearDraft, draftRef]` | `openInWorktree` 用了 `scope.attachments` 却不在依赖数组里,也没写豁免注释;`npx eslint` 可复现这条 warning。 |
| H-A-b | `apps/desktop/src/app/chat/composer/hooks/use-composer-submit.ts:234`:`queueCurrentDraft()` | 排队**按钮**路径不像 ⌘Enter 路径那样先从 DOM 重读草稿,`draftRef` 由 rAF 合并更新,窄窗口内可能排进陈旧文本;未复现,只证明了保护的不对称。 |
| H-A-c | `apps/desktop/src/app/chat/composer/hooks/use-composer-draft.ts:313`:`}, [composerRuntime, queueEditRef])` | 同一个 effect 里调了 `stashAt` 却不在依赖里(另一处在 `:417`),同样无豁免注释。 |
| H-A-d | `apps/desktop/src/app/chat/session-tile-actions.ts:193`:`[requestGateway, scope.attachments]` | 该 `useCallback` 缺 `readState` 依赖,是本片第 4 条 exhaustive-deps warning。 |
| H-A-e | `website/docs/developer-guide/desktop-plugin-sdk.md:336` 的 `let a plugin add controls around the message composer, provide an` | SDK 文档把 `COMPOSER_AREAS` 写成 6 项,代码是 8 项(缺 `underside`、`microActions`);`ComposerMicroActionProvider` 在整个 `website/` 里零命中。记 ◎+◇,未记 ▲。 |
| H-A-f | `apps/desktop/src/app/chat/composer/index.tsx:497`:`const scope = openDirectiveScope(event.currentTarget)` | 在 `handlePaste` 内用同名 `scope` 遮蔽了 `:142` 的 `ComposerScope`;当前无行为缺陷,是隐患。 |
| H-A-g | `apps/desktop/src/app/chat/right-rail/preview-pane.tsx:27`:`type PreviewWebview = HTMLElement & {` | 本片**未穷举**的接缝之一:`<webview>` 的事件/方法面只读了这个结构类型与两处注册接口,事件表(`did-fail-load` / `console-message` / `dom-ready` …)没列全。 |
| H-A-h | `apps/desktop/src/app/chat/composer/hooks/use-voice-conversation.ts:19`:`export type ConversationStatus = 'idle' | 'listening' | 'transcribing' | 'thinking' | 'speaking'` | 本片**未穷举**的接缝之二:语音会话状态机只记了 5 个状态名与 7 个返回成员,状态迁移边没列。 |
| H-A-i | `apps/desktop/src/app/chat/composer/contrib.ts:39`:`microActions: 'composer.microActions'` | 若后续轮次要写"插件如何扩展 composer"的成品章,这一区与 `underside` 是文档里查不到的两块,必须从代码取证。 |

---

## 10. 本片成本自报

```text
片号            : A
层              : L2
文件数 / 行数   : 84 / 18,804
实际打开的文件数: 62          (真读过内容;另 22 个只读了导出面/头部注释,
                               靠 `grep -nE '^export '` 与 awk 抽 interface/docstring)
实际读过的行数  : 约 9,500     (估法:全文读的 21 个文件合计约 6,300 行,
                               其余 41 个按"头部注释 + 接口块 + 返回块"平均 ~80 行计)
底稿字节数      : (主线自测)
主观耗费        : 中偏高。瓶颈有两个,都不是"单文件长":
                  (1) 概念密度 —— 24 个 hook 之间是显式握手(queueEditRef、
                      draftRef、activeQueueSessionKeyRef 在三个引擎间穿),
                      不把握手关系画出来就读不懂任何单个 hook 的返回面;
                  (2) 跨文件追链 —— 判据 3 的链从 contentEditable 一路到
                      `prompt.submit`,中间有 3 跳落在片外
                      (session-tile-actions → use-prompt-actions/submit),
                      为确认锚点行号又读了两个片外文件。
                  单位成本参考:84 文件 / 18,804 行的 L2,约耗 1 个会话档次的预算,
                  其中约三成花在跑 vitest(198s)与 eslint 上等待。
```
