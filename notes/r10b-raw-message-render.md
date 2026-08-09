# r10b 片 F · 消息渲染 —— assistant-ui、聊天组件与右侧栏 —— 底稿

> 证据层。求全求证,不追求好读。凡对 hermes-agent 行为的断言,锚点
> `路径:行号 @ 863e313` 单独成行、置于代码块之前;围栏块是逐字源码摘录,
> ```text / ```verify / ```console 是作者声明的非源码块。
>
> 本片层级 **L2**(读接口面,不读实现体)。范围:`data/r10b/slices/F.txt`,
> **124 文件 / 21,029 行**,全部在 `apps/desktop/src/` 下。

---

## 0. 本片范围与逐文件点名

### 0.0 范围核对(机械)

```verify
# 片内文件数(在 hermes-study 仓库根执行)
wc -l < data/r10b/slices/F.txt
# → 124

# 片内每个文件的行数与总行数
cd /home/user/hermes-agent && while read -r f; do wc -l < "$f"; done \
    < /home/user/hermes-study/data/r10b/slices/F.txt | paste -sd+ | bc
# → 21029
```

四个目录,四种角色:

| 目录 | 文件数 | 它是什么 |
|---|---|---|
| `apps/desktop/src/components/assistant-ui/` | 65 | 消息与工具调用的渲染层(thread 19 / tool 10 / embeds 28 / 根 8) |
| `apps/desktop/src/components/chat/` | 30 | 渲染层复用的通用零件(代码卡、diff、骨架屏、计时器、图片) |
| `apps/desktop/src/app/right-sidebar/` | 29 | 右侧三块面板:文件树 / git review / 内嵌终端 |
| 合计 | **124** | |

### 0.1 `components/assistant-ui/`(根 8 个)

- `apps/desktop/src/components/assistant-ui/ansi-text.tsx` —— 把带 ANSI SGR 转义的文本渲染成着色 span;无转义时退回纯字符串节点,省掉解析成本。
- `apps/desktop/src/components/assistant-ui/artifact-card.tsx` —— 被"提升为 artifact"的围栏块在正文里的占位卡片(图标/标题/种类/版本徽章),点击打开右栏。
- `apps/desktop/src/components/assistant-ui/clarify-tool.tsx` —— `clarify` 工具的三态渲染:待答(可交互选项+文本框)、已答(Q&A 定格)、被打断(退回通用行)。
- `apps/desktop/src/components/assistant-ui/directive-text.tsx` —— `@kind:value` 指令文本解析成内联 chip;同时是 assistant-ui 的 directive formatter 实现(serialize/parse)。
- `apps/desktop/src/components/assistant-ui/markdown-text.tsx` —— assistant 正文的 markdown 管线(Streamdown + KaTeX + 懒加载 shiki + 18 个标签覆写)。
- `apps/desktop/src/components/assistant-ui/message-render-boundary.tsx` —— 只吞 assistant-ui store 的瞬时 `useClientLookup out of bounds` 竞态,别的错误重新抛给根边界。
- `apps/desktop/src/components/assistant-ui/reference-kinds.ts` —— 引用词汇表:16 种 kind 的图标/标签,以及在消息文本里认出引用的那一个正则。
- `apps/desktop/src/components/assistant-ui/tooltip-icon-button.tsx` —— 带 tooltip 的图标按钮(消息动作条通用件)。

### 0.2 `components/assistant-ui/thread/`(19 个)

- `apps/desktop/src/components/assistant-ui/thread/index.tsx` —— Thread 外壳:装配四个 message 组件类型、还原确认对话框、时间线。
- `apps/desktop/src/components/assistant-ui/thread/list.tsx` —— 消息列表:turn 分组、渲染预算(DOM 上限)、粘底滚动、`content-visibility` 虚拟化。
- `apps/desktop/src/components/assistant-ui/thread/message-parts.tsx` —— **本片最核心的分派表**:part 类型 → 组件、工具名 → 组件。
- `apps/desktop/src/components/assistant-ui/thread/assistant-message.tsx` —— assistant 气泡:正文、错误行、预览附件、动作条(复制/朗读/重跑/分支/表情)、改动文件卡。
- `apps/desktop/src/components/assistant-ui/thread/user-message.tsx` —— user 气泡(粘顶)、后台进程通知的系统样式改写、Stop/还原按钮、tapback。
- `apps/desktop/src/components/assistant-ui/thread/user-message-text.tsx` —— user 文本的极简 markdown(仅围栏与行内 code),指令 chip 仍解析。
- `apps/desktop/src/components/assistant-ui/thread/user-edit-composer.tsx` —— 点气泡进入的行内编辑器(完整补全触发器 / 拖放 / 撤销)。
- `apps/desktop/src/components/assistant-ui/thread/system-message.tsx` —— system 行三种形态:`steer:` 提示、`slash:` 命令回显、纯文本。
- `apps/desktop/src/components/assistant-ui/thread/status.tsx` —— 四个状态指示器:会话 spinner、首 token 前的 loading、后台恢复提示、流停滞提示。
- `apps/desktop/src/components/assistant-ui/thread/content.ts` —— 纯函数:从 message.content 抽文本 / 判有无可见文本 / 取附件引用 / 选主预览目标。
- `apps/desktop/src/components/assistant-ui/thread/changed-files.ts` —— 纯函数:把一轮的文件编辑 part 折成"每文件一行 +N/−M"。
- `apps/desktop/src/components/assistant-ui/thread/changed-files-card.tsx` —— 上面那份数据的卡片渲染(点行打开该文件 diff)。
- `apps/desktop/src/components/assistant-ui/thread/message-reactions.tsx` —— 表情选择器(六个快捷 + frimousse 全量)与已落表情徽章。
- `apps/desktop/src/components/assistant-ui/thread/use-message-reactions.ts` —— 表情读写 hook:本地先画、后台持久化;双击 tapback 手势判定。
- `apps/desktop/src/components/assistant-ui/thread/timeline.tsx` —— 右缘的 prompt 导览轨(四道可见性闸门)。
- `apps/desktop/src/components/assistant-ui/thread/timeline-data.ts` —— 时间线的纯数据推导(条目、预览、活动项索引)。
- `apps/desktop/src/components/assistant-ui/thread/timestamp.ts` —— 消息时间戳格式化(今天/昨天/更早)。
- `apps/desktop/src/components/assistant-ui/thread/transcript-window.tsx` —— "显示更早"的两级来源(先花 DOM 预算,再向 store 要更多)。
- `apps/desktop/src/components/assistant-ui/thread/types.ts` —— 只有一个 `RestoreMessageTarget` 接口。

### 0.3 `components/assistant-ui/tool/`(10 个)

- `apps/desktop/src/components/assistant-ui/tool/fallback.tsx` —— 通用工具行 `ToolEntry` + 运行折叠 `ToolRun` + 分组切分 `ToolGroupSlot`。
- `apps/desktop/src/components/assistant-ui/tool/fallback-model/index.ts` —— 通用工具行的**纯数据模型**:`TOOL_META` 表 + `buildToolView()`(把 args/result 折成标题/副标题/详情/计数/状态)。
- `apps/desktop/src/components/assistant-ui/tool/fallback-model/format.ts` —— 格式化原语(JSON 宽松解析、预览截断、时长、渲染字符上限)。
- `apps/desktop/src/components/assistant-ui/tool/fallback-model/targets.ts` —— URL/路径识别、可预览目标判定、disclosure id 生成。
- `apps/desktop/src/components/assistant-ui/tool/fallback-model/types.ts` —— `ToolPart` / `ToolView` / `ToolStatus` 等契约类型。
- `apps/desktop/src/components/assistant-ui/tool/approval.tsx` —— 危险命令审批条(行内 + 浮动兜底),`approval.respond` 的发起点。
- `apps/desktop/src/components/assistant-ui/tool/run-summary.ts` —— 把一串工具调用折成一行灰字("Explored 3 files, ran 5 commands")。
- `apps/desktop/src/components/assistant-ui/tool/run-ticker.tsx` —— 单行滚动窗(工具运行 / 子代理活动共用)。
- `apps/desktop/src/components/assistant-ui/tool/delegate.tsx` —— `delegate_task` 的扇出卡片(每个子代理一行 + 活动 ticker)。
- `apps/desktop/src/components/assistant-ui/tool/delegate-model.ts` —— 子代理行的三源合并(调用参数 / 结果 / 实时 subagent store)。

### 0.4 `components/assistant-ui/embeds/`(28 个)

嵌入子系统分三层:**检测(providers)→ 同意闸门(url-embed + embed-consent)→ 渲染器(4 个懒加载)**。

- `apps/desktop/src/components/assistant-ui/embeds/index.ts` —— 对外桶文件(5 行,只导出 6 个符号)。
- `apps/desktop/src/components/assistant-ui/embeds/registry.tsx` —— **围栏语言 → 懒渲染器**表(mermaid / svg)。
- `apps/desktop/src/components/assistant-ui/embeds/types.ts` —— 围栏渲染器的 props 契约 `RichFenceProps`。
- `apps/desktop/src/components/assistant-ui/embeds/url-embed.tsx` —— **URL 嵌入的总入口**:隐私闸门 + descriptor → 4 个渲染器的分派。
- `apps/desktop/src/components/assistant-ui/embeds/embed-consent.tsx` —— 未同意时的占位卡("Load X" / "Always allow X")。
- `apps/desktop/src/components/assistant-ui/embeds/embed-size.ts` —— 嵌入高度上限常量 `EMBED_MAX_H = '33dvh'`(4 行)。
- `apps/desktop/src/components/assistant-ui/embeds/fail.tsx` —— 嵌入失败的红字占位(7 行)。
- `apps/desktop/src/components/assistant-ui/embeds/rich-boundary.tsx` —— 富渲染器的局部错误边界(吞掉**全部**渲染错误,爆炸半径=一个块)。
- `apps/desktop/src/components/assistant-ui/embeds/scroll-gate.tsx` —— 地图嵌入的滚轮闸(按住 ⌘ 才交给 iframe)。
- `apps/desktop/src/components/assistant-ui/embeds/use-is-dark.ts` —— 读 `<html>` 的 `dark` class,给会自绘主题的嵌入用(18 行)。
- `apps/desktop/src/components/assistant-ui/embeds/escape-html.ts` —— 3 行的 HTML 转义(`& < > "`),`social-embed` 拼 blockquote 用。
- `apps/desktop/src/components/assistant-ui/embeds/frame-embed.tsx` —— 通用 iframe 渲染器(地图额外套 ScrollGate)。
- `apps/desktop/src/components/assistant-ui/embeds/youtube-embed.tsx` —— YouTube 专用 iframe(补 `origin` 参数)。
- `apps/desktop/src/components/assistant-ui/embeds/spotify-embed.tsx` —— Spotify 专用 iframe(补 `theme=0` / 强制 `color-scheme: light`)。
- `apps/desktop/src/components/assistant-ui/embeds/social-embed.tsx` —— X / Instagram:在本文档里插官方 blockquote + 注入官方脚本。
- `apps/desktop/src/components/assistant-ui/embeds/mermaid-embed.tsx` —— ```mermaid 围栏 → SVG 图(`securityLevel: 'strict'`)。
- `apps/desktop/src/components/assistant-ui/embeds/svg-embed.tsx` —— ```svg 围栏 → DOMPurify 净化后注入。
- `apps/desktop/src/components/assistant-ui/embeds/alert.tsx` —— GitHub 风格 `> [!NOTE]` 引用块 → 五种告示卡。
- `apps/desktop/src/components/assistant-ui/embeds/providers/index.ts` —— 8 个 matcher 的顺序表 + `detectEmbed()`。
- `apps/desktop/src/components/assistant-ui/embeds/providers/types.ts` —— provider/renderer 联合类型 + `bareHost()`。
- `apps/desktop/src/components/assistant-ui/embeds/providers/youtube.ts` —— youtu.be / youtube.com / youtube-nocookie.com,11 位 id,支持 `t`/`start`。
- `apps/desktop/src/components/assistant-ui/embeds/providers/vimeo.ts` —— vimeo.com / player.vimeo.com,取最后一段纯数字。
- `apps/desktop/src/components/assistant-ui/embeds/providers/instagram.ts` —— `/p|reel|tv/<code>`,固定高 450。
- `apps/desktop/src/components/assistant-ui/embeds/providers/pinterest.ts` —— `/pin/<digits>`,固定高 380。
- `apps/desktop/src/components/assistant-ui/embeds/providers/tiktok.ts` —— `/…/video/<digits>`,9:16 官方 player。
- `apps/desktop/src/components/assistant-ui/embeds/providers/twitter.ts` —— twitter.com / x.com 的 `/status/<digits>`,唯一 `renderer: 'tweet'`。
- `apps/desktop/src/components/assistant-ui/embeds/providers/spotify.ts` —— open.spotify.com 的 6 种类型,统一压到 152px 紧凑播放器。
- `apps/desktop/src/components/assistant-ui/embeds/providers/maps.ts` —— 两个 provider 合一:Google Maps(`@lat,lng` / `q=` / `/place/`)与 OpenStreetMap(`#map=z/lat/lng` → bbox)。

