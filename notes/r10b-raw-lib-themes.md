# r10b 片 E · 运行时库、主题、调试与类型面 —— 底稿

> 证据层底稿。求全求证,不追求好读。凡对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313`
> 单独成行、置于代码块之前;非源码块用 ```` ```text ```` / ```` ```verify ```` 显式声明。
> 基线:`NousResearch/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`。
> 本片全部文件在 `apps/desktop/` 下,故下文路径一律从仓库根写起。

---

## 0. 本片范围与逐文件点名

**范围**:126 文件 / 20,540 行 = `src/lib/` 102(含 `src/lib/keybinds/` 4)+ `src/themes/` 11 +
`src/debug/` 10(含一份 README)+ `src/types/hermes.ts` + `src/global.d.ts` + `src/vite-env.d.ts`。

```verify
# 文件数与行数复核(任何人 clone 后可重跑)
wc -l < /home/user/hermes-study/data/r10b/slices/E.txt          # 126
cd /home/user/hermes-agent && while read -r f; do wc -l < "$f"; done \
    < /home/user/hermes-study/data/r10b/slices/E.txt | paste -sd+ | bc   # 20540
```

### 0.1 `src/debug/` —— 10 个文件

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/debug/README.md` | 111 | 这一簇的设计说明:为什么用 bippy 而不是 `<Profiler>` / react-scan,为什么 import 顺序是承重的,一次基线测量的数字 |
| `apps/desktop/src/debug/dev-only.ts` | 19 | dev 入口。`main.tsx` 唯一静态 import 的门面,自身只 `import './index'` |
| `apps/desktop/src/debug/dev-only.noop.ts` | 8 | 生产替身。`vite.config.ts` 把 `@/debug/dev-only` 别名到它,整个 debug 图不进产物 |
| `apps/desktop/src/debug/index.ts` | 36 | 把三个探针(render-counter / perf-live / right-pane-probe)拉进图,并调用 `watchSessionAtoms()` |
| `apps/desktop/src/debug/render-counter.ts` | 308 | `window.__RENDER_COUNTS__`:逐组件归因「这次 commit 为什么重渲染」(props / state / context / 纯父级级联) |
| `apps/desktop/src/debug/atom-churn.ts` | 132 | `window.__ATOM_CHURN__`:逐 nanostores atom 统计通知次数、监听者扇出、以及「值深等但仍通知」的浪费数 |
| `apps/desktop/src/debug/watched-atoms.ts` | 81 | 挑出值得归因的 store 清单(HOT / DERIVED / SIDEBAR 三组),不是全量 atom |
| `apps/desktop/src/debug/perf-live.ts` | 306 | `window.__PERF_LIVE__`:真实交互(拖 resize / 打字)期间的逐帧 + Long Animation Frame 归因 |
| `apps/desktop/src/debug/right-pane-events.ts` | 25 | 右栏性能事件的**类型 + 生产安全打点函数**(`markRightPanePerf`),生产里是空调用 |
| `apps/desktop/src/debug/right-pane-probe.ts` | 58 | 上面那个打点的 dev 侧记录器实现(`window.__RIGHT_PANE_PERF__`) |

### 0.2 类型面 —— 3 个文件

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/types/hermes.ts` | 1417 | 后端 REST/RPC 的**响应体类型总表**,130 个导出;被 225 个文件 import,是全仓被引用最广的类型模块 |
| `apps/desktop/src/global.d.ts` | 946 | `window.hermesDesktop` preload 桥的**类型契约**(94 个顶层成员)+ 64 个 `Desktop*`/`Hermes*` 结构体 |
| `apps/desktop/src/vite-env.d.ts` | 1 | 一行 `/// <reference types="vite/client" />`,把 `import.meta.env` 的类型引进来 |

### 0.3 `src/themes/` —— 11 个文件

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/themes/types.ts` | 101 | 主题数据模型:`DesktopThemeColors`(26 个色令牌)/ `DesktopThemeTypography` / `DesktopTerminalPalette`(19 槽)/ `DesktopTheme` |
| `apps/desktop/src/themes/presets.ts` | 291 | 6 个内置主题(nous / midnight / ember / mono / cyberpunk / slate)+ 默认字体栈 + emoji 兜底字体 |
| `apps/desktop/src/themes/color.ts` | 148 | 颜色数学:hex 解析、mix、WCAG 相对亮度与对比度、`ensureContrast`、带 alpha 压平的 `normalizeHex` |
| `apps/desktop/src/themes/context.tsx` | 413 | `ThemeProvider` + `useTheme`;把主题写成 `:root` CSS 变量、按 profile 分别持久化 skin/mode、开机前置绘制 |
| `apps/desktop/src/themes/skin.ts` | 117 | CLI/TUI 的 **skin**(YAML 调色板)→ `DesktopTheme` 转换器 |
| `apps/desktop/src/themes/backend-sync.ts` | 94 | 后端推来的 skin 的落库与「要不要立即上色」的判定(连接期 seed vs 运行期 apply) |
| `apps/desktop/src/themes/vscode.ts` | 370 | VS Code 颜色主题 JSON(JSONC)→ `DesktopTheme`,含终端 ANSI 16 槽提取 |
| `apps/desktop/src/themes/install.ts` | 92 | 从粘贴文本 / Marketplace 扩展安装主题;把一个扩展的 light+dark 两个变体折成**一个**主题条目 |
| `apps/desktop/src/themes/user-themes.ts` | 193 | 用户安装主题的 localStorage 存储 + `themes` 贡献区 + `resolveTheme` / `listAllThemes` 合并顺序 |
| `apps/desktop/src/themes/use-skin-command.ts` | 60 | `/skin` 斜杠命令的实现(切换 / 循环 / list / 别名) |
| `apps/desktop/src/themes/index.ts` | 6 | 桶文件,只有 7 行再导出 |

### 0.4 `src/lib/` —— 102 个文件(按用途分组;组内逐个列全路径)

**(a) 消息装配与运行时(6)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/chat-messages.ts` | 1174 | 本片最核心:`ChatMessage`/`ChatMessagePart` 模型、流式 delta 合并、tool part upsert、持久消息 → 气泡的重建 |
| `apps/desktop/src/lib/chat-runtime.ts` | 497 | 会话运行时的纯函数杂集:客户端会话初态、斜杠命令解析、附件 ref、`ChatMessage` → assistant-ui `ThreadMessage` |
| `apps/desktop/src/lib/inflight-turn-journal.ts` | 545 | 崩溃可存活的「进行中回合」日记:把可见尾巴节流写 localStorage,恢复时折回 |
| `apps/desktop/src/lib/incremental-external-store-runtime.ts` | 265 | assistant-ui ExternalStore 运行时的增量写版本:只写身份变了的那条消息 |
| `apps/desktop/src/lib/render-weight.ts` | 84 | 一条消息的「渲染成本」计价(字符 + part 数),供 store 窗口与 DOM 分页预算共用 |
| `apps/desktop/src/lib/use-session-slice.ts` | 63 | 只订阅 `Record<sessionId, T[]>` 里**一个会话**那一片的 `useSyncExternalStore` |

**(b) markdown / 代码块 / 数学(5)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/markdown-preprocess.ts` | 520 | 渲染前的文本整形:剥思考块、修补反引号噪声、围栏语言归一、货币 `$` 与数学 `$` 消歧、裸 URL 自动链接 |
| `apps/desktop/src/lib/markdown-code.ts` | 328 | 语言标签清洗、语言/扩展名 → codicon 与 Shiki 语言、以及「这段围栏其实是散文」的启发式 |
| `apps/desktop/src/lib/markdown-blocks.ts` | 138 | 块切分的两级缓存(精确串缓存 + 流式追加增量 lex) |
| `apps/desktop/src/lib/katex-memo.ts` | 260 | 记忆化的 rehype-katex:按 `(displayMode, 公式源码)` LRU 缓存渲染结果 |
| `apps/desktop/src/lib/artifact-detect.ts` | 232 | 判定一个围栏块够不够格升级成右栏 artifact 卡(kind / language / title) |

**(c) 工具结果与终端输出呈现(4)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/tool-result-summary.ts` | 469 | 任意 JSON 工具结果 → 人话摘要;以及从嵌套结构里挖出错误消息 |
| `apps/desktop/src/lib/ansi.ts` | 186 | 最小 ANSI SGR 解析器(颜色/加粗/reset),输出带样式的段数组 |
| `apps/desktop/src/lib/summarize-command.ts` | 216 | shell 命令 → 一行显示用摘要(切复合命令、剥管道尾、去重定向/env 前缀) |
| `apps/desktop/src/lib/todos.ts` | 88 | 工具负载里的 todo 列表解析与「取本会话最新一份」 |

