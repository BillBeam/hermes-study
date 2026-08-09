# r10-ui-tui 组件、库与构建脚本 —— 终端里那 24,682 行“前端”到底在解决什么

> 片名:**E · ui-tui 组件、库与构建脚本**。范围边界 = `data/r10/slices/E.txt`,97 个文件。
> 溯源约定:凡对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` 单独成行、置于代码块之前。
> 本轮是 **L2 结构级理解**:读接口面、生命周期与协作方式,不逐个读实现体。

---

## §1 这一片是什么

`ui-tui` 是 hermes 的**终端富交互客户端**:TypeScript 进程负责画屏与收键,
Python 侧(`tui_gateway/`)负责会话、工具、模型调用。两者之间是 stdio 上的
**行分隔 JSON-RPC**(每行一个 JSON 对象的远程过程调用协议)。

几个第一次出现的名词先锚定:

| 名词 | 一句话解释 |
|---|---|
| Ink | 把 React 组件树渲染成终端字符画的渲染器。本仓库用的是**分叉版** `@hermes/ink`(在 `ui-tui/packages/hermes-ink/`,属另一片)。 |
| nanostores | 极小的全局状态库。`$xxx` 命名的都是 store,组件用 `useStore($xxx)` 订阅。 |
| grapheme(字素簇) | 用户眼里的“一个字符”。JS 的 `str.length` 数的是 UTF-16 码元,`"é"`(e + 组合符)是 2,字素簇是 1。 |
| 显示宽度(display width) | 一个字符在终端占几列。CJK 汉字、全角标点占 **2 列**,零宽连接符占 0 列。`stringWidth()` 算的是这个。 |
| ANSI 转义序列 | 以 `ESC[`(`\x1b[`)开头的控制串,用来改颜色、移光标、开关鼠标上报等。终端里“画界面”就是往 stdout 写这些。 |
| SGR | ANSI 里管字符外观的那一族(`\x1b[1m` 粗体、`\x1b[7m` 反显、`\x1b[38;2;r;g;bm` 24 位真彩前景色)。 |
| OSC | ANSI 里管“跟终端本体对话”的那一族(OSC 52 = 读写系统剪贴板;OSC 10/11 = 设置终端默认前景/背景色)。 |
| 软换行(soft wrap) | 文本超出终端宽度时终端自己折到下一行,字符串里并没有 `\n`。光标定位的所有麻烦都从这里来。 |
| IME / 组合键 | 输入法。打中文/越南文时,终端会先送来若干**中间态字节**,最后才送来定稿字符。 |

这一片是它的**组件层 + 工具库 + 构建/基准脚本**,不含入口(`entry.tsx`)、
顶层编排(`app.tsx`、`src/app/`)、协议客户端(`gatewayClient.ts`)与分叉渲染器
(`packages/hermes-ink/`)——那些在别的片。因此本片的定位是:

- `src/components/`(36 文件,**15,317** 行):**所有屏幕内容的产出方**。全屏 overlay、
  状态栏、输入框、Markdown 渲染、思考/工具活动树、组件级原语(手风琴、滚动条、菜单行)。
- `src/lib/`(45 文件,**7,152** 行):**无 React 或轻 React 的纯工具层**。终端能力探测、
  颜色数学、宽度/换行度量、剪贴板、滚轮加速、V8 堆快照、LaTeX→Unicode……
  组件层的“物理学”都在这里,大部分是纯函数,所以也是这一片里被单测覆盖最多的部分。
- `scripts/`(9 文件,**1,622** 行):**一个生产构建脚本 + 四类开发期行为规格**
  (虚拟滚动基准、流式 Markdown 策略基准、账单 overlay 视觉夹具、主题×背景视觉回归)。
- 根配置 + README(7 文件,**590** 行):`package.json` / 两个 tsconfig / eslint /
  vitest / `.gitignore` / `README.md`(492 行,§6 的 ▲◇ 全部出自它)。

四组相加 15,317 + 7,152 + 1,622 + 590 = **24,681**,与 `wc -l` 全片合计一致。

行数口径:`wc -l` 得 **24,681**,台账口径 **24,682**,差 1 行来自
`ui-tui/.gitignore` **没有结尾换行**(`scripts/inventory.py` 的规则是
“`\n` 个数 + 非空且不以 `\n` 结尾则 +1”)。已逐文件核对,只有这一个文件如此。

```verify
# 行数、分组行数、以及“唯一无结尾换行的文件”复核
cd /home/user/hermes-agent
wc -l $(cat /home/user/hermes-study/data/r10/slices/E.txt | tr '\n' ' ') | tail -1   # 24681 total
for f in $(cat /home/user/hermes-study/data/r10/slices/E.txt); do
  [ -n "$(tail -c 1 "$f")" ] && echo "NO-TRAILING-NEWLINE: $f"
done
cd /home/user/hermes-agent/ui-tui
cat src/components/*.tsx | wc -l                                                     # 15317
ls src/lib/*.ts src/lib/*.tsx | grep -v '\.test\.' | xargs cat | wc -l               # 7152
find scripts -type f | xargs cat | wc -l                                             # 1622
for f in package.json tsconfig.json tsconfig.build.json eslint.config.mjs \
         vitest.config.ts .gitignore README.md; do wc -l < "$f"; done | paste -sd+ | bc  # 590
```

---

## §2 文件清单(97 个,逐个全路径 + 一句话角色)

### §2.1 根配置 + README(7)

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/package.json | 45 | 包名 `hermes-tui`、13 个 npm 脚本、8 个运行时依赖(含两个 `file:` 本地依赖 `@hermes/ink`、`@hermes/shared`)、7 个 devDependencies、1 条 `overrides`(把 `ink-text-input` 的 `ink` 重定向到分叉版)。 |
| ui-tui/tsconfig.json | 20 | 类型检查配置:ES2023 / nodenext / `jsx: react-jsx` / `strict: true`;`exclude` 掉 `src/__tests__`。 |
| ui-tui/tsconfig.build.json | 8 | 继承上者,只加一条 `paths`,把 `@hermes/ink` 指向手写声明 `src/types/hermes-ink.d.ts`——**构建期不必先编译分叉渲染器**。 |
| ui-tui/eslint.config.mjs | 15 | 继承仓库根 `eslint.config.shared.mjs`,并对 `packages/hermes-ink/**` 关掉 5 条规则(那是外来分叉代码,不按本仓风格改)。 |
| ui-tui/vitest.config.ts | 7 | 唯一内容是 `exclude: ['dist/**','node_modules/**']`——测试文件靠 vitest 默认约定发现,不显式列目录。 |
| ui-tui/.gitignore | 3(台账 4) | 忽略 `dist/`、`node_modules/`、`src/*.js`、`docs/`。`src/*.js` 说明历史上有过就地编译产物。 |
| ui-tui/README.md | 492 | 作者自绘地图:运行方式、App 模型、热键表、事件表、命令表、File map。§6 的 ▲/◇ 全部出自它。 |

（`README.md` 计入本组,故本组 7 个文件、590 行。)

### §2.2 `src/components/`(36)

**A. 顶层骨架与状态栏(4)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/components/appLayout.tsx | 591 | 顶层 Ink 树的组装者:`Static` 抄本区 + 虚拟历史 + 流式行 + 状态栏 + overlay 层;另含 `PetPane`(右下角宠物浮层,**不占布局行**,只发布自己的占位供抄本避让)。文件开头 `import '../sdk/apps/index.js'` 就是为了在启动时注册参考 widget app。 |
| ui-tui/src/components/appChrome.tsx | 890 | 状态栏(`StatusRule`)、状态栏分段宽度计算(`statusBarSegments`/`statusRuleWidths`)、忙碌指示器宽度、`FloatBox`(浮层边框盒)、`StickyPromptTracker`(把当前用户提问钉在顶部)、`TranscriptScrollbar`。 |
| ui-tui/src/components/appOverlays.tsx | 384 | overlay **路由**:`PromptZone`(审批/追问/密码等阻塞式提示的宿主)与 `FloatingOverlays`(把 modelPicker / petPicker / skillsHub / pluginsHub / 补全列表等塞进一个 WidgetGrid)。 |
| ui-tui/src/components/branding.tsx | 562 | 开屏:`Banner`(响应式 ASCII logo,宽度不足时逐级降级为紧凑横线→纯文字→隐藏)、`SessionPanel`(模型/工具/技能/MCP 摘要)、`Panel`、`ArtLines`。 |

**B. 抄本与流式渲染(5)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/components/messageLine.tsx | 311 | 一条抄本行。含 ANSI 直出 vs Markdown 渲染的分流、长系统消息折叠、`/details` 分区可见性、块间空行(lead gap)规则。 |
| ui-tui/src/components/markdown.tsx | 1178 | Markdown→Ink 渲染器。除 README 提到的标题/列表/引用/表格/围栏/diff/行内码/强调/链接外,还做 **LaTeX 行内与块级数学**(经 `mathUnicode`)、脚注、定义列表、任务列表、setext 标题、`MEDIA:` 与 `[[audio_as_voice]]` 指令行、语法高亮;含一个 **Theme-keyed WeakMap + 512 条 LRU** 的解析缓存。 |
| ui-tui/src/components/streamingMarkdown.tsx | 166 | 流式增量 Markdown:前向扫描器把已到达的完整行折进围栏/数学状态,`\n\n` 处冻结“已定稿块”,每块只被 tokenize 一次。§5.3 详述。 |
| ui-tui/src/components/streamingAssistant.tsx | 118 | 正在流出的那一行助手输出 + `LiveTodoPanel`。 |
| ui-tui/src/components/thinking.tsx | 1237 | 思考/推理 + 工具调用 + 子代理生成树 + 活动流的**统一折叠树**。§5.2 详述。 |

**C. 输入与提示流(3)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/components/textInput.tsx | 1555 | 自研行编辑器。§5.1 详述。 |
| ui-tui/src/components/prompts.tsx | 312 | 三种阻塞式提示:`ApprovalPrompt`(审批,含纯函数 `approvalAction`)、`ClarifyPrompt`(选项 + “Other” 自由文本)、`ConfirmPrompt`。 |
| ui-tui/src/components/maskedPrompt.tsx | 41 | sudo / secret 的掩码输入,`mask="*"` 传给 `TextInput`。 |

**D. 全屏 / 浮动 overlay(10)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/components/activeSessionSwitcher.tsx | 917 | `/sessions` 会话切换器。行序固定为 `[+ new][live…][history…]`;含大量可单测的纯函数(行类型判定、相对时间、关闭后回落策略、草稿标题生成)。 |
| ui-tui/src/components/agentsOverlay.tsx | 976 | `/agents` 子代理审计 overlay:实时生成树、spawn 历史(最近 10 次)、两次 fan-out 的 diff、暂停/中断。 |
| ui-tui/src/components/modelPicker.tsx | 710 | `/model` 选择器。两级(provider→model),模糊排序用 `lib/fuzzy` + `lib/model-search-text`;可存 key、可断开 provider。 |
| ui-tui/src/components/billingOverlay.tsx | 950 | `/billing`(即 topup)状态机:overview → buy \| autoreload \| limit,buy → confirm → stepup。RPC 全在 `overlay.ctx` 里,本组件只渲染 + 路由按键。 |
| ui-tui/src/components/subscriptionOverlay.tsx | 1024 | `/subscription` 订阅状态机:overview → picker → confirm → result,必要时插入 stepup;团队 org 直接死路指向 /topup。 |
| ui-tui/src/components/journey.tsx | 595 | “Journey / 学习星图” overlay,渲染 Python 侧 `learning_graph_render.py` 产的 run 序列,配色来自 `lib/starmapPalette`。 |
| ui-tui/src/components/skillsHub.tsx | 301 | `/skills`:三段式(category→skill→actions),`x` 安装、`i` 查看。 |
| ui-tui/src/components/pluginsHub.tsx | 241 | `/plugins`:列表 + 启停,走 `plugins.manage`。 |
| ui-tui/src/components/petPicker.tsx | 187 | `/pet list` 宠物图鉴选择器。§4 端到端链的主角。 |
| ui-tui/src/components/gridTestOverlay.tsx | 318 | 栅格布局自测 overlay(由 `src/sdk/apps/gridTestState.ts` 驱动),用来眼验 `lib/widgetGrid` 的轨道求解。 |

**E. overlay 原语与共享控件(5)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/components/overlay.tsx | 133 | `Overlay`(9 个锚位 zone + 可选 lipgloss 式假 scrim)与 `Dialog`。 |
| ui-tui/src/components/overlayPrimitives.tsx | 247 | overlay 通用件:宽度收敛 `clampOverlayWidth`、菜单键盘 `useMenu`、`MenuRow`/`ActionRow`、行高亮样式、`UsageBars`(用量条)、`barCells`、滚动条配色。 |
| ui-tui/src/components/overlayControls.tsx | 50 | `useOverlayKeys`(`q` 关闭、Esc 返回或关闭)、`OverlayHint`(底部提示行)、列表开窗 `windowOffset`/`windowItems`。**没有任何“按钮”组件**(见 ▲5)。 |
| ui-tui/src/components/overlayScrollbar.tsx | 84 | 绑定 `ScrollBox` ref 的鼠标可拖拽滚动条,靠父级 `tick` 重算滑块高度。 |
| ui-tui/src/components/accordion.tsx | 58 | 展开/折叠原语,受控与非受控双模式;点击标题即可切换(**环境 widget 收不到键盘,只有鼠标**)。 |

**F. 栅格与 widget(2)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/components/widgetGrid.tsx | 267 | `WidgetGrid`(行列自动放置 + `colStart`/`colSpan` + `gap`,单元格 `overflow:hidden` 防串格)与 `GridAreas`(命名区域版)。布局数学在 `lib/widgetGrid.ts`。 |
| ui-tui/src/components/gridStreamsDemo.tsx | 364 | 六个各自独立打点的面板 demo,其中一个占 2×2 提升槽;用来演示 `layoutGridAreas` 与 `lib/charts` 的 sparkline。 |

**G. 小件与装饰(7)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/components/todoPanel.tsx | 93 | todo 列表面板,字形/色调来自 `lib/todo`。 |
| ui-tui/src/components/queuedMessages.tsx | 64 | 排队消息预览,固定 3 行窗口(`QUEUE_WINDOW`),编辑第 N 条时窗口跟随。 |
| ui-tui/src/components/helpHint.tsx | 68 | 空输入时的上下文帮助:6 条常用命令 + 平台相关热键串(`content/hotkeys.ts`)。 |
| ui-tui/src/components/loaders.tsx | 172 | 骨架屏:高亮带扫过块状串的 shimmer;**一次合成只用一个 interval**(父级打点、行是纯的),颜色由调用方给主题色。 |
| ui-tui/src/components/petSprite.tsx | 93 | 用半块字符 `▀`/`▄` 把一格当两个像素画宠物精灵(数据来自 `pet.cells` RPC),外加纯字符兜底 `PetKitty`。 |
| ui-tui/src/components/themed.tsx | 30 | `Fg`:从 `$uiState` 取主题、按语义色名(`ThemeColor`)着色的 `Text` 包装。 |
| ui-tui/src/components/fpsOverlay.tsx | 30 | `HERMES_TUI_FPS=1` 时右上角的 FPS 计数,≥50 绿 / ≥30 黄 / 否则红;关闭时零成本。 |

### §2.3 `src/lib/`(45)

**A. 终端能力与模式(9)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/lib/terminalModes.ts | 103 | 退出时的“把终端还回去”:20 条 ANSI 复位串常量 `TERMINAL_MODE_RESET`(鼠标 6 种协议、焦点事件、bracketed paste、备用屏、kitty 键盘、modifyOtherKeys、光标可见),外加 OSC 10/11 默认前景/背景的**只还我涂过的**语义。 |
| ui-tui/src/lib/forceTruecolor.ts | 60 | 在 chalk / supports-color 被 import **之前**决定是否强制 24 位色;显式不从 `TERM_PROGRAM=Apple_Terminal` 推断真彩(Tahoe 26 之前的 Terminal.app 不支持 RGB SGR)。 |
| ui-tui/src/lib/terminalSetup.ts | 444 | 往 VSCode/Cursor/Windsurf 的 `keybindings.json` 装 hermes 键位(含 JSONC 去注释、配置目录定位、远程会话识别)。 |
| ui-tui/src/lib/terminalParity.ts | 78 | macOS 终端“行为对齐”提示:检测出宿主后给一句具体建议。 |
| ui-tui/src/lib/termux.ts | 31 | Termux(Android 上的终端环境)检测:`TERMUX_VERSION` 或 `PREFIX` 含 termux 前缀。 |
| ui-tui/src/lib/platform.ts | 414 | 平台键位归一:macOS 的“动作修饰键”是 Cmd(kitty CSI-u 报 `super`,老终端报 `meta`,还有把 Cmd+Left 直接改写成 Ctrl+A 的),非 mac 是 Ctrl;另含 SSH 检测、复制快捷键判定、语音录制热键的解析/格式化/匹配。 |
| ui-tui/src/lib/osc52.ts | 76 | OSC 52 剪贴板:构造查询串、解析回包、带超时的读、写。**这是唯一能穿过 SSH 的剪贴板通道**。 |
| ui-tui/src/lib/clipboard.ts | 188 | 本机剪贴板:macOS `pbcopy`/`pbpaste`、WSL `powershell.exe`、Wayland `wl-copy`/`wl-paste`、X11 `xclip`/`xsel`,按平台依次尝试。 |
| ui-tui/src/lib/themeBoot.ts | 209 | **免闪主题启动**:主题解析天然异步(skin 随连接到、OSC-11 背景探测在首帧后才回、config 里的模式钉在 config sync 时才到),所以把上次解析结果落盘、下次当第一帧回放。 |

**B. 度量与排版(6)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/lib/inputMetrics.ts | 203 | 光标行列 ↔ 字符串偏移的双向映射。核心是 `visualLines` **直接用 wrap-ansi 的输出反推每一视觉行的源区间**,以保证与 Ink `<Text wrap="wrap">` 的折行点逐格一致。§5.1 详述。 |
| ui-tui/src/lib/text.ts | 377 | 文本杂役中枢:`stripAnsi`/`hasAnsi`/`sanitizeAnsiForRender`、预览截断、粗略 token 估算、思考文本清洗与限长、工具轨迹行的构造/解析/分组、行数估算 `estimateRows`。 |
| ui-tui/src/lib/emoji.ts | 55 | 给“默认按文字呈现”的 emoji 补 VS16 变体选择符,让 `☀`、`❤` 之类真按 emoji(**占 2 列**)渲染而不是 1 列文字。 |
| ui-tui/src/lib/mathUnicode.ts | 783 | 尽力而为的 LaTeX→Unicode:希腊字母、黑板体/哥特体/花体大写、集合与逻辑符、箭头、上下标、`\frac{a}{b}`→`a/b`;`\boxed{}` 用 U+0001/U+0002 哨兵标出,由 markdown.tsx 渲染成反显。纯正则管线,不认识的原样保留。 |
| ui-tui/src/lib/virtualHeights.ts | 160 | 虚拟列表的行高估算 + 稳定 key(文本 djb2 哈希),Termux 模式下用不同的横向预留。 |
| ui-tui/src/lib/syntax.ts | 117 | 极小语法高亮:按语言给关键字集合与行注释符,输出 `[文本, 颜色]` token 对。 |

**C. 滚动与视口(5)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/lib/wheelAccel.ts | 190 | 滚轮加速状态机。原生终端(Ghostty/iTerm2)与 xterm.js 宿主(VSCode/Cursor)两条不同节奏的路径;识别机械滚轮的**编码器抖动**(方向翻转又翻回 ≤200ms)与触控板**快扫**(连续 5 个 <5ms 事件)。 |
| ui-tui/src/lib/precisionWheel.ts | 48 | 高精度滚轮的“黏帧预算”:16ms 帧、80ms 黏滞,避免一次物理滚动被拆成多帧抖动。 |
| ui-tui/src/lib/viewportStore.ts | 124 | 用 `useSyncExternalStore` 把 `ScrollBoxHandle` 的视口/滚动条快照变成 React 可订阅状态,并给出比较用的 key 函数。 |
| ui-tui/src/lib/resizeCoalescer.ts | 56 | 终端 resize 抖动的“前沿 + 后沿”节流(拖窗口时一秒几十次 resize)。 |
| ui-tui/src/lib/fpsStore.ts | 51 | 由 Ink `onFrame` 喂的 FPS store;`HERMES_TUI_FPS` 未设时 `trackFrame` 为 `undefined`,回调在可选链处短路 → 零成本。 |

**D. 颜色(3)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/lib/color.ts | 325 | **唯一的颜色原语**:解析(hex6/hex3/`rgb()`)、sRGB 线性混合(为了和桌面端 `color-mix(in srgb,…)` 逐字节一致)、相对亮度、对比度、`ensureContrast`/`liftForContrast`、HSL 往返、`retone`/`boostSaturation`、链式 `color()`。 |
| ui-tui/src/lib/starmapPalette.ts | 147 | 从桌面端 `starmap/color.ts` 移植的星图配色:主色的补色作“记忆墨”,年龄用 alpha 混背景做淡出。 |
| ui-tui/src/lib/charts.ts | 80 | 纯字符串图元:`sparkline`(8 级块字符)、`sparkRows`(多行)、`gauge`、`hbars`,全部自动按序列 min/max 缩放。 |

**E. 进程与系统集成(7)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/lib/editor.ts | 70 | `$VISUAL`/`$EDITOR` 未设时的回落链(对齐 prompt_toolkit 的 `Buffer.open_in_editor()`),`openInEditor` 期间用 `withInkSuspended` 让出终端。 |
| ui-tui/src/lib/externalCli.ts | 16 | 起一个 `hermes <args>` 子进程(`HERMES_BIN` 可覆盖),返回退出码。 |
| ui-tui/src/lib/openExternalUrl.ts | 158 | 按平台打开 URL:darwin→`open`、win32→`explorer.exe`、Linux/BSD 家族→`xdg-open`,其余返回 `null` 让“找不到命令”的兜底诚实地触发。 |
| ui-tui/src/lib/externalLink.ts | 440 | 链接标题解析:URL 归一、host/path 标签、slug 猜标题、可抓取性判定、带 500 条上限缓存 + inflight 去重的 `fetchLinkTitle`、React 侧 `useLinkTitle`。 |
| ui-tui/src/lib/gracefulExit.ts | 67 | 信号与未捕获异常的收尾:跑 cleanups,并用 failsafe 超时兜住卡住的 cleanup。 |
| ui-tui/src/lib/parentLog.ts | 59 | Node 父进程往 `~/.hermes/tui-parent.log` 追加生命周期面包屑,**为了和 Python 侧 panic log 按时间戳交错读**。 |
| ui-tui/src/lib/history.ts | 82 | 输入历史落盘(`$HERMES_HOME` 或 `~/.hermes/.hermes_history`),上限 1000 行,进程内缓存。 |

**F. 内存与性能诊断(3)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/lib/memory.ts | 246 | V8 堆快照落盘(带目录轮转与大小上限)、堆空间统计、`formatBytes`。 |
| ui-tui/src/lib/memoryMonitor.ts | 188 | 周期采样 heapUsed/rss,分 normal/high/critical 三档,越档自动触发堆转储(带冷却)。 |
| ui-tui/src/lib/perfPane.tsx | 107 | `HERMES_DEV_PERF=1` 时:`PerfPane` 用 React.Profiler 记每个面板的 commit 时长,`logFrameEvent` 记 Ink 每帧的 yoga/renderer/diff/optimize/write 各阶段;**输出是 JSON-lines 日志文件,不在屏幕上画任何东西**(见 ▲5)。 |

**G. 领域小工具(12)**

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/src/lib/subagentTree.ts | 351 | 把扁平的子代理事件流重建成生成树(按 `parentId` 分组,`depth`→`index` 排序),并聚合工具数/token/费用/热度;含 `sparkline`、`fmtCost`/`fmtTokens`/`fmtDuration`、`hotnessBucket`/`peakHotness`。 |
| ui-tui/src/lib/liveProgress.ts | 79 | “工具货架”消息的合并规则:相邻的纯工具行合成一条抄本行;todo 完成判定。 |
| ui-tui/src/lib/messages.ts | 17 | 抄本追加(委托给 `liveProgress`)、按 `MAX_HISTORY` 截断、按角色 upsert。 |
| ui-tui/src/lib/reasoning.ts | 55 | 从文本里切出被 `<think>`/`<reasoning>`/`<REASONING_SCRATCHPAD>` 等 5 种标签包住的推理段。 |
| ui-tui/src/lib/todo.ts | 9 | todo 状态 → 定宽 ASCII 字形(`[x]`/`[>]`/`[ ]`/`[-]`,**故意不用 emoji,否则会占 2 列把行推歪**)与色调。 |
| ui-tui/src/lib/fuzzy.ts | 177 | 轻量模糊子序列打分(`g4o` 命中 `gpt-4o`),按完全匹配>前缀>词边界>连续>靠前排序,返回命中下标供高亮。 |
| ui-tui/src/lib/model-search-text.ts | 30 | 只用于模型选择器排序的额外检索 token(某些 provider 的旗舰 id 就叫 `k3`,用户仍按 `kimi-` 搜);声明要与 `web/src/lib/model-search-text.ts`、`hermes_cli/model_search.py` 同步。 |
| ui-tui/src/lib/rpc.ts | 52 | JSON-RPC 结果的类型守卫(`asRpcResult`/`asCommandDispatch`)与错误消息提取 `rpcErrorMessage`。 |
| ui-tui/src/lib/prompt.ts | 36 | 组合器提示符文本(shell 模式、profile 名、Termux 下换成安全的 `>`)。 |
| ui-tui/src/lib/billingDialog.ts | 36 | 从 `@hermes/shared/billing` 的 `BillingBlock` 生成对话框四段文案(标题/详情/确认/取消)。 |
| ui-tui/src/lib/circularBuffer.ts | 48 | 定容泛型环形缓冲(容量非正整数直接抛 `RangeError`)。 |
| ui-tui/src/lib/widgetGrid.ts | 510 | 栅格布局求解器:`layoutWidgetGrid`(自动列数/显式列数/轨道列表 + 跨列放置)、`resolveGridTracks`(固定轨道取定值,`fr` 轨道按权重分余,跌破 `min` 就钉住重解,最后从尾部削溢出)、`layoutGridAreas`(命名区域)。 |

### §2.4 `scripts/`(9)

| 全路径 | 行 | 角色 |
|---|---|---|
| ui-tui/scripts/build.mjs | 66 | **唯一在生产路径上的脚本**:esbuild 把 `src/entry.tsx` 打成自包含的 `dist/entry.js`。 |
| ui-tui/scripts/bench-history-scroll.tsx | 483 | 虚拟历史滚动的确定性基准 + 不变量检查。 |
| ui-tui/scripts/bench-streaming-md.tsx | 302 | 三种流式 Markdown 策略的对照基准(naive / monolithic / per-block)。 |
| ui-tui/scripts/billing-fixtures.tsx | 244 | 16 个账单/订阅 overlay 状态夹具,直接挂真组件供 tmux 截图评审。 |
| ui-tui/scripts/profile-tui.mjs | 121 | 用 V8 inspector 给整棵 `AppLayout` 做 CPU profile + 内存三点采样。 |
| ui-tui/scripts/visual/run.mjs | 47 | `npm run visual` 的零依赖启动器:先 tsx 跑 render.tsx,再借桌面工作区的 electron 跑 shot.mjs。 |
| ui-tui/scripts/visual/render.tsx | 319 | 把真 TUI 表面按 4 个「主题×背景」场景渲成 ANSI,再手写 ANSI→HTML 转换写出 `tui-visual.html`。 |
| ui-tui/scripts/visual/shot.mjs | 29 | 用 Electron 离屏窗口(1500×2100)把那个 HTML 截成 `tui-visual.png`。 |
| ui-tui/scripts/visual/paths.mjs | 11 | 两者共用的输出目录:`HERMES_TUI_VISUAL_DIR` 或 `os.tmpdir()/hermes-tui-visual`(**不写死 `/tmp`,否则原生 Windows 会解析成 `C:\tmp`**)。 |

97 = 7(根配置含 README)+ 36(components)+ 45(lib)+ 9(scripts)。

```verify
# 片内文件数与分目录条数复核
wc -l < /home/user/hermes-study/data/r10/slices/E.txt          # 97
cd /home/user/hermes-agent/ui-tui
ls src/components/*.tsx | wc -l                                 # 36
ls src/lib/*.ts src/lib/*.tsx | grep -v '\.test\.' | wc -l      # 45
find scripts -type f | wc -l                                    # 9
```

---

## §3 接缝穷举

### S1 本片直接发起的 gateway RPC 方法(**17 个方法 / 20 处调用**,逐项列全)

这是本片唯一的**对外协议接缝**:组件层不自己开进程、不自己读文件,凡要越过 TS 边界
拿数据,都走 `gw.request(method, params)`。

锚点一律写成「锚点 + 紧跟的反引号摘录」的声明式,以便被 `verify_citations.py` 机械校验。

| # | 方法 | 调用点(全部) |
|---|---|---|
| 1 | 读 | `ui-tui/src/components/agentsOverlay.tsx:684`:`'delegation.status'` |
| 2 | 写 | `ui-tui/src/components/agentsOverlay.tsx:726`:`'delegation.pause'` |
| 3 | 写 | `ui-tui/src/components/agentsOverlay.tsx:705`:`'subagent.interrupt'` |
| 4 | 读 | `ui-tui/src/components/journey.tsx:163`:`'learning.frames'` |
| 5 | 写 | `ui-tui/src/components/journey.tsx:193`:`'learning.delete'` |
| 6 | 读 | `ui-tui/src/components/journey.tsx:219`:`'learning.detail'` |
| 7 | 写 | `ui-tui/src/components/journey.tsx:231`:`'learning.edit'` |
| 8 | 读 | `ui-tui/src/components/modelPicker.tsx:69`:`'model.options'` |
| 9 | 写 | `ui-tui/src/components/modelPicker.tsx:212`:`'model.save_key'` |
| 10 | 写 | `ui-tui/src/components/modelPicker.tsx:272`:`'model.disconnect'` |
| 11 | 读 | `ui-tui/src/components/petPicker.tsx:48`:`'pet.gallery'` |
| 12 | 写 | `ui-tui/src/components/petPicker.tsx:78`:`'pet.select'` |
| 13 | 读+写 | `ui-tui/src/components/pluginsHub.tsx:59`:`'plugins.manage'`(另一处 `:93`) |
| 14 | 读+写 | `ui-tui/src/components/skillsHub.tsx:33`:`'skills.manage'`(另两处 `:74`、`:83`) |
| 15 | 读 | `ui-tui/src/components/activeSessionSwitcher.tsx:354`:`'session.active_list'` |
| 16 | 读 | `ui-tui/src/components/activeSessionSwitcher.tsx:357`:`'session.list'` |
| 17 | 写 | `ui-tui/src/components/activeSessionSwitcher.tsx:512`:`'session.delete'` |

第二列的“读/写”是我按方法语义标注的,不是代码里的字段。

```verify
# 方法名与调用点(在 /home/user/hermes-agent/ui-tui 下跑)
grep -rnoE "gw\.request(<.*>)?\('[a-z_.]+'" src/components src/lib \
    --include=*.ts --include=*.tsx | sed -E "s/gw\.request(<.*>)?\('/ /; s/'$//" | sort -k2
# 20 处调用 / 17 个方法
grep -rcE "gw\.request" src/components src/lib --include=*.ts --include=*.tsx | awk -F: '{s+=$2} END{print "sites="s}'
grep -rhoE "gw\.request(<.*>)?\('[a-z_.]+'" src/components src/lib --include=*.ts --include=*.tsx \
  | grep -oE "'[a-z_.]+'$" | sort -u | wc -l
# 反向确认没有别的调用形状(应只剩 ctx.requestRemoteSpending 两处,那是 overlay.ctx 的本地回调)
grep -rn "\.request\|\.notify" src/components src/lib --include=*.ts --include=*.tsx \
  | grep -v "gw\.request"
```

**负结论及其搜索面**:本片(`src/components/` + `src/lib/`,含 `.ts` 与 `.tsx`)内
**没有第三种协议出口**——既没有 `gw.notify(...)`(`grep -rn "\.notify"` 零命中),
也没有把方法名放进变量再传的间接调用(`grep -rn "\.request"` 共 22 处,
20 处形如 `gw.request('字面量'`,余下 2 处是 `ctx.requestRemoteSpending()`
即 `overlay.ctx` 注入的本地回调,不是 RPC)。未排除的情形是:**由父级通过 props
传进来的回调**(如 `onModelSelect`、`onResumeSelect`、`onActiveSessionClose`)
最终可能在 `src/app/` 里发 RPC —— 那部分不在本片,本表只声明“本片自己发的”。

### S2 `ui-tui/package.json` 的 npm 脚本(**13 条**,逐项列全)

| # | 脚本 | 命令 |
|---|---|---|
| 1 | `dev` | `npm run build:ink && tsx --watch src/entry.tsx` |
| 2 | `start` | `tsx src/entry.tsx` |
| 3 | `build` | `node scripts/build.mjs` |
| 4 | `build:ink` | `npm run build --prefix packages/hermes-ink` |
| 5 | `visual` | `node scripts/visual/run.mjs` |
| 6 | `typecheck` | `tsc --noEmit -p tsconfig.json` |
| 7 | `lint` | `eslint src/ packages/` |
| 8 | `lint:fix` | `eslint src/ packages/ --fix` |
| 9 | `fmt` | `prettier --write 'src/**/*.{ts,tsx}' 'packages/**/*.{ts,tsx}'` |
| 10 | `fix` | `npm run lint:fix && npm run fmt` |
| 11 | `check` | `npm run build:ink && npm run typecheck && npm run test && npm run lint` |
| 12 | `test` | `vitest run` |
| 13 | `test:watch` | `vitest` |

只有 **2 条**指向本片的 `scripts/`(`build`、`visual`);`bench-history-scroll.tsx`、
`bench-streaming-md.tsx`、`billing-fixtures.tsx`、`profile-tui.mjs` **没有任何 npm 入口**,
只在各自文件头的注释里写了 `npx tsx …` 用法。

```verify
cd /home/user/hermes-agent/ui-tui
node -e 'const s=require("./package.json").scripts;console.log(Object.keys(s).length);for(const[k,v]of Object.entries(s))console.log(k,"=",v)'
grep -n "scripts/" package.json      # 只有 build 与 visual 两行
```

**负结论及其搜索面**:全仓(排除 `node_modules/` 与 `ui-tui/scripts/` 自身)
grep 三个基名 `bench-history-scroll` / `bench-streaming-md` / `billing-fixtures`
**零命中**,`profile-tui` 只命中仓库根的 `scripts/profile-tui.py`——那是**另一个同名工具**
(Python 写的按键驱动 profiler,注释里还要求先 `npm run build`),不是本片这个
`ui-tui/scripts/profile-tui.mjs` 的调用方。未排除:CI 配置若用完整路径以外的方式引用
(如 shell 变量拼接)则搜不到。

### S3 `ui-tui/package.json` 依赖(**8 + 7 + 1**,逐项列全)

运行时(8):`@hermes/ink`(`file:./packages/hermes-ink`)、`@hermes/shared`(`file:../apps/shared`)、
`@nanostores/react@1.1.0`、`ink-text-input@6.0.0`、`nanostores@1.4.0`、`react@19.2.7`、
`undici@6.27.0`、`unicode-animations@1.0.3`。
开发期(7):`@types/node@22.20.1`、`@types/react@19.2.17`、`esbuild@0.28.1`、
`prettier@3.9.5`、`tsx@4.23.1`、`typescript@6.0.3`、`vitest@4.1.10`。
覆盖(1):`ink-text-input` 的 `ink` → `npm:@hermes/ink@0.0.1`。

值得记一笔:`ink-text-input` 虽然被声明为运行时依赖,**`ui-tui/src/` 里没有任何一处 import 它**
(见 ▲1),它只被 `packages/hermes-ink/text-input.js` 再导出,并被 `scripts/build.mjs`
刻意排除在 bundle 之外。

### S4 本片读取的环境变量(**52 个**,逐项列全)

`APPDATA` `CLAUDE_CODE_SCROLL_SPEED` `COLORTERM` `COLS` `CURSOR_TRACE_ID` `EDITOR`
`ELECTRON_BIN` `FORCE_COLOR` `GHOSTTY_BIN_DIR` `GHOSTTY_RESOURCES_DIR`
`HERMES_AUTO_HEAPDUMP` `HERMES_AUTO_HEAPDUMP_COOLDOWN_MS` `HERMES_BIN` `HERMES_DEV_PERF`
`HERMES_DEV_PERF_LOG` `HERMES_DEV_PERF_MS` `HERMES_HEAPDUMP_DIR` `HERMES_HEAPDUMP_MAX_BYTES`
`HERMES_HOME` `HERMES_TUI_BACKGROUND` `HERMES_TUI_LIGHT` `HERMES_TUI_SCROLL_SPEED`
`HERMES_TUI_TERMUX_FAST_ECHO` `HERMES_TUI_TERMUX_MODE` `HERMES_TUI_THEME`
`HERMES_TUI_TRUECOLOR` `HERMES_TUI_VISUAL_DIR` `HISTORY` `ITERS` `LINES` `MOUNTED`
`NODE_ENV` `PATH` `PREFIX` `ROWS` `SSH_CLIENT` `SSH_CONNECTION` `SSH_TTY` `STY` `TERM`
`TERMUX_VERSION` `TERM_PROGRAM` `TERM_SESSION_ID` `TMUX` `VISUAL` `VITEST`
`VSCODE_GIT_ASKPASS_MAIN` `VSCODE_GIT_IPC_HANDLE` `WAYLAND_DISPLAY` `WSL_DISTRO_NAME`
`WSL_INTEROP` `WT_SESSION`

其中 `COLS`/`ROWS`/`ITERS`/`LINES`/`MOUNTED`/`HISTORY` 只被 `scripts/profile-tui.mjs` 用作
基准参数;`ELECTRON_BIN`/`HERMES_TUI_VISUAL_DIR`/`FORCE_COLOR`/`COLORTERM` 属 visual harness。

```verify
cd /home/user/hermes-agent/ui-tui
grep -rhoE "env\.[A-Z][A-Z0-9_]+|process\.env\.[A-Z][A-Z0-9_]+|env\[['\"][A-Z][A-Z0-9_]+" \
    src/components src/lib scripts --include=*.ts --include=*.tsx --include=*.mjs \
  | grep -oE "[A-Z][A-Z0-9_]+$" | sort -u | tee /dev/stderr | wc -l   # 52
```

### S5 `billing-fixtures.tsx` 的夹具注册表(**16 条**,逐项列全)

`sub-free`、`sub-mid`、`sub-top`、`sub-not-admin`、`sub-downgrade`、`sub-cancel`、
`sub-team`、`sub-confirm`、`sub-confirm-new`、`sub-handoff`、`topup-overview`、
`topup-no-card`、`topup-not-admin`、`topup-disabled`、`topup-buy`、`topup-stepup`。

### S6 `visual/render.tsx` 的场景矩阵(**4 条**,逐项列全)

`default · dark terminal`(bg `#101014`,空 skin)、`default · light terminal (Cursor)`(bg `#ffffff`,空 skin)、
`slate · dark terminal`(bg `#101014`,SLATE skin)、`slate · light terminal (raw palette + display shim)`(bg `#ffffff`,SLATE skin)。

```verify
cd /home/user/hermes-agent/ui-tui
grep -cE "^  '(sub|topup)-[a-z-]+': \{" scripts/billing-fixtures.tsx   # 16
grep -c "^addScene(" scripts/visual/render.tsx                          # 4
```

### S7 导出面规模(供“接口面 vs 实现体”定位)

顶层 `export` 语句:components 合计 **158** 条(其中 `textInput.tsx` 一个文件占 **22** 条,
`thinking.tsx` 只 **3** 条),lib 合计 **239** 条。这个反差本身就是结构信息:
`textInput.tsx` 把可判定的逻辑逐条切成了纯函数导出以便单测;`thinking.tsx` 相反,
几乎全是内部组件,只对外给 `Spinner` / `Thinking` / `ToolTrail`。

```verify
cd /home/user/hermes-agent/ui-tui
grep -h '^export ' src/components/*.tsx | wc -l                                    # 158
ls src/lib/*.ts src/lib/*.tsx | grep -v '\.test\.' | xargs grep -h '^export ' | wc -l  # 239
grep -c '^export ' src/components/textInput.tsx                                    # 22
grep -c '^export ' src/components/thinking.tsx                                     # 3
```

---

## §4 端到端链:`/pet list` → 屏幕 → Python → 屏幕

选这条链是因为它**短、完整、两端都在本片可见**:一个 overlay 的开启、一次读 RPC、
一次写 RPC、一次关闭,全程只经过 4 个文件。

**① 用户敲 `/pet list`。** 本地 slash 命令把 overlay 标记置真(此跳在
`src/app/`,不在本片,是本片的上游接入点):

ui-tui/src/app/slash/commands/session.ts:398 @ 863e313

```ts
      // Gallery picker — the interactive browse surface.
      if (sub === 'list') {
        return patchOverlayState({ petPicker: true })
      }
```

**② overlay 路由挂载组件。** 本片的 `appOverlays.tsx` 订阅 `$overlayState`,
把 `PetPicker` 塞进浮动 widget 列表,并把“关闭”实现成把标记置假:

ui-tui/src/components/appOverlays.tsx:257 @ 863e313

```tsx
  if (overlay.petPicker) {
    widgets.push({
      id: 'pet-picker',
      render: width => (
        <FloatBox color={theme.color.border}>
          <PetPicker gw={gw} maxWidth={width} onClose={() => patchOverlayState({ petPicker: false })} t={theme} />
        </FloatBox>
      )
    })
```

**③ 组件挂载即拉数据(读 RPC)。** 注意 `.catch` 把错误交给 `lib/rpc.ts` 的
`rpcErrorMessage` 转成人话,`.finally` 无条件收掉 loading——这是本片所有 hub/picker
的统一写法:

ui-tui/src/components/petPicker.tsx:47 @ 863e313

```tsx
  useEffect(() => {
    gw.request<Gallery>('pet.gallery')
      .then(r => {
        setGallery(r)
        setErr('')
      })
      .catch((e: unknown) => setErr(rpcErrorMessage(e)))
      .finally(() => setLoading(false))
  }, [gw])
```

**④ Python 内核接住。** `pet.gallery` 是一个装饰器注册的 RPC 方法:

tui_gateway/methods_session.py:1480 @ 863e313

```python
@method("pet.gallery")
@_profile_scoped
def _(rid, params: dict) -> dict:
    """List adoptable pets for the desktop appearance picker.

    Returns the petdex gallery merged with local install state plus the
    current config (active slug + enabled). Agent-independent. Fail-open:
```

**⑤ 这条方法被显式放进“不占读线程”的白名单。** 这是跨语言接缝上一个重要的设计事实:
宠物类 RPC 要么走网络(manifest 抓取 / 精灵图下载),要么每帧做 PNG 解码,
若在 reader 线程内联执行就会把 `prompt.submit` / `session.interrupt` 堵在后面:

tui_gateway/server.py:232 @ 863e313

```python
        # animation poll stutters. On the pool they run concurrently.
        "pet.cells",
        "pet.gallery",
        # Generation is the heaviest pet path by far — multiple image-model
        # round-trips per call — so it must never block the reader thread.
        "pet.generate",
        "pet.hatch",
        "pet.info",
        "pet.select",
```

**⑥ 用户按 ↑/↓ 选中、Enter 收养(写 RPC)。** 组件自己拿 `useInput` 收键(过滤掉
控制键与和弦键),成功后直接调 `onClose()` 回到 ②:

ui-tui/src/components/petPicker.tsx:75 @ 863e313

```tsx
  const adopt = (slug: string) => {
    setBusy(true)
    setErr('')
    gw.request('pet.select', { slug })
      .then(() => onClose())
      .catch((e: unknown) => {
        setErr(rpcErrorMessage(e))
        setBusy(false)
      })
  }
```

**⑦ Python 落盘并回参。** 写侧的失败被翻成结构化错误码,而不是异常穿透:

tui_gateway/methods_session.py:1563 @ 863e313

```python
@method("pet.select")
@_profile_scoped
def _(rid, params: dict) -> dict:
    """Adopt a pet from the desktop picker: install (if needed) + activate.

    Params: ``slug`` (required). Writes ``display.pet.*`` to config and returns
    ``{ok, slug, displayName}``. The surface re-pulls ``pet.info`` to render it.
    """
    slug = str(params.get("slug") or "").strip()
    if not slug:
        return _err(rid, 4004, "missing slug")
```

**⑧ 回到界面。** `onClose()` → `patchOverlayState({petPicker:false})` → `appOverlays` 不再
push 该 widget → 浮层消失;宠物本身由 `appLayout.tsx` 的 `PetPane` 在下一次 `pet.info`
轮询时亮起(README 与 petPicker 的注释都写作“no restart”)。

**两端接到谁**:链的上游端(①)在 `src/app/slash/`(片外),下游端(④⑤⑦)在
`tui_gateway/`(片外)。本片负责的是 ②③⑥⑧,即**挂载、发起、收键、卸载**这四跳。

---

## §5 逐机制结构笔记

### §5.1 为什么终端里一个输入框要 1,555 行(重点 a)

先把问题演出来。用户在一个 80 列的终端里,已经打了 79 个字符的 `hello…`,
现在他打第 80 个字符,然后按一次退格。在浏览器里这是两次 DOM 更新;在终端里,
你面对的是这样一串事实:

- 你不能“重画那一格”。你只能往 stdout 写字节,并靠 ANSI 转义把光标移到你想写的位置。
- 终端在第 80 列写下字符后会**自动折行**,光标物理上已经在下一行第 0 列。
  而 `\b \b`(退格-空格-退格,最常见的“擦掉一个字符”手法)**无法跨过折行边界回退**。
- 如果用户打的是中文,一个字素簇占 **2 列**,`str.length` 与列数不再相等。
- 如果用户用的是越南语 Telex 或任何 IME,在定稿之前终端可能已经送来若干中间态字符。
- 如果用户在 tmux 里,tmux 有自己的一份光标模型,你直接写 stdout 会让它跑偏。

`textInput.tsx` 的 1,555 行,基本上就是这五件事各自的对策 + 它们互相不许打架的约束。
下面按“终端特有难题”逐条对上代码。

#### (1) 字素簇:所有位移都不许按 `str.length` 走

模块内建了 `Intl.Segmenter` 的字素边界表,并给它加了 **32 条上限的 LRU 缓存**
(`stopCache`),因为每次按键都要问“上一个/下一个字素边界在哪”。
`snapPos` / `prevPos` / `nextPos` 全部在这张表上走,而不是 `cursor ± 1`。
`wordLeft` / `wordRight` 才回到按字符扫空白(词边界不需要字素精度)。

`lineNav` 是这里最值得抄的一个设计:上下方向键在多行草稿里应当移动光标,
但在**首行按 ↑ / 末行按 ↓** 时应当把这个键**让给上层**(去翻历史或改队列)。
它用返回 `null` 表达“我不吃这个键”:

ui-tui/src/components/textInput.tsx:245 @ 863e313

```tsx
export function lineNav(s: string, p: number, dir: -1 | 1): null | number {
  const pos = snapPos(s, p)
  const curStart = s.lastIndexOf('\n', pos - 1) + 1
  const col = pos - curStart

  if (dir < 0) {
    if (curStart === 0) {
      return null
    }
```

#### (2) 宽字符与软换行:光标行列必须和 Ink 的折行算法**逐格一致**

这是本片最硬的一条不变量,而且它不在 `textInput.tsx` 里,在 `lib/inputMetrics.ts`。
组件渲染文本用的是 Ink 的 `<Text wrap="wrap">`,而 Ink 内部用 `wrap-ansi`。
如果输入框自己再写一份 word-wrap 来算“光标在第几行第几列”,两套算法在
**正好填满一行**、**词中断行**这些边界上会差一格,结果就是硬件光标停在
最后一个字符旁边好几格的地方。

对策不是“把两套算法调一致”,而是**只留一套**:直接把 `wrap-ansi` 的输出拿来,
沿着它一个字符一个字符地反推每一视觉行在原串里的区间。

ui-tui/src/lib/inputMetrics.ts:35 @ 863e313

```ts
function visualLines(value: string, cols: number): VisualLine[] {
  if (!value.length) {
    return [{ start: 0, end: 0 }]
  }

  const width = Math.max(1, cols)
  const wrapped = wrapAnsi(value, width, { hard: true, trim: false })
  const lines: VisualLine[] = []
```

这个反推能成立,依据是 `wrap-ansi` 在 `hard: true, trim: false` 且输入无 ANSI 时
**只插入 `\n`,不删改不重排**——所以两边并行走一遍就能一一对上。
代码里还留了防御性的重同步分支(对不上就 `indexOf` 往前找,找不到就带着已有结果退出),
理由写得很直白:将来换库或有人开始传带 ANSI 的字符串时,宁可少给几行,
也不要给出“看着合理但是错”的区间。

**列数**由 `widthBetween` 用 `stringWidth(每个字素簇)` 累加得出,这才是 CJK 占两列的地方。
`offsetFromPosition` 是它的反函数(鼠标点在第 row 行第 col 列 → 字符串偏移),
里面 `targetCol <= column + Math.max(0, part.width - 1)` 这一句就是“点在宽字符的
右半格也算点中它”。

#### (3) 快速回显(fast echo)与它的四道闸门

纯 React 路径下,每敲一个键要走 React commit → yoga 布局 → diff → 写终端。
在按住键连打或粘贴长文本时这条链太贵。于是有一条**绕过渲染器直接写 stdout** 的旁路:
追加字符就写字符本身,退格就写 `"\b \b"`。

旁路的危险在于:Ink 不知道你动了光标。所以每一次旁路写都必须配一次
`noteCursorAdvance(delta)` 告诉 Ink“物理光标被我挪了几格”。代码把这个配对
**做成了返回值形状**——`fastBackspaceEffect` 同时返回 `write` 和 `advanceDelta`,
调用方拿不到其中一个就不可能只用另一个:

ui-tui/src/components/textInput.tsx:1256 @ 863e313

```tsx
        } else if (canFastBackspace(v, c)) {
          const effect = fastBackspaceEffect(v, c)
          v = effect.newValue
          c = effect.newCursor
          stdout!.write(effect.write)
          // The "\b \b" sequence ends with the cursor one column to the
          // LEFT of where Ink last parked it. Tell Ink so its `displayCursor`
          // (and log-update's relative-move basis on the next frame) stays
          // in sync — otherwise the cursor parks one cell to the right of
          // the caret on the next unrelated re-render.
          noteCursorAdvance(effect.advanceDelta)
          commit(v, c, true, false, false, Math.max(0, lineWidthRef.current - 1))

          return
```

`noteCursorAdvance` 来自分叉渲染器(片外),它同时更新 Ink 的 `displayCursor`
(下一帧相对移动的基准)与当前的光标声明:

ui-tui/packages/hermes-ink/src/ink/hooks/use-cursor-advance.ts:31 @ 863e313

```ts
export function useCursorAdvance(): CursorAdvanceNotifier {
  return useContext(CursorAdvanceContext)
}
```

**四道闸门**决定这条旁路能不能走:

1. **形状闸门(追加)**——`canFastAppendShape`。它**不是**用
   `stringWidth(text) === text.length` 判断,而是要求纯 ASCII 可打印字符,
   因为越南语的预组合字母 `ề`(U+1EC1)宽度 1 长度 1 却仍然是 IME 产物:

   ui-tui/src/components/textInput.tsx:421 @ 863e313

   ```tsx
   export function canFastAppendShape(
     current: string,
     cursor: number,
     text: string,
     columns: number,
     currentLineWidth: number
   ): boolean {
     if (cursor !== current.length) {
       return false
     }

     if (current.length === 0) {
       return false
     }

     if (current.includes('\n')) {
       return false
     }

     if (!ASCII_PRINTABLE_RE.test(text)) {
       return false
     }

     return currentLineWidth + text.length < Math.max(1, columns)
   }
   ```

   最后那个 `<`(严格小于)就是软换行闸门:只要这次追加会**正好填满**当前行,
   就退回正常渲染路径。

2. **形状闸门(退格)**——`canFastBackspaceShape`,同样只允许纯 ASCII,并在传入
   `columns` 时额外拒绝“光标在视觉列 0”与“光标列 ≥ 宽度”两种物理上等价的状态
   (都表示终端已经自动折到下一行,`"\b \b"` 表达不了那次跨行回退)。
   `columns` 是可选参数,只为让老的形状契约单测不必穿宽度进来,注释里明确写着
   **新调用方不许省略**。

3. **终端闸门**——`supportsFastEchoTerminal`。三类宿主整体禁用:

   ui-tui/src/components/textInput.tsx:511 @ 863e313

   ```tsx
   export function supportsFastEchoTerminal(env: NodeJS.ProcessEnv = process.env): boolean {
     // Terminal.app still shows paint/cursor artifacts under the fast-echo
     // bypass path. Fall back to the normal Ink render path there.
     if ((env.TERM_PROGRAM ?? '').trim() === 'Apple_Terminal') {
       return false
     }
   ```

   tmux 的判定尤其值得抄:`TMUX` 变量**不会随 SSH 转发**,所以远端 TUI 只能看到
   tmux 风味的 `TERM`(`tmux` / `tmux-*`),于是两者都匹配;同时**刻意不匹配 `screen*`**
   ——GNU screen 设同样的 `TERM` 但没有漂移报告,在无证据的情况下扩大禁用面
   等于白白关掉优化。Termux 默认关闭但留 `HERMES_TUI_TERMUX_FAST_ECHO` 显式开关。

4. **运行时闸门**——`canFastEchoBase()`:必须 `focus` 且终端有焦点、无选区、
   非掩码输入、stdout 是 TTY。

#### (4) 三个 16ms 定时器:本地渲染、父级回调、按键突发

`FRAME_BATCH_MS = 16`(一帧)在三处独立使用,分别对应三种“可以晚一点”的东西:

- `scheduleLocalRender()` → 延后 `setCur`(本组件重渲染);
- `scheduleParentChange()` → 延后 `cbChange.current(next)`(通知父级 draft 变了);
- `scheduleKeyBurstCommit()` → 连打时只在突发结束后 flush 一次父级。

延后 `setCur` 带来一个真实的回归,注释里点名了它:如果这 16ms 内有**不相关的**
渲染冲刷了本组件,而布局用了过期的 `cur` state,`useDeclaredCursor` 里的 layout effect
就会发布一个过期的光标声明,把旁路刚做的 `noteCursorAdvance` 覆盖掉。修法是把
“该读 ref 不该读 state”这条不变量**提成一个纯函数**以便单测:

ui-tui/src/components/textInput.tsx:318 @ 863e313

```tsx
export function resolveCursorLayout(display: string, cur: number, curRefCurrent: number, columns: number) {
  void cur // intentionally unused for layout — see doc comment above

  return cursorLayout(display, curRefCurrent, columns)
}
```

`void cur` + 参数保留是刻意的:`cur` 仍在作用域里,React 因此正常追踪依赖,
但它不作为布局真值。

#### (5) ANSI 转义:三处“不许用 SGR”的决定

终端里画反显、灰字、光标块,最省事的写法是 SGR 的 `dim`(2)和 `inverse`(7)。
本文件三处都**拒绝**了这条路,理由都很具体:

- **占位提示文字**必须用显式真彩前景色(`colorizeHint`),不许用 dim/inverse。
  因为这两者都由终端相对默认前/背景色解释,在**透明背景配置**
  (`terminal.background #00000000`)下会合成到一个用户根本看不见的黑色 RGB 上,
  提示就渲染成一个色块。
- **打字回显**(旁路写的那些字节)必须带上和 Ink 渲染同一个显式前景色
  (`colorizeEcho`)。否则一旦皮肤把背景重绘成相反极性(深色皮肤跑在浅色终端上),
  旁路写下的字符就是黑底黑字。
- **空输入时的光标**是**合成的**(`hintCursorCell`):把占位符第一个字符画成
  “提示色底 + 按亮度挑的墨色”,同时把硬件光标藏掉。因为宿主终端用**自己的**
  cursor/cursorAccent 颜色画块状光标,会变成一个吞掉第一个字形的实心色块
  (注释里的现象:`Ask me anything…` 显示成 `sk me anything…`)。

  ui-tui/src/components/textInput.tsx:69 @ 863e313

  ```tsx
  /** Synthetic placeholder cursor: a hint-colored chip with luminance-picked
   *  ink, standing in for the hidden hardware cursor (bubbles pattern). */
  const hintCursorCell = (ch: string, hex?: string) => {
    const [r, g, b] = hintRgb(hex)
    const ink = 0.2126 * r + 0.7152 * g + 0.0722 * b > 140 ? '0;0;0' : '255;255;255'

    return `${ESC}[48;2;${r};${g};${b}m${ESC}[38;2;${ink}m${ch}${ESC}[39m${ESC}[49m`
  }
  ```

  硬件光标的隐藏/恢复是一个 effect 对 `\x1b[?25l` / `\x1b[?25h` 的成对写入,
  触发条件有三个:有选区、终端失焦(否则多数终端会在停靠位画一个空心方框幽灵)、
  正在显示占位符。

选区反显仍然用 SGR 7,但是**手写**的(`INV` / `INV_OFF` 常量 + `renderWithSelection`),
不走 Ink 的样式属性——因为反显要落在字符串的任意子区间上,而不是整个 `<Text>`。

#### (6) 键盘协议的坑:前向删除靠嗅探原始字节

Ink 的按键模型分不清某些终端送来的前向删除(Delete 键)。于是有一个 hook 在
input 事件上 **prependListener**,直接用正则嗅探原始序列 `ESC[3~` / `ESC[3$` / `ESC[3^` / `ESC[3;`:

ui-tui/src/components/textInput.tsx:583 @ 863e313

```tsx
function useFwdDelete(active: boolean) {
  const ref = useRef(false)
  const { inputEmitter: ee } = useStdin()

  useEffect(() => {
    if (!active) {
      return
    }

    const h = (d: string) => {
      ref.current = FWD_DEL_RE.test(d)
    }

    ee.prependListener('input', h)

    return () => {
      ee.removeListener('input', h)
    }
  }, [active, ee])

  return ref
}
```

同类的“协议归一”还有:
- **Ctrl+J(裸 LF)**:`shouldPreserveCtrlJNewline` 按宿主(Windows Terminal、SSH、
  Ghostty、WSL)决定裸 `\n` 是换行还是提交。
- **行删除修饰键**:`isLineKillModifier` **只认 `super` 位**。注释解释得很清楚——
  复用 `isActionMod` 会在 macOS 上把 `meta` 也算进去,而分叉 Ink 把 Option 报成 `meta`,
  那样 Option+Backspace(macOS 标准的删词)就被吞了。
- **macOS 终端的改写**:`isMacActionFallback` 处理那些把 Cmd+Left/Right/Backspace
  直接翻成 Ctrl+A/Ctrl+E/Ctrl+U 才送进来的终端。
- **bracketed paste**:`BRACKET_PASTE` 正则在插入前剥掉 `ESC[200~` / `ESC[201~` 包裹;
  含 `\n` 的多字符输入一律按粘贴路由(`shouldRouteMultiCharInputAsPaste`)。
- **让位给全局处理器**:`shouldPassThroughToGlobalHandler` 列出 9 类键
  (Ctrl+C/X/O、Tab、Shift+Tab、PgUp、PgDn、Esc、以及用户配置的语音键)。
  语音键排在最前,因为用户可能把语音绑到 `ctrl+v`,那时它必须赢过粘贴。

#### (7) 鼠标与撤销

鼠标是四个 handler:`onClick`(移光标)、`onMouseDown`(左键起选区 / 500ms 内同位
再点 = 全选 / 右键按 `decideRightClickAction` 决定复制还是粘贴)、`onMouseDrag`、
`onMouseUp`(macOS 上抬手即写系统剪贴板,对齐平台习惯)。
撤销/重做是两个上限 200 的栈,`commit(..., track=false)` 用于回放本身。
另外组件把选区通过 `setInputSelection` 发布到 `app/inputSelectionStore`,
让滚动逻辑能在滚动时保持选区锚点(README 的 `src/app/scroll.ts`)。

**小结:1,555 行的构成**。粗分:约 250 行是纯字符串/位移算法(字素、词、行、kill),
约 200 行是快速回显的四道闸门 + 效果函数,约 120 行是 ANSI 直写(提示色、回显色、
合成光标、反显、光标显隐),约 300 行是单个 `useInput` 里的按键分派树,
约 120 行是鼠标,其余是状态/ref/定时器/类型与那些**解释“为什么不能简化”的注释**。
它长不是因为功能多,而是因为**每一个平台差异都必须显式写下来**——终端没有
“浏览器帮你处理”的那一层。

### §5.2 `thinking.tsx`:一棵会自己决定要不要出现的树(重点 a 之二)

场景:模型开始回答。它先思考(reasoning),然后调三个工具,其中一个是
`Delegate Task` 从而 fan-out 出 5 个子代理,子代理又各自调工具;同时后台有两条
警告事件。用户此刻可能想看全部,也可能想只看一行摘要,还可能用 `/details hidden`
把整片区域关掉——但**失败信息不能因此看不到**。

`thinking.tsx` 就是这个显示策略的全部实现,结构上是三层:

1. **树形原语**(`TreeRow` / `TreeTextRow` / `TreeNode`)。终端里没有缩进容器,
   树线是**字符串**:`rails`(一串布尔,表示每层是否还要画竖线)+ `branch`(`mid`/`last`)
   经 `treeLead` 拼出 `│ ` / `  ` / `├─ ` / `└─ ` 的前缀。`NoSelect fromLeftEdge` 把
   这段前缀排除在鼠标文本选择之外——用户复制内容时不该带上树线。
2. **动画原语**。`Spinner` 从 `unicode-animations` 的 7 个盲文动画里随机挑一个,
   并把每帧**截成单个码点**(`raw.frames.map(f => [...f][0])`),因为多码点帧在
   窄终端里宽度不稳。`StreamCursor` 是 420ms 闪一次的 `▍`。
3. **面板装配**。`ToolTrail` 把 `trail`(字符串行)、`tools`(活动工具)、
   `subagents`(生成树)、`activity`(环境事件)整理成最多 4 个可折叠面板
   + 一个 Σ token 汇总行。

三个值得抄的设计:

**(a) 分区可见性是三态而不是布尔。** `sectionMode(section, detailsMode, sections, commandOverride)`
把全局 `/details` 模式和逐区覆盖合成 `hidden` / `collapsed` / `expanded`。
本地折叠状态只在**挂载时**从它初始化,之后由用户的点击拥有。注释里用大写警告
写明**绝不许在渲染时把本地状态和 `expanded` 做 OR**——那会把面板锁死在展开态,
让手动点击静默失效。

**(b) effect 首跑会打脸初始值。** React 的 effect 在**第一次**渲染后也会跑,
所以那个“可见性变了就重新同步折叠态”的 effect 会在挂载后立刻把
`reasoningAlwaysVisible`(MoA 参考块的特权)冲掉。修法是跳过第一次:

ui-tui/src/components/thinking.tsx:754 @ 863e313

```tsx
  // Effects run after the FIRST render too, not just on later updates — so
  // this re-sync was clobbering the reasoningAlwaysVisible mount value above
  // right after mount, collapsing a just-opened MoA reference panel under
  // `thinking: hidden` before the user ever saw it (#64701). Skip only the
  // very first run; every subsequent `visible` change (the case this effect
  // exists for) still re-syncs without the override, so a manual collapse
  // still sticks per the no-OR-at-effect-time rule above.
  const skippedInitialSync = useRef(false)
  useEffect(() => {
    if (!skippedInitialSync.current) {
      skippedInitialSync.current = true

      return
    }

    setOpenThinking(visible.thinking === 'expanded')
    setOpenTools(visible.tools === 'expanded')
    setOpenSubagents(visible.subagents === 'expanded')
    setOpenMeta(visible.activity === 'expanded')
```

**(c) 全隐藏时的兜底(backstop)。** 只有当**每一个**分区都解析为 `hidden` 时
才整体收敛为空;而这时如果还有 error/warn 级别的活动事件,就退化成最多两行
紧凑告警,免得静音模式的用户对失败完全失明。

其余结构要点:所有生成树派生(`buildSubagentTree`/`peakHotness`/`treeTotals`/
`widthByDepth`/`sparkline`/`formatSummary`)都用 `useMemo` 并**放在任何提前 return
之前**,以满足 React 的 hooks 调用顺序稳定;工具计时用一个 500ms 的 interval,
且只在有工具且面板展开时才起;单个 `Delegate Task` 组时把子代理树**内联**到该组下面
(`inlineDelegateKey`),避免同一份信息出现两次。

### §5.3 流式 Markdown 的三代演进(与 §5.4 的基准脚本互为因果)

`streamingMarkdown.tsx` 的文件头把三代方案写全了:

- **naive**:每个 delta 都 `<Md text={full}/>`,整条消息重新 tokenize → O(total)×deltas。
- **monolithic**:切一个“稳定前缀”出来 memo。修掉了每 delta 的成本,但没修
  **每块的悬崖**:边界每前进一次,整个前缀从头重解一遍 → O(blocks²),外加每次
  一遍 O(total) 的围栏重扫。
- **per-block(现行)**:一个**前向扫描器**把围栏/数学状态和扫描位置存在 ref 里
  跨 delta 保留,每个 delta 只碰新到的完整行;`\n\n` 处冻结出的定稿块进一个
  append-only 数组,各自是一个按“永不再变的文本”memo 的 `<Md>`。

ui-tui/src/components/streamingMarkdown.tsx:91 @ 863e313

```tsx
export const advanceScan = (text: string, state: StreamScanState) => {
  const start = state.scanned.length

  let i = start

  while (i < text.length) {
    const nl = text.indexOf('\n', i)

    if (nl < 0) {
      break // partial trailing line — could still open a fence; keep in tail
    }
```

四条保持正确性的不变量(文件头自述,我逐条对上了代码):
只扫**以换行结尾**的行(残缺尾行可能还会变成围栏开头,留在 tail);
空行边界不可回溯合并(setext 下划线只绑紧邻上一行);
未闭合的 `$$` / `\[` 视为**永远开着**(比 `markdown.tsx` 的全文回落更保守,
因为定稿块冻结后无法在闭合符流进来时反悔);
状态只前进(StrictMode 下幂等),`text` 不再延续 `scanned` 时整体重置。

### §5.4 `scripts/` 是性能与视觉的行为规格(重点 b)

这九个脚本里只有 `build.mjs` 在生产路径上,其余八个的价值是**把“怎么算变好了”写成可执行的**。
逐个说清测什么、判据是什么。

#### `build.mjs` —— 生产打包(判据:能跑起来 + 不带多余依赖)

esbuild 把 `src/entry.tsx` 打成单文件 ESM(`platform: node`、`target: node20`)。
三处刻意:

ui-tui/scripts/build.mjs:38 @ 863e313

```
  // Skip the prebuilt @hermes/ink bundle and inline the source instead:
  // (1) esbuild's `__esm` helper does not await nested async init, so the
  //     prebuilt bundle's lazy `render` would never resolve when nested in
  //     this top-level Promise.all; (2) bundling from source also lets us
  //     keep `ink-text-input` and the upstream `ink` graph OUT of the
  //     bundle entirely — re-exporting them from entry-exports created a
  //     circular async chain that hung the TUI at startup with only ANSI
  //     reset bytes on screen (#31227).
  alias: { '@hermes/ink': resolve(root, 'packages/hermes-ink/src/entry-exports.ts') },
  plugins: [stubDevtools],
```

（注:上面这个块的锚点扩展名是 `.mjs`,不在 `verify_citations.py` 的可识别后缀表里,
因此它是**未被机械校验**的逐字摘录——我用 `sed -n '38,47p'` 取出后原样粘贴。）

另两处:`stubDevtools` 插件把只在 `DEV=true` 才用的 `react-devtools-core` 换成空实现;
产物生成后**剥掉 shebang**,因为 Nix 的 `patchShebangs` 会把
`/usr/bin/env -S node --foo` 里的 `node` token 吃掉,留下一个坏解释器。

这个脚本的“判据”是外部的、真实的:Nix 构建直接调它,`hermes_cli` 会检查
`ui-tui/dist/entry.js` 是否比源文件旧:

nix/tui.nix:11 @ 863e313

```nix
  buildPhase = ''
    # esbuild bundles everything — no need for tsc or vite.
    # Run from the workspace root where node_modules/ lives.
    node ui-tui/scripts/build.mjs
  '';
```

（同上:`.nix` 也不在校验器的可识别后缀表里,这个块是 `sed -n '11,15p' nix/tui.nix`
取出后原样粘贴的**未被机械校验**的逐字摘录。）

#### `bench-history-scroll.tsx` —— 虚拟滚动的性能**与正确性**双规格

**测什么**:在 100 / 1,000 / 10,000 条历史(可用 `--items=` 改)下,把 `useVirtualHistory`
挂进真 Ink 渲染(`renderSync` + 一个自计数的 `CountingStream` 当 stdout,80×30…
实际 `COLUMNS=100 / ROWS=30`),跑五个阶段:挂载 → 改最后一条重渲染 → 滚到 55% 处 →
把当前可见的某一行**高度改大 3 行**并等偏移表收敛 → 卸载。

**判据(这是它比普通 benchmark 值钱的地方)**:每个 sample 采 11 个指标,其中 **3 个是
不变量而不是速度**:

- `anchorError` —— 被改高的那一行如果在视口**上方**,滚动位置应当同步 +3;
  否则应当**不动**。误差 = |实际 scrollTop − 期望|。**这条不为 0 就是回归**
  (内容变高把用户正在看的地方顶跑了)。
- `invalidOffsets` —— 偏移表里出现非有限数的个数,应为 0。
- `nonMonotoneOffsets` —— 偏移表非单调递增的个数,应为 0。

速度侧是 `mountMs` / `rerenderMs` / `scrollMs` / `measuredHeightReconciliationMs` /
`terminalBytes` / `terminalWrites` / `heapDeltaBytes` / `mountedRowsMax`,每项都出
min/mean/p50/p95/p99/max,并额外算**相邻规模之间的 p50 比值**(`scaling`):
条目从 100→1,000→10,000 各涨 10 倍,如果 `mountP50Factor` 也涨 10 倍就说明还是 O(n),
虚拟化没生效。`mountedRowsMax` 必须被 `MAX_MOUNTED = 120` 压住,这是虚拟化的直接证据。

**另一半工作负载**:每轮还在固定视口里挂一个 100 / 1,000 / 10,000 行的**超大 bordered/fill 盒**
(高度方向一个、宽度方向一个 absolute),只有几个 Yoga 节点。这样把
**渲染器裁剪成本**从**节点构造成本**里分离出来:`terminalBytes` 若随 extent 线性上涨,
说明裁剪没生效。

**可比性的设计**:文件头第一句就写“本文件刻意只用性能候选之前就存在的 API,
以便同一份脚本在 base 与 candidate 两个 checkout 上原样跑”。这是把“对照实验”
写进脚本约束的做法。

#### `bench-streaming-md.tsx` —— 三策略对照(判据:倍数表)

**测什么**:合成一段按块生成的 Markdown 流(段落/列表/`ts` 围栏/标题四种循环),
按**每行一次**的粒度重放(`makeUpdates`),分别喂给 naive / monolithic / per-block 三种渲染,
规模 32 / 128 / 512 块。输出是一张 Markdown 表:每种策略的耗时 + `new vs naive`、
`new vs monolithic` 的倍数。

**判据即那两列倍数**,并且倍数应随规模**变大**(如果 per-block 真是每块只解一次,
它对 O(blocks²) 的领先必须随块数增长)。为了让倍数可信,脚本做了三件隔离:

- **每个「策略×规模」跑在自己的子进程里**(orchestrator 模式,`execFileSync npx tsx 自己`),
  这样 `markdown.tsx` 里那个解析 LRU 和一种策略造成的 GC 压力不会污染另一种;
- 每次运行给文本一个**唯一 salt**,并新建一个 theme 对象——因为 `mdCache` 是
  `WeakMap<Theme, Map<...>>`,新 theme 就是新缓存桶;
- 每 64 次重渲染清一次 `performance` 的 mark/measure 缓冲,否则**条目缓冲自己**
  会在几千次重渲染后变成内存泄漏并把长跑数据带偏。

它还把**上一代实现整份抄在文件里**(`findStableBoundaryOld` + `fenceOpenAt` +
`MonolithicStreamingMd`),这样对照组不依赖 git 历史——这正是 §5.3 那段演进叙述的实验装置。

#### `profile-tui.mjs` —— 整树 CPU/内存 profile(判据:JSON 报告)

**测什么**:用 `node:inspector` 起 Profiler + HeapProfiler,把整棵 `AppLayout` 挂到一个
自造的 `Sink`(假 stdout,记 `bytes`/`writes`,`isTTY = true`),喂 500 条历史
(`HISTORY`)、120 行挂载上限(`MOUNTED`)、1,200 行流式文本(`LINES`),
分 40 次(`ITERS`)按前缀递增地 `rerender`。

**判据**:输出 JSON —— `elapsedMs`、`stdoutBytes`、`stdoutWrites`、
`startMem`/`endMem`/`afterGc`(collectGarbage 之后再采一次,**用来区分"缓存"与"泄漏"**)、
`profileNodes`。所有规模都从环境变量读,便于扫参数。
注意它 `render(...)` 之前先 `resetUiState/resetTurnState/resetOverlayState`——
nanostore 是模块级单例,不重置就带着上一次的状态。

#### `billing-fixtures.tsx` —— 状态穷举式视觉夹具(判据:人眼 + 可复述的状态名)

**测什么**:不是性能,是**状态覆盖**。它绕过 gateway,用手搓的 state 对象直接挂真
`BillingOverlay` / `SubscriptionOverlay`,"和 vitest 渲染测试完全一样的方式",
所以看到的就是 `/subscription` 与 `/topup` 运行时画的东西。16 个夹具
(见 S5)把该覆盖的分支都点了名:免费/中层/顶层、非管理员只读、
计划降级挂起、取消挂起、团队 org 死路、确认页(首次订阅 vs 变更)、handoff 过渡、
有卡/无卡、组织关闭远程支付、购买页、step-up。
`SCREEN=confirm npx tsx …` 可直达子屏幕;`--list` 打印全表。

**判据**:`--list` 里每个夹具的一句话 `desc` 就是验收话术(例如
`topup-stepup` 的 `'/topup step-up — "Allow Remote Spending" (resumable, holds $100 buy)'`
——评审要能看到那笔 $100 被"held"而不是丢掉)。文件里还留了一条防漂移声明:
`TIERS` 只是镜像线上目录,真 overlay 永远从 `GET /api/billing/subscription` 读 tiers。

#### `visual/*` —— 主题 × 背景的视觉回归(判据:一张四宫格 PNG)

四个文件是一条流水线,`npm run visual` 是入口:

- **`run.mjs`(启动器)**:自己设 `FORCE_COLOR=3` / `COLORTERM=truecolor` 而不用
  POSIX 的 `VAR=x cmd` 前缀(那在 Windows 的 npm command shell 下会坏);
  electron 从安装树里 `require.resolve` 借来(桌面工作区已经有一份,根
  `npm install` 会 hoist),而不是给 ui-tui 再声明一份依赖,`ELECTRON_BIN` 可覆盖。
- **`render.tsx`(取样)**:用 `renderSync` 把三块真表面——`Banner` + `SessionPanel`、
  `FloatingOverlays`(带补全列表)、状态行 —— 渲成**带 ANSI 的字符串**,
  然后自己实现一个 SGR 解析器把 ANSI 转成 HTML span(处理 `38;2`/`48;2` 真彩、
  `38;5`/`48;5` 索引色→CSS 变量、0/1/2/3/7/22/23/27/39/49,以及**丢弃非 SGR 转义**),
  按 4 个场景铺成 2×2 网格写出 `tui-visual.html`。
- **`shot.mjs`(定影)**:Electron 离屏窗口 1500×2100,`disableHardwareAcceleration()`,
  载入 HTML、等 700ms、`capturePage()` 存 PNG。
- **`paths.mjs`**:两边共用输出目录。

**判据**:一张 `tui-visual.png`,四宫格。它测的是那类**只有人眼(或多模态 agent)
能判的缺陷**:深色皮肤跑在浅色终端上是否黑底黑字、透明背景下 banner 是否出现黑条、
dim 在不同背景下是否还读得出、边框字符是否对齐。§5.1 讲的三处"不许用 SGR"决定,
就是这条流水线能抓到的那类问题。

### §5.5 lib 层里几个可直接迁移的小设计

- **`terminalModes.ts` 的"只还我涂过的"**。退出时要把终端各种模式复位,
  但**不该**顺手把用户自己的默认前/背景色也重置。做法是给 OSC 10/11 各建一个
  带 `painted` 标记的槽,`resetTerminalModes` 只在真涂过时才追加 `OSC 110/111`:

  ui-tui/src/lib/terminalModes.ts:3 @ 863e313

  ```ts
  export const TERMINAL_MODE_RESET =
    "\x1b[0'z" + // DEC locator reporting
    "\x1b[0'{" + // selectable locator events
    '\x1b[?2029l' + // passive mouse
    '\x1b[?1016l' + // SGR-pixels mouse
    '\x1b[?1015l' + // urxvt decimal mouse
    '\x1b[?1006l' + // SGR mouse
    '\x1b[?1005l' + // UTF-8 extended mouse
    '\x1b[?1003l' + // any-motion mouse
    '\x1b[?1002l' + // button-motion mouse
    '\x1b[?1001l' + // highlight mouse
    '\x1b[?1000l' + // click mouse
    '\x1b[?9l' + // X10 mouse
    '\x1b[?1004l' + // focus events
    '\x1b[?2004l' + // bracketed paste
    '\x1b[?1049l' + // alternate screen
    '\x1b[<u' + // kitty keyboard
    '\x1b[>4m' + // modifyOtherKeys
    '\x1b[0m' + // attributes
    '\x1b[?25h' // cursor visible
  ```

  复位走 `writeSync(fd)` 而不是异步 `stream.write`,因为进程正在退出;
  运行时的颜色涂改走异步流,以便和 Ink 的帧有序。

- **`themeBoot.ts` 的"回放上一帧"**。主题的三个来源都是异步的,于是把上次解析结果
  落盘,下次当第一帧渲染。这是把 Web 上 `localStorage` 防主题闪烁那套搬进终端。

- **`wheelAccel.ts` 的两条路径**。同一个"滚一格滚多少行"的问题,原生终端和
  xterm.js 宿主的事件节奏完全不同,所以是两个函数而不是一堆 `if`;并且它承认了
  一个物理事实——机械滚轮编码器会抖动(方向翻转又立刻翻回),需要**推迟一个事件**
  才能区分"抖动"和"真反向",代价是那一格被吞掉,注释里明写"acceptable latency"。

- **`loaders.ts` 的"一个 interval"**。骨架屏动画的成本在终端里是实打实的重绘,
  所以整套 shimmer 只有父级持有一个时钟,行组件是纯的;颜色一律由调用方给主题色,
  **绝不硬编码**。

- **`widgetGrid.ts` 的轨道求解**。固定轨道取定值,`fr` 轨道按权重分余数
  (floor 分配 + 余数从左往右补),跌破 `min` 的轨道钉住后**重解其余**,
  最后保证每条 ≥1 格、总和不超过可绘宽度(不够就从尾部削)。终端里没有子像素,
  所以"整数 + 余数分配"是必须的,不能像 CSS 那样靠浮点。

---

## §6 发现清单

### ■1 `killToLineStart` 在"草稿首字符是换行且光标在 0"时**插入**一个换行

Ctrl+U(或映射过来的 Cmd+Backspace)的实现是:

ui-tui/src/components/textInput.tsx:334 @ 863e313

```tsx
export function killToLineStart(value: string, cursor: number): { value: string; cursor: number } {
  const start = value.lastIndexOf('\n', Math.max(0, cursor - 1)) + 1
  const from = start === cursor && cursor > 0 ? start - 1 : start

  return { value: value.slice(0, from) + value.slice(cursor), cursor: from }
}
```

`cursor === 0` 时 `Math.max(0, cursor - 1)` 把 `lastIndexOf` 的起点**夹到 0**,
于是它会匹配到**位于下标 0 的那个换行**——那个换行并不在光标之前。
`start` 变成 1,而 `start === cursor && cursor > 0` 这道守卫因 `cursor > 0` 不成立而
不生效,于是 `from = 1 > cursor = 0`,`slice(0,1) + slice(0)` 把 `value[0]` 算了两遍。

复现(把上面锚点处的函数体逐字转抄进 node,不依赖 node_modules):

```verify
node -e '
const killToLineStart = (value, cursor) => {
  const start = value.lastIndexOf("\n", Math.max(0, cursor - 1)) + 1
  const from = start === cursor && cursor > 0 ? start - 1 : start
  return { value: value.slice(0, from) + value.slice(cursor), cursor: from }
}
console.log(JSON.stringify(killToLineStart("\nabc", 0)))  // {"value":"\n\nabc","cursor":1}  ← 多了一个换行
console.log(JSON.stringify(killToLineStart("abc", 0)))    // {"value":"abc","cursor":0}      ← 正确的 no-op
console.log(JSON.stringify(killToLineStart("ab\ncd", 3))) // {"value":"abcd","cursor":2}     ← 正确
'
```

**可达路径**:空草稿按 Shift+Enter(得到 `v="\n"`, `c=1`)→ Home / Ctrl+A(`c=0`)
→ Ctrl+U。分派处 `textInput.tsx:1297` 的 `actionDeleteToStart` 分支**没有 `c > 0` 守卫**
(`k.backspace` 分支有)。**影响很小**(退化成一次多余的换行插入,可撤销),
但方向是错的:一个"删除"操作在边界上变成了"插入"。

**是不是已知**:现有单测 `ui-tui/src/__tests__/textInputKillLine.test.ts:41`
那条用例叫 `is a no-op at the very start of the buffer`,但只用 `'abc'` 取样——
即**契约已经写明"缓冲区最开头是 no-op"**,而首字符为换行的取样从未被测过。
`killToLineEnd` 对称位置是正确的(`killToLineEnd("\nabc",0)` → `"abc"`)。

### ▲1 README 说掩码提示与 clarify 自由文本用 `ink-text-input`,实际用的是本仓的 `components/textInput.tsx`

ui-tui/README.md:182 @ 863e313

> - Clarify free-text mode and masked prompts use `ink-text-input`, so text editing there follows the library's default bindings rather than `components/textInput.tsx`.

整句一并判定:前半句(用哪个组件)与后半句(因此键位跟库的默认而非 `textInput.tsx`)
**都不成立**。它归 `## Hotkeys and interactions` → `### Prompt and picker modes` →
`Notes:` 管,是这一节对"这两处编辑体验按哪套键位"的唯一说明。

`MaskedPrompt` 直接 import 本仓的 `TextInput`,并传 `mask="*"`:

ui-tui/src/components/maskedPrompt.tsx:1 @ 863e313

```tsx
import { Box, Text } from '@hermes/ink'
import { useState } from 'react'

import type { Theme } from '../theme.js'

import { TextInput } from './textInput.js'

export function MaskedPrompt({ cols = 80, icon, label, onSubmit, sub, t }: MaskedPromptProps) {
  const [value, setValue] = useState('')
```

`ClarifyPrompt` 的自由文本分支同样用它(`ui-tui/src/components/prompts.tsx:9` 的
`import { TextInput } from './textInput.js'`,第 196 行处渲染)。

**搜索面**:`grep -rn "ink-text-input" ui-tui/`(排除 `node_modules/`)命中 13 处,
其中 `ui-tui/src/` 下**只有 1 处且在测试注释里**(`src/__tests__/bundleNoAsyncEsmDeadlock.test.ts`
断言 bundle **不含**它),其余在 `packages/hermes-ink/`(再导出)、
两个 `package.json`(依赖 + overrides)、`scripts/build.mjs`(刻意排除)和 README 自身。
即 `ui-tui/src/` 里**没有任何生产代码 import 它**。未排除:运行时动态 import
(`grep -rn "import("` 未专门核查)。

后果不只是文档不准:README 由此推断"那两处的编辑键位跟库默认",而实际上它们
**完整继承了 `textInput.tsx` 的全部行为**——包括快速回显旁路、鼠标选区、
撤销栈、OSC/剪贴板路径。对着 README 排查一个掩码输入框的按键问题会找错文件。

### ▲2 README 说审批提示可用 `o`/`s`/`a`/`d` 快捷选择,实际只认数字 1..N

ui-tui/README.md:168 @ 863e313

> | approval prompt             | `o`, `s`, `a`, `d`  | Quick-pick `once`, `session`, `always`, `deny`    |

审批提示的按键分派全部在一个纯函数里,它只处理 Esc、**数字**、Enter、上下箭头:

ui-tui/src/components/prompts.tsx:59 @ 863e313

```tsx
    return { kind: 'choose', choice: 'deny' }
  }

  const n = parseInt(ch, 10)

  if (n >= 1 && n <= opts.length) {
    return { kind: 'choose', choice: opts[n - 1]! }
  }

  if (key.return) {
    return { kind: 'choose', choice: opts[sel]! }
  }
```

组件自己画的提示行也写着数字:`↑/↓ select · Enter confirm · 1-{opts.length} quick pick · Esc/Ctrl+C deny`
(`ui-tui/src/components/prompts.tsx:140`)。同一张表里 clarify 那三行写的是
"single-digit number",是对的;唯独 approval 这一行写成了字母。

**搜索面**:`ApprovalPrompt` 全仓仅一处挂载(`ui-tui/src/components/appOverlays.tsx:71`),
其 `useInput` 回调只调 `approvalAction`,别无分支;
`grep -rn "=== 'o'\|=== 'a'\|=== 's'\|=== 'd'\|inp === 'o'" ui-tui/src --include=*.ts --include=*.tsx`
(排除 `__tests__`)的 15 处命中全部属于别的组件(会话切换器的 `d`=删除、
agentsOverlay 的 `s`、journey 的 `d`、modelPicker 的 Ctrl+D、`sdk/apps/gridTest`、
以及 textInput 的 Cmd+A),没有一处在审批路径上。
未排除:分叉 Ink 若把某些字母键翻译成 `key.*` 布尔位(未逐一核查 `packages/hermes-ink` 的键解析表)。

### ▲3 README 说 clarify 模式没有专用取消快捷键,实际 Esc 就是

ui-tui/README.md:184 @ 863e313

> - Clarify mode has no dedicated cancel shortcut in the current client. Sudo and secret prompts only expose `Ctrl+C` cancellation from the app-level blocked handler.

第一句不成立。`ClarifyPrompt` 的 `useInput` 第一件事就是处理 Esc,且区分两态:
在"选项 + 正在打自由文本"时 Esc 退回选项列表,否则 Esc 直接取消:

ui-tui/src/components/prompts.tsx:158 @ 863e313

```tsx
  useInput((ch, key) => {
    if (key.escape) {
      typing && choices.length ? setTyping(false) : onCancel()

      return
    }
```

组件自己的提示行也写着 `Esc/Ctrl+C cancel`(`ui-tui/src/components/prompts.tsx:227`)
与 `Esc {choices.length ? 'back' : 'cancel'}`(第 205 行)。第二句(sudo/secret 只有 Ctrl+C)
未在本片证伪——`MaskedPrompt` 确实不自己处理 Esc,取消走上层。

### ▲4 README 说 `PgUp`/`PgDn` 交给终端、TUI 不处理,实际 TUI 按半屏滚抄本

ui-tui/README.md:161 @ 863e313

> - `PgUp` / `PgDn` are left to the terminal emulator; the TUI does not handle them.

本片的输入框确实**不吃**这两个键——它把它们列进"让给全局处理器"的名单
(`ui-tui/src/components/textInput.tsx:1546` 的 `key.pageUp ||`)。但全局处理器接住了它们
并滚动抄本(此文件在片外,是本条 ▲ 的判定依据):

ui-tui/src/app/useInputHandlers.ts:504 @ 863e313

```ts
    if (key.pageUp || key.pageDown) {
      // Half-viewport keeps 50% continuity and stays under Ink's
      // `delta < innerHeight` DECSTBM fast-path threshold.
      const viewport = terminal.scrollRef.current?.getViewportHeight() ?? Math.max(6, (terminal.stdout?.rows ?? 24) - 8)
      const step = Math.max(4, Math.floor(viewport / 2))

      return scrollTranscript(key.pageUp ? -step : step)
    }
```

同一文件 `:77` 还把 pageUp/pageDown 归入"应视为滚动意图"的判定。
`grep -rn "pageUp\|pageDown" ui-tui/src`(排除 `__tests__`)另有 6 处在
`agentsOverlay.tsx` 与 `journey.tsx` 里做 overlay 分页——**三个层次都在处理它**。

### ▲5 File map 对两个文件的描述与代码不符

ui-tui/README.md:456 @ 863e313

> perfPane.tsx               FPS / render perf overlay pane

`perfPane.tsx` **不画任何东西**:未开启时 `PerfPane` 原样返回 children,开启时
包一层 `React.Profiler`;所有采样都写进 JSON-lines 日志文件
(默认 `~/.hermes/perf.log`),屏幕上没有 pane,也不显示 FPS(FPS 在
`components/fpsOverlay.tsx` + `lib/fpsStore.ts`)。

ui-tui/src/lib/perfPane.tsx:65 @ 863e313

```tsx
export function PerfPane({ children, id }: { children: ReactNode; id: string }) {
  if (!ENABLED) {
    return children
  }

  return (
    <Profiler id={id} onRender={onRender}>
      {children}
    </Profiler>
  )
}
```

同一张 File map 的另一处:

ui-tui/README.md:391 @ 863e313

> overlayControls.tsx        shared overlay control buttons

`overlayControls.tsx` 全文 50 行,导出 `useOverlayKeys`(键盘钩子)、
`OverlayHint`(一行提示文字)、`windowOffset`、`windowItems`(列表开窗数学)——
**没有任何按钮组件**(全文见 §2.2 E 组;`grep -c "Button" ui-tui/src/components/overlayControls.tsx` = 0)。

### ◇1 File map 漏了 36 个组件里的 12 个

漏的是:`accordion.tsx`、`gridStreamsDemo.tsx`、`gridTestOverlay.tsx`、`journey.tsx`、
`loaders.tsx`、`overlay.tsx`、`overlayPrimitives.tsx`、`overlayScrollbar.tsx`、
`petPicker.tsx`、`petSprite.tsx`、`subscriptionOverlay.tsx`、`widgetGrid.tsx`。
漏掉的不是边角料:`subscriptionOverlay.tsx` 是全片第 4 大文件(1,024 行),
`journey.tsx` 595 行且是唯一发 `learning.*` RPC 的组件,`overlayPrimitives.tsx`
是几乎每个 overlay 都 import 的原语层。反向核对:File map 里列出的 24 个**都存在**。

### ◇2 File map 漏了 45 个 lib 模块里的 8 个

漏的是:`billingDialog.ts`、`charts.ts`、`color.ts`、`model-search-text.ts`、
`resizeCoalescer.ts`、`starmapPalette.ts`、`themeBoot.ts`、`widgetGrid.ts`。
其中 `color.ts` 自称"**THE** color primitive —— 整个 TUI 的颜色计算都过它",
`widgetGrid.ts`(510 行)是布局求解器,`themeBoot.ts` 是首帧主题机制——
三个都是核心件。反向核对:File map 里列出的 37 个**都存在**。

```verify
# ◇1/◇2 复核(bash,在 /home/user/hermes-agent/ui-tui 下跑;不落临时文件)
# 只在磁盘上、README File map 未列的组件(应打出 12 个)
comm -13 <(sed -n '377,401p' README.md | grep -oE "^      [a-zA-Z]+\.tsx" | tr -d ' ' | sort) \
         <(ls src/components/ | sort)
# 只在 README 里、磁盘上没有的组件(应为空)
comm -23 <(sed -n '377,401p' README.md | grep -oE "^      [a-zA-Z]+\.tsx" | tr -d ' ' | sort) \
         <(ls src/components/ | sort)
# 只在磁盘上、README File map 未列的 lib 模块(应打出 8 个)
comm -13 <(sed -n '435,472p' README.md | grep -oE "^      [a-zA-Z0-9]+\.tsx?" | tr -d ' ' | sort) \
         <(ls src/lib/ | grep -v '\.test\.' | sort)
# 只在 README 里、磁盘上没有的 lib 模块(应为空)
comm -23 <(sed -n '435,472p' README.md | grep -oE "^      [a-zA-Z0-9]+\.tsx?" | tr -d ' ' | sort) \
         <(ls src/lib/ | grep -v '\.test\.' | sort)
# 条数:24 / 36 与 37 / 45
sed -n '377,401p' README.md | grep -cE "^      [a-zA-Z]+\.tsx"; ls src/components/ | wc -l
sed -n '435,472p' README.md | grep -cE "^      [a-zA-Z0-9]+\.tsx?"; ls src/lib/ | grep -vc '\.test\.'
```

### ◇3 File map 整体漏掉 `ui-tui/scripts/`(9 文件)与 `src/sdk/`(11 文件)

`## File map` 的树从 `ui-tui/` 下直接列 `packages/hermes-ink/` 与 `src/`,
`scripts/` 这一整个目录没有出现;`src/` 下列了 10 个子目录,唯独没有 `src/sdk/`。
而 `package.json` 里有 `"visual": "node scripts/visual/run.mjs"`,
`appLayout.tsx` 第 2 行就 `import '../sdk/apps/index.js'`——两者都是活的。
后果是 README 的"Local package commands"清单里也没有 `visual`,
**整套视觉回归 harness 在文档里不存在**。

```verify
cd /home/user/hermes-agent/ui-tui
ls -d */                                  # packages/ scripts/ src/
ls -d src/*/                               # 含 src/sdk/
grep -n "scripts/\|sdk/" README.md | head  # File map 里没有这两个目录
```

### ◇4 "Markdown renderer handles …" 的能力清单少了一批

ui-tui/README.md:206 @ 863e313

> The Markdown renderer handles headings, lists, block quotes, tables, fenced code blocks, diff coloring, inline code, emphasis, links, and plain URLs.

字面为真(列出的都支持),所以不是 ▲。但 `markdown.tsx` 另有一批**没被提到**的能力:
行内与块级 LaTeX 数学(经 `lib/mathUnicode.ts` 转 Unicode,`\boxed{}` 用
U+0001/U+0002 哨兵标出后渲染成反显)、脚注(`FOOTNOTE_RE`)、定义列表(`DEF_RE`)、
任务列表(`TASK_RE`)、setext 标题(`SETEXT_RE`)、水平分割线(`HR_RE`)、
`MEDIA:` 行与 `[[audio_as_voice]]` 指令(`MEDIA_LINE_RE` / `AUDIO_DIRECTIVE_RE`)、
以及 `lib/syntax.ts` 的语法高亮。数学支持尤其不该省:它是
`streamingMarkdown.tsx` 里"未闭合 `$$` 视为永远开着"那条不变量的**唯一理由**。

---

## §7 未取证与推定

诚实列出我**没有**验证的部分:

1. **一行代码都没跑过。** 未 `npm install`、未 `vitest`、未 `npx tsx` 任何脚本
   (派工书铁律 3)。所有关于渲染结果、基准数值、PNG 长相的陈述都是**读代码得出的**,
   不是观测到的。§6 ■1 的那次 `node -e` 是把函数体**转抄**后执行的纯函数,
   不是导入基线模块——所以它证明的是"这段逻辑在这些输入下产出什么",
   而不是"运行中的 TUI 确实这样"。可达路径(Shift+Enter → Home → Ctrl+U)是我**推演**的,
   未在真终端复现。
2. **实现体基本没读。** 按 L2 口径,以下大文件我只读了接口面、头部注释、
   导出表与关键分支,**没有逐个方法读实现**:`markdown.tsx`(1,178 行,
   只读了缓存层、表格换行、正则表和 `MdInline` 的入口)、`subscriptionOverlay.tsx`(1,024)、
   `agentsOverlay.tsx`(976)、`billingOverlay.tsx`(950)、`activeSessionSwitcher.tsx`(917)、
   `appChrome.tsx`(890)、`mathUnicode.ts`(783,只读设计规则注释与哨兵常量)、
   `modelPicker.tsx`(710)、`journey.tsx`(595)、`appLayout.tsx`(591)、
   `branding.tsx`(562)、`externalLink.ts`(440)、`terminalSetup.ts`(444)、
   `platform.ts`(414,只读了修饰键归一与语音键部分)。
3. **`thinking.tsx` 的 380–560 行(`SubagentAccordion` 的 sections 装配)只读了两端**,
   中间的每个 section(thinking / tools / notes / kids)如何拼 header 未逐行核。
4. **`textInput.tsx` 的按键分派树我读全了,但没有穷举它的等价类。**
   例如 `isMacActionFallback` 的四个目标(`a`/`e`/`u`/`w`)在各终端下的真实到达情况、
   `voiceRecordKey` 与所有默认键的冲突矩阵,都没做。
5. **▲2 的未排除面**:分叉 Ink 的键解析表(`packages/hermes-ink/`)是否会把字母键
   翻成 `key.*` 布尔位,我没读。若它会,理论上有一条我看不到的路径。
   但审批分支只消费 `ch` 和 `approvalAction` 认识的四个 key 位,所以这个漏洞窗很窄。
6. **▲1 的未排除面**:只搜了静态 `import`/字面量,没搜运行时动态 `import()`。
7. **本片 45 个 lib 模块里有 12 个有同名 `.test.ts` 兄弟文件**
   (`billingDialog`、`color`、`editor`、`fuzzy`、`liveProgress`、`memory`、`messages`、
   `model-search-text`、`openExternalUrl`、`resizeCoalescer`、`text`、`todo`),
   **它们不在本片清单里**(应属 LT 层)。我读了其中几个的用例名当行为规格参照
   (如 `todo.test.ts` 那条 "uses fixed-width ASCII markers so the active row does not
   render wide or emoji-like" 直接解释了 `todo.ts` 为什么不用 emoji),但没系统整理。
8. **`README.md` 我逐节读了,但只对"能在本片证伪/证实"的断言做了判定。**
   `## App model`、`## Event surface`(41 个事件类型)、`## Theme model`、
   `## Commands`(命令清单)这几节的对象在 `src/app/`、`gatewayTypes.ts`、`theme.ts`,
   都在片外,我**没有**判定它们——那是别的片的活,不要以为"README 已经查过了"。
9. **`scripts/` 的基准脚本我没有跑,因此不知道当前基线上的实际数值**;
   §5.4 里所有"判据"都是从脚本的输出字段与注释推出的**应然**,不是实测值。

---

## §8 L2 判据自评

| # | 判据 | 自评 | 说明 |
|---|---|---|---|
| 1 | 片内每个文件至少出现一次全路径 + 一句话角色 | ✅ **97/97** | §2 四张表按 7 + 36 + 45 + 9 逐个列全路径,每个一句话角色。同型薄文件也各自单列(如 `todo.ts` 9 行、`paths.mjs` 11 行)。机械核查见本节末。 |
| 2 | 每个对外接缝逐项列全 + 机械枚举命令 + 条数 | ✅ | S1 RPC 方法 **17 个 / 20 处**、S2 npm 脚本 **13** 条、S3 依赖 **8+7+1**、S4 环境变量 **52**、S5 账单夹具 **16**、S6 视觉场景 **4**、S7 导出面 **158/239**。每项都给了 ```verify``` 命令。两条负结论(无第三种协议出口、bench 脚本无调用方)都写了搜索面。 |
| 3 | 一条端到端链逐跳带锚点 | ✅ | §4 `/pet list` 八跳,含 Python 侧两个 handler 与线程池白名单;明确标出上游端在 `src/app/slash/`、下游端在 `tui_gateway/`,本片负责第 ②③⑥⑧ 跳。 |
| 4 | 至少 2 个围栏块是逐字源码摘录 | ✅ | 共 **23** 个逐字源码围栏(4 个 `ts`、14 个 `tsx`、3 个 `python`、1 个 `nix`、1 个无标记的 `.mjs`),外加 6 个 `>` 文档摘录块;另有 10 个 ```` ```verify ```` 声明式非源码块。全部用 `sed -n 'A,Bp'` 取出后原样粘贴,未手抄。其中 2 个(`ui-tui/scripts/build.mjs` 与 `nix/tui.nix`)的锚点扩展名 `.mjs` / `.nix` **不在 `verify_citations.py` 的识别表内**,因此**未被机械校验**——已在正文就地声明,不当成已验证。 |
| 5 | 至少一条 ■/▲/◇/◎ | ✅ | **■1 + ▲5 + ◇4 = 10 条**,全部带锚点与逐字代码/引用块。无 ◎。 |

判据 1 的机械核查(逐条拿清单里的路径回查底稿,期望 `missing=0 / 97`):

```verify
cd /home/user/hermes-study
miss=0
while read -r p; do
  grep -qF "$p" notes/r10-raw-ui-tui-components.md || { echo "MISSING: $p"; miss=$((miss+1)); }
done < data/r10/slices/E.txt
echo "missing=$miss / $(wc -l < data/r10/slices/E.txt)"
```

引用校验读数(交付前实跑):`citations=39 OK=32 UNCHECKED=7`,
可校验比例 **82.1%**(下限 70%),`MISMATCH=0`、`BLOCK-DRIFT=0`;
表格行内锚点 `table_anchors=24 OK=24`(`TABLE-DRIFT=0`、`TABLE-OUT-OF-RANGE=0`),
退出码 0 且输出 `OK: every code-block-backed citation matches the baseline`。
那 7 条 UNCHECKED 全是散文里顺带提到、后面不接代码块的锚点(单测文件、
提示行行号之类),不是"块后 + 散文隔开"那种无声排版违规。

**没做到的部分**(与 §7 呼应,不重复):判据 2 的"每个接缝"我按**协议/配置/枚举表**
理解并穷举;但如果把"组件的 props 契约"也算接缝,那我**没有**穷举——
36 个组件的 props interface 没有逐个列表(只列了导出符号数)。
这是我对判据的解读,如果口径是后者,那本片判据 2 只算做到约六成。

---

## §9 移交

| 编号 | 锚点 + 现象 | 建议 |
|---|---|---|
| H-R10E-a | `ui-tui/src/components/textInput.tsx:334`:`export function killToLineStart(value: string, cursor: number): { value: string; cursor: number } {` —— `cursor === 0` 且 `value[0] === '\n'` 时返回值多了一个换行、光标前移到 1;分派处 `ui-tui/src/components/textInput.tsx:1297` 的 `actionDeleteToStart` 分支无 `c > 0` 守卫。 | 归入 R11/R12 的"■ 汇总";若将来要给上游提 issue,这是本片唯一一条可独立成立的代码缺陷。 |
| H-R10E-b | `ui-tui/README.md:182`:`- Clarify free-text mode and masked prompts use` …(整句见 §6 ▲1)—— 与 `ui-tui/src/components/maskedPrompt.tsx:6`:`import { TextInput } from './textInput.js'` 直接冲突。 | 写 TUI 章时,**不要**沿用 README 的"两套输入实现"叙事——全客户端只有一个行编辑器。 |
| H-R10E-c | `ui-tui/src/components/appLayout.tsx:2`:`import '../sdk/apps/index.js'` —— `src/sdk/`(11 文件)是 widget app SDK,本片只见到它被"为副作用而 import"这一个接触点,SDK 本体不在本片清单里。 | 请确认 `src/sdk/` 已被 R10 的某一片覆盖;若未覆盖,它是本轮的一个黑洞(它含 `host.tsx`、`registry.ts`、`userWidgets.ts` 与 5 个参考 app)。 |
| H-R10E-d | `ui-tui/src/lib/model-search-text.ts:8` 的 `Keep in sync with web/src/lib/model-search-text.ts and` —— 该文件自述要与 web 端和 `hermes_cli/model_search.py` 三处同步,本片未做三方比对。 | 交给覆盖 `web/` 或 `hermes_cli/` 的片做一次三方一致性核对;不一致就是一条 ■。 |
| H-R10E-e | `ui-tui/src/lib/inputMetrics.ts:41`:`const wrapped = wrapAnsi(value, width, { hard: true, trim: false })` —— 光标定位的正确性**完全依赖**分叉 Ink 导出的 `wrapAnsi` 与 `<Text wrap="wrap">` 内部用的是同一份实现/同一组选项;本片无法验证这一点。 | 交给覆盖 `ui-tui/packages/hermes-ink/` 的片确认:`entry-exports.ts` 导出的 `wrapAnsi` 与 Text 渲染路径调用的是否同一个函数、选项是否一致。这是"光标漂移"整类 bug 的根。 |
| H-R10E-f | `ui-tui/src/components/textInput.tsx:474`:`export function canFastBackspaceShape(current: string, cursor: number, columns?: number): boolean {` —— `columns` 可选,注释明写"新调用方不许省略",但类型系统不强制。 | 若 R11 要做"可迁移设计原则"一节,这是一个好例子:注释里的契约 vs 类型里的契约。当前唯一生产调用方 `ui-tui/src/components/textInput.tsx:848`:`canFastBackspaceShape(current, cursor, columns)` 确实传了宽度。 |