### 0.5 `components/chat/`(30 个)

- `apps/desktop/src/components/chat/widget-shell.ts` —— 12 行,一个常量 `WIDGET_SHELL_CLASS`(内联小部件的统一外壳)。
- `apps/desktop/src/components/chat/scaffold-row.tsx` —— transcript "脚手架行"的统一灰度与行式(thinking / 工具摘要共用)。
- `apps/desktop/src/components/chat/disclosure-row.tsx` —— 可折叠块的表头行(标题右侧 hover 出 caret;`trailing` 覆盖、`action` 在流内)。
- `apps/desktop/src/components/chat/status-row.tsx` —— composer 状态栈的行外壳(leading 图标 / 内容 / hover 出的 trailing)。
- `apps/desktop/src/components/chat/status-section.tsx` —— 状态栈里的一个可折叠分组。
- `apps/desktop/src/components/chat/code-card.tsx` —— 围栏代码的圆角底板(`CodeCard` / `CodeCardBody` / `CodeCardIcon`)。
- `apps/desktop/src/components/chat/shiki-highlighter.tsx` —— 高亮入口:预算判定、分块、懒加载 shiki、复制按钮。
- `apps/desktop/src/components/chat/shiki-block.tsx` —— 15 行,**全仓唯一静态 import `react-shiki` 的模块**(隔离多 MB chunk)。
- `apps/desktop/src/components/chat/expandable-block.tsx` —— 超高内容的折叠 + 底部渐隐 + 右下角展开按钮。
- `apps/desktop/src/components/chat/compact-markdown.tsx` —— 工具详情体的紧凑 markdown(Streamdown,static 模式,17 个标签覆写)。
- `apps/desktop/src/components/chat/diff-lines.tsx` —— 统一 diff 的解析与渲染(`DiffBody` 纯色 / `FileDiffPanel` 面板 / shiki transformer)。
- `apps/desktop/src/components/chat/syntax-diff.tsx` —— diff 的 shiki 高亮版(拆出来只为让 `react-shiki` 懒加载)。
- `apps/desktop/src/components/chat/fixed-row-window.ts` —— 定高行的窗口化(diff/日志的伪虚拟滚动)。
- `apps/desktop/src/components/chat/skeletons.tsx` —— 文件树与 diff 的加载骨架。
- `apps/desktop/src/components/chat/stable-text.tsx` —— 把每个字符放进 1ch 宽格子,防跳数(计时器用)。
- `apps/desktop/src/components/chat/activity-timer.ts` —— 模块级计时注册表(跨卸载存活)+ `formatElapsed` + 两个 hook。
- `apps/desktop/src/components/chat/activity-timer-text.tsx` —— 上面那个秒数的呈现件。
- `apps/desktop/src/components/chat/terminal-output.tsx` —— 只读小终端视图(挂载即到底,之后近底才跟随)。
- `apps/desktop/src/components/chat/log-tail.tsx` —— 共享日志尾随面板(复制按钮 + 跟底)。
- `apps/desktop/src/components/chat/zoomable-image.tsx` —— 可点开灯箱的图片 + 下载动作按钮。
- `apps/desktop/src/components/chat/preview-attachment.tsx` —— "打开预览"附件条(按本会话 cwd 解析目标,带请求令牌防竞态)。
- `apps/desktop/src/components/chat/generated-image-result.tsx` —— `image_generate` 结果卡(比例提示先占位、远程网关走 data URL)。
- `apps/desktop/src/components/chat/image-generation-placeholder.tsx` —— 生成中的 ASCII "扩散"动画画布 `DiffusionCanvas`。
- `apps/desktop/src/components/chat/vibe-hearts.tsx` —— `reaction` 事件触发的飘心粒子(composer 位 / 宠物位)。
- `apps/desktop/src/components/chat/intro.tsx` —— 空会话的开场白(按人格挑文案)。
- `apps/desktop/src/components/chat/intro-copy.jsonl` —— 75 行 JSONL 文案库,`?raw` 导入;每行 `{personality, headline, body}`。**本片唯一非 TS 文件**。
- `apps/desktop/src/components/chat/code-editor.tsx` —— CodeMirror 6 编辑器封装 + 命令式 `CodeEditorApi`。
- `apps/desktop/src/components/chat/code-editor-theme.ts` —— CodeMirror 的 GitHub 明/暗调色板(对齐读视图的 shiki 主题)。
- `apps/desktop/src/components/chat/json-document-editor.tsx` —— 内存态 JSON 编辑器(格式化/保存动作条),非磁盘预览。
- `apps/desktop/src/components/chat/composer-dock.ts` —— composer 及其贴附面板的共享皮肤字符串(6 个导出)。

### 0.6 `app/right-sidebar/`(29 个)

**文件树簇(7)**

- `apps/desktop/src/app/right-sidebar/index.tsx` —— 文件面板外壳:cwd 判定、刷新/全折叠、四种空态。
- `apps/desktop/src/app/right-sidebar/files/use-project-tree.ts` —— 树状态 hook(懒加载子节点、占位节点、workspace 变更重载)。
- `apps/desktop/src/app/right-sidebar/files/ipc.ts` —— `readDir` 桥 + `.gitignore` 过滤 + git root/ignore 双缓存。
- `apps/desktop/src/app/right-sidebar/files/tree.tsx` —— react-arborist 行渲染(仓库改动着色、内联重命名、揭示请求)。
- `apps/desktop/src/app/right-sidebar/files/dnd-manager.ts` —— 全应用一个 react-dnd manager(绕开 HTML5Backend 双重注册崩溃)。
- `apps/desktop/src/app/right-sidebar/files/remote-picker.tsx` —— 远程网关模式的文件夹选择对话框。
- `apps/desktop/src/app/right-sidebar/file-actions.tsx` —— 右键菜单 + 删除/重命名对话框 + 内联重命名输入框。

**git review 簇(5)**

- `apps/desktop/src/app/right-sidebar/review/index.tsx` —— review 面板主体(文件树 + diff + 还原确认)。
- `apps/desktop/src/app/right-sidebar/review/file-tree.tsx` —— 改动文件的列表/树两种视图 + 右键动作。
- `apps/desktop/src/app/right-sidebar/review/tree-data.ts` —— 纯函数:扁平列表 / 目录聚合树。
- `apps/desktop/src/app/right-sidebar/review/ship-bar.tsx` —— commit / push / PR 动作条(也可整包交给 agent)。
- `apps/desktop/src/app/right-sidebar/review/churn-bar.tsx` —— 每行 churn 的"数字雨"条;**文件头注释自陈"Not wired in"**(死代码,保留待复活)。

**终端簇(17)**

- `apps/desktop/src/app/right-sidebar/store.ts` —— 终端 takeover 开关 + 待注入命令(30 行)。
- `apps/desktop/src/app/right-sidebar/terminal/terminals.ts` —— 终端标签的 store(创建/选择/关闭/重命名/复活缓冲)。
- `apps/desktop/src/app/right-sidebar/terminal/use-terminal-session.ts` —— PTY 会话 hook(本片最长文件,1,059 行):连接、复活快照、OSC 7 cwd 探测。
- `apps/desktop/src/app/right-sidebar/terminal/instance.tsx` —— 单个 xterm 宿主(交互式 / agent 只读两种)。
- `apps/desktop/src/app/right-sidebar/terminal/persistent.tsx` —— 挂在布局根、用 `position: fixed` 追踪 slot 的常驻 xterm。
- `apps/desktop/src/app/right-sidebar/terminal/chrome.tsx` —— 面板内的 slot + rail 组合(24 行)。
- `apps/desktop/src/app/right-sidebar/terminal/workspace.tsx` —— 终端工作区:把活动 id 喂给 `buffer` 的读者表。
- `apps/desktop/src/app/right-sidebar/terminal/rail.tsx` —— 终端标签栏(右键菜单、中键关闭、快捷键提示)。
- `apps/desktop/src/app/right-sidebar/terminal/buffer.ts` —— **agent 侧接缝**:序列化 xterm 缓冲给 `read_terminal` 工具。
- `apps/desktop/src/app/right-sidebar/terminal/agent-terminal-stream.ts` —— agent 终端输出的写入器注册 + 每进程 256KB backlog。
- `apps/desktop/src/app/right-sidebar/terminal/use-agent-terminal.ts` —— agent 只读终端 hook。
- `apps/desktop/src/app/right-sidebar/terminal/active-resize.ts` —— 只对可见终端跑 ResizeObserver + 每帧一次 fit。
- `apps/desktop/src/app/right-sidebar/terminal/clipboard.ts` —— 终端复制/粘贴键位判定 + 选择镜像到隐藏 textarea。
- `apps/desktop/src/app/right-sidebar/terminal/selection.ts` —— VS Code 默认终端调色板 + 选择标签/锚点。
- `apps/desktop/src/app/right-sidebar/terminal/links.ts` —— 链接激活(⌘/Ctrl+click)与两条链接路径的统一出口。
- `apps/desktop/src/app/right-sidebar/terminal/terminal-font.ts` —— 终端字体族的 store/归一/预热/应用(11 个导出)。
- `apps/desktop/src/app/right-sidebar/terminal/use-terminal-font.ts` —— 字体控制器 hook(53 行)。