**(d) 媒体、图片、预览(6)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/media.ts` | 194 | 扩展名 → 媒体类型/MIME、`MEDIA:` markdown href 的编解码、远程网关下的取流与下载 |
| `apps/desktop/src/lib/embedded-images.ts` | 204 | 从文本里抽出 base64 data URL 图片(含被截断的 JSON 图片片段),以及 `@image:` ref 抽取 |
| `apps/desktop/src/lib/generated-images.ts` | 114 | 图像生成工具结果 → 展示图,并把模型在正文里重复的路径回声去重 |
| `apps/desktop/src/lib/preview-targets.ts` | 63 | `[Preview:…](#preview:…)` 标记的抽取/剥离/往返编码 |
| `apps/desktop/src/lib/local-preview.ts` | 276 | 本地/远程文件的预览目标解析;远程 HTML 走 DOMPurify + CSP 重写后再展示 |
| `apps/desktop/src/lib/svg-image.ts` | 56 | SVG 字符串栅格化成 PNG 并写剪贴板(mermaid 图的「复制为图片」) |

**(e) 键位(4)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/keybinds/actions.ts` | 243 | 可重绑定热键的**唯一真源**:71 条动作元数据 + 13 条只读展示项 + `keybinds` 贡献区 |
| `apps/desktop/src/lib/keybinds/combo.ts` | 230 | 组合键的规范化(`event.key` 与 `event.code` 各管一半)、`mod`/`ctrl` 折叠、显示标签 |
| `apps/desktop/src/lib/keybinds/composer-focus-keys.ts` | 147 | 软 `/`、Enter 聚焦与「打字即聚焦」的让位规则(对话框/菜单/终端/clarify 卡片) |
| `apps/desktop/src/lib/keybinds/use-keybind-hint.ts` | 36 | 给 tooltip 取「这个动作现在绑在哪个键上」的 hook |

**(f) 语音、唤醒词、声音、触感(10)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/voice-playback.ts` | 516 | TTS 播放:WebSocket + PCM 流式路径与整段 data-URL 回退,含停滞看门狗与自动播放解锁 |
| `apps/desktop/src/lib/voice-barge-in.ts` | 326 | 全双工 VAD 打断监视器:回合期间盯麦克风,触发即打断并把**含前摇**的整句录下来 |
| `apps/desktop/src/lib/voice-stop-word.ts` | 105 | 「整句就是一个停止指令」的识别(保守到 "stop the docker container" 不会被吞) |
| `apps/desktop/src/lib/speech-text.ts` | 167 | 送 TTS 前的文本清洗(剥 emoji / 代码块 / markdown 链接 / 思考前缀) |
| `apps/desktop/src/lib/wake-client-capture.ts` | 234 | 后端无声卡时由桌面端采麦、重采样到 16k 单声道 int16,经 `wake.feed` 回推 |
| `apps/desktop/src/lib/wake-indicator.ts` | 55 | 唤醒指示器窗口的状态机(capturing / detected / hidden) |
| `apps/desktop/src/lib/wake-sound.ts` | 88 | 唤醒词命中的上行两音提示音(WebAudio 合成,不带资源文件) |
| `apps/desktop/src/lib/completion-sound.ts` | 530 | 回合结束提示音库:14 个 WebAudio 合成预设 + 混响/低通链路 + 多窗去重 |
| `apps/desktop/src/lib/thinking-sound.ts` | 108 | 思考期间的循环环境音(填补「无音即死机」的空档) |
| `apps/desktop/src/lib/haptics.ts` | 129 | 触感意图表 + 全局限流(1 秒 5 次),避免上游风暴把触控板震成蜂鸣 |

**(g) 会话列表 / 会话引用(9)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/session-branch-tree.ts` | 124 | 侧栏会话的分支树扁平化(父会话 + 分支子项) |
| `apps/desktop/src/lib/session-date-groups.ts` | 150 | 侧栏的日期分隔行与会话行交织成一个扁平列表 |
| `apps/desktop/src/lib/session-source.ts` | 130 | 会话来源(23 个平台标签)归一化、消息类来源判定、搜索词 |
| `apps/desktop/src/lib/session-search.ts` | 23 | 侧栏搜索命中判定(标题 / 预览 / 来源) |
| `apps/desktop/src/lib/session-signatures.ts` | 54 | 轮询用的廉价签名比较,内容没变就不换原子引用 |
| `apps/desktop/src/lib/session-refs.ts` | 118 | `@session:<profile>/<id>` 引用的纯解析/编码(刻意不依赖 React 与 store) |
| `apps/desktop/src/lib/session-link-title.ts` | 143 | 上面那个引用的**有状态**标题解析(进程级缓存 + 在途去重 + 订阅) |
| `apps/desktop/src/lib/session-ids.ts` | 26 | 通知里的 runtime session id → 路由用的 stored session id |
| `apps/desktop/src/lib/session-export.ts` | 59 | 把一个会话导出成 markdown 文件下载 |

**(h) 桌面/网关桥接(9)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/desktop-fs.ts` | 191 | 文件系统门面:本地走 Electron IPC,远程网关走 REST `/api/fs/*`,同一套函数签名 |
| `apps/desktop/src/lib/desktop-git.ts` | 109 | 同上的 git 版本(worktree / 分支 / 状态 / review) |
| `apps/desktop/src/lib/desktop-remote-auth.ts` | 26 | 远程网关认证提供方的展示形态推导(是否密码、显示名) |
| `apps/desktop/src/lib/desktop-toolsets.ts` | 24 | 桌面 Toolsets 列表的黑名单(5 个:平台耦合 + 内部管线) |
| `apps/desktop/src/lib/gateway-events.ts` | 158 | 网关事件的会话归属判定(切走聊天后未加 session_id 的事件仍钉在原会话)+ 日志项构造 |
| `apps/desktop/src/lib/gateway-rpc.ts` | 21 | 三个 RPC 错误形状识别器(方法不存在 / 挂起请求已消失 / 忙时切模型被拒) |
| `apps/desktop/src/lib/oneshot.ts` | 58 | 走会话之外的一次性 LLM 调用客户端(commit message、改名建议之类) |
| `apps/desktop/src/lib/yolo-session.ts` | 76 | 会话级 YOLO(审批绕过)的 `config.set` 开关,不动全局 `approvals.mode` |
| `apps/desktop/src/lib/runtime-readiness.ts` | 152 | 「后端到底能不能跑」的信号汇总与解释(provider 配没配、runtime check 过没过) |

**(i) 斜杠命令与 MCP(4)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/desktop-slash-commands.ts` | 626 | 桌面斜杠命令的唯一真源:35 条 canonical + 41 条「无桌面界面」+ 15 个别名 |
| `apps/desktop/src/lib/slash-completion-cache.ts` | 107 | `/` 补全响应的 React Query 缓存键与失效纪元 |
| `apps/desktop/src/lib/mcp-tool-filter.ts` | 61 | MCP server 的 `tools.include` / `tools.exclude` 逐工具门控(镜像 `tools/mcp_tool.py`) |
| `apps/desktop/src/lib/mcp-dashboard-oauth.ts` | 71 | MCP server OAuth 流程的轮询驱动(start → 开浏览器 → 轮询 status) |

**(j) 模型与 provider(5)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/model-options.ts` | 78 | 模型目录查询键、以及「持久化的手动选型已从目录里消失」的保守判定 |
| `apps/desktop/src/lib/model-search-text.ts` | 30 | 模型搜索的别名扩展(`k3` → `kimi-k3 kimi`),不改 wire id |
| `apps/desktop/src/lib/model-status-label.ts` | 124 | 状态栏/选择器上的模型显示名与「当前选中的是哪一对 (provider, model)」 |
| `apps/desktop/src/lib/reasoning-effort.ts` | 54 | 7 档思考强度枚举 + 标签 + 解析(镜像后端 `hermes_constants.py`) |
| `apps/desktop/src/lib/provider-setup-errors.ts` | 14 | 「这条错误其实是没配 API key」的识别 |

**(k) 图标与品牌(2)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/icons.ts` | 269 | 123 个 Tabler 图标的精选别名 + `iconSize` 5 档尺寸标度 |
| `apps/desktop/src/lib/brand-icon.ts` | 429 | 191 个注册域 → 167 个 simple-icons 品牌标 的查表(后缀回退) |

**(l) 输入设备与交互原语(8)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/input-modality.ts` | 26 | 记录「最近一次交互是鼠标还是键盘」,用来限定 `:focus-visible` |
| `apps/desktop/src/lib/middle-click.ts` | 64 | 中键(与 macOS 上的 ⌘ 点击)关闭手势的 pointerdown/up 配对 |
| `apps/desktop/src/lib/trackpad-gestures.ts` | 50 | macOS 上 pinch-zoom 与 smart-zoom 都伪装成 `wheel+ctrlKey` 的消歧 |
| `apps/desktop/src/lib/drag-ghost.ts` | 43 | 跟随指针的拖拽小票(纯 DOM,不经 React) |
| `apps/desktop/src/lib/reorder.ts` | 33 | 横向拖拽重排的统一手感参数(弹簧、过渡、触感节拍) |
| `apps/desktop/src/lib/escape-layers.ts` | 53 | Esc 的分层归属(5 层优先级),让一次 Esc 只做一件事 |
| `apps/desktop/src/lib/find-in-page.ts` | 109 | ⌘F 查找条的纯逻辑:计数投影、条内按键路由、以及它**占用**哪些组合键 |
| `apps/desktop/src/lib/use-enter-animation.ts` | 110 | 只在首次挂载放一次的入场动画(Web Animations API,躲开 CSS transition 的重放) |

**(m) 格式化与文本(9)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/text.ts` | 15 | 五个文本微工具(`asText`/`includesQuery`/`prettyName`/`normalize`/`capitalize`),被 103 个文件 import |
| `apps/desktop/src/lib/format.ts` | 24 | 唯一的紧凑数字格式化(`1230 → 1.2k`) |
| `apps/desktop/src/lib/time.ts` | 238 | 唯一的时间/日期格式化与相对时间、日历分桶(共享 `Intl` 实例) |
| `apps/desktop/src/lib/display-path.ts` | 157 | 路径显示归一(home → `~`),只影响显示不影响真实路径 |
| `apps/desktop/src/lib/sanitize.ts` | 21 | 逐键入生效的标识符整形(git ref、slug) |
| `apps/desktop/src/lib/json-format.ts` | 15 | `JSON.stringify(JSON.parse(x), null, 2)` 的带错版本 |
| `apps/desktop/src/lib/composer-input-sanitize.ts` | 74 | 剥掉终端 bracketed-paste 泄漏标记与重复粘贴尾巴(镜像 `hermes_cli/input_sanitize.py`) |
| `apps/desktop/src/lib/statusbar.tsx` | 81 | 状态栏的时长/路径/上下文条格式化 + 一个自走时的 `LiveDuration` |
| `apps/desktop/src/lib/profile-color.ts` | 55 | profile 名 → 稳定色相(不持久化,纯哈希) |

**(n) 存储与状态原语(5)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/storage.ts` | 158 | 全应用持久化的**唯一咽喉**:`readKey`/`writeKey` + 事件订阅 + 若干类型化读写 |
| `apps/desktop/src/lib/persisted.ts` | 78 | 自动读写 localStorage 的 nanostores 原子(经上面那个咽喉) |
| `apps/desktop/src/lib/query-client.ts` | 48 | 共享的 React Query client 与 profile 作用域失效 |
| `apps/desktop/src/lib/stable-array.ts` | 7 | 元素相同就保留旧引用(并冻结新数组),让 `computed` 跳过发射 |
| `apps/desktop/src/lib/mutable-ref.ts` | 6 | 一行的 ref 写入函数;它同时是 eslint 规则显式点名的对象 |

**(o) 杂项工具与内容表(11)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/utils.ts` | 6 | `cn()` = clsx + tailwind-merge;被 246 个文件 import,是全仓被引用最广的模块 |
| `apps/desktop/src/lib/pool.ts` | 20 | 带并发上限的 `Promise.all` |
| `apps/desktop/src/lib/raf-coalesce.ts` | 34 | 把一串值合并成每帧一次 apply |
| `apps/desktop/src/lib/renderer-loop-pause.ts` | 50 | 窗口最小化/失焦时暂停轮询循环的控制器 |
| `apps/desktop/src/lib/reconnect-backoff.ts` | 45 | 全抖动指数退避(AWS "Exponential Backoff And Jitter"),避免重连风暴 |
| `apps/desktop/src/lib/remote-url.ts` | 22 | 无 scheme 的 `host:port` 补 `http://`(与 electron 侧同源规则) |
| `apps/desktop/src/lib/clipboard.ts` | 28 | 把 `navigator.clipboard.writeText` 改道走 Electron IPC(失焦时原生 API 会抛权限错) |
| `apps/desktop/src/lib/download-text.ts` | 16 | blob 下载保存文本 |
| `apps/desktop/src/lib/excluded-paths.ts` | 44 | 文件树/review 树永远隐藏的 34 个目录名 |
| `apps/desktop/src/lib/selectable-card.ts` | 31 | 可选卡片的三态类名(active / prominent / muted) |
| `apps/desktop/src/lib/loadout.ts` | 279 | 通用二进制分享码编解码器(位打包 + DEFLATE + 校验和 + base64url) |

**(p) 版本、更新、模板(5)**

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/lib/commit-changelog.ts` | 179 | Conventional Commits 头解析 + 面向用户的变更分组(内联实现,不依赖 npm 包) |
| `apps/desktop/src/lib/update-copy.ts` | 44 | 更新弹层「有新版本」文案的纯选择逻辑(客户端 vs 远端后端) |
| `apps/desktop/src/lib/version-status.ts` | 106 | 版本标签/tooltip/是否有更新 的纯推导,状态栏与命令面板共用 |
| `apps/desktop/src/lib/project-idea-templates.ts` | 116 | 新建项目对话框的 18 条点子模板(纯内容) |
| `apps/desktop/src/lib/external-link.tsx` | 331 | 外链的规范化、标题解析、品牌标、`ExternalLink`/`PrettyLink`/`LinkifiedText` 组件;**桌面端把 URL 交给外部程序的入口** |

---

## 1. 这一簇解决什么问题

这 126 个文件不是一个机制,是一层。它承担的事情可以归成五类:

1. **把网关的线上格式翻译成 UI 能画的东西。** `chat-messages.ts` / `chat-runtime.ts` /
   `tool-result-summary.ts` / `markdown-*.ts` 一整条链,输入是网关的 JSON-RPC 事件与持久化消息行,
   输出是 assistant-ui 的 `ThreadMessage`。
2. **把「同一件事在本地和远程网关上要走不同通道」这件事收敛到门面里。**
   `desktop-fs.ts` / `desktop-git.ts` / `media.ts` 都是同一个手法:本地走 `window.hermesDesktop.*`,
   远程走 REST,调用方看不出区别。
3. **把散落的手感规则做成单一真源。** 键位表、Esc 分层、触感意图、图标别名、时间格式、
   紧凑数字——每一个都在文件头写明「不要在别处重新实现」。
4. **主题:一份调色板要同时喂三个界面。** CLI 的 skin(YAML)、VS Code 的主题 JSON、
   桌面自己的 6 个内置主题,统一收敛成 `DesktopTheme`,再展开成 CSS 变量。
5. **性能自证工具。** `src/debug/` 不是日志,是四个可以给出**归因**的计数器,
   并且用构建期别名保证它们不进产物。

---

## 2. 接缝穷举

### 2.0 口径声明(与派工书 §3 判据 2 的差异)

派工书判据 2 原文是「每个对外接缝(IPC 通道表 / 路由表 / store action 面 / 组件 props 契约 /
导出面 / 事件表)逐项列全」。**本片没有一个统一的接缝**——`lib/` 是 102 个互不相干的小库。
按本片专属说明给的口径,我把判据 2 落成三件事,**三件都逐项列全、都给机械枚举命令**:

- **E-1 导出面**:123 个 `.ts/.tsx` 的每一个导出符号 + 它被多少个文件 import(§2.1)。
- **E-2 类型契约面**:`global.d.ts` 的 94 个桥成员 + 64 个结构体;`types/hermes.ts` 的 130 个类型(§2.2)。
- **E-3 库内数据表**:本片里「表即行为」的 30 张常量表,逐张给条数(§2.3)。

另外,`src/debug/` 有一个真正意义上的对外接缝——4 个 `window.__*__` 全局对象——单独在 §2.4 列全。

### 2.1 E-1:导出面(123 文件 / 809 个导出符号)

```verify
python3 /home/user/hermes-study/data/r10b/probes/probe_e_exports.py /home/user/hermes-agent \
  | tail -n +2 | wc -l                                            # 123 文件
python3 /home/user/hermes-study/data/r10b/probes/probe_e_exports.py /home/user/hermes-agent \
  | awk -F'\t' 'NR>1{s+=$2} END{print s}'                         # 809 个导出
```

下表三列是:**文件全路径 / 导出数 / 被多少个文件 import / 导出符号**。
`n_importers` 的口径见探针文件头(按模块说明符 grep,按文件去重,不含自身),
它对 `index.ts` 这类桶文件会偏高(命中的是目录名),对同名 basename 会偏高——
**它是量级指示,不是精确调用图**,精确调用图不是本片的交付物。

```text
### A. 导出面主表(123 个 .ts/.tsx)

apps/desktop/src/debug/atom-churn.ts                         2    1  AtomChurn,watchAtom
apps/desktop/src/debug/dev-only.noop.ts                      0    0  
apps/desktop/src/debug/dev-only.ts                           0    0  
apps/desktop/src/debug/index.ts                              0   25  
apps/desktop/src/debug/perf-live.ts                          0    0  
apps/desktop/src/debug/render-counter.ts                     1    0  RenderRecord
apps/desktop/src/debug/right-pane-events.ts                  3    5  RightPanePerfEvent,RightPanePerfSnapshot,markRightPanePerf
apps/desktop/src/debug/right-pane-probe.ts                   0    0  
apps/desktop/src/debug/watched-atoms.ts                      1    1  watchSessionAtoms
apps/desktop/src/lib/ansi.ts                                 6    4  AnsiSegment,AnsiColor,parseAnsi,ansiColorClass,hasAnsiCodes,stripAnsi
apps/desktop/src/lib/artifact-detect.ts                      6    6  ArtifactKind,ArtifactDetection,detectArtifact,artifactSlug,artifactContentHash,artifactDownloadName
apps/desktop/src/lib/brand-icon.ts                           2    3  BrandIcon,resolveBrandIcon
apps/desktop/src/lib/chat-messages.ts                       20   47  ChatMessagePart,ChatMessage,GatewayEventPayload,textPart,reasoningPart,renderMediaTags,assistantTextPart,chatMessageText,UnspokenTurnSpeech,collectUnspokenTurnSpeech,mergeFinalAssistantText,messageReactions,appendTextPart,appendReasoningPart,appendAssistantTextPart,hasToolPart,upsertToolPart,toChatMessages,preserveLocalAssistantErrors,branchGroupForUser
apps/desktop/src/lib/chat-runtime.ts                        22   53  SLASH_COMMAND_RE,BUILTIN_PERSONALITIES,createClientSessionState,sessionTitle,coerceGatewayText,coerceThinkingText,isImageGenerationTool,contextPath,attachmentId,pathLabel,attachmentDisplayText,optimisticAttachmentRef,personalityNamesFromConfig,normalizePersonalityValue,parseSlashCommand,parseCommandDispatch,quickModelOptions,messageCreatedAt,toRuntimeMessage,ToolMergeCache,createToolMergeCache,coalesceToolOnlyAssistants
apps/desktop/src/lib/clipboard.ts                            1    4  installClipboardShim
apps/desktop/src/lib/commit-changelog.ts                     6    2  CommitGroupId,CommitGroup,ParsedCommit,CommitChangelogInput,parseCommitHeader,buildCommitChangelog
apps/desktop/src/lib/completion-sound.ts                     4    2  CompletionSoundVariant,COMPLETION_SOUND_VARIANTS,previewCompletionSound,playCompletionSound
apps/desktop/src/lib/composer-input-sanitize.ts              3    6  stripLeakedBracketedPasteWrappers,collapseRepeatedInputArtifacts,sanitizeComposerInput
apps/desktop/src/lib/desktop-fs.ts                          17   16  DesktopFsRemotePicker,setDesktopFsRemotePicker,desktopFsCacheKey,isDesktopFsRemoteMode,desktopFsProfile,readDesktopDir,readDesktopFileText,writeDesktopFileText,readDesktopFileDataUrl,desktopGitRoot,desktopDefaultCwd,revealDesktopPath,renameDesktopPath,trashDesktopPath,copyTextToClipboard,desktopFileDiff,selectDesktopPaths
apps/desktop/src/lib/desktop-git.ts                          1    5  desktopGit
apps/desktop/src/lib/desktop-remote-auth.ts                  2    3  RemoteAuthProviderShape,deriveRemoteAuthProviderShape
apps/desktop/src/lib/desktop-slash-commands.ts              26    6  CommandsCatalogSection,CommandsCatalogLike,SkillCatalogEntry,SkillCatalogMap,DesktopSlashCompletion,DesktopThemeCommandOption,DesktopActionId,DesktopPickerId,DesktopUnavailableReason,DesktopCommandSurface,SlashCommandBuildCtx,DesktopSlashArgumentMode,DesktopCommandSpec,canonicalDesktopSlashCommand,resolveDesktopCommand,isDesktopSlashExtensionCommand,isDesktopSlashCommand,isDesktopSlashSuggestion,isPickerCommand,isModelPickerCommand,desktopSlashUnavailableMessage,desktopSlashDescription,desktopSlashCommandArgumentMode,desktopSkinSlashCompletions,rankSkillCommands,filterDesktopCommandsCatalog
apps/desktop/src/lib/desktop-toolsets.ts                     1    2  isDesktopToolsetVisible
apps/desktop/src/lib/display-path.ts                         4   11  DisplayPathOptions,normalizeDisplayPath,displayPath,pathLeaf
apps/desktop/src/lib/download-text.ts                        1    1  downloadTextFile
apps/desktop/src/lib/drag-ghost.ts                           2    1  DragGhost,createDragGhost
apps/desktop/src/lib/embedded-images.ts                      7    7  DATA_IMAGE_URL_RE,EmbeddedImageExtraction,dataUrlToBlob,extractEmbeddedImages,embeddedImageUrls,textWithoutEmbeddedImages,extractImageRefs
apps/desktop/src/lib/escape-layers.ts                        3    7  ESCAPE_PRIORITY,pushEscapeLayer,isTopEscapeLayer
apps/desktop/src/lib/excluded-paths.ts                       2    2  ALWAYS_EXCLUDED,isExcludedPath
apps/desktop/src/lib/external-link.tsx                      14   18  normalizeExternalUrl,shortHostLabel,hostPathLabel,urlSlugTitleLabel,isTitleFetchable,fetchLinkTitle,useLinkTitle,openExternalLink,ExternalLinkIcon,LinkBrandIcon,ExternalLink,PrettyLink,LinkifiedText,__resetLinkTitleCache
apps/desktop/src/lib/find-in-page.ts                         5    5  formatMatchLabel,FindBarKeyAction,FindBarKeyEvent,findBarKeyAction,findBarClaimsCombo
apps/desktop/src/lib/format.ts                               1   11  compactNumber
apps/desktop/src/lib/gateway-events.ts                       6    3  gatewayEventRequiresSessionId,GatewayEventSessionRouteInput,GatewayEventSessionRoute,resolveGatewayEventSessionId,gatewayEventCompletedFileDiff,buildGatewayLogItems
apps/desktop/src/lib/gateway-rpc.ts                          3    6  isMissingRpcMethod,isMissingPendingPromptRequest,isBusySessionModelSwitch
apps/desktop/src/lib/generated-images.ts                     4    5  generatedImageFromResult,generatedImageEchoSources,stripGeneratedImageEchoes,dedupeGeneratedImageEchoesInParts
apps/desktop/src/lib/haptics.ts                              4   57  HapticIntent,HapticTrigger,registerHapticTrigger,triggerHaptic
apps/desktop/src/lib/icons.ts                              125  115  (见下 A-2 / A-3 单列)
apps/desktop/src/lib/incremental-external-store-runtime.ts   2    5  syncRepositoryIncrementally,useIncrementalExternalStoreRuntime
apps/desktop/src/lib/inflight-turn-journal.ts                8    3  InFlightTurnSnapshot,JournalableSessionState,InFlightRecoveryResult,mergeInFlightMessages,persistInFlightTurnState,readInFlightTurnJournal,recoverInFlightTurnJournal,clearInFlightTurnJournal
apps/desktop/src/lib/input-modality.ts                       2    2  InputModality,lastInputModality
apps/desktop/src/lib/json-format.ts                          2    2  FormatJsonResult,tryFormatJson
apps/desktop/src/lib/katex-memo.ts                           1    1  createMemoizedMathPlugin
apps/desktop/src/lib/keybinds/actions.ts                    18   48  KeybindCategory,KEYBIND_PANEL_ACTION,KEYBIND_CATEGORIES,KeybindActionMeta,PROFILE_SLOT_COUNT,SESSION_SLOT_COUNT,KEYBIND_ACTIONS,KEYBIND_ACTION_IDS,KEYBINDS_AREA,KeybindContribution,contributedKeybinds,allKeybindActions,keybindAction,contributedKeybindHandler,KeybindBindings,defaultBindings,KeybindReadonly,KEYBIND_READONLY
apps/desktop/src/lib/keybinds/combo.ts                       8   13  IS_MAC,comboFromEvent,canonicalizeCombo,comboTokens,formatCombo,isFocusWithin,isEditableTarget,comboAllowedInInput
apps/desktop/src/lib/keybinds/composer-focus-keys.ts         6    2  isComposerFocusSoftCombo,isActivateOnEnterTarget,clarifyCardOwnsKey,composerFocusBlockedBySurface,typeToFocusChar,composerFocusKeysAllowed
apps/desktop/src/lib/keybinds/use-keybind-hint.ts            1    2  useKeybindHint
apps/desktop/src/lib/loadout.ts                              9    1  BitWriter,BitReader,Dict,idxOf,indexBits,LoadoutError,Loadout,LoadoutSpec,createLoadout
apps/desktop/src/lib/local-preview.ts                        5    9  validatedRemoteHtmlDataUrl,remoteHtmlPreviewDocument,openPreviewTargetInBrowser,localPreviewTarget,normalizeOrLocalPreviewTarget
apps/desktop/src/lib/markdown-blocks.ts                      1    2  parseMarkdownIntoBlocksCached
apps/desktop/src/lib/markdown-code.ts                        6    8  sanitizeLanguageTag,codiconForLanguage,codiconForFilename,shikiLanguageForFilename,isLikelyProseFence,isLikelyProseCodeBlock
apps/desktop/src/lib/markdown-preprocess.ts                  1    3  preprocessMarkdown
apps/desktop/src/lib/mcp-dashboard-oauth.ts                  2    2  McpOAuthFlow,completeMcpDesktopOAuth
apps/desktop/src/lib/mcp-tool-filter.ts                      5    2  McpToolsFilter,readToolsFilter,isToolEnabled,toggleToolInServer,countEnabledTools
apps/desktop/src/lib/media.ts                               16    7  MediaKind,mediaKind,mediaMime,mediaName,mediaMarkdownHref,isInlineMediaSrc,resolveMediaDisplaySrc,resolveMediaPlaybackSrc,mediaExternalUrl,mediaStreamUrl,mediaPathFromMarkdownHref,filePathFromMediaPath,isRemoteGateway,gatewayMediaDataUrl,downloadGatewayMediaFile,mediaDisplayLabel
apps/desktop/src/lib/middle-click.ts                         2    4  isMetaClose,middleClickHandlers
apps/desktop/src/lib/model-options.ts                        3   11  manualPickRemoved,modelOptionsQueryKey,requestModelOptions
apps/desktop/src/lib/model-search-text.ts                    1    1  modelSearchText
apps/desktop/src/lib/model-status-label.ts                   5    7  currentPickerSelection,modelBaseId,modelDisplayParts,displayModelName,formatModelStatusLabel
apps/desktop/src/lib/mutable-ref.ts                          1    3  setMutableRef
apps/desktop/src/lib/oneshot.ts                              2    1  OneShotRequest,requestOneShot
apps/desktop/src/lib/persisted.ts                            3    9  Codec,Codecs,persistentAtom
apps/desktop/src/lib/pool.ts                                 1    2  mapPool
apps/desktop/src/lib/preview-targets.ts                      6    6  stripPreviewTargets,extractPreviewTargets,previewMarkdownHref,previewTargetFromMarkdownHref,previewName,previewDisplayLabel
apps/desktop/src/lib/profile-color.ts                        4    7  profileColor,resolveProfileColor,PROFILE_SWATCHES,profileColorSoft
apps/desktop/src/lib/project-idea-templates.ts               3    1  ProjectIdeaTemplate,PROJECT_IDEA_TEMPLATES,randomIdeaTemplates
apps/desktop/src/lib/provider-setup-errors.ts                1    5  isProviderSetupErrorMessage
apps/desktop/src/lib/query-client.ts                         3   12  queryClient,writeCache,invalidateProfileScopedQueries
apps/desktop/src/lib/raf-coalesce.ts                         1    2  rafCoalesce
apps/desktop/src/lib/reasoning-effort.ts                     8    9  REASONING_EFFORTS,ReasoningEffort,REASONING_EFFORT_VALUES,DEFAULT_REASONING_EFFORT,reasoningEffortLabel,isReasoningEffort,isThinkingEnabled,resolveReasoningEffort
apps/desktop/src/lib/reconnect-backoff.ts                    2    4  ReconnectBackoffOptions,reconnectBackoffDelayMs
apps/desktop/src/lib/remote-url.ts                           1    3  coerceRemoteUrlScheme
apps/desktop/src/lib/render-weight.ts                        2    4  RENDER_WEIGHT_CHARS,messageRenderWeight
apps/desktop/src/lib/renderer-loop-pause.ts                  1    5  createRendererLoopPauseController
apps/desktop/src/lib/reorder.ts                              7    2  REORDER_SPRING,REORDER_RAIL_DURATION_MS,REORDER_RAIL_TRANSITION,REORDER_RAIL_TRANSITION_CSS,REORDER_DRAG_TRANSITION_CSS,reorderStepHaptic,reorderCommitHaptic
apps/desktop/src/lib/runtime-readiness.ts                    9    6  SetupStatusSnapshot,RuntimeCheckSnapshot,RuntimeReadinessSignals,RuntimeReadinessOptions,RuntimeReadinessResult,RuntimeReadinessRequester,fetchRuntimeReadinessSignals,interpretRuntimeReadiness,evaluateRuntimeReadiness
apps/desktop/src/lib/sanitize.ts                             2   10  gitRef,slug
apps/desktop/src/lib/selectable-card.ts                      2    4  SelectableCardState,selectableCardClass
apps/desktop/src/lib/session-branch-tree.ts                  3    4  SidebarSessionEntry,FlattenSessionsOptions,flattenSessionsWithBranches
apps/desktop/src/lib/session-date-groups.ts                  3    3  SidebarListRow,groupEntriesByRecency,toSessionRows
apps/desktop/src/lib/session-export.ts                       1    2  exportSession
apps/desktop/src/lib/session-ids.ts                          1    2  storedSessionIdForNotification
apps/desktop/src/lib/session-link-title.ts                   4    4  lookupLocalSessionTitle,fetchSessionLinkTitle,useSessionLinkTitle,__resetSessionLinkTitleCache
apps/desktop/src/lib/session-refs.ts                         8    6  SESSION_REF_RE,splitSessionRefValue,parseSessionRefValue,sessionRefCacheKey,sessionRefFallbackLabel,sessionMarkdownHref,sessionRefFromMarkdownHref,linkifySessionRefs
apps/desktop/src/lib/session-search.ts                       1    2  sessionMatchesSearch
apps/desktop/src/lib/session-signatures.ts                   2    3  sameCronSignature,sessionMessagesSignature
apps/desktop/src/lib/session-source.ts                       7    6  LOCAL_SESSION_SOURCE_IDS,MESSAGING_SESSION_SOURCE_IDS,isMessagingSource,normalizeSessionSource,handoffOriginSource,sessionSourceLabel,sessionSourceSearchTerms
apps/desktop/src/lib/slash-completion-cache.ts               7    6  cachedSlashCompletion,hasCachedSlashCompletion,peekCachedSlashCompletion,cachedPathCompletion,hasCachedPathCompletion,$slashCompletionsEpoch,invalidateSlashCompletions
apps/desktop/src/lib/speech-text.ts                          1    2  sanitizeTextForSpeech
apps/desktop/src/lib/stable-array.ts                         1    2  stableArray
apps/desktop/src/lib/statusbar.tsx                           6    1  formatDuration,compactPath,contextBar,usageContextLabel,contextBarLabel,LiveDuration
apps/desktop/src/lib/storage.ts                             16   34  PersistenceEvent,onPersistenceEvent,readKey,writeKey,readJson,writeJson,storedBoolean,persistBoolean,storedString,persistString,storedStringArray,persistStringArray,storedStringRecord,persistStringRecord,arraysEqual,insertUniqueId
apps/desktop/src/lib/summarize-command.ts                    1    3  summarizeShellCommand
apps/desktop/src/lib/svg-image.ts                            2    1  svgToPngBlob,copySvgAsPng
apps/desktop/src/lib/text.ts                                 5  103  asText,includesQuery,prettyName,normalize,capitalize
apps/desktop/src/lib/thinking-sound.ts                       3    2  isThinkingSoundActive,startThinkingSound,stopThinkingSound
apps/desktop/src/lib/time.ts                                25   75  SECOND,MINUTE,HOUR,DAY,fmtClock,fmtDayTime,fmtDateTime,fmtDate,fmtMonth,fmtMonthYear,relativeTime,SessionBucketKind,SessionBucket,SessionBucketLabels,startOfLocalDay,DAY_ROLLOVER_HOUR,nominalDayStart,localeWeekStartDay,startOfLocalWeek,calendarBucket,sessionBucketLabel,ElapsedUnit,coarseElapsed,AgoLabels,formatAgo
apps/desktop/src/lib/todos.ts                                5   15  TodoStatus,TodoItem,parseTodos,todosFromMessageContent,latestSessionTodos
apps/desktop/src/lib/tool-result-summary.ts                  2    2  formatToolResultSummary,extractToolErrorMessage
apps/desktop/src/lib/trackpad-gestures.ts                    5    2  WheelLike,isSmartZoomWheel,isPinchZoomWheel,DOUBLE_TAP_MS,createDoubleTapDetector
apps/desktop/src/lib/update-copy.ts                          5    3  UpdateTarget,UpdateCopyStrings,ResolveUpdateCopyInput,UpdateCopyResult,resolveUpdateCopy
apps/desktop/src/lib/use-enter-animation.ts                  1    5  useEnterAnimation
apps/desktop/src/lib/use-session-slice.ts                    2   10  useSessionSlice,useStoreSelector
apps/desktop/src/lib/utils.ts                                1  246  cn
apps/desktop/src/lib/version-status.ts                       4    3  VersionStatusCopy,VersionStatusInput,VersionStatusResult,resolveVersionStatus
apps/desktop/src/lib/voice-barge-in.ts                       2    2  BargeMonitorCallbacks,monitorSpeechDuringPlayback
apps/desktop/src/lib/voice-playback.ts                       8    6  VoicePlaybackOptions,stopVoicePlayback,SpeechStreamSession,startSpeechStream,playSpeechText,isVoicePlaybackActive,markVoicePlaybackInterrupted,takeVoicePlaybackInterrupted
apps/desktop/src/lib/voice-stop-word.ts                      2    3  isVoiceStopCommand,interceptsTypedVoiceStop
apps/desktop/src/lib/wake-client-capture.ts                  4    1  WakeFeedRequester,ClientWakeCaptureOptions,ClientWakeCaptureHandle,startClientWakeCapture
apps/desktop/src/lib/wake-indicator.ts                       5    6  WakeIndicatorState,WakeIndicatorVoiceStatus,activateWakeIndicator,syncWakeIndicatorWithVoice,clearWakeIndicator
apps/desktop/src/lib/wake-sound.ts                           1    2  playWakeSound
apps/desktop/src/lib/yolo-session.ts                         4    3  GatewayRequester,setSessionYolo,setGlobalYolo,setYoloEnabled
apps/desktop/src/themes/backend-sync.ts                      4    6  $backendThemes,$pendingSkinApply,__resetBackendSkinSync,ingestBackendSkin
apps/desktop/src/themes/color.ts                             9   18  hexToRgb,rgbToHex,mix,relativeLuminance,contrastRatio,readableOn,ensureContrast,luminance,normalizeHex
apps/desktop/src/themes/context.tsx                          6   26  ThemeMode,skinPref,modePref,getBaseColors,ThemeProvider,useTheme
apps/desktop/src/themes/index.ts                             7   25  ingestBackendSkin,ThemeProvider,useTheme,BUILTIN_THEME_LIST,BUILTIN_THEMES,DEFAULT_SKIN_NAME,skinToDesktopTheme
apps/desktop/src/themes/install.ts                           4    5  MARKETPLACE_ID_RE,installVscodeThemeFromText,buildThemeFromMarketplace,installVscodeThemeFromMarketplace
apps/desktop/src/themes/presets.ts                          11   12  EMOJI_FALLBACK,DEFAULT_TYPOGRAPHY,nousTheme,midnightTheme,emberTheme,monoTheme,cyberpunkTheme,slateTheme,BUILTIN_THEMES,BUILTIN_THEME_LIST,DEFAULT_SKIN_NAME
apps/desktop/src/themes/skin.ts                              1    4  skinToDesktopTheme
apps/desktop/src/themes/types.ts                             4  146  DesktopThemeColors,DesktopThemeTypography,DesktopTerminalPalette,DesktopTheme
apps/desktop/src/themes/use-skin-command.ts                  1    1  useSkinCommand
apps/desktop/src/themes/user-themes.ts                      10    8  $userThemes,installUserTheme,removeUserTheme,isUserTheme,marketplaceIdOf,$marketplaceInstalls,THEMES_AREA,contributedThemes,resolveTheme,listAllThemes
apps/desktop/src/themes/vscode.ts                            6    3  VscodeColorTheme,ConvertOptions,ConvertResult,vscodeThemeSlug,parseVscodeTheme,convertVscodeColorTheme
apps/desktop/src/types/hermes.ts                           130  225  (见下 A-2 / A-3 单列)

### A-2 icons.ts —— 125 个导出

iconSize IconSize Activity AlertCircle AlertTriangle AppWindow Archive ArchiveOff ArrowUp ArrowUpRight
AtSign AudioLines BarChart3 Bell Bookmark BookmarkFilled Box Brain Bug Check CheckCircle2 CheckIcon
ChevronDown ChevronDownIcon ChevronLeft ChevronLeftIcon ChevronRight ChevronRightIcon CircleIcon
CircleLetterA Clipboard Clock Cloud Command Copy CopyIcon CornerDownLeft Cpu CreditCard Download Ear EarOff
Egg ExternalLink Eye EyeOff FileImage FileText FolderOpen GitBranch GitBranchIcon GitFork GitForkIcon Globe
Hash HelpCircle ImageIcon Info Keyboard KeyRound Layers3 LayoutDashboard Link Link2 LinkIcon Loader2
Loader2Icon Lock LogIn Mail Maximize MessageCircle MessageQuestion MessageSquareText Mic MicOff Monitor
MonitorPlay Moon MoreHorizontal MoreHorizontalIcon MoreVertical NotebookTabs Package Palette PanelBottom
PanelLeftIcon Pause PawPrint Pencil PencilIcon PencilLine Pin Play Plus RefreshCw RefreshCwIcon Save Search
SearchIcon Send Settings Settings2 SlidersHorizontal SmilePlusIcon Square Starmap SteeringWheel StopFilled
Sun Terminal Trash2 Upload Users Volume2 Volume2Icon VolumeX VolumeXIcon Wrench X XIcon Zap ZapFilled ZoomIn
ZoomOut

### A-3 types/hermes.ts —— 130 个导出

ConfigFieldSchema ConfigSchemaResponse AudioTranscriptionResponse AudioSpeakResponse ElevenLabsVoice
ElevenLabsVoicesResponse OAuthProviderStatus OAuthProvider OAuthProvidersResponse OAuthStartResponse
OAuthSubmitResponse OAuthPollResponse MemoryProviderOAuthStatus EnvVarInfo MemoryProviderFieldKind
MemoryProviderFieldOption MemoryProviderField MemoryProviderConfig CustomEndpoint CustomEndpointsResponse
CustomEndpointUpdate CustomEndpointValidationResponse MessagingEnvVarInfo MessagingHomeChannel
MessagingPlatformInfo MessagingPlatformsResponse PairingUser PairingResponse MessagingPlatformUpdate
MessagingPlatformTestResponse WebhookRoute WebhooksResponse WebhookCreatePayload WebhookCreateResponse
WebhookEnableResponse GatewayReadyPayload HermesConfig HermesConfigRecord ModelInfoResponse ModelPricing
ModelOptionProvider ModelCapabilities ModelOptionsResponse PaginatedSessions RpcEvent SessionCreateResponse
SessionInfo TimelineDisplayMetadata MessageReaction SessionMessage SessionMessagesResponse
SessionResumeResponse SessionRuntimeInfo UsageStats StarmapNode StarmapEdge StarmapCluster StarmapMemoryCard
StarmapGraph ContextUsageCategory ContextBreakdown AnalyticsDailyEntry AnalyticsModelEntry AnalyticsResponse
AnalyticsToolEntry AnalyticsSkillEntry AnalyticsSkillsSummary AnalyticsTotals CronJob CronJobCreatePayload
CronJobSchedule CronJobUpdates CronDeliveryTarget AutomationBlueprintField AutomationBlueprint
ProfileCreatePayload ProfileInfo ProfileSetupCommand ProfileDesktopOverlay ProjectFolder ProjectInfo
ProjectsPayload ProfileSoul ProfilesResponse SkillInfo ToolsetInfo ToolEnvVar ToolProviderStatus
ToolProvider WebCapability ToolsetConfig TerminalBackendStatus TerminalBackendInfo TerminalBackendsResponse
ToolsetModel ToolsetModelsResponse ComputerUsePermissionSource ComputerUseCheck ComputerUseStatus
SessionSearchResult SessionSearchResponse LogsResponse PlatformStatus StatusResponse ActionResponse
ActionStatusResponse BackendUpdateCommit BackendUpdateCheckResponse AuxiliaryTaskAssignment
AuxiliaryModelsResponse MoaModelSlot MoaConfigResponse ModelAssignmentRequest StaleAuxAssignment
SkillHubSource SkillHubResult SkillHubInstalledEntry SkillHubSourcesResponse SkillHubSearchResponse
SkillHubPreview SkillHubScanFinding SkillHubScanResult McpServerSummary McpServerTestResponse
McpCatalogEntry McpCatalogResponse MemoryStatusResponse CuratorStatusResponse DebugShareResponse
ModelAssignmentResponse
```

三个数值上的观察:

- **两个「全仓公共设施」**:`apps/desktop/src/lib/utils.ts` 的 `cn()` 被 246 个文件 import,
  `apps/desktop/src/lib/text.ts` 的五个微工具被 103 个。它们各自只有 6 行和 15 行。
- **0 导出但被 25 个文件命中的 `apps/desktop/src/debug/index.ts`**:它确实没有导出,
  25 是 grep 命中了 `@/debug/...` 前缀(桶目录名),不是真有 25 个 importer。
  真实 importer 只有 `apps/desktop/src/debug/dev-only.ts`。
- **4 个 0 导出 0 importer 的文件**:`dev-only.noop.ts`(别名目标)、`perf-live.ts`、
  `right-pane-probe.ts`(纯副作用,靠 `import './perf-live'` 拉进来)、以及
  `render-counter.ts` 只导出一个类型。**副作用模块不会出现在导出面上**,
  这也是本片导出面枚举唯一的盲区,已在 §2.4 用 `window.__*__` 表补齐。

### 2.2 E-2:类型契约面

#### 2.2.1 `apps/desktop/src/global.d.ts` —— preload 桥的 94 个顶层成员

```verify
python3 /home/user/hermes-study/data/r10b/probes/probe_e_global_dts.py /home/user/hermes-agent bridge | tail -1
# total   94
python3 /home/user/hermes-study/data/r10b/probes/probe_e_global_dts.py /home/user/hermes-agent decls | tail -1
# total   64
python3 /home/user/hermes-study/data/r10b/probes/probe_e_global_dts.py /home/user/hermes-agent diff
# declared_in_global_dts  94 / exposed_in_preload  94 / 两个差集都为空
```

`apps/desktop/src/global.d.ts:14 @ 863e313`

```ts
declare global {
  interface Window {
    hermesDesktop: {
```

94 个顶层成员(行号 = `global.d.ts` 里的声明行):

```text
  20 getConnection            27 revalidateConnection    30 touchBackend
  31 getGatewayWsUrl          37 openSessionWindow       41 openWindow
  45 claimAmbientCue          46 wakeIndicator           54 petOverlay
  69 quickEntry               93 getBootProgress         94 getConnectionConfig
  95 saveConnectionConfig     96 applyConnectionConfig   97 testConnectionConfig
  98 sshConfigHosts           99 sshResolveHost         100 probeConnectionConfig
 101 oauthLoginConnectionConfig                         102 oauthLogoutConnectionConfig
 105 cloud                   112 profile                119 api
 120 notify                  121 requestMicrophoneAccess 122 readFileDataUrl
 124 readFileDataUrlForAttach                           126 dataUrlReadMax
 130 readFileText            131 selectPaths            133 selectSavePath
 138 writeClipboard          139 readClipboard          140 saveImageFromUrl
 141 saveImageBuffer         142 saveClipboardImage     143 getPathForFile
 144 normalizePreviewTarget  145 watchPreviewFile       149 watchDirectory
 150 stopPreviewFileWatch    151 setActiveWork          152 setTitleBarTheme
 153 setNativeTheme          154 setTranslucency        155 setKeepAwake
 156 setPreviewShortcutActive                           157 openExternal
 158 openPreviewInBrowser    159 fetchLinkTitle         160 sanitizeWorkspaceCwd
 161 settings                166 zoom                   171 revealLogs
 172 getRecentLogs           173 readDir                174 gitRoot
 176 revealPath              178 openDir                182 desktopPluginsRoot
 184 renamePath              186 writeTextFile          188 trashPath
 190 git                     244 terminal               256 onClosePreviewRequested
 257 onOpenFolderRequested   258 onOpenUpdatesRequested 259 onDeepLink
 262 signalDeepLinkReady     263 onWindowStateChanged   264 onFocusSession
 265 onNotificationAction    266 onPreviewFileChanged   267 onBackendExit
 270 onConnectionApplied     271 onPowerResume          272 getOnBattery
 273 onBatteryChanged        274 onBootProgress         275 getBootstrapState
 276 continueBootstrapLocal  277 resetBootstrap         278 repairBootstrap
 279 cancelBootstrap         280 onBootstrapEvent       281 getVersion
 282 getRemoteDisplayReason  283 updates                290 uninstall
 294 themes                  307 findInPage             308 stopFindInPage
 309 onFoundInPage
```

◇ **类型声明与 preload 实现严格 1:1**。`apps/desktop/electron/preload.ts` 里
`contextBridge.exposeInMainWorld('hermesDesktop', {...})` 的顶层键**恰好也是 94 个,
两个差集都为空**。这是一个没有任何工具强制、却被严格维持的一致性——
`global.d.ts` 是手写的 `declare global`,TypeScript **不会**校验 preload 对象与它一致
(preload 是另一个 tsconfig,`tsconfig.electron.json`,且没有 `satisfies Window['hermesDesktop']` 之类的绑定)。
搜索面:在 `apps/desktop/` 下 grep `satisfies`、`Window\['hermesDesktop'\]`、
`: Window\[` 三种写法,`electron/preload.ts` 一处都没有。

`apps/desktop/electron/preload.ts:141 @ 863e313`

```ts
  openExternal: url => ipcRenderer.invoke('hermes:openExternal', url),
```

`global.d.ts` 里另外 64 个 `interface`/`type` 声明(桥方法的参数与返回体),逐项列全:

```text
 15 interface Window                     314 interface DesktopMarketplaceSearchItem
322 interface DesktopMarketplaceThemeFile   330 interface DesktopMarketplaceThemeResult
336 interface HermesTerminalSession      342 interface HermesTerminalExit
347 interface DesktopVersionInfo         355 type      DesktopUninstallMode
357 interface DesktopUninstallSummary    370 interface DesktopUninstallResult
379 interface DesktopUpdateCommit        386 interface DesktopUpdateStatus
404 type      DesktopUpdateDirtyStrategy 406 interface DesktopUpdateApplyOptions
410 interface DesktopUpdateApplyResult   443 type      DesktopUpdateStage
460 interface DesktopUpdateProgress      468 interface HermesConnection
491 interface HermesTitleBarTheme        497 interface HermesActiveWork
502 interface HermesWindowState          510 interface DesktopActiveProfile
516 interface DesktopConnectionConfig    544 interface DesktopConnectionConfigInput
563 interface DesktopConnectionTestResult   585 interface DesktopSshResolveResult
592 interface DesktopSshHostsResult      596 interface DesktopAuthProvider
606 interface DesktopConnectionProbeResult  615 interface DesktopOauthLoginResult
621 interface DesktopOauthLogoutResult   628 interface DesktopCloudStatus
638 interface DesktopCloudAgent          650 interface DesktopCloudOrg
664 type      DesktopCloudDiscoverResult 668 interface DesktopCloudAgentSignInResult
675 interface DesktopBootProgress        689 interface DesktopBootstrapStageDescriptor
696 type      DesktopBootstrapStageState 698 interface DesktopBootstrapStageResult
706 interface DesktopBootstrapUnsupportedPlatform
713 interface DesktopBootstrapSetupChoice   718 interface DesktopBootstrapState
730 type      DesktopBootstrapEvent      758 interface HermesApiRequest
773 interface HermesNotification         784 interface HermesPreviewTarget
799 interface HermesReadFileTextResult   809 interface HermesPreviewWatch
816 interface HermesGitWorktree          830 interface HermesGitBranch
842 interface HermesGitBaseBranch        850 interface HermesRepoStatusFile
860 interface HermesRepoStatus           885 type      HermesReviewScope
888 interface HermesReviewFile           897 interface HermesReviewList
905 interface HermesReviewPr             913 interface HermesReviewShipInfo
918 interface HermesReadDirEntry         (…余下 8 项见下方命令输出)
```

上表为节省篇幅在 918 行处收尾;完整 64 项用下面这条命令列全(它是本表的生成器):

```verify
python3 /home/user/hermes-study/data/r10b/probes/probe_e_global_dts.py /home/user/hermes-agent decls
```

#### 2.2.2 `apps/desktop/src/types/hermes.ts` —— 130 个后端响应体类型

`apps/desktop/src/types/hermes.ts:538 @ 863e313`

```ts
export interface SessionMessage {
  codex_reasoning_items?: unknown
  content: unknown
```

130 个导出见 §2.1 表末的 A-3 单列。两个结构性事实:

- **13 个导出只在本文件内被引用**(作为别的类型的字段类型),外部零引用:
  `OAuthProviderStatus`、`MemoryProviderFieldKind`、`MemoryProviderFieldOption`、
  `ModelCapabilities`、`TimelineDisplayMetadata`、`StarmapCluster`、`AnalyticsToolEntry`、
  `WebCapability`、`TerminalBackendStatus`、`PlatformStatus`、`BackendUpdateCommit`、
  `AuxiliaryTaskAssignment`、`SkillHubScanFinding`。每一个在本文件内都恰好出现 2 次
  (声明 + 一处引用),所以没有死代码,只是「本可以不 export」。

```verify
cd /home/user/hermes-agent/apps/desktop && python3 - <<'PY'
import re, subprocess
src = open('src/types/hermes.ts', encoding='utf-8').read()
names = re.findall(r'^export (?:interface|type)\s+([A-Za-z_$][\w$]*)', src, re.M)
unused = [n for n in names
          if not [p for p in subprocess.run(['rg','-l','--no-messages','-w',n,
                    'src','electron','e2e','scripts'],capture_output=True,text=True).stdout.split()
                  if p != 'src/types/hermes.ts']]
print(len(names), "declared;", len(unused), "referenced only inside hermes.ts:", unused)
PY
```

- **类型比运行时更保守**:`SessionMessage.display_metadata` 的类型是
  `string | TimelineDisplayMetadata`,而实际读它的地方
  (`apps/desktop/src/lib/chat-messages.ts:348` 的 `parseDisplayMetadata`)把它当
  `unknown` 处理、先 `JSON.parse` 再 `typeof === 'object'` 收窄,并在注释里点名
  「比本应用旧的远端后端会把它当原始 JSON 文本发过来」。这是本片里
  「**类型是意图,不是保证**」这一原则最清楚的一处。

### 2.3 E-3:库内数据表(30 张,逐张给条数)

```verify
python3 /home/user/hermes-study/data/r10b/probes/probe_e_counts.py /home/user/hermes-agent
```

```text
KEYBIND_ACTIONS 字面行         =   44   # actions.ts 表内 `{ id: '`
PROFILE_SLOT_COUNT          =   18   # 生成 profile.switch.N
SESSION_SLOT_COUNT          =    9   # 生成 session.slot.N
KEYBIND_ACTIONS 运行时总数       =   71   # 字面 + 两组生成
KEYBIND_READONLY            =   13   # 只读展示行
KEYBIND_CATEGORIES          =    5   # 分类枚举
CODE_TO_KEY                 =   20   # event.code → 基础键
MODIFIER_CODES              =    8   # 纯修饰键 code
TOKEN_LABELS                =    9   # 显示标签
BUILTIN_THEMES              =    6   # nous midnight ember mono cyberpunk slate
ANSI_TOKENS                 =   16   # VS Code terminal.ansi* → xterm ITheme 槽
DesktopThemeColors 字段       =   26   # 主题色令牌
DesktopTerminalPalette 字段   =   19   # 终端调色板槽
icons.ts Tabler 别名          =  123   # IconX as X
iconSize 档位                 =    5   # xs..xl
BRAND_ICONS 域名键             =  191   # 注册域 → 品牌图标
BRAND_ICONS 去重组件            =  167   # simple-icons 组件
COMPLETION_SOUND_VARIANTS   =   14   # 回合结束提示音预设
ESCAPE_PRIORITY             =    5   # Esc 归属层
CODICON_BY_LANGUAGE         =   40   # markdown-code 映射表
LANGUAGE_BY_EXTENSION       =   27   # markdown-code 映射表
SHIKI_LANGUAGE_BY_EXTENSION =   69   # markdown-code 映射表
COMMON_CODE_LANGUAGES       =   29   # 被当成真代码的语言
MEDIA_BY_EXT                =   18   # 扩展名 → 媒体类型
SOURCE_LABELS               =   23   # 会话来源标签
ALWAYS_EXCLUDED             =   34   # 文件树硬排除项
DESKTOP_HIDDEN_TOOLSETS     =    5   # 桌面隐藏的 toolset
BUILTIN_PERSONALITIES       =   14   # 内置人格名
REASONING_EFFORTS           =    7   # 思考强度档
PROJECT_IDEA_TEMPLATES      =   18   # 新建项目点子池
```

**斜杠命令表单独展开**(它是本片第二大的「表即行为」):

```verify
python3 /home/user/hermes-study/data/r10b/probes/probe_e_slash_table.py /home/user/hermes-agent
```

```text
  canonical specs      : 35
  aliases              : 15
  no-desktop-surface   : 41
  ALL_SPECS (canonical+nds) : 76
  resolvable names (ALL_SPECS + aliases) : 91
  surface kinds        : {'action': 14, 'exec': 15, 'picker': 2, 'rpc': 2, 'unavailable': 2}
```

35 条 canonical(surface 类型):
`/new` `/branch` `/yolo` `/wake` `/handoff` `/profile` `/skin` `/title` `/help` `/browser`
`/journey` `/compress` `/pet` `/hatch` = **action**(14);
`/model` `/resume` = **picker**(2);`/save` `/status` = **rpc**(2);
`/approvals` `/agents` `/background` `/debug` `/goal` `/personality` `/queue` `/retry`
`/rollback` `/steer` `/stop` `/tools` `/undo` `/usage` `/version` = **exec**(15);
`/reload-mcp` `/reload-skills` = **unavailable**(2)。

41 条「已知但桌面无界面」按理由分四桶:terminal 31、advanced 6、messaging 2、settings 2。

`apps/desktop/src/lib/desktop-slash-commands.ts:162 @ 863e313`

```ts
const DESKTOP_COMMAND_SPECS: readonly DesktopCommandSpec[] = [
  // Local client actions
  { name: '/new', description: 'Start a new desktop chat', aliases: ['/reset'], surface: action('new') },
```

**键位表单独展开**:71 条动作 = 44 条字面行 + 18 条 `profile.switch.N` + 9 条 `session.slot.N`。
字面行按分类:composer 3、profiles 5、session 9、navigation 9、view 18。

`apps/desktop/src/lib/keybinds/actions.ts:55 @ 863e313`

```ts
export const KEYBIND_ACTIONS: readonly KeybindActionMeta[] = [
  // ── Composer ─────────────────────────────────────────────────────────────
  // Soft `/` / Enter focus (gated); other printables type-to-focus unbound.
  { id: 'composer.focus', category: 'composer', defaults: ['/', 'enter'] },
```

### 2.4 `src/debug/` 的 `window.__*__` 接缝(4 个,逐个列全)

| 全局对象 | 声明处 | 方法面 | 装配处 |
|---|---|---|---|
| `window.__RENDER_COUNTS__` | `apps/desktop/src/debug/render-counter.ts:233` 的 `declare global {` | `counts` `commits()` `clear()` `start()` `stop()` `recording()` `report(limit?)` `get(name)` `explain(name?)` | 同文件 `:259` 起 |
| `window.__ATOM_CHURN__` | `apps/desktop/src/debug/atom-churn.ts:100` 的 `declare global {` | `churn` `clear()` `start()` `stop()` `recording()` `report(limit?)` `get(name)` `watched()` | 同文件 `:116` 起 |
| `window.__PERF_LIVE__` | `apps/desktop/src/debug/perf-live.ts:286` 的 `declare global {` | `on()` `off()` `last()` `watching()` | 同文件 `:297` 起 |
| `window.__RIGHT_PANE_PERF__` | `apps/desktop/src/debug/right-pane-events.ts:10` 的 `declare global {` | `clear()` `mark(event, detail?)` `snapshot()` `start()` `stop()` | `apps/desktop/src/debug/right-pane-probe.ts:14` 的 `if (typeof window !== 'undefined' && !window.__RIGHT_PANE_PERF__) {` |

注意第四个的**类型/打点** 与 **记录器实现** 被刻意拆成两个文件:
`right-pane-events.ts` 里的 `markRightPanePerf` 是「生产安全的调用点」
(`window.__RIGHT_PANE_PERF__?.mark(...)`,可选链,生产里全局不存在就是空调用),
因此产品代码可以直接 import 它而不把记录器拖进产物;记录器在 `right-pane-probe.ts`,
只被 `apps/desktop/src/debug/index.ts` 以副作用 import 拉进 dev 图。

---

## 3. 端到端链

### 3.1 链 A:一条带 markdown + 工具调用的助手消息,从网关事件到屏幕

**第 1 跳 —— 网关事件到 store。** `tool.start` / `tool.complete` 事件进 `use-message-stream`,
调用本片的 `upsertToolPart` 把工具 part 合进当前助手气泡的 parts 数组。

`apps/desktop/src/app/session/hooks/use-message-stream/index.ts:472 @ 863e313`

```ts
      mutateStream(
        sessionId,
        parts => dedupeGeneratedImageEchoesInParts(upsertToolPart(parts, payload, phase)),
        () => upsertToolPart([], payload, phase),
        { pending: m => phase !== 'complete' || (m.pending ?? false) }
      )
```

**第 2 跳 —— 文本 delta 的合并,顺带把 `MEDIA:` 标签变成 markdown 链接。**
`appendAssistantTextPart` 先把 delta 并进同段落的最后一个 text part,再看要不要跑
`renderMediaTags`。这里有一处很值得抄的细节:**它要处理「`MEDIA:` 这个词被 delta 边界切开」**,
所以判定条件是四个后缀的或。

`apps/desktop/src/lib/chat-messages.ts:446 @ 863e313`

```ts
export function appendAssistantTextPart(parts: ChatMessagePart[], delta: string): ChatMessagePart[] {
  const { index, parts: next } = appendStreamPart(parts, 'text', delta)
  const part = next[index]
```

`apps/desktop/src/lib/chat-messages.ts:454 @ 863e313`

```ts
  const mayContainMedia =
    delta.includes('MEDIA:') || delta.includes('DIA:') || delta.includes('EDIA:') || delta.includes('IA:')
```

**第 3 跳 —— 渲染入口把预处理、块切分、数学插件三样都换成本片的实现。**

`apps/desktop/src/components/assistant-ui/markdown-text.tsx:598 @ 863e313`

```tsx
  return (
    <StreamdownTextPrimitive
      components={components}
      containerClassName={cn(MARKDOWN_CONTAINER_CLASS_NAME, containerClassName)}
      containerProps={containerProps}
      defer={defer}
      lineNumbers={false}
      mode="streaming"
```

`apps/desktop/src/components/assistant-ui/markdown-text.tsx:611 @ 863e313`

```tsx
      parseIncompleteMarkdown={false}
      parseMarkdownIntoBlocksFn={parseMarkdownIntoBlocksCached}
      plugins={plugins}
      preprocess={preprocessWithTailRepair}
```

**第 4 跳 —— `preprocess` 里跑本片的 `preprocessMarkdown`。** 它是一条七段流水线。

`apps/desktop/src/lib/markdown-preprocess.ts:480 @ 863e313`

```ts
export function preprocessMarkdown(text: string): string {
  const cleaned = text.replace(REASONING_BLOCK_RE, '').replace(PREVIEW_MARKER_RE, '')
  const scrubbed = scrubBacktickNoise(cleaned)
  const normalizedFences = normalizeFenceBlocks(scrubbed)
  const strippedEmptyFences = stripEmptyFenceBlocks(normalizedFences)
```

七段依次是:①剥 `<think>`/`<thinking>`/… 与 `[Preview:…]` 标记;②`scrubBacktickNoise`
清掉不成对的反引号噪声(**但保护住成对围栏和「正在流式输出、还没收尾」的那个围栏**);
③`normalizeFenceBlocks` 把围栏的 info 串清成合法语言标签,并把 ` ```math ` 单独路由到数学渲染;
④删空围栏;⑤按围栏切段,**围栏内原样透传**;⑥对散文段跑数学归一 + 货币 `$` 转义 +
剥 preview 标记 + 裸 URL 自动链接 + `@session:` 链接化 + 引文角标 `[1]` 剥除;⑦行尾空白清理。

第⑥步里最能说明这一层「难在哪」的是货币与数学的消歧:

`apps/desktop/src/lib/markdown-preprocess.ts:232 @ 863e313`

```ts
/**
 * Escape price openers without corrupting balanced numeric inline math.
 *
 * The upstream helper deliberately treats every `$` followed by a digit as
 * currency. That turns `$4\in A$` into `\$4\in A$`; remark-math then pairs
 * the orphan closing dollar with a later formula and renders the intervening
 * prose as math. We retain the price behavior for `$5 and $10` and `$5-$10`,
 * but preserve balanced, same-line numeric math spans.
 */
```

**第 5 跳 —— 块切分,缓存两层。** 流式场景下每次 flush 都是一个新字符串,
stock 切分器要对全文重新 lex(实测 64–192KB 时 3.4–9.6ms/次,~30 次/秒)。

`apps/desktop/src/lib/markdown-blocks.ts:117 @ 863e313`

```ts
export function parseMarkdownIntoBlocksCached(markdown: string): string[] {
  const hit = exactCache.get(markdown)
```

增量路径的**正确性论证**是这一段最值得学的地方——「往后追加文本可以回头改变前面块的解析结果」,
所以它丢掉最后**两个**内容块而不是一个:

`apps/desktop/src/lib/markdown-blocks.ts:74 @ 863e313`

```ts
  // Settled boundary: drop the last TWO content blocks (skipping any
  // whitespace-only blocks around them). Dropping only the single last content
  // block is unsound: appended text can retroactively merge the previous
  // parse's last two blocks into one. The trigger is a trailing Setext
  // underline — `marked` only treats `-`/`=` as an underline for the paragraph
  // ABOVE it, so a settled `"#e\n5\n-"` lexes as ["#e\n", "5\n-"], but growing
  // the tail to `"#e\n5\n-p2=kj:c"` collapses both into one paragraph. The
  // block before the last is the deepest an append can reach (the underline
  // consumes exactly one preceding block), so re-lexing the last two is safe;
  // earlier blocks are fenced off by settled blank lines. join('') === text
  // still holds either way, so the reconstruction check below can't catch this.
```

**第 6 跳 —— 数学节点走记忆化 KaTeX。** 命中缓存时**返回克隆**而不是同一批节点,
因为下游 rehype 插件会就地改写树。

`apps/desktop/src/lib/katex-memo.ts:224 @ 863e313`

```ts
        // Splice CLONES of the cached children into the parent. Reusing
        // the same node instances across renders would let downstream
        // rehype plugins or toJsxRuntime mutate the cached subtree —
        // breaking the next cache hit. structuredClone is ~100µs per
        // equation, well below the ~5–20ms katex.renderToString cost
        // we're avoiding.
        const clonedChildren = cached.map(child => structuredClone(child))
```

**第 7 跳 —— 工具卡片走另一条路。** 工具 part 不进 markdown 管线,
由 `apps/desktop/src/components/assistant-ui/tool/fallback-model/index.ts:860` 调
`formatToolResultSummary` 把 JSON 结果压成人话摘要,`:667` 调 `extractToolErrorMessage`
决定卡片是不是画成失败态。**这里有一条只有踩过才写得出的规则**:

`apps/desktop/src/lib/tool-result-summary.ts:24 @ 863e313`

```ts
const ERROR_KEYS = ['error', 'errors', 'failure', 'exception'] as const
// 'stderr' deliberately excluded: many CLIs emit informational lines on
// stderr (npm progress, git's hint:, gcc's `In file included from`) that
// aren't errors. Treating those as error signal flipped tool cards into
// destructive styling for healthy commands.
```

**第 8 跳(安全边界)—— 摘要文本里的链接。** 工具卡片的摘要行是用
`LinkifiedText` 渲染的,这一跳把我们带到本片唯一一个 ■,见 §6.1。

### 3.2 链 B:按下一个键,到底发生了什么

**第 1 跳 —— 归一成 combo 串。** 全局 keydown → `comboFromEvent`。
它的设计取舍值得单列:字母和**未按 Shift 的**标点从 `event.key` 取(跟随用户布局),
数字和按了 Shift 的标点从 `event.code` 取(AZERTY 上数字排是 shift 位,
`event.key` 会给出 `&`,那样 `mod+1` 就按不出来了)。

`apps/desktop/src/lib/keybinds/combo.ts:103 @ 863e313`

```ts
export function comboFromEvent(event: KeyboardEvent): string | null {
  if (MODIFIER_CODES.has(event.code)) {
    return null
  }

  const base = baseKeyFromEventKey(event.key, event.shiftKey) ?? baseKeyFromCode(event.code)
```

`mod` 与 `ctrl` 是两个不同的令牌:macOS 上 `mod` = Cmd、`ctrl` = 物理 Control;
非 macOS 上 `canonicalizeCombo` 把 `ctrl` 折成 `mod`。这样 `ctrl+tab`(切标签)
在 macOS 上是真 ⌃Tab(⌘Tab 被系统占了),在别处自动变成 Ctrl+Tab。

**第 2 跳 —— 查找条优先。** 若 ⌘F 查找条开着,它先声明自己占用 `mod+g` / `mod+shift+g` / `escape`。

`apps/desktop/src/lib/find-in-page.ts:107 @ 863e313`

```ts
export function findBarClaimsCombo(combo: string): boolean {
  return combo === 'mod+g' || combo === 'mod+shift+g' || combo === 'escape'
}
```

**为什么必须由派发器主动让位而不能靠 `stopPropagation`**:两个监听器都挂在 `window` 的捕获阶段,
`stopPropagation` 不抑制同一 target 上的兄弟监听器。这条推理直接对上
`apps/desktop/AGENTS.md:166 @ 863e313` 的不变式:

```md
- Keyboard ownership follows focus. The focused surface wins its keys; one
  cancel gesture does exactly one thing.
```

**第 3 跳 —— 查绑定索引,或者落到「打字即聚焦」。**

`apps/desktop/src/app/hooks/use-keybinds.ts:343 @ 863e313`

```ts
      const actionId = $comboIndex.get().get(combo)

      // Unbound printable → type-to-focus. Bound chords (shift+n, …) win above.
      if (!actionId) {
        const typeChar = typeToFocusChar(event)

        if (typeChar && composerFocusKeysAllowed(event, 'type')) {
          event.preventDefault()
          requestComposerFocus('active', { typeChar })
        }

        return
      }

      if (isEditableTarget(event.target) && !comboAllowedInInput(combo)) {
        return
      }
```

**第 4 跳 —— 软键的表面门控。** `composer.focus` 默认绑 `/` 和 `enter`,
但这两个键在很多场合另有主人。`composerFocusKeysAllowed` 依次问:
输入框里?被 overlay 盖住?焦点在终端里?会话切换器开着?整页路由?
——以及一条最细的:**clarify 卡片只占用它真的渲染出来的那几个键**。

`apps/desktop/src/lib/keybinds/composer-focus-keys.ts:58 @ 863e313`

```ts
/**
 * True when a live clarify card binds THIS key, so type-to-focus must yield it.
 *
 * The card owns Enter plus the shortcuts it actually renders — `1..N+1` and
 * `A..` for its N choices and the trailing "Other" row. It does NOT own the
 * rest of the alphabet: typing a real message instead of picking an option is a
 * legitimate answer ("none of these"), and blanket-blocking every printable
 * left the user unable to start that message at all — the first letter vanished
 * and the composer never focused. Out-of-range keys fall through to the
 * composer, which skips the question on send.
 *
 * The choice count rides in the attribute's value, so this stays a DOM read
 * with no store coupling.
 */
```

**第 5 跳 —— 执行。** 内置动作的 handler 在 `use-keybinds.ts` 里(它们需要 React context),
插件贡献的动作自带 `run`:

`apps/desktop/src/app/hooks/use-keybinds.ts:374 @ 863e313`

```ts
      // Built-in handlers first (they carry React context); contributed
      // actions bring their own `run` through the registry.
      const handler = handlersRef.current[actionId] ?? contributedKeybindHandler(actionId)
```

**第 6 跳(以 Shift+X 为例)—— 落到主题。** `appearance.toggleMode` 的 handler 走
`useTheme().setMode`,`ThemeProvider` 的 effect 调 `applyTheme` 把 26 个色令牌
写成 `:root` 的 CSS 自定义属性,并把 `chromeBg` 写进两个 localStorage 裸键
供下次开窗的**内联前置绘制脚本**用。

`apps/desktop/src/themes/context.tsx:240 @ 863e313`

```tsx
  // Raw (non-JSON) keys read by the inline pre-paint script in index.html —
  // they let a brand-new window paint the themed background on its very first
  // frame, before this module has even loaded.
  try {
    window.localStorage.setItem('hermes-boot-background', chromeBg)
    window.localStorage.setItem('hermes-boot-color-scheme', rendered)
```

---

## 4. 逐机制 / 逐区域

### 4.1 `src/debug/` —— 为什么这套探针值得抄

**它回答的问题**:「刚才那次交互,**什么**重渲染了、**为什么**、以及**哪个 store** 推的?」

**(a) 为什么不用 React 自带的东西。** README 把三条路都堵死了,并且给了可复现的验证:

`apps/desktop/src/debug/README.md:46 @ 863e313`

```md
**React 19.2 removed `injectProfilingHooks` from react-dom.** Verified:
`grep -c injectProfilingHooks node_modules/react-dom/cjs/react-dom-client.development.js`
→ `0`. Only `onCommitFiberRoot` / `onPostCommitFiberRoot` remain. The entire
`mark*` profiling family (`component-render-start`, `state-update`,
`render-scheduled`) is dead on this stack — anything built on it is out.
```

`apps/desktop/src/debug/README.md:52 @ 863e313`

```md
**`<Profiler>` cannot answer "did the sidebar re-render?"** React invokes
`onRender` for *every* Profiler in a committed tree, including subtrees that
bailed out. Counting those callbacks "proves" a re-render that never happened.
`actualDuration` is not a discriminator either: a bailed-out subtree still
reports a small nonzero duration, so there's no safe threshold. `didFiberRender`
is the honest signal. (Note `app/chat/perf-probe.tsx` exports a `PerfProbe`
Profiler wrapper that is used nowhere — that's why.)
```

括号里那句自我披露可以直接验证,**成立**:全仓 `PerfProbe` 只有三处出现——定义处
`apps/desktop/src/app/chat/perf-probe.tsx:458`、README 自己、以及一份 markdown 笔记
`apps/desktop/scripts/profile-typing-lag.md:387`,**零个 JSX 使用点**。

```verify
cd /home/user/hermes-agent/apps/desktop && rg -n "PerfProbe" src/ e2e/ scripts/ electron/
# 3 hits: perf-probe.tsx:458 (定义) / debug/README.md:57 / scripts/profile-typing-lag.md:387
```

**(b) 归因逻辑本身。** 每个 commit 遍历真正渲染过的 composite fiber,对每个组件问三个问题:
有 prop 的引用变了吗(`Object.is` 逐键)、有 hook 的 `memoizedState` 变了吗
(覆盖 `useState`/`useSyncExternalStore`/`useMemo`/`useReducer`)、消费的 context 变了吗。
三个都没有 → 计入 `wasted`。

`apps/desktop/src/debug/render-counter.ts:132 @ 863e313`

```ts
/** Did any consumed context value change? A `memo()` cannot block a re-render
 *  caused by context, so distinguishing this from a parent-driven render is
 *  the difference between "add a memo" and "split the provider". */
```

`explain(name)` 更进一步:从一次 wasted 渲染**向上走到级联的顶端**,而不是停在第一个
prop 变了的祖先——因为父级重建 JSX 会让沿途每个节点都报「children 变了」,那是症状不是原因。

`apps/desktop/src/debug/render-counter.ts:181 @ 863e313`

```ts
    // explain() support: walk UP from a wasted render to the TOP of the
    // cascade — the highest ancestor that also rendered this commit. That
    // fiber is the origin; its own changed props/state is the reason.
    // Stopping at the first ancestor with changed props is wrong: JSX rebuilt
    // by a parent makes every intermediate node report "children changed",
    // which is the symptom cascading down, not the cause.
```

**(c) 状态侧的对照计数器。** `atom-churn.ts` 统计的核心指标是 `wasted`:
新值与旧值**深等**却仍然通知。`@nanostores/react` 的 `useStore` 只按引用相等 bail-out,
所以发一个内容相同的新数组 = 所有订阅者白渲染一遍。深比较**限深 3 层**,
超过就退回引用比较——注释明确说这会**低报**浪费而不是**虚构**浪费,
这是给测量工具选默认值时的正确方向。

`apps/desktop/src/debug/atom-churn.ts:38 @ 863e313`

```ts
/** Structural equality, depth-capped so a long transcript array doesn't make
 *  the instrumentation itself the bottleneck. Beyond the cap we compare by
 *  reference, which under-reports waste rather than inventing it. */
```

`listeners` 从 store 自己的 `lc` 字段读,而不是数通知次数——因为 `onNotify`
在零订阅者时也会触发,只数通知会高报扇出。

**(d) 观测对象是**精选**的,不是全量。** 32 个 store 分三组:HOT(每个 token 都写)、
DERIVED(应该保持安静,一有动静就是候选 bug)、SIDEBAR(回合期间应该完全冷)。
理由写在文件头:「一个报 200 行的 churn 计数器和没有一样没用。」

**(e) import 顺序是承重的,而且用构建期别名而不是 tree-shaking 来保证不进产物。**

`apps/desktop/src/main.tsx:8 @ 863e313`

```tsx
// Dev-only render/state churn counters. MUST precede the `react-dom` import
// below: react-dom captures the devtools hook at module init, so bippy has to
// install during THIS import's evaluation or every commit goes unseen
// (verified — a late install reports renderers=0, commits=0). `vite.config.ts`
// aliases this specifier to a no-op module for non-dev builds, so neither the
// counters nor bippy reach a shipped renderer.
import '@/debug/dev-only'
```

`apps/desktop/vite.config.ts:34 @ 863e313`

```ts
const debugEntry = (command: string, env: Record<string, string>) =>
  command === 'serve' || env.VITE_PERF_PROBE === '1'
    ? path.resolve(__dirname, './src/debug/dev-only.ts')
    : path.resolve(__dirname, './src/debug/dev-only.noop.ts')
```

**这个组合是这套设计里最聪明的一步**:静态副作用 import 无法被 tree-shake,
所以「dev 要它、生产不要它」这件事必须在**模块解析层**解决,而不是在打包优化层。
`dev-only.noop.ts` 因此有一条硬规矩——「保持本文件无 import」。

**(f) `perf-live.ts` 补的是渲染计数器看不见的另一半。** 它挂 LoAF
(Long Animation Frame,浏览器给出的「这一帧超长了,里面跑了哪些脚本、
样式布局花了多久」的 PerformanceObserver 条目)。文件头把动机说得很直白:
合成场景(短散文、无工具调用、无代码块)能报 57fps,而真实会话在同一手势上明显卡顿。

`apps/desktop/src/debug/perf-live.ts:33 @ 863e313`

```ts
/** One Long Animation Frame, attributed. `styleMs` is the engine's style+layout
 *  time inside the frame; `scripts` names who ran JS and for how long. This is
 *  the half the render counter cannot see — a frame can cost 900ms with almost
 *  no React in it, and only LoAF says whether that was layout, a ResizeObserver
 *  callback loop, or some timer. */
```

### 4.2 主题:一份调色板喂三个界面

**四个来源汇成一个 `DesktopTheme`**:

| 来源 | 转换器 | 关键取舍 |
|---|---|---|
| 6 个内置主题 | `apps/desktop/src/themes/presets.ts` 直接写死 | 只有 `nous` 之类手工调了 `darkColors`;没有 `darkColors` 的主题,亮色版由 `synthLightColors` 合成 |
| CLI/TUI 的 skin(YAML) | `apps/desktop/src/themes/skin.ts:46` 的 `export function skinToDesktopTheme(skin: HermesSkin): DesktopTheme \| null {` | skin 是**单模式**的,所以 `colors` 和 `darkColors` 都填同一份 |
| VS Code 主题 JSON | `apps/desktop/src/themes/vscode.ts:205` 的 `export function convertVscodeColorTheme(raw: VscodeColorTheme, opts: ConvertOptions = {}): ConvertResult {` | 只读 ~6 个 workbench 键做种子,其余靠向前景/背景混色推导 |
| 插件贡献 | `apps/desktop/src/themes/user-themes.ts:155` 的 `export function contributedThemes(): DesktopTheme[] {` | 一个数据贡献**就是**一个 `DesktopTheme`,同样的合法性门槛 |

**「朴素令牌转换器」是明说的策略**,不是偷懒:

`apps/desktop/src/themes/vscode.ts:1 @ 863e313`

```ts
/**
 * VS Code color-theme → DesktopTheme converter.
 *
 * VS Code themes carry ~hundreds of `workbench.colorCustomization` keys, but the
 * desktop theme model only needs a `DesktopThemeColors` struct — `applyTheme`
 * derives every glass/shadcn token from a small seed chain via `color-mix()`.
 * In practice ~6 workbench keys carry the whole look (background, foreground,
 * accent, elevated surface, sidebar, error); everything else we derive by mixing
 * those toward the background/foreground. That's the "naive token converter".
```

两个转换器**共用同一条对比度保险**:强调色要在侧栏表面上跑小号大写标签,
所以必须过 WCAG AA(4.5:1),否则就往白/黑方向分五档混色直到过关。
两个文件各自定义了同名常量 `ACCENT_MIN_CONTRAST = 4.5` 并在注释里互相点名。

`apps/desktop/src/themes/color.ts:67 @ 863e313`

```ts
/**
 * Guarantee `color` reads against `bg`: if it's below `min` contrast, mix it
 * toward white (on a dark bg) or black (on a light bg) in steps until it clears,
 * keeping the hue as much as possible. Used so imported accents never collapse
 * into a near-background sidebar (the "invisible label" case).
 */
```

**合并顺序**是这一簇的对外接缝,列全如下(内置 → 贡献 → 后端 skin → 用户安装,后者可遮蔽前者,
但**内置名永远不可被遮蔽**):

`apps/desktop/src/themes/user-themes.ts:171 @ 863e313`

```ts
/** Resolve a theme by name across the merged set (built-in + user + backend + contributed). */
export function resolveTheme(name: string): DesktopTheme | undefined {
  return (
    BUILTIN_THEMES[name] ??
    $userThemes.get()[name] ??
    $backendThemes.get()[name] ??
    contributedThemes().find(theme => theme.name === name)
  )
}
```

**「painted mode」与「picked mode」是两个概念**,这是本簇最容易被抄漏的设计。
用户选的是 light/dark/system(`resolvedMode`),但某些主题在 "dark" 下仍是亮背景,
于是 `.dark` 类是否加,按**实际背景亮度**判断(`renderedModeFor`),
终端调色板之类跟表面走的 UI 要读 `renderedMode` 而不是 `resolvedMode`。

`apps/desktop/src/themes/context.tsx:140 @ 863e313`

```tsx
/**
 * Some palettes intentionally keep a bright background even when
 * `mode === 'dark'`, so we shouldn't apply the `.dark` class. Decide from
 * the actual background luminance.
 */
```

**开机前置绘制**:模块加载时就画一次(在 `ThemeProvider` 挂载之前),
用的是**上次活跃 profile** 的皮肤与模式,避免闪白。

`apps/desktop/src/themes/context.tsx:271 @ 863e313`

```tsx
if (typeof window !== 'undefined') {
  const profile = readBootProfileKey()
  const pref = modePref.resolve(profile)
  const resolved = resolveMode(pref)
  const theme = deriveTheme(skinPref.resolve(profile), resolved)
  applyTheme(theme, resolved)
  syncNativeTheme(pref, renderedModeFor(theme.colors, resolved))
}
```

**后端推来的 skin 什么时候上色**:`gateway.ready` 只 seed 不上色(否则每次重连都会
盖掉用户手动选的桌面主题),只有真正的名字变化才上色。这个「seed vs apply」的状态机
只用一个模块级变量 `lastSynced: { applied, name }` 表达。

`apps/desktop/src/themes/backend-sync.ts:32 @ 863e313`

```ts
// Last skin name synced from the backend + whether it was ever APPLIED (vs
// merely seeded at connect). Once applied, only a name change applies again —
// no re-apply on repeat events, no snap-back after a manual desktop switch.
// A `skin.changed` matching a seed-only baseline still applies: the seed
// records without painting, so if the activation event was missed (backend
// restart / disconnected), an explicit re-affirm must repaint, not no-op.
```

### 4.3 语音:打断为什么是这一簇里最难的一块

`voice-barge-in.ts` 解决的是一个**物理问题**:扬声器在响,麦克风要判断「用户在说话」。
它的四条规则各自对应一次失败:

1. **噪声底只在安静期标定,播放期冻结。** 在扬声器有声时标定 = 把回声烘进底噪,
   触发阈值就永远够不到(注释点名:Windows 上 `echoCancellation` 挡不住同应用播放)。
2. **播放期把阈值**夹到一个下限(回声本身不足以触发)**并封一个上限**(大声播放时人声仍够得到)。
3. **播放刚起的一小段宽限期**吃掉启动瞬态,而且宽限只在「离上次播放有真空档」时才给,
   免得句间的 playing 抖动把宽限窗口串起来。
4. **触发判定是滑窗多数**(最近 300ms 里 ≥80% 超阈),不是连续超阈,
   这样词内的能量凹陷不会把进度清零。

`apps/desktop/src/lib/voice-barge-in.ts:250 @ 863e313`

```ts
          // Phase-aware trigger: quiet baseline x multiplier; playback clamps
          // it up (bleed alone can't trip) but a ceiling keeps speech
          // reachable even over loud playback.
          let trigger = Math.max(MIN_TRIGGER_LEVEL, quietFloor * FLOOR_MULTIPLIER)

          if (playing) {
            trigger = Math.min(Math.max(trigger, PLAYBACK_MIN_TRIGGER_LEVEL), TRIGGER_CEILING_LEVEL)
          }
```

**还有一条产品级洞察**:光检测到打断是不够的,**打断的那句话的开头会丢**。
所以监视器全程跑一个 `MediaRecorder`(前摇),触发后继续录到用户安静为止,
交付完整的一句;安静期每 5 秒 rotate 一次 recorder,免得前摇 blob 累积整个回合。

`apps/desktop/src/lib/voice-barge-in.ts:1 @ 863e313`

```ts
// Full-duplex VAD monitor: watch the mic across the agent turn — while the
// model is generating (no audio yet) AND while TTS plays — fire the moment the
// user talks over either phase, and CAPTURE what they say. Detection alone
// loses the first words — by the time sustained speech trips the trigger and a
// fresh recorder spins up, "stop, actually—" has become "actually—". So a
// MediaRecorder runs on the monitor's stream the whole time (pre-roll), and
// once tripped it keeps rolling until the user goes quiet, delivering the
// complete utterance.
```

播放侧(`voice-playback.ts`)有两条路:优先开一个 WebSocket 到
`/api/audio/speak-stream` 走 int16 PCM 帧,用 Web Audio 排程——这样第一句话在
provider 吐出第一块音频时就开始出声,而不是等整段合成 + base64 传完。
拿不到 WS 就回退到整段 data URL 的 `HTMLAudioElement`。
还有一个 15 秒的停滞看门狗,因为「免费 Edge TTS 偶尔给一段既不 `playing`
也不 `ended` 也不 `error` 的音频,让语音模式永远卡在 speaking」。

三个提示音(`wake-sound` / `completion-sound` / `thinking-sound`)全部是
**WebAudio 振荡器合成,不带资源文件**,并且刻意做成可区分的形状:
唤醒音上行(开始/就绪),完成音下行(结束)。`completion-sound.ts` 里 14 个预设
共用一条 `voices → master → lowpass → (dry + reverb send) → out` 的信号链。

多窗去重走一个跨窗「认领」原语:

`apps/desktop/src/lib/completion-sound.ts:456 @ 863e313`

```ts
// Plays the selected completion cue on any `message.complete`. Pass a dedupeKey
// (the session id) so only one window beeps when several are open — the mute
// check runs first, so a muted window never claims the cue out from under an
// audible peer.
```

触感侧则是一个**全局限流器**——上游风暴(鉴权过期的 toast 连发、重连抖动)会把触控板
震成蜂鸣:

`apps/desktop/src/lib/haptics.ts:118 @ 863e313`

```ts
  recentFires = recentFires.filter(t => now - t < RATE_WINDOW)

  if (recentFires.length >= RATE_LIMIT) {
    return
  }
```

### 4.4 性能原语:这一层为什么到处是「保引用」

流式回合里 `$sessionStates` 每个 delta 都重新发布(每秒几十次),
而派生出来的「哪些会话在忙」这类集合只在状态**边沿**变。nanostores 的
`computed` 按 `!==` 通知,所以派生集合每次都会发一个内容相同的新数组,
整个侧栏跟着每 token 重渲一次。`stableArray` 就是那把锁:

`apps/desktop/src/lib/stable-array.ts:1 @ 863e313`

```ts
/** Keep `prev`'s reference when it's element-equal to `next`, so a nanostores
 *  `computed` (notifies on `!==`) skips the emit when its projected list didn't
 *  actually change — e.g. status-id sets recomputed on every stream delta.
 *  `next` is frozen: the ref is shared across ticks, so an in-place mutation
 *  would corrupt the cache — fail loud instead. */
export const stableArray = <T>(prev: readonly T[], next: T[]): readonly T[] =>
  prev.length === next.length && prev.every((v, i) => v === next[i]) ? prev : Object.freeze(next)
```

同一思路在本片出现了至少六次,值得单独成表——**「保引用」是这一层的统一手法**:

| 位置 | 保的是什么 | 不保会怎样 |
|---|---|---|
| `apps/desktop/src/lib/stable-array.ts:6` 的 `export const stableArray = <T>(prev: readonly T[], next: T[]): readonly T[] =>` | 派生 id 集合的数组引用 | 侧栏每 token 全量重渲 |
| `apps/desktop/src/lib/markdown-blocks.ts:38` 的 `const EXACT_CACHE_MAX = 256` | 同一段文本永远返回**同一个数组** | Streamdown 把块列表镜像进 `useState`,新引用 = 自身重渲 + 所有 Block 重渲 |
| `apps/desktop/src/lib/use-session-slice.ts:10` 的 `const EMPTY: readonly never[] = []` | 缺席 key 的空数组 | 每次 store 写入都产生新空数组,`useSyncExternalStore` 的快照 bail-out 失效 |
| `apps/desktop/src/lib/incremental-external-store-runtime.ts:38` 的 `Write only the items whose (message, parentId) pair actually moved.` | 只写身份变了的那条 | 流式时 N-1 次写入是纯开销,且随会话长度增长 |
| `apps/desktop/src/lib/katex-memo.ts:105` 的 `const cache = new LruCache<string, CachedRender>()` | 公式渲染结果 | 每个 token 把整篇所有公式重跑一遍 KaTeX |
| `apps/desktop/src/lib/raf-coalesce.ts:6` 的 `export function rafCoalesce<T>(apply: (value: T) => void): { finish: () => void; push: (value: T) => void } {` | 每帧只 apply 一次 | 一次拖拽驱动多次布局 |

`render-weight.ts` 则是另一个方向的教训——**不能用条数计价**:

`apps/desktop/src/lib/render-weight.ts:1 @ 863e313`

```ts
/**
 * Render cost of one message's content parts, in budget units.
 *
 * Two layers bound long transcripts and both spend the same currency: the
 * store window (how many messages reach assistant-ui at all) and the DOM page
 * budget (how many of those actually render). Neither can be a message COUNT —
 * counting only parts underpriced a 51KB tool result as "1", so a handful of
 * huge results let a 600KB transcript through the old 300-part cap and drove
 * Chromium's renderer into a GC crash. Characters approximate markdown
 * parsing, text-node allocation, and tool-result formatting; parts approximate
 * component/node count.
```

### 4.5 本地/远程双通道门面

`desktop-fs.ts`、`desktop-git.ts`、`media.ts` 是同一个模式的三次实现:
**同一组函数,本地走 Electron IPC,连远程网关时走后端 REST**,调用方不分叉。

`apps/desktop/src/lib/desktop-git.ts:12 @ 863e313`

```ts
// Remote-aware git facade. Locally the desktop runs git through Electron
// (window.hermesDesktop.git); on a remote gateway that's the wrong filesystem,
// so we mirror the same surface over the dashboard REST API (/api/git/*) — the
// coding rail, worktree lanes, review pane, and branch ops then act on the
// BACKEND repo where sessions actually run. Mirrors desktop-fs.ts.
```

这条设计的代价也在本片里可见:`desktop-fs.ts` 需要一个可注入的
`DesktopFsRemotePicker`(远程模式下「选文件」得由别的组件提供),
因为远程时没有本地文件对话框可用。

### 4.6 崩溃可存活的回合日记

`inflight-turn-journal.ts` 的定位很清楚:后端自己的 `inflight` 快照覆盖
「后端还活着的重连」,这份日记覆盖「后端也死了」,并且**更富**——
后端快照只带文本,日记保留完整的 part 结构(工具调用也在内)。

`apps/desktop/src/lib/inflight-turn-journal.ts:3 @ 863e313`

```ts
/**
 * Crash-survivable in-flight turn journal.
 *
 * While a session is busy, the visible tail of the running turn (user prompt +
 * streamed assistant rows, tool calls included) is persisted to localStorage.
 * If the renderer or the whole app dies mid-turn, session resume folds the
 * journaled tail back onto the restored transcript, so streamed progress is
 * not silently lost. The backend's own `inflight` snapshot (merged by
 * `appendLiveSessionProjection`) covers reconnects while the backend is alive;
 * this journal covers the cases where the backend died too — and it is richer,
 * because the backend snapshot carries text only while the journal keeps the
 * full part structure.
 *
 * Best-effort by design: storage failures must never break chat streaming.
 */
```

关键工程细节:localStorage 是**同步**写,而流式重绘约每 33ms 一次,
所以用 400ms 尾沿节流——「崩溃最多损失这么多最新尾巴」被明确当成可接受代价。

### 4.7 `chat-messages.ts` 的两块硬骨头

**(a) 无稳定 id 的工具事件配对。** 有些流会先发无 id 的 `tool.start`,
再发带 id 的 `tool.complete`;并行工具调用又会有多个同名待完成行。
`findToolPartIndex` 因此做了一个五级回退:稳定 id → 参数内容重叠
(`search_term`/`query`/`question`/`command`/`code`/`path` 里第一个非空串,
外加 `context`/`preview`)→ 唯一待完成行 → 完成事件取**最老**的 → 运行中事件取**最新**的。

`apps/desktop/src/lib/chat-messages.ts:592 @ 863e313`

```ts
  // Completion events without stable IDs frequently arrive after multiple
  // same-name starts (parallel tool calls). Resolve them oldest-first so we
  // don't collapse an entire burst into a single row.
```

**(b) 流式 part 的分段合并。** delta 合进「当前段」里最后一个同类型 part;
段的边界是任何非流式 part(工具调用、图片)。**相反通道(text ↔ reasoning)是透明的**,
所以两段正文中间插一段推理不会把一句话切成 text / Thinking / text 三块。

`apps/desktop/src/lib/chat-messages.ts:405 @ 863e313`

```ts
// Coalesce a streaming delta into the most recent same-type part within the
// current segment, where a segment is bounded by any non-streaming part (a
// tool call, image, …). The opposite streaming channel (text <-> reasoning) is
// transparent, so a reasoning burst between two content deltas can't shred one
// sentence into text / Thinking / text — the fragmentation models that
// interleave reasoning_content + content otherwise produce. Tool calls still
// open a fresh part, preserving narration order across steps.
```

**(c) 最终文本合并时的一条非对称规则。** 最终答复会替换所有流式 text part,
并在「推理内容被最终文本完全包含」时丢掉推理;**反向不成立**——
一句短的 "Done." 不能吞掉一段以它开头的长推理(issue #61447)。

### 4.8 外链:桌面端唯一「把内容交给外部程序」的地方

信任边界在 **IPC**,不在渲染进程。渲染侧只是转发:

`apps/desktop/src/lib/external-link.tsx:198 @ 863e313`

```tsx
export function openExternalLink(href: string): void {
  if (href) {
    void window.hermesDesktop?.openExternal?.(href)
  }
}
```

主进程才做 scheme 白名单(`file:` 单独走 `resolveRequestedPathForIpc` + `shell.openPath`):

`apps/desktop/electron/main.ts:1344 @ 863e313`

```js
  if (!['http:', 'https:', 'mailto:'].includes(parsed.protocol)) {
    return false
  }
```

**这是正确的分工**:渲染进程里任何 URL 校验都可能被绕过(比如中键点击走的是
`setWindowOpenHandler` 而不是 React 的 `onClick`),而那两条路
(`apps/desktop/electron/main.ts:8712` 的 `win.webContents.setWindowOpenHandler(details => {` 与
`:8717` 的 `win.webContents.on('will-navigate', (event, url) => {`)也都汇到同一个
`openExternalUrl`。渲染侧的 `SKIP_PROTO_RE` 只管**要不要去抓标题**,不管能不能打开:

`apps/desktop/src/lib/external-link.tsx:115 @ 863e313`

```tsx
export function isTitleFetchable(value: string): boolean {
  if (!value || SKIP_PROTO_RE.test(value)) {
    return false
  }

  const url = parseUrl(value)

  return Boolean(url && /^https?:$/.test(url.protocol) && !LOCAL_HOST_RE.test(url.host))
}
```

标题抓取这条路本身则有问题,见 §6.1。

同一簇里另一个安全面是 `local-preview.ts`:远程 HTML 预览先做 base64 往返校验
(`btoa(atob(x)) === x`)、再过 DOMPurify、再**注入一条 `default-src 'none'` 的 CSP meta**
并逐元素抹掉 `href`/`ping`:

`apps/desktop/src/lib/local-preview.ts:112 @ 863e313`

```ts
  const csp = `default-src 'none'; base-uri 'none'; form-action 'none'; img-src data:; media-src data:; font-src data:; style-src 'unsafe-inline'`
```

### 4.9 一条被 lint 规则钉住的库函数

`apps/desktop/src/lib/mutable-ref.ts` 全文 6 行,只做 `ref.current = value`。
它存在的理由是「让 react-compiler 不去标记 hook 参数里的 ref 写入」。
但它同时被 eslint 显式列为**禁止出现在 `useEffect` 里**的三种形状之一:

`apps/desktop/eslint.config.mjs:71 @ 863e313`

```mjs
        {
          // useEffect(() => { setMutableRef(ref, value) }, [value])
          selector:
            'CallExpression[callee.name="useEffect"] > ArrowFunctionExpression[body.type="BlockStatement"]:has(CallExpression[callee.name="setMutableRef"])',
```

◇ **这是一个值得记的模式**:一个为绕开编译器警告而存在的 helper,
必须同时被 lint 规则围起来,否则它就成了绕开那条真正规则(「不要把响应式值镜像进 ref」)的后门。
规则注释里列出了四个曾经被这个反模式咬到的实例(`cancelRun` 把 `session.interrupt`
发到了错误的会话,以及 `steerPrompt` / `restoreToMessage` / `editMessage` 的闭包陈旧读)。

---

## 5. 文档与代码的出入

### ▲ E-1 `src/debug/README.md` 里指向 `stableArray` 守卫的行号锚点已漂

`apps/desktop/src/debug/README.md:103 @ 863e313`

```md
The sidebar hypothesis is **refuted**: 6 renders across the whole run, all
attributable to hook state on genuine busy/needsInput edges, none wasted. The
`stableArray` guards on `$workingSessionIds` / `$attentionSessionIds`
(`store/session-states.ts:236-259`) are doing their job.
```

**整句判定**:这句话讲了三件事——(i) 侧栏假设被证伪、6 次渲染 0 浪费;
(ii) 原因是 `$workingSessionIds` / `$attentionSessionIds` 上的 `stableArray` 守卫;
(iii) 那些守卫在 `store/session-states.ts:236-259`。
(i) 是一次测量记录,无法在静态代码里证伪,不判;(ii) **成立**;
**只有 (iii) 不成立**,所以 ▲ 只落在那个锚点上,不覆盖整句。

`apps/desktop/src/store/session-states.ts:257 @ 863e313`

```ts
let workingIds: readonly string[] = []
export const $workingSessionIds = computed(
  $sessionStates,
  states =>
    (workingIds = stableArray(
```

`apps/desktop/src/store/session-states.ts:268 @ 863e313`

```ts
export const $attentionSessionIds = computed(
```

`stableArray` 在该文件的全部出现位置是 `:31`(import)、`:249`(注释)、`:261`、`:271`。
被引的 `236-259` 区间里**一次 `stableArray` 调用都没有**——`:233-242` 是
`clearAllSessionStates()`,`:244-255` 是注释与 `storedIds` 辅助函数。
`$attentionSessionIds` 的守卫在 `:271`,整整落在区间之外。

```verify
cd /home/user/hermes-agent/apps/desktop && rg -n "stableArray" src/store/session-states.ts
# 31 / 249 / 261 / 271  —— 与 README 所述的 236-259 区间不相交(仅 249 是注释提及)
```

*口径说明:`src/debug/README.md` 不在派工书 §4 列出的六个「作者自绘地图」文档来源里。
但它是本片的**片内文件**,且这条锚点正是下一个读它的人会直接跳过去的东西,
所以按同一标准记 ▲,并在此声明它不计入跨轮「地图腐烂度」的 ▲ 计数。*

### ▲ E-2 `DESIGN.md` 的「不要在功能代码里直接 import 图标包」在 simple-icons 上不成立

`apps/desktop/DESIGN.md:224 @ 863e313`

```md
- **Tabler** is the default component/chrome set. Import its curated aliases and
  `iconSize` scale from `src/lib/icons.ts`; do not import icon packages directly
  in feature code.
```

**整段判定 + 归属确认**:这条 bullet 在 `## Iconography & brand` 标题下,
同一节下面还有 `**BrandMark**` 的 bullet,所以这一节明确覆盖品牌图标而不只是 Tabler。
bullet 里三件事:(i) Tabler 是默认集合 —— 成立;
(ii) 从 `src/lib/icons.ts` 取别名与 `iconSize` —— 成立(全仓只有 1 处直接 import
`@tabler/icons-react`,且只 import 了一个**类型**);
(iii) **不要在功能代码里直接 import 图标包** —— **不成立**。

```verify
cd /home/user/hermes-agent/apps/desktop
rg -n "from '@tabler/icons-react'" src/ --glob '!src/lib/icons.ts'
#   src/components/ui/codicon.tsx:1:import type { Icon } from '@tabler/icons-react'   ← 仅类型
rg -ln "@icons-pack/react-simple-icons" src/
#   src/lib/brand-icon.ts            ← 这是「curated」那一侧,合规
#   src/app/messaging/platform-icon.tsx   ← 功能代码,直接 import
#   src/app/skills/mcp-tab.tsx            ← 功能代码,直接 import
```

`apps/desktop/src/app/messaging/platform-icon.tsx:14 @ 863e313`

```tsx
} from '@icons-pack/react-simple-icons'
```

补充事实:**这条规则没有任何 lint 强制**。`apps/desktop/eslint.config.mjs` 里
`no-restricted-imports` 只配了一条,且只作用于 `src/plugins/**`(插件围栏);
`no-restricted-syntax` 三条全是 ref-mirroring 相关。搜索面:
在 `apps/desktop/eslint.config.mjs` 全文 grep `tabler`、`icons-pack`、
`no-restricted-imports`,只命中插件围栏那一条。

### ◎ E-3 `src/debug/README.md` 标题说「两个计数器」,实际有四个 `window.__*__`

`apps/desktop/src/debug/README.md:1 @ 863e313`

```md
# Dev-only state diagnostics

Two counters that answer, for any interaction: **what re-rendered, why, and
which store pushed it?**
```

**字面为真**——它说的那两个(`__RENDER_COUNTS__` / `__ATOM_CHURN__`)确实回答那两个问题,
它没有说「只有两个」。但 `apps/desktop/src/debug/index.ts` 同时拉进了
`./perf-live` 与 `./right-pane-probe`,目录实际暴露 **4 个** `window.__*__` 全局
(§2.4 列全)。按记号约定「字面为真就不是 ▲」,记 **◎**:README 描述保守,
读它的人会以为 `debug/` 只有两件东西。

`apps/desktop/src/debug/index.ts:27 @ 863e313`

```ts
import './render-counter'
// Live interaction profiler — arms on real resize/typing so we can measure the
// app under REAL sessions instead of a synthetic scenario's toy transcripts.
// window.__PERF_LIVE__.on() in the console, then just use the app.
import './perf-live'
import './right-pane-probe'
```

### ◇ E-4 preload 桥的 94 个成员与 `global.d.ts` 严格一致,但无任何机制保证

见 §2.2.1。文档(`apps/desktop/AGENTS.md` / `DESIGN.md` / `README.md`)对此**只字未提**;
搜索面:在这三个文件里 grep `global.d.ts`、`preload`、`contextBridge`、`hermesDesktop`,
`AGENTS.md` 零命中,`DESIGN.md` 零命中,`README.md` 零命中。

### ◇ E-5 `src/lib/` 里有 6 个文件明说自己是某个 Python 文件的镜像

这是一条文档没画出来的**跨语言一致性约束**,逐条列全(这就是搜索面:
在 `apps/desktop/src/lib/` 与 `src/themes/` 下 grep `\.py\b` 与 `hermes_cli/` 与 `tools/`):

| 桌面文件 | 声明镜像的后端文件 | 锚点 |
|---|---|---|
| `apps/desktop/src/lib/composer-input-sanitize.ts` | `hermes_cli/input_sanitize.py` | `apps/desktop/src/lib/composer-input-sanitize.ts:5` 的 `Mirrors hermes_cli/input_sanitize.py (CLI/TUI gateway defensive path).` |
| `apps/desktop/src/lib/mcp-tool-filter.ts` | `tools/mcp_tool.py` 的 `_register_server_tools` | `apps/desktop/src/lib/mcp-tool-filter.ts:3` 的 `// — `include` wins, no filter means all. Mirrors `_register_server_tools` in` |
| `apps/desktop/src/lib/reasoning-effort.ts` | `hermes_constants.py` 的 `VALID_REASONING_EFFORTS` | `apps/desktop/src/lib/reasoning-effort.ts:3` 的 `/** Hermes' reasoning levels, in ascending order — mirrors the backend's` |
| `apps/desktop/src/lib/voice-barge-in.ts` | `tools/voice_mode.full_duplex_listen` | `apps/desktop/src/lib/voice-barge-in.ts:10` 的 `// Phase-aware trigger (mirrors tools/voice_mode.full_duplex_listen on the` |
| `apps/desktop/src/lib/thinking-sound.ts` | `tools/voice_mode.py` 的 numpy 合成 | `apps/desktop/src/lib/thinking-sound.ts:6` 的 `// backend's numpy-synthesized blips in tools/voice_mode.py so CLI and desktop` |
| `apps/desktop/src/lib/model-search-text.ts` | `hermes_cli/model_search.py` + 另两个前端 | `apps/desktop/src/lib/model-search-text.ts:8` 的 `* Keep in sync with ui-tui/src/lib/model-search-text.ts,` |
| `apps/desktop/src/lib/remote-url.ts` | `electron/connection-config.ts` 的 `normalizeRemoteBaseUrl()` | `apps/desktop/src/lib/remote-url.ts:4` 的 `* Renderer-side twin of the scheme coercion in` |
| `apps/desktop/src/lib/wake-client-capture.ts` | `tools/wake_word.py` 的帧长 | `apps/desktop/src/lib/wake-client-capture.ts:11` 的 `const DEFAULT_FRAME = 1280 // 80 ms @ 16 kHz — matches tools/wake_word.py` |
| `apps/desktop/src/lib/local-preview.ts` | 后端 filesystem 端点的 `_FS_DATA_URL_MAX_BYTES` | `apps/desktop/src/lib/local-preview.ts:9` 的 `// Mirrors `_FS_DATA_URL_MAX_BYTES` in the backend filesystem endpoint.` |

(表头说 6 个,实际数出来是 9 条——以表为准,上面那句「6 个」按表更正为 **9 条**。)

**这 9 条都是靠注释维持的**,没有任何测试或脚本比对两侧。对「独立实现同级 harness」
这个目标来说,这是一条重要的负债形态:跨语言双实现 + 纯注释约束。

---

## 6. 缺陷

### ■ E-1 工具结果里的「文件名形状」词元会被链接化,并触发主进程发起对外 HTTP 请求

**现象链**(每一跳都能单独复核):

1. 工具卡片摘要用 `LinkifiedText` 渲染,**且用的是 `pretty` 默认档、没有传 `explicitOnly`**:

`apps/desktop/src/components/assistant-ui/tool/fallback.tsx:281 @ 863e313`

```tsx
function LinkifiedText({ className, text }: { className?: string; text: string }) {
  return <SharedLinkifiedText className={className} pretty text={cleanVisibleText(text)} />
}
```

2. `explicitOnly` 为 false 时用的是带**裸域名分支**的 `URL_RE`,它会把 `agent.log`
   这类文件名当成域名:

`apps/desktop/src/lib/external-link.tsx:13 @ 863e313`

```tsx
const URL_RE =
  /(?:https?:\/\/|www\.)[^\s<>"'`]+[^\s<>"'`.,;:!?)]|[a-z0-9](?:[a-z0-9-]*\.)+[a-z]{2,}(?:\/[^\s<>"'`.,;:!?)]*)?/gi
```

3. `normalizeExternalUrl` 给它补上 `https://`,于是 `agent.log` → `https://agent.log`。
   **这一行为有测试钉着**,是承诺行为而不是意外:

`apps/desktop/src/lib/external-link.test.tsx:243 @ 863e313`

```tsx
  it('without explicitOnly, bare filename tokens are still linkified (default behavior)', () => {
    installDesktopBridge()

    render(<LinkifiedText pretty={false} text="open agent.log please" />)

    const link = screen.getByRole('link', { name: 'agent.log' })
    expect(link.getAttribute('href')).toBe('https://agent.log')
  })
```

4. `pretty` 档渲染的是 `PrettyLink`,而 `LinkifiedText` **不给它 `label` / `fallbackLabel`**
   (§4.8 引的 `LinkifiedText` 只传 `href` 和 `key`),所以 `authoredLabel` 为空,
   标题抓取被触发:

`apps/desktop/src/lib/external-link.tsx:271 @ 863e313`

```tsx
// Title resolution is a fallback, not an override. Both props carry authored
// text — chat markdown passes `fallbackLabel` — so either one skips the fetch.
export function PrettyLink({ className, fallbackLabel, href, label, ...rest }: PrettyLinkProps) {
  const target = useMemo(() => normalizeExternalUrl(href), [href])
  const authoredLabel = label?.trim() || fallbackLabel?.trim()
  const fetched = useLinkTitle(authoredLabel ? null : target)
```

5. `isTitleFetchable` 只挡非 http scheme 与四个字面 localhost 形式(见 §4.8 引文),
   `agent.log` 全部通过,于是走到主进程 `fetchLinkTitle`——**它没有任何主机白名单、
   没有私网/链路本地地址过滤**,先 curl、失败再开一个隐藏 BrowserWindow 真加载该 URL:

`apps/desktop/electron/main.ts:4749 @ 863e313`

```js
  const pending = fetchHtmlTitleWithCurl(url)
    .catch(() => '')
    .then(value => usableTitle((value || '').slice(0, 240)))
    .then(
      async value => value || usableTitle(((await fetchHtmlTitleWithRenderer(url).catch(() => '')) || '').slice(0, 240))
    )
```

**为什么算缺陷而不是设计**:同一个文件里已经为**同一个问题**造了缓解手段,
并且注释点名了同一个场景(`/debug` 报告里的 `agent.log` / `errors.log`):

`apps/desktop/src/lib/external-link.tsx:16 @ 863e313`

```tsx
// Explicit-scheme / www. URLs only — no bare-domain matching. Used where the
// surrounding text is full of filename-shaped tokens (e.g. `agent.log`,
// `errors.log` in a /debug report) that the bare-domain branch of URL_RE would
// otherwise mistake for domains and linkify.
```

但**只有系统消息面用了它**。搜索面:在 `apps/desktop/src/` 下 grep `explicitOnly`,
与 `LinkifiedText` 相关的命中共 4 处,全部在
`apps/desktop/src/components/assistant-ui/thread/system-message.tsx`(`:56` `:60` `:78`)
加上定义处 `apps/desktop/src/lib/external-link.tsx:294`;
工具卡片那条路(`fallback.tsx:282`)没有传。

**影响面**:模型/工具输出是**不可信输入**。一段工具结果只要包含
`something.co`、`x.io`、`report.zip` 这类词元,桌面主进程就会对该主机发起
DNS + HTTP 请求(并且第二次尝试会用一个真 BrowserWindow 加载它),
把「用户此刻在看某条工具结果」这件事泄漏给一个由模型输出决定的第三方主机。
`isTitleFetchable` 挡住的只有 `localhost` / `127.0.0.1` / `0.0.0.0` / `[::1]` 四个字面量,
显式写出的 `http://169.254.169.254/…`(云元数据端点)或 `http://10.0.0.5:8080/…`
既能通过裸域名之外的**显式 scheme 分支**,也能通过 `isTitleFetchable`。

**最小修法**(不改架构):把 `fallback.tsx:282` 那处也传 `explicitOnly`,
并在 `isTitleFetchable` 里加私网/链路本地网段过滤。前者一行,后者是主进程侧的事。

### ■ E-2 `atom-churn.ts` 的 `unsubscribes` 是只写不读的死数组

`apps/desktop/src/debug/atom-churn.ts:32 @ 863e313`

```ts
const churn = new Map<string, AtomChurn>()
const unsubscribes: Array<() => void> = []
let recording = false
```

`watchAtom` 每注册一个 store 就往里 push 一个 `off`,但**全文件没有第二处引用**,
`window.__ATOM_CHURN__` 的方法面(§2.4)里也没有任何取消订阅的入口。
搜索面:在 `apps/desktop/src/debug/atom-churn.ts` 全文 grep `unsubscribes`,
命中 2 处(`:33` 声明、`:87` push);在 `apps/desktop/src/` 下 grep `unsubscribes`
只此一个文件。

严重性:**低**。dev-only 图,32 个 store 各一个闭包,永远不释放但也永远不增长。
记在这里是因为它是一个「本来打算做、后来没做」的残留——写 harness 时值得注意的形态:
一个注册器攒了 disposer 却没有 dispose 入口,读代码的人会以为「有清理路径」。

### ■ E-3(观察,非 bug)`render-counter.explain()` 会顺手打开录制但不会关掉

`apps/desktop/src/debug/render-counter.ts:282 @ 863e313`

```ts
    explain: name => {
      if (name !== undefined) {
        explainTarget = name
        explainCauses.clear()

        if (name && !recording) {
          recording = true
        }
```

`explain('Block')` 会把 `recording` 置真,`explain(null)` 只清 `explainTarget`,
不还原 `recording`。控制台工具,`stop()` 就在旁边,影响可忽略;
列在这里只是为了让「这一片的缺陷面已经看过」这句话是有内容的。

---

## 7. 测试(行为规格)

**运行环境**(用例数是环境的函数,必须一并记):

```text
基线副本 : /home/user/r10b-ts/hermes-agent(git archive 导出,不污染基线)
node     : v22.22.2
vitest   : 4.1.10   (project=ui, jsdom)
node_modules 顶层条目数 : 736
容器      : 无 IPv6、以 root 运行(本片用例不涉及这两项)
```

**命令与结果**:

```verify
cd /home/user/r10b-ts/hermes-agent/apps/desktop && npx vitest run --project ui src/lib src/themes src/debug
```

```text
 Test Files  1 failed | 75 passed (76)
      Tests  1 failed | 689 passed (690)
   Duration  128.07s
```

- **passed 689 / failed 1 / skipped 0。**
- **零执行 / 整文件跳过:0 个。** 搜索面:在 `apps/desktop/src/lib`、`src/themes`、
  `src/debug`、`src/types` 下 grep `\b(describe|it|test)\.(skip|todo|only)\b`,**零命中**。
  76 个测试文件全部有用例执行(76 个文件 690 个用例,无收集错误)。
- **`src/debug/` 下 0 个测试文件。** 这是刻意的:README 自己解释了为什么在 `ui` project
  里测不了——`setupFiles` 会在任何测试体之前引入 `@testing-library/react`(从而引入 react-dom),
  bippy 的 hook 就再也装不上了。

`apps/desktop/src/debug/README.md:87 @ 863e313`

```md
If you add a test that imports these counters, note the `ui` vitest project's
`setupFiles` pulls in `@testing-library/react` (and thus react-dom) before any
test body runs, so the hook can never install there. Use a config without
`setupFiles`.
```

**那 1 个失败是环境性的,不是代码缺陷**,已单独复现确认:

```text
FAIL src/lib/markdown-blocks.test.ts
  > parseMarkdownIntoBlocksCached
  > matches a full lex at every char-level streaming cut over noisy markdown (property fuzz)
  Error: Test timed out in 30000ms.   (实测耗时 35398ms)
```

用例自己声明了 30 秒预算(`apps/desktop/src/lib/markdown-blocks.test.ts:163` 的 `}, 30_000)`),
它在 76 个文件并行跑时被 worker 争用拖过了线。单独跑同一个文件时**测试体只花 9.86 秒**:

```verify
cd /home/user/r10b-ts/hermes-agent/apps/desktop && npx vitest run --project ui --testTimeout=180000 src/lib/markdown-blocks.test.ts
# Test Files 1 passed (1) / Tests 6 passed (6) / Duration 12.16s (tests 9.86s)
```

**归类**:容器算力/并行度导致的用例脆性(用例把绝对墙钟时间钉进了断言预算),
与 CLAUDE.md 已记录的 6 条「环境必然失败」同类,建议加入该表(见移交项 H-R10B-E-5)。

**几个把设计钉死的测试**(行为规格价值最高的):

| 测试 | 它钉住的行为 |
|---|---|
| `apps/desktop/src/lib/markdown-blocks.test.ts:137` 的 `it('matches a full lex at every char-level streaming cut over noisy markdown (property fuzz)', () => {` | 增量 lex 在**每一个字符级流式切点**上都必须与全量 lex 逐字节相同;12 seed × 500 步 |
| `apps/desktop/src/lib/markdown-blocks.test.ts:123` 的 `const prev = `${settled}#e\n5\n-`` | Setext 下划线导致「追加文本回头合并前两个块」的那个具体反例 |
| `apps/desktop/src/lib/external-link.test.tsx:243` 的 `it('without explicitOnly, bare filename tokens are still linkified (default behavior)', () => {` | §6.1 那条行为是**承诺的默认值**,不是意外 |
| `apps/desktop/src/components/assistant-ui/markdown-text.test.ts:232` 的 `expect(preprocessMarkdown('Probability is $2/3$ and fee is $7.')).toBe('Probability is $2/3$ and fee is \\$7.')` | 同一行里数学 `$` 与货币 `$` 的消歧结果 |

---

## 8. 判据自查

| # | 判据 | 自评 | 依据 |
|---|---|---|---|
| **1 点名到位** | 126/126 文件全路径 + 一句话角色 | **达标** | §0.1–§0.4 四张分组表,组内逐个列全路径;下面给了自检命令 |
| **2 接缝穷举** | 三个面全列,给了机械枚举命令与条数 | **达标(口径已声明)** | §2.0 声明口径替换;§2.1 导出面 123 文件 / 809 符号全列;§2.2 类型面 94 + 64 + 130 全列;§2.3 30 张常量表条数;§2.4 4 个 `window.__*__` 全列。**唯一自认的缺口**:`n_importers` 是 grep 量级而非精确调用图,已在 §2.1 声明 |
| **3 端到端链** | 两条链,逐跳带锚点 | **达标** | §3.1 消息 → markdown → 渲染(8 跳);§3.2 按键 → 键位表 → 主题(6 跳) |
| **4 逐字取证** | 远超 2 个 | **达标** | 全文 45 个 ```` ```ts/tsx/js/mjs/md ```` 逐字源码块 |
| **5 记号** | 2 ▲ / 2 ◇ / 1 ◎ / 3 ■ | **达标** | §5、§6 |

判据 1 的自检命令(主线复核可直接用):

```verify
cd /home/user/hermes-study && miss=0; while read -r f; do \
    grep -qF "$f" notes/r10b-raw-lib-themes.md || { echo "MISSING: $f"; miss=1; }; \
  done < data/r10b/slices/E.txt; echo "missing=$miss"
```

**未达标 / 打折扣的地方,如实列出**:

1. **`n_importers` 不是调用图。** 它按模块说明符 grep 并按文件去重,对桶文件(`debug/index.ts`)
   和同名 basename 会偏高。要精确需要解析 import 语句并解析路径别名,本片没做。
2. **`src/lib/` 里有约 30 个文件我只读了文件头 + 导出面,没有读完实现体。**
   按 L2「读接口面而不读实现体」这是允许的,但要说清楚具体是哪些:
   §0.4 分组 (l)(m)(n)(o)(p) 里除 `loadout.ts`、`storage.ts`、`time.ts`、`external-link.tsx`
   之外的文件,我读的是头部文档注释 + 导出列表 + 关键常量表,没有逐行读实现。
   这些文件的**接口面**在 §2.1 是完整的。
3. **`src/types/hermes.ts` 的 130 个类型我只列了名字,没有逐个展开字段。**
   展开会是几千行,超出底稿的边际价值;我展开了其中与本片链条直接相关的
   `SessionMessage` / `TimelineDisplayMetadata`。
4. **`presets.ts` 的 6 个主题我只核了名字与结构,没有逐个核 26 个色令牌的取值。**

---

## 9. 移交项

| 编号 | 锚点 + 摘录 | 一句话现象 | 建议 |
|---|---|---|---|
| **H-R10B-E-1** | `apps/desktop/src/components/assistant-ui/tool/fallback.tsx:282`:`return <SharedLinkifiedText className={className} pretty text={cleanVisibleText(text)} />` | 工具结果摘要走的是 `pretty` + 无 `explicitOnly` 的链接化,`agent.log` 这类词元会变成 `https://agent.log` 并触发主进程标题抓取 | 与电子端片(`electron/main.ts:4733` 的 `fetchLinkTitle`)合并成一条完整的「不可信文本 → 外发请求」定案,不要两片各写一半 |
| **H-R10B-E-2** | `apps/desktop/src/lib/external-link.tsx:24`:`const LOCAL_HOST_RE = /^(?:localhost\|127\.0\.0\.1\|0\.0\.0\.0\|\[::1\])(?::\d+)?$/i` | 标题抓取的主机拦截只有四个字面 localhost 形式,没有私网 / 链路本地 / 云元数据网段 | 归入 H-R10B-E-1 的同一条定案 |
| **H-R10B-E-3** | `apps/desktop/src/debug/README.md:103`:`The sidebar hypothesis is **refuted**: 6 renders across the whole run, all` | 这段结尾的 `store/session-states.ts:236-259` 锚点已漂,真实位置是 `:261` 与 `:271` | 成品章引用这段测量结论时,改引真实行号;▲ 计数按 §5 声明不计入跨轮 |
| **H-R10B-E-4** | `apps/desktop/src/app/messaging/platform-icon.tsx:14`:`} from '@icons-pack/react-simple-icons'` | `DESIGN.md:224-226` 的「功能代码不直接 import 图标包」在 simple-icons 上有两处反例,且无 lint 强制 | 与 UI 组件片(`src/components/`)核对是否还有更多反例后再定 ▲ 的范围 |
| **H-R10B-E-5** | `apps/desktop/src/lib/markdown-blocks.test.ts:163`:`}, 30_000)` | 该 fuzz 用例在 76 文件并行下实测 35.4s、超它自己声明的 30s 预算;单跑只要 9.86s | 建议加入 CLAUDE.md「容器环境必然失败」表作第 7 条,注明**只在全目录并行时**失败 |
| **H-R10B-E-6** | `apps/desktop/src/types/hermes.ts:519`:`export type TimelineDisplayMetadata =` | 该类型声明了三种形状,但唯一的读取点 `chat-messages.ts:348` 把 `display_metadata` 当 `unknown` 重新收窄,类型没被用作保证 | 写「类型契约 vs 运行时校验」那一章时,这是本仓最干净的一个例子 |
| **H-R10B-E-7** | `apps/desktop/src/debug/atom-churn.ts:33`:`const unsubscribes: Array<() => void> = []` | 只写不读的 disposer 数组,`window.__ATOM_CHURN__` 没有取消订阅入口 | 低优先级;若某轮统一清点「攒了 disposer 却没有 dispose 入口」的形态,这是一例 |
| **H-R10B-E-8** | `apps/desktop/src/lib/composer-input-sanitize.ts:5`:`Mirrors hermes_cli/input_sanitize.py (CLI/TUI gateway defensive path).` | 本片查到 9 处「桌面 TS 实现声明自己镜像某个 Python 文件」,全部只靠注释约束,无测试/脚本比对 | 值得单独做一次跨语言双实现清点(不限于本片),它是 harness 设计里一类系统性负债 |

---

## 10. 本片成本自报

```text
片号            : E
层              : L2
文件数 / 行数   : 126 / 20,540
实际打开的文件数: 121   (126 减去 5 个只看了路径与行数的:
                        vite-env.d.ts 1 行、以及 4 个纯内容表
                        project-idea-templates.ts / excluded-paths.ts 尾部 /
                        presets.ts 的 5 个非 nous 主题字面量 / icons.ts 的别名清单
                        —— 这几个我只读了头部与结构,没通读字面量)
实际读过的行数  : 约 11,500
                  (估法:完整读完的文件按全行数计——debug/ 全部 1,085 行、
                   themes/ 全部 1,905 行、chat-messages.ts 1,174、
                   markdown-preprocess/blocks/code/katex-memo 1,246、
                   external-link.tsx 331、tool-result-summary 469、
                   keybinds/ 656、voice-barge-in 326、voice-playback 前 200、
                   desktop-slash-commands 前 430、inflight-turn-journal 前 70、
                   chat-runtime 前 70、types/hermes.ts 约 200 行抽读、
                   global.d.ts 约 130 行 + 探针输出;其余约 60 个文件按
                   「头部注释 + 导出列表」各计 20 行)
底稿字节数      : (主线自测)
主观耗费        : 中。瓶颈不在单文件长度,也不在概念密度,在**文件多且彼此无关**——
                  20,540 行分散在 126 个文件里,平均 163 行/文件,
                  没有一条主线可以顺着读下去,必须先用探针把导出面机械拉平,
                  再按主题重新聚类才有结构可讲。真正吃时间的是**判据 2 的口径转换**
                  (把「接缝穷举」翻译成「导出面 + 类型契约面 + 常量表」并逐一枚举)
                  和**确认 ■ E-1 的完整链路**(要跨到 electron/ 与 components/ 才闭环)。
                  测试跑了两次(全目录 128s + 单文件复现 12s)。
```