---

## 1. 这一簇解决什么问题

一条 assistant 消息在协议上是 **part 数组**(text / reasoning / tool-call / …),
在屏幕上必须变成"人能读的一段对话"。这一片就是那个转换,它同时要满足四件互相拉扯的事:

1. **分派**:每种 part、每个工具名要落到哪个组件;没有专属组件时的回落是什么。
2. **降噪**:一轮可能有几十次工具调用。全展开会把答案埋掉,全折叠又看不见 diff。
3. **不受信内容落地**:模型输出的 markdown/HTML/SVG/mermaid、工具返回的 ANSI、远端图片与第三方 iframe,都在这一层变成 DOM。
4. **不卡**:30Hz 的 token 流打在一棵长 transcript 上,任何一个没 memo 住的选择器都会放大成千次无效渲染。

四个约束的取舍痕迹在这一片到处可见,后面逐节记。

---

## 2. 接缝穷举(判据 2)

### 2.1 导出面(全片)

全片 **123 个 `.ts`/`.tsx` 文件、366 处顶层导出**,**没有一个文件是零导出**。
唯一的三条 `export *` re-export 都在同一个文件里:

`apps/desktop/src/components/assistant-ui/tool/fallback-model/index.ts:30 @ 863e313`

```
export * from './format'
export * from './targets'
export * from './types'
```

```verify
# 在 hermes-study 仓库根执行
python3 data/r10b/probes/probe_f_exports.py /home/user/hermes-agent data/r10b/slices/F.txt | wc -l
# → 366   (stderr 另打印 "# files=123 exports=366")

# 零导出文件(应为空)
python3 data/r10b/probes/probe_f_exports.py /home/user/hermes-agent data/r10b/slices/F.txt \
  | cut -f1 | sort -u > /tmp/f-with-exports.txt
grep -E '\.tsx?$' data/r10b/slices/F.txt | sort | comm -23 - /tmp/f-with-exports.txt
# → (无输出)
```

探针:`data/r10b/probes/probe_f_exports.py`(纯文本扫描顶层 `export`,不做 TS 解析)。

### 2.2 接缝 ① message part → 组件(**5 项,穷举**)

这是整片的根分派。Hermes 只覆写 5 个槽位,其余槽位留给库默认实现。

`apps/desktop/src/components/assistant-ui/thread/message-parts.tsx:264 @ 863e313`

```
export const MESSAGE_PARTS_COMPONENTS = {
  Reasoning: ReasoningTextPart,
  ReasoningGroup: ReasoningAccordionGroup,
  Text: MarkdownText,
  ToolGroup: ToolGroupSlot,
  tools: { Fallback: ChainToolFallback }
} as const
```

| 槽位 | 覆写成 | 干什么 |
|---|---|---|
| `Text` | `MarkdownText` | `apps/desktop/src/components/assistant-ui/markdown-text.tsx:642`:`export const MarkdownText = memo(MarkdownTextImpl)` |
| `Reasoning` | `ReasoningTextPart` | 同一 markdown 管线,`disableArtifacts`(草稿不许注册 artifact 版本) |
| `ReasoningGroup` | `ReasoningAccordionGroup` | 连续 reasoning part 折成一个 "Thinking / Thought for 12s" 折叠块 |
| `ToolGroup` | `ToolGroupSlot` | `apps/desktop/src/components/assistant-ui/tool/fallback.tsx:954`:`export const ToolGroupSlot: FC<PropsWithChildren<{ endIndex: number; startIndex: number }>> = ({` |
| `tools.Fallback` | `ChainToolFallback` | 工具名 → 组件的第二级分派(见 2.3) |

**没有覆写的槽位**(库侧类型 `MessagePrimitiveParts.BaseComponents` / `StandardComponents`,
定义在 `@assistant-ui/core` 的 npm 包里而**不在基线仓库内**,故无锚点):
`Empty`、`Source`、`Image`、`File`、`Unstable_Audio`、`data`、`Quote`、`generativeUI`、`ChainOfThought`。
一个值得记的设计选择:库的 `tools` 配置本身就支持 **`by_name`**(工具名 → 组件的 map),
Hermes **不用它**,而是只填 `Fallback`、在自己的组件里写 if 链。代价是分派表不能被静态枚举;
收益是同一个入口能顺带做"这个工具根本不渲染"(见下)。

### 2.3 接缝 ② 工具名 → 组件(**6 条分支,穷举**)

`apps/desktop/src/components/assistant-ui/thread/message-parts.tsx:50 @ 863e313`

```
const ChainToolFallback: FC<ToolCallMessagePartProps> = props => {
  // todo parts are hoisted to a dedicated panel above the message content.
  if (props.toolName === 'todo') {
    return null
  }

  // A reaction's UI is the emoji landing on the bubble (message.reaction
  // event) — a "React To Message" tool block next to it would be the agent
  // narrating its own tapback. Failures still render so they're debuggable.
  if (props.toolName === 'react_to_message' && !props.isError) {
    return null
  }

  if (props.toolName === 'delegate_task') {
    return <DelegateToolPart {...props} />
  }

  if (props.toolName === 'image_generate') {
    return <ImageGenerateTool {...props} />
  }

  if (props.toolName === 'clarify') {
    return <ClarifyTool {...props} />
  }

  return <ToolFallback {...props} />
}
```

| 工具名 | 渲染成 | 回落条件 |
|---|---|---|
| `todo` | **不渲染**(null) | 无条件;todo 面板在 composer 状态栈 |
| `react_to_message` | **不渲染**(null) | 仅 `!isError`;失败时落回 `ToolFallback` |
| `delegate_task` | `DelegateTool` 扇出卡 | `props.isError` 时落回 `ToolFallback`(`message-parts.tsx:42`) |
| `image_generate` | `GeneratedImage` 图卡 | 有 result 但 `generatedImageFromResult()` 解不出时落回 `ToolFallback`(`message-parts.tsx:29`) |
| `clarify` | `ClarifyTool` 问答卡 | 有 result → 定格态;无 result 且消息已停 → `ToolFallback`(`clarify-tool.tsx:200`) |
| **其他一切** | `ToolFallback` → `ToolEntry` | 这是 fallback 本身 |

三个"专属卡片"工具再被登记进 `CARD_TOOLS`,决定它们**不被折进运行摘要**:

`apps/desktop/src/components/assistant-ui/tool/fallback.tsx:752 @ 863e313`

```
const CARD_TOOLS = new Set(['clarify', 'delegate_task', 'image_generate'])
```

`apps/desktop/src/components/assistant-ui/tool/fallback-model/index.ts:34 @ 863e313`

```
const FILE_EDIT_TOOL_NAMES = new Set(['edit_file', 'patch', 'write_file'])
```

两个集合的并集就是"卡片工具",共 **6 个名字**:

`apps/desktop/src/components/assistant-ui/tool/fallback.tsx:754 @ 863e313`

```
export function isCardTool(toolName: string): boolean {
  return CARD_TOOLS.has(toolName) || isFileEditTool(toolName)
}
```

### 2.4 接缝 ③ `TOOL_META`:23 行图标/色调/文案表(**穷举 + 与内核对账**)

`buildToolView()` 先查这张表拿"专属"元数据;查不到走前缀表(`browser_` / `web_`),再查不到走
`titleForTool()` 拆下划线首字母大写。三级回落。

```verify
awk 'NR>=143 && NR<=213' \
  /home/user/hermes-agent/apps/desktop/src/components/assistant-ui/tool/fallback-model/index.ts \
  | grep -cE '^  [a-z_0-9]+:'
# → 23
```

这 23 个键与 i18n 的 `ToolTitleKey` 联合一一对应 —— 也就是说每个键都必须配齐
`done` / `pending` / `pendingAction` 三句文案 × 5 种语言:

`apps/desktop/src/i18n/types.ts:10 @ 863e313`

```
export type ToolTitleKey =
  | 'browser_click'
  | 'browser_fill'
  | 'browser_navigate'
  | 'browser_snapshot'
```

23 个键按 tone 分组:

| tone | 键 |
|---|---|
| `browser` | `browser_click` `browser_fill` `browser_navigate` `browser_snapshot` `browser_take_screenshot` `browser_type` |
| `agent` | `clarify` `cronjob` `memory` `session_search_recall` `todo` |
| `file` | `edit_file` `list_files` `patch` `read_file` `search_files` `write_file` |
| `terminal` | `execute_code` `terminal` |
| `image` | `image_generate` `vision_analyze` |
| `web` | `web_extract` `web_search` |

**与内核工具注册表的机械对账**(探针 `data/r10b/probes/probe_f_tool_names.py`):

```verify
python3 data/r10b/probes/probe_f_tool_names.py /home/user/hermes-agent
# TOOL_META keys        : 23
# kernel registered     : 82
# UI-only (dead rows)   : 5 -> browser_fill, browser_take_screenshot, edit_file, list_files, session_search_recall
# kernel-only (generic) : 64
```

结论见 §6 的 ■-1。反向的 64 个"内核有、渲染层没点名"**不是缺口**——那正是三级回落的设计目的
(`browser_press` / `browser_scroll` 走 `browser_` 前缀;`kanban_create` 走 `titleForTool` → "Kanban Create")。

### 2.5 接缝 ④ 其他工具名集合(**4 张,逐项列全**)

`apps/desktop/src/components/assistant-ui/tool/approval.tsx:46 @ 863e313`

```
export const APPROVAL_TOOLS = new Set(['terminal', 'execute_code'])
```

`apps/desktop/src/components/assistant-ui/tool/run-summary.ts:35 @ 863e313`

```
const EXPLORE_TOOLS = new Set([
  'list_files',
  'read_file',
  'search_files',
  'session_search_recall',
  'vision_analyze',
  'web_extract',
  'web_search'
])
```

| 集合 | 条数 | 全部成员 | 用途 |
|---|---|---|---|
| `APPROVAL_TOOLS` | 2 | `terminal`, `execute_code` | `apps/desktop/src/components/assistant-ui/tool/approval.tsx:58` 的 `if (!request || !APPROVAL_TOOLS.has(part.toolName)) {` —— 决定审批条挂在哪一行下面 |
| `CARD_TOOLS` | 3 | `clarify`, `delegate_task`, `image_generate` | 不折进运行摘要 |
| `FILE_EDIT_TOOL_NAMES` | 3 | `edit_file`, `patch`, `write_file` | 文件编辑判定(图标用文件类型图标、diff 面板、changed-files 卡) |
| `EXPLORE_TOOLS` | 7 | 上面代码块 7 行 | 运行摘要归类为 "Explored N files" |
| `DEFAULT_COUNT_NOUN_BY_TOOL` | 6 | `browser_snapshot`→item, `list_files`→file, `search_files`→result, `session_search_recall`→result, `todo`→todo, `web_search`→result | 计数标签的默认量词 |

运行摘要的类别只有 5 个,且**顺序固定**(同一 run 无论哪个类别在活跃,读出来的句子结构一样):

`apps/desktop/src/components/assistant-ui/tool/run-summary.ts:25 @ 863e313`

```
const CATEGORY_ORDER: readonly RunCategory[] = ['edit', 'explore', 'run', 'delegate', 'other']
```

分类函数 `toolCategory()` 的判定顺序:file-edit → `terminal|execute_code` → `delegate_task` →
`EXPLORE_TOOLS ∪ browser_*` → `other`。

### 2.6 接缝 ⑤ `ToolView` 契约(**22 个字段,穷举**)

`buildToolView(part, inlineDiff) → ToolView` 是"工具调用原始数据 → 可渲染视图"的唯一出口。

`apps/desktop/src/components/assistant-ui/tool/fallback-model/types.ts:30 @ 863e313`

```
export interface ToolView {
  countLabel?: string
  detail: string
  detailLabel: string
  durationLabel?: string
  icon?: string
  imageUrl?: string
  inlineDiff: string
  previewTarget?: string
```

全部字段与填法:

| 字段 | 类型 | 由谁填 |
|---|---|---|
| `title` | string | `dynamicTitle()`,7 个工具有专属句式 |
| `titleAction` | `ToolTitleAction?` | 标题里要打 shimmer 的那个动词片段(前缀/文本/后缀三段) |
| `subtitle` | string | `toolSubtitle()`,9 个分支 |
| `detail` | string | `toolDetailText()` + 去分隔线 |
| `detailLabel` | string | 错误时 `'Error details'`;`web_search`→`'Details'`;`browser_snapshot`→`'Snapshot summary'`;其余空 |
| `status` | `'error'\|'running'\|'success'\|'warning'` | `toolStatus()`;`memory` 失败降级为 warning |
| `tone` | `ToolTone` | `TOOL_META` / 前缀表 / `'default'` |
| `icon` | string? | codicon 名,同上 |
| `countLabel` | string? | `toolResultCount()`:24 个计数字段名 + 7 个数组字段名 + 文本兜底正则 |
| `durationLabel` | string? | `result.duration_s` |
| `inlineDiff` | string | 参数传入(sideband store 或 result) |
| `imageUrl` | string? | **只认 `data:image/` 或 http(s) 且扩展名在 png/jpe?g/gif/webp/bmp/svg** |
| `previewTarget` | string? | 见 §2.9 |
| `searchQuery` / `searchHits` | string? / `SearchResultRow[]?` | 仅 `web_search`,最多 6 条 |
| `stdout` / `stderr` | string? | 仅 `terminal`/`execute_code`,且后端确实分了流 |
| `rendersAnsi` | boolean? | 仅 `terminal`/`execute_code` |
| `terminalCommand` / `terminalExitCode` | string? / number? | 仅 `terminal` |

### 2.7 接缝 ⑥ markdown 标签覆写(**18 项,穷举**)

```verify
sed -n '476,590p' /home/user/hermes-agent/apps/desktop/src/components/assistant-ui/markdown-text.tsx \
  | grep -cE '^        [A-Za-z][A-Za-z0-9]*:'
# → 18
```

`h1` `h2` `h3` `h4` `p` `a` `inlineCode` `hr` `blockquote` `ul` `ol` `li` `table` `thead` `th` `td` `img` `SyntaxHighlighter`。

其中三个是**安全/路由相关**,不是排版。`a` 的五级判定
(媒体路径 → 预览目标 → session 引用 → 非 http(s) 的原样 `<a rel="noopener noreferrer">` →
`PrettyLink`/富嵌入)从这里开始:

`apps/desktop/src/components/assistant-ui/markdown-text.tsx:252 @ 863e313`

```
function MarkdownLink({ children, className, href, ...props }: ComponentProps<'a'>) {
  const mediaPath = mediaPathFromMarkdownHref(href)

  if (mediaPath) {
    return <MediaAttachment path={mediaPath} />
  }
```

另两个:`img` → `MarkdownImage`(`apps/desktop/src/components/assistant-ui/markdown-text.tsx:317`,
按扩展名把 video/audio 路由到 `<video>/<audio>`);`SyntaxHighlighter` →
artifact 提升 / `RichCodeBlock` / shiki 三选一。

**同一仓库里有三条 markdown 路径**,面向三种输入。第二条给工具详情体
(Streamdown `mode="static"`,17 项覆写):

`apps/desktop/src/components/chat/compact-markdown.tsx:81 @ 863e313`

```
const COMPONENTS = {
  a: MarkdownAnchor,
  blockquote: tagged('blockquote'),
  code: MarkdownCode,
  h1: tagged('h1'),
```

第三条给 user 气泡,是手写切分器,只认围栏与行内 code(外加指令 chip):

`apps/desktop/src/components/assistant-ui/thread/user-message-text.tsx:121 @ 863e313`

```
export const UserMessageText: FC<UserMessageTextProps> = ({ className, text }) => {
  const top = useMemo(() => splitFences(text), [text])
```

### 2.8 接缝 ⑦ 嵌入(**8 matcher / 9 provider / 4 渲染器 / 2 围栏语言,全部穷举**)

`apps/desktop/src/components/assistant-ui/embeds/providers/index.ts:14 @ 863e313`

```
const MATCHERS: EmbedMatcher[] = [youtube, vimeo, instagram, pinterest, tiktok, twitter, spotify, maps]
```

8 个 matcher 产出 9 个 provider(`maps` 一个 matcher 里含 Google Maps 与 OpenStreetMap 两支):

| provider | 匹配主机 | 路径要求 | renderer | 布局 |
|---|---|---|---|---|
| `youtube` | youtu.be / youtube.com / youtube-nocookie.com | 11 位 id | frame | 16:9,max 640 |
| `vimeo` | vimeo.com / player.vimeo.com | 末段纯数字 | frame | 16:9,max 640 |
| `instagram` | instagram.com | `/p\|reel\|tv/<code>` | frame(**实走 social**) | 高 450,max 400 |
| `pinterest` | 主机含 `pinterest.` | `/pin/<digits>` | frame | 高 380,max 236 |
| `tiktok` | tiktok.com | `…/video/<digits>` | frame | 9:16,max 365 |
| `twitter` | twitter.com / x.com | `…/status/<digits>` | **tweet** | max 480 |
| `spotify` | open.spotify.com | 6 类型 × id | frame | 高 152,max 480 |
| `googlemaps` | google.* 且 `/maps` 或 `maps.` 子域 | 需能解出 `q` | frame | 16:10,max 640 |
| `openstreetmap` | openstreetmap.org | fragment `#map=z/lat/lng` | frame | 16:10,max 640 |

**descriptor → 渲染器**的分派(4 个懒加载 chunk),注意它**不完全按 `renderer` 字段走**:

`apps/desktop/src/components/assistant-ui/embeds/url-embed.tsx:28 @ 863e313`

```
function LazyRenderer({ descriptor }: { descriptor: EmbedDescriptor }) {
  // X and Instagram load their official blockquote script in-document. The tweet
  // check also narrows the union to FrameEmbed for the iframe renderers below.
  if (descriptor.renderer === 'tweet' || descriptor.provider === 'instagram') {
    return <SocialEmbedRenderer descriptor={descriptor} />
  }

  if (descriptor.provider === 'youtube') {
    return <YouTubeEmbedRenderer descriptor={descriptor} />
  }

  if (descriptor.provider === 'spotify') {
    return <SpotifyEmbedRenderer descriptor={descriptor} />
  }

  return <FrameEmbedRenderer descriptor={descriptor} />
}
```

即:`twitter`+`instagram` → social;`youtube` → youtube-embed;`spotify` → spotify-embed;
其余 6 个 provider → frame-embed。`instagram` 的 descriptor 明明写着 `renderer: 'frame'` 和一个
`embedUrl`,却被 provider 名硬拐到 social —— 那个 `embedUrl` 因此**从不被使用**。

**围栏语言 → 懒渲染器**(只有 2 种):

`apps/desktop/src/components/assistant-ui/embeds/registry.tsx:11 @ 863e313`

```
const LAZY_FENCE: Record<string, LazyExoticComponent<ComponentType<RichFenceProps>>> = {
  mermaid: lazy(() => import('./mermaid-embed')),
  svg: lazy(() => import('./svg-embed'))
}

export const RICH_FENCE_LANGUAGES: ReadonlySet<string> = new Set(Object.keys(LAZY_FENCE))
```

**GFM 告示种类**(5 种,样式表在 `apps/desktop/src/components/assistant-ui/embeds/alert.tsx:15`):
`caution` `important` `note` `tip` `warning`,由这一个正则识别:

`apps/desktop/src/components/assistant-ui/embeds/alert.tsx:23 @ 863e313`

```
const MARKER_RE = /^\s*\[!(note|tip|important|warning|caution)\]\s*\n?/i
```

**第三方脚本注入面**(3 条,其中 tiktok 那条不可达 —— 见上,tiktok 走 frame):

`apps/desktop/src/components/assistant-ui/embeds/social-embed.tsx:21 @ 863e313`

```
const SCRIPT: Record<string, { id: string; src: string }> = {
  instagram: { id: 'hermes-ig-embed', src: 'https://www.instagram.com/embed.js' },
  tiktok: { id: 'hermes-tt-embed', src: 'https://www.tiktok.com/embed.js' },
  twitter: { id: 'hermes-tw-embed', src: 'https://platform.twitter.com/widgets.js' }
}
```

### 2.9 接缝 ⑧ 引用词汇表(**16 kind / 8 wire kind / 2 可激活动作**)

```verify
awk 'NR>=60 && NR<=119' \
  /home/user/hermes-agent/apps/desktop/src/components/assistant-ui/reference-kinds.ts \
  | grep -cE '^  [a-z]+: \{'
# → 16
```

16 种 kind:`file` `folder` `url` `image` `tool` `line` `terminal` `session` `git` `diff` `staged`
`command` `skill` `theme` `emoji` `other`。其中能进消息文本(`@kind:value`)的只有 8 种:

`apps/desktop/src/components/assistant-ui/reference-kinds.ts:138 @ 863e313`

```
export const WIRE_REFERENCE_KINDS = ['file', 'folder', 'url', 'image', 'tool', 'line', 'terminal', 'session'] as const
```

`apps/desktop/src/components/assistant-ui/reference-kinds.ts:147 @ 863e313`

```
const REFERENCE_PATTERN = /@(file|folder|url|image|tool|line|terminal|session):(`[^`\n]+`|"[^"\n]+"|'[^'\n]+'|\S+)/
```

**可点击激活的 kind 只有 2 种**:

`apps/desktop/src/components/assistant-ui/directive-text.tsx:473 @ 863e313`

```
export const DIRECTIVE_ACTIONS: Record<string, DirectiveAction> = {
  session: {
    icon: 'link-external',
    label: t => t.composer.openDirective,
    run: openSessionRef
  },
  url: {
    icon: 'link-external',
    label: t => t.composer.openDirective,
    run: openExternalLink
  }
}
```

其余 kind 渲染成惰性 `<span>` —— 表里没有条目就没有 `activate`,连 `<button>` 都不是:

`apps/desktop/src/components/assistant-ui/directive-text.tsx:543 @ 863e313`

```
  const activate = onClick ?? (DIRECTIVE_ACTIONS[type] ? () => DIRECTIVE_ACTIONS[type]!.run(id) : undefined)
```

`DirectiveContent` 里另有 3 条特判
(`apps/desktop/src/components/assistant-ui/directive-text.tsx:353-363`):`image` 段**不内联**、
改到底部缩略图行;`session` 走 `SessionRefChip`(异步解析标题);`skill` 走 `SlashChip`。

### 2.10 接缝 ⑨ 右侧栏的面板注册面(**5 个 pane,3 个属本片**)

面板不是在 right-sidebar 里 mount 的,而是通过 contrib registry 声明式注册。注册点在片外
(`apps/desktop/src/app/contrib/controller.tsx`),本片提供其中三个的 render 实现:

| pane id | placement | 注册处 | 本片对应实现 |
|---|---|---|---|
| `sessions` | left | `apps/desktop/src/app/contrib/controller.tsx:139` 的 `id: 'sessions',` | 片外 |
| `workspace` | main | `apps/desktop/src/app/contrib/controller.tsx:157` 的 `id: 'workspace',` | 片外(transcript 宿主) |
| `terminal` | bottom | `apps/desktop/src/app/contrib/controller.tsx:171` 的 `id: 'terminal',` | `right-sidebar/terminal/*`(17 文件) |
| `files` | right | `apps/desktop/src/app/contrib/controller.tsx:187` 的 `id: 'files',` | `right-sidebar/index.tsx` + `files/*` |
| `review` | right | `apps/desktop/src/app/contrib/controller.tsx:203` 的 `id: 'review',` | `right-sidebar/review/*` |

四个内置布局预设(`apps/desktop/src/app/contrib/controller.tsx:384-387`)都把这 5 个 pane
排进树:`default` / `focus` / `terminal-deck` / `quad`。

**默认树里终端在右列的下半** —— `grp-terminal` 与 `[review, files]` 同属 `spl-right` 这个
column split,不是独立底栏。`placement: 'bottom'` 只是 contribution 的落位提示,
真正的默认位置由这棵树决定:

`apps/desktop/src/app/contrib/controller.tsx:339 @ 863e313`

```
const DEFAULT_TREE = split(
  'row',
  [
```

### 2.11 接缝 ⑩ 渲染层 ↔ 内核的双向通道(**本片涉及的 6 条**)

| 方向 | 事件/方法 | 渲染侧落点 |
|---|---|---|
| 内核 → UI | `tool.start` | 建 tool-call part(名字+context;**无结构化 args**) |
| 内核 → UI | `tool.complete` | 结果 + `duration_s` + `summary` + **`inline_diff`(仅事件,不入 result)** |
| 内核 → UI | `approval.request` | `apps/desktop/src/store/prompts.ts:106` 的 `export const sessionApprovalRequest = (sessionId: string | null) =>` |
| UI → 内核 | `approval.respond` | `apps/desktop/src/components/assistant-ui/tool/approval.tsx:145` 的 `await gateway.request<{ resolved?: boolean }>('approval.respond', {` |
| 内核 → UI(请求) | `terminal.read.request` | `apps/desktop/src/app/right-sidebar/terminal/buffer.ts:44` 的 `export function readActiveTerminal(opts: TerminalReadOptions): TerminalReadResult \| null {` |
| UI → 内核(应答) | `terminal.read.respond` | 见 §3.2 |
| 内核 → UI | `agent.terminal.output` | `apps/desktop/src/app/right-sidebar/terminal/agent-terminal-stream.ts:37` 的 `export function writeAgentTerminalChunk(procId: string, chunk: string): void {` |

---

## 3. 端到端链(判据 3)

### 3.1 链 A:危险命令审批(用户动作 → 组件 → 状态 → 协议 → 内核)

**场景**:agent 要跑 `rm -rf build/`。内核的 `terminal` 守卫判为需审批,阻塞在
`_await_gateway_decision()`;桌面在那一行工具行下面长出一条按钮条;用户按 ⌘⏎;agent 继续。

**跳 1 — 内核发事件。** `tui_gateway/server.py:1811 @ 863e313`

```
    _emit("approval.request", sid, payload)
```

同一函数在发之前做了两件事:补 `choices`(按 `smart_denied` / `allow_permanent` 推出可选项),
以及用 `_redact_approval_command` 把命令里的凭据形状打码 —— 因为这是第三条出口通道。

**跳 2 — 渲染层收事件、写会话级 store。**
`apps/desktop/src/app/session/hooks/use-message-stream/gateway-event.ts:917 @ 863e313`

```
      } else if (event.type === 'approval.request') {
```

`apps/desktop/src/app/session/hooks/use-message-stream/gateway-event.ts:927 @ 863e313`

```
        setApprovalRequest({
          // false only when a tirith warning forbids it; backend omits the field otherwise.
          allowPermanent: payload?.allow_permanent !== false,
          choices: Array.isArray(payload?.choices)
            ? payload.choices.filter(choice => typeof choice === 'string')
            : undefined,
          command,
          description,
          sessionId: sessionId ?? null,
          smartDenied: payload?.smart_denied === true
        })
```

**跳 3 — 组件挂载点。** 审批条挂在"仍在 pending 的那一行工具行"下面:

`apps/desktop/src/components/assistant-ui/tool/fallback.tsx:590 @ 863e313`

```
      {isPending && <PendingToolApproval part={part} />}
```

`apps/desktop/src/components/assistant-ui/tool/approval.tsx:58 @ 863e313`

```
  if (!request || !APPROVAL_TOOLS.has(part.toolName)) {
```

**这是位置绑定,不是命令匹配。** 文件头注释把理由写清楚了:`tool.start` 事件里根本没有结构化
args(只有 tool_id / name / context),所以前端**无法**按命令串把审批 join 到某一行;但
`approval.request` 只可能来自 `terminal` / `execute_code` 两个守卫,且 agent 线程一次只阻塞在
一个审批上 —— 所以"那两个工具里唯一 pending 的那一行"**就是**发起审批的那一行。命令文本另从
事件 payload 取。

**跳 4 — 用户动作 → RPC。** ⌘⏎ / 点 Run / Esc 都走同一个 `respond()`:

`apps/desktop/src/components/assistant-ui/tool/approval.tsx:145 @ 863e313`

```
        await gateway.request<{ resolved?: boolean }>('approval.respond', {
          choice,
          session_id: request.sessionId ?? undefined
        })
```

**跳 5 — 内核解阻塞。** `tui_gateway/methods_prompt.py:915 @ 863e313`

```
@method("approval.respond")
def _(rid, params: dict) -> dict:
    session, err = _sess(params, rid)
    if err:
        return err
    try:
        from tools.approval import resolve_gateway_approval
```

**闸门的第二个消费者(同一状态,不同 UI)**:一个正在滚动的 tool run 会把自己"打开"到全高,
只要它里面有 pending 的审批工具 —— 否则那条要用户回答的问题会被单行 ticker 直接滚过去。

`apps/desktop/src/components/assistant-ui/tool/fallback.tsx:920 @ 863e313`

```
  const blocked = Boolean(approval) && pendingApprovalTool
  const unfurled = blocked || rowOpen
  const expanded = live ? unfurled : (persistedOpen ?? false)
```

### 3.2 链 B:`read_terminal` 工具反向读渲染层(内核 → UI → 内核)

内核工具 `read_terminal` 要读的是**用户屏幕上那个 xterm 的缓冲**,而缓冲只存在于渲染进程。
于是这条链是反的:内核发请求事件,渲染层同步作答。

**跳 1 — 注册。** 每个活着的 xterm 注册一个 reader,键是终端 id:

`apps/desktop/src/app/right-sidebar/terminal/use-terminal-session.ts:986 @ 863e313`

```
    const term = termRef.current

    return term ? registerTerminalReader(id, makeTerminalReader(term)) : undefined
```

**跳 2 — 选活。** 标签选择驱动 `setActiveTerminalId`;按 id 而不是按"最后一个注册者"选活,
是为了让"正在卸载的 tab 的清理"不能把"刚激活的 tab"置空:

`apps/desktop/src/app/right-sidebar/terminal/workspace.tsx:24 @ 863e313`

```
  // Mirror the tab selection into the agent reader (read_terminal reads it).
  useEffect(() => {
    const unsubscribe = $activeTerminalId.subscribe(setActiveTerminalId)
```

**跳 3 — 应答。**

`apps/desktop/src/app/session/hooks/use-message-stream/gateway-event.ts:1007 @ 863e313`

```
          const result = readActiveTerminal({ start, count })

          void $gateway.get()?.request('terminal.read.respond', {
            request_id: requestId,
            text: result ? JSON.stringify(result) : ''
          })
```

序列化的形状由本片定义,行号是**绝对**的(0 = 最老的 scrollback 行),这样 agent 能用
`start_line/count` 对着 `total_lines` 翻页:

`apps/desktop/src/app/right-sidebar/terminal/buffer.ts:6 @ 863e313`

```
export interface TerminalReadResult {
  total_lines: number
  start: number
  end: number
  viewport_rows: number
  cursor_row: number
  text: string
}
```

没有活动终端时 `text: ''` —— Python 侧阻塞在 respond 上,所以**必须**立刻答,哪怕答空。

---

## 4. 逐机制 / 逐区域

### 4.1 分派的三层结构

```text
MessagePrimitive.Parts
  └─ MESSAGE_PARTS_COMPONENTS            (第 1 层:part 类型 → 组件,5 个槽位)
       ├─ Text / Reasoning  → markdown 管线
       ├─ ReasoningGroup    → Thinking 折叠块
       └─ ToolGroup         → ToolGroupSlot
            └─ splitRunItems()           (第 2 层:相邻工具调用 → card / run 切分)
                 ├─ card  → 原样渲染那一行
                 └─ run   → 摘要行 + (live ? 单行 ticker : 折叠体)
                      └─ ChainToolFallback  (第 3 层:工具名 → 组件,6 分支)
                           └─ ToolFallback → ToolEntry → buildToolView()
```

第 2 层是这片最值得学的一处设计。assistant-ui 把"相邻的一批工具调用"整段交过来,但
**"相邻"和"该放一起"不是一回事**:一次 diff、一个要用户回答的问题,是这一轮的产出,必须留在原位;
读文件、跑命令是过程,应该塌成一行。`splitRunItems()`
(`apps/desktop/src/components/assistant-ui/tool/fallback.tsx:769`)按 `isCardTool`
在保序的前提下切成 `card` 与 `run` 两种条目,所以"读→改→再读"会渲染成
"摘要 / diff / 摘要"三段,而不是"所有摘要 + 所有 diff"。

run 的身份**用它的第一个 tool call id,而不是位置**
(`apps/desktop/src/components/assistant-ui/tool/fallback.tsx:904`)。理由写在注释里:实时流与从历史重放对
"哪几个调用是一组"看法一致,但对"它们落在第几个 index"看法不一致 —— 重放会把一整轮折进一个气泡,
而实时视图把它铺在好几个上。按 index 做键,曾经导致一轮刚结束就整片重排。

### 4.2 不受信内容的落地点(本片最该看清楚的一条线)

模型输出与工具结果在这一层变成 DOM。逐条列出**所有会产生 HTML/脚本/远端请求的出口**:

| 出口 | 守卫 | 位置 |
|---|---|---|
| ```` ```svg ```` 围栏 | **DOMPurify svg profile** | `apps/desktop/src/components/assistant-ui/embeds/svg-embed.tsx:14` 的 `DOMPurify.sanitize(code, {` |
| ```` ```mermaid ```` 围栏 | **mermaid `securityLevel: 'strict'`** | `apps/desktop/src/components/assistant-ui/embeds/mermaid-embed.tsx:25` 的 `mermaid.initialize({ fontFamily: 'inherit', securityLevel: 'strict', startOnLoad: false, theme })` |
| markdown 正文 | Streamdown 自身(不走 `dangerouslySetInnerHTML`) | `markdown-text.tsx:599` |
| 裸链接 → 富嵌入 | provider 白名单 + 同意闸门 + 固定 embedUrl 主机 | 见下 |
| X/Instagram blockquote | `escapeHtml()` 拼属性 + 官方脚本 | `apps/desktop/src/components/assistant-ui/embeds/social-embed.tsx:30` 的 `const url = escapeHtml(descriptor.sourceUrl)` |
| 外链点击 | `openExternalLink` / `PrettyLink`,非 http(s) 走 `rel="noopener noreferrer"` | `markdown-text.tsx:273` |
| 工具结果里的图片 | 只认 `data:image/` 或带图片扩展名的 http(s) | `fallback-model/index.ts:775` |
| 终端输出 | 自研 ANSI 解析 → span,不注入 HTML | `apps/desktop/src/components/assistant-ui/ansi-text.tsx:14` 的 `export const AnsiText = memo(({ className, text }: AnsiTextProps) => {` |

**SVG 净化。** `apps/desktop/src/components/assistant-ui/embeds/svg-embed.tsx:11 @ 863e313`

```
export default function SvgRenderer({ code }: RichFenceProps) {
  const clean = useMemo(
    () =>
      DOMPurify.sanitize(code, {
        USE_PROFILES: { svg: true, svgFilters: true }
      }),
    [code]
  )
```

守卫**绑在渲染点上**,不是绑在数据入口:同一段 `code` 走别的路径(复制、artifact)不经过这里。
这是本项目历轮反复出现的形态,记一笔。

**第三方请求的隐私闸门。** 富嵌入要向第三方发请求(IP / referer / cookie),所以默认不发:

`apps/desktop/src/components/assistant-ui/embeds/url-embed.tsx:54 @ 863e313`

```
  if (mode === 'off') {
    return <PrettyLink className="wrap-anywhere" href={descriptor.sourceUrl} />
  }

  const consented = mode === 'always' || loaded || allowed.includes(descriptor.provider)
```

三档全局模式 `off` / `ask`(默认) / `always`,外加 per-provider 的"永久允许"清单,
两者都持久化在 `localStorage`:

`apps/desktop/src/store/embed-consent.ts:18 @ 863e313`

```
/** Global default: ask (placeholder), always (auto-load), off (plain link). */
export const $embedMode = persistentAtom<EmbedMode>(MODE_KEY, 'ask', modeCodec)
/** Providers granted a standing "always allow" (e.g. `youtube`, `twitter`). */
export const $embedAllowed = persistentAtom<string[]>(ALLOWED_KEY, [], Codecs.stringArray)
```

**纯客户端**:发请求的是渲染进程,所以这个闸门不经网关、也不写 `config.yaml` —— 与工具审批
(走网关、可落盘)是同构但独立的两套。

还有一层收窄:富嵌入**只在裸自动链接上触发**,`[watch](url)` 这种带标签的链接保持纯链接,
而且只在桌面端(有 webview/iframe 渲染器)才试:

`apps/desktop/src/components/assistant-ui/markdown-text.tsx:289 @ 863e313`

```
  // Bare autolink → inline rich embed when a provider matches. Labeled links
  // (`[watch](url)`) stay plain. Desktop only (webview / iframe renderers).
  if (window.hermesDesktop && text && normalizeExternalUrl(text) === target) {
    const embed = detectEmbed(target)

    if (embed) {
      return <UrlEmbed descriptor={embed} />
    }
  }
```

iframe 侧的加固是一条 `allow` 白名单 + 三个属性
(`referrerPolicy="strict-origin-when-cross-origin"`、`loading="lazy"`、`scrolling="no"`):

`apps/desktop/src/components/assistant-ui/embeds/frame-embed.tsx:9 @ 863e313`

```
const ALLOW = 'autoplay; encrypted-media; picture-in-picture; clipboard-write; fullscreen'
```

**没有 `sandbox` 属性** —— social-embed 的文件头注释解释了为什么不能沙箱化那一路
(官方脚本需要真实 origin 才能跑,`srcDoc` 的 null origin 下它们静默失败),
但 frame-embed 这一路的 iframe 也同样没有 sandbox。

### 4.3 降噪:什么时候一行都不画

这一片有**四处**会让内容彻底不出现,值得单独列全(它们是"transcript 看起来漏了东西"的全部来源):

1. `todo` part —— 无条件 null(`apps/desktop/src/components/assistant-ui/thread/message-parts.tsx:52`)。
2. `react_to_message` 成功 —— null(`apps/desktop/src/components/assistant-ui/thread/message-parts.tsx:59`);失败仍画。
3. **空 reasoning 组 —— 整个 Thinking 头都不画**:

`apps/desktop/src/components/assistant-ui/thread/message-parts.tsx:214 @ 863e313`

```
  const hasContent = useAuiState(s =>
    s.message.parts
      .slice(Math.max(0, startIndex), endIndex + 1)
      .some(p => p?.type === 'reasoning' && typeof p.text === 'string' && p.text.trim().length > 0)
  )

  if (!hasContent) {
    return null
  }
```

4. **已结算、成功、但没有 diff 的文件编辑行** —— null:

`apps/desktop/src/components/assistant-ui/tool/fallback.tsx:526 @ 863e313`

```
  // persists its diff in the tool result, so creates rehydrate diff-less and
  // read like dead duplicates of the real diff row. Hide them — but keep
  // in-flight writes (activity) and failures (errors) visible.
  if (isFileEdit && !isPending && view.status !== 'error' && !view.inlineDiff) {
    return null
  }
```

第 4 条的后果见 §6 ■-2。

另有两处是"折叠"而非"消失":`ToolRun` 在 `count < 2` 时不加摘要头
(`apps/desktop/src/components/assistant-ui/tool/fallback.tsx:911`),
以及用户可手动 dismiss 已结算的行(`$toolRowDismissed`)。

### 4.4 性能:三个"数出来的"预算

这一片有三个独立的上限,都不是拍脑袋定的:

| 预算 | 值 | 计的是什么 |
|---|---|---|
| DOM 渲染预算 | `apps/desktop/src/components/assistant-ui/thread/list.tsx:52` 的 `const RENDER_BUDGET = 300` | 每个 part 计 1,长字符串每 512 字再计 1 |
| 首帧预算 | `apps/desktop/src/components/assistant-ui/thread/list.tsx:64` 的 `const FIRST_PAINT_BUDGET = 20` | 切会话时先只画 20 单位,rAF 后用 transition 补齐 |
| 工具输出绘制上限 | `apps/desktop/src/components/assistant-ui/tool/fallback-model/format.ts:49` 的 `export const MAX_TOOL_RENDER_CHARS = 20_000` | 每个内联绘制的 payload;Copy 仍拿未截断的 |
| markdown 上限 | `apps/desktop/src/components/assistant-ui/markdown-text.tsx:431` 的 `const MAX_MARKDOWN_CHARS = 200_000` | 超过就退化成分块纯文本 |
| shiki 高亮上限 | `apps/desktop/src/components/chat/shiki-highlighter.tsx:44` 的 `const MAX_HIGHLIGHT_CHARS = 150_000` | 另有 `MAX_HIGHLIGHT_LINES = 3_000` |

`RENDER_BUDGET` 的注释记了它为什么从"数 part"改成"数渲染成本":只数 part 会把一个 51KB 的工具结果
记成 1,于是几个大结果就能把 600KB 的 transcript 放进 300-part 的旧上限,把 Chromium 渲染进程
推进 GC 崩溃。

还有一条"活尾"策略:最新的若干轮**不做** `content-visibility` 虚拟化。

`apps/desktop/src/components/assistant-ui/thread/list.tsx:171 @ 863e313`

```
export const LIVE_TAIL_PARTS = 40
// Floor: always exempt at least this many turns regardless of weight, so a
// transcript of very heavy turns still keeps the streaming one unvirtualized.
export const LIVE_TAIL_MIN_GROUPS = 2
// Ceiling: never exempt more than this many turns, however light they are. On a
// long transcript of tiny turns a weight-only budget would walk back further
// than the old turn-count tail did and virtualize LESS — this keeps the new
// policy a strict improvement on every shape.
export const LIVE_TAIL_MAX_GROUPS = 6
```

理由:`contain-intrinsic-size: auto` 只在元素**渲染过之后**才记住尺寸,一轮刚流完就被跳过会
snap 回流式中途那个更小的高度,把粘底锁往上顶 —— 就是"长会话最后会显示旧回复"那个 bug。

三处 shiki 隔离(`shiki-block.tsx` / `syntax-diff.tsx` / `markdown-text.tsx` 的
`useCodePlugin()`)都是同一个动机:多 MB 的 grammar+theme bundle 绝不能进入口 chunk。

### 4.5 右侧栏三块面板

**文件树**是"浏览这个会话的 cwd",没有 cwd 就只显示一行提示,而**不是**退回 Hermes 的启动目录
(`right-sidebar/index.tsx:38` 的 `const hasWorkspace = Boolean(currentCwd)`)。
`.gitignore` 过滤在 `files/ipc.ts` 做,带 git-root 与 ignore 两级缓存。

**review** 面板是纯 store 驱动(`@/store/review` 的 12+ 个 atom),本片只提供三块视图
(树/列表、diff、ship bar)与一份纯数据构建(`tree-data.ts`)。`churn-bar.tsx` 是**明确
未接线的死代码**,文件头自陈。

**终端**是这三块里唯一有"状态必须活下来"要求的:xterm 的 WebGL renderer 会观察自己的
DOM attachment,一挪 DOM 就会 detach 并清屏。所以宿主**不动**,而是挂在布局根、用
`position: fixed` 追着 slot 的 bounding rect 跑(`terminal/persistent.tsx:15` 的注释)。
`store.ts` 里的 `$terminalInjection` 是个小而有意思的接缝:

`apps/desktop/src/app/right-sidebar/store.ts:16 @ 863e313`

```
export const $terminalInjection = atom<null | string>(null)
```

它让"断开某个 CLI 托管的 provider"这类操作**在用户眼前跑一条真命令**,而不是 Hermes 偷偷删凭据。

---

## 5. 文档与代码的出入

### ◎-1 `WIDGET_SHELL_CLASS` 的消费者是 3 个,文档列了 2 个

`apps/desktop/DESIGN.md:200 @ 863e313`

> - **Inline widgets** — a tool result that renders as a panel the user reads or
>   acts on (clarify, artifact card) wears `WIDGET_SHELL_CLASS`

代码里第三个消费者是 `ChangedFilesCard`:

```verify
grep -rl "WIDGET_SHELL_CLASS" /home/user/hermes-agent/apps/desktop/src --include=*.tsx | sort
# /home/user/hermes-agent/apps/desktop/src/components/assistant-ui/artifact-card.tsx
# /home/user/hermes-agent/apps/desktop/src/components/assistant-ui/clarify-tool.tsx
# /home/user/hermes-agent/apps/desktop/src/components/assistant-ui/thread/changed-files-card.tsx
```

`apps/desktop/src/components/chat/widget-shell.ts:12` 的
`export const WIDGET_SHELL_CLASS = 'rounded-3xl bg-(--ui-widget-surface-background) px-3.5 py-3'`
自己的 docstring 也只举了同样两个例子。

**记 ◎ 不记 ▲**:文档那句字面为真(clarify 与 artifact card 确实都穿了这件外壳),
括号里是举例不是穷举,只是保守 —— 按记号约定,字面为真就不是 ▲。

### ◇-1 富嵌入子系统与其隐私闸门,全部文档零覆盖

28 个文件、9 个 provider、一套三档 + per-provider 的第三方请求同意机制,在作者自绘地图上
**不存在**:

```verify
grep -rniE "rich embed|embed consent|third[- ]party embed|EmbedFacade|allowProvider" \
  /home/user/hermes-agent/website/docs/ \
  /home/user/hermes-agent/apps/desktop/AGENTS.md \
  /home/user/hermes-agent/apps/desktop/DESIGN.md \
  /home/user/hermes-agent/apps/desktop/README.md \
  /home/user/hermes-agent/README.md /home/user/hermes-agent/AGENTS.md | wc -l
# → 0
```

**搜索面交代**:上述 6 个文档来源(`website/docs/**` 全树 + 5 个 markdown 根文件),
大小写不敏感,5 个模式("rich embed" / "embed consent" / "third-party embed" / 组件名
`EmbedFacade` / 函数名 `allowProvider")。排除了:代码注释、i18n 文案、测试。
`website/docs/user-guide/desktop.md` 通篇讲桌面功能,也没有一节提到内联嵌入。

这条 ◇ 的分量在于它是**用户可见的隐私行为**:默认 `ask` 意味着用户点一下才会向 YouTube /
X / Google Maps 发请求,而这条默认值只写在代码注释里。

### 未成立的 ▲(记一笔,防下一轮重做)

`website/docs/user-guide/desktop.md:105`(归 `### Terminal` 标题管)写
"A real terminal lives in the right sidebar, next to the file browser"。
乍看与 `controller.tsx:183` 的 `placement: 'bottom'` 矛盾,**但不成立**:`placement` 只是
contribution 的落位提示,真正的默认位置是 `DEFAULT_TREE`(`controller.tsx:339`),
它把 `grp-terminal` 放在 `spl-right` 这个右侧 column split 里,与 `[review, files]` 同列。
文档字面为真,不记 ▲ 也不记 ◎。

---

## 6. 缺陷

### ■-1 工具渲染分派表有 5 行永远命不中(其中 `edit_file` 还参与语义判定)

`TOOL_META` 的 23 个键里,**5 个在内核里没有任何同名工具**:
`browser_fill`、`browser_take_screenshot`、`edit_file`、`list_files`、`session_search_recall`。

```verify
python3 data/r10b/probes/probe_f_tool_names.py /home/user/hermes-agent
# UI-only (dead rows)   : 5 -> browser_fill, browser_take_screenshot, edit_file, list_files, session_search_recall
```

**为什么这个对账是有效的**:`tool.start` 事件带的就是注册表里的原始工具名
(`tui_gateway/server.py:5311` 的 `"name": name,`),没有任何改名层,所以 `TOOL_META` 的键
必须逐字等于注册名才可能命中。

**负结论的搜索面**(以 `edit_file` 为例,最干净的一个):

```verify
# 全基线 Python(含 tests)
grep -rn "edit_file" /home/user/hermes-agent --include=*.py | wc -l
# → 0
```

`edit_file` 在全仓只出现在桌面前端:`fallback-model/index.ts` 2 处、5 个 i18n 文件各 1 处、
`i18n/types.ts` 1 处、`tool/fallback.test.ts` 1 处 —— 共 9 处,**Python 侧 0 处**。
搜索面 = 基线全树的 `*.py`(0 命中)与 `*.py *.ts *.tsx *.md *.mdx`(排除 `node_modules`,9 命中)。
内核注册名的采集面 = `tools/**/*.py` 里的 `registry.register(name="…")`(含换行写法),82 个。
**这不覆盖运行期注册**:插件(`hermes_cli/plugins.py:452`)与 MCP 工具的名字来自清单/远端,
理论上一个插件可以叫 `edit_file`;但那是插件,不是内置工具,而 `TOOL_META` 显然是内置表的镜像
(其余 18 个键全部逐字命中内置注册名)。

**影响分级**:
- `browser_fill` / `browser_take_screenshot` / `list_files` / `session_search_recall` —— 纯死行:
  图标、色调与三段式 i18n 文案(5 种语言 × 3 句)都为不存在的工具维护着。
- `edit_file` **不只是死行**:它还在 `FILE_EDIT_TOOL_NAMES` 里,而这个集合驱动
  `isFileEditTool` → `isCardTool`(不折进摘要)、diff 面板、`deriveChangedFiles`。
  也就是说仓库里有一条"文件编辑工具"的语义路径,是为一个不存在的工具名铺的。

`session_search_recall` 尤其像**改名后忘了跟**:内核注册的是 `session_search`
(`registry.register(name="session_search"`),渲染层写的是 `session_search_recall`,
于是这个工具在 transcript 里既拿不到 🔍 图标,也拿不到本地化的
"Searched conversation history",只会显示 `titleForTool()` 拼出来的 "Session Search"。

### ■-2 成功但无 diff 的文件编辑,在 transcript 里可以完全没有痕迹

三道闸口用**同一个谓词**("有没有 diff"),而且互不兜底:

1. 行本身被隐藏 —— `apps/desktop/src/components/assistant-ui/tool/fallback.tsx:529` 的
   `if (isFileEdit && !isPending && view.status !== 'error' && !view.inlineDiff) {`
2. 它也进不了运行摘要 —— `isCardTool()` 把所有文件编辑排除在 run 之外
   (`fallback.tsx:754` 的 `export function isCardTool(toolName: string): boolean {`),
   所以没有"Edited 1 file"那一行来兜底。
3. 它也进不了 "N files changed" 卡:

`apps/desktop/src/components/assistant-ui/thread/changed-files.ts:44 @ 863e313`

```
    const result = parseMaybeObject(part.result)
    const diff = inlineDiffFromResult(result)

    if (!diff) {
      continue
```

**"没有 diff"比注释暗示的更常见。** 注释说"only `patch` persists its diff in the tool result",
这一点属实:`PatchResult.to_dict()`(`tools/file_operations.py:226` 的 `if self.diff:`)会写
`result["diff"]`,而 `WriteResult`(`tools/file_operations.py:178` 的 `class WriteResult:`)
**根本没有 diff 字段**。实时那一路靠的是事件旁路 —— 网关在 `tool.complete` 上现渲染一个
`inline_diff`(`tui_gateway/server.py:5363` 的 `payload["inline_diff"] = "\n".join(rendered)`),
渲染层把它记进按 tool_call_id 分键的 `$toolInlineDiff`。这条旁路有三种断法:

- **重载/重放**:`tool.complete` 不会重放,`$toolInlineDiff` 为空 → 所有 `write_file` 都无痕。
- **渲染抛异常**:`render_edit_diff_with_delta` 外面是裸的 `except Exception: pass`
  (`tui_gateway/server.py:5364-5365`)→ 静默无 `inline_diff`,实时也无痕。
- **`patch` 的空操作**:`no_change: true` 时不带 diff(`file_operations.py:222-227`
  按 `if self.diff:` 写字段)→ 无痕。

结果是"agent 说它改了文件,transcript 上什么都没有"。

**取证边界(如实说)**:以上是静态读接口面得出的 —— 三处谓词一致、`WriteResult` 无 diff 字段、
`inline_diff` 只在事件上。**没有实机复现**(需要真跑一次 agent + 桌面)。因此这条按
"三道闸口共用同一谓词、且该谓词有三条已知失效路径"记,不是"已复现的用户可见 bug"。

### ■-3 两个 provider 的主机判定是子串/前缀匹配,会误配无关域名

`apps/desktop/src/components/assistant-ui/embeds/providers/pinterest.ts:3 @ 863e313`

```
export const pinterest: EmbedMatcher = url => {
  // Pinterest runs many locale TLDs (pinterest.co.uk, fr.pinterest.com, ...).
  if (!bareHost(url.hostname).includes('pinterest.')) {
    return null
  }
```

`apps/desktop/src/components/assistant-ui/embeds/providers/maps.ts:6 @ 863e313`

```
function googleMapsEmbed(url: URL): FrameEmbed | null {
  const host = bareHost(url.hostname)

  if (host !== 'google.com' && host !== 'maps.google.com' && !host.startsWith('google.')) {
    return null
```

注释说明了意图(Pinterest 有很多地区 TLD;Google 也有 `google.co.uk`),但两个谓词都比意图宽:

```verify
node -e "console.log('notpinterest.com'.includes('pinterest.'), 'google.evil.com'.startsWith('google.'))"
# → true true
```

于是 `https://notpinterest.com/pin/12345` 会被判成 Pinterest 嵌入,
`https://google.evil.com/maps?q=x` 会被判成 Google Maps 嵌入。

**影响有限但不为零。** 不构成 SSRF:两者的 `embedUrl` 都是**写死的主机**
(`assets.pinterest.com` / `maps.google.com`),攻击者控制的只有 id/query 参数。
真正的后果是**观感冒充**:模型输出一个 `https://notpinterest.com/pin/1` 的裸链接,
transcript 里会长出一张真的 Pinterest 卡片。同意占位卡上显示的 `hostOf(descriptor)`
是原始主机(`embeds/embed-consent.tsx:51` 的 `return new URL(descriptor.sourceUrl).hostname.replace(/^www\./, '')`),
所以在 `ask` 模式下用户还能看见真实主机;但在 `always` 模式或该 provider 已被"永久允许"后,
占位卡不出现,只剩那张卡。

### ■-4(轻)三处死分支

- `social-embed.tsx` 的 `tiktok` 那条 `SCRIPT` 与 `markup()` 的 `case 'tiktok'` 不可达:
  `LazyRenderer` 只在 `renderer === 'tweet' || provider === 'instagram'` 时走 social,
  而 tiktok 的 descriptor 是 `renderer: 'frame'`(`embeds/providers/tiktok.ts:19` 的 `id: \`tiktok:${id}\`,`)。
- `instagram` descriptor 的 `embedUrl` 从不被读:走 social 那一路只用 `sourceUrl`。
- `apps/desktop/src/app/right-sidebar/review/churn-bar.tsx:9` 的
  `// changed file. Not wired in — drop \`<ChurnBar file={file} />\` into a review row`
  —— 作者自陈的未接线组件(59 行)。这条是**有意保留**,列出来只为让台账不把它当活代码。

---

## 7. 测试(行为规格)

在主线准备的基线副本上跑(**不装包**):

```verify
cd /home/user/r10b-ts/hermes-agent/apps/desktop && npx vitest run --project ui \
  src/components/assistant-ui src/components/chat src/app/right-sidebar
```

```console
 Test Files  53 passed (53)
      Tests  401 passed (401)
   Duration  216.02s
```

**passed 401 / failed 0 / skipped 0。**

**零执行核查**(判据要求逐个点名):

```verify
# 目录下的测试文件总数,应等于 vitest 报的 53
cd /home/user/r10b-ts/hermes-agent/apps/desktop && \
  find src/components/assistant-ui src/components/chat src/app/right-sidebar \
       -name '*.test.ts' -o -name '*.test.tsx' | wc -l
# → 53

# skip / todo 标记
grep -rnE "\.(skip|todo|skipIf|runIf)\(" src/components/assistant-ui src/components/chat \
    src/app/right-sidebar --include=*.test.ts --include=*.test.tsx
# → (无输出)
```

53 个文件全部被收集且全部执行,**没有整文件跳过、没有收集错误、没有 `describe.skip`**,
没有被掩盖的用例。唯一的噪音是 jsdom 打印 5 次
`Not implemented: HTMLCanvasElement's getContext()` —— 那是 `image-generation-placeholder.tsx`
的 ASCII 扩散画布在 jsdom 下取不到 2D context,组件自己有 fallback,不影响断言。

**当作行为规格读的几个**(和本片结论直接相关):

| 测试文件 | 钉住的行为 |
|---|---|
| `apps/desktop/src/components/assistant-ui/tool/fallback.test.ts:10` 的 `for (const toolName of ['clarify', 'image_generate', 'edit_file', 'patch', 'write_file']) {` | `isCardTool` 的 5 个成员(注意它把 `edit_file` 当成真工具 —— 见 ■-1) |
| `apps/desktop/src/components/assistant-ui/embeds/providers/detect.test.ts` | 9 个 provider 的 URL 识别矩阵(`it.each`) |
| `apps/desktop/src/components/assistant-ui/thread/list.test.ts` | `buildGroups` / `firstVisibleGroupIndex` / `liveTailStart` 三个纯函数的边界 |
| `apps/desktop/src/components/assistant-ui/tool/tool-group.test.tsx:583` 的 `setApprovalRequest({ command: 'rm -rf /tmp/x', description: 'dangerous command', sessionId: 'sess-1' })` | 有 pending 审批时 run 必须展开(链 A 的第 5 跳) |
| `apps/desktop/src/components/assistant-ui/thread/transcript-window.test.ts` | "显示更早"先花 DOM 预算再要 store 窗口 |

**环境记录**(照 CLAUDE.md 的要求):测试跑在 `/home/user/r10b-ts/hermes-agent`(主线用
`git archive` 导出的基线副本,**不是基线本身**),node_modules 由主线在开工时装好,本片
未安装任何包。vitest 4.1.10,project `ui`(jsdom)。

---

## 8. 判据自查

| # | 判据 | 自评 | 依据 |
|---|---|---|---|
| **1 点名到位** | 每个文件全路径 + 一句话角色 | **达标** | §0.1–§0.6 共 8+19+10+28+30+29 = **124** 条,每条都是仓库根可解析的全路径 |
| **2 接缝穷举** | 每个对外接缝逐项列全 + 机械枚举命令 | **达标(有一处声明式让步)** | §2.1–§2.11 共 11 张表,全部给了条数;5 条 ```verify 命令可重跑。**让步**:§2.2 的"未覆写槽位"来自 `@assistant-ui/core` 的 npm 类型,**不在基线仓库内**,已明写无锚点 |
| **3 端到端链** | ≥1 条,逐跳带锚点 | **达标(2 条)** | §3.1 审批链 5 跳(内核→事件→store→组件→RPC→内核),§3.2 `read_terminal` 反向链 3 跳 |
| **4 逐字取证** | ≥2 个围栏块是逐字源码 | **达标** | 全文 **21** 个源码围栏块,分布在 12 个文件;非源码块一律 ```text/```verify/```console 声明 |
| **5 记号** | ≥1 条带锚点 | **达标** | ◎×1、◇×1、■×4,外加一条"未成立的 ▲"备案 |

**未达标 / 已知不足,如实列出**:

- §2.6 的 `ToolView` 表把 22 个字段列全了,但**没有**把 `toolSubtitle()` 的 9 个分支、
  `toolDetailText()` 的 7 个分支、`toolCopyPayload()` 的 6 个分支逐条展开成表 —— 那是实现体,
  按 L2 定义不读;但它们确实构成"工具名 → 文案"的一张隐式表。**这一层只做到了"列全了入口与字段,
  没有列全每个工具的文案分支"**,约 7 成。
- `user-edit-composer.tsx`(852 行)、`use-terminal-session.ts`(1,059 行)、
  `diff-lines.tsx`(677 行)三个大文件只读了头部与导出面,**没有读接口面之外的任何实现**。
  它们各自的对外面(props / 导出)已列入 §2.1 的 366 条。
- `code-editor.tsx` / `json-document-editor.tsx` / `image-generation-placeholder.tsx` /
  `vibe-hearts.tsx` 四个与"消息渲染"关系较远的文件,只读了头部 30 行 + 导出面。

---

## 9. 移交项

| 编号 | 锚点 + 现象 | 建议 |
|---|---|---|
| H-R10B-F-a | `apps/desktop/src/components/assistant-ui/tool/fallback-model/index.ts:34`:`const FILE_EDIT_TOOL_NAMES = new Set(['edit_file', 'patch', 'write_file'])` —— `edit_file` 在内核 Python 里 0 命中,却参与 `isCardTool` / diff 面板 / changed-files 三条语义路径 | 若后续轮要写"工具生命周期"章,需交代这条 UI 侧的幽灵工具名;也可作为"前后端工具名没有单一真源"的证据 |
| H-R10B-F-b | `apps/desktop/src/components/assistant-ui/tool/fallback.tsx:529`:`if (isFileEdit && !isPending && view.status !== 'error' && !view.inlineDiff) {` —— 与 `changed-files.ts:47` 的 `if (!diff) {` 共用同一谓词,两者都不兜底 | 本片未实机复现。若后续有能跑通 agent 的轮次,值得实测一次 `write_file` 重载后的 transcript |
| H-R10B-F-c | `tui_gateway/server.py:5364`:`except Exception:` —— 包住 `render_edit_diff_with_delta`,失败即静默丢掉 `inline_diff` | 这是 ■-2 三条失效路径里唯一在 Python 侧的一条,属片 F 边界外,交给做 gateway 的片/轮 |
| H-R10B-F-d | `apps/desktop/src/components/assistant-ui/embeds/providers/pinterest.ts:5`:`if (!bareHost(url.hostname).includes('pinterest.')) {` —— 子串匹配,`notpinterest.com` 命中 | 若 R12 蓝图要写"不受信 URL 的处理",这是一个"白名单写成子串匹配"的现成反例 |
| H-R10B-F-e | `apps/desktop/src/components/assistant-ui/embeds/url-embed.tsx:31`:`if (descriptor.renderer === 'tweet' \|\| descriptor.provider === 'instagram') {` —— 分派不完全按 `renderer` 字段走,导致 instagram 的 `embedUrl` 与 tiktok 的 `SCRIPT` 条目成为死数据 | 纯整洁性问题,不阻断;记录以免下一轮把 `renderer` 字段当成完整分派依据 |
| H-R10B-F-f | `apps/desktop/src/components/assistant-ui/thread/message-parts.tsx:269`:`tools: { Fallback: ChainToolFallback }` —— 库支持 `tools.by_name`(工具名→组件 map),Hermes 只用 `Fallback` + 手写 if 链 | 设计取舍点,值得进 R12 蓝图的"分派表该不该是数据"一节 |

---

## 10. 本片成本自报

```text
片号            : F
层              : L2
文件数 / 行数   : 124 / 21,029
实际打开的文件数: 96          (真的读过内容的;另 28 个只读了导出面/头部 30 行)
实际读过的行数  : 约 11,500   (估法:全文读完的 62 个文件按实际行数求和 ≈ 8,100;
                              另 34 个只读头 30 行或关键段,按每个约 100 行计 ≈ 3,400)
底稿字节数      : (主线自测)
主观耗费        : 中偏高。瓶颈不是单文件长度,是**分派表分散在 6 个文件里**
                  (message-parts / fallback / fallback-model / run-summary /
                   approval / registry),要把"一个工具名会经过哪几张表"拼起来
                  必须跨文件追链;其次是判据 2 要求的"与内核对账"逼着离开本片
                  去读 tools/ 与 tui_gateway/,那部分占了约三成时间。
                  embeds/ 28 个文件虽多但每个都短且同构,反而最便宜。
```
